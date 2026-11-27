# Replacing Dirty Checking, Flush, and EntityManager with Explicit Writes

When migrating an application from JPA/Hibernate to **Spring Data Relational JDBC**, the most significant change lies in how the application manages entity state. In JPA, an entity loaded into a persistence context can become a managed entity. Hibernate tracks object mutations, performs dirty checking, and synchronizes those changes to the database on flush. In Spring Data JDBC, there is no such persistence context: entities are ordinary Java objects, and in-memory changes are persisted only when the application explicitly invokes a write operation.

Accordingly, migrated code must replace the following assumptions:

- Replace dirty checking with explicit calls to `repository.save(...)`, `JdbcAggregateTemplate.update(...)`, or dedicated update statements.
- Replace `EntityManager.flush()` with write operations executed immediately within the transaction; the transaction still commits only upon completion.
- Replace `EntityManager` with repositories, `JdbcAggregateTemplate`, `JdbcTemplate`, or `NamedParameterJdbcTemplate` depending on the goal.
- Replace reliance on managed entities and an identity map by explicitly passing the aggregate to save and re-querying when fresh state is needed.

This lesson explains the lifecycle differences, how to translate each JPA operation, how to structure transactions and partial updates, and what to watch out for when aggregates have children, generated IDs, or optimistic locking.

## 1. Two Different Persistence Models

### 1.1. JPA: Persistence Context Tracks Entities

In JPA, an `EntityManager` manages a persistence context. When calling `find`, the entity is loaded into the context and typically becomes a managed entity. If you modify entity attributes, Hibernate can detect the change without needing a `save` call:

~~~java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName(newName);
    // Hibernate detects changes on flush.
}
~~~

Dirty checking compares current state against the snapshot managed by the persistence provider. On flush, Hibernate generates the necessary INSERT/UPDATE/DELETE statements to synchronize the persistence context with the database.

### 1.2. Spring Data JDBC: Explicit Write Operations

Spring Data JDBC does not maintain a persistence context containing managed entities. Repositories return objects materialized from the database. Mutating those objects does not automatically generate SQL:

~~~java
@Transactional
public void renameCustomer(Long id, String newName) {
    Customer customer = customers.findById(id)
            .orElseThrow();

    customer.setName(newName);
    // No SQL UPDATE yet just because the setter was called.

    customers.save(customer);
    // The write operation is performed explicitly.
}
~~~

This is a shift in responsibility: the service or application use case decides when to write the aggregate. You cannot port JPA code with setters verbatim and expect dirty checking to persist it automatically.

### 1.3. Quick Comparison

| JPA/Hibernate | Spring Data JDBC |
| --- | --- |
| `EntityManager` manages persistence context | Repository/template executes operations directly |
| Managed entities are tracked | Entities are plain objects |
| Dirty checking detects changes | Invoke write operations explicitly |
| `flush()` synchronizes persistence context | SQL executes when the write operation runs |
| `clear()` detaches all entities in context | No persistence context to clear |
| `refresh()` reloads managed entity state | Re-query to obtain a fresh snapshot |
| `persist()`/`merge()` per JPA lifecycle | `save()` or `JdbcAggregateTemplate.insert/update` |
| Lazy loading/proxies per JPA mapping | Aggregates load per Spring Data JDBC model, without relying on lazy proxies |
| Cascades per JPA mapping | Persistence follows aggregate boundaries and Spring Data Relational mapping |

Do not treat `repository.save` as a direct rename of `EntityManager.merge`. Both models have different semantics, especially with aggregates and child collections.

## 2. Replacing Dirty Checking with Explicit Save

Suppose legacy JPA code looks like:

~~~java
@Transactional
public void changeAddress(Long customerId, Address newAddress) {
    Customer customer = entityManager.find(Customer.class, customerId);
    customer.setAddress(newAddress);
    // No merge/save call.
}
~~~

In Spring Data JDBC, write:

~~~java
@Transactional
public void changeAddress(Long customerId, Address newAddress) {
    Customer customer = customers.findById(customerId)
            .orElseThrow(() -> new CustomerNotFoundException(customerId));

    customer.setAddress(newAddress);
    customers.save(customer);
}
~~~

The `save` call is the explicit boundary where the application asks the persistence layer to store the aggregate. If the entity is immutable, the service produces a new version:

~~~java
@Transactional
public void changeAddress(Long customerId, Address newAddress) {
    Customer current = customers.findById(customerId)
            .orElseThrow(() -> new CustomerNotFoundException(customerId));

    Customer changed = current.withAddress(newAddress);
    customers.save(changed);
}
~~~

In both cases, use the object returned from `save` whenever persistence can assign a new ID or version. For immutable objects, the repository can return an instance carrying generated or updated values.

### 2.1. Do Not Call save After Every Setter

Spring Data JDBC does not require calling `save` immediately after each setter. Finish all mutations for a use case and save the aggregate once:

~~~java
@Transactional
public void confirmOrder(Long id) {
    PurchaseOrder order = orders.findById(id).orElseThrow();

    order.confirm();
    order.recordConfirmationTime(clock.instant());
    order.addDomainNote("Confirmed by customer");

    orders.save(order);
}
~~~

In-memory mutations accumulate into the final aggregate state before the persistence operation executes. This is structuring use-case logic, not dirty checking.

### 2.2. Avoid Forgetting to Save

A common migration bug is keeping entity-mutating code while dropping the write operation:

~~~java
@Transactional
public void deactivateCustomer(Long id) {
    Customer customer = customers.findById(id).orElseThrow();
    customer.deactivate();
    // Missing customers.save(customer).
}
~~~

The method completes without error, yet the database does not change. Tests must re-read from the repository after the transaction ends or verify SQL execution to catch this bug.

## 3. Replacing persist and merge with repository.save

JPA distinguishes `persist` for new entities from `merge` for state synchronization. Spring Data JDBC generally exposes a single `save` API for both new and existing entities:

~~~java
PurchaseOrder saved = orders.save(order);
~~~

Spring Data JDBC chooses insert vs. update based on its new-entity detection mechanism (newness strategy). This can rely on ID, `@Version`, or `Persistable.isNew()` depending on the entity and configuration.

### 3.1. Entities with Database-Generated IDs

With auto-generated, unassigned IDs, a new entity typically has a null ID:

~~~java
PurchaseOrder order = new PurchaseOrder(
        null,
        "PO-1001",
        OrderStatus.NEW
);

PurchaseOrder saved = orders.save(order);
Long generatedId = saved.getId();
~~~

Do not continue reading `order.getId()` if the original object is immutable or the repository returns a new instance. Use `saved` as the persisted state.

### 3.2. Entities with Application-Assigned IDs

If IDs are always assigned before saving, the default ID-based strategy may not distinguish new entities from existing ones. You can implement `Persistable<ID>` to provide `isNew()`, or use `@Version` where appropriate.

Skeleton example:

~~~java
@Table("external_customer")
public class ExternalCustomer implements Persistable<String> {

    @Id
    private String id;

    @Transient
    private boolean newEntity = true;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markNotNew() {
        this.newEntity = false;
    }
}
~~~

This example requires completing the lifecycle of the `newEntity` flag according to how the entity is constructed and reloaded; never let an already persisted entity keep reporting `isNew() == true`. A common pattern is post-load/post-insert callbacks or dedicated factories ensuring accurate state.

### 3.3. When You Want Insert-Only or Update-Only

If a use case needs explicit semantics, `JdbcAggregateTemplate` offers dedicated operations:

~~~java
template.insert(newOrder);
template.update(existingOrder);
~~~

`insert` fits aggregates guaranteed to be new; `update` fits aggregates guaranteed to already exist. Using the exact operation catches invalid state earlier than a `save` that has to guess.

Repository `save` remains the standard choice when the application wants Spring Data JDBC to decide insert vs. update via its newness strategy.

