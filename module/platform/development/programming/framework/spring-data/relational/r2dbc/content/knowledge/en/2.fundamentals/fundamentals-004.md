# Mono and Flux When Representing Query Results

In Spring Data Relational R2DBC, query operations are represented using Project Reactor's reactive types. The two types that appear most frequently are `Mono<T>` and `Flux<T>`. Choosing the right return type expresses how many records a query can produce while allowing repository, service, and web layers to continue processing data reactively without blocking threads to wait for results.

The key point to remember is that `Mono` and `Flux` describe a stream of signals to be consumed in the future. They are not containers holding results already fetched at the moment the method is called.

## 1. Why Does Spring Data R2DBC Use Mono and Flux?

R2DBC provides a reactive API for accessing relational databases. Spring Data R2DBC builds repositories and row-to-entity mapping on top of that API. Consequently, query methods typically return a publisher instead of returning entities or collections synchronously.

Project Reactor provides two primary publisher types:

- `Mono<T>`: represents a stream that can emit at most one item of type `T`.
- `Flux<T>`: represents a stream that can emit zero, one, or many items of type `T`.

Both conform to Reactive Streams. A publisher can emit data signals and then terminate with a completion signal or an error signal. When working with repositories, the application typically receives a publisher, chains processing steps, and returns the publisher for the next component to subscribe to and consume.

For example, calling `repository.findById(id)` produces a `Mono<Customer>`. The application can map the entity to a DTO, add handling for when no data is found, or combine it with another query before the publisher is subscribed to.

## 2. Mono: Results with at Most One Item

`Mono<T>` is suitable when a query is expected to return no more than one record. There are two normal outcome cases:

1. The query finds no record: the publisher completes without emitting any item, often referred to as `Mono.empty()`.
2. The query finds one record: the publisher emits one item and then completes.

A `Mono` can also terminate with an error, such as a database connection failure or a data mapping error. Therefore, `Mono<T>` does not guarantee that a value will be present.

Example creating a publisher:

```java
Mono<Customer> customer = customerRepository.findById(42L);
```

If identifier `42` exists, the publisher emits one `Customer`. If it does not exist, the publisher completes empty. No `null` value is emitted to represent the not-found case.

### Common Uses for Mono

- Finding one entity by primary key, e.g., `findById(id)`.
- Finding by an attribute guaranteed to be unique, such as an email or product code.
- Returning an aggregate value such as a record count or existence check result.
- Representing completion of an operation that does not need to return an entity, commonly using `Mono<Void>`.

Several methods inherited from `ReactiveCrudRepository` illustrate this usage clearly:

```java
Mono<Customer> findById(Long id);
Mono<Customer> save(Customer customer);
Mono<Void> deleteById(Long id);
```

`Mono<Void>` is still a publisher. It emits no entity or data value; the completion signal indicates the operation finished, while the error signal indicates it failed.

## 3. Flux: Results That May Include Multiple Items

`Flux<T>` is appropriate when a query may return multiple records. Each database row is mapped to an item and emitted in the stream. A `Flux` can:

- Complete immediately without emitting any items if no rows match.
- Emit one item and then complete.
- Emit many items and then complete.
- Terminate with an error if the query or processing encounters a problem.

Example:

```java
Flux<Customer> customers = customerRepository.findAll();
```

This publisher represents the set of customers returned by the query. When consumed, the application can process each customer using operators such as `map`, `filter`, or `flatMap`.

Common methods on `ReactiveCrudRepository` demonstrate this rule:

```java
Flux<Customer> findAll();
Flux<Customer> findAllById(Iterable<Long> ids);
Flux<Customer> saveAll(Iterable<Customer> customers);
```

For queries capable of returning multiple rows, using `Flux<T>` keeps results in streaming form. The application can process items as they are emitted instead of being forced to collect the entire result into a collection before starting work.

## 4. Choosing the Return Type by Result Cardinality

The return type should reflect how many results the business logic and query allow. Do not pick a type merely to match some API convenience in the caller layer.

