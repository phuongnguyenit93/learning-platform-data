# Transaction Boundaries Required to Protect Each Invariant

## Lesson Objectives

After this lesson, you will be able to identify which data changes must commit or roll back together to preserve an invariant; choose transaction boundaries appropriate to the data scope and business workflow; distinguish transaction boundaries from aggregate or service boundaries; and select locks, isolation levels, or constraints to protect concurrent updates.

You will also learn how to avoid overly short transactions that expose invariants, overly long transactions that cause resource contention, and how to handle workflows spanning multiple services or external systems.

## 1. What is a transaction boundary?

A **transaction boundary** defines where a unit of data work begins and ends so that changes inside it are processed as a consistent unit. With a database transaction, changes either commit together or roll back together.

For example, when transferring funds between two accounts, the system must debit the sender account and credit the recipient account. If it only debits and then hits an error before crediting, the data becomes wrong. Both updates must sit inside the same transaction:

~~~text
BEGIN
  Debit sender account
  Credit recipient account
COMMIT
~~~

If any required step fails, the transaction must roll back so neither change is partially persisted.

Transaction boundaries are chosen based on the **invariant to protect**. Ask: which data must change together so that after the operation, the business condition still holds true? All of those required changes must be protected by a single consistency mechanism—typically a transaction combined with appropriate constraints or locks.

### 1.1. Transactions protect a state transformation

A transaction has a before state and an after state:

~~~text
Valid state D
       |
       | Transaction T
       v
Valid state D'
~~~

If the transaction succeeds, the system transitions from D to D'. If it fails, the system keeps D. For an invariant P, the requirement is:

~~~text
P(D) = true
T succeeds => P(D') = true
T fails    => state is rolled back, P(D) remains true
~~~

This assumes the initial state was already valid and every relevant write path follows the protection mechanism. A transaction does not automatically fix pre-existing invalid data, nor does it know business rules unless we encode them.

### 1.2. Transaction boundaries are more than BEGIN and COMMIT placement

Wrapping a block of code in BEGIN and COMMIT does not automatically protect an invariant. You must determine:

- Which rows or tables are involved?
- Can other requests update the same data?
- Are there operations outside the transaction that could still break the rule?
- Is the isolation level sufficient to protect multi-row conditions?
- Do database constraints block invalid states?
- Does a mid-flight error roll back all changes?
- Have any side effects outside the database already occurred before commit?

For example, an order confirmation transaction might lock the Order record while an OrderItem deletion operation does not acquire the same lock. Then two transactions can still interleave badly and leave a confirmed order with zero line items. The right boundary must be paired with a synchronization protocol obeyed by every write path.

## 2. Start from the invariant, not from statement counts

A transaction should be designed around conditions that must always hold true. Do not group SQL statements into a transaction merely because they sit inside one function or endpoint.

### 2.1. Write invariants as testable statements

Example:

> Every account balance must be non-negative, and the total monetary amount in an internal transfer must be conserved.

This invariant involves two accounts and two balance updates. The transaction must include both updates as well as the transfer record if ledger entries are a required part of the books.

Another example:

> A room must not have two confirmed bookings with overlapping time intervals.

This invariant involves all bookings for the same room with intersecting intervals. A transaction updating only a single booking is insufficient; a mechanism is needed to prevent two concurrent requests from both passing the check.

### 2.2. Map affected data

For each invariant, list:

1. Data read to make the decision.
2. Data created, updated, or deleted.
3. Other rows that may be affected by concurrent operations.
4. Constraints protecting the data.
5. Events or side effects to emit after commit.

Order confirmation example:

| Component | Role |
|---|---|
| Order | Status transitions from DRAFT to CONFIRMED |
| OrderItem | Must have at least one valid line item |
| Inventory | Stock must be sufficient and reserved/deducted per policy |
| Payment | Payment conditions must be satisfied if required by workflow |
| Outbox event | Record OrderConfirmed event to publish after commit |

This table shows that some changes belong in the same database transaction, whereas others may live in another service and require a distributed workflow.

### 2.3. Identify check points and commit points

A workflow typically has stages:

- read required data;
- lock or check version;
- verify preconditions;
- apply changes;
- verify postconditions or rely on constraints;
- record events to emit;
- commit.

The commit point must sit after all changes needed to preserve the invariant. If you commit too early, data can be exposed in an intermediate state forbidden by the business. If you commit too late, the transaction holds locks too long and increases contention.

## 3. Principles for choosing transaction boundaries

### 3.1. Include all changes requiring atomicity

If two or more changes must succeed or fail together to uphold an invariant, place them in the same transaction when they reside within the same transactional database boundary.

Examples:

- debit and credit in a funds transfer;
- deducting inventory and creating a reservation record;
- updating order status and recording state-transition history;
- creating an invoice and its invoice lines;
- writing business data and its corresponding outbox event.

Omitting a mandatory change can cause the system to commit an invalid state.

### 3.2. Do not bundle work that does not need atomicity

An overly broad transaction can:

- hold locks too long;
- increase deadlock probability;
- reduce throughput;
- increase rollback volume when an unrelated step fails;
- create coupling between tasks that could run independently.

For example, creating an order and sending a confirmation email usually do not need to share a database transaction. The email can be sent after the order commits. If sending the email fails, the order still exists and the system can retry sending the email.

What matters is distinguishing side effects required to uphold an invariant from side effects that can execute afterward.

### 3.3. Keep transactions short and bounded

Transactions should finish quickly and avoid holding resources while waiting on users or external services.

Avoid:

- opening a transaction when a user opens a form and keeping it open for minutes;
- calling payment APIs or sending emails while holding database row locks;
- waiting for OTP input or manual approval inside a transaction;
- running large reports inside a hot write transaction unless a long snapshot is truly needed.

Collect inputs first, run the short transactional step when the user confirms, and handle external side effects using an appropriate mechanism.

### 3.4. A transaction needs a cohesive purpose

Transaction names should reflect business intent, such as:

- ReserveInventory;
- ConfirmOrder;
- TransferFunds;
- PostJournalEntry;
- AssignEmployeeToDepartment.

A clear goal helps readers see which invariants are protected and evaluate whether an operation belongs in the transaction.

## 4. Transaction scope and aggregate boundaries

In Domain-Driven Design, an **aggregate** is a cluster of entities and value objects managed as a consistency unit. The aggregate root is the primary entry point for modifying state within the cluster.

Aggregates help identify where to centralize invariant protection. However, aggregate boundaries and database transaction boundaries are not always strictly identical.

### 4.1. Invariants within an aggregate

For example, Order and OrderItem are managed within the same aggregate:

- line items must belong to the right order;
- quantities must be positive;
- totals must be calculated per rules;
- confirmed orders may not modify line items per policy.

A ConfirmOrder command can update Order status after checking the line items in the same transaction.

### 4.2. Invariants across multiple aggregates

Suppose an order must reserve stock across multiple products. Order and Inventory may be separate aggregates because inventory is managed independently per product.

If both live in the same database and the business requires reserving stock simultaneously with creating the order, a single database transaction covering the needed records can be used. If they live in different services/databases, a local transaction cannot guarantee global atomicity; a distributed workflow such as a saga is required.

### 4.3. Do not create oversized aggregates just to bundle transactions

If you lump products, orders, customers, payments, and shipments into one giant aggregate, every operation may contend on the same lock and fail to scale.

Identify which invariants truly require immediate protection. Other rules can be handled via events, asynchronous workflows, or convergence checks when the business permits.

## 5. Database mechanisms protecting boundaries

Transactions provide atomicity, but must be combined with constraints, locks, and isolation to ensure correctness under contention.

### 5.1. Constraints remain necessary

For example, transferring money in a transaction does not replace a non-negative balance CHECK:

~~~sql
CREATE TABLE accounts (
    account_id BIGINT PRIMARY KEY,
    balance NUMERIC(18, 2) NOT NULL CHECK (balance >= 0)
);
~~~

CHECK protects each row on write. The transaction ensures both account updates commit or roll back together. Each layer plays a distinct role.

### 5.2. UNIQUE protects concurrent uniqueness

Suppose each customer can have only one active record per document type. If the application queries first and inserts afterward, two concurrent requests can both see no existing record.

An appropriate unique constraint acts as the final safeguard:

~~~sql
CREATE UNIQUE INDEX uq_active_identity
ON identity_documents(customer_id, document_type)
WHERE status = 'ACTIVE';
~~~

Partial index syntax depends on the DBMS. In PostgreSQL, this example prevents two ACTIVE records with the same customer_id and document_type. The application should handle unique-violation errors as an expected business outcome.

### 5.3. FOREIGN KEY protects references

If a child record must reference an existing parent, a FK ensures no orphaned references exist at commit time according to database rules.

~~~sql
CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id)
);
~~~

