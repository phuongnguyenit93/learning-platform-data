# Dialect-Specific SQL Upserts and Idempotency Checks

## 1. What is an upsert?

An **upsert** combines insert and update operations: if a row does not yet exist according to a defined conflict key, the database inserts a new row; if a row already exists, the database performs the specified update action.

For example, an inventory sync system receives data keyed by `tenant_id` and `sku`. Whenever a snapshot arrives, the application wants to insert the inventory row if absent or replace the current quantity if present:

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity)
VALUES (:tenantId, :sku, :quantity)
ON CONFLICT (tenant_id, sku)
DO UPDATE SET quantity = EXCLUDED.quantity;
~~~

The query above uses PostgreSQL syntax. `ON CONFLICT` specifies how to handle an insert that violates the corresponding unique constraint or primary key. `EXCLUDED` represents the row proposed for insertion.

Upserts are useful for data synchronization, recording latest state, storing configuration by business key, and handling messages that may be redelivered. However, an upsert does not automatically make every business operation idempotent. Idempotency depends on the semantics of the written data, the operation's identifying key, and any accompanying side effects.

In Spring Data R2DBC, database-specific upserts are typically executed with explicit SQL through **DatabaseClient** or a repository method using `@Query`. You must choose syntax matching the database engine and define database unique constraints to handle concurrent contention safely.

## 2. Distinguishing upsert from idempotency

These two concepts are related but not synonymous.

An **upsert** is a data-writing strategy: insert when no row matches the conflict key, update when one exists.

**Idempotency** is a property of an operation: executing the same request multiple times produces the same meaningful state as executing it once.

Expressed conceptually:

```text
f(f(state, request), request) = f(state, request)
```

If a request is resent due to a timeout, retry, or message broker redelivery, the system produces no unintended extra effects.

Examples:

| Operation | Sending same request twice | Idempotent? |
|---|---|---|
| Set quantity to 12 | Final value remains 12 | Yes, assuming no other side effects |
| Set status to ACTIVE | Final status remains ACTIVE | Yes, if secondary fields are also stable |
| Increment quantity by 2 | Value increases by 4 | No |
| Add 100 to balance | Balance increases twice | No |
| Record event with unique event_id and skip processed events | Event applies only once | Yes, if recording the event and updating business state are atomic |
| Send an email after every upsert | May send two emails | No, even if the database row ends up identical |

An upsert statement can be idempotent or non-idempotent depending on its `DO UPDATE` clause. Assigning absolute values is generally easier to make idempotent than applying incremental additions. When an operation has side effects outside the database, separate deduplication mechanisms are required.

## 3. Unique constraints are the foundation of upserts

The database must know what defines "the same record." This must be expressed through a primary key or unique constraint/index.

Example:

~~~sql
CREATE TABLE inventory (
    tenant_id UUID NOT NULL,
    sku VARCHAR(80) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity >= 0),
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (tenant_id, sku)
);
~~~

The composite primary key `(tenant_id, sku)` uniquely identifies an inventory row per SKU within each tenant.

Without a suitable unique constraint, two concurrent requests can both check and see no row, then both insert two rows. A `SELECT` before an `INSERT` cannot replace a constraint because a race condition can occur between the two statements.

Practical rules:

- Pick a business key reflecting true record identity.
- Define a primary key or unique constraint/index in the database.
- Reference the exact constraint columns in the conflict target.
- For tenant-scoped keys, include the tenant ID in the unique key.
- Never rely on service-layer existence checks alone to guarantee uniqueness.

If a unique key is meaningful only per tenant, a global unique constraint on SKU alone would cause one tenant to collide with another. Constraint design must match business scope.

## 4. Upserts in PostgreSQL with ON CONFLICT

PostgreSQL supports `INSERT ... ON CONFLICT` with two common actions: `DO NOTHING` and `DO UPDATE`.

### 4.1. Skipping duplicates with DO NOTHING

~~~sql
INSERT INTO external_customers (external_id, name)
VALUES (:externalId, :name)
ON CONFLICT (external_id) DO NOTHING;
~~~

If external_id does not exist, the row is inserted. If it already exists, the database skips the insert. No row is updated on conflict.

This is useful when recording a unique key once—such as an event ID or idempotency key. Note that `DO NOTHING` does not return the existing row on conflict. If the application needs the existing record, it must query separately after observing no row was inserted, or use a flow suited to concurrency needs.

