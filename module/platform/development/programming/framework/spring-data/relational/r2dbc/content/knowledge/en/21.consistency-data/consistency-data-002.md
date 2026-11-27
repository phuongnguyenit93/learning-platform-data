# Choosing Isolation Levels Based on Business Invariants

Transaction isolation determines which concurrent changes a transaction can observe and how the database coordinates running transactions. With Spring Data R2DBC, the isolation level is configured on reactive transactions through the Spring transaction manager and ultimately depends on the capabilities of the database and the R2DBC driver.

Do not choose `SERIALIZABLE` for every operation just to make data "safe," and do not always leave the default level without understanding business invariants. Identify what must always remain true, examine how concurrent operations could break that condition, and then choose the right mechanism: database constraints, atomic update statements, optimistic locking, row locks, or a higher isolation level.

## 1. Start from Business Invariants

A business invariant is a condition that must hold true before and after every valid transaction. For example:

- Inventory quantity must never be negative.
- An email can belong to only one account within the same tenant.
- A room can have at most one active booking during the same time slot.
- Total debited amount must equal total credited amount.
- On an on-call team, at least one person must always remain on duty.
- An order cannot be both payment-confirmed and cancelled across two concurrent flows.

Isolation is only part of the solution. Many invariants are better protected by constraints or a single atomic SQL statement. For instance, `CHECK (available >= 0)` and `UPDATE ... WHERE available >= :quantity` can protect stock directly in the database without needing `SERIALIZABLE` for every operation.

Before selecting an isolation level, answer:

1. Which condition must always be true?
2. Which transactions can read or write the same row, the same row set, or the same logical range?
3. Does a transaction need to re-read data and see the exact initial snapshot?
4. Can multiple transactions check the same condition and then update different rows?
5. Does the database provide constraints or atomic operations to enforce that condition?
6. If the database aborts a transaction due to a conflict, can the application safely retry?

## 2. Phenomena When Transactions Run Concurrently

Isolation levels are commonly explained through several anomalies. They help identify what can happen when two transactions interleave.

### 2.1 Dirty Read

A dirty read occurs when transaction A reads data modified by transaction B before B has committed. If B rolls back, A has acted on a value that never became committed data.

Example: B reduces a balance from 100 to 20 without committing. A reads 20 and decides to reject an expense. Then B rolls back, and the actual balance returns to 100. A's decision was based on transient data.

Under the SQL model, `READ_UNCOMMITTED` permits dirty reads. Many databases do not actually allow dirty reads; for example, PostgreSQL treats `READ UNCOMMITTED` as `READ COMMITTED`. Check the target database's behavior instead of relying solely on the isolation level name.

### 2.2 Non-repeatable Read

A non-repeatable read occurs when a transaction reads the same row twice and gets two different values because another transaction committed an update between the two reads.

Example: A reads an order status as `PENDING`. B updates it to `PAID` and commits. When A reads the same row again, A sees `PAID`. If business logic requires reads within a transaction to observe the same data version, an appropriate isolation level or snapshot strategy is needed.

### 2.3 Phantom Read

A phantom read occurs when a transaction re-runs the same query condition and sees the resulting row set change because another transaction inserted, deleted, or modified a row so that it matches that condition.

Example: A counts room bookings in a time window and gets 0. B inserts a matching booking and commits. A re-runs the same query and gets 1. The newly appearing row in the result set is a phantom.

### 2.4 Lost Update

A lost update occurs when two transactions read the same value, independently compute a new value, and overwrite each other. For example, a balance is 100; A computes 100 + 10 = 110, and B computes 100 - 20 = 80. If both write absolute values without conflict control, the final result may be 110 or 80 instead of 90.

Not every database or every isolation level handles lost updates the same way. They can be avoided using atomic relative updates (`balance = balance + :delta`), optimistic version checks, or row locks depending on the business logic.

### 2.5 Write Skew

Write skew can occur when two transactions read the same dataset satisfying an invariant, and then each transaction updates a different row. Because they do not overwrite the same row, per-row conflict detection may fail to prevent a set-wide violation.

