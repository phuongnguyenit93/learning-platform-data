# Separating Transactions and Resources When JDBC and R2DBC Coexist

A Spring application may need to use JDBC and R2DBC simultaneously during a migration period or because two workloads have different characteristics. For example, legacy modules still use `JdbcTemplate` for reads and writes while new modules use Spring Data R2DBC for reactive APIs. Flyway or Liquibase also typically use JDBC to run migrations, even when the application runtime uses R2DBC.

The key point to understand is that JDBC and R2DBC manage connections, transactions, and execution contexts through two separate mechanisms. A `DataSource` and a `ConnectionFactory` are two distinct resources. JDBC transactions are usually bound to the current thread; R2DBC reactive transactions propagate via the Reactor Context. Pointing both APIs to the same database does not make them automatically share a connection or a single transaction.

Without clear boundaries, an application can hit hard-to-diagnose failures: part of the data commits while the rest rolls back, `@Transactional` picks the wrong transaction manager, blocking JDBC calls run on the event loop, connection pools are undersized, or tests behave differently from runtime.

This lesson explains how Spring manages both resource types, how to configure `DataSource` and `ConnectionFactory` separately, choose `PlatformTransactionManager` and `ReactiveTransactionManager`, combine blocking and reactive code safely, handle cross-transaction consistency, use JDBC migrations in an R2DBC application, and test realistic commit/rollback scenarios.

## 1. Resource Model: JDBC and R2DBC Are Two Separate Connection Paths

An application using both technologies typically has two distinct stacks:

~~~text
Spring Application
    |
    +------------------------------+
    |                              |
    v                              v
JDBC / imperative              R2DBC / reactive
    |                              |
    v                              v
DataSource                    ConnectionFactory
    |                              |
    v                              v
JDBC Connection               R2DBC Connection
    |                              |
    v                              v
PlatformTransactionManager    ReactiveTransactionManager
    |                              |
    v                              v
Thread-bound transaction      Reactor Context transaction
    |                              |
    v                              v
JdbcTemplate / JDBC DAO        DatabaseClient / R2DBC Repository
    |                              |
    +--------------+---------------+
                   |
                   v
             Database server
~~~

Both branches can connect to the same database server, the same database, and even the same schema. Even so, connections are created and managed independently.

| Component | JDBC | R2DBC |
|---|---|---|
| Connection API | DataSource | ConnectionFactory |
| Connection | java.sql.Connection | io.r2dbc.spi.Connection |
| Common access APIs | JdbcTemplate, JDBC DAO, Spring Data JDBC/JPA | DatabaseClient, Spring Data R2DBC |
| Transaction manager | PlatformTransactionManager, e.g. DataSourceTransactionManager | ReactiveTransactionManager, e.g. R2dbcTransactionManager |
| Transaction context | Typically thread-bound | Bound to Reactor Context |
| Common pool | HikariCP | r2dbc-pool |
| Execution model | Blocking | Non-blocking when supported by driver and pipeline |

You cannot convert a JDBC `Connection` into an R2DBC `Connection` or vice versa. The R2DBC SPI and JDBC API have different lifecycles, protocols, and connection types.

## 2. Why Sharing the Same Database Does Not Create a Shared Transaction

Suppose a request performs two operations:

1. Uses `JdbcTemplate` to update the `account` table.
2. Uses an R2DBC repository to create an `audit` record.

Even though both operations target the same PostgreSQL database, each stack acquires its own connection:

~~~text
JDBC transaction
  Connection J1
  UPDATE account ...
  COMMIT

R2DBC transaction
  Connection R1
  INSERT audit ...
  ROLLBACK
~~~

If the second step fails after the first has committed, the `account` update remains persisted. Neither transaction manager automatically rolls back the JDBC transaction just because the R2DBC transaction failed.

A database server can manage many concurrent transactions, but it cannot infer that two connections from two separate APIs belong to the same business unit of work. Coordinating two resource managers requires an explicitly supported distributed transaction mechanism; sharing a database URL is not enough.

### 2.1. What Is Not Shared

JDBC and R2DBC do not automatically share:

- Connections.
- Transaction status.
- Savepoints.
- Rollback scope.
- Thread/Reactive Context.
- Connection pools.
- Timeout and isolation settings.
- Locks or visibility semantics of an uncommitted transaction.

The database still enforces locks and visibility of committed data according to isolation levels. However, an open transaction on a JDBC connection does not become the transaction of an R2DBC connection.

### 2.2. Same Schema Does Not Mean Same Transaction

For instance, JDBC inserts a row but has not yet committed. An R2DBC query on another connection typically does not see the uncommitted row under common isolation levels such as `READ COMMITTED`. Depending on isolation and the database, it may wait on a lock or read a different snapshot, but it does not participate in the JDBC transaction.

If JDBC commits first, an R2DBC transaction started afterward can read the committed data. That is ordering between two independent transactions, not shared atomicity.

## 3. Configuring Separate Dependencies and URLs

An application needs dependencies for both stacks. Gradle example:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    implementation("org.springframework.boot:spring-boot-starter-data-r2dbc")

    runtimeOnly("org.postgresql:postgresql")
    runtimeOnly("org.postgresql:r2dbc-postgresql")

    // If using Flyway for migrations:
    implementation("org.flywaydb:flyway-core")
}
~~~