### 4.2. Updating on conflict

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity, updated_at)
VALUES (:tenantId, :sku, :quantity, :updatedAt)
ON CONFLICT (tenant_id, sku)
DO UPDATE
SET quantity = EXCLUDED.quantity,
    updated_at = EXCLUDED.updated_at
RETURNING tenant_id, sku, quantity, updated_at;
~~~

- `(tenant_id, sku)` is the conflict target.
- `EXCLUDED.quantity` is the quantity in the row proposed for insertion.
- `inventory.quantity` is the quantity currently stored in the existing row.
- `RETURNING` asks PostgreSQL to return the row after insert or update.

Because values come from the same request, resending the same payload sets quantity to the same value. If `updatedAt` also comes from the request and stays constant across retries, the persisted state remains stable.

### 4.3. Keeping updated_at unchanged if data did not change

Using `updated_at = now()` updates the timestamp on every retry even when quantity did not change. The primary business state may match, yet the row still mutates.

You can update the timestamp only when quantity actually differs:

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity, updated_at)
VALUES (:tenantId, :sku, :quantity, :updatedAt)
ON CONFLICT (tenant_id, sku)
DO UPDATE SET
    updated_at = CASE
        WHEN inventory.quantity IS DISTINCT FROM EXCLUDED.quantity
        THEN EXCLUDED.updated_at
        ELSE inventory.updated_at
    END,
    quantity = EXCLUDED.quantity
RETURNING tenant_id, sku, quantity, updated_at;
~~~

`IS DISTINCT FROM` is PostgreSQL's null-safe comparison operator. This illustrates avoiding metadata churn when a payload does not alter quantity. Adjust the condition to cover every field considered meaningful domain state.

### 4.4. Updating only allowed columns

Do not blindly overwrite all columns from the incoming row if some are immutable or server-managed.

Example:

~~~sql
ON CONFLICT (tenant_id, sku)
DO UPDATE SET
    quantity = EXCLUDED.quantity,
    updated_at = EXCLUDED.updated_at;
~~~

This preserves other columns such as `created_at`, `created_by`, or moderation status, preventing sync requests from accidentally overwriting data owned by a separate workflow.

### 4.5. Conditional DO UPDATE

PostgreSQL allows a `WHERE` clause on `DO UPDATE`:

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity, version)
VALUES (:tenantId, :sku, :quantity, :incomingVersion)
ON CONFLICT (tenant_id, sku)
DO UPDATE SET
    quantity = EXCLUDED.quantity,
    version = EXCLUDED.version
WHERE inventory.version = :expectedVersion
RETURNING tenant_id, sku, quantity, version;
~~~

This updates only if the stored version matches the version expected by the application. If the condition fails, the row is not updated and `RETURNING` emits nothing.

In code, an empty result must be distinguished from a successful insert/update. It can indicate a version conflict or an unmet update predicate. This combines upsert with optimistic concurrency; clearly define incoming vs. expected versions in your API contract.

### 4.6. Conflict target must match a constraint

PostgreSQL can specify the conflict target by column list or constraint name:

~~~sql
ON CONFLICT ON CONSTRAINT uq_inventory_tenant_sku
DO UPDATE SET quantity = EXCLUDED.quantity;
~~~

The constraint name must exist in the schema. If the conflict target does not match an appropriate unique index or constraint, the statement fails. For partial unique indexes, predicate conditions and index inference must also satisfy PostgreSQL rules.

## 5. Executing PostgreSQL upserts with DatabaseClient

DatabaseClient fits well because upserts use dialect-specific SQL and the application often wants control over `RETURNING`.

Suppose the result record is:

~~~java
import java.time.OffsetDateTime;
import java.util.UUID;

public record Inventory(
        UUID tenantId,
        String sku,
        Integer quantity,
        OffsetDateTime updatedAt
) {}
~~~

Upsert method:

~~~java
public Mono<Inventory> upsertInventory(
        UUID tenantId,
        String sku,
        int quantity,
        OffsetDateTime updatedAt) {

    return databaseClient.sql("""
            INSERT INTO inventory (
                tenant_id, sku, quantity, updated_at
            )
            VALUES (
                :tenantId, :sku, :quantity, :updatedAt
            )
            ON CONFLICT (tenant_id, sku)
            DO UPDATE SET
                quantity = EXCLUDED.quantity,
                updated_at = EXCLUDED.updated_at
            RETURNING tenant_id, sku, quantity, updated_at
            """)
        .bind("tenantId", tenantId)
        .bind("sku", sku)
        .bind("quantity", quantity)
        .bind("updatedAt", updatedAt)
        .map((row, metadata) -> new Inventory(
                row.get("tenant_id", UUID.class),
                row.get("sku", String.class),
                row.get("quantity", Integer.class),
                row.get("updated_at", OffsetDateTime.class)
        ))
        .one();
}
~~~

Points to note:

- Table and column names match the PostgreSQL schema.
- All input values are bound, never string-concatenated into SQL.
- The row callback converts columns into Java types.
- `one()` returns `Mono<Inventory>` since the statement expects one row from RETURNING.
- With the PostgreSQL R2DBC driver, Java types read from temporal columns must match the SQL type and driver; for example, `OffsetDateTime` for `TIMESTAMPTZ`.

Without RETURNING, call `fetch().rowsUpdated()` to obtain the affected row count. When using RETURNING, map returned rows using `map(...).one()` or an appropriate multi-row fetch method.

Never call `block()` or manually call `subscribe()` inside a service. Return `Mono<Inventory>` to the caller so the reactive pipeline, errors, and transactions remain properly managed end-to-end.

## 6. Upserts across other database engines

Upserts have no single SQL syntax supported identically across all databases. R2DBC provides the reactive communication API; upsert syntax remains database-defined.

| Database | Common syntax | Key considerations |
|---|---|---|
| PostgreSQL | `INSERT ... ON CONFLICT ... DO UPDATE/NOTHING` | Supports conflict target and RETURNING |
| SQLite | `INSERT ... ON CONFLICT ... DO UPDATE/NOTHING` | UPSERT supported in suitable versions; verify SQLite version |
| MySQL | `INSERT ... ON DUPLICATE KEY UPDATE` | Conflicts can come from primary key or any unique index; no conflict target like PostgreSQL |
| MariaDB | `INSERT ... ON DUPLICATE KEY UPDATE` | Check version differences in syntax and referenced values |
| SQL Server | `MERGE` or controlled UPDATE/INSERT strategy | Must consider concurrency, locking, and version-specific behavior |
| Oracle | `MERGE` | Oracle-specific syntax and semantics; test with the corresponding driver |

### 6.1. MySQL

MySQL uses `ON DUPLICATE KEY UPDATE`:

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity)
VALUES (:tenantId, :sku, :quantity) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = incoming.quantity;
~~~

This example uses a row alias after VALUES per supported MySQL versions. In older versions or MariaDB, how proposed values are referenced may differ. Check documentation for your exact deployed database version.

One difference from PostgreSQL is that MySQL triggers the update branch on conflict against *any* matching primary key or unique index. If a table has multiple unique keys, understand clearly which conflicts can trigger an update. Do not assume targeted conflict matching like PostgreSQL's `ON CONFLICT (tenant_id, sku)`.

### 6.2. SQLite

SQLite supports UPSERT with `ON CONFLICT`:

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity)
VALUES (:tenantId, :sku, :quantity)
ON CONFLICT (tenant_id, sku)
DO UPDATE SET quantity = excluded.quantity;
~~~

SQLite uses `excluded` for the row proposed for insertion. Verify your SQLite version and R2DBC driver before relying on this syntax.

### 6.3. SQL Server and Oracle

SQL Server and Oracle offer `MERGE` to combine insert/update based on match conditions. However, syntax and concurrency characteristics differ. On SQL Server, carefully review locking, unique constraints, and version-specific guidance; a simple MERGE statement does not automatically make all concurrent workloads safe.

An alternative is attempting UPDATE first and falling back to INSERT if no row matched, though the sequence must be protected by a transaction and unique constraints; concurrent transactions racing to insert must still be handled. Never use a plain SELECT-then-INSERT without race handling.

### 6.4. Why one shared SQL query cannot work everywhere

Databases differ in:

- Conflict clause naming and placement.
- How unique constraints are targeted.
- How newly proposed rows are referenced.
- Row return support via RETURNING or OUTPUT.
- Trigger, sequence, and affected-row count behavior.
- Locking and transaction semantics.
- Handling when multiple unique indexes collide simultaneously.

