# Splitting a Long Processing Flow into Explicit Transaction Segments with TransactionTemplate

## 1. Scenario: A Long Business Process Should Not Be One Giant Transaction

Suppose an order-processing system follows a sequence of steps:

1. Record the request and generate a processing ID.
2. Check inventory or perform computational tasks.
3. Call an external service to confirm payment or shipping.
4. Update the result in the database.
5. Record a failure state so it can be retried if a step fails.

If you wrap the **entire** flow in one `@Transactional` method, the transaction can stay open across network waits, retries, file processing, or long CPU work. Meanwhile, connections and certain locks may be held, forcing other transactions to wait.

Example design **to avoid by default**:

~~~java
@Transactional
public void process(long jobId) {
    insertInitialState(jobId);
    callRemotePaymentService();  // May take many seconds or time out.
    transformLargeDocument();    // CPU or non-database I/O.
    updateFinalState(jobId);
}
~~~

This is an **illustrative code snippet**, not a standalone Java program. A broad transaction is sometimes necessary if all operations **on the same DB** genuinely must be atomic; however, it **does not turn an HTTP request or CPU computation into a rollbackable operation**. Wrapping an HTTP call inside a DB transaction does not make the HTTP service participate in the database commit.

For a flow that is permitted to advance in stages and has a recovery mechanism, you can switch to multiple **short, clearly scoped transactions** using `org.springframework.transaction.support.TransactionTemplate`:

~~~text
TX-1: write PREPARED checkpoint -> COMMIT
       |
       v
Long work / remote I/O, NO transaction held
       |
       v
TX-2: write DONE result -> COMMIT
       |
       +-- on failure -> ROLLBACK TX-2
                            |
                            v
                     TX-3: write RETRY state -> COMMIT
~~~

The most important takeaway: **splitting into separate transactions means accepting partial commits**. Once TX-1 has committed, a failure in TX-2 does not automatically undo TX-1. Therefore, the design needs a **state machine, idempotency, retry mechanism, or compensation** rather than assuming every step will roll back together.

## 2. What Is TransactionTemplate Used For?

`TransactionTemplate` is Spring's **programmatic transaction management** API for imperative code, similar to how `JdbcTemplate` hides JDBC boilerplate.

It requires a `PlatformTransactionManager`. Inside `execute(...)` or `executeWithoutResult(...)`:

1. `TransactionTemplate` asks the transaction manager to get or open a transaction per `TransactionDefinition`.
2. Runs the application-supplied callback.
3. When the callback completes normally, Spring attempts to commit the transaction owned by the scope (unless marked rollback-only).
4. When the callback throws an unchecked exception, Spring executes rollback per the manager's semantics and propagates the exception to the caller.
5. In commit, rollback, or transaction system error cases, the caller may still receive an exception; the callback having returned is **not enough** to assert commit succeeded.

Syntax with a return value:

~~~java
TransactionTemplate template = new TransactionTemplate(transactionManager);
String value = template.execute(status -> {
    jdbcTemplate.update(
        "INSERT INTO audit_record (event_name) VALUES (?)", "STARTED");
    return "recorded";
});
~~~

This is an **illustrative snippet**, requiring `transactionManager`, `jdbcTemplate`, and the corresponding table. When the transaction manager opens a new transaction and `execute` returns normally, the commit/rollback scope has been handled; if `execute` only **joins an outer transaction**, the final physical commit still belongs to outer.

For callbacks that do not need to return a value:

~~~java
template.executeWithoutResult(status -> {
    jdbcTemplate.update(
        "UPDATE work_item SET state = ? WHERE id = ?",
        "PREPARED", 10);
});
~~~

`executeWithoutResult` is a concise form available since Spring Framework 5.2. It gives the lambda access to `TransactionStatus` to proactively call `setRollbackOnly()`. Both snippets are **API usage examples**, not complete programs.

### `@Transactional` Is Not Required for TransactionTemplate to Work

With `TransactionTemplate`, the transaction boundary is created when code calls `execute(...)` through the template itself; it does not depend on Spring AOP self-invocation rules. For example, calling a `private` helper from a public method still works **if the helper actually calls the template**. Even so, the service still needs an appropriate transaction manager and JDBC/JPA accesses must use Spring-managed resources.

This differs from annotation-driven `@Transactional`, which normally only applies when the call passes through a Spring proxy.

## 3. Why Split a Long Flow into Short Transactions?

| Factor | Single transaction wrapping whole flow | Multiple short transactions via TransactionTemplate |
| --- | --- | --- |
| Connections and locks | May be held across network/CPU waits | Each TX is short-scoped and releases resources between stages |
| Atomicity | SQL inside **the same physical transaction** commits/rolls back together | Only **SQL within each stage** commits/rolls back together |
| If the final step fails | SQL changes in the wide transaction can roll back | Previously committed stages remain persisted |
| Recoverability | May have to rerun the entire operation | Can retry from a committed checkpoint |
| Non-DB operations | Cannot roll back automatically | Explicitly left outside TX, avoiding false sense of atomicity |
| Isolation/timeout | One scope may run too long | Can set suitable policies per new stage |
| Observability | Hard to tell which durable milestone was passed | State machine and operation ID express progress |
| Business complexity | Simple if everything is atomic SQL | Requires handling intermediate states, retries, idempotency, compensation |

**Splitting smaller is not always better.** If two money-transfer statements in the same database must **commit together or roll back together**, splitting them into two physical transactions violates financial atomicity. If the work consists of just a few fast SQL statements requiring joint atomicity, keeping one transaction is right.

