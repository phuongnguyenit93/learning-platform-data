# Triggering a Mid-Flow Error and Observing Rollback

## 1. Practice Goal

A transaction is only truly meaningful when you **prove it undoes operations that already ran before an error**. This lesson intentionally injects an error midway through a Spring Framework business operation, then re-reads the data to inspect the result.

After this lesson, you can:

- Distinguish **changes executed inside a transaction** from **committed changes**.
- Pinpoint the start, failure point, and rollback point of a `@Transactional` method.
- Write an integration test for two scenarios: failure **after the first SQL statement** and failure **after both SQL statements yet before commit**.
- Explain why exceptions must pass through the transaction interceptor, and why catching/swallowing errors can cause the database to commit partial data.
- Self-verify by removing the transaction in a **learning sandbox** and observing assertions fail.

We use **Java 17+, Spring Boot 3.5.0, Spring JDBC, in-memory H2, and JUnit 5**. Tests run via Maven; no HTTP API or separate database server is required. All changes stay within the H2 test database.

## 2. Scenario: Money Transfer Must Not Leave Partial Updates

There are two accounts in the same database:

| Account | Initial balance | After successful 200 transfer | After error and rollback |
| --- | ---: | ---: | ---: |
| A (id = 1) | 1,000 | 800 | 1,000 |
| B (id = 2) | 500 | 700 | 500 |
| **Total** | **1,500** | **1,500** | **1,500** |

The business operation must execute in order:

1. Deduct 200 from account A using `UPDATE`.
2. Add 200 to account B using `UPDATE`.
3. Only **commit** when the entire business operation completes.

To test rollback, we **deliberately throw an exception** after step 1, before step 2. At that moment, the debit SQL statement has already affected one row; a query run **inside the same transaction** can see A = 800. Yet the transaction has not committed. Once the exception escapes and Spring rolls back, the durable outcome must be A = 1,000, B = 500.

One tougher test: let both `UPDATE` statements finish, **and only then throw an exception before the method returns**. Both the deduction from A and the addition to B must roll back. That proves "SQL has finished executing" does not mean "the transaction has committed."

~~~text
Caller
  |
  v
Spring transaction proxy
  |
  +-- BEGIN
  |     |
  |     +-- UPDATE account A: 1000 -> 800
  |     |
  |     +-- [FAILURE POINT 1] Exception? -- Yes --> ROLLBACK
  |     |
  |     +-- UPDATE account B: 500 -> 700
  |     |
  |     +-- [FAILURE POINT 2] Exception? -- Yes --> ROLLBACK
  |     |
  |     +-- No error ----------------> COMMIT
  |
  v
Caller receives result or exception
~~~

An **error after the transaction has committed** is a different scenario: rollback cannot automatically rewind a completed commit. This lesson deliberately injects errors **before the commit boundary** to observe atomicity.

## 3. Setting Up a Runnable Spring Boot Project

Create a `rollback-lab` directory with this structure:

~~~text
rollback-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/rollback/
    │   │   ├── RollbackLabApplication.java
    │   │   └── MoneyTransferService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/com/example/rollback/
            └── MoneyTransferServiceTest.java
~~~

If generating from **Spring Initializr**, select Java 17, Maven, Spring Boot 3.5.0, and dependencies **JDBC API**, **H2 Database**, **Spring Boot Starter Test**. You can also create the files below directly, then run them with Maven already installed.

### 3.1. The `pom.xml` File

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>rollback-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
~~~

`spring-boot-starter-jdbc` provides Spring JDBC/`JdbcTemplate` and JDBC transaction infrastructure; `h2` is the observable database; `spring-boot-starter-test` provides JUnit 5 and Spring testing support.

### 3.2. The `src/main/resources/application.properties` File

~~~properties
spring.datasource.url=jdbc:h2:mem:rollback_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

H2 lives in the Java process memory. Once the process exits, test data is not meant for long-term persistence. The `DB_CLOSE_DELAY=-1` parameter keeps the in-memory database alive throughout the process lifetime, even when the last connection closes. Spring Boot runs `schema.sql` at startup, and the test re-inserts initial data before each case.

