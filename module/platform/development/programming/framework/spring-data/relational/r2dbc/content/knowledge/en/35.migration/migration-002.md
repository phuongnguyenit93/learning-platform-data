# Replacing ORM Assumptions with Explicit Queries and Write Boundaries

Spring Data Relational R2DBC works with a relational data model and reactive APIs, but it does not provide a full unit-of-work mechanism like a traditional ORM. When migrating from JPA/Hibernate to R2DBC, assumptions such as a persistence context, dirty checking, lazy loading, entity proxies, and object-graph cascades are no longer the foundation for application design.

Instead, the application must explicitly express what data is read, which queries load required relationships, which operations persist changes, and which transaction surrounds each use case. Repositories, `R2dbcEntityTemplate`, or `DatabaseClient` execute queries; application services orchestrate steps; aggregate roots define the boundary of data protected together; and database constraints protect final integrity.

This approach does not mean writing raw SQL for every operation. Spring Data R2DBC still provides repositories, derived queries, mapping metadata, entity callbacks, and abstractions like `Criteria`. What matters is not relying on ORM behaviors that Spring Data Relational does not promise.

This lesson explains how to replace ORM assumptions with explicit queries and write boundaries, covering aggregate design, reading data with projections/joins, avoiding N+1 queries, intentional updates, reactive transaction management, concurrency, and testing.

## 1. Differences Between ORM Unit-of-Work and Spring Data Relational

In an ORM such as JPA/Hibernate, a persistence context can track loaded entities. When fields change, dirty checking detects differences and the ORM generates an UPDATE on flush. Relationships can be lazily loaded via proxies; cascades can propagate operations from a root through an object graph according to mappings.

Spring Data Relational R2DBC has a different model. Repositories operate on entities through concrete persistence commands. Modifying a Java object does not automatically produce an UPDATE. Relationships must be loaded with explicit queries. Aggregate boundaries affect how Spring Data persists related data.

| ORM Assumption | Spring Data R2DBC Approach |
| --- | --- |
| Entities are managed inside a persistence context. | Entities are typically data objects; there is no JPA-style change-tracking session. |
| Dirty checking automatically detects modified fields. | Call repository/template `save` or an explicit `UPDATE` statement. |
| Lazy loading automatically queries when a relation is accessed. | Load related data with explicit queries/repositories. |
| Object graphs are navigated through proxies. | Use joins, projections, or multiple intentional queries. |
| Cascades automatically propagate persist/remove across an object graph. | Define explicit aggregate boundaries, write commands, and foreign keys. |
| Flush synchronizes changes in the persistence context. | Reactive publishers execute operations upon subscription; there is no ORM session flush. |
| A loaded object is always the latest state in the session. | Each query may read fresh state; use transactions/locking when consistency is required. |

Spring Data Relational still offers mapping metadata, repository abstractions, and entity callbacks. The difference lies in the state management model and how write operations are executed.

## 2. Thinking in Aggregates and Data Boundaries

An aggregate is a cluster of objects managed as a consistent unit in the domain. The aggregate root is the entry point for modifying that cluster of data. In Spring Data Relational, aggregate design determines which objects are persisted alongside the root and which objects are referenced only by ID.

For example, an order consists of:

- `Order`: aggregate root.
- `OrderLine`: line item belonging to the order.
- `Product`: another aggregate, referenced via `productId`.
- `Customer`: another aggregate, referenced via `customerId`.

Diagram:

~~~mermaid
flowchart TD
    O[Order aggregate root] --> L1[OrderLine 1]
    O --> L2[OrderLine 2]
    O --> L3[OrderLine 3]
    L1 --> P1[productId reference]
    L2 --> P2[productId reference]
    L3 --> P3[productId reference]
    O --> C[customerId reference]
~~~

`OrderLine` belongs to the lifecycle of `Order`. `Product` and `Customer` have their own lifecycles. There is no need to load the entire `Product` object just to save an order line; storing `productId` is usually sufficient if the use case only needs a reference.