Split when there is a **valid business boundary**: a meaningful intermediate state from which recovery can proceed safely.

## 4. State Model Before Writing Transactions

Suppose a job has these states:

~~~text
               Prepare TX
          (idempotent request key)
                   |
                   v
                PREPARED
                   |
        external step succeeds
                   |
                   v
               Finish TX
                   |
                   +---- COMMIT ------> DONE
                   |
                   +---- ROLLBACK ----> still PREPARED
                                              |
                                       Error-mark TX
                                              |
                                              v
                                            RETRY
                                              |
                                     safe worker retry
                                              |
                                              v
                                             DONE
~~~

`PREPARED` **does not** mean the business operation is finished; it only confirms a checkpoint was recorded. `RETRY` indicates work remains to be processed; `DONE` is only written once the corresponding business conditions have been satisfied.

The state set here is a **simplified model** for learning transactions. Production systems usually need additional states like `PROCESSING`, `FAILED`, `CANCELLED`, error codes, versions, timestamps, lease/lock ownership, and retry counts.

### Rules for Designing Commit Milestones

A good transaction stage should be able to answer:

1. **What invariant does it protect?** For example, "create one request record with a unique operation ID".
2. **After commit, is the intermediate data valid?** `PREPARED` must be a state the system can read and process.
3. **What if the process crashes right after commit?** There must be a mechanism to scan/resume non-`DONE` records.
4. **What if the callback throws an exception before commit?** Can it be retried without creating duplicate records?
5. **What if commit succeeded yet the client lost connection before receiving confirmation?** Do not assume rollback; check state using an idempotency key.
6. **What if the remote call succeeded yet the DB update failed?** There must be a reconcile/compensation mechanism; do not assume DB rollback undoes the remote request.
7. **What if two workers pick up the same job?** Concurrency control and guarded state transitions are needed.

Therefore, transaction boundaries and **state semantics** must be designed together.

## 5. Scoping Each Template

`TransactionTemplate` implements `TransactionDefinition`. You can set propagation, isolation, read-only, timeout, and transaction name at initialization time.

~~~java
TransactionTemplate prepareTx = new TransactionTemplate(transactionManager);
prepareTx.setName("work-prepare");
prepareTx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
prepareTx.setTimeout(5); // 5 seconds, not 5 ms.

TransactionTemplate finishTx = new TransactionTemplate(transactionManager);
finishTx.setName("work-finish");
finishTx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
finishTx.setTimeout(5);
~~~

This is an illustrative configuration; the complete example in section 7 uses these exact properties. Once configured, **do not mutate the configuration of a shared TransactionTemplate being used by other threads**. Spring notes that the template holds no conversational state and can be shared, yet it does hold **configuration state**; each distinct policy needs its own template instance.

### Default `REQUIRED` Has One Crucial Condition

`TransactionTemplate` uses `REQUIRED` propagation by default. If there is **no transaction from the caller**, each `execute(...)` call starts and completes its own physical transaction:

~~~text
Caller with NO transaction:
  prepareTx.execute(...) -> TX-A -> COMMIT
  externalWork()         -> outside TX
  finishTx.execute(...)  -> TX-B -> COMMIT/ROLLBACK
~~~

However, if the caller **already opened an enclosing `@Transactional`**, both `REQUIRED` templates can **join the same outer physical transaction**:

~~~text
Caller ALREADY has @Transactional:
  outer TX-X BEGIN
    prepareTx.execute(...) -> JOIN TX-X (not physically committed yet)
    externalWork()         -> still inside TX-X!
    finishTx.execute(...)  -> JOIN TX-X
  outer TX-X COMMIT/ROLLBACK
~~~

In the latter case, the design **is no longer** three independent stages! This is a common pitfall when a team thinks they separated transactions merely by adding multiple template calls.

**Principle for the demo:** the orchestrator has **no outer `@Transactional`** and is called from `main` while the thread has no transaction. In production, inspect the call graph/tests. If separation is genuinely needed regardless of whether the caller has an outer transaction, consider `PROPAGATION_REQUIRES_NEW` and understand the cost/impact on connection pools, locks, and visibility.

## 6. The Right Flow: Non-Database Work Sits Between Two Transactions

Preferred design:

~~~text
Request
  |
  +-- TX-A [short]: INSERT work_item(id, PREPARED) --> COMMIT
  |
  +-- [NO TX]: file processing / HTTP API / long computation
  |
  +-- TX-B [short]: UPDATE work_item(id, DONE) --> COMMIT
  |
  '-- Response

If TX-B fails:
  TX-B ROLLBACK (work_item stays PREPARED)
  TX-C [short]: UPDATE work_item(id, RETRY) --> COMMIT
  record alert/retry per policy
~~~

**Why is this "splitting a flow" rather than just multiple SQL statements?** Because each `COMMIT` is an **explicit durable milestone**. Subsequent work does not need to hold the previous transaction open. The process can resume from database state instead of relying on one transaction spanning the entire request lifecycle.

Rollback example in TX-B:

~~~text
TX-A: INSERT id=102, state=PREPARED       -> COMMIT
        |
        v
External step                              -> SUCCESS
        |
        v
TX-B: UPDATE id=102, state=DONE
      throw IllegalStateException          -> ROLLBACK TX-B
        |
        v
Database remains: id=102, state=PREPARED
        |
        v
TX-C: UPDATE id=102, state=RETRY          -> COMMIT
~~~

