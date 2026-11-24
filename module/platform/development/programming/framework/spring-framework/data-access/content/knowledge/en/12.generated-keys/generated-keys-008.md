# Driver- and Database-Dependent Key Retrieval Capabilities

When inserting a record with Spring JDBC, the application often needs the database-assigned `id` to return to an API or create related records. However, a successful `INSERT` **does not automatically mean** JDBC will return the generated key. The result depends simultaneously on the table's value-generation mechanism, the database management system (DBMS), the JDBC driver version, the SQL statement form, and how the application requests the key.

This lesson focuses on the **limits and verification of generated-keys retrieval** in `JdbcTemplate`, `KeyHolder`, and `SimpleJdbcInsert`. Generated keys here can be numeric primary keys, UUIDs, or columns populated by `DEFAULT`/`IDENTITY`/sequence/trigger. Not every database-generated value is returned by the driver as a generated key.

## 1. Distinguishing three commonly confused responsibilities

1. **DB generates the key:** For example, `orders.id` is assigned by an identity column. The DB can create a valid record without the application supplying `id`.
2. **Driver retrieves the key:** After executing `INSERT`, the JDBC driver must support capturing and returning the result via `Statement.getGeneratedKeys()`. This support varies by DBMS + driver pair.
3. **Spring reads the key:** Spring receives the result from the driver and puts it into `KeyHolder` or returns it from `SimpleJdbcInsert.executeAndReturnKey(...)`. Spring cannot manufacture a key that the driver/SQL does not return.

For example, `jdbcTemplate.update("INSERT ...", args...)` returns the **number of affected rows**, not the new `id`. If the method returns `1`, that merely means one row was updated/inserted. Do not use that value as the key.

| Component | Role | What to verify |
| --- | --- | --- |
| DB schema | Defines which columns are auto-generated | `IDENTITY`, sequence, `DEFAULT`, trigger, UUID; does it actually generate a value on `INSERT`? |
| DBMS | Governs SQL and what data can be returned | Does it support `RETURNING`/`OUTPUT` or an equivalent mechanism? |
| JDBC driver | Implements `prepareStatement`, `getGeneratedKeys`, and type mapping | Does it return the right column, right row count, and right type for this operation? |
| Spring JDBC | Manages resources and wraps results | Was key retrieval enabled and `KeyHolder` read properly? |

## 2. How does JDBC request and return keys?

JDBC supports creating a `PreparedStatement` with a generated-keys request in these ways:

~~~java
// Option A: let the driver decide which key to return
PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO orders (description) VALUES (?)",
        Statement.RETURN_GENERATED_KEYS);

// Option B: explicitly specify the column name to retrieve (if supported by driver)
PreparedStatement psByName = connection.prepareStatement(
        "INSERT INTO orders (description) VALUES (?)",
        new String[] {"id"});
~~~

These are two **illustrative options**, not two variables to initialize simultaneously for one insert statement. Run `executeUpdate()` and then read `ps.getGeneratedKeys()` before closing the statement. `getGeneratedKeys()` returns a `ResultSet`, which may have zero rows or one/multiple columns depending on actual behavior.

- `Statement.RETURN_GENERATED_KEYS`: convenient when the driver auto-detects the generated column; not guaranteed to return the `id` column on every DB.
- Column-name array `new String[] {"id"}`: explicitly requests the column to return; some drivers do not support this form, or differ on case sensitivity/schema rules.
- Column-index array `int[]`: also a JDBC variant, though the index must match column definitions accepted by the driver.
- If the generated-keys mechanism is not enabled when creating the statement, `getGeneratedKeys()` can be empty even when `INSERT` succeeds.

`DatabaseMetaData.supportsGetGeneratedKeys()` indicates whether the driver reports supporting generated-keys retrieval. Under the JDBC contract, when returning `true`, the driver must support returning keys for at least some `INSERT` statements. Still, `true` is **not a guarantee** for every table, key type, column-name argument, or batch. Returning `false` means you should not rely on the standard generated-keys API; the DB may still offer custom `RETURNING`/`OUTPUT` syntax.

A driver can throw `SQLFeatureNotSupportedException` when using a `prepareStatement` variant it does not implement. When the statement runs but the key list is empty, inspect the SQL, generated column, key request, and how the driver returns results.

