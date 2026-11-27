# saveAll, deleteAll, and Limits When Processing Multiple Records

Spring Data R2DBC provides `saveAll` and `deleteAll` to operate on multiple entities through a reactive repository. These methods keep application code concise and preserve the data flow as `Flux` or `Mono`. However, the method names do not mean every operation executes as a single bulk SQL statement, nor do they guarantee that loading and writing millions of records will automatically be memory-efficient.

When processing large volumes, you must understand the API variant in use, how the publisher is consumed, how many connections and queries are generated, database limits, transactions, backpressure, and failure behavior when a single element errors. Choosing properly among `saveAll`, `deleteAll`, conditional queries, SQL batching, and chunked processing helps control load and avoid unintended operations.

## 1. saveAll Methods in ReactiveCrudRepository

A reactive repository typically extends `ReactiveCrudRepository`:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
```

The repository provides two common forms of `saveAll`:

```java
<S extends T> Flux<S> saveAll(Iterable<S> entities);

<S extends T> Flux<S> saveAll(Publisher<S> entityStream);
```

The main difference lies in the data source:

- `Iterable` is an existing collection of elements, usually a `List` or collection already constructed in memory.
- `Publisher` emits elements reactively; the source may be a `Flux` produced from a file, API, message stream, or another query.

Example with an existing list:

```java
public Flux<Customer> saveCustomers(List<Customer> customers) {
    return customerRepository.saveAll(customers);
}
```

Example with a reactive source:

```java
public Flux<Customer> importCustomers(Flux<Customer> customerStream) {
    return customerRepository.saveAll(customerStream);
}
```

In both cases, the result is a `Flux<Customer>` emitting the saved entities. The publisher performs work only when subscribed to; simply calling `saveAll` and ignoring the result does not mean data has been written.

## 2. saveAll Does Not Equal a Single Bulk INSERT

`saveAll` is a contract for saving multiple entities. It does not promise that the driver will send a single SQL statement like:

```sql
INSERT INTO customer (name, email)
VALUES
    ('An', 'an@example.com'),
    ('Binh', 'binh@example.com'),
    ('Chi', 'chi@example.com');
```

Spring Data R2DBC must apply mapping rules and entity state checks for each element. In common repository implementations, entities pass through the `save` path sequentially, which can produce an individual insert or update operation per entity. Internal execution may vary across versions; the `saveAll` contract does not guarantee a single bulk statement or single round trip for the entire collection.

This matters because 10,000 entities can produce many separate database operations. The reactive API helps compose operations and regulate consumption, but it does not automatically turn them into an optimized bulk write statement.

If the requirement is high-throughput large-scale import, consider:

- Multi-row SQL inserts if supported by the database and within parameter count limits.
- Batching or prepared statements supported by the R2DBC driver.
- Database-native bulk load mechanisms, such as PostgreSQL's COPY protocol.
- Splitting data into bounded-size batches.

Which option fits depends on the database, driver, mapping requirements, generated IDs, auditing, and optimistic locking.

## 3. saveAll Still Applies Newness Detection per Entity

When calling `saveAll`, each entity must still have an appropriate persistence state. Spring Data detects whether an entity is new or existing via its standard mechanism: typically based on `@Version` if present, otherwise based on `@Id`, or via `Persistable.isNew()`.

For example:

```java
List<Customer> customers = List.of(
        new Customer(null, "An", "an@example.com"),
        new Customer(null, "Binh", "binh@example.com"),
        new Customer(existingId, "Chi Nguyen", "chi@example.com")
);

Flux<Customer> saved = customerRepository.saveAll(customers);
```

The first two entities have null IDs, so they are typically treated as new and follow the insert path. The last entity has a non-null ID, so it is typically treated as existing and follows the update path, unless `@Version` or `Persistable` changes that rule.

A non-null ID does not prove that the row exists in the database. If business logic needs to insert new records with pre-assigned UUIDs, configure newness state using `@Version`, `Persistable`, or explicit insert operations. Do not use `saveAll` as an automatic upsert command.

For entities with `@Version`, each update can trigger an optimistic locking check. An entity carrying a stale version can cause the save operation to fail if the row was modified by another transaction.

## 4. Processing Large Data Sources with a Publisher

If input data is already in a very large `List`, wrapping it with `Flux.fromIterable(list)` does not make the initial list disappear from memory. The entire collection has already been loaded upfront.

For example:

```java
List<Customer> allCustomers = loadAllCustomersIntoMemory();

