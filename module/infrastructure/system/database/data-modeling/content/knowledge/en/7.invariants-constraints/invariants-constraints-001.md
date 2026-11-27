# An invariant describes what must always be true in a model

## Lesson Objectives

After this lesson, you will be able to explain what a data invariant is, distinguish invariants from validation and operation conditions, identify the scope within which a rule must hold, and translate business rules into verifiable constraints. You will also know how to choose where to enforce invariants—in the database, within a transaction, or in the business logic layer—handle concurrent updates, and inspect existing data before applying constraints.

## 1. What is an invariant?

An **invariant** is a predicate or condition that must always hold true for a model within a defined scope and state. An invariant describes what the system is not allowed to violate when data is created, updated, deleted, or transitioned between states.

Examples in a sales system:

- The quantity on an order line item must be greater than 0.
- Every order line item must belong to an existing order.
- An order number must be unique within a store's scope.
- The total recorded payment amount must not exceed the amount due if the business policy prohibits overpayment.
- A shipped order cannot return to the draft state.
- Two confirmed room bookings must not occupy the same room during overlapping time intervals.

These conditions do not merely describe sample data. They must hold true across every valid data state accepted by the system.

An invariant can be expressed as a logical predicate over a data state D:

~~~text
Invariant P: P(D) = true
~~~

Each valid operation transforms state D into D'. What must be guaranteed is:

~~~text
P(D) = true  =>  P(D') = true
~~~

In other words, if the state before the operation is valid, then after the operation completes, the new state must still satisfy the invariant. If an operation causes an invariant to become false, the system must reject the operation, adjust how it is executed, or bring the data back to a valid state before committing.

### 1.1. Scoped invariants

A statement such as “every order must have at least one line item” is not precise enough if draft orders are allowed to have no line items yet.

We need to clarify:

- Does it apply to orders in all states or only confirmed orders?
- Does it apply to orders imported from a legacy system?
- Must the condition hold after every SQL statement or after the transaction completes?
- Does it apply across multiple tenants or only within a single tenant?
- From what point in time does the rule take effect?

A good invariant always specifies its scope, applicability conditions, and how valid states are determined.

A clearer example:

> Every order in the CONFIRMED state must have at least one valid line item at the moment the transaction transitions the order to that state.

This statement specifies the target entity, the state condition, and the point in time when the check must hold.

## 2. Distinguishing invariants from validation and operation conditions

These concepts are related, but they address different questions.

| Concept | Question | Example |
|---|---|---|
| Invariant | What must always be true in a valid state? | An account balance must be non-negative |
| Validation | Is the input data valid according to format or rules? | The email has an accepted format |
| Precondition | What must be true before an operation is allowed to run? | The account must be active before transferring funds |
| Postcondition | What must be true after an operation completes? | The sender account decreases and the recipient account increases by the same amount |
| Authorization | Does the caller have permission to perform the action? | A user may only modify orders belonging to their own tenant |

Validation can check data before writing, yet the data can still become invalid due to another concurrent request. An invariant must be protected across all write operations and data access paths.

Preconditions and postconditions typically describe a specific operation. A correct operation must preserve the model's invariants upon completion.

Money transfer example:

- Precondition: the sender account is active and has sufficient balance.
- Operation: debit the sender account, credit the recipient account.
- Postcondition: the balances of both accounts change by the exact transfer amount.
- Invariant: the total monetary value within the managed scope is conserved, and balances remain non-negative if overdrafts are prohibited by policy.

Not every validation is an invariant. Checking that an input field has at most 100 characters may be a UI rule or an API contract. If all data stored in the database must also obey that limit, it can become a schema constraint.

## 3. Common categories of invariants

Categorizing invariants helps choose how to express them and where to enforce them.

### 3.1. Domain invariants

An attribute's value must fall within an allowed domain.

Examples:

- quantity is greater than 0;
- percentage is between 0 and 100;
- status belongs to a defined set of values;
- end date is not earlier than start date;
- currency code belongs to the list of supported currencies.

These can be protected using data types, NOT NULL, CHECK, enums, or validation at the application boundary.

~~~sql
CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    discount_percent NUMERIC(5, 2) NOT NULL
        CHECK (discount_percent >= 0 AND discount_percent <= 100)
);
~~~

