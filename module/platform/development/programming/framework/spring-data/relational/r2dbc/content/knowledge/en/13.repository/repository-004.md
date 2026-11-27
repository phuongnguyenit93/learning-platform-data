# CRUD Operations and the Meaning of Returned Results

## 1. CRUD in Spring Data R2DBC

CRUD covers four fundamental groups of data operations:

- **Create:** creating new records.
- **Read:** reading one or more records.
- **Update:** modifying existing data.
- **Delete:** removing data.

In Spring Data R2DBC, these operations are typically performed through a reactive repository extending `ReactiveCrudRepository<T, ID>`. The repository provides an entity-centric API, while Spring Data and the R2DBC driver handle SQL generation, parameter binding, execution, and result mapping.

What matters is not only which method creates, reads, updates, or deletes, but also **what the return type communicates**. `Mono<T>`, `Flux<T>`, `Mono<Boolean>`, `Mono<Long>`, and `Mono<Void>` carry different semantics. Using the wrong one or ignoring the return value can cause the application to lose generated IDs, fail to recognize nonexistent records, or accidentally mask database errors.

## 2. Basic CRUD Repository

Entity and repository example:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    private String name;

    @Column("email_address")
    private String email;

    // Constructors, getters and setters
}
```

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
```

`Customer` is the managed entity type; `Long` is the ID type. By extending `ReactiveCrudRepository`, the repository gains common CRUD operations without needing manual SQL for each operation.

Core method signatures commonly used:

| Method | Return type | Result meaning |
| --- | --- | --- |
| `save(entity)` | `Mono<S>` | Entity after saving |
| `saveAll(entities)` | `Flux<S>` | Entities after saving |
| `findById(id)` | `Mono<T>` | One entity or an empty publisher |
| `findAll()` | `Flux<T>` | Stream of potentially multiple entities |
| `findAllById(ids)` | `Flux<T>` | Entities found for the list of IDs |
| `existsById(id)` | `Mono<Boolean>` | `true` or `false` |
| `count()` | `Mono<Long>` | Number of entities |
| `deleteById(id)` | `Mono<Void>` | Delete completion signal, emitting no entity or row count |
| `delete(entity)` | `Mono<Void>` | Entity delete completion signal |
| `deleteAll()` | `Mono<Void>` | Completion signal for deleting all repository entities |

The repository also provides overloads accepting `Iterable` or `Publisher` for operations such as `saveAll`, `findAllById`, and `deleteAll`. Check the signatures of the Spring Data version in use when choosing a specific overload.

## 3. Understanding Mono and Flux in CRUD Results

Spring Data R2DBC uses Project Reactor to represent reactive results:

- `Mono<T>` emits at most one element and completes, can complete empty, or terminates with an error.
- `Flux<T>` emits 0 to many elements and completes, or terminates with an error.
- `Mono<Void>` represents an operation where you only need to know whether it completed or errored; it emits no data values.

For example:

```java
Mono<Customer> one = customerRepository.findById(10L);
Flux<Customer> many = customerRepository.findAll();
Mono<Boolean> exists = customerRepository.existsById(10L);
Mono<Long> total = customerRepository.count();
Mono<Void> deleted = customerRepository.deleteById(10L);
```

These variables hold publishers. With reactive repositories, database operations typically execute when the publisher is subscribed to. Simply calling `findAll()` and discarding the result does not mean the application read any data.

### 3.1. No Element Differs from false or null

The following outcomes have distinct meanings:

| Result | Meaning |
| --- | --- |
| `Mono.just(false)` | Existence query ran and found no matching record |
| `Mono.just(0L)` | Count query ran and counted 0 records |
| `Mono.empty()` | Publisher completed without emitting an element; common when `findById` finds nothing |
| `Mono.error(error)` | Operation terminated with an error, such as a connection or SQL error |
| `Mono<Void>` completed | Operation completed normally, emitting no data value |

Reactive Streams forbids a publisher from emitting `null` as an element. When no entity exists, `findById` represents this with `Mono.empty()`, not `Mono.just(null)`.

Do not arbitrarily turn all errors into `false`, `0`, or empty. If the database cannot be reached, the application does not know whether the record exists; that is an error, not a "does not exist" outcome.

## 4. Create and the Meaning of save

The `save` method persists an entity and returns the saved entity:

