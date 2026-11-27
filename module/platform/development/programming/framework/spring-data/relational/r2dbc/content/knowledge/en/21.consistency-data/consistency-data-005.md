# Concurrency Control Using Conditional Updates and Affected Row Counts

## 1. The Concurrent Update Problem

In an application where multiple requests, workers, or instances access a database concurrently, two operations can read the same state and attempt to update it. If the application simply reads data into Java, computes a new value, and writes it back without a protection mechanism, one update can overwrite another or violate business rules.

For example, suppose an inventory has 5 items left. Two requests both read the quantity as 5:

1. Request A wants to reserve 4 items.
2. Request B wants to reserve 3 items.
3. Both read quantity 5.
4. A computes 1 remaining and writes `available = 1`.
5. B computes 2 remaining and writes `available = 2`.

The final result may be 2, even though 7 items were reserved in total. One request overwrote the other's result, and inventory data no longer reflects reality.

Spring Data R2DBC lets you perform direct updates using conditional SQL. The condition is placed right inside the `UPDATE` statement so the database checks the state and modifies the row within the same statement. The affected row count then tells the application whether the condition matched, according to database/driver semantics.

## 2. The Idea: Checking the Condition Directly in UPDATE

Instead of executing two separate steps:

```text
SELECT available
Application checks available >= quantity
UPDATE inventory SET available = calculated_value
```

put the condition directly into the update statement:

```sql
UPDATE inventory
SET available = available - :quantity
WHERE product_id = :productId
  AND available >= :quantity;
```

The database checks the condition and updates the row in a single statement. For an inventory row uniquely identified by `product_id`, competing requests are coordinated by the database according to its locking and isolation mechanisms. A request updates only when `available >= quantity` still holds true at the moment the statement performs the update.

This is a form of **conditional update** or **compare-and-set (CAS)**: modify the data only if the current state still satisfies the caller's required condition.

Conditions in `WHERE` can check:

- Sufficient remaining quantity or balance.
- Current status still matching the expected status.
- Version not modified by another request.
- Record not soft-deleted.
- Owner or tenant matching the request context.
- Expiration time or business condition still valid.

## 3. The Affected Row Count Model

An UPDATE or DELETE statement can affect 0, 1, or multiple rows. The affected row count helps the application interpret the result:

| Common outcome | Interpretation |
| ---: | --- |
| `0` | No rows reported as affected; possibly because the row does not exist or the condition no longer holds |
| `1` | One row reported as affected; matches operations expecting a single record |
| Greater than `1` | Multiple rows affected; valid for bulk updates, but potentially a bug if business logic expects a single row |

For example, when updating an account by primary key, the expected count is usually 1. When updating the status of all expired tasks, the count may be greater than 1.

Do not over-interpret `0`. It could mean:

- The ID does not exist.
- Balance/inventory is no longer sufficient.
- Current status differs from the expected status.
- Version changed due to another request's update.
- Record was soft-deleted.
- Ownership or tenant condition did not match.

If the statement only returns the row count, these reasons usually cannot be distinguished directly. You can design an additional diagnostic query, return a SQL result containing a reason code, or use an appropriate business workflow.

## 4. Retrieving Affected Row Counts with DatabaseClient

Spring's `DatabaseClient` supports executing SQL statements and reading the number of updated rows:

```java
public Mono<Integer> reserve(
        DatabaseClient databaseClient,
        Long productId,
        int quantity) {

    return databaseClient.sql("""
            UPDATE inventory
            SET available = available - :quantity
            WHERE product_id = :productId
              AND :quantity > 0
              AND available >= :quantity
            """)
            .bind("productId", productId)
            .bind("quantity", quantity)
            .fetch()
            .rowsUpdated();
}
```

`rowsUpdated()` returns a publisher emitting the number of affected rows according to the Spring Framework API and driver in use. In common Spring R2DBC versions, the return type is `Mono<Integer>`; verify the signature for your project's version when upgrading the framework.

Key points to note:

- `available = available - :quantity` computes from the row's current value in the database.
- `available >= :quantity` prevents negative quantities caused by competing requests.
- `:quantity > 0` adds an input guard directly in SQL.
- Values are bound as parameters, never string-concatenated from request data.
- If the condition does not match, the affected row count is typically 0.

