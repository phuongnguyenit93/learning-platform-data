# Connection, Statement, PreparedStatement, and CallableStatement

Oracle JDBC is the bridge between Java applications and Oracle Database. JDBC provides standard interfaces to open connections, send SQL, pass parameters, read results, and invoke stored procedures in the database. The four most important interfaces in this section are `Connection`, `Statement`, `PreparedStatement`, and `CallableStatement`.

They relate to one another in a common usage flow:

```text
Java application
      |
      v
DataSource / DriverManager
      |
      v
Connection
      |
      +---- createStatement() ------> Statement
      |
      +---- prepareStatement(sql) --> PreparedStatement
      |
      +---- prepareCall(sql) -------> CallableStatement
                                         |
                                         v
                                  ResultSet / OUT values
```

`Connection` represents a working session with the database. From a connection, the application creates a statement object suited to the type of SQL to execute. Query statements can return a `ResultSet`; DML can return the number of affected rows; procedures can return results via `OUT`, `IN OUT`, or `REF CURSOR` parameters.

## 1. Preparing Oracle JDBC and database connectivity

### 1.1. JDBC driver

The Oracle JDBC driver implements JDBC interfaces so Java communicates with Oracle Database. The Thin driver is commonly used in applications because it connects directly over Oracle Net without requiring a full Oracle Client installation on the application host.

Applications need an `ojdbc` dependency matching the Java version and deployment environment. The Maven configuration example below illustrates declaring the dependency; manage the version through the project's dependency management and choose an artifact compatible with the JDK in use:

```xml
<dependency>
    <groupId>com.oracle.database.jdbc</groupId>
    <artifactId>ojdbc11</artifactId>
    <version>${oracle.jdbc.version}</version>
</dependency>
```

The artifact name and driver version should be selected based on the JDK, Oracle Database, and required features. Do not copy a random version from an example and use it for every environment.

With modern JDBC, the driver is typically registered automatically via the service provider mechanism. Therefore, applications generally no longer need to call `Class.forName("oracle.jdbc.OracleDriver")`. If using an older environment or special classloader configuration, check the corresponding driver documentation.

### 1.2. Service-name JDBC URL

Oracle Thin URLs commonly use the service name form:

```text
jdbc:oracle:thin:@//dbhost.example.com:1521/orclpdb.example.com
```

Components:

- `jdbc:oracle:thin:`: uses the Oracle Thin JDBC driver.
- `dbhost.example.com`: database server hostname or address.
- `1521`: listener port in the example.
- `orclpdb.example.com`: service name published by the listener.

In production applications, use the service name corresponding to the PDB or database service; do not infer the service from the SID. The legacy SID URL format has a different syntax and should not be confused with the service name form.

### 1.3. Opening a simple connection with DriverManager

`DriverManager` is suitable for small examples, command-line programs, or test tools. Example:

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class OracleConnectionExample {
    private static final String URL =
        "jdbc:oracle:thin:@//dbhost.example.com:1521/orclpdb.example.com";

    public static void main(String[] args) throws SQLException {
        String username = System.getenv("DB_USERNAME");
        String password = System.getenv("DB_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(URL, username, password)) {
            System.out.println("Connected: " + !connection.isClosed());
        }
    }
}
```

`getConnection` returns a `Connection` if the connection succeeds; if it fails, JDBC throws `SQLException`. The example reads credentials from environment variables to avoid hardcoding passwords in source code. For real systems, use a secret manager or credential mechanism managed by the deployment platform. Environment variables are only a simple example and still need protection.

### 1.4. Using DataSource in real applications

`DataSource` is the recommended way to obtain connections in server applications. It separates connection configuration from code and can integrate with a connection pool, JNDI, or Oracle Universal Connection Pool (UCP).

Example using a `DataSource` configured by an application server or dependency injection:

```java
import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.SQLException;

public class CustomerRepository {
    private final DataSource dataSource;

