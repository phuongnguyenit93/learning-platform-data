# CREATE PROCEDURE, CREATE FUNCTION, and Choosing Program Units in Oracle

## 1. From Anonymous Blocks to Named PL/SQL Programs

An anonymous block allows running a group of PL/SQL statements without creating an object stored in a schema. This is convenient when testing or performing a one-off task. When logic needs to be called repeatedly from multiple places, has a clear parameter interface, and requires execution privilege management, Oracle provides **named PL/SQL units** such as procedures, functions, and packages.

The two commonly used standalone program units are:

- **Procedure:** performs an action or a workflow. It can accept input parameters and return data via `OUT` or `IN OUT` parameters; a procedure does not have a `RETURN` expression carrying a result value like a function.
- **Function:** computes or retrieves a value and returns it using `RETURN`. A function can be called in PL/SQL expressions; if it satisfies SQL rules, a function can also be called directly inside a SQL statement.

Procedure example:

```sql
CREATE OR REPLACE PROCEDURE say_hello (
    p_name IN VARCHAR2
) AS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello, ' || p_name);
END say_hello;
/
```

Function example:

```sql
CREATE OR REPLACE FUNCTION calculate_tax (
    p_amount IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN p_amount * 0.10;
END calculate_tax;
/
```

A procedure is called to perform an action; a function is called when a return value is needed. This is the starting principle for choosing a program unit. In practice, packages are often used to group related procedures/functions into a unified schema API.

This lesson belongs to the **Procedures and Packages** chapter, covering `CREATE PROCEDURE`, `CREATE FUNCTION` syntax, parameters, return values, invocation, privileges, transactions, compilation, and schema dependencies; it also compares anonymous blocks, procedures, functions, packages, and triggers to choose the right program unit for each requirement.

## 2. What Are Stored Procedures and Stored Functions?

Procedures and functions are PL/SQL programs stored in Oracle Database as schema objects. After being created and compiled successfully, these programs can be called from:

- Anonymous PL/SQL blocks.
- Other procedures or functions.
- Packages.
- Triggers.
- Client applications such as Java/JDBC.
- SQL statements for functions that meet SQL invocation requirements.

### 2.1. Why Store Logic in the Database?

Stored PL/SQL can be useful when:

- Multiple applications share the same business rules.
- Multiple DML statements need to be encapsulated into a single operation with a stable interface.
- Reducing round trips between the application and the database is needed.
- You want to grant `EXECUTE` privilege on the program rather than granting direct DML privileges on every table to application users.
- Logic needs to reside close to the data to handle tightly coordinated operations.

However, not all logic should be moved into the database. UI logic, external service calls, long-running workflow orchestration, or processing not tightly coupled to data may be better suited to the application tier. Consider testability, deployment, versioning, and Oracle dependencies.

### 2.2. Procedures/Functions as Schema Objects

When running:

```sql
CREATE OR REPLACE PROCEDURE refresh_customer_status AS
BEGIN
    NULL;
END refresh_customer_status;
/
```

Oracle creates or replaces the `REFRESH_CUSTOMER_STATUS` procedure in the current schema. The procedure has its own name, metadata, compilation status, and access privileges.

An anonymous block does not have a similar standalone object that other users can call by name. If a block needs to be reused, its logic can be converted into a procedure/function.

## 3. CREATE PROCEDURE

### 3.1. General Syntax

```sql
CREATE [OR REPLACE] PROCEDURE procedure_name
    [(parameter [IN | OUT | IN OUT] datatype [DEFAULT expression], ...)]
    [AUTHID DEFINER | CURRENT_USER]
AS
    -- declarations
BEGIN
    -- executable statements
[EXCEPTION
    -- exception handlers
]
END [procedure_name];
/
```

Components:

- `CREATE PROCEDURE`: creates a stored procedure.
- `OR REPLACE`: replaces the existing definition with the new definition if an object with the same name already exists and the user has the appropriate privileges.
- `procedure_name`: the name of the procedure in the schema.
- Parameter list: optional list of parameters.
- `AUTHID`: chooses execution privileges according to definer or invoker.
- `AS` or `IS`: begins the declaration section and procedure body.
- `BEGIN ... END`: mandatory executable section.
- `EXCEPTION`: optional error-handling section.

`AS` and `IS` can be used interchangeably in standard procedure/function definitions.

### 3.2. Procedure Without Parameters

```sql
CREATE OR REPLACE PROCEDURE show_server_time AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS.FF TZH:TZM')
    );
END show_server_time;
/
```

Calling the procedure:

```sql
BEGIN
    show_server_time;
END;
/
```

In PL/SQL, a procedure can be called by name and parameter list. Empty parentheses are not required for a procedure without parameters.

### 3.3. Procedure with Input Parameters

```sql
CREATE OR REPLACE PROCEDURE print_employee (
    p_employee_id IN NUMBER
) AS
    v_name VARCHAR2(100);
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = p_employee_id;

    DBMS_OUTPUT.PUT_LINE(v_name);
END print_employee;
/
```

`p_employee_id` is the data passed in by the caller. The `IN` keyword is the default mode, but it should be written explicitly to keep the interface readable.

Calling it:

```sql
BEGIN
    print_employee(100);
END;
/
```

### 3.4. Procedure Using %TYPE for Parameters

```sql
CREATE OR REPLACE PROCEDURE print_employee (
    p_employee_id IN employees.employee_id%TYPE
) AS
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = p_employee_id;

    DBMS_OUTPUT.PUT_LINE(v_name);
END print_employee;
/
```

`%TYPE` keeps parameters and variables aligned with column types. When table structure changes, the stored unit may need to be recompiled; Oracle tracks dependencies and may mark the unit `INVALID` if the change affects the program.

## 4. IN, OUT, and IN OUT Parameters

PL/SQL supports three parameter modes.

| Mode | Data Direction | Meaning |
|---|---|---|
| `IN` | Caller → program | Input; the program reads the value |
| `OUT` | Program → caller | Output; the program assigns a result to the parameter |
| `IN OUT` | Caller ↔ program | Receives an initial value, can modify it, and returns it |

### 4.1. IN Parameter

```sql
CREATE OR REPLACE PROCEDURE calculate_discount (
    p_amount IN NUMBER,
    p_rate   IN NUMBER
) AS
    v_discount NUMBER;
BEGIN
    v_discount := p_amount * p_rate;
    DBMS_OUTPUT.PUT_LINE('Discount=' || v_discount);
END calculate_discount;
/
```

