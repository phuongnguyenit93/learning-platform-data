# Clearing the Persistence Context Before Verifying Reloading

In JPA, a managed entity is typically held in the persistence context. When a test calls a repository to look up the entity again by the same ID, JPA can return the exact same managed object instead of re-reading data from the database. This causes some tests to pass even though they never actually verified the reloading process.

To test reloading explicitly, synchronize changes you want to keep down to the database with `flush()`, then call `clear()` to detach all entities from the persistence context. When the test looks up the entity again, JPA must bring an instance into the context from the underlying store according to current cache and transaction behavior. This approach separates in-memory object state from state synchronized to the database.

## Learning Objectives

After this lesson, you can:

- Explain the persistence context and JPA's first-level cache.
- Understand why looking up an entity by the same ID can return the exact same managed instance.
- Distinguish `flush()`, `clear()`, `detach()`, and `refresh()`.
- Use `EntityManager.clear()` before verifying entity reloading.
- Write integration tests proving data is reloaded after the persistence context is cleared.
- Avoid losing unflushed changes when calling `clear()`.
- Understand why `clear()` neither commits nor starts a new transaction.
- Recognize the impact of the second-level cache, transaction isolation, and lazy loading.
- Choose the right tool among `EntityManager`, Spring Data repositories, and Spring Boot's `TestEntityManager`.

## 1. What Is the Persistence Context?

The persistence context is the region tracking entities currently managed by an `EntityManager`. For each entity with an identifier, the persistence context maintains one representative instance within that context's scope. This underpins JPA's identity guarantee: within the same persistence context, looking up the same entity identity generally returns the same Java object.

Example:

~~~java
AppUser first = entityManager.find(AppUser.class, 10L);
AppUser second = entityManager.find(AppUser.class, 10L);

assertSame(first, second);
~~~

If the entity with ID `10` is already managed, the subsequent lookup can immediately return that object from the persistence context. JPA does not need to instantiate another object just because the test called `find()` again.

The persistence context also tracks entity changes. When code modifies a field on a managed entity, the provider can detect the change via dirty checking and synchronize it to the database on flush.

We can visualize this as:

~~~mermaid
flowchart TD
    A["EntityManager.find(AppUser, 10)"] --> B{"Entity 10 already managed?"}
    B -->|Yes| C["Return existing instance from persistence context"]
    B -->|No| D["Load data and create managed instance"]
    D --> E["Place instance into persistence context"]
    E --> F["Return entity to caller"]
~~~

In Spring Data JPA, repositories typically use `EntityManager` under the hood. Therefore, calling `repository.findById(id)` does not guarantee the database is queried every time. If the entity is already in the persistence context, JPA can return the managed instance.

## 2. Why Do Tests Need Clear Before Verifying Reload?

Suppose a test saves a user, changes the name on the object, and calls the repository to find by ID again:

~~~java
AppUser user = repository.save(new AppUser("Alice"));
Long id = user.getId();

user.rename("Alicia");

AppUser loaded = repository.findById(id).orElseThrow();
~~~

If `user` is still managed in the persistence context, `loaded` may be the exact same `user` reference. The following assertion can pass:

~~~java
assertEquals("Alicia", loaded.getDisplayName());
~~~

Yet this assertion only proves the in-memory object currently holds the name Alicia. It does not prove the database stored that value or that JPA can reload it once the old object is no longer managed.

This is a source of false positives in persistence tests. The test inadvertently asserts the state of the first-level cache instead of proving data was synchronized and can be reloaded.

After calling `flush()` and `clear()`, the persistence context no longer holds the old entity. When looked up again, JPA must load a managed instance into the context. The test can verify both identity and data:

~~~java
entityManager.flush();
entityManager.clear();

AppUser reloaded = repository.findById(id).orElseThrow();

assertNotSame(user, reloaded);
assertEquals("Alice", reloaded.getDisplayName());
~~~

The reloaded value depends on what was flushed before clearing. If only the initial insert was flushed and the object was modified without flushing the edit, the database still stores Alice. After clearing, the lookup shows Alice, not the unsynchronized in-memory modification.

## 3. Distinguishing `flush`, `clear`, `detach`, and `refresh`

