# Managing Commit, Rollback, and Exceptions at Each Stage with Spring's Direct Transaction API

## 1. Goal: Controlling a Transaction from Start to Finish

In Spring Framework, besides declaring `@Transactional`, an application can actively control a transaction with the imperative API:

- `PlatformTransactionManager`: start/join, commit, and roll back a transaction.
- `TransactionDefinition`: describe propagation, isolation, timeout, read-only, and transaction name.
- `TransactionStatus`: scope-specific status, including whether the transaction is new or participating, rollback-only, completed, and savepoint when supported.
- `TransactionTemplate`: wrap begin, callback execution, commit/rollback, and exception handling to reduce boilerplate.

The topic **"Managing commit, rollback, and exceptions at each stage"** requires distinguishing moments that are very easy to mishandle:

1. **Before having a `TransactionStatus`**: `getTransaction(...)` may fail while looking up or starting a transaction; there is no valid status to roll back.
2. **Inside the business body**: an error may be a checked exception, an unchecked exception, or an `Error`. With the direct API, **your own code** decides whether to call `commit` or `rollback`; do not mechanically assume `@Transactional`'s default rollback rule applies.
3. **During commit**: commit may succeed, detect rollback-only, or throw an error from flush, synchronization, database, or the transaction manager. Under the `PlatformTransactionManager` contract, once **`commit(status)` has been called and that call completes (even if it finishes by throwing an exception)**, the transaction status is already completed/cleaned up. **Do not call `rollback(status)` to "fix" a commit that threw an error**.
4. **During rollback**: rollback can also throw a `TransactionException`/system error. You must not lose track of the original exception and must not reuse an already completed status.
5. **After completion**: proceed with post-transaction steps only based on the actual completion outcome. The fact that an SQL UPDATE ran does not mean the transaction committed.

The core rule of this lesson: **each transaction status must be completed only once** by one appropriate commit or rollback call; and an exception during the completion stage must be handled **differently** from an exception thrown by business code.

## 2. Four Objects and Responsibilities in Spring's Imperative Transaction API

| Object/API | Responsibility | What not to confuse it with |
| --- | --- | --- |
| `TransactionDefinition` | Defines propagation, isolation, timeout, read-only, name | Only a request; not a running transaction |
| `PlatformTransactionManager.getTransaction(def)` | Returns `TransactionStatus` representing a new/participating scope per definition | Does not always open a new physical transaction |
| `TransactionStatus` | Reports `isNewTransaction()`, `isRollbackOnly()`, `isCompleted()`; allows `setRollbackOnly()` | Not an object to reuse for beginning/committing multiple times |
| `PlatformTransactionManager.commit(status)` | Completes scope according to state, may roll back if rollback-only | "Calling commit" does not guarantee the DB actually committed |
| `PlatformTransactionManager.rollback(status)` | Requests scope rollback; if joining an outer transaction, may only mark rollback-only | Not every rollback rolls back a separate physical transaction |
| `TransactionTemplate.execute(...)` | Runs a callback inside a transaction, handling lifecycle and exceptions | Does not let business code manually commit the callback's status |
| `JdbcTransactionManager` / `DataSourceTransactionManager` | JDBC transaction manager implementation for a `DataSource` | Do not substitute for `ReactiveTransactionManager` in R2DBC flows |

Example of initializing a definition:

~~~java
DefaultTransactionDefinition def = new DefaultTransactionDefinition();
def.setName("checkout-manual");
def.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
def.setIsolationLevel(TransactionDefinition.ISOLATION_READ_COMMITTED);
def.setTimeout(15);
def.setReadOnly(false);
~~~

This is an excerpt requiring imports `org.springframework.transaction.support.DefaultTransactionDefinition` and `org.springframework.transaction.TransactionDefinition`; it is not a standalone program. Properties **isolation/timeout** generally apply only when the manager **actually starts a new transaction**, rather than altering an existing physical transaction when `REQUIRED` joins it.

### 2.1. Choosing the Right Manager and Resources

With Spring JDBC, data-access code should use `JdbcTemplate`/`DataSourceUtils` with the same `DataSource` managed by the transaction manager. If a DAO opens `new Connection` from another source or uses a different `DataSource`, those SQL statements may fall outside the controlled transaction.

If there are multiple managers, inject or qualify the right bean; `PlatformTransactionManager` is an **imperative** abstraction. For reactive database flows, use `ReactiveTransactionManager`/`TransactionalOperator` and Reactor subscriber context instead of copying thread-local-based imperative patterns.

## 3. Which Stages Make Up the Full Lifecycle?

### Stage A — Obtain or Start the Transaction

~~~java
TransactionStatus status = txManager.getTransaction(def);
~~~

With `PROPAGATION_REQUIRED`, the manager joins an existing transaction or opens a new physical transaction. A JDBC manager may acquire a connection, disable auto-commit, configure isolation/read-only, and bind the resource to the thread.

**Errors at Stage A** typically belong to:

- `CannotCreateTransactionException`: unable to start the transaction (e.g., failing to acquire a connection).
- `IllegalTransactionStateException`: definition conflicts with current state, e.g., `MANDATORY` when no transaction exists.
- `InvalidIsolationLevelException`/other backend errors: requirement not supported by manager/resource.
- `TransactionException` in general: failure while finding or creating the status.

When `getTransaction(...)` **throws an exception before returning a status**, the application **does not yet hold a valid status**. Never write `txManager.rollback(status)` in a catch block when `status` was never assigned, and never fabricate a dummy status. Let the manager handle cleanup appropriate for the begin phase and propagate the error to the caller.

### Stage B — Execute Business Logic Within the Scope

Once a status is obtained, the application runs SQL and business logic. There are three paths:

- **Success:** request commit after the body finishes normally.
- **Failure requiring cancellation:** request rollback, then propagate the original exception (or a meaningful business error).
- **Handle error and choose a different outcome:** an **explicit** business policy may decide to commit even after catching a checked error, or mark rollback-only and return a result. Never let accidental exception swallowing decide the outcome.

