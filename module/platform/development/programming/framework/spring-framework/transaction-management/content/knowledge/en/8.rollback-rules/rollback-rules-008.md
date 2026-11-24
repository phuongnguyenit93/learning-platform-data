# Marking Rollback-Only When Not Rethrowing an Exception in Spring Framework

## 1. Objective and Problem Statement

In Spring, `@Transactional` normally triggers rollback when a `RuntimeException` or `Error` exits the method managed by the transaction interceptor. However, many business flows need to **catch an exception, handle it, and not rethrow**: for instance, returning a `REJECTED` result instead of HTTP 500, or recording a data validation failure per the business contract. When an exception is caught inside the method, the transaction interceptor may see only a **normal return** and will commit the SQL statements that were executed.

**Rollback-only** solves that problem: code can explicitly tell the transaction manager that **the transaction scope must end in rollback even though no exception exits outward**.

After this lesson, you will know:

- Why catching an exception inside `@Transactional` prevents exception-driven automatic rollback from triggering.
- How to use `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` when managed by a Spring transaction proxy.
- How to use `TransactionTemplate` and `TransactionStatus.setRollbackOnly()` in programmatic transactions.
- Why marking rollback-only is **different** from executing `ROLLBACK` immediately.
- The difference between marking at the outer transaction versus an inner `Propagation.REQUIRED`; when `UnexpectedRollbackException` arises.
- The impact of `NESTED` and `REQUIRES_NEW` on the scope rolled back.
- How to verify data after the transaction ends, along with common pitfalls and a Java 17+ lab.

**Scenario:** A service writes a change, then detects that data fails a business rule. The API must return `REJECTED` rather than throwing an exception, yet the database must retain its state from before the call. Simply catching and returning would let the transaction commit. You must explicitly mark rollback-only before finishing.

## 2. Exceptions, the Transaction Interceptor, and the Commit Decision

With standard Spring AOP transactions:

```text
Caller
  |
  v
Spring transaction proxy
  |  starts / joins transaction
  v
@Transactional service
  |  INSERT/UPDATE...
  |  exception may occur
  |  try/catch inside?
  v
TransactionInterceptor handles completion
  |  exception escapes -> evaluates rollback rules
  |  normal return -> checks rollback-only and commits/rolls back
  v
Caller receives return value or exception
```

Consider an **illustrative snippet, not a standalone program**:

```java
@Transactional
public void save() {
    jdbcTemplate.update(
        "INSERT INTO tx_event(id, description) VALUES (?, ?)",
        1L, "candidate");

    try {
        validateInput(); // Throws IllegalArgumentException
    } catch (IllegalArgumentException ex) {
        log.warn("Rejected input", ex);
        // Does not rethrow and does not mark rollback.
    }
}
```

`IllegalArgumentException` is an unchecked exception. If it **escapes** the method through the transactional interceptor, Spring rolls back by default. Here, however, the method catches the exception and returns normally. If there is no rollback-only flag or other failure, Spring will **commit** the INSERT. The interceptor does not automatically know about every exception that occurred and was handled inside the method.

| Situation at boundary | Default when the method owns the physical transaction |
| --- | --- |
| Normal return, not rollback-only | Commit |
| `RuntimeException` or `Error` escapes | Rollback |
| Checked `Exception` escapes, no `rollbackFor` | Usually commits and rethrows exception |
| Exception caught and method returns normally | Usually commits |
| Exception caught, `setRollbackOnly()` called, then returns | Rolls back when scope completes |
| Marked rollback-only inside another transaction | May roll back and throw `UnexpectedRollbackException` on outer commit |

The table describes default configuration. `rollbackFor`, `noRollbackFor`, propagation, DB errors, and `rollback-only` state can alter concrete outcomes. Notably, rollback-only may be set by **another** scope sharing the same physical transaction.

## 3. What Does rollback-only Mean?

`TransactionStatus.setRollbackOnly()` marks the current transaction scope as **only allowed to finish by rolling back**. This is a decision for the transaction manager at **scope completion time**, not an immediate `Connection.rollback()` call on the line where it is invoked.

```text
BEGIN
  |
  +-- INSERT A
  +-- validate() throws error
  +-- catch error
  +-- status.setRollbackOnly()  <-- sets flag, does not run ROLLBACK immediately
  +-- return or continue executing some statements
  |
  v
Spring transaction manager completes scope
  |
  +-- ROLLBACK (if scope owns the whole transaction)
  +-- or handles savepoint rollback / marks shared transaction
```

