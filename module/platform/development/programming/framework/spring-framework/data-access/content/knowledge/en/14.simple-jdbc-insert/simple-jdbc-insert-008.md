# Finalizing Configuration Before Sharing a SimpleJdbcInsert Instance

## 1. What "Configure Completely Before Sharing" Means

In Spring JDBC, `SimpleJdbcInsert` encapsulates the **configuration of a single INSERT operation**: which table to write to, which columns to send, which column generates keys, and whether JDBC metadata is used. It is not an object for storing per-request data. Once configuration is complete, the same instance can accept **many different parameter sets** to insert different rows.

For example, a singleton `AuditRepository` is called concurrently by many requests. Every request can use the same `SimpleJdbcInsert` configured for the `audit_event` table, while each request creates its own fresh `MapSqlParameterSource` holding its data.

~~~text
Create object            Declare full configuration            Lock config           Reuse
new SimpleJdbcInsert -> withTableName(...)                  -> compile()       -> execute(...)
                        usingColumns(...)                                      executeAndReturnKey(...)
                        usingGeneratedKeyColumns(...)                         executeBatch(...)
                        metadata / schema options...
~~~

**Rule:** finalize configuration **before publishing the reference** to components that may invoke it concurrently. Spring designed `SimpleJdbcInsert` to be reused across multiple threads once configuration is stable. Never treat it as a builder modified per request.

## 2. Choices to Lock Down Before `compile()`

| API | Purpose | Example / Warning |
| --- | --- | --- |
| `new SimpleJdbcInsert(dataSource)` | Selects `DataSource` | Use the application-managed `DataSource` |
| `withTableName(...)` | Selects table | `audit_event` |
| `withSchemaName(...)`, `withCatalogName(...)` | Selects schema/catalog if needed | Depends on DBMS |
| `usingColumns(...)` | Limits list of columns written | `actor_name`, `event_type` |
| `usingGeneratedKeyColumns(...)` | Specifies DB-generated key column | `event_id` |
| `withoutTableColumnMetaDataAccess()` | Disables **table column** metadata processing | Must declare write columns explicitly |
| `usingQuotedIdentifiers()` | Quotes SQL identifiers | Enable only when schema/case/keywords require it |
| `compile()` | Finalizes configuration, prepares INSERT descriptor | Call after all options above |

Example of clear configuration:

~~~java
// Snippet: dataSource is an existing DataSource,
// and the audit_event table already exists before metadata is read.
SimpleJdbcInsert insert = new SimpleJdbcInsert(dataSource)
        .withTableName("audit_event")
        .usingColumns("actor_name", "event_type")
        .usingGeneratedKeyColumns("event_id");

insert.compile();
~~~

When `event_id` is DB-generated, each call does not supply a value for that column. The `usingColumns` list prevents the SQL contract from changing unexpectedly if the database gains new columns with defaults, or if the table has columns you do not intend to write.

Choose table, column, and schema names matching the actual database. SQL object names are **configuration**, not a parameter to swap freely based on request data.

## 3. What Does `compile()` Do?

`SimpleJdbcInsert` inherits `compile()` and `isCompiled()` from `AbstractJdbcInsert`. During the compile phase, Spring uses configuration together with JDBC metadata (when enabled) to determine the INSERT statement, columns, and corresponding parameter info.

- **Before compile:** configuration methods may be called; do not share the instance yet if those methods are still being invoked.
- **During compile:** Spring prepares the INSERT statement and may fetch table info via `DatabaseMetaData`; configuration errors or schema mismatches can be detected here.
- **After successful compile:** `isCompiled()` is `true`. Configuration is locked. Spring enforces rejection of configuration edits after this point.
- **Without manual compile:** `SimpleJdbcInsert` supports **lazy compile** on first execution. This is valid API behavior. However, for singletons, compiling eagerly surfaces configuration/schema errors at startup rather than on the first live request.

~~~java
// Snippet: insert has been created with table/columns declared.
insert.compile();
System.out.println(insert.isCompiled()); // true

// Lifecycle error: cannot change table after compile.
insert.withTableName("other_table"); // Rejected after compiled.
~~~

Attempts to modify configuration after compile may throw `InvalidDataAccessApiUsageException`. Calling `compile()` again is also not a "recompile with new configuration" mechanism: the API documentation states subsequent compile calls are ignored once compilation is complete.

`compile()` here **does not** compile Java code and **does not guarantee** a server-side prepared statement stays pinned in the database. It prepares the INSERT operation at the Spring layer. At execution time, the JDBC driver/database can still fail due to constraints, permissions, data, connections, or schema changes. `isCompiled() == true` is not a DB health check.

