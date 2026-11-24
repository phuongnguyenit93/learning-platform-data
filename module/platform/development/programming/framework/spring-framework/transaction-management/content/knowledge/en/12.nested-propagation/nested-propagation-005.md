# Manager, Driver, and Database Support Conditions for NESTED and Savepoints

## 1. Learn the True Essence Before Enabling PROPAGATION_NESTED

In Spring Framework, `Propagation.NESTED` allows a branch of work to be rolled back **to a savepoint** inside the **same physical transaction** opened by the outer work. As a result, changes before the savepoint can be preserved and the outer transaction can continue, provided the entire infrastructure genuinely supports it and rolling back to the savepoint succeeds.

However, merely writing `@Transactional(propagation = Propagation.NESTED)` **does not guarantee** nested transactions will work on every system. This feature depends simultaneously on:

1. **Spring transaction manager:** the manager implementation must support nested transactions/savepoints appropriately and have `nestedTransactionAllowed` enabled.
2. **JDBC driver/connection:** the connection must actually support APIs to create, roll back to, and when needed release savepoints.
3. **Database and operation types:** the engine must support valid transactions/savepoints for the SQL statements executed; there must be no DDL implicit commits or out-of-transaction operations breaking expectations.

This lesson presents how to identify all three conditions, verify from metadata through actual behavior, configure Spring JDBC, run a Java 17+ example with H2, write an integration test for a manager with `NESTED` disabled, and understand limitations with JPA, JTA, DDL, multiple DataSources, and transaction propagation.

After this lesson, you can answer practical questions: "Why does the same NESTED annotation work with H2 yet fail on another DB?", "Is `supportsSavepoints() == true` sufficient?", "Why can outer still commit after an inner rollback?", "Why does NESTED sometimes behave like REQUIRED?", and "Why is enabling `nestedTransactionAllowed` on `JpaTransactionManager` still dangerous for JPA state?".

## 2. NESTED Uses One Physical Transaction, Not an Independent Transaction

Diagram of a JDBC transaction:

```text
Connection A / physical transaction T
|
| BEGIN
| INSERT order-header (outer)
|
| SAVEPOINT S1                    <- inner NESTED starts
| INSERT optional-line (inner)
| business error occurs
| ROLLBACK TO SAVEPOINT S1        <- discards work after S1
|
| INSERT audit-log (outer)
| COMMIT T                        <- commits header + audit-log
|
+--> optional-line data is absent from the final result
```

In Spring, typically:

- Outer `@Transactional(REQUIRED)` creates physical transaction T on the JDBC connection.
- Inner `@Transactional(NESTED)` is invoked **through a Spring transactional proxy**, recognizes that T already exists, and creates a savepoint on **that same connection**.
- If inner succeeds, the savepoint is completed/released according to the resource's capability; there is no separate physical commit yet.
- If inner throws an exception triggering a rollback rule, the nested scope's interceptor rolls back to the savepoint. Outer can catch the exception and continue.
- **Only the outermost transaction** commits or rolls back all of T. A later outer rollback still discards all writes inside T, including inner parts that previously "succeeded."

### Comparing Three Commonly Confused Propagations

| Inner propagation when outer has already opened a transaction | Physical transaction | When inner rolls back | If outer rolls back afterward |
| --- | --- | --- | --- |
| `REQUIRED` | Shared, does not automatically create a savepoint | Usually marks the shared transaction rollback-only; outer commit may throw `UnexpectedRollbackException` | All outer/inner writes are lost |
| `NESTED` | Shared **with a savepoint** when supported | Rolls back the nested scope to the savepoint; outer can continue | All writes of the physical transaction are lost |
| `REQUIRES_NEW` | Opens a separate physical transaction, suspends outer | Only the new transaction rolls back; outer continues | Independently committed inner may **not** be undone by outer rollback |

`NESTED` is not a way to "commit early" for a child branch. It is **partial rollback within the same physical transaction**. Because it uses the same connection, an inner `NESTED` scope usually inherits the isolation, timeout, and attributes of the outer physical transaction instead of having a separate transaction with independent settings.

### When No Outer Transaction Exists

A `PROPAGATION_NESTED` method called when **no active physical transaction exists** behaves similarly to `REQUIRED`: it creates a new transaction and commits/rolls back that entire transaction when the method ends. There is no outer transaction in which to place a savepoint. Therefore, a test that "calls the nested method directly" is not enough to conclude the system supports savepoints.

## 3. Condition 1 — The Spring Transaction Manager Must Support NESTED

### 3.1. DataSourceTransactionManager and JdbcTransactionManager

In the case of a **local single-DataSource JDBC transaction**, Spring's `DataSourceTransactionManager` supports `PROPAGATION_NESTED` based on JDBC savepoints. The `nestedTransactionAllowed` property on this manager defaults to **`true`**. `JdbcTransactionManager` extends `DataSourceTransactionManager` with the same mechanism while also adding exception translation on commit/rollback.

Java configuration example:

```java
@Bean
DataSourceTransactionManager transactionManager(DataSource dataSource) {
    DataSourceTransactionManager manager =
            new DataSourceTransactionManager(dataSource);
    manager.setNestedTransactionAllowed(true);
    return manager;
}
```

This is a fragment; `@Bean`, `DataSource`, and class/import declarations belong in the complete project in section 8. Setting `true` explicitly makes the lab easy to verify, which does not mean calling the setter is always required since the JDBC manager allows nested by default.

