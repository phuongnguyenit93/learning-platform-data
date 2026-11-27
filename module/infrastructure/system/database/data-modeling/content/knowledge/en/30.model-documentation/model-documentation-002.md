# Data Dictionary for Tables, Fields, Types, Units, and Value Domains

## 1. What Problem Does a Data Dictionary Solve?

Looking at an `orders` table, a developer might guess that `total_amount` is the order total, `status` is the status, and `created_at` is the creation timestamp. Yet column names alone cannot determine:

- Is `total_amount` the order value before or after discounts, does it include taxes/shipping, and in which currency unit is it expressed?
- Does `status = 'PAID'` mean a payment request was sent or that the provider confirmed collection?
- Is `created_at` the time the customer placed the order, the time the server received the request, or the time the row was inserted into the database?
- Is `customer_id` a customer key within one tenant, within one source system, or across the entire platform?
- Does `NULL` in `delivered_at` mean not yet delivered, not applicable, not yet received, or deleted?
- An order has multiple product lines; does joining payments multiply revenue?

A **data dictionary** is a structured document defining **data objects and each attribute**: name, business meaning, storage location, type, unit, value domain, keys, relationships, missing-data rules, authoritative source, time semantics, and required checks.

The goal is not merely listing `VARCHAR` or `BIGINT` types. The goal is to help someone **who did not author the schema** understand the data accurately enough to:

1. Design tables, keys, constraints, and indexes without guessing requirements.
2. Write APIs, queries, reports, and integration pipelines with identical semantics.
3. Validate a value for **both technical and business** correctness.
4. Know what must remain invariant when changing schemas or data sources.
5. Distinguish current values, historical values, derived data, and confirmed events.
6. Trace bad data back to its owner, source, and transformation rules.

The running example is a multi-tenant sales platform. We will build a dictionary for `sales_order`, `sales_order_line`, and `payment_movement`, from business requirements to the logical model, PostgreSQL, and verification rules.

## 2. Distinguishing Data Dictionary from ERD, Business Glossary, Catalog, and DDL

These documents complement one another rather than replacing each other completely.

| Tool/Document | Question It Answers Well | What It Usually Does Not Answer on Its Own |
| --- | --- | --- |
| **Business glossary** | What do "placed order," "revenue," and "active customer" mean? | Which physical column stores the data, its DB type, and exact FK. |
| **ERD / relational model** | Which entities have 1:N, N:N relationships? Where are primary and foreign keys? | Currency units, recognition cutoff conditions, NULL semantics, and authoritative source. |
| **Data dictionary** | What are each table/field's grain, type, meaning, domain, unit, and rules? | Cannot automatically enforce every rule unless wired to code/DB. |
| **DDL/schema** | How does the database declare columns, types, PK/FK/CHECK/INDEX? | Why the column exists, which values constitute business proof, and history mutation rules. |
| **Metadata catalog** | Where does a dataset live, who uses it, when was it updated, what are its lineage and permissions? | Does not guarantee every field has accurate business definitions if metadata lacks governance. |
| **Data contract** | What does the producer guarantee consumers regarding schema, semantics, quality, and changes? | May describe only a published interface without covering the entire internal model. |

**The right relationship:** the glossary defines terms; the ERD shows relationships; the dictionary binds semantics to entities/fields; the DDL enforces part of the constraints; the catalog enables discovery and governance; the contract specifies commitments between provider and consumer.

A dictionary auto-generated from `information_schema.columns` only knows names, types, `nullable`, and a few physical properties. It **does not know** that `total_minor` means "booked order value" rather than "actual cash collected." Metadata verified by an accountable owner must be added.

## 3. Start from Grain and Source of Truth, Not a Column List

**Grain** is the exact statement of "what a single row represents." Without grain, a dictionary easily degrades into a disconnected list of columns.

For the example system:

| Dataset | Grain: One Row Represents… | Authoritative Source |
| --- | --- | --- |
| `sales_order` | One accepted sales order keyed by `(tenant_id, order_id)`. | Ordering. |
| `sales_order_line` | One product line `line_no` of a specific order. | Ordering. |
| `payment_movement` | One capture or refund transaction recorded by Payment **as confirmed** by the payment source. | Payment. |
| `catalog_product` | One product published by Catalog within a tenant. | Catalog. |
| `daily_sales_mart` | One day, one tenant, one currency, one channel per approved metric definitions. | Analytics; derived data from owners. |

Only from the grain do you determine:

- **Business key:** a business identifier such as `order_id` within a tenant scope.
- **Primary key:** the DB key enforcing row uniqueness.
- **Foreign key / external reference:** how rows link to other rows or entities.
- **Descriptive attributes** and **measures** at that exact grain.
- **Value domains, units, and timestamps** associated with each attribute.
- **Cases that are mandatory or allowed to be missing**.

For instance, `payment_movement` can have **multiple rows per order** because an order may be captured multiple times or partially refunded. If the dictionary merely writes "order payment info" without clarifying that one row is *one monetary movement*, report authors can easily JOIN `order_line` and `payment_movement` on order and multiply totals.

### Owner Is Not Synonymous with Storage Location

`customer_id` may appear in Ordering to record who placed the order, while Customer Identity owns the customer profile. Ordering is permitted to hold an **external reference** and order-time snapshot data; having a `customer_id` column does not authorize Ordering to edit the customer's email.

The dictionary should explicitly mark each fact as **authoritative**, **captured snapshot**, or **derived projection**.

## 4. Data Dictionary Structure: System, Table, and Column Levels

A usable dictionary requires at least three levels.

### Model/Dataset Level

| Metadata | How to Populate |
| --- | --- |
| Model/dataset ID | `SALES_ORDER_V1`; stable code distinct from display name. |
| Purpose | Supports recording placed orders and analyzing order value. |
| Bounded context/owner | Ordering, definition approver. |
| Storage & environment | PostgreSQL, schema `ordering`; avoid recording secrets. |
| Tenant/region scope | Tenant key, access policies, and data residency. |
| Data source | Accepted order-placement commands, not cache status. |
| Refresh/latency | Direct in OLTP or ETL latency with an SLO. |
| Contract version | `v1`, effective date, and links to ADR/migrations. |
| Data policy | Classification, permissions, retention, deletion/anonymization, backup. |

### Table/Collection Level

Each table entry should record:

- Logical and physical names, business description.
- **Grain** and the set of entities in scope.
- PK, candidate/business keys, unique constraints.
- Relationships, cardinality, and orphan/cascade rules.
- Write owner, authoritative source, source/derived classification.
- INSERT/UPDATE/DELETE rules, immutable vs. mutable state.
- Partition key, read/write patterns, indexes serving workloads.
- Sensitivity classification, retention period, and downstream sync paths.

### Column/Field Level

Each entry needs at minimum:

