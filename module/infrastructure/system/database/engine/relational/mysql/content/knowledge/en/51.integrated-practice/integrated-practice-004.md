# Designing Inventory Reservations and Verifying Multi-Session Concurrency

A store has 10 units of a product in stock. Two customers nearly simultaneously place orders for 7 units each. If both requests read the available count of 10, check that stock is sufficient, and then update the table, the system could confirm 14 units even though the warehouse only holds 10. This is an overselling bug caused by an unprotected read–check–write sequence lacking proper concurrency control.

This lesson belongs to the **Integrated Practice** chapter of the **DATABASE_MYSQL** module. In the MySQL mastery track covering table design, data types, keys, SQL queries, indexes, transactions, concurrency control, execution plan inspection, query optimization, privileges, backups, and operations, this lab combines schema design, data constraints, InnoDB transactions, row locking, idempotency, and multi-session testing. The goal is to build a reservation flow resilient to concurrent requests, retries, and expiration jobs without letting available stock go negative.

## 1. Business Model and Invariants

Before writing SQL, define the quantities:

- **on_hand_qty:** physical quantity currently in the warehouse.
- **reserved_qty:** quantity currently held for unconfirmed orders.
- **available_qty:** quantity still available to reserve, calculated as `on_hand_qty` minus `reserved_qty`.
- **reservation:** a reservation record linked to a unique request, warehouse, SKU, quantity, and expiration time.
- **request_key:** an application-generated idempotency key for each reservation request.

Invariants that must always hold:

~~~text
on_hand_qty >= 0
reserved_qty >= 0
reserved_qty <= on_hand_qty
available_qty = on_hand_qty - reserved_qty
quantity of each reservation > 0
reserved_qty = sum of quantity across all RESERVED reservations
~~~

The final invariant links the aggregated counter in the `inventory` table to the individual `reservation` records. MySQL can enforce per-row bounds via CHECK constraints, yet cannot use a standard CHECK constraint to compare against a sum from another table. The application must update both `inventory` and `reservation` within the same transaction; periodic reconciliation detects discrepancies caused by operational mistakes or out-of-band data edits.

A reservation has the following states:

| Status | Meaning | Impact on reserved_qty |
|---|---|---:|
| RESERVED | Stock currently held, not yet confirmed | Adds quantity |
| CONFIRMED | Order confirmed, stock deducted from available inventory | Subtracts quantity from both on_hand_qty and reserved_qty |
| RELEASED | Reservation cancelled | Subtracts quantity from reserved_qty |
| EXPIRED | Timed out and released | Subtracts quantity from reserved_qty |

Never transition a state back to RESERVED after it becomes RELEASED or EXPIRED. If the customer places another order, create a new reservation with a new request key. Retaining status history simplifies auditing and retry investigations.

## 2. Designing the `inventory` and `reservations` Tables

The `inventory` table stores one row per `(warehouse, SKU)` pair. A composite primary key guarantees a single stock counter per item in each warehouse.

~~~sql
CREATE TABLE inventory (
  warehouse_id BIGINT UNSIGNED NOT NULL,
  sku VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  on_hand_qty BIGINT UNSIGNED NOT NULL DEFAULT 0,
  reserved_qty BIGINT UNSIGNED NOT NULL DEFAULT 0,
  PRIMARY KEY (warehouse_id, sku),
  CONSTRAINT chk_inventory_reserved
    CHECK (reserved_qty <= on_hand_qty)
) ENGINE=InnoDB;
~~~

The quantity columns use `UNSIGNED` to prevent negative numbers. CHECK constraints are enforced starting in MySQL 8.0.16; if running an older version, do not rely on CHECK—protect the invariant inside your `UPDATE` statements and write logic, and upgrade when feasible.

The reservation table stores each individual hold:

~~~sql
CREATE TABLE inventory_reservations (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  request_key VARCHAR(64)
    CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  order_id BIGINT UNSIGNED NOT NULL,
  warehouse_id BIGINT UNSIGNED NOT NULL,
  sku VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  quantity BIGINT UNSIGNED NOT NULL,
  status VARCHAR(16)
    CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  created_at DATETIME(6) NOT NULL,
  expires_at DATETIME(6) NOT NULL,
  confirmed_at DATETIME(6) NULL,
  released_at DATETIME(6) NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_reservation_request (request_key),
  KEY ix_reservation_expiry (status, expires_at, id),
  KEY ix_reservation_order (order_id),
  KEY ix_reservation_inventory (warehouse_id, sku),
  CONSTRAINT chk_reservation_quantity CHECK (quantity > 0),
  CONSTRAINT chk_reservation_status
    CHECK (status IN ('RESERVED', 'CONFIRMED', 'RELEASED', 'EXPIRED')),
  CONSTRAINT fk_reservation_inventory
    FOREIGN KEY (warehouse_id, sku)
    REFERENCES inventory (warehouse_id, sku)
    ON UPDATE RESTRICT
    ON DELETE RESTRICT
) ENGINE=InnoDB;
~~~

