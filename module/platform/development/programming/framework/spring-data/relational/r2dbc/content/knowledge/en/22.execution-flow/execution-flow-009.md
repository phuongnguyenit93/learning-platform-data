# Preserving Result Order When Combining Multiple Asynchronous Operations

## 1. Why can order change in reactive applications?

In Spring Data R2DBC, repositories return `Mono` or `Flux`. Publishers can perform asynchronous work and complete at different times. When combining multiple operations with Reactor, the emitted result order can differ from the order of input elements.

For example, the application receives a list of IDs in order `[10, 20, 30]` and loads each customer:

```java
Flux.fromIterable(List.of(10L, 20L, 30L))
        .flatMap(customerRepository::findById);
```

If the query for ID `30` completes before ID `10`, `flatMap` can emit customer `30` first. The result is not guaranteed to follow `[10, 20, 30]`.

This is not a bug in R2DBC or the database. It is the behavior of publisher composition that lets inner publishers run concurrently and emit results as soon as they are ready.

When order carries business meaning, pick the right Reactor operator and clearly distinguish which order must be preserved:

- The order of rows returned by the database.
- The order of elements in the input publisher.
- The completion order of inner publishers.
- The final order of elements emitted to the subscriber.
- The order in which side effects or write statements actually execute.
- The correlation order needed to match results with original IDs or requests.

These kinds of order are related, yet they are not synonymous. A pipeline can emit results in input order while inner operations still execute concurrently.

## 2. Distinguishing database order and Reactor order

Reactor can only preserve or sort the order of elements emitted by upstream. If the database does not guarantee the order of returned rows, the pipeline cannot guess the business order the application desires.

Example:

```sql
SELECT id, name
FROM customer;
```

Without `ORDER BY`, the database does not guarantee results by ID, creation time, or insertion order. One run may happen to return a familiar sequence, yet execution plans, indexes, vacuuming, partitioning, or data changes can alter the order.

If results are needed by creation time:

```sql
SELECT id, name, created_at
FROM customer
ORDER BY created_at ASC, id ASC;
```

`id` acts as a secondary tie-breaker to establish deterministic ordering when multiple rows share the same `created_at`. Writing only `ORDER BY created_at` still allows rows with identical timestamps to appear in varying orders across queries.

### 2.1. ORDER BY is the source of ordering guarantees in the database

When ordering is a data requirement, express it in SQL or query metadata:

- Sort by a business-meaningful column.
- Add a unique or sufficiently stable tie-breaker column.
- Specify ascending (`ASC`) or descending (`DESC`) explicitly.
- When paginating, keep the exact same sorting rule across every page.

Do not rely on physical table order, insertion order, or whatever index order the database happens to pick.

### 2.2. Derived queries with sorting

Spring Data R2DBC can use `Sort` in queries that support sorting:

```java
Flux<Customer> findByStatus(String status, Sort sort);
```

Usage:

```java
Sort sort = Sort.by(
        Sort.Order.asc("createdAt"),
        Sort.Order.asc("id"));

return customerRepository.findByStatus("ACTIVE", sort);
```

Properties in `Sort` are entity property names; mapping metadata translates them to SQL column names. Confirm method signatures and sorting support in your version of Spring Data R2DBC.

With explicit SQL, place `ORDER BY` directly in `@Query` or `DatabaseClient`:

```java
@Query("""
    SELECT id, name, created_at
    FROM customer
    WHERE status = :status
    ORDER BY created_at ASC, id ASC
    """)
Flux<CustomerSummary> findActiveCustomersInOrder(
        @Param("status") String status);
```

## 3. Ordering of Reactor operators

Operators combining publishers have different policies regarding concurrency and result emission order.

