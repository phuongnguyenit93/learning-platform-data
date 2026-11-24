# Identifying RdbmsOperation and SQL-Operation Classes When Reading Existing Spring JDBC Code

> **Goal:** When encountering `RdbmsOperation`, `MappingSqlQuery`, `SqlUpdate`, `BatchSqlUpdate`, or `StoredProcedure` in a codebase, you can distinguish each operation type, trace where SQL and parameters are configured, identify when SQL actually runs, read result types and transaction boundaries accurately. This lesson focuses on **reading and maintaining existing code**, illustrated with a runnable Java 17+ project.

These classes belong to `org.springframework.jdbc.object` in **Spring Framework JDBC**. They still appear in long-lived projects even though newer code often prefers `JdbcTemplate`, `JdbcClient`, or `SimpleJdbcCall`. Do not equate them with Spring Data Repositories or ORM/Hibernate.

## 1. Core Idea of RdbmsOperation

`RdbmsOperation` is an **abstract class** representing a relational database operation as a **configure-once, reuse-many-times object**. The operation can be a SELECT, INSERT/UPDATE/DELETE, or stored procedure. It is **not** a JDBC `Connection`/`Statement`, does not directly represent a business transaction, and does not require JPA.

Mental model:

```text
Initialize an operation:
  DataSource or JdbcTemplate
       + SQL / procedure name
       + SqlParameter / SqlOutParameter
       + mapper or options
               |
            compile()
               |
          ready for use
               |
        execute/findObject/update
               |
         Spring JDBC / JdbcTemplate
               |
      JDBC PreparedStatement / CallableStatement
               |
            database
               |
       result + cleanup
```

Seeing a constructor or `compile()` **does not prove SQL has run**. Only when the caller invokes `execute`, `findObject`, `update`, or a matching execution API does the operation hit the database.

Common responsibilities seen when reading `RdbmsOperation`:

- `setDataSource(DataSource)` or `setJdbcTemplate(JdbcTemplate)`: specifies the connection source and JDBC infrastructure used.
- `setSql(String)` and `getSql()`: the SQL statement or routine name in some classes.
- `declareParameter(SqlParameter)`, `setParameters(...)`, `setTypes(...)`: declares JDBC types and parameter order.
- `compile()`, `isCompiled()`, `afterPropertiesSet()`: finalizes metadata/configuration before use.
- `setQueryTimeout(...)`, `setFetchSize(...)`, `setMaxRows(...)`: configures JDBC behavior per driver and transaction.
- `setReturnGeneratedKeys(...)`, `setGeneratedKeysColumnNames(...)`: configures generated keys where supported.

RDBMS operation classes use `JdbcTemplate` infrastructure underneath, inheriting Spring JDBC's resource cleanup and `DataAccessException` translation. Configured instances themselves are generally safe to share/reuse, **except `BatchSqlUpdate`, which is not thread-safe**.

## 2. Inheritance Tree: Identifying Operations by Class Name

```text
RdbmsOperation [abstract]
|
+-- SqlOperation [abstract: SQL query/update]
|   |
|   +-- SqlQuery<T> [abstract: SELECT query]
|   |   |
|   |   +-- GenericSqlQuery<T> [concrete + RowMapper]
|   |   +-- MappingSqlQueryWithParameters<T> [abstract]
|   |   |     |
|   |   |     +-- MappingSqlQuery<T> [abstract]
|   |   |           |
|   |   |           +-- SqlFunction<T>
|   |   +-- UpdatableSqlQuery<T>
|   |
|   +-- SqlUpdate [concrete: INSERT/UPDATE/DELETE]
|         |
|         +-- BatchSqlUpdate [with batch queue]
|
+-- SqlCall [abstract: CallableStatement]
      |
      +-- StoredProcedure [abstract]
            |
            +-- GenericStoredProcedure [concrete]
```