Exceptions from SQL may be Spring `DataAccessException` (unchecked); `IOException` or checked business exceptions are another category. **When using `PlatformTransactionManager` directly, `@Transactional`'s `rollbackFor` does not run on this code**: the application itself is responsible for calling the right completion method.

### Stage C — Decide Completion

Only **after the body** do you choose one of:

~~~java
txManager.commit(status);   // When wanting to commit and not yet completed.
~~~

or:

~~~java
txManager.rollback(status); // When wanting to roll back and not yet completed.
~~~

These two lines are **mutually exclusive choices**, never executed sequentially on the same `TransactionStatus`. `commit` may also execute a rollback if the status had `setRollbackOnly()` called or if the physical transaction was marked global rollback-only.

### Stage D — Commit/Rollback, Synchronization, and Cleanup

In JDBC, completion can include before-commit/before-completion callbacks, flushing, physical connection commit or rollback, after-commit/after-completion callbacks, and connection cleanup/release. Exact order and behavior depend on the manager, resource, and whether joining or opening a new transaction.

**API invariant:** once `PlatformTransactionManager.commit(status)` returns, **whether normally or by throwing an exception**, the transaction is considered completed/cleaned up from the manager's perspective; you must not roll back that status again. Likewise, never continue by committing an already rolled-back status.

## 4. Decision Diagram Across Stages

~~~mermaid
flowchart TD
    A["Receive business request"] --> B["txManager.getTransaction(definition)"]
    B --> C{"Begin succeeded?"}
    C -->|"No"| D["Report begin error<br/>NO status to roll back"]
    C -->|"Yes"| E["Have TransactionStatus"]
    E --> F["Execute business logic"]
    F --> G{"Body error needing rollback?"}
    G -->|"Yes"| H["txManager.rollback(status)"]
    H --> I{"Rollback succeeded?"}
    I -->|"Yes"| J["Propagate original error"]
    I -->|"No"| K["Report rollback error;<br/>preserve original as cause/suppressed"]
    G -->|"No"| L["txManager.commit(status)"]
    L --> M{"Commit succeeded?"}
    M -->|"Yes"| N["Complete according to transaction outcome"]
    M -->|"No"| O["Report commit error;<br/>DO NOT roll back status again"]
    N --> P["Return result / continue after completion"]
~~~

**Do not apply this diagram mechanically to the case "body had an error but business policy deliberately allows commit"**: state the policy explicitly and only commit when the resource remains valid. Similarly, `commit(status)` on a **rollback-only status** can lead to a rollback; do not label the outcome "COMMITTED" merely because no exception was thrown.

## 5. Safe Code Pattern for the Direct API: Commit Outside the Body Catch

A crucial pattern is **not placing `commit(status)` inside the same `try` block whose `catch` calls rollback**, because that catch could intercept an exception from commit and attempt to roll back an already completed status.

### 5.1. Wrong: Catch Wrapping Commit and Rolling Back a Second Time

~~~java
// ANTI-PATTERN — do not use in applications:
TransactionStatus status = manager.getTransaction(definition);
try {
    executeBusinessLogic();
    manager.commit(status); // May throw TransactionException at completion.
} catch (RuntimeException ex) {
    manager.rollback(status); // WRONG if the exception came from commit!
    throw ex;
}
~~~

This is an illustrative snippet without imports/definitions. Under the `PlatformTransactionManager` contract, if `commit` throws an error, the transaction has already been cleaned up; a subsequent `rollback(status)` can throw `IllegalTransactionStateException` ("already completed") and mask the real cause of the commit failure.

### 5.2. Right: Wrap Only the Body with Rollback Catch, Commit Afterward

~~~java
TransactionStatus status = manager.getTransaction(definition);
try {
    executeBusinessLogic();
} catch (RuntimeException | Error original) {
    try {
        manager.rollback(status);
    } catch (TransactionException rollbackFailure) {
        original.addSuppressed(rollbackFailure);
    }
    throw original;
}
manager.commit(status); // Lies OUTSIDE the business body catch.
~~~

This is also an excerpt pattern; it requires manager, definition, and helpers. It demonstrates a **best-effort strategy to preserve the original exception**: when rollback fails, attach the rollback error as a suppressed exception and still throw the original. Depending on product requirements, you could instead make the rollback exception primary and attach original as cause; the mandatory point is **never lose both**.

If `getTransaction(def)` throws, execution has not entered `try`, so rollback is not called. If `commit(status)` throws, execution does not enter the catch that calls rollback. If the body fails, rollback is invoked **once** before rethrowing.

**Do not assume only RuntimeException needs rollback.** Catching `RuntimeException | Error` is a common policy. If a business API uses a checked exception to signal a failure requiring rollback, catch that checked type or use an explicit callback/lambda mechanism.

## 6. Checked Exceptions: With the Direct API, Rollback Decisions Are Not Automatic

With declarative `@Transactional`, the default rollback rule usually rolls back on `RuntimeException`/`Error` and does not automatically roll back on checked `Exception` (configurable). With the direct API, however:

~~~java
TransactionStatus status = manager.getTransaction(definition);
try {
    performJdbcWrites();
    readExternalFile(); // may throw IOException
} catch (IOException ex) {
    manager.rollback(status); // You yourself choose to roll back when IOException occurs.
    throw ex;
} catch (RuntimeException | Error ex) {
    manager.rollback(status);
    throw ex;
}
manager.commit(status);
~~~

This is an illustrative excerpt, not a standalone runnable file. Under a business policy requiring atomicity, `IOException`, even though checked, still triggers rollback because the application **explicitly calls rollback**.

Conversely, sometimes a checked exception means "data write succeeded, but a warning needs to be reported". If you verify that the DB operations are valid and the resource can still commit, the code can **catch the checked exception, hold onto it to report to the caller, call commit, and only then throw it**. In that case the caller sees the exception yet the data **has committed** — document the business contract clearly and test the outcome rather than choosing at random.

