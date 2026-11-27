# Defining Update, Delete, and Data Integrity Behaviors

A relational schema does not merely answer “which tables exist and which keys link them?”—it must also answer **what is permitted to happen when data changes**. When a customer is deleted, should past orders be deleted too? When a department code changes, do employees in that department need to be updated? When canceling an order, should order lines already used for invoicing be deleted? If two users edit a balance concurrently, how do we guarantee it never goes negative?

These questions relate directly to **update/delete behavior**, **referential integrity**, **domain integrity**, **entity integrity**, and **business invariants**. They must be defined during modeling, rather than deferred until API implementation.

In the **Relational Modeling** chapter of the **DATABASE_DATA_MODELING** module, the goal is to translate business requirements into enforceable tables, keys, indexes, and verification rules; understand the limits of each mechanism; and choose models suited to history, performance, concurrency, and system evolution.

## 1. Types of Integrity to Distinguish

Suppose a sales system has **Customer**, **Order**, **OrderLine**, and **Product**:

~~~text
Customer 1 ─── N Order 1 ─── N OrderLine N ─── 1 Product
                   |
                   └── status DRAFT / CONFIRMED / CANCELLED
~~~

For this model to be sound, multiple layers of rules must be protected:

| Integrity Layer | Question | Common Relational Mechanisms |
| --- | --- | --- |
| **Entity** | Does each record have a unique, unambiguous identifier? | PRIMARY KEY, UNIQUE, NOT NULL |
| **Domain** | Is quantity positive, and is status within the valid set? | Data types, NOT NULL, CHECK, domain |
| **Referential** | Does Order point to an existing Customer? Does OrderLine point to an existing Order/Product? | FOREIGN KEY and ON DELETE/ON UPDATE actions |
| **Multiplicity / relationship** | Must an Order have at least one line when confirmed? Does a customer have at most one primary email? | UNIQUE/partial unique index; cross-row checks where needed |
| **Business** | Cannot edit the amount of a reconciled order? Cannot sell when out of stock? | Transactions, constraints, triggers/procedures, write workflows |
| **Temporal / historical** | Are shipping address and price at purchase time preserved? | Snapshots, version tables, effective dates, immutability rules |
| **Concurrency** | Can two transactions concurrently turn a valid state invalid? | Locks, isolation, atomic operations, retries |

An **invariant** is a statement that must always hold true at system-defined points—for example, “every stored order line must point to an existing order” or “stock quantity is non-negative”. Always clarify **when it is checked**: at the end of each statement, at transaction commit, during a business state transition, or as of a historical point in time.

A foreign key only protects **the existence of the referenced record**. It does not know whether a customer is still active, whether a product is still for sale, or whether an order has already been closed for accounting.

## 2. Behavior When a Parent Row Is Updated or Deleted

In a relational database, a **foreign key** can specify what happens to **child rows** when **the parent row's referenced key changes** or **the parent row is deleted**. Two directions must be distinguished:

- **ON DELETE:** what happens when deleting the referenced record?
- **ON UPDATE:** what happens when updating **the referenced key value**?

Updating an ordinary attribute on the parent row—such as name or description—**does not trigger ON UPDATE** on the FK as long as the referenced key value remains unchanged.

### 2.1. Comparison Table of Referential Actions

| Action | Meaning | When to Consider | Caution |
| --- | --- | --- | --- |
| **NO ACTION** | Does not auto-modify child rows; rejects if FK is invalid at check time | Protecting references while managing intentional changes | In PostgreSQL, checking can be deferred if the constraint is DEFERRABLE |
| **RESTRICT** | Blocks deleting/updating parent key if child rows still reference it | Historical documents, data that must not cascade-delete | PostgreSQL cannot defer the RESTRICT action itself |
| **CASCADE** | Deletes child rows when parent is deleted; updates child FK when parent key updates | Strictly lifecycle-dependent parts or natural keys that must update in sync | Can affect large row counts; inspect chained relationships |
| **SET NULL** | Detaches link by setting child FK to NULL | Optional links where child rows remain meaningful independently | FK column must be nullable; loses reference if no history is stored |
| **SET DEFAULT** | Sets child FK to its declared DEFAULT when parent is deleted/updated | When a policy-defined valid default object exists | DEFAULT must satisfy the FK (or be NULL if allowed); avoid fake placeholder exceptions |

In PostgreSQL, **NO ACTION** is the default action when unspecified. It is normally checked at the end of the statement, or at transaction commit when the FK is declared **DEFERRABLE** and actually set to deferred mode. **RESTRICT** blocks the operation immediately and cannot defer that restriction check. Both actions behave identically in many ordinary operations, yet differ inside transactions that temporarily alter links and restore validity before commit.

**CASCADE does not mean updating all data on child rows.** ON UPDATE CASCADE only updates **the corresponding FK columns** when the parent key changes; it does not recalculate prices, permissions, or business statuses.

### 2.2. Choosing Actions from Lifecycle Semantics

Classify each relationship using these questions:

1. Can the child row **exist independently** after the parent row disappears?
2. Is the child row a **document/history record that must be retained**?
3. Does deleting a parent record mean **physical deletion** or merely **deactivation**?
4. Is the link to the parent **mandatory** or optional?
5. Is the parent key genuinely **allowed to change**, or should identifiers be immutable?
6. May a child row be reassigned to another parent, and who is authorized to do so?
7. Do legal, contractual, or retention policies govern deletion?

There is no universal rule like “every foreign key should CASCADE” or “every table should RESTRICT”. A choice is right only when it accurately reflects the lifecycle of each entity pair.

## 3. PostgreSQL Example: Orders, Order Lines, and Shopping Carts

Suppose the business specifies:

- A Customer can place multiple Orders.
- An Order once created must keep referencing a valid Customer in business data.
- An OrderLine belongs to an Order and references a Product; lines of confirmed orders are documents that must be preserved.
- Price on OrderLine is **the locked-in transaction price**, unaffected by changes to the Product's current price.
- Temporary shopping carts can be completely deleted along with their cart items since no accounting document was created yet.
- A Product cannot be physically deleted if OrderLines still reference it; it can be **archived/discontinued** instead of deleted.

### 3.1. Illustrative Schema

~~~sql
-- PostgreSQL; uses BY DEFAULT so learning examples can assign explicit IDs.
CREATE TABLE customers (
    customer_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    full_name   TEXT NOT NULL CHECK (btrim(full_name) <> ''),
    status      TEXT NOT NULL DEFAULT 'ACTIVE'
                CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED'))
);

CREATE TABLE products (
    product_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku        TEXT NOT NULL UNIQUE,
    title      TEXT NOT NULL,
    list_price NUMERIC(14, 2) NOT NULL CHECK (list_price >= 0),
    archived_at TIMESTAMPTZ
);

CREATE TABLE sales_orders (
    order_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT'
           CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    shipping_address_text TEXT NOT NULL,
    CONSTRAINT fk_order_customer FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(14, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_line_order FOREIGN KEY (order_id)
        REFERENCES sales_orders(order_id) ON DELETE RESTRICT,
    CONSTRAINT fk_line_product FOREIGN KEY (product_id)
        REFERENCES products(product_id) ON DELETE RESTRICT
);

CREATE TABLE shopping_carts (
    cart_id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id) ON DELETE CASCADE
);

