# Distinguishing NESTED from REQUIRES_NEW in Spring Transaction Management

## 1. The Problem: Partial Rollback or Independent Commit?

When a service is already inside a transaction and calls a child service, sometimes you want to **undo only the child step while continuing the parent service's work**. Other times, you want **the child step to commit for real, even if the parent service later fails**. Two seemingly similar requirements lead to two different Spring propagation behaviors:

- **PROPAGATION_NESTED:** creates a **savepoint inside the caller's same physical transaction**, so an executed segment can be rolled back; the final commit still depends on the outer transaction.
- **PROPAGATION_REQUIRES_NEW:** suspends the outer transaction and starts an **independent physical transaction**, which can commit or roll back on its own.

The decisive difference does not lie in the number of `@Transactional` methods, but in **the number of physical transactions**, **the number of JDBC Connections used**, **when data actually commits**, and **whether an outer rollback affects inner**.

This lesson is part of the **NESTED and savepoints** section of Spring Framework transaction management. It focuses on comparing NESTED with REQUIRES_NEW and guiding the right choice in JDBC/JPA applications. The Java 17+ hands-on section uses Spring JDBC and H2 to illustrate four rollback/commit scenarios you can verify directly.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **logical transaction scope** from **physical transaction** in nested method calls.
2. Accurately describe how NESTED uses a **JDBC Savepoint**.
3. Explain why REQUIRES_NEW needs an **independent transaction and usually another Connection**.
4. Predict which data remains when **inner fails**, **outer fails**, **inner commits**, or **outer commits**.
5. Identify support limitations of the **transaction manager/driver/DBMS**, especially with JPA.
6. Avoid **self-invocation** bugs, pool exhaustion, lock contention, and misunderstanding "inner commit."
7. Write integration tests verifying each scenario instead of inferring from a single annotation.

## 2. From REQUIRED to Two Nested Propagation Styles

By default, `@Transactional` uses **Propagation.REQUIRED**. When an outer transaction already exists, an inner REQUIRED method **joins the same physical transaction**. If inner logic marks the transaction rollback-only, outer catching the error and trying to commit can throw **UnexpectedRollbackException**, because the entire physical transaction must roll back.

Both NESTED and REQUIRES_NEW can alter that outcome, yet via **two completely different mechanisms**:

~~~text
REQUIRED (participating):
    outer T1 begin ----------------------- outer T1 commit/rollback
        inner REQUIRED -> uses same T1; no automatic savepoint
        inner requests rollback-only -> T1 cannot commit

NESTED (savepoint):
    outer T1 begin ----------------------- outer T1 commit/rollback
        SAVEPOINT S1
        inner NESTED -> same T1, same Connection
        inner fails -> ROLLBACK TO S1
        outer can continue; if outer rolls back, all of T1 is lost

REQUIRES_NEW (new transaction):
    outer T1 begin -- suspend ---------- resume -- outer commit/rollback
                     inner T2 begin
                     inner T2 commit/rollback
        T1 and T2 are independent in final commit decisions
~~~

A **physical transaction** is the transaction on which the JDBC Connection/DBMS executes commit/rollback. A **logical scope** is the configured boundary of a Spring-intercepted method call. NESTED adds a savepoint, whereas REQUIRES_NEW adds a genuine physical transaction.

### Core Differences Table

| Criterion | NESTED | REQUIRES_NEW |
| --- | --- | --- |
| When outer transaction already exists | Joins the **same physical transaction** while creating a savepoint | Suspends outer transaction; creates a **new physical transaction** |
| JDBC Connection | Typically the **same Connection** as outer | Usually uses **another Connection** while outer holds its connection |
| How inner rolls back | Rolls back to **savepoint** | Rolls back **inner transaction** independently |
| Inner succeeds | No independent commit; changes await outer commit | Can **commit independently as soon as inner finishes** |
| Outer rolls back after inner succeeds | **Discards inner changes too** | Does not discard **already-committed** inner changes |
| Outer commits after inner rolls back, error handled | Can keep valid outer work | Can keep outer work while inner rolled back independently |
| Physical-level isolation/timeout/read-only | Usually follows outer transaction since no new physical transaction opens | Can configure independent policy for the new transaction |
| Resources/pool | Savepoint on existing connection; usually borrows no extra connection | May need an extra connection; prone to pool exhaustion if poorly designed |
| Support prerequisites | Manager + JDBC driver + DBMS supporting savepoints | Manager supporting suspend/resume and opening a matching new transaction |
| Common use case | Trying a secondary DB branch; partial rollback yet **same final commit** | Audit/status logging that must commit **separately** when outer fails |
| Consistency level | Nested part still belongs to outer's all-or-nothing unit | Inner commit can persist even if outer does not commit |

**One-sentence takeaway:** NESTED is **partial rollback within the same transaction**; REQUIRES_NEW is **a separate transaction with its own commit authority**.

## 3. NESTED Operates with a JDBC Savepoint

### 3.1. What Is a Savepoint?

JDBC provides APIs in `java.sql.Connection`:

