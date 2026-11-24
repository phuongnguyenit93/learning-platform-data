# SERIALIZABLE and the possibility of transaction retries in Spring Framework

## Key focus

`SERIALIZABLE` is the transaction isolation level aimed at guaranteeing that **committed transactions produce an outcome equivalent to some serial execution schedule**. It does not promise that all concurrent transactions will succeed, nor does it mean the database forces every transaction to run one at a time. To preserve correctness when read/write conflicts occur, the database **may force one or more transactions to roll back**. The application must then **retry the entire transaction from the beginning**, including re-reading data, re-checking business conditions, choosing SQL statements, and writing data.

In Spring, we typically declare:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE
)
public void allocateResources() {
    // Read current state, check invariant, then update data
}
```

This is an **illustrative fragment**, lacking a class and repository to run standalone. It only takes effect at a transaction boundary actually managed by Spring advice. If this call **joins** an outer `REQUIRED` transaction already running at a different isolation level, the inner `SERIALIZABLE` declaration **does not automatically raise the isolation level** of the existing physical transaction by default. Place isolation at the boundary that opens a new transaction, or choose `REQUIRES_NEW` when business semantics permit.

In PostgreSQL, the characteristic error is SQLSTATE **`40001` (`serialization_failure`)**. This signals that the current transaction cannot safely continue/commit under the observed concurrent schedule. A proper retry means **starting a new transaction and re-running the entire business logic**, not catching an exception mid-transaction and re-executing only the `UPDATE` statement. Some deadlocks may also be retried under a separate policy (`40P01` in PostgreSQL), though not all SQL errors should be treated as transient.

This lesson belongs to the **Isolation levels** group of **Spring Framework – transaction-management**. It focuses on the possibility of retries under `SERIALIZABLE`, simulating conflicts, structuring transactions/retries in Spring, safety limits, and a standalone runnable Java 17 example.

---

## 1. What does SERIALIZABLE guarantee, and what does it not?

A transaction typically consists of several steps:

```text
T1:
  read current data
  check business condition
  compute decision
  update one or more rows
  commit

T2 running concurrently:
  read current data
  check similar condition
  update data
  commit
```

If read/write operations interleave, the final outcome may correspond to neither **T1 then T2** nor **T2 then T1**. Such a schedule exhibits a **serialization anomaly**.

`SERIALIZABLE` aims to guarantee that any set of committed transactions can be explained as some **serial history**. A database can achieve this by:

- Locking and blocking conflicting operations via a specific mechanism.
- Checking conflicts/dependencies to decide when a transaction must abort.
- Combining MVCC, predicate locking, or other concurrency control algorithms depending on the DBMS.

In PostgreSQL specifically, `SERIALIZABLE` uses **Serializable Snapshot Isolation (SSI)**: transactions read from snapshots while tracking read/write dependencies that could form a non-serializable schedule; when a risk is detected, the system may abort a transaction. Do not imagine that every `SELECT` immediately acquires locks blocking all writers. SSI incurs conflict-tracking overhead and can still experience other blocking due to row locks or SQL statements.

### 1.1. Serializable does not mean linearizable

- **Serializability**: committed transactions are equivalent to some valid serial order.
- **Strict serializability / linearizability**: additionally constrains real-time ordering across non-overlapping operations.

These are distinct consistency properties. Do not see `Isolation.SERIALIZABLE` and assume a distributed system or the application's entire API provides linearizability.

### 1.2. Serializable does not make "non-DB operations" transactional

Emails, HTTP requests, file writes, or events sent to a message broker outside the transaction resource or to another datasource **do not automatically roll back** when a JDBC transaction aborts. Re-running the entire transaction can cause non-DB side effects to happen **twice** if placed inside the retried block. Separate side effects or use an outbox/transactional messaging/idempotency appropriately.

### 1.3. Serializable does not guarantee success in bounded time

A transaction may be aborted multiple times under high contention. Retrying does not mean the second attempt is guaranteed to succeed; the system needs an attempt limit, backoff, contention monitoring, and a clean failure response if the retry budget is exhausted.

## 2. Why can SERIALIZABLE fail even when every SQL statement is valid?

SQL statements in two individual transactions can be syntactically valid, satisfy constraints, and succeed when run sequentially. The problem arises from **the relationship between snapshots and writes across multiple concurrent transactions**.

An intuitive example with the rule: *at least one doctor must always be on call*. Initially both doctors A and B are on call:

| ID | Doctor | `on_call` |
| --- | --- | --- |
| 1 | A | `true` |
| 2 | B | `true` |

Transaction T1 wants to let A leave duty, and T2 wants to let B leave duty. Both execute:

1. `SELECT COUNT(*) FROM doctors WHERE on_call = TRUE`.
2. If the count on call is greater than 1, update their doctor to `on_call=FALSE`.
3. Commit.

An overlapping schedule can look like:

```text
Time           T1 (A leaves)                    T2 (B leaves)
----------------------------------------------------------------
t0             BEGIN SERIALIZABLE               BEGIN SERIALIZABLE
t1             COUNT(on_call)=2
t2                                                COUNT(on_call)=2
t3             UPDATE id=1 SET false
t4                                                UPDATE id=2 SET false
t5             COMMIT
t6                                                COMMIT -> may get 40001
```

If both committed, the final count of on-call doctors would be **0**, violating the invariant. Yet in any **serial** schedule, the second transaction would observe only one doctor remaining on call and refuse to let the last one leave. Hence a schedule where both decide from count=2 and commit is not serializable.

In an SSI implementation such as PostgreSQL, the database detects the read/write dependencies and **aborts at least one transaction** in an eligible conflicting scenario. The aborted transaction must re-read the count in **a new transaction**; at that point the business check may produce a different outcome. This is precisely why retries must re-run **decision logic**, not merely resubmit the UPDATE statement.

### 2.1. Write skew vs. lost update

- **Lost update**: two transactions update the same data in a way where one change can be overwritten.
- **Write skew**: two transactions read a shared dataset and then update **different rows**, causing an overall invariant to break despite no overlapping row updates.

The on-call doctors example is **write skew**. It explains why locking or checking **only the row you are about to UPDATE** may fail to protect a multi-row invariant.

### 2.2. Database dependence

Databases do not implement isolation using the exact same mechanism. A level named `SERIALIZABLE` can involve locking, optimistic validation, MVCC/SSI, and different exception types. PostgreSQL uses standard error `40001` for serialization failures; MySQL/InnoDB, SQL Server, Oracle, or H2 can have different error patterns, detection rules, and overhead.

Therefore, a JDBC/H2 example simulating an exception **does not prove** PostgreSQL's SSI behavior. This lesson separates a real SQL demonstration on PostgreSQL from a Java example using H2 to deterministically test the **retry mechanism**.

## 3. Real PostgreSQL demonstration with two sessions

This section is for **PostgreSQL** and requires two `psql` terminals connected to **the same database**. Each session is a separate connection. Use a test database; do not run on production data.

### 3.1. Prepare data once, outside competing transactions

```sql
DROP TABLE IF EXISTS doctors;