### 3.3. The `src/main/resources/schema.sql` File

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);
~~~

`balance` uses an integer solely to simplify the lesson and avoid `double` rounding errors. Real financial applications must design currency units, value ranges, overflow checks, transaction history, access permissions, and idempotency properly. The `CHECK` constraint only prevents negative balances; it does not automatically guarantee both transfer steps succeed together.

### 3.4. The `src/main/java/com/example/rollback/RollbackLabApplication.java` File

~~~java
package com.example.rollback;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RollbackLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(RollbackLabApplication.class, args);
    }
}
~~~

This class is the Spring Boot entry point and lets `@SpringBootTest` locate the application configuration. The service and test classes must reside in the same `com.example.rollback` package shown in the layout above.

## 4. Writing a Service with Two Clear Failure Points

**File `src/main/java/com/example/rollback/MoneyTransferService.java`:**

~~~java
package com.example.rollback;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class MoneyTransferService {
    public enum FailurePoint {
        NONE,
        AFTER_DEBIT,
        AFTER_CREDIT
    }

    private final JdbcTemplate jdbc;

    public MoneyTransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(
            long sourceId,
            long destinationId,
            long amount,
            FailurePoint failurePoint) {

        if (amount <= 0 || sourceId == destinationId || failurePoint == null) {
            throw new IllegalArgumentException("Invalid transfer input");
        }

        int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, sourceId, amount
        );

        if (debited != 1) {
            throw new IllegalStateException(
                "Source missing or insufficient balance"
            );
        }

        // Intentional failure between the two UPDATE statements.
        if (failurePoint == FailurePoint.AFTER_DEBIT) {
            long balanceInsideTransaction = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = ?",
                Long.class,
                sourceId
            );
            throw new IllegalStateException(
                "FAIL_AFTER_DEBIT: source balance inside transaction=" +
                balanceInsideTransaction
            );
        }

        int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, destinationId
        );

        if (credited != 1) {
            throw new IllegalStateException("Destination account missing");
        }

        // Both UPDATEs have executed; the transaction has not committed yet.
        if (failurePoint == FailurePoint.AFTER_CREDIT) {
            throw new IllegalStateException("FAIL_AFTER_CREDIT");
        }
    }
}
~~~

### Exact Moment-by-Moment Explanation

**Before `@Transactional`:** Spring manages the `MoneyTransferService` bean. When another bean calls `transfer(...)` **through Spring's proxy**, the transaction interceptor asks the transaction manager to start a transaction or join an existing one. In this lab, the test has no enclosing transaction, so each service call creates a new transaction.

**After the debit statement:** `JdbcTemplate.update(...)` returns the number of updated rows. If the source account exists, has enough balance, and the SQL is valid, it returns `1`; A's balance becomes **800 inside the transaction**. This does not mean the data has committed. When the same connection/query inside the transaction reads again, it can see that uncommitted change.

**At `AFTER_DEBIT`:** code intentionally runs `throw new IllegalStateException(...)`. This is a `RuntimeException`, matching Spring's default rollback rule. The update to B has not been called yet. The exception leaves the service, and the transaction interceptor catches it and requests rollback. On H2, A = 800 is undone back to 1,000.

**At `AFTER_CREDIT`:** A has been debited and B has been credited, yet the method has not completed normally so the transaction has not committed. `IllegalStateException` still rolls back both statements, bringing A/B back to 1,000/500.

**At `NONE`:** both statements succeed and the method returns normally; the transaction interceptor commits. The confirmed state is A = 800, B = 700.

**When the destination account does not exist:** `jdbc.update(...)` returns `0`, and the service throws an exception *after already debiting the source*. This is a realistic business error scenario, distinct from an injected fault, yet the expected rollback outcome is the same.

