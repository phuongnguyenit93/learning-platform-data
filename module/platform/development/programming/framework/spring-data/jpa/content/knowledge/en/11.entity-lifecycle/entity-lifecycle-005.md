# How Is Flush Different from Commit?

In JPA, **flush** synchronizes changes currently managed in the persistence context to the database using the necessary SQL statements. **Commit** ends the database transaction and confirms the transaction's changes. Flush can send INSERT, UPDATE, or DELETE, yet the data is still uncommitted; the transaction can still roll back afterward.

This is an important distinction when working with Spring Data JPA. Calling save(), flush(), or saveAndFlush() does not mean data has been committed. To understand when data is actually confirmed, you must follow the persistence context, the transaction manager, and `@Transactional` boundaries together.

## 1. Distinguishing persistence context, flush, and commit

The persistence context is the working area of the EntityManager. It manages tracked entities, entity identity, and changes arising during the entity lifecycle.

When reading an entity into the persistence context, the entity is usually in the managed state. If a property of a managed entity is modified, the JPA provider records the change via dirty checking. SQL may not run immediately when the setter is called.

You can visualize it as:

```text
Java code modifies managed entity
             |
             v
     Persistence context
      (dirty checking)
             |
             | flush
             v
   INSERT / UPDATE / DELETE
             |
             v
       Database transaction
             |
             | commit
             v
     Transaction is confirmed
```

The three steps have different meanings:

- **Change in the persistence context:** Java state is updated and tracked by the provider.
- **Flush:** the provider synchronizes changes that need to be written to the database via SQL within the current transaction.
- **Commit:** the transaction manager/database confirms the transaction; written changes become committed data according to the database's transaction and isolation rules.

Flush does not clear the persistence context, does not end the transaction, and does not transition entities to detached. After flush, entities remain managed and can continue to be modified; a subsequent flush can issue additional SQL.

## 2. Example: modifying an entity without flushing yet

Suppose we have a Customer entity:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public void rename(String name) {
        this.name = name;
    }

    public String getName() {
        return name;
    }
}
```

A service modifies the entity:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void renameCustomer(Long id) {
        Customer customer = repository.findById(id).orElseThrow();

        customer.rename("An Nguyen");

        // Here the entity has changed in the persistence context.
        // The SQL UPDATE may not have been sent to the database yet.
    }
}
```

When rename() is called, JPA is not required to send an UPDATE immediately. Because the entity is managed, dirty checking records that the name property changed. When the transaction flushes, the provider issues the SQL UPDATE. When the transaction commits, the database confirms the change.

If the method finishes normally, the Spring transaction interceptor typically performs commit after the method body returns. Thus, even if the code never calls flush() or commit(), the change is still persisted when the transaction completes successfully.

If the method throws an exception covered by the rollback policy, the transaction may roll back, and changes in the persistence context along with uncommitted SQL will not be confirmed.

## 3. Flush is not commit

Consider a transaction with the following steps:

```java
@Transactional
public void updateCustomer(Long id) {
    Customer customer = repository.findById(id).orElseThrow();

    customer.rename("An Nguyen");

    entityManager.flush();

    // The SQL UPDATE has been sent to the database.
    // The transaction is still open.

    customer.rename("An Tran");

    // The second change is still being tracked.
    // Another UPDATE can be issued at the next flush.
}
```

After the first flush, the database has received the SQL UPDATE for the name "An Nguyen", but the transaction has not committed. When renaming again to "An Tran", the persistence context records the new state. At commit time, the provider can flush the remaining change and then commit the transaction.

If an error occurs after the first flush and the transaction rolls back, even the UPDATE already sent within the transaction is rolled back by the database's transaction mechanism. The fact that SQL has executed does not mean the data is confirmed.

Flush is often used to force SQL errors to surface early at a specific point in the flow, such as checking a unique constraint or optimistic locking before proceeding to another business step. However, deferred constraint errors or errors only detected by the database at commit time can still appear later.

## 4. Commit usually flushes automatically before confirming the transaction

