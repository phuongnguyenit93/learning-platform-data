# Static SQL, Dynamic SQL, and Selection Criteria in PL/SQL

PL/SQL can execute SQL in two main ways: **static SQL** and **dynamic SQL**. With static SQL, the SQL statement is written directly inside the PL/SQL block. With dynamic SQL, the program builds the statement as a string and instructs Oracle to parse and execute it at runtime.

Static SQL is usually the first choice because its syntax is readable, checked when PL/SQL compiles, supports dependency tracking, and carries lower risk when handling input. Dynamic SQL is useful when the statement structure itself is known only at runtime—such as table names, column names, variable filter conditions, or DDL statements chosen by configuration.

Choosing the wrong approach can make programs harder to maintain, trigger runtime-only errors, increase parse overhead, or introduce SQL injection vulnerabilities. This lesson explains both execution methods, Native Dynamic SQL, `DBMS_SQL`, bind variables, security, execution privileges, performance, and selection criteria.

## 1. What is static SQL?

Static SQL is a SQL statement written directly inside PL/SQL code. The statement and its structure are already determined in the source code:

~~~sql
DECLARE
    v_salary employees.salary%TYPE;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE('Salary = ' || v_salary);
END;
/
~~~

In this example, the `EMPLOYEES` table, `SALARY` column, `EMPLOYEE_ID` column, and `SELECT` structure are written explicitly in the program. The value `100` is a literal; it can be replaced with a PL/SQL variable without converting the SQL statement into dynamic SQL.

### 1.1. Using PL/SQL variables in static SQL

~~~sql
DECLARE
    v_employee_id employees.employee_id%TYPE := 100;
    v_salary      employees.salary%TYPE;
BEGIN
    SELECT salary
    INTO v_salary
    FROM employees
    WHERE employee_id = v_employee_id;

    DBMS_OUTPUT.PUT_LINE(v_salary);
END;
/
~~~

PL/SQL automatically passes the `V_EMPLOYEE_ID` variable into the SQL statement as a bind value. There is no need to concatenate SQL strings to insert values into conditions.

### 1.2. Validation and dependencies

Because static SQL is embedded directly in PL/SQL:

- The compiler can validate the SQL syntax and semantics in the compilation context.
- Oracle tracks dependencies between the stored program and referenced schema objects.
- Structural changes to dependent objects can invalidate the program so it requires recompilation.
- Readers of the source code can easily see which tables, columns, and data types the program uses.

Successful compilation does not guarantee every runtime execution will succeed. For example, `SELECT INTO` can still hit `NO_DATA_FOUND` or `TOO_MANY_ROWS` depending on runtime data; constraints, privileges, and system state can also cause runtime errors.

## 2. Static SQL examples in PL/SQL

### 2.1. SELECT INTO

`SELECT INTO` fetches a single row into variables or a record:

~~~sql
DECLARE
    v_name employees.last_name%TYPE;
BEGIN
    SELECT last_name
    INTO v_name
    FROM employees
    WHERE employee_id = 100;

    DBMS_OUTPUT.PUT_LINE(v_name);
END;
/
~~~

`SELECT INTO` has key outcomes:

| Query result | Behavior |
|---|---|
| Exactly one row | Assigns values to variables |
| Zero rows | Raises `NO_DATA_FOUND` |
| More than one row | Raises `TOO_MANY_ROWS` |

If a query can return multiple rows, use a cursor, cursor `FOR LOOP`, or `BULK COLLECT` instead of single-row `SELECT INTO`.

### 2.2. Static DML

~~~sql
DECLARE
    v_department_id employees.department_id%TYPE := 50;
    v_raise_rate    NUMBER := 0.05;
BEGIN
    UPDATE employees
    SET salary = salary * (1 + v_raise_rate)
    WHERE department_id = v_department_id;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows = ' || SQL%ROWCOUNT
    );
END;
/
~~~

`SQL%ROWCOUNT` returns the number of rows affected by the most recent SQL statement in the session. With static DML, you can use implicit cursor attributes like `SQL%ROWCOUNT`, `SQL%FOUND`, and `SQL%NOTFOUND` to inspect the outcome.

The block above does not auto-`COMMIT`. Changes remain in the current transaction; the caller or session decides `COMMIT`/`ROLLBACK` per application flow.

### 2.3. Static cursor

~~~sql
DECLARE
    CURSOR c_employee IS
        SELECT employee_id, last_name, salary
        FROM employees
        WHERE department_id = 50
        ORDER BY employee_id;
BEGIN
    FOR rec IN c_employee LOOP
        DBMS_OUTPUT.PUT_LINE(
            rec.employee_id || ' - ' ||
            rec.last_name || ' - ' ||
            rec.salary
        );
    END LOOP;
END;
/
~~~

The cursor `FOR LOOP` automatically opens, fetches, and closes the cursor. The `SELECT` structure is known at compile time, so this is static SQL.

## 3. What is dynamic SQL?

Dynamic SQL is a SQL statement constructed as a string and executed at runtime. The program can build the statement text based on parameters, metadata, or user selections.

Example:

~~~sql
DECLARE
    v_sql   VARCHAR2(1000);
    v_count NUMBER;
BEGIN
    v_sql := 'SELECT COUNT(*) FROM employees WHERE department_id = :dept';

    EXECUTE IMMEDIATE v_sql
        INTO v_count
        USING 50;

    DBMS_OUTPUT.PUT_LINE('Employee count = ' || v_count);
END;
/
~~~

Here, the SQL statement is held in the string variable `V_SQL`. Oracle parses the statement when the program executes `EXECUTE IMMEDIATE`. `:DEPT` is a bind placeholder; the value `50` is passed separately in `USING`.

