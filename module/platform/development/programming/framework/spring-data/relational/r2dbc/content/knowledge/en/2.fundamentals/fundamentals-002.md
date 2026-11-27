# Transactions, Isolation Levels, and Concurrent Access in Relational Databases

In applications using Spring Data Relational R2DBC, multiple write operations often need to be executed as a single unit: creating an order and deducting inventory, debiting and crediting accounts during a money transfer, or updating data alongside its processing status. If one step succeeds while the next step fails, data can end up in an inconsistent state. At the same time, multiple requests may read and modify the same record concurrently.

A transaction defines the boundary within which SQL statements are processed together. The isolation level governs how much of concurrent changes a transaction can observe. Concurrency control mechanisms help protect business rules when multiple transactions operate on data simultaneously.

With R2DBC, these database concepts remain the same, but the way Spring manages transactions is tied to the reactive stream and Reactor Context rather than relying primarily on `ThreadLocal` as in traditional imperative approaches.

## 1. Why Are Transactions Needed?

Consider transferring 500,000 VND from account A to account B. From a business perspective, the operation consists of two statements:

1. Deduct 500,000 VND from account A's balance.
2. Add 500,000 VND to account B's balance.

If the first statement succeeds but the second fails, money is deducted from A without being credited to B. A transaction allows the database to either commit both changes or roll back both changes.

A relational transaction is typically described by four ACID properties:

| Property | Meaning | Example |
|---|---|---|
| Atomicity | Changes within a transaction either all succeed or all get aborted | Never let a transfer debit one account without crediting the other |
| Consistency | A transaction moves data from one valid state to another valid state according to defined constraints | A balance cannot become negative if that is a system rule |
| Isolation | Concurrent transactions must not observe each other in ways that violate the chosen isolation level | One transaction does not read uncommitted data from another transaction |
| Durability | After a successful commit, data is persisted durably according to the DBMS's guarantees | Committed results remain intact after the application process restarts |

ACID does not automatically guarantee every business rule. The application must still design appropriate update statements, data constraints, and isolation levels. For example, a transaction can be completely atomic yet still allow two requests to order the last item in stock if the inventory check and deduction statements are designed unsafely.

## 2. The Transaction Model in Spring Data R2DBC

R2DBC is a reactive API for accessing relational databases. Applications typically work with `ConnectionFactory`, reactive repositories, `DatabaseClient`, or `R2dbcEntityTemplate`. Spring manages transactions through a `ReactiveTransactionManager`, usually `R2dbcTransactionManager`.

When a transaction begins, the transaction manager acquires a connection from `ConnectionFactory`, starts a transaction on that connection, and attaches the transaction resource to the Reactor Context. R2DBC operations within the same reactive stream using the matching `ConnectionFactory` participate in the active transaction. When the publisher completes successfully, Spring commits; when the publisher terminates with an error, Spring rolls back according to rollback rules.

The key point is that a reactive transaction is bound to the subscription and Reactor Context, not pinned to a single thread. Operators such as `publishOn` can switch execution across threads while still propagating Reactor Context via Reactor's mechanism. However, creating an independent subscription with `subscribe()` starts a separate execution flow and does not automatically participate in the caller's transaction.

### 2.1. Configuring the Transaction Manager

If the application needs to declare a transaction manager explicitly, a bean can be created as follows:

~~~java
@Configuration
class R2dbcTransactionConfiguration {

    @Bean
    R2dbcTransactionManager transactionManager(
            ConnectionFactory connectionFactory) {
        return new R2dbcTransactionManager(connectionFactory);
    }
}
~~~

In a Spring Boot application, auto-configuration may already provide an appropriate transaction manager. Before declaring an extra bean, check the actual configuration to avoid creating multiple unnecessary transaction managers.

An `R2dbcTransactionManager` manages transactions for one `ConnectionFactory`. Repositories and `DatabaseClient` instances that need to join the same transaction must use the corresponding connection factory. If an operation uses a different connection factory or opens a connection outside the transaction manager, that operation may run outside the current transaction.

### 2.2. Keeping All Operations in the Same Reactive Chain

A business method should return a publisher containing all operations that belong to the transaction:

~~~java
@Transactional
public Mono<Void> processOrder(Long orderId) {
    return orderRepository.markAsProcessing(orderId)
            .then(inventoryRepository.decreaseForOrder(orderId))
            .then(orderRepository.markAsCompleted(orderId));
}
~~~

