# Optimistic Locking, Pessimistic Locking, and Deadlock Errors

When multiple requests read and update the same data concurrently, the application must control contention to avoid overwriting each other's changes or holding resources too long. Spring Data JPA builds on JPA and database locking mechanisms to support two main strategies:

- **Optimistic locking:** allows multiple transactions to read the same data; on update, checks whether the data has changed since it was read.
- **Pessimistic locking:** locks data rows in the database so other transactions cannot perform conflicting operations until the lock is released.

Deadlock happens when transactions hold locks that other transactions need, forming a wait cycle. The database usually detects the cycle and aborts one transaction as the victim. The application must recognize the exact error type, design consistent access ordering, and only retry after the old transaction has ended.

## 1. Understanding Update Conflicts and Lost Updates

Suppose inventory has 10 items remaining. Two requests both read quantity 10:

1. Transaction A reads 10 and wants to subtract 7.
2. Transaction B also reads 10 and wants to subtract 6.
3. A writes 3.
4. B writes 4 based on the stale value 10.

Without concurrency control, one update can overwrite the other. The final result is 3 or 4 depending on write order, while both requests were processed as if both succeeded. This is a lost update.

Not all concurrent access is an error. Many transactions can safely read the same data. Problems arise when they concurrently modify data and results must preserve business invariants—such as non-negative inventory, balances not losing updates, or order statuses not moving backward.

## 2. Optimistic Locking with @Version

### Mechanism

Optimistic locking assumes conflicts are infrequent. An entity has a version field annotated with `@Version`. When the provider updates the entity, it uses the previously read version value as a condition in the SQL statement and increments the version if the update succeeds.

Illustrative SQL concept:

```sql
UPDATE inventory
   SET available = 3,
       version = 8
 WHERE id = 100
   AND version = 7;
```

If another transaction has already updated the row and the current version is no longer 7, the statement affects 0 rows. The provider detects the conflict and throws an optimistic locking error. Consequently, an update based on a stale snapshot cannot silently overwrite newer data.

### Declaring Version in an Entity

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Inventory {

    @Id
    private Long id;

    private int available;

    @Version
    private Long version;

    protected Inventory() {
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (available < quantity) {
            throw new IllegalStateException("Insufficient inventory");
        }
        available -= quantity;
    }

    public int getAvailable() {
        return available;
    }
}
```

Common portable version types include `int`, `Integer`, `short`, `Short`, `long`, `Long`, and `java.sql.Timestamp`. Use a single version field on the entity and let the JPA provider manage its value; do not manually increment version in ordinary setters.

### Service Updating with Optimistic Locking

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository inventoryRepository;

    public InventoryService(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void reserve(Long inventoryId, int quantity) {
        Inventory inventory = inventoryRepository.findById(inventoryId)
            .orElseThrow(() -> new IllegalArgumentException("Inventory not found"));

        inventory.reserve(quantity);

        // Entity is managed; dirty checking writes changes on flush/commit.
    }
}
```

Two transactions can both load an entity with the same version. The transaction that commits first updates successfully and increments the version. The other transaction will hit an optimistic locking failure at flush or commit.

Do not check for errors only around the setter call. Conflicts are usually detected only when the provider issues SQL, i.e., at `flush()` or transaction commit.

### Common Exceptions

At the JPA layer, the error is typically `jakarta.persistence.OptimisticLockException`. After passing through Spring repository exception translation, the application may receive Spring DAO types such as `OptimisticLockingFailureException` or `ObjectOptimisticLockingFailureException`, depending on the execution path and provider.

This error means the transaction's snapshot is no longer valid for updating. Do not automatically write back the old value or replay the same detached object. Reload the latest state, re-evaluate business rules, and decide whether to retry or report a conflict to the user.

### Optimistic Lock Modes

JPA also provides lock modes:

- `LockModeType.OPTIMISTIC`: requests a version check to guard against conflicting updates.
- `LockModeType.OPTIMISTIC_FORCE_INCREMENT`: in addition to the optimistic check, requires incrementing the version even when no ordinary field changed.

