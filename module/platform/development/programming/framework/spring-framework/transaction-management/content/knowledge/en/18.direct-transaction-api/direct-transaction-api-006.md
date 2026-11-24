# Distinguishing Business Errors from Commit or Rollback Errors When Using Spring's Direct Transaction API

## 1. The Real-World Problem: Three Kinds of Failures Cannot Be Handled the Same Way

An order-placement application typically performs these steps: check business rules, update the database, commit the transaction, and return the result. Different errors can arise along that flow:

- **Business/domain error:** for example insufficient balance, closed order, or invalid amount. Application code rejects the request according to a specific rule.
- **Data-access error:** for example a SQL statement violating a unique key or a DB connection failing during processing. This is a resource error; it can be mapped to a domain error only when the application understands the exact cause.
- **Commit error:** the business callback completed normally, yet the transaction manager failed to finish the commit step as expected.
- **Rollback error:** after a business error or SQL error, the application requests a rollback, yet the manager/resource fails while undoing the work.

First scenario:

~~~text
BEGIN T1
  business check: OK
  INSERT: OK
  callback returns "OK"
COMMIT T1 -> TransactionSystemException
Caller receives an error at the COMMIT stage.
~~~

Second scenario:

~~~text
BEGIN T2
  callback throws BusinessRuleException
ROLLBACK T2 -> TransactionSystemException
Caller may receive the ROLLBACK error instead of the original business error.
~~~

**Rule:** you must determine **at which stage the error occurred**, **what the root cause is**, and **whether the transaction state is known for certain**. You cannot look solely at the final exception class and assert that the data definitely committed or rolled back.

This Knowledge article belongs to Spring Framework's **Direct Transaction API** group, focusing on:

- `TransactionTemplate.execute(TransactionCallback)`: Spring manages the transaction lifecycle around a callback.
- `PlatformTransactionManager`: the developer directly calls `getTransaction(...)`, `commit(status)`, and `rollback(status)`.

After this lesson, you will know how to classify domain errors and infrastructure errors, preserve the original error when rollback also fails, avoid calling rollback a second time after a commit error, use `setRollbackOnly()` properly, and design safe retry/idempotency.

## 2. Four Stages and Characteristic Exceptions

~~~mermaid
flowchart TD
    A["Caller"] --> B["getTransaction(definition)"]
    B --> C{"Did begin succeed?"}
    C -->|"No"| D["Transaction creation error"]
    C -->|"Yes"| E["Business body / SQL"]
    E --> F{"Did body throw?"}
    F -->|"Yes"| G["rollback(status)"]
    G --> H{"Did rollback succeed?"}
    H -->|"Yes"| I["Return original body error"]
    H -->|"No"| J["Rollback error may mask body error"]
    F -->|"No"| K["commit(status)"]
    K --> L{"Did commit succeed?"}
    L -->|"Yes"| M["Return result"]
    L -->|"No"| N["Commit error; verify final state"]
~~~

| Phase | Example error | Safe conclusion |
| --- | --- | --- |
| **Begin** | `CannotCreateTransactionException` | No valid status obtained yet to roll back |
| **Business body** | `BusinessRuleException` | Domain rejection; undo writes participating in the transaction if business requires |
| **SQL body** | `DataIntegrityViolationException` | SQL/constraint failed; does not automatically equate to a commit error |
| **Commit** | `UnexpectedRollbackException` | Coordinator rolled back when caller expected commit |
| **Commit** | `TransactionSystemException` | Commit encountered a failure; in some cases outcome needs reconciliation |
| **Rollback** | `TransactionSystemException` | Undo encountered a failure; preserve original error and verify state |

Some ORMs such as JPA/Hibernate may **flush data lazily** at commit. Therefore, a constraint error can still surface during the commit phase, even though the underlying cause is invalid data. Record the **observed phase** and the **technical root cause** separately.

### Distinguishing the Signals

A **business error** answers: which domain rule did the request fail to satisfy?

A **commit or rollback error** answers: could the transaction coordinator complete or undo the transaction?

Both can occur together: `BusinessRuleException` happens first, and then `TransactionSystemException` arises during rollback. The caller may only see the transaction exception if prior error details were not preserved.

