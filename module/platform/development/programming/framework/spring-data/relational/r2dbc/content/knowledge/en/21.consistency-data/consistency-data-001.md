# Lost Update, Non-repeatable Read, and Phantom Read

When multiple requests or transactions concurrently read and modify data, the execution order can cause the final result to differ from what the business logic expects. Three common phenomena are **lost update**, **non-repeatable read**, and **phantom read**.

These phenomena relate to how a database isolates concurrent transactions. In Spring Data R2DBC, an application can control them using reactive transactions, isolation levels, optimistic locking with `@Version`, atomic update statements, or explicit locking when supported by the database and driver.

No single isolation level is always appropriate for every operation. Identify which data may face contention, the consequences of reading data that changes midway, and the level of locking or retries the system can tolerate.

## 1. Why Can Concurrent Transactions Cause Anomalies?

A transaction is a unit of work that reads and/or writes data. When multiple transactions run concurrently, the database may interleave their statements to increase throughput.

For example, two requests simultaneously update an account balance. Each request might read the same initial value and compute its own result. If both write back values based on stale data, one change can be overwritten.

Transactions require certain consistency guarantees. Databases provide these through isolation levels, locks, MVCC (Multi-Version Concurrency Control), conflict detection, and commit/rollback mechanisms.

### 1.1. Key Terminology

| Term | Meaning |
| --- | --- |
| Transaction | A group of database operations managed as a single commit or rollback unit |
| Concurrent transactions | Transactions whose execution times overlap |
| Isolation level | The degree to which a database prevents a transaction from observing uncommitted effects or changes from other transactions |
| MVCC | A mechanism that manages multiple versions of data so a transaction can read an appropriate snapshot |
| Lock | A mechanism that coordinates read/write permissions on rows, keys, or data ranges |
| Optimistic locking | Detecting conflicts on write using a version or comparison condition, rather than holding an exclusive lock upfront |
| Pessimistic locking | Proactively locking data to restrict other transactions from modifying it during an operation |

The isolation level is part of the transaction contract. The actual implementation mechanism and level of guarantees depend on the database management system.

## 2. Lost Update

A lost update occurs when two transactions both read the same version of data, compute separate changes, and then the later write overwrites the result of the earlier write. Both operations may report success, yet one business change is missing from the final value.

### 2.1. Account Balance Example

Suppose an account has an initial balance of 100. Two concurrent requests arrive:

- Transaction T1 withdraws 20.
- Transaction T2 withdraws 10.

The correct result if both transactions are accepted is 70. However, an unsafe read-modify-write approach can produce the following execution schedule:

| Order | Transaction T1 | Transaction T2 | Balance in database |
| ---: | --- | --- | ---: |
| 1 | Read balance = 100 | | 100 |
| 2 | | Read balance = 100 | 100 |
| 3 | Compute 100 - 20 = 80 | | 100 |
| 4 | | Compute 100 - 10 = 90 | 100 |
| 5 | Write 80 | | 80 |
| 6 | | Write 90 | 90 |

The final result is 90. T1's withdrawal of 20 was overwritten by T2. This is a lost update.

### 2.2. Vulnerable Read-Modify-Write Code

A service might be written like this:

```java
@Transactional
public Mono<Account> withdraw(Long accountId, BigDecimal amount) {
    return accountRepository.findById(accountId)
            .flatMap(account -> {
                BigDecimal newBalance = account.getBalance().subtract(amount);
                account.setBalance(newBalance);
                return accountRepository.save(account);
            });
}
```

A transaction groups operations into a single commit unit, but merely declaring `@Transactional` does not automatically prevent all lost updates. Two transactions can still read the same value and write based on stale data if there is no appropriate conflict detection or locking mechanism.

### 2.3. Approach 1: Atomic Update in the Database

If the business logic only needs to deduct money and ensure the balance stays non-negative, let the database perform the calculation in a single conditional statement:

```sql
UPDATE accounts
SET balance = balance - :amount
WHERE id = :accountId
  AND balance >= :amount;
```

Neither request sends back a previously read balance value. Each update statement computes based on the current value at the time the database executes the operation, and the `balance >= :amount` condition is checked together with the update statement.

The repository can declare:

```java
public interface AccountRepository
        extends ReactiveCrudRepository<Account, Long> {

    @Modifying
    @Query("""
           UPDATE accounts
           SET balance = balance - :amount
           WHERE id = :accountId
             AND balance >= :amount
           """)
    Mono<Integer> withdrawIfEnough(
            @Param("accountId") Long accountId,
            @Param("amount") BigDecimal amount);
}
```

The service checks the number of affected rows:

```java
public Mono<Void> withdraw(Long accountId, BigDecimal amount) {
    if (amount.signum() <= 0) {
        return Mono.error(new IllegalArgumentException("Amount must be positive"));
    }

    return accountRepository.withdrawIfEnough(accountId, amount)
            .flatMap(rows -> {
                if (rows == 1) {
                    return Mono.empty();
                }
                return Mono.error(new InsufficientBalanceException(accountId));
            });
}
```

This example assumes each ID identifies exactly one account. If the row count is 0, the account may not exist or may have insufficient balance; an additional query can be executed if the business logic needs to distinguish between the two cases. Confirm the row-counting semantics of the driver and database.

Atomic updates are especially useful for counters, inventory, balances, and transformations that can be expressed directly in SQL. However, if the update decision depends on multiple complex domain rules, the statements and transactions must be designed to fully express those conditions.

### 2.4. Approach 2: Optimistic Locking with `@Version`

Optimistic locking allows multiple transactions to read the same record, but checks the version on write. The first transaction updates successfully and increments the version. The subsequent transaction still holds the old version and therefore fails to update.

Entity:

```java
@Table("accounts")
public class Account {

    @Id
    private Long id;

    @Version
    private Long version;

    private BigDecimal balance;

    // Constructors, getters, and setters omitted.
}
```

Repository:

```java
public interface AccountRepository
        extends ReactiveCrudRepository<Account, Long> {
}
```

When saving an entity with `@Version`, Spring Data Relational uses the version in the update condition and updates the version when the operation succeeds. If no row matches the expected version, Spring Data raises an optimistic locking error, typically `OptimisticLockingFailureException`.

Illustrative execution schedule:

| Order | T1 | T2 |
| ---: | --- | --- |
| 1 | Read balance 100, version 4 | |
| 2 | | Read balance 100, version 4 |
| 3 | Write balance 80 with condition version = 4; succeeds, version becomes 5 | |
| 4 | | Write balance 90 with condition version = 4; no matching row |
| 5 | | Receives optimistic locking error and handles conflict |

T2 does not silently overwrite T1. The application can ask the client to retry, reload the latest version and recalculate, or return a conflict depending on business rules.

### 2.5. Approach 3: Pessimistic Locking or Explicit Locks

For operations that must read a record and then make a decision based on the current state, a locking statement such as `SELECT ... FOR UPDATE` can be used inside a transaction. The database holds an appropriate lock until the transaction finishes, causing competing transactions to wait or fail according to the timeout/deadlock policy.

Repository example:

```java
@Query("SELECT * FROM accounts WHERE id = :id FOR UPDATE")
Mono<Account> findByIdForUpdate(@Param("id") Long id);
```

Service:

```java
@Transactional
public Mono<Account> withdrawWithLock(Long id, BigDecimal amount) {
    return accountRepository.findByIdForUpdate(id)
            .switchIfEmpty(Mono.error(new AccountNotFoundException(id)))
            .flatMap(account -> {
                if (account.getBalance().compareTo(amount) < 0) {
                    return Mono.error(new InsufficientBalanceException(id));
                }

                account.setBalance(account.getBalance().subtract(amount));
                return accountRepository.save(account);
            });
}
```

This example follows the syntax of databases that support `FOR UPDATE`. Locking capabilities, lock scope, and exact syntax vary by database and driver. The transaction must genuinely wrap both the `SELECT ... FOR UPDATE` statement and the write operation; if the query runs outside a transaction, the lock may be released as soon as the statement completes.

Keep locking transactions very short. Do not make HTTP calls, send emails, or wait for user input while holding a database lock.

## 3. Non-repeatable Read

A non-repeatable read occurs when a transaction reads the same row twice and gets different values because another transaction committed a change between the two reads.

### 3.1. Order Status Example