CREATE TABLE doctors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    on_call BOOLEAN NOT NULL
);

INSERT INTO doctors(id, name, on_call)
VALUES (1, 'A', TRUE),
       (2, 'B', TRUE);
```

Run the setup in one session and wait for commit/autocommit to finish. Open two new sessions or two parallel connections.

### 3.2. Coordinating the ordering of the two sessions

**Session 1:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM doctors WHERE on_call = TRUE;
-- 2; keep transaction open, do not COMMIT yet
```

**Session 2:**

```sql
BEGIN TRANSACTION ISOLATION LEVEL SERIALIZABLE;

SELECT COUNT(*) FROM doctors WHERE on_call = TRUE;
-- 2; keep transaction open, do not COMMIT yet
```

Now both have read their initial snapshot before either session commits.

**Session 1:**

```sql
UPDATE doctors SET on_call = FALSE WHERE id = 1;
COMMIT;
```

**Session 2:**

```sql
UPDATE doctors SET on_call = FALSE WHERE id = 2;
COMMIT;
```

In this schedule, to prevent a non-serializable outcome, **one of the transactions may be aborted with SQLSTATE `40001`**. The error may be raised during the write statement or at commit; processing order and which session gets aborted depend on the actual schedule and PostgreSQL. Once a session has been aborted, do not keep using that transaction to retry writes; exit/roll back and open a new transaction.

You can use `\set VERBOSITY verbose` in `psql` to see SQLSTATE or inspect error info exposed by the driver; do not rely on exact error message wording because messages can change. Once one transaction has committed, the retrying session must start with a fresh `BEGIN ... SERIALIZABLE`, re-read the on-call count, and then decide whether updating is still allowed.

### 3.3. Why retrying the UPDATE statement alone is wrong

Suppose T1 commits first, marking A off duty. T2 is aborted. If T2 merely resubmits:

```sql
UPDATE doctors SET on_call = FALSE WHERE id = 2;
```

without re-reading `COUNT(*)`, the outcome can violate the invariant: both A and B are off duty. The original decision "B may leave duty" was based on count=2 from **the old snapshot**, which is no longer valid. A proper retry must re-run the read, check, and only then earn the right to UPDATE in the new transaction.

**Mandatory rule:** Retry the entire transaction *including reads and SQL/value decision computations*. PostgreSQL cannot generically retry a transaction at the server layer because it cannot know how application business decisions depended on read results.

## 4. Which error types should be considered retryable?

For PostgreSQL:

| SQLSTATE | Error name | Typical handling |
| --- | --- | --- |
| `40001` | `serialization_failure` | **Retry the entire transaction**, with a limit and backoff policy |
| `40P01` | `deadlock_detected` | May retry the entire transaction per policy |
| `23505` | `unique_violation` | **Do not** auto-retry every case; could be a permanent data error or a serialization-like race depending on logic |
| `23P01` | `exclusion_violation` | Only consider retrying if its relationship to concurrent decisions is understood |
| `23503` | `foreign_key_violation` | Usually a data integrity violation; do not auto-retry unconditionally |
| `42601` | `syntax_error` | SQL error; retrying verbatim will not fix it |
| `28P01` | Authentication failure | Configuration/credential error; not a serialization conflict |

**Distinguish `40001` from `40P01`:** a serialization failure is distinct from a deadlock, even though both belong to PostgreSQL's transaction rollback class. Many systems retry both, yet expanding the retry set should be grounded in DB/driver semantics and business logic rather than catching every `RuntimeException`.

**Distinguish SQLSTATE from message text:** text like "could not serialize access due to concurrent update" is human-readable but less stable than SQLSTATE. For PostgreSQL, prefer `SQLException.getSQLState()` from the root cause or the data-access layer's exception classifier.

### 4.1. Spring translates SQLException to its own exceptions