    public CustomerRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public void checkConnection() throws SQLException {
        try (Connection connection = dataSource.getConnection()) {
            // Perform database operations within this connection scope.
        }
    }
}
```

In a pooled environment, `dataSource.getConnection()` usually borrows a connection managed by the pool. Calling `close()` returns the connection to the pool for reuse rather than necessarily closing the physical connection to the database. Therefore, still close connections with try-with-resources after every unit of work.

Do not create a single global `Connection` and share it arbitrarily across all requests or threads. Connections carry transaction state, session settings, and cursors; concurrent sharing can mix transactions and cause unpredictable errors. Each unit of work should borrow a connection according to pool conventions.

## 2. Connection

### 2.1. Role of Connection

`java.sql.Connection` represents a JDBC connection/session to the database. It is the starting point to:

- Create `Statement`, `PreparedStatement`, and `CallableStatement`.
- Manage transactions via `commit`, `rollback`, and `setAutoCommit`.
- Configure isolation level, read-only hint, schema, and certain session properties.
- Create `Savepoint`s.
- Retrieve metadata about the database and driver.
- Close or return the connection to the pool.

A connection typically corresponds to one database session for the duration it is borrowed. A session can hold state such as an open transaction, NLS settings, current schema, package state, and temporary objects depending on configuration.

### 2.2. Default auto-commit

Per JDBC, a new connection usually has `autoCommit = true`. In this mode, each SQL statement is committed automatically upon completion. You can inspect or change it:

```java
boolean autoCommit = connection.getAutoCommit();
connection.setAutoCommit(false);
```

When `autoCommit` is `false`, the application is responsible for ending the transaction with `commit()` or `rollback()`.

### 2.3. Transaction example with Connection

Suppose you need to debit account A and credit account B. Both operations must succeed together or fail together:

```java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.SQLException;

public class TransferService {
    public void transfer(
            Connection connection,
            long fromAccount,
            long toAccount,
            BigDecimal amount) throws SQLException {

        boolean previousAutoCommit = connection.getAutoCommit();
        connection.setAutoCommit(false);

        try {
            try (PreparedStatement debit = connection.prepareStatement(
                    "UPDATE accounts SET balance = balance - ? " +
                    "WHERE account_id = ? AND balance >= ?")) {
                debit.setBigDecimal(1, amount);
                debit.setLong(2, fromAccount);
                debit.setBigDecimal(3, amount);

                int debited = debit.executeUpdate();
                if (debited != 1) {
                    throw new SQLException("Insufficient funds or source account missing");
                }
            }

            try (PreparedStatement credit = connection.prepareStatement(
                    "UPDATE accounts SET balance = balance + ? " +
                    "WHERE account_id = ?")) {
                credit.setBigDecimal(1, amount);
                credit.setLong(2, toAccount);

                int credited = credit.executeUpdate();
                if (credited != 1) {
                    throw new SQLException("Destination account not found");
                }
            }

            connection.commit();
        } catch (SQLException | RuntimeException ex) {
            try {
                connection.rollback();
            } catch (SQLException rollbackError) {
                ex.addSuppressed(rollbackError);
            }
            throw ex;
        } finally {
            connection.setAutoCommit(previousAutoCommit);
        }
    }
}
```

The example focuses on transaction boundaries. In real code, clearly define who owns the connection and who is responsible for committing. If the connection is managed by a framework's transaction manager, the repository should not arbitrarily commit or change `autoCommit`; the transaction manager must control the transaction lifecycle.

Note that Oracle DDL such as `CREATE`, `ALTER`, or `DROP` performs an implicit commit per Oracle rules. Do not mix DDL with DML in a single transaction expecting `rollback()` to undo all DDL.

### 2.4. Savepoint

Savepoints allow rolling back a portion of work within a transaction:

```java
import java.sql.Savepoint;

connection.setAutoCommit(false);

try {
    updateOrder(connection);
    Savepoint beforeOptionalStep = connection.setSavepoint("BEFORE_OPTIONAL");

    try {
        applyOptionalDiscount(connection);
    } catch (SQLException optionalFailure) {
        connection.rollback(beforeOptionalStep);
    }

    connection.commit();
} catch (SQLException ex) {
    connection.rollback();
    throw ex;
}
```

After `rollback(savepoint)`, operations before the savepoint remain in the transaction; operations after the savepoint are undone. Savepoints do not replace clear transaction design and should not be used to mask business errors.

### 2.5. Transaction isolation

Oracle defaults to `READ COMMITTED`: each SQL statement sees data committed as of the time the statement began, following Oracle's read consistency mechanism. Oracle also supports `SERIALIZABLE` and read-only transactions with the corresponding syntax.

JDBC can set the isolation level:

```java
connection.setTransactionIsolation(Connection.TRANSACTION_READ_COMMITTED);
```

Or:

```java
connection.setTransactionIsolation(Connection.TRANSACTION_SERIALIZABLE);
```

Do not assume every JDBC isolation level is supported identically by Oracle. Oracle does not provide `READ UNCOMMITTED` in the manner of some other databases. `Connection.setReadOnly(true)` is a hint to the driver/DBMS and should not be treated as a security authorization mechanism. If an Oracle read-only transaction is required, use the corresponding transaction mechanism and verify syntax by version.

`SERIALIZABLE` can lead to serialization errors when a transaction cannot continue safely, such as `ORA-08177`. Applications need a bounded retry policy for transactions that can be safely re-executed.

### 2.6. Metadata and connection status

Some useful APIs:

```java
DatabaseMetaData metadata = connection.getMetaData();
System.out.println(metadata.getDatabaseProductName());
System.out.println(metadata.getDatabaseProductVersion());
System.out.println(metadata.getDriverName());