return customerRepository.saveAll(Flux.fromIterable(allCustomers));
```

This snippet uses a reactive publisher, yet the data source is still a materialized list.

If the data can be read as a stream, build the publisher from a streaming source:

```java
Flux<Customer> parsedCustomers = customerFileReader.readRows();

return customerRepository.saveAll(parsedCustomers);
```

Here, `customerFileReader.readRows()` represents a publisher that reads data incrementally without constructing the whole list upfront. Ensure the file-reading library itself truly supports streaming; if it reads the entire file into memory before emitting a `Flux`, this benefit is lost.

Reactive Streams backpressure allows subscribers to signal element demand. However, how the driver, parser, and repository buffer data still depends on their implementations. Do not treat using `Flux` as a guarantee of constant memory usage. Control source size, prefetch, batching, and how much data is buffered at each layer.

## 5. Bounded-Batch Import Example

A common approach is splitting the source into small batches and saving each batch:

```java
public Flux<Customer> importCustomers(Flux<Customer> source) {
    return source
            .buffer(500)
            .concatMap(customerRepository::saveAll);
}
```

Here:

- `buffer(500)` collects up to 500 entities into a list.
- `concatMap` processes each list sequentially, waiting for the current batch's publisher to complete before starting the next batch.
- At any time, only one active batch is held at this pipeline stage, plus any buffers/prefetch in the source and lower layers.

The size 500 is only an example. Smaller batches reduce memory retention and limit failure blast radius, at the cost of more batch orchestrations. Larger batches reduce orchestration overhead but can increase memory usage, transaction hold time, and parameter counts if using bulk SQL.

If you want to process batches concurrently, you can use `flatMap` with bounded concurrency:

```java
public Flux<Customer> importCustomersConcurrently(Flux<Customer> source) {
    return source
            .buffer(500)
            .flatMap(customerRepository::saveAll, 2);
}
```

This example allows up to two batch-saving publishers to run concurrently. Measure database load before increasing concurrency. Concurrent processing can alter result ordering, increase active connection usage, and cause contention with transactions or constraints. If write ordering is a business requirement, prefer `concatMap` or an explicit ordering strategy.

## 6. Transactions When Saving Multiple Entities

An important question is: if the 80th entity in a 100-entity batch fails, are the preceding 79 entities persisted?

That depends on the transaction boundary. If operations do not run within the same transaction, already-committed writes can remain persisted when a later element fails. Do not assume `saveAll` is automatically a single atomic transaction just because it returns one `Flux`.

If business rules require an entire batch to succeed or fail together, place the save operation inside a reactive transaction:

```java
@Transactional
public Flux<Customer> saveBatch(List<Customer> customers) {
    return customerRepository.saveAll(customers);
}
```

Spring needs a matching R2DBC transaction manager, and the publisher must be returned in the same flow so the transaction interceptor manages subscription, commit, or rollback. Do not call `subscribe()` inside the method, as doing so can detach the work from the managed transaction.

For large datasets, wrapping a multi-million-row import in a single long-running transaction is rarely desirable. Long transactions hold connections, may retain locks, grow transaction logs, and strain the database. A common strategy is per-batch transactions: each batch is an independent commit/rollback unit. When one batch fails, previously committed batches remain, and a resume or reconciliation process handles recovery.

## 7. Error Handling in saveAll

An error can occur when:

- Data violates `NOT NULL`, unique, or foreign key constraints.
- A value is incompatible with the column type.
- An entity has a duplicate ID on insert.
- Optimistic locking detects a changed version.
- The connection drops or the database times out.
- A converter or mapping callback throws an error.

When an entity save publisher errors, the `saveAll` stream typically terminates with that error and stops emitting subsequent entities. Entities processed before the error may already be persisted if no enclosing transaction exists.

You can handle errors at the service boundary:

```java
public Flux<Customer> importCustomers(Flux<Customer> source) {
    return customerRepository.saveAll(source)
            .doOnError(error ->
                    log.error("Customer import failed", error)
            );
}
```

Do not mechanically use `onErrorResume(error -> Flux.empty())` to turn all errors into normal completion. Doing so can hide partial imports.

If you want to continue with valid elements and record failing ones, design a per-element handling flow, classify skippable errors, store failure records in a report, and ensure retries do not create duplicate records. For writes, retry logic must account for the possibility that an earlier write succeeded in the database even though the response was lost.

## 8. Repository deleteAll Variants

`ReactiveCrudRepository` provides multiple delete methods. They do not share the same semantics:

```java
Mono<Void> deleteAll();

