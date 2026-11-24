# Integrating Queries with the Right Transaction Manager in Spring Boot: JDBC and jOOQ

When building integration flows in Spring Boot, a service often combines **JDBC** for straightforward operations with **jOOQ** for compile-time type-checked SQL. For example, a consumer receives a `PaymentCaptured` event, inserts an `eventId` into a deduplication table via `JdbcTemplate`, updates a limit with jOOQ, and inserts a ledger entry via SQL. If the final step fails, all three changes must **roll back within the same transaction**. Simply adding `@Transactional` is not enough if queries run over different connections or are coordinated by the wrong transaction manager.

This lesson belongs to the **JDBC and jOOQ** chapter of the **SPRING_BOOT_INTEGRATION** module. The module explores integrating Spring Boot with HTTP clients, databases, caches, message brokers, and Spring Integration adapters—focusing on configuration, data contracts, transactions, errors, duplicate prevention, testing, and system observability. Here we focus on **choosing the `PlatformTransactionManager` matching your resources**, how `JdbcTemplate` and `DSLContext` participate in the same transaction, and where boundaries lie when a flow crosses into another database, thread, or broker.

> Examples illustrate Spring Boot 3.x, Spring Framework 6.x, JDBC, jOOQ, and PostgreSQL. `ON CONFLICT` SQL syntax is PostgreSQL-specific. When using another Boot version, multiple datasources, or a custom transaction manager, verify the actual beans in `ApplicationContext` and test rollbacks against a real database. jOOQ classes such as `WALLET` are assumed generated from the schema via jOOQ code generation.

## 1. Why Can Individually Succeeding Queries Still Corrupt Data?

Consider recording a debit after receiving a payment event:

~~~mermaid
sequenceDiagram
    participant L as @RabbitListener
    participant S as LedgerService
    participant J as JdbcTemplate
    participant Q as jOOQ DSLContext
    participant DB as PostgreSQL

    L->>S: apply(PaymentCaptured)
    Note over S,DB: One Spring transaction
    S->>J: INSERT processed_events(eventId)
    J->>DB: INSERT
    S->>Q: UPDATE wallet SET balance...
    Q->>DB: UPDATE
    S->>J: INSERT wallet_ledger
    J->>DB: INSERT
    alt All steps succeed
        S->>DB: COMMIT
        S-->>L: Success, listener can ACK
    else Any step throws rollback-triggering error
        S->>DB: ROLLBACK
        S--xL: Exception for listener to handle
    end
~~~

If `JdbcTemplate` uses connection A inside the transaction while `DSLContext` opens connection B in auto-commit mode, the jOOQ update can **commit immediately** while the JDBC statements roll back. When the consumer retries, the account balance can be debited twice.

For a transaction to truly cover both JDBC and jOOQ queries, all of these conditions must hold simultaneously:

1. Both operations target the intended **database resource**, usually the same `DataSource` pointing to the destination database.
2. The chosen transaction manager manages **that exact `DataSource`**.
3. Both `JdbcTemplate` and `DSLContext` acquire connections through **Spring transaction-aware mechanisms**.
4. Every atomic operation executes within the **active transaction boundary**, without hopping unintentionally onto another thread or connection.
5. Exception/rollback rules match every failure case that must abort the transaction.

**`@Transactional` on a method is only a declarative marker.** Actual behavior depends on the manager, connection provider, proxy invocation, and verified commit/rollback tests.

## 2. Distinguishing Transaction Manager, `DataSource`, and `Connection`

These three components are related but not interchangeable:

| Component | Role | Examples |
| --- | --- | --- |
| `DataSource` | Supplies database connections, typically backed by a pool | `HikariDataSource` |
| `PlatformTransactionManager` | Begins, commits, rolls back, suspends, or creates savepoints per transaction definition | `JdbcTransactionManager`, `JpaTransactionManager`, `JtaTransactionManager` |
| `Connection` | Physical/logical JDBC session executing SQL with auto-commit, isolation, and state | `java.sql.Connection` |

In a declarative Spring JDBC transaction, the transaction manager borrows a connection from `DataSource`, configures auto-commit/isolation/read-only state, and **binds a `ConnectionHolder` to the current thread** via `TransactionSynchronizationManager`. Spring JDBC queries call `DataSourceUtils` to obtain that bound connection, letting all statements share uncommitted state and roll back together.

~~~mermaid
flowchart TD
    TX["@Transactional via Spring proxy"] --> TM["JdbcTransactionManager"]
    TM --> DS[("DataSource / Hikari pool")]
    TM --> HOLDER["ConnectionHolder on thread"]
    JDBC["JdbcTemplate / NamedParameterJdbcTemplate"] --> DSU["DataSourceUtils"]
    JOOQ["jOOQ DSLContext"] --> TAP["TransactionAwareDataSourceProxy or Spring-integrated provider"]
    DSU --> HOLDER
    TAP --> HOLDER
    HOLDER --> DB[("Same JDBC Connection")]
    DB --> SQL["INSERT / UPDATE / SELECT in one transaction"]
~~~

This diagram shows the **imperative** JDBC model. `ThreadLocal` transaction context does not propagate automatically into `@Async`, `CompletableFuture`, `parallelStream`, or another Reactor scheduler thread. With R2DBC/reactive transactions, resource and context propagation work differently; never read this diagram as implying `R2dbcTransactionManager` manages JDBC.

### Common Transaction Managers

