# Rolling Back a Nested Scope to a Savepoint with Spring PROPAGATION_NESTED

## 1. Essence of the Problem: Undoing a Part While Keeping the Outer Transaction

In a large business flow, sometimes one step **may fail without forcing the entire operation to abort**. For example: creating a warehouse receipt and writing the main log entry are mandatory, whereas applying an optional promotion might fail; the application wants to undo the SQL changes of the promotion step and continue saving the receipt.

With Spring transaction management, `Propagation.NESTED` can address this use case using a **JDBC savepoint**: a marker inside the **same physical transaction**. If the nested scope fails and matches a rollback rule, Spring rolls back the work from that savepoint onward, while the outer transaction's work before the savepoint remains intact and can continue.

Keep four core points in mind:

1. **NESTED does not open an independent physical transaction** when a compatible outer transaction already exists. It uses one physical transaction and one (or more) savepoints.
2. **Rollback of the nested scope** is typically `ROLLBACK TO SAVEPOINT`, not a `ROLLBACK` of the entire transaction.
3. **Commit of the nested scope** does not make data durable on its own: the child's results only become final if the outer transaction actually commits.
4. **The outer transaction still retains the power to cancel everything**. If the outer rolls back after the child ran successfully, changes both before and inside the nested scope are discarded.

Lesson goals:

- Explain the sequence of creating a savepoint, executing SQL, rolling back to the savepoint, continuing, and committing.
- Properly write two Spring-managed services so `@Transactional(propagation = Propagation.NESTED)` is activated via proxy.
- Observe that **rows before the savepoint are kept**, **rows after the savepoint are discarded**, and **the outer transaction can still commit**.
- Distinguish it from `REQUIRED` (which easily leads to global rollback-only when the child fails) and `REQUIRES_NEW` (an independent physical transaction).
- Understand JDBC/JPA support limits, exception rules, error catching, and side effects that savepoints cannot undo.

> This lesson focuses on *rolling back a nested scope to a savepoint*; do not view savepoints as a substitute for data consistency logic, exception design, or transaction boundaries.

## 2. One Physical Transaction, Multiple Rollback Markers

Visualize the sequence:

```text
Begin physical transaction T
|
+-- Outer: INSERT A                (pending commit)
|
+-- Create SAVEPOINT S1
|      |
|      +-- Inner: INSERT B         (pending commit)
|      +-- Inner: error occurs
|      +-- ROLLBACK TO SAVEPOINT S1
|             -> removes SQL effects of B after marker S1
|
+-- Outer intentionally catches error
+-- Outer: INSERT C
|
+-- COMMIT T
       -> A and C exist; B does not exist
```

**A savepoint is not a mini-commit.** When creating a savepoint, the database does not permanently confirm the part before the marker; A still belongs to transaction T and can be rolled back if T fails. `ROLLBACK TO SAVEPOINT S1` merely returns transaction state to the point of S1 without closing T.

Similarly, if the inner succeeds and Spring releases the savepoint, INSERT B has still not committed independently. An error in the outer before `COMMIT T` can cause A, B, and every other SQL statement in T to roll back together.

### Distinguishing the SQL Commands

Example in **PostgreSQL** syntax (assuming table `events(id, message)` already exists and lacks the IDs below):

```sql
BEGIN;

INSERT INTO events(id, message) VALUES (1, 'outer-before');

SAVEPOINT optional_step;
INSERT INTO events(id, message) VALUES (2, 'inner-to-undo');

ROLLBACK TO SAVEPOINT optional_step;
RELEASE SAVEPOINT optional_step;

INSERT INTO events(id, message) VALUES (3, 'outer-after');

COMMIT;
```

After committing, querying:

```sql
SELECT id, message FROM events ORDER BY id;
```

returns rows with IDs **1 and 3**, without ID 2.

| SQL | Effect |
| --- | --- |
| `BEGIN` | Opens a physical transaction |
| `SAVEPOINT optional_step` | Marks a position to which you can return |
| `ROLLBACK TO SAVEPOINT optional_step` | Undoes SQL changes since that marker within the same transaction |
| `RELEASE SAVEPOINT optional_step` | Releases the marker; not a commit |
| `COMMIT` | Confirms all remaining changes in the transaction |
| `ROLLBACK` | Discards the entire physical transaction, including changes before the savepoint |

In PostgreSQL, `ROLLBACK TO SAVEPOINT` does not automatically destroy the named savepoint; `RELEASE SAVEPOINT` can be used when it is no longer needed. Marker creation/removal, limits, and recovery details depend on the DB/driver; with Spring, usually let the transaction manager perform savepoint operations instead of manually mixing in raw `SAVEPOINT` SQL.

## 3. How Does Spring Perform a Nested Rollback?

For a JDBC transaction manager that supports nested transactions:

```java
@Transactional
public void outer() {
    // SQL A
    nestedService.doOptionalWork();
    // SQL C
}

@Transactional(propagation = Propagation.NESTED)
public void doOptionalWork() {
    // SQL B
    throw new IllegalStateException("optional work failed");
}
```

This is **illustrative** code, not a standalone program: it requires imports, a JDBC implementation, and calling `nestedService` through a Spring-managed proxy.

Exact sequence when `outer()` is called via proxy:

1. Spring opens transaction T for the outer with the default `Propagation.REQUIRED`.
2. Outer executes SQL A inside T.
3. The proxied call into inner with `NESTED` finds T already exists.
4. With a savepoint-capable JDBC manager, Spring creates savepoint S1 on T's connection **before running the inner body**.
5. Inner executes SQL B and throws `IllegalStateException`. A runtime exception triggers rollback by default.
6. The inner's transaction interceptor requests rolling back the **nested scope**; Spring rolls back to S1, usually releases the marker, and rethrows the exception to outer.
7. **If the outer catches the exception and decides to continue**, it can execute SQL C.
8. When outer completes normally, Spring attempts to commit T; if commit succeeds, A and C exist and B is discarded.

Important point: **the outer must handle the error at the right place** to proceed. If the exception from inner escapes the outer method as well, the outer's default rollback rule treats it as a failure of the **outer transaction**, so all of T typically rolls back. Marking `NESTED` does not mean every error only affects the nested scope regardless of exception flow.

### What Changes When There Is No Outer Transaction?

`Propagation.NESTED` does not by default create an empty savepoint waiting for another transaction. With `DataSourceTransactionManager`/`JdbcTransactionManager`, if the call finds no existing transaction, it acts to **start a new transaction**, just like `REQUIRED` with no outer. In that case, failure is not a "partial rollback"; the new transaction itself rolls back all work of the call.

Therefore, to prove true **partial rollback**, a test must have an active outer transaction and the call into nested must go through a transaction proxy.

## 4. Scope of Nested Rollback: What Stays, What Goes?

Assume a DB transaction T with savepoint S1:

| Operation | State after rolling back to S1 | After outer commits successfully |
| --- | --- | --- |
| INSERT A executed **before** S1 | Kept in T | A exists |
| INSERT B executed **after** S1 | Undone | B does not exist |
| UPDATE on a pre-S1 row executed **after** S1 | Post-S1 UPDATE is undone | Value returns to its state at S1 |
| INSERT C executed **after rolling back to S1** | Kept in T | C exists |
| Inner runs successfully then outer rolls back entirely | Inner cannot be saved | All changes in T are discarded |
| Email/API call executed after S1 | Not rolled back by JDBC savepoint | External side effects outside DB may have already happened |

Rolling back to a savepoint rolls back **database changes within the transaction and database-controlled resources since that marker**, not "only undoing a single Java method" via method identity tracking. If other SQL statements used the **same transaction/connection** while the nested scope was open, they may also fall into the undone portion.

For example, if the inner modifies the same row that the outer already modified earlier, rolling back to S1 can preserve the outer's pre-S1 update and discard only the inner's additional update. That is why savepoints are useful for optional steps while requiring a precise understanding of when the marker is created.

**Does not revert Java memory:** objects whose fields were mutated in RAM, counters, application caches, or JPA entities may still hold old/stale state after a JDBC rollback. You must resynchronize proactively and avoid relying on savepoints as a "JVM rewind."

## 5. Comparing NESTED with REQUIRED and REQUIRES_NEW

Suppose outer already has transaction T; inner throws an unchecked exception, and outer catches it to try continuing:

| Characteristic | Inner `REQUIRED` | Inner `NESTED` | Inner `REQUIRES_NEW` |
| --- | --- | --- | --- |
| Physical transaction | Shares T | Shares T | New transaction T2; T is usually suspended |
| Dedicated savepoint | Not per this propagation | Usually yes on JDBC | Not needed to isolate T2 |
| Inner fails, interceptor rolls back | Usually marks T rollback-only | Rolls back to T's savepoint | Rolls back T2 |
| Outer catches and tries to commit | May get `UnexpectedRollbackException` and T rolls back | **Can** commit the rest of T | **Can** commit T independently of T2 |
| Inner succeeds then outer rolls back | Inner changes discarded with T | Inner changes discarded with T | Committed changes of T2 can **still persist** |
| Connection/resource | Same transaction resource | Same JDBC connection transaction | Usually needs an independent connection/transaction resource |
| When to use | One business operation must be atomic overall | An optional step needs to be undoable individually **yet still depend on outer commit** | Need inner commit/rollback outcome **independently** |

The statement "outer can commit" is always conditional: not already marked rollback-only for another reason, the database still allows continuing and committing, and the outer has no remaining error requiring full rollback.

`NESTED` is **not** another way of writing `REQUIRES_NEW`:

- NESTED rolls back B, yet if outer eventually rolls back, A/C and all remaining child changes in T also roll back.
- REQUIRES_NEW can commit T2 before T rolls back, making it suitable for certain independent audits, but it does **not** guarantee shared atomicity; overusing it can increase connection pool demand and resource deadlock risk.
- REQUIRED joins the same T without creating a marker for the sub-part. If inner fails and the interceptor decides to roll back, the shared transaction is usually marked rollback-only; outer catching the exception does not guarantee it can commit.

Choose propagation based on **atomicity** requirements rather than a desire to "make errors disappear."

## 6. Conditions for `PROPAGATION_NESTED` to Work Properly

### 6.1. Transaction Manager and JDBC Driver Must Support Savepoints

In imperative Spring Framework:

- `DataSourceTransactionManager` and its subclass `JdbcTransactionManager` support JDBC savepoints. The `nestedTransactionAllowed` property defaults to **true** on `DataSourceTransactionManager`, though the driver/database must also actually support savepoints.
- `AbstractPlatformTransactionManager` has the `setNestedTransactionAllowed(boolean)` setting. The base class does not guarantee nested support for every manager; concrete managers decide.
- When nested is unsupported or a savepoint cannot be created, the system may throw `NestedTransactionNotSupportedException` or a corresponding transaction exception; **do not assume Spring automatically substitutes REQUIRES_NEW for NESTED**.
- `JpaTransactionManager` **disables nested transactions by default**. There are cases where savepoints are allowed for JDBC access inside a JPA transaction, yet a savepoint does not synchronize the entire **JPA EntityManager/persistence context**. Do not treat toggling a flag as full NESTED support for all entity operations.
- JTA/distributed/reactive managers have different models; do not assume JDBC savepoint conclusions apply.

If using only Spring JDBC + a single DataSource, verify the driver via metadata:

```java
try (var connection = dataSource.getConnection()) {
    boolean supported = connection.getMetaData().supportsSavepoints();
    System.out.println("Savepoints supported: " + supported);
}
```

This snippet is **illustrative outside a transaction**; it requires a `dataSource` variable of type `javax.sql.DataSource` and appropriate Exception/JDBC imports. Metadata support is a necessary condition, not proof that Spring proxy/manager configuration is right. Inside a transactional method, do not manually acquire a new connection via `dataSource.getConnection()` to manipulate savepoints on a different connection; let Spring manage the current connection.

### 6.2. Must Go Through a Spring AOP Proxy

Incorrect example in standard proxy mode:

```java
@Service
public class SameBeanService {

    @Transactional
    public void outer() {
        inner(); // Internal call via this, does not trigger inner's advice.
    }

    @Transactional(propagation = Propagation.NESTED)
    public void inner() {
        // No savepoint is automatically created during this self-invocation.
    }
}
```

**This is illustrative code.** In standard Spring proxy mode, calling `outer()` from outside through the proxy opens T, but `this.inner()` does not go through the interceptor, so **no nested savepoint is created** per the inner's annotation. The clear approach is splitting into `OuterService` and `InnerService`, injecting the other bean, and calling through the Spring-managed proxy.

If you instantiate the service with `new` outside the Spring container, or the method is not matched by the transaction advisor, the annotation does not manage connections automatically.

### 6.3. Exception Rules Still Determine Rollback

When a nested method throws a `RuntimeException`/`Error` out of the proxy, Spring requests rolling back the nested scope by default. For checked exceptions, traditional Spring transaction defaults **do not automatically roll back** unless an appropriate `rollbackFor` is declared.

Example:

```java
@Transactional(
    propagation = Propagation.NESTED,
    rollbackFor = OptionalStepException.class
)
public void performOptionalStep() throws OptionalStepException {
    // SQL inside nested scope
    throw new OptionalStepException("Cannot apply optional step");
}
```

The illustrative snippet above assumes `OptionalStepException extends Exception` and the other components exist. Without `rollbackFor`, a checked exception can cause the inner scope to **complete under Spring's commit decision**, releasing the savepoint without undoing SQL B; if outer catches the exception and commits, B can still be saved. Therefore, you cannot say "any exception exiting NESTED automatically rolls back to the savepoint."

Furthermore, if the exception is **caught and swallowed inside the nested method body**, the interceptor sees the method return normally; the savepoint is typically released rather than rolled back unless code explicitly marks the nested status for rollback or another transaction error occurs.

## 7. Runnable Spring Boot Example: Roll Back Child, Keep Outer Transaction

The example set below uses **Java 17, Spring Boot 3.3.13, Spring JDBC, and in-memory H2**, one JDBC transaction manager, and no JPA. The versions are pinned for reproducibility, not claimed to be the latest. You can use a project generated with Spring Initializr with the Gradle Wrapper.

### 7.1. Project Structure and Dependencies

```text
nested-savepoint-lab/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat
└── src/main/
    ├── java/demo/savepoint/
    │   ├── SavepointApplication.java
    │   ├── TransactionConfig.java
    │   ├── InnerService.java
    │   └── OuterService.java
    └── resources/
        └── application.yml
```

**`settings.gradle`**

```groovy
rootProject.name = 'nested-savepoint-lab'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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

The Spring JDBC starter provides `JdbcTemplate` and transaction infrastructure. Spring Boot provides a DataSource from the JDBC URL configuration, typically using the HikariCP connection pool. `spring-boot-starter-web` is not needed just to verify transactions.

**`src/main/resources/application.yml`**

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:nesteddemo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
```

The in-memory H2 database only holds data within the current JVM, not a persistent database. On each new process run, the demo table is created fresh. `DB_CLOSE_DELAY=-1` keeps the DB alive until the JVM shuts down.

### 7.2. Creating a Manager with Savepoint Support

**`src/main/java/demo/savepoint/TransactionConfig.java`**

```java
package demo.savepoint;

import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement
public class TransactionConfig {

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);
        manager.setNestedTransactionAllowed(true);
        return manager;
    }
}
```

