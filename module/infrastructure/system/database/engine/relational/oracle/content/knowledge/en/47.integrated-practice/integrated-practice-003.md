# Designing Inventory Reservation and Verifying Concurrent Transactions in Oracle

## 1. The Inventory Reservation Problem

In an order management or sales system, multiple requests can attempt to purchase the same product simultaneously. If each request reads the inventory balance, checks it, and then updates it, two transactions can observe the same available quantity and both decide to sell. As a result, the system confirms more orders than physical stock allows: **overselling**.

For example, suppose a warehouse has 5 units in stock. Two requests, A and B, both read `available_qty = 5`. Each request needs 4 units. If both check only in Java and then insert their orders, the total promised quantity is 8 while the warehouse only has 5.

The solution must enforce correctness in the database, where competing transactions contend for the same row of data. This lesson belongs to the **Database Engine Relational Oracle** module, chapter **Integrated Practice**, and focuses on **designing inventory reservation and verifying concurrent transactions**.

A complete design requires:

- Defining inventory invariants and reservation states.
- Executing reservations via an atomic conditional update.
- Placing the inventory update, reservation record, and request outcome inside the same transaction.
- Preventing duplicate submissions using an idempotency key and unique constraint.
- Handling confirm, release, cancel, and expire through locked state transitions.
- Enforcing consistent lock ordering for multi-product orders.
- Verifying with multiple truly concurrent connections/transactions.
- Performing reconciliation to detect discrepancies between reserved quantities and active reservations.

## 2. Defining Invariants Before Writing SQL

Suppose each product tracks inventory per warehouse. We manage two quantities:

- `on_hand_qty`: physical quantity currently in the warehouse and not yet shipped out.
- `reserved_qty`: portion of `on_hand_qty` held for unfinished orders/reservations.

Quantity available for new requests:

\[
available\_qty = on\_hand\_qty - reserved\_qty
\]

Core invariants:

\[
on\_hand\_qty \geq 0
\]

\[
reserved\_qty \geq 0
\]

\[
reserved\_qty \leq on\_hand\_qty
\]

\[
available\_qty \geq 0
\]

A new reservation may only be created when:

\[
available\_qty \geq requested\_qty
\]

and `requested_qty > 0`.

These rules must be enforced in Oracle using conditional DML and constraints. Validation in Java only returns early user feedback; it cannot prevent two concurrent transactions from racing.

### 2.1. Distinguishing Physical Stock, Available Stock, and Committed Stock

Do not overload a single `quantity` column with multiple meanings. Align with business definitions:

- Goods received into warehouse, not yet sold: increase `on_hand_qty`.
- Goods temporarily held: increase `reserved_qty`.
- Reservation cancelled or expired: decrease `reserved_qty`.
- Order confirmed and stock consumed: decrease both `on_hand_qty` and `reserved_qty`.
- Damaged/lost stock: decrease `on_hand_qty`, but only if it does not push `on_hand_qty` below `reserved_qty`; any held portion must be handled through a separate workflow.

If the business defines an “allocated but not yet shipped” state, you can keep `reserved_qty` until shipment. Define precisely when stock leaves `available_qty`.

### 2.2. Units and Precision

If products are sold only in whole units, use integers. If goods are weighed or measured, choose an appropriate scale, such as `NUMBER(18,3)` for kilograms or liters with three decimal places. Do not use `FLOAT` or `BINARY_DOUBLE` for quantities requiring exact reconciliation.

All APIs must use the same unit of measure; never let one service send grams while another interprets the value as kilograms.

## 3. Oracle Data Model

Data can be separated into an inventory stock table, a request/reservation header, and reserved product line items.

### 3.1. Inventory Stock by Product and Warehouse

```sql
CREATE TABLE app.inventory_stock (
    warehouse_id   NUMBER(18,0) NOT NULL,
    product_id     NUMBER(18,0) NOT NULL,
    on_hand_qty    NUMBER(18,3) DEFAULT 0 NOT NULL,
    reserved_qty   NUMBER(18,3) DEFAULT 0 NOT NULL,
    updated_at     TIMESTAMP WITH TIME ZONE
                   DEFAULT SYSTIMESTAMP NOT NULL,

    CONSTRAINT inventory_stock_pk
        PRIMARY KEY (warehouse_id, product_id),

    CONSTRAINT inventory_stock_onhand_ck
        CHECK (on_hand_qty >= 0),

    CONSTRAINT inventory_stock_reserved_ck
        CHECK (reserved_qty >= 0),

    CONSTRAINT inventory_stock_available_ck
        CHECK (reserved_qty <= on_hand_qty)
);
```

The primary key guarantees one stock row per warehouse/product pair. Check constraints act as the final line of defense if another batch job or application updates the table.

For integer-only units, change the quantity columns to `NUMBER(18,0)` and validate inputs accordingly.

### 3.2. Reservation/Request Header

A request carries an idempotency key unique within a tenant and operation:

```sql
CREATE TABLE app.inventory_reservation (
    reservation_id   NUMBER GENERATED BY DEFAULT AS IDENTITY,
    tenant_id        NUMBER(18,0) NOT NULL,
    operation_name   VARCHAR2(40) NOT NULL,
    idempotency_key  VARCHAR2(128) NOT NULL,
    request_hash     RAW(32) NOT NULL,
    reservation_status VARCHAR2(16) NOT NULL,
    created_at       TIMESTAMP WITH TIME ZONE
                     DEFAULT SYSTIMESTAMP NOT NULL,
    expires_at       TIMESTAMP WITH TIME ZONE,
    completed_at     TIMESTAMP WITH TIME ZONE,
    result_code      VARCHAR2(40),

    CONSTRAINT inventory_reservation_pk
        PRIMARY KEY (reservation_id),

    CONSTRAINT inventory_reservation_request_uq
        UNIQUE (tenant_id, operation_name, idempotency_key),

    CONSTRAINT inventory_reservation_status_ck
        CHECK (reservation_status IN
          ('PROCESSING', 'HELD', 'REJECTED',
           'CONFIRMED', 'RELEASED', 'EXPIRED'))
);
```