| Transaction Manager | Primary Resource | When to Use? | Notes |
| --- | --- | --- | --- |
| `JdbcTransactionManager` | JDBC `DataSource` | `JdbcTemplate`, `NamedParameterJdbcTemplate`, JDBC-backed jOOQ on the same source | Appropriate default for local JDBC transactions; supports SQL exception translation on commit/rollback |
| `DataSourceTransactionManager` | JDBC `DataSource` | Same JDBC model; foundation for `JdbcTransactionManager` | Does not coordinate multiple databases automatically |
| `JpaTransactionManager` | JPA `EntityManagerFactory`; can also bridge JDBC on the same `DataSource` when configured properly | Flows mixing JPA and JDBC in one DB | Cannot assume support for every jOOQ/JDBC query if separate connections/providers are used |
| `JtaTransactionManager` | Transaction coordinator / XA | Coordinating multiple XA-capable resources with supporting infrastructure | Adds significant cost and complexity; object storage, HTTP clients, and many brokers are not XA resources |
| `R2dbcTransactionManager` | R2DBC `ConnectionFactory` | Reactive database queries over R2DBC | Does not manage JDBC `DataSource` or `JdbcTemplate` |
| jOOQ's own transaction provider | jOOQ `Configuration`/`ConnectionProvider` | When calling `DSLContext.transaction(...)` | Must integrate with the Spring manager if sharing boundaries |

For **a single JDBC database** without an ORM requiring another manager, `JdbcTransactionManager` is usually the direct choice. Never choose a manager just because "transaction" appears in its bean name; match it against the **actual `DataSource` being queried**.

## 3. Spring Boot Auto-Configuration: A Safe Starting Point

### Dependencies

A Maven project using PostgreSQL and Spring Boot typically declares:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jooq</artifactId>
    </dependency>

    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

Spring Boot dependency management normally manages compatible Spring JDBC, jOOQ, and driver versions for your Boot release. **jOOQ code generation** is a separate build step: configure a plugin and schema source if using generated table classes; adding the starter alone does not generate `WALLET` from the database in every project.

`application.yml` for a single `DataSource`:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/payments
    username: ${DB_USER}
    password: ${DB_PASSWORD}
    hikari:
      maximum-pool-size: 12
  jooq:
    sql-dialect: POSTGRES
~~~

Never commit real passwords. A 12-connection pool is only an example that must be tuned to instance count, concurrency, transaction hold times, and PostgreSQL connection limits.

With one `DataSource` and standard Boot JDBC settings, Boot can provision `JdbcTemplate`, `NamedParameterJdbcTemplate`, a JDBC transaction manager, and jOOQ's `DSLContext`. Depending on versions and starters on the classpath, **the resulting transaction manager can differ**: if the application registers a custom manager, adds JPA/JTA, or defines multiple `DataSource`s, auto-configuration conditions shift. Inspect the real runtime beans rather than assuming Boot always picks the exact same manager.

In Boot-supported jOOQ configurations, `DSLContext` can use a `TransactionAwareDataSourceProxy`/`ConnectionProvider` and a Spring-integrated transaction provider, letting jOOQ queries join active JDBC transactions. If you manually instantiate `DSLContext` outside Boot, that wiring responsibility moves to your application.

### Inspecting Which Manager Is Actually Injected

During diagnostics, you can list transaction manager beans once on startup:

~~~java
import java.util.Map;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class TransactionDiagnostics {

    @Bean
    ApplicationRunner logTransactionManagers(
            Map<String, PlatformTransactionManager> managers) {
        return args -> managers.forEach(
                (name, manager) ->
                        System.out.println(
                                name + ": " + manager.getClass().getName()));
    }
}
~~~

This snippet is a **temporary diagnostic**; in production use a logger and never print connection URLs or credentials. With multiple managers, verify manager-to-`DataSource` mappings via bean configs, metrics, or tests so services never accidentally bind to the wrong manager.

Spring `@Transactional` picks the default/`@Primary` manager or configured qualifier. With multiple managers, specify `transactionManager = "..."` explicitly on critical boundaries.

## 4. Designing a Transaction Combining `JdbcTemplate` and jOOQ

Consider a consumer handling `DebitAuthorized` with three atomic steps:

- Record `eventId` to block broker redeliveries.
- Deduct wallet balance if sufficient.
- Insert a ledger entry.

Illustrative PostgreSQL schema:

~~~sql
CREATE TABLE wallet (
    account_id     BIGINT PRIMARY KEY,
    balance_cents  BIGINT NOT NULL CHECK (balance_cents >= 0)
);

