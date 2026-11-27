# save and How persist or merge Is Chosen in Spring Data JPA

## 1. What Does save() Actually Do?

In Spring Data JPA, a repository typically extends `JpaRepository` or `CrudRepository`, which provides the `save(entity)` method to save an entity. However, `save()` is not a fixed SQL statement, nor does it mean always running an INSERT or always running an UPDATE.

In the default JPA repository implementation (`SimpleJpaRepository`), the core execution flow is:

~~~java
if (entityInformation.isNew(entity)) {
    entityManager.persist(entity);
    return entity;
} else {
    return entityManager.merge(entity);
}
~~~

In other words:

- If Spring Data JPA detects the entity as **new**, `save()` calls `EntityManager.persist()`.
- If the entity is detected as **existing**, `save()` calls `EntityManager.merge()`.
- `save()` returns the object that should continue to be used. Especially in the `merge` branch, you must use the returned object because it is the managed instance returned by JPA.

Therefore, to understand `save()`, you need to understand JPA's two operations `persist` and `merge`, as well as how Spring Data JPA determines whether an entity is new.

## 2. Entity States: new, managed, detached, and removed

JPA manages entities through a persistence context. An entity is typically in one of the following states:

| State | Meaning |
|---|---|
| **New / transient** | An object just created in Java, not yet managed by the persistence context and not yet saved as an entity in the database |
| **Managed / persistent** | An object currently managed by the persistence context; property changes can be written to the database upon flush |
| **Detached** | An entity that was previously managed but is no longer in the persistence context; its changes are not automatically tracked |
| **Removed** | An entity marked for deletion by the persistence context; DELETE is synchronized upon flush |

Example:

~~~java
Customer customer = new Customer("An");
// customer is in the new state

entityManager.persist(customer);
// customer becomes managed

entityManager.detach(customer);
// customer becomes detached

entityManager.remove(entityManager.merge(customer));
// the merged instance becomes managed and is then marked as removed
~~~

The last snippet only illustrates the states. In a real application, you need to manage transactions and avoid calling unnecessary lifecycle operations. `remove()` requires a managed object; therefore, the example merges before removing.

An important point: a detached entity is still an ordinary Java object and can hold data. However, JPA no longer automatically tracks changes to that object until it is merged into a persistence context.

## 3. persist(): Adding a New Entity to the Persistence Context

`EntityManager.persist(entity)` is used to register a new entity into the current persistence context.

~~~java
Customer customer = new Customer("An");

entityManager.persist(customer);

// customer is now managed
~~~

After `persist()`:

- The passed object becomes managed in the persistence context.
- The provider schedules an INSERT when synchronizing data.
- The SQL statement may be sent immediately or deferred until flush/commit, depending on the key generation strategy and provider.
- Subsequent changes on that same managed object are tracked by JPA via dirty checking.

`persist()` has a `void` return type; it does not create a managed copy to return. The passed object itself becomes the managed entity.

### When Is persist Appropriate?

Use `persist()` when creating a new entity and you want to start managing it in the persistence context:

~~~java
@Transactional
public Customer createCustomer(String name) {
    Customer customer = new Customer(name);
    entityManager.persist(customer);
    return customer;
}
~~~

You should not call `persist()` on a detached entity with the intention of updating it. According to JPA, persist applies to new entities; passing a detached entity can lead to an exception, either immediately or during flush.

If an entity is already managed in the persistence context, calling `persist()` again on that entity does not turn it into a different object and usually does not create another record. However, there is no need to call this operation repeatedly.

## 4. merge(): Copying State into a Managed Entity

`EntityManager.merge(entity)` is used to bring the state of a new or detached entity into the current persistence context.

The most important point about `merge()` is that **the passed object does not necessarily become managed**. JPA returns a managed instance whose state is synchronized from the source object.

~~~java
Customer detached = receiveCustomerFromAnotherLayer();

Customer managed = entityManager.merge(detached);

// managed is the instance managed by the persistence context.
// detached remains the source object and stays detached.
~~~

There are three cases to distinguish:

1. **Detached object:** JPA finds or loads a managed instance corresponding to the identifier, then copies the state from the detached object into the managed instance and returns that managed instance.
2. **New object:** JPA creates a new managed instance and copies the state from the source object into that instance. Depending on the state and mapping, an INSERT will be executed upon flush.
3. **Already managed object:** the merge operation returns the corresponding managed instance itself; there is no need to merge to continue tracking changes that are already managed by the persistence context.

