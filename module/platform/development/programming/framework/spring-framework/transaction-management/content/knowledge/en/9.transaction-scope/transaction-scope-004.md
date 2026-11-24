# Which Attributes Are Applied When Creating a New Transaction in Spring?

In Spring Framework, `@Transactional` describes a **transaction request**; `PlatformTransactionManager` is the component that decides whether to start a **new physical transaction** or join an existing one. When a new transaction is opened, the manager has the opportunity to apply **isolation**, **timeout**, **readOnly**, as well as management metadata such as the **transaction name**, depending on the capabilities of the datasource, driver, database, and transaction manager. **Propagation** decides whether to create new, join, or suspend; **rollback rules** decide the outcome when the call ends with an exception, even in a scope that merely joins an existing transaction.

The most important point in this **Transaction Scope** lesson:

> With `PROPAGATION_REQUIRED`, if an outer transaction already exists, the inner scope normally inherits the characteristics of the **outer physical transaction**. Different isolation, timeout, and read-only requests on the inner scope **do not reconfigure** that physical transaction. With `REQUIRES_NEW`, Spring suspends the outer transaction and starts an independent transaction, so the inner attributes have the opportunity to apply to the new transaction.

Therefore, the question must be answered **attribute by attribute**; one should not mistakenly conclude either that every field of `@Transactional` is ignored when joining, or that every annotation means a new transaction.

## 1. Model: request, logical scope, physical transaction, and outcome

There are four concepts:

1. **`TransactionDefinition`**: the request contract before a scope starts, including propagation, isolation, timeout, read-only, and name.
2. **`TransactionAttribute`**: extends the definition for declarative transactions; adds exception handling rules and metadata needed by the advice.
3. **`TransactionStatus`**: the status object returned by the manager for a `getTransaction(...)` call; indicates whether the scope has a new transaction, is rollback-only, or is completed.
4. **Physical transaction**: the actual transaction on the JDBC connection, JPA resource, or corresponding infrastructure.

Example with two Spring beans:

```text
HTTP request / message
       |
       v
OrderService.createOrder()        logical scope A: REQUIRED
       |                          start physical T1
       |
       +--> StockService.reserve() logical scope B: REQUIRED
       |                           join physical T1
       |
       +--> InvoiceService.save()  logical scope C: REQUIRED
                                   join physical T1

T1: begin ----------------------------------- commit or rollback
```

There are three **logical scopes** but only one **physical transaction** T1. If B and C declare their own `timeout` or `isolation`, they do not become two new physical transactions to pick those settings independently.

Same flow, but `StockService.reserve()` uses `REQUIRES_NEW`:

```text
T1 outer:        begin -------- suspend ------ resume -------- commit
T2 stock:                        begin -- commit/rollback
```

T2 has its own transaction manager status and configuration capability, though it may require a second JDBC connection. An already committed T2 is not automatically rolled back by outer T1; business consistency design must account for that independence.

## 2. Quick answer table by attribute group

| Configuration / attribute | When a new physical transaction is created | When the method joins an existing transaction |
| --- | --- | --- |
| `propagation` | Used to decide **whether to create new** | Still evaluated to choose join, suspend, nested, forbid, or require a transaction |
| `isolation` | Manager attempts to set the requested isolation level | Normally follows outer's isolation; does not automatically alter T1 |
| `timeout`, `timeoutString` | Can set a new timeout/deadline if supported by backend | Does not reset outer's timeout/deadline |
| `readOnly` | Manager/provider can pass a hint or read-only optimization | Follows outer transaction properties; does not toggle T1 between read-only/read-write |
| Transaction name | Metadata name attached when starting an appropriate scope/transaction | Joining scope normally does not rename the outer physical transaction |
| `label` | Manager may handle labels in its own way | Not guaranteed that every manager uses labels to alter physical attributes |
| `transactionManager` / `value` | Selects the manager and resource handling begin | Still determines **which manager** is used to look up the transaction to join |
| `rollbackFor`, `noRollbackFor` | Applied when the interceptor decides rollback/commit | **Still applied** when an exception escapes the inner logical scope, potentially marking T1 rollback-only |

In the `@Transactional` documentation, Spring describes isolation, timeout, and read-only as settings primarily intended for `REQUIRED` and `REQUIRES_NEW` because they only take physical effect when starting a transaction. In particular, `readOnly` can also be used as metadata/a hint for some resource contexts **without a physical transaction** (such as `SUPPORTS` in certain situations), so a hint must be distinguished from a database-level change.

**In short:** the three attributes most frequently misunderstood are `isolation`, `timeout`, and `readOnly`. Two settings that should not be put into an "only applies when new" bucket are `propagation` and **rollback rules**.

