# Applying @Lock to Queries and Redeclared CRUD Methods

Spring Data JPA lets you specify a JPA lock mode directly on repository methods using the `@Lock` annotation. This annotation can be used on derived query methods, queries declared with `@Query`, and even inherited CRUD methods redeclared in the repository interface. As a result, the application can request pessimistic locks or optimistic lock checks when reading data within a transaction.

`@Lock` specifies the lock mode for the query operation. It does not open a transaction on its own and does not replace `@Transactional`. For locks to take effect properly across the business operation, you must establish appropriate transaction boundaries, choose the right lock mode, and keep transactions sufficiently short.

## 1. What is @Lock?

Spring Data JPA provides the annotation:

```java
import org.springframework.data.jpa.repository.Lock;
import jakarta.persistence.LockModeType;
```

The `@Lock` annotation accepts a value from the `jakarta.persistence.LockModeType` enum:

```java
@Lock(LockModeType.PESSIMISTIC_WRITE)
Optional<Product> findBySku(String sku);
```

When Spring Data executes the repository method, the lock mode is applied to the corresponding JPA query. The JPA provider instructs the database or persistence management mechanism to enforce that lock mode.

Common places to use it:

- Derived queries: methods like `findByStatus()`, `findBySku()`.
- JPQL queries declared with `@Query`.
- CRUD methods redeclared in the repository interface, such as `findAll()`, to attach locking metadata.

`@Lock` does not lock the entire repository or the entire table. It applies to the annotated query operation and the entities within the lock scope supported by the JPA provider.

## 2. Applying @Lock to derived queries

For derived queries, simply place `@Lock` directly on the method:

```java
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;

import java.util.List;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Lock(LockModeType.PESSIMISTIC_READ)
    List<Product> findByCategoryId(Long categoryId);
}
```

Spring Data JPA still parses the name `findByCategoryId` to generate the query. The `@Lock` annotation adds the lock mode to the generated query.

This example requests a pessimistic read lock on matching products. How the database enforces the lock depends on the JPA provider and the database management system. Some databases may use row-level locks; some cases may escalate or convert the lock mode.

If the query method is called in a business flow requiring multiple consistent operations, call it from a service annotated with `@Transactional`. Custom-declared query methods do not inherently carry transactional configuration just because they live in a repository.

## 3. Applying @Lock to @Query queries

For JPQL declared with `@Query`, place `@Lock` on the same method:

```java
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Optional;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select p
        from Product p
        where p.id = :id
        """)
    Optional<Product> findForUpdate(@Param("id") Long id);
}
```

When `findForUpdate(id)` is called, Spring Data JPA executes the query and requests `PESSIMISTIC_WRITE` mode. Common uses include reading a record and updating it within the same transaction, such as deducting stock, reserving slots, or transitioning an order's state.

A service using this method:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final ProductRepository products;

    public InventoryService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public void decreaseStock(Long productId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be positive");
        }

        Product product = products.findForUpdate(productId)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Product not found: " + productId));

        if (product.getStock() < quantity) {
            throw new IllegalStateException("Insufficient stock");
        }

        product.setStock(product.getStock() - quantity);
        // product is managed in the persistence context.
        // Dirty checking will persist changes on flush/commit.
    }
}
```

The service transaction encompasses both the locked read and the stock update. When another transaction also requests a write lock on that record, the later transaction must wait or receive a timeout error depending on configuration. After the first transaction commits or rolls back, the waiting transaction can proceed against the new data state.

Do not split the `findForUpdate()` call and the update operation into two independent transactions. Once the transaction holding the lock ends, the lock is released; subsequent processing will no longer be protected by the acquired lock.

## 4. Redeclaring CRUD methods to add @Lock

You can redeclare a CRUD method inherited from `JpaRepository` or `CrudRepository` and attach `@Lock` to the new declaration. Spring Data JPA uses this metadata when executing the repository method.

Example of a pessimistic read lock for `findAll()`:

```java
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;