A FK does not automatically guarantee every Order has at least one OrderItem. That is a parent-side invariant requiring a separate mechanism.

### 5.4. Deferred constraints

Some DBMSs allow constraints to be checked at the end of a transaction rather than immediately after each statement. This is useful when intermediate states inside a transaction temporarily violate the rule while the final state is valid.

For instance, updating circular references or inserting interdependent rows may need checks deferred until commit. `DEFERRABLE` support and syntax vary across DBMSs; do not assume every CHECK or constraint can be deferred.

## 6. Isolation levels and cross-row invariants

Transaction boundaries answer which changes travel together. Isolation levels answer how concurrent transactions observe and affect each other.

### 6.1. Read Committed

Under Read Committed, each statement typically sees data committed before the statement began. Two SELECTs inside the same transaction can see different snapshots if another transaction commits in between.

This level suffices for many operations when paired with constraints and atomic updates. However, reading a set of rows and making write decisions based on that read can suffer race conditions.

### 6.2. Repeatable Read and Snapshot Isolation

In some DBMSs, snapshot-based Repeatable Read gives a transaction a more consistent read snapshot. Yet a snapshot does not automatically protect all cross-row invariants. Two transactions can both read a true condition and write different rows such that the combined state violates the rule (write skew), depending on isolation semantics.

Do not pick Repeatable Read simply because the name sounds like all reads are repeatable. Understand the specific behavior of your database.

### 6.3. Serializable

Serializable aims for results equivalent to some serial execution order. The database may abort a transaction when detecting conflicts requiring a retry.

This level helps with complex invariants depending on row sets or absence conditions. However, it does not eliminate the need for proper design:

- applications must safely retry serialization errors;
- transactions should be short;
- external side effects must not execute before commit is known;
- realistic load and contention testing is required.

### 6.4. Row locking and range locking

SELECT ... FOR UPDATE locks selected rows per the database's locking semantics. It is useful when competing transactions update the same resource that already has a representative row.

However, if the invariant depends on **no row existing** that matches a condition, locking existing rows may not suffice. Another transaction can still insert a new row (phantom) unless isolation or range locking prevents it.

Options include:

- unique/exclusion constraints;
- locking a parent row as a business mutex;
- advisory locks if supported by the DBMS;
- serializable transactions;
- redesigning data to introduce an explicit resource/guard row.

Choose the mechanism based on the condition to protect, not merely familiar SQL syntax.

## 7. Example: transferring funds between two accounts

Invariants:

1. Account balances are non-negative.
2. Transfer amount is deducted from the sender account and added to the recipient account.
3. The transfer record is recorded only if both updates succeed.

### 7.1. Transaction boundary

~~~sql
BEGIN;

UPDATE accounts
SET balance = balance - :amount
WHERE account_id = :from_account
  AND balance >= :amount;

-- Application must confirm exactly one row was updated.
-- Otherwise, roll back and return an insufficient-balance error.

UPDATE accounts
SET balance = balance + :amount
WHERE account_id = :to_account;

-- Application must confirm the recipient account exists.
-- Otherwise, roll back.

INSERT INTO transfers (
    transfer_id,
    from_account_id,
    to_account_id,
    amount,
    status
)
VALUES (
    :transfer_id,
    :from_account,
    :to_account,
    :amount,
    'COMPLETED'
);

COMMIT;
~~~

This is a transaction sketch; the application must check affected row counts and roll back if any mandatory step fails. Validate positive amount, distinct accounts if required by policy, compatible currencies, and transfer authorization before committing.

### 7.2. Avoiding deadlocks when locking multiple accounts

Two opposing transfers can lock accounts in opposite orders:

- Transaction A locks account 10 then waits for 20.
- Transaction B locks account 20 then waits for 10.

This is a deadlock. Reduce the risk by locking accounts in consistent account_id order across all transfer paths.

The database can still detect deadlocks and abort one transaction. Applications need bounded retries and idempotency to avoid creating duplicate transfers.

### 7.3. Idempotency

Clients may resend requests due to timeouts even though the previous transaction committed. Use a unique idempotency key within the appropriate scope:

~~~sql
CREATE TABLE transfers (
    transfer_id UUID PRIMARY KEY,
    idempotency_key VARCHAR(100) NOT NULL UNIQUE,
    from_account_id BIGINT NOT NULL,
    to_account_id BIGINT NOT NULL,
    amount NUMERIC(18, 2) NOT NULL CHECK (amount > 0),
    status VARCHAR(20) NOT NULL
);
~~~

