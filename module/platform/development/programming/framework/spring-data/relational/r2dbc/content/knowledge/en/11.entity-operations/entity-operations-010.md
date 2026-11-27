# Distinguishing In-Memory Entity Changes from Database Persistence

In Spring Data Relational R2DBC, an entity read from a repository is a Java object holding the row's data at query time. After receiving that object, the application can mutate fields, invoke setters, or construct a new instance. Those operations alter state only in application memory. They do not automatically update the row in the database.

R2DBC does not use a persistence context or dirty-checking mechanism like JPA/Hibernate. Spring Data Relational does not track every loaded entity to detect which fields changed and flush them automatically when a transaction ends. To persist data, the application must invoke an explicit persistence operation such as `repository.save(...)`, `R2dbcEntityTemplate.update(...)`, or a SQL statement through `DatabaseClient`.

This distinction is vital when designing reactive services: mutating an object is a synchronous in-memory Java operation; writing to the database is reactive I/O, which typically begins only when the publisher is subscribed to and becomes durable only once the transaction commits.

## 1. Two Distinct States: Java Object and Database Row

Suppose the database holds this row:

```sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    name VARCHAR(200) NOT NULL
);

INSERT INTO customer (id, name) VALUES (10, 'Lan');
```

The repository reads that row:

```java
Mono<Customer> customerMono = customerRepository.findById(10L);
```

When the publisher is consumed, Spring Data reads the row and maps it to a Java object. For instance, the received object has state:

```java
Customer customer = new Customer(10L, "Lan");
```

Then the application calls:

```java
customer.setName("Lan Nguyen");
```

The Java object's value is now `Lan Nguyen`, while the row in the database is still `Lan`. Calling a setter assigns a field on the current object; it sends no SQL and notifies nothing in the database.

We can contrast the steps as follows:

| Action | Java Object State | Database State |
| --- | --- | --- |
| Reading entity via `findById` | Creates/receives object with fetched data | Unchanged |
| Calling setter or mutating field | Changes immediately in memory | Unchanged |
| Creating a new object with updated data | New instance exists in memory | Unchanged |
| Creating publisher via `save(entity)` | Save operation is described | SQL has not necessarily executed yet |
| Subscribing to `save` publisher | Pipeline begins executing | Runs INSERT/UPDATE per entity state |
| Transaction commits successfully | Application receives save result | Changes are committed in the database |
| Transaction rolls back | Java object does not revert to prior state | Changes in the transaction are rolled back in the database |

A Java object is not a live replica linked to a database row. It is simply data currently held by the application. If another transaction updates the same row, the object sitting in memory does not automatically reflect those changes either.

## 2. R2DBC Does Not Perform JPA-Style Dirty Checking

In JPA/Hibernate, entities are managed by a persistence context. When a managed entity changes, the ORM can diff it against an initial snapshot and generate SQL updates during flush. With R2DBC/Spring Data Relational, the entity lifecycle does not work that way.

R2DBC repositories map query results to objects and emit them through `Mono` or `Flux`. Once emitted, Spring Data retains no persistence context to monitor subsequent Java mutations on those objects.

Example:

```java
public Mono<Void> renameWithoutSaving(Long id) {
    return customerRepository.findById(id)
            .doOnNext(customer -> customer.setName("Lan Nguyen"))
            .then();
}
```

This method runs a read query, mutates the name on the received object, and terminates the stream. There is no `save`, `UPDATE`, or other write command. The database retains the old name.

Placing this method in a `@Transactional` service does not alter the outcome:

```java
@Transactional
public Mono<Void> renameWithoutSaving(Long id) {
    return customerRepository.findById(id)
            .doOnNext(customer -> customer.setName("Lan Nguyen"))
            .then();
}
```

A transaction establishes a commit/rollback boundary for database operations executed in the pipeline. It does not detect mutated Java fields or flush entities automatically. If the pipeline only reads and mutates an object in memory, the transaction has no write statements to commit.

Do not carry JPA assumptions straight into R2DBC. In reactive code, always trace which operation produces write SQL and which publisher is consumed to execute it.

## 3. Persisting Changes with `repository.save(...)`

With repositories extending `ReactiveCrudRepository`, the standard way to persist entity state is calling `save` and chaining the returned publisher into the pipeline:

```java
public Mono<Customer> renameCustomer(Long id, String newName) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Customer not found: " + id)
            ))
            .flatMap(customer -> {
                customer.setName(newName);
                return customerRepository.save(customer);
            });
}
```

