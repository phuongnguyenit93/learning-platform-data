# detach, clear, refresh, and When State Needs to Be Resynchronized

## Objective

JPA manages entities through a persistence context. Within a persistence context, loaded or saved entities are in the managed state; changes to managed entities are tracked by JPA and can be written to the database on flush.

The three operations `EntityManager.detach`, `EntityManager.clear`, and `EntityManager.refresh` control the relationship between Java objects in memory and data in the database:

- `detach(entity)`: stops managing a specific entity.
- `clear()`: stops managing all entities in the persistence context.
- `refresh(entity)`: reloads the database state of a managed entity, overwriting its current in-memory state.

This lesson explains the entity lifecycle, differences among the three operations, when to use them, their effects on transactions, bulk queries, lazy loading, and common mistakes.

After this lesson, you will be able to:

- Distinguish transient/new, managed, detached, and removed.
- Know which changes JPA synchronizes automatically.
- Use detach/clear to control the persistence context and memory.
- Use refresh when you need to retrieve the state currently in the database.
- Avoid losing unflushed changes or unintentionally overwriting data.
- Safely combine flush/clear/refresh in services and batch processing.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA.

## 1. Persistence context and entity lifecycle

A persistence context is the collection of entity instances currently managed by an EntityManager. You can view it as a working area that tracks Java objects and their corresponding database state.

When an entity is in the managed state:

- JPA tracks changes to persistent properties.
- The entity has identity within the persistence context: the same entity/database identity is represented by the same managed instance in that context.
- On flush, JPA synchronizes changes with the database using the appropriate INSERT, UPDATE, or DELETE.
- When the transaction commits, flushed changes are committed with the transaction.

Four common states:

| State | Meaning | Does JPA automatically track changes? |
|---|---|---|
| New / transient | Newly created Java object, not yet managed by a persistence context | No |
| Managed / persistent | Entity currently managed by an EntityManager | Yes |
| Detached | Entity that was previously managed but has left the persistence context | No |
| Removed | Managed entity marked for deletion | Yes, JPA will synchronize the DELETE operation on flush |

### 1.1. State transition diagram

<box border radius="lg" padding={3} gap={2}>
  <box background="surface-secondary" radius="md" padding={3} align="center">
    **New / transient**
    <caption color="secondary">new Employee(...)</caption>
  </box>
  <row justify="center">
    <icon name="arrow-down" color="secondary" size="lg"/>
    <caption color="secondary">persist() or save() when recognized as new</caption>
  </row>
  <box background="rgba(22,163,74,0.10)" radius="md" padding={3} align="center">
    **Managed**
    <caption color="secondary">Tracked in the persistence context</caption>
  </box>
  <grid columns={2} gap={2}>
    <grid-item>
      <box align="center" gap={1}>
        <icon name="arrow-down" color="secondary"/>
        <caption color="secondary">detach() / clear()</caption>
        <box background="surface-secondary" radius="md" padding={2} width="100%" align="center">
          **Detached**
          <caption color="secondary">No more dirty checking</caption>
        </box>
      </box>
    </grid-item>
    <grid-item>
      <box align="center" gap={1}>
        <icon name="arrow-down" color="secondary"/>
        <caption color="secondary">remove()</caption>
        <box background="surface-secondary" radius="md" padding={2} width="100%" align="center">
          **Removed**
          <caption color="secondary">Will be deleted on flush</caption>
        </box>
      </box>
    </grid-item>
  </grid>
  <caption color="secondary">A detached entity can be merged to produce a new managed instance. A removed entity can be re-persisted per JPA rules before actual deletion occurs.</caption>
</box>

### 1.2. Example entity

```java
@Entity
@Table(name = "employees")
public class Employee {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String fullName;

    protected Employee() {
    }

    public Employee(String fullName) {
        this.fullName = fullName;
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public void setFullName(String fullName) {
        this.fullName = fullName;
    }
}
```

Repository:

```java
public interface EmployeeRepository
        extends JpaRepository<Employee, Long> {
}
```

