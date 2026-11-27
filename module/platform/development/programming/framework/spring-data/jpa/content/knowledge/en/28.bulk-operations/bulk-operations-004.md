# flushAutomatically and clearAutomatically in Spring Data JPA

When using Spring Data JPA to run bulk update or delete statements with `@Modifying`, the database may have changed while managed entities in the persistence context still hold old values. The two attributes `flushAutomatically` and `clearAutomatically` control when pending changes are synchronized and when managed state is cleared after the bulk statement.

- `flushAutomatically = true`: instructs Spring Data JPA to call `EntityManager.flush()` before executing the modifying query.
- `clearAutomatically = true`: instructs Spring Data JPA to call `EntityManager.clear()` after executing the modifying query.

Both attributes belong to the `@Modifying` annotation. They serve different purposes and do not replace `@Transactional`.

## 1. Why do bulk updates/deletes need flush and clear?

### The persistence context holds entity state

Within a transaction, JPA normally manages loaded or persisted entities through the persistence context. When modifying a managed entity, Hibernate/JPA records changes in memory and synchronizes SQL statements to the database at flush time.

Example:

```java
User user = entityManager.find(User.class, 10L);
user.setActive(false);
```

After `setActive(false)`, the entity has changed in the persistence context. The SQL `UPDATE` may not have been sent to the database yet. Detecting changes and writing SQL in this manner is commonly called dirty checking.

Bulk JPQL update/delete works differently from modifying individual entities:

```java
UPDATE User u SET u.active = false WHERE u.lastLoginAt < :cutoff
```

The statement is executed directly by the database across multiple rows. JPA does not load each `User` into an object and apply dirty checking. Consequently, already-managed `User` objects may not automatically receive the new values after the bulk statement.

This is the root of two problems:

1. Pending entity changes exist in the persistence context, yet the bulk query runs before those changes are synchronized.
2. The bulk query has updated the database, yet managed entities still hold old values.

`flushAutomatically` addresses the first problem by flushing before the query. `clearAutomatically` addresses the second problem by clearing the persistence context after the query.

## 2. flushAutomatically: flushing before running a modifying query

### Meaning

Declaring:

```java
@Modifying(flushAutomatically = true)
```

instructs Spring Data JPA to call:

```java
entityManager.flush();
```

immediately before executing the update/delete statement annotated with `@Modifying`.

Flushing synchronizes pending changes in the persistence context to the database within the current transaction. Flushing does not mean committing. The transaction can still roll back afterward.

For example, the application modifies an entity's state and then runs a bulk query:

```java
User user = entityManager.find(User.class, 10L);
user.setActive(true);

// Bulk query runs after the change above.
int updated = userRepository.deactivateInactiveUsers(cutoff);
```

If you need to guarantee that pending changes are sent to the database before the bulk statement, use `flushAutomatically = true`. This makes the execution order explicit: pending changes are flushed first, then the bulk query runs.

### Repository example

Suppose the `User` entity has `active` and `lastLoginAt` properties:

```java
import java.time.LocalDateTime;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface UserRepository extends JpaRepository<User, Long> {

    @Modifying(flushAutomatically = true)
    @Query("""
        update User u
           set u.active = false
         where u.lastLoginAt < :cutoff
        """)
    int deactivateInactiveUsers(
        @Param("cutoff") LocalDateTime cutoff
    );
}
```

`flushAutomatically = true` is useful when the persistence context may contain changes that need to be written before the bulk statement, or when you want explicit control over synchronization order.

### Flushing may expose errors earlier

Because flushing sends pending changes to the database, errors can surface right at the flush step, such as:

- Unique constraint or foreign key violations.
- Values violating NOT NULL constraints.
- Optimistic locking errors when updating entities.
- Data type conversion errors or SQL errors.

These are not errors created by the attribute itself; flushing causes pending operations to execute earlier so errors are detected at a more deterministic point.

