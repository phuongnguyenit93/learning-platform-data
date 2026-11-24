# Lost update, write skew, and multi-row invariants in Spring transaction management

## 1. Why is @Transactional alone not enough to guarantee business correctness under concurrency?

**@Transactional** helps Spring create commit/rollback boundaries for a group of operations on a managed resource. However, two requests can run **within valid transactions**, each committing successfully, yet produce a result that **violates a business invariant** because both made decisions on stale data.

Two failure patterns to distinguish:

- **Lost update:** two transactions read the same value, each computes a new value based on what it read, and the later write **overwrites the result** of the earlier write. For example, two users each add 10 to a balance of 100, yet the final value is only 110 instead of 120.
- **Write skew:** two transactions read **a condition spanning multiple records**, then update **different records**. Because they do not touch the same row to trigger a direct write conflict, both can commit while **breaking the shared invariant**. For example, a shift must always have at least one doctor on call, yet two doctors request leave at the same time, leaving nobody on call.

Both phenomena are **read–decide–write races**: the decision is derived from a snapshot that is no longer consistent with the full commit history. Yet the solutions differ. Locking or versioning a single row is usually enough to prevent a lost update on that row; write skew additionally requires protecting the **predicate / set of rows / cross-record invariant**.

This lesson belongs to the **Isolation levels** group in Spring Framework transaction management. We will trace execution schedules over time, compare isolation levels, write a Java 17+ example with Spring JDBC and PostgreSQL, and build an appropriate strategy of locks, versions, constraints, and retries. Never infer from the mere presence of @Transactional that all business logic is consistent.

### After this lesson, you should be able to

1. Distinguish dirty read, nonrepeatable read, phantom, lost update, and write skew without conflating concepts.
2. Pinpoint **which transaction reads what, decides what, writes which row, and commits when**.
3. Explain why READ_COMMITTED allows read–compute–write lost updates and why PostgreSQL REPEATABLE_READ can still allow write skew.
4. Understand how multi-row invariants differ from per-row CHECK constraints.
5. Choose among: atomic UPDATE, optimistic locking, SELECT FOR UPDATE, shared guard row, SERIALIZABLE, and full-transaction retry.
6. Place isolation at the appropriate Spring transaction boundary, keeping in mind that REQUIRED joins an outer transaction.
7. Verify results with two concurrent connections/transactions rather than a sequential unit test.

## 2. Three foundational concepts: atomicity, isolation, and invariant

**Atomicity** means "either all changes belonging to *one transaction* are committed, or none of the changes belonging to that transaction are committed." **Isolation** defines how concurrent transactions can observe and affect one another. A **business invariant** is a condition that any valid database state must satisfy, even after two actors act concurrently.

Example in an account system:

- Row invariant: balance >= 0 for each account.
- Cross-row invariant: the sum of a group of accounts after internal transfers remains unchanged.
- Cross-table invariant: every confirmed booking must have a valid reservation.
- Predicate invariant: a team must have at least one member currently on call.

Two transactions can **each be atomic** and still break an invariant when they read data concurrently and make decisions without sufficient isolation/locking protection. Therefore, "Spring committed both transactions" does not mean "every invariant holds."

### What is an interleaving?

Name two transactions **T1** and **T2**. Each transaction contains a sequence of read and write operations. When running concurrently, their operations can interleave:

~~~text
T1: READ X -> compute -> WRITE X -> COMMIT
T2:     READ X -> compute -----> WRITE X -> COMMIT
~~~

To analyze an anomaly, write down **the actual value each transaction observes** rather than just writing "T1 runs before T2." For an MVCC DBMS, both the time a snapshot is taken and the time a write lock is acquired matter.

**Serializable** means the outcome of committed transactions must be equivalent to **some serial execution order**, not necessarily that SQL statements on the server literally execute one after another. PostgreSQL implements Serializable Snapshot Isolation (SSI), which may **abort a transaction with serialization_failure** to prevent non-serializable execution schedules. The application needs to know how to retry.

## 3. Lost update: when two increments leave only one

### 3.1. Read–compute–write scenario

Suppose counter.amount = 100. Two independent requests both want to add 10:

~~~text
Time            T1                                  T2
-------------------------------------------------------------------
t1              SELECT amount -> 100
t2                                                  SELECT amount -> 100
t3              Compute newValue = 110
t4                                                  Compute newValue = 110
t5              UPDATE counter SET amount=110
t6              COMMIT
t7                                                  UPDATE counter SET amount=110
t8                                                  COMMIT

Final value = 110 (wrong); should be 120.
~~~

Both T1 and T2 can commit normally at **PostgreSQL READ COMMITTED**. At t7, T2's UPDATE may have to wait for T1's lock, but **the parameter 110 was already computed by the application from the stale read**. Waiting on the lock does not magically turn 110 into 120.

This is a lost update **caused by the application supplying a new absolute value**:

~~~java
// Illustrative snippet; two requests can both read 100.
int balance = jdbc.queryForObject(
        "SELECT amount FROM counter WHERE id = 1", Integer.class);
int newValue = balance + 10;
jdbc.update("UPDATE counter SET amount = ? WHERE id = 1", newValue);
~~~

If another request updated the row between SELECT and UPDATE, the UPDATE above can still overwrite the committed change without the code knowing.

### 3.2. Not every concurrent UPDATE is a lost update

Replace it with an **atomic database-side read–modify–write** SQL statement:

~~~sql
UPDATE counter
SET amount = amount + 10
WHERE id = 1;
~~~

In PostgreSQL READ COMMITTED, two UPDATEs on the same row are coordinated by the DBMS through row locking, applying the addition to the appropriate row version. If both succeed and commit, 100 -> 110 -> 120. This differs from passing a precomputed constant newValue=110 from Java.

**Limitation:** an atomic UPDATE solves single-row addition, but **does not automatically solve invariants that require reading multiple rows and then updating two different rows**. Do not conclude that converting every UPDATE to an arithmetic expression eliminates write skew.

