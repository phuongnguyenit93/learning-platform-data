# One Physical Transaction with Multiple Savepoints: `NESTED` and JDBC Savepoints in Spring

## Objectives

After this lesson, you will be able to:

1. Accurately describe what **one physical transaction with multiple savepoints** means, in contrast to creating multiple independent transactions.
2. Explain how `@Transactional(propagation = Propagation.NESTED)` creates a nested scope and uses savepoints when a JDBC transaction already exists.
3. Trace the order of creating, releasing, and rolling back savepoints, especially the scenario where **an inner savepoint succeeds but its parent savepoint is rolled back**.
4. Predict which data remains when an inner scope fails, the outer catches the exception, continues, and eventually commits; and why an outer rollback discards even inner scopes that succeeded.
5. Distinguish between `NESTED`, `REQUIRED`, and `REQUIRES_NEW`, and know the requirements regarding the transaction manager, JDBC driver, and invoking through a Spring proxy.
6. Run the **Java 17+, Spring Boot 3.3.5, JDBC/H2** example, test it with JUnit 5, and use `SavepointManager` when manual control is needed.

**Scope:** Within Spring Framework transaction management, this lesson focuses on `NESTED`/savepoints for JDBC transactions. Do not assume that JPA, JTA, reactive transactions, or every DBMS automatically supports the same mechanism.

---

## 1. One Transaction, Multiple Rollback Points

A physical transaction is the unit handled by the database at `BEGIN`, `COMMIT`, or `ROLLBACK`. With JDBC, the transaction manager manages `autoCommit` state, the connection, and transaction completion. Once the outermost method has started transaction T, business steps can create **savepoints** inside T.

A savepoint is a **marker within an open transaction**. You can ask the database to execute `ROLLBACK TO SAVEPOINT S` to undo changes made **after S** while keeping transaction T running. Then you can continue executing SQL and commit T. However, **a savepoint does not commit any data**.

Conceptual example:

```text
BEGIN T
  INSERT A             -- outer operation
  SAVEPOINT S1
  INSERT B             -- operation in nested scope 1
  ROLLBACK TO S1       -- discard B, keep A

  SAVEPOINT S2
  INSERT C             -- operation in nested scope 2
  RELEASE S2           -- end savepoint S2, C is still NOT COMMITTED

  INSERT D             -- outer operation
COMMIT T               -- A, C, D commit together
```

Result after commit: **A, C, D remain; B is lost**.

If you replace the last line with `ROLLBACK T`, **none of A, B, C, or D are committed**, including C which belonged to a nested scope that completed successfully. This is the most important takeaway of the lesson.

### Three Conceptual Levels to Distinguish

| Concept | Role | Lifetime |
| --- | --- | --- |
| Physical transaction **T** | The DB's commit/rollback unit | From transaction start until final commit/rollback |
| Logical transaction scope | The boundary established by `TransactionInterceptor` for each advised method | While passing through the corresponding `@Transactional` |
| JDBC **savepoint** | A partial rollback marker inside T | While T is active and the driver/manager supports it |

Multiple logical scopes do not automatically correspond to multiple physical transactions. With `NESTED`, you typically have **one T** and **one savepoint for each inner scope that needs nesting**. A savepoint only enables partial recovery; it does not turn an inner scope into an autonomous transaction.

## 2. How Does `PROPAGATION_NESTED` Work?

Spring provides the enum `org.springframework.transaction.annotation.Propagation.NESTED`.

```java
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(propagation = Propagation.NESTED)
public void saveOptionalDetail() {
    // SQL that needs to be rolled back independently to a savepoint when an outer T already exists.
}
```

This is a snippet illustrating annotation placement, not a standalone method that can be compiled directly with `javac`. Operating rules:

- **Existing transaction T with a compatible manager:** Spring creates a **nested logical scope**; with `DataSourceTransactionManager` and JDBC savepoints, it creates a new savepoint **inside T**.
- **Nested method succeeds:** Spring ends the nested scope and typically releases the savepoint. Changes made after this marker **remain inside T and are not committed yet**.
- **Nested method fails and matches a rollback rule:** Spring rolls back to the savepoint, discarding the nested scope's changes. The outer method can catch the exception **after the inner interceptor completes**, continue T, and commit the remaining valid parts.
- **No existing transaction:** `NESTED` behaves like `REQUIRED`, starting a new physical transaction. There is no outer T in which to nest a savepoint.
- **Nested/savepoints not supported:** It must not silently downgrade from `NESTED` to an alternative with different semantics. The framework may throw `NestedTransactionNotSupportedException` or a related transaction/resource exception, depending on the cause.

The Spring AOP proxy must **actually intercept the call** to the nested method. If a bean calls `this.nestedMethod()` on itself, the annotation may be bypassed due to self-invocation. In that case, no separate savepoint is created by `@Transactional(NESTED)` at that call site.

### A Detailed Timeline

```text
Outer proxy -> BEGIN T
  outer INSERT(1)

  Nested-A proxy -> SAVEPOINT S1
    INSERT(2)
    throw RuntimeException
  Nested-A interceptor -> ROLLBACK TO S1, exit with exception

  outer catches error from Nested-A
  Nested-B proxy -> SAVEPOINT S2
    INSERT(3)
  Nested-B interceptor -> release S2 (DOES NOT COMMIT T)

  outer INSERT(4)
  Outer proxy -> COMMIT T
```

**After commit, 1, 3, and 4 exist; 2 does not.** The failed inner scope is restored to its own marker, and the physical transaction is not necessarily marked globally rollback-only like a typical `REQUIRED` participating scope.

**Do not overgeneralize:** a severe DB error, a rollback-only mark from another scope, or an exception at the outer boundary can still cause T to roll back entirely. `NESTED` has no magic to turn every error into a valid DB state.