CREATE TABLE shopping_cart_items (
    cart_id BIGINT NOT NULL
        REFERENCES shopping_carts(cart_id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL
        REFERENCES products(product_id) ON DELETE RESTRICT,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (cart_id, product_id)
);
~~~

In this example, **OrderLine** is part of Order, yet does not auto-delete with Order. Because the business treats order lines as accounting documents, **RESTRICT** is chosen to prevent accidental physical deletion. By contrast, **shopping_cart_items** are deleted with their temporary cart because they carry no independent archival obligation.

The **sales_orders** table stores the shipping address string at order placement time. This is a simple example of a **transaction snapshot**: when a Customer edits their current address, the shipping address on past orders does not change along with it. Production systems may need multi-field address structures, versioning, and richer audit details.

### 3.2. Sample Data and Testing Delete Behavior

~~~sql
INSERT INTO customers(customer_id, full_name)
VALUES (101, 'Nguyễn Thị Lan');

INSERT INTO products(product_id, sku, title, list_price)
VALUES (501, 'BOOK-001', 'Data Design Book', 180000);

INSERT INTO sales_orders(order_id, customer_id, status, shipping_address_text)
VALUES (1001, 101, 'CONFIRMED', '12 Nguyễn Huệ, TP.HCM');

INSERT INTO order_lines(order_id, line_no, product_id, quantity, unit_price)
VALUES (1001, 1, 501, 2, 175000);

INSERT INTO shopping_carts(cart_id, customer_id)
VALUES (701, 101);

INSERT INTO shopping_cart_items(cart_id, product_id, quantity)
VALUES (701, 501, 1);
~~~

When deleting the temporary cart:

~~~sql
DELETE FROM shopping_carts WHERE cart_id = 701;
-- shopping_cart_items for cart 701 are deleted via ON DELETE CASCADE.
~~~

When deleting Customer 101, the database rejects it because Order 1001 still references the Customer:

~~~sql
DELETE FROM customers WHERE customer_id = 101;
-- Rejected: fk_order_customer with ON DELETE RESTRICT.
~~~

The failed DELETE does **not** allow deleting the Customer merely because shopping carts were configured with CASCADE. When a parent has multiple dependent relationships, the operation must satisfy **all** constraints; one RESTRICT FK can block the deletion even if another FK uses CASCADE.

Similarly:

~~~sql
DELETE FROM products WHERE product_id = 501;
-- Rejected because order_lines still references Product 501.
~~~

Instead of deleting a product that has participated in transactions, you can **discontinue/archive** it:

~~~sql
UPDATE products
SET archived_at = CURRENT_TIMESTAMP
WHERE product_id = 501
  AND archived_at IS NULL;
~~~

Marking a product as archived does not lose historical links from OrderLine to Product. However, **a foreign key does not automatically block** creating a new OrderLine pointing to an archived Product: if the business forbids selling discontinued products, enforce a check at order creation/approval time.

### 3.3. Why Avoid CASCADE on Documents?

If you changed `fk_line_order` to ON DELETE CASCADE, a single DELETE on Order could wipe out all OrderLines. In systems handling payments, taxes, refunds, audits, and customer support, cascading deletes can destroy essential records.

For documents, options worth considering typically include:

- **RESTRICT or NO ACTION** to block deleting referenced rows.
- **A canceled status** instead of physical DELETE.
- **Adjustment/reversal entries** instead of directly mutating closed records.
- **Controlled archiving/anonymization** according to retention schedules.

Specify explicitly whether **DRAFT** orders may be physically deleted. If one Order table holds both drafts and finalized documents, a plain FK cannot distinguish “deleting a draft is allowed, deleting a confirmed order is forbidden” by status; the design must add business logic or separate lifecycles appropriately.

## 4. ON UPDATE CASCADE, SET NULL, and SET DEFAULT

### 4.1. ON UPDATE CASCADE When Changing a Referenced Key

Suppose **department_code** is a referenced business code. When changing the code from ENG to DEV, the business wants employees in that department to keep referencing **the exact same department**:

~~~sql
CREATE TABLE departments (
    department_code TEXT PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    full_name TEXT NOT NULL,
    department_code TEXT,
    CONSTRAINT fk_employee_department
        FOREIGN KEY (department_code)
        REFERENCES departments(department_code)
        ON UPDATE CASCADE
        ON DELETE SET NULL
);

INSERT INTO departments(department_code, name)
VALUES ('ENG', 'Engineering');

INSERT INTO employees(employee_id, full_name, department_code)
VALUES (8, 'Minh', 'ENG');

UPDATE departments
SET department_code = 'DEV'
WHERE department_code = 'ENG';

-- Minh's employees.department_code is updated from ENG to DEV.
~~~

ON UPDATE CASCADE adjusts the **foreign key** alongside the parent key. The employee still belongs to **the same Department entity** when the business merely renames the identifier. If changing the code also changes the nature of the department or splits/merges departments, that is no longer a simple key rename and requires a dedicated business workflow.

**Designing with a stable surrogate key** usually avoids updating referenced keys altogether. An immutable `department_id` as PK plus a mutable `UNIQUE department_code` is often preferable when business codes change easily. ON UPDATE CASCADE is useful, yet not a reason to make primary keys arbitrarily mutable.

### 4.2. ON DELETE SET NULL When the Link Is Optional

In our example, **employees.department_code** allows NULL, so:

~~~sql
DELETE FROM departments
WHERE department_code = 'DEV';

-- Minh still exists; department_code becomes NULL.
~~~

This makes sense **only when an employee can temporarily belong to no department**. If every active employee must belong to a department, SET NULL breaks the business rule; choose RESTRICT, reassign employees before deleting, or separate active statuses.

If the FK is **NOT NULL**, ON DELETE SET NULL normally fails because it violates NOT NULL. Never choose SET NULL when the model does not allow “no parent”.

In PostgreSQL, you can specify **a column list to SET NULL** in certain composite FK delete cases; this requires careful design so tenant/identity columns are not unintentionally nulled out. Do not assume all DBMSs support the same syntax.

### 4.3. ON DELETE SET DEFAULT

SET DEFAULT replaces the child row's FK value with its declared default value. If the DEFAULT points to a nonexistent parent row, the FK is still violated.

Example illustrating a policy with an unclassified queue:

~~~sql
CREATE TABLE support_queues (
    queue_id INTEGER PRIMARY KEY,
    queue_name TEXT NOT NULL
);

INSERT INTO support_queues(queue_id, queue_name)
VALUES (0, 'Unclassified'), (10, 'Technical Support');

CREATE TABLE tickets (
    ticket_id BIGINT PRIMARY KEY,
    queue_id INTEGER NOT NULL DEFAULT 0
        REFERENCES support_queues(queue_id)
        ON DELETE SET DEFAULT
);

INSERT INTO tickets(ticket_id, queue_id) VALUES (9001, 10);

DELETE FROM support_queues WHERE queue_id = 10;
-- Ticket 9001 switches queue_id to 0, because queue 0 already exists.
~~~

This is a rule for **reassigning child rows to a default group**, not self-destructing tickets. Apply it only if “Unclassified” is genuinely a valid business state. Using dummy rows solely to bypass FK errors can mask data anomalies.

You cannot normally delete queue 0 while tickets still point to 0 and SET DEFAULT also tries to set the FK to 0; the default row itself needs a protective policy.

## 5. NO ACTION, RESTRICT, and Deferred Constraints

Some rules cannot be evaluated purely on **an intermediate state within a transaction**. For instance, a system may need to temporarily replace a parent row while ending with the same final identity.

In PostgreSQL, a foreign key can be declared:

~~~sql
CREATE TABLE parent_records (
    parent_id BIGINT PRIMARY KEY
);

CREATE TABLE child_records (
    child_id BIGINT PRIMARY KEY,
    parent_id BIGINT NOT NULL,
    CONSTRAINT fk_child_parent
        FOREIGN KEY (parent_id)
        REFERENCES parent_records(parent_id)
        ON DELETE NO ACTION
        ON UPDATE NO ACTION
        DEFERRABLE INITIALLY IMMEDIATE
);
~~~

By default, the constraint is checked after each statement. Inside a specific transaction, you can request deferral:

~~~sql
BEGIN;

SET CONSTRAINTS fk_child_parent DEFERRED;

-- Operations are permitted to temporarily break references
-- provided all references are validly restored before COMMIT.

COMMIT;
-- FK is checked before the transaction completes successfully.
~~~

Not every constraint can be DEFERRED, and not every FK action has the same deferral semantics. **RESTRICT in PostgreSQL cannot be deferred like NO ACTION**; never swap them without checking multi-step update flows.

Deferred constraints do not mean “allow bad data to be committed”. They allow an **intermediate state** inside a transaction to temporarily violate the constraint, while **the final state must be valid**. Limit their use and handle errors at COMMIT, since failures surface later than the statement that caused them.

## 6. Keys, UNIQUE, CHECK, and NULL Corner Cases

Referential integrity is only part of the model. Row-level and set-level rules require additional mechanisms.

### 6.1. NOT NULL and CHECK Must Work Together

~~~sql
CREATE TABLE stock_balances (
    product_id BIGINT PRIMARY KEY
        REFERENCES products(product_id) ON DELETE RESTRICT,
    available_quantity INTEGER NOT NULL
        CHECK (available_quantity >= 0),
    reserved_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (reserved_quantity >= 0)
);
~~~

In SQL/PostgreSQL, a CHECK constraint is violated only when the expression evaluates to **FALSE**; an **UNKNOWN** result caused by NULL is accepted. Therefore:

~~~sql
quantity INTEGER CHECK (quantity > 0)
~~~

does not automatically require quantity to be non-NULL. If quantity is mandatory, write:

~~~sql
quantity INTEGER NOT NULL CHECK (quantity > 0)
~~~

A common mistake is writing a CHECK assuming it enforces a required value while forgetting NOT NULL.

### 6.2. Scoped UNIQUE

For example, a customer can have multiple emails but **at most one primary email**:

~~~sql
CREATE TABLE customer_emails (
    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (customer_id, email)
);

CREATE UNIQUE INDEX uq_customer_primary_email
ON customer_emails(customer_id)
WHERE is_primary;
~~~

The composite key prevents repeating an email for **the same customer**, without forbidding the email from being used across multiple customers. The partial unique index prevents having two primary emails for the same customer.

However, it only guarantees **at most one** primary email; **it does not guarantee at least one**. Minimum-count rules typically require multi-row checking mechanisms.

### 6.3. UNIQUE and NULL Do Not Always Mean “Only One NULL”

In PostgreSQL, a standard UNIQUE constraint allows multiple NULLs because NULL values are treated as distinct by default. Newer PostgreSQL versions support **NULLS NOT DISTINCT** to treat NULLs as indistinguishable in UNIQUE constraints.

Do not treat UNIQUE(email) on a nullable email column as proof that every customer has provided a valid email; NULL rows can still appear. Always state **mandatory/optional** rules separately from uniqueness rules.

### 6.4. Composite FKs and NULL

For multi-column foreign keys, consider **MATCH SIMPLE** (PostgreSQL default) vs. **MATCH FULL**:

- Under **MATCH SIMPLE**, if **any** FK component is NULL, the child row does not need to satisfy the referential check for that tuple of columns.
- Under **MATCH FULL**, only when **all** FK components are NULL is checking skipped; a mix of NULL and non-NULL is rejected. When all are non-NULL, the tuple must exist in the parent table.

Example where employee IDs are unique only within a tenant:

~~~sql
CREATE TABLE tenant_employees (
    tenant_id BIGINT NOT NULL,
    employee_id BIGINT NOT NULL,
    full_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, employee_id)
);