### When is enabling it unnecessary?

If there are no pending changes that need synchronization before the bulk query, or the default JPA/provider flush mechanism already satisfies the requirement, you can keep the default value `false`.

Note that `flushAutomatically = false` means Spring Data JPA does not explicitly call `flush()` via this attribute. The provider may still flush automatically according to `FlushModeType.AUTO` and JPA synchronization rules. When you need an explicit guarantee that all pending changes are flushed before the modifying query, enable this attribute.

## 3. clearAutomatically: clearing the persistence context after a modifying query

### Meaning

Declaring:

```java
@Modifying(clearAutomatically = true)
```

instructs Spring Data JPA to call:

```java
entityManager.clear();
```

after the modifying query executes.

`EntityManager.clear()` removes all managed entities from the current persistence context. Java objects that the code still holds remain in memory, but they transition to the detached state. JPA no longer performs dirty checking on those objects in the cleared persistence context.

This is important because the bulk query modifies data directly in the database, whereas previously loaded entities may still contain stale data.

### Stale state example

Suppose a service loads a user before calling a bulk update:

```java
User user = userRepository.findById(10L).orElseThrow();

userRepository.deactivateInactiveUsers(cutoff);

// The user variable may still contain active=true,
// even though the database was bulk-updated to active=false.
System.out.println(user.isActive());
```

The bulk query does not automatically synchronize new values into the managed `user` object. If the application continues reading this entity after the query, it may observe stale state.

Enabling `clearAutomatically = true` clears the persistence context after the query. When you need to read the entity again, reload it from the repository or EntityManager:

```java
@Modifying(clearAutomatically = true)
@Query("update User u set u.active = false where u.lastLoginAt < :cutoff")
int deactivateInactiveUsers(
    @Param("cutoff") LocalDateTime cutoff
);
```

After the persistence context is cleared, you can call `findById()` to obtain a fresh managed instance with current data inside the transaction:

```java
userRepository.deactivateInactiveUsers(cutoff);

User refreshed = userRepository.findById(10L).orElseThrow();
System.out.println(refreshed.isActive()); // false if user matched the bulk update condition
```

The example above assumes the user has `lastLoginAt` earlier than `cutoff` and the statement executed successfully.

### Clear affects the entire persistence context

`clearAutomatically = true` does not only clear entities affected by the update/delete statement. It clears every managed entity in the current persistence context.

Consequences:

- All previously loaded entities become detached.
- Subsequent changes on detached objects are no longer automatically dirty-checked.
- Lazy relationships on detached objects may fail to load if uninitialized and no longer backed by an active persistence context.
- If you need to continue updating an entity, reload it or re-manage it in an appropriate transaction/persistence context.

Because of its broad impact, do not enable automatic clearing mechanically in methods managing many entities that still require further operations.

## 4. Combining flushAutomatically and clearAutomatically

