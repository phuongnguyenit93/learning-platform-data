# Falling Back to Templates for Batching or Specialized Operations Not Covered by the Facade

## 1. Core Idea: JdbcClient Is a Convenient Facade, Not a Replacement for All JDBC APIs

`JdbcClient` in Spring Framework is a **fluent facade** for common SQL operations. For example, code can express a query in natural order: SQL → bind parameters → map results → retrieve a list or single element.

~~~java
List<ProductRow> rows = client.sql("""
        SELECT id, sku, price, stock, state
        FROM inventory
        WHERE state = :state
        ORDER BY id
        """)
        .param("state", "READY")
        .query((rs, rowNum) -> new ProductRow(
                rs.getLong("id"),
                rs.getString("sku"),
                rs.getBigDecimal("price"),
                rs.getInt("stock"),
                rs.getString("state")))
        .list();
~~~

The snippet above is **illustrative repository code** assuming a `JdbcClient client` field, `ProductRow` record, and `List` import. For standard CRUD, this API is easier to read than writing multiple helper objects around a `JdbcTemplate`.

However, **you should not force every JDBC requirement into the fluent facade**. When an operation requires complex batching, low-level Statement/Connection control, a specialized stored procedure mechanism, or JDBC optimizations not yet supported by your `JdbcClient` version, fall back to **`JdbcTemplate`, `NamedParameterJdbcTemplate`, `SimpleJdbcCall`, or `SimpleJdbcInsert`**. This is not an "architectural downgrade": `JdbcClient` itself is built on top of Spring's JDBC templates; you are simply choosing the API level that fits the problem.

### Crucial Version Note

Never state categorically that "JdbcClient does not support batching" across all versions:

- **Spring Framework 6.1, 6.2, and early 7.0 API lines:** `JdbcClient` mainly offers fluent query/update; batching typically uses `JdbcTemplate.batchUpdate(...)` or `NamedParameterJdbcTemplate.batchUpdate(...)`. The example application in this lesson uses **Spring Boot 3.3.5 / Spring Framework 6.1.x**, so it falls back to templates for batching.
- **Spring Framework 7.1:** the `JdbcClient.StatementSpec.batch()` API with `BatchSpec.entry(...)/entries(...).update()` appeared. In that version, many simple batches **can be written with the fluent facade**. You still fall back to templates for specialized operations not covered by the facade or when finer control is needed.
- **All versions:** always check the exact Javadoc of the version and driver you are running. Never copy 7.1 batch APIs into a Spring 6.1 project expecting it to compile.

**Learning takeaway:** "falling back to a template" is **a choice based on your current version's API capabilities and business requirements**, not a permanently fixed rule.

## 2. JdbcClient and the Layers Underneath

`JdbcClient` supports positional or named parameter binding and delegates to the JDBC template layer:

~~~text
Service / Transaction boundary
          |
          v
Repository
  |----------------------------|
  | JdbcClient                 |  query/update fluent API
  |----------------------------|
  | JdbcTemplate               |  batchUpdate, execute callbacks,
  |                            |  Statement/ResultSet control
  |----------------------------|
  | NamedParameterJdbcTemplate |  named-parameter batch,
  |                            |  SqlParameterSource, typed NULL
  |----------------------------|
  | SimpleJdbcInsert/Call      |  generated keys, stored procedures
  |----------------------------|
          |
          v
Spring JDBC transaction & resource management
          |
          v
DataSource -> JDBC driver -> Database
~~~

Classes across these "layers" **coexist within the same module**. You do not have to rewrite an entire repository to replace `JdbcClient` with `JdbcTemplate`. One method can use `JdbcClient` for readable `SELECT`s; another can use `JdbcTemplate.batchUpdate` for multi-row writes; a specialized method can use `ConnectionCallback` or `SimpleJdbcCall`.

For unified transactions, all delegates must share **the exact `DataSource` managed by the transaction manager**. For example:

~~~java
public InventoryRepository(JdbcTemplate jdbc) {
    this.jdbc = jdbc;
    this.namedJdbc = new NamedParameterJdbcTemplate(jdbc);
    this.client = JdbcClient.create(jdbc);
}
~~~

This is an illustrative constructor: `jdbc` is Spring-injected, and `namedJdbc` and `client` both reuse that `JdbcTemplate`. The benefit is sharing the same `DataSource` configuration, connection handling, and template settings. There is no need to create a second `DataSource` or connection pool just to use a different API.

### Choosing the Abstraction by Task