**Trade-off:** the remote step may have succeeded while the DB needs retry/reconciliation. `RETRY` does not necessarily mean **blindly calling the remote service again**; the worker must check the external operation ID or idempotency mechanism before repeating side effects.

## 7. Runnable Java 17+ Demo with Spring Framework, JDBC, and H2

The example uses **Java 17+**, **Spring Framework 6.2.5**, **H2 2.2.224**, and Maven. No Spring Boot and no external database server are required.

Key points:

- `prepareTx`, `finishTx`, and `recoveryTx` are initialized once with the same `PlatformTransactionManager`.
- `FlowRunner.runJob(...)` has **no** `@Transactional`; each `TransactionTemplate` creates the transaction boundary itself.
- Simulated remote work runs **outside** any template; the example avoids real HTTP calls to keep stdout deterministic.
- Two jobs run: job 101 succeeds; job 102 fails **after the UPDATE statement inside TX-B**.
- After TX-B fails, querying directly outside any transaction proves row 102 is still `PREPARED`; then TX-C transitions it to `RETRY`.
- There are no sleeps, HTTP calls, or non-reproducible side effects in the demo code.

### 7.1. Directory Structure

~~~text
transaction-template-stages/
  pom.xml
  src/main/java/demo/StageTransactionsDemo.java
~~~

### 7.2. Create `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>transaction-template-stages</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
            <scope>runtime</scope>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides `ApplicationContext` and JavaConfig; `spring-jdbc` provides `JdbcTemplate` and the JDBC transaction manager; `spring-tx` provides `TransactionTemplate`/`TransactionDefinition`. H2 is the in-memory database. Versions are pinned for easy reproducibility.

### 7.3. Create `src/main/java/demo/StageTransactionsDemo.java`

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
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

public class StageTransactionsDemo {

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            FlowRunner runner = context.getBean(FlowRunner.class);

            jdbc.execute("""
                CREATE TABLE work_item (
                    id INT PRIMARY KEY,
                    state VARCHAR(24) NOT NULL
                )
                """);

            runner.runJob(101, false);
            runner.runJob(102, true);

            System.out.println("FINAL 101=" + runner.readState(101)
                    + " 102=" + runner.readState(102));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            var dataSource = new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl("jdbc:h2:mem:stage_demo;DB_CLOSE_DELAY=-1");
            dataSource.setUsername("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource ds) {
            return new JdbcTransactionManager(ds);
        }

        @Bean
        public FlowRunner flowRunner(
                JdbcTemplate jdbc, PlatformTransactionManager manager) {
            return new FlowRunner(jdbc, manager);
        }
    }

    public static class FlowRunner {
        private final JdbcTemplate jdbc;
        private final TransactionTemplate prepareTx;
        private final TransactionTemplate finishTx;
        private final TransactionTemplate recoveryTx;

        public FlowRunner(JdbcTemplate jdbc, PlatformTransactionManager manager) {
            this.jdbc = jdbc;
            this.prepareTx = configured(manager, "prepare-stage");
            this.finishTx = configured(manager, "finish-stage");
            this.recoveryTx = configured(manager, "recovery-stage");
        }

        private static TransactionTemplate configured(
                PlatformTransactionManager manager, String name) {
            var template = new TransactionTemplate(manager);
            template.setName(name);
            template.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRED);
            template.setTimeout(5); // Maximum 5 seconds per new transaction.
            return template;
        }

        public void runJob(int jobId, boolean failFinalization) {
            // TX-A: write checkpoint. When executeWithoutResult returns
            // normally with no outer TX, TX-A has already committed.
            prepareTx.executeWithoutResult(status -> {
                System.out.println("prepare.tx=" + active());
                jdbc.update(
                        "INSERT INTO work_item (id, state) VALUES (?, ?)",
                        jobId, "PREPARED");
            });

            System.out.println("after_prepare[" + jobId + "]="
                    + readState(jobId));

            // NOT inside any template: does not hold a DB transaction.
            simulateExternalStep(jobId);

            try {
                // TX-B: update result.
                finishTx.executeWithoutResult(status -> {
                    System.out.println("finish.tx=" + active());
                    int changed = jdbc.update(
                        "UPDATE work_item SET state = ? "
                        + "WHERE id = ? AND state = ?",
                        "DONE", jobId, "PREPARED");

                    if (changed != 1) {
                        throw new IllegalStateException("invalid state");
                    }

                    if (failFinalization) {
                        throw new IllegalStateException("simulated finish error");
                    }
                });

                System.out.println("after_finish[" + jobId + "]="
                        + readState(jobId));
            } catch (IllegalStateException ex) {
                // Exception escaped callback: TX-B already rolled back.
                System.out.println("finish.error[" + jobId + "]="
                        + ex.getMessage());
                System.out.println("after_rollback[" + jobId + "]="
                        + readState(jobId));

                // Independent TX-C after TX-B has ended.
                recoveryTx.executeWithoutResult(status -> {
                    System.out.println("recovery.tx=" + active());
                    int changed = jdbc.update(
                        "UPDATE work_item SET state = ? "
                        + "WHERE id = ? AND state = ?",
                        "RETRY", jobId, "PREPARED");

                    if (changed != 1) {
                        throw new IllegalStateException("recovery conflict");
                    }
                });

                System.out.println("after_recovery[" + jobId + "]="
                        + readState(jobId));
            }
        }

        private void simulateExternalStep(int jobId) {
            System.out.println("external[" + jobId + "].tx=" + active());
            // In reality this might call HTTP or process a file.
            // The demo performs no external side effects.
        }

        public String readState(int jobId) {
            return jdbc.queryForObject(
                    "SELECT state FROM work_item WHERE id = ?",
                    String.class, jobId);
        }

        private static boolean active() {
            return TransactionSynchronizationManager
                    .isActualTransactionActive();
        }
    }
}
~~~