Validating `quantity > 0` at the domain/service layer is still necessary to return clear input errors. The SQL condition is an extra safeguard when multiple write paths or untrusted callers exist.

## 5. Using @Modifying in Repositories

For fixed, straightforward SQL statements, you can declare modifying queries in a repository:

```java
public interface InventoryRepository
        extends ReactiveCrudRepository<Inventory, Long> {

    @Modifying
    @Query("""
        UPDATE inventory
        SET available = available - :quantity
        WHERE product_id = :productId
          AND :quantity > 0
          AND available >= :quantity
        """)
    Mono<Integer> reserveIfAvailable(
            @Param("productId") Long productId,
            @Param("quantity") Integer quantity);
}
```

Using it in an application service:

```java
public Mono<Void> reserveInventory(Long productId, int quantity) {
    if (quantity <= 0) {
        return Mono.error(new IllegalArgumentException(
                "Quantity must be positive"));
    }

    return inventoryRepository.reserveIfAvailable(productId, quantity)
            .flatMap(rows -> {
                if (rows == 1) {
                    return Mono.empty();
                }
                if (rows == 0) {
                    return Mono.error(
                            new InsufficientInventoryException(productId));
                }
                return Mono.error(new IllegalStateException(
                        "Expected one inventory row, got " + rows));
            });
}
```

This example assumes `product_id` is unique so at most one row is updated. If the schema allows multiple rows with the same `product_id`, update the key or query conditions to accurately reflect the model.

`@Modifying` marks `@Query` as a data-modifying statement. For reactive modifying queries, numeric return types such as `Mono<Integer>` provide the affected row count; if only a completion signal is needed, you can use a reactive void-style return type supported by your Spring Data R2DBC version.

## 6. Avoiding the SELECT-then-UPDATE Pattern

A common pattern that is unsafe under contention:

```java
return inventoryRepository.findByProductId(productId)
        .flatMap(inventory -> {
            if (inventory.getAvailable() < quantity) {
                return Mono.error(new InsufficientInventoryException(productId));
            }

            inventory.setAvailable(inventory.getAvailable() - quantity);
            return inventoryRepository.save(inventory);
        });
```

The issue is that the condition is checked in Java against a previously read snapshot. Before `save` executes, another request may have already modified the quantity. Both requests can pass the check simultaneously.

A transaction at the default isolation level does not automatically make a read-then-write sequence safe against all concurrent updates. Actual behavior depends on isolation level, locking, versioning, and query structure.

If the rule can be expressed as a SQL condition, use a conditional UPDATE statement. If you must load an aggregate and apply complex logic, consider optimistic locking with `@Version` or an appropriate locking mechanism.

## 7. Example: Safely Reserving Inventory

Suppose the schema is:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    version BIGINT NOT NULL DEFAULT 0
);
```

Reservation statement:

```sql
UPDATE inventory
SET available = available - :quantity,
    reserved = reserved + :quantity,
    version = version + 1
WHERE product_id = :productId
  AND :quantity > 0
  AND available >= :quantity;
