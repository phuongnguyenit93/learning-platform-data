# Why merge Returns a Different Managed Object

## Objective

After this lesson, you will be able to:

- Explain accurately what `EntityManager.merge()` does for new, managed, detached, and removed entities.
- Understand why the object passed into `merge()` does not itself become managed when it is detached.
- Distinguish `persist()` from `merge()` and know when to use each operation.
- Correctly use the return values from `EntityManager.merge()` and `JpaRepository.save()`.
- Recognize the risk of overwriting data with stale detached state or an object constructed from a partial DTO.
- Use `@Version`, transactions, and integration tests to control concurrent updates.

## 1. Entity lifecycle in JPA

JPA manages entities according to states. The state indicates whether an entity is currently tracked by a persistence context.

| State | Meaning | Example |
|---|---|---|
| New / Transient | New Java object, not yet managed by a persistence context and with no corresponding managed record | `new Customer("An")` |
| Managed / Persistent | Entity currently managed by a persistence context; changes are tracked by dirty checking | Result of `find()` inside a transaction |
| Detached | Entity that has a database identity but is no longer managed by the current persistence context | Entity after `detach()`, `clear()`, or when the context closes |
| Removed | Entity marked for deletion in the persistence context | Entity after `remove()` |

A persistence context maintains one managed instance per persistent identity within the scope of that context. For example, if the Customer record with ID 10 has already been loaded into the context, subsequent operations in the same context work with the managed instance representing Customer 10.

This helps Hibernate/JPA track one consistent state: which changes need to be written, which entities need to be deleted, and which associations need to be synchronized on flush.

## 2. What does merge() actually do?

`EntityManager.merge(entity)` copies the state of the input object onto a managed object with the same persistent identity and returns that managed object.

Key point: if the input is detached, JPA does not turn that detached object itself into a managed one. It brings the object's state into the persistence context through a managed instance.

This can be summarized by input state:

| Input state | Merge behavior | Returned object |
|---|---|---|
| New / Transient | Creates a new managed instance and copies input state into it | New managed instance |
| Detached | Finds a managed instance with the same identity in the context or creates/loads a managed instance, then copies state | Managed instance representing that identity |
| Managed | The entity itself is already managed; merge does not need to create a new copy, though the merge operation can still cascade | That exact managed instance |
| Removed | Cannot be merged; the operation may throw IllegalArgumentException or an error detected at commit | No valid result |

For a detached entity, the object passed in and the object returned can be two different Java objects:

~~~java
Customer detached = ...;

Customer managed = entityManager.merge(detached);

// detached remains detached
// managed is tracked by the persistence context
~~~

Both can have the same ID and the same data after merge, yet only `managed` is tracked by the current persistence context.

### Why is a different managed instance needed?

A detached entity has already left an old persistence context. It may have been held in a user session, an application cache, or sent over a request. Meanwhile, the database may have changed, and a new persistence context might already be managing another instance of the same record.

JPA needs an instance managed by the current persistence context in order to perform dirty checking, synchronize relationships, and write changes on flush. Therefore, merge copies the state from the external object into the managed instance representing that identity.

This also avoids having two Java objects simultaneously representing one persistent identity where only one is tracked by the context. The managed instance is the object the application should continue using within the transaction.

## 3. Illustrative example: input object and returned object

Suppose we have a Customer entity:

~~~java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getName() {
        return name;
    }

    public void rename(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name must not be blank");
        }
        this.name = name;
    }
}
~~~

Within a transaction, you can create and persist the entity:

~~~java
Customer original = new Customer("Lan");
entityManager.persist(original);
entityManager.flush();

Long id = original.getId();
~~~

Then detach the entity from the persistence context:

~~~java
entityManager.detach(original);

boolean detachedIsManaged = entityManager.contains(original);
// false
~~~

Call merge:

~~~java
Customer managed = entityManager.merge(original);

boolean originalIsManaged = entityManager.contains(original);
// false

boolean returnedIsManaged = entityManager.contains(managed);
// true

boolean sameReference = original == managed;
// false when a detached input is copied to a managed instance
~~~

Both objects share the same identity:

~~~java
System.out.println(original.getId().equals(managed.getId()));
// true
~~~

