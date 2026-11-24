# setRollbackOnly in a TransactionTemplate Callback — Spring Framework Transaction Management

In Spring Framework, **TransactionTemplate** lets you open and complete a transaction programmatically in Java without placing `@Transactional` on every method. Each call to **execute(...)** or **executeWithoutResult(...)** takes a callback that runs within the transaction and receives a **TransactionStatus** object. When business rules determine that all changes must be discarded without wanting to throw an exception to the caller, the callback can call **status.setRollbackOnly()**.

This approach is readable, yet there is one crucial point: **setRollbackOnly() marks a rollback request; it does not immediately execute a JDBC ROLLBACK on that line**. The callback can keep running and even return a normal value. TransactionTemplate inspects the rollback-only state when completing the boundary; if the template owns the physical transaction, it asks the manager to roll back instead of commit. Therefore, **the callback's return value is not proof that the data committed**.

This lesson is part of the **TransactionTemplate** section of the Spring Framework – transaction management module. It focuses on when to call `setRollbackOnly` inside a callback, how it differs from throwing exceptions, how to report business outcomes, nested propagation, JDBC/JPA, testing, and common mistakes. A Java 17+ program using Spring JDBC/H2 is included so learners can observe the data after each transaction.

## 1. When Should You Call setRollbackOnly?

An application transaction can be rejected by business rules **after running some SQL statements**:

- Two update steps must both succeed, yet the second returns `updateCount=0`.
- A write operation is technically accepted, yet a final business condition check fails.
- A **BusinessResult** such as `REJECTED` or `CANCELLED` must be returned to the caller instead of using exceptions for every situation.
- A callback catches an error classified as convertible to a business result, while all prior DB changes must roll back.

Suppose a service prepares an order:

~~~text
BEGIN transaction T1
  INSERT order_header
  INSERT order_line
  check final business constraint
  => invalid
  status.setRollbackOnly()
  return Result.REJECTED
TransactionTemplate completes T1:
  ROLLBACK all changes in T1
Caller receives Result.REJECTED
~~~

This is **an intentional way to cancel a transaction while still returning a business result**. Returning `Result.REJECTED` must not be assumed to roll back automatically: **calling setRollbackOnly** (or an exception/rollback rule or another infrastructure mechanism) is what requests the rollback. If the callback simply returns `"REJECTED"` without calling `setRollbackOnly` and without any other error/marker, the manager may commit the executed SQL.

### Learning Objectives

Learners should be able to:

1. Explain the `TransactionTemplate` lifecycle and the role of `TransactionStatus`.
2. Mark rollback in **execute** and **executeWithoutResult** using Java lambdas.
3. Distinguish rollback-only from throwing exceptions, returning null, returning false, and catching exceptions.
4. Understand why calling `setRollbackOnly` and continuing to write SQL is a risky design.
5. Predict outcomes when a callback participates in **REQUIRED**, **NESTED**, or **REQUIRES_NEW** inside another transaction.
6. Distinguish a callback that owns its physical transaction from one joining an existing transaction.
7. Verify using DB state after `execute(...)` returns, rather than looking only at `status.isRollbackOnly()`.
8. Handle imperative `TransactionTemplate` callbacks separately from reactive transaction operators.

## 2. Lifecycle of TransactionTemplate

`TransactionTemplate` operates on the **PlatformTransactionManager** supplied via its constructor. For Spring JDBC, the manager is typically **JdbcTransactionManager** or **DataSourceTransactionManager**; for JPA it can be **JpaTransactionManager**. All data operations must use the resource managed by the corresponding manager.

Typical flow:

~~~text
Caller invokes transactionTemplate.execute(callback)
  |
  v
TransactionTemplate asks PlatformTransactionManager
  |
  +-- REQUIRED: join existing transaction or start a new one
  +-- configure propagation, isolation, timeout, readOnly, name...
  |
  v
callback.doInTransaction(status)
  |
  +-- SQL operations via JdbcTemplate/repository/EntityManager
  +-- callback can:
  |     a) return normally
  |     b) status.setRollbackOnly() then return
  |     c) throw RuntimeException/Error
  |
  v
TransactionTemplate completes scope
  |
  +-- callback throws RuntimeException/Error: roll back via exception path
  +-- status is rollback-only: manager decides rollback
  +-- no error/not rollback-only: manager attempts commit
  |
  +-- if only joining outer REQUIRED: does not commit physical transaction itself
  |
  v
clean up transaction resources and return result/exception to caller
~~~

The key point is that **TransactionTemplate controls the boundary**, while **TransactionStatus passed into the callback represents the status of that scope**. The caller does not need to—and should not—manually call `transactionManager.commit(status)` or `rollback(status)` on the template-provided status; doing so can cause the template to complete a second time or operate on an already completed status.

### Core API

| API | Purpose | Notes |
| --- | --- | --- |
| `new TransactionTemplate(manager)` | Creates template with manager | Must select the right DataSource/JPA resource |
| `template.execute(status -> result)` | Runs callback and returns result of type T | result can still be returned even when transaction rolls back intentionally |
| `template.executeWithoutResult(status -> ...)` | For callbacks needing no result | Still receives status to mark rollback |
| `status.setRollbackOnly()` | Requests rollback when scope completes | Does not throw an exception; does not execute rollback at the call line |
| `status.isRollbackOnly()` | Checks whether rollback-only has been flagged on status | Not proof that the DB has physically rolled back |
| `status.isNewTransaction()` | Indicates whether scope owns a new transaction | false when joining outer REQUIRED |
| `status.hasSavepoint()` | Indicates whether scope carries a savepoint | Usually true in inner JDBC NESTED |
| `status.isCompleted()` | Indicates whether status was completed by manager | Not yet completed during a normal callback |
| `template.setPropagationBehavior(...)` | Selects REQUIRED/NESTED/REQUIRES_NEW... | Configure before multi-threaded use |
| `template.setIsolationLevel(...)`, `setTimeout(...)`, `setReadOnly(...)` | Metadata for transaction definition | Effectiveness depends on manager, DBMS, and new/joined scope |

A **TransactionTemplate** instance can be reused across multiple calls and threads once its configuration is stable, because it holds no per-transaction conversational state. However, the **template's configuration properties are mutable**: do not change propagation/timeout mid-flight while multiple threads share the instance. If different policies are needed, create separate templates with dedicated configurations.

## 3. Simplest Usage: Mark Rollback Then Return

### 3.1. execute(...) When Returning a Business Result

Example for a callback processing two SQL steps:

~~~java
// Illustrative snippet, assuming tx is TransactionTemplate,
// jdbc is JdbcTemplate, and updateA/updateB methods exist.
BusinessResult result = tx.execute(status -> {
    updateA(jdbc);

    int affected = updateB(jdbc);
    if (affected != 1) {
        status.setRollbackOnly();
        return BusinessResult.rejected("Step B failed");
    }

    return BusinessResult.accepted();
});
~~~