## 3. Propagation is the first decision

By default `@Transactional` uses `Propagation.REQUIRED`. Before asking "which isolation applies?", determine what the scope's propagation does.

| Propagation | No existing transaction | Existing transaction |
| --- | --- | --- |
| `REQUIRED` | Starts a new T1 | Joins T1 |
| `REQUIRES_NEW` | Starts a new T1 | Suspends T1, starts a separate T2 |
| `SUPPORTS` | Runs without a physical transaction | Joins T1 |
| `MANDATORY` | Throws missing-transaction error | Joins T1 |
| `NOT_SUPPORTED` | Runs non-transactionally | Suspends T1, runs non-transactionally |
| `NEVER` | Runs non-transactionally | Throws error because T1 is active |
| `NESTED` | May start a transaction when none exists, per manager | Usually uses a savepoint within T1 when supported |

`NESTED` is **not synonymous** with `REQUIRES_NEW`: when T1 already exists, a nested scope typically still shares one physical transaction and rolls back to a savepoint. A savepoint does not create a new JDBC isolation level for the inner block. Some managers/resources that do not support nested transactions or savepoints will throw an error.

`NOT_SUPPORTED` can activate logical synchronization even without a physical transaction. Do not take `isSynchronizationActive()` as proof that SQL inside this scope will roll back together.

`REQUIRES_NEW` can hold outer's connection while borrowing another connection for inner, so the connection pool needs sufficient headroom. If an independent transaction is created solely to change isolation, consider pool cost, deadlocks, data consistency, and the real transaction count.

## 4. Isolation: attribute at the start of a physical transaction

Isolation determines to what degree one transaction observes changes made by another transaction. In `@Transactional`, the default value is `Isolation.DEFAULT`, meaning **use the backend's default**, not `READ_COMMITTED` by default for every database.

| Level | General meaning |
| --- | --- |
| `READ_UNCOMMITTED` | May allow dirty reads if the backend actually supports it |
| `READ_COMMITTED` | Does not read uncommitted data; later reads may see newly committed values |
| `REPEATABLE_READ` | Restricts already-read data from changing within a transaction, depending on MVCC/locking |
| `SERIALIZABLE` | Aims for effects equivalent to a serial schedule, often with overhead/serialization conflicts |

Details of phantoms, snapshots, locks, and upgrading or downgrading isolation levels depend on the database; do not treat this overview table as a substitute for PostgreSQL, MySQL/InnoDB, SQL Server, or H2 documentation.

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE
)
public void calculateClosingBalance() {
    // Business logic requiring consistency
}
```

This is an **illustrative fragment**, not independently compilable. If no transaction exists, `REQUIRED` starts T1 and the JDBC transaction manager can configure connection isolation before executing SQL. If T1 already exists at `READ_COMMITTED`, the call only joins T1: inner `SERIALIZABLE` **does not upgrade T1's isolation** by default.

### 4.1. Why not change isolation mid-transaction?

Because inner `REQUIRED` still uses the same physical transaction. The isolation level belongs to the properties the manager/backend applies to that transaction; the appearance of a new logical scope does not automatically split T1 into two independent transactions. In fact, on some databases, changing isolation mid-transaction has restrictions or fails.

If the use case genuinely needs `SERIALIZABLE`, consider placing the annotation on the **boundary that opens T1**. If a piece of work must be independent and can be separated functionally, `REQUIRES_NEW` can be used to open T2 with its own isolation; do not use `REQUIRES_NEW` mechanically just to avoid redesigning boundaries.

### 4.2. How far does DB-enforced isolation go?

The JDBC manager can call `Connection.setTransactionIsolation(...)`, but actual support and semantics are provided by the driver/backend. `SERIALIZABLE` does not mean the application never has to retry; some databases return serialization failures. For concurrent correctness requirements, write integration tests with two real concurrent transactions.

## 5. Timeout: a new deadline only when there is a new transaction

`@Transactional(timeout = 20)` requests a timeout in **seconds** for a matching transaction. If the manager is opening a new T1, it attempts to record the deadline via its infrastructure. If an inner `REQUIRED(timeout=2)` joins T1 which already started 50 seconds ago with a 60-second timeout, inner does not create a new "2-second transaction" and **does not reset** T1's deadline.

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    timeout = 8
)
public void reserveExternalNumber() {
    // Call intercepted by Spring advice, new T2 if valid
}
```

This is an illustrative fragment; `REQUIRES_NEW` can start an independent transaction with its own timeout, after which the outer transaction is resumed.