| Metadata Attribute | Explanation and Example |
| --- | --- |
| `column_name` | `order_total_minor`, stable physical name within the schema version. |
| `business_term` | "Booked order value"; linked to glossary. |
| `definition` | After line-level discounts; before actual refunds. |
| `data_type` | PostgreSQL `BIGINT`. |
| `nullable` and `null_meaning` | `NOT NULL` or categorized reasons why NULL is permitted. |
| `unit` and `scale` | Smallest unit of the corresponding `currency_code`. |
| `domain` | Integer >= 0; domain is versioned when changed. |
| `default` | Whether present; used only when default value is business-valid. |
| `key_role` | PK/FK/business key/non-key. |
| `source_authority` | Ordering at the time of order acceptance. |
| `derivation` | If computed from other sources: formula, rounding, and rule version. |
| `temporal_meaning` | When the value takes effect/locks, whether corrections are allowed. |
| `classification` | Public/internal/PII/financial and required permissions. |
| `quality_rules` | CHECKs, SQL tests, reconciliation checks, and SLOs. |
| `change_policy` | Rename, deprecation, compatibility rules, approver. |

Not every cell requires a long paragraph, but **cells that determine correctness**—such as grain, unit, domain, NULL, and source authority—must have unambiguous meanings. Marking "TBD" with an accountable owner to resolve it is far better than inventing information.

## 5. Business Model Example: Orders and Capture/Refund Transactions

Business requirements:

1. A tenant has many orders; an order has at least one product line when accepted.
2. Each line stores the quantity and price **locked** at order placement.
3. Order value is calculated per ordering rules; it is **distinct from** the amount collected by the provider.
4. An order may have multiple captures/refunds; only confirmed transactions count.
5. Never add amounts across different currencies, and never collapse multiple monetary movements into one order row.
6. Reports need both current order status and payment movement history.

~~~mermaid
erDiagram
    SALES_ORDER ||--|{ SALES_ORDER_LINE : contains
    SALES_ORDER ||--o{ PAYMENT_MOVEMENT : related_to
    SALES_ORDER {
        uuid tenant_id PK
        uuid order_id PK
        uuid customer_id
        timestamptz placed_at
        varchar order_status
        bigint booked_total_minor
        char currency_code
    }
    SALES_ORDER_LINE {
        uuid tenant_id PK
        uuid order_id PK
        integer line_no PK
        uuid product_id
        numeric quantity
        bigint agreed_unit_price_minor
        bigint line_net_minor
    }
    PAYMENT_MOVEMENT {
        uuid tenant_id PK
        uuid movement_id PK
        uuid order_id FK
        varchar movement_type
        bigint amount_minor
        char currency_code
        timestamptz confirmed_at
    }
~~~

The diagram depicts **logical relationships**; `customer_id` and `product_id` may be references to other owners and do not necessarily have cross-database FKs. An order line might undergo post-order adjustments or cancellations; if the business requires line change history, additional events/audits/history tables are needed.

### Time Rules

- `placed_at`: when Ordering accepts the order per the cutoff definition, not when written to the warehouse.
- `confirmed_at` on movement: when Payment recognizes a capture/refund confirmed by the provider.
- `recorded_at`: when Payment writes the movement record; may be later than `confirmed_at`.
- `created_at` in OLTP: when the DBMS creates the row; must not blindly substitute for `placed_at`.

Callback messages can arrive late or duplicate; the dictionary must specify how a single transaction is deduplicated rather than equating "callback count" with collection count.

## 6. PostgreSQL Schema Example to Cross-Reference the Dictionary

This is an **illustrative schema**, not a full accounting model. It focuses on columns the dictionary must explain.

~~~sql
CREATE SCHEMA IF NOT EXISTS ordering;

CREATE TABLE ordering.sales_order (
    tenant_id           UUID NOT NULL,
    order_id            UUID NOT NULL,
    customer_id         UUID NOT NULL,
    placed_at           TIMESTAMPTZ NOT NULL,
    order_status        VARCHAR(20) NOT NULL
                        CHECK (order_status IN
                          ('PLACED', 'CANCELLED', 'FULFILLED')),
    booked_total_minor  BIGINT NOT NULL
                        CHECK (booked_total_minor >= 0),
    currency_code       CHAR(3) NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, order_id)
);

CREATE INDEX ix_order_tenant_placed
    ON ordering.sales_order (tenant_id, placed_at DESC);

CREATE TABLE ordering.sales_order_line (
    tenant_id              UUID NOT NULL,
    order_id               UUID NOT NULL,
    line_no                INTEGER NOT NULL CHECK (line_no > 0),
    product_id             UUID NOT NULL,
    quantity               NUMERIC(18, 3) NOT NULL
                           CHECK (quantity > 0),
    agreed_unit_price_minor BIGINT NOT NULL
                           CHECK (agreed_unit_price_minor >= 0),
    line_net_minor         BIGINT NOT NULL
                           CHECK (line_net_minor >= 0),
    PRIMARY KEY (tenant_id, order_id, line_no),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.sales_order (tenant_id, order_id)
);

CREATE TABLE ordering.payment_movement (
    tenant_id           UUID NOT NULL,
    movement_id         UUID NOT NULL,
    order_id            UUID NOT NULL,
    provider_name       VARCHAR(50) NOT NULL,
    provider_reference  VARCHAR(120) NOT NULL,
    movement_type       VARCHAR(10) NOT NULL
                        CHECK (movement_type IN ('CAPTURE', 'REFUND')),
    amount_minor        BIGINT NOT NULL CHECK (amount_minor > 0),
    currency_code       CHAR(3) NOT NULL,
    confirmed_at        TIMESTAMPTZ NOT NULL,
    recorded_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, movement_id),
    UNIQUE (tenant_id, provider_name, provider_reference),
    FOREIGN KEY (tenant_id, order_id)
        REFERENCES ordering.sales_order (tenant_id, order_id)
);

CREATE INDEX ix_payment_order_confirmed
    ON ordering.payment_movement
       (tenant_id, order_id, confirmed_at DESC);
~~~

**Conditions for reading this DDL accurately:**

- `order_status` describes the **order** lifecycle, not a substitute for `payment_movement`. The CHECK list does not prevent a `FULFILLED -> PLACED` transition; the transaction/domain state machine must enforce it.
- `booked_total_minor` is the order value locked per Ordering rules; assuming **order discounts deducted**, **refunds not deducted**, and tax/shipping handled per separate policy. In this example, the sum formula is not expressed as a CHECK because it may involve multiple independent charges.
- `agreed_unit_price_minor` is the price **per standard quantity unit**; `quantity` allows fractional decimals, requiring a rounding rule before producing integer `line_net_minor`. Do not multiply and cast arbitrarily.
- `currency_code` is the currency code of the corresponding amount, yet `CHAR(3)` **does not prove** the code is valid or that two tables share the same currency. A currency catalog and conversion policy are required.
- `UNIQUE (tenant_id, provider_name, provider_reference)` holds only if the provider guarantees unique references within that scope per movement. If references are only unique per merchant account or operation type, include that exact namespace in the key.
- `customer_id` and `product_id` are external references if Customer/Catalog are owned by other databases; do not create fake cross-service FKs.
- Foreign keys among the three co-owned tables are enforced by the DBMS per tenant; do not casually apply `ON DELETE CASCADE` since transaction records have independent retention.

