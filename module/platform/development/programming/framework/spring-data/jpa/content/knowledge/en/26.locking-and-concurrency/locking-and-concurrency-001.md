# Lost Updates and the Need for Concurrency Control

## Objectives

When multiple requests simultaneously read and modify the same record, each request may work with an outdated version of the data. If the application writes back the entire value without detecting conflicts, a later write can overwrite the result of an earlier write. That phenomenon is called a **lost update**.

After this lesson, you will be able to:

- Describe how a lost update occurs in an application using Spring Data JPA.
- Explain why simply placing a method inside a transaction is not enough to prevent all conflicts.
- Use **optimistic locking** with a **@Version** field.
- Use **pessimistic locking** with **@Lock** when a record needs to be locked during processing.
- Choose atomic update statements for quantity or counter changes.
- Handle conflicts, retries, and test concurrency scenarios.

## 1. How does a lost update happen?

Suppose the warehouse has 10 items in stock. Two requests simultaneously want to decrease the quantity: transaction T1 decreases by 2, and transaction T2 decreases by 3. Both read the initial value of 10:

| Time | Transaction T1 | Transaction T2 | Value in DB |
|---|---|---|---:|
| 1 | Read quantity = 10 | | 10 |
| 2 | | Read quantity = 10 | 10 |
| 3 | Compute 10 - 2 = 8 | | 10 |
| 4 | Write quantity = 8 | | 8 |
| 5 | | Compute 10 - 3 = 7 | 8 |
| 6 | | Write quantity = 7 | 7 |

The final result is 7. However, if both requests were applied, the correct quantity should be 5. T2 wrote a result computed from stale data and overwrote T1's change.

The danger is that each individual transaction can still succeed. The application does not necessarily receive an SQL error; the data simply loses an update silently.

Lost updates typically occur in a **read–modify–write** workflow:

1. Read an entity from the database.
2. Compute the new value in memory.
3. Write the new value back to the database.

If two transactions perform this workflow concurrently on the same record, they may both compute from the same stale value.

## 2. Why doesn't @Transactional solve the problem by itself?

Spring manages transaction boundaries with **@Transactional**. JPA manages entities loaded into the persistence context; when an entity's attributes change, the dirty checking mechanism records the changes and sends an UPDATE statement upon flush.

For example:

~~~java
@Transactional
public void decrease(Long productId, int amount) {
    Product product = productRepository.findById(productId)
        .orElseThrow();
    product.setQuantity(product.getQuantity() - amount);
}
~~~

The method above has a transaction, but if the entity has no version-checking mechanism, the UPDATE statement usually identifies the record only by its primary key, similar to:

~~~sql
UPDATE product
SET quantity = ?
WHERE id = ?;
~~~

The database knows which record to update, but the statement does not express which version the new value was computed from. Another transaction could have modified the record since the entity was read.

**A transaction guarantees that a group of operations follows commit or rollback boundaries; the ability to prevent lost updates also depends on the concurrency mechanism and the isolation level.** Under READ COMMITTED, two transactions can still read the same value before either writes. You should not treat @Transactional as an automatic lock for every entity.

Some database management systems and higher isolation levels can detect or prevent certain conflicting execution schedules. However, exact behavior depends on the database engine and configuration. Applications should choose an explicit control mechanism suited to the business logic.

## 3. Optimistic locking with @Version

Optimistic locking assumes conflicts do not occur frequently. Instead of locking the record from the start, JPA checks the version at the time of update. If the record has already been modified by another transaction, the current transaction is rejected and the application receives a conflict error.

### 3.1. Declaring the version field

Add a property annotated with **@Version** to the entity:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "product")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private int quantity;

    @Version
    private long version;

    protected Product() {
    }

    public void decrease(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount must be positive");
        }
        if (quantity < amount) {
            throw new IllegalStateException("Insufficient quantity");
        }
        quantity -= amount;
    }
}
~~~

The JPA provider manages the value of the version field. The application should not manually assign or increment this field in normal entity update flows. Commonly used types are **long**, **Long**, **int**, **Integer**, **short**, or **Short**; timestamp types are also supported by the JPA specification and providers.

The version column must exist in the corresponding table. When creating the schema via migrations, ensure this column is added with an appropriate type and a valid initial value. For entities that already have data, the migration must set an initial value for existing rows.

### 3.2. JPA checks the version on write

Suppose two transactions both load an entity with version = 4.

- T1 updates successfully. The provider writes the new value and increments version to 5.
- T2 still holds the entity with version = 4. When T2 flushes, the condition version = 4 no longer matches.
- T2's UPDATE affects 0 rows. The provider recognizes the conflict and raises an optimistic locking error.

The illustrative SQL statement looks like:

~~~sql
UPDATE product
SET quantity = ?, version = ?
WHERE id = ? AND version = ?;
~~~