The snippet above only illustrates the transaction boundary; the repository methods must return publishers and use the same R2DBC configuration. Spring can manage the transaction because the publisher is returned to the `@Transactional` interceptor.

Do not call `subscribe()` inside a business method to run an operation that needs to be part of the transaction:

~~~java
@Transactional
public Mono<Void> processOrder(Long orderId) {
    inventoryRepository.decreaseForOrder(orderId).subscribe();
    return orderRepository.markAsCompleted(orderId);
}
~~~

In this incorrect example, the inventory deduction creates a separate subscription. The method may complete and the transaction may commit before the inventory deduction finishes; that operation is also not guaranteed to use the current transaction's connection. Chain publishers using `then`, `flatMap`, `concatMap`, or another appropriate operator and return the entire chain to Spring.

Similarly, do not use `block()` inside a reactive flow to wait for an R2DBC operation. Blocking a thread defeats non-blocking benefits and can cause deadlocks or thread starvation in a reactive environment.

### 2.3. Avoiding Concurrent Statements on the Same Connection

`Mono.zip` or `Mono.when` can start multiple publishers concurrently. Within an R2DBC transaction, these publishers may share the same connection. Not every driver or connection supports multiple SQL statements running concurrently on the same connection.

If statements need to execute sequentially, use `then` or `concatMap`. Run them concurrently only when you have verified that the driver, connection, and transaction semantics support that execution model. The fact that publishers share a Reactor Context does not mean the database will safely execute statements in parallel on the same connection.

## 3. Transaction Boundaries and Rollback

### 3.1. Using `@Transactional`

Spring supports reactive transactions for methods returning reactive types such as `Mono` or `Flux` when the application uses a `ReactiveTransactionManager`. The annotation can be placed on a method or service class:

~~~java
@Transactional
public Mono<Order> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Order not found")))
            .flatMap(order -> {
                order.setStatus(OrderStatus.CONFIRMED);
                return orderRepository.save(order);
            });
}
~~~

Several conditions to remember:

- The call must pass through the Spring proxy for the transaction interceptor to be applied. Calling another `@Transactional` method within the same instance (self-invocation) typically bypasses the proxy and does not establish the expected transaction boundary.
- The method must return a reactive publisher for Spring to manage a reactive transaction. Do not mix an imperative transaction manager with a reactive R2DBC chain.
- Operations belonging to the same transaction must reside within the returned publisher or be invoked within the corresponding reactive transaction context.
- When multiple transaction managers exist, specify the manager via the `transactionManager` or `value` attribute of `@Transactional`.

### 3.2. Rollback on Error

With Spring's default configuration, runtime exceptions typically trigger transaction rollback; checked exceptions do not trigger rollback by default in all cases. Rules can be declared explicitly via `rollbackFor` or `noRollbackFor` when required by business logic.

In a reactive flow, the error signal must reach the transaction boundary for Spring to detect it and roll back. Where an error-handling operator is placed can change the outcome:

~~~java
// Error leaves the transaction operator before being handled:
return performWrites()
        .as(transactionalOperator::transactional)
        .onErrorResume(error -> returnFallbackResult());
~~~

~~~java
// Error has been converted into a successful result inside the transaction:
return performWrites()
        .onErrorResume(error -> returnFallbackResult())
        .as(transactionalOperator::transactional);
~~~

In the second example, if `onErrorResume` replaces the error with a normally completing publisher, the transaction manager may see the transaction finish successfully and commit prior changes. If business logic requires a rollback, let the error propagate across the transaction boundary or explicitly mark it rollback-only using the appropriate transaction API.

### 3.3. Transactions with `Flux`

When a `@Transactional` method returns a `Flux`, the transaction typically remains active for the entire duration of the subscription processing the publisher. If downstream consumes data slowly, the transaction and connection may be held open for a long time. This increases lock hold times, reduces available connections in the pool, and impacts other requests.

Do not keep a database transaction open across an infinite stream or while waiting on user input, slow HTTP service calls, or unrelated work. For large data processing, consider splitting work into batches with clear transaction boundaries if business rules allow.

### 3.4. Propagation, Timeout, and Read-Only

Spring provides commonly used transaction attributes:

| Attribute | Purpose |
|---|---|
| `propagation` | Defines behavior when a method is called while a transaction already exists. `REQUIRED` is the default: join the current transaction or create a new one |
| `isolation` | Selects the isolation level for a new transaction |
| `timeout` | Limits transaction duration according to transaction manager and driver support |
| `readOnly` | Provides a read-only transaction hint; whether the database enforces write restrictions depends on the platform |
| `rollbackFor` / `noRollbackFor` | Customizes which exception types trigger or do not trigger rollback |

`REQUIRES_NEW` requests a new transaction according to the transaction manager's capabilities. Savepoint or `NESTED` support depends on the transaction manager, driver, and database. Do not assume all propagation modes behave identically across every database system.

An isolation level declared on a method typically takes effect only when the method actually starts a new transaction. If the method joins an existing transaction, an isolation setting on the inner call does not automatically alter the isolation level of the outer transaction.

## 4. Phenomena Under Concurrent Transactions

To choose the right isolation level, you need to understand the anomalies transactions can observe.

### 4.1. Dirty Read — Reading Uncommitted Data

Transaction A updates a balance from 1,000,000 to 500,000 without committing yet. Transaction B reads the balance as 500,000. Afterward, A rolls back. B has used a value that never became committed data.

Dirty reads can cause an application to make decisions based on temporary data from another transaction.

### 4.2. Non-Repeatable Read — Re-Reading the Same Row Yields a Different Value

Transaction A reads an account balance as 1,000,000. Transaction B updates the balance to 800,000 and commits. When A reads the same row again, A receives 800,000.

Two reads of the same row within one transaction return different results because another transaction committed a change in between.

### 4.3. Phantom Read — The Set of Matching Rows Changes

Transaction A queries all orders with status `PENDING` and receives 5 rows. Transaction B inserts a new order with status `PENDING` and commits. When A runs the same condition again, the result may contain 6 rows.

Unlike non-repeatable reads, phantom reads involve the set of rows satisfying a query condition; new rows can appear or existing rows can stop matching the condition.

### 4.4. Lost Update — One Transaction's Update Is Overwritten

Suppose an initial balance is 100:

1. A reads balance 100.
2. B also reads balance 100.
3. A computes `100 + 20` and writes 120.
4. B computes `100 - 10` and writes 90.

The final result is 90; A's addition of 20 has been overwritten. Both transactions may have committed successfully, yet the business result is wrong.

Lost updates commonly arise when an application reads a value, computes in the application layer, and writes back the entire modified value. Suitable fixes are usually atomic SQL updates, optimistic locking, or row locking; simply raising the isolation level without understanding database behavior does not necessarily solve the problem properly.

### 4.5. Write Skew — Transactions Preserve Individual Conditions Yet Break a Shared Rule

Suppose an on-call shift must always have at least one doctor on duty. A and B both read that two doctors are currently on duty. A takes the first doctor off shift; B takes the second doctor off shift. Each transaction updates a different row, so they may not conflict directly. If both commit, nobody remains on duty.

This is a classic example of write skew in systems using snapshot isolation. Protecting multi-row rules may require `SERIALIZABLE`, locking a representative row for the rule, or redesigning data and constraints so the database can enforce the invariant.

## 5. Common Isolation Levels

SQL defines four standard isolation levels. Higher levels generally reduce observable anomalies but can lower concurrency, increase lock wait times, or cause transactions to be retried.

| Isolation Level | Dirty Read | Non-Repeatable Read | Phantom Read per SQL Standard |
|---|---|---|---|
| `READ_UNCOMMITTED` | May occur | May occur | May occur |
| `READ_COMMITTED` | No | May occur | May occur |
| `REPEATABLE_READ` | No | No | May occur |
| `SERIALIZABLE` | No | No | No |

This describes the SQL model. How each database system implements isolation may be stronger or differ in details. In particular, snapshot isolation is not completely synonymous with `SERIALIZABLE`: write skew can still occur in some systems.

### 5.1. `READ_UNCOMMITTED`

This level allows a transaction to read data not yet committed by other transactions. It offers low isolation and is generally unsuitable for business logic that requires reliable data.

Some database systems do not actually implement dirty reads. For example, PostgreSQL treats a `READ UNCOMMITTED` request as `READ COMMITTED`. Therefore, the isolation level name in configuration is not enough to infer runtime behavior; consult the documentation of the database you are running.