boolean valid = connection.isValid(5);
```

`isValid(timeout)` checks whether a connection is still valid via the driver's mechanism. In server applications, the connection pool should have proper validation; do not manually run a ping query before every SQL statement if the pool already manages validation effectively.

## 3. Statement

### 3.1. When is Statement used?

`Statement` executes SQL that does not need bind parameters. It fits static statements, such as fixed queries or certain administrative commands. Example:

```java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public void listStatuses(Connection connection) throws SQLException {
    String sql = "SELECT status_code, status_name FROM order_status";

    try (Statement statement = connection.createStatement();
         ResultSet resultSet = statement.executeQuery(sql)) {

        while (resultSet.next()) {
            System.out.println(
                resultSet.getString("status_code") + " - " +
                resultSet.getString("status_name")
            );
        }
    }
}
```

`createStatement()` creates a statement bound to the connection. `executeQuery()` is used for queries returning a `ResultSet`. `ResultSet` is a cursor for reading each row of results; call `next()` to advance to the next row.

### 3.2. Execution methods

| Method | Used for | Result |
|---|---|---|
| `executeQuery(sql)` | Queries returning data, usually `SELECT`. | `ResultSet`. |
| `executeUpdate(sql)` | `INSERT`, `UPDATE`, `DELETE`, and some DDL. | Number of affected rows; typically 0 for DDL. |
| `execute(sql)` | When it is unknown whether the result is a ResultSet or update count, or for generic result handling. | `true` if the first result is a ResultSet, `false` if it is an update count or there are no results. |
| `addBatch(sql)` / `executeBatch()` | Grouping multiple static statements for batch execution. | Array of update counts. |

DML example with `Statement`:

```java
try (Statement statement = connection.createStatement()) {
    int updated = statement.executeUpdate(
        "UPDATE app_settings SET setting_value = 'ON' " +
        "WHERE setting_name = 'FEATURE_X'"
    );
    System.out.println("Rows updated: " + updated);
}
```

This example uses a fixed SQL string. When values come from users or dynamic data, prefer `PreparedStatement` to bind parameters.

### 3.3. Limitations and risks

`Statement` does not provide bind parameters. If input strings are concatenated into SQL, the application risks SQL injection:

```java
// Unsafe: userInput can alter the SQL structure.
String sql = "SELECT * FROM users WHERE username = '" + userInput + "'";
try (Statement statement = connection.createStatement()) {
    ResultSet rs = statement.executeQuery(sql);
}
```

Beyond injection risk, string concatenation makes the SQL text change for each value, making cursor reuse and statement tracking harder. Use `PreparedStatement` to separate SQL from data values.

## 4. PreparedStatement

### 4.1. What is PreparedStatement?

`PreparedStatement` is a statement with bind parameters, created from SQL containing `?` placeholders. The application sets values for each position using `setXxx()` methods and then executes it.

Example:

```java
String sql = "SELECT customer_id, customer_name " +
             "FROM customers WHERE customer_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String name = rs.getString("customer_name");
            System.out.println(name);
        }
    }
}
```

Bind positions start at 1, not 0. The `?` placeholder represents a value, not a table name, column name, SQL keyword, or arbitrary expression fragment.

### 4.2. Why are bind variables important?

Bind variables help:

- Separate input data from SQL structure, reducing SQL injection risk.
- Avoid manually escaping quotes and special characters in values.
- Allow the database to reuse cursors/SQL statements when SQL has the same structure and fits cursor sharing mechanisms.
- Pass values with explicit data types, such as numbers, dates/times, decimals, or binary data.

Bind variables do not automatically make every query faster in all cases. Execution plans still depend on statistics, bind peeking, adaptive cursor sharing, selectivity, and Oracle version. However, binding is usually the right choice for dynamic data values.

### 4.3. Common bind types

| Method | Common Java type | Guidance |
|---|---|---|
| `setString()` | `String` | `VARCHAR2`, `CHAR`; mind length and character semantics. |
| `setNString()` | `String` | National character columns like `NVARCHAR2` when needed. |
| `setInt()`, `setLong()` | `int`, `long` | Integer values. |
| `setBigDecimal()` | `BigDecimal` | `NUMBER` requiring decimal precision. |
| `setDate()` | `java.sql.Date` | JDBC date; note Oracle `DATE` also stores time. |
| `setTimestamp()` | `java.sql.Timestamp` | Oracle `DATE`/`TIMESTAMP` when preserving time components. |
| `setBoolean()` | `boolean` | Check target type and version/driver support; traditional Oracle SQL lacks a SQL BOOLEAN type in all contexts. |
| `setBytes()` | `byte[]` | Binary data of suitable size. |
| `setBinaryStream()` | `InputStream` | Large binary data. |
| `setCharacterStream()` | `Reader` | Long text/CLOB. |

Date/time bind example:

```java
String sql = "SELECT order_id, order_date " +
             "FROM orders WHERE order_date >= ? AND order_date < ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setTimestamp(1, startTimestamp);
    ps.setTimestamp(2, endTimestamp);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process each row.
        }
    }
}
```

Oracle `DATE` stores both date and time down to the second. If `java.sql.Date` is used for an Oracle `DATE` column, the time component may not be represented as intended. When time matters, consider `Timestamp` or a driver-supported Java time API, and test timezone/precision explicitly. For `TIMESTAMP WITH TIME ZONE`, choose a mapping type that preserves offset/region as required.

### 4.4. Binding NULL properly

If a value may be `null`, use `setNull(index, sqlType)` or `setObject` with the appropriate type:

```java
if (middleName == null) {
    ps.setNull(2, java.sql.Types.VARCHAR);
} else {
    ps.setString(2, middleName);
}
```

Do not concatenate the literal word `NULL` into SQL. SQL `NULL` is a special value with distinct semantics; comparisons against `NULL` must use `IS NULL` or `IS NOT NULL`, not `= NULL`.

### 4.5. Bind parameters cannot replace table or column names

The following does not work as expected:

```java
PreparedStatement ps = connection.prepareStatement(
    "SELECT * FROM ? WHERE customer_id = ?"
);
ps.setString(1, "CUSTOMERS");
ps.setLong(2, customerId);
```

The first bind is a value; it cannot substitute for the identifier `CUSTOMERS`. If a table or column name must vary by request, use a fixed allowlist controlled by the application:

```java
Set<String> allowedSortColumns = Set.of("ORDER_DATE", "TOTAL_AMOUNT");

