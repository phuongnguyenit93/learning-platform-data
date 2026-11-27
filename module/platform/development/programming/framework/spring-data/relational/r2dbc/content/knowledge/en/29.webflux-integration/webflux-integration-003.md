# Choosing Mono or Flux Based on the API Contract

In Spring Data R2DBC and Spring WebFlux, the reactive return type is part of the API contract. **`Mono<T>`** represents a result that may not exist or has at most one element; **`Flux<T>`** represents a stream that may have zero, one, or many elements. Choosing the right type helps the repository, service, and controller speak the same language about the cardinality of results a caller can receive.

Do not choose `Mono` or `Flux` merely out of habit or based on whatever data happens to sit in the database. Start from the business meaning: does the endpoint return a single resource, an aggregated value, a bounded result set, or a long-lived event stream? Then choose the corresponding publisher type, empty-case handling, HTTP format, and pagination strategy.

## 1. Cardinality of Mono and Flux

Reactive Streams never emit `null` values. A publisher terminates in one of these states: emits elements and completes, completes without emitting any element, or emits an error. Cancellation can be sent by the subscriber to request stopping the subscription.

Reactor's two core types:

| Type | Cardinality | Meaning |
|---|---|---|
| `Mono<T>` | 0 or 1 | An optional single result |
| `Flux<T>` | 0 to N | A result set or stream of elements |
| `Mono<Void>` | 0 values | Only completion or error matters |
| `Flux<Void>` | Rarely needed for data APIs | A stream of completion signals carrying no values |

### 1.1. Mono<T>: One or No Result

`Mono` is appropriate when the business contract states an operation returns at most one object:

- Finding a customer by ID.
- Finding an account by unique identifier.
- Creating an order.
- Updating a record and returning its new state.
- Computing a total or an aggregated result.

Examples:

~~~java
Mono<Customer> findById(Long id);

Mono<Customer> findByEmail(String email);

Mono<Order> createOrder(CreateOrderCommand command);
~~~

A `Mono` can emit exactly one `Customer` and complete, or complete without emitting a `Customer`. The absence of an element is represented by `Mono.empty()`, not `Mono.just(null)`.

### 1.2. Flux<T>: Zero or Many Results

`Flux` is appropriate when a query may return multiple records:

- A list of active customers.
- Orders belonging to a customer.
- Data rows in a report.
- Events or notifications emitted over time.
- Filtered search results.

Examples:

~~~java
Flux<Customer> findByActiveTrue();

Flux<Order> findByCustomerId(Long customerId);

Flux<OrderLine> findLinesByOrderId(Long orderId);
~~~

`Flux` can emit 0, 1, or many `Order` items. Do not switch to `Mono` just because one particular run returns only one result; the return type must reflect the cardinality allowed by the contract.

### 1.3. Never Use null as a Not-Found Signal

Reactive Streams do not allow publishers to emit `null`. The following is wrong or invalid:

~~~java
return Mono.just(null);
~~~

Instead, use:

~~~java
return Mono.empty();
~~~

If the input is a nullable value from a synchronous API:

~~~java
return Mono.justOrEmpty(possiblyNullValue);
~~~

At the API layer, `Mono.empty()` signals no result. The controller or service must decide the HTTP/business meaning of that case.

## 2. Choosing Return Types in Spring Data R2DBC Repositories

Spring Data R2DBC provides a reactive repository abstraction. Method signatures should use `Mono` or `Flux` depending on how many results the query can return.

Entity example:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("customer")
public record Customer(
    @Id Long id,
    String fullName,
    String email,
    Boolean active
) {}
~~~

Repository:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByActiveTrue();

    Flux<Customer> findByFullNameContainingIgnoreCase(String fragment);
}
~~~

Basic CRUD methods also reflect cardinality:

| Repository Method | Typical Return Type | Meaning |
|---|---|---|
| `findById(id)` | `Mono<T>` | Zero or one entity by ID |
| `findById(Publisher<ID>)` | `Mono<T>` | One ID emitted asynchronously |
| `findAll()` | `Flux<T>` | Set of entities |
| `findAllById(ids)` | `Flux<T>` | Entities matching multiple IDs |
| `save(entity)` | `Mono<S>` | One saved entity |
| `saveAll(entities)` | `Flux<S>` | Multiple saved entities |
| `deleteById(id)` | `Mono<Void>` | Completion or error |
| `count()` | `Mono<Long>` | One count value |
| `existsById(id)` | `Mono<Boolean>` | One true/false value |

Do not declare synchronous `List`, `Optional`, or `Page` as the return type of a reactive repository method as if it were a blocking call. Use the reactive types supported by Spring Data and let the publisher execute within the reactive flow.

### 2.1. Querying by Unique Key: Mono

If `id` is the primary key, `findById` fits `Mono` because at most one row can match:

~~~java
Mono<Customer> customer = customerRepository.findById(id);
~~~

Similarly, if `email` has a unique constraint and business rules ensure each email belongs to one customer:

~~~java
Mono<Customer> customer = customerRepository.findByEmail(email);
~~~

If the query predicate is not genuinely unique, be careful when choosing `Mono`. The query can emit an error if multiple results exist when the signature requires at most one. Use `Flux` if multiple rows are valid, or enforce uniqueness in both schema and business rules.

### 2.2. Querying Lists: Flux

If a customer has multiple orders:

~~~java
Flux<Order> orders =
    orderRepository.findByCustomerId(customerId);
~~~

Do not use `Mono<Order>` just because the current UI only displays the most recent order. If the business logic specifically needs the latest order, express the ordering and limit in the query, then return `Mono<Order>`:

~~~java
Mono<Order> findFirstByCustomerIdOrderByCreatedAtDesc(Long customerId);
~~~

Derived query names must match the properties and syntax of the Spring Data version in use. Use `Query`/`Criteria` or `@Query` when explicit control over sort/limit is needed.

## 3. Distinguishing Empty Results from Errors

`Mono.empty()` and `onError` are two different states.

| State | Example | Interpretation |
|---|---|---|
| `Mono` with value | Found `Customer` | Query succeeded, result present |
| `Mono.empty()` | ID does not exist | Query succeeded, no result |
| `onError` | Database lost connection | Operation failed |
| `Flux.empty()` | No matching orders | Query succeeded, empty result set |
| `Flux` emits items then `onError` | Stream read failed mid-way | Partial data emitted, stream did not complete |

Do not turn every database error into `Mono.empty()`. Doing so causes connection errors, SQL errors, or constraint violations to be misinterpreted as "not found."

Example handling optional results in the service:

~~~java
public Mono<Customer> requireCustomer(Long id) {
    return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(id)
        ));
}
~~~

Here, only the `Mono.empty()` case is converted into a domain error. Database errors still propagate downstream via the `onError` signal.

## 4. Mapping Mono.empty() to HTTP Status in WebFlux

An endpoint retrieving a single resource typically needs to return 404 when the resource does not exist. `Mono.empty()` merely represents no value; it does not automatically carry HTTP 404 semantics in every controller contract.

An explicit approach is returning `Mono<ResponseEntity<T>>` and deciding the status based on the result:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @GetMapping("/customers/{id}")
    public Mono<ResponseEntity<?>> getById(
            @PathVariable Long id) {

        return service.findById(id)
            .<ResponseEntity<?>>map(ResponseEntity::ok)
            .defaultIfEmpty(
                ResponseEntity.notFound().build()
            );
    }
}
~~~

This pattern expresses the contract: if `Customer` exists, return 200 with a body; if not, return 404. `ResponseEntity<?>` allows both branches to return bodies of different types within the same publisher.

Another approach is converting empty into an exception:

~~~java
@GetMapping("/customers/{id}")
public Mono<CustomerDto> getById(@PathVariable Long id) {
    return service.findById(id)
        .switchIfEmpty(Mono.error(
            new CustomerNotFoundException(id)
        ));
}
~~~

