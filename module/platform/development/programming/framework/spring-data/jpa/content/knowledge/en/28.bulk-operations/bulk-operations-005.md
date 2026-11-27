# Stale PersistenceContext After Bulk Update or Bulk Delete

Spring Data JPA allows executing bulk updates or deletes with JPQL to process many records in a single SQL statement. This approach is typically faster than loading each entity and modifying or deleting them one by one. However, bulk updates and bulk deletes act directly on the database and do not synchronize managed entities in the persistence context.

Therefore, after running a bulk operation, a previously loaded entity may still hold old values in memory. If the application continues reading or writing that entity, it may return stale data or inadvertently overwrite the changes just performed. This lesson explains why this happens and how to synchronize state safely.

## 1. What is the persistence context?

The persistence context is JPA's workspace, managed by `EntityManager`. Within a persistence context, each entity with a given database identifier is normally represented by a single managed instance.

Main entity states:

- **Transient:** a newly created Java object, not yet managed by JPA and not attached to a persistence context.
- **Managed:** an entity currently under management. JPA tracks property changes via dirty checking and can synchronize them to the database on flush.
- **Detached:** an entity that was previously managed but has been separated from the persistence context, such as after `clear()`, `detach()`, or when the persistence context ends.
- **Removed:** an entity marked for deletion in the persistence context; the delete statement will be synchronized on flush.

The persistence context acts as a first-level cache. When calling `find()` or repository `findById()`, if an entity with the same identifier is already managed in the current persistence context, JPA can return that exact instance without re-reading the latest state from the database.

Example:

```java
@Transactional
public void inspectOrder(Long id) {
    PurchaseOrder first = entityManager.find(PurchaseOrder.class, id);
    PurchaseOrder second = entityManager.find(PurchaseOrder.class, id);

    System.out.println(first == second); // true
}
```

Both variables reference the same managed instance in the persistence context. If another operation updates the corresponding row directly in the database, this instance does not change automatically.

## 2. Why do bulk update and bulk delete make the persistence context stale?

A normal entity operation goes through the persistence context:

1. JPA loads the entity into the persistence context.
2. The application modifies properties or marks the entity for removal.
3. Dirty checking and JPA's synchronization mechanism detect the changes.
4. On flush, JPA emits the corresponding SQL statements.

Bulk DML takes a different execution path. JPQL `UPDATE` or `DELETE` is translated into a statement affecting multiple rows directly in the database. The provider does not load each entity into the persistence context to apply changes.

For example, the repository runs:

```sql
UPDATE purchase_orders
SET status = 'ARCHIVED'
WHERE created_at < ?;
```

If `PurchaseOrder` has a managed instance, that instance's `status` property may still be `OPEN`, even though the database has changed to `ARCHIVED`.

Similarly, bulk delete can delete rows in the database while the corresponding instances remain in the persistence context. Those entities do not automatically transition to the `Removed` state; the application can still hold a reference to a Java object representing a deleted row.

Key point: **bulk DML does not synchronize managed entities with the statement's results.** JPA does not automatically update or remove individual instances in the persistence context after a bulk operation.

## 3. Example reproducing stale data

Suppose there is a `PurchaseOrder` entity with `id`, `status`, and `createdAt` properties. A method reads the entity first, then calls a bulk update:

```java
@Transactional
public void demonstrateStaleState(Long id) {
    PurchaseOrder order = entityManager.find(PurchaseOrder.class, id);

    // Update the database directly via a JPQL bulk update.
    entityManager.createQuery("""
        update PurchaseOrder p
        set p.status = :status
        where p.id = :id
        """)
        .setParameter("status", OrderStatus.ARCHIVED)
        .setParameter("id", id)
        .executeUpdate();

    // The managed instance may still hold the old status value.
    System.out.println(order.getStatus());
}
```

`executeUpdate()` returns the number of affected rows. It does not update the properties of the `order` variable. If `order.getStatus()` is called after the bulk update, the result may still be the old value loaded earlier.

A subsequent repository query in the same persistence context may also return the old managed instance. Simply calling `findById(id)` again does not guarantee refreshing the entity if JPA finds that instance in the first-level cache.

## 4. Bulk update/delete with Spring Data JPA

In Spring Data JPA, use `@Modifying` together with `@Query` to declare an update or delete query:

