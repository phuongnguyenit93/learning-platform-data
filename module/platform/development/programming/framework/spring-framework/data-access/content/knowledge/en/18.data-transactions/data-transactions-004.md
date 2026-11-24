# Choosing the Same DataSource and Manager for Coordinated Operations

A business operation may require multiple data operations to succeed together: creating an order, deducting inventory, writing an audit entry, or writing an outbox message. When using Spring JDBC, **for those operations to commit or roll back together in a local JDBC transaction, they must participate in the exact same transactional resource**: the `DataSource` controlled by the transaction manager, a transaction-aware way of acquiring connections, and an execution scope actually managed by Spring.

**Sharing the same JDBC URL, the same database, or the same table is not enough to guarantee the same transaction.** Two independently instantiated `DataSource` objects can open two different `Connection`s and commit separately. Similarly, two repositories using the same `DataSource` yet running on different threads or in separate transactions still may not belong to the same unit of commit.

This article focuses on **selecting and wiring the right `DataSource` with the transaction manager for operations that need coordination**, how to verify real behavior in Spring JDBC, configurations that easily break atomicity, and boundaries involving JPA, multiple databases, and external systems.

## 1. Defining What "Coordination" Means

Suppose an application has three steps:

1. Insert `purchase_order` with status `PENDING`.
2. Decrement `inventory.available` after checking sufficient quantity.
3. Insert `order_outbox` so an event can be published after commit.

If all three reside in **one transaction on a transaction-capable database**, an error at step 2 or 3 must roll back the data from all three steps. If commit succeeds, all DB changes in that transaction are accepted together. This is **atomicity of the DB unit of work**, not a guarantee that the downstream event consumer or external payment gateway has finished processing.

When designing, answer three questions:

- **Business boundary:** Which changes must commit/roll back together? Which steps only need retries or separate reconciliation?
- **Resource boundary:** Do they use a single database/transactional resource, or in reality multiple databases, connection factories, or message brokers?
- **Execution boundary:** Do they run through the same Spring-managed transaction, the right manager, and the right context/thread?

Within the scope of **single-resource local JDBC**, the common solution is one unified `DataSource`, `JdbcTemplate`/`NamedParameterJdbcTemplate` using it, and a `JdbcTransactionManager` or `DataSourceTransactionManager` managing **that exact `DataSource`**.

## 2. Distinguishing the Key Components and Responsibilities

| Component | Role | Key Consideration |
| --- | --- | --- |
| `DataSource` (`javax.sql.DataSource`) | Factory supplying JDBC `Connection`s | The resource that both the transaction manager and JDBC data access must use consistently |
| `PlatformTransactionManager` | Starts, commits, rolls back, and defines transaction scope | Must choose an implementation bound to the actual resource type |
| `JdbcTemplate` / `NamedParameterJdbcTemplate` | Executes SQL, manages statements/results, translates JDBC errors | Uses `DataSourceUtils` to obtain the connection bound to the Spring transaction |
| `DataSourceUtils` | Acquires/releases connections with Spring transaction awareness | Do not open connections directly via `dataSource.getConnection()` in DAOs meant to join Spring transactions |
| `TransactionSynchronizationManager` | Manages thread-bound resources/synchronizations in imperative transactions | Used internally by the framework; do not manually bind/unbind resources in normal application code |

`DataSourceTransactionManager` controls a JDBC `Connection` belonging to the chosen `DataSource`. `JdbcTransactionManager` inherits that management and adds JDBC exception translation on commit/rollback to the `DataAccessException` hierarchy when applicable. Both serve the **single-resource JDBC** case; neither coordinates atomic commits across two independent database engines.

With Spring JDBC, a `JdbcTemplate.update(...)` call inside a transaction obtains its connection via `DataSourceUtils.getConnection(dataSource)`. If the matching resource is currently bound to the thread by Spring, JDBC joins that exact connection. When no transaction manages the connection, each operation typically borrows a connection and follows the connection/driver/pool auto-commit rules.

### Same DataSource Does Not Mean the Same Physical Connection Forever

