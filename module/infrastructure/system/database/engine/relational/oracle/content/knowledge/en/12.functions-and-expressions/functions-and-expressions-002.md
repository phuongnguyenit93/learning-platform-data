# Numeric Functions: ROUND, TRUNC, MOD, CEIL, and FLOOR in Oracle Database

In Oracle SQL, the numeric functions commonly used for rounding, truncating fractional digits, finding remainders, or determining the nearest integers are **ROUND, TRUNC, MOD, CEIL, and FLOOR**. They look similar, but their rules differ significantly, especially when handling negative numbers:

- **ROUND** rounds to the requested digit position.
- **TRUNC** truncates digits beyond the requested position, moving toward 0.
- **MOD** returns the remainder according to Oracle's definition.
- **CEIL** returns the smallest integer greater than or equal to the input value.
- **FLOOR** returns the largest integer less than or equal to the input value.

For example, TRUNC(-2.7) equals -2, whereas FLOOR(-2.7) equals -3. Misunderstanding this difference can distort quantities, monetary amounts, ratios, or how data is bucketed into groups. This lesson covers syntax, SQL examples, practical applications, data types, NULL handling, and lab exercises using DUAL.

## 1. Overview

| Function | Syntax | Meaning | Example | Result |
|---|---|---|---|---:|
| ROUND | ROUND(n [, integer]) | Round to the specified position | ROUND(12.345, 2) | 12.35 |
| TRUNC | TRUNC(n [, integer]) | Truncate digits toward 0 | TRUNC(12.345, 2) | 12.34 |
| MOD | MOD(n2, n1) | Remainder of n2 divided by n1 | MOD(17, 5) | 2 |
| CEIL | CEIL(n) | Smallest integer not less than n | CEIL(12.1) | 13 |
| FLOOR | FLOOR(n) | Largest integer not greater than n | FLOOR(12.9) | 12 |

n, n1, and n2 are numeric expressions. The integer argument of ROUND and TRUNC specifies the digit position; if omitted, it defaults to 0, meaning the integer unit position.

These functions can be used in the SELECT list, WHERE, ORDER BY, calculated expressions, subqueries, INSERT, or UPDATE. When called in SELECT, they only produce result values; they do not modify data stored in the table.

## 2. ROUND: rounding numbers

### 2.1 Syntax and rounding position

~~~sql
ROUND(number [, integer])
~~~

- number is the numeric value to be rounded.
- integer is the digit position to round to.
- Omitting integer is equivalent to rounding to an integer.
- A positive integer indicates positions to the right of the decimal point; a negative integer indicates positions to the left.

~~~sql
SELECT ROUND(12.345)    AS rounded_integer,
       ROUND(12.345, 1) AS rounded_1_decimal,
       ROUND(12.345, 2) AS rounded_2_decimals,
       ROUND(12.345, 3) AS rounded_3_decimals
FROM dual;
~~~

Result:

| ROUNDED_INTEGER | ROUNDED_1_DECIMAL | ROUNDED_2_DECIMALS | ROUNDED_3_DECIMALS |
|---:|---:|---:|---:|
| 12 | 12.3 | 12.35 | 12.345 |

When rounding to two decimal places, the third digit is 5, so 12.345 becomes 12.35.

### 2.2 ROUND to integers and negative numbers

~~~sql
SELECT ROUND(2.1)  AS a,
       ROUND(2.5)  AS b,
       ROUND(2.9)  AS c,
       ROUND(-2.1) AS d,
       ROUND(-2.5) AS e,
       ROUND(-2.9) AS f
FROM dual;
~~~

Results for NUMBER:

| Expression | Result |
|---|---:|
| ROUND(2.1) | 2 |
| ROUND(2.5) | 3 |
| ROUND(2.9) | 3 |
| ROUND(-2.1) | -2 |
| ROUND(-2.5) | -3 |
| ROUND(-2.9) | -3 |

At exact half-way points such as 2.5 and -2.5, Oracle's NUMBER rounding moves away from 0. This is an important point to remember when processing negative numbers or financial data.

### 2.3 Positive argument: rounding to the right of the decimal point

~~~sql
SELECT ROUND(123.4567, 0) AS p0,
       ROUND(123.4567, 1) AS p1,
       ROUND(123.4567, 2) AS p2,
       ROUND(123.4567, 3) AS p3
FROM dual;
~~~

| P0 | P1 | P2 | P3 |
|---:|---:|---:|---:|
| 123 | 123.5 | 123.46 | 123.457 |

### 2.4 Negative argument: rounding to the left of the decimal point