Mono<Void> deleteAll(Iterable<? extends T> entities);

Mono<Void> deleteAll(Publisher<? extends T> entityStream);

Mono<Void> deleteAllById(Iterable<? extends ID> ids);

Mono<Void> deleteAllById(Publisher<? extends ID> idStream);
```

Meaning:

| Method | Delete scope |
| --- | --- |
| `deleteAll()` | Deletes every row belonging to the repository's entity/table |
| `deleteAll(Iterable)` | Deletes the supplied entities |
| `deleteAll(Publisher)` | Consumes the publisher and deletes emitted entities |
| `deleteAllById(Iterable)` | Deletes rows whose IDs are in the supplied set |
| `deleteAllById(Publisher)` | Consumes the ID publisher and deletes the corresponding rows |

In particular, the argumentless `deleteAll()` can wipe out the entire table managed by the repository. Verify the right repository and environment before calling it. Do not use it as a method to delete a filtered subset of records.

## 9. deleteAll() vs. deleteAll(entities) and deleteAllById(ids)

### Deleting the Entire Table via Repository

```java
public Mono<Void> clearAllCustomers() {
    return customerRepository.deleteAll();
}
```

This operation deletes all rows in the corresponding table. Depending on the Spring Data R2DBC implementation, it is typically translated into an unconditional delete statement for the entity type. It is not equivalent to `TRUNCATE TABLE`: `TRUNCATE` is a separate DDL/DML statement with different semantics regarding identities, locks, and foreign keys.

### Deleting Known Entities

```java
public Mono<Void> deleteCustomers(List<Customer> customers) {
    return customerRepository.deleteAll(customers);
}
```

This method targets only the entities in the collection. The repository implementation may process each entity through the corresponding delete path; do not assume a single `DELETE ... WHERE id IN (...)` SQL statement is generated.

### Deleting by a List of IDs

```java
public Mono<Void> deleteCustomersById(List<Long> ids) {
    return customerRepository.deleteAllById(ids);
}
```

This variant is suitable when the application already has identifiers and does not need to load entities first. It avoids a read round trip before deleting. Still, exact execution and SQL statement count depend on the implementation; the API does not promise that all IDs are combined into a single `IN` statement.

## 10. Deleting by Publisher to Handle Large ID Streams

When the list of IDs comes from a reactive source, you can pass the publisher directly:

```java
public Mono<Void> deleteCustomers(Flux<Long> customerIds) {
    return customerRepository.deleteAllById(customerIds);
}
```

For example, IDs might come from a query selecting expired customers, an import file, or an event stream. Using a publisher avoids building a huge `List<Long>` upfront.

However, the input publisher must be bounded by design. If the source is infinite or has no termination condition, the delete operation can continue running indefinitely. Filter and bound the source, or use a conditional delete query in the database when the goal is deleting all rows matching criteria.

With `deleteAll(Publisher<T>)`, the publisher emits entities to delete. If you already have IDs, `deleteAllById(Publisher<ID>)` expresses the intent more clearly and avoids loading entities.

## 11. Conditional Bulk Deletion Using Template

If the requirement is "delete all records with status EXPIRED", there is no need to read every entity into Java and call `deleteAll`. You can use `R2dbcEntityTemplate` to issue a conditional delete:

```java
public Mono<Long> deleteExpiredSessions() {
    Query query = Query.query(
            Criteria.where("status").is("EXPIRED")
    );

    return template.delete(Session.class)
            .matching(query)
            .all();
}
```

The template returns the affected row count, which is useful when you need to know how many rows were deleted. The repository's `deleteAll()` returns `Mono<Void>`, which only indicates completion or error and provides no row count.

A conditional delete query can be executed by the database as a single SQL statement, for example:

```sql
DELETE FROM session
WHERE status = 'EXPIRED';
```

This is usually much more efficient than selecting all expired sessions and sending each entity back from the application for deletion. Consider foreign keys, triggers, and transaction volume before deleting a very large set.

## 12. Limits When Processing Many Records

### Memory

Loading all entities into a `List` before saving or deleting can cause heap usage to spike. Use streaming publishers, pagination, or bounded buffers.

### Round-Trip Count

`saveAll` and entity/ID delete variants do not guarantee bulk statements. If each element triggers a separate operation, network latency and database overhead can become significant.

### Statement and Parameter Size

If building `IN (...)` or multi-row insert SQL manually, databases and drivers impose limits on parameter counts, statement length, and packet size. Split into appropriately sized batches.

### Connection Pool

A long import or multiple concurrent batches can occupy many connections. If parallel work exceeds pool capacity, other requests may wait or hit acquire timeouts. Tune concurrency alongside pool size and database limits.

### Transactions and Locks

Long transactions hold connections, lock rows, and grow transaction logs. Split into per-batch transactions if business rules allow partial commits.

### Foreign Keys and Triggers

Deleting many rows may be constrained by foreign keys, triggers, or cascades. The database might reject deletions or trigger additional cascading work. Understand the schema before calling `deleteAll()`.

### Cancellation

If a subscriber cancels the publisher, unexecuted operations may stop, while already-committed operations can remain in effect if no enclosing transaction exists. Import pipelines need progress tracking to resume or reconcile after cancellation.

## 13. saveAll vs. Batch SQL: When to Use Which?

| Need | Approach |
| --- | --- |
| Save a moderate set of entities needing mapping/auditing/versioning | `repository.saveAll(...)` |
| Read input from a stream | `saveAll(Publisher)` |
| Large import needing bounded memory | Publisher + `buffer(n)` + batch processing |
| Controlled concurrency needed | Buffer + `flatMap(..., concurrency)`, after load measurement |
| High-throughput bulk insert | Multi-row SQL, batching, or native bulk load |
| Delete entire table | `repository.deleteAll()`, only when intentionally wiping all rows |
| Delete a known set of IDs | `deleteAllById(...)` |
| Delete rows matching a condition | Derived delete query or template delete by Query |
| Need deleted row count | Template delete returning affected row count |

### Multi-Row SQL Insert Example

On databases that support it, multiple rows can be written in one statement:

```sql
INSERT INTO customer (name, email)
VALUES
    (:name1, :email1),
    (:name2, :email2),
    (:name3, :email3);
