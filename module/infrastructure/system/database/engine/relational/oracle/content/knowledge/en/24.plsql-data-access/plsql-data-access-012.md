# Preventing SQL injection in dynamic SQL and using DBMS_ASSERT in Oracle Database

SQL injection occurs when input data is concatenated into a SQL or PL/SQL statement in a way that alters the structure or meaning of the command. Attackers can cause the application to evaluate unexpected conditions, read unauthorized data, modify data, or invoke operations using the privileges of the schema running the program.

In Oracle, risk commonly arises when using `EXECUTE IMMEDIATE`, `OPEN ... FOR`, or `DBMS_SQL` to build dynamic statements via string concatenation. The most important defense is **using bind variables for all data values**. When dynamic table names, column names, or keywords are needed, choose fixed options from an allowlist and validate names using appropriate `DBMS_ASSERT` functions.

`DBMS_ASSERT` helps validate and quote certain forms of SQL names or literals. This package is an additional layer of defense; it does not replace bind variables, allowlists, authorization checks, or least-privilege design.

This lesson covers how SQL injection forms, vulnerability patterns in dynamic SQL and dynamic PL/SQL, binding values, handling dynamic identifiers, using `DBMS_ASSERT`, preventing NLS and second-order injection, controlling privileges in stored procedures, testing methods, and secure implementation patterns.

## 1. What is SQL injection?

### 1.1. Input data altering SQL structure

Applications often receive data from web/mobile forms, REST APIs, imported files, message queues, scheduled jobs, staging tables, or data previously written by another application.

If an application concatenates data directly into SQL, the input can become part of the SQL syntax rather than just a search value.

Unsafe example:

```sql
DECLARE
    v_sql VARCHAR2(4000);
BEGIN
    v_sql :=
        'SELECT COUNT(*) FROM employees ' ||
        'WHERE last_name = ''' || :p_last_name || '''';

    EXECUTE IMMEDIATE v_sql;
END;
/
```

This code builds SQL by concatenating `p_last_name` between two single quotes. If the data contains quotes or SQL expressions, the condition's structure can be altered.

Do not try to fix this example merely by stripping out a few special characters. SQL has many types of literals, expressions, comments, type conversions, and syntactic contexts. Manual character-filtering rules easily miss edge cases.

### 1.2. Potential impacts

Depending on schema privileges and application structure, SQL injection can lead to:
- Bypassing authentication or data-filtering conditions.
- Reading rows or columns outside authorized scope.
- Modifying or deleting data.
- Invoking unintended procedures/packages.
- Accessing other objects within the same database.
- Triggering errors to probe SQL structure or metadata.

SQL injection does not automatically bypass all Oracle security privileges. The statement still executes with the privileges of the session or PL/SQL program running it. However, if the application connects using an overly privileged schema, the impact can be severe.

### 1.3. SQL injection differs from ordinary input errors

Malformed input can cause data conversion errors or constraint violations without being SQL injection. SQL injection occurs when input data is interpreted as syntax or alters statement structure.

Examples:
- Entering letters into a `NUMBER` field can cause a conversion error.
- Entering a quote into a bound string remains purely data.
- Concatenating a quote into dynamic SQL without proper handling can alter the SQL expression.

Defense should rely on how statements are constructed, not on assuming users will only submit normal characters.

## 2. Dynamic SQL locations prone to SQL injection

### 2.1. EXECUTE IMMEDIATE

`EXECUTE IMMEDIATE` executes a SQL statement or PL/SQL block built at runtime. If the SQL string contains untrusted data via concatenation, injection risk appears.

Unsafe:

```sql
v_sql :=
    'DELETE FROM orders WHERE customer_id = ' ||
    p_customer_id;

EXECUTE IMMEDIATE v_sql;
```

Even when `p_customer_id` is typed as `NUMBER`, converting it to text and concatenating it into the command is unnecessary. Use a bind:

```sql
v_sql :=
    'DELETE FROM orders WHERE customer_id = :1';

EXECUTE IMMEDIATE v_sql
    USING p_customer_id;
```

### 2.2. OPEN FOR with REF CURSOR

Dynamic queries using `OPEN ... FOR` are also vulnerable if data is concatenated.

Unsafe:

```sql
v_sql :=
    'SELECT order_id, total_amount ' ||
    'FROM orders WHERE customer_id = ' ||
    p_customer_id;

OPEN p_result FOR v_sql;
```

Safer:

```sql
v_sql :=
    'SELECT order_id, total_amount ' ||
    'FROM orders WHERE customer_id = :customer_id';

OPEN p_result FOR v_sql
    USING p_customer_id;
```

`REF CURSOR` does not automatically make SQL safe. What decides safety is how the string is built and how values are passed.

### 2.3. Dynamic PL/SQL blocks

Not only `SELECT`/`INSERT`/`UPDATE`/`DELETE` carry risk. Concatenating data into a dynamic PL/SQL block can also allow input to alter the executed commands.

Dangerous example:

```sql
v_block :=
    'BEGIN process_order(''' ||
    p_order_code ||
    '''); END;';

EXECUTE IMMEDIATE v_block;
```

If you only need to pass parameters to a procedure, bind them:

```sql
v_block := 'BEGIN process_order(:order_code); END;';

EXECUTE IMMEDIATE v_block
    USING p_order_code;
```

Never embed input data into the body of a block when it can be passed as a parameter.

### 2.4. DBMS_SQL

`DBMS_SQL` lets you parse, bind, and execute dynamic statements step by step. This package does not automatically protect applications from SQL injection. If the string is built by concatenating untrusted data, the risk remains.

Use the `DBMS_SQL` bind API to pass values. Use `DBMS_SQL` only when you need dynamic SQL capabilities that Native Dynamic SQL does not conveniently provide, such as handling column counts or result types unknown at compile time.

## 3. Bind variables as the primary defense for data values

### 3.1. Separating values from syntax

A bind variable is a placeholder in SQL. The value is passed separately at execution time rather than concatenated into the SQL string.

```sql
DECLARE
    v_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM employees WHERE department_id = :dept'
        INTO v_count
        USING 10;

    DBMS_OUTPUT.PUT_LINE('Count = ' || v_count);
END;
/
```

The value `10` is bound to the placeholder. If a user passes a string containing quotes or SQL keywords into a `VARCHAR2` bind, Oracle treats it as predicate data and never interprets it as SQL syntax.

### 3.2. Binding for INSERT, UPDATE, and DELETE

INSERT:

```sql
EXECUTE IMMEDIATE
    'INSERT INTO audit_events(event_type, actor_id) ' ||
    'VALUES (:event_type, :actor_id)'
USING p_event_type, p_actor_id;
```

UPDATE:

```sql
EXECUTE IMMEDIATE
    'UPDATE employees SET salary = :salary ' ||
    'WHERE employee_id = :employee_id'
USING p_salary, p_employee_id;
```

DELETE:

```sql
EXECUTE IMMEDIATE
    'DELETE FROM orders WHERE order_id = :order_id'
USING p_order_id;
```

In each case, the SQL statement maintains a fixed structure and values are passed separately.

### 3.3. Binding dates, numbers, and strings

Do not convert values to text and concatenate them into SQL. Binding with proper data types avoids formatting and NLS errors.

Binding `DATE`:

```sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM orders WHERE order_date >= :from_date'
    INTO v_count
    USING p_from_date;
```

Binding `NUMBER`:

```sql
EXECUTE IMMEDIATE
    'UPDATE accounts SET balance = balance - :amount ' ||
    'WHERE account_id = :account_id'
USING p_amount, p_account_id;
```

Binding strings:

```sql
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM employees WHERE last_name = :last_name'
    INTO v_count
    USING p_last_name;
```

Do not use `TO_CHAR` to turn dates or numbers into SQL literal fragments when you can bind directly.

### 3.4. Bind order in Native Dynamic SQL

For a dynamic SQL statement, positional placeholders are matched with expressions in `USING` in order of appearance.

```sql
EXECUTE IMMEDIATE
    'UPDATE employees ' ||
    'SET salary = :x ' ||
    'WHERE employee_id = :y'
USING p_salary, p_employee_id;
```

Here the first bind is salary and the second bind is `employee_id`.

For a dynamic anonymous PL/SQL block or `CALL` statement, placeholder handling rules differ when the same placeholder name appears multiple times. To avoid confusion, name placeholders clearly and consult the Native Dynamic SQL rules in the Oracle documentation for your version. Do not assume every case supports matching by name.

### 3.5. Binds cannot replace table names or column names

Binds only substitute expression values. They cannot be used for identifiers or keywords:

```sql
-- Invalid to bind a table name:
EXECUTE IMMEDIATE
    'SELECT COUNT(*) FROM :table_name'
    INTO v_count
    USING p_table_name;
```

Oracle must know object names when parsing the SQL statement. Thus, table/column names must be in the SQL string before parsing. This is where allowlists and `DBMS_ASSERT` apply, as covered in the sections below.

### 3.6. Binding IN lists

You cannot treat a `VARCHAR2` bind containing `10,20,30` as a list of three values in an `IN (:ids)` predicate. Oracle treats it as a single scalar value.

If filtering by multiple IDs is needed, you can:
- Use an SQL collection type and `TABLE()` when the collection type is declared appropriately.
- Use `JSON_TABLE` with bound JSON.
- Generate a number of placeholders matching the element count, binding each value individually.
- Load IDs into a staging table or global temporary table and join against it.

Example creating a schema-level collection type:

```sql
CREATE TYPE number_list_t AS TABLE OF NUMBER;
/
```

Using the collection:

```sql
SELECT e.employee_id, e.last_name
FROM   employees e
WHERE  e.department_id IN (
    SELECT column_value
    FROM   TABLE(:department_ids)
);
```

Direct collection binding capability depends on context and driver. In applications, use the appropriate Oracle JDBC/driver collection binding API; otherwise, use a staging table or generate individual placeholders per element.

## 4. Dynamic SQL with varying identifiers

