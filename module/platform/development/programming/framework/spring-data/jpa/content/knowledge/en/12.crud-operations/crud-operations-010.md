# flush, saveAndFlush, and saveAllAndFlush

## Objectives

In JPA, changes to managed entities are typically tracked in the persistence context and synchronized to the database upon flush. Spring Data JPA provides the `flush()`, `saveAndFlush(entity)`, and `saveAllAndFlush(entities)` methods so the application can explicitly request synchronization at required points.

The three methods serve different roles:

- `flush()`: synchronizes all pending changes in the persistence context to the database.
- `saveAndFlush(entity)`: saves a single entity using the repository's mechanism, then flushes the persistence context.
- `saveAllAndFlush(entities)`: saves a group of entities, then flushes the persistence context.

Flush does not end the transaction and does not mean commit. Understanding this boundary helps determine exactly when SQL is sent, detect constraint errors early, re-read data within the same transaction, and optimize processing across many records.

After this lesson, you will be able to distinguish save, flush, and commit; choose among save, saveAndFlush, and saveAllAndFlush; understand that flush affects the entire persistence context; know when database errors surface; use flush properly in transactions, tests, and batch processing; and avoid assuming saveAllAndFlush always generates a single bulk insert SQL statement.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA.

## 1. Persistence Context and When SQL Is Written

JPA manages entities through the persistence context. When an entity is in the managed state, the provider tracks changes on persistent properties. This mechanism is called dirty checking.

Example:

```java
@Transactional
public void renameEmployee(Long id) {
    Employee employee = employeeRepository.findById(id)
            .orElseThrow();

    employee.setFullName("An Nguyen");
    // No need to call save() again.
}
```

When the transaction completes successfully, JPA flushes necessary changes before committing. The provider generates the corresponding SQL, such as UPDATE employees, and the database executes the statement within the transaction.

We need to distinguish three moments:

1. **Object modification:** the managed Java object changes in memory.
2. **Flush:** JPA synchronizes persistence context changes with the database via SQL.
3. **Commit:** the database confirms the transaction succeeded and changes become committed data.

```text
Modify managed entity
        |
        v
Persistence context records change
        |
        | flush()
        v
SQL is sent to the database
        |
        | commit transaction
        v
Transaction completes successfully
```

Flush does not end the transaction. If the transaction rolls back after a flush, the SQL changes belonging to that transaction are still rolled back.

## 2. flush(): Synchronizing the Persistence Context

`EntityManager.flush()` instructs JPA to synchronize the state of the current persistence context to the database. Spring Data JPA exposes the corresponding method on `JpaRepository`:

```java
void flush();
```

Example:

```java
@Service
public class EmployeeService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void updateAndFlush(Long id) {
        Employee employee = entityManager.find(Employee.class, id);

        employee.setFullName("An Nguyen");

        entityManager.flush();
        // UPDATE has been sent to the database in the current transaction.
        // The transaction continues running after this line.
    }
}
```

### 2.1. Which Entities Does Flush Apply To?

Flush does not write only the entity on which you just called `save` or the entity passed to a specific method. It synchronizes necessary changes across the entire persistence context.

```java
@Transactional
public void flushAllPendingChanges(Long firstId, Long secondId) {
    Employee first = employeeRepository.findById(firstId).orElseThrow();
    Employee second = employeeRepository.findById(secondId).orElseThrow();

    first.setFullName("First updated");
    second.setFullName("Second updated");

    employeeRepository.flush();
}
```

Both changes can be sent to the database upon flush. Other managed entities with pending changes in the same persistence context can also be synchronized.

Therefore, flush is a persistence-context-level operation, not a command to write just a single entity.

### 2.2. Flush Is Not Commit

After a flush:

- SQL has been sent to the database and executed within the current transaction.
- Constraints may be checked and errors may surface.
- The transaction remains open if managed by an outer transaction.
- Other transactions generally do not see uncommitted changes yet, depending on isolation level and database.
- A rollback can still undo the flushed changes.