| Task | Suitable API | Reason |
| --- | --- | --- |
| SELECT with named parameters and DTO mapping | `JdbcClient` | Fluent, concise, readable. |
| Single UPDATE/INSERT with simple binding | `JdbcClient` | `sql(...).param(...).update()` suffices. |
| Batching on Spring Framework 6.1/6.2 | `JdbcTemplate.batchUpdate` or `NamedParameterJdbcTemplate.batchUpdate` | Facade in these versions has no fluent batch API. |
| Batching on Spring Framework 7.1 | `JdbcClient.sql(...).batch()` **or** template | Facade adds batching; templates still work and fit when lower-level control is needed. |
| Named-parameter batching with typed NULLs | `NamedParameterJdbcTemplate.batchUpdate` | `SqlParameterSource[]` provides values and SQL type metadata. |
| Multi-chunk batching with a fixed chunk size | `JdbcTemplate.batchUpdate(sql, collection, batchSize, setter)` | Organized in chunks, helpful for large item counts. |
| JDBC Connection metadata / vendor API | `JdbcTemplate.execute(ConnectionCallback<T>)` | Accesses Connection within a Spring-managed lifecycle. |
| Customizing `PreparedStatement` | `JdbcTemplate.execute(..., PreparedStatementCallback<T>)` | Grants low-level JDBC method access on the statement. |
| Stored procedures with IN/OUT parameters | `SimpleJdbcCall` or `JdbcTemplate`/`CallableStatement` | Choose an API supporting OUT parameters and your driver. |
| INSERT returning generated keys using metadata | `SimpleJdbcInsert` or template with `KeyHolder` | Avoids manual JDBC plumbing. |
| Aggregating multiple rows from one `ResultSet` | `RowMapper` / `ResultSetExtractor` via template or facade | Depends on scope and required level of control. |

## 3. What Is Batching Really and When Should You Use It?

**JDBC batching** groups multiple executions of a `PreparedStatement` (or multiple SQL statements in another variant) so the driver/database has an opportunity to reduce round-trips and process them more efficiently.

Suppose three inventory items need to be inserted:

~~~sql
INSERT INTO inventory(id, sku, price, stock, state)
VALUES (?, ?, ?, ?, ?);
~~~

Running `JdbcClient.sql(...).param(...).update()` three separate times is completely valid, though it may issue three individual executions. `JdbcTemplate.batchUpdate` lets you pass a list of value sets for the same SQL so the driver can use JDBC batching. That does **not** mean a batch becomes a single multi-row SQL statement, nor does it guarantee faster execution in every case: results depend on the driver, database, batch size, indexes, locks, and network.

### 3.1. Batching Does Not Equal a Transaction

These are two independent concepts:

- **Batching:** groups operations at the JDBC level for efficiency.
- **Transaction:** defines which operations commit or roll back together.

If an application runs a batch outside a business transaction, the driver/connection may run with autoCommit and leave partial changes behind upon failure. If the entire group must be atomic, place `@Transactional` on the service and use templates sharing the same `DataSource`/transaction manager.

Conversely, `@Transactional` does not automatically merge multiple individual `update()` calls into a JDBC batch. A transaction guarantees commit/rollback while still incurring multiple round-trips. Only choosing a batch API requests batching.

### 3.2. Returned `int[]` Values Are Not Always Exact Row Counts

`batchUpdate` overloads typically return `int[]` or `int[][]`. Elements can be:

- Affected row count (e.g., `1` when an INSERT succeeds).
- `Statement.SUCCESS_NO_INFO` (typically `-2`): the driver reports the operation succeeded without providing a row count.
- `Statement.EXECUTE_FAILED` (typically `-3`) when a driver reports JDBC failure status; a batch failure may also throw an exception.

Never write production code asserting every element must equal `1` without understanding your driver and business requirements. When strict verification is needed, combine unique keys, post-batch data checks, or integration tests with your target database.

## 4. Three Batching Options on Templates

### 4.1. `JdbcTemplate` + `BatchPreparedStatementSetter`

Fits when SQL uses `?` markers and you need explicit JDBC setter control per element:

~~~java
int[] affected = jdbc.batchUpdate("""
        UPDATE inventory SET stock = ? WHERE id = ?
        """, new BatchPreparedStatementSetter() {
    @Override
    public void setValues(PreparedStatement ps, int index)
            throws SQLException {
        StockAdjustment item = changes.get(index);
        ps.setInt(1, item.newStock());
        ps.setLong(2, item.id());
    }

    @Override
    public int getBatchSize() {
        return changes.size();
    }
});
~~~

This is a **method-body illustration**: it requires `JdbcTemplate jdbc`, a `changes` list, and an application-defined `StockAdjustment` record. `BatchPreparedStatementSetter` lives in `org.springframework.jdbc.core`. Each `setValues` call only binds parameters for one item without calling `executeUpdate()`; the template coordinates the batch.

Pros: explicit JDBC types, direct placeholder ordering, easy `setNull` usage when needed. Cons: more boilerplate than named parameters; `?` order must match setter indices exactly.