```

The `available >= :quantity` condition sits inside the same statement as the subtraction. The database does not receive an old Java-computed `available` value to overwrite with; it computes directly against the row's value at update time.

Suppose initially `available = 5` and two concurrent requests arrive:

| Request | Quantity to reserve |
| --- | ---: |
| A | 4 |
| B | 3 |

One request updates first and reduces `available` to 1. When the other request is processed by the database, `available >= 3` is no longer true, so it does not update the row. As a result, only one request succeeds and the remaining quantity stays non-negative.

Exact behavior depends on the database's concurrency control and isolation, but the conditional statement eliminates the gap between checking and writing in the application. The `CHECK (available >= 0)` constraint adds an extra layer of schema protection.

## 8. Example: Deducting an Account Balance

An account must never have a negative balance. Schema:

```sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    balance NUMERIC(19, 2) NOT NULL CHECK (balance >= 0),
    version BIGINT NOT NULL DEFAULT 0
);
```

Repository:

```java
public interface AccountRepository
        extends ReactiveCrudRepository<Account, Long> {

    @Modifying
    @Query("""
        UPDATE account
        SET balance = balance - :amount,
            version = version + 1
        WHERE id = :accountId
          AND :amount > 0
          AND balance >= :amount
        """)
    Mono<Integer> debitIfSufficient(
            @Param("accountId") Long accountId,
            @Param("amount") BigDecimal amount);
}
```

Service:

```java
public Mono<Void> debit(Long accountId, BigDecimal amount) {
    if (amount == null || amount.signum() <= 0) {
        return Mono.error(new IllegalArgumentException(
                "Amount must be positive"));
    }

    return accountRepository.debitIfSufficient(accountId, amount)
            .flatMap(rows -> {
                if (rows == 1) {
                    return Mono.empty();
                }
                if (rows == 0) {
                    return Mono.error(
                            new InsufficientBalanceException(accountId));
                }
                return Mono.error(new IllegalStateException(
                        "Unexpected number of accounts updated: " + rows));
            });
}
```

For money, use `BigDecimal` and `NUMERIC/DECIMAL` columns; never use `double`. The column precision/scale must be sufficient for business values.

The `balance >= :amount` condition ensures the balance is never overdrawn within the same statement. The `CHECK` constraint enforces the invariant in the database even if another write path bypasses the service.

## 9. Example: Money Transfer Requiring Multiple Statements in One Transaction

A money transfer involves at least two changes:

1. Debit the source account.
2. Credit the destination account.

Both changes must commit together or roll back together. If debiting succeeds but crediting fails, money must not be lost.

```java
@Service
public class TransferService {

    private final AccountRepository accountRepository;

    public TransferService(AccountRepository accountRepository) {
        this.accountRepository = accountRepository;
    }

    @Transactional
    public Mono<Void> transfer(
            Long fromId,
            Long toId,
            BigDecimal amount) {

        if (fromId.equals(toId)) {
            return Mono.error(new IllegalArgumentException(
                    "Source and destination must differ"));
        }
        if (amount == null || amount.signum() <= 0) {
            return Mono.error(new IllegalArgumentException(
                    "Amount must be positive"));
        }

        return accountRepository.debitIfSufficient(fromId, amount)
                .flatMap(debited -> {
                    if (debited != 1) {
                        return Mono.error(
                                new InsufficientBalanceException(fromId));
                    }

                    return accountRepository.credit(toId, amount)
                            .flatMap(credited -> credited == 1
                                    ? Mono.<Void>empty()
                                    : Mono.error(new AccountNotFoundException(toId)));
                });
    }
}
```

`credit` can be declared as a modifying query:

```java
@Modifying
@Query("UPDATE account SET balance = balance + :amount, version = version + 1 WHERE id = :accountId")
Mono<Integer> credit(
        @Param("accountId") Long accountId,
        @Param("amount") BigDecimal amount);
```

If the source account has insufficient funds, the service emits an error before crediting. If the destination account does not exist, the service emits an error after debiting the source; the reactive transaction rolls back the source change provided the error crosses the transaction boundary and both operations share the same `ConnectionFactory` and transaction manager.

This snippet illustrates a local transaction within a single database. If the source and destination accounts reside in two different databases, a single `R2dbcTransactionManager` cannot guarantee atomicity across both. In that case, use a distributed workflow such as a saga or an explicitly supported multi-resource transaction solution.

## 10. State Transitions via Compare-and-Set

A common use case only permits a state transition when the record is currently in the expected state. For example, an order can only be confirmed when it is `PENDING`:

```sql
UPDATE purchase_order
SET status = 'CONFIRMED',
    confirmed_at = CURRENT_TIMESTAMP
WHERE id = :orderId
  AND status = 'PENDING';
```

If two requests try to confirm the same order simultaneously, the first transitions the row from `PENDING` to `CONFIRMED`. The subsequent request no longer matches `status = 'PENDING'`, so its affected row count is 0.

Repository:

```java
@Modifying
@Query("""
    UPDATE purchase_order
    SET status = 'CONFIRMED',
        confirmed_at = CURRENT_TIMESTAMP
    WHERE id = :orderId
      AND status = 'PENDING'
    """)