`JdbcTransactionManager` is the JDBC-focused manager extending `DataSourceTransactionManager` and supporting JDBC savepoints. On this manager type, `nestedTransactionAllowed` already defaults to **true**; calling the setter here makes the assumption explicit and enables unambiguous configuration checks. The custom transaction manager is registered under the bean name `transactionManager`; Spring Boot JDBC auto-configuration normally avoids creating another manager when a matching bean already exists.

Spring Boot typically enables transaction annotation support automatically when suitable infrastructure is present; `@EnableTransactionManagement` is declared explicitly in the example so readers do not have to guess from auto-configuration. This is the **single** manager bean in the project.

### 7.3. InnerService: One Failing Method and One Succeeding Method

**`src/main/java/demo/savepoint/InnerService.java`**

```java
package demo.savepoint;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public void writeThenFail() {
        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            2L, "inner-to-undo"
        );
        throw new IllegalStateException("nested failed");
    }

    @Transactional(propagation = Propagation.NESTED)
    public void writeSuccessfully() {
        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            5L, "inner-success"
        );
    }
}
```

`writeThenFail()` inserts ID 2 and then throws an unchecked exception. Choosing the case "**SQL succeeded, then business logic detected an error**" proves that rollback actually undoes the change; it does not rely on an INSERT that already failed and never wrote data.

`writeSuccessfully()` creates a nested scope with a savepoint and completes normally. It proves that **inner success is not an independent commit**: if the outer later fails, ID 5 still cannot survive.

### 7.4. OuterService: Catching Errors to Continue and Testing Global Rollback

**`src/main/java/demo/savepoint/OuterService.java`**

```java
package demo.savepoint;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final InnerService inner;
    private final JdbcTemplate jdbc;

    public OuterService(InnerService inner, JdbcTemplate jdbc) {
        this.inner = inner;
        this.jdbc = jdbc;
    }

    @Transactional
    public void outerContinuesAfterNestedFailure() {
        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            1L, "outer-before"
        );

        try {
            inner.writeThenFail();
        } catch (IllegalStateException ex) {
            System.out.println("Caught nested: " + ex.getMessage());
        }

        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            3L, "outer-after"
        );
    }

    @Transactional
    public void outerFailsAfterNestedSuccess() {
        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            4L, "second-outer"
        );
        inner.writeSuccessfully();
        throw new IllegalStateException("outer failed");
    }
}
```

Notes:

- `OuterService` and `InnerService` are **two separate beans**. Calls to `inner.writeThenFail()` and `inner.writeSuccessfully()` pass through the Spring AOP proxy.
- `outerContinuesAfterNestedFailure` **catches the error after the inner proxy call has finished rolling back to the savepoint**. If an error from inner is not an ignorable business error, you should not swallow exceptions like this.
- `outerFailsAfterNestedSuccess` intentionally throws an unchecked exception **after the inner has completed**. The outer transaction rolls back both ID 4 and ID 5.

### 7.5. Main Program, Queries, and Output

**`src/main/java/demo/savepoint/SavepointApplication.java`**

```java
package demo.savepoint;

import java.util.List;

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
    CommandLineRunner demonstrate(OuterService outer, JdbcTemplate jdbc) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE events ("
                    + "id BIGINT PRIMARY KEY, "
                    + "message VARCHAR(80) NOT NULL)"
            );

            System.out.println("Before: " + rows(jdbc));

            outer.outerContinuesAfterNestedFailure();
            System.out.println("After nested rollback: " + rows(jdbc));

            try {
                outer.outerFailsAfterNestedSuccess();
            } catch (IllegalStateException ex) {
                System.out.println("Caught outer: " + ex.getMessage());
            }
            System.out.println("After outer rollback: " + rows(jdbc));
        };
    }

    private static List<String> rows(JdbcTemplate jdbc) {
        return jdbc.query(
            "SELECT id, message FROM events ORDER BY id",
            (rs, rowNum) ->
                rs.getLong(1) + ":" + rs.getString(2)
        );
    }
}
```

Run in the project directory containing the Gradle Wrapper:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Amid Spring Boot and Gradle logs, five lines printed by the program appear in this exact order:

```text
Before: []
Caught nested: nested failed
After nested rollback: [1:outer-before, 3:outer-after]
Caught outer: outer failed
After outer rollback: [1:outer-before, 3:outer-after]
```

Reading the output:

1. Initially the table is empty: `Before: []`.
2. Outer INSERTs ID 1.
3. Inner creates a savepoint, INSERTs ID 2, and throws `IllegalStateException`. Spring rolls back to the savepoint; outer catches the exception and prints `Caught nested`.
4. Outer INSERTs ID 3 and returns normally; the physical transaction commits. The DB contains IDs **1 and 3**, without ID 2.
5. Second call: outer INSERTs ID 4; nested inner INSERTs ID 5 and completes normally. Then outer throws `IllegalStateException`. Spring rolls back the **entire second transaction**, so neither ID 4 nor 5 exists in the DB. Data committed from the first call remains intact.

**Distinguishing before/after proxy:** The runner has no enclosing transaction and calls `OuterService` methods through the Spring bean. Each `rows(jdbc)` read happens **after the outer proxy has committed or rolled back**. Reading inside outer before commit can show uncommitted data, so do not use that observation as proof that data has been permanently confirmed.