Data types eliminate certain invalid values, while CHECK expresses specific domain conditions. Always verify the syntax and behavior of the database management system in use.

### 3.2. Identity and uniqueness invariants

An identifier must be unique within a defined scope.

Examples:

- each customer has a unique customer_id;
- order number is unique within a store;
- line item number is unique within an order;
- external code is unique within the same issuer and namespace.

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    store_id BIGINT NOT NULL,
    order_number VARCHAR(50) NOT NULL,
    UNIQUE (store_id, order_number)
);
~~~

The constraint above allows two stores to use the same order_number while prohibiting duplicates within the same store. The uniqueness scope must match the business rule.

### 3.3. Referential invariants

Every reference must point to a valid object within the data scope.

Examples:

- each order line item references an existing order;
- each payment references a valid order;
- each employee references an existing department if required by business rules.

~~~sql
CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0)
);
~~~

Foreign keys protect references. NOT NULL requires a reference value to be present. If a FK is allowed to be NULL, the model must clearly define what an unlinked case means.

### 3.4. Cross-attribute invariants

Two or more attributes within the same record must satisfy a relationship.

Examples:

- end date must be greater than or equal to start date;
- discounted price must not exceed original price;
- cancelled status must have a cancellation timestamp;
- a date range must have its start date before its end date.

~~~sql
CREATE TABLE contracts (
    contract_id BIGINT PRIMARY KEY,
    starts_on DATE NOT NULL,
    ends_on DATE,
    CHECK (ends_on IS NULL OR ends_on >= starts_on)
);
~~~

Placing rules close to the data ensures that every application writing to the table is subject to the same condition.

### 3.5. Cross-row invariants

The condition depends on multiple rows or multiple entities.

Examples:

- total allocated amount does not exceed the budget;
- a room does not have two overlapping confirmed bookings;
- the sum of allocation lines must equal the transaction total;
- every confirmed order has at least one line item.

This category is difficult to express with a simple CHECK constraint because a standard CHECK only inspects values of the row being written. You should not rely on a CHECK containing a query to another table as if it could safely protect a cross-row rule on its own. Instead, choose an appropriate combination of UNIQUE, foreign keys, exclusion constraints, triggers, or transaction/business logic.

### 3.6. State and state-transition invariants

An object has a set of valid states and may only transition along permitted paths.

Example:

~~~text
DRAFT -> CONFIRMED -> FULFILLING -> SHIPPED -> COMPLETED
   |          |
   v          v
CANCELLED   CANCELLED
~~~

Not every pair of states allows a direct transition. A SHIPPED order may not be allowed to transition back to DRAFT. This rule is not just checking whether a status belongs to a list; it checks the relationship between the prior state and the next state.

This can be protected using state-transition logic in a domain service, transactions, and concurrency control. If multiple services update the status, a unified mechanism is needed so that no write path bypasses the rule.

### 3.7. Temporal invariants

Rules that depend on time, effective periods, or event ordering.

Examples:

- end timestamp is not earlier than start timestamp;
- an identifier is not assigned to two objects during overlapping effective periods;
- an employee does not have two primary assignments active at the same time;
- a room booking does not overlap with another confirmed booking.

Some rules can use range types or exclusion constraints in DBMSs that support them. In other systems, transactions and appropriate locking may be needed to check time intervals safely.

### 3.8. Aggregate and balance invariants

A dataset must maintain an overall aggregate relationship.

Examples in accounting:

- total debits equal total credits in every journal entry;
- account balance is derived from transactions according to a defined rule;
- total budget allocations do not exceed the approved limit.

For balance rules, you must define the grain, aggregation scope, currency, precision, and posting point. If multiple currencies are involved, amounts in different units must not be summed directly without conversion rules.

## 4. Invariants at the attribute, entity, and model levels

Invariants can apply at multiple levels.

### 4.1. Attribute level

An attribute has a clear value domain:

- quantity is a positive integer;
- currency_code matches the required format and belongs to the supported list;
- status does not accept arbitrary values;
- email must not be NULL if required by the business.

Simple rules are usually well suited for NOT NULL, CHECK, data types, and enums.

### 4.2. Entity level

A record must satisfy multiple combined conditions:

- a contract has valid start and end dates;
- a payment must have a positive amount, currency, and transaction ID;
- the COMPLETED status requires completed_at;
- a closed record does not accept ordinary attribute updates.

Database constraints can be combined with business logic to protect conditions that depend on state or workflow.

### 4.3. Relationship level

Relationships must enforce cardinality, optionality/mandatory participation, or linking conditions:

- every OrderItem belongs to exactly one Order;
- each account has at most one active verification profile;
- an employee has only one primary department at a time;
- a confirmed order must have at least one line item.

Foreign keys and UNIQUE constraints handle many cases, but some minimum-cardinality conditions on the parent side require transactions, triggers, or other mechanisms.

### 4.4. Aggregate or whole-model level

An aggregate is a consistency boundary designed to protect related rules within a single business unit. For example, an order and its line items can be modified within the same transaction before the order is confirmed.

A whole-model invariant may span multiple aggregates or multiple services. In that case, you must determine whether the rule must be guaranteed immediately or can converge after an asynchronous workflow. You should never claim that an invariant is globally guaranteed if the architecture only checks it locally within individual services.

## 5. Choosing where to enforce invariants

A rule can be checked at multiple layers. Choose where to enforce it based on scope, technology capabilities, and how data is written.

### 5.1. Database constraints

The database is suitable for rules that can be declared directly and must be protected regardless of which application writes the data.

Common mechanisms:

| Mechanism | What it protects | Example |
|---|---|---|
| NOT NULL | Required value | order_id must be present |
| CHECK | Row-level condition | quantity > 0 |
| PRIMARY KEY | Unique and non-NULL identifier | order_id |
| UNIQUE | No duplicates within key scope | (store_id, order_number) |
| FOREIGN KEY | Valid reference | order_items.order_id |
| EXCLUSION | Disallows conflicting values/ranges by operator | Non-overlapping room booking intervals |
| Trigger | Rules needing operation- or multi-row logic | Validating state-dependent changes |

The advantage of database constraints is that every write path into the database is checked, including batch jobs and other applications. However, constraints must be designed properly and do not replace all business logic.

### 5.2. Business-layer logic

Some rules require business context or multiple steps:

- does the current state allow this action;
- does the user have permission to make the change;
- is approval required before exceeding a limit;
- can a confirmed order have its line items edited;
- can a process complete once an external service confirms.

These rules typically belong in a domain service or application service. However, if multiple processes can update the same data, application logic must combine transactions, locking, or concurrency control. Simply reading data and checking it in the application can introduce race conditions.

### 5.3. API or UI validation

APIs and UIs should validate early to provide friendly feedback:

- required fields;
- format;
- length;
- value domain;
- data that can surface errors immediately.

This is the user-experience and boundary-protection layer. It is not the final guarantee for data integrity if batch imports, workers, admin scripts, or other services can write directly.

### 5.4. Choosing a layer by rule type

| Rule type | Typically appropriate enforcement layer |
|---|---|
| NOT NULL, simple value domain | Database and API |
| Uniqueness over one or more columns | UNIQUE/index and error handling in the application |
| Referential existence | FOREIGN KEY |
| Business state transitions | Domain service + transaction |
| Non-overlapping time intervals | Exclusion constraint or transaction/locking |
| Multi-row aggregation | Transaction, trigger, or appropriate domain workflow |
| User/tenant access control | Authorization and database-level data protection if available |
| Cross-service convergent rules | Event/process orchestration and consistency checks |

The same rule can be enforced across multiple layers to improve user experience and safeguard data. Avoid letting layers use conflicting definitions—for example, the API allowing quantity 0 while the database rejects it.

## 6. Protecting invariants under concurrent updates

An invariant may hold when checking individual requests in isolation yet be violated when two requests execute simultaneously.

### 6.1. Race condition when checking quantities

Suppose a room has only one spot left. Two requests both read available_count = 1. Both check and see availability, then both create a booking. The result is two bookings even though only one spot remained.

A “read-then-write” check in the application is unsafe without concurrency control.

### 6.2. Conditional updates

For inventory quantities, an atomic UPDATE statement can be used:

~~~sql
UPDATE inventory
SET available_quantity = available_quantity - 1
WHERE product_id = :product_id
  AND available_quantity >= 1;
~~~