## 4. Replacing EntityManager with Repositories and Templates

Not every JPA operation should turn into `repository.save`. Choose the abstraction by intent.

| Legacy JPA Operation | Spring Data JDBC Equivalent |
| --- | --- |
| `entityManager.find(Type.class, id)` | `repository.findById(id)` |
| `entityManager.persist(entity)` | `repository.save(entity)` or `JdbcAggregateTemplate.insert(entity)` |
| `entityManager.merge(entity)` | `repository.save(entity)` or `JdbcAggregateTemplate.update(entity)` when entity is known to exist |
| `entityManager.remove(entity)` | `repository.delete(entity)` or `deleteById(id)` |
| `entityManager.flush()` | Execute write operation; transaction commits at transaction boundary |
| `entityManager.clear()` | No equivalent needed; no persistence context |
| `entityManager.refresh(entity)` | Re-query entity/aggregate for fresh snapshot |
| JPQL bulk update | `@Modifying @Query`, `JdbcTemplate`, or `NamedParameterJdbcTemplate` |
| `EntityManager.createNativeQuery(...)` | Repository `@Query` or JDBC template |

### 4.1. Repositories for Aggregate Operations

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
~~~

Service:

~~~java
@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository orders;

    public PurchaseOrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public PurchaseOrder addLine(Long orderId, OrderLine line) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow();

        order.addLine(line);
        return orders.save(order);
    }
}
~~~

### 4.2. JdbcAggregateTemplate for Explicit Persistence

`JdbcAggregateTemplate` is Spring Data JDBC's aggregate-level abstraction. Use it when you need insert/update/delete/find without declaring a separate repository interface:

~~~java
@Service
public class PurchaseOrderWriter {

    private final JdbcAggregateTemplate template;