Suppose T1 is generating a report and needs to read an order's status twice within the same transaction:

| Order | Transaction T1 | Transaction T2 |
| ---: | --- | --- |
| 1 | `SELECT status` → `PAID` | |
| 2 | | `UPDATE orders SET status = 'CANCELLED' WHERE id = 10` |
| 3 | | COMMIT |
| 4 | Second `SELECT status` → `CANCELLED` | |

T1 reads the same row, yet the value differs within the same transaction. This is a non-repeatable read.

### 3.2. How Do Isolation Levels Affect This?

According to the SQL isolation model:

- `READ COMMITTED` prevents reading uncommitted data, but allows a transaction to see newly committed values between two statements. Thus, non-repeatable reads can occur.
- `REPEATABLE READ` guarantees repeatable reads for the same row per the SQL standard, though exact behavior regarding snapshots and range queries depends on the database.
- `SERIALIZABLE` requires the outcome to be equivalent to a valid serial execution order, thereby preventing serialization anomalies such as non-repeatable reads.

Some databases use MVCC and provide a stable snapshot for `REPEATABLE READ` transactions; others use different locking mechanisms and definitions. Check the documentation for the database system in use rather than inferring every detail solely from the isolation level name.

### 3.3. When Should Non-repeatable Reads Be Prevented?

Not every read API needs the same snapshot for the entire request. If a screen only displays current data at the moment of each query, `READ COMMITTED` may be suitable.

Preventing non-repeatable reads is useful when a transaction needs to:

- Read the same value multiple times to make a consistent decision.
- Compute sums or validate conditions based on previously read data.
- Generate reports where multiple read steps must use the same snapshot.
- Check state before performing related modifications.

If only a single stable value is needed, you can sometimes read it once and hold it in a local variable. However, if the decision spans multiple statements and contended data, consider an appropriate isolation level or lock.

## 4. Phantom Read

A phantom read occurs when a transaction re-executes the same conditional query and sees additional or missing rows because another transaction inserted, deleted, or modified a row so that it starts or stops matching the condition.

Unlike a non-repeatable read, the focus of a phantom read is that **the set of rows matching a predicate changes**, not merely the value of an already-read row.

### 4.1. Counting Open Orders Example

T1 needs to count the number of `OPEN` orders:

| Order | Transaction T1 | Transaction T2 |
| ---: | --- | --- |
| 1 | `SELECT COUNT(*) FROM orders WHERE status = 'OPEN'` → 5 | |
| 2 | | `INSERT INTO orders (..., status) VALUES (..., 'OPEN')` |
| 3 | | COMMIT |
| 4 | Re-run same query → 6 | |

The new row added by T2 becomes a "phantom" to T1's second read.

A phantom can also appear when T2 changes an order's status from `CLOSED` to `OPEN`, or deletes a row that matched the predicate.

### 4.2. Why Row Locking Alone May Not Prevent Phantoms

If T1 only locks existing `OPEN` rows, another transaction can still insert a new row matching that condition into the range, depending on the database and lock type. To prevent phantoms, the database needs a predicate/range protection mechanism or an appropriate snapshot/isolation level.

Some databases use range locks or predicate locks at higher isolation levels. Other databases rely on MVCC and detect conflicts at commit time. Implementations vary.

### 4.3. Isolation Levels and Phantom Reads

According to SQL isolation levels:

- `READ COMMITTED` allows phantom reads.
- `REPEATABLE READ` under the SQL standard prevents non-repeatable reads, but may still allow phantom reads.
- `SERIALIZABLE` prevents phantom reads by requiring equivalence to serial execution.

Some database systems implement `REPEATABLE READ` more strongly than the standard minimum. For example, a database's snapshot isolation might prevent phantoms within a specific transaction while still not being fully equivalent to `SERIALIZABLE` for all forms of write skew. Check the database documentation and test against the actual configuration.

## 5. Comparing the Three Phenomena

| Phenomenon | Observed change in transaction | Example | Common handling |
| --- | --- | --- | --- |
| Lost update | Later write overwrites earlier write based on stale data | Two requests modify a balance simultaneously | Atomic update, `@Version`, explicit lock |
| Non-repeatable read | Reading the same row twice yields different values | Order status changes between two SELECTs | `REPEATABLE_READ`/`SERIALIZABLE` isolation, appropriate lock |
| Phantom read | Set of rows matching the same predicate changes between two queries | Count of `OPEN` orders increases due to new insert | `SERIALIZABLE`, predicate/range locking, or appropriate snapshot |

