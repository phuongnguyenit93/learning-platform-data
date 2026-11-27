# Rules Within a Record, Within a Group, and Across Multiple Data Groups

A database may contain well-typed values and still reflect an invalid business state. For example, every order line item has a positive quantity yet total pre-ordered quantity exceeds inventory; every individual payment is valid yet total collected amount exceeds the amount due; every contract has a start date before its end date yet two contracts occupy the same piece of equipment during overlapping intervals.

In **data modeling**, conditions that data must always satisfy are called invariants. Constraints are mechanisms that enforce part or all of those conditions. During design, you must determine the scope of each rule: whether it concerns a single record, a group of records sharing a key, or multiple groups of data across different tables or entities.

This lesson classifies rules by scope, identifies suitable mechanisms in relational databases, and explains how to protect them when multiple transactions execute concurrently. The running example is a sales and inventory management system where orders, order lines, payments, products, and reserved stock must remain consistent.

## 1. What is an invariant and why classify it?

An invariant is a condition that must hold true in every data state considered valid. It can originate from business rules, contracts, operational policies, or technical requirements.

Examples:

- The quantity of an order line item must be greater than zero.
- Each order number belongs to only one order.
- An order must belong to an existing customer.
- The sum of line item totals must match the order total according to pricing rules.
- Reserved inventory quantity must not exceed allocatable quantity.
- Total recorded payments must not exceed the amount due, unless business policy permits overpayment.
- A piece of equipment cannot be allocated to two contracts with overlapping time intervals.

Rules have different scopes:

| Scope | Target being checked | Example | Common mechanisms |
|---|---|---|---|
| Single record | Columns within the same row | quantity > 0 | NOT NULL, CHECK |
| Group of records | Multiple rows sharing a key or scope | An order cannot have two lines with the same line_no | PRIMARY KEY, UNIQUE, partial unique index |
| Multiple data groups | Multiple related tables, groups, or entities | Total payments do not exceed amount due | Transactions, locks, isolation levels, specialized constraints |

Classifying by scope helps avoid placing a rule in the wrong layer. CHECK is well suited for checking that quantity is positive within a single row, but cannot on its own guarantee that the sum of quantities across all line items does not exceed stock. UNIQUE can prevent duplicate codes within a table, but cannot on its own sum a customer's outstanding balance across multiple orders.

Not every invariant is enforced by a single constraint. What matters is clearly specifying the condition, where it is protected, ensuring all write paths obey the same mechanism, and how to detect data drift.

## 2. Identifying invariants from business rules

### 2.1. Writing rules as verifiable conditions

A statement like “an order must be valid” is too vague to implement. Convert it into testable conditions:

- Each order has a unique order number.
- Each line item has a positive line number and belongs to an existing order.
- Line item quantity is greater than zero.
- Unit price at order placement time is non-negative.
- A confirmed order must have at least one line item.
- Finalized total equals the sum of components according to tax, fee, and discount rules.
- Only orders in an allowed state may record payments.

Rules must also specify when they apply. For instance, a draft order may not have line items yet, whereas a confirmed order must have at least one line. Requiring “every order always has line items” would make step-by-step order creation difficult.

### 2.2. Distinguishing invariants from UI rules

A required field on a screen is not necessarily a data invariant. A field may be entered in a later step or populated from an integration source. Conversely, a critical invariant such as unique order numbers must not be checked solely with JavaScript in the UI.

Ask:

- If another service writes directly to the database, is the rule still upheld?
- If two requests write at the same time, can the rule be violated?
- If a process stops halfway through, does the data remain in a valid state?
- If legacy data is imported, can invalid rows be detected and quarantined?

These questions help select the right enforcement layer. Rules that must be protected across all write paths belong in the database or a shared mechanism offering equivalent guarantees.

### 2.3. Documenting the owner of each invariant

Every invariant needs an explicit responsible component. For example, uniqueness of order numbers is protected by the orders table via UNIQUE. Inventory reservation rules may be protected by the ordering service's transaction using atomic updates and row locking. Total calculation may be enforced upon order confirmation and verified by a reconciliation job.

If the same rule is implemented differently across multiple services, interpretations can diverge. Document the canonical definition, enforcement mechanism, and permitted write flows.

## 3. Rules within a single record

Single-record rules only inspect values belonging to the same row. This is the simplest scope for applying constraints directly.

### 3.1. NOT NULL and value domains

