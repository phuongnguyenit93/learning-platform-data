# Handling Version Conflicts on Update or Delete

## 1. Why Can Concurrent Updates Cause Data Loss?

In a Spring Data Relational R2DBC application, multiple requests can read and modify the same record almost simultaneously. Without a conflict-detection mechanism, a later write can overwrite the result of an earlier write, even though the later writer relied on stale data.

Suppose an order currently has status PENDING and two users open the admin screen at the same time:

1. User A reads the order with status PENDING.
2. User B also reads the same order with status PENDING.
3. A changes the status to PAID and saves successfully.
4. B, still holding the stale data, changes the status to CANCELLED and saves afterward.

If the database only updates by ID, B's operation can overwrite PAID with CANCELLED. The application does not know that B edited an outdated version.

This phenomenon is commonly called a **lost update**. The final data reflects the last write, potentially discarding a decision someone else just saved.

Spring Data Relational supports **optimistic locking** via the @Version annotation. This mechanism lets the application detect that an entity has changed since it was read. When a conflict is detected, the update or delete operation is rejected and raises an optimistic locking error.

## 2. How Does Optimistic Locking Work?

Optimistic locking assumes write conflicts do not happen frequently. The application does not hold database locks while users read and edit data. Instead, each record has a version value. On write, the database accepts the operation only if the current version still equals the version the application read.

You can visualize it as:

~~~text
A reads order: version = 5
B reads order: version = 5
          |
          v
A updates with condition version = 5
          |
          v
Database writes successfully, version increments to 6
          |
          v
B updates with condition version = 5
          |
          v
No row matches version = 5
          |
          v
B receives a version conflict error
~~~

The key point is that checking the version and updating the data happen inside the same conditional statement in the database. Therefore, two competing requests cannot both update successfully based on the same old version.

Optimistic locking is well suited for cases where:

- Multiple users can view and edit the same record simultaneously.
- Conflicts do not occur too frequently.
- Holding database locks during user interaction is undesirable.
- Stale data must be detected before overwriting.
- Users can be asked to reload or merge changes when a conflict occurs.

## 3. Declaring the @Version Property

Spring Data Relational recognizes the version property via the annotation:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Table;

@Table("orders")
public class Order {

    @Id
    private Long id;

    @Version
    private Long version;

    private String status;

    public Long getId() {
        return id;
    }

    public Long getVersion() {
        return version;
    }

    public String getStatus() {
        return status;
    }

    public void setStatus(String status) {
        this.status = status;
    }
}
~~~

The @Version annotation belongs to package org.springframework.data.annotation. It marks the property used by Spring Data to track the entity's version.

Typically, version uses an integer numeric type such as Long or Integer. Spring Data manages the version value during inserts, updates, and deletes. The application should not manually increment the version in business code before each save call.

### 3.1. The Database Schema Must Have a Version Column

DDL example:

~~~sql
CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    version BIGINT NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
~~~

The column name is derived from the Java property via the naming strategy or can be specified explicitly with @Column. In this example, version maps to the version column.

If the existing database does not yet have a version column, create a migration before deploying code that uses @Version:

~~~sql
ALTER TABLE orders
ADD COLUMN version BIGINT NOT NULL DEFAULT 0;
~~~

The DEFAULT value in the migration gives existing rows an initial version. When Spring Data manages the version, the framework applies its own initialization and increment rules. Check the DDL, Java type, and Spring Data version in use to ensure compatibility.

### 3.2. Do Not Manage Version Manually in Business Code

Do not write:

~~~java
order.setVersion(order.getVersion() + 1);
return orderRepository.save(order);
~~~

Spring Data needs the old version value to evaluate the update condition and manages the new version value itself. If application code increments it before saving, the value used for checking may no longer match the version in the database, causing the operation to be rejected or breaking version management conventions.

Modify business fields and then call save:

~~~java
order.setStatus("PAID");
return orderRepository.save(order);
~~~