| Operator | Inner publisher execution | Result emission order |
| --- | --- | --- |
| `map` | Synchronous per upstream element | Preserves upstream order |
| `flatMap` | Can run multiple inner publishers concurrently | In order of inner publisher emission; can invert order |
| `flatMapSequential` | Can subscribe to multiple inner publishers concurrently | Preserves inner publisher order matching upstream elements |
| `concatMap` | Processes inner publishers sequentially, one at a time | Preserves upstream order without overlapping inner publishers |
| `concat` | Subscribes to publishers one after another | Emits entire first publisher before the next publisher |
| `merge` | Subscribes to multiple publishers concurrently | Interleaves by emission time; does not guarantee input order |
| `zip` | Subscribes to sources and pairs elements by position | Pairs the nth element of each source; does not pair by completion time |
| `collectList` | Consumes upstream and gathers into a List | Preserves the order emitted by upstream |
| `sort` / `collectSortedList` | Must collect data before sorting | By comparator once sufficient data arrives |

Choose the operator based on what must be guaranteed. If you only need results emitted in input order while running I/O concurrently, `flatMapSequential` fits. If execution order of the operations themselves must also be sequential, use `concatMap`.

## 4. flatMap: prioritizes concurrency, does not preserve input order

`flatMap` turns each element into a publisher and merges the inner publishers. Inner publishers can be subscribed to concurrently; whichever element becomes ready first can be emitted first.

Example:

```java
Flux<Integer> result = Flux.just(1, 2, 3)
        .flatMap(value -> Mono.delay(delayFor(value))
                .map(ignored -> value));
```

If element 3 takes less time than element 1, the output can be `3, 2, 1` even though the source emitted `1, 2, 3`.

In an R2DBC application:

```java
Flux<Customer> customers = Flux.fromIterable(List.of(10L, 20L, 30L))
        .flatMap(customerRepository::findById);
```

Queries can finish in different orders. This is a good choice when order does not matter and you want to leverage concurrency, but it is unsuitable if the caller requires results in the ID list order.

### 4.1. Limiting flatMap concurrency

You can limit the number of concurrently running inner publishers:

```java
source.flatMap(this::asyncOperation, 8);
```

The parameter `8` limits how many inner publishers are subscribed to concurrently per the corresponding overload. Limiting concurrency helps control running queries, connection pool pressure, and load on external services.

Limiting concurrency does not establish ordering. Results are still emitted in the order inner publishers emit data.

## 5. flatMapSequential: runs concurrently yet emits in source order

`flatMapSequential` allows subscribing to inner publishers eagerly and running them concurrently, while keeping emission order aligned with the order inner publishers were created from upstream.

Example:

```java
Flux<Integer> result = Flux.just(1, 2, 3)
        .flatMapSequential(value -> Mono.delay(delayFor(value))
                .map(ignored -> value));
```

Even if the inner publisher for `3` finishes before `1`, Reactor buffers `3`'s result until `1` and `2` are emitted in order. The subscriber receives `1, 2, 3`.

In Spring Data R2DBC:

```java
List<Long> requestedIds = List.of(10L, 20L, 30L);

Flux<Customer> customers = Flux.fromIterable(requestedIds)
        .flatMapSequential(customerRepository::findById, 8);
```

Queries can execute concurrently up to the configured limit, while found customers are emitted in input ID order.

### 5.1. Empty results in an inner publisher

`findById` returns `Mono.empty()` when not found. `flatMapSequential` does not generate a placeholder for that ID; it simply preserves the relative order of elements actually emitted.

For example, with input `[10, 20, 30]` where ID `20` does not exist, the output may contain only customer `10` followed by customer `30`. If you need to keep the slot for missing IDs, emit a result type containing both the ID and found status instead of letting the inner publisher complete empty.

### 5.2. flatMapSequential does not serialize side effects

Crucial point: `flatMapSequential` preserves **emission order**, not sequential completion of inner publishers. Queries or side effects inside can still run concurrently.

If write operations depend on one another or execution order is mandatory, `flatMapSequential` does not replace `concatMap`.

## 6. concatMap: processes each publisher in order

`concatMap` processes the next inner publisher only after the current inner publisher completes. It preserves source element order and serializes subscription/execution of inner publishers in the pipeline.

Example:

```java
Flux<Customer> customers = Flux.fromIterable(List.of(10L, 20L, 30L))
        .concatMap(customerRepository::findById);
```

Processing sequence:

1. Query customer `10` and wait for publisher completion.
2. Then query customer `20`.
3. Then query customer `30`.

If ID `20` does not exist, its publisher completes empty and the pipeline proceeds to ID `30`.

### 6.1. When should you use concatMap?

Use `concatMap` when:

- A later operation depends on the result or side effect of an earlier operation.
- Write statements must execute sequentially.
- An external service does not support concurrent requests.
- You want tight load control and to avoid multiple operations contending for one resource.
- Processing order is part of the business contract.

Example sequential updates:

```java
Flux<Void> updates = Flux.fromIterable(commands)
        .concatMap(command -> orderRepository.applyCommand(command));
```

Each command's publisher must complete before the next command begins. This is helpful when the next command must observe changes written by the previous command.

### 6.2. Throughput trade-off

`concatMap` does not run inner publishers concurrently. If each query takes 100 ms and there are 10 independent queries, total time can approach the sum of all queries rather than exploiting concurrency.

Only enforce sequential execution when ordering or resource constraints require it. If operations are independent and only output order matters, `flatMapSequential` can keep order while still exploiting concurrency.

## 7. Comparing the three common operators

| Requirement | `flatMap` | `flatMapSequential` | `concatMap` |
| --- | --- | --- | --- |
| Inner publishers run concurrently | Yes | Yes, bounded | No |
| Results in input order | Not guaranteed | Yes | Yes |
| Side effects serialized | No | No | Yes |
| May need to buffer early-arriving results | Can interleave directly | Yes, if later inner finishes before earlier one | No need to buffer waiting for later inner order |
| Throughput on independent I/O | Typically high | High, can stall on slow leading inner | Lower due to sequential execution |
| Use when | Order does not matter | Ordered output needed, still want concurrency | Execution/side-effect order is required |

Practical rule:

- Order not needed: `flatMap`.
- Output needed in source order: `flatMapSequential`.
- Sequential execution needed: `concatMap`.

## 8. Combining multiple independent publishers

Not every asynchronous combination problem starts from a `Flux` and applies `flatMap`. You may need to coordinate multiple independent data sources.

### 8.1. Mono.zip: pairing results by source position

Suppose a screen needs customer info and order count:

```java
Mono<CustomerDashboard> dashboard = Mono.zip(
        customerRepository.findById(customerId),
        orderRepository.countByCustomerId(customerId),
        (customer, orderCount) -> new CustomerDashboard(customer, orderCount)
);
```

Both queries can complete in any order. `Mono.zip` keeps results according to the positions of the publishers passed in: the first combinator argument is the customer, the second is the order count. It never swaps the two values based on completion time.

If one `Mono` source completes empty, `Mono.zip` typically cannot form a tuple and the result also completes empty; handle missing data before or after zipping as business rules dictate.

### 8.2. Flux.zip pairs the nth elements

With multiple `Flux`es, `zip` pairs elements by emission index:

```java
Flux<Tuple2<Customer, OrderSummary>> paired = Flux.zip(
        customerFlux,
        orderSummaryFlux);
```

The first element from source A is paired with the first element from source B, the second with the second, and so on. Differences in emission speed do not cause `zip` to match by ID or arrival proximity.

`zip` normally completes once one source runs out of elements to form the next tuple. Therefore, if two streams have mismatched element counts or ordering, data can be paired incorrectly.

If you need to match by a business key, join by ID/map or perform a `JOIN` in the database rather than relying on the positions of two `Flux`es.

### 8.3. zipWhen when the second operation depends on the first result

`zipWhen` fits when you need to fetch one value and then call another publisher based on it:

```java
Mono<CustomerDashboard> dashboard = customerRepository.findById(customerId)
        .zipWhen(customer -> orderRepository.countByCustomerId(customer.getId()))
        .map(tuple -> new CustomerDashboard(
                tuple.getT1(),
                tuple.getT2()));
```