Identity columns require an Oracle release that supports identity. On older releases, use a sequence with a `BEFORE INSERT` trigger or supply `NEXTVAL` from the application.

`PROCESSING` is strictly an internal state inside an uncommitted transaction. Never commit a header in this state under a synchronous model; if the transaction finishes normally, the header must transition to `HELD` or `REJECTED` before commit.

### 3.3. Reservation Line Items

```sql
CREATE TABLE app.inventory_reservation_line (
    reservation_id NUMBER(18,0) NOT NULL,
    warehouse_id   NUMBER(18,0) NOT NULL,
    product_id     NUMBER(18,0) NOT NULL,
    quantity       NUMBER(18,3) NOT NULL,

    CONSTRAINT inventory_reservation_line_pk
        PRIMARY KEY (reservation_id, warehouse_id, product_id),

    CONSTRAINT inventory_reservation_line_qty_ck
        CHECK (quantity > 0),

    CONSTRAINT inventory_reservation_line_res_fk
        FOREIGN KEY (reservation_id)
        REFERENCES app.inventory_reservation(reservation_id),

    CONSTRAINT inventory_reservation_line_stock_fk
        FOREIGN KEY (warehouse_id, product_id)
        REFERENCES app.inventory_stock(warehouse_id, product_id)
);
```

If a request can contain the same product multiple times, aggregate lines by `(warehouse_id, product_id)` before reserving or design appropriate row locking. Pre-aggregating ensures only one stock update per warehouse/product pair.

### 3.4. Index for the Expiry Worker

The worker typically searches for held reservations that have expired:

```sql
CREATE INDEX app.inventory_reservation_exp_ix
ON app.inventory_reservation
   (reservation_status, expires_at, reservation_id);
```

Indexes must be evaluated under realistic workload. If most reservations are terminal, data skew and partitioning/retention strategy can influence index choices.

## 4. Why SELECT Followed by UPDATE in Java Is Unsafe

A common anti-pattern:

```text
SELECT available_qty
If available_qty >= requested_qty:
    UPDATE inventory_stock
    INSERT reservation
```

There is a time gap between `SELECT` and `UPDATE`. Two transactions can read the same previously committed value.

Example:

```text
T1: SELECT available = 5
T2: SELECT available = 5
T1: check 5 >= 4
T2: check 5 >= 4
T1: INSERT reservation 4
T2: INSERT reservation 4
T1: COMMIT
T2: COMMIT
```

Without a lock or a guard condition in the `UPDATE` statement, total reservations can exceed available stock.

This is a time-of-check to time-of-use (TOCTOU) race condition. Adding `synchronized` inside a single JVM does not solve it when the application runs across multiple pods/processes or shares the database with batch jobs.

## 5. Reserving via Atomic Conditional UPDATE

For a single product in one warehouse, the core operation is:

```sql
UPDATE app.inventory_stock
SET reserved_qty = reserved_qty + :requested_qty,
    updated_at = SYSTIMESTAMP
WHERE warehouse_id = :warehouse_id
  AND product_id = :product_id
  AND on_hand_qty - reserved_qty >= :requested_qty;
```

Then inspect the affected row count:

- `SQL%ROWCOUNT = 1`: reservation succeeded.
- `SQL%ROWCOUNT = 0`: no matching stock row or insufficient available quantity.

The predicate `on_hand_qty - reserved_qty >= :requested_qty` is evaluated within the `UPDATE` statement itself. Oracle locks the updated row; if another transaction is modifying the same row, the second transaction waits. Once it proceeds, the predicate is re-evaluated against the row state per Oracle write-consistency rules. Thus two requests cannot both increment `reserved_qty` past `on_hand_qty` as long as all write paths respect the invariant.

### 5.1. No Need to Read Stock First to Decide

The application can read `available_qty` for UI display, but that is merely informational as of the read timestamp. The authoritative reserve decision must come from the conditional `UPDATE`.

Display query example:

```sql
SELECT on_hand_qty - reserved_qty AS available_qty
FROM app.inventory_stock
WHERE warehouse_id = :warehouse_id
  AND product_id = :product_id;
```

The value can change immediately after the query returns. Only the reserve `UPDATE` confirms the right to hold that quantity.

### 5.2. Validating Input Before Binding

At the application layer:
- Quantity must be greater than 0.
- Quantity must fit within the column's precision and scale.
- Warehouse and product must be valid.
- Reject NaN/Infinity if data passes through floating-point types.
- Normalize units of measure.
- Construct `BigDecimal` from decimal strings or exact decimal sources.

Oracle check constraints continue to protect data if another caller bypasses application validation.

## 6. Placing the Stock Update and Reservation Record in the Same Transaction

Never commit an increase to `reserved_qty` and insert the reservation record in a separate transaction. If the insert fails, stock remains locked with no record to release it.

Conversely, never commit a `HELD` reservation before increasing `reserved_qty`, because the system would record a hold without deducting from available quantity.

Both operations must be atomic:

```text
BEGIN TRANSACTION
    |
    v
INSERT reservation request (unique idempotency key)
    |
    v
Conditional UPDATE inventory_stock
    |
    +---- 0 rows --> UPDATE reservation = REJECTED
    |                COMMIT rejection outcome
    |
    v
INSERT reservation lines
    |
    v
UPDATE reservation = HELD, expires_at = ...
    |
    v
COMMIT
```

If an unexpected error occurs before commit, rolling back undoes the stock update, reservation header, and reservation lines together.

### 6.1. Single-Product Reserve Transaction Example

SQL/PLSQL pseudocode:

```sql
-- Start transaction managed by caller.
INSERT INTO app.inventory_reservation (
    tenant_id,
    operation_name,
    idempotency_key,
    request_hash,
    reservation_status
)
VALUES (
    :tenant_id,
    'RESERVE_STOCK',
    :idempotency_key,
    :request_hash,
    'PROCESSING'
)
RETURNING reservation_id INTO :reservation_id;

UPDATE app.inventory_stock
SET reserved_qty = reserved_qty + :quantity,
    updated_at = SYSTIMESTAMP
WHERE warehouse_id = :warehouse_id
  AND product_id = :product_id
  AND on_hand_qty - reserved_qty >= :quantity;

-- Application/procedure checks rowcount.
-- If 0: update header to REJECTED and commit the outcome.
-- If 1: insert line, set HELD/expires_at and commit.
```

This is an illustrative sequence; `RETURNING ... INTO` must be executed in PL/SQL or an appropriate JDBC construct. When using JDBC, retrieve generated keys/sequences according to your driver and schema configuration.

### 6.2. Persisting Rejection Outcomes When Idempotency Requires Preserving Outcome

If a request with a given key is rejected due to insufficient stock, there are two semantics:

- **Deduplicate successes only:** roll back the request record when stock is insufficient; a subsequent retry with the same key after restocking can succeed.
- **Deduplicate all outcomes:** record `REJECTED` along with the response code in the transaction and commit the rejection; retries with the same key always return the same rejection.

The API must choose clear semantics. To preserve rejection outcomes, when the conditional `UPDATE` returns 0 rows, do not roll back the header; update `reservation_status='REJECTED'`, `result_code='INSUFFICIENT_STOCK'`, and commit. No stock modifications need to be undone.

If a multi-line order has already reserved some SKUs before a later SKU runs short, create a `SAVEPOINT` before the stock updates. When one line is insufficient, `ROLLBACK TO SAVEPOINT` to undo all stock/line changes while preserving the request header, transition it to `REJECTED`, and commit.

## 7. Idempotency Keys Against Duplicate Requests

A client may time out after the database commits but before receiving the response, and then retry the same request. If every call creates a new reservation, the system can double-reserve stock.

Use a stable idempotency key for each business intent:

```text
tenant_id       = 42
operation_name  = RESERVE_STOCK
idempotency_key = 8f3c... (UUID)
request_hash    = SHA-256 of canonicalized payload
```

Unique constraint:

```sql
UNIQUE (tenant_id, operation_name, idempotency_key)
```

### 7.1. Handling Duplicates

When inserting the header triggers `ORA-00001`:
1. Confirm the error came from the idempotency key unique constraint.
2. Fetch the existing reservation by tenant, operation, and key.
3. Compare `request_hash`.
4. If the hash differs, return a conflict error because the same key was reused with a different payload.
5. If the hash matches, return the stored status/outcome.
6. Do not re-run the conditional stock `UPDATE`.

Do not assume every `ORA-00001` is a duplicate request; another unique constraint could have been violated.

### 7.2. Two Concurrent Requests with the Same Key

The unique constraint acts as the synchronization point in the database. The second request may block on the unique index until the first transaction finishes:

- If the first transaction commits, the second receives a duplicate-key error and reads the stored outcome.
- If the first transaction rolls back, the second can insert the key and become the active handler.
- Two reservations can never commit for the same scoped key.

Never rely solely on a `SELECT` check before inserting; that introduces a race condition.

### 7.3. Payload Hashing

Compute the hash over a canonicalized payload:
- Line items sorted in canonical order.
- Quantities converted to standard units.
- All semantically meaningful fields included in the hash.
- Transient fields that do not affect business intent (such as request timestamp or trace ID) excluded.
- Never hash a raw JSON string with arbitrary property ordering without canonicalization.

Reusing the same key with a different product, warehouse, or quantity must be rejected.

## 8. Oracle Concurrency and Row-Level Locking

Oracle defaults to `READ COMMITTED` unless the isolation level is changed. Each statement reads a consistent snapshot as of statement start. DML locks modified rows, forcing other transactions attempting to modify the same row to wait.

### 8.1. Contending on the Same Inventory Row

If two transactions reserve the same product/warehouse simultaneously:
- The first transaction acquires the row lock via `UPDATE`.
- The second transaction waits.
- After the first commits or rolls back, the second resumes.
- The `UPDATE` predicate determines whether sufficient available quantity remains.

This protects invariants at the stock row level without locking the entire table.

### 8.2. SELECT FOR UPDATE

When business logic needs to inspect multiple columns, evaluate extra conditions, and then update, lock the row upfront:

```sql
SELECT on_hand_qty,
       reserved_qty
FROM app.inventory_stock
WHERE warehouse_id = :warehouse_id
  AND product_id = :product_id
FOR UPDATE;
```

Once the lock is held, compute available stock and update within the same transaction. However, for straightforward reservations, a conditional `UPDATE` is more concise and avoids an extra round-trip.

### 8.3. NOWAIT, WAIT, and SKIP LOCKED

Oracle supports locking clauses:
- `FOR UPDATE NOWAIT`: fail immediately if the row is locked.
- `FOR UPDATE WAIT n`: wait at most `n` seconds.
- `FOR UPDATE SKIP LOCKED`: skip rows locked by other sessions, useful when multiple workers claim jobs from a queue.

Example:

```sql
SELECT reservation_id
FROM app.inventory_reservation
WHERE reservation_status = 'HELD'
  AND expires_at <= SYSTIMESTAMP
FOR UPDATE SKIP LOCKED;
```

Workers can process expired reservations not currently locked by another worker. Limit batch sizes and lock durations; never hold thousands of row locks inside a long-running transaction.

`SKIP LOCKED` is suited for queue/worker claiming, not as a replacement for conditional stock `UPDATE`s.

### 8.4. When to Use SERIALIZABLE?

`SERIALIZABLE` isolation may fit workflows requiring transaction-level snapshot semantics, but it can raise `ORA-08177` when a transaction cannot be serialized. On that error, roll back and consider bounded full-transaction retries.

Do not elevate all reservation transactions to `SERIALIZABLE` as a blanket fix for race conditions. Conditional DML and row-level locks are generally better suited for per-SKU inventory counts.