### An Aggregate Root Is Not an Arbitrary Object Graph

Do not cram every database relationship into a giant object graph expecting the repository to load and synchronize everything automatically. An aggregate should be sized to match business consistency rules.

For example, changing the quantity of an `OrderLine` may belong to the transaction updating an `Order`. Changing a `Product` name is typically a separate use case and should not force loading or saving every `Order` containing that `Product`.

### Use IDs for Cross-Aggregate References

Example:

~~~java
@Table("orders")
public record Order(
    @Id UUID id,
    UUID customerId,
    String status,
    BigDecimal total
) {}
~~~

`Order` holds `customerId`. When a read use case needs to display the customer's name, it can query `CustomerRepository` or use a join projection. Do not assume a `Customer` proxy will be lazily loaded when calling `order.customer()`.

## 3. Mapping Aggregates with Spring Data Relational

Spring Data Relational supports mapping objects belonging to an aggregate. For example, an `Order` with a list of `OrderLine` items:

~~~java
@Table("orders")
public record Order(
    @Id UUID id,
    UUID customerId,
    String status,
    @MappedCollection(idColumn = "order_id", keyColumn = "line_no")
    List<OrderLine> lines
) {}

public record OrderLine(
    UUID productId,
    Integer quantity,
    BigDecimal unitPrice
) {}
~~~

In this example, `Order` is the root; `OrderLine` is stored in a table with an `order_id` column pointing to the root and `line_no` acting as the key/index if the schema is designed accordingly.

Illustrative schema:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    status VARCHAR(30) NOT NULL,
    total NUMERIC(14, 2) NOT NULL
);

CREATE TABLE order_lines (
    order_id UUID NOT NULL REFERENCES orders(id),
    line_no INTEGER NOT NULL,
    product_id UUID NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no)
);
~~~

Column names, key columns, and mappings must match the actual schema. Inspect the SQL generated for inserts and updates on the specific Spring Data Relational version you are using.

### Understanding Aggregate Save Semantics

When saving an aggregate that owns dependent collections, Spring Data Relational must synchronize the dependent rows according to the mapping. For collections mapped with `@MappedCollection`, updating the root can trigger replacing or synchronizing dependent rows; the concrete implementation may delete and re-insert related rows rather than tracking individual children like ORM dirty checking.

This has several consequences:

- Do not treat replacing a single element in a `List` as an independent `UPDATE` statement.
- Consider the number of child rows inside an aggregate.
- Understand the impact of saving the root on dependent rows.
- Do not turn huge collections into a single aggregate.
- Test generated SQL and performance when collections are large or updated frequently.

If you need to update a specific line under high concurrency, an explicit `UPDATE` statement on `order_lines` may be more appropriate than re-saving the entire aggregate. When doing so, maintain `Order` invariants and transaction boundaries explicitly.

## 4. No Dirty Checking: Persist Changes Explicitly

In JPA, a managed entity can have its fields mutated and the ORM detects those changes at flush time. With Spring Data R2DBC, mutating an object in memory does not automatically write to the database.

Example:

~~~java
return productRepository.findById(id)
    .doOnNext(product -> {
        // Mutating an object in memory does not automatically issue an UPDATE.
        product.setName("New name");
    });
~~~

The snippet above only emits the loaded entity. It does not save the change. With immutable records, fields cannot be mutated directly; you must create a new instance and call `save` or a corresponding update command.

Explicit approach with a mutable entity:

~~~java
return productRepository.findById(id)
    .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
    .flatMap(product -> {
        product.setName(command.name());
        return productRepository.save(product);
    });
~~~

With an immutable record:

~~~java
return productRepository.findById(id)
    .switchIfEmpty(Mono.error(new ProductNotFoundException(id)))
    .flatMap(current -> {
        ProductEntity updated = new ProductEntity(
            current.id(),
            command.name(),
            current.price(),
            current.status(),
            current.version()
        );
        return productRepository.save(updated);
    });