## 3. Business Errors: Exception or Outcome?

Example domain rule:

~~~java
if (amount <= 0) {
    throw new BusinessRuleException("INVALID_AMOUNT");
}
~~~

This is an illustrative snippet; the `BusinessRuleException` class is fully defined in section 8. It can be a runtime exception distinct from Spring infrastructure errors.

When business logic rejects a request **before writing to the DB**, opening a transaction is not necessarily required. When partial writes have occurred and domain logic later rejects, decide whether the transaction may retain those changes or not.

With `TransactionTemplate`, throwing a runtime exception:

~~~java
try {
    template.execute(status -> {
        verifyBusinessRules();
        writeRows();
        return null;
    });
} catch (BusinessRuleException ex) {
    // Domain rejected; template has requested rollback.
}
~~~

This is an illustrative snippet requiring the `template` variable and two real helpers. The original exception is rethrown if rollback **succeeds**.

If business rejection is a normal outcome, you can return an Outcome instead of throwing an exception:

~~~java
Outcome outcome = template.execute(status -> {
    saveSomeData();
    status.setRollbackOnly();
    return new Outcome("DECLINED");
});
~~~

This is also an illustrative snippet. If you save data and then return `DECLINED` **without calling `setRollbackOnly()`**, the template can still commit because the callback completed normally.

**Never use `catch(RuntimeException)` and blindly return a business error.** `DataAccessException` and `TransactionException` are both runtime exceptions, yet neither is a domain rejection.

## 4. TransactionTemplate: Callback Success Is Not Yet Commit Success

Example:

~~~java
TransactionTemplate template = new TransactionTemplate(manager);
String result = template.execute(status -> {
    jdbc.update("INSERT INTO tx_event(id, description) VALUES (?, ?)",
                1L, "saved");
    return "OK";
});
~~~

This is a snippet requiring `manager` and `jdbc` variables provided by Spring.

Typical execution flow of `TransactionTemplate.execute(...)`:

1. `getTransaction(...)` acquires/starts the transaction.
2. Calls `TransactionCallback.doInTransaction(status)`.
3. Callback returns normally → calls `commit(status)`. If `status` is rollback-only, the manager may execute a rollback per contract.
4. Callback throws `RuntimeException` or `Error` → attempts to call `rollback(status)`.
5. If rollback succeeds, the callback's exception is rethrown to the caller.
6. If rollback fails, the transaction exception can **replace the callback exception as the top-level error**.
7. If commit fails, `execute(...)` **throws the commit error** even though the callback just returned `"OK"`.

~~~text
TransactionTemplate.execute
    begin
    callback -> return "OK"
    commit
        success -> execute returns "OK"
        error   -> execute throws exception
~~~

Therefore, do not emit an irreversible `ORDER_COMMITTED` event directly inside the callback. In a scope that owns a new transaction, only after `execute(...)` returns normally do you have grounds to believe the manager committed.

### Runtime and Checked Exceptions

The `TransactionCallback<T>` interface **does not declare checked exceptions**. A lambda that directly throws `IOException` must catch/convert it, or represent the failure with an Outcome + `setRollbackOnly()`.

Example of preserving a checked exception's cause:

~~~java
try {
    callExternalLibrary();
} catch (IOException ex) {
    throw new IllegalStateException("External operation failed", ex);
}
~~~

This is an illustrative snippet requiring a `callExternalLibrary()` helper. Here the exception escaping the callback is **unchecked**, so the template requests rollback. However, with external HTTP/APIs, rolling back the DB does not retract already completed network side effects.

Do not assume `@Transactional`'s `rollbackFor` applies to `TransactionTemplate`. The template has its own callback behavior; if you need to handle checked exceptions while preserving their signature, the direct manager is an option.

### setRollbackOnly Does Not Create a Business Exception by Itself

~~~java
String result = template.execute(status -> {
    status.setRollbackOnly();
    return "DECLINED";
});
~~~

When the template starts a new transaction, local rollback-only makes the manager roll back instead of committing; the callback can still return a normal Outcome. If the template **joins an outer transaction** via REQUIRED, rollback-only can prevent the shared transaction from committing, causing `UnexpectedRollbackException` at the outer boundary. Always inspect propagation and who owns the physical transaction.