| Query Need | Common Return Type | Meaning |
| --- | --- | --- |
| Find by primary key | `Mono<Customer>` | Zero or one entity |
| Find by an email guaranteed unique | `Mono<Customer>` | Zero or one entity |
| Find all customers by status | `Flux<Customer>` | Potentially multiple entities |
| Count customers | `Mono<Long>` | A single count value |
| Check whether an email exists | `Mono<Boolean>` | A single boolean value |
| Delete an entity by ID | `Mono<Void>` | Only interested in completion or error |
| Save multiple entities | `Flux<Customer>` | Can emit each saved entity |

Example of a repository with both single-result and multi-result queries:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatusOrderByCreatedAtDesc(String status);

    Mono<Long> countByStatus(String status);

    Mono<Boolean> existsByEmail(String email);
}
```

In this example, `findByEmail` should return `Mono<Customer>` only when email is genuinely unique under data rules. There should be a corresponding unique constraint in the database to protect that rule, even when data is written by another application or process.

If a method returns `Mono<Customer>` yet the underlying query can actually match multiple rows, execution may throw a result-size error such as `IncorrectResultSizeDataAccessException`. Do not use `Mono` to mask possible duplicate data. Clarify the business rule, enforce uniqueness in the database, or switch the method to `Flux` if multiple results are valid.

## 5. Using Mono and Flux with Derived Queries and `@Query`

Spring Data R2DBC can derive queries from repository method names. The return type indicates whether the method expects one result or multiple results:

```java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    Mono<Product> findBySku(String sku);

    Flux<Product> findByCategoryIdOrderByNameAsc(Long categoryId);
}
```

The first method is appropriate if SKU is unique. The second method can return multiple products belonging to the same category.

For custom SQL queries declared with `@Query`, the same return-type selection rules apply:

```java
public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    @Query("SELECT * FROM product WHERE sku = :sku")
    Mono<Product> findOneBySku(String sku);

    @Query("SELECT * FROM product WHERE category_id = :categoryId ORDER BY name")
    Flux<Product> findAllByCategory(Long categoryId);
}
```

The first query's SQL is designed to look up one product by a unique SKU. The second query can return multiple rows, so it uses `Flux<Product>`. The `ORDER BY` clause makes result ordering explicit; if SQL does not specify ordering, the application should not assume the database always returns rows in a fixed order.

## 6. Handling Empty Results and Composing Publishers

In reactive programming, finding no data is normally represented by an empty publisher, not `null`. How to handle it depends on business logic.

### Converting an Empty Result into a Business Error

```java
public Mono<Customer> getRequiredCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ));
}
```

`switchIfEmpty` subscribes to an alternative publisher when the initial publisher completes without emitting an item. This is useful when the service layer requires the entity to exist.

### Providing a Default Value

```java
public Mono<String> getCustomerName(Long id) {
    return customerRepository.findById(id)
            .map(Customer::getName)
            .defaultIfEmpty("Unknown customer");
}
```

`defaultIfEmpty` emits a default value if the publisher is empty. The default value must make sense for the business logic; do not use it to hide query errors or connection failures.

### Transforming Each Item in a Flux

```java
public Flux<CustomerView> findActiveCustomers() {
    return customerRepository.findByStatusOrderByCreatedAtDesc("ACTIVE")
            .map(customerMapper::toView);
}
```

`map` is applied to each item emitted by the `Flux`. If there are no matching customers, the result remains an empty `Flux` and the mapping function is never invoked.

When another reactive operation must be invoked for each item, `flatMap` can be used:

```java
return customerRepository.findAll()
        .flatMap(customer ->
                addressRepository.findByCustomerId(customer.getId())
                        .map(address -> customerMapper.toView(customer, address))
        );