However, only the returned object is managed:

- Modifying `managed.rename("Lan Nguyen")` will be tracked by dirty checking.
- Modifying `original.rename("Lan Tran")` after merge is not automatically written to the database.
- Calling `entityManager.contains(original)` still returns false.
- Calling `entityManager.contains(managed)` returns true.

This is why you must always use the return value of merge.

## 4. How do persist() and merge() differ?

These two operations have different purposes.

| Criterion | persist(entity) | merge(entity) |
|---|---|---|
| Purpose | Places a new entity into the managed state | Copies an entity's state into a managed instance |
| Input object | Typically new/transient | Can be new or detached; managed is also accepted |
| Return value | void | Managed instance |
| Input reference | That object itself becomes managed | If input is detached/new, the input object does not become managed |
| Existing ID | Can lead to identity/duplicate errors depending on state and timing | Uses identity to find or create the corresponding managed instance |
| SQL writes | Typically at flush, depending on generator and provider | Merge does not mean an immediate SQL UPDATE; flush synchronizes changes |

Example with a new entity:

~~~java
Customer customer = new Customer("Mai");

entityManager.persist(customer);

// customer itself is the managed instance
assert entityManager.contains(customer);
~~~

Example with a detached entity:

~~~java
Customer detached = loadInPreviousTransaction();

Customer managed = entityManager.merge(detached);

// Must continue working with managed
managed.rename("Mai Nguyen");
~~~

Do not use `persist()` as a way to update a detached entity. Under JPA, persist is for new entities; passing a detached entity to persist can lead to EntityExistsException or an error detected at flush/commit.

Conversely, there is no need to call merge for an entity that is already managed. Any changes on a managed entity within a transaction are already tracked by dirty checking.

## 5. merge is not an immediate UPDATE

A common misconception is that calling merge makes Hibernate immediately run a SQL UPDATE statement.

In reality:

1. Merge determines the corresponding managed instance.
2. Input state is copied into the managed instance.
3. The persistence context records the state needing synchronization.
4. On flush, the provider compares state and generates the necessary SQL.
5. Transaction commit makes the changes durable in the database.

Flush can occur before commit, such as when calling `flush()` or before a query under an appropriate FlushMode. SQL already sent in the transaction can still be rolled back if the transaction fails.

Therefore, if you want to verify data after merge, consider both the persistence context and the database transaction. A query in the same context may return results from the managed instance or synchronize prior to the query depending on flush mode.

## 6. Spring Data JPA save() can also return a different object

In Spring Data JPA, `JpaRepository.save(entity)` decides whether to use persist or merge based on whether the entity is recognized as new.

Regarding the typical behavior of `SimpleJpaRepository`:

- If the entity is considered new, the repository calls `EntityManager.persist(entity)` and returns the input entity itself.
- If the entity is not considered new, the repository calls `EntityManager.merge(entity)` and returns the managed instance from merge.

Therefore, code should capture the result:

~~~java
Customer saved = customerRepository.save(customer);
~~~

Do not ignore the return value:

~~~java
customerRepository.save(customer);

// Do not continue assuming customer has become managed
// if save took the merge branch.
~~~

If an immediate flush is needed:

~~~java
Customer saved = customerRepository.saveAndFlush(customer);
~~~

`saveAndFlush()` still does not alter merge semantics: if the entity took the merge branch, use the returned object. Flush only requests synchronizing pending changes to the database within the current transaction.

### How does Spring Data determine if an entity is new?

The default mechanism typically checks:

1. If there is a non-primitive `@Version` property, a null version is usually treated as a new entity.
2. If there is no suitable version, a null ID is usually treated as a new entity.
3. If the ID has already been assigned and there is no version for newness detection, Spring Data may treat the entity as existing and call merge.

This is especially important with UUIDs assigned by the application before save. If the ID is already non-null, do not assume by default that Spring Data will call persist.

This can be resolved with a nullable `@Version` or by implementing `Persistable<ID>` with an appropriate `isNew()`. When using `Persistable`, test state detection across persist, load, detach, and callbacks to avoid misreporting newness.

## 7. Merge and stale state

Merge copies the detached entity's state into a managed instance. If the detached object was created from stale data, it can overwrite newer changes in the database.

