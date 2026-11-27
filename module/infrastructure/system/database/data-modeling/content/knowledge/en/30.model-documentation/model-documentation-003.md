# Defining Keys, Relationships, Cardinality, and Lifecycle Behavior

An entity–relationship diagram can show **Customer connected to Order**, **Order connected to OrderLine**, and **OrderLine connected to Product**. Yet looking only at connector lines is not enough for the engineering team to implement it correctly:

- How many orders can a customer place? Can an order **have no customer** during an in-store purchase?
- Is a draft order allowed to have no order lines yet? Can a confirmed order have its last line deleted?
- Can a Product appear in multiple OrderLines? If a Product is renamed or discontinued, how must historical sales lines be handled?
- Is an Order code unique only **within a tenant** or across the entire system? Can customer codes be reused?
- When deleting a Customer, are Orders deleted along with it, blocked, or retained with anonymized information? Is every "delete" a physical DELETE?

If documentation merely states "Customer 1–N Order" without explaining **keys, identifier scope, minimum/maximum cardinality, optionality, effective timing, and lifecycle behavior**, each implementation team will guess differently. The result can be a syntactically valid database that violates sales rules, ownership boundaries, or accounting history.

This lesson belongs to the **Model Documentation** chapter in the **DATABASE_DATA_MODELING** module. Its goal is to teach how to write a **data model contract** clear enough to translate business requirements into PK/FK/UNIQUE/CHECK constraints, relationship design, update–delete–history rules, and verification tests. The examples use PostgreSQL while also showing how those semantics are expressed in document, graph, and analytical models.

> **Principle:** Every relationship line must read as **a business sentence with subject and predicate**, accompanied by **cardinality on both sides**, key scope, write rules, and behavior when objects change or end their lifecycle. An ERD is only one projection of the contract, not the entire contract.

## 1. What Does Model Documentation Document?

A data model typically distinguishes three layers:

| Layer | Question | Example to Document |
| --- | --- | --- |
| **Conceptual** | Which entities and relationships exist in the business? | Customer places Order; Order contains Lines |
| **Logical** | What identifies entities, and which cardinalities and rules must hold? | A Line belongs to exactly one Order; a CONFIRMED Order must have at least one Line |
| **Physical** | How does the DBMS store and enforce them via keys, indexes, columns, and transactions? | PK(tenant_id,order_id,line_no), composite FK, CHECK, confirmation procedure |

**The same rule** can appear at all three layers with varying detail. For example:

- Conceptual: "An Order consists of order lines."
- Logical: "A DRAFT Order has 0..N Lines; a CONFIRMED Order has 1..N Lines; a Line belongs to exactly one Order and cannot move to another Order after creation."
- Physical: `order_lines` has FK (tenant_id,order_id), key (tenant_id,order_id,line_no), and the state-transition procedure checks Line existence inside a transaction; every delete/update path on Line must coordinate through the same owner.

With FK alone, you **cannot** conclude that an Order always has a Line. The FK enforces the **Line → Order** direction; it does not force the reverse direction to have elements.

### 1.1. What Fields Does a Complete Relationship Contract Need?

| Component | Question to Answer |
| --- | --- |
| **Name and meaning** | Does the relationship mean "Customer places Order" or "Customer receives Order"? |
| **Roles at both ends** | Who is the owner, referrer, participant, or referent? |
| **Identifiers** | Primary key, business key, reference key; unique within what scope? |
| **Min/max cardinality** | Does each side have 0, 1, or many related objects? |
| **Optionality** | Mandatory at creation or only after a state/milestone? |
| **Lifecycle** | When is it created, linked, unlinked, updated, archived, hidden, or deleted? |
| **Constraints** | What can the DBMS enforce versus what must the owner/transaction control? |
| **Time** | Is the relationship current-only or effective-dated with valid_from/valid_to? |
| **Scope and permissions** | Tenant, service owner, shard, security, and access rules? |
| **Exceptions** | How are guest checkout, late data, soft delete, and missing references handled? |
| **Verification** | Which SQL query/test proves the rule within the chosen scope? |

Documentation that only lists column names and SQL types is a **bare-bones data dictionary**; it does not yet fully describe relationships and lifecycles.

## 2. From Requirements to Keys: Distinguishing Key Types

### 2.1. Candidate Key, Primary Key, and Alternate Key

A **candidate key** is a minimal set of attributes that uniquely distinguishes a row per business rules within a **defined identity scope**.

For example, an Order in a SaaS system may have:

- **Business key:** (tenant_id, order_code), where `order_code` is displayed to customers.
- **Technical key:** (tenant_id, order_id), where `order_id` is system-assigned.
- **Primary key:** one key chosen as the row identifier in the database.
- **Alternate key:** another remaining candidate key protected by UNIQUE where appropriate.

Do not assume `order_code` is globally unique just because current sample data shows no collisions. If two tenants are allowed to issue code O-001, uniqueness must be **scoped to tenant**.

As another example, a Product with SKU P-101 may change codes due to reclassification while `product_id` remains unchanged. Here, SKU is a **business code with a code-change policy**, while `product_id` can serve as the entity's stable identifier. Reusing SKUs requires a separate policy.

### 2.2. Composite Keys Reflect Scope

~~~text
Order identity:
  (tenant_id, order_id)

Order business code:
  UNIQUE (tenant_id, order_code)

Line identity:
  (tenant_id, order_id, line_no)

Product identity:
  (tenant_id, product_id)
~~~

**line_no = 1** has no unique meaning outside an Order. **order_id = 1001** must not be assumed unique outside a tenant unless the system explicitly guarantees it. Composite keys allow documentation to express scope accurately and enable FKs to guard tenant boundaries.

When multiple tables use composite keys, explicitly document **column order**, the meaning of each component, and the rationale. Do not create an FK on `customer_id` alone if Customer is identified by `(tenant_id, customer_id)`.

### 2.3. Identifying Keys Differ from Display Keys

Some fields are suitable for display or search but should not serve as PKs:

- Customer name, product name, or address: can collide and change.
- Email: requires decisions on case normalization, sharing, changes, or deletion.
- Phone number: can change owners and be recycled.
- `created_at` timestamps: multiple records can share the same timestamp.
- Content hash: identical content does not guarantee the same entity; editing content changes the hash.

Even if choosing a surrogate key, you still need to guard **real business-key invariants** using UNIQUE, registries, or appropriate checks; a surrogate PK does not prevent creating two Customers for the same business identity.

### 2.4. NULL and UNIQUE Must Not Be Described Ambiguously

In PostgreSQL, a standard UNIQUE constraint can allow multiple rows with NULL values in a key column under default NULL handling. Therefore:

~~~text
UNIQUE(tenant_id, external_reference)
~~~

does not mean "every Order must have a reference," nor does it automatically handle blank references, whitespace, or uppercase/lowercase normalization.

Documentation must explicitly state:

1. Can the attribute be NULL? Does NULL mean **unknown**, **not applicable**, or **not yet assigned**?
2. Must identity remain unique when the attribute is NULL?
3. Under text normalization, when are two codes equivalent?
4. Can codes be changed, moved across tenants, or reused after soft deletion?
5. Can two source systems issue identical codes? Does the key need `source_system`?

**Do not use NULL as a default catch-all for unanalyzed cases.**

## 3. Defining Relationships via Business Sentences and Roles

A connector line is more than a name like "FK_Customer." Write sentences from **both sides**.

Examples:

- "Each Order is placed by **exactly one registered Customer**."
- "A Customer may place **zero or many Orders**."
- "Each OrderLine belongs to **exactly one Order**."
- "A DRAFT Order may have **0 or many OrderLines**."
- "A CONFIRMED Order must have **at least one OrderLine**."
- "Each OrderLine references **exactly one Product in the same tenant**."
- "A Product may appear in **zero or many OrderLines**."

These sentences already contain the **cardinality**, **optionality**, and **scope** needed to design keys. However, they still lack behavior when deleting Customer, Product, or Order, or when transitioning Order state.

### 3.1. Reading Cardinality in min..max Notation

Write on each end of the relationship:

| Notation | Meaning |
| --- | --- |
| **0..1** | Zero or at most one |
| **1..1** | Mandatory, exactly one |
| **0..N** | Zero or many |
| **1..N** | At least one, unbounded above in the logical model |
| **m..n** | At least m, at most n; requires dedicated business constraint |

Example **Customer — Order**:

~~~text
From the perspective of an Order:
  number of referenced Customers = 1..1

From the perspective of a Customer:
  number of Orders placed by Customer = 0..N
~~~

For **Order — OrderLine**, cardinality depends on state:

~~~text
Line -> Order:                1..1 in all valid states
Order DRAFT -> Line:          0..N
Order CONFIRMED -> Line:      1..N
~~~

Cardinality changing **by state** cannot be fully expressed by a static ERD line. Textual annotations and state transition rules are required.

### 3.2. Relationships and FK Columns Are Not the Same Concept