Conceptually equivalent XML configuration:

```xml
<bean id="transactionManager"
      class="org.springframework.jdbc.datasource.DataSourceTransactionManager">
    <property name="dataSource" ref="dataSource"/>
    <property name="nestedTransactionAllowed" value="true"/>
</bean>
```

`dataSource` must be defined and used properly by the DAO/`JdbcTemplate`. When the manager and DAO use two incompatible DataSources, a savepoint on one connection **cannot control** statements executed on the other connection.

**Next mandatory condition:** the JDBC driver and database must still genuinely support savepoints; `nestedTransactionAllowed=true` only permits Spring to try creating a nested scope, **it does not synthesize the feature on the backend**.

### 3.2. Disabling NESTED to Verify Fail-Fast Errors

You can explicitly disable it:

```java
manager.setNestedTransactionAllowed(false);
```

When inner requests `NESTED` and an outer transaction exists, a JDBC-style Spring transaction manager rejects the nested scope, typically with `NestedTransactionNotSupportedException`, rather than silently falling back to `REQUIRED`.

**Note:** if there is no outer transaction, a `NESTED` call can still create a new transaction like `REQUIRED`, so a test calling only the standalone nested method **will not detect** that the manager disabled nested. Test **NESTED inside an open transaction**.

### 3.3. JpaTransactionManager Does Not Mean "Nested JPA"

`JpaTransactionManager` can support **JDBC savepoints for JDBC access** participating in a JPA transaction with appropriate configuration, yet `nestedTransactionAllowed` on this manager defaults to **`false`**. Setting it to `true` **does not turn JPA into a system supporting nested persistence-context transactions**.

Savepoints act on JDBC connection/database state, **not automatically rolling back state inside the JPA `EntityManager` and cached/managed entities**. For instance, after rolling back to a savepoint, an entity modified in the persistence context may still hold values mismatched with the database. Continuing to flush without handling that state properly can push changes that were supposed to roll back right back into the DB.

Therefore:

- **Do not infer** that `@Transactional(NESTED)` on a JPA repository/service will give safe partial rollback semantics like JDBC.
- If JDBC nested/savepoints are genuinely needed in a JPA application, you must verify that the manager, `JpaDialect`, JDBC driver, connection, and JDBC-access code share compatible resources, and clearly understand the boundary between the persistence context and savepoints.
- Alternatives may include changing transaction boundaries, using an independent `REQUIRES_NEW` transaction where business rules allow, or separating JDBC operations with explicit design. This is **not** a matter of flipping one flag and calling it done.

### 3.4. JTA and Other Managers

`JtaTransactionManager` works with JTA/global transactions. **Do not assume** `PROPAGATION_NESTED` has an available JDBC savepoint mechanism under JTA: standard JTA does not provide the same local JDBC savepoint semantics. Rely on transaction provider/manager documentation and real tests; when unsupported, treat `NESTED` as unavailable.

Similarly, do not infer from `PlatformTransactionManager` (an interface) that **every implementation** has savepoint semantics. Reactive transactions use a different API from synchronous JDBC; verify the specific manager/provider rather than mechanically applying JDBC material here.

### 3.5. Difference Between "Allowed" and "Executable"

A complete setup requires **all of the conditions**:

```text
@Transactional(NESTED)
        |
        v
Is there an active outer transaction?
  | No -> create a new transaction like REQUIRED
  | Yes
  v
Does the manager support it and nestedTransactionAllowed=true?
  | No -> cannot create a nested scope
  | Yes
  v
Does the connection support savepoints?
  | No -> cannot create a savepoint
  | Yes
  v
Do the DB/engine and SQL statements actually have rollback-to-savepoint semantics?
  | No -> cannot rely on partial rollback results
  | Yes
  v
NESTED can operate as designed
```

If any condition fails, do not default to `REQUIRES_NEW` as an "equivalent replacement"; it has **different semantics** (an independent physical transaction).

## 4. Condition 2 — JDBC Driver/Connection Must Actually Support Savepoints

### 4.1. Relevant JDBC APIs

Standard JDBC APIs:

```java
Connection connection = dataSource.getConnection();
boolean supported = connection.getMetaData().supportsSavepoints();

// When already inside an actual JDBC transaction:
Savepoint savepoint = connection.setSavepoint("after_header");
connection.rollback(savepoint);
connection.releaseSavepoint(savepoint);
```

This is an **illustrative fragment**, not meant to run directly as a complete application. Common imports: `java.sql.Connection`, `java.sql.Savepoint`, and `javax.sql.DataSource`.

Meaning:

- `DatabaseMetaData.supportsSavepoints()` is the capability flag **reported by the JDBC driver**.
- `Connection.setSavepoint()` requests creating a savepoint on the current connection.
- `Connection.rollback(savepoint)` requests returning to the saved marker without rolling back the entire transaction.
- `Connection.releaseSavepoint(savepoint)` releases the savepoint when supported/needed.

Typically you must be inside a JDBC transaction with `autoCommit=false` to create a savepoint. Calling `setSavepoint()` on a connection with `autoCommit=true` can throw `SQLException` per the JDBC contract. In a Spring application, `DataSourceTransactionManager` manages `autoCommit` and resource binding when opening transactions; **do not manually toggle autoCommit on a connection managed by Spring**.