`request_key` uses a binary collation so the idempotency key strictly distinguishes letter case. The data type and collation of `sku` must match across both tables for the foreign key to be valid. If SKUs follow different case rules, choose the charset/collation per business requirements and apply it consistently to both tables.

Because the foreign key uses `ON DELETE RESTRICT` and reservations are kept for auditing, do not physically delete `inventory` rows while referencing reservation history exists. If a SKU is discontinued, mark it inactive in the production schema or archive historical records through a controlled process before removing inventory rows.

Index `ix_reservation_expiry(status, expires_at, id)` helps the expiration worker find timed-out reservations. The order index supports looking up reservations by order. The warehouse/SKU index supports inventory queries and reconciliation.

The `inventory` table stores the `reserved_qty` counter for fast availability checks, while the reservations table stores per-request details. Because this is redundant aggregated state maintained alongside detail rows, every creation, confirmation, cancellation, and expiration flow must update both tables inside the same transaction. Never update just one table via an operational script without a reconciliation process.

## 3. Preparing Test Data

Create two items in the warehouse:

~~~sql
INSERT INTO inventory
  (warehouse_id, sku, on_hand_qty, reserved_qty)
VALUES
  (1, 'SKU-CHAIR', 10, 0),
  (1, 'SKU-DESK', 5, 0);
~~~

Check available quantities:

~~~sql
SELECT
  warehouse_id,
  sku,
  on_hand_qty,
  reserved_qty,
  on_hand_qty - reserved_qty AS available_qty
FROM inventory
ORDER BY warehouse_id, sku;
~~~

Initial state:

| Warehouse | SKU | On hand | Reserved | Available |
|---:|---|---:|---:|---:|
| 1 | SKU-CHAIR | 10 | 0 | 10 |
| 1 | SKU-DESK | 5 | 0 | 5 |

Suppose the application receives requests to reserve 7 chairs for two different orders. Each request carries a unique `request_key` and holds stock for 15 minutes. Use `DATETIME(6)` storing UTC by convention; generate and compare expiration timestamps with `UTC_TIMESTAMP(6)` to avoid session timezone dependencies.

## 4. Creating a Reservation Inside One Transaction

The reservation creation flow performs two changes in the same transaction. Because there is a foreign key from `inventory_reservations` to `inventory`, update and lock the `inventory` row first before inserting the child row. Inserting a child row performs a foreign key check on the parent row; if two sessions both insert reservations first and then try to upgrade their parent locks from shared to exclusive to update stock, they can deadlock on lock upgrade.

1. Increment `reserved_qty` only if available stock remains sufficient; the `UPDATE` acquires an exclusive record lock on the `inventory` row.
2. Insert the reservation record with a unique request key while still holding the inventory lock.

The SQL example below uses `?` placeholders for the application to bind via `PreparedStatement`. Check the affected row count returned by `executeUpdate()` after the `UPDATE` before executing the `INSERT` and `COMMIT`.

~~~sql
START TRANSACTION;

UPDATE inventory
SET reserved_qty = reserved_qty + ?
WHERE warehouse_id = ?
  AND sku = ?
  AND on_hand_qty - reserved_qty >= ?;

-- If UPDATE affects 0 rows: ROLLBACK and check request_key.

INSERT INTO inventory_reservations
  (request_key, order_id, warehouse_id, sku, quantity, status, created_at, expires_at)
VALUES
  (?, ?, ?, ?, ?, 'RESERVED', UTC_TIMESTAMP(6),
   UTC_TIMESTAMP(6) + INTERVAL 15 MINUTE);

-- Only COMMIT when both UPDATE and INSERT succeed.

COMMIT;
~~~

In this example, `quantity` is bound three times: once for incrementing `reserved_qty`, once for the availability check, and once for the reservation row. The application must validate that `quantity > 0` before sending the SQL. The CHECK constraint on the reservation provides an additional safeguard.

If `UPDATE` affects 0 rows, either the SKU does not exist in that warehouse or available stock is insufficient. The application must `ROLLBACK`; after rolling back, look up `request_key` to distinguish a previously processed request from a genuine out-of-stock condition. If inserting the reservation fails—for example, due to a duplicate `request_key`—also `ROLLBACK` to undo the `reserved_qty` increment. Never `COMMIT` a reservation whose quantity was not added to the stock counter, or vice versa.

You can check affected rows via JDBC `executeUpdate()`; the return value of `UPDATE` is the number of changed rows. Since `quantity` must be positive, a successful `UPDATE` increases the counter and affects one row. There is no need to run a prior `SELECT` to check stock before `UPDATE`; the condition inside `UPDATE` performs an atomic check under the row lock.

### Why lock `inventory` first before inserting `reservation`?