If `updateB` fails to update a row, the callback already executed `updateA`, yet it marks rollback-only and returns `REJECTED`. When the template manages **a new physical transaction**, `updateA` is rolled back. **result is still REJECTED**, so the application can return HTTP 409 or an appropriate business message instead of reporting "OK". Where an outer `REQUIRED` exists, the effect on the outer transaction requires separate analysis (propagation section below).

This is a snippet, not a standalone compilable Java file: it needs the `BusinessResult` class, `updateA`/`updateB` methods, and an actual transaction manager bean. Full runnable code is in section 8.

### 3.2. executeWithoutResult(...) When No Return Value Is Needed

~~~java
// Snippet: Spring 6.2; callback uses a consumer returning no value.
tx.executeWithoutResult(status -> {
    jdbc.update("INSERT INTO demo_event(message) VALUES (?)", "attempt");
    if (!businessConditionSatisfied()) {
        status.setRollbackOnly();
        return; // returns from lambda, does not return a business value.
    }
    jdbc.update("INSERT INTO demo_event(message) VALUES (?)", "accepted");
});
~~~

`executeWithoutResult` fits when the caller does not need a result object. The `return;` statement only exits the lambda; if `setRollbackOnly` was called, the template still must complete the transaction according to that state.

Avoid writing:

~~~java
// Wrong for business intent: setRollbackOnly does not stop the callback.
tx.executeWithoutResult(status -> {
    jdbc.update("UPDATE account SET balance = balance - 10 WHERE id = 1");
    status.setRollbackOnly();

    // This line CAN STILL run if we do not return/throw.
    jdbc.update("UPDATE account SET balance = balance + 10 WHERE id = 2");
});
~~~

Even though the SQL operations may ultimately roll back, continuing after already knowing the transaction will fail can waste locks, run unnecessary queries, cause secondary exceptions, and emit side effects outside the database. **Return immediately, or throw an exception** if the caller needs to know of the failure via exception.

### 3.3. One Key Line: setRollbackOnly Is Not an Immediate Rollback Command

Comparison:

~~~text
Inside callback:
  status.setRollbackOnly()
  status.isRollbackOnly() -> true
  transaction may still be active
  JDBC Connection/EntityManager may not be cleaned up yet

After callback finishes and template completes scope:
  if scope owns physical transaction -> manager executes ROLLBACK
  if scope joins outer REQUIRED -> marks global rollback-only,
                                   physical transaction handled at outer boundary
~~~

With a new transaction, **the status object receiving the marker inside the callback** is the source of the decision when the template completes, without the caller needing to invoke rollback manually. After the template returns, the status should no longer be retained and used as an active transaction API.

## 4. setRollbackOnly vs. Throwing an Exception, Returning, and Catching

A table to avoid common confusion:

| Action inside callback | Typical state when owning a new transaction | What does the caller receive? |
| --- | --- | --- |
| return `"OK"` after successful SQL | Template attempts commit | Value `"OK"` if commit succeeds |
| return `"REJECTED"` **without setRollbackOnly** | May commit prior SQL | `"REJECTED"` yet database may have changed |
| `status.setRollbackOnly()`; return `"REJECTED"` | Rollback | `"REJECTED"` (if rollback completes cleanly) |
| `status.setRollbackOnly()`; return `null` | Rollback | `null`; not an exception |
| throw `new IllegalStateException(...)` | Rollback via RuntimeException path | Exception rethrown to caller |
| catch RuntimeException then return `"OK"` | May commit unless marked rollback-only by another scope/infra | `"OK"` yet may hide errors |
| catch RuntimeException; `status.setRollbackOnly()`; return `"REJECTED"` | Rollback | `"REJECTED"` if completion path succeeds |
| `status.setRollbackOnly()`; throw RuntimeException | Rollback via exception path | Exception; marker may be redundant |

**Note on checked exceptions:** Java callbacks normally cannot throw a checked `Exception` directly from a lambda if the functional interface does not declare `throws`; it must be handled/transformed appropriately. `TransactionTemplate` handles `RuntimeException`/`Error` along the template's rollback path; do not mechanically apply declarative `@Transactional` checked-vs-unchecked rules to guess every callback exception path. If you catch a checked business error and want to return a result, you can call `setRollbackOnly` and return explicitly.

### 4.1. When Is Using setRollbackOnly Good?

It is useful when:

- The failure is an **expected business outcome**, e.g., failing eligibility after writing temporary rows.
- An external API wants a **Result/Outcome** rather than an exception, while the DB must roll back completely.
- The callback checks affected row counts and wants to undo earlier steps.
- There is a short workflow where code intentionally controls both data access and outcome inside the callback.

### 4.2. When Should You Throw an Exception?

Consider throwing an exception when:

- The error is unexpected, not a normal business outcome.
- The caller needs the stack trace/cause for diagnostics or retries.
- Swallowing the exception could hide inconsistency, the DB transaction is already in an error state, or the database cannot continue executing.
- The transaction is simply declarative `@Transactional` and the exception policy is already clearly defined.

**Do not call `setRollbackOnly` as a substitute for error handling.** If a `SQLException` occurred due to a dropped connection or the DBMS already aborted the transaction, marking rollback does not heal the connection or fix data by itself. Let the error propagate and allow the transaction manager to clean up properly.

### 4.3. Return Value Does Not Prove Commit

Example:

~~~java
// Inside a String-returning callback, status represents the current transaction.
String outcome = tx.execute(status -> {
    jdbc.update("UPDATE task SET state='DONE' WHERE id=1");
    status.setRollbackOnly();
    return "DONE";
});
~~~

After `execute`, the caller can receive the String **"DONE"** even though the UPDATE did not commit. This is a **dangerous API contract**. If the application wants to return a result, use a value reflecting reality, such as `"CANCELLED"` or `"REJECTED"`; do not return `SUCCESS` after requesting rollback. When the callback joins an outer transaction, even returning success from inner does not confirm physical commit.

## 5. TransactionStatus: What to Understand and What Not to Do

**TransactionStatus** is the interface holding the state of the current execution; a status is issued for one specific callback.

### 5.1. setRollbackOnly Is One-Way

Once rollback-only has been set, there is no safe API to "unset" the marker and continue committing that transaction. If business logic changes its mind after marking rollback, the proper way is usually to finish/roll back the transaction and execute **a new transaction**, not hack into internals to clear the flag.

~~~java
// Snippet: there is no status.unsetRollbackOnly() to recover.
tx.executeWithoutResult(status -> {
    if (mustAbort()) {
        status.setRollbackOnly();
        return;
    }
    doDatabaseWork();
});
~~~

`mustAbort` and `doDatabaseWork` are illustrative. In a scope participating in an existing transaction, the marker can render **the outer transaction unable to commit**; this is especially important with `REQUIRED`.

### 5.2. isRollbackOnly Is a Signal, Not the Final DB State

Inside the callback:

~~~java
tx.executeWithoutResult(status -> {
    System.out.println("initial rollback-only=" + status.isRollbackOnly());
    status.setRollbackOnly();
    System.out.println("after marking=" + status.isRollbackOnly());
});
~~~

This typically prints `false`, `true` in a new transaction with no prior rollback-only marker. However, **`true` does not mean a JDBC ROLLBACK was just sent to the DBMS**; the template decides scope completion after the callback. Do not rely on a log line `"rollback only=true"` to claim all data has been reverted; re-read the DB after the boundary.

### 5.3. isNewTransaction Distinguishes Owner from Participant

When `TransactionTemplate` `REQUIRED` runs with no active transaction, `status.isNewTransaction()` is usually `true`. When a `REQUIRED` template is called inside an outer `REQUIRED` transaction, the inner status usually **does not own a new physical transaction**.

~~~text
No outer:
  template(REQUIRED) -> status.isNewTransaction() = true
  marker -> rolls back this scope's own physical transaction

With outer T1:
  outer template(REQUIRED) -> owner of T1
  inner template(REQUIRED) -> status.isNewTransaction() = false
  inner marker -> T1 is affected, no separate commit in inner
~~~

Status carries information revealing context state; it **is not a JDBC Connection** and must not be passed to another thread to alter the state of the imperative transaction in the current thread.

### 5.4. hasSavepoint in NESTED

If a `PROPAGATION_NESTED` template runs inside a JDBC transaction supporting savepoints, `status.hasSavepoint()` is usually `true`. Marking `setRollbackOnly()` on the nested status causes the manager to **roll back to the savepoint**, allowing outer to continue if DBMS conditions permit. Not every manager/JPA provider supports nested savepoint semantics.

## 6. Integrating into Business APIs: Result Instead of Swallowing Errors

Outcomes can be modeled explicitly:

~~~java
// Java 17 example: record describing data, does not manage transactions itself.
public record TransferResult(boolean accepted, String reason) {
    public static TransferResult ok() {
        return new TransferResult(true, "accepted");
    }
    public static TransferResult rejected(String reason) {
        return new TransferResult(false, reason);
    }
}
~~~

In a service with `TransactionTemplate`:

~~~java
// Excerpt, requires a class with TransactionTemplate tx and JdbcTemplate jdbc fields.
public TransferResult transfer(long from, long to, long amount) {
    return tx.execute(status -> {
        int debit = jdbc.update(
            "UPDATE wallet SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, from, amount);
        if (debit != 1) {
            status.setRollbackOnly();
            return TransferResult.rejected("source missing or insufficient funds");
        }

        int credit = jdbc.update(
            "UPDATE wallet SET balance = balance + ? WHERE id = ?",
            amount, to);
        if (credit != 1) {
            status.setRollbackOnly();
            return TransferResult.rejected("destination missing");
        }

        return TransferResult.ok();
    });
}
~~~

**This is a snippet**, not a standalone compilable program since class/config/imports are omitted. It illustrates a sound contract:

- One callback wraps both debit and credit.
- Every invalid branch **marks rollback-only and returns immediately**.
- The caller receives a result accurately describing the intended commit/rollback outcome.
- If debit updates successfully yet credit affects 0 rows, the debit change is rolled back.
- When `accepted=true`, the template attempts to commit, yet **commit can still throw an error**, so the caller must only consider `accepted` successful when `execute` actually returns without an exception from the manager.

In financial applications, you must also handle negative amounts, overflow, identical source/destination accounts, optimistic or row locking, isolation, and idempotency. A local JDBC transaction does not automatically include HTTP/email/other DBs in its rollback.

### 6.1. "I Don't Want an Exception" Is Different from "I Don't Want a Rollback"

Quite a few services write:

~~~java
// NOT safe if the first SQL already modified the DB.
return tx.execute(status -> {
    jdbc.update("UPDATE wallet SET balance = balance - 10 WHERE id=1");
    if (!canComplete()) {
        return "REJECTED";  // Missing status.setRollbackOnly()
    }
    jdbc.update("UPDATE wallet SET balance = balance + 10 WHERE id=2");
    return "OK";
});
~~~

If `canComplete()` is false, the callback **returns normally** and the transaction typically commits the earlier debit. This easily creates a "debited but never credited" state. Check every rejection branch: were there prior SQL side effects? If so, the rollback marker/exception must be explicit.

Better yet, **check immutable preconditions** before opening a transaction if safe; however, invariants can change under concurrent requests, so critical conditions must be **re-checked inside the transaction** or protected by constraints/locking.

## 7. Two Modern Invocation Styles: execute and executeWithoutResult

### 7.1. execute(callback) Returning Data

`TransactionTemplate` implements `TransactionOperations`, with `execute` taking **TransactionCallback<T>**. The lambda takes `status` and returns `T`:

~~~java
String result = tx.execute(status -> {
    performStepOne();
    if (!allowed()) {
        status.setRollbackOnly();
        return "CANCELLED";
    }
    performStepTwo();
    return "COMPLETED";
});
~~~

This is a snippet with illustrative business methods. Java infers `T` as `String`; the caller can receive `null` if the callback returns `null`. Do not assume `null` means rollback. If checked errors or a Result object are desired, design the return type explicitly.

### 7.2. executeWithoutResult(callback) Returning void

On modern Spring Framework such as 6.2, you can call:

~~~java
tx.executeWithoutResult(status -> {
    insertAuditDraft();
    if (mustCancel()) {
        status.setRollbackOnly();
        return;
    }
    finishAudit();
});
~~~

When reading older examples, you may see **TransactionCallbackWithoutResult** with `doInTransactionWithoutResult(status)` or an `execute` lambda returning `null`. All those forms use a transaction callback and allow `setRollbackOnly`; this lesson prefers `executeWithoutResult` when no value is needed.

### 7.3. Configuring Transaction Definition

~~~java
// Initialization snippet inside a Spring service constructor or @Bean.
TransactionTemplate tx = new TransactionTemplate(manager);
tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
tx.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
tx.setTimeout(15);
tx.setReadOnly(false);
~~~

- `REQUIRED`: if no transaction exists, create a new one; if a suitable outer transaction exists, join outer.
- Isolation: when a new transaction starts, the manager applies the policy on the resource; when joining an existing transaction, inner isolation may not change it.
- Timeout: requested duration for the transaction; enforcement level depends on manager/driver and queries.
- Read-only: hint about read intent, not a DB privilege strictly forbidding writes.
- The template should be completely configured **before concurrent use**.

By default, `TransactionTemplate` uses settings equivalent to a standard `DefaultTransactionDefinition`. You do not need to call `setPropagationBehavior(REQUIRED)` if you just want the default, though setting it explicitly in practice exercises improves readability.

## 8. Java 17+ Program Verifying Directly on H2

The following example runs Spring Framework 6.2.12 with Spring JDBC, H2 in-memory, and Java 17+. Spring Boot is omitted so `PlatformTransactionManager` is clearly visible. The `demo_balance` table has two rows A and B with `amount=0`. Each operation modifies `amount` via UPDATE. The program resets data before each scenario, making the results after each callback easy to compare.

**Test cases:**

1. Callback returns `OK`, no rollback mark → commit.
2. Callback calls `setRollbackOnly` then returns `CANCELLED` → rollback yet caller still receives `CANCELLED`.
3. First step UPDATE succeeds, second step UPDATE targets a non-existent row → `setRollbackOnly` and returns `REJECTED` → first step rolls back.
4. `executeWithoutResult` with `setRollbackOnly` → rollback despite no return value.
5. Callback throws `RuntimeException` → rollback and exception propagates out.
6. Inner `REQUIRED` template calls `setRollbackOnly` while joining outer `REQUIRED` → outer physical transaction does not commit, outer caller can receive `UnexpectedRollbackException`.
7. Inner `NESTED` template calls `setRollbackOnly` → rolls back to savepoint; outer still commits its own change.

### 8.1. Structure

~~~text
transaction-template-rollback-only/
├── pom.xml
└── src/main/java/demo/RollbackOnlyDemo.java
~~~

### 8.2. Maven Dependencies

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-template-rollback-only</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.RollbackOnlyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

In real Spring Boot applications, use the Spring Boot dependency management/BOM matching your Boot version rather than pinning separate Spring versions without checking compatibility. `DriverManagerDataSource` is only suitable for demos/tests; production typically uses a properly configured connection pool.

### 8.3. Complete Java Main

**src/main/java/demo/RollbackOnlyDemo.java**

~~~java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.support.TransactionTemplate;

public final class RollbackOnlyDemo {
    private RollbackOnlyDemo() {}

    private static void reset(JdbcTemplate jdbc) {
        jdbc.update("UPDATE demo_balance SET amount = 0");
    }

    private static void add(JdbcTemplate jdbc, int id) {
        int rows = jdbc.update(
                "UPDATE demo_balance SET amount = amount + 1 WHERE id = ?",
                id);
        if (rows != 1) {
            throw new IllegalStateException("Missing row: " + id);
        }
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
                "SELECT amount FROM demo_balance WHERE id = ?",
                Integer.class, 1);
        Integer b = jdbc.queryForObject(
                "SELECT amount FROM demo_balance WHERE id = ?",
                Integer.class, 2);
        return "A=" + a + ", B=" + b;
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            PlatformTransactionManager manager =
                    context.getBean(PlatformTransactionManager.class);

            jdbc.execute("CREATE TABLE demo_balance (" +
                    "id INT PRIMARY KEY, amount INT NOT NULL)");
            jdbc.update(
                    "INSERT INTO demo_balance(id, amount) VALUES (?, ?)", 1, 0);
            jdbc.update(
                    "INSERT INTO demo_balance(id, amount) VALUES (?, ?)", 2, 0);

            TransactionTemplate tx = new TransactionTemplate(manager);
            tx.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRED);

            TransactionTemplate participating = new TransactionTemplate(manager);
            participating.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRED);

            TransactionTemplate nested = new TransactionTemplate(manager);
            nested.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_NESTED);

            System.out.println("initial: " + balances(jdbc));

            // 1. No rollback-only set: commits both UPDATEs.
            reset(jdbc);
            String accepted = tx.execute(status -> {
                add(jdbc, 1);
                add(jdbc, 2);
                return "OK";
            });
            System.out.println("1 commit: result=" + accepted +
                    ", " + balances(jdbc));

            // 2. Mark rollback; still returns business result.
            reset(jdbc);
            String cancelled = tx.execute(status -> {
                add(jdbc, 1);
                add(jdbc, 2);
                status.setRollbackOnly();
                return "CANCELLED";
            });
            System.out.println("2 mark rollback: result=" + cancelled +
                    ", " + balances(jdbc));

            // 3. Step 2 UPDATE fails; rolls back step 1.
            reset(jdbc);
            String rejected = tx.execute(status -> {
                add(jdbc, 1);
                int rows = jdbc.update(
                        "UPDATE demo_balance " +
                        "SET amount = amount + 1 WHERE id = ?", 999);
                if (rows != 1) {
                    status.setRollbackOnly();
                    return "REJECTED";
                }
                add(jdbc, 2);
                return "OK";
            });
            System.out.println("3 reject: result=" + rejected +
                    ", " + balances(jdbc));

            // 4. No return value, can still roll back.
            reset(jdbc);
            tx.executeWithoutResult(status -> {
                add(jdbc, 1);
                status.setRollbackOnly();
            });
            System.out.println("4 without result: " + balances(jdbc));

            // 5. Throw RuntimeException: template rolls back and rethrows.
            reset(jdbc);
            boolean caught = false;
            try {
                tx.executeWithoutResult(status -> {
                    add(jdbc, 1);
                    throw new IllegalStateException("test exception");
                });
            } catch (IllegalStateException expected) {
                caught = true;
            }
            System.out.println("5 exception: caught=" + caught +
                    ", " + balances(jdbc));

            // 6. Inner REQUIRED joins outer; inner marker blocks T1 commit.
            reset(jdbc);
            boolean unexpected = false;
            try {
                tx.executeWithoutResult(outer -> {
                    add(jdbc, 1);
                    participating.executeWithoutResult(inner -> {
                        add(jdbc, 2);
                        inner.setRollbackOnly();
                    });
                });
            } catch (UnexpectedRollbackException expected) {
                unexpected = true;
            }
            System.out.println("6 joined REQUIRED: unexpected=" + unexpected +
                    ", " + balances(jdbc));

            // 7. Inner NESTED has savepoint: discards B while outer commits A.
            reset(jdbc);
            Boolean savepoint = tx.execute(outer -> {
                add(jdbc, 1);
                return nested.execute(inner -> {
                    add(jdbc, 2);
                    boolean found = inner.hasSavepoint();
                    inner.setRollbackOnly();
                    return found;
                });
            });
            System.out.println("7 NESTED: savepoint=" + savepoint +
                    ", " + balances(jdbc));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:rollback_only_demo;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource ds) {
            return new JdbcTemplate(ds);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            JdbcTransactionManager manager = new JdbcTransactionManager(ds);
            manager.setNestedTransactionAllowed(true);
            return manager;
        }
    }
}
~~~

**Why does the code run as a single Java file?** `Config` and helper methods are all inside `RollbackOnlyDemo`; the transaction manager, `DataSource`, and `JdbcTemplate` are initialized by Spring, while `TransactionTemplate` instances are created in `main`. `@EnableTransactionManagement` is not required because the example **does not use `@Transactional` advice**: `TransactionTemplate` invokes the manager directly. With Spring JDBC, `JdbcTemplate` uses the exact transaction-bound `Connection` from `JdbcTransactionManager`.

### 8.4. Running and Expected Stdout