The dictionary is where **why** each decision exists and how to verify it are explained, whereas DDL only enforces part of it.

## 7. Table-Level Dictionary Template Ready for Projects

Example table entry for `ordering.sales_order`:

| Item | Dictionary Content |
| --- | --- |
| **Dataset ID** | `ordering.sales_order.v1`. |
| **Business name** | Accepted sales order. |
| **Description** | Booked order entity; holds order state and booked value, not provider cash flow. |
| **Grain** | One row per `(tenant_id, order_id)`. |
| **Owner and writer** | Ordering; only the Order workflow may update order status. |
| **PK / business key** | PK `(tenant_id, order_id)`; `order_id` stable within tenant. |
| **Relationships** | 1:N with `sales_order_line`; 1:N with `payment_movement`. |
| **Temporal contract** | `placed_at` is order acceptance time; `created_at` is row write time. |
| **Statuses** | `PLACED`, `CANCELLED`, `FULFILLED`; transitions governed by a separate state machine. |
| **Update policy** | Status may change; ID and acceptance timestamp must not change arbitrarily. |
| **Delete policy** | Do not physically delete simply because an order is cancelled; retain per record policy. |
| **Classification** | Internal/financial; `customer_id` is an identifier linkable to a natural person. |
| **Typical queries** | Lookup order by PK; list by tenant and `placed_at`. |
| **Quality checks** | Unique PK; non-missing currency; non-negative total; reconcile order lines at same cutoff. |

A table dictionary must have **a single grain**. If the team does not agree on what one row represents, do not begin designing derived monetary columns yet.

### Relationship-Level Dictionary

Include a relationship table instead of merely naming FKs:

| Relationship | Cardinality | Optionality | Lifecycle Rules |
| --- | --- | --- | --- |
| Order → OrderLine | An Order has 1..N lines once booked. | At least one line is a **business invariant**, not enforced by a one-way FK alone. | Do not delete historical lines when Catalog deletes a product. |
| Order → PaymentMovement | An Order has 0..N movements. | May have zero confirmed payments. | Movements have independent retention and audit. |
| Order → CustomerIdentity | Order references one customer per contract. | Key non-null at booking. | Deactivating a customer must not erase historical orders. |
| OrderLine → CatalogProduct | Line stores product ID and locked price. | ID must be validated per contract at placement. | Current Catalog price must never overwrite locked price. |

## 8. Column-Level Dictionary Template: A Complete Example

The following table covers `ordering.sales_order`. Rows here are **a summary**; production systems should also store linkable owners, sources, and quality rules.

| Column | Physical Type | NULL | Unit/Domain | Definition and Constraints |
| --- | --- | --- | --- | --- |
| `tenant_id` | `UUID` | No | Namespaced tenant ID. | PK component; all queries/reconciliations must stay within the right tenant. |
| `order_id` | `UUID` | No | Stable order ID within tenant. | PK component; never reused for another order. |
| `customer_id` | `UUID` | No | External customer reference. | CustomerIdentity ID at placement; not email or customer name. |
| `placed_at` | `TIMESTAMPTZ` | No | Absolute instant. | When Ordering accepted placement; used for event-time grouping where appropriate. |
| `order_status` | `VARCHAR(20)` | No | `PLACED/CANCELLED/FULFILLED`. | Order lifecycle; does not imply captured or refunded. |
| `booked_total_minor` | `BIGINT` | No | Smallest unit of `currency_code`; ≥ 0. | Total booked order value per rules, before deducting refunds. |
| `currency_code` | `CHAR(3)` | No | Approved currency code. | All monetary sums must group/convert by currency. |
| `created_at` | `TIMESTAMPTZ` | No | Row storage timestamp. | Technical metadata; must not default to customer placement time. |

Each definition should also explain **when not to use the column**. For example, `booked_total_minor` may be used for "booked sales" per policy, but **must not** be used as "net cash received" without reconciling movements.

### Order Line Table

| Column | Domain and Unit | Meaning |
| --- | --- | --- |
| `line_no` | Positive integer, unique within order. | Line sequence number; immutable once order is booked. |
| `product_id` | Tenant-scoped product reference. | Product ordered at cutoff, distinct from current Catalog name. |
| `quantity` | `NUMERIC(18,3)`; unit from product contract. | Ordered units; `1.500` may mean 1.5 kg, not 1.5 pieces. |
| `agreed_unit_price_minor` | Minor currency **per standard quantity unit**. | Agreed unit price, not auto-updated with Catalog. |
| `line_net_minor` | Minor unit of Order's currency. | Line amount after locked discount/rounding policy. |

If items include both `kg` and `piece`, there must be a per-product unit rule or a `unit_code` column on the line. A `quantity` column lacking a unit/scale contract renders aggregates meaningless even when the DB type is valid.

## 9. Choosing Data Types: Physically Valid Is Not Enough—It Must Match the Business Domain

| Category | Common Types | Dictionary Rules to Record |
| --- | --- | --- |
| Identifiers | `UUID`, `BIGINT`, `VARCHAR` | Namespace, stability, ID generation method, whether reuse is allowed. |
| Integer counts | `INTEGER`/`BIGINT` | Can it be negative? Upper bound? Can counters reset? |
| Decimals | `NUMERIC(p,s)` / `DECIMAL` | Precision, scale, rounding, physical unit, can it be negative? |
| Money | `BIGINT` minor units or `NUMERIC` | Currency, minor-unit convention, FX rates, and rounding. |
| Text | `TEXT`/`VARCHAR(n)` | Definition, Unicode normalization, realistic length, sensitivity. |
| Boolean | `BOOLEAN` | Are two states sufficient? What does NULL mean if allowed? |
| Enum/code | `VARCHAR` + CHECK or reference table | Code list, meanings, deprecation status, version. |
| Instants | `TIMESTAMPTZ` | Business milestone, display timezone, precision, and clock source. |
| Local dates | `DATE` | Business timezone/calendar used to determine "day." |
| JSON/document | `JSONB` or separate document | Schema version, required/optional fields, query/index strategy, free-form controls. |
| Binary | `BYTEA` / object reference | MIME/type, size, checksum, permissions, and retention. |

### Do Not Store Everything as Strings

