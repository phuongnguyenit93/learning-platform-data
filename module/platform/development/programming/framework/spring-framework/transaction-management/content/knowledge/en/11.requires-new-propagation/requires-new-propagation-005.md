# Extra Connection Pool Demand When Using PROPAGATION_REQUIRES_NEW

## 1. Why Can One Request Hold Two JDBC Connections?

When a method already running inside a Spring transaction calls another method annotated with `@Transactional(propagation = Propagation.REQUIRES_NEW)` **through the transaction proxy**, Spring must create a **new physical transaction** for the inner method. The outer physical transaction is **suspended** while the inner method runs, and resumed afterward.

In a JDBC application using `DataSourceTransactionManager` or `JdbcTransactionManager` with a pooled `DataSource`, the key fact is that **suspending a transaction does not return the outer transaction's connection to the pool**. If outer already borrowed connection C1, that connection remains held to continue physical transaction T1. The inner `REQUIRES_NEW` requires an independent physical transaction T2 and typically borrows connection **C2** from the same pool. Thus, a single Java thread can **simultaneously occupy two pool slots** even without executing two Java blocks in parallel.

~~~text
Caller -> OuterService proxy
             |
             v
        @Transactional(REQUIRED) outer:
        begin T1, hold JDBC connection C1
             |
             v
        InnerService proxy:
        @Transactional(REQUIRES_NEW)
             |
             +-- suspend T1 context; C1 still belongs to outer
             +-- begin T2, borrow connection C2
             +-- execute SQL, commit/roll back T2, release C2
             |
             v
        resume T1; continue using C1
        commit/roll back T1; release C1
~~~

This extra connection demand is the **resource cost of independent commit/rollback semantics**: a successful inner commit is not undone just because outer later rolls back. You cannot both demand two independent physical transactions and expect to use only a single JDBC connection still tied to the outer transaction.

**Scope of this statement:** This is the typical path with Spring JDBC when outer **has already borrowed an actual JDBC connection**. If there is no outer transaction, or outer uses lazy connection acquisition and has not yet touched the DB, measured active connections can differ. JPA, JTA, and reactive R2DBC manage resources differently; do not apply one fixed number to every system.

## 2. Comparing REQUIRED, REQUIRES_NEW, and NESTED from a Resource Perspective

Assume all beans/methods are properly called through Spring AOP proxies and share **one JDBC DataSource**:

| Inner propagation | Physical transaction | Connection when outer holds C1 | Ability to complete independently |
| --- | --- | --- | --- |
| `REQUIRED` | Joins existing T1 | Usually continues using C1 already bound to the transaction | No separate commit; inner can mark the shared transaction rollback-only |
| `REQUIRES_NEW` | Suspends T1, opens independent T2 | C1 stays held; T2 usually borrows C2 | Yes; T2 commits/rolls back independently of T1 |
| `NESTED` | Usually uses a savepoint within T1 | Usually continues using C1 | Can partially roll back to savepoint, **cannot** commit independently of T1 |
| No outer transaction and calling `REQUIRES_NEW` | Creates new T2 | Only needs a connection for T2 as usual | No C1 being held |

`REQUIRED` does not inherently require an extra connection when outer and inner share the same manager/resource. `NESTED` is not an equivalent way to build an independent audit transaction: if outer rolls back, the entire physical transaction—including changes after the inner savepoint—is rolled back.

`REQUIRES_NEW` is not merely another name for `REQUIRED`. Spring can apply separate isolation, timeout, and read-only settings to T2, and locks acquired by T2 are generally released when T2 finishes. Those are real benefits, yet they add pool pressure whenever outer already holds a connection.

## 3. Resource Diagram Within a Single Thread

~~~mermaid
flowchart TD
    A["Java thread calls outer via proxy"] --> O["Physical transaction T1"]
    O --> C1["Borrow JDBC Connection C1"]
    C1 --> H["Outer executes SQL and holds C1"]
    H --> S["inner() via Spring proxy<br/>PROPAGATION_REQUIRES_NEW"]
    S --> P["Suspend T1 context<br/>C1 not returned to pool"]
    P --> I["Physical transaction T2"]
    I --> C2["Borrow JDBC Connection C2"]
    C2 --> DB[("Database")]
    C1 --> DB
    C2 --> E["Inner commits/rolls back T2<br/>release C2"]
    E --> R["Resume T1 on C1"]
    R --> F["Outer completes T1<br/>release C1"]
~~~