```

`flatMap` merges inner publishers into a single result stream. If emission order is a business requirement, choose an operator suited to ordering requirements and weigh the cost of sequential processing; do not assume every use of `flatMap` preserves source order.

## 7. How Do `Mono<List<T>>` and `Flux<T>` Differ?

Sometimes an application needs a complete list. In that case, a `Flux<T>` can be collected into a `Mono<List<T>>` using `collectList()`:

```java
Mono<List<Customer>> allCustomers =
        customerRepository.findAll().collectList();
```

These two types have different semantics:

| Type | Emission Pattern | Consumption Consequence |
| --- | --- | --- |
| `Flux<Customer>` | Emits each customer individually | Items can be processed one by one as the stream continues |
| `Mono<List<Customer>>` | Emits one list after collection finishes | Collected items must be held in memory until the list is complete |

If there are no customers, `Flux<Customer>` completes without emitting items; `collectList()` turns that into a `Mono` emitting an empty list. When data is present, the list is emitted only after collection completes.

Use `collectList()` only when the caller genuinely needs a complete collection and the result count is reasonably bounded. For queries that can return large datasets, collecting everything into one list can consume significant memory and forfeit the streaming benefits of `Flux`.

## 8. Converting Flux to Mono: Understand the Semantics Clearly

Reactor provides several operators for turning a `Flux<T>` into a `Mono<T>`. They are not equivalent:

```java
Mono<Customer> firstCustomer =
        customerRepository.findAll().next();

Mono<Customer> zeroOrOneCustomer =
        customerRepository.findAll().singleOrEmpty();
```

- `next()` takes the first emitted item and stops consuming the stream. It does not verify that the query produced only one result.
- `singleOrEmpty()` allows zero or one item; if the stream emits more than one item, it signals an error.
- `single()` requires exactly one item; it signals an error if the stream is empty or has more than one item.

Therefore, if business logic requires confirming that a result is unique, `singleOrEmpty()` expresses intent more accurately than `next()`. Using `next()` is appropriate only when the requirement is genuinely to take the first item—for example, a query with an `ORDER BY` and limit tailored to that purpose.

## 9. When Does a Publisher Execute?

When calling a repository method and receiving a `Mono` or `Flux`, the application receives a reactive description of work. For query publishers created by Spring Data R2DBC, the database operation typically begins when a subscriber consumes the publisher.

Example:

```java
Mono<Customer> customerPublisher =
        customerRepository.findById(42L);

Mono<String> namePublisher =
        customerPublisher.map(Customer::getName);
```

These two lines build the publisher and attach processing steps. In a Spring WebFlux application, a controller can return the publisher to the framework; the framework subscribes and handles results over the request lifecycle.

A publisher is not a variable holding already-queried results. If a cold publisher is subscribed to multiple times, each subscription can re-execute the query. Thus, do not assume that storing a `Mono` in a variable means the previous query's result has been cached.

## 10. Returning Mono and Flux from Service or WebFlux Layers

The service layer can preserve reactive types so higher layers can continue composing publishers:

```java
public Mono<CustomerView> findCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ))
            .map(customerMapper::toView);
}