**Warning:** "Commit on checked exceptions" is not an enforced rule of `PlatformTransactionManager`. The transaction state may be rollback-only or the DB may have rejected SQL, making commit impossible even if you try.

## 7. TransactionStatus: States You Must Read Correctly

Several useful APIs of `TransactionStatus` and `TransactionExecution`:

| API | Meaning | Note |
| --- | --- | --- |
| `isNewTransaction()` | Does this scope represent a new physical transaction? | Usually false for participating `REQUIRED` |
| `isRollbackOnly()` | Is the transaction/status marked rollback-only? | True does not mean rollback has already completed |
| `setRollbackOnly()` | Actively requests rollback when the scope completes | Does not immediately roll back on this call |
| `isCompleted()` | Has the scope status completed according to the manager? | Do not use status to commit/rollback a second time |
| `hasSavepoint()` | Does the status have a savepoint? | Requires manager/driver support for nested/savepoint |
| `flush()` | Hint to flush underlying resources if supported | Not equivalent to a physical commit |

**Distinguish rollback-only from an executed rollback:**

~~~java
TransactionStatus status = manager.getTransaction(definition);
status.setRollbackOnly();
manager.commit(status);  // May perform rollback instead of commit.
~~~

If the scope is a **new transaction** and code deliberately sets local rollback-only, `commit(status)` can roll back **without necessarily throwing `UnexpectedRollbackException`**. By contrast, if an inner `REQUIRED` marks the shared physical transaction global rollback-only and outer still tries to commit, outer can receive `UnexpectedRollbackException`. Both situations share the "do not commit" direction, yet differ in outer expectations.

Do not use `isCompleted()` to infer "database commit succeeded": it only says the transaction **status has completed**. A rolled-back status is also completed, and a failed commit still requires cleanup.

## 8. Failures at Begin, During Body, at Commit, and at Rollback

| Stage | Example exceptions | Is a status available? | What to do |
| --- | --- | --- | --- |
| `getTransaction` | `CannotCreateTransactionException` when pool is out of connections | No status returned yet | Report begin error; do not roll back a nonexistent status |
| Body/SQL | `DataAccessException`, `IllegalArgumentException`, `IOException` | Status exists | Apply policy: roll back or handle explicitly; do not swallow errors inadvertently |
| `commit(status)` | `UnexpectedRollbackException`, `TransactionSystemException`, pre-commit flush error | Status will be completed/cleaned up | Do not call rollback on the same status after commit failure |
| `rollback(status)` | `TransactionSystemException`/resource failure | Status is being completed | Do not repeat rollback; preserve both original error and rollback error |
| After commit | Separate HTTP/Kafka/email error | DB transaction may have already committed | Cannot undo commit by rolling back the same status; use outbox/compensation |
| Using status a 2nd time | `IllegalTransactionStateException` "already completed" | Completed | Fix code structure: one completion per status |

### 8.1. A Commit Failure Does Not Always Mean the Same Thing

When `commit(status)` throws an exception, the source of failure can belong to multiple categories:

- **Before-commit/flush exception:** callback or ORM flush failed before DB commit; the manager typically rolls back or handles accordingly.
- **Global rollback-only:** a participating logical scope rendered the physical transaction uncommittable, leading to `UnexpectedRollbackException` when outer attempts to commit.
- **Database commit/system failure:** broken connection, indeterminate network outcome, or heuristic decision from a transaction coordinator. The physical outcome can be **uncertain** from the client side if communication drops at the critical moment.
- **After-commit callback failure:** a callback after DB commit may fail; an exception propagated to the caller at this point **does not mean** the data failed to commit.

Therefore do not log all commit exceptions as "rolled back" without evidence from the manager/resource. Especially in network failures, never retry a write transaction lacking an idempotency key or unique invariant.

### 8.2. Rollback Failure Does Not Allow Assuming Success

If a business exception occurs and the application calls `rollback(status)`, yet rollback also throws an error, both must be recorded. Do not reuse the failed status to arbitrarily repeat commit/rollback. In systems with external side effects, the transaction manager does not automatically undo emails, HTTP calls, or Kafka publishes already sent.

`TransactionSystemException` may hold an application exception in some cases; however, do not rely on every exception having a useful `getCause()`. Preserving both the original and rollback failures in logs/exception chains is a design responsibility.

## 9. TransactionTemplate: Spring's Recommended Choice for Imperative Flows

Spring generally recommends `TransactionTemplate` over manually writing `getTransaction → try/catch → commit/rollback` boilerplate when the application just needs a clear transaction scope.

~~~java
TransactionTemplate template = new TransactionTemplate(manager);
template.executeWithoutResult(status -> {
    jdbc.update("UPDATE ledger SET balance = balance + 10 WHERE id = 1");
});
~~~

This is an excerpt inside a bean injected with `PlatformTransactionManager` and `JdbcTemplate`. The template manages lifecycle and exception handling:

- Callback **returns normally**: the template attempts to complete by committing.
- Callback throws **RuntimeException** or **Error**: the template rolls back and propagates the exception, unless rollback itself fails.
- Callback calls `status.setRollbackOnly()` and returns: the template requests rollback when the scope ends without the callback needing to throw an exception.
- Callback wants to return a value: use `template.execute(status -> result)`.
- Callback must not directly call `manager.commit(status)` or `manager.rollback(status)` on the status owned by the template, because the template already owns completion.

`TransactionTemplate` implements `TransactionOperations`; shared instances can be thread-safe **when configuration is not modified while in use**. If you need different propagation/timeout/isolation settings, create separate templates per policy rather than mutating a shared instance concurrently.

### 9.1. Checked Exceptions Inside Callbacks

`TransactionCallback<T>` does not declare arbitrary checked exceptions like `IOException` in its lambda signature. If an operation can throw a checked exception, the application must:

- Catch inside the callback, call `status.setRollbackOnly()`, and return an appropriate error result.
- Or wrap it in an unchecked exception with cause so the template rolls back by convention.
- Or use the direct API when you need to preserve the checked exception and an explicit policy.

Do not catch `IOException` and return a success DTO while forgetting to mark rollback-only if the business logic requires atomicity.

### 9.2. Programmatic TransactionTemplate Also Obeys Propagation

~~~java
TransactionTemplate independent = new TransactionTemplate(manager);
independent.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
independent.executeWithoutResult(status -> {
    // Work in a physical transaction independent of outer if any.
});
~~~

This is an illustrative excerpt. `REQUIRES_NEW` still suspends outer and may require an extra connection from the pool while outer holds a connection. The template does not merge two physical transactions into one simply because both run on the same thread.

## 10. Participating REQUIRED Transactions: Inner Rollback Is Not an Isolated Rollback

A key shift when programming directly is that **not every status represents a new physical transaction**. For example:

~~~java
DefaultTransactionDefinition def = new DefaultTransactionDefinition();
def.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);

TransactionStatus outer = manager.getTransaction(def); // Opens T1 when none exists.
TransactionStatus inner = manager.getTransaction(def); // Joins T1.

manager.rollback(inner); // Usually only marks T1 rollback-only.
manager.commit(outer);   // May throw UnexpectedRollbackException.
~~~

This excerpt assumes the same thread, same manager, and no other errors. `rollback(inner)` on a participating status does **not** immediately roll back only inner's SQL and let outer commit normally. With managers based on `AbstractPlatformTransactionManager` in default mode, a failing participating scope can mark **global rollback-only**. When outer attempts to commit T1, Spring rolls back everything and throws `UnexpectedRollbackException` to avoid returning a false "success".

If inner genuinely needs independent rollback/commit, `REQUIRES_NEW` creates a separate physical transaction. If partial rollback within the same physical transaction is needed, `PROPAGATION_NESTED` can use JDBC savepoints when supported; do not assume nested commits independently.

## 11. REQUIRES_NEW, Connection Pools, and Failures at the Begin Stage

An outer transaction already using JDBC connection C1 can continue **holding C1** while suspended. Inner `REQUIRES_NEW` needs a second connection C2 from the pool to open a new physical transaction.

- If the pool has a maximum of **one** connection and outer is holding C1, inner can wait for `connectionTimeout` and fail **right at `getTransaction`**; at that moment there is no inner `TransactionStatus` to roll back.
- If inner succeeds and commits, a subsequent outer rollback **does not undo** inner's committed work.
- If outer holds a lock on a row that inner tries to update, inner can wait on a database lock even when the pool has enough C2 connections.
- Do not change every `REQUIRED` to `REQUIRES_NEW` just to avoid rollback-only side effects without examining atomicity, locking, and connection budget.

Choose propagation based on business rules, test against a production-like DB/pool, and monitor active/idle/pending connections and transaction hold times.

## 12. Synchronization Callbacks: Observing Before/After Completion Properly

Some systems need extra behavior after commit or after rollback, such as updating caches, emitting notifications, or recording metrics. Spring provides `TransactionSynchronizationManager` and `TransactionSynchronization` when transaction synchronization is active.

Illustrative excerpt **inside an imperative transaction with active synchronization**:

~~~java
if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                // Only after the transaction commits successfully.
            }

            @Override
            public void afterCompletion(int status) {
                if (status == STATUS_COMMITTED) {
                    // Transaction completed with committed status.
                } else if (status == STATUS_ROLLED_BACK) {
                    // Transaction completed with rolled-back status.
                } else {
                    // STATUS_UNKNOWN: manager cannot confirm a certain outcome.
                }
            }
        }
    );
}
~~~

Requires imports `org.springframework.transaction.support.TransactionSynchronizationManager` and `org.springframework.transaction.support.TransactionSynchronization`. This is illustrative code, not a standalone class.

**Avoid four misconceptions:**

1. `beforeCommit` can run **before** the DB actually commits; do not emit irreversible events there just because the callback fired.
2. `afterCommit` runs after the main transaction commits, yet older resources may still be bound to the thread during some cleanup phases. If a callback must write to the DB in its own transaction, deliberately use a `REQUIRES_NEW` scope instead of implicitly expecting a second commit.
3. An exception after DB commit cannot be "fixed" by rolling back an already completed status.
4. `afterCompletion(STATUS_UNKNOWN)` requires handling uncertainty according to the manager's semantics. Never claim with certainty that data committed or rolled back when it is genuinely unknown.

For events/messages requiring guaranteed coordination with DB writes, consider a **transactional outbox** instead of sending directly in before-commit or after-commit without retry/idempotency.

## 13. Standalone Runnable Example: Java 17+, Spring Boot, JDBC, H2

### 13.1. Purpose of the Example

This CLI application uses **Spring Boot 3.3.5 / Spring Framework 6.1.x**, Java 17+, Maven, `JdbcTransactionManager`, `JdbcTemplate`, and H2 in-memory. It needs no HTTP server or external database. A `ledger` table starts with two rows: id 1 with balance **100**, id 2 with balance **1000**.

The program sequentially demonstrates:

1. Committing a transaction manually.
2. Business RuntimeException triggering **manual rollback**.
3. Checked `IOException` triggering **manual rollback** because the application chooses that policy.
4. Checked `IOException` retained to report to the caller while the application **deliberately commits** valid data.
5. `setRollbackOnly` followed by commit: the new transaction rolls back instead of committing.
6. `TransactionTemplate` committing a successful callback.
7. Template rolling back when the callback throws an unchecked exception.
8. Template rolling back when the callback returns normally after calling `setRollbackOnly`.
9. Inner `REQUIRED` joining the outer physical transaction; rolling back inner leads to `UnexpectedRollbackException` when outer tries to commit.
10. Inner `REQUIRES_NEW` committing independently on row id 2, after which outer rolls back its part on row id 1.