The save publisher emits the entity after a successful save. Use the returned entity, because the resulting object's version has been updated by the save operation.

### 3.3. Version and New Entity Detection

Spring Data needs to distinguish new entities from existing entities. Both ID and version may participate in newness detection depending on data types and entity configuration.

When using @Version, let Spring Data initialize the version per the framework's convention. Do not arbitrarily assign a version to a new entity just to force an insert or update. If an entity uses a custom newness strategy, understand Persistable and how it interacts with ID/version before applying it.

## 4. How Spring Data Builds Versioned Update Conditions

When saving an existing entity with @Version, Spring Data Relational generates a conditional update operation based on the ID and current version.

Conceptually, the equivalent SQL is:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = :nextVersion
WHERE id = :id
  AND version = :expectedVersion;
~~~

Placeholder names, increment mechanics, and exact SQL are determined by Spring Data and the dialect. What matters is that the UPDATE statement has two conditions:

- The ID must match the record being updated.
- The version in the database must equal the version carried by the entity.

If the update succeeds, the version is incremented. If no row satisfies both conditions, Spring Data does not treat it as a normal successful save, but raises an optimistic locking error.

### 4.1. Repository Example

~~~java
public interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {
}
~~~

Service:

~~~java
@Service
public class OrderService {

    private final OrderRepository orderRepository;

    public OrderService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    public Mono<Order> markAsPaid(Long orderId) {
        return orderRepository.findById(orderId)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order -> {
                order.setStatus("PAID");
                return orderRepository.save(order);
            });
    }
}
~~~

The read-then-write flow executes within a reactive pipeline. When save executes, Spring Data uses the version of the newly read entity as the update condition. If another request updated the entity after the read step, save can fail because the version no longer matches.

No database lock needs to be held for the duration between findById and save. The conditional UPDATE statement is the arbitration point deciding which request writes successfully.

### 4.2. Using the Entity Returned After save

Example:

~~~java
return orderRepository.findById(orderId)
    .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
    .flatMap(order -> {
        order.setStatus("PAID");
        return orderRepository.save(order);
    })
    .map(savedOrder -> {
        // savedOrder carries the new version after a successful save
        return toOrderResponse(savedOrder);
    });
~~~

If you keep using an older entity copy held elsewhere, the version in that copy may be outdated. Pass the object returned by save through subsequent steps or reload data when needed.

## 5. What Happens When Two Requests Update Simultaneously?

Suppose the initial version in the database is 3.

| Time | Request A | Request B | Database |
|---|---|---|---|
| 1 | Reads entity | | version = 3 |
| 2 | | Reads entity | version = 3 |
| 3 | Changes status to PAID | | version = 3 |
| 4 | Save succeeds | | version = 4 |
| 5 | | Changes status to CANCELLED | version = 4 |
| 6 | | Saves with expected version 3 | No row matches version 3 |
| 7 | | Receives optimistic locking error | version remains = 4 |

Request B is not allowed to silently overwrite A's change. The application layer can turn this error into a conflict response, prompt to reload data, or apply a change-merging rule.

Optimistic locking does not decide on the user's behalf whether PAID or CANCELLED is more correct. It only detects that the data Request B relied upon is stale. The business decision after a conflict belongs to the application.

## 6. Handling Conflicts on Update

When save raises an optimistic locking error, several handling strategies exist.

### 6.1. Reporting the Conflict and Asking to Reload

This is appropriate when the user needs to inspect the latest data before proceeding.

Service-level error translation example:

~~~java
public Mono<Order> updateStatus(Long orderId, String status) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> {
            order.setStatus(status);
            return orderRepository.save(order);
        })
        .onErrorMap(
            OptimisticLockingFailureException.class,
            error -> new OrderConflictException(orderId, error)
        );
}
~~~

A web application can translate OrderConflictException into HTTP 409 Conflict. The client displays a message indicating the data was modified by someone else and prompts the user to reload.

In an API, do not expose internal database details or stack traces to the client. Return a clear error code and business message.

