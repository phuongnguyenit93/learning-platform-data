# Detached Entities, Improper Merge, and EntityExistsException

In JPA, an Entity can be in the new/transient, managed, detached, or removed state. Many errors during data updates stem from confusing these states or misusing persist/merge.

A detached Entity was previously managed by a persistence context but is no longer managed by an EntityManager. To synchronize its changes, merge can be used. However, merge does not re-attach the original input object itself; it copies state onto a managed instance and returns that instance. If you ignore the return value of merge or JpaRepository.save(), the application may continue modifying the detached object and mistakenly believe changes were saved.

EntityExistsException typically occurs when persisting an Entity that already has an identity/exists, or when an identity conflict is detected by the persistence provider. Distinguish this error from stale data merges, optimistic locking, and database constraint errors.

## 1. The Four Lifecycle States of an Entity

JPA manages Entities through a persistence context, typically bound to an EntityManager.

| State | Meaning | Are changes auto-synchronized? |
|---|---|---|
| New/transient | New object, not yet persisted and not managed | Not yet |
| Managed/persistent | Entity currently managed by an EntityManager | Yes, via dirty checking on flush |
| Detached | Entity was managed previously but no longer belongs to the current persistence context | No |
| Removed | Entity marked for deletion in the persistence context | DELETE is synchronized on flush |

Example creating a new Entity:

~~~java
Customer customer = new Customer("An");
~~~

This object is in the new/transient state. After calling persist inside a transaction:

~~~java
entityManager.persist(customer);
~~~

customer becomes managed. Changes to its properties are tracked by JPA:

~~~java
customer.rename("An Nguyen");
~~~

On flush or commit, Hibernate/JPA issues an UPDATE statement if the Entity has changed.

When the EntityManager closes, the persistence context is cleared, or the Entity is detached, the object is no longer managed. Changes made to a detached object are not automatically written to the database.

## 2. When Does an Entity Become Detached?

An Entity can become detached in several situations:

- The EntityManager is closed.
- Calling entityManager.clear(), which detaches all managed Entities.
- Calling entityManager.detach(entity), which detaches a specific Entity.
- The transaction/persistence context ends and the Entity is no longer managed.
- The Entity is returned from a service, serialized, or passed across another request and reused.
- The Entity is stored in a session/web state or application cache after the persistence context has ended.

Example:

~~~java
@Transactional
public Customer loadCustomer(Long id) {
    return customerRepository.findById(id).orElseThrow();
}
~~~

Once the service finishes, the returned object is typically no longer managed by the service's transaction/persistence context. Mutating that object in a controller or subsequent request does not automatically update the database.

You can check status within an EntityManager scope:

~~~java
boolean managed = entityManager.contains(customer);
~~~

If it returns false, the Entity is not managed by the current EntityManager. This does not necessarily mean the object is detached in every context; a new/transient object also returns false. You need to know the object's lifecycle history to tell them apart.

## 3. persist() Is for New Entities

EntityManager.persist() puts a new Entity into the persistence context:

~~~java
Customer customer = new Customer("An");

entityManager.persist(customer);

assert entityManager.contains(customer);
~~~

After persist:
- The passed-in object itself becomes managed.
- JPA tracks changes on the object.
- The INSERT may execute immediately or be deferred until flush/commit depending on the ID strategy and provider.
- No new managed object is returned; persist() returns void.

Do not use persist() to update an existing detached Entity. persist() is designed for the new/transient state.

If you pass a detached Entity or an Entity sharing an identifier with an existing Entity, JPA may throw errors such as EntityExistsException or IllegalArgumentException depending on the scenario and detection timing. Hibernate may throw a provider-specific error such as PersistentObjectException with the message detached entity passed to persist.

## 4. merge() Synchronizes Detached State

EntityManager.merge() copies the state of the input object into a managed instance with the same identity. The new return value is the managed instance in the current persistence context.

~~~java
Customer detached = loadOutsideCurrentPersistenceContext();

Customer managed = entityManager.merge(detached);

assert entityManager.contains(managed);
~~~

If detached is indeed not managed in the current persistence context, managed is the instance representing that identity in that context. The original detached object remains detached.

Key points:

- merge() does not turn the input object into a managed instance.
- merge() returns the managed instance.
- Subsequent modifications must be made on the returned instance.
- The input object's state is copied onto the managed instance per JPA merge rules.
- Relationships are only cascaded during merge if the mapping specifies cascade MERGE or ALL.