From the `transaction-template-rollback-only` directory:

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout of Java main** (excluding separate Maven/Spring logs):

~~~text
initial: A=0, B=0
1 commit: result=OK, A=1, B=1
2 mark rollback: result=CANCELLED, A=0, B=0
3 reject: result=REJECTED, A=0, B=0
4 without result: A=0, B=0
5 exception: caught=true, A=0, B=0
6 joined REQUIRED: unexpected=true, A=0, B=0
7 NESTED: savepoint=true, A=1, B=0
~~~

Explanation:

1. **1 commit**: callback returns `OK`, no rollback-only marker; both UPDATEs are committed.
2. **2 mark rollback**: both A and B are UPDATEd, yet `status.setRollbackOnly()` causes the physical transaction to roll back; caller still receives `CANCELLED`.
3. **3 reject**: step A UPDATEd, yet step B did not find row 999; callback marks rollback-only and returns `REJECTED`. `A=0` confirms the earlier update was also discarded.
4. **4 without result**: `executeWithoutResult` returns no business value, yet `status` can still request rollback.
5. **5 exception**: callback throws `IllegalStateException`; template rolls back and rethrows. Caller catches the exception, DB unchanged.
6. **6 joined REQUIRED**: inner `TransactionTemplate` with `REQUIRED` propagation does not open its own physical transaction, instead joining outer T1. Inner marks rollback-only; outer tries to complete normally yet T1 cannot commit, so Spring raises `UnexpectedRollbackException` at the outer boundary. Both A and B are rolled back.
7. **7 NESTED**: outer updates A; inner `NESTED` updates B, `hasSavepoint=true`, and then `setRollbackOnly` rolls back to the savepoint. Outer still commits A. The result `A=1,B=0` shows the marker has a different scope when the scope is a `NESTED` savepoint.

The values are read **after `TransactionTemplate` has completed**; that is the proof of final data. On other databases/managers, especially managers that do not support savepoints, the `NESTED` scenario may be rejected instead of succeeding. Do not use H2 stdout to generalize all behavior of JPA or production DBMSs.

### 8.5. Why Not Use try/catch to Manually Commit/Rollback Inside the Callback?

`TransactionTemplate` already manages begin/commit/rollback/cleanup. Inside the callback, the application should use the callback `status` to mark rollback or throw an exception, **not acquire another `TransactionStatus` or call commit/rollback on the template-managed status**.

If full control to call `PlatformTransactionManager` directly is needed, that is a lower-level programmatic workflow: `getTransaction(definition)`, `commit(status)`, or `rollback(status)` in `finally`/`catch`. Do not mix that workflow with the status of a `TransactionTemplate.execute` call.

## 9. Hard Case: REQUIRED Callback Joining an Outer Transaction

With `REQUIRED`, **setRollbackOnly inside an inner callback can affect the entire physical transaction**, even if the inner callback does not throw an exception.

Suppose:

~~~text
T1 outer @Transactional(REQUIRED) or TransactionTemplate(REQUIRED)
   |
   +-- UPDATE A
   |
   +-- inner TransactionTemplate(REQUIRED):
   |     UPDATE B
   |     innerStatus.setRollbackOnly()
   |     return normally
   |
   +-- outer continues and wants to COMMIT
   |
   +-- physical transaction T1 is already marked rollback-only
   +-- manager ROLLBACKs T1
   +-- outer caller may receive UnexpectedRollbackException
~~~

**Reason for `UnexpectedRollbackException`:** the outer caller did not request a rollback itself and might think it committed when the outer method returns normally. Spring raises the exception to avoid falsely reporting success when the transaction rolled back due to a participating scope. If the **outer owner itself calls `outerStatus.setRollbackOnly()`**, the owner's intentional rollback normally completes without `UnexpectedRollbackException` in the new/independent case.

### 9.1. Do Not Look Only at the Inner Callback Return

~~~java
// Snippet, outerTx and innerTx are both REQUIRED on the same manager/DB.
outerTx.executeWithoutResult(outer -> {
    jdbc.update("UPDATE demo_balance SET amount=amount+1 WHERE id=1");
    innerTx.executeWithoutResult(inner -> {
        jdbc.update("UPDATE demo_balance SET amount=amount+1 WHERE id=2");
        inner.setRollbackOnly();
    });
    // Inner has returned, yet the shared physical transaction cannot commit.
});
~~~

If outer has another code path that keeps writing after inner, SQL can continue before the outer boundary discovers the final rollback; that does not make the transaction committable. Return the failure result early to outer or redesign so outer decides to abort. Do not swallow the marker and return success.

### 9.2. Distinguishing isRollbackOnly on Statuses of Different Scopes

An inner status has **local rollback-only** after `setRollbackOnly`. When inner `REQUIRED` finishes, the manager may translate this request into **global rollback-only on the physical transaction**. Because outer status is a different logical scope, do not infer from one status's local flag without considering the global marker/manager. The API provides state-inspection mechanisms, though details depend on the manager and transaction implementation.

A better design is returning a **typed Result** to outer so outer itself decides `setRollbackOnly` when conditions require canceling the whole operation. If a section must be able to roll back separately, consider `NESTED` when JDBC savepoints are supported or `REQUIRES_NEW` when an independent physical transaction is genuinely required.

## 10. Same setRollbackOnly Call, Yet NESTED Differs from REQUIRES_NEW

`TransactionTemplate` also allows configuring different propagation behaviors.

| Inner propagation when outer exists | Processing scope | Effect of inner setRollbackOnly |
| --- | --- | --- |
| `REQUIRED` | Joins same physical transaction T1 | When inner finishes, shared transaction may be marked rollback-only; outer cannot commit |
| `NESTED` | Same T1 with savepoint S1, if manager supports it | Rolls back changes since S1; outer can continue/commit the rest |
| `REQUIRES_NEW` | Suspends outer T1, opens independent physical transaction T2 | Rolls back T2; outer T1 can continue if it has no error/marker of its own |
| `SUPPORTS` | Joins T1 if present; otherwise no actual transaction | Cannot assume physical rollback when no transaction exists |
| `NOT_SUPPORTED` | Runs outside transaction, suspending outer if needed | No local DB transaction to roll back via standard marker |

### 10.1. NESTED Relies on Savepoints

In the demo, the `NESTED` template uses `JdbcTransactionManager` and H2 with savepoints. When inner calls `setRollbackOnly`, the manager rolls back to the savepoint. **Outer does not have to roll back all of T1**. This is a partial rollback mechanism, not `NESTED` having an independent commit.

~~~text
T1 begin
  UPDATE A
  SAVEPOINT S1
     UPDATE B
     nestedStatus.setRollbackOnly()
  ROLLBACK TO S1
  UPDATE C
T1 commit
=> A and C can commit; B is rolled back
~~~