The relationship "Order belongs to Customer" may be implemented via `customer_id` in Orders. However:

- An FK may point to a **surrogate key** rather than a business code.
- A relationship can have **its own attributes** such as `effective_from`, `role`, `allocation_weight`.
- A relationship can be stored via a **junction table**, document nesting, or a graph edge.
- An FK only checks referential existence within the DBMS's capabilities; it does not express all lifecycle semantics.

Document the **business predicate** first, then record the storage mechanism.

## 4. Documenting Cardinality on Both Sides and Participation Conditions

An illustrative relationship table for the Order domain:

| Relationship | A looking at B | B looking at A | Special Conditions |
| --- | --- | --- | --- |
| Customer places Order | Customer → Order: 0..N | Order → Customer: 1..1 | Order created for a registered Customer |
| Order contains Line | Order → Line: 0..N when DRAFT | Line → Order: 1..1 | CONFIRMED Order: 1..N |
| Product appears in Line | Product → Line: 0..N | Line → Product: 1..1 | Product may be inactive while historical Lines remain valid |
| Order has PaymentAttempt | Order → PaymentAttempt: 0..N | Attempt → Order: 1..1 | Multiple attempts; independent payment status |
| Order has Label | Order → Label: 0..N | Label → Order: 0..N | Requires associative link table |

**Mandatory participation** can carry two meanings:

- **Exists immediately at creation:** an Order created must have a Customer.
- **Exists upon reaching a state:** a DRAFT Order may lack Lines, yet cannot be confirmed without Lines.

Do not conflate the two and apply inappropriate NOT NULL/FK constraints. A static constraint can enforce that a Line belongs to an Order, whereas "a CONFIRMED Order must have a Line" requires cross-row and write-path control.

### 4.1. Illustrative ERD and Expressiveness Limits