```

This is only an illustrative SQL shape; binding dynamic parameter lists and supported syntax depend on the database/driver. Cap batch sizes so parameter or packet limits are not exceeded.

### R2DBC Statement Batch Example

The R2DBC SPI includes `Batch` for grouping multiple independent SQL statements, and `Statement` can support adding multiple executions of the same statement template. However, `Batch.add(String)` accepts SQL strings, not a mechanism for binding multiple parameter sets to the same statement. When parameter binding is needed, check the `Statement.add()` API and specific driver capabilities, or use an appropriate multi-row SQL statement.

Batching does not automatically guarantee atomicity. If the entire batch must commit or roll back together, place it inside an appropriate transaction.

## 14. Safe Batch Saving and Deletion

An import workflow might consist of these steps:

1. Read the source as a stream.
2. Validate and normalize data in small batches.
3. Write each batch in a short transaction.
4. Persist progress or checkpoints after each batch.
5. Record invalid element errors for reprocessing.
6. Provide idempotency so reruns do not create duplicate data.

An old-data cleanup workflow can look similar:

1. Select the scope of data to delete using deterministic criteria.
2. If the volume is large, choose batch sizes and deletion order respecting foreign keys.
3. Delete by condition or by batches of IDs.
4. Log deleted counts and execution timestamps.
5. Make reruns safe when conditions and domain rules allow.

When using table-wide `deleteAll()`, exercise extra caution in production environments. You might require elevated permissions, tenant scope verification, or a service method named to clearly reflect full-table deletion. Never expose a full-table delete through an endpoint that can be invoked indiscriminately.

## 15. Testing saveAll and deleteAll

Integration tests should cover both normal outcomes and failure cases:

### Testing saveAll

```java
StepVerifier.create(customerRepository.saveAll(List.of(
                new Customer(null, "An", "an@example.com"),
                new Customer(null, "Binh", "binh@example.com")
        )))
        .expectNextCount(2)
        .verifyComplete();
