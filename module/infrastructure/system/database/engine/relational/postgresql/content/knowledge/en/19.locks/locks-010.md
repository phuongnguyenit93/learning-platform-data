# Application-Level Optimistic Concurrency Control with Data Versions in PostgreSQL

A multi-user application may let two users open the same order, edit it simultaneously, and click **Save** one after the other. Both operations can be completely valid `UPDATE` statements in PostgreSQL, yet without concurrency control the second save **overwrites the first user's changes** without any warning.

Example:

```text
10:00:00  A reads order #101: note="Morning delivery"
10:00:01  B reads order #101: note="Morning delivery"

10:00:10  B saves: note="Customer switched to afternoon"
10:00:20  A saves: note="Call before delivery"

If both UPDATEs only use WHERE order_id=101:
    Final value becomes "Call before delivery".
    B's change silently disappears from the current record.
```

PostgreSQL has MVCC, row-level locks, and transaction isolation levels, yet **a row lock during the write transaction cannot tell PostgreSQL that A's form was loaded ten minutes ago**. What needs protection is the application's expectation: *only apply this update if no one else modified the record since I read it*.

A standard solution is **optimistic concurrency control** (*optimistic locking*) using a **data version**. Each row includes a `row_version` column; on read, the application receives both the data and its version; on write, the application sends back the **expected version**, and PostgreSQL checks it atomically inside the `UPDATE`.

```sql
UPDATE orders
SET note = 'Call before delivery',
    row_version = row_version + 1
WHERE order_id = 101
  AND row_version = 7
RETURNING row_version;
```

If the current version is still 7, one row is updated and its version becomes 8. If someone else already advanced it to version 8, an `UPDATE` expecting version 7 updates **0 rows**. The application must handle that as a conflict rather than reporting "saved successfully."

This lesson covers **application-level optimistic concurrency control with data versions** in the PostgreSQL **Locks** chapter. It focuses on read–write protocols, atomic version matching, two-session scenarios, differences from `SELECT FOR UPDATE`, conflict/retry handling, API/Java/JPA integration, single-row version limits, and correctness across multiple tables.

---

## 1. Learning Objectives

After this lesson, you will be able to:

1. Analyze **lost updates** and explain why MVCC does not replace application-level version checks.
2. Compare optimistic locking with pessimistic locking.
3. Design a `BIGINT NOT NULL` version column and initialization/increment rules.
4. Write **compare-and-swap (CAS)** updates using `UPDATE ... WHERE id = ? AND row_version = ?`.
5. Use `RETURNING` or affected row counts to distinguish success from conflict.
6. Simulate two sessions reading the same version and prove only one writer succeeds on that expected version.
7. Combine versions with `tenant_id`, order status, soft delete, and authorization checks.
8. Distinguish 0-row `UPDATE`s from deadlocks, serialization failures, and constraint errors.
9. Design UX flows for stale forms: reload, diff comparison, merge, or reject.
10. Implement the pattern in JDBC, JPA `@Version`, and HTTP `ETag`/`If-Match`.
11. Keep outbox/audit records consistent in a transaction and use idempotency for request retries.
12. Recognize cases where per-row versions do not protect multi-row invariants.
13. Audit other write paths such as batch jobs, imports, admin scripts, and ORM bulk updates.
14. Write two-connection barrier integration tests and monitor conflict rates.

Run the DDL, `INSERT`, `UPDATE`, and `DELETE` practice commands **only in a test database**. If an example modified data, reset the lab before predicting output for subsequent examples.

---

## 2. Lost Updates: Where Is the Problem?

Suppose the orders table contains:

| order_id | note | row_version |
| ---: | --- | ---: |
| 101 | Morning delivery | 7 |

Two browsers call the API:

```text
Client A                      PostgreSQL                     Client B
   |                              |                              |
   |---- GET order #101 --------->|<-------- GET order #101 ----|
   |<--- note=morning,version=7 --|--- note=morning,version=7 -->|
   |                              |                              |
   |                              |<------- B's UPDATE ----------|
   |                              |   note=afternoon, COMMIT     |
   |                              |-------- SUCCESS ------------>|
   |                              |                              |
   |------- A's UPDATE ---------->|                              |
   |        from stale v7 read    |                              |
   |                              |                              |
   |     Without version guard:   |                              |
   |     A overwrites B's change. |                              |
```

An `UPDATE` vulnerable to lost updates:

```sql
UPDATE orders
SET note = :new_note
WHERE order_id = :order_id;
```

This condition asks "does the row still exist?"—**not "is the row still at the version the client read?"**

### 2.1. Why Don't Row Locks Automatically Save a Stale Form?

PostgreSQL uses row-level locking during `UPDATE` execution. Two concurrent transactions updating the same row wait on each other; PostgreSQL prevents unsafe simultaneous physical writes.

However, a form is loaded in an earlier read transaction that already closed. A user may spend several minutes editing in the browser before submitting a write in a brand-new transaction. No row lock from the earlier read **still exists**.

If the write request carries only absolute new values, the server has no idea the user acted on stale data. Adding `expected_version` to `WHERE` makes the operation's precondition explicit.

### 2.2. Last-Write-Wins Is Not Always Wrong

For cache-like fields or telemetry where overwriting with the latest write is acceptable, last-write-wins can be a valid contract. For customer records, editorial content, approval workflows, payments, or critical configuration, silent overwrites erase another user's decisions.

Versioning turns silent overwrites into **detectable, handleable conflict events** instead of subtle corrupted state.

---

## 3. Optimistic Locking vs. Pessimistic Locking

| Aspect | Optimistic locking | Pessimistic locking |
| --- | --- | --- |
| Assumption | Conflicts are relatively rare; verify at write time | Conflicts are frequent; hold locks to serialize work |
| Mechanism | `WHERE row_version = expected` | `SELECT ... FOR UPDATE`, row locks |
| On conflict | 0 rows updated or transaction error depending on isolation | Lock waits, timeouts, `NOWAIT` errors, deadlocks |
| Transaction hold time | Usually just the write request | Covers read, decision, and write inside one transaction |
| Best suited for | Forms, APIs, slow user editing | Short workflows needing row protection across multi-step checks |
| Trade-offs | Needs conflict feedback and merge/retry UX | Lock contention, longer transactions, deadlock risk |

**Optimistic locking does not mean PostgreSQL `UPDATE` skips row locking.** It is an application-level version check, not a way to disable database locks.

### 3.1. Never Hold FOR UPDATE While Users Edit Forms

A form can stay open for many minutes. Holding a transaction and row lock that long:

- Blocks concurrent operations.
- Pins a database connection.
- Causes lock waits and timeouts.
- Keeps old snapshots/tuples alive.
- Is hard to recover when clients lose network or close tabs.

Standard pattern: **read data with its version, close the transaction, and run a CAS update when the client saves**.

### 3.2. Both Can Be Combined

An application can enforce optimistic versions at the API layer while still using short row locks inside the write transaction on related tables—for example, transitioning an order status and deducting inventory atomically. The two techniques complement each other.

---

## 4. Designing the Version Column