Placing `@Transactional` on the **public service method** puts the transaction boundary around the entire business operation. Placing separate transactions on individual repository updates without an outer transaction can cause the first statement to commit before the next statement fails.

## 5. Writing an Integration Test Measuring Persisted Data

**File `src/test/java/com/example/rollback/MoneyTransferServiceTest.java`:**

~~~java
package com.example.rollback;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static com.example.rollback.MoneyTransferService.FailurePoint.AFTER_CREDIT;
import static com.example.rollback.MoneyTransferService.FailurePoint.AFTER_DEBIT;
import static com.example.rollback.MoneyTransferService.FailurePoint.NONE;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class MoneyTransferServiceTest {
    @Autowired
    private MoneyTransferService service;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void resetAccounts() {
        jdbc.update("DELETE FROM account");
        jdbc.update(
            "INSERT INTO account (id, balance) VALUES (?, ?)",
            1L, 1000L
        );
        jdbc.update(
            "INSERT INTO account (id, balance) VALUES (?, ?)",
            2L, 500L
        );
    }

    @Test
    void noFailureCommitsBothUpdates() {
        service.transfer(1L, 2L, 200L, NONE);

        assertEquals(800L, balanceOf(1L));
        assertEquals(700L, balanceOf(2L));
    }

    @Test
    void failureBetweenUpdatesRollsBackFirstUpdate() {
        IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> service.transfer(1L, 2L, 200L, AFTER_DEBIT)
        );

        assertEquals(
            "FAIL_AFTER_DEBIT: source balance inside transaction=800",
            error.getMessage()
        );

        // Re-read after the call through the Spring proxy finishes with rollback.
        assertEquals(1000L, balanceOf(1L));
        assertEquals(500L, balanceOf(2L));
    }

    @Test
    void failureAfterBothUpdatesRollsBackEverything() {
        IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> service.transfer(1L, 2L, 200L, AFTER_CREDIT)
        );

        assertEquals("FAIL_AFTER_CREDIT", error.getMessage());
        assertEquals(1000L, balanceOf(1L));
        assertEquals(500L, balanceOf(2L));
    }

    @Test
    void invalidDestinationAlsoRollsBackDebit() {
        IllegalStateException error = assertThrows(
            IllegalStateException.class,
            () -> service.transfer(1L, 99L, 200L, NONE)
        );

        assertEquals("Destination account missing", error.getMessage());
        assertEquals(1000L, balanceOf(1L));
        assertEquals(500L, balanceOf(2L));
    }

    private long balanceOf(long id) {
        return jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?",
            Long.class,
            id
        );
    }
}
~~~

### Why Does This Way of Writing Tests Actually Prove Rollback?

1. **`@SpringBootTest` starts a real Spring context** and injects the Spring-managed `MoneyTransferService`, so calls pass through the transaction proxy. If you call `new MoneyTransferService(jdbc)` yourself, the annotation is not triggered through the default proxy.
2. **`@BeforeEach` cleans and initializes data independently for each test.** Whichever test runs first does not affect subsequent test results.
3. **There is no `@Transactional` on the test class or test methods.** If a test opens an outer transaction itself, the test can "look like it rolled back properly" because the test's own transaction is rolled back by the framework at the end, even if the service failed to manage its transaction as intended. With the approach here, `jdbc.update` during setup commits outside the service's transaction, and reads after the exception observe the finalized state of the service's transaction.
4. **`assertThrows` only checks that an error was thrown; assertions reading the DB are what test atomicity.** A test that only verifies an exception without reading state afterward does not prove rollback.
5. **Checking both accounts** matters more than checking only an exception or a single balance. The `AFTER_CREDIT` test specifically demonstrates that even when both updates already executed, both are undone.
6. **Checking the `800` message inside the transaction:** at the moment the `AFTER_DEBIT` error is created, a query inside the same transaction genuinely sees the intermediate balance 800; yet after rollback, the test reads 1,000. That is the difference between **temporary changes** and **committed data**.

