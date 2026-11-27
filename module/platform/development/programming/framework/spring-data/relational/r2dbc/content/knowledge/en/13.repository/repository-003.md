# Return Types Mono, Flux, and Empty-Result Contracts

In Spring Data Relational R2DBC, repositories access the database reactively. Therefore, a repository method typically returns a publisher instead of immediately returning an entity, a list, or null. The return type is part of the API contract: it communicates how many results the method can emit, how the absence of results is represented, and how errors are propagated to the calling layer.

Two commonly used Reactor types are `Mono<T>` and `Flux<T>`:

- `Mono<T>` represents zero to one element.
- `Flux<T>` represents zero to many elements.

Both can complete normally without emitting any data. An empty publisher does not mean a database error. A query that finds no matching rows is usually a valid outcome; connection errors, SQL errors, or mapping errors are propagated via a separate error signal.

This lesson explains how to choose repository return types, how to define the contract when no data is found, the difference between single-result and multi-result queries, the role of `Mono<Void>`, and how to preserve the reactive chain from repository to service and API.

## 1. Result Contract of a Repository Method

When designing a read method, first determine the cardinality—the number of elements the method may return.

| Business requirement | Typical return type | Contract |
|---|---|---|
| Find one entity by key, may not exist | `Mono<T>` | Zero or exactly one entity |
| Find multiple entities by condition | `Flux<T>` | Zero, one, or many entities |
| Check existence only | `Mono<Boolean>` | Emits `true` or `false` |
| Count rows | `Mono<Long>` | Emits count, including `0` |
| Execute command needing no return data | `Mono<Void>` | Completes successfully or terminates with error |
| Obtain a small collected list | `Mono<List<T>>` at processing layer | Emits a list, which may be empty |

Return types are not merely for Java syntax. They tell the caller how to handle the case where no data is found.

For example, `findById` returns `Mono<Customer>` because a primary key identifies at most one row. `findByCity` returns `Flux<Customer>` because a city may have many customers. If the two methods swapped return types, their contracts would no longer accurately represent the domain.

## 2. Mono: Zero to One Element

`Mono<T>` is a publisher that can emit at most one element of type `T`, and then complete. It has three basic outcomes:

1. Emits one element and completes.
2. Completes empty, emitting no element.
3. Terminates with an error.

Diagram:

~~~text
Mono<Customer>
    |
    +---- onNext(Customer) ---- onComplete
    |
    +------------------------- onComplete (empty)
    |
    +------------------------- onError(exception)
~~~

Repository example:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);
}
~~~

`findByEmail` expresses the intent to find at most one customer by email. If the email does not exist, the result is `Mono.empty()`. If email is expected to be unique, the database also needs a unique constraint to enforce that rule.

### 2.1. Mono Does Not Guarantee One Result Is Always Present

A common misconception is seeing `Mono<Customer>` and assuming the method always returns a `Customer`. In reality, `Mono<T>` allows zero elements. It is not a guarantee of "always exactly one".

For example:

~~~java
Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
~~~

If the ID does not exist, the publisher completes empty. The caller must decide whether that case is normal, requires a default value, or should raise a business error.

If the use case requires the entity to exist, you can turn an empty result into an error:

~~~java
Mono<Customer> requireCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

Separating this contract in the service layer keeps the repository focused on describing the true database state: a row exists or does not exist. The service decides that a missing customer is unacceptable in a specific use case.

### 2.2. Mono for Queries Expecting One Row

Methods looking up by primary key usually return `Mono<T>`. Derived queries can also use `Mono<T>` when the condition is expected to match at most one row:

~~~java
Mono<Customer> findByEmail(String email);

Mono<Order> findByOrderNumber(String orderNumber);
~~~

If the condition is not guaranteed unique by the database and multiple rows match, a single-result query can fail because the result count exceeds one. Do not expect the framework to silently pick an arbitrary row.

When uniqueness is a data rule, express it with a `PRIMARY KEY` or `UNIQUE` constraint. The `Mono<T>` return type describes the application's expectation; the constraint protects the data against all concurrent requests and all write paths.

### 2.3. Mono for Non-Entity Scalar Values

`Mono` is also suitable for single values such as booleans, counts, or projections:

~~~java
Mono<Boolean> existsByEmail(String email);

Mono<Long> countByActiveTrue();

Mono<BigDecimal> findTotalAmountByCustomerId(Long customerId);
~~~

A count with no matching rows typically emits `0L`, rather than completing empty. An existence check emits `false` if no rows match. Choose a return type that accurately reflects the query's result.

