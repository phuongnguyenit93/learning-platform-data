# When to Use JdbcAggregateTemplate Instead of a Repository?

In **Spring Data Relational JDBC**, a repository is the familiar way to access an aggregate: declare an interface for the aggregate root type, extend `CrudRepository` or `ListCrudRepository`, and use methods such as `findById`, `save`, and `deleteById`. However, Spring Data JDBC also provides **JdbcAggregateTemplate**, a template-style API for working directly with aggregates without going through a specific repository interface.

Both approaches share Spring Data JDBC's aggregate mapping model, yet they suit different ways of organizing code. Repositories fit most CRUD use cases tied to a single aggregate type and queries expressed through methods. `JdbcAggregateTemplate` is useful when you need to invoke aggregate operations programmatically, choose the aggregate type at runtime, or explicitly request an insert or update.

The key point to remember is that `JdbcAggregateTemplate` still operates at the **aggregate level**. It is not a `JdbcTemplate` for running arbitrary SQL, nor does it replace domain behavior. This lesson explains how it works, when to use it, how to integrate it into services, and the limitations to consider.

## 1. Repository as the Default Choice for Per-Aggregate CRUD

Suppose an application manages orders. `PurchaseOrder` is the aggregate root and `OrderLine` instances belong to the order:

~~~text
PurchaseOrder (aggregate root)
├── id
├── orderNumber
├── status
└── lines
    ├── OrderLine
    └── OrderLine
~~~

A repository can be declared as:

~~~java
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long> {

    Optional<PurchaseOrder> findByOrderNumber(String orderNumber);

    List<PurchaseOrder> findByStatus(String status);
}
~~~

A service using the repository:

~~~java
@Service
public class OrderService {

    private final PurchaseOrderRepository orders;

    public OrderService(PurchaseOrderRepository orders) {
        this.orders = orders;
    }

    public PurchaseOrder getOrder(long id) {
        return orders.findById(id)
            .orElseThrow(() ->
                new NoSuchElementException("Order not found"));
    }
}
~~~

A repository provides a domain-oriented abstraction:

- The aggregate type and ID type are fixed right in the declaration.
- CRUD methods are available out of the box without writing basic data access boilerplate.
- Derived queries such as `findByStatus` can be added easily.
- The repository acts as a clear boundary between application services and persistence.
- Calling code does not have to pass `Class<PurchaseOrder>` for every operation.

For an application with well-defined aggregates and standard CRUD, a repository is usually the most readable and maintainable option.

## 2. What Is JdbcAggregateTemplate?

`JdbcAggregateTemplate` is Spring Data JDBC's template-style API for performing persistence operations on aggregates. The class resides in the package:

~~~java
org.springframework.data.jdbc.core.JdbcAggregateTemplate
~~~

Instead of declaring a dedicated repository interface for each aggregate, code can call the template and pass the object or domain type to operate on.

Common operations include:

| Operation | Purpose |
|---|---|
| `insert(aggregate)` | Insert a new aggregate |
| `update(aggregate)` | Update an existing aggregate |
| `save(aggregate)` | Choose insert or update using the new-entity detection strategy |
| `findById(id, AggregateType.class)` | Find an aggregate by ID and root type |
| `findAll(AggregateType.class)` | Read all aggregates of the specified type |
| `existsById(id, AggregateType.class)` | Check whether an ID exists |
| `count(AggregateType.class)` | Count aggregates |
| `deleteById(id, AggregateType.class)` | Delete an aggregate by ID |
| `delete(aggregate)` | Delete the passed aggregate |

Exact APIs and overloads may vary across Spring Data JDBC versions. Consult the Javadoc for the version declared in your project when you need to confirm exact signatures.

An obvious difference is that read and delete operations by ID take an additional aggregate type parameter, for example:

~~~java
PurchaseOrder.class
~~~

The template needs this type to know which mapping metadata to use, because an ID such as `1001L` by itself does not indicate which aggregate table it belongs to.

## 3. The Template Still Preserves Aggregate Mapping and Semantics

The name "Template" may lead learners to think `JdbcAggregateTemplate` is merely a utility wrapper around SQL statements. In reality, it is a Spring Data JDBC persistence API that works with aggregate metadata and the framework's mapping mechanism.

When operating on `PurchaseOrder`, the template uses the mapping declared for the root and its aggregate members, such as a child collection via `@MappedCollection`:

~~~java
@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Column("order_number")
    private String orderNumber;

    private String status;

    @MappedCollection(idColumn = "order_id")
    private Set<OrderLine> lines = new LinkedHashSet<>();

    // Constructors and domain behavior.
}
~~~

