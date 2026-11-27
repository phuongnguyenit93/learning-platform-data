# Selecting Single Entities, Multiple Entities, and Empty Results

In Spring Data Relational R2DBC, data read operations typically return Reactor publishers. The return type indicates whether the application expects a single entity, a collection of entities, or potentially no matching rows. Choosing the right return type ensures clean handling of found, not-found, and unexpected cardinality scenarios.

The two most commonly used types are `Mono<T>` and `Flux<T>`:

- `Mono<T>` represents a result with at most one element. The publisher may emit one entity and complete, or complete empty if there is no result.
- `Flux<T>` represents zero to many elements. The publisher emits each entity and completes; if no rows match, it completes without emitting any elements.

Having no results does not equal an error. A query finding no matching records is often a valid business outcome. Conversely, connection failures, SQL errors, or mapping errors are propagated as reactive error signals.

This lesson explains how to read one entity, read multiple entities, handle empty results, distinguish single-row queries from limit-one queries, and choose the right API among repositories, `@Query`, and `DatabaseClient`.

## 1. Mono and Flux Representing Query Results

In Reactor, a publisher can emit data, complete, or terminate with an error. The maximum number of elements is the fundamental distinction between `Mono` and `Flux`.

| Return Type | Element Count | When No Rows Match |
|---|---:|---|
| `Mono<T>` | 0 or 1 | Completes empty (`Mono.empty()`) |
| `Flux<T>` | 0 to many | Completes empty, emitting no elements |
| `Mono<List<T>>` | One list | Emits an empty list if the query returns no rows |
| `Mono<Boolean>` | One boolean value | Emits `true` or `false` depending on the check |

Illustrative example:

~~~text
Query by ID, one row found:
Mono<Customer>  ---- Customer ---- complete

Query by ID, no rows found:
Mono<Customer>  ------------------ complete (empty)

Query by condition, multiple rows found:
Flux<Customer>  -- C1 -- C2 -- C3 -- complete

Query by condition, no rows found:
Flux<Customer>  ------------------ complete (empty)
~~~

`Mono<T>` is not an object that can emit `null` to represent not-found. Reactor forbids emitting `null`; the absence of an element is represented by an empty publisher.

Similarly, an empty `Flux<T>` is still a normally completed publisher. Do not throw an exception merely because a result list has zero items, unless business rules require at least one record.

## 2. Reading a Single Entity with ReactiveCrudRepository

`ReactiveCrudRepository<T, ID>` provides common read operations for reactive repositories. For an entity with a primary key, `findById` normally returns `Mono<T>`.

Example entity:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Column("full_name")
    private String fullName;

    @Column("email_address")
    private String email;

    // Constructor, getters, and setters
}
~~~

Repository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

Reading one customer by ID:

~~~java
Mono<Customer> findCustomer(Long id) {
    return customerRepository.findById(id);
}
~~~

If a row with the given ID exists, the publisher emits a `Customer`. If not, the publisher completes empty. The repository returns a publisher; the query executes only when subscribed to by the framework or a caller-side subscriber.

### 2.1. Handling Not-Found Cases

You can use `switchIfEmpty` to replace an empty publisher with another publisher:

~~~java
Mono<Customer> getCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)));
}
~~~

This snippet turns a not-found result into a business error. It fits endpoints that require the resource to exist, such as fetching customer details by ID.

If not finding a record is a normal outcome, you can leave `Mono.empty()` as-is and let the caller decide how to respond.

Another option is returning a default value:

~~~java
Mono<Customer> getCustomerOrDefault(Long id) {
    return customerRepository.findById(id)
            .defaultIfEmpty(Customer.guest());
}
~~~

Only use a default value when business rules genuinely define a fallback object. Do not silently fabricate a dummy entity to mask missing data, as callers might mistake it for a persisted record in the database.

### 2.2. Distinguishing Not-Found from Query Errors

Not-found typically produces an empty publisher. Database failures produce an error signal:

~~~java
return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(
                new CustomerNotFoundException(id)))
        .onErrorMap(
                DataAccessException.class,
                DatabaseOperationException::new);
~~~

Do not use `onErrorResume` to turn every database error into `Mono.empty()`. Doing so can turn connection or SQL errors into a "not found" response, obscuring the real root cause.