### 4.1. Why do identifiers need separate handling?

A report may allow users to select a sort column:

```sql
SELECT order_id, order_date, total_amount
FROM orders
ORDER BY <selected_column>;
```

`selected_column` is a column name, not a data value. Oracle does not permit binding a column name in that position. The application must assemble a SQL fragment from an allowed set of options.

Never concatenate a client-supplied string directly:

```sql
-- Unsafe:
v_sql := 'SELECT * FROM orders ORDER BY ' || p_sort_column;
```

Input could include extra unintended syntax.

### 4.2. Allowlisting is the preferred choice

Instead of accepting any column name, map a selection code to a fixed SQL fragment:

```sql
CASE UPPER(p_sort_key)
    WHEN 'DATE' THEN
        v_sort_column := 'ORDER_DATE';
    WHEN 'AMOUNT' THEN
        v_sort_column := 'TOTAL_AMOUNT';
    WHEN 'ID' THEN
        v_sort_column := 'ORDER_ID';
    ELSE
        RAISE_APPLICATION_ERROR(-20001, 'Unsupported sort option');
END CASE;
```

The value concatenated into the statement can only be one of three developer-defined column names. External input merely selects one valid branch.

### 4.3. Allowlisting sort directions

Never concatenate `ASC` or `DESC` directly from the user. Map the selection:

```sql
CASE UPPER(p_sort_direction)
    WHEN 'ASC' THEN
        v_direction := 'ASC';
    WHEN 'DESC' THEN
        v_direction := 'DESC';
    ELSE
        RAISE_APPLICATION_ERROR(-20002, 'Unsupported sort direction');
END CASE;
```

Then concatenate `v_direction`, which can only hold two fixed values. Apply the same principle to operators, schema names, table names, join fragments, and all dynamic SQL structural parts.

### 4.4. Identifiers sourced from metadata

Some administrative or reporting tools must pick tables/columns from metadata. Even when names come from the data dictionary, verify:
- Does the object belong to an allowed schema?
- Is the object of the right type?
- Is the name in the application's allowed list?
- Does the caller have privileges to perform that operation?

A syntactically valid name does not imply the name is permitted for the feature being built.

## 5. What is DBMS_ASSERT?

### 5.1. Input validation package for dynamic SQL

`DBMS_ASSERT` is an Oracle package providing functions to validate certain forms of SQL identifiers or literals. It helps confirm that a string conforms to a supported SQL naming context.

Common functions:
- `SIMPLE_SQL_NAME`
- `QUALIFIED_SQL_NAME`
- `SCHEMA_NAME`
- `SQL_OBJECT_NAME`
- `ENQUOTE_NAME`
- `ENQUOTE_LITERAL`
- `NOOP`

These functions do not make arbitrary strings safe in every SQL position. Choose the function matching the exact context and still restrict privileges, objects, and permitted operations.

### 5.2. SIMPLE_SQL_NAME

`DBMS_ASSERT.SIMPLE_SQL_NAME` verifies whether a string is a valid simple SQL name. It returns the string if valid; otherwise, it raises an exception.

```sql
DECLARE
    v_name VARCHAR2(128);
BEGIN
    v_name := DBMS_ASSERT.SIMPLE_SQL_NAME('EMPLOYEES');
    DBMS_OUTPUT.PUT_LINE(v_name);
END;
/
```

This function checks simple identifier syntax. It does not confirm that a column or table exists, nor that the caller is authorized to access it.

### 5.3. ENQUOTE_NAME

`DBMS_ASSERT.ENQUOTE_NAME` validates a simple SQL name and encloses it in double quotes per Oracle identifier rules:

```sql
DECLARE
    v_quoted_name VARCHAR2(300);
BEGIN
    v_quoted_name := DBMS_ASSERT.ENQUOTE_NAME(
        'EMPLOYEES',
        capitalize => TRUE
    );

    DBMS_OUTPUT.PUT_LINE(v_quoted_name);
END;
/
```

The `capitalize` parameter defaults to `TRUE`. If preserving uppercase/lowercase of a quoted name is needed, pass `FALSE`. Quoted identifiers in Oracle are case-sensitive, so use it consistently with how the object was created.

`ENQUOTE_NAME` does not check whether the object exists or whether the caller has access. It only assists in validating/quoting a name per simple SQL name grammar.

### 5.4. QUALIFIED_SQL_NAME

`DBMS_ASSERT.QUALIFIED_SQL_NAME` checks a qualified SQL name per Oracle syntax, such as a name with schema and object components:

```sql
DECLARE
    v_name VARCHAR2(300);
BEGIN
    v_name := DBMS_ASSERT.QUALIFIED_SQL_NAME('APP.EMPLOYEES');
    DBMS_OUTPUT.PUT_LINE(v_name);
END;
/
```

This function validates qualified name syntax per Oracle rules. Do not treat its result as confirmation that the object exists, belongs to an allowlist, or is authorized for business access. If confirming object existence is needed, see `SQL_OBJECT_NAME` and additionally verify allowed schemas/objects.