Consequences:

- `setRollbackOnly()` **does not re-raise** the caught exception. If the caller needs to know the operation was rejected, return a clear failure status (`REJECTED`) or use an appropriate reporting mechanism.
- Code can continue executing after the marker, yet writes belonging to the physical transaction will not commit if the overall transaction rolls back. Avoid performing non-rollbackable side effects once you already know the transaction must abort.
- `status.isRollbackOnly()` reports the flag on the status; it **does not prove** the SQL ROLLBACK statement has already executed. Data may remain visible on the current connection until the transaction actually finishes.
- There is no `setCommitOnly()` API to clear rollback-only. Once a shared transaction is marked rollback-only, adding `noRollbackFor` cannot force it to commit either.
- If the DB already put the transaction into an error/aborted state, the marker does not make the connection valid again; finish the scope, roll back, and handle the error appropriately.

## 4. Approach A: TransactionAspectSupport.currentTransactionStatus()

Inside a `@Transactional` method processed **through a Spring proxy**, use:

```java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public Result process(long id) {
    jdbcTemplate.update(
        "INSERT INTO tx_event(id, description) VALUES (?, ?)",
        id, "candidate");

    try {
        checkBusinessRule(id);
    } catch (BusinessValidationException ex) {
        TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
        return Result.REJECTED;
    }

    return Result.ACCEPTED;
}
```

This is an **illustrative fragment**: `Result`, `BusinessValidationException`, `checkBusinessRule`, and fields must be declared to run. Behavior:

1. Caller invokes the Spring proxy; the interceptor starts or joins a transaction.
2. The INSERT participates in the JDBC connection managed by the manager.
3. The exception is caught inside the method; no exception exits.
4. Code obtains the current status via `TransactionAspectSupport` and marks rollback-only.
5. The method returns `REJECTED`; the transaction manager processes rollback when the scope ends according to propagation.
6. The caller must not treat a normal `return` as proof that the database committed.

### Conditions and Limitations of `currentTransactionStatus()`

`TransactionAspectSupport.currentTransactionStatus()` looks up the **status bound to the current thread by the transaction aspect**. If no status was created by advice, the API can throw `NoTransactionException`. Therefore:

- It must be called from code running inside a **transaction interceptor context**. Simply putting the annotation on a method invoked via self-invocation (`this.method()`) does not ensure the interceptor ran.
- Do not call it from another thread or `@Async` assuming it sees the original thread's status. Synchronous Spring transactions do not propagate automatically across new threads.
- If `TransactionTemplate` already provided `TransactionStatus` in its callback, use the callback parameter directly.
- When using `Propagation.SUPPORTS` without an actual transaction, distinguish logical status from physical resources. To inspect real JDBC transactions, check `TransactionSynchronizationManager.isActualTransactionActive()`.
- Business code now depends directly on Spring's transaction API. If the contract permits throwing exceptions across the boundary, `@Transactional(rollbackFor = ...)` is generally easier to test and less coupled.

## 5. Approach B: TransactionTemplate and Callback TransactionStatus

With programmatic transactions, Spring passes the status directly to the callback:

```java
transactionTemplate.executeWithoutResult(status -> {
    jdbcTemplate.update(
        "INSERT INTO tx_event(id, description) VALUES (?, ?)",
        20L, "candidate");

    try {
        validateInput();
    } catch (IllegalArgumentException ex) {
        status.setRollbackOnly();
    }
});
```

This is a **fragment**, requiring `transactionTemplate`/`jdbcTemplate` declarations and the validation helper. When the callback returns normally while status is rollback-only, `TransactionTemplate` handles rollback according to propagation.

A business result can also be returned:

```java
Decision result = transactionTemplate.execute(status -> {
    try {
        saveInDatabase();
        validateBusinessRule();
        return Decision.ACCEPTED;
    } catch (BusinessValidationException ex) {
        status.setRollbackOnly();
        return Decision.REJECTED;
    }
});
```

`Decision` and the helpers must be defined; the snippet illustrates the flow. If `TransactionTemplate` starts its own transaction, `REJECTED` is returned after rollback. If the callback only joins an existing outer transaction, the final outcome of the physical transaction is still governed by the outer scope.

