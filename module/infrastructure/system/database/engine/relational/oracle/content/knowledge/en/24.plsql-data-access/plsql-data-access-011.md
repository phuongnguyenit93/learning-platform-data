# Positional vs. Named Binding and Differences Between Dynamic SQL and PL/SQL Blocks in Oracle

In Oracle, bind variables allow passing values into a SQL statement or PL/SQL block without concatenating those values directly into the command string. Binding separates syntax from data, reduces SQL injection risk, supports cursor reuse, and clarifies input data types.

When writing dynamic SQL in PL/SQL, you must understand a rule that often trips people up: **how Oracle matches bind arguments to placeholders depends on the type of content being executed**.

- For a **dynamic SQL statement** such as `SELECT`, `INSERT`, `UPDATE`, or `DELETE`, Oracle matches bind arguments by **the positional occurrence of each placeholder**. Two placeholders spelled with the same name are still two occurrences and require two corresponding bind arguments.
- For a **dynamic anonymous PL/SQL block** or **`CALL`** statement, Oracle matches by **unique placeholder name**. If the same placeholder name appears multiple times, only one bind argument is needed for that name.
- With **`DBMS_SQL`**, the program can bind explicitly by name using the `BIND_VARIABLE` procedure.
- At the application layer, standard JDBC `PreparedStatement` APIs use positional `?` indices; specific frameworks or driver extensions may provide their own named parameter mechanisms.

Confusing these rules commonly leads to mismatched bind counts, passing values into the wrong slots, or statements succeeding while processing the wrong data. This lesson explains the distinctions, concrete examples, and how to design safe dynamic SQL.

## 1. What is a bind variable?

A bind variable is a placeholder for a value supplied when a statement executes. In Oracle dynamic SQL, placeholders are usually written with a leading colon, for example:

~~~sql
SELECT employee_id, last_name
FROM employees
WHERE department_id = :p_department_id;
~~~

Here, `:p_department_id` is a placeholder. The actual value is passed separately in the `USING` clause or through a client binding API.

Comparing two ways of building a SQL statement:

~~~sql
-- Concatenating the value directly into the string:
l_sql := 'SELECT employee_id FROM employees WHERE department_id = '
         || TO_CHAR(p_department_id);

-- Using a bind variable:
l_sql := 'SELECT employee_id FROM employees WHERE department_id = :dept';
EXECUTE IMMEDIATE l_sql
    BULK COLLECT INTO l_employee_ids
    USING p_department_id;
~~~

The bind approach maintains a structurally stable statement and passes the value separately. String concatenation produces distinct SQL text per input value, increasing injection risk and reducing cursor reuse.

### 1.1. Binds are data, not SQL syntax fragments

Bind variables fit data values:

~~~sql
WHERE employee_id = :employee_id
WHERE hire_date >= :from_date
WHERE salary < :max_salary
~~~

Binds cannot replace table names, column names, keywords, operators, or sort directions:

~~~sql
-- Does NOT select the column whose name is passed in :column_name:
SELECT :column_name FROM employees;

-- Does NOT substitute the table name with the bound value:
SELECT * FROM :table_name;
~~~

In the examples above, the placeholder is an expression value; Oracle does not interpret that value as a table or column identifier.

### 1.2. Benefits of binding

- **Security:** input data is handled strictly as values, never becoming SQL syntax.
- **Cursor reuse:** the same statement structure can execute with many different values.
- **Explicit data types:** the driver or PL/SQL passes values with proper types, avoiding many string-conversion bugs.
- **Maintainability:** SQL statements are not tangled with input data.
- **Performance:** can reduce hard parses when repeated executions share the same SQL structure, though actual behavior still depends on cursor sharing, bind peeking, adaptive cursor sharing, and workload.

Binding does not guarantee that every execution uses the same execution plan. The optimizer can still pick different plans based on statistics, bind sensitivity, and Oracle version features.

## 2. How do dynamic SQL and dynamic PL/SQL blocks differ?

Dynamic SQL refers to SQL or PL/SQL statements built as strings and parsed/executed at runtime. In PL/SQL, Native Dynamic SQL normally uses `EXECUTE IMMEDIATE` or `OPEN FOR`.

There are two forms to distinguish.

### 2.1. Dynamic SQL statement

