# Savepoints and Partial Rollback in Spring Framework

## 1. Objectives and problem statement

After this lesson, you will be able to:

- Explain savepoints and partial rollback inside an active transaction.
- Distinguish rolling back to a savepoint, rolling back the entire transaction, releasing a savepoint, and committing.
- Use `@Transactional(propagation = Propagation.NESTED)` in Spring JDBC.
- Create and control savepoints using `TransactionStatus`/`TransactionTemplate`.
- Compare `REQUIRED`, `NESTED`, and `REQUIRES_NEW`, and identify limitations with JPA, JTA, or non-database side effects.
- Verify the actual remaining data after an inner scope fails.

**Problem:** In an order-recording workflow, the main step must succeed; an additional data-recording step can be skipped if optional data is invalid. If the additional step fails, we want to discard only that step's SQL statements and continue. However, if the final main step fails, all changes must still roll back.

Savepoints allow doing this **within the same database transaction**. Spring maps the JDBC savepoint mechanism onto `NESTED` propagation.

## 2. What is a savepoint?

A standard transaction has a `BEGIN → COMMIT/ROLLBACK` boundary. `COMMIT` confirms all changes; `ROLLBACK` discards uncommitted changes of the transaction.

A **savepoint** is a marker placed *inside a transaction*. `ROLLBACK TO SAVEPOINT` discards changes made **after the marker**, while changes before the marker remain part of the current transaction and are not yet committed.

SQL example (exact syntax varies by database):

```sql
BEGIN;

INSERT INTO audit_event(id, description) VALUES (1, 'main-before');

SAVEPOINT optional_part;
INSERT INTO audit_event(id, description) VALUES (2, 'optional');

ROLLBACK TO SAVEPOINT optional_part;

INSERT INTO audit_event(id, description) VALUES (3, 'main-after');
COMMIT;
```

After `COMMIT`, the table contains rows `id = 1` and `id = 3`; `id = 2` was rolled back to the savepoint.

| Step | Operation | Active uncommitted changes |
| --- | --- | --- |
| T0 | Start transaction | None |
| T1 | INSERT id=1 | 1 |
| T2 | Create savepoint S | 1 |
| T3 | INSERT id=2 | 1, 2 |
| T4 | Roll back to S | 1 |
| T5 | INSERT id=3 | 1, 3 |
| T6 | Outer COMMIT | 1 and 3 are confirmed |

Key points:

1. `ROLLBACK TO SAVEPOINT` **does not commit** data prior to the marker. If the outer transaction rolls back after T5, both id=1 and id=3 are discarded as well.
2. `RELEASE SAVEPOINT` only releases the marker; it does not commit data.
3. Databases can support multiple savepoints, yet rolling back to an earlier marker can invalidate markers created afterward. Check the database/driver rules.
4. Savepoints only manage changes belonging to the same database transaction; they do not undo emails, files, HTTP requests, published messages, or transactions on other connections.
5. DDL/storage engine types and a database's savepoint support can cause differences. Never infer production behavior from a single test DB alone.

## 3. Spring's NESTED mechanism

Spring uses `PlatformTransactionManager` to manage transactions. With JDBC and a single `DataSource`, `DataSourceTransactionManager` supports JDBC savepoints; `JdbcTransactionManager` is an extended variant that translates commit/rollback exceptions.

When an active outer transaction calls a method marked `@Transactional(propagation = Propagation.NESTED)` **through a Spring proxy**:

1. The transaction manager detects the existing physical transaction.
2. Spring creates a savepoint on the **same JDBC Connection**.
3. JDBC statements inside the nested method execute on that same physical transaction.
4. If the nested method returns normally, the nested scope ends; there is no physical commit yet.
5. If the method throws an exception matching a rollback rule, Spring rolls back to the savepoint and propagates the exception to the caller.
6. The outer caller can catch the exception, continue, and commit. If the outer transaction later rolls back, all uncommitted data from both outer and inner is discarded.

```text
Outer transaction: one connection, one final COMMIT
|-- INSERT A
|-- [SAVEPOINT S] ---------+
|      INSERT B           |
|      error → ROLLBACK S --+
|-- INSERT C
+-- COMMIT  => A, C remain; B is lost
```