Do not confuse merge() with a simple SQL UPDATE statement. The provider must synchronize object state with the persistence context and database; the operation may need to read current data, verify version, and schedule INSERT/UPDATE.

## 5. Common Mistake: Ignoring the Object Returned by merge()

Incorrect example:

~~~java
Customer detached = receiveCustomerFromRequest();

entityManager.merge(detached);

// Wrong: detached is still not managed.
detached.rename("New name");
~~~

merge() copied the current state of detached onto a managed instance. The subsequent rename() call on detached is not tracked by dirty checking.

Correct approach:

~~~java
Customer detached = receiveCustomerFromRequest();

Customer managed = entityManager.merge(detached);

managed.rename("New name");
~~~

If you only need to synchronize current state, use the returned instance. If further edits are required, continue working on managed.

The same rule applies to JpaRepository.save(). When save() chooses merge, the method returns the managed instance. Always use the returned value:

~~~java
Customer managed = customerRepository.save(detached);
managed.rename("New name");
~~~

Do not write save(detached) and assume the original detached object was re-attached to the persistence context.

## 6. How Does Spring Data JPA save() Choose Between Persist and Merge?

JpaRepository.save(entity) does not always call persist() nor always call merge(). Spring Data JPA determines whether an Entity is considered new via EntityInformation.isNew().

Common default rules:
1. If the Entity has a non-primitive `@Version` property, Spring Data checks the version. A null version is usually treated as a new Entity.
2. If there is no applicable version property, Spring Data checks the ID. A null ID is usually treated as a new Entity.
3. If the Entity implements Persistable, Spring Data uses the isNew() supplied by the Entity.
4. Applications can customize EntityInformation via the repository factory mechanism when truly needed.

If considered new, save() calls EntityManager.persist(entity) and returns that entity. If not new, save() calls EntityManager.merge(entity) and returns the managed instance.

Therefore, ID/version mapping directly influences whether persist or merge is chosen.

## 7. Why Can Entities with Pre-Assigned IDs Be Mishandled by save()?

Some applications use externally provided IDs, client/app-generated UUIDs, or business keys instead of database-generated IDs.

Example:

~~~java
@Entity
public class ExternalCustomer {

    @Id
    private UUID id;

    private String name;
}
~~~

If you create a new ExternalCustomer with a non-null id already assigned, and the Entity lacks an appropriate version property, the default rule may consider it an existing Entity and select merge.

This can trigger a SELECT before writing, or cause behavior different from creating a new record. When version or database state differs from expectations, the result can be an incorrect insert/update, an optimistic locking exception, or a constraint error.

Do not assume a non-null ID always means the record already exists. An ID can be assigned before insert.

## 8. Using @Version to Assist New Entity Detection

A non-primitive version property can help Spring Data recognize a new Entity:

~~~java
@Entity
public class ExternalCustomer {

    @Id
    private UUID id;

    @Version
    private Long version;

    private String name;
}
~~~

For a new Entity, version is typically null; Spring Data can recognize it as new and use persist. Once the Entity is persisted, the provider manages version for optimistic locking.

Use wrapper Long instead of primitive long if you need a null state to signal newness. A primitive cannot represent null and thus cannot provide an "unpersisted" signal this way.

Version is not merely a newness flag. It also protects concurrent updates by checking the old version during UPDATE. Do not manually assign arbitrary version values just to force Spring Data into the persist/merge branch.

## 9. Using Persistable When IDs Are Pre-Assigned

If an Entity uses assigned IDs and cannot rely on version, you can implement `Persistable<ID>` to explicitly define newness.

Example:

~~~java
import jakarta.persistence.*;
import org.springframework.data.domain.Persistable;

@Entity
public class ExternalCustomer implements Persistable<UUID> {

    @Id
    private UUID id;

    private String name;

    @Transient
    private boolean newEntity = true;

    protected ExternalCustomer() {
    }