Amounts `"120000"`, timestamps `"22/11/2026"`, and statuses `"1"` can all be stuffed into `VARCHAR`, sacrificing format checks and breeding conflicting interpretations across consumers. Reserve strings for codes or genuinely textual data; business values deserve strict types at storage and contract layers.

### Precision Differs from Real-World Accuracy

`NUMERIC(18,6)` can store six decimal places without making a scale or sensor accurate to six decimal places. The dictionary must distinguish:

- **Storage resolution**: digits/step size representable.
- **Measurement accuracy**: instrument/source error tolerance.
- **Rounding rules**: how computed values convert into stored money or units.

For FLOAT/DOUBLE, also define comparison tolerance policies. Do not use exact equality checks for real-number calculations where business logic requires a tolerance band.

## 10. Units of Measure: A Mandatory Part of Field Semantics

`temperature = 30` is incomplete without knowing °C or °F. `amount = 20000` is likewise insufficient without currency, minor units, or measure definition.

A measurement column needs at least:

1. **Quantity kind**: temperature, mass, duration, distance, money, ratio…
2. **Canonical unit**: °C, kg, millisecond, minor units, %, fraction…
3. **Conversion system**: which source, how converted, whether versioned.
4. **Precision/scale/rounding**: how many digits kept, when rounding occurs.
5. **Valid bounds**: physical bounds and business bounds may differ.
6. **Additivity**: can it be SUMmed across time/customers/products?
7. **Reference time**: when measured, for which period, at which FX rate timestamp.

Examples:

| Field | Safe Definition | What Not to Do |
| --- | --- | --- |
| `quantity` | Quantity with `unit_code` or product canonical unit. | Add 3 kg and 2 pieces as if identical units. |
| `amount_minor` | Integer in smallest unit of paired currency. | Directly sum VND and USD. |
| `discount_rate` | Fractional ratio 0..1; `0.15` means 15%. | Confuse `0.15` with 0.15% or `15` with 15%. |
| `temperature_c` | Celsius temperature, scaled per device. | Compare against Fahrenheit thresholds without conversion. |
| `latency_ms` | Non-negative millisecond duration. | Confuse absolute timestamp with elapsed duration. |
| `inventory_balance` | Point-in-time balance. | Sum daily balances as if inflows/outflows. |

### Monetary Aggregation Rules Must Be Explicit

For example, `amount_minor = 150000` with `currency_code = 'VND'` follows VND's minor-unit convention agreed in the contract; if another currency uses different decimal places, converters must look up the currency rather than hardcoding "divide by 100" for all currencies.

~~~sql
-- Example sum of captures and refunds by currency, without currency conversion.
SELECT tenant_id, currency_code,
       SUM(CASE WHEN movement_type = 'CAPTURE'
                THEN amount_minor ELSE 0 END) AS captured_minor,
       SUM(CASE WHEN movement_type = 'REFUND'
                THEN amount_minor ELSE 0 END) AS refunded_minor,
       SUM(CASE WHEN movement_type = 'CAPTURE'
                THEN amount_minor ELSE -amount_minor END) AS net_cash_minor
FROM ordering.payment_movement
WHERE tenant_id = :tenant_id
GROUP BY tenant_id, currency_code;
~~~

The result is **confirmed net cash flow** within source data scope; it is not automatically accounting revenue. If FX rates apply, the dictionary/contract must specify the rate source, effective date, rounding, target currency, and restatement rules when rates are revised.

## 11. Value Domains: More Than an Enum List

A **value domain** is the set of values that can appear **along with their meanings and validity conditions**. A domain is not just enums; it can be numeric ranges, formats, cross-column relationships, reference catalogs, or state-dependent rules.

Examples:

| Field | Value Domain | Rules Beyond Type |
| --- | --- | --- |
| `line_no` | Positive integer. | Unique within each order. |
| `quantity` | Positive decimal, up to 3 decimal places. | Unit matches product type; integer quantity if sold by piece. |
| `booked_total_minor` | Non-negative integer. | Sum formula per locked pricing rules. |
| `order_status` | `PLACED/CANCELLED/FULFILLED`. | Valid transitions, actor permissions, cancellation conditions. |
| `currency_code` | System-supported currency code. | Effective-dated code list, not merely length = 3. |
| `confirmed_at` | Absolute instant with confirming source. | Must not default to `received_at` if callback lacks timestamp. |
| `provider_reference` | String per provider namespace. | Unique per merchant/tenant/provider scope per contract. |

### Types of Domains to Identify

- **Enumerated:** status codes, movement types, contract types.
- **Range:** `0 ≤ discount_rate ≤ 1`, `quantity > 0`.
- **Format:** country codes, emails, phone numbers, business IDs.
- **Referential:** code must exist in an owned lookup table/config.
- **Cross-field:** `end_at > start_at`, `net_amount = gross - discount` per policy.
- **Conditional:** if `movement_type = REFUND`, an eligible capture reference is required if business rules demand it.
- **Temporal:** value is valid only within an effective period.
- **Uniqueness:** one `provider_reference` per transaction within source scope.

A `status` enum can be valid in SQL while still representing an illegal business transition. For instance, `FULFILLED -> PLACED` may be forbidden even though both values pass `CHECK`. The dictionary should link to the **state machine** and transition guards.

### Value Domains Can Evolve Over Time

Adding `PARTIALLY_FULFILLED` is a contract change; legacy consumers may fail to parse the new enum. The dictionary needs to record:

- Status name and code, description, effective start date.
- Writer/reader behavior upon encountering unknown codes.
- Deprecation rules for old codes and historical handling.
- Where hardcoded enums are used versus versioned reference tables.

Never assign **a new meaning to an old code** and then interpret all historical records under the new meaning.

## 12. NULL Values, Absence, and Default Values

`NULL` in a database means **no value present in the column for the current state**, yet the **business cause** can vary. The dictionary must define:

| Case | Example | Representation to Consider |
| --- | --- | --- |
| **Not yet occurred** | Order not yet delivered, no `delivered_at`. | Nullable timestamp + explicit state. |
| **Not applicable** | Charge requires no tracking number. | Null or distinct business type; explain why. |
| **Not yet provided** | Customer omitted secondary phone number. | Null, never fabricate a fake number. |
| **Pending verification** | Refund outcome not yet confirmed by provider. | PENDING status; do not equate NULL with refunded. |
| **Unknown from legacy source** | Legacy record lacks capture timestamp. | `UNKNOWN_LEGACY`/documented status, never default to `now()`. |
| **Erased/masked** | Personal attribute processed per policy. | Proper lifecycle metadata, never conflated with "unknown." |

A single nullable column should not carry five different meanings simultaneously if they drive different decisions. An accompanying **status or reason_code** may be needed.

### Do Not Confuse NULL with 0 or Empty String