When a persistence context may contain unflushed changes and the bulk query may also make managed entities stale, you can enable both:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
```

Spring Data JPA's execution order is:

1. Call `EntityManager.flush()` before the modifying query if `flushAutomatically = true`.
2. Execute the update/delete statement using `executeUpdate()`.
3. Call `EntityManager.clear()` after the statement if `clearAutomatically = true`.

Thus, pending changes are flushed before the query; after the query updates the database, the persistence context is cleared to prevent continued use of stale entities.

Complete repository-level example:

```java
import java.time.LocalDateTime;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface UserRepository extends JpaRepository<User, Long> {

    @Modifying(
        flushAutomatically = true,
        clearAutomatically = true
    )
    @Query("""
        update User u
           set u.active = false
         where u.lastLoginAt < :cutoff
        """)
    int deactivateInactiveUsers(
        @Param("cutoff") LocalDateTime cutoff
    );
}
```

Here, `int` is the number of rows affected by the update statement according to the `executeUpdate()` result. The `User` entity and properties used in JPQL must match the project's entity model.

## 5. These two attributes do not replace a transaction

`@Modifying` tells Spring Data JPA that the query declared with `@Query` is a data-modifying statement that must execute via the modifying query mechanism. The flush/clear attributes control the persistence context around that statement.

They do not open a transaction on their own and do not commit transactions.

Bulk update/delete statements must run inside a transaction. `@Transactional` can be placed at the service layer so the entire business operation has a clear transaction boundary:

```java
import java.time.LocalDateTime;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserMaintenanceService {

    private final UserRepository userRepository;

    public UserMaintenanceService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    @Transactional
    public int deactivateInactiveUsers(LocalDateTime cutoff) {
        return userRepository.deactivateInactiveUsers(cutoff);
    }
}
```

When the service finishes normally, the transaction interceptor performs the commit via the transaction manager. If an error occurs and rollback rules apply, the transaction can roll back. Flushing only synchronizes SQL within the transaction; it does not make data durable independently of the transaction.

You can place `@Transactional` directly on the repository query method if application design requires it. However, placing the transaction in the service is usually more convenient when a business operation consists of multiple repository calls that must commit or roll back together.

## 6. Comparing defaults and configurations

Both attributes of `@Modifying` default to `false`.

| Configuration | Before query runs | After query runs | Primary impact |
|---|---|---|---|
| Default | Does not instruct Spring Data JPA to flush explicitly | Does not auto-clear | Minimal impact on persistence context; stale state must be handled manually if present |
| `flushAutomatically = true` | Flushes pending changes | Does not auto-clear | Ensures pending changes are synchronized before the query |
| `clearAutomatically = true` | Does not request explicit flush | Clears entire persistence context | Prevents reusing stale entities, but may detach many entities |
| Both `true` | Flushes before query | Clears after query | Synchronizes pending changes then evicts managed entities from context after bulk operation |

There is no single right configuration for every repository. Choose based on the persistence context state and the operations occurring after the bulk query.

## 7. Important considerations when using bulk update/delete

### Clearing can discard unflushed changes

This is the easiest mistake to make when enabling `clearAutomatically` alone.

Suppose code modified a managed entity, but that change has not been flushed yet. If a bulk query runs and `EntityManager.clear()` is called afterward, the unsynchronized changes may be dropped from the persistence context.

If those changes must be saved before the bulk query, enable `flushAutomatically = true` at the same time:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
```

If you do not want to flush the entire persistence context, consider a different transaction boundary design or manually flushing/clearing at a controlled business point.

### Bulk queries bypass dirty checking and normal entity lifecycles

JPQL bulk update/delete operates directly on the database. It does not load entities one by one and invoke setters. Therefore, do not expect a bulk query to automatically:

- Invoke entity lifecycle callbacks such as `@PreUpdate`, `@PostUpdate`, `@PreRemove`, or `@PostRemove` for each entity.
- Perform cascade remove/update as when operating through the entity graph.
- Synchronize state into managed entities.
- Automatically apply per-entity optimistic locking as in normal entity updates.

If business logic depends on lifecycle callbacks, cascades, or optimistic locking, evaluate loading and updating entities individually, or explicitly implement the corresponding rules in the bulk query and transaction.

In particular, a bulk update on an entity with a `@Version` field must not be assumed to automatically increment and check the version like normal dirty checking. If concurrency protection is required, design explicit version conditions and version increments, or use an appropriate entity-level update mechanism.

### Flush does not mean commit

After `EntityManager.flush()`, SQL has been sent within the current transaction. An error occurring afterward can still roll back the entire transaction. Do not use flush as confirmation that data has been committed.

### Clear does not update Java objects held in variables

After `clear()`, Java variables still reference the old objects, but those objects are detached. Clearing does not modify object fields to the new database values. Reload the entity if you need to read fresh state.

### Avoid automatic clearing if many entities still need further processing

