# Programming with the JdbcAggregateOperations Interface

Spring Data JDBC provides the `JdbcAggregateOperations` interface to operate directly on aggregates in the database. Instead of calling predefined repository methods, a service or custom repository fragment can use this interface to save, read, update, delete, and query aggregates in a domain-typed manner.

`JdbcAggregateOperations` is the abstraction for aggregate operations. Its standard implementation is `JdbcAggregateTemplate`, which Spring configures and manages as a bean. This interface operates at the aggregate root level: when saving or reading a root, Spring Data JDBC handles the child entities belonging to the aggregate according to the declared mapping.

This lesson covers how to inject the interface, how to choose among `save`, `insert`, and `update`, how to read and delete aggregates, how to build queries with `Query` and `Criteria`, and how to coordinate transactions and optimistic locking.

## 1. Where Does JdbcAggregateOperations Fit?

Spring Data JDBC offers several data access layers at different levels of abstraction:

| Component | Responsibility |
| --- | --- |
| `CrudRepository` / specialized repository | Repository API, derived queries, query methods, and per-aggregate abstraction |
| `JdbcAggregateOperations` | Interface for programmatic aggregate operations |
| `JdbcAggregateTemplate` | Implementation class of `JdbcAggregateOperations` |
| `JdbcTemplate` | Low-level JDBC API for executing SQL and working with `ResultSet` |

A repository is the natural choice when an application needs a stable data access contract with named finder methods. `JdbcAggregateOperations` is useful when a service or custom repository needs to invoke aggregate operations under dynamic programmatic conditions, or needs a general-purpose template API without writing CRUD SQL manually.

Unlike `JdbcTemplate`, `JdbcAggregateOperations` understands Spring Data JDBC metadata: aggregate roots, IDs, embedded objects, child entity collections, converters, and versions. When saving a `PurchaseOrder` with `OrderLine` items, the operation executes across the aggregate instead of requiring the application to write to each table separately.

## 2. Injecting the Interface via Spring

When a project has Spring Data JDBC configured with an appropriate `DataSource` and transaction infrastructure, Spring creates a `JdbcAggregateTemplate` bean. Because this class implements `JdbcAggregateOperations`, the application can inject the interface via constructor injection:

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateOperations;
import org.springframework.stereotype.Service;

@Service
public class OrderService {

    private final JdbcAggregateOperations aggregates;

    public OrderService(JdbcAggregateOperations aggregates) {
        this.aggregates = aggregates;
    }
}
~~~

Injecting by interface keeps the service coupled to the aggregate operations contract. There is no need to instantiate `JdbcAggregateTemplate` with `new` or manually wire converters, mapping context, dialect, and data access strategy.

If your application uses custom Spring Data JDBC configuration, verify that the template bean is registered and injectable via the interface. In standard setups, Spring manages these components.

### Commonly Used Packages

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateOperations;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.domain.Sort;
import org.springframework.transaction.annotation.Transactional;
~~~

`JdbcAggregateOperations` belongs to package `org.springframework.data.jdbc.core`. `Query` and `Criteria` belong to the Spring Data Relational packages. Do not confuse them with Spring Data JPA query APIs.

## 3. Aggregate Model Used in Examples

Suppose an order management system has `PurchaseOrder` as the aggregate root and a list of `OrderLine` child entities belonging to the order lifecycle.