A `DataSource` is a **connection factory**; outside a transaction it can return different connections per call. What is required is that **within the same transaction scope**, operations join the connection already bound to the resource by the manager. Spring manages acquiring/releasing connections, so you should never store a `Connection` in a singleton repository field for reuse across requests.

```text
                 Spring-managed service transaction
                              │
                              ▼
                 JdbcTransactionManager(ds)
                              │
                  thread-bound Connection
                     via DataSourceUtils
                       ┌──────┴──────┐
                       ▼             ▼
                 JdbcTemplate A   JdbcTemplate B
                     (ds)            (ds)
                       │             │
                       └──────┬──────┘
                              ▼
                     same JDBC transaction
                       commit / rollback
```

If `JdbcTemplate B` instead uses `anotherDataSource`, it can open a new connection not controlled by the manager above, even if both datasources use **the exact same username, URL, and database**.

## 3. Standalone Java 17+ Example: Full Rollback and Coordination Failure

This example uses **Spring JDBC + in-memory H2** so results can be observed from a separate connection after each transaction. Neither Spring Boot nor `@Transactional` is required in the demo, because `TransactionTemplate` makes the transaction boundary explicit. How JDBC transactions and `DataSource` work is also the foundation behind `@Transactional` when the right manager is used.

### 3.1. Gradle Configuration

Create `settings.gradle`:

```groovy
rootProject.name = 'jdbc-coordinated-transaction-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.12'
    runtimeOnly 'com.h2database:h2:2.3.232'
}

application {
    mainClass = 'CoordinatedTransactionDemo'
}
```

Use JDK 17+ and a compatible Gradle version. `spring-jdbc` transitively pulls in the required transaction components. H2 is runtime-only because Java code does not import H2 classes directly.

### 3.2. Complete Runnable Program

