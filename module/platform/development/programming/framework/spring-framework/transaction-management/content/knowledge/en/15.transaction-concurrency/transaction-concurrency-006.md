# Deadlocks and Consistent Resource Access Ordering in Spring Transaction Management

## 1. The problem: why do two valid transactions still wait on each other forever?

In a Spring application, each **@Transactional** call may be configured properly and each SQL statement may be valid, yet two concurrently running transactions **hold locks that the other transaction needs**. If the waiting dependencies form **a closed cycle**, that is a **deadlock**.

For example, two requests both updating two accounts A and B:

- T1 locks A, then wants to lock B.
- T2 locks B, then wants to lock A.
- T1 waits for T2 to release B; T2 waits for T1 to release A.
- Neither transaction can make progress on its own to release its lock.

A DBMS like PostgreSQL has a deadlock detector. It selects one transaction as the **victim**, aborts that transaction, and returns an error. The other transaction can proceed, but the victim's business operation **is not automatically retried**. The application must decide whether to retry and, if retrying, must create a new transaction.

**The most important prevention:** when multiple transactions must access the same group of resources, require **every execution path to acquire locks in one consistent global order**. For instance, always process the account with the smaller id first and the larger id second, regardless of transfer direction.

This lesson is part of the **Locking and Concurrency** section of Spring Framework transaction management. The focus is recognizing deadlocks, designing practical lock ordering, working with Spring TransactionManager, reading PostgreSQL errors, retrying safely, and verifying with two concurrent transactions.

### Objectives

After this lesson, you can:

1. Construct a **wait-for graph** and distinguish deadlocks from ordinary lock waits/timeouts.
2. Explain deadlocks caused by row locks, table locks, lock upgrades, SQL/foreign keys/ORM flush.
3. Design a **canonical lock order** by entity type, database key, and lock mode.
4. Apply **SELECT ... FOR UPDATE** and UPDATE in a stable order inside a @Transactional service.
5. Read PostgreSQL **SQLSTATE 40P01** properly and distinguish 40001, 55P03, and 57014.
6. Retry the **entire transaction** outside the transaction boundary with bounds/backoff, without duplicating side effects.
7. Run a Java 17+ Spring JDBC example with PostgreSQL: one execution schedule producing a deadlock and one consistent-order schedule avoiding the wait cycle.
8. Test and monitor deadlocks without relying on Thread.sleep() or reading only application logs.

## 2. What is a deadlock? Distinguishing it from ordinary lock waiting

In a relational database, UPDATE or SELECT ... FOR UPDATE typically acquires locks in the corresponding mode to protect rows from conflicting modifications. Locks are necessary to preserve correctness under concurrency; the problem is not "having locks," but **how multiple transactions acquire and wait on locks**.

A **valid wait** scenario:

~~~text
T1: lock A ----------- UPDATE A -------- COMMIT (releases lock A)
T2:       request lock A - WAIT ---------- gets lock A --- COMMIT

T2 waits for T1, but T1 does not wait for T2 -> no deadlock.
~~~

A **deadlock** scenario:

~~~text
T1: lock A ------------------- request lock B -- WAIT(T2)
T2:      lock B -------------- request lock A -- WAIT(T1)

T1 holds A and waits for B; T2 holds B and waits for A.
T1 can only proceed when T2 finishes; T2 can only proceed when T1 finishes.
=> Wait cycle with no exit without intervention.
~~~

**Wait-for graph:**

~~~mermaid
flowchart LR
    T1["Transaction T1: holds A, needs B"]
    T2["Transaction T2: holds B, needs A"]
    T1 -->|"waits for lock B held by T2"| T2
    T2 -->|"waits for lock A held by T1"| T1
~~~

This is a **cycle**. With three transactions, a deadlock can be T1 waiting for T2, T2 waiting for T3, T3 waiting for T1; it does not have to involve just two parties. In systems with complex lock modes and queues, the wait-for graph can contain more edges than a simple cycle.

### Deadlock, lock contention, timeout, and starvation

| Phenomenon | Nature | Resolution approach |
| --- | --- | --- |
| **Lock contention** | Multiple transactions need the same resource; one waits for the lock holder | Optimize transaction duration, indexes, batches, lock modes, and concurrency |
| **Deadlock** | There is a wait cycle; neither can progress on its own | Consistent lock ordering; DB aborts victim; retry whole transaction when appropriate |
| **Lock timeout** | A lock request waits past the limit; may have no cycle | Identify blocker, reduce lock duration, choose proper timeout and retry policy |
| **Statement timeout** | SQL runs longer than the limit; may be due to locks or a slow query | Analyze plan/locks/IO; do not assume it is a deadlock |
| **Starvation** | One request is repeatedly delayed or unfavorably chosen | Fairness, backoff, load limits, queues, and retry metrics |
| **Optimistic conflict** | Version check/update count shows data changed | Retry logic with fresh data or report conflict to the user |

**Important:** waiting a long time for a lock is **not enough** to conclude a deadlock. Strong evidence is the database returning a specific deadlock error, or a wait graph containing a cycle. Without a wait cycle, the lock-holding transaction can progress and eventually release for the waiter.

## 3. Why doesn't Spring @Transactional eliminate deadlocks automatically?

Spring manages **transaction boundaries**, not the scheduling of every lock inside the DBMS. With imperative JDBC/JPA:

~~~text
Caller
  |
  v
Spring AOP proxy / TransactionInterceptor
  |
  +-- PlatformTransactionManager opens or joins transaction
  |
  +-- Service/repository invokes SQL
  |       |
  |       +-- PostgreSQL grants lock or forces wait
  |       +-- PostgreSQL detects deadlock and aborts victim
  |
  +-- exception escapes -> rollback per policy
  +-- transaction cleanup, release Connection
~~~

Suppose two service methods both have:

~~~java
// Snippet: method must be called through a Spring-managed proxy.
@Transactional
public void transfer(long fromId, long toId, long amount) {
    debit(fromId, amount);
    credit(toId, amount);
}
~~~

If request **A -> B** calls debit(A) then credit(B), while request **B -> A** calls debit(B) then credit(A), the **actual lock acquisition order** can be reversed. A proper outer @Transactional only keeps each transaction atomic; it **does not force two transactions to both pick A before B**.

The JDBC transaction manager helps roll back when an appropriate SQLException escapes the interceptor (Spring DataAccessException is a RuntimeException), but it cannot "guarantee zero deadlocks." **A transaction aborted by PostgreSQL due to a deadlock must be ended and redone in a new transaction** if business rules allow.

### Locks can be acquired implicitly

You do not need SQL LOCK TABLE to hit a deadlock. The following operations can acquire locks:

- Direct UPDATE/DELETE on rows.
- SELECT ... FOR UPDATE / FOR NO KEY UPDATE / FOR SHARE depending on mode.
- INSERT/UPDATE with unique constraints or foreign keys.
- Triggers, cascade deletes/updates, referential integrity checks.
- DDL requiring table-level locks; batch maintenance or migrations.
- JPA/Hibernate flushes, JDBC batches, and index updates.

Therefore, a lock ordering plan must consider the **database resources the SQL actually touches**, not just the order of Java statements in source code.

## 4. Two-account deadlock: inconsistent ordering

Suppose the account table has two rows id=1 and id=2, each with amount=0. Two requests want to update both rows. If each transaction acquires locks in a different order:

~~~text
Time          T1 (id 1 then id 2)                T2 (id 2 then id 1)
-----------------------------------------------------------------------
t1            BEGIN
t2                                               BEGIN
t3            UPDATE account WHERE id=1          (T1 locks row 1)
t4                                               UPDATE account WHERE id=2
                                                 (T2 locks row 2)
t5            UPDATE account WHERE id=2          (T1 waits for row 2)
t6                                               UPDATE account WHERE id=1
                                                 (T2 waits for row 1)
t7            PostgreSQL detects cycle
t8            One transaction is aborted with 40P01
t9            The remaining transaction can finish and COMMIT
~~~

The post-error outcome depends on which transaction was chosen as victim and each side's business operation. Never design around the assumption **"T2 is always the victim because it arrived later"**; PostgreSQL may choose either side to break the cycle.

### Illustrative SQL example with two psql sessions

**Session 1:**

~~~sql
BEGIN;
UPDATE account SET amount = amount + 1 WHERE id = 1;
-- Pause here so session 2 locks id=2.
UPDATE account SET amount = amount + 1 WHERE id = 2;
COMMIT;
~~~

**Session 2:**

~~~sql
BEGIN;
UPDATE account SET amount = amount + 1 WHERE id = 2;
-- Pause here so session 1 locks id=1.
UPDATE account SET amount = amount + 1 WHERE id = 1;
COMMIT;
~~~

The "pause here" comments are manual step instructions, not SQL commands. Running both scripts sequentially from start to finish will usually **not deadlock**. You must interleave right after the first two UPDATEs. In PostgreSQL, once a transaction receives error 40P01, that transaction is already in an aborted state; do not proceed to COMMIT as if everything succeeded.

## 5. How does consistent access ordering break the wait cycle?

Choose a **total order** for the resources a transaction must lock. With two accounts:

~~~text
Rule: always lock the account with the smaller ID first, larger ID second.

T1 wants to process A=1 and B=2:
  lock row 1 -> lock row 2 -> modify -> commit

T2 wants to process B=2 and A=1:
  lock row 1 -> lock row 2 -> modify -> commit

If T1 is holding row 1, T2 waits on row 1.
T1 does not need to request a lock already held by T2 earlier.
=> No wait cycle is formed between these two rows under this protocol.
~~~

Crucial point: **lock order does not depend on business role** such as "source account," "destination account," "debit," or "credit." It depends on a stable key like **account_id**. After acquiring all required locks, the code applies the transfer in the proper business direction.

If every transaction acquires locks strictly in ascending order of the same global key, wait cycles over that lock set are generally eliminated: supposing a cycle existed, each transaction would have to wait for a lock greater than the one it already holds, whereas a closed cycle requires returning to a smaller lock, contradicting the order. That is why choosing a **shared order across all write paths** is so effective.

### Canonical order across multiple resource types

When code accesses multiple tables/entities, a convention might be:

1. Choose a resource class order: e.g., tenant_guard before account, account before ledger_entry.
2. Within the same class, choose a stable identifier key: tenantId, accountId, orderId...
3. Sort before locking; use the same comparator across all services/workers.
4. When a stronger lock mode will be needed later, consider acquiring the **needed mode upfront** to avoid conversion/upgrade deadlocks.
5. Maintain the same order in bulk operations, background jobs, schedulers, admin tools, and migrations.
6. Check indirect locks from indexes, foreign keys, triggers, cascades, or ORM flushes.

**Sorting a list in Java does not mean zero deadlocks unconditionally.** The SQL optimizer may alter actual access order in bulk SQL, the ORM may flush in a different order, and triggers/foreign keys can take locks outside the list. Conventions must reflect **actual lock acquisition order**, verified via integration tests and SQL/DB logs.

### Locking multiple rows in a controllable way

In PostgreSQL, when you have exactly two ids to lock, a clear approach for this lesson is **two sequential SELECT FOR UPDATE statements**, by sorted id:

~~~sql
BEGIN;

SELECT id FROM account WHERE id = 1 FOR UPDATE;
SELECT id FROM account WHERE id = 2 FOR UPDATE;

-- Both rows are locked in a stable order.
-- Apply debit/credit inside the same transaction.

COMMIT;
~~~

For two requests handling (2,1), both still run SELECT id=1 before id=2. SELECT FOR UPDATE holds row locks until the transaction ends (barring specific savepoint rollback cases). If an id does not exist, SELECT returns no row to lock; code must handle the **missing resource** rather than assuming a guard lock was acquired.

A single **SELECT ... WHERE id IN (...) ORDER BY id FOR UPDATE** is sometimes used to lock a set of rows. For workflows demanding strict ordering, do not assume every query plan/batching/ORM grants locks strictly in the Java list's order; verify the DBMS and SQL plan. Locking rows sequentially by canonical key is easy to verify in small-row examples.

## 6. Distinguishing lock order from business update order

Suppose transferring money from account 20 to account 10:

- **Lock order:** 10 first, 20 second.
- **Business logic:** debit from 20, credit to 10.
- **Physical row writes:** can execute after all locks are held.

Never do "smaller id always debits" — that is **wrong business logic**. Sorting is solely for **synchronizing resources**, while debit/credit follows `fromId`/`toId`. Spring JDBC example:

~~~java
// Snippet inside a @Transactional service invoked through a Spring proxy.
long first = Math.min(fromId, toId);
long second = Math.max(fromId, toId);

jdbc.queryForObject(
        "SELECT id FROM account WHERE id = ? FOR UPDATE",
        Long.class, first);
jdbc.queryForObject(
        "SELECT id FROM account WHERE id = ? FOR UPDATE",
        Long.class, second);

// After holding all locks, perform operations in the true transfer direction.
int debited = jdbc.update(
        "UPDATE account SET balance = balance - ? " +
        "WHERE id = ? AND balance >= ?",
        amount, fromId, amount);
int credited = jdbc.update(
        "UPDATE account SET balance = balance + ? WHERE id = ?",
        amount, toId);
if (debited != 1 || credited != 1) {
    throw new IllegalStateException("Invalid transfer");
}
~~~