The tests use H2 with the same `DataSource` for the Spring transaction manager and `JdbcTemplate`. If a real application has multiple `DataSource`s/transaction managers, you must select the right transaction manager and ensure operations requiring atomicity fall under its management scope.

## 6. Running the Tests and Interpreting Results

Open a terminal in the `rollback-lab` directory. Check the environment:

~~~bash
java -version
mvn -version
~~~

Java 17+ is required; ensure Maven uses that JDK. Run:

~~~bash
mvn test
~~~

If created via Spring Initializr with the Maven Wrapper, you can use `./mvnw test` on Linux/macOS or `.\mvnw.cmd test` on Windows PowerShell.

JUnit runs all four tests within one Spring Boot context; execution order need not be fixed. When dependencies/compilation/H2 startup succeed, the Maven Surefire report must show **4 tests passed, 0 failures, 0 errors**. Spring log lines, library versions, and timings are not fixed.

| Test | Failure Injection Point | Observed Values After Call | What It Proves |
| --- | --- | --- | --- |
| `noFailureCommitsBothUpdates` | No error injected | A = 800, B = 700 | Happy path commits both UPDATEs. |
| `failureBetweenUpdatesRollsBackFirstUpdate` | After debiting A, before crediting B | A = 1,000, B = 500 | Debit statement ran yet was rolled back. |
| `failureAfterBothUpdatesRollsBackEverything` | After debiting A and crediting B, before commit | A = 1,000, B = 500 | Both executed SQL statements were still rolled back. |
| `invalidDestinationAlsoRollsBackDebit` | After debiting A, when updating B affects 0 rows | A = 1,000, B = 500 | Business error does not lose the debited amount. |

### Detailed Observation of the Mid-Flow Failure Test

Following `failureBetweenUpdatesRollsBackFirstUpdate`:

~~~text
Before test:
    SELECT A -> 1000
    SELECT B -> 500

Inside @Transactional:
    UPDATE A -200 -> A=800 inside transaction
    SELECT A same transaction -> 800
    throw IllegalStateException("FAIL_AFTER_DEBIT: ...=800")

Spring transaction interceptor:
    RuntimeException escapes method
    -> roll back transaction

After service call finishes:
    SELECT A -> 1000
    SELECT B -> 500
~~~

**Why don't we need to call `rollback()` in the service?** Because Spring manages the transaction boundary. When a runtime exception matching rollback rules escapes a proxy-managed method, the transaction manager undoes the transaction. Business code focuses on updates, condition checks, and throwing meaningful errors.

**Must the exception appear on the console?** No. `assertThrows` catches the exception as an expected outcome, so the test still **PASSES**. The primary evidence is the asserted message and re-read balances. If you want further observation via debugger, set breakpoints on the `throw` statement and on `balanceOf` in the test; no external logging or manual data edits are needed.

## 7. Counter-Proof: What Changes If the Transaction Boundary Is Removed?

Perform this only in a **copy of the lab project and H2 tests**:

1. Temporarily comment out the `@Transactional` annotation on `MoneyTransferService.transfer(...)`.
2. Re-run `mvn test` with all assertions unchanged.
3. Observe the rollback tests fail; then restore `@Transactional` and re-run to confirm PASS.

With `JdbcTemplate` and H2 in default auto-commit mode when **there is no enclosing transaction**, each successful `UPDATE` commits independently. Therefore:

| Scenario when `@Transactional` is removed | Observable outcome with lab configuration |
| --- | --- |
| `AFTER_DEBIT` error | A = 800, B = 500: data is left partially updated. |
| `AFTER_CREDIT` error | A = 800, B = 700: both updates committed separately even though the call threw an exception. |
| Destination account missing | A = 800, B = 500: 200 lost from source. |
| No error | A = 800, B = 700: looks right on the surface, yet provides no atomicity if a mid-way error occurs. |

In the mid-flow error test, the assertion expects `1000` yet actually reads `800`, so the test fails. This is a **controlled counter-proof** for the transaction's role; never use "remove the transaction to test" on a system with real data.