Since Spring 5.3, `timeoutString` supports string or placeholder configuration:

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    timeoutString = "${tx.order.timeout:15}"
)
public void confirmOrder() {
    // ...
}
```

This is a fragment requiring Spring property resolution at runtime. The resolved value must be valid in seconds. Use **one** of `timeout` or `timeoutString` on a method to avoid conflicting configuration.

### 5.1. Timeout is not always an immediate CPU interrupt at second N

Different `PlatformTransactionManager`s apply timeouts differently:

- With Spring JDBC, the deadline can be stored on the resource and applied as a query timeout through `JdbcTemplate`/`DataSourceUtils` when creating a `Statement`.
- With JPA, the timeout mechanism depends on the transaction manager, JPA provider, and JDBC driver.
- Some backends do not support custom timeouts and may reject the request or apply it only partially.
- `Thread.sleep()` or pure Java computation is not guaranteed to throw an exception right at the timeout mark.

Therefore, do not test timeout by sleeping and concluding Spring always "kills" the thread at exactly 8 seconds. Verify with actual statements/resources and observe the exception type returned by the backend.

### 5.2. Suspend does not mean pausing outer's clock

An inner `REQUIRES_NEW(timeout=5)` runs while T1 is open: T1 may be suspended from the thread, but that is not a promise to extend or refresh T1's timeout. If the overall workflow must finish within a fixed window, the overall deadline and retries must be designed at the use-case level.

## 6. Read-only: hint when creating a physical transaction

`readOnly=true` indicates that the code **is not expected to write** within the transaction. With JDBC, the manager can call `Connection.setReadOnly(true)`; with JPA/Hibernate, the provider can apply optimizations for the persistence context or flush handling.

```java
@Transactional(readOnly = true)
public List<OrderView> listOrders() {
    // Query via repository
}
```

This is a fragment requiring classes/methods/repositories in an application. If `listOrders()` starts a new transaction, the read-only hint can be applied when the resource is prepared. If the method merely joins a read-write T1, inner `readOnly=true` **does not turn T1 into read-only**.

The reverse is also important: outer `readOnly=true` followed by inner `@Transactional(REQUIRED, readOnly=false)` **does not turn T1 into read-write**. The manager can still maintain outer's metadata/read-only state and, when strict validation is enabled, reject certain mismatches.

### 6.1. Read-only is not a permission system

`readOnly=true` may only be a hint; some drivers/DBs do not forbid every `UPDATE` statement. To block writes for security, use database permissions and real tests. Do not treat a query succeeding or `Connection.isReadOnly()` as sufficient testing for the whole backend.

### 6.2. Note on `SUPPORTS`

A `SUPPORTS(readOnly=true)` scope without a physical transaction can still supply read-only metadata to some managed resources in the application context. However, you cannot conclude from this that a new JDBC transaction has started or that SQL statements will roll back together. This is the difference between **metadata/hint** and **physical transaction configuration**.

## 7. Transaction name and labels

`TransactionDefinition` includes a transaction name for logging, tracing, or monitoring. When using programmatic transactions, you can call:

```java
DefaultTransactionDefinition def =
        new DefaultTransactionDefinition();