### 7.4. Why Does This Code Produce Three Clear Transactions?

`StageTransactionsDemo.main(...)` obtains the bean from the context but is **not inside `@Transactional`**. `FlowRunner.runJob(...)` also has no outer transaction. Therefore, the three default `PROPAGATION_REQUIRED` `TransactionTemplate`s each open separate physical transactions when invoked:

- `prepareTx.executeWithoutResult(...)` → new TX-A; commits before external work runs.
- `simulateExternalStep(...)` → runs with no active Spring transaction on the thread.
- `finishTx.executeWithoutResult(...)` → new TX-B; commits or rolls back; when throwing an unchecked exception, the error reaches the caller after the template handles rollback.
- `recoveryTx.executeWithoutResult(...)` → new TX-C, called only after TX-B has failed and ended.

**`@EnableTransactionManagement` is not needed in this example**, because we are not using declarative transaction advice; the template itself calls `PlatformTransactionManager`. Spring still creates the matching `DataSource`/`JdbcTransactionManager` so `JdbcTemplate` uses the same JDBC resource.

### 7.5. Run Command

In the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.StageTransactionsDemo
~~~

Lines printed by the program's `System.out`, ignoring Maven/driver/framework messages:

~~~text
prepare.tx=true
after_prepare[101]=PREPARED
external[101].tx=false
finish.tx=true
after_finish[101]=DONE
prepare.tx=true
after_prepare[102]=PREPARED
external[102].tx=false
finish.tx=true
finish.error[102]=simulated finish error
after_rollback[102]=PREPARED
recovery.tx=true
after_recovery[102]=RETRY
FINAL 101=DONE 102=RETRY
~~~

### 7.6. Reading the Output Line by Line

**Job 101 — success path**

1. `prepare.tx=true`: the first template opened a transaction.
2. Callback inserts row 101 in `PREPARED` state; template commits when callback finishes.
3. `after_prepare[101]=PREPARED`: a query outside any transaction observes the saved checkpoint.
4. `external[101].tx=false`: the external processing step no longer holds the JDBC transaction from the prepare stage.
5. `finish.tx=true`: the second template opens a new transaction, updating `PREPARED -> DONE`.
6. `after_finish[101]=DONE`: the second transaction completed and the result was observed outside the scope.

**Job 102 — finalization step fails**

1. TX-A inserts row 102 and commits the `PREPARED` checkpoint.
2. Simulated remote step runs while `tx=false`.
3. TX-B temporarily changes `PREPARED -> DONE` and then throws `IllegalStateException`.
4. `TransactionTemplate` rolls back **the change from TX-B**. `after_rollback[102]=PREPARED` proves the state saved by TX-A was not lost.
5. TX-C marks `RETRY` in its own transaction, commits, and `after_recovery[102]=RETRY`.
6. Finally, the DB has job 101 `DONE` and job 102 `RETRY`.

**What must be understood accurately:** job 102 does not revert to "never requested". TX-A committed, so the durable checkpoint remains intact. This **is the trade-off** enabling stage-by-stage recovery.

## 8. Splitting Stages Properly Does Not Mean Wrapping Every Function in a Template

A common mistake is:

~~~java
template.executeWithoutResult(status -> {
    createCheckpoint();
    callRemoteService(); // Defeats the goal of splitting transactions!
    finalizeRecord();
});
~~~

Even though `TransactionTemplate` is used, **the entire callback is still inside one transaction**. Switching from `@Transactional` to a template does not automatically make a transaction shorter.

Similarly, the following example still has an outer transaction if the enclosing method is `@Transactional`:

~~~java
@Transactional
public void outer() {
    template.executeWithoutResult(status -> saveCheckpoint());
    doSlowWork();
    template.executeWithoutResult(status -> finalizeData());
}
~~~

If `template` uses `PROPAGATION_REQUIRED`, the callbacks may simply **join outer**, creating no two independent commits. When a stage must genuinely separate from outer, remove the outer boundary or redesign the call graph. `REQUIRES_NEW` can be used when there is a clear reason, yet suspending outer does not release all locks/resources and can consume an extra connection.

**Good practice:** draw a timeline of `BEGIN -> SQL -> COMMIT/ROLLBACK -> external work` and write tests proving DB state **after each boundary**, rather than merely reading `isActualTransactionActive()` logs.

## 9. Distinguishing Throwing Exceptions, Catching Exceptions, and setRollbackOnly

`TransactionTemplate` does not have `rollbackFor` like `@Transactional`. The callback receives `TransactionStatus` and can make rollback decisions in two main ways:

### 9.1. Letting an Unchecked Exception Escape the Callback

~~~java
template.executeWithoutResult(status -> {
    jdbcTemplate.update(
        "UPDATE work_item SET state = ? WHERE id = ?",
        "DONE", 102);
    throw new IllegalStateException("cannot finalize");
});
~~~

This is an illustrative example. Spring rolls back the callback's transaction per the manager's semantics and **rethrows the unchecked exception**. The caller can catch the error **outside `executeWithoutResult`**, when the transaction template has already processed the corresponding rollback.

If the transaction template **joins an outer transaction**, the rollback may mark the outer transaction rollback-only rather than performing an immediate physical rollback. Do not draw conclusions about independence without knowing propagation.

