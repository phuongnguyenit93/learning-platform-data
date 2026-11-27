# Variables, Constants, Scope, Nested Blocks, and Name Shadowing in PL/SQL

PL/SQL allows declaring variables and constants to store values during business processing. A variable can be used in expressions, conditionals, loops, SQL statements, and procedure calls. However, a variable does not exist everywhere in a program: it can only be accessed within the **scope** in which it is declared and any child blocks nested inside that scope.

When a nested PL/SQL block declares a variable with the same name as a variable in an outer block, the inner name **shadows** the outer name within the child block's scope. Without understanding this rule, a program can read or update the wrong variable even though the syntax is completely valid. A similar situation also occurs when a variable name matches a column name in embedded SQL.

This lesson belongs to the **PL/SQL Basics** topic of *Database Engine Relational Oracle*. The content focuses on:

- How to declare, initialize, and use variables in PL/SQL.
- Constants with the `CONSTANT` keyword.
- Scalar data types, anchored types `%TYPE`, and `%ROWTYPE` records.
- Variable scope, visibility, and lifetime.
- Nested blocks, block labels, and how to access parent block variables.
- Name shadowing among variables, parameters, package variables, and SQL columns.
- Naming conventions and hands-on exercises runnable in SQL Developer/SQL*Plus.

## 1. PL/SQL Block Structure and Declaration Placement

A PL/SQL block has at most three sections:

~~~sql
DECLARE
    -- Declarative section: variables, constants, types, cursors, exceptions...
BEGIN
    -- Executable section: PL/SQL statements
EXCEPTION
    -- Error-handling section (optional)
END;
/
~~~

- `DECLARE` is optional for an anonymous block. For stored procedures/functions/packages, the declarative section sits within their respective syntax.
- `BEGIN` and `END` enclose the executable section; this section is mandatory.
- `EXCEPTION` is optional for handling errors raised within the block.
- The `/` on its own line is a SQL*Plus/SQL Developer script command to send the entered block to the database; it is not a PL/SQL statement.

Variables and constants are declared in the declarative section, before `BEGIN`. Regular variables cannot be declared in the middle of executable statements as in some other programming languages.

Anonymous block example:

~~~sql
SET SERVEROUTPUT ON;

DECLARE
    l_customer_id NUMBER := 100;
    l_total       NUMBER(12,2) := 0;
BEGIN
    l_total := 1250.50;
    DBMS_OUTPUT.PUT_LINE(
        'Customer ' || l_customer_id ||
        ' total = ' || TO_CHAR(l_total)
    );
END;
/
~~~

`l_customer_id` and `l_total` are declared in the block, so they can only be used inside this block and its child blocks.

## 2. Declaring Variables

General syntax:

~~~sql
variable_name [CONSTANT] datatype [NOT NULL]
    [ { := | DEFAULT } expression ];
~~~

For a regular variable, omit the `CONSTANT` keyword:

~~~sql
DECLARE
    l_count       PLS_INTEGER;
    l_unit_price  NUMBER(10,2);
    l_description VARCHAR2(200);
    l_created_at  DATE := SYSDATE;
BEGIN
    l_count := 3;
    l_unit_price := 19.95;
    l_description := 'USB-C adapter';
END;
/
~~~

### Assigning initial values

A variable can be initialized at declaration using `:=` or `DEFAULT`:

~~~sql
DECLARE
    l_attempts PLS_INTEGER := 0;
    l_status   VARCHAR2(20) DEFAULT 'NEW';
BEGIN
    NULL;
END;
/
~~~

Without an initializing expression, a typical scalar variable has an initial value of NULL. Do not confuse the default NULL value with 0, an empty string, or FALSE.

### Assigning values after declaration

In the executable section, use the assignment operator `:=`:

~~~sql
DECLARE
    l_quantity PLS_INTEGER;
BEGIN
    l_quantity := 5;
    l_quantity := l_quantity + 2;
    DBMS_OUTPUT.PUT_LINE(l_quantity); -- 7
END;
/
~~~

The `=` sign is normally used in comparisons, whereas `:=` is used to assign a value to a PL/SQL variable.

### NOT NULL variables

You can declare a variable that cannot accept NULL using `NOT NULL`, but you must initialize it with a non-NULL value:

~~~sql
DECLARE
    l_customer_name VARCHAR2(100) NOT NULL := 'An';
BEGIN
    l_customer_name := 'Binh';
    -- l_customer_name := NULL; -- raises VALUE_ERROR
END;
/
~~~

If declared `NOT NULL` without an initial value, PL/SQL reports a compilation error. If `NULL` is assigned at runtime, `VALUE_ERROR` is raised.

