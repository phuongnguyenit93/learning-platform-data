# SQL Macros and Usage Conditions by Release/Update

SQL macros are a mechanism that encapsulates part of a SQL statement into a parameterized component, which can then be used directly inside the calling SQL statement. Instead of writing a PL/SQL function that executes per row and returns a value, a macro produces a SQL expression or query expression that Oracle expands into the main statement.

SQL macros are useful when multiple queries repeat the same calculation, filter, join, or query structure. Macros help standardize logic, accept parameters, and let the optimizer see the expanded SQL. However, macro capabilities depend heavily on the Oracle version and Release Update (RU). In particular, distinguish between:

- Oracle Database 19c supports table SQL macros; declared as a PL/SQL function with SQL_MACRO and usable only in FROM.
- Oracle Database 21c supports both table macros and scalar macros via SQL_MACRO(TABLE) or SQL_MACRO(SCALAR).
- 23ai releases have changes by RU. Oracle announced that release 23.26.4 allows using macros in the WITH clause; do not extrapolate this feature to every 23ai RU.
- Oracle AI Database 26ai adds native SQL syntax CREATE MACRO, defining a SQL expression/query directly instead of returning SQL text from a PL/SQL function.

An application may run on 19c yet fail to run scalar macro or CREATE MACRO examples taken from 21c/26ai documentation. Therefore, before choosing syntax, identify the exact database release, RU, service/PDB, and RAC environment.

## 1. What Problem Do SQL Macros Solve?

A regular view encapsulates a query for reuse:

~~~sql
CREATE OR REPLACE VIEW department_totals_v AS
SELECT department_id,
       COUNT(*) AS employee_count,
       SUM(salary) AS total_salary
FROM employees
GROUP BY department_id;
~~~

Views avoid rewriting GROUP BY, but views do not accept parameters the way functions do. If a query wants to sum from a specific hire date, you may have to filter in an outer query or rewrite the logic. For complex queries with analytic functions, grouping, or multiple conditional branches, placing the filter at the right layer can matter to the result.

SQL macros allow defining parameterized queries:

~~~sql
SELECT *
FROM employees_hired_since(DATE '2025-01-01');
~~~

The macro name is used in FROM like a table expression. The macro expands into the corresponding query, with parameters injected into the SQL expression.

Scalar macros solve a different need: reusing calculated expressions:

~~~sql
SELECT order_id,
       net_amount(gross_amount, discount_rate) AS amount_after_discount
FROM orders;
~~~

In versions supporting scalar macros, net_amount can expand into a SQL expression for the optimizer to process along with the query.

### 1.1 Macros Are Not Row-by-Row Data-Returning Functions

Distinguish the mechanisms:

| Mechanism | Result/Behavior | Typical Usage Location |
|---|---|---|
| View | A stored query in the database | FROM |
| SQL table macro | Query expression expanded into the calling SQL | FROM; some newer releases allow macros in WITH |
| SQL scalar macro | SQL expression expanded into the calling SQL | SELECT, WHERE, GROUP BY, HAVING, ORDER BY depending on release |
| Regular PL/SQL function | Value computed and returned by PL/SQL | SQL expressions if types and privileges permit |
| Pipelined table function | PL/SQL generates and emits rows through a pipeline | FROM |
| Polymorphic table function | Output table shape/row behavior controlled via PL/SQL interface | FROM |
| Inline view / CTE | Subquery written directly in the SQL statement | FROM / WITH |

SQL macros do not read rows one by one and return them via PL/SQL. The macro function is invoked to produce SQL text; Oracle expands that SQL fragment and executes the query after parsing/optimizing. Thus, macros generally avoid per-row SQL-to-PL/SQL context switches unlike regular PL/SQL functions.

This does not guarantee every macro is faster. The expanded query can still suffer from large joins, poor cardinality estimates, non-sargable predicates, bind sensitivity, or suboptimal execution plans. Measure execution plans and runtime statistics.

## 2. Lifecycle of a Function-Based SQL Macro

In the PL/SQL-function-based SQL_MACRO model, the general flow is:

~~~text
Application sends SQL statement
        |
        v
Oracle parses SQL statement
        |
        v
Recognizes SQL macro call
        |
        v
Runs macro body to generate SQL text
        |
        v
Expands parameters into SQL expression/query
        |
        v
Parses and optimizes expanded SQL
        |
        v
Executes SQL and returns results
~~~

The macro function is typically processed during the parse/hard-parse phase to generate SQL text. It is not called as a PL/SQL computation for each result row. The expanded SQL text is what the optimizer sees.

### 2.1 Macros Return SQL Text

A function-based SQL macro must return a supported character type such as VARCHAR2, CHAR, or CLOB. The return value is a valid SQL fragment, for example:

~~~sql
RETURN q'[
    SELECT order_id, customer_id
    FROM sales.orders
]';
~~~

The returned text is not result data. It is a query expression inserted into the calling SQL statement.

### 2.2 Calling a Macro Function Directly in PL/SQL

If you call a function marked SQL_MACRO from a PL/SQL block, the function behaves like a normal function returning a character string; no macro expansion occurs as when referenced from a SQL statement.

Example:

~~~sql
DECLARE
    l_sql VARCHAR2(4000);
BEGIN
    l_sql := employees_hired_since(DATE '2025-01-01');
    DBMS_OUTPUT.PUT_LINE(l_sql);
END;
/
~~~

This is not how you run a macro query to fetch rows. It simply calls the function and receives SQL text per normal PL/SQL behavior. For Oracle to expand the macro, call the macro in SQL in a position supported by your release.

## 3. Conditions by Release and Update

This must be verified before using SQL macros in a project.

### 3.1 Capability Matrix

| Database release/update | Function-based table macro | Function-based scalar macro | Macro in WITH | Native CREATE MACRO |
|---|---|---|---|---|
| 19c prior to RU with feature | Should not be assumed available | No | No | No |
| 19c RU supporting table macro | Yes | No | No per pre-23.26.4 restriction | No |
| 21c | Yes | Yes | No per pre-23.26.4 restriction | No |
| 23ai / 23.x prior to 23.26.4 | Yes | Yes | No per pre-23.26.4 restriction | No |
| 23.26.4 | Yes | Yes | Oracle announced restriction on macros in WITH lifted | No |
| 26ai | Yes | Yes | Yes | Yes |

This matrix separates three distinct mechanisms: table/scalar SQL_MACRO on PL/SQL functions, the ability to use macros in WITH by RU, and macro objects defined with CREATE MACRO. Do not see "SQL macro supported" and conclude every syntax is available.

### 3.2 Oracle Database 19c

