# Self-Assigned UUIDs or Business Codes and the Risk of `save` Mischoosing Update

In **Spring Data JDBC**, an aggregate root can use a database-generated key, an application-generated UUID, or a business code such as `SO-2026-000123`. Self-assigning keys lets the application know the object's identity immediately upon creation, which is convenient for referencing and integration. However, there is a common pitfall: **Spring Data JDBC must determine whether the object is new or existing before deciding whether `save()` executes INSERT or UPDATE**.

If the application generates a UUID before saving, the `@Id` property is already non-`null`. Under the default ID-based detection strategy, Spring Data JDBC may treat the aggregate as existing and choose the UPDATE branch. When the database does not yet contain a row with that UUID, the save call does not automatically become an INSERT. The result may be zero rows updated or an error depending on the versioning mechanism and framework version.

This lesson explains how Spring Data JDBC detects new entities, how to use `@Version` or `Persistable` when IDs are pre-assigned, how to separate technical UUIDs from business codes, and how to organize safe creation and update flows.

## 1. Three types of identifiers to distinguish

Before writing an entity, distinguish three concepts that are often conflated:

| Type | Example | Purpose |
|---|---|---|
| **Technical key (surrogate ID)** | UUID `b9f...`, number `101` | Stable identifier for a row/aggregate in the system |
| **Business code (business key)** | `SO-2026-000123`, `INV-HCM-0088`, `SKU-CHAIR-01` | Code meaningful to users, processes, or external systems |
| **Entity new/existing state** | New / Existing | Decides whether `save()` needs INSERT or UPDATE |

The technical key answers: *which aggregate is this?* The business key answers: *by what code do users or processes refer to this aggregate?* The new/existing state answers: *does this aggregate already exist in the database?*

These three are related, not identical. A UUID generated in memory can already have a value while the corresponding record **does not yet exist in the database**.

### 1.1. Application-generated UUID

The application can generate a UUID before inserting:

~~~java
UUID id = UUID.randomUUID();
~~~

Benefits:

- Identity is available right when the object is created, before calling the database.
- Aggregates can be created across multiple processes without requesting sequence numbers from a central database.
- Convenient when creating related objects or messages that must carry an ID before persisting.
- Harder to guess than sequential integers in some cases, though UUID is not an authorization or secrecy mechanism.

Points to note:

- A UUID is non-`null` from initialization, which can affect new-entity detection.
- Ensure the UUID type is properly supported by the database and JDBC driver. PostgreSQL and H2 have a UUID type; other database systems may require `CHAR(36)`, `BINARY(16)`, or a converter.
- You still need a primary key/unique constraint in the database. UUIDs have an extremely low collision probability, yet the database remains the place that enforces uniqueness.

### 1.2. Application-assigned business codes

Examples:

~~~text
SO-2026-000123
INV-2026-00451
CUSTOMER-HN-000078
~~~

A business code usually has a specific format, rule, or meaning. It may be printed on invoices, sent to customers, or exchanged with other systems. Thus, the code generally needs to be stable over the business lifecycle.

Do not default to using the business code as the primary key. If the code might change when transferring branches, changing numbering rules, or merging data, using it as `@Id` will ripple identity changes into referencing tables.

A usually more flexible design:

~~~text
purchase_orders
├── id            UUID PRIMARY KEY       (technical key)
├── order_number  VARCHAR UNIQUE         (business code)
├── version       BIGINT                 (optimistic locking)
└── status        VARCHAR
~~~

Here, `id` is used for relationships and repositories; `order_number` is used for lookup and display. The database enforces a unique constraint on the business code to prevent two orders from sharing the same number.

## 2. How does `save()` decide between INSERT and UPDATE?

`CrudRepository.save(entity)` is a general API for persisting. It **does not mean always running INSERT**, nor does it mean always executing a SQL `UPSERT` statement.

Conceptually, Spring Data JDBC performs:

~~~text
repository.save(aggregate)
          |
          v
  Is aggregate detected as new?
       /          \
     Yes           No
      |             |
    INSERT        UPDATE
~~~

New/existing detection occurs before writing. Spring Data JDBC uses a new-entity detection strategy (`IsNewStrategy`) based on entity metadata:

1. If the entity has a `@Version` property, the version value takes precedence to determine new state. For wrapper types like `Long`, `null` indicates a new entity; for primitive types like `long`, `0` indicates a new entity.
2. If there is no version property, Spring Data relies on the `@Id` property. A reference-type ID with value `null` usually indicates new; a primitive-type ID with default value `0` usually indicates new.
3. If the entity implements `Persistable`, the `isNew()` method provided by the entity is used to determine state.

Therefore, **an assigned ID value does not mean the row already exists**. This is the root cause of errors when self-assigning UUIDs or business codes.

## 3. Failure example: a populated UUID causes `save()` to take the UPDATE branch

Suppose a simple entity:

~~~java
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id UUID id,
        String orderNumber,
        String status
) {
    public static PurchaseOrder create(String orderNumber) {
        return new PurchaseOrder(
            UUID.randomUUID(),
            orderNumber,
            "DRAFT"
        );
    }
}
~~~

And schema:

~~~sql
CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
);
~~~

When calling:

~~~java
PurchaseOrder order = PurchaseOrder.create("SO-2026-000123");
System.out.println(order.id()); // Already has a UUID

PurchaseOrder saved = repository.save(order);
~~~

`order.id()` is already non-`null`. Because the entity has no `@Version` and does not implement `Persistable`, the default ID-based strategy may treat the object as **existing**. `save()` chooses UPDATE instead of INSERT.

If the database does not yet have a row with that ID, UPDATE cannot create a new row. Depending on execution mechanics and versioning configuration, the operation may affect zero rows or result in an exception. Do not rely on a specific error behavior to drive creation flow.

In particular, adding a check like:

~~~java
if (repository.existsById(order.id())) {
    repository.save(order);
} else {
    repository.save(order);
}
~~~

does not solve the problem. Both branches still call the same `save()` with the same entity whose ID is non-`null`; moreover, `existsById()` followed by insert introduces a race condition if two requests check before either writes data.

## 4. Recommended approach: use `@Version` to distinguish new entities and control concurrent updates

When an aggregate uses a UUID or self-assigned ID, an appropriate approach is to add a version property:

~~~java
import java.util.UUID;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id UUID id,
        @Version Long version,
        String orderNumber,
        String status
) {
    public static PurchaseOrder create(String orderNumber) {
        return new PurchaseOrder(
            UUID.randomUUID(),
            null,
            orderNumber,
            "DRAFT"
        );
    }

    public PurchaseOrder changeStatus(String newStatus) {
        return new PurchaseOrder(id, version, orderNumber, newStatus);
    }
}
~~~

Corresponding schema:

~~~sql
CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY,
    version BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
);
~~~

The two properties have different roles:

- `@Id UUID id`: UUID generated by the application before saving.
- `@Version Long version`: `null` before the first insert, helping Spring Data JDBC detect the aggregate as new.

When the insert succeeds, Spring Data JDBC initializes the version via the versioning mechanism (typically `0` for a new record). On update, the version is checked and incremented. Because `version` is of type `Long`, a `null` value before saving clearly distinguishes it from an existing aggregate.

### 4.1. Repository

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, UUID> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
~~~

The repository's generic ID type must match the `@Id` type: here it is `UUID`, not `Long`.

### 4.2. Creating with an assigned UUID

~~~java
PurchaseOrder draft = PurchaseOrder.create("SO-2026-000123");

// id already has a UUID, but version == null so the entity is detected as new.
PurchaseOrder saved = repository.save(draft);

System.out.println(saved.id());
System.out.println(saved.version());
~~~

The first `save()` performs an INSERT. Always use the **returned object** because the framework-managed version is updated in the returned instance. With an immutable record, the original `draft` variable still has `version == null`.

### 4.3. Updating an existing aggregate

~~~java
PurchaseOrder current = repository.findById(saved.id())
    .orElseThrow();

PurchaseOrder changed = current.changeStatus("CONFIRMED");
PurchaseOrder updated = repository.save(changed);

System.out.println(updated.version());
~~~

This save performs an UPDATE. `current.version()` is the version currently in the database; Spring Data JDBC uses it to detect conflicting updates and increments the version upon a successful save.

### 4.4. Why shouldn't you ignore the returned object?

Suppose:

~~~java
PurchaseOrder first = repository.findById(id).orElseThrow();
PurchaseOrder updated = repository.save(first.changeStatus("CONFIRMED"));
~~~

With a record, `first` still holds the old version, while `updated` holds the new version. If you continue using `first` to save another change, the old version no longer matches the database. Spring Data JDBC can throw `OptimisticLockingFailureException`, detecting stale updates instead of silently overwriting data.

Continue from the latest object:

~~~java
PurchaseOrder next = repository.save(
    updated.changeStatus("SHIPPED")
);
~~~

Do not manually set or increment the version. Version is a concurrency mechanism managed by Spring Data JDBC.

## 5. Why is `@Version` more useful than a plain "isNew" flag?

`@Version` solves two related problems:

1. **New-entity detection:** an uninitialized version value indicates the aggregate has not been saved yet.
2. **Optimistic locking:** when multiple transactions update the same aggregate concurrently, the version detects when one transaction is writing over stale data.

Example of two requests loading version `3`:

~~~text
Initial database: version = 3

Request A reads version 3
Request B reads version 3

Request A UPDATE ... WHERE id = ? AND version = 3
  -> succeeds, database version = 4

Request B UPDATE ... WHERE id = ? AND version = 3
  -> no row matches version anymore
  -> OptimisticLockingFailureException
~~~

The application can ask the user to reload data, return a conflict error, or retry according to business rules. Do not retry indefinitely, because a conflict may indicate two operations that need user resolution.

**Note:** adding `@Version` requires adding the corresponding column in the database and deploying a migration for existing tables. For tables with existing data, determine the initial version value and proper migration ordering before releasing new code.

## 6. Alternative: implementing `Persistable` when not using `@Version`

Spring Data provides the `Persistable<ID>` interface so an entity can determine the result of `isNew()` itself. This is useful when IDs are always pre-assigned yet the application does not want a version property.

Concept:

~~~java
public interface Persistable<ID> {
    ID getId();
    boolean isNew();
}
~~~

An entity implementing `Persistable<UUID>` can hold a new-state flag in memory:

~~~java
@Table("purchase_orders")
public class PurchaseOrder implements Persistable<UUID> {

    @Id
    private UUID id;

    private String orderNumber;
    private String status;

    @org.springframework.data.annotation.Transient
    private boolean newEntity;

    protected PurchaseOrder() {
        // For mapping.
    }

    private PurchaseOrder(
            UUID id,
            String orderNumber,
            String status,
            boolean newEntity) {
        this.id = id;
        this.orderNumber = orderNumber;
        this.status = status;
        this.newEntity = newEntity;
    }

    public static PurchaseOrder create(String orderNumber) {
        return new PurchaseOrder(
            UUID.randomUUID(), orderNumber, "DRAFT", true);
    }

    @Override
    public UUID getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }

    public void markPersisted() {
        this.newEntity = false;
    }
}
~~~

The snippet above illustrates the `Persistable` mechanism and is **not yet a complete implementation ready to drop straight into production**. You must ensure the `newEntity` flag switches to `false` after a successful insert and that entities loaded from the database are also marked as existing. This must be managed through an appropriate Spring Data Relational lifecycle callback or a well-defined factory/mapper convention. Otherwise, an already inserted object that still returns `isNew() == true` can cause the next `save()` to choose INSERT again and hit a duplicate key error.

When using immutable entities or records, managing a state flag is usually more complex. `@Version` is generally cleaner and brings the added benefit of optimistic locking, making it a more maintainable choice for many aggregates.

### Comparing `@Version` and `Persistable`

| Criterion | `@Version` | `Persistable.isNew()` |
|---|---|---|
| Detecting self-assigned UUID | Yes, if initial version indicates new | Yes, based on `isNew()` result |
| Concurrent update control | Provides optimistic locking | Does not provide version locking itself |
| State management after insert | Framework updates version | Application must manage `isNew` flag |
| Fit with immutable records | Usually convenient | Harder if the flag must mutate |
| Extra database column | Has a version column | Not required |
| When to choose | Need conflict detection and want a clear strategy | Have custom detection rules with controlled lifecycle |

Do not implement both mechanisms arbitrarily. Choose one suitable new-entity detection strategy and test the create, read, and update flows of the aggregate itself.

## 7. Self-assigned business codes face the same issue