```java
import java.time.LocalDateTime;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long> {

    @Modifying
    @Query("""
        update PurchaseOrder p
        set p.status = :status
        where p.createdAt < :cutoff
        """)
    int updateStatusBefore(
            @Param("status") OrderStatus status,
            @Param("cutoff") LocalDateTime cutoff);

    @Modifying
    @Query("""
        delete from PurchaseOrder p
        where p.status = :status
        """)
    int deleteAllWithStatus(@Param("status") OrderStatus status);
}
```

`@Modifying` informs Spring Data that the query declared with `@Query` is a data-modifying operation and should execute via `executeUpdate()`, rather than being treated as a read query.

Bulk update/delete methods must run within a transaction. `@Transactional` can be placed at the service layer to group related operations into one transaction boundary:

```java
import java.time.LocalDateTime;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderMaintenanceService {

    private final PurchaseOrderRepository repository;

    public OrderMaintenanceService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public int archiveOldOrders(LocalDateTime cutoff) {
        return repository.updateStatusBefore(
                OrderStatus.ARCHIVED, cutoff);
    }
}
```

`@Modifying` only changes how Spring Data executes the query; it does not create a transaction boundary on its own. Ensure the method is called inside an active transaction, typically via `@Transactional` on the service or an appropriate repository method.

Query methods declared directly in a repository should not be assumed to automatically inherit the same transaction configuration as inherited CRUD methods. Placing a clear transaction boundary in the service layer makes it easier to control multiple operations within the same business flow.

## 5. Using flushAutomatically and clearAutomatically

`@Modifying` has two important attributes:

| Attribute | Default | Effect |
|---|---:|---|
| `flushAutomatically` | `false` | Flushes the persistence context before executing the modifying query. |
| `clearAutomatically` | `false` | Clears the persistence context after the modifying query executes successfully. |

Both can be enabled:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update PurchaseOrder p
    set p.status = :status
    where p.createdAt < :cutoff
    """)
int updateStatusBefore(
        @Param("status") OrderStatus status,
        @Param("cutoff") LocalDateTime cutoff);
```

### flushAutomatically

`flushAutomatically = true` instructs Spring Data to call `EntityManager.flush()` before running the bulk query.

Flushing synchronizes pending changes on managed entities to the database. This is important if the persistence context contains unwritten changes and the upcoming bulk statement may affect the same data.

If flushing is skipped, the ordering between pending in-memory changes and bulk DML can produce unexpected results relative to application expectations. Flushing beforehand ensures pending changes reach the database before the bulk statement runs.

Flushing is not committing. The transaction remains open and can still roll back all changes on error.

### clearAutomatically

`clearAutomatically = true` instructs Spring Data to call `EntityManager.clear()` after the bulk query executes successfully.

`clear()` detaches **all** managed entities from the current persistence context, not just those affected by the bulk statement. Subsequent queries will load entities from the database into a fresh/clean persistence context or create new managed instances.

When clear is enabled, Java variables holding references to old entities still exist, but those entities are detached. Property values in those variables do not change automatically. Re-query to obtain fresh instances.

Consider enabling both `flushAutomatically = true` and `clearAutomatically = true` together when a bulk method may run in a persistence context containing unflushed changes. Clearing without flushing can leave pending changes on detached entities unsynchronized with the database.

Example:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    delete from PurchaseOrder p
    where p.status = :status
    """)