### 4.2. `NamedParameterJdbcTemplate` + `SqlParameterSource[]`

When SQL has many parameters, the named style is easier to read:

~~~java
SqlParameterSource[] batch = ids.stream()
        .map(id -> (SqlParameterSource) new MapSqlParameterSource()
                .addValue("id", id, Types.BIGINT)
                .addValue("state", "READY", Types.VARCHAR))
        .toArray(SqlParameterSource[]::new);

int[] updated = namedJdbc.batchUpdate(
        "UPDATE inventory SET state = :state WHERE id = :id",
        batch);
~~~

This is an **illustrative snippet** inside a class with `NamedParameterJdbcTemplate namedJdbc`, `List<Long> ids`, and imports for `MapSqlParameterSource`, `SqlParameterSource`, and `Types`. Each `SqlParameterSource` element describes one SQL execution.

Pros: reduces parameter mix-ups, supports `java.sql.Types` and typed NULLs. `SqlParameterSourceUtils.createBatch(...)` can also build batches from beans/Maps with matching property names, though when specific SQL types are needed, inspect generated metadata or construct `MapSqlParameterSource` manually for clarity.

### 4.3. Chunked Batching with a Bounded Size

When processing tens of thousands of objects, the following API splits them into chunks:

~~~java
int[][] results = jdbc.batchUpdate(
        "UPDATE inventory SET stock = ? WHERE id = ?",
        changes,
        200,
        (ps, item) -> {
            ps.setInt(1, item.newStock());
            ps.setLong(2, item.id());
        });
~~~

This is an **illustration inside a repository**, where `changes` is `Collection<StockAdjustment>`. The overload signature is `batchUpdate(String sql, Collection<T> batchArgs, int batchSize, ParameterizedPreparedStatementSetter<T> pss)` and returns `int[][]` because there are multiple chunks. Each chunk contains up to 200 items; the final chunk may be smaller. This caps the size of each JDBC batch, yet if all 50,000 rows run inside **one `@Transactional`**, the transaction still spans all chunks. Design commit/rollback boundaries around consistency and system load rather than mistaking chunk size for transaction size.

## 5. Complete Example: Same Repository Using Both JdbcClient and Templates

We will build a Java 21 console application with Spring Boot 3.3.5 (Spring Framework 6.1.x) and H2. Reads use **`JdbcClient`**, batch INSERTs use **`JdbcTemplate`**, named batch UPDATEs use **`NamedParameterJdbcTemplate`**, and metadata inspection uses **`ConnectionCallback`**. All of these share the same `JdbcTemplate` injected by Spring Boot.

Scenario: insert 3 items into the `inventory` table, mark items #1 and #3 as READY, read READY rows via fluent `JdbcClient`, then trigger a failed batch and observe rollback. Everything runs in memory with no separate database server needed.

### 5.1. Project Structure

~~~text
jdbcclient-template-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/fallback/
    │   ├── FallbackApplication.java
    │   ├── StockItem.java
    │   ├── InventoryRepository.java
    │   └── InventoryService.java
    └── resources/
        ├── application.properties
        └── schema.sql
~~~

File `settings.gradle`:

~~~groovy
rootProject.name = 'jdbcclient-template-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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

File `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.main.banner-mode=off
spring.datasource.url=jdbc:h2:mem:fallbackdemo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
logging.level.root=ERROR
~~~

File `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE inventory (
    id BIGINT PRIMARY KEY,
    sku VARCHAR(40) NOT NULL,
    price DECIMAL(12, 2) NOT NULL,
    stock INTEGER NOT NULL,
    state VARCHAR(16) NOT NULL
);
~~~

This is a test table with primary key `id`. In a real environment, add `CHECK` constraints for `price`, `stock`, and `state` where appropriate, enforce unique `sku`, and choose business-appropriate precision/scale. In the demo, IDs are supplied explicitly so stdout is predictable without relying on generated keys.

### 5.2. Application Data Type

File `src/main/java/example/fallback/StockItem.java`:

~~~java
package example.fallback;

import java.math.BigDecimal;

public record StockItem(
        long id,
        String sku,
        BigDecimal price,
        int stock,
        String state) {
}
~~~

This record serves as both batch input and read DTO from the database. In a real application, consider separating input commands from read DTOs, especially when fields are database-assigned or require separate validation. The demo record does not automatically validate positive prices or non-negative stock.

### 5.3. Repository Combining Facade and Templates

File `src/main/java/example/fallback/InventoryRepository.java`:

~~~java
package example.fallback;

import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.util.List;

import org.springframework.jdbc.core.BatchPreparedStatementSetter;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.namedparam.NamedParameterJdbcTemplate;
import org.springframework.jdbc.core.namedparam.SqlParameterSource;
import org.springframework.jdbc.core.simple.JdbcClient;
import org.springframework.stereotype.Repository;