`NESTED` with JPA `EntityManager` does not have the exact same meaning as a JDBC savepoint: a savepoint on a JDBC `Connection` does not automatically clean up all state cache/dirty entities in the persistence context. `JpaTransactionManager` usually does not enable `nestedTransactionAllowed` by default. Verify the provider/manager/DBMS rather than using `NESTED` as a trick to erase arbitrary ORM errors.

### 10.2. REQUIRES_NEW Uses an Independent Transaction

~~~text
T1 outer begin, UPDATE A
  suspend T1
  T2 inner begin, UPDATE B
  innerStatus.setRollbackOnly()
  ROLLBACK T2
  resume T1
T1 commit
=> A is kept, B is lost
~~~

If inner T2 calls `setRollbackOnly` and returns normally, outer can still commit T1 (if there are no other errors/markers). However, `REQUIRES_NEW` usually requires an extra JDBC `Connection` while outer holds resources; this can increase connection pool pressure, lock waits, or deadlocks when inner needs resources locked by outer. Do not use it just so outer escapes `UnexpectedRollbackException` without considering business rules.

### 10.3. When Should You Place the Marker on Outer?

If the business rule says "no step of the use case may commit", the outer owner transaction can call `outerStatus.setRollbackOnly()` after receiving the inner result. If a sub-step is allowed to fail separately while preceding/following steps must still commit, an intentional savepoint boundary or independent physical transaction is needed, rather than trying to force `REQUIRED` into partial rollback.

## 11. Interacting with @Transactional in a Spring Service

You can use `TransactionTemplate` inside a service that already has `@Transactional`, but you must understand **who owns the physical transaction**.

~~~java
// Snippet: outerMethod must be called through a Spring proxy.
@Transactional
public void outerMethod() {
    innerTransactionTemplate.executeWithoutResult(status -> {
        repository.write();
        status.setRollbackOnly();
    });
    // Default REQUIRED TransactionTemplate normally joins the outer transaction.
}
~~~

If the inner template uses `REQUIRED` and the same transaction manager, the marker can cause **outer to roll back** and raise `UnexpectedRollbackException`. Do not assume the inner template automatically creates an independent transaction just because you wrote `new TransactionTemplate(...)`. Default propagation is `REQUIRED`.

### 11.1. Comparison with TransactionAspectSupport

In declarative transactions, the current status can be accessed via:

~~~java
// Valid only inside a corresponding Spring AOP transactional invocation.
org.springframework.transaction.interceptor.TransactionAspectSupport
        .currentTransactionStatus()
        .setRollbackOnly();
~~~

This approach couples business code to Spring transaction infrastructure. With `TransactionTemplate`, **status is already passed directly into the callback**; that is the cleanest and most direct API in this context. There is no need to call `TransactionAspectSupport.currentTransactionStatus()` inside the callback.

If you want pure domain code free of framework dependencies, let the application service decide transaction policy outside the domain and let the domain return errors/exceptions/results; do not force domain objects to call `setRollbackOnly` directly.

### 11.2. Self-Invocation Differs from Callback Behavior

A `@Transactional` method calling `this.otherTransactionalMethod()` in the same bean can bypass the Spring AOP proxy. `TransactionTemplate` is a directly called programmatic API; **if `tx.execute(...)` actually runs**, it can create a transaction via the manager without needing AOP interception. However, if you combine both, **outer `@Transactional` may fail to activate** due to self-invocation; the inner template will then run under whatever context actually exists. Check the entrypoint, not just annotations.

## 12. TransactionManager and DataSource Must Match

Callback example:

~~~java
tx.executeWithoutResult(status -> {
    jdbcTemplate.update("UPDATE demo_balance SET amount=amount+1 WHERE id=1");
    status.setRollbackOnly();
});
~~~

For the UPDATE to roll back, `JdbcTemplate` must use the **DataSource belonging to the coordinating transaction manager** and the call's transaction context:

- `JdbcTransactionManager`/`DataSourceTransactionManager` manages connections of the corresponding `DataSource`.
- `JdbcTemplate` uses `DataSourceUtils` to join the connection bound to the Spring transaction on the thread.
- If code opens another JDBC `Connection` itself with `DriverManager` or uses a different `DataSource`, UPDATE may autocommit outside the transaction.
- If a repository writes to a different DB inside the callback, a marker on the local manager does not automatically roll back that other DB.
- If JPA is enabled, the transaction manager and `EntityManagerFactory`/persistence context must be compatible.

**No transaction manager causes already sent emails, HTTP calls, file writes, or messages to undo themselves** merely through `status.setRollbackOnly()`. If business logic needs to emit events after commit, consider transactional outbox or appropriate after-commit callbacks. If a request can be retried, side effects must be idempotent.

## 13. When the DBMS Has Aborted the Transaction, setRollbackOnly Cannot "Heal" It

Some DBMSs, notably PostgreSQL, put a transaction into a **failed/aborted** state after a SQL error. Subsequent SQL statements in the same physical transaction can fail with "current transaction is aborted". Marking rollback-only does not reset that transaction to keep running.

Dangerous example:

~~~java
// Snippet illustrating UNSAFE handling on PostgreSQL after a SQL error.
tx.executeWithoutResult(status -> {
    try {
        jdbc.update("INSERT INTO demo(id) VALUES (1)");
        jdbc.update("INSERT INTO demo(id) VALUES (1)"); // unique violation
    } catch (org.springframework.dao.DataAccessException ex) {
        status.setRollbackOnly();
        // Do not continue executing new SQL statements in a failed transaction.
        return;
    }
});
~~~

The safe way when encountering an unexpected data error is to let the transaction end/roll back, then start a new transaction if the business operation is retryable. To retry transient errors like deadlocks/serialization failures, ensure **each attempt gets a new transaction** and re-reads business conditions. Do not write a retry loop inside a callback after the transaction has already aborted.

In JPA, a flush error or persistence exception can also leave the `EntityManager`/transaction unsafe to continue; do not use `setRollbackOnly` as a recovery switch for the persistence context.

### Things to Keep Outside a Rollbackable Transaction

- Sending emails/SMS.
- Publishing Kafka/RabbitMQ messages directly without a consistency protocol.
- Calling payment or third-party APIs.
- Uploading files or writing to external non-database systems.
- Waiting on a long `Future`/remote call, sleep/backoff retries.
- Writing audit/business logs that must survive rollback if they sit inside the same DB transaction.

If auditing **every attempt** is required even when the main transaction rolls back, design an intentional independent transaction or external logging system outside the DB transaction, clearly defining semantics and side effects.

## 14. TransactionTemplate, TransactionalOperator, and Asynchronous Code

This lesson uses **PlatformTransactionManager** and `TransactionTemplate` for imperative JDBC/JPA. In the reactive stack, Spring uses **ReactiveTransactionManager** and **TransactionalOperator**, with **ReactiveTransaction** and a signal-based lifecycle.