### 9.2. Catching Errors Inside the Callback and Proactively Marking Rollback-Only

~~~java
boolean accepted = template.execute(status -> {
    try {
        performBusinessValidationAndWrites();
        return true;
    } catch (ExpectedBusinessException ex) {
        status.setRollbackOnly();
        return false;
    }
});
~~~

This is an **illustrative snippet**, without defining the methods and exception. With a new transaction owned by the template, `status.setRollbackOnly()` causes the scope to roll back when the callback returns. The caller can still receive `false` instead of an exception; design a clear contract.

If the callback **catches the error and returns normally without marking rollback-only**, the transaction may commit, provided the manager/DB has not marked rollback-only for another reason. This is a source of data corruption when teams write `catch (Exception e) { log(e); }` right inside a callback.

### 9.3. Checked Exceptions and Converting Them to Appropriate Failures

`TransactionCallback` does not declare arbitrary checked exceptions. When calling an API that throws `IOException`, you can catch the checked exception **inside the callback**, mark rollback-only, and return a structured result; or convert it into a meaningful unchecked business exception and let it escape the callback.

~~~java
template.executeWithoutResult(status -> {
    try {
        importOneSmallChunk();
    } catch (java.io.IOException ex) {
        throw new IllegalStateException("chunk import failed", ex);
    }
});
~~~

**Illustrative snippet**; `importOneSmallChunk` must be defined. Do not mistakenly assume "checked exceptions commit by default" in `TransactionTemplate` in exact analogy to Spring declarative rollback rules: the programmatic API uses callbacks and a different error-control model, so checked exception handling must be decided explicitly.

### 9.4. When Using Multiple Consecutive Templates

If TX-B's callback throws an exception, the error **does not automatically roll back an already committed TX-A**. If recovery TX-C's callback also throws an exception, TX-C may roll back while TX-A still remains. Thus, the orchestration layer must ensure alerts are emitted or a worker can retry even when recording the recovery state itself fails.

## 10. Separate Timeout, Isolation, and Read-Only per Stage

You can create multiple `TransactionTemplate` instances with different configurations:

~~~java
TransactionTemplate readTx = new TransactionTemplate(manager);
readTx.setReadOnly(true);
readTx.setTimeout(3); // 3 seconds.

TransactionTemplate writeTx = new TransactionTemplate(manager);
writeTx.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
writeTx.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
writeTx.setTimeout(5); // 5 seconds.
~~~

This is an **illustrative configuration snippet**. These properties mainly apply to a **newly created** transaction. If `REQUIRED` merely joins an outer transaction, isolation/timeout/read-only on the inner template do not necessarily alter the existing physical transaction.

**Timeout** is not a Java thread timer that always interrupts right at expiration. It is applied by the transaction manager/driver according to supported mechanisms. If a step outside the transaction has its own HTTP timeout, configure the HTTP client timeout **separately** rather than expecting transaction timeout to protect the external stage.

**Read-only** is a hint to the transaction manager/driver/ORM, not a security rule strictly blocking all DML. Declare read-only only on purely read-only stages.

### Is Replacing `REQUIRED` with `REQUIRES_NEW` Appropriate?

~~~java
TransactionTemplate isolated = new TransactionTemplate(manager);
isolated.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
~~~

If the caller already has a transaction, `REQUIRES_NEW` requests an independent physical transaction. This can ensure a stage genuinely commits before outer completes, yet brings **partial commits**, potential need for a second connection, lock contention, and uncommitted-data visibility considerations.

**Prefer designing the orchestrator without an outer transaction** when the goal is simply splitting a long flow. Use `REQUIRES_NEW` intentionally when a stage must be independent even inside an outer transaction whose consequences you control.

## 11. External APIs Do Not Participate in DB Rollback

Suppose a stage communicates with a payment gateway:

~~~text
TX-A writes PREPARED     -> DB COMMIT
Remote charge            -> SUCCESS outside DB
TX-B writes CHARGED      -> DB COMMIT or ROLLBACK
~~~

If the remote charge succeeds yet TX-B rolls back or the process crashes, **the DB does not yet reflect the payment result**, while the remote system has already charged. There is no way to use `TransactionTemplate` alone to roll back a remote charge like rolling back a JDBC row.

Mechanisms to consider:

- **Idempotency key:** use the same operation ID for every retry so the remote provider does not create duplicate charges.
- **Reconciliation:** after a restart, query the remote system for the result by operation ID before calling again.
- **Compensating action:** issue a refund/cancel if business rules allow, though compensation itself can fail and must be tracked.
- **Timeout/retry policy:** clearly distinguish "definitely not executed" errors from "uncertain whether executed" errors.
- **Durable workflow state:** store checkpoints and pending state in the DB; do not rely solely on a boolean variable in RAM.

State machine diagrams must distinguish "not sent", "sent with unknown outcome", "remote confirmed", and "DB confirmed". A simple `RETRY` column like in the demo **is insufficient** for running real payments; the demo only illustrates transaction boundaries.

## 12. Transactional Outbox: When Events Must Be Emitted After Commit

A commonly used pattern:

~~~text
TX-A:
  INSERT business row (PREPARED)
  INSERT outbox event (PROCESS_WORK_ITEM)
COMMIT

Outbox publisher:
  read committed event
  send message/queue
  retry with stable event ID

Worker:
  execute external task
  TX-B writes DONE or recovery state
~~~

Because the business row and outbox event are written in **the same physical transaction**, there is never a state where "the business row committed yet the intent to publish was not recorded". Still, **message delivery** happens after commit and may repeat; consumers should be idempotent.