Example:

```java
@Transactional
public void flushThenFail(Long id) {
    Employee employee = employeeRepository.findById(id).orElseThrow();

    employee.setFullName("Temporary name");
    employeeRepository.flush();

    throw new IllegalStateException("Cancel operation");
}
```

If the exception triggers a transaction rollback, the flushed UPDATE is also rolled back. That SQL has executed does not mean data has been committed.

### 2.3. When Does JPA Flush Automatically?

The application does not always need to call `flush()` manually. Under the default `AUTO` flush mode, JPA can flush automatically at points needed to ensure consistent query results—such as before a query that might be affected by pending changes, and before transaction commit.

Flush modes:

- `FlushModeType.AUTO`: the provider must ensure relevant changes are reflected in query results; the provider may flush at appropriate times.
- `FlushModeType.COMMIT`: the provider is permitted to defer flushing until commit, though it may still flush earlier in certain situations.

Do not rely on a specific flush schedule beyond the JPA contract. If you need SQL sent before a subsequent operation or want to detect errors at a specific point, call flush explicitly.

## 3. save(entity): Requesting to Save an Entity

`JpaRepository` inherits the `save` method from the CRUD contract:

```java
<S extends T> S save(S entity);
```

In Spring Data JPA, `save` determines whether the entity is new or existing and chooses the JPA operation:

- Entity detected as new: typically calls `EntityManager.persist(entity)`.
- Entity detected as existing: typically calls `EntityManager.merge(entity)`.

`save` does not guarantee that SQL is sent immediately at the call site. While the entity remains managed, changes may simply be tracked in the persistence context and flushed later.

Example:

```java
@Transactional
public Employee createEmployee(String fullName) {
    Employee employee = new Employee(fullName);

    Employee saved = employeeRepository.save(employee);

    // saved may already be managed in the persistence context.
    // SQL may not have been flushed at this moment.
    return saved;
}
```

If the entity is merged, the object returned from `save` may differ from the input object. Use the returned value when continuing operations.

For a managed entity already loaded in a transaction, modifying properties usually does not require calling `save` again; dirty checking writes changes on flush.

## 4. saveAndFlush(entity): Save and Flush Immediately

`JpaRepository` provides:

```java
<S extends T> S saveAndFlush(S entity);
```

Semantically, this method:

1. Invokes the repository's save mechanism to persist or merge the entity.
2. Calls flush to synchronize the persistence context to the database.
3. Returns the saved entity per the save contract.

Example:

```java
@Transactional
public Employee createAndFlush(String fullName) {
    Employee employee = new Employee(fullName);

    Employee saved = employeeRepository.saveAndFlush(employee);

    // Pending changes in the persistence context have been flushed.
    return saved;
}
```

Use `saveAndFlush` when you need an immediate flush after saving an entity, such as:

- Wanting to catch constraint violations at a specific point in business logic.
- Needing to ensure SQL has executed before running a subsequent operation in the same transaction.
- Needing database-generated values after INSERT/UPDATE that the provider synchronizes back into the entity.
- Executing a persistence workflow that requires a clear flush boundary.

There is no need to use `saveAndFlush` for every save. Flushing too frequently can reduce opportunities to batch multiple changes into SQL batches and add extra round-trips to the database.

### 4.1. saveAndFlush Does Not Flush Only the Passed Entity

Suppose the persistence context holds three managed entities and all three have modifications. Calling:

```java
employeeRepository.saveAndFlush(employee);
```

can flush changes for all three entities, not only `employee`. This is a consequence of flushing at the persistence context level.

If you only want to write a specific group of entities, design appropriate transaction/persistence context boundaries. Do not assume `saveAndFlush` is an isolated single-row update command.

## 5. saveAllAndFlush(entities): Save Multiple Entities Then Flush

`JpaRepository` also provides:

```java
<S extends T> List<S> saveAllAndFlush(Iterable<S> entities);
```

This method accepts an Iterable of entities, saves each entity via the repository mechanism, and flushes after finishing the save group.

Example:

```java
@Transactional
public List<Employee> importSmallGroup(List<EmployeeInput> inputs) {
    List<Employee> employees = inputs.stream()
            .map(input -> new Employee(input.fullName()))
            .toList();

    return employeeRepository.saveAllAndFlush(employees);
}
```

The result is a list of saved entities per the repository contract. This method is useful when a small group of entities must be synchronized to the database before the next step in the same transaction.

### 5.1. Is saveAllAndFlush a Single Bulk INSERT?

No. The method name does not promise that the entire list is written using a single SQL statement or a single bulk insert.

Spring Data JPA processes entities via the save mechanism; the JPA provider decides SQL and batching based on mappings, ID generation, JDBC batching, and the database.

A group of entities can generate multiple INSERT/UPDATE statements. If you want batch optimization, configure and measure it separately.

### 5.2. The Persistence Context Still Keeps Entities Managed

`saveAllAndFlush` flushes data but does not automatically clear the persistence context. Entities can remain managed after the method returns.

If processing hundreds of thousands of records, repeatedly calling `saveAllAndFlush` alone can cause the persistence context to hold many objects and snapshots. Consider flushing and then clearing per batch.

## 6. Comparing the Three Methods

| Method | Saves entity? | Flushes? | Flush scope |
|---|---|---|---|
| `flush()` | Does not call save for input entities | Yes | Entire persistence context |
| `saveAndFlush(entity)` | Yes, one entity | Yes, after save | Entire persistence context |
| `saveAllAndFlush(entities)` | Yes, a group of entities | Yes, after saveAll | Entire persistence context |

Related CRUD APIs:

| Method | Meaning |
|---|---|
| `save(entity)` | Requests saving one entity; does not guarantee immediate flush |
| `saveAll(entities)` | Requests saving a group of entities; does not guarantee immediate flush |
| `flush()` | Flushes pending changes |
| `saveAndFlush(entity)` | Saves one entity then flushes |
| `saveAllAndFlush(entities)` | Saves a group of entities then flushes |

Choose the method based on requirements:

- Normal saving inside a transaction: `save` or dirty checking.
- Saving one entity and needing SQL executed immediately: `saveAndFlush`.
- Saving a group and needing a flush right after that group: `saveAllAndFlush`.
- Multiple managed entities already modified and needing to synchronize the entire context: `flush`.

## 7. Constraint Violations and Error Detection Timing

Many database errors only surface when SQL is sent to the database. If you only call `save`, errors might only surface at an automatic flush before a query or before commit.

For example, the employees table has a unique constraint on email. When saving two employees with the same email, the database rejects one of the INSERT/UPDATE statements.

```java
@Transactional
public Employee createEmployee(String email) {
    Employee employee = new Employee(email);

    Employee saved = employeeRepository.save(employee);

    employeeRepository.flush();
    // Unique constraint violation can surface right here.

    return saved;
}
```

Calling flush surfaces the error closer to the save operation. The exact exception depends on the provider/database and Spring's exception translation; typically you will see exceptions in the data integrity or persistence exception family.

### 7.1. Where to Catch Errors?

Errors can be handled in the service or in an exception-handling layer outside the transaction. If the transaction has been marked rollback-only after a persistence error, do not continue writing data in that transaction as if everything were still normal.

Example of handling the exception in the caller:

```java
try {
    employeeService.createEmployee(email);
} catch (DataIntegrityViolationException ex) {
    // Translate to an appropriate business error, e.g., email already exists.
}
```

If you want to pre-check for duplicates before saving to return a friendly message, you can use an exists query. However, pre-checking does not eliminate race conditions between concurrent transactions; the database unique constraint remains the final safeguard.

### 7.2. A Flush Error Cannot Be Fixed by Continuing in the Same Transaction