If a service is processing multiple entities and still needs to update them after the bulk query, clearing the entire persistence context removes dirty checking for subsequent operations. When only a few entities are affected, consider `EntityManager.refresh(entity)` for an entity that is still managed, or clear/reload at an appropriate boundary.

## 8. Choosing configuration by scenario

| Scenario | Recommended configuration | Reason |
|---|---|---|
| Only running bulk update, no pending changes, and managed entities are not reused | Keep defaults | No extra flush/clear needed when there is no sync risk |
| Pending entity changes exist and must be written before the bulk query | `flushAutomatically = true` | Flushes before running the query |
| Need to re-read potentially managed entities after the bulk query | `clearAutomatically = true` or controlled manual refresh/clear | Avoids reading stale values from the persistence context |
| Pending changes exist and stale entities must be evicted after the bulk query | Consider enabling both | Flushes before, clears after |
| Still need dirty checking on multiple managed entities after the query | Do not enable automatic clear indiscriminately | Clearing detaches all managed entities |

### A quick decision checklist

Before adding the two attributes, answer three questions:

1. Might the persistence context have unflushed changes that need to be written before the bulk statement? If yes, consider `flushAutomatically = true`.
2. After the bulk statement, might the code read previously loaded entities? If yes, you need to clear or refresh to avoid stale state.
3. After the query, does the code still need those entities in a managed state? If yes, consider refreshing individual entities or performing a controlled reload instead of clearing the entire context.

## 9. Testing flush and clear behavior

Test with integration tests using Spring Data JPA and an appropriate database, because the goal is to verify coordination across the repository proxy, EntityManager, transaction manager, and JPA provider.

A useful test can verify:

- Persist or modify an entity in a transaction without manually calling flush.
- Call a repository method with `flushAutomatically = true`, then verify the bulk query sees the necessary data.
- Call a method with `clearAutomatically = true`, then verify `EntityManager.contains(entity)` returns `false` for the previously managed entity.
- Reload the entity via the repository and confirm the read values reflect the bulk update result.
- Check the updated row count returned by the repository method.
- Test rollback: if an error occurs after flush but before commit, changes must still roll back with the transaction.

With `@DataJpaTest`, keep in mind that tests normally run inside a framework-managed transaction. When testing commit timing or service transaction behavior, design tests so transaction boundaries execute as in production. Do not inspect only the old Java object because it becomes detached after clear; re-query the data.

## 10. Common mistakes

- **Forgetting `@Modifying`:** Spring Data JPA may execute the query along the read-query path instead of `executeUpdate()`; the DML statement will not execute properly. Add `@Modifying` to update/delete `@Query` methods.
- **Thinking `@Modifying` creates a transaction:** This annotation selects the query execution mode, not a transaction. Place `@Transactional` on the service or repository as designed.
- **Enabling `clearAutomatically` without considering pending changes:** Clearing can discard unflushed changes. If those changes must be kept, consider enabling `flushAutomatically` at the same time.
- **Assuming clear only affects updated rows:** `EntityManager.clear()` detaches all managed entities in the current persistence context.
- **Continuing to use an object after clear as a managed entity:** The object still exists, but it is detached; reload or re-manage it appropriately.
- **Thinking flush is commit:** Flush only synchronizes SQL inside a transaction. Commit/rollback is still controlled by the transaction manager.
- **Expecting bulk queries to trigger callbacks or cascades:** Bulk DML bypasses the normal entity update pipeline. Handle required business logic manually or use per-entity operations.

## Conclusion

`flushAutomatically` controls synchronizing pending changes before a modifying query; `clearAutomatically` controls removing all managed entities from the persistence context after the query. Use flush when you need to guarantee database write order, use clear when you need to prevent stale entities after bulk update/delete, and combine both when the business logic requires both behaviors.

Always run modifying queries inside an appropriate transaction and remember that flush does not commit, clear does not update old Java objects, and bulk update/delete does not go through dirty checking and per-entity lifecycles.
