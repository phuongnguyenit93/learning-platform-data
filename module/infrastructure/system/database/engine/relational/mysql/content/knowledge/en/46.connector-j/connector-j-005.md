# Connection, Statement, PreparedStatement, and CallableStatement

MySQL Connector/J is the JDBC driver that enables Java applications to connect to and interact with MySQL. JDBC defines standard interfaces such as Connection, Statement, PreparedStatement, CallableStatement, and ResultSet; Connector/J provides the implementations that let these interfaces communicate with MySQL Server.

Choosing the right statement type directly affects SQL safety, statement reusability, parameter binding, and result handling. Statement fits static SQL with no parameters; PreparedStatement fits queries with input data; CallableStatement is for stored procedures or stored functions. All three operate over a Connection and must be closed properly.

This lesson belongs to the **Connector/J** chapter of the DATABASE_MYSQL module. The module covers table design, data types, keys, SQL queries, indexes, transactions, concurrency control, query optimization, authorization, backups, and relational database operations. Examples use modern Java JDBC and MySQL Connector/J; cross-check against the documentation of your project's actual Connector/J and JDK versions.

After this lesson, you will be able to:

- Create and manage a Connection to MySQL using JDBC.
- Distinguish Statement, PreparedStatement, and CallableStatement.
- Bind data types properly and handle NULL values.
- Read ResultSets, update counts, and generated keys.
- Execute controlled batches and transactions.
- Call stored procedures/functions with IN, OUT, and INOUT parameters.
- Handle SQLExceptions, bounded retries, and resource management.
- Choose Connector/J settings suitable for TLS, connection pools, and workloads.

## 1. Role of JDBC and Connector/J

JDBC is Java's standard API for accessing relational databases. Applications invoke interfaces in the java.sql and javax.sql packages; the driver translates those calls into the database-specific protocol.

Common components:

| Component | Role |
|---|---|
| DriverManager | Creates a connection from a JDBC URL and credentials. |
| DataSource | Recommended way to obtain connections in applications; can be wrapped by a connection pool. |
| Connection | Represents a session with MySQL, manages transactions, and creates statements. |
| Statement | Executes SQL without parameter binding. |
| PreparedStatement | Executes SQL with placeholders and binds values by position. |
| CallableStatement | Calls stored procedures or stored functions and registers OUT parameters. |
| ResultSet | Reads rows and columns returned by a query. |
| SQLException | Carries JDBC error details, SQLState, and driver/server error codes. |

Modern Connector/J self-registers the JDBC driver through Java's service provider mechanism. In typical applications, there is no need to call Class.forName to load the driver manually. The current driver class is com.mysql.cj.jdbc.Driver; the old class name com.mysql.jdbc.Driver belongs to very old Connector/J versions and should not be used in new code.

## 2. Adding Connector/J to a Project

If the project uses Maven, declare the Connector/J dependency. Choose a version tested and compatible with your project's JDK and MySQL Server.

~~~xml
<dependency>
  <groupId>com.mysql</groupId>
  <artifactId>mysql-connector-j</artifactId>
  <version>VERSION_APPROVED_BY_PROJECT</version>
</dependency>
~~~

Replace VERSION_APPROVED_BY_PROJECT with a specific project-approved version; do not leave this placeholder string in a real build file.

If using Gradle:

~~~gradle
dependencies {
    runtimeOnly("com.mysql:mysql-connector-j:VERSION_APPROVED_BY_PROJECT")
}
~~~

The application only needs the driver at runtime if compiled code uses only standard JDBC interfaces. If code instantiates Connector/J-specific classes such as MysqlDataSource, the dependency may be needed on the compile classpath.

Do not download JARs from untrusted sources or place multiple Connector/J versions simultaneously on the classpath. The loaded driver version may differ from the intended one, causing hard-to-diagnose failures.

## 3. JDBC URLs and Creating a Connection

A MySQL JDBC URL has the general form:

~~~text
jdbc:mysql://host:port/database?property=value
~~~

Example:

~~~text
jdbc:mysql://mysql.example.internal:3306/sales?sslMode=VERIFY_IDENTITY&connectionTimeZone=UTC
~~~

In the URL:

- jdbc:mysql is the scheme for MySQL Connector/J.
- mysql.example.internal is the server hostname.
- 3306 is the standard MySQL port, which can vary by environment.
- sales is the default database for the connection.
- sslMode=VERIFY_IDENTITY requires TLS and verifies server identity against the certificate.
- connectionTimeZone=UTC configures the connection timezone to UTC on Connector/J versions supporting this property.

When using VERIFY_IDENTITY, configure an appropriate trust store/CA so the driver can verify the server certificate. Never disable TLS verification to bypass certificate errors in production. Check Connector/J documentation for version-specific security and timezone properties.

### 3.1. Using DriverManager

Example creating a simple connection:

~~~java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;

public class DbConnectionExample {
    public static void main(String[] args) throws SQLException {
        String url = System.getenv("MYSQL_JDBC_URL");
        String user = System.getenv("MYSQL_USER");
        String password = System.getenv("MYSQL_PASSWORD");

        try (Connection connection =
                 DriverManager.getConnection(url, user, password)) {
            System.out.println("Connected: " +
                connection.getMetaData().getDatabaseProductVersion());
        }
    }
}
~~~

