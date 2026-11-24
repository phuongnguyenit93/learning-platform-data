# Impact of `rollback-only` in an Inner Scope with `PROPAGATION_REQUIRED`

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish a **logical transaction** (logical transaction scope) from a **physical transaction** when both methods use `@Transactional(propagation = REQUIRED)`.
2. Explain why when an inner scope marks **rollback-only**, the outer scope cannot commit the shared physical transaction, even if the outer code catches the exception.
3. Recognize when the caller receives `UnexpectedRollbackException`, when it receives the original business exception, and when a method returns normally yet data still rolls back.
4. Distinguish `setRollbackOnly()` of the current scope, the global rollback-only flag of the shared transaction, and an exception that has passed through `TransactionInterceptor`.
5. Practice with **Java 17+, Spring Boot, JDBC, and H2**, verifying against actual data after each case finishes.
6. Know when not to choose `REQUIRES_NEW`, when `NESTED`/savepoints are suitable, and how to avoid surprises in multi-layered service design.

**Main topic:** the consequences of **rollback-only in an inner scope** when propagation is `REQUIRED`. Other propagation modes are used only for comparison, not as substitutes for understanding the shared transaction.

## 1. `REQUIRED`: Multiple Logical Scopes Yet Only One Physical Transaction

Suppose `OrderService.placeOrder()` calls `InventoryService.reserveStock()`. Both methods have `@Transactional(propagation = Propagation.REQUIRED)`. In Spring's standard transaction manager configuration:

- If the caller has no transaction, `placeOrder()` creates **physical transaction T**.
- When the call passes through `InventoryService.reserveStock()`'s **proxy**, `REQUIRED` detects that T already exists and **joins T**, without creating a second physical transaction.
- Spring still creates a **separate logical transaction scope** for `reserveStock()`. This scope can decide rollback-only on its own according to its errors/rollback rules.
- Both logical scopes share physical transaction T, the same connection, and the same final commit fate. There is no truly independent "child commit".

```text
Caller
  |
  v
OrderService proxy
  |  Logical scope OUTER: REQUIRED
  |  Begin physical transaction T
  |
  v
OrderService.placeOrder()
  |  SQL A in T
  |
  v
InventoryService proxy
  |  Logical scope INNER: REQUIRED
  |  Join physical transaction T
  |
  v
InventoryService.reserveStock()
  |  SQL B in T
  |  ERROR or setRollbackOnly()
  |
  v
INNER marks T rollback-only
  |
  v
OUTER continues, may attempt COMMIT
  |
  v
T can only ROLLBACK
```

It is the simultaneous existence of **two logical scopes** and **one physical transaction** that produces seemingly paradoxical behavior: the outer method "sees no error" or has `catch`ed the error, yet still cannot commit.

### What is the default `REQUIRED`?

Spring's `@Transactional` uses `Propagation.REQUIRED` by default. The two declarations below are equivalent in propagation:

```java
@Transactional
public void outer() {
    // ...
}
```

```java
@Transactional(propagation = Propagation.REQUIRED)
public void inner() {
    // ...
}
```

These are two standalone snippets. They only become two **actual transactional scopes** if the methods are processed by **Spring transaction advice**, typically through calls across two different beans. Merely annotating a method and calling it with `this.inner()` does not create an advised logical scope.

## 2. Who Owns the Transaction and Who Has Authority to Commit?

Distinguish three concepts:

1. **Owner / transaction originator:** the scope that started the new physical transaction T, usually the outermost `REQUIRED` when no transaction existed beforehand.
2. **Participant:** an inner `REQUIRED` scope merely joins the existing T. When it finishes normally, the manager handles completing the **logical scope**, without actually committing T's connection.
3. **Rollback-only:** a status indicating T is no longer permitted to commit. A participant can cause T to be marked rollback-only; the owner cannot "clear" that flag and commit as if nothing happened.

| Scope | When starting | When completing successfully | If marked rollback-only |
| --- | --- | --- | --- |
| Outer `REQUIRED`, creates new T | Begins physical transaction T | Attempts to commit T | Must roll back T |
| Inner `REQUIRED`, joins T | Does not open a new physical transaction | Returns control to outer; **does not commit T** | Can mark T as global rollback-only |
| Outer after inner rollback-only | Still inside T | Commit attempt detects T is not committable | Performs rollback, usually throwing `UnexpectedRollbackException` if outer did not request rollback itself |

**One physical transaction cannot simultaneously commit the outer part and roll back only the inner part** when the changes lie in the same T without a savepoint/independent transaction. With `REQUIRED`, if inner causes T to become rollback-only, outer's SQL statements before and after inner must all roll back with T.

### Local and global rollback-only

In Spring's API, a `TransactionStatus` can reflect **local rollback-only** set by the current scope, or the **global rollback-only** state of the underlying physical transaction.

- Calling `status.setRollbackOnly()` on a logical scope's status sets **local rollback-only** for that scope.
- When an inner `REQUIRED` scope joins an existing transaction and ends with a rollback request (for example, after an unchecked exception), the transaction manager by default **marks the shared physical transaction as rollback-only**. Outer may not have called `setRollbackOnly()` at all.
- When the owner attempts to commit, the manager checks the transaction status and must roll back if T has been marked uncommittable.

The term "global" here means **the state of the shared physical transaction**, not "global distributed transaction"/XA/JTA. A `DataSourceTransactionManager` using one JDBC connection and a local transaction still carries global rollback-only in the framework's terminology.