The string contains a SQL statement such as `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, or DDL:

~~~sql
l_sql := 'UPDATE employees
          SET salary = salary + :increase
          WHERE employee_id = :employee_id';

EXECUTE IMMEDIATE l_sql
    USING p_increase, p_employee_id;
~~~

Oracle parses the content as a SQL statement. Placeholders match bind arguments by each occurrence, from left to right.

### 2.2. Dynamic anonymous PL/SQL block

The string contains a PL/SQL block, for example:

~~~sql
l_block := 'BEGIN
                payroll_api.adjust_salary(
                    p_employee_id => :p_employee_id,
                    p_increase    => :p_increase
                );
            END;';

EXECUTE IMMEDIATE l_block
    USING p_employee_id, p_increase;
~~~

Oracle parses the content as a PL/SQL block. Placeholders match by unique placeholder name. If `:p_employee_id` appears again elsewhere in the block, it still refers to the same bind placeholder.

### 2.3. Quick comparison

| Feature | Dynamic SQL statement | Dynamic anonymous PL/SQL block |
|---|---|---|
| String content | `SELECT`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, DDL... | `DECLARE`/`BEGIN`/`EXCEPTION`/`END` |
| Execution mechanism | `EXECUTE IMMEDIATE` or `OPEN FOR` | `EXECUTE IMMEDIATE` |
| Bind matching in Native Dynamic SQL | By position of each occurrence | By unique placeholder name |
| Repeated placeholder with same name | Each occurrence needs its own bind argument | One bind argument for that name |
| Can use `OUT`/`IN OUT` variables via `USING` | Usually receives output via `INTO` or `RETURNING INTO` | Can use `USING OUT`/`IN OUT` |
| Can contain `IF`/`LOOP`/`EXCEPTION` | No, because it is a SQL statement | Yes |
| Purpose | SQL structure varies at runtime | Call PL/SQL logic or execute runtime-built blocks |

The core distinction does not lie in whether a placeholder is written `:x` or `:name`. It lies in the kind of statement Oracle is executing.

## 3. Positional binding in dynamic SQL statements

With Native Dynamic SQL, when the string is a SQL statement, bind arguments in `USING` match placeholders in order of appearance. Placeholder names do not trigger named matching.

Example:

~~~sql
DECLARE
    l_sql VARCHAR2(1000);
BEGIN
    l_sql := 'UPDATE employees
              SET salary = :new_salary
              WHERE employee_id = :employee_id';

    EXECUTE IMMEDIATE l_sql
        USING 9000, 101;
END;
/
~~~

Bind order:

| Position | Placeholder | Passed value |
|---:|---|---:|
| 1 | `:new_salary` | 9000 |
| 2 | `:employee_id` | 101 |

The placeholder names could be changed to `:x` and `:y` without changing positional matching.

### 3.1. Repeated placeholder names still require multiple binds

This is an important case:

~~~sql
DECLARE
    l_sql VARCHAR2(1000);
BEGIN
    l_sql := 'SELECT employee_id
              FROM employees
              WHERE department_id = :dept
                 OR manager_id = :dept';

    EXECUTE IMMEDIATE l_sql
        BULK COLLECT INTO l_employee_ids
        USING 10, 10;
END;
/
~~~

In a SQL statement, the two occurrences of `:dept` are treated as two positional placeholders. Therefore, `USING` requires two bind arguments. Passing only one value causes Oracle to raise a missing-bind error.

Mapping table:

| Position | Placeholder in SQL | Bind argument |
|---:|---|---|
| 1 | `:dept` in `department_id` predicate | First value |
| 2 | `:dept` in `manager_id` predicate | Second value |

Both values can be identical, as above, yet must still be passed twice.

### 3.2. Renaming placeholders does not change order

~~~sql
l_sql := 'SELECT employee_id
          FROM employees
          WHERE department_id = :first_value
             OR manager_id = :second_value';

EXECUTE IMMEDIATE l_sql
    BULK COLLECT INTO l_employee_ids
    USING p_department_id, p_manager_id;
~~~

The first bind corresponds to `:first_value`; the second corresponds to `:second_value`. Renaming them to `:x` and `:y` still maps in order of appearance.

### 3.3. Be careful when modifying SQL statements

Suppose initially:

~~~sql
l_sql := 'UPDATE employees
          SET salary = :salary
          WHERE employee_id = :employee_id';

EXECUTE IMMEDIATE l_sql
    USING p_salary, p_employee_id;
~~~

Later a maintainer adds a condition:

~~~sql
l_sql := 'UPDATE employees
          SET salary = :salary
          WHERE department_id = :department_id
            AND employee_id = :employee_id';

EXECUTE IMMEDIATE l_sql
    USING p_salary, p_employee_id, p_department_id;
~~~

The second snippet has the wrong order: the second bind should be the department ID and the third should be the employee ID. Use meaningful PL/SQL variable names and order bind arguments strictly by placeholder order in the string.

### 3.4. SELECT INTO and USING have different roles

For a single-row dynamic `SELECT`:

~~~sql
DECLARE
    l_sql        VARCHAR2(500);
    l_last_name  employees.last_name%TYPE;
    l_salary     employees.salary%TYPE;
BEGIN
    l_sql := 'SELECT last_name, salary
              FROM employees
              WHERE employee_id = :employee_id';

    EXECUTE IMMEDIATE l_sql
        INTO l_last_name, l_salary
        USING 101;
END;
/
~~~

- `INTO` receives data returned by `SELECT`.
- `USING` supplies input values for placeholders.

Do not put `SELECT` output target variables into `USING`. Variable count and order in `INTO` must match the columns in the select list.

If the `SELECT` returns no rows, Oracle raises `NO_DATA_FOUND`. If it returns more than one row in single-row `INTO` form, Oracle raises `TOO_MANY_ROWS`.

### 3.5. Multi-row queries with OPEN FOR

When the returned row count is not fixed, use a `REF CURSOR`:

~~~sql
DECLARE
    l_sql    VARCHAR2(500);
    l_cursor SYS_REFCURSOR;
    l_id     employees.employee_id%TYPE;
    l_name   employees.last_name%TYPE;
BEGIN
    l_sql := 'SELECT employee_id, last_name
              FROM employees
              WHERE department_id = :dept
              ORDER BY employee_id';

    OPEN l_cursor FOR l_sql USING 10;

    LOOP
        FETCH l_cursor INTO l_id, l_name;
        EXIT WHEN l_cursor%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(l_id || ' - ' || l_name);
    END LOOP;

    CLOSE l_cursor;
END;
/
~~~

With `OPEN FOR`, bind arguments for a dynamic SQL statement are also positional. Always close the cursor after use, including in error-handling paths in production code.

## 4. Named binding in dynamic anonymous PL/SQL blocks

For a dynamic anonymous PL/SQL block or `CALL` statement, Oracle matches binds by unique placeholder name. A placeholder repeated multiple times in the block still refers to the same bind.

Example:

~~~sql
DECLARE
    l_block VARCHAR2(1000);
BEGIN
    l_block := 'BEGIN
                    audit_api.record_values(
                        p_old_value => :value,
                        p_new_value => :value,
                        p_actor     => :actor
                    );
                END;';

    EXECUTE IMMEDIATE l_block
        USING 'ACTIVE', 'APP_USER';
END;
/
~~~

There are two unique placeholder names here:

1. `:value`
2. `:actor`

Even though `:value` appears twice, it is a single bind. `USING` provides one value for `:value` and one value for `:actor`, ordered by each name's first appearance in the block.

### 4.1. Repeated placeholders share one value

~~~sql
l_block := 'BEGIN
                report_api.compare_values(
                    :input_value,
                    :input_value,
                    :output_value
                );
            END;';

EXECUTE IMMEDIATE l_block
    USING p_value, p_result;
~~~

In the block:
- `:input_value` is one unique placeholder, used in two positions.
- `:output_value` is the second unique placeholder.

If two positions need two different values, use two distinct placeholder names, such as `:first_value` and `:second_value`.

### 4.2. Meaningful placeholder names prevent mistakes

~~~sql
l_block := 'BEGIN
                order_api.change_status(
                    p_order_id => :p_order_id,
                    p_status   => :p_status
                );
            END;';

EXECUTE IMMEDIATE l_block
    USING p_order_id, p_status;
~~~

Name placeholders to reflect the procedure's parameters. Clear names do not alter argument order in `USING`, yet help readers understand the contract between the dynamic PL/SQL string and the passed values.

### 4.3. Placeholder names are not named-argument syntax in USING

In Native Dynamic SQL, `USING` is a bind argument list following the executed statement's rules. Do not write PL/SQL named-argument assignment syntax like:

~~~sql
-- Not valid USING syntax for EXECUTE IMMEDIATE:
EXECUTE IMMEDIATE l_block
    USING p_order_id => p_order_id;
~~~

Named matching in dynamic PL/SQL blocks is Oracle's rule for placeholders inside the block string; it does not mean `USING` supports named-argument notation like regular procedure calls.

## 5. Side-by-side comparison using the same placeholder name in SQL and PL/SQL blocks

This is the most important comparison to remember.

### 5.1. Case A: SQL statement

~~~sql
DECLARE
    l_sql VARCHAR2(1000);
BEGIN
    l_sql := 'UPDATE employees
              SET salary = salary + :amount
              WHERE manager_id = :amount';

    EXECUTE IMMEDIATE l_sql
        USING 500, 500;
END;
/
~~~

There are two occurrences of `:amount` in the SQL statement, so two bind arguments must be passed.

### 5.2. Case B: PL/SQL block

~~~sql
DECLARE
    l_block VARCHAR2(1000);
BEGIN
    l_block := 'BEGIN
                    payroll_api.apply_adjustment(
                        :amount,
                        :amount
                    );
                END;';

    EXECUTE IMMEDIATE l_block
        USING 500;
END;
/
~~~

There is one unique placeholder name `:amount`, so only one bind argument is passed. Both positions in the block receive the same value.

### 5.3. Summary table

| String content | Placeholder occurrences | Unique placeholder names | Bind arguments in NDS |
|---|---:|---:|---:|
| SQL: `WHERE a = :x OR b = :x` | 2 | 1 | 2 |
| PL/SQL: `BEGIN p(:x, :x); END;` | 2 | 1 | 1 |
| SQL: `WHERE a = :x AND b = :y` | 2 | 2 | 2 |
| PL/SQL: `BEGIN p(:x, :y); END;` | 2 | 2 | 2 |
| SQL: `WHERE a = :x OR b = :y OR c = :x` | 3 | 2 | 3 |
| PL/SQL: `BEGIN p(:x, :y, :x); END;` | 3 | 2 | 2 |

For dynamic PL/SQL blocks, `USING` arguments correspond to unique placeholder names in order of first appearance. For SQL statements, each occurrence is bound individually by position.

## 6. IN, OUT, and IN OUT in dynamic PL/SQL blocks

A dynamic PL/SQL block can invoke procedures or functions with input, output, and bidirectional parameters. Native Dynamic SQL lets you specify parameter modes in the `USING` clause.

- `IN`: passes a value into the block.
- `OUT`: receives a value returned by the block.
- `IN OUT`: passes an initial value in and receives the updated value after the block runs.

### 6.1. OUT example

Suppose a package/schema has a procedure returning an order total:

~~~sql
CREATE OR REPLACE PROCEDURE get_order_total (
    p_order_id IN NUMBER,
    p_total    OUT NUMBER
) AS
BEGIN
    SELECT NVL(SUM(quantity * unit_price), 0)
    INTO p_total
    FROM order_items
    WHERE order_id = p_order_id;
END;
/
~~~

Calling it via a dynamic PL/SQL block:

~~~sql
DECLARE
    l_block VARCHAR2(500);
    l_total NUMBER;
BEGIN
    l_block := 'BEGIN
                    get_order_total(
                        p_order_id => :p_order_id,
                        p_total    => :p_total
                    );
                END;';

    EXECUTE IMMEDIATE l_block
        USING IN 1001, OUT l_total;

    DBMS_OUTPUT.PUT_LINE('Total = ' || l_total);
END;
/
~~~

Placeholder `:p_order_id` receives input; `:p_total` receives output. The order of bind arguments in `USING` matches the order of unique placeholder names as they first appear in the block.

### 6.2. IN OUT example

~~~sql
CREATE OR REPLACE PROCEDURE add_fee (
    p_amount IN OUT NUMBER,
    p_fee    IN NUMBER
) AS
BEGIN
    p_amount := p_amount + p_fee;
END;
/
~~~

Dynamic call:

~~~sql
DECLARE
    l_block  VARCHAR2(300);
    l_amount NUMBER := 1000;
BEGIN
    l_block := 'BEGIN
                    add_fee(:amount, :fee);
                END;';

    EXECUTE IMMEDIATE l_block
        USING IN OUT l_amount, IN 50;

    DBMS_OUTPUT.PUT_LINE(l_amount);
END;
/
~~~

After the block executes successfully, `l_amount` receives the updated value. `OUT`/`IN OUT` fits dynamic PL/SQL blocks or `CALL`. For SQL queries, results are normally received via `INTO` or `BULK COLLECT INTO`; for DML with `RETURNING`, use `EXECUTE IMMEDIATE`'s `RETURNING INTO` clause.

### 6.3. Do not pass an OUT variable as a default IN bind

Verify the called procedure's parameter modes carefully. If the block must return a result, the corresponding placeholder must be bound with `OUT` or `IN OUT` appropriately. Passing an output variable with the default `IN` mode does not create a return path.

## 7. Dynamic procedure calls vs. static procedure calls

When the procedure name and signature are known at compile time, a static call is usually clearer:

~~~sql
BEGIN
    order_api.approve_order(p_order_id => 1001);
END;
/
~~~

The compiler can check dependencies and data types according to PL/SQL compilation rules.

When the package/procedure name or block structure is known only at runtime, a dynamic block can be used:

~~~sql
DECLARE
    l_block VARCHAR2(500);
BEGIN
    l_block := 'BEGIN order_api.approve_order(:p_order_id); END;';

    EXECUTE IMMEDIATE l_block USING 1001;
END;
/
~~~

Use a dynamic block only when PL/SQL structure genuinely needs to be built at runtime. If only input values vary for a known procedure, a static call is simpler and easier to verify.

### 7.1. Static PL/SQL vs. dynamic PL/SQL blocks

| Criterion | Static PL/SQL | Dynamic PL/SQL block |
|---|---|---|
| Content | Written directly in source | Constructed as a string |
| Compile-time checks | Dependencies and types verified at compile time | String content parsed at runtime |
| Runtime object name changes | Inflexible | Can build dynamic object/block names, must validate safely |
| Value binding | Uses PL/SQL variables directly in static SQL or calls | Uses placeholders and `USING` |
| Debugging | Usually easier | Harder because actual source forms at runtime |
| Injection risk | Lower when not using dynamic SQL | Requires strict string, bind, and identifier control |

## 8. Native Dynamic SQL: EXECUTE IMMEDIATE and OPEN FOR

Native Dynamic SQL (NDS) is the way to write dynamic SQL directly in PL/SQL using native language syntax.

### 8.1. DML

~~~sql
DECLARE
    l_sql VARCHAR2(500);
BEGIN
    l_sql := 'UPDATE employees
              SET salary = salary * :factor
              WHERE department_id = :dept';

    EXECUTE IMMEDIATE l_sql
        USING 1.05, 10;

    DBMS_OUTPUT.PUT_LINE('Rows updated: ' || SQL%ROWCOUNT);
END;
/
~~~

After DML, `SQL%ROWCOUNT` reports how many rows the just-executed SQL statement affected. This is the implicit cursor attribute of the most recent statement.

### 8.2. Single-row SELECT

~~~sql
DECLARE
    l_sql    VARCHAR2(500);
    l_name   employees.last_name%TYPE;
BEGIN
    l_sql := 'SELECT last_name
              FROM employees
              WHERE employee_id = :id';

    EXECUTE IMMEDIATE l_sql
        INTO l_name
        USING 101;

    DBMS_OUTPUT.PUT_LINE(l_name);
END;
/
~~~

### 8.3. Multi-row SELECT

You can use `OPEN FOR` with a `REF CURSOR`, or `BULK COLLECT INTO` when data types and result sizes fit:

~~~sql
DECLARE
    TYPE t_names IS TABLE OF employees.last_name%TYPE;
    l_names t_names;
    l_sql   VARCHAR2(500);
BEGIN
    l_sql := 'SELECT last_name
              FROM employees
              WHERE department_id = :dept';

    EXECUTE IMMEDIATE l_sql
        BULK COLLECT INTO l_names
        USING 10;

    FOR i IN 1 .. l_names.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(l_names(i));
    END LOOP;
END;
/
~~~

If the dataset is very large, consider cursor batch fetching instead of loading the entire result into a collection.

### 8.4. Dynamic DDL

NDS can also execute DDL:

~~~sql
BEGIN
    EXECUTE IMMEDIATE 'CREATE TABLE lab_dynamic_demo (id NUMBER)';
END;
/
~~~

DDL normally does not accept bind variables for object names or syntax parts. Object names must come from validated sources. Remember Oracle DDL performs an implicit commit; running dynamic DDL can alter the session's transaction boundaries.

## 9. Terminator differences between dynamic SQL and dynamic PL/SQL blocks

Dynamic SQL statement strings normally do not end with a semicolon:

~~~sql
l_sql := 'DELETE FROM employees WHERE employee_id = :id';
EXECUTE IMMEDIATE l_sql USING 101;
~~~

Dynamic PL/SQL block strings must include semicolons to terminate statements inside the block and a semicolon after `END`:

~~~sql
l_block := 'BEGIN
                cleanup_api.remove_employee(:id);
            END;';

EXECUTE IMMEDIATE l_block USING 101;
~~~

Do not append the SQL*Plus/SQLcl slash (`/`) at the end of the block string. The slash is a client command, not syntax inside the block sent to `EXECUTE IMMEDIATE`.

A common mistake is writing:

~~~sql
l_sql := 'UPDATE employees SET salary = salary + 100 WHERE employee_id = :id;';
~~~

A trailing semicolon in a SQL statement can cause a syntax error in dynamic SQL. For PL/SQL blocks, semicolons inside the block are required.

## 10. DBMS_SQL and explicit named binding

NDS fits when bind counts and result types are known at compile time. When column counts or bind counts are known only at runtime, `DBMS_SQL` provides a more flexible API.

`DBMS_SQL` lets you:
- Open a dynamic cursor.
- Parse the SQL statement.
- Bind variables by placeholder name.
- Describe query columns when result structure is unknown.
- Define/fetch columns from runtime metadata.
- Execute and close the cursor.

### 10.1. Named binding example with DBMS_SQL

~~~sql
DECLARE
    l_cursor   INTEGER;
    l_rows     INTEGER;
    l_sql      VARCHAR2(500);
BEGIN
    l_sql := 'UPDATE employees
              SET salary = salary + :increase
              WHERE employee_id = :employee_id';

    l_cursor := DBMS_SQL.OPEN_CURSOR;

    DBMS_SQL.PARSE(
        l_cursor,
        l_sql,
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.BIND_VARIABLE(
        l_cursor,
        ':increase',
        500
    );

    DBMS_SQL.BIND_VARIABLE(
        l_cursor,
        ':employee_id',
        101
    );

    l_rows := DBMS_SQL.EXECUTE(l_cursor);

    DBMS_OUTPUT.PUT_LINE('Rows updated: ' || l_rows);

    DBMS_SQL.CLOSE_CURSOR(l_cursor);
EXCEPTION
    WHEN OTHERS THEN
        IF l_cursor IS NOT NULL AND DBMS_SQL.IS_OPEN(l_cursor) THEN
            DBMS_SQL.CLOSE_CURSOR(l_cursor);
        END IF;
        RAISE;
END;
/
~~~

Here, placeholder names are explicitly specified in `BIND_VARIABLE` calls. This differs from the NDS `USING` clause, which has no `p_name => value` argument naming syntax.

### 10.2. When should you choose DBMS_SQL?

| Scenario | Usually appropriate choice |
|---|---|
| SQL statement and bind count are known | `EXECUTE IMMEDIATE` |
| Single-row `SELECT` with known structure | `EXECUTE IMMEDIATE ... INTO` |
| Multi-row query with known structure | `OPEN FOR` or `BULK COLLECT` |
| Dynamic PL/SQL block with known parameters | `EXECUTE IMMEDIATE ... USING` |
| `SELECT` column count known only at runtime | `DBMS_SQL` |
| Need to describe metadata of dynamic result set | `DBMS_SQL` |
| Need explicit binding by name | `DBMS_SQL.BIND_VARIABLE` |

`DBMS_SQL` is more powerful yet more verbose and complex. Do not pick it merely to name placeholders in a simple SQL statement if positional NDS suffices.

## 11. JDBC and application-side parameter binding

When calling Oracle from Java, binding mechanics depend on the API.

### 11.1. PreparedStatement uses positional binding

Standard JDBC `PreparedStatement` uses question marks and 1-based indices:

~~~java
String sql = """
    UPDATE employees
       SET salary = salary + ?
     WHERE employee_id = ?
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setBigDecimal(1, increase);
    ps.setLong(2, employeeId);

    int updated = ps.executeUpdate();
}
~~~

Each question mark is a separate bind position. If the same value appears twice in SQL, you must bind it at both indices.

### 11.2. CallableStatement calling procedures

Example calling a procedure with `IN` and `OUT` parameters:

~~~java
String call = "{ call order_api.get_order_total(?, ?) }";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, orderId);
    cs.registerOutParameter(2, Types.NUMERIC);

    cs.execute();

    BigDecimal total = cs.getBigDecimal(2);
}
~~~

Standard JDBC uses positional parameters in this example. Some drivers or frameworks offer separate named-parameter APIs, but you should never assume a framework's naming syntax matches Native Dynamic SQL rules inside Oracle. Distinguish carefully:
- JDBC driver bind mapping.
- `EXECUTE IMMEDIATE` bind mapping.
- `DBMS_SQL` bind mapping.

### 11.3. Calling a dynamic PL/SQL block through JDBC

~~~java
String block = """
    BEGIN
        order_api.approve_order(:p_order_id);
    END;
    """;

try (CallableStatement cs = connection.prepareCall(block)) {
    cs.setLong(1, orderId);
    cs.execute();
}
~~~

From the JDBC side, parameters are normally assigned using the driver API and bind indices. Once Oracle receives and parses the block, placeholder rules inside PL/SQL's NDS are a separate topic. Do not assume that because JDBC uses indices, every internal NDS dynamic block shares SQL statement rules.

## 12. Binding NULL and data types

In PL/SQL Native Dynamic SQL, do not use the literal `NULL` directly inside the `USING` clause. Declare an uninitialized variable of the appropriate type and bind that variable.

~~~sql
DECLARE
    l_sql       VARCHAR2(500);
    l_status    VARCHAR2(20);
BEGIN
    -- l_status is unassigned, so its value is NULL.
    l_sql := 'UPDATE employees
              SET commission_pct = :commission
              WHERE employee_id = :id';

    EXECUTE IMMEDIATE l_sql
        USING l_status, 101;
END;
/
~~~

In JDBC applications, use the appropriate setter or `setNull` with the matching JDBC type:

~~~java
ps.setNull(1, Types.NUMERIC);
~~~

Do not convert all values to strings and bind strings when target columns are `DATE`, `NUMBER`, or `TIMESTAMP`. Pass native data types to avoid NLS-setting dependencies and implicit conversions.

### 12.1. DATE and TIMESTAMP

~~~sql
l_sql := 'SELECT COUNT(*)
          FROM orders
          WHERE order_date >= :from_date
            AND order_date < :to_date';

EXECUTE IMMEDIATE l_sql
    INTO l_count
    USING p_from_date, p_to_date;
~~~

Pass variables with matching `DATE`/`TIMESTAMP` types. Avoid concatenating date strings into SQL because parsing can depend on `NLS_DATE_FORMAT` or session formatting.

## 13. Bind variables do not replace IN lists or identifiers

### 13.1. One bind is one scalar value

The following does NOT mean `:ids` represents multiple values:

~~~sql
SELECT *
FROM employees
WHERE employee_id IN (:ids);
~~~

If `:ids` is bound to `'10,20,30'`, Oracle treats it as a single string value, not three separate elements.

If a dynamic list is needed, you can:
- Use an appropriate SQL/PLSQL collection and `TABLE()` if the collection type is designed for SQL querying.
- Generate the exact number of scalar placeholders for the element count, then bind each value.
- Load the list into a global temporary table or staging table and join against it.
- Use an API accepting a collection type supported by Oracle.

Never concatenate raw ID strings from requests into an `IN` clause.

### 13.2. Identifiers require whitelisting

If choosing a table by report type, map input against an allowed identifier list:

~~~sql
DECLARE
    l_table_name VARCHAR2(30);
    l_sql        VARCHAR2(500);
    l_count      NUMBER;
BEGIN
    CASE UPPER(:requested_source)
        WHEN 'ORDERS' THEN
            l_table_name := 'ORDERS';
        WHEN 'CUSTOMERS' THEN
            l_table_name := 'CUSTOMERS';
        ELSE
            RAISE_APPLICATION_ERROR(-20060, 'Unsupported source');
    END CASE;

    l_sql := 'SELECT COUNT(*) FROM ' || l_table_name;

    EXECUTE IMMEDIATE l_sql INTO l_count;
END;
/
~~~

The example illustrates a whitelist; in real PL/SQL, input variables should be declared and populated from procedure parameters or an appropriate context. If identifiers have special schemas or quoting, apply proper normalization and validation rules.

### 13.3. DBMS_ASSERT assists identifier validation

`DBMS_ASSERT` provides functions to validate or quote identifiers such as `SIMPLE_SQL_NAME`, `SQL_OBJECT_NAME`, and `ENQUOTE_NAME`. They help when building dynamic SQL, yet do not replace business authorization checks. A syntactically valid identifier can still refer to an object the caller is not permitted to access.

## 14. SQL injection and writing safe dynamic SQL

SQL injection happens when untrusted data is concatenated into a SQL string and interpreted as syntax.

### 14.1. Unsafe example

~~~sql
l_sql := 'SELECT employee_id
          FROM employees
          WHERE last_name = '''
          || p_last_name || '''';

EXECUTE IMMEDIATE l_sql INTO l_employee_id;
~~~

If `p_last_name` contains a quote character and a SQL fragment, the statement's structure can be altered.

### 14.2. Use bind variables

~~~sql
l_sql := 'SELECT employee_id
          FROM employees
          WHERE last_name = :last_name';

EXECUTE IMMEDIATE l_sql
    INTO l_employee_id
    USING p_last_name;
~~~

The value of `p_last_name` is passed separately. Its contents are never parsed as SQL syntax.

### 14.3. When dynamic identifiers are required

Table or column names cannot be bound as values. The safe solution is:
1. Allow only identifiers present in a whitelist.
2. Validate identifiers and schemas/objects in context.
3. Use `DBMS_ASSERT` where appropriate.
4. Bind all remaining data values.
5. Grant least database privilege to the executing program.

Do not rely on manual quote-doubling tricks to sanitize arbitrary input into safe SQL. Manual escaping easily misses edge cases and does not replace binding.

## 15. Common binding errors

| Error/Symptom | Possible cause | Resolution |
|---|---|---|
| `ORA-01008: not all variables bound` | Missing bind argument or occurrence count mismatch in SQL statement | Count every placeholder occurrence and match against `USING` |
| `ORA-01006: bind variable does not exist` | Binding a name absent from the statement or block | Inspect the constructed SQL/block string |
| `ORA-01036: illegal variable name/number` | Invalid bind name or number, API mismatch | Verify placeholders and the bind API being used |
| Right number of values passed but wrong rows updated | `USING` order shifted relative to SQL statement | Map placeholder positions before binding |
| Dynamic block needs one bind yet multiple were passed | Confusing SQL occurrence rules with block unique-name rules | Count unique placeholder names in the block |
| Cannot bind table/column name | Identifiers are not bind values | Whitelist and validate identifiers |
| `IN` returns only one value | A scalar bind was mistaken for a list | Use a collection, placeholder list, or staging table |
| Syntax error near end of string | Trailing semicolon in dynamic SQL or missing semicolon in block | Distinguish SQL statement vs. PL/SQL block syntax |
| Wrong `DATE`/`NUMBER` values | String conversion depending on NLS | Bind native data types |
| Query suffers excessive hard parses | Concatenating literals creates distinct SQL texts | Bind varying values |
| Binding `NULL` fails | Direct literal `NULL` in `USING` | Use an uninitialized typed variable |
| Function/procedure does not return `OUT` | Using default `IN` mode for output | Declare `OUT` or `IN OUT` in `USING` |

## 16. Controlled workflow for building dynamic SQL

When building statements at runtime, follow this sequence:

1. Determine whether the content is a SQL statement or a PL/SQL block.
2. Identify what varies: data values, identifiers, or statement structure.
3. Keep structure fixed if only data values change; use bind variables.
4. If identifiers must vary, map through a whitelist and validate.
5. Count placeholder occurrences if it is a SQL statement.
6. Count unique placeholder names if it is a PL/SQL block or `CALL`.
7. Order bind arguments according to the exact rules of the API in use.
8. Pick `INTO`, `BULK COLLECT`, `OPEN FOR`, or `OUT`/`IN OUT` appropriately.
9. Manage cursors and exceptions, guaranteeing resource cleanup.
10. Verify transaction boundaries, especially when the dynamic statement is DDL.
11. Test `NULL` inputs, quote characters, boundary data types, bind counts, and invalid identifiers.
12. Log `SQL_ID` or diagnostic context without exposing sensitive data.

## 17. Comprehensive example: SQL statement and PL/SQL block using the same placeholder name

Suppose you need to increase salary and reference two occurrences of a value in the logic.

### 17.1. Dynamic SQL statement

~~~sql
DECLARE
    l_sql VARCHAR2(1000);
BEGIN
    l_sql := 'UPDATE employees
              SET salary = salary + :delta
              WHERE employee_id = :employee_id
                 OR manager_id = :employee_id';

    EXECUTE IMMEDIATE l_sql
        USING 250, 101, 101;

    DBMS_OUTPUT.PUT_LINE('Rows affected: ' || SQL%ROWCOUNT);
END;
/
~~~

There are three occurrences:
1. `:delta`
2. `:employee_id` in the first condition
3. `:employee_id` in the second condition

Because this is a SQL statement, three bind arguments are required.

### 17.2. Dynamic PL/SQL block

~~~sql
DECLARE
    l_block VARCHAR2(1000);
BEGIN
    l_block := 'BEGIN
                    payroll_api.audit_adjustment(
                        p_employee_id => :employee_id,
                        p_requested_by => :actor,
                        p_confirmed_for => :employee_id
                    );
                END;';

    EXECUTE IMMEDIATE l_block
        USING 101, 'APP_USER';
END;
/
~~~

There are two unique placeholder names:
1. `:employee_id`
2. `:actor`

Even though `:employee_id` appears twice, the block needs only one bind argument for that name.

### 17.3. Memory aid

~~~text
NATIVE DYNAMIC SQL

SQL statement:
    :x, :x, :y, :x
    -> 4 occurrences
    -> 4 bind arguments by position

Anonymous PL/SQL block / CALL:
    :x, :x, :y, :x
    -> 2 unique names
    -> 2 bind arguments by name
       (in order of each name's first appearance)

DBMS_SQL:
    BIND_VARIABLE(cursor, ':x', value)
    -> explicitly specifies bind name
~~~

## 18. Controlled hands-on lab

The exercises use the sample schema `EMPLOYEES` table if available. If you lack privileges or the sample schema is not installed, create your own lab table in a `DEV`/`TEST` schema. Never run sample DML or DDL on production business data.

### Exercise 1 — Positional binding in dynamic SQL

Create an `UPDATE` statement with two differently named placeholders. Pass two values in order and verify the right row updates. Swap the two values and observe the result or error.

### Exercise 2 — Repeated placeholder in a SQL statement

Write:

~~~sql
SELECT employee_id
FROM employees
WHERE department_id = :x
   OR manager_id = :x
~~~

Run it with two bind arguments. Then try passing only one bind and record the error. Explain why the same name still creates two occurrences.

### Exercise 3 — Repeated placeholder in a PL/SQL block

Write the block:

~~~sql
BEGIN
    demo_api.compare_values(:x, :x, :y);
END;
~~~

Invoke it via `EXECUTE IMMEDIATE` with two bind arguments. Try renaming the second placeholder from `:x` to `:z` and observe how many binds are required.

### Exercise 4 — IN and OUT

Create a procedure with one `IN` parameter and one `OUT` parameter. Call it through a dynamic PL/SQL block, declaring modes in `USING`. Verify the returned `OUT` value.

### Exercise 5 — SELECT INTO and OPEN FOR

Write a dynamic `SELECT` returning one row using `INTO`. Then write a query returning multiple rows using a `REF CURSOR` with `OPEN FOR`. Compare how rows are fetched and cursors closed.

### Exercise 6 — DBMS_SQL named binding

Use `DBMS_SQL` to parse an `UPDATE` with two placeholders. Call `BIND_VARIABLE` by name for each placeholder and execute. Compare with positional `EXECUTE IMMEDIATE`.

### Exercise 7 — SQL injection

Create an example using string concatenation with an input containing quotes. Then fix it with a bind variable. Explain why binds do not work for table names and how to whitelist identifiers.

### Exercise 8 — Binding NULL and data types

Bind an uninitialized `NUMBER` variable into a SQL condition. Then test `DATE`/`TIMESTAMP`. Verify values are passed with the right type without relying on NLS string formats.

### Lab data cleanup

Delete only the exact objects created for the practice exercises in your `DEV`/`TEST` schema after confirming no one else uses them. DDL in Oracle performs an implicit commit; never run cleanup commands on objects outside the lab scope.

## 19. Review questions

**Question 1.** What is a bind variable?

**Answer:** A placeholder that receives a value at execution time, separating data from SQL/PLSQL syntax strings.

**Question 2.** In Native Dynamic SQL, what rule does a SQL statement use to match binds?

**Answer:** By the position of each occurrence in the SQL statement, not by placeholder name.

**Question 3.** If `:x` appears twice in a dynamic `UPDATE`, how many bind arguments are needed?

**Answer:** Two bind arguments, one for each occurrence.

**Question 4.** In a dynamic anonymous PL/SQL block, if `:x` appears twice, how many bind arguments are needed?

**Answer:** One bind argument for the unique placeholder name `:x`.

**Question 5.** If two positions in a dynamic PL/SQL block need two different values, what should you do?

**Answer:** Use two different placeholder names and pass two corresponding bind arguments.

**Question 6.** Does `USING` in `EXECUTE IMMEDIATE` support named-argument syntax like a procedure call?

**Answer:** No. `USING` is a bind argument list; matching rules depend on whether the string is a SQL statement or a PL/SQL block.

**Question 7.** How does `INTO` differ from `USING` when running a dynamic `SELECT`?

**Answer:** `INTO` receives result columns; `USING` supplies input values for placeholders.

**Question 8.** When is `OPEN FOR` used?

**Answer:** When a dynamic query returns multiple rows and needs to be fetched through a `REF CURSOR`.

**Question 9.** When should `DBMS_SQL` be used instead of NDS?

**Answer:** When column or bind counts/types are known only at runtime, result metadata must be described, or explicit named binding is needed.

**Question 10.** Can a table name be bound?

**Answer:** No. Bind variables represent values; identifiers require whitelisting and separate validation.

**Question 11.** Why should user data not be concatenated into dynamic SQL?

**Answer:** It introduces SQL injection risks, creates multiple SQL texts, and makes data types and cursor reuse harder to control. Bind values instead.

**Question 12.** How does a standard JDBC `PreparedStatement` bind parameters?

**Answer:** Positionally by question mark index, starting at 1. Named binding APIs in specific frameworks/drivers are separate mechanisms and require checking their respective docs.

**Question 13.** Does a dynamic PL/SQL block auto-commit?

**Answer:** Not simply because it is dynamic. Transaction outcome depends on statements inside it; DML stays in the session transaction, while internal `COMMIT`, `ROLLBACK`, or DDL can alter transaction boundaries.

**Question 14.** Why must semicolons be distinguished between dynamic SQL and dynamic PL/SQL blocks?

**Answer:** Dynamic SQL statements normally omit a trailing semicolon; PL/SQL blocks require semicolons for internal statements and after `END`. The SQL*Plus slash is not part of the block string.

## Conclusion

In Oracle Native Dynamic SQL, bind matching depends on the type of content executed. For **SQL statements**, Oracle matches positionally per placeholder occurrence; repeated placeholder names still require separate bind arguments. For **anonymous PL/SQL blocks or `CALL`**, Oracle matches by unique placeholder name; a repeated name requires only one bind argument. `USING` arguments for a block follow the order of first appearance of each unique placeholder name. `DBMS_SQL` provides explicit named binding via `BIND_VARIABLE`.

Bind variables represent only data values, never identifiers or syntax fragments. When dynamic table/column names are needed, use whitelists and validate identifiers; always bind remaining values. Clearly distinguish `INTO`/`OPEN FOR` from `USING`, `IN`/`OUT`/`IN OUT` modes, SQL vs. PL/SQL block terminators, and DDL transaction boundaries. When binds and result shapes are known, Native Dynamic SQL is concise; when metadata is known only at runtime, consider `DBMS_SQL`. At the Java layer, standard `PreparedStatement` binds positionally, so honor each API's contract rather than mixing rules.

## Oracle Reference Documentation

- [Oracle Database 19c PL/SQL Language Reference — Native Dynamic SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/native-dynamic-sql.html): `EXECUTE IMMEDIATE`, `OPEN FOR`, `USING`, and placeholder bind rules.
- [Oracle Database 19c PL/SQL Language Reference — Dynamic SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/dynamic-sql.html): choosing between Native Dynamic SQL and `DBMS_SQL`.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_SQL](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SQL.html): `PARSE`, `BIND_VARIABLE`, `DESCRIBE_COLUMNS`, and `EXECUTE`.
- [Oracle Database 19c PL/SQL Packages and Types Reference — DBMS_ASSERT](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_ASSERT.html): validating object names and identifiers when building dynamic SQL.
- [Oracle Database 19c SQL Language Reference](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/index.html): SQL syntax, bind variables, and DDL.