When a JPA transaction is committed, the provider must synchronize the necessary persistence context changes before the transaction completes. Therefore, in normal flows, the application does not need to call entityManager.flush() right before every commit.

Example:

```java
@Transactional
public void createCustomer() {
    Customer customer = new Customer("An");
    repository.save(customer);

    // No need to call flush() just to ensure the transaction
    // is written when the method finishes normally.
}
```

When the method returns normally, the Spring transaction manager handles commit. During that process, the JPA provider flushes pending changes and then the database commits the transaction.

General sequence:

1. The service method runs within a transaction.
2. An entity is persisted or modified in the persistence context.
3. The method returns normally.
4. The transaction manager requests commit.
5. The JPA provider flushes necessary changes.
6. The database completes the commit.
7. The transaction ends; transaction resources are released as managed by Spring/provider.

Commit can fail even if SQL statements succeeded during an earlier flush. For example, the database might encounter a deferred constraint, serialization failure, deadlock, or connection loss during commit. The application must handle errors at the transaction boundary, not merely rely on an earlier flush succeeding.

## 5. Is flushed SQL visible to other transactions?

Normally, uncommitted data is not visible to other transactions under READ COMMITTED isolation. However, other transactions may be blocked by locks or behave depending on the isolation level and database.

Within the same transaction, subsequent queries can see that transaction's own flushed changes. This allows a business operation to write data and then query it again within the same transaction.

Example:

```java
@Transactional
public Customer createAndReadBack() {
    Customer customer = new Customer("An");
    repository.save(customer);

    entityManager.flush();

    return repository.findById(customer.getId()).orElseThrow();
}
```

After flush, the query running in the same transaction can read the newly inserted record. Another transaction normally will not see the record until the current transaction commits, depending on the isolation level.

Distinguish three concepts:

- **Persistence context visibility:** managed entities and in-memory state of the current transaction.
- **Database transaction visibility:** data seen by SQL statements within the current transaction.
- **Cross-transaction visibility:** data that other transactions are allowed to read according to the isolation level.

Do not use flush as a substitute for commit when data needs to be published to other transactions or external systems.

## 6. When does JPA flush automatically?

JPA defines FlushModeType with two primary modes: AUTO and COMMIT. In a typical Spring Data JPA environment, AUTO is the default mode.

### 6.1. FlushModeType.AUTO

With AUTO, the provider must ensure that changes in the persistence context that could affect a query's result are reflected when the query executes. The provider usually flushes before the relevant query, or may use another implementation mechanism to satisfy the JPA contract.

Example:

```java
@Transactional
public List<Customer> findCustomersAfterRename() {
    Customer customer = repository.findById(1L).orElseThrow();
    customer.rename("An Nguyen");

    return entityManager.createQuery("""
        select c
        from Customer c
        where c.name = :name
        """, Customer.class)
        .setParameter("name", "An Nguyen")
        .getResultList();
}
```

Because changing name can affect the query result, the provider must ensure the query returns results consistent with persistence context state under AUTO. Hibernate typically flushes before a query when the query space overlaps tables with pending changes.

Do not conclude that every SELECT always flushes the entire persistence context. Exact behavior can depend on the query, provider, and tables used by the query.

### 6.2. FlushModeType.COMMIT

COMMIT requires the provider to flush before the transaction commits. Per the JPA contract, the effect of unflushed changes in the persistence context on query results is unspecified if a query runs before commit.

```java
entityManager.setFlushMode(FlushModeType.COMMIT);
```

This mode can reduce early flushes in some flows, but care is needed if queries must immediately reflect pending changes. Hibernate also has its own FlushModes such as MANUAL; those are provider-specific APIs/behaviors, not identical to the two standard JPA modes.

Do not change flush mode just to cure an unmeasured performance problem. Inspect the SQL and identify which query is actually triggering flushes.

## 7. What does entityManager.flush() do?

Calling:

```java
entityManager.flush();
```

instructs the provider to synchronize changes of the current persistence context to the database. Depending on entity states, the SQL may include:

- INSERT for newly persisted entities.
- UPDATE for modified managed entities.
- DELETE for removed entities.
- SQL statements related to associations, collections, or join tables.