```java
Mono<Customer> saved = customerRepository.save(customer);
```

The returned value may contain a database-generated ID, a new version, or state mapped after writing. Therefore, use the entity emitted by the publisher rather than assuming the input object is always updated in place.

For example:

```java
public Mono<Long> createCustomer(String name, String email) {
    Customer customer = new Customer();
    customer.setName(name);
    customer.setEmail(email);

    return customerRepository.save(customer)
            .map(Customer::getId);
}
```

If the ID is auto-generated, the ID value is only available after the save operation completes. Do not read `customer.getId()` immediately after calling `save` without consuming the publisher.

### 4.1. Save Is Not Always an INSERT

The name `save` covers both creation and update. Spring Data determines whether an entity is new via *newness detection*. Depending on the entity and configuration, detection is usually based on:

1. If the entity implements `Persistable`, Spring Data uses `isNew()` provided by the entity.
2. If the entity has a `@Version` property, the version value can be used to determine newness.
3. Without the above mechanisms, Spring Data typically checks the ID; a missing ID value usually indicates a new entity.

Hence, `save` does not mean the database executes an atomic UPSERT statement in database-specific syntax. Spring Data picks the insert or update path based on entity state.

### 4.2. Auto-Generated IDs and Pre-Assigned IDs

With auto-generated IDs, the entity typically has a `null` ID before saving:

```java
Customer customer = new Customer();
customer.setName("Lan Nguyen");
customer.setEmail("lan@example.com");

return customerRepository.save(customer)
        .doOnNext(saved -> System.out.println(saved.getId()));
```

If the ID is pre-assigned—such as a UUID or an ID issued by another system—Spring Data may treat the entity as already existing when there is no `@Version` or `Persistable` controlling newness. In that case, `save` might follow the update path instead of inserting as intended.

For entities with pre-assigned IDs, design newness detection explicitly. You can implement `Persistable<ID>` to provide `isNew()`, or use a nullable version property if suitable for the model and schema.

### 4.3. Save May Return a Different Instance

With mutable entities, Spring Data may update the ID or version on the object depending on the mapping. With immutable entities or constructor/wither-based mapping, the framework may create a new instance containing the post-save values.

Thus, the safe practice is to always use the emitted result:

```java
return customerRepository.save(customer)
        .flatMap(savedCustomer -> publishCustomerCreated(savedCustomer));
```

Do not discard the result and continue using the input object assuming all generated properties were updated.

## 5. Update and Optimistic Locking

In a CRUD repository, updates also typically use `save`. If the entity is detected as existing, Spring Data executes an update operation matching the mapping.

For example:

```java
public Mono<Customer> renameCustomer(Long id, String newName) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .flatMap(customer -> {
                customer.setName(newName);
                return customerRepository.save(customer);
            });
}
```

`findById` returns `Mono.empty()` if no customer exists. `switchIfEmpty` turns that case into a business error. If found, `flatMap` modifies the entity and chains the publisher returned by `save`.

### 5.1. Not Finding an Entity Does Not Mean save Automatically Creates One

A subtle pitfall: if `findById(id)` finds nothing, creating a new object with that same ID and calling `save` does not always produce the behavior you want. Because the ID is already assigned, Spring Data may consider the entity existing and execute an update. Depending on the database, an update matching no rows may complete without changing any record.

If the business rule is "update if present, otherwise return an error", handle `Mono.empty()` before calling `save`, as shown above. If the business rule is upsert, design it explicitly with SQL/`DatabaseClient` or a suitable database mechanism rather than guessing from the name `save`.

### 5.2. Using @Version to Detect Concurrent Updates

When two requests read the same entity concurrently, both can modify and save it. Without control, one change can overwrite the other's change.

Spring Data Relational supports optimistic locking via `@Version`:

```java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;
}
```

Spring Data uses the version during updates to check that the entity is still at the version the application read. If the record was already updated by another operation or no longer exists at the expected version, the operation can fail with `OptimisticLockingFailureException`.

The `save` result may also carry the new version. If the application needs to perform further operations on the updated entity, use the entity emitted by `save`.

Do not automatically retry every optimistic locking error. Before retrying, reload the latest state and verify whether the action is still valid under business rules.

## 6. Read: findById, findAll, and findAllById

### 6.1. findById

`findById(id)` returns `Mono<T>`:

```java
Mono<Customer> customer = customerRepository.findById(10L);
```

If found, the publisher emits one entity and completes. If not found, it completes empty. If the query fails, the publisher terminates with `onError`.

Example handling both present and missing cases:

```java
public Mono<Customer> getCustomer(Long id) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
}
```

If you want a fallback value:

```java
return customerRepository.findById(id)
        .defaultIfEmpty(Customer.anonymous());
```

Only use a fallback value when it represents meaningful domain behavior. For a single-customer detail API, returning a not-found error is usually clearer than returning a dummy entity.

### 6.2. findAll

`findAll()` returns `Flux<T>`:

```java
Flux<Customer> customers = customerRepository.findAll();
```

`Flux` can emit multiple entities. If the table is empty, it completes without emitting elements. If an error occurs while reading data, the error propagates through the publisher.

Do not assume `findAll()` is suitable for every table. If data is large, use filtered queries, pagination, or streaming processing. Collecting an entire `Flux` into a `List` can consume substantial memory.

### 6.3. findAllById

`findAllById(ids)` takes a list of IDs and emits the entities found:

```java
Flux<Customer> customers = customerRepository.findAllById(List.of(10L, 20L, 30L));
```

If some IDs do not exist, the method only emits the entities that were found; it emits no placeholders for missing IDs. The order of returned elements is not guaranteed to match the input ID list order. If business logic requires an exact order, re-sort by the ID list in the application or use a query with `ORDER BY` and explicit ordering rules.

## 7. Exists and Count

These two methods return scalar results instead of entities:

```java
Mono<Boolean> exists = customerRepository.existsById(10L);
Mono<Long> total = customerRepository.count();
```

`existsById` emits `true` or `false`; `count` emits the total record count. When you only need to know whether a record exists, use `exists` instead of loading the entity or counting all rows.

A repository can also declare derived queries:

```java
Mono<Boolean> existsByEmail(String email);
Mono<Long> countByStatus(String status);
```

These are conditional query methods, not full entity reads. Choose according to the output data you actually need.

## 8. Delete and the Meaning of Mono<Void>

Delete methods in `ReactiveCrudRepository` typically return `Mono<Void>`:

```java
Mono<Void> deleteById(Long id);
Mono<Void> delete(Customer customer);
Mono<Void> deleteAll();
```

`Mono<Void>` emits neither the deleted entity, the affected row count, nor a success boolean. It indicates whether the operation completed normally or terminated with an error.

Example deleting by ID:

```java
public Mono<Void> removeCustomer(Long id) {
    return customerRepository.deleteById(id);
}
```

When the publisher completes, the delete operation has completed per the repository contract. If the database raises an error such as a constraint violation, connection loss, or transaction failure, the publisher terminates with an error.

### 8.1. Deleting a Nonexistent ID

`deleteById(id)` does not return a boolean indicating whether a record was deleted. When deleting by ID, if no row matches, the DELETE statement may affect 0 rows while the publisher still completes normally.

If business logic needs to answer "was a record deleted or not", `Mono<Void>` does not provide enough information. You could check beforehand with `existsById`, though a check-then-delete sequence has a race condition; alternatively, use custom SQL returning the affected row count.

### 8.2. Deleting an Entity and Optimistic Locking

When calling `delete(entity)` on an entity with `@Version`, Spring Data can check the version to detect if the entity was modified or deleted by another operation. If no row matches the expected ID and version, the operation can fail with an optimistic locking error.

`deleteById(id)` only has the ID, so it cannot verify the version of the entity the caller read. If version-based conflict protection is needed, use an operation on the versioned entity or a custom statement with a version condition.

### 8.3. Deleting Everything

`deleteAll()` deletes every entity belonging to the repository. This is a broad operation and must be called deliberately:

```java
Mono<Void> clearCustomers() {
    return customerRepository.deleteAll();
}
```

Do not confuse `deleteAll()` with deleting one tenant's data or records matching a business condition. If you only need to delete a subset of records, use a conditional method or a custom delete query.

## 9. Result Semantics of Each CRUD Group