Versions should be managed by Spring Boot dependency management/BOM. Do not pin Spring Data, Spring Framework, or R2DBC SPI versions manually without verifying compatibility.

The JDBC driver and R2DBC driver are distinct artifacts even when from the same vendor for the same database engine.

### 3.1. Configuring application.yml

Example with two URLs pointing to the same PostgreSQL database:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: app_user
    password: jdbc-secret-injected
    hikari:
      maximum-pool-size: 12
      connection-timeout: 3000

  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: app_user
    password: r2dbc-secret-injected
    pool:
      enabled: true
      initial-size: 2
      max-size: 8
      max-acquire-time: 3s
~~~

Pool properties and names may vary by Spring Boot version. Check the configuration metadata for your release. If URLs, usernames, or credentials differ, verify that both stacks actually connect to the intended database and schema.

Never commit real passwords to source control. Use a secret manager or separate environment variables per connection.

### 3.2. Why Two Drivers Are Needed

A JDBC driver implements the `java.sql` API and usually returns blocking connections. An R2DBC driver implements the `io.r2dbc.spi` SPI with a reactive API.

You cannot use a JDBC dependency to build an R2DBC `ConnectionFactory` merely by changing the URL prefix. Nor can you pass an `r2dbc:postgresql:` URL to HikariCP.

### 3.3. If the Two Stacks Point to Different Databases

Configuration must make each stack's database/schema explicit. Do not rely on identical default schemas or search paths across connections. Each pool may have different session settings, timezones, roles, search paths, and isolation levels.

If JDBC and R2DBC point to different databases, the consistency issue is even clearer: two local transactions cannot roll each other back.

## 4. Declaring Two Explicit Transaction Managers

When multiple transaction managers exist, give them clear names so callers choose the right one.

~~~java
@Configuration
public class PersistenceTransactionConfiguration {

    @Bean("jdbcTransactionManager")
    PlatformTransactionManager jdbcTransactionManager(
            DataSource dataSource) {

        return new DataSourceTransactionManager(dataSource);
    }

    @Bean("r2dbcTransactionManager")
    ReactiveTransactionManager r2dbcTransactionManager(
            ConnectionFactory connectionFactory) {

        return new R2dbcTransactionManager(connectionFactory);
    }

    @Bean("r2dbcTransactionalOperator")
    TransactionalOperator r2dbcTransactionalOperator(
            @Qualifier("r2dbcTransactionManager")
            ReactiveTransactionManager transactionManager) {

        return TransactionalOperator.create(transactionManager);
    }
}
~~~

Key imports:

~~~java
import javax.sql.DataSource;
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.r2dbc.connection.R2dbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.ReactiveTransactionManager;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.reactive.TransactionalOperator;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
~~~

`javax.sql.DataSource` belongs to Java SE. Spring packages may vary by generation; use compatible Spring Framework/Spring Boot dependencies.

Spring Boot may auto-configure one or both transaction managers depending on the classpath and existing beans. When declaring managers explicitly, check auto-configuration conditions to avoid creating competing beans or accidentally binding the wrong `DataSource`/`ConnectionFactory`.

### 4.1. Using DataSourceTransactionManager for JDBC

`DataSourceTransactionManager` manages JDBC transactions for a `DataSource`. Newer Spring Framework versions also offer `JdbcTransactionManager`, which adds extra JDBC exception handling; the choice depends on version.

The key requirement is that the manager controls the exact `DataSource` used by `JdbcTemplate`/JDBC DAOs.

### 4.2. Using R2dbcTransactionManager for R2DBC

`R2dbcTransactionManager` manages transactions for a `ConnectionFactory`. Repositories and `DatabaseClient` must use the same managed `ConnectionFactory` to participate in the transaction.

If multiple `ConnectionFactory` beans exist, declare a matching transaction manager per resource and make clear which repository uses which resource.

### 4.3. Avoid Relying on a Default Manager When Multiple Exist

When multiple transaction managers exist in the context, default resolution can depend on bean name, type, qualifiers, or `@Primary`. Never let default resolution implicitly decide the transaction manager for an important operation.

Explicit naming and qualifiers make it clear in code reviews which resource a transaction spans.

## 5. Binding @Transactional Correctly to Each Stack

### 5.1. JDBC Methods Use the JDBC Transaction Manager

~~~java
@Service
public class LegacyAccountService {

    private final JdbcTemplate jdbcTemplate;

    public LegacyAccountService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(transactionManager = "jdbcTransactionManager")
    public void updateBalance(Long accountId, BigDecimal amount) {
        jdbcTemplate.update(
                """
                UPDATE account
                SET balance = balance + ?
                WHERE id = ?
                """,
                amount,
                accountId);
    }
}
~~~

The transaction is opened by the JDBC transaction manager. `JdbcTemplate` acquires a connection through Spring's synchronization mechanism and joins the active transaction on the executing thread.

### 5.2. R2DBC Methods Returning Publishers Use the Reactive Manager

~~~java
@Service
public class AuditService {

    private final AuditRepository repository;

    public AuditService(AuditRepository repository) {
        this.repository = repository;
    }

    @Transactional(transactionManager = "r2dbcTransactionManager")
    public Mono<AuditEntry> record(AuditEntry entry) {
        return repository.save(entry);
    }
}
~~~

