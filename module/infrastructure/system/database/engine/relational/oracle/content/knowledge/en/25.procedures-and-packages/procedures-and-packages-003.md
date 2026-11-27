# Overloading, Named Notation, and Positional Notation

In PL/SQL, **overloading** allows multiple subprograms to share the same name while having different parameter lists. When that name is called, Oracle determines which version to execute based on the number, order, and data types of the arguments matching the declarations.

PL/SQL also supports three ways to pass arguments:

- **Positional notation**: arguments are matched to parameters by their position in the declaration.
- **Named notation**: arguments are matched to parameters by formal parameter name, using the syntax `parameter_name => value`.
- **Mixed notation**: combines positional arguments at the beginning of the call with named arguments afterward.

These capabilities are commonly used in packages to build APIs with multiple ways to invoke them, support default values, and keep calls readable when subprograms have many parameters.

For example, a package can provide multiple ways to display values:

~~~sql
CREATE OR REPLACE PACKAGE display_api AS
    PROCEDURE show_value(p_value IN NUMBER);
    PROCEDURE show_value(p_value IN DATE);
    PROCEDURE show_value(p_value IN VARCHAR2);
END display_api;
/
~~~

The three procedures share the name SHOW_VALUE but accept three different data types. When called with an explicit NUMBER, DATE, or VARCHAR2, Oracle selects the corresponding overload.

This lesson covers the scope of overloading, signature distinction rules, how Oracle resolves calls, positional/named/mixed notation, default parameters, common errors, and how to design stable package APIs.

## 1. Subprograms and Parameter Signatures

A subprogram in PL/SQL is either a procedure or a function. A subprogram has:
- A name.
- A formal parameter list, if any.
- The data type and mode of each parameter.
- For a function, a return data type.
- A body that performs the work.

Example:

~~~sql
PROCEDURE calculate_total(
    p_quantity IN NUMBER,
    p_unit_price IN NUMBER,
    p_total OUT NUMBER
);
~~~

In the declaration above:
- CALCULATE_TOTAL is the procedure name.
- P_QUANTITY, P_UNIT_PRICE, and P_TOTAL are formal parameters.
- NUMBER is the data type.
- IN and OUT are parameter modes.

When calling a subprogram, the values or variables passed in are called actual arguments. Example:

~~~sql
calculate_total(2, 150, l_total);
~~~

The actual arguments 2, 150, and L_TOTAL are matched with the three formal parameters in order.

### 1.1. Signatures and Overloading

In the context of overloading, Oracle needs to distinguish same-named declarations by characteristics of their parameter lists. Factors that can make signatures distinct include:
- Number of parameters.
- Parameter order when data types differ at different positions.
- Parameter data types or data type families.

Example:

~~~sql
PROCEDURE find_record(p_id IN NUMBER);
PROCEDURE find_record(p_code IN VARCHAR2);
~~~

The two procedures have the same name but different parameter types, so they can be overloaded.

### 1.2. Overloading Is Commonly Declared in Packages

Packages are the typical place to publish multiple overloads under the same name:

~~~sql
CREATE OR REPLACE PACKAGE employee_api AS
    PROCEDURE find_employee(p_employee_id IN NUMBER);
    PROCEDURE find_employee(p_employee_code IN VARCHAR2);
END employee_api;
/
~~~

The package specification publishes the API to callers. The package body contains the corresponding implementations.

Overloading can also appear in other appropriate PL/SQL scopes such as local subprograms and object type methods. Do not design multiple standalone schema-level procedures differing only in parameters expecting them to coexist under one name; place overloads inside a package.

### 1.3. Public Overloads and Private Overloads

- Subprograms declared in the package specification are public and can be called by callers outside the package.
- Subprograms declared only in the package body are private and are only used internally within the package.
- Every overload intended for external callers must have a corresponding declaration in the specification.

The package body must implement all public overloads matching the exact parameter lists published.

## 2. Declaring and Implementing Overloads

Example of a package providing three ways to display a value depending on its data type:

~~~sql
CREATE OR REPLACE PACKAGE display_api AS
    PROCEDURE show_value(p_value IN NUMBER);
    PROCEDURE show_value(p_value IN DATE);
    PROCEDURE show_value(p_value IN VARCHAR2);
END display_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY display_api AS

    PROCEDURE show_value(p_value IN NUMBER) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'NUMBER: ' || TO_CHAR(p_value)
        );
    END show_value;

    PROCEDURE show_value(p_value IN DATE) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'DATE: ' || TO_CHAR(p_value, 'YYYY-MM-DD')
        );
    END show_value;

    PROCEDURE show_value(p_value IN VARCHAR2) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'TEXT: ' || p_value
        );
    END show_value;

END display_api;
/
~~~

Calling the overloads:

~~~sql
BEGIN
    display_api.show_value(125);
    display_api.show_value(DATE '2025-03-08');
    display_api.show_value('Oracle PL/SQL');
END;
/
~~~

Oracle selects the overload matching the type of the actual argument.

### 2.1. Overloading by Parameter Count