For example, suppose two doctors are on call. The invariant is that at least one doctor must always be on call. A reads that both doctors 1 and 2 are on call, and toggles doctor 1 off duty. B also reads a snapshot with both doctors on call, and toggles doctor 2 off duty. If both commit, nobody is on call even though each transaction individually saw one doctor remaining.

Write skew is why multi-row invariants must be understood. `@Version` on individual rows does not automatically resolve every conflict across different rows. You may need `SERIALIZABLE`, locking a row that represents the group, or redesigning the data model so a database constraint can enforce the rule.

## 3. Common Isolation Levels

Spring defines isolation levels via `TransactionDefinition`:

| Isolation level | Dirty read | Non-repeatable read | Phantom read | General meaning |
|---|---|---|---|---|
| `READ_UNCOMMITTED` | Possible | Possible | Possible | Allows reading uncommitted data per standard; databases may upgrade to a stricter level. |
| `READ_COMMITTED` | No | Possible | Possible | Each statement reads only committed data as of a point appropriate to the database. |
| `REPEATABLE_READ` | No | Not per standard definition | Possible per standard definition | Keeps already-read data stable; phantom handling depends on the database. |
| `SERIALIZABLE` | No | No | Not under standard model | Outcome is equivalent to a serial execution order; transactions may be aborted on conflict. |

This table describes high-level SQL standard semantics. Databases may implement them using locks, MVCC, or other mechanisms, and some systems are stricter than the standard minimum. For example, PostgreSQL uses snapshot isolation for `REPEATABLE READ`, preventing phantoms in its implementation while still allowing certain serialization anomalies; PostgreSQL's `SERIALIZABLE` uses Serializable Snapshot Isolation and may abort transactions requiring retry.

`DEFAULT` is not a standalone isolation level in the anomaly matrix. It instructs Spring to use the default level configured by the transaction manager or database. Verify the database's default instead of assuming every system uses `READ_COMMITTED`.

## 4. Choosing a Level by Invariant Type

Some common guidelines:

| Invariant or need | Mechanism to consider first | Typically suitable isolation |
|---|---|---|
| Disallow duplicate emails | Composite unique constraint on tenant and email | Usually no need to raise isolation just for uniqueness. |
| Non-negative inventory | `CHECK` constraint and `UPDATE ... WHERE available >= :qty` | Usually default/`READ_COMMITTED` suffices if atomic. |
| Updating the same row, detecting overwrites | `@Version` or version-conditional update | Default level may suffice if conflicts are handled. |
| Reading the same snapshot across multiple statements | Appropriate snapshot/transaction isolation | `REPEATABLE_READ` or database-equivalent level. |
| Rule spanning multiple rows/ranges with write-skew risk | Constraint, range lock, or serializable transaction | `SERIALIZABLE` may be needed. |
| Reporting reads not requiring cross-statement snapshot consistency | Separate queries or read model | Usually default/`READ_COMMITTED`. |

This is a starting point for analysis, not a replacement for database documentation. Examine the specific SQL, indexes, constraints, transaction patterns, and semantics of the running database engine.

## 5. Configuring Isolation in Spring Data R2DBC

Spring Data R2DBC uses a reactive transaction manager, typically `R2dbcTransactionManager`, to manage transactions for a `ConnectionFactory`. The isolation level can be declared using `@Transactional` on methods returning reactive publishers.

Example requesting `READ_COMMITTED`:

```java
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Transactional(isolation = Isolation.READ_COMMITTED)
public Mono<Order> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> {
            order.setStatus(OrderStatus.CONFIRMED);
            return orderRepository.save(order);
        });
}
```

With `@Transactional`, ensure the method is invoked through a Spring proxy according to the application's transaction configuration. Self-invocation within the same bean usually bypasses the proxy. Reactive methods must return `Mono` or `Flux` so the transaction wraps the publisher lifecycle; do not call `subscribe()` or `block()` inside to detach operations from the transaction context.

If `isolation` is omitted, Spring uses `ISOLATION_DEFAULT`, meaning the default of the transaction manager/database. Do not apply `SERIALIZABLE` across all services when only a few operations have invariants requiring it.

### 5.1 Configuring with TransactionalOperator

When you want to control transaction boundaries directly inside a reactive chain, create a `TransactionalOperator` with a `TransactionDefinition`:

```java
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.DefaultTransactionDefinition;
import org.springframework.transaction.reactive.TransactionalOperator;

DefaultTransactionDefinition definition = new DefaultTransactionDefinition();
definition.setIsolationLevel(TransactionDefinition.ISOLATION_SERIALIZABLE);

TransactionalOperator serializableOperator =
    TransactionalOperator.create(transactionManager, definition);

Mono<Booking> result = serializableOperator.transactional(
    createBookingAndCheckCapacity(request)
);
```

`DefaultTransactionDefinition` lets you set isolation, timeout, and propagation. You can create a dedicated operator for a use case needing a different isolation level. In setups with multiple `ConnectionFactory` instances, choose the matching `ReactiveTransactionManager` for the database used by the publisher.

The requested isolation level must be supported by both driver and database. If unsupported, the transaction may fail on startup or when setting isolation. Some databases map multiple levels to the same behavior. Check driver documentation and verify with integration tests.

## 6. Example: Protecting Inventory with an Atomic Statement

Suppose inventory must never become negative. An error-prone approach is reading the quantity, checking in Java, and then updating:

```java
repository.findById(productId)
    .flatMap(product -> {
        if (product.getAvailable() >= quantity) {
            product.setAvailable(product.getAvailable() - quantity);
            return repository.save(product);
        }
        return Mono.error(new InsufficientStockException());
    });
```

Two requests could simultaneously read stock 5 and each try to buy 4. Both see sufficient stock and both compute a new value of 1. Without concurrency control on the update, the result may fail to reflect both sales.

A better approach is to let the database check the condition and update in the same statement:

```sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :productId
  AND available >= :quantity;
```

Then check the number of affected rows:

```java
Mono<Void> reserveStock(Long productId, int quantity) {
    if (quantity <= 0) {
        return Mono.error(new IllegalArgumentException("quantity must be positive"));
    }

    return databaseClient.sql("""
            UPDATE inventory
            SET available = available - :quantity
            WHERE product_id = :productId
              AND available >= :quantity
            """)
        .bind("quantity", quantity)
        .bind("productId", productId)
        .fetch()
        .rowsUpdated()
        .flatMap(updated -> updated == 1
            ? Mono.empty()
            : Mono.error(new InsufficientStockException()));
}
```

With this statement, two competing requests are serialized by the database on the target row. Only the request that still satisfies the condition succeeds in updating. Add `CHECK (available >= 0)` to enforce the invariant directly in the schema. This approach is usually simpler and more efficient than escalating an entire use case to `SERIALIZABLE` just to deduct stock.

## 7. Example: Conditional Update via Optimistic Locking

If multiple users can edit the same entity, `@Version` can detect when another transaction modified the row after it was read:

```java
@Table("product")
public class Product {
    @Id
    private Long id;

    private String name;

    @Version
    private Long version;
}
```

Spring Data Relational can include the version in the update condition and increment it when saving the entity. If the updated row count is not as expected because the version changed, the operation can emit `OptimisticLockingFailureException`.

Optimistic locking fits when conflicts are infrequent and the application can ask users to reload or retry the business action. It protects the versioned row itself. It does not automatically protect invariants spanning multiple distinct rows, such as total booked seats not exceeding room capacity if each request inserts or updates a separate booking row.

With hand-written SQL, do not assume `@Version` is automatically added to the statement. You must explicitly include `version = :expectedVersion` in `WHERE`, increment version, and check `rowsUpdated()`.

## 8. Example: Row Locking When Reading Before Deciding

Some business flows must read the current state, evaluate multiple conditions, and then update. If other transactions must not alter the row during that interval, pessimistic row locking can be used when supported by the database.

SQL example:

```sql
SELECT id, available
FROM inventory
WHERE product_id = :productId
FOR UPDATE;
```

`FOR UPDATE` asks the database to lock the selected row(s) until the transaction ends, according to database semantics. After reading and checking, the transaction updates the row and commits. Other transactions needing a conflicting lock may have to wait.

The locking query must run inside an active transaction. If the select and update run on two different connections or transactions, the lock does not protect the workflow. Keep transactions short, lock rows in a consistent order when multiple rows are needed to reduce deadlock risk, and verify the exact syntax and locking capabilities of the target database.

