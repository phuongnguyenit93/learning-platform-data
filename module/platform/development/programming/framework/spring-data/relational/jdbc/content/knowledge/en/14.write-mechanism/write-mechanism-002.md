# Aggregate Update Flow Under the Full-State Save Model

In **Spring Data Relational JDBC**, a single call to `repository.save(aggregate)` is interpreted as persisting the state of the **entire aggregate** at the moment of the call. The framework does not maintain a persistence context to track individual changed fields like JPA/Hibernate dirty checking. Applications typically load the aggregate, modify the object in memory, and pass the root back to the repository to save.

This directly impacts how services and update APIs are written:

- You must work with the full state of the aggregate root and its owned child entities.
- Omitting a property or setting it to `null` can mean removing or deleting child data.
- Child entities are persisted according to the aggregate lifecycle; when updating an existing aggregate, Spring Data JDBC may delete and re-insert child rows instead of detecting exact per-child changes.
- References to other aggregates do not participate in the root's delete/re-insert lifecycle.
- If multiple requests can update the same aggregate, consider optimistic locking to prevent overwriting newer data with a stale object.

This lesson explains the save flow for new and existing aggregates, how relationships within an aggregate are handled, how to design safe update operations, and the impacts on transactions, performance, and consistency.

## 1. The aggregate is the unit of persistence

An aggregate has an **aggregate root** as its primary entry point. For example:

```text
PurchaseOrder (aggregate root)
  ├── id
  ├── orderNumber
  ├── status
  ├── shippingAddress (embedded value)
  └── lines (owned child collection)
        ├── OrderLine
        ├── OrderLine
        └── OrderLine

Customer (another aggregate)
  └── referenced by customerId
```

`PurchaseOrder` owns the `OrderLine` instances because order lines only have meaning within the scope of an order and are added, modified, and removed through the order. `Customer` is a separate aggregate: it has an independent lifecycle and can be referenced by many orders.

The core rule of Spring Data JDBC is that saving goes through the root. Calling `save` on the root persists the state of the aggregate root along with its mapped owned child entities. It does not automatically load and persist an entire arbitrary object graph simply because a Java class has a field referencing another object.

## 2. Spring Data JDBC does not use dirty checking

In JPA, an entity managed inside a persistence context can have its changes tracked; when the transaction completes, the ORM can emit `UPDATE` statements only for modified properties. Spring Data JDBC follows a different model:

| Aspect | Spring Data JDBC | Typical JPA/Hibernate |
| --- | --- | --- |
| Persistence context managing entities | Does not maintain a JPA-style persistence context | Has a persistence context |
| Per-property change tracking | No automatic dirty checking | Can track changes on managed entities |
| How the application writes | Calls repository to save aggregate state | Modifies managed entity and flushes/commits or calls persist/merge |
| Child entity lifecycle | Follows the aggregate root and relational mapping | Follows configured JPA cascade/orphan removal and mappings |
| Loading data | Repository returns materialized objects; no default JPA-style lazy-loading proxy graph | Can be lazy/eager depending on mapping and persistence context |

Therefore, do not apply the mindset of "changing one field means the framework only updates one field" to `save` in Spring Data JDBC. For an existing aggregate, the root is updated and the entities referenced inside the aggregate are synchronized according to Spring Data JDBC's persistence model.

### 2.1. Example of an aggregate

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String orderNumber;
    private String status;

    @MappedCollection(idColumn = "purchase_order_id")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String orderNumber) {
        this.orderNumber = orderNumber;
        this.status = "DRAFT";
    }

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getStatus() {
        return status;
    }

    public List<OrderLine> getLines() {
        return List.copyOf(lines);
    }

    public void confirm() {
        if (lines.isEmpty()) {
            throw new IllegalStateException("An order needs at least one line");
        }
        this.status = "CONFIRMED";
    }

    public void addLine(String sku, int quantity, BigDecimal unitPrice) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        lines.add(new OrderLine(sku, quantity, unitPrice));
    }

    public void removeLine(String sku) {
        lines.removeIf(line -> line.sku().equals(sku));
    }
}

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice
) {}
```

The example uses `List` as the owned child collection. In real applications, add appropriate constructors/factories, validation, and domain rules for updating prices/quantities. `getLines()` returns an unmodifiable copy to prevent external code from mutating the collection while bypassing business methods.

A repository only needs to be declared for the root:

```java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}
```

A separate repository for `OrderLine` is not needed if it is merely a child owned by the `PurchaseOrder` aggregate.

## 3. Flow for saving a new aggregate

For a new aggregate, the framework identifies the entity as new using its new-state detection strategy (typically based on a null ID, or a null version when a version property is used). With database-generated IDs, a new object typically leaves `id = null`:

```java
PurchaseOrder order = new PurchaseOrder("PO-2026-100");
order.addLine("SKU-CHAIR", 2, new BigDecimal("125.00"));
order.addLine("SKU-DESK", 1, new BigDecimal("450.00"));

