# Building a Repeatable Upsert Without Duplicate Business Writes

In the `DATABASE_MYSQL` module, learners master MySQL from table design, data types, keys, and SQL queries through indexing, transactions, concurrency control, execution plan inspection, query optimization, privilege management, backups, and operational troubleshooting for relational databases. This lab combines unique keys, `INSERT ... ON DUPLICATE KEY UPDATE`, transactions, idempotency keys, and concurrency testing to build write operations that can be safely retried after timeouts or failures without creating duplicate records or duplicate business side effects.

A request may reach the server multiple times because a client timed out even after the database committed, a worker reprocessed a message following a restart, or two instances received the same command almost simultaneously. If every delivery performs a plain `INSERT` or adds/subtracts quantities, the system can create duplicate records or apply business effects multiple times. An idempotent operation for a given identifier and identical input payload yields the same final business state whether executed once or multiple times.

`UPSERT` is a useful write technique, yet the upsert syntax alone does not guarantee end-to-end business idempotency. You must define the business key, which fields are allowed to update, how duplicate requests are detected, how conflicting payloads are handled, and the transaction boundaries.

## 1. Distinguishing Upsert, Retry, and Idempotency

- **Upsert:** attempt an insert; on a primary key or unique key conflict, execute the update branch instead.
- **Retry:** re-execute an operation after a transient error or indeterminate outcome.
- **Idempotency:** ensure that repeating the same business intent causes no unintended additional side effects.

Example of importing a product from an external warehouse system:

1. The external system sends `sku=SKU-100`, name, and current quantity.
2. MySQL does not yet have that SKU, so the application inserts it.
3. If the SKU already exists, the application updates its state according to defined rules.
4. If the same message is redelivered, the data is not duplicated.

An upsert fits snapshot data well—for example, overwriting current stock with an absolute value. However, if the payload is a delta, such as "add 5 units," re-running `quantity = quantity + 5` adds 5 twice. For deltas, you must deduplicate using an event ID inside the same transaction as the addition.

## 2. Choosing Business Keys Before Writing SQL

A business key determines whether two requests describe the same entity. Do not use a display name or a mutable field as the key if it is not guaranteed unique by the business contract.

Example of a product synchronized from multiple external systems:

```sql
CREATE TABLE external_product (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    source_system VARCHAR(40) NOT NULL,
    external_id VARCHAR(100) NOT NULL,
    sku VARCHAR(80) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    source_version BIGINT UNSIGNED NOT NULL,
    source_updated_at DATETIME(6) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_product_source_external
        (source_system, external_id),
    UNIQUE KEY uq_product_source_sku
        (source_system, sku)
) ENGINE=InnoDB;
```

`(source_system, external_id)` identifies the record in the source system. The unique constraint enforces uniqueness even when two concurrent requests hit two application instances. Checking with `SELECT` before `INSERT` is not enough to prevent race conditions: both requests can simultaneously observe "does not exist" before either inserts.

Only create unique keys on attributes that truly must be unique. When multiple unique keys exist, keep in mind that `ON DUPLICATE KEY UPDATE` can be triggered by any of them. If two unique keys could match two different existing rows, the update branch may modify a row the application did not intend. When independent identifiers might collide, establish merge rules upfront or split write paths.

## 3. MySQL `INSERT ... ON DUPLICATE KEY UPDATE` Syntax

MySQL supports upserts via `INSERT ... ON DUPLICATE KEY UPDATE`. When an insert violates a primary key or unique index, the server executes the update clause instead of returning a standard duplicate-key error.

On MySQL 8.0.19 or later, you can define a row alias for the incoming row:

```sql
INSERT INTO external_product (
    source_system,
    external_id,
    sku,
    display_name,
    source_version,
    source_updated_at
)
VALUES (
    'warehouse-a',
    'P-9081',
    'SKU-100',
    'Mechanical keyboard',
    12,
    '2026-11-19 10:30:00.000000'
) AS incoming
ON DUPLICATE KEY UPDATE
    sku = incoming.sku,
    display_name = incoming.display_name,
    source_version = incoming.source_version,
    source_updated_at = incoming.source_updated_at;
```

