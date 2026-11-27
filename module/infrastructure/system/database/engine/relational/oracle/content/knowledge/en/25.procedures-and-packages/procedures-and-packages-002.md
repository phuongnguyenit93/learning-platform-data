# IN, OUT, IN OUT Parameters, and Default Values

> **Topic:** Database Engine Relational Oracle  
> **Chapter:** Procedures and Packages  
> **Goal:** Understand how to declare and pass parameters to procedures/functions in PL/SQL; distinguish the three modes IN, OUT, and IN OUT; use default values; invoke subprograms using positional notation and named notation; choose appropriate parameter data types using %TYPE/%ROWTYPE; and handle results, NULL, exceptions, and NOCOPY safely.

## 1. Parameters Allow Subprograms to Receive Data and Return Results

Procedures and functions often need to work with data that changes per call. A parameter is the interface through which the caller passes inputs to a subprogram or receives results from it.

For example, a procedure that calculates a discounted price may accept:

- Original price.
- Discount rate.
- Final price to return.

~~~sql
CREATE OR REPLACE PROCEDURE calculate_price (
    p_original_price IN NUMBER,
    p_discount_rate  IN NUMBER,
    p_final_price    OUT NUMBER
) IS
BEGIN
    p_final_price :=
        p_original_price * (1 - p_discount_rate);
END;
/
~~~

Calling the procedure:

~~~sql
DECLARE
    l_final_price NUMBER;
BEGIN
    calculate_price(
        1000,
        0.10,
        l_final_price
    );

    DBMS_OUTPUT.PUT_LINE('Final price = ' || l_final_price);
END;
/
~~~

Here P_ORIGINAL_PRICE and P_DISCOUNT_RATE receive input data; P_FINAL_PRICE is assigned by the procedure and returned to the caller.

In PL/SQL, each formal parameter has a mode that defines how data crosses the call boundary:

- **IN:** receives an input value for reading.
- **OUT:** returns a value to the caller.
- **IN OUT:** receives an initial value, allows modification, and returns the new value.

If no mode is specified, Oracle defaults to IN.

## 2. Formal Parameter and Actual Parameter

Two concepts should be distinguished:

- **Formal parameter:** the parameter name declared in the procedure/function.
- **Actual parameter (argument):** the actual value or variable passed at the call site.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE greet_user (
    p_user_name IN VARCHAR2
) IS
BEGIN
    DBMS_OUTPUT.PUT_LINE('Hello ' || p_user_name);
END;
/
~~~

When calling:

~~~sql
DECLARE
    l_name VARCHAR2(50) := 'Lan';
BEGIN
    greet_user(l_name);
END;
/
~~~

P_USER_NAME is the formal parameter; L_NAME is the actual parameter.

An actual parameter can be a literal, constant, variable, or expression for an IN parameter. For OUT and IN OUT, the actual parameter must be a variable capable of receiving a result.

## 3. IN: Input Parameter

IN is the default mode. The subprogram receives a value from the caller and is allowed to read it. A formal IN parameter is read-only inside the subprogram; do not assign a new value to it.

Syntax:

~~~sql
p_parameter_name IN datatype
~~~

Example:

~~~sql
CREATE OR REPLACE PROCEDURE show_employee (
    p_employee_id IN employees.employee_id%TYPE
) IS
    l_employee_name employees.employee_name%TYPE;
BEGIN
    SELECT employee_name
    INTO l_employee_name
    FROM employees
    WHERE employee_id = p_employee_id;

    DBMS_OUTPUT.PUT_LINE(l_employee_name);
END;
/
~~~

Calling the procedure:

~~~sql
BEGIN
    show_employee(100);
END;
/
~~~

### 3.1. IN Is Read-Only

You cannot assign to a formal IN parameter:

~~~sql
CREATE OR REPLACE PROCEDURE invalid_example (
    p_amount IN NUMBER
) IS
BEGIN
    p_amount := 100; -- Invalid
END;
/
~~~

If you need to compute using the input value, assign it to a local variable:

~~~sql
CREATE OR REPLACE PROCEDURE calculate_tax (
    p_amount IN NUMBER
) IS
    l_tax NUMBER;
BEGIN
    l_tax := p_amount * 0.10;

    DBMS_OUTPUT.PUT_LINE('Tax = ' || l_tax);
END;
/
~~~

This preserves the input semantics and clarifies what data comes from the caller versus what is an internal computed result.

### 3.2. Actual Parameters for IN Can Be Expressions

Because IN only receives input, the caller can pass literals or expressions:

~~~sql
BEGIN
    calculate_tax(1000);
    calculate_tax(500 + 500);
END;
/
~~~

A variable can also be passed:

~~~sql
DECLARE
    l_amount NUMBER := 2500;
