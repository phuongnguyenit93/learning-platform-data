# Assignment, Expressions, and NULL Handling

In PL/SQL, variables store values so that a program can perform calculations, evaluate conditions, and pass data between statements. An assignment statement uses the := operator. Oracle evaluates the expression on the right side first, then places the result into the variable or assignable target on the left side.

A NULL value represents unknown, unprovided, or inapplicable data. NULL is not equivalent to 0, FALSE, or a string containing spaces. When a comparison involves NULL, the result can be UNKNOWN. That is why many PL/SQL and SQL conditions must intentionally use IS NULL, COALESCE, NVL, or CASE.

This lesson explains how to declare and assign variables, combine expressions, retrieve data using SELECT INTO and RETURNING INTO, the three-valued logic rules TRUE/FALSE/UNKNOWN, how conditions behave when NULL appears, and the NULL-handling tools commonly used in Oracle.

## 1. Assignment Statements in PL/SQL

Basic syntax:

~~~sql
variable_name := expression;
~~~

Example:

~~~sql
DECLARE
    v_quantity NUMBER := 3;
    v_unit_price NUMBER := 125;
    v_total NUMBER;
BEGIN
    v_total := v_quantity * v_unit_price;
    DBMS_OUTPUT.PUT_LINE('Total = ' || v_total);
END;
/
~~~

Oracle evaluates v_quantity * v_unit_price first, then assigns the result 375 to v_total.

### 1.1. := vs. =

In PL/SQL:

- := is used to assign a value to a variable.
- = is used for equality comparison in conditions.

~~~sql
DECLARE
    v_count NUMBER := 10;
BEGIN
    v_count := v_count + 1;       -- Reassign value.

    IF v_count = 11 THEN          -- Equality comparison.
        DBMS_OUTPUT.PUT_LINE('Eleven');
    END IF;
END;
/
~~~

In SQL DML statements, the syntax uses the equals sign in the SET clause:

~~~sql
UPDATE products
SET unit_price = unit_price * 1.05
WHERE product_id = 100;
~~~

SET unit_price = ... is SQL column update syntax. Do not replace the equals sign in SQL with :=.

### 1.2. Assigning to Record Fields

A record variable can be assigned field by field:

~~~sql
DECLARE
    TYPE t_employee IS RECORD (
        employee_id NUMBER,
        full_name   VARCHAR2(100),
        salary      NUMBER
    );
    v_employee t_employee;
BEGIN
    v_employee.employee_id := 101;
    v_employee.full_name := 'Lan Nguyen';
    v_employee.salary := 2500;
END;
/
~~~

The left-hand side can be a scalar variable, a record field, or an assignable collection element. The expression on the right-hand side must be compatible with the target data type.

## 2. Declaring and Initializing Variables

PL/SQL variables are declared in the declarative section of a block, procedure, function, or package. Without an initial value, a scalar variable starts with the value NULL.

### 2.1. Assigning a Value at Declaration

~~~sql
DECLARE
    v_name VARCHAR2(50) := 'Oracle';
    v_count PLS_INTEGER := 0;
    v_rate NUMBER(5, 2) DEFAULT 7.5;
BEGIN
    DBMS_OUTPUT.PUT_LINE(v_name);
    DBMS_OUTPUT.PUT_LINE(v_count);
    DBMS_OUTPUT.PUT_LINE(v_rate);
END;
/
~~~

Both := and DEFAULT can be used to set an initial value in a variable declaration. In regular code, choose one consistent style.

### 2.2. Uninitialized Variables Have a NULL Value

~~~sql
DECLARE
    v_amount NUMBER;
BEGIN
    IF v_amount IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Amount has not been assigned');
    END IF;
END;
/
~~~

Do not assume an uninitialized numeric variable has a value of 0 or an uninitialized string variable is an empty string. If the program needs a default value, declare or assign it explicitly.

### 2.3. CONSTANT

A constant must be initialized at declaration and cannot be reassigned:

~~~sql
DECLARE
    c_tax_rate CONSTANT NUMBER := 0.08;
    v_net NUMBER := 1000;
    v_gross NUMBER;
BEGIN
    v_gross := v_net + (v_net * c_tax_rate);
    DBMS_OUTPUT.PUT_LINE(v_gross);
END;
/
~~~

If you try to reassign c_tax_rate, PL/SQL raises an error because a constant cannot be changed after declaration.

### 2.4. NOT NULL for Variables

A variable declared NOT NULL must have an initial value:

~~~sql
DECLARE
    v_status VARCHAR2(10) NOT NULL := 'NEW';
BEGIN
    v_status := 'DONE';
END;
/
~~~

Assigning NULL to a NOT NULL variable causes a runtime VALUE_ERROR. Only use NOT NULL when the program truly guarantees a valid value is always present.

### 2.5. Using %TYPE to Match Column Types

Instead of guessing the data type, you can declare a variable anchored to a column:

~~~sql
DECLARE
    v_customer_name customers.customer_name%TYPE;
    v_credit_limit  customers.credit_limit%TYPE;
BEGIN
    NULL;
END;
/
~~~

%TYPE keeps the variable type synchronized with the column type when table definitions change. It does not automatically apply every column constraint to the variable; for example, a %TYPE variable does not automatically inherit the column's NOT NULL constraint in all declaration contexts.

### 2.6. Using %ROWTYPE for a Row

~~~sql
DECLARE
    v_customer customers%ROWTYPE;
BEGIN
    SELECT *
    INTO v_customer
    FROM customers
    WHERE customer_id = 101;

    DBMS_OUTPUT.PUT_LINE(v_customer.customer_name);
END;
/
~~~

%ROWTYPE creates a record with fields matching the columns of a table or view. It is convenient for fetching a full row, though if only a few columns are needed, declaring individual variables and listing columns explicitly usually makes the code clearer.

## 3. Expressions in PL/SQL

An expression is a combination of literals, variables, constants, operators, and function calls that evaluates to a single value.

~~~sql
DECLARE
    v_quantity NUMBER := 4;
    v_price NUMBER := 250;
    v_discount_rate NUMBER := 0.10;
    v_total NUMBER;
BEGIN
    v_total := v_quantity * v_price * (1 - v_discount_rate);
    DBMS_OUTPUT.PUT_LINE(v_total);
END;
/
~~~

The result is 900.

### 3.1. Common Operator Groups

| Group | Operators | Example |
| --- | --- | --- |
| Arithmetic | +, -, *, /, ** | v_total := v_price * v_quantity; |
| String concatenation | \|\| | v_full_name := v_first \|\| ' ' \|\| v_last; |
| Comparison | =, <>, !=, <, >, <=, >= | IF v_score >= 50 THEN ... |
| Logical | AND, OR, NOT | IF v_age >= 18 AND v_active = 'Y' THEN ... |
| NULL check | IS NULL, IS NOT NULL | IF v_code IS NULL THEN ... |
| Set / range conditions | IN, BETWEEN, LIKE | IF v_status IN ('NEW', 'OPEN') THEN ... |

Oracle supports both <> and != for inequality; <> is the standard SQL form and is generally preferred.

### 3.2. Using Parentheses to Express Intent

Operators have precedence rules. When an expression is long, parentheses help readers clearly see how operations are grouped:

~~~sql
v_total := (v_quantity * v_unit_price)
           - (v_discount_amount + v_coupon_amount);
~~~

Do not rely on memorizing precedence when an expression has many operators, especially when mixing arithmetic, string concatenation, and logic.

### 3.3. CASE Expressions Returning a Value

CASE can be used directly inside an assignment:

~~~sql
DECLARE
    v_score NUMBER := 82;
    v_grade VARCHAR2(2);
BEGIN
    v_grade := CASE
        WHEN v_score >= 90 THEN 'A'
        WHEN v_score >= 80 THEN 'B'
        WHEN v_score >= 70 THEN 'C'
        WHEN v_score >= 60 THEN 'D'
        ELSE 'F'
    END;

    DBMS_OUTPUT.PUT_LINE(v_grade);
END;
/
~~~

All return branches of a CASE expression must have compatible data types. If no WHEN branch matches and there is no ELSE, the CASE expression returns NULL.

### 3.4. Functions as Part of Expressions

~~~sql
DECLARE
    v_name VARCHAR2(100) := '  lan nguyen  ';
    v_normalized VARCHAR2(100);
BEGIN
    v_normalized := INITCAP(TRIM(v_name));
    DBMS_OUTPUT.PUT_LINE(v_normalized);
END;
/
~~~

Functions can be nested, but deeply nested expressions become hard to read and debug. If a calculation involves multiple business steps, assign intermediate results to clearly named variables.

## 4. Data Types and Conversion During Assignment

The expression's value must be compatible with the target variable's type. Oracle can perform some implicit conversions, but you should not rely on implicit conversion if formatting or NLS settings might change.

### 4.1. Explicit Conversion