## 3. Flux: Zero to Many Elements

`Flux<T>` can emit zero, one, or many elements and then complete, or terminate with an error. It suits collection queries:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByCity(String city);

    Flux<Customer> findByActiveTrue();

    Flux<Customer> findByLastNameContaining(String keyword);
}
~~~

A query by city can return multiple customers. If nobody lives in that city, `Flux<Customer>` completes empty.

### 3.1. An Empty Flux Is a Valid Result

For example:

~~~java
Flux<Customer> customers =
        customerRepository.findByCity("Hue");
~~~

If the database has no customers in Hue, `customers` emits no `Customer` yet still completes normally. The caller can return an empty list or continue a flow that needs no data.

There is no need to turn every empty `Flux` into an error. For searches, filters, or listings, having no results is typically a normal state.

### 3.2. Flux Emits Element by Element

`Flux` allows processing each row as soon as it is ready, rather than waiting to collect the entire result into a list. For example:

~~~java
Flux<CustomerSummary> summaries =
        customerRepository.findByCity("Hue")
                .map(CustomerSummary::from);
~~~

If you need to invoke another publisher for each entity, chain publishers with reactive operators:

~~~java
Flux<CustomerReport> reports =
        customerRepository.findByCity("Hue")
                .flatMap(reportService::createReport);
~~~

`flatMap` can run multiple inner publishers concurrently and does not preserve source emission order. If you need sequential processing and order preservation, consider `concatMap`. If you need to bound concurrency, use an overload with an appropriate concurrency parameter.

Do not call `subscribe()` inside `map` or `flatMap`. The callback should return a publisher so Reactor manages the entire chain, errors, and cancellation.

### 3.3. Collecting a Flux into a List Only When Truly Needed

If the caller requires a bounded list and the result set is reasonably constrained, you can use `collectList()`:

~~~java
Mono<List<Customer>> findCustomersAsList(String city) {
    return customerRepository.findByCity(city)
            .collectList();
}
~~~

When the source emits no elements, `collectList()` still emits an empty list:

~~~text
Empty Flux<Customer>
       |
       | collectList()
       v
Mono<List<Customer>>
       |
       v
List<Customer> = []
~~~

This is the difference between `Mono<Customer>` and `Mono<List<Customer>>`:

- `Mono<Customer>` can complete empty if there is no customer.
- `Mono<List<Customer>>` after `collectList()` emits a list; that list can be empty.

Do not collect an unbounded or very large `Flux` into a list. Every element will be held in memory until the source completes. For large datasets, process elements as a stream or limit results in the database.

## 4. Return Types in ReactiveCrudRepository

`ReactiveCrudRepository<T, ID>` defines CRUD operations using reactive types. Common return types include:

| Method | Return type | Meaning |
|---|---|---|
| `save(entity)` | `Mono<S>` | Saves entity and emits the saved entity |
| `saveAll(entities)` | `Flux<S>` | Saves multiple entities and emits the saved entities |
| `findById(id)` | `Mono<T>` | Finds at most one entity by ID |
| `findAll()` | `Flux<T>` | Emits all entities |
| `findAllById(ids)` | `Flux<T>` | Emits entities whose IDs are in the input set |
| `existsById(id)` | `Mono<Boolean>` | Checks existence |
| `count()` | `Mono<Long>` | Emits entity count |
| `deleteById(id)` | `Mono<Void>` | Deletes by ID and signals completion only |
| `delete(entity)` | `Mono<Void>` | Deletes entity and signals completion only |

Key points to understand:

- `findById` can complete empty if no row exists.
- `findAll` can complete empty if the table has no rows.
- `existsById` emits a boolean; not found is represented by `false`.
- `count` emits a count; an empty set is represented by `0`.
- Delete methods typically return `Mono<Void>` because callers need to know whether the operation completed or errored, not receive the deleted entity.

Exact method names and overloads depend on the interface, but the principle is that reactive repositories return publishers so database access happens within the reactive pipeline.

## 5. Mono<Void> and the No-Data-Returned Contract

`Mono<Void>` is typically used for operations with side effects that do not need to return an entity or value. For example:

~~~java
Mono<Void> deleteCustomer(Long id) {
    return customerRepository.deleteById(id);
}
~~~

`Mono<Void>` does not emit `onNext` with a `Void` object. It completes with `onComplete` on success or `onError` on failure.

This contract differs from an empty `Mono<Customer>`:

| Type | Meaning when completing without payload |
|---|---|
| `Mono<Customer>` | No customer to return |
| `Mono<Void>` | Operation completed with no payload |
| `Mono<Boolean>` | Typically emits a boolean value then completes |
| `Mono<Long>` | Typically emits a count then completes |

Example of a status update command needing no returned entity:

~~~java
Mono<Void> archiveOldOrders(LocalDate cutoffDate) {
    return orderRepository.archiveBefore(cutoffDate);
}
~~~

If you need to know the number of affected rows, the contract should be `Mono<Integer>` or an appropriate result type instead of `Mono<Void>`:

~~~java
@Modifying
@Query("""
    UPDATE purchase_order
    SET status = 'ARCHIVED'
    WHERE created_at < :cutoffDate
    """)
Mono<Integer> archiveBefore(LocalDate cutoffDate);
~~~

When using custom data-modification statements, the return type should match what the driver and Spring Data provide for that operation. The example above illustrates a contract returning the number of updated rows.

### 5.1. The then Operator Turns a Result into Mono<Void>

You can discard a publisher's data and care only about completion:

~~~java
Mono<Void> processAndDiscardResult(Long id) {
    return customerRepository.findById(id)
            .doOnNext(this::recordAccess)
            .then();
}
~~~

`then()` creates a publisher that completes after the source completes successfully. If the source errors, the error still propagates. If the source is empty, the resulting publisher also completes normally.

Do not use `then()` if the caller still needs the entity or value emitted by the original publisher.

### 5.2. Chaining Operations That Need No Payload

`then` also helps sequence commands in order:

~~~java
Mono<Void> closeAccount(Long id) {
    return accountRepository.markAsClosed(id)
            .then(transactionRepository.disableNewTransactions(id))
            .then();
}
~~~

Operations requiring atomicity together must be placed inside an appropriate transaction. `then` only controls ordering within the reactive pipeline; it does not create a transaction by itself.

## 6. Contracts When No Results Are Found

Having no matching rows can mean different things depending on the use case. Decide this explicitly at the right layer.

### 6.1. Not Found Is Normal

A search query may return no results:

~~~java
Flux<Product> searchProducts(String keyword) {
    return productRepository.findByNameContaining(keyword);
}
~~~

If no products match, returning an empty result set makes sense. The repository does not need to throw an exception.

### 6.2. Entity Must Exist

An order update operation requires an existing entity:

~~~java
Mono<Order> requireOrder(Long id) {
    return orderRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)));
}
~~~

Turning an empty publisher into an error in the service expresses the rule of that use case. Other use cases may still treat not finding the same entity type as normal.

### 6.3. Using a Default Value

Some configuration lookups can fall back to a default value when no record exists in the database:

~~~java
Mono<AppPreference> loadPreference(String key) {
    return preferenceRepository.findById(key)
            .defaultIfEmpty(AppPreference.defaultFor(key));
}
~~~

Only use defaults when the domain clearly defines that value. Do not fabricate dummy entities for accounts, orders, or permissions to hide missing data.

### 6.4. Checking Whether a Publisher Has an Element

If you already have a publisher and only need to know whether it emits an element:

~~~java
Mono<Boolean> hasCustomer =
        customerRepository.findById(customerId)
                .hasElement();
~~~

`hasElement()` emits `true` when the source has at least one element, and `false` if the source completes empty. If the repository provides an `existsById` or `existsBy...` method, prefer it because it directly expresses existence-check intent.

## 7. Distinguishing Empty, Null, and Error

These three concepts are not interchangeable.

### 7.1. Empty Publisher

`Mono.empty()` is a publisher that completes normally without emitting an element. `Flux.empty()` also completes without emitting any elements.

~~~java
Mono<Customer> result = customerRepository.findById(999L);
~~~

If ID 999 does not exist, the result can be `Mono.empty()`.

### 7.2. Null in Data

Reactor does not allow a publisher to emit `null`. `Mono.just(null)` is invalid. However, an emitted entity can have null Java properties if database columns allow NULL and the mapping supports those values.

For example, a customer exists without a phone number set. In that case, `Mono<Customer>` still emits the entity; the `phoneNumber` property may be `null`.

This is an important distinction:

- No row: the publisher emits no entity.
- Row exists with a SQL NULL column: the publisher emits an entity whose corresponding property is null.
- Query error: the publisher emits an error signal.

Do not use `defaultIfEmpty` to handle a null property inside an entity. `defaultIfEmpty` only handles a publisher that emits no elements.