~~~java
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public class PurchaseOrder {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    private List<OrderLine> lines = new ArrayList<>();

    protected PurchaseOrder() {
    }

    public PurchaseOrder(String status, List<OrderLine> lines) {
        this.status = status;
        this.lines = new ArrayList<>(lines);
    }

    public void markPaid() {
        this.status = "PAID";
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
}
~~~

Child entity:

~~~java
public record OrderLine(String sku, int quantity) {
}
~~~

Illustrative schema for PostgreSQL:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL REFERENCES purchase_orders(id),
    line_no INTEGER NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

`@MappedCollection` specifies the back-reference column `order_id` and key column `line_no` in the child table. `@Version` enables optimistic locking for the root. Table and column names must match the application's mapping and migrations.

When operating through `JdbcAggregateOperations`, pass the root type `PurchaseOrder.class`. Do not pass `OrderLine.class` to ask the template to save a child owned by this aggregate on its own.

## 4. Saving Aggregates with save

`save` is the general-purpose choice when the caller wants to persist an aggregate and let Spring Data JDBC decide between insert and update based on the entity's new/existing state.

~~~java
PurchaseOrder order = new PurchaseOrder(
    "NEW",
    List.of(
        new OrderLine("BOOK-01", 2),
        new OrderLine("PEN-02", 3)
    )
);

PurchaseOrder saved = aggregates.save(order);

Long orderId = saved.getId();
~~~

With a database-generated ID, the database assigns the root ID and Spring Data JDBC populates that value on the returned instance. Always use the object returned from `save`, especially since immutable entity models may require creating a new instance to hold the newly generated ID and version.

`save` persists the entire aggregate: the root and the child entities declared in the mapping. It does not update just a single property.

### How Does Spring Data Determine Whether an Entity Is New?

By default, Spring Data inspects the property annotated with `@Id`:

- If the ID is `null`, the entity is generally considered new.
- If a primitive numeric ID has the default value `0`, it is considered new.
- If the ID has a non-default value, it is generally considered an existing entity.

If an `@Version` property is present, Spring Data can use the version to detect newness: a `null` or `0` version indicates a new entity. If the entity implements `Persistable`, determining newness is delegated to `isNew()`.

This matters when the application assigns UUIDs or IDs before inserting. An already populated ID does not by itself prove that the row exists in the database. Choose an appropriate newness strategy—such as `@Version` or `Persistable`—or use an explicit `insert` operation when that matches your intent.

## 5. Distinguishing save, insert, and update

In addition to `save`, the template API provides specialized operations:

| Method | Meaning | When to Use |
| --- | --- | --- |
| `save(instance)` | Automatically chooses insert or update based on entity state | Standard persistence operations |
| `insert(instance)` | Always executes the insert path, bypassing newness checks | Caller knows the aggregate is new |
| `update(instance)` | Always executes the update path, bypassing newness checks | Caller knows the aggregate already exists |
| `upsert(instance)` | Inserts if no matching ID exists; updates if it does | Only when supported by version and dialect |

Example of explicit `insert`:

~~~java
PurchaseOrder created = aggregates.insert(newOrder);
~~~

Example of explicit `update`:

~~~java
PurchaseOrder current =
    aggregates.findById(orderId, PurchaseOrder.class);

if (current == null) {
    throw new IllegalArgumentException("Order not found: " + orderId);
}

current.markPaid();
PurchaseOrder updated = aggregates.update(current);
~~~

`insert` and `update` do not replace business validation. If a caller invokes `insert` for an already existing aggregate, the database may reject it due to a primary key or unique constraint violation. Calling `update` for a nonexistent aggregate does not turn the operation into an insert. Choose the method according to the actual state.

`save` has the same semantics as `CrudRepository.save`. `insert` and `update` skip the new/existing entity check and execute the exact operation specified.

### Saving an Existing Aggregate May Rewrite Child Entities

Spring Data JDBC does not maintain a persistence context to track fine-grained changes like some ORMs. It does not know the previous database state of the aggregate. When saving an existing aggregate, the default behavior is to delete referenced child entities, update the root, and re-insert the child entities according to the object's current state.

This means `save` and `update` are aggregate-level operations. Even if you only change one root property on an aggregate with a large collection, saving may still generate many SQL statements for child rows. Consider aggregate size and design reasonable aggregate boundaries; do not treat `JdbcAggregateOperations` as a single-column patch API.

### Upsert in Supported Versions

Recent versions of Spring Data Relational provide `upsert(instance)`. In Spring Data Relational 4.1, this operation requires an assigned ID and a dialect that supports native upsert, typically via `MERGE` or `INSERT ... ON CONFLICT`.

~~~java
PurchaseOrder stored = aggregates.upsert(orderWithAssignedId);
~~~

`upsert` inserts if no root row exists with that ID and updates if one does. This API does not support optimistic locking in the referenced 4.1 release. Use it only when your project's dependency version and database dialect support it; in older versions, the method may not exist.

## 6. Reading Aggregates

`findById` takes two arguments: the ID and the aggregate root class. Unlike `CrudRepository.findById`, this template method returns the object directly or `null` if not found.

~~~java
PurchaseOrder order =
    aggregates.findById(orderId, PurchaseOrder.class);

if (order == null) {
    throw new IllegalArgumentException("Order not found: " + orderId);
}
~~~

When loading the root, Spring Data JDBC also loads the aggregate's member components according to the mapping. The application does not need to query `order_lines` manually just to assemble the list of order lines.

### Finding All and Finding by IDs

~~~java
List<PurchaseOrder> all =
    aggregates.findAll(PurchaseOrder.class);

List<PurchaseOrder> selected =
    aggregates.findAllById(orderIds, PurchaseOrder.class);
~~~

These methods return collections of aggregate roots. An unbounded `findAll` can read a massive amount of data; avoid using it on large tables when you only need a subset of results.

### Sorting Results

~~~java
List<PurchaseOrder> newestFirst = aggregates.findAll(
    PurchaseOrder.class,
    Sort.by(Sort.Direction.DESC, "id")
);
~~~

`Sort` specifies ordering by mapped property. Confirm the actual property and column names in the entity mapping.

### Streaming Data

On supported APIs, `streamAll` returns a `Stream` to process aggregates sequentially:

~~~java
try (Stream<PurchaseOrder> stream =
        aggregates.streamAll(PurchaseOrder.class)) {
    stream.forEach(this::processOrder);
}
~~~

A stream may hold JDBC resources while being consumed. Close the stream with try-with-resources and do not retain it for use after the transaction or connection has ended. Streaming does not automatically turn processing into batch updates; if writes are needed, define clear transaction boundaries and a batching strategy.

## 7. Counting and Checking Existence

When you only need a count or existence check, do not load entire aggregates into Java:

~~~java
long totalOrders = aggregates.count(PurchaseOrder.class);

boolean exists =
    aggregates.existsById(orderId, PurchaseOrder.class);
~~~

These operations work at the aggregate root level and are suitable for existence checks or overall counts.

## 8. Deleting Aggregates

You can delete by root object or by ID:

~~~java
PurchaseOrder order =
    aggregates.findById(orderId, PurchaseOrder.class);

if (order != null) {
    aggregates.delete(order);
}
~~~

Or:

~~~java
aggregates.deleteById(orderId, PurchaseOrder.class);
~~~

Deleting by ID deletes the aggregate, including child entities belonging to it. You do not need to issue a separate delete command for each `OrderLine`.

Bulk deletion operations are also available in the API:

~~~java
aggregates.deleteAllById(orderIds, PurchaseOrder.class);
~~~

`deleteAll(PurchaseOrder.class)` deletes every aggregate of that type. This is a broad operation—invoke it only when business requirements explicitly call for deleting all data of that type.

If the root has `@Version`, deleting by root object can enforce version checking. `deleteById` does not have an object version to compare against, so it does not provide the same optimistic locking check as deleting a loaded aggregate.

## 9. Building Dynamic Queries with Query and Criteria

A key strength of the template API is building search conditions in code instead of composing method names or concatenating SQL strings. `Query` represents the SELECT query, while `Criteria` constructs the WHERE conditions.

Example finding orders with status `PAID`:

~~~java
import static org.springframework.data.relational.core.query.Criteria.where;

import org.springframework.data.relational.core.query.Query;

Query query = Query.query(
    where("status").is("PAID")
);

List<PurchaseOrder> paidOrders =
    aggregates.findAll(query, PurchaseOrder.class);
~~~

`where("status")` refers to the mapped property/column; `is("PAID")` creates an equality predicate. Parameters are handled through Spring Data's query mechanism without concatenating values into a SQL string.

### Combining Multiple Conditions

Example finding orders with status `PAID` and an ID above a threshold:

~~~java
Query query = Query.query(
    where("status").is("PAID")
        .and("id").greaterThan(1000L)
);

List<PurchaseOrder> result =
    aggregates.findAll(query, PurchaseOrder.class);
~~~

You can use comparison operators supported by `Criteria`, such as `is`, `isNull`, `isNotNull`, `greaterThan`, `greaterThanOrEquals`, `lessThan`, `lessThanOrEquals`, `like`, `not`, and `in`.

Example with a `LIKE` condition:

~~~java
Query query = Query.query(
    where("status").like("P%")
);
~~~

`Criteria.like` uses the pattern exactly as passed; it does not automatically turn the pattern into a prefix or substring match the way derived query keywords `StartingWith` or `Containing` do. If using wildcards, prepare the pattern according to your intent.

### Finding a Single Aggregate with Query

~~~java
Optional<PurchaseOrder> result = aggregates.findOne(
    Query.query(where("status").is("PAID")),
    PurchaseOrder.class
);
~~~

`findOne` returns an `Optional`. It fits when the query yields at most one result by design. If multiple rows match the condition, the API may throw `IncorrectResultSizeDataAccessException`; do not use `findOne` for conditions that can match multiple orders.

### Count and Exists with Query

~~~java
long paidCount = aggregates.count(
    Query.query(where("status").is("PAID")),
    PurchaseOrder.class
);

boolean hasOpenOrders = aggregates.exists(
    Query.query(where("status").is("OPEN")),
    PurchaseOrder.class
);
~~~

These operations check datasets against conditions without loading the entire aggregate list into the application.

## 10. Transactions Across Multiple Operations

A use case may involve multiple aggregate operations or additional repository calls. Place transaction boundaries at the service boundary using `@Transactional`.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final JdbcAggregateOperations aggregates;
    private final OrderAuditRepository audits;

    public OrderApplicationService(
            JdbcAggregateOperations aggregates,
            OrderAuditRepository audits) {
        this.aggregates = aggregates;
        this.audits = audits;
    }

    @Transactional
    public PurchaseOrder markPaid(Long id) {
        PurchaseOrder order =
            aggregates.findById(id, PurchaseOrder.class);

        if (order == null) {
            throw new IllegalArgumentException("Order not found: " + id);
        }

        order.markPaid();

        PurchaseOrder saved = aggregates.update(order);
        audits.save(OrderAudit.statusChanged(id, "PAID"));

        return saved;
    }
}
~~~