if (!allowedSortColumns.contains(sortColumn)) {
    throw new IllegalArgumentException("Unsupported sort column");
}

String sql = "SELECT order_id, total_amount FROM orders ORDER BY " +
             sortColumn + " DESC";
```

Only concatenate an identifier after validating against the allowlist; filter values must still be bound with `?`. Never place client-supplied identifiers directly into SQL.

### 4.6. Reusing PreparedStatement

A `PreparedStatement` can be reused multiple times on the same connection by resetting bind values:

```java
String sql = "SELECT order_id FROM orders WHERE customer_id = ?";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (long customerId : customerIds) {
        ps.setLong(1, customerId);

        try (ResultSet rs = ps.executeQuery()) {
            while (rs.next()) {
                System.out.println(rs.getLong("order_id"));
            }
        }
    }
}
```

Close the `ResultSet` before re-executing the statement. Oracle JDBC's prepared statement caching can help reuse statements in some configurations, but do not rely on caching to skip closing resources.

### 4.7. Batch DML

When performing many operations with the same structure, `PreparedStatement` supports batching:

```java
String sql = "INSERT INTO audit_events(event_id, event_type, created_at) " +
             "VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    connection.setAutoCommit(false);

    for (AuditEvent event : events) {
        ps.setLong(1, event.id());
        ps.setString(2, event.type());
        ps.setTimestamp(3, event.createdAt());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
    connection.commit();
}
```

Batching reduces round trips and can improve throughput. However, very large batches can consume significant memory or create long transactions. Split batches into appropriate sizes, measure on representative data, and manage commits per business requirements.

The result of `executeBatch()` may contain updated row counts, `Statement.SUCCESS_NO_INFO`, or `Statement.EXECUTE_FAILED`. On error, JDBC may throw `BatchUpdateException` and provide update counts completed prior to the failure; how the driver executes batches and partial success semantics must be handled per driver documentation.

Batch error handling example:

```java
try {
    ps.executeBatch();
    connection.commit();
} catch (java.sql.BatchUpdateException ex) {
    connection.rollback();
    int[] updateCounts = ex.getUpdateCounts();
    // Log technical metrics; do not log sensitive data.
    throw ex;
}
```

If a transaction manager manages the connection, do not call `commit()`/`rollback()` directly inside the repository. Let a single consistent layer control transaction boundaries.

## 5. CallableStatement

### 5.1. Used to call stored procedures or functions

`CallableStatement` extends `PreparedStatement` to call stored procedures or functions. In Oracle, procedures/functions are commonly written in PL/SQL and may reside inside packages.

Call a procedure using JDBC escape syntax:

```java
CallableStatement cs = connection.prepareCall(
    "{call app_customer_pkg.update_status(?, ?)}"
);
```

Or use an anonymous PL/SQL block:

```java
CallableStatement cs = connection.prepareCall(
    "BEGIN app_customer_pkg.update_status(?, ?); END;"
);
```

JDBC escape syntax helps the driver process calls according to the JDBC standard. PL/SQL blocks are useful when invoking multiple operations or using Oracle-specific syntax.

### 5.2. IN parameters

`IN` parameters are passed similarly to `PreparedStatement`:

```java
String call = "{call app_customer_pkg.update_status(?, ?)}";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, customerId);
    cs.setString(2, "ACTIVE");
    cs.execute();
}
```

Parameter order must match the procedure signature. If a package overloads multiple procedures with the same name, bind types and order must be unambiguous enough for Oracle to resolve the right overload.

### 5.3. OUT parameters

For `OUT` parameters, register the SQL type before executing:

```java
String call = "{call app_customer_pkg.get_customer_name(?, ?)}";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, customerId);
    cs.registerOutParameter(2, java.sql.Types.VARCHAR);

    cs.execute();

    String customerName = cs.getString(2);
    System.out.println(customerName);
}
```

`registerOutParameter(2, Types.VARCHAR)` declares the second position as a string output. Only read the OUT value after the procedure has executed successfully.

### 5.4. IN OUT parameters

An `IN OUT` parameter both receives an input value and returns a new value:

```java
String call = "{call app_counter_pkg.increase_counter(?)}";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setInt(1, currentValue);
    cs.registerOutParameter(1, java.sql.Types.INTEGER);
    cs.execute();

    int updatedValue = cs.getInt(1);
}
```

The bind position is both set and registered as output. Java/SQL types must be compatible with the PL/SQL declaration.

### 5.5. Calling a function that returns a value

For a function, the first position is typically reserved for the return value:

```java
String call = "{? = call app_tax_pkg.calculate_tax(?)}";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.registerOutParameter(1, java.sql.Types.NUMERIC);
    cs.setBigDecimal(2, taxableAmount);
    cs.execute();

    BigDecimal tax = cs.getBigDecimal(1);
}
```

The parameter order is: return value first, followed by the function parameters. `NUMBER` is typically mapped to `BigDecimal` to preserve decimal precision.

### 5.6. REF CURSOR

An Oracle procedure can return a `REF CURSOR` so the application can read multiple rows. With a JDBC driver supporting `Types.REF_CURSOR`, for example:

```java
String call = "{call app_report_pkg.get_orders(?, ?)}";