~~~

Calling `save` is an explicit write boundary. No changes are persisted merely because an object was loaded or held in a local variable.

### When to Use `save` vs. Explicit `UPDATE`?

Use `repository.save` when persisting an entity/aggregate using standard Spring Data mapping. Use an explicit `UPDATE` statement when:

- Only a few columns need to change.
- You want to avoid loading the entity before updating.
- An atomic database-side operation is required.
- You need control over the `WHERE` predicate and affected row count.
- You are processing large data volumes or bulk updates.

An explicit `UPDATE` statement must have tight predicates—especially ID, tenant, and version if optimistic concurrency is required.

## 5. Creating and Saving an Aggregate in a Single Use Case

An order creation use case may need to check the customer, verify products, compute the total amount, and save the order together with its lines. The application service orchestrates all of those steps.

Example:

~~~java
public Mono<Order> createOrder(CreateOrderCommand command) {
    return customerRepository.findById(command.customerId())
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(command.customerId())
        ))
        .flatMap(customer ->
            validateAndPriceLines(command.lines())
                .map(lines -> orderFactory.create(customer, lines))
        )
        .flatMap(orderRepository::save);
}
~~~

This is an illustrative skeleton. If `validateAndPriceLines` queries multiple products, choose an appropriate query strategy and ensure write steps execute inside the required transaction.

Do not call `subscribe` inside a service:

~~~java
orderRepository.save(order).subscribe();
return Mono.just(order);
~~~

This detaches the write operation from the use case's publisher, causing callers not to wait for completion and errors not to propagate along the pipeline. Always return the composed publisher so WebFlux or the caller manages subscription.

## 6. Reading Relational Data with Explicit Queries

There is no automatic lazy loading. If an endpoint needs an order along with the customer name and product name, explicitly decide what data to read and construct the appropriate queries.

There are three common approaches:

1. Multiple queries across repositories, composed reactively.
2. A single SQL `JOIN` mapped to a projection.
3. Querying the root first, then loading child/reference records by batching IDs.

Choose based on result size, number of round trips, transaction consistency, and SQL complexity.

### Intentional Multiple Queries

Example fetching an order and then its customer:

~~~java
public Mono<OrderDetails> getOrder(UUID orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order ->
            customerRepository.findById(order.customerId())
                .map(customer -> new OrderDetails(
                    order.id(),
                    order.status(),
                    customer.name()
                ))
        );
}
~~~

This approach is readable and reuses separate repositories. However, if a list endpoint returns 100 orders and calls `customerRepository.findById` for each one, the application can trigger N+1 queries.

## 7. Avoiding N+1 with Joins or Batch Fetching

N+1 happens when the application executes one query to fetch N records and then runs an additional query per record to fetch related data.

Inefficient example:

~~~java
return orderRepository.findRecentOrders()
    .flatMap(order ->
        customerRepository.findById(order.customerId())
            .map(customer -> toSummary(order, customer))
    );
~~~

If there are 100 orders, this path can execute 1 orders query and up to 100 customer queries. `flatMap` may run several queries concurrently, but it does not reduce the total query count.

### Approach 1: JOIN and Projection

~~~sql
SELECT
    o.id AS order_id,
    o.status AS order_status,
    c.id AS customer_id,
    c.name AS customer_name
FROM orders o
JOIN customers c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.id;
~~~

Projection:

~~~java
public record OrderSummary(
    UUID orderId,
    String orderStatus,
    UUID customerId,
    String customerName
) {}
~~~

Execute via `DatabaseClient` and map each row:

~~~java
return databaseClient.sql("""
    SELECT
        o.id AS order_id,
        o.status AS order_status,
        c.id AS customer_id,
        c.name AS customer_name
    FROM orders o
    JOIN customers c ON c.id = o.customer_id
    WHERE o.status = :status
    ORDER BY o.id
    """)
    .bind("status", status)
    .map((row, metadata) -> new OrderSummary(
        row.get("order_id", UUID.class),
        row.get("order_status", String.class),
        row.get("customer_id", UUID.class),
        row.get("customer_name", String.class)
    ))
    .all();