If an application supports multiple databases, separate implementations behind dialect/adapter abstractions rather than forcing a single SQL string across all engines.

## 7. Why ReactiveCrudRepository.save() is not a business-key upsert

Spring Data's `save(entity)` determines whether an entity is new or existing using entity state detection, typically based on ID and potentially `@Version` or `Persistable.isNew()`.

This differs from upserting by a unique business key such as email, external_id, or `(tenant_id, sku)`.

For example, a new entity has a null ID while its external_id already exists in the database. `save(entity)` selects INSERT because the entity is detected as new. The database then raises a unique constraint error. Spring Data does not automatically translate that error into an UPDATE by external_id.

Conversely, an entity with a pre-assigned ID may be detected as existing and result in an update. That is likewise not equivalent to an atomic upsert on a unique business key.

Distinguish:

| Mechanism | Decision rule |
|---|---|
| `repository.save(entity)` | Spring Data detects entity state via ID/version/Persistable |
| `R2dbcEntityTemplate.insert(...)` | Explicit insert |
| `DatabaseClient` with upsert SQL | Database resolves conflicts via unique constraints and SQL clause |
| `SELECT` then INSERT/UPDATE | Application coordinates multiple statements; must handle race conditions |

If business rules require upserting by external_id, declare a unique constraint on external_id and issue the database-appropriate upsert statement. Never infer upsert semantics from the method name `save`.

## 8. Idempotency of upsert statements

### 8.1. Assigning absolute values is often idempotent

Example:

~~~sql
INSERT INTO user_settings (user_id, language)
VALUES (:userId, :language)
ON CONFLICT (user_id)
DO UPDATE SET language = EXCLUDED.language;
~~~

Sending the same userId and language repeatedly produces the same language state. This is an assignment, not an accumulation.

For the entire row to remain stable, inspect other columns such as updated_at, retry_count, audit fields, and triggers. If every rerun increments a counter or inserts a new audit row, the overall operation may still be non-idempotent.

### 8.2. Accumulative updates are not idempotent

~~~sql
INSERT INTO inventory (sku, quantity)
VALUES (:sku, :delta)
ON CONFLICT (sku)
DO UPDATE SET
    quantity = inventory.quantity + EXCLUDED.quantity;
~~~

If a request with delta = 5 is delivered twice, quantity increases by 10 total. The upsert handles row conflicts, not duplicate event delivery.

Never use direct accumulation if messages can be redelivered without an event ID or deduplication mechanism.

### 8.3. Timestamps and audit fields can break idempotency

Example:

~~~sql
DO UPDATE SET
    status = EXCLUDED.status,
    updated_at = CURRENT_TIMESTAMP;
~~~

Resending the same request changes updated_at every time. If the contract cares only about status, business state may be considered equivalent; if the entire record or audit history is observable, the operation is not strictly idempotent.

Define clearly which state must stay invariant across retries. You can pass a request-supplied timestamp preserved across retries, or update the timestamp only when business values actually change.

### 8.4. External side effects are not protected by upserts

Suppose after upserting an order status, the service sends an email or calls a payment API. If the request retries, the email or external call may run again even though the database row already matches.

An upsert governs only the database operation in that SQL statement. It does not grant exactly-once guarantees to emails, HTTP calls, message brokers, or external systems.

## 9. Idempotency keys for retryable requests

A common pattern for API retries is requiring clients to send an **idempotency key**. The key identifies one logical request, not a single HTTP transmission.

PostgreSQL schema example:

~~~sql
CREATE TABLE idempotency_requests (
    tenant_id UUID NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    response_status INTEGER,
    response_body JSONB,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, idempotency_key)
);
~~~

The primary key guarantees at most one record per tenant and idempotency key. request_hash is a fingerprint of the canonicalized payload; it detects if a client reuses the same key for a different request.

Typical processing flow:

1. Authenticate the caller and resolve tenant from a trusted source.
2. Canonicalize the request and compute request hash.
3. Attempt to insert the idempotency key using `ON CONFLICT DO NOTHING`.
4. If the insert succeeds, this is the first observed request; execute business logic.
5. Persist business results and stored response in the same transaction.
6. Mark the idempotency record complete before committing.
7. If the key already exists, load the existing record.
8. If the request hash differs, reject because the key was reused for a different payload.
9. If the hash matches and the request completed, return the stored response instead of re-executing business logic.