### 5.5. SCHEMA_NAME

`DBMS_ASSERT.SCHEMA_NAME` checks a schema name and confirms the corresponding schema exists in the database:

```sql
DECLARE
    v_schema VARCHAR2(128);
BEGIN
    v_schema := DBMS_ASSERT.SCHEMA_NAME('HR');
    DBMS_OUTPUT.PUT_LINE(v_schema);
END;
/
```

Schema existence does not mean the application should let users access every object in that schema. Allowlists and authorization checks are still required.

### 5.6. SQL_OBJECT_NAME

`DBMS_ASSERT.SQL_OBJECT_NAME` validates a qualified SQL object name and confirms the corresponding object exists per package rules:

```sql
DECLARE
    v_object_name VARCHAR2(300);
BEGIN
    v_object_name := DBMS_ASSERT.SQL_OBJECT_NAME('HR.EMPLOYEES');
    DBMS_OUTPUT.PUT_LINE(v_object_name);
END;
/
```

This function is useful when dynamic SQL must reference an existing object. However, an existing object may still lie outside the scope a user is allowed to touch. Never use `SQL_OBJECT_NAME` as a substitute for authorization policy.

### 5.7. ENQUOTE_LITERAL

`DBMS_ASSERT.ENQUOTE_LITERAL` quotes a string as a SQL character literal:

```sql
DECLARE
    v_literal VARCHAR2(4000);
BEGIN
    v_literal := DBMS_ASSERT.ENQUOTE_LITERAL('O''Brien');
    DBMS_OUTPUT.PUT_LINE(v_literal);
END;
/
```

This function can be helpful when constructing a literal in special situations. However, for ordinary data values, **bind variables remain the preferred choice**. Manual literal quoting easily leads to context mistakes, type conversion issues, or errors in complex SQL.

Do not use `ENQUOTE_LITERAL` to quote table/column names; identifiers and string literals are two different syntactic contexts.

### 5.8. NOOP

`DBMS_ASSERT.NOOP` returns the input string without performing meaningful security validation. Never use `NOOP` as a measure to validate identifiers or prevent SQL injection.

### 5.9. Function selection table

| Function | Purpose | Does not guarantee |
| --- | --- | --- |
| SIMPLE_SQL_NAME | Validates a simple identifier | Object exists or caller has privileges |
| ENQUOTE_NAME | Validates and quotes a simple identifier | Object exists or is in allowlist |
| QUALIFIED_SQL_NAME | Validates a qualified SQL name | Object is permitted for business use |
| SCHEMA_NAME | Verifies schema exists | Caller has permission to access schema |
| SQL_OBJECT_NAME | Verifies SQL object name exists | Object is allowlisted or safe for all operations |
| ENQUOTE_LITERAL | Quotes a character literal | Replacing binds for ordinary values |
| NOOP | Returns string unchanged | Performs no validation; do not use for protection |

Function names and behavioral details should be cross-referenced against the `DBMS_ASSERT` documentation for your exact Oracle version.

## 6. Combining allowlists and DBMS_ASSERT

### 6.1. Two-layer validation

For dynamic identifiers:
1. Validate the business selection against an allowlist.
2. Use `DBMS_ASSERT` to validate/quote the name in the right context.
3. Concatenate the controlled identifier into SQL.
4. Bind all remaining data values.
5. Execute with least required privileges.

The allowlist answers "Does the application allow this choice?". `DBMS_ASSERT` helps answer "Does the string conform to identifier syntax?".

### 6.2. Safe sort column example

```sql
DECLARE
    v_column_name VARCHAR2(30);
    v_quoted_name VARCHAR2(300);
    v_direction   VARCHAR2(4);
    v_sql         VARCHAR2(4000);
    v_cursor      SYS_REFCURSOR;
BEGIN
    CASE UPPER(p_sort_key)
        WHEN 'DATE' THEN
            v_column_name := 'ORDER_DATE';
        WHEN 'AMOUNT' THEN
            v_column_name := 'TOTAL_AMOUNT';
        WHEN 'ID' THEN
            v_column_name := 'ORDER_ID';
        ELSE
            RAISE_APPLICATION_ERROR(-20001, 'Invalid sort key');
    END CASE;

    CASE UPPER(p_direction)
        WHEN 'ASC' THEN
            v_direction := 'ASC';
        WHEN 'DESC' THEN
            v_direction := 'DESC';
        ELSE
            RAISE_APPLICATION_ERROR(-20002, 'Invalid direction');
    END CASE;

    v_quoted_name :=
        DBMS_ASSERT.ENQUOTE_NAME(v_column_name);

    v_sql :=
        'SELECT order_id, order_date, total_amount ' ||
        'FROM orders ' ||
        'WHERE customer_id = :customer_id ' ||
        'ORDER BY ' || v_quoted_name || ' ' || v_direction;

    OPEN v_cursor FOR v_sql
        USING p_customer_id;
END;
/
```

Only the column name and sort direction are concatenated into SQL, and both come from fixed value sets. Customer ID is bound. In a real procedure, return the `REF CURSOR` to the caller or fetch and close the cursor per design.

