# Restoring Outer Transaction Resources After `REQUIRES_NEW` Completes

## Learning Objectives

In Spring Framework, `Propagation.REQUIRES_NEW` allows a method to open an **independent physical transaction** even when the caller already has an active transaction. While the new transaction executes, the outer transaction is **suspended**. Once the inner transaction commits or rolls back, Spring cleans up the inner transaction's resources and **resumes** the outer transaction's resource context so the caller continues on its original transaction.

This lesson focuses on the **restoration step after the inner transaction completes**. By the end, you will be able to:

1. Identify the context data Spring must save on suspend and restore on resume: resource bindings, transaction synchronizations, transaction name, read-only flag, isolation level, and actual-transaction flag.
2. Describe the sequence: suspend -> begin inner -> commit/roll back inner -> cleanup inner -> resume outer.
3. Explain why outer remains the same original transaction after inner commits/rolls back; distinguish continuing outer from "creating a new outer".
4. Analyze the success path, unchecked exception caught by outer, unchecked exception propagated further, and failure when beginning the new transaction.
5. Write and run a Java 17 + Spring JDBC example to verify the transaction context and restoration of the exact same resource, rather than guessing from annotations.
6. Recognize limitations: Spring AOP self-invocation, connection pools/locks, differences across transaction managers, multiple data sources, new threads, and reactive contexts.

## 1. Context: Two Physical Transactions in One Call Stack

Suppose `CheckoutService.checkout()` has transaction A. Inside this method, the service calls `AuditService.record()`, which uses `REQUIRES_NEW` to write an audit record that must commit independently. When `record()` is called through a Spring AOP proxy, Spring must prevent transaction B from accidentally using transaction A's connection/transaction bound to the current thread.

```text
Caller
  |
  v
CheckoutService.checkout()     Transaction A active
  |
  +-- AuditService.record()   @Transactional(REQUIRES_NEW)
  |      |
  |      +-- suspend A
  |      +-- begin B
  |      +-- execute INSERT audit in B
  |      +-- commit or roll back B
  |      +-- cleanup B
  |      +-- resume A
  |
  +-- continue checkout processing in transaction A
  |
  +-- commit or roll back A
```

Key points:

- **Transaction B** has an independent commit/rollback lifecycle; completing B does not mean A has completed.
- **Transaction A** is not committed, rolled back, reset to the beginning, or replaced by another transaction while B runs. A remains alive and may hold its own connection/locks.
- After B finishes, Spring *rebinds* A's resources into the execution context so subsequent JDBC statements in outer continue using A.
- When resume succeeds, outer does not need to reopen a transaction via another `@Transactional`. Restoration is the transaction manager's responsibility.

Spring documentation describes `REQUIRES_NEW` as an **independent physical transaction**; therefore B can commit while A later rolls back, and B's isolation/timeout/read-only settings are not inherited from A.

## 2. Distinguishing Three Things Often Mistakenly Called "Transaction"

| Component | Role in the A -> B -> A example |
|---|---|
| **Physical transaction A** | The real transaction on outer's JDBC connection; not finished while B runs |
| **Physical transaction B** | A different real transaction, possibly on another JDBC connection, with its own commit/rollback |
| **Thread-bound transaction context** | Information Spring stores per thread (resource map, synchronizations, and metadata) so data-access layers know which transaction they currently participate in |

With `JdbcTransactionManager`/`DataSourceTransactionManager`, the transaction manager works with a `DataSource`. Spring can bind a `ConnectionHolder` in `TransactionSynchronizationManager` keyed by the datasource; Spring-aware APIs such as `JdbcTemplate` retrieve the bound connection to participate in the transaction.

When **suspending A**, Spring can **temporarily unbind A's binding from the thread** and store that resource object in a holder for later resumption. A's resource still belongs to transaction A and is not "released back to the pool" just because of suspension. When **beginning B**, Spring binds B's resource to the thread so JDBC calls inside inner do not mistakenly use A. When **resuming A**, Spring unbinds the completed resource B and rebinds the exact same resource A.

Do not interpret "suspend" as temporarily closing connection A or releasing A's locks. If the database holds locks under A, B may be blocked if it needs the same row/table. Suspension at the Spring layer is primarily **temporarily switching the visible transaction context**, not an SQL command telling the DB to release locks.

## 3. Actual Order of Suspend and Resume

With the underlying `AbstractPlatformTransactionManager` mechanism and a manager that supports suspension, the general flow when outer already has an active transaction is:

