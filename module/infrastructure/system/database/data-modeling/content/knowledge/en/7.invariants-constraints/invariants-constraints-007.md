# Pre-Write Checks and Contention When Concurrent Operations Occur

A system can validate input data thoroughly and still write invalid data when multiple requests execute simultaneously. For example, two customers simultaneously order the last chair in stock. Both requests read one chair available, both pass the check, and both create an order. As a result, the system sells more inventory than actually exists.

The problem lies in the window between checking and writing data. A condition that holds at read time may no longer hold when another transaction modifies the data. This is a common form of **race condition** in concurrent processing. To protect data invariants, checking and updating must be combined into an atomic operation, protected with appropriate locking, or enforced via database constraints.

Within the scope of **DATABASE_DATA_MODELING**, this lesson explains how to perform pre-write checks, identify contention, choose transactions and synchronization mechanisms, and design constraints to protect data even when multiple applications write concurrently.

## Learning Objectives

After this lesson, you will be able to:

- Explain why application-level pre-write checks are insufficient to guarantee invariants across multiple transactions.
- Identify race conditions and TOCTOU (time-of-check to time-of-use) bugs.
- Convert simple check conditions into atomic update statements.
- Choose among constraints, optimistic locking, pessimistic locking, and transaction isolation levels.
- Handle limits on inventory, capacity, balances, and multi-row rules.
- Design retries, idempotency, and reproducible concurrency tests.

## 1. Invariants and check timing

An **invariant** is a condition that must always hold true for the data state managed by the system. Examples:

- Inventory quantity must not be negative.
- Account balance must not fall below the allowed minimum.
- Every order number must be unique.
- An enrollment must reference an existing student and course offering.
- Active enrollments must not exceed class capacity.
- Transaction total must match line items and pricing rules.

Pre-write checking is the step that verifies input data or current state meets business conditions. However, distinguish two kinds of checks:

- **Input validation:** does the data match the required format and value domain, e.g. quantity is a positive integer.
- **Shared-state checking:** does the resource or state in the database still satisfy the condition, e.g. inventory has enough stock to sell or a class still has open seats.

Input validation can usually run early in the application for fast feedback. Shared-state checking must be tied to the write operation with an appropriate synchronization mechanism, because another transaction can modify that state.

### 1.1. TOCTOU: checking right, using at the wrong time

TOCTOU stands for *time of check to time of use*: the interval between checking a condition and acting on the result of that check. If state changes during that window, a decision based on the stale check can be wrong.

Example with one item in stock:

| Time | Transaction A | Transaction B |
|---|---|---|
| T1 | Read `available = 1` | |
| T2 | | Read `available = 1` |
| T3 | Check sufficient stock: true | |
| T4 | | Check sufficient stock: true |
| T5 | Create order | |
| T6 | | Create order |
| T7 | Both orders get confirmed | |

Both transactions evaluated against the same stale state. If each transaction simply reads and then writes separately, the system can confirm two orders for a single item.

### 1.2. Race conditions are not only two writes to the same row

Contention can happen when:

- Two transactions update the same row.
- Two transactions check the same aggregate condition and write to different rows.
- One transaction reads a set of rows while another inserts or deletes rows, changing the query result.
- A request is resent after a timeout even though the first attempt already committed.
- Multiple services write to the same table or manage the same business resource.

Therefore, inspecting individual `INSERT` or `UPDATE` statements in isolation is not enough. You must analyze the entire business operation and how transactions may interleave.

## 2. Why `SELECT` followed by `UPDATE` can fail

Suppose we have an inventory table:

```sql
CREATE TABLE inventory (
    product_id BIGINT PRIMARY KEY,
    available INTEGER NOT NULL CHECK (available >= 0)
);
```

An error-prone approach is:

```sql
SELECT available
FROM inventory
WHERE product_id = 101;

-- Application checks available >= requested_quantity.

UPDATE inventory
SET available = $1 - 1
WHERE product_id = 101;
```

