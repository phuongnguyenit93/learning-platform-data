# Behavior When No Outer Transaction Exists — NESTED and Savepoints

## 1. The Core Answer

When Spring Framework encounters a call to a method declared with `@Transactional(propagation = Propagation.NESTED)`, Spring must first check **whether an outer physical transaction already exists at the call site**.

- **No outer transaction exists:** `NESTED` opens **a new physical transaction**, then commits when the method completes normally, or rolls back the entire transaction when an exception matching a rollback rule exits. **There is no savepoint nested inside an old transaction** because no old transaction exists at all.
- **Compatible outer JDBC transaction already exists:** `NESTED` shares **the same physical transaction** and creates a **savepoint** for the inner logical scope. When inner fails, it can roll back to the savepoint and let outer continue. Inner completing normally does not mean an independent commit: outer still decides the final commit.
- **Outer exists, yet manager/driver does not support savepoints:** do not assume nested will work. Spring may report `NestedTransactionNotSupportedException` or a JDBC error.
- **Does not go through a Spring proxy:** the annotation on the inner method may not be handled by the transaction interceptor, even though `@Transactional` is in the source code.

Therefore, the exact answer to "**Behavior when no outer transaction exists**" is: **`NESTED` starts a transaction like `REQUIRED` when no transaction exists; it neither requires an outer transaction nor creates a standalone savepoint.** Requiring an outer transaction is `MANDATORY`'s behavior, not `NESTED`'s.

### Quick Decision Table

| Situation | Physical transaction | Savepoint | Who commits / rolls back? |
| --- | --- | --- | --- |
| NESTED via proxy, **no outer** | Starts new T1 | No | Inner proxy completes T1 |
| NESTED via proxy, **outer T1 exists** and JDBC supports it | Shares T1 | Yes, at start of inner scope | Outer completes T1; inner can roll back locally |
| NESTED when outer exists but nested unsupported | Cannot execute savepoint as requested | No valid savepoint | Must handle configuration / DB capability error |
| `this.inner()` bypassing proxy | Does not apply inner annotation automatically | Not created automatically | Depends on existing transaction, if any |

This lesson is about **propagation and transaction scope**, not introducing separate Java syntax. The hands-on section below uses JDBC and H2 to inspect `isNewTransaction` and `hasSavepoint` directly.

## 2. A Savepoint Is Not an Independent Transaction

### Transaction, Logical Scope, and Savepoint

**Physical transaction** is the actual database transaction: SQL operations belong to one connection/resource transaction, and the database guarantees commit/rollback for it.

**Logical transaction scope** is the boundary managed by the Spring transaction interceptor when a transactional method is invoked via proxy. Multiple logical scopes can share a single physical transaction.

**Savepoint** is a marker **inside** an open transaction. It allows partial rollback while keeping operations before the marker within the same transaction. A savepoint is not a second transaction with an independent commit.

Illustrative SQL example when **outer exists**:

~~~sql
BEGIN;

UPDATE account_balance SET amount = amount + 10 WHERE id = 1;

SAVEPOINT inner_start;
UPDATE account_balance SET amount = amount + 10 WHERE id = 2;

ROLLBACK TO SAVEPOINT inner_start;
-- UPDATE for id=2 is undone, id=1 still has uncommitted changes.

UPDATE account_balance SET amount = amount + 10 WHERE id = 1;
COMMIT;
~~~

In Spring/JDBC, the transaction manager normally operates through `Connection.setSavepoint()` and savepoint rollback APIs rather than requiring developers to emit these SQL statements manually. This is only a conceptual description, not commands to embed manually in code running `@Transactional`.

When **no outer transaction exists**, the accurate flow is:

~~~text
Call via Spring proxy @Transactional(NESTED)
             |
             v
