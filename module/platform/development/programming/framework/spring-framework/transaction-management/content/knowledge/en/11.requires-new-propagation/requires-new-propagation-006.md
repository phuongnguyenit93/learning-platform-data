# Risk of Connection Pool Exhaustion or Lock Waits When Using REQUIRES_NEW

> **Spring Framework — Transaction Management -> REQUIRES_NEW.** Why can a `@Transactional(propagation = Propagation.REQUIRES_NEW)` call cause an application to stall, run out of connections, time out, or be blocked by the outer transaction itself? This lesson explains two distinct risk groups: **pool exhaustion because the outer transaction still holds a connection** and **lock waits because the outer transaction still holds database locks**. It also covers pool sizing, diagnosing symptoms, and redesigning transaction boundaries.

## 1. Core Principle: Suspend Does Not Mean Resources Are Released

`Propagation.REQUIRES_NEW` requires **an independent physical transaction** every time the method is intercepted by Spring's transaction infrastructure, even if the caller is already inside a transaction.

When a method `outer()` holds transaction T1 and calls `inner()` with `REQUIRES_NEW`:

1. Spring suspends outer's transaction context on the current thread.
2. **The connection/resources attached to T1 remain owned by T1** and are not returned to the pool merely because the Java call stack temporarily moves into inner.
3. Inner must start transaction T2 with its own resources, typically **another JDBC connection** from the same pool.
4. T2 commits or rolls back independently; T2's connection is returned to the pool once the manager finishes and cleans up.
5. Spring resumes T1's transaction context; only then does outer continue and eventually commit or roll back T1.

This does not mean the database supports a "SUSPEND TRANSACTION command" that releases all locks. Spring mainly **suspends the association between the transaction/resources and the execution context**, while physical T1 remains open.

```text
Same thread, one DataSource + connection pool

outer()  @Transactional(REQUIRED)
  |
  |-- acquire Connection A from pool
  |-- BEGIN T1; write data; may hold locks
  |
  +-- inner() @Transactional(REQUIRES_NEW)
  |      |
  |      |-- suspend T1 context, DO NOT return A to pool
  |      |-- request Connection B from the same pool
  |      |      |
  |      |      +-- B available --> BEGIN T2 --> commit/rollback --> return B
  |      |      |
  |      |      +-- pool exhausted --> WAIT --> connection timeout / failure
  |      |
  |      +-- restore T1 context
  |
  +-- outer continues with A
  +-- commit/roll back T1 --> return A to pool
```

**Remember one sentence:** During a `REQUIRES_NEW` call, the outer transaction can **still hold both a connection and locks**, while inner needs an additional connection and can be blocked by outer's locks. These are two **independent** bottlenecks: enlarging the pool only addresses connection shortages and cannot unlock database locks.

Spring documentation states explicitly: only use `PROPAGATION_REQUIRES_NEW` when the connection pool is sized appropriately, with at least greater capacity than the number of concurrent threads holding outer transaction connections; otherwise pool exhaustion and resource-wait deadlocks can occur. Detailed sizing must factor in both application demand and the DBMS.

## 2. Distinguishing Three Types of "Waiting" States

| Phenomenon | Waiting on which resource? | Where is the resource? | Common symptoms | Is increasing pool size enough? |
| --- | --- | --- | --- | --- |
| **Pool starvation / pool exhaustion** | An unavailable connection | HikariCP / application pool layer | `active == maximumPoolSize`, `idle = 0`, threads awaiting connection; followed by connection acquisition timeout | Can help if DB handles the connections and no other bottleneck exists |
| **Database lock wait** | Row/table/index/key-range/advisory lock | Database engine | Inner query already has a connection yet waits on a lock, lock timeout / deadlock / statement timeout | **No**. The second connection is already acquired, yet outer has not released the lock |
| **Thread starvation or general queueing** | Worker threads, executor slots, CPU, or request capacity | Application / server runtime | Rising request latency, long queues, high/low CPU depending on cause | Not necessarily; must diagnose the real bottleneck |

The same outward symptom of a "hung request" does not prove the same root cause. Look at the sequence:

```text
Borrow connection
  |
  +-- Waiting at pool / getConnection()
  |     => Pool starvation
  |
  v
Connection granted, execute SQL
  |
  +-- Waiting at database lock manager
  |     => Lock wait / lock timeout / deadlock
  |
  v
SQL completes
  |
  +-- Waiting on commit / log / network / replication / I/O
        => Another kind of bottleneck
```

Analyze metrics and stack traces to know which step is stalling. Multiple problems can occur together: outer holds connection A, inner acquires B and waits on a row lock; while waiting, both A **and** B occupy pool slots, causing other requests to wait for connections as well.

## 3. Why Does REQUIRES_NEW Acquire an Extra Physical Connection?

### 3.1. Independent Transactions Need Independent Commit/Rollback Boundaries

Example service writing an order and an audit record:

```java
@Service
class OrderService {
    private final AuditService audit;

    OrderService(AuditService audit) {
        this.audit = audit;
    }

    @Transactional // REQUIRED
    public void placeOrder() {
        // Write order table in transaction T1.
        audit.logAttempt(); // Call through injected Spring bean proxy.
        // T1 can commit/roll back after audit has finished.
    }
}

@Service
class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void logAttempt() {
        // Write audit in independent T2.
    }
}
```

This is an **illustrative fragment**, not standalone runnable code: imports, repositories/JDBC, and Spring configuration are omitted. T1 and T2 can have different outcomes:

- T2 commits, then T1 rolls back: the audit record remains (barring other errors).
- T2 rolls back, yet T1 can still commit if outer handles the error appropriately and is not marked rollback-only.
- T2 needs an independent connection to commit before T1 ends. With JDBC local transactions on the same datasource, you cannot take connection A already running transaction T1, tell it to run an independent transaction T2, and return to T1 as if nothing happened.