Here `$1` is the `available` value read earlier by the application. If both transactions read `1`, both can write `0` and both create orders; the non-negative constraint still holds, yet the system has confirmed two orders for one unit. If subtracting directly from the current value without a sufficient-stock condition, one transaction can push the count negative and be rejected by `CHECK`.

`CHECK (available >= 0)` prevents negative inventory, but the `UPDATE` lacks an `available >= 1` predicate paired with the subtraction. More importantly, checking logic and mutation logic were not combined into a single explicit atomic decision.

Never rely on “reading right before writing” to eliminate race conditions. That window still exists, and another transaction can interleave.

## 3. Atomic updates via conditions in the write statement

For simple conditions on the same row, a good approach is embedding the condition directly in the `UPDATE` statement. The database evaluates the condition and applies the change as a single atomic operation on the updated row.

### 3.1. Conditional inventory deduction

```sql
UPDATE inventory
SET available = available - $1
WHERE product_id = $2
  AND $1 > 0
  AND available >= $1
RETURNING available;
```

The application passes the purchase quantity in `$1` and the product ID in `$2`:

- If one row is returned, stock was deducted successfully.
- If zero rows are returned, the product does not exist, input quantity is invalid, or stock is insufficient. The application can query further to distinguish causes if detailed messaging is needed.

The key point is that `available >= $1` is checked at the exact moment of subtraction. If two transactions compete for one unit, one updates first; the other re-evaluates the condition against the updated state and cannot subtract into negative territory.

### 3.2. Conditional balance transfer

For accounts, a similar statement can be used:

```sql
UPDATE account
SET balance = balance - $1
WHERE account_id = $2
  AND $1 > 0
  AND balance >= $1
RETURNING balance;
```

The predicate ensures the balance is not overdrawn during the update. The table should still have a constraint:

```sql
ALTER TABLE account
    ADD CONSTRAINT account_balance_nonnegative
    CHECK (balance >= 0);
```

The predicate in `UPDATE` handles business logic and returns success/failure; `CHECK` acts as the final guardrail against invariant-violating writes from any other path.

### 3.3. Creating an order in the same transaction

Deducting inventory and creating an order form one business operation with multiple changes. If stock deduction succeeds yet inserting the order fails, data must not remain half-changed. Use a single transaction:

```sql
BEGIN;

UPDATE inventory
SET available = available - $1
WHERE product_id = $2
  AND $1 > 0
  AND available >= $1
RETURNING available;

-- Application must confirm UPDATE returned exactly one row.
-- Otherwise, ROLLBACK and return out-of-stock / invalid-input error.

INSERT INTO sales_order (order_id, customer_id, status)
VALUES ($3, $4, 'CONFIRMED');

INSERT INTO order_line (order_id, line_no, product_id, quantity)
VALUES ($3, 1, $2, $1);

COMMIT;
```

The SQL snippet illustrates control flow: the application must check the row count returned by `UPDATE ... RETURNING` before continuing; if no row is returned, the transaction must roll back. For multi-product orders, deduct inventory for every product inside the same transaction and roll back the whole transaction if any line lacks stock.

Transactions guarantee that changes commit together or roll back together. They do not automatically make prior checks safe; predicates must be placed properly and related rows must be locked/updated under a consistent strategy.

## 4. Constraints as data-protection guardrails

Application checks give friendly feedback, yet data often has multiple write paths: APIs, batch jobs, imports, admin tools, message consumers, or data-fix tasks. Database constraints protect invariants regardless of which write path is used.

### 4.1. Common constraints

| Constraint | Protected invariant | Example |
|---|---|---|
| `NOT NULL` | Required attribute must have a value | `customer_id NOT NULL` |
| `CHECK` | Condition on columns of a row | `quantity > 0`, `balance >= 0` |
| `UNIQUE` | No duplicate values/combinations per rule | `UNIQUE (tenant_id, external_code)` |
| `PRIMARY KEY` | Each row has a unique non-null identifier | `PRIMARY KEY (order_id, line_no)` |
| `FOREIGN KEY` | Reference points to an allowed existing row | `customer_id REFERENCES customer(customer_id)` |
| Exclusion constraint | Disallows conflicting values/ranges by operator | Prevents two room bookings for the same room overlapping in time |