Do not use a `TransactionTemplate` status from another thread to roll back an already completed physical JDBC transaction. If a callback merely schedules an async task and returns, `TransactionTemplate` can commit/roll back as soon as the callback returns, **without waiting for `CompletableFuture` to finish**. `PlatformTransactionManager` transaction context is typically bound to the current thread.

~~~java
// Snippet illustrating a temporal boundary gap.
tx.execute(status -> {
    CompletableFuture<Void> future = CompletableFuture.runAsync(
            () -> performDatabaseWorkInAnotherThread());
    return future; // Callback returns before the worker necessarily completes.
});
~~~

This snippet omits imports/methods and is not standalone. Imperative `TransactionTemplate` does not extend the transaction until the worker `Future` finishes. If the worker's SQL needs transactional atomicity, establish a boundary inside the worker or design an independent workflow. If the async task fails **after the template's transaction has already ended**, calling `setRollbackOnly` cannot retroactively roll it back.

Spring's reactive transaction operator has its own `setRollbackOnly` API via reactive callbacks, following Reactor Context and publisher lifecycle. Do not convert imperative code to reactive merely by changing return types.

## 15. Logging and Verifying Real Rollbacks

In applications with Spring Boot logging, you can temporarily enable:

~~~properties
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.support=DEBUG
logging.level.org.springframework.transaction.support=TRACE
~~~

You may see manager logs containing lines similar to:

~~~text
Creating new transaction ...
Acquired Connection ...
Switching JDBC Connection to manual commit ...
Initiating transaction rollback ...
Rolling back JDBC transaction on Connection [...]
Releasing JDBC Connection [...] after transaction
~~~

With a callback that marks rollback-only itself, an application stack trace does not necessarily appear because **no exception was thrown**. Do not rely on fixed log wording: loggers, managers, versions, and log levels can vary.

If using a connection pool, "releasing JDBC Connection" can mean **returning the connection to the pool**, not closing the physical socket. `TransactionTemplate` cleanup manages resource binding; do not manually close a Spring-managed connection inside the callback.

### Three Verification Levels

1. **Inside callback:** `status.isRollbackOnly()` after marking indicates rollback requested.
2. **Immediately after execute:** the template has completed the scope it manages; if it created a new transaction, commit/rollback has been processed by the manager (or an exception thrown).
3. **Reading from an independent transaction/connection:** the final DB state shows whether changes committed, avoiding confusion with uncommitted data visible inside the same transaction.

With a `REQUIRED` template **joining an outer transaction**, `execute` finishing **does not yet mean physical commit/rollback is done**. Final outcomes must be read after the outer boundary.

## 16. Testing: Avoiding "False Greens" from @Transactional Tests

In Spring TestContext, a test method annotated with `@Transactional` can open an outer transaction and roll back by default when the test ends. Calling a `REQUIRED` `TransactionTemplate` inside that test **joins the outer test transaction**, so:

- `status.isNewTransaction()` may be `false`.
- If inner calls `setRollbackOnly`, it can mark the entire test transaction rollback-only.
- Assertions reading on the same connection/context do not yet confirm a physical commit.
- The test framework rolling back at the end of the test can make every case look like it rolled back, even when production logic forgot `setRollbackOnly`.

To test the exact semantics properly:

- Run transactions along production boundaries, without being inadvertently wrapped by an outer test transaction.
- Initialize data beforehand, invoke the service/template, and let the boundary complete.
- Read results from a fresh connection/transaction.
- Test accepted, rejected, exception, and propagation branches.
- When testing joined outer `REQUIRED`, assert `UnexpectedRollbackException` at the owner boundary if that is the active behavior.
- When using `NESTED`, verify the manager/driver/savepoint actually supports it.
- When using JPA, flush/clear `EntityManager` or use a fresh persistence context to avoid reading cached state.
- Test non-DB side effects separately; DB rollback alone is not enough to prove events were not emitted.

### Recommended Test Matrix

| Case | SQL ran in callback? | `setRollbackOnly`? | Expected result when owning a new transaction |
| --- | --- | --- | --- |
| Normal completion | Yes | No | Commit; return accepted |
| Rejected after step 1 | Yes | Yes | Rollback; return rejected |
| `executeWithoutResult` cancelled | Yes | Yes | Rollback; no result |
| `RuntimeException` escapes | Yes | Not necessarily | Rollback; exception reaches caller |
| Catch exception, return normally | Yes | No | May commit — warning case |
| Catch exception, mark, return | Yes | Yes | Rollback; typed result |
| Inner `REQUIRED` marks while outer active | Yes | Yes in inner | Global rollback; outer may hit `UnexpectedRollbackException` |
| Inner `NESTED` marks while outer active | Yes | Yes in nested | Rollback to savepoint; outer can commit |
| Inner `REQUIRES_NEW` marks while outer active | Yes | Yes in inner | Rollback inner transaction; outer independent |

### Complementary Unit Tests and Integration Tests

Unit tests with a mocked `JdbcTemplate` can verify that code **calls `setRollbackOnly` on the right branch**, yet cannot prove real DB transaction rollback without a DBMS/resource. Integration tests should use H2 for foundational learning and production databases (PostgreSQL/MySQL/Oracle...) if logic depends on isolation, savepoints, constraints, or DB error behavior.

In applications with multiple transaction managers, each test must know which manager the template uses, rather than inferring solely from `@Transactional` annotations on other services.

## 17. Common Mistakes

| Mistake | Why it is dangerous | Right approach |
| --- | --- | --- |
| Returning `"FAILED"` yet forgetting `setRollbackOnly` | Template can commit already executed SQL | Set marker or throw when rollback is needed |
| `setRollbackOnly` then returning `"SUCCESS"` | Caller thinks it committed despite DB rollback | Use a typed Result expressing `CANCELLED`/`REJECTED` |
| `setRollbackOnly` without returning/throwing | Callback continues unnecessary SQL/side effects | Stop callback right after deciding rollback |
| Calling `transactionManager.rollback(status)` inside template callback | Template still has to complete status, causing double handling | Only use `status.setRollbackOnly()` or throw an exception |
| Thinking `status.setRollbackOnly()` rolls back immediately | Transaction stays active until template handles completion | Treat rollback marker as a request at the boundary |
| Reading `status.isRollbackOnly=true` and assuming DB rolled back | Marker is not the physical outcome | Query after the outer boundary completes |
| Inner `REQUIRED` marks yet outer returns success | Physical transaction rolls back, may raise `UnexpectedRollbackException` | Design outer to recognize error results and handle properly |
| Using `NESTED` with JPA without checking provider | Savepoints do not mean reverting the persistence context | Verify transaction manager/DBMS or avoid |
| Assuming `new TransactionTemplate` always creates a separate transaction | Default `REQUIRED` can join outer | Choose propagation intentionally |
| Using `REQUIRES_NEW` arbitrarily to dodge shared rollback | Inner commits/rolls back independently; different pool/lock behavior | Choose based on business invariants |
| Catching `SQLException` then running more SQL after marker | DB transaction may already be aborted | Finish/roll back, retry in a new transaction |
| Sending email before callback decides rollback | Email is not rolled back | Outbox/after-commit/idempotency |
| Passing `TransactionStatus` to another thread | Imperative transactions follow execution context | Dedicated boundary inside worker |
| Using `TransactionTemplate` yet calling manually opened JDBC Connection | SQL can autocommit outside managed transaction | Use `JdbcTemplate`/`DataSource` matching the manager |
| Mutating template config across threads | Shared mutable configuration causes races | Configure upfront; use separate templates for different policies |
| `@Transactional` test method making all data vanish at end of test | Masks missing `rollback-only` in business code | Test across independent boundary and re-read DB |
| Checking exception message strings instead of class/cause | Loses stack/cause and error classification | Preserve cause; classify clearly before retry |