## 3. Why Does `UnexpectedRollbackException` Occur?

Consider the typical flow:

```java
// Outer service:
@Transactional
public void process() {
    saveHeader();
    try {
        innerService.saveDetailAndFail();
    } catch (IllegalStateException ex) {
        // Catch the error yet want to continue.
    }
    saveAuditRow();
}
```

```java
// Inner service is a DIFFERENT Spring bean:
@Transactional
public void saveDetailAndFail() {
    saveDetail();
    throw new IllegalStateException("Detail failed");
}
```

These two code blocks are illustrative snippets, without declaring all beans/helpers. The actual flow when called from outside through the outer proxy:

1. Outer proxy opens physical transaction T.
2. Outer writes `header` in T.
3. Inner proxy creates a `REQUIRED` logical scope and joins **that same T**.
4. Inner writes `detail`, then throws `IllegalStateException`.
5. The exception **passes through the inner `TransactionInterceptor`**; by default an unchecked exception requires rollback. The inner transaction manager cannot roll back part of T independently without rolling back outer's part, so it marks T **rollback-only** and rethrows the exception.
6. The outer method catches `IllegalStateException` and continues writing `audit` in the same T. The outer method returns normally.
7. The outer proxy attempts to commit because the method completed normally, yet T is already rollback-only. Spring rolls back all of header/detail/audit.
8. Because outer **did not intentionally request rollback** yet must not be allowed to think commit succeeded, the caller receives **`UnexpectedRollbackException`**.

```text
Outer @Transactional REQUIRED (owner of T)
   saveHeader()
   |
   +--> Inner @Transactional REQUIRED (participant in T)
   |       saveDetail()
   |       throw IllegalStateException
   |       Inner interceptor: mark T rollback-only
   |       throw IllegalStateException
   |
   catch IllegalStateException      <- exception is caught
   saveAuditRow()
   return                            <- outer method looks successful
   |
   Outer interceptor: commit(T)?
            |
            +-- T is rollback-only
                    |
                    v
               ROLLBACK T
                    |
                    v
           UnexpectedRollbackException
```

`UnexpectedRollbackException` is **deliberate behavior to preserve API correctness**: the caller must not receive a successful commit signal when the transaction actually rolled back due to another scope. This is not "Spring causing an error on its own"; it is the signal of a shared transaction vetoed by an inner scope.

### Not every rollback produces `UnexpectedRollbackException`

| Scenario | Typical outward signal | Why |
| --- | --- | --- |
| Inner throws runtime exception, outer **does not catch** | Original business exception | Outer interceptor sees the error and intentionally rolls back |
| Inner throws runtime exception, outer **catches and returns normally** | `UnexpectedRollbackException` at outer commit | Inner already marked T rollback-only; outer still tries to commit |
| Inner calls `setRollbackOnly()` itself, returns normally; outer still tries to commit | `UnexpectedRollbackException` at outer commit | No exception is needed for rollback-only to propagate to T |
| Outer calls `setRollbackOnly()` on the transaction it owns | May return normally; T rolls back as outer requested | Rollback was explicitly requested by outer, not necessarily "unexpected" |
| Error caught **before passing through any inner interceptor**, T not rollback-only | Outer can commit | Transaction advice received no failure signal and there is no rollback-only |
| Inner throws a checked exception **not matching rollback rules**, outer catches | Outer can commit | Spring defaults on 6.1 do not mark rollback-only for checked exceptions |
| Inner uses `REQUIRES_NEW`, inner rolls back, outer catches and continues | Outer can commit its own transaction | Two independent physical transactions; business semantics differ |

The outcomes above assume Spring's default transaction manager and a database/driver still operating in the described state. Serious SQL errors can leave the DB uncommittable **even if** the exception is caught.

## 4. The Rollback-Only Marking Mechanism in Spring

In the imperative JDBC/JPA model, the transaction status can be accessed via `TransactionAspectSupport.currentTransactionStatus()` **inside a call handled by Spring transaction advice**.

```java
@Transactional(propagation = Propagation.REQUIRED)
public void innerWork() {
    // Perform part of the data work participating in the current transaction.
    TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
}
```

After this call:

- The inner method can return **without throwing an exception**.
- The inner transaction scope finishes with a rollback request.
- With `REQUIRED` joining an existing T, the manager propagates the rollback-only state onto the shared T.
- Outer can keep running Java code, yet cannot commit T as a valid transaction.

Do not use `setRollbackOnly()` merely to "skip writing one extra row": it is a decision that affects the **entire physical transaction T** when sharing `REQUIRED`.

### `@Transactional` and rollback rules

By default in Spring Framework 6.1, typically paired with Spring Boot 3.3.x:

- `RuntimeException` and `Error` escaping a transactional method normally trigger rollback.
- Checked exceptions do not trigger rollback without a matching `rollbackFor`.
- You can declare `@Transactional(rollbackFor = IOException.class)` or `rollbackFor = Exception.class` to change the rule.
- You can use `noRollbackFor` for cases permitted to commit even if the exception escapes.

These are **rules applied at each advised logical scope**. If inner has already marked T rollback-only, outer cannot undo it by declaring `noRollbackFor` on outer. Outer's `noRollbackFor` governs how the **outer interceptor reacts to an exception passing through it**, and has no authority to make T committable again.

A newer Spring Framework configuration may change default rollback rules (for example, an option to roll back on all exceptions); always check the actual system's version and configuration. The demo section below pins Spring Boot 3.3.5 so expectations are clear.

## 5. Runnable Java 17+ Demo: Six Scenarios on One H2 Database