Note: if another outer transaction wraps the call, or datasource/auto-commit settings differ, the counter-proof will not be equivalent. Thus the lab intentionally uses a test without `@Transactional` and default H2 connections.

## 8. Common Mistakes That Prevent Rollback from Happening as Expected

### 8.1. Error Caught and Swallowed Inside the Service

See this **erroneous illustration**:

~~~java
@Transactional
public void doWork() {
    try {
        performFirstUpdate();
        performSecondUpdate();
    } catch (RuntimeException ex) {
        // Only log and exit method normally.
    }
}
~~~

This is not a standalone compilable class because the update methods are omitted for illustration. If the exception is caught and no rollback signal remains, Spring may see the method end normally and **commit the changes already performed**.

A usually better fix is to **rethrow the exception** after adding context or use a business unchecked exception. When you must catch an error yet still roll back, explicitly mark the transaction rollback-only via the appropriate Spring API; note that if participating in an outer transaction, the caller may encounter `UnexpectedRollbackException` when attempting to commit a transaction marked rollback-only.

### 8.2. Using Checked Exceptions Without Configuring Rollback Rules

By default, Spring rolls back when a `RuntimeException` or `Error` escapes a transactional method. A checked exception like `IOException` **does not trigger rollback by default**. When rollback is also needed for checked exceptions, configure accordingly:

~~~java
@Transactional(rollbackFor = java.io.IOException.class)
public void operation() throws java.io.IOException {
    // Annotation configuration example; not a standalone program.
}
~~~

In the lab, we intentionally chose `IllegalStateException` to test default rollback rules. Do not assume "throwing any Exception triggers rollback."

### 8.3. Not Calling Through the Spring Proxy

With default proxy transactions:

- Manually instantiating a service with `new` typically bypasses the transaction interceptor.
- Calling `this.transfer(...)` from another method **in the same bean** (self-invocation) typically does not go through the proxy.
- Placing the annotation only on a private method and expecting the AOP proxy to wrap it in a transaction is a misconception.
- Tests must obtain the bean from the Spring context, e.g., via `@Autowired` as above.

What needs checking is **whether a transaction is actually opened at the business call**, not merely whether the annotation appears in source code.

### 8.4. Putting Transactions Only on Individual Statements

If each repository method has its own transaction and commits when the method returns, the first transaction can commit before the second method fails. The problem requires atomicity for **the entire money transfer**, so the outer transaction must live on the service method representing the whole operation.

### 8.5. Tests Opening Their Own Transaction Masking Bugs

Spring Test can roll back a test's transaction after the test completes if the test is annotated with `@Transactional`. That is handy when writing other tests, yet can prevent this example from **measuring the service's own commit/rollback behavior**.

Hence this lesson uses `@SpringBootTest` **without `@Transactional` on the test** and resets data via `@BeforeEach`. Assertions execute after the service proxy has already handled commit or rollback.

### 8.6. Multiple Datasources or External Side Effects

A local JDBC transaction does not automatically undo sent emails, HTTP requests, published messages, or changes in an entirely separate database. Dedicated coordination designs are required (e.g., transactional outbox, idempotency, saga depending on business needs). Never treat a passing H2 test as proof that an entire distributed system is safe.

## 9. Observing Differences Between Rollback, Commit, and Post-Commit Failure

One especially important scenario in real applications: the service has committed, yet the HTTP connection to the client drops before the client receives the response.

| Situation | Database state | What the client can know |
| --- | --- | --- |
| Exception after first SQL, before commit | Transaction rolls back; A/B unchanged | Client typically receives an error. |
| Exception after second SQL, before commit | Transaction rolls back both; A/B unchanged | Client typically receives an error. |
| Method finishes and commits successfully | A/B change per business rules | Client typically receives success. |
| Commit succeeded yet response was lost | A/B **may have already changed** | Client is unsure whether the request was processed. |