## 3. Standalone JDBC example to probe driver support

The following example is a **complete Java 17+ program** using standard JDBC and H2 2.x as the test DB. File `GeneratedKeysProbe.java`:

~~~java
import java.sql.Connection;
import java.sql.DatabaseMetaData;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

public class GeneratedKeysProbe {
    public static void main(String[] args) throws SQLException {
        String url = "jdbc:h2:mem:keys_demo;DB_CLOSE_DELAY=-1";

        try (Connection connection =
                     DriverManager.getConnection(url, "sa", "")) {
            try (Statement statement = connection.createStatement()) {
                statement.executeUpdate("""
                        CREATE TABLE orders (
                            id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                            description VARCHAR(100) NOT NULL
                        )
                        """);
            }

            DatabaseMetaData metadata = connection.getMetaData();
            System.out.println("supportsGetGeneratedKeys="
                    + metadata.supportsGetGeneratedKeys());

            String sql = "INSERT INTO orders (description) VALUES (?)";
            try (PreparedStatement ps = connection.prepareStatement(
                    sql, new String[] {"ID"})) {
                ps.setString(1, "demo");
                int affected = ps.executeUpdate();

                try (ResultSet keys = ps.getGeneratedKeys()) {
                    if (!keys.next()) {
                        throw new SQLException(
                                "INSERT succeeded but no key was returned");
                    }
                    long id = keys.getLong(1);
                    if (keys.wasNull()) {
                        throw new SQLException("Generated id is SQL NULL");
                    }

                    System.out.println("affected=" + affected);
                    System.out.println("id=" + id);
                }
            }
        }
    }
}
~~~

Compile with JDK 17+:

~~~bash
javac GeneratedKeysProbe.java
~~~

Place the 2.x `h2.jar` driver on the classpath when running (Java needs the corresponding JDBC driver):

~~~bash
# Linux/macOS
java -cp ".:h2.jar" GeneratedKeysProbe

# Windows PowerShell / cmd
java -cp ".;h2.jar" GeneratedKeysProbe
~~~

With H2 2.x, a fresh database and fresh table, the expected output is:

~~~text
supportsGetGeneratedKeys=true
affected=1
id=1
~~~

`id=1` holds for this newly created table; real applications should not assume every key starts at 1 or increments contiguously. The example properly closes `Connection`, `Statement`, and `ResultSet` using try-with-resources, so no JDBC resources leak. Switching to another driver/DB may require adjusting the URL, DDL, column names, or how generated keys are requested.

## 4. Retrieving keys with Spring JdbcTemplate and KeyHolder

Suppose the `orders` table has a DB-generated `id BIGINT` column and a `description` column. In an application configured with `DataSource` and Spring JDBC, the repository class below illustrates how to pass the key request properly. This is a **complete repository-level Java class**: it requires Spring JDBC, a DB driver, and an existing `orders` table; it is not a standalone `main` program.

~~~java
import java.sql.PreparedStatement;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;

public final class OrderRepository {
    private final JdbcTemplate jdbcTemplate;

    public OrderRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public long create(String description) {
        String sql = "INSERT INTO orders (description) VALUES (?)";
        KeyHolder keyHolder = new GeneratedKeyHolder();

        int affected = jdbcTemplate.update(connection -> {
            PreparedStatement ps = connection.prepareStatement(
                    sql, new String[] {"id"});
            ps.setString(1, description);
            return ps;
        }, keyHolder);

        if (affected != 1) {
            throw new IllegalStateException(
                    "Expected one inserted row, got " + affected);
        }

        Number key = keyHolder.getKey();
        if (key == null) {
            throw new IllegalStateException(
                    "Driver did not return a generated id");
        }
        return key.longValue();
    }
}
~~~

**Execution flow:** `JdbcTemplate` borrows a connection from `DataSource`, invokes the callback to create a `PreparedStatement` with the generated-key column list, binds the `description` parameter, runs `INSERT`, reads `getGeneratedKeys()`, and puts the result into `GeneratedKeyHolder`. It closes resources per Spring's contract. If the application uses Spring transactions, the transaction-bound connection is managed accordingly.