Is a compatible physical transaction active?
             |
             +-- NO
             |      |
             |      +-- Open new transaction T1
             |      +-- Execute method inside T1
             |      +-- Success ----------> COMMIT T1
             |      +-- Rollback error ---> ROLLBACK T1
             |
             +-- YES, manager supports JDBC savepoints
                    |
                    +-- Create SAVEPOINT S1 inside T1
                    +-- Run method body inside T1
                    +-- Success -> complete S1 scope
                    +-- Rollback error -> ROLLBACK TO S1
                    +-- Outer still decides COMMIT/ROLLBACK T1
~~~

Do not interpret `NESTED` as "always has a child transaction T2." It only creates a **new physical transaction when an existing transaction is absent**; when joining an outer transaction, it is primarily a **savepoint inside the same T1**, unlike `REQUIRES_NEW`.

### Why Can't You Roll Back to an Outer's Savepoint Without an Outer?

A savepoint must belong to a transaction. If T1 does not exist yet, there is no "before entering inner" position inside T1 to revert to. Instead of creating an imaginary savepoint, Spring **starts a new T1**, and rolls back all of T1 if the method fails.

This explains why the same annotation produces two observable semantics:

- Standalone `NESTED`: `isNewTransaction() = true` and `hasSavepoint() = false`.
- `NESTED` joining JDBC outer: `isNewTransaction() = false` and `hasSavepoint() = true`.

The values above are for a **DataSourceTransactionManager-style JDBC transaction manager** in this lab, not a guarantee for every custom transaction manager.

## 3. Comparing Propagations When No Outer Exists

| Propagation | When **no** outer transaction exists | When an outer transaction **already exists** |
| --- | --- | --- |
| `REQUIRED` | Starts a new transaction | Joins existing transaction; typically does not create a new savepoint |
| **`NESTED`** | **Starts a new transaction**, no savepoint needed | Same physical transaction, with savepoint if supported |
| `REQUIRES_NEW` | Starts a new transaction | Suspends outer and creates an **independent** transaction |
| `MANDATORY` | Throws error because no transaction exists | Joins existing transaction |
| `SUPPORTS` | Does not require starting a new transaction | Joins existing transaction |
| `NOT_SUPPORTED` | Runs without a transaction | Suspends outer and runs non-transactionally when supported |

When **no outer exists**, `REQUIRED`, `NESTED`, and `REQUIRES_NEW` can all **start a new transaction**. Therefore, a test that only checks "is there a transaction or not" cannot tell the three apart. To observe the difference, you must test **with an outer** and inspect savepoint/independent commit behavior.

Key differences when **outer exists**:

1. **`REQUIRED`** inner failing and requesting rollback can mark the **shared transaction rollback-only**. Outer catching the exception may still hit `UnexpectedRollbackException` when trying to commit.
2. **`NESTED`** inner has a savepoint; if an error matching rollback rules occurs and rolling back to the savepoint succeeds, outer can **continue and commit** the remaining valid work.
3. **`REQUIRES_NEW`** inner is a different transaction T2. Once T2 commits, outer T1 rolling back **does not automatically undo T2**; however, using another connection, locks, and pool capacity must be weighed.

Do not automatically replace `NESTED` with `REQUIRES_NEW` when encountering an unsupported-savepoint error. The two options differ in **data invariants**.

## 4. Testing with Two Accounts: Without Outer vs. With Outer

Suppose table `account_balance` contains:

| Account | id | Initial amount |
| --- | ---: | ---: |
| A | 1 | 100 |
| B | 2 | 200 |

Method invoked through proxy:

~~~java
@Transactional(propagation = Propagation.NESTED)
public void add(long id, long delta, boolean fail) {
    // UPDATE amount = amount + delta
    // If fail, throw IllegalStateException.
}
~~~

This is an API-explaining snippet, not a standalone runnable class; the full runnable project appears in section 6.

### Case A — Calling NESTED Twice When the Caller Is Non-Transactional

~~~text
NonTransactionalCoordinator.runTwoSteps()
    |
    +-- nested.add(A,+10,false)
    |     no outer -> OPEN T1 -> COMMIT T1
    |     A is already saved as 110
    |
    +-- nested.add(B,+10,true)
          still no outer -> OPEN T2
          B temporarily becomes 210
          throws RuntimeException -> ROLLBACK all of T2
          B returns to 200