These four operations serve different purposes:

| Operation | Effect | Ends the Transaction? |
|---|---|---|
| `flush()` | Synchronizes pending changes in the persistence context down to the database | No |
| `clear()` | Detaches all managed entities from the persistence context | No |
| `detach(entity)` | Detaches one specific entity | No |
| `refresh(entity)` | Reloads database state into a single managed entity | No |

### `flush()`: Synchronize Changes

~~~java
entityManager.flush();
~~~

`flush()` instructs the JPA provider to synchronize pending changes in the persistence context with the database. It can generate INSERT, UPDATE, or DELETE statements.

Flush does not commit the transaction. The transaction remains active, and changes sent to the database can still be rolled back when the transaction ends.

### `clear()`: Clear the Entire Persistence Context

~~~java
entityManager.clear();
~~~

`clear()` detaches all managed entities. After this call, Java objects held by the test still exist, but they are no longer tracked by the `EntityManager`.

Unflushed changes can be left behind with the discarded context. Therefore, if you want to retain data before clearing the context, flush first.

### `detach()`: Detach One Entity

~~~java
entityManager.detach(user);
~~~

`detach(user)` removes only one entity from the persistence context. Other entities and their relationships may remain managed. Use this operation when a test only needs to detach a specific object.

### `refresh()`: Reload State of One Managed Entity

~~~java
entityManager.refresh(user);
~~~

`refresh(user)` overwrites the in-memory state of a managed entity with state read from the database. The entity remains managed after refresh.

Unlike `clear`, `refresh` requires a managed entity and refreshes only the specified entity. You cannot call `refresh` on a detached entity; you must first find or merge the entity into an appropriate context.

## 4. The Right Sequence: Flush, Then Clear, Then Find

When the goal is verifying entity reloading after the persistence context no longer holds the old instance, the usual sequence is:

1. Create or update the entity.
2. Call `flush()` to synchronize the changes under test down to the database.
3. Save the ID needed for querying.
4. Call `clear()` to detach all entities.
5. Use the repository or `EntityManager` to look up the entity by ID.
6. Assert the new instance and reloaded values.

~~~mermaid
flowchart TD
    A["Create or update entity"] --> B["EntityManager.flush()"]
    B --> C["SQL synchronized within transaction"]
    C --> D["EntityManager.clear()"]
    D --> E["Old entity becomes detached"]
    E --> F["findById(id)"]
    F --> G["JPA loads managed instance into context"]
    G --> H["Assert identity and data"]
~~~

Do not reverse the order to `clear` before `flush`. Once cleared, the old entity is detached; its unflushed changes are no longer tracked by the persistence context for synchronization as before.

A short example:

~~~java
AppUser user = repository.save(new AppUser("Alice"));

entityManager.flush();
Long id = user.getId();

entityManager.clear();

AppUser reloaded = repository.findById(id).orElseThrow();

assertNotSame(user, reloaded);
assertEquals("Alice", reloaded.getDisplayName());
~~~

In this example, the insert is flushed before clearing. The subsequent lookup cannot retrieve the old instance from the first-level cache because the context was cleared.

## 5. Integration Test Example with Spring Data JPA

Suppose we have an entity:

~~~java
@Entity
@Table(name = "app_user")
public class AppUser {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String displayName;

    protected AppUser() {
    }

    public AppUser(String displayName) {
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getDisplayName() {
        return displayName;
    }

    public void rename(String displayName) {
        this.displayName = displayName;
    }
}
~~~

Repository:

~~~java
public interface AppUserRepository
        extends JpaRepository<AppUser, Long> {
}
~~~

Test using `@DataJpaTest`:

~~~java
@DataJpaTest
class AppUserRepositoryReloadTest {

    @Autowired
    AppUserRepository repository;

    @PersistenceContext
    EntityManager entityManager;