The snippet above is **not a standalone Java file**; it needs imports, `JdbcTemplate`, `fromId`/`toId`/`amount`, and transaction configuration. Real applications must handle `fromId==toId`, invalid amounts, missing rows, overflow, constraints, and request idempotency.

With Spring JDBC, `JdbcTemplate` uses the transaction-bound Connection when sharing the same DataSource and TransactionManager; **do not open a separate connection** inside a repository to run UPDATE after the service locked rows. If SQL goes over a different connection, those two SELECT FOR UPDATE statements no longer protect the operation as intended.

## 7. Java 17+ demo with Spring JDBC/PostgreSQL: inducing a deadlock, then avoiding it

The example uses **PostgreSQL 16**, **Spring Framework 6.2.12**, and **PostgreSQL JDBC driver 42.7.4**. We create **two concurrent physical transactions** using Spring **TransactionTemplate** (PlatformTransactionManager), synchronized with **CyclicBarrier**. The lesson does not use `Thread.sleep()` hoping a race appears by chance.

Two rounds:

- **Round 1 — opposite order:** T1 UPDATEs id=1 then id=2; T2 UPDATEs id=2 then id=1. The barrier ensures both workers locked their first row before contending for the second row → creating a wait cycle. PostgreSQL aborts one transaction with 40P01; the other commits both UPDATEs.
- **Round 2 — consistent order:** both workers UPDATE id=1 then id=2; the barrier sits **before acquiring the first lock**, not between the two locks. One worker may wait on the other's row 1, but no cycle forms between these two rows. Both transactions finish in turn.

Each UPDATE increments `amount` by 1. Starting with row1=row2=0; expected results are 1/1 in round 1 because only one transaction commits, and 2/2 in round 2 because both commit.

### 7.1. Starting local PostgreSQL for the experiment

The machine needs Java 17+, Maven, and Docker. The following command uses data/credentials **only for this local lesson**:

~~~bash
docker run -d --rm --name spring-deadlock-pg \
  -e POSTGRES_USER=demo \
  -e POSTGRES_PASSWORD=demo \
  -e POSTGRES_DB=demo \
  -p 127.0.0.1:55432:5432 \
  postgres:16
~~~

Check readiness:

~~~bash
docker exec spring-deadlock-pg pg_isready -U demo -d demo
~~~

Proceed once PostgreSQL reports **accepting connections**. Do not use example passwords for real databases; if the port is busy, change both the Docker port and the JDBC URL below. On Windows PowerShell, run `docker run` on a single line or use PowerShell line continuation instead of Bash backslashes.

### 7.2. Project structure

~~~text
spring-deadlock-demo/
├── pom.xml
└── src/main/java/demo/SpringDeadlockDemo.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-deadlock-demo</artifactId>
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
                    <mainClass>demo.SpringDeadlockDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Versions are pinned to give the demo a clear environment, not necessarily the latest releases. In Spring Boot applications, let the Spring Boot BOM manage dependency versions compatible with the current Boot release.

### 7.3. Complete Java main

**src/main/java/demo/SpringDeadlockDemo.java**:

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

public final class SpringDeadlockDemo {
    private SpringDeadlockDemo() {}

    private static TransactionTemplate transaction(
            PlatformTransactionManager manager) {
        TransactionTemplate template = new TransactionTemplate(manager);
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);
        template.setIsolationLevel(
                TransactionDefinition.ISOLATION_READ_COMMITTED);
        template.setTimeout(20);
        return template;
    }

    private static void awaitBoth(CyclicBarrier barrier) {
        try {
            barrier.await(15, TimeUnit.SECONDS);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", ex);
        } catch (BrokenBarrierException | TimeoutException ex) {
            throw new IllegalStateException("Barrier timed out", ex);
        }
    }

    private static boolean hasSqlState(Throwable error, String expected) {
        for (Throwable cause = error; cause != null; cause = cause.getCause()) {
            if (cause instanceof SQLException sql &&
                    expected.equals(sql.getSQLState())) {
                return true;
            }
        }
        return false;
    }

    private static void increment(JdbcTemplate jdbc, int id) {
        int updated = jdbc.update(
                "UPDATE demo_account SET amount = amount + 1 WHERE id = ?",
                id);
        if (updated != 1) {
            throw new IllegalStateException("Account row missing: " + id);
        }
    }

    // Both workers lock two rows in opposite order and then request the remaining row.
    private static String oppositeOrder(
            PlatformTransactionManager manager, JdbcTemplate jdbc,
            CyclicBarrier barrier, int firstId, int secondId) {
        TransactionTemplate tx = transaction(manager);
        try {
            tx.executeWithoutResult(status -> {
                increment(jdbc, firstId);
                // Both already hold their first row before requesting the second row.
                awaitBoth(barrier);
                increment(jdbc, secondId);
            });
            return "COMMIT";
        } catch (RuntimeException ex) {
            if (hasSqlState(ex, "40P01")) {
                return "40P01";
            }
            throw ex;
        }
    }

    // Both workers always lock in row 1 -> row 2 order.
    private static String consistentOrder(
            PlatformTransactionManager manager, JdbcTemplate jdbc,
            CyclicBarrier startBarrier) {
        TransactionTemplate tx = transaction(manager);
        try {
            tx.executeWithoutResult(status -> {
                // Synchronize before acquiring locks, NOT holding between them.
                awaitBoth(startBarrier);
                increment(jdbc, 1);
                increment(jdbc, 2);
            });
            return "COMMIT";
        } catch (RuntimeException ex) {
            if (hasSqlState(ex, "40P01")) {
                return "40P01";
            }
            throw ex;
        }
    }

    private static List<String> runBoth(
            Callable<String> left, Callable<String> right)
            throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> first = pool.submit(left);
            Future<String> second = pool.submit(right);
            return List.of(
                    first.get(30, TimeUnit.SECONDS),
                    second.get(30, TimeUnit.SECONDS));
        } finally {
            pool.shutdownNow();
        }
    }

    private static long count(List<String> results, String value) {
        return results.stream().filter(value::equals).count();
    }

    private static int amount(JdbcTemplate jdbc, int id) {
        Integer value = jdbc.queryForObject(
                "SELECT amount FROM demo_account WHERE id = ?",
                Integer.class, id);
        if (value == null) {
            throw new IllegalStateException("Row missing: " + id);
        }
        return value;
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            PlatformTransactionManager manager =
                    context.getBean(PlatformTransactionManager.class);

            jdbc.execute("DROP TABLE IF EXISTS demo_account");
            jdbc.execute("CREATE TABLE demo_account (" +
                    "id INT PRIMARY KEY, amount INT NOT NULL)");
            jdbc.update("INSERT INTO demo_account(id, amount) VALUES (1, 0)");
            jdbc.update("INSERT INTO demo_account(id, amount) VALUES (2, 0)");

            CyclicBarrier oppositeBarrier = new CyclicBarrier(2);
            List<String> opposite = runBoth(
                    () -> oppositeOrder(
                            manager, jdbc, oppositeBarrier, 1, 2),
                    () -> oppositeOrder(
                            manager, jdbc, oppositeBarrier, 2, 1));
            System.out.printf(
                    "opposite order: commits=%d, deadlocks=%d, " +
                    "row1=%d, row2=%d%n",
                    count(opposite, "COMMIT"), count(opposite, "40P01"),
                    amount(jdbc, 1), amount(jdbc, 2));

            // Reset runs after both transactions have finished.
            jdbc.update("UPDATE demo_account SET amount = 0");

            CyclicBarrier orderedStart = new CyclicBarrier(2);
            List<String> ordered = runBoth(
                    () -> consistentOrder(manager, jdbc, orderedStart),
                    () -> consistentOrder(manager, jdbc, orderedStart));
            System.out.printf(
                    "consistent order: commits=%d, deadlocks=%d, " +
                    "row1=%d, row2=%d%n",
                    count(ordered, "COMMIT"), count(ordered, "40P01"),
                    amount(jdbc, 1), amount(jdbc, 2));
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
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }
    }
}
~~~