~~~

`JOIN` lets the database fetch related data in a single query and return the exact shape needed for the use case. There is no need to hydrate an entire entity graph if the API only needs a summary.

### Approach 2: Batch Fetching by ID Set

If you need to keep separate repositories and the relationship points to many customers:

1. Fetch the list of orders.
2. Collect the distinct `customerId` values.
3. Query customers using a single `IN` condition.
4. Build a `Map` of `customerId` → `Customer`.
5. Combine results in memory.

Conceptual example:

~~~java
return orderRepository.findRecentOrders()
    .collectList()
    .flatMapMany(orders -> {
        List<UUID> customerIds = orders.stream()
            .map(Order::customerId)
            .distinct()
            .toList();

        return customerRepository.findAllById(customerIds)
            .collectMap(Customer::id)
            .flatMapMany(customers ->
                Flux.fromIterable(orders)
                    .map(order -> toSummary(
                        order,
                        customers.get(order.customerId())
                    ))
            );
    });
~~~

This reduces queries from N+1 down to one orders query and one customers query, though the `collectList` example holds all orders in memory. For large results, paginate or process in chunks.

### Choosing Between JOIN and Batch Fetch

- `JOIN` fits when the returned data has clear relationships and the query can be optimized with indexes.
- Batch fetching fits when preserving repository boundaries or when data comes from distinct queries.
- For large datasets, paginate the root first and then batch-fetch children for each page.
- Avoid uncontrolled one-to-many `JOIN` queries that multiply rows and break pagination semantics.

## 8. Projections Instead of Loading Full Entities

A use case needing only a few fields does not need to load a full entity. Projections reduce data transferred from the database and clarify the read contract.

For example, an order list needing only ID, status, and total:

~~~java
public record OrderListItem(
    UUID id,
    String status,
    BigDecimal total
) {}
~~~

Custom query:

~~~java
@Query("""
    SELECT id, status, total
    FROM orders
    WHERE customer_id = :customerId
    ORDER BY id DESC
    """)
Flux<OrderListItem> findOrderList(UUID customerId);
~~~

How projections map through repositories depends on the projection type and Spring Data version. If a query uses aliases or complex expressions, `DatabaseClient` provides explicit mapping.

A projection is not a managed entity and should not be passed to `save` if it does not represent the full persistence model.

### Dedicated Read Models for Screens

A screen may need aggregated data from multiple tables. Creating a dedicated read DTO or projection is usually clearer than loading an aggregate and invoking multiple relationship getters.

Read models can be tailored to each read use case's query. Write models still preserve aggregate boundaries to protect invariants when mutating data.

## 9. Loading Many-to-Many Relationships Explicitly

Suppose `Product` and `Tag` have a many-to-many relationship via `product_tags`. Do not assume accessing `product.tags` triggers a lazy query.

You can use a `JOIN`:

~~~sql
SELECT
    p.id AS product_id,
    p.name AS product_name,
    t.id AS tag_id,
    t.name AS tag_name
FROM products p
LEFT JOIN product_tags pt ON pt.product_id = p.id
LEFT JOIN tags t ON t.id = pt.tag_id
WHERE p.id = :productId
ORDER BY t.name;
~~~

The `JOIN` returns one row per tag; if a product has no tags, `LEFT JOIN` still returns a row with null tag columns. The mapper must collapse the rows into a single DTO containing the list of tags.

For a list of many products, group rows by `productId` or run two queries: fetch the product page, then fetch all tags for that list of product IDs. Do not query tags individually per product.

## 10. Partial Updates with Explicit UPDATE Statements

If only `status` changes, there is no need to read the entire entity and call `save`:

~~~java
@Modifying
@Query("""
    UPDATE orders
    SET status = :status
    WHERE id = :id
    """)
