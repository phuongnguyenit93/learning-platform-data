# Connection, PreparedStatement, ResultSet, and the JDBC Driver

When a Java application reads from or writes to a relational database, it ultimately has to send SQL statements over a real connection. **JDBC (Java Database Connectivity)** is Java's standard API for that job. Spring JDBC reduces boilerplate when working with JDBC; **Spring Data JDBC** builds aggregate mapping and repository capabilities on top of this foundation. Understanding the four components — **JDBC driver**, **`Connection`**, **`PreparedStatement`**, and **`ResultSet`** — helps explain exactly what happens beneath a call to `repository.save(...)` or `repository.findById(...)`.

## 1. How Do the Four Components Work Together?

| Component | Role | Key Point to Remember |
| --- | --- | --- |
| **JDBC driver** | Library implementing JDBC and communicating via a specific DBMS protocol. | The application must have a driver compatible with PostgreSQL, MySQL, H2, etc. |
| **`Connection`** | Represents a JDBC session with the database; holds transaction context and session settings. | Obtained from `DataSource` or `DriverManager` and always returned/closed properly. |
| **`PreparedStatement`** | A precompiled/prepared SQL statement allowing values to be bound to `?` parameters and executed. | Only bind **data values**; never concatenate user input directly into SQL strings. |
| **`ResultSet`** | Tabular row/column results from a `SELECT` query (or auto-generated key results). | The cursor initially sits **before the first row**; call `next()` before reading columns. |

Simplified flow of a query:

```text
Application / Spring Data JDBC
           │ requests data read
           ▼
   DataSource (may use a connection pool)
           │ provides Connection
           ▼
       Connection
           │ prepareStatement(SQL)
           ▼
   PreparedStatement -- setXxx(...) --> parameters
           │ executeQuery()
           ▼
      JDBC driver <---- network / DB protocol ----> Database
           │ returns rows
           ▼
        ResultSet
           │ next(), getXxx(...)
           ▼
     Java Objects
```

This diagram is a conceptual model: **the driver is also involved when establishing the `Connection`**, not just at SQL execution time. `INSERT`, `UPDATE`, and `DELETE` statements normally return an affected row count rather than a `ResultSet` containing `SELECT` data.

## 2. JDBC Driver: The Bridge Between Java API and Database

JDBC defines interfaces primarily in `java.sql` and `javax.sql`; each vendor's driver implements the communication with its database. Because the Java interfaces are standardized, code using `Connection` or `PreparedStatement` looks similar across database engines, although SQL dialects, data types, transaction features, and driver optimizations still vary.

Example connection URLs:

| Database | Sample JDBC URL | Typical Driver |
| --- | --- | --- |
| PostgreSQL | `jdbc:postgresql://localhost:5432/learn_db` | PostgreSQL JDBC Driver |
| MySQL | `jdbc:mysql://localhost:3306/learn_db` | MySQL Connector/J |
| H2 in-memory | `jdbc:h2:mem:learn_db` | H2 JDBC Driver |

In a Spring Boot project with managed dependency versions, you can declare the driver in Gradle:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jdbc'
    runtimeOnly 'org.postgresql:postgresql'
}
```

This example is for **PostgreSQL**; if using H2, replace the driver dependency with `runtimeOnly 'com.h2database:h2'`. Spring Boot dependency management must be enabled to omit explicit versions as shown; plain Java projects must specify a compatible driver version.

Since JDBC 4.0, modern drivers automatically register via Java's Service Provider mechanism. Thus typical application code **does not need** to call `Class.forName("org.postgresql.Driver")` before connecting. Manual driver class loading mainly appears in legacy code or environments with special classloader setups.

Two common ways to obtain a connection:

```java
// Plain Java/JDBC: direct connection.
Connection connection = DriverManager.getConnection(
        "jdbc:postgresql://localhost:5432/learn_db",
        "app_user",
        password
);

