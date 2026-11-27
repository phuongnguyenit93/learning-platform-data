# DBMS_SQL When Column Counts or Bind Variables Are Unknown Upfront in Oracle PL/SQL

Dynamic SQL lets a program build and execute SQL statements at runtime. With Native Dynamic SQL (NDS), PL/SQL typically uses `EXECUTE IMMEDIATE` or `OPEN FOR`. That approach is concise and works well when the statement structure, bind variable count, and result data types are known at coding time.

However, there are scenarios where the application receives a SQL statement only at runtime:

- A reporting tool allows users to pick an arbitrary number of columns.
- A search filter generates a varying number of predicates based on UI selections.
- An admin utility reads a `SELECT` statement from configuration.
- A framework needs to read results without knowing column names and types ahead of time.
- A SQL executor receives a list of bind variables from metadata.

In these cases, column counts or bind variable counts may be unknown when compiling PL/SQL. The **`DBMS_SQL`** package provides a procedural API to open a cursor, parse SQL, describe result columns, define target variables, bind values, execute, and fetch row by row.

An important distinction: `DBMS_SQL` can describe result set columns after parsing a `SELECT`, but it does not provide a general API equivalent to `DESCRIBE_COLUMNS` to auto-discover all bind placeholders in an arbitrary SQL statement. If the bind count is unknown, the application needs metadata on bind names and types from the SQL generator or an explicit input contract. `DBMS_SQL` helps perform dynamic binding from that metadata.

## 1. When is DBMS_SQL needed?

### 1.1 Native Dynamic SQL fits when structure is known

If the SQL statement and target variable count are known ahead of time, `EXECUTE IMMEDIATE` is usually the simplest option:

~~~sql
DECLARE
    l_count NUMBER;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT COUNT(*) FROM employees WHERE department_id = :dept'
        INTO l_count
        USING 10;

    DBMS_OUTPUT.PUT_LINE(l_count);
END;
/
~~~

If the `SELECT` column count is known upfront:

~~~sql
DECLARE
    l_name employees.last_name%TYPE;
    l_salary employees.salary%TYPE;
BEGIN
    EXECUTE IMMEDIATE
        'SELECT last_name, salary
           FROM employees
          WHERE employee_id = :id'
        INTO l_name, l_salary
        USING 100;
END;
/
~~~

PL/SQL requires an `INTO` variable list matching the result columns. If the column count varies across SQL statements, you cannot write a fixed `INTO` list that works for every statement.

### 1.2 DBMS_SQL fits when column counts or types are known only at runtime

`DBMS_SQL` lets you:

1. Open a cursor with `OPEN_CURSOR`.
2. Parse the SQL statement with `PARSE`.
3. Describe column count and metadata with `DESCRIBE_COLUMNS`.
4. Call `DEFINE_COLUMN` for each column with the matching data type.
5. Execute the statement.
6. Fetch row by row and retrieve values via `COLUMN_VALUE`.
7. Close the cursor with `CLOSE_CURSOR`.

~~~text
OPEN_CURSOR
    |
    v
PARSE SQL
    |
    v
DESCRIBE_COLUMNS
    |
    v
DEFINE_COLUMN for each column
    |
    v
EXECUTE
    |
    v
FETCH_ROWS
    |
    v
COLUMN_VALUE for each column
    |
    v
CLOSE_CURSOR
~~~

### 1.3 DBMS_SQL is also useful when the bind list is supplied at runtime

If a SQL builder produces a SQL statement along with its placeholder list and data types, the program can iterate through the metadata and call `BIND_VARIABLE` repeatedly. This handles varying bind counts cleanly.

`DBMS_SQL` cannot infer business values, intended data types, or the meaning of placeholders on its own. That information must come from the caller, configuration, or SQL builder.

## 2. DBMS_SQL vs. Native Dynamic SQL

| Criterion | Native Dynamic SQL | DBMS_SQL |
|---|---|---|
| Primary API | `EXECUTE IMMEDIATE`, `OPEN FOR` | `OPEN_CURSOR`, `PARSE`, `BIND_VARIABLE`, `DEFINE_COLUMN`, `EXECUTE`, `FETCH_ROWS` |
| Result column count | Usually must be known upfront in PL/SQL | Can be described at runtime |
| Bind variable count | `USING` list written explicitly | Can bind in a loop from metadata |
| Data types | Easy with known PL/SQL types | Must dispatch the right overload from metadata |
| Code length | Usually shorter | More steps and cursor state tracking |
| Best fit | Dynamic SQL with known structure | Generic SQL, unknown result structure |
| Cursor conversion | Can use `SYS_REFCURSOR` | Can convert via `TO_REFCURSOR` and `TO_CURSOR_NUMBER` |