Important notes:

- `KeyHolder` is an **output** container; merely creating `new GeneratedKeyHolder()` while forgetting to request keys in `prepareStatement` gives the driver no reason to return `id`.
- `getKey()` is only suitable for **one row, one numeric key column**. If the driver returns multiple columns or multiple rows, this method can throw an exception; inspect `getKeys()` or `getKeyList()`.
- Do not cast directly to `Long`: the driver may return `Integer`, `Long`, or another `Number`. `key.longValue()` is appropriate when the column and value range truly fit within `long`; handle type/precision separately if values can be larger.
- Create a fresh `KeyHolder` per insert operation; do not share a stateful instance across concurrent requests.
- Checking both `affected` and the key is important. Do not conflate these two pieces of information into one.

If a driver only supports the generic flag, replace `new String[] {"id"}` with `Statement.RETURN_GENERATED_KEYS` after **verifying on the actual driver/DB pair**. Do not switch blindly: some drivers return a different column than the expected key when using the generic flag.

## 5. When using SimpleJdbcInsert

`SimpleJdbcInsert` leverages JDBC metadata to reduce SQL boilerplate. You can configure the table name, input columns, and generated-key columns:

~~~java
import java.util.Map;
import javax.sql.DataSource;

import org.springframework.jdbc.core.simple.SimpleJdbcInsert;

public final class SimpleOrderRepository {
    private final SimpleJdbcInsert insertOrder;

    public SimpleOrderRepository(DataSource dataSource) {
        this.insertOrder = new SimpleJdbcInsert(dataSource)
                .withTableName("orders")
                .usingColumns("description")
                .usingGeneratedKeyColumns("id");
    }

    public long create(String description) {
        Number id = insertOrder.executeAndReturnKey(
                Map.of("description", description));
        return id.longValue();
    }
}
~~~

Here `usingGeneratedKeyColumns("id")` declares the column to return, while `usingColumns("description")` restricts the columns included in `INSERT`. Do not pass `id` as an auto-generated parameter. `executeAndReturnKey(...)` returns a `Number` for a single numeric key; for multiple columns or non-numeric keys, use `executeAndReturnKeyHolder(...)` and read the structure inside `KeyHolder`.

**Boundaries of the convenience API:** metadata helps Spring decide how to construct the SQL/statement, but it still relies on the driver. A driver reporting incomplete metadata or differing support across key-retrieval variants can make the same `SimpleJdbcInsert` setup work on DB A yet fail on DB B. When you need exact control over SQL and column names, `JdbcTemplate` with `PreparedStatementCreator` is often easier to diagnose.

## 6. Returned columns and data types are not always identical

`GeneratedKeyHolder` stores the general structure `List<Map<String, Object>>`: each map corresponds to the set of generated-key columns for one result row returned by the driver. For one row and multiple columns:

~~~java
Map<String, Object> generated = keyHolder.getKeys();
if (generated == null || generated.isEmpty()) {
    throw new IllegalStateException("No generated columns returned");
}
System.out.println(generated);
~~~

The snippet above **illustrates reading the result of an executed operation**, assuming `keyHolder` was created/populated as before; it is not a standalone `main` program. Map keys may be `id`, `ID`, or another name/label depending on the driver. With `UUID`, the value may be `java.util.UUID`, `String`, or another JDBC type; verify the actual type before converting.

`ResultSet` column indexes start at 1; `rs.getLong(1)` is the **first column in the generated-keys result**, not necessarily the first column of the table. Do not rely on the ordering of multiple columns without verification. When calling `getKey()` on a multi-column result, the error stems from a **wrong structural assumption**, not necessarily a failed insert.

Situations where behavior commonly changes:

- Tables using `IDENTITY`/auto-increment: usually the simplest case; still verify the driver and key-request method.
- Tables generating keys via sequence or trigger: key retrieval depends on the DB and may require specifying columns or dedicated SQL.
- DB-generated `UUID` values: do not assume a `Number`; use multi-type reading APIs or SQL explicitly returning columns.
- Multi-row/batch `INSERT`: the driver may return multiple key rows, fewer rows than inserted, or not guarantee pairing keys with inputs as expected. Test specifically rather than grabbing a single value.