### 3.2. What Does Spring Actually "Suspend"?

With an imperative `PlatformTransactionManager` and implementations like `JdbcTransactionManager`/`DataSourceTransactionManager`, Spring temporarily detaches T1's resource holder and transaction synchronizations from the thread, then binds T2's resources. Once T2 finishes, T1's state is restored.

**Do not equate Spring's suspend with releasing database locks.** On standard databases, locks owned by transaction T1 are only released according to database semantics: commit, rollback, or specific savepoint/lock operations or provider behaviors. Switching the Java thread to T2 **does not terminate T1**.

### 3.3. Does Every REQUIRES_NEW Always Take Two Connections?

Do not state this as an absolute rule across all managers and situations. In the **JDBC local transaction, single pool, outer already borrowed physical connection** model, inner `REQUIRES_NEW` generally needs an extra concurrent connection. Exceptions exist:

- Outer has not yet borrowed a physical connection thanks to `LazyConnectionDataSourceProxy` or other lazy acquisition.
- Inner uses a different datasource or pool; pressure shifts to inner's pool rather than outer's pool.
- JPA's JDBC connection acquisition/release timing depends on the provider and transaction settings.
- JTA has its own enlistment/suspension mechanics.
- R2DBC uses `ConnectionFactory` and reactive context, so metrics are not interpreted directly as a JDBC pool.

**The count of "outer transactions" does not always equal active connections.** Sizing must be based on actual physical connection usage, the transaction manager, and how operations execute.

## 4. Simplest Pool Exhaustion Scenario: One Thread, Pool Size = 1

Suppose the pool only lends **one** JDBC connection:

```text
Pool: maximumPoolSize = 1

Thread-1:
  outer T1 --> borrow A                         [Pool 1/1 active]
     |
     +--> inner REQUIRES_NEW --> wants B        [Pool 1/1 active]
              |
              +--> B unavailable
              +--> waits for connectionTimeout
              |
     outer cannot commit/roll back T1
     until inner returns control

Pool cannot grant B because A is still held by T1
=> Inner timeout / CannotCreateTransactionException
```

This is **pool starvation within the same call stack**, requiring neither multiple threads nor database locks. Inner typically never even enters its method body: the failure happens **before** Spring invokes inner's business method, when the transaction manager tries to start T2 and borrow a connection.

With HikariCP, the borrow waits up to `connectionTimeout`. If no connection becomes available, Hikari throws `SQLException`; Spring's JDBC transaction manager typically translates it into `CannotCreateTransactionException`. The exception propagates to outer. If outer does not catch it, the default rollback rule for runtime exceptions rolls back T1 and returns A to the pool.

**Common misconception:** increasing `connectionTimeout` from 2 seconds to 30 seconds does not create an extra connection. In the single-thread scenario above, A is never released while inner has not finished; it only prolongs the wait. A sensible timeout surfaces failures clearly rather than solving capacity shortages.

### Wait Cycle Across Multiple Threads

Suppose 8 concurrent requests each open an outer transaction on the same pool of size 8, and all call an inner `REQUIRES_NEW`:

```text
Pool maximum = 8

Thread 1: outer holds A1 --> needs B1
Thread 2: outer holds A2 --> needs B2
Thread 3: outer holds A3 --> needs B3
...
Thread 8: outer holds A8 --> needs B8

Pool: 8/8 connections held by outer
      0 connections left for inner

All threads waiting; no thread advances
outer to release A1..A8
=> wait cycle / starvation pool deadlock
=> connectionTimeout after a delay
```

In practice, some requests may finish earlier or the pool may have idle connections, so the failure does not occur on every run. That is why this issue often **appears only as concurrency rises**, hard to reproduce in dev yet erupting under production load.

## 5. Sizing the Connection Pool: Avoid Mechanical Formulas

### 5.1. Threshold to Avoid Wait Cycles

Spring warns: the pool should be **larger than the number of concurrent threads** that can hold outer transaction connections, by **at least one connection** for inner. If N threads each already occupy an outer connection, a pool size equal to N blocks every inner call. N+1 allows **one** inner to proceed, commit, and return its connection, giving others a turn one by one.

Example:

| Outer transactions holding connections | Pool size | Connections left for inner | Meaning |
| ---: | ---: | ---: | --- |
| 1 | 1 | 0 | Inner `REQUIRES_NEW` cannot start until a connection frees; same thread stalls on itself |
| 8 | 8 | 0 | If all 8 require inner at once, all can wait until timeout |
| 8 | 9 | 1 | At least one connection lets an inner advance, if there are no other borrowers |
| 8 | 16 | 8 | Room for 8 concurrent inners, **if the DB can handle it** and there is no other demand |

**N+1 is not a general optimal sizing.** It is a condition for avoiding a specific wait cycle—not a promise of good latency, nor enough capacity for retries, multi-level `REQUIRES_NEW`, other threads, scheduled jobs, or health checks.

### 5.2. Capacity Model Based on Workload

An approximate peak-load model:

```text
required_concurrent_connections
  ~= outer connections still held
   + concurrent REQUIRES_NEW connections
   + connections for other work sharing the same pool
   + reasonable safety margin
```

Suppose 12 concurrent requests each hold 1 outer connection and may invoke an inner transaction simultaneously:

```text
Outer held:                     12
Max concurrent inner:           12
Other queries/background work:   3
-------------------------------
Illustrative peak demand:       27+
```

This figure is **only an illustrative capacity calculation**, not a default recommendation to set the pool to 27. You must check database connection limits, TPS/latency, connection hold times, request spikes, and other workloads. Too large a pool can overload the database via CPU, I/O, lock, and memory contention.