## 9. Multi-Product Orders

A reservation can contain multiple SKUs. If SKU A succeeds but SKU B lacks stock, business rules usually demand all-or-nothing.

Use a single transaction:
1. Normalize and merge duplicate SKU lines.
2. Sort by key `(warehouse_id, product_id)`.
3. Execute conditional `UPDATE` for each line in deterministic order.
4. If any line is insufficient, roll back to the savepoint placed before stock updates.
5. Record `REJECTED` and commit the header if rejection idempotency is desired.
6. If all lines succeed, insert reservation lines, set header to `HELD`, and commit.

### 9.1. Lock Ordering

All multi-SKU flows must lock and update stock rows in the exact same order, such as ascending `warehouse_id`, then `product_id`.

If transaction A locks SKU 10 then SKU 20 while transaction B locks SKU 20 then SKU 10, the two transactions can deadlock.

Consistent lock ordering reduces deadlock risk. On `ORA-00060`, roll back the entire business transaction; retry only if the operation is idempotent and still within its deadline.

### 9.2. All-or-Nothing

Never commit individual SKUs within a single order if the business requires full-order reservation. Per-line commits create partial states and force the application to build compensating sagas.

If the system intentionally supports partial fulfillment, model per-line outcomes and order states explicitly; never allow partial success by accident.

## 10. Reservation State Machine

A reservation should have clearly defined states and transitions:

```text
             +--------------------+
             |                    v
NEW/PROCESSING ---> HELD ------> CONFIRMED
                     |               |
                     +--> RELEASED  |
                     |               |
                     +--> EXPIRED   |
                                     v
                              (stock consumed)
```

Example state meanings:

| State | Meaning | `reserved_qty` |
|---|---|---|
| PROCESSING | Request is inside an uncommitted transaction | Not externally observable |
| HELD | Stock is held until `expires_at` | Increased |
| REJECTED | Insufficient stock or request rejected | Unchanged |
| CONFIRMED | Transaction confirmed and stock consumed in this model | Decreased alongside `on_hand_qty` |
| RELEASED | User/system cancelled the hold | Decreased |
| EXPIRED | TTL elapsed and worker released hold | Decreased |

If `CONFIRMED` only means the order is accepted but not yet shipped, retain `reserved_qty` and introduce an `ALLOCATED`/`FULFILLING` state; decrement `on_hand_qty` only when shipment physically leaves the warehouse. The state machine must match accounting and warehouse definitions.

### 10.1. Conditional State Transitions

Never do:

```sql
UPDATE app.inventory_reservation
SET reservation_status = 'RELEASED'
WHERE reservation_id = :id;
```

That statement could overwrite an already `CONFIRMED` reservation with `RELEASED`, even though stock was already consumed.

Lock the header or update conditionally on the expected prior status:

```sql
UPDATE app.inventory_reservation
SET reservation_status = 'RELEASED',
    completed_at = SYSTIMESTAMP
WHERE reservation_id = :reservation_id
  AND reservation_status = 'HELD';
```

Release stock in the same transaction only when `SQL%ROWCOUNT = 1`. For complex flows, lock the header with `FOR UPDATE`, inspect its state, and perform controlled transitions.

### 10.2. Idempotent Transitions

If a release request arrives twice:
- The first call transitions `HELD` → `RELEASED` and decrements `reserved_qty`.
- The second call sees it is already `RELEASED` and returns the current state without decrementing `reserved_qty` again.

The same principle applies to confirm and expire. Each transition may apply at most once against a locked reservation header.

## 11. Confirming Reservations and Consuming Inventory

In a model where `CONFIRMED` means sold/consumed stock, the transaction must:
1. Lock the reservation header.
2. Verify current status is `HELD`.
3. Verify it has not expired according to the database clock.
4. Read reservation lines.
5. Update stock rows in deterministic lock order.
6. Decrement both `on_hand_qty` and `reserved_qty`.
7. Transition the header to `CONFIRMED`.
8. Commit.

Single-line example:

```sql
UPDATE app.inventory_stock
SET on_hand_qty = on_hand_qty - :quantity,
    reserved_qty = reserved_qty - :quantity,
    updated_at = SYSTIMESTAMP
WHERE warehouse_id = :warehouse_id
  AND product_id = :product_id
  AND on_hand_qty >= :quantity
  AND reserved_qty >= :quantity;
```

`SQL%ROWCOUNT` must equal 1. If not, an invariant was violated or data was modified by a non-compliant write path; roll back and investigate. Never ignore the mismatch and still mark the header `CONFIRMED`.

If order confirmation only moves from held to allocated without shipping yet, do not decrement `on_hand_qty` until physical dispatch; adjust the state machine and SQL accordingly.

## 12. Releasing, Cancelling, and Expiring Reservations

### 12.1. Manual Release

When a user cancels:
- Lock the reservation header.
- If status is not `HELD`, return the current state or reject the invalid transition.
- For each line, decrement `reserved_qty`.
- Transition header to `RELEASED`.
- Commit within the same transaction.

```sql
UPDATE app.inventory_stock
SET reserved_qty = reserved_qty - :quantity,
    updated_at = SYSTIMESTAMP
WHERE warehouse_id = :warehouse_id
  AND product_id = :product_id
  AND reserved_qty >= :quantity;
```

If rowcount is not 1, roll back and report an inconsistency. Never allow `reserved_qty` to go negative.

### 12.2. Expiration Using the Database Clock

When creating a reservation, compute expiry using the database clock:

```sql
SYSTIMESTAMP + NUMTODSINTERVAL(:ttl_seconds, 'SECOND')
```

Using `SYSTIMESTAMP` and `TIMESTAMP WITH TIME ZONE` avoids dependence on JVM clocks or session time zones. Do not pass locale-formatted expiry strings.

### 12.3. Expiry Worker

The worker locates expired `HELD` reservations, locks them with `FOR UPDATE SKIP LOCKED`, then releases stock and sets status to `EXPIRED` in the same transaction.