Minimal schema:

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL,
    note TEXT,
    row_version BIGINT NOT NULL DEFAULT 1
        CHECK (row_version > 0)
);
```

Rules:

- Initialize version to a consistent starting value (typically 0 or 1).
- Every protected change must increment the version.
- **Never reset or reuse versions** during an entity's lifetime.
- Version is scoped per record identifier, not globally unique.
- Increment the version **in the same statement or transaction** as the data change.
- Return the new version to the client after a successful commit.

### 4.1. Why Use BIGINT?

`BIGINT` provides a vast signed integer range, plenty for update counts over a business record's lifetime. Still, it is finite; never rely on wraparound behavior on overflow.

### 4.2. Why Not Use Only updated_at?

Timestamps have multiple flaws as concurrency tokens:

- PostgreSQL's `now()` is fixed to **transaction start time**, so multiple `UPDATE`s in one transaction get the same timestamp.
- Timestamp precision can be truncated across JSON, Java, JavaScript, or external systems.
- Two rapid updates can produce indistinguishable timestamps after rounding/serialization.
- Triggers or migrations may set `updated_at` inconsistently.
- Timestamps record wall-clock time, not whether a logical mutation occurred.

Keep `updated_at` for auditing and display; use `row_version` or an explicit opaque token for CAS.

### 4.3. Why Not Use xmin or ctid as Long-Lived Application Tokens?

PostgreSQL exposes system columns `xmin`, `xmax`, and `ctid`. However:

- `xmin` reflects the creating transaction ID, subject to XID freezing and internal lifecycle.
- `ctid` is the physical tuple slot, which changes on every `UPDATE` or table rewrite.
- They are not stable business version tokens across migrations or replication.
- They fit poorly with external API contracts and off-database state.

While specialized libraries sometimes inspect system columns in narrow scopes, general application design should prefer an **explicit application-managed version column**.

---

## 5. Creating the PostgreSQL Practice Dataset

The lab includes two tenants to practice both version control and tenant-scoped locking.

> **Warning:** The `DROP TABLE IF EXISTS` statements below delete existing lab tables of the same name. Run only in a dedicated database safe to reset—never in production.

### 5.1. Orders Schema

```sql
CREATE SCHEMA IF NOT EXISTS optimistic_lock_lab;

DROP TABLE IF EXISTS optimistic_lock_lab.order_outbox;
DROP TABLE IF EXISTS optimistic_lock_lab.orders;

CREATE TABLE optimistic_lock_lab.orders (
    tenant_id INTEGER NOT NULL,
    order_id BIGINT NOT NULL,
    status TEXT NOT NULL
        CHECK (status IN ('DRAFT', 'PAID', 'CANCELED')),
    amount NUMERIC(14,2) NOT NULL CHECK (amount >= 0),
    note TEXT,
    row_version BIGINT NOT NULL DEFAULT 1
        CHECK (row_version > 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id, order_id)
);
```

The `PRIMARY KEY` is **`(tenant_id, order_id)`**, letting tenants have overlapping `order_id` values. `WHERE` clauses must include the **full key**; tenant verification must come from server-trusted auth context, never an unchecked client field.

### 5.2. Seed Data

```sql
INSERT INTO optimistic_lock_lab.orders (
    tenant_id, order_id, status, amount, note, row_version
)
VALUES
    (10, 101, 'DRAFT', 100.00, 'Morning delivery', 1),
    (10, 102, 'DRAFT',  50.00, 'Packing', 1),
    (10, 103, 'PAID',  150.00, 'Paid', 1),
    (20, 101, 'DRAFT',  70.00, 'Other tenant order', 1);

SELECT tenant_id, order_id, status, note, row_version
FROM optimistic_lock_lab.orders
ORDER BY tenant_id, order_id;
```

Initially every record has `row_version=1`. Write examples increment versions; when running independent exercises, reset the lab at the start of this section.

### 5.3. Outbox Table for Advanced Examples

```sql
CREATE TABLE optimistic_lock_lab.order_outbox (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id INTEGER NOT NULL,
    order_id BIGINT NOT NULL,
    event_type TEXT NOT NULL,
    resulting_version BIGINT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES optimistic_lock_lab.orders(tenant_id, order_id)
);
```

This outbox table illustrates atomicity between order updates and events. It is not a full messaging relay, as it omits worker claiming, retries, deduplication, and delivery status.

---

## 6. Core SQL Statement: Compare-and-Swap

Correct `UPDATE`:

```sql
UPDATE optimistic_lock_lab.orders AS o
SET note = 'Call before delivery',
    row_version = o.row_version + 1,
    updated_at = clock_timestamp()
WHERE o.tenant_id = 10
  AND o.order_id = 101
  AND o.row_version = 1
RETURNING
    o.tenant_id,
    o.order_id,
    o.note,
    o.row_version,
    o.updated_at;
```

On initial data, this updates one row, saves the new note, and advances version to **2**.

### 6.1. Why Must the Check Be Inside WHERE?

If you write:

```text
SELECT row_version
Compare expectedVersion in application code
UPDATE orders SET note=... WHERE order_id=...
```

there is a **race window** between check and use. Another writer can `UPDATE` after your `SELECT` and before your `UPDATE`.

When you write:

```sql
UPDATE ...
WHERE order_id = :id
  AND row_version = :expected_version;
```

PostgreSQL evaluates the predicate on the target row as part of the write operation itself. Combined with row locking and MVCC, this ensures no two CAS updates can both succeed against the same old version of **the same row** under applicable rules.

### 6.2. Why Increment Version in the Same UPDATE?

Wrong approach:

```sql
UPDATE orders SET note = :new_note WHERE order_id = :id;
UPDATE orders SET row_version = row_version + 1 WHERE order_id = :id;
```

Two separate statements let one succeed while the other fails, or allow another writer to interleave unless properly wrapped in a transaction/lock.

Combined:

```sql
UPDATE orders
SET note = :new_note,
    row_version = row_version + 1
WHERE order_id = :id
  AND row_version = :expected_version
RETURNING row_version;
```

Version verification and data mutation execute **atomically at the `UPDATE` statement level**.

### 6.3. Re-Running with the Same Expected Version

Once version is 2, running the same statement with `row_version=1`:

```sql
UPDATE optimistic_lock_lab.orders AS o
SET note = 'Call before delivery',
    row_version = o.row_version + 1
WHERE o.tenant_id = 10
  AND o.order_id = 101
  AND o.row_version = 1
RETURNING o.row_version;
```

returns **0 rows**. That simply reflects a non-matching condition; it is not a syntax error or an exception thrown by PostgreSQL.

### 6.4. Why SET row_version = row_version + 1?

When `WHERE` guarantees the expected version, `expected_version + 1` yields the same number. Using the stored `row_version` makes the intent self-evident ("new version = current version + 1") and prevents parameter-binding mistakes.

---

## 7. Two-Session Experiment: Detecting a Stale Update

Open two **genuinely independent** PostgreSQL connections. If you modified order 101 above, reset the lab to initial seed data first.

### 7.1. Session A Reads

```sql
-- SESSION A
SELECT tenant_id, order_id, note, row_version
FROM optimistic_lock_lab.orders
WHERE tenant_id = 10 AND order_id = 101;
```

A receives:

```text
note="Morning delivery"
row_version=1
```

A edits the form and intends to save `"Call before delivery"`.

### 7.2. Session B Reads the Same Version

```sql
-- SESSION B
SELECT tenant_id, order_id, note, row_version
FROM optimistic_lock_lab.orders
WHERE tenant_id = 10 AND order_id = 101;
```

B also receives version 1 and intends to save `"Afternoon delivery"`.

### 7.3. B Saves First

```sql
-- SESSION B
UPDATE optimistic_lock_lab.orders AS o
SET note = 'Afternoon delivery',
    row_version = o.row_version + 1,
    updated_at = clock_timestamp()