The second publisher is created from the first publisher's result. Using `zipWhen` expresses this dependency more clearly than managing tuples manually.

### 8.4. when only waits for completion without pairing values

If you need to run multiple operations and only care that all complete:

```java
Mono<Void> completed = Mono.when(
        auditRepository.writeAudit(entry),
        metricsPublisher.recordEvent(event));
```

`Mono.when` coordinates completion of the sources; it does not emit a tuple of their values. Sources can run concurrently and completion order is not guaranteed.

If the operations need the same R2DBC transaction, ensure they share the same transaction context/`ConnectionFactory`. If only waiting for completion, `when` does not create a transaction or guarantee atomicity on its own.

## 9. concat and merge for existing publishers

When you already have multiple publishers:

```java
Mono<Customer> first = customerRepository.findById(10L);
Mono<Customer> second = customerRepository.findById(20L);
```

`Mono.concat(first, second)` subscribes sequentially, waiting for the first publisher to complete before processing the second:

```java
Flux<Customer> ordered = Flux.concat(first, second);
```

`Flux.merge(first, second)` subscribes to multiple publishers concurrently and emits elements as they become ready:

```java
Flux<Customer> merged = Flux.merge(first, second);
```

If `second` completes first, `merge` can emit the second customer before the first. `concat` preserves input publisher order.

For multiple independent sources where you want concurrency yet output in source order, consider `mergeSequential` if suitable for the publisher types and Reactor version. This operator subscribes to sources concurrently while emitting results in source order as a sequential-output combination.

## 10. Preserving ID order when using findAllById

A common mistake is assuming a repository returns entities in the exact order of the input ID list:

```java
List<Long> ids = List.of(30L, 10L, 20L);

return customerRepository.findAllById(ids);
```

Never assume the result is `30, 10, 20`. The database may return rows by index or query plan; the repository contract does not guarantee input ordering.

If the required order is the order of `ids`, you can collect results into a map and re-emit following the ID list:

```java
public Flux<Customer> findInRequestedOrder(List<Long> requestedIds) {
    return customerRepository.findAllById(requestedIds)
            .collectMap(Customer::getId)
            .flatMapMany(foundById -> Flux.fromIterable(requestedIds)
                    .map(foundById::get)
                    .filter(Objects::nonNull));
}
```

Characteristics of this approach:

- Results are emitted in the exact order of `requestedIds`.
- Missing IDs are skipped.
- If the input list contains duplicate IDs, the corresponding entity is emitted multiple times at the requested positions.
- All found entities are held in memory in a map before re-emission.

If you need to report which IDs were missing, use a result type holding both the requested ID and an optional entity:

```java
public record CustomerLookup(Long requestedId, Optional<Customer> customer) {
}

public Flux<CustomerLookup> findAllInRequestedOrder(List<Long> requestedIds) {
    return customerRepository.findAllById(requestedIds)
            .collectMap(Customer::getId)
            .flatMapMany(foundById -> Flux.fromIterable(requestedIds)
                    .map(id -> new CustomerLookup(
                            id,
                            Optional.ofNullable(foundById.get(id)))));
}
```

For very large ID lists, collecting every entity into a map consumes significant memory. In that case, split the list into batches, use a SQL query with explicit ordering, or design a query returning the requested order.

## 11. Specifying custom order directly in SQL

If you want the database to return rows in the input ID order, you can express that order in SQL. Syntax depends on the database engine.

PostgreSQL example using `unnest` with `WITH ORDINALITY`:

```sql
SELECT c.id, c.name
FROM unnest(ARRAY[30, 10, 20]::BIGINT[]) WITH ORDINALITY AS requested(id, position)
JOIN customer c ON c.id = requested.id
ORDER BY requested.position;
```

`WITH ORDINALITY` assigns a position to each ID in the array; `ORDER BY requested.position` returns rows in the exact input order. Array syntax and types must match the PostgreSQL driver. When using bind parameters, verify how the driver binds arrays.

