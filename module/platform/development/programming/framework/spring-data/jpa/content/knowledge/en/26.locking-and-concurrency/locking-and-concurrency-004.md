# Pessimistic Locking and Choosing the Right LockModeType in Spring Data JPA

## Objectives

After this lesson, you will be able to explain when pessimistic locking is needed; distinguish `PESSIMISTIC_READ`, `PESSIMISTIC_WRITE`, and `PESSIMISTIC_FORCE_INCREMENT`; apply `@Lock` on repository methods; keep locks within the proper transaction scope; configure timeouts and lock scopes; handle timeouts and deadlocks; and test concurrency behavior on your target database.

The examples use Java 17+, Spring Boot 3+, Spring Data JPA, and Jakarta Persistence (`jakarta.persistence.*`). Pessimistic locks are enforced by the database through the JPA provider and JDBC driver. Specific SQL may differ across PostgreSQL, MySQL, SQL Server, Oracle, and other database management systems.

## 1. Why is pessimistic locking needed?

When multiple transactions concurrently read and update a record, the result can depend on execution order. For example, stock has 5 items left. Two requests both read quantity 5; each request wants to order 4 items. If both check against the stale value and then write, the system could accept 8 items in total even though stock only has 5. This is a form of race condition and lost update.

Pessimistic locking instructs the database to lock the relevant record so other transactions must wait or cannot perform a conflicting operation until the lock is released. This approach is useful when:

- Update conflicts are likely to happen frequently.
- An operation needs to read the current state, check a condition, and update within the same transaction.
- It is unacceptable for two transactions to both pass a business check based on stale data.
- Operations on a specific record or group of records must be serialized.

Pessimistic locking carries a cost: transactions holding locks for a long time can make other requests wait, reduce throughput, or cause deadlocks. Lock only the rows needed and keep transactions short.

## 2. LockModeType in Jakarta Persistence

`jakarta.persistence.LockModeType` describes how JPA requests entity locking. Common modes fall into optimistic and pessimistic groups:

| LockModeType | Group | Practical meaning |
| --- | --- | --- |
| `NONE` | No lock requested | No additional checks or locks requested beyond the provider/database defaults |
| `OPTIMISTIC` | Optimistic | Validates the version when the transaction completes; detects conflicts rather than locking rows on read |
| `OPTIMISTIC_FORCE_INCREMENT` | Optimistic | Checks and increments the version of a versioned entity |
| `PESSIMISTIC_READ` | Pessimistic | Requests a shared read lock; other transactions can read but cannot perform conflicting updates/deletes |
| `PESSIMISTIC_WRITE` | Pessimistic | Requests an exclusive write lock; other transactions trying to lock or modify the same row usually must wait |
| `PESSIMISTIC_FORCE_INCREMENT` | Pessimistic | Acquires a pessimistic write lock and forces an increment of the `@Version` on a versioned entity |

When the goal is to prevent another transaction from modifying a row while checking and updating, `PESSIMISTIC_WRITE` is usually the right choice. `PESSIMISTIC_READ` is meant for protecting data from modification during reads when the database/provider supports shared locks as expected. `PESSIMISTIC_FORCE_INCREMENT` should only be used when both a write lock and a version token change are required.

### 2.1. Do not confuse READ and WRITE with pessimistic locks

The `READ` and `WRITE` enum names are legacy compatibility aliases for the optimistic group:

- `READ` is equivalent to `OPTIMISTIC`.
- `WRITE` is equivalent to `OPTIMISTIC_FORCE_INCREMENT`.

Therefore, `LockModeType.READ` does not mean the database acquires a shared pessimistic lock; `LockModeType.WRITE` does not mean acquiring an exclusive pessimistic lock. When you need pessimistic locking, explicitly write `PESSIMISTIC_READ` or `PESSIMISTIC_WRITE`.

## 3. PESSIMISTIC_READ, PESSIMISTIC_WRITE, and PESSIMISTIC_FORCE_INCREMENT

### 3.1. PESSIMISTIC_READ

`PESSIMISTIC_READ` requests a read lock to prevent other transactions from updating or deleting the locked entity until the current transaction finishes. Multiple transactions can hold a read lock on the same row simultaneously if the database supports shared locks.

This mode is suitable when you need to read a stable state within a transaction and block concurrent updates. However, the database or JPA provider may implement it using a stronger lock, such as upgrading to a write lock. Do not assume this mode always allows multiple concurrent readers; verify the SQL and behavior on the actual database.