If updating the order or writing the audit fails and an exception triggers rollback, all changes in the same transaction roll back together. This assumes they share the same transaction manager and `DataSource` and that exceptions are not swallowed in a way that allows the transaction to commit.

`@Transactional` must be invoked through a Spring proxy according to the application's transaction management setup. In typical proxy-based configurations, self-invocation of a transactional method within the same instance bypasses the proxy and does not activate the annotation the way an external call from another bean does.

### Do Not Detach Children from the Aggregate Just to Call the Template

If `OrderLine` belongs to the lifecycle of `PurchaseOrder`, operate on it through the root. Do not look up the root ID and manually insert or update children with separate SQL. Doing so forces the service to manage foreign keys manually and can break the aggregate's consistency boundary.

If an object has an independent lifecycle, identity, and workflow, evaluate modeling it as a separate aggregate; then template operations on its own root make sense.

## 11. Optimistic Locking with @Version

If multiple requests can update the same order concurrently, `@Version` helps detect overwrites of another request's changes.

In our example, the root has:

~~~java
@Version
private Long version;
~~~

Spring Data JDBC includes the current version in the update condition. If another request has already updated the row and incremented the version, a concurrent request carrying the stale version cannot update it as though nothing changed; the framework throws `OptimisticLockingFailureException`.