## 18. Practice Reasoning Before Running Code

**Question 1.** In a `TransactionTemplate` creating a new physical transaction, the callback UPDATEs A, calls `setRollbackOnly`, and returns `"OK"`. After `execute`, what happens?  
**Answer:** The manager rolls back A, yet the caller can still receive `"OK"` if no error occurs during rollback. The return value does not prove commit; code should return `CANCELLED`/`REJECTED`.

**Question 2.** The callback UPDATEs A, catches `BusinessException`, and returns `"REJECTED"` without marking/throwing. Does it roll back?  
**Answer:** Not by default. Without a rollback-only marker from elsewhere, `TransactionTemplate` can commit A because the callback returned normally.

**Question 3.** Does `status.setRollbackOnly()` throw an exception right at the call line?  
**Answer:** No; it marks rollback. The callback must return/throw itself to avoid executing extra unintended SQL.

**Question 4.** When `executeWithoutResult(status -> ...)` uses `return;`, what data does that return carry?  
**Answer:** It carries no business value; `return` only exits the lambda. The manager still processes the rollback marker at completion.

**Question 5.** Inner `REQUIRED` template joins outer T1 and calls `setRollbackOnly`, and outer attempts to commit. Why can `UnexpectedRollbackException` occur?  
**Answer:** Inner rendered the shared physical transaction uncommittable. Outer may not know, so Spring raises the exception to avoid falsely reporting a commit.

**Question 6.** If inner `NESTED` uses a savepoint and calls `setRollbackOnly`, must outer roll back?  
**Answer:** No, if the manager/DBMS supports savepoints and outer has no other error. Inner rolls back the part after the savepoint; outer can still commit the remaining steps.

**Question 7.** If a callback directly uses `REQUIRES_NEW` and marks rollback-only, does outer roll back along with it?  
**Answer:** Not automatically. Inner is a separate physical transaction so outer can continue; business logic at the caller may still decide to roll back outer as well.

**Question 8.** Does `status.isRollbackOnly=true` mean an already sent email will be recalled?  
**Answer:** No. It only affects the resource transaction coordinated by the manager; email is a non-DB side effect.

**Question 9.** Is `@EnableTransactionManagement` needed to use `TransactionTemplate` in the demo?  
**Answer:** No. `TransactionTemplate` calls `PlatformTransactionManager` directly; `@EnableTransactionManagement` is needed for proxy-based `@Transactional` processing in standard Spring configs.

**Question 10.** If an INSERT triggers a unique violation on PostgreSQL and the callback catches the error and marks rollback, should it continue running another INSERT in the same transaction?  
**Answer:** Not by default. The transaction may already be failed; finish/roll back first, then retry in a new transaction when business policy permits.

**Question 11.** Why does a unit test with a mocked repository fail to prove rollback?  
**Answer:** Mocks have no physical transaction and no real database commit/rollback; an integration test checking DB state after the boundary is needed.

**Question 12.** Is calling `status.setRollbackOnly()` in the callback and manually calling `transactionManager.rollback(status)` better?  
**Answer:** No. `TransactionTemplate` already owns the lifecycle. Only use the status marker or an exception to let the template do its job; avoid double completion.

## 19. Project Application Checklist

1. **Identify atomic units:** Which SQL statements must commit or roll back together?
2. **Choose the right manager:** `JdbcTransactionManager`/`JpaTransactionManager` and matching `DataSource`/`EntityManagerFactory`.
3. **Choose boundaries:** `TransactionTemplate` in the application service; do not arbitrarily open transactions around every tiny method.
4. **Define outcomes:** `accepted`/`rejected`/`cancelled`/`error`; never use `"SUCCESS"` for an intentional rollback.
5. **Check every return branch:** Has any SQL executed before an error-return branch that forgot `setRollbackOnly`?
6. **Mark then exit early:** `status.setRollbackOnly()`; return outcome or throw when needed.
7. **Do not manually call commit/rollback** on the template-provided status.
8. **Analyze outer transactions:** `REQUIRED` join, `NESTED` savepoint, or `REQUIRES_NEW` independent transaction?
9. **Isolate transient DB exceptions:** roll back then retry the entire use case in a new transaction, bounded and idempotent.
10. **Do not emit unprotected side effects** before commit.
11. **Integration-test data after the boundary:** H2 for demos, production DBMS when behavior differs.
12. **Observe logs/metrics:** commits, rollbacks, rollback-only, `UnexpectedRollbackException`, and connection pool duration.

## 20. Conclusion

**`setRollbackOnly` in a `TransactionTemplate` callback is a clear way to request discarding changes within a transaction scope without being forced to throw an exception.** Key traits:

- The callback can return normally while the transaction ultimately **rolls back**.
- The marker does not halt the callback by itself; return immediately after deciding to cancel.
- **A return value does not confirm physical commit.** Name `Outcome` values to reflect actual rollback.
- A callback **creating a new transaction** can normally roll back intentionally without throwing an exception to the caller.
- A **`REQUIRED` callback joining outer** can cause outer to eventually receive `UnexpectedRollbackException`.
- A **`NESTED`** callback can roll back a savepoint without discarding outer; **`REQUIRES_NEW`** rolls back its own transaction.
- Verify `DataSource`/manager alignment, proxy context if combined with `@Transactional`, and DB readbacks after the boundary.

This is a useful tool when needing to express **business rejection with rollback** via a Result object. When standard exception-based rollback suffices, declarative `@Transactional` can be simpler and involve less infrastructure coupling. Whichever approach you pick, protect business invariants and never emit side effects expecting a DB rollback to undo them.

## References

- [Spring Framework — Programmatic Transaction Management / TransactionTemplate](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Transaction Propagation and UnexpectedRollbackException](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — TransactionStatus API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionStatus.html)
- [Spring Framework — TransactionTemplate API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework — JdbcTransactionManager API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Spring JDBC Connection Handling](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)

**Final takeaway:** Inside a `TransactionTemplate` callback, if a business branch needs to return a rejection after writing data, mark rollback-only before returning; then check DB state after the boundary completes. Choosing the right transaction scope is just as important as calling the right API.