try (CallableStatement cs = connection.prepareCall(call)) {
    cs.setLong(1, customerId);
    cs.registerOutParameter(2, java.sql.Types.REF_CURSOR);
    cs.execute();

    try (ResultSet rs = (ResultSet) cs.getObject(2)) {
        while (rs.next()) {
            long orderId = rs.getLong("ORDER_ID");
            BigDecimal amount = rs.getBigDecimal("TOTAL_AMOUNT");
            // Process result row.
        }
    }
}
```

Some older Oracle JDBC versions use `OracleTypes.CURSOR` from the Oracle extension package instead of `Types.REF_CURSOR`. Choose the registration method based on your JDK and driver. Close both `ResultSet` and `CallableStatement` after reading; cursors are database resources and should not be left open long.

### 5.7. When should stored procedures be used?

Stored procedures may be suitable when:

- Business logic needs to run close to the data and is shared across multiple applications.
- Multiple SQL operations need to be combined into one call to reduce round trips.
- Permissions are managed through `EXECUTE` on packages/procedures.
- Large data-processing workflows or logic require a clearly defined transaction boundary.

Do not convert every simple SQL statement into a stored procedure just because `CallableStatement` exists. Choose where to place logic based on maintainability, testability, authorization, and application deployment.

## 6. ResultSet and reading data

### 6.1. ResultSet is a cursor

`ResultSet` maintains a pointer to the query's result set. Initially the cursor sits before the first row; `next()` moves to the next row and returns `false` when no rows remain.

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT employee_id, first_name, salary FROM employees WHERE department_id = ?")) {
    ps.setInt(1, departmentId);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            long id = rs.getLong("EMPLOYEE_ID");
            String name = rs.getString("FIRST_NAME");
            BigDecimal salary = rs.getBigDecimal("SALARY");
        }
    }
}
```