BEGIN
    calculate_tax(l_amount);
END;
/
~~~

Do not use literals or expressions for OUT/IN OUT because those modes require a target to write results into.

## 4. OUT: Output Parameter

OUT is used by a subprogram to return a result to the caller. The caller must pass an assignable variable.

Syntax:

~~~sql
p_parameter_name OUT datatype
~~~

Example of a procedure returning an employee's name and salary:

~~~sql
CREATE OR REPLACE PROCEDURE get_employee_details (
    p_employee_id   IN  employees.employee_id%TYPE,
    p_employee_name OUT employees.employee_name%TYPE,
    p_salary        OUT employees.salary%TYPE
) IS
BEGIN
    SELECT employee_name, salary
    INTO p_employee_name, p_salary
    FROM employees
    WHERE employee_id = p_employee_id;
END;
/
~~~

The caller declares receiving variables:

~~~sql
DECLARE
    l_name employees.employee_name%TYPE;
    l_salary employees.salary%TYPE;
BEGIN
    get_employee_details(
        p_employee_id   => 100,
        p_employee_name => l_name,
        p_salary        => l_salary
    );

    DBMS_OUTPUT.PUT_LINE(l_name || ': ' || l_salary);
END;
/
~~~

### 4.1. OUT Is Not Used to Read the Old Value of the Actual Parameter

OUT is designed to return results. Upon entering the subprogram, do not rely on whatever value the caller currently holds in the actual variable as input data. Assign a value to the formal OUT parameter before using it as a result.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE get_discount (
    p_customer_type IN  VARCHAR2,
    p_discount_rate OUT NUMBER
) IS
BEGIN
    IF p_customer_type = 'VIP' THEN
        p_discount_rate := 0.20;
    ELSE
        p_discount_rate := 0.05;
    END IF;
END;
/
~~~

Do not write logic like "if p_discount_rate already has a prior value, add to it..." because OUT does not carry read-modify semantics for an input actual value. If you need to receive an initial value and return a modified value, use IN OUT.

### 4.2. OUT Must Be Assigned on Every Successful Path

A procedure should explicitly determine its output result before normal termination:

~~~sql
CREATE OR REPLACE PROCEDURE calculate_bonus (
    p_salary IN  NUMBER,
    p_bonus  OUT NUMBER
) IS
BEGIN
    IF p_salary IS NULL THEN
        p_bonus := 0;
    ELSIF p_salary >= 10000 THEN
        p_bonus := p_salary * 0.20;
    ELSE
        p_bonus := p_salary * 0.10;
    END IF;
END;
/
~~~

If a normal branch finishes without assigning OUT, the caller may receive an unexpected value. A good rule is to assign a default first and then update per branch:

~~~sql
BEGIN
    p_bonus := 0;

    IF p_salary >= 10000 THEN
        p_bonus := p_salary * 0.20;
    END IF;
END;
~~~

The second snippet only illustrates initializing the result; a complete procedure must include the corresponding declaration and parameter list.

### 4.3. OUT with SELECT INTO

A common use case is returning queried data:

~~~sql
CREATE OR REPLACE PROCEDURE find_customer_name (
    p_customer_id   IN  customers.customer_id%TYPE,
    p_customer_name OUT customers.customer_name%TYPE
) IS
BEGIN
    SELECT customer_name
    INTO p_customer_name
    FROM customers
    WHERE customer_id = p_customer_id;
END;
/
~~~

SELECT INTO can raise:

- NO_DATA_FOUND if no row exists.
- TOO_MANY_ROWS if more than one row exists.

If an exception escapes the subprogram, the caller should not rely on the OUT value as though a normal result was returned. Define the error contract clearly: propagate the exception, return a status, or use a nullable result with an explicit convention.

### 4.4. Returning Status via OUT

A procedure can be designed to return both data and status:

~~~sql
CREATE OR REPLACE PROCEDURE try_get_customer (
    p_customer_id   IN  customers.customer_id%TYPE,
    p_customer_name OUT customers.customer_name%TYPE,
    p_found         OUT VARCHAR2
) IS
BEGIN
    p_customer_name := NULL;
    p_found := 'N';

    BEGIN
        SELECT customer_name
        INTO p_customer_name
        FROM customers
        WHERE customer_id = p_customer_id;

        p_found := 'Y';
    EXCEPTION
        WHEN NO_DATA_FOUND THEN
            p_customer_name := NULL;
            p_found := 'N';
    END;
END;
/
~~~

In this example, NO_DATA_FOUND is handled internally and the procedure exits normally with status N. If another error occurs, the exception continues propagating to the caller.

Do not use NULL as a status if NULL can also be a valid data value or an undetermined state. Choose an explicit status domain such as Y/N, FOUND/NOT_FOUND, or defined result codes.