Flush applies to the persistence context managed by the EntityManager, not just one entity the caller happens to care about. If multiple pending entities exist in the same persistence context, the provider can synchronize all necessary changes.

Flush does NOT:

- Commit the transaction.
- Roll back the transaction.
- Clear the persistence context.
- Detach entities.
- Necessarily close the EntityManager.
- Guarantee that other transactions see uncommitted data.
- Guarantee that all deferred constraints have been checked.

Calling flush without an appropriate active transaction typically results in a TransactionRequiredException. With a Spring-managed EntityManager, let the transaction manager control the transaction lifecycle; do not manually call commit() on an EntityManager injected via @PersistenceContext.

## 8. save(), saveAndFlush(), and flush() in Spring Data JPA

These three methods are frequently misunderstood:

| Method | Meaning |
|---|---|
| save(entity) | Instructs the repository to persist a new entity or merge an existing entity per Spring Data's mechanism |
| saveAndFlush(entity) | Saves the entity and then requests a flush of the persistence context |
| flush() | Requests a flush of pending changes in the persistence context |

Example:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void saveCustomer() {
        Customer customer = new Customer("An");

        Customer saved = repository.save(customer);

        // Save has been requested; SQL may still not have run yet.
        repository.flush();

        // Changes after flush still belong to the current transaction.
        saved.rename("An Nguyen");
    }
}
```

Repository save() does not mean the database has committed. For new entities, Spring Data typically uses persist; for entities considered existing, it may use merge. merge returns a managed instance; callers should use the returned instance because the passed-in object may remain detached.

saveAndFlush():

```java
@Transactional
public Customer saveImmediately() {
    Customer customer = new Customer("An");
    return repository.saveAndFlush(customer);
}
```

saveAndFlush() performs save and then flush. It does not by itself commit an enclosing transaction. If the service method is running inside `@Transactional`, the transaction remains open after saveAndFlush returns and can roll back later.

If you call an independent repository method without an enclosing transaction, the repository method's default transaction may end when the method returns. In that case, commit occurs at the transaction boundary managed by Spring Data/Spring. That is why you must distinguish the effect of flush from the actual transaction boundary.

## 9. Flush helps detect errors early

Some errors only appear when SQL is sent to the database:

- Unique constraint violations.
- Foreign key or NOT NULL violations.
- Values exceeding column length.
- Incompatible data types.
- Optimistic locking conflicts due to mismatched versions.
- Other SQL or constraint errors from the database.

Example checking duplicate customer codes:

```java
@Transactional
public void registerCustomer(String name, String email) {
    Customer customer = new Customer(name, email);

    repository.save(customer);
    entityManager.flush();

    // If the unique constraint is checked on INSERT,
    // the error can surface right at flush().
    sendRegistrationNotification(customer);
}
```

This example requires considering business boundaries: sending a notification before transaction commit could notify of success even though the transaction later rolls back. In real systems, publish events after commit or use a transactional outbox if consistency between the database and message delivery is required.

Early flush lets persistence errors surface before performing additional work. However, it does not immediately make the transaction succeed. If flush throws an error, the transaction usually needs to roll back. Do not catch the exception and continue writing inside a transaction already marked rollback-only or a database transaction in an aborted state.

## 10. Optimistic locking can fail at flush or commit

For an entity with @Version:

```java
@Entity
@Table(name = "products")
public class Product {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;