    public ExternalCustomer(UUID id, String name) {
        this.id = id;
        this.name = name;
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    @PostPersist
    @PostLoad
    void markNotNew() {
        this.newEntity = false;
    }
}
~~~

When freshly created via the constructor, newEntity is true so save() chooses persist. After persist or load, the callback marks the Entity as no longer new.

This is an illustrative pattern. Ensure every creation/loading path initializes the flag properly, especially with serialization, deserialization, factories, and import tools. Never accept isNew status from client data as trustworthy; it is persistence metadata managed by the application.

## 10. What is EntityExistsException?

Jakarta Persistence defines EntityExistsException to report that a persist operation encountered an already-existing Entity or an identity conflict detected by the persistence provider.

A common scenario:

~~~java
Customer customer = entityManager.find(Customer.class, 10L);
entityManager.detach(customer);

// Do not call persist() on this detached object.
entityManager.persist(customer);
~~~

The Entity already has an ID and previously existed. Calling persist() is not the way to update it. The provider may detect the conflict immediately at persist() or defer until flush/commit.

Another example is the application manually assigning an ID matching an existing Entity and calling persist() on that new object.

Do not rely on a single execution point to catch the error. In JPA, some persistence errors only surface during flush or commit.

## 11. Distinguishing EntityExistsException from Similar Errors

| Error | Common meaning | What to check |
|---|---|---|
| EntityExistsException | persist encountered an existing Entity/identity | Check Entity state, ID, and persist/merge |
| PersistentObjectException | Hibernate-specific error, e.g., detached entity passed to persist | Check for detached objects passed to persist/cascade |
| NonUniqueObjectException | Hibernate Session already manages another object with the same identifier | Check for multiple instances with the same ID in one Session |
| OptimisticLockException | Version no longer matches during update | Check stale data and @Version |
| DataIntegrityViolationException | Spring translation of constraint/data integrity error | Check unique, FK, NOT NULL, and input data |
| ConstraintViolationException | Hibernate reports SQL constraint violation | Check database constraints and SQL statement |

Exception classes may be wrapped inside other exceptions via Spring exception translation. Inspect the root cause, SQL state, constraint name, and error timing instead of relying solely on the outermost exception name.

Do not treat every "detached" error as EntityExistsException. Detached is a lifecycle state; EntityExistsException is a specific persistence error type.

## 12. How Do persist() and merge() Differ?

| Criterion | persist() | merge() |
|---|---|---|
| Suitable input | New/transient Entity | Detached Entity or state to merge |
| Return result | void | Managed instance |
| Input object | Becomes managed | Remains detached if originally detached |
| Identity | Uses new Entity's identity | Synchronizes into managed instance with same identity |
| Purpose | Create a new Entity | Copy state into the persistence context |
| Cascade | PERSIST or ALL | MERGE or ALL |
| Common risk | Persisting a detached/existing object | Ignoring managed copy or overwriting newer state |

Do not use merge() as a cure-all for persist errors. If the object is actually a new record, fix newness detection and use persist. If the detached object represents an existing record, merge may be suitable, provided the merged data is controlled.

## 13. merge() Can Overwrite Database Data

merge() synchronizes the state of a detached object. If the object was built from a stale payload or contains only partial fields, null/default values may be copied onto the managed instance and overwrite newer data.

For example, the database currently holds:

~~~text
id = 10
name = "An Nguyen"
email = "an@example.com"
active = true
~~~

The client sends only:

~~~json
{
  "id": 10,
  "name": "An"
}
~~~

If the application constructs a new Entity containing only id and name and merges the whole object, email could be overwritten with null and active could be overwritten with its default value depending on mapping/field initialization.

This is why you should not turn a request DTO into a detached Entity and merge it directly when the request only carries partial data.

A safer approach:
1. Load the managed Entity by ID.
2. Verify permissions and business state.
3. Apply only the fields permitted to change.
4. Let dirty checking synchronize changes.
5. Use `@Version` if you need to detect updates based on stale data.

## 14. Updating a Managed Entity Instead of Merging a Newly Constructed Object

A typically safe service pattern:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public CustomerDto update(Long id, UpdateCustomerCommand command) {
        Customer customer = repository.findById(id)
                .orElseThrow(() -> new CustomerNotFoundException(id));

        if (command.name() != null) {
            customer.rename(command.name());
        }

        if (command.email() != null) {
            customer.changeEmail(command.email());
        }

        return CustomerDto.from(customer);
    }
}
~~~

Customer is loaded within the transaction and is therefore managed. Modifications on the object are tracked by the persistence context. On commit, dirty checking generates an UPDATE for the changed attributes.

In this case, calling repository.save(customer) again is usually unnecessary. Calling save() on an already-managed Entity is not needed for dirty checking, though it may be used per codebase conventions.

If the API needs to distinguish "field omitted" from "explicitly sent null to clear the field", the DTO must represent those two states. Checking `command.email() != null` is merely an example for an API that does not allow setting email to null.

## 15. Cascade MERGE and the Entity Graph

When merging an Entity with relationships, related Entity state is only propagated if the mapping declares appropriate cascade.

Example:

~~~java
@OneToMany(
    mappedBy = "customer",
    cascade = CascadeType.MERGE
)
private List<Address> addresses = new ArrayList<>();
~~~

CascadeType.MERGE allows merge operations on Customer to propagate to Address instances according to JPA rules.

Common cascade types:

- PERSIST: propagates persist.
- MERGE: propagates merge.
- REMOVE: propagates remove.
- REFRESH: propagates refresh.
- DETACH: propagates detach.
- ALL: includes all the cascade types above.

Do not add CascadeType.ALL merely to avoid errors. Cascade is a lifecycle rule: deleting a Customer can trigger deletion of Addresses if REMOVE is enabled. Only cascade when the parent Entity truly owns the lifecycle of child objects.

For many-to-many relationships or shared Entities, cascade REMOVE can accidentally delete shared data if mapped improperly.

## 16. What Errors Can a Detached Graph and Relationships Cause?

A detached object may contain an entire Entity graph. During merge, the provider must process relationships according to cascade and mapping.

Common issues:
- Child relationship lacks cascade MERGE, so changes on child objects are not merged as expected.
- A detached child object with the same ID carries stale state and overwrites newer data.
- A relationship points to a transient Entity while the mapping lacks appropriate PERSIST/MERGE cascade.
- A collection is submitted missing elements and merging alters relationships unintentionally.
- Multiple instances representing the same ID in one graph cause conflicts in the Hibernate Session.
- Orphan removal deletes child Entities when items are removed from a managed collection.

For business aggregates, it is usually best to load the managed root, then add/remove/update children through domain methods on the root. Do not blindly merge an entire graph built from an external request.

## 17. Do Not Use persist() to Update a Detached Entity

A common wrong snippet:

~~~java
@Transactional
public void update(Customer detached) {
    entityManager.persist(detached);
}
~~~

If detached represents an existing record, persist() is not an update operation. You may get EntityExistsException or a provider-specific error.

There are two valid directions depending on the use case.

Use a managed entity:

~~~java
@Transactional
public void update(Long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);

    if (customer == null) {
        throw new CustomerNotFoundException(id);
    }

    customer.rename(newName);
}
~~~

Or merge when you genuinely need to synchronize detached state:

~~~java
@Transactional
public Customer updateDetached(Customer detached) {
    return entityManager.merge(detached);
}
~~~

The first approach is usually easier for controlling editable fields and avoiding accidental overwrites. The second approach fits when the application intentionally merges full detached state.

## 18. save() Does Not Always Mean INSERT or Always UPDATE

Spring Data JPA save() chooses persist or merge based on newness detection, not just the caller's intent.

| Entity | Newness typically detected | save() behavior |
|---|---|---|
| Null ID, no version | New | persist |
| Non-null ID, no version | Not new | merge |
| Non-null ID, null Long version | New under version strategy | persist |
| Non-null ID, non-null version | Not new | merge |
| Implements Persistable and isNew() true | New under custom strategy | persist |
| Implements Persistable and isNew() false | Not new under custom strategy | merge |

This table describes Spring Data JPA's common default strategies. If an application customizes EntityInformation or overrides repository behavior, outcomes may differ.

If save() takes the merge path, always use the returned object. If IDs are pre-assigned yet the Entity is genuinely new, configure an explicit newness strategy instead of relying on guesswork.

## 19. saveAndFlush() Does Not Fix Merge/Persist Errors

saveAndFlush() calls save() and then requests a persistence context flush. It does not change how Spring Data decides between persist and merge.

~~~java
Customer saved = repository.saveAndFlush(customer);
~~~

If save() chooses merge, saved is still the managed copy returned from merge. If save() chooses persist, saved is typically the new object itself.

Flush forces the provider to synchronize SQL earlier and can cause EntityExistsException, constraint errors, or optimistic locking errors to surface right at the call site. Flush is not commit; the transaction can still roll back afterward.

Do not use saveAndFlush() as a way to "force update" a detached Entity or patch broken newness detection.

## 20. Optimistic Locking When Merging Stale Data

If an Entity has `@Version`, the provider uses the version to detect two transactions editing the same record concurrently.

Example:

~~~java
@Entity
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;

    public void rename(String name) {
        this.name = name;
    }
}
~~~

Scenario:
1. Transaction A reads Customer version 4.
2. Transaction B also reads version 4.
3. B updates and commits; version becomes 5.
4. A merges/updates the stale object still carrying version 4.
5. On flush/commit, the provider detects the version mismatch and throws OptimisticLockException or a corresponding Spring-translated exception.