**Note:** `TransactionTemplate` defaults to `REQUIRED` propagation. It does not automatically create an independent transaction in every situation. An inner callback inside an outer transaction can make the **outer transaction rollback-only**, just like an inner `@Transactional(REQUIRED)`.

## 6. Marker Placement and Propagation: Very Different Consequences

### 6.1. Marking in the Outermost Transaction

```text
caller without a transaction
  |
  -> @Transactional REQUIRED process()
        INSERT A
        catch validation error
        setRollbackOnly()
        return REJECTED
  |
  -> proxy ROLLS BACK physical transaction
  |
  -> caller receives REJECTED; does not necessarily receive an exception
```

This is an **intentional rollback** owned by the outermost scope. `UnexpectedRollbackException` **does not necessarily** arise in this situation: when the outer scope itself requests rollback, Spring normally rolls back cleanly. If the caller needs to know the outcome, design the return value to represent failure.

### 6.2. Inner REQUIRED Marks Rollback-Only

```text
caller
  |
  -> @Transactional REQUIRED outer()
        INSERT A
        |
        -> @Transactional REQUIRED inner()
             INSERT B
             catch error
             currentTransactionStatus().setRollbackOnly()
             return normally
        |
        INSERT C
        return normally
  |
  -> outer proxy tries to commit shared physical transaction
       => ROLLBACK A, B, C
       => UnexpectedRollbackException
```

With `REQUIRED`, scopes can be logically distinct while sharing **one physical transaction**. When the inner status requests rollback, Spring marks the shared physical transaction rollback-only. The outer scope did not set the flag itself and intends to commit; therefore it must receive `UnexpectedRollbackException` so the caller is not misled into thinking the commit succeeded.

**When it is thrown:** `UnexpectedRollbackException` can occur while the **outer interceptor processes commit**, meaning **after the body of `outer()` has returned**. A `try/catch` wrapping `inner()` *inside outer's body* will not necessarily catch this commit error; the caller invoking the **outer proxy** is where it surfaces.

### 6.3. NESTED and REQUIRES_NEW

| Inner propagation when outer exists | Physical transaction | Inner rollback-only marker |
| --- | --- | --- |
| `REQUIRED` | Shares physical transaction | Can make the entire outer transaction rollback-only, leading to `UnexpectedRollbackException` |
| `NESTED` | Same transaction, creates savepoint if manager/driver supports it | Can roll back to savepoint at end of nested scope; outer can continue |
| `REQUIRES_NEW` | Independent transaction; outer is suspended | Rolls back inner independently; outer can commit its own work |

`NESTED` does not commit independently: if outer rolls back, all changes in the physical transaction are discarded. `REQUIRES_NEW` is independent, yet can require an extra connection and create consistency issues if inner commits while outer later rolls back.

In the lab below, the inner example uses **REQUIRED** to clearly demonstrate `UnexpectedRollbackException`; do not assume every transaction manager supports `NESTED` savepoints.

## 7. Java 17+ Spring Boot Project: Four Rollback-Only Scenarios

The project uses **Spring Boot 3.3.5**, **Spring JDBC**, **H2**, and **Maven**. It prints verification results **after proxy invocations finish**:

1. Catch error without setting rollback-only → record is committed.
2. Catch error and call `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` → rolls back without rethrowing.
3. Catch error inside `TransactionTemplate` and use callback status → rolls back.
4. Inner `REQUIRED` marks rollback-only → outer rolls back, caller receives `UnexpectedRollbackException`.

### 7.1. Project Structure