### 7.3. Error Signal

Connection failures, SQL syntax errors, constraint violations, or mapping errors are emitted as `onError`. Errors may occur when the publisher is subscribed to, not necessarily at the moment the repository method is invoked.

Do not turn all errors into an empty publisher:

~~~java
// Avoid: hides both database errors and programming errors as "not found".
return repository.findById(id)
        .onErrorResume(error -> Mono.empty());
~~~

Only handle errors that the business logic understands:

~~~java
return repository.findById(id)
        .onErrorMap(
                DataAccessException.class,
                DatabaseOperationException::new);
~~~

If you need to handle not-found cases, use `switchIfEmpty`. If you need to handle database errors, use the appropriate error operators. Keeping this distinction clear helps logging, monitoring, and API responses stay accurate.

## 8. Derived Queries and Return Types

Spring Data can generate queries from repository method names. The return type must match the number of rows the condition can match.

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {

    Mono<Order> findByOrderNumber(String orderNumber);

    Flux<Order> findByCustomerId(Long customerId);

    Mono<Order> findFirstByCustomerIdOrderByCreatedAtDesc(
            Long customerId);

    Flux<Order> findTop20ByStatusOrderByCreatedAtDesc(
            OrderStatus status);

    Mono<Boolean> existsByOrderNumber(String orderNumber);

    Mono<Long> countByCustomerId(Long customerId);
}
~~~

Meaning:

- `findByOrderNumber` uses `Mono<Order>` if order number is unique.
- `findByCustomerId` uses `Flux<Order>` because a customer can have many orders.
- `findFirst...OrderBy...` limits the result to one row in the specified order.
- `findTop20...` limits the result set to at most 20 rows.
- `existsBy...` only answers an existence question.
- `countBy...` returns the count, even when the count is 0.

### 8.1. First and Top Must Have Business Meaning

If you want the newest record, specify an ordering:

~~~java
Mono<Order> findNewestOrder(Long customerId) {
    return orderRepository
            .findFirstByCustomerIdOrderByCreatedAtDesc(customerId);
}
~~~

Do not rely on arbitrary row order in the database. SQL only guarantees ordering when `ORDER BY` is present.

`First` or `Top` represents limiting the number of results. If you need to ensure data is truly unique, do not use `First` to silently discard duplicate rows; enforce uniqueness with a constraint.

### 8.2. Mono Does Not Replace a Unique Constraint

Suppose email must be unique. A method:

~~~java
Mono<Customer> findByEmail(String email);
~~~

does not prevent the database from storing two rows with the same email. If multiple rows match, a single-result query may raise a result-size error. The proper protection is adding a unique constraint and handling errors on write.

The return type reflects the method's expected contract; the database constraint protects the data invariant even under concurrent requests.

## 9. Return Types for @Query and DatabaseClient

With custom SQL, the reactive contract still needs to express cardinality clearly.

Repository method returning one entity:

~~~java
@Query("""
    SELECT id, order_number, status
    FROM purchase_order
    WHERE order_number = :number
    """)
Mono<Order> findOneByNumber(@Param("number") String number);
~~~

Repository method returning multiple entities:

~~~java
@Query("""
    SELECT id, order_number, status
    FROM purchase_order
    WHERE customer_id = :customerId
    ORDER BY created_at DESC
    """)
Flux<Order> findOrdersByCustomer(
        @Param("customerId") Long customerId);
~~~

With `DatabaseClient`, the fetch API lets you choose how results are retrieved:

~~~java
Mono<Map<String, Object>> one =
        databaseClient.sql("""
                SELECT id, order_number
                FROM purchase_order
                WHERE id = :id
                """)
                .bind("id", id)
                .fetch()
                .one();
~~~

~~~java
Mono<Map<String, Object>> first =
        databaseClient.sql("""
                SELECT id, order_number
                FROM purchase_order
                WHERE status = :status
                ORDER BY created_at DESC
                """)
                .bind("status", status)
                .fetch()
                .first();
~~~

~~~java
Flux<Map<String, Object>> all =
        databaseClient.sql("""
                SELECT id, order_number
                FROM purchase_order
                WHERE status = :status
                ORDER BY created_at DESC
                """)
                .bind("status", status)
                .fetch()
                .all();
~~~

These APIs have different contracts:

| API | Contract |
|---|---|
| `one()` | Zero or one row; more than one row is an error |
| `first()` | Takes the first row if present; does not verify uniqueness |
| `all()` | Emits all matching rows |