## 5. IN OUT: Both Receiving and Returning Values

IN OUT allows a subprogram to receive the current value of the actual parameter, read or modify it, and return the new value to the caller.

Syntax:

~~~sql
p_parameter_name IN OUT datatype
~~~

Example of increasing a variable's value by a percentage:

~~~sql
CREATE OR REPLACE PROCEDURE apply_increase (
    p_amount IN OUT NUMBER,
    p_rate   IN     NUMBER DEFAULT 0.10
) IS
BEGIN
    p_amount := p_amount * (1 + p_rate);
END;
/
~~~

Calling it:

~~~sql
DECLARE
    l_amount NUMBER := 1000;
BEGIN
    apply_increase(l_amount, 0.20);

    DBMS_OUTPUT.PUT_LINE('New amount = ' || l_amount);
END;
/
~~~

Initially L_AMOUNT is 1000. The procedure receives that value, computes 1200, and returns the result into the same L_AMOUNT variable.

### 5.1. IN OUT Requires an Actual Variable

Valid:

~~~sql
DECLARE
    l_counter NUMBER := 5;
BEGIN
    apply_increase(l_counter);
END;
/
~~~

Invalid:

~~~sql
BEGIN
    apply_increase(1000); -- A literal cannot receive a returned result
END;
/
~~~

IN OUT requires a variable to receive the value after the subprogram completes.

### 5.2. Distinguishing IN and IN OUT

If you only need to read an input and return a separate result, use IN + OUT:

~~~sql
calculate_price(
    p_original_price => l_original,
    p_discount_rate  => l_rate,
    p_final_price    => l_final
);
~~~

If you need to modify the passed-in value itself, use IN OUT:

~~~sql
apply_increase(l_amount, 0.10);
~~~

Do not use IN OUT merely for convenience. The mode should express the subprogram's contract accurately so callers know which variables may be modified.

## 6. Comparing the Three Modes

| Characteristic | IN | OUT | IN OUT |
|---|---|---|---|
| Receives data from caller | Yes | Does not use old value as input | Yes |
| Reads formal parameter inside subprogram | Yes | Only read after assigning result | Yes |
| Assigns formal parameter | No | Yes | Yes |
| Returns result to caller | No | Yes | Yes |
| Actual parameter must be a variable | Not required | Yes | Yes |
| Allows default value | Yes | No | No |
| Purpose | Input | Output | Input transformed into output |

A procedure can combine multiple modes:

~~~sql
CREATE OR REPLACE PROCEDURE calculate_invoice (
    p_subtotal IN     NUMBER,
    p_tax_rate IN     NUMBER DEFAULT 0.08,
    p_tax      OUT    NUMBER,
    p_total    OUT    NUMBER
) IS
BEGIN
    p_tax := NVL(p_subtotal, 0) * p_tax_rate;
    p_total := NVL(p_subtotal, 0) + p_tax;
END;
/
~~~

When calling, the caller provides subtotal, may omit tax rate, and passes two variables to receive the results.

## 7. Default Values for Parameters

Default values save the caller from having to pass every parameter on every call. In PL/SQL, defaults are declared for IN parameters.

Syntax:

~~~sql
parameter_name IN datatype DEFAULT expression
~~~

Or using the assignment operator:

~~~sql
parameter_name IN datatype := expression
~~~

Example:

~~~sql
CREATE OR REPLACE PROCEDURE create_ticket (
    p_title    IN VARCHAR2,
    p_priority IN VARCHAR2 DEFAULT 'NORMAL',
    p_source   IN VARCHAR2 DEFAULT 'WEB'
) IS
BEGIN
    INSERT INTO support_tickets (
        title,
        priority,
        source
    )
    VALUES (
        p_title,
        p_priority,
        p_source
    );
END;
/
~~~

Calling with all parameters:

~~~sql
BEGIN
    create_ticket('Cannot sign in', 'HIGH', 'MOBILE');
END;
/
~~~

Omitting trailing default parameters:

~~~sql
BEGIN
    create_ticket('Question about invoice');
END;
/
~~~

In the second call, P_PRIORITY receives NORMAL and P_SOURCE receives WEB.

### 7.1. Default Is Only Used When the Parameter Is Omitted

This is an important distinction:

~~~sql
BEGIN
    create_ticket('Cannot sign in');
END;
/
~~~

P_PRIORITY receives the default value NORMAL.

~~~sql
BEGIN
    create_ticket(
        p_title    => 'Cannot sign in',
        p_priority => NULL
    );
END;
/
~~~

P_PRIORITY receives NULL because the caller passed an explicit value. Oracle does not automatically replace NULL with the default.

If the business rule wants NULL to also mean using the default, the procedure must handle it explicitly:

~~~sql
IF p_priority IS NULL THEN
    l_priority := 'NORMAL';
ELSE
    l_priority := p_priority;
END IF;
~~~

Here L_PRIORITY is a local variable; the formal IN parameter P_PRIORITY remains read-only.

### 7.2. Only IN Can Have a Default

Do not declare defaults for OUT or IN OUT:

~~~sql
CREATE OR REPLACE PROCEDURE invalid_defaults (
    p_input  IN     NUMBER DEFAULT 0,
    p_result OUT    NUMBER DEFAULT 0
) IS
BEGIN
    NULL;
END;
/
~~~

The declaration above is invalid because OUT does not support default parameter values. Similarly, IN OUT cannot declare a default.

If a subprogram has an OUT parameter, the caller must still supply a receiving variable.

### 7.3. Order of Default Parameters

With positional notation, parameters with defaults are usually placed at the end so callers can omit them without shifting positional mapping.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE search_orders (
    p_customer_id IN NUMBER,
    p_status      IN VARCHAR2 DEFAULT 'OPEN',
    p_min_amount  IN NUMBER DEFAULT 0
) IS
BEGIN
    NULL;
END;
/
~~~

Can be called as:

~~~sql
BEGIN
    search_orders(100);
    search_orders(100, 'PAID');
    search_orders(100, 'PAID', 500);
END;
/
~~~

If you want to omit P_STATUS while still passing P_MIN_AMOUNT, positional notation is inconvenient; use named notation.

### 7.4. Default Expression

A default can be an expression compatible with the parameter type, for example:

~~~sql
CREATE OR REPLACE PROCEDURE register_event (
    p_event_name IN VARCHAR2,
    p_created_at IN TIMESTAMP DEFAULT SYSTIMESTAMP
) IS
BEGIN
    NULL;
END;
/
~~~

When the caller omits P_CREATED_AT, the default value is used. When the caller passes a specific timestamp, that value is used instead.

The default expression must be type-compatible and comply with PL/SQL restrictions. Do not confuse formal parameter defaults with column DEFAULTs in CREATE TABLE; the two mechanisms apply at different times and in different contexts.

## 8. Positional Notation: Passing by Position

With positional notation, actual arguments are mapped in the order the formal parameters are declared.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE register_customer (
    p_name   IN VARCHAR2,
    p_email  IN VARCHAR2,
    p_region IN VARCHAR2 DEFAULT 'VN'
) IS
BEGIN
    NULL;
END;
/
~~~

Calling:

~~~sql
BEGIN
    register_customer('An', 'an@example.com', 'SG');
    register_customer('Binh', 'binh@example.com');
END;
/
~~~

The first call maps:

- P_NAME = An
- P_EMAIL = an@example.com
- P_REGION = SG

The second call passes only two arguments, so P_REGION uses the default VN.

### 8.1. Pros and Cons

Positional notation is concise when a procedure has few parameters and an obvious order. However, when multiple parameters share the same data type, readers have difficulty spotting swapped positions.

Example:

~~~sql
calculate_transfer(
    100,
    200,
    500
);
~~~

If all three are NUMBER, it is very hard to tell from the call alone which value is the source account, destination account, or amount.

## 9. Named Notation: Passing by Name

Named notation explicitly states which formal parameter receives which actual argument:

~~~sql
BEGIN
    register_customer(
        p_name   => 'An',
        p_email  => 'an@example.com',
        p_region => 'VN'
    );
END;
/
~~~

The order of named arguments can be changed:

~~~sql
BEGIN
    register_customer(
        p_region => 'SG',
        p_email  => 'binh@example.com',
        p_name   => 'Binh'
    );
END;
/
~~~

Parameter names make code easier to read and reduce the risk of passing arguments in the wrong order when multiple parameters share the same data type.

### 9.1. Named Notation Lets You Skip Middle Default Parameters

Example:

~~~sql
CREATE OR REPLACE PROCEDURE create_report (
    p_report_name IN VARCHAR2,
    p_format      IN VARCHAR2 DEFAULT 'PDF',
    p_language    IN VARCHAR2 DEFAULT 'VI',
    p_owner       IN VARCHAR2 DEFAULT 'SYSTEM'
) IS
BEGIN
    NULL;
END;
/
~~~

To use defaults for FORMAT and LANGUAGE while passing OWNER:

~~~sql
BEGIN
    create_report(
        p_report_name => 'Monthly sales',
        p_owner       => 'FINANCE'
    );
END;
/
~~~

Oracle uses defaults for the omitted parameters. This is why named notation is useful when there are many optional parameters.

### 9.2. Do Not Pass Positional Arguments After Named Arguments

Once you start using named notation, do not continue with a positional actual argument afterward.

Invalid:

~~~sql
BEGIN
    create_report(
        p_report_name => 'Monthly sales',
        'CSV'
    );
END;
/
~~~

Place positional arguments first, followed by named arguments; or use named notation for everything:

~~~sql
BEGIN
    create_report(
        p_report_name => 'Monthly sales',
        p_format      => 'CSV'
    );
END;
/
~~~

### 9.3. Using the => Symbol

In named notation, the `=>` symbol binds a formal parameter name to an actual argument:

~~~sql
p_parameter_name => actual_value
~~~

Do not confuse `=>` with the assignment operator `:=`. The `:=` operator assigns values to variables in PL/SQL; `=>` is used in calls to map parameters by name.

## 10. Combining Positional and Named Notation

PL/SQL allows passing leading arguments positionally, then using named notation for the remaining arguments.

Example:

~~~sql
BEGIN
    create_report(
        'Monthly sales',
        p_owner => 'FINANCE'
    );
END;
/
~~~

P_REPORT_NAME is passed positionally. P_OWNER is passed by name. P_FORMAT and P_LANGUAGE are omitted and thus use defaults.

A positional argument must not follow a named argument. In production code, using named notation for calls with many parameters is usually easier to maintain.

## 11. Using %TYPE and %ROWTYPE for Parameter Data Types

When a parameter has the same type as a table column, use %TYPE to avoid declaring the data type manually:

~~~sql
CREATE OR REPLACE PROCEDURE update_employee_salary (
    p_employee_id IN employees.employee_id%TYPE,
    p_new_salary  IN employees.salary%TYPE
) IS
BEGIN
    UPDATE employees
    SET salary = p_new_salary
    WHERE employee_id = p_employee_id;
END;
/
~~~

If the column's data type or precision changes, referencing %TYPE keeps the parameter synchronized with the column type.

### 11.1. %ROWTYPE for Records

You can use %ROWTYPE when you need to pass an entire row:

~~~sql
CREATE OR REPLACE PROCEDURE display_employee (
    p_employee IN employees%ROWTYPE
) IS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        p_employee.employee_id || ': ' ||
        p_employee.employee_name
    );
END;
/
~~~

The caller creates a compatible record:

~~~sql
DECLARE
    l_employee employees%ROWTYPE;
BEGIN
    SELECT *
    INTO l_employee
    FROM employees
    WHERE employee_id = 100;

    display_employee(l_employee);
END;
/
~~~

A record parameter is useful when many fields are always passed together. However, it creates a dependency on the row structure; if a procedure only needs a few fields, separate parameters usually express the contract more clearly.

### 11.2. Collection or Object Parameters

PL/SQL also allows passing collections, records, objects, and appropriate composite data types. For large collections, OUT/IN OUT modes may warrant considering NOCOPY to reduce copy overhead; see the following section.

The data types of actual and formal parameters must be compatible under PL/SQL rules. Implicit conversion may occur in some cases, but you should not rely on ambiguous implicit conversions between strings and numbers/dates.

## 12. NULL Values and Default Values

Defaults only apply when the caller omits the parameter. NULL is an explicitly passed value.

| Call Pattern | Result for Parameter with Default |
|---|---|
| Parameter omitted | Uses default |
| Specific value passed | Uses specific value |
| NULL passed | Parameter value is NULL |
| Variable currently holding NULL passed | Parameter value is NULL |

Example:

~~~sql
CREATE OR REPLACE PROCEDURE set_priority (
    p_priority IN VARCHAR2 DEFAULT 'NORMAL'
) IS
BEGIN
    DBMS_OUTPUT.PUT_LINE(
        'Priority = ' || NVL(p_priority, 'NULL')
    );
END;
/
~~~

Calling:

~~~sql
BEGIN
    set_priority;          -- NORMAL
    set_priority('HIGH');  -- HIGH
    set_priority(NULL);    -- NULL
END;
/
~~~

If you want NULL to be treated as the default:

~~~sql
CREATE OR REPLACE PROCEDURE set_priority (
    p_priority IN VARCHAR2 DEFAULT 'NORMAL'
) IS
    l_priority VARCHAR2(20);
BEGIN
    l_priority := NVL(p_priority, 'NORMAL');

    DBMS_OUTPUT.PUT_LINE('Priority = ' || l_priority);
END;
/
~~~

This is a rule defined by the procedure itself. Only add NVL when NULL genuinely has the same business meaning as the default value.

## 13. OUT and IN OUT When Exceptions Occur

OUT/IN OUT parameters are channels for returning results. If a subprogram terminates normally, formal values are copied back to actual parameters according to PL/SQL semantics.