Columns can be read by 1-based index or by column label. Using labels is usually easier to read and less coupled to column order. If a query has two columns with the same label, give them explicit aliases.

### 6.2. Handling SQL NULL

Primitive getters such as `getInt()` or `getLong()` return 0 when the SQL value is `NULL`. To distinguish `NULL` from 0, call `wasNull()` immediately after the getter:

```java
long managerId = rs.getLong("MANAGER_ID");
if (rs.wasNull()) {
    // MANAGER_ID is SQL NULL.
}
```

For object types such as `getBigDecimal()` or `getString()`, JDBC normally returns `null` if the SQL value is `NULL`.

### 6.3. ResultSet type and concurrency

By default, statements typically create forward-only, read-only ResultSets. Other types can be requested:

```java
Statement statement = connection.createStatement(
    ResultSet.TYPE_FORWARD_ONLY,
    ResultSet.CONCUR_READ_ONLY
);
```

Not every ResultSet type is fully supported by every driver or database. Scrollable or updatable ResultSets can be resource-intensive and have limitations; in Oracle applications, it is usually better to use explicit queries and separate DML rather than relying on cursor-based updates.

### 6.4. Fetch size and multi-row queries

JDBC allows hinting how many rows to fetch per trip from the database:

```java
ps.setFetchSize(500);
```

A larger fetch size can reduce round trips when reading many rows, at the cost of higher client-side memory usage. The right value depends on row width, network latency, row count, and heap limits. Oracle JDBC also has a row prefetch mechanism; fetch size and prefetch settings should be understood per driver version. Measure performance with realistic data instead of setting a huge value for every query.

If a query may return millions of rows, consider filtering, keyset pagination, streaming, or batch processing. Never hold a `ResultSet` and connection open while the application waits for user interaction.

### 6.5. Reading LOBs via streams

For large CLOBs/BLOBs, you do not need to load the entire content into memory. Streams can be used:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT document_content FROM documents WHERE document_id = ?")) {
    ps.setLong(1, documentId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            try (java.io.Reader reader = rs.getCharacterStream("DOCUMENT_CONTENT")) {
                char[] buffer = new char[8192];
                int count;
                while ((count = reader.read(buffer)) != -1) {
                    // Write or process each chunk.
                }
            }
        }
    }
}
```

LOB streams typically depend on the ResultSet/connection staying open. Consume the stream before closing the cursor and connection, and handle IOException alongside SQLException.

## 7. Resource management with try-with-resources

`Connection`, `Statement`, `PreparedStatement`, `CallableStatement`, and `ResultSet` are all resources that must be closed. The safest and cleanest way is try-with-resources:

```java
String sql = "SELECT customer_id, customer_name FROM customers WHERE status = ?";