@Repository
public class InventoryRepository {
    private static final String INSERT_SQL = """
            INSERT INTO inventory(id, sku, price, stock, state)
            VALUES (?, ?, ?, ?, ?)
            """;

    private final JdbcTemplate jdbc;
    private final NamedParameterJdbcTemplate namedJdbc;
    private final JdbcClient client;

    public InventoryRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
        this.namedJdbc = new NamedParameterJdbcTemplate(jdbc);
        this.client = JdbcClient.create(jdbc);
    }

    public int[] insertBatch(List<StockItem> items) {
        return jdbc.batchUpdate(INSERT_SQL, new BatchPreparedStatementSetter() {
            @Override
            public void setValues(PreparedStatement ps, int index)
                    throws SQLException {
                StockItem item = items.get(index);
                ps.setLong(1, item.id());
                ps.setString(2, item.sku());
                ps.setBigDecimal(3, item.price());
                ps.setInt(4, item.stock());
                ps.setString(5, item.state());
            }

            @Override
            public int getBatchSize() {
                return items.size();
            }
        });
    }

    public int[] updateStateBatch(List<Long> ids, String state) {
        SqlParameterSource[] params = new SqlParameterSource[ids.size()];
        for (int index = 0; index < ids.size(); index++) {
            params[index] = new MapSqlParameterSource()
                    .addValue("id", ids.get(index), Types.BIGINT)
                    .addValue("state", state, Types.VARCHAR);
        }

        return namedJdbc.batchUpdate("""
                UPDATE inventory
                SET state = :state
                WHERE id = :id
                """, params);
    }

    public List<StockItem> findByState(String state) {
        return client.sql("""
                SELECT id, sku, price, stock, state
                FROM inventory
                WHERE state = :state
                ORDER BY id
                """)
                .param("state", state)
                .query((rs, rowNumber) -> new StockItem(
                        rs.getLong("id"),
                        rs.getString("sku"),
                        rs.getBigDecimal("price"),
                        rs.getInt("stock"),
                        rs.getString("state")))
                .list();
    }

    public long countAll() {
        return client.sql("SELECT COUNT(*) FROM inventory")
                .query(Long.class)
                .single();
    }

    public String databaseName() {
        return jdbc.execute((ConnectionCallback<String>) connection ->
                connection.getMetaData().getDatabaseProductName());
    }
}
~~~

**Inspect the three paths closely:**

1. **Batch INSERT with `JdbcTemplate`.** `BatchPreparedStatementSetter` binds values by position; the template prepares the JDBC Statement, executes the batch, and cleans up. The setter callback never calls `executeBatch()` or `close()`. `int[]` holds the counts reported by the JDBC driver.
2. **Batch UPDATE with `NamedParameterJdbcTemplate`.** Each ID gets a `MapSqlParameterSource` with `BIGINT` and `VARCHAR` types. Spring expands `:id` and `:state` into positional bindings and runs the batch.
3. **SELECT with `JdbcClient`.** The fluent API fits simple read queries and a `RowMapper`. It returns a materialized `List<StockItem>`, never a raw `ResultSet`.

`countAll()` demonstrates a scalar query with the facade. `databaseName()` shows that when `DatabaseMetaData` is needed, you can fall back to `JdbcTemplate.execute(ConnectionCallback<T>)` without manually opening a raw `Connection` from the pool. The connection is managed by the template; the callback never closes it.

### 5.4. Service Ensuring Transactions for Batches

File `src/main/java/example/fallback/InventoryService.java`:

~~~java
package example.fallback;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {
    private final InventoryRepository repository;

    public InventoryService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void createAndPromote() {
        List<StockItem> items = List.of(
                new StockItem(1L, "SKU-001",
                        new BigDecimal("12.50"), 3, "NEW"),
                new StockItem(2L, "SKU-002",
                        new BigDecimal("22.00"), 5, "NEW"),
                new StockItem(3L, "SKU-003",
                        new BigDecimal("30.00"), 1, "NEW"));

        int[] inserted = repository.insertBatch(items);
        if (inserted.length != items.size()) {
            throw new IllegalStateException("Batch INSERT missing results");
        }

        int[] updated = repository.updateStateBatch(
                List.of(1L, 3L), "READY");
        if (updated.length != 2) {
            throw new IllegalStateException("Batch UPDATE missing results");
        }
    }

    @Transactional
    public void demonstrateRollback() {
        repository.insertBatch(List.of(
                new StockItem(9L, "SKU-009",
                        new BigDecimal("9.00"), 2, "NEW"),
                new StockItem(10L, "SKU-010",
                        new BigDecimal("10.00"), 4, "NEW")));

        throw new IllegalStateException("Intentional rollback");
    }
}
~~~