Nothing depends on AOP intercepting self-invocation: transactions are **all opened via the direct API**, and `CommandLineRunner` has no `@Transactional`.

### 13.2. Three-File Structure

~~~text
programmatic-tx-demo/
├── pom.xml
└── src/main/java/example/programmatictx/
    ├── ProgrammaticTxDemoApplication.java
    └── TxScenarios.java
~~~

### 13.3. pom.xml

~~~xml
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

    <groupId>example</groupId>
    <artifactId>programmatic-tx-demo</artifactId>
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

`spring-boot-starter-aop` is not needed because this example **uses the direct transaction API**, requiring no `@Transactional` proxy.

### 13.4. src/main/java/example/programmatictx/ProgrammaticTxDemoApplication.java

~~~java
package example.programmatictx;

import java.io.IOException;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.UnexpectedRollbackException;

@SpringBootApplication
public class ProgrammaticTxDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ProgrammaticTxDemoApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, TxScenarios cases) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE ledger (id INT PRIMARY KEY, balance INT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO ledger (id, balance) VALUES (?, ?)", 1, 100
            );
            jdbc.update(
                "INSERT INTO ledger (id, balance) VALUES (?, ?)", 2, 1000
            );
            System.out.println("START=" + balances(jdbc));

            cases.manualCommit();
            System.out.println("AFTER_MANUAL_COMMIT=" + balances(jdbc));

            try {
                cases.manualRuntimeRollback();
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT_RUNTIME=" + ex.getMessage());
            }
            System.out.println("AFTER_RUNTIME_ROLLBACK=" + balances(jdbc));

            try {
                cases.manualCheckedRollback();
            } catch (IOException ex) {
                System.out.println("CAUGHT_CHECKED_ROLLBACK=" + ex.getMessage());
            }
            System.out.println("AFTER_CHECKED_ROLLBACK=" + balances(jdbc));

            try {
                cases.manualCheckedCommit();
            } catch (IOException ex) {
                System.out.println("CAUGHT_CHECKED_COMMIT=" + ex.getMessage());
            }
            System.out.println("AFTER_CHECKED_COMMIT=" + balances(jdbc));

            cases.manualMarkRollbackOnly();
            System.out.println("AFTER_MARK_ONLY=" + balances(jdbc));

            cases.templateCommit();
            System.out.println("AFTER_TEMPLATE_COMMIT=" + balances(jdbc));

            try {
                cases.templateRuntimeRollback();
            } catch (IllegalStateException ex) {
                System.out.println("CAUGHT_TEMPLATE=" + ex.getMessage());
            }
            System.out.println("AFTER_TEMPLATE_RUNTIME=" + balances(jdbc));

            cases.templateMarkRollbackOnly();
            System.out.println("AFTER_TEMPLATE_MARK=" + balances(jdbc));

            try {
                cases.participatingRollback();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                    "CAUGHT_UNEXPECTED=" + ex.getClass().getSimpleName()
                );
            }
            System.out.println("AFTER_PARTICIPATING=" + balances(jdbc));

            cases.independentRequiresNew();
            System.out.println("AFTER_REQUIRES_NEW=" + balances(jdbc));
        };
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer one = jdbc.queryForObject(
            "SELECT balance FROM ledger WHERE id = ?", Integer.class, 1
        );
        Integer two = jdbc.queryForObject(
            "SELECT balance FROM ledger WHERE id = ?", Integer.class, 2
        );
        return one + "/" + two;
    }
}
~~~

### 13.5. src/main/java/example/programmatictx/TxScenarios.java

~~~java
package example.programmatictx;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.TransactionException;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Component
public class TxScenarios {

    private final JdbcTemplate jdbc;
    private final PlatformTransactionManager manager;
    private final TransactionTemplate template;

    public TxScenarios(
            JdbcTemplate jdbc, PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.manager = manager;
        this.template = new TransactionTemplate(manager);
    }

    private TransactionStatus begin(String name) {
        DefaultTransactionDefinition def = new DefaultTransactionDefinition();
        def.setName(name);
        def.setPropagationBehavior(
            TransactionDefinition.PROPAGATION_REQUIRED
        );
        return manager.getTransaction(def);
    }

    private void add(int id, int delta) {
        jdbc.update(
            "UPDATE ledger SET balance = balance + ? WHERE id = ?",
            delta, id
        );
    }

    private void failChecked() throws IOException {
        throw new IOException("checked-failed");
    }

    // If rollback fails, preserve original and attach rollbackFailure.
    // Must not call rollback repeatedly on that status.
    private void rollbackPreserving(
            TransactionStatus status, Throwable original) {
        try {
            manager.rollback(status);
        } catch (TransactionException rollbackFailure) {
            original.addSuppressed(rollbackFailure);
        }
    }

    // Case 1: complete successfully.
    public void manualCommit() {
        TransactionStatus status = begin("manualCommit");
        try {
            add(1, 10);
        } catch (RuntimeException | Error original) {
            rollbackPreserving(status, original);
            throw original;
        }
        manager.commit(status); // Outside catch so we do not roll back after a commit error.
    }

    // Case 2: RuntimeException -> application actively rolls back.
    public void manualRuntimeRollback() {
        TransactionStatus status = begin("manualRuntimeRollback");
        try {
            add(1, 20);
            throw new IllegalStateException("runtime-failed");
        } catch (RuntimeException | Error original) {
            rollbackPreserving(status, original);
            throw original;
        }
    }

    // Case 3: checked IOException -> application CHOOSES rollback.
    public void manualCheckedRollback() throws IOException {
        TransactionStatus status = begin("manualCheckedRollback");
        try {
            add(1, 30);
            failChecked();
        } catch (IOException original) {
            rollbackPreserving(status, original);
            throw original;
        } catch (RuntimeException | Error original) {
            rollbackPreserving(status, original);
            throw original;
        }
        manager.commit(status);
    }

