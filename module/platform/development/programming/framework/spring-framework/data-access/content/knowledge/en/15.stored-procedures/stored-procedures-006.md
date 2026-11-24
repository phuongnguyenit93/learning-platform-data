# Reading Multiple Result Sets, OUT Values, and Cursors from Procedures/Functions with Spring JDBC

> **Scope:** Spring Framework – Data Access / **Stored Procedures and Functions**. This lesson explains how to collect multiple result sets (`ResultSet`), affected row counts (`update count`), `OUT`/`INOUT` parameters, and cursors (`REF_CURSOR`) when calling stored procedures/functions. The decisive factor is **the actual capabilities of the DBMS and JDBC driver pair**, not just Spring API names.

## 1. What can a single call return?

A stored procedure does not necessarily return a single value. One call can produce a **sequence of results**, for example:

```text
CALL report_proc(?)
    ├─ UPDATE COUNT: 2 rows updated
    ├─ RESULT SET #1: employee list
    ├─ RESULT SET #2: summary table
    └─ OUT "matched": 2
```

These are four related yet distinct concepts:

| Result channel | Nature | How received in JDBC | How received in Spring JDBC |
| --- | --- | --- | --- |
| First, second, ... `ResultSet` | Rows/columns returned by the procedure in the call's result stream | `execute()`, `getResultSet()`, `getMoreResults()` | `SimpleJdbcCall.returningResultSet(name, rowMapper)`, or `JdbcTemplate` callback |
| `update count` | Number of rows affected by a DML statement inside the procedure (if emitted by the driver) | `getUpdateCount()` after each step | `JdbcTemplate` can process/return counts; do not confuse them with `ResultSet` |
| `OUT`/`INOUT` | Values bound to procedure parameters | `registerOutParameter(...)` then `getXxx(...)` | `SqlOutParameter`, `SqlInOutParameter`; retrieved from `SimpleJdbcCall.execute(...)` `Map` |
| `REF_CURSOR` | An `OUT` parameter pointing to a DB-side result set, when supported by the DB/driver | Register cursor type, `getObject(...)`, and process the returned driver object | `returningResultSet` with the exact cursor name, or `SqlOutParameter` with a suitable mapper |

**Do not confuse:** a result set emitted directly during procedure execution is not necessarily an `OUT` parameter; conversely, a cursor-typed `OUT` parameter can be the *source* of a `ResultSet`. A function also has a **return value** via `{? = call func_name(?)}` syntax; the first `?` slot is the return value, shifting subsequent parameter positions to the right.

Because procedure SQL, cursor return mechanisms, and parameter names vary by DBMS, analyze the procedure signature and driver configuration before writing result-reading code.

## 2. JDBC rules so no result set is missed

`CallableStatement` extends `Statement` and supports an interleaved stream of **ResultSets / update counts**:

1. Create a `CallableStatement` via `Connection.prepareCall("{call ...}")`; use `setXxx` for `IN` and `INOUT`, and register **all `OUT`/`INOUT`** parameters via `registerOutParameter` **before execution**.
2. Call **`execute()`** when multiple results are possible. A return value of `true` means **the current result is a `ResultSet`**; `false` means the current result is an **update count or there are no more results**. `false` **does not mean finished**.
3. If `true`, fetch `getResultSet()` and read all needed rows. If `false`, fetch `getUpdateCount()`; `0` is also a **valid update count**.
4. Stop only when the current result **is not a `ResultSet` and `getUpdateCount() == -1`**. After each item, call `getMoreResults()` to advance to the next one.
5. For maximum portability, finish reading **all `ResultSet`s and update counts before reading `OUT` parameters**. Some drivers only make `OUT` values fully available after the result stream ends.
6. Close `ResultSet`s, `CallableStatement`s, and `Connection`s; in Spring, use callbacks/templates so Spring manages connections and transactions.

**Algorithm to remember:**

