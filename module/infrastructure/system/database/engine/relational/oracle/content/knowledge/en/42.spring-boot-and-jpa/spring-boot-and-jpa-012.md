# Optimistic Locking, Pessimistic Locking, and Timeouts

## 1. Why Does an Application Need Locking Mechanisms?

In a Spring Boot and JPA application, multiple requests can read and update the same record nearly simultaneously. Without concurrency control, one request can overwrite another request's changes or read stale state that is no longer valid.

For example, an account has a balance of 1,000. Two requests both read 1,000. Request A subtracts 300 and writes 700; Request B subtracts 200, still computing from the stale 1,000, and writes 800. If both writes succeed, the final balance is 800 instead of 500. This is a lost update.

Locking coordinates concurrent transactions. JPA provides two primary strategies:

- **Optimistic locking** assumes conflicts are rare. Multiple transactions can read the same data; on write, the provider verifies whether the data has changed since it was read.
- **Pessimistic locking** assumes contention is likely. A transaction asks the database to lock the data before or during processing so other transactions cannot update/delete the locked rows in conflicting ways.

Timeouts bound how long operations wait to acquire locks or execute transactions/queries. Timeouts keep systems from hanging indefinitely, though you must distinguish lock timeout, query timeout, transaction timeout, and connection-pool timeout because they apply at different layers.

## 2. Optimistic Locking with @Version

### 2.1. The Version Column Mechanism

JPA supports optimistic locking through the `@Version` annotation. Each entity has a version attribute managed by the provider. When reading the entity, Hibernate records the current version in the persistence context. When updating, Hibernate generates SQL with a predicate checking the old version.

Entity example:

```java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "PRODUCTS")
public class Product {
    @Id
    private Long id;

    @Column(nullable = false)
    private String name;

    @Column(nullable = false)
    private Integer quantity;

    @Version
    @Column(nullable = false)
    private Long version;

    // getters/setters
}
```

The Oracle schema needs a matching version column:

```sql
CREATE TABLE products (
    id       NUMBER(19) PRIMARY KEY,
    name     VARCHAR2(200) NOT NULL,
    quantity NUMBER(10) NOT NULL,
    version  NUMBER(19) NOT NULL
);
```

Version values are managed by Hibernate; never increment the version manually in business code when using `@Version`. On insert, the provider initializes the version per its strategy; on update, the provider increments the version when a version check applies.

### 2.2. Version-Checked UPDATE SQL

Suppose an entity is read with `id=10`, `quantity=20`, `version=4`. On update, the SQL takes the general form:

```sql
UPDATE products
SET quantity = 18,
    version = 5
WHERE id = 10
  AND version = 4;
```

If another transaction already updated the row and bumped the version to 5, the SQL above updates zero rows. Hibernate detects that the affected row count differs from expected and throws an optimistic locking conflict.

Thus, two transactions can both read version 4, yet only one succeeds in updating. The other must handle the conflict rather than silently overwriting newer data.

### 2.3. When Are Conflicts Detected?

Conflicts do not necessarily surface immediately at the setter or `repository.save()` call. JPA may defer SQL until flush. Consequently, exceptions can occur at:

- Explicit `EntityManager.flush()`.
- Automatic Hibernate flush before a query or commit.
- Transaction commit when the provider performs its final flush.

Example:

```java
@Transactional
public void decreaseStock(Long productId, int amount) {
    Product product = entityManager.find(Product.class, productId);
    if (product.getQuantity() < amount) {
        throw new IllegalStateException("Insufficient stock");
    }

    product.setQuantity(product.getQuantity() - amount);
    // Hibernate performs version check at flush/commit.
}
```

You can call `flush()` explicitly to surface conflicts before subsequent steps, though flush does not commit the transaction. The transaction can still roll back afterward.

### 2.4. Handling OptimisticLockException

On a version mismatch, JPA throws `OptimisticLockException`. Spring/Hibernate translates this into Spring's exception hierarchy, such as `ObjectOptimisticLockingFailureException` or `OptimisticLockingFailureException`.

Example handling at the service/API layer:

```java
@RestControllerAdvice
public class ApiExceptionHandler {
    @ExceptionHandler(OptimisticLockingFailureException.class)
    ResponseEntity<String> handleOptimisticConflict(
            OptimisticLockingFailureException exception) {
        return ResponseEntity.status(HttpStatus.CONFLICT)
                .body("Data has been updated by someone else. Please reload and try again.");
    }
}
```

