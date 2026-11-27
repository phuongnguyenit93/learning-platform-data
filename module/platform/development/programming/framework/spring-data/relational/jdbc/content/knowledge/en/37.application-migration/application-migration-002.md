# Migrating from JPA: Shifting Mindset to Aggregates and Object Lifecycle

Migrating an application from **JPA/Hibernate** to **Spring Data Relational JDBC** is not just swapping repository interfaces or changing annotations. The two technologies have fundamentally different persistence models. JPA manages entities within a persistence context, tracks object mutations, and can load relationships lazily. Spring Data JDBC operates around **aggregate boundaries**: repositories read and write an aggregate as a unit, and Java objects are not held by the framework in a long-lived persistence context.

The most important change is how you think about objects:

- With JPA, an entity can become managed after being loaded or persisted by the `EntityManager`; field changes can be detected by dirty checking and written to the database on flush.
- With Spring Data JDBC, objects are in-memory data. To persist changes, the application calls a repository or template explicitly. There is no dirty checking, lazy proxy, or persistence-context identity map.
- With JPA, object relationships are typically modeled as entity-to-entity associations. With Spring Data JDBC, you define aggregate roots, owned entities, and references to other aggregates.
- With JPA, cascades and `orphanRemoval` control entity lifecycles inside the persistence context. With Spring Data JDBC, aggregate ownership dictates what data is saved or deleted with the root.
- With JPA, queries can load partial graphs via fetch joins or entity graphs. With Spring Data JDBC, querying the root and its collections follows aggregate loading; custom queries typically return DTOs/read models.

Do not mechanically translate every JPA annotation into a similar-looking JDBC annotation. Redefine aggregate boundaries and use cases first, then design mappings, queries, transactions, and tests around the new model.

## 1. Two Different Persistence Models

### JPA: Persistence Context Manages Entities

The JPA `EntityManager` maintains a persistence context. Within the scope of the context, entities have lifecycle states:

- **New/transient:** the object is not yet managed by a persistence context.
- **Managed:** the object is tracked; changes to persistent fields can be written to the database via dirty checking on flush.
- **Detached:** the object was previously managed but is no longer attached to a persistence context.
- **Removed:** the entity is marked for deletion and will be deleted on flush/commit.

Example:

~~~java
@Transactional
public void renameCustomer(Long id, String name) {
    Customer customer = entityManager.find(Customer.class, id);
    customer.setName(name);
    // No need to call save().
    // Dirty checking will detect changes on flush/commit.
}
~~~

If an entity is loaded within the same persistence context, `EntityManager` normally returns the same managed instance for the same entity identity. This is the identity map. JPA can also use proxies to lazily load associations when the application accesses a property.

### Spring Data JDBC: Explicit Aggregate Persistence

Spring Data JDBC does not maintain a JPA-style persistence context. When a repository reads data, the framework materializes an object graph for the aggregate and returns it to the application. The object does not become a managed entity.

The same use case must call `save`:

~~~java
@Transactional
public void renameCustomer(Long id, String name) {
    Customer customer = customerRepository.findById(id)
            .orElseThrow();

    customer.rename(name);

    customerRepository.save(customer);
}
~~~

If you omit the `save` call, the change remains only in the Java object and is never written to the database.

### Lifecycle Comparison

| Aspect | JPA/Hibernate | Spring Data JDBC |
|---|---|---|
| Persistence context | Yes | No |
| Managed entity | Yes | No equivalent concept |
| Dirty checking | Yes | No |
| Flush | Yes; synchronizes persistence context changes with DB | No persistence-context flush; repository executes persistence operations when called |
| Lazy proxy | Possible | No |
| Identity map | Yes, inside persistence context | No |
| Detached entity | Yes | Objects are just objects; no managed/detached state |
| Object mutations | Can be written automatically on flush | Must explicitly call save/update |
| Aggregate boundary | Not enforced by JPA | Central to the persistence model |

**Consequence:** code that relies on "load an entity, mutate a field, and let the transaction flush automatically" must be rewritten when migrating to Spring Data JDBC.

## 2. Define Aggregate Boundaries Before Changing Mappings

In Spring Data JDBC, an aggregate is a cluster of objects with a single root that manages their lifecycle. The root is the entry point for loading and saving that cluster of data.

Example:

~~~text
PurchaseOrder (aggregate root)
  id
  customer reference
  status
  shipping address (value object)
  lines
    ├── OrderLine
    └── OrderLine

Customer (separate aggregate root)
  id
  name

Product (separate aggregate root)
  id
  sku
~~~

`PurchaseOrder` owns `OrderLine` and `ShippingAddress`. `Customer` and `Product` are separate aggregate roots; `PurchaseOrder` references them only by ID.