Some databases have vendor-specific functions like `FIELD(...)` or `CASE` expressions, but avoid putting dialect-specific syntax into repositories shared across multiple database engines without an appropriate abstraction layer.

When ordering does not depend on an input list and instead depends on data attributes, `ORDER BY` on a business column is usually clearer and more portable.

## 12. flatMapSequential and handling multiple R2DBC queries

Example loading customers by ID, allowing up to 5 active queries while keeping output ordered:

```java
public Flux<Customer> loadCustomers(List<Long> ids) {
    return Flux.fromIterable(ids)
            .flatMapSequential(customerRepository::findById, 5);
}
```

`5` is the inner publisher concurrency cap. If the first query is slow, results from later queries can finish yet must wait in a buffer until the first result is emitted. Thus, output ordering can cause head-of-line blocking.

Tuning concurrency should be based on:

- Connection pool size.
- Database concurrent processing capacity.
- Query duration and latency distribution.
- Number of concurrent requests in the application.
- Memory allocated for results buffered while waiting to emit in order.

Do not set concurrency overly high just to chase throughput. If the pool only has 10 connections while hundreds of pipelines each open many queries, requests will queue waiting to acquire connections and raise latency.

### 12.1. Limiting concurrency of flatMapSequential

You can use the overload:

```java
source.flatMapSequential(this::loadOne, maxConcurrency, prefetch);
```

- `maxConcurrency` caps how many inner publishers are subscribed to concurrently.
- `prefetch` controls how many elements are pre-requested from each inner publisher per operator semantics.

These parameters affect resource pressure and buffering. Use moderate values and measure in practice rather than choosing arbitrarily large numbers.

## 13. Preserving execution order when writing multiple records

Suppose there are commands updating one order in sequence:

1. Mark as paid.
2. Close the order.
3. Record as archived.

If commands depend on state produced by the previous command, do not use `flatMap`:

```java
Flux.fromIterable(commands)
        .flatMap(orderRepository::applyCommand);
```

Operations may run concurrently and race on the same aggregate. Use `concatMap` to ensure the next operation starts only after the previous one completes:

```java
Flux.fromIterable(commands)
        .concatMap(orderRepository::applyCommand);
```

If each command must read fresh state written by the prior command, pipeline serialization expresses the dependency properly. The database still needs appropriate constraints/versions if external requests outside this pipeline update the same order concurrently.

### 13.1. flatMapSequential does not guarantee write order

The snippet below may emit results in command order while the write statements still run concurrently:

```java
Flux.fromIterable(commands)
        .flatMapSequential(orderRepository::applyCommand);
```

If the second command depends on the first command having committed, use `concatMap`. Preserving emission order does not mean the database executed side effects in the same order.

## 14. Combining operations in the same reactive transaction

When using `@Transactional`, publishers in the same pipeline can join a single reactive transaction if they use the same `ConnectionFactory` and transaction manager.

For dependent operations, chain with `flatMap` or `then`:

```java
@Transactional
public Mono<Order> createOrder(Order order) {
    return orderRepository.save(order)
            .flatMap(saved -> auditRepository.save(
                    new AuditEntry("ORDER_CREATED", saved.getId()))
                    .thenReturn(saved));
}
```

`flatMap` here chains one publisher to the next based on the saved result. It does not run two independent operations concurrently.

For multiple independent operations:

```java
@Transactional
public Mono<Void> writeIndependentRecords(AuditEntry audit, MetricRecord metric) {
    return Mono.when(
            auditRepository.save(audit),
            metricRepository.save(metric));
}
```

`Mono.when` may subscribe to both operations at once. However, if they join the same R2DBC transaction, both may share a single connection. Not every R2DBC driver allows multiple statements executing concurrently on one connection; some drivers serialize them or raise an error. If strict ordering is needed or broad driver compatibility is desired, chain operations with `then`/`concatMap`.

### 14.1. Ordering and transactions are two distinct requirements