This can be used when a business operation needs to mark an aggregate/entity as concurrency-checked even if scalar data did not change. There is no need to use force increment for every read.

## 3. Pessimistic Locking with LockModeType

### Mechanism

Pessimistic locking asks the database to lock resources immediately inside the transaction, typically the queried rows. Other transactions may have to wait, time out, or receive an error depending on lock type, isolation level, and database.

Common lock modes:

- `PESSIMISTIC_READ`: requests a read lock to prevent conflicting updates while the lock is held.
- `PESSIMISTIC_WRITE`: requests a write lock, typically used when preparing to modify data and needing to serialize writers.
- `PESSIMISTIC_FORCE_INCREMENT`: combines pessimistic locking with incrementing the version on a versioned entity.

How the database implements locks specifically depends on provider, dialect, engine, and query type. For example, on supporting databases, `PESSIMISTIC_WRITE` is typically implemented with a statement similar to `SELECT ... FOR UPDATE`.

### Declaring @Lock in Spring Data JPA

Spring Data JPA provides the `@Lock` annotation to attach a lock mode to a query method:

```java
import java.util.Optional;

import jakarta.persistence.LockModeType;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<Inventory, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from Inventory i where i.id = :id")
    Optional<Inventory> findByIdForUpdate(@Param("id") Long id);
}
```

Service using this method within a transaction:

```java
@Service
public class InventoryService {

    private final InventoryRepository inventoryRepository;

    public InventoryService(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public void reserveWithLock(Long id, int quantity) {
        Inventory inventory = inventoryRepository.findByIdForUpdate(id)
            .orElseThrow(() -> new IllegalArgumentException("Inventory not found"));

        inventory.reserve(quantity);
    }
}
```

The transaction acquires the lock, checks the quantity, updates the entity, and holds the lock until the transaction finishes. Other requests needing a conflicting lock on the same row must wait or fail per timeout/lock policy.

A repository method acquiring a lock must run inside an active transaction. Placing the `@Transactional` boundary on the service is usually appropriate because the locked read, validation, and update must share the same transaction.

### When to Use Pessimistic Locking?

Suitable when:

- Conflicts occur frequently.
- A transaction needs to read and update a resource without letting multiple writers pass through the processing step concurrently.
- The operation is short and can hold locks briefly.
- Business rules require serializing updates, such as allocating a scarce resource.

Unsuitable when transactions are long-running, call external services while holding locks, or load more rows than necessary. Those cases increase wait times and deadlock risk.

### Lock Timeout

You can configure a lock timeout using a JPA query hint, for example:

```java
import jakarta.persistence.QueryHint;

import org.springframework.data.jpa.repository.QueryHints;

@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(
    @QueryHint(
        name = "jakarta.persistence.lock.timeout",
        value = "3000"
    )
)
@Query("select i from Inventory i where i.id = :id")
Optional<Inventory> findByIdForUpdate(@Param("id") Long id);
```

The example value is 3000 milliseconds. Hint support and enforcement vary across JPA providers and databases; some systems cannot guarantee the exact requested timeout. Inspect actual SQL and provider behavior.

Lock timeout differs from deadlock: timeout means the transaction could not acquire a lock within the allowed time; deadlock means a wait cycle exists among transactions. Both can be translated into Spring DAO locking exceptions.

## 4. Comparing Optimistic and Pessimistic Locking

| Criterion | Optimistic locking | Pessimistic locking |
|---|---|---|
| How it works | Detects conflicts at update/flush/commit using version | Holds database locks during the transaction |
| Suitable scenarios | Low contention, read-heavy, short transactions | High contention, writers need serialization |
| Impact on conflict | One transaction fails and must re-process business logic | Other transactions wait, time out, or get rejected |
| Cost | Avoids holding locks during reads; may require retry handling | Holds locks and increases wait times |
| Dependencies | `@Version` field and provider | Lock mode, transaction, database, and dialect |
| Primary risk | Users receive conflicts when data changes concurrently | Lock contention, timeouts, and deadlocks |