WHERE o.tenant_id = 10
  AND o.order_id = 101
  AND o.row_version = 1
RETURNING o.note, o.row_version;
```

With autocommit on, B updates one row and version becomes **2**.

### 7.4. A Saves the Stale Form

```sql
-- SESSION A
UPDATE optimistic_lock_lab.orders AS o
SET note = 'Call before delivery',
    row_version = o.row_version + 1,
    updated_at = clock_timestamp()
WHERE o.tenant_id = 10
  AND o.order_id = 101
  AND o.row_version = 1
RETURNING o.note, o.row_version;
```

A gets **0 rows** because the stored version is no longer 1.

Verify:

```sql
SELECT note, row_version
FROM optimistic_lock_lab.orders
WHERE tenant_id = 10 AND order_id = 101;
```

The data remains:

```text
note="Afternoon delivery"
row_version=2
```

**Desired outcome:** B's change is preserved, and A detects the conflict so it can reload or merge instead of silently overwriting.

### 7.5. What If Both UPDATEs Start Simultaneously?

When two transactions contend on updating the same row:

1. One transaction acquires the row lock first.
2. The second waits, or fails if `lock_timeout`/`NOWAIT` applies.
3. When the first writer commits, the second proceeds per visibility/isolation rules.
4. Under `READ COMMITTED` with a CAS version check, the second no longer matches `WHERE`, yielding **0 rows**.
5. Under stricter isolation levels, certain schedules throw a **serialization failure** instead of 0 rows.

Applications must handle both 0-row conflicts and concurrent transaction exceptions.

---

## 8. 0 Rows Updated Is Not Always a Version Conflict

Consider:

```sql
UPDATE optimistic_lock_lab.orders AS o
SET status = 'PAID',
    row_version = o.row_version + 1
WHERE o.tenant_id = 10
  AND o.order_id = 101
  AND o.row_version = 1
  AND o.status = 'DRAFT'
RETURNING o.row_version;
```

If 0 rows return, there are multiple possible causes:

- Record does not exist.
- Wrong tenant.
- Blocked from seeing/updating by RLS.
- Version already changed.
- Status is not `DRAFT`.
- Record was deleted.
- Another business condition no longer holds.

Thus, **0 rows = not all predicates matched**, which alone does not pinpoint a single cause.

### 8.1. Classifying Within Authorized Scope

An application can re-read the record within the caller's authorized scope to return a clearer error. Keep in mind:

- Re-reading happens at a later point in time when another writer may have modified the row again.
- Never let the diagnostic read leak resources belonging to another tenant.
- Do not treat the diagnostic read as an atomic snapshot with the failed `UPDATE`.
- Do not return misleading HTTP status codes by lumping every 0-row outcome into one generic error.

### 8.2. Using RETURNING

`RETURNING` returns columns from rows actually modified:

```sql
UPDATE optimistic_lock_lab.orders AS o
SET note = 'Verified',
    row_version = o.row_version + 1
WHERE o.tenant_id = 10
  AND o.order_id = 102
  AND o.row_version = 1
RETURNING o.order_id, o.note, o.row_version;
```

- Exactly one row: update succeeded per conditions.
- 0 rows: predicate did not match.
- Multiple rows: with an exact `PRIMARY KEY` `WHERE` clause, must never happen.

Never assume "no SQL error" means "saved successfully."

---

## 9. Version Checks and Business State Checks Are Distinct Guards

Example order lifecycle:

```text
DRAFT ------> PAID
   |
   +--------> CANCELED

PAID -X-> DRAFT (disallowed in example)
CANCELED -X-> PAID
```

Transition `UPDATE`:

```sql
UPDATE optimistic_lock_lab.orders AS o
SET status = 'PAID',
    row_version = o.row_version + 1,
    updated_at = clock_timestamp()
WHERE o.tenant_id = 10
  AND o.order_id = 101
  AND o.row_version = 1
  AND o.status = 'DRAFT'
RETURNING o.status, o.row_version;
```

Two critical predicates:

- `row_version = expected`: catches clients submitting stale snapshots.
- `status = 'DRAFT'`: enforces the rule allowing only `DRAFT` → `PAID`.

If you drop the status guard, a client with the latest version could perform an invalid transition. If you drop the version guard, a client holding an old draft gets no warning about concurrent changes.

### 9.1. Do Not Forget tenant_id

Two tenants can share `order_id = 101` and `row_version = 1`. Filtering only by `order_id` and version could touch multiple rows or the wrong tenant.

Use the full primary key:

```sql
WHERE tenant_id = :authenticated_tenant
  AND order_id = :order_id
  AND row_version = :expected_version
```

The tenant must come from trusted authentication context. Versions are not secret credentials and do not replace authorization.

### 9.2. Business Rules May Also Need DB Constraints

Invariants like `amount >= 0`, uniqueness, and foreign keys should be enforced by `CHECK`, `UNIQUE`, and `FOREIGN KEY` constraints. Version predicates do not replace data-integrity constraints.

---

## 10. Increment Version on Every Protected Mutation

A very common bug: the REST API uses CAS, yet a scheduled job or admin script updates rows **without incrementing `row_version`**.

Example:

```sql
-- Missing version increment.
UPDATE optimistic_lock_lab.orders
SET status = 'CANCELED'
WHERE tenant_id = 10 AND order_id = 102;
```

After this runs, a client holding a form opened at version 1 can still submit a CAS update expecting version 1 and succeed even though status changed. The optimistic locking protocol is broken.

### 10.1. Write Paths to Audit

```text
REST / GraphQL mutations
Admin console
Scheduled jobs
Queue consumers
Import and backfill scripts
Native SQL / stored procedures
ORM bulk updates
Support tools
Database migrations
```

Every write path modifying client-visible state must follow the same version policy.

### 10.2. Should Version Increment on No-Op UPDATEs?

Depends on your contract:

- If every confirmed save must reject stale concurrent forms, increment even when values are identical.
- To avoid creating new tuple versions when values match, use `IS DISTINCT FROM` to skip no-op updates.
- If audits must record every save attempt, skipping the `UPDATE` could omit triggers/events.

Example updating `note` only when it actually changes:

```sql
UPDATE optimistic_lock_lab.orders AS o
SET note = 'verified',
    row_version = o.row_version + 1,
    updated_at = clock_timestamp()
WHERE o.tenant_id = 10
  AND o.order_id = 102
  AND o.row_version = 1
  AND o.note IS DISTINCT FROM 'verified'
RETURNING o.row_version;
```

Here, 0 rows can also mean `note` was already `'verified'`, **not necessarily a stale version**. Define API semantics clearly for no-op saves.

### 10.3. Can a Trigger Manage the Version?

You can build a trigger that automatically increments version on `UPDATE`. Avoid these pitfalls:

- ORM increments version and the trigger increments it again.
- Trigger increments only for certain columns, missing critical ones.
- Native/bulk writers fall out of sync with ORM expectations.
- Application misreads the token returned by `RETURNING`.

Pick one clear strategy—SQL/ORM-managed versions or consistently trigger-managed versions—and test every write path. A trigger that merely increments version **does not detect stale clients** if the `UPDATE` omits the expected-version `WHERE` clause.

---

## 11. READ COMMITTED and CAS UPDATEs

`READ COMMITTED` is PostgreSQL's default isolation level. Statements normally take a snapshot at statement start, while `UPDATE` waits on row locks and re-evaluates `WHERE` against rows committed by other transactions.

Example with two writers both expecting version 4:

```text
A: UPDATE WHERE version=4 -> locks row
B: UPDATE WHERE version=4 -> waits for A

