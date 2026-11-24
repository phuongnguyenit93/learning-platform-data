# Verifying Success, Propagated Error, and Caught Error Flows with Spring REQUIRED

## 1. Objective

`Propagation.REQUIRED` is the default propagation mode of `@Transactional` in Spring Framework. When no transaction exists, a `REQUIRED` method creates a new physical transaction; when a compatible transaction already exists, it **joins the caller's same physical transaction**. This directly impacts outcomes when an error occurs, especially when the outer method **catches an exception** from an inner service and continues.

This lesson helps you verify these flows yourself:

1. **Success flow:** both outer and inner `REQUIRED` complete, and all changes commit together.
2. **Propagated error:** inner throws an unchecked exception, outer does not catch it, and the exception escapes through both interceptors; the entire transaction rolls back.
3. **Error caught by outer:** inner `REQUIRED` was already marked rollback-only by its transaction interceptor before the exception reached outer; outer catches and returns normally yet commit still fails, typically producing `UnexpectedRollbackException`.
4. **Error caught directly inside inner:** the error does not escape through the inner transaction interceptor and nobody marks rollback-only; the transaction can commit normally if no other issue occurs.

After this lesson, you will also know how to write integration tests verifying **committed/rolled-back data**, distinguish an exception occurring inside a method from an exception surfacing at commit, understand the effect of Spring AOP proxies, and choose appropriate error-handling strategies.

**Context:** An order placement service writes mandatory data before and after calling a child step. With `REQUIRED`, the child step does not get an independent transaction, even though it is a method annotated with `@Transactional` separately. Therefore, an error handled in the calling layer does not guarantee the shared transaction remains eligible to commit.

## 2. The REQUIRED Mechanism: Logical Scopes and Physical Transaction

Suppose an outer service calls an inner service, both annotated with `@Transactional(propagation = Propagation.REQUIRED)`:

```text
Caller
  |
  v
OuterService proxy
  |  Creates physical transaction T
  |  +-- logical scope OUTER
  |       |
  |       +-- INSERT A
  |       |
  |       +-- InnerService proxy
  |       |     +-- logical scope INNER
  |       |          uses same physical transaction T
  |       |          INSERT B
  |       |
  |       +-- INSERT C
  |
  +-- when OUTER ends: COMMIT or ROLLBACK T
  v
Caller
```

Two key concepts:

- **Physical transaction:** the actual transaction on the database connection, having a single final commit or rollback decision.
- **Logical transaction scope:** the boundary created when a call passes through a transactional interceptor. Outer and inner can have separate logical metadata/rollback-only status, yet `REQUIRED` maps them onto **the same physical transaction** when a transaction already exists.

Therefore:

- Inner `REQUIRED` does not commit independently when the inner method returns normally. Physical commit still waits for the outermost transaction boundary.
- If outer rolls back, all changes from inner participating in that transaction are also undone.
- If the inner transaction scope marks the shared transaction **rollback-only**, outer cannot clear that flag merely via `try/catch` or returning normally.
- In Spring's default configuration, when an inner participant makes the shared transaction rollback-only while outer still tries to commit, Spring throws `UnexpectedRollbackException` so the caller is not misled into thinking commit succeeded.

### When does REQUIRED open a new transaction?

| Context when calling a REQUIRED method | Behavior | Who decides the final commit? |
| --- | --- | --- |
| No existing transaction | Opens a new physical transaction | That method's transaction interceptor |
| Compatible existing transaction | Joins the open physical transaction | The outermost scope owning the physical transaction |
| Method only calls `this.inner()` in the same bean | May bypass the inner method's proxy | Only interceptors actually traversed apply metadata |
| Using `@Async`/a new thread | Thread-bound transaction does not carry across threads automatically | Depends on any new transaction actually opened on that thread |

In this lesson, all calls originate from a `CommandLineRunner` **without an outer transaction**. The outer service is in its own Spring bean; the inner service is also a separate Spring bean so both interceptors run. That lets us clearly observe `REQUIRED` logic without accidentally hitting self-invocation.

## 3. Flow 1 — Success: Outer and Inner Commit Together

```text
T0: caller -> outer proxy -> BEGIN T
T1: outer INSERT id=101
T2: inner proxy -> joins T, INSERT id=102
T3: inner returns normally -> no physical commit
T4: outer INSERT id=103, returns normally
T5: outer proxy -> COMMIT T succeeds
T6: caller SELECT -> [101, 102, 103]
```