`@Transactional` is placed on the service, wrapping repository calls using both `JdbcTemplate` and `NamedParameterJdbcTemplate`. Because they share one `JdbcTemplate`/`DataSource`, the SQL participates in the active Spring transaction. If an unchecked exception exits the service, Spring rolls back by default.

Checking `inserted.length` only verifies that the driver returned one result entry per item; it does **not** prove every row affected exactly one row. In production, business logic may need to check individual counts and actual data; remember JDBC allows `SUCCESS_NO_INFO`. In this H2 demo with explicit primary keys, the inserts succeed cleanly on the sample data.

### 5.5. Runner and Stdout

File `src/main/java/example/fallback/FallbackApplication.java`:

~~~java
package example.fallback;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class FallbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(FallbackApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            InventoryService service,
            InventoryRepository repository) {
        return args -> {
            service.createAndPromote();

            System.out.println("Database: " + repository.databaseName());

            List<StockItem> ready = repository.findByState("READY");
            System.out.println("READY: " + ready.size());
            for (StockItem item : ready) {
                System.out.printf(
                        "%d | %s | %s | %d | %s%n",
                        item.id(),
                        item.sku(),
                        item.price().toPlainString(),
                        item.stock(),
                        item.state());
            }

            try {
                service.demonstrateRollback();
            } catch (IllegalStateException expected) {
                System.out.println("Rollback requested");
            }

            System.out.println("Total after rollback: "
                    + repository.countAll());
            System.out.println("NEW after rollback: "
                    + repository.findByState("NEW").size());
        };
    }
}
~~~

Run with **JDK 21 and a Java 21-compatible Gradle** (e.g., Gradle 8.5), from the `jdbcclient-template-demo` directory:

~~~bash
gradle bootRun
~~~

Lines printed by the program (excluding Gradle/Spring messages):

~~~text
Database: H2
READY: 2
1 | SKU-001 | 12.50 | 3 | READY
3 | SKU-003 | 30.00 | 1 | READY
Rollback requested
Total after rollback: 3
NEW after rollback: 1
~~~

**Result explanation:** the first batch inserts three rows, and the batch UPDATE changes the state of #1 and #3 to READY. `JdbcClient` finds those two READY rows. Next, a batch INSERTs two rows #9 and #10, but the service throws `IllegalStateException`; Spring rolls back that transaction. The database keeps the original three rows, with only #2 remaining NEW.

This is the expected output when the program runs in a fresh process with an empty H2 database and the configuration shown. The example includes all classes/files and requires no external database installation. Standalone illustrative snippets outside section 5 are **not** part of the runnable project unless integrated separately.

## 6. Controlling Transactions When Combining APIs

Using `JdbcClient` alongside templates **does not split the transaction** as long as both share the same `DataSource`/transaction manager and are called inside a valid Spring transaction. In the demo:

~~~text
CommandLineRunner
       |
       v
InventoryService.createAndPromote()
       |
       +-- @Transactional proxy opens transaction
       |
       +-- InventoryRepository.insertBatch()
       |      -> JdbcTemplate -> Connection in transaction
       |
       +-- InventoryRepository.updateStateBatch()
       |      -> NamedParameterJdbcTemplate
       |      -> same JDBC transaction resource
       |
       +-- service completes normally
              -> commit
~~~

Several mistakes can break this assumption:

- **Different pools:** one `JdbcTemplate` points to DataSource A, while a `NamedParameterJdbcTemplate` points to DataSource B. Two pools can even target the same database URL yet remain two independent Connections/transactions.
- **Raw Connection:** calling `dataSource.getConnection()` directly on the underlying pool inside a transaction can grab a separate Connection with its own auto-commit. When low-level APIs are needed, use `JdbcTemplate.execute(ConnectionCallback<T>)` or `DataSourceUtils` properly.
- **Self-invocation:** in standard Spring proxy mode, one service method calling another `@Transactional` method on `this` bypasses the proxy.
- **Different thread:** synchronous JDBC transactions are bound to the executing thread. `@Async`, executors, or new threads do not automatically inherit the transaction.
- **Catching and swallowing exceptions:** if a service catches an error and returns normally, the transaction interceptor may commit even though a business step failed.
- **`Propagation.REQUIRES_NEW`:** an explicitly separated transaction commits/rolls back independently; it is not a way to "make all batches roll back together".
- **Different databases:** a local JDBC transaction manager does not automatically create a distributed transaction across multiple databases.

**Distinguish atomicity from throughput:** batching optimizes how SQL operations are sent; transactions govern commit points and consistency. Both must be designed intentionally and do not replace each other.