Operations modifying reservations must follow a uniform lock order: `inventory` first, `reservation` second. When inserting a reservation with a foreign key, InnoDB checks the parent row; if the transaction does not already hold a lock on `inventory`, the foreign key check can acquire a shared lock on the parent row. Two sessions both holding shared locks and attempting to update the parent row can deadlock when upgrading to exclusive locks. Updating `inventory` first ensures the transaction already holds an exclusive lock before the child foreign key check runs.

- Create: conditional `UPDATE` on `inventory`, then `INSERT` reservation.
- Confirm: read warehouse/SKU keys first, lock `inventory` with `FOR UPDATE`, then lock reservation with `FOR UPDATE`.
- Cancel/expire: follow the exact same order—`inventory` first, `reservation` second.

This is the lock-ordering convention for this lab. If a single transaction handles multiple SKUs, lock the `inventory` rows in a deterministic order, such as ascending `(warehouse_id, sku)`, before writing reservations. All confirm, cancel, and expiry flows must follow this same ordering.

## 5. Never Check Stock with `SELECT` Followed by `UPDATE`

Error-prone pattern:

~~~sql
SELECT on_hand_qty - reserved_qty AS available_qty
FROM inventory
WHERE warehouse_id = 1
  AND sku = 'SKU-CHAIR';

-- Application sees available_qty = 10 and decides to reserve 7.

UPDATE inventory
SET reserved_qty = reserved_qty + 7
WHERE warehouse_id = 1
  AND sku = 'SKU-CHAIR';
~~~

Two requests can both read 10 before either updates the row. Without locking and re-checking inside the transaction, both can add 7.

The safe pattern places the condition directly inside `UPDATE`:

~~~sql
UPDATE inventory
SET reserved_qty = reserved_qty + 7
WHERE warehouse_id = 1
  AND sku = 'SKU-CHAIR'
  AND on_hand_qty - reserved_qty >= 7;
~~~

InnoDB locks the row being updated. If another transaction is currently updating the same row, the second `UPDATE` waits. Once it proceeds, the condition is evaluated against the latest committed row state; if available stock is no longer enough, `UPDATE` affects 0 rows. This protects concurrency without relying on a stale snapshot read.

An alternative is `SELECT ... FOR UPDATE`, followed by reading the quantities and updating inside the same transaction. That is a locking read, suitable when multiple attributes must be inspected or complex logic is required. For a simple conditional counter increment, conditional `UPDATE` is usually more concise.

## 6. Simulating Two Competing Sessions

Start from this state:

~~~text
SKU-CHAIR: on_hand_qty = 10, reserved_qty = 0
Request A wants to reserve 7
Request B wants to reserve 7
~~~

Open two MySQL client windows, each acting as an independent connection.

### Session A

~~~sql
START TRANSACTION;

UPDATE inventory
SET reserved_qty = reserved_qty + 7
WHERE warehouse_id = 1
  AND sku = 'SKU-CHAIR'
  AND on_hand_qty - reserved_qty >= 7;

INSERT INTO inventory_reservations
  (request_key, order_id, warehouse_id, sku, quantity, status, created_at, expires_at)
VALUES
  ('req-A', 1001, 1, 'SKU-CHAIR', 7, 'RESERVED', UTC_TIMESTAMP(6),
   UTC_TIMESTAMP(6) + INTERVAL 15 MINUTE);

-- Result: 1 row updated.
-- Hold off on COMMIT for now.
~~~

### Session B

While Session A has not yet committed, run in Session B:

~~~sql
START TRANSACTION;

UPDATE inventory
SET reserved_qty = reserved_qty + 7
WHERE warehouse_id = 1
  AND sku = 'SKU-CHAIR'
  AND on_hand_qty - reserved_qty >= 7;

-- Only execute INSERT reservation if UPDATE affects exactly 1 row.
~~~

Session B's `UPDATE` blocks waiting on the `inventory` row lock held by Session A.

Return to Session A:

~~~sql
COMMIT;
~~~

Once A commits, B's `UPDATE` resumes. The condition `on_hand_qty - reserved_qty >= 7` is now false because only 3 units remain available. Session B's `UPDATE` affects 0 rows; B skips inserting the reservation and must `ROLLBACK` its transaction. Had B's `UPDATE` affected 1 row (for instance, if A had rolled back), B would then insert its reservation in the same transaction.

~~~sql
-- Session B
ROLLBACK;
~~~

Final state:

| Metric | Value |
|---|---:|
| on_hand_qty | 10 |
| reserved_qty | 7 |
| available_qty | 3 |
| RESERVED reservations | 1 |
| Total reserved quantity | 7 |

If Session A runs `ROLLBACK` instead of `COMMIT`, Session B proceeds and successfully reserves 7. Only one transaction is allowed to confirm a hold exceeding remaining availability.

This is the core test: two independent sessions competing for the same `inventory` row while the database enforces the invariant once both transactions finish.

## 7. Idempotency on Client Retries