### 6.3. Dynamic schema and object names

If an application has an admin feature that selects objects, do not simply call `SQL_OBJECT_NAME` on arbitrary user-supplied strings and permit unrestricted queries.

Map the selection code to an allowed object:

```sql
CASE UPPER(p_report_code)
    WHEN 'CURRENT_ORDERS' THEN
        v_object_name := 'APP.ORDERS';
    WHEN 'ARCHIVE_ORDERS' THEN
        v_object_name := 'APP.ORDERS_ARCHIVE';
    ELSE
        RAISE_APPLICATION_ERROR(-20010, 'Unknown report');
END CASE;

v_object_name :=
    DBMS_ASSERT.SQL_OBJECT_NAME(v_object_name);

v_sql :=
    'SELECT COUNT(*) FROM ' || v_object_name;

EXECUTE IMMEDIATE v_sql INTO v_count;
```

The allowlist ensures only two objects are used by this feature. `SQL_OBJECT_NAME` adds a check that the object is valid/existing. The executing schema's privileges must still be restricted.

### 6.4. Do not allow users to submit raw WHERE clauses

A risky design is accepting a `p_where_clause` parameter and concatenating it:

```sql
v_sql := 'SELECT * FROM orders WHERE ' || p_where_clause;
```

`DBMS_ASSERT` is not a general-purpose SQL parser capable of proving an arbitrary `WHERE` clause contains only safe predicates. Instead, accept separate data fields such as customer ID, status, start/end dates, and build predicates from fixed branches with bind variables.

## 7. Advanced forms of SQL injection

### 7.1. Second-order SQL injection

Second-order injection happens when dangerous data is stored first, and another program later reads that stored data and concatenates it into dynamic SQL.

Example:
1. A screen lets a user save a report name or configuration value.
2. The data is stored in a table.
3. An admin job reads the stored data.
4. The job concatenates that string into dynamic SQL.
5. The SQL structure is altered when the job runs.

Data read from the database is not inherently trustworthy. Its origin may be users, integration systems, imports, or other applications. Bind variables and allowlists must still be enforced at SQL construction time, not only on the input form.

### 7.2. NLS injection

Oracle can convert `NUMBER` or `DATE` to text according to NLS settings if code concatenates values into SQL.

Risky design example:

```sql
v_sql :=
    'SELECT * FROM orders WHERE order_date = ''' ||
    p_date ||
    '''';
```

Converting `DATE` to text can depend on `NLS_DATE_FORMAT` or session settings. In unsafe scenarios, session-controlled NLS formats can alter the generated SQL string.

The best approach is to bind `DATE`:

```sql
v_sql := 'SELECT * FROM orders WHERE order_date = :d';

OPEN p_cursor FOR v_sql USING p_date;
```

If you need text for display or logging, use `TO_CHAR` with a fixed format mask; never use a formatted string to replace a bind in a predicate.

Similarly for `NUMBER`, bind directly to avoid depending on `NLS_NUMERIC_CHARACTERS`.

### 7.3. Injection through LIKE

Using bind variables prevents values from becoming SQL syntax, yet `%` and `_` still act as wildcards in `LIKE`. This is usually a search-semantics issue rather than SQL injection.

If business logic needs to match literal `%` or `_` characters, escape the wildcards:

```sql
SELECT employee_id, last_name
FROM employees
WHERE last_name LIKE :p_pattern ESCAPE '\';
```

The application must escape the escape character, `%`, and `_` in the right order before binding. Distinguish:
- SQL injection: input alters SQL syntax.
- Wildcard injection: input broadens `LIKE` results unintentionally.

### 7.4. Injection in object names and database links

Schema names, table names, column names, sequences, database links, or partition names can appear in dynamic SQL. These identifiers cannot be bound. You must:
- Use an explicit object allowlist.
- Specify allowed schemas.
- Verify object types if required by business logic.
- Use the appropriate `DBMS_ASSERT` function for identifiers.
- Never allow users to choose arbitrary database links.

A database link can open access to another system using configured credentials. Do not let users control a database link merely because its name is syntactically valid.

### 7.5. Injection in ORDER BY and expressions

`ORDER BY` often requires choosing a column or sort direction. Never concatenate arbitrary client-submitted expressions. Use selection codes mapped to fixed SQL fragments. The same principle applies to:
- Column names in the `SELECT` list.
- Join conditions.
- Comparison operators.
- Table or view names.
- Partition names.
- `ASC`/`DESC` directions.
- Function names or expressions.

## 8. Workflow for writing safe dynamic SQL

### 8.1. Classify each component

| Component | Example | Handling |
| --- | --- | --- |
| Data values | ID, name, amount, date | Bind variable |
| Table/column names | ORDERS, ORDER_DATE | Allowlist + appropriate DBMS_ASSERT |
| Keywords/syntax fragments | ASC, DESC, JOIN type | Fixed allowlist |
| Dynamic predicates | Optional filters | Concatenate code-controlled fragments; bind values |
| Complete SQL submitted by user | Arbitrary SQL text | Do not execute as normal input |