The alias `incoming` represents the row being inserted. Row-alias syntax is supported starting in MySQL 8.0.19. The `VALUES(column)` function was previously used to reference inserted values but was deprecated in MySQL 8.0.20; on newer versions, prefer row-alias syntax per your server version's documentation.

For older MySQL versions without row-alias support, use compatible syntax for that version and plan migration during upgrades. Do not mix syntax examples across versions without checking the parser and release notes.

### Repeatable snapshot upsert

When inputs represent absolute state, assigning the same value again is repeatable:

```sql
INSERT INTO product_stock (
    sku,
    available_quantity,
    source_version
)
VALUES ('SKU-100', 25, 42) AS incoming
ON DUPLICATE KEY UPDATE
    available_quantity = incoming.available_quantity,
    source_version = incoming.source_version;
```

Re-running the same payload does not raise the quantity from 25 to 50; it leaves the value at 25. This is a key property of snapshot upserts.

However, an older message can arrive after a newer one. If version 41 is processed after version 42, the statement above would overwrite newer state with stale data. Use the source version to reject stale updates:

```sql
INSERT INTO product_stock (
    sku,
    available_quantity,
    source_version
)
VALUES ('SKU-100', 25, 42) AS incoming
ON DUPLICATE KEY UPDATE
    available_quantity = IF(
        incoming.source_version > product_stock.source_version,
        incoming.available_quantity,
        product_stock.available_quantity
    ),
    source_version = GREATEST(
        product_stock.source_version,
        incoming.source_version
    );
```

Place the `source_version` assignment after data assignments so the comparison evaluates the existing version before it is updated. This statement ignores older snapshots and leaves `available_quantity` unchanged when the incoming version is equal or lower. If two payloads carry the same version but different content, that is a data conflict requiring detection and investigation; never silently treat them as valid retries.

### Never turn an upsert into a repeated addition

This example is NOT idempotent if the request can be retried:

```sql
INSERT INTO product_stock (sku, available_quantity)
VALUES ('SKU-100', 5) AS incoming
ON DUPLICATE KEY UPDATE
    available_quantity =
        product_stock.available_quantity + incoming.available_quantity;
```

If the same request executes twice, the quantity increases by 10 instead of 5. This statement is only valid if each execution is guaranteed to represent a distinct new delta and the system enforces exactly-once delta tracking at the business layer.

## 4. Pitfalls to Watch Out for with `ON DUPLICATE KEY UPDATE`

### Any unique key can trigger the update

Suppose a table has a unique key on email and another unique key on customer code. An insert carrying row A's email alongside row B's customer code can trigger an unintended conflict. With multiple unique indexes, MySQL treats a duplicate as an update on the first conflicting condition and only one row can be updated. Never use a single shared upsert if multiple unique keys identify separate entities.

### Triggers and timestamps

The duplicate branch is an update operation. An `UPDATE` trigger can fire even when assigned values match existing ones. If the trigger produces side effects or writes audit logs, repeated requests can produce extra side effects. Avoid placing non-idempotent side effects inside triggers on upserted tables.

If you set `updated_at = CURRENT_TIMESTAMP` on every duplicate, repeated requests still modify the timestamp. When a timestamp must reflect actual data changes, update it only when the payload is newer or values actually differ; never use retry time as business event time.

### Affected row count is not a reliable business signal

With `INSERT ... ON DUPLICATE KEY UPDATE`, affected rows are typically 1 for an insert, 2 for an update, and 0 if an update assigns the same existing values; the `CLIENT_FOUND_ROWS` client flag can alter reporting for no-op updates. Never infer "new request" versus "duplicate request" solely from the return value of `executeUpdate()`.

### Auto-increment can leave gaps

A failed insert attempt that falls into the duplicate branch can still increment the `AUTO_INCREMENT` counter. Auto-increment IDs are not guaranteed to be gapless; never use ID gaps to infer lost records or duplicate requests.

## 5. `INSERT IGNORE` and `REPLACE` Are Not Equivalents to Upsert