If order matters, SQL using `first()` needs `ORDER BY`. If data must be unique, `one()` or a query method returning `Mono<T>` helps detect duplicate rows, though a constraint remains the necessary data safeguard.

## 10. Publishers Are Lazy: Calling the Repository Does Not Run the Query Yet

Reactive repository methods typically return publishers. Calling the method only builds the processing chain; the query executes when the publisher is subscribed to.

~~~java
Mono<Customer> customer = customerRepository.findById(10L);
~~~

That line does not mean the database has been queried yet. Only when a web framework, a subscriber, or a test subscribes to the publisher does execution occur.

Therefore, do not call `subscribe()` inside a service just to "run" the repository:

~~~java
// Avoid: detaches the query into an independent subscription.
public Mono<Void> updateCustomer(Long id) {
    customerRepository.findById(id).subscribe();
    return auditRepository.recordUpdate(id);
}
~~~

An independent subscription can run outside the transaction context and outside the request lifecycle. The service should chain publishers and return the complete pipeline:

~~~java
public Mono<Void> updateCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)))
            .flatMap(customer -> {
                customer.setActive(false);
                return customerRepository.save(customer);
            })
            .then(auditRepository.recordUpdate(id));
}
~~~

When returning the publisher, the caller can coordinate data, errors, and subscription cancellation within the same flow. If the operation requires a transaction, place the appropriate transaction boundary around the reactive chain.

## 11. The Flux Contract and Backpressure

`Flux<T>` is not just a list wrapped in a reactive type. It supports streaming emission and Reactive Streams backpressure. A subscriber can request elements according to its demand via the subscription.

This is useful when a query returns many rows. Instead of loading everything into a `List`, the application can process elements one by one:

~~~java
return customerRepository.findAll()
        .map(CustomerSummary::from)
        .doOnNext(this::sendToDownstream);
~~~

Do not call `collectList()` on a very large source just to make code easier to write. Collecting all data consumes memory proportional to the element count and loses the benefits of streaming.

If the business requirement needs a bounded list, limit results in the query or paginate. Backpressure also does not replace database load limits: queries, connections, and transactions must still be managed within system capacity.

### 11.1. Cancellation and Resources

A subscriber can cancel the subscription before `Flux` emits all its data. The driver and Spring manage resources according to the reactive operation lifecycle; the application should keep publishers within the same chain so cancellation propagates properly.

Avoid storing connections or transactions in fields to reuse across subscriptions. Do not share a publisher holding stateful or mutable resources across requests without thoroughly understanding its semantics.

## 12. Translating Repository Contracts into API Responses

Repositories should not depend on HTTP. They represent data state with publishers; the service/controller decides how to translate that state into API responses.

| Repository contract | Common API handling |
|---|---|
| `Mono<T>` emits an entity | Return the entity content |
| `Mono<T>` completes empty | May return 404 if the resource must exist; map explicitly |
| `Flux<T>` has elements | Return a list or stream per the API contract |
| `Flux<T>` is empty | Typically return an empty result set for search endpoints |
| `Mono<Void>` completes | Can use an empty-body response, such as HTTP 204 |
| Publisher emits domain error | Map via exception handler to an appropriate error code |
| Publisher emits database error | Handle as a system error, not as missing data |

An empty `Mono<T>` does not automatically mean HTTP 404. If an endpoint needs 404, turn the empty case into an exception or build the appropriate `ResponseEntity` in the web layer.

For search endpoints, an empty `Flux<T>` is usually a valid empty list. Do not return 404 just because there are no results if the API contract defines the endpoint as a search query.

For deletes or updates requiring no response body, `Mono<Void>` represents completion without a payload. The controller can map it to the appropriate status according to the API contract.

## 13. Testing Mono and Flux Contracts

`StepVerifier` from Reactor Test lets you verify the signals a publisher emits. Tests should verify data, empty completion, and errors.

Testing a `Mono` with data:

~~~java
StepVerifier.create(customerRepository.findById(existingId))
        .expectNextMatches(customer ->
                customer.getId().equals(existingId))
        .verifyComplete();
~~~

Testing an empty `Mono`:

~~~java
StepVerifier.create(customerRepository.findById(missingId))
        .verifyComplete();
~~~

Having no `expectNext` means the test expects the publisher to complete without emitting data.

Testing a service turning empty into a domain error:

~~~java
StepVerifier.create(customerService.requireCustomer(missingId))
        .expectError(CustomerNotFoundException.class)
        .verify();
~~~