```java
// JDBC algorithm; assumes cs already has parameters bound/registered.
boolean hasResultSet = cs.execute();
while (true) {
    if (hasResultSet) {
        try (ResultSet rs = cs.getResultSet()) {
            while (rs.next()) {
                // Read/map each row of the current ResultSet.
            }
        }
    } else {
        int updateCount = cs.getUpdateCount();
        if (updateCount == -1) {
            break; // Only this is the termination condition.
        }
        // Handle updateCount, including the value 0.
    }
    hasResultSet = cs.getMoreResults();
}
// Only after the loop, read cs.getXxx(OUT_position).
```

By default, `getMoreResults()` closes the current `ResultSet`. If you need to keep multiple `ResultSet`s open simultaneously, JDBC provides `getMoreResults(Statement.KEEP_CURRENT_RESULT)`, but only use it after checking `DatabaseMetaData.supportsMultipleOpenResults()`; the simpler, more maintainable pattern is **read, close, then advance**.

## 3. Concrete example: SQL Server emitting 2 ResultSets, an update count, and an OUT parameter

This example intentionally picks **SQL Server + Microsoft JDBC Driver** because this database supports procedures directly emitting multiple `SELECT` statements alongside an `OUT` parameter. The script below is **SQL Server T-SQL** and cannot be copied verbatim to PostgreSQL/MySQL/Oracle. You need a running SQL Server instance, a test database, privileges to create tables/procedures, and the corresponding JDBC driver.

### 3.1. Creating data and the procedure

Run in SSMS or `sqlcmd` (here `GO` is the SQL Server tool batch separator, **not** an SQL statement sent over JDBC):

```sql
CREATE TABLE dbo.demo_employee (
    id        INT           NOT NULL PRIMARY KEY,
    full_name NVARCHAR(100) NOT NULL,
    visits    INT           NOT NULL
);
GO

INSERT INTO dbo.demo_employee (id, full_name, visits) VALUES
(1, N'An',   0),
(2, N'Binh', 0),
(3, N'Chi',  0);
GO

CREATE OR ALTER PROCEDURE dbo.demo_employee_report
    @min_id  INT,
    @matched INT OUTPUT
AS
BEGIN
    -- Allow the driver to see the UPDATE count.
    SET NOCOUNT OFF;

    UPDATE dbo.demo_employee
    SET visits = visits + 1
    WHERE id >= @min_id;

    -- ResultSet 1: detail rows
    SELECT id, full_name, visits
    FROM dbo.demo_employee
    WHERE id >= @min_id
    ORDER BY id;

    -- ResultSet 2: single summary row
    SELECT COUNT(*) AS n
    FROM dbo.demo_employee
    WHERE id >= @min_id;

    -- OUT value: not a third ResultSet.
    SET @matched = (
        SELECT COUNT(*) FROM dbo.demo_employee WHERE id >= @min_id
    );
END;
GO
```

With `@min_id = 2` on the first run, the update affects employees `2` and `3`; the detail set contains two rows, the summary set yields `n = 2`, and `@matched = 2`. Calling the procedure again keeps incrementing `visits`, so this is **not** an idempotent example.

### 3.2. Java 17: reading the exact result sequence

Create **`ReadProcedureResults.java`**:

```java
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;

public final class ReadProcedureResults {
    public static void main(String[] args) throws SQLException {
        String url = System.getenv("DB_URL");
        String username = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");

        if (url == null || username == null || password == null) {
            throw new IllegalStateException(
                "Set DB_URL, DB_USER and DB_PASSWORD first");
        }

        try (Connection connection =
                     DriverManager.getConnection(url, username, password);
             CallableStatement call = connection.prepareCall(
                     "{call dbo.demo_employee_report(?, ?)}")) {

            // SQL Server: @min_id (IN), @matched (OUT)
            call.setInt(1, 2);
            call.registerOutParameter(2, Types.INTEGER);

            boolean hasResultSet = call.execute();
            int resultSetNumber = 0;

            while (true) {
                if (hasResultSet) {
                    resultSetNumber++;

                    try (ResultSet rs = call.getResultSet()) {
                        if (resultSetNumber == 1) {
                            while (rs.next()) {
                                System.out.printf(
                                    "EMPLOYEE id=%d name=%s visits=%d%n",
                                    rs.getInt("id"),
                                    rs.getString("full_name"),
                                    rs.getInt("visits"));
                            }
                        } else if (resultSetNumber == 2) {
                            while (rs.next()) {
                                System.out.println(
                                    "SUMMARY n=" + rs.getInt("n"));
                            }
                        } else {
                            // Rule for procedures expanded later:
                            // at minimum, consume any extra results.
                            while (rs.next()) {
                                // Can be handled using ResultSetMetaData.
                            }
                        }
                    }
                } else {
                    int count = call.getUpdateCount();
                    if (count == -1) {
                        break;
                    }
                    System.out.println("UPDATE_COUNT=" + count);
                }

                hasResultSet = call.getMoreResults();
            }

            // Read OUT after the entire ResultSet/update count sequence.
            int matched = call.getInt(2);
            System.out.println(
                "OUT matched=" + (call.wasNull() ? "NULL" : matched));
        }
    }
}
```

The program above uses **only JDK 17's `java.sql` API** at compile time. At **runtime**, the JVM still needs the Microsoft JDBC Driver on the classpath; the JAR name and version depend on the installed driver package:

```bash
javac --release 17 -encoding UTF-8 ReadProcedureResults.java

# Windows PowerShell: rename the driver JAR to mssql-jdbc.jar
java -cp ".;mssql-jdbc.jar" ReadProcedureResults

# Linux/macOS uses ':' instead of ';' as the classpath separator:
# java -cp ".:mssql-jdbc.jar" ReadProcedureResults
```

Before running, set `DB_URL`, `DB_USER`, and `DB_PASSWORD` in environment variables. `DB_URL` must point to the database where the script in section 3.1 ran; for example, `jdbc:sqlserver://localhost:1433;databaseName=your_database`, with TLS/authentication settings configured for your real environment.

**Meaning of the first-run output** (these are logical values; log line order or whether the driver emits extra update counts can vary by configuration):

```text
UPDATE_COUNT=2
EMPLOYEE id=2 name=Binh visits=1
EMPLOYEE id=3 name=Chi visits=1
SUMMARY n=2
OUT matched=2
```

The key takeaway of the Java snippet is not a fixed number of `UPDATE_COUNT`s, but that **the loop does not stop after a `getMoreResults() == false` if `getUpdateCount() >= 0` remains**. In SQL Server, `SET NOCOUNT ON` can suppress intermediate counts; changing procedure settings can alter the result stream seen by the client. The program checks the exact **sequence number of the `ResultSet`s**, without relying on how many update counts arrive.

> **Execution scope:** the `main` example is a JDBC application outside Spring to show the full mechanism. In a Spring application with managed transactions, do not call `DriverManager` directly or close Spring-provided connections; use the application's `JdbcTemplate`/`DataSource`.

## 4. Using `SimpleJdbcCall` in Spring to receive multiple ResultSets and OUT

Once you know the procedure signature and which result sets will appear, `SimpleJdbcCall` is usually the more concise option. It accepts `IN` parameters and maps `OUT` values and result sets into a single `Map<String, Object>`.

**Integration example inside a Spring JDBC 6.x application using the SQL Server procedure from section 3** (this DAO class requires `spring-jdbc` and a configured `DataSource`; it is an application component, not a standalone `main` program):

