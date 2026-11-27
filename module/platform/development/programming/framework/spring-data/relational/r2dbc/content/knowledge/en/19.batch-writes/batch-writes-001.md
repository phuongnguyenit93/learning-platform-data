# Distinguishing `saveAll` from Batch SQL Operations

Spring Data Relational R2DBC provides `saveAll(...)` to persist multiple entities through a repository. At a lower level, the R2DBC SPI and databases also support ways to execute multiple writes such as batch statements, multi-row `INSERT` statements, or bulk update commands. All of these approaches can process multiple records, but they do not have the same semantics and do not guarantee the same level of optimization.

The key distinction is between **persisting multiple entities through the mapping lifecycle** and **sending a batch SQL operation to the database**. `saveAll` works with entities: Spring Data determines new/existing state, maps properties, applies conversions and appropriate callbacks, and then performs inserts/updates for each entity. A SQL batch works at the statement/driver level: the application prepares a SQL statement and multiple parameter sets so the driver executes them using a supported batching mechanism.

Therefore, calling `saveAll` does not mean the framework will always generate a single `INSERT` statement or a single batch network round-trip. If the goal is to save entities with the Spring Data lifecycle, `saveAll` is usually appropriate. If the goal is high throughput for uniform data where you can control the SQL, a batch statement or multi-row SQL may be more effective, though the application must take responsibility for mapping rules, auditing, versioning, and generated values that the entity-oriented path normally handles.

## 1. Three concepts commonly grouped together as "batch"

In an R2DBC application, the word "batch" can refer to at least three different approaches:

| Approach | Mechanism | Unit of operation |
| --- | --- | --- |
| `repository.saveAll(...)` | Spring Data persists each entity through the repository persistence path | One entity per save operation; not a SQL batch by default |
| `Statement.add()` | R2DBC SPI collects multiple bound parameter sets for the same SQL statement | One SQL statement with multiple parameter sets |
| Multi-row SQL | One SQL statement containing multiple `VALUES` tuples or a bulk command | One SQL statement affecting multiple rows |

In addition, the R2DBC SPI has `Batch` created via `Connection.createBatch()` to execute multiple SQL statements. This API differs from `Statement.add()`: `Statement.add()` is for multiple parameter sets of the same statement, whereas `Batch` groups multiple SQL statements. Support and limits depend on the driver.

Illustrative examples:

```java
// Repository: save multiple entities via Spring Data.
Flux<Customer> saved = customerRepository.saveAll(customers);
```

```java
// R2DBC SPI: same INSERT, multiple bound parameter sets.
Statement statement = connection.createStatement(
        "INSERT INTO customer (id, name) VALUES ($1, $2)"
);
statement.bind(0, 1L).bind(1, "Lan").add();
statement.bind(0, 2L).bind(1, "Minh");
Publisher<? extends Result> result = statement.execute();
```

```sql
-- A single INSERT statement containing multiple rows.
INSERT INTO customer (id, name)
VALUES (1, 'Lan'), (2, 'Minh'), (3, 'An');
```

All three examples can produce three rows, but their execution paths, callbacks, binding approaches, returned results, and driver support differ.

## 2. What does `saveAll` do?

Reactive repositories provide common overloads:

```java
Flux<S> saveAll(Iterable<S> entities);

Flux<S> saveAll(Publisher<S> entityStream);
```

The exact API depends on the repository interface and Spring Data version, but the general meaning is accepting multiple entities and emitting the saved entities. `saveAll` is a repository-layer API, not a guarantee that the database will receive a single batch SQL statement.

In common R2DBC repository implementations, entities are passed through the corresponding `save` logic, typically sequentially using an operator such as `concatMap`. Each entity may be classified as new or existing and then go through a separate insert or update operation. Internal details can change across Spring Data versions; when relying on batching for performance, check the implementation/version in use and measure with the real driver.

Example:

```java
public Flux<Customer> createCustomers(List<Customer> customers) {
    return customerRepository.saveAll(customers);
}
```

The returned publisher emits the entities as each save operation completes. Because reactive publishers are typically lazy, calling `saveAll` only constructs the pipeline; the database begins processing when the publisher is subscribed to by a WebFlux controller, `StepVerifier`, or another consumer.

### `saveAll` still applies newness detection