    public PurchaseOrderWriter(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Transactional
    public PurchaseOrder create(PurchaseOrder order) {
        return template.insert(order);
    }

    @Transactional
    public PurchaseOrder revise(PurchaseOrder order) {
        return template.update(order);
    }
}
~~~

Pick repositories when you want domain repository APIs and query methods. Pick templates when you need direct control over aggregate operations inside a service or custom persistence component.

### 4.3. JdbcTemplate for Direct SQL Operations

When updating a single column or running bulk statements, `JdbcTemplate` or `NamedParameterJdbcTemplate` is often better suited than loading and saving an entire aggregate:

~~~java
int changed = jdbcTemplate.update(
        "UPDATE customer SET status = ? WHERE id = ?",
        "INACTIVE",
        customerId
);
~~~

With named parameters:

~~~java
int changed = namedParameterJdbcTemplate.update(
        """
        UPDATE customer
        SET status = :status
        WHERE id = :id
        """,
        Map.of("status", "INACTIVE", "id", customerId)
);
~~~

Direct operations should sit inside a persistence adapter or repository fragment so services still call a meaningful business API.

## 5. Replacing Flush with Write Operations and Transactions

### 5.1. What Does Flush Do in JPA?

In JPA, `flush()` instructs the persistence provider to synchronize persistence context changes to the database. It is not synonymous with commit. The transaction can keep running and later roll back.

Example:

~~~java
entityManager.persist(order);
entityManager.flush(); // SQL is sent to the database
// The transaction is not necessarily committed yet.
~~~

### 5.2. Spring Data JDBC Has No Persistence Context to Flush

In Spring Data JDBC, a write call such as:

~~~java
orders.save(order);
~~~

executes the corresponding SQL during the persistence call itself. No separate `flush()` command is needed to synchronize dirty entities.

However, when the call runs inside an open transaction, SQL execution does not mean the data is committed. The transaction manager still decides commit or rollback at the end of the transaction.

~~~text
BEGIN TRANSACTION
    |
    +-- repository.save(order)
    |       |
    |       +-- INSERT/UPDATE/DELETE executed
    |
    +-- other JDBC operations
    |
COMMIT or ROLLBACK
~~~

If there is no outer transaction, the repository operation may run in a repository-managed transaction and commit when the method returns, depending on transaction configuration.

### 5.3. Adjusting Order When Code Relied on Flush

Some JPA code calls `flush()` mid-use-case to force constraint checks early or let subsequent queries observe synchronized SQL.

In Spring Data JDBC:

- Call `save` at the point where SQL needs to execute.
- If you need to read back newly written data within the same transaction, issue the query after the write operation; that transaction sees its own writes per isolation/database semantics.
- To check constraints, let the database execute the write and handle the resulting exception appropriately.
- If constraints are deferred until commit by the database, `save` may not catch the error immediately; commit can still fail.

Do not add `save` calls merely to mimic `flush` when no aggregate changes need saving. Identify why legacy code flushed and replace it with the appropriate operation.

### 5.4. No saveAndFlush

Spring Data JDBC does not use a `saveAndFlush` pattern like some Spring Data JPA repositories. `save` already executes the write operation. Commit boundaries remain governed by the transaction.

## 6. Replacing clear and refresh

### 6.1. No Persistence Context to Clear

JPA has `EntityManager.clear()` to detach all managed entities. Spring Data JDBC does not track managed entities, so there is no corresponding state to clear.

Every repository read performs a database read and materializes objects. If the same ID is read twice, there is no guarantee both calls return the same Java object reference.

### 6.2. Re-Reading When Fresh State Is Needed

If fresh state from the database is needed:

~~~java
Customer reloaded = customers.findById(customerId)
        .orElseThrow();
~~~

Within the same transaction, queries still respect the database isolation level. Re-reading does not guarantee seeing commits from other transactions if isolation forbids it.

### 6.3. Avoid Retaining Stale Objects After Bulk Updates

If `@Modifying` or `JdbcTemplate.update` performs a direct update, objects loaded earlier do not automatically update. Discard stale snapshots and re-query when fresh data is needed.

This differs significantly from JPA, where bulk JPQL updates can leave managed entities in the persistence context stale, requiring clear/refresh. In Spring Data JDBC, there is no identity map keeping loaded objects synchronized.

## 7. Full Aggregate Write or Partial Update?

This is a critical design decision when leaving JPA.

### 7.1. save Persists Aggregate State

Spring Data JDBC operates by aggregate boundary. Calling `save` on an aggregate root handles the root and its referenced entities per mapping. For aggregates with child collections, saving may delete existing child rows and re-insert the new collection state, rather than diffing each child to update only changed rows like ORM dirty checking.

Exact SQL details depend on mappings, entity types, and the Spring Data Relational version. Do not assume `save` only emits a single `UPDATE` for the root or updates only modified children. Design sensibly sized aggregates and inspect SQL in integration tests when performance matters.

### 7.2. When Is Saving the Whole Aggregate Appropriate?

`save` fits well when:

- The use case modifies aggregate root state.
- The aggregate is small and fully loaded.
- Children belong to the same consistency boundary.
- The entire aggregate is the unit of change and persistence.

Example:

~~~java
@Transactional
public void changeOrderStatus(Long id, OrderStatus status) {
    PurchaseOrder order = orders.findById(id).orElseThrow();
    order.changeStatus(status);
    orders.save(order);
}
~~~

### 7.3. When Is a Partial Update Needed?

If a table has millions of rows or a use case only increments a counter, loading and saving the entire aggregate is unnecessary. Use a targeted update statement:

~~~java
public interface InventoryRepository
        extends CrudRepository<Inventory, Long> {

    @Modifying
    @Query("""
        UPDATE inventory
        SET reserved_quantity = reserved_quantity + :amount
        WHERE product_id = :productId
        """)
    int reserve(
            @Param("productId") Long productId,
            @Param("amount") int amount
    );
}
~~~

Annotation names and imports depend on your Spring Data JDBC version; in repository queries, `@Modifying` marks statements that mutate data. Check the affected row count to verify whether the update matched a record.

For complex predicates or bulk updates, use `NamedParameterJdbcTemplate` inside a custom repository adapter.

### 7.4. Do Not Mix Both Write Styles Uncontrolled

If one use case both loads an aggregate and runs direct SQL against the same table, the in-memory object may no longer reflect database state. Follow these rules:

1. Establish one authoritative data source per use case.
2. Avoid saving a stale aggregate after executing a bulk update.
3. Re-query if you need to read updated state.
4. Share the same transaction if operations must succeed or fail together.

## 8. Mutating Aggregates and Child Entities

In JPA, code can mutate a managed child and rely on dirty checking to detect it. In Spring Data JDBC, children are part of the aggregate persisted through the root:

~~~java
@Transactional
public void changeLineQuantity(
        Long orderId,
        Long lineId,
        int quantity
) {
    PurchaseOrder order = orders.findById(orderId).orElseThrow();

    order.changeLineQuantity(lineId, quantity);
    orders.save(order);
}
~~~

The aggregate root enforces invariants and mutates children. The repository persists aggregate state per mapping.

### 8.1. Do Not Update Children Outside Aggregate Boundaries Arbitrarily

If a child table is mutated independently by multiple use cases or has its own lifecycle, revisit the aggregate boundary. Spring Data JDBC assumes referenced entities belong to the aggregate root and are persisted through the root.

If performance requires updating a single child row directly, create a controlled, explicit persistence operation and define how it interacts with root invariants. Avoid competing write paths that leave aggregates inconsistent.

### 8.2. Collection Changes Can Emit Multiple SQL Statements

Adding one element to a collection does not mean Spring Data JDBC executes only a single row `INSERT` if the aggregate is saved using collection replacement. Evaluate costs for large aggregates:

- Number of child rows deleted/inserted.
- Foreign keys and indexes.
- Database triggers or auditing.
- Locks and transaction duration.
- Total SQL statements per save.

If a collection is very large or has an independent lifecycle, consider splitting the aggregate or using a dedicated repository/SQL for that operation.

## 9. Transaction Boundaries Replacing EntityManager Lifecycle

Transactions remain vital in Spring Data JDBC. The difference is that transactions protect executed SQL statements rather than wrapping a persistence context waiting to flush.

### 9.1. Place Transactions at the Application Service

~~~java
@Service
public class OrderApplicationService {