## 3. Multiple Savepoints: Sequential and Nested

The phrase "multiple rollback points" has two common meanings.

### 3.1. Sequential Savepoints

```text
BEGIN T
  INSERT outer-A
  S1 -> INSERT inner-1 -> rollback S1
  S2 -> INSERT inner-2 -> release S2
  S3 -> INSERT inner-3 -> rollback S3
  INSERT outer-B
COMMIT T
```

Savepoints S1, S2, and S3 allow each optional step to succeed or fail independently. Inner-2 "succeeding" only means it **was not rolled back to its savepoint**, not that it was independently committed.

This model is appropriate if a primary record must exist, while some enrichment/line-items are allowed to be discarded when validation fails; **there must be a business contract allowing partial success**.

### 3.2. Savepoints Nested Inside Another Savepoint

A nested method can call **another bean** that also has `@Transactional(NESTED)`:

```text
BEGIN T
  outer INSERT A

  SAVEPOINT S_PARENT
    INSERT B
    SAVEPOINT S_CHILD
      INSERT C
    RELEASE S_CHILD        -- C remains in T, not committed yet

    throw ParentFailure
  ROLLBACK TO S_PARENT     -- discard C and B

  outer INSERT D
COMMIT T
```

Final result: **A and D**. Even though C belonged to a child scope that returned successfully, it is still discarded because **S_PARENT was created before both B and C**. Releasing a child savepoint does not make its data durable against a rollback to the parent savepoint.

**Ordering rule:** `ROLLBACK TO S` affects changes in T since S was created, not just changes belonging to the method associated with S's name. On the same connection, rolling back to an older marker can discard the work of child scopes that already released their savepoints but occurred after that marker.

### Is a Savepoint a Copy of the Database?

No. A DBMS typically maintains transactional state and log/undo/lock structures for partial rollback; it does not create a full DB copy for each savepoint. Lifecycle, resource cost, naming, and post-rollback savepoint handling depend on the DBMS/driver. Do not treat a savepoint as a data snapshot that can be recalled after T has committed or fully rolled back.

## 4. How Does `NESTED` Differ from `REQUIRED` and `REQUIRES_NEW`?

| Characteristic | Inner `REQUIRED` | Inner `NESTED` | Inner `REQUIRES_NEW` |
| --- | --- | --- | --- |
| When outer T exists | Joins T | Joins T and creates a savepoint when supported | Suspends T and creates a new physical transaction |
| Physical transaction | Same T | **Same T** | Inner is independent of T |
| Inner rollback on error | Usually marks shared T rollback-only | **Rolls back to savepoint**; outer can continue | Rolls back inner's separate physical transaction |
| Inner returns normally | Does not commit T | Releases savepoint, **does not commit T** | Can commit inner's separate transaction |
| Outer rolls back after inner succeeds | Inner SQL in T also rolls back | Inner SQL in T also rolls back | Separately committed inner does not automatically roll back with outer |
| Partial recovery capability | Limited once shared T is rollback-only | Yes, when savepoint can recover and T remains valid | Yes, via separate transaction |
| Resources | One matching transaction/connection | One matching JDBC transaction/connection | May require a new connection; watch connection pool |
| Depends on JDBC savepoint | No | Usually yes | Does not use savepoints in the same sense |

In `REQUIRED`, an inner `TransactionInterceptor` encountering an unchecked exception usually marks the shared T rollback-only. If the outer catches it and tries to commit, the caller may see `UnexpectedRollbackException`. With `NESTED` backed by real savepoints, Spring typically rolls back **only the nested scope** and lets the outer continue. These are two different policies, not just different names.

In `REQUIRES_NEW`, the inner transaction is truly independent and can commit even if the outer eventually rolls back. Choosing it instead of `NESTED` changes atomicity, adds connection requirements, and introduces the possibility of data divergence. Do not use it merely to "make rollback errors go away."

## 5. Conditions for Having Multiple JDBC Savepoints in Spring

To rely on the model above, you must verify the following factors.

1. **Supporting transaction manager:** `DataSourceTransactionManager` supports JDBC savepoints; `JdbcTransactionManager` is a subclass of it. The `nestedTransactionAllowed` flag on `DataSourceTransactionManager` defaults to `true`, though you should still verify the actual manager and configuration.
2. **JDBC driver and DBMS support savepoints:** Check the database documentation and `Connection.getMetaData().supportsSavepoints()` when needed. Not every combination of driver, DB, or SQL operation follows the same rules.
3. **Same transaction manager/DataSource:** `NESTED` must see a matching existing transaction T bound to the current resource. It does not implicitly create savepoints across two datasources.
4. **Same connection management path:** Code uses `JdbcTemplate` or `DataSourceUtils` to participate in the Spring transaction, rather than manually acquiring a new connection in a way that bypasses transaction-bound resources.
5. **Calls go through a Spring proxy:** A different bean, or an explicit transaction boundary that Spring actually intercepts; not merely an annotation present in source code.
6. **Transaction T remains committable after rolling back to a savepoint:** SQL errors, ORM state, other resources, or a `REQUIRED` scope marking global rollback-only can still break committability.
7. **No independent commit inside the nested scope:** All nested SQL only becomes durable after `COMMIT T`.

In particular, `JpaTransactionManager` sets `nestedTransactionAllowed=false` by default. Even if enabled for some direct JDBC operations, a savepoint only reflects the **JDBC connection**, and does not automatically revert the **JPA EntityManager/persistence context** to a corresponding state. Do not promise that rolling back to a savepoint will fully restore ORM state cached in memory. JPA does not generally provide nested transactions with JDBC savepoint semantics.

For the examples below, plain JDBC/H2 is used to avoid that confusion.

## 6. Runnable Example: Spring Boot + Java 17 + JDBC/H2