## 3. Variable Data Types

PL/SQL supports SQL data types and PL/SQL-specific types. Choose types based on the value domain and how the data is used.

### Common scalar types

| Type | Purpose | Example |
| --- | --- | --- |
| NUMBER(p,s) | Integers or decimal numbers | NUMBER(12,2) |
| PLS_INTEGER | Signed integer suited for integer arithmetic in PL/SQL | PLS_INTEGER |
| BINARY_INTEGER | Compatible PL/SQL integer type | BINARY_INTEGER |
| VARCHAR2(n) | Variable-length character string | VARCHAR2(100) |
| CHAR(n) | Fixed-length character string | CHAR(2) |
| DATE | Date and time down to seconds | DATE |
| TIMESTAMP | Date and time with fractional seconds | TIMESTAMP |
| BOOLEAN | TRUE, FALSE, or NULL in PL/SQL | BOOLEAN |
| CLOB / BLOB | Large character data / large binary data | CLOB |

`BOOLEAN` is a PL/SQL type and cannot be used directly as a SQL `BOOLEAN` column in many traditional Oracle versions. Oracle Database 23ai adds a SQL `BOOLEAN` type; SQL availability depends on the version. In basic PL/SQL lessons, treat `BOOLEAN` as a PL/SQL expression/variable type unless you have confirmed the version and SQL type in use.

Example:

~~~sql
DECLARE
    l_amount    NUMBER(12,2) := 150.75;
    l_count     PLS_INTEGER := 4;
    l_name      VARCHAR2(80) := 'Oracle';
    l_is_active BOOLEAN := TRUE;
    l_started   TIMESTAMP := SYSTIMESTAMP;
BEGIN
    IF l_is_active THEN
        DBMS_OUTPUT.PUT_LINE(l_name || ': ' || l_count);
    END IF;
END;
/
~~~

### NUMBER and PLS_INTEGER

- Use `NUMBER` when decimals, currency, or SQL-style numeric precision are required.
- Use `PLS_INTEGER` for counters and integer arithmetic in PL/SQL when the value range fits.
- `PLS_INTEGER` has a 32-bit integer limit; overflowing the range raises an error.
- Do not use `NUMBER` for every variable merely because it is common; choose a type that is meaningful and appropriate for the data.

### BOOLEAN has three logical states

`BOOLEAN` can hold `TRUE`, `FALSE`, or `NULL`. Therefore, an `IF` condition executes the `THEN` branch only when the expression evaluates to `TRUE`:

~~~sql
DECLARE
    l_is_valid BOOLEAN;
BEGIN
    IF l_is_valid THEN
        DBMS_OUTPUT.PUT_LINE('Valid');
    ELSIF l_is_valid = FALSE THEN
        DBMS_OUTPUT.PUT_LINE('Invalid');
    ELSE
        DBMS_OUTPUT.PUT_LINE('Unknown');
    END IF;
END;
/
~~~

When `l_is_valid` is `NULL`, neither comparison against `TRUE` or `FALSE` evaluates to `TRUE`; execution enters `ELSE`. This is three-valued logic; `NULL` should not be treated as `FALSE` in every expression.

## 4. Anchored Types: %TYPE and %ROWTYPE

When a variable stores data fetched from a table, an independent type declaration can drift when column structures change. PL/SQL provides anchored declarations so variables track column types or row structures.

### %TYPE: taking the type from a column or another variable

Syntax:

~~~sql
variable_name table_name.column_name%TYPE;
~~~

Example:

~~~sql
DECLARE
    l_employee_id employees.employee_id%TYPE;
    l_salary      employees.salary%TYPE;
    l_new_salary  l_salary%TYPE;
BEGIN
    l_employee_id := 100;
    l_salary := 5000;
    l_new_salary := l_salary * 1.10;
END;
/
~~~

If the type or precision of `EMPLOYEES.SALARY` changes, variables declared with `%TYPE` automatically follow the column definition when the program is recompiled.

`%TYPE` can also reference an already declared variable:

~~~sql
DECLARE
    l_base_amount NUMBER(12,2) := 100;
    l_tax_amount  l_base_amount%TYPE;
BEGIN
    l_tax_amount := l_base_amount * 0.08;
END;
/
~~~

Note: `%TYPE` inherits the data type and associated length/precision attributes, but it does not automatically inherit the table column's `NOT NULL` constraint. A variable declared as `employees.employee_name%TYPE` can still accept `NULL` unless the variable itself is declared `NOT NULL`.

### %ROWTYPE: declaring a record matching a row

`%ROWTYPE` creates a record with fields corresponding to the columns of a table, view, or cursor:

~~~sql
DECLARE
    l_employee employees%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE(
        l_employee.employee_id || ': ' ||
        l_employee.first_name || ' ' ||
        l_employee.last_name
    );
END;
/
~~~

Record fields are accessed using dot notation: `l_employee.employee_id`, `l_employee.salary`. Field names and types follow the referenced source structure.

`SELECT * INTO record%ROWTYPE` is convenient when fetching an entire row. If selecting only a subset of columns, use `INTO` with variables/records matching the select item list; you cannot arbitrarily `SELECT` two columns into a full-row table record.

### Differences between %TYPE and %ROWTYPE

| Characteristic | %TYPE | %ROWTYPE |
| --- | --- | --- |
| Purpose | Declares a single variable matching a column/variable type | Declares a record of fields matching a row |
| Access | Uses the variable name directly | Uses `record.field` |
| Reference source | Column or PL/SQL variable | Table, view, or cursor |
| Suitable for | Single IDs, amounts, dates, names | Fetching/processing multiple columns of a row |

## 5. Constants with CONSTANT

A constant is a name representing a value that cannot be reassigned after declaration. Use `CONSTANT` to express configuration values, thresholds, rates, or fixed codes within a block's scope.

Syntax:

~~~sql
constant_name CONSTANT datatype [NOT NULL] := expression;
~~~

An initial value is mandatory:

~~~sql
DECLARE
    c_tax_rate   CONSTANT NUMBER(5,4) := 0.0800;
    c_max_retries CONSTANT PLS_INTEGER := 3;
    c_app_name  CONSTANT VARCHAR2(30) := 'OrderService';
BEGIN
    DBMS_OUTPUT.PUT_LINE(c_app_name);
    DBMS_OUTPUT.PUT_LINE(c_tax_rate);
END;
/
~~~

A constant cannot be reassigned:

~~~sql
DECLARE
    c_limit CONSTANT PLS_INTEGER := 10;
BEGIN
    -- c_limit := 20; -- error: constant cannot be modified
    NULL;
END;
/
~~~

### Initializing constants with expressions

The initial value can be a literal or a valid expression:

~~~sql
DECLARE
    c_started_at CONSTANT TIMESTAMP := SYSTIMESTAMP;
    c_today      CONSTANT DATE := TRUNC(SYSDATE);
BEGIN
    DBMS_OUTPUT.PUT_LINE(TO_CHAR(c_today, 'YYYY-MM-DD'));
END;
/
~~~

The expression is evaluated when the block executes/initializes. For a constant using `SYSDATE`, the value is the timestamp when that block initializes, not an immutable value across all program invocations.

### CONSTANT and NOT NULL

A constant must have an initial value; it can be combined with `NOT NULL` to state intent explicitly:

~~~sql
DECLARE
    c_region CONSTANT VARCHAR2(10) NOT NULL := 'APAC';
BEGIN
    NULL;
END;
/
~~~

Constants reduce bugs caused by accidental value modification and help readers distinguish fixed configuration from mutable state. However, do not declare local constants for every minor literal; name values when they carry business meaning or are reused.

## 6. Scope, Visibility, and Lifetime

These three concepts are related but not identical:

- **Scope:** the region of source code where a name is defined and can be referenced under language rules.
- **Visibility:** whether the name is visible at the current location or shadowed by a closer declaration.
- **Lifetime:** the duration during which the variable's value exists in memory/the session.

In PL/SQL, variables declared in a block have lexical scope: that block and child blocks nested inside it can reference the variable; outer blocks cannot access variables declared only inside child blocks.

Example:

~~~sql
DECLARE
    l_outer_value NUMBER := 10;
BEGIN
    DECLARE
        l_inner_value NUMBER := 20;
    BEGIN
        DBMS_OUTPUT.PUT_LINE(l_outer_value); -- sees outer variable
        DBMS_OUTPUT.PUT_LINE(l_inner_value); -- inner block variable
    END;

    DBMS_OUTPUT.PUT_LINE(l_outer_value); -- still visible
    -- l_inner_value is no longer in scope here.
END;
/
~~~

`l_inner_value` is only in scope within the nested block. After that block's `END`, code in the outer block cannot reference that name.

### Scope is lexical, not by call order

A child block sees the parent block's declarations because the child block is written inside that scope. A procedure declared elsewhere does not automatically see the calling block's local variables merely because it is invoked from that block. To pass data, use parameters; to share longer-lived state, use package variables or an appropriate storage mechanism.

### Lifetime of local variables

Local variables are created when their enclosing block/subprogram begins executing and cease to exist after that execution finishes. Each invocation of a normal subprogram has its own local state for that call.