### 4.2. Constraints and cross-row checks

A standard `CHECK` evaluates values within a single row. Do not write a `CHECK` that depends on child row counts or queries another table to enforce multi-row rules. PostgreSQL does not safely enforce cross-table `CHECK` conditions under concurrent writes.

For example, the rule “a class has at most 30 active students” cannot be enforced solely with a `CHECK` on each enrollment row. You need a class-level synchronization mechanism, controlled counter, parent row lock, or transaction with an appropriate isolation level.

### 4.3. `UNIQUE` protects against duplicates under contention

If each customer may have only one profile per external provider, use a constraint:

```sql
ALTER TABLE external_customer
    ADD CONSTRAINT one_external_customer_per_source
    UNIQUE (source_system, external_customer_id);
```

Two transactions may both check “this code does not exist yet” and both attempt to insert. `UNIQUE` ensures the database lets only one transaction succeed; the other receives a unique-violation error. A prior `SELECT` check cannot replace this constraint.

If you want to handle the already-exists case, use `INSERT ... ON CONFLICT`:

```sql
INSERT INTO external_customer
    (source_system, external_customer_id, customer_name)
VALUES
    ($1, $2, $3)
ON CONFLICT (source_system, external_customer_id)
DO NOTHING;
```

`ON CONFLICT` handles conflicts explicitly. If updating an existing record is desired, use `DO UPDATE`, while clearly defining which fields may be overwritten and how concurrent updates from two sources are resolved.

## 5. Pessimistic locking: locking before modifying

Pessimistic locking assumes contention can occur and locks relevant rows before reading/writing. Other transactions trying to update or lock the same rows must wait until the lock is released.

### 5.1. `SELECT FOR UPDATE`

Example handling inventory using row locking:

```sql
BEGIN;

SELECT available
FROM inventory
WHERE product_id = $1
FOR UPDATE;

-- Application checks available >= requested_quantity.

UPDATE inventory
SET available = available - $2
WHERE product_id = $1
  AND $2 > 0
  AND available >= $2;

-- Application must confirm exactly one row was updated.

COMMIT;
```

`FOR UPDATE` locks the matched inventory row until the transaction ends. Other transactions wanting to update or lock that row must wait. Once the lock is acquired, the transaction reads the latest state consistent with the active isolation level and can perform checks and updates.

### 5.2. When to use pessimistic locking?

Appropriate when:

- Contention is frequent and retry costs are high.
- Business logic needs to read multiple fields before deciding on the update.
- A parent row must be locked as a synchronization point for multiple child rows.
- Transactions are short and finish quickly while holding locks.

Drawbacks:

- Other transactions must wait, reducing throughput when many requests contend for the same resource.
- Holding locks too long can cause timeouts and cascading slowdowns.
- Locking multiple rows in inconsistent orders can cause deadlocks.
- `SELECT ... FOR UPDATE` only locks existing matched rows; it does not lock non-existent rows or future rows matching the query predicate.

Never call external APIs, send emails, wait on users, or run slow tasks while holding database locks. Keep transactions short and commit/roll back early.

### 5.3. Locking a parent row to protect a condition over child rows

Suppose a course offering has a seat limit. Simply counting active enrollments and inserting lets two transactions both see one open seat.

One approach is locking the `course_offering` row as a synchronization point:

```sql
BEGIN;

SELECT capacity
FROM course_offering
WHERE offering_id = $1
FOR UPDATE;

SELECT COUNT(*)
FROM enrollment
WHERE offering_id = $1
  AND status IN ('PENDING', 'CONFIRMED');

-- Application inserts only if active count < capacity.

INSERT INTO enrollment (student_id, offering_id, status)
VALUES ($2, $1, 'PENDING');

COMMIT;
```