We will build a project with a `tx_events` table. Each event has an `id` and an `event_name`; at the end of each scenario, we read the event list **after the transaction boundary has completed**. This lets us clearly distinguish SQL statements that ran from committed data.

There are **three scenarios**:

- **A — Selective recovery:** one inner savepoint fails; another inner succeeds; a nested parent fails after its nested child has succeeded. The outer catches at the right places and commits the valid steps.
- **B — Full outer rollback:** an inner `NESTED` scope completes successfully, but the outer throws a runtime exception; all of T rolls back, and the inner has no independent commit.
- **C — Standalone `NESTED`:** no outer transaction exists; the nested method creates a new physical transaction just like `REQUIRED`, and commits upon success.

### 6.1. Project Structure

```text
nested-savepoints-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/savepoint/
    │   │   ├── DeepStepService.java
    │   │   ├── NestedStepService.java
    │   │   ├── OuterWorkflowService.java
    │   │   └── SavepointsApplication.java
    │   └── resources/
    │       ├── application.yml
    │       └── schema.sql
    └── test/java/example/savepoint/
        └── SavepointsApplicationTest.java
```

Create a Spring Boot Gradle project targeting JDK 17+ or use Spring Initializr to get the Gradle wrapper. Java files must reside in the `example.savepoint` package. Running the command in section 6.10 does not require a web server.

### 6.2. File `settings.gradle`

```groovy
rootProject.name = 'nested-savepoints-demo'
```

### 6.3. File `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Spring Boot manages Spring Framework, JDBC, and H2 versions via dependency management. Version 3.3.5 uses Spring Framework 6.1.x, suitable for Java 17 examples. `spring-boot-starter-jdbc` brings `JdbcTemplate` and transaction infrastructure onto the classpath. We will declare an **explicit JDBC transaction manager** so savepoint behavior does not rely on readers guessing default beans.

### 6.4. File `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:nested_savepoints_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

The in-memory H2 database persists across the run; `spring.sql.init.mode=always` makes Boot execute `schema.sql`. Do not place `@Transactional` on the ApplicationRunner, so each scenario opens and closes its own physical transaction according to the service code.

### 6.5. File `src/main/resources/schema.sql`

```sql
CREATE TABLE tx_events (
    id INTEGER PRIMARY KEY,
    event_name VARCHAR(80) NOT NULL
);
```

The table has no initial data. ApplicationRunner deletes rows before each case so results do not depend on earlier cases. The demo's INSERT statements use unique IDs per case and are valid against the schema; errors are thrown **from Java after a successful INSERT**, allowing us to evaluate savepoint behavior in isolation without handling transaction states after SQL syntax/constraint errors.

### 6.6. File `src/main/java/example/savepoint/DeepStepService.java`

```java
package example.savepoint;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DeepStepService {
    private final JdbcTemplate jdbc;

    public DeepStepService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void succeed(int id, String name) {
        jdbc.update(
            "INSERT INTO tx_events (id, event_name) VALUES (?, ?)",
            id, name
        );
    }
}
```

`DeepStepService` is a separate bean with a public method. When called through a Spring proxy from another nested method participating in T, it creates a **deeper scope's savepoint**. If it completes normally, the savepoint is released, but the data remains uncommitted data within T.

### 6.7. File `src/main/java/example/savepoint/NestedStepService.java`

```java
package example.savepoint;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NestedStepService {
    private final JdbcTemplate jdbc;
    private final DeepStepService deep;

    public NestedStepService(JdbcTemplate jdbc, DeepStepService deep) {
        this.jdbc = jdbc;
        this.deep = deep;
    }

    private void insert(int id, String name) {
        jdbc.update(
            "INSERT INTO tx_events (id, event_name) VALUES (?, ?)",
            id, name
        );
    }

    @Transactional(propagation = Propagation.NESTED)
    public void failAfterInsert(int id, String name) {
        insert(id, name);
        throw new IllegalStateException("nested-failed-" + id);
    }

    @Transactional(propagation = Propagation.NESTED)
    public void succeed(int id, String name) {
        insert(id, name);
    }

    @Transactional(propagation = Propagation.NESTED)
    public void failAfterDeepChildSuccess() {
        insert(5, "parent-write");
        deep.succeed(6, "child-write");
        throw new IllegalStateException("parent-failed");
    }
}
```

In `failAfterInsert()`, the SQL succeeds, but the code intentionally throws an unchecked exception. When the exception exits the method, the **nested interceptor** applies the default rollback rule and rolls back to this scope's savepoint.

In `succeed()`, no exception is thrown so the scope succeeds, yet T is not committed.

In `failAfterDeepChildSuccess()`, Spring creates savepoint **S_PARENT** before `insert(5)`; the call `deep.succeed(6, ...)` goes through **another bean's proxy**, so it creates **S_CHILD** after `insert(5)`. The child returns normally, and Spring releases S_CHILD. Immediately afterward, the parent throws an error, and the interceptor rolls back to S_PARENT: both **5 and 6** are discarded. This is the most important "multiple rollback points" behavior.

### 6.8. File `src/main/java/example/savepoint/OuterWorkflowService.java`

```java
package example.savepoint;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterWorkflowService {
    private final JdbcTemplate jdbc;
    private final NestedStepService nested;

    public OuterWorkflowService(
            JdbcTemplate jdbc, NestedStepService nested) {
        this.jdbc = jdbc;
        this.nested = nested;
    }

    private void insert(int id, String name) {
        jdbc.update(
            "INSERT INTO tx_events (id, event_name) VALUES (?, ?)",
            id, name
        );
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void recoverSelectedSteps() {
        insert(1, "outer-before");

        try {
            nested.failAfterInsert(2, "failed-A");
        } catch (IllegalStateException ignored) {
            // Nested interceptor has already rolled back to S1.
        }

        nested.succeed(3, "nested-ok");
        insert(4, "outer-middle");

        try {
            nested.failAfterDeepChildSuccess();
        } catch (IllegalStateException ignored) {
            // Parent nested interceptor has already rolled back to S_PARENT;
            // both operations 5 and 6 are discarded.
        }

        insert(7, "outer-after");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void abortAfterNestedSuccess() {
        insert(10, "outer-start");
        nested.succeed(11, "nested-success");
        throw new IllegalStateException("outer-failed");
    }
}
```