~~~sql
CREATE OR REPLACE PACKAGE log_api AS
    PROCEDURE write_log(p_message IN VARCHAR2);

    PROCEDURE write_log(
        p_message IN VARCHAR2,
        p_level IN PLS_INTEGER
    );
END log_api;
/
~~~

The two declarations have different parameter counts. Callers can log just a message or pass an additional severity level:

~~~sql
BEGIN
    log_api.write_log('Started');
    log_api.write_log('Connection failed', 3);
END;
/
~~~

In the package body, both versions must be implemented with parameter lists matching the specification.

### 2.2. Overloading by Parameter Order and Types

You can have two overloads accepting the same two types in different orders:

~~~sql
CREATE OR REPLACE PACKAGE conversion_api AS
    PROCEDURE convert_value(
        p_amount IN NUMBER,
        p_currency IN VARCHAR2
    );

    PROCEDURE convert_value(
        p_currency IN VARCHAR2,
        p_amount IN NUMBER
    );
END conversion_api;
/
~~~

Positional calls distinguish them by the order and types of actual arguments:

~~~sql
BEGIN
    conversion_api.convert_value(100, 'USD');
    conversion_api.convert_value('EUR', 250);
END;
/
~~~

In practice, two overloads with swapped parameter orders can easily cause confusion. Only use this pattern when both call forms have clear semantics; otherwise, choose distinct subprogram names or a cleaner API structure.

### 2.3. Overloading Functions

Functions can also be overloaded:

~~~sql
CREATE OR REPLACE PACKAGE format_api AS
    FUNCTION format_value(p_value IN NUMBER)
        RETURN VARCHAR2;

    FUNCTION format_value(p_value IN DATE)
        RETURN VARCHAR2;
END format_api;
/
~~~

Caller:

~~~sql
DECLARE
    l_number_text VARCHAR2(100);
    l_date_text   VARCHAR2(100);
BEGIN
    l_number_text := format_api.format_value(1250.5);
    l_date_text := format_api.format_value(DATE '2025-03-08');
END;
/
~~~

The two functions are distinguished by their input parameter types. A function's return type alone is not enough to create a new overload.

## 3. Differences Insufficient for Overloading

Not every difference in declaration makes two subprograms valid overloads.

### 3.1. Differing Only in Parameter Names

You cannot create two overloads solely because formal parameters have different names:

~~~sql
-- Not two valid overloads based on parameter names alone.
PROCEDURE process_value(p_number IN NUMBER);
PROCEDURE process_value(p_amount IN NUMBER);
~~~

Both have the same single NUMBER parameter. Renaming P_NUMBER to P_AMOUNT does not create a distinct signature.

### 3.2. Differing Only in Parameter Mode

IN, OUT, and IN OUT do not distinguish two overloads.

~~~sql
-- Cannot overload using IN and OUT alone.
PROCEDURE get_value(p_value IN NUMBER);
PROCEDURE get_value(p_value OUT NUMBER);
~~~

The mode defines how data is passed between caller and subprogram; it does not create an independent overload version.

### 3.3. Differing Only in Subtype

Subtypes sharing the same base type are not necessarily distinguishable for overloading.

For example, INTEGER and SMALLINT are subtypes of NUMBER. You cannot rely on that difference alone to create two equivalent overloads:

~~~sql
-- Not two distinguishable overload signatures.
PROCEDURE process_number(p_value IN INTEGER);
PROCEDURE process_number(p_value IN SMALLINT);
~~~

Similarly, declaring a user-defined subtype over NUMBER does not make it an independent data type family for overloading purposes.

### 3.4. Differing Only in Return Type

You cannot create two functions with the same name and same parameter list differing only in RETURN type:

~~~sql
-- Cannot overload using RETURN type alone.
FUNCTION get_value(p_id IN NUMBER) RETURN NUMBER;
FUNCTION get_value(p_id IN NUMBER) RETURN VARCHAR2;
~~~

When calling GET_VALUE(10), Oracle cannot select the function solely from the receiving variable's type. Change the input parameters in a valid distinguishing way or use a different function name.

### 3.5. Differing Only in Default Value

A DEFAULT value does not distinguish signatures:

~~~sql
-- Cannot create two overloads using different DEFAULT values alone.
PROCEDURE search_data(p_status IN VARCHAR2 DEFAULT 'NEW');
PROCEDURE search_data(p_status IN VARCHAR2 DEFAULT 'ALL');
~~~

The two declarations still have the same name and the same parameter list in terms of types/counts. Use a single procedure with a clear default rule or a different procedure name.

## 4. Data Types and Overload Distinguishability

Oracle must be able to match an actual argument unambiguously to one overload. Data types belonging to the same family or differing only by subtype may not be distinguishable.

Clear example:

~~~sql
PROCEDURE display(p_value IN NUMBER);
PROCEDURE display(p_value IN DATE);
PROCEDURE display(p_value IN VARCHAR2);
~~~

NUMBER, DATE, and VARCHAR2 are distinct enough to demonstrate three overloads.