Mono<Integer> confirmIfPending(@Param("orderId") Long orderId);
```

The service can interpret `1` as a successful transition and `0` as either an ineligible status or a missing order. If you need to distinguish "not found" from "already confirmed," you can read the status after receiving 0 or use a statement with `RETURNING` to return data if supported by the database.

This pattern is also useful for:

- Claiming a job only if it is `READY`.
- Issuing an invoice only if it has not yet been issued.
- Marking a token as used only if it is unused.
- Processing a message only if it is unprocessed.
- Cancelling a booking only if its status is still `PENDING`.

## 11. Combining Version Checks in the Update Condition

Optimistic locking is one way to control concurrent updates. Spring Data Relational supports `@Version` when saving entities via repositories. With custom SQL or bulk updates, the application must include the version in the statement itself.

Example table:

```sql
CREATE TABLE document (
    id BIGINT PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);
```

A request reads a document with `version = 7`. When saving changes, the compare-and-set statement is:

```sql
UPDATE document
SET title = :title,
    version = version + 1
WHERE id = :id
  AND version = :expectedVersion;
```

If another request already updated the version to 8, the statement with `expectedVersion = 7` matches nothing and updates zero rows.

Repository:

```java
@Modifying
@Query("""
    UPDATE document
    SET title = :title,
        version = version + 1
    WHERE id = :id
      AND version = :expectedVersion
    """)
Mono<Integer> updateTitleIfVersionMatches(
        @Param("id") Long id,
        @Param("title") String title,
        @Param("expectedVersion") Long expectedVersion);
```

Interpretation:

- `1`: ID exists and version matched; update succeeded.
- `0`: ID does not exist or version changed.
- Greater than `1`: an issue exists with the unique-ID assumption or schema/query.

When using `@Version` with `repository.save(entity)`, Spring Data can build the version condition automatically. When using `@Modifying`, do not assume entity optimistic locking runs automatically; include both the version condition and the version increment in SQL.

## 12. Distinguishing Rows Matched vs. Rows Changed

The term "affected rows" is not identical across all databases. Some systems report rows matching the condition; some drivers/configurations may report rows whose values actually changed. For example, MySQL can return changed rows or found rows depending on client configuration; PostgreSQL's UPDATE command tag reports the number of rows processed, even if the assigned value equals the existing value.

Therefore, for the statement:

```sql
UPDATE customer
SET status = 'ACTIVE'
WHERE id = :id;
```

if the customer already has `status = 'ACTIVE'`, the affected rows result can depend on database/driver semantics. Do not use `rows == 0` to conclude with certainty "ID does not exist" if a statement might match without changing any value.

To make results unambiguous, you can:

- Design the statement to match only when an actual state transition is needed, e.g., adding `AND status <> 'ACTIVE'`.
- Use `RETURNING` if supported by the database and you need to know which rows were updated.
- Test semantics with the exact database and driver versions.
- Name the result according to its actual meaning, such as `rowsAffected`, rather than calling it `entitiesChanged` without verifying.

## 13. When Row Count Is 0: Business Outcome Handling

A count of 0 is not necessarily a database error. It usually indicates that the update condition no longer holds or no row matched.

Balance check example:

```java
return accountRepository.debitIfSufficient(accountId, amount)
        .flatMap(rows -> {
            if (rows == 1) {
                return Mono.just(DebitResult.success());
            }
            if (rows == 0) {
                return accountRepository.findById(accountId)
                        .map(account -> DebitResult.insufficientFunds())
                        .defaultIfEmpty(DebitResult.accountNotFound());
            }
            return Mono.error(new IllegalStateException(
                    "Unexpected rows affected: " + rows));
        });
```

This example performs a read query after UPDATE returns 0 to distinguish between a missing account and an account with insufficient balance. This is post-operation diagnostic information; state can still be modified by another request immediately after that read. If business logic requires an exact reason code as of the same instant, design a database statement returning categorized results or use an appropriate locking/transaction mechanism.

Do not throw system errors for every case where rows equals 0. It may be a normal business outcome such as "job already claimed by another worker" or "order already processed."

## 14. Conditional Updates Do Not Replace Database Constraints

A conditional UPDATE protects a specific operation. Database constraints protect data against every write path.

Example:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);
```