## 7. Differences across database systems

The table below provides **guidance for choosing a strategy**, not a promise across all driver versions:

| DBMS | Approach to verify | Risks to keep in mind |
| --- | --- | --- |
| PostgreSQL | `getGeneratedKeys()` via JDBC; when explicit values are needed, SQL `INSERT ... RETURNING id` | `RETURNING` syntax is DB-specific; driver and column type determine the received Java value |
| MySQL/MariaDB | `AUTO_INCREMENT` and JDBC driver normally support generated-key retrieval | Do not generalize from `AUTO_INCREMENT` to every trigger/default/UUID case; batch behavior can differ |
| Oracle Database | Specify the generated-key column name if accepted by the driver; for complex needs, consider appropriate `RETURNING ... INTO` syntax | Some Oracle JDBC drivers/versions return `ROWID` when using only the generic `RETURN_GENERATED_KEYS` flag |
| SQL Server | JDBC driver and `IDENTITY` column; SQL `OUTPUT INSERTED.id` when explicit output control is needed | `OUTPUT` has its own semantics and restrictions with certain triggers/statements; must be tested |
| H2 (test) | Convenient for testing `IDENTITY` and `getGeneratedKeys()` | Passing on H2 does not prove PostgreSQL/Oracle/MySQL/SQL Server in production will behave identically |

Never list a DBMS as “supported” and conclude that every version, every `INSERT` form, and every key type are compatible. The unit you must verify is **DBMS + server version + JDBC driver/version + schema + SQL form + row count**.

### Direct result-returning SQL when JDBC generated keys do not fit

**PostgreSQL-specific** example:

~~~sql
INSERT INTO orders (description)
VALUES ('demo')
RETURNING id;
~~~

In Spring JDBC, if the PostgreSQL environment supports this statement, you can fetch the value directly from the SQL statement's result set:

~~~java
Long id = jdbcTemplate.queryForObject(
        "INSERT INTO orders (description) VALUES (?) RETURNING id",
        Long.class,
        "demo");
if (id == null) {
    throw new IllegalStateException("INSERT RETURNING returned null id");
}
~~~

This is a **code fragment used in a DAO that has `jdbcTemplate`**, not a standalone Java class; `RETURNING` SQL must be executed by the driver as a statement returning a result set. Do not copy this syntax verbatim to MySQL/Oracle/SQL Server. When a DB uses `RETURNING ... INTO` or `OUTPUT INSERTED...`, write it according to the DB's documentation and use the appropriate JDBC/Spring API.

Functions that fetch the “last id” per connection are another DBMS mechanism, usually tied to a specific session/connection. Never run `INSERT` on one pooled connection and read the session value on an arbitrary connection. **Never use `SELECT MAX(id)` to find the newly inserted key**: other users can insert concurrently.

## 8. Verify actual capabilities before depending on them

In a class with `JdbcTemplate`, you can query metadata on a Spring-provided connection:

~~~java
import org.springframework.jdbc.core.ConnectionCallback;

Boolean supported = jdbcTemplate.execute(
        (ConnectionCallback<Boolean>) connection ->
                connection.getMetaData().supportsGetGeneratedKeys());
System.out.println("Driver reports generated keys: " + supported);
~~~

This is an **illustrative snippet** in an environment that already has `jdbcTemplate`, not a runnable standalone class. You can also inspect `getDatabaseProductName()`, `getDatabaseProductVersion()`, `getDriverName()`, and `getDriverVersion()` from the same `DatabaseMetaData` to record the exact DB/driver pair in use.

A reliable test includes:

1. Identify the actual generated column and schema (identity, sequence, default, trigger); record DB/driver/version.
2. Check `supportsGetGeneratedKeys()` as an initial signal; **do not treat it as an end-to-end test**.
3. In the integration test database, execute an `INSERT` with known data using the exact SQL/`PreparedStatement` the application will use.
4. Check simultaneously: affected row count, returned key row count, column count, column names, Java types, non-`null`, and whether the value matches the newly inserted record.
5. Test each needed branch: single insert, batch/multi-row, numeric key or UUID, trigger/default; if running across multiple DBs/drivers, use a test matrix for real combinations.
6. Create a controlled failure case (e.g., invalid SQL or constraint-violating insert) to confirm the application does not return a stale key and does not perform unsafe retries.