This protects against lost updates. Do not bypass optimistic locking errors by repeatedly re-merging the stale object. Load the latest state, compare changes, and decide whether to retry or return a conflict to the caller.

## 21. When to Use refresh(), detach(), and clear()?

Persistence context APIs serve different purposes:

- detach(entity): removes a single Entity from the persistence context.
- clear(): detaches all managed Entities in the context.
- refresh(entity): reloads database state into a managed Entity, overwriting unflushed changes on the object.
- merge(entity): copies an object's state into a managed instance and returns that instance.

Example refresh:

~~~java
entityManager.refresh(customer);
~~~

Only refresh a managed Entity. Refresh can discard unflushed changes on the object since database state is reloaded.

clear() is useful in batch processing to avoid keeping too many Entities in the persistence context, but after clear, all prior objects are detached. If you continue updating them, reload or merge them properly.

Do not call clear() midway and continue assuming old objects remain managed.

## 22. When Can EntityExistsException Occur?

The JPA provider may detect the error at several points:

- Immediately when persist() is called if it knows the Entity is invalid for that operation.
- At flush() when SQL is actually sent to the database.
- At commit() when the transaction manager triggers flush and the database checks constraints.

Therefore, a test wrapping only persist() in assertThrows may fail to catch the error if the provider defers validation:

~~~java
entityManager.persist(entity);
entityManager.flush();
~~~

When testing persistence errors, establish an explicit flush/commit point and verify the root cause. Do not catch an overly narrow exception class if JPA/provider may report an equivalent failure via a wrapper.

## 23. Diagnostic Workflow for Detached/Merge Errors

When encountering messages like detached entity passed to persist, EntityExistsException, or merge failing to save changes, check in order:

1. Determine whether the Entity is new, managed, detached, or removed.
2. Check EntityManager.contains(entity) in the right persistence context.
3. Check whether the code calls persist(), merge(), or repository.save().
4. If calling merge/save, check whether the returned object is used.
5. Check whether the ID is generated or pre-assigned.
6. Check whether `@Version` exists and uses a wrapper type.
7. If implementing Persistable, check isNew() and state-updating callbacks.
8. Check cascade PERSIST/MERGE on each relationship.
9. Check whether multiple objects with the same ID exist in one persistence context.
10. Check whether detached data has null/default fields overwriting existing data.
11. Check stale versions and optimistic locking.
12. Explicitly call flush in tests to see if the error arises at persist, flush, or commit.
13. Read the root cause, SQL state, and constraint name instead of looking only at the exception wrapper.

Do not fix errors by adding CascadeType.ALL, calling saveAndFlush(), or merging every object without identifying the root cause.

## 24. Testing Merge and Managed State

An integration test can prove merge returns a separate managed instance:

~~~java
@DataJpaTest
class CustomerMergeTest {

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void mergeReturnsManagedCopyOfDetachedEntity() {
        Customer customer = new Customer("An");
        entityManager.persist(customer);
        entityManager.flush();

        Long id = customer.getId();

        entityManager.detach(customer);
        assertFalse(entityManager.contains(customer));

        customer.rename("An Nguyen");

        Customer managed = entityManager.merge(customer);

        assertNotSame(customer, managed);
        assertTrue(entityManager.contains(managed));
        assertFalse(entityManager.contains(customer));

        entityManager.flush();

        Customer reloaded = entityManager.find(Customer.class, id);
        assertEquals("An Nguyen", reloaded.getName());
    }
}
~~~

The test assumes Customer has a generated ID, constructor, and matching rename/getName methods. EntityManager keeps the test transaction; flush synchronizes SQL, though the test transaction may roll back when finished.

The test should confirm:
- The detached object is unmanaged.
- merge() returns a managed object.
- The original input object remains detached.
- The merged values are persisted after flush.
- Reloading within the persistence context reflects the expected state.

## 25. Testing Spring Data save() with Detached Entities

With Repositories, verify the return value too:

~~~java
@DataJpaTest
class CustomerRepositorySaveTest {

    @Autowired
    private CustomerRepository repository;

    @PersistenceContext
    private EntityManager entityManager;

    @Test
    void saveReturnsManagedInstanceForDetachedEntity() {
        Customer customer = repository.save(new Customer("An"));
        repository.flush();

        Long id = customer.getId();

        entityManager.detach(customer);
        customer.rename("An Nguyen");

        Customer saved = repository.save(customer);

        assertNotSame(customer, saved);
        assertTrue(entityManager.contains(saved));
        assertFalse(entityManager.contains(customer));

        repository.flush();

        entityManager.clear();

        Customer reloaded = repository.findById(id).orElseThrow();
        assertEquals("An Nguyen", reloaded.getName());
    }
}
~~~