We create two independent Spring beans: **`InnerService`** and **`OuterService`**. Both use `@Transactional(propagation = REQUIRED)` and share the same `JdbcTemplate`/`DataSourceTransactionManager`. Each scenario resets the data before running so outcomes can be compared directly.

**Illustrative business domain:** two wallets `wallets(1)=1000`, `wallets(2)=500`. Inner debits 100 from wallet 1. Outer adds 10 and then adds 20 to wallet 2. If the transaction commits, the balances after the entire sequence can be `1=900, 2=530`. If T rolls back, both wallets return to `1=1000, 2=500`.

Cases:

| Scenario | What happens in inner | Outer | Transaction T outcome |
| --- | --- | --- | --- |
| 1. Inner throws runtime, outer catches | Inner interceptor marks rollback-only | Returns normally, tries to commit | Rolls back T, `UnexpectedRollbackException` |
| 2. Inner calls `setRollbackOnly()` | Inner returns normally yet marks rollback-only | Returns normally, tries to commit | Rolls back T, `UnexpectedRollbackException` |
| 3. Outer does not catch inner exception | Inner marks rollback-only and throws runtime | Exception passes through outer interceptor | Rolls back T, caller sees `IllegalStateException` |
| 4. Outer catches a local error itself | Does not call inner proxy; error swallowed in outer | Returns normally | Commits writes made in outer |
| 5. Inner throws checked `IOException` | Does not match default rollback rule | Outer catches and returns | Commits writes of both inner + outer |
| 6. No error | Inner does not participate or reports no error | Outer returns normally | Commits successfully |

### 5.1. Creating the project

Use Spring Initializr to create a Java 17+, Gradle, Spring Boot 3.3.5 project with the JDBC and H2 dependencies. Place the files at the exact paths inside that project.

Structure:

```text
required-rollback-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/
    │   ├── java/example/required/
    │   │   ├── InnerService.java
    │   │   ├── OuterService.java
    │   │   └── RequiredRollbackApplication.java
    │   └── resources/
    │       ├── application.yml
    │       └── schema.sql
    └── test/java/example/required/
        └── RequiredRollbackTest.java
```

### 5.2. `settings.gradle`

```groovy
rootProject.name = 'required-rollback-demo'
```

### 5.3. `build.gradle`

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

`spring-boot-starter-jdbc` provides `JdbcTemplate` and JDBC transaction infrastructure; H2 is an in-memory database. When Spring Boot configures the `DataSource` and transaction manager, both services use the same `DataSource` and thus join the same physical transaction when the inner method has `REQUIRED`.

### 5.4. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:required_scope_demo;DB_CLOSE_DELAY=-1"
    driver-class-name: org.h2.Driver
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

The application runs in CLI mode, requiring no web server. `spring.sql.init.mode=always` runs `schema.sql` at startup. H2 is for demonstration; in production you must use an appropriate DBMS and schema migration.

### 5.5. `src/main/resources/schema.sql`

```sql
CREATE TABLE wallets (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

INSERT INTO wallets (id, balance) VALUES (1, 1000);
INSERT INTO wallets (id, balance) VALUES (2, 500);
```

The `balance` column and `CHECK` constraint represent real data, allowing us to test commit/rollback consequences. All wallets in the demo live in a single H2 database, and both services receive the same Spring-configured `JdbcTemplate`.

### 5.6. `src/main/java/example/required/InnerService.java`

```java
package example.required;

import java.io.IOException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private void debit() {
        int updated = jdbc.update(
            "UPDATE wallets SET balance = balance - 100 " +
            "WHERE id = 1 AND balance >= 100"
        );
        if (updated != 1) {
            throw new IllegalStateException("Insufficient balance");
        }
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void throwRuntimeAfterDebit() {
        debit();
        throw new IllegalStateException("Inner runtime failure");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void markRollbackOnlyWithoutThrowing() {
        debit();
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void throwCheckedAfterDebit() throws IOException {
        debit();
        throw new IOException("Inner checked failure");
    }
}
```

**Points to verify:**

- All three public methods use **`REQUIRED`**, and `InnerService` is a **different** Spring bean from `OuterService`.
- `throwRuntimeAfterDebit()` updates one row successfully, then throws an unchecked exception. The inner interceptor sees the error when the method terminates abnormally and decides on rollback.
- `markRollbackOnlyWithoutThrowing()` updates successfully, then marks rollback-only via `TransactionAspectSupport.currentTransactionStatus()`. The method can return normally; the rollback-only flag still takes effect.
- `throwCheckedAfterDebit()` updates successfully and then throws checked `IOException`. With Spring Boot 3.3.5's default rollback rules, the inner interceptor **does not** request rollback solely for `IOException`; therefore the outer transaction can still commit if no other error occurs.
- `debit()` is a private helper without its own transactional annotation. It executes SQL **on the connection already participating in T** because it is called from an advised public method.

This example intentionally throws an **application exception after a valid SQL statement**, rather than a SQL error or constraint violation. That isolates the behavior of Spring's rollback rules from the DB marking the transaction aborted on its own.

### 5.7. `src/main/java/example/required/OuterService.java`

