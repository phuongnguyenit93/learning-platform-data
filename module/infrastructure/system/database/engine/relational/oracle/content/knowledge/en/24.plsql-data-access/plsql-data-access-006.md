# REF CURSOR, SYS_REFCURSOR, and Returning Result Sets to Applications

A PL/SQL procedure can return data to an application as a **result set** rather than returning only a single scalar value or writing data into a staging table. Oracle commonly uses `REF CURSOR` for this purpose. A `REF CURSOR` is a cursor variable pointing to the work area of an open query; the application receives the cursor, reads each row, and closes it when finished.

In PL/SQL, a `REF CURSOR` can be strongly typed (strong) or weakly typed (weak). Oracle provides a built-in weak `REF CURSOR` type named `SYS_REFCURSOR`, which is very commonly used as an `OUT` parameter of a procedure. The application calls the procedure through a driver, obtains the returned cursor, and fetches rows like a `ResultSet` or data reader.

This lesson covers:

- How `REF CURSOR` differs from explicit cursors and collections.
- Strong `REF CURSOR`, weak `REF CURSOR`, and `SYS_REFCURSOR`.
- How to `OPEN`, `FETCH`, `CLOSE`, and manage the cursor lifecycle.
- Returning one or multiple result sets via `OUT` parameters.
- Calling procedures from SQL*Plus/SQLcl and JDBC applications.
- Using bind variables when opening cursors with dynamic SQL.
- Issues around `NULL`, transactions, privileges, resources, and performance.

The examples use Oracle Database 19c and standard PL/SQL syntax. Some client APIs depend on the driver version; always verify against the documentation for the driver you deploy.

## 1. What is a REF CURSOR?

When a `SELECT` statement is opened, Oracle creates a cursor attached to the SQL statement's work area. A `REF CURSOR` is a PL/SQL variable holding a reference to that cursor. You can pass this variable via procedure/function parameters so the caller can read the results.

~~~text
Application
    |
    | CALL procedure
    v
PL/SQL procedure
    |
    | OPEN ref_cursor FOR SELECT ...
    v
Oracle SQL cursor / result set
    |
    | OUT SYS_REFCURSOR
    v
Application receives cursor handle
    |
    | FETCH rows
    v
Application processes each row
    |
    | CLOSE result set
    v
Cursor resources released
~~~

A `REF CURSOR` is not a materialized copy of data stored in a collection. It is a handle to an open cursor in the database session. The application reads rows over the driver protocol; the data is not necessarily loaded completely into client memory the moment the procedure returns.

### 1.1. When is REF CURSOR commonly used?

- A procedure needs to return multiple rows to Java, .NET, Python, or another application.
- An API needs to encapsulate query logic inside PL/SQL.
- Multiple result sets need to be returned in a single call.
- A cursor needs to be opened on one of several `SELECT` statements depending on input parameters.
- A cursor needs to be passed between PL/SQL procedures or functions.

If only a single value is needed, use a scalar `OUT` parameter. If a small dataset already processed inside PL/SQL is needed, a collection may fit. `REF CURSOR` fits when the caller needs to consume a cursor-style result set.

## 2. Explicit cursors vs. REF CURSOR

Both allow row-by-row data fetching, but they differ in how the query is defined.

### 2.1. Explicit cursor

An explicit cursor is bound to a fixed `SELECT` statement in the PL/SQL declarative section:

~~~sql
DECLARE
    CURSOR c_customers IS
        SELECT customer_id, customer_name
        FROM customers
        WHERE status = 'ACTIVE'
        ORDER BY customer_id;

    v_id   customers.customer_id%TYPE;
    v_name customers.customer_name%TYPE;
BEGIN
    OPEN c_customers;

    LOOP
        FETCH c_customers INTO v_id, v_name;
        EXIT WHEN c_customers%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(v_id || ': ' || v_name);
    END LOOP;

    CLOSE c_customers;
END;
/
~~~

The query is fixed in the cursor declaration. You can use cursor parameters to pass filter values, but you cannot swap the query text of an explicit cursor after compilation.

### 2.2. REF CURSOR

A `REF CURSOR` is a cursor variable. The `SELECT` statement is bound to the variable at runtime using `OPEN ... FOR`:

~~~sql
DECLARE
    TYPE t_customer_cursor IS REF CURSOR;
    v_cursor t_customer_cursor;
    v_id     customers.customer_id%TYPE;
    v_name   customers.customer_name%TYPE;
BEGIN
    OPEN v_cursor FOR
        SELECT customer_id, customer_name
        FROM customers
        WHERE status = 'ACTIVE'
        ORDER BY customer_id;

    LOOP
        FETCH v_cursor INTO v_id, v_name;
        EXIT WHEN v_cursor%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(v_id || ': ' || v_name);
    END LOOP;

    CLOSE v_cursor;
END;
/
~~~

The key difference is that a `REF CURSOR` can be opened with different `SELECT` statements based on runtime logic, and can be passed through parameters or returned to a caller.