This example reads credentials from environment variables for illustration. In real systems, use a secret manager or your platform's secret provisioning mechanism. Never hard-code passwords in source code, commit config files containing secrets, or log passwords.

Try-with-resources automatically closes the Connection when exiting the block, even if an exception occurs. When a connection comes from a pool, close normally returns the connection to the pool for reuse rather than closing the physical socket; this detail depends on the DataSource/pool.

### 3.2. Using DataSource

DataSource separates connection-creation config from business code and serves as the integration point for connection pools.

You can instantiate Connector/J's DataSource:

~~~java
import com.mysql.cj.jdbc.MysqlDataSource;
import javax.sql.DataSource;

MysqlDataSource mysqlDataSource = new MysqlDataSource();
mysqlDataSource.setURL(
    "jdbc:mysql://mysql.example.internal:3306/sales" +
    "?sslMode=VERIFY_IDENTITY&connectionTimeZone=UTC"
);

DataSource dataSource = mysqlDataSource;

try (Connection connection =
         dataSource.getConnection(user, password)) {
    // Perform JDBC work.
}
~~~

Connector/J's MysqlDataSource provides a DataSource, but using a DataSource by itself does not mean you have a connection pool. In server applications, a managed pool such as HikariCP is typically placed in front of the DataSource to cap connection counts, reuse sockets, and enforce timeouts.

Do not create a new connection pool for every request. Create the pool at application startup, size connection limits according to MySQL capacity, and shut down the pool when the application stops.

## 4. Managing Connection Lifecycle

A Connection represents a database session and can hold state:

- Auto-commit enabled/disabled.
- Transaction isolation level.
- Read-only hint.
- Current catalog/schema.
- Session variables and timezone.
- Open statements.

Key principles:

- Open a connection close to when it is needed.
- Close connections using try-with-resources.
- Do not hold a connection while making HTTP calls or waiting for user input.
- Do not share one Connection across multiple threads simultaneously.
- Do not store a Connection as an application-wide shared singleton.
- With a pool, return connections early so other requests can use them.
- Set connect timeout, socket timeout, and pool timeout according to application requirements.

Example reading state:

~~~java
try (Connection connection =
         dataSource.getConnection()) {
    System.out.println("Auto commit: " +
        connection.getAutoCommit());
    System.out.println("Read only: " +
        connection.isReadOnly());
    System.out.println("Isolation: " +
        connection.getTransactionIsolation());
}
~~~

Do not rely on Connection defaults to infer isolation levels or session state across all environments. Check and configure them explicitly whenever business logic depends on them.

## 5. Statement: Executing Static SQL

Statement is appropriate when the SQL string is fixed and no input values need to be injected. For example, running a metadata query or DDL hardcoded in application code:

~~~java
import java.sql.Connection;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

String sql = "SELECT VERSION()";

try (Connection connection = dataSource.getConnection();
     Statement statement = connection.createStatement();
     ResultSet resultSet = statement.executeQuery(sql)) {

    if (resultSet.next()) {
        System.out.println(resultSet.getString(1));
    }
}
~~~

Common methods:

| Method | When to use | Result |
|---|---|---|
| executeQuery(sql) | Statement returns a ResultSet, typically SELECT | ResultSet |
| executeUpdate(sql) | INSERT, UPDATE, DELETE, or simple DDL | Affected row count; DDL typically returns 0 |
| execute(sql) | Unknown whether statement returns a ResultSet or update count, or produces multiple results | boolean indicating whether the first result is a ResultSet |
| addBatch(sql) | Adds a static SQL statement to a batch | Does not return a result immediately |
| executeBatch() | Runs statements added to the batch | Array of update counts |

Do not use Statement to concatenate user data into SQL. The following example is unsafe:

~~~java
String sql =
    "SELECT * FROM sales.orders WHERE customer_id = " +
    requestCustomerId;
Statement statement = connection.createStatement();
ResultSet resultSet = statement.executeQuery(sql);
~~~

If requestCustomerId contains unexpected SQL syntax, the statement's meaning can be altered. Use PreparedStatement to bind data instead of string concatenation.

Statement can also be contrasted with PreparedStatement and CallableStatement created via Connection. When a Statement executes a new SQL query, the current ResultSet attached to that statement is normally closed. Consume the ResultSet completely or close it before reusing the statement.

## 6. PreparedStatement: Parameterized SQL

PreparedStatement is the default choice for queries with input data. The SQL uses question marks as placeholders; the application binds values by 1-based position.

~~~java
String sql = """
    SELECT order_id, total_amount, status
    FROM sales.orders
    WHERE customer_id = ?
      AND status = ?
    ORDER BY order_id DESC
    LIMIT ?
    """;

try (Connection connection = dataSource.getConnection();
     PreparedStatement statement =
         connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);
    statement.setString(2, "PAID");
    statement.setInt(3, 50);

    try (ResultSet resultSet = statement.executeQuery()) {
        while (resultSet.next()) {
            long orderId = resultSet.getLong("order_id");
            var total = resultSet.getBigDecimal("total_amount");
            String status = resultSet.getString("status");

            System.out.printf(
                "%d %s %s%n", orderId, total, status
            );
        }
    }
}
~~~

This example uses Java 15+ text blocks. If the project targets an older Java version, replace text blocks with concatenated lines or standard strings.

Benefits of PreparedStatement:

- Separates SQL structure from input values.
- Prevents bound data from being interpreted as SQL syntax.
- Reduces parse/prepare overhead when statements are appropriately reused.
- Enforces explicit data type binding.
- Supports batching with the same SQL structure.

PreparedStatement does not automatically make every query fast. Indexes, execution plans, returned row counts, network round trips, and connection usage still dominate performance.

## 7. Binding Data Types Properly

Use setters matching the column type and Java value:

| Common SQL Type | Suggested JDBC Setter |
|---|---|
| TINYINT, SMALLINT, INT | setByte, setShort, setInt |
| BIGINT | setLong |
| DECIMAL, NUMERIC | setBigDecimal |
| FLOAT, DOUBLE | setFloat, setDouble |
| CHAR, VARCHAR, TEXT | setString |
| BINARY, VARBINARY, BLOB | setBytes or stream setters |
| DATE | setDate or setObject with LocalDate if supported by version |
| TIME | setTime or setObject with LocalTime if supported by version |
| TIMESTAMP | setTimestamp or setObject with LocalDateTime/Instant per chosen mapping |
| BOOLEAN | setBoolean; verify boolean/tinyint conventions in schema |

Do not convert all data to strings and rely on MySQL implicit casting. Binding exact types keeps code clear and avoids conversion differences across versions, timezones, or SQL modes.

### 7.1. DECIMAL and Currency

For monetary values, use BigDecimal instead of double/float to avoid binary floating-point rounding errors:

~~~java
BigDecimal amount = new BigDecimal("1250.75");

try (PreparedStatement statement =
         connection.prepareStatement(
             "UPDATE sales.orders SET total_amount = ? " +
             "WHERE order_id = ?")) {

    statement.setBigDecimal(1, amount);
    statement.setLong(2, orderId);
    int changed = statement.executeUpdate();
}
~~~

Construct BigDecimal from a decimal string or an exact decimal source. Do not use new BigDecimal(0.1) when you need an exact representation of decimal 0.1.

### 7.2. NULL Values

Use setNull with the corresponding SQL type when a parameter is null:

~~~java
if (phoneNumber == null) {
    statement.setNull(1, java.sql.Types.VARCHAR);
} else {
    statement.setString(1, phoneNumber);
}
~~~

You can use setObject(index, null, Types.VARCHAR) when appropriate. Never pass the string "NULL", as that is text, not SQL NULL.

SQL conditions must also handle NULL properly. Comparing a column with equals against a NULL parameter does not return TRUE; use IS NULL or an appropriate null-safe expression. For example, if a filter may be absent, build the condition explicitly rather than expecting column = NULL to match.

### 7.3. Date, Time, and Timezones

MySQL has DATE, TIME, DATETIME, and TIMESTAMP with different semantics. TIMESTAMP is converted according to the session timezone on write/read; DATETIME stores date and time components without inherently representing a timezone-aware instant.

Choose Java mappings based on business semantics:

- LocalDate for calendar dates, such as birth dates or invoice dates.
- LocalDateTime for date/time points without an attached timezone, if the schema uses DATETIME with that convention.
- Instant or OffsetDateTime for a global point in time; convert explicitly to the SQL type and connection timezone.
- Do not rely on the application host's default timezone.

Configure connection timezones consistently between application and database. Test data across midnight boundaries and across environments with different timezones.

## 8. Placeholders Are Only for Values, Not Column Names

Question marks in PreparedStatement represent data values. They cannot substitute for table names, column names, ORDER BY keywords, or fragments of SQL syntax.

Example that does not work as expected:

~~~java
String sql = "SELECT * FROM sales.orders ORDER BY ?";
~~~

That placeholder is a value expression, not a dynamic column name. If sorting by user selection is required, use a whitelist:

~~~java
String sortColumn;
switch (requestedSort) {
    case "created" -> sortColumn = "created_at";
    case "amount" -> sortColumn = "total_amount";
    default -> sortColumn = "order_id";
}

String sql =
    "SELECT order_id, total_amount " +
    "FROM sales.orders ORDER BY " + sortColumn + " DESC";
~~~

Only interpolate column names selected from a fixed application-controlled list. Never interpolate request values directly into SQL.

### 8.1. IN with Variable Parameter Counts

To pass a list of IDs, generate the exact number of placeholders and bind each element. Check for an empty list before building the SQL:

~~~java
if (orderIds.isEmpty()) {
    return List.of();
}

String placeholders = String.join(
    ",", Collections.nCopies(orderIds.size(), "?")
);

String sql =
    "SELECT order_id, status " +
    "FROM sales.orders WHERE order_id IN (" +
    placeholders + ")";

try (PreparedStatement statement =
         connection.prepareStatement(sql)) {
    for (int i = 0; i < orderIds.size(); i++) {
        statement.setLong(i + 1, orderIds.get(i));
    }

    try (ResultSet rs = statement.executeQuery()) {
        // Read results.
    }
}
~~~

Very large lists can produce long SQL strings with many placeholders. In those cases, split into batches, use a temporary table, or choose an appropriate set-passing mechanism. Always cap input size to avoid oversized statements.

## 9. ResultSet: Reading Query Results

A ResultSet is normally a forward-only cursor. Call next() to advance to the next row; when it returns false, there are no more rows.