public Flux<CustomerView> findCustomersByStatus(String status) {
    return customerRepository.findByStatusOrderByCreatedAtDesc(status)
            .map(customerMapper::toView);
}
```

A Spring WebFlux controller can return these types directly:

```java
@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerRepository customerRepository;

    public CustomerController(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    @GetMapping("/{id}")
    public Mono<ResponseEntity<Customer>> findById(@PathVariable Long id) {
        return customerRepository.findById(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.<Customer>notFound().build());
    }

    @GetMapping
    public Flux<Customer> findAll() {
        return customerRepository.findAll();
    }
}
```

In the detail endpoint, `Mono<Customer>` allows mapping a found record into an OK response or creating a not-found response when the publisher is empty. In the list endpoint, `Flux<Customer>` represents a result set that may include multiple customers. WebFlux is responsible for subscribing to the publisher during request handling.

## 11. Avoiding `block()` and `subscribe()` in Reactive Processing Flows

Do not call `block()` inside an application's reactive processing chain:

```java
Customer customer = customerRepository.findById(id).block();
```

`block()` waits for the result by blocking the current thread. This defeats the non-blocking advantage of R2DBC and can cause thread starvation when many requests wait on the database concurrently. In reactive services or controllers, return and compose `Mono` or `Flux` rather than extracting results synchronously.

Also avoid calling `subscribe()` manually inside a service just to kick off a query:

```java
public void updateSomething(Long id) {
    customerRepository.findById(id).subscribe(customer -> {
        // Processing is detached from the stream managed by the caller
    });
}
```

By subscribing manually, the service detaches execution from any publisher received by the caller. The caller struggles to coordinate completion timing, error handling, and transaction context. Return the publisher from the method instead:

```java
public Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
```

`block()` may still appear at controlled imperative boundaries or in certain tests, but it should not be placed on reactive request-handling paths.

## 12. Backpressure and Multi-Row Queries

`Flux` supports Reactive Streams backpressure: subscribers can regulate how many items they wish to receive. This helps pipeline components coordinate processing rates when working with multi-item streams.

However, using `Flux` does not automatically guarantee that the entire data path is free of buffering or always uses constant memory. Batch reading, buffering, and fetching behaviors depend on the R2DBC driver, the database, and how the query executes. Applications still need to consider result sizes, query limits, and per-item processing.

For instance, with a large customer list, keeping results as `Flux<Customer>` and processing item by item is usually better than calling `collectList()` and holding the entire list in memory. If the UI needs only a subset of data, design a bounded or paginated query instead of loading the entire table.

## 13. Testing Mono and Flux Behavior

Reactor Test's `StepVerifier` can verify the signals emitted by a publisher. Example testing a single-item query:

```java
StepVerifier.create(customerRepository.findById(42L))
        .expectNextMatches(customer -> customer.getId().equals(42L))
        .verifyComplete();
```

And testing a multi-result query:

```java
StepVerifier.create(customerRepository.findByStatus("ACTIVE"))
        .expectNextCount(2)
        .verifyComplete();
```

In addition to emitted values, reactive tests should cover empty publisher cases and error termination cases. For example, primary-key lookups should have tests for nonexistent IDs; queries expected to be unique should test how the system reacts if data violates the uniqueness assumption.

## 14. Common Mistakes

1. **Assuming `Mono` always has a result.** `Mono<T>` allows zero results; not-found cases are normally `Mono.empty()`.
2. **Using `Mono` for queries that can return multiple rows.** The return type should match the query's cardinality and data rules.
3. **Using `next()` to pretend results are unique.** `next()` simply takes the first item; it does not detect duplicate data.
4. **Treating `Flux` like an already-populated `List`.** `Flux<T>` is a publisher emitting items over consumption time; obtaining a complete list requires explicit collection.
5. **Calling `collectList()` for every query.** Collecting everything can consume excessive memory and lose item-by-item streaming benefits.
6. **Using `block()` or `subscribe()` indiscriminately.** Both can break reactive coordination among repositories, services, and frameworks.
7. **Assuming `Flux` always has a fixed order.** If business logic depends on SQL row ordering, specify `ORDER BY`.
8. **Confusing empty results with query errors.** Finding no matching rows is a valid outcome; connection or SQL failures are delivered via the `onError` signal.

## Quick Selection Rules

- Choose `Mono<T>` when a query returns zero or one value, such as finding by primary key or unique attribute.
- Choose `Flux<T>` when a query can return multiple entities, such as finding all records by status.
- Choose `Mono<Long>` or `Mono<Boolean>` for single scalar results like counts or existence checks.
- Choose `Mono<Void>` when you only need to know whether an operation completed or failed.
- Convert `Flux<T>` to `Mono<List<T>>` only when a complete list is required and the data volume is manageable.

When designing a Spring Data R2DBC repository, start by asking how many rows the query can return. Then choose the appropriate `Mono` or `Flux` type and preserve reactive types across processing layers. This clarifies the method's data contract, handles missing-data cases properly, and preserves a non-blocking database access model.