## 7. Spring Framework 7.1: JdbcClient Has Fluent Batching

In versions supporting the new API, you can write a simple batch **directly on the facade**:

~~~java
int[] affected = client.sql("""
        INSERT INTO inventory(id, sku, price, stock, state)
        VALUES (:id, :sku, :price, :stock, :state)
        """)
        .batch()
        .entry(e -> e.param("id", 11L)
                .param("sku", "SKU-011")
                .param("price", new BigDecimal("11.00"))
                .param("stock", 2)
                .param("state", "NEW"))
        .entry(e -> e.param("id", 12L)
                .param("sku", "SKU-012")
                .param("price", new BigDecimal("12.00"))
                .param("stock", 1)
                .param("state", "NEW"))
        .update();
~~~

**This example uses the Spring Framework 7.1 API and will not work with section 5's Spring Boot 3.3.5.** It assumes the class has a `JdbcClient client` field and imports `BigDecimal`. `BatchSpec.entry(...)` describes each parameter binding set, and `update()` executes the batch and returns `int[]`. The API also provides `entries(...)` to supply a list of parameter objects when appropriate.

This evolution does not make template knowledge obsolete: `JdbcTemplate` and `NamedParameterJdbcTemplate` still offer overloads and callbacks for Statement control, Connection metadata, custom batch logic, and stored procedures. Consider at least two questions when choosing an API:

1. **Does the current version support the feature?** Check the exact version's Javadoc from your dependency tree rather than guessing from a blog post.
2. **Does the facade provide enough control?** Even when batching is supported, a workflow needing specialized JDBC details can still be clearer and safer with a template.

If upgrading a project from Spring 6.1 to 7.1, do not change dependencies solely to make one batch call look nicer. Evaluate Spring Boot compatibility, Java baseline, driver, transactions, tests, and the full system before upgrading.

## 8. Specialized Operations Not Well Suited to the Fluent Facade

### 8.1. `ConnectionCallback`: Metadata and Connection-Level APIs

When you need the database product name, driver capabilities, or vendor-specific SQL types, use `JdbcTemplate.execute(ConnectionCallback<T>)`:

~~~java
String dbName = jdbc.execute(
        (ConnectionCallback<String>) connection ->
                connection.getMetaData().getDatabaseProductName());
~~~

This snippet sits in a repository with a `JdbcTemplate` field. The callback receives a Spring-managed `Connection`, so it participates in transactions when the `DataSource` matches. **Never call `connection.close()`, `commit()`, or `rollback()` inside the callback**; close any `Statement`/`ResultSet` created by the callback itself, while Spring releases the `Connection`. Also never return the `Connection` or `ResultSet` out of the callback.

### 8.2. `PreparedStatementCallback` for Statement-Level Operations

When you need advanced JDBC APIs on a statement (such as reading generated keys in a special mode, inspecting result set metadata, or using driver options), `JdbcTemplate.execute(..., PreparedStatementCallback<T>)` offers more direct access. Distinguish overloads taking `String sql` and callbacks, and let Spring manage resources.

Example **illustrating only the callback inside a repository**, not a standalone Java file:

~~~java
String sql = "SELECT COUNT(*) FROM inventory";
Integer count = jdbc.execute(sql, ps -> {
    try (ResultSet rs = ps.executeQuery()) {
        if (!rs.next()) {
            throw new SQLException("COUNT returned no result");
        }
        return rs.getInt(1);
    }
});
~~~

For an actual `COUNT(*)`, `queryForObject` or `JdbcClient` is still better: the pattern above only shows the callback when direct `PreparedStatement` access is truly needed. Appropriate JDBC imports and a `JdbcTemplate jdbc` variable are required.

### 8.3. `SimpleJdbcCall` for Stored Procedures

When calling a stored procedure with IN/OUT parameters or metadata declarations, `SimpleJdbcCall` is the Spring JDBC API dedicated to this use case. Structural usage example:

~~~java
SimpleJdbcCall call = new SimpleJdbcCall(jdbc)
        .withProcedureName("recalculate_stock");

Map<String, Object> results =
        call.execute(Map.of("warehouse_id", 7L));
~~~

This is a **structural example and cannot run on the H2 demo**, because no stored procedure with this name was created. It requires an actual procedure, EXECUTE privileges, a driver supporting metadata/parameter names, and imports for `SimpleJdbcCall` and `Map`. For databases that do not return complete procedure metadata, you may need `withoutProcedureColumnMetaDataAccess()` and explicit `declareParameters(...)`. Never assume every vendor handles OUT parameters identically.

### 8.4. `SimpleJdbcInsert` or `KeyHolder` for Generated Keys