When saving the aggregate root, the framework knows how to map child elements according to the configuration. The application continues working with a single aggregate rather than manually writing to individual tables with separate SQL statements.

That means:

- The template uses Spring Data JDBC's mapping metadata, converters, and persistence mechanisms.
- Members belonging to the aggregate are handled according to the root's mapping.
- A child entity does not automatically become an aggregate root just because it has a table or an `@Id` property.
- Other aggregates referenced by ID retain their own independent lifecycle.
- The template does not automatically enforce business rules; domain methods and application services remain responsible for that.

## 4. When Should You Use JdbcAggregateTemplate?

### 4.1. Operating on an Aggregate Without Creating a Dedicated Repository

An infrastructure component may need to write an aggregate type in a generic flow without needing derived queries or a dedicated repository API.

For example, a service that imports normalized data as a `PurchaseOrder`:

~~~java
@Service
public class OrderImportService {

    private final JdbcAggregateTemplate aggregateTemplate;

    public OrderImportService(JdbcAggregateTemplate aggregateTemplate) {
        this.aggregateTemplate = aggregateTemplate;
    }

    @Transactional
    public PurchaseOrder importNewOrder(PurchaseOrder order) {
        return aggregateTemplate.insert(order);
    }
}
~~~

Here the use case knows for certain that the object is a new aggregate and wants to request an explicit INSERT. There is no need to create a repository just to invoke a single `insert` operation.

The example above assumes Spring Data JDBC is already configured and `JdbcAggregateTemplate` is registered as a bean in the application context, as in standard Spring Data JDBC/Spring Boot setups.

### 4.2. Explicitly Choosing Insert or Update

This is a practical reason to choose the template. A CRUD repository typically steers callers toward `save()`, whereas the template provides distinct operations:

~~~java
aggregateTemplate.insert(newOrder);
aggregateTemplate.update(existingOrder);
~~~

When the business flow has already determined the state with certainty:

- Use `insert` when you know the aggregate does not exist yet and want to create a new one.
- Use `update` when you know the aggregate already exists and want to update it.

Choosing explicitly makes the code's intent clearer, especially in imports, data migrations, or integration adapters. The database must still enforce primary key and unique constraints; `insert` does not eliminate the possibility of duplicate keys.

Do not use `insert` simply because an object has a non-null ID, or avoid it for the same reason. An ID can be application-assigned before a row exists. Persistence state must be determined from the use case, not solely by inspecting the ID value.

### 4.3. Selecting the Aggregate Type at Runtime

Template methods accept a domain type such as `PurchaseOrder.class`. Therefore, in a generic component, the aggregate type can be passed in from configuration or a controlled processing flow.

For example, a helper for reading aggregates:

~~~java
public class AggregateReader {

    private final JdbcAggregateTemplate template;

    public AggregateReader(JdbcAggregateTemplate template) {
        this.template = template;
    }

    public <T> Optional<T> findById(Object id, Class<T> aggregateType) {
        return template.findById(id, aggregateType);
    }
}
~~~

Calling code can explicitly select the type:

~~~java
Optional<PurchaseOrder> order =
    aggregateReader.findById(1001L, PurchaseOrder.class);
~~~

This is useful when building adapters or shared persistence components. However, you should not turn every application service into generic code just to avoid declaring repositories. Concrete aggregate types usually make business code safer and easier to read.

If the aggregate type originates from external input, do not pass arbitrary class names directly to load data. Map a whitelisted business type to an allowed class instead.

### 4.4. Integrating into a Custom Repository Fragment

A repository may need special methods beyond standard CRUD and derived queries. You can create a repository fragment and use `JdbcAggregateTemplate` inside its implementation:

~~~java
public interface PurchaseOrderOperations {
    PurchaseOrder insertImported(PurchaseOrder order);
}
~~~