Each entity is persisted according to its persistence state. Depending on the entity:

- If the entity is new, Spring Data performs an insert.
- If the entity already exists, Spring Data performs an update.
- If the entity implements `Persistable`, `isNew()` can determine the state.
- If the entity has `@Version`, the version participates in state detection and optimistic locking.
- Without `Persistable` or `@Version`, the `@Id` identifier is typically used to determine whether the entity is new or existing.

Consequently, a single `saveAll` call can contain both new and existing entities. It does not necessarily correspond to a uniform batch insert.

### Entity lifecycle, conversions, and callbacks

Because `saveAll` goes through the entity persistence path, save operations can use:

- Mapping metadata to determine table, column, and identifier.
- `R2dbcCustomConversions` to convert domain types to driver/store types.
- Appropriate entity lifecycle callbacks such as before-convert/save and after-save callbacks.
- Auditing such as `@CreatedDate`, `@LastModifiedDate`, `@CreatedBy`, and `@LastModifiedBy` if configured.
- Optimistic locking via `@Version`.
- Generated IDs or database-returned values, depending on driver and operation capabilities.

This makes `saveAll` convenient when each entity needs to go through the application's standard persistence rules. However, it can also incur more mapping work and more database statements than a bulk SQL statement.

## 3. Example of `saveAll` with new entities

Suppose the `customer` table uses a generated ID:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    status VARCHAR(30) NOT NULL
);
```

Entity:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    private String status;

    public Customer(String name, String status) {
        this.name = name;
        this.status = status;
    }

    // Constructors/getters required for mapping and the application.
}
```

Repository:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
```

Saving multiple entities:

```java
List<Customer> customers = List.of(
        new Customer("Lan", "ACTIVE"),
        new Customer("Minh", "ACTIVE"),
        new Customer("An", "PENDING")
);

Flux<Customer> savedCustomers = customerRepository.saveAll(customers);
```

When the pipeline is subscribed to, Spring Data detects entities without an ID as new, executes inserts, and emits the saved entities. Use the emitted entities to obtain the database-generated IDs:

```java
return customerRepository.saveAll(customers)
        .doOnNext(saved -> log.info("Saved customer id={}", saved.getId()));
```

Do not assume the input objects are always mutated in place. With immutable entities, Spring Data can create new instances containing the ID; even with mutable entities, the emitted result is the value that should be used after persistence.

## 4. `saveAll` does not guarantee a SQL batch

A common misconception is that:

```java
customerRepository.saveAll(customers);
```

is equivalent to:

```sql
INSERT INTO customer (name, status)
VALUES
    ('Lan', 'ACTIVE'),
    ('Minh', 'ACTIVE'),
    ('An', 'PENDING');
```

You cannot infer that solely from the name `saveAll`. The repository API describes saving all entities. Common implementations process each entity through the `save` logic, and each iteration may issue a separate statement. Whether the driver optimizes internally or not is an implementation detail, not a portable guarantee of `saveAll`.

Consequences can include:

- Multiple statements prepared/executed instead of one multi-row statement.
- Each entity going through its own callbacks, conversions, and newness detection.
- Generated IDs/versions potentially being returned per entity.
- Completion time increasing with the number of entities and database round-trips.
- Backpressure regulating publisher consumption, without turning separate statements into a batch.

If the goal is to reduce the number of statements sent to the database, use a batch API or multi-row SQL supported by the driver/database, after clearly identifying which lifecycle behaviors must be preserved.

## 5. `Iterable` and `Publisher` overloads of `saveAll`

The two overloads serve two different data sources.

### `Iterable` source

```java
List<Customer> customers = loadCustomers();
return customerRepository.saveAll(customers);
```

The list already exists in memory before calling the repository. If the list is large, the application must hold the entities in heap before publisher consumption begins. This is suitable when the count is moderate and data has already been created or read into a collection.

### `Publisher` source

```java
Flux<Customer> customerStream = readCustomersFromSource();
return customerRepository.saveAll(customerStream);
```

A publisher source allows entities to be supplied as a stream. It fits reactive pipelines and can benefit from upstream backpressure. However, if upstream itself materializes the entire dataset into a `List`, the memory benefit disappears.

The input publisher should emit entities in an order and at a pace the pipeline can consume. In common sequential implementations, each entity finishes saving before the next entity is processed. If batch size control is needed, split the source into bounded chunks rather than collecting an unbounded source.

## 6. SQL batch via `Statement.add()`

The R2DBC SPI defines `Statement.add()` to add a bound parameter set to the batch of the same SQL statement. This is useful when many records share the same statement shape, such as inserting multiple rows into one table with the same set of columns.

Example using PostgreSQL markers `$1`, `$2`:

```java
Statement statement = connection.createStatement(
        "INSERT INTO customer (id, name) VALUES ($1, $2)"
);

