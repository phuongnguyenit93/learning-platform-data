# Using map, flatMap, and concatMap Around Data Access Operations

In Spring Data Relational R2DBC, repositories and `DatabaseClient` return reactive publishers such as `Mono` or `Flux`. When composing these publishers with Reactor, the three most commonly used operators are `map`, `flatMap`, and `concatMap`.

They all transform data in a reactive pipeline, but they handle the returned value or publisher differently:

- **map** transforms one value into another value using a synchronous function.
- **flatMap** transforms a value into a `Publisher`, then subscribes to and flattens the result of that `Publisher`; inner `Publisher`s may run concurrently.
- **concatMap** also transforms a value into a `Publisher`, but subscribes and waits for each inner `Publisher` to complete in source order before processing the next element.

When accessing a database, choosing the wrong operator can produce a nested `Mono<Mono<T>>` type, inadvertently execute multiple queries concurrently, break update ordering, or introduce blocking code into a reactive pipeline. Understanding the exact semantics helps chain read/write steps clearly and control execution order.

## 1. Reactive repositories return a Publisher

An R2DBC repository typically returns a `Mono` or `Flux`:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatus(String status);
}
~~~

- `Mono<T>` emits at most one value `T`, or completes empty, or emits an error.
- `Flux<T>` emits 0 to many values `T`, or emits an error.

These publishers describe data access work. Typically, the SQL statement is only executed when the publisher is subscribed to. Therefore, calling `findById()` to create a publisher does not mean the database has already returned a result at that line of code.

For example:

~~~java
Mono<Customer> customerPublisher =
    customerRepository.findById(42L);
~~~

The `customerPublisher` variable holds a publisher. Only when the publisher is subscribed to by the web layer, service, or another operator does the R2DBC work actually execute.

In reactive code, you should compose the publisher and return it to the caller. Do not call `subscribe()` or `block()` yourself inside a service just to fetch data synchronously.

## 2. map: synchronously transform a value

`map` receives a value emitted by a publisher and transforms it into another value. The mapper function must return data directly, not a new `Publisher`.

Example converting `Customer` into a DTO:

~~~java
public Mono<CustomerSummary> findSummary(Long id) {
    return customerRepository.findById(id)
        .map(customer -> new CustomerSummary(
            customer.getId(),
            customer.getName(),
            customer.getStatus()
        ));
}
~~~

Data flow:

~~~text
Mono<Customer>
      |
      v
     map
      |
      v
Mono<CustomerSummary>
~~~

`map` is suitable for fast, synchronous operations that do not need to wait for another `Publisher`:

- Converting an entity into a DTO.
- Extracting a property.
- Normalizing or formatting data.
- Computing a value from an object already in memory.
- Mapping a database row into a Java record.

### map when mapping a DatabaseClient row

This is a very common use case for `map`:

~~~java
Flux<CustomerSummary> customers =
    databaseClient.sql(
            "SELECT id, name, status FROM customer WHERE active = :active"
        )
        .bind("active", true)
        .map((row, metadata) -> new CustomerSummary(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("status", String.class)
        ))
        .all();
~~~

`DatabaseClient` reads each row from the SQL result. The `map` function converts the row into a `CustomerSummary` directly within the pipeline. There is no second database query inside the mapper, so `map` is the right choice.

### map does not subscribe to a returned Publisher

This is a common mistake:

~~~java
Mono<Mono<Customer>> result =
    customerRepository.findById(42L)
        .map(customer ->
            customerRepository.findByEmail(customer.getEmail())
        );
~~~

The `map` function returns a `Mono<Customer>`. Because `map` treats that `Publisher` as an ordinary Java value, the result becomes `Mono<Mono<Customer>>`. The inner `Publisher` is neither flattened nor subscribed to automatically.

If you want to run the second query and receive the final `Customer` directly, use `flatMap`:

~~~java
Mono<Customer> result =
    customerRepository.findById(42L)
        .flatMap(customer ->
            customerRepository.findByEmail(customer.getEmail())
        );