The reactive transaction is bound to the publisher's lifecycle and propagated via Reactor Context. The method must return the publisher so the transaction manager spans subscription and terminal signals.

### 5.3. Do Not Use the JDBC Manager for Reactive Methods

A method returning `Mono` must not be configured with a JDBC `PlatformTransactionManager` expecting it to manage R2DBC queries. A JDBC manager cannot drive an R2DBC `ConnectionFactory`.

Similarly, an R2DBC transaction manager does not manage `JdbcTemplate`. Match return types and transaction managers to their proper stack.

### 5.4. Separate Services by Resource

A clear design structure:

- `LegacyAccountService`: JDBC and `jdbcTransactionManager`.
- `ReactiveAuditService`: R2DBC and `r2dbcTransactionManager`.
- `AccountWorkflowService`: coordinates steps without assuming two local transactions are atomic.

Separating services clarifies transaction boundaries and reduces the risk of a class-level annotation accidentally applying the wrong manager to a method on the other stack.

### 5.5. Self-Invocation and Proxies

Spring typically applies `@Transactional` via proxies. If a method in the same class calls another transactional method on `this` directly, the internal call may bypass the proxy so transaction advice is not applied as expected.

Move transaction boundaries to separate beans or use `TransactionTemplate`/`TransactionalOperator` explicitly when direct control is needed.

## 6. Thread-Bound JDBC Transactions vs. R2DBC Reactor Context

This is the fundamental difference when both technologies coexist.

### 6.1. JDBC Transactions Are Thread-Bound

JDBC transactions in Spring typically rely on thread-bound resources. `DataSourceTransactionManager` binds the JDBC `Connection` to the current thread. `JdbcTemplate` looks up that bound connection via Spring's resource synchronization.

Therefore:

- JDBC calls in the same transaction must execute on the appropriate thread/context.
- Switching JDBC work to another thread can break transaction participation.
- Never hold a JDBC `Connection` and use it arbitrarily across multiple threads.
- An imperative transaction does not propagate automatically through Reactor Context.

### 6.2. R2DBC Transactions Use Reactor Context

The reactive transaction manager uses Reactor Context to carry transaction resources down the publisher chain.

Spring-integrated repositories and `DatabaseClient` retrieve the connection bound to the active transaction context. Switching schedulers in a Reactor chain does not carry the same semantics as a `ThreadLocal` JDBC transaction.

Do not call an independent `subscribe()` mid-pipeline because the detached subscription may lose the original chain's context and transaction.

### 6.3. Contexts Do Not Bridge Automatically into One Transaction

Micrometer Context Propagation or Reactor context bridges do not merge two protocols into one transaction manager.

Context propagation can carry metadata, traces, or selected `ThreadLocal` values; it does not unify two connections or enlist an unenlisted resource into another transaction manager.

## 7. Blocking JDBC Calls in a WebFlux Application

If a WebFlux request must invoke JDBC during a transition phase, the JDBC call must be isolated off event-loop threads.

Example reading with `JdbcTemplate`:

~~~java
public Mono<LegacyAccount> findLegacyAccount(Long id) {
    return Mono.fromCallable(() ->
                    jdbcTemplate.queryForObject(
                            """
                            SELECT id, account_name, balance
                            FROM account
                            WHERE id = ?
                            """,
                            accountRowMapper,
                            id))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

`boundedElastic` is meant for bounded blocking work. This is a transitional adapter, not a way to make JDBC non-blocking.

Keep in mind:

- Bound concurrency of blocking calls.
- Set query timeouts and connection timeouts.
- Monitor scheduler queues.
- Never call `block()` from an event-loop thread.
- Never share a JDBC connection across threads.
- Plan to replace with R2DBC or isolate into an imperative module where appropriate.

### 7.1. JDBC Transactions Must Wrap the Entire Blocking Work on the Same Thread

If multiple JDBC statements are needed inside one transaction, use `TransactionTemplate` inside the blocking callable:

~~~java
public Mono<LegacyAccount> updateLegacyAccount(
        Long accountId,
        BigDecimal amount) {

    return Mono.fromCallable(() ->
                    jdbcTransactionTemplate.execute(status -> {
                        jdbcTemplate.update(
                                "UPDATE account SET balance = balance + ? WHERE id = ?",
                                amount,
                                accountId);

                        return jdbcTemplate.queryForObject(
                                "SELECT id, account_name, balance FROM account WHERE id = ?",
                                accountRowMapper,
                                accountId);
                    }))
            .subscribeOn(Schedulers.boundedElastic());
}
~~~

`TransactionTemplate.execute` opens, commits, or rolls back the JDBC transaction before returning the result. JDBC calls inside the callback participate in the same transaction because they run within the same callback and thread.

Never construct and return a `Mono` from inside the `TransactionTemplate` callback, allowing the JDBC transaction to end before the publisher executes. `TransactionTemplate` is imperative: the callback must finish synchronous JDBC work within the transaction scope.

### 7.2. Wrapping JDBC in fromCallable Does Not Create a Transaction

This only offloads the blocking call:

~~~java
Mono.fromCallable(() -> jdbcTemplate.update(...))
        .subscribeOn(Schedulers.boundedElastic());
~~~

It does not create a transaction without an explicit transaction boundary. If atomicity across multiple JDBC statements is needed, use `@Transactional` on an imperative method called through a proxy, or `TransactionTemplate` inside the callable.

## 8. Combining JDBC and R2DBC in the Same Workflow

You may need to orchestrate two steps inside one reactive service—for example, updating legacy data via JDBC and then writing new data via R2DBC.

~~~java
public Mono<WorkflowResult> execute(Command command) {
    return Mono.fromCallable(() ->
                    jdbcTransactionTemplate.execute(status ->
                            legacyDao.update(command)))
            .subscribeOn(Schedulers.boundedElastic())
            .flatMap(jdbcResult ->
                    r2dbcTransactionalOperator.transactional(
                            reactiveRepository.save(
                                    toReactiveEntity(command, jdbcResult)))
                            .map(audit ->
                                    new WorkflowResult(
                                            jdbcResult.id(),
                                            audit.getId())));
}
~~~

Regarding transaction semantics:

1. The JDBC transaction runs on a `boundedElastic` thread.
2. `TransactionTemplate.execute` commits or rolls back before emitting the JDBC result.
3. Then the R2DBC transaction opens for the `save` publisher.
4. If R2DBC fails, the already-committed JDBC transaction does not roll back automatically.

These are two independent transactions orchestrated sequentially.

### 8.1. Failure After the First Step Has Committed

~~~text
JDBC transaction:
  UPDATE legacy_account
  COMMIT
            |
            v
R2DBC transaction:
  INSERT new_audit
  ERROR
  ROLLBACK
~~~

The resulting state is an updated account with no audit record written. This is partial completion and must be designed and handled as a real business scenario.

Never describe this workflow as atomic merely because both steps reside in one Java method or one reactive chain.

### 8.2. Do Not Hold an R2DBC Transaction Open While Waiting on Slow JDBC

You could wrap the entire workflow in R2DBC `TransactionalOperator` and invoke JDBC in the middle. Doing so can hold an R2DBC connection/transaction open while the blocking JDBC call runs, yet JDBC still does not participate in that transaction.

That lengthens the R2DBC transaction, increases connection hold time, and gives no atomicity. Wrap only the R2DBC work requiring a transaction with the reactive manager; wrap the JDBC work with the JDBC manager.

### 8.3. Reversing the Order Does Not Solve It

If R2DBC commits first and JDBC fails, the inverse occurs: reactive data commits while legacy data remains un-updated.

Reordering does not solve consistency. You need idempotency, an outbox, retries/reconciliation, or compensation.

## 9. Can One @Transactional Cover Both JDBC and R2DBC?

You cannot achieve an atomic transaction across both resources with a single `@Transactional` annotation.

A transaction manager manages only the type of resource it knows how to control. `DataSourceTransactionManager` manages a JDBC `DataSource`; `R2dbcTransactionManager` manages an R2DBC `ConnectionFactory`.

The following does not create a shared transaction:

~~~java
@Transactional(transactionManager = "jdbcTransactionManager")
public Mono<Result> doBoth() {
    // JDBC operation
    // R2DBC repository operation
    return reactiveRepository.save(...).map(...);
}
~~~

The JDBC manager does not control reactive connections. Depending on interception and return types, an incompatible manager configuration may fail to work or leave the reactive subscription outside the transaction scope. Do not use this combination.

Nor should you place a class-level `@Transactional` expecting Spring to automatically switch managers per statement inside a method. Specify the manager per method/service and divide boundaries clearly.

## 10. Multiple Transaction Managers and @Primary

When multiple manager beans exist, Spring must resolve which manager applies to a transaction annotation or API.

Guidelines:

- Give beans clear names such as `jdbcTransactionManager` and `r2dbcTransactionManager`.
- Specify `@Transactional(transactionManager = "...")` on declarative transactional methods.
- Use `@Qualifier` when injecting managers or operators.
- Use `@Primary` only if one manager genuinely serves as the default for most imperative/reactive call sites.
- Never treat `@Primary` as a mechanism that dynamically chooses between JDBC and R2DBC per query.
- Verify the actual manager beans in the application context.

If a class has both JDBC and R2DBC methods, splitting into two services is usually clearer than relying on a class-level default annotation.

### 10.1. Using TransactionTemplate for JDBC

~~~java
@Bean
TransactionTemplate jdbcTransactionTemplate(
        @Qualifier("jdbcTransactionManager")
        PlatformTransactionManager transactionManager) {

    return new TransactionTemplate(transactionManager);
}
~~~

`TransactionTemplate` makes imperative transaction boundaries explicit at the call site, which is especially helpful when wrapping blocking work inside `Mono.fromCallable`.

### 10.2. Using TransactionalOperator for R2DBC

~~~java
@Bean
TransactionalOperator r2dbcTransactionalOperator(
        @Qualifier("r2dbcTransactionManager")
        ReactiveTransactionManager transactionManager) {

    return TransactionalOperator.create(transactionManager);
}
~~~

`TransactionalOperator` wraps a publisher. When the publisher completes successfully, the transaction commits; when errors or cancellations are handled under transaction semantics, the transaction manager performs the appropriate cleanup/rollback.

## 11. Propagation and Isolation Do Not Cross Resource Managers

Attributes such as `REQUIRED`, `REQUIRES_NEW`, `SUPPORTS`, `MANDATORY`, isolation, and timeout apply within their respective transaction manager/resource scope.

For example:

- `REQUIRES_NEW` on the JDBC manager starts a new JDBC transaction.
- `REQUIRES_NEW` on the R2DBC manager starts a new R2DBC transaction.
- A JDBC `REQUIRES_NEW` does not suspend or enlist an R2DBC transaction as the same resource.
- JDBC transaction isolation does not automatically set isolation on an R2DBC connection.

If a business operation spans two resources, design separate orchestration and consistency policies.

### 11.1. Different Isolation Across Connections

The JDBC transaction might use `READ COMMITTED` while the R2DBC transaction uses `REPEATABLE READ`. Reads can observe different results depending on timing and snapshots.

Configure isolation explicitly on each transaction manager when business logic depends on it. Verify which isolation levels the database supports and the driver's actual semantics.

### 11.2. Do Not Hold Transactions Open Across External Calls

Neither a JDBC nor an R2DBC transaction should stay open while waiting on HTTP services, message brokers, or slow file operations. Doing so holds connections and locks unnecessarily.

Break work into short transactional steps and use outbox/saga patterns when coordination is required.

## 12. Why Not Use ChainedTransactionManager for Atomicity?

Some older Spring Data codebases contain `ChainedTransactionManager`, which coordinates multiple transaction managers on a best-effort basis. It is not equivalent to a distributed transaction coordinator with two-phase prepare/commit.

If one manager commits successfully and the next manager fails, the system ends up in a partial commit state. Compensating rollback cannot guarantee reversing an already-committed transaction in all cases.

`ChainedTransactionManager` has been deprecated in relevant Spring Data generations and should not be the foundation for new atomic cross-resource designs.

Do not label a chain of transaction managers a global transaction and assume two database resources commit atomically.

## 13. XA and Distributed Transactions

JDBC can support XA via `XADataSource` and an appropriate resource manager. Spring can integrate a JTA transaction manager with XA-capable resources.

However, the standard R2DBC SPI does not provide a universal XA equivalent for enlisting an R2DBC `ConnectionFactory` into a distributed two-phase commit transaction. Specific capabilities must be verified with the driver and transaction coordinator, never inferred from JDBC XA support on the same database.

Even when both resources support XA and operational infrastructure runs a transaction coordinator, 2PC comes with overhead, lock retention, recovery logs, and operational complexity.

With typical JDBC + R2DBC setups, assume they are two independent local transactions unless concrete implementation proof demonstrates shared enlistment.

## 14. Transactional Outbox to Synchronize Two Persistence Paths

When a business operation must update a primary database and notify another system or persistence path, a Transactional Outbox is usually a better fit than trying to force a shared transaction.

Example where the primary database is updated via R2DBC:

~~~text
R2DBC transaction
  UPDATE business_record
  INSERT outbox_event
  COMMIT
        |
        v
Outbox relay / CDC
        |
        v
Event broker
        |
        v
JDBC consumer
  BEGIN JDBC transaction
  UPDATE legacy_store
  INSERT processed_event_id
  COMMIT
~~~

The business record and the outbox event are inside the same R2DBC transaction. If the transaction rolls back, both roll back. If it commits, the relay can publish the event afterward.

The JDBC consumer processes the event inside its own JDBC transaction. Recording the processed event ID alongside the business update makes the consumer idempotent.

If primary data is written via JDBC, you can write the outbox entry in the same JDBC transaction and relay it via another worker.

### 14.1. Outbox Is Not Automatically Exactly-Once

The relay can re-send an event if the process crashes after publishing but before marking it sent. Consumers require idempotency/deduplication.

The design needs:

- Stable event IDs.
- Unique constraint on processed events.
- Bounded retries and a dead-letter policy.
- Event ordering if aggregates require it.
- Outbox cleanup/retention.
- Metrics for backlog and publish failures.

Outbox gives atomicity between the business write and the outbox record within one resource transaction. Propagation to the other resource is eventual consistency.

## 15. Saga and Compensation

When a workflow spans multiple steps across multiple resources, it can be modeled as a saga:

~~~text
Step 1: JDBC reserve legacy resource
       |
       v
Step 2: R2DBC create new record
       |
       v
Step 3: Publish confirmation
       |
       +---- failure?
               |
               v
       Compensation for completed steps
~~~

Compensation is a new business operation that reverses or adjusts already-committed state—it is not rolling back the old transaction.

Example:

- JDBC reserved inventory.
- R2DBC order creation failed.
- Saga calls JDBC to release the reservation.
- If compensation also fails, persist state requiring retry/reconciliation.

Not every action has perfect compensation. Sending an email or pushing a user-visible notification cannot be undone like a SQL rollback.

A saga requires a durable state machine, idempotency, retries, timeouts, auditing, and a strategy for failed compensations.

## 16. Choosing One Technology as Transaction Owner Per Use Case

One way to simplify the architecture is to pick one persistence technology as the transaction owner for each use case.

| Use Case | Transaction Owner | Resource |
|---|---|---|
| Reactive order creation API | R2DBC | ConnectionFactory |
| Legacy batch account update | JDBC | DataSource |
| Flyway migration | JDBC | DataSource |
| Writing outbox alongside order | R2DBC if order uses R2DBC | Same R2DBC transaction |
| Synchronizing legacy store | JDBC consumer transaction | DataSource |

If a use case must update two resources, treat it as a multi-step workflow with an explicit consistency policy instead of squeezing it into a single local transaction.

In some systems, moving the whole use case to JDBC or the whole use case to R2DBC dramatically reduces complexity. Keeping both technologies carries operational cost and requires clear justification.

## 17. Flyway/Liquibase Using JDBC in an R2DBC Application

A common coexistence scenario is using R2DBC at runtime while running schema migrations over JDBC.

Reason: Flyway/Liquibase have mature JDBC integrations, and migrations typically run at startup/deploy time rather than on the reactive request path.

Example configuring a JDBC datasource for migrations and R2DBC for runtime:

~~~yaml
spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/orders
    username: migration_user
    password: migration-secret-injected

  r2dbc:
    url: r2dbc:postgresql://localhost:5432/orders
    username: app_user
    password: r2dbc-secret-injected
~~~

You can use migration credentials with higher DDL privileges and runtime credentials restricted to required DML privileges. Avoid using high-privilege migration credentials on the request path unless necessary.

### 17.1. Migration Runs in a Separate JDBC Transaction

Flyway/Liquibase execute migrations through a `DataSource`/connection they manage. Once migrations finish, the R2DBC application connects to the updated schema.

Migrations do not join R2DBC reactive transactions. Normally that is desirable: schema changes complete before the application serves traffic.

### 17.2. If Only spring.r2dbc.url Is Configured

Some migration tools require a JDBC URL and JDBC driver. If only an R2DBC URL is present, the migration tool may not know how to connect.

Configure JDBC separately or configure Flyway/Liquibase explicitly according to your Spring Boot and migration tool versions. Inspect startup logs to confirm migrations ran against the right database/schema.

### 17.3. Deployment Order and Schema Compatibility

When rolling deployments run multiple application versions simultaneously, migrations should follow an expand-and-contract strategy:

1. Add columns/tables compatible with the old code.
2. Deploy new code capable of reading both old/new schemas if necessary.
3. Backfill data.
4. Shift traffic/behavior.
5. Drop old schema structures in a later release after no consumers remain.

Never run destructive migrations before all old instances and workers have stopped using those columns/tables.

## 18. Managing Connection Lifecycles Separately

### 18.1. JDBC with JdbcTemplate

`JdbcTemplate` handles acquiring and releasing connections according to transaction context. Prefer `JdbcTemplate` over calling `dataSource.getConnection()` manually.

If lower-level JDBC APIs are needed, use `DataSourceUtils` or Spring's transaction-aware mechanisms. Never close a connection manually while it belongs to an active transaction.

### 18.2. R2DBC with Repositories/DatabaseClient

Spring Data R2DBC repositories and `DatabaseClient` integrate with Spring's connection management. If using the raw R2DBC SPI directly, manage connection lifecycles reactively—for example with `usingWhen`—ensuring release on completion, error, and cancellation.

Never call `ConnectionFactory.create()` and forget to close/release. Connection leaks in R2DBC will steadily grow the pool's pending queue.

### 18.3. Never Share Connections Across Requests

Neither a JDBC `Connection` nor an R2DBC `Connection` is a thread-safe object to share across concurrent requests. Connection pools lease connections per transaction/operation lifecycle.

Never store connections in singleton fields or caches. Never pass connections across messages or schedulers.

## 19. Sizing Connection Budgets Across Both Pools

When running both stacks, total connections can nearly double compared to a single pool.

Example:

- Each instance has JDBC Hikari max 12.
- Each instance has R2DBC pool max 8.
- There are 3 instances.

Total potential connections:

\[
3 \times (12 + 8) = 60
\]

This excludes migrations, admin consoles, monitoring, batch workers, and connections from other applications.

An overall budget:

\[
C_{\text{total}}
=
N_{\text{replicas}}
\times
(C_{\text{JDBC}} + C_{\text{R2DBC}})
+
C_{\text{other}}
\]

Compare against the database's session limit. If both pools point to the same database server, they draw from the same connection budget.

### 19.1. Separate Timeouts

JDBC has connection timeout, validation timeout, query timeout, and socket timeout depending on the pool/driver. R2DBC pools have acquire/create/idle lifetime and driver-specific timeouts.

Do not assume one pool's timeouts automatically apply to the other. Configure and monitor them separately.

### 19.2. Pool Exhaustion Can Happen Independently

The JDBC pool may still have idle connections while the R2DBC pool has pending acquires, or vice versa. One request might succeed on one stack and time out on the other.

Dashboards must separate metrics by pool/resource rather than collapsing everything into a single undifferentiated database connections count.

## 20. Avoiding Cross-Pool Deadlocks

One workflow might hold a JDBC connection while waiting on an R2DBC operation, while another holds an R2DBC connection while waiting on a JDBC operation. If both pools are small and transactions hold connections long, chained waiting or application-level deadlock can occur.

Mitigations:

- Avoid holding one transaction open while calling the other resource.
- Enforce a consistent acquisition order if a workflow must touch both resources.
- Never run blocking JDBC on the event loop.
- Configure acquire and query timeouts.
- Keep transaction scopes short.
- Bound concurrency.
- Use outbox/saga to decouple steps when appropriate.

A local transaction should hold only the resource required for its own work.

## 21. Read-After-Write and Visibility Between Stacks

If JDBC commits and then R2DBC queries the same table, R2DBC usually sees the committed data under the new transaction's isolation level.

However, watch out for these cases:

- The JDBC write has not committed yet.
- The R2DBC transaction opened a snapshot before JDBC committed.
- The two transactions use different isolation levels.
- A read replica has replication lag.
- The two URLs point to different databases/schemas.
- Connection sessions have different search paths, timezones, or roles.

Do not treat sharing a database as proof of instantaneous consistency. Define commit ordering, isolation, primary/replica routing, and retry behavior explicitly.

## 22. Testing Two Transaction Managers

Unit tests mocking `JdbcTemplate` and repositories do not prove that two transactions actually stay isolated or roll back properly. Integration tests against the target database engine are required.

You can use Testcontainers PostgreSQL and configure both a JDBC `DataSource` and an R2DBC `ConnectionFactory` pointing to the same container.

### 22.1. Testing JDBC Rollback

Execute two JDBC statements inside `TransactionTemplate`, deliberately throw an exception midway, and then read via a fresh JDBC or R2DBC connection to verify no changes committed.

### 22.2. Testing R2DBC Rollback

Wrap two R2DBC operations in `TransactionalOperator`, fail the second operation, and then read via a fresh connection to confirm the first operation rolled back as well.

### 22.3. Testing Partial Commit Between Stacks

Scenario:

1. JDBC transaction updates the legacy table and commits.
2. R2DBC transaction inserts an audit entry and emits an error.
3. Read via both APIs.
4. Confirm the JDBC update persists while the audit record does not exist.

This test demonstrates that the two local transactions are not atomic together.

### 22.4. Testing Blocking Calls in WebFlux

Use integration tests with real requests or instrumentation to confirm JDBC calls are offloaded off the event loop. Test concurrency and timeouts when the JDBC pool saturates.

Do not check only for HTTP 200; verify thread/execution boundaries and transaction behavior.

### 22.5. Avoiding Misleading Test @Transactional Usage

A JUnit test wrapped in JDBC `@Transactional` does not automatically cover HTTP requests running on another server thread or publishers subscribed in another context.

Likewise, reactive transaction tests must subscribe to the publisher and check results after terminal signals. Never assume the test thread's transaction covers every reactive operation.

## 23. Tool Selection Matrix

| Scenario | Approach |
|---|---|
| Entire use case uses JDBC | `@Transactional` with JDBC manager or `TransactionTemplate` |
| Entire use case uses R2DBC | Reactive `@Transactional` or `TransactionalOperator` |
| WebFlux calling legacy JDBC | Isolate blocking calls on `boundedElastic`, keep JDBC transaction inside that callback/thread |
| JDBC then R2DBC in one workflow | Two separate transactions with an explicit consistency policy |
| Need atomicity for business write and event | Outbox within the same transaction manager/resource |
| Need updates across two independent databases | Saga, outbox, idempotency, and reconciliation |
| Schema migrations for an R2DBC app | Flyway/Liquibase over a JDBC `DataSource` if the tool uses JDBC |
| Want to roll back JDBC when R2DBC fails | Not possible via ordinary local transaction managers; requires supported distributed transactions or compensation design |

## 24. Common Mistakes When JDBC and R2DBC Coexist

| Mistake | Consequence | Fix |
|---|---|---|
| Thinking same database means same transaction | One stack commits while the other rolls back | Treat each connection/resource as its own transaction |
| Using JDBC manager for R2DBC repositories | R2DBC operations are not managed by JDBC manager | Use `R2dbcTransactionManager` |
| Using R2DBC manager for `JdbcTemplate` | JDBC calls do not join reactive transactions | Use `PlatformTransactionManager` for `DataSource` |
| Relying on default `@Transactional` with multiple managers | Methods may pick the wrong manager | Specify `transactionManager`/qualifier explicitly |
| Putting class-level `@Transactional` on mixed methods | Unclear boundaries and misconfiguration risk | Split services by resource |
| Calling JDBC on the event loop | Blocks requests and degrades throughput | Offload to `boundedElastic` or keep imperative boundary |
| Wrapping JDBC in `fromCallable` without a tx | Multiple statements may auto-commit separately | Use `TransactionTemplate`/JDBC manager |
| Spanning a JDBC transaction across scheduler hops | Thread-bound connection loses context | Keep the entire JDBC callback on one thread |
| Holding an R2DBC transaction while waiting on slow JDBC | Holds connection without providing atomicity | Separate transaction scopes |
| Calling independent `subscribe()` | Loses lifecycle, errors, and Reactor Context | Chain publishers and let the framework manage them |
| Sizing both stacks with the same pool size | Total connections exceed DB limits | Budget each pool across all replicas |
| Using `ChainedTransactionManager` as 2PC | Partial commits can still occur | Outbox/saga or genuinely supported XA |
| Assuming Flyway uses the R2DBC URL | Migrations fail to connect | Configure a JDBC `DataSource`/driver |
| Testing only with H2 or mocks | Misses transaction/driver differences | Test against the target database engine |
| Assuming test-thread rollback wraps HTTP requests | Test data commits unexpectedly | Test transactions in their real execution context |
| Mismatched credentials/session configs | Different schemas, roles, or timezones | Verify configuration of both pools |

## 25. Safe Transition Process While Keeping Both JDBC and R2DBC

A practical roadmap:

1. List all modules and call sites using JDBC.
2. List all repositories, `DatabaseClient` usages, and `ConnectionFactory` beans using R2DBC.
3. Verify database/schema and credentials for each resource.
4. Configure `DataSource`/JDBC driver and `ConnectionFactory`/R2DBC driver separately.
5. Declare separate transaction managers with clear names/qualifiers.
6. Bind each service method to the correct transaction manager.
7. Keep blocking JDBC calls off the event loop and wrap transactions in the same callback/thread.
8. Never assume a single orchestration method creates atomicity across two managers.
9. Choose outbox, saga, idempotency, or compensation for cross-resource consistency.
10. Run migrations over JDBC if required by the tool, before runtime serves traffic.
11. Calculate total connection budget across both pools and all replicas.
12. Add metrics/health checks for each pool and transaction path.
13. Test JDBC rollback, R2DBC rollback, and partial commits between stacks.
14. Migrate each use case to a single clear transaction owner whenever feasible.
15. Remove blocking adapters once no legacy callers remain and confirm no `block()`/JDBC remains on reactive paths.

## 26. End-to-End Example: Workflow Coordinating Two Resources

Suppose an application has:

- A legacy account store using JDBC.
- A new audit store using R2DBC.
- Each step has its own local transaction.
- If auditing fails, a job must retry or reconcile.

A simple orchestration:

~~~java
@Service
public class AccountWorkflowService {

    private final TransactionTemplate jdbcTransactionTemplate;
    private final LegacyAccountDao legacyDao;
    private final AuditRepository auditRepository;
    private final TransactionalOperator r2dbcTx;

    public AccountWorkflowService(
            TransactionTemplate jdbcTransactionTemplate,
            LegacyAccountDao legacyDao,
            AuditRepository auditRepository,
            TransactionalOperator r2dbcTx) {
        this.jdbcTransactionTemplate = jdbcTransactionTemplate;
        this.legacyDao = legacyDao;
        this.auditRepository = auditRepository;
        this.r2dbcTx = r2dbcTx;
    }

    public Mono<WorkflowResult> updateAccount(
            UpdateAccountCommand command) {

        return Mono.fromCallable(() ->
                        jdbcTransactionTemplate.execute(status ->
                                legacyDao.update(command)))
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(legacyResult ->
                        r2dbcTx.transactional(
                                auditRepository.save(
                                        AuditEntry.from(
                                                command,
                                                legacyResult)))
                        .map(audit ->
                                WorkflowResult.completed(
                                        legacyResult.id(),
                                        audit.getId())));
    }
}
~~~

This illustrates commit ordering: the JDBC transaction completes first, and only then does the R2DBC transaction execute. If the audit write fails, the account update is already committed.

For stronger consistency, replace the direct R2DBC audit write with an outbox write inside the same JDBC transaction as the account update. A relay publishes the event, and an R2DBC consumer writes the audit entry idempotently. Then the account update and outbox event are atomic in JDBC, and the audit record updates eventually when the event is processed.

~~~text
JDBC transaction
  UPDATE legacy_account
  INSERT outbox_event
  COMMIT
        |
        v
Outbox relay
        |
        v
Event
        |
        v
R2DBC transaction
  INSERT audit
  INSERT processed_event
  COMMIT
~~~

The consumer needs a unique key on the event ID to handle redelivery. If R2DBC writes the audit entry successfully but the acknowledgment is lost, the event may be redelivered; the unique constraint/deduplication protects against duplicates.

## 27. Design Principles to Remember

- `DataSource`/JDBC and `ConnectionFactory`/R2DBC are two distinct resources.
- JDBC `Connection` and R2DBC `Connection` cannot be swapped or shared.
- JDBC transactions are typically thread-bound; R2DBC transactions flow through Reactor Context.
- `PlatformTransactionManager` manages JDBC; `ReactiveTransactionManager` manages R2DBC.
- Match `DataSourceTransactionManager`/`JdbcTransactionManager` and `R2dbcTransactionManager` to their proper resources.
- Name transaction managers and specify qualifiers explicitly when multiple exist.
- `TransactionTemplate` is for imperative transactions; `TransactionalOperator` is for reactive publishers.
- Never run blocking JDBC on the WebFlux event loop; isolate it on an appropriate scheduler during transition.
- Wrap all JDBC work within the same transaction callback/thread.
- A Java workflow calling both stacks does not make two transactions atomic.
- Once one transaction commits, failure in the other does not roll back the earlier commit.
- `REQUIRES_NEW`, isolation, and savepoints apply only within their respective resource manager.
- Do not rely on `ChainedTransactionManager` as a distributed two-phase commit.
- XA is feasible only when all resources support enlistment and a transaction coordinator exists; the standard R2DBC SPI does not offer universal XA.
- Use outbox, saga, idempotency, and reconciliation for cross-resource consistency.
- Flyway/Liquibase can use a JDBC `DataSource` inside an R2DBC runtime application.
- Budget combined HikariCP and `r2dbc-pool` connections across all replicas.
- Test rollback and partial commits against the target database engine and driver.
- Migrate each use case to a single clear transaction owner to reduce complexity.