statement.bind(0, 101L).bind(1, "Lan").add();
statement.bind(0, 102L).bind(1, "Minh").add();
statement.bind(0, 103L).bind(1, "An");

Publisher<? extends Result> results = statement.execute();
```

The `bind` index in the R2DBC SPI starts at 0, even though PostgreSQL markers in SQL start at `$1`. `add()` saves the current parameter binding set into the batch and lets you supply the next set. The final parameter set is kept for execution when `execute()` is called.

### Conditions for using Statement batching

- Records must execute the same SQL query or the same statement shape.
- Each binding set must provide all required parameters with compatible types.
- The driver must support `Statement.add()` for the statement and data types in use.
- Placeholder syntax must match the driver.
- The application must manage the connection and consume `Result` following the proper lifecycle.

Not every driver supports all forms of batching equally. Some drivers have limits on generated values, data types, number of binding sets, or how update counts are returned. Check the driver documentation and run integration tests against the real database version.

### Reading batch results

`Statement.execute()` returns a publisher of `Result`. You can read the number of updated rows:

```java
Flux<Long> updateCounts = Flux.from(statement.execute())
        .concatMap(result -> Flux.from(result.getRowsUpdated()));
```

The number of `Result` items, how update counts are represented, and support for returning generated values depend on the driver. Do not assume you will always receive exactly one result per binding set or generated keys in matching order unless the driver guarantees it.

## 7. Managing connections when using the R2DBC SPI directly

When using `Statement.add()` directly, the application is responsible for acquiring and releasing the connection. In reactive code, ensure `close()` is called on completion, error, or subscription cancellation. `usingWhen` is one option for asynchronous resource management:

```java
public Mono<Long> insertBatch(List<CustomerInput> customers) {
    if (customers.isEmpty()) {
        return Mono.just(0L);
    }

    return Mono.usingWhen(
            Mono.from(connectionFactory.create()),
            connection -> {
                Statement statement = connection.createStatement(
                        "INSERT INTO customer (id, name) VALUES ($1, $2)"
                );

                for (int i = 0; i < customers.size(); i++) {
                    CustomerInput customer = customers.get(i);
                    statement.bind(0, customer.id())
                            .bind(1, customer.name());

                    if (i < customers.size() - 1) {
                        statement.add();
                    }
                }

                return Flux.from(statement.execute())
                        .concatMap(result -> Flux.from(result.getRowsUpdated()))
                        .reduce(0L, Long::sum);
            },
            connection -> Mono.from(connection.close()),
            (connection, error) -> Mono.from(connection.close()),
            connection -> Mono.from(connection.close())
    );
}
```

This is an illustrative example with PostgreSQL and a driver that supports `Statement.add()`. It assumes the batch list is already in memory, IDs are provided up front, and the driver supports the corresponding bind types. If IDs are database-generated or generated values must be returned, check the driver's API/codecs and design result consumption accordingly.

`usingWhen` closes the connection on completion, error, and cancel paths. When using a connection pool, `close()` typically returns the connection to the pool. In typical Spring Data applications, prefer `DatabaseClient`, `R2dbcEntityTemplate`, or repositories when they already meet your needs; direct SPI usage increases resource management responsibility and driver coupling.

## 8. `Connection.createBatch()` differs from `Statement.add()`

The R2DBC SPI also has `Connection.createBatch()` to create a batch consisting of multiple SQL statements:

```java
Batch batch = connection.createBatch();
batch.add("UPDATE customer SET status = 'INACTIVE' WHERE id = 1");
batch.add("UPDATE customer SET status = 'INACTIVE' WHERE id = 2");

