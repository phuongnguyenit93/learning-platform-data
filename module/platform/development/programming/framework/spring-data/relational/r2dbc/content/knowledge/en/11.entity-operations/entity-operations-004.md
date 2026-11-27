# Updating Entities and Handling Non-Existent Records

In Spring Data Relational R2DBC, updating an entity requires clarifying two things: whether the entity is considered new or existing, and what happens if the update statement finds no matching rows in the database. These two issues are related but not identical.

The save() method can be used for both new and existing entities. Spring Data determines the entity's state first, then chooses INSERT or UPDATE. If an entity is recognized as existing but its corresponding row is no longer in the database, save() does not automatically switch to insert. The application must handle zero updated rows according to its business rules.

With R2DBC, these operations return Mono or Flux. Results and errors only materialize when the publisher is subscribed to. Consequently, not-found checks, entity updates, and error translation must be chained within the same reactive pipeline.

## 1. What Is Updating an Entity?

Updating means modifying the data of an existing record. For example, suppose the customer table contains the row:

| id | name | email | status |
|---:|---|---|---|
| 42 | An | an@example.com | ACTIVE |

When renaming the customer, the database must update the row with ID 42:

~~~sql
UPDATE customer
SET name = 'An Nguyen'
WHERE id = 42;
~~~

The WHERE clause identifies which record is updated. If no rows satisfy the condition, the database updates zero records. The application must decide whether that indicates a missing resource, a concurrent conflict, or an acceptable business outcome.

A well-formed conditional update typically requires:

- Identifying the target entity or ID accurately.
- Validating input data and business rules.
- Sending an update statement with the appropriate condition.
- Checking the execution result, particularly the affected row count.
- Translating a failed update into an appropriate result or business error.

## 2. save() Chooses INSERT or UPDATE

Spring Data provides the save() method on repositories:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

This method does not simply mean "update if it has an ID, insert if it does not." Spring Data uses **entity state detection** to determine whether the entity is new or existing.

Under the default mechanism, the determination order is typically:

1. If the entity implements Persistable, Spring Data uses isNew() provided by the entity.
2. If there is a @Version property, Spring Data uses the version state to detect a new entity.
3. If there is no version property, Spring Data checks the ID.

For a wrapper-typed version property such as Long, a null version indicates a new entity; a non-null version indicates an existing entity. For a primitive integer version, the default value 0 indicates a new state. Without a version, a null wrapper ID or a primitive ID at its default value is generally treated as new.

Once state is determined:

| Entity State | Chosen Operation |
|---|---|
| New | INSERT |
| Existing | UPDATE |

Spring Data does not query the database by default before every save to check whether the ID exists. State is inferred from the entity and the new-state detection strategy.

### New Entity

A new entity is saved via insert:

~~~java
Customer customer = new Customer("An", "an@example.com");

Mono<Customer> result = customerRepository.save(customer);
~~~

If the database or application generates the ID during insert, the returned entity may contain the populated ID. If @Version is present, the framework also initializes the version according to Spring Data Relational rules.

If the ID was pre-assigned yet the entity is still recognized as new, Spring Data still chooses insert. If that ID already exists, the database may reject the insert due to a primary key or unique constraint violation.

### Existing Entity

An entity loaded from a repository typically carries its current ID and version:

~~~java
Mono<Customer> result = customerRepository.findById(42L);
~~~

When modifying the object and calling save:

~~~java
return customerRepository.findById(42L)
    .flatMap(customer -> {
        customer.rename("An Nguyen");
        return customerRepository.save(customer);
    });
~~~

Spring Data recognizes the entity as existing and executes an update. If the record was deleted after the read, the update finds no matching row. Spring Data does not automatically switch this operation to insert because doing so could accidentally recreate an entity that business logic intentionally deleted.

## 3. Distinguishing save() from Upsert

save() is a unified repository API for inserting or updating based on entity state. It should not be thought of as a database upsert statement.

**Upsert** is a database behavior that performs an insert if no matching record exists and an update if a matching record already exists, typically based on a primary key or unique constraint. Upsert syntax varies across databases—for instance, PostgreSQL has ON CONFLICT, while MySQL has ON DUPLICATE KEY UPDATE.

| Aspect | save() in Spring Data Relational | Database Upsert |
|---|---|---|
| Branch selection | Based on entity new-state detection | Based on conflict/unique key condition in SQL |
| Existence check | Does not query beforehand by default to check ID | Database checks during statement execution |
| Entity detected as new but ID already exists | Attempts INSERT; may fail with duplicate key | May UPDATE if specified by the upsert clause |
| Entity detected as existing but row is gone | Attempts UPDATE; does not switch to INSERT | May INSERT depending on upsert syntax and conditions |
| Portability | Repository abstraction hides part of the SQL | Syntax and semantics are database-dependent |