Observable state progression in an **isolated single-threaded JDBC/Hikari application**:

| Milestone | T1 State | T2 State | `activeConnections` |
| --- | --- | --- | ---: |
| Before outer | None | None | 0 |
| Outer begins and borrows C1 | Active | None | 1 |
| Inner begins T2 | Suspended, holds C1 | Active on C2 | 2 |
| Inner finishes | Still holds C1 | C2 returned | 1 |
| Outer finishes | C1 returned | Finished | 0 |

These are **illustrative milestones for the example below**, not a universal rule for every ORM configuration or multi-request workload. A pool under concurrent traffic may show active=5, 10, etc., at corresponding moments.

### What Does Spring Suspend?

In imperative Spring, the transaction manager and synchronization infrastructure manage binding resources to the current thread. Upon entering an inner `REQUIRES_NEW`, the framework suspends the outer transaction context, detaches/stashes outer's resources from the active context, and creates a new context. **It is not a commit or rollback command for outer.**

Because connection C1 belongs to an unfinished T1, lending C1 to another transaction would break transaction state isolation. Hence outer keeps C1 until T1 completes, while T2 needs a separate resource. Even though `JdbcTemplate` in both services uses the **same DataSource bean**, it receives two **different** connections because the active transaction context at borrow time differs.

## 4. Pool Exhaustion Scenario: Every Thread Holds One Connection and Waits for Another

Suppose `maximumPoolSize=3`, and three threads concurrently process three requests, each having opened an outer transaction, executed SQL, and retained a connection:

~~~text
Pool maximum = 3

Thread A: outer T1A holds C1 -> calls inner REQUIRES_NEW -> waits for C4
Thread B: outer T1B holds C2 -> calls inner REQUIRES_NEW -> waits for C4
Thread C: outer T1C holds C3 -> calls inner REQUIRES_NEW -> waits for C4

Active=3, Idle=0, Awaiting=3.
No connection remains to be granted to any inner call.
~~~

All threads **hold an outer connection while waiting for an inner connection**. No inner call can obtain a connection to run and finish, so no slot is freed along the normal path. This is **pool-locking / pool starvation**, typically ending in a **connection acquisition timeout** once `connectionTimeout` expires, or causing prolonged stalling if waiting is not bounded well.

Distinguish carefully:

- **Pool-locking:** inner cannot obtain a connection to begin SQL because all connections are held by outer transactions.
- **Database deadlock/row-lock wait:** inner **has already** borrowed a connection, but its SQL waits on a lock held by outer or another transaction. Increasing the pool does not fix this lock dependency.
- **Connection leak:** code borrows a connection and fails to release it properly; different from outer legitimately holding its connection until the end of its transaction.
- **Transaction timeout:** time limit on a transaction; different from `connectionTimeout` while waiting on the pool.

### What If the Pool Is Increased to 4?

A fourth connection can be granted to **one inner call**. Provided that inner does not wait on row locks or resources held by other outer transactions, it can finish and return the connection for the next inner call. Thus the pool has a **path to make progress** instead of everyone stalling.

However, `maximumPoolSize=4` only allows **one inner to run at a time** when all three outer transactions hold connections. For all three inner calls to hold connections concurrently in that model, peak demand requires around **6 active connections**. Having at least one spare slot to avoid pool-locking is **different** from avoiding queuing during peak traffic.

## 5. Calculating Pool Size: Two Questions, Two Thresholds

Let:

- `T` = number of concurrent threads/requests **currently holding an outer connection** from one pool.
- `C` = maximum connections **a single thread can hold simultaneously** due to nested transactions; in an outer + one inner `REQUIRES_NEW` model, `C=2`.
- `P` = maximum size of **that same pool**, including both active and idle.
- `B` = connections used concurrently by other work sharing the same pool (schedulers, other requests, etc.).

### 5.1. Threshold to Avoid Pool-Locking in a Simple Resource Model

HikariCP states a theoretical formula to prevent every thread from holding almost all resources and waiting on one final connection:

\[
P_{\text{min}} = T \times (C-1) + 1
\]

With one outer and one inner (`C=2`), this yields `P >= T+1`. This is the basis for Spring's warning: the pool must be **larger than the number of concurrent threads holding outer transactions by at least one connection** in typical cases.

For example, if 8 outer calls hold 8 connections, 8+1=9 allows one inner call to make progress. If one thread can hold **three** connections via outer -> inner `REQUIRES_NEW` -> deeper inner `REQUIRES_NEW`, then `C=3`, and with 8 threads the theoretical threshold becomes 8×(3−1)+1=17.