Design rules:

1. An aggregate has one root accessed through a repository.
2. Owned entities have lifecycles dependent on the root.
3. Other aggregate roots are referenced by identifier, not treated as child objects with cascade save/delete.
4. A transaction boundary usually spans a use case that may update one or more aggregates, though each aggregate still retains its own ownership boundary.
5. If a child frequently needs to be loaded, updated, and deleted independently, consider promoting it to its own aggregate root.

### From Association Graph to Aggregate Model

A JPA model may have multiple bidirectional associations:

~~~java
@Entity
class PurchaseOrder {
    @OneToMany(mappedBy = "order",
               cascade = CascadeType.ALL,
               orphanRemoval = true)
    private List<OrderLine> lines;
}

@Entity
class OrderLine {
    @ManyToOne
    private PurchaseOrder order;

    @ManyToOne
    private Product product;
}
~~~

When migrating to Spring Data JDBC, there is no need to maintain that bidirectional object graph. The root holds the child collection; the child does not need a back-reference to the root. `Product` is referenced by ID or `AggregateReference`.

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    private Long customerId;

    private String status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();
}

public class OrderLine {

    private Long productId;

    private int quantity;

    private BigDecimal unitPrice;
}
~~~

This snippet is conceptual; constructors, accessors, ID strategies, and column names must match your application schema. The `order_id` column in the child table is an FK to the root; `productId` is a reference to the `Product` aggregate.

## 3. Shifting How You Think About Entity Lifecycle

### JPA: Mutating a Managed Entity

In JPA, a service method can load an entity, invoke setters or domain methods, and omit `repository.save` as long as the entity remains managed:

~~~java
@Transactional
public void changeOrderStatus(Long id, String status) {
    PurchaseOrder order = entityManager.find(PurchaseOrder.class, id);
    order.setStatus(status);
}
~~~

When the transaction flushes, Hibernate inspects entity state and issues the necessary SQL.

### Spring Data JDBC: Load, Mutate, Save

In Spring Data JDBC, the same flow must be written explicitly:

~~~java
@Transactional
public void changeOrderStatus(Long id, String status) {
    PurchaseOrder order = orderRepository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

    order.changeStatus(status);

    orderRepository.save(order);
}
~~~

There is no background mechanism detecting object mutations. Without calling `save`, the database does not change.

### No JPA-Style Merge Semantics

JPA `EntityManager.merge` takes state from a detached object and copies it into the corresponding managed instance. The return value from `merge` is the managed instance; the argument passed in does not necessarily become managed.

Spring Data JDBC `repository.save` is not a clone of `EntityManager.merge`. It persists the aggregate according to Spring Data's mapping and newness detection. Do not assume saving a detached or stale object will merge individual fields like Hibernate.

When updating an aggregate:

1. Load the current aggregate.
2. Apply commands/domain behavior to the loaded object.
3. Call `save` inside a transaction.
4. Use the object returned from `save`, especially with immutable entities, generated IDs, or versions.

~~~java
@Transactional
public PurchaseOrder updateOrder(Long id, UpdateOrderCommand command) {
    PurchaseOrder order = orderRepository.findById(id)
            .orElseThrow(() -> new OrderNotFoundException(id));

    order.changeShippingAddress(command.address());
    order.changeStatus(command.status());

    return orderRepository.save(order);
}
~~~

If you receive an object from a client or API, do not treat it as a detached entity that can be merged. Treat it as a command/DTO, load the current aggregate, and apply permitted changes.

## 4. save() Is Not Dirty Checking

Spring Data JDBC uses `save` to persist aggregates. The framework decides between insert and update based on the entity's new/existing state via newness detection, typically involving the ID and version.

Example:

~~~java
PurchaseOrder newOrder = new PurchaseOrder(customerId, "DRAFT");
PurchaseOrder saved = repository.save(newOrder);
~~~

If the ID is database-generated, the returned object has the assigned ID per the mapping.

For an existing aggregate:

~~~java
PurchaseOrder existing = repository.findById(id).orElseThrow();
existing.changeStatus("PAID");
PurchaseOrder saved = repository.save(existing);
~~~

Do not assume `save` only emits a single `UPDATE` for the modified field like dirty checking. Spring Data JDBC saves the aggregate according to its mapping; persisting owned entities may require multiple statements. In particular, when updating an aggregate, dependent entities may be deleted and re-inserted under the framework's persistence strategy. This impacts triggers, database-level auditing, generated child IDs, and FKs. Inspect actual SQL and verify behavior on your Spring Data Relational version.

### Assigned IDs and Detecting New Entities