NOT NULL requires a column to hold a value. It fits mandatory attributes such as order number, creation timestamp, or quantity.

CHECK evaluates an expression on a row. Example:

~~~sql
CREATE TABLE order_items (
    order_item_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    discount_amount NUMERIC(18, 2) NOT NULL DEFAULT 0
        CHECK (discount_amount >= 0),
    CHECK (discount_amount <= quantity * unit_price)
);
~~~

These conditions prevent zero or negative quantities, negative prices, and discounts exceeding the line's pre-discount subtotal.

CHECK typically follows SQL's three-valued logic: TRUE, FALSE, and UNKNOWN. A CHECK expression that evaluates to UNKNOWN due to NULL is generally not treated as FALSE. Therefore, if quantity must have a value, both NOT NULL and CHECK (quantity > 0) are needed. CHECK alone does not replace NOT NULL.

### 3.2. Relationships between columns in the same row

Some rules compare two columns:

~~~sql
CREATE TABLE promotions (
    promotion_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    discount_percent NUMERIC(5, 2) NOT NULL
        CHECK (discount_percent BETWEEN 0 AND 100),
    CHECK (ends_at > starts_at)
);
~~~

The condition ends_at greater than starts_at only needs data from a single row, so CHECK can be used.

Similarly, a measurement table can verify minimum_value is not greater than maximum_value. An address table might require country_code and postal_code together according to country-specific policies, though if the condition depends on a country reference table, an additional mechanism is needed.

### 3.3. DEFAULT does not replace constraints

DEFAULT supplies a value when an INSERT omits the column. It does not prevent an application from writing another value, nor does it guarantee the value is always valid.

For example, status has DEFAULT 'draft', yet still needs a CHECK or lookup table to allow only valid statuses. If business rules dictate that status may only transition along a specific flow, CHECK only validates set membership; it does not enforce transition history.

### 3.4. NULL must have clear semantics

NULL can mean unknown, not provided, or not yet occurred. Avoid overloading NULL for every special state.

Examples:

- returned_at is NULL because the item has not been returned.
- verified_at is NULL because the email has not been verified.
- cancelled_at is NULL because the order has not been cancelled.

If multiple distinct meanings exist, introduce separate statuses or attributes. When comparing NULL, use IS NULL or IS NOT NULL; `= NULL` does not behave like ordinary value equality.

## 4. Rules within a group of records

A group is a set of rows sharing a business scope, usually identified by a key such as order_id, customer_id, tenant_id, or product_id. Rules at this scope span multiple rows in the same group.

### 4.1. PRIMARY KEY and UNIQUE

PRIMARY KEY ensures row identity is unique and non-NULL. UNIQUE protects uniqueness of a column or combination of columns.

For example, each order has multiple lines, but line numbers must not duplicate within the same order:

~~~sql
CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

The composite key (order_id, line_no) enforces unique line_no within each order. Two different orders may both have line_no = 1.

If product codes are unique only per supplier, use UNIQUE (supplier_id, supplier_product_code). Including the scope in the key avoids imposing global uniqueness when business rules do not require it.

### 4.2. Partial unique indexes

Sometimes only active rows need to be unique. For instance, a customer may have multiple historical emails but only one active primary email:

~~~sql
CREATE UNIQUE INDEX uq_customer_primary_email
ON customer_emails (customer_id)
WHERE is_primary = TRUE AND active = TRUE;
~~~

This uses partial index syntax supported by some DBMSs, including PostgreSQL. Check equivalent capabilities in your chosen DBMS.

A partial unique index fits conditional uniqueness rules. It does not on its own guarantee every customer has at least one primary email; minimum-existence rules usually require handling in a transaction or another mechanism.

### 4.3. Rules on row counts within a group

A confirmed order needs at least one line item. This is a row-count rule over the order_id group.

A CHECK on orders cannot portably use a subquery to count order_lines. A common implementation checks this when transitioning the order to confirmed inside the same transaction:

~~~sql
BEGIN;

-- Lock the order row to serialize edits and confirmation.
SELECT order_id
FROM orders
WHERE order_id = :order_id
FOR UPDATE;

-- Application or procedure checks the line count.
SELECT COUNT(*)
FROM order_lines
WHERE order_id = :order_id;

-- Transition status only if line count is greater than 0.
UPDATE orders
SET status = 'confirmed',
    confirmed_at = now()
WHERE order_id = :order_id
  AND status = 'draft';