**Note:** This condition applies a pool-level resource-allocation model, assuming an inner call granted a slot can finish and return it. It **does not** guarantee freedom from DB row-lock deadlocks, is not a performance-tuning formula, and does not cover extra demand `B`. If connections must also be held from separate pools, calculate each pool individually and against the total DB budget.

### 5.2. Peak Level So All Threads Can Run Inner Simultaneously

When all `T` threads simultaneously hold up to `C` connections, peak demand (excluding other overhead) is roughly:

\[
P_{\text{peak}} \approx T \times C + B
\]

This is an estimate of **potential demand**, not a blanket recommendation to always size the pool to that value. Opening too many connections can degrade database throughput or exceed system-wide session quotas. Sometimes reducing concurrency is more effective than growing the pool.

| Concurrent outer T | Max C / thread | Progress threshold: `T(C−1)+1` | Peak when all hold C, excl. B |
| ---: | ---: | ---: | ---: |
| 1 | 2 | 2 | 2 |
| 3 | 2 | 4 | 6 |
| 8 | 2 | 9 | 16 |
| 16 | 2 | 17 | 32 |
| 8 | 3 | 17 | 24 |

For instance, a pool max of 17 for 16 outer + one inner per thread lets one inner proceed in the worst case, while other inner calls queue. If you want 32 concurrent connections, verify **whether the database can handle 32 active SQL sessions** and whether other pools share that DB.

### 5.3. Measure Concurrency from Real Requests, Do Not Misuse Metrics

`T` is **not total logged-in users** or HTTP connection count. Count only flows holding connections at the same instant. A web server with 200 request threads where only 12 threads hold JDBC connections concurrently has `T` near 12 for this resource at measured peak; conversely, a job executor with few threads but very long transactions can still create heavy pool pressure.

Factors that change the math include: outer connection hold duration, non-DB I/O inside transactions, `REQUIRES_NEW` nesting depth, multiple DataSources, lazy JDBC connection acquisition, pools for other jobs, and the DB's `max_connections` limit.

## 6. Spring Boot and HikariCP: Settings That Actually Matter

With `spring-boot-starter-jdbc` or the Spring Data JPA starter, Spring Boot typically includes HikariCP. When Boot auto-configures the datasource, settings usually live at:

~~~properties
# Illustrative example; replace URL/credentials/driver for your environment.
spring.datasource.url=jdbc:postgresql://db.example.internal:5432/orders
spring.datasource.username=orders_app

spring.datasource.hikari.pool-name=orders-pool
spring.datasource.hikari.maximum-pool-size=12
spring.datasource.hikari.minimum-idle=4
spring.datasource.hikari.connection-timeout=2000
~~~

**Do not use the placeholder host/credentials above in production.** Measure load and connection budgets before choosing values, and use secrets management for passwords.

| Property | Primary effect | Misconception to avoid |
| --- | --- | --- |
| `maximumPoolSize` | Total maximum connections in the pool, active + idle | Not max thread count; does not reserve slots for inner |
| `minimumIdle` | Idle level the pool tries to maintain | Does not allow exceeding maximum when pool is full |
| `connectionTimeout` | Max time waiting to borrow a connection | Different from SQL/query timeout or overall transaction timeout |
| `poolName` | Name to distinguish pools in logs/metrics | Does not alter `REQUIRES_NEW` semantics |
| `maxLifetime` | Lifetime limit of a connection in the pool | Not a transaction timeout |
| `leakDetectionThreshold` | Warns on long-held connections | May warn on legitimate long outer transactions; does not prove a leak |

When HikariCP has no idle connections and has reached `maximumPoolSize`, it waits up to `connectionTimeout` to borrow and then throws a connection-acquisition error. Spring may wrap the JDBC cause in a transaction-layer exception, such as `CannotCreateTransactionException` when unable to begin the inner transaction. Exact logs and exception types depend on manager/driver/version.

**Three distinct timeouts:** `connectionTimeout` (waiting on the pool), `@Transactional(timeout=...)` (transaction scope, manager-dependent), and statement/query timeout (SQL/DB). Merely increasing `connectionTimeout` makes requests wait longer; it does not create a second connection if all outer calls still hold the entire pool.

## 7. Complete Java 17+ Demo: Observing Hikari active=1 -> 2 -> 1 -> 0

