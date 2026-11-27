# Propagation, Isolation Levels, and Driver Limitations

A transaction groups multiple database operations into a single unit of work with commit or rollback rules. In Spring Data Relational R2DBC, transactions must also follow the reactive model: the connection is attached to the reactive execution context, operations must remain in the same publisher chain, and subscription termination determines when the transaction completes.

Two key configuration groups are **propagation** and **isolation**. Propagation determines whether a method joins an existing transaction, starts a new transaction, suspends the current transaction, or requires a specific transactional state. Isolation determines how visible other transactions' changes are and which read/write anomalies the database must prevent.

These settings do not operate independently of the database. Spring can request an isolation level or savepoint operation, but the driver and database engine must support it. Some features are only partially supported, have differing semantics, or are rejected at runtime.

This lesson covers propagation in Spring reactive transactions, isolation levels, configuration via `@Transactional` and `TransactionalOperator`, the role of Reactor Context, driver/database limitations, and testing transactions in R2DBC applications.

## 1. Transactions in R2DBC applications

A transaction usually includes one or more SQL statements. When all operations succeed, the transaction commits. If an operation fails or business logic decides to abort, the transaction rolls back.

For example, creating an order needs to save both the order and its line items:

~~~text
BEGIN
  |
  +-- INSERT purchase_order
  |
  +-- INSERT purchase_order_item
  |
  +-- UPDATE inventory
  |
  +-- all succeeded?
          |
          +-- Yes --> COMMIT
          |
          +-- No --> ROLLBACK
~~~

If the order is saved while the inventory update fails, the transaction prevents the database from persisting a partial state of the use case.

In Spring Data R2DBC, the transaction manager is usually `R2dbcTransactionManager`. It manages an R2DBC `Connection` acquired from `ConnectionFactory` and binds that connection into the reactive context so database operations share the transaction.

General flow:

~~~text
Service method returns Mono/Flux
        |
        v
Reactive transaction interceptor
        |
        v
R2dbcTransactionManager
        |
        v
ConnectionFactory / Connection
        |
        v
Reactor Context holds transaction resource
        |
        v
Repository / DatabaseClient uses that connection
        |
        v
COMMIT or ROLLBACK
~~~

A reactive transaction is not managed by pinning a fixed thread. Operators may run on different threads; the transaction context propagates through Reactor Context.

## 2. What is propagation?

Propagation defines how a transactional method behaves when invoked inside a workflow that already has an active transaction.

For example, Service A calls Service B:

~~~text
Service A
  |
  +-- start transaction?
  |
  +-- call Service B
          |
          +-- join A's transaction?
          +-- create independent transaction?
          +-- suspend A's transaction?
          +-- require an existing transaction?
~~~

Propagation does not dictate isolation level. A method can use `REQUIRED` with `READ_COMMITTED`, or `REQUIRES_NEW` with `SERIALIZABLE`, depending on configuration and database capabilities.

Spring defines these common propagation behaviors:

| Propagation | When a transaction already exists | When no transaction exists |
|---|---|---|
| `REQUIRED` | Joins the current transaction | Creates a new transaction |
| `REQUIRES_NEW` | Suspends the current transaction and creates a new transaction | Creates a new transaction |
| `SUPPORTS` | Joins the current transaction | Runs without a transaction |
| `MANDATORY` | Joins the current transaction | Throws an error because no transaction exists |
| `NOT_SUPPORTED` | Suspends the current transaction and runs non-transactionally | Runs without a transaction |
| `NEVER` | Throws an error because a transaction already exists | Runs without a transaction |
| `NESTED` | Creates a nested scope using a savepoint if supported | Starts a new transaction |

Distinguish `REQUIRES_NEW` from `NESTED`: a new transaction can commit independently of the outer transaction; a nested transaction uses a savepoint inside the existing transaction and cannot commit independently of the parent transaction.

## 3. REQUIRED: join or create a transaction

`REQUIRED` is the default propagation of `@Transactional`.

- If the caller already has a transaction, the method joins that transaction.
- If no transaction exists, the method begins a new transaction.
- If a participating method emits an error causing rollback, the entire shared unit of work can be rolled back.