import java.util.List;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Override
    @Lock(LockModeType.PESSIMISTIC_READ)
    List<Product> findAll();
}
```

Calling `findAll()` on this repository will apply the declared lock mode. This is useful when an application wants to change the locking behavior of a built-in CRUD method without creating a brand-new query.

Other read methods can be redeclared when appropriate for the API and Spring Data JPA's implementation of them. Choose methods that perform query or entity-loading operations. Attaching `@Lock` to a write method like `save()` does not turn that write operation into a locked read query; use locks on entity-loading methods and then perform updates in the same transaction.

For write-lock operations, place the business transaction in the service:

```java
@Transactional
public void updateProduct(Long id, String newName) {
    Product product = products.findForUpdate(id)
            .orElseThrow();
    product.setName(newName);
}
```

Inherited CRUD methods carry default transaction configuration from the repository implementation. Custom-declared query methods do not have that same default transaction configuration. In both cases, a service transaction keeps locks across the business flow and groups multiple operations into a single commit/rollback unit.

## 5. LockModeType modes

JPA defines the following primary lock modes:

| Lock mode | Meaning and use case |
|---|---|
| `NONE` | No additional lock requested. |
| `OPTIMISTIC` | Requests optimistic lock validation within the transaction. Suitable when conflicts are rare and you do not want to hold database locks during reads. |
| `OPTIMISTIC_FORCE_INCREMENT` | Checks optimistic lock and forces the entity version to increment. Useful when needing to record a synchronization change even if business attributes do not change. |
| `PESSIMISTIC_READ` | Requests a pessimistic read lock to restrict other transactions from updating the locked data. |
| `PESSIMISTIC_WRITE` | Requests a pessimistic write lock, commonly used when needing to read and then update a record while serializing competing operations. |
| `PESSIMISTIC_FORCE_INCREMENT` | Acquires a pessimistic write lock and forces the entity's version to increment if the entity has a version. |

The two names `READ` and `WRITE` also exist in the enum for compatibility: `READ` is equivalent to `OPTIMISTIC`, and `WRITE` is equivalent to `OPTIMISTIC_FORCE_INCREMENT`. In new code, use the explicit names `OPTIMISTIC` and `OPTIMISTIC_FORCE_INCREMENT` to avoid confusing optimistic locking with pessimistic read/write locks.

### Optimistic locking

Optimistic locking assumes write conflicts are infrequent. Multiple transactions can read the same entity without holding row locks throughout processing. When updating, JPA checks the version to detect whether another transaction modified the data.

Entities usually declare a `@Version` field:

```java
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    private int stock;

    @Version
    private Long version;

    // constructors, getters and setters
}
```

When two transactions read the same version and both update, the transaction committing later can fail because the version in the database has changed. JPA typically detects conflicts at flush or commit time, so errors can surface at the end of the service method rather than necessarily at a setter call.

You can explicitly request an optimistic lock check on a query:

```java
@Lock(LockModeType.OPTIMISTIC)
Optional<Product> findBySku(String sku);
```

For entities with `@Version`, normal update operations already receive automatic version checks from JPA. `OPTIMISTIC` is useful when you want to guarantee that the read data remains unchanged by other transactions during the transaction, even if the business logic only reads that entity. `OPTIMISTIC_FORCE_INCREMENT` is used when you want to increment the version even without ordinary attribute changes.

When an optimistic lock fails, JPA may throw `OptimisticLockException`; through Spring's exception translation layer, the error is typically represented by the `OptimisticLockingFailureException` family. The application can report the conflict, reload data, and ask the user to try again. Only auto-retry when the business operation can be safely re-run.

### Pessimistic locking

Pessimistic locking asks the database to hold a lock for the duration of the transaction. It fits high-contention operations or when business logic requires serializing the read and update of a record.

- `PESSIMISTIC_READ`: requests a read lock; other transactions can usually still read but are restricted when trying to update the same data.
- `PESSIMISTIC_WRITE`: requests a write lock; competing transactions trying to acquire a conflicting lock must wait or fail.
- `PESSIMISTIC_FORCE_INCREMENT`: write-locks and increments the version if the entity has a version.

The database and provider determine how a lock mode maps to specific statements or locking mechanisms. A common example is a statement equivalent to `SELECT ... FOR UPDATE` for write locks, though exact syntax and behavior depend on the database management system.

Pessimistic locking generally requires an active transaction. Keep transactions short, avoiding external API calls, waiting for users, or running long tasks while holding locks. If a transaction holds a lock too long, other requests may block, time out, or degrade system throughput.

## 6. Combining @Lock with @Transactional

`@Lock` and `@Transactional` solve two different concerns:

- `@Lock` chooses the JPA lock mode for the query.
- `@Transactional` defines the transaction boundary and lifecycle.

Custom-declared query methods like `findForUpdate()` do not automatically open a transaction just because they carry `@Lock`. A method using pessimistic locking must be called inside an active transaction. The clearest approach is usually placing `@Transactional` on the service method surrounding the entity read and processing.

Example:

```java
@Transactional
public void reserve(Long productId, int amount) {
    Product product = products.findForUpdate(productId)
            .orElseThrow();

    if (product.getStock() < amount) {
        throw new IllegalStateException("Insufficient stock");
    }

    product.setStock(product.getStock() - amount);
}
```

The default propagation of `@Transactional` is `REQUIRED`. Therefore, a repository method called inside a service usually joins the existing transaction. If a repository method is called standalone, check the transaction configuration of that method itself; do not rely on `@Lock` to create a transaction.

For pessimistic write locks, avoid setting the service transaction to `readOnly = true`. A read-only transaction is unsuitable for business logic that both write-locks and updates data, and provider handling may vary.

## 7. Configuring lock timeout

You can pass a JPA query hint to request a lock wait timeout limit. Spring Data JPA supports `@QueryHints` on repository methods:

```java
import jakarta.persistence.LockModeType;
import jakarta.persistence.QueryHint;
import org.springframework.data.jpa.repository.QueryHints;

@Lock(LockModeType.PESSIMISTIC_WRITE)
@QueryHints(
    value = @QueryHint(
        name = "jakarta.persistence.lock.timeout",
        value = "3000"
    )
)
@Query("""
    select p
    from Product p
    where p.id = :id
    """)