    protected Product() {
    }
}
```

The provider uses version in the UPDATE statement to detect whether another transaction modified the record:

```sql
UPDATE products
SET name = ?, version = ?
WHERE id = ? AND version = ?;
```

If no row is updated because the version has changed, the provider detects an optimistic locking conflict. The error typically surfaces when flush executes the UPDATE, or can be reported at commit depending on when the provider synchronizes changes.

Do not assume a setter or save() will detect conflicts immediately. If business logic needs to catch the error before performing a subsequent step, you can flush intentionally, while still handling transaction rollback.

## 11. Flush and batching when writing multiple entities

Flushing too frequently can defeat batching benefits. For example, a loop calling saveAndFlush for each record forces continuous synchronization:

```java
// Unsuitable for large batches if flushing on every iteration.
for (Customer customer : customers) {
    repository.saveAndFlush(customer);
}
```

The common pattern is to write in batches, then flush and clear the persistence context:

```java
@Transactional
public void importCustomers(List<Customer> customers) {
    int batchSize = 50;

    for (int i = 0; i < customers.size(); i++) {
        entityManager.persist(customers.get(i));

        if ((i + 1) % batchSize == 0) {
            entityManager.flush();
            entityManager.clear();
        }
    }

    entityManager.flush();
    entityManager.clear();
}
```

flush sends the current batch's changes to the database. clear detaches all entities from the persistence context to reduce memory usage when processing large datasets. After clear, old objects are no longer managed; if further modifications are needed, re-read or merge appropriately.

Batch size 50 is just an example. Tune it according to Hibernate jdbc.batch_size, the JDBC driver, the database, and entity graph size. If using IDENTITY, Hibernate generally cannot batch entity inserts via standard JDBC batching. Sequences can be more favorable since IDs can be allocated before insert.

Do not clear before flushing if you want to keep pending changes: clear detaches entities and can cause unsynchronized changes to be lost from the persistence context.

## 12. Flush, bulk updates, and the persistence context

JPQL bulk update/delete operates directly on the database and bypasses per-entity dirty checking. Therefore, previously loaded entities may still retain old values in the persistence context.

Example:

```java
@Transactional
public void deactivateAllCustomers() {
    Customer customer = entityManager.find(Customer.class, 1L);

    entityManager.createQuery("""
        update Customer c
        set c.active = false
        where c.active = true
        """).executeUpdate();

    // customer may still hold active=true in memory.
}
```

You can use flush and clear to synchronize pending changes before the bulk query and remove managed entities from the persistence context afterward:

```java
@Transactional
public void deactivateAllCustomers() {
    entityManager.flush();

    entityManager.createQuery("""
        update Customer c
        set c.active = false
        where c.active = true
        """).executeUpdate();

    entityManager.clear();
}
```

Spring Data `@Modifying` provides `flushAutomatically` and `clearAutomatically` attributes to control flush/clear around bulk queries. Only enable `clearAutomatically` when you understand that currently managed entities will be detached; callers cannot continue relying on the old managed state.

## 13. Rollback after flush

A transaction can flush successfully and still roll back:

```java
@Transactional
public void createThenReject() {
    Customer customer = new Customer("An");
    repository.save(customer);

    entityManager.flush();

    throw new IllegalStateException("Business rule rejected");
}
```

If the exception triggers rollback according to Spring's policy, the database rolls back the transaction. The INSERT that was flushed but not committed will not become confirmed data.

However, some ID generators such as sequences or identity columns may have already consumed a value before rollback. Rolling back a transaction does not necessarily revert the sequence/counter to its previous value. Thus, technical IDs can have gaps; do not use auto-generated IDs as document numbers that must be strictly contiguous.

If an exception is caught inside the method and not rethrown, the transaction might still commit if it has not been marked rollback-only. However, SQL errors during flush typically leave the transaction unsafe to continue. Roll back when a persistence operation fails, and handle recovery in a new transaction if needed.

## 14. Transaction boundaries in Spring

With @Transactional, the Spring transaction interceptor begins or joins a transaction before invoking the method, then commits/rolls back when the method finishes according to propagation and rollback rules.

```java
@Service
public class OrderService {

    @Transactional
    public void confirmOrder(Long id) {
        // Load entity.
        // Modify state.
        // Optionally flush when early error detection is needed.
    }
}
```

Do not call entityManager.getTransaction().commit() on an EntityManager managed by Spring via @PersistenceContext. For Spring-managed transactions, use @Transactional or TransactionTemplate. Calling commit manually can cause errors or break Spring's transaction management.

A transactional method called through a Spring proxy has a transaction boundary. Calling another method in the same class via this.method() usually does not go through the proxy, so the annotation on the internally called method may not take effect as expected.

Propagation also affects transaction boundaries. REQUIRED typically joins the current transaction or creates a new one if none exists. REQUIRES_NEW suspends the outer transaction and creates a separate transaction; the new transaction can commit independently even if the outer transaction rolls back. A flush in the outer transaction still does not commit it.

## 15. Testing flush and commit

In persistence tests, save() may not have sent SQL yet. If you want to verify constraints or SQL mapping right in the test, call flush:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void persistsCustomer() {
        Customer customer = new Customer("An");

        repository.save(customer);
        repository.flush();

        assertThat(customer.getId()).isNotNull();
    }
}
```