`CHECK (available >= 0)` prevents negative data regardless of whether the statement comes from a repository, a SQL console, or another service. An UPDATE with `available >= :quantity` protects the reservation use case and uses the affected row count to report whether the operation succeeded.

Common constraints:

- `PRIMARY KEY` guarantees unique and non-null identity.
- `UNIQUE` prevents duplicate values under uniqueness rules.
- `NOT NULL` disallows SQL NULL values.
- `CHECK` enforces that a per-row expression always holds true.
- `FOREIGN KEY` enforces cross-table references per the schema.

Do not rely solely on Java validation to enforce critical invariants like non-negative balances or unique emails. Multiple requests and multiple applications can write concurrently; database constraints are the final line of defense.

## 15. Tenant and Ownership Conditions

Conditional UPDATEs also let you include tenant or owner conditions in the statement, reducing the risk of accidentally modifying the wrong data:

```sql
UPDATE purchase_order
SET status = 'CANCELLED'
WHERE id = :orderId
  AND customer_id = :authenticatedCustomerId
  AND status = 'PENDING';
```

Here, the statement modifies the order only if the ID, owning customer, and status all match. `authenticatedCustomerId` must come from a verified authentication context, not directly from an arbitrary request field.

If rows affected is 0, the order may not exist, may not belong to the customer, or may have already changed status. Many APIs intentionally avoid distinguishing "not found" from "unauthorized" to avoid leaking resource existence.

SQL conditions do not replace full authorization. Complex rules must still be checked at the application/domain layer, and read queries must likewise enforce appropriate tenant scoping.

## 16. Bulk Updates and Affected Row Counts

A single UPDATE statement can affect multiple rows:

```sql
UPDATE task
SET status = 'EXPIRED'
WHERE status = 'PENDING'
  AND expires_at < :now;
```

`rowsUpdated` may return `0`, `1`, or a larger number. For bulk operations, the row count is useful for logging, metrics, or confirming impact scope.

Repository example:

```java
@Modifying
@Query("""
    UPDATE task
    SET status = 'EXPIRED'
    WHERE status = 'PENDING'
      AND expires_at < :now
    """)
Mono<Integer> expirePendingTasks(@Param("now") OffsetDateTime now);
```

Service:

```java
public Mono<Integer> expireTasks(OffsetDateTime now) {
    return taskRepository.expirePendingTasks(now)
            .doOnNext(rows -> log.info("Expired {} tasks", rows));
}
```

Bulk updates do not load each entity into Java, so domain methods, entity callbacks, auditing, or automatic per-entity optimistic locking do not necessarily run. If those behaviors are needed, put them into SQL or choose a load-mutate-save workflow.

## 17. Transactions When a Use Case Has Multiple Conditional Updates

A single conditional UPDATE statement is typically executed atomically at the statement level by the database. If a use case comprises multiple statements that must succeed together, a reactive transaction is needed.

Transfer example:

```java
@Transactional
public Mono<Void> transfer(Long sourceId, Long targetId, BigDecimal amount) {
    return accountRepository.debitIfSufficient(sourceId, amount)
            .flatMap(debited -> {
                if (debited != 1) {
                    return Mono.error(new InsufficientBalanceException(sourceId));
                }

                return accountRepository.credit(targetId, amount)
                        .flatMap(credited -> credited == 1
                                ? Mono.<Void>empty()
                                : Mono.error(new AccountNotFoundException(targetId)));
            });
}
```

If crediting fails and the error crosses the transaction boundary, the debit can be rolled back. Both repositories must use the same `ConnectionFactory` and reactive transaction manager.

Do not call `subscribe()` inside a transactional method. Return the publisher and chain operations with `flatMap`, `then`, or appropriate operators so Spring can track the commit/rollback lifecycle.

A transaction does not turn two independent databases into a single atomic resource. If source and destination live in two separate systems, use a saga or compensating workflow.

## 18. Isolation Levels and Concurrent UPDATEs

Conditional UPDATEs work alongside the database's concurrency control mechanism. When multiple transactions update the same row simultaneously, the database engine may use row locks, MVCC, or an equivalent mechanism to coordinate.

Some key considerations:

- Under `READ COMMITTED`, a statement generally evaluates conditions against the state visible to the database at the time the statement runs; exact contention handling depends on the database system.
- Under `REPEATABLE READ` or `SERIALIZABLE`, some conflicts can cause a transaction to be aborted or require retry instead of simply returning 0 rows.
- Do not rely on one generic isolation level across all databases without testing actual semantics.
- When the database reports a deadlock or serialization failure, the application may need to retry the entire transaction with a cap and backoff.

Update conditions and constraints clarify rules in the database. The isolation level further defines how competing transactions are observed and resolved.

## 19. Retries and Idempotency

When encountering transient errors such as serialization failures or deadlocks, retries can help a use case complete. However, do not blindly retry every error or every conditional update.

For example:

- A conditional UPDATE transitions `PENDING` to `CONFIRMED`. If the first request committed but the response was lost, a retry may return 0 because the status is no longer `PENDING`. The application needs a way to determine whether the prior request succeeded.
- A balance-deduction UPDATE lacks an idempotency key. If a client retries after a timeout without knowing whether the transaction committed, it risks deducting the money a second time.
- A job claimed with `status = 'READY'` might be claimed first by another worker; 0 rows is a normal result, not an error to retry continuously.

For financial operations or retryable commands, use an idempotency key or a unique request tracking table. One transaction can store the processing result by key alongside the business mutation so repeated calls return the recorded outcome.

Retries must:

- Apply only to errors identified as retryable.
- Have a maximum attempt count and backoff.
- Re-run the entire transaction if the error rolled back the current transaction.
- Ensure the use case is idempotent or guarded against duplicate execution.
- Never retry business errors such as insufficient balance or ineligible status.

## 20. When RETURNING Is Needed Instead of Just Counting Rows

Some database systems such as PostgreSQL support `UPDATE ... RETURNING` to return row data after updating:

```sql
UPDATE inventory
SET available = available - :quantity,
    version = version + 1
WHERE product_id = :productId
  AND available >= :quantity
RETURNING product_id, available, version;
```

If the application needs the remaining quantity after reserving stock, `RETURNING` retrieves the result in the same statement rather than running an extra SELECT after the UPDATE.

With `DatabaseClient`, you can map the returned rows:

```java
public Mono<InventorySnapshot> reserveAndRead(
        DatabaseClient databaseClient,
        Long productId,
        int quantity) {

    return databaseClient.sql("""
            UPDATE inventory
            SET available = available - :quantity,
                version = version + 1
            WHERE product_id = :productId
              AND :quantity > 0
              AND available >= :quantity
            RETURNING product_id, available, version
            """)
            .bind("productId", productId)
            .bind("quantity", quantity)
            .map((row, metadata) -> new InventorySnapshot(
                    row.get("product_id", Long.class),
                    row.get("available", Integer.class),
                    row.get("version", Long.class)))
            .one();
}
```

If no row satisfies the condition, `one()` can complete empty. This example uses PostgreSQL `RETURNING` syntax; other databases may not support it or may use different syntax.

`@Modifying` is typically appropriate when only the affected row count is needed. If you need to return updated rows, use `DatabaseClient` or a custom repository to consume result rows rather than assuming a modifying query automatically maps `RETURNING` into an entity.

## 21. Testing Concurrent Updates

A single unit test verifies that the condition looks right, but does not prove behavior under competing requests. You need integration tests executing multiple publishers concurrently against a real database.

Example checking that only one request can reserve stock when requests combined exceed remaining inventory:

```java
Mono<Integer> requestA = inventoryRepository.reserveIfAvailable(100L, 4);
Mono<Integer> requestB = inventoryRepository.reserveIfAvailable(100L, 3);

StepVerifier.create(Mono.zip(requestA, requestB))
        .assertNext(results -> {
            int totalUpdated = results.getT1() + results.getT2();
            assertEquals(1, totalUpdated);
        })
        .verifyComplete();
```

This example assumes initial stock of 5 items and that each statement affects at most one row. One request updates 1 row; the other updates 0 rows. Afterward, re-read to verify `available` is non-negative and `reserved` increased only for the single successful request.