Depending on exact Spring exception translation, you may also need to handle JPA/Hibernate exceptions at the appropriate layer. Never catch all `RuntimeException`s and return HTTP 409, as that hides unrelated bugs.

A transaction encountering an optimistic conflict generally cannot proceed as if nothing happened. Roll back the current transaction; to retry, start a fresh transaction and re-read the latest data.

### 2.5. OPTIMISTIC and OPTIMISTIC_FORCE_INCREMENT

JPA defines optimistic lock modes:

| Lock mode | Meaning |
|---|---|
| `OPTIMISTIC` | Verifies version when the transaction completes to detect concurrent entity modifications |
| `OPTIMISTIC_FORCE_INCREMENT` | In addition to optimistic checking, forces the entity's version to increment even if no ordinary field changed |

Example:

```java
Product product = entityManager.find(
        Product.class,
        productId,
        LockModeType.OPTIMISTIC
);
```

And forcing a version increment:

```java
entityManager.lock(product, LockModeType.OPTIMISTIC_FORCE_INCREMENT);
```

`OPTIMISTIC_FORCE_INCREMENT` is useful when a business event must invalidate stale reads—such as an aggregate root undergoing a logical state transition without modifying its own columns. Use deliberately, as bumping the version causes concurrent transactions holding stale reads to conflict.

The older `READ` and `WRITE` constants in `LockModeType` are legacy aliases for `OPTIMISTIC` and `OPTIMISTIC_FORCE_INCREMENT`; prefer the newer names for clarity.

## 3. Pessimistic Locking with JPA

### 3.1. Database Locking Mechanism

Pessimistic locking asks the database to acquire row locks. With Oracle, Hibernate typically emits `SELECT ... FOR UPDATE` for `PESSIMISTIC_WRITE`.

```sql
SELECT id, name, quantity, version
FROM products
WHERE id = 10
FOR UPDATE;
```

While transaction A holds the row lock, transaction B attempting to update or acquire a conflicting lock on the same row must wait, fail with a timeout, or skip the row depending on the strategy used. Row locks are typically held until commit or rollback.

Pessimistic locking fits read-then-update operations where two transactions cannot safely compute from stale reads, such as reserving inventory or claiming a worker job. However, long locks reduce concurrency and risk deadlocks.

### 3.2. PESSIMISTIC_READ

`PESSIMISTIC_READ` requests a lock preventing other transactions from updating/deleting the read data per JPA semantics. The database/provider may use a shared lock or a stronger lock if required.

```java
Product product = entityManager.find(
        Product.class,
        productId,
        LockModeType.PESSIMISTIC_READ
);
```

Do not assume `PESSIMISTIC_READ` always emits one fixed Oracle lock type. The provider and database determine exact SQL; in some setups a stronger lock is used to satisfy JPA semantics.

### 3.3. PESSIMISTIC_WRITE

`PESSIMISTIC_WRITE` requests a lock strong enough to prevent other transactions from modifying/deleting locked rows until the current transaction finishes:

```java
Product product = entityManager.find(
        Product.class,
        productId,
        LockModeType.PESSIMISTIC_WRITE
);

if (product.getQuantity() < amount) {
    throw new IllegalStateException("Insufficient stock");
}

product.setQuantity(product.getQuantity() - amount);
```

This code must run inside a transaction. Without an active transaction, providers throw an error because pessimistic locks need a transaction to hold the lock until completion.

### 3.4. PESSIMISTIC_FORCE_INCREMENT

`PESSIMISTIC_FORCE_INCREMENT` combines a pessimistic lock with incrementing the version of a versioned entity. It helps when you need an immediate row lock while also bumping the version so optimistic readers detect the change.

```java
Product product = entityManager.find(
        Product.class,
        productId,
        LockModeType.PESSIMISTIC_FORCE_INCREMENT
);
```

Use only when the entity is versioned and business rules need both behaviors. It is not the default choice for routine updates.

### 3.5. @Lock in Spring Data JPA

Spring Data JPA lets you attach lock modes to repository queries via `@Lock`:

```java
public interface ProductRepository extends JpaRepository<Product, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select p from Product p where p.id = :id")
    Optional<Product> findByIdForUpdate(@Param("id") Long id);
}
```

The service invokes the method inside a transaction:

```java
@Service
public class InventoryService {
    private final ProductRepository productRepository;

    @Transactional
    public void reserve(Long productId, int amount) {
        Product product = productRepository.findByIdForUpdate(productId)
                .orElseThrow();

        if (product.getQuantity() < amount) {
            throw new IllegalStateException("Insufficient stock");
        }

        product.setQuantity(product.getQuantity() - amount);
    }
}
```

Spring Data JPA forwards the lock mode to the JPA provider; Hibernate generates Oracle-appropriate SQL. Never put `@Lock` on a repository method and call it outside a transaction if the lock must span the check and update.

## 4. Choosing Optimistic vs. Pessimistic Locking

| Criterion | Optimistic | Pessimistic |
|---|---|---|
| Assumption | Conflicts are rare | Significant contention is likely |
| Control mechanism | Compares version at write/completion | Acquires database locks on rows |
| Wait behavior | No row-lock wait during normal reads; may fail at flush/commit | May wait on locks, time out, or fail immediately |
| Throughput | High when conflicts are low | Can drop when many transactions contend on the same rows |
| Retries | Typically re-reads and retries in a new transaction | May retry on lock timeout/deadlock per policy |
| Best fit | CRUD, low-contention updates | High-contention inventory, queues, job dispatching |

No single strategy fits an entire application. You can use optimistic locking for most entities and reserve pessimistic locking for sensitive operations. For instance, customer profile editing suits optimistic locking, whereas dispatching a job to a worker may call for pessimistic locking or `SKIP LOCKED`.

## 5. Lock Timeouts in JPA

### 5.1. The jakarta.persistence.lock.timeout Hint

JPA defines the `jakarta.persistence.lock.timeout` hint to request a wait limit in milliseconds when acquiring pessimistic locks.

EntityManager example:

```java
Map<String, Object> hints = Map.of(
        "jakarta.persistence.lock.timeout", 3000
);

Product product = entityManager.find(
        Product.class,
        productId,
        LockModeType.PESSIMISTIC_WRITE,
        hints
);
```

Or on a query:

```java
Product product = entityManager.createQuery(
        "select p from Product p where p.id = :id", Product.class)
    .setParameter("id", productId)
    .setLockMode(LockModeType.PESSIMISTIC_WRITE)
    .setHint("jakarta.persistence.lock.timeout", 3000)
    .getSingleResult();
```

In Hibernate 5/older JPA, the property uses `javax.persistence.lock.timeout`; Hibernate 6/7 and Jakarta Persistence use `jakarta.persistence.lock.timeout`. Match the hint name to your application's JPA API.

This is a standard JPA-level hint. Providers and databases may have implementation limits; consult Hibernate documentation and inspect generated SQL. Do not assume all JDBC drivers and databases enforce timeouts identically.

### 5.2. Timeouts with Spring Data JPA

Attach locks and query hints on repository methods:

```java
public interface ProductRepository extends JpaRepository<Product, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @QueryHints({
        @QueryHint(
            name = "jakarta.persistence.lock.timeout",
            value = "3000"
        )
    })
    @Query("select p from Product p where p.id = :id")
    Optional<Product> findForUpdate(@Param("id") Long id);
}
```

The value `3000` represents 3,000 milliseconds per the JPA hint. If Hibernate/Oracle dialect translates the hint into Oracle's `WAIT` clause, inspect the generated SQL and verify behavior on your exact version. Some providers may ignore or round this hint differently.

### 5.3. Spring Transaction Timeout Differs from Lock Timeout

Spring's `@Transactional(timeout = ...)` sets a transaction time limit in seconds (depending on transaction manager and integration):

```java
@Transactional(timeout = 10)
public void reserve(Long productId, int amount) {
    // Business operation
}
```

This is not equivalent to `jakarta.persistence.lock.timeout`. Transaction timeout governs the entire transaction; lock timeout governs waiting to acquire a specific lock. Transaction managers may propagate timeouts to JDBC/providers, but never treat them as interchangeable.

### 5.4. Query Timeout and Connection Timeout

Commonly confused timeouts:

| Timeout | Scope | Example Configuration |
|---|---|---|
| Lock timeout | Waiting to acquire a lock | `jakarta.persistence.lock.timeout` |
| Transaction timeout | Entire transaction | `@Transactional(timeout = 10)` |
| Query timeout | SQL execution duration | `jakarta.persistence.query.timeout`, `Query.setHint`, or JDBC `setQueryTimeout` |
| Connection acquisition timeout | Waiting to borrow a connection from pool | HikariCP/UCP configuration |
| Network/socket timeout | Waiting for network I/O | JDBC driver/network properties |

Query timeout example:

```java
List<Product> products = entityManager.createQuery(
        "select p from Product p where p.quantity < :threshold", Product.class)
    .setParameter("threshold", 5)
    .setHint("jakarta.persistence.query.timeout", 5000)
    .getResultList();
```

A query timeout does not necessarily release all locks or terminate the transaction immediately across all providers. When a query times out, handle the exception and roll back the transaction per business boundaries.

## 6. Oracle Locking: NOWAIT, WAIT, and SKIP LOCKED

Oracle supports clauses on `SELECT ... FOR UPDATE` to control behavior when target rows are already locked by another transaction.

### 6.1. Default: Wait for Lock

```sql
SELECT id, quantity
FROM products
WHERE id = :id
FOR UPDATE;
```

If another transaction holds a conflicting lock, the statement waits until the lock is released. Once the holder commits or rolls back, the waiting statement proceeds and acquires the lock if the row still matches.

### 6.2. NOWAIT

```sql
SELECT id, quantity
FROM products
WHERE id = :id
FOR UPDATE NOWAIT;
```

If the row is already locked, Oracle errors immediately instead of waiting. On Oracle, the typical error is `ORA-00054: resource busy and acquire with NOWAIT specified or timeout expired`.

`NOWAIT` fits when the application wants to reply quickly with "currently busy" instead of stalling requests. However, do not turn every `ORA-00054` into a 500 system error; return HTTP 409/423 or a retry prompt depending on business semantics.

### 6.3. WAIT n

```sql
SELECT id, quantity
FROM products
WHERE id = :id
FOR UPDATE WAIT 5;
```

Oracle waits up to the specified number of seconds in the `WAIT` clause. When time expires, the statement fails to acquire the lock. This fits when business rules tolerate a short wait without letting requests hang indefinitely.

### 6.4. SKIP LOCKED

```sql
SELECT id, payload
FROM job_queue
WHERE status = 'READY'
ORDER BY created_at, id
FOR UPDATE SKIP LOCKED;
```

`SKIP LOCKED` skips rows locked by other sessions and returns available unlocked rows. It is widely used for multiple workers pulling jobs from a queue without piling up behind the first locked row.

`SKIP LOCKED` is not a lock timeout. It alters the returned result set by omitting locked rows. If no unlocked rows match, the query returns empty even while other workers are processing active jobs.

In JPA, `PESSIMISTIC_WRITE` with standard lock timeouts does not automatically guarantee Hibernate generates `SKIP LOCKED`. It is Oracle-specific/provider-specific behavior—check your Hibernate/Oracle JDBC API. When worker queues require `SKIP LOCKED`, native SQL or provider-specific features can be used.

## 7. Deadlocks and Common Locking Errors

### 7.1. Deadlocks

A deadlock occurs when two or more transactions each hold locks the others need, forming a wait cycle.

Example:

```text
Transaction A                 Transaction B
-------------                 -------------
Lock row 1                    Lock row 2
Request lock row 2             Request lock row 1
       |                              |
       +---------- deadlock ----------+
```

Oracle detects deadlocks and typically raises `ORA-00060: deadlock detected while waiting for resource`, rolling back one statement to break the cycle. The application must handle the failed transaction and never continue using persistence context state as if the operation succeeded.

### 7.2. Reducing Deadlock Risk

- Always lock multiple rows in a consistent order, such as ascending primary key.
- Keep transactions short.
- Never wait on HTTP calls, messaging, or user actions while holding row locks.
- Lock no more rows than business logic requires.
- Design proper indexes so locking queries do not scan excessive rows.
- Inspect execution plans and predicates of `SELECT FOR UPDATE` queries.
- Retry deadlocks with bounded attempts, backoff, and only when operations are idempotent/safe.

### 7.3. Errors to Distinguish