All SQL statements at steps T1, T2, and T4 use the same transaction. The key point is that **T3 has not committed yet**, even though the inner method finished. Once outer returns and commits successfully at T5, a new read connection sees all three records.

If outer throws an exception matching a rollback rule after inner returned successfully, inner is rolled back as well. Thus an inner `REQUIRED` that "succeeded" only succeeded in its **logical scope**, not yet as durably committed data.

## 4. Flow 2 — Propagated Error: Entire Transaction Rolls Back

Inner writes a record and then throws `IllegalStateException`; outer **does not catch**:

```text
T0: outer proxy -> BEGIN T
T1: outer INSERT id=201
T2: inner proxy -> joins T
T3: inner INSERT id=202
T4: inner throws IllegalStateException
T5: inner interceptor sees unchecked exception
    -> marks shared transaction rollback-only
    -> rethrows exception to outer
T6: outer method does not catch -> outer interceptor sees exception
    -> ROLLBACK T
T7: caller catches IllegalStateException
T8: caller SELECT -> [] (no id=201,202)
```

With default configuration:

- `RuntimeException` and `Error` trigger rollback when escaping through a transaction interceptor.
- Checked exceptions normally **do not** trigger rollback by default, unless `rollbackFor` is declared or another default rule is configured. If you replace `IllegalStateException` with a checked exception and let it escape **without** configuring rollback, **commit followed by throwing the exception** can occur.
- If an exception is thrown **after SQL statements**, uncommitted data does not magically "stay" just because JDBC reported a successful UPDATE; the transaction manager determines the final outcome.

Example annotation changing the rollback policy for a checked exception:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    rollbackFor = java.io.IOException.class
)
public void importData() throws java.io.IOException {
    // Executes JDBC and may throw IOException.
}
```

This snippet illustrates the rule only; it is not a standalone runnable class. To verify properly, test with a concrete service and exception, then read the database **after the proxy invocation finishes**.

## 5. Flow 3 — Outer Catches Error from Inner REQUIRED: Still Rolls Back

This is the most confusing case:

```text
T0: outer proxy -> BEGIN T
T1: outer INSERT id=301
T2: inner proxy -> joins T, INSERT id=302
T3: inner throws IllegalStateException
T4: inner interceptor marks T rollback-only, then rethrows
T5: outer catches IllegalStateException -> prints "handled"
T6: outer INSERT id=303, returns normally
T7: outer interceptor attempts COMMIT T yet T is rollback-only
T8: Spring ROLLBACKs T and throws UnexpectedRollbackException
T9: caller SELECT -> [] (301,302,303 are all gone)
```

Outer indeed caught the error, yet **it caught it after the inner interceptor processed the error**. Under `REQUIRED`, physical transaction T was already marked rollback-only at T4. Catching in outer cannot clear the flag.

`UnexpectedRollbackException` appears at the **moment the outer interceptor completes the transaction**. It can occur **after the outer method body has returned**, so a `try/catch` inside outer's body around just the inner call will not catch the outer proxy's own commit exception. Only the caller of the outer proxy observes that exception.

This is intentional in Spring: if inner caused the database transaction to require rollback while outer thought it would commit, Spring must report **commit did not succeed**, preventing the caller from receiving a false success signal.

**Condition note:** This description applies to standard `REQUIRED` mechanics and default-configured transaction managers (specifically, an inner participant's rollback failure marking global rollback-only). If deep flags like `globalRollbackOnParticipationFailure` are altered or a specialized transaction manager is used, re-verify semantics. Do not tweak those flags merely to hide `UnexpectedRollbackException`.

## 6. Flow 4 — Error Caught Directly Inside Inner Before Crossing the Interceptor: Can Commit

Same `IllegalStateException`, yet inner catches it itself:

```text
T0: outer proxy -> BEGIN T
T1: outer INSERT id=401
T2: inner proxy -> joins T, INSERT id=402
T3: inner throws and catches IllegalStateException inside its own method body
T4: inner method returns normally; inner interceptor sees no error
T5: outer INSERT id=403, returns normally
T6: outer proxy COMMITs T
T7: caller SELECT -> [401,402,403]
```

**Comparing the catch locations:**

| Catch location | Does inner interceptor see the exception? | Default physical transaction | Typical outcome |
| --- | --- | --- | --- |
| Inner catches before returning | **No** | Does not roll back due to that exception | Commits if outer completes normally |
| Outer catches **after** inner proxy rethrows | **Yes** | Inner already marked rollback-only | Rolls back, potentially `UnexpectedRollbackException` |
| Caller catches after outer proxy rethrows | Outer sees error too | Outer rolls back on exit | Rolls back; caller receives original exception |
| Inner catches and explicitly calls `setRollbackOnly()` | No exception escapes, yet rollback-only is set | Transaction is no longer eligible to commit | Rolls back; if inner `REQUIRED` joined outer, potentially `UnexpectedRollbackException` |

If you need to catch inside inner yet **still require aborting** the entire transaction, you can explicitly mark rollback-only:

```java
catch (IllegalStateException ex) {
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
}
```

This fragment is only valid inside a method managed by Spring's transaction interceptor. When inner `REQUIRED` joins outer, the marker normally turns the shared transaction rollback-only. If the business intent is only to **discard inner's changes** while outer still commits, you need another mechanism such as `NESTED` with JDBC savepoints when supported by manager/driver, or adjusted transaction boundaries; `REQUIRED` does not permit independent partial rollback.

## 7. Complete Practical Example: Spring Boot, JDBC, H2, Java 17+

This project runs the four flows above and prints the actual data remaining after each transaction. It uses **Spring Boot 3.3.5**, **Java 17+**, Spring JDBC, and H2. Maven is the build tool; Spring Boot auto-configures `DataSource` and the JDBC transaction manager when the appropriate dependencies are present.

### 7.1. Directory structure

```text
required-flows-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── RequiredFlowsApplication.java
    │   │   ├── OuterFlowService.java
    │   │   └── RequiredInnerService.java
    │   └── resources/
    │       └── application.properties
    └── test/java/demo/
        └── RequiredFlowsIntegrationTest.java