CREATE TABLE optional_assignments (
    assignment_id BIGINT PRIMARY KEY,
    employee_tenant_id BIGINT,
    employee_id BIGINT,
    CONSTRAINT fk_assignment_employee
        FOREIGN KEY (employee_tenant_id, employee_id)
        REFERENCES tenant_employees(tenant_id, employee_id)
        MATCH FULL
);
~~~

This design allows **both columns to be NULL** when unassigned, yet rejects having tenant_id without employee_id or vice versa. Once assigned, both columns must match a single existing employee.

**MATCH FULL does not replace same-tenant ownership rules for the parent object.** If Assignment also has its own tenant_id, ensure the assigned employee's tenant matches the Assignment's tenant using an appropriate composite FK structure.

## 7. Multi-Row or Multi-Table Rules

The following rules usually **cannot** be enforced by a simple local CHECK:

- “A CONFIRMED Order must have **at least one** OrderLine.”
- “An ACTIVE Customer must have **a verified phone number**.”
- “No two bookings for **the same room** may have overlapping time intervals.”
- “The sum of allocations must equal the approved total.”
- “An assigned employee must belong to an authorized processing group.”

### 7.1. “At Least One Child Row” Is Not Automatically Protected by an FK

The foreign key **OrderLine → Order** guarantees every line has an existing order, not that **Order → has existing OrderLines**.

Diagnostic query:

~~~sql
SELECT o.order_id
FROM sales_orders AS o
WHERE o.status = 'CONFIRMED'
  AND NOT EXISTS (
      SELECT 1
      FROM order_lines AS l
      WHERE l.order_id = o.order_id
  );
~~~

In a compliant system, this query should return zero rows. However, it is a **monitoring query**, not an automatic constraint preventing invalid states.

Protection options:

1. **Design a state-transition workflow** from DRAFT to CONFIRMED inside a transaction, after confirming lines exist.
2. **Use appropriate triggers / constraint triggers** checking line inserts/updates/deletes and status transitions, considering end-of-transaction checks.
3. **Restructure the schema** if there is a way to express the mandatory condition on the same row or via another entity.
4. **Control all writers and concurrent updates**, preventing one transaction from confirming an order right as another deletes its last line.

If the application merely checks “at least one line exists” before updating status while another API allows deleting the last line without lock coordination, both operations can succeed and leave a CONFIRMED Order with zero lines. A plain SELECT does not protect invariants under concurrency.

### 7.2. Atomicity During State Transitions

An order confirmation workflow might begin with:

~~~sql
BEGIN;

-- Lock the Order, provided OrderLine modifications
-- also follow the protocol of locking this same Order.
SELECT order_id, status
FROM sales_orders
WHERE order_id = 1001
FOR UPDATE;

-- Check that at least one line exists.
SELECT EXISTS (
    SELECT 1
    FROM order_lines
    WHERE order_id = 1001
) AS has_lines;

-- Application/procedure must abort and ROLLBACK if has_lines = FALSE
-- or the current status does not permit confirmation.
UPDATE sales_orders
SET status = 'CONFIRMED'
WHERE order_id = 1001 AND status = 'DRAFT';

COMMIT;
~~~

The snippet above is a **workflow outline**, not a guarantee of integrity from those isolated statements alone. The caller must check the results of SELECT EXISTS and UPDATE (exactly one row), and OrderLine add/delete/edit operations must lock/check status under the same protocol. For full database-level enforcement, implement appropriate procedures/constraints covering every write path.

### 7.3. Non-Overlapping Time Intervals

The rule “a room cannot have two overlapping bookings” spans **multiple rows**, not a single-row CHECK. PostgreSQL supports **exclusion constraints** for certain cases; alternatively, the application can coordinate locking and checks, rather than relying on an unsynchronized “SELECT no overlap, then INSERT” under concurrency.

Define intervals explicitly: half-open intervals **[start, end)** allow the next booking to start exactly when the previous one ends; if both endpoints are closed, the boundary can be treated as an overlap.

## 8. Transactions, Isolation, and Concurrent Updates

### 8.1. Atomic Updates Instead of Separate Read–Modify–Write

Suppose available stock is 1. Two users attempt to buy 1 unit simultaneously. If each request runs:

1. SELECT available_quantity;
2. sees 1;
3. UPDATE available_quantity = 0;

then both may believe they succeeded in reserving stock, even though only one unit existed.

A safer approach uses a **conditional UPDATE on the same row**:

~~~sql
UPDATE stock_balances
SET available_quantity = available_quantity - 1,
    reserved_quantity = reserved_quantity + 1
WHERE product_id = 501
  AND available_quantity >= 1
RETURNING available_quantity, reserved_quantity;
~~~

If stock is insufficient, UPDATE returns **0 rows**. The transaction succeeds in reserving stock only when one row is updated. PostgreSQL locks the row during UPDATE and evaluates the predicate under its isolation level; operating on **the same row** avoids many read–modify–write races.

This still must be combined with the Order/Reservation transaction and rules for rollback, idempotency, order cancellation, and restocking. It does not automatically solve multi-product or multi-warehouse invariants.

### 8.2. Optimistic Concurrency Control

When multiple users can edit a configuration record, use a **version column** to prevent overwriting someone else's update:

~~~sql
CREATE TABLE product_descriptions (
    product_id BIGINT PRIMARY KEY
        REFERENCES products(product_id) ON DELETE RESTRICT,
    description TEXT NOT NULL,
    version_no INTEGER NOT NULL DEFAULT 1
               CHECK (version_no > 0)
);

-- Client previously read version_no = 3:
UPDATE product_descriptions
SET description = 'Updated description content',
    version_no = version_no + 1
WHERE product_id = 501
  AND version_no = 3
RETURNING version_no;
~~~

If UPDATE returns 0 rows, the record was either modified by someone else or does not exist. The application must re-read, resolve conflicts, or prompt the user—never silently overwrite.

**Versioning** detects single-row conflicts, yet does not replace FKs, CHECKs, or locks needed for multi-row invariants.

### 8.3. SERIALIZABLE and Retries

For multi-row rules, **SERIALIZABLE** isolation can detect non-serializable schedules. In PostgreSQL, a transaction may abort with a serialization error, so the application must **retry the entire transaction** from the beginning with a bounded strategy.

Do not claim “using a transaction eliminates all race conditions”: a transaction at default isolation can still experience read–write concurrency anomalies. Combine **constraint structure**, **isolation level**, **appropriate locking**, **check timing**, and **retries**.

### 8.4. Deadlocks and Lock Ordering

Two transactions modifying multiple tables in opposite orders can deadlock—for example, T1 locks Order then Stock, while T2 locks Stock then Order. The database detects deadlocks and aborts one transaction, yet systems should minimize risk by:

- Establishing a consistent **lock ordering** when updating related entities.
- Keeping transactions short and avoiding external service calls while holding locks.
- Locking at the **exact business scope** rather than overly broad locks.
- Handling deadlock/serialization errors with safe retries and idempotency for external side effects.

## 9. Hard Delete, Soft Delete, Archiving, and History

A DELETE statement is not always the right action for “the user should no longer see this record”.

| Action | Physical Row | FK Relationship | Typical Use Case |
| --- | --- | --- | --- |
| **Hard delete** | Removed from table | FKs apply declared actions | Temporary data, expired data allowed to be purged |
| **Soft delete** | Retained with deleted_at/status | FKs still see row as existing | Deactivated accounts, recoverable when needed |
| **Archive** | Retained, barred from new operations | FKs usually remain valid | Previously sold products, expired contracts |
| **Anonymize / pseudonymize** | Keeps transaction record while scrubbing identifiers per policy | Must keep referential identifiers consistent | Retaining documents while minimizing personal data |
| **Version / history** | Stores multiple versions or change events | FKs can point to versions or snapshots | Audits, point-in-time reporting |

### 9.1. Soft Delete Does Not Trigger ON DELETE

Example:

~~~sql
ALTER TABLE products
ADD COLUMN deletion_requested_at TIMESTAMPTZ;

UPDATE products
SET deletion_requested_at = CURRENT_TIMESTAMP
WHERE product_id = 501;
~~~

This is an UPDATE, not a DELETE. FK actions ON DELETE CASCADE, SET NULL, or RESTRICT **do not fire** just because this column is set. Queries must filter active objects properly, and new references to removed products must be blocked.

To allow product names to be reused after soft deletion, you can design a **partial unique index** over active records. Still, define policies for duplicate names/SKUs, undelete restoration, and compatibility with foreign keys.

**PostgreSQL Note:** a partial unique index cannot always serve as an FK target; standard FKs must reference a primary key or suitable UNIQUE constraint, not merely a conditional subset of rows. You cannot assume a plain FK automatically enforces “only ACTIVE Products may be referenced”.

### 9.2. Delete Rules Are Not Access Permissions

When a Customer closes their account, you may need to:

1. Block placing new orders.
2. Revoke login sessions and operational permissions.
3. Retain past Orders per retention policy.
4. Handle contact and personal identity data per applicable regulations.
5. Record who requested, who approved, and when the task completed.

This is a **multi-step business workflow**, which should not be replaced by an ON DELETE CASCADE from Customer down through all tables. Conversely, never retain all personal data indefinitely just because ON DELETE RESTRICT is set; the design must satisfy both privacy rules and valid retention periods.

### 9.3. Addresses and Unit Prices Must Preserve History

If a Customer changes their address and a Product changes its price, past Orders must still show **the actual shipping address** and **the locked-in unit price**. Two common solutions:

- **Snapshot:** copy the business fields to preserve into Order/OrderLine at checkout time.
- **Versioned reference:** reference an immutable version of the address/price effective at that time.

Do not place ON UPDATE CASCADE on a relationship where a parent change would effectively **rewrite historical truth** on child rows. ON UPDATE CASCADE is for **updating a referenced key**, not synchronizing historical business facts.

## 10. Indexes and the Cost of Update/Delete Behaviors