~~~java
String sql =
    "SELECT order_id, total_amount, created_at " +
    "FROM sales.orders WHERE customer_id = ?";

try (PreparedStatement statement =
         connection.prepareStatement(sql)) {

    statement.setLong(1, customerId);

    try (ResultSet rs = statement.executeQuery()) {
        while (rs.next()) {
            long orderId = rs.getLong("order_id");
            BigDecimal amount = rs.getBigDecimal("total_amount");
            Timestamp createdAt = rs.getTimestamp("created_at");

            System.out.println(orderId + " " + amount + " " + createdAt);
        }
    }
}
~~~

Columns can be accessed by 1-based index or by label. Using labels is usually easier to read and less coupled to SELECT column ordering.

### 9.1. Distinguishing SQL NULL from Java Defaults

Some getters return primitives and therefore cannot represent null. For instance, getLong returns 0 when the SQL column is NULL. Call wasNull immediately after the getter to check:

~~~java
long quantity = rs.getLong("quantity");
if (rs.wasNull()) {
    // The quantity column is SQL NULL.
} else {
    // quantity holds the actual value.
}
~~~

For reference types such as String, BigDecimal, and Date, getters typically return null when the SQL value is NULL. Even so, check for null before using them.

### 9.2. ResultSet and Statement Lifecycle

A ResultSet depends on the Statement that created it. Closing the Statement normally closes its associated ResultSet. Nested try-with-resources ensures closing in the right order:

1. ResultSet is closed first.
2. PreparedStatement is closed next.
3. Connection is closed last.

Do not return a ResultSet beyond the scope where its Statement/Connection has already been closed. If the service layer needs data after closing the connection, map results to DTOs or collections first.

### 9.3. Large ResultSets

By default, how the driver fetches data can cause large results to consume substantial client-side memory. Limit row counts in SQL, use keyset pagination, or use streaming/cursor fetch mechanisms supported by Connector/J.

setFetchSize is a hint to the driver, not a universal guarantee that data will be fetched in batches. Connector/J has specific streaming modes; some configurations use server-side prepared statements together with useCursorFetch and a positive fetch size. Specific streaming configurations must be checked against Connector/J documentation, as they may keep the connection busy until the ResultSet is exhausted or closed.

Do not open a large streaming ResultSet and execute additional queries on the same connection when the driver requires the ResultSet to be consumed first. For large results, read sequentially, process row by row, and close the cursor early.

## 10. executeQuery, executeUpdate, and execute

Choose the method based on the expected result type.

~~~java
// Query returning a ResultSet
try (PreparedStatement ps =
         connection.prepareStatement(
             "SELECT status FROM sales.orders WHERE order_id = ?")) {
    ps.setLong(1, orderId);
    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            String status = rs.getString(1);
        }
    }
}

// DML returning an update count
try (PreparedStatement ps =
         connection.prepareStatement(
             "UPDATE sales.orders SET status = ? WHERE order_id = ?")) {
    ps.setString(1, "SHIPPED");
    ps.setLong(2, orderId);
    int affectedRows = ps.executeUpdate();
}

// DDL or statement with unknown result type
try (Statement st = connection.createStatement()) {
    boolean hasResultSet = st.execute(
        "CREATE TEMPORARY TABLE tmp_work (id BIGINT PRIMARY KEY)"
    );
}
~~~

executeUpdate is typically used for INSERT, UPDATE, DELETE, and DDL. For DDL, the update count is usually 0; do not interpret 0 as a DDL failure.

Use execute when a statement might return a ResultSet, an update count, or multiple results. For instance, a stored procedure may return multiple result sets and update counts; use getResultSet, getUpdateCount, and getMoreResults to consume results in order.

## 11. Retrieving Generated Keys After INSERT

If a table uses AUTO_INCREMENT, you can instruct JDBC to return generated keys:

~~~java
String sql =
    "INSERT INTO sales.orders (customer_id, status, total_amount) " +
    "VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(
         sql, Statement.RETURN_GENERATED_KEYS)) {

    ps.setLong(1, customerId);
    ps.setString(2, "NEW");
    ps.setBigDecimal(3, new BigDecimal("125.00"));

    int inserted = ps.executeUpdate();

    if (inserted != 1) {
        throw new SQLException("Unexpected insert count: " + inserted);
    }

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long newOrderId = keys.getLong(1);
        } else {
            throw new SQLException("No generated key returned");
        }
    }
}
~~~

Generated keys are the JDBC mechanism to obtain database-generated keys for that execution. Never use SELECT MAX(id) to find the newly inserted key because another connection may insert a row between statements, yielding the wrong result.

When inserting multiple rows in a batch, whether and how many generated keys are returned depends on the driver, version, and configuration. Test with your exact Connector/J version; if exact per-row key mapping is required, consider inserting in small groups or designing an appropriate database API.

## 12. Batching with PreparedStatement

Batching reduces round trips when executing multiple statements sharing the same SQL structure.

~~~java
String sql =
    "INSERT INTO sales.order_items " +
    "(order_id, product_id, quantity) VALUES (?, ?, ?)";

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    for (OrderItem item : items) {
        ps.setLong(1, item.orderId());
        ps.setLong(2, item.productId());
        ps.setInt(3, item.quantity());
        ps.addBatch();
    }

    int[] counts = ps.executeBatch();
}
~~~