```java
import java.sql.Types;
import java.util.List;
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;

public final class EmployeeReportDao {
    public record Employee(int id, String fullName, int visits) {}
    public record Report(
            List<Employee> employees, int total, Integer matched) {}

    private final SimpleJdbcCall procedure;

    public EmployeeReportDao(DataSource dataSource) {
        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.setResultsMapCaseInsensitive(true);

        this.procedure = new SimpleJdbcCall(jdbc)
            .withSchemaName("dbo")
            .withProcedureName("demo_employee_report")
            .withoutProcedureColumnMetaDataAccess()
            .declareParameters(
                new SqlParameter("min_id", Types.INTEGER),
                new SqlOutParameter("matched", Types.INTEGER))
            .returningResultSet("employees", (rs, rowNum) ->
                new Employee(
                    rs.getInt("id"),
                    rs.getString("full_name"),
                    rs.getInt("visits")))
            .returningResultSet("summary", (rs, rowNum) ->
                rs.getInt("n"));
    }

    public Report run(int minId) {
        Map<String, Object> out = procedure.execute(
            new MapSqlParameterSource("min_id", minId));

        @SuppressWarnings("unchecked")
        List<Employee> employees =
            (List<Employee>) out.get("employees");

        @SuppressWarnings("unchecked")
        List<Integer> summary =
            (List<Integer>) out.get("summary");

        Number matched = (Number) out.get("matched");

        return new Report(
            employees,
            summary.get(0),
            matched == null ? null : matched.intValue());
    }
}
```

**Why configure it this way?**

- `withProcedureName("demo_employee_report")` selects the procedure; `withSchemaName("dbo")` selects the SQL Server schema.
- `withoutProcedureColumnMetaDataAccess()` disables guessing the parameter list from metadata; `declareParameters(...)` explicitly declares **parameters in exact order**. This helps when metadata is incomplete, overloads exist, or the driver reports unexpected names. If metadata lookup is enabled, Spring can infer many parameters, though actual driver output must still be verified.
- `new SqlParameter("min_id", Types.INTEGER)` represents `IN`; `new SqlOutParameter("matched", Types.INTEGER)` represents `OUT`. For a parameter that is both `IN` and `OUT`, use `SqlInOutParameter` and supply the corresponding input.
- Two `returningResultSet(...)` calls register **two `RowMapper`s matching the exact order of unnamed ResultSets** emitted by the procedure; `employees`/`summary` are application-chosen keys to retrieve the results. **They are neither column names nor `OUT` parameter names.**
- The returned `Map` contains `employees` and `summary` as lists created by the mappers, alongside the `matched` value. Do not infer result order from the iteration order of `Map` keys.
- `setResultsMapCaseInsensitive(true)` makes `OUT` key lookups more resilient when drivers/databases change parameter name casing. That does not allow arbitrarily changing procedure parameter names when metadata is disabled.
- `summary.get(0)` assumes the procedure promises to return exactly one summary row; if the procedure does not guarantee that, the application should validate the list and raise a business error.

Note: `SimpleJdbcCall` helps **collect and convert** results, but if a large `ResultSet` is mapped into a `List`, memory usage still grows with row count. For millions of rows, see section 7 on streaming/sequential processing.

### When to use `JdbcTemplate` instead of `SimpleJdbcCall`?

`JdbcTemplate.execute(callString, CallableStatementCallback<T>)` lets you control `CallableStatement` directly inside a callback, processing each `ResultSet` and update count using the algorithm in section 2, even when the count/names/shapes of returned sets are only known at runtime. `JdbcTemplate.call(CallableStatementCreator, List<SqlParameter>)` also supports declaring results; `SqlReturnResultSet` can use a `RowMapper`, `ResultSetExtractor`, or `RowCallbackHandler`.

This is useful when decoding a dynamic series of result sets or streaming rows directly to another destination. `JdbcTemplate` callbacks run on Spring's connection, participate in the current transaction, and translate `SQLException` into `DataAccessException`. Do not retain a `ResultSet` to read after the callback has returned.

## 5. `REF_CURSOR`: receiving a cursor as an `OUT` parameter

Some DBMSs return results via a **cursor-typed `OUT` parameter** rather than emitting `SELECT` statements directly in the `getMoreResults()` stream. With drivers supporting standard JDBC, you can register:

```java
// Illustrative: use only when the DB signature and JDBC driver support REF_CURSOR.
try (CallableStatement call =
         connection.prepareCall("{call open_employees(?, ?)}")) {
    call.setInt(1, minId);
    call.registerOutParameter(2, Types.REF_CURSOR);
    call.execute();

    Object value = call.getObject(2);
    if (!(value instanceof ResultSet)) {
        throw new SQLException("Driver did not return a ResultSet cursor");
    }

    try (ResultSet rs = (ResultSet) value) {
        while (rs.next()) {
            // Use data while the cursor, statement, and connection are still alive.
        }
    }
}
```