### 3.3. Other ways to protect a single row

- **Pessimistic row lock:** read using SELECT ... FOR UPDATE **inside the same transaction**, then compute and write; competing writers on the same row serialize on the lock.
- **Optimistic locking/version:** read along with a version; when writing, use WHERE version = the read value; if updateCount = 0 there is a conflict—do not silently treat it as committed.
- **Stronger isolation:** on PostgreSQL, REPEATABLE READ/Serializable can reject a transaction when a concurrent update of the same row is detected; **you must retry** if the request should complete.
- **Conditional UPDATE:** for a non-negative balance, a single statement can combine the check and update: UPDATE ... SET balance=balance-? WHERE id=? AND balance>=?, then check the affected row count.

Optimistic version example:

~~~java
// Snippet: amount and version were previously read from one row.
int updated = jdbc.update(
        "UPDATE counter SET amount = ?, version = version + 1 " +
        "WHERE id = ? AND version = ?",
        proposedAmount, counterId, oldVersion);
if (updated != 1) {
    throw new org.springframework.dao.OptimisticLockingFailureException(
            "Counter has changed; retry the whole operation");
}
~~~

This is a snippet, not a standalone Java file; the variables proposedAmount, counterId, and oldVersion must exist. In JPA, @Version provides a similar optimistic versioning mechanism for managed entities. **Per-entity versioning does not automatically prevent write skew across multiple entities**: two requests can update two different rows with no direct version conflict.

## 4. Write skew: invariant holds in each snapshot but breaks after both commit

### 4.1. Two on-call doctors example

Table doctors:

| id | name | on_call |
| --- | --- | --- |
| 1 | An | true |
| 2 | Binh | true |

**Business invariant:** in every committed state, there must remain **at least one doctor with on_call = true**.

Each doctor's request: "I can leave duty if there are currently at least two doctors on call." Two concurrent requests:

~~~text
Time           T1 (doctor An)                  T2 (doctor Binh)
--------------------------------------------------------------------
t1             SELECT COUNT(on_call) -> 2
t2                                             SELECT COUNT(on_call) -> 2
t3             If >= 2, let An leave
t4                                             If >= 2, let Binh leave
t5             UPDATE doctors SET false
               WHERE id=1
t6                                             UPDATE doctors SET false
                                               WHERE id=2
t7             COMMIT
t8                                             COMMIT

Final state: An=false, Binh=false -> COUNT(on_call)=0.
Invariant >= 1 has been violated.
~~~

**Distinguishing trait:** T1 writes **row 1**, T2 writes **row 2**; the two write sets do not touch the same row. When each transaction checks COUNT, it reads a snapshot where both are still on call. Consequently, even separate optimistic versions on row 1 and row 2 can **both update successfully** without reporting any conflict.

### 4.2. Why does REPEATABLE READ not necessarily prevent it?

In **PostgreSQL**, REPEATABLE READ uses **transaction-level snapshot isolation**. It prevents nonrepeatable reads via the snapshot and detects certain concurrent updates on the same row. Yet write skew **can still happen** because two transactions read the same predicate and write different rows; there is no same-row write conflict forcing one side to fail.

~~~text
T1's snapshot: [An=true, Binh=true] -> COUNT=2
T2's snapshot: [An=true, Binh=true] -> COUNT=2

T1 only writes An=false.
T2 only writes Binh=false.

Each transaction sees a valid result based on its own snapshot.
Combined state after both commits: nobody is on call.
~~~

**Serializable** in PostgreSQL detects dependency cycles that make the execution schedule non-equivalent to any valid serial order. Typically **one transaction is rolled back with SQLSTATE 40001** while the other commits; if the losing transaction is retried in full, the new read sees only one doctor left on call and refuses to let the last doctor leave.

Do not assert that every DBMS implements REPEATABLE READ like PostgreSQL. MySQL/InnoDB, Oracle, SQL Server, and other databases differ in MVCC, locking, snapshots, and corresponding level semantics. When writing software that requires correctness, verify against the **actual engine/version/isolation**.

### 4.3. How write skew differs from lost update and phantom

| Phenomenon | Focus | Example |
| --- | --- | --- |
| **Lost update** | Two writes affect the same value and one change is overwritten | Two actors read 100 and both UPDATE amount=110 |
| **Write skew** | Two transactions read a shared condition then write different rows, breaking an invariant | Two doctors simultaneously set their own on_call to false |
| **Nonrepeatable read** | The same transaction re-reads *the same row* and sees a new committed value | T1 SELECTs balance=100 then SELECTs again and sees 90 |
| **Phantom read** | The same transaction re-runs a predicate query and sees the set of rows change | T1 COUNTs bookings then T1 COUNTs again and sees a new row from T2 |
| **Dirty read** | Reading uncommitted data from another transaction | T1 sees T2's uncommitted value, then T2 rolls back |

Write skew does not require a query to be run twice; each transaction **only needs to read once** and then write based on that snapshot. Therefore, a test that merely verifies "re-reading inside the same transaction does not change" is not enough to protect multi-row invariants.

## 5. Isolation levels: must be understood per specific DBMS

Four standard JDBC/Spring names:

- READ_UNCOMMITTED
- READ_COMMITTED
- REPEATABLE_READ
- SERIALIZABLE

In addition, Spring provides Isolation.DEFAULT to use the datasource/database default. The table below describes **modern PostgreSQL** (do not turn it into a universal rule for every engine):

| Isolation | PostgreSQL snapshot/property | Application read-then-set lost update | Two-doctor write skew |
| --- | --- | --- | --- |
| READ UNCOMMITTED | PostgreSQL treats it as READ COMMITTED | Possible | Possible |
| READ COMMITTED | Per-statement snapshot; does not read uncommitted data | Possible when writing stale values computed in Java | Possible |
| REPEATABLE READ | Transaction-consistent snapshot; detects concurrent updates on the same row | Concurrent same-row updates are typically rejected with a serialization failure instead of losing an update | **Still possible** when updating two different rows |
| SERIALIZABLE | SSI prevents commit schedules not equivalent to serial execution | Does not allow non-serializable commit schedules; may roll back/retry | One transaction is typically aborted when write skew is detected, requiring retry |