| Group | Typical API | What does the publisher emit? | When no data matches |
| --- | --- | --- | --- |
| Create/update | `save` | Saved entity | Typically not empty if the operation succeeds; failures emit an error signal |
| Save multiple entities | `saveAll` | Each saved entity via `Flux` | Empty input Iterable/Publisher emits no elements |
| Read one entity | `findById` | One entity | `Mono.empty()` |
| Read multiple entities | `findAll`, `findAllById` | Matching entities | `Flux` completes empty |
| Existence | `existsById` | Boolean | `false` |
| Count | `count` | Long | `0L` |
| Delete | `delete`, `deleteById`, `deleteAll` | Emits no value (`Void`) | Typically completes normally if no error occurs |

An important difference is that `findById` uses empty to represent not found, whereas `existsById` uses `false`. Delete operations use `Mono<Void>`, so you cannot infer the number of deleted rows merely from publisher completion.

## 10. Using saveAll for Multiple Entities

`saveAll` accepts multiple entities and returns a `Flux<S>` containing the saved entities:

```java
public Flux<Customer> importCustomers(List<Customer> customers) {
    return customerRepository.saveAll(customers);
}
```

There is an overload taking `Iterable` and an overload taking `Publisher`, which is useful when input data is generated or read from another reactive stream:

```java
Flux<Customer> incoming = readCustomersFromSource();

return customerRepository.saveAll(incoming);
```

The result is a `Flux` so downstream stages can process each saved entity. If you need generated IDs, read them from the entities emitted by `saveAll`.

Do not assume `saveAll` always turns into a single bulk SQL insert statement. Depending on the implementation, mapping, and driver, entities may be processed across multiple operations. If batch performance matters, measure the actual SQL and evaluate database-appropriate batch APIs.

### 10.1. Mid-Stream Failures and Transactions

If one entity in the stream fails to save, the publisher can terminate with an error. Earlier operations that already ran may remain committed depending on transaction boundaries. Do not assume a `saveAll` stream is automatically atomic across every call pattern and configuration.

If business logic requires an entire import batch to succeed or roll back together, wrap the entire publisher in an appropriate reactive transaction:

```java
@Transactional
public Flux<Customer> importCustomers(List<Customer> customers) {
    return customerRepository.saveAll(customers);
}
```

The method must return the publisher so Spring manages the transaction lifecycle. With transactions managed by `R2dbcTransactionManager`, operations must share the same transaction context and connection. For very large batches, an overly long transaction can hold connections and create database pressure; consider chunking according to business requirements.

## 11. Using CRUD Results in a Reactive Service

An application service can compose multiple operations without blocking threads:

```java
@Service
public class CustomerApplicationService {

    private final CustomerRepository repository;

    public CustomerApplicationService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<Customer> create(String name, String email) {
        Customer customer = new Customer();
        customer.setName(name);
        customer.setEmail(email);

        return repository.save(customer);
    }

    public Mono<Customer> get(Long id) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)));
    }

    public Mono<Customer> updateName(Long id, String newName) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
                .flatMap(customer -> {
                    customer.setName(newName);
                    return repository.save(customer);
                });
    }

    public Mono<Void> delete(Long id) {
        return repository.deleteById(id);
    }
}
```

The service returns publishers directly to the caller. There is no need to call `subscribe()` inside each method. When using WebFlux, the framework subscribes to the publisher returned by the controller and manages signals over the request lifecycle.

### 11.1. When You Want to Return a Message After Deleting

Since `deleteById` returns `Mono<Void>`, you can append a result after the operation completes:

```java
public Mono<String> deleteAndRespond(Long id) {
    return customerRepository.deleteById(id)
            .thenReturn("Delete operation completed");
}
```

`thenReturn` only emits the string when the preceding publisher completes normally. If the delete fails, the string is not emitted and the error continues downstream.

If you want to return HTTP 204, the controller can return `Mono<Void>`:

```java
@DeleteMapping("/{id}")
public Mono<Void> delete(@PathVariable Long id) {
    return customerService.delete(id);
}
```

HTTP 204 in this example only indicates the operation was processed without a response body; it does not confirm a row was actually deleted if the ID did not exist.

## 12. When You Need the Affected Row Count

Standard CRUD delete methods return `Mono<Void>`, so they do not provide the affected row count. If business logic needs to distinguish between "deleted" and "no matching row", you can use `DatabaseClient`:

```java
public Mono<Long> deleteCustomer(DatabaseClient databaseClient, Long id) {
    return databaseClient.sql("DELETE FROM customer WHERE id = :id")
            .bind("id", id)
            .fetch()
            .rowsUpdated();
}
```