Optional<Product> findForUpdate(@Param("id") Long id);
```

The example requests a 3,000-millisecond wait timeout. The Jakarta Persistence hint name is `jakarta.persistence.lock.timeout`; projects using older JPA versions may use the `javax.persistence.lock.timeout` namespace.

This is a hint for the provider. Support and compliance depend on the JPA provider, driver, and database. Do not assume every environment enforces the exact configured timeout value. Test actual behavior on the database management system your application uses and handle the case where the lock cannot be acquired.

## 8. Scope and limitations to understand

**Locks are tied to the transaction.** A pessimistic lock is held until the transaction ends according to database rules. When the transaction commits or rolls back, the lock is released. You cannot acquire a lock in one transaction and expect it to keep protecting code running after that transaction ends.

**Locks apply to the annotated query.** If a service loads an entity using a different method without a lock mode, do not assume the entity is automatically locked just because another repository method has `@Lock`.

**Lock mode does not replace @Version.** Version-based optimistic locking needs a `@Version` field to detect conflicts through the version mechanism. Pessimistic locking relies on database locks and can cooperate with versions when the entity has that field.

**Bulk updates do not synchronize the persistence context.** Bulk `UPDATE` or `DELETE` queries act directly on the database without going through individual managed-entity updates. If using bulk queries in the same transaction as already-loaded entities, consider flushing and clearing the persistence context to avoid stale data.

**No identical guarantees across all databases.** Lock types, lock scopes, lock escalation behavior, timeouts, and blocking levels depend on the provider and database engine. Integration testing on the exact deployed database type is necessary for contended workflows.

## 9. Common errors and solutions

| Symptom | Common cause | Resolution |
|---|---|---|
| Error requiring a transaction when using pessimistic lock | Query method has `@Lock` but runs outside a transaction | Wrap the call in a `@Transactional` service |
| Two requests still overwrite each other's data | Appropriate lock not used, or read and write occur in different transactions | Use `@Version` or pessimistic locking within the same transaction |
| Optimistic lock fails at commit | Another transaction updated the same entity | Report conflict, reload, and handle safe retry |
| Requests wait a long time when updating | Another transaction is holding a pessimistic lock | Shorten transactions, set appropriate timeouts, consider reducing contention |
| Deadlock | Transactions acquire multiple locks in different orders | Standardize record access order and keep transactions short |
| Entities in persistence context have stale data after bulk update | Bulk query does not synchronize managed entities | Flush beforehand and clear afterward when needed, or reload entities |
| @Lock appears to have no effect | Annotation placed on a method that does not execute the right query, or provider/database behaves differently | Verify the actual repository method and inspect SQL/locks on the database |

A deadlock can occur when transaction A locks record 1 and waits for record 2, while transaction B locks record 2 and waits for record 1. If business logic needs to lock multiple entities, enforce a consistent lock acquisition order across all processing flows.

## 10. Choosing a lock type by business need

| Need | Commonly suitable choice |
|---|---|
| Low-conflict data, acceptable to detect errors at commit | `@Version` and optimistic locking |
| Need to confirm entity does not change during read | `@Lock(OPTIMISTIC)` |
| Need to increment version even without modifying attributes | `@Lock(OPTIMISTIC_FORCE_INCREMENT)` |
| Need multiple concurrent readers while restricting concurrent updates | `@Lock(PESSIMISTIC_READ)` |
| Need to serialize reading and then updating a record | `@Lock(PESSIMISTIC_WRITE)` |
| Need write lock and version increment | `@Lock(PESSIMISTIC_FORCE_INCREMENT)` |

Do not default to pessimistic locking for every query. Pessimistic locking can reduce concurrency and increase lock wait risk. For most CRUD workflows, optimistic locking with `@Version` is usually a suitable starting point; switch to pessimistic locking only when contention patterns and business requirements prove it necessary.

## 11. Implementation and verification workflow

1. Identify the entities and records that need protection when multiple transactions operate concurrently.
2. Choose optimistic or pessimistic locking based on conflict frequency and how the business handles conflicts.
3. For optimistic locking, declare `@Version` on the entity and check how the application handles version errors.
4. For pessimistic locking, place `@Lock` on derived queries, `@Query` methods, or redeclared CRUD read methods.
5. Wrap lock acquisition and update inside the same `@Transactional` service method.
6. If needed, configure query hints for lock timeout and verify whether the provider/database supports them.
7. Test two concurrent transactions on the same record: one transaction holds the lock or updates first, and the other must wait or detect the conflict according to the chosen mode.
8. Inspect SQL logs, wait times, deadlock errors, and data after commit/rollback on the target database.

## Conclusion

`@Lock` is how Spring Data JPA attaches a JPA lock mode to repository queries. It can be applied to derived queries, `@Query` methods, and redeclared CRUD methods such as `findAll()`. Optimistic modes fit when you want to detect conflicts, whereas pessimistic modes fit when you need to hold locks within a transaction to serialize operations. For locks to properly protect the business logic, wrap both reading and processing in `@Transactional`, choose lock modes intentionally, and test on the actual target database management system.