Constraints and indexes aid reads, yet also incur write costs.

### 10.1. Indexes on the Foreign Key Side

In PostgreSQL, creating an FK **does not automatically create an index** on the child table's FK column. When deleting or updating a parent key, the DBMS may need to locate referencing child rows; lacking an index can make that check very expensive.

~~~sql
CREATE INDEX idx_sales_orders_customer
ON sales_orders (customer_id);

CREATE INDEX idx_order_lines_product
ON order_lines (product_id);

CREATE INDEX idx_shopping_carts_customer
ON shopping_carts (customer_id);
~~~

For **order_lines**, the primary key **(order_id, line_no)** already creates an index leading with **order_id**, so a separate single-column index just to filter OrderLines by order_id is usually unnecessary. Meanwhile, product_id does not lead the composite primary key, so a separate index helps when looking up which lines used a product.

Choose indexes based on **actual queries, row counts, update frequency, and EXPLAIN plans**. Do not create redundant indexes simply because every FK looks like a candidate.

### 10.2. ON DELETE CASCADE Can Generate Heavy Write Volume

If a parent row has very many children, deleting one parent row can trigger large numbers of DELETEs across multiple tables, firing triggers, generating WAL/logs, and holding locks. Evaluate this amplification before allowing deletion from an ordinary API request.

For large datasets, you may need batched deletion jobs, pending-delete statuses, load throttling, and audit trails. Ensure no invalid intermediate state is left visible between batches; deleting across multiple separate transactions does not share the atomic semantics of a single CASCADE statement.

### 10.3. ON UPDATE CASCADE on Widely Referenced Keys

Changing a parent key referenced by huge numbers of child rows causes massive updates, long locks, and heavy logging. Restrict mutating identifiers or prefer immutable surrogate keys when business rules allow. When a meaningful key genuinely must change, estimate affected row counts and plan the rollout carefully.

## 11. Auditing and Post-Update Verification

Systems should pair constraints with **reconciliation queries**. Monitoring queries do not replace constraints, yet help detect bad data from legacy imports, migrations, or special write paths.

### 11.1. Checking for Orphan Child Records

Once valid FKs are enabled, no Order should point to a nonexistent Customer. This query remains useful when auditing data before enabling an FK:

~~~sql
SELECT o.order_id, o.customer_id
FROM sales_orders AS o
LEFT JOIN customers AS c ON c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

In models where customer_id is nullable, separate “no parent because optional” from “broken orphan reference”: add **o.customer_id IS NOT NULL** when hunting strictly for broken FKs.

### 11.2. Auditing Retired Records That Still Have Links

~~~sql
SELECT p.product_id, p.sku, COUNT(l.order_id) AS historical_line_count
FROM products AS p
LEFT JOIN order_lines AS l ON l.product_id = p.product_id
WHERE p.archived_at IS NOT NULL
GROUP BY p.product_id, p.sku
ORDER BY p.product_id;
~~~

Having historical OrderLines referencing an archived product **is not an error**. However, a new OrderLine created after the archive timestamp may violate “do not sell discontinued products”; concluding whether it is a violation requires line/order creation timestamps and explicit validity policies.

### 11.3. Distinguishing Integrity Errors from Valid State Transitions

Document in the model specification:

- Which state transitions are allowed: DRAFT → CONFIRMED, CONFIRMED → CANCELLED?
- Who is authorized to perform them, and when?
- Which dependent rows must exist, must not exist, or must remain intact during transitions?
- Does cancellation “restore inventory”, “issue a refund entry”, or merely change status?
- Must event history be preserved and direct UPDATEs on finalized fields blocked?

Some rules should not be stuffed into CHECK constraints if they depend on **prior values** or **external systems**. Triggers, stored procedures, application workflows, and event logs can complement one another, provided there is a clear source of truth and verifiability.

## 12. Designing and Migrating Constraints on Existing Data

When a database already holds data, adding constraints requires planning rather than arbitrary ALTER TABLE statements.

### 12.1. Safe Workflow

1. **Define invariants** from business rules, including exceptions and historical states.
2. **Profile existing data:** NULL values, orphan FKs, duplicate keys, invalid statuses, parentless child rows.
3. **Clean or classify anomalous data:** fix from authoritative data sources, never invent dummy values arbitrarily.
4. **Choose delete/update actions:** RESTRICT, NO ACTION, CASCADE, SET NULL, or SET DEFAULT per relationship.
5. **Create indexes and constraints** using strategies that minimize lock duration if supported by the DBMS.
6. **Ensure all writers are updated:** applications, import scripts, background jobs, external integrations.
7. **Test in a representative environment:** large data volume, concurrent transactions, rollbacks, deadlocks, and failed migrations.
8. **Monitor post-deployment:** constraint errors, reconciliation queries, archived record counts, and bulk delete operations.

### 12.2. PostgreSQL: NOT VALID and VALIDATE CONSTRAINT

For certain constraints like FKs and CHECKs, PostgreSQL supports adding the constraint as **NOT VALID** to avoid scanning all existing rows immediately, while still enforcing the constraint on all new writes:

~~~sql
-- Illustrative example on an existing table containing customer_id.
ALTER TABLE legacy_orders
ADD CONSTRAINT fk_legacy_order_customer
FOREIGN KEY (customer_id)
REFERENCES customers(customer_id)
NOT VALID;

-- Once legacy data has been audited/cleaned:
ALTER TABLE legacy_orders
VALIDATE CONSTRAINT fk_legacy_order_customer;
~~~

This example assumes **legacy_orders** already exists with matching column types. Locking behavior during creation and validation also depends on PostgreSQL version, row count, indexes, and concurrent traffic; test in a realistic environment. Never generalize that **every constraint type** supports NOT VALID.

### 12.3. Switching from CASCADE to RESTRICT