Inside a procedure, an IN parameter cannot be reassigned like a regular output variable. If a computed value needs to be returned to the caller, use OUT or a function.

### 4.2. OUT Parameter

```sql
CREATE OR REPLACE PROCEDURE get_employee_salary (
    p_employee_id IN employees.employee_id%TYPE,
    p_salary      OUT employees.salary%TYPE
) AS
BEGIN
    SELECT salary
    INTO p_salary
    FROM employees
    WHERE employee_id = p_employee_id;
END get_employee_salary;
/
```

The caller receives the value through a variable:

```sql
DECLARE
    v_salary employees.salary%TYPE;
BEGIN
    get_employee_salary(100, v_salary);
    DBMS_OUTPUT.PUT_LINE('Salary=' || v_salary);
END;
/
```

An OUT parameter is suitable when a procedure needs to return multiple results or express status through multiple parameters.

If the procedure raises an exception before assigning the OUT parameter, the caller should not rely on that value as a valid result. Clearly define the error contract and only read OUT values when the call succeeds.

### 4.3. IN OUT Parameter

```sql
CREATE OR REPLACE PROCEDURE add_bonus (
    p_salary IN OUT NUMBER,
    p_bonus  IN NUMBER
) AS
BEGIN
    p_salary := p_salary + p_bonus;
END add_bonus;
/
```

Calling it:

```sql
DECLARE
    v_salary NUMBER := 30000;
BEGIN
    add_bonus(v_salary, 2500);
    DBMS_OUTPUT.PUT_LINE(v_salary); -- 32500
END;
/
```

`IN OUT` receives an initial value and then returns the modified value. Use this mode when the caller genuinely needs a variable updated in place; if only returning a new result, OUT or a function is usually easier to understand.

### 4.4. Parameters with Default Values

An IN parameter can declare a default:

```sql
CREATE OR REPLACE PROCEDURE print_message (
    p_message IN VARCHAR2,
    p_prefix  IN VARCHAR2 DEFAULT 'INFO'
) AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        '[' || p_prefix || '] ' || p_message
    );
END print_message;
/
```

Calling with the default value:

```sql
BEGIN
    print_message('Database is ready');
END;
/
```

Calling and passing a different value:

```sql
BEGIN
    print_message('Disk usage is high', 'WARNING');
END;
/
```

When using positional notation, you cannot skip a parameter in the middle and pass a later parameter. Named notation allows omitting parameters that have defaults.

### 4.5. Positional Notation

```sql
BEGIN
    print_message('Job completed', 'SUCCESS');
END;
/
```

Values are assigned in the order the parameters are declared.

### 4.6. Named Notation

```sql
BEGIN
    print_message(
        p_prefix  => 'SUCCESS',
        p_message => 'Job completed'
    );
END;
/
```

Named notation makes calls easier to read and independent of parameter order. It is especially useful when a procedure has many parameters or many parameters with defaults.

### 4.7. Mixing Positional and Named Notation

You can pass some leading parameters positionally and continue with named notation:

```sql
BEGIN
    print_message(
        'Job completed',
        p_prefix => 'SUCCESS'
    );
END;
/
```

Do not place positional parameters after starting named notation in the same call.

### 4.8. Parameter Data Types

In formal parameter declarations, data types are normally written without length or precision constraints:

```sql
CREATE OR REPLACE PROCEDURE set_customer_name (
    p_customer_id IN customers.customer_id%TYPE,
    p_name        IN VARCHAR2
) AS
BEGIN
    UPDATE customers
    SET customer_name = p_name
    WHERE customer_id = p_customer_id;
END set_customer_name;
/
```

If you need to restrict length or format, define it via column type, constraints, or validation inside the program body. Do not declare `VARCHAR2(100)` directly as a formal parameter.

## 5. CREATE FUNCTION

### 5.1. General Syntax

```sql
CREATE [OR REPLACE] FUNCTION function_name
    [(parameter [IN | OUT | IN OUT] datatype [DEFAULT expression], ...)]
    RETURN return_datatype
    [AUTHID DEFINER | CURRENT_USER]
AS
    -- declarations
BEGIN
    -- executable statements
    RETURN expression;
[EXCEPTION
    -- exception handlers
]
END [function_name];
/
```

A function must have a `RETURN return_datatype` clause in its header and must return a compatible value via a `RETURN expression` statement.

### 5.2. Simple Function

```sql
CREATE OR REPLACE FUNCTION calculate_tax (
    p_amount IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN p_amount * 0.10;
END calculate_tax;
/
```

Calling in PL/SQL:

```sql
DECLARE
    v_tax NUMBER;
BEGIN
    v_tax := calculate_tax(1000);
    DBMS_OUTPUT.PUT_LINE('Tax=' || v_tax);
END;
/
```

The function returns a NUMBER value. The caller can use that value in assignments, expressions, conditions, or pass it as an argument to another call.

### 5.3. Function with Local Declarations

```sql
CREATE OR REPLACE FUNCTION calculate_net_amount (
    p_gross_amount IN NUMBER,
    p_tax_rate     IN NUMBER
) RETURN NUMBER
AS
    v_tax NUMBER;
    v_net NUMBER;
BEGIN
    v_tax := p_gross_amount * p_tax_rate;
    v_net := p_gross_amount - v_tax;

    RETURN v_net;
END calculate_net_amount;
/
```

Local variables are declared between `AS` and `BEGIN`. A function can have an `EXCEPTION` section just like a procedure.

### 5.4. Every Normal Execution Path Must Return a Value

```sql
CREATE OR REPLACE FUNCTION classify_amount (
    p_amount IN NUMBER
) RETURN VARCHAR2
AS
BEGIN
    IF p_amount < 0 THEN
        RETURN 'INVALID';
    ELSIF p_amount = 0 THEN
        RETURN 'ZERO';
    ELSE
        RETURN 'POSITIVE';
    END IF;
END classify_amount;
/
```

Every normal branch has a RETURN. If a function reaches the end of its body without returning a value, Oracle raises a runtime error indicating that the function finished without returning a value, typically `ORA-06503`.

### 5.5. Differences in RETURN Between Procedures and Functions

In a function:

```sql
RETURN expression;
```

returns a value and exits the function.

In a procedure, you can use:

```sql
RETURN;
```