### 5.2. `READ_COMMITTED`

A statement reads only data committed as of when that statement begins. This level prevents dirty reads, but two statements in the same transaction can still see different committed states.

This is PostgreSQL's default choice. It is often appropriate for typical CRUD operations, though applications still need to guard against lost updates and multi-row business rules using atomic statements, locks, or versions.

### 5.3. `REPEATABLE_READ`

This level guarantees repeatable reads of the same row within a transaction as defined by the database system. Under the SQL anomaly table, phantom reads can still occur.

Databases implement this level differently. PostgreSQL uses a stable snapshot for `REPEATABLE READ` transactions and prevents phantom reads under its implementation. MySQL's InnoDB commonly uses `REPEATABLE READ` by default and combines consistent reads with locking/gap locks for certain query types. Do not generalize one database's behavior to another database.

### 5.4. `SERIALIZABLE`

This is the strongest of the four standard levels. The outcome of committed transactions must be equivalent to some serial execution order.

To achieve this, the database may lock more aggressively or detect conflicts and abort a transaction at commit. Consequently, the application must be ready to handle serialization failures and retry the entire transaction when appropriate. `SERIALIZABLE` is useful for invariants hard to protect with a single simple update statement, but should not be turned on everywhere without load testing and checking retry rates.

### 5.5. Do Not Guess Defaults from Isolation Level Names

Defaults depend on the database system, server configuration, connection session, and version. PostgreSQL typically defaults to `READ COMMITTED`; MySQL InnoDB typically defaults to `REPEATABLE READ`. Configuration can override these values. Verify the actual database in your deployment environment and re-check after switching drivers or database engines.

## 6. Configuring Isolation Levels in Spring

### 6.1. Using `@Transactional`

An isolation level can be selected directly on a business method:

~~~java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;

@Transactional(isolation = Isolation.REPEATABLE_READ)
public Mono<MonthlyReport> buildMonthlyReport() {
    return loadReportData();
}
~~~

The `Isolation` enum values correspond to the familiar SQL levels: `READ_UNCOMMITTED`, `READ_COMMITTED`, `REPEATABLE_READ`, and `SERIALIZABLE`.

The annotation is only a request sent to the transaction manager. The database and R2DBC driver must support the requested level. Verify real behavior on the database in use, especially when deploying across multiple database types or testing against a different database than production.

### 6.2. Using `TransactionalOperator`

When you need to create a transaction boundary directly within a reactive pipeline, you can use `TransactionalOperator`:

~~~java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();
definition.setIsolationLevel(
        TransactionDefinition.ISOLATION_SERIALIZABLE);
definition.setTimeout(5);

TransactionalOperator operator =
        TransactionalOperator.create(transactionManager, definition);

return performBusinessOperation()
        .as(operator::transactional);
~~~

Here `transactionManager` is a `ReactiveTransactionManager`, such as `R2dbcTransactionManager`. `performBusinessOperation()` returns a `Mono` or `Flux`; the operator wraps that publisher in a transaction boundary.

`TransactionalOperator` is helpful when only a section of a method needs a transaction, when configuring transaction settings while building the pipeline, or when avoiding annotation proxies. All operations requiring the transaction must still reside inside the wrapped publisher.

### 6.3. Isolation of an Existing Transaction

Suppose method A starts a `READ_COMMITTED` transaction and calls method B declared with `SERIALIZABLE`. If B joins the current transaction under `REQUIRED` propagation, the transaction does not automatically change to `SERIALIZABLE`. The isolation level is typically decided when the physical transaction begins.

If a piece of work truly needs its own transaction, consider a propagation mode that creates a new transaction and understand its cost. Do not use `REQUIRES_NEW` merely to force an isolation level if splitting commits breaks overall business atomicity.

## 7. Ways to Protect Data Under Concurrent Access

Isolation levels are only part of the solution. Applications typically combine several of the mechanisms below.

### 7.1. Using Atomic SQL Update Statements

Instead of reading a balance into the application, subtracting an amount in Java, and writing the new value back, let the database perform the calculation against the current value:

~~~sql
UPDATE bank_account
SET balance = balance - :amount
WHERE id = :accountId
  AND balance >= :amount;
~~~

The `balance >= :amount` condition is evaluated alongside the update statement. If two requests debit concurrently, the database coordinates competing updates on that row; the subsequent statement evaluates the condition against the state dictated by the database's execution rules. If the affected row count is `0`, the account either does not exist or lacks sufficient balance.