| Oracle/JPA/Spring Error | Common Meaning | Resolution |
|---|---|---|
| `ORA-00054` | `NOWAIT` or lock timeout expired | Identify lock holder; decide whether to return conflict or retry |
| `ORA-00060` | Deadlock | Inspect deadlock trace, lock ordering, and transaction boundaries |
| `ORA-30006` | `WAIT` timeout expired while acquiring lock | Review lock hold durations and timeouts |
| `OptimisticLockException` | Version mismatch | Roll back, reload data, and let caller resolve conflict |
| `PessimisticLockException` | Failure acquiring/holding pessimistic lock failing the transaction | Roll back transaction and investigate resource contention |
| `LockTimeoutException` | Failed to acquire lock within deadline; JPA distinguishes statement vs. tx failure | Check provider translation and transaction status |
| Spring `CannotAcquireLockException` | Spring translation of lock acquisition failure | Inspect JDBC/Oracle root cause and apply retry policy |

Final exception names depend on the throwing layer and exception translation. Log the root-cause Oracle error code/SQLState alongside transaction correlation IDs while avoiding sensitive data.

## 8. Locking with Bulk Updates and Native Queries

### 8.1. JPQL Bulk Updates Bypass Normal Entity Lifecycles

JPQL bulk updates execute directly against the database without loading individual entities into the persistence context. Consequently, they do not perform optimistic version checks automatically and do not update entities already held in the persistence context.

Example:

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("update Product p set p.quantity = p.quantity - :amount " +
       "where p.id = :id and p.quantity >= :amount")
int decreaseQuantity(@Param("id") Long id, @Param("amount") int amount);
```

The query returns the updated row count. If optimistic locking is needed on a bulk update, explicitly include version predicates and increment the version in the query, or update managed entities instead. Review the persistence context after bulk DML because previously loaded entities become stale.

### 8.2. Native SQL

Native queries can use Oracle-specific clauses like `FOR UPDATE WAIT`, `NOWAIT`, or `SKIP LOCKED`. When writing native SQL, the application is responsible for transaction boundaries, parameter binding, and entity state synchronization.

Never concatenate user input directly into native SQL strings. Bind all data values; any unbindable syntax elements such as column names or sort directions must be allowlisted.

## 9. Combining @Version with Pessimistic Locks

An entity can have `@Version` while certain operations still request `PESSIMISTIC_WRITE`. The two mechanisms are not mutually exclusive:

- Pessimistic locking prevents other transactions from altering the row while the lock is held.
- Version checking detects updates made through paths that did not acquire the same lock or occurred before the lock was taken.

When combining them, Hibernate/Oracle must follow provider semantics. Do not attach lock modes to every query just because an entity has `@Version`, as doing so unnecessarily degrades concurrency.

## 10. Isolation Levels and Locking

Isolation levels and explicit lock modes are related but distinct layers of control.

Oracle defaults to `READ COMMITTED` at the transaction level. Each SQL statement sees data committed before that statement began via multi-version concurrency control (MVCC). Normal read queries do not lock rows to block writers; `SELECT FOR UPDATE` is what requests row locks.

`SERIALIZABLE` changes transaction snapshot visibility and raises serialization errors on conflicts. It does not replace every use case for pessimistic locks, nor should you raise isolation application-wide merely to patch one race condition.

JPA `LockModeType` expresses entity/query locking requirements; JDBC transaction isolation expresses transaction visibility semantics. Pick the right tool for your business semantics.

## 11. Designing Safe Retries

### 11.1. Retrying Optimistic Conflicts

On an optimistic conflict, retries must load fresh entities in a brand-new transaction. Never retry using stale entities from the failed persistence context.

Conceptual example:

```java
public void updateWithRetry(Long id, int delta) {
    int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            updateInNewTransaction(id, delta);
            return;
        } catch (ObjectOptimisticLockingFailureException ex) {
            if (attempt == maxAttempts) {
                throw ex;
            }
            backoff(attempt);
        }
    }
}
```

`updateInNewTransaction` must genuinely run in a new transaction—for example, on a separate Spring bean or properly configured transaction boundary. Calling another `@Transactional` method on the same object via self-invocation bypasses the Spring proxy, breaking propagation.

Not every business operation may be auto-retried. If a request represents a user decision based on displayed data, return a conflict so the user can review fresh data rather than blindly reapplying the delta.

### 11.2. Retrying Lock Timeouts and Deadlocks

Retry only when:

- The previous transaction rolled back/was marked rollback-only and the connection/persistence context is cleaned up.
- The error is a clearly identified transient locking failure.
- The operation is idempotent or guarded by an idempotency key/duplicate protection.
- Attempts are capped and use exponential backoff with jitter.
- Retries will not worsen overload while the database is under heavy contention.

Never retry `SELECT FOR UPDATE` endlessly when a lock holder is stuck. Find why transactions hold locks too long and fix their lifecycle.

## 12. Workflow for Choosing and Testing Locking

1. Identify the business invariant to protect, such as non-negative inventory or single-worker job ownership.
2. Assess contention levels and transaction duration; low contention usually favors optimistic locking.
3. Add `@Version` to entities needing lost-update detection and verify the schema version column.
4. Use `PESSIMISTIC_WRITE`/`@Lock` for operations needing row locks across read-modify-write.
5. Choose lock timeouts distinct from transaction/query/pool timeouts; verify provider hint support.
6. When using Oracle `NOWAIT`, `WAIT n`, or `SKIP LOCKED`, inspect Hibernate-generated SQL or use controlled native queries.
7. Run real multi-transaction concurrency tests, not just single-threaded unit tests.
8. Test optimistic conflicts, lock timeouts, deadlocks, rollbacks, and retries.
9. Monitor Oracle wait events, blocking sessions, lock durations, SQL plans, and connection pool metrics.
10. Implement retries only for safe operations with cleanly started new transactions.

## 13. Example of Testing Two Concurrent Transactions

One way to test optimistic locking is opening two independent transactions, reading the same versioned entity in both, then flushing sequentially:

```text
Transaction A                 Transaction B
-------------                 -------------
Read Product v=4              Read Product v=4
Change quantity               Change quantity
Flush -> UPDATE ... v=4       
Commit -> version becomes 5   
                              Flush -> UPDATE ... v=4
                              0 rows updated
                              Optimistic lock exception