Workflow:
1. Select an expired reservation and lock its header.
2. Re-verify status and `expires_at <= SYSTIMESTAMP`.
3. Read its lines.
4. Decrement `reserved_qty` for each stock row in standard lock order.
5. Transition header to `EXPIRED`.
6. Commit.
7. Repeat in small batches.

Use `SKIP LOCKED` so multiple workers do not contend on the same header. Process one reservation or a bounded batch at a time to avoid long transactions and excessive row locks.

### 12.4. Confirm vs. Expire Race

Confirm and expire can arrive simultaneously. Both must lock the same reservation header first. Whichever acquires the lock first checks status/time and executes the transition; the other waits and reads the updated state.

- If confirm wins before expiry, the expiry worker sees `CONFIRMED` and skips release.
- If expire wins after expiry, confirm sees `EXPIRED` and does not consume stock.
- Never allow both to decrement `reserved_qty`.

This guarantee holds only if every transition path follows the same locking and state protocol.

## 13. Lock Ordering and Deadlocks

Oracle uses row-level locks; deadlocks occur when two transactions hold different locks and wait on each other.

Example:
- T1 locks stock A, then waits for stock B.
- T2 locks stock B, then waits for stock A.

Oracle detects the deadlock and raises `ORA-00060` to one of the statements. The application must roll back the entire business transaction, not just retry the last SQL statement.

Mitigations:
- Always sort stock keys in the same deterministic order.
- Keep transactions short.
- Never invoke HTTP/payment/email APIs while holding row locks.
- Never wait on user input inside a transaction.
- Index predicates and foreign keys appropriately.
- Lock no more rows than necessary.
- Implement bounded retries with backoff and jitter for deadlocks when the operation is idempotent.

Do not reflexively increase `INITRANS` or change isolation levels upon seeing a deadlock; inspect the lock wait graph in trace/monitoring first.

## 14. Optimistic Locking and Version Columns

For administrative screens or metadata edits, optimistic locking can fit better than long pessimistic locks.

Add a version column:

```sql
ALTER TABLE app.inventory_stock
ADD version_no NUMBER(18,0) DEFAULT 0 NOT NULL;
```

Update:

```sql
UPDATE app.inventory_stock
SET reserved_qty = reserved_qty + :quantity,
    version_no = version_no + 1,
    updated_at = SYSTIMESTAMP
WHERE warehouse_id = :warehouse_id
  AND product_id = :product_id
  AND version_no = :expected_version
  AND on_hand_qty - reserved_qty >= :quantity;
```

If rowcount is 0, either the row changed concurrently or stock is insufficient. The application can re-read and decide whether to retry. A version column does not replace the available-quantity predicate; both are needed to protect invariants.

For hot reservations on a single SKU, an atomic conditional `UPDATE` is usually simpler and sufficient. Optimistic locking is helpful for detecting stale UI edits or metadata updates.

## 15. Transactions in Spring/JDBC/JPA

All reserve steps must run inside a single database transaction:

```java
@Transactional
public ReservationResult reserve(ReserveCommand command) {
    // 1. Claim idempotency key.
    // 2. Conditional UPDATE inventory.
    // 3. Insert reservation lines.
    // 4. Update header to HELD or REJECTED.
    // 5. Return result; Spring commits when the method exits.
}
```

### 15.1. Using the Same Transaction-Bound Connection

When mixing JPA and JDBC:
- `JpaTransactionManager` must manage the exact same `DataSource`.
- `JdbcTemplate` must use that same `DataSource`.
- Never open a standalone connection via `DriverManager`.
- Native SQL or `JdbcTemplate` calls must enlist in the active transaction.

If the stock update runs on connection A while the reservation insert runs on connection B, the two operations are no longer atomic.

### 15.2. Flush Behavior and Isolation

JPA may defer DML until flush time. For reservation logic that needs an immediate rowcount, use JDBC/native queries with explicit rowcounts or flush at the appropriate point.

Oracle's default `READ COMMITTED` is typically ideal for conditional `UPDATE`s. If using `SERIALIZABLE`, handle `ORA-08177` by rolling back and retrying the entire transaction.

### 15.3. Rollback Policy

When one SKU in a multi-line reservation is short:
- Roll back prior stock changes to the savepoint.
- Persist `REJECTED` if idempotency semantics require storing rejections.
- Commit the header rejection.

On unexpected technical errors:
- Roll back the entire transaction.
- Never leave a committed `PROCESSING` header.
- If the connection drops around `COMMIT`, the outcome is ambiguous; look up the idempotency key over a fresh connection before retrying.

## 16. Tracking Inventory with a Ledger

The `on_hand_qty` and `reserved_qty` columns represent current balances for fast lookups. For auditable systems, also record an inventory movement ledger:

- RECEIPT: stock received.
- RESERVE: stock held.
- RELEASE: hold released.
- CONSUME: stock shipped/consumed.
- ADJUSTMENT: cycle count/adjustment.
- TRANSFER_OUT/TRANSFER_IN: inter-warehouse transfer.

Each movement carries a business reference and a unique event/request ID to prevent duplicate entries.

Update both the ledger and aggregate stock inside the same transaction. If the ledger insert succeeds while the aggregate update fails (or vice versa), roll back both.

Never replace row locks/conditional updates with a ledger alone; the ledger is the audit history, while the stock row is the synchronization point governing allocatable supply.

## 17. Reconciling Invariants and Reservations

Compare `reserved_qty` against the total quantity of `HELD` reservations:

```sql
SELECT s.warehouse_id,
       s.product_id,
       s.reserved_qty,
       NVL(SUM(
           CASE
             WHEN r.reservation_status = 'HELD'
             THEN l.quantity
             ELSE 0
           END
       ), 0) AS held_line_qty
FROM app.inventory_stock s
LEFT JOIN app.inventory_reservation_line l
  ON l.warehouse_id = s.warehouse_id
 AND l.product_id = s.product_id
LEFT JOIN app.inventory_reservation r
  ON r.reservation_id = l.reservation_id
GROUP BY s.warehouse_id,
         s.product_id,
         s.reserved_qty
HAVING s.reserved_qty <> NVL(SUM(
           CASE
             WHEN r.reservation_status = 'HELD'
             THEN l.quantity
             ELSE 0
           END
       ), 0);
```