`Mono.zip` subscribes to both publishers simultaneously, though the scheduler, connection pool, and actual database execution still affect test concurrency. For reliable concurrency tests, use multiple appropriate connections/transactions, repeat the scenario, and verify the final invariant rather than relying on a single run.

Cases that should be tested:

- Two requests reserving stock whose combined amount exceeds available inventory.
- Two requests concurrently debiting an account balance.
- Two requests concurrently transitioning status from `PENDING`.
- Two requests updating the same version.
- Repeated requests after a timeout or lost response.
- Affected row count when the ID does not exist.
- Affected row count when assigning the same value as the current value.
- `CHECK`, `UNIQUE`, and foreign key constraints under contention.
- Rollback when the second statement in a transaction fails.

## 22. Observability and Diagnostics

When a conditional update returns an unexpected result, log enough information for analysis without exposing sensitive data:

- Operation type and use case name.
- Identifier masked/hashed per logging policy.
- Number of affected rows.
- Statement execution duration.
- Database error type if applicable.
- Retry count and retry reason.
- Expected version if optimistic locking is used.

Do not log balances, tokens, payment details, or unnecessary personal data. For operations with 0 rows, metrics can categorize by use case such as `insufficient_inventory`, `version_conflict`, or `already_processed` if the application can determine the reason reliably.

If an UPDATE is slow, inspect the execution plan and indexes for columns in the WHERE clause. Example:

```sql
CREATE INDEX ix_task_status_due_at
    ON task(status, expires_at);
```

For queries by primary key, the primary key index already exists. Do not create duplicate indexes if a suitable one already exists; every index adds write overhead and storage cost.

## 23. Common Pitfalls

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Two requests reserve beyond stock | Read, calculated, and wrote back stale value | Use conditional UPDATE `available >= quantity` |
| Row count is 0 even though ID exists | Status, version, or balance condition no longer matched | Interpret 0 as condition mismatch; read further if classification is needed |
| Row count > 1 when updating one ID | Condition not unique or schema missing constraint | Check primary/unique key and WHERE clause |
| Assigning same value yields 0 rows | Database/driver reports changed rows rather than matched rows | Check rows matched/changed semantics of the database |
| Bulk update does not increment version | Custom SQL bypasses automatic `@Version` handling | Increment version and compare expected version in SQL |
| Update succeeds but Java entity stays stale | Custom modifying query does not sync in-memory objects | Re-read or use RETURNING |
| Retry charges twice | Request not idempotent or missing idempotency key | Record unique request within the same transaction |
| Debited source without crediting destination | Two statements not in same transaction or error swallowed | Use reactive transaction and let errors cross boundary |
| Negative data despite service checks | Another write path bypassed Java logic | Add CHECK constraint and SQL conditions |
| UPDATE affects entire table | Missing WHERE clause or wrong parameters | Verify query, bindings, and row count; test before deploying |

## 24. Process for Designing Conditional Updates

When a use case needs to update based on current state, follow this sequence:

1. Identify the invariant to protect, such as non-negative balance, non-negative stock, or single-time state transition.
2. Identify the conditions that must hold at update time.
3. Put those conditions in the `WHERE` clause of the same UPDATE statement.
4. Compute new values directly from current columns in SQL, avoiding overwrites from stale Java snapshots.
5. Retrieve `rowsUpdated` or an appropriate return type to know whether the statement matched rows.
6. Explicitly define the meaning of 0, 1, and > 1 based on business cardinality.
7. Add `CHECK`, `UNIQUE`, `NOT NULL`, or foreign key constraints to enforce data integrity in the schema.
8. If multiple statements must be atomic, use a reactive transaction with the same `ConnectionFactory` and transaction manager.
9. If using versioning, compare expected version and increment version in the same statement.
10. Design idempotency and bounded retries for retryable requests.
11. Test contention against the real database and driver, and verify invariants after concurrent requests complete.

Concurrency control via conditional updates places the rules right where data changes. `WHERE` defines which states are eligible for update; calculations in `SET` operate on the row's current values; affected row counts indicate how many rows matched the operation per database/driver semantics. Combining conditional UPDATEs with constraints, versioning, transactions, and idempotency enables Spring Data R2DBC to handle contention scenarios—such as reserving stock, debiting balances, and transitioning state—without relying on stale application reads.