Spring JDBC uses exception translation to convert many `SQLException`s into subclasses of `DataAccessException`. Some concurrency/locking errors map to classes such as `PessimisticLockingFailureException`, `CannotAcquireLockException`, or other subclasses depending on translator, driver, and version.

Do not assume **every** `40001` error across all Spring versions always becomes the exact **same** Java exception class, especially when the error occurs during `commit()` rather than `JdbcTemplate.update()`. `CannotSerializeTransactionException` is an older type deprecated by Spring since 6.0.3; do not build a retry policy tied solely to that class name.

A PostgreSQL diagnostic strategy is walking the cause chain for an `SQLException` with SQLSTATE `40001`; in real systems also check how the connection pool, ORM, JPA, or transaction manager wraps exceptions. When `SQLException.getNextException()` is present, many drivers attach additional details along that chain.

### 4.2. Do not retry errors you do not understand

If code does:

```java
catch (Exception ex) {
    // retry the whole method for any error
}
```

this is an **illustrative anti-pattern**, not code to use. It can repeat business exceptions (insufficient funds, invalid data), SQL syntax errors, permission errors, or multiple HTTP calls. Retrying must be a **conditional policy**, not a blanket mechanism masking all errors.

## 5. Where should retries sit in Spring?

Correct model:

```text
Caller
  |
  v
RetryCoordinator (outside transaction)
  |
  +-- attempt 1:
  |      begin NEW SERIALIZABLE transaction T1
  |      re-read data, check rules, write DB
  |      commit T1 or roll back T1 on 40001
  |
  +-- if 40001 and budget remains:
  |      backoff (+ jitter), then attempt 2
  |      begin NEW SERIALIZABLE transaction T2
  |      re-read data, recompute, write DB
  |      commit T2 or roll back T2
  |
  +-- if commit succeeds -> return result
  +-- if budget exhausted -> report error, do not claim committed
```

**Retry outside the transaction boundary.** This matters because a transaction already marked aborted/rollback-only by the database cannot become a new transaction simply by re-running SQL statements inside a `catch` block.

### 5.1. `TransactionTemplate`: safe ordering of begin/commit/rollback

With imperative Spring transactions:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);
template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
template.setIsolationLevel(
        TransactionDefinition.ISOLATION_SERIALIZABLE);

for (int attempt = 1; attempt <= 3; attempt++) {
    try {
        template.executeWithoutResult(status -> {
            // re-read, validate, perform all DB work
        });
        break;
    } catch (RuntimeException ex) {
        // only retry if verified as an eligible serialization/deadlock error
        // other exceptions must be rethrown
    }
}
```

This is an **illustrative structure**, without retry-classification and backoff logic. `TransactionTemplate` manages the lifecycle itself, ensuring a failing callback rolls back before the exception leaves `executeWithoutResult`. When an error occurs during commit, the exception also propagates out of the `execute...` call so the retry coordinator can classify it. `REQUIRES_NEW` creates a separate physical transaction per attempt when backed by a compatible manager/resource.

**Do not** wrap the whole loop in an outer `@Transactional(REQUIRED)` and call only a repository inside, thinking each loop iteration gets a fresh physical transaction. By joining T1, every iteration remains trapped in T1's same snapshot/rollback-only context.

### 5.2. Declarative `@Transactional`: separate two Spring beans

```java
@Service
public class RetryCoordinator {
    private final TxWorker worker;

    public RetryCoordinator(TxWorker worker) {
        this.worker = worker;
    }

    public void submit() {
        // retry loop here; do not put @Transactional on submit()
        worker.executeOneAttempt();  // call through another bean's proxy
    }
}

@Service
public class TxWorker {
    @Transactional(
        propagation = Propagation.REQUIRES_NEW,
        isolation = Isolation.SERIALIZABLE
    )
    public void executeOneAttempt() {
        // read, validate, and write data for one attempt
    }
}
```

This is an **illustrative fragment**, omitting the loop/DAO/imports and not a standalone program. Key idea: `RetryCoordinator` is a non-transactional bean, `TxWorker` is another bean invoked through the **Spring proxy**, and each attempt gets its own transaction. Commit-time exceptions can occur **after the target method returns but before the proxy call returns**; hence the retry coordinator outside the proxy can catch failures from both business execution and commit.

If `RetryCoordinator` called `this.executeOneAttempt()` on the same bean, proxy mode would bypass the inner method's advice and `REQUIRES_NEW` might not apply. Handle self-invocation, injection, and AOP ordering explicitly.

### 5.3. Using Spring Retry / `@Retryable`

An application can use Spring Retry, another retry library, or `RetryTemplate`, though a retry library **does not replace a transaction manager**. Check advisor ordering:

- **Retry advice outside transaction advice:** each attempt enters a new transaction boundary; this is normally the desired setup.
- **Retry advice inside transaction advice:** the entire retry loop may share a single physical transaction already marked rollback-only; that is a broken setup for serialization failures.

Do not rely on default advisor ordering without verifying your version/configuration. You can separate coordinator and transactional worker into two beans as above to make the mechanism explicit, or use `TransactionTemplate` to start a new transaction per attempt.

## 6. Retries must include business condition evaluation

Retrying only the failed SQL statement is insufficient:

```text
WRONG:
  check remaining quantity once
  if sufficient:
      LOOP retry(UPDATE ...)
```

Better:

```text
RIGHT:
  LOOP attempt:
      BEGIN new SERIALIZABLE transaction
      SELECT current data
      re-apply business rules
      recompute decision/update parameters
      UPDATE/INSERT per new decision
      COMMIT
      if 40001 -> roll back/close attempt; backoff; re-run from SELECT