This example uses **Spring Boot 3.3.5**, Java 17+, Maven, Spring JDBC, HikariCP, and in-memory H2. There is exactly one pool with `maximumPoolSize=2` and two Spring service beans. Outer writes row id=1 in T1, and inner `REQUIRES_NEW` writes row id=2 in T2. Two different rows avoid lock dependencies between T1 and T2. Outer intentionally throws an unchecked exception to roll back **after** inner has committed, verifying independence through persisted data.

### 7.1. Project Structure

~~~text
requires-new-pool-demo/
├── pom.xml
└── src/main/java/example/txpool/
    ├── PoolDemoApplication.java
    ├── OuterService.java
    └── InnerService.java
~~~

### 7.2. The `pom.xml` File

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
    <artifactId>requires-new-pool-demo</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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

### 7.3. The `src/main/java/example/txpool/PoolDemoApplication.java` File

~~~java
package example.txpool;

import com.zaxxer.hikari.HikariDataSource;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class PoolDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(PoolDemoApplication.class, args);
    }

    @Bean
    HikariDataSource dataSource() {
        HikariDataSource ds = new HikariDataSource();
        ds.setPoolName("requires-new-demo-pool");
        ds.setDriverClassName("org.h2.Driver");
        ds.setJdbcUrl("jdbc:h2:mem:txpool;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        ds.setMaximumPoolSize(2);
        ds.setMinimumIdle(0);
        ds.setConnectionTimeout(1500);
        return ds;
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean
    CommandLineRunner demo(
            JdbcTemplate jdbc, OuterService outer, HikariDataSource pool) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE account (id INT PRIMARY KEY, balance INT NOT NULL)"
            );
            jdbc.update("INSERT INTO account (id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO account (id, balance) VALUES (?, ?)", 2, 200);

            System.out.println("BEFORE=" + balances(jdbc));
            try {
                outer.writeAndRollback();
            } catch (IllegalStateException ex) {
                System.out.println("OUTER_ERROR=" + ex.getMessage());
            }
            System.out.println("AFTER=" + balances(jdbc));
            System.out.println(
                "ACTIVE_AFTER="
                + pool.getHikariPoolMXBean().getActiveConnections()
            );
        };
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?", Integer.class, 1
        );
        Integer b = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?", Integer.class, 2
        );
        return a + "/" + b;
    }
}
~~~

**Why create a `HikariDataSource` bean?** So the demo explicitly sets pool max=2 instead of relying on environment defaults. Spring Boot sees one `DataSource` and supplies the matching `JdbcTemplate`; the transaction manager bean is explicitly built from that **exact** datasource. `DB_CLOSE_DELAY=-1` keeps the in-memory H2 database alive while the pool borrows and returns connections.

### 7.4. The `src/main/java/example/txpool/OuterService.java` File

~~~java
package example.txpool;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;
    private final HikariDataSource pool;

    public OuterService(
            JdbcTemplate jdbc, InnerService inner, HikariDataSource pool) {
        this.jdbc = jdbc;
        this.inner = inner;
        this.pool = pool;
    }

    @Transactional
    public void writeAndRollback() {
        jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            10, 1
        );
        System.out.println(
            "OUTER_ACTIVE="
                + pool.getHikariPoolMXBean().getActiveConnections()
        );

        inner.creditIndependently();

        System.out.println(
            "OUTER_RESUMED_ACTIVE="
                + pool.getHikariPoolMXBean().getActiveConnections()
        );
        throw new IllegalStateException("outer-rollback");
    }
}
~~~

### 7.5. The `src/main/java/example/txpool/InnerService.java` File

~~~java
package example.txpool;

import com.zaxxer.hikari.HikariDataSource;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;
    private final HikariDataSource pool;

    public InnerService(JdbcTemplate jdbc, HikariDataSource pool) {
        this.jdbc = jdbc;
        this.pool = pool;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void creditIndependently() {
        jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            20, 2
        );
        System.out.println(
            "INNER_ACTIVE="
                + pool.getHikariPoolMXBean().getActiveConnections()
        );
    }
}
~~~

### 7.6. Run Command

Requires JDK 17+ and Maven; first run may need to download dependencies from Maven Central. Inside the directory containing `pom.xml`:

~~~bash
mvn -q spring-boot:run
~~~

Looking only at **the lines printed by the program**; Spring Boot/Hikari startup logs may add other lines:

~~~text
BEFORE=100/200
OUTER_ACTIVE=1
INNER_ACTIVE=2
OUTER_RESUMED_ACTIVE=1
OUTER_ERROR=outer-rollback
AFTER=100/220
ACTIVE_AFTER=0
~~~

### 7.7. Interpreting the Results and Transaction Order

1. `BEFORE=100/200`: two rows initialized outside any service transaction method.
2. `OUTER_ACTIVE=1`: `CommandLineRunner` calls `OuterService` through the Spring proxy; outer opens transaction T1 and UPDATEs row id=1 on C1. T1 has not committed yet, so the connection remains active.
3. `INNER_ACTIVE=2`: calls into the **injected `InnerService` bean**, thus passing through the proxy. `REQUIRES_NEW` suspends T1, borrows C2, and updates row id=2 in transaction T2. At this point C1 belongs to outer and C2 belongs to inner: active=2.
4. Inner completes normally; the manager commits T2 and releases C2. Spring resumes T1.
5. `OUTER_RESUMED_ACTIVE=1`: only outer's C1 remains borrowed.
6. Outer throws `IllegalStateException`. Because the unchecked error escapes the outer proxy, transaction T1 rolls back and C1 is returned. Caller catches the exception **after** the proxy.
7. `AFTER=100/220`: row 1's +10 was rolled back with outer; row 2's +20 remains due to inner's independent commit.
8. `ACTIVE_AFTER=0`: after the final SELECT queries release their connections, the isolated demo has no borrowed connections remaining.

**The two UPDATEs intentionally target different rows.** If inner T2 tried to UPDATE the exact row outer T1 locked, inner could wait on T1's row lock even with pool max=2; since outer waits for inner to finish, the wait cycle could cause the demo to fail. That is a locking issue distinct from pool capacity.

Measuring Hikari active counts at those points proves the behavior **in a single-threaded/single-pool environment**. In production with other workloads, active counts are also affected by other borrowers; do not use them to extrapolate per-method connection counts across all JPA versions or drivers.

## 8. Experiment Changing Pool Size to 1: Connection Borrow Failure

After running the demo successfully, you can try changing **one line** in `PoolDemoApplication.java`:

~~~java
ds.setMaximumPoolSize(1);
~~~

This is only an **experimental variant**, not the configuration for the successful stdout in Section 7.

Outer borrows C1 and holds it until the transaction finishes. Inner `REQUIRES_NEW` needs C2, yet the pool has no second slot. With `connectionTimeout=1500` ms, HikariCP waits and reports that it cannot acquire a connection, and Spring may throw a transaction-related exception such as `CannotCreateTransactionException` wrapping the JDBC timeout cause. Exact exception types and logs depend on the environment; **do not** expect the program to print `INNER_ACTIVE=2` or `AFTER=100/220` in this variant.

Because the demo's runner only catches `IllegalStateException` intentionally thrown by outer after inner, the pool max=1 variant can terminate with an error. That aligns with proving that **even a single thread** can fail to complete outer -> REQUIRES_NEW when outer holds a connection and the pool has only one slot.

Restore pool max to 2 after testing. Never use pool size 1 for flows with nested independent transactions if outer typically holds a connection.

### With Multiple Concurrent Outers, the Problem Scales Up

If 8 outers hold all 8 connections of a max=8 pool and all 8 inners wait for C9, the pool shows `active=8`, `idle=0`, `pending≈8`. At pool max=9, one inner can run and return C9; the other inners queue. At pool max=16, in the simple model 8 outers + 8 inners can run concurrently, though the database must also handle that many sessions/queries.

## 9. Measure and Monitor the Pool Instead of Guessing Configuration

To diagnose accurately, inspect both the transaction call graph and pool metrics together.

| Metric | What is it measuring? | Signal to watch |
| --- | --- | --- |
| Active connections | Connections currently borrowed | Repeatedly hitting maximum during peak hours |
| Idle connections | Connections immediately available | Near 0 while latency climbs |
| Pending / threads awaiting connection | Threads waiting to borrow | Rises right as outers call inner `REQUIRES_NEW` |
| Total connections | Total existing connections | Near max; distinguish from active |
| Acquisition latency | Time spent borrowing a connection | High p95/p99 before timeouts |
| Connection timeouts | Borrow timeout count | Spikes during bursts or pool-locking |
| Transaction duration | How long outer holds a connection | Long transactions amplify concurrent connection demand |
| DB lock waits | SQL waiting on locks | Rises even when pool has free connections; distinguish row locks |