Calling `publishMessage()` directly inside TX-A's callback can send the message to the broker before DB commit, and it cannot be rolled back by the JDBC transaction manager. Publishing only via an in-memory `afterCommit` callback risks losing the publish action if the process crashes after DB commit. Outbox solves **durability of event-emission intent**, not a distributed atomic commit with the broker.

This is a complementary architecture for the `TransactionTemplate` lesson, not an automatic feature of `TransactionTemplate`.

## 13. Reducing Connection and Lock Hold Time Properly

Short transactions generally reduce connection/lock hold times, yet you must check **where resources are actually held**:

- With `JdbcTransactionManager`, the connection is normally bound to the thread by Spring during the transaction and cleaned up when the transaction completes.
- If an outer transaction wraps the entire orchestrator, `REQUIRED` templates do not release connections/locks between stages.
- A slow operation **inside the callback** still keeps the transaction open; extracting code into helper functions does not shorten the transaction by itself.
- A read-only callback scanning millions of rows can also hold resources for a long time; use proper pagination/chunking.
- Query isolation, pessimistic locking, `SELECT ... FOR UPDATE`, indexing, and DB execution plans heavily impact lock duration.
- Using `REQUIRES_NEW` inside an outer transaction may require borrowing a second connection, causing the pool to **exhaust faster** rather than freeing outer's connection.
- A short transaction whose commit is delayed by DB/network latency can also cause contention.

**Do not guess performance.** Observe connection pool wait time, active connections, transaction duration, lock waits, query latency, deadlocks, DB logs, and p95/p99 throughput.

## 14. Retry, Idempotency, and Concurrency

### 14.1. Why Must Retries Inspect Committed State?

Job 102 in the demo remained `RETRY`. A later worker should read the state in a short read transaction, check the operation ID, and **attempt to claim the job** safely before retrying.

Example conditional SQL statement:

~~~sql
UPDATE work_item
SET state = 'PROCESSING'
WHERE id = 102 AND state = 'RETRY';
~~~

This SQL snippet is illustrative only. The affected row count must be checked: `1` means the worker claimed it cleanly under the condition; `0` means another worker already claimed it or the state changed. Larger systems may need a version column/optimistic locking, lease timestamps, and handling for workers dying while holding `PROCESSING`.

**Do not do**:

~~~java
if ("RETRY".equals(readState(id))) {
    // Another worker may change the state between read and update.
    executeAgainWithoutClaim(id);
}
~~~

This is an illustrative anti-pattern. Separate read-then-act without concurrency control can produce double execution.

### 14.2. Preventing Duplicate Checkpoints

In the demo, `INSERT` fails with a duplicate key error if called again with the same `jobId`; that is a primary key feature exposing bugs. In production, a unique **idempotency key** and logic for when the key already exists are needed:

- If `DONE`: return the already completed result.
- If `PREPARED/PROCESSING`: do not create a new job; wait/check status.
- If `RETRY`: claim safely and execute the proper resume workflow.
- If `FAILED` or unknown outcome: follow verification policy; do not blindly skip.

A "create" request whose response is lost after commit **may** have already created the job. If the client retries, query by idempotency key before deciding to insert again.

### 14.3. Retry the Failed Stage, Not Necessarily From Scratch

If `PREPARED` already committed and the remote step already produced a durable outcome, rerunning from step one can cause duplicates. The design should **resume from the checkpoint** with suitable transitions and verification of external results.

You can cap retry counts and apply exponential backoff, dead-letter queues, and alerts. Those policies belong to **workflow orchestration**, not automatically provided by `TransactionTemplate`.

### 14.4. Conditional Transactional State Transitions

In the demo code, `UPDATE ... WHERE id = ? AND state = 'PREPARED'` asserts row count is **1**. This is a guard against arbitrarily overwriting unexpected states, though not a complete concurrency solution if other steps like remote calls can run in parallel.

A production system should design a state machine respected by **every writer**, preventing a late exception from reverting `DONE` back to `RETRY`.

## 15. Points Where Crashes Can Happen

Splitting transactions into stages clarifies **what committed**, yet introduces gaps between stages. Inspect each point:

| Failure moment | Possible DB data remaining | Recovery direction |
| --- | --- | --- |
| Inside TX-A before commit | Job not written yet | Caller can retry create with idempotency key |
| Immediately after TX-A commits | `PREPARED` | Worker scans unprocessed checkpoints |
| During remote call outside TX | `PREPARED`, remote outcome unknown | Look up remote by operation ID; do not call blindly again |
| Remote succeeds, before TX-B | `PREPARED` | Reconcile remote outcome then finalize DB state |
| Inside TX-B after UPDATE, before commit | DB may roll back to `PREPARED` | Query state after exception; retry/compensate |
| TX-B commits yet response lost | May already be `DONE` | Re-read DB by operation ID; avoid duplicates |
| Inside TX-C writing `RETRY` | May still be `PREPARED` | Scanner must handle overdue `PREPARED` too |
| Process dies after `RETRY` | Durable `RETRY` | Worker claims/retries under control |

**Do not trust that every exception from `execute(...)` guarantees the DB definitely rolled back.** There are errors at commit time where the database-side outcome is uncertain from the client's perspective. After an uncertain commit failure, inspect or reconcile state using a stable key.

## 16. Comparing TransactionTemplate and `@Transactional` When Splitting Flows