~~~sql
SELECT ROUND(1234.56, -1) AS nearest_ten,
       ROUND(1234.56, -2) AS nearest_hundred,
       ROUND(1234.56, -3) AS nearest_thousand
FROM dual;
~~~

The results are 1230, 1200, and 1000, respectively.

~~~sql
SELECT ROUND(1249, -2) AS a,
       ROUND(1250, -2) AS b,
       ROUND(1251, -2) AS c
FROM dual;
~~~

The results are 1200, 1300, and 1300. With negative numbers:

~~~sql
SELECT ROUND(-1249, -2) AS a,
       ROUND(-1250, -2) AS b,
       ROUND(-1251, -2) AS c
FROM dual;
~~~

The results are -1200, -1300, and -1300.

### 2.5 ROUND and display formatting

~~~sql
SELECT ROUND(12.34567, 2) AS rounded_number,
       TO_CHAR(12.34567, 'FM9999990.00') AS formatted_text
FROM dual;
~~~

ROUND returns a rounded numeric value. TO_CHAR returns a formatted string. The two results may look identical on screen, but their data types differ. If further calculations are needed, keep the numeric value; only convert to a string at the display or report export step.

### 2.6 ROUND in SELECT does not update the table

~~~sql
SELECT amount,
       ROUND(amount, 2) AS amount_rounded
FROM invoice_line;
~~~

The query only produces result values. To overwrite stored data, a separate DML statement is required:

~~~sql
UPDATE invoice_line
SET amount = ROUND(amount, 2);
~~~

This UPDATE modifies real data, which can affect audits, reports, and reconciliation. Do not run a broad update command just to preview a function's result.

## 3. TRUNC: truncating digits toward 0

### 3.1 Syntax

~~~sql
TRUNC(number [, integer])
~~~

TRUNC removes digits beyond the specified position without rounding. If the second argument is omitted, it defaults to 0.

~~~sql
SELECT TRUNC(12.9876)    AS t0,
       TRUNC(12.9876, 1) AS t1,
       TRUNC(12.9876, 2) AS t2,
       TRUNC(12.9876, 3) AS t3
FROM dual;
~~~

| T0 | T1 | T2 | T3 |
|---:|---:|---:|---:|
| 12 | 12.9 | 12.98 | 12.987 |

### 3.2 Negative numbers: TRUNC differs from FLOOR

~~~sql
SELECT TRUNC(2.9) AS positive_value,
       TRUNC(-2.9) AS negative_value,
       FLOOR(-2.9) AS floored_value
FROM dual;
~~~

The results are 2, -2, and -3, respectively. TRUNC truncates toward 0; FLOOR returns the greatest integer less than or equal to the value.

### 3.3 Negative arguments in TRUNC

~~~sql
SELECT TRUNC(1234.567, -1) AS tens,
       TRUNC(1234.567, -2) AS hundreds,
       TRUNC(1234.567, -3) AS thousands
FROM dual;
~~~

The results are 1230, 1200, and 1000. Example contrasting with ROUND:

~~~sql
SELECT ROUND(1251, -2) AS rounded_hundred,
       TRUNC(1251, -2) AS truncated_hundred
FROM dual;
~~~

ROUND returns 1300; TRUNC returns 1200.

### 3.4 Practical application

~~~sql
SELECT product_id,
       exact_quantity,
       TRUNC(exact_quantity, 0) AS whole_quantity
FROM inventory_measurement;
~~~

TRUNC can be used when business rules require dropping the fractional part toward 0. If the requirement is to round according to measurement rules, use ROUND; do not substitute one rule for the other just to make results look neater.

### 3.5 TRUNC(number) vs. TRUNC(date)

Oracle overloads TRUNC for both NUMBER and DATE. This lesson focuses on numbers:

~~~sql
SELECT TRUNC(18.75, 1) AS numeric_truncation
FROM dual;
~~~

However:

~~~sql
SELECT TRUNC(SYSDATE) AS today_at_midnight
FROM dual;
~~~

uses the DATE overload to truncate the time to the start of the day. The second argument of TRUNC(DATE, fmt) is a format model such as 'MM' or 'YYYY', not a number of decimal places. The argument data type determines which overload is invoked.

## 4. MOD: obtaining the remainder

### 4.1 Syntax

~~~sql
MOD(n2, n1)
~~~

n2 is the dividend; n1 is the divisor. Example:

~~~sql
SELECT MOD(17, 5) AS remainder
FROM dual;
~~~

Because 17 = 5 * 3 + 2, the result is 2.

### 4.2 Oracle's rule and negative numbers