**Do not treat "SERIALIZABLE" as "locking the entire database."** PostgreSQL uses SSI based on snapshots and dependency tracking, and may return serialization_failure to ask the application to retry. This approach preserves serializability if the relevant transactions are designed and executed at the appropriate level, at the trade-off of rollbacks/retries and monitoring overhead.

**Terminology note:** The original SQL standard primarily described levels in terms of dirty/nonrepeatable/phantom reads. "Write skew" is a specific anomaly under snapshot isolation; the name REPEATABLE_READ by itself does **not** guarantee that all multi-row read invariants are safe.

### Do not conflate propagation with isolation

~~~java
// Snippet in a service, requires Spring bean/proxy and the right manager.
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE)
public void decideDuty() {
    // read invariant, then update rows ...
}
~~~

If the method joins **an existing outer REQUIRED transaction** at READ_COMMITTED, the isolation declared on the inner method **usually does not change** the outer physical transaction. By default, Spring may silently ignore the joining scope's isolation; to detect mismatches, consider validateExistingTransaction=true on AbstractPlatformTransactionManager.

Therefore, place the isolation level at **the boundary that creates the physical transaction** appropriate to the use case, not solely on a child DAO method. Know which transaction manager coordinates the actual JDBC/JPA resource, and remember that a @Transactional method must be invoked through the Spring proxy in proxy mode.

## 6. Two typical invariants: single-row and multi-row

### Invariant A — non-negative balance on one account

One row accounts(id,balance) and the condition balance>=0:

~~~sql
UPDATE accounts
SET balance = balance - 30
WHERE id = 1 AND balance >= 30;
~~~

Check **updateCount==1** to know whether the debit succeeded. This SQL statement both checks the condition and writes under DB row locking, avoiding the scenario where two requests read the balance and independently write new values without coordination.

Combine with **CHECK(balance >= 0)** for a database-level defense on each row. The constraint catches bugs if another code path attempts to write a negative number.

### Invariant B — at least one doctor on call across the team

Condition:
 
~~~sql
SELECT COUNT(*) FROM doctors WHERE on_call = TRUE;
~~~

This is a **multi-row predicate**. A **CHECK(on_call ...)** on each individual row cannot prove someone else still has on_call=true. Ordinary per-row CHECK constraints cannot contain table-wide COUNT(*) logic in PostgreSQL. Hence a broader coordination strategy is required, such as:

- **SERIALIZABLE** and retrying the entire transaction on error 40001.
- **Pessimistic locking:** lock all relevant rows/guard resources up front, then **re-read the condition and update within the same transaction**.
- **Shared guard row:** every action modifying on-call status locks/updates a representative team row; all writers must follow that protocol.
- **Data/invariant redesign:** a "current on-call doctor" record with appropriate unique/foreign-key/constraints when business rules allow, or an atomically updated counter/aggregate with a CHECK constraint.
- **Controlled database logic** such as constraint triggers combined with locking/serializable if all write paths, not just the Java service, must be guarded.

Simply adding **@Version** to the doctor entity being edited does not stop two different doctors from both leaving. Versioning helps if all concurrent transactions update **the same guard row/version** or use an equivalent invariant-level check.

## 7. Java 17+ demo with Spring JDBC and PostgreSQL

This example intentionally uses **PostgreSQL 16** to accurately demonstrate MVCC, REPEATABLE READ, and SSI SERIALIZABLE behavior. H2 is handy for learning CRUD, but its isolation/locking behavior can differ from PostgreSQL; using H2 and claiming facts about PostgreSQL write skew/SSI is a mistake.

Four experiments run two concurrent transactions, synchronized with **CyclicBarrier** to force both workers to complete the read step **before either worker writes**:

1. **Lost update:** READ_COMMITTED, both read amount=100 then UPDATE constant 110, wrong result = 110.
2. **Atomic SQL increment:** READ_COMMITTED, both execute UPDATE amount=amount+10, correct result = 120.
3. **Write skew:** REPEATABLE_READ, both read count=2 then turn off on_call on two separate rows, both commit, final count = 0.
4. **Serializable protection:** SERIALIZABLE, similar schedule, one transaction commits, one gets serialization_failure 40001, final count = 1.

The program uses **TransactionTemplate** instead of @Transactional to create explicit transaction boundaries **in each worker thread** and set isolation directly; it still uses **Spring PlatformTransactionManager and JdbcTransactionManager**, not manual JDBC commits. After the demo we will map it back to @Transactional at the service layer.

### 7.1. Running PostgreSQL for the lesson

The machine needs **JDK 17+**, Maven, and Docker. Create a local PostgreSQL instance for experimentation; do not use this command as a production configuration:

~~~bash
docker run -d --rm --name spring-iso-pg \
  -e POSTGRES_USER=demo \
  -e POSTGRES_PASSWORD=demo \
  -e POSTGRES_DB=demo \
  -p 127.0.0.1:55432:5432 \
  postgres:16
~~~

Run:

~~~bash
docker exec spring-iso-pg pg_isready -U demo -d demo
~~~

Run the program only once the server reports **accepting connections**. If port 55432 is already occupied, choose another local port and update the JDBC URL in code. Do not use example credentials for real systems.

### 7.2. Project structure and Maven

~~~text
isolation-anomalies/
├── pom.xml
└── src/main/java/demo/IsolationAnomalies.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>isolation-anomalies</artifactId>
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
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <version>42.7.4</version>
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
                    <mainClass>demo.IsolationAnomalies</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Versions here are for reproducing the demo environment, not a claim of being the latest. In a Spring Boot application, use the dependency management/BOM matching the Boot version you are deploying.

### 7.3. Complete Java file

**src/main/java/demo/IsolationAnomalies.java**:

~~~java
package demo;