After a SQL statement fails, the transaction may no longer be usable depending on the database/provider and transaction state. The safe path is to let the transaction roll back and handle recovery in a new transaction if needed.

Do not catch an exception and keep calling repositories in the same transaction without understanding the rollback-only state. Spring may fail at commit time because the transaction was already marked rollback-only.

## 8. Generated IDs and Database-Generated Values

A common reason to flush is needing values generated by the database after saving.

Example with an auto-increment ID:

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
}
```

With the `IDENTITY` strategy, the provider typically needs to execute the INSERT to obtain the database-assigned ID. Thus, the ID may be available right after `save` in many cases. However, exact timing depends on the ID generation strategy and provider.

`saveAndFlush` ensures the persistence context is flushed before the method completes normally, but it does not mean every database-computed/default/trigger value is automatically reloaded into the object. If the mapping/provider does not automatically retrieve generated values, you may need `refresh(entity)` after flush.

Example:

```java
Employee saved = employeeRepository.saveAndFlush(employee);

entityManager.refresh(saved);
// Reload database state if trigger/default-updated values are needed.
```

Only refresh when needed; this operation overwrites the entity's current state with database data.

## 9. Transaction Boundaries and Data Visibility

You must view `saveAndFlush` in the context of transactions.

### 9.1. With an Outer Transaction

```java
@Transactional
public void process(Long id) {
    Employee employee = employeeRepository.findById(id).orElseThrow();

    employee.setFullName("Updated");
    employeeRepository.flush();

    // Transaction is still open.
    // Subsequent operations in the transaction can read this change.
}
```

When the service has `@Transactional`, repository calls join the current transaction under default propagation. Flush only sends SQL; commit occurs when the service method completes normally via the transaction interceptor.

### 9.2. Without an Outer Transaction

Write methods inherited from Spring Data repositories typically carry their own transaction configuration. If you call `saveAndFlush` directly without an outer transaction, the repository-opened transaction can commit once the method finishes normally.

Therefore, to coordinate multiple operations into an atomic business workflow, place `@Transactional` on the service wrapping the whole operation.

### 9.3. Can Other Transactions See Data After Flush?

Normally, other transactions cannot see uncommitted changes. Flush does not make data committed.

Visibility also depends on isolation level and database behavior. Do not use flush as a way to publish data to other transactions. If other transactions need to see the data, the current transaction must commit per the business workflow.

## 10. Batch Processing: Flushing and Clearing in Batches

For large data volumes, process in small batches:

```java
@Service
public class EmployeeImportService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void importEmployees(List<EmployeeInput> inputs) {
        int batchSize = 50;

        for (int i = 0; i < inputs.size(); i++) {
            EmployeeInput input = inputs.get(i);

            entityManager.persist(new Employee(input.fullName()));

            if ((i + 1) % batchSize == 0) {
                entityManager.flush();
                entityManager.clear();
            }
        }

        entityManager.flush();
        entityManager.clear();
    }
}
```

Why use both?

- `flush()`: sends the current batch's SQL to the database.
- `clear()`: detaches all entities in the persistence context, reducing memory because JPA does not have to retain every processed entity and snapshot.

Key cautions:

- `clear()` detaches every entity in the context, even entities outside the current batch.
- Do not use cleared entities as if they were still managed.
- If changes need to be kept before clearing, flush before clearing.
- If the transaction is still one large transaction, locks and transaction logs can still grow long. Consider splitting into multiple transactions per batch when business rules permit.
- JDBC batching requires provider and driver configuration; flush/clear only manages the persistence context and does not guarantee batching by itself.
- With `GenerationType.IDENTITY`, INSERT batching capability may be limited depending on Hibernate and the database.

A common Hibernate configuration to test JDBC batching:

```yaml
spring:
  jpa:
    properties:
      hibernate:
        jdbc:
          batch_size: 50
        order_inserts: true
        order_updates: true