| Class | Clues when reading code | Return type / primary effect |
| --- | --- | --- |
| `RdbmsOperation` | Base class, configures datasource/SQL/parameters | No single common execute method across all branches |
| `SqlOperation` | Abstract class between base and ordinary SQL | Prepares `PreparedStatement` |
| `SqlQuery<T>` | `execute(...)`, `findObject(...)` | `List<T>`; `T` or `null` |
| `MappingSqlQuery<T>` | Subclass overriding `mapRow(ResultSet,int)` | One DTO/domain object per row |
| `MappingSqlQueryWithParameters<T>` | Mapper also receives `parameters` and `context` | Per-row object able to use context |
| `GenericSqlQuery<T>` | `setRowMapper(...)`, no subclass needed | Query mapping via RowMapper |
| `SqlUpdate` | `update(...)`, `setRequiredRowsAffected(...)` | `int` affected row count |
| `BatchSqlUpdate` | `setBatchSize`, `update`, `flush`, `reset` | Batch queue and execution results |
| `SqlCall` / `StoredProcedure` | `setFunction`, IN/OUT parameters | `Map<String,Object>` procedure output |
| `GenericStoredProcedure` | Stored procedure defined by configuration | Output Map |
| `SqlFunction<T>` | Subclass under `MappingSqlQuery<T>` | Value-query SQL wrapper |
| `UpdatableSqlQuery<T>` | Overrides `updateRow`, updatable ResultSet | Special, rarely seen case |

**Distinguish names:** `SqlFunction` sits under `SqlQuery`, whereas a *stored function* can be declared via `StoredProcedure` + `setFunction(true)`. Do not assume the two classes are invoked the same way merely because both names contain "function".

## 3. Seven Questions to Read Any RDBMS Operation

When opening a Java file, XML bean definition, or Spring config, trace:

1. **What is the real class?** `SqlQuery`, `SqlUpdate`, or `SqlCall`? A field declared as a parent type can hold a subclass, so locate where the object is instantiated.
2. **Where is the object created?** `new` in a DAO constructor, `@Bean` method, XML bean definition, or factory? Reusable operations are typically instantiated once.
3. **Where is the SQL?** `super(dataSource, sql)`, `setSql`, XML property, constant, or config file? For `StoredProcedure`, `sql` is usually the *routine name*.
4. **What are the parameters?** Number of `?` placeholders, `declareParameter`, JDBC `Types`, argument order, named variants; procedures also have IN/OUT/INOUT.
5. **When is it compiled?** `compile()` in constructor/`@Bean`, or `InitializingBean.afterPropertiesSet()` during bean initialization?
6. **Where is it executed and how are results read?** `execute` for lists/procedures, `findObject` for one row, `update` for count; which mapper turns `ResultSet` into objects?
7. **Who manages transactions?** Called from a `@Transactional` service, which datasource/transaction manager, same transaction or independent queries?

For long codebases, sketch the flow:

```text
Controller/Job -> Service
                   |
                   +-> Dao.find...()
                         |
                         +-> MappingSqlQuery.execute(id)
                               |
                               +-> SQL SELECT + RowMapper
                   |
                   +-> Dao.update...()
                         |
                         +-> SqlUpdate.update(values...)
                               |
                               +-> SQL UPDATE + affected rows
                   |
              transaction boundary at service if needed
```

Names like `FindOrderQuery` or `DeactivateUser` are only hints; **the SQL and base class determine the true nature of the operation**.

## 4. Configuration Order and the Real Meaning of compile()

Illustrative snippet:

```java
// Snippet in configuration/DAO with existing DataSource ds.
SqlUpdate update = new SqlUpdate(ds,
        "UPDATE books SET title = ? WHERE id = ?");
update.declareParameter(new SqlParameter("title", Types.VARCHAR));
update.declareParameter(new SqlParameter("id", Types.BIGINT));
update.setRequiredRowsAffected(1);
update.compile();

int affected = update.update("New title", 10L);
```

- `new SqlUpdate` and `declareParameter` only configure the operation.
- `SqlParameter` belongs to `org.springframework.jdbc.core`, and `Types` belongs to `java.sql`. These declarations describe SQL types without executing anything.
- `compile()` prepares Spring's internal metadata / statement creator factory. **It is not Java compilation and does not by default send SQL to the database to run the optimizer or validate data.**
- `update("New title", 10L)` is what executes DML; bind order is title first, id second.
- `setRequiredRowsAffected(1)` requires the UPDATE to affect exactly one row, not "execute only once."