If an exception escapes the subprogram, the caller should not rely on OUT/IN OUT values as valid results. Handle exceptions and clearly define the result-return contract.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE calculate_total (
    p_quantity IN  NUMBER,
    p_price    IN  NUMBER,
    p_total    OUT NUMBER
) IS
BEGIN
    p_total := NULL;

    IF p_quantity IS NULL OR p_price IS NULL THEN
        RAISE_APPLICATION_ERROR(-20001, 'Input is required');
    END IF;

    p_total := p_quantity * p_price;
END;
/
~~~

The caller should handle errors:

~~~sql
DECLARE
    l_total NUMBER;
BEGIN
    calculate_total(2, 100, l_total);
    DBMS_OUTPUT.PUT_LINE(l_total);
EXCEPTION
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(SQLERRM);
        RAISE;
END;
/
~~~

In the example, when the input is invalid, the procedure raises an exception. The caller must not assume L_TOTAL holds a new result value. If the API also needs to return failure status, expected errors can be caught inside the procedure and returned via an OUT status per contract; unexpected errors should still propagate.

Do not catch WHEN OTHERS and pretend the call succeeded. If catching an error, make explicit decisions about rollback, output state, and error reporting.

## 14. NOCOPY: Pass-by-Reference Hint

NOCOPY can be used with OUT or IN OUT to hint that the compiler should pass the parameter by reference instead of copying data. It can be useful for large records or collections.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE normalize_names (
    p_names IN OUT NOCOPY name_list_type
) IS
BEGIN
    FOR i IN 1 .. p_names.COUNT LOOP
        p_names(i) := UPPER(TRIM(p_names(i)));
    END LOOP;
END;
/
~~~

NOCOPY is a **hint**, not a guarantee that Oracle will always pass by reference. The compiler may ignore it in certain situations.

### 14.1. Risks of Using NOCOPY

With pass-by-reference, the caller may observe partial modifications to the actual parameter even when the subprogram terminates with an exception. This differs from the normal copy-in/copy-out expectation of some programs.

For example, a procedure modifies the first element of a collection and then fails on a later element; the caller may see the collection partially modified if NOCOPY was applied.

Therefore:

- Only use NOCOPY when there is a measurable performance reason.
- Do not rely on OUT/IN OUT only being updated when the subprogram succeeds.
- Design error handling so callers know data may have been partially modified.
- Test the behavior on the actual Oracle release/compiler.
- Avoid passing the same actual variable to multiple NOCOPY parameters, which can cause aliasing and unpredictable results.

Do not add NOCOPY out of habit to every OUT/IN OUT parameter.

## 15. Parameters in Package Specification and Package Body

When a procedure/function is a public member of a package, the declaration in the package specification defines the interface visible to callers.

Example:

~~~sql
CREATE OR REPLACE PACKAGE employee_api AS
    PROCEDURE get_salary (
        p_employee_id IN employees.employee_id%TYPE,
        p_salary      OUT employees.salary%TYPE
    );

    PROCEDURE apply_bonus (
        p_employee_id IN employees.employee_id%TYPE,
        p_rate        IN NUMBER DEFAULT 0.10
    );
END employee_api;
/
~~~

The package body implements the logic:

~~~sql
CREATE OR REPLACE PACKAGE BODY employee_api AS
    PROCEDURE get_salary (
        p_employee_id IN employees.employee_id%TYPE,
        p_salary      OUT employees.salary%TYPE
    ) IS
    BEGIN
        SELECT salary
        INTO p_salary
        FROM employees
        WHERE employee_id = p_employee_id;
    END get_salary;

    PROCEDURE apply_bonus (
        p_employee_id IN employees.employee_id%TYPE,
        p_rate        IN NUMBER
    ) IS
    BEGIN
        UPDATE employees
        SET salary = salary * (1 + p_rate)
        WHERE employee_id = p_employee_id;
    END apply_bonus;
END employee_api;
/
~~~

Defaults are published in the specification so callers can omit parameters. When defining the body, keep compatible signatures; do not arbitrarily change modes or data types compared to the specification.

The package specification is the public contract. Changing parameter names, order, modes, or defaults can impact caller source code and must be deployed under change control.

## 16. OUT Parameters and Function RETURN

A function has one formal return value via RETURN:

~~~sql
CREATE OR REPLACE FUNCTION calculate_area (
    p_width  IN NUMBER,
    p_height IN NUMBER
) RETURN NUMBER IS
BEGIN
    RETURN p_width * p_height;
END;
/
~~~

Calling:

~~~sql
DECLARE
    l_area NUMBER;
BEGIN
    l_area := calculate_area(10, 20);
END;
/
~~~

A function can also have OUT/IN OUT parameters in PL/SQL, but avoid using multiple result channels when a single RETURN value is already clear enough. In addition, functions called from SQL must comply with SQL-callable function restrictions; OUT/IN OUT parameters cannot be used as parameters in regular SQL statement calls.