No single strategy is best for every entity. Choose based on contention frequency, transaction duration, invariant criticality, and how conflicts can be handled in business logic.

## 5. What is a Deadlock?

A deadlock occurs when a group of transactions hold locks that other transactions in the group need, creating a wait cycle that cannot make progress on its own.

Example:

- Transaction A locks row X, then needs to lock row Y.
- Transaction B locks row Y, then needs to lock row X.
- A waits for B to release Y.
- B waits for A to release X.

```text
Transaction A                  Transaction B
-------------                  -------------
LOCK row X                     LOCK row Y
REQUEST row Y  ------------->  holding row Y
holding row X  <------------- REQUEST row X
       \                           /
        \_______ wait cycle _______/
```

Databases usually have a deadlock detector. When a cycle is detected, the database picks one transaction as the victim and rolls it back to free locks for the remaining transaction. The victim transaction may receive a deadlock error from JDBC/provider, translated by Spring into a data access exception.

Deadlock does not simply mean two transactions waited on each other for too long. A lock timeout can happen without any cycle. Inspect database messages and logs to tell them apart.

## 6. Common Causes of Deadlocks

### Accessing Multiple Rows in Different Orders

This is the classic cause: transaction A locks X then Y, while transaction B locks Y then X. Standardizing lock order greatly reduces the risk of forming a cycle.

### Transactions Holding Locks Too Long

A transaction holding locks while:

- Calling HTTP or external services.
- Waiting for user input.
- Processing files or performing heavy computation.
- Running many unrelated queries.
- Processing overly large batches.

The longer locks are held, the higher the chance of overlapping with another transaction.

### Queries Missing Indexes or Wide Lock Scopes

A query without a proper index may scan many rows, increasing execution time and, depending on the engine, locking far more resources than expected. Proper query predicates and indexes help the database locate target rows quickly.

### Updating Multiple Tables or Relationships in Different Orders

Transactions modifying the same entities and related associations in different sequences can create lock cycles. Cascades, triggers, and foreign keys can also cause the database to acquire additional locks beyond the statements directly visible in Java.

### Lock Escalation and Database-Specific Behavior

Different engines have different locking strategies, lock granularities, and deadlock detection mechanisms. Do not deduce exact lock scopes from JPA annotations alone; check the actual SQL and the documentation for your database.

## 7. Diagnosing Deadlocks and Locking Errors

### Step 1: Identify the Root Exception

Possible exceptions include:

- `OptimisticLockException` in JPA or a Spring-translated optimistic locking exception.
- `PessimisticLockException` when a lock failure aborts the transaction.
- `LockTimeoutException` when waiting for a lock exceeds the limit; per JPA, a timeout may not force a full transaction rollback in all cases, depending on the error type and provider.
- Spring DAO exceptions such as `PessimisticLockingFailureException`, `CannotAcquireLockException`, or related subtypes.
- JDBC/SQL exceptions carrying database error codes and deadlock messages.

Exact exception types depend on the database driver, provider, and Spring exception translation. Log the full exception chain and SQL state/vendor error code instead of logging only the outermost message.

### Step 2: Identify SQL and Lock Acquisition Order

Enable SQL and transaction logging during investigation:

```yaml
logging:
  level:
    org.springframework.transaction: TRACE
    org.springframework.orm.jpa: DEBUG
    org.hibernate.SQL: DEBUG
```

If bind parameters are needed, enable the Hibernate bind parameter logger corresponding to your version; logging sensitive values must follow data security policies.

Correlate transaction timestamps, SQL update/select statements, lock requests, and rollback timing. Focus on the rows and tables accessed concurrently by both transactions.

### Step 3: Inspect the Database

Deadlock diagnostics provided by the database are often more informative than Java stack traces because the database sees the entire lock cycle.

Examples:

- **MySQL/InnoDB:** inspect `SHOW ENGINE INNODB STATUS` for the most recent deadlock; on supporting versions, also check `performance_schema.data_locks` and `data_lock_waits`.
- **PostgreSQL:** inspect `pg_stat_activity`, `pg_locks`, and blocking relationships via system views; server logs may contain detailed deadlock graphs.

Syntax and privileges depend on database version, configuration, and permissions. Do not run diagnostic queries that could expose sensitive data in production environments.

### Step 4: Reproduce with a Concurrency Test

Use two independent threads/transactions, two real database connections, and barriers/latches to control operation ordering. Do not share one EntityManager across two threads. The test should verify:

- Both transactions actually run concurrently.
- Lock ordering reproduces the failure scenario.
- One transaction receives the expected deadlock/lock failure.
- The database is not left with partial data state.
- Final state satisfies business invariants.

Sequential tests or tests wrapped in a single outer test transaction will not reproduce contention between two independent transactions.

## 8. How to Prevent Deadlocks

1. **Standardize lock ordering:** all business flows updating multiple rows should access them in the same deterministic order, such as sorting IDs ascending before locking.
2. **Keep transactions short:** include only database operations requiring atomicity inside the transaction.
3. **Never call external services while holding locks:** send HTTP requests, emails, or process files after the transaction ends, or use an outbox.
4. **Use appropriate indexes:** optimize WHERE conditions, JOINs, and lock queries to avoid wide scans.
5. **Lock narrowly:** select only needed rows; avoid pessimistic locks on broad queries.
6. **Reduce batch sizes:** split large batches into smaller chunks with clear transaction boundaries when business rules permit.
7. **Keep multi-table update order consistent:** use cases touching multiple tables should follow a uniform sequence.
8. **Set reasonable timeouts:** cap wait times so requests do not hang indefinitely, and monitor timeouts to spot contention.
9. **Never share EntityManager or transactions across threads:** EntityManager is not thread-safe; each transaction/thread needs proper scoping.

## 9. Retrying After Optimistic Lock, Lock Timeout, or Deadlock

Retries can work for transient contention errors, but must occur at the proper transaction boundary.

### Safe Retry Principles

- The previous transaction must roll back/finish before retrying.
- Each attempt must re-read fresh data in a new transaction.
- Re-run all business logic and re-check invariants from the beginning.
- Limit attempt counts; use backoff and jitter to avoid repeated collisions.
- Retry only errors identified as transient.
- Ensure operations are idempotent or protected against duplicate processing.
- Never retry indefinitely and never retry business errors like insufficient inventory.

Specifically, never catch an optimistic locking exception and keep using stale entities in the same transaction. The transaction may already be marked rollback-only; the data and persistence context are no longer valid to proceed.

### Structuring Retries Outside the Transaction

An easy-to-control pattern puts the retry loop in a non-transactional facade bean; each call invokes a worker service with its own `@Transactional`. When the worker throws, the worker's transaction ends/rolls back before the caller decides to retry.

Illustrative structure:

```java
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.dao.PessimisticLockingFailureException;
import org.springframework.stereotype.Service;

@Service
public class InventoryRetryFacade {

    private final InventoryTransactionService transactionService;

    public InventoryRetryFacade(
            InventoryTransactionService transactionService) {
        this.transactionService = transactionService;
    }

    // Do not put @Transactional on this facade.
    public void reserve(Long id, int quantity) {
        int maxAttempts = 3;

        for (int attempt = 1; ; attempt++) {
            try {
                transactionService.reserveOnce(id, quantity);
                return;
            } catch (OptimisticLockingFailureException
                     | PessimisticLockingFailureException ex) {
                if (attempt >= maxAttempts) {
                    throw ex;
                }
                waitBeforeRetry(attempt);
            }
        }
    }

    private void waitBeforeRetry(int attempt) {
        try {
            Thread.sleep(100L * attempt);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Retry interrupted", ex);
        }
    }
}
```

The worker must be a separate Spring bean:

```java
@Service
public class InventoryTransactionService {

    private final InventoryRepository repository;

    public InventoryTransactionService(InventoryRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void reserveOnce(Long id, int quantity) {
        Inventory inventory = repository.findById(id)
            .orElseThrow(() -> new IllegalArgumentException("Not found"));

        inventory.reserve(quantity);
    }
}
```

This is an illustrative skeleton. In production, backoff should include jitter and metrics; catch only exceptions known to be transient. Spring-translated exception names can vary by provider/database. Separating the facade and transactional worker into two beans places the retry boundary outside the transaction and prevents self-invocation from bypassing the proxy.

### Retries and External Side Effects

Never send emails, charge payment gateways, or call non-idempotent APIs inside a block that can be retried. If a transaction rolls back after a side effect already occurred, retrying can duplicate the side effect. Use idempotency keys, outbox patterns, or dispatch side effects after commit to stay safe.

With optimistic locking, after reloading fresh data, the original request may no longer be valid. For instance, stock may now be insufficient; in that case return a business error rather than retrying further.

## 10. Bulk Updates and Limitations of @Version

JPQL bulk updates/deletes and native SQL operate directly on the database and do not perform per-entity dirty checking like ordinary entity operations. Do not assume bulk updates automatically check and increment `@Version` the way the provider does when updating a managed entity.

For example, a bulk update with a version check must be written explicitly:

```sql
UPDATE inventory
   SET available = :newAvailable,
       version = version + 1
 WHERE id = :id
   AND version = :expectedVersion;
```

If affected rows equals 0, either the record does not exist or the version changed; the application must distinguish these per business requirements. After a bulk update, the persistence context may contain stale entities; refresh or clear in a controlled way before continuing to use those entities.

If you want JPA's automatic optimistic locking, prefer updating managed entities with a `@Version` field. If using bulk SQL for performance, manually implement the version predicate, increment the version, check the affected row count, and synchronize the persistence context.

## 11. Choosing a Strategy by Scenario

| Scenario | Suggested strategy | Reason |
|---|---|---|
| Infrequent concurrent writes, read-heavy | Optimistic locking with `@Version` | Avoids holding locks during reads |
| Many requests updating the same row in short bursts | Consider `PESSIMISTIC_WRITE` | Serializes writers at the database |
| Updating multiple rows in one business flow | Consistent lock order, short transactions; pick optimistic/pessimistic by contention | Prevents wait cycles |
| Rare deadlocks that can be retried | Bounded retry after rollback | Database already aborted the victim transaction |
| Optimistic lock error because someone else updated first | Reload and re-evaluate business rules | Input snapshot is stale |
| Insufficient inventory or business rule violation | Never retry blindly | This is not a transient conflict |

## 12. Diagnostic Checklist

When encountering locking errors or deadlocks in Spring Data JPA:

1. Record the root exception, SQL state, vendor error code, and transaction ID/correlation ID.
2. Determine whether the error is an optimistic conflict, lock timeout, deadlock, or another constraint error.
3. Identify which transaction holds locks and which transaction is waiting.
4. Check whether the entity has `@Version` or the repository query uses `@Lock`.
5. Inspect actual SQL, WHERE predicates, indexes, and row/table access order.
6. Check whether the transaction holds locks while calling external APIs or performing slow work.
7. Choose the resolution: reload and re-validate business logic, adjust lock strategy, optimize queries, or retry after rollback.
8. Write a concurrency integration test to confirm final data still satisfies invariants.

## Conclusion

Optimistic locking uses `@Version` to detect when a transaction updates based on stale data. Pessimistic locking uses `LockModeType` and `@Lock` to have the database hold locks within a transaction. Deadlock is a wait cycle between transactions, usually detected by the database which rolls back one transaction.

Select a locking strategy matching real contention levels, keep transactions short, standardize resource access ordering, and inspect root exceptions. If retrying is appropriate, only retry after the previous transaction has ended, in a fresh transaction, with bounded attempts and full re-validation of business rules.