A common migration pattern is JPA entities using application-assigned IDs before persistence. In Spring Data JDBC, a non-null ID typically causes the entity to be treated as already existing if no other newness indicator is present. If an ID is pre-assigned to a new aggregate, `save` may take the update branch.

Options:

- Use database-generated IDs when appropriate.
- Use `@Version` so Spring Data has additional information for newness detection per framework rules.
- Implement `Persistable` and `isNew()` when explicit control over newness state is needed.
- Write tests for insert/update with assigned IDs instead of relying on JPA assumptions.

Example interface:

~~~java
public class ExternalOrder implements Persistable<String> {

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

    public void markPersisted() {
        this.newEntity = false;
    }
}
~~~

This example needs a mechanism to transition state after insert and can use callbacks or withers suited to the entity style. For immutable models, design the newness state differently. Never leave a transient flag in the wrong state, as a subsequent `save` could attempt to insert a duplicate key.

## 5. JPA Relationships Become Ownership and References

### @OneToMany: Usually an Owned Collection

JPA:

~~~java
@OneToMany(mappedBy = "order",
           cascade = CascadeType.ALL,
           orphanRemoval = true)
private List<OrderLine> lines;
~~~

Spring Data JDBC:

~~~java
@MappedCollection(idColumn = "order_id", keyColumn = "line_no")
private List<OrderLine> lines;
~~~

The child collection lives in a separate table with an FK pointing back to the root. The aggregate root manages the child lifecycle. No object back-reference from `OrderLine` to `PurchaseOrder` is needed.

### @ManyToOne: Reference by ID

JPA:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "customer_id")
private Customer customer;
~~~

Spring Data JDBC can store the ID:

~~~java
@Column("customer_id")
private Long customerId;
~~~

Or use `AggregateReference`:

~~~java
private AggregateReference<Customer, Long> customer;
~~~

The schema still has the `customer_id` column and may have an FK to `customer(id)`. When loading `PurchaseOrder`, Spring Data JDBC does not automatically load `Customer` into the object graph via a lazy proxy. If you need the customer's name, execute a separate query or use a JOIN projection.

### @ManyToMany: Re-examine the Model

JPA often uses `@ManyToMany` to map a join table. When moving to Spring Data JDBC, evaluate whether the relationship is genuinely many-to-many or whether the join table carries its own data or identity.

If the association has attributes such as `quantity`, `role`, `createdAt`, or status, model the association as a proper entity or aggregate. If you simply need to reference multiple other aggregates, store IDs in an owned collection or reference structure using supported mappings and clearly establish ownership. Never let two aggregate roots jointly own the same collection row.

### Bidirectional Associations Are Not the Goal

JPA can maintain both sides and often requires helper methods to synchronize the owning and inverse sides. Spring Data JDBC typically uses a unidirectional object graph from aggregate root down to children. Reverse navigation is handled via dedicated queries when needed.

This eliminates circular references and clarifies aggregate boundaries, while requiring the application to write explicit queries for reverse traversal.

## 6. CascadeType and orphanRemoval Must Not Be Translated Mechanically

In JPA:

- `CascadeType.PERSIST/REMOVE/MERGE/ALL` propagates operations across associations.
- `orphanRemoval` deletes a child when it is removed from a collection or association.

In Spring Data JDBC, there is no equivalent set of cascade annotations. Persistence of owned entities resides with the aggregate root; saving or deleting the root processes owned data according to the aggregate mapping. References to other aggregates never imply cascading.

| JPA Mapping | How to Think About It in JDBC |
|---|---|
| `CascadeType.PERSIST` on owned child | Child belongs to aggregate; persisted through root |
| `CascadeType.MERGE` | Load root, apply changes, then save; no persistence-context merge semantics |
| `CascadeType.REMOVE` on owned child | Deleting root removes owned data per aggregate lifecycle |
| `CascadeType.REMOVE` on `Customer`/`Product` reference | Does not cascade to other aggregates; delete independent aggregates via their own use case |
| `orphanRemoval=true` | Removing a child from an owned collection is handled by aggregate persistence; test SQL and FKs |
| `CascadeType.ALL` on large graphs | Re-analyze ownership; do not copy verbatim |

In particular, a JPA cascade from `PurchaseOrder` to `Customer` may currently cause the application to delete a `Customer` alongside an `Order` due to legacy mapping. If `Customer` is truly an independent aggregate root, that behavior violates aggregate boundaries. Migrating to JDBC is an opportunity to clarify invariants and deletion workflows.

### Database FKs and Cascades

Do not equate framework cascading with database `ON DELETE CASCADE`. They are two distinct mechanisms:

- JPA cascade is the persistence provider orchestrating operations across an entity graph.
- Spring Data JDBC aggregate persistence orchestrates operations for owned entities.
- FK `ON DELETE CASCADE` is the database automatically deleting dependent rows when a parent row is deleted.

Choose database cascades intentionally, especially when direct SQL, batch jobs, or other applications write to the same schema. Test delete ordering and constraints against the real database.

## 7. Replace Lazy Loading with Explicit Queries and Read Models

JPA can declare:

~~~java
@ManyToOne(fetch = FetchType.LAZY)
private Customer customer;

@OneToMany(mappedBy = "order", fetch = FetchType.LAZY)
private List<OrderLine> lines;
~~~

The application can access `order.getLines()` while the persistence context is still open, and Hibernate may issue additional SQL. This is convenient, yet easily causes N+1 queries and `LazyInitializationException` when accessed after the session closes.

Spring Data JDBC has no lazy proxies. When loading an aggregate, the framework loads owned entities according to the aggregate loading strategy. References to other aggregates do not automatically load related objects.

If a screen needs related data:

- Use a DTO projection with a SQL JOIN.
- Use a repository fragment or `NamedParameterJdbcTemplate` for specialized queries.
- Load the separate aggregate root explicitly if the use case needs domain behavior.
- Use Single Query Loading if the aggregate and dialect meet the feature's constraints.

Do not replace lazy loading by calling a repository inside a getter. Getters with query side effects hide query counts and create hard-to-control coupling.

### N+1 Can Still Happen in the Service Layer

Example:

~~~java
List<PurchaseOrder> orders = repository.findAll();

for (PurchaseOrder order : orders) {
    Customer customer = customerRepository.findById(order.getCustomerId())
            .orElseThrow();
    // ...
}
~~~

Even without lazy proxies, code can still produce N+1 queries by calling a repository inside a loop. If a view needs customer names, write a JOIN/projection query or batch-load customers by a collection of IDs.

## 8. Embedded Value Objects and Custom Conversions

JPA provides `@Embeddable`/`@Embedded`:

~~~java
@Embeddable
public class Address {
    private String street;
    private String city;
}

@Embedded
private Address shippingAddress;
~~~

Spring Data JDBC also provides `@Embedded` to store value object fields in columns on the owner's table:

~~~java
@Embedded(prefix = "shipping_")
private Address shippingAddress;
~~~

The DDL contains `shipping_street` and `shipping_city`. An embedded object is not an aggregate root and has no separate table.

If a value object maps to a single store value, you can use custom converters between the domain type and `String`/`BigDecimal`/`UUID`. Spring Data JDBC uses `JdbcCustomConversions`; JPA `AttributeConverter` implementations are not automatically reused as Spring Data converters.

Example:

~~~java
@WritingConverter
public class EmailAddressWritingConverter
        implements Converter<EmailAddress, String> {

    @Override
    public String convert(EmailAddress source) {
        return source.value();
    }
}

@ReadingConverter
public class EmailAddressReadingConverter
        implements Converter<String, EmailAddress> {

    @Override
    public EmailAddress convert(String source) {
        return new EmailAddress(source);
    }
}
~~~

Bidirectional converters must be registered in `JdbcCustomConversions`/`AbstractJdbcConfiguration` or the corresponding Spring Boot configuration. Verify actual JDBC store types and null behavior.

## 9. Transaction Boundaries Still Matter, Without a Flush Context

Both JPA and Spring Data JDBC use Spring's `@Transactional`. However, a transaction does not turn a Spring Data JDBC object into a managed entity.

JPA may defer SQL until flush/commit. Spring Data JDBC executes SQL statements when repository or template methods are called, within the active transaction. This changes when constraint violations surface and how SQL logs read.

Service example:

~~~java
@Transactional
public void placeOrder(PurchaseOrder order) {
    PurchaseOrder saved = orderRepository.save(order);
    inventoryRepository.reserve(order.getProductId(), order.getQuantity());

    if (saved.getId() == null) {
        throw new IllegalStateException("Missing generated ID");
    }
}
~~~

SQL statements have executed but are not committed until the transaction ends. If the method throws a runtime exception, the transaction can roll back all changes. There is no need to call `EntityManager.flush` because Spring Data JDBC does not use `EntityManager`.

### Repository Transactions vs. Service Transactions

Spring Data JDBC repository CRUD methods carry default transaction metadata. However, when a use case calls multiple repositories or combines a repository with `JdbcTemplate`, place `@Transactional` on the service so all operations share the same transaction boundary.

Do not rely on individual repository methods to provide atomicity across an entire use case. If each method is invoked separately without an enclosing transaction, each may commit independently.