SQL to claim the key:

~~~sql
INSERT INTO idempotency_requests (
    tenant_id, idempotency_key, request_hash
)
VALUES (:tenantId, :key, :requestHash)
ON CONFLICT (tenant_id, idempotency_key) DO NOTHING
RETURNING tenant_id, idempotency_key;
~~~

If `RETURNING` emits a row, this operation claimed the new key. If no row returns, the key already existed or a concurrent request won. The application loads the existing record and enforces hash/status rules.

### 9.1. Same key with different payload must be handled explicitly

Never silently return an old response for a different payload. For instance, a client sends key `abc` with amount 100, then reuses that key with amount 500. Checking only the key would return the previous response and mask a client bug.

Comparing request_hash catches this case. Define canonicalization before hashing so field ordering, date formatting, or numeric representation differences do not make the same logical request look different.

### 9.2. Keys need scope and retention limits

Idempotency keys should be scoped appropriately—by tenant, user, or operation type. Never use global keys if two independent customers could pick the same string.

Also define record retention. Expiring keys too early lets late retries re-execute operations. Keeping them forever grows the table unboundedly. Retention should match client, broker, and business retry windows.

## 10. Combining idempotency records with reactive transactions

To stop two concurrent requests from executing the same business action simultaneously, claiming the idempotency key and writing business state must be atomic inside the same database transaction.

With PostgreSQL, the unique constraint on `(tenant_id, idempotency_key)` forces two racing transactions using the same key to be coordinated by the database. One transaction inserts the key; the other waits on conflict resolution under PostgreSQL's transaction semantics.

Illustrative service structure:

~~~java
@Transactional
public Mono<PaymentResult> createPayment(
        UUID tenantId,
        String idempotencyKey,
        String requestHash,
        CreatePaymentCommand command) {

    return claimIdempotencyKey(tenantId, idempotencyKey, requestHash)
            .flatMap(claimed -> {
                if (!claimed) {
                    return loadPreviousResult(
                            tenantId, idempotencyKey, requestHash
                    );
                }

                return createPaymentRecord(command)
                        .flatMap(result ->
                                storeIdempotencyResult(
                                        tenantId,
                                        idempotencyKey,
                                        result
                                ).thenReturn(result)
                        );
            });
}
~~~

`claimIdempotencyKey`, `loadPreviousResult`, `createPaymentRecord`, and `storeIdempotencyResult` are illustrative methods to implement via repositories, templates, or `DatabaseClient`. The crucial point is returning the whole publisher inside one transaction with all operations sharing the same `ConnectionFactory` and transaction manager.

If the business step fails before commit, the transaction rolls back both the newly inserted idempotency record and business data. A subsequent retry can claim the key and reattempt under defined policy.

For long-running workflows or returning an IN_PROGRESS state across multiple transactions, the design differs: you need explicit processing states, leases/timeouts, recovery, and handling for workers crashing mid-flight. Never hold a database transaction open across long jobs or external network calls.

## 11. Using event IDs to prevent duplicate message processing

With at-least-once message brokers, the same event can be redelivered. Store processed event IDs with a unique constraint:

~~~sql
CREATE TABLE processed_events (
    event_id UUID PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL
);
~~~

Inside a transaction:

1. Insert event_id into processed_events with `ON CONFLICT DO NOTHING`.
2. If no new row was inserted, the event was already processed; skip business logic.
3. If the insert succeeded, apply the business state change.
4. Commit both the event marker and business change together.

If the business step fails, the transaction must roll back so the event marker is not persisted alone. When the broker redelivers, the event can be retried.

For accumulative operations, such as incrementing inventory or awarding points, a unique event ID is essential so the delta is never applied twice. Upserting by SKU and adding delta alone will still double-apply on duplicate deliveries.

When a message handler must also emit downstream events to a broker, write an outbox record in the same transaction as the business change. A separate publisher reads the outbox and dispatches messages; downstream consumers still need deduplication by event ID because broker publishing itself can retry.

## 12. Outbox and external side effects

A local R2DBC transaction cannot span both a database and an external HTTP/email service. If the database commits and the HTTP call fails, or the HTTP call succeeds and the database rolls back, the two systems fall out of sync.