Testing a `Flux` with multiple elements:

~~~java
StepVerifier.create(customerRepository.findByCity("Hue"))
        .expectNextCount(2)
        .verifyComplete();
~~~

Testing an empty `Flux`:

~~~java
StepVerifier.create(customerRepository.findByCity("NoSuchCity"))
        .verifyComplete();
~~~

Testing `Mono<Void>` completion:

~~~java
StepVerifier.create(customerRepository.deleteById(existingId))
        .verifyComplete();
~~~

These examples require corresponding test data. With R2DBC repositories, integration tests against a real database or Testcontainers verify query and mapping behavior. Unit tests with mock publishers only verify how the service handles signals, not that SQL or the driver works properly.

## 14. Common Mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Assuming `Mono<T>` always has an entity | Fails to handle not-found cases | Treat `Mono` as zero or one element |
| Using `Mono<T>` for queries with multiple results | May encounter result-size errors | Use `Flux<T>` or intentionally limit the query |
| Using `Flux<T>` for data that must be unique without checks | May overlook duplicate data | Use `Mono<T>` and a unique constraint |
| Treating empty publishers as database errors | Wrong responses for queries with no matching rows | Distinguish empty `onComplete` from `onError` |
| Turning all errors into `Mono.empty()` | Hides SQL, connection, and mapping errors | Handle errors strictly by type |
| Using `Mono.just(null)` | Reactor forbids null emissions | Use `Mono.empty()` or a non-null value |
| Using `Mono<Void>` when affected row count is needed | Loses operation outcome information | Use an appropriate result type such as `Mono<Integer>` |
| Using `List<T>` or `Optional<T>` as synchronous contracts in reactive repositories | Loses reactive semantics | Use `Mono<T>` or `Flux<T>` |
| Collecting a large `Flux` into a list | Increases memory usage and latency | Stream results or limit/paginate |
| Calling `subscribe()` inside a service | Detaches execution from caller and transaction context | Chain publishers and return them |
| Assuming `Mono<T>` guarantees unique data | Database can still contain duplicate rows | Use keys or unique constraints |
| Using `first` without ordering | Selected row is unstable | Add `ORDER BY` or a sorted derived query |
| Expecting empty `Mono` to automatically become HTTP 404 | API may return an unexpected response | Map empty to explicit status/exception in web layer |

## 15. Process for Choosing a Return Type

When declaring a repository method, determine:

1. Can the query condition match at most one row or multiple rows?
2. If no row exists, is that a normal state or a business error?
3. If one row is expected, does the database have a key or unique constraint protecting that?
4. Does the method return an entity, a scalar value, a list, or only a completion signal?
5. If using `Flux`, can the caller process streaming results or does it need a bounded list?
6. If using `Mono<Void>`, does the caller need to know the number of affected rows?
7. Do the service and API layers map empty and error signals according to the contract?
8. Is the publisher chained and returned completely instead of calling `subscribe()` inside the service?

You can use these reference guidelines:

| Intent | Return type |
|---|---|
| Find one entity, may not exist | `Mono<T>` |
| Find multiple entities | `Flux<T>` |
| Search where no results is normal | Empty `Flux<T>` |
| Entity must exist | `Mono<T>` combined with `switchIfEmpty` in service |
| Check existence | `Mono<Boolean>` |
| Count records | `Mono<Long>` |
| Command needing no payload | `Mono<Void>` |
| Command needing affected row count | `Mono<Integer>` or appropriate result type |
| Small list needing collection | `Flux<T>.collectList()` at processing layer |
| Query needing verification of at most one row | `Mono<T>` or appropriate `one()` API |

## 16. Key Takeaways

- Return types are part of the repository contract: they describe cardinality and how results are represented.
- `Mono<T>` represents zero to one element; `Flux<T>` represents zero to many elements.
- Empty publishers complete normally; database errors are propagated via `onError`.
- `Mono<T>` does not guarantee an entity is always present, nor does it replace a unique constraint.
- `Flux<T>` suits result sets and enables streaming processing; only collect into a list when data is reasonably bounded.
- `Mono<Void>` represents an operation completing without a payload; if affected row count is needed, choose a return type that carries data.
- A SQL NULL in a property is different from a query returning no rows.
- Use `switchIfEmpty` for business rules requiring data; do not turn every error into empty.
- Reactive repositories return publishers; chain publishers and return the complete pipeline rather than calling `subscribe()` in services.
- Service and API layers decide how to translate empty into defaults, domain errors, empty lists, or HTTP responses.