```

For pessimistic locking:

```text
Transaction A                 Transaction B
-------------                 -------------
SELECT ... FOR UPDATE         SELECT ... FOR UPDATE
Gets row lock                 Waits / NOWAIT error
Update row                    
Commit                        Acquires lock or fails
```

Tests must use two independent connections/sessions and real transaction boundaries. Running sequentially inside a single persistence context will not reproduce contention.

## 14. Key Principles to Remember

- Optimistic locking uses `@Version` to detect concurrent modifications before writing; it does not lock rows during reads.
- Pessimistic locking requests database row locks; Oracle typically uses `SELECT FOR UPDATE` and holds locks until commit/rollback.
- `OPTIMISTIC_FORCE_INCREMENT` and `PESSIMISTIC_FORCE_INCREMENT` force version increments per their lock modes.
- Spring Data JPA `@Lock` sets lock modes on repository queries; operations must run inside a proper transaction.
- `jakarta.persistence.lock.timeout` is a hint in milliseconds; Hibernate/drivers/databases may have implementation constraints.
- `@Transactional(timeout=...)`, query timeouts, and connection-pool timeouts are distinct limits.
- Oracle `NOWAIT`, `WAIT n`, and `SKIP LOCKED` have different semantics; `SKIP LOCKED` skips locked rows instead of waiting.
- Handle deadlocks with transaction rollbacks, consistent lock ordering, and short transactions; never retry endlessly.
- Handle bulk JPQL/native DML carefully since it bypasses normal optimistic version checks and persistence-context synchronization.
- Retry in a fresh transaction only when operations are idempotent or guarded against duplicate processing.

## References

- [Jakarta Persistence Specification — Locking and Concurrency](https://jakarta.ee/specifications/persistence/)
- [Hibernate ORM User Guide — Locking](https://docs.hibernate.org/orm/6.6/userguide/html_single/Hibernate_User_Guide.html#locking)
- [Spring Data JPA Reference — Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html)
- [Spring Framework Reference — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Oracle Database 19c SQL Language Reference — SELECT](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/SELECT.html)
- [Oracle Database 19c Concepts — Data Concurrency and Consistency](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/data-concurrency-and-consistency.html)
