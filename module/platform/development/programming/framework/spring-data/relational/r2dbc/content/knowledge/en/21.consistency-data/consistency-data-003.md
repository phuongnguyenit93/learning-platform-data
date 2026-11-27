# Optimistic Locking with @Version

When multiple requests or multiple processes read and update the same record simultaneously, one request can overwrite changes that another request just saved. This is a *lost update* scenario. In Spring Data R2DBC, the `@Version` annotation provides an *optimistic locking* mechanism to detect this situation when saving an entity.

Optimistic locking does not hold a database lock while the application reads and processes data. Instead, the entity carries a version value. When updating, Spring Data only writes if the version in the database still equals the version the application originally read. If another request updated the record first, the version condition no longer matches and the current operation fails with an optimistic locking error.

## 1. The Lost Update Problem

Suppose a customer has the display name `An`, and the record currently has `version = 4`. Two requests, A and B, read this same state almost simultaneously.

```text
Database: display_name = "An", version = 4

Request A                         Request B
---------                         ---------
Read name "An", version 4         Read name "An", version 4
Change name to "Anh An"           Change name to "An Nguyen"
Write update                      Write update
```

If the update statement relies solely on the primary key, both requests can write successfully. The later write overwrites the earlier request's value. The database has no idea the second request was based on stale state.

Optimistic locking adds a version condition to the write operation:

```sql
UPDATE customers
SET display_name = :displayName,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
```

The first request updates the row with `version = 4`, after which the version becomes 5. The second request still sends `expectedVersion = 4`; the `WHERE` condition no longer matches, so no row is updated. Spring Data raises an optimistic locking error to inform the application that the data has changed since the previous read.

## 2. How Does @Version Work?

`@Version` marks the property used to track an entity's version. The annotation resides in the `org.springframework.data.annotation` package and is used by Spring Data Relational during inserts, updates, and persistence operations that support versioning.

For a numeric version property, the general flow is as follows:

1. When creating a new entity, the version is unset or holds an initial value according to the data type's rules.
2. On insert, Spring Data initializes the version in the record.
3. When reading an entity, the application receives both the ID and the current version.
4. On update, Spring Data uses the ID and old version as the condition to identify the row to modify.
5. If the update succeeds, the version is incremented.
6. If no row matches the ID and old version, Spring Data reports an optimistic locking error.

Diagram of two requests updating the same version:

```text
                    Read version = 4
                    /             \
                   /               \
             Request A          Request B
             expected = 4       expected = 4
                  |                  |
                  v                  v
        UPDATE ... version=4  UPDATE ... version=4
                  |                  |
                  v                  v
        Matched 1 row         Matched 0 rows
        version -> 5          version is already 5
                  |                  |
                  v                  v
               Success       Optimistic locking error
```

The version check and increment occur inside the database operation, so two requests cannot both succeed based on the same old version if both update the same versioned row.

## 3. Declaring the Version Property in an Entity

### 3.1. Entity Using Long

Customer entity example:

```java
package com.example.store.customer.persistence;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record CustomerEntity(
        @Id Long id,
        String email,
        @Column("display_name") String displayName,
        @Version Long version
) {
}
```

`@Version` is placed on the `version` property. The `Long` type can represent `null`, which is convenient for recognizing a new entity when IDs are pre-assigned or when the application needs to distinguish an uninserted state from a database-initialized version.

With a standard Java class, the version property can be a `Long` field or another compatible numeric type. If using a primitive type like `long`, the default value is `0`; Spring Data applies corresponding newness detection rules. Choose a type consistent with the schema and the application's ID generation strategy.

### 3.2. Database Schema

The version column must exist in the table and have a type compatible with the Java property. PostgreSQL example:

```sql
CREATE TABLE customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(254) NOT NULL UNIQUE,
    display_name VARCHAR(120) NOT NULL,
    version BIGINT NOT NULL
);
```

Spring Data manages the version value during supported save operations. For an existing schema with data, a migration must add the column and initialize the version for existing rows, for example:

```sql
ALTER TABLE customers
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
```

Real migrations must follow the project's schema tooling and workflow. Do not just add the Java property and expect the database to automatically have the corresponding column. If the column name differs from the property name, declare `@Column` appropriately.

### 3.3. Version Initialization Rules

For numeric versions, Spring Data uses an initial value for new entities and increments the version upon successful updates. Typically:

- A wrapper such as `Long` can be `null` before insert.
- A primitive numeric type has a default value of `0`.
- After insert, the saved entity has the initialized version, typically `0`.
- Each time an update passes the version check, the version increments by one.

Do not manually assign an arbitrary version to a new entity to manipulate SQL generation. Let Spring Data determine new/existing state based on entity metadata and versioning rules. For entities with application-assigned IDs, a version property is especially helpful for distinguishing unsaved entities from existing ones; check how `isNew` behaves for the chosen version type.

## 4. Updating a @Version Entity Through a Repository

### 4.1. Repository

```java
package com.example.store.customer.persistence;

import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<CustomerEntity, Long> {
}
```

You do not need to write a custom `UPDATE` statement just to check the version when using `save` under Spring Data Relational's standard mapping mechanism. The repository recognizes the `@Version` property on the entity and applies optimistic locking to appropriate update operations.

### 4.2. Creating a New Entity

```java
CustomerEntity draft = new CustomerEntity(
        null,
        "an@example.com",
        "An",
        null
);

return customerRepository.save(draft);
```

On insert, Spring Data creates a new row and initializes the version. With immutable entities like records, `save` emits the saved instance; use that instance to obtain the assigned ID and version.

```java
return customerRepository.save(draft)
        .map(saved -> {
            // saved has the ID and version after insert.
            return saved;
        });
```

Do not continue using `draft` as if it were mutated in place. An immutable entity does not receive the new ID/version via setters; the return value from `save` represents the persisted state.

### 4.3. Reading, Copying, and Saving

With immutable entities, business methods create a new instance while preserving the ID and version that were just read:

```java
@Table("customers")
public record CustomerEntity(
        @Id Long id,
        String email,
        @Column("display_name") String displayName,
        @Version Long version
) {
    public CustomerEntity rename(String newName) {
        if (newName == null || newName.isBlank()) {
            throw new IllegalArgumentException("Name is required");
        }

        return new CustomerEntity(id, email, newName.trim(), version);
    }
}
```

The service chains operations with Reactor:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<CustomerEntity> rename(Long id, String newName) {
        return repository.findById(id)
                .switchIfEmpty(Mono.error(
                        new CustomerNotFoundException(id)))
                .map(customer -> customer.rename(newName))
                .flatMap(repository::save);
    }
}
```

`rename` preserves the `id` and `version` of the entity that was read. `save` uses that version as the expected version. When the update succeeds, the publisher emits the saved entity with the new version. If another request wrote first, the publisher emits an optimistic locking error.

### 4.4. Do Not Manually Increment the Version in the Service

Do not write:

```java
return new CustomerEntity(id, email, newName, version + 1);
```

The version must reflect the version that was read so the database can compare against it. Spring Data is responsible for incrementing the version when the update succeeds. If the service increments it manually before calling `save`, it may send a non-existent expected version and cause the operation to be rejected.

## 5. Handling Optimistic Locking Errors in Reactive Pipelines

When the version no longer matches, Spring Data raises an exception from the optimistic locking/concurrency failure hierarchy, typically `OptimisticLockingFailureException` in Spring's DAO abstraction. With reactive repositories, the error is emitted as an error signal on the `Mono` or `Flux`.

Do not treat this error as a normal connection error or silently ignore it. It indicates that the state the request was modifying has become stale.

### 5.1. Mapping to a Business Error

You can translate the persistence exception into an application exception for the API layer to handle:

```java
public Mono<CustomerEntity> rename(Long id, String newName) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .map(customer -> customer.rename(newName))
            .flatMap(repository::save)
            .onErrorMap(OptimisticLockingFailureException.class,
                    error -> new CustomerConflictException(id, error));
}
```

The example above illustrates exception translation; in a real application, ensure `CustomerConflictException` preserves the original cause for logging and observability. If a transaction wraps multiple operations, consider placing error mapping at an appropriate boundary and do not swallow errors inside a transaction when other operations must roll back.

### 5.2. Mapping to an HTTP Response

An update based on a stale version can usually be represented by HTTP `409 Conflict`. If the API uses HTTP conditional mechanisms like `ETag` and `If-Match`, a stale version may be represented by `412 Precondition Failed` depending on the API contract.

WebFlux layer handling example:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(CustomerConflictException.class)
    public ResponseEntity<ApiError> handleConflict(
            CustomerConflictException exception) {
        ApiError body = new ApiError(
                "CUSTOMER_VERSION_CONFLICT",
                "Customer was changed by another request");

        return ResponseEntity.status(HttpStatus.CONFLICT).body(body);
    }
}
```

