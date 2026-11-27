# Avoiding Side Effects, Repeated Queries, and Circular Dependencies in Callbacks

Spring Data R2DBC supports entity callbacks to execute logic at specific points in the entity conversion and persistence lifecycle. Callbacks are useful for small, consistent operations such as normalizing data, enriching metadata, or adjusting values before writing. However, callbacks can easily become a dumping ground for too many responsibilities: querying other repositories, writing extra entities, making HTTP calls, sending messages, or calling back into the very repository that triggered them.

Such behaviors can cause N+1 repeated queries, create recursive call loops, introduce hard-to-manage bean dependencies, and trigger side effects at the wrong time relative to transactions. The safe practice is to keep callbacks short, predictable, and focused on the current entity; place orchestration, related queries, and side effects in services/use cases with clear boundaries.

## 1. Where do entity callbacks sit in the persistence lifecycle?

When Spring Data R2DBC saves or reads an entity through a repository or `R2dbcEntityTemplate`, the framework performs conversion steps between Java objects and relational data. Entity callbacks allow applications to participate at certain points in that process.

Common callbacks include:

| Callback | General timing | Suitable purpose |
| --- | --- | --- |
| `BeforeConvertCallback<T>` | Before the entity is converted into write data | Normalize or populate values on the entity |
| `BeforeSaveCallback<T>` | Before writing already-converted data | Adjust the outbound row if genuinely necessary |
| `AfterSaveCallback<T>` | After saving the entity | Observe save results or update local metadata |
| `AfterConvertCallback<T>` | After a row is converted into an entity | Adjust the entity after mapping using available data |

Exact callback names and signatures must be checked against your Spring Data Relational version. Reactive callbacks return a publisher so the framework can coordinate them in the pipeline; they are not synchronous listeners permitted to block threads.

High-level write flow:

~~~mermaid
flowchart TD
    A[Repository save / Template insert or update]
    B[BeforeConvertCallback]
    C[Convert entity to outbound row]
    D[BeforeSaveCallback]
    E[Execute SQL through R2DBC]
    F[AfterSaveCallback]
    G[Return saved entity publisher]
    A --> B --> C --> D --> E --> F --> G
~~~

The read flow converts rows into entities and runs post-mapping callbacks. Callbacks are invoked only when the operation passes through Spring Data's corresponding entity mapping path. Hand-written SQL with `DatabaseClient` and manual `Row` mapping does not automatically become a full entity lifecycle like repository/template operations.

## 2. What kind of logic belongs in callbacks?

Callbacks should handle small, local logic that does not orchestrate multiple resources:

- Normalizing strings before saving, such as trimming whitespace.
- Generating a slug from a name when the rule is completely deterministic from the current entity.
- Populating simple timestamps or metadata.
- Applying pure transformation rules on the entity.
- Adjusting values in the outbound row before sending to the database.

Email normalization example:

~~~java
import java.util.Locale;
import org.reactivestreams.Publisher;
import org.springframework.data.r2dbc.mapping.event.BeforeConvertCallback;
import org.springframework.data.relational.core.mapping.SqlIdentifier;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class NormalizeCustomerCallback
        implements BeforeConvertCallback<Customer> {

    @Override
    public Publisher<Customer> onBeforeConvert(
            Customer customer,
            SqlIdentifier table) {

        String normalizedEmail = customer.email()
                .trim()
                .toLowerCase(Locale.ROOT);

        Customer normalized = new Customer(
                customer.id(),
                customer.name().trim(),
                normalizedEmail
        );

        return Mono.just(normalized);
    }
}
~~~

The callback only reads the input entity, builds the normalized entity, and returns a publisher. It does not query the database, call other services, or emit external side effects.

For immutable entities such as records, the modified instance must be returned. Do not assume Spring Data mutates the original object in place.

## 3. Reactive callbacks are not a place to block

Callbacks in Spring Data R2DBC are reactive. Receiving/returning a publisher lets the callback participate in the pipeline without blocking threads.

Do not do this:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    Customer existing = customerRepository
            .findById(customer.id())
            .block();

    return Mono.just(customer);
}
~~~

This snippet has multiple problems:

- `block()` blocks a thread inside a reactive flow.
- The callback turns a small transformation into a database query.
- Every save can trigger an additional query.
- If the callback is triggered by the very persistence path the query uses, it can cause a call loop.
- Query errors are thrown synchronously instead of being composed naturally in the reactive pipeline.

If an operation truly needs data from another repository, move it out to the service before calling save:

~~~java
public Mono<Customer> createCustomer(CreateCustomerCommand command) {
    return tenantRepository.findById(command.tenantId())
            .switchIfEmpty(Mono.error(
                    new TenantNotFoundException(command.tenantId())
            ))
            .flatMap(tenant -> {
                Customer customer = new Customer(
                        null,
                        tenant.id(),
                        command.name(),
                        command.email()
                );
                return customerRepository.save(customer);
            });
}
~~~

The service clearly expresses the required query and business sequence. The Customer callback can remain focused on normalizing Customer's own data.

## 4. Querying inside callbacks can cause N+1

Suppose a callback after loading Order queries Customer to populate the customer's name:

~~~java
@Component
public class EnrichOrderCallback
        implements AfterConvertCallback<Order> {

    private final CustomerRepository customerRepository;

    public EnrichOrderCallback(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @Override
    public Publisher<Order> onAfterConvert(
            Order order,
            Row row,
            RowMetadata metadata) {

        return customerRepository.findById(order.customerId())
                .map(customer -> order.withCustomerName(customer.name()));
    }
}
~~~

This is an example to avoid for large lists. When querying 100 Orders, the callback can trigger 100 additional Customer queries:

~~~text
SELECT orders ...                 -- 1 query
  callback Order 1 -> SELECT customer WHERE id = ?
  callback Order 2 -> SELECT customer WHERE id = ?
  callback Order 3 -> SELECT customer WHERE id = ?
  ...
  callback Order 100 -> SELECT customer WHERE id = ?
~~~

This is the N+1 problem: one query fetches the primary set plus one query per entity. Being reactive does not eliminate round-trip cost or database load; it only changes how asynchronous execution is expressed and consumed.

Callbacks can also be invoked when an entity is read across many different use cases. A seemingly simple query can unexpectedly trigger many extra queries and make latency unpredictable.

## 5. Use JOINs or batch queries instead of N+1

If a screen needs Order together with Customer name, build a read model using a JOIN query:

~~~java
public record OrderSummary(
        Long orderId,
        Long customerId,
        String customerName,
        String status
) {}

public Flux<OrderSummary> findOrderSummaries() {
    return databaseClient.sql("""
            SELECT o.id AS order_id,
                   c.id AS customer_id,
                   c.name AS customer_name,
                   o.status
            FROM orders o
            JOIN customer c ON c.id = o.customer_id
            ORDER BY o.id
            """)
            .map((row, metadata) -> new OrderSummary(
                    row.get("order_id", Long.class),
                    row.get("customer_id", Long.class),
                    row.get("customer_name", String.class),
                    row.get("status", String.class)
            ))
            .all();
}
~~~

This query returns the needed data in a single read round trip. It needs no callback querying Customer for every Order.

If a JOIN cannot be used, load the Customer set in a batch:

~~~java
public Mono<List<OrderSummary>> findSummaries() {
    return orderRepository.findAll()
            .collectList()
            .flatMap(orders -> {
                Set<Long> customerIds = orders.stream()
                        .map(Order::customerId)
                        .collect(Collectors.toSet());

                return customerRepository.findAllById(customerIds)
                        .collectMap(Customer::id)
                        .map(customers -> orders.stream()
                                .map(order -> toSummary(
                                        order,
                                        customers.get(order.customerId())
                                ))
                                .toList()
                        );
            });
}
~~~

This batch example reduces Customer queries to one query by ID set, though `collectList()` holds all Orders in memory. For large datasets, paginate Orders first and fetch Customers by ID per page. You can also use `R2dbcEntityTemplate` or `DatabaseClient` to execute a JOIN directly.

## 6. Callbacks calling back into the repository can create recursion

A more dangerous bug than N+1 is a callback invoking the very persistence path that triggered the callback:

~~~java
@Component
public class CustomerAfterConvertCallback
        implements AfterConvertCallback<Customer> {

    private final CustomerRepository repository;

    public CustomerAfterConvertCallback(CustomerRepository repository) {
        this.repository = repository;
    }

    @Override
    public Publisher<Customer> onAfterConvert(
            Customer customer,
            Row row,
            RowMetadata metadata) {

        return repository.findById(customer.id());
    }
}
~~~

The call chain can become:

1. `findById` reads Customer.
2. Spring Data converts row into Customer.
3. `AfterConvertCallback` runs.
4. The callback calls `findById` again.
5. The nested query reads Customer and triggers the same callback.
6. The loop continues until resources are exhausted or an error occurs.

Do not call the repository to reload the same entity inside a post-mapping callback. The callback already receives the loaded entity; if verification or loading other data is needed, do it in a service or dedicated query outside the callback.

## 7. Circular dependencies between callbacks, services, and repositories

A callback is a Spring bean. If a callback injects a service, the service uses a repository, and repository operations trigger the callback, the application can form a runtime execution cycle:

~~~mermaid
flowchart LR
    A[Repository save/read] --> B[Entity callback]
    B --> C[Domain service]
    C --> A
~~~

Depending on configuration, the cycle can also create a bean dependency cycle at startup:

~~~text
CustomerRepository / mapping infrastructure
        -> CustomerCallback
        -> CustomerService
        -> CustomerRepository
~~~

Even if Spring manages to initialize the beans, the callback can call back into the service/repository and trigger the same chain again. Using `@Lazy` or setter injection only defers dependency resolution; it does not fix the logical call cycle.

Design should separate responsibilities:

- Repositories only perform queries and persistence.
- Callbacks only transform the current entity or outbound row.
- Services/use cases coordinate multiple repositories and business rules.
- Event/side-effect dispatchers run at appropriate boundaries after data commits.

If a callback needs to call a service to decide how to save, that logic almost certainly belongs in the service before calling the repository.

## 8. Do not write additional entities from save callbacks

A pre-save or post-save callback on Order that calls `orderRepository.save(...)` can re-trigger itself:

~~~java
@Component
public class OrderSaveCallback
        implements AfterSaveCallback<Order> {

    private final OrderRepository repository;

    public OrderSaveCallback(OrderRepository repository) {
        this.repository = repository;
    }

    @Override
    public Publisher<Order> onAfterSave(
            Order order,
            OutboundRow row,
            SqlIdentifier table) {

        return repository.save(order.withProcessed(true));
    }
}
~~~

This is a persistence loop: saving Order triggers AfterSaveCallback; the callback saves Order again; the second save triggers the callback again. Even with a termination condition, the flow is confusing and can write data multiple times.

If business logic needs to save a related record, put that operation in a service with an explicit transaction:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    orderAuditRepository.save(toAudit(order))
                            .thenReturn(order)
            );
}
~~~