If a request is resent with the same key, the system returns the existing transaction outcome instead of debiting again. Scope the key per tenant or client if keys are only unique within that scope.

## 8. Example: order confirmation and inventory reservation

Suppose an order has multiple lines and needs sufficient stock reserved for all products. If Order and Inventory live in the same database, the transaction may include:

1. lock or conditionally update inventory rows;
2. verify sufficient quantity for all products;
3. write reservation records;
4. transition Order to CONFIRMED or RESERVED per model;
5. write outbox event;
6. commit.

If any product lacks stock, the entire transaction rolls back so partial stock is not unintentionally held.

### 8.1. Conditional update

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - :quantity
WHERE product_id = :product_id
  AND available_quantity >= :quantity;
~~~

If zero rows are updated, stock is insufficient or the product does not exist. For multi-product orders, check every line and roll back if any line fails to reserve.

### 8.2. Consistent lock ordering

When locking multiple products, acquire locks in consistent product_id order to reduce deadlocks. If multiple order lines reference the same product, aggregate quantities before deducting to avoid messy repeated updates.

### 8.3. When not to reserve stock inside order creation

If policy permits creating orders first and reserving stock later, there is no need to bundle everything into one large transaction. You can create the order in PENDING_RESERVATION and have a worker perform the reservation. The model must explicitly define intermediate states and out-of-stock handling.

The choice depends on customer experience, inventory contention, and overselling rules. A PENDING state is not a flaw when intentionally modeled as a business state.

## 9. Multi-row invariants: using guard rows or appropriate locks

Some invariants depend on sums or row counts. For example, each class has at most 30 students.

If two transactions both count 29 students and insert, both can pass the check and produce 31. Counting then inserting without concurrency protection is unsafe.

### 9.1. Guard row

Capacity and enrolled_count can be stored on a single Course row:

~~~sql
UPDATE courses
SET enrolled_count = enrolled_count + 1
WHERE course_id = :course_id
  AND enrolled_count < capacity;
~~~

Only the transaction that updates one row proceeds to create the enrollment. The enrollment record and counter update must be in the same transaction so they do not drift.

This makes the single Course row a synchronization point. Under high throughput, that row can become hot; measure load and consider alternative strategies.

### 9.2. Counters must stay synchronized with detail data

If enrolled_count is derived from the enrollments table, define how it is maintained:

- update the counter in the same transaction when adding/removing enrollments;
- recompute and reconcile periodically;
- or compute directly from the table if workload allows.

A cached counter must not be treated as an independent source of truth if it can drift from detail data.

### 9.3. Better-fitting constraints or locks

If the invariant is “each student may enroll only once in the same term,” `UNIQUE(student_id, course_id, term_id)` is a more direct solution. If the invariant is total students not exceeding capacity, unique cannot solve it; a guard row, locking, serializable isolation, or a different design is needed.

Choose the mechanism closest to the rule's structure.

## 10. Transaction boundaries in multi-service systems

When data resides in multiple databases owned by separate services, local ACID transactions cannot span the entire workflow. Never hold a transaction open while calling services sequentially over the network.

### 10.1. Local transactions and distributed workflows

For instance, placing an order requires:

- creating an order in Order Service;
- reserving stock in Inventory Service;
- collecting payment in Payment Service;
- requesting delivery in Shipping Service.

Each service has its own local transaction on its own database. The overall workflow needs an orchestration and error-handling model.

### 10.2. Saga

A **Saga** breaks a long workflow into multiple local transactions. Each step can have a compensating action if a subsequent step fails.

Example:

| Step | Local transaction | Compensating action |
|---|---|---|
| 1 | Create PENDING Order | Cancel Order |
| 2 | Reserve inventory | Release reservation |
| 3 | Capture payment | Refund or void authorization |
| 4 | Create shipment request | Cancel shipment if still feasible |
| 5 | Confirm Order | No compensation needed if workflow completes |

Compensation is not a global database rollback. It is a new business action bringing the system back to an acceptable state. For example, refunding adds a refund transaction and history rather than deleting the earlier payment transaction.

### 10.3. Invariants during intermediate states

A saga can leave the system in an intermediate state for a period of time. The model must define which states are allowed:

- PENDING_INVENTORY;
- PENDING_PAYMENT;
- PAYMENT_AUTHORIZED;
- CANCELLATION_REQUESTED;
- COMPENSATING;
- FAILED.

Intermediate states should not be treated as violations if the business permits them and timeouts, retries, compensation, and monitoring ensure convergence to a final outcome.

Distinguish safety invariants that must hold at all times—such as never releasing shipment when unauthorized—from liveness conditions—such as valid orders eventually completing or transitioning cleanly to a failed state.

### 10.4. Outbox pattern

If a transaction updates data and publishes a message separately, two failures can occur:

- database commits, yet message is never sent;
- message is sent, yet database rolls back.

The Outbox pattern writes the business change and an outbox record in the same database transaction. Another process reads the outbox and publishes messages after commit.

~~~sql
BEGIN;

UPDATE orders
SET status = 'CONFIRMED'
WHERE order_id = :order_id;

INSERT INTO outbox_events (
    event_id,
    aggregate_id,
    event_type,
    payload,
    created_at
)
VALUES (
    :event_id,
    :order_id,
    'OrderConfirmed',
    :payload,
    CURRENT_TIMESTAMP
);

COMMIT;
~~~

A worker publishes events from the outbox and marks them sent. Messages may be delivered more than once, so consumers need idempotency or inbox/deduplication.

The outbox does not create a distributed transaction with the broker; it guarantees that recording the event to publish commits atomically with the business change in the source database.

## 11. What not to put inside a transaction

Avoid operations with unbounded latency or external system dependencies:

- calling a payment gateway;
- sending emails or SMS;
- calling shipping APIs;
- waiting for user confirmation;
- waiting for OTP entry;
- uploading large files;
- processing images or videos;
- running long reports unrelated to the update;
- waiting for another message to arrive.

These operations can be slow, time out, or fail independently. Keeping a transaction open while waiting holds connections and locks, degrading capacity for other requests.

A common structure:

1. Create a PENDING record and commit.
2. Send the external request via a worker or workflow.
3. Receive the result via callback/message.
4. Open a new transaction to update status and history.
5. Retry or compensate on failure.

For payments, distinguish authorize, capture, and refund according to provider contracts. Never assume an API call succeeding means the database committed, or vice versa.

## 12. Retries, timeouts, and commit failures

A transaction can fail due to deadlocks, serialization failures, dropped connections, or timeouts.

### 12.1. Retry only when safe

A transaction can be retried when:

- the error is classified as transient;
- the entire operation can be rerun;
- no external side effects outside the database occurred beforehand;
- idempotency protects against duplicate execution;
- retry attempts are capped and use backoff.

Never retry indefinitely. Log sufficient details for investigation and return an appropriate error once limits are exceeded.

### 12.2. Ambiguous commit outcomes

If the connection drops right after the client sends COMMIT, the client may not know whether the database committed. Never assume a network error means the transaction rolled back.

Handle this by using an idempotency key or transaction identifier to query the recorded outcome. For creation operations, a unique constraint on the idempotency key helps detect prior execution.

### 12.3. Timeouts and request cancellation

When a client times out or disconnects, the server may already have committed before noticing the cancellation. The system must decide whether the operation may proceed or must be cancelled, and provide a status lookup endpoint if required by the business.

Do not tie HTTP connection cancellation to rolling back an already-committed transaction.

## 13. Documenting transaction boundaries

For each critical invariant, document how transactions protect it.

| Field | Content |
|---|---|
| Invariant ID | Related invariant identifier |
| Transaction / use case | Business operation name |
| Participating data | Tables, aggregates, or services |
| Preconditions | Conditions before starting |
| Atomic changes | Changes that must commit together |
| Concurrency control | Constraints, locks, versioning, or isolation |
| Commit conditions | Conditions required to commit |
| Failure handling | Rollback, retry, compensation, or error state |
| Side effects | Events, emails, external APIs, and emission timing |
| Verification | Standard tests, concurrency tests, monitoring |

### 13.1. Example transaction record

**TX-ORDER-002 — ConfirmOrder**

- **Invariant:** a CONFIRMED order must have at least one valid line item and must not confirm when inventory conditions are unmet.
- **Local scope:** Order, OrderItem, Inventory, and Outbox in the same database.
- **Preconditions:** Order is in DRAFT; line items are valid; products are active for sale.
- **Atomic changes:** reserve inventory, update Order status, write reservation and outbox event.
- **Concurrency control:** lock Order; conditional inventory update; lock products in ascending ID order.
- **Commit conditions:** all lines reserve stock and status transitions validly.
- **Failure handling:** roll back entire transaction if stock is insufficient; return out-of-stock result.
- **Side effect:** worker publishes OrderConfirmed after commit.
- **Verification:** test empty order, single product out of stock, two concurrent requests claiming last unit, worker redelivering event.