Values after caller receives exception:
A = 110, B = 200
~~~

This is a critical consequence: **two consecutive NESTED method calls do not automatically form an "invisible parent transaction."** The first method already committed before the second method started. If the workflow requires both steps to succeed or fail together, you need a service facade with `@Transactional` wrapping both steps.

### Case B — Calling NESTED Inside an Outer @Transactional

~~~text
OuterService.absorbNestedErrorAndCommit()
    |
    +-- OPEN T1
    +-- UPDATE A +10  (A is 110 in T1)
    |
    +-- nested.add(B,+10,true)
    |     NESTED with outer -> SAVEPOINT S1 in T1
    |     UPDATE B +10  (B temporarily 210)
    |     throw IllegalStateException
    |     ROLLBACK TO S1  (B reverts to 200)
    |
    +-- Outer catches the expected test exception
    +-- UPDATE A +10  (A is 120 in T1)
    +-- COMMIT T1

Persisted values: A = 120, B = 200
~~~

Here, the savepoint only undoes inner's update to B; outer's operations before and after are still committed provided all other constraints allow.

### Case C — Inner Completes Normally, Outer Fails

~~~text
OUTER T1:
  UPDATE A +10
  NESTED creates S1
  INNER: UPDATE B +10 succeeds
  Inner returns normally (NO separate physical commit)
  OUTER throws RuntimeException
  ROLLBACK all of T1

Persisted values: A = 100, B = 200
~~~

When outer exists, a "successful" NESTED inner only means it has not rolled back within the inner scope. It **cannot keep its result when outer rolls back**.

## 5. Measuring Transaction Status Instead of Guessing from Annotations

Spring provides `TransactionAspectSupport.currentTransactionStatus()` within the active transaction interceptor scope. Inside a method called via proxy, you can inspect:

~~~java
TransactionStatus tx =
    TransactionAspectSupport.currentTransactionStatus();

boolean newTransaction = tx.isNewTransaction();
boolean hasSavepoint = tx.hasSavepoint();
~~~

This snippet needs imports and method context; full code is below.

| Call in JDBC lab | `isNewTransaction()` | `hasSavepoint()` | Meaning |
| --- | --- | --- | --- |
| `nested.observe()` without outer | `true` | `false` | Inner itself opened the physical transaction |
| `outer.observeNestedWithinOuter()` calling `nested.observe()` | `false` | `true` | Inner joined outer's physical transaction and uses a savepoint |

You can also check `TransactionSynchronizationManager.isActualTransactionActive()`; in both cases it should report `true`. Yet `active=true` alone is not enough to prove whether a savepoint exists.

**Limitation:** `currentTransactionStatus()` must be called from an invocation currently managed by an interceptor; outside that context it can throw an error. Observed values are only meaningful when the app uses the proper transaction manager, Spring proxy, and resource. The lab does not treat `TransactionStatus` as business data to persist.

## 6. Complete Lab: Java 17, Spring Boot, JDBC, H2, JUnit

The lab uses **Spring Boot 3.5.0**, Java 17+, Spring JDBC, in-memory H2, and JUnit 5. No separate database server installation is needed. We declare **one DataSourceTransactionManager** for the same DataSource used by `JdbcTemplate`, explicitly enable `nestedTransactionAllowed`, and verify eight scenarios.

File structure:

~~~text
nested-no-outer-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/nestedlab/
    │   │   ├── NestedLabApplication.java
    │   │   ├── TxSnapshot.java
    │   │   ├── NestedService.java
    │   │   ├── OuterService.java
    │   │   └── NonTransactionalCoordinator.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/com/example/nestedlab/
            └── NestedTransactionTest.java
~~~

### 6.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>nested-no-outer-lab</artifactId>
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
</project>
~~~

### 6.2. application.properties and schema.sql

File `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:nested_no_outer_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

File `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE account_balance (
    id BIGINT PRIMARY KEY,
    amount BIGINT NOT NULL
);
~~~

