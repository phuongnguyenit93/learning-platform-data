# SQL injection, bind parameters, and dynamic object name control in Oracle Database

SQL injection occurs when untrusted input data is concatenated directly into a SQL or PL/SQL statement as executable code. When that happens, a value the user intended to send as data can alter the statement structure, add conditions, read out-of-scope data, modify/delete data, or execute another statement within the privileges of the database account.

The most important measure to prevent SQL injection is **using bind variables for all data values**. Bind variables transmit values separately from the SQL text, so quotes, semicolons, or SQL-like strings cannot turn into executable syntax.

Table names, schema names, column names, keywords, and sort directions are SQL structural components; they cannot be replaced by bind variables like ordinary values. When dynamic object selection is genuinely required, you must use an **allowlist** defining the permitted choices, and then validate/quote names with appropriate functions such as DBMS_ASSERT. DBMS_ASSERT assists in validating syntax and object names; it does not replace allowlists, privilege controls, or secure design.

This lesson focuses on Oracle Database, static SQL, Native Dynamic SQL, DBMS_SQL, DBMS_ASSERT, and PL/SQL execution rights. Examples illustrate how to turn input data into binds, how to control dynamic identifiers, and common security pitfalls.

## 1. What is SQL injection?

An application often builds queries by combining SQL text with user data. If the application concatenates strings unsafely, the data can alter the SQL syntax.

For example, suppose an application wants to find a user by username:

~~~sql
SELECT user_id, username
FROM app_users
WHERE username = '<input>';
~~~

If the input is concatenated straight into the SQL statement, a user can enter a string containing quotes and SQL operators to alter the condition. When data becomes part of the SQL text, the database parses it as syntax.

### 1.1 Unsafe string concatenation example

~~~sql
CREATE OR REPLACE PROCEDURE find_user_unsafe (
    p_username IN  VARCHAR2,
    p_user_id  OUT NUMBER
)
AS
    l_sql VARCHAR2(4000);