Classify errors by their meaning:

- No matching rows: empty publisher.
- Database unreachable: error publisher.
- Invalid SQL or mapping mismatch: error publisher.
- Business rule does not allow a missing entity: explicitly convert the empty publisher to a domain error.

## 3. Reading Multiple Entities with Flux

When a query condition can match multiple rows, use `Flux<T>`. Repository example:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Flux<Customer> findByCity(String city);

    Flux<Customer> findByActiveTrue();

    Flux<Customer> findByLastNameContaining(String keyword);
}
~~~

These methods can emit zero, one, or many customers. If no customers match, they complete empty.

Usage example:

~~~java
Flux<Customer> customersInHanoi =
        customerRepository.findByCity("Hanoi");
~~~

No `null` check is needed before iterating results. An empty `Flux` simply emits no `onNext` signals; the subscriber still receives the completion signal.

### 3.1. Iterating and Processing Each Element

Each entity can be processed using Reactor operators:

~~~java
Flux<String> customerNames =
        customerRepository.findByCity("Hanoi")
                .map(Customer::getFullName);
~~~

If you need to invoke a reactive operation per entity, use `flatMap`:

~~~java
Flux<CustomerSummary> summaries =
        customerRepository.findByCity("Hanoi")
                .flatMap(customer ->
                        summaryService.createSummary(customer));
~~~

`flatMap` allows inner publishers to run concurrently and results may not preserve source ordering. If sequential processing and order preservation are needed, consider `concatMap`. If you need to bound concurrency, use the overload with an appropriate concurrency parameter.

Never call `subscribe()` inside `map` or `flatMap` to launch an independent stream. Return the publisher from the callback so Reactor manages the full chain.

### 3.2. Collecting Results into a List

If the result set is small and the caller needs a complete list, you can use `collectList`:

~~~java
Mono<List<Customer>> findCustomersAsList(String city) {
    return customerRepository.findByCity(city)
            .collectList();
}
~~~

`collectList()` always emits a list when the source completes successfully. If there are no rows, the emitted list is empty:

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

Unlike `Mono<Customer>`, `Mono<List<Customer>>` in this case is not empty when the query returns zero rows; it emits an empty list. If the query fails, the error still propagates to the subscriber.

Do not use `collectList()` for unbounded or very large result sets. All entities will be held in memory until the source completes. For large datasets, stream element by element or paginate as needed.

## 4. Built-in Repository Read Methods

Common methods from `ReactiveCrudRepository`:

| Method | Return Type | Meaning |
|---|---|---|
| `findById(id)` | `Mono<T>` | Reads at most one entity by primary key |
| `findById(publisherOfId)` | `Mono<T>` | Reads by an ID emitted by a publisher |
| `findAll()` | `Flux<T>` | Reads all entities |
| `findAllById(ids)` | `Flux<T>` | Reads entities whose IDs are in the input collection |
| `existsById(id)` | `Mono<Boolean>` | Checks whether an entity exists |
| `count()` | `Mono<Long>` | Counts the entities |
| `deleteById(id)` | `Mono<Void>` | Deletes by ID without emitting the deleted entity |

Notes:

- `findAll()` can return a very large number of rows. Consider pagination or filter conditions instead of loading an entire table.
- `findAllById(...)` returns found entities; nonexistent IDs do not produce dummy entities or `null` elements.
- `existsById(...)` is appropriate when you only need to know whether a record exists without loading the full entity.
- `count()` returns `0` when the table or dataset has no matching rows.
- `deleteById(...)` completes without emitting data; if you need to know whether a record was deleted, design a separate check.

### 4.1. Checking Existence Instead of Loading Entities

If you only need to answer "does this ID exist?", use:

~~~java
Mono<Boolean> customerExists(Long id) {
    return customerRepository.existsById(id);
}
~~~

There is no need to load the whole entity just to check `customer != null`. `existsById` expresses the intent accurately and allows the framework to optimize the query for the database.

For custom conditions, you can declare a derived query:

~~~java
Mono<Boolean> existsByEmail(String email);
~~~

### 4.2. Counting Results

Example:

~~~java
Mono<Long> countActiveCustomers() {
    return customerRepository.countByActiveTrue();
}
~~~