```

Values should be measured using real data. Too large a batch can increase memory and lock duration; too small a batch can increase round-trips.

## 11. Testing Flush

`@DataJpaTest` typically runs within a transaction and rolls back after each test. `flush()` can be used to force SQL execution before assertions, helping surface mapping/constraint errors at a clear point in the test.

Example:

```java
@DataJpaTest
class EmployeeRepositoryTest {

    @Autowired
    private EmployeeRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    @Test
    void saveAndFlushPersistsEmployee() {
        Employee employee = new Employee("An Nguyen");

        Employee saved = repository.saveAndFlush(employee);

        assertThat(saved.getId()).isNotNull();

        entityManager.clear();

        Employee loaded = repository.findById(saved.getId())
                .orElseThrow();

        assertThat(loaded.getFullName()).isEqualTo("An Nguyen");
    }
}
```

The test assumes the entity uses a generated ID and the repository and test dependencies are configured. `saveAndFlush` sends the INSERT to the database; `clear` forces the next read to reload the entity instead of returning the managed instance.

Another test can verify a group:

```java
@Test
void saveAllAndFlushStoresAllEmployees() {
    List<Employee> saved = repository.saveAllAndFlush(List.of(
            new Employee("An"),
            new Employee("Binh")
    ));

    assertThat(saved).hasSize(2);
    assertThat(saved).allMatch(employee -> employee.getId() != null);
}
```

In tests expecting constraint violations, flush inside the assertion so the error occurs at the check point rather than waiting for test framework teardown/commit. The specific exception caught should match the provider, Spring exception translation, and database in use.

## 12. Common Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Thinking save already sent SQL immediately | Save may only mutate the persistence context | Call flush when SQL must execute at a specific point |
| Thinking flush already committed | Confusing SQL synchronization with transaction completion | Let the transaction commit successfully |
| Unique error only appears at end of transaction | SQL was not flushed at save call | Flush intentionally to detect errors early |
| saveAndFlush causes lots of SQL to run | Flush applies to the entire persistence context | Check other managed entities with pending changes |
| saveAllAndFlush does not emit one bulk INSERT | API does not promise a single SQL statement | Configure JDBC batching and measure |
| Memory keeps growing when looping saveAllAndFlush | Flush does not clear the persistence context | Flush then clear in batches |
| Data flushed but other transactions cannot see it | Transaction has not committed | Commit at the business boundary |
| Exception caught but commit still fails | Transaction was marked rollback-only | Let the transaction roll back and handle in a new transaction |
| Generated column still stale in object | Provider did not reload database-generated values | Refresh or configure appropriate generated property mapping |

## 13. Checklist for Choosing Flush APIs

- [ ] Only need to request saving an entity: use `save`.
- [ ] Need to save one entity and flush immediately: use `saveAndFlush`.
- [ ] Need to save a group of entities and flush: use `saveAllAndFlush`.
- [ ] Modified managed entities and need to synchronize the whole context: use `flush`.
- [ ] Need to preserve changes before clearing: flush before clear.
- [ ] Need to read database-generated values: check whether the provider auto-synchronizes or if refresh is needed.
- [ ] Need to coordinate multiple atomic operations: place the transaction on the service.
- [ ] Processing large datasets: consider batch flush/clear and JDBC batching.
- [ ] Do not treat flush as commit or as a way to make data visible to other transactions.
- [ ] Test constraints by flushing at the assertion point.

## Conclusion

`flush()` synchronizes all pending changes in the persistence context to the database. `saveAndFlush(entity)` saves one entity and flushes; `saveAllAndFlush(entities)` saves a group and flushes. All three operations operate within a transaction and do not automatically commit an enclosing transaction.

Use normal save for most CRUD operations. Only flush explicitly when SQL must run before a subsequent step, when you want to catch database errors at a specific point, or when managing batch processing. For large data volumes, combine batch flush and clear, configure JDBC batching, and verify performance with real metrics.