### Lifecycle When the Operation Is a Spring Bean

`RdbmsOperation` implements `InitializingBean`, whose `afterPropertiesSet()` ensures compilation. Therefore, in codebases you might **not see an explicit `compile()` call** when property injection and bean initialization handle it. Some execution paths also perform lazy compilation checks. When reading code, inspect the full configuration before assuming someone "forgot to compile."

**Never mutate `setSql`, `declareParameter`, mapper, or configuration setters on the same singleton while multiple threads use it.** The model is configure first, reuse afterward.

## 5. Identifying Parameter Types

**Positional parameters:** SQL contains `?`, and arguments to `update(v1, v2)` or `execute(v1, v2)` are bound by position. `declareParameter` order matters.

```java
// Illustrative snippet; DataSource ds and imports must be supplied.
SqlUpdate setStatus = new SqlUpdate(
        ds, "UPDATE orders SET status = ? WHERE id = ?");
setStatus.declareParameter(
        new SqlParameter("status", Types.VARCHAR));
setStatus.declareParameter(
        new SqlParameter("id", Types.BIGINT));
setStatus.compile();

int count = setStatus.update("PAID", 42L);
```

**Note:** naming a `SqlParameter` `"status"` does not turn `?` in SQL into `:status`. Methods like `executeByNamedParam(Map)` / `updateByNamedParam(Map)` follow the named-parameter contract; check the class SQL/configuration and the exact overload invoked. `StoredProcedure.execute(Map)` follows procedure IN/OUT declaration semantics and should not be confused with `SqlQuery.execute(..., context)` context maps.

**Do not guess JDBC types carelessly from Java types:** `java.sql.Types.BIGINT`, `VARCHAR`, `TIMESTAMP`, `DECIMAL`, etc. correspond to SQL parameter metadata; pay special attention to SQL NULL, decimal scale, timezones, and custom vendor types.

Typical bugs when reading or editing code:

- SQL has two `?` placeholders but only one parameter was declared or declared out of order.
- Caller passes `id` before `status` even though SQL expects status first.
- Wrong `Types` declared, preventing the driver from binding/converting.
- Modifying `WHERE` or adding a placeholder without updating `declareParameter`.
- Mixing up positional APIs with named-map APIs, or misdeclaring IN/OUT names in procedures.

## 6. SqlQuery<T>: SELECT and Reading Results

`SqlQuery<T>` is an abstract class providing reusable SELECT operations. It has several overloads:

- `execute(...)` returns **`List<T>`**, from zero rows (empty list) to many rows.
- `findObject(...)` represents a result of **at most one row**. By default it returns `null` when nothing is found and treats multiple rows as an error; this differs from `JdbcTemplate.queryForObject` on the zero-row case.
- `executeByNamedParam(Map)` or `findObjectByNamedParam(Map)` when using the named-parameters contract.
- Newer versions (Spring Framework 7) include `stream(...)`, requiring proper stream closing due to JDBC resources; do not assume this API exists on older Spring branches.

Thus, always check whether the caller calls `query.execute(id)` or `query.findObject(id)`, not just what SELECT the query defines.

### MappingSqlQuery<T>: Subclass Implementing mapRow

```java
public class FindBookById extends MappingSqlQuery<Book> {

    public FindBookById(DataSource ds) {
        super(ds, "SELECT id, title FROM books WHERE id = ?");
        declareParameter(new SqlParameter("id", Types.BIGINT));
        compile();
    }

    @Override
    protected Book mapRow(ResultSet rs, int rowNum)
            throws SQLException {
        return new Book(rs.getLong("id"),
                        rs.getString("title"));
    }
}
```

This snippet requires class `Book`, JDBC/Spring imports, and an appropriate package (see Section 10 for the complete project). In this style, `MappingSqlQuery` supplies the mapping machinery; the subclass only turns **one row** of `ResultSet` into a `Book`. `rowNum` starts at 0, **not a database ID**.

When seeing `MappingSqlQueryWithParameters<T>`, the subclass callback also receives `parameters` and `context`; used when mapping needs data outside the SQL row. Do not look for the two-parameter `MappingSqlQuery` signature in that class.