import java.sql.SQLException;
import java.util.List;
import java.util.concurrent.BrokenBarrierException;
import java.util.concurrent.Callable;
import java.util.concurrent.CyclicBarrier;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
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

public final class IsolationAnomalies {
    private IsolationAnomalies() {}

    private static TransactionTemplate template(
            PlatformTransactionManager manager, int isolationLevel) {
        TransactionTemplate tx = new TransactionTemplate(manager);
        tx.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRED);
        tx.setIsolationLevel(isolationLevel);
        tx.setTimeout(20);
        return tx;
    }

    private static void synchronize(CyclicBarrier barrier) {
        try {
            barrier.await(15, TimeUnit.SECONDS);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Worker interrupted", ex);
        } catch (BrokenBarrierException | TimeoutException ex) {
            throw new IllegalStateException("Concurrency barrier failed", ex);
        }
    }

    private static List<String> simultaneously(
            Callable<String> first, Callable<String> second)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> a = pool.submit(first);
            Future<String> b = pool.submit(second);
            return List.of(
                    a.get(30, TimeUnit.SECONDS),
                    b.get(30, TimeUnit.SECONDS));
        } finally {
            pool.shutdownNow();
        }
    }

    private static long committed(List<String> result) {
        return result.stream().filter("COMMIT"::equals).count();
    }

    private static long serializationFailures(List<String> result) {
        return result.stream().filter("40001"::equals).count();
    }

    private static boolean containsSqlState(Throwable throwable, String state) {
        for (Throwable cause = throwable; cause != null; cause = cause.getCause()) {
            if (cause instanceof SQLException sql
                    && state.equals(sql.getSQLState())) {
                return true;
            }
        }
        return false;
    }

    private static int counter(JdbcTemplate jdbc) {
        Integer number = jdbc.queryForObject(
                "SELECT amount FROM counter WHERE id = 1", Integer.class);
        return number.intValue();
    }

    private static int onCall(JdbcTemplate jdbc) {
        Integer number = jdbc.queryForObject(
                "SELECT COUNT(*) FROM doctors WHERE on_call = TRUE",
                Integer.class);
        return number.intValue();
    }

    private static String lostUpdate(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc, CyclicBarrier barrier) {
        TransactionTemplate tx = template(
                manager, TransactionDefinition.ISOLATION_READ_COMMITTED);
        tx.executeWithoutResult(status -> {
            int oldValue = counter(jdbc);
            synchronize(barrier); // Both workers read oldValue=100.
            jdbc.update("UPDATE counter SET amount = ? WHERE id = 1",
                    oldValue + 10);
        });
        return "COMMIT";
    }

    private static String atomicIncrement(
            PlatformTransactionManager manager,
            JdbcTemplate jdbc, CyclicBarrier barrier) {
        TransactionTemplate tx = template(
                manager, TransactionDefinition.ISOLATION_READ_COMMITTED);
        tx.executeWithoutResult(status -> {
            synchronize(barrier);
            jdbc.update("UPDATE counter " +
                    "SET amount = amount + 10 WHERE id = 1");
        });
        return "COMMIT";
    }

    private static String doctorLeaves(
            PlatformTransactionManager manager, JdbcTemplate jdbc,
            CyclicBarrier barrier, int doctorId, int isolationLevel) {
        TransactionTemplate tx = template(manager, isolationLevel);
        try {
            tx.executeWithoutResult(status -> {
                int currentlyOnCall = onCall(jdbc);
                synchronize(barrier); // Both SELECTs complete before UPDATE.
                if (currentlyOnCall >= 2) {
                    jdbc.update(
                            "UPDATE doctors SET on_call = FALSE WHERE id = ?",
                            doctorId);
                }
            });
            return "COMMIT";
        } catch (RuntimeException ex) {
            if (containsSqlState(ex, "40001")) {
                return "40001";  // PostgreSQL serialization_failure
            }
            throw ex; // Do not swallow other errors.
        }
    }

    private static void resetCounter(JdbcTemplate jdbc) {
        jdbc.update("UPDATE counter SET amount = 100 WHERE id = 1");
    }

    private static void resetDoctors(JdbcTemplate jdbc) {
        jdbc.update("UPDATE doctors SET on_call = TRUE");
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            PlatformTransactionManager manager =
                    context.getBean(PlatformTransactionManager.class);

            // Setup completes before running the two workers.
            jdbc.execute("DROP TABLE IF EXISTS doctors");
            jdbc.execute("DROP TABLE IF EXISTS counter");
            jdbc.execute("CREATE TABLE counter (" +
                    "id INT PRIMARY KEY, amount INT NOT NULL)");
            jdbc.execute("CREATE TABLE doctors (" +
                    "id INT PRIMARY KEY, on_call BOOLEAN NOT NULL)");
            jdbc.update(
                    "INSERT INTO counter(id, amount) VALUES (1, 100)");
            jdbc.update(
                    "INSERT INTO doctors(id, on_call) VALUES (1, TRUE)");
            jdbc.update(
                    "INSERT INTO doctors(id, on_call) VALUES (2, TRUE)");

            CyclicBarrier b1 = new CyclicBarrier(2);
            List<String> lost = simultaneously(
                    () -> lostUpdate(manager, jdbc, b1),
                    () -> lostUpdate(manager, jdbc, b1));
            System.out.printf(
                    "lost update READ_COMMITTED: committed=%d, amount=%d%n",
                    committed(lost), counter(jdbc));

            resetCounter(jdbc);
            CyclicBarrier b2 = new CyclicBarrier(2);
            List<String> atomic = simultaneously(
                    () -> atomicIncrement(manager, jdbc, b2),
                    () -> atomicIncrement(manager, jdbc, b2));
            System.out.printf(
                    "atomic SQL READ_COMMITTED: committed=%d, amount=%d%n",
                    committed(atomic), counter(jdbc));

            resetDoctors(jdbc);
            CyclicBarrier b3 = new CyclicBarrier(2);
            List<String> repeatable = simultaneously(
                    () -> doctorLeaves(manager, jdbc, b3, 1,
                            TransactionDefinition.ISOLATION_REPEATABLE_READ),
                    () -> doctorLeaves(manager, jdbc, b3, 2,
                            TransactionDefinition.ISOLATION_REPEATABLE_READ));
            System.out.printf(
                    "write skew REPEATABLE_READ: committed=%d, " +
                    "serializationFailures=%d, onCall=%d%n",
                    committed(repeatable),
                    serializationFailures(repeatable), onCall(jdbc));

            resetDoctors(jdbc);
            CyclicBarrier b4 = new CyclicBarrier(2);
            List<String> serializable = simultaneously(
                    () -> doctorLeaves(manager, jdbc, b4, 1,
                            TransactionDefinition.ISOLATION_SERIALIZABLE),
                    () -> doctorLeaves(manager, jdbc, b4, 2,
                            TransactionDefinition.ISOLATION_SERIALIZABLE));
            System.out.printf(
                    "write skew SERIALIZABLE: committed=%d, " +
                    "serializationFailures=%d, onCall=%d%n",
                    committed(serializable),
                    serializationFailures(serializable), onCall(jdbc));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.postgresql.Driver");
            ds.setUrl("jdbc:postgresql://127.0.0.1:55432/demo");
            ds.setUsername("demo");
            ds.setPassword("demo");
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
    }
}
~~~