Local variables are not persistent storage. To retain data across multiple calls or across a session, choose another mechanism such as package state (within a session), tables, properly managed collections, or external storage.

## 7. Nested Blocks and Variable Accessibility

A block can contain another block inside its executable section. The child block sees variables and constants declared in the parent block, provided the name is not shadowed by another declaration. The parent block does not see variables declared only in the child block.

~~~sql
SET SERVEROUTPUT ON;

DECLARE
    l_outer_value NUMBER := 10;
BEGIN
    DBMS_OUTPUT.PUT_LINE('Outer before: ' || l_outer_value);

    DECLARE
        l_inner_value NUMBER := 20;
    BEGIN
        DBMS_OUTPUT.PUT_LINE('Outer from inner: ' || l_outer_value);
        DBMS_OUTPUT.PUT_LINE('Inner value: ' || l_inner_value);
    END;

    DBMS_OUTPUT.PUT_LINE('Outer after: ' || l_outer_value);
    -- l_inner_value cannot be referenced here.
END;
/
~~~

The child block can read the outer variable. It can also reassign the outer variable if that variable is not shadowed:

~~~sql
DECLARE
    l_total NUMBER := 100;
BEGIN
    DECLARE
        l_tax NUMBER := 8;
    BEGIN
        l_total := l_total + l_tax;
    END;

    DBMS_OUTPUT.PUT_LINE(l_total); -- 108
END;
/
~~~

The child block does not create an automatic copy of the outer variable. When referencing the outer variable's name, the program reads or modifies the exact variable declared in the parent block.

### Multiple levels of nested blocks

A deeply nested block can access visible declarations from every enclosing parent level:

~~~sql
DECLARE
    l_company VARCHAR2(30) := 'Northwind';
BEGIN
    DECLARE
        l_department VARCHAR2(30) := 'Sales';
    BEGIN
        DECLARE
            l_employee VARCHAR2(30) := 'Mai';
        BEGIN
            DBMS_OUTPUT.PUT_LINE(
                l_company || '/' || l_department || '/' || l_employee
            );
        END;
    END;
END;
/
~~~

When a child block ends, its local variables go out of scope. Variables in parent blocks continue to exist until their respective parent blocks end.

## 8. Name Shadowing

**Shadowing** occurs when a declaration in an inner scope has the same name as a declaration in an outer scope. Inside the child block, an unqualified name resolves to the nearest declaration in the current scope; the outer declaration is shadowed at that point.

Example:

~~~sql
SET SERVEROUTPUT ON;

DECLARE
    l_status VARCHAR2(20) := 'OUTER';
BEGIN
    DBMS_OUTPUT.PUT_LINE(l_status); -- OUTER

    DECLARE
        l_status VARCHAR2(20) := 'INNER';
    BEGIN
        DBMS_OUTPUT.PUT_LINE(l_status); -- INNER
    END;

    DBMS_OUTPUT.PUT_LINE(l_status); -- OUTER
END;
/
~~~

The inner declaration of `l_status` does not overwrite the value of the outer `l_status`. It creates a separate variable with its own scope, shadowing the outer name only within the child block.

### Shadowing variables and constants

The nearest-name rule also applies if the outer name is a constant:

~~~sql
DECLARE
    c_limit CONSTANT PLS_INTEGER := 10;
BEGIN
    DECLARE
        c_limit CONSTANT PLS_INTEGER := 3;
    BEGIN
        DBMS_OUTPUT.PUT_LINE(c_limit); -- 3
    END;

    DBMS_OUTPUT.PUT_LINE(c_limit); -- 10
END;
/
~~~

Do not overuse the same name across multiple levels. Although valid, shadowing makes it difficult for readers to tell which value an expression uses, especially in long blocks or blocks containing many SQL statements.

### An inner-block name can shadow multiple outer levels

~~~sql
DECLARE
    l_code NUMBER := 1;
BEGIN
    DECLARE
        l_code NUMBER := 2;
    BEGIN
        DECLARE
            l_code NUMBER := 3;
        BEGIN
            DBMS_OUTPUT.PUT_LINE(l_code); -- 3
        END;
    END;
END;
/
~~~

At the deepest position, the unqualified name `l_code` references the nearest variable (value 3). The two outer declarations still exist but are shadowed at that location.

## 9. Block Labels: Accessing Shadowed Variables

You can label a block using `<<label_name>>`. A label identifies the block and serves as a qualifier to reference an outer block's variable even when the inner block declares a variable with the same name.

~~~sql
SET SERVEROUTPUT ON;

<<outer_block>>
DECLARE
    l_count PLS_INTEGER := 100;