Count methods return `0` when no records match. That is an emitted result value, not an empty publisher. Distinguish `Mono<Long>` emitting `0L` from `Mono.empty()`.

## 5. Derived Queries: Choosing Mono or Flux by Data Semantics

Spring Data can generate queries from repository method names. The return type should reflect the expected business result count.

Example:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByCity(String city);

    Mono<Customer> findFirstByCityOrderByCreatedAtDesc(String city);

    Flux<Customer> findTop10ByCityOrderByCreatedAtDesc(String city);
}
~~~

How to read these:

- `findByEmail`: uses `Mono<Customer>` if email is expected to be unique.
- `findByCity`: uses `Flux<Customer>` because a city can have many customers.
- `findFirstByCityOrderByCreatedAtDesc`: retrieves at most the first customer ordered by newest creation time.
- `findTop10ByCityOrderByCreatedAtDesc`: limits the result to at most ten customers in the specified order.

If a method returns `Mono<Customer>` but the actual query matches multiple rows, Spring Data may throw an incorrect result size error rather than picking an arbitrary entity. This helps catch mismatches between the "single result" expectation and actual data.

### 5.1. Enforcing Uniqueness in the Database

If email must be unique, do not rely solely on the repository returning `Mono<Customer>`. Add a `UNIQUE` constraint in the database:

~~~sql
ALTER TABLE customer
ADD CONSTRAINT uk_customer_email UNIQUE (email_address);
~~~

If you only check before inserting:

~~~java
return customerRepository.existsByEmail(email)
        .flatMap(exists -> {
            if (exists) {
                return Mono.error(
                        new DuplicateEmailException(email));
            }

            return customerRepository.save(customer);
        });
~~~

Two concurrent requests can still both receive `false` before either inserts. A `UNIQUE` constraint is the ultimate safeguard. The application must handle unique constraint violation errors on save.

### 5.2. When Business Logic Needs the First Record

If there are multiple rows and business logic truly needs the first one, specify a clear ordering:

~~~java
Mono<Customer> findNewestCustomer(String city) {
    return customerRepository
            .findFirstByCityOrderByCreatedAtDesc(city);
}
~~~

Do not run a query without `ORDER BY` and assume the first row is always the newest or deterministic. SQL row order is not guaranteed unless sorting is explicitly requested.

Method names with `First` or `Top` express result-limiting intent. Even if you only need an arbitrary row, defining a business-appropriate tie-breaker makes the outcome predictable.

## 6. Custom Queries with @Query

With custom SQL, the return type still determines how the application receives results.

Querying a single customer by email:

~~~java
@Query("""
    SELECT id, full_name, email_address
    FROM customer
    WHERE email_address = :email
    """)
Mono<Customer> findOneByEmail(@Param("email") String email);
~~~

Querying multiple customers by city:

~~~java
@Query("""
    SELECT id, full_name, email_address
    FROM customer
    WHERE city = :city
    ORDER BY full_name
    """)
Flux<Customer> findAllByCity(@Param("city") String city);
~~~

In the first case, the query expects at most one row. If the data contains multiple rows with the same email, a result size error may occur; enforce a unique constraint if email must be unique.

In the second case, every matching row is emitted sequentially through `Flux`. If there are no rows, `Flux` completes empty.

Never concatenate user input directly into SQL strings. Use named parameters or parameter binding to pass values. Table and column names in SQL must match the physical schema; entity mapping annotations do not rewrite custom SQL literals automatically.

## 7. Reading Results with DatabaseClient

`DatabaseClient` lets you execute SQL directly and choose how to consume results based on row count.

Example reading at most one row:

~~~java
Mono<Customer> findCustomer(Long id) {
    return databaseClient.sql("""
            SELECT id, full_name, email_address
            FROM customer
            WHERE id = :id
            """)
            .bind("id", id)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("full_name", String.class),
                    row.get("email_address", String.class)))
            .one();
}
~~~

`one()` expresses the expectation of at most one row. If there are no rows, the publisher completes empty. If there is more than one row, the API signals an error instead of picking a row arbitrarily.

Reading the first row:

~~~java
Mono<Map<String, Object>> firstCustomer =
        databaseClient.sql("""
                SELECT id, full_name, email_address
                FROM customer
                WHERE city = :city
                ORDER BY created_at DESC
                """)
                .bind("city", "Hanoi")
                .fetch()
                .first();
~~~

`first()` returns the first row if present, or an empty publisher if there are no rows. It does not assert that only one row matched. If order matters, the SQL must include `ORDER BY`.

Reading all rows:

~~~java
Flux<Map<String, Object>> customers =
        databaseClient.sql("""
                SELECT id, full_name, email_address
                FROM customer
                WHERE city = :city
                ORDER BY full_name
                """)
                .bind("city", "Hanoi")
                .fetch()
                .all();
~~~

`all()` returns a `Flux` of rows. If the query returns no rows, `Flux` completes empty.

### 7.1. Distinguishing one() and first()

| API | No Rows | Exactly One Row | Multiple Rows |
|---|---|---|---|
| `one()` | Completes empty | Emits that row | Errors because more than one row returned |
| `first()` | Completes empty | Emits that row | Emits the first row without requiring uniqueness |
| `all()` | Empty Flux | Emits one row | Emits all rows |

This is an important distinction when designing queries. If business logic requires uniqueness, `one()` helps catch duplicate data. If business logic simply needs the top row in priority order, `first()` or an explicitly limited query is more suitable.

## 8. Converting Multi-Row Publishers to a Single Result

Sometimes an API or service layer receives a `Flux<T>` and needs to convert it into a single result. Reactor provides several operators, each with its own cardinality rules.

| Operator | Zero Elements | One Element | Multiple Elements |
|---|---|---|---|
| `next()` | `Mono.empty()` | Emits that element | Takes the first element and cancels the rest |
| `single()` | Error | Emits that element | Error |
| `singleOrEmpty()` | `Mono.empty()` | Emits that element | Error |
| `collectList()` | Emits empty list | Emits one-element list | Emits list containing all elements |

Example using `singleOrEmpty`:

~~~java
Mono<Customer> findExactlyOneOrNone(String city) {
    return customerRepository.findByCity(city)
            .filter(Customer::isPreferred)
            .singleOrEmpty();
}
~~~

If there is no preferred customer, the result is `Mono.empty()`. If there is exactly one, the publisher emits the entity. If there is more than one, the publisher errors so the application detects that the data violates expectations.

Use `next()` when business logic intentionally accepts taking the first element:

~~~java
Mono<Customer> findAnyCustomer(String city) {
    return customerRepository.findByCity(city)
            .next();
}
~~~

`next()` does not check uniqueness. If the dataset has multiple rows, remaining rows are discarded after the first element. Thus, never use `next()` to hide a violated uniqueness constraint.

`single()` requires strictly one element; both empty and multiple-element cases are errors. Use it when business logic mandates exactly one result and wants any deviation treated as an error.

## 9. No Rows vs. Columns with NULL Values

Distinguish between two scenarios:

1. The query returns zero rows.
2. The query returns a row, but one column in that row has SQL `NULL`.

For example, a table has a customer without a phone number entered:

~~~sql
SELECT id, full_name, phone_number
FROM customer
WHERE id = 10;
~~~

If the row exists and `phone_number` is `NULL`, Spring Data can still instantiate a `Customer`. The corresponding `phoneNumber` property receives Java `null` if the type and mapping allow it.

The result is `Mono<Customer>` emitting an entity with `phoneNumber == null`, not `Mono.empty()`.

Conversely, if no row has ID 10, `Mono<Customer>` completes empty.

| Scenario | Reactive Result |
|---|---|
| No rows found | `Mono.empty()` |
| Row found, nullable column is SQL `NULL` | `Mono` emits entity with the corresponding property set to null |
| Row found, all values valid | `Mono` emits entity |
| Database or SQL error | `Mono` emits error signal |

Do not use `defaultIfEmpty` to replace a null column inside an entity; that operator handles a publisher that emits no elements, not individual null properties. To substitute null column values, use SQL `COALESCE`, a custom conversion, or logic after the entity is mapped.

## 10. Handling Empty Results in the Service and API Layers

How empty results are handled depends on the semantics of the endpoint or use case.

### 10.1. Resource Required to Exist