After executing, the application checks the affected row count:

- 1 row: reservation succeeded;
- 0 rows: insufficient stock or the product does not exist.

The database evaluates the condition and performs the update in a single atomic operation according to the DBMS's concurrency mechanism. If a booking must be recorded alongside decrementing inventory, wrap both in a single transaction so they commit or roll back together.

### 6.3. Pessimistic locking

Records to be checked can be locked inside a transaction, such as with SELECT ... FOR UPDATE in DBMSs that support it.

Workflow:

1. Begin transaction.
2. Lock the inventory record.
3. Read the latest quantity.
4. Verify sufficient stock.
5. Decrement quantity and create booking.
6. Commit.

Other requests must wait or handle a timeout according to policy. Locks should be acquired in a consistent order to reduce the risk of deadlocks.

### 6.4. Optimistic locking

A version column can be used to detect whether data has changed:

~~~sql
UPDATE inventory
SET available_quantity = :new_quantity,
    version = version + 1
WHERE product_id = :product_id
  AND version = :expected_version;
~~~

If no row is updated, the version has changed; the application must re-read and retry or return a conflict error.

Optimistic locking is suitable when contention is infrequent. Retries must be bounded and must never blindly repeat side effects outside the database.

### 6.5. Isolation levels and serializable transactions

Transaction isolation determines the extent to which transactions observe each other's changes. For certain cross-row invariants, SERIALIZABLE or explicit locking may be required to prevent write skew.

SERIALIZABLE can cause transactions to abort when serialization conflicts are detected. The application must handle retries safely. Simply choosing a higher isolation level is no substitute for understanding the rule and testing under real concurrency.

## 7. Example: protecting order invariants

Consider a simple model consisting of Order and OrderItem.

Rules:

1. Every line item belongs to exactly one order.
2. Quantity must be a positive integer.
3. Unit price is non-negative.
4. Draft orders may have no line items yet.
5. An order may only transition to CONFIRMED when it has at least one valid line item.
6. A SHIPPED order must not return to DRAFT.

### 7.1. Database constraints

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'SHIPPED', 'CANCELLED'))
);

CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);
~~~

These constraints protect valid status membership, the order reference, quantity, and unit price. They do not yet guarantee that a CONFIRMED order has at least one line item, nor do they enforce valid state-transition paths.

### 7.2. State-transition transaction

A workflow can:

1. Begin transaction.
2. Lock the Order row to be confirmed.
3. Verify the current status is DRAFT.
4. Verify there is at least one valid OrderItem.
5. Update status to CONFIRMED.
6. Commit.

If adding/removing line items and confirming the order can occur concurrently, both write paths must be protected. For instance, operations that add or delete line items must lock or check the same Order using a consistent mechanism. If only the confirmation operation locks the Order while line-item deletion does not coordinate via the same mechanism, the invariant can still be violated.

### 7.3. Conditional state transition

Updates can be restricted by prior state:

~~~sql
UPDATE orders
SET status = 'SHIPPED'
WHERE order_id = :order_id
  AND status = 'CONFIRMED';
~~~

If no rows are updated, the order is not in an allowed state or does not exist. This helps prevent certain invalid state updates, though additional rules—such as shipment items being ready, inventory deducted, or payment confirmed—still need to be enforced.

## 8. Example: total amount and balance invariants

Suppose an order has line items with quantity and unit_price. Line totals are calculated as:

~~~text
line_total = quantity * unit_price
order_total = SUM(line_total) - discounts + fees
~~~

You must determine:

- whether unit price includes tax;
- whether discounts apply per line or to the entire order;
- whether rounding rules apply per line or at the final total;
- which currency is used;
- whether order_total is recomputed or stored as a snapshot;
- what happens if line items change after confirmation.

If order_total is stored as a cached value or snapshot, a synchronization rule is required. If it is computed dynamically from lines, transactions must be controlled so reports do not read a half-updated state.

In double-entry accounting, a journal entry typically requires total debits to equal total credits within the same currency and entry scope. A per-row CHECK alone cannot guarantee that the sum across multiple rows balances. Stored procedures, deferred triggers, or a transaction service that only posts balanced entries may be needed.

Avoid binary floating-point types for monetary calculations requiring decimal precision. Choose NUMERIC/DECIMAL with appropriate precision and scale, and define rounding behavior explicitly.

