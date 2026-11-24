# `CallableStatement` and the Need to Call Code in the Database

In Spring Framework Data Access, most ordinary read/write operations can be performed with `JdbcTemplate.query(...)`, `update(...)`, or a JDBC `PreparedStatement`. However, a system may also place **executable code inside the database** in the form of *stored procedures* and *stored functions*. When a Java application needs to invoke these objects, JDBC provides `java.sql.CallableStatement`; Spring JDBC provides utility classes such as `SimpleJdbcCall` to reduce boilerplate code.

Lesson objectives: understand **when it is necessary to call code in the database**, how procedures/functions differ from ordinary SQL statements, how to pass/receive `IN`/`OUT`/`INOUT` parameters, read results, and integrate those calls into a Spring application while properly managing connections, transactions, and errors.

## 1. Why does an application need to call code stored in the database?

Suppose a system has logic to aggregate revenue per customer. There are three common ways to organize this:

1. Java sends `SELECT SUM(amount) ...` directly using `PreparedStatement`/`JdbcTemplate`.
2. The database already defines `get_customer_total(customer_id, total OUT)`; Java calls this procedure to receive the value.
3. The database already defines a function `with_ten_percent_fee(amount)`; Java uses the function result in a `SELECT` statement, or calls it through a function-oriented API.

Encapsulating logic as a routine can be appropriate when:

- **Multiple applications share the same data processing rules** and the database serves as the central place to manage those rules.
- **The system already has existing procedures/functions** (for example, legacy systems or databases integrated with external software) that the application is required to use.
- **A business operation involves multiple SQL statements** that can be executed at the database, reducing several client-server round trips when properly designed.
- **Access permissions are granted per routine**: the application account can be permitted to call a procedure instead of being granted direct privileges on all underlying tables, depending on the RDBMS's permission configuration and execution mode.

Those are useful possibilities, **not a default reason to put all business logic into stored procedures**. That approach can increase vendor lock-in and create difficulties for versioning/migrations, testing, and code tracing; procedures running on the database also consume database resources. A simple `SELECT` or `UPDATE` usually does not need a routine.

### How do procedures, functions, and SQL statements differ?

| Form | Primary purpose | Typical inputs/outputs | Common invocation style |
| --- | --- | --- | --- |
| Direct SQL | Read/write data with a specific statement | `ResultSet`, affected-row count | `PreparedStatement` or `JdbcTemplate` |
| Stored procedure | Execute a sequence of operations defined in the DB | `IN`, `OUT`, `INOUT`; may produce result sets/update counts | `CALL ...`, JDBC `{call ...}` |
| Stored function | Compute a value and return it to the calling expression | Input arguments and one `RETURN` value | `SELECT function(...)` or JDBC `{? = call ...}` when supported by the driver |

The syntax for defining routines and what routines are allowed to do **differ across MySQL, PostgreSQL, SQL Server, Oracle...**. This lesson uses **MySQL 8.4** to provide concrete SQL examples and outputs; `CallableStatement` itself is a standard JDBC API, though driver and SQL compatibility must be verified on the actual RDBMS.

## 2. How `CallableStatement` works in JDBC

`CallableStatement` is an interface in `java.sql` that **extends `PreparedStatement`**. Therefore, it has parameter-binding methods such as `setInt`, `setLong`, and `setString`, supplemented with methods for declaring/reading output parameters such as `registerOutParameter`, `getInt`, and `getBigDecimal`.

A typical call:

```text
Java / Spring code
    |
    | Connection.prepareCall("{call ...}")
    | setXxx(IN), registerOutParameter(OUT), execute()
    v
JDBC driver (translates escape syntax to the appropriate DB protocol)
    |
    v
Stored procedure / function in the database
    |
    | results, OUT parameters, result sets, update counts, or errors
    v
CallableStatement -> Java code reads results
```

Two common forms of *JDBC escape syntax*:

```java
// Call a procedure with two parameters; this is an SQL string, not complete Java.
"{call get_customer_total(?, ?)}"

// Call a function with one argument and one return value.
"{? = call with_ten_percent_fee(?)}"
```