## 5. Transaction Exceptions You Must Understand

| Exception | Typical meaning |
| --- | --- |
| `CannotCreateTransactionException` | Manager could not create or join a transaction |
| `TransactionTimedOutException` | Transaction deadline detected as expired |
| `IllegalTransactionStateException` | Invalid usage of transaction state, e.g., completing a status twice |
| `UnexpectedRollbackException` | Caller expected commit, yet coordinator rolled back |
| `TransactionSystemException` | Transaction system error, possibly at commit or rollback |
| `HeuristicCompletionException` | Heuristic condition from a distributed coordinator, possibly mixed outcome |

### 5.1. UnexpectedRollbackException: Usually Indicates an Actual Rollback

Example:

~~~text
Outer REQUIRED: creates T1
  Inner REQUIRED: joins T1
    Inner throws RuntimeException
    Transaction interceptor marks T1 rollback-only
  Outer catches exception and returns normally
Outer calls commit
  Manager sees rollback-only, rolls back T1
  Caller receives UnexpectedRollbackException
~~~

This is **not** "the DB definitely committed and the response was lost". It signals that the expected commit **did not occur** because the coordinator rolled back.

### 5.2. TransactionSystemException: Masking an Earlier Application Error

When the callback throws `BusinessRuleException`, the template tries to roll back. If rollback throws `TransactionSystemException`, the final exception may be the transaction error rather than the domain error.

Spring's `TransactionTemplate` has a mechanism to preserve the original error via `TransactionSystemException.initApplicationException(original)`. The caller can inspect:

~~~java
catch (TransactionSystemException ex) {
    Throwable initial = ex.getApplicationException();
    // initial may be BusinessRuleException.
}
~~~

This is an illustrative snippet. `getApplicationException()` can return **null**, for example on a commit failure after a successful callback. With other runtime rollback exceptions, the original error is not always stored through this mechanism. If you use the manager directly, preserve the error via suppressed/cause or context logging.

### 5.3. DataAccessException Appearing in the Body or at Commit

With JDBC, an INSERT violating a primary key typically throws `DataIntegrityViolationException` at the SQL statement. With JPA or deferred constraints, the error may surface at flush/commit. Distinguish:

- **Source:** database constraint or SQL error.
- **Observed phase:** body or commit.
- **Transaction outcome:** rolled back cleanly, failed commit, or unconfirmed.

Never apply a single domain label to all constraint violations. Only map when a specific constraint corresponds to a well-defined business rule, such as a unique constraint on an idempotency key.

## 6. Direct PlatformTransactionManager: Writing try/catch Properly

The methods:

~~~java
TransactionStatus status = manager.getTransaction(definition);
// Perform operations belonging to this scope.
manager.commit(status);
~~~

This is a skeleton; when the body fails, it must roll back.

### Anti-pattern: Rollback After a Commit Error

~~~java
TransactionStatus status = manager.getTransaction(definition);
try {
    writeBusinessData();
    manager.commit(status);
} catch (RuntimeException ex) {
    manager.rollback(status);  // WRONG if the exception came from commit!
    throw ex;
}
~~~

This is an **anti-pattern**. The Spring `PlatformTransactionManager.commit(status)` contract states explicitly that the transaction is completed and cleaned up when the commit call finishes, **whether commit succeeds or throws an exception**. Therefore, **never call `rollback(status)` after `commit(status)` throws an error**. Doing so can throw `IllegalTransactionStateException` and mask the original commit error.

### Right Pattern: Separate Body try from Commit

~~~java
TransactionStatus status = manager.getTransaction(definition);

try {
    writeBusinessData();
} catch (RuntimeException | Error original) {
    try {
        manager.rollback(status);
    } catch (TransactionException rollbackFailure) {
        rollbackFailure.addSuppressed(original);
        throw rollbackFailure;
    }
    throw original;
}

// Lies OUTSIDE the catch handling body errors.
manager.commit(status);
~~~

This snippet illustrates the pattern; section 8 provides a complete Java method using the same approach.

Things to remember:

1. If `getTransaction(...)` fails, you do not yet have a valid status to roll back.
2. If the body fails **before commit is called**, roll back once using the received status.
3. If rollback fails, **preserve the original body exception** (e.g., `rollbackFailure.addSuppressed(original)`).
4. If the body succeeds, call commit outside the body's catch block.
5. If commit throws an exception, do not roll back that status again; propagate the error to the caller for classification/reconciliation.
6. If the manager joined an outer transaction, the child scope's `commit(status)` call may not be the final physical commit.

### If Business Code Has Checked Exceptions

~~~java
TransactionStatus status = manager.getTransaction(definition);
try {
    operationThatMayThrowIOException();
} catch (IOException original) {
    try {
        manager.rollback(status);
    } catch (TransactionException rollbackFailure) {
        rollbackFailure.addSuppressed(original);
        throw rollbackFailure;
    }
    throw original;
}
manager.commit(status);
~~~

This snippet requires helpers and a method with `throws IOException`. With a manual manager, the developer decides whether to catch, roll back, and rethrow checked exceptions. There is no automatic "do not roll back on checked exceptions" rule unless your own code implements that decision.

## 7. Completion States: Commit, Rollback, and Unknown

### Commit Errors Can Leave the Outcome Indeterminate

~~~text
Application ------------------> Database: COMMIT
                      (connection lost before ACK)
Application <----------X------- Database: no response received
~~~

A DB may have already committed before the network dropped, or it may not have. Client-side exceptions alone cannot always determine which happened. **Never blindly retry a write with a new key**, especially for payment/transfer operations.

Safe approach:

1. Assign an **idempotency key** to the logical operation.
2. Place a unique constraint on the key and write it in the same transaction as the business change.
3. When commit outcome is unclear, reconcile via a new connection using the key and business state.
4. Retry only when the contract allows; limit attempts and use backoff.
5. Account for replica lag or the first transaction still finishing; a SELECT not seeing the row immediately is not absolute proof it did not commit.

### State Table

| Signal | What can be concluded |
| --- | --- |
| Commit on a new scope returns normally | Manager completed commit under the resource's contract |
| Rollback returns normally | Manager reports rollback of the corresponding scope finished |
| `UnexpectedRollbackException` | Coordinator rolled back instead of the expected commit |
| Rollback `TransactionSystemException` | Rollback success unconfirmed; needs investigation |
| Network/resource error at commit | Outcome may be unconfirmed; needs reconciliation |
| SQL constraint in body | That SQL failed, yet verify whether the transaction rolled back |
| Callback returns a business Outcome | Do not infer commit or rollback without checking status and completion |

Do not slap the UNKNOWN label on every error: `UnexpectedRollbackException` is a clearer rollback signal. With network errors right at commit time, however, you must be cautious.

## 8. Java 17+ Hands-On Lab: Business Errors, SQL Errors, and Simulated Commit/Rollback Faults

The lab is split into two parts:

- **Real Spring Boot + JDBC/H2:** verify database commit/rollback outcomes for callbacks.
- **Fake `PlatformTransactionManager` in a separate test suite:** inject commit and rollback faults to see which exception reaches the caller. The fake manager **does not talk to a DB**, so it cannot prove whether the DB committed or rolled back.

### 8.1. Maven Project

Create a Spring Boot 3.x Maven project compatible with Java 17+, selecting **JDBC API** (`spring-boot-starter-jdbc`) and **H2 Database**. Keep the complete Spring Initializr `pom.xml`. Dependencies:

~~~xml
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
~~~

This is a **dependencies excerpt**, not the full `pom.xml`.

Structure:

~~~text
src/main/
  java/com/example/txerrors/
    TxErrorApplication.java
    BusinessRuleException.java
    FaultSimulation.java
  resources/
    schema.sql
    application.properties
~~~