```

Subtle point: even **SQL parameters** chosen in Java can depend on data previously read. If a retry reuses values computed from an old snapshot, retrying the statement can still produce incorrect business results even if the second transaction commits.

Example in a booking system:

- Attempt 1 reads that room A is free and decides to book A.
- Attempt 1 gets `40001` because a concurrent transaction changed the room's status.
- Attempt 2 must re-query room A's status and alternatives; it cannot blindly resend `UPDATE room A` skipping the check.

The same applies to balances, inventory, stock-based pricing, issuing the last ticket, or maximum valid row count rules.

## 7. Standalone runnable Java 17 example: transaction retry at the right boundary

### 7.1. Goal and verification scope

This example uses **Java 17+**, **Spring Framework 6.2.19**, **Spring JDBC**, **H2 in-memory 2.3.232**, and **Maven 3.9+**.

We need a **repeatable test with deterministic output**. Because H2 is not PostgreSQL SSI, the program **intentionally raises a simulated exception with an `SQLException` cause carrying SQLSTATE `40001` on attempt 1**. It verifies:

1. `TransactionTemplate` starts a separate `SERIALIZABLE` transaction for each attempt.
2. SQL executed during attempt 1 **rolls back** when the exception escapes the callback.
3. The retry coordinator **outside** the transaction opens attempt 2 and **re-reads the data**.
4. Attempt 2 commits; final balances are exact and money is not deducted twice.

This tests **the rollback + retry mechanism**, not whether H2 detects a real serialization anomaly or whether PostgreSQL always fails at a specific instant. A real conflict test with PostgreSQL is described in section 3.

### 7.2. Project structure

```text
serializable-retry-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── SerializableRetryDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>serializable-retry-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

In the example, `spring-context` provides Java configuration/IoC, while `spring-jdbc` provides `JdbcTemplate`, `DriverManagerDataSource`, `JdbcTransactionManager`, and the corresponding transaction dependencies. H2 is only needed at runtime.

### 7.3. Complete Java source

File `src/main/java/demo/SerializableRetryDemo.java`:

```java
package demo;

import java.sql.SQLException;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class SerializableRetryDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:serializable_demo;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             SerializableRetryDemo.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            PlatformTransactionManager manager =
                    context.getBean(PlatformTransactionManager.class);

            jdbc.execute("""
                    CREATE TABLE wallet (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update(
                    "INSERT INTO wallet(id, balance) VALUES (1, 100), (2, 50)");

            System.out.println("BEFORE=" + balances(jdbc));

            TransactionTemplate template = new TransactionTemplate(manager);
            template.setIsolationLevel(
                    TransactionDefinition.ISOLATION_SERIALIZABLE);
            template.setPropagationBehavior(
                    TransactionDefinition.PROPAGATION_REQUIRES_NEW);
            template.setTimeout(10);

            transferWithRetry(template, jdbc, 10);

            System.out.println("AFTER=" + balances(jdbc));
        }
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM wallet WHERE id = 2", Integer.class);
        return "A=" + a + ", B=" + b;
    }

    private static void transferWithRetry(
            TransactionTemplate template, JdbcTemplate jdbc, int amount) {

        final int maxAttempts = 3;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            final int current = attempt;

            try {
                template.executeWithoutResult(status -> {
                    System.out.println("ATTEMPT=" + current);

                    // Decision must be recomputed in EACH transaction.
                    int source = jdbc.queryForObject(
                            "SELECT balance FROM wallet WHERE id = 1",
                            Integer.class);

                    if (source < amount) {
                        throw new IllegalStateException(
                                "insufficient balance");
                    }

                    jdbc.update(
                            "UPDATE wallet SET balance = balance - ? "
                            + "WHERE id = 1", amount);

                    if (current == 1) {
                        // Synthetic error with SQLSTATE 40001 to test retry.
                        // Not real PostgreSQL concurrency.
                        SQLException sql = new SQLException(
                                "simulated serialization failure", "40001");

                        throw new IllegalStateException(
                                "synthetic transaction abort", sql);
                    }

                    jdbc.update(
                            "UPDATE wallet SET balance = balance + ? "
                            + "WHERE id = 2", amount);
                });

                System.out.println("COMMITTED_ATTEMPT=" + current);
                return;
            } catch (RuntimeException ex) {
                boolean serialization = hasSqlState(ex, "40001");

                if (!serialization || current == maxAttempts) {
                    throw ex;
                }

                System.out.println("RETRY_40001_AFTER=" + current);
            }
        }
    }

    private static boolean hasSqlState(Throwable failure, String state) {
        for (Throwable current = failure;
                current != null;
                current = current.getCause()) {

            if (current instanceof SQLException sql
                    && state.equals(sql.getSQLState())) {
                return true;
            }
        }
        return false;
    }
}
```

`@Configuration` merely declares beans; the demo uses `TransactionTemplate` **programmatically**, so neither `@EnableTransactionManagement` nor a Spring AOP proxy is required to drive the transaction callback.

### 7.4. Run command

In the `serializable-retry-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.SerializableRetryDemo
```

Lines **printed by the program itself** (excluding Maven/Spring logs):

```text
BEFORE=A=100, B=50
ATTEMPT=1
RETRY_40001_AFTER=1
ATTEMPT=2
COMMITTED_ATTEMPT=2
AFTER=A=90, B=60
```

### 7.5. Reading the output step by step

**Attempt 1:**