int deleteAllWithStatus(@Param("status") OrderStatus status);
```

After this method, the current persistence context is cleared. Entities previously loaded through the repository must be re-queried before being used as managed entities.

## 6. Three ways to handle stale state

There is no single approach suited to every situation. Choose the operation based on the number of affected entities and the scope of the persistence context that needs synchronization.

### Approach 1: clear then re-query

Use when the bulk operation affects many entities and may render numerous objects in the persistence context stale:

```java
@Transactional
public PurchaseOrder updateAndReload(Long id) {
    entityManager.createQuery("""
        update PurchaseOrder p
        set p.status = :status
        where p.id = :id
        """)
        .setParameter("status", OrderStatus.ARCHIVED)
        .setParameter("id", id)
        .executeUpdate();

    entityManager.clear();

    return entityManager.find(PurchaseOrder.class, id);
}
```

After `clear()`, all old entities are detached. The subsequent `find()` reloads the data and returns a new managed instance.

Note: `clear()` affects the entire persistence context. If there are changes to preserve, flush before clearing. Old references do not automatically turn into references to the new instance.

### Approach 2: refresh a specific entity

Use `refresh(entity)` when only a single managed entity needs synchronization:

```java
@Transactional
public PurchaseOrder updateAndRefresh(Long id) {
    PurchaseOrder order =
            entityManager.find(PurchaseOrder.class, id);

    entityManager.createQuery("""
        update PurchaseOrder p
        set p.status = :status
        where p.id = :id
        """)
        .setParameter("status", OrderStatus.ARCHIVED)
        .setParameter("id", id)
        .executeUpdate();

    entityManager.refresh(order);

    return order;
}
```

`refresh()` re-reads state from the database and overwrites the current state of the managed entity. It cannot be used on detached or removed entities.

Be careful: if the entity has unflushed changes, `refresh()` can overwrite and discard those changes because in-memory state is replaced by database state. If changes need to be preserved, flush before refreshing.

If the bulk method uses `clearAutomatically = true`, the entity is already detached after the statement. You cannot call `refresh()` on that detached instance; re-query instead of refreshing.

### Approach 3: detach a specific entity

`entityManager.detach(entity)` separates a single entity from the persistence context:

```java
entityManager.detach(order);
```

This is useful when you only want to stop tracking one entity. However, `detach()` does not load new data and does not update the object's properties. The Java instance still holds its old values. To read the new state, re-query the entity by identifier.

Quick comparison:

| Operation | Scope | Loads fresh state? |
|---|---|---|
| `clear()` | All managed entities in the persistence context | No; must re-query. |
| `refresh(entity)` | A single managed entity | Yes; overwrites in-memory state with DB state. |
| `detach(entity)` | A single entity | No; only detaches from the persistence context. |
| `find()` after clear | Entity looked up by identifier | Yes; loads into the persistence context after clear. |

## 7. Example safe workflow with Spring Data JPA

A service method can perform a bulk update and then re-read the data:

```java
@Service
public class OrderMaintenanceService {

    private final PurchaseOrderRepository repository;

    public OrderMaintenanceService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder archiveAndReload(Long id) {
        repository.updateStatusById(
                id, OrderStatus.ARCHIVED);

        // The repository method is configured with clearAutomatically=true.
        // Re-query to obtain a fresh managed entity.
        return repository.findById(id)
                .orElseThrow(() ->
                        new IllegalArgumentException(
                                "Order not found"));
    }
}
```

The repository can declare:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update PurchaseOrder p
    set p.status = :status
    where p.id = :id
    """)
int updateStatusById(
        @Param("id") Long id,
        @Param("status") OrderStatus status);
```

After the modifying query runs, Spring Data clears the persistence context. The subsequent `findById()` reloads the entity. The returned result is a managed instance in the current persistence context, as long as the transaction remains active.

If you need to continue working with other previously loaded entities, remember that they were also detached on clear. Subsequent operations must reload or merge them intentionally; do not assume old instances are still managed.

## 8. Do bulk operations bypass lifecycle and cascades?

Yes. JPQL bulk update/delete acts directly on the database and does not process individual entities through JPA's normal lifecycle.

This has several consequences:

- Callbacks such as `@PreUpdate`, `@PostUpdate`, `@PreRemove`, and `@PostRemove` are not invoked for each entity affected by bulk DML.
- JPA cascade mechanisms such as `CascadeType.REMOVE` are not executed as when deleting entities one by one.
- Related entities are not automatically loaded and updated or deleted according to relationships.
- Database foreign key constraints still apply. A bulk delete statement can fail if child records still reference the parent and the schema forbids deletion.
- Business rules placed in entity methods or lifecycle callbacks do not run automatically.

If business logic requires cascades, validation, or per-entity callbacks, consider deleting/updating entities through the repository or handling the related steps separately. Bulk DML fits when you intentionally accept these lifecycle differences in exchange for performance.

It is also important to distinguish derived delete queries such as `deleteByStatus(...)` from a JPQL bulk delete declared with `@Modifying @Query`. Spring Data's derived delete can load matching entities and delete each entity individually so lifecycle callbacks run; JPQL bulk delete is a direct DML command with different semantics. Check the repository method type before relying on callbacks or cascades.