def.setName("billing.endOfDay");
TransactionStatus status = txManager.getTransaction(def);
```

This is an **illustrative fragment**; `txManager` must be a suitable bean and `status` must be committed/rolled back exactly once after the work. The name is Spring metadata, not a database-supplied ID.

With declarative `@Transactional`, Spring normally auto-generates the name from **fully qualified class + method**, such as `com.example.PaymentService.charge`. The annotation **does not have** a `name` attribute to set arbitrarily like `DefaultTransactionDefinition.setName()`.

If an inner `REQUIRED` simply joins T1, do not expect the transaction name attached to outer to automatically change to inner's name. In imperative transactions, you can inspect `TransactionSynchronizationManager.getCurrentTransactionName()` for diagnostics.

`@Transactional(label = {"billing", "priority"})` supplies labels to the transaction manager. Managers can interpret labels according to their implementation; **there is no general rule** that labels change isolation, read-only, or timeout across all databases.

## 8. `transactionManager` qualifier: selected whether new or joining

An application may have multiple transaction managers:

```java
@Transactional(transactionManager = "ordersTxManager")
public void reserveOrder() {
    // Uses the manager with the matching bean name or qualifier
}
```

This is a fragment. `transactionManager` or its alias `value` selects the manager used for the transactional invocation. That decision is made even when the manager finds an existing transaction to join.

If a system has two independent datasources, selecting the manager for datasource A does not automatically cause operations on datasource B to roll back together. Achieving multi-resource consistency requires an appropriate mechanism such as JTA/XA when genuinely needed, or outbox/saga/compensation by architecture.

Another mistake is a DAO obtaining a JDBC connection directly from another datasource instead of through a `JdbcTemplate`/`DataSourceUtils` compatible with the manager. Then you may see Spring logs opening T1, while the SQL you observe auto-commits outside T1.

## 9. Rollback rules still matter when only joining a transaction

`rollbackFor` and `noRollbackFor` are not connection isolation settings. They are **advice rules evaluated when the method terminates with an exception**.

Under Spring 6.2's standard default configuration:

- A `RuntimeException` or `Error` escaping the transactional invocation triggers rollback.
- A checked `Exception` normally does not trigger rollback by default.
- This can be customized with `rollbackFor` and `noRollbackFor`.
- Since Spring 6.2, there is a global default option such as `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)`; check the actual application configuration.

```java
@Transactional(
    propagation = Propagation.REQUIRED,
    rollbackFor = java.io.IOException.class
)
public void importData() throws java.io.IOException {
    // Throws IOException outside the transactional boundary on import error
}
```

This is an illustrative fragment. Suppose this method joins T1; when `IOException` escapes the inner transaction advice and matches the rollback rule, the manager can mark the shared transaction **rollback-only**. If outer catches `IOException` and returns normally, outer can still hit `UnexpectedRollbackException` at commit because T1 was already marked.

In other words, rollback rules **are still applied on the participating logical scope**, unlike the isolation/timeout/read-only settings of a new physical transaction. Do not lump everything into an "ignored when `isNewTransaction=false`" bucket.

### 9.1. Exceptions caught and swallowed inside the method

If an exception is thrown and caught without escaping the transactional advice, the interceptor can follow the normal return path. When business logic truly needs a rollback while still returning a normal value, `TransactionStatus.setRollbackOnly()` can be used in the appropriate scope; the caller must be informed that the operation did not commit.

`setRollbackOnly()` only marks the state; it does not undo SQL at the exact line of the call. The transaction manager handles rollback when the boundary completes. `isCompleted()` indicates the scope has finished, **not** that the outcome was a commit.

## 10. `validateExistingTransaction`: checking mismatches instead of silently ignoring them

Some transaction managers extending `AbstractPlatformTransactionManager` provide:

```java
JdbcTransactionManager manager = new JdbcTransactionManager(dataSource);
manager.setValidateExistingTransaction(true);
```

This is an illustrative fragment. The API uses **`setValidateExistingTransaction`** (singular method name); `dataSource` must exist. By default this validation is `false`: inner `REQUIRED` typically joins T1 leniently and does not impose its own isolation/timeout/read-only onto T1.

When enabled, Spring can reject participation with **incompatible isolation**, and reject a **read-write inner** attempting to join a **read-only outer**, instead of silently using outer's characteristics. It does not convert an active transaction into one with a new isolation level; nor does it grant inner its own timeout.

Example:

```text
OUTER T1: REQUIRED, isolation=READ_COMMITTED, readOnly=false
      |
      +-- INNER REQUIRED, isolation=SERIALIZABLE, readOnly=true
```

- Lenient: INNER joins T1, actually using T1's `READ_COMMITTED` and read-write mode.
- Strict validation: INNER may be rejected because its `SERIALIZABLE` isolation request does not match T1, before inner's business body runs.

**Do not assume validation is symmetric in every direction**: a read-only inner wishing to join a read-write outer is not necessarily rejected solely because of read-only; the clearest case documented by Spring is a **read-write inner joining a read-only outer**. Validation is not a way to alter T1's attributes—it only helps catch mismatched expectations early.

## 11. Transaction managers and backends can apply things differently

| Manager / resource | What to verify |
| --- | --- |
| `JdbcTransactionManager` / `DataSourceTransactionManager` | Isolation/read-only via JDBC connection on start, timeout/query timeout via Spring JDBC, commit/rollback with the connection |
| `JpaTransactionManager` | JPA `EntityManager`/persistence provider, flush behavior, and ability to apply isolation/timeout depend on provider/dialect |
| `JtaTransactionManager` | Container/provider transaction infrastructure; do not assume every isolation request can be set per transaction |
| Reactive transaction manager | Uses Reactor Context instead of thread-bound JDBC transactions; needs appropriate reactive resources and APIs |

A manager may reject an isolation level or timeout it does not support. `Isolation.DEFAULT` does not always mean `READ_COMMITTED`. `readOnly=true` is only a hint unless a specific integration/backend strictly enforces it.

Logical flow when **creating a new physical transaction**:

```text
Transaction advice / TransactionTemplate
       |
       v