| Situation | TransactionTemplate | `@Transactional` |
| --- | --- | --- |
| Service method with one clear transaction | Works, though adds extra code | Usually concise and readable |
| Long method needing **multiple short TX boundaries in the same flow** | **Very suitable**: wrap each callback | Requires splitting beans/methods and proper proxy call graphs |
| Catching errors between transactions and recording recovery state | Explicit with `try/catch` **outside** callbacks | Possible with separate services, yet easy to trip over self-invocation |
| Varying propagation/timeout per stage | Each template has its own config | Each method has its own annotation |
| Avoiding self-invocation proxy pitfalls | Template callback is called directly, no AOP interceptor needed | Must ensure calls go through proxy |
| Placing transactions in a reactive pipeline | Unsuitable for reactive streams | Has reactive `@Transactional` or `TransactionalOperator` |
| Rollback policies across many checked exception types | Handle/structure callback proactively, `setRollbackOnly` | Convenient `rollbackFor`/`noRollbackFor` |
| Testing exact boundaries | Easy to mock `TransactionOperations`, integration-test real DB | Integration-test via proxy |

**Recommendation:** combine both mechanisms selectively. Use `@Transactional` for short service units; use `TransactionTemplate` when orchestration genuinely needs control over BEGIN/COMMIT/ROLLBACK **at multiple points within a flow**. Do not mix the two layers unconsciously and create hard-to-predict nested/participating transactions.

### When Should You Use `TransactionOperations`?

`TransactionOperations` is the interface of `TransactionTemplate`, injectable for easier testing. When a service only needs `execute(...)`/`executeWithoutResult(...)` without altering template settings, programming to the interface makes mocking/faking more convenient.

Example:

~~~java
public class ReportService {
    private final TransactionOperations transactions;

    public ReportService(TransactionOperations transactions) {
        this.transactions = transactions;
    }

    public void rebuild() {
        transactions.executeWithoutResult(status -> rebuildOnePart());
    }
}
~~~

This is an illustrative pattern without an implementation of `rebuildOnePart`. In a real application, ensure the supplied `TransactionOperations` instance has propagation/isolation/timeout matching the desired boundary.

## 17. Testing: Verifying State After Each Commit

Integration tests for transaction stages must verify **DB state after the template returns**, not just how many times callbacks were invoked.

Cases to cover:

1. **Full success:** `PREPARED` after TX-A, `DONE` after TX-B.
2. **TX-A throws unchecked exception:** no new job row exists.
3. **External step fails:** TX-A remains `PREPARED`; error-handling step records appropriate state without holding a DB transaction during the remote call.
4. **TX-B updates and then throws exception:** rolls back to `PREPARED`, not `DONE`.
5. **TX-C succeeds:** `PREPARED -> RETRY` commits in a new transaction.
6. **TX-C also fails:** needs scanner retry or alerting; TX-A's checkpoint still remains.
7. **Duplicate `jobId`/idempotency key:** neither duplicate jobs nor duplicate remote side effects are created.
8. **Concurrent workers:** only one worker claims the job via guarded update/lock/lease.
9. **Outer caller accidentally has `@Transactional`:** test detects that two `REQUIRED` templates join outer and lose independence.
10. **Uncertain commit outcome:** read/reconcile by operation ID rather than assuming exception means uncommitted.

### Be Careful with `@Transactional` on Test Methods

Spring TestContext may start an outer transaction for a `@Transactional` test and roll it back when the test finishes. Your `PROPAGATION_REQUIRED` `TransactionTemplate` calls then **join the test transaction**, defeating the purpose of verifying independent commits.

For integration tests verifying boundaries, **do not** wrap the test in a default outer transaction; or explicitly manage `TestTransaction`/end the test transaction. Read the DB after each boundary in the actual context under test.

### Observing Actual Transactions

While debugging, you can print:

~~~java
boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();

boolean sync =
        TransactionSynchronizationManager.isSynchronizationActive();
~~~

This is an illustrative API snippet. `active=true` indicates a Spring transaction is active on the thread; it **does not prove** it is a new transaction, nor does it prove a successful commit. `sync=true` can appear even when there is no actual transaction.

To measure resources, enable the `org.springframework.transaction` logger in test environments and observe the connection pool; do not turn on sensitive traces or log SQL bind parameters casually in production.

## 18. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Right approach |
| --- | --- | --- |
| Wrapping the entire long flow in one template | Transaction still holds connections/locks during network calls | Put each short DB segment in its own `execute` |
| Splitting code into methods while keeping an outer `@Transactional` | `REQUIRED` templates join outer, creating no independent commits | Remove outer boundary or design propagation intentionally |
| Assuming every template call always creates a new TX | `REQUIRED` only opens a new one when no outer exists | Check caller context and transaction definition |
| Putting an HTTP call inside TX thinking HTTP rolls back | External side effects do not join JDBC rollback | Call outside TX; use idempotency and compensation |
| Thinking TX-B rollback rolls back an already committed TX-A | Partial commits are a consequence of splitting stages | Persist checkpoint/recovery state |
| Catching errors **inside** callback and swallowing them | Normal callback return can lead to commit | Rethrow unchecked or call `status.setRollbackOnly()` |
| Treating `setRollbackOnly()` as equivalent to a forced exception | Callback can return normally; caller must understand outcome | Return structured result or throw intentionally |
| Using one shared template and mutating timeout at runtime | Configuration state mutated while threads use it | Configure once; use separate templates for different policies |
| Confusing `timeout=5` with 5 milliseconds | Wrong deadline | Spring transaction timeout is in seconds |
| Using `REQUIRES_NEW` to fix every outer transaction | Can exhaust connection pool and break atomicity | Use only when an independent boundary is intended |
| Retrying remote immediately after an ambiguous timeout | Can double-charge/double-create | Use operation IDs and reconcile |
| Re-running checkpoint with non-idempotent INSERT | Duplicate key or duplicate operations | Unique key + resumable state machine |
| Letting two workers process one job concurrently | Race conditions, double effects | Guarded UPDATE/optimistic locking/lease |
| Writing DONE before verifying remote outcome | DB falsely reports success | Choose accurate states and verification steps |
| Relying on `isActualTransactionActive()` to conclude commit | Flag only states active status | Query after boundary and use proper commit callbacks |
| Test wrapped in `@Transactional` assuming template committed for real | `REQUIRED` template joined outer test transaction | Test outside test transactions or manage completion explicitly |
| Using `TransactionTemplate` for a reactive pipeline | Imperative thread-bound API does not wrap reactive contexts | Use `TransactionalOperator` and reactive manager |