```java
package example.required;

import java.io.IOException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    private void addToSecondWallet(long amount) {
        jdbc.update(
            "UPDATE wallets SET balance = balance + ? WHERE id = 2",
            amount
        );
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void catchRuntimeFromInner() {
        addToSecondWallet(10);
        try {
            inner.throwRuntimeAfterDebit();
        } catch (IllegalStateException ignored) {
            // Inner interceptor already saw the error and marked T rollback-only.
        }
        addToSecondWallet(20);
        // Returns normally yet outer commit must fail.
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void innerMarksRollbackOnly() {
        addToSecondWallet(10);
        inner.markRollbackOnlyWithoutThrowing();
        addToSecondWallet(20);
        // No Java exception in inner yet T is already rollback-only.
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void letRuntimeEscape() {
        addToSecondWallet(10);
        inner.throwRuntimeAfterDebit();
        // Not caught: exception continues to outer interceptor.
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void catchLocallyBeforeAnyInnerAdvice() {
        addToSecondWallet(10);
        jdbc.update(
            "UPDATE wallets SET balance = balance - 100 " +
            "WHERE id = 1"
        );

        try {
            throw new IllegalStateException("Locally handled failure");
        } catch (IllegalStateException ignored) {
            // No inner @Transactional boundary saw the exception.
        }
        addToSecondWallet(20);
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void catchCheckedFromInner() {
        addToSecondWallet(10);
        try {
            inner.throwCheckedAfterDebit();
        } catch (IOException ignored) {
            // Checked exception does not match default rollback rule.
        }
        addToSecondWallet(20);
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void completeSuccessfully() {
        addToSecondWallet(10);
        addToSecondWallet(20);
    }
}
```

**Mechanism in the initial cases:**

- In `catchRuntimeFromInner()`, `inner.throwRuntimeAfterDebit()` is called through **another bean's Spring proxy**. The inner interceptor receives `IllegalStateException`, sets global rollback-only on T, and rethrows. Outer's `catch` only swallows the Java exception; it **does not clear rollback-only** on T.
- In `innerMarksRollbackOnly()`, inner throws no error. Even so, when the inner logical scope ends, the transaction manager receives `status.setRollbackOnly()` and marks the shared physical transaction. Outer has no way to commit T.
- In `letRuntimeEscape()`, the error passes through both the inner and outer interceptors. Outer also receives the failure, so it rolls back T as requested; the caller receives the business exception `IllegalStateException` rather than `UnexpectedRollbackException`.
- In `catchLocallyBeforeAnyInnerAdvice()`, outer catches an exception itself before it has passed through **any inner transactional interceptor**. With T still committable and no other database errors, outer completes normally and commits all updates. This is a counterexample distinguishing "threw an exception" from "inner scope marked rollback-only".
- In `catchCheckedFromInner()`, `IOException` passes through the inner proxy, yet the default rule **does not require rollback**. Outer catches the exception and finishes normally, so both inner and outer updates commit.

Writing code like `catchLocallyBeforeAnyInnerAdvice()` is a **case to understand, not a safe business pattern to copy**. If the debit operation must not fail independently, design rollback rules or exception propagation properly.

### 5.8. `src/main/java/example/required/RequiredRollbackApplication.java`

```java
package example.required;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class RequiredRollbackApplication {

    @FunctionalInterface
    interface Job {
        void run() throws Exception;
    }

    public static void main(String[] args) {
        SpringApplication.run(RequiredRollbackApplication.class, args);
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.update(
            "UPDATE wallets SET balance = 1000 WHERE id = 1"
        );
        jdbc.update(
            "UPDATE wallets SET balance = 500 WHERE id = 2"
        );
    }

    private static String balances(JdbcTemplate jdbc) {
        return String.join(", ", jdbc.query(
            "SELECT id, balance FROM wallets ORDER BY id",
            (rs, row) ->
                rs.getLong("id") + "=" + rs.getLong("balance")
        ));
    }

    private static void runCase(
            String name, JdbcTemplate jdbc, Job job) {
        reset(jdbc);
        String signal = "completed";

        try {
            job.run();
        } catch (Exception error) {
            signal = error.getClass().getSimpleName();
        }

        System.out.println(
            name + " | " + signal + " | " + balances(jdbc)
        );
    }

    @Bean
    ApplicationRunner demo(OuterService outer, JdbcTemplate jdbc) {
        return args -> {
            runCase("Inner exception caught", jdbc,
                outer::catchRuntimeFromInner);
            runCase("Inner rollback-only", jdbc,
                outer::innerMarksRollbackOnly);
            runCase("Exception escapes outer", jdbc,
                outer::letRuntimeEscape);
            runCase("Caught before inner advice", jdbc,
                outer::catchLocallyBeforeAnyInnerAdvice);
            runCase("Checked inner exception", jdbc,
                outer::catchCheckedFromInner);
            runCase("Success", jdbc,
                outer::completeSuccessfully);
        };
    }
}
```

`ApplicationRunner` is the CLI entry point. The `OuterService` bean is **injected by Spring**, so the `outer::...` calls go through the outer proxy. `OuterService` also has the `InnerService` bean injected, so inner calls go through a separate proxy—a mandatory condition for the demo to actually create multiple **logical transaction scopes**.

The `runCase()` method resets data **outside** the service transaction for each scenario. After the method finishes (or the transaction proxy throws an exception), it reads the DB with `JdbcTemplate` to determine what committed or rolled back.

### 5.9. Run and expected stdout

Using the project's Gradle wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Ignoring Spring and Gradle log lines, the six lines printed by the demo itself are:

```text
Inner exception caught | UnexpectedRollbackException | 1=1000, 2=500
Inner rollback-only | UnexpectedRollbackException | 1=1000, 2=500
Exception escapes outer | IllegalStateException | 1=1000, 2=500
Caught before inner advice | completed | 1=900, 2=530
Checked inner exception | completed | 1=900, 2=530
Success | completed | 1=1000, 2=530
```