That final scenario is not solved by "blindly retrying": the transfer could be executed a second time. Production designs require a **request ID/idempotency key**, operation status lookup, and retry rules. Transactions guarantee atomicity **within the managed boundary**, not that clients always learn the result across all network failures.

## 10. Extended Practice on This Same Project

Once all four tests pass, you can try additional cases in the test database:

**Exercise A — Insufficient balance:** call `service.transfer(1L, 2L, 2000L, NONE)`. The debit SQL has condition `balance >= 2000`, so it affects 0 rows; the exception occurs **before any data changes**. Assert A/B remain unchanged. This is a validation test, yet it **does not replace** a mid-flow rollback test because there was no update to undo.

**Exercise B — Error after both steps:** set a breakpoint before `throw new IllegalStateException("FAIL_AFTER_CREDIT")`. Use the debugger to inspect both temporary balances inside the transaction if desired; after resuming, the test confirms they return to 1,000/500. The key part is reading **after rollback** rather than inferring from an intermediate log.

**Exercise C — Exception present yet no rollback:** create a test-only copy of the service, catch and swallow `IllegalStateException` at the failure point. Observe why the annotation is no longer enough when the method returns normally. Then fix it by rethrowing the error; do not put the broken copy into real applications.

**Exercise D — Changing rollback rules:** try a checked exception in a separate lab method and configure `rollbackFor`. Distinguish **exception type** from **whether a transaction started**.

**Exercise E — Two callers modifying the same row:** if switching to PostgreSQL or MySQL, try two concurrent transactions and observe lock waits/isolation. This is a concurrency exercise, distinct from rollback caused by intentionally injected faults.

## 11. Self-Check Questions

1. **At the moment of the `AFTER_DEBIT` exception, is A equal to 800 or still 1,000?** — Inside that transaction itself, A became 800; however, the change has not committed and will be rolled back to 1,000.
2. **Is `assertThrows` alone enough to prove rollback?** — No. You must re-read the database after the exception passes through the transaction interceptor and confirm the original data is preserved.
3. **If both SQL statements finish successfully and only then throw, can both roll back?** — Yes, provided they are in the same uncommitted transaction and an exception matching rollback rules escapes.
4. **Why is the test not annotated with `@Transactional`?** — So no outer test transaction masks boundary bugs in the service's transaction.
5. **If an exception is caught inside the method and not rethrown, is Spring guaranteed to roll back?** — No. The method may complete normally and commit if the transaction was not marked rollback-only.
6. **Why run with `@Autowired MoneyTransferService`?** — So calls go through the Spring bean/proxy and the transaction interceptor is activated.
7. **Why is `AFTER_DEBIT` a better injection point than failing right before the first SQL statement?** — Because an actual change exists that must be undone; that is what makes rollback evidence meaningful.
8. **Can lost responses after commit be solved by rollback?** — No. You must determine the processed outcome and prevent duplicate retries.

## 12. Learning Outcomes Checklist

- [ ] Run `mvn test` with **4 passing tests** and no external database.
- [ ] Know that A = 800 is an **intermediate state inside the transaction** before rollback, not committed state.
- [ ] When injecting an error after the first UPDATE, final data is **A = 1,000, B = 500**.
- [ ] When injecting an error after both UPDATEs, final data is **A = 1,000, B = 500**.
- [ ] When no error is injected, final data is **A = 800, B = 700**.
- [ ] Understand rollback requires both an **appropriate transaction boundary** and a **triggered exception/rollback rule**.
- [ ] Distinguish rollback before commit from committing successfully yet the client missing the response.

**Conclusion:** place an error at a point **after data has been modified yet before commit**, then re-read the database from outside the transactional call. What proves it is not whether code has `@Transactional` or whether a test caught an exception, but that **all incomplete updates were genuinely undone**. The success test and the two failure tests above are direct evidence of that behavior.

### Reference Documentation

- [Spring Framework — Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Rolling back a declarative transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transactional test execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)
- [Spring Boot — SQL databases and SQL initialization](https://docs.spring.io/spring-boot/reference/data/sql.html)