transactionManager.getTransaction(definition)
       |
       +-- evaluate propagation and active transaction
       +-- if creating new: acquire resource/connection
       +-- configure isolation, read-only when supported
       +-- set deadline/timeout metadata
       +-- bind transaction resource & synchronization
       |
       v
Business method + repository/DAO
       |
       v
commit or roll back based on outcome and rollback-only
       |
       v
clean up resources, restore connection state
```

This is a conceptual diagram and does not describe every exact step across all `PlatformTransactionManager` implementations.

To verify, do not look only at `@Transactional` attributes in source code: determine **which manager is selected**, which resource is being used, whether the transaction is new, and how the DB actually commits/rolls back.

## 12. Standalone Java 17 example: REQUIRED joining and REQUIRES_NEW opening a transaction

This example uses **Java 17+**, **Maven 3.9+**, **Spring Framework 6.2.19**, and in-memory H2. It focuses on three scopes:

1. OUTER: `REQUIRED`, no existing transaction so it opens **T1** with `READ_COMMITTED`, read-write, 30-second timeout.
2. JOIN: `REQUIRED` requests `SERIALIZABLE`, read-only, 1-second timeout, yet **joins T1**.
3. NEW: `REQUIRES_NEW` requests `SERIALIZABLE`, read-only, 5-second timeout, so it opens an independent **T2** and then returns control to T1.

The program checks `TransactionStatus.isNewTransaction()` and imperative metadata from `TransactionSynchronizationManager`. **Timeouts are not measured in the output**: testing timeout requires a real operation on a suitable resource/backend.

### 12.1. Structure and dependencies

```text
tx-attributes/
├── pom.xml
└── src/main/java/demo/TxScopeDemo.java
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
    <artifactId>tx-attributes</artifactId>
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

`spring-context` provides IoC/configuration, `spring-jdbc` provides `JdbcTemplate`, the JDBC transaction manager, and related transaction dependencies. H2 is a runtime-only JDBC database. Spring Boot auto-configuration is not needed to understand the example.

### 12.2. Single-file source code

File `src/main/java/demo/TxScopeDemo.java`:

```java
package demo;

import java.sql.Connection;
import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionStatus;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Configuration
@EnableTransactionManagement
public class TxScopeDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:scope_demo;DB_CLOSE_DELAY=-1");
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

    @Bean
    InnerService innerService() {
        return new InnerService();
    }

    @Bean
    OuterService outerService(InnerService inner, JdbcTemplate jdbc) {
        return new OuterService(inner, jdbc);
    }

    public static void main(String[] args) {
        try (var ctx =
                     new AnnotationConfigApplicationContext(TxScopeDemo.class)) {

            JdbcTemplate jdbc = ctx.getBean(JdbcTemplate.class);
            jdbc.execute("""
                    CREATE TABLE wallet (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update("INSERT INTO wallet (id, balance) VALUES (1, 100)");

            ctx.getBean(OuterService.class).run();

            int amount = jdbc.queryForObject(
                    "SELECT balance FROM wallet WHERE id = 1",
                    Integer.class);
            System.out.println("AFTER_COMMIT=" + amount);
        }
    }

    private static void show(String label) {
        TransactionStatus status =
                TransactionAspectSupport.currentTransactionStatus();
        Integer level = TransactionSynchronizationManager
                .getCurrentTransactionIsolationLevel();

        String isolation;
        if (level == null) {
            isolation = "DEFAULT";
        } else if (level == Connection.TRANSACTION_READ_COMMITTED) {
            isolation = "READ_COMMITTED";
        } else if (level == Connection.TRANSACTION_SERIALIZABLE) {
            isolation = "SERIALIZABLE";
        } else {
            isolation = "OTHER(" + level + ")";
        }

        System.out.println(label
                + ": new=" + status.isNewTransaction()
                + ", readOnly="
                + TransactionSynchronizationManager
                        .isCurrentTransactionReadOnly()
                + ", isolation=" + isolation);
    }

    public static class InnerService {

        @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.SERIALIZABLE,
            timeout = 1,
            readOnly = true
        )
        public void join() {
            show("JOIN");
        }

        @Transactional(
            propagation = Propagation.REQUIRES_NEW,
            isolation = Isolation.SERIALIZABLE,
            timeout = 5,
            readOnly = true
        )
        public void newTransaction() {
            show("NEW");
        }
    }

    public static class OuterService {
        private final InnerService inner;
        private final JdbcTemplate jdbc;

        public OuterService(InnerService inner, JdbcTemplate jdbc) {
            this.inner = inner;
            this.jdbc = jdbc;
        }

        @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.READ_COMMITTED,
            timeout = 30,
            readOnly = false
        )
        public void run() {
            show("OUTER");
            jdbc.update(
                    "UPDATE wallet SET balance = balance - 10 WHERE id = 1");
            inner.join();
            inner.newTransaction();
            show("RESUME");
        }
    }
}
```

