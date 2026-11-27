# Scope and Consistency of the First-Level Cache

In JPA, the first-level cache is the persistence context associated with an `EntityManager`. It holds the entities currently being managed within the scope of the persistence context, ensuring that an entity of the same type and primary key has only one managed instance within that context. As a result, JPA can track changes via dirty checking and avoid reloading the same entity multiple times within the same management scope.

The first-level cache always exists within a persistence context; an application does not enable or disable it like an optional cache. However, the lifetime of the persistence context, the timing of data synchronization, and how entities are refreshed determine whether the data seen by code is still fresh.

## 1. What is a persistence context?

A persistence context is a set of entity instances currently managed by an `EntityManager`. Each managed entity is identified by its entity type and primary key. Within the same persistence context, JPA maintains an identity guarantee: one entity identifier corresponds to one managed instance.

Example:

```java
User first = entityManager.find(User.class, 10L);
User second = entityManager.find(User.class, 10L);

System.out.println(first == second); // true within the same persistence context
```

The second call can return the exact same managed instance from the previous call, rather than creating another managed object for the same identifier. This means changes made to `first` are also visible when code reads through `second`, because both variables reference the same object.

The persistence context also has the following responsibilities:

- Holding the current state of managed entities.
- Tracking entity changes to perform dirty checking.
- Maintaining relationships between entities and their state.
- Coordinating persist, remove, merge, refresh, and flush operations.
- Guaranteeing entity identity within the management scope.

The first-level cache is not a map cache manually created by the application, nor is it a cache shared across the entire application. It is bound to a specific persistence context.

## 2. Lifecycle of the persistence context in Spring Data JPA

In a typical Spring Data JPA application, the `EntityManager` is managed through Spring and the transaction manager. When a service method annotated with `@Transactional` is invoked, Spring opens or joins a transaction and binds the `EntityManager` appropriate for that transaction to the current thread. Repositories invoked within the same transaction usually use the same persistence context.

Example:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class UserService {

    private final UserRepository users;

    public UserService(UserRepository users) {
        this.users = users;
    }

    @Transactional
    public void updateAndRead(Long id) {
        User first = users.findById(id).orElseThrow();
        first.setDisplayName("New name");

        User second = users.findById(id).orElseThrow();

        // Two reads in the same persistence context can return
        // the same managed instance.
        System.out.println(first == second); // true
        System.out.println(second.getDisplayName()); // New name
    }
}
```

In this example, the second read sees the new value because the managed entity was modified in memory. There is no need to call `save()` for JPA to recognize the change; dirty checking detects the modification when the persistence context flushes.

### Default scope and special cases

- **Transaction-scoped persistence context:** the common model with Spring Data JPA. The persistence context is bound to the transaction; when the transaction ends, the corresponding context is closed or terminated according to how Spring/the provider manages it.
- **Extended persistence context:** can span multiple transactions in specialized JPA models. You should not assume a standard Spring Boot application uses this model.
- **Open EntityManager in View (OSIV):** if enabled, the `EntityManager` can remain open throughout an entire HTTP request to support lazy loading at the web layer. This extends the persistence context scope across the request, but does not turn it into an application-wide cache, nor does it mean the entire request runs inside a single database transaction.

Therefore, when analyzing stale data, you need to determine precisely which `EntityManager`/persistence context is being used and what scope it lives in.

## 3. How does the first-level cache work?

### find() and identity within the same context

When calling:

```java
User user = entityManager.find(User.class, 10L);
```

JPA checks the persistence context. If an entity with that identifier is already managed, `find()` returns the managed instance. If not, the provider fetches data from the database, creates the entity instance, and places it into the persistence context.

This means:

- A first `find()` call may need to query the database.
- Subsequent `find()` calls for the same entity within the same persistence context can be served from the first-level cache.
- When another context is created, that entity is not automatically shared into the new context.

### JPQL queries can still query the database

You should not infer that the first-level cache turns every query into a cache hit. A JPQL query such as:

```java
List<User> users = entityManager.createQuery(
    "select u from User u where u.active = true",
    User.class
).getResultList();
```

may still need to execute SQL so the database can evaluate the condition and find matching rows. When the result contains an entity that is already in the persistence context, the provider reuses the corresponding managed instance instead of creating a second managed instance for the same identifier.

Consequently, the query can read a fresh result set from the database, yet the returned object still retains its managed state in the persistence context. JPA does not automatically refresh all fields of a managed entity just because a query was re-executed.

### The first-level cache stores managed entities, not all query results

The first-level cache primarily manages entity instances. It should not be treated as a general-purpose cache for:

- DTO projections.
- Scalar results such as `count(*)`.
- Arbitrary JPQL/native queries.
- Arbitrary search results.

Hibernate's query cache, if configured, is a different mechanism. The second-level cache is also a separate mechanism that can share entity data across multiple persistence contexts depending on provider configuration.

## 4. Dirty checking and when data is written to the database

When a managed entity is modified, JPA records its state in the persistence context. The provider can detect differences between the current state and the initial snapshot upon flush.

```java
@Transactional
public void renameUser(Long id) {
    User user = entityManager.find(User.class, id);
    user.setDisplayName("Lan");

    // SQL UPDATE does not necessarily occur immediately at the setter line.
    // SQL is typically emitted on flush or commit.
}
```

### flush() synchronizes pending changes

`EntityManager.flush()` instructs the provider to synchronize changes in the persistence context with the database using SQL. Flushing does not end the transaction and does not commit data.

```java
entityManager.flush();
```

After flushing:

- The necessary SQL statements have been sent within the current transaction.
- The entity remains managed and stays in the first-level cache.
- Subsequent modifications can still undergo dirty checking.
- The transaction can still roll back.

Therefore, flushing is neither a cache-clearing operation nor does it make data durable independently of the transaction.

### Commit typically triggers flush

When a transaction commits, the JPA provider synchronizes the required changes before the transaction is committed. Depending on the flush mode and provider, a flush can also occur before a query when necessary to ensure the query sees changes in the persistence context.

If you need to pinpoint an SQL error at a specific location, you can flush explicitly. This is useful for detecting a constraint violation or optimistic locking failure early, though it does not alter the lifetime of the first-level cache.

## 5. Why can an entity become stale?

The first-level cache guarantees identity within a single persistence context; it does not guarantee that an entity always reflects the latest changes in the database made by another transaction or another system.

Example:

1. Transaction A loads `User#10` and gets `displayName = "An"`.
2. Entity `User#10` is held in A's persistence context.
3. Transaction B updates the database to `displayName = "Binh"` and commits.
4. Transaction A calls `find(User.class, 10L)` again.
5. If the entity is still managed in persistence context A, JPA can return the existing instance with the value `"An"`.