With a chain `outer -> innerA(REQUIRES_NEW) -> innerB(REQUIRES_NEW)`, one thread can hold multiple transaction resources simultaneously, pushing peak demand past the "max 2 connections per thread" model. Audit the entire call graph, not just one annotation.

### 5.3. Use Measurements Instead of Counting Request Threads Alone

HikariCP exposes helpful metrics:

- `ActiveConnections`: connections currently leased out.
- `IdleConnections`: connections currently ready in the pool.
- `TotalConnections`: total connections managed by the pool.
- `ThreadsAwaitingConnection`: threads currently waiting to borrow a connection.
- Acquisition time, timeout counts, wait durations; typically integrated via Micrometer/Actuator/JMX depending on setup.

Do not look only at `maximumPoolSize`. A pool of 20 with sustained `active=20`, `idle=0`, `awaiting=30` during requests calling inner `REQUIRES_NEW` is a clear sign of capacity contention. Inspect query latency and DB locks in parallel, because an inner call blocked on a DB lock also holds connection B for a long time, draining the pool in a chain reaction.

## 6. Second Scenario: Inner Gets a Connection Yet Waits on Outer's Lock

Having a second connection available **does not** guarantee transaction T2 can run. If T1 already locked the data T2 needs:

```text
Connection A / T1 (outer):
    UPDATE accounts SET balance = balance - 100 WHERE id = 42;
    [T1 holds exclusive lock on row id=42]
                       |
                       | outer calls inner REQUIRES_NEW
                       v
Connection B / T2 (inner):
    UPDATE accounts SET status = 'VERIFIED' WHERE id = 42;
    [T2 waits for exclusive lock held by T1]
                       |
                       v
    T1 can only commit after inner returns control
    T2 can only proceed after T1 releases the lock

=> Wait cycle, lock timeout, or deadlock detection
```

In this single-thread synchronous scenario, T1 is "suspended" on the Java call stack yet **still open in the DB**. T1 cannot commit or roll back to release the lock until inner completes. T2 waits on the lock held by T1, so they block each other by causal dependency.

Depending on the DBMS, the lock manager may detect a deadlock and pick a victim, or T2's SQL waits until exceeding `lock_timeout`/`statement_timeout` and throws an exception. Not every engine reports an error literally named "deadlock" for this wait pattern; **lock timeout** is a very common outcome.

### Distinguishing from Connection Exhaustion

| Did pool grant inner connection B? | Did inner's SQL start? | Primary cause |
| --- | --- | --- |
| Not yet | Not yet | Waiting on pool |
| Yes | Yes, waiting on lock | Database lock wait |
| Yes | Yes, heavy CPU/I/O query | Slow query or other DB bottleneck |

Raising `maximumPoolSize` from 2 to 100 **does not release T1's lock**. On the contrary, it can allow even more inner transactions to get stuck simultaneously holding extra connections, widening the blast radius.

### "Inner Already Committed So Outer Sees New Data" Is Not Absolute Either

Even after T2 commits independently, T1 may still be using an older snapshot/isolation view or a JPA persistence context; it will not necessarily see T2's changes immediately. Conversely, T2 may **not see T1's uncommitted changes**, so logic like "read the order just inserted by outer and update an audit tied to that order" can fail or block on locks/foreign keys because the order is not committed yet.

Analyze isolation, MVCC snapshots, foreign-key locks, and caches/persistence contexts, not just connection counts.

## 7. A Design Mistake Example and How to Redirect It

### 7.1. Design Prone to Lock Waits

```java
@Service
class BookingService {
    private final BookingRepository bookingRepository;
    private final StatusService statusService;

    @Transactional
    public void reserve(long bookingId) {
        bookingRepository.markReserved(bookingId); // T1 locks row
        statusService.verify(bookingId);           // T2 needs same row
        // T1 does not finish until verify() returns.
    }
}

@Service
class StatusService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void verify(long bookingId) {
        bookingRepository.markVerified(bookingId);
    }
}
```

This is a **structural fragment**, not standalone compilable code; constructors/imports/repositories are omitted. Calling `markReserved` in outer and `markVerified` in inner on the same row easily creates a lock wait, even though both methods use the same database.

### 7.2. If Both Steps Must Roll Back Together: Use REQUIRED

If updating "reserved" and "verified" must be atomic in one transaction, choose one `REQUIRED` boundary (inner also `REQUIRED` or without its own boundary) so both operate in T1. Inside the same transaction, there is no T2 competing with T1's lock merely due to `REQUIRES_NEW`.

```java
@Transactional
public void reserveAndVerify(long bookingId) {
    bookingRepository.markReserved(bookingId);
    bookingRepository.markVerified(bookingId);
}
```

This is a fragment. Statements can still be blocked by **other transactions**; `REQUIRED` does not eliminate all contention. However, it eliminates the issue of "an independent inner in the same call stack waiting on a lock held by outer" in the illustrated case.

### 7.3. If Both Steps Need Independent Commits: Move the Boundary

If the verify step genuinely needs an independent transaction, consider moving it **after outer commits**:

```text
T1: reserve booking --> commit, release locks
                      |
                      v
T2: verify booking --> independent commit
```

Splitting introduces a time window between the two states, requiring retries, idempotency, and intermediate-failure handling. If the requirement is reliably recording an event after the business transaction commits, a transactional outbox inside T1 paired with a publishing worker is a common option.

**Do not reflexively slap `REQUIRES_NEW` on every audit/log requirement.** Auditing may need independence for legal or business reasons, yet the design must account for pools, lock ordering, data visibility, and retryability.

## 8. Runnable Java 17+ Example: Pool Size 1 Fails, Pool Size 2 Succeeds

The example below demonstrates **pool exhaustion** using Spring Framework 6.2.x + `JdbcTransactionManager` + HikariCP 5.1.0 + in-memory H2. No Spring Boot or external DB server is needed.

