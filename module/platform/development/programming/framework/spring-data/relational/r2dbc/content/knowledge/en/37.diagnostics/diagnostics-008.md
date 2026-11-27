# Version Conflicts, Constraint Violations, and Zero Rows Updated

In Spring Data Relational R2DBC, a write operation can fail for several different reasons. Three situations frequently confused are data constraint violations, version conflicts when concurrent transactions modify the same entity, and `UPDATE`/`DELETE` statements affecting zero rows.

They look similar at the API layer—a request fails to persist data—but their meanings and fixes differ:

- **Constraint violation**: submitted data violates a database-enforced rule such as unique, foreign key, `NOT NULL`, or `CHECK`.
- **Optimistic locking conflict**: the entity was modified by another transaction since the current transaction read it; the version no longer matches.
- **Zero rows updated/deleted**: the DML statement found no matching rows or modified no rows per database/driver semantics. You must know which API and SQL statement were used before concluding the cause.

Do not lump all of these into a generic 500 error, retry blindly, or grant broader permissions. Classify them by SQLState/vendor code, Spring exception, SQL statement, `WHERE` clause, version, and transaction context.

## 1. Three Distinct Failure Categories

| Category | What Happened? | Examples | Typical Handling |
|---|---|---|---|
| Constraint violation | Database rejected invalid data | Duplicate email, missing FK, `CHECK` failed | Return matching business error, fix data or write flow |
| Optimistic locking | Current version mismatches read entity version | Two requests edit the same order | Report conflict, re-read and reapply business logic if safe |
| Zero rows affected | DML affected no rows | Non-existent ID, `WHERE` filtered out, stale version | Distinguish not found, stale state, filter mismatch, or row-count semantics |

One operation can encounter multiple protection layers at once. For instance, a versioned `UPDATE` can affect 0 rows because the version became stale; another `INSERT` may be rejected by a unique constraint. The two cases require different handling.

## 2. What Is a Constraint?

A constraint is an integrity rule declared in the database. It protects data regardless of whether writes originate from Spring Data R2DBC, direct SQL, batch jobs, or another service.

Common types:

- `PRIMARY KEY`: each row has a unique identifier.
- `UNIQUE`: a value or column combination must not duplicate.
- `FOREIGN KEY`: referenced values must exist in the referenced table.
- `NOT NULL`: column must have a value.
- `CHECK`: values must satisfy a conditional expression.
- `EXCLUSION` or specialized constraints: prevent conflicting values/rows per database engine rules.

Example:

~~~sql
CREATE TABLE customer (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL,
    credit_limit DECIMAL(18, 2) NOT NULL,
    CONSTRAINT uq_customer_email UNIQUE (email),
    CONSTRAINT ck_customer_credit_limit
        CHECK (credit_limit >= 0)
);
~~~

Constraints are the final line of defense for data invariants. Pre-checks in Java are still helpful for friendly user messages, yet they cannot replace constraints because two concurrent requests can pass pre-checks before either writes.

## 3. Unique Constraints and Duplicate Keys

Suppose the system requires unique customer emails:

~~~sql
ALTER TABLE customer
ADD CONSTRAINT uq_customer_email UNIQUE (email);
~~~

Two concurrent requests can both see that the email does not exist yet:

~~~text
Request A: SELECT email -> not found
Request B: SELECT email -> not found
Request A: INSERT email -> succeeds
Request B: INSERT email -> unique violation
~~~

Therefore, a `SELECT`-then-`INSERT` pattern does not guarantee uniqueness. The database must enforce a unique constraint to handle races at the storage layer.

### Handling Duplicates Properly

- If a duplicate email is a business error, translate it into an error like `EmailAlreadyRegistered`.
- If the operation must be idempotent, check whether the existing record carries the same semantic intent as the request.
- If you intend to update on collision, use an explicit upsert matching the database dialect.
- Never automatically delete old records or overwrite someone else's data just to make a request succeed.

Not every unique violation means the same kind of duplicate. A table can have multiple unique constraints, such as email, external code, and document number. Identify which constraint failed so you map to the right business error.

## 4. Foreign Key Violations

Foreign keys ensure child rows reference existing parent rows:

~~~sql
CREATE TABLE order_line (
    id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    CONSTRAINT fk_order_line_order
        FOREIGN KEY (order_id) REFERENCES orders(id),
    CONSTRAINT fk_order_line_product
        FOREIGN KEY (product_id) REFERENCES product(id)
);
~~~

Failure scenarios:

- Inserting an `order_line` with a non-existent `order_id`.
- Inserting a line referencing a deleted product.
- Deleting an order still referenced by `order_line` when FK restricts deletion.
- Changing a parent key so child references become invalid.

Do not catch every foreign key error and return "Order not found." The violation could come from `product`, `tenant`, `category`, or another referenced table.

### Pre-Checks and Race Conditions

The application can check that an order exists before inserting `order_line` for a better user experience. However, the parent row could still be deleted between `SELECT` and `INSERT`. Foreign keys provide the final safeguard.

If business rules must guarantee the parent stays alive throughout a multi-step sequence, design appropriate transactions and locking/isolation. Do not assume a plain `SELECT` prevents another transaction from deleting the row.

## 5. `NOT NULL` and `CHECK` Violations

`NOT NULL`:

~~~sql
ALTER TABLE orders
ALTER COLUMN status SET NOT NULL;
~~~

Errors appear when an `INSERT` or `UPDATE` attempts to write `NULL` into a required column. In R2DBC, distinguish Java `null`, `bindNull`, and skipping a property during entity mapping. Ultimately, the database still enforces the constraint.

`CHECK`:

~~~sql
ALTER TABLE inventory
ADD CONSTRAINT ck_inventory_quantity
CHECK (quantity >= 0);
~~~

An error occurs if an operation makes `quantity` negative. This protects the invariant at the database even when multiple services write to the `inventory` table.

Do not rely solely on controller validation. Background jobs, imports, or direct SQL can bypass controllers.

## 6. Mapped Exceptions in Spring and R2DBC

R2DBC drivers emit errors per SPI—typically an `R2dbcException` subclass containing details like message, SQLState, and vendor error code. Spring can translate database errors into Spring's DAO exception hierarchy.

Common Spring-level exceptions:

| Exception | General Meaning |
|---|---|
| `DataIntegrityViolationException` | Data integrity constraint violated |
| `DuplicateKeyException` | Unique/duplicate key conflict recognized |
| `OptimisticLockingFailureException` | Update/delete on versioned entity no longer matches |
| `TransientDataAccessException` | Error classified as transient by the translator |
| `DataAccessException` | General data access exception hierarchy |

Not every driver or database maps a specific failure to the exact same subclass. A unique violation may translate to `DuplicateKeyException` in one setup, while appearing only as `DataIntegrityViolationException` or another exception in a different setup.

Accordingly, business logic should handle Spring abstractions verified on the target driver while retaining SQLState/vendor codes in internal logs for diagnostics.

### Reading SQLState and Vendor Error Codes

R2DBC SPI exceptions may provide:

- `getSqlState()`: SQLState if supplied by the driver.
- `getErrorCode()`: vendor-specific error code if available.
- `getMessage()`: error message from the driver/database.
- `getCause()`: underlying cause if provided.

Do not assume every driver populates all fields. Inspect the exception chain instead of reading only the outermost exception.

## 7. Common Error Codes by Database

The codes below are common examples, not an exhaustive list. Database versions, drivers, and translators can affect the resulting exception.

| Engine | Duplicate/Unique | Foreign Key | `NOT NULL` / `CHECK` |
|---|---|---|---|
| PostgreSQL | SQLState `23505` | `23503` | `23502` / `23514` |
| MySQL | Error `1062` | `1452` on child insert/update; `1451` on deleting/updating referenced parent | `1048`; `CHECK` typically has version-specific codes |
| SQL Server | `2601` or `2627` | `547` | `515` for `NULL`; `547` can apply to `CHECK`/FK |
| Oracle | `ORA-00001` | `ORA-02291` or `ORA-02292` | `ORA-01400`; `ORA-02290` |
| SQLite | Constraint error code by constraint type | Foreign key constraint failed | `NOT NULL`/`CHECK` constraint failed |

Do not hardcode vendor codes across domain services if the application supports multiple databases. Keep vendor-specific identification inside the persistence adapter/error translator layer.

## 8. Constraint Names Aid Error Classification

When multiple unique/FK constraints exist, explicit constraint names add diagnostic value:

~~~sql
CONSTRAINT uq_customer_email UNIQUE (email),
CONSTRAINT uq_customer_external_id UNIQUE (external_id),
CONSTRAINT fk_customer_tenant
    FOREIGN KEY (tenant_id) REFERENCES tenant(id)
~~~

Clear constraint names make logs and migrations much easier to interpret than auto-generated names like `uk_9k3...`.

However, not all drivers expose the constraint name via a portable API. Parsing messages/vendor metadata in a dedicated adapter may be necessary, though free-form message parsing should stay out of domain logic when better options exist.

Never return raw constraint names, SQL, internal table names, or database error messages to end clients. Map them to business errors and keep technical details in controlled logs.

## 9. What Is Optimistic Locking?

Optimistic locking assumes write conflicts are relatively rare. Instead of locking rows while a user edits data, the application stores a version and verifies that version on update.

Example:

~~~text
Database:
id = 10, quantity = 20, version = 4

Request A reads version 4
Request B reads version 4

Request A updates:
WHERE id = 10 AND version = 4
SET quantity = 18, version = 5
=> 1 row updated

Request B updates:
WHERE id = 10 AND version = 4
SET quantity = 15, version = 5
=> 0 rows matched because current version is already 5
=> optimistic locking conflict
~~~

Request B must not silently overwrite A's change. It must read the new state and decide via business rules whether to reapply its change or ask the user to resolve the conflict.

## 10. Using `@Version` in Spring Data Relational

Spring Data Relational provides `org.springframework.data.annotation.Version`:

~~~java
@Table("inventory")
public class Inventory {

    @Id
    private Long id;

    private Integer quantity;

    @Version
    private Long version;
}
~~~

When inserting a new entity, Spring Data initializes the version per the supported version type's rules. For numeric types, the initial value is usually `0`. When updating an existing entity, the version is incremented and included in the `WHERE` clause.

Conceptual SQL:

~~~sql
UPDATE inventory
SET quantity = :quantity,
    version = :newVersion
WHERE id = :id
  AND version = :oldVersion;
~~~

This shows the conceptual shape; exact SQL is generated by Spring Data and the dialect.

If no row matches ID and version, the operation on the versioned entity throws `OptimisticLockingFailureException`. This signals that the entity is no longer at the version the caller read.

### Version Must Be Managed Consistently

- The version column must exist in the schema with a compatible type.
- Do not increment the version manually in code before calling `save` when Spring Data manages it.
- Do not let another writer update the row while skipping the version convention if the application relies on optimistic locking.
- Use the entity returned after `save` because the new version may be written onto that returned instance.
- With immutable entities, use the resulting instance created/returned by Spring Data instead of keeping the stale version.

Do not confuse `@Version` with a business column like `revisionLabel`. Version exists to detect storage conflicts; business revisions follow their own rules.

## 11. Using Version in Repository Flows

A read-then-modify flow:

~~~java
public Mono<Inventory> changeQuantity(
        Long inventoryId,
        int newQuantity) {

    return inventoryRepository.findById(inventoryId)
        .switchIfEmpty(Mono.error(
            new InventoryNotFoundException(inventoryId)
        ))
        .flatMap(inventory -> {
            inventory.setQuantity(newQuantity);
            return inventoryRepository.save(inventory);
        });
}
~~~

If another request saved a new version after `findById`, the current request's `save` emits an optimistic locking exception.

When using the result after `save`:

~~~java
return inventoryRepository.save(inventory)
    .map(saved -> {
        // saved has the new version after update
        return saved;
    });
~~~

Do not assume the input object is always updated in place, especially with immutable entities or mappings using withers/copies.

## 12. Optimistic Locking on UPDATE and DELETE

For versioned entities, Spring Data can use ID and version to ensure `UPDATE`/`DELETE` affects only the entity at the version the caller holds.

Example deleting a loaded entity:

~~~java
return repository.findById(id)
    .switchIfEmpty(Mono.error(new OrderNotFoundException(id)))
    .flatMap(repository::delete);
~~~

If the entity changed before delete, the version no longer matches and the versioned delete can throw an optimistic locking failure.

Key difference:

- `delete(entity)` carries the entity and its version to verify.
- `deleteById(id)` only has the ID; it does not carry the version the caller previously read for comparison.