A request may commit successfully in MySQL right before the connection drops and before the application receives the response. The client retries the same request. If the application generates a new reservation with a different request key, stock could be reserved twice.

Use a unique `request_key` to make retries idempotent:

- Each business request generates one stable request key.
- Every retry of that request reuses the same key.
- If `INSERT` hits a duplicate key error, roll back the current transaction and read the existing reservation.
- Compare `order_id`, warehouse, SKU, and `quantity` against the retry payload.
- If the payload matches, return the existing reservation result.
- If the payload differs, return a conflict; never silently reuse one key for two different requests.

Do not use `INSERT IGNORE` to mask duplicate requests. You need to distinguish an "already-processed request" from "other data errors." The unique key lets MySQL serialize two requests carrying the same key: one transaction inserts the row while the other waits on the unique check and receives a duplicate error once the first commits.

If the first transaction rolls back, the second request can insert successfully. Thus, retrying with the same key both prevents duplicate reservations after a commit and lets a request succeed if the earlier attempt did not commit.

If a commit fails due to a network error, the application cannot always know whether the transaction committed. Retrying with the same request key and reading the persisted state is safer than generating a fresh key.

With the `inventory`-before-`reservation` lock order, two concurrent requests sharing a `request_key` can hit two cases: the second request's `UPDATE inventory` returns 0 rows because the first request consumed the remaining availability, or the `UPDATE` succeeds and `INSERT` hits a duplicate key. Both branches must `ROLLBACK` first, then look up `request_key` in a fresh transaction. If the payload matches, return the stored result; if it differs, return conflict; if no matching reservation exists, report out-of-stock or missing SKU accordingly.

## 8. Confirming a Reservation and Deducting Stock

When payment or order confirmation completes, the reservation transitions from `RESERVED` to `CONFIRMED`. At that point, deduct the held quantity from both `on_hand_qty` and `reserved_qty`.

To maintain the `inventory`-before-`reservation` lock order, first read the immutable warehouse/SKU key from the reservation, then lock the `inventory` row, and finally lock the reservation to inspect its current status. The first read only locates the parent key; the `FOR UPDATE` read performs the locked status check.

~~~sql
START TRANSACTION;

SELECT warehouse_id, sku
FROM inventory_reservations
WHERE id = ?;

SELECT warehouse_id, sku
FROM inventory
WHERE warehouse_id = ?
  AND sku = ?
FOR UPDATE;

SELECT id, warehouse_id, sku, quantity, status, expires_at
FROM inventory_reservations
WHERE id = ?
FOR UPDATE;
~~~

The application checks the status:

- `CONFIRMED`: operation already completed previously; return an idempotent success without deducting stock again.
- `RELEASED` or `EXPIRED`: cannot confirm this reservation.
- `RESERVED` and not yet expired: proceed.
- `RESERVED` but already expired: release via the expiration flow; do not confirm.

For an unexpired reservation, update `inventory`:

~~~sql
UPDATE inventory
SET
  on_hand_qty = on_hand_qty - ?,
  reserved_qty = reserved_qty - ?
WHERE warehouse_id = ?
  AND sku = ?
  AND on_hand_qty >= ?
  AND reserved_qty >= ?;
~~~

If `UPDATE` affects exactly one row, update the reservation status:

~~~sql
UPDATE inventory_reservations
SET
  status = 'CONFIRMED',
  confirmed_at = UTC_TIMESTAMP(6)
WHERE id = ?
  AND status = 'RESERVED'
  AND expires_at > UTC_TIMESTAMP(6);
~~~

The application must verify both `UPDATE` statements affected exactly one row before `COMMIT`. If any condition fails, `ROLLBACK` the entire transaction. The expiration condition in the status `UPDATE` re-checks validity right before finalizing the transition.

When the transaction succeeds:

- `on_hand_qty` decreases because the stock is now committed/consumed.
- `reserved_qty` decreases because the quantity is no longer in the pending hold pool.
- `available_qty` stays unchanged at the moment of transition.
- The reservation becomes `CONFIRMED`.

Both the `inventory` and `reservation` updates must execute inside the same transaction. Never commit `CONFIRMED` first and deduct stock in a separate transaction.

## 9. Releasing a Reservation Exactly Once

When an order is cancelled prior to confirmation, release the held quantity. Read the immutable warehouse/SKU first, lock `inventory`, and then lock the reservation to keep the exact same lock order as creation and confirmation:

~~~sql
START TRANSACTION;

SELECT warehouse_id, sku
FROM inventory_reservations
WHERE id = ?;

SELECT warehouse_id, sku
FROM inventory
WHERE warehouse_id = ?
  AND sku = ?
FOR UPDATE;

SELECT id, warehouse_id, sku, quantity, status
FROM inventory_reservations
WHERE id = ?
FOR UPDATE;
~~~

Only deduct the counter if status is `RESERVED`:

~~~sql
UPDATE inventory
SET reserved_qty = reserved_qty - ?
WHERE warehouse_id = ?
  AND sku = ?
  AND reserved_qty >= ?;
~~~

Then transition the status:

~~~sql
UPDATE inventory_reservations
SET
  status = 'RELEASED',
  released_at = UTC_TIMESTAMP(6)
WHERE id = ?
  AND status = 'RESERVED';
~~~

Verify both `UPDATE` statements succeeded before committing. If the reservation is already `RELEASED` or `EXPIRED`, return a released outcome without subtracting `reserved_qty` a second time. If it is already `CONFIRMED`, order cancellation must follow a dedicated restock/return workflow; you cannot simply release an already consumed reservation.

The inventory lock serializes changes on the same warehouse/SKU; the `FOR UPDATE` lock on the reservation guards the state transition. The first request transitions `RESERVED` to `RELEASED`; the second request, once it acquires the locks, observes `RELEASED` and does not update `inventory` again. This makes the state transition idempotent.

## 10. Automatic Expiration via Worker

Reservations should not hold stock indefinitely. A periodic worker finds overdue `RESERVED` reservations and releases them.

Index `(status, expires_at, id)` supports fetching a batch of candidate IDs. This scan does not lock reservations; each ID is processed in its own transaction following the `inventory`-before-`reservation` lock order:

~~~sql
SELECT id
FROM inventory_reservations
WHERE status = 'RESERVED'
  AND expires_at <= UTC_TIMESTAMP(6)
ORDER BY expires_at, id
LIMIT 100;
~~~

Do not run `SELECT ... FOR UPDATE` on `inventory_reservations` during the candidate scan and then lock `inventory` afterward. Doing so reverses the lock order and can deadlock with confirm/cancel flows. If multiple workers pick up the same ID, they serialize at the `inventory` row; the later worker re-reads the reservation status and skips it if already processed. You can partition ID ranges across workers to minimize duplicate work. `SKIP LOCKED` is helpful for queue workers, yet only apply it when the query design preserves the `inventory`-before-`reservation` lock order.

For each candidate ID, within one transaction:

1. Read `warehouse_id` and `sku` from the reservation to locate the `inventory` row.
2. Lock the `inventory` row with `SELECT ... FOR UPDATE`.
3. Re-lock the reservation with `SELECT ... FOR UPDATE` and check its current status and expiration time.
4. If still `RESERVED` and expired, decrement `reserved_qty` and transition status to `EXPIRED`.
5. Verify affected row counts and `COMMIT`.

Example processing after the worker locks `inventory` and then the reservation:

~~~sql
START TRANSACTION;

SELECT warehouse_id, sku
FROM inventory_reservations
WHERE id = ?;

SELECT warehouse_id, sku
FROM inventory
WHERE warehouse_id = ?
  AND sku = ?
FOR UPDATE;

SELECT id, quantity, status, expires_at
FROM inventory_reservations
WHERE id = ?
FOR UPDATE;

-- Only run the two UPDATE statements below if status = 'RESERVED'
-- and expires_at <= UTC_TIMESTAMP(6).

UPDATE inventory
SET reserved_qty = reserved_qty - ?
WHERE warehouse_id = ?
  AND sku = ?
  AND reserved_qty >= ?;

UPDATE inventory_reservations
SET
  status = 'EXPIRED',
  released_at = UTC_TIMESTAMP(6)
WHERE id = ?
  AND status = 'RESERVED'
  AND expires_at <= UTC_TIMESTAMP(6);

COMMIT;
~~~

If either `UPDATE` fails to affect exactly one row, `ROLLBACK` and log an error for investigation; never advance status if the stock counter was not updated.

Processing one reservation per transaction simplifies lock ordering and limits lock duration. If batching, lock all `inventory` rows in ascending `(warehouse_id, sku)` order first, then lock the corresponding reservations; bound batch sizes and test for deadlocks.

If the worker runs behind schedule, stock that has expired by wall-clock time may temporarily remain in `reserved_qty` until released. This makes `available_qty` look lower than reality for a brief window, yet never causes overselling. If the business requires immediate expiration at the exact deadline, design a synchronous locked expiration path and test concurrency against confirm/cancel.

## 11. Concurrency Between Confirm, Cancel, and Expiry

All three operations can race on the same reservation. Every path must follow the same lock order: locate warehouse/SKU, lock the `inventory` row first, then lock the reservation with `SELECT ... FOR UPDATE` and re-verify status.

| Race Condition | Valid Outcome |
|---|---|
| Confirm vs. cancel | Only one operation transitions RESERVED to a terminal state; the other sees the updated state and leaves counters untouched |
| Confirm vs. expiry worker | Only one acquires the lock first; if a valid confirm runs before expiration the worker skips it, and if expiry transitions first confirm cannot consume stock |
| Two cancels | First call releases stock; second call observes RELEASED and does not deduct again |
| Two expiry workers | Worker acquiring the inventory lock first processes it; the other waits, reads the updated state, and skips |
| Retry confirm | If already CONFIRMED, return the existing outcome without deducting stock again |