This is the **expected stdout based on the code and configuration shown**; it is not a claim that Gradle was run in your environment. H2, the Spring transaction manager, and the database schema must be fully configured as in the files above for the results to match.

### 5.10. Interpreting the output with a state table

| Case | Inner logical scope | State of T when outer tries to finish | Outer return / what caller receives |
| --- | --- | --- | --- |
| Inner exception caught | Unchecked error, marks T rollback-only | Cannot commit | `UnexpectedRollbackException` |
| Inner rollback-only | Explicitly calls `setRollbackOnly`, marks T rollback-only | Cannot commit | `UnexpectedRollbackException` |
| Exception escapes outer | Unchecked error passes through both inner and outer | Outer knows it must roll back | `IllegalStateException` |
| Caught before inner advice | No error passes through inner interceptor; T remains valid | Can commit | Normal return |
| Checked inner exception | Checked exception does not match default rollback rule | Can commit | Outer catches, normal return |
| Success | No failure | Can commit | Normal return |

**Note:** You may still observe outer/inner SQL statements executing after T is marked rollback-only (such as the `+20` update in the first case), depending on DB/connection state. Yet they **cannot be committed** when T eventually rolls back. Do not check "is temporary data visible after the third SQL statement?" and conclude the transaction succeeded.

## 6. Testing with JUnit 5 and Real Data

Tests check the **exception at the boundary** and the **database state after the transaction**, not merely whether `@Transactional` exists in source code.

File `src/test/java/example/required/RequiredRollbackTest.java`:

```java
package example.required;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

@SpringBootTest
class RequiredRollbackTest {
    @Autowired OuterService outer;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("UPDATE wallets SET balance = 1000 WHERE id = 1");
        jdbc.update("UPDATE wallets SET balance = 500 WHERE id = 2");
    }

    private long balance(long id) {
        Long value = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = ?",
            Long.class,
            id
        );
        return value.longValue();
    }

    @Test
    void catchingInnerExceptionCannotMakeSharedTransactionCommit() {
        assertThrows(
            UnexpectedRollbackException.class,
            outer::catchRuntimeFromInner
        );
        assertEquals(1000L, balance(1));
        assertEquals(500L, balance(2));
    }

    @Test
    void innerRollbackOnlyWithoutExceptionStillAbortsOuter() {
        assertThrows(
            UnexpectedRollbackException.class,
            outer::innerMarksRollbackOnly
        );
        assertEquals(1000L, balance(1));
        assertEquals(500L, balance(2));
    }

    @Test
    void escapingInnerRuntimeExceptionRollsBackNormally() {
        assertThrows(
            IllegalStateException.class,
            outer::letRuntimeEscape
        );
        assertEquals(1000L, balance(1));
        assertEquals(500L, balance(2));
    }

    @Test
    void catchingLocalFailureBeforeInnerAdviceDoesNotMarkRollback() {
        outer.catchLocallyBeforeAnyInnerAdvice();
        assertEquals(900L, balance(1));
        assertEquals(530L, balance(2));
    }

    @Test
    void catchingCheckedExceptionCanLeaveTransactionCommittable() {
        outer.catchCheckedFromInner();
        assertEquals(900L, balance(1));
        assertEquals(530L, balance(2));
    }

    @Test
    void successfulMethodCommits() {
        outer.completeSuccessfully();
        assertEquals(1000L, balance(1));
        assertEquals(530L, balance(2));
    }
}
```

Run:

```bash
./gradlew test
```

`@SpringBootTest` builds the application context and may execute `ApplicationRunner`, while `@BeforeEach` resets the fixture before each test. The tests are **not annotated with `@Transactional`** so that transactions managed by the test framework do not mask the service's own commit/rollback. If running tests in parallel against the same H2 database, isolate schemas/fixtures or serialize execution to avoid race conditions.

### Why not use only Mockito?

Mockito can verify that `inner.throwRuntimeAfterDebit()` was called, or that outer caught the exception, yet there is no **physical transaction** to mark rollback-only or commit. You need integration tests with `DataSourceTransactionManager` and a real or transaction-capable in-memory database to verify the most important consequence.

## 7. Catching an Exception in Outer Cannot Clear Rollback-Only

Let's compare two superficially similar situations:

**A. Error is thrown and caught purely inside the outer method**

```java
@Transactional
public void methodA() {
    performFirstUpdate();
    try {
        throw new IllegalStateException("Business warning");
    } catch (IllegalStateException ignored) {
    }
    performSecondUpdate();
}
```

If the DB itself does not report an error/rollback-only, the method returns successfully and **can commit** both updates. The error never passed through an **inner transaction interceptor**.

**B. Error passes through an inner proxy before outer catches it**

```java
@Transactional
public void methodB() {
    performFirstUpdate();
    try {
        otherBean.innerTransactionalMethod();
    } catch (IllegalStateException ignored) {
    }
    performSecondUpdate();
}
```

If `otherBean.innerTransactionalMethod()` uses `REQUIRED` and throws an unchecked exception, the inner interceptor typically marks T rollback-only. Even if outer catches it, that does not "cancel the rollback order".

These two snippets are illustrative only, not standalone Java source; the runnable project is in section 5. The difference is not the `catch` keyword, but **which transactional advice the exception passed through before being caught**.

### What if outer also intentionally wants to roll back?

Outer can explicitly mark its own scope:

```java
@Transactional
public boolean processOrReject() {
    try {
        otherBean.innerTransactionalMethod();
        return true;
    } catch (IllegalStateException failure) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return false;
    }
}
```

If outer owns the new T, outer's local rollback-only causes the transaction to roll back by **outer's explicit decision**, without necessarily producing `UnexpectedRollbackException` on completion. However, `false` is a **failure result**; the caller must not turn it into a "successful commit". If outer is itself just a participant in a broader transaction, the shared transaction can still cause an even further outer scope to hit unexpected rollback when it tries to commit.

In real code, **rethrowing an appropriate business exception** is usually simpler than relying on `TransactionAspectSupport`. Use `setRollbackOnly()` only when the API contract requires handling the error internally while signaling failure through the return type, and you understand the consequences for outer scopes.

## 8. Why Does the Manager Sometimes Report Errors Early or Late?

`AbstractPlatformTransactionManager` has advanced settings affecting how a participating transaction is handled.

### 8.1. `globalRollbackOnParticipationFailure`

Default is **`true`**: if a `REQUIRED` participant fails according to rollback rules, the manager marks the shared transaction as global rollback-only. This is the behavior that explains the `catchRuntimeFromInner()` case.

Some managers allow `setGlobalRollbackOnParticipationFailure(false)` so the transaction owner can decide whether to continue after a participant's failure. **Do not treat this as a generic fix** for `UnexpectedRollbackException`: the underlying resource may already have been marked failed/rollback-only at the database or ORM layer, and continuing a transaction after a data-access failure may be invalid. This setting also **does not clear** a rollback-only explicitly set via `TransactionStatus.setRollbackOnly()`.

### 8.2. `failEarlyOnGlobalRollbackOnly`

Spring transaction managers typically default to **`false`**: if T has been marked global rollback-only, `UnexpectedRollbackException` is normally reported at the **outermost boundary** when outer attempts to commit.

If changed to `true`, the framework can throw `UnexpectedRollbackException` **earlier** at an inner transaction boundary when it detects global rollback-only. Toggling this flag does not change the underlying fact: once T is rollback-only, it cannot commit.

### 8.3. `validateExistingTransaction`

By default, a `REQUIRED` participant typically **inherits the outer transaction's characteristics**, rather than changing the isolation, timeout, or read-only flag of the existing physical transaction. Setting `validateExistingTransaction=true` asks the manager to detect mismatches in isolation or read-only when joining. This is a way to enforce transaction policy, **not a tool to clear rollback-only**.

| Setting | Typical default | Effect |
| --- | --- | --- |
| `globalRollbackOnParticipationFailure` | `true` | Participant failure -> shared T rollback-only |
| `failEarlyOnGlobalRollbackOnly` | `false` | Reports unexpected rollback at the outermost boundary |
| `validateExistingTransaction` | `false` | May allow joining even if local policy differs from outer |

These three flags belong to transaction manager infrastructure and must be evaluated against the real DB/ORM. Do not arbitrarily change defaults to hide a service design flaw.

## 9. Comparing `REQUIRES_NEW` and `NESTED` Without Swapping Semantics

When the business logic **genuinely wants part of the work to be able to fail independently**, you can consider another propagation. However, this is a **decision that changes consistency semantics**, not a trick to suppress `UnexpectedRollbackException`.

| Inner propagation | Relationship with outer | How inner rollback affects outer | Notes |
| --- | --- | --- | --- |
| `REQUIRED` | Same physical transaction T | T can be marked rollback-only; outer cannot commit | Default, fits all-or-nothing |
| `REQUIRES_NEW` | New independent inner transaction; outer is suspended | Inner rollback **does not automatically** mark outer transaction rollback-only | Requires separate connection/resource, can exhaust pool |
| `NESTED` | One physical transaction, using a savepoint when supported | Inner rolls back to savepoint; outer can continue and commit the rest | Requires manager/driver savepoint support; not an independent commit |

### `REQUIRES_NEW`: true independence

For example, an email-sending service outside the database transaction does not change this issue; `REQUIRES_NEW` only coordinates transactions managed by the resource manager. If using `REQUIRES_NEW` for independent DB audit logging:

```java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void writeIndependentAudit() {
    // Write audit in a new transaction.
}
```

It can commit even if the outer transaction rolls back, yet that is **only valid** when the audit record is allowed to exist independently. If the audit must strictly reflect a committed business operation, splitting transactions like this can leave inconsistent data.

### `NESTED`: rolling back to a savepoint

With `DataSourceTransactionManager` and a driver supporting JDBC savepoints, `PROPAGATION_NESTED` can create a savepoint when inner joins T. If inner fails, the manager rolls back to the savepoint; outer can handle the error and proceed to commit the work done before the savepoint.

However, `NESTED` is still **one physical transaction**. It does not open an independent transaction and is not guaranteed to be available on every transaction manager (especially JPA/JTA cases). If outer rolls back, all inner changes past the savepoint that had not been finally committed also roll back.

**Choose according to the invariant:**

- All steps must succeed or fail together -> prefer `REQUIRED` and let exceptions/rollback-only be handled properly.
- An independent part must commit/roll back on its own -> consider `REQUIRES_NEW` and its resource cost.
- Want to recover part of SQL work within the same transaction -> consider `NESTED`/savepoints when supported by the manager.

## 10. Reasons the Example Might Fail to Create Two Logical Scopes

Having two `@Transactional` methods in a class does not mean two interceptors ran.

### 10.1. Self-invocation