### 7.4. Run command and expected stdout

From the **isolation-anomalies** directory:

~~~bash
mvn -q compile exec:java
~~~

When the database is ready and there is no external traffic outside the demo, **the stdout output** of the four experiments on PostgreSQL 16 looks like:

~~~text
lost update READ_COMMITTED: committed=2, amount=110
atomic SQL READ_COMMITTED: committed=2, amount=120
write skew REPEATABLE_READ: committed=2, serializationFailures=0, onCall=0
write skew SERIALIZABLE: committed=1, serializationFailures=1, onCall=1
~~~

The program does not print which worker won because concurrent scheduling does not predetermine whether T1 or T2 will commit in the SERIALIZABLE case. The values **committed=1** and **serializationFailures=1** are what to observe, not which doctor's ID remained on call. In environments with custom database settings or connection issues, the program may halt with an error instead of printing the output above; that is an error to diagnose, not something to interpret as a successful result.

Stop the container when finished:

~~~bash
docker stop spring-iso-pg
~~~

If you are on Windows PowerShell, the Bash-style backslash line continuation in the docker run command is not parsed the same way by PowerShell; put the docker run command on a single line or use PowerShell's line-continuation syntax. This is an example Bash command, not a requirement to use a specific shell.

### 7.5. Why is the example reproducible?

- **Two physical transactions** run on two worker threads, each transaction opened by TransactionTemplate on its own thread.
- **DriverManagerDataSource** opens a connection when requested; because two transactions exist concurrently, they do not share a single JDBC Connection. Production applications should use a properly configured pool.
- **CyclicBarrier** after the SELECT forces both requests to see the initial state before any UPDATE occurs. Does not rely on Thread.sleep() or scheduler luck.
- **READ_COMMITTED + UPDATE amount=?** keeps the constant computed from the old snapshot; both commits lead to a lost update.
- **READ_COMMITTED + UPDATE amount=amount+10** lets the DBMS apply an atomic addition; row locking protects against overwriting with a stale constant.
- **REPEATABLE_READ** creates transaction snapshots for both doctors; because the two writes touch different rows, write skew can still commit.
- **SERIALIZABLE** detects the risk of non-serializability. One transaction may report SQLSTATE **40001** and be rolled back; the other commits.
- **Post-run queries** execute outside the two workers' transactions, so they see the committed state rather than reading one worker's old snapshot.

**Note on timeouts:** CyclicBarrier waits at most 15 seconds, transaction timeout is 20 seconds, and Future.get waits at most 30 seconds. These numbers are **safety bounds for the demo**, not runtime guarantees under load on every machine. If a machine is very slow, a timeout is a signal to inspect the environment rather than arbitrarily changing isolation logic. Do not put barriers waiting on each other into production code while holding DB transactions.

## 8. Using @Transactional instead of TransactionTemplate in real applications

The program above uses TransactionTemplate to make the two threads and isolation configuration explicit; in normal applications, the policy is placed on an application service:

~~~java
// Snippet: requires @Service, imports, Spring AOP transaction infrastructure.
@Service
public class DutyService {
    private final JdbcTemplate jdbc;

    public DutyService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(
            transactionManager = "transactionManager",
            propagation = Propagation.REQUIRED,
            isolation = Isolation.SERIALIZABLE)
    public void leaveDuty(int doctorId) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM doctors WHERE on_call = TRUE",
                Integer.class);
        if (count == null || count < 2) {
            throw new IllegalStateException(
                    "Must keep at least one doctor on call");
        }
        jdbc.update(
                "UPDATE doctors SET on_call = FALSE WHERE id = ?",
                doctorId);
    }
}
~~~

**Not a standalone program**: it requires a Java class file, imports, beans, and the doctors table. Yet it expresses the right boundary: **read invariant + decide + update** sit within the same service transaction at the appropriate isolation level.

In Spring proxy mode, the method must be called from outside **through the Spring-managed proxy**. Calling this.leaveDuty(...) within the same object or instantiating DutyService with new can bypass TransactionInterceptor; the isolation level will not be applied as intended.

### 8.1. Why place isolation on the service, not just the DAO?

A transaction with Propagation.REQUIRED can encompass multiple DAO methods. If the outer service already opened READ_COMMITTED, a child DAO annotated with:

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void updateDoctor(...) {
    // ...
}
~~~

typically **does not upgrade** the running outer transaction. With REQUIRED, the inner scope joins the existing physical transaction, and Spring by default may ignore the inner isolation when joining. Place **SERIALIZABLE at the outer boundary that creates the new transaction**, or use TransactionTemplate where the transaction is opened. You can enable validateExistingTransaction to detect mismatches when appropriate.