    private final PurchaseOrderRepository orders;
    private final PaymentRepository payments;

    public OrderApplicationService(
            PurchaseOrderRepository orders,
            PaymentRepository payments
    ) {
        this.orders = orders;
        this.payments = payments;
    }

    @Transactional
    public void confirm(Long orderId) {
        PurchaseOrder order = orders.findById(orderId).orElseThrow();
        order.confirm();

        payments.recordConfirmation(orderId);
        orders.save(order);
    }
}
~~~

If both repositories share the same datasource and transaction manager, database operations participate in the same transaction. If one fails with a rollback-triggering exception, database changes within that transaction roll back.

### 9.2. SQL Executes Immediately, Yet Commit Happens at the End

Inside a transaction, SQL is sent to the database when `save` is called. Other transactions normally cannot see uncommitted changes; the current transaction can read its own writes.

Do not confuse SQL execution with durable persistence. Commit is the point where the transaction completes successfully.

### 9.3. Read-Only Transactions

Read-only use cases can use:

~~~java
@Transactional(readOnly = true)
public PurchaseOrder getOrder(Long id) {
    return orders.findById(id).orElseThrow();
}
~~~

Do not place write operations inside a transaction marked read-only expecting standard write behavior. Match transaction configuration to the work performed.

### 9.4. Self-Invocation and Proxies

Spring's `@Transactional` is typically applied via proxies. Calling another transactional method on the same instance (`this.someMethod()`) may bypass the proxy, causing the transaction annotation on the target method not to apply as expected.

When migrating services, place transaction boundaries on public application service methods invoked from outside the bean, or extract transactional collaborators into separate beans.

## 10. Optimistic Locking Instead of Managed State Tracking

Dirty checking does not by itself resolve concurrent write conflicts. Spring Data JDBC supports optimistic locking with `@Version`:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private OrderStatus status;
}
~~~