Oracle defines MOD using the formula:

~~~text
MOD(n2, n1) = n2 - n1 * FLOOR(n2 / n1)
~~~

Because this formula uses FLOOR, results for negative numbers can differ from the remainder operator in Java, C, or other languages.

~~~sql
SELECT MOD(11, 4) AS a,
       MOD(-11, 4) AS b,
       MOD(11, -4) AS c,
       MOD(-11, -4) AS d
FROM dual;
~~~

Result:

| A | B | C | D |
|---:|---:|---:|---:|
| 3 | 1 | -1 | -3 |

Explanation:

- MOD(11,4) = 11 - 4 * FLOOR(2.75) = 3.
- MOD(-11,4) = -11 - 4 * FLOOR(-2.75) = 1.
- MOD(11,-4) = 11 - (-4) * FLOOR(-2.75) = -1.
- MOD(-11,-4) = -11 - (-4) * FLOOR(2.75) = -3.

### 4.3 Divisor equal to 0

In Oracle, MOD(n2, 0) returns n2:

~~~sql
SELECT MOD(17, 0) AS result
FROM dual;
~~~

The result is 17. This is specific to MOD; you cannot infer that dividing 17 / 0 is also valid. In applications, you should still validate inputs and explicitly define how a zero divisor is handled.

### 4.4 Even/odd checks and group partitioning

For non-negative integers:

~~~sql
SELECT employee_id,
       MOD(employee_id, 2) AS parity
FROM staff;
~~~

MOD equals 0 for even numbers and 1 for odd numbers. If the data contains negative numbers, keep Oracle's MOD rule in mind; do not apply assumptions from the `%` operator in application languages.

Example of assigning task IDs to four round-robin groups:

~~~sql
SELECT task_id,
       MOD(task_id - 1, 4) + 1 AS worker_group
FROM task_queue;
~~~

This expression works for positive IDs and the intended distribution logic. It does not guarantee balanced actual load if IDs have gaps or input data follows a pattern.

## 5. CEIL: ceiling integer

### 5.1 Syntax and meaning

~~~sql
CEIL(n)
~~~

CEIL returns the **smallest integer greater than or equal to n**. You can picture it as the nearest integer above or equal to the value on the number line.

~~~sql
SELECT CEIL(2.1)  AS a,
       CEIL(2.9)  AS b,
       CEIL(2.0)  AS c,
       CEIL(-2.1) AS d,
       CEIL(-2.9) AS e
FROM dual;
~~~

Result:

| A | B | C | D | E |
|---:|---:|---:|---:|---:|
| 3 | 3 | 2 | -2 | -2 |

CEIL(-2.1) is -2 because -2 is greater than -2.1 and is the smallest integer satisfying the condition. CEIL does not mean always increasing the absolute value.

### 5.2 Calculating page count

A list has 101 records, with 20 records displayed per page:

~~~sql
SELECT CEIL(101 / 20) AS total_pages
FROM dual;
~~~

The result is 6 pages. The first five pages hold 100 records, and the last page holds the remaining record. This fits CEIL because the page count must be enough to contain all the data.

With dynamic data:

~~~sql
SELECT CEIL(total_rows / page_size) AS total_pages
FROM report_paging_config;
~~~

Ensure PAGE_SIZE is greater than 0 and handle NULL according to policy. Do not let pagination calculations depend on a zero divisor or missing data.

### 5.3 Calculating cartons/boxes required

There are 101 products, and each box holds at most 24 products:

~~~sql
SELECT CEIL(101 / 24) AS boxes_needed
FROM dual;
~~~

The result is 5 boxes. Four boxes hold 96 products, and the last box holds 5 products. CEIL is appropriate when you need enough whole units to hold the entire quantity.

## 6. FLOOR: floor integer

### 6.1 Syntax and meaning

~~~sql
FLOOR(n)
~~~

FLOOR returns the **largest integer less than or equal to n**.

~~~sql
SELECT FLOOR(2.1)  AS a,
       FLOOR(2.9)  AS b,
       FLOOR(2.0)  AS c,
       FLOOR(-2.1) AS d,
       FLOOR(-2.9) AS e
FROM dual;
~~~

Result:

| A | B | C | D | E |
|---:|---:|---:|---:|---:|
| 2 | 2 | 2 | -3 | -3 |

With negative numbers, FLOOR moves downward along the number line. -3 is less than -2.1, whereas -2 is greater than -2.1, so FLOOR(-2.1) is -3.

### 6.2 Counting complete groups

With 101 products, each box holds 24 products:

~~~sql
SELECT FLOOR(101 / 24) AS full_boxes,
       MOD(101, 24) AS remaining_items,
       CEIL(101 / 24) AS boxes_needed
FROM dual;
~~~

Result:

| FULL_BOXES | REMAINING_ITEMS | BOXES_NEEDED |
|---:|---:|---:|
| 4 | 5 | 5 |

- FLOOR counts the completely full boxes.
- MOD counts the remaining items after filling complete boxes.
- CEIL counts the total number of boxes needed.

This is an example of combining three functions to express a business requirement.

### 6.3 FLOOR differs from TRUNC for negative numbers

~~~sql
SELECT TRUNC(-2.7) AS truncated_value,
       FLOOR(-2.7) AS floored_value
FROM dual;
~~~

The results are -2 and -3.

| Function | Rule | For -2.7 |
|---|---|---:|
| TRUNC | Truncate toward 0 | -2 |
| FLOOR | Largest integer not exceeding n | -3 |
| CEIL | Smallest integer not less than n | -2 |

Do not replace FLOOR with TRUNC when calculating whole groups in a domain that can contain negative values.

## 7. Comparing ROUND, TRUNC, CEIL, and FLOOR

~~~sql
SELECT 2.7 AS input_value,
       ROUND(2.7) AS rounded,
       TRUNC(2.7) AS truncated,
       CEIL(2.7) AS ceiling,
       FLOOR(2.7) AS floor_value
FROM dual
UNION ALL
SELECT -2.7,
       ROUND(-2.7),
       TRUNC(-2.7),
       CEIL(-2.7),
       FLOOR(-2.7)
FROM dual;
~~~

Result:

| INPUT_VALUE | ROUNDED | TRUNCATED | CEILING | FLOOR_VALUE |
|---:|---:|---:|---:|---:|
| 2.7 | 3 | 2 | 3 | 2 |
| -2.7 | -3 | -2 | -2 | -3 |

You can remember them by purpose:

| Need | Function to Consider | Reason |
|---|---|---|
| Round money to 2 decimal places | ROUND(amount, 2) | Rounds based on the next digit |
| Drop digits without increasing absolute value | TRUNC(value, 2) | Truncates toward 0 |
| Calculate page count or boxes needed | CEIL(quantity / capacity) | Any remainder requires an extra unit |
| Count complete full groups | FLOOR(quantity / capacity) | Counts only full integer groups |
| Get remainder / check parity | MOD(value, divisor) | Computes remainder using Oracle's rule |
| Round to the nearest hundred | ROUND(value, -2) | Negative argument targets digits left of decimal |
| Truncate to thousands | TRUNC(value, -3) | Drops digits below the thousands place |

## 8. Precision, scale, and numeric data types

Oracle has common numeric types such as NUMBER, BINARY_FLOAT, and BINARY_DOUBLE. The input data type affects how numbers are represented and can affect calculation results.

### 8.1 NUMBER(p,s)

NUMBER(p,s) defines:

- p is precision, the maximum number of significant digits.
- s is scale, the number of digits after the decimal point; a negative scale sets precision to the left of the decimal point.

Example:

~~~sql
CREATE TABLE numeric_type_lab (
    amount_2dp NUMBER(12,2),
    rate_4dp   NUMBER(8,4),
    whole_no   NUMBER(8,0)
);
~~~

AMOUNT_2DP has scale 2; RATE_4DP has scale 4; WHOLE_NO has scale 0. When writing a value into a column with a limited scale, Oracle applies conversion rules for the target type, which may round digits exceeding the scale. If the value exceeds precision, the operation can raise an error.

### 8.2 ROUND in an expression vs. column scale

~~~sql
SELECT ROUND(123.456, 2) AS expression_value
FROM dual;
~~~

The expression returns a numeric value rounded to two decimal places. Meanwhile:

~~~sql
CREATE TABLE amount_store_lab (
    amount NUMBER(8,2)
);
~~~

defines a column with scale 2. The column type controls storage; the ROUND function expresses the calculation rule where it is called. Do not rely on column scale as a substitute for business rounding rules in SQL or application logic.

### 8.3 Using NUMBER for monetary data

~~~sql
CREATE TABLE invoice_amount_lab (
    invoice_id NUMBER PRIMARY KEY,
    amount     NUMBER(14,2) NOT NULL
);
~~~

NUMBER is a decimal numeric type suitable for many monetary problems requiring exact decimal rules. BINARY_FLOAT and BINARY_DOUBLE store numbers in binary floating-point format; some decimal fractions such as 0.1 do not have an exact finite binary representation. Consequently, calculations can contain approximation errors.

