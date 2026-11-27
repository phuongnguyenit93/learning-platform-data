# Structural Normalization Is No Substitute for Accurate Business Terms and Rules

A schema can **satisfy 3NF, BCNF, or even 5NF** structurally and still describe **the business operations inaccurately**. For example, a **shipments** table stores only one shipment per order because the designer believes "each order is shipped only once"; in reality, an order can be split into multiple shipments across different days. Keys and functional dependencies built on a false assumption strip the system of the ability to store a valid business state.

**Normalization** organizes data based on **confirmed** dependencies. It **does not define on its own** what constitutes a "customer," what "completed order" means, which price counts toward revenue, the scope within which an identifier is unique, or which values must be frozen at transaction time.

This lesson belongs to the **Normalization** chapter of the **DATABASE_DATA_MODELING** module. Its goal is to combine data-modeling discipline with skills for clarifying terms, constraints, time semantics, and data scope—then verifying them with relational models, SQL, and business scenarios.

## 1. Two Distinct Layers of Correctness

| Layer | Question to Answer | Example Failure |
| --- | --- | --- |
| **Semantic correctness** | What fact does one row represent? Are terms, scope, lifecycle, rules, and exceptions right? | Equating "order" with "shipment"; dropping multi-shipment orders |
| **Structural correctness** | Do candidate keys, functional dependencies, normal forms, decompositions, and constraints fit that semantics? | Copying current customer names into every order line and updating them inconsistently |

The two layers **complement** rather than replace each other. A model can be:

- **Semantically right yet redundant:** every shipment line stores the current warehouse name, causing update anomalies.
- **Cleanly normalized yet semantically wrong:** placing **UNIQUE(order_id)** on the shipments table when one order can have multiple shipments.
- **Right for both today yet hard to evolve:** assuming a single currency or single marketplace without declaring scope, making keys and historical data ambiguous when the system expands.

A normalized schema only protects **the rules that were stated and modeled**. If the initial rule is wrong, normalization can make the system enforce **a false assumption very strictly**.

## 2. Business Terms Must Have Operational Definitions

A single word in requirements documents often has multiple valid interpretations. The designer must translate it into a **data-verifiable definition**.

### 2.1. One Word, Multiple Concepts

| Common Term | Questions to Clarify | Modeling Consequence |
| --- | --- | --- |
| **Customer** | Individual, account, contracting organization, or recipient? Can guest buyers place orders? | May need separate **customers**, **accounts**, **organizations**, **recipients**; do not assume one email = one customer |
| **Product** | Product line, SKU variant, service bundle, or catalog version? Can SKUs be reused? | Determines grain, keys, and **product–variant–SKU** relationships |
| **Order** | Draft cart, confirmed purchase commitment, or payment batch? | Affects creation time, status, keys, and link to payments |
| **Order line** | Can a product appear only once per order, or across multiple lines with different prices/promotions? | Choose **(order_id, line_no)** instead of assuming **(order_id, product_id)** |
| **Shipment** | Does one order map to one shipment, many shipments, or can one shipment consolidate multiple orders? | Determines 1-to-many / many-to-many cardinality and **shipments** key |
| **Price** | Current list price, quoted price, post-discount price, or price locked at checkout? | Do not conflate **current_price** and **unit_price_at_order** |
| **Revenue** | By order date, payment date, shipment date, invoice date, or obligation fulfillment? Net of refunds? | Requires event grain and calculation policy, not just an **amount** column |
| **Completed** | Payment received, full quantity delivered, customer confirmed, or return window expired? | Must define state transition conditions; do not merely add a string **COMPLETED** |

For instance, two departments may both say "active customer," yet:

- Customer Support means an account that is not suspended.
- Sales means a customer who purchased at least once in the last 90 days.
- Finance means a customer with an open balance or active contract.

Three interpretations lead to **three different query criteria**. Adding an **is_active BOOLEAN** column without defining "active" and its source of truth merely turns business ambiguity into a column whose true/false value depends on who wrote it.

### 2.2. Minimum Glossary Entry

Every critical term should specify:

1. **Official name and synonyms:** e.g., "shipment," distinct from "order."
2. **Positive definition:** what it represents.
3. **Exclusions:** a shipment is neither an invoice nor a payment event.
4. **Unit/grain:** what one ID represents—a shipment, a line, or an event.
5. **Lifecycle and timing:** when created, updated, locked, or canceled; what is current vs. historical.
6. **Identifier scope:** unique globally, per store, per partner, or per period.
7. **Rule owner:** team or role that approves and owns changes to the definition.
8. **Valid/invalid examples:** especially exceptions and boundary cases.

**Example glossary:**

| Term | Definition in Example | Scope / Time |
| --- | --- | --- |
| **order_id** | Identifier of a placed purchase commitment; may contain multiple lines and multiple shipments | Unique within one sales system |
| **line_no** | Sequential line number within an order; may repeat across other orders | Unique within **order_id** |
| **shipment_no** | Sequential shipment number within an order | Unique within **order_id** |
| **unit_price_vnd_at_order** | VND unit price locked for the order line at placement time | Historical fact of **(order_id, line_no)** |
| **ship_to_address_snapshot** | Address used when creating the shipment; does not change if customer edits profile | Fact of **(order_id, shipment_no)** |
| **shipment_status** | Processing state of a shipment along defined steps | Current value; may require a status transition log |