Mono<Integer> updateStatus(UUID id, String status);
~~~

Service:

~~~java
public Mono<Void> changeStatus(UUID id, String status) {
    return orderRepository.updateStatus(id, status)
        .flatMap(rows -> {
            if (rows == 0) {
                return Mono.error(new OrderNotFoundException(id));
            }
            return Mono.empty();
        });
}
~~~

This example assumes the repository method returns the affected row count as `Mono<Integer>`. Supported return types depend on the Spring Data R2DBC version and how modifying queries are declared. Check your project's API version.

Direct update statements have these characteristics:

- No need to hydrate the full entity.
- Does not automatically run entity lifecycle callbacks along the `save` path.
- Does not automatically apply mapper/service logic.
- Audit fields must be updated explicitly if no corresponding mechanism applies.
- Must check `rowsUpdated` to detect non-existent IDs.
- Must include version/tenant predicates if business rules require them.

Do not treat an explicit `UPDATE` as a replacement for all domain logic. The application service still needs to validate allowed state transitions and permissions.

## 11. Conditional Updates and Optimistic Locking

If two requests update the same order concurrently, the later operation can overwrite the earlier change. A version field can be used to detect conflicts.

Entity:

~~~java
@Table("orders")
public record Order(
    @Id UUID id,
    String status,
    BigDecimal total,
    @Version Long version
) {}
~~~

Spring Data Relational supports optimistic locking via `@Version` on supported `save` operations. When the stored version differs from the entity's version, the operation can raise `OptimisticLockingFailureException`.

With an explicit SQL `UPDATE`, include the version in the `WHERE` predicate and increment it:

~~~sql
UPDATE orders
SET status = :status,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

If `rowsUpdated` is 0, either the record does not exist or the version has changed. Depending on the API, an additional query may be needed to distinguish not-found from conflict. Never return success if zero rows were updated.

### Checking State Transitions

Some statuses only allow transitions along a business state graph. For instance, `PAID` cannot revert to `DRAFT`. Do not only validate that the requested status is a valid enum value; validate the transition from the current state.

The current status condition can be placed directly in the `UPDATE`:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = version + 1
WHERE id = :id
  AND status = :expectedStatus
  AND version = :expectedVersion;
~~~

This ensures the race condition check happens atomically at the database. The service must translate `rowsUpdated = 0` into conflict or not-found according to the API contract.

## 12. Deleting Data and Foreign Keys

Do not assume calling delete on a root automatically deletes all related objects like JPA cascade remove. Behavior depends on aggregate mapping and database schema.

For relationships owned within an aggregate, Spring Data Relational has its own aggregate persistence semantics. For cross-aggregate relationships, define deletion behavior explicitly and design foreign keys accordingly:

- `ON DELETE RESTRICT`/`NO ACTION` to prevent deletion while references still exist.
- `ON DELETE CASCADE` if the database is permitted to delete dependent rows automatically by domain rules.
- Delete dependents with explicit statements inside the same transaction when required.
- Soft delete if history or auditing must be retained.

Example deleting an order and its lines explicitly:

~~~java
public Mono<Void> deleteOrder(UUID orderId) {
    return transaction.transactional(
        orderLineRepository.deleteByOrderId(orderId)
            .then(orderRepository.deleteById(orderId))
    );
}
~~~

This snippet assumes the repository methods are implemented and share the same R2DBC `ConnectionFactory`/transaction manager. If the foreign key uses `ON DELETE CASCADE`, a separate child delete statement may not be necessary. Pick one clear owner for deletion rules.

Never delete a `Product` merely because an `OrderLine` references its `productId`. `Product` is a separate aggregate with its own lifecycle.

## 13. Use-Case Transaction Boundaries

A transaction should wrap a single use case requiring atomicity, not a large object graph just because an ORM previously held a long session.

For example, marking an order `PAID` requires:

1. Updating order status.
2. Recording the payment entry.
3. Writing an audit/event record in the same database if needed.
4. Committing all or rolling back all.