If business logic requires exact monetary calculations at a defined scale, use NUMBER with appropriate precision/scale and define the rounding step explicitly. Floating-point types fit workloads where approximation is acceptable and their computational characteristics are needed.

### 8.4 Distinguishing numeric values from display strings

~~~sql
SELECT amount,
       ROUND(amount, 2) AS rounded_amount,
       TO_CHAR(amount, 'FM9999990.000000') AS display_six_places
FROM invoice_line;
~~~

These are three distinct things:

1. The original numeric value AMOUNT.
2. The new numeric value returned by ROUND.
3. The string formatted by TO_CHAR.

Formatting for display with six decimal places does not give the stored value a scale of 6; similarly, TO_CHAR with two decimal places does not alter the underlying number.

## 9. Round per row or after aggregation?

The two expressions below do not always yield the same result:

~~~sql
SUM(ROUND(line_amount, 2))
ROUND(SUM(line_amount), 2)
~~~

Example with three lines, each having an amount of 0.005:

~~~sql
SELECT SUM(ROUND(amount, 2)) AS sum_rounded_lines,
       ROUND(SUM(amount), 2) AS rounded_total
FROM (
    SELECT 0.005 AS amount FROM dual
    UNION ALL
    SELECT 0.005 FROM dual
    UNION ALL
    SELECT 0.005 FROM dual
);
~~~

With NUMBER:

- Each line ROUND(0.005,2) becomes 0.01; the sum of the three rounded lines is 0.03.
- The sum of the original values is 0.015; rounding the sum to two decimal places yields 0.02.

The two results differ: 0.03 and 0.02. These reflect two different calculation policies, not an Oracle bug.

In invoicing/tax domains, regulations may require rounding per line, per tax category, per document, or only at the final total. Rules must be aligned across the database, backend, payment systems, and reports. Test negative values, refunds, and exact half-unit boundary cases as well.

## 10. NULL and type conversion

### 10.1 NULL arguments

~~~sql
SELECT ROUND(CAST(NULL AS NUMBER), 2) AS round_null,
       TRUNC(CAST(NULL AS NUMBER), 2) AS trunc_null,
       MOD(CAST(NULL AS NUMBER), 3) AS mod_null,
       CEIL(CAST(NULL AS NUMBER)) AS ceil_null,
       FLOOR(CAST(NULL AS NUMBER)) AS floor_null
FROM dual;
~~~

CAST(NULL AS NUMBER) clarifies the numeric type of the NULL value. When a required argument is NULL, standard numeric functions normally return NULL. Decide whether NULL means "unknown", "not applicable", or a default value permitted by business rules.

### 10.2 NVL and COALESCE

~~~sql
SELECT amount,
       ROUND(NVL(amount, 0), 2) AS rounded_or_zero
FROM invoice_line;
~~~

If AMOUNT is NULL, it is replaced with 0 before rounding. This is a data-substitution policy. Do not use NVL just to hide NULL if NULL genuinely means "undetermined".

### 10.3 Avoid implicit conversion from strings

Do not rely on implicit conversion:

~~~sql
SELECT ROUND('12.345', 2)
FROM dual;
~~~

The result depends on string-to-NUMBER conversion capability and related formatting rules. If the input is truly a string, convert explicitly:

~~~sql
SELECT ROUND(TO_NUMBER('12.345', '9999990D999'), 2)
FROM dual;
~~~

With format models containing decimal or thousands separators, NLS settings must be aligned. In applications, it is better to bind a NUMBER value instead of passing numeric strings for Oracle to guess.

### 10.4 Result data type

These functions return a numeric value. The result type depends on the argument type and Oracle's numeric precedence rules. When combining NUMBER with BINARY_FLOAT or BINARY_DOUBLE, the expression may be promoted to the type with higher precedence.

When designing views, APIs, or result tables, check metadata and driver mappings, especially when mixing financial decimals with floating-point values.

## 11. Real-world applications

### 11.1 Calculating page count

~~~sql
SELECT CEIL(257 / 25) AS total_pages
FROM dual;
~~~

The result is 11 pages if each page holds up to 25 records. When using dynamic data, ensure PAGE_SIZE is greater than 0 and handle NULL before computing.

### 11.2 Calculating full cases and remainder

~~~sql
SELECT product_id,
       quantity,
       FLOOR(quantity / 24) AS full_cases,
       MOD(quantity, 24) AS loose_units,
       CEIL(quantity / 24) AS cases_required
FROM warehouse_stock;
~~~

Assuming quantity is non-negative and each case holds 24 units:

- FLOOR calculates the number of full 24-unit cases.
- MOD calculates the remaining loose units.
- CEIL calculates the total number of cases required.

If quantity can be negative due to inventory adjustments, define separate business handling; do not mechanically interpret negative numbers as case counts.

### 11.3 Calculating percentages

~~~sql
SELECT department_id,
       actual_sales,
       target_sales,
       ROUND(
         actual_sales / NULLIF(target_sales, 0) * 100,
         2
       ) AS achievement_percent
FROM department_sales;
~~~

NULLIF(target_sales,0) avoids division by zero. If target equals 0, the ratio returns NULL; reports can display N/A instead of arbitrarily assigning 0%.

### 11.4 Rounding or truncating weight

~~~sql
SELECT item_id,
       measured_weight,
       ROUND(measured_weight, 3) AS rounded_weight,
       TRUNC(measured_weight, 3) AS truncated_weight
FROM shipment_item;
~~~

ROUND and TRUNC can yield different results. Follow measurement/billing regulations; do not pick TRUNC merely to avoid rounding up if the rules mandate ROUND.

### 11.5 Round-robin group assignment

~~~sql
SELECT task_id,
       MOD(task_id - 1, 4) + 1 AS worker_group
FROM task_queue;
~~~

For positive, sequential IDs, the expression produces groups 1, 2, 3, 4 and repeats. If IDs have gaps or data follows a pattern, groups may be uneven. For production workloads, measure the actual distribution.

### 11.6 Truncating or rounding revenue to thousands

~~~sql
SELECT branch_id,
       revenue,
       TRUNC(revenue, -3) AS revenue_thousand_truncated,
       ROUND(revenue, -3) AS revenue_thousand_rounded
FROM branch_revenue;
~~~

With a revenue of 1,234,567, TRUNC to thousands returns 1,234,000; ROUND returns 1,235,000. Aliases help readers clearly understand how the value was processed.

## 12. DUAL for quick testing

DUAL is a special single-row system table commonly used to evaluate expressions without reading business tables.

~~~sql
SELECT ROUND(12.345, 2) AS round_result,
       TRUNC(12.345, 2) AS trunc_result,
       MOD(17, 5) AS mod_result,
       CEIL(12.1) AS ceil_result,
       FLOOR(12.9) AS floor_result
FROM dual;
~~~

The result has one row with five columns. DUAL is useful for testing syntax, verifying negative-number rules, or comparing expressions before putting them into large table queries.

Test negative numbers too:

~~~sql
SELECT ROUND(-2.5) AS rounded_negative,
       TRUNC(-2.5) AS truncated_negative,
       CEIL(-2.5) AS ceil_negative,
       FLOOR(-2.5) AS floor_negative,
       MOD(-11, 4) AS mod_negative
FROM dual;
~~~

The results are -3, -2, -2, -3, and 1, respectively.

Never INSERT, UPDATE, or DELETE into SYS.DUAL for practice. Use SELECT from DUAL or create your own table in a lab schema if you need multiple rows.

## 13. Practicing with a dedicated numeric table

The following commands are intended for a dedicated practice schema with table-creation privileges and appropriate quota. Do not run test DDL/DML on a production schema. CREATE TABLE is DDL with an implicit commit.

### 13.1 Creating the table and loading data

~~~sql
CREATE TABLE lab_numeric_values (
    value_id     NUMBER PRIMARY KEY,
    description  VARCHAR2(50) NOT NULL,
    amount       NUMBER(12,4),
    divisor      NUMBER(8,2)
);

INSERT INTO lab_numeric_values VALUES
    (1, 'POSITIVE_FRACTION', 12.3456, 5);
INSERT INTO lab_numeric_values VALUES
    (2, 'NEGATIVE_FRACTION', -12.3456, 4);
INSERT INTO lab_numeric_values VALUES
    (3, 'ROUNDING_BOUNDARY', 12.3450, 2);
INSERT INTO lab_numeric_values VALUES
    (4, 'ZERO', 0, 3);
INSERT INTO lab_numeric_values VALUES
    (5, 'NULL_AMOUNT', NULL, 5);
INSERT INTO lab_numeric_values VALUES
    (6, 'LARGE_VALUE', 1251, 100);

COMMIT;
~~~

### 13.2 Running the functions on each row

~~~sql
SELECT value_id,
       description,
       amount,
       ROUND(amount, 2) AS amount_rounded,
       TRUNC(amount, 2) AS amount_truncated,
       CEIL(amount) AS amount_ceil,
       FLOOR(amount) AS amount_floor,
       MOD(amount, divisor) AS amount_mod