~~~sql
DECLARE
    v_amount_text VARCHAR2(30) := '1250.50';
    v_amount NUMBER(10, 2);
    v_date_text VARCHAR2(10) := '2026-11-14';
    v_order_date DATE;
BEGIN
    v_amount := TO_NUMBER(v_amount_text, '9999990D99',
                          'NLS_NUMERIC_CHARACTERS=''.,''');
    v_order_date := TO_DATE(v_date_text, 'YYYY-MM-DD');
END;
/
~~~

Explicit formats and NLS settings keep results consistent across sessions with different configurations. If the input string does not match the format or cannot be converted, Oracle raises a conversion error such as ORA-01722 or the corresponding date error.

### 4.2. CAST

CAST converts an expression to a specified type:

~~~sql
v_amount := CAST(v_amount_text AS NUMBER);
~~~

CAST is useful when you want to state the result type explicitly in SQL/PLSQL. For date or numeric strings with specific formats, TO_DATE and TO_NUMBER with a format model usually express intent more clearly.

### 4.3. Avoiding Implicit Conversion in Conditions

Do not compare a NUMBER column with an arbitrary string:

~~~sql
-- Do not rely on implicit conversion.
WHERE amount = '100'
~~~

Use a numeric literal instead:

~~~sql
WHERE amount = 100
~~~

Or convert binds/strings at the data boundary using explicit formats. Implicit conversion can depend on NLS settings, prevent index usage, or raise errors on invalid data.

## 5. Assigning Data from SQL Statements to Variables

### 5.1. SELECT ... INTO

In PL/SQL, SELECT ... INTO retrieves query results and assigns the columns to variables in order:

~~~sql
DECLARE
    v_name customers.customer_name%TYPE;
    v_limit customers.credit_limit%TYPE;
BEGIN
    SELECT customer_name, credit_limit
    INTO v_name, v_limit
    FROM customers
    WHERE customer_id = 101;

    DBMS_OUTPUT.PUT_LINE(v_name || ': ' || v_limit);
END;
/
~~~

The number of expressions in SELECT must match the number of variables in INTO, and the data types must be compatible.

SELECT INTO requires exactly one row:

- No rows: PL/SQL raises NO_DATA_FOUND.
- More than one row: PL/SQL raises TOO_MANY_ROWS.
- Exactly one row, but a column contains NULL: the corresponding variable receives NULL.

Example handling not-found:

~~~sql
DECLARE
    v_name customers.customer_name%TYPE;