```text
rollback-only-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/
    │   │   ├── RollbackOnlyApplication.java
    │   │   ├── LocalRollbackService.java
    │   │   ├── InnerService.java
    │   │   └── OuterService.java
    │   └── resources/application.properties
    └── test/java/demo/
        └── RollbackOnlyIntegrationTest.java
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
    <artifactId>rollback-only-demo</artifactId>
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

`spring-boot-starter-jdbc` includes `JdbcTemplate` and transaction support; H2 runs inside the JVM. `spring-boot-starter-test` provides Spring TestContext and JUnit 5.

### 7.3. application.properties

**`src/main/resources/application.properties`**

```properties
spring.datasource.url=jdbc:h2:mem:rollback_only_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.main.banner-mode=off
```

The H2 database named `rollback_only_demo` lets connections in the same JVM share one database. `DB_CLOSE_DELAY=-1` keeps the database alive when the last connection closes, which suits the example.

### 7.4. LocalRollbackService: Three Error-Handling Approaches

**`src/main/java/demo/LocalRollbackService.java`**

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class LocalRollbackService {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate template;

    public LocalRollbackService(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.template = new TransactionTemplate(manager);
    }

    @Transactional
    public void swallowedWithoutMarker(long id) {
        insert(id, "no-marker");

        try {
            rejectForDemo();
        } catch (IllegalArgumentException ex) {
            // Anti-pattern: swallows error, does not request rollback.
        }
    }

    @Transactional
    public void swallowedAndMarked(long id) {
        insert(id, "marked");

        try {
            rejectForDemo();
        } catch (IllegalArgumentException ex) {
            TransactionAspectSupport.currentTransactionStatus()
                    .setRollbackOnly();
        }
    }

    public void templateAndMarked(long id) {
        template.executeWithoutResult(status -> {
            insert(id, "template-marked");

            try {
                rejectForDemo();
            } catch (IllegalArgumentException ex) {
                status.setRollbackOnly();
            }
        });
    }

    private void insert(long id, String description) {
        jdbc.update(
                "INSERT INTO tx_event(id, description) VALUES (?, ?)",
                id, description);
    }

    private void rejectForDemo() {
        throw new IllegalArgumentException("business rejected");
    }
}
```

**Analysis:**

- `swallowedWithoutMarker` is an **anti-pattern**: the exception is handled, the interceptor sees the method succeed, so the new transaction commits.
- `swallowedAndMarked` still catches the exception yet explicitly sets rollback-only. Since it is called by a caller with no outer transaction, the proxy rolls back the method's transaction.
- `templateAndMarked` needs no annotation on the wrapper: `TransactionTemplate` manages the transaction inside the callback and uses the passed-in `status`.

The code intentionally shares the same failure helper to eliminate differences in validation logic. In production code, catch **expected, handleable error types**, return an appropriate outcome, and avoid swallowing `Exception` broadly.

### 7.5. InnerService: Rollback-Only in Inner REQUIRED

**`src/main/java/demo/InnerService.java`**

```java
package demo;

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

    @Transactional(propagation = Propagation.REQUIRED)
    public void markInsideInner(long id) {
        jdbc.update(
                "INSERT INTO tx_event(id, description) VALUES (?, ?)",
                id, "inner");

        try {
            throw new IllegalArgumentException("inner rejected");
        } catch (IllegalArgumentException ex) {
            TransactionAspectSupport.currentTransactionStatus()
                    .setRollbackOnly();
        }
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
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional
    public void callInner(long beforeId, long innerId, long afterId) {
        jdbc.update(
                "INSERT INTO tx_event(id, description) VALUES (?, ?)",
                beforeId, "outer-before");

        inner.markInsideInner(innerId); // Different Spring bean, through proxy.

        jdbc.update(
                "INSERT INTO tx_event(id, description) VALUES (?, ?)",
                afterId, "outer-after");
    }
}
```

`OuterService` and `InnerService` are separate Spring beans, avoiding self-invocation. Inner `REQUIRED` joins the outer transaction. When inner marks local rollback-only and returns, Spring marks the shared physical transaction rollback-only. Outer goes on to run the final INSERT, but upon completion, commit is rejected with `UnexpectedRollbackException` and all three records roll back.

### 7.6. RollbackOnlyApplication: Reading After the Transaction Boundary