If business rules require version-checked deletion, use an operation accepting the entity/version or write a custom conditional `DELETE`. Do not call `deleteById` and assume optimistic concurrency control was enforced.

## 13. `@Version` Is Not a Pessimistic Lock

Optimistic locking does not hold a row lock while a user edits data. It detects conflicts at write time.

Pessimistic locking typically relies on database locks such as `SELECT ... FOR UPDATE`, though support and APIs vary by database, driver, and Spring Data R2DBC. Do not assume repository methods with JPA-like lock annotations behave identically here.

Choose optimistic locking when:

- Conflicts are relatively infrequent.
- Transactions are short.
- Callers can re-read and handle conflicts.
- Holding row locks during long processing is undesirable.

Choose another locking mechanism when business logic requires serializing operations and the database/driver supports it appropriately. Do not keep a transaction open while waiting for UI confirmation.

## 14. Handling `OptimisticLockingFailureException`

Do not map every optimistic locking failure to a generic server error. It is usually a state conflict suitable for HTTP `409 Conflict` or an equivalent business error.

Example:

~~~java
return inventoryRepository.save(inventory)
    .onErrorMap(
        OptimisticLockingFailureException.class,
        error -> new InventoryConflictException(inventory.getId())
    );
~~~

At the HTTP layer, map the conflict to an appropriate response:

~~~json
{
  "code": "INVENTORY_VERSION_CONFLICT",
  "message": "Data has changed. Please reload before saving."
}
~~~

Responses should not expose SQL, internal versions, or database exception messages.

If an API uses HTTP `ETag`/`If-Match`, the version can be represented as an entity tag. When a client sends a stale `If-Match`, the server can return `412 Precondition Failed` per API contract. Choose `409` or `412` consistently with endpoint semantics.

## 15. When Is Retrying an Optimistic Conflict Safe?

Blindly retrying with the same stale entity never resolves a conflict:

~~~text
Attempt 1: version 4 no longer matches
Retry with same version 4: still does not match
Retry again: still does not match
~~~

To retry, you must re-read the new state and recompute the change per business rules:

1. Read the current row and new version.
2. Check whether the concurrent transaction's change invalidates the current request.
3. Recompute the result from the new state.
4. Save using the newly read version.
5. Cap retry attempts and apply backoff if appropriate.

For instance, incrementing a counter may safely reapply the addition if business rules permit. However, an operation "set quantity to 5" must not blindly overwrite if someone else just adjusted the quantity for a business reason.

Do not retry every `OptimisticLockingFailureException` unconditionally. Under high contention, retries can create conflict loops and amplify database load.

## 16. Atomic Updates to Avoid Read-Modify-Write

Some operations can be expressed as a single atomic `UPDATE` instead of reading the entity, modifying in Java, and saving:

~~~sql
UPDATE inventory
SET quantity = quantity - :amount
WHERE id = :id
  AND quantity >= :amount;
~~~

The database evaluates the condition and updates within one statement. This eliminates the race window between `SELECT` and `UPDATE` for the non-negative quantity invariant.

If version is needed:

~~~sql
UPDATE inventory
SET quantity = quantity - :amount,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion
  AND quantity >= :amount;
~~~

An updated row count of 1 means the condition held and the change applied. A count of 0 could mean missing ID, mismatched version, or insufficient quantity. Row count alone does not distinguish the three causes.

To classify accurately, you can:

- Use database-supported SQL/`RETURNING` to return details.
- Perform a follow-up inspection query inside an appropriate transaction per semantics.
- Return a generic "unable to apply change" error if the API need not distinguish them.

Do not run an inspection `SELECT` and treat it as absolute truth if concurrent writers can modify state afterward.

## 17. What Does Zero Rows Updated Mean?

For DML:

~~~sql
UPDATE orders
SET status = :status
WHERE id = :id;
~~~

An updated row count of 0 can have several causes:

1. No row exists with that ID.
2. Row exists, yet another `WHERE` predicate did not match.
3. A tenant or ownership filter excluded the row.
4. Version in `WHERE` no longer matches.
5. Row was deleted by another transaction.
6. The driver/database reports row counts as "rows actually changed" when the new value equals the old value.
7. A trigger, view, or special DML construct affects the reported row count.