Example:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;
    private final InventoryService inventoryService;

    @Transactional
    public Mono<Order> placeOrder(Order order) {
        return orderRepository.save(order)
                .flatMap(saved ->
                        inventoryService.reserve(saved)
                                .thenReturn(saved));
    }
}
~~~

If `inventoryService.reserve(...)` also runs inside a `REQUIRED` transaction managed by the same transaction manager, saving the order and reserving inventory share the same transaction.

`REQUIRED` fits when steps form one business unit: either all succeed together or all roll back together.

### 3.1. A participating transaction can become rollback-only

Suppose Service A opens a transaction and calls Service B. Service B joins the current transaction and marks it rollback-only or emits an error causing rollback. Service A cannot force that transaction to commit merely by catching the error on the outside.

In some cases, Spring may throw `UnexpectedRollbackException` when the outer scope tries to commit a transaction already marked rollback-only. Therefore, do not assume catching an exception in the caller always recovers the transaction.

If a secondary step's failure can be ignored, determine clearly whether the shared transaction remains valid. If that step must be independent, consider `REQUIRES_NEW` or redesigning the use-case boundaries.

## 4. REQUIRES_NEW: independent transaction

`REQUIRES_NEW` requests an independent transaction. If an outer transaction is active, Spring suspends it and starts a new transaction for the invoked method.

Example of recording an audit entry that must survive even if the main use case rolls back:

~~~java
@Service
public class AuditService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public Mono<AuditRecord> recordAttempt(AuditRecord record) {
        return auditRepository.save(record);
    }
}
~~~

Suppose the call flow is:

~~~text
Transaction A: place order
    |
    +-- call AuditService
            |
            +-- suspend A
            |
            +-- Transaction B: save audit
            |
            +-- COMMIT B
    |
    +-- order placement step fails
    |
    +-- ROLLBACK A
~~~

The audit record in B can persist even though A rolls back, because B is an independent transaction.

### 4.1. REQUIRES_NEW has connection costs

Transaction A may already hold a connection. When B starts, the pool typically needs to supply another connection. If the pool is too small and many requests hold outer transactions while waiting for inner transactions, the system can exhaust connections or stall waiting for connection acquisition.

For instance, suppose a pool's maximum connections equals the number of in-flight requests; each request holds one connection for its outer transaction and then requests another connection for `REQUIRES_NEW`. No free connections remain to grant to the inner transaction.

Therefore:

- Use `REQUIRES_NEW` purposefully for genuinely independent work.
- Size timeouts and pools appropriately for the workload.
- Avoid nesting multiple layers of `REQUIRES_NEW` unnecessarily.
- Load-test to detect pool starvation.
- Do not rely on the inner transaction reading uncommitted data from the outer transaction.

Transaction B normally cannot see A's uncommitted changes. If B needs values newly created in A, pass the required values via parameters and avoid designs that depend on B reading uncommitted data.

## 5. NESTED: using savepoints inside a transaction

`NESTED` represents a sub-scope inside the active transaction using a savepoint, if supported by the transaction manager and driver.

~~~text
BEGIN transaction A
  |
  +-- operation A1
  |
  +-- SAVEPOINT nested_B
  |      |
  |      +-- operation B1
  |      +-- operation B2 fails
  |      |
  |      +-- ROLLBACK TO SAVEPOINT nested_B
  |
  +-- operation A2
  |
  +-- COMMIT transaction A
~~~

Rolling back the nested scope can undo changes after the savepoint while keeping earlier changes in the parent transaction. However, the parent transaction still determines the final commit or rollback.

Example:

~~~java
@Transactional(propagation = Propagation.NESTED)
public Mono<Void> addOptionalDetails(Long orderId) {
    return detailRepository.save(buildDetails(orderId))
            .then();
}
~~~

This code works as a nested transaction only if the transaction manager/driver supports savepoints for this case. Otherwise, Spring may report that nested transactions are not supported.

### 5.1. How NESTED differs from REQUIRES_NEW

| Characteristic | `NESTED` | `REQUIRES_NEW` |
|---|---|---|
| Mechanism | Savepoint inside current transaction | Independent transaction |
| Commit | Commits only with parent transaction | Can commit independently |
| Rollback | Can roll back to savepoint | Rolls back the new transaction |
| Connection | Typically uses parent transaction's connection | Needs independent transaction/connection |
| Support needed | Requires savepoints | Requires suspending and creating new transactions |
| When parent rolls back | Nested changes also roll back | Committed inner transaction can persist |