BEGIN
    SELECT customer_name
    INTO v_name
    FROM customers
    WHERE customer_id = 999999;

    DBMS_OUTPUT.PUT_LINE(v_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Customer does not exist');
END;
/
~~~

Do not use WHEN OTHERS to hide TOO_MANY_ROWS or data errors. If business logic expects a single row, use an appropriate key/unique constraint or define a clear row-selection rule.

### 5.2. SELECT COUNT(*) INTO

The aggregate COUNT(*) without GROUP BY returns exactly one row, even when there are no source rows:

~~~sql
DECLARE
    v_count PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM customers
    WHERE status = 'ACTIVE';

    DBMS_OUTPUT.PUT_LINE(v_count);
END;
/
~~~

If there are no ACTIVE customers, v_count receives 0. This differs from SELECT customer_name INTO ... finding no rows, which raises NO_DATA_FOUND.

### 5.3. Assigning Values from DML Using RETURNING INTO

INSERT, UPDATE, or DELETE can return column values into variables using RETURNING INTO:

~~~sql
DECLARE
    v_new_id lab_orders.order_id%TYPE;
BEGIN
    INSERT INTO lab_orders (order_id, order_status)
    VALUES (lab_orders_seq.NEXTVAL, 'NEW')
    RETURNING order_id INTO v_new_id;

    DBMS_OUTPUT.PUT_LINE('Created order ' || v_new_id);
END;
/
~~~

The table and sequence names in the example are illustrative objects; create the corresponding table/sequence before running. RETURNING INTO is useful when you need to retrieve an ID or value just generated/updated by the database without re-querying.

For operations affecting multiple rows, you can use RETURNING BULK COLLECT INTO to receive multiple values into an appropriate collection. Do not use a scalar RETURNING INTO as if it automatically aggregates all affected rows.

## 6. What Is NULL?

NULL represents an unknown or missing value. It is not:

- The number 0.
- A string with space characters.
- FALSE.
- A default value guessed by the application.

Example of an order without a shipping date yet:

~~~sql
DECLARE
    v_shipped_at DATE;
BEGIN
    IF v_shipped_at IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Not shipped yet');
    END IF;
END;
/
~~~

NULL can carry multiple business meanings: unknown, not entered, not applicable, or not yet occurred. If those meanings must be distinguished, use a dedicated status/code instead of overloading NULL for all of them.

### 6.1. NULL in Assignment

~~~sql
DECLARE
    v_amount NUMBER := 100;
BEGIN
    v_amount := NULL;
    DBMS_OUTPUT.PUT_LINE(v_amount);
END;
/
~~~

A scalar variable that allows NULL will receive NULL. From that point onward, operations and comparisons involving it must be handled according to NULL rules.

### 6.2. Empty Strings in Oracle

In Oracle Database, a zero-length character string ('') is currently treated as NULL for standard character types. Therefore:

~~~sql
DECLARE
    v_text VARCHAR2(20) := '';
BEGIN
    IF v_text IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('NULL or empty input');
    END IF;
END;
/
~~~

A string containing spaces, such as ' ', is not the same as an empty string. If whitespace-only strings should be treated as missing data, use TRIM before checking for NULL:

~~~sql
IF TRIM(v_text) IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('No meaningful text');
END IF;
~~~

Oracle notes that the handling of zero-length strings may change in the future. Do not build critical business rules on empty strings and NULL always being identical; normalize inputs and store states explicitly.

## 7. Three-Valued Logic: TRUE, FALSE, and UNKNOWN

In SQL and PL/SQL, a comparison involving NULL typically produces UNKNOWN (represented by NULL in a PL/SQL Boolean context). Consequently, logic is not limited to just TRUE and FALSE.

### 7.1. Comparing with NULL

The following expressions do not evaluate to TRUE:

~~~sql
v_amount = NULL
v_amount <> NULL
NULL = NULL
~~~

They evaluate to UNKNOWN because Oracle does not know whether two undetermined values are equal.

Check for NULL using:

~~~sql
IF v_amount IS NULL THEN
    ...
END IF;
~~~

Check for a non-NULL value:

~~~sql
IF v_amount IS NOT NULL THEN
    ...
END IF;
~~~

### 7.2. Basic Truth Table

U below stands for UNKNOWN:

| A | B | A AND B | A OR B |
| --- | --- | --- | --- |
| TRUE | TRUE | TRUE | TRUE |
| TRUE | FALSE | FALSE | TRUE |
| TRUE | U | U | TRUE |
| FALSE | FALSE | FALSE | FALSE |
| FALSE | U | FALSE | U |
| U | U | U | U |

For NOT:

| A | NOT A |
| --- | --- |
| TRUE | FALSE |
| FALSE | TRUE |
| U | U |

Important consequences:

- TRUE AND NULL is UNKNOWN.
- FALSE AND NULL is FALSE.
- TRUE OR NULL is TRUE.
- FALSE OR NULL is UNKNOWN.
- NOT NULL is still UNKNOWN.

### 7.3. NULL in IF

In PL/SQL, the THEN branch runs only when the condition is TRUE. If the condition is FALSE or NULL/UNKNOWN, that branch does not run:

~~~sql
DECLARE
    v_score NUMBER;
BEGIN
    IF v_score >= 50 THEN
        DBMS_OUTPUT.PUT_LINE('Pass');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Not pass or score missing');
    END IF;
END;
/
~~~

Because v_score is NULL, the comparison v_score >= 50 yields UNKNOWN; the program runs ELSE. If business logic needs to distinguish failing from missing scores, check for NULL first:

~~~sql
IF v_score IS NULL THEN
    DBMS_OUTPUT.PUT_LINE('Score is missing');
ELSIF v_score >= 50 THEN
    DBMS_OUTPUT.PUT_LINE('Pass');
ELSE
    DBMS_OUTPUT.PUT_LINE('Fail');
END IF;
~~~

### 7.4. NULL in WHERE

In SQL, WHERE keeps only rows whose condition is TRUE. Rows producing FALSE or UNKNOWN are filtered out:

~~~sql
SELECT customer_id, credit_limit
FROM customers
WHERE credit_limit > 1000;
~~~

Rows with a NULL CREDIT_LIMIT are not returned because the condition evaluates to UNKNOWN. If you want to include rows without a credit limit set:

~~~sql
SELECT customer_id, credit_limit
FROM customers
WHERE credit_limit > 1000
   OR credit_limit IS NULL;
~~~

This differs from thinking NULL is like 0: if NULL were treated as 0, the results could differ significantly.

### 7.5. CASE When Conditions Are UNKNOWN

In a searched CASE, a WHEN branch is selected only when its condition is TRUE:

~~~sql
CASE
    WHEN v_amount > 0 THEN 'POSITIVE'
    WHEN v_amount = 0 THEN 'ZERO'
    WHEN v_amount < 0 THEN 'NEGATIVE'
    ELSE 'UNKNOWN'
END
~~~

If v_amount is NULL, the first three conditions are all UNKNOWN and the ELSE branch is chosen.

For a simple CASE:

~~~sql
CASE v_status
    WHEN 'NEW' THEN 'New'
    WHEN 'DONE' THEN 'Completed'
    ELSE 'Other'
END
~~~

If you want to handle NULL, use a searched CASE with WHEN v_status IS NULL. Do not write WHEN NULL expecting it to match a NULL value, because equality comparison with NULL does not return TRUE.

## 8. NULL in Operations and Expressions

### 8.1. Arithmetic

If a numeric operand is NULL, the arithmetic result is normally NULL:

~~~sql
DECLARE
    v_price NUMBER := 100;
    v_tax NUMBER;
    v_total NUMBER;
BEGIN
    v_total := v_price + v_tax;

    IF v_total IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Total is unknown');
    END IF;
END;
/
~~~

If v_tax has not been assigned, the total is also NULL. If business rules define unset tax as 0, make that rule explicit with NVL or COALESCE; do not automatically turn every NULL into 0.

### 8.2. String Concatenation

Oracle has a special string concatenation rule: concatenating a NULL/zero-length string with a non-empty string produces the non-empty string. Example:

~~~sql
DECLARE
    v_first VARCHAR2(20) := 'Lan';
    v_middle VARCHAR2(20);
    v_full VARCHAR2(60);
BEGIN
    v_full := v_first || ' ' || v_middle;
    DBMS_OUTPUT.PUT_LINE(v_full);
END;
/
~~~

The result is Lan with a trailing space. This differs from numeric addition. When joining multiple optional fields, proactively handle spaces/separators to avoid names with extra whitespace.

### 8.3. Aggregate Functions and NULL

SQL aggregate functions generally ignore NULL values:

| Expression | Behavior |
| --- | --- |
| COUNT(*) | Counts all rows |
| COUNT(column_name) | Counts rows where column_name is not NULL |
| SUM(column_name) | Sums non-NULL values |
| AVG(column_name) | Computes average over non-NULL values |
| MIN(column_name), MAX(column_name) | Ignores NULL when determining min/max |

If all input values to SUM or AVG are NULL, the aggregate result can be NULL. COUNT(column_name) in that case is 0.

~~~sql
SELECT
    COUNT(*) AS all_rows,
    COUNT(commission_pct) AS rows_with_commission,
    AVG(commission_pct) AS average_commission
FROM employees;
~~~

Do not interpret COUNT(commission_pct) = 0 as meaning there are no employees; it only means no rows have a non-NULL commission value.

## 9. Common NULL-Handling Functions

### 9.1. NVL

NVL(expr1, expr2) returns expr2 if expr1 is NULL; otherwise it returns expr1.

~~~sql
DECLARE
    v_commission NUMBER;
    v_pay NUMBER;
BEGIN
    v_pay := 1000 + NVL(v_commission, 0);
END;
/
~~~

In SQL:

~~~sql
SELECT employee_id,
       salary + NVL(commission_pct, 0) * salary AS total_pay
FROM employees;
~~~

NVL is useful when business rules specify a replacement value. Be aware of type conversion rules: Oracle converts expr2 to the data type of expr1 in many character cases; for numbers, numeric precedence rules apply. Pass two expressions with clearly compatible types.

### 9.2. NVL2

NVL2(expr1, expr2, expr3) returns expr2 if expr1 is not NULL, and returns expr3 if expr1 is NULL:

~~~sql
SELECT
    employee_id,
    NVL2(commission_pct, 'Commission eligible', 'No commission')
        AS commission_status
FROM employees;
~~~

NVL2 is useful when choosing one of two outcomes based on whether an expression is NULL.

### 9.3. COALESCE

COALESCE(expr1, expr2, ..., exprN) returns the first non-NULL expression:

~~~sql
SELECT
    customer_id,
    COALESCE(mobile_phone, work_phone, home_phone, 'No phone')
        AS contact_phone
FROM customers;
~~~

Unlike NVL, COALESCE accepts multiple arguments and is a standard SQL expression. Oracle evaluates it using short-circuiting: it stops at the first non-NULL expression. All returned expressions must have compatible data types.

### 9.4. NULLIF

NULLIF(expr1, expr2) returns NULL if the two expressions are equal; otherwise it returns expr1:

~~~sql
SELECT
    actual_amount / NULLIF(expected_amount, 0) AS ratio
FROM payment_checks;
~~~

If EXPECTED_AMOUNT = 0, the pattern above produces NULL instead of dividing by 0. If EXPECTED_AMOUNT is already NULL, the result remains NULL per comparison logic. NULLIF does not replace data validation; it only expresses an expression rule.

### 9.5. CASE

CASE lets you write complex, readable replacement rules:

~~~sql
CASE
    WHEN credit_limit IS NULL THEN 'NOT SET'
    WHEN credit_limit = 0 THEN 'ZERO'
    WHEN credit_limit < 0 THEN 'INVALID'
    ELSE 'SET'
END
~~~

When conditions involve NULL, IS NULL prevents unexpected UNKNOWN results.

### 9.6. DECODE

Oracle's DECODE has a special rule: two NULL values are treated as equal in DECODE's matching logic:

~~~sql
SELECT DECODE(optional_code,
              NULL, 'MISSING',
              'PRESENT') AS code_status
FROM source_rows;
~~~

This differs from optional_code = NULL, which evaluates to UNKNOWN. DECODE is a legacy Oracle function; for new logic, CASE WHEN optional_code IS NULL THEN ... is usually clearer and more portable across database engines.

## 10. NULL-Safe Comparisons

Many problems require checking whether two values are the same, where two NULLs are also considered to represent the same missing state.

### 10.1. Explicit Condition Pattern

~~~sql
IF (v_old_value = v_new_value)
   OR (v_old_value IS NULL AND v_new_value IS NULL)
THEN
    DBMS_OUTPUT.PUT_LINE('Same value');
ELSE
    DBMS_OUTPUT.PUT_LINE('Different value');
END IF;
~~~

When one value is NULL and the other is not NULL, the first branch is UNKNOWN while the second branch is FALSE; the overall result is not TRUE and execution goes to ELSE. When both are NULL, the second branch is TRUE.

### 10.2. Using DECODE to Compare Two Values

~~~sql
IF DECODE(v_old_value, v_new_value, 1, 0) = 1 THEN
    DBMS_OUTPUT.PUT_LINE('Same value');
END IF;
~~~

DECODE treats two NULLs as equal. However, pay attention to implicit conversion rules and argument data types. For complex conditions or portability, the explicit IS NULL pattern is easier to understand.

### 10.3. Avoiding Arbitrary Sentinels

A common approach is replacing NULL with a dummy value:

~~~sql
NVL(v_code, 'UNKNOWN')
~~~

If UNKNOWN is a valid value in the data, the replacement creates a collision between NULL and real values. For numbers, using -1 carries a similar risk if -1 can legitimately appear. Only use a sentinel when the domain excludes that value via constraints and clear business rules.

## 11. NULL in Optional Filter Conditions

A common application pattern is an optional filter parameter that can be NULL: NULL means do not filter by this column.

~~~sql
SELECT customer_id, customer_name
FROM customers
WHERE (:p_region IS NULL OR region_code = :p_region);
~~~

If :p_region is NULL, the first side is TRUE so the query does not restrict by region. If a value is provided, the query filters by that region.

This is a convenient pattern, but on large tables an OR predicate can affect execution plans and index usage depending on bind peeking/optimizer behavior. For critical workloads, inspect the execution plan; you may need dynamic SQL with bind variables to add the predicate only when the parameter is supplied.

If business logic needs to find rows where REGION_CODE is NULL, then a NULL parameter cannot simultaneously mean "do not filter." Use a separate flag or an API that clearly expresses both states: skip filter and filter for NULL.

## 12. Short-Circuit Evaluation

In PL/SQL, the logical operators AND and OR perform short-circuit evaluation:

- For A AND B, if A is FALSE, PL/SQL does not need to evaluate B.
- For A OR B, if A is TRUE, PL/SQL does not need to evaluate B.

Example:

~~~sql
IF v_denominator <> 0
   AND v_numerator / v_denominator > 10
THEN
    DBMS_OUTPUT.PUT_LINE('Ratio is large');
END IF;
~~~

In PL/SQL, if the first side is FALSE, the division is not evaluated. However, do not rely on expression evaluation order inside a SQL query to protect a conversion that could fail. The SQL optimizer can reorder predicates. Use safe expressions such as NULLIF, CASE, or data validation to avoid errors inside the calculation itself.

Safe division example:

~~~sql
v_ratio := v_numerator / NULLIF(v_denominator, 0);
~~~

If the denominator is 0 or NULL, the result is NULL; the program can check the result before using it.

## 13. Comprehensive Lab: Calculating Order Totals with NULLs

Let's create a simple order-lines table:

~~~sql
CREATE TABLE lab_order_lines (
    line_id       NUMBER PRIMARY KEY,
    quantity      NUMBER,
    unit_price    NUMBER(10, 2),
    discount_rate NUMBER(5, 4),
    note          VARCHAR2(100)
);

INSERT INTO lab_order_lines VALUES (1, 2, 100, 0.10, 'Promo');
INSERT INTO lab_order_lines VALUES (2, 3, 50, NULL, 'No discount set');
INSERT INTO lab_order_lines VALUES (3, 1, 80, 0.20, NULL);
INSERT INTO lab_order_lines VALUES (4, NULL, 30, 0.00, 'Missing quantity');
COMMIT;
~~~

### 13.1. Observing Calculations When NULL Appears

~~~sql
SELECT
    line_id,
    quantity,
    unit_price,
    discount_rate,
    quantity * unit_price AS gross_amount,
    quantity * unit_price * (1 - discount_rate) AS net_amount
FROM lab_order_lines
ORDER BY line_id;
~~~

Expected results:

| LINE_ID | GROSS_AMOUNT | NET_AMOUNT | Explanation |
| ---: | ---: | ---: | --- |
| 1 | 200 | 180 | All operands have values |
| 2 | 150 | NULL | DISCOUNT_RATE is NULL |
| 3 | 80 | 64 | NULL NOTE does not affect numeric math |
| 4 | NULL | NULL | QUANTITY is NULL |

### 13.2. Applying a Rule Where NULL Means No Discount

Use this approach only if business rules confirm that a NULL discount means 0:

~~~sql
SELECT
    line_id,
    quantity * unit_price * (1 - NVL(discount_rate, 0))
        AS net_amount
FROM lab_order_lines
ORDER BY line_id;
~~~

Row 2 now has a net amount of 150. Row 4 remains NULL because quantity has no value; NVL only handles the discount rate.

### 13.3. Assigning to Variables and Handling Missing Cases

~~~sql
DECLARE
    v_line_id NUMBER := 2;
    v_quantity lab_order_lines.quantity%TYPE;
    v_price lab_order_lines.unit_price%TYPE;
    v_discount lab_order_lines.discount_rate%TYPE;
    v_net_amount NUMBER;
BEGIN
    SELECT quantity, unit_price, discount_rate
    INTO v_quantity, v_price, v_discount
    FROM lab_order_lines
    WHERE line_id = v_line_id;

    IF v_quantity IS NULL OR v_price IS NULL THEN
        DBMS_OUTPUT.PUT_LINE('Cannot calculate: missing quantity or price');
    ELSE
        v_net_amount := v_quantity * v_price
                        * (1 - COALESCE(v_discount, 0));
        DBMS_OUTPUT.PUT_LINE('Net amount = ' || v_net_amount);
    END IF;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('Line not found');
END;
/
~~~

This code distinguishes two situations: row not found versus row found but missing data needed for calculation. This is cleaner than replacing every NULL with 0 up front.

## 14. Common Mistakes

| Symptom | Cause | Solution |
| --- | --- | --- |
| Writing v_total = 100 to assign | Confusing comparison with assignment | Use v_total := 100 |
| Using := in SQL UPDATE | Confusing PL/SQL syntax with SQL | Use SET column = expression |
| Treating uninitialized variable as 0 | Wrong assumption about default values | Initialize explicitly or check IS NULL |
| x = NULL does not enter IF branch | Comparing with NULL yields UNKNOWN | Use x IS NULL |
| Two NULLs not treated as equal | SQL does not define NULL = NULL as TRUE | Write a NULL-safe condition or use DECODE intentionally |
| Adding numbers produces NULL | One operand is NULL | Confirm business rules then use NVL/COALESCE if appropriate |
| String has trailing space | Concatenating with NULL still keeps separator | TRIM or build strings conditionally |
| SELECT INTO raises NO_DATA_FOUND | Query returns no rows | Handle the exception or check existence as needed |
| SELECT INTO raises TOO_MANY_ROWS | Query returns more than one row | Use a unique key or a clear row-selection rule |
| String-to-number conversion fails | Data does not match format or NLS | Use TO_NUMBER/TO_DATE with explicit format and NLS |
| CASE misses NULL branch | Using simple CASE WHEN NULL | Use searched CASE with IS NULL |
| NVL replaces NULL with a value breaking business logic | Inappropriate sentinel or default value | Replace NULL only per clear business rules |
| COUNT(column) is lower than COUNT(*) | COUNT(column) ignores NULL | Choose the right count form for your purpose |
| Relying on AND in SQL to prevent conversion errors | Optimizer may reorder predicate evaluation | Use CASE/safe conversion expressions and validate inputs |

## 15. Practice Exercises

Use the LAB_ORDER_LINES table from section 13.

### Exercise 1 — Declaration and Assignment

Declare variables for quantity, unit price, and total amount. Assign values with :=, compute the total using an arithmetic expression, and print the result.

### Exercise 2 — Distinguishing := and =

Write a block that both assigns v_count := v_count + 1 and uses IF v_count = 5. Explain the role of both operators.

### Exercise 3 — SELECT INTO

Fetch QUANTITY, UNIT_PRICE, and DISCOUNT_RATE for a given LINE_ID into %TYPE variables. Try a nonexistent ID and a query returning multiple rows; handle NO_DATA_FOUND and TOO_MANY_ROWS.

### Exercise 4 — Three-Valued Logic

Create a Boolean variable with value NULL. Test the expressions TRUE AND NULL, FALSE AND NULL, TRUE OR NULL, and NOT NULL. Predict which IF branch executes.

### Exercise 5 — Handling NULL with Functions

Calculate net amount using NVL, NVL2, COALESCE, and CASE. Explain when a NULL discount is allowed to be interpreted as 0.

### Exercise 6 — NULL-Safe Comparison

Write a condition that detects when old and new values are the same, including when both are NULL. Implement one version using IS NULL conditions and one version using DECODE.

### Exercise 7 — Empty Strings

Assign '', ' ', and '  ' to VARCHAR2 variables. Check IS NULL, LENGTH, and TRIM. Explain why whitespace-only strings must be normalized separately.

### Exercise 8 — Safe Division

Write an expression to calculate the ratio actual / expected. Test with expected equal to 0, NULL, and a positive number. Use NULLIF to avoid division by zero and decide how to display a NULL result.

## 16. Cleaning Up Lab Data

Run only in the lab schema you created, after completing the exercises:

~~~sql
DROP TABLE lab_order_lines PURGE;
~~~

PURGE bypasses the recycle bin. Do not run on business tables or data that may need recovery.

## Summary

In PL/SQL, := assigns the result of an expression to a variable; = is used for comparison. Uninitialized scalar variables hold NULL. Use CONSTANT, NOT NULL, %TYPE, and %ROWTYPE to express intent and keep data types consistent. SELECT INTO requires exactly one row, while RETURNING INTO retrieves values from DML.

NULL is not 0 or FALSE. Comparisons with NULL produce UNKNOWN, so use IS NULL/IS NOT NULL; in IF, only TRUE executes the THEN branch, whereas WHERE filters out both FALSE and UNKNOWN. The functions NVL, NVL2, COALESCE, NULLIF, CASE, and DECODE each have their own rules. Only replace NULL with a default value when business logic clearly defines the meaning of the replacement. When processing real data, control conversion types and formats, distinguish missing data from missing rows, and test NULL cases explicitly.

## Oracle Reference Documentation

- [Oracle Database PL/SQL Language Reference — Assignment Statement (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/assignment-statement.html) — assignment syntax in PL/SQL.
- [Oracle Database PL/SQL Language Reference — Expressions (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/plsql-expressions.html) — expressions and operators.
- [Oracle Database PL/SQL Language Reference — NULLs (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/nulls.html) — NULL in PL/SQL.
- [Oracle Database SQL Language Reference — Nulls (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Nulls.html) — NULL in SQL and conditions.
- [Oracle Database SQL Language Reference — NVL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/NVL.html) — replacing NULL.
- [Oracle Database SQL Language Reference — COALESCE (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/COALESCE.html) — choosing the first non-NULL expression.
- [Oracle Database SQL Language Reference — NVL2 (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/NVL2.html) — choosing a result based on NULL status.
- [Oracle Database SQL Language Reference — NULLIF (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/NULLIF.html) — returning NULL when two expressions are equal.

When deploying on an Oracle release other than 19c, consult the PL/SQL Language Reference and SQL Language Reference for your exact version, especially for Boolean rules, type conversions, empty strings, and the behavior of NULL-handling functions.