If business logic truly needs upsert, design the SQL statement and conflict handling explicitly for the target database. Do not call save() hoping the database will decide between insert and update based on ID.

## 4. Updating Entities with a Repository

In Spring Data R2DBC, repositories typically extend ReactiveCrudRepository:

~~~java
public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}
~~~

A service can look up the entity, check for missing records, mutate state, and save:

~~~java
public Mono<Customer> rename(Long id, String newName) {
    return customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .flatMap(customer -> {
            customer.rename(newName);
            return customerRepository.save(customer);
        });
}
~~~

Execution flow:

1. findById(id) emits a customer if found.
2. If no row exists, the repository emits Mono.empty().
3. switchIfEmpty converts the empty result into a not-found business error.
4. If found, flatMap invokes the state-changing behavior on the entity.
5. save() performs the update and emits the saved entity.

This example fits cases where the entity must be loaded to apply business rules before updating. The entity can also carry a version so optimistic locking detects concurrent modifications.

### findById Not Found

The repository returns Mono.empty() when no entity exists. Do not use null to represent this case:

~~~java
return customerRepository.findById(id)
    .switchIfEmpty(Mono.error(
        new CustomerNotFoundException(id)
    ));
~~~

switchIfEmpty triggers only when the publisher completes without emitting a value. It does not catch database errors; query failures continue along the onError signal.

## 5. What Happens If an Entity Is Deleted Between Read and Update?

Suppose request A reads customer ID 42. Before A saves its changes, request B deletes that customer.

~~~text
Request A                 Database                 Request B
    |                         |                         |
    |---- SELECT id = 42 ---->|                         |
    |<--- Customer 42 --------|                         |
    |                         |<---- DELETE id = 42 ----|
    |                         |---- Deleted ----------->|
    |---- UPDATE id = 42 ---->|                         |
    |<--- 0 matching rows ----|                         |
    |                         |                         |
    v
Cannot update deleted entity
~~~

This is a race condition: a successful read does not guarantee the record still exists at write time. Simply calling findById() before updating is not enough to guarantee the update succeeds.

If the entity has @Version, the update statement generated by Spring Data can check both ID and version. When the record has been deleted or the version no longer matches, zero rows are updated and Spring Data reports an optimistic locking error.

If the entity has no version property, the update still targets the row by ID. When no matching row exists, the save fails; Spring Data does not re-insert the record. The exact exception type depends on the execution path and framework version, so the application layer should handle the actual error emitted rather than relying on an assumed SQL statement.

## 6. Distinguishing Not-Found from Optimistic Locking Conflict

Two situations can cause an update to affect zero rows, yet they carry different business meanings:

- **Not found:** the requested resource does not exist at processing time.
- **Optimistic locking conflict:** the entity was read, but its version in the database changed prior to the update.

When using @Version, a conditional update by ID and version can fail because:

1. The record was deleted.
2. The record still exists, but its version was incremented by another request.

Observing an updated row count of 0 alone is not enough to distinguish these two cases. If the API needs to return 404 for a deleted record and 409 for a version conflict, the application can re-read to determine the current state. However, that extra read can still experience a race condition if data keeps changing. For stronger guarantees, consider transactions, isolation levels, and an appropriate locking strategy.

A common API response policy:

| Scenario | Possible Response |
|---|---|
| Not found during initial read | 404 Not Found |
| Entity deleted before update completes | 404 or 409 depending on contract and classification |
| Version is stale due to another request's update | 409 Conflict |
| Connection or unexpected database error | Appropriate 5xx |

Do not return 404 for all update failures. Optimistic locking failures usually need to be surfaced as conflicts so the client knows to reload or merge the data.

## 7. Role of @Version in Updates

@Version marks the version property that Spring Data uses for optimistic locking. Example:

~~~java
@Table("customer")
public class Customer {

    @Id
    private Long id;

    @Version
    private Long version;

    private String name;

    public void rename(String newName) {
        this.name = newName;
    }
}
~~~

Suppose the database currently stores:

| id | name | version |
|---:|---|---:|
| 42 | An | 5 |

Two requests both load version 5. Request A updates first and the version increments to 6. Request B still holds version 5. When B saves, the update condition no longer matches.

Conceptually, the generated SQL looks like:

~~~sql
UPDATE customer
SET name = :name,
    version = :next_version
WHERE id = :id
  AND version = :previous_version;
~~~

This illustrates the semantics, not a guarantee of the exact SQL every Spring Data version or dialect generates. The framework manages the version for supported entity operations; the application should continue using the entity returned by save() since the post-save version may have changed.

When the affected row count is not as expected due to a version mismatch, Spring Data raises an optimistic locking error, typically OptimisticLockingFailureException. Do not silently ignore this error or overwrite with an unversioned update if business rules require protecting against concurrent edits.