Suppose an order uses the code `SO-2026-000123` as `@Id`:

~~~java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id String orderNumber,
        String status
) {
    public static PurchaseOrder create(String orderNumber) {
        return new PurchaseOrder(orderNumber, "DRAFT");
    }
}
~~~

Because `orderNumber` already has a value, Spring Data JDBC can treat the entity as existing if there is no version property or `Persistable`. Even though the code `SO-2026-000123` was just generated and the database has no row yet, `save()` may still choose UPDATE.

This problem does not occur only with UUIDs. It applies to any pre-assigned ID:

- `String` containing an order code.
- `Long` self-assigned by the application.
- `UUID` generated by `UUID.randomUUID()`.
- Codes obtained from an external system.

If you still want the business key as `@Id`, use `@Version` or an appropriate `Persistable` strategy. However, carefully weigh using a business code as a primary key.

### 7.1. Commonly recommended design: UUID as ID, business key as unique column

~~~java
@Table("purchase_orders")
public record PurchaseOrder(
        @Id UUID id,
        @Version Long version,
        String orderNumber,
        String status
) {
    public static PurchaseOrder create(String orderNumber) {
        return new PurchaseOrder(
            UUID.randomUUID(), null, orderNumber, "DRAFT");
    }
}
~~~

Schema:

~~~sql
CREATE TABLE purchase_orders (
    id UUID PRIMARY KEY,
    version BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    status VARCHAR(20) NOT NULL
);
~~~

Repository still uses UUID as the ID type:

~~~java
interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, UUID> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);
}
~~~

Benefits:

- UUID is a stable technical identifier that does not need to change when the order code format changes.
- Business code has a unique constraint and can be used for lookups.
- Version separates new/existing state from the presence of the UUID.
- Relationships between aggregates use UUID; users can still look up orders by the `SO-...` code.

If a business code is a truly immutable natural identifier, unique and meaningful across the entire lifecycle, using it as `@Id` can still make sense. But it must be a deliberate decision, not merely because that column already has a value.

## 8. Generating business codes safely under concurrent requests

Another mistake is generating order numbers by reading the largest number:

~~~sql
SELECT MAX(order_number) FROM purchase_orders;
~~~

Then adding 1 to form the new code. This approach is unsafe when multiple requests run concurrently:

~~~text
Request A reads max number = 100
Request B reads max number = 100
Request A creates code 101
Request B also creates code 101
~~~

A unique constraint will reject one of the two inserts, yet the rejected request still fails. Without proper retry handling, users may encounter sporadic failures under high load.

### Common ways to generate business codes

**Database sequence:** the database assigns sequential numbers via a sequence; the application formats the number into `SO-2026-000123`. Sequences are generally safe under concurrent requests, though they can leave gaps when transactions roll back. Whether gaps are acceptable is a separate business requirement.

**Number allocation table with locking/atomic update:** a transactional operation updates a counter and returns the new number. Locking and retry handling must be designed carefully to avoid duplicates.

**Dedicated code-generation service:** suitable for multi-service systems or when numbering rules depend on branch, fiscal year, or document type.

**UUID as reference code:** if business rules do not require human-readable sequential numbers, a UUID can serve as a public or reference code; still distinguish security requirements from unpredictability.

Avoid `MAX(...) + 1` in concurrent flows. Even if the code ultimately has a unique constraint, the unique constraint is a last line of defense, not a code-generation algorithm.

### Business code vs. idempotency key

An order creation API can accept a `requestKey` to prevent duplicate creation when a client retries a request. This idempotency key should be stored with a unique constraint and linked to the creation outcome. Do not equate it with the internal UUID or displayed order code if their lifecycles and uniqueness scopes differ.

## 9. Separating creation and update flows at the service layer

Do not let an arbitrary request decide that if an entity has an ID it must update. Design explicit use cases:

~~~java
@Service
public class OrderService {

    private final PurchaseOrderRepository repository;

    public OrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder create(String orderNumber) {
        PurchaseOrder draft = PurchaseOrder.create(orderNumber);
        return repository.save(draft);
    }

    @Transactional
    public PurchaseOrder changeStatus(UUID id, String status) {
        PurchaseOrder current = repository.findById(id)
            .orElseThrow(() ->
                new NoSuchElementException("Order not found: " + id));

        PurchaseOrder changed = current.changeStatus(status);
        return repository.save(changed);
    }
}
~~~