~~~java
public class PurchaseOrderOperationsImpl
        implements PurchaseOrderOperations {

    private final JdbcAggregateTemplate template;

    public PurchaseOrderOperationsImpl(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Override
    public PurchaseOrder insertImported(PurchaseOrder order) {
        return template.insert(order);
    }
}
~~~

The repository combines the fragment:

~~~java
public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long>,
                PurchaseOrderOperations {
}
~~~

This is a clean way to keep the business API on the repository while the implementation uses the template for specialized persistence operations. Fragment implementation naming conventions and composition rules must follow the Spring Data version in use.

### 4.5. Needing an Aggregate API in an Infrastructure Adapter

An adapter may receive an aggregate created by the domain/application layer and persist it without depending on a concrete repository interface. The template provides aggregate operations as a direct API.

However, consider dependency direction: pure domain code should not depend on Spring Data JDBC. Typically, the template is injected into an adapter or infrastructure service, while the application service calls through a port if the project uses a ports-and-adapters architecture.

## 5. CRUD Examples with JdbcAggregateTemplate

The examples below use `PurchaseOrder` as the aggregate root with a `Long` ID.

### 5.1. Injecting the Template

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.stereotype.Service;

@Service
public class PurchaseOrderPersistenceService {

    private final JdbcAggregateTemplate template;

    public PurchaseOrderPersistenceService(JdbcAggregateTemplate template) {
        this.template = template;
    }
}
~~~

In a standard Spring Data JDBC configuration, the template is provided by infrastructure. If the application configures JDBC manually, make sure the mapping context, converters, dialect, and data access strategy are configured consistently.

### 5.2. Inserting a New Aggregate

~~~java
@Transactional
public PurchaseOrder create(PurchaseOrder draft) {
    return template.insert(draft);
}
~~~

`insert` clearly expresses that the use case intends to create a new row. If the database generates the ID automatically, use the returned object to retrieve the identifier populated by the framework. For immutable object types, do not assume the input instance is mutated in place.

If the ID is assigned by the application, `insert` still executes as an insert. Primary key or unique constraints in the database protect uniqueness.

### 5.3. Updating an Existing Aggregate

~~~java
@Transactional
public PurchaseOrder update(PurchaseOrder changed) {
    return template.update(changed);
}
~~~

Only call `update` when the use case knows the aggregate already exists. If no matching row exists, `update` does not automatically turn into an insert. When the aggregate uses `@Version`, the version still participates in Spring Data JDBC's optimistic locking mechanism; pass the aggregate with a valid version.

### 5.4. Using save When New/Existing State Is Not Explicitly Decided

~~~java
@Transactional
public PurchaseOrder save(PurchaseOrder order) {
    return template.save(order);
}
~~~

`save` uses Spring Data JDBC's new-entity detection strategy. Therefore, its semantics are close to repository `save`: the framework relies on metadata such as `@Id`, `@Version`, or `Persistable.isNew()` to choose insert or update.

Do not interpret `save` as an atomic SQL upsert statement. If multiple requests create the same ID concurrently, or data changes concurrently, database constraints and optimistic locking must still be handled.

### 5.5. Finding an Aggregate by ID

~~~java
@Transactional(readOnly = true)
public PurchaseOrder get(long id) {
    return template.findById(id, PurchaseOrder.class)
        .orElseThrow(() ->
            new NoSuchElementException("Order not found"));
}
~~~

The `PurchaseOrder.class` type tells the template which aggregate metadata to use. The result is typically represented as `Optional<T>` so calling code can handle the not-found case.

### 5.6. Checking Existence and Counting

~~~java
boolean exists = template.existsById(id, PurchaseOrder.class);

long count = template.count(PurchaseOrder.class);
~~~

These operations are useful for technical checks or administrative tasks. If you need complex conditions such as counting orders by status, tenant, or date range, use a repository query, `@Query`, or dedicated read SQL.

### 5.7. Deleting an Aggregate

~~~java
@Transactional
public void delete(long id) {
    template.deleteById(id, PurchaseOrder.class);
}
~~~

Or when you already have the aggregate:

~~~java
@Transactional
public void delete(PurchaseOrder order) {
    template.delete(order);
}
~~~

The operation still applies to the aggregate root. If the root owns child entities via `@MappedCollection`, the framework handles the aggregate members according to the mapping. Another aggregate that merely holds a foreign key referencing the order is not automatically deleted along with it.

## 6. How Do JdbcAggregateTemplate and Repositories Differ?

These two APIs are not two independent persistence engines. Both belong to Spring Data JDBC and rely on aggregate mapping. The main difference lies in the level of abstraction and how operations are expressed.

| Criterion | Repository | JdbcAggregateTemplate |
|---|---|---|
| Declaration style | Interface per aggregate root | Inject template into a class |
| Aggregate type | Fixed in repository generics | Passed via `Class<T>` parameter on many operations |
| Standard CRUD | Very convenient | Provides corresponding aggregate operations |
| Derived queries | Supported | No mechanism for declaring named query methods |
| Custom operations | Repository method/fragment | Called directly from service/adapter or fragment |
| Explicit insert/update | Typically uses `save` from CRUD repository | Has separate `insert` and `update` |
| Code organization | Domain-oriented persistence contract | Programmatic aggregate operations API |
| Best suited for | Typical per-aggregate use cases | Generic flows, explicit persistence operations, infrastructure |

Choosing the template does not automatically make operations faster. Nor does it turn aggregate operations into bulk SQL. The reason to choose it should be API organization or the need for explicit operations, not assumptions about performance.

## 7. Distinguishing JdbcAggregateTemplate from JdbcTemplate

The two class names look similar, but their purposes are different:

| | JdbcAggregateTemplate | JdbcTemplate |
|---|---|---|
| Abstraction | Spring Data JDBC aggregate | Direct SQL/JDBC |
| Inputs | Aggregate objects, IDs, and domain types | SQL, parameters, and `RowMapper` |
| Mapping | Aggregate metadata and Spring Data converters | Application specifies row mapping |
| Child relationships | Handled via aggregate mapping | Application writes SQL for each table |
| JOINs and window functions | Not the primary target | Well suited |
| Reporting DTOs | Not the primary target | Well suited |
| Data modifications | Insert/update/delete aggregates | Arbitrary SQL, including bulk statements |

`JdbcTemplate` example:

~~~java
List<OrderSummary> summaries = jdbcTemplate.query(
    """
    SELECT
        o.id,
        o.order_number,
        COUNT(l.id) AS line_count
    FROM purchase_orders o
    LEFT JOIN order_lines l ON l.order_id = o.id
    GROUP BY o.id, o.order_number
    """,
    (rs, rowNum) -> new OrderSummary(
        rs.getLong("id"),
        rs.getString("order_number"),
        rs.getLong("line_count")
    )
);
~~~

This is a read-model query. `JdbcTemplate` is appropriate because the result is an aggregated DTO across multiple tables, not an aggregate that needs to be saved through root mapping.

Do not pick `JdbcAggregateTemplate` simply because its name contains "JDBC" when your real goal is running JOINs, CTEs, window functions, or bulk SQL. Choose the API based on the result type and the responsibility required.

## 8. Does the Template Replace Domain Behavior?

No. `JdbcAggregateTemplate` is a persistence API. It does not know business rules such as:

- Can an order that has already been submitted have its lines modified?
- Can an order be confirmed without any order lines?
- Which statuses permit cancellation?
- How must order totals be calculated or validated?

These rules must live inside the aggregate or in domain/application services.

For example, do not accept an arbitrary object and call `template.update(order)` before checking state. Use domain methods:

~~~java
@Transactional
public PurchaseOrder submit(long id) {
    PurchaseOrder order = template.findById(id, PurchaseOrder.class)
        .orElseThrow();

    order.submit(); // Domain enforces invariants.

    return template.update(order);
}
~~~

Here the template performs persistence, while `submit()` decides whether the change is valid. If the application needs to distinguish between creating and updating, the use case should intentionally choose `insert` or `update`.

## 9. Transactions and Multiple Aggregate Operations

A use case may need to read an aggregate, check rules, update another aggregate, or write an audit record. Place the transaction boundary at the application service when database operations must succeed or roll back together:

~~~java
@Service
public class OrderWorkflowService {

    private final JdbcAggregateTemplate template;
    private final OrderAuditRepository audit;

    public OrderWorkflowService(
            JdbcAggregateTemplate template,
            OrderAuditRepository audit) {
        this.template = template;
        this.audit = audit;
    }

    @Transactional
    public PurchaseOrder confirm(long id) {
        PurchaseOrder order = template.findById(
            id, PurchaseOrder.class
        ).orElseThrow();

        order.confirm();
        PurchaseOrder saved = template.update(order);

        audit.save(OrderAudit.confirmed(saved.getId()));
        return saved;
    }
}
~~~

This example illustrates a template and a repository participating in the same use case. To share a transaction, the components must use the same transaction manager and the appropriate shared `DataSource`. Do not assume two different databases or two different transaction managers automatically commit or roll back together.

If the operation calls external services, avoid holding a database transaction open across long network waits. An outbox or asynchronous workflow may be needed depending on consistency requirements.

## 10. Considerations When Choosing the Template

### 10.1. Do Not Use the Template to Avoid Designing Repositories

If an aggregate has many domain queries such as `findByStatus`, `findByOrderNumber`, and `findByCustomerId`, a repository interface clearly expresses the read contract. Using the template for everything and rewriting queries manually sacrifices the benefits of the repository abstraction.

### 10.2. Do Not Manipulate Child Entities Directly as Independent Aggregates

If `OrderLine` belongs to `PurchaseOrder`, load and modify it through the root. `JdbcAggregateTemplate` is not a reason to turn a child entity into an independent persistence unit that bypasses aggregate ownership and invariants.

### 10.3. Be Careful with insert, update, and save

The three methods express three different intents:

- `insert`: definitely creating a new aggregate.
- `update`: definitely updating an existing aggregate.
- `save`: letting the new/existing detection strategy choose the branch.

Do not mechanically choose a method based solely on whether the object already has an ID. Application-assigned IDs can have values before the first insert. If using `save`, understand how `@Version` or `Persistable.isNew()` affects the decision.

### 10.4. Do Not Assume the Template Is a Bulk API

Calling `insert` or `update` for each aggregate is still an aggregate-level operation. If you need to ingest hundreds of thousands of rows at high throughput, measure the cost, design batching, and consider an appropriate bulk mechanism. Direct bulk SQL requires handling foreign keys, mapping, auditing, and invariants yourself—things repositories and templates normally coordinate.

### 10.5. Verify the API for Your Version

Method signatures, overloads, and template configuration can change across Spring Data JDBC versions. Use your project's dependency version to check the Javadoc and write integration tests against the target database. Do not copy an example from another version without verifying packages, beans, and return types.

## 11. Decision Table: Which API Should You Use?

| Scenario | Usually Suitable Choice | Reason |
|---|---|---|
| Standard CRUD for `PurchaseOrder` | `PurchaseOrderRepository` | Aggregate-oriented contract, built-in CRUD |
| Finding orders by status or number | Repository derived query | Method name expresses the filter |
| Import flow guaranteed to have new aggregates | `JdbcAggregateTemplate.insert` | Explicit INSERT intent |
| Update flow guaranteed to have existing aggregates | `JdbcAggregateTemplate.update` or repository `save` after loading root | Operation matches known state |
| Generic component needing domain type at runtime | `JdbcAggregateTemplate` | Accepts `Class<T>` |
| Repository needing one special template-backed operation | Custom repository fragment | Keeps repository API, uses template in implementation |
| Multi-table JOIN report | `JdbcTemplate` / `NamedParameterJdbcTemplate` | Custom SQL and DTOs |
| Projection of selected properties | Repository projection or dedicated query | Returns only the needed data view |
| Bulk SQL with complex conditions | Spring JDBC or dedicated SQL | Needs control over SQL statement and batching |

## 12. Hands-On Exercises

### Exercise 1 — Performing CRUD with the Template

1. Create a `PurchaseOrder` aggregate with `@Id` and an `OrderLine` collection.
2. Inject `JdbcAggregateTemplate`.
3. Create a new order using `insert`.
4. Read it back with `findById(id, PurchaseOrder.class)`.
5. Change its status through a domain method and persist with `update`.
6. Delete the aggregate with `deleteById`.

Observe the data in both the root table and child table to understand that the template still uses aggregate mapping.

### Exercise 2 — Comparing save and insert

1. Create an aggregate with a UUID or pre-assigned ID.
2. Try `save` with an appropriate new/existing detection configuration.
3. Try `insert` for a new aggregate.
4. Try `insert` with a duplicate ID and observe the constraint error.
5. Explain why a non-null ID does not by itself prove that a row already exists.

### Exercise 3 — Combining Repository and Template

1. Use a repository to find an order by `orderNumber`.
2. Use the template to perform an explicit `insert` in an import service.
3. Place both inside one application service.
4. Verify that they use the same mapping and transaction manager.

### Exercise 4 — Distinguishing the Three APIs

Write the same order list report in three ways: a repository returning aggregates, a projection returning root properties, and `JdbcTemplate` joining the customer table. Note the returned data, column count, and purpose of each approach.

## 13. Conclusion

**Use a repository for most per-aggregate CRUD** because it provides a domain-oriented abstraction, built-in CRUD, and readable derived queries. **Use JdbcAggregateTemplate when you need programmatic aggregate operations**, especially when you want explicit `insert`/`update` calls, work with an aggregate type passed at runtime, or implement a specialized persistence operation inside infrastructure or a custom repository fragment.

`JdbcAggregateTemplate` still follows Spring Data JDBC's aggregate mapping model. It is not a tool for arbitrary SQL, does not replace domain rules on its own, and is not a bulk API. When you need JOINs, aggregations, or reporting DTOs, use `JdbcTemplate`/`NamedParameterJdbcTemplate` or an appropriate projection.

Choose the API according to intent: repositories for aggregate CRUD contracts, the template for explicit and flexible aggregate operations, and direct JDBC SQL for custom queries or updates. Whichever approach you use, the aggregate root remains the place where domain invariants are protected.