// Spring application: DataSource is configured and managed for you.
Connection pooledConnection = dataSource.getConnection();
```

`DriverManager` is handy for learning JDBC mechanics and small utilities. In server applications, `DataSource` is the standard abstraction for configuration, pooling, and Spring transaction integration. **`DataSource` is not a driver**: it supplies `Connection` instances and relies on a driver underneath.

## 3. Connection: Session, Resources, and Transactions

A `Connection` is created when a database connection is opened or borrowed from a pool. It provides methods such as:

- `prepareStatement(sql)`: creates a `PreparedStatement` bound to the connection.
- `createStatement()`: creates a `Statement` for parameterless SQL, generally only safe when SQL is constant or strictly controlled.
- `setAutoCommit(false)`, `commit()`, `rollback()`: controls transactions when managing JDBC directly.
- `setTransactionIsolation(...)`: sets the isolation level when supported by the database/driver.
- `close()`: ends usage of the connection.

### 3.1. Why Must Connections Be Closed?

A real connection consumes resources on both client and server and may occupy a slot in a connection pool. Failing to release connections causes the application to run out of available connections, leading to timeouts or pool exhaustion.

Always use **try-with-resources**:

```java
try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(
             "SELECT id, full_name FROM customers WHERE id = ?")) {
    ps.setLong(1, customerId);

    try (ResultSet rs = ps.executeQuery()) {
        if (rs.next()) {
            System.out.println(rs.getString("full_name"));
        }
    }
} // rs, ps, conn are closed in reverse order
```

For a connection obtained directly from `DriverManager`, `close()` normally closes the physical connection. With a connection pool like **HikariCP**, calling `close()` on a pooled connection typically **returns the connection to the pool** for reuse. That is why code borrowing a connection must still call `close()` even when pooling is used.

Do not share an active `Connection` across multiple threads. `PreparedStatement` and `ResultSet` should also be scoped to a single operation rather than stored as shared fields in a singleton service.

### 3.2. Auto-Commit and Transactions

In plain JDBC, connections usually default to `autoCommit = true`: each completed statement commits automatically. When two operations must **succeed or fail together**, you need a transaction:

```java
void transfer(DataSource dataSource, long fromId, long toId,
              BigDecimal amount) throws SQLException {
    try (Connection conn = dataSource.getConnection()) {
        conn.setAutoCommit(false);
        try (PreparedStatement debit = conn.prepareStatement(
                     "UPDATE accounts SET balance = balance - ? " +
                     "WHERE id = ? AND balance >= ?");
             PreparedStatement credit = conn.prepareStatement(
                     "UPDATE accounts SET balance = balance + ? WHERE id = ?")) {

            debit.setBigDecimal(1, amount);
            debit.setLong(2, fromId);
            debit.setBigDecimal(3, amount);
            if (debit.executeUpdate() != 1) {
                throw new SQLException("Source account not found or insufficient balance");
            }

            credit.setBigDecimal(1, amount);
            credit.setLong(2, toId);
            if (credit.executeUpdate() != 1) {
                throw new SQLException("Destination account not found");
            }

            conn.commit();
        } catch (SQLException e) {
            conn.rollback();
            throw e;
        }
    }
}
```

This example assumes `amount` is positive, the two accounts are distinct, and the schema/DB supports transactions; other input validations must be handled in the business layer. Both updates run on the **same `Connection`**, so they participate in the same transaction.

In a Spring application, you should normally place `@Transactional` on service methods and let the **Spring transaction manager** manage commit/rollback, rather than manually calling `setAutoCommit` or `commit` on Spring-managed connections. Spring transactions bind compatible operations in the same execution flow to the appropriate connection.

## 4. PreparedStatement: Parameterized SQL

A `PreparedStatement` is created from a `Connection` with a fixed SQL template. The `?` symbol is a **parameter marker**, assigned values via `setString`, `setLong`, `setBigDecimal`, etc. Parameter indices **start at 1**, whereas many Java structures are 0-based.

Suppose the database has the table:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE
);
```

Inserting a customer:

```java
String sql = "INSERT INTO customers (full_name, email) VALUES (?, ?)";

try (Connection conn = dataSource.getConnection();
     PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setString(1, "Nguyen An");
    ps.setString(2, "an@example.test");

    int affectedRows = ps.executeUpdate(); // typically 1 here
    System.out.println("Inserted rows: " + affectedRows);
}
```

Key execution methods:

| Method | When to Use | Return Value |
| --- | --- | --- |
| `executeQuery()` | SQL that returns a row set, typically `SELECT` | `ResultSet` |
| `executeUpdate()` | `INSERT`, `UPDATE`, `DELETE`, or compatible DDL | `int` count of affected rows; meaning for DDL depends on driver |
| `execute()` | When it is not known upfront if SQL returns rows or an update count | `boolean` indicating whether the first result is a `ResultSet` |
| `addBatch()` / `executeBatch()` | Submitting a batch of operations with the same SQL template | Array of update counts; details depend on driver |