## 4. Runnable Java 17 Program: Sharing After Compile

The following example creates an H2 table, configures and compiles once, and lets **two threads** share a single `SimpleJdbcInsert`. Each thread supplies its own parameters.

Uses Spring JDBC **6.1.20** and H2 **2.3.232**. This is a plain Java application using Spring JDBC classes; no Spring Boot project is needed just to verify the principle.

~~~text
simple-insert-demo/
├── pom.xml
└── src/main/java/demo/SharedInsertDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>simple-insert-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.1.20</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.SharedInsertDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/demo/SharedInsertDemo.java**

~~~java
package demo;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcInsert;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class SharedInsertDemo {
    public static void main(String[] args) throws Exception {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl("jdbc:h2:mem:shared_demo;DB_CLOSE_DELAY=-1");
        dataSource.setUsername("sa");
        dataSource.setPassword("");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);
        jdbc.execute("""
                CREATE TABLE audit_event (
                    event_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    actor_name VARCHAR(50) NOT NULL,
                    event_type VARCHAR(30) NOT NULL
                )
                """);

        // 1. Finish configuring once the table exists.
        SimpleJdbcInsert insert = new SimpleJdbcInsert(dataSource)
                .withTableName("audit_event")
                .usingColumns("actor_name", "event_type")
                .usingGeneratedKeyColumns("event_id");

        // 2. Lock configuration BEFORE sharing.
        insert.compile();
        System.out.println("Compiled: " + insert.isCompiled());

        // 3. Two tasks share insert, while each task's parameters are separate.
        ExecutorService pool = Executors.newFixedThreadPool(2);
        long id1;
        long id2;
        try {
            Future<Long> first = pool.submit(
                    () -> insertEvent(insert, "alice", "CREATE"));
            Future<Long> second = pool.submit(
                    () -> insertEvent(insert, "bob", "UPDATE"));
            id1 = first.get();
            id2 = second.get();
        } finally {
            pool.shutdown();
        }

        Integer rows = jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_event",
                Integer.class);
        System.out.println("Rows: " + rows);
        System.out.println("Distinct keys: " + (id1 != id2));
    }

    private static long insertEvent(
            SimpleJdbcInsert insert, String actor, String eventType) {
        MapSqlParameterSource params = new MapSqlParameterSource()
                .addValue("actor_name", actor)
                .addValue("event_type", eventType);
        return insert.executeAndReturnKey(params).longValue();
    }
}
~~~

From the `simple-insert-demo/` directory, with JDK 17+ and Maven 3.9+, run:

~~~bash
mvn -q compile exec:java
~~~

Lines printed by the program (excluding build tool logs):

~~~text
Compiled: true
Rows: 2
Distinct keys: true
~~~

**Result explanation:** H2 generates an ID for each record. The two tasks may complete in either order, so the example prints only the row count and key distinctness without relying on specific ID values. Both use the **same compiled `insert` reference** while creating `MapSqlParameterSource` inside `insertEvent`; thus request data is never stored in a shared field.

`DriverManagerDataSource` is suitable for short demos because it opens connections on demand, but it does not provide connection pooling. In production, use a `DataSource` and pool configured/monitored for your application. This demo has no shared transaction between the two tasks; **sharing an instance does not automatically create a shared transaction**.

## 5. Integrating into a Spring Singleton Bean

In a Spring Boot application, configure once in the data access layer and let Spring publish the finalized bean. Example using `@Bean` and constructor injection:

~~~java
// Snippet to integrate into a Spring application, not a standalone file.
// Requires importing DataSource, @Bean, @Configuration, @Repository,
// @Qualifier, SimpleJdbcInsert, and MapSqlParameterSource.

@Configuration(proxyBeanMethods = false)
class InsertConfig {
    @Bean
    SimpleJdbcInsert auditEventInsert(DataSource dataSource) {
        SimpleJdbcInsert insert = new SimpleJdbcInsert(dataSource)
                .withTableName("audit_event")
                .usingColumns("actor_name", "event_type")
                .usingGeneratedKeyColumns("event_id");
        insert.compile();
        return insert;
    }
}

@Repository
class AuditRepository {
    private final SimpleJdbcInsert insert;

    AuditRepository(
            @Qualifier("auditEventInsert") SimpleJdbcInsert insert) {
        this.insert = insert;
    }

    long add(String actor, String eventType) {
        MapSqlParameterSource args = new MapSqlParameterSource()
                .addValue("actor_name", actor)
                .addValue("event_type", eventType);
        return insert.executeAndReturnKey(args).longValue();
    }
}
~~~