### 3.2. PESSIMISTIC_WRITE

`PESSIMISTIC_WRITE` requests an exclusive write lock on the entity. Other transactions trying to acquire a conflicting lock or update the same row will usually have to wait until the lock is released or time out.

This is a common choice for operations such as deducting inventory, reserving slots, transitioning order statuses, or updating a shared quota. Acquire the lock before reading the value used for decision-making, check the condition, and write the change in the same transaction.

### 3.3. PESSIMISTIC_FORCE_INCREMENT

`PESSIMISTIC_FORCE_INCREMENT` acquires a pessimistic write lock and forces an increment on the `@Version` field of a versioned entity. It is useful when an operation needs to change the version token so other transactions know the state has been synchronized, even if the business logic does not modify a regular attribute.

Use this mode only when the entity is versioned and there is a clear business reason to increment the version. If you only need to prevent concurrent updates within a transaction, `PESSIMISTIC_WRITE` is usually simpler.

## 4. Example entity with version and inventory quantity

The `Inventory` entity illustrates an item with an available quantity. `@Version` enables JPA to perform optimistic version checks on write; it can coexist with pessimistic locks.

```java
package com.example.learning.inventory;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "inventory")
public class Inventory {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true)
    private String sku;

    @Column(nullable = false)
    private int available;

    @Version
    private long version;

    protected Inventory() {
    }

    public Inventory(String sku, int available) {
        this.sku = sku;
        this.available = available;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public int getAvailable() { return available; }
    public long getVersion() { return version; }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (available < quantity) {
            throw new IllegalStateException("insufficient inventory");
        }
        available -= quantity;
    }
}
```

`reserve` contains the entity's business rule. The method does not write SQL itself; when the entity is managed and the transaction commits, JPA dirty checking detects that `available` changed and synchronizes it to the database.

## 5. Using @Lock on a repository method

Spring Data JPA provides the annotation `org.springframework.data.jpa.repository.Lock`. This annotation attaches a `LockModeType` to the query executed by the repository:

```java
package com.example.learning.inventory;

import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import jakarta.persistence.LockModeType;

public interface InventoryRepository extends JpaRepository<Inventory, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select i from Inventory i where i.id = :id")
    Optional<Inventory> findByIdForUpdate(@Param("id") Long id);

    @Lock(LockModeType.PESSIMISTIC_READ)
    @Query("select i from Inventory i where i.sku = :sku")
    Optional<Inventory> findBySkuForRead(@Param("sku") String sku);
}
```

The `findByIdForUpdate` method returns the selected entity with lock mode `PESSIMISTIC_WRITE`. The `ForUpdate` method name helps callers understand the intent, but the method name itself does not create the lock; the `@Lock` annotation sets the lock mode.

You can place `@Lock` on derived query methods or redeclare a CRUD method to add a lock mode:

```java
@Override
@Lock(LockModeType.PESSIMISTIC_WRITE)
Optional<Inventory> findById(Long id);
```

When redeclaring `findById`, every caller of that method uses a write lock. Consider the impact scope; a dedicated method like `findByIdForUpdate` usually expresses more clearly which use case actually requires locking.

`@Lock` only configures the lock mode for the query. It does not automatically open a transaction for the caller's entire business logic. Place the transaction in the service so acquiring the lock, checking data, and updating all fall within the same boundary.

## 6. Holding locks inside a service transaction

Example service performing inventory reservation:

```java
package com.example.learning.inventory;

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
        Inventory inventory = inventoryRepository.findByIdForUpdate(inventoryId)
            .orElseThrow(() -> new IllegalArgumentException("inventory not found"));

        inventory.reserve(quantity);
    }
}
```

Sequence:

1. Spring opens a transaction when the call goes through the transactional proxy.
2. The repository executes the query and asks the database to acquire a `PESSIMISTIC_WRITE` lock.
3. If another transaction is holding a conflicting lock, the query may wait or time out.
4. Once the lock is acquired, the service validates and decrements the quantity on the managed entity.
5. When the transaction commits or rolls back, the database releases the lock.

There is no need to call `save(inventory)` in this example because the entity is already managed in the persistence context and changes are written via dirty checking on flush/commit. An extra `save` call does not make the lock stronger.

For write flows, use a normal transaction (`readOnly = false`, which is the default). Do not mark this transaction `readOnly = true` because its purpose is to update inventory and databases/providers may handle read-only transactions in ways unsuitable for write operations.