Hence, zero rows does not universally mean "record not found."

## 18. Distinguishing Matched Rows from Changed Rows

Some databases/drivers distinguish:

- Rows matched: rows satisfying the `WHERE` clause.
- Rows changed/affected: rows whose values actually changed.

Example:

~~~sql
UPDATE customer
SET status = 'ACTIVE'
WHERE id = 10;
~~~

If row 10 already has status `ACTIVE`, databases/drivers may report different counts depending on semantics and settings. MySQL has differences tied to `CLIENT_FOUND_ROWS`; other databases/drivers have their own row-count rules.

For versioned entity operations, Spring Data increments the version on update, so a successful update always performs an actual version change. This prevents optimistic locking from depending on whether business fields changed.

With custom SQL that does not increment a version, understand the exact `rowsUpdated` semantics on your database/driver before treating `0` as not found.

## 19. `DatabaseClient` and `rowsUpdated`

A custom update via `DatabaseClient` can read the reported row count:

~~~java
Mono<Integer> rowsUpdated = databaseClient.sql(
        "UPDATE orders " +
        "SET status = :status " +
        "WHERE id = :id AND tenant_id = :tenantId"
    )
    .bind("status", status)
    .bind("id", id)
    .bind("tenantId", tenantId)
    .fetch()
    .rowsUpdated();
~~~

Spring's `DatabaseClient` API may represent the row count with an integer/long numeric type depending on the framework version. At the R2DBC SPI layer, `Result.getRowsUpdated()` emits a `Publisher` of row counts per SPI contract. Verify the exact return type against your project's API.

Checking the row count:

~~~java
return rowsUpdated.flatMap(count -> {
    if (count == 1) {
        return Mono.empty();
    }
    if (count == 0) {
        return Mono.error(new OrderNotUpdatedException(id));
    }
    return Mono.error(new UnexpectedUpdateCountException(count));
});
~~~

This policy fits when the operation contract requires exactly one row and the database/driver reports matching row counts accordingly. If a no-op update can return 0 on the target database, adjust the SQL or classify separately.

If an update can legitimately affect multiple rows, do not assert `count == 1`. Define bounds and semantics appropriate for the business rule.

## 20. Zero Rows in Versioned UPDATEs

For versioned entities, Spring Data includes version in the update condition. If the version mismatches or the row does not exist, zero rows are updated and Spring Data reports an optimistic locking failure.

Conceptually:

~~~sql
UPDATE orders
SET status = :newStatus,
    version = :nextVersion
WHERE id = :id
  AND version = :expectedVersion;
~~~

A result of 0 here means the update could not be applied to the version held by the entity. The cause may be a stale version or a deleted row; distinguishing them requires extra information.

Do not catch `OptimisticLockingFailureException` and convert it into success just because the client does not need details. If the update was required, the caller must receive an appropriate conflict/not-found outcome.

## 21. Zero Rows in Unversioned UPDATEs

If an entity lacks `@Version` or custom SQL does not check version:

~~~sql
UPDATE orders
SET status = :status
WHERE id = :id;
~~~

If the count is 0:

- The ID may not exist.
- The row may have been deleted.
- The `WHERE` clause may have additional unmatched filters.
- No values actually changed per driver semantics.

Spring Data cannot infer business meaning from custom SQL unless the application supplies extra conditions.

If distinguishing not-found from no-op is required, read state first or use database-supported SQL returning rows. Consider transaction/isolation because state can still change between two statements.

## 22. Zero Rows in DELETE

Example:

~~~sql
DELETE FROM orders
WHERE id = :id
  AND tenant_id = :tenantId;
~~~

A count of 0 can mean:

- ID does not exist.
- Row belongs to another tenant.
- Row was already deleted.
- Extra predicates did not match.

For security-sensitive APIs, you may intentionally return the same not-found response for missing IDs and cross-tenant IDs to avoid leaking existence of out-of-scope records.

When using versioned `delete(entity)`, version can participate in the predicate so stale versions are detected. `deleteById(id)` does not carry a previously read version and cannot provide the same optimistic delete semantics.

## 23. Constraint Violations Inside Reactive Transactions

When an `INSERT`/`UPDATE` violates a constraint inside a transaction, the database may mark the transaction in an error state. If the error propagates out of the reactive chain, the transaction manager can roll back the transaction per rules.