Example handling in a service:

~~~java
try {
    return aggregates.update(order);
} catch (OptimisticLockingFailureException ex) {
    throw new OrderConflictException(
        "Order was changed by another operation", ex
    );
}
~~~

Do not increment the version manually in Java expecting the template to interpret it. Let Spring Data's mechanism manage the version and handle conflicts in business logic via the exception.

Optimistic locking applies at the aggregate root and helps detect contention during versioned updates and deletes. `upsert` in Spring Data Relational 4.1 currently does not support optimistic locking, so do not use `upsert` if the use case depends on version checks.

## 12. Using JdbcAggregateOperations in Custom Repositories

A custom repository fragment can use `JdbcAggregateOperations` to add operations that a repository interface cannot conveniently express.

Example custom contract:

~~~java
public interface PurchaseOrderRepositoryCustom {
    PurchaseOrder markPaid(Long id);
}
~~~

Implementation:

~~~java
import org.springframework.data.jdbc.core.JdbcAggregateOperations;
import org.springframework.stereotype.Component;
import org.springframework.transaction.annotation.Transactional;

@Component
public class PurchaseOrderRepositoryCustomImpl
        implements PurchaseOrderRepositoryCustom {

    private final JdbcAggregateOperations aggregates;

    public PurchaseOrderRepositoryCustomImpl(
            JdbcAggregateOperations aggregates) {
        this.aggregates = aggregates;
    }

    @Override
    @Transactional
    public PurchaseOrder markPaid(Long id) {
        PurchaseOrder order =
            aggregates.findById(id, PurchaseOrder.class);

        if (order == null) {
            throw new IllegalArgumentException("Order not found: " + id);
        }

        order.markPaid();
        return aggregates.update(order);
    }
}
~~~

The main repository can compose the fragment:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface PurchaseOrderRepository
        extends CrudRepository<PurchaseOrder, Long>,
                PurchaseOrderRepositoryCustom {
}
~~~