### GenericSqlQuery<T>: Injected RowMapper

```java
// Snippet requiring DataSource ds, record Book, and imports.
GenericSqlQuery<Book> query = new GenericSqlQuery<>();
query.setDataSource(ds);
query.setSql("SELECT id, title FROM books WHERE id = ?");
query.declareParameter(new SqlParameter("id", Types.BIGINT));
query.setRowMapper((rs, rowNum) ->
        new Book(rs.getLong("id"), rs.getString("title")));
query.compile();

List<Book> found = query.execute(1L);
```

Here `RowMapper` is configured via a setter, **with no separate FindBookQuery subclass**. If the code uses `setRowMapperClass`, trace that mapper class. When refactoring, preserve SQL NULL handling, column aliases, column order, and data-type mappings.

## 7. SqlUpdate: Affected Row Count, Generated Keys, and Guardrails

`SqlUpdate` is a **concrete** class representing a DML operation. It provides `update(...)`/`updateByNamedParam(...)` overloads and can take a `KeyHolder` to capture generated keys when properly configured and supported by the driver.

```java
// Illustrative snippet; DataSource ds and imports needed.
SqlUpdate deleteInactive = new SqlUpdate(ds,
        "DELETE FROM sessions WHERE active = ?");
deleteInactive.declareParameter(
        new SqlParameter("active", Types.BOOLEAN));
deleteInactive.setMaxRowsAffected(100);
deleteInactive.compile();

int rows = deleteInactive.update(false);
```

**Read counts properly:** `rows` is the number of rows affected by SQL execution, not a count of Java objects in memory. `setMaxRowsAffected` is a post-execution validation check, not a way to inject `LIMIT 100` into SQL. `setRequiredRowsAffected(1)` enforces exactly one row, useful for updates by identifier key.

When generated keys are used, inspect both `setReturnGeneratedKeys`/`setGeneratedKeysColumnNames` and the `update(params, keyHolder)` overload. Never assume `update(...)` returns the new key by default; its basic return type is `int`.

**Transaction note:** if a command executes SQL before detecting a count mismatch, changes must be rolled back inside an appropriate transaction when business rules require it. Never assume setting a guard automatically undoes DB changes if the caller already committed or has no transaction.

## 8. BatchSqlUpdate: Same Family, Yet NOT Thread-Safe

`BatchSqlUpdate extends SqlUpdate`, yet execution differs sharply: `update(...)` **enqueues parameter sets**; the batch executes when reaching the batch size or when `flush()` is called. Common APIs: `setBatchSize`, `getQueueCount`, `getExecutionCount`, `getRowsAffected`, `flush`, and `reset`.

```java
// Snippet requiring DataSource ds and a books table with a status column.
BatchSqlUpdate batch = new BatchSqlUpdate(
        ds,
        "UPDATE books SET status = ? WHERE id = ?",
        new int[] { Types.VARCHAR, Types.BIGINT },
        100
);
batch.update("READY", 1L);
batch.update("READY", 2L);
int[] counts = batch.flush();
```

**Reading this code differs from `SqlUpdate`:** two `batch.update` calls may **not** have sent two DB commands yet; look for `flush` and handling of exceptions/partial counts. `BatchSqlUpdate` holds a mutable queue and **is explicitly documented as not thread-safe in Spring Javadoc**. Never keep a single instance shared across concurrent requests assuming it is safe like a compiled `SqlQuery`. Scope each batch appropriately or synchronize properly; nor does batching guarantee atomicity without a transaction.

## 9. SqlCall, StoredProcedure, and Output Parameters

The procedure branch is:

```text
RdbmsOperation
  -> SqlCall
      -> StoredProcedure
          -> GenericStoredProcedure
```

`SqlCall` configures a `CallableStatement` rather than a plain SQL SELECT. `StoredProcedure` is abstract: typically subclassed per business use case, or configured via concrete `GenericStoredProcedure` beans. The SQL string on `StoredProcedure` is normally the **DB procedure/function name**. You may see `setFunction(true)`, `setSqlReadyForUse(true)`, or lists of `SqlParameter`, `SqlOutParameter`, and `SqlInOutParameter`.