Do not treat `NESTED` as a universal drop-in replacement for `REQUIRES_NEW`. They have different semantics.

## 6. Remaining propagation modes

### 6.1. SUPPORTS

`SUPPORTS` joins a transaction if the caller already has one. If not, the method runs without a transaction.

Use it when a read operation can benefit from an existing transaction but does not require opening one itself.

~~~java
@Transactional(propagation = Propagation.SUPPORTS)
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
~~~

Do not rely on `SUPPORTS` to guarantee multiple `SELECT` queries see the same snapshot if the caller has no transaction.

### 6.2. MANDATORY

`MANDATORY` requires the caller to provide a transaction. If no transaction is active, Spring throws an error.

~~~java
@Transactional(propagation = Propagation.MANDATORY)
public Mono<Void> updateBalance(Long accountId, BigDecimal amount) {
    return accountRepository.addBalance(accountId, amount);
}
~~~

It can guard an operation that must only be called inside a larger transactional use case, helping catch service calls made in the wrong context.

### 6.3. NOT_SUPPORTED

`NOT_SUPPORTED` requires running outside a transaction. If a transaction is active, Spring suspends it for the duration of the method execution.

Use when an operation should not participate in an open transaction, such as independent work not requiring shared atomicity. Remember, however, that database operations outside a transaction may execute under auto-commit or connection default semantics.

Do not use `NOT_SUPPORTED` to dodge transaction errors without understanding the data impact. If the operation needs clear commit/rollback, give it its own transaction.

### 6.4. NEVER

`NEVER` requires that no transaction exists. If the caller already has a transaction, the method fails.

~~~java
@Transactional(propagation = Propagation.NEVER)
public Mono<SystemStatus> loadExternalStatus() {
    return statusRepository.findCurrentStatus();
}
~~~

It is useful when a method must not run inside a transaction—for example, due to long-running work or non-rollbackable side effects. If the method still accesses an R2DBC database, define clearly the semantics of running without a transaction.

## 7. What is isolation?

Isolation describes the extent to which a transaction is affected by uncommitted or committed changes from other transactions. When many transactions run concurrently, the database must balance consistency, concurrency, and performance.

Commonly referenced read/write anomalies:

| Anomaly | Meaning |
|---|---|
| Dirty read | Reading data written by another transaction that has not yet committed |
| Non-repeatable read | Reading the same row twice within one transaction and observing different values |
| Phantom read | Re-running the same query predicate and seeing the set of matching rows change |
| Lost update | One update overwrites another transaction's change due to lack of coordination |
| Write skew | Transactions read the same state and then write disjoint rows, violating an overall invariant |

The first three anomalies are standard concepts used to describe isolation levels. Lost updates and write skew also depend on query patterns, locking, and database implementation; do not assume picking an isolation level alone solves every business race condition.

## 8. Common isolation levels

Spring defines isolation levels corresponding to transaction definitions:

| Isolation | Dirty read | Non-repeatable read | Phantom read | Characteristics |
|---|---|---|---|---|
| `READ_UNCOMMITTED` | Possible | Possible | Possible | Lowest level; many DBs map it to a higher level |
| `READ_COMMITTED` | Prevented | Possible | Possible | Each statement reads only committed data |
| `REPEATABLE_READ` | Prevented | Prevented per standard | Possible per standard | Re-reading the same row stays stable in the transaction; details depend on DB |
| `SERIALIZABLE` | Prevented | Prevented | Prevented per serializable semantics | Strongest level; may cause serialization errors requiring retries |
| `DEFAULT` | Per DB | Per DB | Per DB | Uses the database/connection default level |

This table describes semantics under the standard isolation model. MVCC, locking, and specific database implementations may be stronger or differ in detail from the general summary.

### 8.1. READ_UNCOMMITTED

Under the standard model, this level permits reading uncommitted data. That can create dirty reads: transaction A reads a value written by B, and then B rolls back.

