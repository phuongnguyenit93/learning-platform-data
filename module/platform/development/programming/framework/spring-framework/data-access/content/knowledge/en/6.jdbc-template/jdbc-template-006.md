# PreparedStatementCreator and PreparedStatementSetter in JdbcTemplate

> **Topic:** Spring Framework JdbcTemplate. This article explains two core callbacks used with JDBC `PreparedStatement`: **`PreparedStatementCreator` creates a statement from a `Connection` supplied by Spring**, whereas **`PreparedStatementSetter` binds parameter values onto an already-created statement**. Both give developers control over necessary JDBC details while letting `JdbcTemplate` handle execution, exception translation, and resource cleanup.

## 1. The Problem: Why Does `JdbcTemplate` Have Two Callbacks?

Suppose the data layer needs to store a product with `sku`, `price`, and `stock`, and then read the list of products with minimum stock. The SQL uses `?` placeholders for parameters:

~~~sql
INSERT INTO product (sku, price, stock) VALUES (?, ?, ?);

UPDATE product SET stock = ? WHERE id = ?;

SELECT id, sku, price, stock
FROM product
WHERE stock >= ?
ORDER BY id;
~~~

There are **two technical responsibilities** that commonly sit together in plain JDBC code:

1. **Creating the statement:** Calling `Connection.prepareStatement(sql)`, or a variant with `Statement.RETURN_GENERATED_KEYS`, `ResultSet.TYPE_FORWARD_ONLY`, or special options.
2. **Configuring the statement:** Calling `ps.setString(1, sku)`, `ps.setBigDecimal(2, price)`, `ps.setInt(3, stock)`, and appropriate setter methods.

`PreparedStatementCreator` represents the first responsibility, optionally including parameter binding when writing the callback yourself. `PreparedStatementSetter` focuses on the second responsibility, used when `JdbcTemplate`'s default statement-creation setup is sufficient. Most routine CRUD queries can also use the shorter `update(sql, args...)` or `query(sql, rowMapper, args...)` overloads; you do not have to write a callback every time.

**Core point:** A callback is a way to pass behavior into `JdbcTemplate`, not a JDBC resource that callers open and close themselves.

## 2. Role in the Path from Application to Database

~~~mermaid
flowchart TD
    S["Service / Repository"] --> J["JdbcTemplate"]
    J --> C["DataSourceUtils: obtain transaction-aware Connection"]
    C --> CN["JDBC Connection"]
    J --> P{"How to create PreparedStatement?"}
    P -- "Standard SQL" --> A["JdbcTemplate calls Connection.prepareStatement(sql)"]
    P -- "Custom needed" --> B["PreparedStatementCreator.createPreparedStatement(conn)"]
    A --> PS["PreparedStatement"]
    B --> PS
    PS --> V["PreparedStatementSetter.setValues(ps) or creator binds"]
    V --> E["executeQuery / executeUpdate"]
    E --> DB[("Database")]
    DB --> RM["RowMapper / ResultSetExtractor or affected row count"]
    RM --> J
    J --> R["Close Statement/ResultSet, release Connection properly"]
    R --> S
~~~

The diagram illustrates responsibilities. For `update(PreparedStatementCreator)`, the creator creates and can bind parameters itself; not every overload runs an additional separate setter. `JdbcTemplate` acquires the connection via Spring infrastructure, manages JDBC statements/result sets, translates `SQLException` into `DataAccessException`, and releases the connection according to the transaction. Inside an active Spring transaction, releasing does not mean physically closing the connection before the transaction ends.

### Comparison with Plain JDBC

With plain JDBC, the code typically handles everything manually:

~~~java
// Illustrative fragment: dataSource and variables are already initialized.
try (Connection con = dataSource.getConnection();
     PreparedStatement ps = con.prepareStatement(
         "UPDATE product SET stock = ? WHERE id = ?")) {

    ps.setInt(1, newStock);
    ps.setLong(2, productId);
    int changed = ps.executeUpdate();
}
~~~

With JdbcTemplate, you can write:

~~~java
// Equivalent fragment using Spring JdbcTemplate.
int changed = jdbcTemplate.update(
    "UPDATE product SET stock = ? WHERE id = ?",
    ps -> {
        ps.setInt(1, newStock);
        ps.setLong(2, productId);
    }
);
~~~

In the second example, the lambda has type `PreparedStatementSetter`, because the API takes **SQL** and a callback receiving a **`PreparedStatement`**. Never call `con.close()` or `ps.close()` inside the callback; `JdbcTemplate` owns that lifecycle. If you only need to bind two simple values, `jdbcTemplate.update(sql, newStock, productId)` is even shorter.

## 3. Exact Contract of the Two Functional Interfaces

Both interfaces belong to package `org.springframework.jdbc.core` and are compatible with Java 8+ lambdas.

### 3.1. `PreparedStatementCreator`

Core shape:

~~~java
@FunctionalInterface
public interface PreparedStatementCreator {
    PreparedStatement createPreparedStatement(Connection connection)
        throws SQLException;
}
~~~

The `Connection` passed in by JdbcTemplate is already bound to the appropriate DataSource and transaction context. The callback must **return a `PreparedStatement` created from the provided Connection**. It decides the SQL and statement creation options. For example:

~~~java
PreparedStatementCreator creator = connection -> {
    PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO product (sku, price, stock) VALUES (?, ?, ?)",
        Statement.RETURN_GENERATED_KEYS
    );
    ps.setString(1, sku);
    ps.setBigDecimal(2, price);
    ps.setInt(3, stock);
    return ps;
};
~~~

The creator **can bind parameters while creating the statement**, as shown above, because `JdbcTemplate.update(creator, keyHolder)` has no separate setter argument. If a creator also provides SQL via the `SqlProvider` interface, Spring can include more helpful SQL context in certain errors; this is optional and not required for lambdas.

### 3.2. `PreparedStatementSetter`

Core shape:

~~~java
@FunctionalInterface
public interface PreparedStatementSetter {
    void setValues(PreparedStatement ps) throws SQLException;
}
~~~

Here the SQL **has already been passed to JdbcTemplate** so the framework creates the statement. The setter only configures parameters and, where appropriate, minor statement properties before execution:

~~~java
String sql = "UPDATE product SET stock = ? WHERE id = ?";
PreparedStatementSetter setter = ps -> {
    ps.setInt(1, newStock);
    ps.setLong(2, productId);
};
int affected = jdbcTemplate.update(sql, setter);
~~~

`setValues` cannot choose different SQL or replace the statement object. Nor does it **call `executeUpdate()` itself** when used with `update(sql, setter)`: JdbcTemplate executes the statement after the setter finishes.

### 3.3. Differences You Must Not Overlook

| Criterion | `PreparedStatementCreator` | `PreparedStatementSetter` |
| --- | --- | --- |
| Parameter received by callback | `Connection` | `PreparedStatement` |
| Return value | `PreparedStatement` | `void` |
| Who decides how `prepareStatement(...)` is called? | The creator itself | JdbcTemplate, from the provided SQL |
| Can it set `?` parameter values? | Yes, by binding inside the creator or via an appropriate API | Yes, this is its primary purpose |
| Customize generated keys/result set mode on creation? | Suitable | Cannot choose a different `prepareStatement` overload once created |
| Can it be used with `SELECT` queries? | Yes | Yes |
| Does it manage Connection/closing itself? | No | No |
| Typical complexity | Higher, meant for special creation options | Lower, meant for parameter binding |

The name "Creator" refers only to **creating the PreparedStatement object**; it does **not** mean "creating a new record in the DB." A `SELECT` can also use `PreparedStatementCreator`. Similarly, "Setter" means setting JDBC parameter values, unrelated to Java entity getters/setters.

## 4. Execution Order and Resource Ownership

For a typical `jdbcTemplate.update(sql, setter)` call:

1. JdbcTemplate obtains a `Connection` from the DataSource via Spring's mechanism.
2. JdbcTemplate creates a `PreparedStatement` from the SQL.
3. JdbcTemplate invokes `setter.setValues(ps)` to bind parameters.
4. JdbcTemplate calls `ps.executeUpdate()` and retrieves the affected row count.
5. JdbcTemplate cleans up resources and releases the connection, respecting any active transaction.

For `jdbcTemplate.update(creator, keyHolder)`:

1. JdbcTemplate obtains a Connection.
2. Calls `creator.createPreparedStatement(connection)`; the creator typically calls `connection.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)` and binds values.
3. JdbcTemplate calls `executeUpdate()`, retrieves generated keys if supported by the driver, and populates `KeyHolder`.
4. JdbcTemplate closes the Statement and releases the Connection according to context.

How many times a callback runs is an API/operation detail; do not use callbacks for business side effects like sending emails or logging payments. A callback may run at a different point than callers assume with complex APIs; keep it short, pure JDBC, and transaction-safe.

**Do not do inside either callback:** call `connection.commit()`, `connection.rollback()`, `connection.close()`, `statement.close()`, open another DataSource, or silently swap the current connection. These actions break resource ownership and can conflict with Spring transactions.

## 5. Which `JdbcTemplate` Overload Should You Choose?

Commonly used overloads in Spring Framework 6.x:

| Goal | API | When to choose |
| --- | --- | --- |
| Simple data write | `update(String sql, Object... args)` | Sufficient when just binding a few values positionally |
| Write with explicit binding | `update(String sql, PreparedStatementSetter pss)` | Controlling `setNull`, JDBC types, custom setters, or statement properties |
| Write with custom statement creation | `update(PreparedStatementCreator psc)` | Need to call `Connection.prepareStatement` with specific options |
| Write and retrieve generated key | `update(PreparedStatementCreator psc, KeyHolder holder)` | INSERT with identity/sequence when driver supports generated keys |
| Query with RowMapper | `query(String sql, PreparedStatementSetter pss, RowMapper<T> rm)` | SQL is ready, need parameter binding and per-row mapping |
| Query with creator | `query(PreparedStatementCreator psc, RowMapper<T> rm)` | Need to customize how `PreparedStatement` is created |
| Fetch data via extractor | `query(String sql, PreparedStatementSetter pss, ResultSetExtractor<T> rse)` | Want to aggregate the whole ResultSet into one structure |
| Simple query | `query(String sql, RowMapper<T> rm, Object... args)` | Most SELECTs with normal parameter binding |