FROM lab_numeric_values
ORDER BY value_id;
~~~

Observations:

- The positive row shows ROUND and TRUNC differ when the last retained digit needs to increase.
- The negative row illustrates CEIL and FLOOR moving in opposite directions.
- The NULL row shows that expressions depending on AMOUNT return NULL.
- The LARGE_VALUE row demonstrates ROUND/TRUNC with negative arguments.

### 13.3 Comparing at the hundreds level

~~~sql
SELECT amount,
       ROUND(amount, -2) AS nearest_hundred,
       TRUNC(amount, -2) AS cut_to_hundred
FROM lab_numeric_values
WHERE value_id = 6;
~~~

With 1,251, the results are 1,300 and 1,200, respectively.

### 13.4 Cross-checking totals

~~~sql
SELECT SUM(ROUND(amount, 2)) AS sum_after_line_rounding,
       ROUND(SUM(amount), 2) AS round_after_sum
FROM lab_numeric_values
WHERE amount IS NOT NULL;
~~~

The two results may differ. Explain the difference by the order of rounding and aggregation rather than treating one result as a bug.

Only drop tables you created in the lab schema once you confirm the data is no longer needed. Never place DROP TABLE in a script that could accidentally run in production; ROLLBACK cannot undo committed DDL.

## 14. Performance and function placement

### 14.1 Functions in the SELECT list

~~~sql
SELECT order_id,
       ROUND(total_amount, 2) AS rounded_total
FROM orders;
~~~

Oracle evaluates the expression for the queried rows to produce the output. If the table is very large, evaluating expressions over many rows still incurs CPU cost.

### 14.2 Functions on columns in WHERE

~~~sql
SELECT order_id
FROM orders
WHERE TRUNC(total_amount) = 100;
~~~

If there is a regular B-tree index on TOTAL_AMOUNT, the TRUNC(total_amount) expression can prevent that index from being used directly as a range predicate on the base column. You can consider:

~~~sql
WHERE total_amount >= 100
  AND total_amount < 101
~~~

The two conditions are equivalent only when the data domain and comparison semantics match. With negative numbers, TRUNC moves toward 0, so never mechanically rewrite predicates. Verify the data domain and inspect the execution plan.

If queries frequently filter by the expression, a function-based index may be an option:

~~~sql
CREATE INDEX idx_orders_trunc_total
ON orders (TRUNC(total_amount));
~~~

This is DDL that changes structure and carries storage/maintenance overhead. Consider it only after reviewing workload, privileges, and execution plans; never create a production index just to test syntax.

### 14.3 Viewing the execution plan

~~~sql
EXPLAIN PLAN FOR
SELECT order_id,
       ROUND(total_amount, 2) AS rounded_total
FROM orders
WHERE total_amount >= 100
  AND total_amount < 101;

SELECT *
FROM TABLE(DBMS_XPLAN.DISPLAY);
~~~

EXPLAIN PLAN displays the estimated plan; it does not measure execution time or verify actual row counts. When tuning, inspect the actual plan, cardinality, access predicates, CPU/I/O, and data distribution.

## 15. NULLs, errors, and common misconceptions

| Misconception / Error | Reality | How to Handle |
|---|---|---|
| ROUND and TRUNC are the same | ROUND rounds, TRUNC truncates toward 0 | Test values just below/above thresholds |
| TRUNC(-2.7) = -3 | TRUNC(-2.7) = -2 | Use FLOOR if a lower integer is needed |
| FLOOR(-2.7) = -2 | FLOOR(-2.7) = -3 | Understand FLOOR along the number line |
| CEIL always increases absolute value | CEIL(-2.7) = -2 | CEIL is the smallest integer not less than n |
| MOD matches `%` in all languages | Oracle uses FLOOR and has distinct negative-number rules | Test all sign combinations |
| MOD with divisor 0 always raises an error | MOD(n2,0) returns n2 | Still validate input data |
| ROUND modifies table data | SELECT ROUND only computes output values | Only UPDATE modifies stored data |
| TO_CHAR rounds stored numbers | TO_CHAR produces display strings | Distinguish formatting from numeric calculation |
| Per-line ROUND always equals total ROUND | Order of rounding and summing can create differences | Follow business policy |
| NULL is automatically treated as 0 | NULL propagating through numeric expressions usually returns NULL | Use NVL/COALESCE when permitted |
| NUMBER and BINARY_DOUBLE are always identical | Binary floating point can use approximations | Use NUMBER for financial decimals |
| ROUND(x,-2) rounds to two decimal places | Negative argument targets positions left of decimal point | Test tens/hundreds examples |
| TRUNC is always TRUNC(number) | Oracle also has TRUNC(date) | Check argument types and overloads |