~~~

### Do not place blocking operations inside map

You should not call JDBC, `block()`, blocking file reads, or synchronous HTTP calls inside `map`:

~~~java
return customerRepository.findById(id)
    .map(customer -> blockingClient.loadProfile(customer.getId()));
~~~

The `map` function runs on the thread emitting the `onNext` signal. If it performs blocking I/O, that thread can be held while waiting. With a reactive client, use `flatMap` to chain the `Publisher`. With a blocking library that must be used, isolate the blocking work on an appropriate scheduler and avoid holding an R2DBC transaction or connection during long waits.

## 3. flatMap: chain another asynchronous operation

`flatMap` is used when the next step returns a `Publisher`, for example querying `Order`s after reading a `Customer`.

~~~java
public Mono<CustomerDetail> findDetail(Long id) {
    return customerRepository.findById(id)
        .flatMap(customer ->
            orderRepository.findByCustomerId(customer.getId())
                .collectList()
                .map(orders ->
                    new CustomerDetail(customer, orders)
                )
        );
}
~~~

Flow:

~~~text
findById(id)
     |
     v
 Mono<Customer>
     |
     v
  flatMap
     |
     +----> findByCustomerId(customerId)
                    |
                    v
               Flux<Order>
                    |
                collectList()
                    |
                    v
               Mono<List<Order>>
                    |
                 map(...)
                    |
                    v
            Mono<CustomerDetail>
~~~

`flatMap` does three things:

1. Receives `Customer` from the source publisher.
2. Calls the mapper function to create the `Order` query `Publisher`.
3. Subscribes to the inner `Publisher` and flattens the result into the outer pipeline.

As a result, the return type is not nested as `Mono<Mono<CustomerDetail>>`.

### flatMap on Mono

With a source `Mono`, there is at most one value to pass forward. Therefore, `flatMap` is commonly used to chain an asynchronous step that depends on the previous result:

~~~java
return customerRepository.findById(id)
    .flatMap(customer ->
        addressRepository.findById(customer.getAddressId())
            .map(address ->
                new CustomerDetail(customer, address)
            )
    );
~~~

The address query can only be built after obtaining the `Customer` and its address ID. This is a data-dependent flow, so `flatMap` is appropriate.

### flatMap on Flux

With a `Flux` that has multiple elements, `flatMap` can subscribe to multiple inner `Publisher`s concurrently:

~~~java
Flux<CustomerDetail> details =
    customerRepository.findByStatus("ACTIVE")
        .flatMap(customer ->
            orderRepository.findByCustomerId(customer.getId())
                .collectList()
                .map(orders ->
                    new CustomerDetail(customer, orders)
                )
        );
~~~

If the `Flux` emits multiple `Customer`s, multiple `Order` queries can execute concurrently. Results may be emitted in the completion order of the inner `Publisher`s, not necessarily in the original `Customer` order.

This is useful when tasks are independent and can run concurrently. However, if the queries share a connection within a reactive transaction or must preserve write order, consider carefully.

### Limiting flatMap concurrency

You can limit the number of active concurrent inner `Publisher`s:

~~~java
return customerRepository.findByStatus("ACTIVE")
    .flatMap(
        customer -> orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders -> new CustomerDetail(customer, orders)),
        8
    );
~~~

The parameter `8` limits the number of inner `Publisher`s subscribed to concurrently at any given time. It helps control load when there are many elements.

This limit does not turn multiple queries into a batch query and does not create separate connections for each branch if the branches participate in the same transaction context. If the goal is to reduce N+1 queries, use a `JOIN` or a batch query instead of only tuning concurrency.

## 4. concatMap: process each Publisher in order

`concatMap` also takes a function returning a `Publisher`, but it only subscribes to the next inner `Publisher` after the current `Publisher` completes. This preserves processing order according to the source element order.

Example deactivating customers one by one:

~~~java
public Mono<Void> deactivateCustomers(List<Long> ids) {
    return Flux.fromIterable(ids)
        .concatMap(id ->
            customerRepository.findById(id)
                .flatMap(customer -> {
                    customer.deactivate();
                    return customerRepository.save(customer);
                })
        )
        .then();
}
~~~

With `ids = [10, 20, 30]`, `concatMap` processes:

1. Read and update customer 10; wait for completion.
2. Read and update customer 20; wait for completion.
3. Read and update customer 30; wait for completion.

No subsequent inner `Publisher` is subscribed to before the current step completes.

### When is concatMap appropriate?

- Write operations that must run in order.
- Each operation depends on the result or side effect of the previous operation.
- SQL statements participating in the same transaction that must avoid concurrent execution on a single connection.
- Input order must be preserved during processing.
- The number of active inner `Publisher`s must be limited to one.

In return, `concatMap` does not exploit concurrency across elements. If individual tasks are independent and can run in parallel on separate connections, `concatMap` may make total execution time longer than necessary.

## 5. Comparing map, flatMap, and concatMap

| Operator | Mapper returns | Nested Publisher handling | Result order | Concurrent inner Publishers |
|---|---|---|---|---|
| map | Value T | Does not flatten | Preserves source order | Not applicable |
| flatMap | Publisher<R> | Subscribes and flattens | Does not guarantee source order | Possible |
| concatMap | Publisher<R> | Subscribes and flattens | Preserves source order | No; processed sequentially |

Short examples:

~~~java
// Synchronous transformation: Customer -> CustomerSummary
Mono<CustomerSummary> a =
    customerRepository.findById(id)
        .map(CustomerSummary::from);

// Chain asynchronous query: Customer -> Mono<Address>
Mono<Address> b =
    customerRepository.findById(id)
        .flatMap(customer ->
            addressRepository.findById(customer.getAddressId())
        );

// Process each customer ID sequentially
Flux<Customer> c =
    Flux.fromIterable(ids)
        .concatMap(customerRepository::findById);
~~~

A way to remember:

- `map`: you already have the data; transform it into different data.
- `flatMap`: you already have the data; use it to launch another reactive task and flatten the result.
- `concatMap`: do the same as `flatMap`, but wait for each task to complete in order.

## 6. How does flatMapSequential differ from concatMap?

Reactor also provides `flatMapSequential`. This operator can subscribe to inner `Publisher`s concurrently like `flatMap`, but emits results in the order of the source elements.

| Operator | Inner Publisher | Result emission order |
|---|---|---|
| flatMap | Can run concurrently | Completion order |
| flatMapSequential | Can run concurrently | Source order |
| concatMap | Sequential | Source order |

Example:

~~~java
return Flux.fromIterable(ids)
    .flatMapSequential(
        id -> customerRepository.findById(id)
    );
~~~

If the query for the second ID completes before the first ID, `flatMapSequential` still emits results in the input ID order. However, the inner `Publisher`s may still execute concurrently.

Therefore, `flatMapSequential` is not a replacement for `concatMap` when the requirement is to avoid issuing concurrent queries on the same transaction-bound connection.

## 7. Combining operators around a read query

A detail-reading use case may consist of these steps:

1. Find `Customer` by ID.
2. If absent, emit a not-found error.
3. Find `Address` by address ID.
4. Convert both objects into a DTO.

~~~java
public Mono<CustomerDetail> findDetail(Long id) {
    return customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .flatMap(customer ->
            addressRepository.findById(customer.getAddressId())
                .map(address ->
                    new CustomerDetail(
                        customer.getId(),
                        customer.getName(),
                        address.getCity()
                    )
                )
        );
}
~~~

Here:

- `switchIfEmpty` handles the missing `Customer` case.
- `flatMap` chains the `Address` query.
- `map` converts `Address` together with `Customer` into `CustomerDetail`.

There is no need for `flatMap` in the final step because creating a DTO is a synchronous transformation and does not produce another `Publisher`.

### map after a query completes