### 3.1. When is SQL structure only known at runtime?

Typical scenarios:

- The table name is chosen from configuration, such as yearly data tables.
- The sort column is chosen by the user from an allowed list.
- Optional filters change the number of predicates.
- Objects need to be created or altered via DDL.
- An administrative utility must query multiple tables with varying names.
- A reporting tool allows choosing columns and groupings at runtime.

Dynamic SQL is not needed just because condition values change. If the tables, columns, and SQL structure are fixed, use static SQL with bind variables.

## 4. Native Dynamic SQL (NDS)

Oracle provides Native Dynamic SQL to execute dynamic statements directly in PL/SQL. Common constructs:

- `EXECUTE IMMEDIATE`: executes DML, DDL, single-row `SELECT`, anonymous PL/SQL blocks, or appropriate calls.
- `OPEN ... FOR`: opens a cursor variable for a dynamic query returning multiple rows.
- `FETCH` and `CLOSE`: reads and closes a dynamic cursor.

NDS is usually simpler than `DBMS_SQL` when the count, data types, and structure of parameters are known when writing the program.

## 5. EXECUTE IMMEDIATE with DML

### 5.1. Dynamic UPDATE with bind variables

Suppose the table name is chosen in code, while the raise rate and department ID are values:

~~~sql
DECLARE
    v_table_name VARCHAR2(30) := 'EMPLOYEES';
    v_sql        VARCHAR2(1000);
    v_rate       NUMBER := 0.05;
    v_dept_id    NUMBER := 50;
BEGIN
    v_sql :=
        'UPDATE ' || v_table_name ||
        ' SET salary = salary * (1 + :rate)' ||
        ' WHERE department_id = :dept';

    EXECUTE IMMEDIATE v_sql
        USING v_rate, v_dept_id;

    DBMS_OUTPUT.PUT_LINE(
        'Updated rows = ' || SQL%ROWCOUNT
    );
END;
/
~~~

The table name is concatenated into the string because identifiers cannot be passed as bind values. The values `0.05` and `50` are passed via `USING` so Oracle treats them strictly as data.

The example above assumes the table name is controlled. If a table name comes from external input, validate it via an allowlist and/or `DBMS_ASSERT` before concatenating into SQL.

### 5.2. Dynamic DELETE

~~~sql
DECLARE
    v_sql VARCHAR2(1000);
    v_id  NUMBER := 100;
BEGIN
    v_sql := 'DELETE FROM employees WHERE employee_id = :id';

    EXECUTE IMMEDIATE v_sql USING v_id;

    DBMS_OUTPUT.PUT_LINE(
        'Deleted rows = ' || SQL%ROWCOUNT
    );
END;
/
~~~

Dynamic `DELETE` participates in the current transaction just like static `DELETE`. `EXECUTE IMMEDIATE` does not auto-`COMMIT` DML.

### 5.3. Dynamic INSERT

~~~sql
DECLARE
    v_sql VARCHAR2(1000);
BEGIN
    v_sql :=
        'INSERT INTO employees ' ||
        '(employee_id, last_name, email, hire_date, job_id, salary)' ||
        ' VALUES (:id, :name, :email, SYSDATE, :job, :salary)';

    EXECUTE IMMEDIATE v_sql
        USING 9001, 'Nguyen', 'NGUYEN9001', 'IT_PROG', 8000;
END;
/
~~~

Bind values are passed in the order placeholders appear in the SQL statement. When using dynamic SQL statements, manage bind positions consistently; do not rely on identical placeholder names to reorder arguments.

## 6. EXECUTE IMMEDIATE with SELECT

### 6.1. SELECT returning exactly one row

~~~sql
DECLARE
    v_sql    VARCHAR2(1000);
    v_salary NUMBER;
    v_id     NUMBER := 100;
BEGIN
    v_sql :=
        'SELECT salary FROM employees WHERE employee_id = :id';

    EXECUTE IMMEDIATE v_sql
        INTO v_salary
        USING v_id;

    DBMS_OUTPUT.PUT_LINE('Salary = ' || v_salary);
END;
/
~~~

For a single-row `SELECT`, `INTO` receives result columns in order. Variable count and data types must match the select list.

If zero rows match, `NO_DATA_FOUND` is raised. If multiple rows match, `TOO_MANY_ROWS` is raised.

### 6.2. Multi-row SELECT with BULK COLLECT

If column count and data types are known, you can load multiple rows into a collection:

~~~sql
DECLARE
    TYPE t_employee_ids IS TABLE OF employees.employee_id%TYPE;
    v_ids t_employee_ids;
    v_dept_id NUMBER := 50;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT employee_id
           FROM employees
          WHERE department_id = :dept
          ORDER BY employee_id'
        BULK COLLECT INTO v_ids
        USING v_dept_id;

    FOR i IN 1 .. v_ids.COUNT LOOP
        DBMS_OUTPUT.PUT_LINE(v_ids(i));
    END LOOP;
END;
/
~~~

`BULK COLLECT` loads all results into the collection. If the query can return a very large dataset, consider PGA memory limits; use a dynamic cursor and fetch in batches when chunked processing is needed.

## 7. OPEN FOR with dynamic cursors

When a query returns multiple rows and needs row-by-row fetching, use a `REF CURSOR`:

~~~sql
DECLARE
    v_sql         VARCHAR2(1000);
    v_dept_id     NUMBER := 50;
    v_employee_id employees.employee_id%TYPE;
    v_last_name   employees.last_name%TYPE;
    v_salary      employees.salary%TYPE;
    v_rc          SYS_REFCURSOR;