### 6.1. The transaction must encompass the entire operation

Do not acquire a lock in a short transaction and then update in another transaction. When the first transaction ends, the lock is released; the subsequent update operation is no longer protected.

Spring's `@Transactional` usually works through a proxy. A public method called from another bean goes through the proxy. If a method in the same object directly calls another `@Transactional` method (self-invocation), the internal call usually bypasses the proxy and may not open a transaction as expected. Place the transaction on a public service method called from outside the bean or structure calls through an appropriate bean.

Keep transactions short: do not call HTTP services, send emails, wait for user input, or run slow tasks while holding locks. Those operations keep connections and row locks held for a long time, forcing other requests to wait.

## 7. Lock timeout and QueryHints

When a row is locked by another transaction, a lock-acquiring query may wait. You can request a timeout via the standard Jakarta Persistence hint:

```java
import jakarta.persistence.LockModeType;
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.QueryHints;

@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(value = {
    @QueryHint(name = "jakarta.persistence.lock.timeout", value = "3000")
})
@Query("select i from Inventory i where i.id = :id")
Optional<Inventory> findByIdForUpdateWithTimeout(@Param("id") Long id);
```

`jakarta.persistence.lock.timeout` takes a timeout value in milliseconds per the hint specification. This is a hint that the provider passes down to the database/driver; support levels and enforcement vary. Some databases do not support per-query timeouts or the provider may ignore the hint. Verify on your target database rather than treating `3000` as a guarantee that every request will wait exactly three seconds.

Do not confuse lock timeout with Spring's transaction timeout. Lock timeout limits the time spent waiting to acquire a lock; transaction timeout limits the execution duration of the transaction per the transaction manager/provider configuration. The two limits solve different problems.

## 8. Lock scope: NORMAL and EXTENDED

Jakarta Persistence defines `PessimisticLockScope` to describe the scope of locked rows:

| Scope | Scope of rows |
| --- | --- |
| `NORMAL` | Rows belonging to the entity being locked, including secondary tables used to store the entity's state |
| `EXTENDED` | NORMAL scope plus rows in join tables of relationships owned by the entity |

`EXTENDED` does not mean locking all entities referenced by relationships. For example, locking a customer with a many-to-many collection can extend to the join table rows of that relationship, but it does not automatically lock the state of every entity on the other side.