Every write path creating enrollments for the same class must follow the same parent-row locking protocol. If one service skips this lock, the guarantee breaks. Both a transaction and checking the condition after acquiring the lock are required.

### 5.4. Conditional capacity counter

For high workloads, maintain `enrolled_count` on the class row and update it atomically:

```sql
UPDATE course_offering
SET enrolled_count = enrolled_count + 1
WHERE offering_id = $1
  AND enrolled_count < capacity
RETURNING enrolled_count;
```

If no row is returned, the class is full or does not exist. Incrementing the counter and inserting the `Enrollment` must happen in the same transaction; if the insert fails, roll back the counter too. When cancelling an enrollment, decrement the counter in the same transaction. The table should include `CHECK (enrolled_count >= 0 AND enrolled_count <= capacity)`.

The counter is derived data and requires a reconciliation process against actual enrollments to detect drift from legacy bugs or non-compliant write paths.

## 6. Optimistic locking: detecting conflicts on write

Optimistic locking does not hold row locks during reading and processing. Instead, writes include a previously read version or value. If another transaction modified the row in the meantime, the update matches zero rows and is treated as a conflict.

### 6.1. Version column

```sql
CREATE TABLE product_price (
    product_id BIGINT PRIMARY KEY,
    price NUMERIC(14, 2) NOT NULL CHECK (price >= 0),
    version BIGINT NOT NULL DEFAULT 0
);
```

The application reads `price` and `version`, computes the new price, and then updates:

```sql
UPDATE product_price
SET price = $1,
    version = version + 1
WHERE product_id = $2
  AND version = $3
RETURNING price, version;
```

If one row is returned, the update succeeded. If zero rows are returned, the version changed or the product no longer exists. The application can re-read, recompute, and retry per policy, or report a conflict for user confirmation.

### 6.2. When to use optimistic locking?

Appropriate when:

- Conflicts are infrequent.
- Reads heavily outnumber contending writes.
- You want to avoid holding locks while the application processes.
- Changes can be detected and resolved when data has shifted.

Unsuitable when conflicts occur constantly and retries amplify load. For multi-row rules, a version column on a single row is also insufficient if transactions can modify different rows while jointly violating a shared invariant. In that case, a shared synchronization point or stronger isolation level is needed.

## 7. Transaction isolation and concurrency anomalies

Transaction isolation defines how transactions observe changes made by other transactions. Higher isolation levels prevent additional anomalies, usually at the cost of extra waiting or higher rates of transaction aborts requiring retries.

### 7.1. Anomalies to understand

- **Dirty read:** reading uncommitted data from another transaction.
- **Non-repeatable read:** reading the same row twice and seeing different values because another transaction committed an update.
- **Phantom read:** re-running the same query predicate and seeing added or missing rows because another transaction committed inserts/deletes.
- **Lost update:** two transactions update based on the same old value and one overwrites the other's change.
- **Write skew:** two transactions read the same state set and update different rows, yet their combined changes violate an invariant.

### 7.2. Common isolation levels

| Isolation level | General characteristics | Design considerations |
|---|---|---|
| Read Uncommitted | Allows reading uncommitted data per SQL spec; some DBMSs implement it like a higher level | Avoid unless dirty reads are acceptable |
| Read Committed | Each statement sees data committed as of statement start | Common; a `SELECT` before `UPDATE` can still race |
| Repeatable Read | Keeps a stable snapshot within the transaction per DBMS implementation | Prevents non-repeatable reads; still must understand DBMS-specific write skew and serialization errors |
| Serializable | Outcomes of successful transactions match some serial execution order | May abort transactions on conflicts; application must retry the full transaction |

Identical isolation-level names do not guarantee identical implementation behavior across DBMSs. Read your DBMS documentation and test under realistic workloads.