### 8.2. When using Spring Data JPA

A service with @Transactional(isolation=Isolation.SERIALIZABLE) using the appropriate JpaTransactionManager and datasource/provider can still protect invariants if the DBMS enforces that isolation and the operations execute within one transaction. However:

- The EntityManager persistence context caches entity state; reading within the same context is no substitute for an independent committed read.
- **save()/flush() does not mean COMMIT**; serialization errors can arise at statement execution or at commit time.
- @Version on **each doctor** does not by itself prevent write skew when each transaction updates a different doctor.
- With bulk SQL/JPQL, optimistic versioning may require special configuration and handling; do not assume every update increments the version.
- Behavior must be tested on the **production database** (not just in-memory H2).

## 9. Addressing write skew beyond SERIALIZABLE

### 9.1. Pessimistic locking of relevant rows

One strategy at READ_COMMITTED is, before COUNT and UPDATE, to **lock all rows that can participate in the invariant** in a consistent order.

~~~sql
BEGIN;
SELECT id, on_call
FROM doctors
WHERE id IN (1, 2)
ORDER BY id
FOR UPDATE;

SELECT COUNT(*)
FROM doctors
WHERE on_call = TRUE;

-- Only if count >= 2, UPDATE the record of the doctor requesting leave.
UPDATE doctors SET on_call = FALSE WHERE id = 1;

COMMIT;
~~~

When **all** competing transactions follow the protocol of locking both rows before checking, one transaction must wait for the other; the later transaction sees the newly committed data under READ_COMMITTED and then **re-checks** the invariant. Note that in PostgreSQL you cannot attach FOR UPDATE directly to an aggregate SELECT COUNT(*) query to lock for the aggregate itself; you must lock the rows first and run COUNT in a separate statement.

**Important conditions:**

- Do not read COUNT first and then acquire locks while keeping the old decision; you must **re-read the predicate after locking**.
- With a dynamic set of doctors, a query locking "existing rows" does not necessarily prevent **phantom inserts/deletes** or every write path that changes the set. You may need to lock **a representative team/shift row (guard row)** that every request locks, or use SERIALIZABLE.
- Consistent lock ordering reduces deadlocks but does not eliminate all risk. Retrying on deadlock 40P01 may still be needed.

### 9.2. Shared guard row for cross-record invariants

For example, add a table duty_team(team_id, active_count, version). Every request for a doctor in the same team to leave duty must:

1. Open a transaction.
2. Lock the corresponding duty_team row or conditionally update **active_count**.
3. Only if active_count >= 2 still holds, update both duty_team and doctors in **the same transaction**.
4. Commit both together; if an error occurs, roll back both.

This forces transactions to conflict on **the same guard row**, giving the database an explicit coordination point. You can add CHECK(active_count >= 1) if the counter is accurately maintained by all write paths/triggers. However, if any writer bypasses the protocol, the counter can drift out of sync with the doctors table; all write paths must be governed in application/DB code and covered by integration tests.

Conditional SQL example:

~~~sql
UPDATE duty_team
SET active_count = active_count - 1
WHERE team_id = 7
  AND active_count >= 2;
~~~

Only if updateCount=1 may the transaction proceed to update the corresponding doctor; if 0, deny the leave request. Both UPDATEs run in the same transaction and roll back together on failure. For each team, writers contend on the guard row rather than only on disjoint doctor rows.

### 9.3. Using unique/exclusion constraints when the invariant allows

An invariant such as "a slot must not have two overlapping ACTIVE bookings" can be expressed with a UNIQUE index or EXCLUDE constraint. DB-level constraints are generally stronger than SELECT-to-check-existence followed by INSERT under READ_COMMITTED. However:

- UNIQUE can prevent **more than one** record matching a condition, not express **at least one** doctor on call.
- A standard row-level CHECK cannot enforce COUNT(*) >= 1 across an entire table.
- Constraint triggers may themselves need locking/serializable to avoid racing between two transactions.
- You must handle database constraint violations as a valid concurrency outcome, not silently catch the error and return success.

### 9.4. SERIALIZABLE + full-transaction retry

PostgreSQL recommends that applications retry **the entire transaction** on SQLSTATE **40001** (serialization_failure). This includes reading state, making the business decision, choosing SQL, and performing writes. Do not merely retry the failed UPDATE statement using stale data.

~~~text
RIGHT:
  attempt 1:
    BEGIN SERIALIZABLE
    SELECT COUNT(on_call) -> 2
    UPDATE doctor 1 -> serialization failure
    ROLLBACK

  attempt 2:
    new BEGIN SERIALIZABLE
    SELECT COUNT(on_call) -> 1
    Deny leaving duty (no UPDATE)
    transaction ends per policy

WRONG:
  after 40001 only re-run UPDATE doctor 1
  without re-reading COUNT/on_call.
~~~

Once a transaction has been aborted by PostgreSQL, do not continue issuing SQL inside that failed transaction. You must exit the boundary so Spring rolls back and cleans up, then start a **new transaction**. When using @Transactional, place the retry loop in **a caller outside the transaction proxy** or use a retry mechanism that guarantees each attempt opens a new transaction; pay attention to AOP advisor ordering if combining @Retryable and @Transactional.

### 9.5. Bounded retries, idempotency, and side effects

A production application should:

- Bound the retry count; use appropriate backoff/jitter under contention.
- Retry SQLSTATE 40001 across the entire use case; consider 40P01 deadlock per policy. Do not unconditionally retry every 23505 unique violation since some reflect permanent data errors.
- Do not send emails, HTTP requests, or messages inside a retryable transaction if the side effect is not idempotent; each retry could **send duplicates**.
- For publishing events, consider a **transactional outbox** in the same DB with a worker dispatching after commit.
- Use an idempotency key at the request boundary if clients can also retry.
- Record metrics for serialization failures, deadlocks, retry counts, and transaction duration to detect contention and overhead.