Many database engines do not actually permit dirty reads. For example, PostgreSQL treats `READ_UNCOMMITTED` as `READ_COMMITTED`. Requesting this level therefore does not mean every database exhibits dirty-read behavior.

Do not choose the lowest level merely for performance if business logic depends on committed data.

### 8.2. READ_COMMITTED

`READ_COMMITTED` prevents dirty reads. A statement sees only committed data according to the database's semantics.

However, two `SELECT` statements within the same transaction can observe different states:

~~~text
Transaction A                    Transaction B
-------------                    -------------
SELECT balance = 100
                                 UPDATE balance = 80
                                 COMMIT
SELECT balance = 80
~~~

This is a non-repeatable read. With predicate queries, a new row can appear between two reads, producing a phantom under the standard model.

This is a common default in many databases, though you should verify your system's actual configuration.

### 8.3. REPEATABLE_READ

`REPEATABLE_READ` aims to ensure re-reading the same row inside a transaction does not observe values modified and committed by another transaction under the standard model. How phantoms are handled depends on the database.

For example, business logic sums account balances and checks a threshold. If rows change between two queries, the total can differ. Understand whether your database uses snapshot isolation, locking, or another variant.

In PostgreSQL, `REPEATABLE READ` uses snapshot transactions and prevents phantoms in the way commonly described; other DBs have different semantics and mechanisms. Do not deduce behavior from the isolation name alone without checking database documentation.

### 8.4. SERIALIZABLE

`SERIALIZABLE` requires the outcome of concurrent transactions to be equivalent to some serial execution order. This provides strong protection, yet does not guarantee every transaction succeeds.

The database may abort a transaction due to a serialization conflict. The application must be ready to retry the entire transaction upon receiving an appropriate serialization error.

Retries must be controlled:

- Cap the number of attempts.
- Use bounded backoff where appropriate.
- Retry only errors identified as transient/serialization conflicts.
- Ensure side effects outside the database are not executed repeatedly.
- Use idempotency keys or outbox for side effects that must be guaranteed.

Do not retry arbitrary SQL errors or business errors.

## 9. Selecting isolation with @Transactional

Propagation and isolation can be declared via annotations:

~~~java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {

    private final AccountRepository accountRepository;

    @Transactional(
            propagation = Propagation.REQUIRED,
            isolation = Isolation.READ_COMMITTED)
    public Mono<Account> deposit(Long accountId, BigDecimal amount) {
        return accountRepository.findById(accountId)
                .switchIfEmpty(Mono.error(
                        new AccountNotFoundException(accountId)))
                .flatMap(account -> {
                    account.setBalance(account.getBalance().add(amount));
                    return accountRepository.save(account);
                });
    }
}
~~~

With R2DBC, ensure the transaction manager is the appropriate reactive manager, typically `R2dbcTransactionManager` configured with the same `ConnectionFactory` used by the repository.

Example configuration:

~~~java
@Bean
R2dbcTransactionManager r2dbcTransactionManager(
        ConnectionFactory connectionFactory) {
    return new R2dbcTransactionManager(connectionFactory);
}
~~~

If the application has multiple transaction managers, specify the manager name in the annotation:

~~~java
@Transactional(
        transactionManager = "r2dbcTransactionManager",
        isolation = Isolation.REPEATABLE_READ)
public Mono<Report> createReport() {
    // reactive database operations
}
~~~

If you select an isolation level unsupported by the database/driver, the transaction may fail when starting or applying the configuration. Verify in a real environment.

### 9.1. Isolation of a joining transaction

When a `REQUIRED` method joins an existing transaction, the isolation setting on the inner method does not necessarily change the isolation of the already-running transaction.

For instance, the outer transaction started at `READ_COMMITTED`, and the inner method declares `REPEATABLE_READ` with `REQUIRED`. The inner method joins the current transaction; do not expect it to automatically upgrade the parent transaction's isolation.

Configure isolation at the boundary that actually initiates the transaction. Spring can be configured to validate transaction attributes when joining, yet validation does not elevate the active transaction's isolation level.

## 10. Using TransactionalOperator for programmatic transactions

`TransactionalOperator` is well suited when you need to define transaction boundaries in code, especially with dynamically constructed reactive pipelines.

Example:

~~~java
@Service
public class TransferService {

    private final TransactionalOperator transactionalOperator;
    private final AccountRepository accountRepository;

    public Mono<Void> transfer(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        Mono<Void> work =
                accountRepository.debit(fromId, amount)
                        .then(accountRepository.credit(toId, amount));

        return transactionalOperator.transactional(work);
    }
}
~~~

Both debit and credit belong to the same transaction. If the publisher emits an error before completion, the transaction manager rolls back per the reactive transaction contract.

### 10.1. Configuring propagation and isolation programmatically

You can create a transaction definition:

~~~java
DefaultTransactionDefinition definition =
        new DefaultTransactionDefinition();

definition.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRED);

definition.setIsolationLevel(
        TransactionDefinition.ISOLATION_REPEATABLE_READ);

definition.setTimeout(5);

TransactionalOperator operator =
        TransactionalOperator.create(transactionManager, definition);
~~~

Then:

~~~java
return operator.transactional(
        accountRepository.recalculateBalance(accountId));
~~~

Timeout is a request to the transaction manager/driver; enforcement and precision depend on configuration. It does not replace timeouts on HTTP requests, connection pools, or statements.

### 10.2. Using execute when rollback-only marking is needed

`execute` provides `ReactiveTransaction` to interact with transaction status:

~~~java
Flux<TransferResult> result =
        transactionalOperator.execute(status -> {
            return transferRepository.performTransfer(command)
                    .onErrorResume(BusinessRuleException.class, error -> {
                        status.setRollbackOnly();
                        return Mono.just(TransferResult.rejected(error.getMessage()));
                    });
        });
~~~

In this example, a business error is turned into a valued outcome while the transaction is marked rollback-only. Without calling `setRollbackOnly`, swallowing the error via `onErrorResume` could let the publisher complete normally and commit the transaction.

Use this pattern only when the business contract wants to return a rejection payload while still rolling back data. If errors should propagate to the caller, let the publisher emit the error instead of converting it to a value.

## 11. What limitations does @Transactional have in reactive code?

The annotation takes effect only when the call passes through the Spring transaction interceptor and an appropriate reactive transaction manager.

### 11.1. Methods must be called through a proxy

Spring typically applies `@Transactional` via proxies. Calling a transactional method from another method on the same object (self-invocation) can bypass the proxy, preventing the called method's propagation or isolation from being applied as intended.

Example:

~~~java
@Service
public class OrderService {

    public Mono<Void> process() {
        return saveOrder(); // self-invocation may bypass transaction proxy
    }

    @Transactional
    public Mono<Void> saveOrder() {
        return orderRepository.save(buildOrder()).then();
    }
}
~~~

Place transaction boundaries on methods called through a bean proxy or use `TransactionalOperator` to make boundaries explicit.

### 11.2. Methods must return a reactive type to use reactive transactions

With R2DBC, transactional methods should return `Mono`, `Flux`, or a Spring-supported reactive `Publisher`. If a method returns a synchronous type like `void` or `Order`, Spring may choose an imperative transaction manager or fail to manage it under reactive semantics as expected.

Do not pair a JDBC `PlatformTransactionManager` with R2DBC repositories expecting them to share a transaction. Choose the `ReactiveTransactionManager` matching R2DBC.

### 11.3. Transactions start when the publisher is subscribed

Calling a method returning `Mono` does not mean SQL has run or the transaction has begun. The transaction is established during subscription of the reactive chain.

Therefore:

- Do not call `subscribe()` inside services.
- Do not use `block()` to extract results mid-transaction.
- Do not create an independent subscription expecting it to join the current transaction.
- Return the entire publisher chain to the framework/caller.

## 12. Reactor Context and sharing transactions across operations

Reactive transactions are stored in Reactor Context rather than relying on `ThreadLocal` like traditional imperative transactions.

Repositories and `DatabaseClient` participate in the same transaction when:

- They share the `ConnectionFactory` matching the transaction manager.
- They execute within the same reactive subscription/context.
- Work is not split into an independent subscription.
- They do not manually open another connection outside the transaction context.

Good example:

~~~java
return orderRepository.save(order)
        .flatMap(saved ->
                itemRepository.saveAll(itemsFor(saved.getId()))
                        .then())
        .then(inventoryRepository.decreaseStock(productId, quantity));