Then use `@ExceptionHandler` or `@RestControllerAdvice` to map `CustomerNotFoundException` to 404.

Do not assume every controller method returning `Mono<T>` that receives `Mono.empty()` will automatically produce the status your API expects. Explicitly define the status and body for missing results.

### 4.1. When to Return 204 No Content?

204 is appropriate when the request succeeds but the API does not return a representation in the response body, common for delete operations or updates that need not return data.

Example:

~~~java
@DeleteMapping("/customers/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable Long id) {
    return service.delete(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

If business rules require distinguishing successful deletion from nonexistent IDs, the service must inspect the result or use a dedicated exception. A `deleteById` method returning `Mono<Void>` only expresses completion/error and does not necessarily provide the deleted row count.

### 4.2. 404, 204, and 200 with Empty Body Are Different Contracts

- 404: the requested resource does not exist.
- 204: the operation succeeded and there is no response content.
- 200 with empty body: a successful response carrying no representation; usually not the clearest way to express that a resource does not exist.

Choose the status based on endpoint semantics and API documentation, not just the `Mono.empty()` type.

## 5. Flux in WebFlux: JSON Array or Streaming?

`Flux<T>` represents multiple elements, but that does not mean every HTTP response will automatically transmit each element as soon as it arrives.

How WebFlux encodes `Flux` depends on the media type and codec.

### 5.1. application/json: JSON Array Response

A list endpoint commonly returns `Flux<T>`:

~~~java
@GetMapping(
    value = "/customers",
    produces = "application/json"
)
public Flux<CustomerDto> list() {
    return service.findAll();
}
~~~

With a non-streaming media type like `application/json`, WebFlux typically collects the elements to encode them into a single JSON array:

~~~json
[
  {"id": 1, "fullName": "An"},
  {"id": 2, "fullName": "Binh"}
]
~~~

This contract suits finite, reasonably bounded lists. The client receives one JSON document that can be parsed as an array.

Do not assume the server always sends each JSON object as soon as the database emits an element. With non-streaming media types, the codec may need to collect data before writing a complete response.

### 5.2. Streaming Media Types

If an endpoint needs to transmit elements as data becomes available, choose a media type with streaming semantics supported by the codec, such as:

- `application/x-ndjson`: each line is a JSON document.
- `application/stream+json`: JSON stream in a supported streaming format.
- `text/event-stream`: Server-Sent Events.

NDJSON example:

~~~java
@GetMapping(
    value = "/customers/stream",
    produces = "application/x-ndjson"
)
public Flux<CustomerDto> streamCustomers() {
    return service.findAll();
}
~~~

The response can be transmitted line by line:

~~~text
{"id":1,"fullName":"An"}
{"id":2,"fullName":"Binh"}
{"id":3,"fullName":"Chi"}
~~~

With Server-Sent Events, you can return `Flux<ServerSentEvent<T>>`:

~~~java
@GetMapping(
    value = "/events",
    produces = "text/event-stream"
)
public Flux<ServerSentEvent<OrderEvent>> events() {
    return eventService.events()
        .map(event ->
            ServerSentEvent.builder(event)
                .event("order")
                .id(event.id())
                .build()
        );
}
~~~

SSE fits long-lived server-to-client streams. It supports event IDs and client reconnection; the application still needs replay/resume design if events must not be lost during client disconnects.

### 5.3. Streaming Does Not Replace Pagination

A `Flux` reading an entire table and streaming it to the client can still place heavy load on the database, connections, and network. If the client reads slowly, the query may hold a connection open for a long time.

For ordinary data lists, pagination is usually a better fit than streaming an entire table. Streaming should be reserved for cases where the contract genuinely requires a long-lived stream or large datasets consumed incrementally.

## 6. Mono<List<T>> or Flux<T>?

These two types represent two different contracts.

~~~java
Flux<CustomerDto> stream = service.findCustomers();

Mono<List<CustomerDto>> collected =
    service.findCustomers().collectList();
~~~

`Flux` emits each `CustomerDto`. `Mono<List<CustomerDto>>` emits a single list only after the entire source completes.

| Criterion | `Flux<T>` | `Mono<List<T>>` |
|---|---|---|
| Cardinality | 0..N elements | 0 or 1 list |
| When elements are received | Can be received incrementally per publisher | Receives the list only after collection completes |
| Memory | Can process element by element | Must hold the entire collected list in memory |
| Suitable for | Data streams, sequential processing, streaming | Finite, bounded result sets |
| Empty | `Flux.empty()` | `Mono` emits an empty `List` if `collectList()` is called on `Flux.empty()` |
| Mid-stream error | May have already emitted elements before error | No list is emitted if `collectList` ends in error |

Use `collectList()` when the caller genuinely needs a complete collection, such as building a small aggregate response. Never use `collectList()` on an unbounded stream or a very large table because it can cause uncontrolled memory growth.

### 6.1. When Does Mono<List<T>> Make Sense?

Example of an API needing to return a small, bounded group of results:

~~~java
public Mono<List<CustomerDto>> featuredCustomers() {
    return customerRepository.findTop10ByActiveTrueOrderByFullName()
        .map(CustomerDto::from)
        .collectList();
}
~~~

This is a list bounded to 10 elements, so collecting into a `List` can be reasonable if the API contract calls for a complete collection value.

### 6.2. When Should You Keep Flux<T>?

If a query can return hundreds of thousands of rows or is a long-lived event stream, keep `Flux` to process incrementally:

~~~java
public Flux<CustomerDto> exportCustomers() {
    return customerRepository.findAll()
        .map(CustomerDto::from);
}
~~~

However, exporting an entire table requires a batch/keyset strategy, resource limits, and timeouts. Do not hold a database connection open for too long just waiting for a slow client to download data.

## 7. Choosing Mono or Flux at the Service Layer

The Repository reflects data cardinality. The Service reflects the business contract. The Service can change publisher types if business logic changes cardinality.

Example of fetching a customer and calculating their order total:

~~~java
public Mono<CustomerSummary> summary(Long customerId) {
    return customerRepository.findById(customerId)
        .flatMap(customer ->
            orderRepository.findByCustomerId(customerId)
                .map(Order::totalAmount)
                .reduce(BigDecimal.ZERO, BigDecimal::add)
                .map(total -> new CustomerSummary(
                    customer.id(),
                    customer.fullName(),
                    total
                ))
        );
}
~~~

The repositories return `Mono<Customer>` and `Flux<Order>`. The Service aggregates multiple `Order` items into one `CustomerSummary`, therefore returning `Mono<CustomerSummary>`.

Example checking whether all orders allow closing an account:

~~~java
public Mono<Boolean> canCloseCustomer(Long customerId) {
    return orderRepository.findByCustomerId(customerId)
        .all(Order::isClosed);
}
~~~

`all()` produces `Mono<Boolean>`. An empty `Flux` returns `true` under `all` semantics: no element violates the predicate. If business rules require at least one order, combine it with `hasElements()` or `count()` accordingly.

Example taking the first element from a `Flux`:

~~~java
public Mono<Order> latestOrder(Long customerId) {
    return orderRepository
        .findByCustomerIdOrderByCreatedAtDesc(customerId)
        .next();
}
~~~

`next()` converts a `Flux` into a `Mono` and takes the first element. The query must have explicit ordering; do not rely on the database's default order.

### 7.1. Converting Flux to Mono with Aggregating Operators

| Operator | Result | Meaning |
|---|---|---|
| `collectList()` | `Mono<List<T>>` | Collects all elements into a `List` |
| `count()` | `Mono<Long>` | Counts the number of elements |
| `hasElements()` | `Mono<Boolean>` | Whether at least one element exists |
| `all(predicate)` | `Mono<Boolean>` | Whether all elements satisfy the predicate |
| `any(predicate)` | `Mono<Boolean>` | Whether at least one element satisfies the predicate |
| `reduce(...)` | `Mono<A>` | Combines elements into a single value |
| `next()` | `Mono<T>` | Takes the first element then cancels the source |
| `singleOrEmpty()` | `Mono<T>` | Requires at most one element; errors if more than one |

Choose the operator based on business meaning. In particular, `singleOrEmpty()` differs from `next()`: `singleOrEmpty()` asserts a cardinality of at most one, whereas `next()` intentionally takes the first element and discards the rest.

## 8. Choosing Result Types When Using R2dbcEntityTemplate

`R2dbcEntityTemplate` also returns reactive types based on cardinality.

Example selecting multiple entities:

~~~java
Flux<Customer> customers =
    template.select(Customer.class)
        .matching(query)
        .all();
~~~

Fetching a single result:

~~~java
Mono<Customer> customer =
    template.select(Customer.class)
        .matching(query)
        .one();
~~~

Count and exists:

~~~java
Mono<Long> count =
    template.count(query, Customer.class);

Mono<Boolean> exists =
    template.exists(query, Customer.class);
~~~

For update/delete operations, the template typically returns `Mono<Long>` representing the number of affected rows:

~~~java
Mono<Long> updated =
    template.update(Customer.class)
        .matching(query)
        .apply(update);
~~~

Do not turn a `Flux` into a `Mono` by taking the first element just to make a method signature look simpler. If the condition can match multiple rows, keep `Flux` or define explicit limit/sort rules.

## 9. Pagination: Bounded List Contracts

A list endpoint should usually implement pagination instead of returning an entire table.

Example repository method accepting `Pageable` and returning `Flux`:

~~~java
Flux<Customer> findByActiveTrue(Pageable pageable);
~~~

The Controller can accept `page` and `size`, validate bounds, and create a `Pageable`:

~~~java
@GetMapping("/customers")
public Flux<CustomerDto> list(
        @RequestParam(defaultValue = "0") int page,
        @RequestParam(defaultValue = "20") int size) {

    int safeSize = Math.min(Math.max(size, 1), 100);
    int safePage = Math.max(page, 0);

    Pageable pageable = PageRequest.of(
        safePage,
        safeSize,
        Sort.by("fullName").ascending()
    );

    return service.findActive(pageable);
}
~~~

Illustrative example; import `Pageable`, `PageRequest`, `Sort` and ensure the repository method supports `Pageable` per your Spring Data version.

Reactive repositories usually do not return a traditional synchronous `Page<T>` because `Page` needs both the data and total count information. Instead, you can return `Flux<T>` for the data page and `Mono<Long>` for the count, then combine them in the service into a DTO:

~~~java
public Mono<CustomerPage> findPage(Pageable pageable) {
    Flux<CustomerDto> content =
        repository.findByActiveTrue(pageable)
            .map(CustomerDto::from);

    Mono<Long> total =
        repository.countByActiveTrue();

    return Mono.zip(content.collectList(), total)
        .map(tuple -> new CustomerPage(
            tuple.getT1(),
            tuple.getT2(),
            pageable.getPageNumber(),
            pageable.getPageSize()
        ));
}
~~~

Example DTO:

~~~java
public record CustomerPage(
    List<CustomerDto> content,
    long totalElements,
    int page,
    int size
) {}
~~~

This is a contract for a single complete page response, so `Mono<CustomerPage>` is appropriate. `content` is collected into a `List` only within the bounds of one limited page.

Count and select are two separate queries. If data changes between the two statements, `total` and `content` may reflect two different points in time depending on isolation/transaction. If a consistent snapshot is required, design appropriate transaction/isolation settings and understand the impact on connections.

### 9.1. Keyset Pagination

Offset pagination can become expensive for very deep pages. For large datasets, keyset pagination uses the key value of the last item from the previous page to locate the next page.

Example query by ascending ID:

~~~sql
SELECT id, full_name, email
FROM customer
WHERE id > :lastSeenId
ORDER BY id
LIMIT :size
~~~

The repository/template can return `Flux<Customer>` for each batch. The API can return `Mono<CustomerCursorPage>` containing a bounded list and `nextCursor`. This avoids large offsets but requires stable ordering and a cursor matching the filter criteria.

## 10. Backpressure and Streaming APIs

`Flux` supports backpressure at the Reactive Streams level: subscribers can request the number of elements they are ready to receive. This helps publishers pace processing and avoid emitting unbounded data into memory.

However, do not assume backpressure propagates intact from the HTTP client all the way to the database in every situation. Codecs can buffer, drivers can prefetch, and the network layer has its own buffering mechanisms. Bound results, use batches, and measure actual resource usage.

### 10.1. Sequential vs. Concurrent Processing

Example processing rows sequentially:

~~~java
return repository.findAll()
    .concatMap(this::processCustomer);
~~~

`concatMap` processes only one inner publisher at a time and preserves order. If using `flatMap`:

~~~java
return repository.findAll()
    .flatMap(this::processCustomer, 8);
~~~

elements can be processed concurrently up to the specified concurrency limit; result order is not guaranteed as with `concatMap`.

Choose concurrency based on database capacity, downstream limits, and business rules. Raising concurrency excessively can exhaust the connection pool or overload downstream systems.

### 10.2. Streaming Can Hold Connections Open for a Long Time

A `Flux` reading from the database and streaming directly to a slow client can prolong result consumption. Depending on the driver and fetch behavior, the connection may be held open for the duration of the stream.

For large data exports, consider:

- Reading in batches/keysets instead of holding an unbounded query.
- Writing to a temporary file or object storage and returning a link if appropriate.
- Limiting execution time and element count.
- Closing resources when the client cancels.
- Never holding a long transaction just to transmit data to a client.

## 11. Cancellation and Client Disconnects

When an HTTP client disconnects, WebFlux can cancel the response publisher's subscription. Cancellation propagates back through the reactive chain, and upstream operations are requested to stop if possible.

With R2DBC, drivers may support cancelling running statements; actual stopping behavior depends on the driver and database. Never assume cancellation always proves SQL did not execute or rolled back.

If the publisher runs inside a Spring-managed reactive transaction, cancellation before commit can roll back the open transaction. If the transaction already committed, a subsequent cancellation cannot undo the data.

This is especially important for write endpoints: a client timeout does not mean the server did not create the order. For requests that can be retried, use an idempotency key or unique business identifier to prevent duplicate data.

## 12. Error Handling for Mono and Flux

`Mono` has at most one element; `Flux` may have already emitted many elements before encountering an error.

`Mono` example:

~~~java
return repository.findById(id)
    .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
    .onErrorMap(
        DataAccessException.class,
        error -> new CustomerStorageException(error)
    );
~~~

`Flux` example:

~~~java
return repository.findByActiveTrue()
    .onErrorMap(
        DataAccessException.class,
        error -> new CustomerStorageException(error)
    );
~~~

Do not replace database errors with `Flux.empty()` if the business logic requires reporting errors. Doing so misleads clients into thinking no data exists when the database is actually failing.

### 12.1. Flux May Emit Partial Data Before Failing

Suppose a `Flux` streams 100 elements, emits 20 elements, and then the connection drops. The subscriber may have already received 20 elements before receiving `onError`.

With a non-streaming JSON array response, WebFlux typically needs to finish encoding before the full response body is written; an error can result in an incomplete response and the server cannot safely replace the body once the response is committed.

With NDJSON or SSE, the client may have already received and processed some elements before the error. The API must define how clients detect abnormal stream termination, retry, or resume from a cursor/event ID.

### 12.2. Centralized Exception Handler

You can use `@RestControllerAdvice` to map domain errors to HTTP statuses:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(CustomerNotFoundException.class)
    public ResponseEntity<ProblemDetail> handleNotFound(
            CustomerNotFoundException error) {

        ProblemDetail problem =
            ProblemDetail.forStatus(HttpStatus.NOT_FOUND);

        problem.setDetail(error.getMessage());

        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(problem);
    }
}
~~~

This is an example of synchronous error handling at the exception handler layer; controllers/services can still emit `Mono`/`Flux`. Never let an exception handler turn every `DataAccessException` into a 404.

## 13. Choosing the API Contract by Use Case

| Use Case | Appropriate Service/Controller Type | Common HTTP Contract |
|---|---|---|
| Fetch single resource by ID | `Mono<DTO>` or `Mono<ResponseEntity<DTO>>` | 200 or 404 |
| Create a resource | `Mono<DTO>` or `Mono<ResponseEntity<DTO>>` | 201 Created, optionally with `Location` |
| Update and return updated resource | `Mono<DTO>` | 200 |
| Delete with no response body | `Mono<Void>` or `Mono<ResponseEntity<Void>>` | 204 |
| Search bounded list | `Flux<DTO>` or `Mono<PageDto>` | JSON array or paginated object |
| Result page with total count | `Mono<PageDto>` | Single JSON object with `content` and metadata |
| Export/stream data | `Flux<DTO>` | NDJSON or streaming media type |
| Server-pushed events | `Flux<ServerSentEvent<T>>` | `text/event-stream` |
| Count only | `Mono<Long>` | Single JSON number or DTO field |
| Check existence | `Mono<Boolean>` | Boolean or status per API design |

These are common choices, not mandatory rules for every endpoint. The final contract must align with clients and API documentation.

### 13.1. Create Resource: Mono and 201 Created

Example:

~~~java
@PostMapping("/customers")
public Mono<ResponseEntity<CustomerDto>> create(
        @RequestBody CreateCustomerRequest request) {

    return service.create(request)
        .map(dto -> ResponseEntity
            .created(URI.create("/customers/" + dto.id()))
            .body(dto));
}
~~~

One request creates one customer, so the service returns `Mono<CustomerDto>`. The controller returns a `ResponseEntity` with 201 Created and `Location`.

### 13.2. Delete Resource: Mono<Void>

~~~java
@DeleteMapping("/customers/{id}")
public Mono<ResponseEntity<Void>> delete(@PathVariable Long id) {
    return service.delete(id)
        .thenReturn(ResponseEntity.noContent().build());
}
~~~

`Mono<Void>` indicates that only completion or error matters. If returning 404 when the ID does not exist is required, the service needs to verify existence or use a delete query returning a count.

### 13.3. Search: Flux or Page DTO

Small lists can return `Flux<CustomerDto>`:

~~~java
@GetMapping("/customers/active")
public Flux<CustomerDto> activeCustomers() {
    return service.findActive();
}
~~~

Lists needing total/page metadata should return `Mono<CustomerPage>`. Choose based on client needs: a simple array or an object containing `content`, `total`, `page`, and `size`.

## 14. Testing Mono/Flux Contracts

Use `StepVerifier` to test cardinality and reactive signals:

~~~java
StepVerifier.create(repository.findById(knownId))
    .expectNextMatches(customer ->
        customer.id().equals(knownId)
    )
    .verifyComplete();
~~~

Not-found case:

~~~java
StepVerifier.create(repository.findById(missingId))
    .verifyComplete();
~~~

`Flux` with multiple results:

~~~java
StepVerifier.create(repository.findByActiveTrue())
    .expectNextCount(2)
    .verifyComplete();
~~~

Test HTTP with `WebTestClient`:

~~~java
webTestClient.get()
    .uri("/customers/{id}", knownId)
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo(knownId);
~~~

Nonexistent case:

~~~java
webTestClient.get()
    .uri("/customers/{id}", missingId)
    .exchange()
    .expectStatus().isNotFound();
~~~

For NDJSON or SSE endpoints, verify `Content-Type`, individual event formatting, and behavior when the stream completes. When testing cancellation, verify the upstream publisher is cancelled and transactions/resources are released as configured.

Tests should cover:

- `Mono` with one result and empty `Mono`.
- Empty `Flux`, single-element `Flux`, and multi-element `Flux`.
- `Mono` queries not allowed to return multiple rows.
- 404 when resource does not exist.
- 201 when creating a resource with valid `Location`.
- 204 when deleting succeeds with no body.
- JSON array vs. NDJSON/SSE streaming.
- Database errors not turned into empty results.
- Client cancellation and connection cleanup.
- Pagination bounding row count and matching total count.

## 15. Common Mistakes

**Using `Mono` for a query that can return multiple rows.** Wrong cardinality contracts can cause errors when multiple results exist. Use `Flux` or apply explicit query limits/ordering.

**Using `Flux` for a single resource by ID.** `Flux` forces callers to handle multiple elements even when IDs are unique. `Mono` accurately expresses the 0..1 contract.

**Assuming `Mono.empty()` automatically produces 404.** Empty simply means no elements. Map it to `ResponseEntity.notFound()` or an exception handled as 404.

**Returning `Mono.just(null)`.** Reactive Streams forbid `null`. Use `Mono.empty()` or `Mono.justOrEmpty()`.

**Using `collectList()` for unbounded datasets.** Collecting everything can consume excessive memory. Paginate or keep `Flux` and process in batches.

**Thinking `Flux` always streams over HTTP.** `application/json` is typically encoded as a JSON array; streaming depends on media type and codec. Choose NDJSON/SSE when streaming is needed.

**Using synchronous `Page<T>` in reactive repositories.** Use `Flux` for content and `Mono<Long>` for total, then combine them into a page DTO.

**Swallowing errors with `onErrorResume` into empty.** Clients will mistake database failures for missing data. Only transform known errors per policy.

**Using `next()` without sorting.** The first element is non-deterministic if the database has no `ORDER BY`. Sort explicitly before taking the first item.

**Holding a transaction while a client streams data for a long time.** Long transactions can hold connections and locks. Use batches/cursors or decouple export generation from the direct response.

## 16. Design Principles

- Choose `Mono` for an optional single result and `Flux` for zero or more results.
- Use `Mono<Void>` when only completion/error signals are needed.
- Use `Mono.empty()` for no results; never emit `null`.
- Distinguish empty results from database errors.
- Map empty to 404, 204, or another response per the endpoint contract.
- Use `Flux` for lists and select media types suited for JSON arrays or streaming.
- Use `Mono<List<T>>` when the result set is finite, bounded, and the caller needs a complete collection.
- Never collect large datasets or unbounded streams.
- Use pagination/keyset for large lists; combine content `Flux` and count `Mono` if metadata is required.
- Specify an explicit sort before calling `next()`/`first()`.
- Keep the reactive chain intact across repository, service, and controller; do not subscribe/block arbitrarily.
- Account for cancellation, backpressure, and connection hold duration when streaming.
- Test cardinality, empty/error states, and HTTP statuses using `StepVerifier`/`WebTestClient`.

## 17. Key Takeaways

`Mono` and `Flux` are not merely technical return types. They express cardinality in the API contract: `Mono` for 0 or 1 result; `Flux` for 0 to many results. Repositories reflect the number of rows a query can return, services can aggregate multiple values into a single result, and controllers decide the status, body, and media type.

`Mono.empty()` does not automatically mean 404, `Flux` does not automatically mean HTTP streaming, and `collectList()` turns a stream into a collection that must reside in memory. With Spring WebFlux, choose JSON arrays for finite lists, NDJSON/SSE for element-by-element streams, pagination for large datasets, and handle cancellation/timeouts cleanly within proper transaction boundaries. Clear contracts let clients know exactly when they have a resource, a list, an empty response, or an error.