When an INSERT must return auto-generated keys, `SimpleJdbcInsert` and template `KeyHolder` overloads provide dedicated APIs. With newer `JdbcClient` versions, inspect the `update(KeyHolder, ...)` overloads in your actual API version. Never open a raw `Connection`, run a raw `PreparedStatement`, and forget cleanup just because a facade feels brief.

### 8.5. `ResultSetExtractor` and `RowCallbackHandler`

When aggregating multiple rows into an object graph instead of one DTO per row, `ResultSetExtractor<T>` can process a `ResultSet` directly. For row-by-row processing without retaining a whole list in memory, `RowCallbackHandler` supports streaming-style processing while the `ResultSet` remains open. Watch memory cost and Connection hold time.

Some overloads/capabilities depend on the facade version; when control is insufficient, falling back to templates means using the intended extension point. Never return an unclosed `ResultSet` or resource-backed stream to callers after a transaction ends.

## 9. Watch Out for Large Batches, Mid-Batch Errors, and Generated Keys

### 9.1. Choosing Batch Size Based on Load

Batches that are too small do not reduce round-trips meaningfully; batches that are too large can cause memory pressure, long locks, timeouts, or hit bind-parameter/packet-size limits. There is no universal optimal number. Benchmark sizes like 100, 200, 500, or 1,000 items in tests and measure throughput, latency, memory, and transaction duration on the real driver/DB. Chunking by size does not split commits automatically; to commit per chunk, design explicit transaction boundaries knowing the atomicity trade-off.

### 9.2. Drivers That Do Not Optimize Batching

Spring `JdbcTemplate` has a fallback when a driver does not support batching for certain overloads: it may run individual updates. Thus calling `batchUpdate` does not automatically guarantee the driver sends an efficient network batch. Check `DatabaseMetaData.supportsBatchUpdates()`, driver version, datasource settings, and measure real behavior. Some drivers have optimization flags such as rewriting batched statements; those flags are vendor-specific and not a universal Spring API.

### 9.3. Exceptions and Partial Updates

Spring's `DataAccessException` can wrap errors from `SQLException`/`BatchUpdateException`. Depending on the driver, update counts prior to the failure may or may not be complete, and partial changes may have reached the database. Inside a real transaction that rolls back when an appropriate error exits the boundary, transaction changes are undone per database guarantees. Outside a transaction, never assume a failed batch rolls everything back automatically.

Never catch `DataAccessException` and return success when data is in an indeterminate state. If business logic needs retries, design idempotency keys to avoid duplicate records. Database `UNIQUE`, `FK`, and `CHECK` constraints must still be enforced.

### 9.4. Generated Keys in Batches

Retrieving generated keys during batching depends on both the Spring API and the JDBC driver. Some template overloads accept `KeyHolder`, though ordering, key counts returned, and driver support vary. If business logic must map each generated key back to its exact input item, test directly against the target database/driver instead of assuming index alignment. In the full demo, IDs are supplied explicitly to keep the focus on **batch fallback** separately from generated keys.

### 9.5. Consistency and Execution Order

Batching typically groups repeated executions of the same SQL, yet batching should never replace designing business ordering, concurrency locks, or optimistic locking. Updating the same ID multiple times in one batch can make the final outcome depend on order, triggers, and constraints. For updates that must prevent lost updates, consider `WHERE id = ? AND version = ?` and verify affected row counts, even in batches.

## 10. Choosing APIs with Controlled Minimalism

A maintainable repository does not need to be "purely" `JdbcClient` or "purely" `JdbcTemplate`. You can follow these principles:

1. **Default to `JdbcClient`** for single queries and updates that read cleanly in your current version.
2. **Use templates when tasks require batching, callbacks, or specialized APIs not covered or insufficiently controlled by the facade.**
3. **Do not open raw Connections outside Spring transactions** just to do things templates already support.
4. **Reuse the same `DataSource`/transaction configuration**, placing transactions at the service layer.
5. **Encapsulate JDBC details inside the repository**; the business layer calls meaningful methods like `insertBatch`, `promoteStateBatch`, `findReady`, without caring whether facade or template is used inside.
6. **Test behavior and performance** rather than judging code solely by brevity.
7. **Always verify the API version**; batching in `JdbcClient` 7.1 shows why rules must not be frozen to outdated docs.

A repository's public API might look like:

~~~java
public interface StockStore {
    void insertMany(List<StockItem> items);
    void markReady(List<Long> ids);
    List<StockItem> findReady();
}
~~~

This is an **illustrative interface**, assuming `StockItem` is in the same package and `List` is imported. Implementations are free to use different templates while keeping the upper-layer API consistent. If callers need diagnostics (counts or per-row errors), return a richer result object instead of `void`.

## 11. Decision Table When Facing a JDBC Task