Transaction A does not automatically know that transaction B modified that row. This is the stale state of an entity in context A.

Consistency also depends on the database isolation level, transaction snapshots, the cache provider, and how queries are executed. The first-level cache only manages state within the context; it does not replace database concurrency control or isolation mechanisms.

### How to handle cases requiring fresh data

There are several options depending on requirements:

- Call `refresh(entity)` to reload the state of a managed entity from the database.
- Call `detach(entity)` if you only want a single entity to stop being managed, then reload it.
- Call `clear()` to detach all entities in the persistence context, then re-query.
- End the current transaction/persistence context and read in a new transaction when a fresh context is needed.

No single option fits every scenario. Consider unflushed changes before calling refresh or clear.

## 6. Distinguishing refresh, detach, clear, and merge

| Operation | Effect | Scope |
|---|---|---|
| `refresh(entity)` | Reloads state from the database, overwriting unflushed changes on that entity | A single managed entity |
| `detach(entity)` | Removes the entity from the persistence context; the entity becomes detached | A single entity |
| `clear()` | Detaches all managed entities | The entire persistence context |
| `merge(entity)` | Copies state from a new/detached entity into a managed instance and returns that managed instance | The merged entity |

### refresh(): re-reading database data

```java
@Transactional
public void reloadUser(Long id) {
    User user = entityManager.find(User.class, id);

    entityManager.refresh(user);

    // user's fields are reloaded from the database.
}
```

`refresh()` requires a managed entity. This operation can overwrite unflushed changes on the entity. If the row has been deleted or no longer exists, refresh may fail. Cascade refresh can be used if the mapping and business logic require it.

### detach(): stopping management of an entity

```java
entityManager.detach(user);
```

After detaching, changes to the Java object are no longer tracked by the persistence context. To persist the modified state, you must merge or perform another appropriate update flow.

### clear(): emptying the persistence context

```java
entityManager.clear();
```

Clear does not delete database data. It only detaches all managed entities in the context. If there are unflushed changes, they may not be written and will be lost from dirty checking scope.

When you need to flush changes before clearing, the order must be:

```java
entityManager.flush();
entityManager.clear();
```

### merge(): does not turn the old object into a managed one

```java
User detached = obtainDetachedUser();

User managed = entityManager.merge(detached);

// detached remains a detached object.
// managed is the managed instance.
managed.setDisplayName("Updated");
```

This is a common point of confusion: `merge()` copies state into a managed instance; it does not re-attach the original detached object itself.

## 7. Relationship with Spring Data repositories and save()

Spring Data JPA repositories normally use a Spring-managed `EntityManager`. Within a service transaction, repositories participating in the same transaction usually operate on the same persistence context.

Example:

```java
@Transactional
public void updateTwice(Long id) {
    User first = userRepository.findById(id).orElseThrow();
    first.setDisplayName("First change");

    User second = userRepository.findById(id).orElseThrow();

    // Same persistence context: second sees First change.
    System.out.println(second.getDisplayName());

    second.setActive(false);
}
```

For a managed entity, dirty checking is sufficient to persist changes upon flush/commit. There is no need to call `save()` just to tell JPA that the entity has changed.

However, Spring Data JPA's `save()` typically chooses `persist()` for an entity identified as new and `merge()` for an existing entity. If `merge()` is used, continue working with the instance returned by `save()` when a managed state is needed:

```java
User managed = userRepository.save(detached);
managed.setDisplayName("New value");
```