    @Test
    void reloadsEntityAfterClearingPersistenceContext() {
        AppUser user = repository.save(new AppUser("Alice"));

        entityManager.flush();
        Long id = user.getId();

        // Modify object in memory without flushing yet.
        user.rename("Alicia");

        AppUser foundBeforeClear =
            repository.findById(id).orElseThrow();

        // Same persistence context, so JPA returns the managed instance.
        assertSame(user, foundBeforeClear);
        assertEquals("Alicia", foundBeforeClear.getDisplayName());

        // Evict the old entity from the first-level cache.
        entityManager.clear();

        assertFalse(entityManager.contains(user));

        AppUser reloaded = repository.findById(id).orElseThrow();

        assertNotSame(user, reloaded);
        assertTrue(entityManager.contains(reloaded));
        assertEquals("Alice", reloaded.getDisplayName());
    }
}
~~~

This test clearly demonstrates two states:

- Before `clear`, `findById` returns the same managed object, so it sees the unflushed change Alicia.
- After `clear`, the old entity is detached. The next lookup loads the flushed state in the database, namely Alice.

`@DataJpaTest` normally runs inside a test-managed transaction and rolls back after each method. Clearing the persistence context does not end this transaction. Thus, data inserted in the test remains inside the current transaction and rolls back when the test completes under default settings.

If using `@SpringBootTest` instead of `@DataJpaTest`, you can inject the repository and `EntityManager` similarly, and add `@Transactional` if you want Spring TestContext to manage a transaction around the method.

## 6. Using `EntityManager.find` Directly for Verification

A repository is not mandatory for the reload step. You can use `EntityManager`:

~~~java
entityManager.flush();

Long id = user.getId();

entityManager.clear();

AppUser reloaded = entityManager.find(AppUser.class, id);

assertNotNull(reloaded);
assertNotSame(user, reloaded);
assertEquals("Alice", reloaded.getDisplayName());
~~~

This approach makes it clear that the lookup is performed by the JPA `EntityManager`. Use the repository when you also want to verify the access path through Spring Data; use `EntityManager` directly when the goal is purely persistence context and JPA identity behavior.

Keep in mind that an `EntityManager` injected by Spring is usually a transaction-bound proxy. It delegates to the `EntityManager` corresponding to the current transaction. Calling `clear()` on it clears the persistence context in use for that transaction.

## 7. Using `TestEntityManager` in `@DataJpaTest`

Spring Boot provides `TestEntityManager` to assist with JPA testing. It offers convenient operations such as `persist`, `flush`, `clear`, `find`, and `detach`.

Example:

~~~java
@DataJpaTest
class AppUserPersistenceTest {

    @Autowired
    TestEntityManager testEntityManager;