A: writes version=5 and COMMITs

B: resumes, WHERE version=4 no longer matches
B: UPDATEs 0 rows
```

B never overwrites silently just because version was 4 when B started waiting.

### 11.1. MVCC Cannot Guess Client Intent

If B runs:

```sql
UPDATE orders SET note='old draft value' WHERE id=101;
```

then after waiting for A, B succeeds against the current row. Row locking protects storage consistency, **not user intent** when `UPDATE` omits the version guard.

### 11.2. REPEATABLE READ / SERIALIZABLE

Under stricter isolation levels, an `UPDATE` hitting a row modified by another transaction since the snapshot throws `SQLSTATE 40001` (*serialization_failure*) rather than returning 0 rows.

The application must:

- Roll back the failed transaction.
- Retry the **entire transaction** when business rules permit, not just re-run one old statement.
- Enforce retry limits and backoff.
- Never blindly replay a stale user form with the new expected version without merging or re-evaluating.

---

## 12. Optimistic Locking Does Not Replace Atomic UPDATEs

Some problems are best expressed directly as an atomic SQL operation.

Example incrementing a counter:

**Lost-update prone:**

```text
Client A reads stock=10
Client B reads stock=10
A computes 11, UPDATE stock=11
B computes 11, UPDATE stock=11
One increment is lost.
```

**Atomic way:**

```sql
-- Sample against a hypothetical inventory table, not in lab.
UPDATE inventory
SET stock = stock + 1
WHERE sku = 'SKU-A'
RETURNING stock;
```

When the operation is purely "add 1," PostgreSQL increments the row safely in place. There is no need to pull the number to the client and CAS a precomputed total.

### 12.1. Put Guard Conditions Inside the UPDATE

To deduct stock only when available:

```sql
UPDATE inventory
SET stock = stock - 1
WHERE sku = 'SKU-A'
  AND stock >= 1
RETURNING stock;
```

Putting `stock >= 1` **inside the write statement** eliminates the race between checking stock and deducting it.

### 12.2. When Is Versioning Still Needed?

When a user sets **new absolute values** based on an older snapshot, or edits several interdependent fields, optimistic versioning detects stale forms.

When an operation is commutative/additive under the contract, an atomic `UPDATE` is simpler. Combine both techniques where needed.

---

## 13. Returning Clear Conflict Feedback to Users

When CAS fails due to a version mismatch, the application can:

1. **Reject and ask the user to reload:** safest for high-stakes operations.
2. **Show a diff:** stored state, what the user opened, and proposed edits.
3. **Allow controlled merging:** when fields are business-independent.
4. **Auto-retry a commutative operation:** only when proven safe.

Example message:

```text
Could not save because this order was updated by another action.

Version you were editing: 7
Current version: 8

Please reload and review changes before saving again.
```

### 13.1. Anti-Pattern: Reading the New Version and Re-Submitting the Stale Payload

```text
UPDATE WHERE version=7 -> 0 rows
SELECT version -> 8
UPDATE WHERE version=8, payload still from old form -> succeeds
```

This effectively **ignores the conflict**. Someone else's edits get overwritten without review.

Auto-retry only when the operation and invariants allow it, such as safe commutative increments. For status changes, notes, or payment edits, reload and confirm user intent.

### 13.2. Per-Field Merging Is Not Always Safe

A edits `note`; B edits `amount`. Even though they edited different columns, `note` might state an agreement about `amount`. Blindly auto-merging can produce a combined state nobody approved.

Define explicitly which fields are independent, which share an invariant, and when user confirmation is mandatory.

---

## 14. HTTP ETag and If-Match

A REST API can expose versions via `ETag`:

```http
GET /tenants/10/orders/101 HTTP/1.1

HTTP/1.1 200 OK
Content-Type: application/json
ETag: "order-101-v7"

{
  "orderId": 101,
  "status": "DRAFT",
  "note": "Morning delivery",
  "version": 7
}
```

The client sends it back on save:

```http
PUT /tenants/10/orders/101 HTTP/1.1
If-Match: "order-101-v7"
Content-Type: application/json

{
  "status": "DRAFT",
  "note": "Call before delivery"
}
```

The server must:

1. Authenticate caller and verify tenant scope.
2. Validate the precondition token per API contract.
3. Pass the matching version into the CAS `UPDATE`.
4. Check row count / `RETURNING`.
5. `COMMIT` cleanly.
6. Return the new `ETag`/version or an appropriate error.

### 14.1. Common HTTP Status Codes

| Scenario | Typical HTTP status |
| --- | --- |
| Successful `GET` | `200 OK` with `ETag` |
| Successful write | `200 OK` or `204 No Content` |
| `If-Match` no longer matches | `412 Precondition Failed` |
| API requires precondition but header missing | `428 Precondition Required` |
| Business state transition conflict | `409 Conflict` or contract-defined code |
| Resource not found in allowed scope | `404 Not Found` |
| Unauthorized operation | `403 Forbidden` or policy hiding existence |

When APIs pass a JSON version field instead of HTTP `If-Match`, many systems return `409` on conflict. PostgreSQL itself does not dictate HTTP status codes.

### 14.2. Strong ETags and Opaqueness

`If-Match` uses strong comparison semantics. A weak `ETag` (`W/...`) is not equivalent for `If-Match` preconditions. An `ETag` may be an opaque string as long as the server maps it deterministically to the record/version contract.

A version/`ETag` is **not a security credential**. Knowing an order's `ETag` never grants permission to update it.

### 14.3. Never Check If-Match in Application Code Before an Unguarded UPDATE

Wrong:

```text
SELECT current ETag
if equal:
    UPDATE orders SET ...
```

Another writer can alter the row between those two steps. Always enforce the CAS check in the database or use an equivalent properly designed transaction/locking guard.

---

## 15. Java JDBC: PreparedStatement with RETURNING

In Java, a repository method can follow this pattern:

```java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;

public final class OrderRepository {

    // Returns null if CAS predicate does not match.
    public Long updateNote(
            Connection connection,
            int tenantId,
            long orderId,
            long expectedVersion,
            String newNote) throws SQLException {

        String sql = """
            UPDATE optimistic_lock_lab.orders
            SET note = ?,
                row_version = row_version + 1,
                updated_at = clock_timestamp()
            WHERE tenant_id = ?
              AND order_id = ?
              AND row_version = ?
            RETURNING row_version
            """;

        try (PreparedStatement ps =
                     connection.prepareStatement(sql)) {

            ps.setString(1, newNote);
            ps.setInt(2, tenantId);
            ps.setLong(3, orderId);
            ps.setLong(4, expectedVersion);

            try (ResultSet rs = ps.executeQuery()) {
                if (!rs.next()) {
                    return null;
                }

                long newVersion = rs.getLong("row_version");

                if (rs.next()) {
                    throw new SQLException(
                        "Unexpected multiple rows for one order");
                }

                return newVersion;
            }
        }
    }
}
```

Uses Java text blocks (Java 15+). On older Java versions, use standard string literals.

### 15.1. Separating Repository Calls from Service Transactions

When a workflow must update an order and insert into outbox/audit tables, manage the transaction at the service layer:

```text
Service transaction
    |
    +--> CAS UPDATE order
    |       |
    |       +--> no row: rollback/conflict
    |
    +--> INSERT outbox
    +--> check remaining invariants
    |
    +--> COMMIT