Execution sequence:

1. `findById` reads the row and emits the entity.
2. `flatMap` receives the entity when present.
3. The setter updates the Java object's state in memory.
4. `save(customer)` creates a publisher representing the save operation.
5. When the pipeline is subscribed to, the save executes and emits the result.

Here, mutating the object and writing to the database are two separate steps, even though they appear in the same pipeline. Omitting `save(customer)` leaves only the in-memory change.

### `save` Chooses INSERT or UPDATE

`save` may run insert or update depending on Spring Data Relational's new-entity detection mechanism. For a typical entity that neither implements `Persistable` nor declares `@Version`, the `@Id` identifier drives the decision: an unassigned ID usually indicates a new entity; a populated ID usually indicates an existing entity. If `@Version` is present, the version takes precedence; if `Persistable` is implemented, `isNew()` is used.

Therefore, `save` does not always translate to an `UPDATE` statement. To understand its exact behavior, examine the entity's state and metadata. `save` also does not query the database by default to verify whether an existing ID is actually present.

### Use the Object Emitted by `save`

Always use the value emitted by the `save` publisher:

```java
return customerRepository.save(customer)
        .map(saved -> new CustomerView(saved.getId(), saved.getName()));
```

This matters when the database generates IDs, Spring Data manages `@Version`, or the entity is immutable. For immutable entities, the framework creates a new instance holding the post-save ID/version instead of mutating the original instance. Consuming the emitted object ensures downstream steps see the post-persistence state.

Avoid calling `save` and then reading ID or version from the input object assuming it was always updated in place.

## 4. Reactive Publishers and When Writes Actually Execute

R2DBC repository operations generally return cold publishers that defer database I/O until subscription. This means calling `save` and executing the write statement happen at two different times.

Example:

```java
Mono<Customer> pendingSave = customerRepository.save(customer);
```

This line creates a publisher. If nothing subscribes to it, the write never starts. A WebFlux controller returns the publisher to the framework so the framework consumes it; in tests, `StepVerifier` subscribes when running verification.

### Chain Publishers So Writes Execute

Correct:

```java
public Mono<Customer> updateName(Long id, String name) {
    return customerRepository.findById(id)
            .flatMap(customer -> {
                customer.setName(name);
                return customerRepository.save(customer);
            });
}
```

Avoid detaching subscriptions from the pipeline:

```java
public Mono<Customer> updateName(Long id, String name) {
    customerRepository.findById(id)
            .flatMap(customer -> {
                customer.setName(name);
                return customerRepository.save(customer);
            })
            .subscribe();

    return Mono.empty();
}
```

In the second example, the service starts an independent subscription and returns a different publisher. Callers cannot await the save result via the returned publisher; errors and lifecycle are detached from the flow managed by the framework. If a reactive transaction wraps the caller, the manual subscription may also execute outside that transaction context.

Return the complete publisher to the caller and let the framework or application boundary subscribe. Never call `subscribe()` inside a service just to trigger a write.

### Avoid Mutating Objects While a Publisher Awaits Subscription

Java field mutations happen immediately when a setter runs, whereas database execution starts when the publisher is subscribed to. Creating a save publisher and then mutating the same object before subscription makes code hard to reason about and risks writing unintended data.

Pattern to avoid relying on:

```java
Mono<Customer> pending = customerRepository.save(customer);
customer.setName("Another name");
return pending;
```

Do not assume the pipeline captures an entity snapshot at the exact line where the publisher is created. Complete all mutations before constructing the save publisher, or use a separate immutable instance for the write. Avoid sharing a mutable entity across multiple pipelines or threads.

## 5. Using Immutable Entities to Clarify Pre-Write State

Immutable entities clearly separate existing data from new state to be persisted. Rather than mutating an existing object, the application creates a new instance carrying the updated values.

Java record example:

```java
@Table("customer")
public record Customer(
        @Id Long id,
        String name
) {
    public Customer withName(String newName) {
        return new Customer(id, newName);
    }
}
```

Service:

```java
public Mono<Customer> renameCustomer(Long id, String newName) {
    return customerRepository.findById(id)
            .map(customer -> customer.withName(newName))
            .flatMap(customerRepository::save);
}
```

`withName` creates a new object. `save` accepts that object and writes it. When the database generates an ID or Spring Data updates a version, use the instance emitted by `save` because it represents the persistence result.