Do not try to create multiple overloads differing only in VARCHAR2 length, NUMBER precision/scale, or equivalent subtypes. Length/precision attributes do not automatically create an independent type.

### 4.1. Anchored Data Types Do Not Create Separate Types

~~~sql
PROCEDURE find_employee(
    p_id IN employees.employee_id%TYPE
);
~~~

%TYPE takes the data type of the referenced column. If EMPLOYEE_ID has type NUMBER, this parameter is essentially still NUMBER for overload resolution; it does not become a new type just by using %TYPE.

Similarly, two columns from different tables both declared as NUMBER do not become two separate type families.

### 4.2. Implicit Conversion Can Make Calls Hard to Resolve

Oracle has implicit type conversion rules in PL/SQL. When multiple overloads exist and an actual argument lacks an explicit type, implicit conversion can make the call ambiguous or match differently than expected.

Always:
- Use variables with explicit data types.
- Use typed literals such as DATE literals.
- Use CAST when type clarification is needed.
- Avoid relying on string contents for Oracle to guess intent.
- Do not create nearly identical overloads just to rely on implicit conversion.

## 5. How Oracle Resolves Overloads

When compiling a PL/SQL call, Oracle inspects accessible same-named declarations and searches for a subprogram matching the actual arguments.

Key factors:
1. Subprogram name and scope/package.
2. Number of actual arguments.
3. Argument mapping by position or name.
4. Data types of actual arguments.
5. Parameter modes and variable passability for OUT/IN OUT.
6. Default values of omitted formal parameters.
7. PL/SQL overloading and type conversion rules.

The outcome must be a single overload that can be selected unambiguously. If no overload matches, the call is invalid. If multiple overloads match and Oracle cannot distinguish them, the call is ambiguous.

### 5.1. A Single Matching Overload

Given:

~~~sql
PROCEDURE find_employee(p_id IN NUMBER);
PROCEDURE find_employee(p_code IN VARCHAR2);
~~~

The calls:

~~~sql
find_employee(101);
find_employee('EMP-101');
~~~

have actual arguments with matching types, so Oracle can select the appropriate version.

### 5.2. No Matching Overload

If only:

~~~sql
PROCEDURE find_employee(p_id IN NUMBER);
~~~

exists and the caller passes an incompatible record or the wrong number of arguments, Oracle cannot find a matching signature. A common error is PLS-00306:

~~~text
PLS-00306: wrong number or types of arguments in call
~~~

Check the count, order, data types, parameter names, and modes of the actual arguments.

### 5.3. Multiple Matching Overloads

If multiple declarations can accept the actual arguments, Oracle may report PLS-00307:

~~~text
PLS-00307: too many declarations of ... match this call
~~~

A classic example is passing an untyped NULL to a name overloaded for multiple types:

~~~sql
-- Can be ambiguous if both overloads are visible.
display_api.show_value(NULL);
~~~

NULL by itself does not indicate whether the caller wants NUMBER, DATE, or VARCHAR2. Specify the type explicitly:

~~~sql
BEGIN
    display_api.show_value(CAST(NULL AS NUMBER));
    display_api.show_value(CAST(NULL AS VARCHAR2(100)));
END;
/
~~~

Or declare a typed variable:

~~~sql
DECLARE
    l_value NUMBER := NULL;
BEGIN
    display_api.show_value(l_value);
END;
/
~~~

### 5.4. Typed Literals Make Calls Unambiguous

DATE literal:

~~~sql
display_api.show_value(DATE '2025-03-08');
~~~

String:

~~~sql
display_api.show_value('2025-03-08');
~~~

These two actual arguments have different data types. A string that looks like a date is still VARCHAR2; Oracle should not be asked to guess business intent from string contents.

## 6. Positional Notation

Positional notation matches actual arguments to formal parameters in exact declaration order.

Suppose a package:

~~~sql
CREATE OR REPLACE PACKAGE order_api AS
    PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_order_date IN DATE,
        p_status IN VARCHAR2
    );
END order_api;
/
~~~

Positional call:

~~~sql
BEGIN
    order_api.create_order(
        100,
        DATE '2025-03-08',
        'NEW'
    );
END;
/
~~~

Mapping:

| Position | Formal parameter | Actual argument |
| ---: | --- | --- |
| 1 | P_CUSTOMER_ID | 100 |
| 2 | P_ORDER_DATE | DATE '2025-03-08' |
| 3 | P_STATUS | 'NEW' |

### 6.1. Advantages of Positional Notation

- Concise for procedures with few parameters.
- Easy to read when parameter order is simple and familiar.
- Well suited for small functions with stable parameter lists.
- Does not depend on formal parameter names at the call site.

### 6.2. Risks When Multiple Parameters Share the Same Type

~~~sql
PROCEDURE transfer(
    p_from_account IN NUMBER,
    p_to_account IN NUMBER,
    p_amount IN NUMBER
);
~~~

The call:

~~~sql
transfer(100, 200, 500);
~~~

is type-valid, but readers can hardly tell that 100 is the source account, 200 is the destination account, and 500 is the amount without checking the declaration.