Lost update is a write-overwrite issue during updates, whereas non-repeatable read and phantom read are read anomalies within a transaction. A system may need to handle multiple types at the same time.

## 6. Isolation Levels in SQL

SQL defines the following standard isolation levels. The table below describes behavior under the standard model; actual databases may provide stronger guarantees or different implementations.

| Isolation level | Dirty read | Non-repeatable read | Phantom read |
| --- | --- | --- | --- |
| `READ UNCOMMITTED` | Possible | Possible | Possible |
| `READ COMMITTED` | Not possible | Possible | Possible |
| `REPEATABLE READ` | Not possible | Not possible per standard | Possible per standard |
| `SERIALIZABLE` | Not possible | Not possible | Not possible |

### 6.1. Dirty Read for Distinction

A dirty read is when a transaction reads data modified by a writing transaction that has not yet committed. If the writing transaction rolls back, the reading transaction has used a value that never became committed data.

A dirty read differs from the three phenomena covered here:

- Lost update: a change is overwritten.
- Non-repeatable read: re-reading a row sees a different value.
- Phantom read: re-reading a predicate sees a different set of rows.

`READ COMMITTED` and higher prevent dirty reads under the SQL model.

### 6.2. Do Not Over-Infer from the Isolation Name

Two databases accepting `REPEATABLE READ` may use different MVCC, locking, or conflict-detection rules. Some databases abort a transaction when detecting a conflict; others make transactions wait for locks.

Therefore, examine:

- The database's default isolation level.
- The isolation level actually applied to the connection.
- The MVCC/locking semantics of the database system.
- Potential serialization/deadlock errors that may occur.
- How the driver propagates the isolation level and transaction to the database.

## 7. Configuring Isolation Levels in Spring Data R2DBC

Spring manages reactive transactions via `R2dbcTransactionManager` or a transaction manager compatible with `ConnectionFactory`. The isolation level can be specified using `@Transactional`.

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class OrderReportService {

    private final OrderRepository orderRepository;

    public OrderReportService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional(isolation = Isolation.REPEATABLE_READ)
    public Mono<OrderSnapshot> createSnapshot(Long orderId) {
        return orderRepository.findById(orderId)
                .flatMap(order -> orderRepository.findById(orderId)
                        .map(secondRead -> new OrderSnapshot(
                                order.getId(),
                                order.getStatus(),
                                secondRead.getStatus())));
    }
}
```

This example illustrates declaring an isolation level. A real use case typically reads from multiple data sources or makes a business decision rather than reading the same row twice like this.

### 7.1. Reactive Transactions Are Bound to the Publisher

For methods returning `Mono` or `Flux`, Spring uses reactive transaction management. The transaction context is propagated via Reactor Context rather than relying solely on the current thread.

Therefore:

- Keep database operations belonging to the transaction within the same publisher chain.
- Let the framework or caller subscribe to the publisher.
- Do not call `.block()` inside a transactional pipeline.
- Do not call `.subscribe()` independently for an operation that needs to participate in the current transaction.
- Ensure repositories use the same `ConnectionFactory` and transaction manager if they must participate in the same transaction.

### 7.2. Using `TransactionalOperator`

Transaction boundaries can be managed with `TransactionalOperator` instead of annotations:

```java
public Mono<OrderSnapshot> loadSnapshot(Long orderId) {
    Mono<OrderSnapshot> work = orderRepository.findById(orderId)
            .flatMap(order -> paymentRepository.findByOrderId(orderId)
                    .collectList()
                    .map(payments -> new OrderSnapshot(order, payments)));

    return transactionalOperator.transactional(work);
}
```

`TransactionalOperator` is useful when wrapping a specific pipeline or when transaction boundaries are created dynamically. The operator must be configured with the corresponding R2DBC transaction manager.

### 7.3. Isolation Level Does Not Replace Transaction Boundaries

Declaring an isolation level on a method does not mean every database call in the application uses that level. It applies to the transaction created at that boundary. If the method does not actually execute through a transaction proxy or the publisher is not consumed properly, the transaction may not take effect as intended.

When multiple transaction managers exist, explicitly specify the appropriate manager if needed so R2DBC operations do not accidentally use a JDBC transaction manager.

## 8. Optimistic Locking in Spring Data Relational

`@Version` is a common way to detect lost updates without holding an exclusive lock for the entire duration of user edits.

### 8.1. Versioned Entity

```java
@Table("products")
public class Product {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;
    private Integer stock;