### 8.2. Building fixed fragments

Example of optional filters:

```sql
v_sql := 'SELECT order_id, customer_id, status FROM orders WHERE 1=1';

IF p_customer_id IS NOT NULL THEN
    v_sql := v_sql || ' AND customer_id = :customer_id';
END IF;

IF p_status IS NOT NULL THEN
    v_sql := v_sql || ' AND status = :status';
END IF;
```

The fragments `AND customer_id = :customer_id` and `AND status = :status` are defined by the program. No syntax comes directly from the user.

When many condition combinations exist, managing bind order can become complex. Write explicit branches with matching `USING` lists, or use `DBMS_SQL` when bind counts vary dynamically.

### 8.3. Example of explicit bind branches

```sql
IF p_customer_id IS NOT NULL
   AND p_status IS NOT NULL
THEN
    v_sql :=
        'SELECT order_id, total_amount FROM orders ' ||
        'WHERE customer_id = :1 AND status = :2';

    OPEN p_result FOR v_sql
        USING p_customer_id, p_status;

ELSIF p_customer_id IS NOT NULL THEN
    v_sql :=
        'SELECT order_id, total_amount FROM orders ' ||
        'WHERE customer_id = :1';

    OPEN p_result FOR v_sql
        USING p_customer_id;

ELSIF p_status IS NOT NULL THEN
    v_sql :=
        'SELECT order_id, total_amount FROM orders ' ||
        'WHERE status = :1';

    OPEN p_result FOR v_sql
        USING p_status;

ELSE
    v_sql :=
        'SELECT order_id, total_amount FROM orders';

    OPEN p_result FOR v_sql;
END IF;
```

This is longer, but makes each structure and bind order explicit. For larger filters, use `DBMS_SQL` or a query builder with controlled bind rules.

### 8.4. Dynamic DDL

Many DDL statements do not support binds for object names or syntax attributes. When creating tables/indexes/partitions dynamically:
- Allow object names only from an allowlist or internal naming conventions.
- Use `DBMS_ASSERT` to validate/quote identifiers.
- Restrict data types, tablespaces, and partition options via enums/allowlists.
- Never concatenate user-supplied DDL fragments directly.
- Run under an administrative account with least required privileges, separated from ordinary application schemas.

Never use `DBMS_ASSERT` to validate an entire DDL string supplied by a user.

## 9. DBMS_ASSERT does not replace authorization

### 9.1. A valid identifier is not necessarily permitted

For example, `HR.EMPLOYEES` may be a valid and existing object name. Yet a feature restricted to reporting on `APP.ORDERS` should never accept `HR.EMPLOYEES` merely because `SQL_OBJECT_NAME` confirms it exists.

An allowlist is the business control layer; `DBMS_ASSERT` is the name-syntax validation layer.

### 9.2. Privileges of definer-rights procedures

Stored procedures default to definer rights (`AUTHID DEFINER`). This causes the procedure to run with the owner's privileges. If a procedure accepts arbitrary object names and runs dynamic SQL, it can inadvertently expose broad owner privileges to callers.

Safe design:
- Expose only specific business operations, never a generic SQL console.
- Restrict objects and operations with allowlists.
- Grant least privileges to the owner.
- Never use an application schema with DBA privileges.
- Verify caller authorization before sensitive operations.

### 9.3. AUTHID CURRENT_USER

A procedure can declare `AUTHID CURRENT_USER` to use invoker rights under Oracle semantics:

```sql
CREATE OR REPLACE PROCEDURE read_allowed_data (
    p_id IN NUMBER
)
AUTHID CURRENT_USER
AS
    v_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM allowed_table WHERE id = :1'
    INTO v_count
    USING p_id;
END;
/
```

Invoker rights change name resolution and privilege evaluation for the program. They do not eliminate SQL injection by themselves. Bind variables, allowlists, and authorization checks are still required. Choose `DEFINER` or `CURRENT_USER` based on security architecture, not as a standalone injection fix.

### 9.4. Least privilege

The application connection account should only have:
- Required privileges on the tables/views/procedures it uses.
- No object creation/drop privileges unless business logic requires them.
- No database administration privileges.
- No out-of-scope access to other schemas.
- `EXECUTE` privileges on only the needed packages/procedures.

If injection occurs, least privilege limits what an exploited statement can do.

## 10. Safe search procedure patterns

### 10.1. Procedure with bound values

```sql
CREATE OR REPLACE PROCEDURE find_orders (
    p_customer_id IN  orders.customer_id%TYPE,
    p_from_date   IN  DATE,
    p_result      OUT SYS_REFCURSOR
)
AUTHID DEFINER
AS
    v_sql VARCHAR2(4000);
BEGIN
    v_sql :=
        'SELECT order_id, order_date, total_amount ' ||
        'FROM orders ' ||
        'WHERE customer_id = :customer_id ' ||
        'AND order_date >= :from_date ' ||
        'ORDER BY order_date DESC';

    OPEN p_result FOR v_sql
        USING p_customer_id, p_from_date;
END;
/
```