`HikariDataSource#getHikariPoolMXBean()` exposes `getActiveConnections()`, `getIdleConnections()`, `getTotalConnections()`, and `getThreadsAwaitingConnection()`. With Spring Boot Actuator/Micrometer, Hikari metrics may be published; verify exact metric names for your version and observability backend. With multiple pools, always separate by `poolName`.

Diagnostic logging you can enable during testing:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.com.zaxxer.hikari=DEBUG
~~~

Do not enable broad DEBUG logging in production due to overhead and sensitive data exposure. Log messages vary by version and manager.

### How to Read a Timeout Incident

1. Which **pool** timed out, and what is its actual size?
2. How many outer transactions were holding connections at that moment?
3. Were `REQUIRES_NEW` calls waiting to borrow connections? How many layers deep?
4. Had inner already obtained a connection, or was it waiting on a DB lock afterward?
5. Did outer hold its connection long due to SQL, HTTP calls, sleep/retries, or blocking logic?
6. Is `connectionTimeout` set too short or too long relative to your SLO?
7. Do other workloads share the pool (batch, schedulers, listeners), or do multiple app instances add connections to the same DB?
8. Are outer and inner transaction managers and `DataSource` instances using the exact pool you expect?
9. Are connections returned when scopes finish, or is there an actual leak?
10. Does a load test reproduce the failure with the corresponding concurrent outers and resource dependencies?

A single `active=maximum` snapshot is not enough to conclude deadlock; a well-utilized pool can stay full with healthy throughput if borrowers release connections promptly. A much stronger signal is **active near max + rising pending + borrow latency/timeouts + a call graph where outer holds a connection and calls REQUIRES_NEW**.

## 10. Ways to Reduce Pool Pressure and Their Trade-Offs

### 10.1. Only Use REQUIRES_NEW When an Independent Transaction Is Needed

If business logic wants **all changes to commit or roll back together**, `REQUIRED` is usually more suitable and avoids splitting physical transactions. If the business requires an independent step to survive even when outer fails (such as critical auditing), `REQUIRES_NEW` makes sense—at the cost of extra connections and split atomicity.

**Do not change propagation blindly** just to fix timeouts. Switching `REQUIRES_NEW` to `REQUIRED` can cause an audit record that previously survived outer rollback to roll back along with it.

### 10.2. Shorten the Outer Transaction

The longer outer holds a connection, the more requests occupy the pool simultaneously. Minimize HTTP calls, sleep, file processing, heavy computation, and remote-service waits **inside transactions** when business logic permits. Wrap transaction boundaries tightly around DB operations that truly require atomicity.

Illustrative structural snippet, **not standalone runnable code**:

~~~java
ValidationResult validated = remoteValidator.validate(request);
transactionalService.persist(validated);
~~~

Do not move a step outside a transaction if doing so breaks invariants/consistency; the goal is shortening resource hold time **while preserving business correctness**.

### 10.3. Limit Concurrency or Introduce Queuing

If the database cannot handle 2T connections at peak, endlessly raising the pool size is not the answer. You can bound concurrent flows using a bounded executor, queue, or semaphore, leaving slots for inner calls and other workloads. Compute the concurrency budget from database capacity and all pools across the entire fleet (all instances), not just one JVM's thread pool.

### 10.4. NESTED/Savepoint When Partial Rollback Is the Goal

When the JDBC manager/driver supports `PROPAGATION_NESTED`, inner can roll back to a savepoint on the same physical transaction. It usually does not need a separate connection T2 like `REQUIRES_NEW`. However, inner **does not commit independently**: an outer rollback still undoes all changes remaining in T1. Choose it only if those semantics fit.

### 10.5. TransactionTemplate Does Not Avoid the Second Connection

If using programmatic transactions:

~~~java
// Snippet inside a Spring bean with PlatformTransactionManager manager injected.
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW
);
template.executeWithoutResult(status -> {
    // JDBC work requiring a new transaction.
});
~~~

`TransactionTemplate` avoids self-invocation limits because the boundary is created explicitly, yet it still requires a **new physical transaction**, so it does not eliminate the need for C2 if outer already holds C1.

### 10.6. Do Not Confuse Two Pools with a Distributed Transaction

If outer uses `ordersDataSource` and inner uses `auditDataSource`, each pool has its own budget. You must select the right transaction manager for each bean; using two DataSources does not automatically create an atomic distributed transaction. And if both pools point to the same database, the sum of connections across **both** still counts against the DB's session quota.