```java
@Service
public class CombinedService {

    @Transactional
    public void outer() {
        try {
            inner();
        } catch (IllegalStateException ignored) {
        }
    }

    @Transactional
    public void inner() {
        throw new IllegalStateException("Failed");
    }
}
```

In Spring AOP **proxy mode**, `outer()` calls `inner()` via `this`, so **it does not go through the proxy again**. There is no inner transaction advice on this call. If the exception is caught in outer and no rollback-only came from elsewhere, outer can still commit. You must not conclude from the code above that "inner `REQUIRED` marked rollback-only".

Solution: extract `inner()` into another Spring bean and call it via the bean proxy, or place the transaction boundary properly on a public entry point called from outside, or use `TransactionTemplate` when programmatic control is needed. Switching from JDK dynamic proxy to CGLIB **does not automatically fix self-invocation**.

### 10.2. Instantiating beans with `new`

```java
InnerService inner = new InnerService(jdbcTemplate);
inner.throwRuntimeAfterDebit();
```

This is an illustrative snippet, not code using a Spring bean. An object created with `new` does not automatically have a transaction proxy. If called directly outside a transaction, SQL may auto-commit, leading to completely different results from the demo.

### 10.3. Calling the wrong transaction manager or datasource

If outer uses datasource A and inner uses datasource B or inner is annotated with a different manager, the statement "same physical transaction T" no longer holds. `REQUIRED` only joins a **matching transaction managed by that manager**. You must verify the transaction manager name, datasource/EntityManager, connection binding, and transaction logs.

### 10.4. Database errors marking T aborted

The demo uses a valid `UPDATE` and then throws an exception **in Java** to isolate Spring's rollback-only behavior. In practice, the DBMS may mark a transaction failed immediately after a SQL error (for example, a PostgreSQL transaction becomes aborted after a statement error unless proper savepoint management is used). Catching the exception will not guarantee the connection can continue and commit. The DB state can cause transaction rollback or commit failure independently of the inner interceptor's rollback-only marking.

### 10.5. `@Async` and reactive chains

Imperative transactions rely on a thread-bound transaction context. Handing a required step off to an executor/`@Async` and returning before the task finishes **does not** create an inner `REQUIRED` scope coordinated automatically in the same T. For reactive transactions using `ReactiveTransactionManager`, context and lifecycle are tied to `Mono`/`Flux` subscriptions; do not mechanically apply conclusions based on JDBC thread-locals. This lesson presents the standard **Spring imperative JDBC** case so rollback-only analysis is clear.

## 11. Debugging `UnexpectedRollbackException` Along the Call Chain

When encountering an error such as:

```text
org.springframework.transaction.UnexpectedRollbackException:
Transaction rolled back because it has been marked as rollback-only
```

Do not look only at the method where the exception appears, because that may be the **outer commit boundary**, while the cause that marked rollback-only occurred earlier in an inner scope.

Check in order:

1. **Outermost entry call:** which method started the new T? Did it go through a Spring proxy?
2. **Propagation configuration:** does inner use default `REQUIRED`, or did it use `REQUIRES_NEW`/`NESTED`?
3. **Same resource:** do outer and inner use the same transaction manager and connection?
4. **First event that marked rollback-only:** did an inner interceptor see an unchecked exception? Are there `rollbackFor`/`noRollbackFor` rules? Did code call `setRollbackOnly()`?
5. **Is there a `catch` in outer?** Did catching happen **after** the exception passed through the inner proxy or before?
6. **Is transaction T still committable?** Is the DBMS in an aborted state or is the ORM Session no longer usable?
7. **Final outcome:** did outer try to commit or intentionally roll back? Was the exception at the caller the original exception or `UnexpectedRollbackException`?
8. **Post-transaction data:** did the DB actually commit or roll back, rather than just looking at whether a SQL update returned rows > 0?

In test environments, you can selectively enable logging:

```yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.jdbc.datasource.DataSourceTransactionManager: DEBUG
```

This is an **optional** configuration snippet; it is not required in the demo to obtain the stdout shown. Enable TRACE only temporarily since transaction logs can be verbose; avoid logging sensitive data.

You can use `TransactionSynchronizationManager.isActualTransactionActive()` to check whether the current thread has an imperative transaction, yet it **does not tell you** whether the transaction is about to commit or is already rollback-only, and it does not replace checking the DB after commit.

## 12. How to Design Without Surprises

### Pattern A — All-or-nothing business flow: let errors cross the outer boundary

```java
@Transactional
public Receipt createOrder(Command command) {
    reserveInventory(command);
    chargeWallet(command);
    return saveReceipt(command);
}
```

If any mandatory step fails, let the business exception matching the rollback rule **escape the outer scope**. The caller receives the true underlying error, the transaction rolls back, and you avoid outer attempting to commit a transaction already marked rollback-only by inner.

### Pattern B — Outer must handle the error yet acknowledge rollback

```java
@Transactional
public ProcessResult process() {
    try {
        innerService.mandatoryStep();
        return ProcessResult.success();
    } catch (BusinessFailure failure) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return ProcessResult.failure(failure.getMessage());
    }
}
```

This is an illustrative snippet, assuming `ProcessResult`, `BusinessFailure`, and `innerService` belong to application code. Outer reports a clear failure result and **explicitly requests rollback itself**. Use this only when a contract returning a result object instead of throwing an exception is intentional; never return `success()` if the transaction has already been marked rollback-only.

### Pattern C — Genuinely optional fallback