Illustrative example:

~~~java
Customer source = new Customer("Binh");
Customer managed = entityManager.merge(source);

source.setName("Chi");
managed.setName("Dung");
~~~

After merging, the change `source.setName("Chi")` is not automatically tracked because `source` remains an unmanaged source object. The change `managed.setName("Dung")` is tracked by the persistence context and can be written to the database upon flush.

### merge Is Not SQL MERGE or Upsert

The name `merge()` easily leads beginners to think it is a SQL `MERGE` statement, or that it always behaves as "UPDATE if present, INSERT if absent" based on a single database statement.

In reality, this is a JPA entity lifecycle operation. The provider locates the managed instance, copies the state, and schedules the appropriate SQL. It is not synonymous with a SQL `MERGE` statement, nor does it guarantee that the database always performs an atomic upsert operation.

If an object carries an ID whose corresponding record no longer exists in the database, merge behavior can result in an INSERT or an error depending on the state, mapping, and provider. You should not rely solely on the ID to definitively infer which SQL statement will run.

## 5. How Does Spring Data JPA Detect a New Entity?

`save()` needs to decide whether to call `persist()` or `merge()`. That decision is based on `EntityInformation.isNew(entity)`.

With the default configuration, Spring Data JPA typically detects new state in the following order:

1. If the entity implements `Persistable`, Spring Data calls the entity's `isNew()`.
2. If the entity does not implement `Persistable` and has a non-primitive `@Version` property, a `null` version value is considered a new entity.
3. If there is no suitable version property, Spring Data checks the ID property: a `null` ID is considered new; a non-`null` ID is considered existing.

Checking the version before the ID helps handle entities that use manually assigned IDs: an entity that already has an ID upon creation can still be detected as new if its wrapper version is still `null`.

### 5.1. Detection by ID

Example of an entity using an auto-generated primary key:

~~~java
@Entity
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;

    protected Customer() {}

    public Customer(String name) {
        this.name = name;
    }
}
~~~

With this entity, the ID is usually `null` when newly created. Spring Data detects the entity as new and calls `persist()`.

After the entity has been saved and has an ID, subsequent calls to `save()` usually go into the `merge()` branch if there is no version property or other detection mechanism.

### 5.2. Detection by @Version

If an entity has a non-primitive version property, Spring Data checks the version before the ID:

~~~java
@Entity
public class Product {
    @Id
    private UUID id;

    @Version
    private Long version;

    private String name;

    protected Product() {}

    public Product(UUID id, String name) {
        this.id = id;
        this.name = name;
    }
}
~~~

When creating a `Product` with a pre-assigned ID while `version == null`, Spring Data can detect the entity as new and choose `persist()`.

After saving, the provider assigns the initial version according to the optimistic locking mechanism. When the entity is reloaded or has a non-`null` version, the entity is typically detected as existing.

`@Version` also serves to control concurrent updates: when two transactions update the same entity concurrently, the version helps detect that one transaction is writing over stale data. This is a benefit independent of its role in supporting new entity detection.

Note: a primitive version property such as `long` cannot have a `null` value, so the null-check rule shown in the `Long` example above cannot be used.

### 5.3. Customizing with Persistable

If the application uses manually assigned IDs and does not have a suitable version property, the null-ID rule may not accurately reflect new state. You can implement `Persistable<ID>` to decide it yourself:

~~~java
@Entity
public class ImportedCustomer implements Persistable<String> {
    @Id
    private String id;

    private String name;

    @Transient
    private boolean newEntity = true;

    protected ImportedCustomer() {}

    public ImportedCustomer(String id, String name) {
        this.id = id;
        this.name = name;
    }