Expiration timestamps should be evaluated using MySQL server time (`UTC_TIMESTAMP(6)`) so workers and app instances do not rely on skewed host clocks. The `expires_at` column in our example stores UTC by application convention.

## 12. Reserving Multiple SKUs in One Order

An order may require multiple items. If policy mandates all-or-nothing holds, create reservations for all lines inside a single transaction:

1. Normalize the warehouse/SKU list, merging duplicate SKU lines if business rules permit.
2. Validate that all quantities are positive.
3. Sort by `(warehouse_id, sku)`.
4. Update/lock all `inventory` rows in that sorted order and verify sufficient stock.
5. Insert a reservation for each line using a per-line unique request key.
6. If any line lacks sufficient stock, `ROLLBACK` the entire transaction.
7. `COMMIT` once all lines succeed.

Locking in deterministic order reduces deadlock likelihood between two orders with overlapping SKUs arriving in reversed input order. Never trust client-supplied item order; normalize and sort on the server.

If business rules allow partial fulfillment, the status model must explicitly track which lines succeeded, which lacked stock, and how order totals adjust. Never use an all-or-nothing transaction and silently skip out-of-stock SKUs.

## 13. Handling Deadlocks and Lock Wait Timeouts

Even with consistent lock ordering, deadlocks can still occur due to secondary indexes, foreign keys, other operations, or transactions not following the same lock sequence.

Guidelines:

- Keep transactions short; never call payment APIs or send emails while holding row locks.
- Lock all `inventory` rows in `(warehouse_id, sku)` order before writing/locking reservations.
- Use primary keys or unique indexes in `WHERE` clauses to minimize lock scope.
- Never hold inventory/reservation locks while waiting for user input or external systems.
- Diagnose deadlocks using `SHOW ENGINE INNODB STATUS` and Performance Schema.
- Retry the entire transaction on deadlock (error 1213) with a bounded retry limit and jittered backoff.
- On lock wait timeout (typically error 1205), explicitly roll back the transaction per policy before retrying if the business operation is still valid.
- Do not retry out-of-stock errors as if they were transient failures.

InnoDB typically rolls back the transaction selected as the deadlock victim. By default, a lock wait timeout may only roll back the timed-out statement depending on `innodb_rollback_on_timeout`; the application should explicitly roll back the transaction before retrying the entire unit of work.

Retries must reuse the same `request_key` so they do not create duplicate reservations if an earlier attempt committed before the response was lost.

## 14. Reconciling Inventory Counters with Reservations

Because `reserved_qty` is an aggregated counter, run a periodic reconciliation query. Aggregate active reservations and compare against `inventory`:

~~~sql
SELECT
  i.warehouse_id,
  i.sku,
  i.reserved_qty AS stored_reserved_qty,
  COALESCE(r.calculated_reserved_qty, 0) AS calculated_reserved_qty
FROM inventory AS i
LEFT JOIN (
  SELECT
    warehouse_id,
    sku,
    SUM(quantity) AS calculated_reserved_qty
  FROM inventory_reservations
  WHERE status = 'RESERVED'
  GROUP BY warehouse_id, sku
) AS r
  ON r.warehouse_id = i.warehouse_id
 AND r.sku = i.sku
WHERE i.reserved_qty <> COALESCE(r.calculated_reserved_qty, 0);
~~~

The result must be empty when data is consistent. On large tables, run scoped by warehouse/SKU ranges or batches during appropriate windows and consider query load. Use a consistent read snapshot if writes are active; if reconciliation runs concurrently with reservation transactions, it may observe mismatched pre/post states across the two tables. Use a consistent snapshot or coordinate/pause writes during corrective procedures.

Never blindly overwrite `reserved_qty` in production with the recalculated sum before understanding the root cause. Before fixing, identify which reservations are missing or extra, inspect audit trails, and apply adjustments within a controlled transaction.

## 15. Testing Concurrency with Two Independent Connections

A concurrency test must use two genuine MySQL sessions. Two threads sharing a single `Connection` cannot simulate two independent transactions.

Minimum integration test suite:

| Test | Setup | What to Verify |
|---|---|---|
| Two requests competing for 7 out of 10 | Two connections, two request keys | Only one reservation succeeds; available never goes negative |
| Request A rolls back | A holds stock then rolls back while B waits | B proceeds and reserves stock |
| Retry with same request key | Send identical payload multiple times | Only one reservation exists |
| Same key, different payload | Reuse key with different quantity/SKU | Returns conflict, inventory unchanged |
| Double cancel | Call cancel concurrently or repeatedly | reserved_qty decreases only once |
| Confirm vs. expiry race | Worker and confirm race on one reservation | Only one terminal state is persisted |
| Multi-SKU different order | Two orders with reversed SKU lists | No oversell; deadlocks minimized and retries handled |
| Rollback on one missing SKU | One line in stock, another out of stock | No leftover reservations or partial counter increments |
| Lost response after COMMIT | Retry with same request key | Returns existing result without reserving twice |