The `OuterService` and `InnerService` beans are **two container-managed objects**. Calls `inner.join()` and `inner.newTransaction()` pass through the inner bean's transaction proxy, so annotations are applied. Do not put the inner methods in the same class and call `this.method()`, because proxy mode will bypass that boundary.

`JdbcTransactionManager` in its default configuration has `validateExistingTransaction=false`, allowing inner `REQUIRED` to join T1 despite a different isolation request. The demo does not write to the DB in T2, so it does not depend on concurrency/locking issues between two connections.

### 12.3. Running and verifying output

In the `tx-attributes` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TxScopeDemo
```

Lines **printed by the program itself**, ignoring library logs:

```text
OUTER: new=true, readOnly=false, isolation=READ_COMMITTED
JOIN: new=false, readOnly=false, isolation=READ_COMMITTED
NEW: new=true, readOnly=true, isolation=SERIALIZABLE
RESUME: new=true, readOnly=false, isolation=READ_COMMITTED
AFTER_COMMIT=90
```

Interpretation:

- **OUTER:** T1 is new, so status reports `new=true`; read-only is `false`, and requested isolation is `READ_COMMITTED`.
- **JOIN:** inner `REQUIRED` joins T1 (`new=false`). Inner's requests for `SERIALIZABLE`, read-only, and 1-second timeout do not change T1's isolation/read-only/deadline. Metadata visible to inner remains `READ_COMMITTED` and `false`.
- **NEW:** inner `REQUIRES_NEW` suspends T1 and opens T2; metadata in T2 is read-only `true`, isolation `SERIALIZABLE`, status `new=true`.
- **RESUME:** after T2, T1 resumes with its original metadata. Outer's `TransactionStatus` is still the status that opened T1.
- **AFTER_COMMIT:** outer returns normally, and T1 commits updating the balance from 100 down to 90.

The example uses one H2 datasource and one transaction manager so the question "what is new, what joins" is clearly visible. It **does not prove** read-only blocks SQL writes in H2 and **is not a timeout test**.

### 12.4. Variant to test strict validation

Simply replace the manager bean with:

```java
@Bean
PlatformTransactionManager transactionManager(DataSource dataSource) {
    JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);
    manager.setValidateExistingTransaction(true);
    return manager;
}
```

Do not add a second manager. When re-run in a new JVM, inner `join()` requests `SERIALIZABLE` which differs from T1's `READ_COMMITTED`. The manager rejects participation with `IllegalTransactionStateException` before `join()`'s body executes. The unchecked error escapes through outer's transactional advice so T1 is rolled back; the `JOIN`, `NEW`, `RESUME`, and `AFTER_COMMIT=90` lines from the lenient variant no longer appear. This is a **mismatch rejection test**, not a way to convert T1 to `SERIALIZABLE`.

## 13. Programmatic configuration: the same rules apply

Using `PlatformTransactionManager` directly follows the same begin/join logic as `@Transactional`:

```java
DefaultTransactionDefinition def =
        new DefaultTransactionDefinition();
def.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);
def.setIsolationLevel(
        TransactionDefinition.ISOLATION_REPEATABLE_READ);
def.setTimeout(12);
def.setReadOnly(true);
def.setName("reports.run");

TransactionStatus status = manager.getTransaction(def);
try {
    runReportQueries();
    manager.commit(status);
} catch (RuntimeException ex) {
    if (!status.isCompleted()) {
        manager.rollback(status);
    }
    throw ex;
}
```

This is a fragment; `manager` and `runReportQueries()` must be defined, along with imports. If no transaction exists, the manager starts a new transaction per the definition. If T1 already exists and `REQUIRED` joins, T1's physical attributes still govern per manager semantics. Do not manually call `commit()` on a status owned by AOP or `TransactionTemplate`.

A less lifecycle-error-prone option:

```java
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
template.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);
template.setTimeout(5);
template.setReadOnly(true);