Choose:

- Function RETURN when the primary result is a single value.
- Procedure with OUT when the operation has multiple results or is a business action.
- IN OUT when the caller intentionally passes a value in for the subprogram to transform and return.

Do not confuse an OUT parameter with the DML RETURNING INTO clause:

~~~sql
UPDATE employees
SET salary = salary + 500
WHERE employee_id = 100
RETURNING salary INTO l_new_salary;
~~~

RETURNING INTO is SQL DML syntax for retrieving values from modified rows; it is not the OUT mode of a formal parameter.

## 17. Complete Example: Procedure Receiving Input, Defaults, and Returning Output

Example of calculating shipping fees:

~~~sql
CREATE OR REPLACE PROCEDURE calculate_shipping (
    p_order_amount IN  NUMBER,
    p_customer_type IN VARCHAR2 DEFAULT 'REGULAR',
    p_shipping_fee OUT NUMBER,
    p_is_free      OUT VARCHAR2
) IS
BEGIN
    p_shipping_fee := 0;
    p_is_free := 'N';

    IF p_order_amount IS NULL OR p_order_amount < 0 THEN
        RAISE_APPLICATION_ERROR(-20010, 'Invalid order amount');
    ELSIF p_order_amount >= 1000 THEN
        p_shipping_fee := 0;
        p_is_free := 'Y';
    ELSIF p_customer_type = 'VIP' THEN
        p_shipping_fee := 10;
    ELSE
        p_shipping_fee := 25;
    END IF;
END;
/
~~~

Positional call:

~~~sql
DECLARE
    l_fee NUMBER;
    l_free VARCHAR2(1);
BEGIN
    calculate_shipping(800, 'VIP', l_fee, l_free);

    DBMS_OUTPUT.PUT_LINE(
        'Fee=' || l_fee || ', free=' || l_free
    );
END;
/
~~~

Named call using the default customer type:

~~~sql
DECLARE
    l_fee NUMBER;
    l_free VARCHAR2(1);
BEGIN
    calculate_shipping(
        p_order_amount => 500,
        p_shipping_fee => l_fee,
        p_is_free      => l_free
    );

    DBMS_OUTPUT.PUT_LINE(
        'Fee=' || l_fee || ', free=' || l_free
    );
END;
/
~~~

In the named call, P_CUSTOMER_TYPE is omitted and receives REGULAR. Both OUT parameters must always be supplied with receiving variables.

## 18. Common Mistakes

| Mistake | Consequence | How to Handle |
|---|---|---|
| Assigning a value to an IN parameter | Compilation error | Use a local variable or IN OUT |
| Passing a literal to OUT | Nowhere to store the result | Pass a variable |
| Passing an expression to IN OUT | Actual cannot receive the new value | Pass a variable |
| Reading OUT as input data | Logic violates mode contract | Use IN OUT if old value needs to be read |
| Not assigning OUT on a successful path | Caller receives undefined result per app logic | Initialize and assign outputs explicitly |
| Declaring default for OUT/IN OUT | Invalid declaration | Only put defaults on IN |
| Thinking passing NULL triggers default | Parameter receives NULL | Omit argument or handle NULL explicitly |
| Skipping a middle parameter in positional notation | Wrong positional mapping or invalid call | Use named notation |
| Placing positional after named | Call syntax error | Positional first, named after |
| Confusing => with := | Invalid call/assignment | => maps named argument, := assigns variable |
| Using data types out of sync with columns | Conversion/precision risks | Use %TYPE |
| Using NOCOPY while assuming atomic copy-out | Caller may see partial changes on exception | Only use when semantics are well understood |
| Unsynchronized package signature changes | Callers fail to compile or behavior changes | Update spec/body and test consumers |
| Using OUT instead of RETURN for every function | Hard-to-read API | Choose the appropriate return channel |

## 19. Practice Exercises

Run the exercises in a lab schema. Create tables or use permitted sample tables; do not update production data without approval.

### Exercise 1 — IN Parameter

Write a procedure accepting EMPLOYEE_ID IN, querying the employee name, and printing it. Try passing a literal, a variable, and a suitable expression.

### Exercise 2 — OUT Parameter

Write a procedure accepting EMPLOYEE_ID and returning SALARY via OUT. Call it from an anonymous block and print the received value.

### Exercise 3 — IN OUT

Write a procedure accepting an IN OUT NUMBER and increasing it by 10%. Call it with a variable; try passing a literal and explain why it is invalid.

### Exercise 4 — Comparing IN, OUT, IN OUT

Create three small procedures: the first only reads input; the second produces output; the third modifies the input value. Write calls demonstrating the difference.

### Exercise 5 — Default Parameter