```

### 7.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>required-flows-demo</artifactId>
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

`spring-boot-starter-jdbc` brings `JdbcTemplate` and transaction support; H2 is an in-JVM database. `spring-boot-starter-test` enables writing integration tests with JUnit 5.

### 7.3. application.properties

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:required_flows;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.main.banner-mode=off
```

`required_flows` is the in-memory database name. Multiple connections within the same JVM using that URL point to the same database; `DB_CLOSE_DELAY=-1` keeps the DB alive for the lifetime of the demo JVM. Each run in a fresh JVM recreates the table from scratch.

### 7.4. RequiredInnerService.java — three inner behaviors, all REQUIRED

**`src/main/java/demo/RequiredInnerService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RequiredInnerService {
    private final JdbcTemplate jdbc;

    public RequiredInnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void write(long id, String description) {
        insert(id, description);
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void writeThenFail(long id) {
        insert(id, "inner-fails");
        throw new IllegalStateException("inner failure");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void writeAndCatchInside(long id) {
        insert(id, "inner-caught");

        try {
            throw new IllegalStateException("handled inside inner");
        } catch (IllegalStateException expected) {
            // Demo only: method handles error, does not rethrow,
            // does not set rollback-only; interceptor sees normal return.
        }
    }

    private void insert(long id, String description) {
        jdbc.update(
                "INSERT INTO flow_event(id, description) VALUES (?, ?)",
                id, description);
    }
}
```

`write`: inner scope finishes normally; no separate commit when outer exists. `writeThenFail`: exception escapes through the inner interceptor and triggers the default rollback rule; afterward the exception continues to outer. `writeAndCatchInside`: exception is caught inside the method so the inner interceptor never sees it, and there is no marker either. The differing outcomes come from **where the exception is handled**, not from the type of JDBC statement.

### 7.5. OuterFlowService.java — four directly comparable flows

**`src/main/java/demo/OuterFlowService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterFlowService {
    private final JdbcTemplate jdbc;
    private final RequiredInnerService inner;

    public OuterFlowService(JdbcTemplate jdbc, RequiredInnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void success(long beforeId, long innerId, long afterId) {
        insert(beforeId, "outer-before");
        inner.write(innerId, "inner-ok");
        insert(afterId, "outer-after");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void propagateRuntime(long beforeId, long innerId) {
        insert(beforeId, "outer-before");
        inner.writeThenFail(innerId);
        // Exception escapes; code after the inner call does not run.
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void catchAfterInnerProxy(
            long beforeId, long innerId, long afterId) {
        insert(beforeId, "outer-before");

        try {
            inner.writeThenFail(innerId);
        } catch (IllegalStateException expected) {
            System.out.println("outer caught inner exception");
        }

        // Still runs, yet the physical transaction is already rollback-only.
        insert(afterId, "outer-after");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void catchInsideInner(
            long beforeId, long innerId, long afterId) {
        insert(beforeId, "outer-before");
        inner.writeAndCatchInside(innerId);
        insert(afterId, "outer-after");
    }

    private void insert(long id, String description) {
        jdbc.update(
                "INSERT INTO flow_event(id, description) VALUES (?, ?)",
                id, description);
    }
}
```