Create `src/main/java/CoordinatedTransactionDemo.java`:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class CoordinatedTransactionDemo {
    private static final String URL =
        "jdbc:h2:mem:coord_demo;DB_CLOSE_DELAY=-1";

    private CoordinatedTransactionDemo() {}

    public static void main(String[] args) {
        DriverManagerDataSource sharedDataSource = createDataSource();
        JdbcTemplate primaryJdbc = new JdbcTemplate(sharedDataSource);
        JdbcTemplate auditJdbcShared = new JdbcTemplate(sharedDataSource);

        JdbcTransactionManager manager =
            new JdbcTransactionManager(sharedDataSource);
        TransactionTemplate tx = new TransactionTemplate(manager);

        primaryJdbc.execute(
            "CREATE TABLE booking (" +
            "id INT PRIMARY KEY, note VARCHAR(40) NOT NULL)"
        );
        primaryJdbc.execute(
            "CREATE TABLE booking_audit (" +
            "id INT PRIMARY KEY, note VARCHAR(40) NOT NULL)"
        );

        // Correct: both JdbcTemplates participate in the same DataSource/transaction.
        expectRollback(tx, primaryJdbc, auditJdbcShared, 1);
        System.out.println("Shared rollback: " + counts(primaryJdbc));

        // Wrong: same JDBC URL but a different DataSource and separate connection.
        DriverManagerDataSource anotherDataSource = createDataSource();
        JdbcTemplate auditJdbcOther = new JdbcTemplate(anotherDataSource);

        expectRollback(tx, primaryJdbc, auditJdbcOther, 2);
        System.out.println("Different DataSource rollback: " + counts(primaryJdbc));

        // Correct: both operations succeed in one transaction.
        tx.executeWithoutResult(status -> {
            primaryJdbc.update(
                "INSERT INTO booking(id, note) VALUES (?, ?)",
                3, "created"
            );
            auditJdbcShared.update(
                "INSERT INTO booking_audit(id, note) VALUES (?, ?)",
                3, "recorded"
            );
        });
        System.out.println("Shared commit: " + counts(primaryJdbc));
    }

    private static DriverManagerDataSource createDataSource() {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.h2.Driver");
        dataSource.setUrl(URL);
        dataSource.setUsername("sa");
        dataSource.setPassword("");
        return dataSource;
    }

    private static void expectRollback(
        TransactionTemplate tx,
        JdbcTemplate primaryJdbc,
        JdbcTemplate auditJdbc,
        int id
    ) {
        try {
            tx.executeWithoutResult(status -> {
                primaryJdbc.update(
                    "INSERT INTO booking(id, note) VALUES (?, ?)",
                    id, "created"
                );
                auditJdbc.update(
                    "INSERT INTO booking_audit(id, note) VALUES (?, ?)",
                    id, "recorded"
                );
                throw new IllegalStateException("SIMULATED_FAILURE");
            });
            throw new AssertionError("Expected transaction failure");
        } catch (IllegalStateException error) {
            if (!"SIMULATED_FAILURE".equals(error.getMessage())) {
                throw error;
            }
        }
    }

    private static String counts(JdbcTemplate jdbc) {
        Integer bookings = jdbc.queryForObject(
            "SELECT COUNT(*) FROM booking", Integer.class
        );
        Integer audits = jdbc.queryForObject(
            "SELECT COUNT(*) FROM booking_audit", Integer.class
        );
        return "bookings=" + bookings + ", audit=" + audits;
    }
}
```

Run from the directory containing `build.gradle`:

```bash
gradle run --quiet
```

If a suitable Gradle Wrapper is present, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

**Expected stdout of the Java program** (excluding Gradle logs):

```text
Shared rollback: bookings=0, audit=0
Different DataSource rollback: bookings=0, audit=1
Shared commit: bookings=1, audit=2
```

### 3.3. Why Do Those Numbers Appear?

- Run 1: `primaryJdbc` and `auditJdbcShared` both reference **the exact same `sharedDataSource` object**. `JdbcTransactionManager(sharedDataSource)` binds a connection to the thread; both `INSERT` statements join the transaction. The runtime exception rolls back the transaction; recounting after the callback exits yields `0, 0`.
- Run 2: `anotherDataSource` was created **separately**, even though its connection URL is identical. It can still hand out a different `Connection` outside the transaction managing `sharedDataSource`. In the demo configuration, `auditJdbcOther`'s statement runs with auto-commit, so the audit row with `id=2` committed; meanwhile `booking id=2` created by `primaryJdbc` rolled back. The outcome `0, 1` is a **partial write** state, not a complete rollback.
- Run 3: both `JdbcTemplate`s share the same datasource; the callback finishes without error and `TransactionTemplate` commits. At this point one `booking id=3` and its matching audit row are saved. **The audit row id=2 from the earlier failed run still exists**, so the counts are `1, 2`, not `1, 1`.
- `DB_CLOSE_DELAY=-1` keeps the H2 database in memory for the JVM's lifetime so new connections still see the same database. Precisely because both datasources access **the same database**, the example highlights that **same database is different from same transaction**.

**Limitations of the example:** H2 permits these simple operations, yet locking, auto-commit behavior, and reactions to DDL can differ from real DBMSs. For real systems, test against the actual database, driver, and connection pool in use. `DriverManagerDataSource` creates simple connections for learning; production typically uses a pool like HikariCP.

## 4. Properly Wiring Beans in a Spring Application

Usually, define **a single `DataSource` bean** as the connection source for the group of operations needing coordination, build repositories/templates on that bean, and create the transaction manager controlling that exact bean. Example Spring structure (the DAO methods are illustrative, not a standalone program):

```java
@Configuration
@EnableTransactionManagement
public class BookingJdbcConfig {
    @Bean("bookingDataSource")
    public DataSource bookingDataSource() {
        // In practice, configure pool/credentials via properties and secrets.
        HikariDataSource pool = new HikariDataSource();
        pool.setJdbcUrl("jdbc:postgresql://localhost:5432/booking");
        pool.setUsername("booking_app");
        // Password supplied by a secure configuration system.
        return pool;
    }

    @Bean("bookingJdbc")
    public JdbcTemplate bookingJdbc(
        @Qualifier("bookingDataSource") DataSource dataSource
    ) {
        return new JdbcTemplate(dataSource);
    }