## 9. Example: non-overlapping time intervals

Suppose a meeting room cannot have two overlapping confirmed bookings.

The invariant can be stated as:

> For the same room_id, two bookings in the CONFIRMED status must not have intersecting time intervals.

If the DBMS supports range types and exclusion constraints, this can be expressed directly. PostgreSQL example:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_bookings (
    booking_id BIGINT PRIMARY KEY,
    room_id BIGINT NOT NULL,
    during TSTZRANGE NOT NULL,
    status VARCHAR(20) NOT NULL,
    CHECK (NOT isempty(during)),
    EXCLUDE USING gist (
        room_id WITH =,
        during WITH &&
    ) WHERE (status = 'CONFIRMED')
);
~~~

In this PostgreSQL example, the && operator tests whether two ranges intersect. The exclusion constraint prevents two confirmed bookings for the same room from having overlapping ranges. Choose range types, open/closed bounds, and time rules appropriate to the domain.

If the database does not support exclusion constraints, you can check within a transaction using a lock on the room resource or an equivalent serialization mechanism. Simply querying for overlapping bookings and then inserting without locking or concurrency protection can cause a race condition.

## 10. Invariants in multi-service systems

In distributed architectures, data may reside in separate databases and synchronize via messages. Not every invariant can be protected by a single ACID transaction.

We must distinguish:

- **Local invariants:** must always hold within a single database or aggregate.
- **Cross-service invariants:** depend on data owned by multiple services.
- **Convergence conditions:** state may be temporarily out of sync but must reach a consistent outcome after the workflow completes.
- **Safety invariants:** something bad must never happen, such as double-charging a customer.
- **Liveness invariants:** something good must eventually happen, such as a valid transaction eventually completing or failing cleanly.

For example, the order service and payment service have separate databases. You cannot assume a single SQL transaction spans both. A saga or orchestration workflow can be used:

1. Order transitions to PENDING_PAYMENT.
2. Payment service creates a request with an idempotency key.
3. Provider returns a result.
4. Payment service emits an event.
5. Order service updates status based on the event.
6. If payment fails or expires, the workflow cancels or retries according to policy.

During synchronization, the order may remain in PENDING_PAYMENT. The model must clearly define which intermediate states are valid and what must never occur—for example, never releasing a shipment before required payment conditions are met.

Idempotency, outbox/inbox patterns, bounded retries, and duplicate-event handling help protect invariants in environments where messages may be redelivered.

## 11. Detecting and fixing data that violates invariants

Before adding a constraint to a running system, inspect existing data. If data already violates the rule, the migration may fail or the new constraint cannot be enabled safely.

### 11.1. Inspecting data before applying constraints

Example finding invalid quantities:

~~~sql
SELECT order_item_id, quantity
FROM order_items
WHERE quantity <= 0;
~~~

Finding orphaned foreign keys:

~~~sql
SELECT oi.order_item_id, oi.order_id
FROM order_items oi
LEFT JOIN orders o ON o.order_id = oi.order_id
WHERE o.order_id IS NULL;
~~~

Finding duplicate order numbers within a store:

~~~sql
SELECT store_id, order_number, COUNT(*)
FROM orders
GROUP BY store_id, order_number
HAVING COUNT(*) > 1;
~~~

These queries identify records that must be resolved before enabling constraints.

### 11.2. Planning data remediation

For each violation, determine:

- which data is the authoritative source of truth;
- whether it can be fixed automatically or requires an authorized person;
- whether old values must be retained for audit purposes;
- whether dependent relationships will be affected;
- how to prevent new violations while the migration is running;
- how to roll back if the migration fails.

Do not delete violating data just to make a migration pass if that data has business or legal value.

### 11.3. Adding constraints safely

For a system under load, a multi-step rollout may be needed:

1. Analyze and quantify violations.
2. Remediate or quarantine invalid data.
3. Deploy new code so no new violations are created.
4. Add the constraint or index using the least-locking method supported by the DBMS.
5. Verify that the constraint has been fully validated.
6. Monitor write errors and queries after deployment.

Statement syntax, the ability to add unvalidated constraints, and online indexing strategies vary by DBMS. Consult your database version's documentation before choosing a migration approach.