Publisher<? extends Result> results = batch.execute();
```

`Batch` is suited for multiple SQL statements that need to run in one batch, but this API does not provide a parameter binding mechanism like `Statement`. Do not concatenate user data directly into SQL strings to construct a batch; doing so risks SQL injection and escaping bugs. For the same statement with multiple parameter sets, `Statement.add()` is more appropriate because it still uses bind parameters.

| API | SQL | Parameters |
| --- | --- | --- |
| `Statement` | One SQL statement | Binds one set of values |
| `Statement.add()` | One SQL statement repeated | Multiple bound value sets for the same statement |
| `Connection.createBatch()` | Multiple SQL statements | No bind parameter API like `Statement` |

Drivers may support these APIs to varying degrees. Do not assume a batch will always be sent in a single network packet; that is a driver and protocol detail.

## 9. Multi-row INSERT: one statement writing multiple rows

If all records share the same set of columns, a single `INSERT` statement can contain multiple `VALUES` tuples:

```sql
INSERT INTO customer (id, name, status)
VALUES
    (:id1, :name1, :status1),
    (:id2, :name2, :status2),
    (:id3, :name3, :status3);
```

In `DatabaseClient`, you can bind the named parameters of a SQL statement built for a fixed number of rows:

```java
Mono<Long> insertThree(CustomerInput a, CustomerInput b, CustomerInput c) {
    return databaseClient.sql("""
                INSERT INTO customer (id, name, status)
                VALUES
                    (:id1, :name1, :status1),
                    (:id2, :name2, :status2),
                    (:id3, :name3, :status3)
                """)
            .bind("id1", a.id())
            .bind("name1", a.name())
            .bind("status1", a.status())
            .bind("id2", b.id())
            .bind("name2", b.name())
            .bind("status2", b.status())
            .bind("id3", c.id())
            .bind("name3", c.name())
            .bind("status3", c.status())
            .fetch()
            .rowsUpdated();
}
```

This is a single multi-row SQL statement, not `Statement.add()`. The number of placeholders grows with the number of rows, and databases have limits on bind parameters, statement size, or packet size. For a variable number of rows, the application must construct structured SQL safely and bind each value; never concatenate input data directly into SQL.

Multi-row inserts can reduce statement count and round-trips, but have limitations:

- Rows generally need the same set of columns and value structure.
- Bind parameter count grows with rows and columns.
- Generated IDs/returning clauses can have database-specific semantics.
- A single constraint error can cause the entire statement to fail.
- Syntax and limits vary across databases.

If the database supports `INSERT ... RETURNING`, returned data can be retrieved, but mapping multiple generated rows must be written explicitly and tested against the driver.

## 10. Bulk UPDATE/DELETE and `@Modifying`

Not every batch is an insert. If you need to update many rows matching the same condition, a bulk SQL statement can be more efficient than loading each entity and calling save:

```java
@Modifying
@Query("UPDATE customer SET status = :newStatus WHERE last_login < :cutoff")
Mono<Integer> deactivateDormantCustomers(
        @Param("newStatus") String newStatus,
        @Param("cutoff") Instant cutoff
);
```

Or using `DatabaseClient`:

```java
Mono<Long> deactivateDormantCustomers(Instant cutoff) {
    return databaseClient.sql("""
                UPDATE customer
                SET status = :status,
                    last_modified = :modifiedAt
                WHERE last_login < :cutoff
                """)
            .bind("status", "INACTIVE")
            .bind("modifiedAt", Instant.now())
            .bind("cutoff", cutoff)
            .fetch()
            .rowsUpdated();
}
```

A bulk command can affect thousands of rows without instantiating entities for each row. However, rows do not go through individual entity lifecycles:

- Entity callbacks do not automatically run per row.
- Auditing must be expressed in the SQL if updates are needed.
- `@Version` does not automatically add optimistic locking conditions or increment the version.
- Previously loaded objects may become stale.
- The result is typically an update count rather than a list of saved entities.

Bulk updates fit well when the rules can be expressed clearly in SQL and the application does not require per-entity callbacks. If each row needs distinct domain logic, individual entity processing or splitting into operation groups may be required.

## 11. Transactions and atomicity across multiple writes

Do not infer that calling a single `saveAll` method guarantees all data is committed or rolled back as a single unit. If all-or-nothing behavior is required, place the write sequence inside an appropriate reactive transaction.

Example:

```java
@Transactional
public Mono<List<Customer>> saveCustomers(List<Customer> customers) {
    return customerRepository.saveAll(customers)
            .collectList();
}
```

When the publisher is subscribed to within a Spring-managed transaction context, repository operations participate in the transaction according to the configuration. If an operation fails, the transaction can roll back database changes within that transaction. Exact final behavior also depends on the database, driver, and transaction manager.

With direct SPI usage, if a batch needs to be inside a transaction, the connection must belong to that transaction. Do not acquire a new connection outside the transaction context and expect the operation to participate in a Spring-managed transaction. When using Spring transactions, prefer letting Spring manage connections via the appropriate factory/transaction manager or use `TransactionalOperator`.

### Do not manually subscribe inside a service

Avoid:

```java
@Transactional
public Mono<Void> saveAllCustomers(List<Customer> customers) {
    customerRepository.saveAll(customers).subscribe();
    return Mono.empty();
}
```

`subscribe()` creates a separate subscription, which can detach from the returned publisher's transaction context. The caller also cannot await the full write process or receive errors through the returned publisher. Return the actual publisher representing the work:

```java
@Transactional
public Mono<Void> saveAllCustomers(List<Customer> customers) {
    return customerRepository.saveAll(customers).then();
}
```

## 12. Mid-batch failures and retries

When writing multiple records, you must decide what happens if one element fails.

### `saveAll` without a surrounding transaction

If each operation executes individually and is not inside a shared transaction, entities before the failure may already have been persisted. When a subsequent entity fails, the publisher emits an error and stops the sequence; earlier writes are not automatically undone just because the overall `Flux` failed.

### With a surrounding transaction

If the entire operation runs inside a reactive transaction and an error triggers rollback, database changes within the transaction can be rolled back together. This provides atomicity, though long transactions can hold connections and locks longer.

### Batch statements or multi-row SQL

An error in a batch may cause the driver/database to stop at one element, report an error for the entire batch, or report results in its own way. A multi-row `INSERT` is typically a single statement, though transaction/constraint semantics are still determined by the database. Check the driver to understand update counts and partial failure behavior.

### Retries can cause duplicate writes

If you retry an entire batch insert after a network error, some rows may already have been written by the database before the client received the error. Resending can cause duplicate keys or repeated side effects if the operation is not idempotent.

For critical writes:

- Use unique keys or business keys to prevent duplicate writes.
- Design upserts/idempotency keys if supported by the database and appropriate for the business logic.
- Retry only transient, recoverable errors.
- Limit retry attempts and apply backoff.
- Clearly identify which operations are safe to re-run.

Do not mechanically wrap a write batch in `retry` without analyzing the possibility that the database partially executed or completed before the connection failed.

## 13. Splitting data into chunks

Putting millions of entities into a `List` and calling `saveAll`, or building one giant batch statement, can consume excessive memory, exceed parameter limits, or hold a transaction open for too long. You can split a publisher into bounded chunks:

```java
public Mono<Long> saveInChunks(Flux<Customer> source, int batchSize) {
    if (batchSize < 1 || batchSize > 1000) {
        return Mono.error(new IllegalArgumentException("Invalid batchSize"));
    }

    return source
            .buffer(batchSize)
            .concatMap(batch -> customerRepository.saveAll(batch).count())
            .reduce(0L, Long::sum);
}
```

`buffer(batchSize)` creates bounded lists. `concatMap` processes each chunk sequentially, preventing all batches from running concurrently. This example still calls `saveAll` per chunk; it does not automatically turn each chunk into a SQL batch. The purpose of chunking here is to bound the number of entities kept in memory and pace the work.

If each chunk needs its own transaction, wrap the chunk operation with a transaction operator or structure the service accordingly. When a single transaction wraps the entire source, even with chunking, the transaction can still remain open until the whole source completes.

### `concatMap` and `flatMap` do not mean batching

```java
source.concatMap(customerRepository::save);
```

executes the save publishers sequentially. Meanwhile:

```java
source.flatMap(customerRepository::save, 8);
```

can run up to a bounded number of save operations concurrently. Both can still generate multiple individual statements; `flatMap` increases concurrency rather than automatically combining statements into a batch.

High concurrency can increase pressure on the connection pool and database and cause completion order to differ from input order. Choose concurrency based on system capacity and ordering requirements; do not treat it as a substitute for true batching.

## 14. Batch size and database limits

Bigger batches are not always faster. A large batch can reduce the number of sends but increases:

- Memory needed to hold entities, parameters, and results.
- Statement/packet size sent over the network.
- Number of bind parameters in a statement.
- Duration of holding transactions, locks, and connections.
- Rollback cost if part of the batch fails.
- Latency for the first element because of waiting to assemble a full batch.

Too-small batches increase statement dispatch overhead and round-trips. The right size depends on column count, payload size, driver/database limits, network latency, and write workload.

A few guidelines:

1. Start with a moderate batch size and measure in practice.
2. Keep bind parameter counts below database/driver limits.
3. Bound total payload size, especially with large JSON or binary data.
4. Avoid holding connections and transactions longer than necessary.
5. Monitor latency, throughput, errors, pool acquire time, and database load.
6. Test with production-like data and sizes.

There is no single optimal batch size that applies to every R2DBC driver and database.

## 15. Generated IDs and batch results

With `saveAll`, each entity goes through the entity persistence path. When the database generates IDs and the driver supports returning generated values, Spring Data can emit entities populated with IDs after saving. This is convenient when the application layer needs to continue processing each saved entity.

With `Statement.add()` batching or multi-row SQL, generated values are more complex:

- Does the driver support `returnGeneratedValues` for batches?
- Does it return one result per binding set or one aggregated result?
- Is the order of generated values guaranteed to match the input order?
- Is `RETURNING` supported for multi-row statements?
- How do you map each returned ID back to its source record?

These questions depend on the driver and database. Do not assume batches always return generated IDs the same way `saveAll` does. If per-entity IDs/versions are needed, check driver capabilities and write integration tests. If the driver does not provide reliable semantics, consider application-assigned IDs or the entity-oriented save path.

## 16. Auditing, callbacks, and optimistic locking

Lifecycle differences are a major reason to choose between `saveAll` and SQL batching.

### Auditing

When `saveAll` goes through the entity persistence path and auditing is configured, properties like `@CreatedDate`/`@LastModifiedDate` can be updated by callbacks for each entity.

Batch SQL does not automatically run auditing callbacks. If timestamps or actors are needed, the statement must write them explicitly:

```sql
INSERT INTO customer (id, name, created_at, last_modified_at)
VALUES ($1, $2, $3, $3);
```

### Optimistic locking

Entities with `@Version` can be updated with a version condition and incremented version through a supported entity persistence path. A handwritten batch statement does not automatically inspect `@Version`. If optimistic locking is needed, include the expected version in the condition and increment the version in SQL.

### Callbacks and domain logic

Before/after-save callbacks, conversions, and logic inside entities/services do not run automatically just because a SQL batch modifies the same table. Bulk SQL is appropriate when the logic can be expressed in the statement and per-entity lifecycles are not required. If callbacks are a mandatory part of the business logic, use the entity path or explicitly execute equivalent logic before batching.

## 17. SQL batching and parameter safety

Always bind data instead of concatenating strings:

```java
statement.bind(0, customer.id())
        .bind(1, customer.name());