A skeleton outside the transaction:

~~~java
// Snippet: caller is NOT inside an open transaction.
// dutyService is a Spring bean/proxy with @Transactional(SERIALIZABLE).
for (int attempt = 1; attempt <= 3; attempt++) {
    try {
        dutyService.leaveDuty(doctorId);
        break;
    } catch (org.springframework.dao.ConcurrencyFailureException ex) {
        if (attempt == 3) {
            throw ex;
        }
        // In production: only retry errors classified as transient,
        // especially SQLSTATE 40001, with bounded backoff.
    }
}
~~~

The snippet above **illustrates the retry structure**, not a standalone Java file. ConcurrencyFailureException can cover more errors than 40001, so production code should inspect the cause/SQLSTATE before retrying. For a required operation, do not return success once attempts are exhausted.

## 10. Why is write skew hard to catch with ordinary unit tests?

A unit test calling the service sequentially:

~~~text
Call doctor An leaves:
  COUNT=2, UPDATE An=false, COMMIT

Call doctor Binh leaves:
  COUNT=1, deny, no UPDATE

=> invariant holds.
~~~

This style of testing only proves **a sequential schedule** works. Write skew only surfaces when two requests **both observe count=2 before writing**. Therefore you need tests that create **real concurrent transactions**, using barriers/latches to force interleaving, then reading state after commit.

A good integration test should have:

1. Database initialization in a completed transaction.
2. **Two independent connections/transactions**, not placing both workers inside the same test transaction.
3. Proper isolation configured on the new transactions and verified against the real database.
4. A barrier positioned after READ and before WRITE to simulate the race.
5. Assertions on the number of committed transactions, serialization failures, and **final state**.
6. Runs under READ_COMMITTED, REPEATABLE_READ, and SERIALIZABLE according to the DBMS in use.
7. Tests for full retries and for business validation rejecting operations that are no longer valid.
8. Checks that external side effects are not duplicated on retry.

**If the test class has @Transactional**, Spring TestContext may open a transaction for the test and roll it back at the end; reading data from that same transaction does not prove the workers committed. Separate transaction boundaries and query using an independent connection. Testcontainers or a dedicated PostgreSQL container usually gives results closer to production than H2.

## 11. Direct analysis by Spring configuration

### 11.1. @Transactional does not automatically enforce invariants

The annotation only delegates opening/ending transactions and setting isolation to the manager. It does not inherently know that "one doctor must remain on call." Your SQL and business logic must **actually read and protect the invariant** under suitable isolation/locking.

A @Transactional method with READ_COMMITTED and two SELECT/UPDATE statements can still suffer write skew. Conversely, a single atomic SQL statement can solve a counter lost update efficiently without raising the entire application to Serializable.

### 11.2. Isolation in Spring is a request to the database

When a new JDBC transaction begins, the Spring transaction manager attempts to configure the Connection's isolation to match TransactionDefinition. The DB driver/DBMS determines the concrete behavior. If the database does not support the requested isolation, it may throw an error or apply its own policy; do not treat the Java enum as absolute proof.

**ISOLATION_DEFAULT** uses the datasource/database default. In PostgreSQL, the default is typically READ COMMITTED. Check the session/database configuration, for example:

~~~sql
SHOW default_transaction_isolation;
SHOW transaction_isolation;
~~~

These must be run in the appropriate session/transaction to read the actual value. With a connection pool, per-connection isolation configuration can differ from the database default.

### 11.3. Propagation.REQUIRES_NEW does not replace SERIALIZABLE

REQUIRES_NEW gives the inner call an independent physical transaction with its own commit. It **does not guarantee** that two concurrent REQUIRES_NEW transactions checking a predicate will preserve an invariant. Two independent transactions at READ_COMMITTED or REPEATABLE_READ can still exhibit write skew. Propagation answers "which transaction?", while isolation/locking answers "how do they execute concurrently?".

### 11.4. READ_ONLY does not prevent concurrency anomalies

@Transactional(readOnly=true) is metadata/a hint for the resource manager and ORM/driver; it cannot be used as DB access control or invariant protection. If one method only reads a count with readOnly=true and another method writes in a separate transaction, the gap between the two transactions makes the decision even more likely to go stale. Keep **the READ and WRITE depending on the same decision** within the same boundary.

### 11.5. Multiple DataSources

If an invariant decision reads from DB A but updates DB B, a local JdbcTransactionManager for A does not automatically coordinate B. Caches or read replicas can also serve data lagging behind the primary. For invariants needing ACID guarantees, verify **which source is read**, **which source is written**, **which manager coordinates**, and whether everything actually sits in one transaction or requires a different consistency design.

## 12. Common thinking errors

| Misconception | Why it is wrong | Fix |
| --- | --- | --- |
| Having @Transactional makes lost updates impossible | Transactions can commit while decisions rely on oldValue | Atomic SQL, version check, lock, or appropriate SERIALIZABLE |
| REPEATABLE_READ always protects every invariant | PostgreSQL snapshot isolation still allows write skew | SERIALIZABLE / lock shared guard, test on DBMS |
| Two UPDATEs touch different rows so there is no concurrency issue | Both can read the same predicate and break an invariant | Protect the row set/predicate, not only the written row |
| @Version on each row prevents all write skew | Two transactions edit different rows so versions do not conflict | Shared guard row/version or SERIALIZABLE |
| SELECT FOR UPDATE after COUNT is enough | The decision was already based on a stale count; still wrong | Lock first and re-check inside the transaction |
| SERIALIZABLE means it never throws errors | PostgreSQL can return 40001 to prevent non-serializable outcomes | Retry the entire transaction with a bound |
| Retrying only the UPDATE with the same old parameters is fine | Does not re-evaluate the changed invariant | Retry the full read–decide–write flow |
| A CHECK on the doctor row guarantees one person stays on call | Multi-row invariants are not simple per-row CHECKs | Shared guard / suitable constraint / serializable |
| Isolation placed on a child DAO always takes effect | REQUIRED inner can join an outer transaction with different isolation | Set isolation at the outer boundary creating the physical transaction |
| Passing an H2 unit test means PostgreSQL production is safe | MVCC/locking/SSI differ across engines | Integration test against the actual DBMS |
| Re-reading from the old EntityManager shows the latest commit | Persistence context may cache state | Read from an independent transaction/context after commit |