    // Case 4: checked IOException treated as warning:
    // application deliberately commits before throwing the checked exception.
    public void manualCheckedCommit() throws IOException {
        TransactionStatus status = begin("manualCheckedCommit");
        IOException pending = null;
        try {
            add(1, 40);
            failChecked();
        } catch (IOException ex) {
            pending = ex;
        } catch (RuntimeException | Error original) {
            rollbackPreserving(status, original);
            throw original;
        }
        manager.commit(status); // If commit fails, IOException does not mask the commit failure.
        if (pending != null) {
            throw pending;
        }
    }

    // Case 5: local rollback-only, not immediately rolled back.
    public void manualMarkRollbackOnly() {
        TransactionStatus status = begin("manualMarkRollbackOnly");
        try {
            add(1, 50);
            status.setRollbackOnly();
            System.out.println("MARK_ONLY=" + status.isRollbackOnly());
        } catch (RuntimeException | Error original) {
            rollbackPreserving(status, original);
            throw original;
        }
        manager.commit(status); // Manager rolls back instead of committing.
    }

    // Case 6: template automatically commits normal callback completion.
    public void templateCommit() {
        template.executeWithoutResult(status -> add(1, 60));
    }

    // Case 7: template rolls back when callback throws an unchecked exception.
    public void templateRuntimeRollback() {
        template.executeWithoutResult(status -> {
            add(1, 70);
            throw new IllegalStateException("template-failed");
        });
    }

    // Case 8: callback returns normally but marks rollback-only.
    public void templateMarkRollbackOnly() {
        template.executeWithoutResult(status -> {
            add(1, 80);
            status.setRollbackOnly();
        });
    }

    // Case 9: two logical REQUIRED scopes on the same physical transaction.
    public void participatingRollback() {
        TransactionStatus outer = begin("outerRequired");
        try {
            add(1, 90);
            TransactionStatus inner = begin("innerRequired");
            try {
                add(1, 100);
            } catch (RuntimeException | Error original) {
                rollbackPreserving(inner, original);
                throw original;
            }
            manager.rollback(inner); // Marks global rollback-only, does not commit.
            add(1, 5);
            System.out.println(
                "OUTER_ROLLBACK_ONLY=" + outer.isRollbackOnly()
            );
        } catch (RuntimeException | Error original) {
            rollbackPreserving(outer, original);
            throw original;
        }
        manager.commit(outer); // Outer tries to commit, but shared T1 is rolled back.
    }

    // Case 10: inner physical transaction commits independently.
    public void independentRequiresNew() {
        TransactionStatus outer = begin("outerForNew");
        try {
            add(1, 1);
            DefaultTransactionDefinition def =
                new DefaultTransactionDefinition();
            def.setName("innerRequiresNew");
            def.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW
            );
            TransactionStatus inner = manager.getTransaction(def);
            try {
                add(2, 5); // Different row to avoid row-lock dependency.
            } catch (RuntimeException | Error original) {
                rollbackPreserving(inner, original);
                throw original;
            }
            manager.commit(inner); // Completes inner status, resumes outer.
        } catch (RuntimeException | Error original) {
            rollbackPreserving(outer, original);
            throw original;
        }
        manager.rollback(outer); // Undoes +1 on id=1, keeps +5 committed on id=2.
    }
}
~~~

**Important checks in the code:**

- `begin(name)` always calls `getTransaction` **before** the `try/catch` handling the business body; if begin fails, there is no status to roll back.
- In methods completing via commit, `manager.commit(status)` sits **after** the body's rollback catch.
- For errors from the body, `rollbackPreserving` keeps original as the primary exception and adds rollbackFailure to `getSuppressed()` if rollback itself fails. This is an intentional logging policy, not mandatory for every application.
- `manualCheckedRollback()` and `manualCheckedCommit()` demonstrate **two different business decisions** for the same checked exception. Spring does not automatically classify checked exceptions to commit in the direct API.
- `template.*` shares a `TransactionTemplate` whose configuration is immutable after the constructor.
- `participatingRollback()` creates an inner `REQUIRED` using the direct API **on the same thread and manager**, so the manager detects the existing transaction; `rollback(inner)` sets shared rollback-only.
- `independentRequiresNew()` opens inner T2, commits it, and then rolls back outer T1. Two different rows prevent T2 from waiting on T1's lock.

### 13.6. How to Run

In the directory containing `pom.xml`, with JDK 17+ and Maven:

~~~bash
mvn -q spring-boot:run
~~~

Spring Boot/HikariCP may print their own logs. Below is only the **stdout printed by the application**, with H2 and the transaction manager in this project:

~~~text
START=100/1000
AFTER_MANUAL_COMMIT=110/1000
CAUGHT_RUNTIME=runtime-failed
AFTER_RUNTIME_ROLLBACK=110/1000
CAUGHT_CHECKED_ROLLBACK=checked-failed
AFTER_CHECKED_ROLLBACK=110/1000
CAUGHT_CHECKED_COMMIT=checked-failed
AFTER_CHECKED_COMMIT=150/1000
MARK_ONLY=true
AFTER_MARK_ONLY=150/1000
AFTER_TEMPLATE_COMMIT=210/1000
CAUGHT_TEMPLATE=template-failed
AFTER_TEMPLATE_RUNTIME=210/1000
AFTER_TEMPLATE_MARK=210/1000
OUTER_ROLLBACK_ONLY=true
CAUGHT_UNEXPECTED=UnexpectedRollbackException
AFTER_PARTICIPATING=210/1000
AFTER_REQUIRES_NEW=210/1005
~~~

### 13.7. Explaining Each Balance Milestone and Completion