### 2.3. Quick comparison

| Criterion | Explicit cursor | REF CURSOR |
| --- | --- | --- |
| Query | Fixed in declaration | Bound at runtime via `OPEN FOR` |
| Variable kind | Declared cursor | Cursor variable |
| Passing as parameter | Can pass cursor parameters in PL/SQL with matching declarations | Primary intended use case |
| Returning result set to client | Not as convenient as an `OUT` cursor API | Very well suited |
| Changing query at runtime | Limited | Can choose query or use dynamic SQL |
| Fetch/close | `OPEN`, `FETCH`, `CLOSE` | `OPEN FOR`, `FETCH`, `CLOSE` |

## 3. Strong REF CURSOR and weak REF CURSOR

When declaring a `REF CURSOR` type, you can specify the row type returned by the cursor or omit the row type.

### 3.1. Strong REF CURSOR

A strong `REF CURSOR` has a `RETURN` clause describing the row type:

~~~sql
DECLARE
    TYPE t_customer_cursor IS REF CURSOR
        RETURN customers%ROWTYPE;

    v_cursor t_customer_cursor;
    v_customer customers%ROWTYPE;
BEGIN
    OPEN v_cursor FOR
        SELECT *
        FROM customers
        WHERE customer_id = 101;

    FETCH v_cursor INTO v_customer;
    CLOSE v_cursor;
END;
/
~~~

The query used in `OPEN` must return a row shape compatible with the declared `RETURN` type. Strong cursors help catch row-type mismatches early at compile time or cursor open time according to PL/SQL rules.

You can define a custom row type if the API only returns a subset of columns:

~~~sql
DECLARE
    TYPE t_customer_row IS RECORD (
        customer_id   customers.customer_id%TYPE,
        customer_name customers.customer_name%TYPE
    );

    TYPE t_customer_cursor IS REF CURSOR
        RETURN t_customer_row;

    v_cursor t_customer_cursor;
    v_row    t_customer_row;
BEGIN
    OPEN v_cursor FOR
        SELECT customer_id, customer_name
        FROM customers
        WHERE status = 'ACTIVE';

    FETCH v_cursor INTO v_row;
    CLOSE v_cursor;
END;
/
~~~

Strong cursors are suitable when the result set structure is a fixed part of the PL/SQL contract and you want compiler type checking.

### 3.2. Weak REF CURSOR

A weak `REF CURSOR` has no `RETURN` clause:

~~~sql
DECLARE
    TYPE t_any_cursor IS REF CURSOR;
    v_cursor t_any_cursor;
BEGIN
    OPEN v_cursor FOR
        SELECT customer_id, customer_name
        FROM customers;
    CLOSE v_cursor;
END;
/
~~~

Because it does not constrain the row shape in its declaration, a weak cursor can open queries returning different column structures. The caller must still fetch matching the exact column count, order, and types of the currently open query; weak does not mean schemaless data.

### 3.3. SYS_REFCURSOR

Oracle provides `SYS_REFCURSOR` as a standard built-in weak `REF CURSOR` type. You do not need to declare your own type when using it:

~~~sql
DECLARE
    v_result SYS_REFCURSOR;
BEGIN
    OPEN v_result FOR
        SELECT customer_id, customer_name
        FROM customers;

    CLOSE v_result;
END;
/
~~~

`SYS_REFCURSOR` is especially convenient in public procedure APIs:

~~~sql
CREATE OR REPLACE PROCEDURE get_customers (
    p_result OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_result FOR
        SELECT customer_id, customer_name
        FROM customers
        ORDER BY customer_id;
END;
/
~~~

`SYS_REFCURSOR` is commonly used when clients need a flexible result set. If the contract requires a fixed row type and stronger type checking inside PL/SQL, declare a strong `REF CURSOR` type in a package specification.

## 4. Lifecycle: OPEN, FETCH, and CLOSE

A `REF CURSOR` is used in three steps:

1. `OPEN FOR`: bind a query to the cursor variable and open the cursor.
2. `FETCH`: retrieve one or more rows from the result set.
3. `CLOSE`: release the cursor once reading is no longer needed.

### 4.1. OPEN FOR

~~~sql
OPEN v_cursor FOR
    SELECT customer_id, customer_name
    FROM customers
    WHERE status = 'ACTIVE';
~~~

After `OPEN`, the cursor is open and ready to fetch. An already open cursor variable should not be reopened as if it had no query; `CLOSE` it before reusing.

### 4.2. Row-by-row FETCH

~~~sql
FETCH v_cursor INTO v_id, v_name;
EXIT WHEN v_cursor%NOTFOUND;
~~~

`FETCH` assigns the columns of the next row into the target variables in order. Variable count and data types must be compatible with the select list. If there is no next row, `%NOTFOUND` becomes `TRUE`.

### 4.3. Cursor attributes

Commonly used attributes on a cursor variable:

| Attribute | Meaning |
| --- | --- |
| `%ISOPEN` | `TRUE` if the cursor is open |
| `%FOUND` | `TRUE` if the most recent `FETCH` retrieved a row; `NULL` before the first fetch |
| `%NOTFOUND` | `TRUE` if the most recent `FETCH` retrieved no row; `NULL` before the first fetch |
| `%ROWCOUNT` | Number of rows successfully fetched |

Example:

~~~sql
LOOP
    FETCH v_cursor INTO v_id, v_name;
    EXIT WHEN v_cursor%NOTFOUND;

    DBMS_OUTPUT.PUT_LINE('Fetched rows: ' || v_cursor%ROWCOUNT);
END LOOP;
~~~

Check `%NOTFOUND` right after `FETCH`. Checking it before the first `FETCH` sees `NULL` and will not exit the loop as intended.

### 4.4. CLOSE

~~~sql
IF v_cursor%ISOPEN THEN
    CLOSE v_cursor;
END IF;
~~~

Closing the cursor releases the cursor handle and associated resources. Do not leave cursors open longer than necessary.

### 4.5. Exception handling to always close the cursor

~~~sql
DECLARE
    TYPE t_cursor IS REF CURSOR;
    v_cursor t_cursor;
    v_id NUMBER;
BEGIN
    OPEN v_cursor FOR
        SELECT customer_id
        FROM customers;

    LOOP
        FETCH v_cursor INTO v_id;
        EXIT WHEN v_cursor%NOTFOUND;
        DBMS_OUTPUT.PUT_LINE(v_id);
    END LOOP;

    CLOSE v_cursor;
EXCEPTION
    WHEN OTHERS THEN
        IF v_cursor%ISOPEN THEN
            CLOSE v_cursor;
        END IF;
        RAISE;
END;
/
~~~

When writing a procedure that returns a cursor to a client, do not close the cursor before the procedure exits. The client needs the cursor still open to fetch; ownership of reading and closing transfers to the caller once it receives the `OUT` parameter.

## 5. Returning SYS_REFCURSOR via an OUT parameter

This is the most common API pattern. The procedure opens the cursor and assigns the handle to an `OUT` parameter.

### 5.1. Creating a procedure that returns a customer list

~~~sql
CREATE OR REPLACE PROCEDURE get_active_customers (
    p_min_credit IN NUMBER,
    p_result     OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_result FOR
        SELECT
            customer_id,
            customer_name,
            credit_limit
        FROM customers
        WHERE status = 'ACTIVE'
          AND credit_limit >= p_min_credit
        ORDER BY customer_id;
END;
/
~~~

The procedure does not fetch rows into PL/SQL variables. It only opens the cursor and returns the cursor handle. The client reads the data.

### 5.2. Calling from SQL*Plus or SQLcl

Clients that support `REFCURSOR` bind variables can invoke:

~~~sql
VARIABLE rc REFCURSOR
EXEC get_active_customers(500, :rc);
PRINT rc
~~~

`VARIABLE`, `EXEC`, and `PRINT` are SQL*Plus/SQLcl commands, not pure SQL syntax runnable across every driver. In applications, use the driver's API to bind the `OUT` parameter.

### 5.3. Calling the procedure from other PL/SQL

A PL/SQL caller can receive the cursor into a `REF CURSOR` variable and fetch:

~~~sql
DECLARE
    v_result SYS_REFCURSOR;
    v_id     customers.customer_id%TYPE;
    v_name   customers.customer_name%TYPE;
    v_limit  customers.credit_limit%TYPE;
BEGIN
    get_active_customers(
        p_min_credit => 500,
        p_result     => v_result
    );

    LOOP
        FETCH v_result INTO v_id, v_name, v_limit;
        EXIT WHEN v_result%NOTFOUND;

        DBMS_OUTPUT.PUT_LINE(v_id || ' - ' || v_name || ' - ' || v_limit);
    END LOOP;

    CLOSE v_result;
END;
/
~~~

The caller must know the shape of the result set to declare matching `FETCH` variables. If the procedure changes the select list while the caller still expects the old structure, the caller can fail on fetch or require a contract update.

## 6. Returning a cursor from a function

A function can also return a `REF CURSOR`. The function creates a local cursor, executes `OPEN FOR` on the query, and returns the cursor variable:

~~~sql
CREATE OR REPLACE FUNCTION open_active_customers (
    p_min_credit IN NUMBER
) RETURN SYS_REFCURSOR
AS
    v_result SYS_REFCURSOR;
BEGIN
    OPEN v_result FOR
        SELECT customer_id, customer_name, credit_limit
        FROM customers
        WHERE status = 'ACTIVE'
          AND credit_limit >= p_min_credit
        ORDER BY customer_id;

    RETURN v_result;
END;
/
~~~

PL/SQL caller:

~~~sql
DECLARE
    v_result SYS_REFCURSOR;
    v_id NUMBER;
    v_name VARCHAR2(100);
    v_limit NUMBER;
BEGIN
    v_result := open_active_customers(500);

    LOOP
        FETCH v_result INTO v_id, v_name, v_limit;
        EXIT WHEN v_result%NOTFOUND;
        DBMS_OUTPUT.PUT_LINE(v_name);
    END LOOP;

    CLOSE v_result;
END;
/
~~~

Procedures with `OUT` cursors are often easier for stored-procedure calls from applications and can return multiple cursors. Functions returning a cursor fit when the API is designed as a function returning a single handle. In both cases, the caller is responsible for reading and closing the cursor.

## 7. Strong REF CURSOR in package APIs

If you want a public API with an explicit row-type contract, declare the `REF CURSOR` type in the package specification:

~~~sql
CREATE OR REPLACE PACKAGE customer_api AS
    TYPE t_customer_result IS REF CURSOR
        RETURN customers%ROWTYPE;

    PROCEDURE open_customer (
        p_customer_id IN customers.customer_id%TYPE,
        p_result      OUT t_customer_result
    );
END customer_api;
/
~~~

Package body:

~~~sql
CREATE OR REPLACE PACKAGE BODY customer_api AS
    PROCEDURE open_customer (
        p_customer_id IN customers.customer_id%TYPE,
        p_result      OUT t_customer_result
    ) AS
    BEGIN
        OPEN p_result FOR
            SELECT *
            FROM customers
            WHERE customer_id = p_customer_id;
    END open_customer;
END customer_api;
/
~~~

The caller can fetch into a `%ROWTYPE` record:

~~~sql
DECLARE
    v_result customer_api.t_customer_result;
    v_customer customers%ROWTYPE;
BEGIN
    customer_api.open_customer(101, v_result);
    FETCH v_result INTO v_customer;

    IF v_result%FOUND THEN
        DBMS_OUTPUT.PUT_LINE(v_customer.customer_name);
    END IF;

    CLOSE v_result;
END;
/
~~~

Strong typing clearly defines the row shape, though it also means table structure changes become contract changes. For long-lived stable APIs, define an explicit `RECORD` type instead of returning the full `%ROWTYPE`, so internal columns added to the table are not accidentally exposed.

## 8. Returning multiple result sets

A procedure can return multiple `SYS_REFCURSOR` values via multiple `OUT` parameters. Each cursor is an independent result set.

~~~sql
CREATE OR REPLACE PROCEDURE get_customer_dashboard (
    p_customer_id IN NUMBER,
    p_orders      OUT SYS_REFCURSOR,
    p_summary     OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_orders FOR
        SELECT order_id, order_date, order_status, total_amount
        FROM orders
        WHERE customer_id = p_customer_id
        ORDER BY order_date DESC;

    OPEN p_summary FOR
        SELECT
            COUNT(*) AS order_count,
            NVL(SUM(total_amount), 0) AS total_amount
        FROM orders
        WHERE customer_id = p_customer_id;
END;
/
~~~

The client binds both `OUT` parameters, receives both cursors, and reads each result set. Even if one cursor is not needed, the client must still close it to release resources.

### 8.1. Implicit results

Oracle 12c and later also support returning implicit result sets via `DBMS_SQL.RETURN_RESULT` for supporting clients. This avoids declaring multiple `OUT` cursor parameters, though consumption support depends on the driver/client. For APIs needing clear compatibility across diverse clients, `OUT SYS_REFCURSOR` is usually easier to recognize and control.

Do not mix implicit results and `OUT` cursors arbitrarily. Clearly define the count, order, column schemas, and how the client consumes each result set.

## 9. Dynamic SQL and REF CURSOR

Sometimes a procedure needs to pick one of several queries based on parameters. You can open a weak cursor with dynamic SQL:

~~~sql
CREATE OR REPLACE PROCEDURE search_customers (
    p_region IN VARCHAR2,
    p_result OUT SYS_REFCURSOR
) AS
    l_sql VARCHAR2(4000);
BEGIN
    l_sql :=
        'SELECT customer_id, customer_name, region_code ' ||
        'FROM customers WHERE region_code = :region ' ||
        'ORDER BY customer_id';

    OPEN p_result FOR l_sql USING p_region;
END;
/
~~~

The value of `p_region` is passed through a bind variable. Never concatenate user input directly into SQL strings.

### 9.1. Choosing a query conditionally

~~~sql
CREATE OR REPLACE PROCEDURE open_customer_search (
    p_mode   IN VARCHAR2,
    p_value  IN VARCHAR2,
    p_result OUT SYS_REFCURSOR
) AS
BEGIN
    IF p_mode = 'NAME' THEN
        OPEN p_result FOR
            SELECT customer_id, customer_name
            FROM customers
            WHERE customer_name LIKE p_value
            ORDER BY customer_name;
    ELSIF p_mode = 'REGION' THEN
        OPEN p_result FOR
            SELECT customer_id, customer_name
            FROM customers
            WHERE region_code = p_value
            ORDER BY customer_id;
    ELSE
        RAISE_APPLICATION_ERROR(-20001, 'Unsupported search mode');
    END IF;
END;
/
~~~

Both queries share the same column count and compatible types so the caller fetches against a single contract. If different modes return different shapes, callers need separate APIs or result sets; do not force clients to guess schema from data.

### 9.2. Bind values, whitelist identifiers

Bind variables are for data values, not table names, column names, or SQL keywords. If choosing a sort column dynamically is unavoidable:

- Use a whitelist mapping mode values to fixed column names.
- Never concatenate raw strings sent by the client.
- Bind filter values.
- You may use `DBMS_ASSERT` for certain identifiers when designed appropriately, but `DBMS_ASSERT` does not replace whitelisting and authorization.

Example:

~~~sql
IF p_sort = 'NAME' THEN
    l_order_by := 'customer_name';
ELSIF p_sort = 'DATE' THEN
    l_order_by := 'created_at';
ELSE
    RAISE_APPLICATION_ERROR(-20002, 'Invalid sort option');
END IF;
~~~

Only controlled identifiers may be appended into query text. All other input data should be passed via `USING`.

## 10. Fetching data in PL/SQL

### 10.1. Row-by-row fetch

~~~sql
DECLARE
    v_result SYS_REFCURSOR;
    v_id NUMBER;
    v_name VARCHAR2(100);
BEGIN
    OPEN v_result FOR
        SELECT customer_id, customer_name
        FROM customers
        ORDER BY customer_id;

    LOOP
        FETCH v_result INTO v_id, v_name;
        EXIT WHEN v_result%NOTFOUND;
        DBMS_OUTPUT.PUT_LINE(v_id || ': ' || v_name);
    END LOOP;

    CLOSE v_result;
END;
/
~~~

This is easy to understand, but for large row counts, row-by-row processing in PL/SQL incurs context-switching overhead between the SQL engine and the PL/SQL engine.

### 10.2. BULK COLLECT

You can fetch multiple rows into a collection:

~~~sql
DECLARE
    TYPE t_customer_rows IS TABLE OF customers%ROWTYPE;
    v_rows t_customer_rows;
    v_result SYS_REFCURSOR;
BEGIN
    OPEN v_result FOR
        SELECT *
        FROM customers
        ORDER BY customer_id;

    LOOP
        FETCH v_result BULK COLLECT INTO v_rows LIMIT 100;
        EXIT WHEN v_rows.COUNT = 0;

        FOR i IN 1 .. v_rows.COUNT LOOP
            DBMS_OUTPUT.PUT_LINE(v_rows(i).customer_id);
        END LOOP;
    END LOOP;

    CLOSE v_result;
END;
/
~~~

`LIMIT 100` caps the number of rows loaded into the collection per fetch, avoiding holding an entire large result set in PGA memory. Choose the batch size based on row width, memory, and measured performance.

### 10.3. Do not fetch the wrong column count or order

A weak `REF CURSOR` allows opening flexible queries, but `FETCH INTO` still requires target variables matching the select list. If the query returns three columns while the caller declares only two variables, or if order/data types do not match, the fetch will fail.

To keep APIs stable:

- List columns explicitly; avoid `SELECT *` in public result contracts.
- Keep column order and types stable.
- Version the API if a result schema change breaks callers.
- Document nullability and the meaning of each column.

## 11. Receiving REF CURSOR in Java applications

The Oracle JDBC driver represents a `REF CURSOR` as a result set. A common calling pattern binds the `OUT` parameter with the cursor type, executes the procedure, and retrieves the `ResultSet`.

~~~java
import java.math.BigDecimal;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.ResultSet;
import oracle.jdbc.OracleTypes;

String call = "{call get_active_customers(?, ?)}";

try (CallableStatement stmt = connection.prepareCall(call)) {
    stmt.setBigDecimal(1, new BigDecimal("500"));
    stmt.registerOutParameter(2, OracleTypes.CURSOR);
    stmt.execute();

    try (ResultSet rs = (ResultSet) stmt.getObject(2)) {
        while (rs.next()) {
            long customerId = rs.getLong("CUSTOMER_ID");
            String customerName = rs.getString("CUSTOMER_NAME");
            BigDecimal creditLimit = rs.getBigDecimal("CREDIT_LIMIT");

            System.out.println(
                customerId + " " + customerName + " " + creditLimit
            );
        }
    }
}
~~~

This example uses the Oracle JDBC extension `OracleTypes.CURSOR`. Depending on the driver/JDBC API version, standard `Types.REF_CURSOR` may be supported; verify compatibility with the driver packaged in your application.

### 11.1. Java-side resource management rules

- Keep the `Connection` open while the `ResultSet` is being read.
- Close the `ResultSet` when done, including on error paths.
- Close the `CallableStatement` after reading the cursor.
- When using a connection pool, return the connection to the pool only after related result sets and statements are closed.
- Do not retain a `ResultSet` for use after the connection has been closed or returned to the pool.

Try-with-resources automatically closes `ResultSet` and `CallableStatement`. The `Connection` is typically owned by the transaction/pool management layer; do not close the connection here if the caller still needs it.

### 11.2. Handling NULL in JDBC

`ResultSet.getLong()` returns `0` when the SQL column is `NULL`; call `wasNull()` immediately after the getter to distinguish them:

~~~java
long creditLimitValue = rs.getLong("CREDIT_LIMIT");
boolean creditLimitIsNull = rs.wasNull();
~~~

For reference types such as `String` or `BigDecimal`, getters normally return Java `null` for SQL `NULL`. Never assume `0` represents an actual value if the column is nullable.

## 12. Receiving REF CURSOR in .NET applications

With Oracle Data Provider for .NET (ODP.NET), the `OUT` parameter uses `OracleDbType.RefCursor`. The client obtains an `OracleRefCursor` and creates an `OracleDataReader`:

~~~csharp
using Oracle.ManagedDataAccess.Client;
using System.Data;

using (var cmd = connection.CreateCommand())
{
    cmd.CommandText = "GET_ACTIVE_CUSTOMERS";
    cmd.CommandType = CommandType.StoredProcedure;

    cmd.Parameters.Add(
        "p_min_credit",
        OracleDbType.Decimal
    ).Value = 500m;

    var resultParameter = cmd.Parameters.Add(
        "p_result",
        OracleDbType.RefCursor
    );
    resultParameter.Direction = ParameterDirection.Output;

    cmd.ExecuteNonQuery();

    using (var refCursor = (OracleRefCursor)resultParameter.Value)
    using (var reader = refCursor.GetDataReader())
    {
        while (reader.Read())
        {
            var customerId = reader.GetInt32(0);
            var customerName = reader.GetString(1);
        }
    }
}
~~~

Specific parameter types and APIs can vary between managed/unmanaged ODP.NET and package versions. Use the exact namespace/driver referenced by your application. Keep the connection open until the reader is closed.

## 13. Multiple cursors and resource limits

Every open cursor consumes session/database resources. A procedure returning multiple cursors, or an application opening many result sets without closing them, can increase open cursor counts and trigger `ORA-01000: maximum open cursors exceeded`.

### 13.1. Avoiding cursor leaks

- Close `ResultSet`/`DataReader` on the client.
- Close the statement once reading finishes.
- Never open a new cursor on every loop iteration while forgetting to close the previous one.
- Always release resources on exception paths.
- With connection pools, reset/close all cursors before returning the connection.

Raising the `OPEN_CURSORS` parameter is no substitute for fixing cursor leaks. Inspect code paths and session open-cursor statistics first.

### 13.2. Limiting returned row volume

An API that returns an entire large table can consume excessive time, network bandwidth, and resources. Design:

- Mandatory filters or sensible defaults.
- Pagination using a stable key.
- A maximum row cap if appropriate for the business rule.
- Driver-appropriate fetch size/prefetch settings.
- Indexed sorts or measured execution plans.

`REF CURSOR` does not provide pagination automatically. If the client needs paging, the query must include explicit keyset predicates or a properly designed offset/fetch mechanism.

## 14. Transactions, read consistency, and connection lifecycle

A `REF CURSOR` is opened within a database session. The client must keep the corresponding connection open to continue fetching. If the connection closes, the session ends, or the cursor is closed, the client can no longer read from that cursor handle.

Oracle provides read consistency for queries. An open cursor reads from a consistent snapshot established when the query was opened/executed. If a result set is consumed over a very long period while underlying data changes continuously, Oracle may need undo to reconstruct consistent versions; insufficient undo can cause `ORA-01555: snapshot too old`.

Therefore:

- Never keep a cursor open while waiting on interactive user input.
- Read the result set and close it promptly.
- Use pagination for large datasets when business logic permits.
- Do not commit or roll back arbitrarily mid-read if the application needs consistent transaction semantics.
- Design retry logic if a connection drops; an old cursor cannot be resumed once its session is lost.

## 15. Privileges and security of cursor-returning procedures

Procedures run under definer rights by default unless `AUTHID CURRENT_USER` is declared. When a procedure opens a query, understand the procedure owner, privileges on referenced tables, and execute privileges granted to the application.

Example:

~~~sql
GRANT EXECUTE ON app_owner.get_active_customers TO app_runtime;
~~~

Grant `EXECUTE` only on required APIs and follow least-privilege data access. Do not grant direct table query privileges across an entire schema to the application when APIs are designed to expose specific datasets.

Returned cursors can still expose sensitive data. Restrict columns in `SELECT`, filter by user/tenant, enforce authorization, and audit per policy. Never let clients pass arbitrary table names or raw SQL into dynamic cursor queries.

## 16. Designing the result set contract

`REF CURSOR` is flexible, but flexibility should not make an API unpredictable. A good contract defines:

| Component | What to specify |
| --- | --- |
| Procedure/function name | Stable name and clear purpose |
| Input parameters | Types, meaning of `NULL`, valid values |
| Output cursors | Number of cursors and parameter order |
| Column names | Stable column names, not relying on `SELECT *` |
| Column types | `NUMBER`, `VARCHAR2`, `DATE`, `TIMESTAMP`, etc. |
| Nullability | Which columns may be `NULL` and what it means |
| Ordering | Whether order is guaranteed; if required, specify `ORDER BY` |
| Volume | Estimated row count, pagination, or row limits |
| Error behavior | Which Oracle exceptions may propagate to the client |
| Versioning | How result schema changes without breaking callers |

Without `ORDER BY`, SQL does not guarantee row order. If the client displays or processes rows in order, the procedure must declare `ORDER BY` with deterministic tie-breakers.

## 17. Complete lab: returning result sets to applications

Practice in a lab schema that you own.

### 17.1. Create table and data

~~~sql
CREATE TABLE lab_customers (
    customer_id   NUMBER PRIMARY KEY,
    customer_name VARCHAR2(80) NOT NULL,
    status        VARCHAR2(10) NOT NULL,
    credit_limit  NUMBER(12, 2)
);

INSERT INTO lab_customers VALUES (1, 'An Nguyen', 'ACTIVE', 1200);
INSERT INTO lab_customers VALUES (2, 'Binh Tran', 'ACTIVE', 300);
INSERT INTO lab_customers VALUES (3, 'Chi Le', 'INACTIVE', 900);
INSERT INTO lab_customers VALUES (4, 'Dung Pham', 'ACTIVE', NULL);
COMMIT;
~~~

### 17.2. Create an OUT SYS_REFCURSOR procedure

~~~sql
CREATE OR REPLACE PROCEDURE lab_get_customers (
    p_status      IN VARCHAR2,
    p_min_credit  IN NUMBER,
    p_result      OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_result FOR
        SELECT
            customer_id,
            customer_name,
            status,
            credit_limit
        FROM lab_customers
        WHERE status = p_status
          AND credit_limit >= p_min_credit
        ORDER BY customer_id;
END;
/
~~~

### 17.3. Call with SQL*Plus/SQLcl

~~~sql
VARIABLE rc REFCURSOR
EXEC lab_get_customers('ACTIVE', 500, :rc);
PRINT rc
~~~

The output contains `ACTIVE` customers with credit limit 500 or above. The row with `NULL` `CREDIT_LIMIT` does not satisfy the comparison and does not appear.

### 17.4. Handling optional filter parameters

If `NULL` means skip the corresponding condition, replace the query in the procedure with:

~~~sql
OPEN p_result FOR
    SELECT
        customer_id,
        customer_name,
        status,
        credit_limit
    FROM lab_customers
    WHERE (p_status IS NULL OR status = p_status)
      AND (p_min_credit IS NULL OR credit_limit >= p_min_credit)
    ORDER BY customer_id;
~~~

When `p_status` is `NULL`, the query does not filter by status. When `p_min_credit` is `NULL`, the query does not filter by credit limit. This is a specific API convention; if you also need to search for rows where a column is actually `NULL`, add a separate parameter or flag to distinguish skipping the filter from filtering for `NULL`.

### 17.5. Returning two cursors

~~~sql
CREATE OR REPLACE PROCEDURE lab_customer_dashboard (
    p_customer_id IN NUMBER,
    p_profile     OUT SYS_REFCURSOR,
    p_orders      OUT SYS_REFCURSOR
) AS
BEGIN
    OPEN p_profile FOR
        SELECT customer_id, customer_name, status, credit_limit
        FROM lab_customers
        WHERE customer_id = p_customer_id;

    OPEN p_orders FOR
        SELECT order_id, order_date, total_amount
        FROM lab_orders
        WHERE customer_id = p_customer_id
        ORDER BY order_date DESC;
END;
/
~~~

This example illustrates a multi-cursor structure; create `LAB_ORDERS` with the matching columns before compiling the procedure. The application binds both `OUT` cursors and reads/closes both.

## 18. Common errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Client receives cursor but fetch fails | Fetch target mismatches column count/order/type | Keep result schema clear and fetch matching types |
| `SYS_REFCURSOR` compiles but caller does not know shape | Weak cursor does not declare row type | Document the select list or use a strong cursor |
| Cursor unreadable after connection closes | Handle is bound to the session/database cursor | Keep connection open until reading completes |
| `ORA-01000` | Cursors/result sets/statements left unclosed | Use try-with-resources or `using` and check for leaks |
| Procedure closes cursor before returning | Caller receives an already-closed handle | Do not `CLOSE` an `OUT` cursor in a successful procedure |
| `SELECT INTO` used instead of `REF CURSOR` for many rows | `SELECT INTO` accepts only one row | Return `SYS_REFCURSOR` or use a collection/`BULK COLLECT` |
| Dynamic SQL vulnerable to SQL injection | Concatenating client input into query text | Use bind variables and identifier whitelists |
| Result set column change breaks app | Unversioned contract | Keep schema stable or create a new API version |
| Returned rows lack consistent order | Query has no `ORDER BY` | Add `ORDER BY` with deterministic tie-breakers |
| Client cannot distinguish `0` from `NULL` | Primitive getters return `0` by default | Check `wasNull()` or use nullable types |
| Row-by-row fetching is too slow | High round-trip/fetch overhead | Tune fetch size or use bulk fetch |
| Cursor held open too long hits `ORA-01555` | Insufficient undo for consistent read | Reduce cursor lifetime, paginate, and size undo |
| Multiple `OUT` cursors but only one closed | Forgot to release unused result sets | Close every cursor, even unread ones |

## 19. Hands-on exercises

Use `LAB_CUSTOMERS` from Section 17.

### Exercise 1 — Explicit cursor and REF CURSOR

Write a block that reads the customer list using an explicit cursor. Rewrite it using a weak `REF CURSOR`. Compare how the query is declared and how `OPEN` is called.

### Exercise 2 — Strong and weak

Declare a strong `REF CURSOR` returning `LAB_CUSTOMERS%ROWTYPE`. Try `OPEN` with `SELECT *` and then with a select list of only two columns. Observe the difference in type checking.

### Exercise 3 — SYS_REFCURSOR OUT

Create a procedure returning a customer list filtered by status and credit limit. Call it from SQL*Plus/SQLcl using `VARIABLE`, `EXEC`, and `PRINT`.

### Exercise 4 — Function returning a cursor

Create a function returning `SYS_REFCURSOR`. Write a PL/SQL caller that fetches row by row and closes the cursor.

### Exercise 5 — Multiple result sets

Create a procedure returning a profile and a transaction list via two `OUT SYS_REFCURSOR` parameters. Call it from a client supporting two cursors and read both.

### Exercise 6 — Dynamic SQL

Write a procedure searching customers by `NAME` or `REGION`. Use bind variables for values and a whitelist for the sort column. Test passing a string containing quotes and verify it is treated strictly as data.

### Exercise 7 — Bulk fetch

Fetch a `REF CURSOR` using `BULK COLLECT` with `LIMIT 50`. Compare the number of loop iterations with row-by-row fetching and explain why batch limiting helps control PGA memory.

### Exercise 8 — Client resource management

Write a Java snippet calling an `OUT` cursor procedure with `CallableStatement`. Use try-with-resources for `ResultSet` and the statement. Test a SQL `NULL` in a `NUMBER` column and verify `wasNull()`.

## 20. Lab data cleanup

Run only in the lab schema you created, after completing the exercises:

~~~sql
DROP PROCEDURE lab_customer_dashboard;
DROP PROCEDURE lab_get_customers;
DROP TABLE lab_customers PURGE;
~~~

If you created `LAB_ORDERS` or other objects for exercises, drop only the objects belonging to your practice schema. Drop procedures before tables to keep cleanup order straightforward. `PURGE` bypasses the Recycle Bin; do not use it on production data or data that might need recovery.

## Summary

A `REF CURSOR` is a cursor variable pointing to an open result set. A strong `REF CURSOR` declares its row type with `RETURN`; a weak `REF CURSOR` does not constrain row shape; `SYS_REFCURSOR` is Oracle's built-in weak type. Open the cursor with `OPEN ... FOR`, read with `FETCH`, and release with `CLOSE`.

To return result sets to an application, procedures typically take an `OUT SYS_REFCURSOR` parameter, open the query, and return the handle to the caller. Clients use their driver to bind the `OUT` parameter, fetch the `ResultSet`/`DataReader`, and close all resources while keeping the connection open. You can return multiple cursors, return a cursor from a function, or use implicit results on supported versions/clients. Keep result schemas stable, bind values in dynamic SQL, limit data volume, handle `NULL` explicitly, and close cursors properly to avoid resource leaks.

## Oracle Reference Documentation

- [Oracle Database PL/SQL Language Reference — Cursor Variables (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/cursor-variables.html) — `REF CURSOR`, strong/weak cursor variables, and cursor operations.
- [Oracle Database PL/SQL Language Reference — OPEN FOR Statement (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/OPEN-FOR-statement.html) — opening a cursor variable for a query.
- [Oracle Database PL/SQL Language Reference — FETCH Statement (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/FETCH-statement.html) — reading rows from a cursor.
- [Oracle Database PL/SQL Language Reference — Cursor Attributes (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/lnpls/cursor-variables.html) — cursor attributes.
- [Oracle Database PL/SQL Packages and Types Reference — DBMS_SQL (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/arpls/DBMS_SQL.html) — implicit result sets and `RETURN_RESULT`.
- [Oracle JDBC Developer's Guide (19c)](https://docs.oracle.com/en/database/oracle/oracle-database/19/jjdbc/) — calling stored procedures and receiving `REF CURSOR` in JDBC.
- [Oracle Data Provider for .NET Developer's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/odpnt/) — `OracleRefCursor` and `OracleDbType.RefCursor`.

When deploying on other Oracle releases or client drivers, consult the exact version's PL/SQL Language Reference and JDBC/ODP.NET documentation, especially regarding `REF CURSOR` binding types, implicit results, and `ResultSet`/`DataReader` lifecycle.