In PostgreSQL, `READ UNCOMMITTED` behaves as `READ COMMITTED`. `REPEATABLE READ` uses a stable snapshot and prevents phantom reads in PostgreSQL, yet certain serialization anomalies such as write skew can still occur. `SERIALIZABLE` uses Serializable Snapshot Isolation and may abort a transaction with a serialization error to prevent those anomalies.

### 7.3. Write skew example

An on-call shift requires at least one doctor on duty. Doctors A and B are both on duty. Two concurrent transactions run:

1. A reads that two doctors are on duty.
2. B also reads that two doctors are on duty.
3. Transaction A turns off A's on-duty status.
4. Transaction B turns off B's on-duty status.
5. Each transaction updates a different row and both can commit under isolation levels that do not detect write skew.

The final state leaves zero doctors on duty, even though each transaction individually saw the initial condition satisfied. You must lock a row representing the shift schedule, use a synchronized allocation model, or use `SERIALIZABLE` with retry handling. Locking only the doctor row being updated is insufficient to protect the group-wide invariant.

### 7.4. Serializable requires retries

At the `SERIALIZABLE` level, the database may abort a transaction to prevent outcomes inconsistent with any serial order. The application must detect serialization errors and retry the **entire transaction** with fresh data—not just rerun the final statement, because earlier decisions may have relied on a stale snapshot.

Retries should be capped, use appropriate backoff, and apply only to operations that can safely rerun. If a transaction already triggered external side effects before aborting, retrying could send duplicate notifications or execute actions twice.

## 8. Choosing the right mechanism for each invariant type

No single technique solves every form of contention. Choose based on the scope of the condition and the data being mutated.

| Scenario | Typically suitable mechanism | Rationale |
|---|---|---|
| Non-negative inventory quantity | Conditional `UPDATE` + `CHECK` | Condition and subtraction execute atomically; constraint adds safety |
| Unique external code | `UNIQUE` constraint + `ON CONFLICT` | Database safely arbitrates concurrent inserts |
| Profile updates rarely colliding | Optimistic locking with `version` | No need to hold locks while users edit |
| Frequently contended single-row updates | `SELECT FOR UPDATE` or conditional update | Serializes transactions modifying the same row |
| Class enrollment capacity limit | Parent row lock, atomic counter, or Serializable | Invariant depends on multiple rows |
| Non-overlapping room bookings | Exclusion constraint or resource lock/transaction | Must protect time intervals, not just a single row |
| Transfer between two accounts | Single transaction updating both accounts, consistent lock order, and balance constraints | Both sides must succeed or fail together |

### 8.1. Transferring funds between two accounts

Funds transfer is a classic multi-row operation. You must guarantee the source account has sufficient funds and both updates commit together.

```sql
BEGIN;

-- Lock in account_id order to reduce deadlock risk.
SELECT account_id, balance
FROM account
WHERE account_id IN ($1, $2)
ORDER BY account_id
FOR UPDATE;

-- Application confirms both accounts exist, amount > 0,
-- and source account has sufficient balance.

UPDATE account
SET balance = balance - $3
WHERE account_id = $1
  AND balance >= $3;

-- Application must confirm exactly one row was updated.

UPDATE account
SET balance = balance + $3
WHERE account_id = $2;

-- Record ledger/debit/credit entries in the same transaction if required by model.

COMMIT;
```

If any step fails its condition, roll back completely. Check `$1 <> $2` or explicitly define self-transfer behavior. In financial systems, it is usually best to maintain an immutable transaction ledger and reconcile total balances; balance updates are part of the posting workflow.

## 9. Deadlocks and lock ordering

Deadlocks occur when transactions wait on each other's locks in a cycle.

Example:

- Transaction A locks account 10, then waits for account 20.
- Transaction B locks account 20, then waits for account 10.
- Neither can proceed without detection and aborting one transaction.

To reduce the risk:

1. Lock multiple rows in a consistent order, such as ascending primary key.
2. Keep transactions short and lock only necessary rows.
3. Avoid calling external services inside transactions.
4. Create suitable indexes so lock queries do not scan overly broad ranges.
5. Detect deadlock errors and retry the entire transaction within bounded limits.