The procedure generates only fixed-structure SQL. Customer and date are bound. The caller must still be authorized to invoke the procedure per application rules.

### 10.2. Procedure allowing sort column selection

```sql
CREATE OR REPLACE PROCEDURE find_orders_sorted (
    p_customer_id IN orders.customer_id%TYPE,
    p_sort_key    IN VARCHAR2,
    p_result      OUT SYS_REFCURSOR
)
AUTHID DEFINER
AS
    v_sort_column VARCHAR2(30);
    v_sql         VARCHAR2(4000);
BEGIN
    CASE UPPER(p_sort_key)
        WHEN 'DATE' THEN
            v_sort_column := 'ORDER_DATE';
        WHEN 'AMOUNT' THEN
            v_sort_column := 'TOTAL_AMOUNT';
        WHEN 'ID' THEN
            v_sort_column := 'ORDER_ID';
        ELSE
            RAISE_APPLICATION_ERROR(-20020, 'Invalid sort key');
    END CASE;

    v_sort_column :=
        DBMS_ASSERT.ENQUOTE_NAME(v_sort_column);

    v_sql :=
        'SELECT order_id, order_date, total_amount ' ||
        'FROM orders ' ||
        'WHERE customer_id = :1 ' ||
        'ORDER BY ' || v_sort_column;

    OPEN p_result FOR v_sql
        USING p_customer_id;
END;
/
```

The column name is mapped from an allowlist and quoted via `ENQUOTE_NAME`. Customer ID is bound. To support `ASC`/`DESC`, map the sort direction through a separate `CASE`, never concatenating raw input.

### 10.3. Error handling

Never return complete dynamic SQL, stack traces, or internal metadata to end clients. Log error codes and correlation IDs in controlled logs while returning an appropriate message to the client.

During development, DBAs/developers may log `SQL_ID` or parameterized SQL statements for investigation. Do not log sensitive bind values unnecessarily.

## 11. Testing and reviewing for SQL injection

### 11.1. Source code review

Locate all occurrences of:
- `EXECUTE IMMEDIATE`
- `OPEN ... FOR`
- `DBMS_SQL.PARSE`
- Strings concatenated with procedure parameters or external inputs.
- Dynamic DDL.
- Stored procedures accepting table names, column names, or `WHERE` clauses.
- Jobs reading data from configuration tables and concatenating it into SQL.

For each location, trace data sources, usage context, and how binding/validation is performed.

### 11.2. Testing with benign anomalous inputs

In a test environment, test:
- Strings with single quotes.
- Strings with comment markers.
- Unusually long strings.
- Non-existent object names.
- Valid object names outside the allowlist.
- Values containing `%` and `_` wildcards when using `LIKE`.
- Dates/numbers under different NLS settings.
- Previously stored data later reused in dynamic SQL.

The goal is to confirm input is always treated as data or rejected by the allowlist, never altering SQL statement structure.

### 11.3. Privilege testing

Test procedures with:
- A valid user with business permissions.
- A user without permissions.
- A user attempting to pick an object outside the allowlist.
- A user invoking the feature with a different schema.
- A user passing a valid object name outside allowed scope.

Verify execution outcomes against designed privileges, not merely string validity.

### 11.4. Regression testing

After remediation:
- Confirm query results are accurate for valid inputs.
- Confirm anomalous inputs do not alter SQL structure.
- Confirm errors are handled consistently.
- Check execution plans if binding or query structure changed.
- Verify transactions and side effects.
- Confirm logs do not expose sensitive data.

## 12. Common mistakes and misconceptions

| Misconception or mistake | Explanation |
| --- | --- |
| Using DBMS_ASSERT on all input is enough | No; values must be bound and identifiers allowlisted |
| Table names can be bound | No; binds are only for expression values |
| Manually replacing quotes is enough to quote strings | Easily misses cases and syntactic contexts |
| SQL_OBJECT_NAME proves caller has privileges | No; it does not replace authorization |
| SIMPLE_SQL_NAME confirms the object exists | No; it checks simple-name syntax only |
| ENQUOTE_NAME is for string literals | No; it is for identifiers |
| ENQUOTE_LITERAL replaces binding | No; binding remains preferred for values |
| Data read from the database is always trustworthy | False; it may contain prior user input |
| Concatenating NUMBER/DATE as text is always safe | No; it can be affected by NLS conversions |
| LIKE wildcards are SQL injection | Not necessarily; they are wildcard semantics needing separate escaping |
| Definer-rights procedures carry no risk | False; owner privileges can amplify impact |
| Catching OTHERS and ignoring errors is safe | False; it hides failures and leaves transactions in unexpected states |

### 12.1. Distinguishing the three control layers

- **Bind variables:** separate data values from SQL syntax.
- **DBMS_ASSERT:** validates/quotes certain identifiers or literals in specific contexts.
- **Authorization/allowlists:** decide which objects/features a caller is permitted to act upon.

These three layers complement each other. None completely replaces the other two.