| Scenario | Recommended action | Verification |
| --- | --- | --- |
| SELECT a list by status | `JdbcClient` fluent query | Mapping, ordering, empty results. |
| UPDATE one row by ID | `JdbcClient` update | Affected rows, concurrency/version. |
| INSERT 500 rows on Spring 6.1 | `JdbcTemplate.batchUpdate` | Batch counts, transactions, driver support. |
| Bulk UPDATE with named parameters | `NamedParameterJdbcTemplate.batchUpdate` | `SqlParameterSource[]`, typed NULLs, key mapping. |
| Simple batch on Spring 7.1 | Consider `JdbcClient.batch()` | Version check and benchmark against template. |
| Need SQL ARRAY / vendor metadata | `ConnectionCallback` / driver API | Resource cleanup, driver compatibility. |
| Need stored procedure with OUT params | `SimpleJdbcCall` | OUT mapping, metadata/permissions. |
| Need generated keys at scale | Template/`KeyHolder` or version-appropriate facade feature | All keys returned, accurate input mapping, rollback. |
| Need to process 1 million rows | Chunking/pagination/streaming with clear lifecycle | Pool, memory, locks, timeouts. |
| Multiple operations must be atomic | `@Transactional` on service + shared `DataSource` | Integration test verifying full rollback. |
| Multiple DataSources | Configure dedicated transaction managers | Never assume automatic cross-DB transactions. |

## 12. Testing and Practical Checklist

### Tests You Should Have

- **Happy path:** three INSERTs succeed; two UPDATEs modify #1 and #3; `JdbcClient` returns the two READY rows in order.
- **Rollback:** batch INSERT two rows #9/#10 and throw `RuntimeException`; verify neither new row persists.
- **Database constraints:** batch with duplicate ID or stock violating `CHECK`; observe exception, rollback, and error reporting.
- **Empty input:** `insertBatch(List.of())` and `updateStateBatch(List.of(), ...)` should have defined behavior; never emit `IN ()` or assume an empty batch issues a statement.
- **Affected rows:** updating a non-existent ID may return 0; business code must define whether that is an error.
- **Resources:** `Statement`/`ResultSet`/`Connection` managed by Spring; no leaks, no JDBC handles returned outside.
- **Version matrix:** run compile tests on the target Spring version; never call `JdbcClient.batch()` if the dependency is below 7.1.
- **Performance:** measure batch sizes and round-trips on a real database rather than extrapolating from H2 demo row counts to production.
- **Concurrency:** optimistic locking and unique constraints still work under batching.
- **Observability:** distinguish mapping/binding errors, SQL exceptions, deadlocks/timeouts, and business errors; log necessary details without leaking sensitive data.

### Self-Check Questions

1. Why can `JdbcClient` participate in the same transaction as `JdbcTemplate`?
2. How do batching and transactions differ? Does a batch automatically roll back everything on error?
3. Why is saying "JdbcClient does not support batching" incomplete without version qualification?
4. On Spring Boot 3.3.5, which batching options in this lesson can run?
5. When should you use `BatchPreparedStatementSetter` vs. `SqlParameterSource[]`?
6. Why might `int[]` returned from `batchUpdate` contain `SUCCESS_NO_INFO` instead of `1`?
7. If you need `Connection` metadata, why should you call `JdbcTemplate.execute(ConnectionCallback)` instead of grabbing a raw `Connection` from the pool?
8. If an operation needs stored procedure OUT parameters, which Spring JDBC class fits better?
9. Why does chunking by 200 items not automatically create 200 independent transactions?
10. When upgrading Spring Framework to 7.1, what should you test before replacing template batches with `JdbcClient.batch()`?

**Conclusion:** `JdbcClient` improves readability for standard SQL, yet **it does not replace all of Spring JDBC**. On Spring 6.1/6.2, batching is a classic reason to fall back to `JdbcTemplate`/`NamedParameterJdbcTemplate`; starting in Spring 7.1, fluent batching can be used where appropriate. Other specialized tasks still call for templates, callbacks, or `SimpleJdbcCall`/`SimpleJdbcInsert`. Choose APIs based on **version, required control, transaction/resource lifecycles, and real requirements**, rather than forcing every operation through a single facade.

### References

- Spring Framework 6.2 — JdbcClient Javadoc (notes falling back to templates for batching): https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/jdbc/core/simple/JdbcClient.html
- Spring Framework — JDBC Core: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework 7.1 — JDBC Core (fluent JdbcClient batch): https://docs.spring.io/spring-framework/reference/7.1/data-access/jdbc/core.html
- Spring Framework — JdbcTemplate Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html
- Spring Framework — NamedParameterJdbcTemplate Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/namedparam/NamedParameterJdbcTemplate.html
- Spring Framework — SimpleJdbcCall Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/simple/SimpleJdbcCall.html