### 6.2. Reloading and Re-Applying the Change

Some changes can be re-applied onto the latest version. For example, an operation incrementing quantity by 1 can be re-executed after reading the new value, if business rules permit.

Handling should make the intent explicit:

1. Catch the optimistic locking error.
2. Re-read the latest entity.
3. Check the current state and business preconditions.
4. Re-apply the change onto the fresh entity.
5. Attempt to save again with the new version.
6. Cap the number of attempts and handle continued conflicts.

Illustrative example retrying once:

~~~java
public Mono<Inventory> increaseStock(Long productId, int amount) {
    return updateStockOnce(productId, amount)
        .onErrorResume(
            OptimisticLockingFailureException.class,
            error -> updateStockOnce(productId, amount)
        );
}

private Mono<Inventory> updateStockOnce(Long productId, int amount) {
    return inventoryRepository.findById(productId)
        .switchIfEmpty(Mono.error(new ProductNotFoundException(productId)))
        .flatMap(inventory -> {
            inventory.setQuantity(inventory.getQuantity() + amount);
            return inventoryRepository.save(inventory);
        });
}
~~~

This example illustrates reloading the entity on the next attempt. In real implementations, bound retries explicitly and distinguish conflict errors from other database errors. Do not retry infinitely when many requests continuously contend for the same record.

### 6.3. Do Not Blindly Retry the Same Stale Entity

The following snippet does not resolve conflicts:

~~~java
Mono<Inventory> saved = inventoryRepository.save(staleInventory);

return saved.retry(3);
~~~

Because staleInventory still carries the old version, each retry resends the exact version condition that already failed. Retry neither reloads the entity nor reconciles data automatically.

To retry, you must re-execute the entire fresh-read, business-check, and write sequence. If the operation cannot be safely re-applied, return a conflict so the user or business layer can decide.

### 6.4. Checking Operation Idempotency

Not every command can be safely re-applied.

For example:

- Setting status to PAID may be a state assignment, but requires checking current status and payment workflow.
- Incrementing quantity by 1 is an additive operation; re-reading and re-adding may be valid if each request represents an independent event.
- Deducting stock for an order cannot be arbitrarily retried if external system effects have already occurred.
- Sending an email or calling a payment gateway must not be repeated simply because a database save hit a conflict.

When a business flow has side effects outside the database, design an idempotency key, outbox, or appropriate coordination process. Do not let optimistic locking retries accidentally send payments or notifications multiple times.

## 7. Handling Conflicts on Delete

Optimistic locking can apply to deleting a versioned entity. Conceptually, the conditional delete statement looks like:

~~~sql
DELETE FROM orders
WHERE id = :id
  AND version = :expectedVersion;
~~~

If the record was updated by someone else after the entity was read, the version in the database no longer matches. The delete statement affects zero rows and Spring Data detects the conflict.

### 7.1. Deleting a Read Entity

Example:

~~~java
public Mono<Void> deleteOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> orderRepository.delete(order));
}
~~~

The entity passed to delete carries the ID and version read by the application. If another request updates the order before the delete executes, the delete operation can fail because the version changed.

### 7.2. Distinguishing Entity Delete from ID-Only Delete

A delete taking only an ID does not carry the version the client read. Therefore, if the business requirement is "delete only if the record is still at the exact version the user confirmed," you must pass the expected version through the delete workflow and ensure the DELETE statement includes the version condition.

You can read the entity, compare its version with the client's expectedVersion, and then delete that entity:

~~~java
public Mono<Void> deleteIfVersionMatches(
        Long orderId,
        Long expectedVersion) {

    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> {
            if (!Objects.equals(order.getVersion(), expectedVersion)) {
                return Mono.error(new OrderConflictException(orderId));
            }

            return orderRepository.delete(order);
        });
}
~~~

There are two layers of protection in this example:

- Comparing the version against the value sent by the client to detect stale data before deleting.
- Deleting the versioned entity so the database checks again during the write, guarding against another request updating between the comparison step and the delete.