Example endpoint retrieving customer details by ID:

~~~java
public Mono<CustomerResponse> getCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)))
            .map(CustomerResponse::from);
}
~~~

The web layer can map `CustomerNotFoundException` to HTTP 404 via an exception handler. The repository does not need to know HTTP status codes; it simply represents missing data with an empty publisher.

### 10.2. Searches That May Return No Results

Example searching customers by city:

~~~java
public Flux<CustomerResponse> searchCustomers(String city) {
    return customerRepository.findByCity(city)
            .map(CustomerResponse::from);
}
~~~

If there are no customers, `Flux` completes normally. Returning an empty list from the endpoint is a valid response; do not convert that case into 404 unless the API contract specifies otherwise.

If the controller layer collects results into a list, it can emit `[]` when no rows are found.

### 10.3. Providing a Default Value

For example, an optional setting may fall back to a default when no record exists:

~~~java
Mono<AppSetting> loadSetting(String key) {
    return settingRepository.findById(key)
            .defaultIfEmpty(AppSetting.defaultFor(key));
}
~~~

Only use defaults when default values are part of the business rules. For critical data such as accounts, orders, or permissions, fabricating fallback values can hide data errors.

### 10.4. Checking Emptiness with hasElement

If you need to know whether a publisher emits an element, you can use:

~~~java
Mono<Boolean> hasCustomer =
        customerRepository.findById(10L)
                .hasElement();
~~~

`hasElement()` emits `true` if the source has at least one element and `false` if it completes empty. For primary-key checks, `existsById` usually expresses intent better. For an existing processing chain, `hasElement()` can be useful.

## 11. Combining Multiple Queries and Empty Results

In a reactive pipeline, empty results affect downstream operators.

### 11.1. flatMap Only Runs When Mono Has an Element

~~~java
Mono<OrderResponse> loadOrder(Long id) {
    return orderRepository.findById(id)
            .flatMap(order ->
                    customerRepository.findById(order.getCustomerId())
                            .map(customer ->
                                    OrderResponse.from(order, customer)));
}
~~~

If the order is not found, the `flatMap` callback never runs. If the order is found but the customer is not found, the inner publisher is also empty and the final result is empty.

If the customer is mandatory data, turn that case into an error:

~~~java
Mono<OrderResponse> loadOrder(Long id) {
    return orderRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new OrderNotFoundException(id)))
            .flatMap(order ->
                    customerRepository.findById(order.getCustomerId())
                            .switchIfEmpty(Mono.error(
                                    new CustomerNotFoundException(
                                            order.getCustomerId())))
                            .map(customer ->
                                    OrderResponse.from(order, customer)));
}
~~~

This style makes it clear which entity does not exist and prevents empty results from propagating without the caller knowing why.

### 11.2. zip and Empty Publishers

`Mono.zip` combines publishers when every source provides a value. If one source completes empty, the combination can complete empty without producing a tuple.

~~~java
Mono<CustomerDashboard> dashboard =
        customerRepository.findById(customerId)
                .zipWith(orderRepository.findLatestByCustomerId(customerId))
                .map(tuple ->
                        CustomerDashboard.from(
                                tuple.getT1(), tuple.getT2()));
~~~

If either the customer or the latest order is missing, the combined result can be empty. Decide for each piece of data whether it is mandatory or optional:

- Mandatory data: use `switchIfEmpty(Mono.error(...))`.
- Optional data: substitute a meaningful default publisher or explicitly represent the optional field in the response.
- Never use dummy values if doing so blurs the distinction between "no data" and "default data".

## 12. Limiting Results and Pagination

You should not always read all results with `findAll()`. When tables are large, limit row counts and define ordering.

Derived queries can limit result counts:

~~~java
Flux<Customer> findTop20ByActiveTrueOrderByCreatedAtDesc();
~~~

With custom SQL, use the limit syntax appropriate for your database:

~~~sql
SELECT id, full_name, email_address
FROM customer
WHERE active = TRUE
ORDER BY created_at DESC
LIMIT 20;
~~~

`LIMIT` is common in PostgreSQL and MySQL; other engines may use different syntax. Spring Data R2DBC does not rewrite hand-written SQL queries into portable syntax across every database.