### 4.2. supportsSavepoints() Is Necessary but Not Sufficient

`supportsSavepoints()==true` is a metadata **support signal**, not end-to-end proof. Reasons metadata may say true while the application still fails:

- Reading metadata from a **different DataSource/connection** than the connection actually used by the transaction manager.
- The driver advertises support yet has restrictions by version/server/engine or specific SQL statements.
- A transaction was not opened properly; the connection is running with `autoCommit=true`.
- The database runs an implicit-commit operation that invalidates the savepoint.
- Some SQL ran over another connection, preventing the savepoint from rolling back that part.
- JPA persistence context or external side effects outside the database are not rolled back by JDBC savepoints.

Therefore, combine **two layers of verification**:

1. Check `DatabaseMetaData.supportsSavepoints()` on the real DataSource.
2. Run a **smoke test creating a savepoint -> writing data -> rollback(savepoint) -> committing outer -> SELECT verification** and an integration test using Spring `@Transactional(NESTED)` itself.

If `supportsSavepoints()==false`, do not claim backend support. If `true` yet real tests fail, trust runtime outcomes and analyze failures layer by layer.

### 4.3. Potential Driver Errors

JDBC can throw `SQLFeatureNotSupportedException` or `SQLException` when a savepoint operation is invalid or unsupported by the backend. Spring may wrap/translate them into transaction-hierarchy exceptions; the exact type depends on where the failure occurs and the implementation.

`NestedTransactionNotSupportedException` typically relates to the manager rejecting nested transactions; **do not use a single exception type to diagnose every savepoint failure**. In logs, record the root cause, driver name, DB product/version, sanitized URL without secrets, and the specific transaction manager.

## 5. Condition 3 — Database/Engine and SQL Statements Must Be Rollback-Capable

### 5.1. Engine Must Support Real Transactions

Savepoint rollback relies on the database's ability to maintain transactions, undo logs/snapshots, or equivalent mechanisms. For example:

- **H2** supports transactions and `SAVEPOINT`/`ROLLBACK TO SAVEPOINT` commands, making it suitable as a practice environment.
- **PostgreSQL** supports savepoints, though you must understand transaction semantics per statement and SQL error.
- **MySQL** requires special attention to storage engines: InnoDB supports transactions/savepoints, whereas non-transactional tables (such as MyISAM) do not roll back changes as expected.
- Other DBMSs also have savepoints or similar mechanisms, yet SQL dialects, limits, and semantics can vary.

Do not treat all "SQL databases" alike. Check product/version/engine and run tests on the **actual deployment environment** instead of relying solely on H2.

### 5.2. DDL and Implicit Commits Are Major Risks

Some DBs auto-commit when executing DDL statements or handle DDL transactions differently from DML. For instance, `CREATE TABLE`, `ALTER TABLE`, and `TRUNCATE`, depending on the database, can trigger an implicit commit or fail to roll back like ordinary INSERT/UPDATE statements.

In this lesson's Java example:

- Create tables **before** opening business transactions.
- Test NESTED primarily with **DML** (`INSERT`), which is rollback-capable in H2.
- Do not place schema migrations or unverified DDL statements inside a nested scope.
- For real DBs, verify DDL/trigger/procedure behavior specifically via documentation and actual tests.

### 5.3. You Cannot "Roll Back" Another Connection

A savepoint belongs to **one connection and transaction**. If outer writes on connection A while inner manually opens `DriverManager.getConnection(...)` on connection B with auto-commit, rolling back a savepoint on A **cannot** undo committed writes on B.

In Spring JDBC, `JdbcTemplate` uses `DataSourceUtils` to obtain the connection bound to the thread's transaction. Use the same `DataSource` for the transaction manager and DAOs. With connection pools, the `Connection` object may be a wrapper/proxy, yet it must represent the same transaction-bound resource.

### 5.4. Other Practical Limitations

- Long-running transactions and savepoints can hold locks/resources. Rolling back to a savepoint **does not mean** all locks are immediately released on every database.
- Databases may limit the number of savepoints or nesting depth; deep nesting of scopes can affect memory and latency.
- Database constraints, stored procedures, triggers, and post-SQL-error transaction states vary. Some errors render the entire transaction unusable; rolling back to a savepoint may not rescue a transaction aborted by backend-specific rules.
- Files, HTTP requests, emails, Kafka messages, and off-DB caches do not automatically roll back with a JDBC savepoint.
- Writes to multiple databases or replicated targets are not atomically governed by a single JDBC savepoint.

**Conclusion:** Having supporting metadata and correct annotations is still not enough. Inspect **results after the outer transaction commits** to confirm rows before/after the savepoint remain and rows from the rolled-back branch are gone.

## 6. Decision Table: Manager × Driver × Database