You cannot eliminate every deadlock in a multi-writer system. Applications should treat deadlocks as recoverable concurrency errors, not a reason to retry forever.

## 10. Idempotency when requests are resent

Not every duplicate execution is a race condition, yet retries from clients, gateways, or message brokers can trigger the same business operation multiple times. For example, a client sends a payment request, the server commits, the response gets lost, the client retries, and the system charges twice.

**Idempotency** ensures a logical request is processed at most once for a defined idempotency key, even when submitted repeatedly.

Example structure:

```sql
CREATE TABLE idempotency_request (
    client_id VARCHAR(100) NOT NULL,
    idempotency_key VARCHAR(100) NOT NULL,
    request_hash VARCHAR(128) NOT NULL,
    response_status INTEGER,
    response_body JSONB,
    completed_at TIMESTAMPTZ,
    PRIMARY KEY (client_id, idempotency_key)
);
```

When receiving a request:

1. Create or claim the record for `(client_id, idempotency_key)` in a transaction.
2. If the key already exists with the same request hash, return the saved response or wait for in-flight processing per policy.
3. If the key exists with different request content, reject it because the same idempotency key is being reused for two different requests.
4. If new, execute the business logic and store the response in the same transaction when possible.

Idempotency does not replace constraints and transactions. It addresses duplicate delivery of the same logical request; constraints still protect data invariants and transactions still protect atomicity.

## 11. Testing concurrency contention

Single-threaded tests rarely catch race conditions. Launch multiple concurrent transactions with synchronized starting points and verify invariants once all finish.

### 11.1. Inventory scenario

Setup:

- A product has `available = 1`.
- Two clients simultaneously request to buy one unit.
- Both transactions start nearly simultaneously.

Expected outcome:

- Only one request successfully deducts stock and creates an order.
- The other receives an out-of-stock result or a handleable conflict.
- Final `available` equals 0, never negative.
- Two orders are never confirmed for the same unit of stock.

### 11.2. Capacity scenario

Set up a class with one remaining seat and have multiple clients enroll concurrently. After execution:

- Active enrollments do not exceed `capacity`.
- Counter (if present) matches the enrollment record count per formula.
- No client receives confirmation if its transaction rolled back.

### 11.3. Optimistic locking scenario

Two clients both read `version = 5`. Client A updates successfully to version 6. Client B submits an update with version 5 and must receive zero rows updated. B must never silently overwrite A's changes.

### 11.4. Idempotency scenario

Send multiple concurrent requests with the same idempotency key and identical payload. The result must produce only one business transaction; all duplicate requests receive the same response per contract. Sending the same key with a different payload must be rejected.

### 11.5. Organizing tests

- Use two or more independent database connections.
- Use barriers/latches to coordinate transactions reaching the check step together before proceeding.
- Do not rely solely on mock repositories; test against a real DBMS since locking and isolation depend on the engine.
- Verify returned responses, final persisted data, and error logs.
- Repeat scenarios sufficiently or use deterministic coordination to avoid false confidence from a single lucky run.
- Reconcile invariants afterward using independent queries.

## 12. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| `SELECT` check followed by unconditional `UPDATE` | Two transactions rely on the same stale read | Use conditional updates, locks, or appropriate isolation |
| Validating only in the application | Batch jobs or other services write bad data | Add database constraints for enforceable invariants |
| Assuming default transactions prevent all races | Some anomalies still occur depending on isolation and queries | Choose isolation level and synchronization matching the invariant |
| Using `CHECK` for multi-row sums | Constraint does not safely enforce cross-row conditions | Use unique/exclusion constraints, parent locks, counters, or Serializable |
| Using `SELECT FOR UPDATE` without locking the parent row | Another transaction inserts new child rows changing the sum | Lock a shared synchronization point or protect the range |
| Holding locks while calling external APIs | Increases wait times, deadlocks, and drops throughput | Move side effects outside transactions; use outbox where appropriate |
| Retrying every error | Can duplicate side effects or mask business errors | Retry only recoverable concurrency errors; cap attempts and ensure idempotency |
| Locking in inconsistent order | Increases deadlock frequency | Standardize lock ordering and handle deadlocks |
| Having a surrogate key without business `UNIQUE` | Allows logically duplicate records | Add candidate key/unique constraints |