If an API needs pagination, clearly decide between offset/page or keyset pagination and how total counts are obtained. The page query and count query are typically two separate operations. For continuously changing data, offset pagination can skip or duplicate records across pages; keyset pagination based on a stable sort key is often better suited for large datasets.

Do not convert a large `Flux` into a `List` just to paginate in memory. Let the database limit the data directly inside the query.

## 13. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Returning `Mono<T>` for a query that inherently has multiple results | May raise an incorrect result size error | Use `Flux<T>` if multiple rows are valid |
| Using `Flux<T>` for a strictly unique query without checks | Can mask duplicate data | Use `Mono<T>` and a unique constraint |
| Using `next()` to hide multiple results | Only takes the first row and drops the rest | Use `one()` or `singleOrEmpty()` if confirming at most one |
| Treating `Mono.empty()` as a database error | Mishandles not-found cases | Distinguish empty publishers from error signals |
| Turning all errors into empty via `onErrorResume` | Masks SQL or connection failures | Handle only specific error types and preserve unexpected errors |
| Using `defaultIfEmpty(null)` | Reactor cannot emit null values | Use an empty publisher or a valid default value |
| Confusing SQL NULL columns with zero rows | Loses information about actual records | Inspect the emitted entity and nullable properties |
| Using `collectList()` on very large datasets | Increases memory usage and latency | Stream `Flux` or paginate at the database |
| Calling `findAll()` on large tables | Loads too much data | Add filters, limits, or pagination |
| Using `first()` without ordering | Selected row may be non-deterministic | Use `ORDER BY` or a sorted derived query |
| Checking existence before insert without a unique constraint | Two concurrent requests can create duplicates | Protect with a constraint and handle insert errors |
| Calling `subscribe()` inside services | Creates a stream detached from the returned chain | Return the publisher and compose with Reactor operators |

## 14. Process for Choosing Return Types and Handling Results

When declaring a read method, answer these questions in order:

1. Can the query condition match multiple rows?
2. If at most one row is expected, is uniqueness enforced by a database key or constraint?
3. If no rows match, is that a normal result, a default value, or a business error?
4. Does the caller need to process each entity, a single entity, or a collected list?
5. Is the dataset small enough for `collectList()`, or are limits/pagination needed?
6. If picking the first row, is the order defined via `ORDER BY`?
7. If using a custom query, does the SQL match the schema and bind parameters safely?

You can use the following guide:

| Need | Option |
|---|---|
| Find by ID, may not exist | `Mono<T>` with `findById` |
| Find by a business key guaranteed unique | `Mono<T>` and a unique constraint |
| Find all rows matching a condition | `Flux<T>` |
| Only check existence | `Mono<Boolean>` from `existsBy...` |
| Count rows | `Mono<Long>` |
| Fetch at most the first row in order | `Mono<T>` with `First`/`Top` and sort |
| Need a small complete list | `Flux<T>.collectList()` |
| Need to assert a Flux has at most one element | `singleOrEmpty()` |
| Custom SQL, need at most one row | `DatabaseClient` with `one()` |
| Custom SQL, take the first row | `DatabaseClient` with `first()` and `ORDER BY` |
| Custom SQL, read all rows | `DatabaseClient` with `all()` |

## 15. Summary

- `Mono<T>` represents zero or one entity; `Flux<T>` represents zero to many entities.
- `findById` returns `Mono.empty()` if no record exists; `findAll` returns an empty `Flux` if no rows match.
- Not-found is an empty result, whereas database failures are reactive error signals.
- `Mono<List<T>>` from `collectList()` emits an empty list when there are no results; it differs from an empty `Mono<T>`.
- Use `existsById` or `existsBy...` when only checking existence; use `count` when counting rows.
- Choose `Mono` for queries expecting at most one row and protect uniqueness with database constraints.
- `one()` enforces at most one row; `first()` takes only the first row and requires `ORDER BY` if ordering matters.
- `singleOrEmpty()` validates that a `Flux` has at most one element; `next()` takes the first element and discards the rest.
- SQL `NULL` in a column is not the same as a query returning no rows.
- Only collect a `Flux` into a list when the result set is reasonably bounded; use filtering and pagination for large datasets.