### Version Does Not Replace Initial Not-Found Checks

@Version helps detect when an update no longer matches the state that was read. It does not automatically produce a "customer not found" business message in every situation. If you need to return 404 when the ID does not exist initially, check the lookup result or execute a conditional update and interpret the affected row count.

## 8. Direct Updates with DatabaseClient

It is not always necessary to load the entire entity. If you only need to change a few columns and do not need to run domain object logic, you can use DatabaseClient:

~~~java
public Mono<Integer> updateStatus(Long id, String status) {
    return databaseClient.sql(
            "UPDATE customer SET status = :status WHERE id = :id"
        )
        .bind("status", status)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
~~~

rowsUpdated() returns the row count reported as affected by the database. The application can inspect it:

~~~java
public Mono<Void> updateStatus(Long id, String status) {
    return databaseClient.sql(
            "UPDATE customer SET status = :status WHERE id = :id"
        )
        .bind("status", status)
        .bind("id", id)
        .fetch()
        .rowsUpdated()
        .flatMap(rows -> {
            if (rows == 0) {
                return Mono.error(
                    new CustomerNotFoundException(id)
                );
            }
            return Mono.empty();
        });
}
~~~

This is straightforward when the database/driver reports row counts matching application policy. Note that affected row semantics can differ by database: some engines report matched rows, while others may report rows whose values actually changed. If a statement assigns the exact same old value, a result of 0 does not necessarily mean the record does not exist across all vendors.

If you need to definitively distinguish a missing record from an update that changed no values, perform an additional existence check or write a statement that returns the needed database feedback. Consider race conditions and transactions when adding extra checks.

### Partial Entity Updates

A DatabaseClient update statement modifies only the listed columns. It does not automatically reload or synchronize the full domain entity. If the application still holds a Customer object in memory, that object becomes stale after this SQL runs. Reload the necessary data or update read models explicitly.

## 9. Direct Updates and Optimistic Locking

When writing custom SQL, @Version on the entity does not automatically rewrite SQL supplied by the application to DatabaseClient. To preserve optimistic locking protection, the statement itself must check and increment the version:

~~~sql
UPDATE customer
SET status = :status,
    version = version + 1
WHERE id = :id
  AND version = :expected_version;
~~~

Example:

~~~java
public Mono<Integer> updateStatus(
        Long id,
        Long expectedVersion,
        String status) {

    return databaseClient.sql(
            "UPDATE customer " +
            "SET status = :status, version = version + 1 " +
            "WHERE id = :id AND version = :expectedVersion"
        )
        .bind("status", status)
        .bind("id", id)
        .bind("expectedVersion", expectedVersion)
        .fetch()
        .rowsUpdated();
}
~~~

If rowsUpdated() returns 0, there are at least two possibilities:

- No row with that ID exists.
- The row exists, but its version does not equal expectedVersion.

The application can check existence to classify the failure:

~~~java
return updateStatus(id, expectedVersion, status)
    .flatMap(rows -> {
        if (rows > 0) {
            return Mono.empty();
        }

        return customerRepository.existsById(id)
            .flatMap(exists -> exists
                ? Mono.error(new CustomerConflictException(id))
                : Mono.error(new CustomerNotFoundException(id))
            );
    });
~~~

This illustrates an application-level classification policy. Checking existsById() after the update may observe newer or altered state if another request runs in between. For consistent classification, place operations inside a transaction with suitable isolation/locking for your database, or use a vendor-specific statement capable of returning the required state.

Never allow a custom SQL write path to modify data while forgetting to increment the version. If another request holds the old version, its subsequent update would fail to detect the earlier change.

## 10. Choosing Between Load-Modify-Save and Direct Update

The two approaches suit different needs:

| Criterion | Load -> Modify -> save() | DatabaseClient UPDATE |
|---|---|---|
| Reads entity first | Yes | Not required |
| Applies domain rules on object | Convenient | Application must organize manually |
| Mapping and version | Managed by Spring Data via entity metadata | Custom SQL must manage explicitly |
| Affected row check | Handled by Spring Data in persistence path | Application inspects rowsUpdated() |
| Updating a few columns | Writes according to entity mapping | Explicit and concise for narrow updates |
| Best suited for | Changes involving business behavior or requiring entity | Bulk updates, narrow updates, or custom queries |

Use load-modify-save when you need to inspect current state, enforce domain behavior, or leverage Spring Data's @Version. Use direct update when the operation maps cleanly to a single SQL statement and the application explicitly handles affected rows, version, transactions, and in-memory object consistency.

## 11. Error Handling in the Reactive Pipeline

Because repositories return Mono or Flux, database errors are not thrown synchronously at the method call site. They are typically emitted when the publisher is subscribed to. Persistence errors can be mapped to business errors:

~~~java
public Mono<CustomerResponse> rename(
        Long id,
        String newName) {

    return customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .flatMap(customer -> {
            customer.rename(newName);
            return customerRepository.save(customer);
        })
        .map(customer -> new CustomerResponse(
            customer.getId(),
            customer.getName()
        ))
        .onErrorMap(
            OptimisticLockingFailureException.class,
            error -> new CustomerConflictException(id, error)
        );
}
~~~

CustomerNotFoundException and CustomerConflictException in this example are application-defined types. The web layer can map them to 404 and 409 per the API contract.

Avoid catching all errors and returning Mono.empty(). Doing so turns connection errors, SQL errors, constraint violations, or optimistic locking failures into an "empty data" result, preventing callers from distinguishing the cause.

Avoid using onErrorResume to unconditionally retry a conflicting update. If retrying is required, reload the fresh version, reapply business changes, and verify the operation's idempotency.

## 12. Transactions for Multi-Step Updates

A business operation may need to update a customer and write an audit record. If both operations must succeed or fail together, use a reactive transaction:

~~~java
@Transactional
public Mono<Customer> changeStatus(Long id, String status) {
    return customerRepository.findById(id)
        .switchIfEmpty(
            Mono.error(new CustomerNotFoundException(id))
        )
        .flatMap(customer -> {
            customer.changeStatus(status);
            return customerRepository.save(customer);
        })
        .flatMap(saved ->
            auditRepository.recordStatusChange(
                saved.getId(), status
            ).thenReturn(saved)
        );
}
~~~

The method must return the publisher so Spring can manage the reactive transaction. Repositories must share the same reactive transaction manager and ConnectionFactory. Do not call subscribe() inside a transactional method, as a detached subscription can execute outside the transaction context.

Transactions guarantee atomicity across operations within the transaction. @Version is still needed to detect if another request modified the entity since it was read. Transactions and optimistic locking solve two different problems.

## 13. Common Scenarios

| Scenario | Behavior to Understand | Resolution |
|---|---|---|
| ID does not exist when calling findById | Repository emits Mono.empty() | Use switchIfEmpty to return not-found |
| Entity detected as new but ID collides | Spring Data chooses INSERT | Handle duplicate key or fix new-state strategy |
| Entity detected as existing but row was deleted | UPDATE matches nothing; does not auto-INSERT | Return appropriate error, typically not-found or conflict |
| Stale version due to another request's update | Optimistic locking fails | Return conflict, reload, and resolve |
| Custom SQL updates 0 rows | May be missing row or version mismatch | Check conditions and classify per policy |
| Reassigning the same old value | Affected rows may depend on database | Confirm driver/database semantics |
| Updating multiple tables in one business flow | May require atomicity | Use an appropriate reactive transaction |
| A write path skips incrementing version | Can mask conflicts | Every write path must follow version rules |

## 14. Designing API Responses for Updates

An update API needs a clear contract for not-found and conflict cases:

~~~text
PUT /customers/{id}
       |
       v
Find customer by ID
       |
       +---- Not found ----> 404 Not Found
       |
       v
Validate and apply changes
       |
       v
Save entity
       |
       +---- Version conflict ----> 409 Conflict
       |
       +---- Database error ------> 5xx
       |
       v
Return response DTO
~~~

These status codes are a common API design choice, not a mandatory Spring Data rule:

- 404 Not Found: ID does not exist at check time per the API contract.
- 409 Conflict: current state no longer matches the version read by the client or service.
- 400 Bad Request or 422 Unprocessable Content: invalid input data per the API contract.
- 5xx: infrastructure or database error not handled as a business outcome.

If the API accepts a version from the client, the version can serve as a concurrency token or be represented via HTTP ETag/If-Match. When the token no longer matches, return an appropriate conflict response. Validate the token and never let clients set arbitrary versions to overwrite data.

## 15. Summary

- save() chooses INSERT or UPDATE based on entity new-state detection; it is not a database upsert by default.
- Entities detected as existing follow the update path. If the record is gone, Spring Data does not re-insert it.
- findById() returns Mono.empty() when not found; use switchIfEmpty to turn it into a not-found error.
- There is a race condition between reading and writing; a successful read does not guarantee the subsequent update will succeed.
- @Version helps detect concurrent modifications. An update with a mismatched version can raise OptimisticLockingFailureException.
- Direct SQL via DatabaseClient requires inspecting rowsUpdated() and manually adding the version predicate/increment if optimistic locking is needed.
- Affected row counts can vary by database, especially when updating a column to its existing value.
- Not-found and optimistic locking conflicts carry different meanings; do not collapse all update errors into 404 or an empty result.
- Use reactive transactions for multi-step operations requiring atomicity, and keep the pipeline intact rather than calling subscribe() inside services.