- A transaction ensures changes within its scope commit or roll back under a single lifecycle.
- `concatMap` ensures inner publishers are processed one after another.
- `flatMapSequential` ensures ordered output emission while inner publishers may run concurrently.
- `flatMap` allows results to interleave.

A transaction does not automatically serialize all operations in source order. To guarantee execution order, pick the right operator and understand your connection/driver capabilities.

## 15. parallel and sequential

Reactor can split a `Flux` into multiple rails using `parallel()` and run them on a scheduler using `runOn()`:

```java
Flux<Integer> processed = Flux.range(1, 10)
        .parallel(4)
        .runOn(Schedulers.parallel())
        .map(this::cpuIntensiveOperation)
        .sequential();
```

`sequential()` merges the rails back into one `Flux`, but does not reliably restore the original order of elements. It merges results from rails in a manner suited to parallel execution; do not treat it as an operator that restores source index order.

If you need to preserve order after parallel processing, attach an index before splitting and re-sort by index afterward:

```java
record IndexedResult<T>(long index, T value) {
}

Flux<Result> ordered = Flux.fromIterable(inputs)
        .index()
        .parallel(4)
        .runOn(Schedulers.parallel())
        .map(tuple -> new IndexedResult<>(
                tuple.getT1(),
                process(tuple.getT2())))
        .sequential()
        .sort(Comparator.comparingLong(IndexedResult::index))
        .map(IndexedResult::value);
```

`sort` must collect elements before emitting the sorted output, so this approach requires memory proportional to the element count. Use it only when the dataset is finite and of manageable size. If you need ordered streaming, consider `concatMap` or `flatMapSequential` from the outset.

`parallel()` is generally better suited for CPU-bound work than generating arbitrary concurrency for R2DBC I/O. Do not run many database queries across rails without accounting for pool and driver limits.

## 16. Sort and collectSortedList: when to use them?

Reactor can sort results after collecting them:

```java
Mono<List<Customer>> sorted = customerRepository.findAll()
        .collectSortedList(Comparator.comparing(Customer::getName));
```

Or:

```java
Flux<Customer> sortedFlux = customerRepository.findAll()
        .sort(Comparator.comparing(Customer::getName));
```

Both approaches must retain elements in order to sort them before emitting results. They are unsuitable for infinite streams or very large datasets.

If the database can sort, using `ORDER BY` is usually preferable because the database can leverage indexes and return data already ordered. Use Reactor sorting when ordering relies on Java logic not easily expressed in SQL or when the dataset is already small in memory.

Do not use `sort` to patch a `flatMap` pipeline when you simply need to preserve input order. `flatMapSequential` or `concatMap` expresses intent more accurately and can avoid collecting all results.

## 17. Preserving correlation between results and original requests

When calling an external service or repository, keep a correlation key rather than relying on position if order can change.

Example:

```java
record CustomerResult(Long requestedId, Customer customer) {
}

Flux<CustomerResult> results = Flux.fromIterable(requestedIds)
        .flatMap(id -> customerRepository.findById(id)
                .map(customer -> new CustomerResult(id, customer)));
```

Results may emit in completion order, yet each entity carries its corresponding `requestedId`. Callers can correlate by ID with a map without confusing one customer for another request.

If not-found results are also needed:

```java
record CustomerLookupResult(Long requestedId, Optional<Customer> customer) {
}

Flux<CustomerLookupResult> results = Flux.fromIterable(requestedIds)
        .flatMap(id -> customerRepository.findById(id)
                .map(customer -> new CustomerLookupResult(
                        id, Optional.of(customer)))
                .defaultIfEmpty(new CustomerLookupResult(id, Optional.empty())));
```

In this example, `flatMap` may emit in completion order, yet every result includes the original ID and found status. If the caller also requires input order, replace `flatMap` with `flatMapSequential`.

## 18. Backpressure, buffering, and head-of-line blocking

When using `flatMapSequential`, a later inner publisher may finish earlier while its result must wait for an earlier inner publisher. Reactor must buffer early-arriving results.

Example:

- Query for ID 1 takes 2 seconds.
- Query for ID 2 takes 50 ms.
- Query for ID 3 takes 70 ms.
- Both ID 2 and 3 finish before ID 1.

The subscriber still does not receive ID 2 and 3 until ID 1 can be emitted in order. This is **head-of-line blocking** at the result emission layer.

To keep resources controlled:

- Set `maxConcurrency` to fit pool and database load.
- Set `prefetch` conservatively when inner publishers emit multiple elements.
- Only preserve ordering if the caller genuinely needs it.
- If order is only needed at a final step, consider carrying ID/index and joining or sorting at that final step.
- Avoid collecting huge streams into a `List` or `Map` if batch processing is feasible.

Backpressure lets the subscriber regulate element demand, but it does not eliminate buffering costs caused by preserving order across unevenly completing inner publishers.

## 19. Errors and cancellation when combining operations

When an inner publisher emits an error, combining operators may propagate the error downstream and cancel remaining inner publishers by default. This affects in-flight operations.

Example:

```java
Flux.fromIterable(ids)
        .flatMapSequential(customerRepository::findById, 8);
```

If one query fails, the pipeline can terminate with an error signal and active sibling queries are cancelled. Never assume every launched query will finish and emit a result.

If business logic needs to capture per-element errors and continue, map errors into a typed outcome inside the mapper:

```java
record LookupOutcome(Long id, Customer customer, Throwable error) {
}

Flux<LookupOutcome> outcomes = Flux.fromIterable(ids)
        .flatMapSequential(id -> customerRepository.findById(id)
                .map(customer -> new LookupOutcome(id, customer, null))
                .onErrorResume(error -> Mono.just(
                        new LookupOutcome(id, null, error)))
                .defaultIfEmpty(new LookupOutcome(id, null, null)));
```

This example uses `null` to illustrate one of three states; in real domain code, use `Optional`, a sealed interface, or a dedicated outcome type to distinguish not found from error cleanly.

Never swallow all errors into “not found”. Connection errors, timeouts, and SQL errors must stay distinct from empty results.

## 20. Combined example in Spring Data R2DBC

Suppose an API receives a list of customer IDs, needs to load data concurrently, preserve input order, and explicitly return missing IDs:

```java
public record CustomerLookup(
        Long requestedId,
        Optional<Customer> customer) {
}

@Service
public class CustomerLookupService {

    private final CustomerRepository customerRepository;

    public CustomerLookupService(CustomerRepository customerRepository) {
        this.customerRepository = customerRepository;
    }

    public Flux<CustomerLookup> findInInputOrder(List<Long> ids) {
        return Flux.fromIterable(ids)
                .flatMapSequential(id -> customerRepository.findById(id)
                        .map(customer -> new CustomerLookup(
                                id, Optional.of(customer)))
                        .defaultIfEmpty(new CustomerLookup(
                                id, Optional.empty())),
                        8);
    }
}
```

Behavior:

1. IDs are received in the order of the input list.
2. Up to 8 queries are subscribed to concurrently.
3. Each query's result is paired with its requested ID.
4. If an ID does not exist, a `CustomerLookup` with `Optional.empty()` is still emitted.
5. Results are emitted in the original ID list order.

If queries themselves must also be serialized, change `flatMapSequential` to `concatMap` and remove the concurrency argument. If order is unnecessary, use `flatMap` to avoid head-of-line waiting.

## 21. Testing ordering with StepVerifier

You can create inner publishers completing in reversed durations to observe behavior:

```java
private Mono<Integer> delayedValue(int value) {
    long delayMillis = (4L - value) * 100L;
    return Mono.delay(Duration.ofMillis(delayMillis))
            .map(ignored -> value);
}
```

`flatMap` does not guarantee order:

```java
Flux<Integer> unordered = Flux.just(1, 2, 3)
        .flatMap(this::delayedValue);
```

With the chosen delays, completion often happens as `3, 2, 1`, though you should not write tests depending on exact scheduler timing. The goal is confirming the operator carries no ordering contract.