**API trap:** `JdbcTemplate` has an internal/protected `update(PreparedStatementCreator, PreparedStatementSetter)` method. Do not assume that is a public overload to call directly from an external Repository. In the public API, standard update cases pick **either creator or setter**, depending on the overload, or use `PreparedStatementCreatorFactory`.

For queries needing both a creator and a setter, JdbcTemplate has overloads like `query(PreparedStatementCreator, PreparedStatementSetter, ResultSetExtractor<T>)`. These are rarely needed in everyday application code; keep the API readable unless truly required.

## 6. Binding Parameters Properly: Position, SQL Type, Nulls, and Security

### Parameter Positions Start at 1

In JDBC, `?` indices start at **1**, not 0. For example:

~~~sql
UPDATE product
SET price = ?, stock = ?
WHERE id = ?;
~~~

~~~java
PreparedStatementSetter setter = ps -> {
    ps.setBigDecimal(1, price);
    ps.setInt(2, stock);
    ps.setLong(3, id);
};
~~~

Mixing up the order may not throw a SQLException if types are compatible, yet the data will be wrong; verify each placeholder and use clear variable names.

### Binding SQL NULL Values

`null` must be bound with an appropriate JDBC type when a column accepts `NULL`:

~~~java
// Fragment: table has a nullable INTEGER column named discount_percent.
PreparedStatementSetter setter = ps -> {
    ps.setString(1, sku);
    if (discountPercent == null) {
        ps.setNull(2, java.sql.Types.INTEGER);
    } else {
        ps.setInt(2, discountPercent);
    }
};
~~~

You can use `ps.setObject(index, value, Types.INTEGER)` with JDBC-compliant drivers; `setNull` explicitly declares the SQL type and is often clearer when control is needed. With `JdbcTemplate.update(sql, args...)`, you can use `SqlParameterValue` or an overload accepting an `argTypes` array to pass explicit SQL types.

### Other Data Types

- Monetary values should use `BigDecimal` and `ps.setBigDecimal(index, amount)`; avoid `double` for money when decimal precision matters.
- For dates/times, confirm timezone and database types. JDBC 4.2 supports mapping many `java.time` types via `setObject`, though exact behavior still depends on the driver and SQL type.
- For streams or large values, understand resource/parameter cleanup lifetimes and avoid closing streams before JdbcTemplate executes the statement.
- Use `ps.setString` for text values; **never** concatenate untrusted data into SQL.

### PreparedStatement Cannot Bind Table/Column Names

`?` only represents **data values**. You cannot write `SELECT * FROM ?` and bind a table name, or `ORDER BY ?` expecting the driver to turn it into a column name. For dynamic identifiers, choose from an application-controlled whitelist and build the SQL safely; never insert user input directly into SQL structure.

## 7. Standalone Runnable Example: Spring Boot + H2 + JdbcTemplate

This example uses **Java 21**, **Gradle**, **Spring Boot 3.3.5**, **Spring JDBC**, and **H2**. The files below are enough to run a console app with Boot's auto-configured `JdbcTemplate`; no PostgreSQL, Docker, or HTTP server is needed.

The example demonstrates:

1. `PreparedStatementCreator` calling `prepareStatement(sql, RETURN_GENERATED_KEYS)` and binding parameters for INSERT.
2. `GeneratedKeyHolder` retrieving the auto-generated key from H2.
3. `PreparedStatementSetter` binding data for UPDATE and SELECT.
4. `RowMapper` doing a different job from the two callbacks above: converting one ResultSet row into a Java object.
5. A creator also working for SELECT, not just INSERT.

### 7.1. Project Structure

~~~text
prepared-statement-callbacks/
├── build.gradle
└── src/main/
    ├── java/com/example/jdbccallbacks/
    │   ├── JdbcCallbacksApplication.java
    │   └── ProductRepository.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

### 7.2. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

`spring-boot-starter-jdbc` brings `JdbcTemplate` and a JDBC pool into the application; H2 is the runtime driver/database. This is a console app, so `spring-boot-starter-web` is unnecessary.

### 7.3. `src/main/resources/application.properties`

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:callbacks;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

Spring Boot runs `schema.sql` when the DataSource is initialized. `DB_CLOSE_DELAY=-1` prevents the in-memory H2 database from vanishing when the last connection closes, keeping the example independent of pool connection cycles.

### 7.4. `src/main/resources/schema.sql`

~~~sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    price DECIMAL(12, 2) NOT NULL CHECK (price >= 0),
    stock INTEGER NOT NULL CHECK (stock >= 0)
);
~~~

This schema creates an empty table with an `id` key auto-generated by H2; sample output assumes each run starts a fresh `mem:callbacks` database in its own JVM. The table structure fits the INSERT, UPDATE, and SELECT statements below.

### 7.5. `ProductRepository.java`

~~~java
package com.example.jdbccallbacks;

import java.math.BigDecimal;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.PreparedStatementCreator;
import org.springframework.jdbc.core.PreparedStatementSetter;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Repository;

@Repository
public final class ProductRepository {

    private static final String SELECT_COLUMNS =
        "SELECT id, sku, price, stock FROM product";

    private static final RowMapper<Product> PRODUCT_MAPPER =
        (rs, rowNum) -> new Product(
            rs.getLong("id"),
            rs.getString("sku"),
            rs.getBigDecimal("price"),
            rs.getInt("stock")
        );