Do not use `DBMS_SQL` for every dynamic SQL statement. If column and bind counts are known, NDS is usually easier to read, easier to maintain, and shorter. Choose `DBMS_SQL` when runtime structural generality is truly required.

## 3. DBMS_SQL cursor lifecycle

### 3.1 OPEN_CURSOR

`OPEN_CURSOR` allocates a cursor number:

~~~sql
l_cursor := DBMS_SQL.OPEN_CURSOR;
~~~

The cursor number is an internal handle of `DBMS_SQL`, not a SQL cursor name or `SYS_REFCURSOR`.

### 3.2 PARSE

`PARSE` parses the SQL statement:

~~~sql
DBMS_SQL.PARSE(
    c             => l_cursor,
    statement     => l_sql,
    language_flag => DBMS_SQL.NATIVE
);
~~~

`DBMS_SQL.NATIVE` specifies Oracle's native SQL/PLSQL syntax. Parsing validates syntax and prepares the statement; for `SELECT`, result metadata can be described after this step.

### 3.3 DESCRIBE_COLUMNS

After parsing a `SELECT`, you can call `DESCRIBE_COLUMNS` or an extended variant:

~~~sql
DBMS_SQL.DESCRIBE_COLUMNS2(
    c       => l_cursor,
    col_cnt => l_col_count,
    desc_t  => l_desc
);
~~~

`DESCRIBE_COLUMNS2` returns the column count and per-column descriptions via `DESC_TAB2`. Metadata typically includes:

- `COL_NAME`: column name or alias.
- `COL_TYPE`: Oracle data type code.
- `COL_MAX_LEN`: maximum described length.
- `COL_PRECISION` and `COL_SCALE`: precision/scale when applicable.
- `COL_NULL_OK`: described nullability flag.
- Charset or type metadata fields depending on record/version.

`DESCRIBE_COLUMNS3` and `DESC_TAB3` can be used when extended metadata—such as type/schema names for applicable types—is needed. Check the package specification for your deployed Oracle version.

### 3.4 DEFINE_COLUMN

For `SELECT`, you must define a target variable for each column before fetching:

~~~sql
DBMS_SQL.DEFINE_COLUMN(l_cursor, 1, l_varchar_value, 32767);
DBMS_SQL.DEFINE_COLUMN(l_cursor, 2, l_number_value);
DBMS_SQL.DEFINE_COLUMN(l_cursor, 3, l_date_value);
~~~

The chosen overload must match the returned data type. Do not use a single `VARCHAR2` variable for every column type and assume Oracle converts every type safely.

### 3.5 EXECUTE

~~~sql
l_result := DBMS_SQL.EXECUTE(l_cursor);
~~~

For DML, the return value indicates the number of processed rows per `DBMS_SQL` semantics. For `SELECT`, call `FETCH_ROWS` to retrieve result rows; do not treat the return value of `EXECUTE` as the `SELECT` row count.

### 3.6 FETCH_ROWS and COLUMN_VALUE

`FETCH_ROWS` retrieves the next row:

~~~sql
WHILE DBMS_SQL.FETCH_ROWS(l_cursor) > 0 LOOP
    DBMS_SQL.COLUMN_VALUE(l_cursor, 1, l_varchar_value);
END LOOP;
~~~

`COLUMN_VALUE` copies a defined column's value into the corresponding PL/SQL variable. Column positions are 1-based.

### 3.7 CLOSE_CURSOR

When finished, always close the cursor:

~~~sql
DBMS_SQL.CLOSE_CURSOR(l_cursor);
~~~

Leaving a cursor open holds session resources and can cause maximum open cursors errors. Ensure closing on exception paths as well.

## 4. Example: reading a SELECT with unknown column count

The example below receives a `SELECT` at runtime. For illustration, it supports three common scalar types: `VARCHAR2`, `NUMBER`, and `DATE`. Other types explicitly raise an unsupported-type error; in production code, add overloads for `TIMESTAMP`, `RAW`, `CLOB`, `BLOB`, `BINARY_FLOAT`, object types, or others as needed.

~~~sql
SET SERVEROUTPUT ON