PurchaseOrder saved = repository.save(order);
```

Conceptual flow:

```text
New object (no id yet)
        │
        ▼
repository.save(root)
        │
        ├── INSERT aggregate root
        │       └── receive database-generated ID
        │
        └── INSERT owned children
                ├── attach back-reference to root ID
                └── save each child's state
```

The exact order and SQL statements are determined by Spring Data JDBC along with the dialect/driver, but children must receive the root key to persist the relationship. If children use a foreign key pointing to the root, the root must have an ID before the children are written.

With immutable entities or entities whose ID/version is populated by the framework, the object returned from `save` may contain new values that the input object does not have. Always use the **return value**:

```java
PurchaseOrder saved = repository.save(order);
Long orderId = saved.getId();
Long version = saved.getVersion();
```

Do not assume the passed-in object is always mutated in place to receive the ID/version.

## 4. Flow for updating an existing aggregate

When an aggregate already exists, the application typically reads it first:

```java
PurchaseOrder order = repository.findById(orderId)
        .orElseThrow();

order.confirm();
PurchaseOrder saved = repository.save(order);
```

Spring Data JDBC does not retain a managed entity snapshot to compare which fields changed. When saving an existing aggregate, the traditional Spring Data JDBC persistence model is:

1. Update the aggregate root row by ID and version if present.
2. Delete the child entities stored within the aggregate.
3. Re-insert the child entities present in the submitted aggregate state.

This is a conceptual description of aggregate synchronization; exact SQL and statement ordering depend on mapping, dialect, and framework version. The key takeaway is **do not rely on the assumption that Spring only issues UPDATE statements for modified children**.

Example:

```text
State in the database:
PurchaseOrder #42
  status = DRAFT
  lines = [A, B, C]

Modified object in the application:
PurchaseOrder #42
  status = CONFIRMED
  lines = [A, C, D]

repository.save(order)
        │
        ▼
Synchronize aggregate state:
  - update root #42
  - replace old child set with current child set [A, C, D]
```

For children, Spring Data JDBC may delete old rows and re-insert current rows, including children whose data did not change. Therefore, if a child has an ID referenced externally, triggers, audit records, or relationships outside the aggregate, re-evaluate the design. Owned children should genuinely depend on the root's lifecycle.

## 5. Effects of adding, modifying, and removing children

Suppose an aggregate has a `lines` collection:

| Change in object before save | Desired aggregate outcome | What to understand |
| --- | --- | --- |
| Add an `OrderLine` | New child appears in aggregate | The current child set is persisted with the root |
| Modify quantity of one line | New value is saved | Do not assume only one column of one child is UPDATEd |
| Remove a line from collection | Child no longer belongs to aggregate | The corresponding child row is excluded from saved state |
| Pass empty collection | Aggregate has no children | May delete all child rows belonging to the collection |
| Pass root with child property `null` | No corresponding children | May delete old child data; must distinguish from a PATCH missing the field |

This is why you should not construct a "partial" root object with only an ID and a few fields and call `save` to update a single field. For example:

The pseudocode below illustrates an object containing only partial state:

```text
partialOrder = object with only id and status = "CANCELLED"
repository.save(partialOrder)
```

If other properties are not restored from the database, null values or empty collections may be treated as the intended state to save. This can overwrite root data or delete all children. With aggregates that have multiple relationships, the impact is even greater.

**A safer standard approach:** load the current aggregate, check permissions and business preconditions, apply changes to the full object, and then save the root.

## 6. Designing services with read-modify-save

A service can encapsulate the entire workflow:

```java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderService {

    private final PurchaseOrderRepository repository;

    public PurchaseOrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder confirm(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));

        order.confirm();

        return repository.save(order);
    }

    @Transactional
    public PurchaseOrder addLine(
            Long orderId,
            String sku,
            int quantity,
            BigDecimal unitPrice) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow(() ->
                        new IllegalArgumentException("Order not found"));

        order.addLine(sku, quantity, unitPrice);

        return repository.save(order);
    }
}
```

This service:

- Loads the full aggregate through the root repository.
- Executes domain behavior rather than letting controllers mutate fields directly.
- Saves the new state through the root.
- Uses a transaction boundary so the read/modify/write and related steps can participate in a single transaction.

For a single repository operation, repositories have default transaction behavior defined by Spring Data. Placing `@Transactional` on the service is useful when a business workflow consists of multiple statements that must commit or roll back together. Transactions do not replace optimistic locking: two transactions can still read the same stale version concurrently.

## 7. PATCH APIs and the risk of accidentally deleting children

REST APIs typically distinguish between:

- **PUT:** the client sends the full representation of the resource per the endpoint contract.
- **PATCH:** the client sends only the fields it wants to change.

A PATCH request omitting the `lines` field usually means "do not change the order lines." However, if a deserializer turns an omitted field into `null`, and the application constructs a new aggregate from the DTO and calls `save`, that state may be interpreted as "no order lines left."

For example, a patch DTO should preserve the distinction between:

1. Field absent from JSON.
2. Field present with value `null`.
3. Field present with an empty list.
4. Field present with a list of elements.

Not every DTO or JSON library automatically distinguishes these four cases. Choose an appropriate data type or representation, such as a presence-aware wrapper, `JsonNode`, or a dedicated patch model.

PATCH processing flow:

```text
HTTP PATCH
    │
    ▼