The order is intentional: **instantiate → declare table/columns/keys → compile → return bean → inject into repository**. Constructor injection gives the repository a stable reference. You can also create and compile `SimpleJdbcInsert` inside the DAO constructor if that is where configuration belongs.

**Mandatory condition:** the table and columns must already exist when compiling with metadata. If using Flyway, Liquibase, `schema.sql`, or another migration tool, ensure schema creation finishes **before** compile time. Do not assume an arbitrary `@Bean` method is automatically ordered after every migration by Spring Boot; design dependencies/lifecycle to match how your application initializes the database. When compile fails during bean creation, the error surfaces immediately at startup, which is easier to diagnose than failing on the first request.

You can rely on lazy compile as supported by the API, but even then you must **finish all configuration calls before the bean is used**. Never allow two threads to mutate configuration while other threads execute.

## 6. True Thread Safety: Isolate Per-Call Data

`SimpleJdbcInsert` is safely reusable concurrently **once its configuration is no longer modified**. That does not mean every object passed to it can also be shared arbitrarily.

| Component | Safe to Share? |
| --- | --- |
| Configured/compiled `SimpleJdbcInsert` | Yes, if configuration is not modified |
| Suitable `DataSource`, typically a connection pool | Yes, per the DataSource/pool contract |
| `MapSqlParameterSource` being mutated | Should not be shared across calls |
| Data `Map` mutated concurrently by threads | Unsafe without synchronization/isolation |
| Raw JDBC `Connection`, `PreparedStatement` | Never share arbitrarily across requests |
| Request transaction | Belongs to each request's execution context, not a field of `insert` |

**Anti-pattern:**

~~~java
// WRONG snippet: multiple threads can mutate sharedParams concurrently.
private final MapSqlParameterSource sharedParams =
        new MapSqlParameterSource();

long unsafeSave(String actor, String eventType) {
    sharedParams.addValue("actor_name", actor);
    sharedParams.addValue("event_type", eventType);
    return insert.executeAndReturnKey(sharedParams).longValue();
}
~~~

With two interleaved calls, `actor_name` could come from the first request while `event_type` comes from the second. Simply make `MapSqlParameterSource` a **local variable** inside `save` so each call has independent data. There is no need to synchronize the entire INSERT operation when the real bug is misusing the parameter object.

Calls to `execute` and `executeAndReturnKey` do not require sharing one JDBC `Connection`; `JdbcTemplate` acquires connections via the calling context's `DataSource`/Spring transaction mechanism. A shared `SimpleJdbcInsert` also does not guarantee every execution will succeed: constraints, timeouts, deadlocks, and network errors can still occur.

## 7. Metadata and Explicit Configuration

By default, `SimpleJdbcInsert` leverages `DatabaseMetaData` to discover column information, reducing boilerplate configuration. This relies on the driver supplying accurate metadata, the schema already existing, and proper access permissions.

If you want to avoid table-column metadata processing or the DB/driver has limited metadata support, declare columns explicitly:

~~~java
// Separate illustrative snippet; do not mutate an already-compiled instance.
SimpleJdbcInsert insert = new SimpleJdbcInsert(dataSource)
        .withTableName("audit_event")
        .withoutTableColumnMetaDataAccess()
        .usingColumns("actor_name", "event_type")
        .usingGeneratedKeyColumns("event_id");
insert.compile();
~~~

When column metadata is disabled, you are responsible for keeping the column list aligned with the actual DDL. Disabling this metadata step **does not** guarantee other JDBC features (especially generated-key retrieval) no longer depend on driver/DB capabilities. Test both the insert path and generated-key retrieval on the target driver.

If columns must preserve uppercase/lowercase or collide with keywords, `usingQuotedIdentifiers()` must be chosen **before compile** and follow the database's quoting rules. Do not enable quoting by guesswork, because unquoted table/column names may have been normalized in case by the database.

Major changes to schema, target table, column list, or key-generation policy may require **creating a new instance with the new configuration**. Never try to reconfigure an already-compiled instance while requests are using it.

## 8. Transactions Are Separate from Shared Configuration

`compile()` only handles the INSERT operation configuration. It does not open a long-lived transaction or hold a fixed connection for the bean's entire lifetime.

~~~java
// Snippet in a Spring service; AuditRepository is injected.
@Service
class AuditService {
    private final AuditRepository repository;