DECLARE
    l_sql       VARCHAR2(32767) :=
        'SELECT table_name, num_rows, last_analyzed
           FROM user_tables
          WHERE table_name LIKE ''EMP%''';

    l_cursor    INTEGER;
    l_col_count PLS_INTEGER;
    l_desc      DBMS_SQL.DESC_TAB2;
    l_exec      INTEGER;
    l_fetch     INTEGER;

    l_varchar   VARCHAR2(32767);
    l_number    NUMBER;
    l_date      DATE;
BEGIN
    l_cursor := DBMS_SQL.OPEN_CURSOR;

    DBMS_SQL.PARSE(
        l_cursor,
        l_sql,
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.DESCRIBE_COLUMNS2(
        l_cursor,
        l_col_count,
        l_desc
    );

    DBMS_OUTPUT.PUT_LINE('Column count = ' || l_col_count);

    -- Define buffers for each column based on described type.
    FOR i IN 1 .. l_col_count LOOP
        DBMS_OUTPUT.PUT_LINE(
            'Column ' || i ||
            ': ' || l_desc(i).col_name ||
            ', type code=' || l_desc(i).col_type ||
            ', max length=' || l_desc(i).col_max_len
        );

        CASE l_desc(i).col_type
            WHEN 1 THEN
                DBMS_SQL.DEFINE_COLUMN(
                    l_cursor, i, l_varchar, 32767
                );
            WHEN 2 THEN
                DBMS_SQL.DEFINE_COLUMN(
                    l_cursor, i, l_number
                );
            WHEN 12 THEN
                DBMS_SQL.DEFINE_COLUMN(
                    l_cursor, i, l_date
                );
            ELSE
                RAISE_APPLICATION_ERROR(
                    -20001,
                    'Unsupported column type code: ' ||
                    l_desc(i).col_type ||
                    ' for column ' || l_desc(i).col_name
                );
        END CASE;
    END LOOP;

    l_exec := DBMS_SQL.EXECUTE(l_cursor);

    WHILE DBMS_SQL.FETCH_ROWS(l_cursor) > 0 LOOP
        FOR i IN 1 .. l_col_count LOOP
            CASE l_desc(i).col_type
                WHEN 1 THEN
                    DBMS_SQL.COLUMN_VALUE(l_cursor, i, l_varchar);
                    DBMS_OUTPUT.PUT_LINE(
                        l_desc(i).col_name || '=' || NVL(l_varchar, '<NULL>')
                    );
                WHEN 2 THEN
                    DBMS_SQL.COLUMN_VALUE(l_cursor, i, l_number);
                    DBMS_OUTPUT.PUT_LINE(
                        l_desc(i).col_name || '=' ||
                        NVL(TO_CHAR(l_number), '<NULL>')
                    );
                WHEN 12 THEN
                    DBMS_SQL.COLUMN_VALUE(l_cursor, i, l_date);
                    DBMS_OUTPUT.PUT_LINE(
                        l_desc(i).col_name || '=' ||
                        NVL(TO_CHAR(l_date, 'YYYY-MM-DD HH24:MI:SS'), '<NULL>')
                    );
            END CASE;
        END LOOP;

        DBMS_OUTPUT.PUT_LINE('---');
    END LOOP;

    DBMS_SQL.CLOSE_CURSOR(l_cursor);
EXCEPTION
    WHEN OTHERS THEN
        IF l_cursor IS NOT NULL
           AND DBMS_SQL.IS_OPEN(l_cursor)
        THEN
            DBMS_SQL.CLOSE_CURSOR(l_cursor);
        END IF;
        RAISE;
END;
/
~~~

### 4.1 Why are two loops needed?

The first loop walks metadata to call `DEFINE_COLUMN` for all result columns. Oracle needs to know target variables and types before `FETCH_ROWS`.

The second loop runs after each `FETCH_ROWS`, reading each column's value via `COLUMN_VALUE`. Both loops rely on the column count returned by `DESCRIBE_COLUMNS2`, so the column count does not need to be known beforehand.

### 4.2 Why does the example support only three types?

`DBMS_SQL` uses strongly typed overloads. The example intentionally supports only `VARCHAR2` (type code 1), `NUMBER` (2), and `DATE` (12) to demonstrate the dispatch mechanism. A generic result set can contain many more types:

- `CHAR`, `NCHAR`, `NVARCHAR2`.
- `TIMESTAMP` and `TIMESTAMP WITH TIME ZONE`.
- `INTERVAL`.
- `RAW`.
- `CLOB`, `NCLOB`, `BLOB`.
- `BINARY_FLOAT`, `BINARY_DOUBLE`.
- Object types or other specialized types.

Each type requires choosing the corresponding PL/SQL variable, `DEFINE_COLUMN`, and `COLUMN_VALUE`. Long or special types require dedicated APIs such as `DEFINE_COLUMN_LONG`/`COLUMN_VALUE_LONG`. Never convert all values blindly to strings without accounting for length, charset, date formats, and numeric precision.

### 4.3 Handling column aliases and duplicate names

A result set can contain two columns with the same name if the SQL omits distinct aliases. When building metadata for clients, keep column position as the stable identifier and assign unique aliases if needed. `COL_NAME` is display metadata; do not use it as a lookup key instead of column position.

## 5. Data types and DEFINE_COLUMN

`DBMS_SQL` offers many `DEFINE_COLUMN` overloads. The rule is that the target variable type must be compatible with the described SQL type.

| SQL result type | Illustrative PL/SQL variable | Notes |
|---|---|---|
| `VARCHAR2` | `VARCHAR2` | Must specify buffer size in the appropriate overload |
| `CHAR` | `CHAR` or appropriate `VARCHAR2` | Check length and padding semantics |
| `NUMBER` | `NUMBER` | Preserves precision/scale |
| `DATE` | `DATE` | Formatting applies only when displaying |
| `TIMESTAMP` | `TIMESTAMP` | Requires the matching timestamp overload |
| `RAW` | `RAW` | Buffer must be large enough |
| `CLOB` | `CLOB` | Handle LOB locator and read content properly |
| `BLOB` | `BLOB` | Handle binary LOB; do not convert arbitrarily to `VARCHAR2` |
| `LONG` | Dedicated `LONG` API | Use `DEFINE_COLUMN_LONG`/`COLUMN_VALUE_LONG` per API limits |

Example with timestamp:

~~~sql
DECLARE
    l_ts TIMESTAMP;
BEGIN
    -- After PARSE and DESCRIBE:
    -- DBMS_SQL.DEFINE_COLUMN(l_cursor, l_position, l_ts);
    NULL;
END;
/
~~~

This snippet only illustrates the variable type. In real code, place `DEFINE_COLUMN` in the define phase before `EXECUTE`/`FETCH` and call `COLUMN_VALUE` with the same type.

### 5.1 COL_MAX_LEN is not always the full buffer size

`COL_MAX_LEN` is metadata describing column length in the result descriptor. For character data, consider byte/character semantics, charset, and PL/SQL variable limits. For LOBs or special types, you cannot simply allocate `VARCHAR2(COL_MAX_LEN)` and treat it as complete handling.

### 5.2 NULL is still a valid value

If a column returns `NULL`, `COLUMN_VALUE` sets the target variable to `NULL`. That differs from a missing column: columns are always identified by position in metadata; `NULL` is the row's value at that column position.

## 6. Bind variables with DBMS_SQL

### 6.1 Binding by name

`DBMS_SQL` supports binding by placeholder name:

~~~sql
DECLARE
    l_cursor INTEGER;
    l_rows   INTEGER;
    l_salary NUMBER := 8000;
    l_emp_id NUMBER := 100;
BEGIN
    l_cursor := DBMS_SQL.OPEN_CURSOR;

    DBMS_SQL.PARSE(
        l_cursor,
        'UPDATE employees
            SET salary = :new_salary
          WHERE employee_id = :emp_id',
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.BIND_VARIABLE(
        l_cursor, ':new_salary', l_salary
    );
    DBMS_SQL.BIND_VARIABLE(
        l_cursor, ':emp_id', l_emp_id
    );

    l_rows := DBMS_SQL.EXECUTE(l_cursor);

    DBMS_OUTPUT.PUT_LINE('Rows processed=' || l_rows);

    DBMS_SQL.CLOSE_CURSOR(l_cursor);
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF l_cursor IS NOT NULL
           AND DBMS_SQL.IS_OPEN(l_cursor)
        THEN
            DBMS_SQL.CLOSE_CURSOR(l_cursor);
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

In this example, the `UPDATE` has two bind placeholders. `DBMS_SQL.BIND_VARIABLE` is called separately for each name. Data values are passed via binds instead of concatenated into the SQL string.

### 6.2 Varying bind counts driven by metadata

Suppose a SQL generator returns:

- SQL text.
- List of bind names.
- Data type of each bind.
- Corresponding values.

PL/SQL can iterate over the list and invoke the matching overload:

~~~sql
FOR i IN 1 .. l_bind_count LOOP
    CASE l_binds(i).data_type
        WHEN 'NUMBER' THEN
            DBMS_SQL.BIND_VARIABLE(
                l_cursor,
                l_binds(i).bind_name,
                l_binds(i).number_value
            );
        WHEN 'VARCHAR2' THEN
            DBMS_SQL.BIND_VARIABLE(
                l_cursor,
                l_binds(i).bind_name,
                l_binds(i).varchar_value
            );
        WHEN 'DATE' THEN
            DBMS_SQL.BIND_VARIABLE(
                l_cursor,
                l_binds(i).bind_name,
                l_binds(i).date_value
            );
        ELSE
            RAISE_APPLICATION_ERROR(
                -20002,
                'Unsupported bind type: ' || l_binds(i).data_type
            );
    END CASE;
END LOOP;
~~~

This is the core of the metadata-driven binding model. `L_BINDS` and its fields in the example are application-defined data structures; they are not built-in `DBMS_SQL` types. A real implementation must declare appropriate records/collections or use separate collections per data type.

### 6.3 DBMS_SQL does not auto-describe bind placeholders

`DESCRIBE_COLUMNS` describes `SELECT` result columns, not a SQL statement's bind variable list. `DBMS_SQL` does not provide a generic operation to ask: "Which placeholders exist in this arbitrary SQL statement, and what is the expected type of each?"

Therefore, if the bind count is unknown upfront:

1. The SQL builder should emit SQL and bind metadata together.
2. Metadata must include placeholder name, type, and value.
3. Code iterates through metadata to bind each variable.
4. Parse/execute will catch missing binds or incompatible types.

Do not try to discover placeholders using a simple regex on SQL text. Colons can appear inside string literals, comments, quoted identifiers, or other syntax; a general SQL parser must understand real SQL grammar.

### 6.4 Repeated placeholders

If the same placeholder name appears multiple times in SQL, bind consistently by name. Do not create duplicate bind metadata entries with different values under the same name. One placeholder represents one bind value; if two independent values are needed, use two distinct names.

### 6.5 Binding typed NULLs

When binding `NULL`, use a PL/SQL variable with the desired type:

~~~sql
DECLARE
    l_number_value NUMBER := NULL;
BEGIN
    DBMS_SQL.BIND_VARIABLE(
        l_cursor,
        ':p_amount',
        l_number_value
    );
END;
/
~~~

A `NUMBER`-typed variable selects the `NUMBER` bind overload. Avoid passing an untyped `NULL` expression when overloads would be ambiguous.

## 7. Distinguishing bind values from SQL identifiers

Bind variables substitute data values, not table names, column names, keywords, or sort directions.

Valid:

~~~sql
SELECT employee_id, salary
FROM employees
WHERE department_id = :dept_id;
~~~

You cannot use a bind placeholder to replace a table name:

~~~sql
SELECT *
FROM :table_name;
~~~

If table/column names must change at runtime, construct identifiers from an allowed list and validate/quote them properly. You can use `DBMS_ASSERT` functions like `SIMPLE_SQL_NAME` or `SQL_OBJECT_NAME` in context, but `DBMS_ASSERT` does not replace whitelisting and business authorization checks.

Example:

~~~sql
DECLARE
    l_table_name VARCHAR2(128) := 'EMPLOYEES';
    l_sql        VARCHAR2(1000);
    l_cursor     INTEGER;
BEGIN
    l_table_name := DBMS_ASSERT.SIMPLE_SQL_NAME(l_table_name);

    l_sql := 'SELECT COUNT(*) FROM ' || l_table_name ||
             ' WHERE department_id = :dept';

    l_cursor := DBMS_SQL.OPEN_CURSOR;
    DBMS_SQL.PARSE(l_cursor, l_sql, DBMS_SQL.NATIVE);
    DBMS_SQL.BIND_VARIABLE(l_cursor, ':dept', 10);
    -- Define/fetch or execute depending on statement type.
    DBMS_SQL.CLOSE_CURSOR(l_cursor);
END;
/
~~~

This example only illustrates identifier validation and binding values; in real applications, the table must belong to a business allowlist and be accessed according to user/session privileges.

Never concatenate user input directly into SQL text. Binding values prevents SQL injection in value positions; dynamic identifiers require a separate validation policy.

## 8. DBMS_SQL for DML with dynamic bind counts

For DML, `DESCRIBE_COLUMNS` and `DEFINE_COLUMN` are unnecessary when the statement returns no result set. The workflow is `OPEN_CURSOR`, `PARSE`, bind each placeholder, `EXECUTE`, then `CLOSE_CURSOR`.

~~~sql
DECLARE
    l_cursor INTEGER;
    l_rows   INTEGER;
    l_dept   NUMBER := 20;
    l_raise  NUMBER := 500;
BEGIN
    l_cursor := DBMS_SQL.OPEN_CURSOR;

    DBMS_SQL.PARSE(
        l_cursor,
        'UPDATE employees
            SET salary = salary + :raise_amount
          WHERE department_id = :department_id',
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.BIND_VARIABLE(l_cursor, ':raise_amount', l_raise);
    DBMS_SQL.BIND_VARIABLE(l_cursor, ':department_id', l_dept);

    l_rows := DBMS_SQL.EXECUTE(l_cursor);
    DBMS_OUTPUT.PUT_LINE('Updated rows=' || l_rows);

    DBMS_SQL.CLOSE_CURSOR(l_cursor);
    COMMIT;
EXCEPTION
    WHEN OTHERS THEN
        IF l_cursor IS NOT NULL
           AND DBMS_SQL.IS_OPEN(l_cursor)
        THEN
            DBMS_SQL.CLOSE_CURSOR(l_cursor);
        END IF;
        ROLLBACK;
        RAISE;
END;
/
~~~

If the bind count varies, the binding section can sit inside a metadata loop. Successful DML does not imply auto-`COMMIT`; transaction control remains with the caller or procedure per the designed contract.

## 9. DML with RETURNING and output binds

`DBMS_SQL` can bind output variables for certain statements with `OUT`/`IN OUT` binds. After executing, use `VARIABLE_VALUE` to retrieve the output value by bound placeholder name. For string outputs, pick the matching overload and buffer size.

Conceptual example:

~~~sql
DECLARE
    l_cursor INTEGER;
    l_id     NUMBER;
    l_rows   INTEGER;
BEGIN
    l_cursor := DBMS_SQL.OPEN_CURSOR;

    DBMS_SQL.PARSE(
        l_cursor,
        'BEGIN :out_id := 100; END;',
        DBMS_SQL.NATIVE
    );

    DBMS_SQL.BIND_VARIABLE(
        l_cursor,
        ':out_id',
        l_id
    );

    l_rows := DBMS_SQL.EXECUTE(l_cursor);

    DBMS_SQL.VARIABLE_VALUE(
        l_cursor,
        ':out_id',
        l_id
    );

    DBMS_OUTPUT.PUT_LINE('Output id=' || l_id);
    DBMS_SQL.CLOSE_CURSOR(l_cursor);
END;
/
~~~

This example illustrates `OUT` binding for an anonymous PL/SQL block. With DML `RETURNING INTO`, dynamic SQL syntax and bind declarations must follow the specific statement form; never assume every placeholder is `IN`. Check package documentation for `OUT`/`IN OUT` overloads and limits of the data types you use.

## 10. Converting between DBMS_SQL and SYS_REFCURSOR

Sometimes one layer needs `DBMS_SQL` to describe dynamic columns, while another layer wants a `SYS_REFCURSOR` to fetch via NDS APIs. Oracle provides:

- `DBMS_SQL.TO_REFCURSOR`: converts an open cursor number into a `SYS_REFCURSOR`.
- `DBMS_SQL.TO_CURSOR_NUMBER`: converts a `SYS_REFCURSOR` into a `DBMS_SQL` cursor number.

Example converting a cursor after parse/prepare:

~~~sql
DECLARE
    l_cursor INTEGER;
    l_refcur SYS_REFCURSOR;
BEGIN
    l_cursor := DBMS_SQL.OPEN_CURSOR;
    DBMS_SQL.PARSE(
        l_cursor,
        'SELECT employee_id, last_name FROM employees',
        DBMS_SQL.NATIVE
    );

    l_refcur := DBMS_SQL.TO_REFCURSOR(l_cursor);
    -- Cursor ownership has transferred to l_refcur.
    -- Fetch via SYS_REFCURSOR in the receiving layer.
    CLOSE l_refcur;
END;
/
~~~

After `TO_REFCURSOR`, do not keep using the old cursor number as if `DBMS_SQL` still owned the cursor. The cursor must be closed through the ref cursor. Conversion helps bridge APIs, but does not eliminate the need to know how to consume result metadata.

## 11. Safe cursor and exception handling

`DBMS_SQL` is a lower-level API than NDS and requires careful cursor lifecycle management.

### 11.1 Always close the cursor on both success and error paths

Basic pattern:

~~~sql
DECLARE
    l_cursor INTEGER;
BEGIN
    l_cursor := DBMS_SQL.OPEN_CURSOR;

    -- PARSE, BIND, DEFINE, EXECUTE, FETCH...

    DBMS_SQL.CLOSE_CURSOR(l_cursor);
EXCEPTION
    WHEN OTHERS THEN
        IF l_cursor IS NOT NULL
           AND DBMS_SQL.IS_OPEN(l_cursor)
        THEN
            DBMS_SQL.CLOSE_CURSOR(l_cursor);
        END IF;
        RAISE;
END;
/
~~~

`IS_OPEN` lets you check whether the cursor is still open before closing inside the exception handler. Do not swallow the original error just because closing the cursor hits a secondary error; in production systems, log any cleanup error while preserving the primary exception.

### 11.2 Do not reuse a cursor number after closing

After `CLOSE_CURSOR`, the handle is invalid. Open a new cursor via `OPEN_CURSOR` if you need to execute another statement.

### 11.3 Do not hold cursors open longer than needed

Close as soon as fetching finishes. If results must be returned to a calling layer, consider returning a `SYS_REFCURSOR` or converting with `TO_REFCURSOR` under clearly defined ownership.

### 11.4 Controlling parse and bind errors

Errors that can occur:

- Invalid SQL syntax.
- Non-existent object or column.
- Missing bind variable.
- Mismatched bind name.
- Incompatible bind type.
- Result type unsupported by dispatch code.
- Insufficient object access privileges.

Report the SQL error code, column/bind position, and failing step clearly, without writing entire SQL texts or sensitive bind values into logs.

## 12. DBMS_SQL and security

Dynamic SQL carries SQL injection risk if an application concatenates untrusted data into SQL text.

Rules:

1. Bind all data values.
2. Permit identifiers only from a controlled allowlist.
3. Use `DBMS_ASSERT` appropriately to validate identifiers when needed.
4. Never let users supply arbitrary SQL statements unless the feature is explicitly designed as a SQL console.
5. Limit schema execution privileges; never run dynamic SQL under overly broad privileges.
6. Log request IDs and normalized statements per policy, avoiding data exposure.
7. Enforce row limits, runtime limits, and resource controls on user-configurable queries.

`DBMS_SQL` is a dynamic SQL execution tool—it does not make SQL safe automatically. `BIND_VARIABLE` protects values at bind positions; it does not protect identifiers concatenated into SQL.

## 13. Limitations of DBMS_SQL and when not to use it

### 13.1 No generic auto-discovery of bind metadata

`DBMS_SQL` describes output columns, not a public generic API describing all bind placeholders of arbitrary SQL. Design your SQL builder to emit bind metadata alongside SQL.

### 13.2 Do not use DBMS_SQL just to avoid declaring variables

If the SQL statement is fixed and column counts are known upfront, `EXECUTE IMMEDIATE` is usually simpler. `DBMS_SQL` adds considerable cursor management, define, and fetch boilerplate.

### 13.3 Special data types require dedicated handling

LOBs, `LONG`, object types, collections, `REF`, timezone-aware timestamps, and extended types require the right overloads/APIs. Never assume the `VARCHAR2`/`NUMBER`/`DATE` example is a universal parser.

### 13.4 SQL text size limits

Statement length limits depend on the overload and Oracle version. If a SQL statement exceeds the `VARCHAR2` limit of your interface, check `CLOB`/array overloads in `DBMS_SQL` for that version. Never arbitrarily split a SQL string into fragments and parse each fragment as an independent statement.

### 13.5 Successful PARSE does not guarantee execution succeeds

`PARSE` validates syntax and prepares the statement, yet privilege errors, bind errors, constraint violations, data issues, and runtime errors can still occur during execute/fetch.

## 14. Metadata-driven SQL builder

For applications needing variable bind counts, build a layer that emits SQL and metadata together instead of trying to parse SQL text after generation.

Conceptual contract example:

| Metadata field | Example | Purpose |
|---|---|---|
| SQL text | `SELECT ... WHERE status = :p1 AND created_at >= :p2` | Statement to execute |
| Bind name | `:p1` | Placeholder in SQL |
| Data type | `VARCHAR2` | Select bind overload |
| Value | `OPEN` | Data value |
| Direction | `IN` | `IN`, `OUT`, or `IN OUT` if supported by API |
| Size | `30` | Buffer size for types requiring length |

Flow:

~~~text
UI / API request
       |
       v
SQL builder
       |
       +----> SQL text
       |
       +----> bind metadata collection
                     |
                     v
                DBMS_SQL
                     |
                     v
             Parse / bind / execute
                     |
                     v
             Describe result columns
                     |
                     v
             Define / fetch / map result
~~~

Metadata must be generated from controlled query structures. Never accept an untrusted SQL string alongside an arbitrary bind list and assume it is safe.

## 15. Lab: SELECT with varying column counts

Run the lab in a practice schema. The examples use `USER_TABLES` to demonstrate three common data types and runtime metadata.

### 15.1 Preparation

~~~sql
SET SERVEROUTPUT ON
~~~

Run the block in Section 4. Try changing the `SELECT` to:

~~~sql
SELECT table_name
FROM user_tables;
~~~

and:

~~~sql
SELECT table_name,
       num_rows,
       last_analyzed
FROM user_tables;
~~~

The column count changes from one to three, yet the `DBMS_SQL` code retrieves the column count via `DESCRIBE_COLUMNS2`.

### 15.2 Test an unsupported type

Add a column with a type not covered in the `CASE` statement, such as a timestamp expression:

~~~sql
SELECT table_name,
       CAST(last_analyzed AS TIMESTAMP) AS analyzed_ts
FROM user_tables;
~~~

The illustrative code reports an unsupported type code for the `TIMESTAMP` column. This is intentional: add `DEFINE_COLUMN` and `COLUMN_VALUE` branches for `TIMESTAMP` before supporting that type.

### 15.3 Test DML with binds

Use a lab table you created or a dedicated test table. Parse an `UPDATE` with two placeholders, bind two values, and inspect the row count returned by `DBMS_SQL.EXECUTE`. Never use production tables or modify real business data in the lab.

### 15.4 Verify cursor closing on errors

Intentionally pass invalid SQL syntax or omit a bind to trigger an exception. Verify that the exception handler closes the cursor before re-raising. Do not remove the handler for repeated tests in a session, as doing so can leave open cursors behind.

## 16. Common errors

| Error | Cause | Resolution |
|---|---|---|
| Using `EXECUTE IMMEDIATE` for variable column counts | `INTO` list must match result structure | Use `DBMS_SQL` to describe/define/fetch |
| Calling `DESCRIBE_COLUMNS` before `PARSE` | Cursor has no parsed statement yet | `PARSE` the `SELECT` first |
| Skipping `DEFINE_COLUMN` | Target variables not declared before fetch | Define each column per metadata |
| Using the wrong `DEFINE_COLUMN` overload | Variable type incompatible with SQL type | Dispatch by `COL_TYPE` |
| Calling `COLUMN_VALUE` before `FETCH_ROWS` | No current row fetched yet | `FETCH_ROWS` first, then `COLUMN_VALUE` |
| Treating `EXECUTE` return as `SELECT` row count | `SELECT` rows are retrieved via `FETCH_ROWS` | Use `FETCH_ROWS` to fetch |
| Missing bind variable | Not all placeholders bound | Emit bind metadata and bind all |
| Trying to describe binds with `DESCRIBE_COLUMNS` | This API describes output columns only | Caller supplies bind metadata |
| Concatenating values into SQL | SQL injection and hard parsing | Use `BIND_VARIABLE` |
| Using binds for table/column names | Binds only substitute values | Allowlist and validate identifiers |
| Not closing cursor | Session resource leak | `CLOSE_CURSOR` on both success and error paths |
| Converting all types to `VARCHAR2` | Loss of precision/formatting or no LOB support | Use proper types and overloads |
| Using `COL_MAX_LEN` as buffer size for all variables | Does not fit all types/charsets/LOBs | Handle per data type |
| Parsing binds with a simple regex | Confuses strings/comments/identifiers | SQL builder emits metadata alongside SQL |

## 17. Deployment checklist

Before using `DBMS_SQL` in an application, verify:

1. Why can NDS not handle the runtime structure?
2. Is the SQL statement a `SELECT` or a DML/PLSQL block?
3. If `SELECT`, does code call `DESCRIBE_COLUMNS` after `PARSE`?
4. Does it dispatch `DEFINE_COLUMN` by `COL_TYPE`?
5. Are supported data types bounded and documented?
6. Are `NULL`, LOBs, `LONG`, and special types handled appropriately?
7. Do bind counts, names, types, and values come from trusted metadata?
8. Are all data values bound rather than concatenated?
9. Do dynamic identifiers have proper allowlist/`DBMS_ASSERT` validation?
10. Is `EXECUTE` distinguished from `FETCH_ROWS` for `SELECT`?
11. Is the cursor closed on both success and exception paths?
12. Are SQL text length, row count, execution time, and privileges bounded?
13. Do error logs capture enough detail to investigate without leaking sensitive bind values?
14. If passing a cursor to another layer, are ownership and closing responsibilities clear?
15. Are varying column types, column counts, bind counts, and runtime errors tested?

## 18. Summary

`DBMS_SQL` is the PL/SQL API for dynamic SQL scenarios requiring cursor-level operations when statement structure is known only at runtime.

- `OPEN_CURSOR` opens a cursor number; `PARSE` parses the statement.
- `DESCRIBE_COLUMNS`/`DESCRIBE_COLUMNS2` describes result column count and metadata.
- `DEFINE_COLUMN` declares a target variable for each column by data type.
- `EXECUTE` runs the statement; `SELECT` requires `FETCH_ROWS` to retrieve each row.
- `COLUMN_VALUE` retrieves column values by position and defined variable type.
- `BIND_VARIABLE` binds values by placeholder; it can iterate in a loop when the caller supplies bind metadata.
- `DBMS_SQL` has no generic API to auto-describe every bind placeholder and expected type in arbitrary SQL.
- Bind values cannot replace identifiers; dynamic table/column names must be controlled separately.
- Cursors must be closed on all execution paths, including exceptions.

When column and bind counts are known upfront, prefer Native Dynamic SQL for cleaner code. When an application truly needs to handle runtime-varying result metadata or bind lists, `DBMS_SQL` provides explicit steps to parse, describe, define, bind, execute, and fetch in a controlled manner.