The example above is **integration code, not standalone**: the `open_employees` procedure, call syntax, cursor type, and whether `getObject` returns a `ResultSet` must be verified against the DB/driver. Do not equate `Types.REF_CURSOR` with `Types.REF`; they are two distinct JDBC type codes. A driver may require a different type code—for instance, some PostgreSQL call paths register `Types.OTHER`.

### 5.1. PostgreSQL via pgJDBC: different from the SQL Server example

PostgreSQL allows functions to return `SETOF` or `refcursor`. **Functions returning `SETOF`** should usually be queried with `SELECT * FROM func_name(?)` via `PreparedStatement`/`JdbcTemplate.query(...)`, rather than forcing them into `CallableStatement`. For functions returning `refcursor`, pgJDBC documentation instructs setting `autoCommit = false` and registering the return parameter as `Types.OTHER`.

Illustrative example for an **existing PostgreSQL function** named `open_employees(min_id integer) RETURNS refcursor`, defined to open a cursor on the corresponding table:

```java
// PostgreSQL integration code, used outside a Spring-managed transaction.
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (CallableStatement call = connection.prepareCall(
            "{? = call open_employees(?)}")) {
        call.registerOutParameter(1, Types.OTHER);
        call.setInt(2, 2);
        call.execute();

        try (ResultSet cursor = (ResultSet) call.getObject(1)) {
            while (cursor.next()) {
                System.out.println(cursor.getString("full_name"));
            }
        }
    }
    connection.commit();
}
```

**Two easily overlooked constraints:**

1. PostgreSQL cursors require a live transaction. If the transaction closes/commits too early, the server-side cursor may no longer be accessible. In a Spring application, use `@Transactional` so the reader shares the same transaction scope; avoid arbitrarily calling `setAutoCommit(false)`/`commit()` on Spring-managed connections.
2. **pgJDBC currently documents a specific limitation:** when reading a `refcursor` as a `ResultSet`, the driver may fetch and cache **all rows on the client**, and `fetchSize` does not reduce memory on this code path. Thus, "cursor" does not automatically mean low-RAM streaming. If the goal is reading very large row counts, evaluate a `SELECT` query + driver-supported cursor/fetch-size or pagination.

Additionally, pgJDBC has the `escapeSyntaxCallMode` property: the default favors functions; `callIfNoReturn` is often needed when calling **procedures** that have no return slot. Do not apply the same `{call ...}` syntax across all DBs without checking driver mapping.

### 5.2. Oracle and other drivers

Oracle commonly uses `SYS_REFCURSOR`/cursor `OUT` parameters in PL/SQL signatures; Oracle drivers may support `Types.REF_CURSOR` or a call path using Oracle-specific type constants. Always check the driver version, registered types, and `ResultSet` mapping. SQL Server, by contrast, commonly returns `SELECT` statements directly in a multi-result stream rather than requiring `REF_CURSOR` parameters. These are **common patterns**, not rules for every procedure or driver version.

In Spring, `SimpleJdbcCall.returningResultSet("p_cursor", mapper)` can map an `OUT` cursor **if supported by both the driver and Spring**, provided **the name `p_cursor` matches the procedure's cursor parameter name**. With some drivers/cursor types, you may need to declare `SqlOutParameter` explicitly with a `RowMapper`/`SqlReturnType`. Avoid registering the same cursor twice via two mechanisms without understanding metadata; inspect the resulting `Map` against the real procedure.

## 6. Evaluating driver capabilities before choosing a call style

JDBC provides `DatabaseMetaData` to inspect features that the **driver + database** report as supported:

```java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.SQLException;

public final class JdbcCapabilities {
    public static void print(Connection connection) throws SQLException {
        DatabaseMetaData m = connection.getMetaData();
        System.out.println("Driver: " + m.getDriverName());
        System.out.println("Driver version: " + m.getDriverVersion());
        System.out.println("Stored procedures: " +
                m.supportsStoredProcedures());
        System.out.println("Multiple result sets: " +
                m.supportsMultipleResultSets());
        System.out.println("Multiple open results: " +
                m.supportsMultipleOpenResults());
        System.out.println("REF_CURSOR: " +
                m.supportsRefCursors());
    }
}
```

**Interpretation:**

- `supportsStoredProcedures()`: the driver/database reports support for stored procedure calls.
- `supportsMultipleResultSets()`: can receive multiple `ResultSet`s from **a single `execute()`**.
- `supportsMultipleOpenResults()`: can keep multiple `ResultSet`s from one call open simultaneously; **different** from reading multiple `ResultSet`s *sequentially*.
- `supportsRefCursors()`: reports JDBC `REF_CURSOR` support. `false` or `SQLFeatureNotSupportedException` may require choosing a different strategy; some vendor-specific call paths may still work even when the driver does not advertise full JDBC standard support.
- `DatabaseMetaData.getProcedureColumns(...)`, `getProcedures(...)`, and corresponding function metadata methods can help locate signatures, though names, schemas, overloads, and `OUT` types are not always returned completely or accurately by drivers. In those cases, inspect the DB catalog directly and declare explicitly in `SimpleJdbcCall`.

**Metadata is only a screening step.** Run integration tests with the exact **DBMS + JDBC driver + Spring Framework versions** used in production; driver updates can alter update counts, `OUT` names, automatic cursor loading, and result ordering. Never write code assuming every DBMS returns multiple `ResultSet`s identically.

## 7. Managing transactions, resources, and memory when reading results

**Transactions and cursor lifecycles.** A `ResultSet` normally depends on the `Statement` and `Connection` that produced it. Read all rows inside `try-with-resources` or a Spring callback; never return a raw `ResultSet` from a DAO and close the connection. Some server-side cursors require an active transaction and may close upon commit depending on holdability.

**Data volume.** `SimpleJdbcCall` with a `RowMapper` accumulates results into a `List` per result set. For large datasets, you can use `JdbcTemplate.execute(..., CallableStatementCallback<T>)` and process rows one by one (writing to a file, forwarding to a consumer, computing an aggregate) while the `ResultSet` is open; check `fetchSize` and how the driver loads rows. If the driver already buffers the entire cursor client-side, writing your own loop will not save memory.

**Column labels/types.** Mappers must use the exact column names/aliases returned by the procedure. Two result sets with different schemas need two separate mappers; never assume `getInt` on a nullable column without checking `rs.wasNull()`. For `OUT INTEGER`, call `call.wasNull()` immediately after `call.getInt(index)` to distinguish `0` from SQL `NULL`.

**Security and transactions:** the DB user only needs privileges to invoke the procedure and perform required actions; pass values via `?`/bind parameters instead of concatenating strings from input to build call statements. If a procedure both updates data and returns results, define transaction isolation, commit/rollback, retry, and idempotency expectations; `getMoreResults` does not auto-commit.

**Errors and status:** `SQLException` exposes `getSQLState()` and `getErrorCode()` to aid root-cause analysis. In some drivers, errors in later result sets only surface when you call `getMoreResults()` or read `ResultSet.next()`; therefore, stopping after the first set can miss errors. Spring translates JDBC errors into `DataAccessException`. Do not mask errors by skipping unprocessed sets or catching exceptions and returning an empty list.

## 8. Common mistakes