The transactional outbox pattern solves persisting the intent to emit a message:

~~~sql
CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_id BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ
);
~~~

Within one transaction:

- Upsert or update business data.
- Insert an outbox event with a unique event_id.
- Commit.

A worker/publisher polls unsent outbox events, sends the message, and updates published_at. If the publisher sends successfully and crashes before marking published_at, the event may be sent again. Consumers require their own idempotency/deduplication.

An outbox does not make a broker exactly-once. It ensures business changes and emission intent persist atomically in the same database; duplicate deliveries still need handling.

## 13. Handling contention and race conditions

### 13.1. Why SELECT then INSERT is unsafe

An error-prone implementation:

~~~text
Request A: SELECT -> no row
Request B: SELECT -> no row
Request A: INSERT -> succeeds
Request B: INSERT -> duplicate key error
~~~

Without a unique constraint, both INSERTs can succeed and create logically duplicate rows. With a unique constraint, one request fails and the application must still handle the conflict properly.

Atomic upserts backed by a unique constraint let the database resolve contention inside a single statement. That is why database conflict clauses should be used instead of splitting into SELECT followed by INSERT/UPDATE.

### 13.2. Unique constraints remain a mandatory safeguard

Never rely solely on distributed locks or application-layer checks while omitting unique constraints. Multiple application instances, retries, timeouts, and other processes can touch the same data concurrently.

Constraints are the final guarantee at the database level. Application locks can reduce contention, not replace constraints.

### 13.3. Upserts do not resolve every business conflict

Suppose two requests update the same product with different values. The database serializes the conflict via its locking mechanism, yet the later request can overwrite the earlier one.

To detect stale writes, use versions, expected states, or conditional updates. For instance, update only when the stored version matches the version read by the client. On mismatch, report a conflict so the caller reloads and decides.

### 13.4. Event ordering can matter

If two events with different timestamps or sequence numbers arrive out of order, a simple upsert by external_id can let an older event overwrite a newer one. Add a predicate accepting only newer versions or timestamps:

~~~sql
INSERT INTO external_status (external_id, source_version, status)
VALUES (:externalId, :sourceVersion, :status)
ON CONFLICT (external_id)
DO UPDATE SET
    source_version = EXCLUDED.source_version,
    status = EXCLUDED.status
WHERE external_status.source_version < EXCLUDED.source_version;
~~~

This skips the update when the stored version is greater than or equal to the incoming version. If RETURNING emits no row, the application must distinguish an ignored stale event from a successful update.

## 14. Retries and errors after sending SQL

A reactive pipeline can retry on transient errors, though retrying a write statement is not automatically safe.

Scenarios:

- Connection drops before the database executes the statement.
- Database commits, then the response is lost.
- Transaction hits a deadlock or serialization failure.
- Driver times out while it is unclear whether the database completed.
- Client retries the entire HTTP request after receiving no response.

When commit outcome is ambiguous, re-executing a non-idempotent operation can apply its effect a second time. Business keys, idempotency keys, or event IDs are needed to tell whether a request was already processed.

Rules:

- Retry only errors classified as transient under your policy.
- Retry the entire transaction when a transaction rolls back and the error is retryable.
- Never place `subscribe()` internally to launch another attempt manually.
- Never retry indefinitely; cap attempts and apply backoff.
- Keep the same idempotency key across retries of the same logical request.
- Never generate a new key per retry, as the system would treat it as a brand-new request.
- For external side effects, use an outbox and deduplication.

With Spring transactions, where the retry operator sits determines whether each retry creates a new transaction or reuses an old transaction context. Design and test transaction/retry ordering under your real setup rather than tacking `retryWhen` onto the end of a pipeline and assuming all errors are handled safely.

## 15. R2dbcEntityTemplate and repositories in upsert scenarios

R2dbcEntityTemplate suits entity-oriented operations and exposes separate insert/update methods. However, do not assume `save()` performs an atomic upsert by unique business key.

- `ReactiveCrudRepository.save(entity)` picks insert/update via entity state detection.
- `R2dbcEntityTemplate.insert(...)` performs an insert.
- `R2dbcEntityTemplate.update(...)` performs an update by query.
- `DatabaseClient` can issue database-specific upsert SQL in one statement.