~~~java
// Illustrates the JDBC API only; not code for use inside a Spring-managed transaction.
Savepoint point = connection.setSavepoint("before_optional_step");
try {
    performOptionalSql(connection);
} catch (SQLException ex) {
    connection.rollback(point);
}
connection.releaseSavepoint(point);
~~~

This illustrative code requires a `Connection`, `performOptionalSql`, and complete transaction handling to run. In Spring, **do not manually manipulate savepoints on a Connection managed by the transaction manager** unless you have a specific reason and know how to coordinate it; let `@Transactional(propagation=NESTED)` or the `TransactionStatus` API handle it per the manager's contract.

A savepoint acts like a **marker** inside an open physical transaction:

~~~text
BEGIN T1
    UPDATE account_A                       (change belonging to T1)
    SAVEPOINT S1
        UPDATE account_B                   (change after S1)
        error occurs
    ROLLBACK TO SAVEPOINT S1               (undoes change to account_B)
    UPDATE account_C                       (continues inside T1)
COMMIT T1                                  (only A and C are saved)
~~~

If `COMMIT T1` is replaced with **ROLLBACK T1**, A and C are also discarded. A savepoint **is not a separately committed transaction** and does not make inner changes durable before outer commits.

At the DBMS level, rolling back to a savepoint can revert data changes and some locks, yet when other locks/objects are released depends on the engine and isolation level. Do not assume a savepoint guarantees resetting all Java/ORM state or external side effects outside the database.

### 3.2. What Does Spring NESTED Do When the Inner Method Is Intercepted?

If outer has opened transaction T1 and the inner method declares:

~~~java
// Snippet: method must be called through an appropriate Spring-managed proxy.
@Transactional(propagation = Propagation.NESTED)
public void optionalUpdate() {
    jdbcTemplate.update("UPDATE optional_table SET score = score + 1");
}
~~~

With `JdbcTransactionManager`/`DataSourceTransactionManager` and a savepoint-capable JDBC driver, Spring creates a nested transaction status linked to a savepoint; inner SQL runs on T1's transaction-bound Connection.

- **Inner returns normally:** Spring ends the nested scope, typically releasing the savepoint. **Physical COMMIT is not called yet** because outer T1 is still running.
- **Inner throws a RuntimeException qualifying for rollback:** the transaction interceptor requests rolling back the nested status; the manager rolls back to the savepoint; the error propagates to outer.
- **Outer catches inner's error and continues:** provided the savepoint rollback succeeded and the physical transaction remains valid, outer can continue and commit the rest.
- **Outer ends in rollback:** all of T1 is discarded, including inner changes that had "succeeded."

If `REQUIRED` were used instead of `NESTED`, an inner runtime failure would typically cause the logical scope to mark **T1 rollback-only**, because there is no savepoint to roll back individually; outer may receive `UnexpectedRollbackException` when trying to commit. This is why NESTED is useful for branches that may fail without aborting the entire business operation.

### 3.3. A Crucial Case: Nested Success Is Not a Commit

~~~text
T1 outer:
    UPDATE A = A + 10
    S1:
        UPDATE B = B + 10
        inner NESTED returns success
    outer encounters error and rolls back T1

Final result:
    A does not increase
    B does not increase either
~~~

This is a decisive difference from REQUIRES_NEW. If the product requirement is "persist B even if part A later rolls back," NESTED does not satisfy it because B has no independent commit.

## 4. REQUIRES_NEW Operates with Two Physical Transactions

When the inner method declares:

~~~java
// Snippet: method called through another Spring bean/proxy.
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void recordAudit() {
    jdbcTemplate.update("INSERT INTO audit_log(message) VALUES (?)", "attempted");
}
~~~

If outer T1 is active, Spring typically:

1. **Suspends** outer T1's transaction context/resources.
2. Acquires a resource for the new transaction T2, usually a different JDBC Connection.
3. Opens transaction T2 with its own propagation/isolation/read-only/timeout policies when supported.
4. Executes the inner method and **COMMITs T2** or **ROLLBACKs T2** depending on the outcome.
5. Cleans up T2, releases T2's Connection, and **resumes** outer T1's context.
6. Lets outer continue; when outer finishes, it commits/rolls back T1 independently.

~~~mermaid
sequenceDiagram
    actor Caller
    participant Outer as Outer service
    participant TM as TransactionManager
    participant Inner as Inner service
    participant DB as DBMS
    Caller->>Outer: outer() REQUIRED
    Outer->>TM: begin T1
    TM->>DB: Connection 1 / T1
    Outer->>Inner: inner() REQUIRES_NEW
    Inner->>TM: suspend T1; begin T2
    TM->>DB: Connection 2 / T2
    Inner->>DB: SQL inner
    Inner->>TM: commit or rollback T2
    TM->>DB: End T2
    TM->>Outer: resume T1
    Outer->>TM: commit or rollback T1
    TM->>DB: End T1
    Outer-->>Caller: Result
~~~

If inner T2 **commits successfully** and then outer T1 rolls back, T2's commit normally persists. Outer failing does not make `TransactionManager` retroactively roll back already-committed transaction T2. That is REQUIRES_NEW's exact semantics, and also a **business consistency risk** if misused.

### Example Showing Reversed Outcome Order