R2DBC does not have a single portable annotation equivalent to all JPA pessimistic locking mechanisms. With Spring Data R2DBC, it is usually expressed using explicit SQL via `DatabaseClient` or query mechanisms supported by the driver and database.

## 9. Example: Multi-Row Invariants

Suppose a room has a limit of 10 seats. Each booking creates a separate row. Two transactions both count existing bookings as 9, and each inserts one booking. If they only check `COUNT(*)` before inserting, both see one spot left and both insert, resulting in 11 bookings.

Several design options exist:

- Use a `room_capacity` row as a counter and update it atomically with a condition: `UPDATE room_capacity SET reserved = reserved + 1 WHERE room_id = :id AND reserved < capacity`. A booking is inserted only if the update succeeds; both operations run in the same transaction.
- Lock the room row with `SELECT ... FOR UPDATE`, check the seat count, and then insert the booking in the same transaction.
- Use `SERIALIZABLE` if the invariant is checked across a set of rows without a suitable constraint or atomic statement, while handling serialization failures with retries.
- Design alternative constraints or data models if the database can directly express the limit to be enforced.

Counting then inserting under `READ_COMMITTED` is insufficient to enforce the cap under contention. Raising isolation can be a solution, though an atomically updated counter row is often easier to observe and control.

## 10. When Is SERIALIZABLE Needed?

`SERIALIZABLE` is appropriate when correctness depends on a sequence of reads and writes across multiple rows or a data range, and cannot be adequately protected by constraints, atomic updates, or simple explicit locks.

For example, the rule "at least one doctor on the team must remain on call" depends on the state of multiple rows. If two concurrent transactions read the same snapshot and update two different rows, write skew can occur. `SERIALIZABLE` requires the database to guarantee an outcome equivalent to a serial order; a conflicting transaction may be aborted instead of allowing both to commit.

This means `SERIALIZABLE` does not simply mean "wait so everything runs one by one." The database may use locks or detect conflicts and return a serialization error. The application must be prepared to retry the entire transaction when encountering appropriate serialization/deadlock errors.

Before choosing `SERIALIZABLE`, evaluate:

- How frequently transactions touch the same data.
- Read volume and query predicate scope.
- Cost of retrying on conflict.
- Actual isolation behavior of the database.
- Ability to keep external side effects outside the transaction or emit them after commit.

## 11. Retrying When a Transaction Is Aborted Due to Conflict

At `SERIALIZABLE`, the database can refuse to commit a transaction to preserve serializability. This is not necessarily a programming bug; it can be a normal outcome when two transactions contend. You can retry the entire transaction with a bounded retry count and backoff.

Illustrative example:

```java
Mono<Booking> createWithRetry(BookingRequest request) {
    Mono<Booking> oneAttempt = transactionalOperator.transactional(
        createBookingAndValidateCapacity(request)
    );

    return oneAttempt.retryWhen(
        Retry.backoff(3, Duration.ofMillis(100))
            .filter(this::isSerializationFailure)
    );
}
```

`isSerializationFailure` must accurately identify errors raised by the driver/database or exceptions translated by Spring. Specific error codes and exception types differ across PostgreSQL, MySQL, SQL Server, and drivers. Do not retry every `DataAccessException`, because constraint errors, invalid data, or syntax errors will not resolve by retrying.

Place retry logic outside the transactional publisher so each re-subscription starts a fresh transaction. Retrying is safe only if the entire operation can be re-executed. Do not send emails, call payment APIs, or publish messages directly inside a retryable block; use an outbox or emit side effects after commit to avoid duplicate execution.

## 12. Isolation Does Not Replace Constraints