    AuditService(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void recordTwo() {
        repository.add("alice", "CREATE");
        repository.add("alice", "UPDATE");
    }
}
~~~

With an appropriate transaction manager, both operations in `recordTwo()` can join the same transaction for that **service call**. Another request can still use the same `SimpleJdbcInsert` inside its own transaction context. Spring `@Transactional` is typically proxy-based: internal self-calls via `this.recordTwo()` bypass the proxy and will not start a transaction as expected.

If a UNIQUE key conflict or constraint violation occurs, `DataAccessException` can still be thrown. Safe instance sharing does not replace proper transaction, isolation, idempotency, and retry design.

## 9. Common Mistakes and How to Fix Them

| Mistake | Consequence | Right Approach |
| --- | --- | --- |
| Publishing instance to requests before configuration finishes | Requests may run while configuration is incomplete | Finish configuration, compile, then publish |
| Calling `usingColumns` / `withTableName` after compile | API rejects configuration changes | Set all options before compile |
| Creating a new instance per INSERT | Unnecessary repeated initialization/metadata lookup | Reuse a stably configured singleton |
| Sharing a mutable `MapSqlParameterSource` | Request data can bleed into each other | Create fresh parameters per call |
| Storing a `Connection` field in a singleton repository | Stateful connection, prone to concurrency errors | Use `DataSource` and Spring JDBC |
| Compiling before migrations run | Metadata/table/column errors on startup | Ensure migration runs before compile |
| Switching tables per tenant on one instance | Breaks fixed contract, risk of race conditions | Separate instances/configurations per variant needed |
| Assuming compile guarantees the DB is always healthy | Misses runtime/constraint errors | Verify DB and handle exceptions separately |
| Using generated IDs to infer execution order of two threads | Scheduler/commit order is non-deterministic | Assert post-conditions on data, not thread scheduling |

### An Easy-to-Make Mistake

~~~java
// ANTI-PATTERN: assigning to a shared field before configuration finishes.
private SimpleJdbcInsert insert;

void init(DataSource ds) {
    insert = new SimpleJdbcInsert(ds).withTableName("audit_event");
    // Risk of other code reading the field before it is finalized.
    insert.usingGeneratedKeyColumns("event_id");
}
~~~

If you must initialize a field manually in the Spring lifecycle, use a local variable and assign once after compiling:

~~~java
// Illustrative snippet inside a constructor/initialization method.
SimpleJdbcInsert ready = new SimpleJdbcInsert(dataSource)
        .withTableName("audit_event")
        .usingColumns("actor_name", "event_type")
        .usingGeneratedKeyColumns("event_id");
ready.compile();
this.insert = ready;
~~~

Usually, constructor injection or a `@Bean` factory provides a cleaner way to publish a finalized instance than manually managing a mutable field.

## 10. Pre-Sharing Verification Checklist

1. **Schema ready:** tables, columns, and write permissions are created by migrations before `compile()`.
2. **Single configuration:** table/schema names, column list, generated key, and metadata options are decided in one place.
3. **Compiled:** `compile()` succeeds; when appropriate, assert `isCompiled()` in startup tests.
4. **Immutable after compile:** tests or reviews confirm no code mutates table/columns while handling requests.
5. **Isolated parameters:** every `execute`/`executeAndReturnKey` receives an independent `Map` or `SqlParameterSource`, never mutated by another thread.
6. **Repeated execution:** multiple sequential and concurrent inserts write correct values and receive valid keys (if any).
7. **Transaction tests:** constraints, DB errors, and rollbacks behave per business rules, rather than assuming anything from compiled state.
8. **Real DB/driver:** verify metadata, quoted identifiers, and generated keys on the actual target deployment database, not just H2.
9. **Observability:** if errors occur after deployment, distinguish compile/configuration failures from execution/transaction failures to fix the right layer.

## 11. Conclusion

**Configure once → compile → share → execute with fresh arguments.** `SimpleJdbcInsert` can be shared because it holds a **stable INSERT configuration**, while each statement's data lives in per-call parameters. Calling `compile()` once tables exist locks configuration and catches errors early; safe sharing still depends on properly designed `DataSource`, transactions, and input data.

**Official documentation:**

- [Spring Framework — Simplifying JDBC Operations with the SimpleJdbc Classes](https://docs.spring.io/spring-framework/reference/data-access/jdbc/simple.html)
- [Spring Framework 6.1.20 — AbstractJdbcInsert API](https://docs.spring.io/spring-framework/docs/6.1.20/javadoc-api/org/springframework/jdbc/core/simple/AbstractJdbcInsert.html)
- [Spring Framework — SimpleJdbcInsert API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/core/simple/SimpleJdbcInsert.html)
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