## 11. Notable Exceptions and Pitfalls

### 11.1. Lazy Connection Acquisition

`LazyConnectionDataSourceProxy` or certain ORMs may defer borrowing a physical JDBC connection until the first SQL statement. If outer only runs Java logic without SQL yet, it may not occupy a pool slot. When inner runs, you may observe active=1 instead of 2. **Do not conclude `REQUIRES_NEW` was ignored solely from a low active count**: verify proxies, managers, connection timing, and independent commits.

### 11.2. JPA/Hibernate

`JpaTransactionManager` manages `EntityManager` and the persistence context, typically using a JDBC connection underneath. Borrow/release timing can depend on the JPA provider. Resource-pressure warnings remain important, but do not assume every annotated outer immediately borrows a connection or that every nested JPA setup behaves identically to Spring JDBC.

### 11.3. R2DBC Does Not Use JDBC HikariCP

`R2dbcTransactionManager` uses `ConnectionFactory` and Reactor subscriber context, not Hikari's `javax.sql.DataSource` shown in the demo. While independent transactions can still increase R2DBC pool usage, the `spring.datasource.hikari.maximum-pool-size` property does not configure the R2DBC pool. Monitor and configure the corresponding reactive driver/connection factory.

### 11.4. Self-Invocation Can Lose REQUIRES_NEW

A bean calling `this.inner()` in proxy mode usually **bypasses the inner interceptor**, so `@Transactional(REQUIRES_NEW)` on inner does not start a new transaction. You may see only one connection, yet that is **not** a successful resource optimization: the required semantics may be silently broken. To establish a real boundary, move the method to another bean and call through the proxy, or use `TransactionTemplate` where appropriate.

### 11.5. Row-Lock Deadlocks Cannot Be Fixed by Enlarging the Pool

Outer T1 updates row `id=1` and holds the uncommitted lock. Inner T2 `REQUIRES_NEW` also updates row `id=1`, so T2 waits on T1's lock; meanwhile T1 waits for inner to return before continuing. Whether the pool has 2, 12, or 100 connections, enlarging the pool **cannot break this lock wait**. You must change lock scope, access order, the data inner touches, or the architecture.

### 11.6. Pool Active Is Not Thread Count

One thread can hold two connections; many threads can share connections across sequential transactions as they are released. Thus `activeConnections` does not equal concurrent requests at every moment. Read pool metrics **alongside** borrow/release timelines and propagation behavior.

## 12. Designing Proper Capacity Tests

### Single-Threaded Test

1. Set up H2 and a Hikari pool with max 2, using real Spring proxies.
2. Have outer UPDATE a row to ensure it has borrowed a physical connection.
3. Have inner `REQUIRES_NEW` UPDATE a different row and print `getActiveConnections()`.
4. Assert the sequence active 1 -> 2 -> 1, and active 0 after outer completes.
5. Have outer intentionally roll back; assert only inner's update remains.
6. Write **a separate test** with pool max 1 and a short timeout to confirm inner cannot borrow a connection. Do not alter the passing test's config and expect the same stdout.

### Multi-Threaded Test

1. Choose `T=3` and create three outer transactions touching three **distinct** DB rows.
2. In the test harness, use a barrier so all three outers borrow connections before calling inner.
3. With pool max 3, observe pending rising and borrow timeouts when all inners need new connections.
4. With pool max 4, at least one inner can proceed if there are no row-lock dependencies; the others wait for a slot.
5. With pool max 6, connections suffice for all three inners concurrently, though SQL/DB may still queue on CPU, locks, or session quotas.
6. Ensure executors are shut down, the database is reset, and no active connections remain leaked after tests.

Avoid placing `@Transactional` directly on the test method if it causes the service to join an outer test transaction and roll back at test end, skewing connection counts and commit observations. Measure from a caller outside any test transaction and inspect persisted data **after the proxy finishes**.

## 13. Quick Diagnostic Table