This query returns stock rows whose `reserved_qty` mismatches the sum of `HELD` reservations. Run it on an appropriate snapshot and consider workload; large tables may need batched or partition-aware reconciliation.

Also check invariants directly:

```sql
SELECT warehouse_id,
       product_id,
       on_hand_qty,
       reserved_qty,
       on_hand_qty - reserved_qty AS available_qty
FROM app.inventory_stock
WHERE on_hand_qty < 0
   OR reserved_qty < 0
   OR reserved_qty > on_hand_qty;
```

Constraints should prevent these cases during normal operation. Reconciliation queries detect legacy data, bypasses, or application bugs.

Never auto-correct `reserved_qty` from query results without identifying root cause and creating an audit trail. Adjustments require movement records and business approval.

## 18. Verifying Concurrent Transactions

Unit tests that mock repositories do not prove Oracle locking behaves as expected. You need integration tests against Oracle Database using multiple independent connections/sessions.

### 18.1. Oversell Scenario

Setup:
- `on_hand_qty = 100`.
- `reserved_qty = 0`.
- 100 concurrent requests.
- Each request reserves 2 units.
- Each request has a distinct idempotency key.

Expected outcome:
- At most 50 requests succeed.
- Total `HELD` reservations equal 100.
- `reserved_qty = 100`.
- `available_qty = 0`.
- No negative stock and no `reserved_qty` exceeding `on_hand_qty`.
- Remaining requests receive `REJECTED/INSUFFICIENT_STOCK`.

There is no requirement on which specific requests win; only that invariants hold.

### 18.2. Same Idempotency Key Scenario

Send 20 concurrent requests with:
- Same tenant.
- Same operation.
- Same idempotency key.
- Same payload/hash.

Expected:
- Only one reservation header is committed.
- Only one set of reservation lines exists.
- `reserved_qty` increments only once.
- Remaining callers receive the stored result.

Then send the same key with a different quantity. Expect a conflict error with no stock changes.

### 18.3. Multi-SKU All-or-Nothing Scenario

Submit a request where SKU A has sufficient stock and SKU B is short. Expected:
- Request is `REJECTED`.
- SKU A is not partially reserved.
- SKU B is unchanged.
- No partial `HELD` reservation lines exist.
- If rejections are stored idempotently, retrying with the same key returns the same rejection.

### 18.4. Confirm vs. Expire Contention Scenario

Create a soon-to-expire reservation and run confirm and the expiry worker nearly simultaneously. Expected:
- Only one transition succeeds.
- `reserved_qty` decreases exactly once (either consumed by confirm or released by expire).
- The reservation cannot become both `CONFIRMED` and `EXPIRED`.
- Stock invariants hold.

### 18.5. Repeated Release Scenario

Send two release commands for the same reservation. Expected:
- Only one command decrements `reserved_qty`.
- The second returns the current `RELEASED` state.
- `reserved_qty` never goes negative.

## 19. Java Concurrency Testing Example

Tests must give each worker its own connection and transaction. Never share a single `Connection`, `EntityManager`, or transaction across threads.

Pseudocode using `ExecutorService` and `CountDownLatch`:

```java
int workers = 100;
ExecutorService executor = Executors.newFixedThreadPool(workers);
CountDownLatch ready = new CountDownLatch(workers);
CountDownLatch start = new CountDownLatch(1);

List<Future<ReservationResult>> futures = new ArrayList<>();

for (int i = 0; i < workers; i++) {
    final int requestNo = i;

    futures.add(executor.submit(() -> {
        ready.countDown();
        start.await();

        // reserve() opens a dedicated transaction/connection for this worker.
        return reservationService.reserve(
            new ReserveCommand(
                tenantId,
                "req-" + requestNo,
                warehouseId,
                productId,
                new BigDecimal("2")
            )
        );
    }));
}

ready.await();
start.countDown();

int success = 0;
for (Future<ReservationResult> future : futures) {
    if (future.get().isHeld()) {
        success++;
    }
}

executor.shutdown();
```

This is a test harness skeleton, not complete production code. Configure the connection pool large enough to create real contention while staying within lab database session limits. If the pool has only one connection, the test runs largely sequentially and does not verify concurrency contention.

Do not spawn 100 threads if the database only permits a small number of sessions. Tune concurrency to match your test environment.

### 19.1. Post-Test Assertions

```sql
SELECT on_hand_qty,
       reserved_qty,
       on_hand_qty - reserved_qty AS available_qty
FROM app.inventory_stock
WHERE warehouse_id = :warehouse_id
  AND product_id = :product_id;
```

Verify:
- `reserved_qty <= on_hand_qty`.
- `reserved_qty` equals the sum of `HELD` lines.
- Count of `HELD` reservations matches the successful request count.
- Every request key is unique.
- No committed `PROCESSING` records exist in synchronous mode.

## 20. Fault Injection and Recovery

Beyond normal contention, test failures at transaction boundaries:

1. Process crashes after stock `UPDATE` but before line `INSERT`.
2. Process crashes after line inserts but before `COMMIT`.
3. Connection drops during `COMMIT`.
4. Client times out after `COMMIT` but before receiving the response.
5. Expiry worker crashes before `COMMIT`.
6. Two expiry workers pick up the same batch.
7. Deadlock in a multi-SKU request.
8. A stock row is deleted or missing.
9. Same key submitted with a different payload hash.

Expected outcomes:
- Uncommitted transactions roll back both stock and reservation changes.
- If commit succeeded but the response was lost, retrying with the same key returns the stored outcome.
- Expiry workers can re-run safely without double-releasing stock.
- On deadlock, roll back and retry the entire transaction with the same key.
- No partial states exist outside the state machine.