COMMIT;
~~~

This is an illustrative flow; production implementations must ensure all line-item add/delete operations also lock or check the same orders row using a consistent protocol. Otherwise, another transaction could delete the last line after the count check but before order confirmation.

### 4.4. Rules on group totals or limits

A group may require total quantity not to exceed a limit. For example, an allocation batch has a capacity of 100 units, so the sum of line quantities must not exceed 100.

Per-row CHECK constraints alone cannot enforce this because each individual row can be valid while the group total exceeds the cap. You can protect it with a summary row representing the group:

- Store allocated_quantity on the allocation_batch row.
- Update the total and insert detail rows within the same transaction.
- Place CHECK (allocated_quantity BETWEEN 0 AND capacity) on the summary row.
- Lock the allocation_batch row to serialize updates to the same group.

The aggregated value is derived data updated concurrently with details. A reconciliation check is needed to detect if the parent total ever diverges from the sum of child rows.

### 4.5. Non-overlapping time interval rules

A group may require time intervals not to intersect. For example, a meeting room cannot be booked twice during the same period. In PostgreSQL, an exclusion constraint combined with range types can protect this rule:

~~~sql
-- PostgreSQL illustration; requires the btree_gist extension to compare room_id.
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_bookings (
    booking_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id BIGINT NOT NULL,
    booking_period TSTZRANGE NOT NULL,
    status VARCHAR(20) NOT NULL,
    CHECK (NOT isempty(booking_period)),
    EXCLUDE USING GIST (
        room_id WITH =,
        booking_period WITH &&
    )
    WHERE (status IN ('confirmed', 'in_progress'))
);
~~~

The `&&` operator tests whether two intervals overlap. The exclusion constraint prevents rows with the same room_id and overlapping booking_period values among active occupancy statuses. Syntax and support depend on the DBMS; do not assume this is standard SQL available in every database.

Without a specialized constraint, use a transaction and lock a row representing the resource (room or equipment) before checking the schedule. Every scheduling write path must follow the same protocol.

## 5. Rules across multiple groups or tables

A cross-table invariant typically combines data from multiple entities or groups. Examples:

- Sum of order lines must equal the order total.
- Total payments must not exceed amount due.
- Total reserved stock must not exceed allocatable stock.
- Customer's total active credit exposure must not exceed the credit limit.
- Equipment must not be simultaneously allocated to a contract and scheduled in a maintenance window.

These rules are harder because multiple concurrent transactions may touch different rows simultaneously.

### 5.1. Foreign keys protecting referential relationships

Foreign keys ensure referenced values exist in the referenced table. For example, every order_line must point to an existing order and an existing product.

~~~sql
CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    order_number VARCHAR(40) NOT NULL UNIQUE
);