```text
[Current thread]
A: actual=true; datasource -> holder A; sync A
    |
    | Inner method invoked THROUGH PROXY, propagation=REQUIRES_NEW
    v
suspend(A):
    1. Call suspend() on registered TransactionSynchronizations for A
    2. Suspend/clear A's synchronizations on the thread
    3. doSuspend(A): transaction manager detaches A's resource
    4. Save A's metadata: name, readOnly, isolation, wasActive
    |
    v
begin(B):
    5. doBegin(B): create/bind new resource for B
    6. Set B's synchronizations/metadata
    |
    v
execute inner:
    7. Execute database operations in B
    |
    v
complete(B):
    8. Commit B or roll back B according to outcome and policy
    9. Clear synchronizations + doCleanupAfterCompletion(B)
    |
    v
resume(A):
   10. doResume(A): rebind A's saved resource
   11. Restore A's name, readOnly, isolation, actual-transaction flag
   12. Re-register A's synchronizations, call resume() on each callback
    |
    v
A: actual=true; datasource -> holder A; sync A
    |
    v
Outer continues on the same physical transaction A
```

The diagram describes standard behavior in Spring Framework 6.x with `AbstractPlatformTransactionManager`. Transaction manager subclasses are responsible for implementing the specialized `doSuspend`/`doResume` operations. If a transaction manager does not support suspension (or the underlying transaction system lacks the required capability), using `REQUIRES_NEW` while a transaction is active can fail; do not treat the diagram as a guarantee that every manager executes it successfully.

**Distinguishing two callback layers:**

- `TransactionSynchronization.suspend()` and `resume()` are for **registered synchronizations**; an implementation managing additional resources can unbind/rebind its own resources inside these callbacks.
- `AbstractPlatformTransactionManager.doSuspend(...)` and `doResume(...)` are the manager's **template methods** to temporarily detach/reattach the primary transaction resource (for example `ConnectionHolder`).
  
These are related mechanisms with different responsibilities. Do not call them directly from business code; let Spring's transaction interceptor and transaction manager handle them.

## 4. What Exactly Is Restored?

`TransactionSynchronizationManager` manages thread-bound state for synchronous transactions. When A is suspended, Spring preserves the information needed to restore the exact context after B:

| Component | While A runs | While B runs | After B, when A resumes |
|---|---|---|---|
| Resource by datasource | Holder/connection A bound to thread | A temporarily unbound; holder/connection B bound to thread | Holder/connection A rebound |
| Actual transaction flag | `true` | `true` for B | A's `true` |
| Transaction name | A's name (if any) | B's name | A's name restored |
| Read-only metadata | A's read-only flag | B's read-only flag | A's flag restored |
| Isolation metadata | A's level | B's level | A's level restored |
| Synchronization callbacks | A's callback list | B's separate callback list | A's callbacks re-registered, `resume()` called |

In many annotation-driven examples, the transaction name is derived from the transactional method. The name may differ or be absent in specialized configurations; do not build business logic around the name string.

Some values such as **transaction A's timeout deadline** cannot "reset the clock" merely by resuming; transaction A remains open, and the time B runs can contribute to the total duration A holds its resources. B can also have its own isolation, timeout, and read-only settings. Spring restoring metadata does not imply the two transactions shared settings or the same physical connection.

**Do not confuse:** `isSynchronizationActive()` indicates that Spring is managing synchronizations on the thread; it can be `true` even when there is no actual database transaction under certain other propagations. To inspect state in a JDBC demo, use `isActualTransactionActive()` together with comparing resources and transaction status.

## 5. Resume Occurs When Inner Commits, Rolls Back, or Throws an Exception

With a proxied invocation, the transaction mechanism completes its work before control returns to the caller:

### 5.1. Inner Completes Normally

1. Inner returns without throwing an error -> B's interceptor decides to commit B.
2. Spring runs cleanup for B: clears B's metadata/synchronizations and cleans up B's resources.
3. Spring resumes A (restores the holder and synchronizations).
4. Only after that does `innerService.inner()` return to outer.
5. Outer continues and eventually commits or rolls back A on its own.

If B committed data, rolling back A **does not erase the data committed in B**. This is the intended independence of `REQUIRES_NEW`.

### 5.2. Inner Throws an Unchecked Exception, Outer Catches and Continues