Even when a service uses `SERIALIZABLE`, constraints remain essential for enforcing data conditions that the database can express:

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    tenant_id UUID NOT NULL,
    email VARCHAR(320) NOT NULL,
    balance NUMERIC(19, 2) NOT NULL CHECK (balance >= 0),
    CONSTRAINT uk_account_tenant_email UNIQUE (tenant_id, email)
);
```

In this example:

- `PRIMARY KEY` guarantees unique identity.
- `UNIQUE (tenant_id, email)` ensures emails do not duplicate within a tenant.
- `CHECK (balance >= 0)` ensures balances cannot be negative.

These constraints protect data regardless of whether changes come from Spring Data R2DBC, another application, an operational script, or a batch import. Isolation only governs how transactions interact; it does not replace row-level validity enforcement.

## 13. Be Careful with Nested Transactions and Propagation

A `@Transactional` method can call another transactional method. With the default `REQUIRED` propagation, the operation usually joins the existing transaction rather than creating an independent one. Therefore, declaring a different isolation level on a method invoked inside an existing transaction does not necessarily start a new transaction with the new isolation level.

If a use case genuinely needs an independent transaction, `REQUIRES_NEW` has different semantics and may require an additional connection. Do not use it merely to "upgrade isolation" for a piece of code without evaluating its impact on atomicity and connection pooling.

With `TransactionalOperator`, where the publisher is wrapped determines the transaction scope. When an operator is applied inside an existing transaction, behavior depends on configured propagation. Design clear boundaries and avoid unnecessary nested transactions.

## 14. Choices by Database and R2DBC Driver

Isolation is a standard concept, but implementation details vary:

- A database may support certain isolation levels while mapping others to the closest available level.
- `REPEATABLE_READ` may prevent phantoms in one database while not guaranteeing the same behavior in another.
- `SERIALIZABLE` may use locking or MVCC/SSI, leading to different wait behaviors and conflict error types.
- The R2DBC driver must pass Spring's isolation request to the database. Setting isolation may be constrained by the driver or connection state.
- Some databases allow changing isolation only at transaction start or have special rules for read-only transactions.

When switching databases or upgrading driver versions, re-run integration tests for contention and isolation. Do not merely check that the application starts or that annotations do not throw errors.

## 15. Testing Invariants Under Contention

A sequentially run unit test cannot prove an invariant holds when two transactions run concurrently. Have integration tests against the target database/driver using two threads or two independent connections to reproduce contention.

Examples of scenarios to test:

| Invariant | Contention scenario | Expected outcome |
|---|---|---|
| Non-negative stock | Two requests simultaneously buy quantities exceeding total stock | Only an eligible request succeeds; `available` is non-negative. |
| Unique email | Two transactions simultaneously insert the same tenant/email | One insert succeeds; the other receives a unique constraint error. |
| Optimistic locking | Two transactions read the same version and both save | One update succeeds; the stale update receives a conflict. |
| Capacity limit | Two transactions simultaneously book the last spot | Only one booking is accepted. |
| Multi-row invariant | Two transactions update different rows while jointly violating the overall condition | Database prevents concurrent commit, or application uses appropriate locks/constraints. |

Tests should synchronize their starting point so both transactions truly contend, and check final row counts and error states. Using mock repositories only tests publisher handling logic and proves nothing about database isolation semantics.

## 16. Process for Choosing Isolation Levels

You can apply the following sequence to each use case:

1. Write down the business invariant as a testable condition.
2. Identify the rows and data ranges that multiple transactions may read/write concurrently.
3. Check whether it can be enforced with primary keys, unique constraints, foreign keys, or check constraints.
4. Check whether read-modify-write logic can be turned into a single atomic update statement.
5. If contention targets the same row, consider `@Version` or `SELECT ... FOR UPDATE`.
6. If the invariant spans multiple rows and risks write skew, evaluate `SERIALIZABLE` or locking a representative scope row.
7. Configure isolation at the proper reactive transaction boundary and verify driver/database support.
8. Determine whether conflict errors are retryable; retry the entire transaction and keep external side effects out of the retryable block.
9. Write concurrent integration tests against the target database and monitor deadlocks, serialization failures, lock waits, and retry rates.

Isolation levels should be chosen based on the invariant to protect and the anomalies that could break it. Use constraints and atomic operations for conditions that can be expressed directly; use optimistic or pessimistic locking when specific conflict control is needed; choose `SERIALIZABLE` when rules span multiple rows or read/write ranges and no simpler mechanism provides enough protection. Finally, always verify behavior on the real database and R2DBC driver, because identical isolation names do not guarantee identical implementations across systems.