Accurately distinguish two styles of `catch`:

- `recoverSelectedSteps()` catches `IllegalStateException` **after the exception has passed through the nested proxy**, so rolling back to the savepoint has already happened before control returns to the outer catch. The outer continues with T still valid.
- If caught **right inside `NestedStepService.failAfterInsert()`** and the method returns, its interceptor only sees normal completion, so it typically **does not roll back** to the savepoint due to that error. You must let the exception exit across the nested boundary or explicitly call `setRollbackOnly()` in the nested scope.

`abortAfterNestedSuccess()` proves that releasing a savepoint is not a commit: `nested.succeed(11)` succeeds, but the outer's unchecked exception forces a rollback of **T**, erasing both events 10 and 11.

### 6.9. File `src/main/java/example/savepoint/SavepointsApplication.java`

```java
package example.savepoint;

import java.util.List;
import javax.sql.DataSource;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class SavepointsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SavepointsApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        DataSourceTransactionManager manager =
            new DataSourceTransactionManager(dataSource);
        manager.setNestedTransactionAllowed(true);
        return manager;
    }

    private static String snapshot(JdbcTemplate jdbc) {
        List<String> rows = jdbc.query(
            "SELECT id, event_name FROM tx_events ORDER BY id",
            (rs, rowNum) ->
                rs.getInt("id") + ":" + rs.getString("event_name")
        );
        return rows.toString();
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.update("DELETE FROM tx_events");
    }

    @Bean
    ApplicationRunner demonstration(
            OuterWorkflowService outer,
            NestedStepService nested,
            JdbcTemplate jdbc) {
        return args -> {
            reset(jdbc);
            outer.recoverSelectedSteps();
            System.out.println("A rows=" + snapshot(jdbc));

            reset(jdbc);
            try {
                outer.abortAfterNestedSuccess();
            } catch (IllegalStateException ex) {
                System.out.println("B outer error=" + ex.getMessage());
            }
            System.out.println("B rows=" + snapshot(jdbc));

            reset(jdbc);
            nested.succeed(20, "standalone");
            System.out.println("C rows=" + snapshot(jdbc));
        };
    }
}
```

There is a single `PlatformTransactionManager` bean named `transactionManager`; Spring Boot JDBC auto-configuration does not need to select another manager automatically. `DataSourceTransactionManager` uses the JDBC connection managed by Spring, and explicitly sets `nestedTransactionAllowed=true` to make the example's premise clear. With H2, JDBC savepoints are supported.

`ApplicationRunner` calls the **injected Spring beans**, rather than `new OuterWorkflowService(...)` or self-invocation. Each `JdbcTemplate` step uses the transaction-bound connection; therefore, multiple nested logical scopes can all manipulate savepoints inside **a single physical transaction** initiated by the outer service.

### 6.10. How to Run and Expected stdout

From the project root directory containing the Gradle wrapper, run on macOS/Linux:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

If the project does not have a wrapper yet, you can use `gradle bootRun` with an appropriately installed Gradle, or generate the wrapper first. Do not run `javac`/`java` directly without supplying the Spring/H2 classpath.

The stdout printed by the application (excluding Boot/Gradle startup logs) is expected to be:

```text
A rows=[1:outer-before, 3:nested-ok, 4:outer-middle, 7:outer-after]
B outer error=outer-failed
B rows=[]
C rows=[20:standalone]
```

**Why are these lines correct?**

- **A:** id 2 was rolled back to S1. Id 3 belonged to a successful nested scope, so it remained in T. Ids 5 and 6 were rolled back to S_PARENT, even though id 6 belonged to a child savepoint that had succeeded. The outer committed T with ids 1, 3, 4, and 7.
- **B:** id 11 passed through the nested method successfully and its savepoint was released. The outer threw `IllegalStateException`, so rolling back T erased both id 10 and id 11. The caller caught the exception after the outer proxy to print the error; catching it does not reverse the rollback.
- **C:** `nested.succeed(20, ...)` was called with no existing transaction. `NESTED` acted like `REQUIRED`, opening a new transaction and committing it when the method succeeded. Thus id 20 exists.

This is the **expected result based on the code and configuration**, not a claim that Gradle was executed in the current environment. To verify for real, run `bootRun` and the tests in section 8.

## 7. Inspecting Each Savepoint of Case A Exactly

The table below follows the execution order of `recoverSelectedSteps()` within a single T.

| Time | Scope | Action | Events visible *temporarily inside T* | Final outcome of action |
| --- | --- | --- | --- | --- |
| T0 | Outer | Begin T | — | Not committed |
| T1 | Outer | Insert id 1 | 1 | Kept temporarily in T |
| T2 | Nested-A | Create S1, insert id 2 | 1, 2 | Not committed |
| T3 | Nested-A | Exception -> rollback S1 | 1 | 2 discarded |
| T4 | Nested-B | Create S2, insert id 3, release S2 | 1, 3 | 3 remains temporarily in T |
| T5 | Outer | Insert id 4 | 1, 3, 4 | Kept temporarily in T |
| T6 | Nested-Parent | Create S_PARENT, insert id 5 | 1, 3, 4, 5 | Kept temporarily |
| T7 | Nested-Child | Create S_CHILD, insert id 6, release S_CHILD | 1, 3, 4, 5, 6 | 6 is still not committed |
| T8 | Nested-Parent | Exception -> rollback S_PARENT | 1, 3, 4 | 5 and 6 discarded |
| T9 | Outer | Insert id 7 | 1, 3, 4, 7 | Kept temporarily |
| T10 | Outer | Commit T | 1, 3, 4, 7 | **Single physical commit** |