Both scenarios run in the same program, sequentially creating a Spring context with pools of 1 and 2 connections:

- Outer `@Transactional` writes to `outer_events`, holding connection A.
- Inner `@Transactional(REQUIRES_NEW)` writes to `audit_events`; needs an independent connection B.
- When inner runs, outer **intentionally throws an exception** to roll back. With pool 2, inner already committed so the audit persists.
- With pool 1, inner cannot borrow B within `connectionTimeout`, failing **before inner SQL runs**; outer rolls back.

Using **two separate tables** avoids self-inflicted lock conflicts: this example illustrates pool exhaustion independently from the database locking problem in Section 6.

### 8.1. Project Structure

```text
requires-new-pool-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── dev/
                └── learning/
                    └── RequiresNewPoolDemo.java
```

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>dev.learning</groupId>
    <artifactId>requires-new-pool-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>com.zaxxer</groupId>
            <artifactId>HikariCP</artifactId>
            <version>5.1.0</version>
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
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>dev.learning.RequiresNewPoolDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 8.2. Create `src/main/java/dev/learning/RequiresNewPoolDemo.java`

```java
package dev.learning;

import javax.sql.DataSource;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

public final class RequiresNewPoolDemo {

    // A dedicated settings bean so both scenarios share Config
    // without mutating global static state or system properties.
    public record DemoSettings(int poolSize) {}

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement
    public static class Config {

        @Bean(destroyMethod = "close")
        HikariDataSource dataSource(DemoSettings settings) {
            HikariConfig cfg = new HikariConfig();
            cfg.setJdbcUrl(
                    "jdbc:h2:mem:pool_" + settings.poolSize()
                            + ";DB_CLOSE_DELAY=-1");
            cfg.setUsername("sa");
            cfg.setPassword("");
            cfg.setMaximumPoolSize(settings.poolSize());
            cfg.setMinimumIdle(settings.poolSize());

            // Let inner wait at most 2 seconds when the pool is exhausted.
            // Increasing the timeout cannot cure a same-thread wait cycle.
            cfg.setConnectionTimeout(2_000);
            return new HikariDataSource(cfg);
        }

        @Bean
        JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }

        @Bean
        AuditService auditService(JdbcTemplate jdbc) {
            return new AuditService(jdbc);
        }

        @Bean
        OrderService orderService(JdbcTemplate jdbc, AuditService audit) {
            return new OrderService(jdbc, audit);
        }
    }

    public static class AuditService {
        private final JdbcTemplate jdbc;

        public AuditService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRES_NEW)
        public void writeAudit() {
            jdbc.update(
                    "INSERT INTO audit_events(id, description) "
                            + "VALUES (?, ?)",
                    2, "inner committed");
        }
    }

    public static class OrderService {
        private final JdbcTemplate jdbc;
        private final AuditService audit;

        public OrderService(JdbcTemplate jdbc, AuditService audit) {
            this.jdbc = jdbc;
            this.audit = audit;
        }

        @Transactional
        public void placeOrderThenFail() {
            jdbc.update(
                    "INSERT INTO outer_events(id, description) "
                            + "VALUES (?, ?)",
                    1, "outer rolled back");

            // Needs a second connection from the same pool.
            // AuditService's Spring proxy applies REQUIRES_NEW.
            audit.writeAudit();

            // With pool=2, audit already committed; outer can still roll back.
            throw new IllegalStateException("outer failed");
        }
    }

    private static int count(JdbcTemplate jdbc, String table) {
        return jdbc.queryForObject(
                "SELECT COUNT(*) FROM " + table,
                Integer.class);
    }

    private static void runScenario(int poolSize) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Register settings before refreshing the context.
            context.registerBean(
                    DemoSettings.class,
                    () -> new DemoSettings(poolSize));
            context.register(Config.class);
            context.refresh();

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                    "CREATE TABLE outer_events "
                            + "(id INT PRIMARY KEY, description VARCHAR(80))");
            jdbc.execute(
                    "CREATE TABLE audit_events "
                            + "(id INT PRIMARY KEY, description VARCHAR(80))");

            String failureType = "none";
            try {
                // Obtain Spring bean proxy; do not instantiate OrderService with new.
                context.getBean(OrderService.class)
                        .placeOrderThenFail();
            } catch (RuntimeException ex) {
                failureType = ex.getClass().getSimpleName();
            }

            System.out.println(
                    "pool=" + poolSize + " failure=" + failureType);
            System.out.println(
                    "pool=" + poolSize
                            + " outer=" + count(jdbc, "outer_events")
                            + " audit=" + count(jdbc, "audit_events"));
        }
    }

    public static void main(String[] args) {
        runScenario(1);
        runScenario(2);
    }
}
```

### 8.3. Run the Demo

Requires **JDK 17+**, **Maven 3.x**, and Internet on first run to fetch dependencies. Inside `requires-new-pool-demo`:

```bash
mvn -q clean compile exec:java
```

**Lines printed by the program** with the dependencies/configuration above, excluding logging that may appear from Maven, Spring, HikariCP, or SLF4J:

```text
pool=1 failure=CannotCreateTransactionException
pool=1 outer=0 audit=0
pool=2 failure=IllegalStateException
pool=2 outer=0 audit=1
```

**Interpreting the output:**