If Inventory lives in another service, the transaction record must change: Order Service cannot update Inventory in the same local transaction. Instead, use a saga, reservations, and compensation with defined intermediate states.

## 14. Verifying transaction boundaries

A transaction that looks correct in a single-threaded flow can still fail under errors or contention. Test at least these scenario groups:

1. Error before the first change.
2. Error after partial changes but before commit.
3. Constraint violated at the final step.
4. Two requests modifying the same resource simultaneously.
5. Two requests checking the same multi-row condition simultaneously.
6. Deadlock or serialization failure.
7. Timeout where the client does not know the commit outcome.
8. Duplicate message delivery after commit.
9. Worker crashing mid-outbox processing.
10. One external service succeeds while the next service fails.
11. Retry after a transient failure.
12. Compensation failing and requiring continuation.

After each case, verify:

- does the invariant still hold;
- are there any partial changes left behind;
- which side effects occurred;
- can the transaction outcome be determined;
- does retrying create duplicate records or transactions;
- can intermediate states recover cleanly.

### 14.1. Rollback testing

Funds transfer example: intentionally force the recipient-account credit step to fail. After rollback, the sender balance must match its pre-transaction value and no COMPLETED transfer record may exist.

### 14.2. Concurrency testing

Run multiple concurrent requests booking the last seat or reserving stock. Results must never exceed capacity and no duplicate reservations may exist. Tests should run against a real database or equivalent engine, because mocks cannot verify locking and isolation semantics.

### 14.3. Crash recovery testing

Stop the worker after reading the outbox but before marking the row sent. Upon restart, the message may be redelivered; consumers must handle duplicates safely.

## 15. Common mistakes

- **Splitting transactions per SQL statement:** changes requiring atomicity commit separately, creating invalid intermediate states.
- **Bundling everything into one large transaction:** holds locks long and increases contention, rollbacks, and deadlocks.
- **Locking on only one write path:** another operation not using the same protocol can break the invariant.
- **Assuming BEGIN/COMMIT alone protects every invariant:** appropriate constraints, isolation, or concurrency control are required.
- **Counting then inserting without locking:** two transactions can both pass the check.
- **Holding transactions during external API calls:** timeouts and network errors keep database resources tied up.
- **Publishing messages before commit:** consumers can observe events for uncommitted data.
- **Assuming sagas are atomic rollbacks:** compensation is a separate business action that can fail and require retries.
- **Retrying every error:** business errors or non-idempotent operations can cause repeated side effects.
- **Ignoring ambiguous commit outcomes:** client-side timeouts do not prove the database rolled back.
- **Equating aggregates with system-wide transactions:** aggregates define domain consistency boundaries; multi-service workflows need different patterns.
- **Skipping concurrency and crash tests:** single-threaded happy paths do not prove transaction boundaries are sound.

## 16. Conclusion

Transaction boundaries must cover all changes that must succeed or fail together to uphold an invariant. Start from the invariant statement, identify affected data and write paths, and then select appropriate transaction boundaries, constraints, and concurrency controls.

Local transactions protect changes within one database; isolation and locks protect against contention; outbox ensures events publish after commit; sagas coordinate multi-service workflows with intermediate states and compensation. Keep transactions short, focused, safely retryable, and tested against both failures and concurrent requests.

## Self-Check

1. Why must transaction boundaries be determined from invariants rather than SQL statement counts?
2. In a funds transfer, which changes must commit or roll back together?
3. An Order is locked on confirmation, but OrderItem deletion does not use the same mechanism. What is the risk?
4. Why don't Repeatable Read or snapshots automatically protect all cross-row invariants?
5. When do you need guard rows, unique/exclusion constraints, or Serializable isolation?
6. Why should you avoid calling a payment gateway while holding a database transaction open?
7. What problem does the Outbox pattern solve? Why do consumers still need idempotency?
8. How does a Saga differ from an ACID transaction rollback?
9. A client times out right after COMMIT. Why can't you conclude the transaction rolled back?
10. Write a transaction record for a use case in a system you know, including invariants, participating data, atomic changes, concurrency control, and failure handling.