## 12. Documenting and verifying invariants

An important invariant should be documented as part of the data model or business documentation.

Recommended fields:

| Field | Meaning |
|---|---|
| Invariant ID | Stable identifier, e.g. INV-ORDER-001 |
| Statement | Condition that must always hold |
| Scope | Entity, aggregate, tenant, or system |
| Applicability | State, point in time, or record type |
| Owner | Person/team with business accountability |
| Enforcement mechanism | CHECK, FK, UNIQUE, transaction, domain logic... |
| Behavior on violation | Reject, retry, quarantine, or manual handling |
| Verification | Query, test, metric, or audit |
| Links | Related requirements, decisions, schemas, and APIs |

### 12.1. Example invariant record

**INV-ORDER-001 — Confirmed order has at least one line item**

- Statement: An Order in the CONFIRMED state must have at least one valid OrderItem.
- Scope: a single Order and its OrderItems.
- Applicability: at the time of the order-confirmation transaction.
- Enforcement mechanism: transaction checks line count and locks Order; line-item add/delete operations coordinate using the same mechanism.
- Behavior on violation: disallow state transition and return a business error.
- Verification: test empty order, single-line order, two concurrent confirmation requests, and concurrent line-item deletion requests.
- Owner: Order domain team.

This record helps engineers understand the condition, testers know which scenarios to verify, and operators know how to detect violations.

### 12.2. Testing invariants

Testing can be structured across layers:

- **Unit tests:** verify domain functions or state-transition logic.
- **Integration tests:** confirm the database actually rejects violating data.
- **Concurrency tests:** execute concurrent requests to uncover race conditions.
- **Migration tests:** test legacy data handling and constraint activation.
- **Monitoring:** run violation-detection queries or track constraint errors in production.

Do not test only the happy path. Actively test invalid data, duplicate requests, concurrent updates, timeouts, and retries.

## 13. Common mistakes

- **Validating only in the UI:** batch jobs or other services can write invalid data. Place constraints at a layer that protects all write paths.
- **Defining invariants too vaguely:** “a valid order” does not specify state, scope, or which conditions must hold.
- **Using CHECK for cross-row rules:** standard CHECK constraints are not a safe mechanism for checking aggregates or querying other records.
- **Reading then writing without concurrency protection:** two requests can pass the check together and create an invalid state.
- **Assuming transactions automatically solve all race conditions:** isolation levels and locking strategies must match the invariant.
- **Confusing validation with authorization:** properly formatted data does not mean the caller is permitted to modify it.
- **Using undocumented triggers:** hidden logic can make errors hard for applications to interpret or cause unexpected side effects.
- **Enabling constraints before checking legacy data:** migrations can fail or disrupt writes.
- **Failing to define violation responses:** users and calling services need to know whether an error is fixable, retryable, or fatal.
- **Failing to check all write paths:** one service may preserve an invariant while a batch import breaks it.
- **Claiming global invariants in distributed systems:** when only local checks and asynchronous synchronization exist, describe intermediate states and convergence conditions explicitly.

## 14. Conclusion

An invariant describes what must always hold true within valid data states and a defined scope. It may involve value domains, identities, references, multiple attributes, multiple rows, states, time, or aggregates.

To protect invariants, write rules clearly, define scope and timing, choose appropriate enforcement mechanisms, handle concurrent updates, and inspect existing data. Database constraints protect correctness at the storage layer; transactions and business logic protect complex workflows; validation catches errors early. All layers must share the same definition so the model remains consistent.

## Self-Check

1. How does an invariant differ from validation and preconditions?
2. Why does the statement “every order must have at least one line item” need to specify the applicable state?
3. Distinguish domain invariants, referential invariants, and cross-row invariants with examples.
4. Why is CHECK unsuitable for guaranteeing the total amount across multiple rows?
5. How can two requests booking the last remaining spot violate an invariant? Give two ways to protect against it.
6. When should you use UNIQUE, FOREIGN KEY, transactions, or exclusion constraints?
7. In a multi-service system, how should local invariants and convergence conditions be distinguished?
8. What should you inspect and prepare before adding a constraint to a running database?
9. Write an invariant record for a rule in a system you know, including statement, scope, enforcement mechanism, and verification method.