`rowsUpdated()` returns the number of modified rows reported by the driver execution result. For example, `1` typically means one row was deleted, while `0` means no row matched. Exact types and behavior should be confirmed against the Spring Framework R2DBC version and driver in use.

Similarly, for a custom UPDATE:

```java
public Mono<Long> updateCustomerEmail(
        DatabaseClient databaseClient,
        Long id,
        String email) {

    return databaseClient.sql("""
            UPDATE customer
            SET email_address = :email
            WHERE id = :id
            """)
            .bind("email", email)
            .bind("id", id)
            .fetch()
            .rowsUpdated();
}
```

This is an explicit SQL operation, not the default behavior of `ReactiveCrudRepository.save`. When using custom SQL, the application is responsible for mapping, WHERE clauses, optimistic locking if needed, and domain consistency.

## 13. Transactions and the Boundary of a CRUD Operation

A single repository operation typically follows Spring Data's transaction configuration. However, a use case involving multiple repository calls needs a transaction boundary defined at the application layer.

For example, creating a customer and an audit record:

```java
@Transactional
public Mono<Customer> register(Customer customer) {
    return customerRepository.save(customer)
            .flatMap(saved -> auditRepository.save(
                    new AuditEntry("CUSTOMER_CREATED", saved.getId()))
                    .thenReturn(saved));
}
```

If both repositories share the same `ConnectionFactory` and appropriate transaction manager, the operations can participate in the same reactive transaction. If audit records are stored in a different database or system, this R2DBC transaction does not automatically cover that other system.

Reactive transactions are tied to the Reactor Context and publisher lifecycle. Therefore, do not call `subscribe()` independently inside a `@Transactional` method and then return a different publisher. An independent subscription can execute outside the caller's transaction.

## 14. Derived Queries and Custom CRUD

`ReactiveCrudRepository` provides generic operations, but applications often need queries based on domain conditions:

```java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatus(String status);

    Mono<Boolean> existsByEmail(String email);

    Mono<Long> countByStatus(String status);
}
```

Method names are parsed against entity properties. Read methods can return `Mono` or `Flux` depending on the result cardinality to represent. Exists/count methods return the corresponding scalar types.

When custom SQL is required, you can use `@Query` on repository methods or `DatabaseClient` for operations needing fine-grained control. For custom update/delete statements, annotate and configure them according to the modifying query mechanism supported by your Spring Data R2DBC version, and select a return type matching the affected row count if that information is needed.

## 15. Errors and Handling CRUD Results

Database errors should not be confused with the absence of data. For example:

```java
return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
        .onErrorMap(DataAccessException.class,
                error -> new CustomerPersistenceException(error));
```

In practice, preserve or translate errors according to a clear policy. Common scenarios include:

| Operation | Scenario | Handling semantics |
| --- | --- | --- |
| `save` | Unique constraint violation | Failed to save; translate into an appropriate business error if the specific constraint is identified |
| `save` with `@Version` | Version already changed | Optimistic locking failure; reload and decide how to proceed |
| `findById` | No row exists | `Mono.empty()`; can be turned into not found |
| `findAll` | No row exists | `Flux` completes empty; not an error |
| `existsById` | No row exists | Emits `false` |
| `count` | No row exists | Emits `0L` |
| `deleteById` | No row exists | Typically completes without emitting deleted row count |
| Any operation | Connection drop, timeout, SQL error | Publisher terminates with an error signal |

`onErrorResume` can provide a fallback publisher when a specific error occurs. Do not use it to turn every error into empty or a default value, as that loses vital information for observability and business handling.

## 16. Common Misconceptions

### save Is Always INSERT

`save` can insert or update based on entity newness. Understand `isNew` detection, IDs, `@Version`, and `Persistable`.

### Successful Save Means the Input Object Always Has the New ID

Use the entity emitted by `Mono<S>` or `Flux<S>`. Immutable entities may be replaced by a new instance; generated values depend on the database, dialect, and driver.

### findById Returns false When Not Found

`findById` returns `Mono.empty()`. `existsById` is what returns `Mono<Boolean>` with `false` when nonexistent.

### deleteById Returns the Number of Deleted Rows