Do not replace delete(entity) with deleteById(id) if the requirement demands checking the client's expected version. An ID-only API cannot convey the version the client observed. Verify method semantics in the Spring Data R2DBC version in use and use a conditional statement when explicit control is needed.

### 7.3. Deletes and Dependent Data

If deleting an aggregate that has child data, check how Spring Data Relational handles aggregates and database foreign keys. Optimistic locking on the aggregate root detects whether the root version changed according to supported mapping mechanics. Foreign key constraints and ON DELETE behaviors remain a separate referential-integrity layer.

If the database rejects a delete due to a foreign key or constraint, that is a data integrity error, not an optimistic locking conflict. Do not map every delete failure to HTTP 409 with the same message without distinguishing the cause.

## 8. Returning the Version to Clients via API

In web applications, clients typically read a resource, edit it, and then send an update request. So the server knows which version the client is basing changes on, you can return the version in the response DTO.

Example:

~~~java
public record OrderResponse(
    Long id,
    String status,
    Long version
) {}
~~~

When the client updates, the request can send back expectedVersion:

~~~java
public record UpdateOrderRequest(
    String status,
    Long version
) {}
~~~

The service compares the client version with the latest entity and uses optimistic locking at save time. Checking the version in the service gives early feedback; the @Version condition in the database remains necessary to protect the window between the read and the write.

### 8.1. Using HTTP ETag and If-Match

Another approach is representing the version via HTTP ETag:

- GET resource returns an ETag containing the version.
- Client sends If-Match when updating or deleting.
- Server accepts the change only if the current version matches the ETag.
- If mismatched, server returns HTTP 412 Precondition Failed or 409 Conflict per API contract.

An ETag can be constructed from the version:

~~~text
ETag: "order-42-v7"
~~~

Update request:

~~~http
PUT /orders/42
If-Match: "order-42-v7"
Content-Type: application/json
~~~

The server parses the ETag, determines the expected version, and executes a versioned operation. ETag is the HTTP contract; @Version is the persistence mechanism. They work together rather than replacing one another.

### 8.2. Do Not Blindly Trust Client-Sent Versions

A version from the client is input data. Validate its format, verify the resource and access permissions, and then use that value as a concurrency condition. Do not let clients arbitrarily choose a new version to overwrite state.

If a client omits the version on an API requiring concurrent-update protection, decide explicitly: require If-Match, return a precondition error, or apply another update policy. Do not silently bypass version control.

## 9. Direct SQL Updates Must Check Version Manually

When using repository save(entity), Spring Data can apply optimistic locking based on @Version. However, a custom SQL statement via DatabaseClient or @Query does not automatically inherit full optimistic locking semantics just because the entity has a @Version field.

If writing an UPDATE manually, include the expected version in WHERE and increment the version in the same statement:

~~~sql
UPDATE orders
SET status = :status,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

With DatabaseClient:

~~~java
public Mono<Void> updateStatus(
        Long orderId,
        Long expectedVersion,
        String status) {

    return databaseClient.sql("""
            UPDATE orders
            SET status = :status,
                version = version + 1
            WHERE id = :id
              AND version = :expectedVersion
            """)
        .bind("status", status)
        .bind("id", orderId)
        .bind("expectedVersion", expectedVersion)
        .fetch()
        .rowsUpdated()
        .flatMap(rows -> {
            if (rows == 1) {
                return Mono.empty();
            }

            return Mono.error(new OrderConflictException(orderId));
        });
}
~~~

For an UPDATE targeting exactly one row, rowsUpdated equal to 1 means the update succeeded. If it equals 0, either the ID does not exist or the version did not match. You can re-read to distinguish a missing record from a version conflict if the API needs two different responses.

When using custom SQL:

- Add the version condition manually.
- Increment the version manually.
- Check the number of affected rows.
- Synchronize the version of any in-memory entity by reloading or updating the result.
- Do not assume @Version automatically intercepts every hand-written SQL statement.