~~~text
BEGIN T1 (outer)
    UPDATE A = A + 10                  [uncommitted]
    SUSPEND T1
        BEGIN T2 (REQUIRES_NEW)
        UPDATE B = B + 10
        COMMIT T2                       [B committed]
    RESUME T1
    ERROR outer
ROLLBACK T1

Final result:
    A unchanged
    B increased by 10
~~~

**Independence does not mean zero interaction:** two physical transactions can still contend on locks, deadlock, or experience isolation anomalies. If inner T2 tries to update a row that outer T1 currently locks, T2 may have to wait or time out; while outer is suspended waiting on T2, that wait can be hard to resolve. The hands-on example below intentionally updates **different rows** to separate propagation behavior from locking issues.

## 5. Rollback and Commit Prediction Matrix

Suppose outer updates row A and inner updates row B. Both use the same DB and encounter no other errors. The following table is the core reference of this lesson:

| Scenario | NESTED | REQUIRES_NEW |
| --- | --- | --- |
| Inner succeeds; outer succeeds | **A and B commit together in T1** | B commits T2 first; A commits T1 afterward |
| Inner succeeds; outer rolls back | **Both A and B roll back** | A rolls back; **committed B is kept** |
| Inner rolls back; outer catches and commits | B rolls back to savepoint; **A is committed** | B rolls back T2; **A is committed** |
| Inner rolls back; outer does not catch and rolls back | Both A and B roll back | B rolls back T2, A rolls back T1 |
| Both inner and outer succeed, yet outer's final commit fails | B cannot be considered committed either since it is inside T1 | B committed in T2 can persist even though T1 did not commit |
| No outer transaction exists | Creates a new transaction (no outer transaction in which to place a savepoint) | Creates a new transaction |

Note: **without an outer transaction**, NESTED does not create a floating savepoint. Like other transaction-creating propagations, Spring creates a new physical transaction to run the method. Comparing NESTED/REQUIRES_NEW matters most when **a transaction already exists at the caller level**.

### Visibility State in the Database

Because NESTED shares the same physical transaction, inner "succeeding" is normally **not yet visible as committed data** to independent transactions until outer commits. REQUIRES_NEW commits separately, so inner's data can become visible to other transactions after commit per the matching isolation level. **There is no guarantee outer immediately sees T2's data** if outer uses snapshot/special transaction isolation; do not rely on outer re-reading for correctness without understanding your DBMS.

## 6. Runnable Java 17+ Example: Four Scenarios on One Database

The example uses **Spring Framework 6.2.12**, **Spring JDBC**, **H2 2.3.232**, and **JdbcTransactionManager**. It needs no Spring Boot or external database server. The same two service beans receive Spring AOP proxies; outer always uses REQUIRED, while inner alternates between NESTED and REQUIRES_NEW.

We create three rows A, B, and C, each starting with `amount=0`. Outer methods update A and C; inner only updates B. By using distinct rows, the demo reduces lock contention between T1 and T2 to focus on transaction semantics.

### 6.1. Project Structure

~~~text
nested-versus-requires-new/
├── pom.xml
└── src/main/java/demo/NestedVsRequiresNewDemo.java
~~~

### 6.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>nested-versus-requires-new</artifactId>
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
            <artifactId>spring-aop</artifactId>
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
                    <mainClass>demo.NestedVsRequiresNewDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring 6.x requires Java 17+. Real applications using Spring Boot should prefer Spring versions managed by Boot's BOM rather than hardcoding versions from an example.

### 6.3. src/main/java/demo/NestedVsRequiresNewDemo.java

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
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

public final class NestedVsRequiresNewDemo {
    private NestedVsRequiresNewDemo() {}

    private static void show(JdbcTemplate jdbc, String label) {
        Integer a = jdbc.queryForObject(
                "SELECT amount FROM demo_amount WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT amount FROM demo_amount WHERE id = 2", Integer.class);
        Integer c = jdbc.queryForObject(
                "SELECT amount FROM demo_amount WHERE id = 3", Integer.class);
        System.out.printf("%s: A=%d, B=%d, C=%d%n", label, a, b, c);
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.update("UPDATE demo_amount SET amount = 0");
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            OuterService outer = ctx.getBean(OuterService.class);

            jdbc.execute("CREATE TABLE demo_amount (" +
                    "id INT PRIMARY KEY, amount INT NOT NULL)");
            for (int id = 1; id <= 3; id++) {
                jdbc.update(
                        "INSERT INTO demo_amount(id, amount) VALUES (?, ?)",
                        id, 0);
            }
            show(jdbc, "initial");

            outer.catchNestedFailure();
            show(jdbc, "NESTED failure, outer commit");

            reset(jdbc);
            try {
                outer.nestedSuccessThenOuterFailure();
            } catch (IllegalStateException expected) {
                // Outer rollback is intentional for this experiment.
            }
            show(jdbc, "NESTED success, outer rollback");

            reset(jdbc);
            try {
                outer.newSuccessThenOuterFailure();
            } catch (IllegalStateException expected) {
                // Inner REQUIRES_NEW committed before outer failed.
            }
            show(jdbc, "REQUIRES_NEW success, outer rollback");

            reset(jdbc);
            outer.catchNewFailure();
            show(jdbc, "REQUIRES_NEW failure, outer commit");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:nested_vs_new;DB_CLOSE_DELAY=-1");
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

        @Bean
        public InnerService innerService(JdbcTemplate jdbc) {
            return new InnerService(jdbc);
        }

        @Bean
        public OuterService outerService(
                JdbcTemplate jdbc, InnerService inner) {
            return new OuterService(jdbc, inner);
        }
    }