| Case | SQL in transaction | Completion | Balance after |
| --- | --- | --- | --- |
| Manual success | id1 +10 | `commit(status)` succeeds | 110 / 1000 |
| RuntimeException from body | id1 +20 | `rollback(status)`, rethrow original | 110 / 1000 |
| IOException, rollback chosen | id1 +30 | `rollback(status)`, rethrow checked error | 110 / 1000 |
| IOException, commit chosen | id1 +40 | `commit(status)` then rethrow checked warning | 150 / 1000 |
| Mark rollback-only | id1 +50 | `commit(status)` sees local rollback-only and rolls back | 150 / 1000 |
| Template success | id1 +60 | Template commits | 210 / 1000 |
| Template runtime error | id1 +70 | Template rolls back then propagates | 210 / 1000 |
| Template mark rollback-only | id1 +80 | Template rolls back on return | 210 / 1000 |
| Inner `REQUIRED` joins | outer id1 +90, inner +100, outer +5 | Inner status rollback marks T1 rollback-only; outer commit rolls back, caller sees `UnexpectedRollbackException` | 210 / 1000 |
| Inner `REQUIRES_NEW` | outer id1 +1, inner id2 +5 | Inner T2 commits; outer T1 rolls back | 210 / 1005 |

**Reading the result accurately:** `CAUGHT_CHECKED_COMMIT` appears **together with** the committed id1 +40 change. There is no contradiction: the checked error is reported **after** the application deliberately commits because case 4's contract allows it. If the business logic truly treats `IOException` as a failure that must not be persisted, use case 3.

`CAUGHT_UNEXPECTED` appears only after outer `commit(status)` tries to complete transaction T1, which is already global rollback-only; not because an UPDATE statement itself threw an exception. `manager.rollback(inner)` decided to make the shared physical transaction uncommittable.

`AFTER_REQUIRES_NEW` proves T2 commits independently: outer rolls back id1 +1 while id2 +5 remains. In-memory H2 with HikariCP and a default pool supporting two connections is an illustrative environment, not a throughput benchmark.

## 14. Avoiding Anti-Patterns That Corrupt Results or Mask Root Causes

### 14.1. Rollback After Commit Exception

~~~java
try {
    doWork();
    manager.commit(status);
} catch (Exception ex) {
    manager.rollback(status); // WRONG if the error came from commit.
}
~~~

Do not use this pattern. Per the contract, commit already completed cleanup even on failure. Rolling back after a commit failure can throw `IllegalTransactionStateException` and hide the commit error.

### 14.2. Commit After Rollback

~~~java
manager.rollback(status);
manager.commit(status); // WRONG: status is already completed.
~~~

You cannot "try committing" an already ended status again. If business retry is needed, create a **new transaction** via `getTransaction`, and only retry when the operation is idempotent and external state has been verified.

### 14.3. Catching Errors and Returning Success

~~~java
TransactionStatus status = manager.getTransaction(def);
try {
    writeStepOne();
    writeStepTwo(); // throws error but is caught below
} catch (RuntimeException ignored) {
    // Anti-pattern: ignore error and proceed to commit.
}
manager.commit(status);
~~~

There is no "automatic rollback whenever a RuntimeException occurred earlier" with the direct API. If an exception is caught and the status is not rollback-only, `commit` can succeed, creating partial state. An SQL error may also leave the DB transaction aborted, causing commit to fail. Choose an explicit policy instead of swallowing errors.

### 14.4. Failing to Catch Errors from Rollback

~~~java
catch (RuntimeException original) {
    manager.rollback(status); // If rollback throws, original can be masked.
    throw original;
}
~~~

This structure is common, yet rollbackFailure can knock the original exception off the top of the stack. When forensics are needed, preserve both. The `addSuppressed` strategy in the demo is one option.

### 14.5. Sharing One TransactionStatus Across Multiple Threads

Statuses and resources in imperative transaction management are normally tied to the execution scope and thread. Never hold a `TransactionStatus` in a singleton field for multiple requests to commit/roll back, and never pass it to another thread expecting the manager to automatically migrate the connection/thread-local context. Use a separate transaction boundary for each execution.

### 14.6. Obtaining a JDBC Connection Outside Spring Transaction Awareness

Acquiring a connection directly from a different datasource/pool can cause queries not to participate in the right transaction. Use `JdbcTemplate` or `DataSourceUtils` compatible with the manager, and avoid manually committing/rolling back a JDBC connection managed by Spring.

### 14.7. Sending Irreversible Notifications Before Commit

If you send an email or publish a message and the DB transaction then rolls back, the side effect is not automatically undone. Use an outbox and delivery/idempotency mechanisms if the system requires consistency between the database and message broker.

## 15. Exception-Handling Strategy Across Different Stages

A production service should have a **policy table** before writing catch blocks:

| Stage | Common failures | Appropriate response |
| --- | --- | --- |
| Acquire/begin | Pool connection timeout, DB down, unsupported isolation | Fail request, bounded retry if safe; do not roll back a nonexistent status |
| Business validation **before writes** | Invalid input data | Return meaningful error; usually no need to start a transaction yet |
| Business validation **after writes** | Domain rule violated | Roll back current status; preserve business exception |
| SQL execution | Constraint violation, deadlock, query timeout | Roll back status, classify error code, and retry appropriately if safe |
| Commit | Rollback-only, flush fail, network/system failure | Do not roll back status again; classify certain vs. uncertain outcome, check DB/idempotency |
| Rollback | Connection error, manager system failure | Preserve both original error and rollback error; do not assume data was undone |
| After-completion | Notification fail, event delivery fail | Retry side effect with idempotency/outbox; do not reuse DB status |
| Retrying whole request | Duplicate execution, race | New transaction, unique constraints/idempotency key, and bounded backoff |

**Especially for network-induced commit failures:** the server may have committed while the client never received the ACK. Blindly retrying the entire INSERT/transfer can create duplicates if there is no idempotency key or reliable state-query mechanism. Do not claim every `TransactionSystemException` definitely rolled back.

### Separating Business Errors from Transaction-Management Errors