Example:

~~~java
return transactionalOperator.transactional(
    orderRepository.save(order)
        .flatMap(saved -> orderLineRepository.saveAll(lines).then())
);
~~~

If an operation in the chain emits an error, it crosses the transaction boundary and triggers rollback.

### Do Not Swallow Constraint Errors Inside the Same Transaction

Avoid:

~~~java
return transactionalOperator.transactional(
    repository.save(entity)
        .onErrorResume(DataIntegrityViolationException.class,
            error -> Mono.empty())
        .then(repository.save(otherEntity))
);
~~~

In some databases—especially PostgreSQL—a failed statement leaves the transaction in an aborted state until rollback. Swallowing the exception in the reactive chain does not recover the database transaction. Subsequent statements will fail because the transaction remains aborted.

If an error is an ignorable business case, design a separate transaction boundary or use savepoints where supported by the database/driver with clear semantics. Do not merely turn the error into `Mono.empty()`.

## 24. Distinguishing Retryable Errors from Non-Retryable Errors

| Error Type | Retry Same Request Immediately? | Approach |
|---|---|---|
| Unique violation from duplicate business key | Usually no | Identify duplicate, idempotency, or upsert |
| Foreign key violation | Usually no | Check referenced data and write order |
| `NOT NULL`/`CHECK` violation | No | Fix input or logic |
| Optimistic locking conflict | Do not retry stale entity | Re-read and reapply business logic with bounds |
| Deadlock | Can retry entire transaction | Retry with backoff and limit |
| Serialization failure | Can retry entire transaction | Re-run entire transaction logic |
| Connection reset/timeout | Depends on timing and idempotency | Determine commit outcome before retrying |
| Zero rows | Do not auto-retry | Classify not found, stale state, or predicate mismatch |

Retries are safe only when you know whether the prior attempt committed and the operation is idempotent. On network errors after sending `COMMIT`, the client may not know whether the database committed.

## 25. Idempotency When Clients Resend Requests

If a client times out and resends an order creation command, a unique constraint on an idempotency key prevents duplicate orders:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT uq_orders_idempotency_key
UNIQUE (idempotency_key);
~~~

The first request creates the order. A repeated request with the same idempotency key:

- If the payload matches, returns the already-saved result.
- If the payload differs, returns a conflict error.
- Does not create a second order merely because the client missed the first response.

Idempotency keys should be scoped to actor/tenant with a business-defined retention/lifecycle. Do not use a global key that can collide across different customers when uniqueness should be per-tenant.

## 26. Upsert Does Not Replace Conflict Handling Blindly

Upsert is useful when business semantics truly mean "create if absent, update per rules if present." It is not a blanket way to ignore duplicates.

Before using upsert:

- Identify the conflict target.
- Ensure the matching unique constraint exists.
- Specify which columns are updated.
- Determine whether overwriting existing data is allowed.
- Handle generated IDs and versions.
- Test concurrency against the real database.

If an entity uses optimistic locking, a custom upsert can bypass version checks if version is omitted from SQL. That breaks the concurrency invariant relied upon by other repository methods.

## 27. Separating Exception Translation from Domain Logic

A clean layering structure:

~~~text
R2DBC driver exception
        |
        v
Spring DataAccessException / OptimisticLockingFailureException
        |
        v
Persistence adapter
        |
        v
Domain exception
        |
        v
Application/API error mapping
~~~

The persistence adapter knows about the database, constraint names, or vendor codes. The domain layer receives meaningful domain errors such as:

- `CustomerEmailAlreadyExists`.
- `ReferencedProductNotFound`.
- `InventoryConflict`.
- `OrderNotFound`.
- `OrderStateChanged`.

Do not leak SQLState or PostgreSQL error codes into the domain model if the application must support multiple databases. Technical codes can remain in logs/telemetry.

### Exception Mapping Example

~~~java
public Mono<Customer> register(Customer customer) {
    return customerRepository.save(customer)
        .onErrorMap(
            DuplicateKeyException.class,
            error -> new CustomerEmailAlreadyExists()
        );
}
~~~

This example is valid only when the persistence adapter knows `DuplicateKeyException` corresponds to the email constraint in that table. If a table has multiple unique keys, classify more accurately instead of mapping every duplicate to an email error.