### 4.1. Why Not Concatenate User Input into SQL?

**Unsafe** example:

```java
String sql = "SELECT id FROM customers WHERE email = '" + emailInput + "'";
```

The contents of `emailInput` can alter the SQL structure, causing **SQL injection**. The right way:

```java
String sql = "SELECT id FROM customers WHERE email = ?";
try (PreparedStatement ps = conn.prepareStatement(sql)) {
    ps.setString(1, emailInput);
    try (ResultSet rs = ps.executeQuery()) {
        // Read data...
    }
}
```

The driver handles the SQL string and parameter values per the JDBC contract, preventing data values from becoming part of SQL syntax. However, `?` **cannot** replace table names, column names, SQL keywords, or arbitrary `ORDER BY` clauses. If users can choose sort columns, map them against an application-defined allowlist of valid names.

`PreparedStatement` also allows reusing the same SQL template with different sets of values. Whether the database actually creates a server-side prepared statement and caches execution plans depends on the driver, configuration, and database; do not assume every driver optimizes identically.

### 4.2. Data Types and NULL Values

Choose the setter matching the SQL type:

```java
ps.setLong(1, 1001L);
ps.setString(2, "an@example.test");
ps.setBigDecimal(3, new BigDecimal("150000.50"));
ps.setNull(4, java.sql.Types.VARCHAR);
```

`setNull(index, sqlType)` sends a SQL `NULL` value with type metadata, unlike the string `"null"`. Java types and SQL types do not always map one-to-one; date/time types, decimals, UUIDs, or JSON may require driver-specific APIs or configuration.

### 4.3. Retrieving Database-Generated Keys

If the `id` column is generated by the database, you can request `getGeneratedKeys()`:

```java
String sql = "INSERT INTO customers (full_name, email) VALUES (?, ?)";
try (PreparedStatement ps = conn.prepareStatement(
        sql, Statement.RETURN_GENERATED_KEYS)) {
    ps.setString(1, "Nguyen An");
    ps.setString(2, "an@example.test");
    ps.executeUpdate();

    try (ResultSet keys = ps.getGeneratedKeys()) {
        if (keys.next()) {
            long generatedId = keys.getLong(1);
            System.out.println("ID: " + generatedId);
        }
    }
}
```

ID generation syntax and generated-key support vary across DBMSs. Spring Data JDBC handles most ID generation/retrieval automatically during entity saving when supported by the mapping and database dialect.

## 5. ResultSet: Reading Results Row by Row

`ResultSet` is not a pre-mapped Java `List`. It exposes returned data via a JDBC cursor. After `executeQuery()`, you must call `next()` to advance to the first row; each successful `next()` call moves the cursor to the next row.

Example reading a customer by ID:

```java
record Customer(long id, String fullName, String email) {}

static Optional<Customer> findById(DataSource dataSource, long id)
        throws SQLException {
    String sql = """
            SELECT id, full_name, email
            FROM customers
            WHERE id = ?
            """;

    try (Connection conn = dataSource.getConnection();
         PreparedStatement ps = conn.prepareStatement(sql)) {
        ps.setLong(1, id);

        try (ResultSet rs = ps.executeQuery()) {
            if (!rs.next()) {
                return Optional.empty();
            }
            Customer customer = new Customer(
                    rs.getLong("id"),
                    rs.getString("full_name"),
                    rs.getString("email")
            );
            return Optional.of(customer);
        }
    }
}
```

This snippet requires importing `java.sql.*`, `java.util.Optional`, and `javax.sql.DataSource`. It assumes `id` is non-`NULL` since it is the primary key.

If the query can return multiple rows, use `while (rs.next())` instead of `if (rs.next())`:

```java
List<Customer> customers = new ArrayList<>();
while (rs.next()) {
    customers.add(new Customer(
            rs.getLong("id"),
            rs.getString("full_name"),
            rs.getString("email")
    ));
}
```

Tips when mapping data:

- You can read columns by **1-based** index (`getString(2)`) or by name/alias (`getString("full_name")`). Explicit aliases reduce mapping mistakes in queries with `JOIN`s.
- For primitive getters such as `getLong(...)`, SQL `NULL` may be converted to `0`; call `rs.wasNull()` right after the getter when you need to distinguish `NULL` from `0`. For compatible types, `getObject("column", Long.class)` can preserve `null`, depending on driver support.
- `ResultSet` is normally **forward-only/read-only** under default `Connection.prepareStatement(...)` options. Do not assume you can scroll backward, update rows directly, or eagerly load all rows.
- `ResultSet` is tied to the `Statement` and `Connection` that created it. Never return a `ResultSet` directly out of a `try-with-resources` block that closes the connection; map it to objects/DTOs first.

For large result sets, avoid loading all rows into RAM unnecessarily. You can paginate in SQL, select only needed columns, or consider `setFetchSize(...)`. Batch fetching and server-side cursors depend on the database, driver, and transaction settings; **`setFetchSize` does not guarantee streaming** in every environment.

## 6. Complete Plain JDBC Example with H2

The following Java example creates an in-memory H2 database, creates a table, inserts a row, retrieves the generated ID, and queries by ID. The H2 JDBC driver must be present on the runtime classpath. If using Spring Boot dependency management, you can add `runtimeOnly 'com.h2database:h2'`; plain Java applications must declare an appropriate H2 version.

```java
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public class JdbcBasics {
    public static void main(String[] args) throws SQLException {
        String url = "jdbc:h2:mem:learn_db;DB_CLOSE_DELAY=-1";

        try (Connection conn = DriverManager.getConnection(url, "sa", "")) {
            try (Statement ddl = conn.createStatement()) {
                ddl.executeUpdate("""
                        CREATE TABLE customers (
                            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                            full_name VARCHAR(100) NOT NULL,
                            email VARCHAR(255) NOT NULL UNIQUE
                        )
                        """);
            }

            long newId;
            String insertSql =
                    "INSERT INTO customers (full_name, email) VALUES (?, ?)";

            try (PreparedStatement insert = conn.prepareStatement(
                    insertSql, Statement.RETURN_GENERATED_KEYS)) {
                insert.setString(1, "Nguyen An");
                insert.setString(2, "an@example.test");
                int rows = insert.executeUpdate();
                if (rows != 1) {
                    throw new SQLException("INSERT did not create exactly one row");
                }

                try (ResultSet keys = insert.getGeneratedKeys()) {
                    if (!keys.next()) {
                        throw new SQLException("Database did not return a new ID");
                    }
                    newId = keys.getLong(1);
                }
            }

            try (PreparedStatement find = conn.prepareStatement(
                    "SELECT id, full_name, email FROM customers WHERE id = ?")) {
                find.setLong(1, newId);

                try (ResultSet rs = find.executeQuery()) {
                    while (rs.next()) {
                        System.out.printf("%d | %s | %s%n",
                                rs.getLong("id"),
                                rs.getString("full_name"),
                                rs.getString("email"));
                    }
                }
            }
        }
    }
}
```

Sample output:

```text
1 | Nguyen An | an@example.test
```

The actual ID value is assigned by the database. The parameter `DB_CLOSE_DELAY=-1` keeps the in-memory H2 database alive inside the JVM process after the last connection closes; this is for learning examples, not durable storage. An in-memory H2 database loses all data when the JVM exits.

In this example:

1. `DriverManager` finds the driver handling `jdbc:h2:...` and obtains a `Connection`.
2. `Statement` executes the table creation DDL with no user input.
3. `PreparedStatement` binds name/email to `?` and executes `INSERT`.
4. `getGeneratedKeys()` returns a `ResultSet` containing the new ID.
5. `executeQuery()` returns another `ResultSet` containing the selected row.
6. JDBC objects are closed via `try-with-resources`.

## 7. Where Do These Components Sit in Spring Data JDBC?

With Spring Boot, you typically configure `spring.datasource.*` so Boot creates a `DataSource`; when HikariCP is on the classpath (normally via the JDBC starters), the pool manages borrowing and returning connections. **Spring JDBC** uses `JdbcTemplate` or `NamedParameterJdbcTemplate` to open/close resources properly, bind parameters, and translate `SQLException` into Spring's `DataAccessException` hierarchy.

Example using `JdbcTemplate`:

```java
@Repository
class CustomerQueries {
    private final JdbcTemplate jdbc;

    CustomerQueries(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    List<Customer> findByEmail(String email) {
        return jdbc.query(
                "SELECT id, full_name, email FROM customers WHERE email = ?",
                (rs, rowNum) -> new Customer(
                        rs.getLong("id"),
                        rs.getString("full_name"),
                        rs.getString("email")),
                email
        );
    }
}
```