```java
@Transactional
public void createWithOptionalEnrichment() {
    saveRequiredData();
    try {
        optionalEnrichment();
    } catch (OptionalEnrichmentException ex) {
        recordWarning(ex);
    }
}
```

This pattern is **safe only when** failure of `optionalEnrichment` is acceptable, violates no invariants, and **no inner scope has marked T rollback-only**. If `optionalEnrichment()` is actually a call to a proxied `@Transactional(REQUIRED)` bean that throws a runtime exception, outer's catch can still hit `UnexpectedRollbackException` afterward.

If optional logic needs to roll back separately, design isolation with a different transaction or savepoint and test actual resource behavior, rather than merely adding a `try/catch`.

## 13. Common Mistakes

| Symptom | Cause | How to handle |
| --- | --- | --- |
| Outer caught exception yet still `UnexpectedRollbackException` | Inner `REQUIRED` interceptor already marked T rollback-only | Trace the inner scope; if the whole business operation must abort, let the error escape |
| Inner returned normally yet outer cannot commit | Inner called `setRollbackOnly()` | Review inner's contract; do not mark recklessly when you only meant to skip a part |
| Outer sees `IllegalStateException`, no `UnexpectedRollbackException` | Error passed through outer interceptor and outer rolled back | This may be the intended outcome |
| SQL after inner failure shows `rowsUpdated=1` yet data is gone at the end | SQL only modified uncommitted data in T; T rolled back | Read the database **after the boundary finishes** |
| Inner's checked exception is caught and transaction commits | Default rollback rules do not roll back checked exceptions | Add `rollbackFor` if needed, and test for real |
| Cannot reproduce rollback-only | Inner called via `this`, `new`, or without a proxy | Use Spring beans properly and verify AOP |
| Switching to `REQUIRES_NEW` stops the error yet data diverges | Inner is independent, no longer all-or-nothing with outer | Clarify invariants before changing propagation |
| Called `setGlobalRollbackOnParticipationFailure(false)` yet still rolls back | DB or code directly marked rollback-only | Do not treat that config as a blanket bug fix |
| Error surfaces late at the outer boundary | `failEarlyOnGlobalRollbackOnly=false` | Trace the early cause in logs, not just the final stack trace |
| DB error caught yet transaction can no longer run | DBMS transaction aborted | Roll back/retry at the proper scope; do not assume recovery |
| Test sees an exception without knowing whether it committed or rolled back | Only asserting exception type | Assert balances/rows in the database after the transaction |
| Multiple transaction managers | Inner did not join the expected T | Verify wiring, qualifiers, and connections |

## 14. Self-Check Questions

1. Do two nested `@Transactional(REQUIRED)` methods create two physical transactions? **Usually no**; two logical scopes share one T.
2. Can an inner scope mark rollback-only without throwing an exception? **Yes**, via `TransactionStatus.setRollbackOnly()` through the Spring API.
3. Why does commit still fail when outer catches the exception? **The inner interceptor already marked the shared T rollback-only before the exception reached the catch.**
4. Does `UnexpectedRollbackException` mean commit succeeded? **No**; Spring reports that the transaction rolled back instead of committing as the caller expected.
5. If outer does not catch an inner unchecked exception, what does the caller typically see? **The original exception**, because the outer interceptor also decides to roll back on the error.
6. If outer catches an exception itself before it passes through any inner interceptor, does it always roll back? **No**; if T is not rollback-only and the DB is still committable, outer can commit.
7. Does `@Transactional(noRollbackFor=IllegalStateException.class)` on outer clear a rollback-only flag already set by inner? **No**.
8. Does inner `REQUIRES_NEW` rolling back force outer to roll back? **Not automatically**, because the two physical transactions are independent, though outer can still roll back due to business logic or an error escaping outer.
9. Does `NESTED` create an independent commit? **No**; when supported, it uses a savepoint within the same physical T.
10. Can an outer transaction commit SQL executed after inner has already marked T rollback-only? **No**; all updates in the same T roll back if T is rollback-only.
11. Does switching from JDK proxy to CGLIB automatically make `this.inner()` advised? **No**.
12. Where should tests verify outcomes? **After the transaction boundary finishes**, in an independent read transaction/connection, while also asserting the corresponding exception.

## 15. Practical Checklist for `REQUIRED`

1. Annotate the right **outer boundary** of the business unit requiring atomicity.
2. Verify every inner call genuinely passes through a **Spring transaction proxy** and uses the same transaction manager.
3. Distinguish logical scopes from the shared physical transaction; do not expect inner `REQUIRED` to commit or roll back alone.
4. When inner fails, verify default rollback rules and actual `rollbackFor`/`noRollbackFor` rules.
5. If inner has marked rollback-only, outer must not assume catching the error makes the transaction committable.
6. Let critical exceptions escape past the outer boundary, or explicitly mark outer rollback-only and report failure transparently.
7. Do not switch to `REQUIRES_NEW` or disable global rollback policy merely to silence exceptions; decide based on business invariants.
8. Check SQL/ORM errors that abort the connection/session and how the manager handles them, not just Java code.
9. Test commit/rollback with post-transaction data as well as exception cases, checked exceptions, `setRollbackOnly()`, and self-invocation.
10. Keep transactions short, encompassing only resources actually coordinated by the transaction manager.

## Official References

- Spring Framework — Transaction Propagation (`REQUIRED`, `REQUIRES_NEW`, `NESTED`, logical vs physical scopes): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — `AbstractPlatformTransactionManager` Javadoc (global/fail-early flags): https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html