This approach is usually simpler and more effective than an application-level read-modify-write cycle. A `CHECK (balance >= 0)` constraint can be added in the database to protect the balance invariant even if another write path exists in the application.

### 7.2. Using Optimistic Locking with `@Version`

Optimistic locking fits scenarios where conflicts are infrequent. Each row has a version column. When reading, the application fetches both the data and the version; when updating, the statement succeeds only if the version in the database still equals the version that was read.

Example Spring Data Relational entity:

~~~java
@Table("inventory")
public class Inventory {

    @Id
    private Long id;

    private Integer quantity;

    @Version
    private Long version;

    // Constructors, getters, and setters
}
~~~

When saving an entity with `@Version`, Spring Data R2DBC uses the version to detect whether the record has changed since it was read. If another transaction updated it first, the save operation can throw `OptimisticLockingFailureException` instead of silently overwriting newer data.

Optimistic locking works well for edit screens, profiles, settings, or data with low conflict rates. The application must decide how to handle conflicts: reload data, ask the user to confirm, merge changes, or retry an operation that can safely be recomputed.

With custom SQL statements via `@Query`, do not assume Spring automatically appends a version condition as it does when saving a managed entity. If using a custom update, include the version in the condition and increment the version in the statement yourself:

~~~sql
UPDATE inventory
SET quantity = :newQuantity,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

If the affected row count is `0`, either the version changed or the record no longer exists.

### 7.3. Using Pessimistic Locking with `SELECT ... FOR UPDATE`

Pessimistic locking locks the target rows so other transactions must wait or fail when attempting to acquire a conflicting lock. Example:

~~~sql
SELECT id, balance
FROM bank_account
WHERE id = :accountId
FOR UPDATE;
~~~

This statement usually must run inside a transaction. The lock is held until the transaction commits or rolls back. Exact syntax, options like `NOWAIT` or `SKIP LOCKED`, and what gets locked depend on the database.

Pessimistic locking is useful when data faces high contention or business rules require serializing operations on specific rows. On the flip side, other transactions may have to wait; the longer a transaction holds locks, the greater the risk of bottlenecks and deadlocks.

If a business operation locks multiple rows, acquire locks in the same consistent order, such as ascending by ID. This reduces the risk of two transactions locking rows in opposite orders.

### 7.4. Using Database Constraints

Rules expressible as constraints should be enforced in the database:

- `PRIMARY KEY` ensures unique identification.
- `UNIQUE` prevents duplicate values or combinations of values.
- `FOREIGN KEY` ensures valid referential relationships.
- `CHECK` enforces conditions on row values, such as non-negative quantities.
- `NOT NULL` prevents missing data in required columns.

Java-layer validation helps fail fast with clear error messages, but it does not replace constraints. Two requests can both pass an application check simultaneously; constraints serve as the final guard when both attempt to write.

### 7.5. Choosing `SERIALIZABLE` for Multi-Row Invariants

When business rules depend on a dataset or multiple rows where locking and atomic updates are not straightforward enough, `SERIALIZABLE` can be an appropriate choice. The database ensures committed transactions produce an outcome equivalent to a serial order.

The application must handle cases where the database rejects a transaction due to serialization conflicts. Retry the entire business operation in a new transaction, not just the final statement.

## 8. Example: Money Transfer with Spring Data R2DBC

The example below illustrates combining a transaction boundary with atomic updates. Assume the `bank_account` table has columns `id` and `balance`.

The repository declares the update statements:

~~~java
public interface AccountRepository
        extends ReactiveCrudRepository<Account, Long> {

    @Modifying
    @Query("""
        UPDATE bank_account
        SET balance = balance - :amount
        WHERE id = :id
          AND balance >= :amount
        """)
    Mono<Integer> debit(
            @Param("id") Long id,
            @Param("amount") BigDecimal amount);

    @Modifying
    @Query("""
        UPDATE bank_account
        SET balance = balance + :amount
        WHERE id = :id
        """)
    Mono<Integer> credit(
            @Param("id") Long id,
            @Param("amount") BigDecimal amount);
}
~~~

The service executes both updates inside the same transaction:

~~~java
@Service
public class TransferService {

    private final AccountRepository accounts;

