# Atomic Updates with Business Conditions and Row Count Checks

In systems where multiple requests modify the same data concurrently, reading an entity, checking a condition in Java, and then writing can create a race condition. Two transactions can read the same stale value, both see the condition as valid, and both apply changes. The final outcome can violate business rules.

Spring Data JPA lets you run a conditional `UPDATE` statement directly in the database. The statement checks the condition and modifies the data in a single operation. The affected row count indicates whether the operation succeeded. This is an implementation of **conditional update** or **compare-and-set**.

## 1. The problem with read-then-write flows

Suppose inventory has 5 items left and two customers each order 4 items. A common flow looks like:

1. Read the stock quantity.
2. Check whether the stock quantity is sufficient.
3. Subtract the ordered quantity.
4. Save the entity.

If two transactions both read the value 5 before either writes, both can pass the check. Each transaction then subtracts 4, even though the warehouse only had 5 items.

The reason is that the check and the update sit in two separate operations. A transaction groups operations under commit/rollback boundaries, yet merely annotating a method with `@Transactional` does not turn a read-then-write sequence into an atomic conditional update.

## 2. Putting business conditions into the UPDATE statement

Instead of loading the entity into Java to check, place the condition inside the `WHERE` clause of the update statement. For example, only deduct stock when the product is active and the remaining quantity suffices to fulfill the request.

Suppose the entity has fields `id`, `available`, and `active`:

```java
@Entity
public class Inventory {

    @Id
    private Long id;

    private int available;

    private boolean active;

    protected Inventory() {
    }

    // Constructors, getters and other domain methods
}
```

Declare the repository method:

```java
package com.example.repository;

import com.example.domain.Inventory;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface InventoryRepository
        extends JpaRepository<Inventory, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update Inventory i
           set i.available = i.available - :quantity
         where i.id = :id
           and i.active = true
           and :quantity > 0
           and i.available >= :quantity
        """)
    int reserveIfAvailable(
            @Param("id") Long id,
            @Param("quantity") int quantity);
}
```

Key parts:

- `@Query` declares the JPQL statement. The names `Inventory`, `available`, and `active` are the Java entity and property names, not SQL table or column names.
- `@Modifying` tells Spring Data JPA this is a data-modifying query. This annotation is required when using `@Query` for `UPDATE` or `DELETE`.
- `@Param` binds Java parameters to the named parameters in JPQL.
- The condition `i.available >= :quantity` ensures remaining stock is sufficient before deducting.
- The condition `:quantity > 0` prevents negative quantities from increasing stock. The service should also validate inputs to return clear errors.
- The `int` return value is the number of rows affected by the statement.

A conceptually equivalent SQL statement is:

```sql
UPDATE inventory
SET available = available - ?
WHERE id = ?
  AND active = true
  AND ? > 0
  AND available >= ?;
```

JPQL in the repository uses entity property names; the illustrative SQL uses database table and column names.

## 3. Checking the affected row count

With `id` as the primary key, the statement above typically yields only two outcomes:

| Affected rows | Meaning |
|---:|---|
| 1 | A matching record meeting all conditions was found and updated successfully |
| 0 | No record satisfied all conditions |

If the result is 0, the record may not exist, the product may be inactive, or stock may be insufficient. Based solely on the affected row count, you cannot distinguish the exact cause.

You can handle the result in the service:

```java
package com.example.service;

import com.example.repository.InventoryRepository;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InventoryService {

    private final InventoryRepository inventoryRepository;

    public InventoryService(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    @Transactional
    public boolean reserve(Long inventoryId, int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "Quantity must be greater than zero");
        }

        int affected = inventoryRepository.reserveIfAvailable(
                inventoryId, quantity);

        if (affected > 1) {
            throw new IllegalStateException(
                    "An inventory ID updated more than one row");
        }

        return affected == 1;
    }
}
```

The service opens a transaction for the business operation. When the repository returns 1, the reservation succeeded. When it returns 0, the service can return a failure outcome so the calling layer decides how to respond, such as reporting insufficient stock. The row count check must run immediately after the update statement and stay inside the same transaction's processing flow.

For a primary key, more than 1 affected row is abnormal. If updating by a non-unique condition, clarify whether more than 1 affected row is valid or indicates an unintended update scope.

## 4. Why are conditional updates safer under contention?

Suppose initial stock is 5 and two transactions both request reserving 4 items. Each transaction sends a conditional statement:

```sql
UPDATE inventory
SET available = available - 4
WHERE id = 10 AND available >= 4;
```

The database coordinates concurrent updates according to its locking mechanism and isolation level. One transaction succeeds, leaving stock at 1. When the other transaction evaluates the condition against the current row state, `available >= 4` is no longer true, so it updates zero rows.