This example set **is a complete Spring Boot project when the files are placed in the proper structure with the Gradle Wrapper and declared dependencies**. The Java files cannot run standalone with `javac` lacking the Spring classpath; the run command is `./gradlew bootRun`.

## 8. Where You Catch the Exception Makes a Difference

### 8.1. Catching in Outer, After the Nested Interceptor Rolls Back

Pattern from the example:

```java
@Transactional
public void outer() {
    writeRequiredPart();

    try {
        nestedService.optionalStep();
    } catch (OptionalOperationException ex) {
        recordFallbackState();
    }

    writeFinalPart();
}
```

This is illustrative code with undeclared helpers. Assume `optionalStep()` is a method on another bean with `@Transactional(propagation = NESTED, rollbackFor = OptionalOperationException.class)`, the exception truly exits through the inner proxy, savepoints are supported, and the transaction remains healthy. When outer catches the exception, the child step has already rolled back, while the outer's work before the savepoint remains in the same physical transaction.

You must decide **which exceptions are recoverable**. Do not `catch (Exception)` and act as if the transaction is definitely safe; some connection/database errors prevent the transaction from continuing. For severe system errors, letting the exception propagate out to roll back everything is usually safer.

### 8.2. Catching Right Inside Inner, Then Returning Normally

```java
@Transactional(propagation = Propagation.NESTED)
public void optionalStep() {
    try {
        jdbc.update("INSERT INTO events ...");
        validateAfterWrite();
    } catch (IllegalStateException ex) {
        // Swallows error and returns; interceptor does not receive exception.
    }
}
```

This illustrative snippet cannot run standalone because the SQL/helpers are abbreviated. Without rollback-only and with the method returning normally, the interceptor usually **releases the savepoint** instead of rolling back. The SQL changes already executed may be committed along with the outer. If you want to undo the child step, it is best to let an exception matching a rollback rule **exit the inner's transaction advice**, then catch it in the outer.

### 8.3. Inner Throws Exception, Outer Does Not Catch

```text
outer transaction T
  |
  +-- create savepoint for inner NESTED
  +-- inner throws RuntimeException
  +-- roll back inner to savepoint
  +-- exception continues exiting outer
  +-- outer interceptor sees RuntimeException
  +-- roll back all of T
```

Part of the work was rolled back to the savepoint, **yet the entire transaction still rolls back afterward** because outer did not handle the error. Therefore, the statement "NESTED always lets outer commit" is false. NESTED creates the *capability* for local recovery; outer business logic still has to decide whether to continue.

### 8.4. Checked Exceptions Must Declare a Rollback Rule

Suppose:

```java
public class OptionalStepException extends Exception {
    public OptionalStepException(String message) {
        super(message);
    }
}
```

When inner declares:

```java
@Transactional(
    propagation = Propagation.NESTED,
    rollbackFor = OptionalStepException.class
)
public void optionalStep() throws OptionalStepException {
    jdbc.update("INSERT INTO events (id, message) VALUES (?, ?)",
                20L, "checked-step");
    throw new OptionalStepException("optional step rejected");
}
```

this is an illustrative class/service fragment using a `jdbc` field in a real bean. `rollbackFor` makes unchecked/checked rollback rules reflect business requirements properly. If **`rollbackFor` is omitted**, Spring by traditional default does not roll back on receiving only a checked exception, even in a NESTED scope; inner may finish by releasing the savepoint and outer still commits the SQL performed.

Also distinguish:

- `noRollbackFor` can prevent a specific exception from triggering child rollback.
- `rollbackForClassName` matches exception name string patterns, risking unintended matches; use `rollbackFor = OptionalStepException.class` when the type is on the classpath.
- If inner is called via self-invocation, neither `NESTED` nor `rollbackFor` on inner is applied by transaction advice in standard proxy mode.
- Projects enabling a non-default global rollback policy must test against their actual policy rather than inferring from default examples.

## 9. Programmatic NESTED with TransactionTemplate

Using annotations is not mandatory. When dynamic transaction boundaries are needed, `TransactionTemplate` offers explicit control. Below is **an illustrative method that can compile inside a class holding the appropriate dependencies**; assume table `events` exists and IDs do not collide:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