to exit the procedure early, without a return value in the RETURN statement. A procedure returns data through OUT/IN OUT parameters or other result mechanisms.

### 5.6. A Function Can Raise Exceptions

```sql
CREATE OR REPLACE FUNCTION get_employee_salary (
    p_employee_id IN employees.employee_id%TYPE
) RETURN NUMBER
AS
    v_salary employees.salary%TYPE;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = p_employee_id;

    RETURN v_salary;
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        RAISE_APPLICATION_ERROR(
            -20010,
            'Employee does not exist'
        );
END get_employee_salary;
/
```

If no employee is found, the function converts `NO_DATA_FOUND` into a business error with code `-20010`. If not caught, the original exception propagates to the caller.

Do not return 0 or NULL for every error if the caller needs to distinguish between "employee does not exist", "salary not set", and "query error".

## 6. Core Differences Between Procedures and Functions

| Criterion | Procedure | Function |
|---|---|---|
| Primary purpose | Perform an action/workflow | Compute or return a value |
| RETURN value | No return value via RETURN; can use `RETURN;` to exit | Must declare a return type and return a value |
| Result | OUT/IN OUT, DML, status, or cursor | One value of the declared type |
| Calling in PL/SQL | Called as a statement | Called inside an expression or appropriate statement |
| Calling in SQL | Cannot call a procedure directly in SELECT | Can call a function if it meets SQL invocation rules |
| OUT parameters | Suitable | Allowed in PL/SQL, but SQL-called functions cannot use OUT/IN OUT |
| COMMIT/ROLLBACK | Can be written in a procedure, but requires transaction boundary design | Cannot perform transaction control in a function called from SQL; generally keep functions computational without side effects |
| Examples | Create order, update status, pass data via OUT | Calculate tax, normalize value, return total amount |

Rule of thumb: if the program name represents an action such as `CREATE_ORDER`, `CLOSE_ACCOUNT`, `PROCESS_PAYMENT`, start with a procedure. If the name represents a value such as `CALCULATE_TAX`, `GET_ORDER_TOTAL`, start with a function.

## 7. Complete Example: Procedure to Create an Order

### 7.1. Creating the Demo Table

The example uses an identity column, which requires Oracle Database 12c Release 1 or later:

```sql
CREATE TABLE demo_orders (
    order_id NUMBER GENERATED BY DEFAULT AS IDENTITY
        CONSTRAINT pk_demo_orders PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12, 2) NOT NULL,
    status VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT ck_demo_orders_amount CHECK (amount >= 0)
);
```

### 7.2. Creating the Procedure

```sql
CREATE OR REPLACE PROCEDURE create_demo_order (
    p_customer_id IN demo_orders.customer_id%TYPE,
    p_amount      IN demo_orders.amount%TYPE,
    p_order_id    OUT demo_orders.order_id%TYPE
) AS
BEGIN
    IF p_amount < 0 THEN
        RAISE_APPLICATION_ERROR(
            -20020,
            'Order amount cannot be negative'
        );
    END IF;

    INSERT INTO demo_orders (
        customer_id,
        amount,
        status
    )
    VALUES (
        p_customer_id,
        p_amount,
        'NEW'
    )
    RETURNING order_id INTO p_order_id;
END create_demo_order;
/
```

The procedure validates the input data, INSERTs a row, and returns the new key via an OUT parameter. The procedure does not COMMIT; the transaction remains owned by the caller.

### 7.3. Calling the Procedure in an Anonymous Block

```sql
DECLARE
    v_order_id demo_orders.order_id%TYPE;
BEGIN
    create_demo_order(
        p_customer_id => 501,
        p_amount      => 250000,
        p_order_id    => v_order_id
    );

    DBMS_OUTPUT.PUT_LINE('Created order=' || v_order_id);
END;
/
```

Afterward, the caller decides:

```sql
COMMIT;
```

Or cancels the operation:

```sql
ROLLBACK;
```

Not committing automatically inside the procedure allows the caller to combine order creation with other business operations in the same transaction.

## 8. Complete Example: Function to Calculate Order Total

A function that only reads data and returns a value:

```sql
CREATE OR REPLACE FUNCTION get_customer_order_total (
    p_customer_id IN demo_orders.customer_id%TYPE
) RETURN NUMBER
AS
    v_total NUMBER;
BEGIN
    SELECT NVL(SUM(amount), 0)
    INTO v_total
    FROM demo_orders
    WHERE customer_id = p_customer_id
      AND status <> 'CANCELLED';

    RETURN v_total;
END get_customer_order_total;
/
```

`SUM` without GROUP BY returns one aggregate row even if there are no matching orders; `NVL` converts NULL to 0. Therefore, the function returns 0 if the customer has no qualifying orders.

### 8.1. Calling the Function in PL/SQL

```sql
DECLARE
    v_total NUMBER;
BEGIN
    v_total := get_customer_order_total(501);
    DBMS_OUTPUT.PUT_LINE('Total=' || v_total);
END;
/
```

### 8.2. Calling the Function in SQL

```sql
SELECT get_customer_order_total(501) AS order_total
FROM dual;
```

This is a key benefit of a function: if it meets SQL invocation rules, it can be used in SELECT, WHERE, ORDER BY, or appropriate SQL expressions.

## 9. Rules When Calling a Function from SQL

Not every PL/SQL function can be called from SQL. The function must obey restrictions on parameters, data types, and side effects.

### 9.1. Use IN Parameters for Functions Called from SQL

A function called directly from SQL must not declare `OUT` or `IN OUT` parameters. Parameters used in SQL invocation must be compatible with the data types supported by SQL in that database version.

Suitable example:

```sql
CREATE OR REPLACE FUNCTION add_tax (
    p_amount IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN p_amount * 1.10;
END add_tax;
/

SELECT add_tax(1000)
FROM dual;
```

The function uses an IN parameter and returns a scalar NUMBER.

### 9.2. Functions Called from SQL Should Avoid DML and Side Effects

A function called inside a SQL statement should be designed as a computation/data read without side effects. If a function attempts to perform DML in a SQL query context, Oracle can raise an error such as `ORA-14551: cannot perform a DML operation inside a query`.

A function called from SQL also cannot perform transaction control such as COMMIT or ROLLBACK. Do not use a function in SELECT to silently update tables, write logs via DML, or control workflows.

If data needs to be modified, use a procedure or explicit DML statements.