| Declaration | Role |
| --- | --- |
| `new SqlParameter("p_id", Types.BIGINT)` | IN parameter |
| `new SqlOutParameter("p_status", Types.VARCHAR)` | OUT parameter |
| `new SqlInOutParameter("p_value", Types.NUMERIC)` | INOUT parameter |

**Illustrative** example, not runnable without a matching `read_status` stored procedure:

```java
final class ReadStatus extends StoredProcedure {
    ReadStatus(DataSource ds) {
        super(ds, "read_status");
        declareParameter(new SqlParameter("p_id", Types.BIGINT));
        declareParameter(
                new SqlOutParameter("p_status", Types.VARCHAR));
        compile();
    }

    String read(long id) {
        Map<String, Object> out =
                execute(Map.of("p_id", id));
        return (String) out.get("p_status");
    }
}
```

Using this snippet requires importing `javax.sql.DataSource`, `java.sql.Types`, `java.util.Map`, `org.springframework.jdbc.object.StoredProcedure`, `org.springframework.jdbc.core.SqlParameter`, and `SqlOutParameter`. When reading real code, verify routine name, parameter order, DB vendor, OUT types, and transactions. `execute(Map)` returns `Map<String,Object>`, unlike `SqlQuery.execute(...)` returning `List<T>`.

**Do not confuse `SqlFunction<T>` with stored functions:** `SqlFunction<T>` is a query wrapper under `SqlQuery`, whereas procedure/function calls via `SqlCall` have distinct semantics. The more convenient `SimpleJdbcCall` also invokes routines, yet **is not a subclass of `RdbmsOperation`**.

## 10. Complete Runnable Example with Java 17+, Spring Boot, and H2

This example demonstrates the exact pattern **declare operation once, compile, and execute repeatedly**. It uses **Java 17+, Maven, Spring Boot 3.5.16, Spring JDBC, and H2**. Neither Spring Data nor Hibernate is used. This is a multi-file project, so a single Java snippet cannot run via `javac` alone without dependencies.

**Structure:**

```text
jdbc-object-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/jdbcobjects/JdbcObjectApplication.java
    └── resources/
        ├── application.properties
        ├── schema.sql
        └── data.sql
```

**pom.xml**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>jdbc-object-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**src/main/resources/schema.sql**

```sql
CREATE TABLE books (
    id BIGINT PRIMARY KEY,
    title VARCHAR(120) NOT NULL
);
```

**src/main/resources/data.sql**

```sql
INSERT INTO books (id, title) VALUES (1, 'Initial');
```

**src/main/resources/application.properties**

```properties
spring.main.web-application-type=none
spring.main.banner-mode=off
logging.level.root=ERROR
spring.datasource.url=jdbc:h2:mem:jdbcobjects;DB_CLOSE_DELAY=-1
spring.sql.init.mode=always
```

**src/main/java/com/example/jdbcobjects/JdbcObjectApplication.java**

```java
package com.example.jdbcobjects;

import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Types;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.SqlParameter;
import org.springframework.jdbc.object.MappingSqlQuery;
import org.springframework.jdbc.object.SqlUpdate;

@SpringBootApplication
public class JdbcObjectApplication {

    public static void main(String[] args) {
        SpringApplication.run(JdbcObjectApplication.class, args);
    }

    public record Book(long id, String title) {}

    // Reusable SELECT.
    public static class FindBookById extends MappingSqlQuery<Book> {

        public FindBookById(DataSource ds) {
            super(ds, "SELECT id, title FROM books WHERE id = ?");
            declareParameter(new SqlParameter("id", Types.BIGINT));
            compile();
        }

        @Override
        protected Book mapRow(ResultSet rs, int rowNum)
                throws SQLException {
            return new Book(rs.getLong("id"),
                            rs.getString("title"));
        }
    }

    @Bean
    FindBookById findBook(DataSource ds) {
        return new FindBookById(ds);
    }

    // Reusable UPDATE.
    @Bean
    SqlUpdate renameBook(DataSource ds) {
        SqlUpdate op = new SqlUpdate(
                ds, "UPDATE books SET title = ? WHERE id = ?");
        op.declareParameter(new SqlParameter("title", Types.VARCHAR));
        op.declareParameter(new SqlParameter("id", Types.BIGINT));
        op.setRequiredRowsAffected(1);
        op.compile();
        return op;
    }

    @Bean
    CommandLineRunner demo(FindBookById findBook, SqlUpdate renameBook) {
        return args -> {
            System.out.println("before=" + findBook.findObject(1L));
            System.out.println("updated=" +
                    renameBook.update("Revised", 1L));
            System.out.println("after=" + findBook.findObject(1L));
            System.out.println("missing=" + findBook.findObject(999L));
        };
    }
}
```