    public TransferService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public Mono<Void> transfer(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        if (amount == null || amount.signum() <= 0) {
            return Mono.error(
                    new IllegalArgumentException(
                            "Amount must be greater than 0"));
        }

        if (fromId.equals(toId)) {
            return Mono.error(
                    new IllegalArgumentException(
                            "Source and destination accounts must be different"));
        }

        return requireOne(
                    accounts.debit(fromId, amount),
                    "Cannot debit: account does not exist or has insufficient balance")
                .then(requireOne(
                    accounts.credit(toId, amount),
                    "Cannot credit: destination account does not exist"));
    }

    private Mono<Void> requireOne(
            Mono<Integer> update,
            String errorMessage) {
        return update.flatMap(rows -> {
            if (rows == 1) {
                return Mono.<Void>empty();
            }
            return Mono.error(
                    new IllegalStateException(errorMessage));
        });
    }
}
~~~

Key characteristics of this flow:

1. The debit statement checks the balance and updates it in a single SQL operation.
2. Only when debit affects exactly one row does the publisher execute the credit statement.
3. If the destination account does not exist, the method emits an error. The error propagates out of the `@Transactional` method, so the debit change is rolled back with the transaction.
4. The publisher is returned to Spring, allowing the transaction interceptor to manage the entire reactive chain.

This is an illustrative example; production systems need account ownership authorization, transaction limit checks, currency handling, history recording, and error handling according to product requirements. With concurrent opposing transfers, the database may still detect deadlocks depending on lock order. You can lock both accounts in a fixed ID order before updating, or apply bounded retries for deadlock errors.

## 9. Deadlocks and Retries

A deadlock occurs when transactions wait on each other's locks. For example:

- Transaction A locks account row 10 and then waits for account row 20.
- Transaction B locks account row 20 and then waits for account row 10.

Neither transaction can proceed. The database typically detects the deadlock and aborts one transaction to unblock the system. The application should treat this as a recoverable error in some situations, though it should not retry every exception type.

Ways to reduce deadlocks:

- Acquire locks in the same order across all business flows.
- Keep transactions short; do not make HTTP calls, send emails, or wait for user actions while holding locks.
- Create appropriate indexes so statements locate rows quickly and lock fewer rows.
- Update only the necessary data scope.
- Retry only identified transient errors such as deadlocks or serialization failures, with a bounded retry count and backoff.

Example placing retry outside the transaction boundary so each attempt starts a new transaction:

~~~java
Mono.defer(() -> performTransfer()
        .as(transactionalOperator::transactional))
    .retryWhen(Retry.backoff(3, Duration.ofMillis(100))
        .filter(this::isRetryableConcurrencyFailure));
~~~

`performTransfer()` must recreate the work upon subscription. The filter should accept only retryable failures; invalid input, missing accounts, or business rule violations should not be retried.

Retries can re-execute the entire transaction body. Therefore, do not place non-rollbackable external side effects (such as sending an email or calling a payment gateway) inside a transaction expecting a database rollback to undo them. For side effects that must be emitted after commit, consider the transactional outbox pattern: write the event to an outbox table in the same transaction, then have a separate process publish events safely with idempotent handling.

For APIs that clients may resend after a network timeout, consider an idempotency key or unique transaction reference. A committed database transaction whose response was lost can prompt a client retry; idempotency prevents executing the business operation twice.

## 10. Performance and Operations

Higher isolation can increase lock contention, aborted transactions, and retries. Choose the lowest level that still protects business invariants, then measure on a database and workload close to production.

Metrics to monitor:

- Transaction duration and connection hold time.
- Active connections, pool wait counts, and connection acquisition errors.
- Lock waits, deadlocks, serialization failures, and optimistic locking failures.
- Retry rate, average retry attempts, and final business failure rate.
- Slow queries or missing indexes that cause transactions to hold locks longer.

Do not keep a transaction open while performing non-database work. Read the needed data, process outside the transaction if safe, then open a short transaction to verify and write the required changes. If you must ensure data has not changed since reading, combine versions, conditional updates, or appropriate locks.

When using a connection pool, the transaction manager manages connections borrowed for transactions and returns them when the transaction ends. Long transactions can occupy connections and force other requests to wait even when the database still has capacity. Set sensible timeouts and size the pool to real load; increasing pool size is no substitute for shortening transactions and optimizing queries.