If two same-type arguments are accidentally swapped:

~~~sql
transfer(200, 100, 500);
~~~

the compiler will still accept it. This is a logic bug rather than a data type error. Named notation helps reduce this risk.

### 6.3. Changing Parameter Order Can Break Callers

If a package API reorders parameters of the same type, existing positional calls may still compile while taking on a completely different meaning.

Original example:

~~~sql
PROCEDURE transfer(
    p_from_account IN NUMBER,
    p_to_account IN NUMBER,
    p_amount IN NUMBER
);
~~~

If changed to:

~~~sql
PROCEDURE transfer(
    p_amount IN NUMBER,
    p_from_account IN NUMBER,
    p_to_account IN NUMBER
);
~~~

An existing caller passing three NUMBERs will still match types, but the data will be mapped to the wrong semantics. Changing public parameter order is an API change that must be managed carefully.

## 7. Named Notation

Named notation matches an actual argument to a formal parameter by name. Syntax:

~~~sql
subprogram_name(
    formal_parameter_name => actual_argument
);
~~~

Example:

~~~sql
BEGIN
    order_api.create_order(
        p_customer_id => 100,
        p_order_date  => DATE '2025-03-08',
        p_status      => 'NEW'
    );
END;
/
~~~

The order of named arguments does not need to match the declaration order. Oracle maps them by formal parameter name.

### 7.1. Easier-to-Read Calls

With the money-transfer procedure:

~~~sql
account_api.transfer(
    p_from_account => 100,
    p_to_account   => 200,
    p_amount       => 500
);
~~~

Readers immediately see the meaning of each value. This is a clear advantage when multiple parameters share the same data type.

### 7.2. Named Notation Prevents Swapping Same-Type Parameters

Suppose:

~~~sql
PROCEDURE create_range(
    p_start_date IN DATE,
    p_end_date IN DATE
);
~~~

A named call:

~~~sql
create_range(
    p_end_date => DATE '2025-12-31',
    p_start_date => DATE '2025-01-01'
);
~~~

is readable and independent of listing order at the call site. If start date and end date were swapped in positional notation, the compiler could not detect it because both are DATE.

### 7.3. Named Notation Requires Exact Names

The argument name must match the formal parameter declared in the selected subprogram. Names are case-insensitive under standard identifier rules, unless the identifier was declared quoted and case-sensitive.

For example, if the formal parameter is P_CUSTOMER_ID, the call uses `P_CUSTOMER_ID => ...`; a nonexistent name can prevent the call from matching.

### 7.4. Do Not Pass the Same Parameter Twice

A formal parameter cannot be assigned two actual arguments in the same call:

~~~sql
-- Invalid: P_CUSTOMER_ID is supplied twice.
order_api.create_order(
    p_customer_id => 100,
    p_customer_id => 200
);
~~~

Each formal parameter can be supplied at most once; required parameters must have an actual argument.

## 8. Mixed Notation

Mixed notation combines positional and named notation in the same call. Rule: **positional arguments must precede named arguments**.

Example:

~~~sql
order_api.create_order(
    100,
    p_status => 'NEW',
    p_order_date => DATE '2025-03-08'
);
~~~

The first positional argument is matched to P_CUSTOMER_ID. The remaining two arguments are mapped by name.

### 8.1. Do Not Place Positional After Named

The following call is invalid:

~~~sql
-- Invalid: positional argument appears after named argument.
order_api.create_order(
    p_customer_id => 100,
    DATE '2025-03-08',
    'NEW'
);
~~~

Once you begin using named notation, subsequent arguments must also be named.

### 8.2. When to Use Mixed Notation?

Mixed notation is useful when:
- Leading parameters are very obvious and short.
- Trailing parameters are numerous or easy to confuse.
- You want to keep part of the call compact while still clarifying important values.

However, for long APIs, using named notation for all arguments is usually more readable and less error-prone.

## 9. Default Parameters and Omitting Arguments

PL/SQL allows declaring default values for IN parameters. If the caller does not provide an actual argument for a parameter with a default, the subprogram uses the default value.

Example:

~~~sql
CREATE OR REPLACE PACKAGE search_api AS
    PROCEDURE search_orders(
        p_customer_id IN NUMBER,
        p_status IN VARCHAR2 DEFAULT 'NEW',
        p_from_date IN DATE DEFAULT NULL
    );
END search_api;
/
~~~

You can call it with all parameters:

~~~sql
search_api.search_orders(
    100,
    'CLOSED',
    DATE '2025-01-01'
);
~~~

Or omit trailing parameters with defaults using positional notation:

~~~sql
search_api.search_orders(100);
~~~

The call above uses CUSTOMER_ID=100, STATUS='NEW', and FROM_DATE=NULL.

### 9.1. Omitting Trailing Parameters with Positional Notation

Positional notation can omit parameters with defaults at the end of the list. A caller cannot skip a middle parameter and pass a later parameter positionally without supplying the skipped position.

Suppose:

~~~sql
PROCEDURE search_orders(
    p_customer_id IN NUMBER,
    p_status IN VARCHAR2 DEFAULT 'NEW',
    p_from_date IN DATE DEFAULT NULL
);
~~~

There is no simple positional way to omit P_STATUS while passing P_FROM_DATE; passing two positional arguments maps the second argument to P_STATUS.

### 9.2. Named Notation Can Skip Middle Parameters

Using named notation:

~~~sql
search_api.search_orders(
    p_customer_id => 100,
    p_from_date => DATE '2025-01-01'
);
~~~

P_STATUS is omitted and uses the default NEW. P_FROM_DATE is supplied by name.

This is a key advantage of named notation for subprograms with many optional parameters.

### 9.3. Only IN Parameters Have Defaults

Default values apply to IN parameters. Do not declare defaults for OUT or IN OUT parameters. If the caller needs to receive an OUT value, a suitable variable must be supplied in the call.

### 9.4. Default Values Do Not Distinguish Overloads

Do not use two different defaults to try creating two versions with the same signature. Treat a default as a calling rule for one declaration, not as an overload identifier.

### 9.5. Defaults Can Make Overload Calls Ambiguous

Suppose a package has:

~~~sql
PROCEDURE lookup(p_id IN NUMBER);

PROCEDURE lookup(
    p_id IN NUMBER,
    p_mode IN VARCHAR2 DEFAULT 'FULL'
);
~~~

Both overloads can be considered when the caller passes only one NUMBER:

~~~sql
lookup(100);
~~~

The call can be ambiguous because the second overload can also be called after applying the default for P_MODE. Avoid designing such overlapping overloads; if needed, pass enough arguments to disambiguate or rename the API.

## 10. Named Notation and Overloading

Named notation can help distinguish overloads that already have different signatures, because each overload can publish different formal parameter names.

Example:

~~~sql
CREATE OR REPLACE PACKAGE employee_lookup AS
    PROCEDURE find_employee(
        p_employee_id IN NUMBER
    );

    PROCEDURE find_employee(
        p_employee_code IN VARCHAR2
    );
END employee_lookup;
/
~~~

Calls:

~~~sql
BEGIN
    employee_lookup.find_employee(
        p_employee_id => 101
    );

    employee_lookup.find_employee(
        p_employee_code => 'E-101'
    );
END;
/
~~~

Parameter names help calls clearly express the intended lookup form.

### 10.1. Parameter Names Do Not Create Overloads by Themselves

Two declarations with the same name, same types, and same parameter count do not become two valid overloads merely because formal parameter names differ. Named notation only maps a call to an existing valid declaration; it does not replace signature rules.

### 10.2. Identical Parameter Names May Not Help Disambiguate

If two overloads share the same formal parameter names with different type orders, named notation may still match both depending on the mapping. Do not assume that using parameter names will always resolve ambiguity.

When disambiguation is needed:
- Use actual arguments with explicit data types.
- Use distinct formal parameter names if the overloads already declare different names.
- Design non-overlapping signatures.
- Use different subprogram names if the two behaviors are not genuinely the same API.

### 10.3. Renaming Formal Parameters Can Affect Callers

With positional notation, callers do not depend on formal parameter names. With named notation, callers depend on those names.

Example existing caller:

~~~sql
employee_lookup.find_employee(
    p_employee_code => 'E-101'
);
~~~

If the package renames P_EMPLOYEE_CODE to P_CODE, callers using the old named notation may no longer compile. Therefore, parameter names in a package specification are part of the public API.

## 11. OUT and IN OUT with Both Notation Styles

Both positional and named notation can pass OUT/IN OUT parameters. The corresponding actual argument must be a variable capable of receiving a value, not a literal or immutable expression.

Example:

~~~sql
CREATE OR REPLACE PACKAGE calculation_api AS
    PROCEDURE calculate_total(
        p_quantity IN NUMBER,
        p_unit_price IN NUMBER,
        p_total OUT NUMBER
    );
END calculation_api;
/
~~~

Positional call:

~~~sql
DECLARE
    l_total NUMBER;
BEGIN
    calculation_api.calculate_total(3, 250, l_total);
    DBMS_OUTPUT.PUT_LINE(l_total);
END;
/
~~~

Named call:

~~~sql
DECLARE
    l_total NUMBER;
BEGIN
    calculation_api.calculate_total(
        p_unit_price => 250,
        p_total => l_total,
        p_quantity => 3
    );
    DBMS_OUTPUT.PUT_LINE(l_total);
END;
/
~~~

You cannot pass a literal as an OUT actual argument:

~~~sql
-- Invalid: a literal is not a variable that can receive a value.
calculation_api.calculate_total(3, 250, 0);
~~~

### 11.1. Mode Cannot Be Used to Overload

If two procedures differ only by IN and OUT, Oracle does not treat them as two distinct overloads. Mode is a data-passing rule, not a way to create separate signatures.

### 11.2. IN OUT Requires an Input and Output Variable

An IN OUT actual argument supplies an initial value and receives the value after the subprogram completes. The caller must pass a variable with a compatible data type.