Declare P_STATUS IN DEFAULT 'NEW'. Try omitting it, passing 'PAID', and passing NULL. Record all three outcomes.

### Exercise 6 — Default in the Middle of the List

Declare a procedure with three IN parameters where the second and third have defaults. Use named notation to omit the second parameter while passing the third.

### Exercise 7 — Positional and Named Notation

Call the same procedure using both styles. Reorder the named arguments and confirm the result is unchanged.

### Exercise 8 — OUT with NO_DATA_FOUND

Write a procedure with SELECT INTO for a customer. Test an existing ID and a non-existent ID; choose either to propagate the exception or return an OUT status, then explain the API contract.

### Exercise 9 — %TYPE and %ROWTYPE

Use %TYPE for ID/salary and %ROWTYPE for a customer record. Compare the degree of schema coupling.

### Exercise 10 — Package Specification

Declare a procedure with a default in a package specification and implement it in the body. Call it from an anonymous block using named notation.

### Exercise 11 — NOCOPY

Create a collection type and an IN OUT NOCOPY procedure that modifies a few elements and then raises a controlled exception. Observe the actual collection and discuss why callers should not assume atomic copy-out.

### Exercise 12 — API Design

Design a money-transfer procedure accepting source ID, destination ID, amount, and returning status. Determine each parameter's mode, sensible defaults, NULL handling, exceptions, and transaction ownership.

## 20. Parameter Design Checklist

- [ ] Identify which data is input, output, and input requiring transformation.
- [ ] Use IN for read-only input.
- [ ] Use OUT for results returned to the caller.
- [ ] Use IN OUT when receiving an initial value and returning a modified value.
- [ ] Declare defaults only for IN parameters.
- [ ] Understand that omitting a parameter uses its default; passing NULL still passes NULL.
- [ ] Place parameters with defaults at the end if simple positional calls are desired.
- [ ] Use named notation when skipping optional parameters or calling with many same-type arguments.
- [ ] Never place positional arguments after named arguments.
- [ ] Pass variables for OUT/IN OUT.
- [ ] Use %TYPE/%ROWTYPE when staying synchronized with schema structure is needed.
- [ ] Assign OUT on every normal termination path.
- [ ] Clearly define outputs when data is not found or an error occurs.
- [ ] Do not rely on OUT/IN OUT if an exception escapes the subprogram.
- [ ] Use NOCOPY only when partial-modification risks are understood and there is a measurable benefit.
- [ ] Keep signatures synchronized between package specification and body.
- [ ] Clearly define which procedure is responsible for COMMIT/ROLLBACK.
- [ ] Test positional calls, named calls, omitted defaults, NULL arguments, and exceptions.

## 21. Key Takeaways

- IN receives data for reading; OUT returns results; IN OUT receives an initial value and returns the transformed value.
- The default mode of a formal parameter is IN.
- IN parameters cannot be assigned inside a subprogram; OUT/IN OUT require a writable actual parameter.
- OUT does not use the actual's old value as input; assign outputs explicitly before normal completion.
- IN OUT is appropriate when logic needs to read and modify the exact value passed by the caller.
- Only IN parameters can declare default values.
- Omitting a parameter with a default uses the default; explicitly passing NULL does not trigger the default.
- Positional notation maps by declaration order; named notation maps by name and allows skipping optional parameters.
- When mixing notations, positional arguments must precede named arguments.
- %TYPE and %ROWTYPE keep parameter/record data types aligned with the schema.
- An exception escaping a subprogram means callers should not rely on OUT/IN OUT results; design a clear status/error contract.
- NOCOPY is a hint that can reduce copying of large data, but may expose partial changes to the caller upon exception.
- Functions use RETURN for the primary result; procedures with OUT are suited for multiple results or business actions.
- Public signatures in a package specification must stay synchronized with the package body and callers.
- Choose modes based on the data contract and transaction ownership, not out of habit.

### Oracle Documentation to Reference

- [Oracle Database PL/SQL Language Reference](https://docs.oracle.com/en/database/) — Subprogram parameters, parameter modes, default values, positional/named notation, and NOCOPY.
- [Oracle Database PL/SQL Language Fundamentals](https://docs.oracle.com/en/database/) — Data types, records, %TYPE, %ROWTYPE, and parameter passing.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/) — Package specification/body and subprogram interfaces.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/) — SQL-callable functions and RETURNING INTO.
- [Oracle Database Error Messages](https://docs.oracle.com/en/database/) — Errors related to compilation, argument mapping, and exceptions in PL/SQL.

Details of parameter passing, NOCOPY, data types, and restrictions on SQL-called functions may depend on the Oracle release. Consult the documentation for your exact version, compile the examples in a lab schema, and test successful calls, NULLs, default parameters, and exceptions.