You can request the scope using a hint:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(value = {
    @QueryHint(name = "jakarta.persistence.lock.scope", value = "EXTENDED")
})
@Query("select i from Inventory i where i.id = :id")
Optional<Inventory> findWithExtendedLockScope(@Param("id") Long id);
```

Increase the scope only when business logic requires protecting related rows. Wider lock scopes increase contention and deadlock risk. Providers/databases may have implementation limitations; test actual behavior.

## 9. Using EntityManager for programmatic locking

In addition to repository `@Lock`, you can request locks through `EntityManager`. This is useful in custom repositories or when choosing a lock mode dynamically by business branch:

```java
import jakarta.persistence.EntityManager;
import jakarta.persistence.LockModeType;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class InventoryLockRepository {
    private final EntityManager entityManager;

    public InventoryLockRepository(EntityManager entityManager) {
        this.entityManager = entityManager;
    }

    @Transactional
    public Inventory findForUpdate(Long id) {
        Inventory inventory = entityManager.find(Inventory.class, id);
        if (inventory == null) {
            return null;
        }
        entityManager.lock(inventory, LockModeType.PESSIMISTIC_WRITE);
        return inventory;
    }
}
```

Related APIs:

- `entityManager.find(Entity.class, id, lockMode)` loads the entity with the specified lock mode.
- `entityManager.lock(managedEntity, lockMode)` requests a lock for a currently managed entity.
- `entityManager.refresh(entity, lockMode)` reloads database state and can request a lock at the same time.

`lock` requires the entity to belong to the current persistence context. `refresh` overwrites in-memory state with database state; do not call it after making unflushed changes you want to keep. Lock-acquiring operations require an active transaction.

## 10. How does the database enforce locks?

JPA describes locking intent at the API level. The provider generates SQL tailored to the dialect and database. Many databases use statements like `SELECT ... FOR UPDATE` for write locks; some use different syntax or mechanisms.

Do not assume:

- `PESSIMISTIC_READ` is always implemented as a distinct shared row lock.
- A query always locks only one row if the query has joins or the database uses lock escalation.
- A lock mode protects rows that do not yet exist or future records matching the condition.
- Different databases behave identically under the same isolation level or lock hint.

Indexes on the lookup condition for locked rows help the database locate records faster and can reduce lock hold time. However, actual lock types, range locks, and lock escalation possibilities depend on the database, isolation level, execution plan, and SQL generated by the provider.

When using `PESSIMISTIC_WRITE`, enable SQL logging or observe the database to understand the emitted statements and lock waits. Test on the exact database version running in production.

## 11. Locking queries, joins, and nonexistent records

Lock modes apply to entities returned by the query according to JPA/provider rules. If a query returns a projection or scalar instead of an entity, do not assume the underlying entity was locked as desired. For operations requiring locks, prefer queries returning entities and inspect the actual SQL.

When a query joins multiple tables, the database may lock additional rows or lock differently than expected. Avoid unnecessary joins in lock-acquiring queries. If multiple entities must be protected, clearly define the lock order and scope of each query.

A nonexistent row cannot be locked as an existing entity via `findByIdForUpdate`. If two transactions both check for a nonexistent code and then both insert, a row lock on an empty result does not protect that gap on all databases. Use a unique constraint to guarantee uniqueness, handle insert conflicts, or choose database-appropriate isolation/advisory locks if the business logic requires locking a key that has no row yet.

## 12. Timeouts, deadlocks, and exceptions

Pessimistic locking can lead to operational errors that must be explicitly handled:

- **Lock timeout:** a transaction waits longer than allowed to acquire a lock.
- **Deadlock:** transaction A holds a lock that B needs, while B holds a lock that A needs; the database chooses one transaction as a victim and rolls it back.
- **Database lock error:** a driver/database-specific error when a lock cannot be acquired or maintained.

Jakarta Persistence has two notable exceptions:

| Exception | Meaning per JPA |
| --- | --- |
| `LockTimeoutException` | Lock wait timed out and only the statement is rolled back per the JPA contract; the transaction may still remain active |
| `PessimisticLockException` | Failed to acquire lock and the transaction is rolled back at the transaction level |

Spring can translate provider/JDBC exceptions into exceptions under the `DataAccessException` hierarchy, such as the lock acquisition failure group. The observed exception type depends on the provider, driver, and transaction manager; do not catch only a single JPA class and assume every error has the same form.

When encountering a deadlock or timeout, let the transaction finish according to its rollback state. If retrying, retry the entire use case in a new transaction, with bounded attempts and backoff; only retry when the operation can be safely executed multiple times. Do not continue updating inside a transaction already marked rollback-only.

## 13. Reducing deadlocks and contention

Practices to reduce wait times and deadlocks:

1. Keep transactions short and lock only the necessary rows.
2. Acquire locks in a consistent order, such as ascending by ID, across all business flows.
3. Do not call external services or wait for I/O while holding locks.
4. Create appropriate indexes for lookup conditions on locked rows.
5. Avoid locking wide collections/relationships unless needed.
6. Choose `PESSIMISTIC_READ` when only read protection is needed and the database genuinely supports that behavior; use `PESSIMISTIC_WRITE` when concurrent updates must be excluded.
7. Monitor lock wait times, deadlock counts, timeout counts, and the connection pool.

If an operation must lock multiple rows, establish the lock order before implementing. Two code paths acquiring the same two rows in opposite orders is a common cause of deadlocks.

## 14. Comparing pessimistic locking and optimistic locking

| Criterion | Pessimistic locking | Optimistic locking |
| --- | --- | --- |
| Protection method | Database locks rows during the transaction | Uses version to detect conflicts on write/commit |
| When conflict occurs | Other transactions may wait or time out | One transaction may fail with an optimistic lock exception |
| Best suited for | Frequent conflicts, need to serialize operations | Rare conflicts, read-heavy workloads, avoiding long-held locks |
| Main cost | Lock waits, contention, deadlocks, and held connections | Retries or conflict handling when version changes |
| Annotation/API | `@Lock(PESSIMISTIC_WRITE)` | `@Version`, `OPTIMISTIC`, or `OPTIMISTIC_FORCE_INCREMENT` |

There is no single best choice for every use case. If conflicts are rare, `@Version` is usually simpler and scales better. If an operation must check and update shared state and conflicts happen frequently, a pessimistic write lock may fit better. Measure under realistic load before deciding.

## 15. Testing repository locks

You can start with an integration test to confirm the repository method can execute the locking query:

```java
package com.example.learning.inventory;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class InventoryLockRepositoryTest {
    @Autowired
    private InventoryRepository inventoryRepository;

    @Test
    void loadsInventoryUsingPessimisticWriteQuery() {
        Inventory saved = inventoryRepository.saveAndFlush(
            new Inventory("SKU-1", 5)
        );

        Inventory locked = inventoryRepository.findByIdForUpdate(saved.getId())
            .orElseThrow();

        assertThat(locked.getAvailable()).isEqualTo(5);
    }
}
```

`@DataJpaTest` normally runs tests inside a transaction and rolls back when the test finishes. This test verifies that the mapping, query, and lock request work in the test environment; it does not prove that a second transaction is actually blocked.

To test contention, you need an integration test with two independent transactions on two threads or two connections:

1. Transaction A acquires `PESSIMISTIC_WRITE` on an inventory row and keeps the transaction open in a controlled way.
2. Transaction B tries to acquire the same lock.
3. Verify that B waits or times out according to the database/driver configuration.
4. Let A commit/roll back and verify that B proceeds or receives the expected error.

Use latches/barriers for test coordination instead of arbitrary `sleep` calls. Run this test on the same database and driver type as production; H2 can differ from PostgreSQL, MySQL, SQL Server, or Oracle in lock semantics and timeouts.

## 16. Common mistakes

- **Using `READ` when wanting a pessimistic read lock.** `READ` is an alias for `OPTIMISTIC`; use `PESSIMISTIC_READ`.
- **Using `WRITE` when wanting a pessimistic write lock.** `WRITE` is an alias for `OPTIMISTIC_FORCE_INCREMENT`; use `PESSIMISTIC_WRITE`.
- **Assuming `@Lock` opens a transaction automatically.** Place `@Transactional` on the service wrapping the query, check, and update.
- **Acquiring a lock and ending the transaction before updating.** The lock is released when the transaction ends; keep the entire operation in one transaction.
- **Using `PESSIMISTIC_WRITE` for every query.** Lock only where true concurrency requirements exist; overly broad locking hurts throughput.
- **Assuming `PESSIMISTIC_READ` is always a shared lock.** The provider/database may use a stronger lock.
- **Calling external services while holding a lock.** Transactions stretch out and increase lock waits.
- **Not enforcing a consistent lock order.** Multiple threads acquiring locks in different orders can deadlock.
- **Trying to lock a row that does not exist yet.** Use a unique constraint or an appropriate key-locking mechanism; a query returning empty cannot lock a nonexistent entity.
- **Relying on timeout hints without checking the driver.** Hints can be ignored or supported differently.
- **Testing only with H2 and extrapolating to production.** Test contention on the actual target database.
- **Retrying inside a rollback-only transaction.** End the failed transaction and retry the entire operation in a new transaction if safe.

## 17. Pre-deployment checklist

- [ ] Clear business reason to use pessimistic instead of optimistic locking.
- [ ] Correct selection among `PESSIMISTIC_READ`, `PESSIMISTIC_WRITE`, or `PESSIMISTIC_FORCE_INCREMENT`.
- [ ] Not confusing `READ`/`WRITE` with pessimistic modes.
- [ ] Repository method has `@Lock` on a query returning an appropriate entity.
- [ ] Service transaction encompasses lock acquisition, validation, and update.
- [ ] Transaction performs no external I/O or long-running work while holding locks.
- [ ] Timeout and lock scope are tested on the actual provider/database.
- [ ] Query predicates have appropriate indexes and lock scope is narrow enough.
- [ ] Acquisition order for multiple locks is consistent across business flows.
- [ ] Handling is in place for timeouts, deadlocks, and retries in a new transaction where appropriate.
- [ ] Integration tests use two independent transactions to verify contention behavior.

## Conclusion

In Spring Data JPA, `@Lock` attaches a JPA `LockModeType` to a repository query. `PESSIMISTIC_READ` requests a read lock, `PESSIMISTIC_WRITE` requests an exclusive write lock, and `PESSIMISTIC_FORCE_INCREMENT` also forces a version increment on versioned entities. `READ` and `WRITE` are compatibility names for optimistic modes, so do not use them in place of pessimistic locks. Keep locks within short service transactions, verify timeout/scope configurations, acquire locks in a consistent order, and test contention on the actual target database.