**Run** from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

**Lines explicitly printed by the application** (aside from Maven/Spring logs):

```text
before=Book[id=1, title=Initial]
updated=1
after=Book[id=1, title=Revised]
missing=null
```

**Explanation:**

1. Spring Boot configures `DataSource` and initializes H2's table and row data.
2. Bean `FindBookById` defines the SELECT, binds BIGINT, and maps each row into a `Book` record. `compile()` only prepares the operation.
3. Bean `SqlUpdate` defines the UPDATE with two `SqlParameter`s and an exactly-one-row constraint.
4. `findObject(1L)` queries the DB and returns the record; `update("Revised", 1L)` sends DML and returns the affected row count; the next query confirms the new title.
5. `findObject(999L)` returns `null` because no row matches. If the query returned multiple rows, the finder API would treat that as an error.
6. Separate calls inside the runner do not prove a single transaction spans all of them. To make multiple changes atomic, place `@Transactional` on an appropriate business service.

This example uses Spring Framework APIs managed by Spring Boot 3.5. **Do not use APIs exclusive to Spring Framework 7** when running on this stack.

## 11. Recognizing XML-Style Configuration in Legacy Applications

Many Spring XML codebases declare `SqlUpdate` as a bean rather than instantiating it in Java:

```xml
<bean id="deactivateUser"
      class="org.springframework.jdbc.object.SqlUpdate">
    <property name="dataSource" ref="dataSource"/>
    <property name="sql"
              value="UPDATE users SET active = ? WHERE id = ?"/>
    <property name="types">
        <list>
            <value>16</value>
            <value>-5</value>
        </list>
    </property>
</bean>
```

This illustrates Spring XML configuration: codes `16` and `-5` correspond to `Types.BOOLEAN` and `Types.BIGINT`. In real projects, check parent beans, aliases, property placeholders, and bean factories. `RdbmsOperation` implements `InitializingBean`, so the container can call `afterPropertiesSet` to finish compilation. **Never edit Java code thinking the SQL changed** if the real SQL lives in external configuration outside the class.

Semantically equivalent Java example:

```java
SqlUpdate deactivateUser = new SqlUpdate(ds,
        "UPDATE users SET active = ? WHERE id = ?");
deactivateUser.declareParameter(
        new SqlParameter("active", Types.BOOLEAN));
deactivateUser.declareParameter(
        new SqlParameter("id", Types.BIGINT));
deactivateUser.compile();
```

When migrating from XML to `@Configuration`, preserve the exact datasource, SQL, JDBC types, and initialization timing.

## 12. Distinguishing from Commonly Used Modern APIs

| API seen | How to read it | Relationship to RdbmsOperation |
| --- | --- | --- |
| `JdbcTemplate.query(sql, mapper, params)` | SQL and mapper at the call site | Same Spring JDBC infrastructure; no separate query object needed |
| `NamedParameterJdbcTemplate` | SQL/params typically using `:name` | Wrapper around JdbcTemplate, not part of RdbmsOperation tree |
| `JdbcClient` | Fluent query/update facade (Spring Framework 6.1+) | Newer API; not a subclass of RdbmsOperation |
| `SimpleJdbcCall` | Stored procedures/functions often leveraging DB metadata | Not under `StoredProcedure`/`RdbmsOperation` |
| `SimpleJdbcInsert` | INSERT based on table metadata/configuration | Not `SqlUpdate` |
| `JpaRepository` | Spring Data JPA repository | Different layer, usually backed by a JPA provider/ORM |
| `EntityManager` / Hibernate | Persistence context and ORM mapping | Not JdbcTemplate/RDBMS object |