1. **Pool 1:** Outer T1 took the sole connection and wrote `outer_events`. Spring attempts to start T2 for `AuditService.writeAudit()`, but no second connection is available. After `connectionTimeout`, HikariCP reports it cannot supply a connection; `JdbcTransactionManager` wraps the transaction-creation failure as `CannotCreateTransactionException`. The outer transaction rolls back due to the exception; neither table has any rows. Inner's body **never executed**, so `audit=0`.
2. **Pool 2:** Outer T1 holds connection A; inner T2 acquires connection B. Two distinct tables avoid self-induced row-lock contention in this scenario. T2 writes the audit, commits, and returns B to the pool. Outer then intentionally throws `IllegalStateException`, rolling back T1. The independently committed audit row remains: `outer=0 audit=1`.
3. The two contexts use different in-memory H2 databases (`pool_1`, `pool_2`), preventing data from the first run from affecting the second.
4. When `runScenario()` exits, Spring closes the context and corresponding Hikari datasource; connection pools are not left open indefinitely.

**Why is this example more useful than merely increasing the pool?** It also demonstrates the independent semantics of `REQUIRES_NEW`. Sizing the pool properly lets inner run, yet **does not make T1 and T2 a single atomic transaction**. If an application demands "audit exists only if order commits", the pool=2 case also proves the business design is wrong: the audit committed before the order rolled back.

### 8.4. Further Self-Checks with Intentional Changes

**Experiment A — Change inner to `REQUIRED`.** On the same JDBC datasource, inner joins outer's connection/transaction; pool size 1 can run the call chain (assuming no other connection demand), and when outer throws an exception both writes roll back: `outer=0 audit=0`. Thus the need for a second connection is tied directly to `REQUIRES_NEW`.

**Experiment B — Remove the exception in outer.** With pool size 2, both T1 and T2 commit and both tables have one record. With pool size 1, inner still lacks a second connection so the flow still fails.

**Experiment C — Keep pool size 2, but make both transactions update the same row.** When T1 holds a lock and T2 needs that row, inner can wait on the lock / time out even though the pool has a spare connection. This is a **different** problem from pool starvation; configure a short DB lock timeout in a test environment and never deploy wait-inducing code to production.

**Experiment D — Make pool size large enough, then simulate many concurrent outer calls.** Use concurrency tests with timeouts and bounded thread counts; monitor active/idle/pending metrics and connection acquisition latency. Never run unbounded load tests against a production DB.

## 9. Row-Lock Wait Scenario: Fragment for an Integration Test

To reproduce a lock wait specifically, you need **two real connections** and a row that already exists before the transactions start:

```sql
CREATE TABLE accounts (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL,
    verified BOOLEAN NOT NULL
);

INSERT INTO accounts(id, balance, verified)
VALUES (42, 1000, FALSE);
```

Hypothetical transaction flow:

```java
// Inside Spring bean OuterService.
@Transactional
public void outer() {
    jdbc.update(
            "UPDATE accounts SET balance = balance - 100 WHERE id = ?",
            42L);                         // T1 locks row 42.

    innerService.verifySameAccount();     // T2 needs row 42.
    // T1 can only finish after the inner call returns.
}

// Inside another bean InnerService; called through Spring proxy.
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void verifySameAccount() {
    jdbc.update(
            "UPDATE accounts SET verified = TRUE WHERE id = ?",
            42L);                         // T2 waits on T1's lock.
}
```

This is a **fragment, not a standalone program**, omitting imports, beans, DB setup, and timeout guards. It illustrates a flow that can be **blocked by the outer transaction itself**.

When testing in a sandbox/test DB, set a short database lock timeout and fail the test if exceeded. H2 supports `LOCK_TIMEOUT`; PostgreSQL has `lock_timeout` and `statement_timeout`; MySQL InnoDB has `innodb_lock_wait_timeout`. Scope and semantics vary across DBMS engines; consult driver and DBMS documentation before applying.

**Do not put unbounded lock-wait examples in automated test suites.** They can tie up connections and worker threads and hang CI pipelines.

### Locks Beyond "Same Row" Also Cause Waits

Real-world situations are more complex than one UPDATE:

- T1 inserts an uncommitted parent record, and T2 inserts a child record requiring a foreign-key check against the parent.
- T1 updates a unique/index entry, and T2 inserts or updates a related key.
- T1 uses `SELECT ... FOR UPDATE`/pessimistic locking, and T2 also needs that row/range.
- T1 holds a table lock/DDL lock or advisory lock needed by T2.
- T2 reads T1's uncommitted data under an isolation level disallowing dirty reads and sees stale data, sees nothing, or waits depending on the DBMS/operation.
- T1 used a JPA `EntityManager` without flushing; T2 on another connection does not automatically see changes still sitting in the persistence context.

Thus **"inner writes to a different table" does not always guarantee zero lock contention**. Foreign keys, indexes, triggers, and relationships can create indirect conflicts.

## 10. Four Anti-Patterns That Sharply Increase Risk

### 10.1. Overly Long Outer Transaction

```java
@Transactional
public void fulfillOrder() {
    repository.save(order);

    callExternalHttpService();  // Slow or times out.
    generateLargeReport();      // Heavy CPU/I/O.
    auditService.writeInRequiresNewTransaction();
}
```

Illustrative fragment. Outer can hold connections and locks while waiting on HTTP or CPU, and then hold them even longer once inner starts. Try to enclose only operations genuinely needing atomicity inside the transaction; move independent I/O outside transaction boundaries when appropriate.

### 10.2. Inner REQUIRES_NEW Also Doing Slow Work

If inner makes HTTP calls, processes files, or runs heavy queries while holding connection B, it extends both the time outer holds A and the time inner holds B. Pool demand nearly doubles for that single request during that window.

**Strategy:** keep inner strictly to short, predictable DB work that genuinely needs independent commit; avoid long-running operations in both T1 and T2.

### 10.3. Multiple Nested Layers of REQUIRES_NEW

```text
A @Transactional(REQUIRED)             -> holds conn 1
  B @Transactional(REQUIRES_NEW)        -> holds conn 2, suspends A
    C @Transactional(REQUIRES_NEW)      -> needs conn 3, suspends B
      D @Transactional(REQUIRES_NEW)    -> needs conn 4, suspends C
```