The implementation class name and how Spring discovers fragments must follow the repository fragment conventions of your project's Spring Data version. The key idea is that the custom implementation uses the same Spring-configured template bean, preserving mappings, converters, and transaction infrastructure.

## 13. Comparing Repository, JdbcAggregateOperations, and JdbcTemplate

| Need | Consider Using |
| --- | --- |
| Standard CRUD and a clear repository interface | `CrudRepository` / `ListCrudRepository` |
| Derived queries by method name | Repository |
| Query methods with `@Query` | Repository |
| Programmatic aggregate operations in a service or custom fragment | `JdbcAggregateOperations` |
| Dynamic `Query`/`Criteria` mapped into aggregates | `JdbcAggregateOperations` |
| Low-level custom SQL, custom joins/projections, or non-aggregate operations | `JdbcTemplate` / JDBC client |

`JdbcAggregateOperations` is not a replacement for every repository. If a repository interface already expresses the use case cleanly, keep using it. The template API shines when logic needs to construct dynamic queries or when a custom repository wants to reuse aggregate persist/load mechanics.

`JdbcTemplate` gives more direct control over SQL, but the caller must manage SQL statements, parameter binding, row mapping, and table relationships manually. Do not use the aggregate template for complex reporting SQL simply because it is part of Spring Data JDBC; choose the right API for the job.

## 14. Limitations to Keep in Mind

- The template operates by aggregate root and mapping metadata; it is not a tool for arbitrary single-column patches.
- `findById` returns `null` when not found, not `Optional`.
- `findAll` can load all aggregates; be mindful of dataset size.
- `streamAll` must be closed and consumed while JDBC resources remain valid.
- `findOne(Query, Class)` expects at most one result; multiple results trigger an incorrect result size error.
- Pagination is generally a better fit for repositories. Some `findAll(..., Pageable)` overloads on the template were deprecated in Spring Data Relational 4.0 and scheduled for removal.
- `upsert` is only available in recent versions (from 4.1), requires an assigned ID and dialect support, and currently lacks optimistic locking.
- `save`/`update` rewrite aggregate state; child entities may be deleted and re-inserted, so write cost depends on aggregate size.

### Do Not Use the Template to Bypass Aggregate Boundaries

If `Customer` is a separate aggregate and `PurchaseOrder` only holds a customer ID, saving an order does not mean the template will automatically save `Customer`. An operation on a root only manages components belonging to that aggregate root. Use service/application workflows to coordinate multiple aggregates and define appropriate transactions.

## 15. Testing Template Operations

Integration tests can verify that the template saves and restores both root and children:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.data.jdbc.core.JdbcAggregateOperations;

@DataJdbcTest
class JdbcAggregateOperationsTest {

    @Autowired
    JdbcAggregateOperations aggregates;

    @Test
    void insertsAndLoadsWholeAggregate() {
        PurchaseOrder order = new PurchaseOrder(
            "NEW",
            List.of(
                new OrderLine("BOOK-01", 2),
                new OrderLine("PEN-02", 3)
            )
        );

        PurchaseOrder saved = aggregates.insert(order);

        assertThat(saved.getId()).isNotNull();

        PurchaseOrder loaded =
            aggregates.findById(saved.getId(), PurchaseOrder.class);

        assertThat(loaded).isNotNull();
        assertThat(loaded.getStatus()).isEqualTo("NEW");
        assertThat(loaded.getLines()).hasSize(2);
    }
}
~~~

The example assumes migrations have created the tables and the test configuration provides a suitable database. When using a versioned entity, you can verify that the version increments after an update and that two concurrent updates cannot both succeed with the same old version.

Scenarios worth testing:

1. Insert a new aggregate and verify the ID is generated.
2. Read the aggregate and verify child entities are restored.
3. Update the root and verify changes are persisted.
4. Delete the root and verify aggregate children are deleted.
5. Call `findById` with a nonexistent ID and verify a `null` result.
6. Use `Query`/`Criteria` with appropriate predicates and verify the result set.
7. If using `@Version`, test optimistic locking conflicts.