### 9.3. Do Not Rely on the Number of Times a Function Is Called

When a function appears in SQL, the optimizer may transform the execution plan. Do not assume the function is called exactly once per row, or called in the row order you see in the output.

Functions used in SQL must avoid side effects and should not depend on invocation order or call count. If you need to control execution order, write the logic explicitly in PL/SQL or an appropriate SQL structure.

### 9.4. Functions Can Read Tables

A function that reads a table and returns a value can be used in SQL if it meets the other conditions:

```sql
CREATE OR REPLACE FUNCTION get_customer_level (
    p_customer_id IN customers.customer_id%TYPE
) RETURN VARCHAR2
AS
    v_level customers.customer_level%TYPE;
BEGIN
    SELECT customer_level
    INTO v_level
    FROM customers
    WHERE customer_id = p_customer_id;

    RETURN v_level;
END get_customer_level;
/
```

If no customer is found, the function raises `NO_DATA_FOUND` unless handled. When the function is called from a large query, an exception can cause the entire statement to fail. Consider cardinality and the cost of calling the function across many rows.

### 9.5. Avoid Calling PL/SQL Functions Row-by-Row When Set-Based SQL Can Be Used

Example:

```sql
SELECT order_id,
       get_customer_level(customer_id)
FROM orders;
```

If the function executes a separate query for each order, a large SELECT can result in a huge number of PL/SQL and SQL executions. If the logic can be written as a JOIN or pure SQL expression, the set-based approach is usually preferred so the optimizer has more information to optimize.

Not every function call is slow; measure the workload. However, you should recognize the risk of context switching and repeated lookups when a function is called across many rows.

## 10. Transactions in Procedures and Functions

### 10.1. Procedures Usually Let the Caller Manage Transactions

A procedure performing DML:

```sql
CREATE OR REPLACE PROCEDURE update_demo_order_status (
    p_order_id IN demo_orders.order_id%TYPE,
    p_status   IN demo_orders.status%TYPE
) AS
BEGIN
    UPDATE demo_orders
    SET status = p_status
    WHERE order_id = p_order_id;

    IF SQL%ROWCOUNT = 0 THEN
        RAISE_APPLICATION_ERROR(
            -20021,
            'Order does not exist'
        );
    END IF;
END update_demo_order_status;
/
```

The procedure does not COMMIT. The caller can call other procedures and then COMMIT everything as a single business transaction, or ROLLBACK if any step fails.

### 10.2. Why Hidden COMMITs Inside a Procedure Can Be Dangerous

Suppose an application needs to:

1. Create an order.
2. Deduct inventory.
3. Record payment history.

If the order creation procedure commits in step 1, the caller cannot ROLLBACK the entire order when inventory deduction fails. The transaction boundary is unintentionally fragmented.

Only let a procedure COMMIT itself when the business contract explicitly specifies that the procedure owns the transaction and callers understand the impact.

### 10.3. Functions Used to Compute Values

A regular function should perform no DML and no transaction control:

```sql
CREATE OR REPLACE FUNCTION calculate_line_total (
    p_quantity IN NUMBER,
    p_unit_price IN NUMBER
) RETURN NUMBER
AS
BEGIN
    RETURN p_quantity * p_unit_price;
END calculate_line_total;
/
```

Such a function can be used in both PL/SQL and SQL without side effects.

### 10.4. Functions with DML in a PL/SQL Context

A PL/SQL function can contain DML in certain PL/SQL-only invocation scenarios, but that introduces side effects and restricts its ability to be called from SQL. If the goal is to modify data, a procedure expresses the intent more clearly.

A function containing DML when called from a SELECT statement can encounter `ORA-14551`. Autonomous transactions have their own rules and are not a general way to turn a function with side effects into good design. Do not use autonomous transactions merely to bypass DML restrictions in SQL.

## 11. AUTHID DEFINER and AUTHID CURRENT_USER

Stored procedures/functions can execute with the privileges of the program owner or the privileges of the caller.

### 11.1. Definer's Rights

By default, a stored PL/SQL unit uses **definer's rights** (`AUTHID DEFINER`). The program executes in the security context of the schema owning the unit, following Oracle privilege rules.

Example:

```sql
CREATE OR REPLACE PROCEDURE app_owner.close_demo_order (
    p_order_id IN NUMBER
) AUTHID DEFINER
AS
BEGIN
    UPDATE app_owner.demo_orders
    SET status = 'CLOSED'
    WHERE order_id = p_order_id;
END close_demo_order;
/
```

The application can be granted `EXECUTE` on the procedure without being granted direct UPDATE privileges on the table, provided the program and privileges are designed properly.

### 11.2. Invoker's Rights

Declare:

```sql
AUTHID CURRENT_USER
```

to use invoker's rights. Access privileges are evaluated according to the current user/invoker under Oracle rules. This is useful when a program needs to operate in the caller's security context.

Example:

```sql
CREATE OR REPLACE PROCEDURE show_current_schema
AUTHID CURRENT_USER
AS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'CURRENT_USER=' || SYS_CONTEXT('USERENV', 'CURRENT_USER')
    );
END show_current_schema;
/
```

### 11.3. Choosing AUTHID Deliberately

| Requirement | Direction to Consider |
|---|---|
| Database API where the owning schema controls table access | `AUTHID DEFINER` |
| Logic that needs to enforce the caller's privileges | `AUTHID CURRENT_USER` |
| Application only allowed to invoke specific encapsulated operations | Definer's rights with minimal GRANT EXECUTE |
| Program accessing objects using the caller's privileges | Invoker's rights, after careful security review |

Do not use `AUTHID CURRENT_USER` simply assuming it is safer. You need to understand privileges, roles, schema resolution, and program dependencies in both models.

### 11.4. Direct Privileges When Compiling Stored PL/SQL

When compiling stored PL/SQL, privileges on referenced dependent objects usually need to be granted directly to the schema owning the program; privileges granted only through roles may not be sufficient to compile static references. Grant least privilege and check compilation errors if a program references tables/schemas elsewhere.

## 12. Calling Procedures and Functions

### 12.1. Calling a Procedure in an Anonymous Block

```sql
BEGIN
    update_demo_order_status(
        p_order_id => 1001,
        p_status   => 'PAID'
    );
END;
/
```

A procedure is called as a statement, not placed directly inside a SELECT expression.

### 12.2. Calling a Function in a PL/SQL Expression