`flatMapSequential` preserves order:

```java
Flux<Integer> ordered = Flux.just(1, 2, 3)
        .flatMapSequential(this::delayedValue, 3);

StepVerifier.create(ordered)
        .expectNext(1, 2, 3)
        .verifyComplete();
```

`concatMap` also preserves order and serializes execution:

```java
Flux<Integer> sequential = Flux.just(1, 2, 3)
        .concatMap(this::delayedValue);

StepVerifier.create(sequential)
        .expectNext(1, 2, 3)
        .verifyComplete();
```

Beyond pure Reactor tests, R2DBC integration tests should verify:

- Queries with `ORDER BY` return deterministic order when sort values tie.
- `findAllById` is never assumed to preserve input ID order.
- `flatMapSequential` preserves output order when queries have varying latencies.
- `concatMap` executes dependent operations in order.
- Empty results and errors on individual queries are handled properly.
- Concurrency stays within intended bounds and does not exhaust the connection pool.

## 22. Common mistakes

| Symptom | Possible cause | How to fix |
| --- | --- | --- |
| Results emitted out of input ID order | Used `flatMap` with inner publishers of varying latency | Use `flatMapSequential` or `concatMap` |
| SQL results change order between runs | Query lacks `ORDER BY` | Sort in SQL and add a stable tie-breaker |
| `flatMapSequential` still runs side effects concurrently | Operator preserves output order but subscribes inner publishers concurrently | Use `concatMap` if side effects must be serialized |
| `concatMap` too slow | All inner publishers processed one by one | Use `flatMapSequential` if only output order matters |
| Results missing when zipping two Fluxes | `zip` pairs by position and completes when one runs out | Join by ID/key or use a proper SQL `JOIN` |
| `findAllById` does not follow ID list order | Repository/database does not commit to input order | Reorder with a map or express order in SQL |
| `sort` spikes memory usage | `sort`/`collectSortedList` must collect all elements | Use `ORDER BY` or batch processing |
| `parallel().sequential()` still scrambles order | `sequential()` only merges rails, does not restore source index | Attach indexes and re-sort, or use an order-preserving operator upfront |
| Writes inside a transaction behave unexpectedly | Multiple publishers contend on one connection or run detached subscriptions | Chain sequentially and keep one reactive pipeline |
| Slow query stalls later results | Head-of-line blocking in `flatMapSequential` | Reassess whether order is truly needed; tune concurrency and queries |
| Single element error stops entire pipeline | Error signal propagates out of mapper | Map errors to typed per-item outcomes if business rules allow continuing |

## 23. Process for choosing operators to preserve order

When combining multiple asynchronous operations, determine requirements in this sequence:

1. Does the database need to return rows in business order? If so, use `ORDER BY` with an explicit tie-breaker.
2. Must input element order be preserved when invoking multiple publishers?
3. Are the operations independent, or does a later operation depend on a prior side effect?
4. If only source-ordered output is needed and concurrency is still desired, use `flatMapSequential` with appropriate limits.
5. If execution itself must be sequential, use `concatMap` or `concat`.
6. If order does not matter, use `flatMap`/`merge` with bounded concurrency to control load.
7. When combining multiple sources, decide whether to match by position (`zip`) or by business key.
8. If results must match back to original requests, keep the ID/index in the result type.
9. Avoid `sort` or `collectList` on large streams if ordering can be solved in the database or directly in the combining operator.
10. Test ordering, errors, cancellation, concurrency, and transactions using publishers with varying latencies alongside a real database/driver.

Preserving result order in a reactive pipeline is a deliberate trade-off among concurrency, latency, and memory. `flatMap` prioritizes emitting results as ready; `flatMapSequential` runs concurrently while emitting in source order; `concatMap` serializes inner publisher execution as well. With Spring Data R2DBC, combine these operators with SQL `ORDER BY`, carry correlation keys when merging results, and respect transaction boundaries so data order, emission order, and side-effect order are never confused.