In a service annotated with `@Transactional`, calling `findById` returns a managed entity in the transaction's persistence context. If `fullName` is modified, JPA can write the change on flush without needing to call `save` again.

## 2. How does flush differ from commit and clear?

Before using detach/clear/refresh, distinguish `flush` from commit.

- **Flush**: synchronizes changes tracked by the persistence context to the database via SQL. Flush does not end the transaction.
- **Commit**: ends the transaction successfully and commits the transaction's changes.
- **Clear**: removes all managed entities from the persistence context; does not automatically write or commit changes.
- **Refresh**: reloads an entity's state from the database into a managed entity.

Example:

```java
@Transactional
public void updateEmployee(Long id) {
    Employee employee = repository.findById(id).orElseThrow();

    employee.setFullName("An Nguyen");

    entityManager.flush(); // Sends UPDATE to the database.
    // The transaction is still open here.

    entityManager.clear(); // Employee is no longer managed.
    // Commit only happens when the transaction finishes successfully.
}
```

If the transaction rolls back after flush, the SQL changes belonging to the transaction are still rolled back by the database's transaction mechanism. Flush does not mean the data has been committed and made visible to all other transactions.

JPA can auto-flush before certain queries or before commit depending on the flush mode. Therefore, do not rely on the assumption that SQL is only sent when `flush()` is called explicitly.

## 3. detach(entity): stopping management of one entity

`EntityManager.detach(entity)` removes a specific managed entity from the persistence context. After detach:

- The entity becomes detached.
- Changes to the object are no longer automatically dirty checked.
- Calling getters/setters still works on the Java object.
- Those changes are not automatically written to the database when the transaction commits.
- Unloaded lazy relationships may no longer be accessible after the entity is detached, depending on the provider and proxy state.

Example:

```java
@Service
public class EmployeeService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void detachExample(Long id) {
        Employee employee = entityManager.find(Employee.class, id);

        entityManager.detach(employee);

        employee.setFullName("Changed in memory");
        // No automatic UPDATE for changes made after detach.
    }
}
```

The entity remains a normal Java object. `detach` does not delete the object from Java memory, does not delete the database row, and does not end the transaction. It only stops managing the entity in the persistence context.

### 3.1. What to do if you want to save a detached entity again?

Use `merge` or `repository.save` according to the appropriate strategy:

```java
@Transactional
public Employee updateDetached(Employee detached) {
    Employee managed = entityManager.merge(detached);

    managed.setFullName("Updated through managed instance");

    return managed;
}
```

`merge` copies the state of the input object into a managed instance and returns that managed instance. The input object remains detached; continue using the returned value.

Be careful when merging an object received from a request containing only a subset of properties. Merge can copy null/default values from the input object onto the managed entity, losing data if the object does not contain all necessary state. For business updates, it is usually better to load the existing entity and modify only the permitted fields.

### 3.2. CascadeType.DETACH

If an association declares `CascadeType.DETACH`, the detach operation can propagate to the related entity:

```java
@ManyToOne(
    fetch = FetchType.LAZY,
    cascade = CascadeType.DETACH
)
@JoinColumn(name = "department_id")
private Department department;
```

You do not need to add cascade detach to every association. Only use it when the persistence context lifecycle of related entities needs to be handled together. `CascadeType.ALL` also includes DETACH, though you should not pick ALL out of habit if you do not need every cascade operation.

## 4. clear(): detaching the entire persistence context

`EntityManager.clear()` removes all managed entities from the current persistence context.

Example:

```java
@Transactional
public void clearExample(Long firstId, Long secondId) {
    Employee first = entityManager.find(Employee.class, firstId);
    Employee second = entityManager.find(Employee.class, secondId);

    first.setFullName("Changed before clear");

    entityManager.flush();
    entityManager.clear();

    Employee reloaded = entityManager.find(Employee.class, firstId);
    // reloaded is a new managed instance in the current persistence context.
}
```