public void processWithTemplates(
        PlatformTransactionManager manager,
        JdbcTemplate jdbc) {

    TransactionTemplate outer = new TransactionTemplate(manager);
    TransactionTemplate nested = new TransactionTemplate(manager);
    nested.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_NESTED);

    outer.execute(outerStatus -> {
        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            10L, "outer-10"
        );

        try {
            nested.execute(nestedStatus -> {
                jdbc.update(
                    "INSERT INTO events (id, message) VALUES (?, ?)",
                    11L, "inner-11"
                );
                throw new IllegalStateException("recoverable");
            });
        } catch (IllegalStateException ex) {
            // Nested template has already rolled back to savepoint if supported.
        }

        jdbc.update(
            "INSERT INTO events (id, message) VALUES (?, ?)",
            12L, "outer-12"
        );
        return null;
    });
}
```

Place this method inside a Java class (with imports at the top of the file), with a `PlatformTransactionManager` supporting nested/savepoints and a `JdbcTemplate` using the right DataSource. `TransactionTemplate.execute(...)` manages transaction status and exceptions automatically, so the same manager sees outer already exists and nested creates a savepoint; when an unchecked exception exits the nested callback, it rolls back the child scope before outer catches the exception. If the entire outer transaction commits, the DB has IDs 10 and 12, without 11.

**Advantage:** does not rely on proxies for the nested call between the two callbacks because the transaction boundary is created **directly via the template**. However, it still depends on a manager/driver that supports savepoints; do not create another manager pointing to a different DataSource and expect it to join the same physical transaction.

If you invoke `TransactionTemplate` for outer while using a JPA repository with a different `JpaTransactionManager` inside, you cannot assume the same connection or the same savepoint. Check the actual transaction architecture.

## 10. Manually Creating Savepoints with JDBC / TransactionStatus for Low-Level Control

### 10.1. Plain JDBC API

JDBC provides `java.sql.Savepoint`, `Connection.setSavepoint()`, `rollback(savepoint)`, and `releaseSavepoint(savepoint)`. Plain JDBC example:

```java
import java.sql.Connection;
import java.sql.Savepoint;

public void optionalJdbcWork(Connection connection) throws Exception {
    // Caller must provide a connection already in a transaction,
    // autoCommit=false, and a driver supporting savepoints.

    Savepoint savepoint = connection.setSavepoint();

    try {
        // Execute JDBC Statements on this same connection.
        performJdbcStep(connection);
        connection.releaseSavepoint(savepoint);
    } catch (Exception ex) {
        connection.rollback(savepoint);
        connection.releaseSavepoint(savepoint);
        throw ex;
    }
}
```

This is **illustrative code**; the helper `performJdbcStep` must be supplied. The critical rule is that all SQL belonging to the rollbackable step uses the **same connection that created the savepoint**. After `rollback(savepoint)`, the outer transaction remains open. The caller decides when to commit/roll back the physical transaction. If rolling back to the savepoint itself fails, treat it as a severe resource error rather than blindly continuing to commit.

Do not manually call `connection.commit()` or a full `connection.rollback()` from a DAO while Spring owns the transaction; doing so breaks the boundaries managed by the transaction manager. In Spring applications, using `TransactionTemplate` or `@Transactional(propagation = NESTED)` is usually safer.

### 10.2. Spring's SavepointManager / TransactionStatus

Spring exposes operations on `TransactionStatus` when supported by the transaction manager:

```java
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

// Inside a method managed by a transaction interceptor:
TransactionStatus status =
    TransactionAspectSupport.currentTransactionStatus();