`OuterFlowService` is created by Spring via `@Service` and injected with `RequiredInnerService` via constructor. Calling `inner.method()` goes through the proxy of a **different** bean. Replacing that call with `this.someAnnotatedInnerMethod()` on the same object can bypass the inner method's transactional advice (proxy mode), yielding different results than predicted.

### 7.6. RequiredFlowsApplication.java — create table and verify after service completion

**`src/main/java/demo/RequiredFlowsApplication.java`**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

@SpringBootApplication
public class RequiredFlowsApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequiredFlowsApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, OuterFlowService outer) {
        return args -> {
            jdbc.execute("""
                    CREATE TABLE flow_event (
                        id BIGINT PRIMARY KEY,
                        description VARCHAR(80) NOT NULL
                    )
                    """);

            outer.success(101L, 102L, 103L);
            System.out.println(
                    "success rows: " + readIds(jdbc, 101L, 103L));

            try {
                outer.propagateRuntime(201L, 202L);
            } catch (IllegalStateException ex) {
                System.out.println(
                        "propagated exception: " + ex.getMessage());
            }
            System.out.println(
                    "propagated rows: " + readIds(jdbc, 201L, 202L));

            try {
                outer.catchAfterInnerProxy(301L, 302L, 303L);
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                        "outer commit exception: UnexpectedRollbackException");
            }
            System.out.println(
                    "caught after inner rows: " + readIds(jdbc, 301L, 303L));