File `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE tx_event (
    id BIGINT PRIMARY KEY,
    description VARCHAR(120) NOT NULL
);
~~~

File `src/main/resources/application.properties`:

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:tx_error_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

In-memory H2 keeps the example independent of PostgreSQL/MySQL and starts with empty data on each new JVM launch.

### 8.2. BusinessRuleException.java

~~~java
package com.example.txerrors;

public final class BusinessRuleException extends RuntimeException {
    public BusinessRuleException(String code) {
        super(code);
    }
}
~~~

This is the **complete file**. The domain error code is placed in the message to keep stdout concise; in a real system, a dedicated `code` field can be used.

### 8.3. TxErrorApplication.java

~~~java
package com.example.txerrors;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionException;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@SpringBootApplication
public class TxErrorApplication {

    public static void main(String[] args) {
        SpringApplication.run(TxErrorApplication.class, args);
    }

    @Bean
    CommandLineRunner demonstrate(
            JdbcTemplate jdbc,
            PlatformTransactionManager manager) {

        return args -> {
            TransactionTemplate template = new TransactionTemplate(manager);

            // Callback and commit succeed.
            template.execute(status -> {
                insert(jdbc, 1L, "accepted");
                return null;
            });
            System.out.println("after success rows=" + count(jdbc));

            // Business error thrown from callback.
            try {
                template.execute(status -> {
                    insert(jdbc, 2L, "rejected");
                    throw new BusinessRuleException("LIMIT_EXCEEDED");
                });
            } catch (BusinessRuleException ex) {
                System.out.println("business code=" + ex.getMessage());
            }
            System.out.println("after business rows=" + count(jdbc));

            // Business Outcome without throwing an exception.
            Outcome denied = template.execute(status -> {
                insert(jdbc, 3L, "declined");
                status.setRollbackOnly();
                return new Outcome("DECLINED");
            });
            System.out.printf(
                "outcome=%s, rows=%d%n", denied.code(), count(jdbc));

            // SQL error detected inside the JDBC callback.
            try {
                template.execute(status -> {
                    insert(jdbc, 4L, "before duplicate");
                    insert(jdbc, 1L, "duplicate key");
                    return null;
                });
            } catch (DataIntegrityViolationException ex) {
                System.out.println(
                    "sql error=DataIntegrityViolationException");
            }
            System.out.println("after sql rows=" + count(jdbc));

            // Manual lifecycle: getTransaction/commit.
            insertManually(manager, jdbc, 5L);
            System.out.println("after manual rows=" + count(jdbc));

            // Tests exception paths only; does not touch real DB.
            FaultSimulation.run();
        };
    }

    private static void insert(
            JdbcTemplate jdbc, long id, String description) {
        jdbc.update(
            "INSERT INTO tx_event(id, description) VALUES (?, ?)",
            id, description);
    }

    private static int count(JdbcTemplate jdbc) {
        Integer result = jdbc.queryForObject(
            "SELECT COUNT(*) FROM tx_event", Integer.class);
        return result;
    }

    private static void insertManually(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc, long id) {

        DefaultTransactionDefinition definition =
            new DefaultTransactionDefinition();
        definition.setName("manual-insert");

        TransactionStatus status = manager.getTransaction(definition);

        try {
            insert(jdbc, id, "manual");
        } catch (RuntimeException | Error original) {
            try {
                manager.rollback(status);
            } catch (TransactionException rollbackFailure) {
                rollbackFailure.addSuppressed(original);
                throw rollbackFailure;
            }
            throw original;
        }

        // Lies OUTSIDE the body catch block.
        // If commit throws an error, DO NOT roll back status again.
        manager.commit(status);
    }

    private record Outcome(String code) {}
}
~~~

Explanation:

1. Id=1 commits, count=1.
2. Id=2 is written, then a domain exception escapes the callback; template rolls back, count stays 1.
3. Id=3 is written, then status is marked rollback-only and callback returns Outcome; count stays 1.
4. Id=4 is written, then inserting duplicate PK id=1 causes `DataIntegrityViolationException`; template rolls back id=4, count stays 1.
5. `insertManually` commits id=5 via the direct API, count=2.
6. `FaultSimulation.run()` does not use H2; it only simulates manager faults at commit/rollback.

In the demo, `CommandLineRunner` has no wrapping transaction, so each `template.execute` call uses default REQUIRED propagation and creates a new transaction on the single-DataSource setup. `JdbcTemplate` and the manager both manage H2.

### 8.4. FaultSimulation.java

~~~java
package com.example.txerrors;

import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.TransactionSystemException;
import org.springframework.transaction.support.SimpleTransactionStatus;
import org.springframework.transaction.support.TransactionTemplate;

final class FaultSimulation {

    private FaultSimulation() {}

    static void run() {
        // Callback succeeds; fake manager simulates a COMMIT fault.
        try {
            TransactionTemplate template =
                new TransactionTemplate(new FaultManager(Phase.COMMIT));

            template.execute(status -> "callback-success");
        } catch (TransactionSystemException ex) {
            System.out.println("commit phase=" + ex.getMessage());
            System.out.println(
                "commit had business error=" +
                (ex.getApplicationException() != null));
        }

        // Callback fails with business error; fake manager simulates a ROLLBACK fault.
        try {
            TransactionTemplate template =
                new TransactionTemplate(new FaultManager(Phase.ROLLBACK));

            template.execute(status -> {
                throw new BusinessRuleException("POLICY_DENIED");
            });
        } catch (TransactionSystemException ex) {
            System.out.println("rollback phase=" + ex.getMessage());
            System.out.println(
                "original business preserved=" +
                (ex.getApplicationException()
                    instanceof BusinessRuleException));
        }
    }

    private enum Phase { COMMIT, ROLLBACK }

    private static final class FaultManager
            implements PlatformTransactionManager {

        private final Phase failingPhase;

        FaultManager(Phase failingPhase) {
            this.failingPhase = failingPhase;
        }

        @Override
        public TransactionStatus getTransaction(
                TransactionDefinition definition) {
            // Fake status; does NOT open a DB transaction.
            return new SimpleTransactionStatus(true);
        }

        @Override
        public void commit(TransactionStatus status) {
            if (failingPhase == Phase.COMMIT) {
                throw new TransactionSystemException("COMMIT_FAULT");
            }
        }

        @Override
        public void rollback(TransactionStatus status) {
            if (failingPhase == Phase.ROLLBACK) {
                throw new TransactionSystemException("ROLLBACK_FAULT");
            }
        }
    }
}
~~~

**Important limitation:** `FaultManager` is a minimal test double. It does not open transactions, does not commit/roll back a DB, and does not represent all state/cleanup behavior of a production manager. It only lets you reproducibly verify `TransactionTemplate`'s **exception routing**.

In `TransactionTemplate`'s path when rollback throws `TransactionSystemException`, Spring saves the original callback exception via `initApplicationException(...)`. Thus the ROLLBACK_FAULT case can read back `BusinessRuleException`. The COMMIT_FAULT case had no prior business exception, so `getApplicationException() == null`.

### 8.5. Run and Expected Stdout

In the Maven directory containing `pom.xml`:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Ignoring Spring/H2 logs (which may include an intentional rollback error log from the fake), the lines printed by `System.out` in the program are:

~~~text
after success rows=1
business code=LIMIT_EXCEEDED
after business rows=1
outcome=DECLINED, rows=1
sql error=DataIntegrityViolationException
after sql rows=1
after manual rows=2
commit phase=COMMIT_FAULT
commit had business error=false
rollback phase=ROLLBACK_FAULT
original business preserved=true
~~~

**Reading the results:**

- `after business rows=1`: the business error caused the transaction containing id=2 to roll back.
- `outcome=DECLINED, rows=1`: rollback-only undid INSERT id=3 even though the callback returned normally.
- `after sql rows=1`: the SQL error inside the callback rolled back id=4.
- `after manual rows=2`: the direct manager committed id=5.
- `commit had business error=false`: the fake callback finished; the failure occurred solely at commit.
- `original business preserved=true`: the fake's rollback fault became the top-level exception, yet Spring preserved the domain error from the callback.

Never confuse results from a **fake** with a real-DB test.

## 9. How to Handle an Unclear Commit Outcome

A safe payment-creation design must not unconditionally retry when COMMIT loses its response. Safeguards:

- Assign an **idempotency key** to the logical request.
- Enforce a unique constraint on the key in the DB.
- Write the idempotency record in the **same transaction** as the business data.
- When commit is unclear, reconcile on a new connection by key and business state.
- Retry only when sufficient information is known or the protocol is idempotent; enforce attempt limits and backoff.
- Never treat an immediate SELECT on an unsynchronized replica as absolute proof the commit did not happen.

A deterministic business error such as `INVALID_AMOUNT` should usually not be retried with the same input. Deadlock/serialization errors or transient DB failures may retry the **entire transaction** when the operation is idempotent and a clear policy exists.

**Distinction:** `UnexpectedRollbackException` tells you the coordinator rolled back instead of committing; do not lump every commit error into UNKNOWN.

## 10. Classifying Errors for API Responses and Logging

You can design the business layer and transaction layer separately:

| Scenario | Typically appropriate response |
| --- | --- |
| Validation/domain rejection and rollback succeeded | Stable business code; 400/409/422 per API contract |
| Unexpected data-access error | Infrastructure error; usually 500/503 depending on context |
| Transaction begin/commit/rollback failure | Technical error; correlation ID, log phase and cause |
| Unconfirmed commit outcome | Pending-reconciliation status or technical error; do not claim writes were undone |
| Rollback failure masking business error | Prioritize infrastructure alert, preserve business code for diagnosis |
| Idempotency key already has a previous result | Reconcile and return the corresponding result per contract |

HTTP codes are only **design examples**, not fixed Spring mappings. In financial scenarios with an UNKNOWN outcome, never return a message saying "funds were not deducted" without sufficient proof.

Log pattern:

~~~text
operation=createOrder
correlationId=request-123
phase=ROLLBACK
errorFamily=TRANSACTION_SYSTEM
errorType=TransactionSystemException
originalBusinessCode=LIMIT_EXCEEDED
outcome=UNKNOWN
~~~

This is an **illustrative example**, not program stdout. Use `outcome=UNKNOWN` only when data state is genuinely unconfirmed. Avoid logging PII, credentials, access tokens, and unnecessary sensitive payloads.

## 11. Tests You Should Have

### Unit Tests with a Fake/Mock Manager

- `getTransaction(...)` throws: callback does not run and rollback is not called on a nonexistent status.
- Callback throws a business exception: template requests rollback.
- Callback finishes: template calls commit.
- Callback finishes, commit fails: commit exception propagates to the caller.
- Callback throws a business exception, rollback fails: top-level transaction exception and original business error are preserved.
- Manual code **does not call rollback again after a commit exception**.
- Manual code preserves the original exception via suppressed when rollback fails.

### Integration Tests with a Database

- Callback INSERTs and returns: data persists after commit.
- Callback INSERTs and throws a domain exception: data does not exist after rollback.
- Callback INSERTs and calls `setRollbackOnly()`: data does not exist even though the callback returns an Outcome.
- Callback INSERTs and then violates PK: data inserted before the error is gone after rollback.
- If using an ORM/DB with deferred constraints: also test flush/commit-time failures.
- If production uses PostgreSQL/MySQL, run integration tests against the exact target DBMS (e.g., Testcontainers).

**Spring Test note:** a test method with `@Transactional` can open an outer transaction and automatically roll back at the end of the test. It alters the semantics of `TransactionTemplate` REQUIRED and hides real physical commits. For tests meant to observe commits, run from a caller without a wrapping transaction.

## 12. Common Mental Traps

**Trap 1:** Every `RuntimeException` is a business rejection. `TransactionException` and `DataAccessException` are also runtime exceptions.

**Trap 2:** The callback returning `"SUCCESS"` means commit finished. The template commits **after the callback**.

**Trap 3:** `status.setRollbackOnly()` throws an exception. It only marks how completion should happen; the callback can still return an Outcome.

**Trap 4:** Putting `commit(status)` inside the body's try block and calling rollback in a shared catch. Commit already cleaned up the status; never roll back twice.

**Trap 5:** A business exception masked by a rollback exception means the business error never happened. Inspect `getApplicationException()` or suppressed/cause.

**Trap 6:** `TransactionSystemException` at commit guarantees the DB rolled back. Sometimes the outcome is indeterminate.

**Trap 7:** `UnexpectedRollbackException` means the DB committed. In fact, it reports an unexpected rollback.

**Trap 8:** A constraint error in the body means a commit error. Distinguish the phases; an ORM can detect constraints late at flush.

**Trap 9:** A `TransactionTemplate` lambda can directly throw any checked exception. The callback API does not declare checked exceptions.

**Trap 10:** Retrying with a new business ID immediately after a commit failure. This can cause duplicate writes if the first commit succeeded and only the response was lost.

**Trap 11:** A fake manager proves the database rolled back. Fakes only verify how the API routes exceptions.

**Trap 12:** Calling commit/rollback twice on a completed status. Each transaction scope needs one appropriate completion.

## 13. Self-Check Exercises

**Question 1.** Callback INSERTs id=10 and throws `BusinessRuleException`. Rollback succeeds. What does the caller receive?

**Answer:** `BusinessRuleException`, and the INSERT inside the transaction was rolled back; this is a domain error in the body, not a commit failure.

**Question 2.** Callback returns success and then commit throws an error. Should you return OK to the client?

**Answer:** No. You must handle the commit error and verify the outcome when necessary.

**Question 3.** Rollback fails after a business exception. What must be preserved?

**Answer:** Both the transaction error and the original domain error; on the template path you can inspect `TransactionSystemException.getApplicationException()`.

**Question 4.** Why shouldn't you roll back inside a catch block that wraps commit too?

**Answer:** If the error came from commit, the status is already completed/cleaned up; calling rollback again can throw `IllegalTransactionStateException` and mask the commit error.

**Question 5.** Callback returns `DECLINED` after an INSERT without calling rollback-only. Is the data guaranteed to be undone?

**Answer:** No. Returning normally from the callback can lead to a commit.

**Question 6.** `UnexpectedRollbackException` occurs when outer commits after an inner REQUIRED marked rollback-only. What is T1's state?

**Answer:** T1 was rolled back instead of committing as expected. You need to find the scope that marked rollback-only.

**Question 7.** The COMMIT response was lost after the application sent the commit command. Can you retry with a new key?

**Answer:** You should not. Reconcile by idempotency key and avoid executing the logical command twice.

**Question 8.** JDBC throws `DataIntegrityViolationException` for a duplicate PK right inside the callback. Is that a commit error?

**Answer:** No, in this sequence it occurred in the body; the template requests rollback. A technology with deferred flushing might detect a similar error at commit.

## 14. Checklist and Conclusion

- [ ] Clearly separate domain errors, SQL/body errors, begin errors, commit errors, and rollback errors.
- [ ] Do not mistake callback success for commit success.
- [ ] A business Outcome after partial writes sets `setRollbackOnly()` if cancellation is needed.
- [ ] Rollback errors do not discard the original business error.
- [ ] `PlatformTransactionManager.commit(status)` sits outside the catch block meant solely for the body.
- [ ] **Never call rollback on the same status after a commit exception**.
- [ ] Never reuse a completed `TransactionStatus`.
- [ ] Understand propagation and physical transaction ownership.
- [ ] Do not treat every runtime exception as a business error.
- [ ] When commit outcome is unclear: have idempotency and reconciliation.
- [ ] Maintain unit tests with fakes and integration tests with a real DB.
- [ ] Logs include phase, correlation ID, and error chain without exposing sensitive data.

**Conclusion:** business errors explain *which domain rule failed*, while commit/rollback errors explain *whether the transaction infrastructure could complete or undo the work*. Both can occur in a single execution. `TransactionTemplate` handles boilerplate yet can still throw exceptions after the callback; `PlatformTransactionManager` grants direct control yet requires separating try/catch blocks properly.

The single most important point: **when `commit(status)` throws an exception, never roll back that status again**. If the commit outcome is unconfirmed, never assert the DB rolled back; reconcile and retry safely.

### Official References

- Spring Framework — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html
- Spring API — PlatformTransactionManager: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html
- Spring API — TransactionTemplate: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html
- Spring API — TransactionSystemException: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/TransactionSystemException.html
- Spring API — UnexpectedRollbackException: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/UnexpectedRollbackException.html
- Spring Framework — Transaction Propagation: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring source — TransactionTemplate.java: https://github.com/spring-projects/spring-framework/blob/main/spring-tx/src/main/java/org/springframework/transaction/support/TransactionTemplate.java