This table does not guarantee that concurrent external transactions see the same event set at T1–T9: isolation levels usually hide uncommitted changes. The column "visible temporarily inside T" only describes state **inside T's connection**, not data readable by other clients.

### Why Is Child Success Not Enough?

Think of S_PARENT as a marker capturing the logical state before running a group of operations, while S_CHILD is a marker placed **after** S_PARENT. Releasing S_CHILD does not turn C into independently committed data; C still sits after S_PARENT. When rolling back to S_PARENT, the DB must undo all changes in that time window, including changes that just passed through a successful child scope.

A helpful mental model:

```text
T--------------------------COMMIT------------------------>
 \-- S_PARENT
      insert 5
      \-- S_CHILD
           insert 6
      /-- release S_CHILD (does not commit)
 /-- ROLLBACK TO S_PARENT (discards both 5 and 6)
```

If the outer later throws an error, events 1, 3, 4, and 7 are also rolled back because T's commit has not completed. Therefore, when business data must be durable independently of the outer, `NESTED` **does not satisfy the requirement**; you must consider `REQUIRES_NEW`, an outbox, or another mechanism according to the invariant.

## 8. JUnit 5 Testing Using Database State

Create `src/test/java/example/savepoint/SavepointsApplicationTest.java`:

```java
package example.savepoint;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class SavepointsApplicationTest {
    @Autowired OuterWorkflowService outer;
    @Autowired NestedStepService nested;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_events");
    }

    private List<String> events() {
        return jdbc.query(
            "SELECT id, event_name FROM tx_events ORDER BY id",
            (rs, rowNum) ->
                rs.getInt("id") + ":" + rs.getString("event_name")
        );
    }

    @Test
    void rollbackToMultipleSavepointsKeepsOnlyValidEvents() {
        outer.recoverSelectedSteps();

        assertEquals(
            List.of(
                "1:outer-before",
                "3:nested-ok",
                "4:outer-middle",
                "7:outer-after"
            ),
            events()
        );
    }

    @Test
    void successfulNestedScopeIsNotAnIndependentCommit() {
        assertThrows(
            IllegalStateException.class,
            outer::abortAfterNestedSuccess
        );
        assertEquals(List.of(), events());
    }

    @Test
    void nestedWithoutExistingTransactionBehavesLikeRequired() {
        nested.succeed(20, "standalone");
        assertEquals(List.of("20:standalone"), events());
    }
}
```

Run:

```bash
./gradlew test
```

**Important testing notes:**

- **Do not put `@Transactional` on the test method or test class**, because a transaction created by the test framework can mask the service's commit/rollback results.
- `@SpringBootTest` boots the context and may run `ApplicationRunner`; `@BeforeEach` clears events before each test to ensure proper baseline data.
- Assertions read data **after the service proxy has completed**, rather than reading mid-transaction and inferring a commit.
- If multiple tests run in parallel against the same H2 database and table, `DELETE` calls can race. Use separate databases/schemas or run tests sequentially when sharing fixtures.
- Test A is a strong check: it must keep 1, 3, 4, 7 while excluding 2, 5, 6. If the implementation accidentally used `REQUIRED` for inner, the result could become `UnexpectedRollbackException`; if it used `REQUIRES_NEW`, unexpectedly committed data might appear.

**Simply reading or asserting from annotations is not enough.** Testing DB state is what proves savepoint rollback and outer commit actually occurred according to contract.

## 9. Two Rollback Styles for a Nested Scope

### 9.1. Exception Exiting the Nested Interceptor

```java
@Transactional(propagation = Propagation.NESTED)
public void optionalStep() {
    jdbc.update("INSERT INTO tx_events (id, event_name) " +
                "VALUES (100, 'optional')");
    throw new IllegalStateException("Reject this step");
}
```

If the method is called through a proxy inside outer T and `IllegalStateException` exits, the transaction advice usually rolls back to the savepoint and rethrows the exception. The outer **can** catch the exception after the proxy and continue T:

```java
@Transactional
public void orchestrate() {
    requiredWrite();
    try {
        otherBean.optionalStep();
    } catch (IllegalStateException rejected) {
        recordOptionalStepSkipped(rejected);
    }
}
```

These two snippets assume existing beans, `JdbcTemplate`, business methods, and Spring transaction infrastructure. They are not two standalone Java files. If `recordOptionalStepSkipped` only writes a Java log, it needs no transaction; if it writes to the DB, it uses the still-active T and must be designed to match invariants.

**Key takeaway:** the exception passed through the **inner transaction advice**, so the savepoint was already rolled back before the outer `catch`.

### 9.2. Explicitly Calling `setRollbackOnly()` in the Nested Scope

If the contract requires returning a failure result instead of throwing an exception:

```java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional(propagation = Propagation.NESTED)
public boolean optionalStep() {
    if (shouldSkipThisStep()) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return false;
    }
    performNestedWrites();
    return true;
}
```

When `NESTED` has its own savepoint and the transaction manager supports it, local rollback-only on the **inner status** causes Spring to roll back to the savepoint when the scope ends; the outer can continue. This differs from a participating `REQUIRED` scope, where rollback-only can be propagated to the shared transaction T, preventing T from committing.

Distinguish clearly:

- **Inner `NESTED` status local rollback-only:** expected to roll back to the inner savepoint.
- **Outer status local rollback-only:** outer requests rolling back the entire T.
- **Transaction already global rollback-only from elsewhere:** creating/rolling back a savepoint does not guarantee T becomes committable again.