- `template.executeWithoutResult` starts a new T1 with requested isolation `SERIALIZABLE`.
- The callback reads balance A=100, confirms 10 units are available, and runs `UPDATE A -= 10`.
- The synthetic exception with cause `SQLException(..., "40001")` escapes the callback.
- `TransactionTemplate` rolls back T1 **before** the coordinator catches the exception.
- The coordinator finds SQLSTATE `40001` in the cause chain and still has retry budget, so it prints `RETRY_40001_AFTER=1`.

**Attempt 2:**

- A new transaction T2 starts; the callback **re-queries** balance A from the DB. Because T1 rolled back, A is still 100.
- No synthetic exception is thrown this time; both `UPDATE A -= 10` and `UPDATE B += 10` execute.
- The callback returns normally and `TransactionTemplate` commits T2; the coordinator prints `COMMITTED_ATTEMPT=2`.

**Final result:** A=90, B=60. If T1 had not rolled back properly, money could have been deducted twice. Thus the example proves both the transaction boundary and the retry mechanism are placed correctly.

`hasSqlState` in the demo is a minimal **cause-chain** scanner; production code may need to check JDBC `SQLException.getNextException()`, JPA/provider exception translation, and classify commit-time errors lacking a direct SQLSTATE cause. Never assume every `IllegalStateException` is retryable: in the example, only errors carrying the specific SQLSTATE are retried.

### 7.6. Why use a synthetic exception?

H2 is not used here as a database generating real SSI conflicts. If you try to run two threads expecting SQLSTATE `40001` on every machine, results can depend on timing and H2's isolation mechanics. Injecting a synthetic error **after the first UPDATE but before the second UPDATE** yields a deterministic test of rollback and retry.

For production PostgreSQL, replace the synthetic exception with **real errors reported by the DB/driver**; integration tests use two concurrent transactions as in section 3. Never leave synthetic failure injection in real business code.

## 8. Production retry policy: bounds, backoff, jitter, deadline

A serious retry loop has at least four bounds:

1. **Maximum attempts:** e.g., 3 or 5, depending on SLO/contention; never an infinite loop.
2. **Total retry duration:** ensure the caller/request still has enough deadline left; a per-transaction timeout **does not mean** the whole retry sequence stays within that limit.
3. **Backoff:** wait progressively longer between attempts so competing transactions do not repeatedly collide at the same instant.
4. **Jitter:** add bounded randomness so many clients do not retry in lockstep.

Java 17 snippet to introduce a delay, used only **after the prior transaction has rolled back/closed**:

```java
long baseMillis = 20L;
long capMillis = 250L;
long maxBackoff = Math.min(capMillis,
        baseMillis << Math.min(attempt - 1, 4));

long pause = java.util.concurrent.ThreadLocalRandom.current()
        .nextLong(maxBackoff + 1);

try {
    Thread.sleep(pause);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException("retry interrupted", ex);
}
```

This is a **fragment**; `attempt` must be a positive attempt number in the outer loop. The formula only illustrates bounded backoff with jitter; depending on system load, use a shared retry policy, metrics, and deadlines instead of copying magic numbers verbatim.

Never call `Thread.sleep` **inside** an open transaction holding connections/locks, as it prolongs contention. Once `40001` is received, finish handling rollback first, then back off and open a new transaction.

### 8.1. Catching commit errors at the right boundary

A serialization failure can surface during SQL in the callback **or at commit time**. If retry logic sits inside a `@Transactional` method and the method returns before the proxy commits, retry code inside the target cannot catch commit failures. Place retries **outside the transaction boundary call**, such as around `TransactionTemplate.execute...` or in a coordinator calling a transactional worker through its proxy.

### 8.2. Do not wrap an entire HTTP request in one long transaction

A request may perform validation, read input, call external services, and only then write to the DB. Only the portion **truly needing a single snapshot and atomic commit** should sit inside the SERIALIZABLE transaction. Keeping transactions short reduces resource hold time, contention, and conflict probability.

If business reads determine SQL parameters, they must live inside the retried transaction. Preparatory steps independent of the snapshot can stay outside.

### 8.3. Retry exhaustion must be reported accurately

Once budget is exhausted, propagate the error or convert it into an explicit failure result; never return "processed successfully" when the last transaction did not commit. The caller can return an HTTP status appropriate to the API contract (e.g., a transient error for clients retrying with an idempotency key) and emit metrics to tune load.

## 9. Idempotency and side effects: prerequisites for safe retries

A DB transaction retry must never cause the user to be:

- Charged multiple times.
- Given duplicate orders from a single request.
- Sent two confirmation emails.
- Calling an external payment API twice.
- Emitting duplicate events to downstream consumers.

### 9.1. Separating side effects from retryable transactions

Recommended pattern:

```text
Retry coordinator
   |
   +--> BEGIN SERIALIZABLE transaction Tn
          |
          +-- check business state
          +-- apply DB changes
          +-- write outbox event in the SAME DB transaction
          |
          +-- COMMIT or ROLLBACK
   |
   +--> only on success allow outbox publisher to send message
```

The outbox record commits together with the business data; if a transaction rolls back with `40001`, that attempt's outbox record disappears too. An out-of-transaction publisher sends after commit, requiring idempotency/at-least-once delivery handling. Putting `@Transactional` around email-sending code does not make an email roll back.

### 9.2. Idempotency keys per request

If a client resends the same request after a network timeout, **the outcome of the earlier commit may be unknown to the client**. Losing a connection during commit is not the same as `40001` meaning the transaction aborted. Thus never blindly retry every connection error assuming the prior transaction definitely did not commit.