**`src/main/java/demo/RollbackOnlyApplication.java`**

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
public class RollbackOnlyApplication {
    public static void main(String[] args) {
        SpringApplication.run(RollbackOnlyApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            JdbcTemplate jdbc,
            LocalRollbackService local,
            OuterService outer) {
        return args -> {
            jdbc.execute("""
                    CREATE TABLE tx_event (
                        id BIGINT PRIMARY KEY,
                        description VARCHAR(80) NOT NULL
                    )
                    """);

            local.swallowedWithoutMarker(1L);
            System.out.println("no marker: " + ids(jdbc, 1L, 1L));

            local.swallowedAndMarked(2L);
            System.out.println("marker: " + ids(jdbc, 2L, 2L));

            local.templateAndMarked(3L);
            System.out.println("template marker: " + ids(jdbc, 3L, 3L));

            try {
                outer.callInner(10L, 11L, 12L);
            } catch (UnexpectedRollbackException ex) {
                System.out.println("outer: UnexpectedRollbackException");
            }
            System.out.println("outer rows: " + ids(jdbc, 10L, 12L));
        };
    }

    private static List<Long> ids(JdbcTemplate jdbc, long from, long to) {
        return jdbc.queryForList(
                "SELECT id FROM tx_event WHERE id BETWEEN ? AND ? ORDER BY id",
                Long.class,
                from, to);
    }
}
```

`CommandLineRunner` has no `@Transactional`, so the runner itself does not create an outer transaction wrapping the entire demo. Each service call passing through the proxy completes its transaction (or throws at commit) **before** `ids(...)` reads the database.

### 7.7. Running and Explaining stdout

Requires JDK 17+ and Maven 3.6.3+; run in the directory containing `pom.xml`:

```bash
mvn spring-boot:run
```

The lines printed by the **program**, aside from Spring and Maven startup banners/logs:

```text
no marker: [1]
marker: []
template marker: []
outer: UnexpectedRollbackException
outer rows: []
```

| Case | What happens in the method | Result |
| --- | --- | --- |
| ID 1 | Catch `IllegalArgumentException`, no marker | Commits id=1 |
| ID 2 | Catch error, `currentTransactionStatus().setRollbackOnly()` | Rolls back id=2, no rethrow needed |
| ID 3 | Catch error in template, `status.setRollbackOnly()` | Rolls back id=3 |
| ID 10–12 | Inner `REQUIRED` marks rollback-only; outer returns | Rolls back everything, outer proxy throws `UnexpectedRollbackException` |

**Notable:** No exception reaches the caller of `local.swallowedAndMarked(2L)`, yet an independent SELECT after the transaction returns `[]`. That proves **normal return does not mean committed**.

## 8. Integration Tests to Prevent False Conclusions

**`src/test/java/demo/RollbackOnlyIntegrationTest.java`**

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class RollbackOnlyIntegrationTest {
    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private LocalRollbackService local;

    @Autowired
    private OuterService outer;

    @Test
    void caughtWithoutMarkerCommits() {
        local.swallowedWithoutMarker(101L);
        assertEquals(1, count(101L));
    }

    @Test
    void caughtWithMarkerRollsBack() {
        local.swallowedAndMarked(102L);
        assertEquals(0, count(102L));
    }

    @Test
    void templateMarkerRollsBack() {
        local.templateAndMarked(103L);
        assertEquals(0, count(103L));
    }

    @Test
    void innerRequiredMarkerPreventsOuterCommit() {
        assertThrows(
                UnexpectedRollbackException.class,
                () -> outer.callInner(110L, 111L, 112L));

        assertEquals(0, count(110L));
        assertEquals(0, count(111L));
        assertEquals(0, count(112L));
    }

    private int count(long id) {
        Integer result = jdbc.queryForObject(
                "SELECT COUNT(*) FROM tx_event WHERE id = ?",
                Integer.class, id);
        return result == null ? 0 : result;
    }
}
```

Run:

```bash
mvn test
```

**Expected:** all four tests pass once the project is created and dependencies download. Spring Boot starts the context and `CommandLineRunner` creates the table with small IDs (1,2,3,10,11,12); tests use distinct IDs (101–112) to avoid collisions.

Do not put `@Transactional` on the test class/methods in this example. If the test has its own transaction opened by `Spring TestContext`, a `REQUIRED` service will **join the test's transaction**, altering commit timing and where `UnexpectedRollbackException` might surface. By default, test-managed transactions roll back after the test, so checking at the wrong boundary can mislead.

Always inspect the **final data state after the outermost transaction ends**, not just assert whether a method threw an exception.

## 9. Returning a Business Result Without Throwing an Exception

An API must align Java outcomes with transaction outcomes. If a caller sees the method return normally while data actually rolled back, returning a “success” message causes confusion.

Example **fragment**, assuming `enum Outcome { ACCEPTED, REJECTED }` and an initialized `jdbcTemplate`:

```java
@Transactional
public Outcome process(long id) {
    jdbcTemplate.update(
            "INSERT INTO tx_event(id, description) VALUES (?, ?)",
            id, "candidate");

    if (!isBusinessValid(id)) {
        TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
        return Outcome.REJECTED;
    }

    return Outcome.ACCEPTED;
}
```

`isBusinessValid()` must be implemented per business rules; this snippet only illustrates the contract. With a transaction owned by this method, `REJECTED` can be returned after rollback. When an outer transaction exists, an inner `REJECTED` does not mean the physical transaction has completed; the caller must handle the outer boundary as well.

If throwing an exception instead of returning a status is viable, the declarative style is usually cleaner:

```java
@Transactional(rollbackFor = BusinessValidationException.class)
public void processOrThrow(long id) throws BusinessValidationException {
    jdbcTemplate.update(
            "INSERT INTO tx_event(id, description) VALUES (?, ?)",
            id, "candidate");

    validateOrThrow(id);
}
```

This is an illustrative fragment, not a standalone class. `rollbackFor` triggers rollback when checked `BusinessValidationException` **exits through the interceptor**. If the method catches the exception and returns normally, `rollbackFor` cannot detect a swallowed exception; you must rethrow or explicitly mark rollback-only.

## 10. When Should You Choose Which Mechanism?

| Requirement | Suggested mechanism |
| --- | --- |
| Business error can be thrown out to caller | `@Transactional` with rollback rule (`rollbackFor` if checked) |
| Catch error inside method, return `REJECTED`, must abort owned transaction | `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` |
| Control transaction via callback without transaction AOP | `TransactionTemplate` and callback `TransactionStatus.setRollbackOnly()` |
| Optional JDBC step needs rollback while outer continues | `NESTED`/savepoint if manager and DB support it |
| Inner must commit or roll back independently of outer | `REQUIRES_NEW` with connection-pool/consistency evaluation |
| Business requires consistent commit across multiple resources or side effects | Dedicated design (outbox, compensation, distributed transaction when appropriate) |

Choose a marker when there is a **clear reason an exception cannot cross the transaction boundary**. If you only want to “catch to log and avoid throwing to the caller” while data truly must roll back, design a transparent failure return so callers are never misled.

## 11. Common Mistakes and How to Fix Them

### 11.1. Catching an Exception and Forgetting to Set Rollback-Only

The swallowed exception leaves the interceptor uninformed. If the goal is to abort the transaction, rethrow the exception or invoke the marker; verify data after completion.

### 11.2. Believing `rollbackFor` Still Runs After Catching the Exception

`rollbackFor` is a rule for exceptions **exiting outward** through the interceptor. It does not scan past exceptions handled inside the method. Likewise, `noRollbackFor` does not clear an existing rollback-only flag.

### 11.3. Marking Inner `REQUIRED` and Assuming Outer Is Safe

A marker in inner `REQUIRED` can propagate across the entire physical transaction. Outer commit may throw `UnexpectedRollbackException`. Return an accurate outcome to callers and test the outer boundary too.

### 11.4. Calling `currentTransactionStatus()` Outside Transaction Advice

Without a matching context, this can throw `NoTransactionException`. Inside `TransactionTemplate`, use the callback status. With `@Transactional`, ensure calls go through the Spring proxy rather than `this.method()` or manually `new`-created objects.

### 11.5. Confusing `setRollbackOnly` with Immediate Rollback

The marker does not execute `Connection.rollback()` immediately. A `SELECT` inside the same transaction can still see uncommitted data. Only evaluate results after the physical transaction completes.

### 11.6. Continuing Non-Rollbackable Side Effects

Emails, Kafka messages, HTTP calls, or written files are not automatically undone when a JDBC transaction rolls back. Place side effects at the proper point or use outbox/idempotency/compensation.

### 11.7. Catching Infrastructure Errors and Trying to Continue

A SQL exception can leave the DB transaction invalidated/aborted. The marker does not “heal” the connection. Normally, let infrastructure errors propagate, roll back, and retry in a controlled way.

### 11.8. Using `TransactionTemplate` and Forgetting Outer Transactions

The template defaults to `REQUIRED`, so its callback can join an existing physical transaction. If you need isolated rollback, design propagation intentionally rather than assuming callbacks are always standalone.

### 11.9. Unintentional `@Transactional` on Tests

Spring TestContext typically opens a test transaction and rolls it back at test end. Inner `REQUIRED` services join that scope, altering outcomes and timing. In this lesson, tests intentionally omit `@Transactional`.

### 11.10. Skipping Data Verification

`isRollbackOnly()` reports flag status, not proof that the database rolled back. Use unique IDs, query after the transaction on an independent connection/transaction, and assert expected values.

## 12. How to Investigate Unexpected Outcomes

**Marker was set, yet data is still present:**

- Did the SQL statement use the same transaction manager and `DataSource`, or did another connection auto-commit?
- Is there an unfinished outer transaction, or did another `REQUIRES_NEW` commit independently?
- Are you reading an old record with a duplicate ID or data written by another transaction?
- Did the call pass through a Spring proxy and set the marker on the right scope's status?
- Did you check after physical transaction completion, or only `SELECT` inside an unfinished transaction?

**No exception seen, yet database rolled back:**

- Did the outer scope call `setRollbackOnly()` itself? That can be an intentional rollback requiring no exception.
- Is the API returning `SUCCESS` even though the service aborted the transaction? Fix the contract to return `REJECTED` or a failure result.

**`UnexpectedRollbackException` appears at outer scope:**

- Did an inner `REQUIRED` or another participant mark rollback-only?
- Did outer catch an exception and assume catching cleared the flag?
- Did the exception arise when the outer proxy committed (after outer's body returned) or in another method?
- Is there a test-managed outer transaction shifting commit timing?

When needed, enable logs in a test environment:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

Logs show transactions starting, participating, and rolling back. Even so, reading logs does not replace `SELECT`ing data **after the transaction ends**.

## 13. Self-Check Questions

**1.** A `@Transactional` method throws `IllegalArgumentException`, catches it immediately inside the method, and returns normally without a marker. Does it roll back by default?

**Answer:** No. Unless the new transaction is rollback-only for another reason, it commits because the interceptor sees a normal return.

**2.** Does writing `@Transactional(rollbackFor = IllegalArgumentException.class)` make an exception already caught inside the method trigger rollback?

**Answer:** No. The rule applies to exceptions exiting the interceptor. You must rethrow or explicitly mark rollback-only.

**3.** Does `setRollbackOnly()` execute SQL ROLLBACK immediately?

**Answer:** No. It requests rollback when the manager completes the scope; with `NESTED`, it can roll back to a savepoint when the inner scope ends.

**4.** The outermost method marks rollback-only itself and returns `REJECTED`. Must the caller receive `UnexpectedRollbackException`?

**Answer:** No. When the outer scope itself decides to roll back, Spring can roll back cleanly and let the caller receive `REJECTED`.

**5.** Inner `REQUIRED` marks rollback-only; outer returns normally. Why can the caller receive `UnexpectedRollbackException`?

**Answer:** Inner and outer share a physical transaction. Outer intends to commit, yet the transaction is already rollback-only, so Spring rolls back and reports commit failure.

**6.** Inside `TransactionTemplate`, where should you obtain status?

**Answer:** Use the `TransactionStatus` passed directly to the callback and call `status.setRollbackOnly()`.

**7.** If you only want to discard an optional JDBC operation while keeping the outer transaction, should you call outer `setRollbackOnly()`?

**Answer:** No. If the driver/manager supports it, use `NESTED`/savepoints to roll back the child part; marking outer cancels the whole physical transaction.

**8.** Can `noRollbackFor` force a transaction already marked rollback-only to commit?

**Answer:** No. `noRollbackFor` only adjusts the interceptor's reaction to matching exceptions; it does not clear rollback-only state.

## 14. Official References

- Spring Framework — Rolling Back a Declarative Transaction; `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` example: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Transaction Propagation, `REQUIRED` and `UnexpectedRollbackException`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Programmatic Transaction Management, `TransactionTemplate`: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring Framework — `TransactionStatus` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionStatus.html
- Spring Framework — `TransactionAspectSupport` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/interceptor/TransactionAspectSupport.html
- Spring Framework — `@Transactional` settings and rollback defaults: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html

**Key takeaway:** When an exception is caught inside a method, Spring's transaction interceptor does not automatically see that exception to trigger rollback. `setRollbackOnly()` lets you explicitly request rollback even when the method returns normally. Make sure to correctly identify the **transaction scope**, **propagation**, **returned business outcome**, and **database state after transaction completion**.