```

Repositories should not commit individually when a service requires multi-step atomicity.

### 15.2. Never Confirm Success Before COMMIT

Even after `RETURNING` hands back the new version, the transaction can still fail on `COMMIT` (for instance due to deferred constraints or serialization errors). Return "saved" to the client only after `commit()` succeeds.

### 15.3. Never Concatenate User Input Into SQL Strings

Always use bound parameters. Never write:

```java
String sql = "UPDATE orders SET note='" + userNote
        + "' WHERE order_id=" + orderId;
```

which invites quoting bugs, SQL injection, and type mismatches.

---

## 16. JPA / Hibernate: @Version

Many Java ORMs support optimistic locking via `@Version`.

Example entity with a single-column primary key:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "application_orders")
public class OrderEntity {

    @Id
    private Long orderId;

    @Version
    @Column(name = "row_version", nullable = false)
    private Long rowVersion;

    private String status;
    private BigDecimal amount;
    private String note;
}
```

**Note:** This is an example mapping for a single-key `application_orders` table. The lab table uses a composite key `(tenant_id, order_id)`, so mapping it directly requires `@EmbeddedId`/`@IdClass` and strict tenant scoping.

### 16.1. What Does the ORM Do Under the Hood?

Conceptual SQL generated by the ORM:

```sql
UPDATE application_orders
SET note = ?,
    row_version = ?
WHERE order_id = ?
  AND row_version = ?;
```

The ORM checks affected row counts. When the version mismatches, the framework throws `OptimisticLockException` or a wrapper exception. Note that this may happen only at `flush()` or transaction `COMMIT`, not immediately when calling a setter.

### 16.2. Do Not Manually Increment ORM-Managed Versions

When the ORM manages the version field:

- Do not manually set version to `+1`.
- Do not let native/bulk SQL skip incrementing version.
- Do not combine ORM version increments with a DB trigger incrementing version without an explicit unified design.
- Do not swallow optimistic lock exceptions in the service layer.

### 16.3. Bulk Updates Are a Common Trap

A query like:

```sql
UPDATE application_orders
SET status = 'CANCELED'
WHERE status = 'DRAFT';
```

bypasses the entity manager's `@Version` handling when run as native SQL or JPQL bulk update. If version does not increment, stale entities/drafts still match their old version tokens.

Every writer—including migrations, batch jobs, and admin scripts—must follow the chosen rule.

---

## 17. Transactional Outbox: Updating Data and Emitting Events Together

Suppose transitioning an order to `PAID` must publish an `OrderPaid` event.

If you publish to the message broker **before `COMMIT`**, the database might roll back after the event already went out. If you `COMMIT` first and publish afterward, the server might crash in between and lose the event.

A **transactional outbox** writes the event to a DB table inside the same transaction as the CAS update:

```sql
BEGIN;

WITH changed AS (
    UPDATE optimistic_lock_lab.orders AS o
    SET status = 'PAID',
        row_version = o.row_version + 1,
        updated_at = clock_timestamp()
    WHERE o.tenant_id = 10
      AND o.order_id = 101
      AND o.row_version = 1
      AND o.status = 'DRAFT'
    RETURNING
        o.tenant_id, o.order_id,
        o.status, o.row_version
)
INSERT INTO optimistic_lock_lab.order_outbox (
    tenant_id, order_id, event_type,
    resulting_version, payload
)
SELECT
    tenant_id,
    order_id,
    'OrderPaid',
    row_version,
    jsonb_build_object(
        'status', status,
        'version', row_version
    )
FROM changed
RETURNING event_id, order_id, resulting_version;

COMMIT;
```

If CAS fails to match, CTE `changed` returns 0 rows and `INSERT` into `order_outbox` **inserts nothing**. The application must still verify that the required operation updated one row before reporting success.

If the outbox `INSERT` fails and the transaction rolls back, the order `UPDATE` rolls back too—that is the value of **one atomic transaction**.

### 17.1. Outbox Alone Does Not Guarantee Exactly-Once Delivery

The relay worker can crash after publishing a message but before marking it sent, causing a retry to emit a duplicate. Consumers need idempotency/deduplication.

Attach `tenant_id`, `order_id`, and `row_version` to events to help ordering and diagnostics, while remembering version numbers do not solve all distributed delivery semantics by themselves.

### 17.2. Never Call External APIs While Holding Row Locks

If the CAS `UPDATE` locks a row and the transaction then waits on a remote HTTP call before `COMMIT`, locks and connections stay pinned, worsening contention and latency. An outbox decouples short write transactions from asynchronous delivery.

---

## 18. Idempotency Is Not the Same as Optimistic Locking

**Optimistic locking:** prevents a request from overwriting newer state using a stale version.

**Idempotency:** prevents the same logical operation from executing twice when a request is retried.

Example:

```text
Client sends payment request.
Server executes CAS and COMMITs successfully.
Response is lost due to network timeout.

Client retries the identical request.
Old expected version -> UPDATE affects 0 rows.
```

From the version conflict alone, the client cannot tell whether its **own first request succeeded** or someone else modified the order.

### 18.1. Idempotency Keys

Applications can store request keys alongside results protected by a unique constraint:

```sql
-- Illustrative schema; no need to create in main lab.
CREATE TABLE processed_requests (
    tenant_id INTEGER NOT NULL,
    request_id UUID NOT NULL,
    operation TEXT NOT NULL,
    response_payload JSONB,
    PRIMARY KEY (tenant_id, request_id)
);
```

When the same `request_id` arrives again, the server looks up and returns the committed result instead of re-running the operation. If the same key arrives with a different payload, reject per contract.

Claiming the key and updating business data must share proper transaction/uniqueness guarantees so concurrent retries do not both execute.

### 18.2. A Version Is Not an Idempotency Key

Version 7 can be read concurrently by two distinct actions; it does not uniquely identify a single payment attempt. Systems needing both stale-write protection and retry safety need **both mechanisms**.

---

## 19. Soft Deletes and Versioned DELETEs

Many systems use soft deletes:

```text
deleted_at IS NULL       -> active
deleted_at IS NOT NULL   -> soft-deleted
```

Soft delete is an **`UPDATE`**, so it must also increment `row_version` per policy.

Example on a hypothetical table with `deleted_at`:

```sql
UPDATE application_orders AS o
SET deleted_at = clock_timestamp(),
    row_version = row_version + 1
WHERE o.tenant_id = :tenant_id
  AND o.order_id = :order_id
  AND o.row_version = :expected_version
  AND o.deleted_at IS NULL
RETURNING o.row_version;
```

If B soft-deletes while A has the form open, A cannot accidentally "revive" or overwrite a deleted row.

### 19.1. Physical DELETE Can Also Be Conditional

On the lab table:

```sql
DELETE FROM optimistic_lock_lab.orders AS o
WHERE o.tenant_id = 10
  AND o.order_id = 102
  AND o.row_version = 1
RETURNING o.order_id, o.row_version;
```

This deletes the row **only if the version still matches**. If someone else updated it first, deleting 0 rows prevents wiping out a newer version the client never saw.

Practice this only in the lab; in production, account for FKs, auditing, retention, permissions, and consequences of physical deletes.

### 19.2. Idempotent DELETE vs. Conditional DELETE

A `DELETE` endpoint may promise post-condition "record no longer exists" even across retries. A conditional `DELETE` requires the version token to match.

Do not conflate the two contracts. For sensitive deletions, requiring `If-Match` ensures users delete only the exact version they reviewed.

---

## 20. Versioning Does Not Enforce Multi-Row Invariants

A classic anomaly is **write skew**.