Only call `TransactionAspectSupport.currentTransactionStatus()` when code is currently managed by Spring transaction advice; calling it outside that scope can fail. If plain declarative code suffices, letting an appropriate exception exit is usually simpler than depending on this Spring API.

### 9.3. Checked Exceptions May Not Roll Back a Savepoint by Default

Under the common default rollback rules in Spring Framework 6.1, `RuntimeException`/`Error` triggers rollback, whereas a checked exception **does not roll back by default**:

```java
@Transactional(propagation = Propagation.NESTED)
public void step() throws java.io.IOException {
    insertSomething();
    throw new java.io.IOException("Checked failure");
}
```

In this example, without declaring another rollback rule, the nested interceptor may end the scope **without rolling back to the savepoint**, even though the caller receives the checked exception. If business logic requires discarding the nested work:

```java
@Transactional(
    propagation = Propagation.NESTED,
    rollbackFor = java.io.IOException.class
)
public void step() throws java.io.IOException {
    insertSomething();
    throw new java.io.IOException("Checked failure");
}
```

Both blocks are illustrative snippets without a declared `insertSomething()` helper. Depending on the Spring version/configuration, default rollback rules can be customized. Always check actual settings, especially when upgrading the framework.

## 10. Programmatic API: Multiple Savepoints with `SavepointManager`

`@Transactional(NESTED)` is the declarative approach. When multiple rollback points are needed **within a single method**, Spring provides the `SavepointManager` API via `TransactionStatus`.

Illustrative code pattern:

```java
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.TransactionStatus;

@Transactional
public void importBatch() {
    TransactionStatus status =
        TransactionAspectSupport.currentTransactionStatus();

    insertRequiredHeader();

    Object pointA = status.createSavepoint();
    try {
        importOptionalSegmentA();
    } catch (RecoverableImportException failure) {
        status.rollbackToSavepoint(pointA);
    } finally {
        status.releaseSavepoint(pointA);
    }

    Object pointB = status.createSavepoint();
    try {
        importOptionalSegmentB();
    } catch (RecoverableImportException failure) {
        status.rollbackToSavepoint(pointB);
    } finally {
        status.releaseSavepoint(pointB);
    }

    insertRequiredFooter();
}
```

**This is a design-level API example**, not a standalone runnable Java class: the helpers and `RecoverableImportException` are domain types you must define yourself. With a JDBC transaction supporting savepoints, the method corresponds conceptually to: start T, mark point A, optionally revert to A, mark point B, optionally revert to B, then let the outer transaction decide the commit.

Notes:

- `TransactionStatus` implements the `SavepointManager` interface, but not **every manager/status** supports creating savepoints. Do not use it on arbitrary JTA/JPA managers and assume it works.
- If an operation can cause a DB error that puts the transaction into an aborted state, you must understand whether the DBMS allows recovery via savepoint.
- Catching exceptions and rolling back manually is a strict design choice: ensure partial success is transparently reported to the caller.
- Do not call `status.setRollbackOnly()` on the **outer status** just to discard segment A; that requests rolling back the **entire T**.
- In multi-layered Spring service code, `@Transactional(NESTED)` across clearly separated beans is usually easier to test and read than manually creating/releasing many savepoints inside one method.

### Using `TransactionTemplate` When You Do Not Want to Rely on AOP Proxies

You can establish the physical transaction with `TransactionTemplate`, then use the status to create a savepoint:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);

template.execute(status -> {
    insertRequiredHeader();

    Object savepoint = status.createSavepoint();
    try {
        writeOptionalDetails();
    } catch (RuntimeException rejected) {
        status.rollbackToSavepoint(savepoint);
    } finally {
        status.releaseSavepoint(savepoint);
    }

    insertRequiredFooter();
    return null;
});
```

This snippet assumes an existing `transactionManager` bean and real helpers, not a standalone program. The idea is to create **one physical transaction T** and work directly with savepoints inside T; if the callback ends normally, the template attempts to commit, and unhandled exceptions roll back according to implemented rules. Do not mix `TransactionTemplate`/savepoints with `@Transactional` arbitrarily without understanding active transaction propagation.

## 11. Limitations and Common Misunderstandings

### 11.1. Nested Success Is Not "Durable" Against Outer Rollback

```java
@Transactional
public void outer() {
    nestedBean.stepSuccess(); // @Transactional(NESTED)
    throw new IllegalStateException("Fail outer");
}
```

The nested step only releases its savepoint. When the outer proxy receives the unchecked exception, **rolling back T** still discards all SQL executed by the nested step. If an audit or payment must persist independently, that requirement has different semantics than `NESTED`.

### 11.2. Nested Failure Does Not Automatically Roll Back All of T

```java
@Transactional
public void outer() {
    writeRequiredPart();
    try {
        nestedBean.optionalStep();  // NESTED, runtime failure
    } catch (OptionalFailure ex) {
        // Accept skipping the optional step.
    }
    writeRequiredCompletion();
}
```

If it truly is `NESTED` with a savepoint, the error exited the nested interceptor, the outer accepts partial recovery, and the DB remains committable, the outer **can commit** the two required steps. If the business invariant does not allow losing the optional step, you should not catch and continue.

### 11.3. Catching Inside the Nested Method Can Prevent Savepoint Rollback

```java
@Transactional(propagation = Propagation.NESTED)
public void optionalStep() {
    insertOptionalData();
    try {
        validateOptionalData();
    } catch (IllegalArgumentException ignored) {
        // Interceptor does not see the exception.
    }
}
```

If `validateOptionalData()` only throws an application error while the nested method returns normally, the transaction advice may release the savepoint and retain the INSERT in T. Use exception propagation or mark rollback-only **on the nested status** when you want to discard the entire scope's work.

### 11.4. Self-Invocation Does Not Create a New Scope

```java
@Service
public class WrongWorkflow {
    @Transactional
    public void outer() {
        inner();  // this.inner(), bypasses proxy
    }