`NESTED` creates **multiple logical rollback boundaries inside one physical transaction**; it does not create an independent commit for the inner part.

### Prerequisites

- An active outer transaction is required if the goal is partial rollback while keeping the outer transaction going. Without an outer transaction, `NESTED` starts a new transaction, similar to `REQUIRED`.
- The transaction manager permits nested transactions and the JDBC driver/database supports savepoints. `DataSourceTransactionManager` enables `nestedTransactionAllowed` by default; still verify the real driver.
- Work must use the same `DataSource` and the connection bound by Spring to the current transaction. `JdbcTemplate` participates in this connection automatically.
- The call to the annotated method must go through the Spring AOP proxy. Calling `this.someNestedMethod()` within the same bean normally bypasses the interceptor in proxy mode.
- Synchronous Spring transactions are thread-bound; they do not automatically propagate across `@Async` or new threads.

## 4. Runnable example: inner rolls back, outer still commits

This example uses **Java 17+, Spring Boot 3.5.16, Spring JDBC, H2**, and Maven. Spring Boot configures the `DataSource` and JDBC transaction manager from dependencies. The nested method is placed in a separate bean so the Spring proxy actually processes propagation.

Project structure:

```text
savepoint-demo/
├── pom.xml
└── src/main/
    ├── java/demo/
    │   ├── SavepointApplication.java
    │   ├── OuterService.java
    │   └── OptionalService.java
    └── resources/application.properties
```

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>savepoint-demo</artifactId>
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

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:savepoints;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
```

**`src/main/java/demo/SavepointApplication.java`**

```java
package demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class SavepointApplication {
    public static void main(String[] args) {
        SpringApplication.run(SavepointApplication.class, args);
    }

    @Bean
    CommandLineRunner example(JdbcTemplate jdbc, OuterService outerService) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE audit_event (
                    id BIGINT PRIMARY KEY,
                    description VARCHAR(100) NOT NULL
                )
                """);

            outerService.execute();

            System.out.println("Committed IDs: "
                    + jdbc.queryForList(
                            "SELECT id FROM audit_event ORDER BY id",
                            Long.class));
        };
    }
}
```

**`src/main/java/demo/OuterService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final OptionalService optionalService;

    public OuterService(JdbcTemplate jdbc, OptionalService optionalService) {
        this.jdbc = jdbc;
        this.optionalService = optionalService;
    }

    @Transactional
    public void execute() {
        jdbc.update(
                "INSERT INTO audit_event(id, description) VALUES (?, ?)",
                1L, "before-savepoint");

        try {
            optionalService.writeOptionalPart();
        } catch (IllegalStateException ex) {
            System.out.println("Optional part rolled back; outer continues");
        }

        jdbc.update(
                "INSERT INTO audit_event(id, description) VALUES (?, ?)",
                3L, "after-savepoint");
    }
}
```

**`src/main/java/demo/OptionalService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OptionalService {
    private final JdbcTemplate jdbc;

    public OptionalService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void writeOptionalPart() {
        jdbc.update(
                "INSERT INTO audit_event(id, description) VALUES (?, ?)",
                2L, "optional-data");

        throw new IllegalStateException("Invalid optional data");
    }
}
```

Requires JDK 17+, Maven 3.6.3+; in the directory containing `pom.xml`, run:

```bash
mvn spring-boot:run
```

Lines **printed by the program** (excluding Spring banner/logs):

```text
Optional part rolled back; outer continues
Committed IDs: [1, 3]
```

### Result analysis

- The runner bean calls `outerService.execute()` **through a proxy**, opening the outer JDBC transaction and inserting id=1.
- `OptionalService` is a separate bean, called through its proxy. `NESTED` creates a savepoint before inserting id=2.
- `IllegalStateException` is an unchecked exception, triggering `@Transactional`'s default rollback: Spring rolls back to the savepoint and then rethrows the exception.
- `OuterService` catches the error after the inner interceptor has already rolled back, inserts id=3, and returns normally.
- The outer interceptor commits; the SELECT runs **after** `execute()` returns through the proxy, so only IDs 1 and 3 are visible.

If you remove the `throw` line in `OptionalService`, the result is `[1, 2, 3]`. If outer throws a `RuntimeException` after inserting id=3 and lets it escape the proxy, the outer transaction rolls back: even records kept after rolling back to the savepoint are not committed.

> The example uses a JDBC transaction manager. Do not infer that `NESTED` works automatically with every `PlatformTransactionManager` or that a JPA persistence context automatically reverts itself.

## 5. Manual savepoints via TransactionStatus

When multiple conditional checkpoints are needed inside the same method, `TransactionStatus` (extending `SavepointManager`) exposes these APIs:

- `createSavepoint()` creates a marker and returns a handle object.
- `rollbackToSavepoint(savepoint)` rolls back changes made after that marker.
- `releaseSavepoint(savepoint)` releases the marker.
- `setRollbackOnly()` requests rollback when the transaction scope ends; **not the same** as rolling back to a specific savepoint.

The example is an **alternative service** reusing the `audit_event` table, not code run at the same time as the previous example:

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class ManualSavepointService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate template;

    public ManualSavepointService(
            JdbcTemplate jdbc,
            PlatformTransactionManager transactionManager) {
        this.jdbc = jdbc;
        this.template = new TransactionTemplate(transactionManager);
    }

    public void runWithSavepoint() {
        template.executeWithoutResult(status -> {
            jdbc.update(
                    "INSERT INTO audit_event(id, description) VALUES (?, ?)",
                    10L, "required-before");

            Object savepoint = status.createSavepoint();
            try {
                jdbc.update(
                        "INSERT INTO audit_event(id, description) VALUES (?, ?)",
                        11L, "optional");

                boolean optionalValid = false;
                if (!optionalValid) {
                    throw new IllegalArgumentException("Optional data invalid");
                }
            } catch (IllegalArgumentException ex) {
                status.rollbackToSavepoint(savepoint);
            }
            status.releaseSavepoint(savepoint);

            jdbc.update(
                    "INSERT INTO audit_event(id, description) VALUES (?, ?)",
                    12L, "required-after");
        });
    }
}
```

To test, **replace** `outerService.execute();` in the runner with `manualSavepointService.runWithSavepoint();` and inject `ManualSavepointService` into the `example` bean parameters. On a fresh database, the final SELECT returns `[10, 12]`.

The snippet above only catches an expected business error; unexpected JDBC errors should be allowed to escape and roll back the whole transaction. If rolling back to the savepoint fails, you should not attempt to commit the outer transaction. For simple cases with clear service boundaries, `NESTED` is usually more readable; `TransactionStatus` is useful when the number and timing of savepoints vary dynamically with business logic.

**Never arbitrarily obtain a separate `Connection` and manually call `setAutoCommit(false)`/`commit()`/`rollback()` inside a Spring-managed transaction.** `JdbcTemplate` and `DataSourceUtils` participate in the thread-bound connection; another connection may not belong to the same transaction, leaving those writes unprotected by the savepoint.

## 6. Comparing REQUIRED, NESTED, and REQUIRES_NEW

| Criterion | `REQUIRED` | `NESTED` | `REQUIRES_NEW` |
| --- | --- | --- | --- |
| When outer already has a transaction | Joins existing physical transaction | Same physical transaction, adds savepoint | Suspends outer, opens independent physical transaction |
| JDBC connection | Current connection | **Same connection** | Usually a different connection |
| Independent inner commit? | No | **No** | **Yes** |
| Inner throws error matching rollback rule | Typically marks shared transaction rollback-only | Rolls back to savepoint; outer can continue | Rolls back inner independently; outer can still continue |
| Outer rolls back after inner succeeded | Inner is also lost | Inner is also lost | Inner's separate commit still persists |
| Use when | Entire task must succeed/fail together | An optional JDBC step can be canceled locally | Inner part must commit independently |

**REQUIRED and `UnexpectedRollbackException`:** An inner method joins using `REQUIRED` and throws an unchecked exception through the interceptor. Outer catches the error and tries to commit. The inner participant may have marked the shared transaction `rollback-only`. Catching the exception does not clear this flag; at outer commit, `UnexpectedRollbackException` typically occurs. With `NESTED`, Spring rolls back specifically to the savepoint when eligible, so an expected inner failure does not necessarily mark the outer transaction rollback-only.

**REQUIRES_NEW:** The inner transaction commits on its own. If it commits and outer later rolls back, the inner result persists. A new connection may be required while outer holds the old connection; with an undersized connection pool, multiple threads can block each other or exhaust connections. Choose this option only when independent commit semantics are genuinely needed.

## 7. Exceptions and rollback rules

By default `@Transactional` rolls back when a `RuntimeException` or `Error` exits through the interceptor; checked exceptions normally do not trigger rollback unless `rollbackFor` is configured. Example configuring rollback for a checked exception:

```java
@Transactional(
    propagation = Propagation.NESTED,
    rollbackFor = java.io.IOException.class
)
public void importOptionalFile() throws java.io.IOException {
    // Execute JDBC operations; IOException may occur.
}
```

This is an **illustrative** signature, not a standalone program. Key notes:

1. **The exception must pass through the interceptor** for annotation-driven automatic rollback. If inner catches and swallows the error in a `try/catch` and returns normally, Spring normally treats the nested scope as successful. Rethrow an appropriate error or explicitly request rollback.
2. **Catching errors in outer is a business decision.** Continue only when the optional error can be safely ignored; do not swallow infrastructure failures or invariant violations.
3. **A savepoint does not clear the whole transaction's rollback-only flag** if another component already set it. When the shared transaction is no longer valid, rolling back everything is usually the safe choice.
4. **Create the savepoint before the risky section.** A marker created after an error cannot revert the transaction to its pre-error state.
5. **A nested scope finishing normally does not mean data is durable.** The final commit is always decided by the outer physical transaction.

## 8. Special limitations

### JPA and Hibernate

`JpaTransactionManager` disallows nested transactions by default. Some configurations support JDBC savepoints for JDBC operations participating in a JPA transaction, yet **the `EntityManager`/persistence context/first-level cache does not automatically revert to its pre-savepoint state**. An entity modified in memory can retain its new values even after the database partially rolled back.

Therefore, you cannot copy the `JdbcTemplate` example straight to `JpaRepository.save()` and expect the entire entity graph to roll back partially. When mixing JDBC with JPA, verify flushing, refresh/clear, entity state, and transaction manager/driver behavior with real integration tests. Setting `nestedTransactionAllowed=true` alone does not guarantee correct JPA nested semantics. For complex JPA workflows, consider different transaction boundaries or an appropriate compensation strategy.

### JTA/XA, R2DBC, and multiple databases

`JtaTransactionManager` does not automatically support JDBC savepoints like `DataSourceTransactionManager`. Do not assume `NESTED` works with JTA/XA/distributed transactions. Reactive/R2DBC applications must check `ReactiveTransactionManager` and driver support separately: the synchronous `JdbcTemplate` example above does not translate verbatim to a reactive pipeline. A savepoint on connection A cannot roll back a transaction on connection B.

### Side effects outside the transaction

HTTP requests, emails, files, messages sent to a broker, or external caches can succeed even when SQL rolls back to a savepoint. Suitable alternatives include transactional outbox, idempotent handling, and compensation; savepoints do not replace those mechanisms.

### DDL and driver capabilities

Some databases perform an implicit commit on DDL; some drivers restrict releasing savepoints. When needed, inspect `Connection.getMetaData().supportsSavepoints()` and run integration tests against the exact production DB/version. Never treat H2 test results as proof for another DB.

## 9. Testing behavior

Test each scenario on a fresh database (or reset data between runs):

| Scenario | Test change | Expected outcome |
| --- | --- | --- |
| Inner fails, outer handles it | Keep example code | Commits id 1, 3 |
| Inner succeeds | Remove `throw` from `OptionalService` | Commits id 1, 2, 3 |
| Outer fails after catching inner | Add unchecked exception at end of `OuterService.execute()` | Outer rolls back; no uncommitted IDs remain |
| Inner changed to REQUIRED | Switch propagation from NESTED to REQUIRED, still throw unchecked exception | Outer typically hits rollback-only/`UnexpectedRollbackException` |
| Call NESTED without outer | Call inner from a bean outside any transaction | NESTED creates a new physical transaction |
| Self-invocation | Call `this.someNestedMethod()` within the same bean | Annotation may be ignored because it bypasses the proxy |

You can enable logging during testing:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Enable verbose logging only when needed and control log volume. Verify **data after the transaction ends**, rather than asserting exceptions alone. A test running inside a transaction that rolls back at test completion can hide true commit results; structure tests to observe the actual boundary.

If you encounter `NestedTransactionNotSupportedException`, check the actual transaction manager, `nestedTransactionAllowed`, driver/database savepoint support, whether an outer transaction exists, and JDBC/JPA/JTA mixing. If partial rollback does not happen, check proxy invocation and exception types/rollback rules.

## 10. Common mistakes

1. **Confusing NESTED with REQUIRES_NEW:** NESTED does not commit independently; outer rollback still discards inner changes.
2. **Outer is already rollback-only and trying to save it with a savepoint:** partial rollback cannot force a rollback-only transaction to commit.
3. **Calling a nested method via `this`:** bypasses the AOP proxy; move the nested method to a separate Spring bean.
4. **Swallowing errors inside inner:** the proxy sees a normal return and does not roll back automatically. Throw an appropriate error or invoke the rollback API.
5. **Using JDBC savepoints for JPA entity state:** persistence context memory does not automatically synchronize with partial rollback.
6. **Opening a separate connection and committing manually:** SQL on that connection is outside the managed transaction/savepoint.
7. **Assuming SQL rollback undoes all side effects:** emails, events, or API requests require separate consistency strategies.
8. **Catching every error and continuing:** DB errors, rollback failures, or unknown failures can leave the transaction unsafe to commit.
9. **Testing only on H2:** you must verify compatibility with the real driver/database.
10. **Holding the outer transaction open too long:** savepoints do not eliminate long locks, timeouts, and resource contention within a single transaction.

## 11. Choosing the right mechanism

- **All succeed or fail together:** Use a single `REQUIRED` transaction; severe errors roll back everything.
- **An optional JDBC step can fail while outer continues:** `@Transactional(NESTED)` with a supporting JDBC transaction manager and driver.
- **Multiple dynamic checkpoints inside one method:** `TransactionTemplate` + `TransactionStatus.createSavepoint()/rollbackToSavepoint()`.
- **Inner must commit independently even if outer rolls back:** `REQUIRES_NEW`, evaluating connection pool sizing and data consistency consequences.
- **Involves JPA entity state, multiple databases, or non-DB side effects:** redesign transaction boundaries or combine outbox/compensation; do not treat JDBC savepoints as a universal rollback mechanism.

## 12. Self-check

**1.** `INSERT A → SAVEPOINT S → INSERT B → ROLLBACK TO S → INSERT C → COMMIT` leaves which records? **A and C**; B was rolled back.

**2.** Inner `NESTED` succeeds, then outer rolls back later; does inner's data remain? **No**; they share the same physical transaction.

**3.** Outer catches an exception from inner `REQUIRED` and returns normally; is commit guaranteed to succeed? **No**; inner may have marked the shared transaction rollback-only, causing `UnexpectedRollbackException`.

**4.** Why can calling an annotated nested method via `this` have no effect? **Because Spring transaction proxies do not intercept self-invocation** in proxy mode.

**5.** Does a savepoint cancel an already-sent HTTP request? **No**; it only manages changes belonging to the corresponding database transaction.

**6.** Does `RELEASE SAVEPOINT` make data durable? **No**; it must wait for the physical transaction's `COMMIT`.

## 13. Official references

- Spring Framework — Transaction propagation/`PROPAGATION_NESTED`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — DataSource/JDBC connections: https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html
- Spring Framework — `TransactionStatus` and SavepointManager methods: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — `JpaTransactionManager` and JPA savepoint limitations: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html

**Takeaway:** A savepoint is a selective rollback point **inside a single physical transaction**; `NESTED` is how Spring JDBC organizes it. Final commit authority still belongs to the outer transaction.