```sql
DECLARE
    v_tax NUMBER;
BEGIN
    v_tax := calculate_tax(5000);

    IF v_tax > 0 THEN
        DBMS_OUTPUT.PUT_LINE('Tax=' || v_tax);
    END IF;
END;
/
```

### 12.3. Calling a Function in SQL

```sql
SELECT calculate_tax(5000) AS tax_amount
FROM dual;
```

### 12.4. Calling a Procedure Using EXEC in SQL*Plus/SQLcl

```sql
EXEC update_demo_order_status(1001, 'PAID');
```

`EXEC` is a SQL*Plus/SQLcl client utility command, not standard SQL syntax sent directly from JDBC. When writing a script with multiple commands, you can use an anonymous block.

### 12.5. Calling a Procedure with an OUT Parameter from SQL*Plus

```sql
VARIABLE v_order_id NUMBER;

BEGIN
    create_demo_order(501, 250000, :v_order_id);
END;
/

PRINT v_order_id;
```

`VARIABLE` and `PRINT` are SQL*Plus/SQLcl client commands. The bind variable `:v_order_id` is passed into the OUT parameter.

## 13. Choosing the Right Program Unit

Not all logic needs a standalone procedure or function. Choose the construct based on reuse scope, purpose, and invocation style.

| Unit | Use When | Examples |
|---|---|---|
| Anonymous block | One-off tasks, experiments, deployment scripts, or short glue code | Running a small batch, calling a procedure |
| Procedure | Performing an action, modifying data, or orchestrating multiple steps in the database | `CREATE_ORDER`, `CLOSE_ACCOUNT` |
| Function | Returning a computed/looked-up value, usable in expressions | `CALCULATE_TAX`, `GET_ORDER_TOTAL` |
| Package | Grouping related APIs, needing public/private members, state, or overloading | `ORDER_API`, `PAYMENT_API` |
| Trigger | Automatically reacting to DML/DDL/database events | Auditing, special event checks |
| Object type method | Behavior attached to an object type | Method of an object-relational type |

### 13.1. When to Use an Anonymous Block?

Use an anonymous block when:

- It only needs to run once from a SQL client.
- Testing logic before creating a stored unit.
- Calling multiple procedures in a script.
- Needing a short piece of glue code with no need to call it again by name.

If the logic becomes a reusable API, move it into a procedure/function or package.

### 13.2. When to Use a Procedure?

Use a procedure when the goal is an action:

- INSERTing a business record.
- Updating status.
- Executing a workflow with multiple DML steps.
- Returning multiple results via OUT parameters.
- Opening and returning a REF CURSOR when the API needs a result set.

A procedure does not return a value inside a SQL expression like a function.

### 13.3. When to Use a Function?

Use a function when the caller needs a value:

- Calculating tax, discount, or points.
- Normalizing a code.
- Looking up a single attribute.
- Returning a sum, count, or classification.
- Using inside SQL expressions if the function meets the restrictions.

A function should have predictable behavior. If a function is only called from PL/SQL and has side effects, consider whether a procedure expresses the intent more clearly.

### 13.4. When to Use a Package?

When multiple programs serve the same business domain, a package groups them into one interface:

```sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE create_order (
        p_customer_id IN NUMBER,
        p_amount IN NUMBER,
        p_order_id OUT NUMBER
    );

    FUNCTION get_order_total (
        p_customer_id IN NUMBER
    ) RETURN NUMBER;
END order_api;
/
```

The package body contains the implementation:

```sql
CREATE OR REPLACE PACKAGE BODY order_api AS
    PROCEDURE create_order (
        p_customer_id IN NUMBER,
        p_amount IN NUMBER,
        p_order_id OUT NUMBER
    ) AS
    BEGIN
        INSERT INTO demo_orders (customer_id, amount)
        VALUES (p_customer_id, p_amount)
        RETURNING order_id INTO p_order_id;
    END create_order;

    FUNCTION get_order_total (
        p_customer_id IN NUMBER
    ) RETURN NUMBER AS
        v_total NUMBER;
    BEGIN
        SELECT NVL(SUM(amount), 0)
        INTO v_total
        FROM demo_orders
        WHERE customer_id = p_customer_id;

        RETURN v_total;
    END get_order_total;
END order_api;
/
```

The package specification is the public API; the package body contains the implementation and can hold private subprograms/variables not exposed in the spec.

Packages also support overloading within the same package, allowing the same name to be used for versions with different signatures according to Oracle rules.

### 13.5. When Not to Use a Trigger Instead of a Procedure?

A trigger runs automatically when an event occurs and is not invoked by callers like a normal API. Triggers are useful for automatic reactions and certain database-level safeguards, but they hide actions from the call flow and can create hard-to-trace side effects.

If the application needs to explicitly request "close order", use a procedure. Triggers should only supplement automatic behavior for a clear reason, not replace the entire business API.

## 14. Packages and Overloading

Standalone procedures/functions in the same schema do not support overloading the way packages do. If you need multiple versions with the same name and different parameter types, consider a package.

Example:

```sql
CREATE OR REPLACE PACKAGE format_api AS
    FUNCTION format_value(p_value IN NUMBER) RETURN VARCHAR2;
    FUNCTION format_value(p_value IN DATE) RETURN VARCHAR2;
END format_api;
/

CREATE OR REPLACE PACKAGE BODY format_api AS
    FUNCTION format_value(p_value IN NUMBER) RETURN VARCHAR2 AS
    BEGIN
        RETURN TO_CHAR(p_value, 'FM999999990D00');
    END format_value;

    FUNCTION format_value(p_value IN DATE) RETURN VARCHAR2 AS
    BEGIN
        RETURN TO_CHAR(p_value, 'YYYY-MM-DD');
    END format_value;
END format_api;
/
```

Calling them:

```sql
SELECT format_api.format_value(1250.5)
FROM dual;

SELECT format_api.format_value(DATE '2026-11-14')
FROM dual;
```

Oracle selects the overload based on parameter types and signatures. Avoid designing overloads with ambiguous signatures or data types prone to confusing implicit conversions.

## 15. Compilation, Error Checking, and Dependency Management

### 15.1. CREATE OR REPLACE

```sql
CREATE OR REPLACE PROCEDURE hello_app AS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello');
END hello_app;
/
```

`OR REPLACE` updates the definition of an existing object with the same name. It is convenient when deploying new versions, though you still need to check compilation status and impact on dependent units.