When upserting by business key or using `ON CONFLICT`, `ON DUPLICATE KEY UPDATE`, or `MERGE`, DatabaseClient is the direct and controllable option. Wrap the SQL inside a custom repository fragment so services remain decoupled from dialect specifics.

An architecture can split out an interface:

~~~java
public interface InventoryUpsertRepository {
    Mono<Inventory> upsert(InventoryCommand command);
}
~~~

Implementation using DatabaseClient:

~~~java
public class InventoryUpsertRepositoryImpl
        implements InventoryUpsertRepository {

    private final DatabaseClient databaseClient;

    public InventoryUpsertRepositoryImpl(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    @Override
    public Mono<Inventory> upsert(InventoryCommand command) {
        // Execute the dialect-specific upsert SQL.
        // Bind all values and map RETURNING to Inventory.
        return executeUpsert(command);
    }
}
~~~

`executeUpsert` represents the database-specific SQL logic. Isolating it in a fragment lets the rest of the domain/service layer rely on a stable contract while implementations vary by dialect.

If the application supports multiple databases, provide dedicated implementations for PostgreSQL, MySQL, or SQL Server. Never pretend a dialect-specific SQL statement is portable merely because it runs through a reactive API.

## 16. Batch upserts

Some databases support multi-row inserts with conflict handling:

~~~sql
INSERT INTO inventory (tenant_id, sku, quantity)
VALUES
    (:tenantA, :skuA, :quantityA),
    (:tenantB, :skuB, :quantityB)
ON CONFLICT (tenant_id, sku)
DO UPDATE SET quantity = EXCLUDED.quantity;
~~~

Batching reduces round-trips and fits data synchronization. Watch out for:

- Large batches can produce oversized statements and result sets.
- Batch size must respect driver/database limits.
- Payloads should be validated before dispatch.
- Decide between whole-batch atomic transactions and per-chunk processing.
- Duplicate conflict keys within the same input batch can cause errors or engine-specific behavior.

In PostgreSQL, a single `INSERT ... ON CONFLICT DO UPDATE` statement cannot affect the same target row twice in one command; duplicate conflict keys in the input can raise a cardinality violation error. Deduplicate or merge inputs by business key before building the statement.

If using `saveAll`, do not assume Spring Data generates a multi-row upsert. `saveAll` is an entity-saving API; its insert/update semantics come from entity state detection and do not automatically become a dialect-specific upsert by business key.

## 17. Security and correctness of upsert data

Upserts are frequently used for external syncs and data ingestion. Control which data may be overwritten.

- Validate types, value ranges, and length bounds before binding.
- Never let inputs dictate table/column identifiers via SQL concatenation.
- Update only columns the data source is authorized to own.
- Enforce unique constraints and CHECK constraints in the database.
- Include tenant scope in unique keys and predicates appropriately.
- Never trust client-supplied timestamps or versions if they could regress state.
- Never leak another tenant's record details when a conflict occurs.
- Avoid logging idempotency keys, tokens, or sensitive payloads unnecessarily.

Bind parameters prevent data values from being parsed as SQL syntax, but they do not enforce authorization. An upsert can be completely safe from SQL injection and still let a user overwrite data they do not own if the service omits tenant and ownership checks.

## 18. Testing upserts and idempotency

Tests must use a database compatible with the actual syntax. Mocking DatabaseClient cannot verify conflict targets, locking, unique constraints, RETURNING, or affected-row behavior.

### 18.1. Testing initial insert

- Send a business key that does not yet exist.
- Verify exactly one row is created.
- Verify generated/default values match expectations.
- Verify RETURNING output includes expected columns.

### 18.2. Testing conflict and update

- Send the same business key with a different quantity.
- Verify only one row still exists.
- Verify allowed update columns changed.
- Verify immutable columns such as created_at were not overwritten.

### 18.3. Testing repeated identical payloads

- Send the same request twice.
- Verify final state is identical.
- Verify timestamps or audit fields change only under defined rules.
- Verify no duplicate events or side effects occurred.

### 18.4. Testing accumulation and deduplication

- Send the same event ID twice.
- Verify the delta applied only once.
- Send a different event ID with the same payload.
- Verify the new event applies per business rules.

### 18.5. Testing concurrency

- Send multiple concurrent requests with the same unique key.
- Verify the database holds only one logical row.
- Check final outcome matches expected ordering/version rules.
- Verify duplicate requests sharing an idempotency key do not execute business logic twice.

### 18.6. Testing rollbacks

- Claim an idempotency key.
- Perform the business mutation.
- Intentionally fail a later step.
- Verify the transaction rolls back both the marker and business mutation when designed in one transaction.
- Retry with the same key and verify the request can be processed per policy.

### 18.7. Testing request hashes

- Send key and payload the first time.
- Resend same key with same payload; verify previous response returns.
- Send same key with different payload; verify rejection.
- Verify tenant scoping and key retention behavior.

Use Testcontainers or a test database matching production engine and version. H2 or mocks cannot prove the semantics of PostgreSQL `ON CONFLICT`, MySQL `ON DUPLICATE KEY UPDATE`, or SQL Server `MERGE`.

## 19. Common errors

| Symptom | Cause | Fix |
|---|---|---|
| Duplicate key on insert | Missing conflict clause or wrong conflict target | Check unique constraints and SQL dialect |
| Multiple rows with the same business key | Missing unique constraint | Create appropriate primary key/unique index |
| Retries increment quantity multiple times | Using accumulation without event deduplication | Use unique event IDs or assign absolute values |
| Retries continually mutate updated_at | Assigning CURRENT_TIMESTAMP on every conflict | Update only when data changes or use stable timestamps |
| Requests with same key return wrong result | Not checking request fingerprint | Store and compare request_hash |
| Two concurrent requests execute logic twice | Application-level existence check before insert | Claim key via unique constraint and transaction |
| Upsert overwrites created_at or internal fields | Updating too many columns | Explicitly list updatable columns |
| Stale event overwrites newer state | Not checking source version/sequence | Add version condition in DO UPDATE |
| RETURNING emits no rows | DO NOTHING or DO UPDATE predicate unmet | Handle empty results and read current state |
| SQL works on PostgreSQL but fails on other engines | Dialect-specific upsert syntax | Separate implementations per database |
| Side effects repeat despite unchanged row | Email/HTTP/messages triggered on every retry | Use outbox, consumer deduplication, or API idempotency |
| Batch upsert fails on duplicate keys | Multiple input rows share a conflict target in one statement | Deduplicate/merge inputs before sending |

## 20. Workflow for designing safe upserts

Before implementing, determine:

1. Which business key uniquely identifies the record?
2. Does the database have a corresponding primary key or unique constraint?
3. Which upsert syntax does the target database support?
4. Which columns may the conflict branch update?
5. Do repeated requests produce the same state or accumulate effects?
6. Do timestamps, counters, auditing, or triggers mutate results on every retry?
7. Are request-level idempotency keys or message-level event IDs needed?
8. How should key reuse with a different payload be handled?
9. Do claiming the key and updating business data need the same transaction?
10. Are there external side effects requiring an outbox or deduplication?
11. Which errors are retried, and how is the idempotency key preserved?
12. Have concurrency, conflicts, rollbacks, and duplicate deliveries been tested against a real database?

A commonly effective design combination:

- Use **upserts by unique business key** for latest state.
- Use **idempotency keys** for retryable requests.
- Use **event IDs** for at-least-once messages.
- Use **transactions** to bind marker writes with business mutations in the same database.
- Use an **outbox** for post-commit event emission intent.
- Use **versions/conditions** to prevent stale data from overwriting newer state.

## 21. Conclusion

Dialect-specific SQL upserts allow the database to handle inserts and conflict updates in a single statement backed by unique constraints. In Spring Data R2DBC, DatabaseClient is the direct choice for issuing statements like PostgreSQL `ON CONFLICT`, MySQL `ON DUPLICATE KEY UPDATE`, SQLite UPSERT, or `MERGE` on supported databases.

Upserts do not automatically guarantee idempotency. Assigning absolute values can typically be repeated safely, whereas accumulation, unconditional timestamp updates, or external side effects can cause duplicate effects. When requests or messages can be retried, use unique idempotency keys or event IDs, store fingerprints to catch key reuse with altered payloads, and enclose related operations in appropriate transactions.

Unique constraints resolve database contention; transactions keep related changes atomic; outboxes and consumer deduplication handle repeatable event delivery. Combining these mechanisms cleanly ensures multi-write operations remain consistent and predictable.