BEGIN
    v_sql :=
        'SELECT employee_id, last_name, salary ' ||
        'FROM employees ' ||
        'WHERE department_id = :dept ' ||
        'ORDER BY employee_id';

    OPEN v_rc FOR v_sql USING v_dept_id;

    LOOP
        FETCH v_rc
        INTO v_employee_id, v_last_name, v_salary;

        EXIT WHEN v_rc%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            v_employee_id || ' - ' ||
            v_last_name || ' - ' ||
            v_salary
        );
    END LOOP;

    CLOSE v_rc;
EXCEPTION
    WHEN OTHERS THEN
        IF v_rc%ISOPEN THEN
            CLOSE v_rc;
        END IF;
        RAISE;
END;
/
~~~

`SYS_REFCURSOR` is a weak ref cursor that can be opened for queries with different select lists. However, when fetching into PL/SQL variables, column count and data types must still match the actual result. A weak cursor is flexible at open time, but it does not turn an unknown structure into matching typed variables automatically.

### 7.1. When to use OPEN FOR instead of BULK COLLECT?

| Requirement | Approach to consider |
|---|---|
| Small result, known column structure | `EXECUTE IMMEDIATE ... BULK COLLECT INTO` |
| Large result, need batch/iterative fetch | `OPEN FOR` with `SYS_REFCURSOR` |
| Need to return result set to caller | Return `REF CURSOR` via `OUT` parameter |
| Column count/types unknown at compile time | `DBMS_SQL` |

## 8. Dynamic SQL for anonymous PL/SQL blocks

`EXECUTE IMMEDIATE` can also execute a PL/SQL block built at runtime:

~~~sql
DECLARE
    v_block VARCHAR2(1000);
    v_dept  NUMBER := 50;
    v_rate  NUMBER := 0.05;
BEGIN
    v_block :=
        'BEGIN ' ||
        '  UPDATE employees ' ||
        '  SET salary = salary * (1 + :rate) ' ||
        '  WHERE department_id = :dept; ' ||
        'END;';

    EXECUTE IMMEDIATE v_block
        USING v_rate, v_dept;
END;
/
~~~

Dynamic blocks are helpful when calling procedures or executing PL/SQL with varying structure. If there is only a single `UPDATE`, executing the DML statement directly is usually simpler.

### 8.1. IN, OUT, and IN OUT parameters

When calling a dynamic PL/SQL block or procedure via dynamic SQL, `USING` can specify parameter modes:

~~~sql
DECLARE
    v_block  VARCHAR2(500);
    v_input  NUMBER := 10;
    v_output NUMBER;
BEGIN
    v_block := 'BEGIN :out_value := :in_value * 2; END;';

    EXECUTE IMMEDIATE v_block
        USING OUT v_output, IN v_input;

    DBMS_OUTPUT.PUT_LINE(v_output);
END;
/
~~~

This example illustrates `OUT` and `IN` parameters in a dynamic anonymous block. With PL/SQL blocks, bind placeholders can serve as input and output parameters; declare modes in the exact order matching the placeholders.

## 9. Dynamic DDL

DDL such as `CREATE`, `ALTER`, and `DROP` often requires dynamic SQL when object names or structures are decided at runtime:

~~~sql
BEGIN
    EXECUTE IMMEDIATE
        'CREATE TABLE lab_dynamic_log (
            log_id NUMBER,
            message VARCHAR2(200)
        )';
END;
/
~~~

No `INTO` clause is used for DDL. The dynamic DDL statement is parsed and executed at runtime.

### 9.1. Bind variables cannot replace table or column names

You cannot write:

~~~sql
EXECUTE IMMEDIATE
    'CREATE TABLE :table_name (id NUMBER)'
USING 'LAB_DYNAMIC_LOG';
~~~

Bind variables represent **data values**, not identifiers, keywords, or SQL syntax fragments. Table names, column names, schema names, and `ORDER BY` directions must be validated and concatenated into the string.

### 9.2. DDL and transactions

Standard DDL commands trigger an implicit commit under Oracle rules. Therefore, dynamic DDL can also end an open DML transaction. Never place `CREATE`/`ALTER`/`DROP` in the middle of a DML workflow that the application expects to roll back completely on error.

Example:

~~~sql
UPDATE employees
SET salary = salary + 100
WHERE employee_id = 100;

EXECUTE IMMEDIATE 'CREATE TABLE lab_ddl_test (id NUMBER)';

ROLLBACK;
~~~

You cannot rely on the final `ROLLBACK` to undo the `UPDATE` before the DDL because the DDL triggered an implicit commit. Separate schema-change workflows from business transactions.

## 10. Bind variables: separating data from SQL structure

A bind variable is a placeholder in a SQL statement bound to a value at execution time. This is the single most important principle when writing safe and efficient dynamic SQL.

Correct example:

~~~sql
DECLARE
    v_sql VARCHAR2(500);
    v_id  NUMBER := 100;
BEGIN
    v_sql := 'DELETE FROM employees WHERE employee_id = :id';
    EXECUTE IMMEDIATE v_sql USING v_id;
END;
/
~~~

The value `100` is passed separately, not concatenated directly into the SQL string.

### 10.1. Avoid concatenating user values into SQL

Error-prone approach:

~~~sql
v_sql :=
    'SELECT COUNT(*) FROM users WHERE username = '''
    || p_username || '''';

EXECUTE IMMEDIATE v_sql INTO v_count;
~~~

If the input contains quotes or syntactically meaningful SQL strings, the statement can fail or change meaning. If input is exploited to inject conditions, this is SQL injection.

Safer approach:

~~~sql
v_sql :=
    'SELECT COUNT(*) FROM users WHERE username = :name';

EXECUTE IMMEDIATE v_sql
    INTO v_count
    USING p_username;
~~~

Bind variables help Oracle handle data with the right type, avoid manual literal escaping, and generally support cursor reuse.

### 10.2. Binding does not apply to identifiers

The following does not mean "sort by the column named in the parameter":

~~~sql
EXECUTE IMMEDIATE
    'SELECT employee_id, last_name FROM employees ORDER BY :column_name'
USING p_column_name;
~~~

`:COLUMN_NAME` is a bind value. Oracle will sort by that constant bind value rather than interpreting it as a column name. To choose a sort column, select the identifier from an allowlist and concatenate the validated column name into the SQL.

## 11. Building safe dynamic SQL with an allowlist

Suppose a report allows sorting by `EMPLOYEE_ID`, `LAST_NAME`, or `SALARY`. Never concatenate a user-supplied string straight into `ORDER BY`. Map the selection to a fixed list of identifiers:

~~~sql
DECLARE
    v_sort_column VARCHAR2(30);
    v_direction   VARCHAR2(4);
    v_sql         VARCHAR2(1000);
    v_min_salary  NUMBER := 5000;
    v_rc          SYS_REFCURSOR;
    v_id          NUMBER;
    v_name        VARCHAR2(100);
    v_salary      NUMBER;
BEGIN
    -- Assumed value received from the UI.
    CASE UPPER('SALARY')
        WHEN 'EMPLOYEE_ID' THEN
            v_sort_column := 'EMPLOYEE_ID';
        WHEN 'LAST_NAME' THEN
            v_sort_column := 'LAST_NAME';
        WHEN 'SALARY' THEN
            v_sort_column := 'SALARY';
        ELSE
            RAISE_APPLICATION_ERROR(-20001, 'Invalid sort column');
    END CASE;

    v_direction := 'DESC';
    IF v_direction NOT IN ('ASC', 'DESC') THEN
        RAISE_APPLICATION_ERROR(-20002, 'Invalid sort direction');
    END IF;

    v_sql :=
        'SELECT employee_id, last_name, salary ' ||
        'FROM employees ' ||
        'WHERE salary >= :min_salary ' ||
        'ORDER BY ' || v_sort_column || ' ' || v_direction;

    OPEN v_rc FOR v_sql USING v_min_salary;

    LOOP
        FETCH v_rc INTO v_id, v_name, v_salary;
        EXIT WHEN v_rc%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(
            v_id || ' ' || v_name || ' ' || v_salary
        );
    END LOOP;

    CLOSE v_rc;
END;
/
~~~

In a real application, replace the literal `'SALARY'` with an input parameter. `CASE` permits only predefined choices. The `MIN_SALARY` value is still bound.

An allowlist controls which identifiers and keywords can be concatenated into SQL. Bind variables are still used for data values.

## 12. DBMS_ASSERT for identifier validation

Oracle provides the `DBMS_ASSERT` package with functions to validate or quote SQL names. Common functions:

| Function | General purpose |
|---|---|
| `SIMPLE_SQL_NAME` | Validates a simple SQL name |
| `QUALIFIED_SQL_NAME` | Validates a qualified name according to allowed syntax |
| `SQL_OBJECT_NAME` | Validates a SQL object name and checks existence per function rules |
| `ENQUOTE_NAME` | Quotes a SQL identifier |
| `ENQUOTE_LITERAL` | Quotes a SQL literal |

Example validating a simple name:

~~~sql
DECLARE
    v_input_name VARCHAR2(128) := 'LAB_EMPLOYEE';
    v_safe_name  VARCHAR2(128);
    v_sql        VARCHAR2(1000);
    v_count      NUMBER;
BEGIN
    v_safe_name := DBMS_ASSERT.SIMPLE_SQL_NAME(v_input_name);

    v_sql := 'SELECT COUNT(*) FROM ' || v_safe_name;

    EXECUTE IMMEDIATE v_sql INTO v_count;
    DBMS_OUTPUT.PUT_LINE(v_count);
END;
/
~~~

`DBMS_ASSERT` validates identifier shape, but it does not replace business authorization checks. A syntactically valid name can still point to an object the user is not authorized to access or should not be allowed to select.

### 12.1. Combining allowlist and DBMS_ASSERT

For a user-selected table name:

1. Compare the input against the list of allowed tables.
2. If valid, use `DBMS_ASSERT` to validate/quote the identifier appropriately.
3. Concatenate the identifier into the SQL statement.
4. Bind all data values.
5. Handle exceptions and log as needed.

The allowlist enforces business rules; `DBMS_ASSERT` provides syntactic/identifier validation. Use both when objects are selected from input.

### 12.2. Do not use ENQUOTE_LITERAL to replace bind variables

`ENQUOTE_LITERAL` can quote a literal in SQL syntax, but bind variables remain the better choice for data values. Binding avoids manual literal construction, preserves data types, and supports cursor sharing. Only use literal quoting when there is a specific reason and you understand the context.

## 13. SQL injection in dynamic SQL

SQL injection occurs when input data is concatenated into a SQL string and alters the structure or meaning of the statement.

Dangerous example:

~~~sql
v_sql :=
    'SELECT COUNT(*) FROM users WHERE username = '''
    || p_username || '''';
~~~

If input contains quotes and SQL expressions, the resulting string can differ from the intended statement. In real applications, injection can lead to unauthorized reads, modifications, or deletions if the program's privileges allow it.

### 13.1. Prevention rules

- Use bind variables for all bindable data values.
- Use allowlists for table names, columns, schemas, sort directions, and dynamic keywords.
- Use `DBMS_ASSERT` appropriately to validate identifiers.
- Never concatenate untrusted input directly into SQL.
- Grant least privilege to schemas and stored programs.
- Consider `AUTHID DEFINER` vs. `AUTHID CURRENT_USER` per security requirements.
- Do not return sensitive internal details in error messages sent to the UI.
- Log queries/errors per policy, avoiding secrets or credentials.

### 13.2. Why bind variables do not solve dynamic table names?

Binding only replaces values in expression positions where SQL permits binds. The parser must know the statement structure, tables, and columns before execution. Therefore, identifiers must be validated and concatenated into the SQL string.

Do not try to bind:

- Table or view names.
- Schema names.
- Column names.
- `ASC`/`DESC` keywords.
- Syntax clauses such as `JOIN` or `WHERE`.

## 14. What is DBMS_SQL?

`DBMS_SQL` is a PL/SQL package providing an API to parse, bind, define columns, execute, and fetch dynamic SQL at a lower level than Native Dynamic SQL.

NDS is usually suitable when the program knows in advance:

- The number of bind variables.
- The data types of bind variables.
- The number and types of returned columns.

`DBMS_SQL` is useful when the result structure is known only at runtime, such as:

- A reporting tool allowing variable column counts.
- An admin utility reading metadata and building `SELECT` statements with changing select lists.
- A framework needing to inspect result columns via `DESCRIBE_COLUMNS`.
- An application handling generic dynamic SQL where a record type cannot be declared in advance.

### 14.1. Basic DBMS_SQL workflow

Typical flow:

1. `OPEN_CURSOR` to get a cursor number.
2. `PARSE` to parse the SQL statement.
3. `BIND_VARIABLE` to attach values.
4. For `SELECT`, `DESCRIBE_COLUMNS` to inspect metadata if needed.
5. `DEFINE_COLUMN` to define target variables for each column.
6. `EXECUTE` to execute.
7. `FETCH_ROWS` to read rows.
8. `COLUMN_VALUE` to retrieve each column's value.
9. `CLOSE_CURSOR` to close the cursor.

### 14.2. DBMS_SQL skeleton example with one VARCHAR2 column

~~~sql
DECLARE
    v_cursor INTEGER;
    v_rows   INTEGER;
    v_value  VARCHAR2(4000);
    v_sql    VARCHAR2(1000);
BEGIN
    v_cursor := DBMS_SQL.OPEN_CURSOR;

    v_sql := 'SELECT last_name FROM employees WHERE department_id = :dept';

    DBMS_SQL.PARSE(
        v_cursor,
        v_sql,
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.BIND_VARIABLE(
        v_cursor,
        ':dept',
        50
    );

    DBMS_SQL.DEFINE_COLUMN(
        v_cursor,
        1,
        v_value,
        4000
    );

    v_rows := DBMS_SQL.EXECUTE(v_cursor);

    WHILE DBMS_SQL.FETCH_ROWS(v_cursor) > 0 LOOP
        DBMS_SQL.COLUMN_VALUE(
            v_cursor,
            1,
            v_value
        );

        DBMS_OUTPUT.PUT_LINE(v_value);
    END LOOP;

    DBMS_SQL.CLOSE_CURSOR(v_cursor);
EXCEPTION
    WHEN OTHERS THEN
        IF v_cursor IS NOT NULL
           AND DBMS_SQL.IS_OPEN(v_cursor)
        THEN
            DBMS_SQL.CLOSE_CURSOR(v_cursor);
        END IF;
        RAISE;
END;
/
~~~

This example uses a known single `VARCHAR2` column select list. For an unknown select list, the program calls `DESCRIBE_COLUMNS` (or an appropriate variant), then `DEFINE_COLUMN` matching each column's data type, and calls `COLUMN_VALUE` accordingly. A generic implementation must handle `NUMBER`, `DATE`, `VARCHAR2`, `CLOB`, and other supported types individually.

### 14.3. NDS vs. DBMS_SQL?

| Criterion | Native Dynamic SQL | DBMS_SQL |
|---|---|---|
| Syntax | Concise and close to regular SQL/PLSQL | Multi-step procedural API |
| Bind types known upfront | Suitable | Suitable |
| Select list known upfront | Suitable | Suitable |
| Column count/types unknown at compile time | Limited | Has `DESCRIBE_COLUMNS` and `DEFINE_COLUMN` |
| Returning multiple rows | `OPEN FOR` or `BULK COLLECT` | `FETCH_ROWS` |
| Common use cases | Application dynamic DML/SELECT/DDL | Generic SQL frameworks, metadata-driven tools |

Do not use `DBMS_SQL` just because SQL is built dynamically. If NDS fits the structure and data types, NDS is typically easier to write and maintain.

## 15. Converting between DBMS_SQL and REF CURSOR

Oracle provides conversion functions to bridge both APIs in certain cases:

- `DBMS_SQL.TO_REFCURSOR`: converts a `DBMS_SQL` cursor to a `REF CURSOR`.
- `DBMS_SQL.TO_CURSOR_NUMBER`: converts a `REF CURSOR` to a `DBMS_SQL` cursor number.

This is useful when one part of a program needs `DBMS_SQL` to describe dynamic SQL, while another part wants to return results via `REF CURSOR`. Conversion carries cursor ownership and state rules; once converted, do not continue using the cursor through the old API improperly. Review the Oracle documentation for your exact version before using this in shared frameworks.

## 16. Placeholders and bind order

When writing NDS, ensure bind count, order, and modes match the placeholders in the statement.

Example:

~~~sql
DECLARE
    v_sql VARCHAR2(500);
BEGIN
    v_sql :=
        'UPDATE employees ' ||
        'SET salary = :new_salary ' ||
        'WHERE employee_id = :employee_id';

    EXECUTE IMMEDIATE v_sql
        USING 9000, 100;
END;
/
~~~

The value `9000` binds to the first placeholder and `100` to the second placeholder in the SQL statement. To avoid confusion, keep bind order clear and use meaningfully named variables.

### 16.1. Repeated placeholders

Placeholder binding rules differ between dynamic SQL statements and anonymous PL/SQL blocks/`CALL`. In a SQL statement, bind arguments match placeholder occurrences positionally; if a placeholder name repeats, each occurrence in the SQL statement must be accounted for in the bind list per NDS rules. In anonymous PL/SQL blocks/`CALL`, repeated placeholder rules differ and should be verified against your Oracle version's documentation.

To minimize confusion, avoid unnecessary repeated placeholders or structure the statement so bind order is easy to verify. When passing many arguments, document the order clearly and cover it with tests on the target version.

### 16.2. Binding NULL values

In `USING`, do not pass the literal `NULL` directly as a bind argument. Use a PL/SQL variable whose value is `NULL`:

~~~sql
DECLARE
    v_null_value VARCHAR2(1);
    v_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM employees WHERE commission_pct = :x'
        INTO v_count
        USING v_null_value;
END;
/
~~~

Note: `COLUMN = NULL` does not evaluate to `TRUE`; to match `NULL`, the proper predicate is usually `COLUMN IS NULL`. The example above illustrates passing a `NULL` bind variable, not how to test for `NULL` in SQL.

## 17. Dynamic SQL with multiple optional conditions

A report may accept optional `department_id` and minimum salary filters. There are two design options:

### 17.1. Keep static SQL with optional predicates

~~~sql
SELECT employee_id, last_name, salary
FROM employees
WHERE (p_department_id IS NULL
       OR department_id = p_department_id)
  AND (p_min_salary IS NULL
       OR salary >= p_min_salary);
~~~

This illustrates the logic; in PL/SQL, parameter variables are used directly inside static SQL. This keeps the statement static, easy to check, and cleanly bound.

However, predicates like `:p IS NULL OR column = :p` can affect cardinality estimates or index usage depending on data, bind peeking, and the optimizer. Measure the execution plan under realistic workloads.

### 17.2. Build predicates dynamically

~~~sql
DECLARE
    v_sql VARCHAR2(2000);
    v_count NUMBER;
    v_dept_id NUMBER := 50;
    v_min_salary NUMBER := 5000;
BEGIN
    v_sql := 'SELECT COUNT(*) FROM employees WHERE 1 = 1';

    IF v_dept_id IS NOT NULL THEN
        v_sql := v_sql || ' AND department_id = :dept';
    END IF;

    IF v_min_salary IS NOT NULL THEN
        v_sql := v_sql || ' AND salary >= :min_salary';
    END IF;

    -- This example illustrates the case where both parameters have values.
    EXECUTE IMMEDIATE v_sql
        INTO v_count
        USING v_dept_id, v_min_salary;

    DBMS_OUTPUT.PUT_LINE(v_count);
END;
/
~~~

If parameters can be `NULL` and the number of predicates varies, the `USING` clause must also match the actual placeholder count. You cannot always pass a fixed list of all variables if the SQL string omits some placeholders. You can use `IF` branches with dedicated `EXECUTE IMMEDIATE` statements per combination, or build a flexible binding mechanism such as `DBMS_SQL` when appropriate.

### 17.3. Choosing between the two approaches

| Condition | Approach to consider |
|---|---|
| Few parameters, stable predicates | Static SQL with optional predicates |
| Small number of distinct query shapes | `IF` branches, each running static SQL |
| Number of predicates varies by configuration | Dynamic SQL with careful bind management |
| Table/column names must change | Dynamic SQL with identifier allowlist |
| Generic metadata-driven query structure | NDS or `DBMS_SQL` |

Do not choose dynamic SQL just to avoid writing a few `IF` branches. Weigh clarity, execution plans, and maintainability.

## 18. Execution privileges: AUTHID DEFINER and AUTHID CURRENT_USER

Stored procedures/functions run with the privileges of either the definer or the invoker depending on `AUTHID`:

- `AUTHID DEFINER`: definer-rights; privileges are evaluated against the program owner's privilege context, following Oracle rules on roles and direct grants.
- `AUTHID CURRENT_USER`: invoker-rights; privileges are evaluated against the caller in the invoker-rights context.

Example:

~~~sql
CREATE OR REPLACE PROCEDURE lab_count_rows
AUTHID CURRENT_USER
AS
    v_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM lab_employee'
        INTO v_count;

    DBMS_OUTPUT.PUT_LINE(v_count);
END;
/
~~~

Dynamic SQL is parsed at runtime, but it does not bypass Oracle's security model. Object privileges, system privileges, roles, and definer/invoker context still apply according to stored PL/SQL rules.

In particular, dynamic SQL inside a definer-rights program must be designed carefully. If a caller can control identifiers or predicates, the program could be abused to execute actions with the owner's privileges. Use allowlists, bind variables, and least privilege.

## 19. Dependencies and runtime errors in dynamic SQL

Static SQL lets the compiler recognize referenced objects. With dynamic SQL, string contents are usually parsed only at runtime:

~~~sql
EXECUTE IMMEDIATE
    'SELECT missing_column FROM missing_table';
~~~

A PL/SQL block containing the string above can compile even if the table or column does not exist, because the SQL inside the string is not validated by the compiler like static SQL. Only at execution time does Oracle parse it and report errors like table does not exist or invalid identifier.

Consequences:

- Typos in table/column names may surface only at runtime.
- Renaming or altering schema objects can break old dynamic SQL strings.
- Tests must cover all generated dynamic SQL variants.
- Log normalized SQL templates and error codes for troubleshooting, without logging secrets or sensitive values.

## 20. Performance and parsing in dynamic SQL

Dynamic SQL adds string construction and runtime statement parsing overhead. Oracle can reuse cursors when SQL text matches and execution environments are compatible, but generating many distinct strings unnecessarily reduces cursor sharing.

### 20.1. Avoid continuously varying literals

Unfavorable example:

~~~sql
v_sql :=
    'SELECT COUNT(*) FROM employees WHERE department_id = '
    || TO_CHAR(v_department_id);

EXECUTE IMMEDIATE v_sql INTO v_count;
~~~

Each department value can generate a different SQL text. Better approach:

~~~sql
v_sql :=
    'SELECT COUNT(*) FROM employees WHERE department_id = :dept';

EXECUTE IMMEDIATE v_sql
    INTO v_count
    USING v_department_id;
~~~

The SQL text stays stable and the value is bound separately.

### 20.2. Hard parse and soft parse

- **Hard parse**: Oracle must parse and optimize a new SQL statement or cannot reuse a matching cursor.
- **Soft parse**: Oracle finds a reusable cursor in the shared pool and reduces parsing work.

Bind variables help multiple executions share the same SQL text. However, cursor sharing also depends on bind types, schema, optimizer environment, privileges, object state, and other factors.

### 20.3. Do not turn all SQL into dynamic SQL

When a SQL statement's structure does not change, static SQL is usually:

- Easier to read and review.
- Free from unsafe string concatenation risks.
- Explicit in its object dependencies.
- Validated at compile time.
- Easier to trace in developer tools.

Dynamic SQL should only be used when runtime flexibility delivers real value.

## 21. Error handling in dynamic SQL

Commonly encountered errors:

- `ORA-00942`: table or view does not exist.
- `ORA-00904`: invalid identifier.
- `ORA-01008`: not all variables bound.
- `ORA-01006`: bind variable does not exist.
- `ORA-01403`: no data found.
- `ORA-01422`: exact fetch returns more than requested number of rows.
- `ORA-01031`: insufficient privileges.

Handling example:

~~~sql
DECLARE
    v_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM employees WHERE department_id = :d'
        INTO v_count
        USING 50;

    DBMS_OUTPUT.PUT_LINE(v_count);
EXCEPTION
    WHEN NO_DATA_FOUND THEN
        DBMS_OUTPUT.PUT_LINE('No row returned');
    WHEN OTHERS THEN
        DBMS_OUTPUT.PUT_LINE(
            'Error ' || SQLCODE || ': ' || SQLERRM
        );
        RAISE;
END;
/
~~~

`COUNT(*)` always returns one row even when no rows match the predicate, so `NO_DATA_FOUND` will not trigger in this particular example. The handler merely illustrates exception structuring; in real applications, catch errors matching realistic scenarios and never swallow unexpected errors.

### 21.1. Logging SQL statements and bind values

When investigating errors, you need to know:

- Which SQL template was executed.
- Which binds were passed, with what types and positions.
- Relevant schema/current user and module/action.
- `SQLCODE`/`SQLERRM` and timestamp.

Never write passwords, tokens, personal data, or confidential values to logs. You can log a request identifier and normalized SQL template to correlate events.

## 22. Transaction behavior of dynamic SQL

`EXECUTE IMMEDIATE` does not create an independent transaction for DML. Dynamic `INSERT`/`UPDATE`/`DELETE` statements participate in the current transaction just like static DML:

~~~sql
BEGIN
    EXECUTE IMMEDIATE
        'UPDATE employees SET salary = salary + 100 WHERE employee_id = 100';

    ROLLBACK;
END;
/
~~~

The `UPDATE` is rolled back if there was no prior `COMMIT`. Conversely, dynamic DDL still follows Oracle's implicit commit rules.

Do not insert `COMMIT` or `ROLLBACK` inside dynamic blocks arbitrarily. Agree clearly on which layer owns the transaction: caller or procedure. Reusable procedures should normally avoid auto-committing if callers need to coordinate multiple business steps in one transaction.

## 23. Criteria for choosing static SQL vs. dynamic SQL

### 23.1. Decision table

| Question | Prefer |
|---|---|
| Are tables and columns known when writing the program? | Static SQL |
| Do only `WHERE` values change? | Static SQL with bind variables |
| Are there just a few fixed query shapes? | Static SQL with `IF`/`CASE` |
| Do table/column names change at runtime? | Dynamic SQL with allowlist and identifier checks |
| Is runtime DDL needed? | Dynamic SQL |
| Are select-list column count/types unknown upfront? | `DBMS_SQL` |
| Need to return multiple rows of known types? | Static cursor or `OPEN FOR` |
| Need to run many DML statements with fixed structure? | Static SQL |
| Need to generate SQL from metadata or config? | Dynamic SQL, consider `DBMS_SQL` |

### 23.2. Scenario-based examples

**Scenario A — Department salary raise**

~~~sql
UPDATE employees
SET salary = salary * 1.05
WHERE department_id = p_department_id;
~~~

Table, columns, and structure are fixed; only the department value changes. Use static SQL.

**Scenario B — Choosing an archive table by year**

The application has `SALES_2024`, `SALES_2025`, `SALES_2026` tables and picks the table by reporting year. The table name varies at runtime. Dynamic SQL is needed, but the year must be validated and mapped to an allowed table name.

**Scenario C — Report with selectable sort column**

Users choose to sort by `DATE`, `CUSTOMER`, or `AMOUNT`. Use an identifier allowlist and concatenate the validated column name; filter values still use binds.

**Scenario D — Admin utility browsing arbitrary tables**

An operator selects a table and wants to display its columns without knowing count/types ahead of time. `DBMS_SQL` may be needed to describe the select list and read columns by metadata.

## 24. Checklist for writing safe dynamic SQL

Before constructing a dynamic SQL statement:

1. Identify which parts truly need to change at runtime.
2. Keep table/column names fixed if possible.
3. Use bind variables for all data values.
4. Use allowlists for identifiers and keywords.
5. Use `DBMS_ASSERT` to validate identifiers in context.
6. Never concatenate untrusted input directly into SQL.
7. Verify bind count, order, and modes.
8. Handle single-row `SELECT`, multi-row `SELECT`, and DML with the right APIs.
9. Handle cursors and exceptions so cursors never leak.
10. Verify execution privileges and transaction behavior.
11. Test all possible generated SQL string configurations.
12. Measure parsing, execution plans, and runtime on representative workloads.

Diagram:

~~~text
Need dynamic SQL?
      |
      v
Does SQL structure truly change?
       /             \
     No              Yes
      |                |
      v                v
 Static SQL      Classify changing parts
                       |
              +--------+---------+
              |                  |
           Values         Identifiers/DDL
              |                  |
              v                  v
         Bind variable      Allowlist + DBMS_ASSERT
              |                  |
              +--------+---------+
                       |
                       v
                Choose NDS or DBMS_SQL
                       |
                       v
             Verify binds and result types
                       |
                       v
             Privileges, transaction, errors
                       |
                       v
               Test and measure runtime
~~~

## 25. Hands-on exercises

### Exercise 1 — Recognizing static SQL

Write a procedure to raise an employee's salary by `employee_id`. Use a PL/SQL parameter in `WHERE`.

**Question:** Why is this static SQL even though the `employee_id` value changes on every call?

### Exercise 2 — EXECUTE IMMEDIATE with binds

Write a block updating `salary` by `department_id` and raise rate passed via variables. Print `SQL%ROWCOUNT`.

### Exercise 3 — Dynamic single-row SELECT

Write `EXECUTE IMMEDIATE` to fetch `last_name` by `employee_id`. Handle `NO_DATA_FOUND` and `TOO_MANY_ROWS` appropriately.

### Exercise 4 — OPEN FOR

Write a dynamic cursor reading `employee_id`, `last_name`, and `salary` by `department_id`. Fetch row by row and close the cursor even when errors occur.

### Exercise 5 — Dynamic table name

Write a procedure allowing selection among three predefined lab tables. Use `CASE`/allowlist to validate the table name and bind filter values.

### Exercise 6 — SQL injection

Create an example concatenating `last_name` directly into a SQL string and explain the risk when input contains quotes. Rewrite it using a bind variable.

### Exercise 7 — DBMS_ASSERT

Use `SIMPLE_SQL_NAME` to validate a simple name. Explain why a business-object allowlist is still necessary.

### Exercise 8 — Dynamic DDL

Use `EXECUTE IMMEDIATE` to create a lab table whose name is picked from an allowed list. Explain the implicit commit impact of DDL.

### Exercise 9 — NDS vs. DBMS_SQL

A report has a varying number of columns based on runtime selection. Explain why `DBMS_SQL` fits better than `SELECT INTO` or `OPEN FOR` with a fixed record.

### Exercise 10 — Architecture choice

A procedure accepts `department_id`, `min_salary`, `sort_column`, and an archive table name. Classify each parameter:

- Which data values need binding?
- Which identifiers need an allowlist?
- Which parts can remain static SQL?
- When would `DBMS_SQL` be needed?

## 26. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| `ORA-00942` | Wrong table/view name or missing privilege | Check schema, object, and grants |
| `ORA-00904` | Wrong column name or identifier | Validate column names, check metadata |
| `ORA-01008` | Missing bind argument | Match placeholders against `USING` |
| `ORA-01006` | Bind placeholder does not exist | Inspect SQL string and bind list |
| `ORA-01403` | `SELECT INTO` returns no rows | Handle `NO_DATA_FOUND` or revise logic |
| `ORA-01422` | `SELECT INTO` returns multiple rows | Use cursor/`BULK COLLECT` or limit results |
| SQL injection | Concatenating untrusted input into SQL | Bind values, allowlist identifiers |
| Unclosed cursor | Exception exits before `CLOSE` | Close cursor in exception handler |
| Dynamic SQL parses repeatedly | SQL text varies from concatenated literals | Use binds to keep SQL text stable |
| DDL commits prior DML | DDL implicit commit | Separate schema maintenance from business transactions |
| Procedure fails on privileges | Wrong `AUTHID`/grant context | Check direct grants, roles, and invoker/definer rights |

## 27. Selection conclusion

Static SQL is suitable when the statement structure is known and only data values change. Dynamic SQL is suitable when the SQL structure itself or identifiers must be determined at runtime. For dynamic SQL, prefer Native Dynamic SQL when bind and result counts/types are known; use `DBMS_SQL` when handling generic result structures unknown upfront.

Data values should be bound. Table names, column names, and varying syntax must be controlled with allowlists and identifier validation. Dynamic DDL still performs an implicit commit; dynamic DML still participates in the current transaction. By choosing the right tool and keeping a clear boundary between data and syntax, PL/SQL programs stay easier to maintain, safer, and predictable in execution behavior.