| Manager | Driver | Database/engine | Expectation with outer transaction + NESTED |
| --- | --- | --- | --- |
| `DataSourceTransactionManager`, nested allowed | JDBC savepoints supported | Transactional DML supports savepoints | **Can** roll back to savepoint; requires integration test |
| `JdbcTransactionManager`, nested allowed | JDBC savepoints supported | Transactional DML supports savepoints | Similar, plus exception translation |
| `DataSourceTransactionManager`, nested **disabled** | Yes | Yes | Manager rejects nested scope |
| `DataSourceTransactionManager`, nested allowed | Savepoints unsupported | Any | Cannot create nested savepoint |
| `DataSourceTransactionManager`, nested allowed | Yes | Nontransactional engine / implicit commit | Partial rollback not guaranteed |
| Default `JpaTransactionManager` | Yes | Yes | Nested disabled by default; **do not infer nested JPA** |
| `JpaTransactionManager` with nested enabled | Yes | Yes | Only potentially useful for integrated JDBC access; JPA persistence context **does not roll back with savepoint** |
| `JtaTransactionManager` / provider without nested support | Yes | Yes | No standard JDBC nested semantics to rely on by default |
| Any manager, but **no outer transaction** | Compatible | Compatible | `NESTED` acts like a new transaction (`REQUIRED`), **not** a partial savepoint |

Every "can" cell means the **necessary condition** is met, not a substitute for actual verification.

## 7. How to Verify Layer by Layer Properly

Follow an ordered checklist so that when a failure occurs, you know which layer has the issue.

### Spring / Bean Layer

1. Obtain the actual Spring-managed `PlatformTransactionManager`; inspect its concrete class via logs/debugging.
2. If using `DataSourceTransactionManager`, confirm `isNestedTransactionAllowed()` is `true`, or intentionally disable it to test negative cases.
3. Confirm the `@Transactional(NESTED)` service bean is invoked **through a Spring proxy**, not `this.inner()`.
4. Confirm an outer physical transaction already exists when calling nested; otherwise `NESTED` creates a new transaction and proves nothing about savepoint support.

### JDBC Connection Layer

5. Use the **same DataSource** as the manager to read `connection.getMetaData().supportsSavepoints()`.
6. Check driver name/version and database product/version when needed: `getDriverName()`, `getDriverVersion()`, `getDatabaseProductName()`, `getDatabaseProductVersion()`.
7. Run a JDBC smoke test with `setAutoCommit(false)`, `setSavepoint`, `rollback(savepoint)`, `commit` (on a dedicated test connection, **without** altering autoCommit on a Spring-managed connection).
8. Do not look only at metadata; test the actual SQL and schema involved.

### Spring End-to-End Layer

9. Outer inserts row A; inner `NESTED` inserts B and throws an unchecked exception.
10. Catch the exception in outer, insert C, and let outer commit.
11. SELECT after the outer proxy returns; the result must be **A and C**, without B.
12. Next test inner succeeding followed by outer rolling back: all rows from that physical transaction must disappear.
13. Test calling nested directly with no outer: it should open a new transaction; throwing an error rolls back all work in that method.

## 8. Runnable Java 17+ Example with Spring Boot, H2, and NESTED

The following Spring Boot project intentionally:

- Explicitly configures `DataSourceTransactionManager` with `nestedTransactionAllowed=true`.
- Uses one `JdbcTemplate` pointing to the **same DataSource**.
- Splits outer and inner into **two beans** so Spring AOP applies `NESTED`.
- Runs success, partial rollback, outer rollback, and nested without an outer.
- Checks `supportsSavepoints()` metadata.
- Writes integration tests proving real outcomes and testing a manager with nested **disabled**.

**Environment:** JDK 17+, Maven, Spring Boot **3.5.6**, in-memory H2. H2 does not represent every production engine, yet it effectively demonstrates the JDBC savepoint mechanism.

### 8.1. Directory Structure

```text
nested-support-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── NestedSupportApplication.java
    │   │   ├── TransactionConfig.java
    │   │   ├── OuterWorkService.java
    │   │   └── InnerNestedService.java
    │   └── resources/
    │       └── application.properties
    └── test/java/demo/
        └── NestedSupportIntegrationTest.java
```

### 8.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>nested-support-demo</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

### 8.3. application.properties

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:nested_support;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.main.banner-mode=off
```

The **named** in-memory H2 database `nested_support` lets connections in the same JVM share the same database. `DB_CLOSE_DELAY=-1` keeps the database alive even if the connection pool closes/opens connections during the demo. Data disappears when the JVM actually terminates.

### 8.4. TransactionConfig.java — Declaring the Manager

**`src/main/java/demo/TransactionConfig.java`**

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

@Configuration
public class TransactionConfig {

    @Bean
    public DataSourceTransactionManager transactionManager(
            DataSource dataSource) {
        DataSourceTransactionManager manager =
                new DataSourceTransactionManager(dataSource);
        manager.setNestedTransactionAllowed(true);
        return manager;
    }
}
```

Declaring the primary transaction manager named `transactionManager` ensures `@Transactional` services use this manager in the demo. Spring Boot auto-configures the H2 `DataSource` and `JdbcTemplate`. When Spring Boot already auto-creates a `PlatformTransactionManager` bean, no extra manager declaration is needed unless customizing, yet here we declare it explicitly to inspect the **exact manager type and flag**.

### 8.5. InnerNestedService.java — Genuine Nested Scope

**`src/main/java/demo/InnerNestedService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerNestedService {
    private final JdbcTemplate jdbc;

    public InnerNestedService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void accepted(long id) {
        jdbc.update(
                "INSERT INTO nested_event(id, note) VALUES (?, ?)",
                id, "nested-accepted");
    }

    @Transactional(propagation = Propagation.NESTED)
    public void rejected(long id) {
        jdbc.update(
                "INSERT INTO nested_event(id, note) VALUES (?, ?)",
                id, "nested-rejected");

        throw new IllegalStateException("inner rejected");
    }
}
```