Suppose a hospital requires "at least one doctor on call at all times." Both doctors A and B are on call:

```text
T1 reads: A=on, B=on
T2 reads: A=on, B=on

T1 UPDATEs row A: on_call=false, version 3->4
T2 UPDATEs row B: on_call=false, version 5->6

Two different rows; separate row versions do not conflict.
Result: zero doctors on call.
```

CAS protects **the specific row whose version is checked**. When an invariant spans multiple rows, per-row versioning is insufficient.

### 20.1. Remedies

Depending on your data model:

- Use `SERIALIZABLE` and retry full transactions on serialization failures.
- Lock a shared coordination/parent row.
- Maintain an aggregate root version that every related mutation must claim.
- Enforce constraints when the invariant can be expressed declaratively.
- Use row locking in a deterministic order within short transactions.
- Redesign the schema so the invariant can be enforced atomically.

Never claim "every table has `row_version`, so races are impossible."

---

## 21. Aggregate Root Versioning Across Multiple Tables

Suppose an order has multiple `order_items`. Two users edit different items simultaneously, yet a business rule caps the order's total amount.

Versioning only individual items allows both edits to succeed while violating the total limit.

One model puts the version on the **order root**:

```sql
BEGIN;

-- Claim the aggregate root's version.
UPDATE orders
SET row_version = row_version + 1
WHERE order_id = :order_id
  AND row_version = :expected_version
RETURNING row_version;

-- If not exactly one row: ROLLBACK.
-- If one row: update order_items, recompute total,
-- validate business invariants, write outbox if needed.

COMMIT;
```

These tables are conceptual. Production implementations also need tenant keys, authorization, FKs, transaction error handling, and constraints.

### 21.1. Why Claim the Root Version Before Modifying Children?

Two transactions editing items on the same order must contend on **the single root row**. Unless the root version advances in the same transaction as child changes, one writer can mutate items without another client noticing the aggregate changed.

### 21.2. What If Only Certain Child Fields Change?

Define clearly:

- Which changes belong to the aggregate.
- Which changes must bump the root version.
- Which fields may merge independently.
- Whether database constraints should also enforce invariants.

Too coarse a version scope causes excessive conflicts; too narrow a scope misses real invariants.

---

## 22. Batch UPDATEs with Multiple Expected Versions

Suppose a client updates two orders with distinct expected versions. An `UPDATE ... WHERE order_id IN (101,102)` cannot check per-row tokens.

Use a `VALUES` CTE:

```sql
WITH expected(tenant_id, order_id, row_version) AS (
    VALUES
        (10, 101::BIGINT, 1::BIGINT),
        (10, 102::BIGINT, 1::BIGINT)
)
UPDATE optimistic_lock_lab.orders AS o
SET note = 'Batch checked',
    row_version = o.row_version + 1,
    updated_at = clock_timestamp()
FROM expected AS e
WHERE o.tenant_id = e.tenant_id
  AND o.order_id = e.order_id
  AND o.row_version = e.row_version
RETURNING o.tenant_id, o.order_id, o.row_version;
```

Only rows matching both key and expected version are updated.

### 22.1. Partial Success

If one of the two orders changed version, the `UPDATE` still modifies whichever row matched. PostgreSQL does not automatically roll back the whole batch because one row failed `WHERE`.

If business logic requires **all-or-nothing**, run inside a transaction, verify both the count and exact set of updated keys, and `ROLLBACK` if any row is missing.

### 22.2. Watch for Duplicates in UPDATE FROM Sources

If CTE `expected` contains two rows with the same `(tenant_id, order_id)`, the join matches multiple source rows to one target row, with undefined choice of which source row wins in PostgreSQL. Validate input uniqueness or stage into a table with a `PRIMARY KEY`.

### 22.3. Batch Execution Does Not Exempt Version Rules

Backfill jobs, SQL migrations, and admin scripts must still increment versions when changing representations that clients may concurrently edit; otherwise API optimistic protection breaks.

---

## 23. UPSERT and Version Guards

`INSERT ... ON CONFLICT DO UPDATE` resolves unique-key insert races, **not stale overwrites**.

Risky example:

```sql
INSERT INTO application_orders(order_id, note, row_version)
VALUES (101, 'new value', 1)
ON CONFLICT (order_id)
DO UPDATE SET note = EXCLUDED.note;
```

If the record already exists with newer data, `DO UPDATE` blindly overwrites it without checking version.

PostgreSQL allows a `WHERE` clause on `DO UPDATE`:

```sql
-- Illustrative sample, not lab schema.
INSERT INTO application_orders (
    order_id, note, row_version
)
VALUES (101, 'new value', 1)
ON CONFLICT (order_id) DO UPDATE
SET note = EXCLUDED.note,
    row_version = application_orders.row_version + 1
WHERE application_orders.row_version = 1
RETURNING order_id, row_version;
```

Still, note:

- The `INSERT` path runs when there is no conflict—wrong for update-only APIs.
- Initial vs. expected version semantics need clear contracts, especially when expected version is not 1.
- If `DO UPDATE` fails its `WHERE`, `RETURNING` emits no row even though the conflicting row was locked for evaluation.
- `UPSERT` does not replace status guards, tenant scoping, authorization, or idempotency.

For update-only endpoints, `UPDATE ... WHERE row_version = ? RETURNING` is simpler and safer.

---

## 24. ABA: Value Returns to Old State, Yet Version Must Still Differ

The **ABA problem** happens when a value changes A → B → A, fooling checks that compare only **current values** into thinking nothing changed.

Example:

```text
Status DRAFT, version 5
    |
    v
Status PAID,  version 6
    |
    v
Status DRAFT, version 7  (assuming policy permits reverting)
```

A client that saw `DRAFT` at version 5 and later checks `status = 'DRAFT'` might think nothing happened. Version 7 proves an intermediate change occurred.

### 24.1. Never Reset Versions

If code resets version from 7 back to 5 when status reverts to `DRAFT`, an old client passes CAS, defeating stale detection.

Versions must increase **monotonically across a logical object's lifecycle**. If an object can be deleted and recreated with the same business ID, include a generation token or distinct surrogate ID to avoid colliding with prior incarnations.

---

## 25. Retries and Database Error Signals

Distinct failure signals:

| Event | How it surfaces |
| --- | --- |
| CAS version mismatch | 0 rows updated |
| Row lock wait exceeded | Lock timeout / exception |
| Deadlock | `SQLSTATE 40P01` |
| Serialization failure | `SQLSTATE 40001` |
| Duplicate key | `SQLSTATE 23505` |
| `CHECK` violation | `SQLSTATE 23514` |
| Foreign key violation | `SQLSTATE 23503` |

### 25.1. When Is Auto-Retry Appropriate?

| Workflow | Typical sensible policy |
| --- | --- |
| Text-editing form | Reject, reload, or offer merge |
| Commutative increment | Atomic `UPDATE` or controlled retry |
| Order approval | Re-check status and permissions |
| Payment | Idempotency and state machine |
| `SERIALIZABLE` transaction hitting `40001` | Bounded retry of **entire transaction** |
| Request timeout after `COMMIT` | Query operation status / idempotency store |
| Audit logging | Never drop or overwrite historical events |

### 25.2. Never Retry by Dropping WHERE version

This destroys protection:

```text
Attempt 1: UPDATE WHERE version=7 -> 0 rows
Attempt 2: UPDATE WHERE id=101      -> 1 row
```

Never add an "unguarded fallback write" just to make requests look successful.