Immutability does not persist data by itself. It only makes creating new in-memory state explicit; explicit persistence calls are still required.

## 6. Persisting Partial Changes vs. Saving the Whole Entity

`repository.save(entity)` persists an entity according to mapping metadata. When the goal is changing only a couple of columns, do not assume `save` acts like a patch statement writing only modified fields. Depending on the API and mapping, saving an entity can issue an update across its persistent properties.

When you explicitly want to update a subset of columns, use `R2dbcEntityTemplate` or `DatabaseClient` to express the targeted update.

### Updating One Column with `R2dbcEntityTemplate`

```java
public Mono<Long> renameCustomer(Long id, String newName) {
    return entityTemplate.update(Customer.class)
            .matching(query(where("id").is(id)))
            .apply(update("name", newName));
}
```

This snippet illustrates `R2dbcEntityTemplate`'s fluent API: specifying the entity/table, matching condition, and property to update. Import the corresponding `query`, `where`, and `update` helpers from Spring Data Relational for your project version.

### Updating One Column with `DatabaseClient`

```java
public Mono<Long> renameCustomer(Long id, String newName) {
    return databaseClient.sql(
                "UPDATE customer SET name = :name WHERE id = :id"
            )
            .bind("name", newName)
            .bind("id", id)
            .fetch()
            .rowsUpdated();
}
```

With this approach, the SQL explicitly states that only the `name` column is updated. The `rowsUpdated()` publisher emits the affected row count upon subscription.

Choose the API by intent:

| Need | Usually Suitable API |
| --- | --- |
| Saving a new entity or persisting mapped entity state | `repository.save(entity)` |
| Explicitly updating a few properties by condition | `R2dbcEntityTemplate.update(...)` |
| Engine-specific SQL, database expressions, or complex updates | `DatabaseClient` |
| Creating a new row with explicit insert intent | `R2dbcEntityTemplate.insert(...)` or SQL `INSERT` |

With custom updates via template or SQL, remember that any Java object currently held in memory is not automatically refreshed from the SQL result. If you need a fresh object matching the database, re-read the row or construct the updated result deliberately.

## 7. Transactions Do Not Track Object Changes

A reactive transaction coordinates database operations within the same transaction context. It allows multiple writes to commit or roll back as a unit. It does not track entity fields or generate SQL updates automatically.

Example:

```java
@Transactional
public Mono<Customer> renameAndRecord(Long id, String newName) {
    return customerRepository.findById(id)
            .switchIfEmpty(Mono.error(
                    new IllegalArgumentException("Customer not found")
            ))
            .flatMap(customer -> {
                customer.setName(newName);
                return customerRepository.save(customer);
            })
            .flatMap(saved -> auditRepository.save(
                    new AuditRecord(saved.getId(), "CUSTOMER_RENAMED")
            ).thenReturn(saved));
}
```

When subscribed to, finding the customer, saving the customer, and saving the audit record execute within a Spring-managed reactive transaction, provided the transaction manager and configuration match. If an operation emits an error, the transaction can roll back database changes made within it.

If `customerRepository.save(customer)` is removed and only `customer.setName(...)` runs, the transaction has no customer update statement to commit. Transactions do not automatically detect setter calls.

### In-Memory Changes Are Not Rolled Back Automatically

Suppose a service mutates a Java object, saves a row, and then a subsequent operation causes the transaction to fail. The database rolls back the statements inside the transaction, yet the Java object sitting in memory does not automatically revert to its pre-transaction snapshot.

For instance, after rollback, the `customer` variable may still hold the new name even though the database reverted to the old name. This is not a transaction bug; transactions manage database state, not Java object snapshots.

If you need reliable state after a rollback, re-read the entity from the database in an appropriate transaction/flow or reconstruct the object from source data. Never assume an object passed to `save` automatically reverts on failure.

### Transactions Apply Only When Publishers Stay in the Managed Pipeline

Avoid calling `subscribe()` manually inside a `@Transactional` method. A new subscription can detach operations from the Spring-managed pipeline's transaction context. Chain all database calls with `flatMap`, `then`, `zip`, or other suitable reactive operators and return the final publisher.

## 8. Entity State After Saving

After a save operation, the input object and the emitted object may differ:

- For entities with database-generated keys, the saved result can contain the new ID.
- For entities with `@Version`, the result can contain the updated version managed by Spring Data.
- For immutable entities, the framework creates a new instance holding the post-save values.
- With custom conversions or entity callbacks, data may be converted or adjusted during persistence as configured.

Accordingly, treat the object emitted by `save` as the authoritative result:

```java
return customerRepository.save(customer)
        .flatMap(saved -> notificationService.prepare(saved.getId(), saved.getName())
                .thenReturn(saved));
```

Do not treat the input object as proof that the database write succeeded. Instantiating an object, calling a setter, or creating a publisher proves neither that SQL executed nor that a transaction committed.

If you need to verify data after writing, re-read via the repository within the same transaction or after commit depending on test goals. Re-reading is especially helpful when database triggers, default values, or generated columns can alter values relative to what was sent.

## 9. Concurrent Updates and Stale Entities

Because loaded entities are no longer automatically managed, multiple requests can read the same row and hold independent objects in memory.

Suppose two requests concurrently read a customer named `Lan`:

1. Request A changes the name to `Lan A`.
2. Request B changes the name to `Lan B`.
3. A saves successfully.
4. B saves afterward using its stale object.

Without concurrency control, the later update can overwrite the earlier change. This is a lost update.

### Using `@Version` to Detect Stale Updates

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

Spring Data includes the version in the update predicate. If one request saves a newer version first, the other request holding the older version fails to match the version predicate and may receive `OptimisticLockingFailureException`.

`@Version` is not dirty checking. The application still must call `save` or execute an explicit update. Versioning simply detects updates based on stale state.

When an optimistic locking failure occurs, handle it per business rules: report a conflict, reload data and ask the user to retry, or recompute the change against the latest version. Avoid blindly retrying an update if the modification is no longer valid against the newest state.

## 10. Entity Callbacks Do Not Replace Save Operations

Spring Data Relational provides lifecycle callbacks for points during persistence—such as before converting an entity or after reading an entity. Callbacks can enrich metadata, normalize values, or run auxiliary logic within Spring Data persistence operations.

Callbacks do not mean Spring Data tracks every entity in memory. If an application loads an entity and calls a setter without calling repository/template/SQL to save, write callbacks will not fire just because the object changed.

Keep the distinction clear:

- Callbacks are triggered as part of an actual persistence operation executed by Spring Data.
- Pure Java object mutation is not a persistence operation and never triggers writes on its own.

If you rely on auditing to populate `createdDate`, `lastModifiedDate`, or modifier info, ensure a real save operation executes and auditing is properly configured. Simply changing fields in memory will not update auditing columns in the database.

## 11. Misleading Code Patterns

### Mutating an Entity Inside `map` and Ending the Pipeline

```java
return customerRepository.findById(id)
        .map(customer -> {
            customer.setName("New name");
            return customer;
        })
        .then();
```

`map` only transforms the emitted item. No database write occurs.

### Calling `save` Without Chaining Its Publisher

```java
return customerRepository.findById(id)
        .doOnNext(customer -> {
            customer.setName("New name");
            customerRepository.save(customer); // Publisher is discarded
        })
        .then();
```

The publisher returned by `save` is never consumed. The save operation never runs. Use `flatMap` to chain the publisher:

```java
return customerRepository.findById(id)
        .flatMap(customer -> {
            customer.setName("New name");
            return customerRepository.save(customer);
        })
        .then();
```

### Subscribing Manually and Returning Assumed Success

```java
customerRepository.save(customer).subscribe();
return Mono.just(customer);
```

The returned publisher does not represent the save outcome. Callers may receive the object before the database operation finishes, and write errors are never propagated through the returned publisher. Return the `save` publisher directly or chain downstream steps onto it.

### Assuming Transaction Commit Flushes Objects

```java
@Transactional
public Mono<Void> rename(Long id) {
    return customerRepository.findById(id)
            .doOnNext(customer -> customer.setName("New name"))
            .then();
}
```

The transaction sees only a read operation. There is no dirty checking to emit an update on commit. You must call `save` or another write API.

## 12. Testing In-Memory Changes vs. Database Changes

An integration test can demonstrate that setters do not persist data automatically:

```java
StepVerifier.create(customerRepository.findById(10L))
        .assertNext(customer -> customer.setName("Changed in memory"))
        .verifyComplete();

StepVerifier.create(customerRepository.findById(10L))
        .assertNext(customer ->
                assertThat(customer.getName()).isEqualTo("Lan")
        )
        .verifyComplete();
```