| Statement | Behavior | Why Caution Is Needed |
|---|---|---|
| `INSERT ... ON DUPLICATE KEY UPDATE` | Duplicate key triggers the specified update branch. | Must choose the right unique key and encode business rules in the update. |
| `INSERT IGNORE` | Ignores certain errors and may convert them into warnings or coerce data. | Can mask data errors beyond duplicate keys; does not update existing rows. |
| `REPLACE` | On unique key conflict, deletes the existing row and inserts a new row. | Can fire delete/insert triggers, affect foreign keys, generate new IDs, and overwrite omitted columns. |

If the goal is to update specific columns when a record already exists, `ON DUPLICATE KEY UPDATE` states the intent clearly. Never use `REPLACE` as shorthand for upsert unless delete-then-insert semantics are genuinely desired.

## 6. Idempotency Keys for API Requests

Business keys identify entities, whereas APIs often need to identify one specific request attempt. For example, a customer submits a payment creation command, the client times out, and it resends the exact same request. Relying solely on `order_id` fails if an order can legitimately have multiple payments or distinct command types. An idempotency key identifies one specific request intent within a scope, usually a tenant or client.

Table design:

```sql
CREATE TABLE api_idempotency (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    idempotency_key VARCHAR(128) NOT NULL,
    request_hash BINARY(32) NOT NULL,
    status VARCHAR(16) NOT NULL,
    response_json JSON NULL,
    resource_id BIGINT UNSIGNED NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    completed_at TIMESTAMP(6) NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_idempotency_tenant_key
        (tenant_id, idempotency_key)
) ENGINE=InnoDB;
```

`request_hash` is a deterministic hash of the canonicalized request body. Reusing the same idempotency key with a different hash must be treated as a conflict, typically returning HTTP 409 or an equivalent business error. Do not use the hash to replace request authentication; it solely detects reusing a key with an altered payload.

### Handling inside one transaction

Processing flow:

1. Client sends an idempotency key and payload.
2. Application canonicalizes the request, computes the hash, and starts a transaction.
3. Application inserts a `PROCESSING` row into the idempotency table.
4. If the key already exists, lock/read that row and compare hashes.
5. If hashes differ, return conflict; if status is `COMPLETED`, return the stored response.
6. If this is a new request, apply the business changes.
7. Store the response/resource ID and set status to `COMPLETED`.
8. Commit both the idempotency row and business changes together.

Example of fetching or creating the idempotency row on MySQL 8.0.19 or later:

```sql
INSERT INTO api_idempotency (
    tenant_id,
    idempotency_key,
    request_hash,
    status
)
VALUES (?, ?, ?, 'PROCESSING') AS incoming
ON DUPLICATE KEY UPDATE
    id = LAST_INSERT_ID(api_idempotency.id);
```

Immediately after, read the row by its unique key within the same transaction:

```sql
SELECT id, request_hash, status, response_json, resource_id
FROM api_idempotency
WHERE tenant_id = ?
  AND idempotency_key = ?
FOR UPDATE;
```

`LAST_INSERT_ID(id)` in the duplicate branch is a MySQL idiom to set the connection-local last insert ID to the existing row's ID; the example above still re-reads by unique key to inspect the hash and status. The idempotency table should not have triggers with side effects because the duplicate branch performs an update. If relying on generated keys to fetch the ID, test behavior on your exact Connector/J version.

Keep the `PROCESSING` row, business updates, and `COMPLETED` transition inside the same transaction. Because uncommitted rows are not visible as completed outcomes to other transactions, a concurrent request with the same key blocks until the unique-key lock resolves. Once the first transaction commits, the second request reads the stored result; if the first rolls back, the second inserts the row and runs the business logic. Do not commit `PROCESSING` separately before running business logic unless you implement a complete lease and recovery protocol.

### Checking the hash and returning stored results

Service-layer pseudocode:

```text
begin transaction
insert-or-lock idempotency row by (tenant_id, key)

if stored request_hash != current request_hash:
    rollback
    return conflict

if status == COMPLETED:
    read stored response
    commit
    return stored response

perform business changes
store resource_id and response_json
set status = COMPLETED and completed_at
commit
return stored response
```