| Mistake | Why it is wrong | Resolution |
| --- | --- | --- |
| `if (!call.execute()) return;` | `false` may be an update count, with more results still following | Use a loop combining `getUpdateCount()` and `getMoreResults()` |
| `while (call.getMoreResults())` as the entire loop | Skips interleaved update counts; can stop before the next result set | Loop until **no result set and count = -1** |
| Reading `OUT` immediately after `execute()` | Some drivers only populate `OUT` once all results are consumed; unread result sets may be lost | Process all result sets/counts first |
| Confusing `OUT` with the first `ResultSet` | `OUT` is a named/positional parameter, whereas direct result sets flow through the JDBC stream | Distinguish `registerOutParameter` from `getResultSet` |
| Declaring wrong names or order for `returningResultSet` | Drivers do not name directly emitted result sets | Register mappers **in actual emission order** |
| Using `Types.REF_CURSOR` on every DB | Drivers may only support `Types.OTHER` or a vendor type | Follow driver documentation and integration testing |
| Committing/closing connection before reading cursor | Cursors depend on the transaction/connection | Read inside the transaction and close in proper order |
| Assuming cursors always stream | Drivers may buffer all rows | Measure heap usage and verify actual streaming paths |
| Assuming `OUT` keys in `Map` always match exact casing | Metadata/drivers alter letter casing | Use `setResultsMapCaseInsensitive(true)` when appropriate |
| Using `executeQuery()` for multi-result procedures | Only accepts one `ResultSet` or fails on update counts/`OUT` | Use `execute()` and traverse the full result stream |
| Not reading error-raising statements in later result sets | Errors may only throw when advancing results or reading rows | Consume the full stream when required by the procedure contract |

## 9. Integration testing and checklist

Prepare concrete test procedures on a **real DB/driver**:

1. **`OUT` only, no result sets:** verify the loop terminates properly and `OUT` values are readable.
2. **Two consecutive result sets:** verify order, column/alias names, and corresponding mappers.
3. **Update count between two result sets** (including a count of `0`): prove the loop does not exit early.
4. **`OUT = NULL`:** distinguish from `0`; verify both raw `wasNull()` and Spring's `Map`.
5. **Procedure adds an extra result set:** check whether the contract allows extra sets; alert when ordering changes.
6. **`REF_CURSOR`:** verify `OUT` registration type, `getObject` return type, reading inside transactions, and memory behavior on large data.
7. **Error paths:** SQL error in the second result set, missing `EXECUTE` privilege, wrong parameter type, timeout, rollback.
8. **Real metadata:** check `supportsMultipleResultSets`, `supportsRefCursors`, `OUT` names, and `SimpleJdbcCall` config on the exact deployment driver.

**Implementation checklist:**

- [ ] Document the full stored procedure/function signature: `IN`, `OUT`, `INOUT`, return value, direct result sets, and cursors.
- [ ] Know the exact DBMS, JDBC driver/version, and relevant feature flags.
- [ ] Use `execute()` and loop until the proper termination condition, never treating `false` as end-of-results.
- [ ] Consume all result sets/update counts before reading `OUT`; check for SQL `NULL`.
- [ ] With `SimpleJdbcCall`, ensure `OUT` cursor names match and mapper order matches direct result sets.
- [ ] Manage connections/transactions and close cursors at the right time.
- [ ] Control memory when mapping into `List`; measure in practice instead of assuming cursors always stream.
- [ ] Test end-to-end with the target driver, especially errors raised only when reading later results.

**Takeaway:** to accurately read a procedure/function returning multiple items, you need to know **which channel carries which result**, **the consumption order**, and **driver limitations**. `SimpleJdbcCall` cuts down parameter binding/mapping boilerplate, but the procedure contract and JDBC driver capabilities remain the final source of truth.

### Official references

- Spring Framework – `SimpleJdbcCall`, OUT parameters, and `returningResultSet`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html
- Spring Framework – `JdbcTemplate` and JDBC callbacks: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Java SE 17 – `CallableStatement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/CallableStatement.html
- Java SE 17 – `Statement.getMoreResults`/`getUpdateCount`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
- Java SE 17 – `DatabaseMetaData`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DatabaseMetaData.html
- Microsoft JDBC Driver for SQL Server – multiple `ResultSet`s: https://learn.microsoft.com/en-us/sql/connect/jdbc/using-multiple-result-sets
- PostgreSQL JDBC – calling procedures/functions and `refcursor`: https://jdbc.postgresql.org/documentation/callproc/