If a custom query omits the version, it can overwrite data without detecting stale entities. This is a common reason why optimistic locking appears to work with repository save yet fails in certain other update paths.

## 10. Combining Optimistic Locking with Reactive Transactions

Optimistic locking and transactions solve two related yet distinct problems:

- Optimistic locking detects that an entity changed since the version was read.
- Transactions ensure a group of database operations commits or rolls back as a single unit per transaction configuration.

For example, an order confirmation flow might update the order and write an audit log:

~~~java
@Transactional
public Mono<Order> confirmOrder(Long orderId) {
    return orderRepository.findById(orderId)
        .switchIfEmpty(Mono.error(new OrderNotFoundException(orderId)))
        .flatMap(order -> {
            order.setStatus("CONFIRMED");
            return orderRepository.save(order);
        })
        .flatMap(savedOrder ->
            auditRepository.save(
                new OrderAudit(savedOrder.getId(), "CONFIRMED")
            ).thenReturn(savedOrder)
        );
}
~~~

If saving the order hits a version conflict, the publisher emits an error and the transaction can roll back. If writing the audit log fails, the transaction can also roll back the order change if both repositories participate in the same reactive transaction.

For transactions to work properly:

1. Use an R2DBC reactive transaction manager.
2. Repositories and transaction manager must share the same ConnectionFactory.
3. Methods must return Mono/Flux so Reactor Context propagates throughout.
4. Do not call subscribe() or block() between steps.
5. Let Spring manage commit/rollback.

A transaction does not eliminate the need for optimistic locking. Two transactions can still both read a stale version; the version condition in the UPDATE/DELETE statement decides which operation succeeds.

### 10.1. When Should a Transaction Be Retried?

If a multi-step transaction encounters an optimistic lock conflict, you usually need to finish the failed transaction before starting a fresh attempt with reloaded data. Do not keep reusing stale entities or the failed transaction state.

Retries should wrap the entire unit of work that can be safely re-run, not just the final save call. Ensure side effects outside the database are not duplicated.

## 11. How Does Optimistic Locking Differ from Pessimistic Locking?

Optimistic locking does not hold a write lock while users view and edit data. It detects conflicts at write time.

Pessimistic locking asks the database to lock a resource to prevent or restrict other transactions from changing data within the locked scope. Specific locking behavior depends on the database engine and transaction.

| Criterion | Optimistic locking | Pessimistic locking |
|---|---|---|
| Mechanism | Compares version at write time | Acquires database lock before or during read/update |
| Holds lock while user thinks | No | Should not hold transactions/locks across long user interactions |
| On conflict | One write fails due to version mismatch | Other transactions may have to wait or be rejected |
| Best suited for | Relatively rare conflicts, read-heavy write-light | High contention or database-level locking rules needed |
| Cost | Requires version column and conflict handling | Can increase wait time, deadlocks, and connection retention |
| Portability | @Version mechanism supported by Spring Data | Lock syntax and semantics depend on database/driver |

With R2DBC, statements such as SELECT ... FOR UPDATE are dialect-dependent and must run inside an appropriate transaction. Do not open a transaction and hold a lock while waiting for a user to submit a form. Choose a strategy based on data access patterns and actual contention levels.

## 12. Limitations and Considerations

### 12.1. All Write Paths Must Respect the Version

@Version protects operations executed through mapping mechanisms that apply optimistic locking. If another job updates SQL directly without incrementing the version, entities in the application may fail to detect that change.

For example, suppose a script runs:

~~~sql
UPDATE orders
SET status = 'PAID'
WHERE id = 42;
~~~

without incrementing the version. An entity still holding the old version may still match the database version and overwrite the script's change. If there are multiple writers, all update paths must follow the version convention or a unified synchronization mechanism.

### 12.2. Version Does Not Replace Business Constraints

