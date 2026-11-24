# Inner Method Attributes May Not Override Outer Configuration

## 1. The problem: why does the inner method's annotation not behave as expected?

When services in Spring Framework call one another, a method that has already opened a transaction may call another method that also has `@Transactional`. Spring does not close the old transaction and create a new one with new attributes merely because it encounters another annotation. **Propagation** determines whether the inner method **joins an existing transaction or opens an independent transaction**.

Example:

~~~java
@Service
class OrderService {
    private final InventoryService inventory;

    OrderService(InventoryService inventory) {
        this.inventory = inventory;
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.SERIALIZABLE,
        readOnly = false,
        timeout = 30
    )
    public void placeOrder() {
        inventory.reserve();
    }
}

@Service
class InventoryService {
    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        readOnly = true,
        timeout = 1
    )
    public void reserve() {
        // Belongs to the same physical transaction opened by placeOrder().
    }
}
~~~

The code above **only illustrates the idea**, not a standalone project (imports and business logic have been omitted). A runnable lab is in section 5.

If `placeOrder()` is called by a caller **through a Spring proxy** and opens a new transaction, and `reserve()` is also called through the `InventoryService` bean's proxy:

- Outer opens a **physical transaction** with isolation `SERIALIZABLE`, read-only `false`, and a 30-second timeout (subject to manager/driver support).
- Inner declares `REQUIRED`, so it **joins** the existing physical transaction. It creates a *logical transaction scope* but **does not open a new physical transaction**.
- By default, Spring's lenient transaction manager **retains the isolation, timeout, and read-only of the outer transaction**, without letting inner attributes replace them on the same physical transaction.
- When inner returns normally, the transaction has not necessarily committed: outer is where the physical transaction for the whole business operation completes.

This does not mean all inner metadata is ineffective: inner's **rollback rules** can still affect the shared rollback-only state. You must separate **physical transaction characteristics** from **logical scope handling rules**.

### First matrix

| Call pattern | Outer state | Inner propagation | Which attributes apply to the actual transaction? |
| --- | --- | --- | --- |
| Call inner through proxy when no transaction exists | None | `REQUIRED` | Inner opens a new transaction, using its own isolation/readOnly/timeout when supported. |
| Outer opens transaction, then calls inner through proxy | Already active | `REQUIRED` | Inner joins outer's transaction; physical parameters remain outer's by default. |
| Outer opens transaction, then calls inner through proxy | Already active | `REQUIRES_NEW` | Inner opens an independent physical transaction, and can use its own parameters. |
| Inner method called via `this.inner()` | Active or not | Annotation may be `REQUIRED` or `REQUIRES_NEW` | **Self-invocation** in proxy mode typically bypasses inner's transaction interceptor. |

The three most important debugging questions are: **is a transaction already active?**, **what is the propagation?**, and **does the call pass through a proxy?**

## 2. Logical scope and physical transaction

Spring distinguishes:

- **Physical transaction:** the actual transaction on the resource/database, with a `BEGIN` or equivalent mechanism, managing the JDBC connection, isolation, commit/rollback, and lifecycle.
- **Logical transaction scope:** the advice scope of a transactional method passing through the interceptor. A scope has its own rollback rules, yet can share a physical transaction with other scopes.
- **Transaction owner:** the scope that starts the physical transaction and is responsible for completing commit/rollback at the outermost boundary of that transaction.

Diagram for `REQUIRED`:

~~~text
Caller
  |
  v
OuterService proxy
  |
  +-- OUTER logical transaction
  |      |
  |      +-- OPENS physical transaction T1
  |      |   isolation=SERIALIZABLE
  |      |   readOnly=false
  |      |   timeout=30
  |      |
  |      +-- outerBusinessMethod()
  |             |
  |             v
  |        InnerService proxy
  |             |
  |             +-- INNER logical transaction REQUIRED
  |             |   joins T1, no T2
  |             |
  |             +-- innerBusinessMethod()
  |                   executes SQL on T1
  |
  +-- OUTER completes T1: commit or rollback
~~~

**Each method can create a logical scope** without necessarily creating a separate database transaction. If both belong to T1, you cannot say "inner committed" just because the inner method returned normally.

### Annotation precedence does not mean authority to alter an already open transaction

When Spring resolves annotations, `@Transactional` settings placed **directly on a method** generally take precedence over settings attached to that class. Example:

~~~java
@Transactional(readOnly = true)
public class ExampleService {
    @Transactional(readOnly = false)
    public void update() {
        // Method-level metadata takes precedence over class-level metadata.
    }
}
~~~

This is an illustrative snippet, not a complete file. **Metadata resolution** happens when Spring determines the transactional attributes for a call. **Joining an existing transaction** is a separate step. `readOnly=false` on the method can be selected properly and still fail to change the read-only state of a physical transaction previously created by an outer method on another bean.

## 3. Attributes to distinguish

### 3.1. isolation

If outer is `SERIALIZABLE` and inner is `REQUIRED(READ_COMMITTED)`, inner normally runs at T1's **SERIALIZABLE** isolation. Inner's isolation attribute cannot automatically downgrade or upgrade the isolation of an active physical transaction.

Conversely, if there is no T1 and inner `REQUIRED` opens a transaction itself, the database/manager can apply `READ_COMMITTED`. With `REQUIRES_NEW`, inner opens a new transaction T2 with its own isolation.

Isolation levels represent database concurrency guarantees. Details of snapshot, lock, and conflict handling can differ between PostgreSQL, MySQL/InnoDB, H2, and other engines.

### 3.2. readOnly

`readOnly=true` is an attribute/hint for the transaction manager, JDBC driver, or ORM; it can optimize flushing, pass a hint to the connection, or enforce constraints depending on configuration. **Do not treat it as a security authorization mechanism** or a guarantee that every database forbids `UPDATE`.

An inner `REQUIRED(readOnly=true)` joining a read-write outer usually **does not convert** T1 into read-only. Conversely, a writing inner cannot automatically "re-enable" read-write if outer opened read-only and the manager/engine forbids it.

### 3.3. timeout

`timeout` applies when **creating a new physical transaction**. Inner `REQUIRED(timeout=1)` joining outer `timeout=30` does not mean T1's deadline is reset to one second. Spring's transaction timeout is also not a timer that arbitrarily interrupts a Java thread at the exact second: its effect depends on how the transaction manager, JDBC/ORM, and driver enforce the limit.

Need a network timeout or a separate business deadline? Design it at the relevant layer instead of expecting an inner method to alter the outer transaction timeout.

### 3.4. propagation

- `REQUIRED`: uses the existing transaction or opens a new one.
- `REQUIRES_NEW`: opens a new physical transaction, suspending the outer transaction when supported by the manager; inner can commit/roll back independently.
- `NESTED`: typically creates a JDBC savepoint within the **same physical transaction** if supported by the manager; not an independent commit like `REQUIRES_NEW`.
- `SUPPORTS`: joins a transaction if present, does not force creating a transaction if absent; do not infer from a `SUPPORTS` annotation that a commit boundary always exists.

`REQUIRES_NEW` can break overall atomicity: an inner transaction that has committed will not be rolled back just because outer later fails. It also requires sufficient resources/connections and can easily hit lock waits if inner writes to rows outer still holds locks on.

### 3.5. rollback rules: the part inner *can* still affect

When inner `REQUIRED` has `@Transactional(rollbackFor = IOException.class)`, if an `IOException` escapes through the **inner proxy**, the advice can mark transaction T1 as **rollback-only**. Outer catching the exception and returning normally **cannot clear this mark**. When outer attempts to commit, Spring typically rolls back and reports `UnexpectedRollbackException`.

Conversely, inner `@Transactional(noRollbackFor = BusinessNotice.class)` does not request rollback solely for that exception. If outer catches the exception and finishes normally, T1 can commit. However, if that unchecked exception still escapes through the outer proxy, **outer's** rollback rule can trigger a rollback.

Therefore, saying "inner's isolation, timeout, and readOnly do not override outer" is accurate when joining T1; saying "all inner attributes are ignored" is **false**.

## 4. Summary table by transaction boundary

| Scenario | Physical transaction | What decides commit/rollback? |
| --- | --- | --- |
| Inner `REQUIRED` without outer | T1 opened by inner | Inner proxy decides completion of T1. |
| Outer T1 calls inner `REQUIRED` | Same T1 | Outer completes it; inner can set rollback-only. |
| Outer T1 calls inner `REQUIRES_NEW` | Outer T1 suspended; independent inner T2 | T2 commits/rolls back separately; T1 resumes afterward. |
| Outer T1 calls inner `NESTED` when supported | Same T1, with savepoint | Can roll back inner scope to savepoint; physical commit belongs to T1. |
| Inner called via `this.inner()` | No inner interceptor triggered | Inner annotation may not be applied; only the existing transaction scope applies. |