Changing an active FK policy requires verifying not only syntax but also application impact:

- Legacy delete flows relying on CASCADE may start failing.
- Child data that previously vanished automatically will now be retained, changing storage growth and query results.
- Cleanup jobs may need to switch to status/retention-date management.
- Measure delete latency, lock timeouts, and user-facing error handling.

Conversely, switching from RESTRICT to CASCADE can be a **destructive data change** and must be evaluated as a major business decision, not just an operational tweak.

## 13. Relation to Document, Graph, and Analytical Models

Integrity rules are **business semantics**. Choosing a different technology only changes the enforcement mechanism.

| Storage Model | Relationship Representation | Update / Delete | What to Verify |
| --- | --- | --- | --- |
| **Relational DB** | PK/FK, parent–child tables, junction tables | ON DELETE/UPDATE and transactions | Domains, cross-row constraints, concurrency |
| **Document** | Embedded child data or referenced IDs | Document updates/deletes, reference sync jobs | Schemas, orphan elements, multi-document updates, history |
| **Graph** | Typed nodes and relationships | Node/edge deletion per DB and app rules | Valid edge types, orphan nodes, cycles, multiplicity, and time |
| **Analytical Warehouse** | Facts, dimensions, bridges, versions | Incremental loads, handling source updates/deletes | Historical accuracy, data grain, duplicate-free aggregation |

### 13.1. Document: Embedding vs. Referencing Determines Lifecycle

A **shopping cart** document can embed cart items because they are typically read, edited, and deleted together:

~~~json
{
  "cartId": 701,
  "customerId": 101,
  "items": [
    {"productId": 501, "quantity": 1}
  ]
}
~~~

Deleting the cart document naturally removes its embedded items—akin to **composition** or ON DELETE CASCADE in an RDBMS.

Conversely, if an Order document stores only a customerId referencing an independent Customer document, deleting the Customer can leave Orders pointing to a nonexistent Customer if the database lacks cross-document FKs. The system must pick deletion rules, snapshots/versions, multi-document transactions if available, and application-level reference checks. Never assume “a document database auto-CASCADEs like an FK” when storing only an ID.

### 13.2. Graph: Relationships and Node Deletion

A Customer node can connect to Order nodes via PLACED edges. Deleting a Customer requires deciding whether edges are deleted, whether Orders remain, or whether Orders transfer to an archival account. Graph DBMSs vary in technical rules for deleting nodes with remaining edges, yet **cannot replace document retention policies**.

Edges can carry validity periods, relationship types, and their own properties; protect cardinality, cycles in hierarchies, node statuses, and write permissions.

### 13.3. Warehouse: Source Updates Do Not Mean Rewriting History

When a Customer changes name or moves region, reports may want:

- **Type 1:** overwrite the current dimension attribute, reinterpreting history under the new value.
- **Type 2:** create a new dimension version, preserving attributes as of transaction time.

These two options reflect different analytical requirements. When a Product is discontinued or soft-deleted in the source system, never delete historical revenue facts simply because the dimension changed status.

A CASCADE delete in the transactional system can create trouble for the analytical warehouse if source records vanish unrecoverably. Design retention policies, CDC, tombstones, and scoped delete handling appropriately.

## 14. Test Matrix for Update and Delete Behaviors

Do not test only **valid INSERTs**. Test operations that mutate data in multiple ways:

| Scenario | Example Expectation | Mechanism to Verify |
| --- | --- | --- |
| Create Order with nonexistent customer_id | Rejected | FK |
| Create OrderLine with quantity = 0 | Rejected | CHECK + NOT NULL |
| Delete Customer with existing Orders | Rejected | ON DELETE RESTRICT |
| Delete temporary cart with cart items | Deletes cart and its items | ON DELETE CASCADE |
| Delete Product present in OrderLine | Rejected | Product FK |
| Archive Product that still has old orders | Archiving allowed; history remains readable | Status UPDATE, business queries |
| Add new OrderLine for archived Product | Rejected by policy (not yet in illustrative DDL) | Business logic / trigger |
| Delete last OrderLine of a CONFIRMED Order | Rejected by policy (not yet in illustrative DDL) | Cross-row / status check |
| Rename Department code that has employees | Updates employee FKs | ON UPDATE CASCADE |
| Delete Department in optional-link model | Employees retained with department_code NULL | ON DELETE SET NULL |
| Two transactions concurrently claim the last stock unit | Only one transaction succeeds | Conditional UPDATE, row locking |
| Two sessions concurrently edit old description | Second session detects conflict | Version / optimistic concurrency |
| Switch primary phone number | Never two primary numbers; never accidentally lose mandatory primary | Partial UNIQUE, transaction, and row checks |
| Delete data while history retention applies | Archive/anonymize workflow instead of blanket delete | Data policy and audit |

Items marked “not yet in illustrative DDL” must **not** be assumed blocked by the database today. They are design gaps to close with appropriate mechanisms before production launch.

### Additional Test Criteria

- When a deletion is rejected, do steps in **the same transaction** roll back cleanly?
- When deleting across multiple tables, are records outside the authorized scope protected from accidental loss?
- When constraints are deferred, are errors surfaced at **COMMIT** handled safely?
- When two transactions update the same object, are conflicts, deadlocks, or serialization failures detected properly?
- When writes come from imports/jobs bypassing the API, how much protection do DB constraints still provide?
- Can data from tenant A accidentally reference tenant B?
- Can soft-deleted data be restored without colliding with UNIQUE constraints of newer records?
- Do historical records still accurately reflect address, unit price, and status at transaction time?

## 15. Common Mistakes