The service makes both write operations explicit and can control transactions, errors, retries, and execution order.

## 9. Do not call external services from persistence callbacks

An `AfterSaveCallback` can tempt developers into sending emails, making HTTP calls, or publishing messages:

~~~java
@Component
public class NotifyAfterSaveCallback
        implements AfterSaveCallback<Order> {

    private final NotificationClient notificationClient;

    @Override
    public Publisher<Order> onAfterSave(
            Order order,
            OutboundRow row,
            SqlIdentifier table) {

        return notificationClient.sendOrderCreated(order)
                .thenReturn(order);
    }
}
~~~

Avoid attaching external side effects to save callbacks because:

- The callback may run before the enclosing transaction commits.
- The notification may already have been sent even if the database transaction later rolls back.
- Transaction retries can invoke the callback multiple times and send duplicates.
- Timeouts/cancellations can leave the application unsure whether the external system received the request.
- A notification error can fail the save publisher even though database data was already written in an uncommitted transaction.

Callbacks are not a reliable boundary for ensuring a side effect happens once after commit.

## 10. Use a transactional outbox for side effects

If an event must be emitted after saving Order, persist an outbox record in the same transaction as the business data:

~~~sql
CREATE TABLE outbox_event (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    aggregate_type VARCHAR(100) NOT NULL,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    published_at TIMESTAMP WITH TIME ZONE
);
~~~

Service:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderCommand command) {
    return orderRepository.save(toOrder(command))
            .flatMap(order ->
                    outboxRepository.save(toOutboxEvent(order))
                            .thenReturn(order)
            );
}
~~~

Order and the outbox event commit or roll back together. A separate process reads unpublished events, sends them to the broker or external service, and marks them processed. Consumers should be idempotent because delivery and acknowledgment can repeat if a worker crashes between those two steps.

An outbox does not guarantee exactly-once delivery on its own. It provides the foundation for at-least-once delivery with idempotent processing and prevents losing events when the business transaction commits.

## 11. Distinguishing callbacks from domain services and lifecycle events

Not everything happening around save belongs in a callback:

| Type of logic | Appropriate place |
| --- | --- |
| Normalizing properties of the current entity | Entity method or `BeforeConvertCallback` |
| Populating simple audit metadata | Spring Data auditing or appropriate callback |
| Validating rules requiring queries across multiple aggregates | Application/domain service before saving |
| Writing multiple entities in one use case | Service inside a reactive transaction |
| Building read models across multiple tables | JOIN with `DatabaseClient` or dedicated query |
| Sending emails, HTTP, or messages | Outbox/dispatcher or appropriate after-commit mechanism |
| Lifecycle logging/metrics | Lightweight callback or observability layer |