Data is reset and inserted in `@BeforeEach` in the tests, so no test depends on the order of other tests. H2 is strictly an in-JVM-memory demo database.

### 6.3. NestedLabApplication.java

File `src/main/java/com/example/nestedlab/NestedLabApplication.java`:

~~~java
package com.example.nestedlab;

import javax.sql.DataSource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;

@SpringBootApplication
public class NestedLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(NestedLabApplication.class, args);
    }

    @Bean
    public PlatformTransactionManager transactionManager(
            DataSource dataSource) {
        DataSourceTransactionManager manager =
            new DataSourceTransactionManager(dataSource);
        manager.setNestedTransactionAllowed(true);
        return manager;
    }
}
~~~

Spring Boot can auto-configure a JDBC manager when conditions match, yet this lab explicitly declares **one transaction manager bean** so there is no ambiguity about nested mechanics. `DataSourceTransactionManager` implements nested via JDBC savepoints when an outer exists and the driver supports it. Setting `setNestedTransactionAllowed(true)` does not magically make an unsupported database support savepoints; the H2 database used in this lab has this capability.

`PlatformTransactionManager` here runs transactions on the same `DataSource` used by `JdbcTemplate`, so JDBC updates inside services participate in the exact transaction.

### 6.4. TxSnapshot.java

File `src/main/java/com/example/nestedlab/TxSnapshot.java`:

~~~java
package com.example.nestedlab;

public record TxSnapshot(
    boolean active,
    boolean newTransaction,
    boolean hasSavepoint
) {}
~~~

This Java 17 record captures Spring transaction context info at the moment of invocation. **Do not confuse it with a database MVCC snapshot**.

### 6.5. NestedService.java

File `src/main/java/com/example/nestedlab/NestedService.java`:

~~~java
package com.example.nestedlab;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class NestedService {
    private final JdbcTemplate jdbc;

    public NestedService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.NESTED)
    public TxSnapshot observe() {
        TransactionStatus tx =
            TransactionAspectSupport.currentTransactionStatus();
        return new TxSnapshot(
            TransactionSynchronizationManager.isActualTransactionActive(),
            tx.isNewTransaction(),
            tx.hasSavepoint()
        );
    }

    @Transactional(propagation = Propagation.NESTED)
    public void add(long id, long delta, boolean failAfterUpdate) {
        int affected = jdbc.update(
            "UPDATE account_balance SET amount = amount + ? WHERE id = ?",
            delta, id
        );
        if (affected != 1) {
            throw new IllegalStateException("Missing account " + id);
        }
        if (failAfterUpdate) {
            throw new IllegalStateException("nested deliberate failure");
        }
    }
}
~~~

The update executes **before** deliberately throwing the error. Thus rollback genuinely has to undo an intermediate modified value, rather than merely testing a Java error before any SQL ran.

- Without outer: `observe()` yields `active=true`, `newTransaction=true`, `hasSavepoint=false`. Successful `add(...)` commits a new transaction; throwing a runtime exception rolls back that entire transaction.
- With outer: `observe()` yields `active=true`, `newTransaction=false`, `hasSavepoint=true`. Failed `add(...)` rolls back to the savepoint when the driver allows continuing, so outer can decide the next step.

### 6.6. OuterService.java

File `src/main/java/com/example/nestedlab/OuterService.java`:

~~~java
package com.example.nestedlab;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final NestedService nested;
    private final JdbcTemplate jdbc;

    public OuterService(NestedService nested, JdbcTemplate jdbc) {
        this.nested = nested;
        this.jdbc = jdbc;
    }

    @Transactional
    public TxSnapshot observeNestedWithinOuter() {
        return nested.observe();
    }

    @Transactional
    public void absorbNestedErrorAndCommit() {
        addToA(10L);

        try {
            nested.add(2L, 10L, true);
        } catch (IllegalStateException ex) {
            if (!"nested deliberate failure".equals(ex.getMessage())) {
                throw ex;
            }
            // Inner rolled back to savepoint; outer continues.
        }

        addToA(10L);
    }

    @Transactional
    public void bothSuccessful() {
        addToA(10L);
        nested.add(2L, 10L, false);
    }

    @Transactional
    public void failAfterNestedSuccess() {
        addToA(10L);
        nested.add(2L, 10L, false);
        throw new IllegalStateException("outer deliberate failure");
    }

    private void addToA(long delta) {
        int affected = jdbc.update(
            "UPDATE account_balance SET amount = amount + ? WHERE id = ?",
            delta, 1L
        );
        if (affected != 1) {
            throw new IllegalStateException("Account A missing");
        }
    }
}
~~~