Parse patch with explicit presence state
    │
    ▼
Load current aggregate via repository
    │
    ▼
Apply only fields requested to be changed
    │
    ▼
Validate invariants and business permissions
    │
    ▼
repository.save(full aggregate)
    │
    ▼
Commit transaction
```

Never turn a small PATCH into an operation that replaces the entire aggregate with an empty or incomplete object.

## 8. Optimistic locking with @Version

Suppose two requests update the same order concurrently:

1. Request A reads version `5`.
2. Request B also reads version `5`.
3. A saves successfully, incrementing version to `6`.
4. B still holds the object at version `5` and attempts to save.

Without concurrency conflict detection, the later operation can overwrite the newer state with an old snapshot. Spring Data JDBC supports **optimistic locking** via a property annotated with `@Version`:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;

@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;
}
```

The framework uses the version during updates to ensure the root row is still at the version the object read. Conceptually, the conditional statement resembles:

```sql
UPDATE purchase_order
SET status = ?, version = version + 1
WHERE id = ? AND version = ?;
```

The SQL above only illustrates the principle; actual statements may include additional columns and dialect-specific syntax. If no rows are updated because the version changed, Spring Data JDBC throws an optimistic locking error (in Spring's `OptimisticLockingFailureException` hierarchy).

### 8.1. What does version protect?

`@Version` on the aggregate root protects aggregate updates through the root: two transactions cannot silently succeed when writing based on the same stale version. When the root update fails to match the version, the save fails and the transaction rolls back, including child changes within the same transaction.

Notes:

- Let the framework manage the version; do not manually increment it in business code.
- Return an appropriate conflict error to the client, usually asking to reload the latest state and decide whether to re-apply the change.
- Do not automatically retry a non-idempotent business command without understanding its impact.
- All write paths must respect the same mechanism. Direct SQL updating children or the root without incrementing the version can break concurrency assumptions.
- Version does not replace transactions, constraints, or business validation.

## 9. References to other aggregates are not replaced like owned children

A root can store the ID of another aggregate:

```java
import org.springframework.data.jdbc.core.mapping.AggregateReference;

private AggregateReference<Customer, Long> customer;
```

`AggregateReference` represents a relationship between two independent aggregates. When saving `PurchaseOrder`, Spring Data JDBC persists the referenced ID value according to the mapping; it does not delete and re-insert the entire `Customer` aggregate.

| Data type in root | Meaning | When saving root |
| --- | --- | --- |
| Owned child entity via `@MappedCollection` | Component belonging to root's lifecycle | Saved with the aggregate; child rows may be replaced |
| Embedded value via `@Embedded` | Value stored within the root row | Embedded columns are saved as root state |
| `AggregateReference<Customer, Long>` | Reference to an independent aggregate | Saves referenced ID; does not cascade save to the other aggregate |
| Scalar ID such as `Long customerId` | Application-managed ID value | Saves scalar; application is responsible for verifying the reference if needed |

Do not embed an independent aggregate object into a root as an owned child merely for convenience when reading related data. Properly defining boundaries prevents accidental deletions and prevents aggregates from growing too large.

## 10. Why should aggregates not be too large?

Because of the aggregate-state persistence model, an aggregate with thousands of children can cause `save` to:

- Process many child rows.
- Delete and re-insert a large set of referenced rows.
- Hold transactions and connections open longer.
- Increase lock duration, write logs, database load, and version conflict probability.
- Make updating a single root field unexpectedly expensive.

For example, an order with 5 order lines is a small, manageable aggregate. An account with millions of transaction history records should not hold its entire history as an owned child collection replaced on every account save. History can be a separate aggregate, referenced by ID or queried via its own repository.

Aggregate design should balance:

- Which data must change atomically together?
- Which objects depend on the root's lifecycle?
- Does the child set have a natural upper bound?
- Which parts are accessed or updated independently?
- Should we use embedded value objects, child tables, or separate aggregates?

Do not split aggregates mechanically just to reduce row counts; boundaries must reflect business consistency boundaries.

## 11. When to use custom SQL instead of saving the full aggregate?

Some tasks that update a single value across large datasets may be better suited to a specialized SQL statement:

```java
@Modifying
@Query("""
    UPDATE purchase_order
    SET status = :status
    WHERE id = :id
    """)
int updateStatus(@Param("id") Long id, @Param("status") String status);
```

This illustrates a modifying query in a repository; exact annotation/import syntax should match your Spring Data Relational version. Custom SQL/`JdbcTemplate` can avoid loading and saving the entire aggregate, but it **bypasses the aggregate persistence lifecycle**:

- Does not automatically synchronize child collections.
- Does not run aggregate domain methods or validation.
- May not update the version the way `save` operations expect.
- Does not automatically trigger domain events or side effects normally run by services.

If using custom updates, you must manually ensure transactions, optimistic locking/version checks, validation, constraints, and consistency with all other write paths. In particular, an SQL query updating the root directly without incrementing version may allow a stale aggregate snapshot to overwrite the change later.

Choose custom SQL when there is a clear justification such as bulk updates, reporting, or intentionally designed specialized operations. Do not use it as a way to evade defining aggregate boundaries.

## 12. Common errors and scenarios

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Calling save with an object having only ID and one field loses other data | Saving a partial object as the full aggregate | Load the current aggregate, apply changes, then save |
| Child list disappears after PATCH | DTO does not distinguish missing field, null, and empty list | Design a presence-aware patch model; only replace collection when requested by client |
| Unchanged children are re-inserted | Spring Data JDBC's aggregate synchronization approach | Do not rely on dirty checking; review child identity, triggers, and aggregate size |
| Two requests overwrite each other | Missing version or a write path bypassing version | Use `@Version` and align all update paths |
| Optimistic locking failure | Object is based on an old version | Reload, handle conflict, and re-apply command in a controlled way |
| Saving root does not save referenced aggregate | Confusing external aggregate with owned child | Use `AggregateReference` for IDs; save the other aggregate via its own repository |
| Transaction leaves partial data behind | Statements execute in different transactions or use non-Spring connections | Set transaction boundaries at the service and use Spring-managed infrastructure |
| Save is slow on large aggregates | Too many children to synchronize | Evaluate aggregate boundaries, child size, and access patterns |

When debugging, inspect the full object before save, current version, executed SQL, affected row counts, and the root exception. Never look solely at a root UPDATE statement and conclude the entire aggregate was persisted properly.

## 13. Hands-on exercises

**Exercise 1 — New save.** Create a `PurchaseOrder` with two `OrderLine` instances, call `save`, and verify the root ID and child foreign keys in the database.

**Exercise 2 — Root update.** Read the order, change `status`, and save. Observe root/child SQL statements and confirm the framework does not need dirty checking to save the aggregate.

**Exercise 3 — Collection changes.** Add a line, edit a line, and delete a line. Compare database state before and after; observe the child synchronization strategy.

**Exercise 4 — PATCH.** Create a DTO capable of distinguishing whether `lines` is omitted, `null`, an empty list, or a populated list. Ensure PATCH only replaces the collection when the API contract requires it.

**Exercise 5 — Concurrent update.** Enable `@Version`. Have two transactions read the same aggregate, save the first transaction, and try saving the stale object in the second transaction. Observe the optimistic locking failure.

**Exercise 6 — Aggregate boundary.** Add `AggregateReference<Customer, Long>` to the order. Save/update the order and verify that the customer is not saved/deleted under the owned-child lifecycle.

### References

- [Spring Data Relational — JDBC Aggregate Persistence](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): how Spring Data JDBC saves aggregates, new entities, and existing entities.
- [Spring Data Relational — JDBC Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): entity references, aggregate references, and relationship mapping.
- [Spring Data Relational — Optimistic Locking](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html#jdbc.optimistic-locking): version properties and handling concurrent updates.