`save()` does not mean SQL is always emitted immediately; SQL may only be sent at flush or commit. Furthermore, you should not repeatedly call `save()` as a way to refresh a stale entity. Use `refresh()`, a new context, or an appropriate query.

## 8. The first-level cache and other caches

| Mechanism | Scope | Enable/disable | Role |
|---|---|---|---|
| First-level cache | One persistence context/`EntityManager` | Always attached to the persistence context | Manages identity, managed state, and dirty checking |
| Second-level cache | Shared across persistence contexts in the same provider configuration | Optional, provider-dependent | Reuses entity state across `EntityManager` instances |
| Query cache | Caches query results per provider mechanism | Optional | Reuses certain query results; does not replace entity state |
| Application cache | Application-defined scope, e.g., Caffeine/Redis | Design-dependent | Caches business data or responses by custom key |

You should not call the first-level cache a global cache. Two different `EntityManager` instances can manage the same database row while holding two different Java instances and two different snapshots.

## 9. Optimistic locking and consistency across concurrent transactions

The first-level cache does not prevent two different transactions from reading and updating the same row concurrently. If the business logic needs to detect concurrent updates, optimistic locking with `@Version` can be used.

```java
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Version;

@Entity
public class Product {

    @Id
    private Long id;

    private String name;

    @Version
    private Long version;

    protected Product() {
    }

    public void rename(String name) {
        this.name = name;
    }
}
```

When the provider updates a versioned entity, the SQL statement typically checks the current version and increments it. If another transaction has already updated the row first, the update can fail with an optimistic locking exception.

`@Version` protects against data contention between transactions; the first-level cache primarily guarantees identity and manages state inside a single persistence context. The two mechanisms solve different problems.

When using bulk JPQL/native updates, pay special attention because bulk operations do not go through per-entity dirty checking and do not inherently perform optimistic locking like regular entity updates.

## 10. Scope and thread-safety considerations

- **`EntityManager` is not thread-safe:** do not arbitrarily share an `EntityManager` or a managed entity across multiple threads. Spring typically provides a proxy that selects the `EntityManager` bound to the current thread/transaction; do not hold onto and share the underlying object across threads.
- **Do not use managed entities as long-lived DTOs:** once a transaction/context ends, entities may become detached. Transfer the necessary data into DTOs or value objects.
- **Lazy loading depends on the context:** accessing lazy associations after the `EntityManager` has closed can cause lazy initialization errors. OSIV can mask some of these errors, but does not replace explicit fetch design.
- **Read-only transactions do not make entities immutable:** `@Transactional(readOnly = true)` allows the provider to optimize flush behavior, but it is not a data protection mechanism and does not make objects immutable.
- **Do not keep a context open too long:** a large persistence context can consume memory and run dirty checking over many entities. For batch processing, consider batching flush/clear operations and managing transaction boundaries appropriately.

## 11. Testing scope and consistency

Use integration tests with an appropriate database and transaction manager to verify actual behavior. Key test cases:

1. Call `find()` twice with the same ID within one `EntityManager` and verify both variables reference the same managed instance.
2. Modify an entity and read it again within the same persistence context; verify the in-memory change is visible immediately.
3. Flush, clear, and reload the entity; verify the data is read from the synchronized database state.
4. Use two separate transactions: the first holds a managed entity, the second updates and commits; verify how the first transaction sees the stale entity, then test refresh.
5. Test `detach()` and `merge()`: the detached object no longer undergoes dirty checking, while the instance returned from merge is managed.
6. Test optimistic locking with two transactions updating the same entity version.
7. Test bulk updates: after the query, already-managed entities may be stale; clear/refresh and reload to verify the data.

A note on unit/integration tests: do not put `@Transactional` on the test itself if your goal is to observe actual commit timing in the service. A transaction managed by the test framework can cause the service transaction to join the test's transaction, altering flush/commit timing.

## 12. Workflow for diagnosing stale entities

When the application reads stale data, check in the following order:

1. Identify the `EntityManager`/persistence context managing the entity.
2. Check whether the entity was previously loaded in that context.
3. Check whether another transaction, bulk query, or native SQL updated the same row.
4. Determine whether changes in the context have been flushed yet.
5. If fresh data is needed, choose `refresh(entity)`, detach/clear and reload, or end the context and read in a new transaction.
6. If multiple transactions write concurrently, add optimistic locking or design appropriate isolation/concurrency control.
7. Check for OSIV or an extended persistence context if the context lives longer than expected.

## Conclusion

The first-level cache is the `EntityManager`'s persistence context, not an application-wide shared cache. It preserves identity and managed entity state within the scope of the context, supports dirty checking, and reduces repeated loads of the same entity. However, managed entities can become stale when the database changes via another transaction or bulk operation.

Understanding the `EntityManager` lifecycle and distinguishing `flush()`, `refresh()`, `detach()`, `clear()`, and `merge()` are essential for keeping data consistent. When you need to detect concurrent updates across transactions, use optimistic locking or an appropriate database mechanism; do not expect the first-level cache to solve it for you.