~~~

The publishers are chained together. When the transaction manager manages this chain, operations can share the same transactional connection.

Bad example:

~~~java
public Mono<Void> placeOrder(Order order) {
    orderRepository.save(order).subscribe(); // separate subscription
    return inventoryRepository.decreaseStock(order.getProductId(), 1);
}
~~~

The order-saving command may run outside the returned publisher's transaction context, is not awaited by the caller, and its errors can become detached from the main flow.

### 12.1. Multiple ConnectionFactories

An R2DBC transaction manager typically manages resources for one `ConnectionFactory`. If repository A uses connection factory A and repository B uses connection factory B, a single transaction manager does not make both databases join one atomic transaction.

If writing to multiple databases is required, you need a dedicated architecture such as saga, transactional outbox, or a system-supported distributed mechanism. Do not assume R2DBC local transactions equal XA/distributed transactions.

## 13. Driver and database limitations

Spring provides a consistent API, yet actual runtime execution depends on the driver and database engine.

| Feature | Limitations to check |
|---|---|
| Isolation levels | Driver/database may not support all levels; some map to another level |
| Savepoint / `NESTED` | Requires driver and database savepoint support |
| `REQUIRES_NEW` | Needs to suspend current transaction and allocate independent transaction/connection; pool can become a bottleneck |
| Read-only transactions | May be only a hint or not enforced by the database |
| Transaction timeout | Enforcement depends on manager, driver, and database; not all timeouts equal statement timeouts |
| DDL inside transactions | Some databases can roll back DDL, others implicitly commit or restrict DDL in transactions |
| Row-level locking | Syntax and support such as `SELECT ... FOR UPDATE` vary |
| Generated values | Ability to return generated keys depends on driver and dialect |
| Multiple result sets | Stored procedures and multiple result segments are not uniformly supported |
| Cancellation | Driver must handle cancel and release resources properly; responsiveness can vary |
| Concurrent use of one connection | A connection is typically not meant for multiple independent concurrent statement streams |

Do not infer that a feature works simply because the SPI interface exposes a method for it. Check driver documentation and run integration tests on the target database.

## 14. Read-only, timeout, and default isolation

### 14.1. Is read-only a hint or a constraint?

You can declare:

~~~java
@Transactional(readOnly = true)
public Flux<OrderSummary> findSummaries() {
    return orderRepository.findAllSummaries();
}
~~~

`readOnly = true` expresses transaction intent. Depending on the transaction manager, driver, and database, it may be used as an optimization hint or translated into a database setting. Do not assume all write statements are automatically blocked merely because the annotation specifies `readOnly = true`.

If strict protection against writes is required, use appropriate database permissions, database-enforced read-only transactions if available, or explicit business checks.

### 14.2. Timeout

You can set a transaction timeout:

~~~java
@Transactional(timeout = 5)
public Mono<Order> processOrder(Order order) {
    return orderRepository.save(order);
}
~~~

Timeout values are typically in seconds in Spring's transaction definitions. How the driver/database enforces timeout can vary. A transaction timeout does not automatically guarantee every SQL query is immediately cancelled on the database or that the HTTP request finishes at the exact same instant.

Coordinate timeouts across layers:

- HTTP/request deadline.
- Connection pool acquisition.
- Transaction.
- Statement/database.
- Retry/backoff.

Do not set long transaction timeouts just to compensate for slow queries; inspect execution plans, indexes, and database load.

### 14.3. Default isolation

If isolation is not declared, Spring usually uses `ISOLATION_DEFAULT`, meaning the database/connection default. This default may be configured at the database, datasource/connection factory, or session level.

To understand actual behavior, check database configuration and test concurrent scenarios on your exact database engine version.

## 15. Data locking and optimistic locking

Isolation is not the only mechanism for handling concurrent updates. Spring Data Relational supports optimistic locking via `@Version` on entities.

Example:

~~~java
@Table("account")
public class Account {

    @Id
    private Long id;

    private BigDecimal balance;

    @Version
    private Long version;
}
~~~

When saving, Spring Data uses the version to detect whether the entity changed since it was read. If the version no longer matches, the operation can fail with an optimistic locking failure.