**Why not use @Transactional directly inside main?** Main creates two Callables and runs them on **two worker threads**. TransactionTemplate opens a proper Spring-managed transaction directly inside each worker. In applications, usually use `@Transactional` on **public service methods called through a Spring proxy**; `JdbcTransactionManager` and database semantics remain the shared foundation.

**Why use DriverManagerDataSource?** It is a simple DataSource suited for a demo, with no connection pool; each worker transaction gets an independent connection. Production applications should use a pool like HikariCP with proper limits and monitor active/idle/pending connections. Do not use `DriverManagerDataSource` for high-load systems.

**Why is there a barrier inside the transaction?** Solely to simulate the deadlock deterministically. In the opposite-order round, each worker UPDATEd a different row and held its lock, then both workers simultaneously requested the other row. Never do this with `CyclicBarrier` or `Thread.sleep` inside production transactions: holding DB locks while waiting for synchronization can stall the entire system.

### 7.4. Run and read output

From the **spring-deadlock-demo** directory:

~~~bash
mvn -q compile exec:java
~~~

When local PostgreSQL is ready, there is no external traffic outside the demo, and the deadlock detector operates normally, **expected stdout from Java main**:

~~~text
opposite order: commits=1, deadlocks=1, row1=1, row2=1
consistent order: commits=2, deadlocks=0, row1=2, row2=2
~~~

Reading the results:

- In **opposite order**, both transactions updated their first row, yet only **one transaction committed both UPDATEs**. The transaction hit by 40P01 rolled back, so row1=row2=1. It does not matter which worker won.
- In **consistent order**, both workers waited normally at row1, then sequentially updated row2 and committed. Each row was incremented twice, so row1=row2=2.
- The experiment performs no automatic retry: it deliberately lets you see the victim aborted by the DB and requiring the caller to decide what to do. The next section discusses retry policies.
- If another error occurs—such as database not ready, barrier timeout, pool/connection issue, or environment timeout configured too low—the program throws an exception instead of printing both lines; investigate the root cause rather than treating it as a "passing deadlock test."

Stop the demo container:

~~~bash
docker stop spring-deadlock-pg
~~~

### 7.5. Limitations of the demo

The demo uses PostgreSQL **READ_COMMITTED** and two simple rows; it does not test every deadlock form in real production systems. A schema with foreign keys, triggers, indexes, partitions, or JPA batching may involve other locks not covered by the "row1 before row2" protocol.

A proper test must verify both **post-completion DB values** and the **SQLSTATE 40P01 error**, not merely count any arbitrary exception. Data is read after both Futures complete, outside both workers' transactions, so it reflects committed state.

## 8. Writing a @Transactional service with standard lock ordering

In real applications, an **application service** should own the entire business operation. The following Spring JDBC example transfers money from `fromId` to `toId`, locking both accounts in ascending ID order **regardless of transfer direction**:

~~~java
// Complete method snippet, but must be placed in a Spring-managed class
// with a JdbcTemplate jdbc field and imported annotations.
@Transactional(
        propagation = Propagation.REQUIRED,
        isolation = Isolation.READ_COMMITTED,
        timeout = 10)
public void transfer(long fromId, long toId, long amount) {
    if (fromId == toId || fromId <= 0 || toId <= 0 || amount <= 0) {
        throw new IllegalArgumentException("Invalid transfer input");
    }

    long first = Math.min(fromId, toId);
    long second = Math.max(fromId, toId);

    // Lock sequentially, same canonical order for every transfer.
    Long actual1 = jdbc.queryForObject(
            "SELECT id FROM account WHERE id = ? FOR UPDATE",
            Long.class, first);
    Long actual2 = jdbc.queryForObject(
            "SELECT id FROM account WHERE id = ? FOR UPDATE",
            Long.class, second);
    if (actual1 == null || actual2 == null) {
        throw new IllegalStateException("Account missing");
    }

    int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount);
    int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, toId);

    if (debited != 1 || credited != 1) {
        throw new IllegalStateException("Transfer rejected");
    }
}
~~~

**Note on JDBC queryForObject:** for each primary-key SELECT FOR UPDATE, `queryForObject` throws `EmptyResultDataAccessException` if no row is found (rather than merely returning null). Real applications must handle that exception per error policy; the `if null` check is a defensive check, not a replacement for the missing-row case. This is a **snippet**, not a standalone Java file or copy-pasteable code without beans/config.

Lock order **does not have to match business UPDATE order**; because rows are already locked in ascending order, the service can debit `fromId` and then credit `toId`. Never accidentally transfer money in the wrong direction just to follow id order.

**Balance protection** also requires `CHECK(balance>=0)`, idempotency keys, `balance>=amount`, and checking affected row counts. Consistent ordering mainly solves one class of deadlocks; it **does not replace** isolation, constraints, or sound business logic.

### Better approach for batching multiple accounts

When locking a list of `accountIds`, normalize and sort by stable numeric ID:

~~~java
// Snippet inside a transaction; accountIds is a Collection<Long>.
List<Long> orderedIds = accountIds.stream()
        .distinct()
        .sorted()
        .toList();

for (Long id : orderedIds) {
    jdbc.queryForObject(
            "SELECT id FROM account WHERE id = ? FOR UPDATE",
            Long.class, id);
}

// After acquiring all locks, validate data and apply business changes.
~~~