After `clear()`, both `first` and `second` are detached. The next `find` creates/loads a new managed instance in the current persistence context.

### 4.1. clear does not delete database data

The method name can be misleading, but `clear()` does not mean truncating tables or deleting data. It only clears entities out of the persistence context.

| Operation | Result |
|---|---|
| `entityManager.clear()` | Detaches all managed entities |
| `repository.deleteAll()` | Requests deletion of the repository's entities |
| `entityManager.remove(entity)` | Marks a managed entity for deletion |
| `entityManager.flush()` | Synchronizes changes to the database |

### 4.2. clear can lose unflushed changes

This point requires special attention.

```java
@Transactional
public void unsafeClear(Long id) {
    Employee employee = entityManager.find(Employee.class, id);

    employee.setFullName("New name");

    entityManager.clear();
    // The entity was detached before the change was flushed.
    // The change "New name" may be lost.
}
```

If you want to preserve changes made before clearing, flush first:

```java
employee.setFullName("New name");

entityManager.flush();
entityManager.clear();
```

Flush sends the UPDATE to the database within the transaction. Clear then removes the entities from the persistence context. If the transaction rolls back, the UPDATE is still rolled back.

### 4.3. Using clear in batch processing

When processing tens of thousands of entities in a single transaction, the persistence context can accumulate many objects and snapshots, increasing memory usage. You can flush and clear in batches:

```java
@Transactional
public void importEmployees(List<EmployeeInput> inputs) {
    int batchSize = 50;
    int count = 0;

    for (EmployeeInput input : inputs) {
        Employee employee = new Employee(input.fullName());
        entityManager.persist(employee);

        count++;

        if (count % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
```

This pattern prevents the persistence context from growing indefinitely with the number of processed entities. However:

- `clear()` detaches all entities, not just those in the batch just processed.
- Objects still held in Java variables remain alive, but are no longer managed.
- If there are unloaded lazy relationships, accessing them after clear can fail.
- Flush does not commit. A very large transaction can still hold locks and transaction logs for a long time; consider splitting transactions per batch if business rules allow.
- With Hibernate, batch inserts/updates also require proper JDBC batching configuration and ID strategy; flush/clear alone does not guarantee batched SQL statements.

## 5. refresh(entity): reloading state from the database

`EntityManager.refresh(entity)` re-reads the database state of a managed entity and overwrites the current state of the object in the persistence context.

Use refresh when:

- A SQL/native query or an external process modified the row currently held by the entity.
- A trigger or database mechanism updated a value that the application needs to read back.
- You want to discard local unflushed changes and restore the database state.
- You need to refresh an entity after a special persistence operation.

Example:

```java
@Transactional
public Employee refreshExample(Long id) {
    Employee employee = entityManager.find(Employee.class, id);

    entityManager.refresh(employee);

    return employee;
}
```

After refresh, the persistent properties of `employee` are resynchronized with the database data visible in the current transaction.

### 5.1. refresh overwrites in-memory changes

Example:

```java
@Transactional
public void refreshDiscardsLocalChange(Long id) {
    Employee employee = entityManager.find(Employee.class, id);

    employee.setFullName("Local unsaved value");

    entityManager.refresh(employee);

    // fullName is reloaded from the database.
    // The value "Local unsaved value" is discarded.
}
```

If changes have not been flushed, refresh overwrites them. Therefore, only refresh when intentionally discarding local state or after synchronizing the changes you want to keep.

If you need to preserve your changes before reloading, you can flush first and then refresh:

```java
employee.setFullName("An Nguyen");

entityManager.flush();
entityManager.refresh(employee);
```

Within the same transaction, refresh reads the database state visible to the current transaction, including that transaction's own flushed changes. Refresh does not commit the transaction.

### 5.2. refresh requires a managed entity

`refresh` is used with a managed entity. If you pass a detached or new object, JPA cannot refresh that object as a managed entity and may throw `IllegalArgumentException`.

If the entity is detached, reload it via the repository/EntityManager, or merge and then refresh the returned managed instance:

```java
Employee managed = entityManager.merge(detachedEmployee);
entityManager.refresh(managed);
```

However, merging before refreshing may copy detached state into the managed instance right before refresh overwrites it again. If the goal is simply to get the latest data, reloading the entity by ID is usually clearer.

If the row has been deleted in the database or no longer exists in the state visible to the transaction, refresh may fail. Handle the case where the entity no longer exists.

### 5.3. CascadeType.REFRESH

You can declare cascade refresh:

```java
@OneToMany(
    mappedBy = "department",
    cascade = CascadeType.REFRESH
)
private List<Employee> employees = new ArrayList<>();
```

When refreshing Department, the operation can cascade to related Employees. Use intentionally because refresh can overwrite local changes on managed child entities as well. `CascadeType.ALL` also includes REFRESH.

## 6. Comparing detach, clear, and refresh

| Operation | Scope | State after operation | In-memory data |
|---|---|---|---|
| `detach(entity)` | One entity | Entity is detached | Retains current values, but no longer dirty checked |
| `clear()` | Entire persistence context | All managed entities become detached | Java objects remain, but are no longer tracked |
| `refresh(entity)` | One managed entity, can cascade | Entity remains managed | Overwritten with database state |

Choose the operation based on your goal:

- Want to stop tracking one specific object: `detach`.
- Want to evict all managed entities from the persistence context: `clear`.
- Want to reload database data for a managed entity: `refresh`.
- Want to save pending changes before detach/clear: `flush` first.
- Want to update a detached entity into a managed instance: `merge` or reload by ID.

## 7. When does state need to be resynchronized with the database?

The persistence context is the EntityManager's first-level cache. An already managed entity can hold stale data compared to the database if another operation modifies the row without updating the object sitting in the context.

Common situations:

### 7.1. Bulk JPQL update/delete

Bulk update/delete executes directly against the database and does not update individual managed entity instances in the persistence context.

Example:

```java
@Modifying(flushAutomatically = true, clearAutomatically = true)
@Query("""
       update Employee e
       set e.active = false
       where e.department.id = :departmentId
       """)
int deactivateByDepartmentId(@Param("departmentId") Long departmentId);
```

Meaning:

- `flushAutomatically = true`: flushes pending changes before running the bulk query.
- `clearAutomatically = true`: clears the persistence context after the query runs to avoid continuing to use stale entity instances.

Without clearing, an Employee entity loaded before the bulk update may still hold `active = true` in memory even though the database changed to false.

Place bulk query methods inside an appropriate transaction; `@Modifying` does not replace `@Transactional`.

### 7.2. Native SQL or stored procedures

If native SQL or a stored procedure updates a row currently managed by the EntityManager, the entity in the persistence context may not automatically know about the change.

You can flush beforehand if pending changes must be kept, run the SQL, and then refresh the specific entity or clear the context and reload.

Illustrative example:

```java
entityManager.flush();

entityManager.createNativeQuery("""
    update employees
    set full_name = :name
    where id = :id
    """)
    .setParameter("name", "An Nguyen")
    .setParameter("id", id)
    .executeUpdate();

entityManager.clear();
```

This snippet illustrates the sequence; in an application, place it in a transactional service and use parameter binding as shown. Clear detaches all managed entities, so only use it when appropriate for the scope of work.

### 7.3. Triggers or database-generated values

Database triggers, default expressions, or computed columns can update values after INSERT/UPDATE. If the application needs to read back the final value, you can:

1. Flush to send the INSERT/UPDATE.
2. Refresh the entity to read the database state.
3. Or use a mapping/generated property mechanism supported by the provider and database.

There is no need to refresh after every save. Use it only when database-created/updated values are not automatically synchronized back into the entity by the current mapping.

### 7.4. Transaction isolation still applies

Refresh reads data that the current transaction is allowed to see according to its isolation level. If the transaction is running under an isolation level such as REPEATABLE READ, refresh may still see an old snapshot even if another transaction has committed changes.