With Testcontainers, pin the target MySQL version and use real Connector/J. Open two connections from the `DataSource`, synchronize start timing using `CountDownLatch` or a barrier, and verify affected row counts and final state. Avoid using `Thread.sleep()` as a primary synchronization mechanism because timing is flaky.

You can check row-level invariants after each test:

~~~sql
SELECT
  on_hand_qty >= 0 AS on_hand_nonnegative,
  reserved_qty >= 0 AS reserved_nonnegative,
  reserved_qty <= on_hand_qty AS reserved_not_over_on_hand
FROM inventory
WHERE warehouse_id = 1
  AND sku = 'SKU-CHAIR';
~~~

In addition to per-row invariants, run the reservation reconciliation query from the previous section to ensure aggregated counters match detail rows.

## 16. Integrating into Spring/JDBC

A Spring service can use `@Transactional` to wrap both `UPDATE inventory` and `INSERT reservation`. All operations must use the same `DataSource` and transaction manager; this order also keeps the inventory lock acquired before the reservation foreign key check executes.

Service-layer flow:

~~~text
reserve(request)
    |
    +--> validate quantity > 0
    |
    +--> begin transaction
    |
    +--> conditional UPDATE inventory
    |       |
    |       +--> affected rows = 0: rollback, then resolve request_key
    |       |
    |       +--> affected rows = 1
    |              |
    |              +--> insert reservation with request_key
    |                         |
    |                         +--> duplicate/error: rollback
    |                         +--> success: commit
    |
    +--> return reservation id
~~~

Service skeleton example:

~~~java
@Transactional
public Reservation reserve(ReserveCommand command) {
    if (command.quantity() <= 0) {
        throw new IllegalArgumentException("quantity must be positive");
    }

    int updated = jdbcTemplate.update("""
        UPDATE inventory
        SET reserved_qty = reserved_qty + ?
        WHERE warehouse_id = ?
          AND sku = ?
          AND on_hand_qty - reserved_qty >= ?
        """,
        command.quantity(),
        command.warehouseId(),
        command.sku(),
        command.quantity()
    );

    if (updated != 1) {
        throw new OutOfStockException(command.sku());
    }

    reservationRepository.insertReserved(
        command.requestKey(),
        command.orderId(),
        command.warehouseId(),
        command.sku(),
        command.quantity()
    );

    return reservationRepository.findByRequestKey(command.requestKey())
        .orElseThrow();
}
~~~

`OutOfStockException` should be an unchecked exception, or `@Transactional(rollbackFor = ...)` should be configured if using a checked exception. Otherwise, Spring does not roll back checked exceptions by default, risking committing a reservation row even though inventory was not incremented.

Duplicate key handling requires a separate transaction boundary. If conditional `UPDATE` affects 0 rows, the transaction must roll back before querying `request_key` to distinguish a previously committed request from an out-of-stock request. If `UPDATE` succeeds but `INSERT reservation` hits a duplicate key, rolling back undoes `reserved_qty`; then, outside that transaction, read the existing `request_key` and compare payloads. In Spring, a database exception can mark the current transaction as rollback-only; never reuse that transaction to read idempotency state.

Never call payment gateways, send emails, or publish messages synchronously while holding inventory locks. If reliable post-commit event publishing is required, use the transactional outbox pattern or an equivalent mechanism.

## 17. Operational Observability

Monitor both business metrics and database behavior:

- Total counts of `RESERVED`, `CONFIRMED`, `RELEASED`, and `EXPIRED` reservations.
- Age of the oldest expired reservation not yet processed by the worker.
- Rates of out-of-stock errors and duplicate idempotency keys.
- Deadlock, lock wait timeout, and retry counts.
- Transaction durations and connection pool wait times.
- `available_qty` per warehouse/SKU.
- Discrepancies between `reserved_qty` and the sum of `RESERVED` reservations.
- Expiry worker run duration and reservations processed per batch.

When investigating locks, inspect `performance_schema.data_lock_waits`, `performance_schema.data_locks`, `SHOW ENGINE INNODB STATUS`, and the processlist. For worker queries, run `EXPLAIN` to confirm the expiry index is used; do not let the worker periodically full-scan the entire reservations table.

Alert if expired reservations remain holding stock for too long, or if aggregated counters diverge from detail records. These alerts catch both application bugs and stalled background jobs early.

## 18. Common Design Pitfalls