If the input is an invalid string, TO_NUMBER can raise a conversion error. Do not let strings like '12,34' enter ROUND without specifying decimal markers and NLS settings. Validate input formats, bind NUMBER values, and handle malformed data at the ingestion boundary.

When writing to a column with limited precision, out-of-range values can fail even after ROUND. Design NUMBER(p,s) to match the value domain; test both maximum and minimum extremes.

## 16. Practice exercises

**Question 1.** Predict:

~~~sql
SELECT ROUND(8.765, 2),
       TRUNC(8.765, 2)
FROM dual;
~~~

Hint: ROUND gives 8.77; TRUNC gives 8.76.

**Question 2.** Predict:

~~~sql
SELECT ROUND(-3.5),
       TRUNC(-3.5),
       CEIL(-3.5),
       FLOOR(-3.5)
FROM dual;
~~~

Hint: -4, -3, -3, and -4.

**Question 3.** Why does TRUNC(-8.9) differ from FLOOR(-8.9)?

Hint: TRUNC truncates toward 0 so it equals -8; FLOOR takes the lower integer so it equals -9.

**Question 4.** Compute MOD(-13,5) using Oracle's formula.

Hint: -13 - 5 * FLOOR(-13/5) = -13 - 5*(-3) = 2.

**Question 5.** You have 73 products, and each box holds 12 products. Write SQL to compute full boxes, loose units, and total boxes needed.

~~~sql
SELECT FLOOR(73 / 12) AS full_boxes,
       MOD(73, 12) AS remaining_units,
       CEIL(73 / 12) AS boxes_required
FROM dual;
~~~

The results are 6, 1, and 7.

**Question 6.** A report has three rows of 0.005. Why does SUM(ROUND(amount,2)) differ from ROUND(SUM(amount),2)?

Hint: Rounding each row creates three values of 0.01 that sum to 0.03; summing raw values first gives 0.015, which rounds to 0.02. Follow financial policy.

**Question 7.** When should you use NUMBER instead of BINARY_DOUBLE?

Hint: When exact decimal behavior is required for financial/unit rules, NUMBER is usually better. BINARY_DOUBLE suits floating-point computations where approximation errors are acceptable.

**Question 8.** What results do ROUND(12345, -3) and TRUNC(12345, -3) return?

Hint: Both return 12000. Try 12501 to see ROUND return 13000 while TRUNC returns 12000.

**Question 9.** What should you keep in mind when using MOD(n,2) for bucketing if n can be negative?

Hint: Oracle's MOD uses FLOOR; do not mechanically assume Java/C remainder behavior.

**Question 10.** How do TO_CHAR(ROUND(amount,2), 'FM9990.00') and ROUND(amount,2) differ in data type?

Hint: ROUND returns a numeric value; TO_CHAR returns a formatted string.

## 17. Workflow for choosing the right function

Before writing an expression, identify the requirement:

1. Need the nearest value? Use ROUND and specify the digit position.
2. Need to drop digits, always toward 0? Use TRUNC.
3. Need the upper integer to cover capacity or page counts? Use CEIL.
4. Need the lower integer to count complete full groups? Use FLOOR.
5. Need a remainder or cyclic check? Use MOD and verify negative-number semantics.
6. Can the data contain NULL? Clarify NULL meaning before substituting 0.
7. Is the numeric type right? Use NUMBER for exact decimal data when needed; check target column precision/scale.
8. Is the result only for display or for further calculation? Keep numeric types for calculations; use TO_CHAR only at the presentation step.

## 18. Summary

Oracle's five numeric functions address distinct needs:

- ROUND(n, p) rounds to position p; positive p is to the right of the decimal point, negative p is to the left.
- TRUNC(n, p) truncates digits toward 0 without rounding. For negative numbers, results differ from FLOOR.
- MOD(n2, n1) computes the remainder using FLOOR; negative numbers may differ from remainder operators in application languages.
- CEIL(n) returns the smallest integer not less than n.
- FLOOR(n) returns the largest integer not greater than n.

In real-world systems, pay attention to NULLs, NUMBER versus floating-point types, precision/scale, rounding timing per business rules, and the impact of functions on predicates and indexes. Use DUAL to quickly test boundary values, especially negative numbers and exact multiples, before applying queries to live data. Choosing the right function keeps SQL expressions readable, results explainable, and calculations consistent across reports and applications.