~~~sql
PROCEDURE add_fee(p_amount IN OUT NUMBER);
~~~

Named notation:

~~~sql
add_fee(p_amount => l_amount);
~~~

## 12. Overloading in Package Specification and Body

The package specification is the public contract. Every public overload must be explicitly declared:

~~~sql
CREATE OR REPLACE PACKAGE payment_api AS
    PROCEDURE pay(
        p_order_id IN NUMBER,
        p_amount IN NUMBER
    );

    PROCEDURE pay(
        p_order_code IN VARCHAR2,
        p_amount IN NUMBER
    );

    FUNCTION get_status(
        p_order_id IN NUMBER
    ) RETURN VARCHAR2;

    FUNCTION get_status(
        p_order_code IN VARCHAR2
    ) RETURN VARCHAR2;
END payment_api;
/
~~~

The package body implements each declaration:

~~~sql
CREATE OR REPLACE PACKAGE BODY payment_api AS

    PROCEDURE pay(
        p_order_id IN NUMBER,
        p_amount IN NUMBER
    ) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'Pay by order id: ' || p_order_id ||
            ', amount=' || p_amount
        );
    END pay;

    PROCEDURE pay(
        p_order_code IN VARCHAR2,
        p_amount IN NUMBER
    ) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'Pay by order code: ' || p_order_code ||
            ', amount=' || p_amount
        );
    END pay;

    FUNCTION get_status(
        p_order_id IN NUMBER
    ) RETURN VARCHAR2 IS
    BEGIN
        RETURN 'STATUS_BY_ID_' || p_order_id;
    END get_status;

    FUNCTION get_status(
        p_order_code IN VARCHAR2
    ) RETURN VARCHAR2 IS
    BEGIN
        RETURN 'STATUS_BY_CODE_' || p_order_code;
    END get_status;

END payment_api;
/
~~~

Calling:

~~~sql
BEGIN
    payment_api.pay(1001, 500);
    payment_api.pay('ORD-A100', 500);

    DBMS_OUTPUT.PUT_LINE(payment_api.get_status(1001));
    DBMS_OUTPUT.PUT_LINE(payment_api.get_status('ORD-A100'));
END;
/
~~~

### 12.1. Signatures in the Body Must Match the Specification

When defining an overload in the package body, the parameter list must correspond to the specification declaration in order, types, and modes. If an implementation is missing or mismatched, the package will not compile cleanly.

When modifying an API:
- Update the specification.
- Update the corresponding body.
- Compile the package.
- Check USER_ERRORS or ALL_ERRORS.
- Check callers that depend on the package.

### 12.2. Private Overloads in the Package Body

A package body can declare private subprograms for internal support. External callers cannot call private overloads directly. If an internal name matches a public subprogram, review scoping and name resolution rules; use clear helper names to avoid making code hard to follow.

## 13. Common Errors When Overloading and Calling Subprograms

| Error | Common Cause | How to Handle |
| --- | --- | --- |
| PLS-00306 | Wrong number or types of actual arguments | Check signature, order, names, and data types |
| PLS-00307 | Multiple overloads match equally | Use explicit types, CAST, or redesign signatures |
| PLS-00302 | Component is not declared in the package/type | Check package specification and spelling |
| PLS-00323 | Subprogram declared in package spec is not defined in body with matching signature | Add implementation with matching signature |
| PLS-00307 when passing NULL | NULL does not indicate intended type | CAST NULL or use a typed variable |
| Named call fails to compile | Formal parameter name mismatch | Use exact name from specification |
| Positional call runs with wrong meaning | Same-type parameters passed in wrong positions | Use named notation |
| Overload fails to compile | Differing only by parameter name/mode/subtype/return type | Create a valid signature distinction |
| Single-argument call is ambiguous | Multiple overloads have default parameters | Avoid overlapping signatures or pass extra distinguishing arguments |
| Package body invalid | Implementation does not match specification | Synchronize order, types, modes, and subprogram names |

### 13.1. Viewing Package Compilation Errors

In the current schema:

~~~sql
SELECT name,
       type,
       line,
       position,
       text
FROM user_errors
WHERE name = 'PAYMENT_API'
ORDER BY sequence;
~~~

If the package belongs to another schema and you have privileges, use ALL_ERRORS or DBA_ERRORS as appropriate.

### 13.2. Viewing Package Declarations

You can inspect the source:

~~~sql
SELECT line, text
FROM user_source
WHERE name = 'PAYMENT_API'
  AND type IN ('PACKAGE', 'PACKAGE BODY')
ORDER BY type, line;
~~~

Compare specification and body to determine which overloads have been published and implemented.

## 14. Designing Easy-to-Call Package APIs

Overloading lets callers use one name for variants with the same purpose, but too many overloads can make calls hard to resolve.

### 14.1. Only Overload When Variants Share the Same Meaning

Reasonable example:

~~~sql
PROCEDURE find_customer(p_customer_id IN NUMBER);
PROCEDURE find_customer(p_customer_code IN VARCHAR2);
~~~

Both are customer lookup operations differing only in identifier type.