The next section turns these statements into tests that **actually read the database** and observe live transaction metadata.

## 5. Complete lab: Java 17 + Spring Boot + JDBC + H2

This hands-on lab uses **Spring Boot 3.5.0**, Spring JDBC, in-memory H2, and JUnit 5. Two separate beans `OuterService`/`InnerService` ensure inner calls pass through the Spring proxy; `SelfCallService` demonstrates the proxy-bypass case.

### 5.1. Project structure

~~~text
tx-scope-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/txscope/
    │   │   ├── TxScopeApplication.java
    │   │   ├── TxView.java
    │   │   ├── InnerService.java
    │   │   ├── OuterService.java
    │   │   └── SelfCallService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/com/example/txscope/
            └── TxScopeTest.java
~~~

### 5.2. pom.xml

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
    <artifactId>tx-scope-lab</artifactId>
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

`spring-boot-starter-jdbc` provides `JdbcTemplate` and the transaction infrastructure; Spring Boot configures a JDBC transaction manager for an appropriate `DataSource`. `spring-boot-starter-test` provides JUnit 5 and `@SpringBootTest`. The lab does not enable strict validation mode.

### 5.3. application.properties and schema.sql

File `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:tx_scope_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

File `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE tx_scope_balance (
    id BIGINT PRIMARY KEY,
    amount BIGINT NOT NULL
);
~~~

H2 runs inside JVM memory and requires no separate database server. Each test inserts its own data for A (id=1, amount=100) and B (id=2, amount=200). This table is only illustrative data, not a real financial model.

### 5.4. TxScopeApplication.java and TxView.java

File `src/main/java/com/example/txscope/TxScopeApplication.java`:

~~~java
package com.example.txscope;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TxScopeApplication {
    public static void main(String[] args) {
        SpringApplication.run(TxScopeApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/txscope/TxView.java`:

~~~java
package com.example.txscope;

public record TxView(
    boolean active,
    Integer isolation,
    boolean readOnly
) {}
~~~

`TxView` returns information from `TransactionSynchronizationManager`. This is transaction metadata held by Spring on the thread, **not an MVCC snapshot**, and it does not verify how the database engine enforces every detail of isolation/read-only. We deliberately do not measure timeout by sleeping a Java thread for one second, because that is not a valid test for a JDBC transaction timeout.

### 5.5. InnerService.java

File `src/main/java/com/example/txscope/InnerService.java`:

~~~java
package com.example.txscope;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        readOnly = true,
        timeout = 1
    )
    public TxView inspect() {
        return new TxView(
            TransactionSynchronizationManager.isActualTransactionActive(),
            TransactionSynchronizationManager.getCurrentTransactionIsolationLevel(),
            TransactionSynchronizationManager.isCurrentTransactionReadOnly()
        );
    }

    @Transactional(rollbackFor = IOException.class)
    public void updateThenFailChecked(long id) throws IOException {
        increase(id);
        throw new IOException("inner checked failure");
    }

    public static class BusinessNotice extends RuntimeException {
        public BusinessNotice(String message) {
            super(message);
        }
    }

    @Transactional(noRollbackFor = BusinessNotice.class)
    public void updateThenNotice(long id) {
        increase(id);
        throw new BusinessNotice("inner business notice");
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void updateIndependently(long id) {
        increase(id);
    }

    private void increase(long id) {
        int affected = jdbc.update(
            "UPDATE tx_scope_balance SET amount = amount + 10 WHERE id = ?",
            id
        );
        if (affected != 1) {
            throw new IllegalStateException("Missing account " + id);
        }
    }
}
~~~

Points to observe:

- `inspect()` declares isolation `READ_COMMITTED`, `readOnly=true`, and `timeout=1`. If there is **no** outer transaction, it opens a transaction itself and returns that metadata. If it joins outer T1, it observes T1's metadata.
- `updateThenFailChecked()` increases balance by 10 and then throws a **checked `IOException`**. Thanks to `rollbackFor`, inner advice requests rollback even though `IOException` does not trigger Spring rollback by default.
- `updateThenNotice()` increases balance and throws unchecked `BusinessNotice`. `noRollbackFor` tells inner not to mark rollback solely for that exception.
- `updateIndependently()` has `REQUIRES_NEW`: it opens an independent T2; it neither replaces T1's isolation nor commits T1.
- `increase()` is a private helper called within an active transaction. There is no need to put `@Transactional` on the private helper; transaction boundaries live on the public service methods.

### 5.6. OuterService.java

File `src/main/java/com/example/txscope/OuterService.java`:

~~~java
package com.example.txscope;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final InnerService inner;
    private final JdbcTemplate jdbc;

    public OuterService(InnerService inner, JdbcTemplate jdbc) {
        this.inner = inner;
        this.jdbc = jdbc;
    }

    @Transactional(
        isolation = Isolation.SERIALIZABLE,
        readOnly = false,
        timeout = 30
    )
    public TxView inspectInnerJoined() {
        return inner.inspect();
    }

    @Transactional
    public void catchCheckedButRollbackOnly() {
        increase(1L);
        try {
            inner.updateThenFailChecked(1L);
        } catch (IOException e) {
            if (!"inner checked failure".equals(e.getMessage())) {
                throw new IllegalStateException(e);
            }
            // Catch does not clear rollback-only set by inner advice.
        }
    }

    @Transactional
    public void catchNoticeAndCommit() {
        increase(1L);
        try {
            inner.updateThenNotice(1L);
        } catch (InnerService.BusinessNotice expected) {
            // noRollbackFor on inner and outer completes normally.
        }
    }

    @Transactional
    public void propagateNoticeAndRollback() {
        increase(1L);
        inner.updateThenNotice(1L);
        // BusinessNotice still escapes through the outer proxy.
    }

    @Transactional
    public void outerFailsAfterIndependentCommit() {
        increase(1L);
        inner.updateIndependently(2L);
        throw new IllegalStateException("outer failure");
    }

    private void increase(long id) {
        int affected = jdbc.update(
            "UPDATE tx_scope_balance SET amount = amount + 10 WHERE id = ?",
            id
        );
        if (affected != 1) {
            throw new IllegalStateException("Missing account " + id);
        }
    }
}
~~~

`OuterService` injects `InnerService` as **another bean**, so `inner.inspect()` and the other inner calls go through the Spring-managed proxy. With `catchCheckedButRollbackOnly()`, outer catches `IOException` **after the inner interceptor already marked the shared transaction rollback-only**. Outer returns normally, yet the transaction cannot commit normally. With `catchNoticeAndCommit()`, inner's `noRollbackFor` does not mark rollback-only; outer catches the exception and finishes normally, so both balance increments commit together if no other error occurs.

`propagateNoticeAndRollback()` is a different case: outer **does not catch** `BusinessNotice`, so the unchecked exception escapes through the outer interceptor, causing a rollback per **outer's** rules despite inner having `noRollbackFor`.

In `outerFailsAfterIndependentCommit()`, outer updates A and inner `REQUIRES_NEW` updates B: inner commits separately, then outer throws an exception and rolls back. This is why `REQUIRES_NEW` is not a "trick to make inner config beat outer" for arbitrary business logic.

### 5.7. SelfCallService.java

File `src/main/java/com/example/txscope/SelfCallService.java`:

~~~java
package com.example.txscope;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class SelfCallService {
    public boolean viaThis() {
        return this.requiresNewTransaction();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public boolean requiresNewTransaction() {
        return TransactionSynchronizationManager.isActualTransactionActive();
    }
}
~~~

In a context **without an outer transaction**, calling `viaThis()` on the bean returns `false`: the `this.requiresNewTransaction()` call does not pass through the transaction proxy. Calling `requiresNewTransaction()` directly **on the Spring bean** returns `true` because the proxy opens a physical transaction. If an outer transaction already existed, `isActualTransactionActive()` could return true even when the inner annotation is bypassed; the lab avoids that context to verify self-invocation accurately.

### 5.8. TxScopeTest.java: seven integration tests

File `src/test/java/com/example/txscope/TxScopeTest.java`:

~~~java
package com.example.txscope;

import java.sql.Connection;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class TxScopeTest {
    @Autowired
    private OuterService outer;

    @Autowired
    private InnerService inner;

    @Autowired
    private SelfCallService self;

    @Autowired
    private JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("DELETE FROM tx_scope_balance");
        jdbc.update(
            "INSERT INTO tx_scope_balance(id, amount) VALUES (?, ?)",
            1L, 100L
        );
        jdbc.update(
            "INSERT INTO tx_scope_balance(id, amount) VALUES (?, ?)",
            2L, 200L
        );
    }

    private long amount(long id) {
        Long result = jdbc.queryForObject(
            "SELECT amount FROM tx_scope_balance WHERE id = ?",
            Long.class, id
        );
        if (result == null) {
            throw new AssertionError("Missing account " + id);
        }
        return result;
    }

    @Test
    void requiredInnerAloneUsesOwnAttributes() {
        TxView view = inner.inspect();

        assertTrue(view.active());
        assertEquals(
            Integer.valueOf(Connection.TRANSACTION_READ_COMMITTED),
            view.isolation()
        );
        assertTrue(view.readOnly());
    }

    @Test
    void requiredInnerJoinsAndKeepsOuterAttributes() {
        TxView view = outer.inspectInnerJoined();

        assertTrue(view.active());
        assertEquals(
            Integer.valueOf(Connection.TRANSACTION_SERIALIZABLE),
            view.isolation()
        );
        assertFalse(view.readOnly());
    }

    @Test
    void innerRollbackOnlyPreventsOuterCommit() {
        assertThrows(
            UnexpectedRollbackException.class,
            outer::catchCheckedButRollbackOnly
        );

        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void caughtNoticeWithNoRollbackForAllowsCommit() {
        outer.catchNoticeAndCommit();

        assertEquals(120L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void uncaughtNoticeStillRollsBackAtOuterBoundary() {
        assertThrows(
            InnerService.BusinessNotice.class,
            outer::propagateNoticeAndRollback
        );

        assertEquals(100L, amount(1L));
        assertEquals(200L, amount(2L));
    }

    @Test
    void requiresNewCommitsIndependentlyOfOuter() {
        assertThrows(
            IllegalStateException.class,
            outer::outerFailsAfterIndependentCommit
        );

        assertEquals(100L, amount(1L));
        assertEquals(210L, amount(2L));
    }

    @Test
    void selfInvocationDoesNotTriggerAnnotation() {
        assertFalse(self.viaThis());
        assertTrue(self.requiresNewTransaction());
    }
}
~~~

**The seven tests** verify both transaction properties and persisted values, not merely checking that annotations exist. The tests **do not place `@Transactional` on the class or methods**; if Spring Test opens an outer transaction automatically, `REQUIRED` services could join the test's transaction and get rolled back when the test ends, hiding the services' real commit/rollback outcomes.

`@BeforeEach` resets and inserts initial data outside a test transaction. Each test reads back after the service proxy finishes its transaction. `amount(1L)` runs a SELECT after the call, observing the expected committed/rolled-back values.

## 6. How to run and interpret results

Requires JDK 17+ and Maven (or the project's Maven Wrapper). In the `tx-scope-lab` directory:

~~~bash
java -version
mvn -version
mvn test
~~~

If the project was generated via Spring Initializr with Maven Wrapper, use `./mvnw test` on Linux/macOS or `.\mvnw.cmd test` on Windows PowerShell.

With the lab code and configuration, Maven Surefire is expected to report **7 tests passed, 0 failures, and 0 errors**. Execution order and system logs are not fixed.

| Test | Expected result | What it proves |
| --- | --- | --- |
| `requiredInnerAloneUsesOwnAttributes` | active=true, READ_COMMITTED, readOnly=true | When opening its own transaction, inner applies its own parameters. |
| `requiredInnerJoinsAndKeepsOuterAttributes` | active=true, SERIALIZABLE, readOnly=false | Inner `REQUIRED` does not override outer's physical transaction characteristics. |
| `innerRollbackOnlyPreventsOuterCommit` | `UnexpectedRollbackException`, A=100, B=200 | Inner with a rollback rule marks T1; outer cannot commit even after catching the checked exception. |
| `caughtNoticeWithNoRollbackForAllowsCommit` | A=120, B=200 | Inner does not mark rollback-only; outer catches the error and commits normally. |
| `uncaughtNoticeStillRollsBackAtOuterBoundary` | `BusinessNotice`, A=100, B=200 | Outer rolls back under its own rule when an unchecked exception escapes. |
| `requiresNewCommitsIndependentlyOfOuter` | Exception, A=100, B=210 | Inner `REQUIRES_NEW` commits separately before outer rolls back. |
| `selfInvocationDoesNotTriggerAnnotation` | viaThis=false; direct call=true | Proxy interception differs from calling `this.inner()`. |

### Detailed analysis of the rollback-only case

~~~text
Initially: A=100, B=200
    |
    v
OuterService.catchCheckedButRollbackOnly() opens T1
    |
    +-- Outer UPDATE A: 100 -> 110
    |
    +-- InnerService.updateThenFailChecked() REQUIRED, joins T1
    |      |
    |      +-- Inner UPDATE A: 110 -> 120
    |      +-- throw IOException
    |      +-- Inner advice has rollbackFor=IOException
    |      +-- marks T1 rollback-only
    |
    +-- Outer catch(IOException), method returns normally
    |
    v
Outer transaction interceptor attempts to commit T1
    |
    +-- Detects rollback-only
    +-- rolls back all of T1
    +-- UnexpectedRollbackException
    |
    v
Afterward: A=100, B=200
~~~

The reason is not that inner "overrode outer's isolation". **Isolation/timeout/readOnly** are properties of the physical transaction; **rollback-only** is a completion state that can be affected by participating logical scopes.

### Testing REQUIRES_NEW without lock confusion

Inner `REQUIRES_NEW` in the demo updates **row B**, while outer updates **row A**, because the outer transaction can still hold a write lock on A while the new inner transaction runs. If both wrote to the same row A, inner could wait for outer to release the lock while outer waits for inner, leading to timeout/deadlock. That does not prove `REQUIRES_NEW` is broken; it is a concurrency consequence that must be handled.

## 7. Strict check option: validateExistingTransaction

By default, many Spring transaction managers act *leniently*: an inner `REQUIRED` with a different isolation level still joins outer and keeps outer's physical isolation. When you need to catch conflicting configurations, you can enable `validateExistingTransaction` on the transaction manager:

~~~java
// Illustrates separate configuration; do not add to the lab if keeping the 7 tests.
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
    manager.setValidateExistingTransaction(true);
    return manager;
}
~~~

The configuration snippet above **does not compile standalone**: it needs a `@Configuration` class and imports for `@Bean`, `DataSource`, `PlatformTransactionManager`, and `JdbcTransactionManager`. When placed in a real project, ensure this is the exact transaction manager used by the services, without creating multiple ambiguous managers.

With strict validation:

- An inner `READ_COMMITTED` joining an outer `SERIALIZABLE` can be rejected with `IllegalTransactionStateException` due to an **isolation mismatch**.
- A **read-write** inner attempting to join a **read-only** outer can be rejected.
- A **read-only** inner joining a **read-write** outer is not necessarily rejected solely because `readOnly` differs in this direction.

**The goal of strict mode is not to let inner override an already open transaction**; it turns inconsistent configurations into visible errors so the developer fixes the transaction boundary/propagation.

## 8. Common mistakes

### 8.1. Confusing method annotation winning over class annotation with inner winning over outer

Method-level `@Transactional` takes precedence over an annotation on the **same class** when resolving metadata for that method. That does not mean a `REQUIRED` method can alter a physical transaction previously opened by an outer method. Those are two different stages.

### 8.2. Self-invocation

In Spring AOP proxy mode, `this.innerMethod()` within the same target does not pass through the interceptor. If outer already opened T1, inner code may execute on T1 yet **have no new transactional logical scope corresponding to inner's annotation**. If there is no outer transaction, such an internal call usually does not open a new transaction either. The `SelfCallService` test makes this clear.

### 8.3. Catching an exception does not clear rollback-only

Inner `REQUIRED` throwing an error matching a rollback rule can mark the shared transaction rollback-only. Outer catching and continuing does not clear that state. When outer commits, `UnexpectedRollbackException` can occur. Do not swallow the error and report success when a participant already requested rollback.

### 8.4. `noRollbackFor` on inner does not protect against outer rollback

An unchecked exception with `noRollbackFor` at the inner boundary that still **escapes through the outer boundary** can be rolled back by the outer interceptor's defaults. To understand the result, trace the exception through each proxy and each scope's rollback rules.

### 8.5. Transactions on different threads or different managers

Spring JDBC transactions normally use a thread-bound context. Calling `@Async`, an executor, or `CompletableFuture` on another thread does not automatically propagate outer's T1. Using two `DataSource`s or two `PlatformTransactionManager`s also does not guarantee all DB writes belong to the same physical transaction. Do not extrapolate the logic above when the actual resources/managers differ.

### 8.6. Connection exhaustion when using REQUIRES_NEW

The inner physical transaction typically needs its own connection while outer still holds its resource. Under high load, many concurrent requests holding outer connections while waiting for inner ones can exhaust the connection pool; Spring's documentation warns to size the pool appropriately. Use `REQUIRES_NEW` intentionally, not as a default "attribute forcing" trick.

### 8.7. Treating `readOnly` and `timeout` as absolute guarantees

`readOnly` does not replace DB permissions; `timeout` is not a tool that kills a Java thread after exactly N seconds. To check actual enforcement, rely on the transaction manager, driver, DB engine, and controlled tests.

### 8.8. Tests wrapped by Spring Test's transaction

If a test has `@Transactional`, `REQUIRED` services can join the test's transaction, and the test framework rolls back everything after the test. When the goal is to observe where the service itself commits or rolls back, avoid this test style or manage the test transaction explicitly. The lab places no transaction annotation on the test.

## 9. Scope design checklist

Before giving an inner method a new `@Transactional` set:

1. Identify **which DB operations must be atomic**: must they commit/roll back together?
2. Identify who **opens the physical transaction**: outer or inner?
3. Identify propagation: `REQUIRED` joins; `REQUIRES_NEW` creates an independent commit; `NESTED` uses a savepoint if supported.
4. Choose isolation/readOnly/timeout **at the boundary that creates the transaction**, rather than expecting inner `REQUIRED` to override them.
5. Check rollback rules at each interceptor: does an exception escape through the proxy and mark rollback-only?
6. Check for self-invocation, thread hops, the right transaction manager, and the same resource.
7. Run integration tests that **read the database back after completion**, not just checking exceptions or proxy names.
8. If conflicting configurations should be rejected, consider `setValidateExistingTransaction(true)` and write mismatch tests.

An order-placement use case usually places the transaction on `OrderService.placeOrder()` and lets repositories/services join via `REQUIRED`. If a service truly needs to record history independently even when order placement fails, `REQUIRES_NEW` can make sense, provided you accept secondary data committing while the main operation rolls back. If calling an external HTTP payment system outside the database, a local transaction cannot roll back HTTP side effects; proper idempotency/compensation is needed.

## 10. Self-check

1. Outer `SERIALIZABLE`, inner `REQUIRED READ_COMMITTED`: what is the physical isolation? — Normally still **outer's SERIALIZABLE**.
2. Outer read-write, inner `REQUIRED(readOnly=true)`: does the physical transaction change to read-only? — **No** under default behavior.
3. Inner `REQUIRED(timeout=1)` joins outer timeout=30: does it reset the deadline to 1 second? — **No**.
4. Inner `REQUIRED` called directly through proxy when no outer exists: who opens the transaction? — **Inner**, using its own parameters.
5. Inner `rollbackFor(IOException.class)` marked rollback-only, outer catches error and returns: is commit guaranteed? — **No**; `UnexpectedRollbackException` may occur.
6. Inner `noRollbackFor(BusinessNotice.class)` yet outer does not catch the error: can it roll back? — **Yes**, because outer's proxy applies its own rules.
7. Inner `REQUIRES_NEW` commits and then outer rolls back: is inner's commit automatically reversed? — **No**, it is independent.
8. Does enabling strict `validateExistingTransaction` on an isolation conflict make inner win? — **No**; it can throw `IllegalTransactionStateException`.
9. Does `this.inner()` open a separate transaction due to inner's annotation? — Usually **no**, because it bypasses the Spring proxy.
10. Why not put `@Transactional` on the test in the lab? — So the test's transaction does not mask the service's real commit/rollback behavior.

## 11. Conclusion

**Inner method attributes may not override outer configuration** when inner uses `REQUIRED` and **joins an existing physical transaction**. That is not an annotation precedence bug: the already open transaction has isolation, timeout, and read-only tied to the physical resource scope; they cannot be changed automatically simply by entering a child method.

Distinguish three layers to avoid confusion:

- **Annotation metadata:** method-level can take precedence over class-level when Spring resolves the policy for that method itself.
- **Physical transaction characteristics:** inner `REQUIRED` typically **inherits outer**; inner `REQUIRES_NEW` can use its own characteristics.
- **Logical completion rules:** rollback-only and exception handling in each interceptor can still affect the shared outcome.

### Official references

- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Transaction-bound resources](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)
- [Spring Framework — TransactionSynchronizationManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)