### Do Not Hold Database Transactions While Waiting on Network I/O

Long transactions hold connections and row locks. After migrating from JPA, audit service boundaries to avoid opening transactions before HTTP calls or waiting on user input. Use an outbox or saga when workflows coordinate the database with external systems.

## 10. Optimistic Locking: @Version Exists, With Different Semantics from a Persistence Context

Spring Data JDBC supports optimistic locking via `@Version`:

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;
}
~~~

When updating, the framework includes the current version in the SQL predicate and increments the version. If the row was modified by another transaction, the update matches zero rows for that version and Spring throws `OptimisticLockingFailureException`.

Differences from JPA:

- JPA typically detects stale state when flushing managed entities.
- Spring Data JDBC detects it during explicit `save`/update operations.
- There is no persistence context holding a managed snapshot.
- In-memory objects can still become stale; reload and retry according to business rules.

Concurrency tests should use two separate transactions/connections:

1. Both load the same root at version `v`.
2. Transaction A updates and commits; version becomes `v+1`.
3. Transaction B attempts to save the object still carrying version `v`.
4. Transaction B must receive an optimistic locking failure.

Do not catch the exception and keep using the stale object. Retrying must load a fresh aggregate in a new transaction and re-apply the command if business rules permit.

## 11. Entity Callbacks and Auditing

JPA has lifecycle annotations such as `@PrePersist`, `@PostLoad`, `@PreUpdate`, and `@PreRemove`. Spring Data JDBC has its own entity callbacks and lifecycle events, such as `BeforeConvertCallback`, `BeforeSaveCallback`, `AfterSaveCallback`, `BeforeDeleteCallback`, and `AfterDeleteCallback`.

Do not port JPA annotations directly onto Spring Data JDBC entities; implement the appropriate callback interfaces or move business logic into the domain/service layer.

Auditing example:

~~~java
@Configuration
@EnableJdbcAuditing
public class JdbcAuditingConfiguration {
}
~~~

Entities can use `@CreatedDate` and `@LastModifiedDate` once auditing is configured. When MyBatis or direct SQL updates a table, Spring Data JDBC callbacks and auditing do not run automatically. If multiple write paths coexist, establish conventions for updating audit columns across all paths.

Persistence callbacks do not replace domain events or after-commit events. To send emails or messages only after commit, use a transactional event listener (`AFTER_COMMIT`) or a transactional outbox.

## 12. Query Language and Repository API Changes

JPA provides JPQL, Criteria API, `EntityGraph`, and fetch joins. Spring Data JDBC does not offer JPQL or a persistence context. Main query options:

- Derived queries for aggregate root properties that can filter without joins.
- `@Query` for explicit SQL.
- Repository fragments with `JdbcTemplate`/`NamedParameterJdbcTemplate` for dynamic SQL, JOINs, projections, and complex queries.
- DTO projections/`RowMapper` for read models.
- Aggregate loading for command/domain use cases.

Example derived query:

~~~java
List<PurchaseOrder> findByStatusAndCustomerId(
        String status,
        Long customerId
);
~~~

Searching by `Customer` name requires a SQL JOIN because `Customer` is a separate aggregate:

~~~sql
SELECT po.id, po.customer_id, po.status, po.created_at
FROM purchase_order po
JOIN customer c ON c.id = po.customer_id
WHERE c.name = :customerName;
~~~

If the query returns a DTO, use a `RowMapper`. If it returns an aggregate root, it must satisfy mapping/constructor requirements; collections may be loaded in separate queries. Do not assume a JOIN inside `@Query` automatically constructs a full object graph.

## 13. Redesigning Many-to-Many and Shared Children

JPA permits `@ManyToMany` when two entities share an association table. However, if the association has attributes or its own lifecycle, model the join table explicitly as an entity.

Example `User` and `Role`:

~~~text
User (aggregate)
Role (aggregate)
UserRoleAssignment (association data)
  user_id
  role_id
  assigned_at
  assigned_by
~~~

If the assignment has its own business semantics, do not let both `User` and `Role` own it simultaneously. Pick one aggregate root responsible for creating/deleting assignments, or design the assignment as its own aggregate with an ID and references to `User` and `Role`.

Principle: one row is owned by one aggregate. Multiple aggregates can reference the same ID, but they must not jointly manage that row's lifecycle.

## 14. Schema and Migrations When Leaving Hibernate

If the application relied on Hibernate schema generation, stop relying on `ddl-auto` to alter production schemas when moving to JDBC.

Manage DDL with Flyway or Liquibase:

- Preserve existing tables/columns if the schema is stable.
- Reconcile table/column names with `@Table`/`@Column` and `NamingStrategy`.
- Ensure FKs reflect aggregate ownership and references.
- Identify child table FKs and key columns for `@MappedCollection`.
- Add a version column if using `@Version`.
- Pick SQL types compatible with converters and the JDBC driver.
- Add indexes aligned with query workloads.
- Run migrations against a production-compatible database before deploying.

Do not change the schema and mapping in a single deployment if compatibility with running older application versions is needed. Use expand -> backfill -> contract for breaking changes.

### Comparing JPA and Spring Data JDBC Schemas

| JPA/Hibernate Concept | Spring Data JDBC Schema Consideration |
|---|---|
| `@Entity` + `@Table` | Aggregate root/owned entity mapping and corresponding table |
| `@Id` + `@GeneratedValue` | `@Id` with ID generation suited to dialect/schema |
| `@JoinColumn` | FK column, `idColumn`, or scalar/`AggregateReference` |
| `@OrderColumn` | `keyColumn` for `List`/collection position |
| `@Embedded` | `@Embedded` prefix or converter |
| `@Version` | Corresponding version column |
| `@ManyToMany` join table | Association entity/owned collection/reference by ownership |
| `orphanRemoval` | Child owned by aggregate; test collection insert/delete/update |
| Hibernate DDL auto | Versioned Flyway/Liquibase migrations |

## 15. Step-by-Step Migration Strategy

Do not migrate every entity and service in a single large commit. A low-risk path:

### Step 1: Inventory JPA Behavior

Locate dependencies on:

- `EntityManager.find/persist/merge/remove`.
- Dirty checking and flush.
- Lazy loading and proxies.
- `CascadeType` and `orphanRemoval`.
- Bidirectional relationship helper methods.
- JPQL/Criteria/fetch joins/entity graphs.
- Entity listeners, callbacks, and auditing.
- `@Version` and locking.
- Hibernate-specific annotations, filters, custom types, and schema generation.

Especially look for methods that mutate entities without calling `repository.save`. Those methods depend on dirty checking and must be rewritten.

### Step 2: Draw Aggregate Boundaries

For each entity, determine:

- Which root manages its lifecycle.
- Which entities are owned children.
- Which value objects can be embedded.
- Which aggregate roots should only be referenced by ID.
- Which relationships need JOIN queries rather than object navigation.
- Which children need independent identity/lifecycles.

Do not decide boundaries solely from legacy `@OneToMany`/`@ManyToOne` annotations. Use invariants and transactional consistency to define them.

### Step 3: Keep Schema Stable and Write Mappings

Create Spring Data JDBC models using `@Table`, `@Id`, `@Column`, `@MappedCollection`, `@Embedded`, `AggregateReference`, and needed converters. Reconcile against current DDL; use explicit column names where stability matters.

### Step 4: Write Repositories and Read Model Queries

- Derived queries for root properties.
- `@Query` for explicit SQL.
- Fragments/`NamedParameterJdbcTemplate` for JOINs, CTEs, dynamic filtering, and projections.
- DTOs for read-only screens/reports.
- Repositories loading aggregates for commands.

### Step 5: Migrate Services from Dirty Checking to Explicit Save

Pattern:

~~~text
JPA:
load managed entity
  → change fields
  → transaction flush

Spring Data JDBC:
load aggregate
  → execute domain method
  → repository.save(aggregate)
  → transaction commit
~~~

Watch out for immutable entities: use the instance returned by `save` to capture generated IDs and versions.

### Step 6: Migrate Transactions and Locking

Place `@Transactional` on use cases. Keep the same `DataSource`/transaction manager for repositories and `JdbcTemplate`. Migrate optimistic locking to `@Version` or appropriate conditional updates/row locks.

### Step 7: Migrate Callbacks/Auditing and Side Effects

Replace JPA entity listeners with Spring Data entity callbacks/lifecycle events where appropriate. Move domain rules into aggregates/services. Handle post-commit side effects using an outbox or transactional event listener.

### Step 8: Run Tests Against a Real Database

Test aggregate insert/load/update/delete, collections, references, converters, versions, queries, transaction rollbacks, and concurrency. Use Testcontainers when the production database has specific behaviors.

### Step 9: Roll Out by Module or Use Case

Select an aggregate with few dependencies as a pilot. Migrate read paths or a bounded context first, monitoring SQL, latency, lock contention, and pool usage. Expand only once tests and behavior stabilize.

## 16. Complete Use Case Migration Example

### JPA Version

~~~java
@Entity
class PurchaseOrder {

    @Id
    @GeneratedValue
    private Long id;

    private String status;

    @OneToMany(mappedBy = "order",
               cascade = CascadeType.ALL,
               orphanRemoval = true)
    private List<OrderLine> lines = new ArrayList<>();