Lifecycle events and entity callbacks also serve different purposes. A callback is a hook that can transform an entity/row and participate in the persistence pipeline. An event generally announces that something occurred; listeners should not be treated as atomic transactions with external systems without additional design.

## 12. Avoiding repeated queries when reading entity lists

When related data is needed in a response, define the query shape upfront:

1. What data needs to be displayed?
2. Can it be retrieved with a JOIN?
3. Can it be loaded once per page by ID set?
4. Can a projection/DTO be constructed directly from SQL?
5. Does the result need pagination or limits?

Example to avoid:

~~~java
return orderRepository.findAll()
        .flatMap(order ->
                customerRepository.findById(order.customerId())
                        .map(customer -> toSummary(order, customer))
        );
~~~

With N Orders, the pipeline can execute one Order query and N Customer queries. Using `flatMap` makes the queries asynchronous, but does not reduce the query count.

JOIN solution:

~~~sql
SELECT o.id, o.status, c.id AS customer_id, c.name AS customer_name
FROM orders o
JOIN customer c ON c.id = o.customer_id
WHERE o.status = :status
ORDER BY o.id;
~~~

If using batch queries, limit the Order set first and then load Customers with `findAllById(ids)`. Do not collect an unbounded table into memory just to avoid N+1.

## 13. Callbacks should be idempotent and independent of call count

A callback can be called again when:

- A persistence operation is retried.
- A service calls save multiple times.
- An import flow reprocesses records.
- A transaction retries after a deadlock/serialization conflict.
- An entity is loaded across different queries.

Therefore, a callback should not assume "each entity passes through the callback exactly once in its entire lifetime." Write logic so the same input produces the same output without duplicate side effects.

For example, string normalization is idempotent:

~~~java
String normalized = email.trim().toLowerCase(Locale.ROOT);
~~~

Applying it multiple times produces the same result.

Conversely, logic like:

~~~java
entity.setAttemptCount(entity.getAttemptCount() + 1);
~~~

can increment the counter every time the callback runs, even if the transaction ultimately rolls back or retries. If this is a business attempt counter, update it in the service/use case via an operation with clear semantics.

## 14. Callbacks and database-generated data

If a callback truly needs a database-generated value, see whether it can be produced by database or Spring Data mechanisms without nested queries:

- Use identity/sequence for auto-generated IDs.
- Use default expressions for database default values.
- Use the auditing infrastructure for created/modified metadata.
- Use converters for data-type conversions.
- Use projections or JOINs for aggregated read data.

Do not re-query the entity right after save solely to fetch the generated ID if the save publisher already returns the entity containing the ID. Use the emitted value:

~~~java
return customerRepository.save(customer)
        .flatMap(saved ->
                auditRepository.save(toAudit(saved.id()))
                        .thenReturn(saved)
        );
~~~

This avoids an unnecessary SELECT round trip and keeps orchestration in the service.

## 15. Callback order and inter-callback dependencies

An application can register multiple callbacks of the same type or callbacks across different stages. When execution order matters, configure order using the ordering mechanism supported by your Spring Data/Spring version, such as `Ordered` or `@Order` where appropriate.

Do not build callback chains where callback A depends on callback B having written to the database or called a service. That order is hard to observe and can create circular dependencies.

If two transformations must run in a mandatory business sequence, consider combining them into one clear component or executing them in the service before calling the repository. Callbacks should be simple transformation steps, not a workflow engine.

## 16. Error handling in callbacks

Because callbacks return a publisher, errors can be emitted asynchronously:

~~~java
@Override
public Publisher<Customer> onBeforeConvert(
        Customer customer,
        SqlIdentifier table) {

    if (customer.email() == null || customer.email().isBlank()) {
        return Mono.error(new InvalidCustomerException(
                "Email is required"
        ));
    }

    return Mono.just(customer);
}
~~~

Simple local validation can be done in a callback, whereas business validation requiring multiple aggregates or database queries belongs in a service. When a callback emits an error, the corresponding persistence operation fails and an enclosing transaction can roll back as configured.

Do not catch all exceptions and return the entity:

~~~java
// Do not mask all errors inside a callback.
return someTransformation()
        .onErrorResume(error -> Mono.just(customer));
~~~

This can allow data violating rules to be written anyway. If a recoverable error exists, classify it explicitly and handle the decision in the business layer.