Object savepoint = status.createSavepoint();
try {
    performOptionalDatabaseWork();
    status.releaseSavepoint(savepoint);
} catch (RuntimeException ex) {
    status.rollbackToSavepoint(savepoint);
    status.releaseSavepoint(savepoint);
    // Caller can decide whether to continue or throw an error.
}
```

This is an **illustrative fragment**; `performOptionalDatabaseWork()` must be defined and run on the resource of the right transaction. `currentTransactionStatus()` is only meaningful when actually inside transaction-managed advice. Calling `status.setRollbackOnly()` has different semantics (marking the status to roll back when the scope completes), **not a direct "rollback to savepoint" call**; for hard-to-control code, prefer explicit savepoint APIs or declarative nested transactions as in the main example.

In newer Spring versions, the savepoint API may also support savepoint-related synchronization callbacks; you do not need them for your first hands-on practice. Always check the Spring API version in your project instead of copying snippets from another version.

## 11. Nested Does Not Mean Safe Rollback for Every Resource Type

### 11.1. JDBC vs JPA/Hibernate

`DataSourceTransactionManager`/`JdbcTransactionManager` uses JDBC connections/savepoints and therefore fits direct SQL examples well. Meanwhile, `JpaTransactionManager` defaults to `nestedTransactionAllowed=false` because a JDBC savepoint **cannot restore a JPA persistence context to its pre-savepoint state**.

Entity example:

```java
order.setStatus(OrderStatus.CONFIRMED);
entityManager.flush();
// JDBC rollback to savepoint behind the SQL operations
// does not automatically restore the status field on the Java object.
```

This is an illustrative snippet, not a standalone runnable method. If SQL is rolled back beneath the ORM, managed entities in the persistence context may still reflect state that no longer exists in the DB. Subsequent flushes can cause inconsistencies or errors. **Do not enable nested on JPA and assume Hibernate entities are synchronously "rewound."**

When using Spring Data JPA, consider redesigning boundaries, working in a separate JDBC layer if suitable, or letting the whole operation roll back. Choose the mechanism based on the actual transaction manager and persistence provider capabilities.

### 11.2. Database Errors Can Render a Transaction Unable to Continue

Rolling back to a savepoint usually recovers **SQL changes since the marker**, and in PostgreSQL it can allow continuing after a statement error by rolling back to a savepoint. However, it does not guarantee recovery from every connection error, lost connection, transaction timeout, system failure, or external side effect.

If the connection has been lost or the DB no longer accepts the transaction, trying to continue will produce new errors. Such errors should bubble up so the outer rolls back and alerts. Only catch business exceptions that the service explicitly defines as **optional, recoverable**.

### 11.3. What Savepoints Cannot Rewind

- HTTP requests, sent emails, published Kafka events, written files, or operations on another system not participating in the same DB transaction.
- Mutations to Java variables, static state, caches, and persistence contexts not synchronized with JDBC rollback.
- Certain database-specific non-transactional effects, such as sequence increments (e.g., `nextval` in PostgreSQL), are not guaranteed to be undone on rollback.
- DDL in some databases can trigger an implicit commit or have different semantics; do not infer that all DDL rolls back safely to a savepoint.

If an optional step causes external side effects outside the DB, consider a transactional outbox, after-commit processing, idempotency, or *compensation* rather than expecting JDBC savepoints to handle everything.

### 11.4. Isolation and Locks Do Not Become "Dedicated" to the Nested Scope

Because NESTED shares one physical transaction, it has no independent isolation level like `REQUIRES_NEW`. Savepoints can affect changes and locks acquired after the marker per each DB's rules, yet they do not commit the outer part before the savepoint or release all resources before the outer finishes.

If an inner method declares `@Transactional(propagation=NESTED, isolation=SERIALIZABLE)` inside an outer already opened with `READ_COMMITTED`, do not expect an independent SERIALIZABLE physical transaction. Under strict policies or specific managers, an error may occur or individual requirements may be ignored; verify against your manager/version instead of relying on the name NESTED.

## 12. Common Misconceptions to Fix Immediately

| Misconception | Truth |
| --- | --- |
| "`NESTED` creates a separate transaction" | It usually creates a **JDBC savepoint within the same physical transaction** when outer already exists |
| "Inner NESTED succeeding means it is already committed" | Success usually only releases the savepoint; an outer rollback afterward still discards inner |
| "If inner fails, outer can always commit" | Outer must handle the error and the transaction/database must still be committable; if the exception escapes outer, outer may roll back everything |
| "Catching the exception inside inner already rolled back the child" | The interceptor does not see a swallowed exception; it may release the savepoint instead of rolling back |
| "All checked exceptions in NESTED roll back" | Requires configuring `rollbackFor`/corresponding policy |
| "`REQUIRED` failing then outer catching behaves like NESTED" | REQUIRED can mark the shared transaction rollback-only, causing outer commit to fail |
| "`REQUIRES_NEW` and NESTED are the same" | REQUIRES_NEW is an independent physical transaction; inner commit can survive even if outer rolls back |
| "Adding `@Transactional(NESTED)` in the same class is enough" | Self-invocation in proxy mode usually bypasses the inner's interceptor |
| "`JpaTransactionManager` handles NESTED entities like JDBC by default" | JPA context is not automatically undone by JDBC savepoints; nested is disabled by default |
| "Savepoint rollback undoes emails/APIs/files" | Only handles compatible transactional resources; does not undo external side effects |

## 13. Designing a Suitable Use Case

A valid scenario:

- The outer transaction must save the **order and primary operational state**.
- An optional step writes to a **secondary notes/promotion table**.
- If the secondary step is rejected by a **recoverable business rule**, undo only the secondary step's SQL.
- The outer records an explicit fallback state and continues to commit, without hiding critical system errors.

Example business structure:

```text
outer @Transactional REQUIRED
    |
    +-- INSERT order
    +-- INSERT inventory reservation
    |
    +-- inner @Transactional NESTED
    |      +-- INSERT optional promotion records
    |      +-- validate promotion
    |      +-- if invalid -> rollback to savepoint
    |
    +-- catch OptionalPromotionRejectedException
    +-- UPDATE order SET promotion_status='SKIPPED'
    +-- COMMIT outer