String result = template.execute(status -> {
    return "read complete";
});
```

This is a fragment; `manager` must exist. The template manages commit/rollback and cleanup for the callback. As far as `TransactionDefinition` goes, the rules for isolation/timeout/readOnly do not differ just because the API is used instead of annotations.

## 14. Table of easily confused scenarios

Assume a JDBC manager supporting the corresponding attributes and using lenient mode.

| Scenario | Physical transaction | Attribute effect |
| --- | --- | --- |
| No existing transaction, `REQUIRED(SERIALIZABLE, timeout=10, readOnly=true)` | Opens T1 | Manager attempts to apply requests to T1 |
| Existing T1 `READ_COMMITTED`, inner `REQUIRED(SERIALIZABLE, timeout=10, readOnly=true)` | Joins T1 | Keeps T1's isolation/timeout/read-only |
| Existing T1, inner `REQUIRES_NEW(SERIALIZABLE, timeout=10, readOnly=true)` | Suspends T1, opens T2 | Applies requests to T2 if supported by resource |
| Existing T1, inner `NESTED` | Savepoint in T1 if supported | No independent physical isolation/timeout like T2 |
| No existing transaction, `SUPPORTS(readOnly=true)` | Not required to open a transaction | May have resource-level read-only hint; not a new DB transaction |
| Existing T1, inner `NOT_SUPPORTED` | Suspends T1 | SQL outside T1 is not automatically rolled back with T1 |
| No existing transaction, inner `MANDATORY` | Does not open | Throws error due to missing transaction |
| Existing T1, inner `NEVER` | Does not open | Throws error due to invalid existing condition |
| Inner `REQUIRED(rollbackFor=IOException.class)` joins T1, IOException escapes advice | Still T1 | Rule can mark T1 rollback-only even without a new transaction |

If strict validation is enabled, join scenarios with incompatible isolation or read-only can switch from "lenient join" to **throwing an error**, not "creating a replacement new transaction".

## 15. Common mistakes and how to fix them

**Mistake 1 – Thinking `REQUIRED` always opens a new transaction.**  
`REQUIRED` means "a transaction is required": if one exists, join it; if not, open a new one. Use the right physical boundary to choose isolation/timeout.

**Mistake 2 – Putting high isolation on a repository method and believing it upgrades the service's transaction.**  
When the repository joins the service's transaction, outer isolation continues to govern. Raise isolation on the outer service or separate business work when an independent transaction is genuinely needed.

**Mistake 3 – Inner `timeout=1`, yet the query still runs under outer's deadline.**  
There is no separate timeout when joining. Set the timeout on the scope that starts the transaction and check query timeouts/backend support.

**Mistake 4 – Expecting inner `readOnly=false` to turn off outer's read-only.**  
There is no mechanism to reset read-only like that on the same physical transaction. With strict validation, certain mismatches are even rejected.

**Mistake 5 – Treating `readOnly=true` as an absolute DB read-only permission.**  
It is often just a hint. Verify DB permissions and actual behavior if blocking writes is required.

**Mistake 6 – Forgetting that `rollbackFor` still takes effect in a participating scope.**  
An inner exception can mark T1 rollback-only; outer catching the exception and returning does not guarantee a successful commit.

**Mistake 7 – Confusing `REQUIRES_NEW` with `NESTED`.**  
`REQUIRES_NEW` has its own physical transaction; `NESTED` is typically a savepoint within the same T1. Pooling, independent commit, and isolation differ.

**Mistake 8 – Self-invocation preventing inner annotations from running.**  
In proxy mode, `this.save()` does not pass through the proxy. Place transaction boundaries on public methods called from outside or extract a separate bean.

**Mistake 9 – DAO using a different datasource.**  
The manager may open T1 properly, yet SQL running on a connection not participating in T1 will not roll back with T1.

**Mistake 10 – Using logs/`isCompleted()` as proof that a transaction committed.**  
`isCompleted()` only reports the scope finished, which could be after a rollback. Verify database post-conditions after the boundary, and observe actual exceptions/results.

**Mistake 11 – Believing every DB implements isolation identically.**  
Some DBs do not exhibit dirty reads the same way or use MVCC snapshot semantics. Run concurrency tests against the actual DB/driver.

**Mistake 12 – Disabling validation to ignore flawed boundary design.**  
Lenient mode allows joining with outer's characteristics; it does not "fix" inner's isolation requirement. If business requirements truly demand different isolation, design an appropriate transaction boundary.

## 16. Design and testing strategy

A good design usually places the transaction boundary on the **application service** where full business context exists:

```text
Controller/Handler
      |
      v
ApplicationService.execute()
  @Transactional(REQUIRED,
                 isolation=READ_COMMITTED,
                 timeout=30)
      |
      +-- DomainService.validate()     join T1
      +-- Repository.update()          join T1
      +-- Repository.insertOutbox()    join T1
      |
      v