## 17. Callbacks and reactive transactions

Callbacks execute within the persistence pipeline they participate in. If the repository operation is inside a reactive transaction, the callback is also part of that process. However, having a callback execute nested queries or call external systems does not automatically make those side effects a true atomic unit.

For example, if a callback sends an HTTP request and the save publisher later emits an error:

- The HTTP request may already have been processed by the external system.
- The database transaction may roll back.
- A retry may send the HTTP request a second time.

An R2DBC transaction only manages the database resource owned by the transaction manager. It does not roll back emails, HTTP requests, or message brokers.

Keeping callbacks local keeps transactions short and predictable. Additional database operations should be chained explicitly inside the service transaction; external side effects should use an outbox or resilient post-commit mechanism.

## 18. Testing callbacks

Callback tests should verify local transformations:

~~~java
@Test
void normalizesEmailBeforeConvert() {
    NormalizeCustomerCallback callback =
            new NormalizeCustomerCallback();

    Customer input = new Customer(
            null,
            "  An Nguyen  ",
            "  AN@EXAMPLE.COM "
    );

    Customer result = Mono.from(
            callback.onBeforeConvert(
                    input,
                    SqlIdentifier.unquoted("customer")
            )
    ).block();

    assertEquals("An Nguyen", result.name());
    assertEquals("an@example.com", result.email());
}
~~~

This is a unit test for pure transformation logic; using `block()` in a synchronous test is intentional and must not be carried into production callbacks/services.

Integration tests must confirm the callback is actually invoked on the repository/template path and transformed values are saved/loaded properly. Also verify:

- The callback does not generate unexpected extra queries.
- The callback does not call save on itself causing recursion.
- Multiple entities in a query do not trigger N+1.
- Callback errors fail the persistence publisher properly.
- Retries do not duplicate side effects.
- Callbacks do not create bean dependency cycles.

If query counts need checking, use logging/metrics or driver-appropriate statement observation in integration tests. Do not rely solely on mocked callbacks to conclude there are no repeated queries at runtime.

## 19. Common mistakes

1. **Querying repositories inside a callback per entity.** Can cause N+1 and increase latency.
2. **Calling the same repository in AfterConvertCallback.** Can re-trigger the callback and create recursion.
3. **Calling save from AfterSaveCallback.** Can infinitely loop the save/callback chain.
4. **Injecting a service into a callback while the service calls that repository.** Creates circular dependencies at runtime or bean startup.
5. **Using @Lazy to hide circular dependencies.** Only defers the error without fixing the logical cycle.
6. **Using block() in a reactive callback.** Blocks threads and defeats reactive benefits.
7. **Sending emails or HTTP calls from callbacks.** Side effects can happen before commit and repeat on retries.
8. **Assuming callbacks run only once.** Retries or multiple persistence operations can re-invoke callbacks.
9. **Incrementing counters or generating random IDs in callbacks without considering retries.** Can mutate data across attempts.
10. **Using callbacks to coordinate multiple aggregates.** That logic belongs in application/domain services.
11. **Collecting all entities and then querying each relationship.** Can create N+1 or consume excessive memory.
12. **Relying on implicit callback order.** Configure explicit ordering or move the workflow to a service.

## Quick selection rules

- Use callbacks for small, local, idempotent transformations on the current entity/row.
- Use `BeforeConvertCallback` for normalizing entities before conversion.
- Use `BeforeSaveCallback` when genuinely needing to adjust data already converted into an outbound row.
- Do not call `block()`, `subscribe()`, or nested repositories inside callbacks.
- Do not query related entities per entity in callbacks; use JOINs or batch queries.
- Do not save entities from save callbacks; orchestrate multiple writes in services and transactions.
- Do not make HTTP calls, send emails, or publish messages from persistence callbacks; use a transactional outbox or appropriate post-commit mechanism.
- Avoid injecting a service into a callback when that service invokes the repository triggering the callback.
- Design callbacks to be idempotent because persistence can be retried or executed multiple times.
- Test both callback transformations and query counts/transactions against a real database.

Entity callbacks are useful hooks in the Spring Data R2DBC mapping lifecycle, yet they should remain small and predictable. When a callback queries repositories, writes extra entities, or calls external systems, it can introduce N+1 queries, recursion, circular dependencies, and side effects that occur before commit or repeat on retries. Use callbacks for local transformations; let services coordinate queries and multiple database operations; use JOINs or batch queries for related data; and use a transactional outbox for side effects that must fire after commit. This separation keeps callbacks from becoming a hidden workflow inside persistence.