    @Test
    void reloadsEntityAfterClear() {
        AppUser user = new AppUser("Alice");

        testEntityManager.persistAndFlush(user);
        Long id = user.getId();

        testEntityManager.clear();

        AppUser reloaded =
            testEntityManager.find(AppUser.class, id);

        assertNotSame(user, reloaded);
        assertEquals("Alice", reloaded.getDisplayName());
    }
}
~~~

`persistAndFlush` saves the entity and flushes changes to the database. `clear` clears the persistence context, and `find` reloads the entity.

`TestEntityManager` is a Spring Boot Test utility, not a standard JPA API. If the project does not use Spring Boot or a test needs to verify how repositories are invoked, use standard `EntityManager` and repositories.

## 8. Why Must You Flush Before Clearing?

This is the most common pitfall when testing reloads.

Suppose a test does the following:

~~~java
AppUser user = new AppUser("Alice");
entityManager.persist(user);

entityManager.clear();

AppUser reloaded = entityManager.find(AppUser.class, user.getId());
~~~

If not flushed yet, the insert statement may still be held inside the persistence context. Calling `clear` detaches the entity and discards the pending state tracked by the context. The subsequent lookup may not find the record because the insert was never sent to the database.

The right approach:

~~~java
entityManager.persist(user);
entityManager.flush();

Long id = user.getId();

entityManager.clear();

AppUser reloaded = entityManager.find(AppUser.class, id);
~~~

Save the ID before clearing. After clearing, the old object is detached; continuing to use it as a managed entity can lead to confusing results or errors when manipulating relationships.

Flushing is also essential after updates:

~~~java
user.rename("Alicia");

entityManager.flush();
entityManager.clear();

AppUser reloaded = entityManager.find(AppUser.class, id);

assertEquals("Alicia", reloaded.getDisplayName());
~~~

In this case, the assertion verifies the new value was synchronized to the database and can be reloaded after clearing.

## 9. Clear Is Not Commit and Does Not Start a New Transaction

`EntityManager.clear()` only clears the persistence context. It does not:

- Commit the current transaction.
- Roll back the current transaction.
- Start a new transaction.
- Close the `EntityManager` or `ApplicationContext`.
- Delete records in the database.
- Clear the JPA provider's second-level cache.

After clearing, the test remains in the same transaction if that transaction has not ended. If the test flushes an insert, clears, and then finds again, it can read data written by that same current transaction. This is a read-after-flush within the same transaction, not proof that another transaction sees the data after commit.

If the goal is verifying that data was committed and is readable in a new transaction, end the current transaction using an appropriate mechanism, such as Spring TestContext's `TestTransaction.flagForCommit()` followed by `TestTransaction.end()`, and then start a new transaction with `TestTransaction.start()` when the test is configured to support it.

| Verification Goal | Appropriate Approach |
|---|---|
| Avoid first-level cache returning old object | `flush()` then `clear()` |
| Refresh a single managed entity | `refresh(entity)` |
| Evict a single entity from context | `detach(entity)` |
| Verify data after commit in a new transaction | Commit transaction then start a new transaction |
| Verify test rollback | Let test-managed transaction roll back or flag for rollback |

## 10. Clear and the Second-Level Cache

The JPA persistence context is the first-level cache, bound to a single `EntityManager`. `clear()` clears this cache.

Some applications also enable a second-level cache at the persistence unit or provider level. That cache can outlive a single `EntityManager` and be shared across multiple persistence contexts. Consequently, after clearing the first-level cache, an entity lookup might still be served from the second-level cache rather than querying the database.

If the test's goal is merely proving the entity is no longer held in the current persistence context, `clear()` is the right operation.

If the goal is verifying data is actually read from the database and not served from the second-level cache, control the second-level cache separately. JPA provides `CacheRetrieveMode.BYPASS` for lookup operations, or the entity can be evicted from the shared cache when appropriate for the test. Exact configuration depends on the Jakarta Persistence version and provider.

Example using cache retrieve mode:

~~~java
Map<String, Object> hints = Map.of(
    "jakarta.persistence.cache.retrieveMode",
    CacheRetrieveMode.BYPASS
);

AppUser reloaded =
    entityManager.find(AppUser.class, id, hints);
~~~

This example uses the modern Jakarta Persistence namespace. For older JPA applications using the `javax.persistence` package, use the API and hints matching that version.

There is no need to bypass the second-level cache in every test. Do so only when second-level caching behavior itself lies outside what you want to test.

## 11. Clear vs. Refresh: Choosing the Operation by Goal

Two operations are often confused:

~~~java
entityManager.refresh(user);
~~~

and:

~~~java
entityManager.clear();
AppUser reloaded = entityManager.find(AppUser.class, id);
~~~

`refresh` keeps the entity managed and reloads database state into that exact object. After refresh, the `user` variable still points to the same instance, with its fields updated from the read data.

`clear` detaches all entities. On re-lookup, JPA creates or obtains a new managed instance for that identity inside the cleared persistence context.

| Criterion | `refresh` | `clear` then `find` |
|---|---|---|
| Scope | One entity | All managed entities |
| Old object | Still managed | Detached |
| Java identity afterward | Keeps the same instance | Lookup yields a new instance |
| Typical goal | Discard in-memory changes and reload one entity | Test reloading after dropping the first-level cache |
| Precondition | Entity must be managed | Entity can be looked up by ID |

Use `refresh` if you want to update a single managed entity from the database. Use `clear` when you want to ensure the next lookup does not return the old object from the persistence context.

## 12. Detached Entities After Clear and Lazy Loading Impact

After `clear`, all entities previously managed in the context become detached. The Java objects still exist, but the `EntityManager` no longer tracks their changes.

Example:

~~~java
entityManager.clear();

user.rename("Changed after clear");

entityManager.flush();
~~~

The `flush()` call does not automatically save the change just made to `user`, because that object is now detached. To update the entity again, re-fetch the managed entity by ID or use `merge()` properly.

Lazy associations also require attention. If a test clears the context and then accesses a lazy collection on the old object, the provider may fail to load data because the entity is no longer managed. This can trigger a `LazyInitializationException` in Hibernate or an out-of-context association access error depending on the provider.

The right way is to reload the root entity after clearing and then access the association while the new entity is managed and the context is active:

~~~java
entityManager.clear();

Order reloaded = entityManager.find(Order.class, orderId);

assertEquals(2, reloaded.getItems().size());
~~~

If associations need to be loaded with the root, consider an entity graph, fetch join, or query suited to the test goal. Do not keep references to lazy collections on old entities expecting them to keep working after `clear`.

## 13. Clear Under Transaction Isolation and Checking External Changes

Clearing forces JPA to drop the first-level cache, but it does not change the database isolation level and does not end the transaction.

If the transaction uses an isolation level such as `REPEATABLE READ` or `SNAPSHOT`, the database may continue serving the same snapshot for subsequent reads within that transaction. Hence, `clear` does not guarantee a test sees data committed by another transaction after the current transaction began.

To verify a new transaction sees commits from a prior transaction:

1. Commit the writing transaction.
2. End that transaction.
3. Start a new transaction.
4. Re-read the data inside the new transaction.

If you only need to confirm an object was synchronized and can be reloaded within the same transaction, `flush` then `clear` is sufficient. If you need to verify visibility across transactions, design the test with distinct transaction boundaries.

## 14. Common Mistakes

- **Calling `clear` before `flush`:** pending changes may not have been sent to the database yet; flush first if you need to keep them.
- **Assuming `clear` commits data:** `clear` only detaches entities; the transaction continues.
- **Assuming `find` always issues SQL:** JPA can return entities from the first-level cache if they are still managed.
- **Asserting fields right after `save`:** assertions may be reading the in-memory object without proving data reloads.
- **Calling `refresh` after an entity is detached:** `refresh` requires a managed entity; re-fetch the entity or use an appropriate operation.
- **Continuing to modify an old object after `clear` and expecting `flush` to save changes:** that object is detached and no longer tracked by dirty checking.
- **Forgetting to save the ID before `clear`:** tests might rely on stale object state or generated identifiers.
- **Treating `clear` as a new transaction:** the transaction and isolation level remain unchanged.
- **Ignoring the second-level cache:** `clear` affects only the first-level cache; the second-level cache may still serve the entity.
- **Accessing lazy associations on a detached entity:** reload the root entity in an active context or use an appropriate fetch plan.
- **Using `clear` when only one entity needs refreshing:** `clear` detaches all entities, which may break other managed references the test still needs.
- **Concluding data was committed solely from `flush` then `clear`:** `flush` does not commit; the test may still be inside the same transaction.

## 15. Workflow for Verifying Entity Reloading

When you need to prove an entity can be reloaded after the persistence context no longer holds the old instance, follow these steps:

1. Create the entity or update the state under test.
2. Persist or save the entity through the repository.
3. Call `EntityManager.flush()` or `saveAndFlush()` to synchronize data.
4. Store the entity's ID in an independent variable.
5. Call `EntityManager.clear()` to detach all entities.
6. Verify the old object is no longer managed via `EntityManager.contains()` if needed.
7. Look up the entity again via the repository or `EntityManager.find()`.
8. Verify it is a new instance using `assertNotSame()`.
9. Check the reloaded fields or associations.
10. If the goal is verifying commit visibility, end the transaction and start a new one; `clear` alone is not enough.
11. If the second-level cache is enabled and the test must verify a database query, control the second-level cache separately.

## Conclusion

The persistence context retains managed entities and acts as JPA's first-level cache. Therefore, looking up an entity by the same ID can return the exact same old object without testing data loading from the database. In tests that need to verify reloading, flush the changes you want to keep, clear the persistence context, and then look up the entity again by ID.

`flush()` synchronizes changes without committing; `clear()` detaches all entities without ending the transaction; `refresh()` reloads one still-managed entity; and `detach()` separates only a single entity. Distinguishing these operations ensures tests verify exactly what they intend: in-memory object state, data synchronized to the database, or data committed and visible from a new transaction.