### 25.3. Never Hold Transactions Open Waiting on Network APIs

If a transaction runs a CAS `UPDATE` holding a row lock and then calls a remote API before `COMMIT`, competing requests wait. Keep transactions short and offload external effects via outbox where appropriate.

---

## 26. Performance, Indexes, and HOT Updates

Optimistic locking adds a version predicate, yet normally does **not** need a dedicated index on `row_version` when the `WHERE` clause already uses the `PRIMARY KEY`.

Example:

```sql
WHERE tenant_id = ?
  AND order_id = ?
  AND row_version = ?
```

The `PRIMARY KEY (tenant_id, order_id)` locates at most one row, and then checks `row_version`.

### 26.1. A Separate Index on row_version Can Hurt Writes

Indexing `row_version` means **every `UPDATE` incrementing `row_version` modifies an indexed column**, preventing Heap-Only Tuple (HOT) updates and adding index/WAL overhead.

Never index a column solely because it appears in `WHERE`. Check query plans, selectivity, and write workload.

### 26.2. Optimistic Locking Still Creates New Tuple Versions

Under PostgreSQL MVCC, a CAS `UPDATE` still:

- Creates a new tuple version.
- Generates WAL on logged tables.
- Maintains affected indexes.
- Leaves dead tuple versions for pruning/`VACUUM`.

Versioning ensures logical correctness, not zero-cost physical writes.

### 26.3. Hot Rows and Conflict Rates

When one row is updated incessantly:

- CAS conflicts climb.
- Row lock waits grow.
- Retry storms degrade throughput further.
- Tweaking version types does not solve physical contention.

Consider splitting aggregate boundaries, using atomic `UPDATE`s for increments, serializing via queues/command processors, or event-sourcing patterns. Never drop version checks just to reduce conflict counts.

### 26.4. Metrics to Monitor

Track:

- CAS attempts and successes.
- Confirmed version conflicts.
- Other conditional 0-row failures.
- Retry counts and retry success rates.
- HTTP `409`/`412` counts.
- Transaction duration and lock waits.
- Deadlock and serialization error counts.
- User reload/merge frequency.
- Write throughput and WAL volume.

Never equate all 0-row `UPDATE`s with version conflicts when `WHERE` includes status, tenant, or business guards.

---

## 27. Testing Concurrent Requests Properly

A single-connection unit test checking one successful `UPDATE` is insufficient. You need integration tests using **two real connections**.

### 27.1. Happy-Path Test

- Order starts at version 1.
- Update expects 1.
- Returns version 2.
- Content matches.
- Commit succeeds.

### 27.2. Stale-Form Test

- A and B both read version 1.
- B commits `UPDATE` advancing to version 2.
- A attempts `UPDATE` expecting 1.
- A receives 0 rows / conflict.
- B's data is untouched.

### 27.3. Simultaneous Contention Test

Use a barrier/latch so two workers fire `UPDATE` expecting version 1 at the same instant. Depending on isolation and lock acquisition:

- One writer commits successfully.
- The other writer must never commit a second mutation based on **the same stale expected version** on that row.
- It returns 0 rows or a concurrent transaction error handled per contract.

### 27.4. Edge Cases

- Wrong tenant or unauthorized caller.
- Non-existent order.
- Status guard mismatch.
- Missing version in form.
- Stale version.
- Two different fields on the same aggregate.
- Soft delete occurring while form is open.
- Partial batch write.
- Transaction rollback after `UPDATE`.
- Outbox insert failure.
- Client timeout after `COMMIT`.
- Same idempotency key sent twice.
- Native/ORM bulk DML bypassing version.
- Deadlock or serialization failure.

Never rely on random sleeps to "simulate concurrency": tests become flaky under scheduler jitter. Use deterministic synchronization barriers.

---

## 28. Common Implementation Mistakes

| Mistake | Risk | Fix |
| --- | --- | --- |
| `UPDATE` by ID only | Stale overwrite | Add expected version |
| `SELECT` version then unguarded `UPDATE` | Race between check and use | Single-statement CAS |
| Not incrementing version on every writer | Stale drafts still match | Standardize policy across all writers |
| Checking only for SQL errors | 0-row `UPDATE` treated as success | Check row count / `RETURNING` |
| Re-reading new version and re-sending old payload | Silently defeats conflict detection | Reload/merge deliberately |
| Retrying by dropping version check | Overwrites newer edits | Never drop the guard |
| `updated_at` as concurrency token with lost precision | Missed concurrent updates | Use `BIGINT` or opaque token |
| `ctid`/`xmin` as durable API tokens | Tied to internal tuple storage | Application version column |
| Soft delete without bumping version | Stale form revives deleted row | Bump token + `deleted_at IS NULL` |
| ORM `@Version` bypassed by bulk SQL | Inconsistent protection | Audit all write paths |
| Per-row version for multi-row invariant | Write skew | Aggregate root, locks, or `SERIALIZABLE` |
| Batch without checking full updated row count | Partial success committed | Transaction + rollback on mismatch |
| Publishing event before `COMMIT` | Event emitted for rolled-back data | Transactional outbox |
| `COMMIT` before writing outbox | Event lost on crash | Write in same transaction |
| Treating version as idempotency key | Cannot tell if prior retry committed | Separate idempotency key |
| Omitting `tenant_id` in `WHERE` | Cross-tenant write bug | Full composite key and authz |
| Treating version token as a secret | No access control | Separate authn/authz |
| Indexing `row_version` without measuring | Extra index writes, disables HOT | Look up by PK, then check version |
| Holding `FOR UPDATE` while user edits form | Long locks and connections | Optimistic locking |
| No two-session concurrency tests | Races go unnoticed | Two-connection barrier tests |
| Reporting success before `COMMIT` | False confirmation | Respond only after `COMMIT` |
| Ignoring `40001`/`40P01` | Failed transactions unhandled | Classify SQLSTATE and retry/log |
| 64-bit version in JS `Number` losing precision | CAS fails on large integers | Serialize as opaque string when needed |

---

## 29. Practice Exercises

### Exercise 1 — Analyzing Lost Updates

Clients A and B both read `note='A'` at version 3. B writes `note='B'`, then A writes `note='C'`. Show the final state if `UPDATE` filters only by ID vs. using CAS.

### Exercise 2 — CAS with RETURNING

On the lab table, update `(10,102)`'s note from version 1 to 2. Re-run the same `UPDATE` expecting version 1; explain why it returns 0 rows.

### Exercise 3 — Two Sessions

Open two connections, both reading order 101 at version 1. B saves first, A saves second. Identify winner, loser, and final row state.

### Exercise 4 — Row Locks vs. Optimistic Versions

Write a short transaction using `SELECT ... FOR UPDATE`. Why should you never hold that transaction open while a user edits a form for 30 minutes?

### Exercise 5 — State Transitions

Allow only `DRAFT` → `PAID`. Write an `UPDATE` checking `status='DRAFT'` and expected version. What happens if status is already `CANCELED` even with a matching version?

### Exercise 6 — Diagnosing 0-Row UPDATEs

List at least five reasons an `UPDATE` filtering by tenant/id/version/status returns 0 rows. Why must diagnostic classification respect tenant authorization?

### Exercise 7 — No-Op and IS DISTINCT FROM

Write an `UPDATE` changing `note` only if it differs from the new value. What happens to `row_version` and audits if `note` already equals that value?

### Exercise 8 — updated_at and Versions

Explain why `now()` inside a single transaction fails as a strictly increasing token per `UPDATE`. Why can JSON drop microseconds?