A confusing example would be using the same name PROCESS for unrelated behaviors. If callers have to memorize a long list of implicit rules, separate names may be better.

### 14.2. Avoid Overloads That Are Too Similar

Avoid creating overloads that:
- Differ only by subtype.
- Differ only in parameter mode.
- Have multiple defaults making single-argument calls ambiguous.
- Rely on implicit conversion for selection.
- Have multiple same-type parameters in different orders without clear meaning.

### 14.3. Use Named Notation for Multi-Parameter APIs

With a procedure:

~~~sql
PROCEDURE create_invoice(
    p_customer_id IN NUMBER,
    p_invoice_date IN DATE,
    p_currency_code IN VARCHAR2,
    p_include_tax IN BOOLEAN DEFAULT TRUE,
    p_note IN VARCHAR2 DEFAULT NULL
);
~~~

Call:

~~~sql
invoice_api.create_invoice(
    p_customer_id => 100,
    p_invoice_date => DATE '2025-03-08',
    p_currency_code => 'VND',
    p_note => 'March invoice'
);
~~~

P_INCLUDE_TAX uses the default TRUE. The caller does not need to fill placeholders for middle parameters.

### 14.4. Keep Parameter Names Stable

If a package specification serves as an API for multiple applications, treat formal parameter names as part of the contract since callers may use named notation. Renaming parameters can break caller source code even when data types and parameter order do not change.

### 14.5. Avoid Overloads Based on Convertible Strings

If one overload accepts NUMBER and another accepts VARCHAR2, require callers to pass the exact data type. Do not rely on the string '100' being convertible to NUMBER in some contexts; that couples code to implicit conversion and can break when NLS settings or data types change.

## 15. Complete Example: Order Lookup and Creation Package

Create a package with two order lookup overloads and an order creation procedure with a default parameter.

### 15.1. Package Specification

~~~sql
CREATE OR REPLACE PACKAGE order_service AS
    PROCEDURE find_order(
        p_order_id IN NUMBER
    );

    PROCEDURE find_order(
        p_order_code IN VARCHAR2
    );

    PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_order_date IN DATE,
        p_status IN VARCHAR2 DEFAULT 'NEW'
    );
END order_service;
/
~~~

### 15.2. Illustrative Package Body

~~~sql
CREATE OR REPLACE PACKAGE BODY order_service AS

    PROCEDURE find_order(
        p_order_id IN NUMBER
    ) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'Find by numeric id: ' || p_order_id
        );
    END find_order;

    PROCEDURE find_order(
        p_order_code IN VARCHAR2
    ) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'Find by code: ' || p_order_code
        );
    END find_order;

    PROCEDURE create_order(
        p_customer_id IN NUMBER,
        p_order_date IN DATE,
        p_status IN VARCHAR2 DEFAULT 'NEW'
    ) IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE(
            'Customer=' || p_customer_id ||
            ', date=' || TO_CHAR(p_order_date, 'YYYY-MM-DD') ||
            ', status=' || p_status
        );
    END create_order;

END order_service;
/
~~~

This is an illustrative API example; a production package would perform actual SELECT/INSERT operations and manage transactions according to business boundaries.

### 15.3. Calling Overloads with Positional Notation

~~~sql
BEGIN
    order_service.find_order(1001);
    order_service.find_order('ORD-2025-001');
END;
/
~~~

### 15.4. Calling Overloads with Named Notation

~~~sql
BEGIN
    order_service.find_order(
        p_order_id => 1001
    );

    order_service.find_order(
        p_order_code => 'ORD-2025-001'
    );
END;
/
~~~

### 15.5. Calling a Procedure with Defaults Using Positional Notation

~~~sql
BEGIN
    order_service.create_order(
        100,
        DATE '2025-03-08'
    );
END;
/
~~~

P_STATUS uses the default value NEW.

### 15.6. Calling a Procedure with Defaults Using Named Notation

~~~sql
BEGIN
    order_service.create_order(
        p_status => 'PENDING',
        p_customer_id => 100,
        p_order_date => DATE '2025-03-08'
    );
END;
/
~~~

The order of named arguments can be freely rearranged.

### 15.7. Calling with Mixed Notation

~~~sql
BEGIN
    order_service.create_order(
        100,
        p_status => 'PENDING',
        p_order_date => DATE '2025-03-08'
    );
END;
/
~~~

The first positional argument maps to P_CUSTOMER_ID; the remaining arguments map by name.

## 16. Workflow for Resolving Ambiguous Calls

When encountering PLS-00307 or a hard-to-read overload call:

1. Find all overloads with the same name in the package specification and current scope.
2. Record the number and order of formal parameters.
3. Record the data type and mode of each parameter.
4. Check whether actual arguments contain untyped literals such as NULL.
5. Check whether default parameters cause multiple overloads to match.
6. Check implicit conversions.
7. Verify whether named arguments match formal parameter names of the intended overload.
8. Use CAST or explicitly typed variables to eliminate ambiguity.
9. If signatures overlap, revise the API so callers can distinguish them clearly.
10. Recompile the package and check USER_ERRORS.