If the query already returns all needed data, just use `map`:

~~~java
return customerRepository.findById(id)
    .map(CustomerDetail::from);
~~~

Do not create a `flatMap` just to wrap `Mono.just(...)`:

~~~java
return customerRepository.findById(id)
    .flatMap(customer ->
        Mono.just(CustomerDetail.from(customer))
    );
~~~

Both approaches may produce equivalent results, but using `map` expresses the intent more accurately and avoids creating an extra `Publisher`.

## 8. Combining operators around write queries

Suppose you need to:

1. Find `Customer`.
2. Check status.
3. Update `Customer`.
4. Write an audit record.

~~~java
@Transactional
public Mono<Customer> changeStatus(Long id, String newStatus) {
    return customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .flatMap(customer -> {
            if ("CLOSED".equals(customer.getStatus())) {
                return Mono.error(
                    new IllegalStateException(
                        "Closed customer cannot be changed"
                    )
                );
            }

            customer.changeStatus(newStatus);
            return customerRepository.save(customer);
        })
        .flatMap(saved ->
            auditRepository.save(toAudit(saved))
                .thenReturn(saved)
        );
}
~~~

`flatMap` is needed at the save step because the repository returns `Mono<Customer>`. Writing the audit record is also a reactive operation, so `flatMap` is used again. `thenReturn(saved)` retains the saved `Customer` after the audit completes.

The publishers are chained by dependency: you cannot write the audit with the new status before knowing the result of saving `Customer`. The entire pipeline is returned so `@Transactional` can manage it.

Do not write:

~~~java
@Transactional
public Mono<Customer> changeStatus(Long id, String newStatus) {
    customerRepository.findById(id)
        .subscribe(customer -> {
            customer.changeStatus(newStatus);
            customerRepository.save(customer).subscribe();
        });

    return Mono.empty();
}
~~~

This code creates independent subscriptions and does not connect errors and completion to the publisher managed by Spring. The method can complete before the database operations finish, and the operations may not participate in the same transaction.

## 9. Handling the Mono.empty() case

Repository `findById()` returns `Mono.empty()` when the entity is not found. When the source publisher completes empty:

- `map` does not invoke the mapper.
- `flatMap` does not invoke the mapper.
- `concatMap` does not invoke the mapper for a non-existent element.

Example:

~~~java
Mono<CustomerSummary> result =
    customerRepository.findById(id)
        .map(CustomerSummary::from);
~~~

If the customer is not found, `result` also completes empty. If the API needs to return not-found, use `switchIfEmpty`:

~~~java
Mono<CustomerSummary> result =
    customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .map(CustomerSummary::from);
~~~

With `Flux`, if the source emits no elements, the mapper in `flatMap` or `concatMap` is not invoked and the result also completes empty.

Do not confuse `Mono.empty()` with a Java `null` value. Reactive Streams does not allow a publisher to emit `null` as an element. If a mapper returns `null`, Reactor emits an error instead of emitting a `null` value.

## 10. Error handling in map, flatMap, and concatMap

If a mapper throws a `RuntimeException`, or an inner `Publisher` emits `onError`, the error propagates through the reactive pipeline.

~~~java
return customerRepository.findById(id)
    .map(customer -> {
        if (customer.getName() == null) {
            throw new IllegalStateException("Customer name is missing");
        }
        return CustomerSummary.from(customer);
    });
~~~

An error from `map` becomes an `onError` signal. With `flatMap`:

~~~java
return customerRepository.findById(id)
    .flatMap(customer ->
        orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders -> new CustomerDetail(customer, orders))
    );
~~~

If the order query fails, the error is propagated to the outer publisher.

With `concatMap`, if an inner `Publisher` errors, subsequent elements are normally not processed; the error terminates the pipeline. Inside a transaction, an error matching the rollback policy can cause the transaction to roll back.

### Transforming an error while preserving onError