For example, an integration test expecting **one** numeric key should assert: exactly one row was inserted, `KeyHolder.getKey() != null`, valid type/conversion, and re-reading the same record with the returned `id` in the same transaction/test setup. Tests passing on H2 only verify H2; production compatibility tests must run against the production DB/driver or an equivalent environment.

## 9. When key retrieval fails: symptom-based diagnosis

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| `update(...)` returns `1`, `getKey()` is `null` or key list is empty | Key retrieval not enabled; DB did not generate expected column; driver did not return keys | Check DDL, `prepareStatement` callback, SQL, metadata, and raw `getGeneratedKeys()` output |
| `SQLFeatureNotSupportedException` | Driver lacks the invoked `prepareStatement`/generated-keys variant | Check driver version, try the generic flag, or use tested DB-specific result-returning SQL |
| Receiving `ROWID`/a column other than `id` | Driver auto-selected a column different from application assumptions | Try specifying column name explicitly; inspect result column metadata; for Oracle check driver docs |
| `getKey()` throws error about multiple columns/rows | Single-value API used on a complex result | Read `getKeys()` or `getKeyList()` and inspect actual structure |
| `ClassCastException`/numeric type mismatch | Driver returned a different type; hard cast used | Read as `Number` or driver-returned type; check overflow/precision |
| Works locally but fails in production | Differences in DB, driver, DDL, column name casing, batch behavior | Compare versions + schema + SQL; add integration tests for production target |
| Batch returns missing keys or unclear order | Driver limitations in returning batch generated keys | Verify count/correlation; consider row-by-row insert or dedicated SQL if exact matching is mandatory |

**Transaction note:** obtaining an `id` does not mean the transaction has committed. A transaction can roll back after the id is allocated; sequences/identities can leave gaps in key numbering. If the insert succeeds but key retrieval fails under auto-commit, the record **may already exist**; do not blindly re-run the insert immediately as that will create duplicate records. Design transactions and error handling intentionally.

## 10. Selection rules in a Spring JDBC project

- **Single numeric id, driver verified to support it:** use `JdbcTemplate.update(PreparedStatementCreator, KeyHolder)` or `SimpleJdbcInsert.executeAndReturnKey(...)`.
- **Want control over column name, SQL, return type:** use `JdbcTemplate` with `prepareStatement(sql, new String[] {"id"})`; verify actual driver output.
- **Single row with multiple generated columns or non-numeric key:** use `KeyHolder.getKeys()`/`executeAndReturnKeyHolder(...)` and inspect column names/types.
- **Batch needing exact key-to-input pairing:** use batch generated-keys APIs only after verifying behavior on the real driver; otherwise consider changing the insert strategy.
- **Driver fails standard JDBC requirements but DB has result-returning SQL:** use `RETURNING`/`OUTPUT` or that DB's official technique and encapsulate the difference in the repository.

Key principle: **the DB's ability to generate keys, JDBC's ability to retrieve keys, and Spring's ability to wrap keys are three separate things**. Verify the application's exact SQL/driver/DB variant, handle empty or mistyped results explicitly, and keep DB-specific logic in the data access layer.

## References

- [Java SE — `DatabaseMetaData.supportsGetGeneratedKeys()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.sql/java/sql/DatabaseMetaData.html): JDBC capability contract.
- [Spring Framework — Retrieving Auto-generated Keys in `JdbcTemplate`](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): callbacks, `KeyHolder`, and key-return flow.
- [Spring Framework — `SimpleJdbcInsert` and generated keys](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html): `usingGeneratedKeyColumns`, `executeAndReturnKey`, `executeAndReturnKeyHolder`.
- [Spring Framework — `KeyHolder` API](https://docs.spring.io/spring-framework/docs/6.0.17/javadoc-api/org/springframework/jdbc/support/KeyHolder.html): `getKey`, `getKeys`, `getKeyList`.
- [Oracle JDBC — auto-generated keys](https://docs.oracle.com/en/database/oracle/oracle-database/18/jjdbc/JDBC-standards-support.html): driver notes on retrieving key columns and `ROWID`.