## 13. Process for designing safe write operations

1. **State invariants clearly:** e.g., “available stock is non-negative” or “each class never exceeds capacity.”
2. **Determine data scope:** single row, multiple rows, conditional set, or multiple tables.
3. **Choose protection mechanisms:** `NOT NULL`, `CHECK`, `UNIQUE`, FK, exclusion constraint, transactions, or domain logic.
4. **Identify contention points:** which transactions may concurrently read/write the resource or alter the condition.
5. **Select synchronization:** conditional update, optimistic version, pessimistic row lock, parent lock, or Serializable.
6. **Wrap changes in transactions:** all changes belonging to one business operation commit/roll back together.
7. **Define errors and retries:** distinguish business violations, version conflicts, deadlocks, serialization failures, and system errors.
8. **Protect duplicate requests:** use idempotency keys for operations with side effects or retryable delivery.
9. **Test concurrency:** reproduce interleaved transactions, verify final state, and reconcile invariants.
10. **Monitor in production:** track conflicts, retries, deadlocks, lock waits, timeouts, and constraint violations.

## 14. Verification checklist

- [ ] Invariants are clearly written with explicit scope and applicability timing.
- [ ] Input validation is separated from shared-state checks.
- [ ] Unconditional `UPDATE`s do not rely on stale `SELECT` results.
- [ ] Simple conditions are embedded into conditional updates where appropriate.
- [ ] Database constraints protect invariants across all possible write paths.
- [ ] Cross-row rules have an explicit synchronization point.
- [ ] Transactions encompass all changes that must succeed or fail together.
- [ ] Locking strategy and lock acquisition order are defined.
- [ ] Optimistic locking verifies versions and handles conflicts explicitly.
- [ ] Isolation level matches the anomalies to prevent and DBMS semantics.
- [ ] Retries apply only to recoverable errors, are bounded, and rerun the full transaction.
- [ ] Duplicate requests are protected with idempotency where needed.
- [ ] Tests run across multiple connections and reconcile invariants afterward.

## Summary

Pre-write checks are necessary but insufficient when state can change concurrently. For single-row conditions, conditional updates typically combine checking and mutation in one atomic operation. Constraints such as `CHECK`, `UNIQUE`, and foreign keys protect data at the database layer. For more complex workflows, combine transactions with optimistic locking, pessimistic locking, or suitable isolation levels.

Multi-row invariants such as class capacity or on-call schedules require a shared synchronization point; locking only the row being edited may not suffice. Systems must also handle deadlocks, serialization failures, and resent requests via bounded retries and idempotency. Design quality is confirmed through concurrency testing on a real DBMS and post-run state reconciliation.

## Key Terms to Remember

| Term | Meaning |
|---|---|
| Invariant | A condition that must always hold true for data state |
| TOCTOU | Gap between time of check and time of acting on that check |
| Race Condition | Outcome depends on the interleaving order of concurrent operations |
| Atomic Update | Update where condition evaluation and mutation are handled atomically by the database |
| Transaction | Group of operations that commit or roll back as a single unit |
| Pessimistic Locking | Locking a resource before reading/writing to block concurrent modifications |
| Optimistic Locking | Using a version or previously read value to detect conflicts on update |
| Isolation Level | Level governing how transactions observe changes from other transactions |
| Write Skew | Transactions update distinct rows whose combined effect violates an invariant |
| Deadlock | Transactions waiting on each other's locks in a cycle |
| Idempotency | Handling repeated delivery of the same logical request without repeating business effects |
| Serialization Failure | Error when the DBMS aborts a transaction to preserve serial-execution equivalence |