Connections accumulate across multiple scopes on the same call stack. A pool sized for "outer + 1 inner" can still exhaust if deep `REQUIRES_NEW` chains occur. Especially dangerous when a shared audit/metrics helper accidentally carries `REQUIRES_NEW` and gets called from multiple layers.

### 10.4. Catching Connection-Exhaustion Errors and Committing Outer Anyway

```java
@Transactional
public void placeOrder() {
    repository.save(order);

    try {
        auditService.writeInRequiresNewTransaction();
    } catch (RuntimeException ignored) {
        // May swallow connection-acquisition or severe DB failures.
    }

    // Outer may complete normally and commit,
    // leaving the audit silently missing.
}
```

Illustrative fragment. If writing the audit is mandatory, **do not silently ignore failures**. Decide explicitly: roll back outer, record into an outbox for retry, or report a controlled partial failure. Furthermore, some DB errors may already mark a transaction rollback-only, so catching the exception does not guarantee commit succeeds.

## 11. Risk-Mitigation Options — Choose by Business Requirement

| Option | When to use | Benefits | Trade-offs / limitations |
| --- | --- | --- | --- |
| **Switch inner to `REQUIRED`** | Writes must commit/roll back together | Same physical transaction, usually no connection B for same datasource; avoids T1/T2 lock self-contention | Inner no longer commits independently; inner rollback-only can affect outer |
| **Keep `REQUIRES_NEW`, size pool from load** | Inner truly needs independent commit | Reduces connection-borrow failures if DB has capacity | Does not fix lock contention; consumes more DB connections |
| **Shorten outer transaction** | Outer wraps HTTP/CPU or steps not needing atomicity | Cuts hold time for A and locks | Requires redesigning boundaries and handling inter-step errors |
| **Move inner after outer commit** | Inner should run after a successful commit | T1 releases locks before T2; A and B not held together on same stack | Window between commits; requires retries/idempotency |
| **Transactional outbox** | Must guarantee event/side effect is recorded with business data | Outbox record commits in T1; publisher dispatches later | Adds worker, retries, duplicate handling/idempotent consumers |
| **`NESTED` / savepoint** | Need partial rollback inside one JDBC physical transaction | Usually avoids a second connection B, avoids independent commit | Depends on JDBC savepoint/manager support; inner does not commit independently |
| **Separate pools/datasources** | Resources are genuinely independent with clear separation rationale | Prevents one workload from exhausting the entire shared pool | Does not remove lock contention if pointing at same DB/row; operational complexity |
| **Concurrency limits / bulkheads** | Traffic spikes trigger many concurrent outer+inner calls | Reduces request pressure and bounds tail latency | Needs timeouts/backpressure, may cap throughput |
| **Optimize SQL/indexes/lock order** | Inner gets a connection yet waits on DB locks | Shortens lock duration and reduces contention | Requires execution-plan and data-access pattern analysis |

**Do not use `REQUIRES_NEW` as a "patch" for every rollback-only issue.** It creates an independent transaction, yet alters both commit/rollback semantics and resource usage.

### What Conditions Apply When Moving Inner After Commit?

If inner should only run when T1 succeeds, you can use post-commit events, task queues, or an outbox. Keep in mind that some transaction synchronization callbacks fire after commit while resource bindings may not be fully cleaned up yet; a new DB write inside a callback requires an **appropriate new transaction**, rather than assuming JDBC calls there auto-commit. For high reliability, transactional outbox + idempotent consumers is sturdier than in-memory event listeners alone.

If inner must record an audit **even when outer rolls back**, that is a different requirement: moving it after commit no longer meets the goal. In that case, consider an independent transaction while avoiding rows locked by outer, bounding durations/connections, or using an external failure-logging mechanism.

## 12. Diagnosing Production Issues in Order

### 12.1. Check Transaction Boundaries and Proxies First

`@Transactional(propagation = Propagation.REQUIRES_NEW)` only takes effect when the call passes through the Spring AOP proxy (in default proxy mode). If outer calls `this.inner()` on the same object, the inner annotation can be bypassed. Tests may then appear "never short on connections", when in reality **no independent physical T2 ever existed**.

```java
public void outer() {
    this.inner();  // Self-invocation: bypasses proxy for inner.
}

@Transactional(propagation = Propagation.REQUIRES_NEW)
public void inner() {
    // Does not automatically get a new transaction on a this.inner() call.
}
```

This is a fragment. Moving it to another bean and injecting the proxy is the straightforward fix. When testing pools, confirm two physical transactions/connections actually exist under the real config rather than assuming from annotations.

### 12.2. Observe Pool Metrics

Inside an application with a `HikariDataSource hikari` bean (fragment):

```java
var metrics = hikari.getHikariPoolMXBean();

System.out.println("active=" + metrics.getActiveConnections());
System.out.println("idle=" + metrics.getIdleConnections());
System.out.println("total=" + metrics.getTotalConnections());
System.out.println(
        "awaiting=" + metrics.getThreadsAwaitingConnection());
```

Values change over time and with concurrency; do not treat one sample as a static Hikari "default". Observe **over time**, especially around requests invoking inner REQUIRES_NEW. Correlate with request concurrency, pool wait times, acquisition timeouts, and database sessions.

If `awaiting>0` persists alongside `active=max` and `idle=0`, check for pool exhaustion. If `active` is not near max yet requests stall, investigate DB locks/SQL/network bottlenecks before enlarging the pool.

### 12.3. Thread Dumps and Application Traces