### 15.2. Viewing Compilation Errors in SQL*Plus/SQLcl

```sql
SHOW ERRORS PROCEDURE hello_app;
```

For a function:

```sql
SHOW ERRORS FUNCTION calculate_tax;
```

`SHOW ERRORS` is a client command, not a SQL statement.

### 15.3. Viewing Errors via USER_ERRORS

```sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
WHERE name = 'HELLO_APP'
ORDER BY sequence;
```

### 15.4. Checking Object Status

```sql
SELECT object_name,
       object_type,
       status,
       last_ddl_time
FROM user_objects
WHERE object_name IN ('HELLO_APP', 'CALCULATE_TAX')
ORDER BY object_type, object_name;
```

`VALID` means the unit was compiled cleanly at the time of inspection. `INVALID` means you need to check errors or dependencies and recompile.

### 15.5. Recompiling

```sql
ALTER PROCEDURE hello_app COMPILE;
ALTER FUNCTION calculate_tax COMPILE;
```

Then check `USER_ERRORS` and `USER_OBJECTS`. Successful compilation does not prove runtime logic is correct; test with realistic data and scenarios.

### 15.6. Dependencies

A procedure/function can depend on:

- Tables and views.
- Types and collection types.
- Packages.
- Other functions/procedures.
- Sequences or other schema objects.

When a dependent object changes, the stored unit may become invalidated and require recompilation. Check `USER_DEPENDENCIES`:

```sql
SELECT name,
       type,
       referenced_owner,
       referenced_name,
       referenced_type
FROM user_dependencies
WHERE name = 'GET_EMPLOYEE_SALARY'
ORDER BY referenced_owner, referenced_name;
```

## 16. Privileges for Creating, Calling, and Granting EXECUTE

### 16.1. Privileges to Create Procedures/Functions

A user needs the privilege to create stored procedures/functions in their own schema, typically `CREATE PROCEDURE`. Creating them in another schema requires an appropriate privilege such as `CREATE ANY PROCEDURE`, which is powerful and should only be granted to administrative deployment accounts.

### 16.2. Granting Execution Privileges on Procedures/Functions

The owner can grant the EXECUTE privilege:

```sql
GRANT EXECUTE ON create_demo_order TO app_user;
GRANT EXECUTE ON get_customer_order_total TO app_user;
```

If the object is in another schema:

```sql
BEGIN
    app_owner.create_demo_order(
        p_customer_id => 501,
        p_amount => 100000,
        p_order_id => v_order_id
    );
END;
/
```

The caller needs the appropriate EXECUTE privilege and must reference the correct schema/object.

### 16.3. Definer's Rights Can Encapsulate DML Privileges

With definer's rights, the schema owning the procedure can be granted direct privileges on tables, while the application is only granted EXECUTE on the procedure. This is a way to build a controlled database API.

However, you must:

- Grant least privilege to the owner.
- Never concatenate untrusted input into dynamic SQL strings.
- Verify AUTHID and schema resolution.
- Avoid granting broad EXECUTE privileges to users who do not need them.

## 17. Dynamic SQL in Procedures/Functions

When table names, column names, or SQL statement structure are only known at runtime, PL/SQL can use dynamic SQL:

```sql
CREATE OR REPLACE PROCEDURE count_rows (
    p_table_name IN VARCHAR2,
    p_count OUT NUMBER
) AS
    v_sql VARCHAR2(1000);
BEGIN
    v_sql := 'SELECT COUNT(*) FROM ' || DBMS_ASSERT.SQL_OBJECT_NAME(p_table_name);

    EXECUTE IMMEDIATE v_sql INTO p_count;
END count_rows;
/
```

SQL object names cannot be bound with placeholders like data values. The example uses `DBMS_ASSERT.SQL_OBJECT_NAME` to validate the object name according to Oracle rules; in real applications, you should whitelist allowed table names.

For data values, use bind variables:

```sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM demo_orders WHERE customer_id = :id'
INTO p_count
USING p_customer_id;
```

Do not concatenate input values directly into SQL strings due to SQL injection risks and parsing issues.

Dynamic SQL is not a reason to turn every query into a string. Static SQL lets the compiler verify object names/types and track dependencies more effectively.

## 18. Calling Procedures/Functions from Java JDBC

### 18.1. Calling a Procedure Without OUT Parameters

```java
String sql = "{ call app_owner.update_demo_order_status(?, ?) }";

try (CallableStatement cs = connection.prepareCall(sql)) {
    cs.setLong(1, 1001L);
    cs.setString(2, "PAID");
    cs.execute();
}
```

`CallableStatement` is the standard JDBC API for calling stored procedures. The schema name can be specified explicitly to avoid resolving to a same-named object in another schema.

### 18.2. Calling a Procedure with OUT Parameters

```java
String sql = "{ call app_owner.create_demo_order(?, ?, ?) }";

try (CallableStatement cs = connection.prepareCall(sql)) {
    cs.setLong(1, 501L);
    cs.setBigDecimal(2, new BigDecimal("250000.00"));
    cs.registerOutParameter(3, java.sql.Types.NUMERIC);

    cs.execute();

    long orderId = cs.getLong(3);
}
```

OUT parameters must be registered with the appropriate JDBC type before reading the result.

### 18.3. Calling a Function Using Escape Syntax

```java
String sql = "{ ? = call app_owner.get_customer_order_total(?) }";

try (CallableStatement cs = connection.prepareCall(sql)) {
    cs.registerOutParameter(1, java.sql.Types.NUMERIC);
    cs.setLong(2, 501L);

    cs.execute();

    BigDecimal total = cs.getBigDecimal(1);
}
```

The first placeholder receives the function's RETURN value; subsequent placeholders are input parameters.

### 18.4. Calling a Function via SELECT

```java
String sql =
    "SELECT app_owner.get_customer_order_total(?) FROM dual";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, 501L);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            BigDecimal total = rs.getBigDecimal(1);
        }
    }
}
```

This approach uses the function as a SQL expression; the function must satisfy SQL invocation restrictions. Using `CallableStatement` is usually clearer when calling a function according to a stored program contract.

### 18.5. Transactions in JDBC

```java
connection.setAutoCommit(false);

try (CallableStatement cs =
         connection.prepareCall("{ call app_owner.update_demo_order_status(?, ?) }")) {
    cs.setLong(1, 1001L);
    cs.setString(2, "PAID");
    cs.execute();

    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
```