In official documentation on **object-oriented JDBC operations**, Spring notes that many `MappingSqlQuery`/`SqlUpdate` use cases can be written more simply with `JdbcTemplate` directly. Thus maintenance work usually starts by **reading current behavior accurately first**, before deciding if refactoring is worthwhile.

Two equivalent styles when SQL, mapping, and parameters match:

```java
// Object style, assuming the query is already compiled.
List<Book> a = findBooks.execute(10L);

// JdbcTemplate style, assuming jdbcTemplate and Book exist.
List<Book> b = jdbcTemplate.query(
        "SELECT id, title FROM books WHERE id >= ?",
        (rs, rowNum) ->
                new Book(rs.getLong("id"), rs.getString("title")),
        10L);
```

This illustration does not assert that `findBooks` actually uses that SQL; open its class to verify. When migrating APIs, preserve differences around `execute` (0-n rows), `findObject` (0-1 rows), null mapping, generated keys, query timeout, required rows, and transactions.

## 13. Transaction Boundaries and Thread Safety

A configured operation is normally safe to share after initialization, yet **it does not open a business transaction across multiple calls automatically**. If a service updates user status, writes an audit entry, and adjusts a quota that must commit/roll back together, put `@Transactional` on the business entry point:

```java
// Illustrative service snippet: separate SqlUpdate beans must exist.
@Service
public class ActivateAccountService {
    private final SqlUpdate activate;
    private final SqlUpdate logChange;

    public ActivateAccountService(
            SqlUpdate activate, SqlUpdate logChange) {
        this.activate = activate;
        this.logChange = logChange;
    }

    @Transactional
    public void activate(long id) {
        activate.update(true, id);
        logChange.update(id);
    }
}
```

This snippet requires imports for `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`, `SqlUpdate`, two separately configured beans, and `@Qualifier` if multiple beans share the type. It only illustrates how a *service* coordinates transactions, not a standalone program. The same datasource and transaction manager must be configured properly.

**Do not confuse two concepts:**

- **Operation thread-safety:** configuration is immutable after initialization, and each execution uses per-invocation state; uniquely, `BatchSqlUpdate` has a non-thread-safe queue.
- **Business consistency:** transactions, isolation, locking, SQL constraints, and exceptions/rollbacks. A thread-safe operation does not replace transactions.

Avoid caching JDBC `Connection` or `ResultSet` in fields of a singleton operation. Underlying `JdbcTemplate` manages connections/statements/result sets per invocation and joins Spring transactions when datasource/manager match. Never manually `commit()` or `close()` connections controlled by the transaction manager.

## 14. Common Mistakes When Reading and Editing Code

1. **Thinking `RdbmsOperation` is a JDBC `Statement` object.** It is only an operation descriptor wrapper, not a single prepared statement shared across all requests.
2. **Assuming `compile()` executes the query.** It is a configuration/factory step; SQL runs in `execute/findObject/update`.
3. **Confusing `SqlQuery.execute` return type with `StoredProcedure.execute`.** The former returns `List<T>`; procedures return an output map.
4. **Applying `JdbcTemplate.queryForObject` rules to `SqlQuery.findObject`.** For finders, zero rows can return `null`, not always an exception.
5. **Skipping subclass constructors.** SQL and parameters may be declared in `super(ds, sql)` of another class.
6. **Searching for SQL only in Java, ignoring XML/`@Bean` configs.** SQL may be injected from configuration.
7. **Changing parameter order during refactoring.** `SqlParameter` names do not override `?` positions in positional calls.
8. **Assuming `setMaxRowsAffected` becomes a SQL LIMIT.** It is a post-execution count check; rollback depends on transactions.
9. **Sharing `BatchSqlUpdate` as a singleton across threads.** Its queue is mutable and not thread-safe.
10. **Forgetting to call `flush()` for a partially filled batch.** Enqueued records may not have been sent yet.
11. **Confusing `SqlFunction` with `StoredProcedure`.** They are two different API branches.
12. **Editing SQL without updating mapper/aliases/JDBC types.** Can cause runtime errors or mis-mapped data.
13. **Thinking object operations are Spring Data Repositories or Hibernate.** They belong to `org.springframework.jdbc.object` in Spring Framework JDBC.
14. **Assuming every method shares one transaction.** Check `@Transactional`, managers, datasources, and thread boundaries.
15. **Rewriting everything to newer APIs without regression tests.** Compare query results, row counts, errors, and transactions.