| Mistake | Why It Is Wrong | Better Approach |
| --- | --- | --- |
| Using CASCADE on every FK | Can wipe out accounting documents and history | Choose per entity lifecycle |
| Assuming RESTRICT and NO ACTION are always identical | Check timing differs when constraints are deferred | Match transaction and DBMS requirements |
| Choosing SET NULL on a NOT NULL FK | Causes NOT NULL failure on delete | Use only for optional links or redesign |
| Assuming SET DEFAULT always succeeds | Default value must still satisfy the FK | Ensure the default parent truly exists |
| Treating FK as checking all business conditions | FKs ignore ACTIVE status, permissions, or effective dates | Add business checks and write gates |
| Writing CHECK without NOT NULL | CHECK can accept UNKNOWN | Separate mandatory rules from domain comparisons |
| Assuming UNIQUE means a child row always exists | UNIQUE only caps maximum / duplicates | Enforce minimum-count conditions separately |
| Checking then INSERT/DELETE in two unsynchronized steps | Suffers from race conditions | Use transactions, locks, and proper constraints |
| Soft-deleting and expecting ON DELETE to fire | Soft delete is an UPDATE | Write explicit status-aware logic |
| Updating current attributes and expecting historical reports to stay accurate | History gets reinterpreted inaccurately | Snapshots or versioning per business rules |
| Ignoring indexes on child FK columns | Parent delete/update checks can scan full tables | Create indexes based on workload and EXPLAIN |
| Using DELETE to represent canceling a transaction | Loses audit trail and linked data | Use status transitions or adjustment entries |

## 16. Scenario Exercises with Solution Hints

### Exercise 1. Deleting Orders vs. Shopping Carts

**Problem:** A Customer has a temporary shopping cart and paid Orders. When the Customer requests account closure, the dev team wants to set ON DELETE CASCADE from Customer to every table.

**Solution Hint:** Temporary carts can fit CASCADE if policy permits purging them. Paid Orders and OrderLines usually require historical retention; never CASCADE-delete accounting documents. Distinguish **account closure/access revocation** from **physical deletion**, and design personal-data handling per valid retention policies.

### Exercise 2. Updating a Department Code

**Problem:** A Department has code ENG referenced by Employees. The business renames the code to DEV while keeping the same department identity. Which FK action helps?

**Solution Hint:** **ON UPDATE CASCADE** updates the foreign key values in sync. However, if department codes change frequently, an immutable **department_id** as PK with a UNIQUE code is usually more convenient and avoids cascading FK updates on code changes.

### Exercise 3. Failed SET NULL Operation

**Problem:** Table Task has assignee_id NOT NULL and an ON DELETE SET NULL FK to Employee. Will deleting an Employee currently assigned to a Task succeed?

**Solution Hint:** No, because SET NULL conflicts with NOT NULL. You must **RESTRICT** Employee deletion, reassign Tasks before deleting, or allow unassigned Tasks if business rules permit.

### Exercise 4. At Most One vs. Exactly One

**Problem:** A Customer can have multiple emails but is required to have **exactly one primary email** while ACTIVE. Is adding UNIQUE(customer_id) WHERE is_primary sufficient?

**Solution Hint:** Not sufficient. That index enforces **at most one**. You must also enforce **at least one** primary email in ACTIVE state, including during email deletions/switches or concurrent transactions. Cross-row workflows and checking mechanisms are needed.

### Exercise 5. Inventory Under Concurrency

**Problem:** One unit remains in stock; two requests both read available = 1 and attempt to purchase. Why is SELECT followed by UPDATE insufficient?

**Solution Hint:** Both requests can act on stale read data. A **conditional UPDATE** (`available >= 1`) on the same row, checking the updated row count, directly ensures only one request reserves the unit. Execute it within the same transaction as related order/stock changes.

### Exercise 6. Historical Address

**Problem:** Order 1001 shipped to address A. The Customer later edits their current address to B. If Order only references the Customer's current address, what might last year's shipping report display?

**Solution Hint:** It may historically misdisplay B. Order needs a shipping snapshot or a reference to an immutable address version used at order/shipment time.

### Exercise 7. Legacy Data Import and Adding FKs

**Problem:** Table `legacy_orders` has several `customer_id` values not present in `customers`. Should you delete all orphan Orders and then add the FK?

**Solution Hint:** Not automatically. Trace sources, classify per policy, decide whether to repair references, restore missing Customers, flag exceptions, or handle invalid records per requirements. PostgreSQL can add the FK as NOT VALID, clean legacy data, and VALIDATE later, while immediately protecting new writes.

### Exercise 8. Multi-Step Updates and NO ACTION

**Problem:** A transaction needs to temporarily replace a parent row and then restore valid references before COMMIT. Why might NO ACTION DEFERRABLE fit better than RESTRICT?

**Solution Hint:** When set to DEFERRED, NO ACTION checks at transaction commit and permits temporary intermediate states that violate the FK. RESTRICT cannot defer its restriction check in PostgreSQL. The final state at commit must still be valid; handling errors at COMMIT is mandatory.

## 17. Key Takeaways

**Update and delete behaviors are part of the data model, not just FOREIGN KEY syntax options.** For every relationship, clearly answer: can child rows exist independently, must history be preserved, can parent keys change, does deletion mean physical removal or status change, and could concurrent transactions break invariants?

- **RESTRICT/NO ACTION** protect referential existence with different check-timing semantics.
- **CASCADE** propagates changes; appropriate for confirmed lifecycle-dependent components, risky for accounting documents.
- **SET NULL/SET DEFAULT** alter links, valid only when new values conform to the model and policy.
- **PK, FK, UNIQUE, NOT NULL, CHECK** address different integrity layers; no single constraint type replaces all business rules.
- **Transactions, locks, isolation, and retry strategies** must be weighed when protecting multi-row rules or concurrent updates.
- **Snapshots, statuses, history, and retention windows** must be designed from the start so updates/deletes never erase historical meaning.

A solid schema allows updates when needed, **blocks invalid changes at the exact right boundary**, and preserves integrity across relational, document, graph, and analytical data as the system grows.