    @Transactional(propagation = Propagation.NESTED)
    public void inner() {
        // No separate nested interceptor on self-invocation.
    }
}
```

In default proxy mode, the annotation on `inner()` is not applied to calls through `this`. Extract it to another bean to get a real interceptor boundary, or choose a programmatic transaction API if the logic must stay in the same class. Switching from JDK proxy to CGLIB **does not automatically fix** self-invocation.

### 11.5. `final`, `private`, and Non-Spring Beans

`@Transactional` is typically enforced via proxies: private or final methods cannot be advised by subclass proxy overriding; likewise, objects instantiated with `new` outside the Spring container have no transaction proxy. With interface proxies, the method must be public and declared on the proxied interface. You cannot conclude an annotation will open a nested scope if the call never passed through Spring transaction advice.

### 11.6. Isolation and Locks Are Not "Globally Reset"

A savepoint does not create a separate transaction with independent isolation. When `NESTED` joins T, **T still uses the outer's isolation/connection**. Depending on the DBMS, rolling back to a savepoint may release some locks acquired after the savepoint, but many other locks/resources follow their own rules. Never promise that all locks acquired after the marker are released on every DB.

The outer transaction may still hold locks, the connection, and transaction state until the final commit, even after multiple nested rollbacks. Adding numerous savepoints does not automatically make a transaction shorter or increase throughput.

### 11.7. DDL and Non-DB Side Effects

Some DBMSs have DDL statements that trigger an implicit commit or have different savepoint semantics than ordinary DML; do not assume every schema operation can be rolled back via a savepoint. Similarly, sending emails, making HTTP calls, publishing events to systems outside the transaction manager, or writing files **are not automatically undone** when rolling back a JDBC savepoint. You must design an outbox, idempotency, or compensation when those side effects are mandatory parts of the business flow.

### 11.8. How Does Rolling Back to an Older Savepoint Affect Newer Savepoints?

In many DBMSs, rolling back to an older savepoint can **invalidate savepoints created after it**; changes after that marker are also discarded. Spring manages the order of nested scopes and corresponding savepoints. With the manual API, developers must explicitly manage the create/rollback/release lifecycle; do not hold onto a child savepoint reference and reuse it after the transaction has rolled back to a parent marker, committed, or ended.

## 12. Why Does JPA/Hibernate Require Extra Caution?

The JDBC/H2 example above uses `JdbcTemplate`, so connection and database state are straightforward. With JPA:

- `JpaTransactionManager` **disables** nested transactions by default (`nestedTransactionAllowed=false`).
- Allowing JDBC savepoints within a JPA transaction **does not mean** rolling back the state of the `EntityManager`/first-level cache, managed entities, or pending flushes.
- An entity already modified in the persistence context may not automatically revert to its DB value after a JDBC `ROLLBACK TO SAVEPOINT`, leading to unpredictable behavior if you keep using the EntityManager normally.
- JPA does not generally provide a nested transaction model via JDBC savepoints. Do not flip the flag and treat `@Transactional(NESTED)` on a JPA repository as having the same semantics as `JdbcTemplate`.

If the architecture uses Spring Data JPA, verify the specific manager/driver/persistence context and consider **redesigning transaction boundaries** or handling recovery through a separate business step. Never silently apply this JDBC code to JPA and promise the same outcome.

## 13. Debugging Multiple Savepoints and Nested Transaction Issues

If you encounter `UnexpectedRollbackException`, `NestedTransactionNotSupportedException`, or unexpected final data, follow this sequence:

1. Confirm that an **outer physical transaction T already exists** before the nested method is called.
2. Confirm the inner method uses `Propagation.NESTED`, not the default `REQUIRED`.
3. Check whether the inner method **goes through a proxy** and is a real Spring bean; do not call `this.inner()`.
4. Check which `PlatformTransactionManager` is running: `DataSourceTransactionManager`/`JdbcTransactionManager` or another JPA/JTA manager?
5. Verify the driver/database supports savepoints and nested transactions are allowed by the manager.
6. Inspect transaction logs to see which savepoints were created, released, and rolled back to. If there are no signs of a nested transaction, recheck interception and propagation.
7. Verify the exception **exits through the nested interceptor** and matches rollback rules; if caught inside the nested method, the savepoint may be released.
8. If the outer catches the error, confirm whether **transaction T is still committable** or was already marked rollback-only by another scope/SQL error.
9. Read the DB **after the outer proxy has committed/rolled back**, not just by looking at affected row counts mid-transaction.
10. When savepoints are nested, check whether a parent rollback also discarded changes from an already-completed child.

You can temporarily add logging configuration:

```yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.jdbc.datasource.DataSourceTransactionManager: DEBUG
```

This is an optional addition to `application.yml`, not required to run the demo. TRACE log level can produce heavy log volume, so only enable it in debug environments and avoid logging sensitive data.

### Common Issues

| Symptom | Possible Cause | Fix |
| --- | --- | --- |
| Inner `NESTED` failure rolls back the entire outer | Inner actually ran `REQUIRED`, DB/resource became global rollback-only, or outer rethrows error | Verify savepoint, proxy, manager, and T's state |
| `NestedTransactionNotSupportedException` | Manager does not allow/support nested transactions | Use an appropriate manager; check driver; do not force semantics |
| Inner succeeds but outer rollback loses inner data | NESTED has no separate commit | This is expected behavior; only an independent transaction has different semantics |
| Child nested succeeds but parent nested rollback loses child | Parent savepoint was created before child | Rolling back to parent marker erases all subsequent changes |
| Error caught yet nested still keeps data | Exception caught inside nested, interceptor saw normal return | Let error propagate out or mark local rollback-only |
| `@Transactional(NESTED)` has no effect | Called via `this`, `new`, or non-advised method | Extract a service bean and call through proxy |
| JPA entity state mismatches after savepoint | JDBC rollback does not sync persistence context | Do not apply JDBC savepoint semantics directly to JPA |
| Using `REQUIRES_NEW` partially commits despite outer rollback | Inner has a separate physical transaction | Redesign around business invariant; do not swap propagation arbitrarily |
| SQL error occurs, savepoint rollback cannot recover | DBMS/driver semantics or connection failure | Check specific DBMS; roll back all of T when needed |
| Data visible mid-T, absent after commit | Uncommitted data or rolled back to savepoint/outer | Assert after the transaction boundary completes |
| Creating too many savepoints prolongs transaction | Savepoints do not shorten T's duration | Shrink scope/keep transactions short; watch pool and locks |
| Email/API call is not undone | Outside the JDBC transaction | Use outbox/idempotency/compensation |

## 14. When Should You Use vs. Avoid `NESTED`?

### Suitable

- An outermost operation must atomically commit **accepted steps**, while certain sub-steps **are allowed to be dropped** when validation fails.
- Sub-operations all use the **same JDBC datasource/connection**; savepoints can roll back the exact scope.
- Sub-scopes have clear boundaries through Spring proxies and integration tests proving data correctness.
- Multiple rollback points are needed **without needing** an inner independent commit before the outer commits.

### Unsuitable or Requires Careful Thought

- Inner transaction **must** commit even if the outer fails: `NESTED` cannot satisfy this.
- System spans **multiple datasources** and needs global atomicity: single-connection savepoints do not coordinate across resources.
- Core logic cannot allow partial success: using `NESTED` + catching errors can violate business rules even if the technical transaction commits cleanly.
- Primarily manipulates JPA managed entities, or the database/driver lacks savepoint support with the needed semantics.
- Sub-step causes side effects outside the DB (email, HTTP, message broker): JDBC savepoints do not undo those side effects.

A design question more important than "is `NESTED` supported?" is: **When a sub-step fails, does the business genuinely allow discarding just that step while still committing the remaining steps?** If the answer is "no," let all of T roll back instead of mechanically wrapping steps in savepoints.

## 15. Practice Exercises

### Exercise 1: Predict State After Multiple Savepoints

Consider the flow:

```text
BEGIN T
  insert A
  SAVEPOINT S1
    insert B
    SAVEPOINT S2
      insert C
    RELEASE S2
    insert D
  ROLLBACK TO S1
  insert E