    // Constructors, getters, and setters omitted.
}
```

The schema needs a corresponding version column:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    name VARCHAR(160) NOT NULL,
    stock INTEGER NOT NULL
);
```

When saving a new entity, Spring Data initializes the version according to the version type's rules. On update, the current version is used in the condition and the new version value is written if the update succeeds.

### 8.2. Handling Optimistic Locking Failures

When two requests both read version 3, only one request can update successfully against that version. The other request receives a conflict error.

```java
public Mono<Product> updateProduct(Product product) {
    return productRepository.save(product)
            .onErrorMap(OptimisticLockingFailureException.class,
                    error -> new ProductConflictException(product.getId(), error));
}
```

The application can translate the error into HTTP `409 Conflict` or a corresponding business outcome. Do not catch the error and return the stale entity as if the operation succeeded.

### 8.3. Retries Must Reload Fresh Data and Recalculate

When optimistic locking fails, do not simply call `save()` again on the same object carrying the stale version. You must load the latest version, re-check business rules, and recalculate the change.

Conceptual example:

```java
public Mono<Product> reserveStock(Long productId, int quantity) {
    return productRepository.findById(productId)
            .switchIfEmpty(Mono.error(new ProductNotFoundException(productId)))
            .flatMap(product -> {
                if (product.getStock() < quantity) {
                    return Mono.error(new InsufficientStockException(productId));
                }

                product.setStock(product.getStock() - quantity);
                return productRepository.save(product);
            });
}
```

If automatic retry is needed, wrap the entire fresh-read, validation, and write flow in a single attempt, bound the retry count, and only retry when business-safe. Do not blindly retry operations with external side effects such as transferring funds, sending emails, or publishing messages without an idempotency mechanism.

## 9. Atomic Updates vs. Optimistic Locking: Which to Choose?

| Situation | Appropriate approach |
| --- | --- |
| Incrementing/decrementing counters, stock, or balances via simple math | A single `UPDATE column = column + ...` statement with a predicate |
| Updating an aggregate after checking multiple fields | `@Version` and repository `save()` |
| Reading then deciding based on current state that requires locking | `SELECT ... FOR UPDATE` in a short transaction, if supported by the database |
| Multiple users editing the same record and needing conflict detection | Optimistic locking and returning a conflict |
| Condition spanning a range of multiple rows | Predicate/range lock or `SERIALIZABLE`, per database semantics |
| No need for a consistent snapshot across multiple reads | Use an appropriate default isolation level, typically `READ COMMITTED` |

Atomic updates generally require fewer round trips and eliminate the window between read and write. Optimistic locking fits when loading an entity and applying domain logic is required. Pessimistic locking fits certain high-contention operations, though it increases wait times and deadlock risk.

## 10. Preventing Non-repeatable Reads and Phantom Reads

### 10.1. Use Snapshot Transactions When Consistent Reads Are Needed

If a use case requires multiple SELECT statements to observe a stable data state, choose an isolation level suited to the database. `REPEATABLE_READ` may suffice for the same row or read snapshot depending on database semantics. If a row set matching a predicate must be protected against concurrent inserts or updates, `SERIALIZABLE` or range locking may be necessary.

### 10.2. Use a Single Statement When Possible

If you need to compute totals, counts, and read related values, a single SQL statement can avoid having two statements observe two different states.

Example:

```sql
SELECT status, COUNT(*) AS order_count
FROM orders
WHERE created_at >= :fromTime
GROUP BY status;
```

A single statement is executed by the database under its snapshot/statement semantics. This can be simpler than running multiple separate queries and merging results, though appropriate isolation is still needed if the transaction makes subsequent write decisions based on it.

### 10.3. Range Locks or SERIALIZABLE for Critical Predicates