## 11. Testing Transactions and Concurrency

Unit tests with mock repositories can verify publisher invocation order, but they cannot prove isolation levels, row locks, deadlocks, or how the driver executes transactions. Those behaviors require integration tests against a real database or an environment compatible with production.

A useful test suite should cover:

1. **Rollback:** make the second step fail and verify changes from the first step are no longer in the database.
2. **Atomic update:** send multiple concurrent inventory or balance deduction requests and verify data does not violate limits.
3. **Optimistic locking:** have two streams read the same version; only one update is accepted while the other receives a conflict error.
4. **Isolation:** coordinate two transactions to check for dirty reads, non-repeatable reads, or phantom reads under the active isolation level.
5. **Deadlocks and retries:** verify errors are recognized properly and retries run in a new transaction.
6. **Subscription cancellation or timeout:** verify connections and transactions are released according to transaction manager and driver behavior.

You can use Testcontainers to run the exact target database engine in integration tests. If production uses PostgreSQL, concurrency testing on H2 is insufficient to draw conclusions about PostgreSQL's locking and isolation behavior. Use `StepVerifier` to assert publisher results, and also query the database afterward to verify the final state.

When writing concurrency tests, coordinate read and write timing with latches, barriers, or proper synchronization primitives. Simply launching two publishers close together does not guarantee the test reproduced the intended interleaving.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Calling `subscribe()` inside a `@Transactional` method | Creates an independent subscription; operation may run outside the transaction | Chain publishers and return the reactive chain |
| Using `block()` in an R2DBC stream | Blocks threads, risking bottlenecks or deadlocks | Keep processing non-blocking with `flatMap`, `then`, `zip` as appropriate |
| Using a different transaction manager or `ConnectionFactory` | Some statements fail to join the same transaction | Align connection factory and transaction manager configuration |
| Catching an error and turning it into success inside a transaction | Transaction may commit even though a business step failed | Place recovery outside the transaction boundary or mark rollback-only |
| Internally calling a `@Transactional` method via `this` | Spring proxy may not apply the annotation | Put transaction boundaries on methods called via bean proxy or use `TransactionalOperator` |
| Running multiple SQL statements concurrently on one connection | Driver may reject or not support concurrent execution | Serialize operations if the driver does not support it |
| Using high isolation across the entire application | Increases lock waits and unnecessary retries | Choose levels based on business invariants and load testing |
| Validating data only in Java | Two requests can pass validation concurrently before writing | Use atomic SQL and database constraints |
| Retrying all exceptions | Repeats non-recoverable errors or external side effects | Retry only identified transient errors; ensure operations are idempotent |
| Testing on a different database than production | Misses differences in isolation, locking, and SQL | Run integration tests on the target database engine |

## 13. Process for Choosing a Transaction Strategy

When designing a write operation, you can follow this sequence:

1. Identify the business invariants: non-negative balance, non-negative stock, unique order code, or at least one person on shift.
2. Identify the rows and tables the operation reads or writes; distinguish single-row rules from multi-row rules.
3. Use constraints and atomic update statements if the rule can be expressed directly in the database.
4. Use optimistic locking when contention is low and version changes can be handled.
5. Use pessimistic locking when operations on specific rows must be serialized and transactions can stay short.
6. Consider `SERIALIZABLE` when invariants span multiple rows or result sets and no simpler protection exists.
7. Verify database/driver behavior, measure lock hold times, and add bounded retries if the database can abort transactions on conflict.
8. Test rollbacks and race conditions against the exact database engine used in deployment.

## 14. Key Takeaways

- Transactions define the commit or rollback boundary for a group of operations.
- Isolation levels determine how concurrent transactions observe each other's data; actual behavior also depends on the database.
- In R2DBC, Spring manages reactive transactions through `ReactiveTransactionManager` and Reactor Context.
- All operations needing the same transaction must belong to the returned reactive chain; avoid `subscribe()` and `block()` inside business flows.
- `READ_COMMITTED` is often sufficient for typical CRUD, but lost updates and business invariants still require atomic SQL, constraints, versions, or locks.
- `@Version`, `SELECT ... FOR UPDATE`, and `SERIALIZABLE` address different forms of conflict; choose based on data characteristics and workload.
- Short transactions, consistent lock ordering, bounded retries, and integration tests on a real database help systems handle concurrency reliably.