For very large row counts, many SELECT round trips add overhead; you can optimize with suitable SQL/batching and **verify actual lock acquisition order** on the DBMS. An `UPDATE ... WHERE id IN (...)` statement does not automatically guarantee locking in the Java list's order. Never rely on the iteration order of `HashMap` or `HashSet`.

## 9. Why is "sorting IDs" alone not the whole solution?

### 9.1. Same canonical order across every code path

Suppose TransferService always locks account 1 then 2, yet a batch reconciliation job locks 2 then 1. A deadlock can still happen:

~~~text
HTTP request:     lock 1 -> wants lock 2
Nightly job:      lock 2 -> wants lock 1
                  => wait cycle
~~~

A convention in just one service **is insufficient**. It must be unified across every path touching the resources: HTTP, schedulers, Kafka consumers, batch jobs, admin commands, migrations, and triggers/DB procedures. When changing schemas, update the lock ordering contract and regression tests.

### 9.2. Lock mode upgrades

Two transactions can both acquire a shared lock on a resource and then **both request an upgrade to a stronger lock** to write. If each transaction blocks the other's upgrade request, a deadlock can form even on the exact same row list.

Principle: if you already know a write is coming, consider **acquiring the required lock mode upfront**, such as PostgreSQL `SELECT FOR UPDATE` instead of `SELECT FOR SHARE` followed by `UPDATE`. Choosing a stronger mode must balance throughput and requirements; do not lock whole tables broadly just out of fear of deadlocks.

### 9.3. Foreign keys, indexes, constraints, and triggers

An INSERT into a child table with a foreign key may need to check/lock the parent row; updating a unique key can wait on another transaction; a trigger can UPDATE additional tables. Thus if a service reads in code order `Account -> Ledger` while the DB implicitly touches `Inventory -> Customer`, the logical code order does not capture all locks.

When deadlocks still occur despite "already sorting," investigate:
- The actual SQL statements sent and their bind parameters.
- Foreign keys and cascades.
- Triggers and stored procedures.
- Unique/exclusion constraints and index maintenance.
- ORM flush ordering and JDBC batching.
- DDL/maintenance operations and lock modes.
- Long transactions upgrading modes or holding many rows.

### 9.4. JPA/Hibernate flush order

In JPA, calling `entityManager.persist`/updating entities in a Java order does not guarantee SQL INSERT/UPDATE executes immediately in that order. The persistence context may defer until flush; Hibernate may batch/reorder SQL per its policies. For cases requiring deterministic lock order, use explicit pessimistic locks on entities in sorted ID order or a shared resource locking protocol before mutating state, then inspect the generated SQL.

~~~java
// Snippet: runs inside a Spring/JPA transaction, IDs already sorted.
Account first = entityManager.find(
        Account.class, firstId, LockModeType.PESSIMISTIC_WRITE);
Account second = entityManager.find(
        Account.class, secondId, LockModeType.PESSIMISTIC_WRITE);
if (first == null || second == null) {
    throw new IllegalStateException("Missing account");
}
~~~

The snippet above requires Jakarta Persistence imports, an `Account` entity, fields, and context; it is not a standalone Java program. Lock modes and locking behavior depend on provider/DBMS; do not use an H2 JPA test to claim every PostgreSQL/MySQL production path is deadlock-free.

### 9.5. No row to lock

A primary-key `SELECT ... FOR UPDATE` returning no rows **places no row lock on a record that does not yet exist**. For the invariant "there must not be two orders created with the same code," locking existing rows alone is insufficient; both transactions see "does not exist yet." Use a unique constraint, guarded upsert/insert, advisory lock, or shared parent/guard row depending on design. Deadlocks and uniqueness races can appear together, yet are distinct problems.

## 10. When the database detects a deadlock: PostgreSQL 40P01

PostgreSQL returns **SQLSTATE 40P01 (deadlock_detected)**. The server breaks the cycle by aborting one transaction; the remaining side can be granted the lock and proceed. SQLSTATE is more stable than parsing message strings, since messages can be localized or include PIDs/transaction IDs.

Distinction table:

| SQLSTATE | PostgreSQL condition | Meaning | Application action |
| --- | --- | --- | --- |
| **40P01** | deadlock_detected | A transaction was aborted due to a wait cycle | Complete rollback, retry whole use case if permitted, fix lock order |
| **40001** | serialization_failure | Transaction could not commit safely under its isolation level | Retry whole transaction after classification and per policy |
| **55P03** | lock_not_available | Can result from NOWAIT or lock_timeout | Do not assume deadlock; may back off, report busy, or retry |
| **57014** | query_canceled | E.g., statement_timeout or query cancel | Analyze query/timeout/cancellation; do not treat as deadlock |
| **23505** | unique_violation | Uniqueness constraint violated | Likely business duplicate; do not auto-retry unconditionally |
| **25P02** | in_failed_sql_transaction | Transaction previously errored and further commands are rejected | End/roll back failed transaction before doing further work |

Spring JDBC provides exception translation via `DataAccessException`. Depending on driver, translator, and version, a deadlock may appear as a subclass like `CannotAcquireLockException` or a pessimistic-locking exception; **do not tie all handling to a single exception class name** without runtime verification. In the example, we walk the cause chain for `SQLException` and check SQLSTATE `40P01` to classify.

**When a SQL error puts a PostgreSQL transaction into an aborted state, do not continue running business SQL inside that transaction.** Spring `TransactionTemplate` or `@Transactional` must roll back/clean up; retries must start a new transaction.

### Warning on savepoints

PostgreSQL can allow recovering from certain errors via `ROLLBACK TO SAVEPOINT` when the transaction and design support it; however, relying on savepoints to "swallow deadlock errors and carry on as if nothing happened" is risky and does not replace retrying the whole business transaction. When the goal is completing a use case after 40P01, the clean strategy is letting the aborted transaction end and re-running the entire read–decide–write inside a new boundary.

### Being a deadlock victim does not mean bad data

The database aborts a victim for liveness/concurrency, not necessarily because business data is invalid. A retry may succeed once the other transaction commits and releases its locks. However, if the business operation is **not idempotent** or external side effects were already emitted, you cannot retry blindly. The next section explains how to structure this.

## 11. Retrying at the right place in Spring: one attempt = one new transaction

Place a retry loop **outside** the transactional service method. Each attempt must:

1. Open a new transaction.
2. Re-read required data.
3. Re-check business preconditions/invariants.
4. Acquire locks in canonical order.
5. Write changes and commit.
6. If 40P01/40001 is classified as retryable, let Spring finish rollback/cleanup, then retry from step 1.

**Do not retry only the final UPDATE with stale read parameters.** After the other transaction committed, balances, inventory, versions, or order statuses may have changed; business decisions must be recomputed.

~~~text
Attempt 1:
  BEGIN T1
  READ + lock + UPDATE
  deadlock 40P01
  ROLLBACK T1
  Spring releases Connection