The word **snapshot** in a column name makes explicit the decision not to retroactively overwrite history when current attributes change. Good column names do not replace specifications, yet they reduce ambiguity when reading data.

## 3. Business Rules Must Be Stated as Invariants and Exceptions

An **invariant** is a condition that must hold for every data state permitted by the system. Vague descriptions are hard to translate into keys and constraints.

Compare:

| Ambiguous Statement | Verifiable Statement |
| --- | --- |
| "Every order has a shipping address." | "Each **shipment** has exactly one locked-in address; one order can have multiple shipments to different addresses." |
| "Every product has one price." | "Current list price can vary by sales channel and effective time; locked-in unit price belongs to each order line." |
| "Never ship more than ordered." | "The sum of **shipped_quantity** across valid shipments for the same **(order_id, line_no)** never exceeds **ordered_quantity**, after accounting for cancellation/adjustment rules." |
| "Item codes are unique." | "SKU is unique within one store catalog at a point in time; may only be reused under an approved policy." |
| "Orders are completed." | "An order is marked COMPLETED once all shippable lines are fully delivered and policy payment/cancellation conditions are met." |

Ask further:

- **Exceptions:** are there pre-orders, zero-priced promotional gifts, split shipments, returns/exchanges, or walk-in orders?
- **Frequency and lifecycle:** can an attribute change over time without being edited retroactively?
- **Write authority:** do multiple systems write the same fact, or is there a single authoritative source?
- **Concurrency:** can two processes ship the same order line at the exact same moment?
- **Scope boundary:** does the rule apply within one store or across a multi-store system?

Every good constraint should come with a **negative example**: a state the system must reject, not only valid examples. That prevents turning a designer's unspoken assumption into a permanent database rule.

## 4. Functional Dependencies Cannot Be Inferred from Sample Data Alone

A functional dependency **X → Y** means: in **every valid state** of the relation, if two rows share the same X, they must share the same Y.

Example:

~~~text
order_id -> customer_id
(order_id, line_no) -> product_id, ordered_quantity, unit_price_vnd_at_order
~~~

Those dependencies hold **when** an order belongs to one customer and each order–line pair identifies one line.

Conversely, do not blindly accept statements like:

~~~text
customer_id -> ship_to_address_snapshot   -- usually FALSE: customer can ship to many addresses
product_id  -> unit_price_vnd_at_order    -- usually FALSE: price depends on transaction
order_id    -> shipment_no               -- FALSE if an order splits into multiple shipments
email       -> customer_id               -- depends on account and email rules
~~~

### 4.1. Matching Sample Values Do Not Create a Dependency

If the first 500 orders each shipped in one parcel, current data makes **order_id → shipment_no** look true. Yet **allowing one order to split shipments** suffices to refute that dependency under business rules, even if no split shipment has occurred in sample data yet.

If current customers happen to have distinct emails, that likewise does not prove email is an immutable identifier or always present. Emails can change, be shared, remain unverified, be recycled, or be absent for walk-in buyers.

### 4.2. Changing Semantics Changes Candidate Keys

Suppose an old design specifies:

~~~text
shipments(order_id, shipped_at, address, ...)
PRIMARY KEY (order_id)
~~~

This can represent **at most one shipment per order**. If new requirements permit multiple shipments, the grain must change to **one shipment of an order**, for example:

~~~text
shipments(order_id, shipment_no, shipped_at, address, ...)
PRIMARY KEY (order_id, shipment_no)
~~~

This change is not pure "normalization tuning." It is **correcting a business assertion** about how many events can exist.

### 4.3. Normal Forms Are Conditional Conclusions

2NF, 3NF, BCNF, 4NF, and 5NF all rest on dependencies and keys that are **true within the confirmed business scope**. A table can satisfy 3NF under a wrong dependency set and still fail to store valid states; conversely, a table called "unnormalized" might actually be storing values at **different points in time**, rather than duplicating the same fact.

Hence the proper sequence is **confirm terminology → confirm dependencies/constraints → determine keys → check normal forms → test usage scenarios**.

## 5. End-to-End Scenario: One Order, Many Lines, Many Shipments

Illustrative assumptions for building the schema:

- Each registered customer has a unique **customer_id**; one customer can have many orders.
- Each product has a unique **product_id**; current product name does not identify the product.
- An order belongs to one customer and can have many lines; lines are numbered by **line_no** within the order.
- An order can be delivered across multiple shipments; each shipment has a **shipment_no** within the order.
- An order line can be split across multiple shipments; a shipment can contain one or more lines **of that same order**.
- Locked-in VND unit price belongs to the order line; locked-in shipping address belongs to the shipment.
- Ordered quantity is a positive integer; shipped quantity in an allocation is a positive integer.
- An order may not have any shipments yet; an ordered line may not be shipped yet.

Under these definitions, there are clear independent business grains:

| Relation | Grain | Candidate Key |
| --- | --- | --- |
| **orders** | One order | **order_id** |
| **order_lines** | One line of an order | **(order_id, line_no)** |
| **shipments** | One shipment of an order | **(order_id, shipment_no)** |
| **shipment_items** | One portion of an order line shipped in a shipment | **(order_id, shipment_no, line_no)** |

This neither forces every order to have exactly one shipment nor forces every line to ship completely in one shipment.

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : "places"
    ORDERS ||--o{ ORDER_LINES : "contains"
    PRODUCTS ||--o{ ORDER_LINES : "ordered in"
    ORDERS ||--o{ SHIPMENTS : "split into"
    SHIPMENTS ||--o{ SHIPMENT_ITEMS : "includes"
    ORDER_LINES ||--o{ SHIPMENT_ITEMS : "allocated via"
    CUSTOMERS {
        varchar customer_id PK
        varchar display_name
    }
    ORDERS {
        varchar order_id PK
        varchar customer_id FK
        timestamptz placed_at
    }
    ORDER_LINES {
        varchar order_id PK, FK
        integer line_no PK
        varchar product_id FK
        integer ordered_quantity
        bigint unit_price_vnd_at_order
    }
    SHIPMENTS {
        varchar order_id PK, FK
        integer shipment_no PK
        text ship_to_address_snapshot
        varchar status
    }
    SHIPMENT_ITEMS {
        varchar order_id PK, FK
        integer shipment_no PK, FK
        integer line_no PK, FK
        integer shipped_quantity
    }
~~~

**Meaning of shipment_items:** it is not merely a "technical join table" between two IDs. Each row holds the fact **shipped_quantity** for a line in a shipment; dropping it loses allocation quantities. Foreign keys must ensure the shipped line and shipment **belong to the same order**, not merely that each ID exists somewhere in the database.

## 6. Translating Confirmed Rules into a PostgreSQL Schema

The following schema is an **intentionally scoped** example: single product catalog, single VND currency, registered customers, no return/exchange modeling, and no multi-order consolidated shipments. These boundaries must be stated explicitly rather than treated as universal truths.

### 6.1. Keys and Referential Relationships

~~~sql
CREATE TABLE customers (
    customer_id VARCHAR(12) PRIMARY KEY,
    display_name VARCHAR(120) NOT NULL,
    contact_phone VARCHAR(32)
);

CREATE TABLE products (
    product_id VARCHAR(12) PRIMARY KEY,
    sku VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(150) NOT NULL
);

CREATE TABLE orders (
    order_id VARCHAR(12) PRIMARY KEY,
    customer_id VARCHAR(12) NOT NULL
        REFERENCES customers(customer_id),
    placed_at TIMESTAMPTZ NOT NULL,
    order_status VARCHAR(16) NOT NULL
        CHECK (order_status IN ('PLACED', 'CANCELLED', 'CLOSED'))
);

CREATE TABLE order_lines (
    order_id VARCHAR(12) NOT NULL
        REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id VARCHAR(12) NOT NULL
        REFERENCES products(product_id),
    ordered_quantity INTEGER NOT NULL
        CHECK (ordered_quantity > 0),
    unit_price_vnd_at_order BIGINT NOT NULL
        CHECK (unit_price_vnd_at_order >= 0),
    PRIMARY KEY (order_id, line_no)
);

CREATE TABLE shipments (
    order_id VARCHAR(12) NOT NULL
        REFERENCES orders(order_id),
    shipment_no INTEGER NOT NULL CHECK (shipment_no > 0),
    ship_to_address_snapshot TEXT NOT NULL,
    shipped_at TIMESTAMPTZ NOT NULL,
    shipment_status VARCHAR(16) NOT NULL
        CHECK (shipment_status IN ('DISPATCHED', 'DELIVERED')),
    PRIMARY KEY (order_id, shipment_no)
);

CREATE TABLE shipment_items (
    order_id VARCHAR(12) NOT NULL,
    shipment_no INTEGER NOT NULL,
    line_no INTEGER NOT NULL,
    shipped_quantity INTEGER NOT NULL
        CHECK (shipped_quantity > 0),
    PRIMARY KEY (order_id, shipment_no, line_no),
    FOREIGN KEY (order_id, shipment_no)
        REFERENCES shipments(order_id, shipment_no),
    FOREIGN KEY (order_id, line_no)
        REFERENCES order_lines(order_id, line_no)
);
~~~

Key details:

- **order_id** identifies only the order; **(order_id, shipment_no)** identifies a shipment under the example rules.
- One shipment can carry multiple lines, and one line can span multiple shipments; **shipment_items** records the actual dispatched quantity.
- The two **composite FOREIGN KEYs** on **shipment_items** share the **same order_id**, ensuring each allocation links a shipment and a line **within the same order**.
- **contact_phone** has no **UNIQUE** constraint because the example does **not** assume phone numbers uniquely identify a single customer.
- **UNIQUE(sku)** is a **business assumption of this single-store catalog**; if SKUs are unique per seller, version, or time period, the constraint must change.
- **CHECK** on status only validates **membership in the allowed value list**, not transition ordering or whether quantities are fully delivered.

The columns **shipped_at** and **shipment_status** in this example represent a shipment **already dispatched**; unshipped drafts, failed deliveries, returns, or rescheduling are not yet modeled. Adding those scenarios requires revisiting grain, statuses, and quantity arithmetic rules.

### 6.2. Sample Data Demonstrating One Order Split into Multiple Shipments

~~~sql
INSERT INTO customers (customer_id, display_name, contact_phone)
VALUES ('C01', 'An', '+84901234567');

INSERT INTO products (product_id, sku, product_name) VALUES
    ('P10', 'KB-001', 'Keyboard'),
    ('P20', 'MS-001', 'Mouse');

INSERT INTO orders (order_id, customer_id, placed_at, order_status)
VALUES (
    'O1001',
    'C01',
    TIMESTAMPTZ '2026-11-20 09:00:00+07',
    'PLACED'
);

INSERT INTO order_lines
    (order_id, line_no, product_id,
     ordered_quantity, unit_price_vnd_at_order)
VALUES
    ('O1001', 1, 'P10', 3, 300000),
    ('O1001', 2, 'P20', 1, 200000);

INSERT INTO shipments
    (order_id, shipment_no, ship_to_address_snapshot,
     shipped_at, shipment_status)
VALUES
    ('O1001', 1, '12 Nguyễn Huệ, TP.HCM',
     TIMESTAMPTZ '2026-11-21 10:00:00+07', 'DELIVERED'),
    ('O1001', 2, '99 Lê Lợi, TP.HCM',
     TIMESTAMPTZ '2026-11-22 11:00:00+07', 'DISPATCHED');

INSERT INTO shipment_items
    (order_id, shipment_no, line_no, shipped_quantity)
VALUES
    ('O1001', 1, 1, 2),
    ('O1001', 2, 1, 1),
    ('O1001', 2, 2, 1);
~~~

One order has two shipments and two different addresses. Line 1 orders three keyboards, split into **two units in shipment 1** and **one unit in shipment 2**. This cannot be fully represented under assumptions like **order_id → shipment_no** or **order_id → ship_to_address_snapshot**.

Query confirming dispatched quantities per line:

~~~sql
SELECT
    ol.order_id,
    ol.line_no,
    p.product_name,
    ol.ordered_quantity,
    COALESCE(SUM(si.shipped_quantity), 0) AS shipped_quantity,
    ol.ordered_quantity
      - COALESCE(SUM(si.shipped_quantity), 0) AS remaining_quantity
FROM order_lines AS ol
JOIN products AS p
  ON p.product_id = ol.product_id
LEFT JOIN shipment_items AS si
  ON si.order_id = ol.order_id
 AND si.line_no = ol.line_no
GROUP BY ol.order_id, ol.line_no, p.product_name,
         ol.ordered_quantity
ORDER BY ol.order_id, ol.line_no;
~~~

Result on the sample data:

| order_id | line_no | ordered_quantity | shipped_quantity | remaining_quantity |
| --- | ---: | ---: | ---: | ---: |
| O1001 | 1 | 3 | 3 | 0 |
| O1001 | 2 | 1 | 1 | 0 |

In this example, **shipped_quantity** is the dispatched quantity; it does not mean the full quantity was **successfully delivered**, because shipment 2 is still **DISPATCHED**. If a report needs delivered quantity, filter or aggregate by delivered status and applicable return rules.

### 6.3. Which Errors Does This Schema Already Prevent?

| Scenario | Enforcing Constraint |
| --- | --- |
| Two lines with the same **(order_id, line_no)** | **PRIMARY KEY** on **order_lines** |
| Two shipments with the same **(order_id, shipment_no)** | **PRIMARY KEY** on **shipments** |
| Zero or negative ordered/shipped quantity | **CHECK** on respective column |
| Recording a shipment for a nonexistent order | **FOREIGN KEY** on **shipments** |
| Allocating a line from a different order than the shipment | **Two composite FOREIGN KEYs** in **shipment_items** |
| Writing a status completely outside the allowed list | **CHECK** on **order_status**, **shipment_status** |

For example, if **O1002** has a line 3, the system is **not** allowed to allocate that line to shipment **(O1001, 2)** merely because both the shipment and the line exist somewhere. The composite keys force allocations to share the same **order_id**.

### 6.4. What Is Still Not Enforced by DDL Alone?

The business rule requires that **total shipped quantity across shipments for a line never exceeds ordered quantity**:

~~~text
For every (order_id, line_no):

SUM(shipment_items.shipped_quantity)
  <= order_lines.ordered_quantity
~~~

This is a **multi-row aggregate constraint**. A simple row-level **CHECK** on **shipment_items.shipped_quantity > 0** is not enough.

Test inside a transaction and roll back:

~~~sql
BEGIN;

INSERT INTO shipments
    (order_id, shipment_no, ship_to_address_snapshot,
     shipped_at, shipment_status)
VALUES
    ('O1001', 3, '12 Nguyễn Huệ, TP.HCM',
     TIMESTAMPTZ '2026-11-22 12:00:00+07', 'DISPATCHED');

-- Line 1 already shipped all 3 units in the first two shipments.
-- The table still accepts 1 more unit if only the CHECK/FK/PK constraints above exist.
INSERT INTO shipment_items
    (order_id, shipment_no, line_no, shipped_quantity)
VALUES ('O1001', 3, 1, 1);

ROLLBACK;
~~~

After those two INSERTs in the demo transaction, total shipped quantity on line 1 is **4 > 3**, yet none of the row-level keys, foreign keys, or CHECK constraints raise an error. This is a **business-constraint enforcement gap**, not necessarily a 3NF violation.

Protecting it requires a **transactional write protocol** or an additional constraint mechanism designed for group totals. For example:

1. Start a transaction.
2. **Lock the corresponding order_lines row** using **SELECT ... FOR UPDATE** (or equivalent concurrency control).
3. Read the current **SUM(shipped_quantity)** for that line.
4. Insert only if the new sum does not exceed **ordered_quantity**.
5. Commit; every write path modifying shipped quantities **must follow the same locking protocol**, and edits to ordered quantity, cancellations, or returns must also be accounted for.

~~~sql
-- Locking step outline, invoked with parameters from the application:
BEGIN;

SELECT ordered_quantity
FROM order_lines
WHERE order_id = :order_id AND line_no = :line_no
FOR UPDATE;

SELECT COALESCE(SUM(shipped_quantity), 0) AS already_shipped
FROM shipment_items
WHERE order_id = :order_id AND line_no = :line_no;

-- Application checks:
-- already_shipped + requested_quantity <= ordered_quantity.
-- Only after check succeeds, INSERT/UPDATE shipment_items.
-- All related write paths must follow the same protocol.

COMMIT;
~~~

This SQL block **is a parameterized outline**, not a standalone runnable script; it omits the INSERT statement itself. In a multi-writer system, enforce the rule via tested transactions, triggers, procedures, or concurrency-safe mechanisms—never rely on an unguarded pre-check **SELECT** outside a transaction. If validation lives in only one application path, another write path can still violate it.

### 6.5. Status Is a State Machine, Not Just a Column

**CHECK (order_status IN (...))** cannot prevent a direct transition **CANCELLED → CLOSED** when business policy forbids it. State transitions must be specified explicitly:

~~~mermaid
stateDiagram-v2
    [*] --> PLACED
    PLACED --> CANCELLED : "permitted to cancel"
    PLACED --> CLOSED : "eligible to close"
    CANCELLED --> [*]
    CLOSED --> [*]
~~~

This is an **illustrative workflow diagram**, omitting returns or order reopening. To audit changes, you can store **order_status_events(order_id, event_no, from_status, to_status, changed_at, actor_id)** with clearly defined keys, timestamps, and event immutability.

Two separate questions must be answered:

- Is the **current status** within the allowed value set? That is a domain check.
- Are the **state transition** and open/close preconditions valid? That is a business rule involving prior state, triggering event, actor permissions, and potentially data in other tables.

## 7. Identifier Scope and Temporal Semantics

The two properties most commonly misunderstood in real-world data modeling are **uniqueness** and **effective timing**.

### 7.1. "Unique" Must Have an Explicit Scope

Suppose the system expands from a single store to multiple independent sellers. If SKU **KB-001** is allowed on two sellers with different meanings, a global unique constraint on **sku** as in section 6 is no longer true.

A revised rule might be:

~~~text
(seller_id, sku) -> product_id
~~~

assuming SKU is unique **within one seller** at a given time and never reused. Then:

~~~sql
CREATE TABLE seller_products (
    seller_id VARCHAR(12) NOT NULL,
    product_id VARCHAR(12) NOT NULL,
    sku VARCHAR(30) NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (seller_id, product_id),
    UNIQUE (seller_id, sku)
);
~~~

This is an **alternative design example** for a multi-seller system, **not** an in-place alteration of section 6's **products** table. If an SKU can be reused after retirement, **UNIQUE(seller_id, sku)** is still too strict for retaining history; you need versioning or effective intervals with time-scoped uniqueness checks.

Always ask "unique where, for how long, and with what exceptions?" before placing **PRIMARY KEY** or **UNIQUE**.

### 7.2. Two Kinds of Time Commonly Confused

| Concept | Meaning | Example |
| --- | --- | --- |
| **Effective / business occurrence time** | When a price, permission, or status is considered valid in the business domain | Price takes effect on Dec 1 |
| **System recorded time** | When the database received or updated the record | On Dec 3, pricing data effective Dec 1 was entered |
| **Transaction-time snapshot** | Locked-in value explaining the transaction at that moment | Unit price on an order line placed on Nov 20 |

These timestamps can differ. When transactions arrive late or are retroactively adjusted, an **updated_at** column cannot answer all historical questions.

An effective-dated price list might have the grain:

~~~text
(product_id, price_list_id, valid_from)
    -> unit_price, valid_to
~~~

yet that **is not enough** to prevent two overlapping effective intervals for the same product and price list. The rule "at most one active price at any point in time" requires checking **time intervals**, via exclusion constraints or controlled write logic depending on the DBMS.

For **unit_price_vnd_at_order**, never recompute an old order from current price lists if doing so alters locked-in transaction terms.

### 7.3. Defining a Metric Does Not Belong Solely to the Schema

Suppose a report asks for **November revenue**. There are at least these interpretations:

- Total value of **orders placed in the month**, including unshipped orders.
- Value of goods **dispatched from the warehouse in the month**.
- Value of goods **successfully delivered in the month**.
- Cash **paid in the month**.
- Accounting revenue **recognized under accounting policy** in the month, adjusted for returns and refunds.

These measures differ in **event grain, timestamp, monetary basis, status filters, and adjustments**. Normalizing to 3NF does not decide which metric is "revenue."

Instead of using an ambiguous label **revenue**, write a metric specification: data source, formula, timezone, cutoff moment, refunds/cancellations, currency, recognition policy, and owner. For analytical warehouses, the **fact** model likewise needs a defined grain before choosing dimensions and keys.

## 8. A Correct Schema Needs Multiple Layers of Protection

| Rule Type | Possible Mechanism | Known Limitation |
| --- | --- | --- |
| Required value | **NOT NULL** | Does not verify semantic validity of the value |
| Numeric/value domain | **CHECK**, data types | Validates only per-row expressions allowed by the DBMS |
| Scoped uniqueness | **PRIMARY KEY**, **UNIQUE** | Scope, NULLs, and effective time must be modeled properly |
| Entity existence relationship | **FOREIGN KEY** | Does not guarantee valid states or behavior on either entity |
| Non-overlapping effective intervals | Interval constraints, exclusion constraints, or locking transactions | Does not replace defining interval start/end semantics |
| Sum of shipped <= ordered | Locking transactions, triggers/procedures, or controlled summary design | Must handle concurrency and all update paths |
| Valid state transitions | State machine with consistent write paths and audit logs | **CHECK(status IN ...)** only checks the final value |
| Transition & approval permissions | Authorization, business policy, event logs | Foreign keys do not enforce who is permitted to act |
| Definitions of revenue, active customer | Metric glossary, calculation rules, report tests | Cannot be inferred from column names |

**Normalization and constraints are not substitutes for one another**: normalization places facts in the right relations; constraints and write protocols prevent states that violate real-world rules.

### 8.1. Monitoring Queries Only Inspect Existing Data

Example query detecting lines whose shipped quantity exceeds ordered quantity:

~~~sql
SELECT
    ol.order_id,
    ol.line_no,
    ol.ordered_quantity,
    COALESCE(SUM(si.shipped_quantity), 0) AS shipped_quantity
FROM order_lines AS ol
LEFT JOIN shipment_items AS si
  ON si.order_id = ol.order_id
 AND si.line_no = ol.line_no
GROUP BY ol.order_id, ol.line_no, ol.ordered_quantity
HAVING COALESCE(SUM(si.shipped_quantity), 0)
       > ol.ordered_quantity;
~~~

Zero returned rows means **no violation was detected** in the queried snapshot; it **does not prove** the write path prevents future violations. Always distinguish **detection**, **prevention**, and **recovery/remediation**.

### 8.2. Do Not Equate Normal Forms with Application Correctness

An **orders** table can be in 3NF while the application still records the wrong order date due to a timezone bug. A **shipments** table can be in BCNF while the application marks **DELIVERED** too early. A completely redundancy-free model might still omit data needed to compute refunds.

Therefore, validating a design must examine:

- **Structure:** keys, dependencies, normal forms, joins.
- **Rules:** invariants, states, permissions, exceptions, history.
- **Behavior:** create/update/delete/cancel/refund, concurrency, cross-system handoffs.
- **Operations:** auditing, data monitoring, remediation, evolving definitions over time.

## 9. Workflow from Business Language to a Verifiable Model

### Step 1 — Interview Using Scenarios, Not Just Nouns

Instead of asking "should there be an orders table?", ask:

- How many shipments can one order have? Can one shipment carry items from multiple orders?
- Can items be partially shipped, returned, failed in delivery, or redirected after placement?
- When a product name changes, should old invoices show the old name or the new name?
- Can a customer be created without a phone number, or share a phone number with someone else?
- What specifically defines "paid," "delivered," and "completed"?

### Step 2 — Write a Glossary and Record Assumptions Explicitly

A simple entry can follow this format:

~~~text
TERM: Shipment
MEANING: One dispatch of goods to fulfill an order.
GRAIN: (order_id, shipment_no)
CARDINALITY: One Order has 0..n Shipments.
TEMPORAL: shipped_at is the actual dispatch timestamp.
EXCLUDES: Does not imply payment or successful delivery.
OWNER: Fulfillment operations team.
EXCEPTION: Returns and multi-order consolidation are out of scope in this version.
~~~

Unverified assumptions must be flagged explicitly, never silently turned into **NOT NULL** or **UNIQUE**.

### Step 3 — Express Rules as Test Cases

Example:

~~~text
Given: Order O has two lines; line 1 orders 3 units.
When: Ship 2 units in shipment 1 and 1 unit in shipment 2.
Then: System accepts; total shipped = 3.

Given: Total shipped for line 1 is already 3.
When: Another process attempts to ship 1 more unit.
Then: System rejects under the total-quantity invariant.

Given: A shipment belongs to order O1 and a line belongs to order O2.
When: Attempt to allocate O2's line to O1's shipment.
Then: System rejects.

Given: Customer changes contact address today.
When: Viewing history of a shipment dispatched last week.
Then: The shipment's snapshot address remains unchanged.
~~~

### Step 4 — Define Grain, Cardinality, and Candidate Keys

For each entity and relationship, state what one row represents, what uniquely identifies it, and within what scope the key holds. Document **0..1**, **1..n**, **0..n** along with exceptions: claiming "every order has a shipment" is false the moment an order is placed.

### Step 5 — Confirm Dependencies and Normalize

Write valid FDs/MVDs/JDs from verified rules. Only then evaluate 1NF, 2NF, 3NF, BCNF, 4NF, or 5NF as needed. When decomposing, verify **lossless join**, **preservation of meaningful dependencies**, and ability to represent newly valid business states.

### Step 6 — Choose Enforcement Mechanisms for Each Invariant

Map each rule to its mechanism: data type, **CHECK**, **UNIQUE**, **FOREIGN KEY**, transactions, procedures, triggers, authorization, or auditing. Distinguish rules **enforced directly by the database** from rules enforced only in **application code**.

### Step 7 — Test Valid Data and Counterexamples

Do not test only happy-path examples. Create test cases for multiple shipments, multiple prices, missing phone numbers, two customers sharing a phone number, cancellations, concurrent writes, partial deliveries, retired codes, and change history.

### Step 8 — Evaluate Evolution and Read Models

If the business shifts to shipments consolidating multiple orders, **(order_id, shipment_no)** may no longer be a suitable identifier for a physical shipment; consider an independent **shipment_id** and an order–shipment junction table. If opening to multiple sellers, scope SKU keys explicitly. If analytical reporting by delivery date is required, add the right event grain and cutoff rules.

Relational, document, graph, and analytical warehouse models all require **consistent term definitions**:

- **Relational:** strong on keys and referential integrity; requires transaction design for multi-row invariants.
- **Document:** can embed lines inside an order to optimize aggregate operations; still must clarify history and cross-document rules.
- **Graph:** useful when multi-hop traversals dominate; edge names and edge semantics must be defined precisely.
- **Analytical:** facts and dimensions may be denormalized for queries; must define grain, effective timing, and metric formulas.

No storage technology can fix calling two different events by the same ambiguous term.

## 10. Misconceptions That Produce Models That Are "Normalized Yet Wrong"

| Misconception | Consequence | Fix |
| --- | --- | --- |
| "Everything has a primary key, so the model is right." | The key might be blocking a valid business state | Confirm grain, uniqueness scope, and exceptions before setting keys |
| "No order has had two shipments yet, so each order has one shipment." | Cannot record partial deliveries or reshipments | Ask what is possible, not only what appears in current data |
| "Every repeated value requires splitting a table." | Loses historical snapshots or mutates past invoices | Distinguish current values from locked-in values and effective times |
| "A column named **status** is self-explanatory." | Teams update and report using conflicting criteria | Define states, transitions, preconditions, and owners |
| "A valid CHECK guarantees the entire business rule." | Fails to block over-shipping or invalid state transitions | Classify constraints by row, group, history, and transaction |
| "UNIQUE(email) normalizes customers." | Rejects shared emails or buyers without emails even when allowed | Confirm whether email is an identifier, who owns it, and whether it is required or mutable |
| "JOIN works on sample data so the split is always lossless." | Spurious tuples can appear when a different business state occurs | Prove dependencies hold across **all valid states** |
| "Once in BCNF, business testing is unnecessary." | State, timing, permission, and concurrency bugs still remain | Test invariants and behavior, not just normal forms |
| "Choosing a document model eliminates normalization concerns." | Embedded facts can drift out of sync or be misinterpreted | Define sources of truth, lifecycles, and consistency before choosing technology |

**Red flag:** requirements containing words like "always," "unique," "current," "already," "all," "latest," "never," or "every" without scope, exceptions, or timestamps. Those words often conceal a dependency or constraint that needs verification.

## 11. Practice Exercises

### Exercise 1 — Normalized Table with Wrong Cardinality

A design team creates:

~~~sql
CREATE TABLE deliveries_bad (
    order_id VARCHAR(12) PRIMARY KEY,
    delivered_at TIMESTAMPTZ,
    delivered_address TEXT NOT NULL
);
~~~

The team argues the table has a single-column key, no non-key functional dependencies, and satisfies BCNF. Later, Operations reports that one order can be delivered **twice on two different dates to two different addresses**.

**Tasks:**

1. Explain why concluding BCNF (under assumed dependencies) does not prove the model is right.
2. Determine the proper grain and candidate key.
3. Propose a structure supporting multiple shipments per order, including orders with zero shipments yet.
4. State one test case the system must pass.

<details>
<summary>Suggested Solution for Exercise 1</summary>

In the old table, **order_id** is the primary key and can store **at most one delivery record per order**, regardless of which normal form it satisfies under that assumption. The new business rule refutes **order_id → delivered_at, delivered_address** in the delivery relation.

If each shipment belongs to one order, create:

~~~text
orders(order_id, ...)
shipments(
    order_id,
    shipment_no,
    delivered_at,
    ship_to_address_snapshot,
    PRIMARY KEY(order_id, shipment_no),
    FOREIGN KEY(order_id) REFERENCES orders(order_id)
)
~~~

**shipments** has the grain of one shipment of an order. An order can have 0, 1, or many shipment rows. Test: create one order, add two shipments with different dates/addresses, and read back both shipments without overwriting one another or forcing order deletion.

</details>

### Exercise 2 — Defining "Active Customer"

Marketing requests a list of **active customers**. The dev team plans to add **customers.is_active BOOLEAN** and update it manually each month. Sales defines "active" as **placed at least one valid order in the last 90 days**, while Support wants to filter **accounts that are not suspended**.

**Tasks:**

1. Why is a single **is_active** column insufficient for both meanings?
2. Write two distinct glossary definitions, including scope and time semantics.
3. If Marketing wants daily historical counts, what else must you ask before designing?

<details>
<summary>Suggested Solution for Exercise 2</summary>

The two concepts are:

- **account_enabled:** whether the account is currently permitted to log in or transact under lock/unlock rules. This is an account-management state and needs history tracking if past points in time must be queried.
- **purchased_in_last_90_days(as_of):** whether at least one **qualifying valid order** exists with **placed_at** within 90 days prior to **as_of**, under confirmed timezone, boundary, and canceled-order exclusion rules.

To recompute across past dates, you need order placement event data, effective dates of policy rules, and cancellation/adjustment records. A single current **BOOLEAN** cannot reconstruct historical states.

</details>

### Exercise 3 — Valid Foreign Keys, Wrong Total Quantity

Order O1001 has a line ordering **3 units**. Shipment 1 dispatches 2 units, and shipment 2 dispatches 1 unit. Another process attempts to ship 1 more unit in shipment 3.

**Tasks:**

1. Why can **PRIMARY KEY**, **FOREIGN KEY**, and **CHECK(shipped_quantity > 0)** all pass even when total shipped exceeds 3?
2. What business invariant must be protected?
3. Describe one approach to stop two concurrent processes from allocating the last remaining unit simultaneously.

<details>
<summary>Suggested Solution for Exercise 3</summary>

Existing constraints only verify that **each allocation row** has a unique key, valid references, and a positive quantity. They do not sum all shipped quantities for a line to compare against the ordered quantity.

Invariant to protect:

~~~text
SUM(shipped_quantity by order_id and line_no)
  <= ordered_quantity of that exact line
~~~

One approach is for every shipment-allocation write path to run inside a transaction, **lock the corresponding order_lines row**, compute the current sum, and write only if the limit is not exceeded. Ensure all write paths and ordered-quantity edits follow the same protocol; otherwise use database-level constraints/procedures and test concurrent writes.

</details>

### Exercise 4 — Defining "Order Revenue"

A report uses:

~~~text
SUM(order_lines.ordered_quantity * order_lines.unit_price_vnd_at_order)
~~~

and labels it **revenue**. The system has unpaid orders, orders canceled after placement, partial deliveries, and refunds.

**Task:** state at least four questions that must be clarified to know whether the expression above accurately represents **revenue**. Propose a safer name for what it actually calculates.

**Hint:** ask about revenue recognition timing, exclusion rules for canceled/unpaid orders, partial deliveries, returns/refunds, taxes, discounts, shipping fees, and accounting periods. The expression above only reflects **gross ordered merchandise value before further adjustments** at locked-in unit prices; a name like **ordered_merchandise_value_vnd** is clearer than **revenue**. Computing accounting revenue requires recognition rules confirmed by Finance.

## 12. Design Handoff Checklist

Before declaring a schema ready for implementation, designers and business stakeholders should agree on:

| Topic | Minimum Evidence |
| --- | --- |
| Terminology | Glossary, owners, explicitly excluded meanings |
| Grain | Exact statement of "what one row represents" for every table |
| Cardinality | 0..1, 1..n, n..m relationships and exceptions |
| Keys and scope | All candidate keys, uniqueness scoped by org/period/time |
| FDs and normal forms | Confirmed rule set, justified decompositions, lossless checks |
| Time | Current fields, historical snapshots, effective vs. recorded timestamps |
| Invariants | Row-level, group-level, state-machine, and transactional rules |
| Tests | Valid cases, rejected cases, concurrency cases, historical mutation cases |
| Queries/metrics | Formulas, sources, units, timezones, filters, reconciliation |
| Evolution | Requirement change scenarios, migration path, compatibility, rollback |

## 13. Conclusion

**Structural normalization is only sound when dependencies and keys are built from accurate business terms, grain, and rules.** Normal forms reduce redundancy, expose misplaced dependencies, and support verifiable decompositions; they do not decide what counts as a customer, a shipment, a revenue figure, or a completed status.

In the order example, separating **orders**, **order lines**, **shipments**, and **shipment items** enables representing split deliveries, per-shipment addresses, and allocated quantities—capabilities an assumption like "one shipment per order" would block. Even once the model is right, the system still must enforce **total shipped quantities**, **state transition rules**, **key scopes**, **effective timing**, and **concurrent writes**.

A reliable workflow order is: **define terms → confirm invariants and exceptions → establish grain/keys/dependencies → normalize and constrain → test data and behavior → optimize physical structures and read models**. That is the foundation for building relational, document, graph, or analytical models that both evolve cleanly and faithfully reflect the business domain.