The standard method returns `Mono<Void>`. If you need the affected row count, use a custom modify/delete query with an API returning `rowsUpdated()`.

### Completed delete Guarantees a Row Was Deleted

Completion only indicates the operation emitted no error. If the ID does not exist, the SQL DELETE may affect 0 rows while the publisher still completes normally.

### saveAll Is Always One Single Bulk SQL Statement

Do not assume that. Execution depends on implementation, mapping, and driver. Measure actual SQL if batch performance matters.

### block or subscribe Can Be Called Anywhere

`block()` blocks the thread; `subscribe()` creates an independent subscription. In reactive services, compose publishers with `map`, `flatMap`, `then` and return the result to the caller.

## 17. Choosing the Right CRUD API for the Need

| Goal | API to use | Result to consume |
| --- | --- | --- |
| Create or save an entity | `save(entity)` | Saved entity, especially ID/version |
| Save a stream of entities | `saveAll(...)` | Each saved entity via `Flux` |
| Fetch one entity | `findById(id)` | Entity or empty |
| Fetch multiple entities | `findAll()` / `findAllById(...)` | Entities emitted via `Flux` |
| Check existence | `existsById(id)` or `existsBy...` | Boolean |
| Count records | `count()` or `countBy...` | Long |
| Delete by ID/entity | `deleteById` / `delete` | Completion signal (`Mono<Void>`) |
| Delete everything | `deleteAll()` | Completion signal (`Mono<Void>`) |
| Need affected row count | `DatabaseClient.fetch().rowsUpdated()` | Affected row count |

When designing a service, first identify the business result that must be returned to the caller. If the post-save entity is needed, return `Mono<Entity>`. If only completion confirmation is needed, `Mono<Void>` suffices. If the modified row count is needed, choose an API that supplies that count. Do not infer information that the return type does not provide.

## 18. Testing CRUD Results

With reactive repositories, you can use `StepVerifier` to verify publishers:

```java
StepVerifier.create(customerRepository.save(customer))
        .assertNext(saved -> {
            assertNotNull(saved.getId());
            assertEquals("lan@example.com", saved.getEmail());
        })
        .verifyComplete();
```

Testing `findById` when not found:

```java
StepVerifier.create(customerRepository.findById(-1L))
        .verifyComplete();
```

Testing exists:

```java
StepVerifier.create(customerRepository.existsById(existingId))
        .expectNext(true)
        .verifyComplete();
```

Testing delete:

```java
StepVerifier.create(customerRepository.deleteById(existingId))
        .verifyComplete();
```

With `Mono<Void>`, do not use `expectNext` because the publisher emits no elements. `verifyComplete()` confirms the operation completed normally; if an error occurred, the test fails.

Integration tests against a real database and R2DBC driver are recommended for persistence-dependent behaviors:

- IDs are generated and returned properly.
- `save` chooses insert or update according to entity state.
- `@Version` detects update conflicts.
- `findById` returns empty when no record exists.
- `deleteById` handles nonexistent IDs per the expected contract.
- `saveAll` behaves transactionally as required by the use case.
- Constraint and connection failures propagate as error signals.

Mock repositories are useful for testing orchestration logic in services, but they do not prove that SQL, mapping, or driver transactions work correctly.

## 19. Workflow for Using CRUD in a Use Case

When building a feature with Spring Data R2DBC, determine step by step:

1. Does the feature need to create, read, update, or delete data?
2. If saving, is the entity new or existing? Does newness detection fit the ID type?
3. Does the caller need a returned entity, a boolean, a count, or just a completion signal?
4. When reading one entity, is the missing case handled as empty or as a business error?
5. When deleting, is the affected row count needed or is `Mono<Void>` enough?
6. If multiple operations must succeed together, where is the reactive transaction placed?
7. Are there optimistic locking, unique constraints, or race conditions to handle?
8. Is the publisher returned throughout the pipeline rather than blocked with `block()` or detached with `subscribe()`?
9. Do integration tests verify return values and real database behavior?

The CRUD APIs of `ReactiveCrudRepository` provide a clear contract between the application and the persistence layer. `save` returns the saved entity; `find` returns an entity or stream of entities; `exists` returns a boolean; `count` returns a count; and delete usually returns only a completion signal. Understanding these semantics accurately helps services handle generated IDs, missing records, database errors, update conflicts, and transactions cleanly in reactive pipelines.