            outer.catchInsideInner(401L, 402L, 403L);
            System.out.println(
                    "caught inside inner rows: " + readIds(jdbc, 401L, 403L));
        };
    }

    private static List<Long> readIds(
            JdbcTemplate jdbc, long from, long to) {
        return jdbc.queryForList(
                "SELECT id FROM flow_event WHERE id BETWEEN ? AND ? ORDER BY id",
                Long.class, from, to);
    }
}
```

**Why is this verification trustworthy?**

- `CommandLineRunner` is not annotated with `@Transactional`, so each outer service call owns a new physical transaction under `REQUIRED`.
- After `outer.success(...)` returns through the proxy, the transaction has committed. The subsequent SELECT runs outside that transaction.
- After `outer.propagateRuntime(...)` throws an error through the proxy, the transaction has already rolled back before the caller catches the exception.
- When `outer.catchAfterInnerProxy(...)` returns from the method body yet commit fails due to rollback-only, `UnexpectedRollbackException` is caught in the **caller**. The SELECT after `catch` confirms no rows from that flow exist.
- When `outer.catchInsideInner(...)` returns through the proxy, no scope marked rollback-only; the database commits all three rows.

Each flow uses a separate ID range. Querying by ID avoids misreading data from another flow. After the service finishes, `JdbcTemplate` has no transaction bound to the thread, so it uses a connection reading outside the just-completed transaction.

### 7.7. Run and observe stdout

Requires JDK 17+, Maven, and network/cached dependencies for the initial library download:

```bash
mvn spring-boot:run
```

Lines printed by the program itself (excluding Spring/Maven logs):

```text
success rows: [101, 102, 103]
propagated exception: inner failure
propagated rows: []
outer caught inner exception
outer commit exception: UnexpectedRollbackException
caught after inner rows: []
caught inside inner rows: [401, 402, 403]
```

Reading the results per case:

| Flow | Inner completion | Outer completion | Data after transaction |
| --- | --- | --- | --- |
| Success | Returns, no rollback-only | Commits | `[101, 102, 103]` |
| Propagated error | Throws unchecked, inner marks rollback-only | Outer rolls back and throws original error | `[]` |
| Outer catches inner error | Inner already marked rollback-only before outer catch | Rolls back, caller receives `UnexpectedRollbackException` | `[]` |
| Inner catches error itself | Inner returns, no rollback-only | Commits | `[401, 402, 403]` |

**Verification conclusion:** `try/catch` does not create a new transaction policy on its own. Behavior depends on **which interceptors the exception passes through**, whether the transaction status has been marked rollback-only, and which boundary performs the final commit.

## 8. Integration Tests: Asserting Data, Exceptions, and Completion Timing

Putting this logic into tests helps you detect changes to propagation, rollback rules, or proxy calls that alter outcomes. Tests carry no `@Transactional` on the class/method so they do not create an unintended outer test transaction.

**`src/test/java/demo/RequiredFlowsIntegrationTest.java`**

```java
package demo;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class RequiredFlowsIntegrationTest {
    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private OuterFlowService outer;

    @Test
    void successCommitsAllWrites() {
        outer.success(1001L, 1002L, 1003L);

        assertEquals(
                List.of(1001L, 1002L, 1003L),
                readIds(1001L, 1003L));
    }

    @Test
    void propagatedRuntimeRollsBackEntireTransaction() {
        assertThrows(
                IllegalStateException.class,
                () -> outer.propagateRuntime(2001L, 2002L));

        assertEquals(List.of(), readIds(2001L, 2002L));
    }

    @Test
    void catchingAfterInnerProxyDoesNotRestoreCommit() {
        assertThrows(
                UnexpectedRollbackException.class,
                () -> outer.catchAfterInnerProxy(
                        3001L, 3002L, 3003L));

        assertEquals(List.of(), readIds(3001L, 3003L));
    }

    @Test
    void catchingInsideInnerWithoutRollbackMarkerCanCommit() {
        outer.catchInsideInner(4001L, 4002L, 4003L);

        assertEquals(
                List.of(4001L, 4002L, 4003L),
                readIds(4001L, 4003L));
    }

    private List<Long> readIds(long start, long end) {
        return jdbc.queryForList(
                "SELECT id FROM flow_event WHERE id BETWEEN ? AND ? ORDER BY id",
                Long.class, start, end);
    }
}
```

Run:

```bash
mvn test
```

**Expected:** all 4 tests pass. Spring Boot initializes the `ApplicationContext`; `CommandLineRunner` runs before test methods begin, creating the table and exercising IDs 101–403. The tests use different IDs (1001–4003) so they do not collide with the demo data. Tests do not open an outer transaction themselves; therefore the outer `REQUIRED` method has already completed before the query in the assertion.

### Why not put `@Transactional` on the whole test?

Spring TestContext can automatically open a **test-managed transaction** for a test annotated with `@Transactional` and roll it back by default when the test ends. When that happens:

1. `outer.success()` `REQUIRED` joins the test's transaction, so when the outer service returns **no physical commit has happened yet**.
2. `outer.catchAfterInnerProxy()` may not throw `UnexpectedRollbackException` when you expect, because the real commit happens at the outer boundary managed by the test.
3. `JdbcTemplate` in the test may use the same connection/transaction and see uncommitted data; such a check does not verify a real commit.
4. The test framework rolling back at the end of the test can make data disappear even if the service itself failed to roll back.

To accurately verify `REQUIRED` flows, test from a caller **outside a transaction** and query after the service call completes. If a test-managed transaction is genuinely needed, you can use `TestTransaction` to end the transaction before verifying, though you must explicitly choose commit/rollback and isolate test data.

### Do not assert only the exception

A test like `assertThrows(IllegalStateException.class, () -> outer.propagateRuntime(...))` only checks the Java signal; without SELECTing data after the transaction, you have not proved the SQL work rolled back. Conversely, seeing only `[]` does not prove the right exception was propagated to the caller. Good tests verify **both the exception and the database state**.

## 9. What If You Want to Catch an Error and Still Commit Partially?

With ordinary `REQUIRED`, inner and outer belong to **one** physical transaction. Once the inner interceptor has set rollback-only, outer catching and continuing cannot "save" the shared transaction's commit by clearing the marker.

There are three design directions, depending on requirements:

1. **All succeed or fail together:** Keep `REQUIRED` and let critical errors escape past the outer proxy, or explicitly mark outer rollback-only and return a failure result. This is the default atomic behavior.
2. **An optional JDBC step allowed to roll back locally:** Consider `Propagation.NESTED` and JDBC savepoints, if supported by `PlatformTransactionManager`/driver/database. When inner fails, Spring rolls back to the savepoint; outer can catch the error, continue, and eventually commit the remainder. `NESTED` still shares the physical transaction and does not commit independently.
3. **A step needing an independent transaction:** `Propagation.REQUIRES_NEW` creates a separate physical transaction, suspending outer when needed. Inner can roll back without marking outer rollback-only, yet it can also commit independently even if outer rolls back later; there are connection costs and consistency risks to weigh.

Do not switch to `REQUIRES_NEW` just to make `UnexpectedRollbackException` disappear without determining whether inner's result is allowed to commit independently. Likewise, tweaking transaction manager flags to skip setting global rollback-only can allow a database transaction to continue unsafely after an error on some DBMSs.

### Another option: catch in the same outer scope before the exception crosses an inner interceptor

If inner is merely a helper without its own transaction advice, an exception caught by outer **before passing through the outer transaction interceptor** allows outer to commit after catching. Yet that is valid only when business rules genuinely **permit keeping writes made before the error**, not as a self-invocation trick to dodge transaction boundaries. Good solutions make transaction boundaries and error policies explicit and easy to test.

## 10. Common Mistakes When Verifying REQUIRED

### 10.1. "Outer already caught it so it will definitely commit"

Wrong if the exception already passed through an inner `@Transactional(REQUIRED)` interceptor and marked the shared transaction rollback-only. When outer commits, `UnexpectedRollbackException` can appear. Always check data after the outer proxy.

### 10.2. Confusing inner's return with COMMIT

Inner `REQUIRED` joins outer's physical transaction. Inner returning involves no independent commit; outer rolling back discards inner's part as well. Do not verify results with a query inside the outer transaction and declare the data committed.

### 10.3. Catching inside inner and thinking Spring automatically rolls back

If inner catches itself, does not rethrow, and does not call `setRollbackOnly()`, the interceptor sees a normal return. Logging the exception is no substitute for a transaction rollback policy.

### 10.4. Catching every exception and continuing to write despite a broken database

Some JDBC/constraint errors can render the DB transaction unusable (depending on DB/driver). Do not swallow all `Exception`s and try to commit while state is uncertain. Organize proper rollback and controlled retries when needed.

### 10.5. Changing unchecked to checked exception while forgetting rollbackFor

Spring rolls back by default on `RuntimeException`/`Error`; checked exceptions normally do not roll back by default. If changing an exception hierarchy or using `IOException` in business logic, consider `@Transactional(rollbackFor = IOException.class)` and add tests.

### 10.6. Self-invocation bypassing Spring AOP

A `this.innerMethod()` call inside the same bean in proxy mode usually does not pass through the inner transaction interceptor. Consequently, a test may commit even though the original design expected inner to mark rollback-only. Use a separate Spring bean and invoke through its proxy as in the example.

### 10.7. Opening a JDBC connection manually and committing outside Spring

`DataSourceTransactionManager` only controls connections belonging to its transaction. If a service opens another connection itself with `autoCommit=true`, data can commit independently and not be undone by outer rollback. Use `JdbcTemplate` with the right `DataSource`.

### 10.8. Re-reading from the same transaction to "confirm commit"

Inside a transaction, the writing connection can see its own uncommitted changes. To confirm, wait for the **outermost physical transaction** to finish and then read using an independent connection/transaction targeting the primary database. Long snapshots under `REPEATABLE_READ` or lagging read replicas can also produce different read results.

### 10.9. `@Transactional` on a test creating an unintended outer boundary

TestContext rolls back test-managed transactions by default. If the test already opened a transaction, your outer service is actually just an inner participant. Avoid `@Transactional` on tests when verifying service commits at the right boundary.

### 10.10. Looking only at a "caught" log and assuming data is kept

Console output `outer caught inner exception` only proves the Java `catch` ran. Immediately afterward, the interceptor can still roll back everything. Place the SELECT **after the caller has exited the proxy** and verify by ID.

## 11. Debugging Strategy When Outcomes Differ from Expectations

If the success case fails to commit:

- Was there an error at transaction commit, a constraint violation, or an earlier SQL failure?
- Was outer marked rollback-only by another participant?
- Are you checking data on the same database/schema/tenant?
- Has the caller exited the outermost proxy, or is an outer/test transaction still incomplete?

If the propagated-error case still leaves data behind:

- Is the actual exception checked or unchecked? Is `rollbackFor` appropriate?
- Is the transaction annotation active through a proxy? Is there self-invocation or a bean instantiated with `new`?
- Does `JdbcTemplate` participate in the transaction manager's `DataSource`?
- Was there a `REQUIRES_NEW` or an auto-committing connection before outer rolled back?
- Did the ID already exist from a previous run or another transaction?

If outer catches an error without receiving `UnexpectedRollbackException`:

- Does the inner method actually have `@Transactional(REQUIRED)` and get called through a **proxy**?
- Did the error escape through the inner interceptor, or was it caught beforehand?
- Is a non-default transaction manager configuration in use?
- Is outer participating in an even broader transaction, so the actual commit failure surfaces **later** at the outermost boundary?
- Does the test have `@Transactional` changing the boundary?

In a practice environment, you can increase transaction logging via Spring Boot configuration:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Enable detailed logging only when needed. Transaction logs help locate boundaries and rollback-only flags, yet **checking the final SQL query result** is what confirms whether data persisted or not.

## 12. Exercises and Review Questions

**Exercise 1 — Success:** In the example, inner `write(...)` returns normally and then outer throws `IllegalStateException` after the last INSERT. Are `[101,102,103]` committed?

**Answer:** No. Inner `REQUIRED` does not commit on its own; outer's exception satisfies the rollback rule, so the entire physical transaction rolls back.

**Exercise 2 — Moving the catch:** If the catch is moved from `OuterFlowService.catchAfterInnerProxy` into `RequiredInnerService.writeThenFail`, with no rethrow and no marker, does `UnexpectedRollbackException` still occur?

**Answer:** No longer from that exception, assuming other conditions stay the same. The inner interceptor sees a normal return, and outer can commit all INSERTs.

**Exercise 3 — Why couldn't catch save it?** Outer catches `IllegalStateException` from inner `REQUIRED`, yet when outer returns the caller receives `UnexpectedRollbackException`. What mechanism occurred?

**Answer:** The inner interceptor marked the shared physical transaction rollback-only. Outer attempted to commit, yet the manager forced a rollback and reported the unexpected outcome at the outer boundary.

**Exercise 4 — Throw timing:** Why can placing `try/catch(UnexpectedRollbackException)` inside the outer method body around the inner call fail to catch outer's commit error?

**Answer:** The outer transaction interceptor performs commit/rollback **after the outer method body has returned**; only the caller of the outer proxy receives the exception upon transaction completion.

**Exercise 5 — Checked exception:** An inner `REQUIRED` method throws `IOException` out through its proxy, with no `rollbackFor`. Is rollback guaranteed?

**Answer:** No. Checked exceptions do not trigger rollback by default under standard rules; Spring may commit if there is no rollback-only flag or other error.

**Exercise 6 — Test transaction:** You add `@Transactional` to an integration test and call `outer.success(...)`. Does the service call returning prove the database committed?

**Answer:** No. `REQUIRED` joins the open test-managed transaction; the actual commit/rollback happens at the test boundary, and TestContext rolls back by default.

**Exercise 7 — Need separate rollback for a child step:** Should you just switch `REQUIRED` to `REQUIRES_NEW` if you want to keep outer when inner fails?

**Answer:** Only after evaluating the transaction independence of the child step. `REQUIRES_NEW` commits independently; if you need a savepoint within the same JDBC transaction, look at `NESTED` when supported.

**Exercise 8 — Reading data:** Why can a `SELECT` inside `outer.success()` see id=102 before the outer proxy commits?

**Answer:** A JDBC connection inside a transaction normally sees its own uncommitted changes. That read is not proof of a commit.

## 13. Official References

- Spring Framework — **Transaction Propagation**, explaining logical/physical scopes of `PROPAGATION_REQUIRED` and `UnexpectedRollbackException`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — **Rolling Back a Declarative Transaction**, default rules for unchecked/checked exceptions: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — **Using @Transactional**, default attributes and `rollbackFor`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — **Declarative Transaction Management Explained**, role of proxies and transaction interceptors: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — **TestContext Transaction Management**, test-managed transactions and default rollback: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html

**Takeaway:** With `REQUIRED`, outer and inner share **one physical transaction** when outer has opened a transaction. Success is confirmed only at the outermost commit; propagating unchecked errors normally rolls back everything; an exception that has passed through an inner interceptor can make the shared transaction rollback-only even if outer catches it; whereas an exception caught *before* passing through the interceptor can allow commit if no marker is set. Always verify both the **Java signal** and the **final data** after the outermost boundary.