BEGIN
    <<inner_block>>
    DECLARE
        l_count PLS_INTEGER := 5;
    BEGIN
        DBMS_OUTPUT.PUT_LINE(l_count);              -- 5
        DBMS_OUTPUT.PUT_LINE(outer_block.l_count);  -- 100

        outer_block.l_count := outer_block.l_count + l_count;
    END inner_block;

    DBMS_OUTPUT.PUT_LINE(l_count); -- 105
END outer_block;
/
~~~

Inside `inner_block`:

- `l_count` references the variable declared in the inner block.
- `outer_block.l_count` references the variable in the block labeled `outer_block`.
- The final assignment updates the outer variable, adding the inner variable's value.

Block labels can also disambiguate names across multiple nesting levels. The label name must appear before the start of the block and can be repeated after `END` to clarify which block is ending.

### Labels do not create new variables

A label merely identifies a block; it does not create an independent namespace for all names, nor does it extend a variable's lifetime. Variables still belong to the block that declared them and cannot be accessed after that block ends.

### When should label qualifiers be used?

- When intentionally reusing the same name in an inner block and needing access to the outer variable.
- When multiple nested blocks share variable names and the source needs clarification.
- When needing to read/write a parent block's variable inside a complex expression.

If you have to use qualifiers constantly, consider renaming variables to reduce shadowing instead of relying on many labels.

## 10. Variable Names Matching Column Names in Embedded SQL

PL/SQL allows using variables inside SQL statements. However, names inside a SQL statement are also resolved according to SQL rules. If an unqualified name can be both a column name and a PL/SQL variable name, the statement becomes ambiguous to readers and may be resolved unexpectedly. Within SQL scope, a column name may resolve to the table's column rather than the variable the programmer intended to use.

Confusing example:

~~~sql
DECLARE
    employee_id NUMBER := 100;
    l_count     PLS_INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO l_count
    FROM employees
    WHERE employee_id = employee_id;
END;
/
~~~

Both sides of the condition can be interpreted as comparing the `EMPLOYEE_ID` column to itself, instead of comparing the column to the variable holding 100. This is a dangerous logic bug because the program can run without any syntax error.

### Name variables differently from column names

The most readable solution is using a consistent prefix for PL/SQL variables and aliases for tables:

~~~sql
DECLARE
    l_employee_id employees.employee_id%TYPE := 100;
    l_raise_pct   NUMBER := 0.05;
BEGIN
    UPDATE employees e
    SET salary = salary * (1 + l_raise_pct)
    WHERE e.employee_id = l_employee_id;
END;
/
~~~

Here:

- `e.employee_id` is the column of the `EMPLOYEES` table.
- `l_employee_id` is the PL/SQL variable.
- `l_raise_pct` is the PL/SQL variable used in the `SET` expression.

Do not name a variable identically to a column name without a clear reason.

### Use a block label to qualify a variable in SQL

When you need to keep a variable name identical to a column name, a block label can clarify the reference to the variable:

~~~sql
<<main_block>>
DECLARE
    employee_id employees.employee_id%TYPE := 100;
BEGIN
    UPDATE employees e
    SET salary = salary + 100
    WHERE e.employee_id = main_block.employee_id;
END main_block;
/
~~~

`main_block.employee_id` explicitly identifies the PL/SQL variable in the block labeled `main_block`; `e.employee_id` identifies the table column. This is valid, though variable prefixes remain easier to read and less error-prone.

### Always qualify columns in multi-table SQL statements

~~~sql
SELECT e.employee_id,
       e.department_id,
       d.department_name
FROM employees e
JOIN departments d
  ON d.department_id = e.department_id
WHERE e.employee_id = l_employee_id;
~~~

Aliases prevent ambiguity between columns with the same name across tables and clarify the data source. When PL/SQL variables are involved, use distinct variable names to avoid conflicts.

## 11. Scope of Parameters and Package Variables

### Procedure/function parameters

Formal parameters are declared in the header of a procedure/function and are scoped to that subprogram:

~~~sql
CREATE OR REPLACE PROCEDURE print_employee (
    p_employee_id IN employees.employee_id%TYPE
) AS
    l_employee_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO l_employee_name
    FROM employees
    WHERE employee_id = p_employee_id;

    DBMS_OUTPUT.PUT_LINE(l_employee_name);
END;
/
~~~

`p_employee_id` can be used in the declarative/executable sections per PL/SQL rules and is meaningful only during the invocation of `PRINT_EMPLOYEE`. Local variable `l_employee_name` exists only for that procedure call.

Parameter modes:

- `IN`: the caller passes a value in; the subprogram cannot reassign an `IN` parameter.
- `OUT`: the subprogram returns a value to the caller.
- `IN OUT`: receives an initial value and can return a modified value.

Parameters and local variables are scoped to the subprogram. If a child block declares a name matching a parameter, the inner declaration can shadow the parameter within that child block; avoid this using naming conventions.

### Package variables

A package can declare variables in the package specification or package body:

~~~sql
CREATE OR REPLACE PACKAGE app_context AS
    g_region VARCHAR2(10) := 'APAC';
    PROCEDURE set_region(p_region IN VARCHAR2);
END app_context;
/

CREATE OR REPLACE PACKAGE BODY app_context AS
    PROCEDURE set_region(p_region IN VARCHAR2) IS
    BEGIN
        g_region := p_region;
    END set_region;
END app_context;
/
~~~

Variables declared in the package specification are public and can be accessed via `app_context.g_region` from authorized programs. Variables declared only in the package body are private, used solely inside the package body.

Package variables are not global variables shared across all sessions. Normal package state exists per database session:

- Subsequent calls to the package within the same session see the modified value.
- Other sessions have their own copy of package state.
- When a session ends, that session's package state ceases to exist.
- A connection pool reusing sessions can preserve package state across requests unless the application explicitly resets or manages it.

Example:

~~~sql
BEGIN
    app_context.set_region('EMEA');
    DBMS_OUTPUT.PUT_LINE(app_context.g_region);
END;
/
~~~

The output in the current session is `EMEA`. Another session that has not called `SET_REGION` still has its own package state at the initial value.

### Package variables vs. package constants

You can declare constants in the package specification to share read-only values:

~~~sql
CREATE OR REPLACE PACKAGE app_constants AS
    c_max_attempts CONSTANT PLS_INTEGER := 5;
    c_default_region CONSTANT VARCHAR2(10) := 'APAC';
END app_constants;
/
~~~

Other programs can reference `app_constants.c_max_attempts` if they have `EXECUTE` privilege on the package. Package constants represent shared package-level configuration, whereas package variables are mutable and retain session-scoped state.

## 12. Variables in EXCEPTION Sections and Scope Errors

Variables declared in a block's `DECLARE` section can be used in both the `BEGIN` and `EXCEPTION` sections of that same block:

~~~sql
DECLARE
    l_employee_id NUMBER := 999999;
    l_name        VARCHAR2(100);
BEGIN
    SELECT last_name
    INTO l_name
    FROM employees
    WHERE employee_id = l_employee_id;

    DBMS_OUTPUT.PUT_LINE(l_name);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE(
            'No employee: ' || l_employee_id
        );
END;
/
~~~

If an exception is raised inside a child block and handled in the parent block, variables declared only in the child block are no longer in scope inside the parent block's handler:

~~~sql
DECLARE
    l_outer_id NUMBER := 100;
BEGIN
    DECLARE
        l_inner_message VARCHAR2(100) := 'inner work';
    BEGIN
        RAISE_APPLICATION_ERROR(-20001, 'Failure');
    END;
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(l_outer_id);
        -- l_inner_message is not in the outer block's scope.
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
END;
/
~~~

The outer block's handler can access outer block variables, but cannot reference local variables declared inside the child block.

### Duplicate declaration errors in the same scope

You cannot declare two variables with the same name in the same declarative region:

~~~sql
DECLARE
    l_value NUMBER := 1;
    -- l_value VARCHAR2(10) := 'A'; -- duplicate name declaration
BEGIN
    NULL;
END;
/
~~~

Shadowing only happens when a declaration is in a nested inner scope; two peer declarations in the same declarative section cause a duplicate identifier error.

## 13. Naming Conventions to Reduce Shadowing

Oracle does not enforce prefixes for variables, parameters, or constants. However, consistent conventions help distinguish PL/SQL names from SQL columns and make code faster to read.

A commonly used convention:

| Prefix | Meaning | Example |
| --- | --- | --- |
| `p_` | Procedure/function parameter | `p_employee_id` |
| `l_` | Local variable | `l_total_amount` |
| `c_` | Constant | `c_tax_rate` |
| `g_` | Package variable/state | `g_current_region` |
| `r_` | Record variable | `r_employee` |
| `t_` | User-defined type/subtype | `t_currency` |

Example:

~~~sql
CREATE OR REPLACE PROCEDURE apply_bonus (
    p_employee_id IN employees.employee_id%TYPE,
    p_bonus       IN NUMBER
) AS
    l_current_salary employees.salary%TYPE;
    l_new_salary     employees.salary%TYPE;
    c_max_bonus      CONSTANT NUMBER := 5000;