CREATE TABLE processed_events (
    consumer_name  VARCHAR(100) NOT NULL,
    event_id       VARCHAR(120) NOT NULL,
    processed_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE wallet_ledger (
    ledger_id      BIGSERIAL PRIMARY KEY,
    event_id       VARCHAR(120) NOT NULL UNIQUE,
    account_id     BIGINT NOT NULL REFERENCES wallet(account_id),
    amount_cents   BIGINT NOT NULL CHECK (amount_cents > 0),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
~~~

Assume jOOQ code generation produced `com.example.jooq.tables.Wallet.WALLET`. DTO:

~~~java
public record DebitAuthorized(
        String eventId,
        long accountId,
        long amountCents
) {
}
~~~

Spring service managing the transaction:

~~~java
import static com.example.jooq.tables.Wallet.WALLET;

import org.jooq.DSLContext;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class WalletDebitService {

    private static final String CONSUMER = "wallet-debit-v1";

    private final JdbcTemplate jdbc;
    private final DSLContext dsl;

    public WalletDebitService(JdbcTemplate jdbc, DSLContext dsl) {
        this.jdbc = jdbc;
        this.dsl = dsl;
    }

    @Transactional
    public void apply(DebitAuthorized event) {
        if (event.eventId() == null || event.eventId().isBlank()
                || event.accountId() <= 0 || event.amountCents() <= 0) {
            throw new IllegalArgumentException("Invalid event");
        }

        // PostgreSQL: first INSERT wins; duplicate delivery returns 0 rows.
        int inserted = jdbc.update("""
            INSERT INTO processed_events (consumer_name, event_id)
            VALUES (?, ?)
            ON CONFLICT (consumer_name, event_id) DO NOTHING
            """, CONSUMER, event.eventId());

        if (inserted == 0) {
            return; // Already processed this eventId in this consumer.
        }

        // jOOQ and JdbcTemplate must share the same transaction-aware DataSource.
        int updated = dsl.update(WALLET)
                .set(WALLET.BALANCE_CENTS,
                        WALLET.BALANCE_CENTS.minus(event.amountCents()))
                .where(WALLET.ACCOUNT_ID.eq(event.accountId()))
                .and(WALLET.BALANCE_CENTS.ge(event.amountCents()))
                .execute();

        if (updated != 1) {
            throw new InsufficientBalanceException(
                    "Account not found or insufficient balance");
        }

        jdbc.update("""
            INSERT INTO wallet_ledger (event_id, account_id, amount_cents)
            VALUES (?, ?, ?)
            """, event.eventId(), event.accountId(), event.amountCents());
    }
}
~~~

`InsufficientBalanceException` is an **application-defined business `RuntimeException`**. Under Spring's default rollback rules, if `updated != 1` or the ledger insert throws an unchecked exception, both the inbox insert and wallet update roll back. If a handler throws a *checked exception*, rollback rules must be configured explicitly (see section 7).

The conditional update `balance_cents >= amount` performs an **atomic check-and-update** in SQL, avoiding the race of reading balance and subtracting in Java without locking. The unique key on `processed_events` resolves races when two consumers receive the same `eventId`: the database arbitrates the key constraint rather than relying on a prior `SELECT`.

Important boundaries:

- When `JdbcTemplate` and `DSLContext` both pull connections from the active transaction, a successful method commits all three changes together.
- Never wire `jdbc.update(...)` to one `DataSource` and `dsl` to another database while expecting a shared transaction.
- `@Transactional` must be invoked through the **Spring proxy**, e.g., a controller or listener injecting the `WalletDebitService` bean and calling `apply`.
- On insufficient balance, the exception delegates error handling to the listener/broker policy; classify this as a business failure to avoid infinite requeue loops.
- The inbox deduplicates only business side effects inside the same database transaction. Subsequent HTTP calls or broker publishes still need matching idempotency or an outbox.

### RabbitMQ Listener Calling the Transactional Service Properly

~~~java
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class WalletEventConsumer {

    private final WalletDebitService walletDebitService;

    public WalletEventConsumer(WalletDebitService walletDebitService) {
        this.walletDebitService = walletDebitService;
    }

    @RabbitListener(queues = "wallet.debit.events")
    public void onMessage(DebitAuthorized event) {
        walletDebitService.apply(event);
    }
}
~~~

This listener assumes message conversion and payload type `DebitAuthorized` are configured. Under Spring AMQP's standard `AUTO` ack mode, returning normally after transaction commit allows the container to ack the delivery. If SQL commits and the broker connection drops before the ack, the message redelivers and the inbox prevents double debiting. Configure retry/reject/DLQ rules per error type so **permanent data or business errors never spin endlessly**.

## 5. How Can jOOQ Accidentally Step Outside Spring Transactions?

`JdbcTemplate` uses `DataSourceUtils` to look up connections bound to Spring transactions. jOOQ, however, knows nothing about Spring's `PlatformTransactionManager` if created directly from a raw `DataSource`, a JDBC URL, or a manually opened `Connection`:

~~~java
// Arbitrary setup like this must have its transaction boundary verified.
DSLContext dsl = DSL.using(dataSource, SQLDialect.POSTGRES);
~~~

A pooled `DataSource` normally hands out a fresh connection when jOOQ calls `getConnection()`, rather than the connection currently held by Spring's transaction manager for `JdbcTemplate`. Thus the jOOQ statement can auto-commit outside the intended transaction.

### `TransactionAwareDataSourceProxy`

Spring provides `TransactionAwareDataSourceProxy` for libraries that call `DataSource.getConnection()` directly without calling `DataSourceUtils`. This proxy returns the Spring transaction-bound connection, **provided the transaction manager manages the same underlying `DataSource`**.

Illustrative configuration when **manually creating `DSLContext`**:

~~~java
import javax.sql.DataSource;
import org.jooq.DSLContext;
import org.jooq.SQLDialect;
import org.jooq.impl.DSL;
import org.jooq.impl.DataSourceConnectionProvider;
import org.jooq.impl.DefaultConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.datasource.TransactionAwareDataSourceProxy;

@Configuration(proxyBeanMethods = false)
public class JooqDataSourceConfiguration {

    @Bean
    DSLContext customDslContext(DataSource dataSource) {
        var config = new DefaultConfiguration();

        config.set(SQLDialect.POSTGRES);
        config.set(new DataSourceConnectionProvider(
                new TransactionAwareDataSourceProxy(dataSource)));

        return DSL.using(config);
    }
}
~~~

This applies to **a single `DataSource`** coordinated by Spring `@Transactional`. If Boot already auto-configures `DSLContext` properly for your single datasource, prefer **injecting Boot's bean** rather than defining a competing one. When customization is required, evaluate Boot customizers before replacing the entire bean.

**Distinguish two jOOQ SPIs:**

1. `ConnectionProvider` governs how jOOQ borrows and returns JDBC connections; it must participate in Spring-managed connections.
2. `TransactionProvider` governs `dsl.transaction(...)` and `dsl.transactionResult(...)`. For jOOQ-started transactions to **also** use the Spring manager and propagation rules, wire/preserve the Spring-integrated transaction provider.

`TransactionAwareDataSourceProxy` above lets queries **join an active `@Transactional`**. It **does not by itself guarantee** `dsl.transaction(...)` routes through `PlatformTransactionManager` in every setup. In Spring-centric services, placing boundaries via `@Transactional` on services is easiest to follow; if using jOOQ's transaction API, verify the provider wired by Boot/starter and test rollbacks and nesting on your exact jOOQ version.

### Avoid Opening Connections Manually Inside Services

This breaks transaction awareness:

~~~java
@Transactional
public void broken() throws Exception {
    try (var connection = DriverManager.getConnection(url, user, password)) {
        connection.createStatement()
                .executeUpdate("UPDATE wallet SET balance_cents = 0");
    }
}
~~~

`DriverManager` opens a connection independent of the transaction manager's `DataSource`. When the outer transaction rolls back, the manual connection's `UPDATE` may already be committed. `try-with-resources` closes the resource without enlisting it in Spring's transaction.

If raw JDBC APIs are unavoidable, borrow via `DataSourceUtils.getConnection(dataSource)` and release via `DataSourceUtils.releaseConnection(...)`, or execute inside a `JdbcTemplate` callback. Never call `commit()`, `rollback()`, toggle `autoCommit`, or manually close a Spring-managed connection inside business logic.

## 6. Choosing Transaction Managers in Multi-DataSource Applications

An application might connect to an operational `paymentsDb` and a `reportingDb`. No single local `JdbcTransactionManager` atomically spans both pools.

~~~mermaid
flowchart TD
    SERVICE["ReportingService"] --> PDB["payments DataSource"]
    SERVICE --> RDB["reporting DataSource"]
    PDB --> PTX["paymentsTransactionManager"]
    RDB --> RTX["reportingTransactionManager"]
    PTX --> PCONN["PostgreSQL payments connection"]
    RTX --> RCONN["PostgreSQL reporting connection"]
    WARN["No automatic atomic commit across two DBs"] -.-> PCONN
    WARN -.-> RCONN
~~~

Each `DataSource` needs its own query beans and transaction manager. Example assuming the project defines and names `reportingDataSource`:

~~~java
import javax.sql.DataSource;
import org.jooq.DSLContext;
import org.jooq.SQLDialect;
import org.jooq.impl.DSL;
import org.jooq.impl.DataSourceConnectionProvider;
import org.jooq.impl.DefaultConfiguration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.JdbcTransactionManager;
import org.springframework.jdbc.datasource.TransactionAwareDataSourceProxy;

@Configuration(proxyBeanMethods = false)
public class ReportingJdbcConfiguration {

    @Bean("reportingTransactionManager")
    JdbcTransactionManager reportingTransactionManager(
            @Qualifier("reportingDataSource") DataSource reportingDataSource) {
        return new JdbcTransactionManager(reportingDataSource);
    }

    @Bean("reportingJdbcTemplate")
    JdbcTemplate reportingJdbcTemplate(
            @Qualifier("reportingDataSource") DataSource reportingDataSource) {
        return new JdbcTemplate(reportingDataSource);
    }

    @Bean("reportingDsl")
    DSLContext reportingDsl(
            @Qualifier("reportingDataSource") DataSource reportingDataSource) {

        var config = new DefaultConfiguration();
        config.set(SQLDialect.POSTGRES);
        config.set(new DataSourceConnectionProvider(
                new TransactionAwareDataSourceProxy(reportingDataSource)));
        return DSL.using(config);
    }
}
~~~

Service using explicit qualifiers:

~~~java
import org.jooq.DSLContext;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ReportingImportService {

    private final JdbcTemplate reportingJdbc;
    private final DSLContext reportingDsl;

    public ReportingImportService(
            @Qualifier("reportingJdbcTemplate") JdbcTemplate reportingJdbc,
            @Qualifier("reportingDsl") DSLContext reportingDsl) {
        this.reportingJdbc = reportingJdbc;
        this.reportingDsl = reportingDsl;
    }

    @Transactional(transactionManager = "reportingTransactionManager")
    public void updateReport(long reportId) {
        reportingJdbc.update(
                "UPDATE reporting_job SET state = ? WHERE id = ?",
                "PROCESSING", reportId);

        reportingDsl.execute(
                "UPDATE reporting_audit SET last_run_at = CURRENT_TIMESTAMP " +
                "WHERE job_id = ?", reportId);
    }
}
~~~

This explicitly ties queries to `reportingDataSource` and transactions to `reportingTransactionManager`. It does not make commits across `reportingDb` and `paymentsDb` atomic—they remain independent resources.

When an application mixes an auto-configured primary `DataSource`/`DSLContext` with a secondary `reporting` `DataSource`/`DSLContext`, keep bean names, `@Qualifier`, `@Primary`, and auto-configuration conditions crystal clear. Never inject an unqualified `DSLContext` when multiple beans of that type exist.

### What About Writing to Two Databases in One Business Flow?

Suppose an order writes to `paymentsDb` and an audit entry writes to `reportingDb`:

- Using only `paymentsTransactionManager` will not roll back `reportingDb`.
- Opening two sequential local transactions leaves a window where one commits and the other fails.
- `@Transactional` with one manager does not create XA/2PC.
- `ChainedTransactionManager` / sequential commits do not deliver true atomicity if the first commit succeeds and the second fails.
- For cross-system consistency, prefer **outbox + idempotent consumers + eventual consistency**, or an infrastructure-supported distributed transaction architecture where its costs are justified.

In systems integrating HTTP, brokers, caches, and object stores, **never assume everything joins one ACID transaction**. Local JDBC transactions govern only the managed database resource.

## 7. `@Transactional` Boundaries, Exceptions, and Self-Invocation

### Proxy Invocation Is Required

In standard Spring proxy mode, `@Transactional` applies only when invoked **through the Spring proxy**. Common mistake:

~~~java
@Service
public class OrderService {

    public void entryPoint(long orderId) {
        // Calling method on same class: self-invocation, bypasses proxy.
        this.updateInTransaction(orderId);
    }

    @Transactional
    public void updateInTransaction(long orderId) {
        // May run without a transaction if invoked only via this.
    }
}
~~~

Fix this by extracting the transactional method to another Spring service and injecting it, or redesigning orchestration—never rely on `this.` calls to activate annotations. Similarly, instantiating with `new SomeService()`, marking methods `private`/`final`, or special proxy modes can bypass interception. Place `@Transactional` on **public service methods** and test boundaries through the real bean.

### Checked Exceptions Do Not Roll Back by Default

By default in Spring `@Transactional`, **`RuntimeException` and `Error`** trigger rollback, whereas checked exceptions do not unless configured:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importDocument(InputStream input) throws IOException {
    // JDBC/jOOQ writes...
    // IOException must be declared in rollbackFor to roll back SQL.
}
~~~

Avoid reflexively setting `rollbackFor = Exception.class` if some checked exceptions represent valid business outcomes that should commit. Define explicitly which exceptions indicate transaction failure. If a method catches an exception, logs it, and returns normally, Spring **commits** even though the operation failed. To roll back after internal handling, rethrow an appropriate exception; in rare cases you can mark rollback-only via `TransactionAspectSupport` with strong justification and tests.

### Rollback-Only and `UnexpectedRollbackException`

Suppose an outer method opens a transaction, an inner `PROPAGATION_REQUIRED` method shares it and throws a `RuntimeException`, and the outer method catches it and tries to commit. Because the shared transaction was marked `rollback-only`, Spring rolls back and throws `UnexpectedRollbackException`. Never handle this by blindly retrying or ignoring it—identify which inner layer marked the transaction rollback-only.

### `@Transactional(readOnly = true)` Is a Hint/Policy, Not a Security Permission

~~~java
@Transactional(readOnly = true)
public WalletSnapshot getSnapshot(long accountId) {
    return dsl.selectFrom(WALLET)
            .where(WALLET.ACCOUNT_ID.eq(accountId))
            .fetchOneInto(WalletSnapshot.class);
}
~~~

`readOnly = true` lets frameworks, drivers, or ORMs optimize or request read-only mode where supported, yet **it is not a security access control** and does not block writes across every database or driver. Enforce least-privilege DB permissions and test in real environments.

## 8. How Do Propagation, Isolation, and Savepoints Affect Queries?

| Propagation | Core Behavior | Risk If Misused |
| --- | --- | --- |
| `REQUIRED` (default) | Joins active transaction or starts a new one | Inner `rollback-only` prevents outer commit |
| `REQUIRES_NEW` | Suspends current transaction and opens a new physical transaction | Needs an extra connection, commits independently, can deadlock/exhaust pool when nested |
| `NESTED` | Creates a savepoint inside the outer transaction when supported | Not an independent physical transaction; depends on DB/JDBC support |
| `MANDATORY` | Requires an existing active transaction | Fails if caller forgot to open a boundary |
| `SUPPORTS` | Joins if present; runs non-transactionally otherwise | Writes may auto-commit when caller lacks a transaction |
| `NOT_SUPPORTED` | Suspends active transaction and runs outside it | Queries lose atomicity with outer work |
| `NEVER` | Fails if a transaction is active | Suits APIs explicitly forbidding transactions |

`REQUIRES_NEW` is helpful for independent audit logs, yet holding an outer connection while opening an inner transaction requires **two concurrent connections on the same thread**. If 10 requests hold 10 connections in a size-10 pool and each waits on `REQUIRES_NEW`, the pool deadlocks completely. Fix the architecture rather than merely raising pool limits endlessly.

`NESTED` in JDBC normally relies on savepoints. Verify your database, driver, and manager support savepoints; with jOOQ `dsl.transaction(...)`, do not assume nested blocks behave identically to Spring `NESTED` if the transaction provider differs.

### Isolation and Race Conditions

`@Transactional(isolation = Isolation.READ_COMMITTED)` configures isolation only when **starting a new transaction**; joining an existing transaction inherits its isolation. `READ_COMMITTED`, `REPEATABLE_READ`, and `SERIALIZABLE` differ subtly across databases. Never expect identical semantics across vendors or assume higher isolation alone prevents all business races.

For the wallet debit example:

~~~sql
UPDATE wallet
SET balance_cents = balance_cents - :amount
WHERE account_id = :accountId
  AND balance_cents >= :amount;
~~~

combined with an affected-row check is far safer than `SELECT balance` followed by an unlocked `UPDATE`. When reading multiple rows before updating based on aggregates, consider `SELECT ... FOR UPDATE`, optimistic version columns, constraints, or higher isolation—designed around your concurrency model and tested with two parallel transactions.

## 9. Multiple Meanings of Timeout: Query, Transaction, Pool, and Downstream

Overly long transactions slow APIs and hold connections and locks, raising deadlock and bottleneck risk. Distinguish four distinct timeouts:

| Type | Configuration Example | What It Bounds |
| --- | --- | --- |
| Connection acquisition timeout | Hikari `connectionTimeout` | Wait time to borrow an idle connection from the pool |
| JDBC statement/query timeout | `JdbcTemplate.setQueryTimeout(...)`, statement timeout, DB `statement_timeout` | SQL execution / result wait time per driver/DB |
| Spring transaction timeout | `@Transactional(timeout = 5)` | Manager-enforced transaction deadline; SQL enforcement depends on JDBC infrastructure |
| HTTP / RPC / broker timeout | HTTP client timeout, RSocket/gRPC deadline, consumer timeout | External resources outside the JDBC transaction |

Example:

~~~java
@Transactional(timeout = 5)
public void reserve(long walletId, long amount) {
    // Queries join the transaction; avoid 30-second HTTP calls here.
}
~~~

`timeout = 5` is in **seconds**. Do not interpret it as guaranteeing thread interruption at exact second 5 or rollback of external side effects. Spring JDBC propagates remaining transaction time to statements via `DataSourceUtils`/`JdbcTemplate`; verify how jOOQ and your driver enforce query timeouts. Long-running statements are also subject to DB policies and socket read timeouts.

When a flow must call an external API before updating SQL, split phases: execute the HTTP call with a bounded deadline **outside a lock-holding transaction**, then open a short transaction to persist outcomes and state/versions, or use outbox/saga orchestration.

## 10. Retries, Deadlocks, and Idempotency

Retrying a **failed transaction** must re-execute the entire unit across all its SQL statements. Never blindly retry only the final statement after a deadlock or serialization failure: the database has typically already marked the transaction for rollback.

Example orchestrator retrying the entire service method:

~~~java
@Service
public class DebitOrchestrator {

    private final WalletDebitService walletDebitService;

    public DebitOrchestrator(WalletDebitService walletDebitService) {
        this.walletDebitService = walletDebitService;
    }

    public void applyWithRetry(DebitAuthorized event) {
        // RetryTemplate/Resilience4j or external exception policy.
        // Each attempt calls through Spring proxy to start a new transaction.
        walletDebitService.apply(event);
    }
}
~~~

This outlines retry placement; if `@Retryable` and `@Transactional` sit on **the same method**, advice ordering determines whether retries wrap **outside** or **inside** the transaction. Verify advice order and write integration tests proving each attempt starts a fresh transaction. Separating the retry orchestrator and transactional service into two beans as above makes behavior clear.

Error classification:

- **Transient**: certain deadlocks, lock timeouts, serialization failures, brief network blips. Retry conditionally with bounded attempts, backoff/jitter, and overall request budget.
- **Permanent**: schema errors, invalid SQL, contract FK violations, invalid payloads. Do not loop retries.
- **Unknown outcome**: DB commit may have succeeded when an ack/response dropped; rely on **idempotency keys** and status checks.

Spring `DataAccessException` differentiates transient vs. non-transient subclasses at the framework level; Boot can translate jOOQ errors into Spring exceptions in supported configurations. If creating `DSLContext` manually, verify the actual exceptions emitted and translator wiring rather than classifying retries by generic exception name alone.

Broker-driven designs must keep `eventId` immutable across every retry; never mint a fresh UUID per attempt. The unique-constrained `processed_events` table in the same transaction gives once-only SQL business effects even when the broker redelivers messages.

## 11. Differences Between Spring `@Transactional` and jOOQ's DSL Transaction API

jOOQ offers:

~~~java
dsl.transaction(configuration -> {
    DSLContext transactionalDsl = DSL.using(configuration);
    // Run jOOQ queries under the configured transaction provider.
});
~~~

Here `configuration` is the transactional jOOQ `Configuration` passed to the callback. Calling `dsl.transaction(...)` delegates begin/commit/rollback to **jOOQ's `TransactionProvider`**. With Boot-configured jOOQ, that provider normally integrates with Spring's `PlatformTransactionManager`. When building `DSLContext` manually, wire the matching provider if you intend to use jOOQ's transaction API.

Questions to verify before mixing both styles:

1. Does `dsl.transaction(...)` invoke Spring's provider or jOOQ's default provider?
2. When called inside `@Transactional`, does the inner block join, create a savepoint, or hit a separate manager?
3. Does JDBC code inside the callback receive the expected connection?
4. When an exception is caught, which transaction rolls back and which stays active?
5. Are there multiple datasources/managers, and which resource does the provider pick?

The simplest rule for services combining JDBC and jOOQ on one SQL database: **define one transaction boundary on the Spring service** and call injected `JdbcTemplate` and `DSLContext` inside it. Use `dsl.transaction(...)` only when specifically required and thoroughly tested alongside your manager.

## 12. DB Transactions vs. Message Brokers, HTTP, and Caches: Where ACID Ends

Integration flows may write PostgreSQL, send to Kafka/RabbitMQ, call REST APIs, update Redis, and upload files. A `JdbcTransactionManager` **manages only the local JDBC resource**. It never rolls back Kafka messages, HTTP side effects, or Redis writes when SQL rolls back.

### The "Dual Write" Problem

Example:

~~~java
@Transactional
public void createOrder(Order order) {
    orderRepository.insert(order);      // SQL transaction
    rabbitTemplate.convertAndSend(
            "orders.exchange", "order.created", order);
    // RabbitMQ publish is not automatically atomic with SQL commit.
}
~~~

Two hazards:

- Broker receives the event, then SQL commit fails → downstream sees a nonexistent order.
- SQL commits, then the app crashes before publishing → order exists in DB without any event.

A practical solution is the **transactional outbox**:

~~~mermaid
sequenceDiagram
    participant API as order-service
    participant DB as PostgreSQL
    participant RELAY as Outbox relay
    participant MQ as RabbitMQ/Kafka
    participant C as Consumer

    API->>DB: BEGIN
    API->>DB: INSERT orders
    API->>DB: INSERT outbox_events (eventId, payload)
    API->>DB: COMMIT
    RELAY->>DB: Read unpublished outbox
    RELAY->>MQ: Publish event
    MQ-->>RELAY: Publish confirmation
    RELAY->>DB: Mark published / save offset
    MQ->>C: Deliver
    C->>DB: Inbox idempotency + business transaction
~~~

The outbox commits atomically with business data in one SQL transaction. The relay may publish duplicates if the broker receives a message before the relay records completion; consumers handle that with idempotency. Mark outbox rows published only after sufficient confirmation per SLA and handle unroutable/failed publishes. Thus outboxes bridge the SQL–broker boundary reliably without claiming universal cross-system exactly-once delivery.

### Is `@TransactionalEventListener(AFTER_COMMIT)` Enough?

An `AFTER_COMMIT` listener avoids publishing prior to SQL commit, yet **if the process crashes after commit and before publishing**, the event is lost. It fits best-effort side effects; durable delivery requires an outbox or equivalent guarantee. Also note that when `AFTER_COMMIT` runs, the originating SQL transaction has already committed; any new DB writes require their own transaction boundary.

### Cache Invalidation

Updating Redis/caches inside an SQL transaction that later rolls back leaves the cache out of sync with the DB. Perform invalidations/updates **after commit** or via outbox-driven eventual consistency. Never expect a JDBC manager to roll back remote caches.

## 13. Handling Queries in Spring Integration Flows and Across Threads

A `@ServiceActivator`, `@JmsListener`, `@RabbitListener`, or HTTP controller can invoke an `@Transactional` Spring service when properly injected. However, once a flow hops across an asynchronous channel, executor, scheduled task, new virtual thread, or separate Reactor scheduler, **`ThreadLocal` transaction context does not transfer automatically**.

~~~mermaid
flowchart LR
    IN["HTTP / RabbitMQ / Integration channel"] --> SVC["Spring @Transactional Service"]
    SVC --> DB[("DB transaction on current thread")]
    SVC --> ASYNC["Async executor / different thread"]
    ASYNC --> NEWTX["Needs new transaction boundary if writing SQL"]
~~~

Practical examples:

- Spring Integration's `ExecutorChannel` hands messages to another thread; transactions begun on the prior thread do not follow the message.
- `@Async` executes on an executor; the target bean called on the new thread must define its own transaction boundary.
- `CompletableFuture.supplyAsync(...)` or `parallelStream()` must never be assumed to share the outer transaction's JDBC connection.
- In WebFlux, `@Transactional` with an imperative JDBC manager does not make blocking JDBC reactive; schedule JDBC onto dedicated bounded threads or move to R2DBC with `R2dbcTransactionManager`.
- When a message listener invokes a transactional service, **broker acknowledgement** happens at a separate boundary from SQL commit; align error handling, redelivery, and inboxes accordingly.

Across thread boundaries, **define explicit transaction boundaries per segment** and pass immutable data/IDs in messages rather than passing `Connection`, transaction-bound `DSLContext`, or thread-unsafe entities.

## 14. Measuring Connections, Transactions, and SQL to Find Bugs

A service can look healthy at the API layer while holding transactions too long or leaking connections outside the pool. Monitor:

| Signal | Meaning |
| --- | --- |
| Hikari active / idle / pending connections | Whether the pool is starved by long transactions, leaks, or under-sizing |
| Connection acquisition latency | Whether requests are queuing for connections |
| Transaction duration and rollback/commit rate | Excessively long transactions or spiking rollbacks |
| SQL latency, statement timeouts, lock waits | Separates slow queries from lock contention |
| Deadlock / serialization failures | Contention pressure and need for controlled retries |
| jOOQ query execution events | Pinpoints slow query shapes without logging bind values |
| Spring JDBC exception categories | Tracks transient vs. non-transient failures by path |
| Duplicate event / inbox hits | Measures redeliveries and deduplication effectiveness |
| Outbox backlog/age and publish failures | Surfaces DB-committed events stalled before the broker |
| Database session counts across instances | Checks whether aggregate pools across pods exceed server limits |

Spring Boot Actuator/Micrometer exports DataSource/Hikari metrics when configured; jOOQ `ExecuteListener` or custom instrumentation tracks SQL counts and latencies. Never enable full bind-parameter logging containing payment details, PII, or credentials in production. Log sanitized operation names, `requestId`, `eventId`, `correlationId`, affected row counts, and timings.

### Distinguishing Connection Leaks from Long-Locking Transactions

- **Leak**: application fails to release connections/streams or opens unclosed manual connections; active counts stay pinned high.
- **Long transaction**: Spring holds the connection legitimately, yet holds it far too long across HTTP calls, sleeps, slow SQL, or lock waits—still starving the pool.
- **`REQUIRES_NEW` exhaustion**: one logical request consumes multiple physical connections concurrently.
- **Connection churn**: repeatedly constructing new `DataSource`/`DSLContext`/client instances instead of reusing singletons.

Remedies differ: raising pool size only masks symptoms of bad transaction boundaries. Comparing `transaction duration` against `SQL time` reveals whether slowness stems from the DB or code holding connections while awaiting downstream I/O.

## 15. Testing Integrated Transactions Against a Real Database

Unit tests mocking `JdbcTemplate` and `DSLContext` verify method calls, **not that both share a connection or roll back together**. Write integration tests against a matching database engine—ideally PostgreSQL in Testcontainers/CI with production-like migrations.

### Minimum Scenarios

| Scenario | Setup | Expected Outcome |
| --- | --- | --- |
| All operations succeed | Inbox `INSERT` + jOOQ `UPDATE` + ledger `INSERT` | All three changes commit |
| Final JDBC query throws | Trigger constraint violation at ledger step | jOOQ `UPDATE` and inbox `INSERT` both roll back |
| jOOQ `UPDATE` affects 0 rows | Insufficient balance; service throws `RuntimeException` | Inbox rolls back; balance and ledger stay unchanged |
| Broker redelivers same `eventId` | Invoke twice with same event ID after commit | Second call does not debit again |
| Two consumers race on same `eventId` | Two concurrent deliveries | Unique inbox protects; net effect is one debit |
| Manager points to wrong `DataSource` | Miswired test configuration | Rollback test fails, catching wiring defect |
| Self-invocation | Annotated method invoked via `this` instead of proxy | Test reveals missing transaction boundary |
| Checked exception | Throw `IOException` with vs. without `rollbackFor` | Behavior matches declared policy |
| `REQUIRES_NEW` | Outer rolls back after inner commits | Demonstrates independence and extra connection cost |
| `NESTED` / savepoint | Nested block fails | Only post-savepoint work rolls back where DB/driver supports it |
| Deadlock / serialization failure | Two competing transactions | Entire transaction rolls back; bounded retry succeeds |
| Retry after SQL commit before ack | Inject fault on broker channel | Inbox idempotency prevents duplicate effect |
| Outbox relay crash | Publish before updating outbox state | May republish; consumer handles idempotently |

### Example Verifying Both JDBC and jOOQ Roll Back Together

An integration test calls the service through the Spring proxy and verifies DB state outside any test-managed rollback transaction:

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootTest
class WalletTransactionIntegrationTest {

    @Autowired WalletDebitService walletDebitService;
    @Autowired JdbcTemplate jdbc;

    @Test
    void rollsBackInboxAndWalletWhenLedgerInsertFails() {
        // Fixtures from migration/test setup:
        // wallet(42, 10000) exists;
        // ledger already has event_id = EVT-DUPLICATE,
        // while processed_events does not yet have this event.

        var event = new DebitAuthorized(
                "EVT-DUPLICATE", 42L, 1_500L);

        assertThatThrownBy(() -> walletDebitService.apply(event))
                .isInstanceOf(RuntimeException.class);

        Long balance = jdbc.queryForObject(
                "SELECT balance_cents FROM wallet WHERE account_id = ?",
                Long.class, 42L);
        Integer inboxRows = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM processed_events
                WHERE consumer_name = ? AND event_id = ?
                """,
                Integer.class, "wallet-debit-v1", "EVT-DUPLICATE");

        assertThat(balance).isEqualTo(10_000L);
        assertThat(inboxRows).isZero();
    }
}
~~~

This **test template** assumes fixtures are seeded beforehand and jOOQ codegen ran. Because `wallet_ledger` already holds the same event ID, the final `INSERT` violates its unique constraint and throws a `RuntimeException`; with proper transaction wiring, both the wallet `UPDATE` and inbox `INSERT` roll back. Isolate/clean up fixtures per test, and crucially **do not annotate the test method itself with `@Transactional`** (letting Spring Test roll back the entire test), because that masks defects in the service's own commit/rollback boundaries.

Add another integration test reading uncommitted writes across both `JdbcTemplate` and jOOQ within the same service to catch connection-provider mismatches early, and run parallel-transaction concurrency tests to verify isolation and locking.

## 16. Common Configuration Mistakes and Fixes

| Symptom | Common Cause | Check / Fix |
| --- | --- | --- |
| `@Transactional` present, yet jOOQ `UPDATE` commits when JDBC fails | jOOQ opens connections outside Spring transaction | Inject Boot's `DSLContext` or wrap `DataSource` in `TransactionAwareDataSourceProxy` |
| No transaction when calling method in same class | Self-invocation bypasses Spring proxy | Extract to another service bean or restructure call path |
| Multiple transaction managers; commits hit wrong DB | Selected manager does not match query `DataSource` | Use explicit qualifiers and test wiring |
| Using `JpaTransactionManager` alongside JDBC/jOOQ | Unverified `DataSource`/connection participation | Verify JPA/JDBC setup; align manager to resource |
| Service handles checked exception and data still commits | Checked exceptions do not roll back by default | Add `rollbackFor` matching contract |
| Exception caught and method returns normally | Spring treats normal return as success and commits | Rethrow appropriate exception or mark rollback-only intentionally |
| `UnexpectedRollbackException` in outer method | Inner `REQUIRED` marked transaction rollback-only | Trace inner root cause and adjust boundary/propagation |
| Pool exhausted during nested transactions | `REQUIRES_NEW` holds extra physical connections | Reduce nesting and tune orchestration/pool against load |
| Very long transactions despite fast SQL | Holding transactions across HTTP/broker calls or sleeps | Move remote I/O outside short transactions |
| Queries run non-transactionally inside `@Async` | `ThreadLocal` does not cross threads | Start a dedicated boundary on the async bean/service |
| jOOQ `dsl.transaction` lacks Spring semantics | `TransactionProvider` not wired to Spring manager | Configure Spring provider or standardize on `@Transactional` |
| RabbitMQ redelivery debits twice | SQL committed before ack without unique inbox | Keep stable `eventId`, transaction, and unique constraint |
| Order exists in DB, missing from Kafka/Rabbit | Non-atomic dual write | Use transactional outbox, relay, and idempotent consumer |
| `readOnly` fails to block `UPDATE` | Read-only hint ignored by driver/DB | Enforce DB grants and test real behavior |
| Tests pass, production rollback fails | Mocks or test-level `@Transactional` masked bug | Run real-DB integration tests with service-owned boundaries |

## 17. Checklist for Spring Boot Projects

1. Identify every **resource** accessed—single JDBC `DataSource`, JPA, R2DBC, or multiple databases—and match the transaction manager.
2. For imperative JDBC/jOOQ on one database, prefer `JdbcTransactionManager` or Boot's properly wired default; verify the runtime bean class.
3. Inject `JdbcTemplate`/`DSLContext` bound to the right `DataSource`; if creating jOOQ manually, use a Spring transaction-aware connection provider.
4. With multiple `DataSource`s/managers, assign clear bean names, qualifiers, and `@Transactional(transactionManager = "...")`, testing every path.
5. Place transaction boundaries on public Spring service methods called via proxies; avoid self-invocation and cross-thread async leaks.
6. Define exception and rollback rules deliberately; understand `REQUIRED`, `REQUIRES_NEW`, `NESTED`, isolation, and rollback-only semantics.
7. Keep transactions short, set realistic query/transaction timeouts, and measure lock, pool, and SQL latencies.
8. On retries, replay the **entire transaction** per policy with stable idempotency keys and bounded attempts.
9. When interacting with brokers, HTTP, caches, or object stores, mark clearly where ACID stops; use inbox/outbox, explicit states, and compensation where needed.
10. Test on a real database for joint JDBC–jOOQ rollbacks, concurrent duplicates, nested transactions, deadlocks, lost acks, and outbox replays.
11. Monitor transaction duration, rollbacks, pool usage, SQL latencies, idempotency hits, and outbox lag while keeping sensitive bind values out of logs.

### References for Version-Specific API Verification

- [Spring Framework – Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): declarative transactions, propagation, rollback rules, and resource binding.
- [Spring Framework – JDBC Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html): `DataSourceUtils`, `TransactionAwareDataSourceProxy`, and connection management.
- [Spring Boot – SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): `DataSource`, transaction managers, JDBC, and jOOQ auto-configuration.
- [jOOQ – Transactions](https://www.jooq.org/doc/latest/manual/sql-execution/transaction-management/): `DSLContext.transaction`, `TransactionProvider`, and transaction nesting.
- [Spring Framework – Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html): `TransactionTemplate` for explicit boundaries when annotations do not fit.

**Remember:** `@Transactional` declares intent, while **pairing the right resource-matched transaction manager with a transaction-aware connection provider** determines whether JDBC and jOOQ actually commit and roll back together. Verifying on a real database, enforcing business-key deduplication, and respecting boundaries around brokers, HTTP, and caches keep Spring Boot integration flows consistent across errors, retries, and connection drops.