- If thread stacks sit in `HikariPool.getConnection(...)` / borrowing a connection, they are likely waiting on the pool.
- If they sit in JDBC driver `PreparedStatement.execute...` or socket reads, threads are waiting on SQL/DB; do not immediately conclude a lock without checking database wait events.
- Trace timings across outer begin, inner call, connection acquisition, first SQL, inner commit, and outer completion to pinpoint where latency accumulates.
- When enabling transaction logs, include request/correlation IDs to distinguish transactions within the same request.

In Spring Boot, diagnostics can be enabled when needed:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.com.zaxxer.hikari=DEBUG
```

This is an **illustrative configuration**. Do not leave TRACE/DEBUG enabled long-term in production if log volume, sensitive data, or load does not permit it. Use sampling and controlled observation windows.

### 12.4. Inspect Database Locks

Depending on the DBMS, use system diagnostic views:

- PostgreSQL: `pg_stat_activity`, `pg_locks`, `pg_blocking_pids(pid)`; see which session blocks which, transaction start times, and active SQL.
- MySQL InnoDB: `performance_schema.data_locks`, `performance_schema.data_lock_waits`, and corresponding diagnostic views/tools.
- SQL Server: DMVs for waiting tasks/requests/locks.
- Oracle: views for sessions, locks, and wait events.

**Do not look only at inner's SQL.** The blocking query is often the outer transaction that ran UPDATE/INSERT earlier before calling inner, not the current query appearing on the application thread.

### 12.5. Different Diagnosis, Different Fix

```text
Request stalls in outer -> inner(REQUIRES_NEW)
                          |
                          v
               Borrowed connection B yet?
                /                      \
               NO                      YES
               |                        |
       active=max, awaiting>0      SQL started?
               |                   /        \
       Pool capacity / leaks      NO        YES
               |                  |          |
       Sizing, release,        driver/net  DB wait state?
       backpressure                          |
                                     lock wait / I/O?
                                            |
                                  check blocking session
                                  and T1 still holding locks