Using a `request_id`/idempotency key with a state table/unique constraint in the DB handles receiving the same request again without repeating business effects.

### 9.3. Computed data must be recomputed while request inputs stay stable

There are two groups of data:

- **Fixed request inputs:** request ID, user, requested amount, limits/options approved by the caller.
- **Snapshot-dependent data:** current balance, available inventory, current policy price, allocation sequence, remaining resource availability.

On retry, keep request inputs consistent while **re-reading and recomputing snapshot-dependent data** in the new transaction.

## 10. JDBC/JPA and Spring exceptions: classifying intentionally

### 10.1. JDBC and `JdbcTemplate`

`JdbcTemplate` participates in Spring-managed transactions when using the datasource managed by the transaction manager. A `JdbcTransactionManager` wraps a local JDBC transaction; the JDBC driver provides `SQLException` with SQLSTATE, and Spring exception translation may wrap it into `DataAccessException`.

An error can travel along this chain:

```text
PostgreSQL server
   -> JDBC SQLException(SQLSTATE 40001)
   -> Spring DataAccessException or transaction exception
   -> retry coordinator outside transaction boundary
```

Do not rely solely on catching the older deprecated `CannotSerializeTransactionException` class. For PostgreSQL, SQLSTATE is the key standard signal. Across different providers, verify actual mapping with integration tests; an error thrown at commit may be wrapped differently from one thrown by `JdbcTemplate.update`.

### 10.2. JPA/Hibernate

A `SERIALIZABLE` JPA transaction is truly configured only if `JpaTransactionManager`/provider/backend support controlling isolation for the physical transaction. An annotation on an inner method merely joining an outer transaction may **not** change isolation.

`flush()` is not `commit()`: serialization or constraint errors may surface on flush, or may not appear until commit. Retries must sit **outside** the JPA transaction boundary and recreate an appropriate persistence context/snapshot; never reuse the `EntityManager` of a rolled-back transaction as if it were clean.

### 10.3. Spring Test and auto-rollback transactions

A test class or test method annotated with `@Transactional` may be wrapped by Spring Test's own transaction. A method you believe opens its own `SERIALIZABLE` transaction may then be **joining** the test transaction at a different isolation level.

To test retries genuinely, use a non-transactional caller, a properly configured transaction manager, and two separate connections/threads or sessions; observe commits and DB state outside the transaction boundary rather than merely inspecting metadata inside the method.

## 11. Distinguishing SERIALIZABLE from READ COMMITTED and REPEATABLE READ

| Isolation level | Primary goal | Key caveat |
| --- | --- | --- |
| `READ_COMMITTED` | Each statement sees only committed data matching the statement's snapshot | Between statements newer data can appear; certain read-then-write invariants need locks/version checks |
| `REPEATABLE_READ` | More stable snapshot within a transaction, depending on DB | Does not prevent all write skew on every DB; PostgreSQL `REPEATABLE READ` corresponds to snapshot isolation |
| `SERIALIZABLE` | Committed transactions produce outcomes equivalent to a serial schedule | May abort transactions to prevent serialization anomalies; applications must be ready to retry |

Levels in Java/Spring are **requests to the backend**. Implementation details vary by database vendor; do not turn PostgreSQL SSI specifics into a universal rule for every DBMS.

### 11.1. Is SERIALIZABLE always worth using?

No. SERIALIZABLE is valuable when a business invariant spans reads and writes across multiple records and is hard to protect with a unique constraint, optimistic version, or simple row-level locking. However, it carries conflict-detection overhead, aborts/retries, increased latency under high load, and idempotency complexity.

In many cases `READ_COMMITTED` + atomic SQL (`UPDATE ... WHERE balance >= ?`), unique constraints, or version columns achieve the goal at lower cost. Choose isolation based on **the invariant to protect** and concurrency tests, not a "higher is always better" mindset.

### 11.2. Serializable does not replace constraints

Database `UNIQUE`, `CHECK`, foreign keys, and `WHERE` predicates can enforce concrete invariants more efficiently. Isolation governs interaction between transactions; constraints govern data validity. Critical systems typically need both.

## 12. Common programming mistakes

### Mistake 1 — Retrying the SQL statement instead of the full logic

This is the most dangerous mistake. A repeated `UPDATE` can rely on conditions computed from a stale snapshot. Start a new transaction and re-run `SELECT`, validation, parameter selection, and writes.

### Mistake 2 — Catching `40001` inside a transaction and continuing on the same connection

The database may have already marked the transaction aborted. Running further SQL in the same transaction can trigger "current transaction is aborted" errors or manager rollback-only states. Exit the transaction boundary to roll back/clean up before retrying.

### Mistake 3 — Wrapping the entire retry loop in `@Transactional`

If the retry loop sits inside a method already holding T1, every iteration shares the same physical transaction, snapshot, and rollback-only state. The retry coordinator must sit outside the boundary; use a separate transactional worker or `TransactionTemplate` creating a fresh transaction per attempt.

### Mistake 4 — Self-invocation rendering `REQUIRES_NEW` ineffective

In Spring proxy mode, `this.executeOneAttempt()` bypasses the transaction proxy, so the inner method's annotation fails to create T2 as intended. Move the worker to a separate bean and invoke it via the Spring-managed proxy.

### Mistake 5 — Catching only a single legacy Spring subclass