Refresh does not bypass database isolation and does not guarantee seeing all latest system-wide changes. When fresh data from a new snapshot is required, you may need to end the current transaction and start another, depending on business requirements and isolation level.

## 8. EntityManager in Spring Data JPA

In Spring applications, EntityManager is typically injected with `@PersistenceContext`:

```java
@Service
public class EmployeeService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void renameAndRefresh(Long id) {
        Employee employee = entityManager.find(Employee.class, id);

        employee.setFullName("An Nguyen");

        entityManager.flush();
        entityManager.refresh(employee);
    }
}
```

In Spring Boot, the injected EntityManager is typically a proxy bound to the current transaction's persistence context. With a transaction-scoped persistence context, refresh requires an active transaction; if called without an appropriate transaction, JPA may throw `TransactionRequiredException`.

The `detach`, `clear`, and `refresh` operations do not replace transactions. They control persistence context state inside the transaction lifecycle.

## 9. Complete example: detach and merge

```java
@Service
public class EmployeeLifecycleService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public Employee renameThenDetach(Long id) {
        Employee employee = entityManager.find(Employee.class, id);

        employee.setFullName("Changed before detach");
        entityManager.flush();

        entityManager.detach(employee);

        employee.setFullName("Changed after detach");
        // Changes after detach are not dirty checked.

        Employee managed = entityManager.merge(employee);
        // merge returns a managed instance.
        return managed;
    }
}
```

In this example:

- The first change is flushed to the database.
- After detach, the entity is no longer managed.
- The second change only exists in the Java object.
- Merge copies the detached object's state into a managed instance.
- The instance returned from merge is the object to continue using in the transaction.

Note that merge copies the detached entity's state. If the object contains stale data or nulls in fields omitted by a client, merge can overwrite existing values. In update workflows, the safe approach is usually to load the managed entity and modify only permitted properties.

## 10. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Object changes are not saved | Entity was detached or never managed | Load entity in a transaction or merge and use the returned instance |
| Changes lost after clear | Cleared before flushing | Flush before clear if changes need to be kept |
| In-memory values revert to old data | Refresh overwrote local changes | Only refresh when intentionally reloading; flush first if changes must be kept |
| Refresh throws IllegalArgumentException | Entity is not managed or no longer exists | Reload entity by ID or merge and then refresh the managed instance |
| LazyInitializationException after detach | Lazy association was not loaded and context closed | Fetch before detaching or map to DTO inside the transaction |
| Stale entities after bulk update | Bulk query does not synchronize managed entities | Use flush/clear or refresh appropriately |
| Clear causes other objects to lose dirty checking | Clear detaches the entire context | Only clear after handling all changes that need to be preserved |
| Refreshed data is still stale | Isolation level holds a snapshot | End transaction and re-read in a new transaction when a fresh snapshot is needed |

## 11. Operation selection checklist

- [ ] Is the entity currently managed or detached?
- [ ] Are there unflushed changes that need to be preserved?
- [ ] Do you want to detach one entity or the entire persistence context?
- [ ] Do you want to reload database state or merely stop dirty checking?
- [ ] Are there bulk JPQL/native SQL statements or triggers making context data stale?
- [ ] Which lazy relationships will need to be accessed after detach/clear?
- [ ] Do the current transaction and isolation level meet the data-reading requirements?
- [ ] Can DTOs/fetch queries be used instead of keeping entity graphs around for long?

## Conclusion

`detach(entity)` stops managing one entity; `clear()` stops managing all entities in the persistence context; `refresh(entity)` reloads database state and overwrites the current state of a managed entity. Flush synchronizes changes to the database but does not commit the transaction.

Use detach/clear when you need to control the persistence context or process batches, and use refresh when out-of-context changes need to be reflected in a managed entity. Before detaching/clearing, account for unflushed changes; before refreshing, account for in-memory changes that could be overwritten. Understanding these boundaries helps avoid data loss, lazy-loading errors, and out-of-sync entity state.