`NestedService` and `OuterService` are two distinct beans, so calls to `nested.observe()`/`nested.add(...)` pass **through the Spring proxy**, not `this.method()` self-invocation.

- `absorbNestedErrorAndCommit()`: A increases twice in the outer transaction, B is updated in the nested scope and rolled back to the savepoint on exception, and outer can commit A=120, B=200.
- `bothSuccessful()`: outer A+10, nested B+10, outer commits both; A=110, B=210.
- `failAfterNestedSuccess()`: inner B+10 completes normally yet does not commit independently, outer throws an error and rolls back the entire transaction; A=100, B=200.

**Do not catch and swallow all database exceptions in production.** The lab catches only the exact Java error deliberately inserted after a valid UPDATE, so the connection/transaction remains safe to use.

### 6.7. NonTransactionalCoordinator.java

File `src/main/java/com/example/nestedlab/NonTransactionalCoordinator.java`:

~~~java
package com.example.nestedlab;

import org.springframework.stereotype.Service;

@Service
public class NonTransactionalCoordinator {
    private final NestedService nested;

    public NonTransactionalCoordinator(NestedService nested) {
        this.nested = nested;
    }

    // No @Transactional on coordinator.
    public void runTwoSteps() {
        nested.add(1L, 10L, false); // T1 opens on its own, commits.
        nested.add(2L, 10L, true);  // T2 opens on its own, rolls back.
    }
}
~~~

This is a counterexample: even though both `add(...)` methods carry the NESTED annotation, **there is no outer transaction** enclosing all of `runTwoSteps()`. The first step already committed before the second step failed. After the error, A stays 110 and B returns to 200.

### 6.8. NestedTransactionTest.java — Eight Checks

File `src/test/java/com/example/nestedlab/NestedTransactionTest.java`:

~~~java
package com.example.nestedlab;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class NestedTransactionTest {
    @Autowired
    private NestedService nested;

    @Autowired
    private OuterService outer;

    @Autowired
    private NonTransactionalCoordinator nonTx;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM account_balance");
        jdbc.update(
            "INSERT INTO account_balance(id, amount) VALUES (?, ?)",
            1L, 100L
        );
        jdbc.update(
            "INSERT INTO account_balance(id, amount) VALUES (?, ?)",
            2L, 200L
        );
    }

    private long amount(long id) {
        Long value = jdbc.queryForObject(
            "SELECT amount FROM account_balance WHERE id = ?",
            Long.class, id
        );
        if (value == null) {
            throw new AssertionError("Missing account " + id);
        }
        return value;
    }

    @Test
    void withoutOuterNestedStartsNewTransactionNotSavepoint() {
        TxSnapshot s = nested.observe();

        assertTrue(s.active());
        assertTrue(s.newTransaction());
        assertFalse(s.hasSavepoint());
    }

    @Test
    void withOuterNestedCreatesSavepointNotPhysicalTransaction() {
        TxSnapshot s = outer.observeNestedWithinOuter();

        assertTrue(s.active());
        assertFalse(s.newTransaction());
        assertTrue(s.hasSavepoint());
    }

    @Test
    void standaloneNestedSuccessCommits() {
        nested.add(1L, 10L, false);

        assertEquals(110L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void standaloneNestedFailureRollsBackWholeTransaction() {
        assertThrows(
            IllegalStateException.class,
            () -> nested.add(1L, 10L, true)
        );

        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void consecutiveStandaloneNestedCallsAreNotOneTransaction() {
        assertThrows(
            IllegalStateException.class,
            nonTx::runTwoSteps
        );

        assertEquals(110L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void nestedFailureRollsBackToSavepointOuterStillCommits() {
        outer.absorbNestedErrorAndCommit();

        assertEquals(120L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void nestedSuccessDoesNotSurviveOuterRollback() {
        assertThrows(
            IllegalStateException.class,
            outer::failAfterNestedSuccess
        );

        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void nestedAndOuterSuccessCommitTogether() {
        outer.bothSuccessful();

        assertEquals(110L, amount(1L));
        assertEquals(210L, amount(2L));
    }
}
~~~

**Why is the test not annotated with `@Transactional`?** Spring Test can open a transaction enclosing the test. In that case `nested.observe()` would **already have the test's outer transaction**, making savepoint results completely different from the "no outer" condition we need to study. This test suite has no outer test transaction; data is reset in `@BeforeEach` via JDBC before each test.

The assertions verify **persisted values after the service proxy finishes**, not just exceptions. The first two tests read `TransactionStatus` directly while the NESTED method is being intercepted.

## 7. Running Tests and Expected Results Table

From the `nested-no-outer-lab` directory, you need JDK 17+, Maven, and dependencies:

~~~bash
java -version
mvn -version
mvn test
~~~

If the project includes the Maven Wrapper, you can run `./mvnw test` (Linux/macOS) or `.\mvnw.cmd test` (Windows PowerShell). With the compatible source and H2 setup above, the **expected** result is **8 tests passing, 0 failures, 0 errors**. This is a code-based prediction, not the log of an executed run; Maven output and test execution order are not fixed.

| Test | Result | Takeaway |
| --- | --- | --- |
| `withoutOuterNestedStartsNewTransactionNotSavepoint` | active=true, newTransaction=true, hasSavepoint=false | NESTED without outer opens a new physical transaction |
| `withOuterNestedCreatesSavepointNotPhysicalTransaction` | active=true, newTransaction=false, hasSavepoint=true | NESTED with outer uses a savepoint |
| `standaloneNestedSuccessCommits` | A=110, B=200 | Standalone method owns commit |
| `standaloneNestedFailureRollsBackWholeTransaction` | A=100, B=200 | Standalone method rolls back its entire transaction |
| `consecutiveStandaloneNestedCallsAreNotOneTransaction` | A=110, B=200 | Two standalone calls are not atomic with each other |
| `nestedFailureRollsBackToSavepointOuterStillCommits` | A=120, B=200 | Inner rolls back locally, outer still commits |
| `nestedSuccessDoesNotSurviveOuterRollback` | A=100, B=200 | Inner does not commit independently |
| `nestedAndOuterSuccessCommitTogether` | A=110, B=210 | Outer commits whole transaction including inner |

**Focus on the first two tests:** the exact same `NESTED` annotation has `hasSavepoint()` false and `isNewTransaction()` true when no outer exists; when outer exists, they flip. That is the proof distinguishing starting a new transaction from creating a savepoint in an existing transaction.

## 8. Limitations and Common Pitfalls

### 8.1. Not Every Manager Supports Nested Transactions

`DataSourceTransactionManager` with JDBC savepoints fits this lab. H2 supports JDBC savepoints; real projects must check their manager and `Connection.getMetaData().supportsSavepoints()` when needed.

- `JpaTransactionManager` manages a JPA persistence context, and JDBC savepoint support does not mean the entire JPA object graph state rolls back synchronously. Do not infer that `NESTED` works across every JPA provider.
- `JtaTransactionManager` may not support `NESTED` in the JDBC-savepoint sense.
- Enabling `nestedTransactionAllowed` in Spring does not create a capability that the driver/database does not support.
- When **no outer exists**, the deciding factor is whether the manager can start a new physical transaction, not a savepoint of a nonexistent outer.

When the manager does not support nested with an outer, Spring may throw `NestedTransactionNotSupportedException`. Report the error and fix the design/configuration; do not blindly switch `NESTED` to `REQUIRES_NEW` if atomicity with outer must be preserved.

### 8.2. NESTED Does Not Create an Independent Commit Like REQUIRES_NEW

A savepoint still belongs to one physical transaction. If outer rolls back, it can discard all uncommitted changes including an inner NESTED that succeeded. `REQUIRES_NEW`, on the other hand, has an independent commit/rollback and may require a separate connection, risking connection pool exhaustion or lock contention.

Choose `NESTED` when you want **one overall transaction** with local rollback capability where appropriate; choose `REQUIRES_NEW` when you truly want an **independent transaction** and accept the consequence that it does not roll back with outer.

### 8.3. Transaction Manager Does Not See Outer Due to Different Thread/Resource

Imperative JDBC transactions are usually thread-bound. If outer creates a transaction and invokes inner on another thread via `@Async`/executor, inner may not see the outer transaction and will open a new one — even if humans consider it "inside outer" in the business flow. Likewise, two different `DataSource`s/transaction managers do not automatically share a physical transaction and savepoint.

When debugging, check the manager, connection resource, thread, and proxy path. Do not claim "NESTED saw outer" solely from a method call arrow in an architecture diagram.

### 8.4. Self-Invocation Bypasses the NESTED Annotation

In standard Spring AOP proxy mode, `this.someNestedMethod()` from the same target bypasses the proxy and the transaction interceptor creates no separate transaction/savepoint. Without an outer, code may run non-transactionally; with an outer, SQL still belongs to outer yet has no inner savepoint from the annotation.

The fix is clear service boundaries, calling a Spring bean through its proxy (the lab injects another bean). Do not automatically add AspectJ weaving just to work around internal-call design.

### 8.5. Exception Type Determines Rollback

In the lab, `IllegalStateException` is a `RuntimeException`; Spring rolls back by default. If inner NESTED throws a checked `IOException` without a rollback rule, Spring may **not roll back** on that exception alone.

Example configuration when a checked exception must roll back:

~~~java
@Transactional(
    propagation = Propagation.NESTED,
    rollbackFor = java.io.IOException.class
)
public void importRecords() throws java.io.IOException {
    // Illustrative snippet, not a standalone class.
}
~~~

Without an outer, it rolls back the entire new transaction. With an outer, it rolls back to the savepoint if supported; an exception continuing through the outer proxy can also trigger the outer's rollback rules.

### 8.6. Not Every Database Error Lets Outer Continue Safely

The lab injects a Java error **after a successful UPDATE**; the connection and transaction can still continue after rolling back to the savepoint. A severe JDBC error, lost connection, or inconsistent ORM persistence context can leave outer unable to commit safely. In production, classify errors and proactively roll back/retry the whole transaction when safe continuation is impossible.

### 8.7. Do Not Confuse a Transactional Test with a Real Outer Transaction

If the test class has `@Transactional`, the Spring Test framework can create an enclosing transaction and roll it back after the test. Then a "standalone NESTED" test is no longer standalone, distorting the target observation. To test real commits/rollbacks, avoid accidental test-level transactions and **read the database after the proxy call completes**.

### 8.8. Do Not Use Savepoints to Dodge Business Constraints

Even though inner can roll back locally, not every business error should be swallowed so outer can commit. If outer and inner together form an invariant requiring atomicity, let the error roll back the entire transaction. `NESTED` is only helpful when the business **genuinely permits** dropping a secondary step while keeping the primary step.

## 9. Diagnostic Procedure

When a NESTED method does not behave as expected:

1. Check whether an **outer transaction actually exists at the moment of invocation**; do not overlook test transactions and thread-locals.
2. Check whether the caller goes through a **Spring proxy** or uses self-invocation, `new`, or an annotation on a non-intercepted method.
3. Confirm the active transaction manager is capable of creating transactions and supporting nested JDBC when an outer exists.
4. Observe `TransactionAspectSupport.currentTransactionStatus()`: `isNewTransaction()`, `hasSavepoint()`, and `TransactionSynchronizationManager.isActualTransactionActive()`.
5. Trigger the error **after an UPDATE** and measure data after completion. Errors before any SQL do not prove actual rollback.
6. Distinguish `NESTED` and `REQUIRES_NEW`: savepoints have no independent commit; independent transactions do.
7. Review rollback rules for both inner and outer; where is the exception caught, which interceptors did it exit, and is the resource still committable?
8. When multiple steps must be atomic, check whether the **outer service has `@Transactional`** and uses the same manager/resource.

## 10. Self-Check

1. **Does calling NESTED via proxy without an outer throw an error?** — Not merely for lacking an outer; a compatible manager starts a new physical transaction.
2. **Without an outer, where is the savepoint?** — No savepoint is nested inside an old transaction; in the lab `hasSavepoint=false`, `isNewTransaction=true`.
3. **Does standalone NESTED commit upon success?** — Yes, if it owns the new transaction and there is no other rollback trigger.
4. **What happens if standalone NESTED throws a RuntimeException after an UPDATE?** — It rolls back the entire physical transaction it just opened.
5. **Are two NESTED calls from a non-transactional coordinator atomic with each other?** — No; an already-committed call is not rolled back by a later call's failure.
6. **With an outer, does a successful inner NESTED commit durably right away?** — No; outer retains final commit authority.
7. **With an outer, can a failing inner NESTED roll back only itself?** — Yes, if savepoints are supported and database state permits outer to continue.
8. **What happens if outer rolls back after nested success?** — Inner's uncommitted changes still roll back together with outer.
9. **How does NESTED differ from MANDATORY when no outer exists?** — NESTED starts a transaction; MANDATORY reports a missing transaction.
10. **Why not put `@Transactional` on the test?** — To avoid accidentally creating an outer transaction that alters the exact condition being observed.
11. **What is the key difference between a savepoint and REQUIRES_NEW?** — A savepoint shares the physical transaction with no independent commit; REQUIRES_NEW is an independent physical transaction.
12. **Does calling `this.nestedMethod()` automatically create a savepoint?** — Normally no in proxy mode.

## 11. Extended Exercises

**Exercise A:** Add `@Transactional` onto `NonTransactionalCoordinator.runTwoSteps()` and re-run the A=110/B=200 test. Now the nested calls see an outer transaction. When the exception is uncaught and exits the outer interceptor, predict A=100/B=200 due to rolling back the whole outer. Explain why adding a transaction on the coordinator changes atomicity.

**Exercise B:** Change one NESTED method to REQUIRED to test the difference **when an outer exists**. If inner REQUIRED throws RuntimeException, the shared transaction can be marked rollback-only; outer catching the error may still fail to commit. State the difference compared to NESTED savepoint rollback.

**Exercise C:** Try `Propagation.MANDATORY` on a method called when no outer exists. Expect Spring to throw `IllegalTransactionStateException`. Compare the result with standalone NESTED.

**Exercise D:** Change NESTED to REQUIRES_NEW in a copy of the lab, having inner/outer update two different rows to avoid lock waits. After inner commits and outer rolls back, check whether B retains its change. That is the counterproof against calling a savepoint an independent transaction.

**Exercise E:** Use a checked `IOException` instead of `IllegalStateException` after the UPDATE; test default behavior and then add `rollbackFor = IOException.class`. Do not guess rollback behavior just from Java throwing an exception.

## 12. Conclusion

**NESTED without an outer** means Spring **starts a new transaction**; it does not create a savepoint inside a nonexistent transaction. **NESTED with an outer** reveals the main purpose of savepoints: local rollback within the same physical transaction while leaving final commit control with outer.

To design transactions accurately, always evaluate **(1) existing transaction, (2) propagation, (3) proxy boundaries, (4) transaction manager/driver, (5) rollback rules**. That combination — not the word `NESTED` alone — determines which data is committed or undone.

### Official References

- [Spring Framework — Transaction Propagation, including PROPAGATION_NESTED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — @Transactional Settings](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — DataSourceTransactionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html)
- [Spring Framework — AbstractPlatformTransactionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Spring Framework — Declarative Rollback Rules](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)