Example:

1. Transaction A reads Customer with name "Lan", version 4.
2. Transaction B reads the same Customer and renames it to "Lan Nguyen", committing version 5.
3. Transaction A still holds the stale detached object with name "Lan".
4. Transaction A merges the stale object.

Without a proper concurrency control mechanism, stale state can overwrite newer values. This is a lost update.

### Using @Version to detect concurrent updates

The Customer entity in the example above has:

~~~java
@Version
private Long version;
~~~

The JPA provider uses version to detect update conflicts. If the detached object has an outdated version, merge/flush/commit can trigger OptimisticLockException or the corresponding optimistic locking error.

The application should catch the error at the transaction boundary and ask the user to reload or reconcile changes according to business rules. Do not blindly auto-retry if the operation is not idempotent or has side effects.

`@Version` is not a pessimistic lock. It detects conflicts on write; it does not hold a row lock continuously while a user is editing.

## 8. Risk when merging entities constructed from DTOs

An anti-pattern is receiving a DTO from an API, constructing a new entity with only the ID and a few submitted fields, and calling merge:

~~~java
Customer partial = new Customer("New name");
partial.setId(id); // assuming a setter or mapper exists
entityManager.merge(partial);
~~~

A detached/partial entity may contain null or default values for fields the request did not send. Merge can copy those values onto the managed instance and lose existing data.

For example, the database has:

~~~text
id = 10
name = "Lan"
email = "lan@example.com"
status = "ACTIVE"
~~~

The request only wants to change name, yet the mapper builds an object:

~~~text
id = 10
name = "Lan Nguyen"
email = null
status = null
~~~

If this object is merged, email and status risk being overwritten with null or default values. Unfetched lazy properties have special rules in JPA, but you should not rely on those to turn a partial entity into a safe patch API.

### Safe update pattern

Instead of merging an entity built from a DTO, load the managed entity inside a transaction and apply only the fields permitted to change:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer rename(Long id, String newName) {
        Customer managed = repository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException(
                    "Customer not found: " + id
                ));

        managed.rename(newName);

        // Dirty checking will save the change when the transaction commits.
        return managed;
    }
}
~~~

This approach offers several benefits:

- Only fields permitted by business logic are modified.
- Fields omitted from the request remain intact.
- State and permissions can be validated before making changes.
- Relationships and collections are modified on the managed aggregate.
- `@Version` still participates in conflict detection.

If you truly need to merge a full detached object, clearly verify who created the object, that all fields are complete, that the version is still current, and how cascade is configured.

## 9. CascadeType.MERGE and entity relationships

Merge can cascade to related entities when the mapping declares `CascadeType.MERGE` or `CascadeType.ALL`.

Example:

~~~java
@OneToMany(
    mappedBy = "customer",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE}
)
private List<Address> addresses = new ArrayList<>();
~~~

When merging Customer, the state of related Addresses can be merged by cascade. Without cascade MERGE, do not assume the entire detached child object graph's state will be copied.

Choose cascade according to the aggregate lifecycle:

- PERSIST when creating a parent needs to create children at the same time.
- MERGE when merging a parent needs to propagate state to children.
- REMOVE when deleting a parent truly must delete children.
- orphanRemoval when a child no longer belonging to the parent must be deleted.

Do not use `CascadeType.ALL` just to avoid understanding individual operations. If child entities are shared or have independent lifecycles, cascade REMOVE/orphanRemoval can delete data unintentionally.

When merging a graph with bidirectional relationships, ensure the owning side and inverse side are synchronized in memory. Merge does not replace helper methods protecting domain invariants.

## 10. Lazy loading and unloaded properties

A detached entity may contain unfetched lazy associations or fields. JPA has rules protecting unfetched lazy state: the provider must not treat an unfetched lazy property as a null value to copy over like an ordinary field.

However, the application should not use a detached entity as a data patch. Distinguish:

- A fetched field with a null value: null may be actual state to merge.
- An unfetched lazy field: the provider may recognize this as unloaded and avoid merging it.
- A field set to null by a mapper because the DTO lacked data: the provider cannot tell whether that null means "not sent" or "clear value."