1. Inner throws a `RuntimeException`; the default rollback policy makes Spring roll back B.
2. Spring cleans up B and resumes A before the exception reaches outer's `catch`.
3. Outer catches and handles the error and continues working with A's restored resources.
4. Outer can commit A if A itself has not been marked rollback-only and encounters no other errors.

This rule differs from `REQUIRED`: when an inner `REQUIRED` joins A and marks A rollback-only, outer can receive `UnexpectedRollbackException` when trying to commit. Inner `REQUIRES_NEW` rolling back B **does not automatically mark A rollback-only**. Nevertheless, outer can still roll back intentionally or be forced to roll back due to another error.

### 5.3. Inner Throws an Exception, Outer Does Not Catch

Spring still finishes B and restores A's context along the normal cleanup path, then propagates the exception to outer. Because the unchecked error escapes the outer method, **outer's transaction interceptor** can roll back A under the default rule. The fact that "A also rolls back" in this case **is not because B's rollback propagated to A**, but because the exception crossed A's `@Transactional` boundary.

### 5.4. If Beginning B Fails

Spring has a path to restore A when the begin-B step throws an error; `AbstractPlatformTransactionManager` includes a resume mechanism after a begin exception. However, if the failure happens during suspend/resume itself or the resource/transaction manager is corrupted, there is **no guarantee** the application can continue normally. Do not assume a severe infrastructure failure can simply be caught to safely commit A.

## 6. Java 17 Example: Verifying the Exact Resource Is Resumed

The example uses Spring Framework 6.2.19, in-memory H2, `JdbcTemplate`, `JdbcTransactionManager`, and class-based AOP proxies. It focuses on **the restoration of A itself**, not only proving that B commits independently.

Three scenarios:

- **B commits, A rolls back:** after inner, outer still observes the exact same resource A; B's committed data remains.
- **B rolls back, outer catches the error and A commits:** A is resumed before `catch`; A continues writing and commits.
- **B rolls back, error propagates to outer:** use `finally` to verify A was already resumed before the outer interceptor rolls back A.

To observe suspend/resume, outer registers a `TransactionSynchronization` with two logging callbacks. Each outer method saves a reference to its bound resource before calling B and compares the **same instance** after B finishes. This is a reasonable diagnostic check with a JDBC transaction manager in a demo; regular business code should not depend on `ConnectionHolder` identity.

### 6.1. Project Structure

```text
spring-resume-demo/
├── pom.xml
└── src/main/java/com/example/tx/Main.java
```