    @Override
    public String getId() {
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

In this example, `newEntity` is not stored in the database because it has `@Transient`. After a successful persist or after loading the entity from the database, the callback marks the entity as no longer new.

This implementation pattern should be tested according to the application's actual lifecycle, especially when entities are deserialized, reconstructed from DTOs, or recreated in another request. Do not use an arbitrary `isNew` flag without defining when it transitions to `false`.

## 6. Comparing persist and merge

| Criterion | `persist(entity)` | `merge(entity)` |
|---|---|---|
| Purpose | Adds a new entity to the persistence context | Copies the state of a new/detached entity into the persistence context |
| Source object | Usually a new entity | New or detached entity; a managed entity can also be passed |
| Object that becomes managed | The passed object itself | The instance returned from `merge()` |
| Return value | `void` | Managed instance |
| Used to update a detached entity? | No | Yes |
| Passing a detached entity | Invalid for the persist operation | Can merge state into a managed instance |
| When does SQL run? | When the provider synchronizes, either immediately or on flush/commit | When the provider synchronizes, either immediately or on flush/commit |
| Related cascade | `CascadeType.PERSIST` or `ALL` | `CascadeType.MERGE` or `ALL` |

Practical rules:

- Create a new entity and put it into the persistence context → `persist()`.
- Have a detached entity and want to copy the source object's state into the persistence context → `merge()`.
- Entity is already managed in a transaction → modify properties directly; dirty checking will record changes upon flush.

## 7. Using repository save() Properly

In a Spring Data JPA application, services typically call repositories instead of interacting directly with `EntityManager`.

### 7.1. Creating New Entities

~~~java
@Service
public class CustomerService {
    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer create(String name) {
        Customer customer = new Customer(name);
        return repository.save(customer);
    }
}
~~~

The new entity has a `null` ID, so Spring Data typically chooses `persist()` according to the default detection strategy. The repository returns the entity that has been saved/added to the persistence context.

### 7.2. Updating an Entity Loaded in a Transaction

The most controllable approach is to load the managed entity and then modify the allowed properties:

~~~java
@Transactional
public Customer rename(Long id, String newName) {
    Customer customer = repository.findById(id)
        .orElseThrow(() -> new EntityNotFoundException("Customer not found"));

    customer.setName(newName);

    return customer;
}
~~~

`customer` is loaded inside the transaction and is managed. When properties change, JPA dirty checking detects the difference and writes an UPDATE on flush. There is no need to call `repository.save(customer)` again for JPA to track changes.

If you want to call `save()` due to service-layer or repository-abstraction conventions, the result must still be used properly. However, calling save on a managed entity is usually unnecessary from a JPA lifecycle perspective.

### 7.3. Updating from a Detached Object

You can merge a detached object, but you need to understand that merge copies the state of the source object. Example:

~~~java
Customer detached = new Customer();
detached.setId(10L);
detached.setName("Lan");

Customer managed = repository.save(detached);
~~~

If Spring Data detects the object as existing, it calls merge and returns a managed instance. Continue using `managed`, and do not assume `detached` has become managed.

This update approach requires caution because the source object might not contain complete data. Unset properties, `null` fields, or unloaded collections could be copied over to the managed entity, overwriting existing values. For partial updates from an HTTP request, load the existing entity and apply only the fields allowed to change.

## 8. Why Must You Use the Return Value of save()?

In the persist branch, Spring Data usually returns the same instance that was persisted. In the merge branch, JPA may return a managed instance that is different from the source object.

Example:

~~~java
Customer detached = getDetachedCustomer();

Customer saved = repository.save(detached);

// Continue using saved.
saved.setName("Updated name");
~~~

If you continue modifying `detached`, those changes are not tracked by the persistence context. Therefore, always assign the result of `save()` to a variable when the entity might go through the merge branch.

This is one of the most common mistakes when using `save()` with detached entities.

## 9. How Do save(), flush(), and commit Differ?

`save()` chooses persist or merge and returns the entity. It does not mean the database has immediately committed the data.

- **save:** puts the entity into the repository's save flow; SQL execution may be deferred.
- **flush:** instructs the persistence context to synchronize pending changes to the database.
- **commit:** ends the transaction successfully and confirms the changes according to the database's transaction mechanism.

Example:

~~~java
@Transactional
public Customer createAndFlush(String name) {
    Customer customer = repository.save(new Customer(name));
    repository.flush();
    return customer;
}
~~~

`saveAndFlush()` is a convenience method combining save and flush. Flush sends the necessary changes to the database and can expose constraint errors earlier, but if the enclosing transaction has not yet committed, the transaction can still roll back.

You should not mechanically call flush after every save. Flush is typically needed when the application must observe database errors at a specific point, ensure SQL has been sent before a subsequent query, or synchronize state before a special operation.

## 10. persist/merge and Cascade Between Entities

When an entity has relationships with other entities, persist or merge can be propagated according to the declared cascade settings.

Example:

~~~java
@OneToMany(
    mappedBy = "customer",
    cascade = {CascadeType.PERSIST, CascadeType.MERGE}
)
private List<Address> addresses = new ArrayList<>();
~~~

- `CascadeType.PERSIST` propagates the persist operation from the source entity to target entities.
- `CascadeType.MERGE` propagates the merge operation to target entities.
- `CascadeType.ALL` includes both persist and merge along with the other cascade operations.

Without declaring the appropriate cascade, persisting a parent entity does not automatically make all child entities managed. When a relationship points to an unpersisted transient entity without cascade PERSIST, the provider may report a transient object/reference error.

You should not add `CascadeType.ALL` to every relationship. Consider lifecycle ownership, whether child entities can be shared, and the impact of each cascade operation.

## 11. Common Mistakes When Using save()

### 11.1. An Entity Has an ID but Is Actually New

If the ID is manually assigned, the default rule may treat an entity with a non-`null` ID as existing. `save()` then calls merge instead of persist.

How to handle it:

- Use `@Version` with a wrapper type like `Long` if it fits the model.
- Or implement `Persistable<ID>` and clearly define `isNew()`.
- Test both new entities and entities loaded from the database.

### 11.2. Calling save Without Using the Returned Object

When merging, the source object remains detached. If you ignore the result of `save()`, subsequent code may mistakenly modify the object that is no longer managed.

How to handle it: always use the instance returned from `save()` if the entity can go through the merge branch.

### 11.3. Merging an Incomplete Object Overwrites Columns

An incoming DTO containing only `id` and a few submitted fields might be mapped into an entity missing the remaining fields. If you merge that object, missing or `null` states can overwrite existing data.

How to handle it: load the managed entity by ID, check update permissions, and then update only the properties present in the request. For partial updates, clearly distinguish between "field not sent" and "field sent with value null".

### 11.4. Confusing merge with Upsert

Merge is a JPA lifecycle operation, not a guarantee of an atomic SQL upsert statement. Do not use it as a deduplication mechanism or to synchronize multiple concurrent requests. If uniqueness must be guaranteed, use a unique constraint and handle conflicts at the database level.

### 11.5. Ignoring Optimistic Locking

Two requests loading the same entity, each modifying a different field and then both merging, can cause overwrites if there is no concurrency control mechanism.

Using `@Version` allows the provider to check the version during UPDATE. If the version has changed since the entity was read, the older transaction may fail with an optimistic locking exception. At the Spring layer, the error may be translated into `ObjectOptimisticLockingFailureException` depending on the call path and exception translation.

## 12. Process for Choosing persist or merge

When writing a service, you can decide using the following steps:

1. Determine whether the object is a new entity or has already been saved.
2. Check Spring Data's new-entity detection rules: `Persistable.isNew()`, version property, or ID.
3. For a new entity, let `save()` choose persist, or call `EntityManager.persist()` if working directly with JPA.
4. For a detached entity, only merge when you genuinely want to copy the source object's state into the persistence context.
5. For an entity already managed in a transaction, modify it directly and let dirty checking handle it.
6. Always use the instance returned from `save()` when the merge branch can occur.
7. Flush only when SQL synchronization is needed at a specific point; commit belongs to the transaction.
8. Check cascade and `@Version` when the entity has relationships or when multiple transactions update the same data.

In most Spring Data JPA applications, the service does not need to branch manually to call `persist()` or `merge()` for each entity. Let repository `save()` handle it via default entity-state detection, unless the application has a clear reason to customize it.

## 13. Key Takeaways

- Spring Data JPA's `save()` chooses `persist()` or `merge()` based on `isNew(entity)`.
- `persist()` makes the source object itself managed.
- `merge()` copies state into a managed instance and returns that instance; the detached source object remains detached.
- By default, Spring Data typically checks `Persistable.isNew()`, then null/non-null wrapper version, then null/non-null ID according to its new-entity detection rules.
- Manually assigned IDs require an appropriate new-entity detection strategy.
- Managed entities undergo dirty checking; there is no need to call save again just to track changes.
- `save()` does not mean flush or commit.
- Merging an incomplete object can overwrite existing fields; partial updates should load the managed entity and apply allowed fields.
- `@Version` helps detect concurrent updates.
- Cascade PERSIST and MERGE determine whether operations propagate to related entities.

Understanding entity states and the return value of `merge()` is the key to using `save()` correctly. When creating a new entity, persist puts the object into the persistence context; when working with detached state, merge copies the state to a managed instance; and when the entity is already managed, dirty checking is usually sufficient.