The Oracle Database 19c SQL Language Reference and PL/SQL Language Reference record that table SQL macros began being supported in 19c Release 19.7. An Oracle Developer Advocate article from October 2026 describes macros as available since 19c 19.6. Because public Oracle materials differ on the RU milestone, use the RU confirmed in the documentation for your exact installation and verify via tests on the target environment; if you need a conservative baseline per the 19c SQL/PLSQL Language Reference, use 19.7 as the documented milestone.

Key characteristics to remember in 19c:

- Only table SQL macros exist.
- Macros are declared using a PL/SQL function with SQL_MACRO.
- Do not declare SCALAR.
- SQL_MACRO defaults to a table macro; explicit TABLE/SCALAR syntax belongs to newer releases.
- Macros can only be used in the FROM clause of a query table expression.
- Do not use macros in the SELECT list or WHERE like scalar macros.
- Do not use macros in virtual columns, function-based indexes, editioning views, or materialized views.
- Return type must be VARCHAR2, CHAR, or CLOB.
- Do not combine SQL_MACRO with RESULT_CACHE, PARALLEL_ENABLE, or PIPELINED.

19c syntax example:

~~~sql
CREATE OR REPLACE FUNCTION orders_for_customer (
    p_customer_id NUMBER
)
RETURN VARCHAR2
SQL_MACRO
IS
BEGIN
    RETURN q'[
        SELECT order_id,
               customer_id,
               order_date,
               status
        FROM sales.orders
        WHERE customer_id = orders_for_customer.p_customer_id
    ]';
END;
/
~~~

Invocation:

~~~sql
SELECT order_id, order_date, status
FROM orders_for_customer(:customer_id)
ORDER BY order_date DESC;
~~~

Do not write SQL_MACRO(TABLE) in examples targeting 19c if following documented 19c syntax; leave it as the default table macro.

### 3.3 Oracle Database 21c

Oracle Database 21c supports both types:

- SQL_MACRO(TABLE): macro returning a table expression, used in FROM.
- SQL_MACRO(SCALAR): macro returning a scalar expression, used where scalar expressions are allowed.

Table macro example:

~~~sql
CREATE OR REPLACE FUNCTION orders_for_customer (
    p_customer_id NUMBER
)
RETURN VARCHAR2
SQL_MACRO(TABLE)
IS
BEGIN
    RETURN q'[
        SELECT order_id,
               customer_id,
               order_date,
               status
        FROM sales.orders
        WHERE customer_id = orders_for_customer.p_customer_id
    ]';
END;
/
~~~

Scalar macro example:

~~~sql
CREATE OR REPLACE FUNCTION net_amount (
    p_gross_amount NUMBER,
    p_discount_rate NUMBER
)
RETURN VARCHAR2
SQL_MACRO(SCALAR)
IS
BEGIN
    RETURN q'[
        p_gross_amount * (1 - NVL(p_discount_rate, 0))
    ]';
END;
/
~~~

Invocation:

~~~sql
SELECT order_id,
       net_amount(gross_amount, discount_rate) AS net_amount
FROM sales.orders;
~~~

Scalar macros are not used in FROM like table macros. They are used in positions allowing scalar expressions, such as the SELECT list, WHERE, ORDER BY, or other SQL expressions per release rules.

21c is an innovation release. When deploying long-lived systems, in addition to syntax capabilities, check the support lifecycle and database upgrade plan.

### 3.4 Oracle Database 23ai and RU 23.26.4

23ai releases continue supporting function-based SQL macros. One specific change announced by Oracle in an October 21, 2026 article is that starting from release 23.26.4, the previous restriction on using macros inside a WITH clause is lifted.

This matters when queries are structured with common table expressions:

~~~sql
WITH recent_orders AS (
    SELECT *
    FROM orders_for_customer(:customer_id)
)
SELECT customer_id,
       COUNT(*) AS order_count
FROM recent_orders
GROUP BY customer_id;
~~~

Do not apply this example to every 23ai RU without testing. If the database runs an older RU, a macro in WITH may be rejected even though the same macro function works in FROM of a simple query.

Several other SQL syntaxes also have specific RU milestones. For example, GROUP BY ALL was added in 23.9 per Oracle documentation; do not put that syntax into examples claimed to be 19c-compatible. Having SQL macros does not mean every new SQL syntax is present.

### 3.5 Oracle AI Database 26ai and CREATE MACRO

26ai adds native CREATE MACRO syntax. Instead of creating a PL/SQL function returning a SQL string, a macro is defined directly with a SQL expression or query.

Table macro example:

~~~sql
CREATE OR REPLACE MACRO orders_since (
    p_start_date DATE
) AS
    SELECT order_id,
           customer_id,
           order_date,
           status
    FROM sales.orders
    WHERE order_date >= p_start_date;
~~~

Invocation:

~~~sql
SELECT order_id, customer_id, status
FROM orders_since(DATE '2026-01-01');
~~~

Scalar macro example:

~~~sql
CREATE OR REPLACE MACRO price_tier (
    p_base_price NUMBER
) AS
    CASE
        WHEN p_base_price >= 1000 THEN 'PREMIUM'
        WHEN p_base_price >= 500 THEN 'STANDARD'
        WHEN p_base_price >= 100 THEN 'BASIC'
        ELSE 'ENTRY'
    END;
~~~

Invocation:

~~~sql
SELECT product_id,
       price_tier(unit_price) AS tier
FROM products;
~~~

Native macros do not put the SQL expression inside a string literal. Oracle parses and checks the SQL definition when creating the macro. This catches syntax errors and certain semantic errors earlier than function-based macros, where the function can compile even if the SQL text it returns is invalid.

Per published Oracle guidance, CREATE MACRO is syntax available only in 26ai. If your system runs 19c, 21c, or 23ai, use function-based SQL_MACRO appropriate for the release; do not copy CREATE MACRO DDL into unsupported environments.

### 3.6 Do Not Infer Features Solely from Major Version

When inspecting a database, record:

- Full version and release.
- Installed RU/RUR or patch level.
- CDB/PDB and service to which the application connects.
- Whether all instances in RAC support the feature.
- JDBC driver compatibility with the database.
- SQL Language Reference and PL/SQL Language Reference for the exact release.
- Restrictions added/removed in the specific RU.

Oracle requires that in a RAC environment all instances support macros before creating a native macro. During rolling patches or environments with differing node versions, check each instance's state and when the feature is permitted for use.

## 4. How to Create a Table SQL Macro on 19c

Table macros are the foundational macro form and are present in 19c RUs that support the feature.

### 4.1 Example: Filtering Orders by Customer

Suppose the table is:

~~~sql
CREATE TABLE sales.orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    order_date DATE NOT NULL,
    status VARCHAR2(20),
    total_amount NUMBER(12, 2)
);
~~~

Create the macro:

~~~sql
CREATE OR REPLACE FUNCTION orders_for_customer (
    p_customer_id NUMBER
)
RETURN VARCHAR2
SQL_MACRO
IS
BEGIN
    RETURN q'[
        SELECT order_id,
               customer_id,
               order_date,
               status,
               total_amount
        FROM sales.orders
        WHERE customer_id = orders_for_customer.p_customer_id
    ]';