```

You can then query back to confirm both rows were saved. Do not check only the count of emitted elements if the test's goal is verifying the data actually resides in the database.

### Testing deleteAllById

```java
Mono<Void> deletion = customerRepository.deleteAllById(List.of(id1, id2));

StepVerifier.create(deletion)
        .verifyComplete();

StepVerifier.create(customerRepository.findAllById(List.of(id1, id2)))
        .verifyComplete();
```

This example assumes `id1` and `id2` existed before deletion. The second check verifies neither entity remains.

### Testing Partial Failures

Create test data where one element in the middle of a batch violates a unique constraint and observe:

- Whether the publisher terminates with an error or continues per the designed policy.
- Whether elements preceding the error remain persisted when there is no transaction.
- Whether changes roll back as expected when enclosed in a transaction.
- Whether retries create duplicate records or corrupt import progress.

Transaction tests must run against a reactive transaction manager and a compatible database. Mock repositories cannot prove real database rollback behavior.

## 16. Common Misconceptions

1. **Assuming saveAll is a single bulk INSERT.** The API does not guarantee one SQL statement or one round trip.
2. **Passing a large List to saveAll and thinking it streams.** The list is already in memory before the publisher starts.
3. **Assuming saveAll always saves in parallel.** The implementation may process sequentially; concurrency must be explicitly designed and bounded.
4. **Assuming all of saveAll is automatically atomic.** Transaction boundaries determine whole-batch rollback capability.
5. **Using deleteAll() when only deleting some records.** The no-argument method deletes all rows of the entity/table.
6. **Assuming deleteAll(entities) uses a single DELETE IN statement.** No such guarantee exists in the API contract.
7. **Packing all IDs into one huge IN clause.** This can exceed parameter limits or degrade query efficiency.
8. **Bulk deleting without considering foreign keys.** The database may reject deletes or cascade to other data.
9. **Swallowing errors with onErrorResume and reporting import success.** This can conceal partial writes.
10. **Retrying writes without idempotency.** An operation may have succeeded even if the client lost the response.
11. **Increasing concurrency without monitoring the pool.** This can exhaust the pool and overload the database.
12. **Using deleteAll as a substitute for TRUNCATE.** The two operations have different semantics and constraints.

## Quick Selection Rules

- Use `saveAll(Iterable)` for moderately sized entity sets already in memory.
- Use `saveAll(Publisher)` when the data source can stream elements.
- Use `buffer(n)` to bound batch sizes; choose `concatMap` when sequential processing is required.
- Increase concurrency only after measuring throughput, connection pool usage, and database load.
- Use per-batch transactions if operations within a batch must roll back together.
- Use `deleteAll()` only when intentionally deleting all rows in the repository.
- Use `deleteAllById` when you already have IDs; use template delete by Query when deleting by condition and needing the affected row count.
- Use SQL batching or native bulk loading when true bulk throughput is required and driver/database limits are verified.
- Design logging, checkpoints, idempotency, and retries to handle mid-stream failures or cancellation.

`saveAll` and `deleteAll` are convenient APIs for handling multiple entities in a reactive model, but their efficiency and atomicity depend on the implementation, transactions, data source, and database. Clearly distinguish full-table deletion from list-based or conditional deletion; distinguish saving multiple entities from bulk SQL; and bound batch sizes, concurrency, and transaction duration. At large data volumes, a pipeline with backpressure, checkpoints, and a clear error strategy is far easier to operate than loading everything into memory and issuing an unbounded operation.