## 13. Pre-production checklist for dynamic SQL

1. Are all data values bound?
2. Is input concatenated directly into any SQL/PLSQL string anywhere?
3. Do dynamic identifiers have an explicit allowlist?
4. Is `DBMS_ASSERT` used in the right name/literal context?
5. Are clients prevented from submitting raw `WHERE` clauses or SQL fragments?
6. Is data read from configuration tables (second-order) treated as untrusted input?
7. Are `DATE`/`NUMBER` values converted to text via NLS before SQL concatenation?
8. Are `LIKE` wildcards distinguished from SQL injection?
9. Does the procedure run with definer rights or invoker rights, and are privileges minimal?
10. Is caller authorization checked per business rules?
11. Do errors/logs leak SQL, bind data, or sensitive information?
12. Have anomalous inputs and regression tests been executed in a test environment?

## 14. Practice exercises

### Exercise 1 — Identifying SQL injection

Review the code concatenating `p_last_name` into the `SELECT` in section 1. Explain why a single quote in data can alter syntax.

### Exercise 2 — Switching to bind variables

Rewrite the employee lookup example using `EXECUTE IMMEDIATE ... USING`. Test with surnames containing apostrophes such as `O'Brien`.

### Exercise 3 — Binding UPDATE and DELETE

Write two blocks updating salary and deleting an order by ID. Ensure all values are bound.

### Exercise 4 — Dynamic query with REF CURSOR

Write a procedure opening a `REF CURSOR` by customer ID and start date. Use `OPEN FOR ... USING`.

### Exercise 5 — Sort key allowlist

Allow sorting by `DATE`, `AMOUNT`, or `ID`. Reject all other choices with `RAISE_APPLICATION_ERROR`. Never concatenate `p_sort_key` directly.

### Exercise 6 — Using SIMPLE_SQL_NAME

Test `SIMPLE_SQL_NAME` with valid column names and strings containing spaces/syntax characters. Observe the exceptions and explain the function's limitations.

### Exercise 7 — Using ENQUOTE_NAME

Quote a column name from an allowlist using `ENQUOTE_NAME`. Test the difference between `capitalize` `TRUE`/`FALSE` and explain the impact of quoted identifiers.

### Exercise 8 — Distinguishing QUALIFIED_SQL_NAME and SQL_OBJECT_NAME

Test `APP.ORDERS`, a non-existent object name, and a syntactically invalid string. Note which function checks syntax and which checks object existence per version documentation.

### Exercise 9 — NLS conversion

Write an unsafe example concatenating `DATE` into SQL text. Then replace it by binding `DATE` and explain why it no longer depends on `NLS_DATE_FORMAT`.

### Exercise 10 — Second-order injection

Design a table storing report names. Write a job reading the name from the table and using it in dynamic SQL. Fix it so report names are mapped strictly through an allowlist.

### Exercise 11 — LIKE wildcards

Write a query searching for literal strings containing `%` or `_`. Bind the pattern and escape wildcards properly using `ESCAPE` syntax.

### Exercise 12 — Authorization

Create a definer-rights procedure allowing queries only on two allowlisted report tables. Verify callers cannot select other objects even if those objects exist.

### Exercise 13 — Dynamic DDL

Write a script creating a demo table with a name generated by internal rules. Use allowlist/`DBMS_ASSERT` for the identifier and fix data types, tablespace, and constraints; never accept raw DDL from users.

### Exercise 14 — Source review

Find all `EXECUTE IMMEDIATE`, `OPEN FOR`, and `DBMS_SQL.PARSE` calls in a PL/SQL project. Classify them into:
- Fixed structure, bound values.
- Identifier allowlist + `DBMS_ASSERT`.
- Needs refactoring due to untrusted input concatenation.

## 15. Oracle reference documentation

- [Oracle Database PL/SQL Packages and Types Reference — DBMS_ASSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ASSERT.html): functions to validate and quote SQL names/literals.
- [Oracle Database PL/SQL Language Reference — Native Dynamic SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dynamic-sql.html): EXECUTE IMMEDIATE, OPEN FOR, and bind arguments.
- [Oracle Database PL/SQL Language Reference — DBMS_SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/DBMS_SQL.html): dynamic SQL with DBMS_SQL.
- [Oracle Database Security Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/dbseg/): database security principles and privileges.
- [Oracle Database SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/): SQL syntax, identifiers, and literals.
- [Oracle Database PL/SQL Packages and Types Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/): PL/SQL packages and APIs.

When writing dynamic SQL, keep the SQL structure controlled by the program and pass all values via bind variables. When table names, column names, or keywords must vary, pick from an allowlist and then use appropriate `DBMS_ASSERT` calls to validate/quote identifiers. Treat data stored in the database as potentially untrusted as well, avoid converting `DATE`/`NUMBER` to text via NLS, restrict procedure privileges, and test dynamic SQL paths thoroughly. **Bind variables are the primary defense for values; DBMS_ASSERT and allowlists add control for identifiers; authorization restricts what callers are permitted to do.**