Backoff

Attempt 2:
  BEGIN new T2
  Re-READ + re-check + lock same order
  UPDATE if business rules still hold
  COMMIT T2
~~~

### Example retry skeleton outside @Transactional

~~~java
// Snippet: this caller is NOT inside an open transaction.
// transferService is another Spring bean/proxy with @Transactional.
for (int attempt = 1; attempt <= 3; attempt++) {
    try {
        transferService.transfer(fromId, toId, amount);
        return;
    } catch (org.springframework.dao.DataAccessException ex) {
        boolean retryable = hasSqlState(ex, "40P01")
                || hasSqlState(ex, "40001");
        if (!retryable || attempt == 3) {
            throw ex;
        }
        // Production: exponential backoff, jitter, and interruption handling.
    }
}
~~~

This is **not standalone code**: it needs `hasSqlState`, input variables, enclosing class/caller, and transaction configuration. Retry only when the business operation is designed to be safely retried. If `@Transactional` wraps the **entire for-loop**, all attempts may share one aborted transaction — incorrect. With Spring Retry/`@Retryable`, mind **AOP aspect ordering**: the retry advice must be ordered so each invocation enters a **new** transactional call.

### Bounded backoff and idempotency

Retries cannot be infinite. Include:

- Maximum attempt count and exponential backoff with **jitter**.
- Clear SQLSTATE classification; do not retry every `DataAccessException`.
- Request timeout/budget; do not hold threads or connections indefinitely.
- Correlation/request ID to trace all related attempts.
- Idempotency key if clients or message consumers may resend the same request.
- Transactional outbox or after-commit events to avoid sending duplicate emails/messages when the DB rolls back and retries.
- Decoupling remote API calls from transactions whenever possible; an executed remote payment does not roll back with JDBC.

For example, "write DB, send email, then deadlock" is very dangerous: the DB rolls back while the email was already sent. Retrying sends a duplicate email. A sound design writes both the business change and an **outbox event** in the same database transaction; a worker sends emails/messages after commit with its own retry/idempotency.

### Only retry the victim, do not replay both as if both failed

In the demo, one transaction committed and one hit 40P01. If the caller retries the victim and both operations **are genuinely two independent business events**, it can be valid for both to eventually commit. Yet if they are duplicate submissions of the same request, an idempotency key is required so it is not processed twice. Do not equate "deadlock is retryable" with "re-running any request is safe."

## 12. Keeping transactions short reduces deadlocks and lock waits

Consistent ordering is strong medicine for the same lock set, yet long transactions still extend lock hold times and create more opportunities for complex interactions.

**Do not keep transactions open across:**

- HTTP calls to external gateways.
- Waiting for user confirmation.
- Sending emails or uploading large files.
- Long CPU computations that do not need transactional DB reads/writes.
- Sleeps/retry delays or awaiting Futures running on other threads.
- Batches of thousands of rows if business logic allows splitting into independent chunks.

Instead, prepare data upfront where possible, open the transaction **close to the read–decide–write steps needing atomicity**, acquire locks in shared order, re-check mutable conditions, commit early, and process side effects after commit.

**Never move critical invariant checks outside the transaction and assume data won't change.** For example, balance/stock read before locking can change by the time the transaction starts. Re-check under lock, use conditional UPDATE, optimistic version, or suitable isolation.

### Avoid broader lock modes than required

Heavy `SELECT FOR UPDATE` and `LOCK TABLE` can hurt throughput if overused. When the problem is simply incrementing a counter, an atomic SQL statement:

~~~sql
UPDATE counter SET value = value + 1 WHERE id = 10;
~~~

can be both simpler and safer than `SELECT ... FOR UPDATE` followed by `UPDATE`. However, when **multiple rows must be updated under a shared invariant**, a broader protocol is needed. Choose the right lock level rather than "locking the whole table just to be safe."

## 13. NOWAIT, SKIP LOCKED, and timeouts: tools for different goals

### NOWAIT

~~~sql
SELECT id FROM account WHERE id = 1 FOR UPDATE NOWAIT;
~~~

If the lock cannot be acquired immediately, PostgreSQL errors instead of waiting long. Useful for APIs that need to reply "currently busy," though it does not replace business correctness or deadlock-avoidance measures. NOWAIT errors typically fall under **lock_not_available** (55P03), which is not proof of a deadlock.

### SKIP LOCKED

~~~sql
SELECT id
FROM job_queue
WHERE status = 'READY'
ORDER BY id
FOR UPDATE SKIP LOCKED
LIMIT 10;
~~~

Useful for **work queues**: workers can skip jobs locked by other workers. Yet results do not reflect a complete snapshot of the whole table; **do not casually use SKIP LOCKED** for money transfers or invariant checks that must see every row. Altering read contents by skipping locked rows can break business logic.

### PostgreSQL timeout settings

| Setting | Meaning |
| --- | --- |
| **deadlock_timeout** | After this wait, PostgreSQL considers running the deadlock detector; does not "auto-abort every slow lock wait" |
| **lock_timeout** | Limit for waiting to acquire a lock; exceeding it can abort the statement with lock_not_available |
| **statement_timeout** | Limit for statement execution duration; can time out even without lock waits |
| **idle_in_transaction_session_timeout** | Limits sessions holding open idle transactions; helps prevent indefinite lock holding |
| **@Transactional(timeout=...)** | Spring transaction timeout metadata; enforcement depends on manager/driver/operation; not identical to every PostgreSQL server setting |

If `lock_timeout` is much shorter than `deadlock_timeout`, requests may fail with lock timeout **before PostgreSQL's deadlock detector identifies the cycle**; not seeing 40P01 in that case does not prove wait cycles are gone. For the demo, avoid overly short `lock_timeout` and use normal deadlock detector settings.

Never tweak global `deadlock_timeout` or `statement_timeout` in production just for illustration. These parameters must be evaluated by DBAs/operations according to workload, permissions, and environment. Timeouts are **damage/latency bounds**, not a substitute for lock ordering.

## 14. Observing deadlocks in PostgreSQL

### 14.1. Reading error logs

PostgreSQL typically emits a **deadlock detected** message, SQLSTATE 40P01, and details about the involved processes/locks/statements. Server logs can record a wait graph. **Specific PIDs, transaction IDs, and the chosen victim vary per run**; never hardcode these values in tests.

When 40P01 occurs in the application, log selectively:

- Correlation ID and operation name.
- SQLSTATE and exception class (not just the message).
- Transaction attempt number and duration.
- Transaction/resource name if available.
- Database connection/backend PID when tooling permits and is appropriate.
- SQL pattern or sanitized fingerprint without sensitive data.