Do not return `200 OK` if the save operation failed due to a stale version. The client must know that its change was not persisted so it can reload the data and decide how to proceed.

### 5.3. Do Not Swallow Errors Inside a Transaction

If a service method performs multiple write operations within the same transaction, an optimistic locking failure may need to roll back the entire business operation. Do not use `onErrorResume` inside the pipeline to replace the error with a default value and continue committing other operations if doing so leaves data in an inconsistent state.

Let the error propagate out of the transaction boundary, then map it to a response at the communication layer. If the business logic has a recovery rule, execute it as a separate, intentional flow.

## 6. Two Concurrent Requests and the Version Check Outcome

Suppose two requests read the same entity:

```java
CustomerEntity firstRead = new CustomerEntity(
        10L, "an@example.com", "An", 7L);

CustomerEntity secondRead = new CustomerEntity(
        10L, "an@example.com", "An", 7L);
```

Request A creates a copy and saves first:

```java
CustomerEntity updateA = firstRead.rename("Anh An");
```

After `save(updateA)` succeeds, the database has version 8. Request B still holds version 7:

```java
CustomerEntity updateB = secondRead.rename("An Nguyen");
```

When B calls `save(updateB)`, the update condition equivalent to `WHERE id = 10 AND version = 7` no longer matches. B receives an optimistic locking error instead of overwriting A's name.

The crucial point is that the version check takes place at the database inside the write statement. Checking the version by reading first and comparing in Java is not safe enough, because another request can still update between the check step and the update statement.

## 7. Optimistic Locking and Transactions

Transactions and optimistic locking solve related but distinct problems.

- **Transaction** groups multiple operations into a single commit/rollback unit and controls consistency via isolation levels.
- **Optimistic locking** detects that an entity has been modified since the read that the request relied upon.

A transaction at `READ_COMMITTED` does not automatically prevent all lost updates. If two transactions both read version 7 and then sequentially attempt to update, the version condition lets the second transaction detect the conflict.

Business method example:

```java
@Transactional
public Mono<CustomerEntity> changeCustomerName(Long id, String newName) {
    return repository.findById(id)
            .switchIfEmpty(Mono.error(new CustomerNotFoundException(id)))
            .map(customer -> customer.rename(newName))
            .flatMap(repository::save);
}
```

Reactive transactions are propagated through Reactor Context. Keep operations within the same pipeline and do not manually call `subscribe()` or `block()` to detach work from the transaction. If the business logic only performs a single version-checked update statement, an explicit transaction may not be needed; if multiple statements must commit or roll back together, define a transaction boundary.

## 8. Operations Not Automatically Protected Like Entity Save

`@Version` is used by Spring Data in persistence operations that carry entity metadata, such as updating an entity via `save`. Do not assume every write SQL statement in the application automatically checks the version.

### 8.1. Bulk Updates with Query/Template

A direct conditional update statement:

```java
template.update(query, update, CustomerEntity.class);
```

typically performs a bulk update by predicate without loading each entity or executing the `find -> modify -> save` cycle for each instance. Do not assume it automatically applies per-entity optimistic locking. If a bulk operation needs a version check, explicitly design the version condition and increment logic, and inspect the affected row count.

### 8.2. Hand-Written SQL or DatabaseClient

With hand-written SQL, you must explicitly include the version condition in the statement:

```sql
UPDATE customers
SET display_name = :displayName,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
```

After execution, inspect the affected row count:

- `1`: the update matched the version and succeeded.
- `0`: the ID does not exist or the version mismatched; distinguish the two cases if the API requires different responses.

Do not concatenate input values directly into SQL. Use bind parameters for ID, update values, and expected version. If custom SQL needs to return the updated entity, retrieve the new version from the database or re-read within the same transaction by design.

### 8.3. deleteById and Entity Delete

`deleteById(id)` accepts only an ID, so the caller does not provide the previously read version for comparison. If business logic requires protecting deletion based on the state/version the user viewed, use an entity/version-aware delete operation or custom SQL with `WHERE id = :id AND version = :expectedVersion`, then verify the affected row count. Verify exact behavior against the repository method and Spring Data version in use.

## 9. Scope of Version in the Aggregate Model

A version belongs to the entity carrying the `@Version` property; it does not automatically become a global version for all related tables.

For example, `OrderEntity` has `@Version`, while `OrderLineEntity` rows are dependent records:

```java
@Table("orders")
public record OrderEntity(
        @Id Long id,
        String status,
        @Version Long version
) {
}
```

If all aggregate modifications go through the root and an appropriate save flow, the root's version can serve as the concurrency control point for that operation. However, if another piece of code directly updates the `order_lines` table via SQL or a separate repository, do not assume the `orders` version is automatically checked or incremented.

Define aggregate boundaries and write rules clearly:

- If modifying an order line must count as modifying the order, ensure the write flow includes a mechanism to update/check the root version by design.
- If order lines are independent aggregates, they may need their own version column on the order lines table.
- If multiple aggregates are updated in the same business flow, use transactions and concurrency rules for each aggregate.

Do not rely on a root's version column as a guarantee that direct mutations to child tables will be detected.

## 10. When Should You Use Optimistic Locking?

Optimistic locking is suitable when:

- Update conflicts are relatively rare.
- Multiple users may read the same data while editing takes an extended time.
- You do not want to hold database locks during user interaction.
- You need to detect and report when data has changed.
- Each write can check a clear scalar version.

Suitable examples include editing customer profiles, updating configurations, modifying order details, or changing document content.

Optimistic locking may be unsuitable if a row is continuously updated with high conflict rates, or if business rules require all updates to be serialized. In such cases, consider redesigning data boundaries, using atomic database updates, or evaluating locking mechanisms suited to the database and transaction.

### 10.1. Comparison with Pessimistic Locking

| Criterion | Optimistic locking (`@Version`) | Pessimistic locking |
|---|---|---|
| Control mechanism | Compare version at write time | Hold database lock during transaction |
| Conflicts | Detected at update/delete time | Can block other transactions upfront |
| Lock duration | No lock held while user edits | Depends on transaction duration |
| Best suited for | Low contention, read-heavy, checked writes | High contention or strict serialization needed |
| Failure handling | Client/service handles version conflict | May wait, time out, or deadlock |

Not every database/driver or Spring Data R2DBC API provides the same pessimistic locking capabilities. Optimistic locking via `@Version` is often a straightforward way to detect lost updates at the entity layer.

## 11. Retries and Conflict Handling

When receiving an optimistic locking error, do not automatically retry with the exact same stale entity. That entity still carries the old version, so subsequent retries will typically continue failing.

A sensible retry workflow when business rules allow:

1. Re-read the latest entity.
2. Check whether someone else's change invalidates the current request.
3. Re-apply the business action onto the new state.
4. Save the new entity with the new version.
5. Limit the number of attempts and return a conflict if it keeps failing.

For example, if the operation sets an independent, idempotent flag, re-reading and re-applying may be safe. If two users edit the same text content, automatic retries could overwrite one user's intent; in that case, return a conflict so the user can review and merge changes.

Do not use unbounded `retry()` for optimistic locking. Retries need a cap, backoff if appropriate, and should only be used when business logic clearly defines how to safely merge or re-apply.

## 12. Using Versions in APIs with ETag and If-Match

If clients edit data over HTTP, you can expose the version as an ETag so the client sends back the version it read.

Response example:

```http
HTTP/1.1 200 OK
ETag: "7"
Content-Type: application/json
```

Client update:

```http
PUT /customers/10
If-Match: "7"
Content-Type: application/json
```

The server can compare `If-Match` with the current version and use database optimistic locking to guard the write. Checking at the HTTP layer gives early feedback, but does not replace the version condition in the update statement because data can still change between the HTTP check and the write step.

When the version no longer matches, the API can return `412 Precondition Failed` per HTTP conditional semantics. If the API does not use ETag/If-Match, `409 Conflict` is typically a clear way to represent a business conflict.

You do not necessarily need to include the version in the JSON body if using ETag. What matters is that the client sends back a version token the server can validate and the database still performs an atomic check at write time.

## 13. Testing Optimistic Locking

Unit tests with mocks can verify that a service passes an entity with an old version to the repository and maps exceptions. However, they do not prove the real SQL includes a version condition or that the database returns an error properly. Integration tests against a suitable database/driver are required.

### 13.1. Testing New Entities and Version Initialization

Save a new entity, then verify the returned entity has an ID and an initialized version per the Spring Data rules of the version in use.

```java
CustomerEntity draft = new CustomerEntity(
        null, "an@example.com", "An", null);

StepVerifier.create(repository.save(draft))
        .assertNext(saved -> {
            assertThat(saved.id()).isNotNull();
            assertThat(saved.version()).isNotNull();
        })
        .verifyComplete();
```

### 13.2. Testing That Successful Updates Increment the Version

```java
StepVerifier.create(repository.findById(customerId)
        .flatMap(current -> repository.save(current.rename("Anh An"))))
        .assertNext(saved -> {
            assertThat(saved.displayName()).isEqualTo("Anh An");
            assertThat(saved.version()).isEqualTo(initialVersion + 1);
        })
        .verifyComplete();
```

This example assumes `initialVersion` is the version read prior to the update. With immutable entities, use the entity returned by `save` to check the new version.

### 13.3. Testing Two Reads with the Same Version

```java
Mono<CustomerEntity> firstRead = repository.findById(customerId);
Mono<CustomerEntity> secondRead = repository.findById(customerId);

Mono<Void> scenario = firstRead.flatMap(first ->
        secondRead.flatMap(second ->
                repository.save(first.rename("Name A"))
                        .then(repository.save(second.rename("Name B")))
                        .then()));

StepVerifier.create(scenario)
        .expectError(OptimisticLockingFailureException.class)
        .verify();
```

This test illustrates the idea of two instances carrying the same version; after the first instance is saved, saving the second must fail. Depending on how test transactions and connections are configured, ensure both reads actually occur before the first update and are not isolated inside the same snapshot transaction in a way that alters the expected outcome.

A clearer testing approach is to read two instances in setup, save instance A, then save instance B and assert the error. Do not wrap the entire scenario in an auto-rollback test transaction if doing so alters the concurrency behavior under test.

### 13.4. Testing Custom Updates

If the application uses `DatabaseClient` or bulk updates, test the affected row count both when the version matches and when it mismatches. Ensure the SQL increments the version exactly once and does not update when the expected version is stale.

### 13.5. Testing API Mapping

If using ETag/If-Match, verify:

- Responses return an ETag matching the current version.
- Requests sending the current version update successfully.
- Requests sending an old ETag receive a conflict/precondition failure.
- Two concurrent requests cannot both write successfully based on the same version.

## 14. Common Pitfalls

### Forgetting to Declare @Version on the Entity

Without version metadata, `save` cannot automatically apply optimistic locking to the entity. Add `@Version` to the property and a corresponding column in the schema.

### Having the Java Property but Missing the Database Column

The application may fail on read or write because the SQL references a non-existent column. Create a migration and backfill existing data before deploying code that depends on the new column.

### Not Using the Entity Returned by save

The version is updated in the persisted instance. For immutable entities, the input object is not mutated; use the publisher emitted by `save` for subsequent steps.

### Manually Incrementing the Version in Business Code

Version is persistence metadata. Keep the read version when creating copies; Spring Data increments it when the update succeeds.

### Retrying the Same Stale Entity

The entity still carries the old version, so retrying does not resolve the conflict. You must re-read, evaluate the new state, and re-apply the action if business rules allow.

### Assuming Transactions Automatically Replace Version Checks

Transactions provide commit/rollback boundaries and isolation; they do not imply all lost updates are automatically detected. Use `@Version` when you need to detect that an entity changed since it was read.

### Assuming Bulk Updates Automatically Check Versions

Custom SQL and query-based updates do not necessarily go through the entity save pipeline. If optimistic locking is needed, put the expected version in the predicate and check affected rows.

### Assuming Root Version Protects All Child Tables

A version belongs to the annotated entity. Direct updates to child tables may bypass the root's version mechanism. Clearly define aggregate boundaries and write flows.

### Swallowing the Exception and Returning Success

If a version conflict is turned into a default value or a success response, the client does not know its change was not saved. Return a conflict or execute an explicit merge workflow.

## 15. Process for Applying @Version

1. Identify entities/aggregates that may be updated concurrently by multiple requests.
2. Add a version column with an appropriate numeric type to the schema and migrate existing data.
3. Declare the `@Version` property in the entity.
4. Check the ID strategy and new-entity detection rules, especially when IDs are pre-assigned.
5. Use `save` via Spring Data Repositories for operations needing automatic optimistic locking.
6. With immutable entities, create copies while preserving the read ID and version.
7. Use the entity returned by `save` to obtain the new version.
8. Handle `OptimisticLockingFailureException` as a meaningful business conflict.
9. Retry only when re-reading and re-applying the action is safe and bounded.
10. For custom SQL/bulk updates, explicitly design expected-version predicates and verify affected rows.
11. Define transactions/isolation for multi-step business flows.
12. Write integration tests with two reads of the same version and competing updates.

## 16. Quick Checklist

- [ ] Entity has a property annotated with `@Version`.
- [ ] Version column exists in schema with a compatible type.
- [ ] Existing data is backfilled when adding the version column.
- [ ] New entities initialize the version according to Spring Data rules.
- [ ] Updates use ID and read version as the condition.
- [ ] Version increments only when the update operation succeeds.
- [ ] Immutable entities preserve ID/version when creating copies.
- [ ] Code uses the entity emitted by `save`.
- [ ] Version is never manually incremented in Services or mappers.
- [ ] Conflicts are translated into appropriate business/API errors.
- [ ] No infinite retries or retries using the same stale entity.
- [ ] Bulk/custom SQL includes its own version predicate if concurrency protection is required.
- [ ] Version scope with respect to aggregates and child tables is clearly defined.
- [ ] Transactions/isolation meet consistency requirements.
- [ ] Integration tests prove two updates with the same version cannot both succeed.

`@Version` helps Spring Data R2DBC detect updates based on stale data via an atomic comparison in the database. When an entity carries the read version, `save` succeeds only if the row is still at that version; otherwise, the application receives a conflict error and can ask the client to reload, merge, or re-apply the action according to business rules. This mechanism is particularly useful for read-heavy, write-light flows that must avoid lost updates without holding database locks during user editing.