    private final JdbcTemplate jdbc;

    public ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Creator: decides how to create the statement to retrieve the generated key.
    public long insertWithCreator(
            String sku, BigDecimal price, int stock) {

        String sql =
            "INSERT INTO product (sku, price, stock) VALUES (?, ?, ?)";

        PreparedStatementCreator creator = connection -> {
            PreparedStatement ps = connection.prepareStatement(
                sql, Statement.RETURN_GENERATED_KEYS
            );
            ps.setString(1, sku);
            ps.setBigDecimal(2, price);
            ps.setInt(3, stock);
            return ps;
        };

        GeneratedKeyHolder keyHolder = new GeneratedKeyHolder();
        int affected = jdbc.update(creator, keyHolder);

        if (affected != 1) {
            throw new IllegalStateException(
                "Expected one INSERT row, got " + affected
            );
        }
        Number id = keyHolder.getKey();
        if (id == null) {
            throw new IllegalStateException(
                "Database did not return generated id"
            );
        }
        return id.longValue();
    }

    // Setter: SQL is already provided, only bind ? placeholders in 1-based order.
    public int changeStockWithSetter(long id, int newStock) {
        String sql = "UPDATE product SET stock = ? WHERE id = ?";

        PreparedStatementSetter setter = ps -> {
            ps.setInt(1, newStock);
            ps.setLong(2, id);
        };

        return jdbc.update(sql, setter);
    }

    // Setter for SELECT; RowMapper processes each result row.
    public List<Product> findStockAtLeastWithSetter(int minimumStock) {
        String sql = SELECT_COLUMNS
            + " WHERE stock >= ? ORDER BY id";

        PreparedStatementSetter setter = ps ->
            ps.setInt(1, minimumStock);

        return jdbc.query(sql, setter, PRODUCT_MAPPER);
    }

    // Creator can also be used for SELECT and bind parameters itself.
    public List<Product> findBySkuWithCreator(String sku) {
        PreparedStatementCreator creator = connection -> {
            PreparedStatement ps = connection.prepareStatement(
                SELECT_COLUMNS + " WHERE sku = ?"
            );
            ps.setString(1, sku);
            return ps;
        };

        return jdbc.query(creator, PRODUCT_MAPPER);
    }

    public record Product(
        long id, String sku, BigDecimal price, int stock
    ) {}
}
~~~

Here four methods play distinct roles. `insertWithCreator` needs the generated-keys API; `changeStockWithSetter` just binds `?` into standard SQL; `findStockAtLeastWithSetter` binds then maps results; `findBySkuWithCreator` proves a creator is not limited to INSERT. `RowMapper` takes `(ResultSet, rowNum)`, completely different from `PreparedStatementSetter`.

Note on affected row counts: `JdbcTemplate.update(...)` returns the number of rows affected by UPDATE/INSERT, not the ID. For INSERTs needing an auto-generated ID, use `KeyHolder`; `GeneratedKeyHolder.getKey()` fits when the driver returns a single numeric key. If the DB/driver returns multiple generated key columns or non-numeric keys, check `getKeys()`/`getKeyList()` instead of assuming a single `Number`.

### 7.6. `JdbcCallbacksApplication.java`