Never print raw payment credentials, tokens, or PII in SQL parameters when debugging locks.

### 14.2. pg_stat_activity and pg_blocking_pids

In PostgreSQL, given appropriate privileges, a blocker-monitoring query:

~~~sql
SELECT
    pid,
    state,
    wait_event_type,
    wait_event,
    pg_blocking_pids(pid) AS blocking_pids,
    LEFT(query, 120) AS query_sample
FROM pg_stat_activity
WHERE datname = current_database()
  AND pid <> pg_backend_pid()
ORDER BY pid;
~~~

`wait_event_type='Lock'` indicates a backend may be waiting on a lock. `pg_blocking_pids(pid)` lists current observed blockers. Relationships can change rapidly; database deadlock detector output and error logs remain the authoritative evidence once a deadlock occurred.

In multi-tenant environments, restrict privileges to view other sessions' SQL and avoid logging query samples containing sensitive information into application logs.

### 14.3. pg_locks and cumulative metrics

~~~sql
SELECT pid, locktype, mode, granted, relation::regclass AS relation_name,
       transactionid
FROM pg_locks
WHERE pid IS NOT NULL
ORDER BY pid, locktype, mode;
~~~

Some row-level conflicts surface via locks on transaction IDs or other mechanisms; you cannot deduce the entire wait chain from a single `pg_locks` row. Combine `pg_blocking_pids`, `pg_stat_activity`, server logs, and SQL execution paths.

Database cumulative deadlock count:

~~~sql
SELECT datname, deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

This is a **cumulative counter** in the DBMS statistics window, not the deadlock count of a single request. To measure rate, take deltas over time; compare with traffic and concurrency. Rising metrics should trigger investigation into diverging lock-order paths and transaction durations.

### 14.4. Do not wait until production to test

A solid observability plan includes dashboards for:

- Deadlocks per minute or deadlocks per thousand transactions.
- Lock wait times and blocked sessions.
- Transaction duration (P95/P99).
- Connection pool active, idle, pending, and timeouts.
- Retries/attempts count, post-retry successes, and exhausted failures.
- SQL fingerprints frequently appearing in deadlock reports.

Metrics only highlight hotspots; **a permanent fix requires finding the exact wait cycle and unifying lock order across code paths**.

## 15. Common Spring/JPA mistakes when handling deadlocks

| Mistake | Consequence | Proper approach |
| --- | --- | --- |
| Adding @Transactional and assuming no deadlocks | DB still has two transactions waiting in a cycle | Design lock order and handle 40P01 |
| Every transfer direction locks fromId first | A->B and B->A lock in reverse order | Sort account IDs and lock smaller ID first |
| Repository A sorts, background worker B does not | Wait cycle still occurs across paths | Standardize protocol across the entire system |
| HashSet/HashMap iteration decides lock order | Unstable order / not a contract | Stable comparator, sort before locking |
| Relying on method call order in JPA | Flush/SQL can happen later or reorder | Lock explicitly in canonical order, check actual SQL |
| Calling @Transactional on this.inner() expecting advice | Self-invocation bypasses proxy mode | Call via Spring-managed bean/proxy appropriately |
| Catching DataAccessException inside @Transactional and continuing SQL | PostgreSQL transaction already aborted, likely 25P02 | Let exception escape and roll back; retry outside |
| Retrying inside an already-open outer transaction | Next attempt reuses failed/rollback-only transaction | One new transaction per attempt |
| Retrying only the final statement after error | Preconditions are stale | Re-run the entire read–decide–write |
| Infinite retries without jitter | Retry storms, worse contention | Bounded attempts, backoff/jitter, metrics |
| Sending email before commit then retrying | Emails/messages can be duplicated | Outbox/after-commit/idempotency |
| Seeing a lock wait and calling it a deadlock | Misdiagnosis | Check SQLSTATE 40P01 or wait cycle |
| Setting tiny lock_timeout to "cure deadlocks" | Masks deadlocks with timeouts; requests fail early | Fix lock order, keep transactions short; timeout is secondary |
| SELECT FOR UPDATE on a nonexistent row | No row is locked | Unique/guard/advisory lock or constraint design |
| Using SKIP LOCKED for operations needing full reads | Skips rows, wrong results | Use only where queue semantics permit |
| Splitting operations into REQUIRES_NEW arbitrarily | Independent commits, pool exhaustion, outer still holds locks | Choose propagation by business atomicity and resource costs |

### How do Spring AOP and propagation relate?

A `@Transactional` service method actually controls transactions only when calls pass through the Spring proxy (in proxy mode). **Self-invocation** or objects created with `new` can leave the boundary nonexistent. If outer `REQUIRED` is open, inner `REQUIRED` joins that transaction; if inner is `REQUIRES_NEW`, Spring suspends outer and opens another transaction, usually needing an extra connection. `REQUIRES_NEW` **is not an anti-deadlock cure**: the inner transaction can still contend for locks with outer or other transactions, and can even complicate the wait graph because outer holds resources while suspended.

When multiple transaction managers/DataSources exist, determine which manager actually governs the SQL. A local transaction manager for DB A cannot govern all locks/commits on DB B. For distributed resources, evaluate consistency architecture and appropriate technologies.

## 16. Practical deadlock investigation workflow

When receiving a deadlock alert:

1. **Confirm the error:** extract SQLSTATE 40P01 (PostgreSQL) from causes/logs. Separate 40001, 55P03, 57014.
2. **Identify participants:** correlation IDs, backend PIDs, SQL fingerprints, and tables/rows/lock modes from logs.
3. **Draw the wait-for graph:** what T1 holds and waits for; what T2 holds and waits for; which cycle causes the deadlock.
4. **Read all transaction code paths:** services, repositories, schedulers, ORM flushes, triggers, FKs, background jobs.
5. **Define canonical lock order:** resource types and primary keys; document as a reviewable contract.
6. **Review lock modes:** acquire sufficiently strong locks upfront if needed to avoid upgrade deadlocks.
7. **Shorten lock duration:** remove remote calls/sleeps from transactions, optimize queries/indexes, split batches per business atomicity.
8. **Place safe retries:** at the outer caller; each attempt opens a new transaction; bounded/backoff, classify errors.
9. **Test with two concurrent transactions:** interleave before/after the fix, read data after commit.
10. **Monitor after rollout:** deadlock counts, lock waits, pool saturation, retry success, and request latency.

**Example root cause:** `transfer()` and `nightly-reconcile()` update the same two accounts; `transfer` uses `from->to`, `reconcile` uses sorted IDs. Just one reverse transfer direction creates a cycle. Fix by having both use sorted IDs before updating. If the cause stems from triggers/unique constraints, update resource ordering at that layer rather than changing only one Java method.

## 17. Testing concurrency in Spring