| Symptom | Suspect | Remediation |
| --- | --- | --- |
| Pool max 1, outer holds C1, inner `REQUIRES_NEW` times out | Missing C2 to start T2 | Provide slots for inner or change semantics if allowed |
| T outers hold T connections, all inners pending | Pool-locking | Reserve capacity, reduce concurrency and transaction duration |
| Pool `T+1` avoids deadlock yet high latency | Only one inner can run while all outers hold slots | Examine peak demand, SQL latency, and DB capacity |
| Pool has free slots yet inner hangs on SQL | Row lock / DB resource dependency | Inspect lock graph, not just pool settings |
| `REQUIRES_NEW` in code yet one transaction and inner rolls back with outer | Self-invocation / wrong manager / wiring | Verify proxy path and integration tests |
| Raising `connectionTimeout` cuts errors but p99 rises | Waiting longer without adding supply | Fix capacity/concurrency; set timeout to match SLO |
| High Hikari active while outer is suspended | Outer legitimately holds connection | Distinguish from leak; check hold duration and end-of-scope release |
| Raising one instance's pool triggers DB too-many-connections | Sum of replica pools exceeds DB quota | Budget connections across the entire system |
| Inner updates same row as outer, still hangs with ample pool | T1 holds lock needed by T2 | Redesign operations or transaction boundaries |
| Switching `REQUIRES_NEW` to `NESTED` stops audit from committing independently | Savepoint semantics differ from independent physical transaction | Choose propagation to match business rules |

## 14. Pre-Run Prediction Exercises

**Q1.** Five concurrent outer transactions have borrowed 5 connections from a pool with max 5; each outer calls an inner `REQUIRES_NEW`. What can happen?

**A:** All five outers occupy the entire pool; all inners wait for a sixth connection and may time out because none can make progress. This is pool-locking in the simple model.

**Q2.** Pool max is increased from 5 to 6. Does that guarantee all five inners run concurrently?

**A:** No. One spare slot may allow **one inner** to advance and free its slot for the next if no locks block it. To have five outers + five inners **all active simultaneously**, peak demand is 10 connections, assuming the DB can handle it.

**Q3.** A request has an outer and two nested `REQUIRES_NEW` levels, with all three physical transactions holding connections. Is pool max 2 enough?

**A:** Not when all three must stay alive concurrently; up to three connections can be needed by one thread. Account for nesting depth and resource release timing.

**Q4.** With 8 threads, each holding up to 3 connections, what theoretical threshold does Hikari's simple anti-pool-locking formula yield?

**A:** `8 × (3−1) + 1 = 17`. This number does not guarantee throughput or prevent DB deadlocks.

**Q5.** Inner T2 commits and then outer T1 rolls back; must inner's changes roll back as well?

**A:** No, provided inner genuinely created an independent `REQUIRES_NEW` transaction and committed successfully. This is the exact semantic distinction to preserve when choosing an architecture.

**Q6.** Pool max is 20 with idle connections available, yet inner T2 waits to UPDATE a row locked by outer. Will raising the pool to 40 fix it?

**A:** No. That is a row-lock dependency between two transactions, not connection starvation.

**Q7.** A service uses `TransactionTemplate` with `PROPAGATION_REQUIRES_NEW` instead of the annotation. Does it reuse outer's connection C1 to bypass pool capacity?

**A:** No. The programmatic API only defines the boundary differently; the new physical transaction still needs its own resource when outer already holds C1.

## 15. Conclusion

**`REQUIRES_NEW` requires an independent physical transaction; with Spring JDBC and an outer transaction holding a connection, that typically demands a second connection from the pool.** Suspending outer does not release C1. One Java thread can temporarily occupy two pool slots, and multiple threads holding outer connections simultaneously can cause inner calls to wait together and time out.

Design around **actual concurrent outers**, **`REQUIRES_NEW` depth**, **resource hold duration**, **pool metrics**, and **database capacity**, not just annotation count or raw request count. `T+1` provides a progress path in a single-outer/single-inner model, but does not guarantee latency. Use bounded concurrency, short transactions, proper resource budgeting, integration tests, and clearly distinguish pool starvation from row-lock dependencies.

Preserving exact commit/rollback semantics comes first: do not rely on self-invocation, switch propagations carelessly, or inflate timeouts to mask a resource problem.

## Official References

- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): `REQUIRES_NEW` retaining outer resources, acquiring a new connection, and pool exhaustion warnings.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation, timeout, read-only, and proxies.
- [Spring Framework — JDBC Connections](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceTransactionManager`, `JdbcTransactionManager`, `DataSourceUtils`.
- [HikariCP — README](https://github.com/brettwooldridge/HikariCP): `maximumPoolSize` and `connectionTimeout` configuration.
- [HikariCP — About Pool Sizing](https://github.com/brettwooldridge/HikariCP/wiki/About-Pool-Sizing): anti-pool-locking principles and database limits.
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource autoconfiguration and HikariCP.