When an outer transaction exists, the interceptor for `accepted`/`rejected` creates a **savepoint** on the transaction's connection. `rejected` throws `IllegalStateException`; as an unchecked exception, it triggers rolling back the nested scope to the savepoint before the exception reaches outer. `accepted` finishes the nested scope normally; data is still not physically committed until outer commits.

If `rejected` is called **without an outer transaction**, `NESTED` acts like `REQUIRED`: it opens a new transaction and rolls back that entire new transaction upon throwing.

### 8.6. OuterWorkService.java — Verifying Partial Rollback

**`src/main/java/demo/OuterWorkService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterWorkService {
    private final JdbcTemplate jdbc;
    private final InnerNestedService inner;

    public OuterWorkService(JdbcTemplate jdbc, InnerNestedService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional
    public void partialRollback(long beforeId, long nestedId, long afterId) {
        insert(beforeId, "outer-before");

        try {
            inner.rejected(nestedId);
        } catch (IllegalStateException expected) {
            System.out.println("outer handled nested error");
        }

        insert(afterId, "outer-after");
    }

    @Transactional
    public void allSuccess(long beforeId, long nestedId, long afterId) {
        insert(beforeId, "outer-before");
        inner.accepted(nestedId);
        insert(afterId, "outer-after");
    }

    @Transactional
    public void outerFailure(long beforeId, long nestedId) {
        insert(beforeId, "outer-before");
        inner.accepted(nestedId);
        throw new IllegalStateException("outer rejected");
    }

    private void insert(long id, String note) {
        jdbc.update(
                "INSERT INTO nested_event(id, note) VALUES (?, ?)",
                id, note);
    }
}
```

`OuterWorkService` and `InnerNestedService` are **two separate Spring beans**. The call `inner.rejected(...)` passes through the inner bean's Spring proxy, giving the transaction interceptor the opportunity to create a savepoint and roll back to it. If everything were collapsed into one bean calling `this.rejected(...)`, proxy mode could skip transactional advice for the inner method, producing different results.

### 8.7. NestedSupportApplication.java — Driver Probe and Post-Commit Verification

**`src/main/java/demo/NestedSupportApplication.java`**

```java
package demo;

import java.sql.Connection;
import java.util.List;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class NestedSupportApplication {
    public static void main(String[] args) {
        SpringApplication.run(NestedSupportApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(
            DataSource dataSource,
            JdbcTemplate jdbc,
            OuterWorkService outer,
            InnerNestedService inner) {
        return args -> {
            jdbc.execute("""
                    CREATE TABLE IF NOT EXISTS nested_event (
                        id BIGINT PRIMARY KEY,
                        note VARCHAR(80) NOT NULL
                    )
                    """);

            // Reports driver capability only; does not replace an integration test.
            try (Connection connection = dataSource.getConnection()) {
                System.out.println(
                        "driver savepoints: "
                                + connection.getMetaData().supportsSavepoints());
            }

            outer.partialRollback(1L, 2L, 3L);
            System.out.println("partial rows: " + ids(jdbc, 1L, 3L));

            outer.allSuccess(11L, 12L, 13L);
            System.out.println("success rows: " + ids(jdbc, 11L, 13L));

            try {
                outer.outerFailure(21L, 22L);
            } catch (IllegalStateException ex) {
                System.out.println("outer error: " + ex.getMessage());
            }
            System.out.println("outer rollback rows: " + ids(jdbc, 21L, 22L));

            try {
                inner.rejected(31L);
            } catch (IllegalStateException ex) {
                System.out.println("standalone error: " + ex.getMessage());
            }
            System.out.println("standalone rows: " + ids(jdbc, 31L, 31L));
        };
    }

    private static List<Long> ids(
            JdbcTemplate jdbc, long start, long end) {
        return jdbc.queryForList(
                "SELECT id FROM nested_event WHERE id BETWEEN ? AND ? ORDER BY id",
                Long.class, start, end);
    }
}
```

**Why is this verification design sound?**

1. `CommandLineRunner` is not marked `@Transactional`: each outer service call has a real transaction boundary instead of being held inside an outer runner transaction.
2. The table is created **before** calling business transactions, avoiding DDL implicit commit interference with the test.
3. The `ids(...)` query is called **after the outer proxy has committed/rolled back**, not relying on "read your own writes" inside an uncommitted transaction.
4. Each case uses distinct IDs, avoiding confusion with records created by other cases.
5. `inner.rejected(31L)` is called without an outer transaction and rolls back entirely, checking `NESTED` semantics without a parent.

### 8.8. Running, stdout, and Meaning

In the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn spring-boot:run
```

Lines printed by **the program itself** (excluding Spring/Maven logs):

```text
driver savepoints: true
outer handled nested error
partial rows: [1, 3]
success rows: [11, 12, 13]
outer error: outer rejected
outer rollback rows: []
standalone error: inner rejected
standalone rows: []
```

Explanation:

| Flow | Condition | DB result after boundary |
| --- | --- | --- |
| `partialRollback(1,2,3)` | Outer T is open; inner `NESTED` writes 2 then fails; rolls back to savepoint | Only **1, 3** |
| `allSuccess(11,12,13)` | Inner and outer finish without error | **11, 12, 13** present |
| `outerFailure(21,22)` | Inner completes nested scope, yet outer throws error | **Neither 21 nor 22** |
| `inner.rejected(31)` called standalone | No outer T; NESTED opens new transaction, throws error | **No 31** |

The result `partial rows: [1, 3]` is the strongest evidence that **Spring NESTED successfully performed partial rollback on the actual JDBC connection**, rather than relying solely on metadata. Had `REQUIRED` been used for inner, the participating inner's failure would normally mark the shared transaction rollback-only and outer commit could throw `UnexpectedRollbackException`.

## 9. Integration Test: Proving Manager, Driver, and DB Work Together

Add file **`src/test/java/demo/NestedSupportIntegrationTest.java`**:

```java
package demo;

