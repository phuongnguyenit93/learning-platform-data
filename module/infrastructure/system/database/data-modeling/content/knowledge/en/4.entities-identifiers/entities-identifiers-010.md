# Identifying a Current Subject and Identifying a Historical Version

A product can change its name, price, description, or category while the store still treats it as the same product. A customer can change their email and phone number while their order history still belongs to the same person. Conversely, if a product is replaced by a different business version or two customer profiles are actually two different people, the system must recognize them as distinct subjects.

To model this accurately, you must distinguish two types of identity:

- **Subject identity:** identifies a business object across its lifecycle, even as its attributes change.
- **Version identity:** identifies a specific state of the subject over a time interval or at a point of recording.

For example, **product_id** identifies a product across its lifecycle; **product_version_id** identifies a specific version of the product's details. When the name or price changes, `product_id` can stay the same while a new `product_version_id` is created.

This distinction is foundational when translating business requirements into a data model. It lets the system answer both "who/what is the current object?" and "at that point in time, what attributes did the object have and what did the system know?".

## 1. Two Different Identification Questions

Let us use an online store as an example.

A product has an SKU, name, description, price, and category. During business operations, the product name may be edited, the price may change, and the product may move to another category. Old orders must still preserve the exact name and price at the time of purchase.

There are two questions:

1. **Which subject is being referred to?** This is the product with a stable identifier, such as Product 501.
2. **Which version of the subject is being referred to?** This is the state of Product 501 effective from 01/10 until before 15/11, with its specific name, price, and category.

One subject can have multiple versions over time:

~~~mermaid
flowchart LR
    P["Product 501<br/>Stable subject identity"] --> V1["Version 1<br/>Name A · 400,000 VND<br/>01/10–14/11"]
    P --> V2["Version 2<br/>Name A Plus · 450,000 VND<br/>15/11–30/11"]
    P --> V3["Version 3<br/>Name A Plus · 470,000 VND<br/>From 01/12"]
~~~

The diagram only illustrates effective periods. In real data, timestamps and values must come from verified business records.

If you only store a single `Product` row and overwrite the name and price on every change, you preserve current information but lose historical states. If you create a new `Product` every time the price changes, you break subject identity: old orders, category links, and reports may treat them as different products.

A versioned model solves both needs by separating stable identity from time-bounded states.

## 2. What Is Subject Identity?

Subject identity is an identifier used to recognize a business object across attribute changes that the business still considers the same object.

Examples:

| Subject | Attribute Change | Subject Identity |
|---|---|---|
| Customer | Changes email or phone number | `customer_id` stays the same if still the same person |
| Product | Edits display name or description | `product_id` stays the same if still the same product |
| Warehouse | Changes name or contact phone number | `warehouse_id` stays the same if still the same location/warehouse |
| Employee | Changes contact address | `employee_id` stays the same if still the same employee |
| Order | Transitions from PENDING to PAID | `order_id` stays the same because it is still the same order |

Subject identity is not a snapshot of attributes. It represents the continuity of the object as defined by the business.

### 2.1. Technical Identifiers and Business Identifiers

A subject often has multiple kinds of identifiers:

- **Technical identifier:** system-generated, such as a numeric `customer_id` or UUID.
- **Business identifier:** a code meaningful to users or external systems, such as SKU, customer code, or order number.
- **External system identifier:** a CRM customer ID, a supplier product code, or a payment gateway transaction ID.

Technical identifiers are usually well suited as internal referencing keys because they can remain stable even when business codes change. Business codes must be governed by uniqueness rules and effective periods if they can change or be reused.

For example, a customer changing their email should not force all orders to update their foreign keys. Orders continue referencing `customer_id`. Old and new emails can be stored in a contact identity history if lookup is needed.

### 2.2. A Code Can Be Unique Without Being a Stable Identity

An email may be unique at a given point in time, yet it can still change or be reassigned to someone else. An SKU may be unique in the current catalog, yet a business might retire and reuse it per policy. Product names are often neither unique nor immutable.