The first test reads the entity and mutates the object in memory. The second reads back from the database and confirms the stored value did not change.

Testing an explicit write:

```java
Mono<Customer> rename = customerRepository.findById(10L)
        .flatMap(customer -> {
            customer.setName("Lan Nguyen");
            return customerRepository.save(customer);
        });

StepVerifier.create(rename)
        .assertNext(saved ->
                assertThat(saved.getName()).isEqualTo("Lan Nguyen")
        )
        .verifyComplete();

StepVerifier.create(customerRepository.findById(10L))
        .assertNext(customer ->
                assertThat(customer.getName()).isEqualTo("Lan Nguyen")
        )
        .verifyComplete();
```

Other tests should cover:

- An unsubscribed `save` publisher performs no write.
- Writing successfully and reading back to confirm committed data.
- Rolling back a transaction and verifying the database retains prior data while Java objects are not assumed to self-revert.
- Using `@Version` to verify a stale entity cannot silently overwrite a newer version.
- Using immutable entities to verify the `save` result carries the new ID/version used in subsequent steps.
- Using `DatabaseClient` or `R2dbcEntityTemplate` to verify partial updates affect only specified columns.

Repository tests must subscribe to publishers, such as with `StepVerifier`. Constructing a `Mono` or `Flux` in a test without verifying/subscribing does not prove any SQL ran.

## 13. Workflow for Handling Entity Changes in a Service

A service updating an entity typically follows this sequence:

1. Read the entity via repository or template.
2. Validate input data and business preconditions.
3. Produce the new in-memory state via setters or a new immutable instance.
4. Invoke `save`, `R2dbcEntityTemplate.update`, or `DatabaseClient` to describe the write operation.
5. Chain the write publisher into the pipeline so it actually gets subscribed to.
6. Use the result emitted by the save operation in subsequent steps.
7. If multiple database operations must commit/roll back together, place them in a reactive transaction and return the full pipeline to the framework.
8. Handle write errors, optimistic locking failures, and rollbacks per business rules.

Combined example:

```java
@Service
public class CustomerService {

    private final CustomerRepository customerRepository;
    private final AuditRepository auditRepository;

    public CustomerService(
            CustomerRepository customerRepository,
            AuditRepository auditRepository
    ) {
        this.customerRepository = customerRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public Mono<Customer> rename(Long id, String newName) {
        return customerRepository.findById(id)
                .switchIfEmpty(Mono.error(
                        new IllegalArgumentException("Customer not found")
                ))
                .flatMap(customer -> {
                    customer.setName(newName);
                    return customerRepository.save(customer);
                })
                .flatMap(saved -> auditRepository.save(
                        new AuditRecord(saved.getId(), "RENAMED")
                ).thenReturn(saved));
    }
}
```

This example shows the setter mutating the object in memory, `save` creating the customer write operation, and the audit save chained after the customer has been saved. When the publisher is consumed inside a reactive transaction, the database statements coordinate within the same transaction. Entities are not flushed automatically; every write is explicitly represented in the pipeline.

## 14. Summary

- An entity read from R2DBC is a Java object holding data from the time of the read; it is not kept in a persistence context for dirty checking.
- Calling setters, mutating fields, or creating new objects alters only application memory and never generates SQL by itself.
- `@Transactional` manages commit/rollback for database operations executed in the pipeline; it does not detect object mutations or flush entities automatically.
- To persist changes, call `repository.save`, `R2dbcEntityTemplate.insert/update`, or `DatabaseClient` and chain the resulting publisher into the pipeline.
- Reactive write publishers usually start I/O only upon subscription; never discard publishers or call `subscribe()` independently out of the service pipeline.
- Use the object emitted by `save` to obtain post-persistence IDs, versions, and state, especially with immutable entities.
- When only a few columns need to change, use explicit updates to specify exact columns written.
- Database rollbacks do not restore in-memory Java objects; re-read or reconstruct state after a rollback when synchronization is needed.
- `@Version` detects concurrent updates but does not replace save/update operations and is not dirty checking.
- Test by subscribing to publishers and reading back from the database to distinguish in-memory changes from committed data.

When reading an R2DBC service, trace two separate things: where the Java object is mutated and where the database write command is constructed and consumed. If no persistence operation is chained into the pipeline, the new state exists solely in memory—even when the method executes inside a reactive transaction.