- `?` is a parameter placeholder, indexed **starting from 1**.
- For the `get_customer_total` procedure, position 1 is `IN` and position 2 is `OUT`.
- For a function using `{? = call ...}` syntax, **position 1 is the return value**, while the function's arguments start at position 2.
- `Connection.prepareCall(...)` creates the `CallableStatement`; the JDBC driver handles the escape syntax and communicates with the database.
- `CallableStatement.execute()` executes the routine. The `boolean` return value of `execute()` indicates **whether the first result is a `ResultSet`**, not a "success/failure" flag. Errors are normally reported via `SQLException`.

### Three parameter modes

| Mode | Meaning | Required methods |
| --- | --- | --- |
| `IN` | Java passes a value into the routine | `setXxx(index, value)` |
| `OUT` | The routine returns a value to Java | `registerOutParameter(index, Types.XXX)`, then `getXxx(index)` after execution |
| `INOUT` | Java both passes an initial value and receives the final value | **Both** `setXxx` **and** `registerOutParameter` at the same position, followed by `getXxx` |

Every `OUT`/`INOUT` parameter (including a function's return parameter when using JDBC escape syntax) must be **registered before execution**. Choose `Types.INTEGER`, `Types.BIGINT`, `Types.DECIMAL`, `Types.VARCHAR`, etc. to match the SQL type. If `getInt()` or `getLong()` reads an SQL `NULL`, Java returns `0`; call `wasNull()` immediately after the getter to distinguish `NULL` from an actual 0 value. For monetary amounts, use `BigDecimal` instead of `double` when decimal precision is required.

## 3. Preparing the MySQL database used throughout the examples

This example runs on **MySQL 8.4**, using a dedicated schema `callable_demo`. Save all of the following SQL into `routines.sql` and execute it with the MySQL command-line client in a learning environment; an account with privileges to create the corresponding schema, tables, and routines is required. The creation and sample data-loading statements are designed for an initial run on a fresh schema.

```sql
CREATE DATABASE IF NOT EXISTS callable_demo;
USE callable_demo;

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    amount DECIMAL(12, 2) NOT NULL
);

INSERT INTO orders (id, customer_id, amount) VALUES
    (1, 42, 100.50),
    (2, 42, 50.00),
    (3, 99, 25.00);

DELIMITER //

CREATE PROCEDURE get_customer_total(
    IN p_customer_id BIGINT,
    OUT p_total DECIMAL(12, 2)
)
BEGIN
    SELECT COALESCE(SUM(amount), 0.00)
      INTO p_total
      FROM orders
     WHERE customer_id = p_customer_id;
END//

CREATE PROCEDURE increment_number(INOUT p_number INT)
BEGIN
    SET p_number = p_number + 1;
END//

CREATE FUNCTION with_ten_percent_fee(p_amount DECIMAL(12, 2))
RETURNS DECIMAL(12, 2)
DETERMINISTIC
NO SQL
RETURN ROUND(p_amount * 1.10, 2)//

DELIMITER ;
```

**Explanation:**

- `get_customer_total` accepts `p_customer_id` (`IN`), computes the sum of `amount`, and assigns it to `p_total` (`OUT`). Customers with no orders get a total of `0.00` thanks to `COALESCE`.
- `increment_number` uses `INOUT`: it takes a number, increments it by 1, and returns it through the same parameter.
- `with_ten_percent_fee` is a function returning a single value: it increases the amount by **a hypothetical 10% fee for the example**, rounded to two decimal places. Since the function only computes from its parameter, it is declared `DETERMINISTIC NO SQL`.
- `DELIMITER //` and `DELIMITER ;` are **MySQL client commands** to submit the entire `CREATE ... BEGIN ... END` block as one unit; they are not SQL statements to send verbatim through `PreparedStatement`.
- A MySQL stored function accepts input arguments and `RETURN`s a single value; `OUT` and `INOUT` in the example belong to **procedures**. Some RDBMSs have different rules.
- Test data: customer `42` has two orders `100.50` and `50.00`; the total is `150.50`.

You can test the routines yourself from the MySQL client:

```sql
CALL get_customer_total(42, @total);
SELECT @total;
SET @counter = 7;
CALL increment_number(@counter);
SELECT @counter;
SELECT with_ten_percent_fee(150.50) AS total_with_fee;
```

The expected values are `150.50`, `8`, and `165.55`, respectively. Passing **session variables** like `@total` and `@counter` is MySQL client syntax; on the Java side we will use JDBC's `registerOutParameter`.

## 4. Java 17 example: calling procedures with IN/OUT, INOUT, and a function

This is a **standalone Java program compilable with JDK 17+**, using the standard JDBC API. To run it for real, you need a running MySQL instance, the schema/routines from section 3, MySQL Connector/J on the runtime classpath, and the three environment variables `JDBC_URL`, `JDBC_USER`, and `JDBC_PASSWORD` matching the database. Save the program in **`CallableStatementDemo.java`**:

```java
import java.math.BigDecimal;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.sql.Types;

public final class CallableStatementDemo {
    private static String requiredEnv(String name) {
        String value = System.getenv(name);
        if (value == null) {
            throw new IllegalStateException("Missing environment variable: " + name);
        }
        return value;
    }

    public static void main(String[] args) throws SQLException {
        String url = requiredEnv("JDBC_URL");
        String user = requiredEnv("JDBC_USER");
        String password = requiredEnv("JDBC_PASSWORD");

        try (Connection connection =
                     DriverManager.getConnection(url, user, password)) {

            BigDecimal total;
            try (CallableStatement call = connection.prepareCall(
                    "{call get_customer_total(?, ?)}")) {
                call.setLong(1, 42L);                         // IN
                call.registerOutParameter(2, Types.DECIMAL); // OUT
                call.execute();
                total = call.getBigDecimal(2);
            }
            System.out.println("customerTotal=" + total.toPlainString());

            try (CallableStatement call = connection.prepareCall(
                    "{? = call with_ten_percent_fee(?)}")) {
                call.registerOutParameter(1, Types.DECIMAL); // RETURN
                call.setBigDecimal(2, total);                 // IN
                call.execute();
                BigDecimal feeTotal = call.getBigDecimal(1);
                System.out.println("totalWithFee=" + feeTotal.toPlainString());
            }

            try (CallableStatement call = connection.prepareCall(
                    "{call increment_number(?)}")) {
                call.setInt(1, 7);                            // IN
                call.registerOutParameter(1, Types.INTEGER);   // OUT
                call.execute();
                int nextValue = call.getInt(1);
                System.out.println("incremented=" + nextValue);
            }
        }
    }
}
```

The program uses `try-with-resources` to close each `CallableStatement` and `Connection` even when an exception occurs. `DriverManager` locates the JDBC driver added to the classpath via the standard driver registration mechanism; the code above has no compile-time dependency on any MySQL-specific class.

**Compile:** place `CallableStatementDemo.java` in the working directory and use JDK 17+:

```bash
javac -encoding UTF-8 CallableStatementDemo.java
```

**Run:** download MySQL Connector/J (for example, version `8.4.0`), place `mysql-connector-j-8.4.0.jar` next to the `.class` file; configure the environment variables with a URL such as `jdbc:mysql://127.0.0.1:3306/callable_demo` and a MySQL account with `EXECUTE` privilege on the routines. On Linux/macOS:

```bash
java -cp ".:mysql-connector-j-8.4.0.jar" CallableStatementDemo
```

On Windows PowerShell:

```powershell
java -cp ".;mysql-connector-j-8.4.0.jar" CallableStatementDemo
```

Output against the created data and routines:

```text
customerTotal=150.50
totalWithFee=165.55
incremented=8
```

Points to verify step by step:

1. When calling `get_customer_total`, `setLong(1, 42L)` binds the ID; `registerOutParameter(2, Types.DECIMAL)` declares the value to retrieve; `getBigDecimal(2)` reads the total after `execute()`.
2. When calling a **function**, the `?` **before** the `=` sign is the return value at position 1. Therefore, the `BigDecimal` input is bound to position **2**, and the result is read from position **1**.
3. With `INOUT`, position **1** both receives `7` via `setInt` and is declared as output via `registerOutParameter`; after the call it returns `8`.
4. `getBigDecimal` can return `null` when the SQL output is `NULL`. In the sample data, `get_customer_total` uses `COALESCE` so it returns a non-null number. Real applications must clearly define how null outputs are handled.
5. Returning `false` from `execute()` for a routine that does not produce a `ResultSet` **is not evidence that the routine failed**. Rely only on outputs/exceptions and the appropriate result types.

## 5. Routine results can be more than a single OUT parameter

`CallableStatement` can encounter the following output forms, depending on the routine and RDBMS:

- **OUT/INOUT parameters:** retrieved with `getXxx(index)` after execution, such as a monetary total or a status code.
- **RETURN value from a function:** registered and retrieved at the appropriate position, typically position 1 with JDBC escape syntax.
- **One or more ResultSets:** if a procedure returns result tables via `SELECT` (as in MySQL), use `getResultSet()` and `getMoreResults()`.
- **Update counts:** when data manipulation statements report the number of affected rows, use `getUpdateCount()`.

The following example is **a Java method that can be added to a JDBC class**, used when a procedure produces one or more `ResultSet`s/update counts. Pass in a `CallableStatement` whose inputs and outputs are already configured, **without having called `execute()` yet**:

```java
static void printAllResults(CallableStatement call) throws SQLException {
    boolean hasResultSet = call.execute();

    while (true) {
        if (hasResultSet) {
            try (java.sql.ResultSet rs = call.getResultSet()) {
                while (rs.next()) {
                    System.out.println("firstColumn=" + rs.getObject(1));
                }
            }
        } else {
            int updateCount = call.getUpdateCount();
            if (updateCount == -1) {
                break; // No more ResultSets or update counts.
            }
            System.out.println("updateCount=" + updateCount);
        }
        hasResultSet = call.getMoreResults();
    }
}
```

The method above prints the first column in each result set (for result sets with at least one column). This is a **result observation utility**, not how to map DTOs for a business application. When you want to map data rows, read the corresponding columns and types. For output parameters, JDBC recommends processing result sets/update counts before retrieving `OUT` values for better portability. Some drivers provide a mechanism to return cursors/`REF_CURSOR` through an output parameter; registration and resource cleanup depend on the driver and database type.

### When to use `executeQuery`, `executeUpdate`, or `execute`?

- `executeQuery()` suits a statement that only returns a single `ResultSet` according to a known contract.
- `executeUpdate()` suits a data manipulation statement with an update count according to a known contract.
- **`execute()` is the flexible choice for `CallableStatement`**, especially when it is unknown whether the routine produces a `ResultSet`, an update count, or multiple result types. Afterwards, use the corresponding result-reading APIs.

Do not confuse **procedure success** with `execute() == true`; `true` only states that **the first result is a `ResultSet`**.

## 6. From plain JDBC to Spring JDBC

In a Spring application using `spring-jdbc` with a configured `DataSource`, the two main approaches are:

1. Use `JdbcTemplate.execute(CallableStatementCreator, CallableStatementCallback)` when you need direct control over `prepareCall`, parameter binding, and reading complex results.
2. Use `SimpleJdbcCall` when you want a named procedure/function caller class, declarative input/output mapping, and Spring managing the JDBC boilerplate.

### 6.1. Calling a procedure via `SimpleJdbcCall`

The following class is a **Spring component**; place it in a project that already has `JdbcTemplate`, `spring-jdbc`, and the MySQL driver. It calls the exact `get_customer_total` routine from section 3.

```java
import java.math.BigDecimal;
import java.sql.Types;
import java.util.Map;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.SqlOutParameter;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcCall;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerRoutineRepository {
    private final SimpleJdbcCall totalCall;
    private final SimpleJdbcCall feeCall;

    public CustomerRoutineRepository(JdbcTemplate jdbcTemplate) {
        this.totalCall = new SimpleJdbcCall(jdbcTemplate)
                .withProcedureName("get_customer_total")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                        new SqlParameter("p_customer_id", Types.BIGINT),
                        new SqlOutParameter("p_total", Types.DECIMAL));

        this.feeCall = new SimpleJdbcCall(jdbcTemplate)
                .withFunctionName("with_ten_percent_fee");
    }

    public BigDecimal customerTotal(long customerId) {
        Map<String, Object> output = totalCall.execute(
                new MapSqlParameterSource("p_customer_id", customerId));
        return (BigDecimal) output.get("p_total");
    }

    public BigDecimal totalWithFee(BigDecimal amount) {
        return feeCall.executeFunction(
                BigDecimal.class,
                new MapSqlParameterSource("p_amount", amount));
    }
}
```

Explanation:

- `totalCall` is **configured once** in the constructor, not rebuilt on every call.
- `withoutProcedureColumnMetaDataAccess()` instructs Spring not to query the database for procedure metadata; therefore, all parameters must be declared via `declareParameters(...)`. This is useful when driver metadata is unreliable or metadata access permissions are restricted.
- `SqlParameter` describes `IN`; `SqlOutParameter` describes `OUT`; for `INOUT`, there is `SqlInOutParameter`.
- `execute(...)` returns a `Map` containing outputs keyed by output name. Writing `output.get("p_total")` assumes the result name matches the declaration. With metadata-based routines, letter casing may vary by database/driver.
- `feeCall.withFunctionName(...)` configures a **function**; `executeFunction(BigDecimal.class, ...)` directly returns a `BigDecimal`. Here Spring uses function metadata from MySQL. If metadata is missing or differs from expectations, declare parameters or adjust the configuration to fit the driver.

`SimpleJdbcCall` does not mean the procedure is compiled into Java code. The logic still executes in the database; Spring handles connections, parameter binding, output decoding, and translating JDBC errors into the `DataAccessException` hierarchy.

### 6.2. Calling via `JdbcTemplate` when direct `CallableStatement` access is needed

The following snippet illustrates **a method inside a class that has a `JdbcTemplate jdbcTemplate` field**; it is not a standalone Java file:

```java
public BigDecimal readTotalWithJdbcTemplate(long customerId) {
    return jdbcTemplate.execute(
            connection -> {
                CallableStatement call = connection.prepareCall(
                        "{call get_customer_total(?, ?)}");
                call.setLong(1, customerId);
                call.registerOutParameter(2, Types.DECIMAL);
                return call;
            },
            (org.springframework.jdbc.core.CallableStatementCallback<BigDecimal>) call -> {
                call.execute();
                return call.getBigDecimal(2);
            });
}
```

You need imports for `java.math.BigDecimal`, `java.sql.CallableStatement`, `java.sql.Types`, and an existing `JdbcTemplate` field. `JdbcTemplate` acquires/releases the JDBC connection and statement according to Spring's mechanism and translates `SQLException` into `DataAccessException`; when using the proper `DataSource` with a transaction manager, the connection participates in the active transaction.

**Do not open a new `DriverManager.getConnection(...)` inside a `@Transactional` Spring service** and assume it joins Spring's transaction. Let `JdbcTemplate`/`DataSourceUtils` use the configured `DataSource` and transaction manager.

## 7. Transactions and privileges: where does the routine run?

Calling a procedure via JDBC does not automatically create its own transaction boundary. For most DML operations, the transaction still depends on the connection, auto-commit mode, RDBMS configuration, and transaction manager.

Example in a Spring service:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerReportService {
    private final CustomerRoutineRepository repository;

    public CustomerReportService(CustomerRoutineRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public BigDecimal readCustomerTotal(long customerId) {
        return repository.customerTotal(customerId);
    }
}
```

This is a **class running inside a Spring project** with the repository above and an appropriate transaction manager. `@Transactional(readOnly = true)` signals read-only intent, which can help the framework/driver optimize; it is **not an absolute safeguard** preventing every stored procedure from writing data on every RDBMS. The routine in the example is read-only. For routines that write data, choose an appropriate transaction setting and design rollback/exception handling clearly.

Practical notes:

- MySQL **stored procedures can contain transaction control statements** under supported conditions; `COMMIT`/DDL statements inside a routine can affect how the outer call rolls back. Do not assume `@Transactional` will undo work that the database has already committed independently.
- MySQL stored functions are more restricted than procedures regarding transactions and result sets. Supported capabilities vary by RDBMS.
- The **`EXECUTE`** privilege is required to call a routine, in addition to connection privileges and depending on security modes such as `SQL SECURITY DEFINER`/`INVOKER`. Do not grant overly broad database privileges just to make a call work.
- When Spring catches a `DataAccessException`, inspect the root cause/`SQLState`/vendor error code to understand missing privileges, nonexistent routines, mismatched parameter types, deadlocks, or business errors.

## 8. Common errors and how to diagnose them

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Calling `{call ...}` but driver reports routine not found | Wrong schema, routine name, `EXECUTE` privilege, or connected to wrong DB | Verify JDBC URL, schema, `SHOW PROCEDURE STATUS`/metadata, and privileges |
| Error “OUT parameter not registered” | Missing `registerOutParameter` before `execute()` | Declare the correct index and `Types` |
| Receiving wrong output from a function | Forgetting that the return parameter occupies position 1 in `{? = call function(?)}` | Sketch an index diagram and bind/read the exact positions |
| `getInt()` returns 0 when data might be null | Integer getter uses a primitive type | Call `wasNull()` immediately after the getter |
| `execute()` returns `false` and is treated as an error | Confusing the first-result boolean with success status | Check `SQLException`, `OUT` values, and `getUpdateCount()` per the contract |
| Procedure returns multiple result sets but data is lost | Reading only one result set and closing the statement | Loop with `getMoreResults()` and check update counts |
| Spring fails to map outputs correctly | Name/case mismatch or insufficient driver metadata | Configure `SimpleJdbcCall` with explicit parameter declarations and verify output keys |
| Transaction failures or unexpected rollback behavior | Routine commits on its own, DDL triggers implicit commit, or connection is outside Spring's transaction | Inspect routine code, transaction manager configuration, and connection boundaries |
| Slow execution despite using a procedure | Unoptimized SQL inside the routine; repeated `prepareCall`/metadata round trips | Measure query plans, I/O, and DB/app latency; configure and reuse calls appropriately |

### Meaningful tests

- **Valid input:** with `customerId = 42`, total is `150.50`; `with_ten_percent_fee` returns `165.55`; `increment_number(7)` returns `8`.
- **Input with no data:** `get_customer_total(12345)` returns `0.00` because of `COALESCE`, unlike procedures that may return `NULL`.
- **INOUT:** verify before and after values, including `0` or negative values if the routine allows them.
- **OUT NULL:** test against a routine that can genuinely return `NULL`; verify that object getters or `wasNull()` handle it properly.
- **Missing privileges/wrong routine name:** verify that errors are logged and Spring translates exceptions appropriately.
- **Transactions:** for routines performing DML, experimentally test commit/rollback on the actual target RDBMS/driver to verify side effects roll back according to the expected contract.
- **Metadata:** retest `SimpleJdbcCall` when upgrading the driver version, renaming parameters, or changing schemas.

Unit tests that only mock `CallableStatement` can verify the order of `set`, `register`, `execute`, and `get`; integration tests against a real database are what show how the routine actually executes and what values it returns.

## 9. Common misconceptions

**“`CallableStatement` is a faster version of `PreparedStatement`?”** No. It is the appropriate interface for **calling stored procedures/functions** and exchanging output parameters. Speed depends on SQL, driver, network, execution plans, and routine design.

**“Functions must be called through `CallableStatement`?”** No. In MySQL, a function can be used inside an SQL expression, such as `SELECT with_ten_percent_fee(?)` with `PreparedStatement`. `CallableStatement` is useful when you want the JDBC callable form and to receive the return parameter through a standard API, if supported by the driver.

**“A procedure always returns a `ResultSet`?”** No. It may return no result sets, multiple result sets, `OUT` parameters, or provide an update count.

**“Using `SimpleJdbcCall` means I no longer need to understand JDBC?”** No. You still need to understand parameters, SQL types, metadata, output names, transactions, and how the database reports errors.

**“A stored procedure is always an atomic transaction?”** No. Statement batches inside a routine, transactions, auto-commit, and error-handling mechanisms are separate concepts; rollback behavior depends on the DBMS and routine code.

**“Can I take a user-supplied procedure name and concatenate it into SQL?”** No, you shouldn't. `?` placeholders are for **parameter values**, not for arbitrarily substituting routine names or identifiers. Use an application-defined allowlist of valid routines and least-privilege permissions rather than concatenating arbitrary identifiers from untrusted input.

## 10. Takeaways and official documentation

Basic JDBC sequence when calling a procedure with outputs:

`prepareCall` → `setXxx(IN/INOUT)` → `registerOutParameter(OUT/INOUT)` → `execute` → process result sets/update counts (if any) → `getXxx(OUT)` → close resources.

In Spring, `SimpleJdbcCall` fits routine calls with a clear parameter contract; `JdbcTemplate.execute(...)` fits cases needing fine-grained JDBC result control. Before moving logic into the database, weigh shared reuse, operational cost, portability, and testability.

Reference documentation:

- Java SE 17 `CallableStatement`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/CallableStatement.html
- Java SE 17 `Connection.prepareCall`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html
- Spring Framework, *Simplifying JDBC Operations with the SimpleJdbc Classes*: https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html
- MySQL 8.4, *CREATE PROCEDURE and CREATE FUNCTION Statements*: https://dev.mysql.com/doc/refman/8.4/en/create-procedure.html
- MySQL Connector/J, *Using JDBC CallableStatements to Execute Stored Procedures*: https://dev.mysql.com/doc/connector-j/en/connector-j-usagenotes-statements-callable.html