- `NULL`: absent or not applicable per contract.
- `0`: numeric zero, **known**.
- `''`: empty string, either invalid or an actual value depending on field.
- `"UNKNOWN"`: explicit classification code, not a catch-all default for missing-data errors.
- **Missing key in a JSON patch**: makes no change to the field, unlike sending `null` to clear it.

For an unoccurred refund: do not insert `refunded_amount_minor = 0` into the payment movement table to fabricate a "zero-amount refund transaction"; net aggregates can return 0 from **having no refund rows**, while every movement row must hold a positive amount.

### DB Defaults vs. Business Defaults

~~~sql
-- Reasonable when metadata is genuinely determined by the DB.
created_at TIMESTAMPTZ NOT NULL DEFAULT now()
~~~

That does not mean every `confirmed_at` can default to `now()`. `confirmed_at` must come from the authoritative source or defined cutoff point. A technically convenient default can **fabricate business facts** if applied to the wrong field.

## 13. Keys, Relationships, and Uniqueness Must Have a Scope

An accurate dictionary must clarify "unique **where**?"

| Kind | Example | What to Document |
| --- | --- | --- |
| **PK** | `(tenant_id, order_id)`. | Row identity, never reused. |
| **Composite FK** | `(tenant_id, order_id)` on OrderLine. | Prevents linking rows across different tenants. |
| **Business key** | `provider_name + provider_reference` in verified namespace. | Does the provider guarantee uniqueness per merchant/time? |
| **Candidate key** | `tenant_id + external_order_no` when source guarantees it. | Can it be missing/duplicated or edited? |
| **Surrogate key** | `customer_sk` in the data warehouse. | Internal SK, does not replace business codes when exchanging with sources. |
| **External reference** | Catalog's `product_id` inside Ordering. | Owner, verification method, lifecycle/tombstone, never assume cross-service FK. |

**Foreign keys protect parent row existence within the same DBMS scope**, but do not automatically enforce all domain invariants. For example, an OrderLine → Order FK does not guarantee that a booked Order has at least one line at commit time; application/transaction logic must check that.

Similarly, `UNIQUE (tenant_id, order_id)` prevents two rows from sharing an ID in one table; it does not enforce idempotency of a **business request** if the request can be replayed with a new order ID. A stable request key and deduplication policy are required.

### 1:N, N:N Relationships and Optionality

Beyond cardinality, the relationship dictionary should specify:

- Is one side **required** to have related rows?
- Deletion rule: RESTRICT, SET NULL, CASCADE, soft delete, or retain history?
- Is the relationship **effective-dated over time**?
- Is it a cross-bounded-context reference?
- Does a many-to-many relationship have its own attributes (role, allocation ratio, effective period)?

If one product belongs to multiple categories, joining to sum revenue by category can multiply amounts. Allocation/bridge grain rules are needed instead of treating N:N as a harmless join.

## 14. Time Definitions and Value Lifecycles

In a dictionary, temporal fields need **milestone definitions**, not just `TIMESTAMP` declarations.

| Field | Meaningful Milestone | Typical Use |
| --- | --- | --- |
| `occurred_at` | When the event is confirmed to have happened by the authoritative source. | Event timelines, event-based analytics. |
| `placed_at` | When Ordering accepts the order. | Order windows/sales periods. |
| `confirmed_at` | When Payment recognizes a provider-confirmed capture/refund. | Cash flow by transaction time. |
| `recorded_at` | When the system writes the record. | Ingest audit, system-known time. |
| `effective_from/to` | Interval when a fact holds per business rules. | Prices, policies, as-of contracts. |
| `deleted_at` | When soft-deleted from standard flows. | Filtering current data; **not** a substitute for purge. |
| `retention_until` | Milestone when eligible for policy action. | Archival, controlled purge/anonymization. |

Business time can differ from recording time. A delayed callback arriving at 15:00 may confirm a capture occurred at 14:30. If reports require provider confirmation time, use `confirmed_at`, not `recorded_at`.

**When data is corrected retroactively**, both **valid time** and **recorded/system time** (bitemporal) may be needed. For instance, a price valid from 01/04 whose correction decision is logged on 10/04. The dictionary must state whether the dataset can answer both "what price was valid on 05/04" and "what price did the system know on 05/04."

### Time Intervals and Timezones

The `[start_at, end_at)` convention—inclusive start, exclusive end—prevents boundary overlaps. The dictionary should record:

- Absolute instants using UTC/`TIMESTAMPTZ` where appropriate.
- Which local timezone defines business dates.
- Time precision: seconds, milliseconds, microseconds.
- Whether `end_at IS NULL` means open-ended or not yet ended.
- Month/week period rules, timezones, and DST transitions if applicable.

Never derive business dates from server timezone across all tenants. The same UTC instant can fall on two different business days in two regions.

## 15. Derived Fields and KPIs: Document Formulas Alongside Semantics

A dictionary does not just cover directly stored columns. For **derived** fields, record:

1. Authoritative source and freshness.
2. Formula **with units** and output grain.
3. Filters: included statuses, time windows, and tenant scope.
4. Handling of missing/late/retry/correction records.
5. Rounding, FX conversion, categorization, and additivity.
6. Definition version, effective start date, and whether historical data is restated.

Example of a mart with two metrics that must stay separate:

| Metric | Suggested Formula | Why Distinct |
| --- | --- | --- |
| **Booked sales** | Sum of `booked_total_minor` for valid orders per policy at `placed_at`. | Order value, does not prove cash collected. |
| **Gross captured** | Sum of provider-confirmed CAPTUREs. | Gross cash inflow; multiple transactions possible per order. |
| **Refunded cash** | Sum of provider-confirmed REFUNDs. | Excludes uncompleted `RefundRequested`. |
| **Net cash** | `gross_captured - refunded_cash` per agreed currency/period. | Net cash flow; not automatically accounting revenue. |
| **Refund rate** | Refund numerator / capture denominator per definition. | Never take AVG of group rates with unequal weights. |

In a data dictionary, **metric definitions** must distinguish raw columns from derived KPIs. A physical column named `revenue` does not prove it matches Finance's "recognized revenue."

### Derived Grain

If `daily_sales_mart` has grain `(tenant_id, business_date, currency_code, channel_id)`, each row must contain metrics strictly for those four keys. Never join movement rows (transaction grain) directly with order_line rows (line grain) and SUM if both sides are one-to-many; pre-aggregate each to the common target grain.

## 16. A Dictionary Must Link to Technical Constraints and Tests

A definition proves its worth when there is a **way to verify it**.