Each loop iteration rebinds every parameter and calls addBatch. If you forget a parameter, the previous value may remain bound to that placeholder depending on statement state; always bind all parameters for every batch entry.

### 12.1. Batch Update Counts

The array returned by executeBatch may contain:

- Affected row counts.
- Statement.SUCCESS_NO_INFO if the driver does not know the exact row count.
- Statement.EXECUTE_FAILED for a failed entry in certain cases.

BatchUpdateException provides getUpdateCounts to inspect partial results. Do not assume the entire batch succeeded simply because some entries have valid update counts.

### 12.2. Batches and Transactions

Batching does not guarantee atomicity across all entries on its own. If all rows must commit or roll back together, use an explicit transaction:

~~~java
try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement ps = connection.prepareStatement(
            "INSERT INTO sales.order_items " +
            "(order_id, product_id, quantity) VALUES (?, ?, ?)")) {

        for (OrderItem item : items) {
            ps.setLong(1, item.orderId());
            ps.setLong(2, item.productId());
            ps.setInt(3, item.quantity());
            ps.addBatch();
        }

        ps.executeBatch();
        connection.commit();
    } catch (SQLException | RuntimeException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
~~~

If a batch is very large, you do not always want everything in a single transaction. Split it into smaller batch transactions to control undo/redo, lock duration, and retryability. That means each batch is an independent commit unit; the business design must tolerate partial progress.

Connector/J provides the rewriteBatchedStatements property to optimize certain batches by rewriting them into multi-row statements or corresponding execution forms. This optimization depends on SQL type and driver version; benchmark and verify semantics/update counts before enabling it broadly.

## 13. CallableStatement: Calling Stored Procedures

CallableStatement uses JDBC escape syntax to invoke stored procedures or functions. For a procedure, the common syntax is:

~~~text
{call schema.procedure_name(?, ?, ?)}
~~~

Example procedure accepting an order ID and returning the total via an OUT parameter:

~~~sql
DELIMITER //

CREATE PROCEDURE sales.get_order_total(
    IN p_order_id BIGINT,
    OUT p_total DECIMAL(12,2)
)
BEGIN
    SELECT COALESCE(SUM(total_amount), 0)
    INTO p_total
    FROM sales.orders
    WHERE order_id = p_order_id;
END//

DELIMITER ;
~~~

Calling the procedure from Java:

~~~java
String call = "{call sales.get_order_total(?, ?)}";

try (Connection connection = dataSource.getConnection();
     CallableStatement cs = connection.prepareCall(call)) {

    cs.setLong(1, orderId);
    cs.registerOutParameter(2, Types.DECIMAL);

    cs.execute();

    BigDecimal total = cs.getBigDecimal(2);
}
~~~

Order matters:

1. Create the CallableStatement using prepareCall.
2. Bind IN parameters.
3. Register SQL types for OUT parameters.
4. Call execute.
5. Read OUT values with the appropriate getters.

### 13.1. IN, OUT, and INOUT Parameters

| Parameter type | Usage |
|---|---|
| IN | Call setXxx to pass a value into the procedure. |
| OUT | Call registerOutParameter before execute, then read the value after execute. |
| INOUT | Both set the input value and call registerOutParameter, then read the updated value. |

INOUT example:

~~~java
try (CallableStatement cs =
         connection.prepareCall("{call sales.adjust_limit(?, ?)}")) {

    cs.setLong(1, accountId);
    cs.setBigDecimal(2, currentLimit);
    cs.registerOutParameter(2, Types.DECIMAL);

    cs.execute();

    BigDecimal adjustedLimit = cs.getBigDecimal(2);
}
~~~

This example assumes the second parameter in the procedure is declared INOUT DECIMAL. Parameter order, types, and modes must match the procedure definition on the server.

### 13.2. Calling Stored Functions

A function returns a value through the first placeholder:

~~~java
try (CallableStatement cs =
         connection.prepareCall(
             "{? = call sales.calculate_tax(?)}")) {

    cs.registerOutParameter(1, Types.DECIMAL);
    cs.setBigDecimal(2, new BigDecimal("100.00"));

    cs.execute();

    BigDecimal tax = cs.getBigDecimal(1);
}
~~~

The first placeholder is the function return value; subsequent placeholders are input parameters. The registered SQL type must be compatible with the actual return type.

## 14. CallableStatement with ResultSets and Multiple Results

A stored procedure can return one or more ResultSets, update counts, and OUT parameters. In this case, execute returns a boolean indicating whether the first result is a ResultSet. Use getMoreResults to continue reading.

~~~java
try (CallableStatement cs =
         connection.prepareCall("{call sales.get_customer_orders(?)}")) {

    cs.setLong(1, customerId);

    boolean hasResultSet = cs.execute();

    while (true) {
        if (hasResultSet) {
            try (ResultSet rs = cs.getResultSet()) {
                while (rs.next()) {
                    long orderId = rs.getLong("order_id");
                    String status = rs.getString("status");
                }
            }
        } else {
            int updateCount = cs.getUpdateCount();
            if (updateCount == -1) {
                break;
            }
        }

        hasResultSet =
            cs.getMoreResults(Statement.CLOSE_CURRENT_RESULT);
    }
}
~~~

Do not read only the first ResultSet and close the CallableStatement if the procedure returns additional results needed by the application. Review procedure design to avoid returning unnecessary result sets.

OUT parameters can be read after the procedure executes; when a procedure returns multiple result sets, consume results per JDBC rules and verify Connector/J behavior for your version. Do not let applications depend on an unspecified result ordering not guaranteed by the procedure contract.

## 15. Transactions via Connection

By default, a JDBC Connection is usually in auto-commit mode. Each statement commits individually upon completion. For multi-operation business logic requiring atomicity, disable auto-commit and control transactions explicitly.

Example transferring money between two accounts:

~~~java
String debitSql =
    "UPDATE banking.account " +
    "SET balance = balance - ? " +
    "WHERE account_id = ? AND balance >= ?";

String creditSql =
    "UPDATE banking.account " +
    "SET balance = balance + ? " +
    "WHERE account_id = ?";

try (Connection connection = dataSource.getConnection()) {
    connection.setAutoCommit(false);

    try (PreparedStatement debit =
             connection.prepareStatement(debitSql);
         PreparedStatement credit =
             connection.prepareStatement(creditSql)) {

        BigDecimal amount = new BigDecimal("50.00");

        debit.setBigDecimal(1, amount);
        debit.setLong(2, fromAccountId);
        debit.setBigDecimal(3, amount);

        int debited = debit.executeUpdate();
        if (debited != 1) {
            throw new SQLException("Insufficient funds or account missing");
        }

        credit.setBigDecimal(1, amount);
        credit.setLong(2, toAccountId);

        int credited = credit.executeUpdate();
        if (credited != 1) {
            throw new SQLException("Destination account missing");
        }

        connection.commit();
    } catch (SQLException e) {
        try {
            connection.rollback();
        } catch (SQLException rollbackError) {
            e.addSuppressed(rollbackError);
        }
        throw e;
    }
}
~~~

In this example, the debit only succeeds if the balance is sufficient and the account exists. If the credit fails, rollback reverts both operations to the pre-transaction state. Tables must use a transactional engine such as InnoDB for proper rollback guarantees.

Do not call payment services, send emails, or perform HTTP requests inside a long-running database transaction. External side effects do not automatically roll back with MySQL. Use a transactional outbox or an appropriate orchestration pattern when side effects must stay synchronized.

### 15.1. Isolation Levels

JDBC allows reading and setting the isolation level:

~~~java
connection.setTransactionIsolation(
    Connection.TRANSACTION_READ_COMMITTED
);
~~~

Standard levels include:

- TRANSACTION_READ_UNCOMMITTED.
- TRANSACTION_READ_COMMITTED.
- TRANSACTION_REPEATABLE_READ.
- TRANSACTION_SERIALIZABLE.

InnoDB typically defaults to REPEATABLE READ, though server/session configuration can change this. Choose an isolation level based on consistency requirements and locking model; never change it solely to reduce lock waits without checking business impact.

### 15.2. Savepoints

Savepoints allow rolling back part of the work inside a transaction:

~~~java
Savepoint savepoint = connection.setSavepoint("before_optional_step");

try {
    // Optional operation.
} catch (SQLException e) {
    connection.rollback(savepoint);
}

// Continue or commit the transaction.
~~~

A Savepoint is not an independent transaction. Committing or rolling back the outer transaction still determines the final outcome.

## 16. SQLException and Error Diagnostics

SQLException provides more information than just a message:

~~~java
try {
    // JDBC operation.
} catch (SQLException e) {
    System.err.println("Message: " + e.getMessage());
    System.err.println("SQLState: " + e.getSQLState());
    System.err.println("Vendor code: " + e.getErrorCode());

    for (SQLException next = e.getNextException();
         next != null;
         next = next.getNextException()) {
        System.err.println("Next: " + next.getMessage());
    }

    throw e;
}
~~~

Key fields to inspect:

- getMessage(): error description.
- getSQLState(): standard SQL or driver state code.
- getErrorCode(): MySQL/driver-specific error code.
- getNextException(): next exception in the exception chain.
- getCause(): underlying cause if present.

Errors can be classified by SQLState and vendor error code. For example, SQLState values starting with 23 generally indicate constraint violations; MySQL deadlocks typically have error code 1213 and SQLState 40001; lock wait timeouts typically have error code 1205. Always verify codes against your version and actual error context.

### 16.1. Transaction Retries

Retrying is only appropriate for transient recoverable errors where business logic permits re-execution. For a deadlock, the victim transaction has already been rolled back; the application can retry the entire transaction from the start with bounded attempts and backoff.

Never retry blindly by catching every SQLException. Syntax errors, missing privileges, wrong schemas, data constraint violations, or authentication errors will not be resolved by retrying.

If the connection drops during commit, the commit outcome may be unknown to the client. Never assume the transaction definitely rolled back. For operations requiring duplicate prevention, use an idempotency key or unique transaction ID to check the outcome before retrying.

### 16.2. SQLWarning

Some operations return warnings without throwing SQLException. JDBC provides getWarnings and clearWarnings on Connection, Statement, and ResultSet. During data imports or conversions, inspect warnings to catch truncation, conversion issues, or unusual conditions even when the statement completed.

Never ignore warnings during critical data migrations just because executeUpdate did not throw an exception.

## 17. Common Connector/J Properties

Connector/J offers many connection properties. Enable a property only when you understand its purpose and have tested it under a real workload.

| Property | Purpose | Notes |
|---|---|---|
| sslMode=VERIFY_IDENTITY | Encrypts connection and verifies server identity | Requires CA/trust store and hostname matching certificate. |
| connectionTimeZone=UTC | Specifies connection timezone | Verify TIMESTAMP/DATETIME mapping and driver version. |
| connectTimeout | Limits time spent opening a connection | Choose based on network and fail-fast policy. |
| socketTimeout | Limits socket read wait time | Too low can cut off valid long-running queries. |
| useServerPrepStmts | Uses server-side prepared statements when supported | Test statement compatibility and performance. |
| cachePrepStmts | Caches prepared statements per connection | Improves efficiency when the same SQL is reused. |
| prepStmtCacheSize | Maximum cached statements per connection | Balance memory usage and cache hit ratio. |
| prepStmtCacheSqlLimit | Maximum SQL length eligible for caching | Longer SQL statements will not be cached. |
| rewriteBatchedStatements | Optimizes certain JDBC batches | Verify update counts, generated keys, and semantics. |
| useCursorFetch | Enables cursor fetching with server-side prepared statements | Requires compatible settings, usually paired with useServerPrepStmts and positive fetch size. |

Example URL configuring several properties:

~~~text
jdbc:mysql://mysql.example.internal:3306/sales?sslMode=VERIFY_IDENTITY&connectionTimeZone=UTC&connectTimeout=10000&socketTimeout=30000&useServerPrepStmts=true&cachePrepStmts=true
~~~

Timeout values in this example are illustrative in milliseconds; choose values based on SLAs and actual query durations. Avoid putting passwords or secrets into the JDBC URL because URLs can show up in logs or admin pages.

### 17.1. Client-Side and Server-Side Prepared Statements

PreparedStatement is a JDBC abstraction. Depending on configuration and statement capabilities, Connector/J can emulate prepared statements on the client or use server-side prepared statements.

useServerPrepStmts=true requests server-side prepared statements when supported by the driver. This can change parameter transmission, round trips, server-side statement resources, and behavior of certain statements. Do not assume server-side is always faster than client-side; measure with actual SQL and workloads.

cachePrepStmts=true lets the driver cache eligible prepared statements per connection. Per-connection caching means a pool with many connections maintains separate caches; calculate total memory across connection count and cached statement count.

## 18. Connection Pools and Concurrency Limits

Opening a new connection for every operation incurs TCP, TLS, authentication, and session initialization overhead. A connection pool holds a managed set of connections for reuse.

When configuring a pool:

- Size maximum pool size according to how many connections MySQL can serve, not mechanically after application thread counts.
- Set a connection timeout so requests do not wait indefinitely.
- Check idle timeout, max lifetime, and proxy/load balancer limits.
- Monitor active, idle, pending counts, and connection acquisition time.
- Keep transactions short and return connections early.
- Do not hold connections during long CPU work or while waiting on external services.
- Do not share connections or statements across multiple threads.

An overly large pool increases context switching, contention, and MySQL session count, making the system slower. Size the pool based on throughput, latency, and server limits.

Connection pools usually reset certain connection states upon return, but applications should still finish transactions and close resources properly. Never let a connection with an uncommitted transaction or custom session variables leak into another request.

## 19. Timeouts, Cancellation, and Long Queries

JDBC provides a query timeout on Statement:

~~~java
try (PreparedStatement ps =
         connection.prepareStatement(
             "SELECT order_id FROM sales.orders WHERE status = ?")) {

    ps.setString(1, "PENDING");
    ps.setQueryTimeout(20);

    try (ResultSet rs = ps.executeQuery()) {
        while (rs.next()) {
            // Process row.
        }
    }
}
~~~

Query timeout is a limit in seconds in the JDBC API. Cancellation behavior and timing precision depend on the driver/server. Do not treat it as a replacement for pool, socket, or request-layer timeouts.

You can call cancel from another thread per JDBC/driver support, but design carefully to avoid races with closing or reused statements. After cancelling a query, check transaction state and roll back if business logic requires it.

## 20. Statements and Thread Safety

Connection, Statement, PreparedStatement, CallableStatement, and ResultSet carry mutable state. Do not share a single instance across concurrent threads.

A typical safe model is:

- One request or unit of work borrows one Connection from the pool.
- The request creates its own statements for SQL execution.
- The ResultSet is read and closed within the same scope.
- The transaction is committed or rolled back before returning the connection.
- The Connection is closed to return it to the pool.

If parallelism is needed, use multiple independent connections and bound worker concurrency to pool/server limits. Do not spawn hundreds of threads just to run concurrent queries if the database cannot handle that load.

## 21. End-to-End Example: Order Query Repository

A repository method should accept business values, bind them via PreparedStatement, map results to objects, and close resources before returning.

~~~java
import java.math.BigDecimal;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.ArrayList;
import java.util.List;
import javax.sql.DataSource;

public record OrderSummary(
    long orderId,
    String status,
    BigDecimal totalAmount
) {}

public class OrderRepository {
    private final DataSource dataSource;

    public OrderRepository(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    public List<OrderSummary> findByCustomer(long customerId)
            throws SQLException {
        String sql =
            "SELECT order_id, status, total_amount " +
            "FROM sales.orders " +
            "WHERE customer_id = ? " +
            "ORDER BY order_id DESC";

        List<OrderSummary> orders = new ArrayList<>();

        try (Connection connection = dataSource.getConnection();
             PreparedStatement statement =
                 connection.prepareStatement(sql)) {

            statement.setLong(1, customerId);

            try (ResultSet rs = statement.executeQuery()) {
                while (rs.next()) {
                    orders.add(new OrderSummary(
                        rs.getLong("order_id"),
                        rs.getString("status"),
                        rs.getBigDecimal("total_amount")
                    ));
                }
            }
        }

        return orders;
    }
}
~~~

Records require Java 16 or higher. On older Java versions, replace with a standard DTO class. The repository does not return a ResultSet because ResultSets are tied to the statement and connection.

## 22. Common Errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| No suitable driver | Missing Connector/J or dependency not on runtime classpath | Check dependencies and JDBC URL. |
| Access denied | Wrong user/password, host mismatch, or missing privileges | Check account host, secret, and MySQL grants. |
| Communications link failure | Network, TLS, server restart, or timeout | Check network, certificates, server logs, and timeouts. |
| Unknown column or syntax error | SQL incompatible with schema/version or misplaced placeholders | Check DDL, SQL, and parameter binding order. |
| Parameter index out of range | Placeholder indexes start at 1 or parameter count mismatch | Count question marks and bind all parameters in order. |
| Data truncation/conversion | Wrong setter type or value exceeds precision/length | Use type-appropriate setters, check schema and SQLWarning. |
| ResultSet closed | Statement re-executed or resource already closed | Keep ResultSet within Statement/Connection scope. |
| Missing generated key | RETURN_GENERATED_KEYS not requested or statement generates no key | Use the appropriate overload and verify insert type. |
| CallableStatement routine not found | Wrong schema, routine name, EXECUTE privilege, or signature | Check procedure/function, grants, and parameter order. |
| Deadlock or lock timeout | Competing transactions | Roll back entire transaction and perform bounded retries if business logic allows. |
| Pool connection exhaustion | Connections not closed or transactions held too long | Use try-with-resources, monitor pool, and shorten transactions. |
| Shifted date/time results | Inconsistent timezone mapping | Standardize connection timezone and choose Java types matching column semantics. |

## 23. Hands-On Exercises

### Exercise 1: Creating a Secure Connection

Create a small Java application using Connector/J to connect to the sales database. Read the JDBC URL and credentials from environment configuration; enable TLS verification in an environment with a valid CA. Print the server version and close the Connection properly.

### Exercise 2: Comparing Statement and PreparedStatement

Write two queries to find orders by customer ID. Test passing input containing special characters and SQL syntax strings. Observe how Statement string concatenation alters the SQL while PreparedStatement binds the input as a value.

### Exercise 3: Binding Data Types and NULL

Write an INSERT with VARCHAR, BIGINT, DECIMAL, DATE, and a nullable column. Bind using the corresponding setters, test setNull, and read back with ResultSet. Verify how wasNull behaves when using primitive getters.

### Exercise 4: Generated Keys and Batching

Insert an order and retrieve the order ID via getGeneratedKeys. Then insert multiple order items using a PreparedStatement batch. Test transaction rollback and verify data in InnoDB.

### Exercise 5: Calling a Procedure

Create a procedure with IN and OUT parameters and call it with CallableStatement. Extend the procedure to return a ResultSet and test reading multiple results with getMoreResults.

### Exercise 6: Retrying Transactions

Create two sessions updating rows in opposite order so a deadlock can occur in a test environment. Catch SQLException, log SQLState/vendor code, roll back the entire transaction, and retry with bounded backoff.

## 24. Checklist Before Shipping JDBC Code to Production

- [ ] Connector/J version is compatible with JDK and MySQL Server.
- [ ] JDBC URL uses the correct hostname/port/database for the environment.
- [ ] TLS is configured and certificate verification is enabled for production connections.
- [ ] Credentials are retrieved from a secret manager or secure config source.
- [ ] Connections are managed via try-with-resources or a pool.
- [ ] Connections/Statements are never shared across threads.
- [ ] PreparedStatement is used for all SQL accepting input values.
- [ ] Dynamic column/table names are chosen solely from a whitelist.
- [ ] JDBC setters match SQL types and NULLs are handled explicitly.
- [ ] ResultSets are read and closed within Statement scope.
- [ ] Generated keys are retrieved via the appropriate JDBC API.
- [ ] Batches have bounded sizes and clear transaction semantics.
- [ ] CallableStatements match routine IN/OUT/INOUT signatures.
- [ ] Transactions have explicit commit/rollback and do not hold connections too long.
- [ ] SQLExceptions are logged with SQLState and vendor code, never secrets.
- [ ] Retries apply only to transient errors where operations can safely repeat.
- [ ] Timeouts, pool sizes, and fetch strategies are measured on realistic workloads.
- [ ] Integration tests run against the exact deployed MySQL and Connector/J versions.

Connection manages the session and transactions; Statement executes static SQL; PreparedStatement safely binds values by position; CallableStatement invokes routines with input/output parameters. Use try-with-resources, proper type bindings, and clear transaction boundaries to prevent resource leaks and data corruption. In production, combine connection pooling, TLS, timeouts, and monitoring; test actual driver behavior for your version rather than relying on assumptions about optimizations or streaming.