You can use `@Transactional` on a service method returning a reactive type:

~~~java
@Service
public class PaymentService {

    @Transactional
    public Mono<Void> markPaid(UUID orderId, Payment payment) {
        return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order -> validateCanPay(order, payment))
            .flatMap(order -> orderRepository.save(order.markPaid()))
            .then(paymentRepository.save(payment))
            .then();
    }
}
~~~

With reactive transactions, the transaction context flows through Reactor Context and publishers. The method must return the publisher so Spring can manage the transaction. If the method calls `subscribe` independently, that work can execute outside the transaction.

### TransactionalOperator

You can control transactions more explicitly inside a reactive chain:

~~~java
public Mono<Void> markPaid(UUID orderId, Payment payment) {
    Mono<Void> work = orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> validateCanPay(order, payment))
        .flatMap(order -> orderRepository.save(order.markPaid()))
        .then(paymentRepository.save(payment))
        .then();

    return transactionalOperator.transactional(work);
}
~~~

`TransactionalOperator` is helpful when the transaction boundary is part of explicit composition or when choosing exactly which publisher belongs to the transaction.

### One Transaction Manager Per ConnectionFactory

`R2dbcTransactionManager` manages transactions for its corresponding `ConnectionFactory`. If the application has multiple databases/`ConnectionFactory` beans, each resource needs its own transaction manager. A reactive transaction does not automatically create a distributed transaction across multiple databases.

## 14. Do Not Use Long Transactions Instead of Aggregate Design

Do not open a transaction at the start of a request and keep it open while:

- Calling an external HTTP service.
- Waiting for user confirmation.
- Processing large files.
- Sending emails or webhooks.
- Running a long-running import task.

Long transactions hold connections and can retain locks, increasing contention. Perform steps that do not need a transaction before or after the transaction boundary, and keep a short transaction around the database updates requiring atomicity.

If messages must be published after commit, a transactional outbox is usually better than sending messages directly inside a transaction. Write the outbox record in the same transaction as the domain change; a worker reads the outbox after commit and dispatches messages with retry/idempotency.

## 15. Read Consistency Across Multiple Queries

A use case that reads with multiple queries can observe different database states if another transaction commits between queries.

Example:

1. Query `Order`.
2. Query `Customer`.
3. Query `OrderLines`.

If these queries run outside a transaction, results may not reflect the same snapshot. Depending on the database and isolation level, a transaction can provide stronger read consistency.

Not every endpoint needs a read transaction. For dashboard data that tolerates eventual consistency, independent queries can be suitable. For financial reports or business decisions requiring a consistent snapshot, choose an appropriate transaction/isolation level or a single join query.

### JOINs Can Help Consistency and Reduce Round Trips

A join query typically observes data within a single statement snapshot under database semantics while reducing round trips. However, one-to-many joins can duplicate rows and complicate pagination.

Choose between a single join query and multiple queries based on consistency requirements, data size, and query plans.

## 16. Pagination When Reading Aggregates and Relationships

Do not paginate directly over a one-to-many `JOIN` result when the goal is to paginate aggregate roots. An order with 10 lines produces 10 joined rows; `LIMIT 20` may cover only two orders instead of 20 orders.

One approach:

1. Query a page of order IDs with a stable sort.
2. Query order details for that list of IDs.
3. Query lines for all order IDs in the page.
4. Group lines by `orderId` and build response DTOs.

Conceptual example:

~~~java
return orderRepository.findPageIds(pageable)
    .collectList()
    .flatMapMany(orderIds ->
        orderRepository.findAllById(orderIds)
            .collectList()
            .flatMapMany(orders ->
                lineRepository.findByOrderIdIn(orderIds)
                    .collectMultimap(OrderLine::orderId)
                    .flatMapMany(linesByOrder ->
                        Flux.fromIterable(orders)
                            .map(order -> toDetails(
                                order,
                                linesByOrder.getOrDefault(
                                    order.id(),
                                    List.of()
                                )
                            ))
                    )
            )
    );