## 19. Self-Check Questions

**Question 1.** A flow consists of `createCheckpoint()`, a 10-second HTTP call, and `finish()`. Why shouldn't you place `@Transactional` over the entire flow by default?

**Answer:** The DB transaction can hold connections/locks throughout the HTTP call, while HTTP side effects cannot roll back with JDBC. If business rules allow intermediate states, splitting into short TXs reduces resource hold time and enables recovery from checkpoints.

**Question 2.** `TransactionTemplate.executeWithoutResult(...)` is called twice consecutively when the caller has **no transaction** and propagation is `REQUIRED`. How many physical transactions occur?

**Answer:** Normally two separate transactions, as the template opens and completes one boundary each time; there is no enclosing outer transaction.

**Question 3.** If `@Transactional` is added to the caller while both templates stay `REQUIRED`, are there still two independent commits?

**Answer:** Independence cannot be assumed; both can join the outer's single physical transaction. To separate them, change the architecture or propagation.

**Question 4.** TX-A commits `PREPARED`, TX-B updates to `DONE` and throws an unchecked exception. What is the DB state prior to recovery?

**Answer:** `PREPARED`: TX-B rolls back its update, while the already committed TX-A is not undone.

**Question 5.** Remote payment succeeded yet TX-B rolled back. Should payment be called again immediately with a new request?

**Answer:** No. Look up the outcome via the operation/idempotency key to avoid double-charging; you can reconcile and update only the DB.

**Question 6.** Inside a callback there is `catch (Exception ex) { log(ex); }`, followed by a normal return. Does Spring always roll back?

**Answer:** No. Unless rollback-only is set or an error is thrown—and assuming the manager/DB has no other rollback-only condition—the template can attempt to commit.

**Question 7.** A template is shared by multiple services. Can you continuously change `setTimeout(...)` per request?

**Answer:** Do not mutate shared configuration while in use; create separate templates for different policies, or keep configuration stable.

**Question 8.** When retrying a partially committed stage, why is a unique operation ID needed?

**Answer:** Request/commit responses can be lost; without a stable ID, rerunning can create duplicate jobs/side effects. The ID enables status lookup, safe claiming, and idempotent remote calls.

**Question 9.** Using `@Transactional` on a test method, can you properly test two independent transactions with `REQUIRED` templates?

**Answer:** Not by default: the outer test transaction can cause both templates to join it and roll back when the test finishes. Test boundaries under conditions without a matching outer transaction.

**Question 10.** If TX-C writing `RETRY` also fails, does the already committed TX-A disappear?

**Answer:** No. TX-A still holds `PREPARED`. A scanner/reconciliation process and alerts are needed to pick up incomplete jobs.

## Takeaways

- **`TransactionTemplate` puts explicit transaction boundaries in imperative code**, via `execute(...)` or `executeWithoutResult(...)` and a `PlatformTransactionManager`.
- **To split a long flow:** place short DB operations in separate templates; place HTTP, file/CPU work outside transactions; record meaningful checkpoints rather than merely splitting method names.
- **Default `REQUIRED` is not always independent:** only when there is no outer transaction does each `execute` create its own physical transaction.
- **A commit of an earlier TX is not rolled back by a later TX.** This is a strength for resumption yet an atomicity trade-off; state machines, retries, idempotency, and compensation/reconciliation are required.
- **Unchecked exceptions escaping a callback usually trigger rollback**; if catching an error inside a callback, use `TransactionStatus.setRollbackOnly()` when rollback is desired.
- **`TransactionTemplate` does not make remote APIs atomic with the DB**; outbox, idempotency, and compensating actions address the architecture outside the DB.
- **Always test after the actual commit/rollback boundary**, especially when an outer `@Transactional`, test transactions, multiple transaction managers, or uncertain commit outcomes are involved.

## Official References

1. Spring Framework — [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): using `TransactionTemplate`, callbacks, rollback-only, and transaction attributes.
2. Spring Framework — [`TransactionTemplate` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html): API, configuration state, and thread safety.
3. Spring Framework — [`TransactionOperations` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionOperations.html): `execute` and `executeWithoutResult`.
4. Spring Framework — [Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRED` and `REQUIRES_NEW`, physical vs. logical transactions, connection pools.
5. Spring Framework — [Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction interceptors and method boundaries.
6. Spring Framework — [TransactionDefinition Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html): propagation, isolation, read-only, and timeout semantics.
7. Spring Framework — [`JdbcTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html): JDBC transaction manager used in the demo.