CREATE TABLE order_lines (
    order_line_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

Foreign keys guarantee the existence of referenced rows, but do not automatically ensure an order has at least one line, has a valid total, or that the product is in stock.

The ON DELETE policy is also part of the model. CASCADE may fit strictly dependent data like certain draft tables, but can destroy history if applied to paid orders. RESTRICT or soft delete is usually more appropriate for transactional data requiring auditing.

### 5.2. Order total and order lines

Suppose orders stores grand_total, while order_lines stores quantity, unit_price, and discount. The invariant is:

**grand_total = sum of line totals + taxes + fees - order-level discounts**

There are two main approaches:

1. Do not store grand_total; compute it from the lines on each read.
2. Store grand_total for fast queries or to snapshot finalized values, updating it in the same transaction with a reconciliation mechanism.

If storing the total, do not let different services compute it with separate formulas. Define rounding rules, finalization point, tax handling, and discount rules explicitly. Once an order is confirmed, lock line modifications or create new adjustment records rather than silently altering historical totals.

A check pattern when finalizing an order:

~~~sql
BEGIN;

SELECT order_id
FROM orders
WHERE order_id = :order_id
FOR UPDATE;

-- Compute total from lines and surcharges/taxes.
SELECT SUM(quantity * unit_price - discount_amount)
FROM order_lines
WHERE order_id = :order_id;

-- Procedure or application applies the same rounding rules,
-- writes grand_total, and transitions status within the transaction.

COMMIT;
~~~

The SUM query above only computes line totals after line-level discounts; taxes, fees, and order-level discounts must be added or subtracted per business rules. The SQL snippet illustrates the serialization point. In production, handle orders with zero lines and ensure line-editing operations also lock the parent row.

### 5.3. Total payments not exceeding amount due

Suppose an order has an amount due of 1,000,000 VND and receives multiple payments. The invariant may be that the sum of captured payments does not exceed amount_due. If overpayments or deposits are allowed, the rule must be formulated differently.

The example below assumes the orders table has amount_due and amount_paid columns; amount_paid is a summary updated in the same transaction as each payment.

One implementation locks the orders row before recording a payment:

~~~sql
BEGIN;

SELECT amount_due, amount_paid
FROM orders
WHERE order_id = :order_id
FOR UPDATE;

-- Check amount_paid + :new_payment <= amount_due.
-- If valid, insert payment and update amount_paid.

COMMIT;
~~~

Locking the orders row serializes payment writes for the same order, provided all write paths follow this protocol. An aggregated amount_paid column enables fast validation, but must be updated in the same transaction as the payment and reconciled against the sum of valid payments.

### 5.4. Inventory on hand and reserved quantities

Inventory is a classic example of an invariant spanning multiple groups. Suppose:

- on_hand is the quantity physically available.
- reserved is the quantity currently reserved.
- available = on_hand - reserved.

Conditions:

- on_hand >= 0.
- reserved >= 0.
- reserved <= on_hand.

If on_hand and reserved are stored on the same inventory_balance row, CHECK constraints can protect these relationships within that record:

~~~sql
CREATE TABLE inventory_balances (
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    warehouse_id BIGINT NOT NULL REFERENCES warehouses(warehouse_id),
    on_hand INTEGER NOT NULL CHECK (on_hand >= 0),
    reserved INTEGER NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    PRIMARY KEY (product_id, warehouse_id),
    CHECK (reserved <= on_hand)
);
~~~

However, individual reservation details live across many other rows. The invariant to protect is that the sum of active reservations for a product at a warehouse must equal reserved on the summary row. Every reservation creation, cancellation, or completion must update both the detail row and the summary row in the same transaction.

A safe reservation operation can use a conditional update:

~~~sql
BEGIN;

UPDATE inventory_balances
SET reserved = reserved + :requested_quantity
WHERE product_id = :product_id
  AND warehouse_id = :warehouse_id
  AND on_hand - reserved >= :requested_quantity;

-- Insert reservation detail only when exactly one row was updated.
-- If stock is insufficient or balance record is missing, roll back.

COMMIT;
~~~

The check condition and increment of reserved happen in a single atomic update statement. Two concurrent requests cannot both consume available stock observed at an earlier point in time, as long as all reservation flows use the same mechanism.

### 5.5. Customer credit limit

A customer has a credit limit of 50 million VND. Total unpaid exposure across multiple orders must not exceed that limit.

This is an invariant spanning multiple orders and payments. If two requests create orders concurrently, each might read an exposure within the limit and both insert new orders, pushing the total past the cap.

Ways to protect it:

- Lock the customer_credit_limit row before computing and updating exposure.
- Maintain a summary current_exposure row and update it atomically in the same transaction as the order.
- Use SERIALIZABLE isolation and handle retries on serialization failures.
- Use a ledger as the source of truth and reconcile it against the summary balance.

A summary column only works if every write path updates it properly. If an import job bypasses that column, the limit can be exceeded even though all online transactions comply.

## 6. Why checking before writing is not enough

A common mistake is reading data, checking conditions in the application, and then writing. The gap between checking and writing creates a race condition.

For example, inventory has one unit left. Two transactions run concurrently:

~~~mermaid
sequenceDiagram
    participant A as Transaction A
    participant B as Transaction B
    participant DB as Database
    A->>DB: Read available = 1
    B->>DB: Read available = 1
    A->>DB: Write reserve 1
    B->>DB: Write reserve 1
    Note over A,B: Without locks or atomic updates
    DB-->>A: Success
    DB-->>B: Success
    Note over DB: Total reserved can reach 2 when only 1 exists
~~~

The application checked the condition, yet the result was no longer true at write time. This is a TOCTOU (time of check to time of use) bug.

The fix is not simply re-checking in the UI. Synchronization is needed at the point of update:

- Atomic conditional updates.
- SELECT ... FOR UPDATE or equivalent locks.
- Specialized unique/exclusion constraints.
- Appropriate isolation levels.
- Optimistic concurrency with a version column and update predicate.

### 6.1. Pessimistic locking

Pessimistic locking locks rows before reading and modifying them. Other transactions wanting to modify the same row must wait or fail based on timeout policy.

Suitable when contention is frequent and operations must be serialized. However, holding locks too long reduces throughput, can cause deadlocks, and requires consistent lock acquisition ordering.

### 6.2. Optimistic concurrency

Optimistic concurrency uses a version or prior value to update only if the data has not changed:

Suppose inventory_balances adds a `version BIGINT NOT NULL DEFAULT 0` column.

~~~sql
UPDATE inventory_balances
SET reserved = :new_reserved,
    version = version + 1
WHERE product_id = :product_id
  AND warehouse_id = :warehouse_id
  AND version = :expected_version;
~~~

If zero rows are updated, the data has changed or the record no longer matches; the application must re-read and reprocess the operation. This works well when contention is low and retries are acceptable.

### 6.3. Isolation levels and serialization failures

Isolation levels govern how concurrent transactions see and affect data. READ COMMITTED, REPEATABLE READ, and SERIALIZABLE behave differently across DBMSs.

SERIALIZABLE aims for outcomes equivalent to a serial execution order, but the DBMS may abort a transaction upon detecting conflicts requiring a retry. The application must handle serialization errors and safely rerun the entire transaction.

Do not pick an isolation level based solely on its name. Read your DBMS documentation, understand which anomalies can occur, and test under realistic workloads.

### 6.4. Lock ordering and deadlocks

If one transaction locks product A then B while another locks B then A, the two transactions can wait on each other and cause a deadlock. Standardize lock acquisition order—for example, sort by product_id before locking multiple rows.

A deadlock does not necessarily mean data is corrupt; the database usually aborts one transaction to break the wait cycle. The application should handle retryable errors, cap retry attempts, and ensure operations are idempotent.

## 7. Choosing mechanisms by invariant scope

No single mechanism fits every rule. Use the following decision table:

| Rule type | Example | Preferred mechanism | Things to verify |
|---|---|---|---|
| Single column | quantity > 0 | NOT NULL, CHECK | NULLs and data types |
| Multiple columns in same row | ends_at > starts_at | CHECK | NULL rules and timezones |
| Uniqueness within group | line_no unique per order | PRIMARY KEY, UNIQUE | Composite key scope |
| Conditional uniqueness | One active primary email | Partial unique index or equivalent | DBMS support |
| Referential | order_line must have order | FOREIGN KEY | ON DELETE/UPDATE policies |
| Group total | Total allocation <= capacity | Summary row + transaction/lock | All write paths update same mechanism |
| Non-overlapping intervals | Room or equipment schedule | Exclusion constraint or resource lock | Interval semantics and concurrency |
| Cross-table | Payment <= amount_due | Transaction, lock, or SERIALIZABLE | Race conditions and retries |
| State workflow | Only confirmed orders may ship | State transition + transaction | Transition history and permissions |

### 7.1. Prefer declarative constraints whenever possible

Declarative constraints in the schema offer a major advantage: every write path going through the database must obey them. They also make part of the data contract visible to anyone reading the schema.

Use PRIMARY KEY, UNIQUE, FOREIGN KEY, NOT NULL, and CHECK for rules they express accurately. For specialized constraints such as exclusion constraints, evaluate portability and DBMS support.

### 7.2. Use transactions for multi-step business changes

A business operation such as reserving inventory typically requires:

1. Check and increment reserved.
2. Create the reservation record.
3. Record reservation expiration.
4. Write history or an outbox event if needed.

All steps must commit together or roll back together. Incrementing reserved without creating the reservation causes the summary count to drift. Creating the reservation without incrementing reserved can let two customers both be confirmed.

### 7.3. Triggers are not the default solution

Triggers can enforce database-level rules when reacting to INSERT/UPDATE/DELETE. However, triggers make write behavior less visible in application code and can complicate debugging, migrations, and performance tuning.

Use triggers only when centralized enforcement provides clear value and the team can test, monitor, and document them thoroughly. Triggers must also be designed for transactions and concurrency; placing logic in a trigger does not automatically make a rule race-safe.

### 7.4. Materialized aggregates require reconciliation

Some systems store balances, totals, or reserved counts for fast reads. These are derived aggregates that can be reconstructed from detail records.

If storing aggregates:

- Identify which detail data is the source of truth.
- Update details and aggregates in the same transaction or via a reliable synchronization mechanism.
- Run periodic reconciliation jobs.
- Provide controlled remediation procedures for discrepancies.
- Never allow multiple services to update the aggregate independently using separate formulas.

A fast aggregate with no verification becomes a hard-to-trace source of drift.

## 8. Invariants and state machines

A status value may belong to the valid set while the state transition flow is still invalid. For example, order statuses include draft, confirmed, paid, fulfilled, cancelled. A CHECK constraint prevents `status = 'unknown'`, but does not stop transitioning from cancelled to fulfilled.

Model valid transitions explicitly:

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Confirmed
    Draft --> Cancelled
    Confirmed --> Paid
    Confirmed --> Cancelled
    Paid --> Fulfilled
    Paid --> Refunded
    Fulfilled --> [*]
    Cancelled --> [*]
    Refunded --> [*]
~~~

When transitioning states:

- Check the current state.
- Check required business preconditions.
- Update status and related data within a transaction.
- Record state-transition history if required.
- Block invalid transitions.

For example, when transitioning an order from confirmed to paid, verify the payment amount is valid and the order has not been cancelled. If recording payment and changing status are two separate operations, a mid-flight failure can leave an inconsistent state.

## 9. Idempotency and handling duplicate submissions

A payment or order request may be resent due to timeouts, flaky networks, or users clicking a button repeatedly. If every submission creates a new record, a single logical operation may be processed twice.

An idempotency key identifies submissions belonging to the same logical operation:

~~~sql
CREATE TABLE payment_requests (
    payment_request_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL UNIQUE,
    request_hash VARCHAR(128) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

When receiving a request:

1. Find or create a record by idempotency_key.
2. If the key already exists with the same request_hash, return the recorded outcome or in-progress status.
3. If the key already exists with different request content, reject it because the same key must not represent two distinct operations.
4. Record the outcome and update status within an appropriate transaction.

A unique constraint guarantees only one logical request is created per key. Still, idempotency handling requires designing statuses, stored responses, key retention periods, and interactions with external payment gateways.

## 10. Detecting and remediating violating data

Constraints block new invalid data, but legacy data may already violate rules before constraints are added. Before deploying a constraint:

1. Query to locate violating rows.
2. Classify root causes: missing data, duplicates, logic bugs, or definition mismatches.
3. Determine a business-justified remediation plan.
4. Preserve original data and remediation decisions if auditing is required.
5. Clean or quarantine violating data.
6. Add the constraint and verify.

For example, before adding UNIQUE on normalized emails, query for duplicates. Do not automatically delete an account because two customers might be sharing an email.

For aggregate invariants, run a reconciliation query:

~~~sql
SELECT
    b.product_id,
    b.warehouse_id,
    b.reserved AS stored_reserved,
    COALESCE(SUM(r.quantity), 0) AS calculated_reserved
FROM inventory_balances b
LEFT JOIN reservations r
    ON r.product_id = b.product_id
   AND r.warehouse_id = b.warehouse_id
   AND r.status = 'active'
GROUP BY
    b.product_id,
    b.warehouse_id,
    b.reserved
HAVING b.reserved <> COALESCE(SUM(r.quantity), 0);
~~~

This query finds summary rows that disagree with active reservation details. Real schemas may also need grouping by batch, owner, or reservation expiry; conditions must match business definitions.

### 10.1. How to fix violating data

Not every error should be fixed automatically. Options include:

- Auto-fix when there is a clear source of truth and an unambiguous transformation.
- Route to a manual review queue when a business decision is required.
- Quarantine bad imported records so they do not affect active data.
- Create compensating adjustments instead of directly mutating finalized transactions.

After fixing, rerun the reconciliation query and record the count of resolved rows, remaining backlog, and reasons.

## 11. Testing invariants

### 11.1. Valid and invalid data tests

For each constraint, include at least one valid case and one rejected case:

| Rule | Valid data | Invalid data |
|---|---|---|
| quantity > 0 | quantity = 2 | quantity = 0 |
| ends_at > starts_at | ends after starts | ends before starts |
| Unique order number | two distinct codes | inserting an existing code |
| Foreign key | existing customer_id | non-existent customer_id |
| One primary email | one active primary row | two primary rows for same customer |
| Inventory | reserved <= on_hand | reserved > on_hand |

### 11.2. Concurrency tests

Aggregate and resource invariants must be tested with genuinely concurrent transactions. Sequential tests can pass every time even when race conditions exist.

Examples:

- Inventory has 1 unit left; send two reservation requests simultaneously.
- Credit limit has room for one order; create two orders concurrently.
- Two users confirm the same room booking at the same time.
- Two payment webhooks deliver the same event concurrently.

Verify the final state: only the allowed number of operations succeeded, totals do not exceed limits, no orphan records exist, and failed transactions left no partial changes.

### 11.3. Rollback and retry tests

Simulate a failure after updating the summary row but before inserting detail rows. The transaction must roll back both changes. Simulate deadlocks or serialization failures to confirm the application retries properly.

If a transaction calls an external system, do not hold database locks while waiting on slow network calls. Use outbox patterns, intermediate states, and asynchronous processing, while defining invariants for each state and recovery behavior on redelivery.

## 12. Evolving constraints and schemas

Invariants can change as the business evolves. For example, orders previously disallowed partial payments, and later allow multiple payments; or inventory begins supporting backorders so `on_hand - reserved` can go negative under a new model.

When changing rules:

- Confirm the new definition and effective date.
- Find legacy data violating the new rule.
- Decide whether to backfill, migrate, or preserve historical states.
- Add constraints in phases if tables are large.
- Deploy application code compatible with the schema during the transition window.
- Monitor constraint errors and reconciliation metrics after release.

For a new constraint on a large table, you may need to inspect data first, add the constraint in a less-blocking mode if supported by the DBMS, validate it, and then switch to fully enforced state. Syntax and locking impact depend on the database product.

Never drop a constraint simply because one write path is failing. First determine whether the failure is due to bad data, an un-updated application path, or a constraint that misstates the business rule.

## 13. Workflow for designing and protecting invariants

When designing an entity or data workflow:

1. **List invariants:** write conditions that must always hold and when they apply.
2. **Determine scope:** single row, group, multi-table, or system-wide.
3. **Choose source of truth:** identify which table or ledger is authoritative.
4. **Select mechanisms:** CHECK, UNIQUE, FOREIGN KEY, exclusion constraint, transactions, locks, or isolation levels.
5. **Identify all write paths:** APIs, jobs, imports, webhooks, admin tools, and migrations.
6. **Analyze concurrency:** identify race conditions, deadlocks, and lock ordering.
7. **Design recovery:** rollback, retry, idempotency, outbox, or compensating workflows.
8. **Test:** valid cases, invalid cases, concurrency, and mid-flight failures.
9. **Reconcile:** build discrepancy-detection queries for aggregates and cross-table rules.
10. **Monitor post-deployment:** track constraint errors, retries, deadlocks, and invariant metrics.

Each key invariant should have brief documentation covering its definition, scope, enforcement point, owner, and verification method. This is especially important when a rule is protected by multiple coordinated mechanisms.

## 14. Design review checklist

- [ ] Invariants are written as concrete conditions with explicit applicability timing.
- [ ] Each rule is classified by scope: single row, single group, or multiple groups.
- [ ] NOT NULL and CHECK protect single-row conditions.
- [ ] PRIMARY KEY and UNIQUE accurately reflect identity scope.
- [ ] Foreign keys protect referential relationships.
- [ ] Aggregate rules have update and reconciliation mechanisms.
- [ ] Cross-table rules are protected by transactions and appropriate concurrency control.
- [ ] Online writes, imports, jobs, and webhooks enforce the same rules.
- [ ] Rollback, deadlock, serialization failure, and retry handling are in place.
- [ ] Duplicate requests have idempotency protection where needed.
- [ ] State transitions are validated rather than checking only status membership.
- [ ] Legacy data is checked before adding new constraints.
- [ ] Queries or metrics exist to detect invariant violations.
- [ ] Each critical invariant has an assigned owner and documentation.

## Conclusion

Invariants should be classified by scope before choosing enforcement mechanisms. Single-row rules usually fit NOT NULL and CHECK. Group rules typically require primary keys, unique constraints, partial indexes, or aggregate checks. Rules spanning multiple groups and tables usually require transactions, locks, isolation levels, or specialized constraints, paired with reconciliation workflows.

Application-level pre-write checks are insufficient to protect data when transactions run concurrently. Place declarative constraints wherever possible, use transactions for multi-step changes, handle retries and idempotency, and test under contention. When invariants are clearly defined, consistently enforced, and regularly verified, the data model maintains reliable state even with multiple write paths and evolving processes.