This example illustrates caller-managed transactions. If the connection is managed by a framework transaction manager, let the framework own commit/rollback rather than committing manually at multiple layers.

## 19. Designing Usable PL/SQL APIs

### 19.1. Procedure Names Should Describe Actions

Examples:

- `CREATE_ORDER`
- `CANCEL_ORDER`
- `UPDATE_CUSTOMER_ADDRESS`
- `REBUILD_DAILY_SUMMARY`

### 19.2. Function Names Should Describe Values

Examples:

- `CALCULATE_TAX`
- `GET_ORDER_TOTAL`
- `NORMALIZE_EMAIL`
- `IS_CUSTOMER_ACTIVE`

Functions returning BOOLEAN can only be used according to the data type capabilities of the database version and context. If broad SQL/driver compatibility is needed, consider returning NUMBER or VARCHAR2 under a clear contract.

### 19.3. Do Not Return Ambiguous Status Codes

If a procedure returns `OUT status_code`, define it clearly:

| Code | Meaning |
|---|---|
| `0` | Success |
| `1` | Object not found |
| `2` | Business state not allowed |
| `-1` | Unexpected error; exception is raised |

This is only a convention example; real systems should use consistent error codes. Do not both return status codes and swallow all exceptions, leaving the caller unaware of how far the transaction progressed.

### 19.4. Define Function Cardinality

A function looking up a single row by a unique key can use SELECT INTO and handle NO_DATA_FOUND. If the function computes a sum or count, an aggregate can return one row. If a function needs to return multiple rows, consider a pipelined table function, a collection return type, or a procedure returning a REF CURSOR as needed; do not force a list into a scalar.

### 19.5. Limit Side Effects in Functions

A function is easiest to use when the same inputs produce the same output given the data it reads and it does not mutate state. For functions called from SQL, avoiding side effects is even more critical. Use procedures for actions that modify data so the API clearly communicates its impact.

## 20. Common Errors and Misconceptions

| Error/Symptom | Common Cause | How to Handle |
|---|---|---|
| `PLS-00103` | Syntax error, missing `;`, `BEGIN`, or `END` | Check the entire body and terminators |
| `PLS-00201` | Undeclared identifier or missing privilege | Check name, schema, direct privileges, and dependencies |
| `PLS-00323` | Package body does not implement a subprogram declared in the spec | Synchronize spec/body signatures |
| `PLS-00306` | Wrong number or types of arguments in call | Check mode, order, data types, and defaults |
| `ORA-06503` | Function finishes without returning a value | Ensure every normal execution path executes RETURN |
| `ORA-14551` | Function called from a query attempts to perform DML | Move the write operation to a procedure or separate DML |
| `ORA-04063` | Stored object has errors or is invalid | Check USER_ERRORS, fix, and compile |
| `ORA-04068` | Existing state of packages has been discarded in certain invalidation/recompile scenarios | Handle controlled retry in the application; manage package deployments |
| Procedure does not return a value | Expecting a procedure to be used like a SQL expression | Use an OUT parameter or a function |
| Function used like an action | Function has unpredictable DML/side effects | Switch to a procedure if the goal is modifying data |
| Procedure commits on its own | Transaction boundary hidden inside the API | Let the caller manage it or document the transaction ownership contract |
| Slow function in SELECT | Repeated PL/SQL calls across many rows | Consider set-based SQL, JOINs, and runtime plans |
| Cannot call from another schema | Missing EXECUTE or wrong owner name | GRANT EXECUTE and schema-qualify |
| Unit INVALID after ALTER TABLE | Dependencies affected | Check USER_ERRORS/DEPENDENCIES and recompile |
| Dynamic SQL injection | Concatenating input into SQL string | Bind values, validate/whitelist object names |

### 20.1. Reading Compile Errors

In SQL*Plus or SQLcl:

```sql
SHOW ERRORS PROCEDURE create_demo_order;
SHOW ERRORS FUNCTION get_customer_order_total;
```

Or:

```sql
SELECT name, type, line, position, text
FROM user_errors
WHERE name IN (
    'CREATE_DEMO_ORDER',
    'GET_CUSTOMER_ORDER_TOTAL'
)
ORDER BY name, sequence;
```

Do not just look at the message `Warning: Procedure created with compilation errors`; read the specific PLS error and its line/position.

## 21. Comprehensive Hands-On Practice

The steps below create a table and stored units in a lab schema. Run them only when you have CREATE TABLE/PROCEDURE privileges and avoid colliding with business object names. Identity columns require Oracle 12c Release 1 or later.

### Step 1. Create the Demo Table

```sql
CREATE TABLE lab_program_orders (
    order_id NUMBER GENERATED BY DEFAULT AS IDENTITY
        CONSTRAINT pk_lab_program_orders PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    amount NUMBER(12, 2) NOT NULL,
    status VARCHAR2(20) DEFAULT 'NEW' NOT NULL,
    created_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

### Step 2. Create the Procedure to Insert an Order

```sql
CREATE OR REPLACE PROCEDURE lab_create_order (
    p_customer_id IN lab_program_orders.customer_id%TYPE,
    p_amount IN lab_program_orders.amount%TYPE,
    p_order_id OUT lab_program_orders.order_id%TYPE
) AS
BEGIN
    IF p_amount < 0 THEN
        RAISE_APPLICATION_ERROR(-20050, 'Amount must be non-negative');
    END IF;

    INSERT INTO lab_program_orders (customer_id, amount, status)
    VALUES (p_customer_id, p_amount, 'NEW')
    RETURNING order_id INTO p_order_id;
END lab_create_order;
/
```

### Step 3. Call the Procedure and Receive the OUT Value

```sql
DECLARE
    v_order_id lab_program_orders.order_id%TYPE;
BEGIN
    lab_create_order(501, 100000, v_order_id);
    DBMS_OUTPUT.PUT_LINE('New ID=' || v_order_id);
END;
/
```

### Step 4. Create the Total Calculation Function

```sql
CREATE OR REPLACE FUNCTION lab_customer_total (
    p_customer_id IN lab_program_orders.customer_id%TYPE
) RETURN NUMBER
AS
    v_total NUMBER;
BEGIN
    SELECT NVL(SUM(amount), 0)
    INTO v_total
    FROM lab_program_orders
    WHERE customer_id = p_customer_id
      AND status <> 'CANCELLED';

    RETURN v_total;