```

Preconditions to turn into tests:

1. If the promotion is invalid, rows/records belonging only to the promotion step **are gone**.
2. The order and inventory reservation before the savepoint are still committed if business rules allow.
3. If the outer detects a mandatory error afterward, **all** DB changes in the outer, including successful nested steps, roll back.
4. For unrecoverable infrastructure errors, the application fails fast instead of catching everything to "try to commit."
5. If JPA/ORM is involved, handle the persistence context issue properly; do not assume JDBC savepoints work for entity changes.

An unsuitable scenario: "Audit logging must persist **even if the outer rolls back**." NESTED **cannot** achieve this requirement because it shares the same physical transaction. You may need `REQUIRES_NEW` if auditing belongs in a suitable independent DB transaction, or an outbox/dedicated audit system with evaluated trade-offs.

## 14. How to Test to Distinguish Propagation Behaviors

An effective test suite should separate scenarios:

| Scenario | Expected Result |
| --- | --- |
| Outer writes A → nested writes B then RuntimeException → outer catches → writes C → outer commits | DB has A/C, no B |
| Outer writes A → nested writes B, returns normally → outer commits | DB has A/B |
| Outer writes A → nested writes B, returns normally → outer rolls back | DB has neither A nor B |
| Outer writes A → nested writes B then fails → outer **does not catch** | Outer also rolls back; DB has neither A nor B |
| Same failure scenario but inner uses `REQUIRED` instead of NESTED | May throw `UnexpectedRollbackException` when outer tries to commit |
| Inner throws checked exception without `rollbackFor`, outer catches and commits | May keep B, since Spring does not roll back child on checked exceptions by default |
| Driver or transaction manager does not support savepoints | Throws unsupported/cannot-create-nested-transaction error; must not assume silent fallback |

**Testing rule:** read data **after the proxied outer method has finished**. A `@Transactional` test wrapping both the call and the query can observe uncommitted data or roll back automatically at the end of the test, hiding the semantics under test.

You can use H2 to learn the Spring lifecycle, then also test on your production DB (PostgreSQL, MySQL InnoDB, ...) to verify real JDBC savepoint, constraint, and error recovery behavior.

### Debugging When You Expected a Savepoint Yet Everything Still Rolled Back

Check in order:

1. Which manager is actually active? `JdbcTransactionManager`, `DataSourceTransactionManager`, or `JpaTransactionManager`?
2. Does the driver/DB report `Connection.getMetaData().supportsSavepoints()`?
3. Did outer have an actual transaction when calling inner?
4. Did the call to inner go through a Spring proxy on a different bean?
5. Was `Propagation.NESTED` declared on the method actually being intercepted?
6. Did the exception exit the inner proxy and match rollback rules?
7. Did outer catch the exception after nested, or let the exception escape outer?
8. Did another error already mark the outer transaction rollback-only or make the DB unable to commit?
9. Are you using the same DataSource/connection? A separate connection outside the transaction is not part of the savepoint.
10. Is a JPA persistence context mixed with JDBC rollback, causing observed state to diverge?

When in doubt, enable selective debug logging for Spring transaction/JDBC in your test environment; inspect when transactions are created, savepoints are created, rollbacks happen, and commits occur. Avoid logging secrets or sensitive data. Clearly separate secondary operations from main business logic to test boundaries independently.

## 15. Self-Check Questions

**1. After inner NESTED succeeds, outer throws `RuntimeException`. Does inner's data remain?**

No, provided all writes belong to the same physical JDBC transaction and outer rolls back successfully. "Inner success" is not a separate commit.

**2. Inner NESTED throws `IllegalStateException`, outer catches it and continues. Why can A stay while B disappears?**

Because Spring rolls back the nested part to the savepoint before returning the exception to outer; changes A before the marker are not locally rolled back. Outer can continue and commit if the transaction remains valid.

**3. If inner NESTED throws a checked `Exception` without `rollbackFor`, is B guaranteed to roll back?**

No. Under traditional default rollback rules, checked exceptions do not trigger rollback automatically. Declare `rollbackFor = YourCheckedException.class` if the goal is child rollback.

**4. Do you need `REQUIRES_NEW` to roll back a child to a savepoint?**

No. `REQUIRES_NEW` creates a separate transaction, whereas `NESTED` uses a savepoint on the same JDBC transaction. The two mechanisms have different semantics when the outer rolls back.

**5. Why does `@Transactional(NESTED)` have no effect when called via `this.inner()`?**

Because in Spring AOP proxy mode, internal calls bypass the inner's transaction interceptor. Split beans or use programmatic `TransactionTemplate` to create a real scope.

**6. With a JPA EntityManager, does a savepoint rollback automatically revert fields on managed entities?**

No. JDBC savepoints and the JPA persistence context manage state through different mechanisms; avoid inferring that JPA fully supports nested transactions.

**7. Does rolling back to a savepoint commit changes made before the savepoint?**

No. It only rolls back the part after the marker, leaving the physical transaction open. Commit must occur at the outer boundary.

## 16. Conclusion

**Rolling back a nested scope to a savepoint** is a key capability of `Propagation.NESTED` in the Spring JDBC ecosystem: one physical transaction can be partitioned into locally recoverable segments. When inner fails and Spring rolls back to the savepoint, outer can intentionally catch the error, continue writing, and eventually commit the remainder. Yet outer remains responsible for the **final outcome**, and an outer rollback undoes all DB changes still belonging to that transaction.

Design formula to remember:

- **Right manager/driver with savepoint support**.
- **Active outer transaction + inner invoked through a Spring proxy**.
- **`NESTED` + appropriate rollback rules**.
- **Catch errors in outer when recovery is genuinely permitted**.
- **Read the DB after outer commit/rollback to verify**.

If inner needs an independent commit, evaluate `REQUIRES_NEW` rather than assigning that job to a savepoint. If using JPA or dealing with external side effects, explicitly design the boundaries and consistency strategy instead of assuming everything automatically reverts to the Java state before the error.

## Official References

- Spring Framework — *Transaction Propagation*, `PROPAGATION_NESTED` section: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — *Declarative Transaction Implementation*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — *Rolling Back a Declarative Transaction*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework 6.1 — `DataSourceTransactionManager` API and nested savepoint support: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — `JdbcTransactionManager`: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html
- Spring Framework — `JpaTransactionManager` and JDBC savepoint/JPA context limitations: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html
- Spring Framework — `TransactionStatus` / savepoint API: https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/transaction/TransactionStatus.html
- PostgreSQL — `SAVEPOINT`: https://www.postgresql.org/docs/current/sql-savepoint.html
- PostgreSQL — `ROLLBACK TO SAVEPOINT`: https://www.postgresql.org/docs/current/sql-rollback-to.html
- PostgreSQL — `RELEASE SAVEPOINT`: https://www.postgresql.org/docs/current/sql-release-savepoint.html