~~~java
return customerRepository.findById(id)
    .flatMap(customer ->
        orderRepository.findByCustomerId(customer.getId())
            .collectList()
    )
    .onErrorMap(
        DataAccessException.class,
        error -> new CustomerReadException(error)
    );
~~~

`onErrorMap` transforms the error type while still emitting `onError`. The caller and transaction boundary still receive the error signal.

### Be careful when recovering from errors

~~~java
return customerRepository.findById(id)
    .flatMap(customer -> orderRepository.findByCustomerId(customer.getId())
        .collectList()
    )
    .onErrorResume(error -> Mono.just(List.of()));
~~~

This code turns a database error into an empty list. The caller cannot distinguish a customer with no orders from a failed order query. If inside a transaction, recovering to a normal value can also cause the transaction to commit.

Only use a fallback when business rules explicitly define that error as a valid alternative result. If you only need logging, use `doOnError` and let the error continue propagating.

## 11. Backpressure and concurrency

With a `Flux` that has many elements, `flatMap` can create many inner `Publisher`s. This can cause many database queries to run simultaneously and increase load on the connection pool or database.

Example:

~~~java
return customerRepository.findAll()
    .flatMap(
        customer -> orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders -> new CustomerDetail(customer, orders)),
        16
    );
~~~

Concurrency `16` limits the number of inner `Publisher`s active at the same time. The value should be chosen based on:

- Connection pool size.
- Concurrent processing capacity of the database.
- Query execution time.
- Number of concurrent requests in the system.
- Memory resources and result size.

Do not raise concurrency just hoping to make requests faster. If the connection pool has few connections, many queries will have to wait. If branches run within the same transaction, they may also share the bound connection instead of acquiring separate connections.

`concatMap` processes one inner `Publisher` at a time, effectively limiting branch concurrency to one. It helps control order, but can increase total completion time when individual queries are slow.

## 12. map, flatMap, and concatMap in the same flow

Example fetching `ACTIVE` customers, querying orders for each customer sequentially, and building DTOs:

~~~java
public Flux<CustomerDetail> findActiveCustomerDetails() {
    return customerRepository.findByStatus("ACTIVE")
        .concatMap(customer ->
            orderRepository.findByCustomerId(customer.getId())
                .collectList()
                .map(orders ->
                    new CustomerDetail(
                        customer.getId(),
                        customer.getName(),
                        orders
                    )
                )
        );
}
~~~

In this example:

- The first repository returns `Flux<Customer>`.
- `concatMap` invokes the order query for each customer and waits for completion in order.
- `collectList` gathers the orders for one customer.
- `map` builds `CustomerDetail` from the customer and the list of orders.

If each customer triggers its own order query, this can still be an N+1 pattern. `concatMap` only serializes the subqueries; it does not reduce the query count. If you need to reduce N+1, consider a `JOIN` or a batch query using `IN`.

If order queries are independent and run outside a shared transaction, `flatMap` with an appropriate concurrency limit can improve throughput. If they share a transaction-bound connection or require ordering, `concatMap` is usually safer and easier to reason about.

## 13. When should you use then()?

`then()` is not a general mapper like `map`/`flatMap`. It waits for the previous `Publisher` to complete before subscribing to the next `Publisher` and discards the value of the previous `Publisher`.

Example:

~~~java
return auditRepository.save(auditRecord)
    .then(notificationRecordRepository.save(notificationRecord))
    .then();
~~~

Saving the notification only starts after saving the audit record completes. If you need to preserve the result of the previous step, use `flatMap` combined with `thenReturn`:

~~~java
return customerRepository.save(customer)
    .flatMap(saved ->
        auditRepository.save(toAudit(saved))
            .thenReturn(saved)
    );
~~~

If you need to transform the saved value itself, use `map`:

~~~java
return customerRepository.save(customer)
    .map(CustomerSummary::from);
~~~

## 14. N+1 is not solved just by changing operators

Suppose there are 100 customers and each customer needs its list of orders:

~~~java
return customerRepository.findAll()
    .flatMap(customer ->
        orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders -> new CustomerDetail(customer, orders))
    );
~~~

Changing `flatMap` to `concatMap`:

~~~java
return customerRepository.findAll()
    .concatMap(customer ->
        orderRepository.findByCustomerId(customer.getId())
            .collectList()
            .map(orders -> new CustomerDetail(customer, orders))
    );
~~~

Both approaches still execute one query for customers and one order query per customer. The difference is that `flatMap` can run multiple subqueries concurrently, whereas `concatMap` runs them one by one.

To reduce round trips, batch the queries:

~~~java
return customerRepository.findByStatus("ACTIVE")
    .collectList()
    .flatMapMany(customers -> {
        if (customers.isEmpty()) {
            return Flux.empty();
        }

        List<Long> ids = customers.stream()
            .map(Customer::getId)
            .toList();

        return orderRepository.findByCustomerIdIn(ids)
            .collectMultimap(PurchaseOrder::getCustomerId)
            .flatMapMany(ordersByCustomer ->
                Flux.fromIterable(customers)
                    .map(customer ->
                        new CustomerDetail(
                            customer.getId(),
                            customer.getName(),
                            List.copyOf(
                                ordersByCustomer.getOrDefault(
                                    customer.getId(),
                                    List.of()
                                )
                            )
                        )
                    )
            );
    });
~~~

The batch solution uses one customer query and one order query for the list of IDs (or per ID batch), then maps/groups data in memory. For large datasets, paginate customers and cap batch sizes instead of collecting the entire table.

## 15. Combining with @Transactional

When a reactive method is annotated with `@Transactional`, database operations join the same transaction context if they use the corresponding transaction manager and `ConnectionFactory`.

If multiple operations must commit or roll back together, chain them sequentially:

~~~java
@Transactional
public Mono<Void> createOrder(Order order) {
    return orderRepository.save(order)
        .flatMap(saved ->
            orderLineRepository.saveAll(saved.getLines())
                .then()
                .thenReturn(saved)
        )
        .flatMap(saved ->
            auditRepository.save(toAudit(saved))
        )
        .then();
}
~~~

Avoid:

~~~java
@Transactional
public Mono<Void> createOrder(Order order) {
    return Mono.when(
        orderRepository.save(order),
        auditRepository.save(toAudit(order)),
        notificationRepository.save(toNotification(order))
    ).then();
}
~~~

`Mono.when` subscribes to the input publishers to wait for all of them. If they share a transaction-bound connection, SQL statements may be issued concurrently on the same connection. Support for this depends on the driver and should not be assumed to be safe.

Changing schedulers with `subscribeOn` or `publishOn` does not create a new connection. If business rules allow each task to commit independently, you can design separate transactions for each task. Do not split transactions if the whole operation must be atomic as a single unit.

## 16. Notes on data emitted by Flux

Some operations need to collect data before querying further:

~~~java
return customerRepository.findByStatus("ACTIVE")
    .collectList()
    .flatMapMany(customers -> {
        // Have the full list of customers to build the ID list.
        return loadOrdersFor(customers);
    });
~~~

`collectList()` turns a `Flux` into a `Mono<List<T>>`. It is useful when you need to build an `IN` query from a list of IDs, but it holds all elements in memory until the source completes.

For large datasets:

- Paginate the source.
- Batch by a bounded number of IDs.
- Process each page and emit results.
- Avoid `collectList()` on an entire table.

If you only need to process elements one at a time, `concatMap` lets you serialize work without collecting all elements into a list.

## 17. Common mistakes