import java.sql.Connection;
import java.sql.SQLException;
import java.util.List;
import javax.sql.DataSource;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.NestedTransactionNotSupportedException;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class NestedSupportIntegrationTest {
    @Autowired
    private DataSource dataSource;

    @Autowired
    private DataSourceTransactionManager transactionManager;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private OuterWorkService outer;

    @Autowired
    private InnerNestedService inner;

    @Test
    void managerAndDriverAdvertiseSupport() throws SQLException {
        assertTrue(transactionManager.isNestedTransactionAllowed());

        try (Connection connection = dataSource.getConnection()) {
            assertTrue(connection.getMetaData().supportsSavepoints());
        }
    }

    @Test
    void nestedRollbackPreservesOnlyOuterWrites() {
        outer.partialRollback(1001L, 1002L, 1003L);
        assertEquals(List.of(1001L, 1003L),
                ids(1001L, 1003L));
    }

    @Test
    void successfulNestedScopeStillDependsOnOuterCommit() {
        outer.allSuccess(1011L, 1012L, 1013L);
        assertEquals(List.of(1011L, 1012L, 1013L),
                ids(1011L, 1013L));

        assertThrows(IllegalStateException.class,
                () -> outer.outerFailure(1021L, 1022L));
        assertEquals(List.of(), ids(1021L, 1022L));
    }

    @Test
    void nestedWithoutOuterBehavesLikeNewTransaction() {
        assertThrows(IllegalStateException.class,
                () -> inner.rejected(1031L));
        assertEquals(List.of(), ids(1031L, 1031L));
    }

    @Test
    void managerWithNestedDisabledRejectsNestedInsideOuter() {
        DataSourceTransactionManager disabledManager =
                new DataSourceTransactionManager(dataSource);
        disabledManager.setNestedTransactionAllowed(false);

        TransactionTemplate outerTemplate =
                new TransactionTemplate(disabledManager);
        TransactionTemplate nestedTemplate =
                new TransactionTemplate(disabledManager);
        nestedTemplate.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_NESTED);

        assertThrows(NestedTransactionNotSupportedException.class,
                () -> outerTemplate.executeWithoutResult(
                        outerStatus ->
                                nestedTemplate.executeWithoutResult(
                                        nestedStatus -> {
                                            // Only verifies capability to create a nested scope.
                                        })));
    }

    private List<Long> ids(long start, long end) {
        return jdbc.queryForList(
                "SELECT id FROM nested_event WHERE id BETWEEN ? AND ? ORDER BY id",
                Long.class, start, end);
    }
}
```

Run:

```bash
mvn test
```

**Expected:** 5 tests pass under H2 and this configuration. `@SpringBootTest` starts the application context, runs `CommandLineRunner` which creates the table and uses IDs 1–31; tests use IDs 1001–1031 to avoid collisions. Tests have no `@Transactional` on the class/methods, avoiding accidentally creating an outer test transaction.

### 9.1. What Does the Negative Test Mean?

`managerWithNestedDisabledRejectsNestedInsideOuter` constructs a separate `DataSourceTransactionManager` **used only in this test**, configured with `nestedTransactionAllowed=false`. `outerTemplate` opens a physical transaction and `nestedTemplate` attempts to create a nested scope inside it. The manager refuses, and the test expects `NestedTransactionNotSupportedException`.

This tests the **manager layer**, not a claim that H2/the driver lacks savepoints. The same H2 and DataSource still support savepoints in the other tests.

### 9.2. Metadata Tests vs. Behavior Tests Differ

- `managerAndDriverAdvertiseSupport` confirms the **manager flag** and **JDBC metadata**.
- `nestedRollbackPreservesOnlyOuterWrites` confirms **actual behavior** through Spring proxy + savepoint + SQL + commit.
- `successfulNestedScopeStillDependsOnOuterCommit` confirms a savepoint has no independent commit.
- `nestedWithoutOuterBehavesLikeNewTransaction` shows that a test lacking an outer transaction **does not prove** a savepoint was created.

Only declare true environment support once behavior tests pass on the **real database**. If CI uses H2 while production uses PostgreSQL/MySQL/Oracle/SQL Server, maintain dedicated integration tests running on the matching production DB (e.g., via Testcontainers) with the exact driver/engine.

## 10. Plain JDBC Smoke Test to Isolate Driver/Database Issues

When `@Transactional(NESTED)` fails, isolate Spring from the experiment with a separate JDBC connection. This is a **diagnostic method**, not how to manipulate a Spring-managed connection in production.

Example **illustrative fragment** using the already-created `nested_event` table:

```java
try (Connection connection = dataSource.getConnection()) {
    boolean initialAutoCommit = connection.getAutoCommit();
    connection.setAutoCommit(false);

    try {
        try (PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO nested_event(id, note) VALUES (?, ?)")) {
            ps.setLong(1, 8001L);
            ps.setString(2, "outer-jdbc");
            ps.executeUpdate();

            Savepoint point = connection.setSavepoint("before_optional");

            ps.setLong(1, 8002L);
            ps.setString(2, "nested-jdbc");
            ps.executeUpdate();

            connection.rollback(point);
            connection.commit();
        }
    } catch (SQLException ex) {
        connection.rollback();
        throw ex;
    } finally {
        connection.setAutoCommit(initialAutoCommit);
    }
}
```

Requires imports for `java.sql.Connection`, `java.sql.PreparedStatement`, `java.sql.Savepoint`, `java.sql.SQLException`, and an available `DataSource`. The fragment omits the enclosing class/method. It creates a **dedicated test connection** and manages its own transaction; **do not run it inside an open Spring-managed transaction**.

After running successfully, a post-commit SELECT will see id=8001 and **not** id=8002. If the plain JDBC test fails, the issue likely lies in the **driver, database, engine, SQL, or transaction mode**, not necessarily Spring AOP. If the JDBC test passes while Spring NESTED fails, revisit the manager, DataSource sharing, proxy configuration, and outer transaction.

### Avoiding Turning a Smoke Test into Data Corruption

Use a resettable test DB, dedicated IDs, and do not run this snippet concurrently with other tests sharing those IDs. In a real application, never call `setAutoCommit(false)`/`commit()` manually on a connection already bound by the Spring transaction manager, as doing so breaks the transaction lifecycle.

## 11. Common Failure Scenarios and Troubleshooting

### 11.1. NestedTransactionNotSupportedException Immediately Upon Entering Inner

First identify which manager is actually running. `nestedTransactionAllowed=false` may be the cause, or the manager/backend lacks savepoint support. Do not inspect only the annotation. Check the manager bean, flag, outer transaction, and root cause.

### 11.2. NESTED Annotation Present Yet No Savepoint Actually Exists

Check whether inner is called **through a Spring proxy**, or via `this.inner()` in the same bean. Check whether an outer transaction is active: without an outer, NESTED starts a new transaction like REQUIRED. Both situations yield "no savepoint observed" because the **prerequisites** to create a nested scope are missing.

### 11.3. Driver Reports supportsSavepoints True Yet Rollback Fails

Run a raw JDBC smoke test with `autoCommit=false`, the same DB/engine, and the same schema. Check for DDL implicit commits, SQL that put the transaction into an aborted state, invalidated savepoints, or driver exceptions. Do not conclude "metadata is false" when the driver reports true yet the transaction state is incompatible.

### 11.4. Inner NESTED Rolls Back Yet Outer Also Rolls Back

Check whether the exception was **caught by outer after the nested interceptor rolled back to the savepoint**, or escaped through the outer interceptor and triggered a full transaction rollback. Also verify inner truly has `NESTED`; if it is `REQUIRED`, a participant failure can mark the shared transaction rollback-only.

### 11.5. Inner NESTED Returned, Yet Outer Rollback Erases Everything

This is the **correct** behavior: a nested scope has no independent commit. Only the outermost transaction can commit the physical transaction. If business logic genuinely needs a separate audit record that survives outer rollback, consider `REQUIRES_NEW` or an outbox/alternative design instead of hoping NESTED commits independently.

### 11.6. SQL Executes on a Different Connection

Inner code acquires a different JDBC connection manually or calls an API outside the database. The outer connection's savepoint does not govern that work. Ensure JDBC work uses `JdbcTemplate` with the same `DataSource`, or explicitly separate transactions when needed.

### 11.7. Trying to Use Nested JPA Like Nested JDBC

`EntityManager` holds state in the first-level cache/persistence context. Rolling back a JDBC savepoint does not automatically reset JPA state. Enabling the nested flag on `JpaTransactionManager` does not solve everything. Prefer avoiding treating JPA nested transactions as equivalent to JDBC savepoints.

### 11.8. DDL or Nontransactional Storage Engine

Some DDL causes an implicit commit; some engines do not roll back DML. Even perfect Spring configuration cannot fix backend limitations. Test real behavior on the production DB/engine and separate schema migrations from business transactions.

### 11.9. Testing Only on H2 and Concluding Production Supports It

H2 is a tool for learning and verifying mechanics, not a 100% compatibility guarantee across all DBs. Test the real driver version, DB version, SQL dialect, and transaction engine. For critical SQL statements, run integration tests against the target backend.

### 11.10. Test Method Has @Transactional Itself

Spring TestContext can create an outer transaction when a test is annotated with `@Transactional`, causing the `NESTED` service to create a savepoint inside the **test-managed transaction** rather than a physical transaction opened by an application service. Commit timing and rollback behavior will differ; tests roll back by default at the end. To test service boundaries, write tests **without `@Transactional` on the test**.

### 11.11. Multiple Managers Have No Shared Transaction

If outer uses `transactionManagerA` while inner uses `transactionManagerB`, you have no basis to assume both share a physical transaction. `NESTED` does not span multiple databases/resources by placing a savepoint on one connection. Choose managers and DataSources deliberately and verify actual resource binding.

### 11.12. Confusing Savepoint Release with Commit

`releaseSavepoint` only removes a marker; it does not commit data. NESTED success does not generate a durable commit on its own. If outer rolls back, changes are still discarded.

## 12. Checklist Before Using NESTED in a Real Project

- [ ] The manager is an implementation with appropriate nested/savepoint support; do not rely merely on `PlatformTransactionManager`.
- [ ] `nestedTransactionAllowed=true` when required, and the exact manager bean is used by the proxy.
- [ ] Outer has opened a **physical transaction**; inner is invoked **through a Spring proxy**.
- [ ] The manager and all JDBC DAOs use the same transaction-bound `DataSource`.
- [ ] JDBC metadata `supportsSavepoints()` returns true on the target connection.
- [ ] A raw JDBC smoke test creates/rolls back a savepoint successfully with the matching SQL and DB/engine.
- [ ] A Spring NESTED integration test rolls back inner's part while keeping outer's part after outer commits.
- [ ] An outer rollback test discards even nested-success changes.
- [ ] Tests run against the real production database/driver/engine, not only H2.
- [ ] NESTED is not used expecting an "independent commit" or rollback of JPA persistence context state.
- [ ] DDL implicit commits, nontransactional engines, external side effects, and long transactions have been considered.
- [ ] A clear fallback strategy exists if the backend lacks support: adjust transaction boundaries/workflow design instead of silent fallback.

## 13. Exercises and Self-Check Questions

**Exercise 1:** The manager is `DataSourceTransactionManager` with `nestedTransactionAllowed=true`, the JDBC driver supports savepoints, yet the table uses a nontransactional engine. Does the Spring annotation guarantee inner data rolls back?

**Answer:** No. The database/engine must genuinely roll back DML; even a properly configured manager and driver cannot make nontransactional operations atomic.

**Exercise 2:** `supportsSavepoints()` returns true. Can you skip integration tests?

**Answer:** No. The metadata flag only reflects what the driver reports. You must test actual `setSavepoint`/`rollback(savepoint)` and `@Transactional(NESTED)` against the target DB/SQL/engine.

**Exercise 3:** Calling `inner.rejected(31)` from a caller with no outer transaction. Does it create a nested savepoint?

**Answer:** There is no outer transaction in which to save a savepoint; `NESTED` acts like a new `REQUIRED` transaction and rolls back the method's entire transaction when throwing an exception.

**Exercise 4:** Outer writes A, inner `NESTED` writes B and fails, outer catches and writes C, outer commits. The backend supports savepoints properly. Which records remain?

**Answer:** A and C remain; B is rolled back to the savepoint.

**Exercise 5:** Inner `NESTED` succeeds, then outer rolls back. Does inner keep its data because it "finished"?

**Answer:** No. Inner still belongs to the same physical transaction. Outer rollback cancels everything.

**Exercise 6:** Why does setting `nestedTransactionAllowed=true` on `JpaTransactionManager` not prove nested JPA semantics?

**Answer:** Savepoints affect the JDBC connection/database, without automatically rolling back entity state in the JPA persistence context. Extreme care is needed if JDBC/JPA share a transaction.

**Exercise 7:** Manager flag is false, yet calling `@Transactional(NESTED)` directly with no outer transaction still works. Is that a contradiction?

**Answer:** No. Without an outer transaction, nested can behave like REQUIRED. To test the flag, invoke NESTED inside an active outer transaction.

**Exercise 8:** Why shouldn't you call `connection.rollback(savepoint)` yourself on a Spring-managed connection while a service is running?

**Answer:** That bypasses the transaction manager and can break Spring's resource/lifecycle management. Use `@Transactional(NESTED)` or the appropriate transaction status/savepoint API within a controlled design.

**Exercise 9:** You need an independent inner commit so data remains even after outer rolls back. Is NESTED suitable?

**Answer:** No. Consider `REQUIRES_NEW` or an appropriate separate storage/reconciliation mechanism, while evaluating business consistency and connection pool resources.

**Exercise 10:** In production, JDBC metadata reports true yet running a DDL statement inside the nested scope makes the savepoint vanish. Which layer should diagnosis focus on?

**Answer:** Database/SQL semantics, specifically implicit commits and DDL types. Do not blame everything on `@Transactional` or driver metadata.

## 14. References

- Spring Framework — Transaction propagation and `PROPAGATION_NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — JDBC connections, `DataSourceTransactionManager`, and savepoints: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — `DataSourceTransactionManager` Javadoc, `nestedTransactionAllowed` defaults to true: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — `JpaTransactionManager` Javadoc, JDBC-only nested and default false flag: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html
- Spring Framework — `NestedTransactionNotSupportedException`: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/NestedTransactionNotSupportedException.html
- JDBC API — `DatabaseMetaData.supportsSavepoints()`, `Connection.setSavepoint()`, `Connection.rollback(Savepoint)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/DatabaseMetaData.html
- H2 Database — transaction support: https://h2database.com/html/features.html
- H2 Database — `SAVEPOINT` and `ROLLBACK TO SAVEPOINT` commands: https://h2database.com/html/commands.html

**In summary:** `PROPAGATION_NESTED` operates via **savepoints within one physical transaction**, not an independent transaction. Use it only when the **manager allows it**, the **driver/connection supports it**, and the **database/engine/SQL genuinely supports rollback-to-savepoint**. Verify both metadata and behavior with an outer transaction + nested rollback + post-commit SELECT. If any layer lacks support, design an explicit alternative instead of assuming the annotation will handle it automatically.