~~~java
package com.example.jdbccallbacks;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class JdbcCallbacksApplication {
    public static void main(String[] args) {
        SpringApplication.run(JdbcCallbacksApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(ProductRepository repository) {
        return args -> {
            long id = repository.insertWithCreator(
                "JAVA-CORE", new BigDecimal("125.50"), 5
            );
            System.out.println("Generated id = " + id);

            int affected = repository.changeStockWithSetter(id, 7);
            System.out.println("Updated rows = " + affected);

            List<ProductRepository.Product> products =
                repository.findStockAtLeastWithSetter(3);
            System.out.println("Found = " + products.size());
            System.out.println("Stock = " + products.get(0).stock());

            int matchingSku = repository
                .findBySkuWithCreator("JAVA-CORE").size();
            System.out.println("By SKU = " + matchingSku);
        };
    }
}
~~~

### 7.7. Running and Reading Output

In the project directory containing `build.gradle`:

~~~bash
# If the project already has the Gradle Wrapper:
./gradlew bootRun

# If there is no Wrapper yet but a compatible Gradle is installed:
gradle bootRun
~~~

On Windows PowerShell, with the wrapper: `.\gradlew.bat bootRun`. Java 21 must be installed or Gradle configured for toolchain provisioning. The lines **printed by the program** (omitting Spring/HikariCP startup logs and Gradle messages) are:

~~~text
Generated id = 1
Updated rows = 1
Found = 1
Stock = 7
By SKU = 1
~~~

Steps in the example:

1. H2 creates an empty table; the first identity value is 1 in a fresh database.
2. `PreparedStatementCreator` creates a statement with the generated-keys flag, binds three parameters, and returns the statement to JdbcTemplate; `KeyHolder` retrieves ID = 1.
3. `PreparedStatementSetter` sets `stock=7` and `id=1`; `UPDATE` affects exactly one row.
4. The second setter binds threshold 3; RowMapper reads the record with stock 7.
5. The SELECT creator builds the statement, binds `sku`, and returns a list containing one matching product.

**Why does the example not call `executeQuery` inside the creator?** Because the creator's job is only to **create the statement**; `JdbcTemplate.query(...)` executes it and consumes the `ResultSet`. Nor should `ps.close()` be called inside the creator. Calling execute or close manually inside the callback breaks the template's intended resource management flow.

In real applications, validate input and affected row counts at the appropriate layer, place `@Transactional` boundaries around business workflows when multiple steps must be atomic, manage concurrency, and handle database errors such as unique constraint violations.

## 8. Deep Dive: Why Is a Creator Helpful for Retrieving Generated Keys?

There is an important JDBC distinction:

~~~java
connection.prepareStatement(sql);
connection.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS);
connection.prepareStatement(sql, new String[] { "ID" });
~~~

These overloads create `PreparedStatement`s with different options. If using a setter, the statement has already been created by JdbcTemplate from `String sql`; you cannot go back and pick a different `prepareStatement` overload.

With H2, using `Statement.RETURN_GENERATED_KEYS` as in the demo works well. Some drivers/databases require specifying the generated key column names explicitly; in that case, the creator can call `connection.prepareStatement(sql, new String[] { "id" })` (name/casing per driver). Verify `DatabaseMetaData.supportsGetGeneratedKeys()` and actual driver behavior.

`GeneratedKeyHolder` output is not guaranteed to always be a single `long` key. If a database has multiple generated columns, `getKey()` may be unsuitable; read the map/list and expected column names. The essential point is using a **creator that enables key retrieval**; passing a KeyHolder without creating a key-supporting statement will not force the DB to return keys.

## 9. `PreparedStatementCreatorFactory`: Reducing Repetitive Creator Code

When multiple operations share the same SQL template and parameter type list, Spring provides `PreparedStatementCreatorFactory`. It knows the SQL, declares JDBC types, and can produce creators or setters for given parameter arrays.

The example below is an **API fragment**, not a standalone Java file; it can be used inside a Repository that already has a `jdbc` field:

~~~java
String sql =
    "INSERT INTO product (sku, price, stock) VALUES (?, ?, ?)";

PreparedStatementCreatorFactory factory =
    new PreparedStatementCreatorFactory(
        sql, Types.VARCHAR, Types.DECIMAL, Types.INTEGER
    );
factory.setReturnGeneratedKeys(true);

PreparedStatementCreator creator =
    factory.newPreparedStatementCreator(
        new Object[] { "SPRING-BOOK", new BigDecimal("89.00"), 2 }
    );

GeneratedKeyHolder holder = new GeneratedKeyHolder();
int rows = jdbc.update(creator, holder);
~~~

Imports needed when integrating this fragment into code:

~~~java
import java.math.BigDecimal;
import java.sql.Types;
import org.springframework.jdbc.core.PreparedStatementCreator;
import org.springframework.jdbc.core.PreparedStatementCreatorFactory;
import org.springframework.jdbc.support.GeneratedKeyHolder;
~~~

The factory is useful when you want **explicit SQL type declarations**, consistency across repeated invocations, or generated-keys configuration without hand-writing statement-creation lambdas. You can also call `setGeneratedKeysColumnNames(...)`. Because the snippet above is not standalone, it has no separate stdout; `rows` is the INSERT row count, normally 1 on success.

**Do not confuse the API:** `PreparedStatementCreatorFactory.newPreparedStatementCreator(...)` creates a callback object; calling it **does not execute SQL yet**. SQL executes when the callback is passed to JdbcTemplate.

## 10. What Else Can `PreparedStatementSetter` Do Besides Binding `?`?

A setter receives a reference to the created `PreparedStatement`. Besides binding parameters, it can adjust valid properties on the statement before execution, for example:

~~~java
// Illustrative query fragment; RowMapper 'mapper' already exists.
PreparedStatementSetter setter = ps -> {
    ps.setInt(1, minimumStock);
    ps.setFetchSize(100);
    ps.setMaxRows(500);
};

List<Product> result = jdbc.query(
    "SELECT id, sku, price, stock FROM product " +
    "WHERE stock >= ? ORDER BY id",
    setter,
    mapper
);
~~~

These properties must align with the driver and `JdbcTemplate` configuration. `setFetchSize` is a **hint** guiding how the driver fetches rows; it does not mean the DB always returns exact 100-row chunks or that every driver streams. `setMaxRows` caps ResultSet rows at the JDBC level, not as a substitute for SQL pagination and indexes. When a transaction timeout is configured, Spring/JdbcTemplate may apply a transaction-linked statement timeout; do not arbitrarily override protective settings that are already configured.

### Streaming Queries

Some `queryForStream(...)` overloads return a Java Stream that must be **closed** after iteration:

~~~java
// Illustrative fragment; mapper is RowMapper<Product>.
try (var products = jdbc.queryForStream(
        "SELECT id, sku, price, stock FROM product",
        mapper
)) {
    products.limit(5).forEach(System.out::println);
}
~~~

This is a case where **the result resource has a different lifecycle from a materialized `List`**. Even though JdbcTemplate manages the statement, the caller consuming the stream must close the Stream per the API contract. Do not let a stream escape its transaction scope and attempt to read from it where a valid connection no longer exists.

## 11. Relationship to `RowMapper`, `ResultSetExtractor`, and `PreparedStatementCallback`

This lesson's two callbacks belong primarily to the **statement preparation phase**. Other callbacks belong to the **result consumption or custom execution phase**:

| Callback | Conceptual signature | Responsibility |
| --- | --- | --- |
| `PreparedStatementCreator` | `PreparedStatement createPreparedStatement(Connection)` | Create the JDBC statement as desired |
| `PreparedStatementSetter` | `void setValues(PreparedStatement)` | Bind parameters or configure an existing statement |
| `RowMapper<T>` | `T mapRow(ResultSet, int)` | Map one row in ResultSet into one object |
| `ResultSetExtractor<T>` | `T extractData(ResultSet)` | Extract/aggregate the entire ResultSet manually |
| `PreparedStatementCallback<T>` | `T doInPreparedStatement(PreparedStatement)` | Run custom operations on the statement |
| `BatchPreparedStatementSetter` | `setValues(ps, i)` + `getBatchSize()` | Bind values once for each item in a batch |

Do not give ResultSet mapping duties to a setter: `setValues` runs before `executeQuery()` and receives no ResultSet. Conversely, `RowMapper` is not the place to choose SQL or tweak the Connection.

### When to Use `PreparedStatementCallback`?

If you need a special sequence of operations on the same PreparedStatement that standard overloads cannot express cleanly, JdbcTemplate offers an API like:

~~~java
// Fragment: jdbc is a JdbcTemplate; sql and parameters are defined.
// Not an example to use for routine CRUD queries.
Integer affected = jdbc.execute(
    "UPDATE product SET stock = ? WHERE id = ?",
    ps -> {
        ps.setInt(1, newStock);
        ps.setLong(2, productId);
        return ps.executeUpdate();
    }
);
~~~

The lambda in `execute(String, PreparedStatementCallback<T>)` calls `ps.executeUpdate()` itself because it is an **execution callback**, unlike the setter in `update(String, PreparedStatementSetter)`. Choose this API only when direct control over statement operations is truly needed; normally `update(sql, setter)` expresses intent more clearly.

## 12. Batch SQL: Do Not Confuse Normal Setters with Batch Setters

A regular `PreparedStatementSetter` has signature `setValues(PreparedStatement ps)` for a single statement execution. To run multiple sets of values against the same SQL template, the dedicated API is `BatchPreparedStatementSetter`:

~~~java
// Illustrative fragment: updates is a defined List<StockChange>.
int[] counts = jdbc.batchUpdate(
    "UPDATE product SET stock = ? WHERE id = ?",
    new BatchPreparedStatementSetter() {
        @Override
        public void setValues(PreparedStatement ps, int index)
                throws SQLException {
            StockChange change = updates.get(index);
            ps.setInt(1, change.stock());
            ps.setLong(2, change.id());
        }

        @Override
        public int getBatchSize() {
            return updates.size();
        }
    }
);
~~~

Here the **batch `index` starts at 0**, while parameter indices inside PreparedStatement still start at **1**. There is also an overload using `ParameterizedPreparedStatementSetter<T>` in `batchUpdate(sql, collection, batchSize, setter)` with signature `setValues(PreparedStatement ps, T argument)`.

**Note:** Batching typically reduces round trips, yet driver implementations and `int[]` return values can differ; JDBC permits codes such as `Statement.SUCCESS_NO_INFO` or `Statement.EXECUTE_FAILED`. Batching does not automatically create a business transaction covering all operations; for atomicity, an appropriate transaction boundary is still required.

Batching is useful for contrasting **responsibility differences**, though it does not replace this lesson's focus: how to **create** a PreparedStatement and how to **bind** parameters on an individual statement.

## 13. Spring Transactions and JDBC Lifecycle in Callbacks

Using `JdbcTemplate` inside a repository does not guarantee that an entire multi-command use case runs atomically. When a transaction must span multiple SQL commands, a Spring-managed Service typically declares `@Transactional`:

~~~java
// Illustrative architecture fragment; not a standalone compilable file.
@Service
public class InventoryService {
    private final ProductRepository products;

    public InventoryService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void applyAdjustment(long firstId, long secondId) {
        products.changeStockWithSetter(firstId, 7);
        products.changeStockWithSetter(secondId, 2);
    }
}
~~~

`@Service`/`@Transactional` imports belong to Spring, alongside `ProductRepository` from the example above. In real applications, instead of overwriting stock with fixed values, compute updates per business rules and check affected rows. This fragment only illustrates **where to place the transaction boundary**.

Inside a Spring transaction, JdbcTemplate obtains the Connection coordinated by the transaction manager; a creator receives that exact Connection in context. Therefore, **never** write a creator like:

~~~java
// ANTI-EXAMPLE: do not do this.
PreparedStatementCreator wrong = ignoredConnection -> {
    Connection another = dataSource.getConnection();
    return another.prepareStatement("UPDATE product SET stock = 0");
};
~~~

This anti-example is intentionally non-standalone and breaks ownership. It bypasses Spring's provided Connection, risks running on a different transaction, leaks `another`, and breaks JdbcTemplate's coordinated resource cleanup. The right approach uses the `connection` received by the callback:

~~~java
PreparedStatementCreator correct = connection ->
    connection.prepareStatement("UPDATE product SET stock = 0");
~~~

**Never call commit/rollback inside callbacks** when Spring manages the transaction. Let the Service and transaction manager define the boundary; callbacks only prepare statements and bind values. `SQLException` thrown by a callback is caught by JdbcTemplate and translated into an appropriate `DataAccessException` when possible; application code does not need to wrap every setter in `try-catch SQLException` and swallow errors.

## 14. Error Analysis: Which Callback Is Wrong?

| Symptom | Common cause | Where to check |
| --- | --- | --- |
| `Parameter index out of range` | SQL has N `?`s but wrong/extra index bound | `PreparedStatementSetter` or binding block in creator |
| `No value specified for parameter` | Missing one placeholder | Match SQL placeholder order against `ps.setXxx` calls |
| INSERT succeeds but `KeyHolder` is empty | Creator did not enable generated keys or driver lacks support | `prepareStatement(sql, RETURN_GENERATED_KEYS)`, driver metadata |
| `SQLSyntaxErrorException`/`BadSqlGrammarException` | Invalid SQL syntax or column name | SQL built in creator or passed to JdbcTemplate |
| `DataIntegrityViolationException` | Unique/foreign key/check constraint violated | Input, business rules, and schema/DB constraints |
| SELECT results read with wrong type | Incompatible RowMapper/ResultSet getter | Mapper / SQL column aliases |
| Pool timeout or connection leak | Connection/stream held too long or raw connection opened outside template | DataSource, transaction, queryForStream, callback ownership |
| UPDATE affects 0 rows | WHERE did not match or record does not exist | Inspect affected row count and SQL conditions |
| Transaction commits only partially | Operations not sharing the same transaction manager/resource | Service transaction boundary; avoid opening raw Connections |

**Systematic debugging:** First log/inspect SQL at an appropriate level (without logging secrets), match placeholders strictly against values and JDBC types, inspect affected row counts, and then verify the datasource and transaction share the same context. SQL injection stems from concatenating input into SQL; PreparedStatement is only safe for **actually bound values**.

### Debugging with SQL Context

A `PreparedStatementCreator` written as a dedicated class can also implement `SqlProvider` to supply SQL text to the framework in certain exception-translation paths. Unless specifically needed, a simple lambda keeps code concise; logs or database errors already provide enough context. Do not build custom wrappers maintaining a global cache of PreparedStatements, because each PreparedStatement is tied to a specific Connection and lifecycle.

## 15. Performance: Does "Prepared" Mean "Faster"?

`PreparedStatement` separates SQL from input data, makes type binding clean, and often helps drivers/databases optimize SQL processing, yet **it does not guarantee every SQL query gets a server-side cached plan**. Exact parsing/preparing/caching depends on the JDBC driver, database, connection, and configuration. Creating a `PreparedStatementCreator` in Java **does not** create a global statement cache.

Factors affecting real performance:

- **Round trips:** Running a SELECT inside a loop many times can be slower than one query fetching all required rows, even though each call uses a PreparedStatement.
- **Indexes and SQL:** `WHERE`, `JOIN`, returned row count, and query plans usually dominate performance.
- **Batches:** Group multiple parameter sets via `batchUpdate` when appropriate, considering batch size limits and transactions.
- **Pool/transactions:** Holding a Connection too long degrades throughput; callbacks must not perform external network calls or blocking work unrelated to JDBC.
- **Large fetches:** Consider fetch size, streaming, and resource lifetimes; do not put entire business workflows inside callbacks.

Choose callbacks for **API requirements and clarity**, then measure performance against real workloads. Compressing Java lines by stuffing everything into a creator does not make SQL run faster.

## 16. When Are Neither of These Two Callbacks Needed?

Simple CRUD code is often shorter with varargs:

~~~java
int rows = jdbc.update(
    "UPDATE product SET stock = ? WHERE id = ?",
    newStock, id
);
~~~

When SQL benefits from readable named parameters, `NamedParameterJdbcTemplate` can fit:

~~~java
// Fragment; namedJdbc is created from the same DataSource.
MapSqlParameterSource parameters = new MapSqlParameterSource()
    .addValue("stock", newStock)
    .addValue("productId", id);

int rows = namedJdbc.update(
    "UPDATE product SET stock = :stock WHERE id = :productId",
    parameters
);
~~~

In Spring Framework 6.1+ applications, `JdbcClient` provides a fluent API layered over JdbcTemplate/NamedParameterJdbcTemplate for many common cases. Those options **do not make callbacks wrong or deprecated**; callbacks remain essential when you need control over type binding, generated keys, statement creation options, and low-level JDBC interactions.

**Quick selection criteria:**

1. **Passing just a few parameters:** `update(sql, args...)` or `query(sql, mapper, args...)`.
2. **Need custom binding while default statement creation suffices:** `PreparedStatementSetter`.
3. **Need to pick a specific `Connection.prepareStatement(...)` overload:** `PreparedStatementCreator`.
4. **Stable SQL/parameter types, creating many creators or needing configured generated keys:** `PreparedStatementCreatorFactory`.
5. **One SQL template for many parameter sets:** `BatchPreparedStatementSetter` or `ParameterizedPreparedStatementSetter`.
6. **Want named-parameter/fluent SQL API:** `NamedParameterJdbcTemplate` or `JdbcClient`, when capabilities fit requirements.

## 17. Common Misconceptions

**"Creator is only for INSERT; Setter is only for UPDATE."** False. Both can be used with SELECT, UPDATE, or INSERT depending on the overload. Creator decides **how to create** the statement; Setter decides **values on** the statement.

**"Setter creates the statement before setValues."** No. `JdbcTemplate` has already created the statement; the setter simply receives a reference to that existing statement.

**"Creator cannot bind parameters."** False. A creator can both create and bind, since it returns a configured statement for JdbcTemplate to execute. When binding patterns repeat, a factory avoids boilerplate.

**"You must close PreparedStatement inside the callback to avoid leaks."** False with `JdbcTemplate`. Spring is responsible for closing statements/result sets and releasing connections; closing them early breaks JdbcTemplate execution.

**"A `PreparedStatementSetter` must call executeUpdate itself."** False with `JdbcTemplate.update(sql, setter)`. Distinguish it from `PreparedStatementCallback` in `JdbcTemplate.execute(...)`, where the callback actively executes the statement.

**"Using `?` parameter binding makes SQL always safe."** Only true for **bound values**; if table/column/`ORDER BY` names still concatenate unchecked input, SQL injection remains possible.

**"To retrieve generated keys, you only need to instantiate `GeneratedKeyHolder`."** Insufficient. The statement/driver must be created and configured to return generated keys, and reading KeyHolder must match the key structure.

**"PreparedStatement caches plans identically on every driver."** No. The driver and database determine caching behavior and when server-side preparation occurs.

**"Each setter is one batch record."** No. A standard setter has no batch index; the dedicated `BatchPreparedStatementSetter` API has `setValues(ps, int i)` and `getBatchSize()`.

## 18. Exercises and Self-Check Questions

**Exercise 1 — Identify the API:** You must INSERT and retrieve an auto-increment ID from the JDBC driver. Which callback should you use?  
**Answer:** Use `PreparedStatementCreator` with `prepareStatement(sql, RETURN_GENERATED_KEYS)` and `JdbcTemplate.update(creator, keyHolder)`; or use a factory creating a creator with generated keys enabled.

**Exercise 2 — Check 1-based indexing:** For `UPDATE product SET price = ?, stock = ? WHERE id = ?`, is `ps.setLong(0, id)` valid?  
**Answer:** Wrong. JDBC parameter positions start at 1. Furthermore, the first column index does not correspond to `id` if the SQL order puts `id` third.

**Exercise 3 — Query:** For a SELECT taking `minimumStock` and returning a list of Products, what callback is needed besides the setter?  
**Answer:** `RowMapper<Product>`; the setter only binds values, while the mapper reads `ResultSet` after execution.

**Exercise 4 — Typed null:** If an optional value maps to a nullable SQL INTEGER, why is `ps.setNull(index, Types.INTEGER)` worth considering?  
**Answer:** It gives the driver an explicit SQL type, avoiding incorrect type inference in certain cases.

**Exercise 5 — Ownership:** Inside a creator, may you call `dataSource.getConnection()` to replace the Connection passed by Spring?  
**Answer:** You should not. The creator must use the passed Connection to preserve proper resource and transaction lifecycles.

**Exercise 6 — Batching:** For 1,000 records sharing an UPDATE template, should you call `PreparedStatementSetter.setValues(ps)` 1,000 times manually on one statement and expect JdbcTemplate to batch them?  
**Answer:** No. Use `batchUpdate` with `BatchPreparedStatementSetter` or an appropriate batch API; also account for transactions and driver behavior.

**Implementation exercise:** Add a `updatePriceWithSetter(long id, BigDecimal price)` method to the repository in Section 7 returning affected row counts. Add `findByPriceAtMostWithCreator(BigDecimal maximum)` using `query(PreparedStatementCreator, RowMapper)`. Build an integration test starting a Spring context with H2 to verify data read back; test a negative price to see the DB CHECK constraint react. When multiple updates must be atomic, wrap them in a public `@Transactional` Service method and test rollback against a real database.

## 19. Official References

- [`PreparedStatementCreator` — Spring Framework API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/PreparedStatementCreator.html): contract receiving Connection and returning PreparedStatement.
- [`PreparedStatementSetter` — Spring Framework API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/PreparedStatementSetter.html): contract receiving a statement to bind parameters.
- [`JdbcTemplate` — Spring Framework API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `update`, `query`, `execute`, and batch overloads.
- [`PreparedStatementCreatorFactory` — Spring Framework API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/jdbc/core/PreparedStatementCreatorFactory.html): creating creators/setters from SQL and parameter types.
- [Spring Framework — JDBC Batch Operations](https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html): using batch-specific callbacks.

**Remember:** `PreparedStatementCreator` decides **how a PreparedStatement is created from a Connection**; `PreparedStatementSetter` decides **how parameters are bound onto an existing statement**. `JdbcTemplate` decides **when to execute and how to manage resources**, while the Service/transaction manager defines business and transaction boundaries. Choosing callbacks by their proper responsibility keeps JDBC code concise, testable, and free of resource-lifecycle bugs.