`JdbcTemplate` still uses the JDBC driver, `Connection`, `PreparedStatement`, and `ResultSet` underneath; the application simply avoids managing each resource manually. With `NamedParameterJdbcTemplate`, you can write parameters like `:email`; Spring converts them into appropriate JDBC parameters before sending to the driver. **Raw JDBC uses `?` and does not understand `:email` syntax.**

At the **Spring Data JDBC** level, you work with entities and repositories:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.jdbc.repository.config.EnableJdbcRepositories;
import org.springframework.data.relational.core.mapping.Table;
import org.springframework.data.repository.CrudRepository;

@Table("customers")
record Customer(@Id Long id, String fullName, String email) {}

interface CustomerRepository extends CrudRepository<Customer, Long> {}
```

In a Spring Boot application properly configured for Spring Data JDBC, the repository can run:

```java
Customer saved = repository.save(
        new Customer(null, "Nguyen An", "an@example.test"));

Optional<Customer> found = repository.findById(saved.id());
```

Here, you do not write `PreparedStatement` or read `ResultSet` yourself: Spring Data JDBC constructs SQL, binds values, executes through the JDBC infrastructure, and maps results using metadata. Default column naming rules typically map `fullName` to `full_name`; naming strategy configuration and annotations can customize this. **Spring Data JDBC does not auto-generate table schemas by default**: the application needs an existing compatible schema, typically managed via migrations or initialization scripts.

Spring Data JDBC is not JPA/Hibernate. It has no persistence context or automatic dirty checking like JPA; `save`, `findById`, and repository operations follow Spring Data JDBC semantics and the **aggregate** model. Even though you operate at a higher level, everything still relies on the JDBC concepts covered in this lesson.

## 8. Common Errors and How to Diagnose Them

| Symptom | Common Cause | How to Check |
| --- | --- | --- |
| `No suitable driver` | Missing driver JAR on runtime classpath, malformed JDBC URL, or mismatched driver | Check runtime dependencies and the `jdbc:...` prefix. |
| Cannot open `Connection` | Database not running, wrong host/port, missing permissions, or wrong credentials | Check DB status, network, credentials, and connection URL. |
| SQL syntax error / table not found | SQL incompatible with dialect, table/column not created, or wrong schema | Test SQL directly against the target DB; check migrations and object names. |
| `Parameter index out of range` | Count or index of `setXxx(...)` does not match `?` placeholders | Count parameter markers and remember indices are 1-based. |
| Cannot read column name | Query lacks the expected column or uses a different alias | Match `SELECT` columns against `rs.getXxx("alias")`. |
| Pool exhausted / hanging queries | Connection not closed, slow queries/transactions, or pool too small for load | Ensure resources are closed; measure query duration and connection hold time. |
| Reading `0` when SQL data is `NULL` | Using primitive getters without checking `wasNull()` | Use `wasNull()` or an appropriate nullable Java type. |
| Partial writes persisted even though a later step failed | Statements ran under separate auto-commits without a surrounding transaction | Use JDBC transactions properly or `@Transactional` in Spring. |

`SQLException` carries details such as message, `SQLState`, and vendor-specific error codes. Inspect the root cause in the exception chain when diagnosing; production applications should log sufficient technical context while avoiding logging passwords and sensitive data values.

## 9. Tracing a Single Query End-to-End

Reading a customer by ID typically follows this sequence:

**Select driver/`DataSource` → borrow `Connection` → prepare SQL via `PreparedStatement` → bind ID with `setLong(1, id)` → `executeQuery()` → iterate `ResultSet` via `next()` → map columns to a Java object → close `ResultSet` and statement → return connection.**

Whenever you see a Spring Data JDBC method like `findById`, you can use this chain to explain where data comes from, where the transaction sits, which resources are held during the query, and why driver and pool configuration affect the application.

### Practice Exercises

1. Modify the H2 example to look up a customer by email using a `PreparedStatement`; test an email containing a single quote and observe why passing it via `setString` remains safe.
2. Add a nullable `phone` column and try two ways of reading: `getString("phone")` and an optional numeric column with `getLong(...)` + `wasNull()`.
3. Execute two `UPDATE` statements in one transaction; intentionally cause an error in the second statement and observe the result after `rollback()`, then compare with auto-commit enabled.