BEGIN
    SELECT e.salary
    INTO l_current_salary
    FROM employees e
    WHERE e.employee_id = p_employee_id;

    l_new_salary := l_current_salary + LEAST(p_bonus, c_max_bonus);

    UPDATE employees e
    SET e.salary = l_new_salary
    WHERE e.employee_id = p_employee_id;
END;
/
~~~

Variable names differ from column names, parameter names have their own prefix, and columns are qualified with aliases. This lowers the risk of mistaken name resolution.

### Principles to keep

- Do not use the same name for outer and inner variables without a clear reason.
- Name variables by data meaning, not merely by type like `number1` or `text2`.
- Use consistent prefixes for parameters, local variables, constants, and package state.
- Qualify columns with table aliases in multi-table SQL.
- Do not use variable names identical to queried column names.
- When shadowing is unavoidable, use block labels to access outer variables and document the intent.
- Do not hold business state in package variables if other requests might reuse the same session without resetting state.

### Avoid names that clash with keywords or built-ins

Do not name variables `date`, `rownum`, `level`, `user`, `count`, or common function names. Even if some names work in certain contexts, they make SQL/PL/SQL statements hard to read and easy to confuse with pseudocolumns, functions, or keywords. Use meaningful names like `l_run_date`, `l_row_count`, `l_current_user`.

## 14. Comprehensive Practice Exercise

Perform this in a learning schema with `CREATE TABLE` privileges and an appropriate quota. DDL performs an implicit commit in Oracle; do not run table creation/deletion commands on production business schemas.

### Step 1: Create sample table

~~~sql
CREATE TABLE lab_employee (
    employee_id NUMBER PRIMARY KEY,
    employee_name VARCHAR2(80) NOT NULL,
    salary NUMBER(12,2) NOT NULL,
    department_id NUMBER
);

INSERT INTO lab_employee VALUES (1, 'Mai', 12000, 10);
INSERT INTO lab_employee VALUES (2, 'An', 15000, 10);
INSERT INTO lab_employee VALUES (3, 'Binh', 11000, 20);
COMMIT;
~~~

### Step 2: Declare variables with %TYPE and constants

~~~sql
SET SERVEROUTPUT ON;

DECLARE
    l_employee_id lab_employee.employee_id%TYPE := 1;
    l_salary      lab_employee.salary%TYPE;
    c_bonus       CONSTANT NUMBER(8,2) := 500;
BEGIN
    SELECT salary
    INTO l_salary
    FROM lab_employee
    WHERE employee_id = l_employee_id;

    DBMS_OUTPUT.PUT_LINE('Old salary: ' || l_salary);
    DBMS_OUTPUT.PUT_LINE('New salary: ' || (l_salary + c_bonus));
END;
/
~~~

Try altering the type/precision of the `SALARY` column in a separate lab table and observe how anchored declarations reduce the risk of type mismatch. Do not modify shared schemas.

### Step 3: Use %ROWTYPE

~~~sql
DECLARE
    r_employee lab_employee%ROWTYPE;
BEGIN
    SELECT *
    INTO r_employee
    FROM lab_employee
    WHERE employee_id = 2;

    DBMS_OUTPUT.PUT_LINE(
        r_employee.employee_name || ': ' || r_employee.salary
    );
END;
/
~~~

### Step 4: Observe shadowing

~~~sql
DECLARE
    l_value NUMBER := 100;
BEGIN
    DBMS_OUTPUT.PUT_LINE('Outer = ' || l_value);

    DECLARE
        l_value NUMBER := 5;
    BEGIN
        DBMS_OUTPUT.PUT_LINE('Inner = ' || l_value);
    END;

    DBMS_OUTPUT.PUT_LINE('Outer again = ' || l_value);
END;
/
~~~

Explain why the outer value remains 100 after the child block ends.

### Step 5: Use a block label

~~~sql
<<main_block>>
DECLARE
    l_total NUMBER := 100;
BEGIN
    DECLARE
        l_total NUMBER := 5;
    BEGIN
        DBMS_OUTPUT.PUT_LINE(l_total);
        DBMS_OUTPUT.PUT_LINE(main_block.l_total);
        main_block.l_total := main_block.l_total + l_total;
    END;

    DBMS_OUTPUT.PUT_LINE(l_total);
END main_block;
/
~~~

The output prints the inner variable (5), the outer variable (100), and then the outer variable after it is updated (105).

### Step 6: Use a block label to avoid column name collision

~~~sql
<<update_block>>
DECLARE
    employee_id lab_employee.employee_id%TYPE := 3;