The expected result is that one transaction receives an affected row count of 1 and the other receives 0. Both checking and writing happen in the same statement, eliminating the gap between a separate read and write.

Exact behavior still depends on the database and isolation level. For critical concurrent operations, test against the exact database management system and transaction configuration your application uses.

## 5. Applying to conditional state transitions

Conditional updates also fit well when a record may transition state only if its current state still matches what is expected. For example, transitioning an order from `PENDING` to `CONFIRMED` only if it is still `PENDING`:

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
    update PurchaseOrder o
       set o.status = :newStatus
     where o.id = :id
       and o.status = :expectedStatus
    """)
int changeStatusIfExpected(
        @Param("id") Long id,
        @Param("expectedStatus") OrderStatus expectedStatus,
        @Param("newStatus") OrderStatus newStatus);
```

If two requests simultaneously attempt to confirm an order, the first request can update the status. The next request no longer sees the current status matching `expectedStatus`, so it receives 0 affected rows. The service can treat this as a state conflict or an already-processed request.

This approach is often called compare-and-set: write the new value only if the current value still equals the expected value.

## 6. Combining with optimistic locking via @Version

JPA supports optimistic locking through a `@Version` attribute. In normal operations on managed entities, the provider uses the version to detect whether another transaction modified the data.

However, a JPQL bulk update operates directly on the database. It bypasses dirty checking on managed entities and does not automatically check or increment the version as a normal entity update does.

If you need optimistic concurrency for a bulk update, put the expected version in `WHERE` and explicitly increment the version in `SET`. For example, the entity has the field:

```java
@Version
private long version;
```

The update method can look like:

```java
@Modifying(clearAutomatically = true, flushAutomatically = true)
@Query("""
    update Inventory i
       set i.available = i.available - :quantity,
           i.version = i.version + 1
     where i.id = :id
       and i.version = :expectedVersion
       and i.available >= :quantity
       and :quantity > 0
    """)
int reserveWithVersion(
        @Param("id") Long id,
        @Param("quantity") int quantity,
        @Param("expectedVersion") long expectedVersion);
```

If the current version no longer equals `expectedVersion`, the statement updates zero rows. A row count of 0 indicates at least one condition no longer holds. When using this approach, manage versions consistently across all write paths and test with your project's specific JPA provider.

## 7. Impact of bulk updates on the persistence context

A bulk update acts directly on rows in the database. The current persistence context does not automatically synchronize entities that were previously loaded. Therefore, a managed entity may still hold stale values in memory after the update statement succeeds.

Two `@Modifying` attributes in the example address this issue:

- `flushAutomatically = true`: requests flushing pending changes before running the update query.
- `clearAutomatically = true`: requests clearing the persistence context after running the query, avoiding continued use of stale entities.

Clearing the persistence context detaches all managed entities in that context, not just the updated entity. If you do not want to clear everything, you can omit this option and explicitly refresh or reload the entities needed after the bulk update. Do not re-read an entity already in the persistence context and assume it automatically reflects the new database value.

Bulk updates also do not perform cascades like regular entity updates and do not invoke lifecycle callbacks such as `@PreUpdate` on individual entities. Business rules relying on callbacks, entity listeners, or dirty checking must be handled separately when using bulk updates.

## 8. Common mistakes

- **Using `@Query` alone and forgetting `@Modifying`:** Spring Data treats the query as a read query. Add `@Modifying` for JPQL `UPDATE` or `DELETE`.
- **No transaction:** data-modifying statements must run inside a transaction. Place `@Transactional` on the service wrapping the business operation or configure appropriate repository transactions.
- **Reading the entity and checking before updating:** the condition can go stale if another transaction modifies the same record. Put the deciding condition in `WHERE`.
- **Ignoring the return value:** the application might report success even when zero rows were updated. Always check the affected row count.
- **Treating 0 as having only a single cause:** 0 merely means no row met all conditions. Use a general message or perform a separate diagnostic step if business logic must differentiate causes.
- **Using entities loaded before the bulk update:** entities in the persistence context may contain stale data. Clear, refresh, or reload according to your strategy.
- **Assuming bulk updates auto-increment `@Version`:** bulk updates skip automatic version handling. If version checks are needed, include the version in the condition and increment it explicitly.
- **Writing overly broad update conditions:** the statement might modify more rows than intended. Narrow the key or business condition tightly and evaluate the returned row count.

## 9. Key takeaways

Atomic updates with business conditions combine validation and data mutation into a single database statement. In Spring Data JPA, declare a JPQL `UPDATE` with `@Modifying`, put data-protecting conditions in `WHERE`, run inside a transaction, and check the affected row count. Also handle persistence context state and versions proactively, because bulk updates bypass the normal entity update pipeline.