When saving a versioned aggregate, Spring Data JDBC uses the version to detect whether the row was modified by another transaction. If the version no longer matches, the operation can throw `OptimisticLockingFailureException`.

### 10.1. Handling Conflicts

~~~java
@Transactional
public void confirm(Long orderId) {
    PurchaseOrder order = orders.findById(orderId).orElseThrow();
    order.confirm();

    try {
        orders.save(order);
    } catch (OptimisticLockingFailureException ex) {
        throw new OrderWasModifiedConcurrentlyException(orderId, ex);
    }
}
~~~

Depending on business rules, the application can return a conflict to the caller, reload the aggregate and retry with a bounded limit, or ask the user to resolve it. Never retry indefinitely, as the operation may no longer be valid against the new state.

### 10.2. Partial Updates Need Version Predicates

A custom `@Modifying` or `JdbcTemplate.update` statement does not automatically inherit the optimistic locking semantics of aggregate repository saves. When updating a versioned table directly, include the version check and increment in the SQL:

~~~sql
UPDATE purchase_order
SET status = :status,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

If zero rows are affected, either the row does not exist or the version changed. Distinguish the two cases with an additional query if business logic requires it.

## 11. Auditing and Entity Callbacks

JPA applications may rely on lifecycle callbacks such as `@PrePersist`, `@PreUpdate`, or listeners to populate audit fields. When migrating to Spring Data JDBC, move that logic to Spring Data Relational's mechanisms:

- Auditing annotations such as `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, and `@LastModifiedBy`.
- `AuditingEntityCallback` and auditing infrastructure.
- `BeforeConvertCallback`, `BeforeSaveCallback`, `AfterSaveCallback`, or version-appropriate callbacks.
- Business logic invoked explicitly in application services or domain objects.

Entity example:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @CreatedDate
    private Instant createdAt;

    @LastModifiedDate
    private Instant updatedAt;
}
~~~

Auditing must be enabled, with an `AuditorAware` provided if recording the actor. Do not assume auditing annotations work simply because they appear on fields.

Direct writes via `JdbcTemplate` bypass the repository save aggregate mapping and callback pipeline. If partial SQL needs to update audit fields, include them in the SQL or in a persistence adapter with clear ownership.

## 12. Domain Events and Side Effects

JPA code may rely on entity listeners to emit events when entities are persisted or updated. When migrating to Spring Data JDBC, distinguish:

- Aggregate business logic: invoked explicitly when performing actions.
- Aggregate events: stored or published using appropriate Spring Data Relational mechanisms.
- Post-commit side effects: use transaction-bound event listeners when they must run after transaction success.

Application service example:

~~~java
@Transactional
public PurchaseOrder confirm(Long id) {
    PurchaseOrder order = orders.findById(id).orElseThrow();
    order.confirm();

    PurchaseOrder saved = orders.save(order);
    events.publishEvent(new OrderConfirmed(saved.getId()));
    return saved;
}
~~~

If a listener must execute only after commit, register it with `@TransactionalEventListener(phase = AFTER_COMMIT)`. If an event must never be lost on process crash, write an outbox row inside the same transaction rather than relying solely on in-memory callbacks.

Never emit events or send messages before commit if a transaction rollback would render those events false.

## 13. JPA APIs Without a One-to-One Replacement

Some APIs reflect the persistence context and have no direct counterpart:

| JPA API/Concept | How to Handle in Spring Data JDBC |
| --- | --- |
| `EntityManager` | Inject repositories, `JdbcAggregateTemplate`, or JDBC templates |
| Managed entity | None; loaded objects are snapshots |
| Dirty checking | Explicitly call save/update |
| `flush()` | SQL runs during write operation; commit is managed by transaction |
| `clear()` | Unnecessary since there is no persistence context |
| `refresh()` | Re-query entity/aggregate |
| `detach()` | No managed state to detach |
| `getReference()` | Query by ID; do not rely on lazy proxies |
| Lazy collections | Design aggregates and dedicated queries for needed data |
| JPQL bulk update | `@Modifying @Query` or JDBC template |
| `merge()` graph | Save aggregate root per Spring Data JDBC mapping and semantics |
| Cascade types | Aggregate boundaries and Spring Data Relational mapping relationships |

If a piece of code relies heavily on `EntityManager` as a unit-of-work, redesign that section rather than swapping method calls for similarly named APIs.

## 14. Complete Use Case Migration Example

### 14.1. JPA Version

~~~java
@Service
public class JpaOrderService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void addLine(Long orderId, OrderLine line) {
        PurchaseOrder order =
                entityManager.find(PurchaseOrder.class, orderId);

        order.addLine(line);

        entityManager.flush();
    }
}
~~~

The code relies on a managed aggregate and flush to synchronize changes.

### 14.2. Spring Data JDBC Version

~~~java
@Service
public class JdbcOrderService {

    private final PurchaseOrderRepository orders;

    public JdbcOrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public PurchaseOrder addLine(Long orderId, OrderLine line) {
        PurchaseOrder order = orders.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.addLine(line);

        return orders.save(order);
    }
}
~~~

Differences:

1. Repository loads the aggregate.
2. Domain method mutates the aggregate in memory.
3. `save` persists the aggregate explicitly.
4. Transaction commits when the application service completes.

No separate `flush` is needed. If `save` fails, the transaction can roll back and the exception propagates to the caller.

### 14.3. Partial Update Instead of Loading the Aggregate

If the use case only updates an independent status without needing aggregate invariant checks:

~~~java
public interface CustomerRepository
        extends CrudRepository<Customer, Long> {

    @Modifying
    @Query("""
        UPDATE customer
        SET status = :status
        WHERE id = :id
        """)
    int updateStatus(
            @Param("id") Long id,
            @Param("status") String status
    );
}
~~~

Service:

~~~java
@Transactional
public void setCustomerStatus(Long id, CustomerStatus status) {
    int changed = customers.updateStatus(id, status.name());

    if (changed == 0) {
        throw new CustomerNotFoundException(id);
    }
}
~~~

This is a direct partial update. It does not load the aggregate, does not run dirty checking, and does not automatically execute the full `save` lifecycle. If versioning, auditing, or invariants must be maintained, enforce them explicitly.

## 15. Testing After Replacing Dirty Checking and Flush

Tests must prove that changes persist only when a write operation is called, while also verifying transaction boundaries.

### 15.1. In-Memory Mutations Do Not Auto-Save

1. Create and save an entity.
2. Load the entity from the repository.
3. Modify a field without calling `save`.
4. End the transaction.
5. Read again in a new transaction.
6. Verify the database still holds the original value.

This test makes it clear that Spring Data JDBC does not dirty-check entities.

### 15.2. Save Persists Changes

1. Load the aggregate.
2. Invoke mutating domain method.
3. Call repository `save`.
4. Reload the aggregate.
5. Verify root and child states are accurate.

### 15.3. SQL Executes Before Commit

Inside a transaction:

1. Call `save`.
2. Re-query within the same transaction to confirm the transaction sees its own writes.
3. Roll back the transaction.
4. Read from a new transaction to confirm the data was not committed.

This distinguishes when SQL executes from when the transaction commits.

### 15.4. Testing Optimistic Locking

1. Load the same aggregate in two transactions.
2. Transaction A updates and commits.
3. Transaction B attempts to save the stale snapshot.
4. Verify optimistic locking failure occurs.

### 15.5. Testing Partial Updates

Verify:

- Affected row count.
- `WHERE` clause does not update unintended rows.
- Version is checked and incremented where applicable.
- Audit fields are updated properly.
- Objects loaded prior to the bulk update are not reused as fresh snapshots.

## 16. Common Migration Mistakes

| Mistake | Why It Happens | Resolution |
| --- | --- | --- |
| Mutate via setter but forget `save` | No dirty checking | Call `save`/update explicitly |
| Call `save` after every field | Confusing `save` with `flush` | Group use-case changes then save the aggregate |
| Keep `EntityManager.flush()` | Persistence context no longer exists | Remove flush and place `save` where writes belong |
| Think `save` equals commit | SQL runs inside an uncommitted transaction | Use proper transaction boundaries |
| Treat `save` like `merge` | Aggregate semantics differ from JPA | Check newness and aggregate write behavior |
| Use old object after `save` | Generated ID/version may be on returned instance | Use the instance returned from `save` |
| Hold entity references as managed objects | No identity map | Pass IDs and re-query when needed |
| Assume lazy loading works | Spring Data JDBC does not rely on lazy proxies | Load aggregate or query needed data separately |
| Save large aggregate to change one field | May rewrite many child rows | Use partial update if compatible with invariants |
| Bulk update then save stale snapshot | `save` can overwrite updated state | Re-query or pick a single write path |
| Custom update ignores `@Version` | Concurrent updates go undetected | Add version predicate and increment version |
| Direct SQL skips auditing | Aggregate callback pipeline is bypassed | Update audit fields explicitly |
| Skip transaction testing | Confusing SQL execution with commit | Test both visibility and rollback |

## 17. Refactoring Procedure from JPA to Spring Data JDBC

When migrating a service:

1. **Locate every `EntityManager` usage:** `find`, `persist`, `merge`, `remove`, `flush`, `clear`, `refresh`, and native queries.
2. **Classify operations:** aggregate CRUD, read queries, partial updates, or bulk operations.
3. **Define aggregate boundaries:** which object is the root and which children save with the root.
4. **Replace read APIs:** use repositories or query adapters.
5. **Replace write APIs:** use `save`, `insert`, `update`, `delete`, or explicit SQL statements.
6. **Add missing write calls:** locate all domain mutations that previously relied on dirty checking.
7. **Remove flush/clear/refresh:** replace with explicit SQL execution and re-querying where needed.
8. **Review transactions:** place `@Transactional` at the use case and verify datasource/transaction manager.
9. **Handle concurrency:** migrate optimistic locking and partial updates properly.
10. **Migrate lifecycle logic:** auditing, callbacks, and domain events.
11. **Test:** save/no-save, root/child, generated IDs, rollbacks, version conflicts, and bulk updates.
12. **Measure actual SQL:** inspect statement counts and costs of saving large aggregates.

## Key Takeaways

Spring Data JDBC lacks JPA's persistence context and dirty checking. Loaded entities are ordinary objects; in-memory changes do not persist automatically. Call `repository.save`, `JdbcAggregateTemplate.insert/update`, or targeted update statements explicitly at use-case boundaries. `save` persists aggregates per mapping, so do not assume it only updates modified fields or a single child row.

`EntityManager.flush()` is unnecessary because SQL executes during write operations. Transactions still govern commit vs. rollback; executed SQL does not mean committed data. `clear`, `detach`, and `refresh` also have no direct equivalents: there is no managed state to clear, and when a fresh snapshot is required, simply re-query.

Use repositories or templates for aggregates, and `@Modifying @Query` or JDBC templates for partial/bulk updates where suitable. For partial updates, proactively preserve optimistic locking, auditing, and invariants because direct SQL paths bypass the full aggregate save lifecycle. Place transactions on application services, use the object returned from `save` when generated IDs or versions are involved, and test forgotten saves, rollbacks, child persistence, and concurrent updates.

## References

- [Spring Data Relational — JDBC](https://docs.spring.io/spring-data/relational/reference/jdbc.html)
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Data Relational — JDBC Aggregate Template](https://docs.spring.io/spring-data/relational/reference/jdbc/aggregate-template.html)
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html)
- [Spring Data Relational — Mapping and Optimistic Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