For example, a business rule limits open orders (`OPEN`) to at most 10. Simply reading `COUNT(*)` and then inserting can suffer a race condition: two transactions both see 9 and both insert, resulting in 11.

To protect this invariant, you can:

- Design a counter/slot row updated atomically with the condition `open_count < 10`.
- Lock a row representing the business scope, then check and write inside a transaction.
- Use `SERIALIZABLE` and handle serialization failures with safe retries.
- Use database constraints or structures that can directly express the invariant.

Locking only existing rows returned for `OPEN` may not be enough to prevent a new row from being inserted into the range, depending on the database. Check predicate/range lock semantics.

## 11. Deadlocks and Serialization Failures

When using locks or `SERIALIZABLE`, transactions can be rejected by the database to preserve consistency.

- **Deadlock** occurs when transactions wait on each other's locks in a cycle.
- **Serialization failure** occurs when the database cannot allow a transaction to commit while maintaining an outcome equivalent to serial execution.
- **Lock timeout** occurs when waiting for a lock exceeds the configured limit.

The application must handle these errors with a bounded retry policy or return an appropriate conflict / service-unavailable error. Do not retry infinitely, as that can increase load and lengthen queues.

To reduce deadlocks:

1. Access rows in a consistent order across transactions.
2. Keep transactions short.
3. Lock only the data that is necessary.
4. Avoid calling external services while holding locks.
5. Set reasonable timeouts.
6. Log transaction IDs, queries, and lock wait durations without exposing sensitive data.

## 12. Testing Concurrency Phenomena

Single-threaded unit tests usually cannot detect lost updates, non-repeatable reads, or phantom reads. Integration tests with a real database and at least two independent connections/transactions are needed.

### 12.1. Designing a Test That Synchronizes Two Transactions

A concurrency test should:

1. Create deterministic initial data.
2. Open two independent transactions.
3. Use a barrier/latch so both read before allowing writes to proceed.
4. Control the commit or rollback order.
5. Read the final result and verify business invariants.
6. Repeat the test enough times to catch rare race conditions.

Do not use the same connection for both transactions. If a test runs inside a single test transaction, it cannot reproduce real contention.

### 12.2. Testing Lost Updates

With an initial balance of 100, run two withdrawals of 20 and 10 concurrently. Verify:

- If both transactions are accepted, the final balance is 70.
- If one transaction is rejected due to conflict, the result accurately reflects the accepted transaction and the client knows the other failed.
- There is never a case where both report success yet the final balance is 80 or 90 due to an overwrite.

### 12.3. Testing Non-repeatable Reads

Open T1 at the isolation level under test. T1 reads a row; T2 updates and commits; T1 reads the same row again. Verify the outcome according to the database semantics and configured isolation level.

### 12.4. Testing Phantom Reads

T1 executes a query counting rows matching a predicate. T2 inserts a row matching the predicate and commits. T1 re-runs the query. Verify the row set or count against the actual isolation level. Do not rely on generic SQL assumptions if the database provides a stronger isolation implementation.

### 12.5. Reactive Testing Tools

`StepVerifier` helps verify that a publisher emits values, completes, or errors:

```java
StepVerifier.create(accountService.withdraw(accountId, new BigDecimal("20.00")))
        .verifyComplete();
```

For concurrency tests, add coordination mechanisms between publishers/transactions, such as `Sinks.One`, a `CountDownLatch` in the test orchestrator, or a dedicated test harness. Do not put blocking synchronization onto the application's event-loop threads.

## 13. Illustrative SQL Two-Transaction Examples

The following snippets should be run in two separate database sessions to observe how isolation behaves. Exact syntax and outcomes depend on the database system.

### 13.1. Non-repeatable Read at READ COMMITTED

Session A:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT status FROM orders WHERE id = 10;
-- Pause to let Session B update and COMMIT.

SELECT status FROM orders WHERE id = 10;
COMMIT;
```

Session B:

```sql
BEGIN;
UPDATE orders SET status = 'CANCELLED' WHERE id = 10;
COMMIT;
```

In a database using common READ COMMITTED semantics, Session A can observe the new value in the second SELECT statement.

### 13.2. Phantom Read Under the SQL Model

Session A:

```sql
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