| Anti-Pattern | Consequence | Fix |
|---|---|---|
| SELECT available then unconditional UPDATE | Two requests both see sufficient stock and oversell | Conditional UPDATE or locking read inside a transaction |
| Creating reservation in a separate transaction from inventory update | Reservation exists without holding stock or vice versa | Same InnoDB transaction |
| No unique request key | Retries create duplicate reservations | Unique idempotency key with payload comparison |
| Cancelling reservation without lock ordering | Two requests both deduct reserved_qty or deadlock | Lock inventory first, reservation second, with conditional state change |
| Expiry worker locks reservation before inventory | Confirm and expiry can deadlock or double-process | Fetch candidates unlocked, lock inventory first, then re-lock reservation |
| Deleting reservation upon cancellation | Loses audit trail and breaks idempotency | Retain terminal state RELEASED/EXPIRED |
| Using cache as source of truth for inventory | Stale cache can confirm beyond physical stock | MySQL transaction is the final source of truth |
| Calling external APIs inside transaction | Holds locks too long, increases deadlocks and timeouts | Split transactions, use outbox/saga |
| Processing multiple SKUs in client-supplied order | Increases deadlock probability | Sort to a deterministic lock order |
| Retrying all errors | Retries out-of-stock needlessly; risks duplicates | Classify errors and reuse stable request keys |

## 19. Complete Practice Lab

Perform the following steps sequentially on a test MySQL instance:

1. Create `inventory` and `inventory_reservations` with all constraints and indexes.
2. Load `SKU-CHAIR` with 10 units and `SKU-DESK` with 5 units.
3. Write the reserve transaction: conditional update on `inventory`, insert reservation, check affected rows, and commit/rollback.
4. Open two sessions, concurrently reserve 7 chairs in both, and verify only one succeeds.
5. Resend the successful request with the same request key; verify `reserved_qty` does not increase a second time.
6. Retry with the same request key but a different payload; verify the system returns a conflict.
7. Confirm one reservation; verify both `on_hand_qty` and `reserved_qty` decrease.
8. Cancel a `RESERVED` reservation twice; verify only the first call decreases `reserved_qty`.
9. Create an expired reservation and run the worker to fetch candidates and then lock `inventory` before `reservation`.
10. Create two multi-SKU orders with reversed SKU ordering; test lock ordering and deadlock handling.
11. Run the reconciliation query comparing `reserved_qty` against the sum of `RESERVED` reservation quantities.
12. Record outputs, error codes, wait times, affected row counts, and invariants after each test.

**Completion criteria:**

- No case where `reserved_qty > on_hand_qty`.
- No `RESERVED` reservation exists without a corresponding increment in `inventory`.
- Retrying with the same request key never creates a second hold.
- Confirm/cancel/expiry transitions state only once.
- Rollback reverts both the reservation row and the inventory counter.
- Two competing sessions reserve no more than actual available stock.
- Expiry workers can run concurrently without double-processing reservations.
- Reconciliation queries and logs are sufficient to investigate discrepancies.

## 20. Takeaways

- Separate physical stock, reserved quantity, and available quantity into clear metrics.
- Use InnoDB and primary key `(warehouse_id, sku)` to uniquely identify each warehouse/SKU counter.
- Create the reservation and increment `reserved_qty` inside the same transaction.
- Place the availability check directly in the `UPDATE` for atomic check-and-write.
- Follow the `inventory`-first, `reservation`-second lock order; use `SELECT ... FOR UPDATE` to verify state before confirm, cancel, or expiry.
- Use a unique request key for safe retries after timeouts or lost `COMMIT` responses.
- Handle terminal states idempotently; never subtract counters a second time.
- Have the expiry worker fetch candidates unlocked and process each reservation in a transaction following the unified lock order.
- Lock multiple SKUs in deterministic order and retry deadlocks with bounded attempts.
- Reconcile the `inventory` counter against the sum of `RESERVED` reservations.
- Test using multiple independent MySQL connections; mocks or a single shared connection cannot prove InnoDB concurrency behavior.

Reliable reservation design rests on clear invariants and atomic transactions. When every creation, confirmation, cancellation, and expiration flow locks in the same order, uses idempotency keys, and is validated with real concurrent sessions, the system handles contention without overselling.

## References

- [MySQL 8.0 Reference Manual: InnoDB Locking](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking.html)
- [MySQL 8.0 Reference Manual: Locking Reads](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking-reads.html)
- [MySQL 8.0 Reference Manual: InnoDB Transaction Model](https://dev.mysql.com/doc/refman/8.0/en/innodb-transaction-model.html)
- [MySQL 8.0 Reference Manual: SELECT ... FOR UPDATE and SKIP LOCKED](https://dev.mysql.com/doc/refman/8.0/en/innodb-locking-reads.html)
- [MySQL 8.0 Reference Manual: Deadlocks in InnoDB](https://dev.mysql.com/doc/refman/8.0/en/innodb-deadlocks.html)
- [MySQL 8.0 Reference Manual: CHECK Constraints](https://dev.mysql.com/doc/refman/8.0/en/create-table-check-constraints.html)
- [Spring Framework Reference: Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Testcontainers for Java: MySQL Module](https://java.testcontainers.org/modules/databases/mysql/)