Store enough response metadata to replay the identical outcome on retries. Never create a new resource or re-emit external messages when a request is detected as already completed.

## 7. Event IDs to Prevent Double-Applying Deltas

For messages representing deltas like "subtract 3 items" or "add 100 points," snapshot upserts do not work. Use an inbox/deduplication table with a unique event ID and record the event in the same transaction as the update:

```sql
CREATE TABLE applied_event (
    consumer_name VARCHAR(100) NOT NULL,
    event_id CHAR(36) NOT NULL,
    applied_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    PRIMARY KEY (consumer_name, event_id)
) ENGINE=InnoDB;
```

Event-processing transaction:

```text
begin transaction
try insert (consumer_name, event_id) into applied_event
if duplicate key:
    rollback or end without applying business change
else:
    apply quantity = quantity + delta
    commit
```

JDBC example:

```java
@Transactional
public void applyStockDelta(StockDelta event) {
    try {
        jdbc.update("""
            INSERT INTO applied_event (consumer_name, event_id)
            VALUES (?, ?)
            """, "inventory-projection", event.eventId());
    } catch (DuplicateKeyException duplicate) {
        return;
    }

    int changed = jdbc.update("""
        UPDATE product_stock
        SET available_quantity = available_quantity + ?
        WHERE sku = ?
        """, event.delta(), event.sku());

    if (changed != 1) {
        throw new IllegalStateException("Unknown SKU: " + event.sku());
    }
}
```

This example uses Spring `JdbcTemplate`; duplicate exceptions must be handled so the transaction is not unexpectedly marked rollback-only by the transaction manager or provider. In Spring, `DuplicateKeyException` may be thrown after a statement fails; in MySQL, the transaction can usually continue, yet rollback-only behavior depends on exception translation and proxy boundaries. Test this on your actual stack. You can replace it with an `INSERT ... ON DUPLICATE KEY UPDATE` carrying an explicit result flag, though never use `INSERT IGNORE` if it could hide unrelated errors.

Crucial rule: inserting the event ID and updating the quantity must share the same transaction and database. If the event insert commits first and the process crashes before updating the quantity, retries are deduplicated and the update is lost. If the quantity update commits first before recording the event ID, retries apply the delta again. Sharing one transaction ensures both succeed or roll back together.

## 8. Writing to an Outbox When an Upsert Emits Events

If a business upsert must publish an event, write to the outbox in the same transaction:

```sql
START TRANSACTION;

INSERT INTO customer_profile (
    source_system,
    external_id,
    display_name,
    source_version
)
VALUES ('crm-a', 'C-100', 'Nguyen An', 8) AS incoming
ON DUPLICATE KEY UPDATE
    display_name = IF(
        incoming.source_version > customer_profile.source_version,
        incoming.display_name,
        customer_profile.display_name
    ),
    source_version = GREATEST(
        customer_profile.source_version,
        incoming.source_version
    );

INSERT INTO outbox_event (
    id, aggregatetype, aggregateid, type, payload
)
VALUES (
    UUID(),
    'Customer',
    'C-100',
    'CustomerSynchronized',
    JSON_OBJECT('sourceVersion', 8)
);

COMMIT;
```

This example only illustrates the transaction boundary. If the request is re-sent, the outbox statement above inserts a new event with a new UUID every time. When events should only be emitted if data actually changed, determine explicitly whether the insert/update modified state and assign a deterministic event identity tied to the command/version. Never emit a brand-new business event on every retry of the same command.

One design approach is storing a deterministic `command_id` or `event_id` in the outbox with a unique constraint, or inserting the outbox event only after confirming the request is new and executing for the first time. CDC connectors can also replay binlog entries on recovery, so downstream consumers still need event-ID deduplication.

## 9. Upserts in Java with PreparedStatement

Use parameter binding to prevent SQL injection and handle data types properly:

```java
String sql = """
    INSERT INTO external_product (
        source_system, external_id, sku, display_name,
        source_version, source_updated_at
    )
    VALUES (?, ?, ?, ?, ?, ?) AS incoming
    ON DUPLICATE KEY UPDATE
        sku = IF(
            incoming.source_version > external_product.source_version,
            incoming.sku,
            external_product.sku
        ),
        display_name = IF(
            incoming.source_version > external_product.source_version,
            incoming.display_name,
            external_product.display_name
        ),
        source_updated_at = IF(
            incoming.source_version > external_product.source_version,
            incoming.source_updated_at,
            external_product.source_updated_at
        ),
        source_version = GREATEST(
            external_product.source_version,
            incoming.source_version
        )
    """;

try (PreparedStatement ps = connection.prepareStatement(sql)) {
    ps.setString(1, sourceSystem);
    ps.setString(2, externalId);
    ps.setString(3, sku);
    ps.setString(4, displayName);
    ps.setLong(5, sourceVersion);
    ps.setTimestamp(6, Timestamp.valueOf(sourceUpdatedAt));
    ps.executeUpdate();
}
```

This SQL assumes Connector/J and MySQL support row aliases in upserts. `sourceVersion` must be a monotonically increasing version assigned by the source; if versions can reset or are only unique per epoch, include a source epoch or sequence in the contract. The statement protects against older snapshots, while same-version payloads with differing contents still require application-level hash/conflict checks.

## 10. Spring Data JPA: `save` Does Not Mean Native Upsert

`JpaRepository.save()` selects persist or merge based on entity state and how the provider detects new entities. It does not automatically generate `INSERT ... ON DUPLICATE KEY UPDATE`. A "read first, update if found, otherwise insert" flow still suffers from race conditions across instances.

Options:

- Use database unique constraints as the final line of defense.
- Use a native `INSERT ... ON DUPLICATE KEY UPDATE` query via a repository or `JdbcTemplate`.
- Use transactions and handle duplicate-key exceptions explicitly.
- For idempotency keys, persist the request/result inside the same business transaction.

Native query example in Spring Data JPA:

```java
@Modifying
@Query(value = """
    INSERT INTO product_stock (sku, available_quantity, source_version)
    VALUES (:sku, :quantity, :version) AS incoming
    ON DUPLICATE KEY UPDATE
        available_quantity = IF(
            incoming.source_version > product_stock.source_version,
            incoming.available_quantity,
            product_stock.available_quantity
        ),
        source_version = GREATEST(
            product_stock.source_version,
            incoming.source_version
        )
    """, nativeQuery = true)
int upsertSnapshot(
    @Param("sku") String sku,
    @Param("quantity") int quantity,
    @Param("version") long version
);
```

This example targets MySQL versions supporting row aliases; verify native query syntax and transaction context for your Spring Data JPA/Hibernate version. If the persistence context already holds the corresponding entity, native SQL can leave the in-memory entity out of sync with the database. Consider `clearAutomatically`, refreshing, or avoiding holding that entity in the same persistence context.

## 11. Transactions, Isolation, and Concurrent Contention

Unique constraints enforce uniqueness at the database layer. When two transactions concurrently insert the same business key, InnoDB coordinates contention on the unique index; one transaction may block waiting for the other to commit or roll back.

Scenario for two requests sharing an idempotency key:

1. Transaction A inserts key K and holds the unique-key lock.
2. Transaction B attempts to insert key K and waits.
3. If A commits, B enters the duplicate branch and reads the completed result.
4. If A rolls back, B proceeds to insert key K and execute the business logic.

This only works properly if the request record and business changes execute in the same transaction. Never use an unlocked `SELECT` to decide "the key does not exist" and then insert later; another transaction can create that key in between.

`SELECT ... FOR UPDATE` can lock an idempotency row once it already exists. A unique constraint is still essential to handle the case where the row does not yet exist and two concurrent transactions attempt to create it simultaneously. Never rely on isolation level alone in place of a unique key.

### Short transactions and retries

Never hold a transaction open while making HTTP calls or waiting on a broker. When external side effects are needed, use an outbox. On deadlocks or lock wait timeouts, roll back the entire unit of work and retry within bounded attempts using jittered backoff. Do not merely re-run the final statement if earlier statements already modified data.

## 12. Testing Idempotency