try (Connection connection = dataSource.getConnection();
     PreparedStatement ps = connection.prepareStatement(sql)) {

    ps.setString(1, "ACTIVE");

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process results.
        }
    }
}
```

When exiting the block, Java automatically closes resources in reverse order of declaration. Closing a statement also closes its current ResultSet; however, declaring ResultSet separately clarifies ownership and ensures timely cursor closure.

Do not close connections only when exceptions occur. Leaking ResultSets or statements can keep cursors, sessions, and server resources held longer than needed. With connection pools, leaking connections can exhaust the pool and force other requests to wait.

## 8. Handling SQLException

### 8.1. Information inside SQLException

`SQLException` can provide:

- `getMessage()`: error message.
- `getSQLState()`: SQL state code per the driver.
- `getErrorCode()`: vendor error code; with Oracle, typically the numeric error code.
- `getNextException()`: next error in the exception chain.
- `getCause()`: root cause if present.

Example:

```java
try (PreparedStatement ps = connection.prepareStatement(
        "SELECT customer_id FROM customers WHERE customer_id = ?")) {
    ps.setLong(1, customerId);
    ps.executeQuery();
} catch (SQLException ex) {
    System.err.println("SQLState: " + ex.getSQLState());
    System.err.println("Vendor code: " + ex.getErrorCode());
    System.err.println("Message: " + ex.getMessage());

    for (SQLException next = ex.getNextException();
         next != null;
         next = next.getNextException()) {
        System.err.println("Next SQL error: " + next.getMessage());
    }
    throw ex;
}
```

In production, use a logging framework and correlation IDs; avoid logging passwords, tokens, sensitive bind values, or full customer data. SQL details and error codes can be helpful for investigations, but read access to logs must be controlled.

### 8.2. Error classification and retries

Do not retry every `SQLException`. Syntax errors, missing privileges, or constraint violations will not resolve themselves on retry. Transient network errors or transaction serialization conflicts may be retried in certain cases, but you must determine whether the transaction can be safely re-executed.

A retry policy should:

- Limit retry count and use backoff.
- Only retry errors classified as transient.
- Roll back the failed transaction before retrying.
- Ensure operations are idempotent or protected by deduplication keys.
- Never retry a payment/write operation when it is unknown whether the previous attempt committed.

## 9. Choosing the right interface for each scenario

| Interface | When to use | Key reminders |
|---|---|---|
| `Connection` | Managing sessions, transactions, and creating statements. | One connection per unit of work; close/return to pool promptly. |
| `Statement` | Static SQL with no dynamic input values. | Never concatenate user input into SQL. |
| `PreparedStatement` | Parameterized SQL, repeated queries/DML, batching. | Use `?` and `setXxx`; binds do not replace identifiers. |
| `CallableStatement` | Calling PL/SQL procedures/functions, OUT or REF CURSOR. | Register OUT parameters before execute; manage returned cursors. |

Practical rule: if SQL contains data values from outside, prefer `PreparedStatement`; if calling defined PL/SQL logic, use `CallableStatement`; only use `Statement` for controlled static SQL.

## 10. Complete combined example

Example repository reading a customer with `PreparedStatement`, then calling a procedure to fetch the order count with `CallableStatement`. `DataSource` is injected from application configuration:

```java
import javax.sql.DataSource;
import java.sql.CallableStatement;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;

public class CustomerService {
    private final DataSource dataSource;