Example from an ambiguous call:

~~~sql
display_api.show_value(NULL);
~~~

to a typed call:

~~~sql
display_api.show_value(CAST(NULL AS NUMBER));
~~~

Or using a variable:

~~~sql
DECLARE
    l_value DATE := NULL;
BEGIN
    display_api.show_value(l_value);
END;
/
~~~

If ambiguity is caused by default parameters, CAST may not be enough; pass additional arguments or change the overload design.

## 17. Common Misconceptions

**Overloading means creating multiple procedures with the same name regardless of parameters.** Incorrect. Declarations must have signature differences that Oracle can distinguish.

**Renaming formal parameters alone creates a new overload.** Incorrect. Parameter names are not sufficient to distinguish signatures.

**IN and OUT create two different overloads.** Incorrect. Parameter mode is not an overload differentiator.

**INTEGER and SMALLINT are always two independent types for overloading.** Incorrect. They are subtypes of the NUMBER family and cannot create overloads based on subtype difference alone.

**You can overload functions by changing only the RETURN type.** Incorrect. The parameter list must provide a valid distinction.

**Different DEFAULT values turn two declarations into two overloads.** Incorrect. Defaults are not criteria for creating a new signature.

**Positional notation is always easier to read.** Incorrect. Multiple parameters of the same type can be swapped without the compiler catching it.

**Named notation allows writing arguments in any order and mixing freely.** Named arguments can be reordered, but positional arguments must precede named arguments.

**Named notation always resolves every ambiguity.** Incorrect. If multiple overloads still match names and types after mapping, the call can remain ambiguous.

**You can skip a middle parameter in positional notation and still pass later parameters.** Incorrect. Use named notation to skip IN parameters with defaults.

**An OUT parameter can accept a literal.** Incorrect. OUT/IN OUT requires a suitable actual variable.

**NULL always selects the overload with the most common type.** Incorrect. Untyped NULL can match multiple overloads; use CAST or a typed variable.

**Renaming parameters in a package specification does not affect callers.** Incorrect if callers use named notation.

**A public overload only needs to exist in the package body.** Incorrect. External callers can only call subprograms published in the package specification.

**Every PLS-00307 error is caused by a missing CAST.** Incorrect. It can be caused by default parameters, overlapping signatures, or insufficient distinction among named arguments.

## 18. Self-Study Exercises

1. Create a package with a SHOW_VALUE procedure accepting NUMBER and VARCHAR2.
2. Add an overload accepting DATE and call all three versions.
3. Create two FIND_EMPLOYEE overloads accepting EMPLOYEE_ID NUMBER and EMPLOYEE_CODE VARCHAR2.
4. Explain why merely renaming P_ID to P_CODE does not create a new overload if the data type does not change.
5. Try creating two overloads differing only in IN and OUT. Identify the compilation error.
6. Why should INTEGER and SMALLINT not be used to create two separate overloads?
7. Write two functions with the same name and same parameters but different RETURN types. Explain why it is invalid.
8. Create overloads differing by parameter count.
9. Create overloads with two parameters, DATE and NUMBER, in two different orders.
10. Call both overloads from the previous exercise using positional notation.
11. Write a named notation call for a procedure with three parameters.
12. Write a mixed notation call with one leading positional argument and two trailing named arguments.
13. Write an invalid call containing a positional argument after a named argument and explain why.
14. Create a procedure with two IN parameters both of type DATE. Use named notation to avoid swapping start/end dates.
15. Create a procedure with parameter P_STATUS defaulting to NEW and call it without passing that parameter.
16. Skip a middle default parameter using named notation.
17. Why can positional notation not skip a middle parameter and still pass the next parameter?
18. Create a one-parameter overload and a two-parameter overload where the second parameter has a DEFAULT. Predict whether a one-argument call will be ambiguous.
19. Call an overload with NULL and resolve PLS-00307 using CAST.
20. Declare a NULL DATE variable and use it to select the DATE overload.
21. Explain why formal parameter names can be part of the public API.
22. Create a package specification with two overloads where the body defines only one. Inspect USER_ERRORS.
23. Create a package with public overloads and private helpers.
24. Write overloaded NUMBER/DATE functions returning VARCHAR2 and call them with explicitly typed variables.
25. Create a procedure with an OUT parameter and call it using positional notation.
26. Call the OUT-parameter procedure using named notation.
27. Why can a literal not be passed to an OUT parameter?
28. Distinguish PLS-00306 and PLS-00307.
29. Design a package API to find customers by ID, email, or external code without ambiguous calls.
30. Inspect a package with multiple overloads and build a formal/actual argument mapping table for positional, named, and mixed calls.

**Overloading allows one subprogram name to represent multiple distinguishable parameter signatures; positional notation matches arguments by order, while named notation matches by formal parameter name and makes multi-parameter calls easier to read.** Default values allow omitting IN parameters, but can cause overloads to overlap and trigger ambiguity. Design clear signatures, use explicit data types when needed, and keep public parameter names stable so package APIs remain easy to call and maintain.