## 16. Common Mistakes When Programming with the Template

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Unable to inject `JdbcAggregateOperations` | Spring Data JDBC not configured or template bean altered | Check starter, `DataSource`, and JDBC configuration |
| `findById` returns `null` | No root exists with that ID | Handle the not-found case before updating |
| `save` inserts instead of updating | Entity is detected as new | Check ID, version, or `Persistable.isNew` |
| `save` updates instead of inserting | ID already has a value and entity is detected as existing | Use `insert` when known to be new or fix newness strategy |
| `update` does not create a new row | `update` always performs an update | Use `insert` or `save` matching actual state |
| Duplicate key on `insert` | Aggregate already exists or assigned ID collides | Check IDs and constraints |
| Children rewritten on `update` | Spring Data JDBC synchronizes the whole aggregate | Evaluate aggregate size and update frequency |
| `findOne` fails with multiple results | Query condition is not unique | Use `findAll` or add unique predicates |
| Data does not roll back together | Operations do not share the same transaction/`DataSource` | Place transaction on the service and verify transaction manager |
| `OptimisticLockingFailureException` | Version changed by another transaction | Reload aggregate and handle business conflict |
| Query not sorted as expected | `Sort` uses wrong property or no `Sort` specified | Specify `Sort` and verify mapping |

## 17. Operation Selection Guide

| Intent | Suggested API |
| --- | --- |
| Save new or existing aggregate without choosing branch manually | `save(instance)` |
| Definitely a new aggregate | `insert(instance)` |
| Definitely an existing aggregate | `update(instance)` |
| Insert or update via native upsert | `upsert(instance)` if version/dialect supports it |
| Read one root by ID | `findById(id, Root.class)` |
| Read multiple roots by dynamic conditions | `findAll(query, Root.class)` |
| Count results matching conditions | `count(query, Root.class)` |
| Check whether results exist | `exists(query, Root.class)` |
| Delete root and aggregate members | `delete(root)` or `deleteById(id, Root.class)` |

Before choosing an API, determine whether the aggregate is new or existing, whether IDs are generated or pre-assigned, whether optimistic locking is used, how many rows the query may return, and whether the operation must share a transaction with other business steps.

## 18. Practice Exercises

### Exercise 1 — Injecting the Interface

Create a service that accepts `JdbcAggregateOperations` via constructor injection. Explain why the service can accept the interface while the actual bean is `JdbcAggregateTemplate`.

### Exercise 2 — Save and Newness

Create an aggregate with an auto-generated ID. Call `save` before and after the aggregate exists. Observe the ID and SQL. Try an entity with a pre-assigned ID to explore the role of `@Version` or `Persistable`.

### Exercise 3 — Insert and Update

Call `insert` for a new aggregate, then call `update` to change its status. Intentionally call `insert` a second time and record the database error. Try `update` with a nonexistent ID and observe the behavior.

### Exercise 4 — Query and Criteria

Build a `Query` to find orders by status, combined with an ID predicate. Use `findAll`, `findOne`, `count`, and `exists` to compare their return types.

### Exercise 5 — Transactions

Inside a `@Transactional` method, update an order and then write an audit record. Trigger an error during the audit step and verify both changes roll back when sharing the same transaction manager.

### Exercise 6 — Optimistic Locking

Load two instances of the same aggregate in two separate transactions. Update the first instance, then attempt to update the second instance with the stale version. Verify the conflict and design how to notify the caller.

### Exercise 7 — Custom Repository Fragment

Create a custom repository fragment with a business method `markPaid`. Use `JdbcAggregateOperations` to load and update the root within the same transaction.

## 19. Official References

- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): how the template persists aggregates, new-entity detection, dynamic queries, and optimistic locking.
- [Spring Data Relational — JdbcAggregateOperations API](https://docs.spring.io/spring-data/jdbc/docs/current/api/org/springframework/data/jdbc/core/JdbcAggregateOperations.html): list of interface methods and return types.
- [Spring Data Relational — JdbcAggregateTemplate API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html): the template implementation class.
- [Spring Data Relational — Query API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Query.html): programmatic query structure.
- [Spring Data Relational — Criteria API](https://docs.spring.io/spring-data/relational/reference/api/java/org/springframework/data/relational/core/query/Criteria.html): condition operators for WHERE clauses.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): how to use `@Transactional` to define transaction boundaries.

`JdbcAggregateOperations` provides a direct API for working with aggregates using Spring Data JDBC's mapping. Inject the bean via constructor, choose `save`, `insert`, or `update` based on entity state, use `Query`/`Criteria` for dynamic conditions, and place transactions at business boundaries when coordinating multiple operations. Remember that the template persists an aggregate as a unit; child entities and versions are processed according to the mapping, so how you design your aggregates determines both consistency and write cost.