This is an illustrative test for an Entity with a generated ID where save() recognizes the detached object as not new. If the Entity uses assigned IDs or Persistable, adjust the fixture per the newness strategy.

In real projects, test pre-assigned IDs, null version, non-null version, and Persistable callbacks to avoid wrong inserts/updates.

## 26. Testing EntityExistsException Across Providers

You can write an integration test for persisting a detached object, but do not assume every provider throws the exact same exception class on the exact same line.

A test can:
1. Persist the Entity and flush.
2. Detach the Entity.
3. Call persist() on the detached object.
4. Flush if no error has been thrown yet.
5. Verify the provider/JPA reports an appropriate persistence error.
6. Verify the root cause is a state/identity conflict rather than another test fixture bug.

If a test must verify EntityExistsException specifically, run it on the application's actual provider and Hibernate version, and account for exception timing. Hibernate may throw a provider-specific exception before a JPA exception wrapper applies.

Do not catch a broad Throwable and treat any error as a pass. Tests must verify the error cause matches the tested scenario.

## 27. Common Mistakes

**Calling persist() with a detached Entity**

persist is for new Entities. Use a managed entity or merge properly.

**Ignoring the return value of merge()**

The input object stays detached. Use the returned managed instance.

**Ignoring the return value of repository.save()**

save() may invoke merge and return a managed copy. Continuing to mutate the old object can lose subsequent changes.

**Building a new Entity from a DTO and merging the whole thing**

Null/default fields can overwrite database data. Load the managed Entity and apply permitted fields.

**Pre-assigned ID causing Spring Data to misdetect newness**

Use an appropriate wrapper `@Version` or implement `Persistable.isNew()`.

**Using primitive version expecting null detection**

Primitives cannot be null. Use a wrapper type if relying on version for newness signaling.

**Missing cascade MERGE on relationships**

Child Entity changes are not cascaded on merge as expected. Check cascade and relationship ownership.

**Mechanically adding CascadeType.ALL**

Can trigger unintended remove/refresh/detach operations. Choose only the cascades required.

**Merging a stale detached graph**

Stale state can overwrite newer updates or unintentionally alter collections. Load the managed aggregate and apply commands.

**Confusing EntityExistsException with OptimisticLockException**

One is a persist/identity conflict; the other is a stale version conflict. Read the root cause and check version.

**Assuming saveAndFlush() commits**

Flush only synchronizes SQL; the transaction can still roll back.

**Checking for errors before flush**

The provider may defer errors to flush/commit. Explicitly call flush in integration tests.

## 28. Workflow for Choosing Persist, Merge, or Updating a Managed Entity

When writing an Entity, determine:

1. Is this a new Entity without a persistent identity yet?
2. Is the ID database-generated or application-assigned beforehand?
3. Will Spring Data detect newness via version, ID, or Persistable?
4. If the Entity is already managed, is calling save() needed or is dirty checking sufficient?
5. If detached, do we need to merge full state or simply load the managed Entity and apply a command?
6. If merging, does the code use the returned object?
7. Which relationships need cascade PERSIST or MERGE?
8. Could null/default fields or stale state overwrite newer data?
9. Is `@Version` present to detect stale updates?
10. Does the exception occur at persist, flush, or commit?
11. Do integration tests verify managed state, return values, and data after clearing the context?

For ordinary business updates, loading the managed Entity inside a transaction and invoking domain methods is usually the easiest approach to control. Use merge when you genuinely need to synchronize a detached graph and fully understand all state being copied.

## 29. Conclusion

A detached Entity is an object no longer managed by the current persistence context. persist() is for new Entities; merge() copies state into a managed instance and returns that instance, while the input object remains detached. JpaRepository.save() chooses persist or merge based on newness detection via version, ID, or Persistable.isNew(). Therefore, always use the object returned from merge/save whenever the merge branch can occur.

EntityExistsException typically relates to persisting an existing Entity or an identity conflict; distinguish it from Hibernate's detached entity passed to persist, NonUniqueObjectException, OptimisticLockException, and constraint errors. Merging detached state can overwrite newer fields or null/default fields, so for partial updates load the managed Entity and apply commands. Verify cascades, `@Version`, ID strategies, and flush/commit timing with integration tests on your actual provider.