BEGIN
    UPDATE lab_employee e
    SET e.salary = e.salary + 100
    WHERE e.employee_id = update_block.employee_id;
END update_block;
/

ROLLBACK;
~~~

The block label distinguishes the PL/SQL variable from the `EMPLOYEE_ID` column. `ROLLBACK` cancels the lab change after observation.

### Step 7: Handle exceptions in a block

~~~sql
DECLARE
    l_employee_id NUMBER := -1;
    l_name lab_employee.employee_name%TYPE;
BEGIN
    SELECT employee_name
    INTO l_name
    FROM lab_employee
    WHERE employee_id = l_employee_id;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE(
            'No employee for id ' || l_employee_id
        );
END;
/
~~~

Variables declared in the outer block can still be used inside that same block's exception handler.

### Step 8: Clean up data

~~~sql
DROP TABLE lab_employee PURGE;
~~~

Run only after finishing the exercise when you no longer need the data. `DROP TABLE` is DDL with an implicit commit; `PURGE` bypasses the Recycle Bin.

## 15. Common Errors and How to Handle Them

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Uninitialized variable returns NULL | Scalar variable has no initializer | Explicitly initialize or handle NULL before use. |
| Assigning NULL raises VALUE_ERROR | Variable is declared NOT NULL | Ensure a non-NULL value or remove NOT NULL if business rules allow. |
| Cannot reassign a constant | Declared with CONSTANT | Use a variable if the value needs to change. |
| Outer block cannot see inner variable | Variable belongs only to child block scope | Move declaration to parent block or return value via OUT/record as appropriate. |
| Outer variable appears unchanged | Same-named variable in child block is shadowing it | Use a distinct name or block label qualifier. |
| SQL filters wrong number of rows | Variable name matches column name and resolves incorrectly | Use variable prefixes, qualify columns, and use block labels when needed. |
| %TYPE still accepts NULL even though column is NOT NULL | %TYPE does not inherit NOT NULL constraint | Declare variable NOT NULL and initialize explicitly if needed. |
| %ROWTYPE cannot receive a shortened SELECT column list | Select item count/order does not match record | Use SELECT * for the matching rowtype or declare an appropriate record. |
| Package variable retains value from previous request | Package state persists within the session | Reset state per request or avoid package globals for request data. |
| Child block variable unusable in outer exception | Variable has left lexical scope | Store needed info in a parent block variable or handle the exception in the child block. |

## 16. Self-Check Questions

1. **Where are variables declared in a PL/SQL block?** In the `DECLARE` section, before `BEGIN`.
2. **What value does an uninitialized scalar variable hold?** `NULL`.
3. **What is the assignment operator in PL/SQL?** Colon-equals, i.e. `:=`.
4. **What does CONSTANT require?** It must have an initializing expression and cannot be reassigned.
5. **What does a NOT NULL variable require?** It must be initialized with a non-NULL value.
6. **What is %TYPE used for?** Declaring a variable anchored to the data type of a column or another variable.
7. **Does %TYPE inherit a column's NOT NULL constraint?** No; if you want the variable not to accept NULL, declare `NOT NULL` separately.
8. **What type does %ROWTYPE create?** A record with fields corresponding to the row structure of a table, view, or cursor.
9. **How does scope differ from lifetime?** Scope is where a name can be referenced; lifetime is how long the value exists.
10. **Can a child block see outer variables?** Yes, provided the name is not shadowed.
11. **Can an outer block see inner variables?** No.
12. **What is shadowing?** A declaration in a nested inner scope sharing the same name and hiding an outer declaration.
13. **How do you access an outer variable when it is shadowed?** Use a block label qualifier, such as `main_block.l_total`.
14. **Does a block label extend a variable's lifetime?** No; it only identifies the block.
15. **Are package variables shared across all sessions?** No; normal package state is private per session.
16. **Why should PL/SQL variables be prefixed?** To distinguish variables from SQL columns and reduce name resolution bugs.
17. **Can a child block's variable be used in the parent block's exception handler?** No, because it is no longer in the parent block's scope.
18. **What is the best way to avoid SQL name collisions?** Use variable names distinct from column names, clear prefixes, and alias-qualified columns.

Variables and constants in PL/SQL are governed by the lexical scope of the block or subprogram where they are declared. Child blocks can access outer variables, but declaring the same name in an inner block shadows the outer name; block labels allow explicitly referencing shadowed variables. Use `%TYPE`/`%ROWTYPE` to stay aligned with data structures, `CONSTANT` to protect immutable values, consistent prefixes to prevent collisions with SQL columns, and remember that package variables maintain per-session state. These practices make programs easier to read, less prone to name-resolution errors, and easier to maintain.