When a commit outcome is unknown, never generate a new key. Query the reservation by idempotency key over a new connection and determine its status before deciding to retry.

## 21. Performance and Operations

### 21.1. Hot Rows

A highly popular product in a single warehouse can become a hot row. Every reservation updates the same stock row, serializing transactions on that row.

This is the inherent cost of protecting a shared balance. Contention can be reduced by:
- Splitting stock by warehouse/bin/location when genuinely meaningful to the business.
- Partitioning stock into shards/buckets if clear aggregation rules and invariants exist.
- Minimizing transaction duration.
- Never calling external services while holding locks.
- Using reasonable batch sizes.
- Keeping read models/caches off the authoritative reserve path.

Never split a balance arbitrarily into buckets if cross-bucket aggregation could oversell or complicate reconciliation.

### 21.2. Lock Wait and Deadlock Metrics

Monitor:
- Requests waiting on row locks.
- Reserve latency p95/p99.
- `ORA-00060` deadlocks.
- `ORA-08177` errors if using serializable isolation.
- Insufficient stock rejections.
- Duplicate idempotency hits.
- Expired reservations.
- Expiry worker lag.
- Reconciliation discrepancies.
- Hot products/warehouses.

Distinguish genuine stockouts from lock-wait timeouts. Never return `INSUFFICIENT_STOCK` merely due to a lock-wait timeout when actual stock status is undetermined.

### 21.3. Retention and Cleanup

Completed reservations can be retained for auditing and idempotency. Do not purge idempotency keys prematurely while clients may still retry. Retention must exceed the retry window and meet audit requirements.

High-volume request tables can be partitioned/archived by time, provided unique constraints and partitioning keys remain compatible with uniqueness guarantees. Partition design must not break the uniqueness scope of idempotency keys.

### 21.4. Inventory Ledger and Reconciliation

Run periodic reconciliations:
- Aggregate stock versus movement ledger.
- `reserved_qty` versus total `HELD` reservations.
- `HELD` reservations past `expires_at` not yet expired.
- Terminal reservations with lines mistakenly counted.
- Negative available quantity.
- Stock movements with duplicate business references.

Alert whenever discrepancies exceed zero; adjustments must include an audit trail.

## 22. Common Anti-Patterns

| Anti-Pattern | Consequence | Fix |
|---|---|---|
| `SELECT` available then decide in Java | Race condition, overselling | Conditional `UPDATE` |
| Relying only on `synchronized` | Fails across multiple JVMs/pods | Synchronize in Oracle |
| Incrementing `reserved` and committing, then inserting reservation later | Risk of orphaned stock holds | Same transaction |
| Inserting `HELD` and committing before incrementing `reserved` | Reservation not backed by stock | Same transaction |
| Missing unique idempotency key | Retries create duplicate reservations | Unique constraint and request hash |
| Returning old result for same key with different payload | Request identity abuse | Compare payload hash |
| Releasing without checking status | Decrements `reserved` multiple times | Conditional state transition |
| Expire and confirm not locking the same header | Both can process the same hold | Lock header, inspect state |
| Committing per SKU in an all-or-nothing order | Partial reservation | Single transaction/savepoint |
| Locking SKUs in arbitrary order | Deadlocks | Deterministic lock ordering |
| Holding locks across payment/HTTP calls | Long lock holds, high contention | Isolate external side effects |
| Retrying only the last statement after deadlock | Inconsistent transaction state | Roll back/retry entire transaction |
| Using cache as reserve source of truth | Stale cache, overselling | Database conditional DML |
| Purging idempotency records too early | Late retries create duplicate orders | Retain per retry/audit window |
| Treating timeout as rollback | May create a second reservation | Resolve outcome by key |
| Not testing against real Oracle | Misses real locking semantics | Integration/concurrency tests |

## 23. Implementation Checklist

### Data Model
- Defined `on_hand`, `reserved`, and `available`.
- Quantities use appropriate precision and scale.
- Check constraints enforce invariants.
- Reservation header enforces unique idempotency scope.
- Payload hash column present.
- Line table and foreign keys defined.
- Indexes exist for expiry and reconciliation queries.

### Transactions
- Conditional `UPDATE` is the reserve decision point.
- Stock and reservation share the same transaction.
- Multi-SKU uses all-or-nothing when required by business rules.
- Savepoint/rollback policy defined for rejected requests.
- Deterministic lock ordering enforced.
- Unknown commit outcomes resolved using the same idempotency key.

### Lifecycle
- State transitions formally defined.
- Confirm/release/expire only act on `HELD`.
- Every transition locks the header first.
- Expiry uses the database clock.
- Workers use `SKIP LOCKED` with bounded batches.
- Repeated release/expire never double-decrements stock.

### Verification
- Multi-connection oversell test implemented.
- Same-key concurrency test implemented.
- Multi-SKU all-or-nothing test implemented.
- Confirm-vs-expire contention test implemented.
- Rollback/fault injection tests implemented.
- Post-test reconciliation automated.
- Hot-SKU performance test executed.

### Operations
- Lock wait, deadlock, expiry, and duplicate metrics tracked.
- Retention and archiving policies defined.
- Audit movement ledger maintained.
- Reconciliation alerts configured.
- Runbooks prepared for inconsistencies and commit ambiguity.

## 24. Integrated Hands-On Lab

Use a dedicated lab schema and database. Never run oversell tests against production inventory data.

### Step 1. Create the Stock Table

Create `APP.INVENTORY_STOCK` with primary key `(WAREHOUSE_ID, PRODUCT_ID)`, `ON_HAND_QTY`, `RESERVED_QTY`, and check constraints.

### Step 2. Seed Initial Stock

For example, seed one SKU with 100 units:

```sql
INSERT INTO app.inventory_stock (
    warehouse_id, product_id, on_hand_qty, reserved_qty
)
VALUES (1, 1001, 100, 0);

COMMIT;
```

### Step 3. Create Reservation Header and Line Tables