Therefore, DTO patches should have explicit semantics (such as field presence or JSON Merge Patch), and the service should apply intentional changes onto the managed entity.

## 11. Example testing that merge returns a managed instance

The test example below assumes the Customer entity has `@Id`, `@Version`, constructors, and a `rename()` method as in the earlier section.

~~~java
package com.example.customer;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

import jakarta.persistence.EntityManager;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

@DataJpaTest
class MergeLifecycleTest {

    @Autowired
    EntityManager entityManager;

    @Test
    void mergeDetachedReturnsManagedCopy() {
        Customer original = new Customer("Lan");
        entityManager.persist(original);
        entityManager.flush();

        Long id = original.getId();

        entityManager.detach(original);

        assertFalse(entityManager.contains(original));

        original.rename("Lan Nguyen");

        Customer merged = entityManager.merge(original);

        assertNotSame(original, merged);
        assertEquals(id, merged.getId());
        assertTrue(entityManager.contains(merged));
        assertFalse(entityManager.contains(original));

        merged.rename("Lan Tran");

        entityManager.flush();
        entityManager.clear();

        Customer reloaded = entityManager.find(Customer.class, id);
        assertEquals("Lan Tran", reloaded.getName());
    }

    @Test
    void mergeManagedReturnsSameInstance() {
        Customer managed = new Customer("Mai");
        entityManager.persist(managed);
        entityManager.flush();

        Customer result = entityManager.merge(managed);

        assertSame(managed, result);
        assertTrue(entityManager.contains(result));
    }
}
~~~

The first test proves:

1. The entity is persisted and receives an ID.
2. detach() removes the object from the persistence context.
3. merge() returns a different managed instance.
4. Only the returned object is tracked by the context.
5. Changes to the returned object are flushed.
6. After clear(), reloading from the database retrieves the value committed within the test transaction.

The second test proves that if the input is already managed, merge returns that exact instance.

`@DataJpaTest` typically runs in a test transaction and rolls back after the test. The example is not a standalone application; it requires Spring Boot test, a JPA provider, the entity, and appropriate database configuration.

## 12. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Called merge yet input object is not updated | Input is detached; merge returns a managed copy | Assign and use the returned object |
| Called save yet continued using old entity | save took the merge branch | Always capture the return value of save/saveAndFlush |
| Fields cleared after merge | Detached entity or DTO had null/default state | Load managed entity and apply fields intentionally |
| Lost update | Merged stale state without concurrency control | Use @Version and handle OptimisticLockException |
| New entity with UUID gets merged instead of persisted | Spring Data recognizes non-null ID as existing | Use nullable @Version or Persistable.isNew() |
| Cascade merge does not update children as expected | Association lacks CascadeType.MERGE or graph is out of sync | Define cascade and owning side clearly |
| Merging a removed entity throws an error | Entity is already marked for deletion | Do not reuse removed entities; create a new entity if business rules require |
| Modified detached entity yet database unchanged | Detached object is not tracked by dirty checking | Merge and use the managed copy, or load the entity in a transaction |
| Called merge on a managed entity expecting a copy | Entity is already in the context | Use the managed instance directly; no need to merge |

## Checklist before merging

- [ ] Determined the input entity's state.
- [ ] If the input is detached/new, code uses the object returned from merge.
- [ ] Not assuming merge issues a SQL UPDATE immediately.
- [ ] Not merging partial entities constructed from DTOs missing fields.
- [ ] Have `@Version` when concurrent updates must be detected.
- [ ] Cascade MERGE is enabled only according to the aggregate lifecycle.
- [ ] Owning side and inverse side of relationships are synchronized.
- [ ] Spring Data save() return values are always captured.
- [ ] Integration tests verify contains(), object identity, and data after flush/clear.
- [ ] Update operations execute within clearly bounded transactions.

## Conclusion

`merge()` does not "reattach" a detached object to the persistence context. It copies the input object's state onto a managed instance with the same identity and returns that instance. Therefore, for detached entities, continue working with the return value; the input object remains detached. Spring Data `save()` can also return a managed copy when taking the merge branch. Avoid merging objects built from DTOs with missing fields, use `@Version` to detect lost updates, and prefer loading the managed entity within a transaction and applying intentional business changes.