@Version does not prevent duplicate emails, negative quantities, or invalid foreign keys. Those rules must be enforced with UNIQUE, CHECK, NOT NULL, FOREIGN KEY, and appropriate business validation.

Optimistic locking only detects that an entity changed by version. It does not check invariants spanning multiple rows or tables.

### 12.3. Aggregate Version and Child Data

Spring Data Relational organizes mapping around aggregate roots. When designing versions, identify which aggregate root represents the business consistency unit. Do not assume every child table or nested object gets an independent version merely because the aggregate root has @Version.

If child data is updated via separate SQL or another repository outside the aggregate save flow, decide explicitly whether that operation should increment the root's version. Writers must coordinate under the same rules to avoid undetected changes.

### 12.4. Cascade Deletes and Operations Outside the Aggregate

Foreign key ON DELETE CASCADE can delete child rows in the database when a parent row is deleted. That is a database referential-integrity mechanism and does not automatically mean every child row undergoes a separate version check.

If business logic requires checking versions of multiple records or preserving history, design an explicit deletion workflow instead of relying entirely on cascades.

## 13. Common Pitfalls

| Error or misconception | Consequence | Resolution |
|---|---|---|
| Forgetting to declare @Version | Updates can overwrite stale data | Add version property and migration |
| Database missing version column | Generated SQL does not match schema | Create migration before deploying code |
| Manually incrementing version before save | Version check condition may be wrong | Let Spring Data manage the version |
| Reusing old entity after save | Continues carrying stale version | Use the entity returned by save |
| Retrying the same stale entity | Repeats the same conflict | Reload, validate, and re-apply intent |
| Catching all exceptions and retrying | Retries constraint, timeout, or connection errors | Handle only OptimisticLockingFailureException per policy |
| Using deleteById when expected version is required | Cannot pass the version the client read | Use versioned entity delete or conditional SQL |
| Custom SQL does not increment version | Other flows may miss the change | Add condition and increment version manually |
| Treating conflict as an abnormal DB error | Confusing user experience | Map to 409/412 or a reload workflow |
| Keeping transactions open too long | Holds connections and increases contention | Limit transactions to database operations |
| Thinking transactions automatically prevent lost updates | Two transactions can still read the same old version | Use @Version or an appropriate locking strategy |
| Not auditing all writers | Scripts or other services bypass version | Standardize update conventions across all writers |

## 14. Process for Implementing Optimistic Locking

When adding version control to an entity, follow this sequence:

1. Identify entities or aggregate roots at risk of concurrent updates/deletes.
2. Add a version property with an appropriate integer type and @Version annotation.
3. Create a migration adding the version column to the existing schema, initializing values for old rows.
4. Check how Spring Data detects new entities and manages versions in the framework version used.
5. Update services to use repository-read entities and pass those entities into save/delete.
6. Translate OptimisticLockingFailureException into a business conflict error.
7. If APIs need client-side version control, include version in DTOs or use ETag/If-Match.
8. For custom SQL, add expected version to WHERE, increment version, and verify rowsUpdated.
9. Evaluate reactive transactions when business logic updates multiple tables.
10. Determine whether retries are safe; if retrying, reload fresh data and re-apply intent.
11. Audit all other write paths such as batch jobs, scripts, or integration services.
12. Write integration tests with two reads of the same version and competing write operations.

## 15. Testing Version Conflicts

A key integration test simulates two requests reading the same entity before either saves.

Structural example:

~~~java
@Test
void shouldRejectUpdateFromStaleVersion() {
    Mono<Order> result = orderRepository.findById(42L)
        .flatMap(firstRead ->
            orderRepository.findById(42L)
                .flatMap(secondRead -> {
                    firstRead.setStatus("PAID");
                    secondRead.setStatus("CANCELLED");

                    return orderRepository.save(firstRead)
                        .then(orderRepository.save(secondRead));
                })
        );

    StepVerifier.create(result)
        .expectError(OptimisticLockingFailureException.class)
        .verify();
}
~~~