Define the unique key on `(TENANT_ID, OPERATION_NAME, IDEMPOTENCY_KEY)`, request hash, status, and expiry.

### Step 4. Implement the Reserve Transaction

Implement:
1. Insert `PROCESSING` request header.
2. Execute conditional stock `UPDATE`.
3. If insufficient, record `REJECTED` per chosen semantics.
4. If sufficient, insert lines and transition to `HELD`.
5. Commit once.

### Step 5. Send Sequential Requests

Reserve 10 units and verify:
- Stock `reserved_qty` increases by 10.
- Reservation header is `HELD`.
- Reservation line records the exact quantity.
- Available stock decreases by 10.

### Step 6. Resend the Same Idempotency Key

Resend the exact same payload. Verify `reserved_qty` does not increase further.

### Step 7. Send the Same Key with a Different Payload

Change quantity or product. Verify the API returns a conflict and stock remains unchanged.

### Step 8. Run the Concurrency Test

Reset lab stock to 100. Run 100 concurrent requests, 2 units each, over separate connections. Verify at most 50 requests become `HELD`.

### Step 9. Test Multi-SKU

Submit a request with two SKUs where the second SKU lacks stock. Verify the first SKU is not partially reserved.

### Step 10. Test Lifecycle Transitions

Test confirm, double release, expiry, and confirm-vs-expire contention. Verify each reservation transitions validly at most once.

### Step 11. Run Reconciliation

Compare `reserved_qty` with total `HELD` reservation quantities. Verify zero discrepancy.

### Step 12. Record Evidence and Clean Up Lab

Save request counts, success/rejection counts, lock-wait timings, final state, and reconciliation query output. Drop lab objects only after verification is complete.

## 25. Self-Check Questions

**Question 1.** Why can `SELECT` available followed by `UPDATE` in Java cause overselling?

**Answer:** Multiple transactions can read the same snapshot before any transaction updates it; check and update are not atomic.

**Question 2.** Which SQL statement is the authoritative reserve decision point?

**Answer:** The conditional `UPDATE` incrementing `reserved_qty` with `on_hand_qty - reserved_qty >= requested_qty`.

**Question 3.** Why must we inspect `SQL%ROWCOUNT`?

**Answer:** One row means the reservation succeeded; zero rows means no matching stock row or insufficient available quantity.

**Question 4.** Why must the stock update and reservation insert run in the same transaction?

**Answer:** To prevent cases where stock is held without a reservation or a reservation exists without reserved stock.

**Question 5.** What does an idempotency key protect against?

**Answer:** Identifying retries of the same business intent so duplicate reservations are not created.

**Question 6.** Why is a request hash needed?

**Answer:** To detect reuse of the same key with a different payload and reject invalid reuse.

**Question 7.** Which race condition does the unique constraint solve?

**Answer:** Preventing multiple transactions from committing requests with the same tenant/operation/idempotency key.

**Question 8.** Why is `synchronized` in Java insufficient?

**Answer:** It only synchronizes within a single JVM/object, providing no protection across processes, pods, or batch clients.

**Question 9.** When should `SELECT FOR UPDATE` be used?

**Answer:** When you must lock a row before reading multiple attributes and executing complex logic in the same transaction.

**Question 10.** When is `SKIP LOCKED` appropriate?

**Answer:** When multiple workers claim distinct reservations/jobs from a queue without waiting on rows locked by other workers.

**Question 11.** Why do multi-SKU orders require lock ordering?

**Answer:** Ensuring every transaction locks rows in the same order reduces wait cycles and deadlocks.

**Question 12.** What should you do on `ORA-00060`?

**Answer:** Roll back the entire business transaction; retry the whole transaction only if the operation is idempotent and within its deadline.

**Question 13.** What must happen when release is called twice?

**Answer:** Only the first call transitions `HELD` to `RELEASED` and decrements `reserved`; the second returns the current state without further decrement.

**Question 14.** Why must confirm and expire lock the same reservation header?

**Answer:** So only one transition wins, preventing stock from being both consumed and released.

**Question 15.** Why use `SYSTIMESTAMP` for expiry?

**Answer:** So expiration is evaluated against the database clock, avoiding clock skew across application instances.

**Question 16.** When can `SERIALIZABLE` raise `ORA-08177`?

**Answer:** When a transaction cannot be serialized because underlying rows were modified by another transaction under isolation rules.

**Question 17.** Why must a cache never make the final reserve decision?

**Answer:** Caches can be stale; the conditional `UPDATE` on the stock row is the final synchronization point.

**Question 18.** Which test proves there is no overselling?

**Answer:** Running multiple independent transactions concurrently reserving a finite stock quantity, then verifying total `HELD` quantities, `reserved_qty`, and invariants.

## 26. Conclusion

Inventory reservation is a concurrency and consistency problem, not just arithmetic subtraction. Clearly define `on_hand_qty`, `reserved_qty`, and `available_qty`, enforce invariants with check constraints, and execute holds using conditional `UPDATE`s. Oracle row-level locking serializes concurrent modifications to the same stock row, allowing subsequent transactions to succeed only if available stock remains sufficient.

Stock updates, reservation headers/lines, and idempotency outcomes must commit together. A unique key scoped by tenant/operation/request combined with a payload hash prevents retries from duplicating holds. Confirm, release, and expire must follow a strict state machine, lock the reservation header, update stock within the same transaction, and ensure each transition takes effect at most once. For multi-SKU orders, apply all-or-nothing semantics when required and enforce deterministic lock ordering to minimize deadlocks.

Verify with multiple independent connections and transactions on a real Oracle instance: test overselling, identical idempotency keys, payload conflicts, multi-SKU requests, confirm-vs-expire races, rollbacks, and failures around `COMMIT`. Afterward, reconcile `reserved_qty` against total `HELD` reservations and monitor lock waits, deadlocks, expiry lag, and hot-row contention. Only when every write path obeys the same invariants and transaction protocol can a system safely reserve inventory under concurrent load.