The `create` method always constructs a new aggregate via a factory. The `changeStatus` method must load the existing aggregate, apply business rules, and then save. If `@Version` is used, the version is carried over from the loaded object.

The example above illustrates service structure; in a real application, use an `OrderStatus` enum and domain methods such as `confirm()` and `cancel()` instead of passing arbitrary status strings.

### Should you call `existsById()` before creating?

Do not use a "check existence then decide save" pattern as a duplicate-prevention measure:

~~~java
if (!repository.existsById(id)) {
    repository.save(order);
}
~~~

Two requests can still both see that the ID does not exist before either inserts. Let the primary key/unique constraint enforce uniqueness and handle duplicate errors intentionally. If an idempotent create operation is needed, define an idempotency key and rules to return the previous creation result.

### Do not turn `save()` into a business upsert

`save()` chooses INSERT or UPDATE based on entity state per the detection strategy. It does not automatically verify "insert if absent, update if present" as an atomic upsert supported across all databases. If you genuinely need an upsert by a unique business key, design database-appropriate SQL, handle concurrency, and define the side effects on the aggregate clearly.

## 10. Troubleshooting common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| New UUID, yet `save()` does not insert a row | ID is already non-`null`, no version or `Persistable` | Add `@Version Long` initially `null`, or implement `Persistable` with proper lifecycle |
| Repository generic uses `Long` while entity ID is UUID | Wrong ID type | Change to `CrudRepository<PurchaseOrder, UUID>` |
| Second update reports optimistic locking | Using stale object/version or another transaction updated it | Reload aggregate, handle conflict, use instance returned from `save()` |
| `version` is null yet schema forbids null on insert | Mismatched mapping/version strategy or DDL | Check `@Version`, wrapper type, SQL configuration, and DDL for your version |
| Two orders created with the same order number | Missing unique constraint or unsafe code allocator | Add a unique constraint and use a concurrency-safe sequence/allocator |
| Rollback leaves document numbers with gaps | Sequences do not roll back with transactions | Determine whether strictly gapless numbering is actually required |
| `isNew` flag stays true | `Persistable` did not transition state after insert | Manage lifecycle callbacks and saved entity state |
| Self-assigned UUID ID treated as existing | Did not separate assigned ID from persistence state | Use `@Version` or `Persistable` |

When investigating, inspect the actual SQL and the values of `id` and `version` right before calling `save()`. Do not rely solely on a "saved" log message or the presence of a UUID in the object to conclude the database contains the record.

## 11. Decision guide

| Scenario | Usually appropriate design |
|---|---|
| Database auto-generates ID, new entity has `null` ID | Let Spring Data JDBC detect the new entity from the ID |
| Application needs UUID as soon as the aggregate is created | Use `@Version Long` initially `null` for new detection and optimistic locking |
| Self-assigned ID without wanting a version property | Consider `Persistable`, managing `isNew()` after insert and after load |
| Human-readable business order code | Use UUID as `@Id`, business code as a unique column |
| Business key is truly immutable and serves as a natural key | Can be used as `@Id`, but new-state detection must be handled |
| Concurrent requests generating sequential numbers | Database sequence or atomic allocator; do not use `MAX + 1` |
| API needs duplicate-creation protection on retry | Design a dedicated idempotency key and unique constraint |

## 12. Conclusion

In Spring Data JDBC, **having a populated ID does not mean the entity already exists in the database**. `save()` selects INSERT or UPDATE based on the new-entity detection strategy. Therefore, when self-assigning a UUID or business code before saving, relying solely on a non-`null` ID can cause `save()` to mistakenly choose UPDATE.

For aggregates using UUIDs, the most controllable approach is usually combining `@Id UUID` with `@Version Long` initialized to `null`. Version both detects the initial insert and catches concurrent updates. `Persistable.isNew()` is another option when there is a specific reason, provided the state flag's lifecycle is managed accurately.

Keep **technical key**, **business code**, and **new/existing state** as three distinct concepts. Use unique constraints for business codes, concurrency-safe code allocators, and service flows that separate creation from updates. That way, self-assigning UUIDs or business codes will no longer cause the repository to misguess your persistence intent.