- `IllegalArgumentException` from domain validation is business information.
- `DataIntegrityViolationException` can indicate SQL violated a constraint.
- `UnexpectedRollbackException` indicates a commit request turned into a rollback due to rollback-only.
- `CannotCreateTransactionException` indicates the transaction could not be created.
- `TransactionSystemException` indicates an infrastructure error at commit/rollback or in the transaction coordinator.

These exception types are not interchangeable. A controller handler can translate them into appropriate responses, yet must **never** mask the transaction error source to the point of returning "success" when the DB has not committed.

## 16. Stage-by-Stage Analysis Exercises

**Question 1.** `getTransaction(def)` throws `CannotCreateTransactionException` because the Hikari pool ran out of connections. Can you call `rollback(status)`?

**Answer:** No `TransactionStatus` was returned, so there is no valid status. Handle the failure at the begin stage; the manager is responsible for internal cleanup.

**Question 2.** With the direct API, a method INSERTs and throws a checked `IOException`. `@Transactional` is not used. Does Spring apply the default rollbackFor automatically?

**Answer:** No. Direct code must call `rollback(status)` per its policy, or deliberately choose commit when business rules permit. Checked vs. unchecked does not drive this API automatically.

**Question 3.** Code puts `manager.commit(status)` inside `try`, and `catch(RuntimeException)` calls `manager.rollback(status)`. What is the bug?

**Answer:** If commit throws an exception, the catch block can roll back an already completed status, causing `IllegalTransactionStateException` and hiding the commit error. Move commit outside the business body's catch block.

**Question 4.** The body returns normally, yet `status.setRollbackOnly()` was called. Is `manager.commit(status)` guaranteed to commit?

**Answer:** No. The manager can roll back instead of committing. For a **new transaction** locally marked rollback-only, completion may return normally after rolling back, so you must understand the marker and never treat the method name `commit` as proof the DB committed.

**Question 5.** Inner `REQUIRED` receives a participating status, code calls `manager.rollback(inner)`, and outer then calls `manager.commit(outer)`. What can happen?

**Answer:** Inner rollback may simply mark the shared physical transaction rollback-only; outer's commit is converted to a rollback and throws `UnexpectedRollbackException`. There is no separate rollback for inner `REQUIRED`.

**Question 6.** Inner `REQUIRES_NEW` commits successfully, and outer rolls back immediately afterward. Does inner's update still exist?

**Answer:** It can still exist because inner has an independent physical transaction. This policy must be acceptable to the business logic, and pool/locking capacity must be sufficient.

**Question 7.** Rollback after a business error throws an additional `TransactionSystemException`. Should you discard the business exception?

**Answer:** You should not lose either. Keep the business error as primary and add the rollback failure to `suppressed`, or choose the rollback failure as primary and attach cause, depending on policy; log enough to note the transaction outcome may be indeterminate.

**Question 8.** The DB has finished committing, but `afterCommit()` fails to send an email. Is it right to call rollback on the old status to cancel the DB data?

**Answer:** No. The DB transaction has already completed; retry the side effect or use an outbox/compensation mechanism instead of rolling back a completed status.

## 17. Implementation Checklist for Direct Transaction Code

- [ ] Use the direct API only when explicit control is needed; prefer `TransactionTemplate` to reduce boilerplate when sufficient.
- [ ] Explicitly define propagation/isolation/timeout and match the right manager/datasource.
- [ ] Account for `getTransaction` possibly failing **before a status exists**.
- [ ] For business exceptions: choose rollback/commit **deliberately** for both checked and unchecked types.
- [ ] Place `commit(status)` **outside the catch** that calls `rollback(status)` for the business body.
- [ ] Never commit/rollback a status that already has `isCompleted()`.
- [ ] Check `setRollbackOnly()` and participating scopes; `commit` does not necessarily mean physical commit.
- [ ] Never swallow SQL errors and assume the connection can still commit.
- [ ] If rollback fails, preserve both rollbackFailure and original.
- [ ] For commit failures, do not assume the DB outcome is definitely rolled back; design retry/idempotency.
- [ ] Never share a `TransactionStatus` across request threads.
- [ ] Write integration tests that read the DB **after the scope completes**, rather than only checking UPDATE logs.
- [ ] When using `REQUIRES_NEW`, verify pool size, row locks, and independent commit behavior.
- [ ] Handle external side effects via outbox/after-completion policies.
- [ ] For reactive flows, use `TransactionalOperator` instead of copying imperatively managed ThreadLocal code.

## 18. Conclusion

**Direct transaction management means managing a one-way lifecycle: begin → business work → exactly one completion → cleanup.** `PlatformTransactionManager` provides a consistent API; `TransactionStatus` tracks the scope's state; `TransactionTemplate` automates most of this work.

The two most dangerous mistakes are **assuming checked/unchecked exceptions automatically follow `@Transactional` rollback rules when using the manager directly**, and **calling rollback after commit has thrown an exception**. Decide your exception policy for each stage, separate the business catch from completion, record rollback failures without masking the original error, and verify DB state after completion. With multiple logical scopes, distinguish a participating transaction from a new physical transaction; with commit failures, always account for the possibility of an indeterminate outcome.

## Official References

- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate`, `PlatformTransactionManager`, `TransactionDefinition`, and `TransactionStatus`.
- [Spring Framework — PlatformTransactionManager Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/PlatformTransactionManager.html): getTransaction/commit/rollback contract, especially **never rolling back after a commit failure**.
- [Spring Framework — TransactionStatus Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/TransactionStatus.html): isRollbackOnly, setRollbackOnly, isCompleted, savepoints.
- [Spring Framework — TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html): callback lifecycle and exception handling.
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): participating REQUIRED, rollback-only/UnexpectedRollbackException, REQUIRES_NEW.
- [Spring Framework — Transaction Synchronization](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html): beforeCommit, afterCommit, and afterCompletion callbacks.
- [Spring Framework — JDBC Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): DataSourceTransactionManager and transaction-aware connection usage.