END;
/
~~~

Invocation:

~~~sql
SELECT order_id,
       order_date,
       status,
       total_amount
FROM orders_for_customer(1001)
ORDER BY order_date DESC;
~~~

The macro produces a table expression equivalent to an inline view containing the filter. The outer query can continue filtering, joining, aggregating, or sorting.

### 4.2 Passing Bind Variables

In JDBC or SQL clients, you can pass bind variables:

~~~sql
SELECT order_id, status
FROM orders_for_customer(:p_customer_id);
~~~

The bind variable remains a bind variable in the expanded SQL statement. Do not concatenate the bind value into the SQL text inside the macro body.

### 4.3 Reusing a Filter by Status

~~~sql
CREATE OR REPLACE FUNCTION orders_by_status (
    p_status VARCHAR2
)
RETURN VARCHAR2
SQL_MACRO
IS
BEGIN
    RETURN q'[
        SELECT order_id,
               customer_id,
               order_date,
               status,
               total_amount
        FROM sales.orders
        WHERE status = orders_by_status.p_status
    ]';
END;
/
~~~

Invocation:

~~~sql
SELECT *
FROM orders_by_status(:status);
~~~

The parameter name is referenced inside the returned SQL using the macro name and parameter name. Qualifying it helps distinguish the parameter from a column with the same name.

### 4.4 Combining the Macro with an Outer Query

~~~sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM orders_by_status(:status)
WHERE order_date >= :from_date
GROUP BY customer_id;
~~~

A macro does not replace full query writing. It encapsulates shared logic while the calling query can apply additional calculations.

## 5. How to Create a Scalar SQL Macro on 21c and Later

Scalar macros are suitable for expressions repeated across multiple queries.

### 5.1 Calculating Price After Discount

~~~sql
CREATE OR REPLACE FUNCTION net_amount (
    p_gross_amount NUMBER,
    p_discount_rate NUMBER
)
RETURN VARCHAR2
SQL_MACRO(SCALAR)
IS
BEGIN
    RETURN q'[
        p_gross_amount
        * (1 - NVL(p_discount_rate, 0))
    ]';
END;
/
~~~

Usage:

~~~sql
SELECT order_id,
       gross_amount,
       discount_rate,
       net_amount(gross_amount, discount_rate) AS amount_after_discount
FROM sales.orders;
~~~

Oracle expands the call into the corresponding expression. The optimizer can analyze the expression together with the query and apply appropriate SQL transformations.

### 5.2 Normalizing Display Codes

~~~sql
CREATE OR REPLACE FUNCTION normalized_code (
    p_code VARCHAR2
)
RETURN VARCHAR2
SQL_MACRO(SCALAR)
IS
BEGIN
    RETURN q'[
        UPPER(TRIM(p_code))
    ]';
END;
/
~~~

Usage:

~~~sql
SELECT normalized_code(product_code) AS search_code
FROM products;
~~~

This is an illustrative expression. If normalization rules involve Unicode, locales, or collations, define clear semantics and test on real data. UPPER/TRIM is not a complete solution for all Unicode rules.

### 5.3 Conditional Expression Macro

~~~sql
CREATE OR REPLACE FUNCTION is_active_order (
    p_status VARCHAR2,
    p_cancelled_at DATE
)
RETURN VARCHAR2
SQL_MACRO(SCALAR)
IS
BEGIN
    RETURN q'[
        p_status = 'ACTIVE'
        AND p_cancelled_at IS NULL
    ]';
END;
/
~~~

Usage:

~~~sql
SELECT order_id
FROM sales.orders
WHERE is_active_order(status, cancelled_at);
~~~

Macros allow sharing conditional rules. If a business rule changes, edit the macro once and test dependent queries.

## 6. How Are Macro Parameters Expanded?

This is critical for correctness and security.

In a function-based macro, parameter names are placed inside the returned SQL. Oracle substitutes parameter references with the actual expressions where the macro is called. If a column name is passed, the column expression is placed into the query. If a bind variable is passed, the bind variable is preserved in the expanded SQL.

Example:

~~~sql
RETURN q'[
    SELECT *
    FROM sales.orders
    WHERE customer_id = orders_for_customer.p_customer_id
]';
~~~

When called:

~~~sql
SELECT *
FROM orders_for_customer(:customer_id);
~~~

The reference `orders_for_customer.p_customer_id` expands according to the call's argument. It is not a PL/SQL value concatenated into a string inside the function body.

### 6.1 Do Not Concatenate Parameters into Returned SQL Text

Do not write:

~~~sql
RETURN
    'SELECT * FROM sales.orders WHERE status = '''
    || p_status
    || '''';
~~~

This approach has several issues:

- Risk of SQL injection if the value comes from untrusted input.
- SQL text changes with values, reducing cursor reuse.
- With bind variables, the macro function may only see the value at hard parse time.
- A parsed query may retain text generated from the value at the first hard parse, leading to unexpected results when the bind changes.
- Quote escaping and datatype conversions are error-prone.

Use parameter references in the returned SQL:

~~~sql
RETURN q'[
    SELECT *
    FROM sales.orders
    WHERE status = orders_by_status.p_status
]';
~~~

### 6.2 String Parameter Values Inside the Macro Body

In function-based SQL macros, string-type parameter values may be NULL inside the macro body to prevent the macro body from reading and concatenating string content into SQL text. Instead, reference the parameter name inside the returned SQL.

For other data types, the value may be observable inside the macro body at hard parse. Concatenating that value into SQL text can still freeze the hard-parse value and break bind behavior. The safe rule is never to build SQL by concatenating parameter values; let Oracle expand parameters as expressions.

### 6.3 Parameters Sharing the Same Name as a Column

Suppose a table has column P_STATUS and the macro also has parameter P_STATUS. Use qualified names:

~~~sql
WHERE orders_by_status.p_status = orders_by_status.p_status
~~~

The example above intentionally demonstrates qualification syntax, though logically it compares an expression to itself rather than being a sensible business query. In real code, use table aliases and distinct parameter names:

~~~sql
WHERE o.status = orders_by_status.p_status
~~~

For native 26ai CREATE MACRO, parameter/column name resolution rules are documented separately: if an unqualified name matches both a parameter and a column, Oracle prioritizes the macro parameter; you can qualify parameters with the macro name and columns with the table alias to avoid ambiguity.

## 7. Macros Accepting Table Arguments

Some table macros accept a table expression as a parameter, enabling reuse of logic across multiple tables with compatible structures.

Example with a function-based macro:

~~~sql
CREATE OR REPLACE FUNCTION take_rows (
    p_count NUMBER,
    p_source DBMS_TF.TABLE_T
)
RETURN VARCHAR2
SQL_MACRO
IS
BEGIN
    RETURN q'[
        SELECT *
        FROM p_source
        FETCH FIRST take_rows.p_count ROWS ONLY
    ]';
END;
/
~~~

Invocation:

~~~sql
SELECT *
FROM take_rows(5, sales.orders);
~~~

DBMS_TF.TABLE_T is the table argument type provided by Oracle for polymorphic table functions and SQL macro table parameters in supported releases.

### 7.1 Why Table Arguments Are Useful

One macro can reuse logic across multiple sources:

~~~sql
SELECT *
FROM take_rows(10, sales.orders);

SELECT *
FROM take_rows(10, sales.customers);
~~~

The table arguments must be compatible with the query the macro references. If the macro selects specific columns, the passed tables must contain matching columns.

### 7.2 Columns and Table Structure

A table macro does not automatically transform an arbitrary table into one with the expected schema. You must verify:

- Column names referenced by the expanded query.
- Compatible data types.
- Aliases and scope of the table expression.
- Behavior if a column does not exist.
- Rules when passing a view, CTE, or inline view.

For macros using table arguments, test with tables, views, and CTEs if supported by the release. Do not test with only one specific table and assume the macro is general-purpose.

### 7.3 The COLUMNS Pseudo-Operator and Column Lists

Function-based macros can use DBMS_TF.COLUMNS_T and the COLUMNS pseudo-operator in scenarios requiring a column list at call time, such as generating a dynamic grouping list or sorting list. This is an advanced case, unlike regular scalar bind parameters.

Some column-list capabilities of function-based macros have no direct equivalent in native CREATE MACRO. A 2026 Oracle SQL blog post notes that native macros do not yet accept column-list parameters the way function-based macros do. If your problem requires dynamic column lists, check the exact DBMS_TF APIs and COLUMNS syntax for your running release before choosing a mechanism.

Never concatenate raw column names from requests into SQL. Only accept column lists validated against metadata/whitelists and ensure the caller is authorized to access those columns.

## 8. SQL Macros and the WITH Clause

Common table expressions (CTEs) help break complex queries into named parts:

~~~sql
WITH recent_orders AS (
    SELECT *
    FROM sales.orders
    WHERE order_date >= :from_date
)
SELECT customer_id, COUNT(*)
FROM recent_orders
GROUP BY customer_id;
~~~

Some releases have restrictions when macros are referenced inside a WITH clause. Oracle announced that starting in 23.26.4 this restriction is lifted. Prior to that RU, do not assume every placement of a macro call in a CTE is valid.

Example on a supported release:

~~~sql
WITH selected_orders AS (
    SELECT *
    FROM orders_for_customer(:customer_id)
),
summary AS (
    SELECT customer_id,
           COUNT(*) AS order_count
    FROM selected_orders
    GROUP BY customer_id
)
SELECT *
FROM summary;
~~~

When deploying on 19c or older 23ai RUs, test the exact query on the target patch level. If unsupported, you can place the macro directly in the FROM clause of the main query or write an inline view/CTE without macros depending on release capabilities.

### 8.1 Do Not Confuse WITH Clauses with Macros in Views

A view can reference a macro in its definition according to view privilege semantics. A CTE is simply a query construct within a statement. Privileges and compatibility for macros in views do not imply the absence of restrictions on macro calls inside WITH.

## 9. Privileges and Security Context of SQL Macros

SQL macros have two privilege phases to understand:

1. The body of a function-based macro runs with definer's rights to generate SQL text.
2. The expanded SQL expression/query is evaluated with invoker's rights in the context of the calling SQL, with exceptions/details when the macro is referenced inside a view.

The AUTHID attribute must not be specified for a function with SQL_MACRO. Do not add AUTHID DEFINER or AUTHID CURRENT_USER to a SQL macro declaration.

### 9.1 Privileges on Objects in Expanded SQL

For example, a macro returns:

~~~sql
RETURN q'[
    SELECT *
    FROM sales.orders
]';
~~~

The user calling the macro needs privileges to access objects in the expanded SQL under the applicable security context. Having only EXECUTE on the macro function does not automatically grant SELECT on SALES.ORDERS.

If the macro is referenced in a view, Oracle processes the macro using the view owner's privileges per documented rules. When designing views/packages, check both owner privileges and caller privileges.

### 9.2 INHERIT PRIVILEGES

Oracle checks INHERIT PRIVILEGES regarding how the macro function generates SQL text and the invoker's privileges. When the macro owner and invoker differ, check the requirements for the exact release and confirm appropriate grants. Do not broadly grant to PUBLIC just to make errors disappear.

Distinguish privileges needed to create/execute the macro function, privileges on objects referenced in the expanded SQL, and inherit privileges related to definer/invoker context.

### 9.3 Granting Macro Usage to Another Schema

If the macro belongs to another schema, the calling user needs the EXECUTE object privilege on the macro function per function-based macro rules. At the same time, the user needs privileges on objects referenced in the expanded SQL.

For example, the owner grants:

~~~sql
GRANT EXECUTE ON reporting.orders_for_customer TO app_runtime;
GRANT SELECT ON sales.orders TO app_runtime;
~~~

If designing a view or API to restrict access, do not automatically grant SELECT on base tables to the runtime user; use views/packages and verify the privilege semantics of the intermediary object.

### 9.4 Native CREATE MACRO on 26ai

Per the 26ai CREATE MACRO documentation:

- Creating a macro in your own schema requires CREATE PROCEDURE.
- Creating a macro in another schema requires CREATE ANY PROCEDURE or corresponding schema privileges.
- Calling another user's macro requires EXECUTE on the macro or EXECUTE ANY PROCEDURE.
- The invoker still needs privileges to access objects referenced in the expanded SQL.
- The macro owner needs appropriate privileges on objects in other schemas referenced in the definition.
- With RAC, all instances must support macros before creation.

Do not grant EXECUTE ANY PROCEDURE to an application just to call a single macro. Prefer EXECUTE on the specific macro.

## 10. Restrictions of Function-Based SQL_MACRO

Verify the following restrictions for your exact release:

- The macro function must return VARCHAR2, CHAR, or CLOB.
- SQL_MACRO cannot be combined with RESULT_CACHE.
- SQL_MACRO cannot be combined with PARALLEL_ENABLE.
- SQL_MACRO cannot be combined with PIPELINED.
- Do not declare DETERMINISTIC; SQL macros are considered implicitly deterministic per feature semantics.
- Do not declare AUTHID.
- Type methods cannot be marked SQL_MACRO.
- Macros cannot be used in virtual column expressions.
- Macros cannot be used in function-based indexes.
- Macros cannot be used in editioning views.
- Macros cannot be used in materialized views.
- Table macros can only be used in the FROM clause of a query table expression.
- Scalar macros cannot be used in FROM; they are used in scalar expression positions.
- Scalar macros cannot accept table arguments.

### 10.1 Do Not Use RESULT_CACHE

Do not declare:

~~~sql
CREATE FUNCTION my_macro (...)
RETURN VARCHAR2
RESULT_CACHE
SQL_MACRO
IS
...
~~~

SQL macros and the PL/SQL function result cache are two different mechanisms. A macro generates a SQL expression; it does not cache query results.

### 10.2 Do Not Use PIPELINED

A table macro is not a pipelined table function. Do not add PIPELINED or PARALLEL_ENABLE to a SQL macro declaration. If you need PL/SQL to emit rows one by one, evaluate pipelined table functions; if you need query expansion and optimizer visibility into SQL, use a macro when the release supports it.

### 10.3 Do Not Use in Virtual Columns or Indexes

If you need an expression in a virtual column/function-based index, use a directly supported SQL expression or a regular function with index-suitable properties. SQL macros are not an automatic replacement for function-based indexes.

### 10.4 Do Not Use in Materialized Views

If you need a materialized view, write a query definition compatible with materialized views and query rewrite/refresh restrictions. Do not assume a query containing a macro can be turned into a materialized view.

## 11. How Do Function-Based Macros and Native CREATE MACRO Differ?

| Criterion | CREATE FUNCTION ... SQL_MACRO | CREATE MACRO (26ai) |
|---|---|---|
| Definition | PL/SQL function returning SQL text | Direct SQL expression/query definition |
| Has PL/SQL body | Yes | Not needed |
| SQL definition check | Function can compile even if returned SQL text is invalid; errors may appear at call time | Oracle parses/semantic-checks SQL when creating the macro |
| Return type | VARCHAR2, CHAR, or CLOB | No function-style return type |
| Table arguments | DBMS_TF.TABLE_T in supported releases | Native TABLE parameter with column constraints |
| Dynamic column list | Can use COLUMNS pseudo-operator/DBMS_TF.COLUMNS_T | Does not have the same column-list parameter mechanism as function macros |
| Dictionary | Function metadata; SQL_MACRO column absent in some 19c views | USER_MACROS/ALL_MACROS/DBA_MACROS and parameter views |
| Release | Table from supported 19c RU; scalar from 21c | 26ai |
| Best suited for | Compatibility with older systems, controlled dynamic SQL generation | Standard SQL macros needing compile-time validation |

Native CREATE MACRO makes definitions easier to read and validates SQL earlier. Function-based macros remain useful when you need to construct controlled dynamic SQL text, such as column lists via DBMS_TF.COLUMNS_T.

Do not convert all function macros to native macros solely for new syntax. Determine whether the macro uses table arguments, column lists, dynamic SQL fragments, or specific behaviors.

## 12. Macros and SQL Injection

SQL macros can receive parameters from applications. Distinguish two groups:

- Data values: customer_id, status, date, amount. Use bind variables/parameter references.
- Identifiers or SQL structure: table names, column names, sort directions, group-by lists. Bind variables cannot replace identifiers; use whitelisting/validation.

### 12.1 Unsafe Example

~~~sql
RETURN
    'SELECT * FROM sales.orders WHERE status = '''
    || p_status
    || '''';
~~~

If p_status contains quotes or user-controlled data, the SQL text can be altered. It also causes each value to generate different SQL text.

### 12.2 Safer Example

~~~sql
RETURN q'[
    SELECT *
    FROM sales.orders
    WHERE status = orders_by_status.p_status
]';
~~~

The parameter is passed into the expanded SQL via the macro mechanism. When calling via JDBC, bind status using a PreparedStatement.

### 12.3 Dynamic Identifiers

If choosing a sort column is required:

~~~sql
CASE p_sort_key
    WHEN 'ORDER_DATE' THEN
        l_order_expression := 'order_date';
    WHEN 'TOTAL_AMOUNT' THEN
        l_order_expression := 'total_amount';
    ELSE
        RAISE_APPLICATION_ERROR(-20001, 'Unsupported sort key');
END CASE;
~~~

Only use identifiers from a fixed whitelist. Never concatenate raw input from HTTP requests into returned SQL. Whenever possible, write explicit ORDER BY branches in SQL instead of generating dynamic identifiers.

### 12.4 SQL Injection and Macro Owner Privileges

A macro is not a sandbox. Expanded SQL still executes with the invoker's privileges or the view's security context per Oracle rules. If a macro lets callers choose arbitrary objects/columns, it may expose unintended data access surfaces.

Verify both the safety of the SQL text and privileges on objects that the expanded SQL can reference.

## 13. Performance Optimization and Execution Plans

SQL macros do not automatically make queries faster. The primary benefit is encapsulating SQL while still letting the optimizer see the expanded expression/query.

### 13.1 Avoiding Row-by-Row Context Switches

A regular PL/SQL function called from SQL can cause switches between the SQL engine and the PL/SQL engine on each invocation, depending on how the optimizer handles it. A scalar macro expands into a SQL expression, avoiding per-row PL/SQL calls for logic expressible in SQL.

### 13.2 Predicate Pushdown

With a table macro:

~~~sql
SELECT *
FROM orders_for_customer(:customer_id)
WHERE order_date >= :from_date;
~~~

After the macro expands, the optimizer sees the query expression and can apply transformations such as predicate pushdown if semantics allow. Inspect the execution plan to confirm where filters are applied.

### 13.3 SQL Text Shape and Hard Parses

If a macro function generates many different SQL text shapes depending on inputs, the shared pool may end up with more cursors/child cursors. Avoid concatenating literals or unnecessarily altering query structure.

Use bind variables for data. Only generate multiple SQL shapes when the query structure genuinely differs and there is a performance reason.

### 13.4 Cardinality and Statistics

Macros do not provide statistics to queries on their own. The optimizer still relies on table/index statistics, histograms, constraints, cardinality estimates, and other factors.

If an expanded query has a poor plan:

1. Capture the SQL_ID and execution plan.
2. Inspect the expanded SQL text if your tooling supports it.
3. Check predicates, join order, and access paths.
4. Check bind peeking/adaptive cursor sharing.
5. Compare against the query written directly.
6. Only add hints after understanding the root cause.

### 13.5 Measure Instead of Guessing

Measure the same workload in both forms:

- Query written directly.
- Query calling the macro.

Compare elapsed time, CPU, logical reads, physical reads, parse calls, executions, and plan hash values. Use equivalent data, bind distributions, and concurrency.

If a macro only reduces duplicate code without changing performance, that can still be a valid design benefit. Do not claim a macro is faster without measuring.

## 14. SQL Macros with JDBC and Java

JDBC has no special API for calling SQL macros. Applications send regular SQL statements containing macro calls in positions supported by Oracle.

### 14.1 Calling a Table Macro via PreparedStatement

~~~java
String sql = """
    SELECT order_id, order_date, status
    FROM orders_for_customer(?)
    ORDER BY order_date DESC
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            Date orderDate = resultSet.getDate("order_date");
            String status = resultSet.getString("status");
            // Map row to application model.
        }
    }
}
~~~

The example uses Java text blocks, requiring Java 15 or later. On older Java versions, concatenate SQL lines into a regular String.

### 14.2 Calling a Scalar Macro

~~~java
String sql = """
    SELECT order_id,
           net_amount(gross_amount, discount_rate) AS net_amount
    FROM sales.orders
    WHERE customer_id = ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement = connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            BigDecimal netAmount =
                resultSet.getBigDecimal("net_amount");
        }
    }
}
~~~

Scalar macros can only be used if the database release supports scalar SQL macros. This query cannot run on 19c, which only supports table macros.

### 14.3 Bind Parameters Like Regular SQL

Use setLong, setString, setDate, setBigDecimal, or the setter matching the datatype. Never concatenate values into SQL text in Java.

Macros do not eliminate the need for bind variables. The expanded query is still SQL and is subject to the same bind, datatype conversion, cursor sharing, and SQL injection rules as any other SQL statement.

### 14.4 Driver and Database Compatibility

The Oracle JDBC driver must be compatible with the database version and datatypes in use. Macros are expanded in the database; the driver does not perform expansion on Oracle's behalf.

If the database reports a parse error or unsupported macro feature, upgrading the driver alone will not add a feature missing from the database RU. Check the database first, then check the driver, SQL syntax, and privileges.

## 15. Checking Release, RU, and Macro Metadata

### 15.1 Viewing Database Version

~~~sql
SELECT * FROM v$version;
~~~

If appropriate privileges exist, also check:

~~~sql
SELECT product, version, status
FROM product_component_version
ORDER BY product;
~~~

Record the full banner/version instead of only writing "Oracle 19c" or "Oracle 23ai".

### 15.2 Viewing SQL Patch History

DBAs can query:

~~~sql
SELECT
    patch_id,
    action,
    status,
    description,
    action_time
FROM dba_registry_sqlpatch
ORDER BY action_time DESC;
~~~

This view shows SQL patch history inside the database. Cross-check with the Oracle Home inventory/patches when needed. Do not infer the RU solely from the major version.

### 15.3 RAC and Multiple Instances

~~~sql
SELECT inst_id, instance_name, version, status
FROM gv$instance
ORDER BY inst_id;
~~~

In RAC, check that every instance has appropriate patch/feature support before creating macros or introducing macros into production SQL. A rolling patch can create windows where nodes differ in capability.

### 15.4 The SQL_MACRO Column in the Data Dictionary

In newer releases, USER_PROCEDURES/ALL_PROCEDURES/DBA_PROCEDURES may have a SQL_MACRO column to identify macro functions. Oracle notes this column is not present in Oracle Database 19c; do not write 19c check scripts assuming that column always exists.

On 26ai native macros, the following dictionary views exist:

- USER_MACROS
- ALL_MACROS
- DBA_MACROS
- USER_MACRO_PARAMETERS
- ALL_MACRO_PARAMETERS
- DBA_MACRO_PARAMETERS

Native macros appear in *_OBJECTS with OBJECT_TYPE equal to MACRO. Use the appropriate view according to privileges and release.

Example:

~~~sql
SELECT owner, object_name, object_type, status
FROM all_objects
WHERE object_type = 'MACRO'
ORDER BY owner, object_name;
~~~

Query macro metadata:

~~~sql
SELECT *
FROM user_macros
ORDER BY macro_name;
~~~

Verify exact column names of the macro dictionary in the SQL Reference for the exact release.

### 15.5 Testing Features in a Dedicated Schema

If metadata is not clear enough, create a small macro in a test schema, compile it, and call it. Never test creating new macros in a production business schema just to probe features.

A minimal test should confirm:

1. Whether CREATE FUNCTION with SQL_MACRO compiles.
2. Whether a table macro can be called in FROM.
3. Whether a scalar macro compiles/calls if needed.
4. Whether macro calls inside WITH work on the current RU.
5. Whether privileges on referenced objects are correct.
6. Whether JDBC PreparedStatement can call the query.
7. Whether the actual RAC/PDB/service exhibits the same behavior.

## 16. Complete Example: Table Macro for Order Reporting

Suppose SALES.ORDERS has columns order_id, customer_id, order_date, status, and total_amount.

### 16.1 Macro Function

~~~sql
CREATE OR REPLACE FUNCTION orders_in_period (
    p_from_date DATE,
    p_to_date DATE,
    p_status VARCHAR2
)
RETURN VARCHAR2
SQL_MACRO
IS
BEGIN
    RETURN q'[
        SELECT order_id,
               customer_id,
               order_date,
               status,
               total_amount
        FROM sales.orders
        WHERE order_date >= orders_in_period.p_from_date
          AND order_date < orders_in_period.p_to_date
          AND (
                orders_in_period.p_status IS NULL
                OR status = orders_in_period.p_status
              )
    ]';
END;
/
~~~

This is a table macro using 19c syntax. On 21c and later, you can explicitly declare SQL_MACRO(TABLE).

### 16.2 Calling the Macro and Aggregating

~~~sql
SELECT customer_id,
       COUNT(*) AS order_count,
       SUM(total_amount) AS total_amount
FROM orders_in_period(
    DATE '2026-01-01',
    DATE '2026-02-01',
    :status
)
GROUP BY customer_id
ORDER BY total_amount DESC;
~~~

Using a half-open interval `[from_date, to_date)` avoids end-of-day time issues when order_date has a time component.

### 16.3 Test Cases

- p_status has a specific value.
- p_status is a NULL bind.
- No rows in the period.
- from_date equals to_date.
- Data with timestamps/dates on the boundary.
- Multiple customers with equal total amounts.
- Caller has SELECT privilege on SALES.ORDERS.
- Macro called from another schema via EXECUTE grant.

### 16.4 Checking the Equivalent Direct SQL

Write the same query without the macro:

~~~sql
SELECT order_id,
       customer_id,
       order_date,
       status,
       total_amount
FROM sales.orders
WHERE order_date >= :from_date
  AND order_date < :to_date
  AND (
        :status IS NULL
        OR status = :status
      );
~~~

Compare the row sets and execution plans. A correct macro should produce semantics equivalent to the direct query for the same bind values.

## 17. Complete Example: Scalar Macro for Amount Calculation

### 17.1 Definition

~~~sql
CREATE OR REPLACE FUNCTION line_net_amount (
    p_quantity NUMBER,
    p_unit_price NUMBER,
    p_discount_rate NUMBER
)
RETURN VARCHAR2
SQL_MACRO(SCALAR)
IS
BEGIN
    RETURN q'[
        p_quantity
        * p_unit_price
        * (1 - NVL(p_discount_rate, 0))
    ]';
END;
/
~~~

This example requires an Oracle release supporting scalar macros, such as 21c or later.

### 17.2 Usage

~~~sql
SELECT line_id,
       quantity,
       unit_price,
       discount_rate,
       line_net_amount(
           quantity,
           unit_price,
           discount_rate
       ) AS net_amount
FROM order_lines;
~~~

### 17.3 Testing NULL Semantics and Rounding

If quantity, unit_price, or discount_rate can be NULL, clearly define the business rule. The current macro returns NULL if quantity or unit_price is NULL; a NULL discount_rate is treated as 0.

If monetary rounding is required:

~~~sql
RETURN q'[
    ROUND(
        p_quantity
        * p_unit_price
        * (1 - NVL(p_discount_rate, 0)),
        2
    )
]';
~~~

Scale/rounding rules should be aligned with the application and NUMBER datatype. Do not round in Java differently from Oracle's rules without testing.

## 18. Native CREATE MACRO on 26ai

Native macros are dedicated syntax in 26ai. They do not require writing a PL/SQL function to return a SQL string.

### 18.1 Table Macro

~~~sql
CREATE OR REPLACE MACRO active_orders (
    p_customer_id NUMBER
) AS
    SELECT order_id,
           customer_id,
           order_date,
           status
    FROM sales.orders
    WHERE customer_id = p_customer_id
      AND status = 'ACTIVE';
~~~

Invocation:

~~~sql
SELECT *
FROM active_orders(1001);
~~~

Table macros are used in the FROM clause.

### 18.2 Scalar Macro

~~~sql
CREATE OR REPLACE MACRO order_priority (
    p_total_amount NUMBER
) AS
    CASE
        WHEN p_total_amount >= 10000 THEN 'HIGH'
        WHEN p_total_amount >= 1000 THEN 'NORMAL'
        ELSE 'LOW'
    END;
~~~

Invocation:

~~~sql
SELECT order_id,
       order_priority(total_amount) AS priority
FROM sales.orders;
~~~

Scalar macros are used in scalar expression positions.

### 18.3 Default Parameters

~~~sql
CREATE OR REPLACE MACRO greeting (
    p_name VARCHAR2 DEFAULT 'World'
) AS
    'Hello, ' || p_name || '!';
~~~

Invocation:

~~~sql
SELECT greeting() FROM dual;
SELECT greeting('Oracle') FROM dual;
~~~

A macro without arguments still needs to be called with parentheses per Oracle guidance.

### 18.4 Table Parameters with Column Constraints

Native CREATE MACRO supports table parameters. You can declare a generic table parameter or constrain the required set of columns.

Illustrative pattern:

~~~sql
CREATE OR REPLACE MACRO summarize_orders (
    p_source TABLE (
        customer_id NUMBER,
        total_amount NUMBER
    )
) AS
    SELECT customer_id,
           SUM(total_amount) AS total_amount
    FROM p_source
    GROUP BY customer_id;
~~~

Verify exact table parameter and column list syntax against the CREATE MACRO grammar for the exact 26ai release. The passed table argument must have the required columns with compatible data types; extra columns or different column ordering may be allowed per native macro rules.

### 18.5 Parameter Name Resolution

If a parameter and a column share the same name, an unqualified name may resolve to the macro parameter first. To avoid ambiguity:

- Qualify parameters with the macro name.
- Qualify columns with the table alias.
- Use easily distinguishable parameter names, such as p_customer_id.
- Alias tables whose names match the macro.

Keep this rule in mind when native macros are used in large query scopes with many tables and overlapping column names.

### 18.6 Compile-Time Validation

Native CREATE MACRO defines SQL directly, so Oracle parses and checks the SQL definition when creating the macro. Compared to function-based macros returning SQL text, syntax/semantic errors in the query definition can be caught earlier.

Even so, successful compilation does not replace runtime testing with bind values, privileges, object data, optimizer plans, and concurrency. A syntactically valid query can still be logically wrong or slow.

## 19. Comparing SQL Macros with Other Options

### 19.1 Views

Use a view when:

- The query does not need parameters.
- You want to provide a stable interface to many consumers.
- You want to manage privileges through the view.
- You want to hide base table structures.

Use a macro when the query needs parameters or a reusable expression must be expanded into the caller's SQL.

### 19.2 Inline Views and CTEs

Use an inline view/CTE when logic is used only once or by a single consumer. Macros fit when the same logic repeats across multiple SQL statements and needs centralized management.

Do not create a macro for a trivial expression just to inflate the number of schema objects. Consider query readability, dependencies, and deployment practices.

### 19.3 Regular PL/SQL Functions

Use a regular function when you need:

- Procedural logic not easily expressed in SQL.
- Calls to packages/APIs or PL/SQL operations.
- Computing a value using a custom algorithm.
- Reusing logic across both PL/SQL and SQL.

Use a scalar macro when the logic can be expressed as a SQL expression and you want the optimizer to see that expression. In newer releases, the SQL Transpiler can also convert some PL/SQL functions into SQL expressions; evaluate that feature separately rather than treating it as synonymous with SQL macros.

### 19.4 Pipelined Table Functions

Pipelined table functions fit when PL/SQL genuinely needs to generate rows one by one, call APIs, or execute procedural logic. They have a different execution model and overhead than table macros.

If the data already resides in tables and can be expressed with SELECT, a table macro is usually more natural because it hands a SQL query to the optimizer.

### 19.5 Polymorphic Table Functions

PTFs fit when you need to alter output row shapes or manipulate column/metadata via a PL/SQL interface. Table macros fit when you want parameterized query expressions. Do not use a macro instead of a PTF if the requirement needs dynamic row metadata processing that a macro cannot express.

## 20. Environment-Based SQL Macro Rollout Process

### Step 1: Identify the Use Case

Clearly state what the macro needs to encapsulate:

- Parameterized table query.
- Scalar expression.
- Table argument.
- Dynamic column list.
- Macro used in WITH.
- Native CREATE MACRO.

### Step 2: Determine Database Capabilities

Record full version, RU, service/PDB, RAC instances, and driver. Cross-check the release matrix and Oracle documentation.

### Step 3: Choose the Right Mechanism

- 19c: table function macro, do not use scalar macros.
- 21c: table/scalar function macros.
- 23ai: check RU for WITH clause support.
- 26ai: consider native CREATE MACRO for standard SQL definitions.
- Dynamic column list needed: evaluate function-based macro with DBMS_TF.COLUMNS_T.

### Step 4: Design Parameters

Classify each parameter:

- Scalar value.
- Bind variable.
- Column expression.
- Table expression.
- Identifier/column list.

Never concatenate inputs into SQL strings. For identifiers, use whitelists and appropriate APIs.

### Step 5: Verify Privileges

Identify the macro owner, invoker, view owner if the macro sits in a view, EXECUTE grants, and privileges on expanded SQL. Check INHERIT PRIVILEGES per release and schema boundaries.

### Step 6: Create the Macro in a Test Schema

Compile the function/native macro, call it with a simple query, then test complex queries and multiple callers. Never start with a production deployment.

### Step 7: Compare with Direct Queries

Write the equivalent query without a macro. Compare results, NULL behavior, datatypes, execution plans, and bind behavior.

### Step 8: Test JDBC

Use PreparedStatement and bind variables. Test with the application's actual driver and datasource. Do not test only in SQL Developer.

### Step 9: Deploy and Monitor

Deploy the macro alongside migrations, grants, and dependent views/packages. Monitor SQL_ID, plans, parse rates, latency, and invalidation errors after release.

## 21. Testing and Troubleshooting

### 21.1 Function Compiles but Query Fails

With function-based macros, the function body can compile even if the returned SQL text contains errors. Oracle only parses the expanded SQL and reports errors when the macro is called.

How to handle:

1. Call the macro with a minimal query.
2. Check object names and aliases in the returned SQL.
3. Check parameter qualification.
4. Run the equivalent query directly.
5. Check privileges on the expanded SQL.
6. Check release restrictions.

### 21.2 ORA-00904 Invalid Identifier

Common causes:

- Parameter referenced with wrong name.
- Column does not exist in the table argument.
- Alias not declared in scope.
- Parameter shares a column name and is unqualified.
- Macro query expanded in a different scope than assumed.

Use aliases and qualify parameters clearly.

### 21.3 ORA-00942 or ORA-01031

Macros do not grant privileges to the caller. Check:

- Macro owner has necessary privileges on objects per definition.
- Invoker has privileges on expanded SQL.
- View owner if the macro is referenced inside a view.
- EXECUTE privilege on the macro function/object.
- INHERIT PRIVILEGES in cross-schema use.
- Correct PDB/service and synonym target.

### 21.4 Macro Not Recognized or Syntax Error

The database RU may not support the feature or syntax from another release is being used.

Common examples:

- Using SQL_MACRO(SCALAR) on 19c.
- Using CREATE MACRO on 23ai.
- Using a macro in WITH on an unsupported RU.
- Using explicit SQL_MACRO(TABLE) on 19c instead of the default table macro syntax.
- Using a macro in a virtual column/function-based index/materialized view.

Check the SQL Language Reference for the exact release and create a test in an isolated schema.

### 21.5 JDBC Parse Error

If a SQL client works but JDBC fails:

- Confirm the datasource uses the right service/PDB.
- Confirm the database user and current schema.
- Confirm the driver version.
- Confirm the SQL string and bind positions.
- Verify the macro query is sent intact.
- Check that JDBC is not wrapping or rewriting the SQL.
- Check connection pool roles/session state.

## 22. SQL Macro Selection Checklist

### Release and Syntax

- [ ] Full database version identified.
- [ ] RU/patch level identified.
- [ ] Correct PDB/service verified.
- [ ] All RAC instances verified.
- [ ] Chosen between table or scalar macro.
- [ ] If 19c, using table macro and compatible syntax.
- [ ] If using WITH, confirmed RU support.
- [ ] If using CREATE MACRO, database is 26ai.
- [ ] Verified restrictions for the exact release.

### Macro Design

- [ ] Macro has a clear reuse use case.
- [ ] Query/expression can be expressed in SQL.
- [ ] Parameters have clear names and datatypes.
- [ ] Parameters are referenced in returned SQL, not concatenated into text.
- [ ] Dynamic identifiers use a whitelist.
- [ ] Table arguments have a clear schema/column contract.
- [ ] Aliases and parameter qualifications are unambiguous.
- [ ] NULL, datatype conversion, and date boundaries are defined.

### Privileges and Security

- [ ] Macro owner has required privileges.
- [ ] Invoker has EXECUTE on the macro.
- [ ] Invoker has privileges on expanded SQL.
- [ ] View owner accounted for if macro is in a view.
- [ ] INHERIT PRIVILEGES checked where needed.
- [ ] Broad ANY privileges are not used just to make the macro run.
- [ ] Untrusted input is never concatenated into SQL text.

### Performance and Testing

- [ ] Direct query exists as a baseline.
- [ ] Macro results match baseline query.
- [ ] Execution plan inspected.
- [ ] Logical reads, CPU, and elapsed time measured.
- [ ] Various bind values tested.
- [ ] Tested via JDBC with the actual driver.
- [ ] Tested across schemas/callers if applicable.
- [ ] Tested on corresponding RU/PDB/RAC.
- [ ] Migration and rollback plans in place.

## 23. Conclusion

SQL macros enable parameterized SQL reuse while still allowing the Oracle optimizer to process the expanded query or expression. Table macros suit queries in FROM; scalar macros encapsulate expressions in SELECT/WHERE and permitted scalar positions. Macro functions are not row-by-row data-returning functions, and they do not automatically guarantee better performance.

Usability depends on release/update. Oracle 19c focuses on table macros; Oracle 21c supports scalar macros; Oracle announced RU 23.26.4 lifts the restriction on macros in WITH clauses; native CREATE MACRO belongs to 26ai. 19c documentation has public discrepancies regarding the 19.6/19.7 RU milestone, so confirm patch levels and documentation for your exact environment before deploying.

When writing macros, reference parameters in the expanded SQL instead of concatenating values into SQL text, verify privileges of the macro owner/invoker/view owner, avoid unwhitelisted dynamic identifiers, and compare execution plans against direct queries. Use macros when they make shared SQL logic clearer and the target release supports the required syntax.

## 24. References

- Oracle Database 19c SQL Language Reference — Changes in This Release: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Changes-in-This-Release-for-Oracle-Database-SQL-Language-Reference.html
- Oracle Database 19c PL/SQL Language Reference — SQL_MACRO Clause: https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/SQL_MACRO_clause.html
- Oracle Database 21c PL/SQL Language Reference — SQL_MACRO Clause: https://docs.oracle.com/en/database/oracle/oracle-database/21/lnpls/sql_macro-clause.html
- Oracle AI Database 26ai PL/SQL Language Reference — SQL_MACRO Clause: https://docs.oracle.com/en/database/oracle/oracle-database/26/lnpls/SQL_MACRO-clause.html
- Oracle AI Database 26ai SQL Language Reference — CREATE MACRO: https://docs.oracle.com/en/database/oracle/oracle-database/26/sqlrf/CREATE-MACRO.html
- Chris Saxon, Oracle Developer Advocate, How to create views with parameters in Oracle AI Database, 21 October 2026: https://blogs.oracle.com/sql/how-to-create-views-with-parameters-in-oracle-ai-database