    public void addLine(OrderLine line) {
        lines.add(line);
        line.setOrder(this);
    }

    public void markPaid() {
        status = "PAID";
    }
}

@Service
class OrderService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional
    public void pay(Long id) {
        PurchaseOrder order =
                entityManager.find(PurchaseOrder.class, id);

        order.markPaid();

        // No need to save; the managed entity is dirty-checked.
    }
}
~~~

### Spring Data JDBC Version

~~~java
@Table("purchase_order")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    public void addLine(OrderLine line) {
        lines.add(line);
    }

    public void markPaid() {
        if (lines.isEmpty()) {
            throw new IllegalStateException(
                    "Cannot pay an order without lines"
            );
        }
        status = "PAID";
    }
}

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {
}

@Service
public class OrderService {

    private final PurchaseOrderRepository repository;

    public OrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public PurchaseOrder pay(Long id) {
        PurchaseOrder order = repository.findById(id)
                .orElseThrow(() -> new OrderNotFoundException(id));

        order.markPaid();

        return repository.save(order);
    }
}
~~~

The change is not just calling `save`. In the new model:

- There is no back-reference from `OrderLine` to `PurchaseOrder`.
- `OrderLine` belongs to the `PurchaseOrder` aggregate.
- `Product`/`Customer` (if present) are referenced by ID.
- There is no lazy loading.
- There is no dirty checking.
- Version is checked on `save`.
- The transaction boundary still spans the use case.

## 17. Regression Testing When Migrating from JPA

Test behaviors that Hibernate previously provided silently:

| Legacy JPA Behavior | Regression Test for Spring Data JDBC |
|---|---|
| Dirty checking | Mutating an object without `save` must not write DB; calling `save` must write DB |
| Cascade persist | Saving root creates owned rows properly |
| `orphanRemoval` | Removing a child from collection and saving root deletes appropriately per mapping |
| Lazy loading | New use case queries related data explicitly; no hidden queries |
| Bidirectional association | Root/child mapping works without back-references |
| `@Version` | Two transactions update concurrently; stale transaction is rejected |
| Entity callbacks | JDBC callbacks execute on the expected persistence paths |
| JPQL/fetch join | New query returns proper DTO/root without N+1 |
| `EntityManager.merge` | Command loads current aggregate then saves; stale objects are not blindly merged |
| Schema generation | Migrations create a production-compatible schema |

### Test Proving There Is No Dirty Checking

~~~java
@Test
void changingLoadedObjectWithoutSaveDoesNotPersist() {
    PurchaseOrder order = repository.findById(existingId).orElseThrow();
    order.changeStatus("PAID");

    PurchaseOrder reloaded = repository.findById(existingId).orElseThrow();

    assertThat(reloaded.getStatus()).isNotEqualTo("PAID");
}

@Test
void changingLoadedObjectAndSavingPersists() {
    PurchaseOrder order = repository.findById(existingId).orElseThrow();
    order.changeStatus("PAID");

    repository.save(order);

    PurchaseOrder reloaded = repository.findById(existingId).orElseThrow();

    assertThat(reloaded.getStatus()).isEqualTo("PAID");
}
~~~

The first test confirms Java objects are not managed by the framework after the repository returns them. The second confirms `save` is the explicit persistence operation.

### Testing Aggregate Ownership

- Save a root with two children; verify child FKs point to the root.
- Remove a child from the collection and save; verify the corresponding row is handled properly.
- Delete the root; verify owned rows are handled and FKs are not violated.
- References to `Customer`/`Product` do not automatically cascade-delete those aggregates.
- Verify direct SQL and migrations do not create orphan rows.

## 18. Common Pitfalls When Migrating from JPA

| Symptom | Common Cause | Resolution |
|---|---|---|
| Mutating field does not update DB | Relying on JPA dirty checking | Call `repository.save` on the aggregate |
| Saving detached object causes unexpected data | Treating `save` like `EntityManager.merge` | Load current aggregate and apply command |
| Cannot access lazy relationship | Spring Data JDBC does not create lazy proxies | Query reference explicitly or use DTO JOIN |
| Many queries in a loop | Introducing N+1 in service code | Batch query/projection/JOIN |
| Cascade deletes `Customer` unintentionally | Porting JPA cascade without checking ownership | `Customer` is a separate aggregate; delete via its own use case |
| Children are not saved | Collection missing from aggregate mapping or wrong FK/key column | Check `@MappedCollection` and DDL |
| Children rewritten more than expected | `save` handles aggregate as a unit, without Hibernate per-child dirty checking | Measure SQL; evaluate triggers/audit/generated IDs |
| Assigned ID treated as existing entity | Newness detection relies on ID/version | Use `@Version`/`Persistable` or appropriate ID generation |
| Query on another aggregate's field fails | Derived JDBC queries do not auto-JOIN | Use `@Query` or a repository fragment |
| `@Version` does not increment on MyBatis/direct SQL writes | Write path bypasses Spring Data JDBC lifecycle | Check and increment version explicitly |
| JPA callbacks do not run | JPA listeners are no longer in runtime | Implement corresponding `EntityCallback` |
| Generated schema differs from mapping | Relying on Hibernate DDL generation or different naming strategy | Manage migrations and mappings explicitly |
| H2 tests pass, production fails | Different dialect/driver/locking | Use Testcontainers with production database |