## 28. Diagnosing a Failure in Production

When a write error is reported:

1. Identify whether the operation is `INSERT`, `UPDATE`, `DELETE`, or repository `save`.
2. Check whether the entity uses `@Version`.
3. Record ID, tenant scope, and expected version if permitted.
4. Record the SQL fingerprint or sanitized SQL.
5. Record bind parameter types without logging raw secrets or sensitive data.
6. Capture the exception chain, SQLState, and vendor error code.
7. Identify the constraint name if provided by the database/driver.
8. Check `rowsUpdated` or row count for custom DML.
9. Check whether a transaction was active and whether it was marked rollback-only/aborted.
10. Verify migration/schema versions match expectations.
11. Cross-check request logs for concurrent operations that may have modified or deleted the row.
12. Reproduce in a test environment using the exact database version and R2DBC driver.

Never log full SQL with sensitive bind values in production logs. Use correlation IDs, query fingerprints, and redacted metadata.

## 29. Analyzing Optimistic Conflicts Across Two Transactions

An integration test can simulate two readers:

~~~text
T1: SELECT inventory -> version 7
T2: SELECT inventory -> version 7
T1: UPDATE WHERE id=? AND version=7 -> version 8
T1: COMMIT
T2: UPDATE WHERE id=? AND version=7 -> 0 rows
T2: OptimisticLockingFailureException
~~~

The test must use two independent transactions/connections to genuinely simulate concurrency. Calling `save` twice sequentially on the same entity in one transaction does not verify concurrent-writer optimistic locking.

After a conflict:

- T2 must not silently overwrite T1.
- T2 can re-read version 8.
- Business logic decides whether T2's change can apply to the new state.
- If reconciliation is impossible, return a conflict to the caller.

## 30. Testing Constraint Violations

Integration tests should verify:

- Inserting duplicate unique keys.
- Inserting rows with non-existent FKs.
- Deleting referenced parent rows.
- Writing `NULL` to `NOT NULL` columns.
- Writing values violating `CHECK`.
- Confirming exception class/SQLState returned by the target driver.
- Confirming transaction rollback when the error crosses the boundary.
- Confirming mapping to the expected domain/API response.

Do not merely mock `DuplicateKeyException`. Mocks do not prove database constraints exist or that the driver translates errors as expected.

## 31. Testing Zero `rowsUpdated`

Create dedicated test cases for:

1. `UPDATE` on a non-existent ID.
2. `UPDATE` on an existing ID with a mismatched tenant.
3. `UPDATE` with a stale version.
4. `UPDATE` setting the exact same values.
5. `DELETE` on a non-existent ID.
6. `DELETE` with a stale version.
7. `UPDATE` involving triggers or views if used by the application.

Record exact row counts and exceptions for your target database/driver. Pay special attention to matched-versus-changed rows semantics if APIs rely on row counts to return not found.

## 32. Version in Immutable Entities

With immutable entities or Java records, do not assume Spring Data mutates version on the input object:

~~~java
@Table("inventory")
public record Inventory(
    @Id Long id,
    Integer quantity,
    @Version Long version
) {
}
~~~

When saving:

~~~java
return inventoryRepository.save(inventory)
    .flatMap(saved -> {
        // Use saved.version() for the next operation
        return continueWith(saved);
    });
~~~

Always use the returned entity to obtain ID/version updated by the persistence layer. New-instance creation depends on mapping and entity models; verify behavior with your Spring Data version.

## 33. Version and Updates Outside Spring Data

If another service updates a table without incrementing version, Spring Data may miss that change:

~~~sql
UPDATE inventory
SET quantity = 100
WHERE id = 10;
~~~

If this SQL leaves version unchanged, an entity holding the old version still matches Spring Data's version predicate and can overwrite the external change.

All writers must obey the same version convention:

~~~sql
UPDATE inventory
SET quantity = :quantity,
    version = version + 1
WHERE id = :id;
~~~

If you cannot control every writer, consider version-managing triggers, stored procedures, or a unified concurrency mechanism. Avoid having both the application and a trigger increment version twice.

## 34. Constraints and Multi-Step Transactions

Suppose creating an order and its `order_line` rows:

~~~java
return transactionalOperator.transactional(
    orderRepository.save(order)
        .flatMap(savedOrder ->
            saveLines(savedOrder.getId(), lines)
                .thenReturn(savedOrder)
        )
);
~~~

If an `order_line` violates FK or `CHECK` and the error propagates out of the transaction boundary, both the order and any lines written in that transaction roll back.

If code catches the error and continues the transaction, know whether the database permits continuing after a statement failure. PostgreSQL normally marks the transaction aborted after a constraint error until rolled back or rolled back to an appropriate savepoint.

Do not generate an "order created" response before the transaction commits. In reactive chains, emit final responses only after the transaction operator completes.

## 35. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| `SELECT` before `INSERT` to avoid duplicates | Race conditions still happen | Enforce unique constraints and handle duplicates |
| Catching all `DataIntegrityViolationException` as duplicate email | Wrong error returned for FK/`CHECK`/`NOT NULL` violations | Classify specific constraints in adapter |
| Skipping database constraints because app validates | Other writers can corrupt invariants | Keep constraints in the database |
| Omitting `@Version` while expecting lost-update detection | Later request overwrites earlier request | Use version or atomic conditional updates |
| Retrying stale entity after optimistic conflict | Version stays stale, conflict repeats | Re-read and recompute business logic |
| Ignoring exceptions from `repository.save` | Caller assumes data was saved | Propagate errors or map to domain errors |
| Confusing zero rows with not found | Misses stale version or filter mismatch | Check `WHERE`, version, and row-count semantics |
| Assuming `rowsUpdated` always means changed rows | No-op updates get misclassified | Test specific driver/database behavior |
| Using `deleteById` when version check is required | No expected version to compare | Delete loaded entity or use conditional `DELETE` |
| Swallowing constraint errors mid-transaction | Transaction may stay aborted | Let error propagate or use savepoints properly |
| Custom upsert ignoring version | Overwrites concurrent changes | Design explicit conflict/version semantics |
| One writer skipping version increments | Partially defeats optimistic locking | Standardize every write path |
| Retrying network errors without knowing commit outcome | Duplicate records or repeated side effects | Use idempotency keys and check commit outcomes |
| Logging raw SQL and bind values | Leaks sensitive data | Log fingerprints and masked parameters |

## 36. Procedure for Handling Write Failures

When a write operation fails, follow this order:

1. Inspect the exception chain and classify the failure at the Spring/R2DBC layer.
2. If an integrity violation, identify the constraint and related business values.
3. If an optimistic locking failure, check expected/current version and decide between reconciliation or conflict response.
4. If row count is 0, inspect `WHERE` predicates, tenant scope, version, and driver row-count semantics.
5. Check transaction rollback and prior operations in the same chain.
6. Retry only when the error is transient or business rules allow re-reading/reapplying.
7. Map to a stable domain/API error.
8. Record sufficient telemetry for investigation without exposing sensitive data.

## 37. Takeaways

- Constraint violations occur when the database rejects data violating `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `NOT NULL`, `CHECK`, or similar rules.
- Java pre-checks do not replace database constraints because race conditions remain.
- Spring can translate R2DBC errors into `DataIntegrityViolationException`, `DuplicateKeyException`, or other exceptions; exact mapping depends on driver/database.
- SQLState and vendor error codes help classify failures, though vendor codes should not leak into domain models.
- `@Version` enables Spring Data Relational to detect updates/deletes on entities modified since being read.
- Use the entity returned by `save` to receive the updated version, especially for immutable entities.
- Retrying optimistic conflicts requires re-reading and recomputing business state; never retry the same stale entity/version.
- `delete(entity)` can check version; `deleteById` carries no expected version from the read entity.
- Zero rows can mean missing ID, unmatched predicate, tenant scope, stale version, or matched-vs-changed row semantics.
- Do not treat `rowsUpdated = 0` as universally meaning not found; verify database and driver semantics.
- Atomic conditional `UPDATE` statements protect invariants without application-level read-modify-write races.
- Constraint errors inside transactions must follow the database's rollback semantics; never swallow errors and keep executing blindly.
- Custom upserts must honor unique constraints and optimistic versions if business logic relies on versioning.
- Use idempotency keys when clients may retry after timeouts with uncertain commit outcomes.
- Integration tests must run against the real database/R2DBC driver and simulate two independent transactions to verify concurrency.