### 6.2. The `pom.xml` File

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-resume-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
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
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` and related dependencies provide Spring beans/AOP; `spring-jdbc` provides the transaction manager and JDBC helpers; H2 provides the in-memory database. The application does not need Spring Boot. Versions in the example are pinned for reproducibility; real applications should use a tested BOM and a version-update policy.

### 6.3. The `src/main/java/com/example/tx/Main.java` File

```java
package com.example.tx;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class Main {

    private static boolean actualTx() {
        return TransactionSynchronizationManager.isActualTransactionActive();
    }

    @Configuration
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:resume_demo;DB_CLOSE_DELAY=-1");
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
            return new JdbcTransactionManager(ds);
        }

        @Bean
        public InnerService innerService(JdbcTemplate jdbc) {
            return new InnerService(jdbc);
        }

        @Bean
        public OuterService outerService(
                JdbcTemplate jdbc, DataSource ds, InnerService inner) {
            return new OuterService(jdbc, ds, inner);
        }
    }

    public static class InnerService {
        private final JdbcTemplate jdbc;

        public InnerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void perform(boolean shouldFail) {
            boolean fresh = TransactionAspectSupport.currentTransactionStatus()
                    .isNewTransaction();
            System.out.println("B actual=" + actualTx() + " new=" + fresh);

            jdbc.update("INSERT INTO tx_events(label) VALUES (?)",
                    shouldFail ? "b-rollback" : "b-commit");

            if (shouldFail) {
                throw new IllegalStateException("inner failed");
            }
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final DataSource dataSource;
        private final InnerService inner;

        public OuterService(JdbcTemplate jdbc, DataSource ds, InnerService inner) {
            this.jdbc = jdbc;
            this.dataSource = ds;
            this.inner = inner;
        }

        private Object getBoundResource() {
            return TransactionSynchronizationManager.getResource(dataSource);
        }

        private Object watchOuterTransaction() {
            Object holder = getBoundResource();
            if (holder == null || !actualTx()) {
                throw new IllegalStateException("outer transaction missing");
            }

            TransactionSynchronizationManager.registerSynchronization(
                new TransactionSynchronization() {
                    @Override
                    public void suspend() {
                        System.out.println("A sync suspend");
                    }

                    @Override
                    public void resume() {
                        System.out.println("A sync resume");
                    }
                }
            );
            return holder;
        }

        private void showRestored(Object holder, String label) {
            System.out.println(label + " same holder=" +
                    (holder == getBoundResource()) +
                    " actual=" + actualTx());
        }

        @Transactional
        public void innerCommitsOuterRollsBack() {
            Object holder = watchOuterTransaction();

            // A has not modified any rows/tables; B avoids locks held by A in the demo.
            inner.perform(false);

            showRestored(holder, "A after B commit");
            jdbc.update("INSERT INTO tx_events(label) VALUES (?)", "a-rollback");
            throw new IllegalStateException("outer failed");
        }

        @Transactional
        public void innerRollsBackOuterCommits() {
            Object holder = watchOuterTransaction();

            try {
                inner.perform(true);
            } catch (IllegalStateException ex) {
                System.out.println("A caught=" + ex.getMessage());
            }

            showRestored(holder, "A after B rollback");
            jdbc.update("INSERT INTO tx_events(label) VALUES (?)", "a-commit");
        }

        @Transactional
        public void innerFailurePropagates() {
            Object holder = watchOuterTransaction();

            try {
                inner.perform(true);
            } finally {
                showRestored(holder, "A in finally");
            }
        }
    }

    private static void scenario(
            String title, Runnable action, JdbcTemplate jdbc) {
        System.out.println("=== " + title + " ===");

        try {
            action.run();
        } catch (IllegalStateException ex) {
            System.out.println("caller caught=" + ex.getMessage());
        }

        System.out.println("rows=" + jdbc.queryForList(
                "SELECT label FROM tx_events ORDER BY id", String.class));
        jdbc.update("DELETE FROM tx_events");
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                    "CREATE TABLE tx_events (" +
                    "id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY, " +
                    "label VARCHAR(40) NOT NULL)"
            );

            OuterService outer = context.getBean(OuterService.class);

            scenario("B_COMMIT_A_ROLLBACK",
                    outer::innerCommitsOuterRollsBack, jdbc);
            scenario("B_ROLLBACK_A_COMMIT",
                    outer::innerRollsBackOuterCommits, jdbc);
            scenario("B_ERROR_PROPAGATES",
                    outer::innerFailurePropagates, jdbc);
        }
    }
}
```

**Why is the code structured this way?**

- `@EnableTransactionManagement(proxyTargetClass = true)` enables class-based proxies. Omitting an interface is a convenience choice for the demo, not a requirement of `REQUIRES_NEW`.
- `OuterService` invokes a separate Spring-managed bean `InnerService`. Calling `this.perform()` in the same class would bypass the proxy via self-invocation and could fail to create transaction B.
- The same `DataSource` is passed into `JdbcTemplate` and `JdbcTransactionManager`. This allows Spring to bind the right JDBC connection to each transaction.
- `watchOuterTransaction()` stores the `ConnectionHolder` as an `Object` and registers a synchronization belonging to A. The `suspend()` and `resume()` callbacks are invoked by Spring around B.
- `showRestored()` checks that A's holder before and after has the **same identity** upon returning to outer. This is an observation of the specific JDBC mechanism, not a business contract requiring every transaction manager to expose an identical holder.
- `InnerService.perform()` verifies transaction B is actual and has `isNewTransaction()=true`, then writes data. With `shouldFail=true`, the unchecked exception causes transaction B to roll back.
- `OuterService` does not write to the table before running B so the H2 demo avoids lock contention between connection A and connection B on the same table. In real systems, outer can certainly hold locks before calling inner; that is a risk requiring separate design.

### 6.4. Run Command and Expected stdout

With JDK 17+ and Maven installed, enter the project directory and run:

```bash
mvn -q compile exec:java -Dexec.mainClass=com.example.tx.Main
```

The lines printed by **the program itself** (excluding Maven messages or extra infrastructure logging):

```text
=== B_COMMIT_A_ROLLBACK ===
A sync suspend
B actual=true new=true
A sync resume
A after B commit same holder=true actual=true
caller caught=outer failed
rows=[b-commit]
=== B_ROLLBACK_A_COMMIT ===
A sync suspend
B actual=true new=true
A sync resume
A caught=inner failed
A after B rollback same holder=true actual=true
rows=[a-commit]
=== B_ERROR_PROPAGATES ===
A sync suspend
B actual=true new=true
A sync resume
A in finally same holder=true actual=true
caller caught=inner failed
rows=[]
```

**Exact analysis of each case:**

1. **B commits, A rolls back:** `A sync suspend` occurs before method B runs. After B finishes, `A sync resume` appears **before outer prints its result**, and `same holder=true`. Outer throws an error so A rolls back; the `b-commit` row remains because B committed independently.
2. **B rolls back, outer catches:** A was already resumed **before the catch block in outer ran**. `same holder=true` shows the `a-commit` write continues on A; outer finishes normally and commits. The `b-rollback` row was rolled back in B.
3. **B rolls back, error propagates:** outer's `finally` block still observes A restored. Afterward, the unchecked error passes through outer's transaction interceptor, causing A to roll back. A's resume mechanism still occurred even though outer did not handle the exception.

Note that in the demo, labels A/B simply help read the log. **B rolling back does not automatically make A rollback-only**. In case (3), A rolls back because the exception itself crossed the outer transaction boundary. With a connection pool, connection acquisition/retention signals will differ from the demo setup, yet the transaction principle remains unchanged.

## 7. Things Spring Does Not "Restore" in the Sense of Automatically Fixing Business State

### 7.1. Resume Does Not Undo Data Committed by B

`REQUIRES_NEW` creates a new physical transaction, so if B commits first and A later rolls back, B's data stays in the database. If operation B is an audit log, that may be intentional. If B is a balance update directly dependent on an uncommitted operation in A, data can become inconsistent. Define the proper transaction boundaries or consider an outbox and eventual consistency design.

### 7.2. Resume Does Not Release A's Locks/Connection Early

A can continue holding its connection and locks throughout B's execution. B may need a second connection and hit rows locked by A; inner can then block or time out. Spring recommends sizing the connection pool large enough when using `REQUIRES_NEW` under concurrent load; a common minimum guideline is a pool size exceeding the number of concurrent threads by at least one connection, and more must be budgeted if there are multiple nested layers of independent transactions.

Dangerous design example:

```text
A: UPDATE accounts SET balance = ... WHERE id = 10
   (holds row lock on id=10)
    |
    +-- B REQUIRES_NEW: UPDATE accounts SET ... WHERE id=10
                       (may wait on A's lock)
    |
A cannot proceed to commit and release the lock
until B completes.
```

Exact behavior depends on the DB and isolation level, but this is a self-blocking hazard between two physical transactions, not a Spring resource-restoration bug.

### 7.3. Resume Does Not "Rewind" A's Timeout

Transaction A is not recreated, so A's resource-holding duration keeps accumulating. B has its own timeout; resuming A does not grant A a fresh full timeout. If outer was already close to its deadline or inner ran for a long time, an operation in A after resume can still time out, even though B itself committed successfully.

### 7.4. Resume Does Not Clear A's Rollback-Only State

If A was already rollback-only before calling B, B committing and A resuming does not return A to a committable state. `REQUIRES_NEW` only guarantees a separate transaction B; it does not "heal" an outer transaction that can no longer commit.

### 7.5. Resume Does Not Automatically Run A's Transaction on Another Thread

Imperative transaction `TransactionSynchronizationManager` relies on a **thread-bound** context. If you spawn a new thread, use `@Async`, or schedule a task, A's resources do not automatically follow that thread. `REQUIRES_NEW` on a new thread can create another separate transaction, but it is not a continuation/resume of A. Nor can this code be used as-is for R2DBC/reactive transactions, which bind context in Reactor `Context`.

## 8. Quick Comparison with Other Propagations to Avoid Confusion

| Inner propagation | Suspends A? | Inner has its own physical transaction? | What needs to be restored? |
|---|---|---|---|
| `REQUIRED` | No | No, if A already exists | No suspend/resume of outer; inner joins A |
| `REQUIRES_NEW` | **Yes** | **Yes**, separate transaction B | A's resources and synchronizations/metadata after B |
| `NOT_SUPPORTED` | Yes, if A exists | No | A's resources and synchronizations/metadata after the non-transactional block |
| `NESTED` | Usually no, when JDBC savepoints are supported | No; savepoint within A | No separate transaction B to resume like `REQUIRES_NEW` |

The table's goal is to explain **whether outer needs to be restored**; each propagation also has specific conditions governed by the transaction manager. Do not generalize `NESTED` to all JPA/R2DBC managers. `NOT_SUPPORTED` can cause SQL statements to use auto-commit connections and no longer roll back with A.

## 9. Common Mistakes When Checking Resume

| Symptom | Common cause | Remedy |
|---|---|---|
| B does not create a separate transaction; still shares A's holder | Self-invocation, call bypassing proxy, or annotation not processed | Invoke a separate inner bean through Spring proxy, enable transaction management |
| After B, outer code does not see transaction A | Code runs on another thread; different transaction manager/data source; context manually altered | Keep synchronous calls through proxies and same manager/resource, avoid manually touching `TransactionSynchronizationManager` |
| B cannot open a connection | Pool exhausted because A still holds a connection | Review `REQUIRES_NEW`, concurrency limits, pool sizing |
| B times out when updating the same data as A | A holds locks while suspended | Shorten A, change access order, avoid updating rows locked by A |
| B commits yet A rolls back and audit remains | **Expected** behavior of two independent transactions | Use only if business requires independent persistence |
| Inner throws error, outer also rolls back despite resume | Unchecked exception propagates through A's interceptor | If A should continue, outer must have a valid error-handling policy; do not swallow errors blindly |
| Inner rolls back, A catches yet cannot commit | A was already rollback-only due to another error or outer marked rollback-only | Track A's status and the cause of rollback-only |
| `suspend()/resume()` callbacks not observed | No synchronization registered on A, manager does not use synchronization as assumed, or proxy inactive | Use the right transaction manager, register callbacks in transaction A, verify via integration test |
| Resume fails | Manager/resource unsupported, transaction coordinator failure, or broken connection state | Handle as system failure, monitor transaction exceptions; do not assume A can safely commit |
| Single test passes but multiple concurrent requests hang | Small pool, lock conflicts, or concurrent transaction nesting | Stress-test with a real pool/DB and measure waiting connections |

**Debug note:** You can enable logging for `org.springframework.transaction` and `org.springframework.jdbc.datasource` at DEBUG/TRACE depending on the version to observe creation, suspend, resume, and cleanup. However, combine logs with database state checks after commit/rollback; seeing `actualTx=true` in outer alone does not prove resource A was restored accurately.

**Management boundary:** `TransactionSynchronizationManager.bindResource`, `unbindResource`, and synchronization callbacks are infrastructure mechanisms. Do not write business code that manually detaches/binds connections hoping to control `REQUIRES_NEW` by hand. When programmatic transaction control is needed, use `TransactionTemplate` with the appropriate `PlatformTransactionManager`; the transaction manager still performs suspend/resume.

## 10. Comprehension Check Exercises

1. **B committed while A was suspended. After B returns to A, which connection does A use?** With the local JDBC transaction manager in the example, Spring rebinds the saved holder/connection A; A does not switch to connection B.
2. **B rolled back, and A caught the exception. Must A roll back?** No. A can continue/commit if it has not been marked rollback-only and no other rollback-triggering error escapes A's boundary.
3. **B rolled back, and outer did not catch the exception. Why does A usually roll back?** Because the unchecked exception escapes outer and is handled by A's transaction interceptor, not because B directly propagated rollback-only to A.
4. **Does suspend release A's DB locks?** No. Physical A remains open and may hold locks.
5. **Is `TransactionSynchronization.suspend()` an `afterCompletion` callback?** No. Suspend/resume temporarily detaches/restores synchronizations, whereas completion callbacks reflect transaction termination.
6. **How does `REQUIRES_NEW` primarily differ from `NESTED`?** `REQUIRES_NEW` uses an independent physical transaction B and resumes A; `NESTED` is typically a savepoint within the same physical transaction A.
7. **Why cannot `@Async` automatically resume transaction A?** Because imperative transaction context is managed on the current thread and is not automatically transferred to another thread.
8. **How can A's resume be verified in an integration test?** Capture the resource binding before inner, verify synchronization suspend/resume and resource binding after inner, then assert commit/rollback results in the DB.

## Official References

- Spring Framework — Transaction Propagation, `PROPAGATION_REQUIRES_NEW` section: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Synchronizing Resources with Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html
- Spring Framework — `AbstractPlatformTransactionManager` Javadoc (`suspend`, `resume`, `doSuspend`, `doResume`): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html
- Spring Framework — `TransactionSynchronization` Javadoc (`suspend()`, `resume()`): https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html
- Spring Framework — `TransactionSynchronizationManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html
- Spring Framework — `DataSourceTransactionManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html
- Spring Framework — Using `@Transactional`: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