## 19. Decision Checklist Before Migrating an Aggregate

1. **Who owns the data?** Identify the aggregate root and owned entities.
2. **Which relationships are just references?** Store IDs/`AggregateReference`; never cascade lifecycle across aggregates.
3. **Does code rely on dirty checking?** Locate every mutation that omits `save`.
4. **Is detached merge used?** Replace with load-current -> apply-command -> save.
5. **Is lazy loading used?** Design explicit queries/projections.
6. **Are cascade/`orphanRemoval` used?** Convert into ownership rules and test child lifecycles.
7. **Is `@Version` used?** Map the version column and test stale updates.
8. **Are entity listeners/auditing used?** Migrate to callbacks or application logic.
9. **Are JPQL/fetch joins used?** Write appropriate SQL, query fragments, or DTOs.
10. **Is schema generation used?** Switch to versioned migrations.
11. **Are assigned IDs or custom types used?** Verify newness detection and converters.
12. **Are there long transactions or network calls?** Shorten transactions and separate side effects.
13. **Are there multiple writers?** Define write ownership, versioning, and cache invalidation.
14. **Are regression tests running on a real database?** Verify aggregates, queries, transactions, concurrency, and schema.

### Quick Decision Table

| JPA Habit | Change When Using Spring Data JDBC |
|---|---|
| Load managed entity then mutate | Load aggregate, mutate, call `save` |
| `EntityManager.merge` detached graph | Use command/DTO, load current aggregate, apply changes |
| Lazy association | Explicit reference query or read model |
| Bidirectional entity graph | Unidirectional object graph from aggregate root |
| Cascade across multiple entities | Distinguish owned children from aggregate references |
| `orphanRemoval` | Child belongs to aggregate; test persistence when removing child |
| JPQL/Criteria/fetch join | Derived query, `@Query` SQL, repository fragment |
| Dirty checking/flush | Explicit repository/template calls in transaction |
| JPA `@Version` | Spring Data JDBC `@Version` and optimistic locking |
| `@PreUpdate`/`@PostLoad` | Appropriate Spring Data `EntityCallback`/lifecycle event |
| Hibernate DDL auto | Flyway/Liquibase migrations |
| `EntityManager` first-level cache | No persistence context; manage reads/caching separately |

**Key takeaway:** when migrating from JPA to Spring Data JDBC, shift from a managed-entity and association-graph mindset to an aggregate-root, ownership, and explicit-persistence mindset. Load the aggregate, apply domain behavior, save explicitly; use IDs to reference other aggregates; replace lazy loading with queries/read models; replace cascades with ownership rules; and re-test transactions, versions, callbacks, schema, and every behavior Hibernate previously provided automatically.

## Official References

- [Spring Data Relational — Domain Driven Design and Relational Persistence](https://docs.spring.io/spring-data/relational/reference/jdbc/domain-driven-design.html): aggregate roots, aggregate boundaries, and how Spring Data JDBC saves aggregates.
- [Spring Data Relational — Object Mapping Fundamentals](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): entity mapping, `@MappedCollection`, `@Embedded`, `AggregateReference`, IDs, and versions.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): aggregate insert/update, lifecycle, and entity callbacks.
- [Spring Data Relational — Query Methods](https://docs.spring.io/spring-data/relational/reference/jdbc/query-methods.html): derived queries, `@Query`, custom SQL, and projection mapping.
- [Spring Data Relational — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction boundaries at the repository and service layers.
- [Jakarta Persistence — Entity Lifecycle](https://jakarta.ee/specifications/persistence/): lifecycle states, persistence context, entity manager, and dirty checking contract.
- [Hibernate ORM User Guide — Persistence Context](https://docs.jboss.org/hibernate/orm/current/userguide/html_single/Hibernate_User_Guide.html): managed/detached entities, dirty checking, cascading, and lazy loading.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): `@Transactional`, proxies, and rollback rules.