```

Note that "connection leak" and "legitimately holding a connection for too long" are different issues. With `REQUIRES_NEW`, outer holding connection A until T1 ends is **correct per transaction semantics**, even if it is an expensive architectural choice.

## 13. Which Timeout Solves What?

| Timeout | Where applied | Primary effect | What it does NOT guarantee |
| --- | --- | --- | --- |
| `Hikari connectionTimeout` | Waiting for a connection from pool | Prevents indefinite connection borrow waits; fails when pool has none | Does not cancel the outer transaction holding a connection |
| Spring `@Transactional(timeout = ...)` | Transaction manager / timeout-aware operations | Caps transaction duration as supported by manager/resources | Does not replace all DB statement/lock timeouts; does not necessarily bound pool wait at every step |
| DB `lock_timeout` / lock wait timeout | Acquiring locks | Aborts SQL blocked too long | Does not grow the pool or fix lock-contention logic |
| DB statement/query timeout | Executing SQL | Cancels/stops long-running queries per DB/driver mechanism | Does not guarantee the transaction can still commit after failure |
| HTTP/request timeout | Caller or gateway | Bounds total request wait time | Does not automatically roll back backend transactions still executing |

Do not simply increase timeouts to "reduce errors" in a pool-starved system: P99 latency and held thread counts will climb. Pair timeouts with capacity planning, shorter resource hold times, and controlled error handling/retries.

### Retries Can Also Make Things Worse

If many requests time out simultaneously due to pool exhaustion and immediately retry, you create a **retry storm** that piles pressure right back onto the pool and DB. Use jittered backoff, bounded retries, circuit breakers/bulkheads, and idempotency where genuinely needed. Place retries at an appropriate transaction boundary; never reuse a completed or rollback-only `TransactionStatus`.

## 14. Comparing REQUIRES_NEW, REQUIRED, and NESTED on Resources

| Aspect | `REQUIRED` | `REQUIRES_NEW` | `NESTED` (with savepoint support) |
| --- | --- | --- | --- |
| Does inner have its own physical tx when outer is active? | No, joins T1 | **Yes, independent T2** | No; savepoint inside T1 |
| Needs extra concurrent JDBC connection on same datasource? | Usually no | **Usually yes**, when outer holds a connection | Usually no, uses T1's connection |
| Are outer locks still held while inner runs? | Same transaction | **Yes**, suspending T1 does not release locks | Locks remain in physical T1; savepoint rollback has own limits |
| Can inner commit independently and survive outer rollback? | No | **Yes** | No |
| Can inner failure make outer rollback-only? | Yes, per rules/manager | Does not automatically propagate rollback-only from T2 to T1; exception can still roll back outer | Can roll back savepoint while outer continues; manager/driver dependent |
| Pool starvation risk from extra connections? | Not from propagation itself (same resource) | **Higher** | Typically lower via savepoint path |
| Supported across all managers? | Broad | Depends on manager suspend/new-transaction support | No; depends on savepoints/JDBC/JPA configuration |

**`NESTED` is not a substitute when independent audit commits are required.** Savepoints only undo partial changes **within the same physical transaction**; if outer rolls back, all changes in T1 roll back too.

## 15. Code Review Checklist for REQUIRES_NEW

- [ ] **Why must inner commit independently?** Is there a concrete invariant/requirement, or is it just trying to evade outer rollbacks?
- [ ] **Is inner called through a proxy?** Not self-invocation or an object created with `new`.
- [ ] **From when to when does outer hold a physical connection?** Is lazy connection acquisition or a separate pool involved?
- [ ] **How many outer transactions run concurrently at peak load?** Have pool active/idle/awaiting metrics been measured?
- [ ] **How many nested connections can one thread hold?** Are there multiple layers of `REQUIRES_NEW`?
- [ ] **Does the pool have at least one spare connection when all outers hold connections?** Was sizing based on latency and DB limits, not just N+1?
- [ ] **Does inner access rows/foreign keys/indexes just locked by outer?** Were DB lock waits checked?
- [ ] **Are T1 and T2 hold durations as short as possible?** Are HTTP calls/CPU/reports inside transactions?
- [ ] **Are connection timeout, lock timeout, and transaction timeout clearly configured separately?**
- [ ] **What does outer do if inner fails to get a connection or hits lock timeout?** Roll back, retry, or monitored partial success?
- [ ] **Is "inner commits, outer rolls back" an acceptable business outcome?**
- [ ] **Are there bounded integration/load tests monitoring SQL and pool metrics?**
- [ ] **Are post-rollback/commit outcomes verified with independent queries?**
- [ ] **Is the pool kept within the database's safe capacity rather than raised indefinitely?**

## 16. Self-Check Questions

**Q1.** Outer opened T1 and called inner `REQUIRES_NEW`. Does "Spring suspends T1" mean connection A is immediately returned to the pool?

*No.* T1's physical transaction remains open; resources bound to T1 typically stay held. Inner must borrow connection B when using JDBC local transactions on the same pool if T1 already holds connection A.

**Q2.** Why can pool size=1 cause a timeout even when the application runs only a single thread?

*Because outer holds the sole connection, while inner REQUIRES_NEW needs another connection before running. Outer cannot release its connection until the inner call returns; inner cannot run until it gets a connection.*

**Q3.** If 10 concurrent threads each hold one connection in a pool of size=10 and all start REQUIRES_NEW, what can happen?

*No connection remains for inner; all 10 threads can wait until timeout. Pool size=11 lets at least one inner proceed if there are no other users, though it may still lack good throughput.*

**Q4.** Pool size was raised to 100, yet inner still times out updating a row outer already UPDATEd. Why?

*That is a lock wait, not connection shortage. T1 still holds the row lock; T2 has connection B but cannot acquire the lock while T1 cannot finish before inner returns.*

**Q5.** If inner `REQUIRES_NEW` wrote and committed an audit, and outer later throws an exception and rolls back, does the audit remain?

*It can remain.* Inner T2 committed independently of T1. That is the intended semantics of `REQUIRES_NEW`, though you must verify whether it fits the business requirements.

**Q6.** Does replacing `REQUIRES_NEW` with `NESTED` always avoid pool exhaustion while keeping independent commits?

*No.* `NESTED` relies on savepoints in the same physical transaction when supported; it usually avoids needing B, yet has **no independent commit**. If outer rolls back, inner data still rolls back.

**Q7.** Why does a single-request test often fail to catch production incidents?

*At low concurrency, the pool has idle connections and little lock contention. When many concurrent outer transactions hold connections/locks, inner demand spikes; test with concurrency, timeouts, and metrics.*

**Q8.** Should `connectionTimeout` be raised to several minutes to prevent pool starvation errors?

*Do not use that as a root fix.* Long timeouts only keep threads waiting longer for connections. Reduce outer resource hold times, size the pool for the workload, eliminate lock conflicts, and apply proper backpressure/retries.

**Q9.** If inner uses a different datasource from outer, is there still a pool-exhaustion risk?

*Potentially.* The risk shifts to the pool of inner's datasource and workloads sharing that pool. If inner touches the same DB rows via another datasource, locks can still contend. Identify the exact datasources, transaction managers, and physical resources.

**Q10.** Can we conclude `REQUIRES_NEW` did not run because we did not see the pool add a connection?

*Not by itself.* Outer might not have acquired a physical connection yet, metrics might have been sampled at the wrong moment, a different pool might be in use, or inner suffered self-invocation. Verify proxies, transaction managers, actual connections, and SQL across real sessions.

## 17. Key Takeaways to Remember

- **`REQUIRES_NEW` creates an independent physical transaction** from outer; inner can commit before outer finishes.
- **Spring's suspend does not end the outer transaction and does not automatically return connections or release database locks.**
- On the same JDBC pool, outer holds connection A and inner needs B: **the pool must support concurrent connections**, not just request thread count.
- **A pool size equal to the number of outer threads** can make all inner calls stall together; adding at least one slot avoids the simple wait cycle, though it does not guarantee latency/throughput.
- **Enough connections does not guarantee enough locks**: inner using B can still wait on locks held by T1, especially when both scopes touch the same row/index/foreign key.
- **Enlarging the pool does not fix lock waits**, and increasing timeouts does not create capacity. Find the true choke point.
- **Shortening outer transaction hold time, reviewing business boundaries, and testing both failure modes** are central to safe design.

## Official References

1. [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `PROPAGATION_REQUIRES_NEW`, connection pool exhaustion warnings, requirement that pool size exceed concurrent threads by at least one connection, and `REQUIRED`/`NESTED` comparison.
2. [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction proxies, `TransactionInterceptor`, manager begin/suspend/commit/resume.
3. [Spring Framework — `AbstractPlatformTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): transaction suspension/resumption and commit/rollback lifecycle support.
4. [Spring Framework — JDBC Connection Management](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceTransactionManager`/`JdbcTransactionManager`, JDBC connection binding, and `LazyConnectionDataSourceProxy`.
5. [HikariCP — Connection Pool Configuration](https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby): `maximumPoolSize`, `connectionTimeout`, `minimumIdle`.
6. [HikariCP — `HikariPoolMXBean`](https://javadoc.io/doc/com.zaxxer/HikariCP/5.1.0/com/zaxxer/hikari/HikariPoolMXBean.html): active/idle/total/waiting connections.
7. [PostgreSQL — Monitoring Database Activity](https://www.postgresql.org/docs/current/monitoring-stats.html): `pg_stat_activity` and wait events.
8. [PostgreSQL — Explicit Locking](https://www.postgresql.org/docs/current/explicit-locking.html): locks, deadlocks, and how the engine manages blocking transactions.