    public static class InnerService {
        private final JdbcTemplate jdbc;

        public InnerService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.NESTED)
        public void nestedFail() {
            jdbc.update(
                    "UPDATE demo_amount SET amount = amount + 10 WHERE id = 2");
            throw new IllegalStateException("nested failed");
        }

        @Transactional(propagation = Propagation.NESTED)
        public void nestedSuccess() {
            jdbc.update(
                    "UPDATE demo_amount SET amount = amount + 10 WHERE id = 2");
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNewSuccess() {
            jdbc.update(
                    "UPDATE demo_amount SET amount = amount + 10 WHERE id = 2");
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void requiresNewFail() {
            jdbc.update(
                    "UPDATE demo_amount SET amount = amount + 10 WHERE id = 2");
            throw new IllegalStateException("requires new failed");
        }
    }

    public static class OuterService {
        private final JdbcTemplate jdbc;
        private final InnerService inner;

        public OuterService(JdbcTemplate jdbc, InnerService inner) {
            this.jdbc = jdbc;
            this.inner = inner;
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void catchNestedFailure() {
            addToA();
            try {
                inner.nestedFail();
            } catch (IllegalStateException expected) {
                // Nested scope already rolled back to its savepoint.
            }
            addToC();
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void nestedSuccessThenOuterFailure() {
            addToA();
            inner.nestedSuccess();
            throw new IllegalStateException("outer failed");
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void newSuccessThenOuterFailure() {
            addToA();
            inner.requiresNewSuccess();
            throw new IllegalStateException("outer failed");
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void catchNewFailure() {
            addToA();
            try {
                inner.requiresNewFail();
            } catch (IllegalStateException expected) {
                // Independent inner transaction already rolled back.
            }
            addToC();
        }

        private void addToA() {
            jdbc.update(
                    "UPDATE demo_amount SET amount = amount + 10 WHERE id = 1");
        }

        private void addToC() {
            jdbc.update(
                    "UPDATE demo_amount SET amount = amount + 10 WHERE id = 3");
        }
    }
}
~~~

This is **one complete Java file**, including Spring config and two services as public static nested classes. No self-invocation is used: outer calls methods on a **separate `InnerService` bean** provided by Spring, giving the interceptor a chance to apply NESTED/REQUIRES_NEW properly.

In the `transactionManager` bean, `setNestedTransactionAllowed(true)` is declared explicitly to emphasize savepoint usage in the example. With `DataSourceTransactionManager`/`JdbcTransactionManager`, this flag already defaults to true, yet the **JDBC driver and DBMS must still support savepoints**.

**Why does the code reset data between runs?** So each scenario starts from A=B=C=0 and learners can see the effect of propagation alone. The reset statements run **after the previous transaction has finished**, without joining the outer transaction. `DriverManagerDataSource` creates connections directly and suits demos; production typically uses a connection pool.

### 6.4. Running the Program and Output

In the `nested-versus-requires-new` directory containing `pom.xml`, with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout** printed by Java's `main` (excluding Maven or logging messages):

~~~text
initial: A=0, B=0, C=0
NESTED failure, outer commit: A=10, B=0, C=10
NESTED success, outer rollback: A=0, B=0, C=0
REQUIRES_NEW success, outer rollback: A=0, B=10, C=0
REQUIRES_NEW failure, outer commit: A=10, B=0, C=10
~~~

### 6.5. Analyzing Each Scenario

**Scenario 1 — Inner NESTED fails; outer still commits**

- Outer opens T1, updating A from 0 to 10.
- Inner NESTED creates savepoint S1 on T1, updates B to 10, then throws `IllegalStateException`.
- Inner's interceptor rolls back to S1; B returns to 0 inside T1.
- Outer catches the exception, updates C to 10, and commits T1.
- Final result: **A=10, B=0, C=10**. There is partial rollback of inner, without an independent commit.

**Scenario 2 — Inner NESTED succeeds; outer rolls back**

- Outer opens T1, updating A to 10.
- Inner NESTED creates a savepoint, updates B to 10, and returns normally.
- The nested scope finishes **without physically committing**. Outer then throws `IllegalStateException`.
- Outer's interceptor rolls back T1; both A and B are discarded.
- Result: **A=0, B=0, C=0**. This proves NESTED **does not commit independently**.

**Scenario 3 — Inner REQUIRES_NEW commits; outer rolls back**

- Outer opens T1, updating A to 10 without committing yet.
- Inner REQUIRES_NEW suspends T1 and creates T2 using a different Connection.
- T2 updates B to 10 and **commits T2**.
- Spring resumes T1; outer throws `IllegalStateException` and rolls back T1.
- Result: **A=0, B=10, C=0**. Inner retains its committed change even though outer failed.

**Scenario 4 — Inner REQUIRES_NEW rolls back; outer still commits**

- Outer opens T1 and increments A.
- Inner's independent T2 increments B and throws `IllegalStateException`, rolling back T2.
- Spring resumes T1, outer catches the exception, increments C, and commits T1.
- Result: **A=10, B=0, C=10**. Identical values to Scenario 1, yet a **completely different mechanism**: savepoint inside T1 vs. rolling back an independent T2.

**You cannot distinguish the mechanisms from a single "B=0" line alone.** You must examine the case where inner succeeds while outer rolls back, and if needed inspect transaction manager logs or connection identity.

## 7. Why Does Connection Count Directly Affect Design?

### 7.1. NESTED Needs No New Physical Connection for a Savepoint

With a Spring JDBC local transaction, outer T1 holds one transaction-bound JDBC Connection. Inner NESTED uses the **already-bound Connection** and creates a savepoint on it. The manager does not need to suspend T1 to borrow a second Connection; this generally conserves pool resources.

However, a savepoint **does not shorten T1's lifetime**. If the outer transaction holds locks for a long time, T1's changes and resources can still cause contention until outer finishes. Do not use NESTED expecting it to "automatically release all locks" when inner returns.

### 7.2. REQUIRES_NEW Can Exhaust the Pool and Cause Mutual Waiting

With transaction T1 holding Connection A, an inner REQUIRES_NEW usually has to borrow Connection B. If there are N worker threads and the pool only has N connections, every worker can hold one Connection A while waiting for a Connection B. That can stall all threads or cause timeouts.

Spring recommends sizing the connection pool **larger than the number of concurrent threads by at least one connection** when using REQUIRES_NEW; in practice you must also account for multiple nested calls/concurrency, pool timeouts, and workload. Do not pick a fixed number blindly for every system.

~~~text
Example pool=4, 4 concurrent threads:
    Thread 1: holds A1 (outer), waits for B1 (REQUIRES_NEW)
    Thread 2: holds A2 (outer), waits for B2
    Thread 3: holds A3 (outer), waits for B3
    Thread 4: holds A4 (outer), waits for B4
    Pool has 0 free connections => all inner calls wait together

If using only NESTED/savepoint:
    Each outer uses its already-borrowed connection;
    the nested scope needs no new connection just to open a savepoint.
~~~

Beyond the connection pool, **REQUIRES_NEW can be blocked by outer's locks**. If T1 holds a lock on row X and T2 tries to update the same row X, T2 must wait for T1; yet T1 is suspended waiting for T2. Transaction isolation and lock timeouts must be considered. The SQL statements in the demo pick different rows specifically to avoid this situation.

### 7.3. Verifying via Logs

In Spring Boot, you can temporarily enable:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.support=DEBUG
~~~

Signs to look for (exact wording varies by version/manager):

~~~text
NESTED:
    Creating nested transaction...
    Creating savepoint...
    Rolling back transaction to savepoint...
    Outer transaction commit/rollback...

REQUIRES_NEW:
    Suspending current transaction...
    Creating new transaction...
    Initiating transaction commit/rollback...
    Resuming suspended transaction...
    Outer transaction commit/rollback...
~~~

Do not treat the lines above as exact literal output. Debug/trace log formatting from Spring/DBMS varies. Combine **transaction status, connection/pool metrics, and post-transaction data reads**. Enable TRACE selectively; avoid logging sensitive SQL parameters in production.

## 8. Support Conditions: Spring Manager, JDBC Driver, and JPA

### 8.1. JdbcTransactionManager / DataSourceTransactionManager

With a local JDBC DataSource:

- **DataSourceTransactionManager** supports nested transactions via JDBC Savepoints; the **nestedTransactionAllowed** property defaults to true in this case.
- **JdbcTransactionManager** extends DataSourceTransactionManager, adding JDBC commit/rollback exception translation tailored for Spring JDBC.
- The driver and DBMS must support savepoints; otherwise NESTED may be rejected or behave unexpectedly.
- Ensure `JdbcTemplate`/DAOs use the **exact DataSource** managed by the manager; if code manually opens Connections via `DriverManager` outside the bound transaction, savepoints will not cover those SQL statements.

Before relying on NESTED, you can probe JDBC driver/DBMS capability and run real integration tests:

~~~java
// Snippet reading metadata of a self-opened Connection in a test environment.
// Do not perform operations on a Connection currently managed by Spring.
try (java.sql.Connection c = dataSource.getConnection()) {
    boolean savepoints = c.getMetaData().supportsSavepoints();
    System.out.println("supportsSavepoints=" + savepoints);
}
~~~

This is only an illustrative snippet (requiring a `dataSource` variable); **`supportsSavepoints=true` is a necessary condition, not sufficient** to guarantee every nested snippet works, because manager settings, transaction status, SQL/DDL, and DBMS restrictions still matter.

### 8.2. JpaTransactionManager: Do Not Treat JPA as Savepoint-Aware

**The JPA EntityManager/persistence context does not have nested transaction semantics like JDBC Savepoints.** In Spring, `JpaTransactionManager` interacts with JDBC savepoints yet **`nestedTransactionAllowed` defaults to false**; if specially enabled for JDBC access, savepoints act on the JDBC Connection rather than automatically "rewinding" the entire state of the EntityManager and cached/dirty entities.

Therefore, **do not mechanically port `@Transactional(NESTED)` from JDBC to JPA** expecting all entity state and flushes to roll back like JDBC segments. Investigate your provider, transaction manager, and actual rollback strategy; if unsupported properly, design a single unified transaction or clearly separated workflows.

With **JtaTransactionManager**, do not assume JDBC-local savepoint NESTED support. With **R2DBC/reactive**, savepoint and context capabilities differ by manager/driver/version; check documentation and test on the active R2DBC driver. This demo only proves local Spring JDBC.

### 8.3. The Database/Driver Is Also Part of the Contract

Even with JDBC, rolling back to a savepoint can be restricted by DDL, storage engine transactions, stored procedures, triggers, or post-error transaction state. Some DBMSs have distinct locking and DDL behaviors. H2 helps teach the concept, yet does not replace testing on PostgreSQL/MySQL/Oracle or your production DBMS when using savepoints to protect critical data.

## 9. How Isolation, Timeout, and Read-Only Differ

**NESTED:** remains in the same physical transaction as outer. Therefore, isolation, timeout, and read-only at the transaction/Connection level are usually determined by outer. If inner NESTED declares `Isolation.SERIALIZABLE` while outer already opened `READ_COMMITTED`, do not assume a new physical transaction with its own isolation exists.

**REQUIRES_NEW:** creates a new physical transaction, so it can request its own isolation/timeout/readOnly without inheriting outer's policies verbatim. Example:

~~~java
// Snippet inside an intercepted bean; policy requires driver/DBMS support.
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    timeout = 5,
    readOnly = true
)
public void readIndependentSnapshot() {
    // Runs read-only queries belonging to the inner transaction.
}
~~~

This snippet is not a standalone program. **`readOnly=true` is a hint** whose enforcement depends on the manager/driver/DBMS, not a security layer. Timeout also does not automatically interrupt every HTTP call at exactly 5 seconds. A NESTED scope on the same Connection cannot alter the running physical transaction's isolation solely through an inner annotation.

If an inner `REQUIRED` method joins outer, it likewise normally uses outer's physical transaction attributes despite differing annotation metadata. When you need mismatch validation, look into `validateExistingTransaction=true` on `AbstractPlatformTransactionManager` for your specific environment.

## 10. Rollback Rules, Catching Exceptions, and UnexpectedRollbackException

### 10.1. Only Exceptions Thrown Out of the Transactional Proxy Are Observed by Advice

The two snippets below can yield different outcomes:

~~~java
// Illustration: outer calls another inner bean so nested advice executes.
@Transactional
public void process() {
    try {
        innerService.optionalNestedStep(); // NESTED throws RuntimeException
    } catch (IllegalStateException ex) {
        // Inner interceptor has already rolled back to the savepoint before the error reaches here.
    }
    repository.saveRequiredData();
}
~~~

With valid NESTED/savepoints, outer can commit `repository.saveRequiredData()`. If inner were `REQUIRED` instead of `NESTED`, the inner interceptor could have marked the physical transaction rollback-only; outer attempting to commit leads to `UnexpectedRollbackException`. With `REQUIRES_NEW`, inner rolls back its own transaction and outer can commit normally.

**Exception rules still matter**: by default `@Transactional` rolls back on `RuntimeException`/`Error`; checked `Exception`s do not trigger rollback under common default settings unless configured via `rollbackFor` or a matching default rollback rule. A checked exception from inner NESTED may not roll back to the savepoint by default; explicitly define business exceptions and rollback policies.

### 10.2. What If Outer Does Not Catch the Exception?

With both NESTED and REQUIRES_NEW, a `RuntimeException` from inner **can continue across the outer transactional boundary**. If outer does not catch it, outer also typically rolls back per its own rules. The difference becomes clear when:

- Inner **already committed** under REQUIRES_NEW and outer throws another error later: inner's commit still persists.
- Inner **succeeded** under NESTED and outer throws another error: inner's changes still belong to T1 and are rolled back by outer.

### 10.3. What If Outer Is Already Marked Rollback-Only?

No propagation can restore an outer already marked rollback-only back to normal. A successful NESTED inner still belongs to T1; eventually outer T1 rolls back. A REQUIRES_NEW inner can commit independently if functioning properly, while outer still must roll back.

### 10.4. Catching Inside Inner vs. Catching Outside Inner

If inner catches the error itself and returns normally **without marking rollback-only**, inner's interceptor may treat the method as successful. With NESTED, the savepoint may be released without rolling back. With REQUIRES_NEW, inner may commit. So if an error requires undoing the inner scope, let an appropriate exception exit to the interceptor or call `setRollbackOnly()` on the transaction status via the proper API.

Do not write `catch (Exception ex)` and merely log to "keep going" when business logic actually requires rollback; swallowing exceptions can alter commit outcomes.

## 11. Choosing NESTED vs. REQUIRES_NEW by Business Meaning

### 11.1. NESTED Fits When "Same Final Commit, Yet a Branch May Be Dropped"

Example of saving an order with an optional supplemental notes update:

- Outer transaction creates the order header and order lines.
- Inner NESTED attempts to write secondary data in the same database.
- If inner fails in a way skippable under business policy, roll back to the savepoint; outer still keeps the valid order.
- If outer fails and cannot commit the order, **the secondary data that had succeeded must also be lost**.

NESTED fits when inner's final outcome **must not exist independently** of outer. Even so, verify DB driver and savepoint capability, and do not apply it mechanically to a JPA `EntityManager`.

### 11.2. REQUIRES_NEW Fits When "Inner Has the Right to Commit Even If Outer Fails"

Example of recording an attempt log for processing a task in the same database:

- Outer executes the main task.
- Inner REQUIRES_NEW writes the **"task attempted"** event, requiring the audit record to persist even when outer fails.
- Inner commits first; if outer rolls back, the attempt record can still remain.

However, distinguish an **attempt log** from a **business audit of committed outcome**. If an audit record states "order completed" while outer eventually rolls back, REQUIRES_NEW can produce false records. When an audit must reflect a **committed** transaction, consider after-commit notifications or a transactional outbox in the same DB instead of committing an independent audit.

### 11.3. When Neither Should Be Used

If the business requires **all or nothing together**, the simplest choice is a single outer **REQUIRED** covering all operations, without unnecessary NESTED/REQUIRES_NEW.

If the business must write to two uncoordinated DBs, REQUIRES_NEW on a local transaction manager **does not turn two DBs into an atomic distributed transaction**. Evaluate JTA/XA when resources support it, or use outbox/saga/eventual consistency. NESTED likewise applies only within a single compatible transaction resource; do not use savepoints to roll back sent HTTP requests/emails/messages.

### Selection Process

1. **Should a successful inner stay persisted if outer rolls back?**
   - If **no**: prefer REQUIRED, or NESTED if a separate branch also needs rollback capability.
   - If **yes**: consider REQUIRES_NEW, and review audit/side-effect semantics.
2. **Can a failed inner be skipped so outer still commits?**
   - If **no**: REQUIRED may suffice and is simpler.
   - If **yes**: either NESTED/savepoint or REQUIRES_NEW can work; the distinction lies in **independent inner commit capability**.
3. **Do the transaction manager/driver/DBMS support savepoints?**
   - If not: do not rely on NESTED.
4. **Are pool capacity and lock behavior sufficient for separate connections and transactions?**
   - If not: REQUIRES_NEW can cause waiting/timeouts; revisit the design.
5. **Has it been verified by integration tests on a real DBMS?**
   - If not: do not treat a propagation policy as a business guarantee.

## 12. AOP Proxy Warning: Annotations Do Not Activate on Self-Invocation

In standard proxy mode:

~~~java
// Snippet DOES NOT work as expected when calling this.inner().
@Service
public class WrongService {
    @Transactional
    public void outer() {
        this.inner(); // Direct access, bypasses transaction proxy.
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void inner() {
        // Looks like a separate transaction, but inner's advice may not run.
    }
}
~~~

This is illustrative code requiring imports and context to use. Similarly, `this.innerNested()` does not create a savepoint just because the method has `@Transactional(NESTED)`.

In the complete demo, **OuterService** calls **InnerService**, a separate Spring bean. The call passes through InnerService's proxy so propagation metadata takes effect. Instantiating a class with `new` outside the container, private/final methods, `@Async` thread switches, or calling the wrong bean can also produce unexpected outcomes.

**Debug before concluding "NESTED does not work":** verify the method was actually intercepted by Spring, check which manager is active, verify the DataSource, and confirm whether an outer transaction already existed.

## 13. Diagnostics and Testing

| Symptom | Possible Cause | What to Check |
| --- | --- | --- |
| `@Transactional(NESTED)` reports unsupported | Manager lacks savepoint support, driver/DBMS lacks support, `nestedTransactionAllowed=false` | Check manager, driver `supportsSavepoints()`, real savepoint test |
| Inner NESTED succeeds yet outer rollback loses inner too | **Correct semantics:** same physical transaction | Switch requirement to REQUIRES_NEW only if independent commit is truly needed |
| Inner REQUIRES_NEW commits then outer rollback leaves inner intact | **Correct semantics:** independent T2 | Confirm business actually wants this data to persist independently |
| Inner REQUIRES_NEW hangs/times out | Pool exhaustion; T2 waits on lock held by T1 | Pool active/idle/pending, DB locks, transaction duration |
| NESTED inner exception caught yet outer still rolls back | Broken DB transaction, other rollback-only, inner did not roll back savepoint, or error exited outer | Enable transaction debug, inspect exceptions/rollback-only and DB state |
| NESTED on JPA fails or entity state does not revert | `JpaTransactionManager` does not guarantee savepoints for `EntityManager` state | Do not treat NESTED as JPA nested semantics; test with provider |
| No log of creating savepoint or suspending | Self-invocation, transaction management not enabled, wrong manager, call bypassed proxy | Check AOP proxy, `@EnableTransactionManagement`, bean naming |
| Inner REQUIRES_NEW does not see outer's uncommitted data as expected | T2 is independent and does not share T1's uncommitted state | DB isolation, flush/commit timing, data-passing protocol |
| NESTED has its own method yet multiple commits still occur | Other top-level calls or different DataSource/manager | Compare JDBC Connection identity and transaction owner |
| Failure in outer after inner NESTED returned "success" | Savepoint finished, outer still decides final outcome | Inspect outer exception and rollback rules |
| `UnexpectedRollbackException` when inner REQUIRED fails | Inner REQUIRED marked shared transaction rollback-only, not NESTED savepoint | Compare actual annotations, proxies, and transaction status |

**A good integration test** must cover these cases:

1. Outer + inner NESTED: inner throws, outer catches and commits → outer kept, inner lost.
2. Outer + inner NESTED: inner succeeds, outer rolls back → **both lost**.
3. Outer + inner REQUIRES_NEW: inner succeeds, outer rolls back → **inner kept**.
4. Outer + inner REQUIRES_NEW: inner throws, outer catches and commits → **outer kept, inner lost**.
5. Inner called with no outer: confirm the method still creates an appropriate transaction.
6. Test savepoint capability errors and connection pool behavior if the application depends on those features.

When using Spring TestContext with a `@Transactional`-annotated test, the test framework can roll back at the end, skewing observations of physical commits. Use explicit test boundaries and independent connections/transactions for re-reading; the Java `main` program above avoids this confound by calling through beans and querying after each transaction.

## 14. Self-Check Questions

**Question 1.** Does NESTED open a new physical transaction when outer already has a transaction?  
**Answer:** Usually not with a local JDBC manager; it uses a savepoint inside the same physical transaction.

**Question 2.** Inner NESTED returned successfully. Outer rolls back. Does inner's data remain?  
**Answer:** No; inner still belongs to the outer physical transaction and has no independent commit.

**Question 3.** Inner REQUIRES_NEW committed. Outer rolls back. What happens to inner's data?  
**Answer:** Inner's commit can still persist because inner's own physical transaction has completed.

**Question 4.** Inner NESTED rolls back to savepoint, outer catches the error and continues. Can outer commit work before/after the savepoint?  
**Answer:** Yes, provided the manager/DBMS supports it and the physical transaction remains valid; changes after the savepoint that were rolled back are not kept.

**Question 5.** Is REQUIRES_NEW always safer than NESTED?  
**Answer:** No. It has independent commit semantics and usually requires an extra connection; it can cause pool exhaustion, lock waits, and inconsistent business state if misused.

**Question 6.** Why can't JPA `EntityManager` automatically use NESTED like JDBC?  
**Answer:** JDBC savepoints do not fully control JPA persistence context state. `JpaTransactionManager` has `nestedTransactionAllowed` disabled by default and requires understanding provider limits.

**Question 7.** If there is no outer transaction, what does a NESTED method do?  
**Answer:** A compatible manager creates a new transaction; a savepoint cannot be created inside a nonexistent transaction.

**Question 8.** Why might calling `this.inner()` annotated with `@Transactional(REQUIRES_NEW)` fail to open T2?  
**Answer:** In proxy mode, self-invocation bypasses the Spring transaction proxy, so propagation advice may not execute.

**Question 9.** A system needs to write an "order committed" audit even though outer might roll back. Should REQUIRES_NEW be used to write the audit before outer commits?  
**Answer:** Be very careful; it can write a false audit if outer rolls back. Consider after-commit hooks or a transactional outbox reflecting the true business outcome.

**Question 10.** Why can both NESTED and REQUIRES_NEW leave A=10, B=0, C=10 when inner fails and outer catches?  
**Answer:** The two inner rollback mechanisms differ, yet the final state in that scenario is identical. You must add the inner-success/outer-rollback scenario to tell them apart: NESTED loses inner, whereas REQUIRES_NEW keeps committed inner.

## 15. Brief Summary

- **NESTED = one physical transaction + JDBC savepoint + partial rollback; outer decides the final commit.**
- **REQUIRES_NEW = independent new transaction + suspend outer + separate commit/rollback; outer rollback does not undo committed inner.**
- NESTED fits a DB branch that can be dropped while still sharing outer's fate; REQUIRES_NEW fits only when a truly independent inner commit is needed.
- REQUIRES_NEW generally adds pressure on the connection pool and can be blocked by outer's locks; NESTED depends on driver/DBMS savepoint capability.
- With JPA, do not assume the persistence context shares JDBC savepoint nested semantics.
- Ensure methods are called through a Spring proxy with the right TransactionManager/DataSource and rollback rules.
- Always test all four commit/rollback scenarios on a real database for critical business flows; **annotations state intent, while post-transaction data proves the outcome**.

## References

- [Spring Framework — Transaction Propagation: REQUIRES_NEW and NESTED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — DataSourceTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html)
- [Spring Framework — JdbcTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html)
- [Spring Framework — JpaTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/orm/jpa/JpaTransactionManager.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Controlling Database Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Java SE 17 — Connection, Savepoint API](https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Connection.html)