```

Do not do:

```java
String sql = "INSERT INTO customer(name) VALUES ('" + customer.name() + "')";
```

Concatenating data can break the SQL when quotes appear, cause encoding issues, and introduce SQL injection. `Statement.add()` allows reusing the same SQL statement with multiple binding sets and is generally the better choice when the driver supports it.

For multi-row SQL with a dynamic row count, generate the placeholder structure safely while still binding each value separately. Never use user input to construct column names, table names, or SQL fragments without validating against an allowlist.

## 18. Detailed comparison of `saveAll` and SQL batching

| Criterion | `saveAll` | `Statement.add()` / multi-row SQL |
| --- | --- | --- |
| API layer | Spring Data repository | R2DBC SPI or SQL API |
| Input | Entities | Parameter sets or multi-row SQL |
| Newness detection | Yes, per entity | Not automatic |
| Mixed inserts and updates | Handled based on entity state | Must design separate statements/groups |
| Mapping metadata | Based on entity mapping | SQL and bind types controlled by application |
| Custom conversions | Yes, via Spring Data conversions | Typically must bind driver-supported types or convert beforehand |
| Entity callbacks | Can run per persistence lifecycle | Do not run automatically |
| Auditing | Can apply if configured | Must write explicitly |
| `@Version` | Can apply optimistic locking | Must add condition and increment version manually |
| Generated ID | Can emit saved entity with ID | Depends on driver returning/generated values support |
| SQL statements | Typically operations per entity | Can combine multiple binding sets/rows in one execution |
| Round-trips | Potentially many | Potentially reduced, depending on driver and SQL |
| Result | Saved entities | Result/update count or returned rows |
| Portability | Higher at the Spring Data layer | More dialect- and driver-dependent |
| SQL control | Lower | Higher |
| Best suited for | Entity CRUD and lifecycle behavior | Uniform data, bulk operations, throughput |

## 19. Which approach to choose in each situation?

### Choose `saveAll` when

- Input already consists of Spring Data entities to persist.
- New and existing entities may be mixed together.
- Generated IDs/versions and resulting entities are needed.
- Spring Data auditing, callbacks, or custom conversions are required.
- Data volume is moderate and repository simplicity matters more than low-level batch optimization.
- You want to keep code less coupled to a specific driver or database.

### Choose `Statement.add()` when

- Many rows share the same SQL structure.
- You need to bind multiple parameter sets for one statement.
- The driver supports batch parameter sets.
- You can manage connections, results, and resource lifecycles directly.
- You can handle auditing/version/generated values manually if needed.

### Choose multi-row SQL when

- The database supports suitable multi-row insert syntax or bulk statements.
- Rows share the same set of columns.
- You want to reduce statement count and round-trips.
- Row count and bind parameter count stay within limits.
- Generated values and constraint errors can be controlled.

### Choose bulk UPDATE/DELETE when

- Many rows need changes matching the same predicate.
- The logic can be expressed directly in SQL.
- Per-row entity lifecycles are not required.
- The update count is sufficient for the business logic, or rows can be re-read when needed.

### Choose chunked `saveAll` when

- The data source is large and you do not want to hold all entities in memory.
- You still need the Spring Data entity lifecycle.
- You want to bound work and transactions by group.
- You accept that each entity may still be written with a separate statement.

## 20. Testing and benchmarking

Do not choose SQL batching solely on the assumption that "batch is always faster." Measure the same input dataset across relevant implementations.

### Correctness testing

- `saveAll` persists the right number of new entities and emits entities with IDs when database-generated.
- `saveAll` handles existing entities according to newness detection.
- Callbacks/auditing/versioning apply on the entity path as configured.
- `Statement.add()` executes all parameter sets and returns update counts per driver behavior.
- Multi-row insert creates the right number of rows and handles constraints properly.
- Mid-batch failures behave properly with transaction boundaries.
- Generated values map correctly if required by the business logic.
- Retries do not create duplicates or unintended repeated side effects.
- Chunking does not drop, duplicate, or unexpectedly reorder data.

Repository test example:

```java
StepVerifier.create(customerRepository.saveAll(customers).collectList())
        .assertNext(saved -> {
            assertThat(saved).hasSize(3);
            assertThat(saved).allMatch(customer -> customer.getId() != null);
        })
        .verifyComplete();