### Exercise 9 — Avoiding xmin/ctid as Durable Tokens

Distinguish system columns from an application `row_version`. Why do `UPDATE`s or table rewrites change `ctid`?

### Exercise 10 — Atomic Increments

Write an `UPDATE` incrementing `stock` by 1 and an `UPDATE` deducting 1 when `stock >= 1`. Why are these safer than `SELECT`ing and writing an absolute value?

### Exercise 11 — JDBC

Write a `PreparedStatement` with bound parameters and `RETURNING row_version`. How do you handle an empty `ResultSet`? When does the service `COMMIT`?

### Exercise 12 — JPA @Version

Describe `@Version` mechanics and when `OptimisticLockException` can be thrown. What risk does a native bulk `UPDATE` that skips incrementing version introduce?

### Exercise 13 — HTTP If-Match

`GET` returns `ETag` v7; `PUT` sends `If-Match` v7 after the DB reached v8. Which HTTP status fits? What if `If-Match` is omitted when required by the API?

### Exercise 14 — Retrying Stale Forms

A developer "fixes" conflicts by reading the latest version and re-sending the stale form payload. Why does that defeat optimistic locking?

### Exercise 15 — Idempotency

The server commits successfully, the response times out, and the client retries. Why can't a CAS conflict tell whether the first request succeeded? Propose an idempotency key design.

### Exercise 16 — Transactional Outbox

Write a CTE `WITH changed AS (UPDATE ... RETURNING ...) INSERT outbox SELECT ... FROM changed`. If CAS returns 0 rows, what goes into the outbox? If the outbox `INSERT` errors, what happens to the order after rollback?

### Exercise 17 — Soft Delete

Design a `deleted_at` `UPDATE` with a version guard. Why is `deleted_at IS NULL` also needed even if the app only queries active rows?

### Exercise 18 — Conditional DELETE

Write a `DELETE` filtering by tenant/id/version with `RETURNING`. Compare with deleting solely by ID when someone just edited the record.

### Exercise 19 — Write Skew

Two doctors request time off simultaneously, each CAS-updating a different row. Why can both succeed and break the invariant? Propose protections.

### Exercise 20 — Aggregate Root

An order has multiple items. Design a transaction modifying an item while claiming the order root's version. Why must child changes never commit without bumping the root version?

### Exercise 21 — Batching

Use `VALUES(tenant_id, order_id, expected_version)` to update two rows. If only one row matches while business logic requires all-or-nothing, how must the transaction handle it?

### Exercise 22 — Duplicates in UPDATE FROM

If the `expected` source contains two rows with the same key, what goes wrong? Explain staging into a table with a `PRIMARY KEY`.

### Exercise 23 — UPSERT

Why can `ON CONFLICT DO UPDATE` without a version guard overwrite newer data? Why shouldn't an update-only endpoint silently insert?

### Exercise 24 — ABA

A record transitions A→B→A with versions 5→6→7. If a client checks only whether status is A, what does it miss? Why never reset versions?

### Exercise 25 — Multi-Tenant

Two tenants both have `order_id` 101 at version 1. Write a CAS `UPDATE` touching only tenant 10. Does version replace authorization?

### Exercise 26 — SERIALIZABLE Retries

Upon `SQLSTATE 40001`, outline rollback, backoff, and full-transaction retry. Why must you never drop expected version during retry?

### Exercise 27 — Hot Rows

One order is updated continuously by workers, raising conflicts and lock waits. Propose three ways to relieve contention without sacrificing correctness.

### Exercise 28 — Indexing Version

Why is `PRIMARY KEY (tenant_id, order_id)` usually enough for CAS lookups? How does adding a separate index on `row_version` hinder HOT updates?

### Exercise 29 — Concurrent Test

Design a two-connection barrier test both updating version 1. What are the valid outcomes per isolation level? What proves two changes never both commit from the same version?

### Exercise 30 — PATCH API Review

Build a review checklist covering: expected version input, tenant auth, status guard, CAS, `RETURNING`, `COMMIT`, conflict UX, outbox, idempotency, retries, bulk writers, monitoring, and concurrency tests.

---

## 30. Implementation Checklist

| Question | What to define |
| --- | --- |
| Which resource must avoid stale overwrites? | Aggregate boundary and business rules |
| Exact identifier? | Primary key and tenant scope |
| How is version stored? | `BIGINT` or opaque token |
| When does version increment? | Every protected mutation |
| Who manages version? | SQL/ORM/trigger, consistently |
| How do clients send expected version? | JSON version field or `If-Match` |
| Is the token mandatory? | Reject if endpoint requires it |
| Is the guard atomic? | Key + version in `WHERE`, incremented in same statement |
| Are status/business guards present? | Included in `UPDATE` |
| Is tenant isolation enforced? | Authn/authz/RLS |
| Are affected row counts checked? | `RETURNING` / exact count |
| How are 0 rows handled? | Classify conflict vs. not found vs. forbidden |
| When is success returned? | Only after `COMMIT` |
| How are stale forms handled? | Reload, compare, merge, or reject |
| Are retries safe? | Only when operation merges safely |
| Is idempotency handled? | Request keys and stored outcomes |
| Are there off-DB events? | Transactional outbox |
| Are there child tables? | Root version / invariants in one transaction |
| Are there multi-row invariants? | Constraints / locks / `SERIALIZABLE` |
| Soft or physical deletes? | Conditional delete and retention |
| Batch jobs / native SQL? | Follow version policy |
| Using JPA `@Version`? | Avoid bypassing or double-incrementing |
| JS clients? | Preserve 64-bit tokens as strings when needed |
| Index on version needed? | Measure plan and write amplification |
| Hot rows present? | Monitor conflicts, lock waits, retries |
| Concurrent tests? | Two connections, barrier, single winner |
| Failure tests? | Rollback, lost response, conflict, `40001` |
| Monitoring? | Success/conflict rates and latency |

## Conclusion

**Application-level optimistic concurrency control with data versions** lets PostgreSQL catch writes submitted from stale drafts without holding row locks across human think time.

At its heart is one compare-and-swap statement:

```sql
UPDATE orders
SET business_data = :new_value,
    row_version = row_version + 1
WHERE primary_key = :id
  AND row_version = :expected_version
RETURNING row_version;
```

Key takeaways:

- **MVCC and row locks** protect database operations, yet cannot detect stale forms across separate transactions on their own.
- **Versions must be checked in `WHERE` and incremented in the same `UPDATE`**; `SELECT`ing first then running an unguarded `UPDATE` leaves a race window.
- **0 rows updated is not success**, nor does it automatically prove a version conflict was the sole cause.
- **Every writer**—APIs, ORMs, batch jobs, migrations, and admin tools—must honor the version policy.
- **Business guards, tenant scope, permissions, and constraints** must accompany version checks.
- **Automatic retries** must never bypass user conflict detection.
- **Idempotency and outboxes** protect retries and external side effects; they are distinct from optimistic locking.
- **Single-row versions do not protect multi-row invariants**; combine aggregate roots, locking, constraints, or `SERIALIZABLE` where needed.
- **JDBC, JPA `@Version`, and HTTP `If-Match`** are different implementations of one unified protocol.
- **Two-session concurrency tests and conflict-rate monitoring** verify your application never silently overwrites newer data.

By defining clear resource boundaries, version tokens, CAS predicates, and conflict handling, PostgreSQL applications preserve concurrent users' changes reliably without turning every edit into a long-lived locking transaction.