| Pattern | Problem | How to handle |
|---|---|---|
| `map` returning Mono/Flux | Produces `Mono<Mono<T>>` or `Flux<Publisher<T>>` | Use `flatMap` or `concatMap` |
| `flatMap` for ordered writes | Inner Publishers may run concurrently and invert order | Use `concatMap` or chain with `then` |
| `flatMapSequential` to avoid concurrent SQL | Can still run inner Publishers concurrently | Use `concatMap` |
| `concatMap` for independent tasks needing high throughput | Sequential processing, can be slow | Consider `flatMap` with proper concurrency and separate connections |
| Calling `block()` inside `map` | Blocks reactive thread | Chain `Publisher` with `flatMap` |
| Calling `subscribe()` inside mapper/service | Creates independent stream, loses error and transaction control | Return `Publisher` and compose |
| Using `flatMap` just to wrap `Mono.just` | Creates unnecessary `Publisher` | Return value directly with `map` |
| Thinking `concatMap` eliminates N+1 | Only serializes, does not reduce query count | `JOIN` or `IN` batching |
| Swallowing errors with `onErrorResume` | Can hide database errors or cause transaction commit | Recover only according to business policy |
| Unbounded `flatMap` with many queries | Increases pool/database pressure | Limit concurrency or batch |
| Thinking switching scheduler creates a new connection | Reactor Context still carries the transaction resource | Design separate transaction boundaries |
| `collectList()` on large datasets | High memory usage | Pagination or batching |

## 18. Choosing an operator by goal

| Goal | Typically suitable operator | Example |
|---|---|---|
| Convert entity to DTO | `map` | Customer → CustomerSummary |
| Extract a property from query result | `map` | Customer → customer.getEmail() |
| Map `DatabaseClient` row | `map` | Row → Java record |
| Run follow-up query based on read result | `flatMap` | Customer → findByCustomerId() |
| Save an entity and use the saved result | `flatMap` | save() → write audit |
| Run multiple independent tasks concurrently | `flatMap` with bounded concurrency | Process independent commands |
| Process each ID in order | `concatMap` | ID → findById/save |
| Multiple SQL operations must be sequential in a transaction | `then`/`flatMap`/`concatMap` | reserve → save order → audit |
| Preserve result order while allowing inner concurrency | `flatMapSequential` | Load multiple independent records |

## 19. Checklist for reading a reactive database pipeline

When reading or writing an R2DBC pipeline, determine step by step:

1. Is the source publisher a `Mono` or `Flux`?
2. Does the mapper function return a value or a `Publisher`?
3. If it returns a `Publisher`, does it need to be subscribed to and flattened?
4. Are there multiple source elements causing inner `Publisher`s to run concurrently?
5. Does SQL execution order matter?
6. Do the operations participate in the same transaction and connection?
7. How will an empty source be handled?
8. Are errors propagated, mapped, or recovered?
9. Are concurrency and data size bounded?
10. Is an N+1 pattern being created by running one subquery per element?

Do not pick an operator purely out of habit. Look at the mapper return type, the number of publishers created, business ordering requirements, and transaction boundaries.

## 20. Takeaways

- `map` is for synchronously transforming one value; it does not subscribe to a returned `Publisher`.
- `flatMap` is used when the next step returns a `Mono`/`Flux` and nested `Publisher`s need flattening.
- `flatMap` on `Flux` may run multiple inner `Publisher`s concurrently and does not guarantee source result order.
- `concatMap` also flattens `Publisher`s, but waits for each inner to complete, preserves order, and keeps only one inner `Publisher` active at a time.
- `flatMapSequential` preserves result emission order, but can still run inner `Publisher`s concurrently.
- Use `map` to map a row or entity to a DTO; use `flatMap` to chain database queries dependent on a previous result.
- Use `concatMap` or `then` when SQL operations must run sequentially, especially on the same transaction-bound connection.
- `Mono.empty()` does not invoke `map`/`flatMap` mappers; use `switchIfEmpty` if not-found handling is needed.
- Do not call `block()` or `subscribe()` inside a service to control flow; compose and return the `Publisher`.
- Concurrency limits help control load, but do not turn N+1 into a batch query by themselves.
- `concatMap` does not reduce the number of queries; `JOIN` or `IN` batching reduces round trips.
- Always consider errors, cancellation, backpressure, and transaction context when composing data access operations.