Therefore, distinguish among:

- **Unique:** no two objects share the same code within the defined scope and time.
- **Stable:** the code continues pointing to the exact same subject across permitted changes.
- **Historically durable:** legacy data can still accurately identify the object or code that was effective at that point in time.

A code can satisfy uniqueness without satisfying stability. Do not use an attribute as a long-term referencing key merely because it happens to be unique today.

### 2.3. Uniqueness Scope of an Identifier

An identifier must have an explicit scope:

- An SKU may be unique within one store or across the entire system.
- A customer code may be unique within a tenant, branch, or country.
- A transaction ID may be unique only within one payment provider.
- An invoice number may be unique per fiscal year or issuing legal entity.

For example, the pair `(tenant_id, customer_number)` can be a unique business identifier within a tenant. In a multi-tenant system, enforcing `customer_number` as globally unique may violate business requirements.

Document the scope explicitly in the identification rules before designing keys.

## 3. What Is Version Identity?

Version identity identifies a specific state record of a subject. A subject can have multiple versions; each version carries a set of attributes for an effective interval or a recording timestamp.

For example, Product 501 has three versions:

| product_id | product_version_id | Name | Price | Effective Period |
|---|---|---|---:|---|
| 501 | 9001 | Headphones A | 400,000 | 01/10–14/11 |
| 501 | 9002 | Headphones A Plus | 450,000 | 15/11–30/11 |
| 501 | 9003 | Headphones A Plus | 470,000 | From 01/12 |

In the table:

- **product_id** identifies the subject.
- **product_version_id** identifies a version.
- Multiple rows share the same `product_id` because they belong to the same subject.
- Each `product_version_id` must be unique.
- The effective intervals of versions for the same subject must follow temporal rules, typically non-overlapping.

Version identity allows an order to reference the exact product details that applied at purchase time, rather than mistakenly reading the current version.

### 3.1. When Is Version Identity Needed?

Consider version identity when requirements include:

- Needing to inspect the name, price, address, classification, or terms at a past point in time.
- Needing to know from when to when an attribute was effective.
- Reports needing historical attributes rather than current attributes.
- Data changes needing to be audited.
- A workflow needing to reference the exact version that was approved or used.
- Retroactive data corrections being allowed while still needing to know what the system previously recorded.

You do not need to version every column. Identify which attributes require history and the business rationale. For instance, you may need history for product price and name, while not needing separate versions for a minor internal notes field.

### 3.2. A New Version Is Not a New Subject

Suppose a product changes price from 400,000 to 450,000 VND. If it is still the same product, `product_id` stays the same and a new version is created.

However, if the business changes the essence of the item—for example, Product A is replaced by a new incompatible model with its own SKU and warranty—the business may treat it as a new subject. In that case, create a new `product_id`, optionally linked via a **replaces** or **successor_of** relationship.

The boundary of "same subject" is a business decision. Neither automatically create a version on every change nor automatically keep the same identity if the object's fundamental nature has changed.

## 4. Data Model Separating Subject and Version

A common relational model separates a stable subject table from a version table.