~~~mermaid
erDiagram
    TENANT ||--o{ CUSTOMER : owns
    TENANT ||--o{ PRODUCT : owns
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--o{ ORDER_LINE : contains
    PRODUCT ||--o{ ORDER_LINE : appears_in
    SALES_ORDER ||--o{ PAYMENT_ATTEMPT : has
    SALES_ORDER ||--o{ ORDER_LABEL_LINK : tags
    ORDER_LABEL ||--o{ ORDER_LABEL_LINK : assigned
~~~

The diagram shows **structural** cardinality. It cannot fully express:

- The rule "CONFIRMED must have a Line."
- Codes/`order_id` unique only within a tenant.
- The rule preventing deletion of a Customer who has Orders.
- Inactive Products still retaining FKs from historical OrderLines.
- PaymentAttempt statuses and retry rules.
- Tenant isolation preventing one tenant from reading another tenant's data.

Those must live in the accompanying **dictionary documentation and invariant catalog**.

## 5. 1–1, 1–N, N–M, and Identifying Relationships

### 5.1. 1–1 Relationships

A User can have at most one separate Profile, and each Profile belongs to only one User. If the Profile may not yet exist, User looking at Profile is **0..1**, while Profile looking at User is **1..1**.

This can be implemented with a UNIQUE NOT NULL FK on Profile:

~~~sql
CREATE TABLE app_users (
    user_id BIGINT PRIMARY KEY
);

CREATE TABLE user_profiles (
    profile_id BIGINT PRIMARY KEY,
    user_id BIGINT NOT NULL UNIQUE
        REFERENCES app_users(user_id)
);
~~~

`UNIQUE(user_id)` prevents **one User from having two Profiles**, but does not force every User to have a Profile. If a Profile must truly coexist with every User, enforce atomic creation in the same transaction or consider merging the two objects; a one-way FK does not guarantee total participation on both sides.

### 5.2. 1–N Relationships

An Order has many Lines, while each Line belongs to exactly one Order. The FK resides on the **N** side (OrderLine). If Line has key `(order_id,line_no)`, it is an **identifying-dependent** entity: `line_no` has meaning only inside an Order.

Note that **weak identification (weak entity/identifying relationship)** is distinct from "cascade-delete children with parent." Even though Line's key depends on Order, the Order delete policy may be RESTRICT to preserve history; never apply CASCADE merely because Line is a weak entity.

### 5.3. N–M Relationships

An Order has many Labels; a Label applies to many Orders. Never store a string `"vip,urgent,fragile"` in one column and expect FK, uniqueness, and tagging timestamps to be enforced.

Typically create an **association table**:

~~~text
OrderLabelLink(
  tenant_id,
  order_id,
  label_id,
  applied_at,
  applied_by
)
~~~

The grain of each row may be **one label currently attached to an Order**. If history of multiple attach/detach events for the same label is needed, the grain must change to **one event or one effective interval**, with additional key columns.

### 5.4. Self-Referencing Relationships

An Employee has a Manager who is another Employee, or a Category has a ParentCategory. Example:

~~~sql
CREATE TABLE categories (
    tenant_id BIGINT NOT NULL,
    category_id BIGINT NOT NULL,
    parent_category_id BIGINT,
    category_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, category_id),
    FOREIGN KEY (tenant_id, parent_category_id)
        REFERENCES categories(tenant_id, category_id),
    CHECK (
        parent_category_id IS NULL
        OR parent_category_id <> category_id
    )
);
~~~

Semantics:

- A Category has **0..1 direct parent**.
- A Category has **0..N direct children**.
- Cannot be its own direct parent in one hop.

**CHECK parent_id <> category_id does not forbid multi-hop cycles** A → B → C → A. If the business requires an acyclic tree, validate the entire ancestor path inside a write mechanism with proper concurrency control. If multiple parents are allowed, the model must switch to a `CategoryEdge` link table with additional graph rules.

### 5.5. Role-Specific Relationships

An Order may have a **buyer**, a **recipient**, and an **approver**. All three might reference the same Person/Customer entity type, yet represent **distinct roles**:

~~~text
Order --placed_by--> Customer
Order --ship_to_contact--> Contact
Order --approved_by--> Employee
~~~

Do not use one generic `person_id` column to represent three different relationships. Documentation must state the role, cardinality, and when NULL is allowed for each relationship.

## 6. PostgreSQL DDL: A Sales Model with Clear Keys and Relationships

The following example is **one concrete logical model** to verify the statements above; it is not a verbatim prescription for every system. Assumptions:

1. **Every Order in this example is placed by a registered Customer**; if the business supports guest checkout, model it explicitly instead of casually dropping NOT NULL.
2. **`tenant_id`** is the identity scope. Child numeric keys may collide across different tenants.
3. **Product** can be discontinued (`is_active = FALSE`) but is not hard-deleted if it has appeared in historical Lines.
4. Order lines store **`unit_price_vnd` at Order creation**; never compute historical revenue using the Product's current price.
5. `PaymentAttempt` is **one payment attempt** with its own identity and lifecycle, not synonymous with the Order being paid.
6. The status column supports DRAFT, CONFIRMED, CANCELLED; transition rules are documented separately in the lifecycle section.

### 6.1. Tenant, Customer, and Product

~~~sql
-- PostgreSQL, run on a dedicated test database.
CREATE TABLE tenants (
    tenant_id BIGINT PRIMARY KEY,
    tenant_code TEXT NOT NULL UNIQUE
);

CREATE TABLE customers (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    customer_id BIGINT NOT NULL,
    customer_code TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    archived_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, customer_id),
    UNIQUE (tenant_id, customer_code)
);

CREATE TABLE products (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    product_id BIGINT NOT NULL,
    sku TEXT NOT NULL,
    product_name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (tenant_id, product_id),
    UNIQUE (tenant_id, sku)
);
~~~

**Documentation explanation:**

- A Customer belongs to **exactly one Tenant** and is identified by `(tenant_id,customer_id)`.
- A Product belongs to **exactly one Tenant** by illustrative convention; Products are not automatically shared across tenants.
- `archived_at` is an inactive state for Customer, **not row deletion**; FKs remain valid.
- `Product.is_active = FALSE` does not break references from older OrderLines.

If the business permits reusing SKUs after a Product is archived, `UNIQUE(tenant_id,sku)` must be adjusted per policy; never drop a constraint without evaluating impact on historical OrderLines and reconciliation.

### 6.2. Order and OrderLine

~~~sql
CREATE TABLE sales_orders (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    order_id BIGINT NOT NULL,
    order_code TEXT NOT NULL,
    customer_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT'
        CHECK (status IN ('DRAFT', 'CONFIRMED', 'CANCELLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMPTZ,
    cancelled_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, order_id),
    UNIQUE (tenant_id, order_code),
    FOREIGN KEY (tenant_id, customer_id)
        REFERENCES customers(tenant_id, customer_id)
        ON DELETE RESTRICT,
    CHECK (status <> 'CONFIRMED' OR confirmed_at IS NOT NULL),
    CHECK (status <> 'CANCELLED' OR cancelled_at IS NOT NULL)
);

CREATE TABLE order_lines (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd BIGINT NOT NULL
        CHECK (unit_price_vnd >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_orders(tenant_id, order_id)
        ON DELETE RESTRICT,
    FOREIGN KEY (tenant_id, product_id)
        REFERENCES products(tenant_id, product_id)
        ON DELETE RESTRICT
);
~~~

**What the DDL enforces:**

- An Order belongs to an existing Customer **within the same tenant**.
- A Line belongs to an existing Order **within the same tenant**.
- A Line references an existing Product within the same tenant.
- An Order cannot have two Lines with the same `line_no`; `line_no` can repeat across different Orders.
- `quantity > 0`, `unit_price_vnd >= 0`, `status` lies within the valid domain.
- Hard-deleting Customer or Product is blocked by FK RESTRICT while referenced.
- A CONFIRMED Order must have `confirmed_at`; CANCELLED must have `cancelled_at`.

**What the DDL does NOT yet enforce:**

- A CONFIRMED Order must have at least one Line.
- Only DRAFT → CONFIRMED/CANCELLED and CONFIRMED → CANCELLED transitions are allowed per policy.
- Disallowing price/line edits after confirmation.
- Preventing an archived Customer from placing new Orders.
- `Product.is_active = TRUE` when adding a new Line.
- Preventing `cancelled_at` from being populated nonsensically in other statuses, if the domain forbids it.
- Whether price/quantity/currency match promotions, taxes, and order totals.

These rules require a **write owner, procedure/transaction, trigger, or domain service** working alongside local constraints. Documentation must distinguish what is **enforced by the DBMS** from what is still **an intended business rule**.

### 6.3. PaymentAttempt and Labels

~~~sql
CREATE TABLE payment_attempts (
    tenant_id BIGINT NOT NULL,
    payment_attempt_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    provider_code TEXT NOT NULL,
    provider_attempt_ref TEXT NOT NULL,
    amount_vnd BIGINT NOT NULL CHECK (amount_vnd > 0),
    status TEXT NOT NULL CHECK (
        status IN ('INITIATED','AUTHORIZED','CAPTURED','FAILED')
    ),
    captured_at TIMESTAMPTZ,
    PRIMARY KEY (tenant_id, payment_attempt_id),
    UNIQUE (tenant_id, provider_code, provider_attempt_ref),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_orders(tenant_id, order_id)
        ON DELETE RESTRICT,
    CHECK (status <> 'CAPTURED' OR captured_at IS NOT NULL)
);

CREATE TABLE order_labels (
    tenant_id BIGINT NOT NULL REFERENCES tenants(tenant_id),
    label_id BIGINT NOT NULL,
    label_code TEXT NOT NULL,
    label_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, label_id),
    UNIQUE (tenant_id, label_code)
);

CREATE TABLE order_label_links (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    label_id BIGINT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, order_id, label_id),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_orders(tenant_id, order_id)
        ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, label_id)
        REFERENCES order_labels(tenant_id, label_id)
        ON DELETE RESTRICT
);
~~~

`PaymentAttempt` is a **business entity requiring history and reconciliation**, so it does not CASCADE on Order deletion. `OrderLabelLink` in this example represents **current auxiliary tags that can be re-applied**, so CASCADE can be used **if** hard-deleting an Order is actually allowed. In this model, an Order normally cannot be deleted once it has Lines/PaymentAttempts due to RESTRICT FKs; `ON DELETE CASCADE` on labels does not grant permission to bypass those constraints.

**If labels serve as an audit trail, do not use CASCADE:** change the lifecycle of `OrderLabelLink` to record attach/detach history with an appropriate deletion policy. `ON DELETE` behavior must never be chosen merely because it simplifies SQL statements.

### 6.4. Sample Verification Data

~~~sql
INSERT INTO tenants(tenant_id, tenant_code)
VALUES (1, 'SHOP-A'), (2, 'SHOP-B');

INSERT INTO customers
    (tenant_id, customer_id, customer_code, customer_name)
VALUES
    (1, 11, 'C-11', 'Customer A'),
    (2, 11, 'C-11', 'Customer B');

INSERT INTO products
    (tenant_id, product_id, sku, product_name)
VALUES
    (1, 101, 'SKU-101', 'Headphones'),
    (2, 101, 'SKU-101', 'Keyboard');

INSERT INTO sales_orders
    (tenant_id, order_id, order_code, customer_id, status)
VALUES
    (1, 1001, 'O-1001', 11, 'DRAFT');

INSERT INTO order_lines
    (tenant_id, order_id, line_no, product_id, quantity, unit_price_vnd)
VALUES (1, 1001, 1, 101, 2, 150000);

INSERT INTO order_labels
    (tenant_id, label_id, label_code, label_name)
VALUES (1, 5, 'PRIORITY', 'Priority');

INSERT INTO order_label_links(tenant_id, order_id, label_id)
VALUES (1, 1001, 5);
~~~

Two tenants can share the same `customer_id`, `product_id`, and SKU because they are **identified within a tenant**. An Order row in tenant 1 cannot reference a Customer that exists only in tenant 2 due to the composite FK.

**Note:** inserting a Customer in tenant 2 alone is not enough to test cross-tenant errors when Customer IDs overlap across both tenants; pick an ID absent from the target tenant, or verify business relationships beforehand. FK test examples are shown later.

## 7. Reading ON DELETE and ON UPDATE as Lifecycle Rules

FOREIGN KEY syntax can specify behavior when a parent record changes. It must reflect **business semantics**, not be picked by default just to minimize errors.

| Behavior | General Meaning | When Appropriate | Warning |
| --- | --- | --- | --- |
| **RESTRICT** | Blocks deleting/updating parent key while children reference it | Customer/Product with historical Orders | Requires an archive workflow instead of DELETE |
| **NO ACTION** | Rejects if constraint remains violated at check time | Preserves referential integrity, optionally deferrable | Not completely identical to RESTRICT under all deferral scenarios |
| **CASCADE** | Deletes/updates child keys following parent action | Auxiliary data whose lifecycle is wholly dependent | Can wipe out bulk data needed for audit |
| **SET NULL** | Clears link to NULL when parent is deleted | Optional relationship where NULL carries valid meaning | FK column must be nullable; must not erase source meaning |
| **SET DEFAULT** | Replaces FK value with default | Only when default points to an approved valid entity | Fake "Unknown" can mask business bugs |

In PostgreSQL, NO ACTION is the default FK action; in some cases checks can be deferred if the constraint is DEFERRABLE with an appropriate setup, whereas RESTRICT should not be assumed identical across all check timings.

### 7.1. Why Not CASCADE Customer → Order?

If deleting a Customer wiped out all Orders/PaymentAttempts, realized revenue could lose reconciliation trails. Documentation should state:

> "A Customer who has placed Orders must transition to ARCHIVED/ANONYMIZED per policy; never hard-delete while Orders/PaymentAttempts require retention. Historical Orders retain `customer_id` or switch to an approved pseudonym/retention model identifier."

Distinguish **erasing personal data** from **deleting entire transactions**. Retention or deletion depends on actual laws and policies; model documentation must specify the owner/workflow without assuming indefinite retention rights.

### 7.2. When Is CASCADE Valid?

A **draft shopping cart** and its CartLines only have meaning during the Cart's lifecycle. If it is agreed that "deleting a draft Cart deletes its CartLines" and CartLines hold no independently retained data, `ON DELETE CASCADE` can fit. Once the cart converts into an Order with transactions, Lines become sales history and **do not inherit** the Cart's deletion policy.

### 7.3. Can Parent Keys Be Edited?

If surrogate `customer_id` or `order_id` are designed as **immutable**, disallow PK updates; do not rely on `ON UPDATE CASCADE` to permit arbitrary identity mutations.

Changing the **display code** `customer_code` may be permitted while `id` stays fixed. If a business code is used as an FK, every code change ripples through many updates and affects history; consider a surrogate key paired with a UNIQUE business code.

### 7.4. Soft Delete Does Not Trigger ON DELETE

~~~sql
UPDATE customers
SET archived_at = CURRENT_TIMESTAMP
WHERE tenant_id = 1 AND customer_id = 11;
~~~

This is a **state UPDATE**, not a DELETE, so FK `ON DELETE` does not automatically handle related Orders. If the business rule says "no new Orders for an archived Customer," the write owner must check `archived_at` within the same consistency boundary.

Similarly, UNIQUE still counts archived Customers under the current constraint. To reuse `customer_code` after archiving, define a new uniqueness constraint scoped by state; however, assess whether historical references and reports can still distinguish identities.

## 8. Lifecycle Is More Than Deletion: Creation, State Transitions, and History Retention

Model documentation should describe at minimum these stages:

~~~text
Create -> Link -> Update -> Lock changes
    -> Confirm/close -> Archive/hide -> Delete per policy
~~~

**Each entity can have its own lifecycle.** A discontinued Product still persists for OrderLines; PaymentAttempt has independent history; a Label can be detached from an Order without deleting the Order.

### 8.1. Order State Machine

Example workflow:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> CONFIRMED : confirm
    DRAFT --> CANCELLED : cancel
    CONFIRMED --> CANCELLED : approved_cancel
    CONFIRMED --> [*] : archived_view
    CANCELLED --> [*] : archived_view
~~~

In the diagram, `archived_view` denotes "retired from active operations"; it is **not necessarily physical deletion**. An Order can be considered closed operationally yet remain stored per accounting policy.

Specify explicitly:

- **Preconditions for DRAFT → CONFIRMED:** at least one valid Line; Customer not archived; stock/payment policies satisfied.
- **Preconditions for CONFIRMED → CANCELLED:** cancellation permission, inventory reversal/release rules, supporting records, and history preservation.
- **What becomes immutable after CONFIRMED:** quantity/price/Line identity, or only specific fields? Defined by the domain.
- **Who can transition:** APIs, batch jobs, manual actions; all writers must pass through the same owner/transaction.
- **Idempotency:** re-sending confirm/cancel must not produce duplicate side effects.

**`CHECK(status IN (...))` only validates the value set**, not the DRAFT → CONFIRMED path or double-cancellation guards. Blocking illegal transitions is a **pre/post-state** constraint requiring an appropriate write mechanism.

### 8.2. Same Entity, Multiple Sub-Lifecycles

`PaymentAttempt` can have its own state sequence:

~~~text
INITIATED -> AUTHORIZED -> CAPTURED
          -> FAILED
~~~

The above is a simplified model; a provider may include VOIDED, EXPIRED, REFUNDED, or partial captures. Do not assume `PaymentAttempt CAPTURED` means the Order is delivered, or that a refund edits the same row. A refund may be **a new financial event** requiring a separate ledger/refund fact.

Documentation must separate **existence relationships** (Attempt belongs to Order) from **state-transition conditions** (what allows Order to become CONFIRMED).

## 9. Cross-Row Invariants Cannot Be Written with Simple CHECKs

In the illustrative schema, a CONFIRMED Order must have at least one Line. SQL to detect violating states:

~~~sql
SELECT o.tenant_id, o.order_id
FROM sales_orders AS o
WHERE o.status = 'CONFIRMED'
  AND NOT EXISTS (
      SELECT 1
      FROM order_lines AS l
      WHERE l.tenant_id = o.tenant_id
        AND l.order_id = o.order_id
  );
~~~

**This is a reconciliation query, not prevention.** A local CHECK on `sales_orders` cannot simply SELECT from `order_lines` and guarantee correctness when another writer deletes a Line concurrently.

### 9.1. Order Confirmation Protocol in a Single Database

A `ConfirmOrder` command can execute these steps within the **same transaction**:

~~~sql
BEGIN;

-- 1. Lock the Order to serialize all Line edits and state transitions.
SELECT status, customer_id
FROM sales_orders
WHERE tenant_id = 1 AND order_id = 1001
FOR UPDATE;

-- 2. Check business preconditions:
SELECT EXISTS (
    SELECT 1
    FROM order_lines
    WHERE tenant_id = 1 AND order_id = 1001
) AS has_line;

-- 3. ONLY WHEN status = DRAFT and has_line = true
--    along with other confirmed business conditions:
UPDATE sales_orders
SET status = 'CONFIRMED',
    confirmed_at = CURRENT_TIMESTAMP
WHERE tenant_id = 1
  AND order_id = 1001
  AND status = 'DRAFT'
RETURNING order_id, status;

-- 4. If row counts/conditions fail: ROLLBACK.
--    If all conditions pass: COMMIT.
COMMIT;
~~~

**Never execute straight through to COMMIT while ignoring the conditional branch in comments.** The application/procedure must verify results before committing.

More importantly, every API that **deletes or edits a Line** must also lock the **parent Order first** and check its status. If `ConfirmOrder` locks the parent but `DeleteLine` skips the same convention, `DeleteLine` can still break the invariant after the Order is CONFIRMED.

Implementation docs should state:

> "All mutations to `order_lines` and all transitions on `sales_orders` must go through the Order Owner. The Owner acquires a lock on the Order by `tenant_id + order_id`, checks status, and writes changes in the same transaction. No writer may bypass it."

### 9.2. What If Order and Line Live on Two Independent Shards?

A local PostgreSQL transaction does not become a cross-database transaction. Calling `GET /order-lines` from another service and then updating status in the Order DB does not guarantee the Line set stayed unchanged between check and COMMIT.

Options:

- Colocate Order and Line under the same shard key/owner.
- Use a true distributed transaction mechanism if supported and appropriate by the platform.
- Design a workflow with intermediate states/ownership that only publishes CONFIRMED once sufficient proof exists.
- Revise the invariant if the business permits, after approval.

Never write "eventual consistency" in documentation and assume a strict invariant is protected.

## 10. Relationship Attributes and Rules Also Have Lifecycles

An N–M relationship can carry metadata:

~~~text
OrderLabelLink:
  label_id, applied_at, applied_by, source_system
~~~

If storing only **current links**, primary key `(tenant_id,order_id,label_id)` enforces at most one active link per pair.

If the business needs to know **when a label was attached/detached**, a history table has a different grain:

~~~text
OrderLabelHistory:
  tenant_id
  order_id
  label_id
  valid_from
  valid_to
  reason
  event_id
~~~

Cardinality now varies by point in time: an Order may have carried the same Label multiple times across **non-overlapping intervals**, yet at any single instant have at most one active link if that is the rule.

### 10.1. Effective-Dated Relationship Model

~~~sql
CREATE TABLE order_label_history (
    tenant_id BIGINT NOT NULL,
    order_id BIGINT NOT NULL,
    label_id BIGINT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    reason TEXT,
    PRIMARY KEY (tenant_id, order_id, label_id, valid_from),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_orders(tenant_id, order_id),
    FOREIGN KEY (tenant_id, label_id)
        REFERENCES order_labels(tenant_id, label_id),
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);
~~~

A CHECK only prevents inverted intervals; it **does not prevent overlapping intervals** for the same `(tenant_id,order_id,label_id)`. If "at most one active LabelLink at any instant" is an invariant, you need an exclusion constraint, procedure/transaction, or DBMS-appropriate enforcement.

Use half-open intervals **`[valid_from,valid_to)`**: inclusive start, exclusive end. Adjacent intervals touching at a boundary are valid without overlapping.

### 10.2. Product Changes Must Not Rewrite OrderLine History

If a Product changes its name or list price, a confirmed OrderLine must preserve the **transaction price** and typically key attributes needed for point-of-sale documentation. An FK to Product only protects product identity; it does not ensure current `product_name` matches the name at sale time.

Depending on requirements:

- Store **`unit_price_vnd`**, discount/tax, and Product identifier on each Line.
- Also store snapshots of product name, SKU, and unit of measure when documents must be immutable.
- Use SCD Type 2 and Product version keys to retrieve historical classifications.
- Separate **as-sold** and **as-current** views; never blend both modes into a single KPI.

Relationship documentation must state **which Product** is referenced: the logical entity across time or a **specific version** at transaction time.

## 11. Tenant, Service, and Relationship Ownership Boundaries

The same model can be deployed:

- In one database: composite FKs enforced by the DBMS.
- Across schemas in one DBMS: FKs/transactions possible depending on deployment.
- Across two independent databases/shards: no automatic global FKs/transactions.
- Across two microservices communicating only via API/events: each service owns distinct data; requires contracts and failure handling.

**Identity scope** must be documented independently of topology. If Customer is unique only per tenant while Orders route by `customer_id` without tenant, requests may hit the wrong owner or check the wrong reference.

### 11.1. Relationship Owner Contract Template

~~~text
Relationship:
  SalesOrder PLACED_BY Customer

Identity:
  Order: (tenant_id, order_id)
  Customer: (tenant_id, customer_id)

Cardinality:
  Order -> Customer: 1..1
  Customer -> Order: 0..N

Write owner:
  Order Service / Order aggregate

Reference scope:
  Same tenant only

Creation:
  Order requires existing active Customer

Update:
  Customer reference immutable after CONFIRMED

Delete/archive:
  Customer archive does not delete Order
  Hard delete blocked while retention requires Order

Enforcement:
  Composite FK in one relational database
  Owner check for Customer active status
  Cross-service consistency: explicitly unresolved if split databases

Verification:
  FK orphan test, tenant mismatch test,
  concurrent archive/create scenario
~~~

Such a contract lets reviewers immediately spot **rules not derivable from FKs** and constraints that arise if services are later split.

### 11.2. Cross-Service Relationships Must Specify Guarantees

If Order Service stores `customer_id` while Customer Service owns Customers in another DB, documentation must state:

- Is the reference verified **synchronously at creation** or reconciled asynchronously?
- When Customer is locked/deleted, are historical Orders retained?
- Is a snapshot of Customer details required on Order?
- If the Customer API call times out, is the Order created as PENDING, rejected, or recorded provisionally?
- Can Customer codes be reused or moved between tenants?
- Who fixes orphan references when events arrive late?

Never simply write "FK to Customers" if the DBMS cannot enforce it. Call it a **logical reference** and document the protective protocol.

## 12. Data Dictionary: Documenting Entities and Individual Attributes

An ERD answers how entities connect; a **data dictionary** records what each attribute means, which source provides it, and when it may change.

Example dictionary for SalesOrder:

| Field | Logical / Physical Type | Meaning | NULL | Source/Rules |
| --- | --- | --- | --- | --- |
| `tenant_id` | ID / BIGINT | Organization owning the order | No | Part of PK and all tenant-scoped FKs |
| `order_id` | ID / BIGINT | Technical Order identifier within tenant | No | PK(tenant_id,order_id), immutable |
| `order_code` | Code / TEXT | Customer-facing code | No | UNIQUE(tenant_id,order_code), issued per policy |
| `customer_id` | ID / BIGINT | Customer placing the order | No in this case | FK(tenant_id,customer_id); guest checkout needs a different model |
| `status` | Enum / TEXT | Order lifecycle status | No | DRAFT, CONFIRMED, CANCELLED |
| `created_at` | Instant / TIMESTAMPTZ | Business record creation time | No | Never use in place of `order_id` |
| `confirmed_at` | Instant / TIMESTAMPTZ | Confirmation milestone when valid | Yes | Mandatory when status is CONFIRMED |
| `cancelled_at` | Instant / TIMESTAMPTZ | Business cancellation milestone | Yes | Mandatory when status is CANCELLED |

This dictionary should be enriched with **owner, sensitivity, retention, source version, examples, and limits** in real projects. For example, contact info and shipping addresses may constitute personal data requiring access controls, retention limits, and anonymization methods.

### 12.1. Distinguishing Data Type from Value Domain

The BIGINT type only describes integer representation within a numeric range. It **does not** tell you:

- Is this money, an ID, or a quantity?
- Can values be negative?
- Is the unit whole VND, cents, or a conversion index?
- Can IDs be reused?
- Which service issues it?
- Can it be NULL in DRAFT yet mandatory in CONFIRMED?

Example `unit_price_vnd` BIGINT in OrderLine:

~~~text
Attribute:
  unit_price_vnd

Meaning:
  Locked unit selling price for the order line, in whole VND.

Grain:
  One OrderLine at order creation time.

Constraints:
  NOT NULL, >= 0 in this model version.

Source:
  Pricing decision when creating/updating the Line before CONFIRMED.

Lifecycle:
  Immutable on a CONFIRMED Line;
  if the business requires corrections, an adjustment event/document is needed.

Anti-rule:
  Never read the current price from Products and mutate Line history.
~~~

This documentation style helps readers grasp **semantics** rather than just knowing a column is numeric.

### 12.2. Naming Relationships Expressively

Choose names like:

- `PLACED_BY`: Order is placed by Customer.
- `CONTAINS`: Order contains OrderLine.
- `REFERENCES_PRODUCT`: Line points to Product.
- `BELONGS_TO_TENANT`: data falls under tenant scope.
- `ATTEMPTED_PAYMENT_FOR`: a payment attempt for Order.
- `TAGGED_WITH`: Order currently holds a Label.

Names like HAS, FK_ID, or LINK without legends are usually inadequate when the same two entities have multiple relationships. If an Order has both a purchasing Customer and a gift-receiving Customer, define **two distinct roles**, each with its own keys/cardinality and historical behavior.

## 13. Relationship Catalog: A Contract Table for Every Connector

A **relationship catalog** lets reviewers audit every FK or logical reference without reading DDL line by line.

| Relationship | Child → Parent | Parent → Child | Scope | Existing Enforcement | Lifecycle |
| --- | --- | --- | --- | --- | --- |
| Customer–Order | 1..1 | 0..N | same tenant | Composite FK, Customer NOT NULL | No hard delete of Customer with Orders |
| Order–Line | 1..1 | 0..N | same Order/tenant | Composite FK, line PK | CONFIRMED requires 1..N; Lines locked for edits |
| Product–Line | 1..1 | 0..N | same tenant | Composite FK | Inactive Product retained for history |
| Order–PaymentAttempt | 1..1 | 0..N | same tenant | Composite FK, unique provider attempt | Not deleted with Order |
| Order–Label | 0..N | 0..N | same tenant | Junction table and composite PK | Unlinking does not delete Label |
| Tenant–Customer | 1..1 | 0..N | tenant | FK + composite PK | Tenant deletion requires system-wide process |

**Key point:** the table documents structural cardinality; the rule that a CONFIRMED Order has a minimum Line must be noted as **an additional condition**, rather than changing "0..N" to "1..N" across all states.

### 13.1. Complete Relationship Documentation Template

~~~yaml
# Illustrative design template example; NOT lesson metadata.
name: SALES_ORDER_CONTAINS_ORDER_LINE
predicate: "An Order contains the order lines belonging to that order"
left_entity: SalesOrder
right_entity: OrderLine

identity:
  order: [tenant_id, order_id]
  line: [tenant_id, order_id, line_no]

cardinality:
  order_to_lines:
    draft: "0..N"
    confirmed: "1..N"
  line_to_order: "1..1"

scope:
  tenant: "must share tenant_id"
  shard_owner: "Order aggregate owner"

creation:
  line_requires_existing_order: true
  line_no_unique_within_order: true

lifecycle:
  line_edit_after_confirm: "forbidden_by_domain"
  line_delete_after_confirm: "forbidden_by_domain"
  order_hard_delete: "restricted_while_business_history_retained"

enforcement:
  database: "PK, composite FK, quantity CHECK"
  application_transaction: "Order lock + confirm preconditions"
  not_enforced_by_fk: "confirmed order must contain >=1 line"

verification:
  - "query confirmed orders lacking lines"
  - "concurrent confirm/delete-last-line test"
  - "cross-tenant FK test"
~~~

This artifact should be managed as a **versioned design contract**, not merely pretty YAML for generating reports. If the spec says `"forbidden_by_domain"` while SQL lets a writer bypass it to delete Lines, the documentation no longer matches reality.

### 13.2. Rules for Documenting Exceptions

If the business has special cases, record them directly in the contract:

~~~text
Case:
  An IMPORTED_HISTORICAL Order may lack a Customer.

Decision:
  Do not assign a fake customer_id pointing to a current Customer.
  Use a distinct Order type and historical_customer_reference,
  or an approved Unknown Member model if reporting requires it.

Impact:
  Order -> Customer cardinality for IMPORTED differs from REGISTERED.
  The contract must document the discriminator and separate scope.
~~~

It is unnecessary to force an exact option in the example if the business has not yet decided. What matters is **never letting a real exception turn into a meaningless NULL** or leading other teams to assume "every Order has a Customer."

## 14. SQL Verification: Turning Contracts into Evidence

Model documentation carries high value when every critical rule has a **verification test**.

### 14.1. Finding CONFIRMED Orders Missing Lines

~~~sql
SELECT o.tenant_id, o.order_id
FROM sales_orders AS o
WHERE o.status = 'CONFIRMED'
  AND NOT EXISTS (
      SELECT 1
      FROM order_lines AS l
      WHERE l.tenant_id = o.tenant_id
        AND l.order_id = o.order_id
  );
-- Expected 0 rows if the invariant is properly enforced.
~~~

If the result is non-empty, trace which owner allowed the transition or deleted the last Line. Adding indexes can speed up the check but **cannot fix a broken write path**.

### 14.2. Finding Archived Customers Used to Create New Orders

~~~sql
SELECT o.tenant_id, o.order_id, o.created_at,
       c.archived_at
FROM sales_orders AS o
JOIN customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE c.archived_at IS NOT NULL
  AND o.created_at > c.archived_at;
~~~

**Interpret carefully:** an Order with `created_at` after `archived_at` might be a historical import/backfill or a system clock discrepancy. If the rule is "no Orders may be created after Customer archive," distinguish **business event time** from ingest time. Diagnostic queries do not replace command and event-source audits.

### 14.3. Checking Uniqueness by Business Key

~~~sql
SELECT tenant_id, order_code, COUNT(*) AS duplicates
FROM sales_orders
GROUP BY tenant_id, order_code
HAVING COUNT(*) > 1;
-- Should return no rows due to UNIQUE(tenant_id, order_code).
~~~

If adding UNIQUE via migration on legacy data, check for duplicates **before adding the constraint** and keep monitoring legacy writers during rollout.

### 14.4. Checking Orphans When FK Is Only a Logical Reference

Within a single database with enforced FKs, key orphans will not occur while integrity holds. However, if data arrives from another source system or FKs are **logical across services**, you can run:

~~~sql
SELECT o.tenant_id, o.order_id, o.customer_id
FROM sales_orders AS o
LEFT JOIN customers AS c
  ON c.tenant_id = o.tenant_id
 AND c.customer_id = o.customer_id
WHERE c.customer_id IS NULL;
~~~

If data resides in two separate databases, the query above is only **illustrative reconciliation logic** once both datasets sit in a common analytics environment; it does not magically run across services.

### 14.5. Checking 0..1 Cardinality Without UNIQUE

For a Profile → User relationship where business requires at most one Profile per User, if `UNIQUE(user_id)` is missing you can detect violations with:

~~~sql
SELECT user_id, COUNT(*) AS profile_count
FROM user_profiles
GROUP BY user_id
HAVING COUNT(*) > 1;
~~~

If the database already enforces `UNIQUE(user_id)`, the query returns empty when active; the check's value lies in **auditing historical data and catching unenforced model invariants**.

### 14.6. Do Not Use COUNT DISTINCT to Mask Fan-Out

Suppose an Order has 3 Lines and 2 PaymentAttempts. Joining directly on Order produces **3 × 2 = 6 rows**; `SUM(amount)` or `COUNT(*)` can be multiplied.

~~~sql
-- Wrong if summing amount per Order:
SELECT o.order_id, SUM(p.amount_vnd) AS paid_amount
FROM sales_orders AS o
JOIN order_lines AS l
  ON l.tenant_id = o.tenant_id
 AND l.order_id = o.order_id
JOIN payment_attempts AS p
  ON p.tenant_id = o.tenant_id
 AND p.order_id = o.order_id
GROUP BY o.order_id;
~~~

In a multi-tenant system, grouping solely by `order_id` can also **mix Orders from different tenants sharing the same `order_id`**. That is a key-scope bug **on top of** fan-out. Even after adding `tenant_id` to GROUP BY, joining two child relationships at detail grain still multiplies amounts.

Fix by defining the **reporting grain** and aggregating each child set to one row per Order before joining:

~~~sql
WITH line_totals AS (
    SELECT tenant_id, order_id,
           SUM(quantity * unit_price_vnd) AS line_amount_vnd
    FROM order_lines
    GROUP BY tenant_id, order_id
),
captured_payments AS (
    SELECT tenant_id, order_id,
           SUM(amount_vnd) AS captured_amount_vnd
    FROM payment_attempts
    WHERE status = 'CAPTURED'
    GROUP BY tenant_id, order_id
)
SELECT o.tenant_id, o.order_id,
       COALESCE(l.line_amount_vnd, 0) AS line_amount_vnd,
       COALESCE(p.captured_amount_vnd, 0) AS captured_amount_vnd
FROM sales_orders AS o
LEFT JOIN line_totals AS l
  ON l.tenant_id = o.tenant_id
 AND l.order_id = o.order_id
LEFT JOIN captured_payments AS p
  ON p.tenant_id = o.tenant_id
 AND p.order_id = o.order_id;
~~~

This is an **illustrative report**: it does not yet account for taxes, discounts, refunds, duplicate provider captures, currency, or the validity of `PaymentAttempt` statuses. Yet it demonstrates why documenting relationship cardinality also guides **correct query design**, not just DDL.

## 15. Negative Testing: Operations That Should Be Rejected

A relationship test plan does not only insert valid data. It must prove **what is forbidden**.

### 15.1. Tenant–Order FK Violation

Suppose Order 1001 exists only in tenant 1. Try creating a Line for tenant 2 with `order_id` 1001:

~~~sql
-- Expected FK error: tenant 2 does not have Order 1001.
INSERT INTO order_lines
    (tenant_id, order_id, line_no, product_id, quantity, unit_price_vnd)
VALUES (2, 1001, 1, 101, 1, 150000);
~~~

Product 101 exists in tenant 2 in the sample data, yet Order 1001 **does not exist in tenant 2**. The composite FK from Line to Order must reject this.

### 15.2. Line Key Identity Violation

~~~sql
-- Row line_no=1 in Order 1001 already exists.
INSERT INTO order_lines
    (tenant_id, order_id, line_no, product_id, quantity, unit_price_vnd)
VALUES (1, 1001, 1, 101, 1, 150000);
-- Expected PK error.
~~~

Two different Orders can both have `line_no=1`, so table-wide `UNIQUE(line_no)` would have the wrong scope.

### 15.3. Value Domain Violation

~~~sql
-- Expected CHECK error:
INSERT INTO sales_orders
    (tenant_id, order_id, order_code, customer_id, status)
VALUES (1, 1002, 'O-1002', 11, 'DELIVERED');
~~~

The error occurs because DELIVERED is outside the status domain of the **sample model**, not because real-world retail lacks DELIVERED. If the domain needs it, update both the state machine and the documentation rather than loosening CHECKs arbitrarily.

### 15.4. Deleting a Referenced Customer

~~~sql
-- Expected FK RESTRICT error since Order 1001 still references it.
DELETE FROM customers
WHERE tenant_id = 1 AND customer_id = 11;
~~~

To archive a Customer, update `archived_at` per policy and confirm no writer creates new Orders for archived Customers. Never add `ON DELETE CASCADE` just to "make DELETE succeed" without evaluating Order history.

### 15.5. Concurrency Testing for Cross-Table Invariants

A scenario to run using **two independent sessions** in a test environment:

~~~text
Session A:
  Lock Order 1001, verify it has a Line, pause before confirm.

Session B:
  Attempt to delete the last Line or edit a Line while Order is still DRAFT.

Expected:
  Both go through the same Order Owner and locking convention;
  no commit schedule produces a CONFIRMED Order without a Line.
~~~

Do not merely run two transactions sequentially and call it a concurrency test. Test interleaved timings, isolation levels, deadlocks/retries, and every Line mutation path that could break the invariant. When locking under the same convention, one side must block or be rejected based on post-commit state.

## 16. History Lifecycle, Soft Delete, and Personal Data

In relational models, **physical DELETE** and **business lifecycle termination** are two distinct acts.

For example, a Customer may move through:

~~~text
ACTIVE -> ARCHIVED -> ANONYMIZED
~~~

while Orders persist for transaction traceability. Documentation must specify:

1. Once archived, can the Customer still place new Orders?
2. Do past Orders still display the Customer's name?
3. Should PII be replaced with a pseudonym/token or specific attributes erased?
4. Which information remains stored due to legal or operational obligations?
5. When a Customer is hard-deleted, which FKs still reference it and under what conditions can they be reassigned/released?
6. What update or deletion schedule applies to derived copies in analytics/search/caches per policy?
7. Who approves and audits deletion/anonymization actions?

Never assert unilaterally that data must be kept forever or wiped immediately. That is a **policy, legal, and business decision** requiring accountable stakeholders.

### 16.1. Retaining Transaction History While Erasing PII

A design can separate **CustomerIdentity** holding personal info from **CustomerReference/OrderSnapshot** needed for transactions. After applying anonymization policies, an Order can retain a **non-directly-identifying identifier** and whatever facts remain required for reconciliation.

However, evaluate re-identification risks via remaining attributes, access permissions, encryption keys, backup retention, and analytics replicas. **Soft delete does not equal erasing personal data.**

### 16.2. Retained Relationships May Need a "Tombstone"

When a source object is removed from the system yet historical events must know it once existed, store a **tombstone** or controlled historical source code. Do not create a fake Customer lacking real attributes and pretend every Order has a valid Customer.

If using an Unknown Member, documentation must distinguish **unknown reference**, **policy-deleted object**, and **genuinely existing object**. These three cases carry different meanings and access permissions.

## 17. Polymorphic Relationships, Source Data, and Object Domains

An easily ambiguated pattern:

~~~text
Comment(
  target_type,
  target_id,
  content
)
~~~

`target_type` might be ORDER, PRODUCT, or CUSTOMER. An FK on `target_id` alone cannot ensure the target belongs to the **right table for `target_type`**. If the system genuinely uses a polymorphic association, documentation must specify:

- The valid set of target types.
- The identifier and tenant scope of each type.
- Who verifies target existence/ownership.
- What happens when a target is deleted/archived.
- Cardinality per target type.
- How queries avoid colliding identical IDs across different tables.

Modeling options:

| Option | Pros | Trade-offs |
| --- | --- | --- |
| Separate nullable `order_id`/`product_id` columns + CHECK exactly one | Enables real FKs to each table | More columns, requires XOR check, harder to add types |
| Dedicated link tables `CommentOrder`, `CommentProduct` | Clear FKs, independent relationship lifecycles | More tables, UNION read paths |
| Shared supertype `Target` table | Single unified PK/FK | Needs proper subtype lifecycle/sync design |
| `target_type + target_id` without physical FK | Flexible on ingest | Requires strong validation/owner/orphan reconciliation |

Never call a polymorphic ID a "foreign key" if the DBMS cannot enforce it. In model documentation, mark it **logical reference** with corresponding verification policies.

### 17.1. Multiple Sources Using Different Codes

If a Product is coded P-101 in ERP and SKU-001 on the storefront, a mapping table can be a separate entity:

~~~text
ProductExternalIdentity(
  source_system,
  source_product_code,
  tenant_id,
  product_id,
  valid_from,
  valid_to
)
~~~

Never naively join two tables by product name, nor assume a source code remains fixed for life. If mappings change over time, the relationship to Product needs **effective dates, source scope, and non-overlap checks**.

## 18. Comparing Relationship Documentation Across Relational, Document, Graph, and Warehouse Models

The same business meaning can be implemented across different structures. Documentation must preserve **invariant semantics** without forcing every technology to look like a relational ERD.

### 18.1. Relational (RDBMS)

- **PK/UNIQUE:** identity and candidate keys.
- **FK:** references, enforceable within the same DBMS and transaction scope.
- **CHECK/NOT NULL:** local single-row validity.
- **Procedure/transaction:** cross-row invariants and state transitions.
- **Index/partition:** physical access paths; do not replace invariants.

Documentation must distinguish constraints **enforced by the DB** from rules **defined only in the application**.

### 18.2. Document: Embedding Owned Component Relationships

An Order document may contain Lines:

~~~json
{
  "tenantId": 1,
  "orderId": 1001,
  "status": "DRAFT",
  "customerId": 11,
  "lines": [
    {"lineNo": 1, "productId": 101, "quantity": 2, "unitPriceVnd": 150000}
  ]
}
~~~

Here Order–Line is modeled as an **embedded component relationship**. This fits when Lines only have meaning inside an Order and are usually read/written alongside the Order. Yet ask:

- Does the document DB support atomic single-document updates?
- Are there size limits or contention risks if Lines grow very large?
- Customer/Product live in other documents: who validates references and tenant isolation?
- When Product changes name or price, does it alter Line history?
- When deleting an Order document, all Lines vanish with it: does that satisfy retention?

Embedding data does not automatically solve all 1–N relationships or cross-document constraints. Lifecycle documentation is just as vital as DDL.

### 18.3. Graph: Relationships as Property-Bearing Edges

In a graph:

~~~text
(Customer {tenant:1,id:11})
   -[:PLACED]-> (Order {tenant:1,id:1001})

(Order {tenant:1,id:1001})
   -[:CONTAINS {lineNo:1,quantity:2}]->
 (Product {tenant:1,id:101})
~~~

If the model uses a CONTAINS edge to represent OrderLine, ask whether **OrderLine has an independent identity and lifecycle**. A Line may need sale-time price, discounts, returns, adjustments, receipts, and `source_line_id`; in that case, a **dedicated Line node/entity** may fit better than a bare edge.

Graphs also carry special invariants:

- Does each Category have at most one direct parent or multiple parents?
- Are cycles forbidden?
- Are multiple edges of the same type permitted between the same two nodes?
- Do edges have `effective_from`/`effective_to` and history?
- Can a query traversing multiple paths count the same Product multiple times?

**Edge multiplicity** and acyclicity are not magically solved merely by storing the model in a graph DB.

### 18.4. Analytical Warehouse: Facts and Dimensions Have Distinct Grains

Because an Order has many Lines, `FactSalesLine` usually has the grain of **one sales line**, not one Order. `DimCustomer`/`DimProduct` supply context. Documentation must state:

- Is the Product key in the fact a **business key** or an **SCD2 version surrogate key**?
- Must every fact reference a dimension? What is the Unknown Member?
- Can one OrderLine appear across multiple distinct facts/events?
- Does joining `FactSales` with `FactReturns` cause fan-out?
- When a Product is archived or changes Category, do historical reports use the old or current Category?

In OLAP, key and cardinality documentation dictates safe joins and aggregations. Never infer from a single ERD FK line that every measure can be SUMmed across every dimension.

## 19. Model Review: Turning Diagrams into Versioned Documentation

A team should verify **model, DDL, and actual data** against the same version. Recommended workflow:

1. **Gather business questions** the model must answer.
2. **List entities and define one row** for each entity/table.
3. **Identify candidate keys**, tenant/source/time scopes, and code-change policies.
4. **Write predicates for every relationship** in both directions.
5. **Assign min..max cardinality** and state-dependent conditions.
6. **Define lifecycle behaviors:** create, edit, split/merge, archive, hard delete, anonymize.
7. **Assign owners/transaction boundaries** for invariants not enforceable on a single row.
8. **Map to PK/FK/UNIQUE/CHECK/indexes** and list rules not enforced by the DB.
9. **Write negative tests and reconciliation queries** for expected failure modes.
10. **Validate against existing data:** NULLs, orphans, duplicates, tenant mismatches, late events, history.
11. **Review with business owners and engineering:** finalize permissions, exceptions, SLOs, and retention periods.
12. **Version documentation and migrations:** note impacts on APIs, CDC, BI, and services.
13. **Monitor post-deploy drift:** compare published constraints against actual schemas, tests, and incoming data.

### 19.1. When Changing Cardinality or Lifecycle

Suppose initially Order → Customer = 1..1, and later guest checkout is added. You cannot simply drop NOT NULL on `customer_id` without answering:

- Which field distinguishes a guest Order?
- Are `guest_contact_snapshot`, consent, and separate retention required?
- Can a guest later be linked to a new Customer?
- If linked later, how is that decision historized?
- Do legacy APIs assume `customer_id` always exists?
- How do unique-customer dashboards count guests?

Changing cardinality **from 1..1 to 0..1** cascades through semantics, nullability, access controls, ETL, and tests. A successful DDL migration does not mean the system-wide contract is updated.

### 19.2. Short Design Decision Template

~~~text
Decision:
  Product is not hard-deleted if historical OrderLines exist.

Rationale:
  Needed for transaction traceability, receipts, and returns/refunds.

Model:
  OrderLine -> Product: 1..1
  Product -> OrderLine: 0..N
  Tenant-scoped FK, ON DELETE RESTRICT.

Allowed lifecycle:
  Product is_active TRUE -> FALSE.
  Disallow new Lines from picking an inactive Product.
  Historical Lines continue referencing Product.

Enforcement:
  FK protects references.
  Write owner enforces active check when creating Lines.
  Audit/reconciliation catches write paths bypassing the owner.

Alternatives:
  Full SKU/product name snapshot on Line
  or versioned dimension if classification history is needed.

Review trigger:
  When retention, data-deletion policies,
  or Product/SKU structures change.
~~~

A decision record lets future maintainers know **why** an FK was configured as RESTRICT and whom to consult before switching to CASCADE.

## 20. Common Documentation Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Drawing lines without predicates | Teams interpret the relationship differently | Write two-way business sentences |
| Writing only "1–N," omitting min cardinality | Unclear whether 0 Lines is allowed | Specify 0..N / 1..N by state |
| Calling every ID a global PK | Mixes tenants, source codes, versions | Document candidate/business/surrogate key scopes |
| FK on `customer_id` alone in multi-tenant systems | Can reference the wrong tenant | Composite FK `tenant_id + customer_id` |
| Assuming FK forces Order to have a Line | CONFIRMED Orders lack Lines | Owner transaction + audit all writers |
| Assuming NOT NULL proves a valid relationship | Column holds an ID whose parent may not exist | FK or controlled logical reference |
| Using CASCADE for every dependency | Wipes out financial history | Decide lifecycle and retention before `ON DELETE` |
| Assuming soft delete acts like DELETE | Writers still reference archived objects | Enforce archive checks inside write owner |
| Applying UNIQUE to reusable codes without scope/time | Breaks policy or collides with history | Define uniqueness by state/effective period |
| Using `CHECK(status IN (...))` alone for workflow | Illegal state transitions happen | State machine and transition guards |
| Omitting multi-role relationships | Confuses buyer/recipient/approver | Separate role names and FKs |
| Storing multiple SCD2 versions yet joining by business key without time filter | Multiplies facts and corrupts reports | Version-key FK or as-of lookup |
| Joining multiple child tables then SUMming | Fan-out inflation | Pre-aggregate to grain before joining |
| Embedding documents without lifecycle rules | Deleting parent wipes retained data | Clarify atomicity and retention |
| Graph checking only `parent != self` | Multi-hop cycles still occur | Path validation with concurrency control |
| Describing logical FKs as DB-enforced FKs | Misleads readers about cross-service guarantees | Document owner, protocol, reconciliation |
| Skipping tests for forbidden operations | Broken constraints linger undetected | Negative tests/concurrency tests |
| Failing to update docs when schemas change | Drift from production | Versioning, ADRs, drift checks |

## 21. Case Study Exercises and Solution Guides

### Exercise 1. Tenant-Scoped Order Keys

**Prompt:** Two tenants both have `order_id = 1001` and `order_code = O-1001`. Which unique keys are appropriate if the business allows identical codes across tenants?

**Solution guide:** `PK(tenant_id,order_id)` and `UNIQUE(tenant_id,order_code)`. Never place table-wide `UNIQUE(order_code)` when identity scope is tenant. If `order_id` is genuinely global, document that difference explicitly.

### Exercise 2. Interpreting Two-Way Cardinality

**Prompt:** A Customer may not have placed any orders yet; an Order must belong to a Customer. Write cardinality for both directions.

**Solution guide:** Customer → Order is 0..N; Order → Customer is 1..1. `customer_id` NOT NULL FK in Orders referencing Customer protects the Order side, without forcing every Customer to have an Order.

### Exercise 3. State-Dependent Conditions

**Prompt:** DRAFT may have no Lines; CONFIRMED must have at least one Line. Is the OrderLine → Order FK sufficient?

**Solution guide:** No. The FK only guarantees a Line has an Order. You need a `ConfirmOrder` rule checking `EXISTS` Line within the same transaction/owner and blocking other writers from deleting the last Line after confirmation.

### Exercise 4. 1–1 Yet Optional

**Prompt:** Each User can have at most one Profile, but account creation does not yet require a Profile. How should FK/UNIQUE be defined?

**Solution guide:** `Profile.user_id` NOT NULL + FK + UNIQUE. Users do not need a Profile immediately, so never infer that every User has a Profile solely from the FK on Profile.

### Exercise 5. N–M Relationships and Identity

**Prompt:** An Order has many Labels; a Label applies to many Orders. How do you prevent attaching the same Label twice in the current state?

**Solution guide:** An `OrderLabelLink` table with `PK(tenant_id,order_id,label_id)` and two tenant-scoped FKs. If attach/detach history is needed, change grain to events/effective intervals and prevent overlapping active intervals.

### Exercise 6. Inactive Products

**Prompt:** A Product is discontinued, yet many historical OrderLines still reference it. Should you put `ON DELETE CASCADE` from Product to Line?

**Solution guide:** No, when Order history must be preserved. Use `is_active`/`archived` and FK `ON DELETE RESTRICT`; the write owner blocks selecting inactive Products for new Lines while historical Lines stay valid.

### Exercise 7. Deleting a Customer with Orders

**Prompt:** A Customer requests anonymization while Order records must be retained per policy. Should deleting the Customer wipe out Orders?

**Solution guide:** Not by default. Design a policy separating PII from transaction identifiers, with controlled archiving/anonymization and retention. Soft delete does not equal PII erasure; hard delete must weigh FKs and specific retention obligations.

### Exercise 8. CHECK and State Transitions

**Prompt:** Status is restricted to DRAFT, CONFIRMED, CANCELLED. A writer transitions CANCELLED → CONFIRMED. Does `CHECK(status IN (...))` block it?

**Solution guide:** No, CONFIRMED is still within the value domain. You need a state machine and transition guard comparing old/new state inside a transaction, controlling all writers.

### Exercise 9. Duplicate `line_no`

**Prompt:** Order 1001 and Order 1002 both have line number 1. Is this a duplicate?

**Solution guide:** No. Line's grain and key are `(tenant_id,order_id,line_no)`. Table-wide `UNIQUE(line_no)` is wrong.

### Exercise 10. Composite FK and NULL

**Prompt:** `FK(tenant_id, customer_id)` is valid yet a NULL `customer_id` is still accepted under default configuration. Why?

**Solution guide:** Under `MATCH SIMPLE` FKs, when any referencing column is NULL, referential checking is skipped. If Customer is mandatory, combine `customer_id NOT NULL` with the FK; guest orders require a model with an explicit exception.

### Exercise 11. Code Is Not Identity

**Prompt:** Product changes SKU from A-101 to A-102; historical OrderLines must still point to the right Product. Should SKU be stored as the sole FK?

**Solution guide:** Prefer stable `product_id` as the FK with `UNIQUE` SKU per policy. If receipts need sale-time SKU, store a snapshot or corresponding version; never silently rewrite historical records when a Product changes codes.

### Exercise 12. An Order with Multiple Attempts

**Prompt:** An Order has 2 PaymentAttempts and 3 Lines. Joining directly and summing Attempt amounts produces how many joined rows if all rows match?

**Solution guide:** 2 × 3 = 6. The sum can be tripled. Pre-aggregate Attempts and Lines to Order grain before joining; clarify that only CAPTURED Attempts count.

### Exercise 13. Multi-Hop Category Cycles

**Prompt:** A has parent B, B has parent C, C has parent A. Does `CHECK(parent_category_id <> category_id)` catch this?

**Solution guide:** No, because no node is its own direct parent. Guaranteeing an acyclic hierarchy requires path checks under concurrency control or an appropriate owner structure.

### Exercise 14. Effective-Dated Relationships

**Prompt:** An Order holds Label L during `[01/10,10/10)`, then `[10/10,20/10)`. Do these two rows overlap? What about `[05/10,12/10)`?

**Solution guide:** The first two intervals only touch at the boundary, so they do not overlap under half-open intervals. The third overlaps both. `CHECK(valid_to > valid_from)` does not prevent overlaps; a constraint/procedure scoped to the relationship key is required.

### Exercise 15. Split Services Still Marked as FK on Diagrams

**Prompt:** Customer lives in database A, Orders in database B; docs say "FK Orders.customer_id → Customer.id" despite no distributed FK existing. What is wrong?

**Solution guide:** Documentation misstates actual guarantees. Label it a logical reference, specifying scope, owner, existence checks, delete/tenant-move handling, timeouts, replays, orphan reconciliation, and acceptance timing.

### Exercise 16. Switching from Mandatory Customer to Guest Checkout

**Prompt:** Product wants to allow ordering without an account. Is dropping `NOT NULL` from `customer_id` enough?

**Solution guide:** No. You must decide how to distinguish guest vs. registered orders, shipping info and retention, whether a guest can later attach to a Customer, legacy APIs/reports assuming Customer, and validation rules. This is a cardinality and lifecycle change, not merely a schema tweak.

## 22. Acceptance Checklist for Keys, Relationships, and Lifecycle Documentation

- [ ] Every entity has a **single-row grain definition** and clear business scope.
- [ ] Candidate keys, primary keys, alternate/business keys, and code-change/reuse policies are documented.
- [ ] Keys scoped by tenant/source/region have **verified uniqueness scopes**, not inferred from sample data.
- [ ] Every relationship has a **predicate**, role names at both ends, and min..max cardinality from both perspectives.
- [ ] Cardinality conditions that vary by **state or time** are documented outside the static ERD.
- [ ] FKs are mapped in the right direction, including tenant columns where needed; cross-DB references are marked logical.
- [ ] 1–1, 1–N, N–M, and self-referencing relationships have appropriate **keys and junction tables**.
- [ ] ON DELETE/ON UPDATE actions are chosen per **business lifecycle and retention**, not habit.
- [ ] Create, update, lock, archive, anonymize, delete, and state-transition rules are stated explicitly per entity.
- [ ] Invariants unenforceable by FK/CHECK are assigned **write owners, transactions/procedures, and concurrency tests**.
- [ ] Policies cover NULL, Unknown, guest, late data, orphans, duplicates, and historical events.
- [ ] Effective-dated/SCD dimensions are joined on the right version without overlap-induced fan-out.
- [ ] Personal data and history retention policies have owners/workflows, never confusing soft delete with PII erasure.
- [ ] Data dictionary, ERD, relationship catalog, DDL, and API/event schemas express the same contract version.
- [ ] Positive/negative verification tests and reconciliation queries are linked to every critical invariant.
- [ ] Model changes include impact reviews across readers/writers, CDC, document, graph, warehouse, and dashboards.

## 23. Takeaways

- **Keys** are more than an ID column's data type: they require scope, stability, change/reuse policies, and matching PK/UNIQUE constraints.
- **Relationships** must read as business sentences with roles, not merely lines and FK names.
- **Cardinality** includes **min and max on both sides**. It can depend on state—such as a CONFIRMED Order requiring Lines—which static ERDs struggle to capture fully.
- **FKs protect one-way referential existence**, but do not automatically guard cross-row invariants or state machines.
- **ON DELETE/UPDATE** are lifecycle decisions: CASCADE can fit auxiliary data, yet is dangerous for receipts, Payments, and business history.
- **Soft delete, archive, anonymize, and hard delete differ** in semantics, references, and data obligations.
- **Effective-dated relationships** require interval definitions, versions, lookup timestamps, and overlap protection.
- **Tenant/shard/service** boundaries are part of identity and enforcement contracts; cross-service logical references are not DBMS-enforced FKs.
- **Documentation becomes verifiable** when each invariant connects to a constraint, owner/protocol, and test or reconciliation query.

Useful data model documentation does more than help viewers see how tables connect. It enables engineers, business owners, and testers to **reach the exact same conclusion on how a row is identified, who links to whom, how many times they can link, when a relationship is valid, and what must happen when object lifecycles change**.