| Documented Fact | Appropriate Constraint/Test | Limitation |
| --- | --- | --- |
| `quantity > 0` | `CHECK (quantity > 0)`. | Does not check whether the unit of measure is right. |
| `order_status` in three codes | `CHECK ... IN (...)`. | Does not validate state transitions. |
| Every OrderLine belongs to an Order | Tenant/order composite FK. | Does not guarantee an Order has at least one line at commit. |
| Unique `provider_reference` | UNIQUE per verified namespace. | Does not stop a provider from issuing two IDs for one business attempt. |
| Single currency per calculation | `GROUP BY currency_code` / conversion rule. | Does not define valid FX rates. |
| Grounded `confirmed_at` | Reconcile provider confirmation and pipeline receipt. | `TIMESTAMPTZ` type does not prove the timestamp is right. |
| No PII in published events | Schema contract + payload/permission tests. | Source DDL does not control downstream consumers. |

### Data Quality SQL Checks

~~~sql
-- 1. Domain-invalid fields in source/staging
--    (with target CHECKs, such rows are rejected on write).
SELECT tenant_id, order_id, line_no
FROM ordering.sales_order_line
WHERE quantity <= 0
   OR line_net_minor < 0;

-- 2. Orphan check at target
--    (in-DB FK normally guards this).
SELECT l.tenant_id, l.order_id, l.line_no
FROM ordering.sales_order_line l
LEFT JOIN ordering.sales_order o
  ON o.tenant_id = l.tenant_id
 AND o.order_id = l.order_id
WHERE o.order_id IS NULL;

-- 3. Enum value distribution (useful when reconciling other sources).
SELECT order_status, COUNT(*) AS n
FROM ordering.sales_order
GROUP BY order_status;

-- 4. Duplicate movements with same provider ref (guarded by UNIQUE in example).
SELECT tenant_id, provider_name, provider_reference, COUNT(*) AS n
FROM ordering.payment_movement
GROUP BY tenant_id, provider_name, provider_reference
HAVING COUNT(*) > 1;
~~~

"Zero-row" tests fit uniqueness/orphan errors; other quality checks need **SLO thresholds**, such as lag between `confirmed_at` and `recorded_at` or the rate of unreconciled orders.

### Invariants That Do Not Fit Inside a Single CHECK

"Do not refund more than collected" may require summing across multiple movements and checking the transaction/ledger owner. "Do not double-sell a seat" requires uniqueness/locking at the seat owner, not merely a CHECK on Booking. In the dictionary, record **owner, rule, and enforcement location**, rather than pretending all rules live in one SQL constraint.

## 17. Which Metadata Can Be Generated Automatically from PostgreSQL?

The DBMS knows names, types, nullability, defaults, keys, indexes, some constraints, and comments. These facts can be queried to compare against the dictionary.

~~~sql
SELECT
    c.table_schema,
    c.table_name,
    c.ordinal_position,
    c.column_name,
    c.data_type,
    c.character_maximum_length,
    c.numeric_precision,
    c.numeric_scale,
    c.is_nullable,
    c.column_default
FROM information_schema.columns AS c
WHERE c.table_schema = 'ordering'
ORDER BY c.table_name, c.ordinal_position;
~~~

Another query lists PK/UNIQUE/FK via `information_schema.table_constraints`, `key_column_usage`, and `constraint_column_usage`, or PostgreSQL system catalogs for engine-specific details. Distinguish **metadata enforced by the DB** from **the intended contract**.

### COMMENT Places Semantics Near the Schema, But Is Not Enough

~~~sql
COMMENT ON COLUMN ordering.sales_order.booked_total_minor IS
'Booked order value, minor units per currency_code; before deducting refunds.';
~~~

Strength: SQL administrators see explanations right on the column. Limitations:

- Comments do not enforce a uniform structure.
- Cannot fully express grain, owner, privacy, quality tests, and version.
- Do not automatically sync with APIs/events or the glossary.
- Can go stale after migrations.

**Best practice:** pick one governed source of truth (metadata-as-code or catalog), **automatically reconcile it against DDL**, and decide which metadata syncs back to `COMMENT`. Never maintain two independent copies of a dictionary without a verification pipeline.

## 18. Machine-Readable Dictionaries and Version Control

A team can store metadata in YAML/JSON/schema registries and render Markdown tables for learners, analysts, or developers. **Illustrative format** example, not a mandatory standard of any specific tool:

~~~yaml
dataset_id: ordering.sales_order
contract_version: 1
owner: Ordering
grain: "One booked order per (tenant_id, order_id)"
primary_key:
  - tenant_id
  - order_id
columns:
  - name: order_id
    type: uuid
    nullable: false
    definition: "Immutable identifier of the order within tenant"
  - name: booked_total_minor
    type: bigint
    nullable: false
    unit: "minor units of currency_code"
    domain: "integer >= 0"
    definition: "Booked order value, before deducting refunds"
  - name: currency_code
    type: char(3)
    nullable: false
    domain_ref: "supported_currency_codes"
    definition: "Currency code attached to booked_total_minor"
quality_checks:
  - "PK unique by (tenant_id, order_id)"
  - "booked_total_minor >= 0"
change_policy: "Semantic changes require a new contract and historical reconciliation"
~~~

Production projects should validate metadata files against a schema, enforce naming rules, and link to DDL/CI. The YAML above describes a **contract**; it does not automatically create CHECKs, FKs, or DB constraints.

### Identifier vs. Display Name

If "Purchase Order" is relabeled "Sales Transaction" while its meaning stays identical, the label may change. If its meaning changes from placed order to paid order, assign a **new term ID/version or distinct term**, rather than silently rewriting the old code's definition and reinterpreting all historical data under the new meaning.

Dictionary definitions also have lifecycles: draft, reviewed, approved, deprecated. A deprecated field may still need documentation to decode historical events/reports until support commitments expire.

## 19. Change Management: From Requirement to DDL, Contracts, and Read Models

Dictionary maintenance should move in lockstep with **schema evolution**, rather than documenting after deployment.

~~~mermaid
flowchart TD
    REQ["Business requirement"] --> DEF["Define grain, columns, units, domains, owner"]
    DEF --> REV["Business + technical + data governance review"]
    REV --> MODEL["Logical model / ERD / data dictionary version"]
    MODEL --> DDL["SQL migration, constraints, API/event contract"]
    DDL --> TEST["Schema, data quality, and compatibility tests"]
    TEST --> DEPLOY["Expand / migrate / cutover / contract"]
    DEPLOY --> OBS["Lineage, lag, drift, KPI, exceptions"]
    OBS --> DEF
~~~

### On Rename

`customer_name` → `display_name` is purely a rename only if **the concept and meaning remain identical**. Update physical/API names and aliases according to the compatibility plan while keeping the term ID stable. Inventory SQL, ORM, CDC, exports, and consumers. If both columns coexist during transition, specify which is authoritative and how they reconcile.

### On Structural Change

`customer.phone` → 0..N contact methods table: update grain, relationships, keys, cardinality, primary/verified rules, and backfill. Do not fabricate `verified_at` if legacy sources lack proof. An old dictionary entry saying only `phone VARCHAR` fails to protect this case.