~~~mermaid
erDiagram
    PRODUCT ||--|{ PRODUCT_VERSION : has
    PRODUCT ||--o{ ORDER_ITEM : ordered_as_subject
    PRODUCT_VERSION ||--o{ ORDER_ITEM : purchased_as_version
~~~

The `Product` table holds the stable identity and attributes that truly never change or rarely change. The `ProductVersion` table holds attributes that can change over time.

PostgreSQL schema example:

~~~sql
CREATE TABLE product (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lifecycle_status VARCHAR(20) NOT NULL
        CHECK (lifecycle_status IN ('ACTIVE', 'DISCONTINUED'))
);

CREATE TABLE product_version (
    product_version_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES product(product_id)
        ON DELETE RESTRICT,
    sku VARCHAR(80) NOT NULL,
    name VARCHAR(250) NOT NULL,
    description TEXT,
    current_price NUMERIC(18, 2) NOT NULL
        CHECK (current_price >= 0),
    currency CHAR(3) NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    UNIQUE (product_id, valid_from)
);

CREATE UNIQUE INDEX uq_product_version_current
    ON product_version(product_id)
    WHERE valid_to IS NULL;

CREATE UNIQUE INDEX uq_product_version_sku_current
    ON product_version(sku)
    WHERE valid_to IS NULL;

CREATE INDEX ix_product_version_lookup
    ON product_version(product_id, valid_from DESC);
~~~

This is a baseline example. If SKUs are reused or unique only within a tenant, include that scope in the keys and validation rules. If versions are scheduled in the future, "current" must be defined relative to the current timestamp, not merely by a null `valid_to`. In systems with multiple scheduled versions, query the version effective at the target timestamp.

### 4.1. How to Read the Current Subject

A query fetching current information can retrieve the currently effective version:

~~~sql
SELECT
    p.product_id,
    v.product_version_id,
    v.sku,
    v.name,
    v.current_price,
    v.currency
FROM product AS p
JOIN product_version AS v
    ON v.product_id = p.product_id
WHERE p.product_id = :product_id
  AND v.valid_from <= now()
  AND (v.valid_to IS NULL OR now() < v.valid_to);
~~~

If the system allows only one current version and no future scheduled versions, a partial unique index with `valid_to IS NULL` helps guarantee at most one open version per `product_id`. However, that index alone does not prevent overlapping historical intervals.

### 4.2. How to Find the Version Effective at Purchase Time

~~~sql
SELECT
    product_id,
    product_version_id,
    sku,
    name,
    current_price,
    currency
FROM product_version
WHERE product_id = :product_id
  AND valid_from <= :purchased_at
  AND (valid_to IS NULL OR :purchased_at < valid_to);
~~~

Using a half-open interval `[valid_from, valid_to)` lets two consecutive versions meet at the exact same boundary without double-counting:

- The old version is effective until before 15/11.
- The new version is effective starting on 15/11.

Any given timestamp belongs to at most one interval provided intervals do not overlap.

### 4.3. Ensuring Effective Intervals Do Not Overlap

The `UNIQUE(product_id, valid_from)` constraint only prevents two versions from starting at the exact same timestamp. It does not prevent two intervals from overlapping in duration.

In PostgreSQL, you can use an exclusion constraint with a range:

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE product_version
ADD CONSTRAINT ex_product_version_no_overlap
EXCLUDE USING gist (
    product_id WITH =,
    tstzrange(valid_from, valid_to, '[)') WITH &&
);
~~~

This constraint prevents two effective intervals of the same `product_id` from intersecting. On other DBMSs, use an equivalent mechanism such as locked transactions, triggers, or atomic validation workflows.

Do not rely solely on an application-layer "check no overlapping record exists before insert" without database locks or constraints. Two concurrent transactions can both observe no conflict and both write overlapping intervals.

## 5. Distinguishing Valid Time and Recorded Time

A key nuance in historical data is that "when did the fact take effect?" and "when did the system learn or record it?" can differ.

- **Valid time:** the time interval during which the fact is true in the business world.
- **Transaction time / system time:** the time interval during which the data is stored and regarded by the system as known information.

For example, on 20/11, staff discover that a product price took effect on 15/11, but the record was entered with the wrong price. The correct price has been effective since 15/11; the system only recorded the correction on 20/11.

If you only store `valid_from` and `valid_to` and overwrite the record, you know the true historical price, yet you lose track of the fact that the system believed the wrong price between the 15th and the 20th. If auditing both perspectives is required, store two time axes.

### 5.1. Bitemporal Model

A bitemporal table can include:

- **valid_from, valid_to:** the interval during which the data is effective in the business.
- **recorded_from, recorded_to:** the interval during which the system stored that version of knowledge.

Example data:

| product_id | Price | Valid time | Recorded time |
|---|---:|---|---|
| 501 | 450,000 | From 15/11 | 15/11–20/11 |
| 501 | 430,000 | From 15/11 | From 20/11 |

The first record represents what the system had recorded before the correction. The second record represents what the system knew after the retroactive correction. Both describe the same business effective period, yet belong to two different recording intervals.

Conceptual schema:

~~~sql
CREATE TABLE product_version_history (
    version_record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES product(product_id),
    name VARCHAR(250) NOT NULL,
    current_price NUMERIC(18, 2) NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    recorded_from TIMESTAMPTZ NOT NULL,
    recorded_to TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CHECK (recorded_to IS NULL OR recorded_to > recorded_from)
);
~~~

This is an illustrative structure; guaranteeing non-overlap across both dimensions requires appropriate constraints and transaction rules. Bitemporality is useful for auditing, retroactive prices/terms, compliance data, and reports that must reconstruct what the system knew at a given time.

### 5.2. Two Questions That Bitemporality Answers

- "Which price was effective on 16/11 according to today's corrected data?" → filter by valid time, using current system knowledge.
- "On 18/11, which price did the system have recorded for 16/11?" → filter by valid time and recorded time as of 18/11.

If the business does not need the second question, storing a single time axis is usually simpler. Do not adopt bitemporality merely because it looks comprehensive; use it when you must separate the history of business facts from the history of system knowledge.

## 6. Linking Current and Historical Data Properly

When designing relationships between tables, clarify whether the referencing side intends to point to the subject or to a specific version.

### 6.1. Referencing the Subject

An order can reference `product_id` to answer "which product did this order purchase?". This relationship is suitable when aggregating revenue by product subject across versions.

However, if you only reference `product_id` and then read the name and price from the current version, old invoices can change along with the catalog. That is a historical data bug.

### 6.2. Referencing the Version

If an order must know the exact catalog version applied at purchase time, `OrderItem` can store both `product_id` and `product_version_id`:

~~~sql
CREATE TABLE order_item (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL REFERENCES product(product_id),
    product_version_id BIGINT NOT NULL
        REFERENCES product_version(product_version_id),
    sku_snapshot VARCHAR(80) NOT NULL,
    name_snapshot VARCHAR(250) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(18, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Here:

- `product_id` supports aggregation by product subject.
- `product_version_id` identifies the version used.
- `sku_snapshot`, `name_snapshot`, and `unit_price` store the commercial facts finalized on the order.

You can reduce snapshot columns if version records are immutable and retained permanently. Still, for commercial documents, storing finalized values directly on the line item helps protect transaction contents against catalog edits or migrations.

### 6.3. When Is Only a Snapshot Needed?

If the goal is to reproduce invoices, the name, SKU, unit price, tax, and shipping address at order placement time can be captured directly on `Order` and `OrderItem`. You do not necessarily need a full versioned model for every entity.

A snapshot is appropriate when:

- You only need to preserve the facts used in a single transaction.
- You do not need to query the subject's full version history.
- Snapshot data has a lifecycle tied to the document.
- You do not need to know intermediate values that were effective between two transactions.

A version table is appropriate when you need version lookup, effective intervals, reporting by historical attributes, or reusing versions across multiple workflows.

Both approaches can coexist: the version table serves as catalog history, while snapshots on `OrderItem` preserve finalized commercial facts.

## 7. Attribute Change or Identity Change?

This is the most important decision when modeling versions.

| Scenario | Keep `subject_id`? | Create New Version? | Explanation |
|---|---|---|---|
| Customer changes email | Yes | Yes if email history is needed | Still the same customer |
| Customer changes phone number | Yes | Yes if contact history is needed | Person identity unchanged |
| Product edits description | Yes | Yes if old description must be queried | Same product |
| Product changes price | Yes | Yes if price history is needed | Same product, time-bounded price |
| Product moves category | Yes | Yes or version the `ProductCategory` relation | Subject stays the same, classification changes |
| New replacement product with different specs | Usually no | New subject | Needs a new identifier and optional replacement link |
| Two duplicate customer profiles of the same person | Keep one canonical identity, store mapping | May update profile history | Needs an audited merge workflow |
| One customer profile actually represents two people | Split into two identities | Do not merely create two versions | This is fixing subject identification, not editing attributes |

### 7.1. Merging Two Duplicate Identities

Suppose the system created Customer 101 and Customer 205 and later verified they are the same person. You should not delete one ID and rewrite all historical data without leaving a trail.

A merge workflow can:

1. Select the canonical identity (`canonical customer`).
2. Record the old identity as an alias/merged identity of the canonical identity.
3. Store the timestamp, reason, and approver of the merge.
4. Migrate current references through a controlled process.
5. Keep a mapping to resolve legacy data or old IDs from integrated systems.
6. Verify orders, payments, and access permissions after the merge.

This can be modeled with a `CustomerIdentityLink` table containing `source_customer_id`, `canonical_customer_id`, `relation_type`, `effective_at`, and `reason`. Prevent merge cycles and explicitly define whether multi-hop merges are allowed.

### 7.2. Splitting a Mistakenly Merged Identity

If one profile actually represents two different people, merely creating two historical versions is wrong: two people are not two states of the same person. You must create two separate subject identities and reallocate facts based on business evidence.

Historical reallocation must be audited. Not every order can be automatically attributed to the right person. Ambiguous records must be flagged for reconciliation rather than assigned by guesswork.

### 7.3. External Identifiers and Aliases

When integrating CRM, ERP, suppliers, or payment gateways, one subject can hold multiple IDs across different systems. Separate external codes into source-attributed identifier records:

| subject_id | source_system | external_id | valid_from | valid_to |
|---|---|---|---|---|
| 501 | ERP | ERP-P-778 | 01/01 | null |
| 501 | Marketplace | MP-991 | 01/03 | null |
| 501 | LegacyCatalog | OLD-77 | 01/01 | 30/06 |

The unique key is typically `(source_system, external_id)` within the valid time interval governed by the source system's rules. Never assume external codes are globally unique or never reused.

## 8. Common Versioning Strategies

### 8.1. Overwrite (Type 1)

When an attribute changes, update the current record directly. No history of old values is kept.

Appropriate when:

- Old values no longer have business meaning.
- Fixing typos or data errors.
- Reports only require the current state.

Unsuitable when transaction-time reconstruction or auditing is required.

### 8.2. Store a New Version (Type 2)

When a tracked attribute changes, close the old version's effective interval and insert a new version. Subject identity stays the same.

Example:

1. The old version gets `valid_to` set to the change timestamp.
2. The new version gets `valid_from` set to that timestamp and `valid_to` set to null.
3. Point-in-time queries select the appropriate version.

This is the standard pattern for attribute history in analytical data models (Slowly Changing Dimension Type 2) and can also be applied in transactional systems when version history is required.

### 8.3. Store Previous and Current Values (Type 3)

Keep one or a few prior values in dedicated columns, such as `previous_region` and `current_region`. This fits only when the number of retained versions is very small and query rules are clear. It cannot substitute for unbounded history.

### 8.4. Store All Change Events

Instead of storing only version states, the system records events such as `ProductRenamed`, `PriceChanged`, and `CategoryAssigned`. State can be reconstructed from events if event sourcing is applied.

This preserves causes and the sequence of changes, yet requires handling ordering, duplicate events, schema versioning, and replay capability. Do not choose event sourcing merely to track name or price history if a simple version table already satisfies the requirements.

| Strategy | Preserves Subject Identity | Preserves History | Complexity | Best Fit |
|---|---|---|---|---|
| Type 1 | Yes | No | Low | Attributes not needing history |
| Type 2 | Yes | Yes, by version | Medium | Point-in-time state queries |
| Type 3 | Yes | Limited | Low to medium | Only a few prior/current values needed |
| Event log/event sourcing | Yes, if designed properly | By event stream | Higher | Action history and replay needed |

## 9. Version Identity in Analytical Models

In data warehouses, dimensions often need attribute history. Slowly Changing Dimension Type 2 is the common approach:

- Each dimension row has its own surrogate key called a version key.
- Multiple dimension rows share the same business key/subject key.
- Each row has effective start/end timestamps and a current flag or rule to identify the current version.
- Fact tables store the version key effective at the time the event occurred.

Example:

| product_sk | product_id (business key) | Name | Category | Effective Period |
|---|---|---|---|---|
| 1001 | 501 | Headphones A | Audio | 01/10–14/11 |
| 1002 | 501 | Headphones A Plus | Premium Audio | From 15/11 |

`FactSales` for an order placed on 10/11 references `product_sk` 1001. `FactSales` for an order placed on 18/11 references `product_sk` 1002. When aggregating by historical name or category, revenue is not misattributed to current attributes.

Distinguish among:

- **product_id** in transactional sources identifies the subject.
- **product_sk** in the dimension identifies the dimension version.
- **order_item_id** or the fact key identifies the transaction event/line item.

If a fact table only stores `product_id` and joins to the current dimension version, historical reports can shift whenever the dimension updates.

## 10. Rules to Protect

A versioned model requires more rules than simply adding a `version_id` column.

| Rule | How to Verify or Enforce |
|---|---|
| Every subject has a stable identifier | Primary key on the subject table |
| Every version has its own identifier | Primary key on the version table |
| Version belongs to the right subject | Foreign key from version to subject |
| Valid time interval | `CHECK valid_to > valid_from` |
| Versions do not overlap | Exclusion constraint or equivalent transaction/trigger |
| Only one current version per rule | Partial unique index or equivalent constraint |
| Business code unique within proper scope | `UNIQUE` per tenant/source and matching effective interval |
| Historical transaction data stays immutable | Reference version and/or store snapshot |
| Retroactive corrections are auditable | Bitemporal or audit history |
| Subject merges/splits leave an audit trail | Identity mapping and approval workflow |

Not all rules can be expressed with a single `CHECK` constraint. Rules spanning multiple rows, multiple intervals, or multiple tables require transactions, exclusion constraints, triggers, or concurrency-safe application logic.

## 11. Common Design Mistakes

### Mistake 1: Using Email as the Customer Primary Key

When a customer changes their email, every referencing table is forced to update. If the email is reused, historical data may get attached to the wrong person.

Fix: use a stable `customer_id` as the subject identifier; treat email as a mutable contact identifier that can carry history and verification status.

### Mistake 2: Creating a New Subject on Every Attribute Change

Creating a new `product_id` every time a product changes price fragments revenue per product and forces related records to migrate.

Fix: keep `product_id` for the same subject and create a new `product_version_id` for the new state if history is needed.

### Mistake 3: Overwriting Old Versions

Updating the current record in place makes it impossible to report the name, price, or classification on the transaction date.

Fix: close the effective period of the old version and insert a new version; or store snapshots on the transaction if only finalized facts are needed.

### Mistake 4: Storing `version_id` Without `subject_id`

Grouping versions of the same subject becomes unclear, and business tables lack a stable identifier to reference. Although the subject can be derived via the version table, storing subject identity explicitly usually makes the model clearer.

### Mistake 5: Allowing Two Current Versions to Coexist

Without constraints, one subject can end up with two versions both considered current. Queries may return two rows and pick one arbitrarily.

Fix: define "current" unambiguously, add an appropriate unique constraint, and enforce non-overlapping effective intervals.

### Mistake 6: Storing Only Recorded Time Without Valid Time

Late-arriving data or retroactive corrections distort business history.

Fix: separate valid time and recorded time whenever the business needs both perspectives.

### Mistake 7: Confusing Events with Versions

An event such as `PaymentCaptured` records a single occurrence. A `Payment` version records transaction state over a period. An event may trigger creating a new version, yet the two concepts do not replace each other.

Fix: use an event log to record what happened; use a version table to record time-effective states; combine them only when clearly required.

## 12. Process for Choosing Identifiers and History Strategies

When designing an entity with changing attributes, follow these steps:

1. **Define the subject:** write down clearly what counts as the same object over time.
2. **Choose a stable identifier:** prefer a technical key free of volatile business meaning; document its uniqueness scope.
3. **List mutable attributes:** classify which attributes need history, do not need history, or only need snapshots.
4. **Identify temporal needs:** do you only need to know when a value was effective, or also when the system recorded it?
5. **Select a strategy:** Type 1, Type 2, Type 3, event history, or snapshots based on query requirements.
6. **Design version identity:** `version_id` or a composite key of `subject_id` plus start timestamp; enforce uniqueness rules.
7. **Define relationships:** specify whether business tables reference the subject, the version, or both.
8. **Protect intervals:** prevent unintended overlapping versions or gaps in effective intervals.
9. **Handle identity merges/splits:** include aliases, mappings, approvals, and traceability.
10. **Verify with historical queries:** test querying current state, state on date X, and what the system knew on date Y.

## 13. Self-Check Exercises

### Exercise 1: Customer Changes Email

A customer changes their email on 10/05. Orders from March must still belong to the same customer, and reports must be able to find the email used at order placement.

Determine:

- Which subject identifier must remain unchanged?
- Is email a current attribute or a contact identifier with history?
- Do orders need an email snapshot?
- Are valid time or recorded time needed?

Hint: `customer_id` stays unchanged. Email can be stored in a contact history table if you need to know which email was effective at order time. An email snapshot on the order is only needed if documents or audit requirements demand the exact value used at that moment.

### Exercise 2: Product Changes Price and Name

Product P is named "Keyboard K" with a price of 700,000 VND. On 01/06 it is renamed to "Keyboard K Pro", and on 10/06 the price rises to 750,000 VND. An order on 05/06 must display the old name and the 700,000 VND price.

Determine:

- Does P keep the same `product_id`?
- How many versions need to be created?
- Does the 05/06 order reference the subject or a version?
- Are name and price snapshots needed on `OrderItem`?

Hint: if it is still the same product, `product_id` stays unchanged. New versions can be created on 01/06 and 10/06. The order references the version effective on 05/06 and stores the finalized values on the order line item.

### Exercise 3: Two Duplicate Customer Profiles

CRM has Customer 100 and Customer 200. After verification, both are the same person. Several orders already reference each ID.

Determine:

- How is the canonical identity chosen?
- Should the other ID be deleted?
- How are reference history and external IDs preserved?
- If it is later discovered the two profiles are two different people, how should it be handled?

Hint: create an identity mapping, record the merge reason and timestamp, and keep the alias. If the determination was wrong and they are actually two people, split them into two subject identities and reconcile each historical relationship.

### Exercise 4: Retroactive Data Correction

On 20/08, staff discover that the correct tax rate took effect on 01/08, yet the system had recorded the wrong rate until 20/08. The audit team needs to know both the tax rate effective during August and the tax rate the system had recorded on 10/08.

Determine whether bitemporality is needed and why.

Hint: yes. Valid time represents effectiveness from 01/08; recorded time shows the system only recorded the correction on 20/08. The two time axes answer two different questions.

### End-of-Lesson Review Questions

- Does the subject have a stable identifier across permitted changes?
- Can business codes change, be reused, or be unique only within a specific scope?
- Does an attribute change actually create a new subject?
- Does each version have its own identifier and link back to the right subject?
- Can version effective intervals overlap?
- Is there a need to distinguish valid time from recorded time?
- Do historical transactions reference a version or store which snapshots?
- Are subject merges/splits traceable and reconcilable?
- Can reporting queries accurately reconstruct attributes as of event occurrence time?

A good data model preserves a subject's identity as the object changes while identifying each version when the business needs history. Subject identity answers "which same object is this?", whereas version identity answers "which specific state of the object is this?". When these two questions are cleanly separated, the system can support current operations, historical documents, point-in-time reporting, and auditing without breaking business links.