A solid test suite verifies both final data state and the count of executed business effects:

| Scenario | Execution | Expected Result |
|---|---|---|
| Fresh insert | Send an unseen business key. | One row created. |
| Resend identical snapshot | Send the same key and identical payload multiple times. | One row; final state unchanged. |
| Late stale snapshot | Send version 12, then version 11. | Version 12 data is preserved. |
| Same version, different payload | Send the same key/version with altered content. | Conflict detected; never silently overwrite. |
| Two concurrent requests with same key | Send the same idempotency key from two connections. | One business effect; the other returns stored result or runs after rollback. |
| Same key, different payload | Reuse key with a different request hash. | Conflict returned; business logic not run twice. |
| Replayed delta event | Deliver the same event ID twice. | Delta applied exactly once. |
| Crash before commit | Abort/rollback transaction after writing idempotency and business rows. | No changes committed; retries can execute cleanly. |
| Timeout after commit | Simulate client missing response despite commit. | Retry returns stored response without extra side effects. |
| Duplicate on secondary unique index | Send payload matching a different unique key than primary business key. | Conflict handled explicitly without updating the wrong row. |

Do not assert only the row count in the main table. Verify outbox events, payment/transfer logs, audit rows, and all related counters. A single main row does not prove the business action ran once if log tables or side effects were duplicated.

## 13. Lab with Two MySQL Sessions

Create the test table:

```sql
CREATE TABLE stock_snapshot (
    sku VARCHAR(40) NOT NULL,
    quantity INT NOT NULL,
    source_version BIGINT NOT NULL,
    PRIMARY KEY (sku)
) ENGINE=InnoDB;
```

**Exercise A — repeatable upsert**

Run the same statement twice:

```sql
INSERT INTO stock_snapshot (sku, quantity, source_version)
VALUES ('SKU-01', 20, 10) AS incoming
ON DUPLICATE KEY UPDATE
    quantity = incoming.quantity,
    source_version = incoming.source_version;
```

Verify:

```sql
SELECT * FROM stock_snapshot WHERE sku = 'SKU-01';
```

The result must contain one row with quantity still equal to 20. Replace the update clause with addition `quantity = stock_snapshot.quantity + incoming.quantity`, run twice, and observe the incorrect result to see why deltas require event deduplication.

**Exercise B — two transactions on the same key**

Open two sessions. Session A starts a transaction and upserts a SKU. Leave the transaction uncommitted. Session B runs an upsert for the same SKU and observes blocking on the unique-key lock. Commit Session A, then verify Session B completes via the duplicate branch. Repeat by rolling back Session A instead and observe Session B inserting cleanly.

**Exercise C — rejecting stale snapshots**

Upsert version 12 with quantity 30, then send version 11 with quantity 15. Use the version-guarded statement from Section 3. Verify the row retains quantity 30 and version 12.

## 14. Integrated Spring Boot Lab

Build an API `PUT /inventory/{sku}` accepting an `Idempotency-Key` header and a payload containing quantity and source version:

1. Create migrations for `product_stock` (with a unique key on SKU) and `api_idempotency` (with a unique key on tenant/key).
2. Create validated DTOs; canonicalize JSON before computing the SHA-256 request hash.
3. Implement a `@Transactional` service: fetch/create the idempotency row, verify the hash, execute the snapshot upsert, and save the response.
4. If the key already completed with the same hash, return the stored response.
5. If the key exists with a different hash, return HTTP 409.
6. If the incoming version is lower than the stored version, do not overwrite newer data.
7. Write integration tests running against real MySQL or Testcontainers with two concurrent connections.
8. Simulate a client timeout after commit and resend the request; verify the response replays and no new business records are created.
9. Simulate two concurrent requests sharing a key; verify only one business outcome occurs.
10. If the API emits events, write to the outbox with a deterministic event ID in the same transaction; test CDC/consumer deduplication separately.
11. Measure lock waits, deadlocks, transaction durations, and the rate of requests served from cached idempotency results.
12. Write a runbook covering idempotency key retention, hash conflicts, retries, and duplicate request investigation.