This test confirms that the flush operation succeeds inside the test transaction. However, many Spring Boot tests run in a transaction that rolls back at the end. Therefore, it does not prove that the transaction committed successfully.

To test commit behavior, you must create a real transaction boundary, such as using TransactionTemplate or an integration test that does not automatically roll back, and verify the data from a new transaction after the first transaction commits.

When testing constraint errors, flush often makes the error appear on an easier-to-pinpoint test line. Still, for deferred constraints or errors that only arise at commit, testing an actual commit remains necessary.

## 16. Quick comparison table

| Criterion | Flush | Commit |
|---|---|---|
| Purpose | Synchronizes persistence context to the database | Ends the transaction and confirms changes |
| Sends SQL | Can send INSERT/UPDATE/DELETE | Usually flushes pending changes before committing |
| Ends transaction | No | Yes |
| Can roll back afterward | Yes | Once committed, a transaction cannot be rolled back |
| Persistence context | Remains active, entities remain managed | Transaction ends; entities do not automatically become detached solely because of commit, though the transaction management scope ends |
| Visible to other transactions | Normally no, depending on isolation | Can become visible according to isolation/commit visibility |
| Constraint error detection | Many errors surface at flush | Some errors still only surface at commit |

## 17. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| Called save() but SQL has not run | Changes are sitting in the persistence context | Flush when early sync is needed; transaction commit flushes pending changes |
| Thinking saveAndFlush() committed | Confusing flush with commit | Check service/repository transaction boundaries |
| Other transactions do not see data yet | SQL was flushed but transaction has not committed | Commit the transaction and check isolation level |
| Unique error appears at end of method | Constraint is only checked at flush/commit | Flush at the point where early detection is needed; still handle commit errors |
| Test passes but production commit fails | Test only flushed and rolled back, not checking commit | Add integration tests with real commits |
| Calling flush outside a transaction fails | No active appropriate transaction | Run inside @Transactional or an appropriate transaction manager |
| Catching flush error and continuing writes | Transaction may be rollback-only or DB transaction aborted | Roll back and handle in a new transaction |
| Slow batch inserts | Flushing too often or IDENTITY limits batching | Flush in batches, measure JDBC batching, and consider sequences |
| Stale entities after bulk update | Bulk query bypasses managed entity state | Flush before, clear/refresh after as needed |

## 18. Practice exercises

1. Create a new Customer with repository.save() and observe when the SQL INSERT is sent.
2. Call entityManager.flush() mid-transaction, then verify the transaction is still active.
3. After flush, modify another property and verify the subsequent flush/commit writes the new change.
4. Add a unique constraint and try inserting a duplicate; compare error timing without flush vs. with explicit flush.
5. Flush successfully and then throw a RuntimeException; verify the transaction rolls back and no record is committed.
6. Run two transactions to observe that the second transaction does not see uncommitted data under READ COMMITTED.
7. Use FlushModeType.COMMIT and compare query behavior with AUTO on your provider.
8. Compare save(), saveAndFlush(), and flush() in a service annotated with @Transactional.
9. Import many entities in batches using flush/clear and observe memory and SQL batch counts.
10. Write a test with an actual commit to distinguish flush errors from commit errors.

**Overarching principle:** flush sends pending persistence context changes to the database within the current transaction; commit confirms the transaction. After flush, the transaction can still roll back and other transactions normally do not see the data yet. Use flush when you need early synchronization or persistence error detection at a specific point; let the Spring transaction manager control commit/rollback at `@Transactional` boundaries.