```

For SPI batching, integration tests should run against the real driver and database, not just a mocked `Statement`, because mocks do not prove the driver supports `add()` or generated values.

### Benchmarking

Compare at least:

1. `saveAll` with the same entity list.
2. `saveAll` in bounded-size chunks.
3. `Statement.add()` if supported by the driver.
4. Multi-row insert with an appropriate batch size.

Record:

- Total time and throughput (rows/second).
- Latency per chunk/batch.
- Number of statements/round-trips if observable.
- Application CPU and memory.
- Database CPU, I/O, locks, and connection load.
- Checked-out connections, pending acquires, and pool wait time.
- Error rate, retries, and actual rows written.

Measure using the same schema, indexes, constraints, transaction semantics, and data. Comparing an approach that includes auditing/versioning against one that skips them compares two different requirements; ensure benchmarked variants enforce the same business rules.

## 21. Common pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `saveAll` is slow for large entity counts | Many individual save operations/statements | Measure round-trips; consider batch or multi-row SQL if lifecycle is not required |
| Assuming `saveAll` automatically creates one SQL batch | Confusing multi-entity save API with driver batching | Check implementation/version; use SPI batching if execution mode must be guaranteed |
| `Statement.add()` does not work | Driver lacks support or binding sets are out of order | Check driver, markers, and `add()` semantics |
| Batch misses the last row | `add()` called in the wrong place or final bind set not executed | Check how parameter sets are added per SPI/driver |
| Generated IDs are not returned | Driver lacks generated values support for batches or incorrect usage | Check `returnGeneratedValues`/`RETURNING` and integration test |
| Auditing does not update in bulk SQL | Direct SQL bypasses entity callbacks | Write timestamps/actors in SQL or use entity persistence |
| Version does not increment | Handwritten batch skips `@Version` | Manually add condition and increment version or use entity path |
| Batch fails yet some rows persist | No shared transaction or driver has partial failure semantics | Define transaction boundaries and check driver results |
| Retries create duplicates | Batch may have executed before error propagated back | Use idempotency/unique keys and controlled retries |
| Pool exhausted during concurrent batches | Concurrency too high or connections/transactions held too long | Limit concurrency, chunk size, and connection hold time |
| Memory spikes sharply | Materializing entire source or batch too large | Use `Publisher`, buffer in chunks, and avoid unnecessary full collection |
| Update count not as expected | Driver returns counts with specific result/batch semantics | Read `Result.getRowsUpdated()` and check driver docs |

## 22. Workflow for implementing multi-record writes

A practical workflow can include:

1. Determine whether inputs are entities needing the mapping lifecycle or raw data suited for bulk SQL.
2. Determine whether new and existing entities are mixed.
3. List requirements for auditing, callbacks, conversions, generated IDs, and optimistic locking.
4. Check whether the driver supports `Statement.add()`, multi-row SQL, or the desired bulk API.
5. Define the transaction boundary: entire batch or per chunk.
6. Choose chunk/batch size based on bind, packet, memory, and transaction duration limits.
7. Bind parameters safely; never concatenate input data into SQL.
8. Consume the publisher and manage connections across completion, error, and cancel paths.
9. Test partial failures, retries, duplicate keys, and generated values.
10. Benchmark with production-like workloads, then tune batch size and concurrency.

## 23. Key takeaways

- `saveAll` is a Spring Data API for saving multiple entities; it is not a guarantee that the database receives a single SQL batch.
- In common R2DBC repository implementations, `saveAll` processes each entity via save logic; each entity may emit a separate statement. Check your version if relying on implementation details.
- `saveAll` preserves entity-oriented behaviors such as newness detection, mapping, conversions, callbacks, auditing, and optimistic locking as configured/supported.
- `Statement.add()` groups multiple bound parameter sets for the same SQL statement; the driver must support it.
- `Connection.createBatch()` groups multiple SQL statements and differs from `Statement.add()`; the `Batch` API does not provide bind parameters like `Statement`.
- Multi-row `INSERT` is a single SQL statement with multiple `VALUES` tuples, subject to bind/packet limits and database-specific syntax.
- Bulk UPDATE/DELETE can affect many rows in a single command but does not automatically run entity callbacks, auditing, or `@Version`.
- `concatMap` runs sequentially and `flatMap` increases concurrency; neither automatically turns individual operations into a SQL batch.
- Chunking bounds memory and unit of work; chunked `saveAll` may still execute individual saves.
- If all-or-nothing is required, define a reactive transaction explicitly; do not infer atomicity merely from the name `saveAll`.
- Retrying batch writes can create duplicates if the database executed before the client received the error; design idempotency and unique constraints.
- Use the emitted entities from `saveAll` to get generated IDs/versions; with SQL batches, generated values depend on the driver and require testing.
- Measure throughput, latency, round-trips, memory, pool metrics, and database load before choosing a batch size.

When writing multiple records with Spring Data R2DBC, choose the API based on the semantics you need to preserve. `saveAll` fits when you want Spring Data to persist each entity through the mapping lifecycle. `Statement.add()` and multi-row SQL fit when the data has a uniform structure and the application can directly manage batching, transactions, auditing, versioning, and generated values. Calling the right method name alone does not tell you performance; verify the driver and measure actual execution.