Exception mapping varies by Spring version, driver, and failure point (query vs. commit). Relying on one deprecated subclass name easily misses cases. For PostgreSQL, inspect SQLSTATE through the cause chain or use an integration-tested error classifier.

### Mistake 6 — Retrying every SQL error, including permanent constraint violations

A permanent unique violation will keep failing; syntax/permission errors do not heal themselves. Only retry errors permitted by an explicit policy for retry-safe business operations.

### Mistake 7 — Unbounded retry count and duration

Under high contention, infinite retry loops amplify system overload. Enforce max attempts, overall deadlines, backoff + jitter, metrics, and explicit error fallbacks.

### Mistake 8 — Keeping a transaction open during backoff

`Thread.sleep()` inside a transaction holds connections/locks/snapshots longer, worsening conflicts. Delays must occur **after rollback or commit failure has been handled** and before starting the new transaction.

### Mistake 9 — Duplicating external side effects

Emails, HTTP calls, published messages, or external charges do not roll back with T1. Separate side effects; use outbox, idempotency keys, and compensation mechanisms.

### Mistake 10 — Assuming all serialization failures happen at UPDATE

Some failures appear **at COMMIT**. If `catch` wraps only an inner repository method inside the transaction, commit-time errors escape unretried. Catch outside `TransactionTemplate.execute...` or outside the proxy call.

### Mistake 11 — Thinking SERIALIZABLE forbids all parallel execution

PostgreSQL SSI generally allows concurrent execution and aborts a transaction when necessary; it does not simply serialize every query behind a global lock. Plan capacity around actual contention and abort rates.

### Mistake 12 — Calling `setRollbackOnly()` and still trusting stale results

`setRollbackOnly()` signals that the transaction did not commit successfully. Data read or objects computed inside a rolled-back scope must never be published as saved results. Retries must re-execute business logic in a fresh transaction.

### Mistake 13 — Suspecting the H2 demo lacks natural `40001` and concluding retry code is useless

The H2 demo uses a synthetic SQLSTATE to **test the retry coordinator and rollback** deterministically. PostgreSQL SSI has its own concurrency algorithm; testing real 40001 requires PostgreSQL and a concurrent schedule as in section 3.

### Mistake 14 — Putting `@Transactional(isolation=SERIALIZABLE)` on a joining method

If outer already opened T1 at another isolation level, inner `REQUIRED` does not upgrade physical isolation. Set isolation at the boundary that starts T1, or separate T2 with `REQUIRES_NEW` when semantically right. Some managers allow `setValidateExistingTransaction(true)` to detect isolation mismatches and reject participation.

### Mistake 15 — Confusing serialization failure with optimistic-lock failure

JPA `OptimisticLockingFailureException`/`OptimisticLockException` from `@Version` is a different concurrency signal. It may have its own retry policy, yet is **not automatically** PostgreSQL SQLSTATE `40001` or a SERIALIZABLE issue. Do not lump both exception families together just because both appear under concurrent updates.

## 13. Production observability and measurement

A retry mechanism built for reliable operations should track:

- Total SERIALIZABLE transactions started, committed, and aborted.
- Counts of `40001` and `40P01`, broken down by operation and endpoint (without putting sensitive data into metric labels).
- Average attempts, retry success rate, and retry-budget exhaustion rate.
- Transaction duration, lock wait time, and DB connection pool saturation.
- Total request latency, including backoff and repeated SQL.
- Idempotency duplicate/suppressed counts, outbox delivery, and client-side retries.
- Throughput and conflict hotspots on involved tables/rows/predicates.

Important note: **never log full SQL exceptions containing sensitive query parameters or personal data** in production logs. Use error codes, trace IDs, and metric labels with bounded cardinality.

### 13.1. Distinguishing a successful retry from a lost commit outcome

`40001` indicates the transaction rolled back due to a serialization failure, making it safe to retry. A network error after sending `COMMIT` can leave the client **uncertain** whether the DB committed. Such "outcome unknown" cases require idempotency/reconciliation; blind retries can create duplicate effects.

### 13.2. Retry storm

If thousands of clients retry immediately after a conflict, the number of contending transactions can surge. Bounded exponential backoff with jitter and rate limiting help spread load. Extreme hotspots should be addressed by redesigning the data model, shortening transaction duration, or partitioning workloads—not just increasing maxAttempts.

## 14. Key test scenarios

1. **Conflict-free path:** a SERIALIZABLE transaction starts, reads and writes, commits; verify data.
2. **Single serialization failure:** inject `40001` after one update; verify the first attempt rolls back and the next attempt commits once.
3. **Commit-time failure:** create a test double or manager/DB integration test raising an exception at `commit`; verify the retry coordinator still catches it.
4. **Attempt exhaustion:** inject `40001` repeatedly; verify the method throws an error, does not report success, and leaves no partial DB writes.
5. **Non-retryable error:** throw `IllegalArgumentException` or a SQL syntax error; verify only one attempt runs.
6. **Data changing between attempts:** modify the DB after a failed attempt; verify the next attempt **re-reads and re-evaluates conditions**.
7. **Real PostgreSQL:** use two sessions like the on-call doctors example; verify `40001` occurs and the invariant holds.
8. **Wrong transaction boundary:** intentionally invoke the worker via `this.method()`/`REQUIRED` joining outer; tests should catch that no new transaction was created as intended.
9. **Outbox/idempotency:** a retried request does not create duplicate business records or send erroneous side effects.
10. **Load:** measure retry success, contention, and latency at production-like concurrent write rates.