BEGIN
    l_sql :=
        'SELECT user_id FROM app_users WHERE username = '''
        || p_username
        || '''';

    EXECUTE IMMEDIATE l_sql INTO p_user_id;
END;
/
~~~

The code above has two issues:

- Input data is concatenated into the SQL text.
- A single quote in the input can terminate the string literal and inject what follows into SQL syntax.

When input changes the structure of a statement, that is SQL injection. An attacker does not need direct connection access to the database; an application or stored procedure that accepts input and builds unsafe SQL is enough.

### 1.2 Safe example using bind variables

~~~sql
CREATE OR REPLACE PROCEDURE find_user_safe (
    p_username IN  VARCHAR2,
    p_user_id  OUT NUMBER
)
AS
BEGIN
    EXECUTE IMMEDIATE
        'SELECT user_id
           FROM app_users
          WHERE username = :username'
        INTO p_user_id
        USING p_username;
END;
/
~~~

The SQL text contains the placeholder :username. The value p_username is passed separately in USING, so even if the input contains quotes or SQL-like strings, Oracle still treats it as predicate data.

### 1.3 What can happen during SQL injection?

Depending on schema privileges and how the application executes statements, SQL injection can lead to:

- Bypassing authentication or filter conditions.
- Reading data belonging to other users/tenants.
- Modifying, inserting, or deleting data.
- Invoking packages/procedures with higher privileges than the application user.
- Executing DDL or other statements if code allows multiple statements or unsafe dynamic PL/SQL blocks.
- Accessing objects outside intended scope via controlled schema/object names.
- Leaking information through SQL errors, timing, or side channels.

The severity depends on the privileges of the database account, stored procedure privileges, accessible data, and other control layers.

## 2. Core rule: separate data from SQL code

A SQL statement has two kinds of components:

| Component | Examples | Safe handling |
|---|---|---|
| Data values | username, date, amount, status, ID | Bind variable |
| Object names | schema, table, view, column | Allowlist, validate, and quote identifier |
| Keywords/structure | ASC/DESC, operators, function names, join type | Choose from a permitted set of constants |
| SQL fragments | WHERE clause, ORDER BY expression | Fixed design or generated from controlled structure |

Do not apply a single rule to every input. Bind variables are the standard choice for data values; identifiers and SQL syntax must be selected from values controlled by the program.

### 2.1 Bind variables are not string escaping

Binding does not modify strings by adding quotes. It keeps SQL text and data on two separate channels:

~~~text
SQL text:  SELECT ... WHERE username = :b1
Bind b1:   user input string
~~~

Oracle parses the SQL text as a statement with placeholders, then receives bind values separately. Bind values are never re-parsed as SQL syntax.

### 2.2 Bind variables also reduce hard parses

When an application concatenates literals into SQL text, each distinct value can produce a distinct SQL text:

~~~sql
SELECT * FROM orders WHERE customer_id = 100;
SELECT * FROM orders WHERE customer_id = 101;
SELECT * FROM orders WHERE customer_id = 102;
~~~

When using binds:

~~~sql
SELECT * FROM orders WHERE customer_id = :customer_id;
~~~

The SQL text can be shared across multiple executions with different bind values, reducing parse overhead and improving cursor sharing. The optimizer may still produce multiple child cursors in certain cases, such as adaptive cursor sharing or differing bind metadata.

Performance is an added benefit. The primary security reason remains that data cannot alter SQL syntax.

## 3. Bind variables in static SQL

With static SQL in PL/SQL, use PL/SQL variables directly inside the SQL statement. Oracle automatically binds those PL/SQL variables:

~~~sql
CREATE OR REPLACE PROCEDURE find_order (
    p_order_id IN orders.order_id%TYPE
) AUTHID DEFINER
AS
    l_status orders.status%TYPE;
BEGIN
    SELECT status
    INTO l_status
    FROM orders
    WHERE order_id = p_order_id;

    DBMS_OUTPUT.PUT_LINE('Status=' || l_status);
END;
/
~~~

This is static SQL. The value p_order_id is passed as a bind; no string concatenation or EXECUTE IMMEDIATE is needed.

### 3.1 Do not build dynamic SQL when static SQL suffices

If tables, columns, and query structure are known at compile time, static SQL is generally better:

- The compiler checks syntax and object references.
- Dependencies are tracked by the database.
- Easier to read, maintain, and review.
- No manual construction of SQL text.
- Input values are still bound.

Use dynamic SQL only when statement structure or target objects genuinely need to vary at runtime, such as choosing among multiple valid tables or generating DDL.

## 4. Bind variables with Native Dynamic SQL

Native Dynamic SQL (NDS) is the use of EXECUTE IMMEDIATE or OPEN FOR to run SQL/PLSQL built at runtime.

### 4.1 Binding values in a single-row SELECT

~~~sql
DECLARE
    l_sql       VARCHAR2(1000);
    l_order_id  NUMBER;
    l_status    VARCHAR2(30);
BEGIN
    l_sql :=
        'SELECT order_id, status
           FROM orders
          WHERE customer_id = :customer_id
            AND order_date >= :from_date';

    EXECUTE IMMEDIATE l_sql
        INTO l_order_id, l_status
        USING p_customer_id, p_from_date;
END;
/
~~~

The placeholders :customer_id and :from_date represent values. Binds in USING are passed positionally for regular dynamic SQL statements.

### 4.2 Binding in INSERT, UPDATE, and DELETE

~~~sql
BEGIN
    EXECUTE IMMEDIATE
        'INSERT INTO order_audit
             (order_id, action_name, created_at)
         VALUES
             (:order_id, :action_name, :created_at)'
    USING p_order_id, p_action_name, SYSTIMESTAMP;

    EXECUTE IMMEDIATE
        'UPDATE orders
            SET status = :new_status
          WHERE order_id = :order_id'
    USING p_new_status, p_order_id;

    EXECUTE IMMEDIATE
        'DELETE FROM order_staging
          WHERE batch_id = :batch_id'
    USING p_batch_id;
END;
/
~~~

Every input value resides in USING. Do not concatenate values into SQL text, even numbers or dates.

### 4.3 Binding OUT parameters with RETURNING INTO

EXECUTE IMMEDIATE supports binding inputs and outputs. With DML RETURNING:

~~~sql
DECLARE
    l_new_status VARCHAR2(30);
BEGIN
    EXECUTE IMMEDIATE
        'UPDATE orders
            SET status = :new_status
          WHERE order_id = :order_id
        RETURNING status INTO :returned_status'
    USING p_new_status, p_order_id
    RETURNING INTO l_new_status;

    DBMS_OUTPUT.PUT_LINE(l_new_status);
END;
/
~~~

RETURNING INTO receives values returned by the DML statement. It does not replace USING for input binds.

### 4.4 Binding multi-row queries with OPEN FOR

When a query returns multiple rows, use a REF CURSOR:

~~~sql
DECLARE
    l_cursor SYS_REFCURSOR;
    l_sql    VARCHAR2(1000);
    l_id     NUMBER;
    l_status VARCHAR2(30);
BEGIN
    l_sql :=
        'SELECT order_id, status
           FROM orders
          WHERE customer_id = :customer_id
          ORDER BY order_date DESC';

    OPEN l_cursor FOR l_sql USING p_customer_id;

    LOOP
        FETCH l_cursor INTO l_id, l_status;
        EXIT WHEN l_cursor%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(l_id || ':' || l_status);
    END LOOP;

    CLOSE l_cursor;
END;
/
~~~

The p_customer_id value is safely bound. ORDER BY is a fixed structure in the SQL text.

### 4.5 Bind order and placeholder names

For a dynamic SQL statement in Native Dynamic SQL, placeholders are associated with bind arguments by **position**, not by placeholder name. Therefore, keep the USING order aligned with the order in which placeholders appear.

~~~sql
DECLARE
    l_sql VARCHAR2(1000);
BEGIN
    l_sql :=
        'UPDATE orders
            SET status = :x
          WHERE customer_id = :x
            AND order_id = :y';

    EXECUTE IMMEDIATE l_sql
        USING p_status, p_customer_id, p_order_id;
END;
/
~~~

In a dynamic SQL statement, two placeholders with the same name :x are still bound by each position. Do not rely on matching names to pass a single bind for multiple occurrences.

For dynamic anonymous PL/SQL blocks or CALL statements, Oracle processes placeholders by name; if the same placeholder name appears multiple times, a single bind argument can satisfy those occurrences. Because rules differ, write examples and USING clauses explicitly, and verify the exact dynamic statement type before reusing code.

## 5. What cannot be bound

Bind variables substitute expression values, not SQL structure.

Cases where binds cannot be used as identifiers/keywords:

~~~sql
SELECT * FROM :table_name;
ORDER BY :column_name;
SELECT :column_name FROM orders;
CREATE TABLE :new_table (...);
~~~

In the examples above, the placeholder does not become a table name, column name, or object name. In SELECT :column_name, Oracle returns the bind value as a scalar expression; it does not read a column whose name is stored in the bind.

### 5.1 Classifying inputs

| Input | Bindable? | Solution |
|---|---|---|
| Customer ID | Yes | Bind NUMBER |
| Username | Yes | Bind VARCHAR2 |
| DATE/TIMESTAMP | Yes | Bind with proper date/time type |
| Status value | Yes | Bind VARCHAR2 |
| Table name | No | Allowlist + identifier validation/quoting |
| Schema name | No | Allowlist schema + validate/quote |
| ORDER BY column name | No | Map selection to a fixed identifier |
| ASC/DESC | No | Choose from two fixed literals |
| Function/operator name | No | Use only program-defined structures |
| Arbitrary WHERE fragment | Unsafe | Design structured filters and bind each value |

### 5.2 Dynamic ORDER BY

Do not concatenate p_sort_column directly:

~~~sql
-- Unsafe
l_sql := 'SELECT ... FROM orders ORDER BY ' || p_sort_column;
~~~

Instead, map input to a fixed set of choices:

~~~sql
DECLARE
    l_sort_column VARCHAR2(30);
    l_direction  VARCHAR2(4);
    l_sql         VARCHAR2(2000);
BEGIN
    CASE UPPER(p_sort_key)
        WHEN 'DATE' THEN
            l_sort_column := 'ORDER_DATE';
        WHEN 'AMOUNT' THEN
            l_sort_column := 'TOTAL_AMOUNT';
        WHEN 'STATUS' THEN
            l_sort_column := 'STATUS';
        ELSE
            RAISE_APPLICATION_ERROR(-20001, 'Unsupported sort key');
    END CASE;

    CASE UPPER(p_sort_direction)
        WHEN 'ASC' THEN
            l_direction := 'ASC';
        WHEN 'DESC' THEN
            l_direction := 'DESC';
        ELSE
            RAISE_APPLICATION_ERROR(-20002, 'Unsupported sort direction');
    END CASE;

    l_sql :=
        'SELECT order_id, order_date, total_amount, status
           FROM orders
          WHERE customer_id = :customer_id
          ORDER BY ' || l_sort_column || ' ' || l_direction;

    OPEN p_result FOR l_sql USING p_customer_id;
END;
/
~~~

Only identifiers and keywords selected by the program enter the SQL text. The customer ID value remains bound.

### 5.3 Column names in dynamic projection

If users can select display columns, use an allowlist:

~~~sql
CASE UPPER(p_field_key)
    WHEN 'ORDER_ID' THEN l_column := 'ORDER_ID';
    WHEN 'ORDER_DATE' THEN l_column := 'ORDER_DATE';
    WHEN 'STATUS' THEN l_column := 'STATUS';
    ELSE
        RAISE_APPLICATION_ERROR(-20003, 'Unsupported field');
END CASE;
~~~

Never accept an arbitrary string as a SELECT column list. A UI selection like ORDER_DATE must map to an application-controlled constant identifier.

## 6. Allowlist: controlling dynamic object names

An allowlist is a list of permitted objects or structures. For dynamic object names, this is the most important business control layer.

For example, suppose an application only allows reading two tables:

| Choice code from application | Schema | Table |
|---|---|---|
| ORDERS | APP | ORDERS |
| ARCHIVE | APP | ORDERS_ARCHIVE |

The user sends the key ORDERS or ARCHIVE. The application looks up the key in a fixed list and retrieves the corresponding schema/table. Never use the user-supplied string directly as the object name.

### 6.1 Allowlist with CASE

~~~sql
DECLARE
    l_owner VARCHAR2(128);
    l_table VARCHAR2(128);
BEGIN
    CASE UPPER(p_source_key)
        WHEN 'ORDERS' THEN
            l_owner := 'APP';
            l_table := 'ORDERS';
        WHEN 'ARCHIVE' THEN
            l_owner := 'APP';
            l_table := 'ORDERS_ARCHIVE';
        ELSE
            RAISE_APPLICATION_ERROR(-20010, 'Source is not allowed');
    END CASE;
END;
/
~~~

The list is controlled in code or in a configuration table that only the DBA/owner can manage. If using an allowlist table, do not let regular users add arbitrary objects.

### 6.2 Allowlists differ from denylists

Denylists try to filter out dangerous strings such as semicolons, quotes, or keywords. This approach easily misses valid alternative syntax and lacks SQL context awareness.

Allowlists accept only explicit choices. For object names, this is easier to control and audit.

### 6.3 Object-level authorization

Even when an object name is in the allowlist, the schema executing the SQL must still hold the required privileges. The allowlist controls application choices; privileges control what the database account can do. Both are required.

## 7. DBMS_ASSERT: validating and quoting SQL names

DBMS_ASSERT is an Oracle package providing input validation functions for dynamic SQL. These functions help verify that a string conforms to a type of SQL name or quote an identifier/literal according to Oracle rules.

DBMS_ASSERT is a useful defense layer, but it does not replace an allowlist:

- A syntactically valid object name may still be an object the application is not permitted to access.
- A schema or object existing does not mean the caller should be allowed to select it.
- DBMS_ASSERT does not replace Oracle's privilege checks.
- For data values, bind variables remain the right choice; DBMS_ASSERT is not needed to replace binds.

### 7.1 Commonly used functions

| Function | Purpose |
|---|---|
| ENQUOTE_NAME | Checks a simple SQL name and encloses it in double quotes |
| SIMPLE_SQL_NAME | Validates a simple SQL name |
| QUALIFIED_SQL_NAME | Validates a qualified SQL name per Oracle grammar |
| SCHEMA_NAME | Verifies a schema name exists |
| SQL_OBJECT_NAME | Verifies a SQL object name exists |
| ENQUOTE_LITERAL | Quotes a SQL string literal; use only when generating a literal is truly needed, binds are still preferred |
| NOOP | Returns input unchanged; performs no validation and no sanitization |

### 7.2 ENQUOTE_NAME

ENQUOTE_NAME checks that the input is a simple SQL name and returns the identifier enclosed in double quotes:

~~~sql
SELECT DBMS_ASSERT.ENQUOTE_NAME('ORDERS')
FROM dual;
~~~

The result is a quoted identifier, typically `"ORDERS"`.

The capitalize parameter defaults to TRUE. For regular unquoted identifiers, Oracle converts names to uppercase. If you need to preserve casing for an allowlisted quoted identifier, use capitalize => FALSE and store the exact name created:

~~~sql
SELECT DBMS_ASSERT.ENQUOTE_NAME('MixedCaseTable', FALSE)
FROM dual;
~~~

Quoted identifiers must match exactly how the object was created. Do not automatically uppercase quoted object names.

### 7.3 SIMPLE_SQL_NAME

SIMPLE_SQL_NAME checks that the input is a valid simple SQL name. It does not check whether the object exists or whether the caller has access privileges.

~~~sql
DECLARE
    l_column_name VARCHAR2(128);
BEGIN
    l_column_name := DBMS_ASSERT.SIMPLE_SQL_NAME(p_column_name);
END;
/
~~~

Calling this function alone does not make an arbitrary column a permitted business choice. After syntax validation, you must still verify the column belongs to the allowlist.

### 7.4 QUALIFIED_SQL_NAME

QUALIFIED_SQL_NAME validates a qualified SQL name per Oracle grammar. It is suitable for checking the syntax of qualified names, but you should not take an arbitrary string from a client and concatenate it into a statement just because validation succeeded.

If an application allows only one schema and a few specific tables, an explicit owner/table allowlist remains clearer.

### 7.5 SCHEMA_NAME and SQL_OBJECT_NAME

SCHEMA_NAME verifies that a schema name exists. SQL_OBJECT_NAME verifies that a SQL object name exists. They are useful after the application has already determined a permitted choice:

~~~sql
DECLARE
    l_owner VARCHAR2(128);
    l_table VARCHAR2(128);
BEGIN
    l_owner := DBMS_ASSERT.SCHEMA_NAME('APP');
    l_table := DBMS_ASSERT.SIMPLE_SQL_NAME('ORDERS');
END;
/
~~~

These are name checks only. Deciding which object a caller may select still requires an allowlist. Actual SELECT/INSERT/UPDATE/DELETE privileges are checked by the database when dynamic SQL executes.

### 7.6 Example of safely assembling dynamic identifiers

~~~sql
DECLARE
    l_owner VARCHAR2(128);
    l_table VARCHAR2(128);
    l_sql   VARCHAR2(4000);
    l_count NUMBER;
BEGIN
    -- Allowlist: input only selects a key, never supplies the object name directly.
    CASE UPPER(p_source_key)
        WHEN 'ORDERS' THEN
            l_owner := 'APP';
            l_table := 'ORDERS';
        WHEN 'ARCHIVE' THEN
            l_owner := 'APP';
            l_table := 'ORDERS_ARCHIVE';
        ELSE
            RAISE_APPLICATION_ERROR(-20020, 'Source is not allowed');
    END CASE;

    -- Validate the schema and table names selected from the allowlist.
    l_owner := DBMS_ASSERT.SCHEMA_NAME(l_owner);
    l_table := DBMS_ASSERT.SIMPLE_SQL_NAME(l_table);

    l_sql :=
        'SELECT COUNT(*) FROM '
        || DBMS_ASSERT.ENQUOTE_NAME(l_owner)
        || '.'
        || DBMS_ASSERT.ENQUOTE_NAME(l_table)
        || ' WHERE status = :status';

    EXECUTE IMMEDIATE l_sql
        INTO l_count
        USING p_status;
END;
/
~~~

Here, only the owner/table selected from the allowlist enters the SQL text. Status is data, so it is bound.

### 7.7 ENQUOTE_LITERAL does not replace binds

DBMS_ASSERT.ENQUOTE_LITERAL can quote a string into a valid SQL literal. However, whenever a value can be bound, bind it:

~~~sql
-- Preferred
EXECUTE IMMEDIATE
    'SELECT user_id FROM app_users WHERE username = :username'
INTO l_user_id
USING p_username;
~~~

Manual literal quoting adds responsibility for handling encoding, data types, lengths, and syntax. Bind variables are both safer and generally better for cursor sharing.

## 8. NLS injection: risks when concatenating DATE and NUMBER

SQL injection does not come only from user strings containing quotes. In Oracle, implicit conversion of DATE, TIMESTAMP, or NUMBER to VARCHAR2 during string concatenation can depend on NLS session settings. An attacker may influence certain NLS settings in a session to alter the generated SQL text.

### 8.1 Example of implicit DATE-to-string conversion

Unsafe code:

~~~sql
l_sql :=
    'SELECT * FROM orders WHERE order_date = '''
    || p_order_date
    || '''';
~~~

P_ORDER_DATE is a DATE, but when concatenated with VARCHAR2 Oracle must convert the DATE to a string. The format can depend on NLS_DATE_FORMAT. If the session's NLS_DATE_FORMAT is altered to a format containing SQL text, the resulting text can alter the statement.

### 8.2 Safe approach: bind DATE

~~~sql
l_sql :=
    'SELECT * FROM orders WHERE order_date = :order_date';

OPEN p_result FOR l_sql USING p_order_date;
~~~

The value remains a DATE when passed into SQL; no string conversion is needed.

### 8.3 NUMBER and NLS_NUMERIC_CHARACTERS

Concatenating a NUMBER into SQL text can depend on NLS_NUMERIC_CHARACTERS, affecting how decimal and grouping separators are formatted. Do not concatenate numbers into SQL:

~~~sql
-- Unsafe and conversion-dependent
l_sql := 'SELECT * FROM invoices WHERE amount > ' || p_amount;
~~~

Use binds:

~~~sql
l_sql := 'SELECT * FROM invoices WHERE amount > :amount';
OPEN p_result FOR l_sql USING p_amount;
~~~

### 8.4 When generating a literal is unavoidable

Some DDL or structural contexts that do not support binds may require generating a literal. Prefer Oracle APIs that support binds/metadata if available; otherwise, perform explicit conversion with a fixed format model, control NLS settings, and quote properly for the type. Never rely on implicit conversion.

However, do not treat literal formatting as a general workaround for DML/SELECT. Bind values whenever binding is supported.

## 9. Second-order SQL injection

Second-order injection occurs when input data is initially stored in a table as ordinary data, but another feature later reads that value and concatenates it into SQL text. The injection point appears on subsequent use, not necessarily on the initial write.

Example:

1. The application saves a configuration string into table REPORT_CONFIG.
2. A report-running procedure reads that string.
3. The procedure concatenates the string into a WHERE clause or ORDER BY.
4. The stored content alters the SQL when the report runs.

Data coming from the database is not implicitly trustworthy. It may have been entered by users, external integrations, batch jobs, or another vulnerable application.

### 9.1 Unsafe example

~~~sql
SELECT filter_expression
INTO l_filter
FROM report_config
WHERE report_id = p_report_id;

l_sql := 'SELECT * FROM orders WHERE ' || l_filter;
OPEN l_result FOR l_sql;
~~~

If users can modify FILTER_EXPRESSION, this is an untrusted SQL fragment even though the value was read from an internal table.

### 9.2 Safer design

Instead of storing an arbitrary SQL snippet, store structured parameters:

| Configuration column | Example |
|---|---|
| FILTER_STATUS | SHIPPED |
| MIN_AMOUNT | 1000 |
| CREATED_FROM | 2026-01-01 |
| SORT_KEY | ORDER_DATE |
| SORT_DIRECTION | DESC |

When running the report:

- Validate SORT_KEY through an allowlist.
- Validate SORT_DIRECTION as ASC/DESC.
- Bind FILTER_STATUS, MIN_AMOUNT, and CREATED_FROM.
- Build SQL text from a fixed template.

Do not store user-authored SQL fragments and execute them directly.

## 10. Dynamic IN lists

A common mistake is concatenating values into an IN list:

~~~sql
-- Unsafe
l_sql := 'SELECT * FROM orders WHERE order_id IN (' || p_id_list || ')';
~~~

Do not turn a string like "10,20,30" into part of the SQL text. There are two common safe approaches.

### 10.1 Generate placeholders, bind each value

If the number of elements is bounded and known ahead of time, generate a placeholder list:

~~~sql
SELECT *
FROM orders
WHERE order_id IN (:id1, :id2, :id3)
~~~

Then bind each ID via USING or DBMS_SQL. Only the count of placeholders controlled by the program is generated dynamically; actual values remain bound.

When the placeholder count varies and is unknown beforehand, DBMS_SQL may fit better than Native Dynamic SQL because it can bind in a loop.

### 10.2 Using a SQL collection

If an appropriate SQL collection type is available, pass the entire collection as a single bind:

~~~sql
DECLARE
    l_ids SYS.ODCINUMBERLIST :=
        SYS.ODCINUMBERLIST(10, 20, 30);
    l_cursor SYS_REFCURSOR;
BEGIN
    OPEN l_cursor FOR
        'SELECT order_id, status
           FROM orders
          WHERE order_id IN (
              SELECT column_value
              FROM TABLE(:ids)
          )'
        USING l_ids;
END;
/
~~~

The collection value is bound. Verify collection types, bindability, and SQL type syntax in your running release; for custom collections, the SQL type must be declared at schema scope for the SQL engine to use it.

## 11. LIKE and bind variables

Bind variables prevent input from altering SQL syntax, but do not eliminate LIKE wildcard semantics.

Example:

~~~sql
SELECT customer_id, last_name
FROM customers
WHERE last_name LIKE :pattern;
~~~

If pattern is "SMI%", this is a prefix search. If pattern is "%SMI%", this is a contains search. `%` and `_` in input still act as wildcards even when bound.

If the business logic intends to search for a literal string entered by the user, escape wildcards:

~~~sql
SELECT customer_id, last_name
FROM customers
WHERE last_name LIKE :pattern ESCAPE '\';
~~~

The application must replace the escape character, `%`, and `_` in user data with their escaped forms before appending any program-controlled wildcards. Logic example:

~~~text
input:       A_10% 
escaped:     A\_10\%
prefix:      A\_10\%%
~~~

Binds remain the SQL injection defense layer. Wildcard escaping only controls search semantics, not as a replacement for binds.

## 12. Native Dynamic SQL and DBMS_SQL

Oracle provides two main mechanisms to run dynamic SQL from PL/SQL.

### 12.1 Native Dynamic SQL

Uses EXECUTE IMMEDIATE or OPEN FOR. Suitable when the number and types of binds/columns are known at compile time:

~~~sql
EXECUTE IMMEDIATE
    'UPDATE orders SET status = :status WHERE order_id = :id'
USING p_status, p_order_id;
~~~

Advantages:

- Concise, readable syntax.
- Direct integration with PL/SQL variables.
- Supports SELECT INTO, RETURNING INTO, OPEN FOR, and bulk operations.
- Fits most dynamic SQL needs in applications.

### 12.2 DBMS_SQL

DBMS_SQL fits when SQL structure is known only at runtime, such as:

- Unknown number of bind variables beforehand.
- Unknown number of columns in the SELECT list beforehand.
- Need to DESCRIBE columns and handle results generically.
- Need cursor manipulation via parse/bind/define/execute/fetch APIs.

General workflow:

1. OPEN_CURSOR.
2. PARSE SQL text.
3. BIND_VARIABLE for each bind.
4. DEFINE_COLUMN if fetching a result set.
5. EXECUTE.
6. FETCH_ROWS and COLUMN_VALUE.
7. CLOSE_CURSOR in every execution branch.

### 12.3 DBMS_SQL value binding example

~~~sql
DECLARE
    l_cursor INTEGER;
    l_rows   INTEGER;
    l_sql    VARCHAR2(1000);
BEGIN
    l_sql :=
        'UPDATE orders
            SET status = :status
          WHERE customer_id = :customer_id';

    l_cursor := DBMS_SQL.OPEN_CURSOR;

    DBMS_SQL.PARSE(
        l_cursor,
        l_sql,
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.BIND_VARIABLE(
        l_cursor,
        ':status',
        p_status
    );

    DBMS_SQL.BIND_VARIABLE(
        l_cursor,
        ':customer_id',
        p_customer_id
    );

    l_rows := DBMS_SQL.EXECUTE(l_cursor);
    DBMS_SQL.CLOSE_CURSOR(l_cursor);
EXCEPTION
    WHEN OTHERS THEN
        IF DBMS_SQL.IS_OPEN(l_cursor) THEN
            DBMS_SQL.CLOSE_CURSOR(l_cursor);
        END IF;
        RAISE;
END;
/
~~~

Bind variables remain data separate from SQL text. DBMS_SQL does not make dynamic SQL automatically safe; concatenating input into l_sql before PARSE still causes SQL injection.

### 12.4 Converting between DBMS_SQL and REF CURSOR

Oracle provides TO_REFCURSOR and TO_CURSOR_NUMBER to convert between DBMS_SQL cursors and REF CURSORs where appropriate. This is useful when dynamic parsing/describing is needed while returning results through a REF CURSOR interface.

## 13. Dynamic PL/SQL blocks are riskier than dynamic SQL statements

If you only need to run SELECT/INSERT/UPDATE/DELETE, construct the appropriate SQL statement type. Do not wrap it in an anonymous PL/SQL block unnecessarily.

Unsafe example:

~~~sql
l_block :=
    'BEGIN process_order(''' || p_order_id || '''); END;';

EXECUTE IMMEDIATE l_block;
~~~

The input string is injected into PL/SQL source code. If the input alters the block, the user can add other calls or statements within the executing privileges.

Safe example:

~~~sql
EXECUTE IMMEDIATE
    'BEGIN process_order(:order_id); END;'
USING p_order_id;
~~~

The bind placeholder is passed into the procedure as an argument. Do not concatenate values into block source.

If the procedure can be called statically:

~~~sql
BEGIN
    process_order(p_order_id);
END;
/
~~~

direct invocation is even simpler and avoids dynamic PL/SQL altogether.

## 14. Controlling privileges when executing dynamic SQL

A SQL injection vulnerability can be far more severe when code runs with broad privileges.

### 14.1 Definer rights and invoker rights

Stored procedures/functions in PL/SQL run with the owner's privileges (definer rights) by default unless AUTHID CURRENT_USER is declared.

| Mode | General meaning |
|---|---|
| AUTHID DEFINER | Unit runs with the privileges of the schema owning the unit |
| AUTHID CURRENT_USER | Unit runs with the invoker's privileges and current schema/context per Oracle rules |

Example:

~~~sql
CREATE OR REPLACE PROCEDURE app_read_orders (
    p_customer_id IN NUMBER
)
AUTHID DEFINER
AS
BEGIN
    -- SQL in the unit executes under the definer-rights model.
    NULL;
END;
/
~~~

AUTHID DEFINER is the default when AUTHID is omitted. A definer-rights procedure can access objects using the owner's privileges; if it constructs SQL text from untrusted input, a vulnerability can let the caller exploit the owner's privileges.

### 14.2 Least privilege

The schema owning stored procedures should hold only required privileges:

- Grant SELECT only on tables that need to be read.
- Grant INSERT/UPDATE/DELETE only on business tables that need writes.
- Do not grant DBA, CREATE ANY TABLE, or broad system privileges unless required.
- Do not allow dynamic procedures to access arbitrary objects outside an allowlist.
- Separate the code-owning schema from the data-owning schema if the deployment model requires it.

Do not use dynamic SQL to bypass application privilege controls.

### 14.3 AUTHID CURRENT_USER does not replace binds

Invoker rights can make a unit use the caller's privileges, but it does not prevent SQL injection. If SQL text is concatenated from untrusted input, an attacker can still alter the statement within the invoker's privileges.

Conversely, definer rights is not automatically a bug. It fits APIs designed to provide a restricted set of operations. What matters is binding values, allowlisting identifiers, minimal privileges, and controlled interfaces.

### 14.4 Direct privileges and roles

Definer-rights stored PL/SQL typically executes with roles disabled, so object privileges must be granted directly to the owner as required by Oracle. When designing packages, check compile-time and runtime privileges separately; do not grant broad roles just to make dynamic SQL run.

## 15. Measures insufficient to prevent SQL injection

### 15.1 Stripping quotes only

Insufficient. SQL has many syntaxes, comments, operators, encodings, and contexts. Character blacklists are easily bypassed and can corrupt valid data.

### 15.2 Manually doubling single quotes

Example:

~~~sql
REPLACE(p_input, '''', '''''')
~~~

This is not a general solution. Quoting behavior can depend on SQL context, data types, and encoding. For values, bind them.

### 15.3 Using DBMS_ASSERT alone

DBMS_ASSERT checks certain forms of SQL names/literals; it does not decide whether the object is permitted by business rules. A valid, existing name may still be an object the user is not allowed to select.

### 15.4 Relying on low privileges alone

Least privilege limits blast radius, but does not fix the injection bug. An attacker can still read/modify/delete any data the compromised account has access to.

### 15.5 Using a bind for an identifier

Binds cannot substitute table/column names. You must pick identifiers from an allowlist, validate/quote them, and assemble them into the SQL text.

## 16. Workflow for building safe dynamic SQL

A workflow that can be applied to procedures requiring dynamic table, column, or sort order selection:

~~~text
Receive input from application
        |
        v
Classify input
        |
        +-----------------------+
        |                       |
        v                       v
Data values            Identifier/SQL structure
        |                       |
        v                       v
Bind variable              Allowlist mapping
                                |
                                v
                         DBMS_ASSERT validation
                         and identifier quoting
                                |
                                v
                         Assemble into SQL template
        |                       |
        +-----------+-----------+
                    |
                    v
            Execute dynamic SQL
                    |
                    v
        Oracle checks privileges
                    |
                    v
          Write appropriate logs/audit
~~~

Practical steps:

1. Prefer static SQL if the query structure is known.
2. Classify all inputs into values, identifiers, or SQL syntax.
3. Bind all bindable values.
4. For identifiers, map a business key to a fixed object/column.
5. Use DBMS_ASSERT to validate/quote names after the allowlist decides.
6. Generate SQL only from program-controlled templates and fragments.
7. Keep schema privileges minimal.
8. Log SQL_ID, module/action, and necessary business choices without logging secrets or sensitive binds.
9. Test inputs containing quotes, comments, delimiters, Unicode, wildcards, and unusual NLS settings.

## 17. Complete example: reporting API with dynamic table and sort

This example allows the application to choose source ORDERS or ARCHIVE, choose one of three sort keys, and pass status/customer ID.

~~~sql
CREATE OR REPLACE PROCEDURE open_order_report (
    p_source_key     IN VARCHAR2,
    p_sort_key       IN VARCHAR2,
    p_sort_direction IN VARCHAR2,
    p_customer_id    IN NUMBER,
    p_status         IN VARCHAR2,
    p_result         OUT SYS_REFCURSOR
)
AUTHID DEFINER
AS
    l_owner       VARCHAR2(128);
    l_table       VARCHAR2(128);
    l_sort_column VARCHAR2(128);
    l_direction   VARCHAR2(4);
    l_sql         VARCHAR2(4000);
BEGIN
    -- Select object from allowlist.
    CASE UPPER(p_source_key)
        WHEN 'ORDERS' THEN
            l_owner := 'APP';
            l_table := 'ORDERS';
        WHEN 'ARCHIVE' THEN
            l_owner := 'APP';
            l_table := 'ORDERS_ARCHIVE';
        ELSE
            RAISE_APPLICATION_ERROR(-20031, 'Invalid report source');
    END CASE;

    -- Select sort column from allowlist.
    CASE UPPER(p_sort_key)
        WHEN 'DATE' THEN
            l_sort_column := 'ORDER_DATE';
        WHEN 'AMOUNT' THEN
            l_sort_column := 'TOTAL_AMOUNT';
        WHEN 'STATUS' THEN
            l_sort_column := 'STATUS';
        ELSE
            RAISE_APPLICATION_ERROR(-20032, 'Invalid sort key');
    END CASE;

    -- Allow only two sort directions.
    CASE UPPER(p_sort_direction)
        WHEN 'ASC' THEN
            l_direction := 'ASC';
        WHEN 'DESC' THEN
            l_direction := 'DESC';
        ELSE
            RAISE_APPLICATION_ERROR(-20033, 'Invalid sort direction');
    END CASE;

    -- Validate and quote identifiers chosen from the allowlist.
    l_owner := DBMS_ASSERT.SCHEMA_NAME(l_owner);
    l_table := DBMS_ASSERT.SIMPLE_SQL_NAME(l_table);
    l_sort_column := DBMS_ASSERT.SIMPLE_SQL_NAME(l_sort_column);

    l_sql :=
        'SELECT order_id, customer_id, order_date, total_amount, status '
        || 'FROM '
        || DBMS_ASSERT.ENQUOTE_NAME(l_owner)
        || '.'
        || DBMS_ASSERT.ENQUOTE_NAME(l_table)
        || ' WHERE customer_id = :customer_id'
        || ' AND status = :status'
        || ' ORDER BY '
        || DBMS_ASSERT.ENQUOTE_NAME(l_sort_column)
        || ' '
        || l_direction;

    OPEN p_result FOR l_sql
        USING p_customer_id, p_status;
END;
/
~~~

Safe components in the example:

- p_source_key is never concatenated directly; it only selects an owner/table pair from the allowlist.
- p_sort_key only selects a predefined column name.
- p_sort_direction can only be ASC or DESC.
- Owner, table, and column are validated/quoted before entering the SQL text.
- Customer ID and status are data values, so they are bound.
- The stored procedure can only execute against objects the definer has privileges on and the code permits selecting.

In a real system, ensure both tables share the selected column structure. If objects have case-sensitive quoted identifiers, store exact names and use the appropriate quoting mode. Also decide explicitly whether the caller is authorized to view archive data as well; technical allowlists do not replace business authorization.

## 18. Testing SQL injection and dynamic controls

Tests should prove that input data cannot alter SQL syntax, and identifiers outside the allowlist are rejected.

### 18.1 Testing inputs with quotes

With the query:

~~~sql
WHERE username = :username
~~~

test usernames containing single quotes, double hyphens, semicolons, and strings resembling SQL conditions. The value must be compared as data; it must not alter the row count or statement structure beyond comparison semantics.

### 18.2 Testing NLS settings

In a lab environment, change the session's NLS_DATE_FORMAT and NLS_NUMERIC_CHARACTERS and invoke the procedure:

~~~sql
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
~~~

Procedures binding DATE/NUMBER must continue working with the exact values. SQL text must not depend on how DATE/NUMBER are converted to strings.

### 18.3 Testing identifiers outside the allowlist

Send invalid keys such as:

- Disallowed schema names.
- Table names not on the list.
- Names containing dots, quotes, or characters outside identifier grammar.
- Unsupported sort keys.
- Directions other than ASC/DESC.

The API must reject them with a clear business error before executing SQL.

### 18.4 Testing second-order injection

If the system stores report configurations, inspect all write paths and all places reading the configuration back. Do not test only the initial input screen; check stored data used inside dynamic SQL in batch jobs, schedulers, or report workers.

## 19. Common mistakes

| Mistake | Cause | Fix |
|---|---|---|
| Concatenating input into WHERE | Data becomes SQL syntax | Bind variable |
| Binding table/column names | Binds only substitute expression values | Allowlist identifiers and quote |
| Stripping quotes or comments only | Blacklists do not cover SQL grammar | Separate data from code with binds |
| Using DBMS_ASSERT as an allowlist | Valid names may still be unauthorized | Allowlist first, DBMS_ASSERT second |
| Concatenating DATE/NUMBER into SQL | Implicit conversion depends on NLS | Bind with proper types |
| Storing SQL fragments in config tables | Second-order injection when fragments execute | Store structured config, never arbitrary SQL |
| Concatenating ORDER BY from input | Column/direction alters structure | Map sort key/direction to constants |
| Concatenating IN-list from string | List values can alter syntax | Bind each value or bind a collection |
| Using dynamic PL/SQL blocks unnecessarily | Creates a larger injection surface | Use SQL statements or static procedure calls |
| Overly broad definer-rights privileges | Injection exploits owner privileges | Least privilege, allowlists, and binds |
| Assuming invoker-rights prevents injection | Dynamic SQL can still be altered | Still bind, validate, and authorize |
| Not closing DBMS_SQL cursors | Cursor leaks on exceptions | Close cursors in exception handlers |
| Not escaping LIKE wildcards | Input can alter search semantics | Bind and escape `%`/`_` when literal search is needed |

## 20. Security checklist for dynamic SQL

Before deploying dynamic SQL to production, confirm:

1. Can dynamic SQL be replaced by static SQL?
2. Are all data values bound?
3. Are any DATE/NUMBER values concatenated into SQL text via implicit conversion?
4. Are schema/table/column names mapped from an allowlist?
5. Are sort directions and operators chosen from fixed literal sets?
6. Is DBMS_ASSERT used appropriately after allowlisting?
7. Are quoted and case-sensitive identifiers properly understood?
8. Are no untrusted SQL fragments read from tables and executed?
9. Is a dynamic PL/SQL block truly necessary?
10. Are dynamic IN-lists bound per value or via collections?
11. Does LIKE need wildcard escaping to preserve literal semantics?
12. Does the stored procedure run as AUTHID DEFINER or CURRENT_USER, and why?
13. Does the schema owner hold only minimal privileges?
14. Is the caller authorized by business rules to access allowlisted objects?
15. Are exceptions handled without leaking SQL text or sensitive data?
16. Are DBMS_SQL cursors closed across all execution branches?
17. Have NLS_DATE_FORMAT and NLS_NUMERIC_CHARACTERS been tested?
18. Have quotes, comments, delimiters, Unicode, and unusual inputs been tested?
19. Has second-order injection been checked across jobs/reports/configurations?
20. Do logs record sufficient SQL_ID/module/action for investigation without logging secrets or sensitive binds?

## 21. Summary

SQL injection occurs when input data is interpreted as part of SQL/PLSQL code. The most important defense is keeping SQL text fixed and passing values using bind variables.

- Static SQL should be preferred whenever query structure is known.
- Native Dynamic SQL uses EXECUTE IMMEDIATE or OPEN FOR with USING to bind values.
- DBMS_SQL fits when the number of binds or result columns is known only at runtime; it still requires binds and SQL text control.
- Bind variables cannot substitute table names, column names, schemas, keywords, or SQL fragments.
- Dynamic identifiers must be chosen from an allowlist; DBMS_ASSERT helps validate/quote identifiers, but does not grant privileges or decide whether an option is permitted.
- Do not concatenate DATE/NUMBER into SQL text because implicit conversion can depend on NLS and create NLS injection.
- Data read from the database can still be untrusted; second-order injection occurs when stored data is concatenated into SQL at a later step.
- AUTHID DEFINER and broad privileges increase vulnerability impact; use least privilege and design clearly scoped APIs.
- Bind variables both prevent injection and aid cursor sharing, but do not replace business authorization or validation.

Classify every input before constructing SQL: bind values, allowlist and validate/quote identifiers, and select SQL structure only from program-defined options. This is the foundation for safe, controllable, and maintainable dynamic SQL.

## 22. Oracle reference documentation

- Oracle Database 19c PL/SQL Language Reference, “Native Dynamic SQL”: https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/native-dynamic-sql.html
- Oracle Database 19c PL/SQL Packages and Types Reference, “DBMS_ASSERT”: https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ASSERT.html
- Oracle Database 19c PL/SQL Language Reference, “SQL Injection”: https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/sql-injection.html
- Oracle Database 19c PL/SQL Language Reference, “Invokers Rights and Definers Rights”: https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/invokers-rights-and-definers-rights.html
- Oracle Database 19c PL/SQL Packages and Types Reference, “DBMS_SQL”: https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SQL.html
- Oracle Database 19c SQL Language Reference, “Placeholders”: https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/Placeholders.html
- Oracle Database Security Guide, “SQL Injection”: https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/sql-injection.html