## 15. Retention and Limits of Idempotency Keys

Idempotency keys should not be purged immediately after a request succeeds. If pruned too early, a client or message broker may redeliver an old request after expiration and the application will treat it as brand new.

Retention policies should account for:

- Maximum window during which clients can retry.
- Maximum duration messages can stay in a broker or dead-letter queue prior to replay.
- Business reconciliation and investigation windows.
- Data retention and privacy regulations.
- Recovery windows from backups or event replays.

For financial transactions or operations that must never repeat over the entire business lifecycle, unique constraints on business tables (such as provider transaction IDs or payment references) must remain enforced even after API idempotency records expire. Transport-level idempotency keys and unique business references solve two different layers of the problem.

Avoid storing full sensitive payloads in the idempotency table if only a hash and minimal response are needed. You can store the hash, resource ID, result code, and a scrubbed response. If verbatim responses must be replayed, define clear encryption and retention policies.

## 16. Common Errors and Fixes

| Symptom | Common Cause | Fix |
|---|---|---|
| Retried request creates a new row | Missing unique business key or key fails to capture business identity. | Add a unique constraint on a stable business key. |
| Quantity increases multiple times | Upsert performs delta addition without event ID deduplication. | Use an inbox/applied-event unique key and update the delta in the same transaction. |
| Same key with altered payload accepted | Request hash not stored or compared. | Compare hashes and return conflict when content differs. |
| Stale snapshot overwrites newer data | Upsert ignores source version. | Apply update only when incoming version is newer; handle same-version conflicts. |
| Two concurrent requests create duplicates | `SELECT` before `INSERT` without unique constraint or duplicate handling. | Use unique keys and transactions; test concurrency with multiple connections. |
| Upsert updates the wrong row | Multiple unique indexes can conflict across different rows. | Separate identifiers, check conflict keys, or handle explicitly in a transaction. |
| Retries emit duplicate audit/outbox events | Trigger or code emits events unconditionally in duplicate branch. | Emit events only for new commands/real changes; use deterministic event IDs with unique constraints. |
| `REPLACE` breaks links | `REPLACE` deletes then inserts. | Use `ON DUPLICATE KEY UPDATE` or an explicit business transaction. |
| Affected row count misinterpreted | Output depends on insert/update/no-op and client flags. | Never base idempotency decisions on affected row counts; read state by key. |
| JPA `save()` still hits races | `save()` is not a native atomic upsert. | Use unique constraints, native upserts, or handle duplicates inside transactions. |

## 17. Completion Criteria

The lab meets requirements when:

- Business keys and unique constraints are clearly defined.
- Re-sending the same snapshot repeatedly produces no unintended state changes.
- Stale snapshots never overwrite newer snapshots.
- Same idempotency key and same request hash replay the stored response.
- Same idempotency key with a different payload is rejected.
- Delta events apply at most once in the database consumer via event IDs and transactions.
- Two concurrent requests never apply two business effects.
- Retries after timeouts never create duplicate payments, transfer logs, or outbox events.
- All side effects outside MySQL are idempotent or emitted via an outbox.
- Tests run against production-compatible MySQL and verify both data tables and business logs.

After completing this lab, learners should be able to explain why unique constraints are the final safeguard, why snapshot upserts differ from delta upserts, why idempotency keys require request hashes and retention, and why deduplication records must share the same transaction as business changes. This forms the foundation for building APIs, workers, and sync pipelines that can retry safely without duplicate business writes.

## Official References

- [MySQL 8.4 Reference Manual: INSERT ... ON DUPLICATE KEY UPDATE](https://dev.mysql.com/doc/refman/8.4/en/insert-on-duplicate.html)
- [MySQL 8.4 Reference Manual: InnoDB Locking](https://dev.mysql.com/doc/refman/8.4/en/innodb-locking.html)
- [MySQL 8.4 Reference Manual: InnoDB and AUTO_INCREMENT Handling](https://dev.mysql.com/doc/refman/8.4/en/innodb-auto-increment-handling.html)
- [Spring Framework Reference: Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Data JPA Reference](https://docs.spring.io/spring-data/jpa/reference/)