## 9. Impact on @Version and optimistic locking

Bulk update/delete bypasses standard optimistic locking checks. If an entity uses `@Version`, a bulk statement does not automatically increment the version like a normal managed entity update.

Example entity:

```java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private long version;

    // Other properties...
}
```

A bulk update that only changes `status` can leave the `version` column unchanged. Another transaction holding an old entity may not notice that the bulk operation changed the data, depending on how the statement and subsequent writes are executed.

When preserving optimistic locking control is necessary, explicitly design version conditions and increment the version in the bulk query, for example:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update PurchaseOrder p
    set p.status = :status,
        p.version = p.version + 1
    where p.id = :id
      and p.version = :expectedVersion
    """)
int updateStatusWithVersion(
        @Param("id") Long id,
        @Param("status") OrderStatus status,
        @Param("expectedVersion") long expectedVersion);
```

The returned updated row count can be used to determine the result:

- `1`: found a row with the matching identifier and version; update succeeded.
- `0`: no matching row; either the record does not exist or the version changed.

The application must decide how to distinguish these two cases if business logic requires it, such as checking existence separately or returning an appropriate conflict error.

Incrementing the version in the bulk query enables other transactions holding the old version to detect conflicts upon flush. However, the current persistence context still needs to be cleared or refreshed so it does not keep holding the old version and properties.

## 10. Common mistakes

| Mistake | Why it happens | Resolution |
|---|---|---|
| Reading an entity right after bulk update and getting old values | Managed entity was not synced with bulk DML. | Clear then re-query, or refresh the still-managed entity. |
| Calling `findById()` again yet still receiving stale data | First-level cache returns the already-managed instance. | Clear the persistence context before re-querying. |
| Calling `refresh()` after clearing | The old entity is detached and no longer in the persistence context. | Use `find()` or the repository to load a fresh instance. |
| Clearing without flushing pending changes | Unsynchronized changes may be lost when entities are detached. | Flush before clearing; consider `flushAutomatically=true`. |
| Assuming clear only detaches updated entities | `EntityManager.clear()` detaches all managed entities. | Evaluate persistence context scope or use refresh for one entity. |
| Expecting callbacks or cascades to run on bulk delete | Bulk DML bypasses normal entity lifecycles. | Handle relationships and logic separately or delete per entity. |
| Assuming `@Version` auto-increments during bulk update | Bulk DML bypasses automatic optimistic locking. | Check and increment version explicitly in the statement if needed. |
| Using `@Modifying` without a transaction | Modifying queries require an active transaction. | Place `@Transactional` on the service or appropriate method. |

## 11. When should bulk DML be used?

Bulk DML is suitable when:

- Many rows need to be updated or deleted under the same condition.
- Running per-entity lifecycle callbacks is unnecessary.
- Automatic JPA cascades for each deleted entity are unnecessary.
- You can actively manage the persistence context after the operation.
- Clear strategies exist for versions, foreign keys, and related business rules.

Consider per-entity operations when:

- Each entity requires different business logic.
- Domain methods must be called on individual objects.
- Lifecycle callbacks or JPA cascades are needed.
- Optimistic locking checks via the normal entity mechanism are needed.
- The record count is small enough that loading and processing each entity has acceptable cost.

Do not choose bulk DML just because it takes fewer lines of code. Balance performance against the bypassed JPA behaviors.

## 12. Checklist before and after bulk update/delete

Before running:

- Identify which entities may currently be managed in the persistence context.
- Check whether any changes are pending flush.
- Ensure the operation runs inside an appropriate transaction.
- Determine whether lifecycle callbacks, cascades, and `@Version` matter to business logic.
- Choose an explicit flush and clear strategy.

After running:

- If `clearAutomatically` is enabled, re-query entities that need to be used.
- If not clearing, refresh specific managed entities whose state was altered by the bulk operation.
- Do not call `refresh()` on detached entities.
- Do not reuse old instances as if they had been updated.
- Check the affected row count and handle cases where no rows matched.
- Test both database data and entity state re-read within the same transaction.

Bulk update and bulk delete help Spring Data JPA process large datasets efficiently with direct statements. In return, the persistence context is not automatically synchronized with statement results. Understanding the differences between flush, clear, refresh, and detach helps prevent reading stale data, losing unflushed changes, and unintentionally overwriting data.