~~~

This is an illustrative example; collection types and repository methods must match your actual model. For very large pages, bound memory usage. The ID query must have a deterministic `ORDER BY`, and detail assembly should preserve page order if the response requires it.

## 17. Large Writes and Bulk Operations

If a use case updates thousands of rows, there is no need to load every entity and save them one by one. You can use conditional `UPDATE` statements, batch statements, or multi-row SQL depending on semantics.

Example batch status update:

~~~sql
UPDATE orders
SET status = :newStatus
WHERE status = :oldStatus
  AND created_at < :cutoff;
~~~

This statement modifies the database directly. It does not invoke domain methods on each order, run per-entity validation logic, or trigger entity callbacks like the normal `save` path.

Before using a bulk update, determine:

- Which invariants must be checked?
- Does `version` need to be updated?
- Is per-row auditing required?
- Are triggers or database constraints protecting the data?
- Do modified IDs need to be returned?
- What are the semantics if some rows fail the condition?
- Does the transaction need to be all-or-nothing?

Bulk operations fit when conditions and effects can be expressed accurately via SQL and database constraints. When each entity has per-instance domain rules, bounded-chunk processing with appropriate transactions is safer.

## 18. Separating Read Models and Write Models When Needed

Some read use cases need multi-table `JOIN`s, aggregations, and calculations; write use cases need to protect an aggregate's invariants. A single object model does not have to serve both.

You can use:

- Entities/aggregates for write operations.
- Projections or DTOs for read queries.
- Dedicated Repository/`DatabaseClient` queries per read use case.
- Application services orchestrating write commands.

This is a lightweight way to apply CQRS thinking without necessarily introducing event sourcing or complex infrastructure.

Example:

~~~java
public record OrderDetailsView(
    UUID orderId,
    String status,
    String customerName,
    BigDecimal total,
    List<OrderLineView> lines
) {}
~~~

The read query can join `orders`, `customers`, and `order_lines` and map directly into the view. Commands changing status still go through the `Order` aggregate/service to enforce transitions and versioning.

Never create a read DTO and pass it to `repository.save(dto)` as though it were an entity. Read models and write models have distinct responsibilities.

## 19. Database Constraints Are the Final Line of Defense

Service-layer validation produces clear business errors, but it cannot replace constraints. Concurrent requests can pass pre-write checks simultaneously.

Use database constraints for invariants expressible at the schema level:

- `PRIMARY KEY` for identity.
- `UNIQUE` for unique business keys.
- `FOREIGN KEY` for referential integrity.
- `NOT NULL` for required fields.
- `CHECK` for single-row conditions.
- Appropriate indexes for queries and uniqueness.

Example:

~~~sql
CREATE TABLE order_lines (
    order_id UUID NOT NULL REFERENCES orders(id),
    line_no INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Application services should still validate early to return meaningful errors. When database constraints raise errors due to race conditions or invalid data, translate specific exceptions into domain/API errors.

## 20. Testing Read and Write Boundaries

Repository tests should verify queries and mappings. Service tests should verify orchestration and transaction semantics. Integration tests against a real database must verify constraints, concurrency, and dialect-specific SQL.

### Testing the Absence of Dirty Checking

A test can prove that loading and mutating an object without saving leaves the database unchanged:

~~~java
StepVerifier.create(
    productRepository.findById(id)
        .doOnNext(product -> product.setName("Changed in memory"))
        .then(productRepository.findById(id))
)
.assertNext(reloaded ->
    assertEquals("Original", reloaded.getName())
)
.verifyComplete();
~~~

This example assumes a mutable `ProductEntity` and that the second query executes after the first object is read. If the entity is a record, you can construct an in-memory copy without calling `save`; reloading still yields the old value.

### Testing Explicit Updates

Verify the affected row count:

~~~java
StepVerifier.create(orderRepository.updateStatus(id, "PAID"))
    .expectNext(1)
    .verifyComplete();
~~~

Then reload to confirm the state. Also test that a non-existent ID returns `0` and that the service converts it to not-found per contract.

### Testing Optimistic Concurrency

- Read the entity at version `v`.
- Update using version `v`.
- Attempt another update using the old version `v`.
- Verify the second operation conflicts or updates zero rows.
- Reload to verify final state.

### Testing Transaction Rollback

Create a multi-table write use case, force a later step to fail, and confirm earlier operations rolled back when inside the same transaction. Use `TransactionalOperator` or `@Transactional` with reactive publishers actually subscribed within the transaction context.

Do not rely solely on mocks, because mocks do not prove `ConnectionFactory`, the transaction manager, and the database participate in a single transaction.

## 21. Common Mistakes When Moving from ORM to R2DBC

| Symptom | Old Assumption | Redesign |
| --- | --- | --- |
| Object modified but DB unchanged | Expected dirty checking to auto-flush. | Call `save` or an explicit `UPDATE`. |
| Accessing a relation returns no data | Expected lazy loading. | Query the relation explicitly. |
| List endpoint is slow | N+1 per entity. | `JOIN` projection or batch fetch. |
| Saving root emits unexpected SQL | Misunderstood aggregate mapping. | Verify collection semantics and aggregate boundaries. |
| Deleting root leaves orphans or fails FK | Expected ORM cascade. | Design explicit FKs and deletion behavior. |
| Lost updates / overwritten data | No concurrency control. | `@Version` or conditional `UPDATE`. |
| Transaction does not cover all operations | Called `subscribe`/`block` detaching publishers. | Return publishers and use reactive transactions. |
| Service queries see inconsistent snapshots | Assumed persistence context caches state. | Use appropriate transaction/isolation or a join query. |
| Bulk update skips auditing/domain logic | Expected callbacks and lifecycle per entity. | Handle metadata and invariants explicitly. |
| Entity graph too large | Used object graphs like an ORM. | Limit aggregate scope and use ID references. |
| Pagination returns fewer roots than requested | `LIMIT` applied to one-to-many `JOIN` rows. | Paginate root IDs first, then load relations. |
| Update misses non-existent record | Did not check `rowsUpdated`. | Check affected row count. |

## 22. Explicit Persistence Design Workflow

When migrating a use case from an ORM to Spring Data Relational R2DBC, follow this sequence:

1. **Identify the aggregate root:** Which object owns the invariants and lifecycle of dependent rows?
2. **Distinguish aggregate members from references:** Which objects belong inside the aggregate; which need only an ID?
3. **Design read queries:** Does the endpoint need full entities, projections, joins, or multiple queries?
4. **Prevent N+1:** Use batch fetching or joins per use case; never query relations inside a loop.
5. **Design write commands:** Save the aggregate, run an explicit `UPDATE`, or use a bulk operation?
6. **Define mutable fields:** Avoid overwriting server-managed fields or out-of-tenant data.
7. **Set transaction boundaries:** Wrap database operations that must be atomic for the use case.
8. **Handle concurrency:** `@Version` or version/state predicates in `UPDATE`.
9. **Enforce integrity in the database:** Foreign keys, unique constraints, check constraints, and indexes.
10. **Identify out-of-persistence behavior:** Auditing, callbacks, outbox, and side effects.
11. **Test real SQL:** Repositories, mapping, query plans, transactions, and constraints.
12. **Measure performance:** Query counts, round trips, connection usage, and aggregate size.

Spring Data Relational R2DBC encourages persistence expressed through clear queries and write commands. There is no dirty checking or lazy loading automatically handling mutations and relationships like an ORM unit-of-work. Aggregate boundaries define what data is persisted together; repositories, templates, and SQL specify exactly what is read and written; application services define transactions per use case; and database constraints plus optimistic locking protect integrity under concurrency. Designing around these boundaries makes persistence behavior predictable, measurable, and well suited to the reactive model.