A sequential unit test will not detect deadlocks without interleaving:

~~~text
T1: lock A, lock B, commit
T2: lock B, lock A, commit
=> At no point do both transactions hold crossed locks.
~~~

To test properly, you need:

1. **Two independent concurrent connections/physical transactions**.
2. A barrier/latch placed at the exact spot between acquiring the two locks **only in tests**.
3. Assertions on outcomes including **commits**, **deadlock errors**, and **post-completion data**.
4. A production-like DBMS; H2 may have different semantics and error codes from PostgreSQL.
5. Never run both workers inside **the same @Transactional test context** thinking they are two independent transactions.
6. Test the new protocol with multiple permutations (A->B, B->A, duplicate ID batches, more than two rows).
7. Run with the same schema constraints, indexes, triggers/ORM flushing as production.
8. Test retrying the victim after rollback in a new transaction, checking idempotency/constraints.
9. Test failure modes too: lock timeout, serialization failure, deadlock, network interruption, commit failure.

In Spring TestContext, if a test method has `@Transactional`, the framework may roll back at the end of the test and fail to represent real commits. Read data via an independent transaction/connection after workers finish. The Java demo in Section 7 uses `TransactionTemplate` inside each worker to avoid accidentally sharing a transaction context across threads.

### Example assertions checklist

| Test | Expected behavior |
| --- | --- |
| Opposite order + barrier after first lock | PostgreSQL detects 40P01; one transaction rolls back, one commits |
| Same order + barrier before first lock | Both transactions commit sequentially, no cycle from these two rows |
| Same order + many requests | No deadlocks from the standardized row/lock-order set |
| Inner REQUIRES_NEW hitting outer locks | Do not assume safe; test lock waits/pool timeouts |
| Retry victim after 40P01 | Opens new transaction and re-reads state; business outcome remains valid |
| Retry sending message/event | No duplicate side effects if request/idempotency/outbox protects it |
| ORM flush/trigger/foreign key | No lock order violating convention from indirect layers |

## 18. Self-check questions

**1. Why is T1 holding A waiting for B and T2 holding B waiting for A a deadlock, whereas T2 merely waiting on T1 holding A is not?**  
Because a deadlock requires a **wait cycle**. In the second case T1 is not blocked by T2, so it can still commit and release A for T2.

**2. PostgreSQL automatically detects deadlocks; does that mean the application has nothing to do?**  
No. PostgreSQL only breaks the cycle by aborting one transaction. The application must handle the error, roll back/clean up, and retry the whole business operation if safe; preventing via lock ordering remains essential.

**3. Why shouldn't A->B and B->A transfers lock `fromId` first?**  
Because the two requests can lock in opposite orders. Lock account IDs in a canonical order, then debit/credit in the business direction.

**4. Does an UPDATE by row ID acquire locks even without `SELECT FOR UPDATE`?**  
Yes. UPDATE typically acquires write locks, so row-level deadlocks can occur without explicit `SELECT FOR UPDATE`.

**5. Why does sorting a `HashSet` with `stream().sorted()` help?**  
It produces a deterministic order so transactions acquire row locks by the same rule; it must be applied across all paths and verified against actual DB SQL.

**6. How does 40P01 differ from 55P03?**  
40P01 is `deadlock_detected` — a wait cycle detected by the database. 55P03 is `lock_not_available` — e.g., from NOWAIT/`lock_timeout`, which does not prove a wait cycle.

**7. Why must retries sit outside the `@Transactional` boundary?**  
Because the errored/aborted PostgreSQL transaction must end and a new transaction must open. Retrying inside the same failed transaction does not restore a clean state to redo the use case.

**8. If an ORM calls `persist(A)` then `persist(B)`, will the DB definitely acquire locks in that order?**  
No. The ORM can defer and reorder SQL during flush/batching. Inspect actual SQL or lock explicitly in canonical order.

**9. Does `@Transactional(timeout=10)` prevent all deadlocks?**  
No. Timeout bounds time per supported mechanism; it does not eliminate wait cycles and may trigger a timeout error before the deadlock detector fires.

**10. A request already sent an email and then the transaction deadlocked and rolled back. What is dangerous about retrying?**  
The sent email does not roll back with the DB, so retrying can send a duplicate. You need outbox, after-commit workflows, and idempotency.

**11. Should `SKIP LOCKED` be used to resolve lock waits in money transfers?**  
Not arbitrarily. Skipping locked rows omits data that must be checked and can break logic; `SKIP LOCKED` suits job queues, not multi-row invariants.

**12. Can sorting two account IDs eliminate 100% of all deadlocks?**  
No. It eliminates cycles between those two account rows if every transaction obeys it, yet other locks still exist via FKs, uniques, triggers, ORM flushes, DDL, and multiple resource types.

## 19. Conclusion and guiding principles

- **Deadlock = a cycle of transactions waiting on each other's locks**, not synonymous with every slow lock wait.
- **Spring `@Transactional` provides atomic boundaries, not automatic lock ordering** in the DBMS.
- **Canonical lock order** must be consistent across all code paths: resource types, stable IDs, lock modes; prefer acquiring needed modes upfront.
- For bidirectional transfers, **lock smaller id then larger id** first, then debit/credit in the right business direction.
- PostgreSQL breaks deadlocks with **SQLSTATE 40P01**, aborting one victim; the other transaction can continue.
- **Retry the entire transaction**, with fresh reads, bounded attempts/backoff, error classification, and idempotency; never continue on an aborted transaction.
- Keep transactions short; avoid remote calls/sleeps inside critical sections.
- Verify with **concurrent integration tests on a real DBMS**, combining error logs, `pg_stat_activity`, `pg_blocking_pids`, pool metrics, and post-commit data.
- **Do not infer absolute deadlock immunity** from a single sort rule, because indirect locks can still arise from indexes, triggers, FKs, ORMs, and DDL.

## References

- [PostgreSQL — Explicit Locking, Deadlocks section](https://www.postgresql.org/docs/current/explicit-locking.html)
- [PostgreSQL — Error Codes: 40P01, 40001, 55P03, 57014](https://www.postgresql.org/docs/current/errcodes-appendix.html)
- [PostgreSQL — Lock Management, deadlock_timeout](https://www.postgresql.org/docs/current/runtime-config-locks.html)
- [PostgreSQL — Client Connection Defaults, lock_timeout / statement_timeout](https://www.postgresql.org/docs/current/runtime-config-client.html)
- [PostgreSQL — Monitoring Statistics, pg_stat_activity and pg_locks](https://www.postgresql.org/docs/current/monitoring-stats.html)
- [PostgreSQL — Serialization Failure Handling](https://www.postgresql.org/docs/current/mvcc-serialization-failure-handling.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — TransactionTemplate API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