This example illustrates two entity copies read prior to saving. The first save increments the version; the second save uses the stale version and must fail. Depending on transaction setup and test fixtures, ensure both reads actually happen before the first save as shown.

Tests should also verify:

- After a successful save, the version increments per framework convention.
- The entity returned by save carries the new version.
- Saving a stale entity raises an optimistic locking error.
- Deleting a stale entity raises a conflict if deletion is versioned.
- Custom SQL with expectedVersion does not update rows when the version mismatches.
- Conflict errors map to appropriate API responses.
- Retries reload the entity and do not repeat external side effects.

Use integration tests with the project's actual R2DBC driver and database. Mocked repository tests may fail to accurately reflect version-conditional SQL and driver concurrency behavior.

## 16. Self-Check Exercises

### Exercise 1: Detecting Lost Updates

Two users read a product with quantity = 10 and version = 2. User A updates quantity = 9 successfully. User B then saves quantity = 8 from the old entity. With @Version, what happens?

Hint: A increments the version. B still sends version 2 while the database already has the new version, so B's operation fails with an optimistic locking error.

### Exercise 2: Declaring Version

Add versioning to a Customer entity with a Long ID.

Hint:

~~~java
@Id
private Long id;

@Version
private Long version;
~~~

Also create the corresponding version column in the schema and a migration for existing data.

### Exercise 3: Handling Conflicts

When save raises OptimisticLockingFailureException, should you retry with the exact same old entity?

Hint: No. The old entity still carries the mismatched version. You must reload, validate business rules, and re-apply the change if safe.

### Exercise 4: Deleting by Expected Version

A client reads an order with version 7 and submits a delete request. Meanwhile, someone else updates the order to version 8. What should the server do?

Hint: Compare expected version 7 against the latest data and reject the request if it has changed. If using entity-based delete, keep the read version and let the delete operation verify again at the database to guard against race conditions after the comparison step.

### Exercise 5: Custom SQL

Write an UPDATE statement that changes status only if the current version equals expectedVersion.

Hint:

~~~sql
UPDATE orders
SET status = :status,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
~~~

Check the number of affected rows to determine success or conflict.

### Exercise 6: Distinguishing Errors

A save operation is rejected because an email violates UNIQUE. Should this error be mapped to an optimistic lock conflict?

Hint: No. A unique constraint violation is a data integrity error distinct from OptimisticLockingFailureException. Map errors according to their actual cause.

### Exercise 7: Does a Transaction Replace @Version?

Two transactions read the same record and sequentially update it. Does using only @Transactional guarantee preventing lost updates?

Hint: No. Transactions protect groups of operations according to the isolation level, but do not automatically compare entity versions. @Version provides version checking on write operations.

## 17. Key Takeaways

- Optimistic locking detects that data has changed since an entity was read.
- Spring Data Relational uses @Version to manage entity versions.
- Schemas need a version column compatible with the Java type.
- On update, the current version is included in the write condition and incremented after a successful save.
- If no row matches the ID and version, the operation may raise OptimisticLockingFailureException.
- Use the entity returned by save because it carries the new version.
- Deleting a versioned entity can check the version; if protecting against the version read by the client, pass the expected version through the delete flow.
- Do not blindly retry stale entities; reload and re-apply changes per business rules.
- Retries are safe only when operations and side effects are idempotent or separately protected.
- Custom SQL must manually add the version condition, increment the version, and inspect affected rows.
- Transactions and optimistic locking complement each other: transactions manage atomicity, while @Version detects concurrent updates.
- All writers must follow the version convention; SQL constraints remain necessary to protect other data invariants.
- For APIs, include version in DTOs or use ETag/If-Match so clients express the version they read.

When designing data updates or deletes where contention may occur, use @Version on appropriate entities, let Spring Data verify the version in the database, and handle conflicts as predictable business outcomes. This mechanism prevents silent overwrites while letting the application decide whether to reload, merge changes, or ask the user for re-confirmation.