## 13. Applied questions and answers

**1. Why do two READ_COMMITTED transactions each adding 10 leave the final amount at only 110?**  
Because the code reads 100 and computes the absolute value 110 in both requests, then both UPDATE to 110. The later write does not add a delta; it overwrites the committed value.

**2. How does replacing UPDATE amount=? with UPDATE amount=amount+10 help?**  
The database performs the addition on the row version protected by write locking; two same-row increments in PostgreSQL READ_COMMITTED can produce 120. However, this is no cure-all for multi-row invariants.

**3. Does write skew necessarily update the same row?**  
No. Its hallmark is precisely that two transactions **update different rows** after reading a shared predicate.

**4. Why can PostgreSQL REPEATABLE_READ let both doctors leave?**  
Both transactions read a snapshot showing two doctors on call, and then each writes a different row. Snapshot isolation does not necessarily detect this predicate dependency cycle.

**5. In PostgreSQL SERIALIZABLE, what happens when both request leave together?**  
To guarantee an outcome equivalent to serial execution, PostgreSQL SSI can abort one transaction with 40001 while the other commits. When retried, the aborted request reads the new count and must obey the business rule.

**6. Can you retry only the UPDATE statement after error 40001?**  
No. You must open a new transaction and repeat the entire read/decide/write cycle because the input data for the decision has changed.

**7. Does @Version on entities An and Binh by itself prevent write skew?**  
No, if each transaction updates only a different entity. Both optimistic version checks can succeed; you need a shared coordination point or SERIALIZABLE.

**8. A DAO has @Transactional(isolation=SERIALIZABLE) while the outer service is already in READ_COMMITTED REQUIRED. Does the DAO upgrade isolation?**  
You should not expect it to. Inner REQUIRED typically uses the outer physical transaction; set isolation at the service boundary or validate mismatches.

**9. When using SELECT FOR UPDATE for a group of doctors, do you read COUNT before or after locking?**  
After locking the relevant rows in the same transaction, so the decision relies on state that cannot be concurrently modified by writers following the same locking protocol.

**10. If new doctors can be INSERTed/DELETEd freely, does locking existing rows solve all phantoms?**  
Not automatically. The set of rows can change; you need a shared guard, locks covering all write paths, or SERIALIZABLE with retry.

**11. Does a successfully committed transaction guarantee the invariant always holds?**  
No. Insufficient isolation or code that fails to guard the invariant can leave an invalid concurrent outcome even though both transactions were atomic and committed.

**12. When should you prefer READ_COMMITTED + atomic SQL over SERIALIZABLE?**  
When the problem is a simple single-row update expressible atomically in the DB with no complex cross-row predicate, this choice can reduce conflicts and retries. Still, test the actual business invariant.

## 14. Production checklist for multi-row invariants

- [ ] State the invariant in clear language: for example, "each shift has >=1 doctor on call."
- [ ] List **every write path** that can change the relevant set of rows, including batch jobs, admin SQL, and workers.
- [ ] Distinguish single-row updates from decisions based on multi-row **COUNT/EXISTS/SUM/JOIN**.
- [ ] Verify the actual isolation of new transactions rather than inferring from inner annotations.
- [ ] Choose a provable protocol: atomic SQL, shared lock, SERIALIZABLE, or schema constraint.
- [ ] Ensure the transaction covers **read–decide–write**, avoiding remote calls inside the transaction.
- [ ] Catch and classify SQLSTATE 40001; retry the **entire transaction** with bounds/backoff.
- [ ] Protect non-DB side effects from duplication on retry.
- [ ] Test with **two concurrent transactions**, not only sequential unit tests.
- [ ] Test on the **production DBMS** with the same engine/version/driver/isolation when correctness is critical.
- [ ] Monitor metrics for concurrency conflicts, serialization failures, deadlocks, wait times, and retry counts.
- [ ] Verify the invariant with a query after the transactions have finished.

## 15. Summary

- **Lost update** typically stems from read–calculate–write on the same value without controlling concurrent updates. Atomic SQL, optimistic versioning, row locks, or stronger isolation can address it depending on the case.
- **Write skew** occurs when transactions read a **multi-row** condition and then write different rows. Protecting individual rows is not enough; the shared invariant requires a shared lock/guard/constraint or SERIALIZABLE.
- In **PostgreSQL**, REPEATABLE_READ is snapshot isolation and can still exhibit write skew; SERIALIZABLE uses SSI to prevent non-serializable commit schedules by rolling back one transaction with **40001**.
- **@Transactional** only declares boundaries and isolation; it does not understand business invariants on its own. Place isolation at the **owning transaction boundary** and ensure the Spring proxy/manager/resource are wired properly.
- **Retries must re-run the entire transaction** and all decisions; do not reuse stale parameters and do not repeat non-idempotent side effects.
- **Prove correctness with concurrent integration tests and post-commit DB state** rather than relying on the intuition that "having a transaction makes it safe."

## References

- [PostgreSQL — Transaction Isolation, MVCC and Serializable](https://www.postgresql.org/docs/current/transaction-iso.html)
- [PostgreSQL — Serialization Failure Handling (SQLSTATE 40001)](https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html)
- [PostgreSQL — Data Consistency Checks at the Application Level](https://www.postgresql.org/docs/current/applevel-consistency.html)
- [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html)
- [PostgreSQL — SELECT and FOR UPDATE](https://www.postgresql.org/docs/current/sql-select.html)
- [PostgreSQL — SET TRANSACTION and isolation levels](https://www.postgresql.org/docs/current/sql-set-transaction.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Transaction Propagation / REQUIRED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — TransactionTemplate API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