SELECT COUNT(*) FROM orders WHERE status = 'OPEN';
-- Pause to let Session B insert and COMMIT.

SELECT COUNT(*) FROM orders WHERE status = 'OPEN';
COMMIT;
```

Session B:

```sql
BEGIN;
INSERT INTO orders (id, status) VALUES (9001, 'OPEN');
COMMIT;
```

Session A may receive a different count on the second read. If run at a higher isolation level, the database may preserve the old snapshot, lock the range, or reject one transaction.

## 14. Common Concurrency Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Balance or inventory gets overwritten | Read-modify-write without version/condition checks | Atomic update, `@Version`, or appropriate lock |
| Two requests both report success but only one change persists | Lost update | Verify invariants with concurrency tests; detect conflicts on write |
| Same transaction reads a row and sees changing values | Isolation allows non-repeatable reads | `REPEATABLE_READ`, `SERIALIZABLE`, or appropriate lock |
| Count changes between two SELECTs | Phantom read or changing source data | Snapshot/`SERIALIZABLE` or predicate protection |
| Optimistic locking failure | Stale entity or another transaction updated first | Reload, revalidate business rules, return conflict, or bounded retry |
| Transactions wait for a long time | Locks held too long or overloaded pool/database | Shorten transactions, inspect lock waits and timeouts |
| Deadlock | Transactions lock resources in different orders | Standardize access order, use bounded retries |
| Retry duplicates operations | Non-idempotent side effects | Idempotency keys, outbox, or idempotent retry design |
| `@Transactional` has no expected effect | Call bypassed proxy, publisher not consumed properly, or wrong transaction manager | Check proxy, reactive chain, and ConnectionFactory |

## 15. Process for Choosing Consistency Controls

When designing a read/write operation, follow these steps:

1. Identify the business invariant, such as a non-negative balance or a cap on open orders.
2. Identify operations that may run concurrently on the same row or dataset.
3. Check the risks of lost updates, non-repeatable reads, and phantom reads separately.
4. If the update can be expressed as a single SQL statement, prefer an atomic update with a predicate.
5. If loading the entity and applying domain logic is required, consider `@Version`.
6. If data must be locked during validation and writing, consider pessimistic locking inside a short transaction.
7. If multiple statements must share the same snapshot, choose an isolation level based on database semantics.
8. If the invariant involves a row set/predicate, evaluate `SERIALIZABLE`, range/predicate locks, or an appropriate counter/constraint structure.
9. Define how optimistic conflicts, deadlocks, and serialization failures will be handled.
10. Write integration tests using multiple independent transactions against the actual target database.

## 16. Mechanism Selection Diagram

```mermaid
flowchart TD
    A[Detect potential contention across transactions] --> B{Is the update a simple transformation?}
    B -->|Yes| C[Conditional atomic UPDATE]
    B -->|No| D{Can optimistic conflicts be tolerated?}
    D -->|Yes| E[@Version and retry/conflict handling]
    D -->|No| F{Need a lock during read-then-write?}
    F -->|Yes| G[SELECT FOR UPDATE in a short transaction]
    F -->|No| H[Redesign invariant and transaction]
    C --> I{Need multiple reads on the same snapshot?}
    E --> I
    G --> I
    H --> I
    I -->|Yes| J[Choose REPEATABLE_READ or SERIALIZABLE per DB]
    I -->|No| K[Appropriate default isolation]
    J --> L[Test concurrency on a real database]
    K --> L
```

## 17. Conclusion

A lost update is when one write overwrites another transaction's change; a non-repeatable read is reading the same row again and seeing a different value; a phantom read is re-running the same predicate and seeing the resulting row set change.

In Spring Data R2DBC, choose controls based on the anomaly type: use atomic updates for simple calculations, `@Version` to detect conflicts when saving entities, `SELECT ... FOR UPDATE` when explicit locking is required, and an appropriate isolation level when multiple reads must share a consistent snapshot. For reactive transactions, keep operations within the same publisher chain and use the right R2DBC transaction manager.

Isolation level names do not guarantee identical behavior across all databases. Verify the database system's semantics, handle deadlocks/serialization failures with bounded retries, and test with multiple independent transactions against a real database before relying on a consistency guarantee in production.