## 15. Self-Check Questions When Reviewing a Pull Request

**Scenario A:** `class FindAccount extends MappingSqlQuery<Account>`, and code calls `findObject(id)`. Which class do you open and what does it return if no row exists?  
**Answer:** open `FindAccount`'s constructor/mapping to inspect SQL, parameters, and mapper; the finder can return `null` by default, which callers must handle.

**Scenario B:** `SqlUpdate.setRequiredRowsAffected(1)` is set on an UPDATE by id. Why does the code still inspect the count?  
**Answer:** the operation enforces an expected-row-count rule; check the exception contract and transaction. The count is not a primary key or generated key.

**Scenario C:** `BatchSqlUpdate.update(...)` is called twice with batch size 500 and no `flush()` in sight. Has the DB definitely received both commands?  
**Answer:** not necessarily; they may still sit in the queue. Locate `flush` or batch lifecycle management, and check concurrency/transactions.

**Scenario D:** `StoredProcedure.execute(Map.of("id", 1L))`. Does this definitely return `List<User>`?  
**Answer:** no; the procedure API returns an output `Map`; check OUT declarations and the routine contract to know exact contents.

**Scenario E:** A `SqlUpdate` bean has no `compile()` call, yet XML sets datasource, SQL, and types. Is that definitely a bug?  
**Answer:** no; bean lifecycle via `InitializingBean.afterPropertiesSet` can compile it. Check configuration and integration tests.

**Scenario F:** Code only imports `org.springframework.jdbc.object.MappingSqlQuery` with no JPA. Is Hibernate needed?  
**Answer:** no. This is Spring JDBC, requiring no ORM provider.

## 16. Practical Checklist for Reading Existing Code

- [ ] Identify whether the real class is `SqlQuery`, `SqlUpdate`, or `SqlCall`.
- [ ] Locate constructors, `@Bean`/XML configs, datasource, and transaction manager.
- [ ] Extract the exact SQL/procedure name and `?`/parameter names.
- [ ] Match `declareParameter` order against call-site values, JDBC `Types`, and nulls.
- [ ] Distinguish configuration/`compile` from actual execution calls.
- [ ] Know that `execute` returns a List, `findObject` returns one object/null, `update` returns a row count, and procedures return an output Map.
- [ ] Inspect `mapRow`/`RowMapper` callbacks and zero/multiple-row handling.
- [ ] If batched, trace queue/`flush`, thread-safety, and transaction boundaries.
- [ ] Check `setRequiredRowsAffected`, `setMaxRowsAffected`, generated keys, and SQL WHERE clauses.
- [ ] Verify transactions, checked/unchecked exceptions, isolation, and connection ownership.
- [ ] Read XML/configs and regression tests before proposing a migration to `JdbcTemplate`/`JdbcClient`.

## Official Documentation

- Spring Framework — Modeling JDBC Operations as Java Objects: https://docs.spring.io/spring-framework/reference/data-access/jdbc/object.html
- Spring Framework — Choosing an Approach for JDBC Database Access: https://docs.spring.io/spring-framework/reference/data-access/jdbc/choose-style.html
- Spring Framework — JdbcTemplate: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring API — RdbmsOperation: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/RdbmsOperation.html
- Spring API — SqlQuery: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/SqlQuery.html
- Spring API — MappingSqlQuery: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/MappingSqlQuery.html
- Spring API — SqlUpdate: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/SqlUpdate.html
- Spring API — StoredProcedure: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/StoredProcedure.html
- Spring API — BatchSqlUpdate: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/object/BatchSqlUpdate.html

**Final takeaway:** `RdbmsOperation` is a **reusable SQL operation descriptor object**. When encountering it in code, trace **class hierarchy → datasource/SQL/parameter config → compile/lifecycle → execute/update/findObject → mapping/output → transactions**. In particular, **`BatchSqlUpdate` maintains a queue and is not thread-safe**, whereas ordinary operations are designed to be reused after initialization.