The actual SQL syntax and how the version is incremented are determined by the JPA provider. What matters is that the WHERE clause includes both the primary key and the old version. Only one transaction can successfully update from the same version.

### 3.3. Using with Spring Data JPA

The repository can keep its basic declaration:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;

public interface ProductRepository
        extends JpaRepository<Product, Long> {
}
~~~

In the service, load the entity and mutate its state inside a transaction:

~~~java
import jakarta.persistence.EntityNotFoundException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final ProductRepository productRepository;

    public InventoryService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Transactional
    public void decrease(Long productId, int amount) {
        Product product = productRepository.findById(productId)
            .orElseThrow(() ->
                new EntityNotFoundException("Product not found"));

        product.decrease(amount);
    }
}
~~~

The entity loaded inside the transaction is a managed entity. When quantity changes, dirty checking records the change; there is no need to call save just for JPA to recognize that change. On flush or commit, the provider executes the UPDATE with the version condition.

An error can occur at flush or commit time, so the fact that the service method reaches its final line does not mean the transaction is guaranteed to commit successfully. Calling save or saveAndFlush also does not eliminate the possibility of an error occurring at commit.

### 3.4. Handling conflicts

At the JPA layer, errors are typically related to **OptimisticLockException**. When passing through Spring's integration layer, the error may be translated into exceptions under **OptimisticLockingFailureException**, such as **ObjectOptimisticLockingFailureException**.

The application must choose behavior appropriate for the business logic:

- Notify the user that the data has changed and ask them to reload before making further edits.
- Return HTTP 409 Conflict from an API when the request is based on stale data and the caller needs to resolve the conflict.
- Retry when the operation can be safely recomputed on fresh data and conflict frequency is low.

If retrying, start a new transaction, reload the entity, and recompute the operation from the new state. Do not catch an optimistic locking error and continue using a transaction that has already rolled back or been marked rollback-only. Also do not blindly retry operations with external side effects such as sending emails, unless the side effects are designed to be idempotent or coordinated after commit.

Optimistic locking is suitable when reads are frequent, write conflicts are relatively rare, and the application accepts handling conflict errors on the caller side.

## 4. Pessimistic locking with @Lock

Pessimistic locking asks the database to lock the record while the transaction is processing. Other transactions wanting to acquire a conflicting lock on the same record usually have to wait, or may fail if a timeout expires or a deadlock occurs.

Spring Data JPA supports declaring a lock mode using **@Lock** on a repository query method:

~~~java
import jakarta.persistence.LockModeType;
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select p from Product p where p.id = :id")
    Optional<Product> findForUpdate(@Param("id") Long id);
}
~~~

Call this method inside a transaction:

~~~java
@Transactional
public void decreaseWithLock(Long productId, int amount) {
    Product product = productRepository.findForUpdate(productId)
        .orElseThrow(() ->
            new EntityNotFoundException("Product not found"));

    product.decrease(amount);
}
~~~

**PESSIMISTIC_WRITE** requests a lock suitable for write operations. The lock is held until the transaction commits or rolls back. Depending on the database management system, other transactions may have to wait, receive a timeout error, or encounter a deadlock.

Notes when using it:

- The lock-acquiring method must run inside a transaction so the lock is held across the entire processing section that needs protection.
- Keep transactions short; avoid calling network services, waiting for user input, or performing long-running work while holding a lock.
- If a flow locks multiple records, enforce a consistent lock-acquisition order to reduce deadlock risk.
- Consider configuring timeouts and handling lock errors according to your database management system's capabilities.
- A lock only protects the resources and scope that the query actually locks; it does not automatically solve every invariant spanning multiple tables.

Pessimistic locking is useful when conflicts are frequent, operations need to be serialized, and the cost of waiting for locks is acceptable. In return, it reduces concurrency and can cause bottlenecks when transactions are long-lived.

## 5. Atomic updates for counters and quantities

Some business operations do not need to load the entire entity, compute in Java, and write back. For adding, subtracting, or incrementing/decrementing a value, you can let the database perform the calculation in a single UPDATE statement.

Example repository for conditional stock reduction:

~~~java
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ProductRepository
        extends JpaRepository<Product, Long> {

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update Product p
           set p.quantity = p.quantity - :amount
         where p.id = :id
           and p.quantity >= :amount
        """)
    int decreaseIfEnough(
        @Param("id") Long id,
        @Param("amount") int amount
    );
}
~~~

Call inside a transaction and check the number of updated rows:

~~~java
@Transactional
public void decreaseAtomically(Long productId, int amount) {
    if (amount <= 0) {
        throw new IllegalArgumentException("amount must be positive");
    }

    int updated = productRepository.decreaseIfEnough(productId, amount);

    if (updated == 0) {
        throw new IllegalStateException(
            "Product not found or insufficient quantity");
    }
}
~~~

The UPDATE statement performs the subtraction directly on the value in the database. The condition quantity >= amount is checked in the same write statement, helping prevent negative inventory when multiple transactions reduce the quantity concurrently. The return value is the number of updated rows: 1 means the update succeeded; 0 means no matching row was found or the quantity was insufficient.

This is a JPQL bulk update. It acts directly on the database and **bypasses dirty checking, entity lifecycle callbacks, and automatic synchronization with managed entities**. After a bulk update, previously loaded entities may hold stale data. The example above uses clearAutomatically to clear the persistence context after the operation; another option is to explicitly refresh or reload the entity.

Bulk updates also do not automatically perform optimistic locking like normal entity updates. If the business logic requires a version check, you must explicitly design the version condition and version increment to match the provider and statement being used. Do not assume that just because an entity has @Version, every JPQL bulk update is protected.

Atomic updates fit counters, balances, or inventory when the business rule can be expressed as a single conditional statement. If the business logic needs to inspect and modify multiple attributes or multiple records according to complex rules, consider optimistic locking, pessimistic locking, or database constraints.

## 6. Which mechanism should you choose?

| Mechanism | Suitable when | Cost and considerations |
|---|---|---|
| Optimistic locking with @Version | Conflicts are rare; want to detect that a record has been modified | Conflicting transaction fails; requires notification or controlled retry |
| Pessimistic locking with @Lock | Conflicts are frequent; need to serialize operations on a record | May incur lock waits, timeouts, or deadlocks; requires short transactions |
| Atomic update | Simple arithmetic on a single value, such as incrementing/decrementing counters or stock | Bulk updates bypass the persistence context and default version checks |
| Database constraints | Invariants that must be enforced at the data level, such as uniqueness or valid bounds | Requires designing constraints and handling violation errors |

There is no single choice that fits every case. Start from the business invariant:

- If you only need to detect that someone else modified an entity, use @Version.
- If you need to hold a lock while performing a short processing step on a record, consider PESSIMISTIC_WRITE.
- If the operation is a simple arithmetic transformation, prefer a conditional UPDATE.
- If the rule spans multiple rows or multiple transactions, evaluate constraints, isolation levels, and lock scope as well. @Version on a single entity does not automatically protect invariants spanning multiple entities.

## 7. Common mistakes

1. **Assuming @Transactional means locking.** A transaction defines commit/rollback scope; choose an appropriate concurrency mechanism.
2. **Forgetting @Version on entities that need optimistic locking.** Without a version field, JPA cannot perform version checks this way.
3. **Modifying the version value manually.** Let the JPA provider manage the field annotated with @Version.
4. **Catching the error and continuing with the stale entity.** After a conflict, reload the data in a new transaction and recompute the business logic.
5. **Using a bulk update and then reading stale entities from the persistence context.** Clear, refresh, or reload to avoid in-memory data diverging from the database.
6. **Holding a pessimistic lock for too long.** Long transactions increase wait times and deadlock risk.
7. **Locking only one row when the rule spans multiple rows.** Identify the full scope of the invariant and protect it at the right level.
8. **Retrying external side effects as well.** Sending notifications or calling external systems may be duplicated if a transaction is retried; design for idempotency or post-commit processing.

## 8. Testing concurrency behavior

A test that merely calls a service sequentially twice usually cannot reproduce a lost update. To test properly, you need two independent transactions that both load the same version before either transaction writes.

An optimistic locking test scenario:

1. Create a Product with quantity = 10 and an initial version.
2. Launch two threads, each opening its own transaction and loading the same Product.
3. Use a CountDownLatch or equivalent synchronization mechanism to ensure both threads have finished reading before allowing updates.
4. Have both threads modify quantity and then flush or commit.
5. Verify that one transaction commits successfully and the other receives an optimistic locking error.
6. Re-read the data in a new transaction and verify that the value is the result of the successful transaction, not a silent overwrite.

When testing pessimistic locking, verify that the second transaction waits or fails according to the database's timeout configuration. When testing atomic updates, run multiple concurrent decrement requests and verify that quantity never goes negative and the total number of successful updates matches the business condition.

You should run integration tests against the same type of database management system that the application uses in production. In-memory or mock test databases may have different locking and isolation behavior from the deployed database engine.

## 9. Production readiness checklist

- Clearly identify the invariant to protect: no overwriting newer data, no negative inventory, no exceeding limits, or other rules.
- Identify the entities and data scope involved in that invariant.
- Choose @Version, @Lock, an atomic UPDATE statement, or an appropriate constraint.
- Place @Transactional boundaries accurately around the operation to protect.
- Handle optimistic locking errors, lock timeouts, deadlocks, and constraint violations according to business requirements.
- If retrying, reload data in a new transaction and ensure side effects are not duplicated.
- Test with multiple independent transactions and verify the final result in the database.

Concurrency control is part of business design. Spring Data JPA provides the tools to detect or coordinate conflicts; the application must pick the right tool based on the data, contention level, and the consequence of rejecting an update.