    public CustomerService(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public CustomerSummary loadSummary(long customerId) throws SQLException {
        String name;
        int orderCount;

        try (Connection connection = dataSource.getConnection()) {
            String query =
                "SELECT customer_name FROM customers WHERE customer_id = ?";

            try (PreparedStatement ps = connection.prepareStatement(query)) {
                ps.setLong(1, customerId);

                try (ResultSet rs = ps.executeQuery()) {
                    if (!rs.next()) {
                        return null;
                    }
                    name = rs.getString("CUSTOMER_NAME");
                }
            }

            String call = "{call app_order_pkg.get_order_count(?, ?)}";
            try (CallableStatement cs = connection.prepareCall(call)) {
                cs.setLong(1, customerId);
                cs.registerOutParameter(2, Types.INTEGER);
                cs.execute();
                orderCount = cs.getInt(2);
            }
        }

        return new CustomerSummary(customerId, name, orderCount);
    }
}
```

`CustomerSummary` is an application-defined DTO. The example uses a single connection for two read operations, closes each statement/result set immediately after use, and closes the connection upon completion. If the two operations must see the same consistent snapshot or belong to a single business transaction, configure appropriate transaction/isolation settings rather than relying on defaults.

## 11. Oracle JDBC and specific caveats

### 11.1. NUMBER and precision

Oracle `NUMBER` can represent decimal numbers with high precision. For currency or values requiring exact precision, use `BigDecimal` and `setBigDecimal()`/`getBigDecimal()` instead of `double`/`float`, since floating point can introduce binary rounding errors.

### 11.2. DATE and TIMESTAMP

Oracle `DATE` stores year, month, day, hour, minute, and second; it is not strictly equivalent to `java.sql.Date`, which represents only a date under JDBC semantics. If time must be preserved, use appropriate mappings such as `Timestamp` or driver-supported Java time APIs. For `TIMESTAMP WITH TIME ZONE` and `TIMESTAMP WITH LOCAL TIME ZONE`, understand database/session timezone rules and how the driver converts them.

### 11.3. LOBs and streaming

For large CLOBs/BLOBs, prefer streaming instead of loading the entire value into a `String` or `byte[]`. LOB locators and streams may depend on the connection/cursor staying open. Close resources in the proper order and do not pass streams outside the connection's lifetime.

### 11.4. REF CURSOR

Oracle PL/SQL often uses `SYS_REFCURSOR` to return result sets. Modern JDBC drivers can support `Types.REF_CURSOR`; older drivers may require `OracleTypes.CURSOR`. Check your JDK and `ojdbc` version before choosing the API.

### 11.5. Statement caching and fetch behavior

Oracle JDBC can support implicit statement caching and row prefetching. Pool/driver configuration can affect statement reuse and how many rows are fetched per round trip. Avoid enabling caches or setting fetch sizes too high without measuring actual memory, cursors, and workload.

### 11.6. TCPS and wallets

JDBC connections can use TCPS and Oracle wallets to protect transport or authenticate per configuration. URLs, trust material, certificates, and wallets must be managed under security policy; never disable certificate checking just to make a connection work.

## 12. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `SQLException: No suitable driver` | Missing `ojdbc` or dependency absent from runtime classpath. | Check dependencies, packaging, and classloader. |
| `ORA-01017` | Wrong username/password or connected to wrong service. | Verify credentials, service name, and secret source. |
| `ORA-28000` / `ORA-28001` | Account locked or password expired. | Check user/profile status and DBA procedures. |
| `ORA-12514` | Listener does not recognize service in connect descriptor. | Verify service name, listener registration, and URL. |
| `ORA-12170` | Connection timed out. | Check network, firewall, listener, and configured timeouts. |
| `ORA-00942` | Table/view does not exist in resolved schema or missing privilege. | Check owner, synonyms, current schema, and grants. |
| `ORA-01008` | Missing bind variable. | Check number of `?` placeholders and all `setXxx` positions. |
| `ORA-01722` | Invalid string-to-number conversion. | Bind the right type, inspect data and implicit conversions. |
| `ORA-00001` | Unique constraint violation. | Identify duplicate key; do not retry blindly. |
| `ORA-08177` | Serializable transaction cannot continue due to conflict. | Roll back and consider bounded retry if business logic permits. |
| Connection pool exhausted | Leaked connections, transactions held too long, or pool too small. | Use try-with-resources, monitor borrow time, and adjust pool config. |

When investigating, record the Oracle error code, SQLState, timestamp, service, and correlation ID. Never write passwords or sensitive data into logs.

## 13. Best practice guidelines

- Use `DataSource` and connection pools in server applications; use `DriverManager` mainly for examples or simple tools.
- Borrow a connection for a single unit of work and always close/return it to the pool promptly.
- Use try-with-resources for connections, statements, callable statements, and result sets.
- Use `PreparedStatement` for dynamic values; never concatenate user data into SQL.
- Bind the right data types, especially for `NUMBER`, dates/times, `NULL`, and LOBs.
- Use `CallableStatement` for procedures/functions and register OUT parameters with the right position/type.
- Manage transactions in one consistent layer; do not let multiple layers commit/rollback arbitrarily.
- Size batches sensibly and handle `BatchUpdateException`.
- Close ResultSets before reusing statements or returning connections to the pool.
- Set fetch size based on actual data and latency; avoid loading huge results into heap.
- Classify SQLException before retrying; retried operations must be safe or idempotent.
- Never share a connection concurrently across threads.
- Verify compatibility across JDK, Oracle JDBC driver, and Oracle Database.

## Conclusion

`Connection` manages sessions and transactions; `Statement` executes static SQL; `PreparedStatement` passes values via bind parameters; `CallableStatement` invokes procedures/functions and receives results via OUT parameters or REF CURSORs. Choosing the right interface keeps code maintainable, reduces SQL injection risk, and improves resource control. Combining `DataSource`/connection pooling, try-with-resources, clear transaction boundaries, proper type binding, and intentional error handling allows Java applications to work reliably and securely with Oracle Database.