COMMIT T
```

**Answer:** A and E remain; B, C, and D are lost. Releasing S2 does not commit C, and rolling back to S1 erases all changes after S1. There is exactly **one physical commit**.

### Exercise 2: Outer Changes to Rollback

If `COMMIT T` in Exercise 1 is replaced with `ROLLBACK T`, which inserts remain? **No inserts are committed from T**, including A before S1 and E after rolling back S1.

### Exercise 3: Checked Exception

A `@Transactional(NESTED)` method writes a record and throws `IOException`. The outer catches it and commits; by default in Spring 6.1, does it roll back to the savepoint? **Not automatically** if the exception does not match rollback rules. To roll back just the inner scope, declare `rollbackFor = IOException.class`.

### Exercise 4: Self-Invocation

`outer()` and `inner()` are in the same bean; `outer()` calls `inner()` directly in Spring proxy mode. Is a savepoint automatically created for `inner()`? **No**, if the call bypasses the proxy. Another bean or a programmatic transaction API is required.

### Exercise 5: Choosing Propagation

You want to write an independent audit log even if the outer order rolls back. Is `NESTED` enough? **No**. You need an appropriate strategy for independent auditing, possibly `REQUIRES_NEW` with connection/atomicity caveats, or an outbox depending on consistency requirements.

## 16. Practical Implementation Checklist

1. Document the **outermost** transaction and which sub-scopes are allowed partial rollback.
2. Confirm the same `DataSource`, the right `PlatformTransactionManager`, and driver support for `Savepoint`.
3. Use `@Transactional(propagation = NESTED)` on public methods invoked through a **Spring bean proxy**.
4. Remember that `NESTED` without an outer T creates a new T just like `REQUIRED`.
5. Define which exceptions roll back to the savepoint; for checked exceptions, configure explicit rules if defaults are unsuitable.
6. Catch errors **after the nested interceptor** in the outer if continuing; do not swallow errors inside nested expecting automatic rollback.
7. If a nested parent rolls back, all nested child changes **after the parent marker** also roll back, even if the child succeeded.
8. Do not treat `releaseSavepoint` as a commit. Changes are only durable if the outer physical T commits.
9. Do not treat savepoints as a tool to restore non-database side effects or JPA persistence context state.
10. Test against the database after the proxy method finishes: inner fail, inner success, parent nested fail, outer fail, standalone nested.
11. When encountering unexpected rollback errors, check for participating `REQUIRED` scopes, global rollback-only, or DB errors outside the nested scope.
12. Keep T short, manage locks/connections carefully, and prioritize business invariants over the convenience of a propagation setting.

## References

- Spring Framework — **Transaction Propagation** (`REQUIRED`, `REQUIRES_NEW`, `NESTED`): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — **Declarative Transaction Management**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — **Rolling Back a Declarative Transaction**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework Javadoc — **`DataSourceTransactionManager`**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework Javadoc — **`Propagation.NESTED`**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Propagation.html
- Spring Framework Javadoc — **`SavepointManager`**: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/SavepointManager.html
- Spring Framework Javadoc — **`JpaTransactionManager`** (JPA persistence context caveat): https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html