### On Semantic Change

If `order_status='PAID'` previously meant "collection request sent" and now means "provider confirmed capture," create a new definition/contract, distinguish legacy data, backfill reconciliations, and migrate consumers. Editing a dictionary description **does not retroactively fix historical data**.

### Definition of Done for a Change

- Logical and physical dictionaries updated to match the contract.
- DDL/schema migration includes proper rollback/cutover.
- API/event/CDC consumers verified.
- Data quality and before/after figures reconciled.
- Owner approves semantics, historical handling, and retention.
- Alerts exist when dictionary metadata diverges from DB-enforced metadata.

## 20. Multi-Source Data: Namespaces, Standardization, and Lineage

An integration data dictionary must clarify which source provides each field.

For example, two systems both use `customer_id`:

- CRM: `crm.customer_id = 42`, unique within CRM.
- E-commerce: `account_id = 42`, unique within tenant and platform.
- Master data: `canonical_customer_id = CUS-920` after evidence-based matching.

These three values **do not automatically refer to the same customer** just because both contain 42. The dictionary must document:

| Metadata | Example |
| --- | --- |
| Source system | `crm`, `ecommerce`. |
| Source field | `crm.customer_id`, `ecommerce.account_id`. |
| Source namespace/scope | Per CRM and tenant. |
| Canonical ID mapping | Mechanism and evidence confirming same customer. |
| Source-of-truth per attribute | CRM owns segment, Customer Identity owns login identity. |
| Update/precedence | Effective timestamps, source priority rules, and conflict resolution. |
| Lineage | Source dataset/record, cursor/batch, rule version, transform. |
| Temporal contract | Source update time, receipt time, effective time. |

Do not pick "latest record" across two sources purely by comparing timestamps without verifying clocks, business semantics, and trusted source precedence. CRM's `last_updated_at` may reflect when **CRM saved the row**, not when a segment became valid.

### Multiple Valid Derived Views Can Coexist

An SCD2 `dim_customer` retains segment as of the sale date; `customer_current` holds only the current segment. Both derive from master data yet have **different grain and time semantics**. The dictionary should specify which questions each dataset is authorized to answer rather than reusing a vague `segment` name across all marts.

## 21. Privacy, Permissions, and Retention Policies Are Mandatory Metadata

The dictionary is also the basis for determining **which data may be used**.

For columns capable of identifying people, locations, or payment data, record:

- **Classification:** public/internal/confidential/PII/financial or the organization's approved scheme.
- **Processing purpose:** why the field must exist in this dataset.
- **Owner and data steward:** who approves read/write access and handles requests.
- **Retention trigger:** when the retention clock starts, any legal hold exceptions.
- **Erasure/anonymization:** which fields are deleted, pseudonymized, aggregated, or retained under separate obligations.
- **Derived paths:** whether APIs, events, caches, search indexes, reports, archives, and backups still hold copies.
- **Tenant/role access:** who can view detail rows; whether soft-deleted records remain queryable.
- **External recipients:** contracts and sharing limits; never assume every consumer needs the full payload.

For example, `customer_id` may be a UUID yet still link back to a natural person. Converting emails to UUIDs or hashing business keys **does not automatically anonymize data**. If `customer_name` is erased from the source table, prior copies in audits, events, CDC, backups, or warehouses still require policy handling.

Never fill in an arbitrary statutory retention period just because an example says "keep 7 years." Actual periods and legal bases must be approved by authorized stakeholders per data type, jurisdiction, and purpose.

## 22. Documenting Document, Graph, Time-Series, and Warehouse Models

Data dictionaries are not solely for SQL tables.

| Model | Units to Document | Special Metadata |
| --- | --- | --- |
| **Relational** | Tables, columns, PK/FK/unique, relationships. | Cardinality, checks, constraints, indexes, partitions. |
| **Document** | Collections, document types, JSON paths, arrays. | Schema version, required/optional/missing, embedded vs. reference, array cardinality. |
| **Graph** | Node labels, edge types, node/edge properties. | Edge direction, multiplicity, effective dates, relationship owner. |
| **Time-series** | Measurement types, sensors, sample IDs, timestamps, values. | Units, event time vs. ingest time, quality flags, revisions, dedup, retention. |
| **Analytical** | Facts, dimensions, metrics, snapshots, marts. | Grain, additive/semi-additive, SCD, business-time, rule version. |
| **Event store** | Event types, aggregate IDs, stream versions, payloads. | Fact semantics, schema version, idempotency, replay/correction. |

### Document: Missing Key Differs from Key = Null

A JSON document may omit `middle_name`, contain `"middle_name": null`, or contain `"middle_name": ""`. The dictionary must specify whether these three forms behave identically or differently; especially with **JSON Merge Patch/partial updates**, omitting a field can mean "keep unchanged," whereas `null` means "delete."

### Graph: Document Edges as Business Facts

An edge `Customer-[:OWNS]->Account` needs to clarify whether ownership is legal or merely operational access, when it takes effect, and whether multiple owners are permitted. Documenting only node/edge labels fails to prevent faulty traversal inferences.

### Time-Series: Timestamp Is Not Measurement Identity

Two valid temperature samples can share `measured_at`. The dictionary must define `measurement_id`, `sensor_id`, unit, revision, and correction policies; defaulting to `(sensor_id, measured_at)` as unique risks silently dropping real data.

### Warehouse: Ratios Do Not Sum Automatically

Daily `inventory_balance` is a balance—do not SUM it across days like sales. `conversion_rate` needs an explicit numerator/denominator and grain; averaging per-store rates does not always equal the company-wide rate. These belong in the **measure dictionary**, not only in dashboard logic.

## 23. Organizing the Review Process So the Dictionary Never Goes Stale

A workable workflow:

1. **Business analyst** writes definitions, grain, and expected-result rules with counterexamples.
2. **Domain owner** confirms recognition cutoffs, source of truth, update authority, and state transition conditions.
3. **Data modeler/DB engineer** confirms types, PK/FK, cardinality, integrity, indexes, and migration strategy.
4. **Data engineer/analytics owner** confirms lineage, transforms, metric grain, late data, and recomputability.
5. **Security/privacy owner** reviews classification, permissions, retention, and derived data.
6. **Consumer representative** checks names, enums, nullability, and compatibility; not just compile passes.
7. **CI/CD** validates metadata schema, database drift, data tests, contracts, and versioned docs.
8. **Post-deploy** monitors quality, exceptions, consumer counts, deprecated fields, and sunset deadlines.

Small teams may not staff every role separately. One person can wear multiple hats, yet **approval accountability** must remain explicitly assigned.

### Prioritize Documentation Effort

You do not need ten pages for a rarely used technical column. Prioritize fields that alter outcomes or carry risk:

- Keys and foreign/external references.
- Amounts, quantities, rates, balances, currencies.
- Statuses/enums governing behavior.
- Timestamps and time intervals.
- PII and sensitive data.
- KPI fact/dimension grains and formulas.
- Columns with multiple sources or correction history.

Concise documentation that is **accurate, owned, and tested** beats a sprawling metadata table copied from DDL and forgotten.

## 24. Common Mistakes When Building a Data Dictionary

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Listing only column names and DB types | Consumers guess meanings, units, and NULLs. | Add definitions, grain, units, domains, and owners. |
| Calling every amount "revenue" | Confuses booked sales with captures/refunds/recognized revenue. | Distinguish cutoff points and sourced formulas. |
| Setting `VARCHAR(20)` and assuming status domain is controlled | Stray codes or invalid state transitions occur. | CHECK/reference table + versioned state machine. |
| Writing "timestamp is UTC" without specifying the milestone | Incorrect daily/window grouping. | Define event/record/effective time and business timezone. |
| Using one NULL value for all causes | Cannot tell unoccurred from unknown or N/A. | Null semantics and required status/reason codes. |
| Defining `quantity` without unit | Adds kg with pieces or misreads decimals. | Unit code, scale, standardization, and quality checks. |
| Documenting only PK, ignoring business key and namespace | ID collisions across tenants/sources, bad mappings. | Clarify scope and evidence-backed mappings. |
| Documenting Order 1:N Payment yet SUMming after M–N JOIN | Multiplies sales figures. | Define grain first and aggregate per grain. |
| Treating auto-generated COMMENT/DDL as a full dictionary | Lacks semantics, owner, and lineage. | Governed metadata + automated reconciliation with schema. |
| Changing column meaning without versioning | Legacy data gets interpreted under new rules. | Semantic versioning, migration, and transparent restatement. |
| Changing enums without checking consumers | Legacy readers fail or fall into wrong defaults. | Contract tests, phased rollout, and deprecation. |
| Having a dictionary without tests | Docs say one thing, data does another. | Bind definitions to CHECK/quality SQL/CI. |
| Assuming UUID/hash equals anonymized data | Still linkable and re-identifiable. | Policy-driven classification and retention. |
| Metadata edited by multiple groups without an owner | Competing definitions, nobody signs off. | RACI/owner, reviews, and approved versions. |
| Changing physical schema without updating dictionary | Stale docs and downstream breakages. | Make dictionary diff a mandatory part of migrations. |

## 25. Practice Exercise: Building a Dictionary for an Equipment Rental System

**Context:** an equipment rental platform manages customers, equipment, rental contracts, equipment lines, deposits, and deposit refunds. A contract can be extended multiple times; customers can change contact numbers; the payment provider sends delayed or duplicate callbacks. Analytics needs reports on rental revenue, held deposits, and late-return rates.

A rough draft model is provided:

~~~text
rental_contract(
    tenant_id, rental_id, customer_id,
    start_time, end_time, status, total_amount
)

rental_item(
    tenant_id, rental_id, line_no, equipment_id,
    quantity, price
)

payment_record(
    tenant_id, payment_id, rental_id,
    type, amount, time, provider_ref
)

equipment(
    tenant_id, equipment_id, code, name, availability
)
~~~

**Tasks:**

1. **Define grain** precisely for all four tables. Is `payment_record` an attempt, a request, or a provider-confirmed movement? Choose and explain.
2. **Identify owners/sources of truth** for contracts, available quantities, deposits, and customer profiles. Which data are external references?
3. **Create a table-level dictionary** for `rental_contract`: PK, business key, relationships, temporal contract, update policy, retention, read indexes.
4. **Create a column-level dictionary** for at least 12 fields across the four tables: name, definition, type, NULL, unit, domain, source, quality rule.
5. **Clarify `start_time/end_time`:** is it contract term, actual handover/return time, or server write time? If all three are needed, propose new field names.
6. **Split `status` into value domains:** contract status differs from payment status and equipment status. Sketch minimal transitions.
7. **Design money and units:** choose `amount_minor`, `currency_code`, quantity, and unit; distinguish locked rental price from current catalog rate.
8. **Clarify NULL:** what does `actual_returned_at = NULL` mean? Is `refund_confirmed_at = NULL` enough to prove no refund occurred?
9. **Define keys/uniqueness:** tenant-scoped composite keys; how is the `provider_ref` business key namespaced? If two contracts request the same equipment over overlapping times, where is that invariant enforced?
10. **Write PostgreSQL DDL** for one table with PK, FK, CHECK, and indexes matching identified queries; explain which rules cannot rely solely on CHECK.
11. **Write verification checks** for: rental lines missing a contract, invalid quantity, duplicate movements, refund exceeding collected amount, invalid return timestamp.
12. **Define KPIs:** rental revenue, held deposits, late-return rate; specify grain, numerator/denominator, time period, currency, and correction handling.
13. **Schema evolution:** is changing `code` → `equipment_code` purely a rename or a semantic change? What structural change is moving customer `phone` from one number to many numbers?
14. **Security and history:** a customer requests phone number deletion while contracts/deposits still have retention obligations; how must the dictionary document affected fields and derived copies?
15. **Metadata-as-code:** write a YAML/JSON snippet describing `rental_contract` and three fields with domain/unit; propose a CI check to detect DDL drift.
16. **Architecture Decision Record:** document assumptions, source-of-truth choices, versioning policy, review workflow, and criteria for considering the dictionary complete.

### Self-Assessment Checklist

| Criterion | Expected Outcome |
| --- | --- |
| **Grain and identity** | Each table has one clear row definition, business key/PK, and tenant scope. |
| **Semantics** | Never conflate contract status, payment, inventory, and business events. |
| **Types and units** | Money, rates, durations, quantities have proper units/precision/rounding. |
| **Value domains** | Domains, transitions, and cross-field conditions specified where needed. |
| **NULL** | Distinguishes unoccurred, unknown, and not applicable. |
| **Time** | Distinguishes event-time, effective-time, recorded-time, and business timezone. |
| **Relationships** | FKs/external references, cardinality, deletion/retention explained. |
| **Correctness** | Includes CHECKs/constraints plus data and cross-table invariant tests. |
| **Integration** | Covers owner, source, lineage, consumer compatibility, and rule versions. |
| **Governance** | Sensitive data, permissions, and retention policies documented responsibly. |

**Conclusion:** a data dictionary is **the explanatory contract of a model**, connecting business requirements to entities, relationships, types, units, value domains, and verification rules. A table with valid DDL does not guarantee **semantically valid** data. When every dataset has a clear grain and owner, every field has a definition/unit/NULL/domain, and constraints are tied to tests and change workflows, the model becomes easy to use, integrate, evolve, and verify over time.