Optimistic locking works well when conflicts are infrequent and the application prefers detecting modifications rather than holding locks for a long time.

On databases supporting row-level locks, locking queries like `SELECT ... FOR UPDATE` can be used inside a transaction. However, syntax, behavior, and locking support depend on the database/driver. Locks are usually held until commit or rollback; longer transactions increase contention risk.

Choose mechanisms based on business invariants:

- `@Version` to detect concurrent modifications.
- Row locks to serialize operations on specific rows when needed.
- Database constraints to protect invariants like unique, foreign key, and check constraints.
- Higher isolation when controlling interactions across multiple rows or predicates.

Do not use high isolation levels as a replacement for data constraints.

## 16. Rollback, errors, and cancellation

In reactive transactions, normal publisher completion usually leads to commit; emitting an error usually leads to rollback. Cancellation before completion must also be handled as a termination path requiring cleanup and rollback per the transaction manager.

A common mistake is swallowing errors inside a transaction:

~~~java
return repository.save(entity)
        .onErrorResume(error -> Mono.empty());
~~~

After `onErrorResume`, the publisher can complete normally. The transaction manager observes completion instead of an error and may commit earlier changes unless the transaction was marked rollback-only.

If rollback is desired, you can:

- Let the error continue propagating outside the transaction.
- Mark the transaction rollback-only using the appropriate API.
- Convert the error into a result after the transaction has rolled back at an appropriate boundary.

Spring rolls back by default on unchecked exceptions (`RuntimeException`) and `Error` in many transaction configurations; checked exceptions require appropriately configured rollback rules such as `rollbackFor`. With reactive publishers, the error signal is a key part of the rollback decision, yet exception rollback rules must still be configured properly.

Do not call `subscribe()` to log or handle errors on a detached stream. Use `doOnError` for observational side effects that do not alter signals; `onErrorResume` alters the error stream and must be used intentionally.

## 17. Limitations when combining propagation and isolation

Some configurations look plausible yet do not produce the effect the author expects:

| Scenario | What to understand |
|---|---|
| Inner `REQUIRED` declares higher isolation than outer | Inner joins current transaction; the already-started transaction's isolation does not auto-upgrade |
| Inner `REQUIRES_NEW` reads outer uncommitted data | New transaction normally cannot see outer uncommitted changes |
| Inner `NESTED` rolls back | Only rolls back to savepoint; outer can still continue if transaction remains valid |
| `SUPPORTS` called outside a transaction | No transaction exists to provide a shared snapshot |
| `NOT_SUPPORTED` inside a transaction | Outer is suspended; inner runs without a transaction |
| `readOnly = true` | May be only a hint, depending on database/driver |
| `SERIALIZABLE` | Can trigger serialization failures; application needs bounded retries |
| Two repositories using two `ConnectionFactory` beans | Do not automatically share one local transaction |
| Catching errors with `onErrorResume` inside a transaction | Can turn error into completion and commit unless marked rollback-only |
| Cancelling a subscription | Must let transaction manager finish cleanup/rollback; do not create another subscription |

## 18. Testing propagation and isolation

Unit tests with fake publishers can test service logic, but do not prove the database enforces isolation, savepoints, or locking properly. Those behaviors require integration tests against the target driver/database.

### 18.1. Testing rollback

A basic scenario:

1. Start a transaction.
2. Write a row.
3. Intentionally emit an error in the next step.
4. Confirm the publisher terminates with an error.
5. Re-read in another transaction and confirm the row rolled back.

Use `StepVerifier` to verify signals:

~~~java
StepVerifier.create(orderService.createOrderThenFail(command))
        .expectError()
        .verify();
~~~

Then query the database to verify no data written inside the rolled-back transaction remains.

### 18.2. Testing REQUIRES_NEW

Open an outer transaction, call a `REQUIRES_NEW` service to write an audit record, and make the outer transaction roll back. Then verify:

- Business data from the outer transaction does not exist.
- Audit data from the inner transaction still exists.

The test must invoke through the Spring proxy and use the same transaction manager configuration expected in production.

### 18.3. Testing NESTED/savepoints

If the driver supports savepoints:

1. Write data before the nested scope.
2. Start the nested scope.
3. Write additional data.
4. Roll back the nested scope.
5. Confirm data written before the savepoint still exists inside the transaction.
6. Commit the outer transaction.
7. Confirm only data written before the savepoint was persisted.

If the database/driver does not support savepoints, tests should make the unavailability explicit rather than assuming nested transactions work.

### 18.4. Testing isolation with two connections

To test dirty reads, non-repeatable reads, or phantom reads, two transactions must run concurrently on two independent connections. Use barriers/latches or reactive test coordination to enforce the exact order:

~~~text
Transaction A                  Transaction B
-------------                  -------------
BEGIN
SELECT ...
                               BEGIN
                               UPDATE ...
                               COMMIT
SELECT again ...
COMMIT
~~~

Results must be interpreted according to the specific database and isolation level under test. Do not use a simple sequential test to draw conclusions about concurrency.

## 19. Workflow for choosing propagation and isolation

When designing a use case, answer:

1. Do the operations need to commit/roll back together?
2. Should the called method join the caller's transaction?
3. Is there a real business reason to create an independent transaction?
4. Is a savepoint needed to roll back part of the work?
5. Do we need repeatable reads of the same row or a consistent result set?
6. Are there multi-row invariants requiring locks or higher isolation?
7. Does the database/driver support the chosen isolation level, savepoints, and locks?
8. Do the repositories share the same `ConnectionFactory` and transaction manager?
9. Is the reactive chain continuous without calling `subscribe()` or `block()`?
10. On error or cancellation, does the transaction roll back properly?
11. If a transaction suffers a serialization failure, does the application have a safe retry strategy?
12. Are timeouts and pool sizes suitable for nested propagation?

Reference table:

| Need | Commonly considered choice |
|---|---|
| Multi-step use case committing/rolling back together | `REQUIRED` |
| Writing audit independent of main transaction | `REQUIRES_NEW`, if independent commit is acceptable |
| Rolling back part of work inside parent transaction | `NESTED`, if savepoints are supported |
| Can join caller's transaction without opening one itself | `SUPPORTS` |
| Caller must already have a transaction | `MANDATORY` |
| Run outside the active transaction | `NOT_SUPPORTED` |
| Disallow calling inside a transaction | `NEVER` |
| Prevent dirty reads | At least `READ_COMMITTED`, per DB semantics |
| Stable re-reads of the same row | `REPEATABLE_READ` or equivalent DB mechanism |
| Need serializable behavior | `SERIALIZABLE`, paired with retry handling |
| Detect concurrent updates on an entity | `@Version` |
| Protect data invariants | Database constraints and appropriate transactions |

## 20. Key takeaways

- Propagation governs how a method joins or creates a transaction; isolation governs visibility of changes across transactions.
- `REQUIRED` joins the current transaction or creates a new one if none exists.
- `REQUIRES_NEW` suspends the outer transaction and creates an independent transaction; it may require an extra connection.
- `NESTED` uses savepoints within the parent transaction if supported by the driver/database; it does not commit independently.
- `SUPPORTS`, `MANDATORY`, `NOT_SUPPORTED`, and `NEVER` express distinct requirements regarding transaction presence.
- `READ_COMMITTED` prevents dirty reads but may permit non-repeatable reads or phantoms under standard semantics.
- `REPEATABLE_READ` and `SERIALIZABLE` have database-specific behavior; `SERIALIZABLE` may require retries.
- Reactive `@Transactional` requires a reactive transaction manager and a method returning a publisher; calls must go through a proxy.
- `TransactionalOperator` lets you define transaction boundaries directly inside a reactive chain.
- Transaction context lives in Reactor Context; do not detach subscriptions with `subscribe()` or block with `block()`.
- Operations share the same local transaction only when using the right `ConnectionFactory` and transaction context.
- Savepoints, isolation, read-only, timeouts, locking, DDL, and cancellation depend on the driver/database.
- `onErrorResume` can swallow errors and cause the transaction to commit unless marked rollback-only.
- Pair `@Version`, row locks, and constraints with appropriate isolation to handle data contention.
- Test transactions with integration tests against the target database/driver, covering rollback, propagation, savepoints, and two concurrent transactions.