END lab_customer_total;
/
```

### Step 5. Call the Function in PL/SQL

```sql
DECLARE
    v_total NUMBER;
BEGIN
    v_total := lab_customer_total(501);
    DBMS_OUTPUT.PUT_LINE('Total=' || v_total);
END;
/
```

### Step 6. Call the Function in SQL

```sql
SELECT lab_customer_total(501) AS customer_total
FROM dual;
```

### Step 7. Check Compilation Errors and Status

```sql
SELECT object_name, object_type, status
FROM user_objects
WHERE object_name IN ('LAB_CREATE_ORDER', 'LAB_CUSTOMER_TOTAL')
ORDER BY object_type;

SELECT name, type, line, position, text
FROM user_errors
WHERE name IN ('LAB_CREATE_ORDER', 'LAB_CUSTOMER_TOTAL')
ORDER BY name, sequence;
```

### Step 8. Observe the Transaction

```sql
SELECT *
FROM lab_program_orders
ORDER BY order_id;

ROLLBACK;
```

Because the procedure does not COMMIT, the caller can roll back the order creation operation. If you want to keep the data in the lab schema, replace ROLLBACK with COMMIT after verifying.

### Step 9. Grant EXECUTE Privilege (Optional)

If there is another lab schema named `APP_USER` and granting privileges is allowed:

```sql
GRANT EXECUTE ON lab_create_order TO app_user;
GRANT EXECUTE ON lab_customer_total TO app_user;
```

### Step 10. Clean Up Practice Objects

Only when you are sure these are objects you created and you no longer need the data:

```sql
DROP PROCEDURE lab_create_order;
DROP FUNCTION lab_customer_total;
DROP TABLE lab_program_orders PURGE;
```

`DROP TABLE ... PURGE` deletes the table and its data, bypassing the recycle bin per command behavior; DDL performs an implicit commit. Do not run cleanup commands on business schemas or shared objects.

## 22. Rules to Remember

| Question | Choose |
|---|---|
| Need to perform an action or DML | Procedure |
| Need a value inside an expression | Function |
| Need multiple output results | Procedure with OUT parameters or an API returning a cursor |
| Need one-off logic in a script | Anonymous block |
| Multiple APIs in the same business domain | Package |
| Need automatic reaction to database events | Trigger, if truly appropriate |
| Need a function usable in SQL | Function with SQL-compatible parameters/types and no disallowed side effects |
| Need to modify data | Procedure or explicit DML |
| Need caller-controlled transactions | No hidden COMMIT/ROLLBACK inside procedures |
| Need controlled execution privileges | GRANT EXECUTE on stored units |
| Need caller-based privileges | Consider AUTHID CURRENT_USER |
| Need API grouping and overloading | Package specification/body |

## 23. Self-Check Questions

**Question 1.** What is a stored procedure?

**Answer:** A named PL/SQL program stored in a schema, typically used to perform an action or workflow and capable of receiving/returning data via parameters.

**Question 2.** What is the main difference between a stored function and a procedure?

**Answer:** A function declares a return type and must return a value via RETURN; a procedure does not return a value through RETURN and can instead use OUT/IN OUT.

**Question 3.** What is the default mode of a PL/SQL parameter?

**Answer:** `IN`.

**Question 4.** What is an OUT parameter used for?

**Answer:** Passing a value produced by the procedure/function back to the caller.

**Question 5.** How does IN OUT differ from OUT?

**Answer:** IN OUT receives an initial value from the caller, can modify it, and returns it; OUT is primarily used to return a result.

**Question 6.** Can a function be called inside a SELECT statement?

**Answer:** Yes, provided the function satisfies SQL invocation rules regarding parameters, data types, and side effects.

**Question 7.** Can a function called from SQL use an OUT parameter?

**Answer:** No. A function called directly from SQL must not have OUT or IN OUT parameters.

**Question 8.** Why should a function called from SELECT not perform DML?

**Answer:** DML inside a query-invoked function is restricted and can cause ORA-14551; functions with side effects also make SQL behavior unpredictable.

**Question 9.** What must a function guarantee regarding RETURN?

**Answer:** Every normal execution path must return a value compatible with the RETURN type.

**Question 10.** Should every procedure COMMIT internally?

**Answer:** No. Usually the caller should manage the transaction boundary so multiple operations can be combined in the same transaction.

**Question 11.** What is AUTHID DEFINER?

**Answer:** The program executes in the security context of the schema owning the unit, following Oracle's definer's rights rules.

**Question 12.** What does AUTHID CURRENT_USER mean?

**Answer:** The program uses invoker's rights, evaluating privileges according to the current user/caller under Oracle rules.

**Question 13.** What advantages do packages have over multiple standalone procedures?

**Answer:** Grouping related APIs, separating public specification from private implementation, supporting overloading, and managing components of the same business domain.

**Question 14.** How do you check compilation errors for a procedure/function?

**Answer:** Use `SHOW ERRORS` or query `USER_ERRORS`, then check the status in `USER_OBJECTS`.

**Question 15.** When should you choose a trigger?

**Answer:** When automatic reaction to a database event is needed for a clear reason; do not use triggers as a substitute for action APIs that the application should call explicitly.

**Question 16.** Can a procedure be called directly inside a SELECT statement?

**Answer:** No. A SQL expression requires a function that returns a value; a procedure is called as a statement in PL/SQL or through a client's procedure call mechanism.

## 24. Conclusion

`CREATE PROCEDURE` and `CREATE FUNCTION` create named, reusable PL/SQL programs stored in a schema. Procedures fit actions, DML, and workflows; functions fit computations or lookups that return a single value. `IN`, `OUT`, and `IN OUT` parameters define data direction, while a function must declare a return type and execute `RETURN` on every normal execution path.

Functions can be used in SQL if they comply with restrictions on parameters, data types, and side effects. Keep functions used in SQL simple, predictable, and free of DML or transaction control. Use procedures for operations that modify data, and typically let the caller manage COMMIT/ROLLBACK to keep transaction boundaries clear.

As APIs grow, packages help group procedures/functions by business domain, expose a stable public interface, and hide implementation details. Anonymous blocks remain suitable for short scripts; triggers are meant for automatic reactions to events. Choosing the right program unit makes PL/SQL easier to call, secure, test, and maintain.