commit T1
```

When an inner service is simply part of the same use case, do not ask it to choose isolation/timeout conflicting with outer and expect physical effect. Only when an independent piece of work has a solid reason to commit separately should you consider `REQUIRES_NEW` and handle consistency after partial success.

Tests should cover:

1. **New REQUIRED:** start from a caller with no transaction, inspect status, metadata, and DB state after commit.
2. **Participating REQUIRED:** outer `READ_COMMITTED`, inner `SERIALIZABLE`; confirm inner uses outer in lenient mode.
3. **REQUIRES_NEW:** confirm inner opens T2 and outer is resumed with its original metadata.
4. **Strict validation:** enable `setValidateExistingTransaction(true)` and verify mismatched isolation is rejected.
5. **Rollback rule:** inner exception matches rollback rule, outer catches the error; verify T1 becomes rollback-only and commit can fail.
6. **Real timeout:** test on a backend/driver with a query that times out, do not rely solely on `Thread.sleep`.
7. **Actual read-only:** test hints and enforcement behavior on the real database.
8. **Isolation/concurrency:** use two concurrent transactions to verify dirty/nonrepeatable reads or serialization conflicts as required.
9. **Proxy boundary:** confirm methods are called through the Spring proxy, not via `this.method()`.
10. **Resource consistency:** manager and DAO use the right datasource; check external side effects if any.

In Spring Test, a test method annotated with `@Transactional` may be automatically rolled back by the framework when it finishes. Therefore, do not let test-level rollback hide missing transaction advice on a service; verify database state outside the test's boundary when appropriate.

## 17. Knowledge self-check

**1.** Outer `READ_COMMITTED`, inner `REQUIRED(SERIALIZABLE)`. When the manager is lenient, what is the actual isolation?  
**Answer:** T1 continues with `READ_COMMITTED`; inner does not change the isolation of the existing transaction.

**2.** Change inner to `REQUIRES_NEW(SERIALIZABLE)`, what differs?  
**Answer:** Outer T1 is suspended, the manager opens a new T2, and has the opportunity to apply `SERIALIZABLE` to T2.

**3.** Does inner `REQUIRED(timeout=2)` extend or reset T1's deadline?  
**Answer:** No. The deadline belongs to the already opened physical transaction T1; inner does not create a separate physical transaction timeout.

**4.** Does `readOnly=true` guarantee every database rejects `UPDATE`?  
**Answer:** No. It may be an optimization hint; enforcement depends on the provider/DB.

**5.** Does enabling strict validation automatically "upgrade" T1's isolation to match inner?  
**Answer:** No. It can reject joining when isolation mismatches.

**6.** Is `rollbackFor=IOException.class` on inner `REQUIRED` still meaningful?  
**Answer:** Yes. If an exception matching the rule escapes the advice, the shared transaction can be marked rollback-only.

**7.** Can you use `@Transactional(name="my-tx")`?  
**Answer:** No. Declarative transaction names are normally auto-generated from class/method; programmatic definitions have `setName()`.

**8.** Does `isNewTransaction()==false` prove there is no DB transaction?  
**Answer:** No. Inner `REQUIRED` joining T1 normally returns `false`, even though it runs inside a transaction.

**9.** Does `SUPPORTS(readOnly=true)` when no transaction exists always open T1?  
**Answer:** No. Metadata/hints may exist, but a physical transaction is not required.

**10.** Does `NESTED` inside T1 have its own transaction isolation like `REQUIRES_NEW`?  
**Answer:** No. A nested scope typically uses a savepoint on the same physical transaction, if supported by the backend.

## 18. Memory checklist

- Ask first: **has this scope passed through transaction advice, and which manager was selected?**
- Next: **does propagation make it open new, join, suspend, savepoint, or run without a transaction?**
- For a **new** transaction, the manager can apply isolation, timeout, read-only, transaction name, and related metadata depending on the resource.
- For a **joining** scope, outer's physical transaction typically determines isolation, timeout, and read-only; inner attributes do not automatically alter those values.
- With `REQUIRES_NEW`, the manager configures a separate physical transaction; remember connection costs and commit independence.
- With `NESTED`, a savepoint is not equivalent to a new physical transaction.
- Rollback rules are still evaluated when an exception escapes a joining **logical scope**.
- If you need to detect mismatches instead of silently accepting them, use `setValidateExistingTransaction(true)` when supported by the manager.
- Always verify against the right database, right datasource, right proxy boundary, and post-transaction outcome.

**A standard takeaway:** `propagation` decides creation; **isolation, timeout, and read-only at the physical transaction level are primarily established when a transaction actually begins**, while **rollback rules and transaction manager selection remain meaningful even for joining scopes**.

## Official Spring documentation

- [Using @Transactional — settings and transaction names](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Transaction Propagation — REQUIRED, REQUIRES_NEW, NESTED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring 6.2 @Transactional Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [TransactionDefinition API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionDefinition.html)
- [AbstractPlatformTransactionManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html)
- [Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
- [Spring JDBC Connection Management](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)