Checking `TransactionStatus.isNewTransaction()` alone is not enough to prove real isolation; combine with `Connection.getTransactionIsolation()` checks (for JDBC) and concurrency tests on the actual database. When using Spring Test with test-level `@Transactional`, watch out for the outer test transaction altering propagation of the service under test.

### 14.1. Testing PostgreSQL in the right environment

For real SSI evidence, use the PostgreSQL version deployed by the application, two separate connections, barriers controlling read/write interleaving, and verify SQLSTATE `40001`. Avoid writing race tests relying only on `Thread.sleep` and hoping a specific thread wins; barrier synchronization or a scripted two-session test provides far better reproducibility.

## 15. Frequently asked questions

**Q: `SERIALIZABLE` means no anomalies, so why are exceptions still thrown?**

Because the database must choose between letting an invalid schedule commit and **aborting a transaction** to preserve correctness. The exception is a mechanism enforcing serializability, not a contradiction of that guarantee.

**Q: Is retrying `40001` once enough?**

No. Contention can persist; use a retry budget and backoff. Optimal attempt counts depend on workload and SLOs.

**Q: Must a retry re-read data even if the initial SQL text did not change?**

Yes, if business decisions or query parameters depended on the old snapshot. PostgreSQL recommends retrying **the entire SQL and value decision logic** in a new transaction.

**Q: Can you retry only the failing child repository method?**

Not if the child repository is just one part of a larger transaction. Retries must span the **actual transaction boundary** and all associated decision reads. Only if the repository itself is the entire standalone transactional unit can retries wrap that unit directly.

**Q: Can you catch SQLException and `Thread.sleep` right inside `@Transactional` and try again?**

That is not a safe structure. The transaction may already be marked aborted, sleeping holds resources, and reads reuse the stale snapshot. Exit the boundary, roll back/clean up, then delay and start a new transaction.

**Q: Is `REQUIRES_NEW` required?**

Not strictly, if the retry coordinator genuinely sits outside all transactions and each callback/method starts a new transaction via `REQUIRED`. Using `REQUIRES_NEW` makes per-attempt isolation of transactions explicit, though it carries overhead if ever called from an active outer scope; design to keep outer transactions from enclosing retry loops.

**Q: Is `23505` retryable?**

In some cases involving concurrent key selection after reading the DB, a unique violation can stem from a concurrency race. Yet `23505` can also be a permanent invalid input. Do not retry unconditionally; distinguish by business flow.

**Q: Does the H2 example printing `RETRY_40001_AFTER=1` prove PostgreSQL raises the real error?**

No. The example uses a synthetic `SQLException(SQLSTATE 40001)` to verify rollback and retry. To verify PostgreSQL SSI, run a two-session test against real PostgreSQL.

**Q: Does Serializable guarantee external actions, like sending email, roll back?**

No. Isolation applies only to transactional resources coordinated by the manager. External side effects require outbox/idempotency/compensation.

**Q: In reactive R2DBC, can you use the same `TransactionTemplate` code?**

No. `TransactionTemplate` is an imperative API. Reactive execution requires `ReactiveTransactionManager` and `TransactionalOperator` using the Reactor Context, with resubscription/retry placed outside the reactive transaction boundary; never mix thread-local JDBC contexts with reactive pipelines.

## 16. Checklist for applying to a Spring project

Before enabling SERIALIZABLE for an operation:

- Identify which invariant needs protection and why weaker isolation, constraints, atomic SQL, or optimistic locks are not enough.
- Verify the right **Spring transaction manager**, datasource/persistence unit, and backend isolation support.
- Confirm the method is intercepted by AOP advice and serves as **the boundary starting a new physical transaction**; avoid inner `REQUIRED` joining an outer transaction with different isolation.
- Place all related SQL reads and business decisions **inside** the retried scope.
- Build the retry coordinator **outside the transaction**, so each attempt gets its own begin/commit/rollback.
- Detect `40001` (and other policy-approved codes) reliably; never retry every exception.
- Catch exceptions raised at **COMMIT**, not only on JDBC statement execution.
- Enforce max attempts, overall deadline, bounded backoff + jitter, and interrupt/cancellation handling.
- Do not send emails/HTTP/messages directly inside a retryable block; consider an outbox.
- Use request IDs / idempotency keys to handle client retries and "commit outcome unknown."
- Test against real PostgreSQL for `40001` using concurrent schedules/barriers; synthetic H2 tests only check retry orchestration.
- Measure retry/abort rates and pool/latency impact; revisit isolation or data design if contention is too high.

**Remember:** `SERIALIZABLE` does not promise *every transaction commits*; it promises *committed transactions never form a non-serializable schedule*. When the DB returns a serialization failure, **close the old transaction, start a new transaction, and re-run the entire read–decide–write logic**; bound retries, avoid duplicate side effects, and verify against the real DB.

## Official documentation and deep references

- [PostgreSQL — Serialization Failure Handling (SQLSTATE 40001, retry entire transaction)](https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html)
- [PostgreSQL — Transaction Isolation (Serializable Snapshot Isolation)](https://www.postgresql.org/docs/current/transaction-iso.html)
- [PostgreSQL — SQLSTATE Error Codes](https://www.postgresql.org/docs/current/errcodes-appendix.html)
- [Spring Framework 6.2 — Declarative Transaction Management, `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 — Programmatic Transaction Management, `TransactionTemplate`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
- [Spring Framework — JDBC Exception Translation](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html)
- [Spring DAO — `CannotSerializeTransactionException` (deprecated)](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/CannotSerializeTransactionException.html)