    @Bean("bookingTransactionManager")
    public PlatformTransactionManager bookingTransactionManager(
        @Qualifier("bookingDataSource") DataSource dataSource
    ) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

The snippet above requires Spring Configuration/Bean/Qualifier imports, `DataSource`, `HikariDataSource`, `JdbcTemplate`, `PlatformTransactionManager`, and `JdbcTransactionManager`; it requires HikariCP/driver dependencies and real credentials configuration. It **illustrates wiring** so it has no standalone bootstrap code, and sample database values should not be used in production.

A service can coordinate two repositories that both use `bookingJdbc`:

```java
@Service
public class BookingService {
    private final BookingRepository bookings;
    private final InventoryRepository inventory;

    public BookingService(
        BookingRepository bookings,
        InventoryRepository inventory
    ) {
        this.bookings = bookings;
        this.inventory = inventory;
    }

    @Transactional(transactionManager = "bookingTransactionManager")
    public long reserve(ReserveCommand command) {
        long bookingId = bookings.insertPending(command);

        int changed = inventory.tryReserve(
            command.sku(), command.quantity()
        );
        if (changed != 1) {
            throw new IllegalStateException("OUT_OF_STOCK");
        }

        bookings.markReserved(bookingId);
        return bookingId;
    }
}
```

`BookingRepository`, `InventoryRepository`, and `ReserveCommand` are domain types to be defined in the project; this snippet only illustrates the service boundary. If both repositories use `bookingJdbc`, the manager is configured on that datasource, and `@Transactional` is genuinely applied by the proxy, the JDBC statements will participate in the transaction according to the active propagation.

**Especially important:** if there are **multiple transaction managers** in the Spring context, use `@Transactional("bookingTransactionManager")` or `@Transactional(transactionManager = "bookingTransactionManager")` to specify the manager for the service. Do not assume Spring will always pick the manager matching the datasource a repository happens to use.

In Spring Boot, auto-configuration usually creates datasources/transaction managers based on dependencies and properties when eligible. However, when an application defines multiple beans, auto-configuration can change. Verify **which bean is actually injected**, rather than just checking names in a YAML file and assuming they are synchronized.

## 5. Transaction Boundaries of `@Transactional`

Even after selecting the right datasource and manager, the following conditions must hold:

### 5.1. Must Go Through the Spring Proxy

`@Transactional` in default proxy mode only takes effect when a call passes **through the Spring-managed proxy**. Example:

```java
@Service
public class TransferService {
    public void process() {
        reserve(); // this.reserve(): internal call, bypasses proxy.
    }

    @Transactional(transactionManager = "bookingTransactionManager")
    public void reserve() {
        // JDBC write ...
    }
}
```

Calling `process()` externally does not cause the internal `reserve()` call to automatically gain a transaction from `reserve`'s annotation. Place the `@Transactional` boundary on the service method called through the proxy, move it to another bean, or use `TransactionTemplate` when an explicit boundary is needed. Do not assume a transaction is active merely because an annotation appears in source code.

### 5.2. Propagation Can Change the Unit of Commit

- `REQUIRED` (default): joins an existing transaction if suitable; opens a new one otherwise. If joining an outer transaction, **method return does not mean the outer transaction has committed**.
- `REQUIRES_NEW`: creates an independent transaction, suspending the current one; changes committed in the inner transaction do not automatically roll back with the outer transaction later. An event/audit in `REQUIRES_NEW` may still remain when the main operation rolls back.
- `NESTED`: with JDBC managers and a database/driver supporting savepoints, allows partial rollback to a savepoint. `NESTED` is not synonymous with `REQUIRES_NEW`, and is not available on every transaction manager/provider.
- `SUPPORTS`, `NOT_SUPPORTED`, `NEVER`, or `MANDATORY` affect whether a transaction actually exists. Check propagation at every entry point before concluding operations are "in the same group."

Two methods using the same datasource **do not guarantee** sharing a transaction if one method deliberately opens a separate transaction.

### 5.3. Errors Must Reach the Rollback Boundary

By Spring default, `RuntimeException` or `Error` rolls back a declarative transaction, whereas checked exceptions normally do not trigger rollback without `rollbackFor` or a custom policy.

```java
@Transactional(
    transactionManager = "bookingTransactionManager",
    rollbackFor = IOException.class
)
public void importOrders() throws IOException {
    // DB writes and reading source that may throw IOException.
}
```

This is an illustrative declaration requiring imports/types and real logic. If code catches an error and returns "success" without rethrowing or marking rollback-only, the manager may commit the data already written. Use domain exceptions and appropriate rollback rules; if you need to continue after an error, design a consistent state rather than swallowing errors unchecked.

### 5.4. Imperative Transactions Are Thread-Bound

A JDBC `PlatformTransactionManager` uses thread-bound resource state. Work dispatched via `@Async`, `new Thread(...)`, `CompletableFuture.supplyAsync(...)`, or an executor **does not automatically inherit the calling thread's JDBC transaction**. A `JdbcTemplate` invoked in a worker thread may open its own connection even when using the same datasource.

With reactive `R2dbcTransactionManager`, transactions use **Reactor Context** and an R2DBC `ConnectionFactory`; do not arbitrarily combine them with a JDBC `DataSource` and expect them to commit together. If the architecture genuinely needs coordination across asynchronous boundaries, use stateful workflows, outbox, retries, or suitable transaction infrastructure.

## 6. Common Mistakes When Selecting a DataSource/Manager

| Situation | What Can Happen | How to Fix or Verify |
| --- | --- | --- |
| Two datasources created via `new ...DataSource()` with the same JDBC URL | Two independent connections/transactions | Inject and reuse the same datasource bean or a compatibly designed proxy |
| Manager for `ordersDataSource`, DAO uses `reportingDataSource` | DAO does not join the transaction on the right resource | Check `@Qualifier`, `JdbcTemplate.getDataSource()`, and bean wiring |
| Calling `dataSource.getConnection()` directly in manual code | Bypasses transaction-aware connection lookup | Use `JdbcTemplate` or `DataSourceUtils.getConnection/releaseConnection` |
| Creating `JdbcTemplate(new DriverManagerDataSource(...))` inside a repository | Has a private datasource outside shared config, prone to auto-commit | Constructor injection of the chosen `DataSource` bean |
| Two independent `PlatformTransactionManager`s for the same sequence | May commit or roll back separately, unpredictable behavior | Pick one owner for a unit of work; do not layer managers arbitrarily |
| Internal `@Transactional` via `this.method()` | Advice does not run in proxy mode | Place transaction on public entry point via Spring bean proxy |
| Inner `REQUIRES_NEW` or `@Async` | Not in the same physical transaction | Use only when intentionally separating transactions; test rollback |
| Mixing JPA and JDBC with an incompatible manager | JDBC and EntityManager may not share a boundary | Configure `JpaTransactionManager` with matching `EntityManagerFactory`/`DataSource`, run integration tests |
| Two databases, two pools, two services | One local JDBC manager cannot guarantee atomicity across both | Consider JTA/XA if distributed transactions are truly needed, or outbox/saga |
| Calling a stored routine with implicit commit/DDL | Transaction may end unexpectedly | Check DBMS/DDL/routine behavior, test specific rollback behavior |

### `TransactionAwareDataSourceProxy` and `LazyConnectionDataSourceProxy`

Do not conclude "bean/instance names must be identical in every case" while overlooking Spring's **specialized proxies**:

- `TransactionAwareDataSourceProxy` helps **legacy JDBC code calling `DataSource.getConnection()`** receive transaction-aware connections and follow Spring close handling. When paired with `DataSourceTransactionManager`, the manager should normally receive the **target `DataSource`**, avoiding redundant wrapping.
- `LazyConnectionDataSourceProxy` defers acquiring a physical connection; it can help transactions that do not actually touch the DB and coordinate transaction-aware routing. When used, the manager and data-access layer must be configured with the exact wrapper/target chain specified by Spring documentation.
- With `AbstractRoutingDataSource`, tenant/primary/replica selection depends on routing context. If the routing key changes mid-transaction, an already acquired connection may still point to the initial source. Determine the route before starting the transaction and test consistently.

Practical takeaway: **reuse the exact datasource bean or an intentionally Spring-supported wrapper configuration**, rather than creating separate connection factories just because the URLs match.

## 7. Mixing Multiple Technologies: JDBC, JPA, Multiple DBs

### 7.1. JDBC + JPA in the Same Database

If the same business operation calls both a JPA repository and `JdbcTemplate`, do not swap `JpaTransactionManager` for `JdbcTransactionManager` and assume `EntityManager` still participates as before.

`JpaTransactionManager` can support JDBC joining the same JPA transaction when `EntityManagerFactory`, `DataSource`, and the JPA provider's connection access mechanism are properly configured. Spring explicitly documents that `DataSourceUtils` supports connections bound to `JpaTransactionManager` under appropriate conditions. **Real testing is essential** with your provider, driver version, and datasource configuration: JPA `flush`, when ORM SQL is sent to the DB, and transaction isolation can affect observed behavior.

When a service primarily performs JPA operations, choose the manager suited for JPA and configure the JDBC part to join the right resource; when everything is JDBC against one database, `JdbcTransactionManager` is usually simpler. Do not choose based on an ambiguous "transactionManager" name.

### 7.2. Two Truly Independent DataSources

A local `DataSourceTransactionManager` manages connections for **only one datasource**. If a business operation must write to database A and database B, even if each manager works properly, A's commit can succeed while B fails.

There are two classes of solutions, chosen by consistency requirements:

1. **True distributed transactions:** use a JTA/XA transaction coordinator and compatible XA resources/drivers if supported by your product and infrastructure. Two-phase commit carries overhead, failover limitations, and operational cost; it does not appear automatically just by declaring two `@Transactional` annotations.
2. **Controlled eventual consistency:** use transactional outbox, event relays, idempotency, retries/reconciliation, and sagas/compensations to handle separate systems. Design intermediate states and duplicate/failure cases.

A sequence of local transactions called sequentially or "chained" **does not become an atomic distributed transaction** because there is no XA-style commit coordination.

### 7.3. Email, HTTP, Payments, and Message Brokers

Even when all SQL statements belong to the same datasource, external API calls **do not automatically roll back** with the database. Do not keep a DB transaction open too long waiting on a slow HTTP API and mistake that for atomicity. You can write an outbox record inside the data transaction and publish independently; consumers need idempotency. An `AFTER_COMMIT` event listener avoids acting before commit, yet **does not replace** durable delivery guarantees if the process crashes after commit.

## 8. How to Properly Observe an Active Transaction

When suspecting a DAO is not inside a transaction, you can temporarily log the state exposed by Spring:

```java
// Diagnostic snippet placed inside a JDBC/service call.
boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();

boolean boundToExpectedDataSource =
    TransactionSynchronizationManager.hasResource(expectedDataSource);
```

This requires importing `org.springframework.transaction.support.TransactionSynchronizationManager` and having an appropriate `DataSource expectedDataSource`. These two checks are useful for narrowing down issues, **not final proof that all statements committed or that all DAOs share a connection**. You must inspect actual commit/rollback outcomes, propagation, routing, and the transaction manager type.

Investigation checklist:

1. Determine whether the public entry point is called through a Spring proxy or raw code; which method carries the annotation?
2. Identify **the exact manager name selected** (is there a `@Transactional(transactionManager="...")` qualifier?).
3. Trace `JdbcTemplate`, `NamedParameterJdbcTemplate`, and repository objects back to the real `DataSource` bean and any wrappers.
4. Confirm execution stays on the same thread/context, does not jump across `@Async`, and does not use propagation that unexpectedly splits transactions.
5. Enable transaction logging **in development environments**, such as `org.springframework.transaction` and `org.springframework.jdbc.datasource` at an appropriate DEBUG level; avoid logging sensitive SQL parameters or credentials.
6. Create a test that deliberately triggers a failure after writing in two places, then query again **after the transaction ends** from an independent connection. Only this test gives strong evidence of end-to-end rollback across the group of operations.

Treat `DataSourceUtils` as Spring's scoped way to access connections; avoid manually calling `getConnection()`, `commit()`, or `rollback()` inside manager-controlled code, as doing so easily breaks ownership rules and transaction termination timing.

## 9. Designing Valuable Integration Tests

An integration test suite for coordinated operations should verify these scenarios:

| Scenario | What to Verify |
| --- | --- |
| All statements succeed | Both primary and secondary records appear together after commit |
| Error in the second step | First step's record is gone after rollback; no secondary data remains |
| Error in the final step | All earlier steps roll back together; no partial state left behind |
| Repository pointed to wrong datasource | Test catches a secondary record committing even when the main business operation rolls back |
| `@Transactional` hit by self-invocation | Test reveals rollback is not applied as expected; fix entry point and retest |
| `REQUIRES_NEW` used intentionally | Verify inner commit persists even when outer rolls back; state matches contract |
| Checked exceptions | Verify `rollbackFor`/rollback rules, not just annotation presence |
| Multi-DB or external systems | Verify compensation/retry/outbox and inter-step failure handling, without expecting a local manager to cover everything |

With Spring Test, note that a test method annotated with `@Transactional` may automatically roll back at the end of the test. That is convenient for data isolation yet can **hide bugs at the service's actual commit boundary**. When you need to prove post-commit state, structure the test outside the default test transaction or use Spring Test utilities (e.g., `TestTransaction`) to end the transaction and query back. With multiple pools or databases, tests must run against the same infrastructure types and proxy/routing configuration as production.

Checks relying solely on `TransactionSynchronizationManager.isActualTransactionActive()` or `id != null` are insufficient: a transaction can be active on datasource A while DAO B still writes via auto-commit through another datasource.

## 10. Practical Workflow for Choosing Configuration in Real Projects

Apply in order:

1. **List the operations that must commit/roll back together.** If all use a single transaction-capable DB, prefer one local JDBC transaction wrapping them.
2. **Choose a single managed `DataSource` for that JDBC group.** Configure pool, routing, and credentials in one place; inject the chosen bean into every related `JdbcTemplate`.
3. **Create/locate the manager for that exact resource.** Pure JDBC can use `JdbcTransactionManager(ds)` or `DataSourceTransactionManager(ds)`; when JPA is present, consider `JpaTransactionManager` with matching provider/source.
4. **Place boundaries on meaningful business service methods.** Use `@Transactional(transactionManager="...")` via proxy or `TransactionTemplate`, checking propagation on inner calls.
5. **Keep connection access Spring-compatible.** Use templates or `DataSourceUtils`; avoid manual connections, extra managers, and unexpected thread switches.
6. **Define failure signals.** Check row counts, business conditions, and exceptions; let rollback happen properly. Do not infer business completion from a newly generated ID.
7. **Verify commit/rollback with integration tests.** Deliberately induce errors between statements and inspect post-transaction state from a separate connection.
8. **Choose strategies for anything beyond one DB.** JTA/XA when distributed atomicity is genuinely required; outbox/saga/idempotency/retries when implementing distributed workflows.

**Remember:** For Spring JDBC operations to share one local transaction, align **the right Spring-managed `DataSource`/connection, the right transaction manager, and the right execution scope**. Matching JDBC URLs, the same database name, or the same `@Transactional` annotation alone does not prove they share commit/rollback outcomes.

### References

- [Spring Framework 6.2 — JDBC connections and DataSourceUtils](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/connections.html)
- [Spring Framework — Transaction abstraction](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring Framework — Synchronizing resources with transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)
- [Spring Framework 6.2 — Using @Transactional and selecting among multiple managers](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Understanding transaction proxy](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — DataSourceTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html)
- [Spring Framework — JdbcTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/support/JdbcTransactionManager.html)
