# Entity–Attribute–Value (EAV) and the Cost of Over-Generic Structures

## Learning Objectives

After this lesson, you will be able to:

- Explain **Entity–Attribute–Value (EAV)** and define the **grain** of each row, rather than confusing an attribute row with a business entity.
- Analyze trade-offs between **flexibility when adding attributes** and **costs in typing, constraints, queries, indexes, statistics, operations, and schema evolution**.
- Spot common EAV pitfalls: storing every type as TEXT, casting at read time, ambiguous missing values, multi-valued attributes without clear grain, and storing prices/balances as arbitrary attributes.
- Write PostgreSQL queries over EAV, understand self-join/pivot costs, and avoid row multiplication or mis-summed measures.
- Distinguish when to use **typed columns**, **category extension tables**, **typed EAV**, **JSONB/documents**, or **read projections**.
- Design governed metadata with **units, required/allowed values, data classification, ownership, and versioning**, plus migration and testing workflows.
- Evaluate options using workload profiles, data policies, historical semantics, and reconcilable criteria.

This lesson sits in the **Common Pitfalls** chapter of **DATABASE_DATA_MODELING**. Aligned with the module's goal, a good model faithfully turns business requirements into entities, relationships, constraints, normalization, keys, indexes, and physical schemas—while comparing relational, document, graph, and analytical models to yield evolvable, verifiable structures. EAV illustrates a crucial truth: **fewer columns does not mean lower modeling cost**.

> **Key message:** EAV is not inherently wrong. It is valuable for attributes that are genuinely dynamic, sparse, and governed. Yet when EAV is used to dodge defining **types, grain, invariants, permissions, and access patterns** for core data, complexity simply shifts from DDL into the surrounding system.

## 1. Scenario: "One Table That Stores Every Kind of Attribute"

A marketplace sells phones, apparel, books, and industrial machinery. Product categories have vastly different attributes:

| Category | Sample Attributes |
| --- | --- |
| **Phones** | storage_gb, color_code, has_nfc, screen_inches |
| **Apparel** | size_code, fabric_code, color_code |
| **Books** | isbn, author, page_count, language_code |
| **Industrial machinery** | voltage_v, power_w, maintenance_cycle_days |

The team wants admins to add attributes without running `ALTER TABLE`. The proposed design:

~~~text
entities:
  entity_id | entity_type | name

attributes:
  attribute_id | name

values:
  entity_id | attribute_id | value
~~~

Example for one phone variant:

| entity_id | attribute | value |
| --- | --- | --- |
| P-101 | color_code | black |
| P-101 | storage_gb | 128 |
| P-101 | has_nfc | true |
| P-101 | screen_inches | 6.5 |

To add **waterproof_rating = IP67**, you only insert metadata and one value row—no column migration required.

Yet the moment the UI needs to search for **black phones with at least 128 GB storage, NFC, sorted by price**, hard questions emerge:

- Is **128** an integer or the string **"128 GB"**?
- Is **true** a Boolean or strings **"TRUE"/"YES"/"1"** depending on the upstream source?
- Does an attribute belong to the **product family** or the **sellable variant**?
- Who governs allowed values and required fields for phones?
- Can users add **internal_cost** or **recipient_email** into the same public table?
- How many joins and indexes are required across millions of variants?
- When an attribute changes unit or meaning, do legacy APIs, search indexes, and ETL pipelines keep working?

**The EAV structure made adding an attribute easy, without answering any of those business questions.**

## 2. What Is EAV, and What Is Its Grain?

EAV represents a fact as a triple:

~~~text
(entity, attribute, value)

entity     = the entity being described
attribute  = definition of a property of that entity
value      = current value for that property
~~~

A typed-column table:

| variant_id | color_code | storage_gb | has_nfc |
| --- | --- | ---: | --- |
| P-101 | black | 128 | true |
| P-102 | blue | 256 | false |

The EAV representation:

| variant_id | attribute_code | value_text |
| --- | --- | --- |
| P-101 | color_code | black |
| P-101 | storage_gb | 128 |
| P-101 | has_nfc | true |
| P-102 | color_code | blue |
| P-102 | storage_gb | 256 |
| P-102 | has_nfc | false |

**Illustrative grain: one EAV row is the current value of one single-valued attribute for one variant within one tenant.** The key may be **(tenant_id, variant_id, attribute_id)**.

If an attribute is multi-valued—like **multiple authors**—that key cannot represent it. Use an Author entity with an N:M **book_authors** table, or model value_id/position/cardinality explicitly. **Never stuff comma-separated lists into value_text to pretend a relationship is a scalar attribute.**

If history is required, a value row also needs **effective_from/effective_to**, version numbers, or event IDs. Never assume appending a row on every change yields valid history without non-overlap constraints and current-version rules.

### 2.1. What Real Problems Does EAV Solve?

- **Very sparse attributes:** each entity subtype uses only a tiny slice of the global field catalog.
- **Configurable forms:** admins define custom fields per form template.
- **Telemetry / observation systems:** attributes and measurement types evolve frequently and are well-described by metadata.
- **Broad multi-category catalogs:** thousands of rare optional traits that are rarely filtered individually.
- **Multi-tenant SaaS custom fields:** each tenant defines a handful of custom attributes, provided the system accepts the governance cost.

However, if 90% of searches filter on 5 stable, well-defined attributes, stuffing those 5 into EAV makes queries and data integrity harder without delivering proportional value.

### 2.2. EAV Neither Automatically Violates Nor Guarantees Normalization

In a single-valued EAV table, the functional dependency **(entity_id, attribute_id) → value** can hold, alongside **attribute_id → attribute definition** in metadata. Such a schema does not necessarily violate classical normal forms.

The real issue is that **logical column types and rules moved into metadata rows**, making it hard for the database to enforce per-attribute NOT NULL, CHECK, or FK constraints. **Normalization, invariant enforcement, and query performance are distinct evaluation axes**—neither "EAV is 3NF" nor "EAV is unnormalized" replaces concrete analysis.

## 3. EAV Is Not a Substitute for Entities and Relationships

A flawed design often tries to store:

~~~text
order:
  buyer_id = "C-101"
  product_ids = "P-1,P-2,P-3"
  payment_status = "PAID"
  shipment_ids = "S-9,S-10"
~~~

Yet:

- An Order has multiple **OrderLine**s, each carrying quantity, variant, and locked price.
- An Order has multiple **Shipment**s, each with its own recipient and lifecycle.
- An Order can have multiple **PaymentCapture**s and **Refund**s, not just one status string.
- Buyer ID links to an Identity domain with tenant isolation and permissions.
- Multi-valued collections need dedicated **grain, keys, ordering, and uniqueness rules**.

EAV can fit **flexible descriptive attributes**; core business relationships and events require structured entities and relationships.

A hybrid layout:

~~~text
catalog_products:
  product_id
  product_name

catalog_variants:
  variant_id, product_id, sku
  list_price_amount, currency_code

phone_specifications:
  variant_id, storage_gb, has_nfc, color_code

variant_optional_attributes:
  variant_id, attribute_id, typed_value

order_lines:
  order_id, line_no, variant_id, quantity
  unit_price_at_confirmation
~~~

**Core** attributes reside where strong types, FKs, and CHECKs apply. **Dynamic, sparse** traits can remain in governed EAV.

## 4. PostgreSQL Example: Minimal EAV Using value_text

The schema below intentionally stores values as TEXT to highlight the pitfalls. It **must not be treated as a default production catalog design**.

~~~sql
CREATE SCHEMA catalog;

CREATE TABLE catalog.variants (
    tenant_id BIGINT NOT NULL,
    variant_id UUID NOT NULL,
    category_code TEXT NOT NULL,
    sku TEXT NOT NULL,
    display_name TEXT NOT NULL,
    list_price_amount NUMERIC(18, 2) NOT NULL,
    currency_code CHAR(3) NOT NULL,

    CONSTRAINT pk_catalog_variants
        PRIMARY KEY (tenant_id, variant_id),
    CONSTRAINT uq_catalog_variants_sku
        UNIQUE (tenant_id, sku),
    CONSTRAINT ck_catalog_variants_price
        CHECK (list_price_amount >= 0)
);

CREATE TABLE catalog.attribute_definitions (
    tenant_id BIGINT NOT NULL,
    attribute_id UUID NOT NULL,
    attribute_code TEXT NOT NULL,
    value_kind TEXT NOT NULL,
    unit_code TEXT,
    is_searchable BOOLEAN NOT NULL DEFAULT FALSE,

    CONSTRAINT pk_attribute_definitions
        PRIMARY KEY (tenant_id, attribute_id),
    CONSTRAINT uq_attribute_definitions_code
        UNIQUE (tenant_id, attribute_code),
    CONSTRAINT ck_attribute_value_kind
        CHECK (value_kind IN ('TEXT', 'NUMBER', 'BOOLEAN'))
);

CREATE TABLE catalog.variant_attribute_eav (
    tenant_id BIGINT NOT NULL,
    variant_id UUID NOT NULL,
    attribute_id UUID NOT NULL,
    value_text TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_variant_attribute_eav
        PRIMARY KEY (tenant_id, variant_id, attribute_id),
    CONSTRAINT fk_eav_variant
        FOREIGN KEY (tenant_id, variant_id)
        REFERENCES catalog.variants(tenant_id, variant_id),
    CONSTRAINT fk_eav_definition
        FOREIGN KEY (tenant_id, attribute_id)
        REFERENCES catalog.attribute_definitions(tenant_id, attribute_id)
);
~~~

What this schema guarantees:

- Each value belongs to an existing **variant** and **attribute** in the same tenant.
- Each **variant–attribute** pair holds at most one current value.
- **attribute_code** is unique per tenant.
- List price uses NUMERIC and CHECK independently of EAV.

What it fails to guarantee:

- NUMBER attributes actually hold parseable numeric `value_text`.
- BOOLEAN attributes hold valid true/false values.
- Phone storage falls within allowed capacities.
- Required attributes for a category actually have rows.
- Attributes are assigned only to permitted categories.
- Units are normalized or converted properly.
- Multi-valued, temporal, or cross-attribute constraints.
- Read/write access permissions per attribute and consumer.

**FKs verify that a metadata row exists; they do not execute that metadata's business rules.**

### 4.1. Invalid Values Not Blocked by the Demo Schema

| variant | attribute | value_text | value_kind |
| --- | --- | --- | --- |
| P-101 | storage_gb | 128 | NUMBER |
| P-102 | storage_gb | 256 | NUMBER |
| P-103 | storage_gb | 128 GB | NUMBER |
| P-104 | has_nfc | YES | BOOLEAN |
| P-105 | screen_inches | unknown | NUMBER |

The final rows insert cleanly into **variant_attribute_eav** because TEXT accepts anything. Validating solely in the UI is insufficient: bad values still arrive via imports, CDC, repair jobs, legacy APIs, or batch migrations.

## 5. Multi-Attribute Queries: From Columns to Self-Joins

Finding **black phones with at least 128 GB storage and NFC** using a typed `phone_specifications` table:

~~~sql
-- Illustrated after creating phone_specifications in Section 9.
SELECT v.variant_id, v.sku, v.list_price_amount
FROM catalog.variants AS v
JOIN catalog.phone_specifications AS s
  ON s.tenant_id = v.tenant_id
 AND s.variant_id = v.variant_id
WHERE v.tenant_id = $1
  AND v.category_code = 'PHONE'
  AND s.color_code = 'black'
  AND s.storage_gb >= 128
  AND s.has_nfc = TRUE
ORDER BY v.list_price_amount, v.variant_id
LIMIT 20;
~~~

EAV requires joining across multiple rows:

~~~sql
-- Intentionally illustrates CAST risk when value_text is unvalidated.
SELECT v.variant_id, v.sku, v.list_price_amount
FROM catalog.variants AS v
JOIN catalog.variant_attribute_eav AS color_v
  ON color_v.tenant_id = v.tenant_id
 AND color_v.variant_id = v.variant_id
JOIN catalog.attribute_definitions AS color_d
  ON color_d.tenant_id = color_v.tenant_id
 AND color_d.attribute_id = color_v.attribute_id
 AND color_d.attribute_code = 'color_code'
JOIN catalog.variant_attribute_eav AS storage_v
  ON storage_v.tenant_id = v.tenant_id
 AND storage_v.variant_id = v.variant_id
JOIN catalog.attribute_definitions AS storage_d
  ON storage_d.tenant_id = storage_v.tenant_id
 AND storage_d.attribute_id = storage_v.attribute_id
 AND storage_d.attribute_code = 'storage_gb'
JOIN catalog.variant_attribute_eav AS nfc_v
  ON nfc_v.tenant_id = v.tenant_id
 AND nfc_v.variant_id = v.variant_id
JOIN catalog.attribute_definitions AS nfc_d
  ON nfc_d.tenant_id = nfc_v.tenant_id
 AND nfc_d.attribute_id = nfc_v.attribute_id
 AND nfc_d.attribute_code = 'has_nfc'
WHERE v.tenant_id = $1
  AND v.category_code = 'PHONE'
  AND color_v.value_text = 'black'
  AND storage_v.value_text::NUMERIC >= 128
  AND nfc_v.value_text = 'true'
ORDER BY v.list_price_amount, v.variant_id
LIMIT 20;
~~~

**The drawbacks go well beyond verbose SQL:**

1. **Repeated self-joins** to reconstruct logical "columns."
2. Metadata must be joined just to identify which attribute is being read.
3. **storage_v.value_text::NUMERIC** crashes on **"128 GB"** or **"unknown"**.
4. TEXT sorting is lexicographical: **"100"** sorts before **"20"**, not numerically.
5. The query optimizer struggles to estimate wildly different attributes packed in one table.
6. Boolean filters depend on uniform text representations.
7. Renaming an attribute code or changing its type can break queries, indexes, and consumers.

Never drop a regex predicate into WHERE and assume the database always evaluates the regex **before** the cast in written order. SQL optimizers can reorder predicate evaluation; **enforcing typed storage/validators at write time** is far safer.

### 5.1. Pivoting and Grouping Are Not Free Either

You can pivot each attribute into a logical column:

~~~sql
SELECT
    av.tenant_id,
    av.variant_id
FROM catalog.variant_attribute_eav AS av
JOIN catalog.attribute_definitions AS d
  ON d.tenant_id = av.tenant_id
 AND d.attribute_id = av.attribute_id
WHERE av.tenant_id = $1
  AND d.attribute_code IN ('color_code', 'has_nfc')
GROUP BY av.tenant_id, av.variant_id
HAVING
    MAX(av.value_text) FILTER (
        WHERE d.attribute_code = 'color_code'
    ) = 'black'
    AND MAX(av.value_text) FILTER (
        WHERE d.attribute_code = 'has_nfc'
    ) = 'true';
~~~

**MAX** here simply collapses a single-valued attribute through `GROUP BY`; it does not mean "largest color." If an attribute is multi-valued or versioned, grouping must adapt to the grain and version selection rules.

A screen with 15 filters produces a pivot query packed with expressions that must handle missing attributes and types. **Never assume pivoting is automatically faster than self-joins**: verify with EXPLAIN and representative data.

### 5.2. Use EXISTS to Avoid Row Multiplication on Existence Checks

When checking only whether an attribute **exists** with a target value, EXISTS prevents duplicate result rows from multi-valued relations:

~~~sql
SELECT v.variant_id, v.sku
FROM catalog.variants AS v
WHERE v.tenant_id = $1
  AND EXISTS (
      SELECT 1
      FROM catalog.variant_attribute_eav AS av
      JOIN catalog.attribute_definitions AS d
        ON d.tenant_id = av.tenant_id
       AND d.attribute_id = av.attribute_id
      WHERE av.tenant_id = v.tenant_id
        AND av.variant_id = v.variant_id
        AND d.attribute_code = 'color_code'
        AND av.value_text = 'black'
  )
  AND EXISTS (
      SELECT 1
      FROM catalog.variant_attribute_eav AS av
      JOIN catalog.attribute_definitions AS d
        ON d.tenant_id = av.tenant_id
       AND d.attribute_id = av.attribute_id
      WHERE av.tenant_id = v.tenant_id
        AND av.variant_id = v.variant_id
        AND d.attribute_code = 'has_nfc'
        AND av.value_text = 'true'
  );
~~~

EXISTS preserves **existence semantics**, yet does not eliminate EAV lookup cost. Proper indexes and measurements are still required.

### 5.3. Joins Corrupt COUNT and SUM, Not Just Latency

Suppose one variant has:

~~~text
3 tags
4 warehouses
2 campaigns
~~~

Joining all 1:N relationships and EAV rows together yields **3 × 4 × 2 = 24 rows** for one variant. `SUM(list_price_amount)` or `COUNT(*)` over that result no longer measures price totals or variant counts.

**Aggregate each source to the right grain before joining**, use EXISTS for filters, or build a **one-row-per-variant** read projection. Never rely on `SUM(DISTINCT price)` as a general fix, since two variants can share the same price.

## 6. Validation: EAV Moves Constraints From DDL Into Metadata

A column declaration:

~~~sql
storage_gb INTEGER NOT NULL
  CHECK (storage_gb IN (64, 128, 256, 512));
~~~

tells the database its type, requiredness, and allowed values. Turning `storage_gb` into **attribute_code = storage_gb, value_text = "128"** pushes those rules into metadata and application code.

| Invariant | Typed Column | What Generic EAV Must Add |
| --- | --- | --- |
| **Type safety** | INTEGER/BOOLEAN/DATE | Parsing and per-attribute type validation |
| **Non-missing** | NOT NULL | Category/version-aware requiredness checks |
| **Range / allowed set** | CHECK/enum/FK | Owner-governed per-attribute rules |
| **Single value** | PK/UNIQUE | Single vs. multi-valued cardinality rules |
| **Referential integrity** | FOREIGN KEY | Reference types or explicit junction tables |
| **Units** | Explicit unit column/type | Unit metadata + conversions |
| **Cross-field rules** | Domain logic / transactions | Rule engine spanning multiple attribute rows |
| **Effective time** | Range/EXCLUDE | Versioning and non-overlap constraints |
| **Authorization** | Role/view/column grants | Per-attribute access policies and scopes |
| **Indexing** | Typed columns + stats | Generic, expression, or projection indexes |

**Typed schemas do not solve all cross-table invariants automatically either**, yet EAV turns even simple single-field rules into write-layer logic and metadata governance.

### 6.1. What Does a Missing Required Attribute Mean?

Phones require `storage_gb`, yet a variant has no `storage_gb` row. **`value_text NOT NULL` cannot catch this**, because there is no row to check.

You can maintain a rules table:

~~~text
category_attribute_rules:
  tenant_id
  category_code
  attribute_id
  is_required
  min_occurrences
  max_occurrences
  validation_version
~~~

Once that table exists—and assuming required attributes are single-valued—you can find missing values:

~~~sql
-- category_attribute_rules is an extra table
-- not declared in Section 4's minimal schema.
SELECT
    v.tenant_id,
    v.variant_id,
    d.attribute_code AS missing_required_attribute
FROM catalog.variants AS v
JOIN catalog.category_attribute_rules AS r
  ON r.tenant_id = v.tenant_id
 AND r.category_code = v.category_code
 AND r.is_required = TRUE
JOIN catalog.attribute_definitions AS d
  ON d.tenant_id = r.tenant_id
 AND d.attribute_id = r.attribute_id
LEFT JOIN catalog.variant_attribute_eav AS av
  ON av.tenant_id = v.tenant_id
 AND av.variant_id = v.variant_id
 AND av.attribute_id = r.attribute_id
WHERE av.attribute_id IS NULL;
~~~

This checks only **coverage**, not whether values have the right type or fall within allowed bounds. **Rules evolving over time** need versions or effective timestamps to evaluate historical records accurately.

### 6.2. Missing, Null, Unknown, and Not Applicable Are Different

An absent EAV row can mean:

- The attribute is **not applicable** to this category.
- Not yet entered (**unknown**).
- Rejected by validation.
- **Late-arriving** or not yet synced by a pipeline.
- Hidden due to caller permissions.
- Redacted or deleted per retention policy.

**Never insert the literal string "NULL" or "N/A" into TEXT and treat it like SQL NULL.** Model presence/reason explicitly rather than letting dashboards substitute 0 for every absence.

## 7. Types, Units, and the Nature of Measures

A weight attribute accumulates values like:

~~~text
"2.5"
"2500 g"
"2,5"
"2.50kg"
"unknown"
~~~

All intend to express mass, yet differ in **syntax and units**. Summing or comparing raw strings yields garbage.

Serious attribute metadata requires:

- **Type:** integer, decimal, Boolean, text, date, timestamp, enum, or reference.
- **Canonical unit:** kg, g, GB vs. GiB, V, A, °C.
- **Precision:** scale, precision, and rounding rules.
- **Valid ranges and allowed value lists.**
- **Cardinality:** single vs. multi-valued; ordered vs. unordered.
- **Required/optional status by entity type and lifecycle state.**
- **Authoritative source, owner, and write permissions.**
- **Sensitivity classification, API audience, and retention.**
- **Definition version / effective interval.**

If producer A sends **GB** and producer B sends **GiB**, two `128` values do not mean the same quantity. Normalize/convert at ingestion and preserve provenance where needed.

### 7.1. Never Force Financial or Inventory Data Into Generic NUMBER

**captured_amount** is not just a number: it has currency, capture state, payment attempt lineage, idempotency, event time, and reconciliation obligations. **on_hand_quantity** is stock at one warehouse/variant/point in time—never summable across days.

`value_kind = NUMBER` provides none of those invariants. Prices, stock balances, payments, ledgers, and transactions belong in grain-accurate entities, facts, or ledgers—never in EAV just to avoid creating tables.

## 8. Indexes and Statistics: Flexibility Has Physical Costs

Suppose 300,000 variants average 40 populated attributes each:

- Roughly **12 million rows** in the EAV table.
- Each row repeats tenant, variant_id, attribute_id, value_text, and metadata.
- Primary and secondary indexes expand storage, I/O, WAL traffic, and vacuum/maintenance overhead.
- Queries filtering 4–6 attributes repeat lookups and joins multiple times.

You cannot blindly assert EAV always uses more bytes than a wide table across every engine—wide tables depend on NULL overhead, compression, TOAST, indexes, and fill rates. **Measure on representative data.**

### 8.1. Indexes Serve Different Queries

PK `(tenant_id, variant_id, attribute_id)` efficiently loads all attributes of **one variant**.

Filtering variants by attribute and value may call for:

~~~sql
CREATE INDEX ix_eav_attr_text_variant
ON catalog.variant_attribute_eav
   (tenant_id, attribute_id, value_text, variant_id);
~~~

Yet this TEXT index cannot turn `value_text::NUMERIC` into an accurate numeric range index. A table-wide expression index casting to numeric crashes on any non-numeric string and mixes unrelated attributes. With typed EAV, a numeric range index on a NUMERIC column works properly.

A shared generic index still faces:

- TEXT mixing colors, capacities, ISBNs, voltages, emails, and dates.
- Wildly varying selectivity across attributes.
- Optimizer difficulty estimating correlations across attributes of the same variant.
- Write amplification and index bloat on frequent updates.
- Thousands of dynamic attributes inflating **cardinality** and metadata overhead.

Never create indexes blindly for every attribute. Optimize only common predicates backed by SLOs and measurements.

### 8.2. Sorting, Pagination, and Absent Attributes

Sorting `storage_gb` as TEXT puts **"100"** before **"20"** lexicographically. Multi-attribute pagination requires a **deterministic tie-breaker** such as `variant_id`, plus explicit handling for NULL/missing values.

Mutations between two page requests can duplicate or skip rows. If an API promises stable pagination, define snapshots or keyset cursors—never assume `OFFSET` over mutable EAV rows stays consistent.

### 8.3. No Schema Change Does Not Mean Zero Cost

Adding a new attribute increases row writes, index size, search projection rebuilds, UI filter complexity, cache invalidation, and backfill operations. **Skipping `ALTER TABLE` does not make changes cheap**, especially once a new attribute enters core filters, sorting, or business decisions.

## 9. Option A — Typed Columns for Core Attributes

For phones, if **color_code, storage_gb, has_nfc** are stable and frequently filtered:

~~~sql
CREATE TABLE catalog.phone_specifications (
    tenant_id BIGINT NOT NULL,
    variant_id UUID NOT NULL,
    color_code TEXT NOT NULL,
    storage_gb INTEGER NOT NULL,
    has_nfc BOOLEAN NOT NULL,
    screen_inches NUMERIC(4, 2),

    CONSTRAINT pk_phone_specifications
        PRIMARY KEY (tenant_id, variant_id),
    CONSTRAINT fk_phone_specs_variant
        FOREIGN KEY (tenant_id, variant_id)
        REFERENCES catalog.variants (tenant_id, variant_id),
    CONSTRAINT ck_phone_storage
        CHECK (storage_gb IN (64, 128, 256, 512, 1024)),
    CONSTRAINT ck_phone_screen
        CHECK (screen_inches IS NULL OR screen_inches > 0)
);

CREATE INDEX ix_phone_specs_search
ON catalog.phone_specifications
   (tenant_id, color_code, has_nfc, storage_gb, variant_id);
~~~

Benefits:

- INTEGER and BOOLEAN are validated immediately on write.
- NOT NULL and CHECK express clear invariants.
- Native indexing on exact predicates and numeric ranges.
- SQL and APIs are easier to read and reconcile.
- Column additions/changes go through formal migrations and reviews.

Limitations:

- Adding core attributes usually requires schema and code deployments.
- This snippet alone does not prevent attaching `phone_specifications` to a non-PHONE variant: enforce via a category-scoped composite FK or transactional domain validation.
- If hundreds of categories carry distinct traits, dozens of extension tables increase maintenance overhead.

**A category-specific table is not automatically good design**; add one only when it clarifies grain, constraints, and permissions for an established workload.

## 10. Option B — Typed EAV for Flexible Values

When dynamic numeric attributes remain necessary, avoid generic `value_text` via typed value tables. For example, a composite FK ensures only NUMBER-defined attributes enter the numeric table:

~~~sql
ALTER TABLE catalog.attribute_definitions
ADD CONSTRAINT uq_attr_definition_kind
UNIQUE (tenant_id, attribute_id, value_kind);

CREATE TABLE catalog.variant_numeric_attributes (
    tenant_id BIGINT NOT NULL,
    variant_id UUID NOT NULL,
    attribute_id UUID NOT NULL,
    value_kind TEXT NOT NULL DEFAULT 'NUMBER',
    value_numeric NUMERIC(18, 4) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_variant_numeric_attributes
        PRIMARY KEY (tenant_id, variant_id, attribute_id),
    CONSTRAINT fk_numeric_variant
        FOREIGN KEY (tenant_id, variant_id)
        REFERENCES catalog.variants (tenant_id, variant_id),
    CONSTRAINT ck_numeric_kind
        CHECK (value_kind = 'NUMBER'),
    CONSTRAINT fk_numeric_definition_kind
        FOREIGN KEY (tenant_id, attribute_id, value_kind)
        REFERENCES catalog.attribute_definitions
            (tenant_id, attribute_id, value_kind)
);

CREATE INDEX ix_numeric_attr_range
ON catalog.variant_numeric_attributes
   (tenant_id, attribute_id, value_numeric, variant_id);
~~~

Benefits of typed EAV:

- NUMERIC truly enforces numeric storage; **"hello"** cannot enter `value_numeric`.
- CHECK + composite FK ensure only NUMBER attributes bind to the NUMBER table.
- Range filters leverage numeric indexes directly.
- Adding a new attribute does not require adding a new column.

What it **still does not solve**:

- Ensuring `storage_gb` matches approved capacities.
- Distinct valid ranges for voltage, temperature, and battery capacity.
- Canonical units, category applicability, and required fields.
- Multi-valued or temporal relationships.
- Per-attribute permissions, metadata versions, and consumer compatibility.
- Overlap when an attribute temporarily spans TEXT and NUMBER tables during migrations.

A typed query:

~~~sql
SELECT v.variant_id, v.sku,
       n.value_numeric AS battery_capacity_mah
FROM catalog.variants AS v
JOIN catalog.variant_numeric_attributes AS n
  ON n.tenant_id = v.tenant_id
 AND n.variant_id = v.variant_id
JOIN catalog.attribute_definitions AS d
  ON d.tenant_id = n.tenant_id
 AND d.attribute_id = n.attribute_id
WHERE v.tenant_id = $1
  AND d.attribute_code = 'battery_capacity_mah'
  AND n.value_numeric >= 4000
ORDER BY n.value_numeric, v.variant_id;
~~~

**Typed EAV solves part of the typing and casting pain, without eliminating the cost of metadata-driven modeling.**

## 11. Option C — JSONB / Documents for Optional Properties

Another option places flexible attributes that are rarely joined or filtered inside a JSONB object tied to the variant:

~~~sql
CREATE TABLE catalog.variant_optional_properties (
    tenant_id BIGINT NOT NULL,
    variant_id UUID NOT NULL,
    properties JSONB NOT NULL,

    CONSTRAINT pk_variant_optional_properties
        PRIMARY KEY (tenant_id, variant_id),
    CONSTRAINT fk_optional_properties_variant
        FOREIGN KEY (tenant_id, variant_id)
        REFERENCES catalog.variants (tenant_id, variant_id),
    CONSTRAINT ck_optional_properties_object
        CHECK (jsonb_typeof(properties) = 'object')
);

CREATE INDEX ix_optional_properties_gin
    ON catalog.variant_optional_properties
    USING GIN (properties jsonb_path_ops);
~~~

An illustrative object:

~~~json
{
  "waterproofRating": "IP67",
  "releaseRegion": "VN",
  "supportedLanguages": ["vi", "en"]
}
~~~

A containment predicate can leverage this GIN index:

~~~sql
SELECT variant_id
FROM catalog.variant_optional_properties
WHERE properties @> '{"releaseRegion":"VN"}'::jsonb;
~~~

**What advantages does JSONB offer over multi-row EAV?**

- Optional attributes typically read together stay in one document.
- JSON distinguishes **number, string, Boolean, array, object, and null** instead of flattening everything to TEXT.
- Supports JSON operators and GIN indexes for suitable queries.
- Rare fields can be added without altering relational columns.

**What problems remain?**

- One producer can write `storageGb: "128"` while another writes `storageGb: 128`—different JSON types.
- Typos, missing required fields, invalid ranges, and inconsistent units still slip in.
- JSONB GIN `jsonb_path_ops` optimizes containment operators (`@>`), **not arbitrary `->>` lookups**, numeric sorting, or range scans—those may require typed expression indexes or dedicated columns.
- Updating one key can cause write conflicts when multiple producers edit the same document.
- Large uncontracted objects risk mixing PII, secrets, and public fields.
- Feeding data into analytics still demands flattening, grain validation, and metric definitions.

**JSONB is flexible storage, not an automatic business validator.** It suits sparse, lightly filtered properties; critical fields still need constraints or authoritative schema validation.

## 12. Comparing Approaches Against Real Needs

| Criterion | Typed Relational Columns | EAV TEXT | Typed EAV | JSONB / Document |
| --- | --- | --- | --- | --- |
| Critical, stable attributes | Strong fit | Hard to govern | Viable, heavy mapping | Needs external validation |
| Rare, fast-changing attributes | Causes frequent DDL | Flexible | Flexible with better typing | Flexible, convenient object reads |
| Frequent numeric range filters | Clear typed indexes | Cast/error risk | Numeric index | Expression index / projection |
| Required / unique / allowed sets | Explicit DDL | Metadata + validator | Typed, still needs rules | JSON schema / app / constraints |
| True multi-valued / relations | 1:N / N:M child tables | Needs extra grain | Needs extra grain | Arrays need custom FK/ordering |
| Search across 6 attributes | Concise SQL, clear indexes | Many joins/pivots | Many joins/pivots | JSON extraction + matching indexes |
| Grain-accurate reporting | Natural in SQL | Requires pivot | Requires pivot | Requires flattening + dictionary |
| Field evolution | DDL migration | Metadata/data migration | Metadata/data migration | Document/schema migration |
| Field-level permissions | Roles/views/APIs | Per-attribute policy | Per-attribute policy | Per-key policy and contract |
| Operational cost | Migrations for core edits | Row/index growth | Multiple tables + validators | Schema drift, indexes, doc writes |

No single column wins everything. A **hybrid** model is often the best balance:

~~~text
Core entities + domain relations:
  IDs, tenant, statuses, prices, inventory, business commands

Typed category extensions:
  common attributes with strict rules

Flexible attributes:
  rare, sparse traits with metadata/validators

Read model / search projection:
  one row per variant for key filters, sorting, and pagination

Analytics:
  grain-accurate facts/dimensions, metric definitions, lineage
~~~

For small workloads, do not introduce typed EAV, JSONB, and a search engine all at once. **Add layers only when justified by use cases and measurements.**

## 13. EAV vs. Other Data Models: Semantic Boundaries

### 13.1. Relational

Relational schemas place PK/FK, UNIQUE, CHECK, NOT NULL, types, and indexes directly on columns, letting the database enforce many invariants natively.

EAV is **a pattern built on top of a relational database**, not an alternative data model. Judge it on **data integrity and workload**, not slogans like "SQL is inflexible."

### 13.2. Document

Documents store dynamic properties inside objects or subdocuments, yet still need rules for:

- Document and nested-array grain.
- IDs, versions, schemas, and units.
- Which consumers may read each key.
- Indexes supporting required filters.
- References outside the document to avoid uncontrolled history copies.

Storing an `authors` array in JSON does not automatically create a validated Author–Book relationship. If you need many-to-many queries, uniqueness, and author roles, a dedicated collection or relational junction table may be required.

### 13.3. Graph

Graphs excel at expressive links like **Customer–PLACED–Order**, **Product–BELONGS_TO–Category**, and **Device–INSTALLED_AT–Site**. Yet a generic **RELATED_TO** edge carrying a **value** property loses semantics. Flattening every event and relationship into node **attribute_value** entries erases edge direction, cardinality, permissions, and effective time.

**Single-valued node properties** differ from **relationships between entities**. Never use EAV to avoid modeling real graph edges.

### 13.4. Analytical / Columnar

Warehouses typically need:

~~~text
fact_order_line_confirmed:
  tenant_id, order_id, line_no, variant_id
  quantity, line_net_amount, confirmed_at, currency_code

dim_product_variant:
  variant_key, variant_id
  storage_gb, color_code, has_nfc
  effective_from, effective_to
~~~

When catalog data lives in EAV, pipelines can pivot **verified** attributes into typed dimensions. Decide explicitly:

- Is the dimension grain one current variant or one **version** of a variant (SCD Type 2)?
- Are attributes captured **as of purchase time** or pulled from current values?
- How do you prevent joining facts to multiple dimension versions without as-of bounds and multiplying revenue?
- Which attributes are needed for reporting and permitted for export?
- How do null/missing/unknown states map into the dimension?

An **on_hand_quantity** attribute is an inventory snapshot—never sum it across days like a transaction flow. Storing `value_numeric` in EAV never turns a state into a flow.

## 14. Evolving Metadata Is Also Schema Evolution

Product wants to rename **storage_gb** to **storage_capacity_gib**. In EAV, it looks like updating one metadata row. Yet GB and GiB are different units; renaming without converting numbers silently corrupts interpretation.

Furthermore:

- APIs and search filters still use the old `attribute_code`.
- Caches and projections hold old field names.
- ETL and analytics pivot by code.
- Indexes and validators may assume old NUMBER semantics and allowed values.
- Older rows may still use different units under the same code.
- Exposure permissions may shift with sensitivity changes.
- Historical transactions must remain readable under the definition active when recorded.

### 14.1. Attribute Definitions Need Governance, Not Just Names

An extended metadata contract may look like:

~~~text
attribute_definition:
  attribute_id           -- stable ID within the published scope
  attribute_code         -- name used by consumers
  value_kind
  canonical_unit
  allowed_values
  range_min, range_max
  applicable_categories
  is_required
  is_searchable
  sensitivity_class
  source_of_truth
  owner
  definition_version
  effective_from
  effective_to
~~~

Not every system needs every field, yet fields governing validation, permissions, and compatibility cannot be neglected.

**Metadata changes can be just as breaking as `ALTER TABLE`.** Follow **expand → migrate data/validators → validate → switch readers/writers → retire legacy structure**.

### 14.2. Distinguish Types of Metadata Changes

| Change | Meaning | Appropriate Action |
| --- | --- | --- |
| **colour → color_code** | Potentially pure rename | Alias/version if underlying values match |
| **weight_kg → weight_g** | Unit change | Verified conversion, precision, provenance |
| **TEXT → NUMBER** | Type change | Parse, quarantine invalid rows, backfill |
| **product-level → variant-level** | Grain change | New relationship and explicit allocation |
| **single → multi-valued** | Cardinality change | Keys/value_id/position or junction table |
| **current → historical** | Temporal axis change | Versioning / effective intervals |
| **public → restricted** | Permission change | Revoke from public APIs, indexes, logs, exports, consumers |

Renaming **storage_gb** to **battery_capacity_mah** is not a valid rename merely because both are numbers. **Attribute IDs must bind to stable semantics**, never reused for a different concept.

## 15. Security: A Generic EAV Table Can Become a Data Backdoor

An admin creates custom attributes:

~~~text
customer_email
recipient_phone
internal_supplier_cost
fraud_review_score
access_token
private_note
~~~

If the catalog API returns **every attribute** to external callers, sensitive data leaks without adding a single table column.

Controls required:

- **Authorization over metadata creation/editing** and sensitivity classification.
- **Public field allowlists per consumer and purpose**—never expose `SELECT *`.
- **Object-level authorization** by tenant and entity; unguessable UUIDs are not access control.
- **Attribute-level policies** when field groups carry distinct read permissions.
- **Value and length validation** on every write path, including imports and batch jobs.
- **Quotas on attributes per tenant**, row counts, and value lengths to prevent unbounded cardinality.
- **Auditing and retention** aligned with data classification.
- **Logs, CDC streams, event buses, DLQs, caches, search indexes, exports, and backups** all leak EAV values if unredacted.
- **Never store secrets in EAV** without dedicated cryptographic protection and access isolation.

Composite PKs/FKs ensure cross-tenant referential boundaries, yet never restrict **who inside a tenant may SELECT which attributes**. When public and restricted attributes share a table, filter them on the backend before serialization—never ship the full JSON to the frontend and hide fields in UI code.

## 16. Search Projections: Fast Reads Create Sync Responsibilities

If search constantly filters on **color, storage, has_nfc, price**, create a one-row-per-variant read projection:

~~~text
catalog_search_projection:
  tenant_id
  variant_id
  sku
  category_code
  color_code
  storage_gb
  has_nfc
  list_price_amount
  currency_code
  source_variant_version
  projected_at
~~~

Advantages:

- Typed columns, clean indexes, straightforward sorting and pagination.
- Eliminates multi-way self-joins on high-traffic read paths.
- EAV or JSONB can still hold rare optional attributes.

New costs:

- Every source update must propagate to the projection.
- **Replication lag** under asynchronous pipelines.
- Duplicate/out-of-order messages require **idempotency and version checks**.
- Metadata changes require projection migrations or rebuilds.
- Deleting an EAV attribute must clear/NULL the projected field rather than leaving stale values forever.
- Requires **watermarks, freshness SLOs, reconciliation, and access controls**.

**Projections never hold authority to create new business truth.** When inventory or pricing guards critical transactions requiring immediate consistency, read from the authoritative source rather than a potentially stale search index.

### 16.1. Reconciling Flexible Metadata Against Typed Projections

A reconciliation workflow should:

1. Fix the tenant/variant scope and source checkpoint.
2. Parse and convert units using the matching metadata version.
3. Compare typed source values against the projection at the same version.
4. Detect **missing, extra, and mismatched values**, including deleted attributes.
5. Quarantine invalid records rather than substituting 0 or default strings.
6. Recompute or backfill from authoritative sources.
7. Verify permissions: restricted fields must never leak into public projections.

Do not treat transient differences within the normal lag window as permanent corruption, nor excuse infinite lag as normal operation.

## 17. Decide With Workloads, Not With "Flexibility" Gut Feelings

Suppose:

- **300,000 variants**, averaging **40 populated attributes/variant** ⇒ roughly **12 million EAV rows**.
- 80% of detail views read the same 20 common fields.
- Search UI filters 6 attributes and sorts by storage or price.
- New optional attributes appear weekly, while the 6 core search filters rarely change.
- Analytical dashboards need variant-grain or order-line-grain facts.

The table below uses **purely hypothetical numbers for comparison practice**, not production benchmarks:

| Approach | Illustrative Search p95 | Notable Costs |
| --- | ---: | --- |
| Direct EAV TEXT | 420 ms | Self-joins, cast risks, dirty data, bloated indexes |
| Typed EAV | 230 ms | Complex validators/rules and pivoting |
| Typed columns for 6 core filters | 85 ms | Migrations when core columns change |
| EAV + search projection | 70 ms | Pipeline ops, lag, replay, reconciliation |
| JSONB for optional fields | 160 ms | Schema/key drift and specialized indexes |

**Never choose solely on p95.** Also measure p99, concurrent load, CPU, I/O, data/index footprint, ingest throughput, WAL volume, update cost, validation failures, rebuild duration, and access controls.

### 17.1. A Practical Benchmark Suite

1. Read full detail of a variant with 20 attributes.
2. Search with 2, 4, and 6 filters of varying selectivity.
3. Numeric range filter + sort with stable pagination.
4. Update a common attribute; measure index write amplification and projection lag.
5. Batch-import records with bad types, units, and missing required fields.
6. Delete an attribute; verify caches, projections, and analytics reflect removal.
7. Query across categories with sharply different attribute sets.
8. Verify COUNT/SUM correctness when joining multi-valued traits.
9. Bump a metadata version and test migration/rollback.
10. Query under a restricted role to confirm zero leakage of restricted attributes.

Run `EXPLAIN (ANALYZE, BUFFERS)` on production-like distributions. Fast SQL on 20 sample rows proves nothing for 12 million rows.

## 18. Migrating From Over-Generic EAV to an Intentional Model

A legacy system stores everything in EAV: **prices, colors, capacities, inventory, notes, and custom fields**. The team wants to keep flexible attributes while moving core facts to typed tables.

Process:

1. **Inventory data:** attribute codes, types, counts, fill rates, value distributions, categories, owners, PII, consumers.
2. **Lock down grain and authority:** product, variant, warehouse inventory, order line, payment? Never cross scopes.
3. **Classify fields:** core fields, category-specific typed fields, optional metadata, derived fields, restricted data.
4. **Design target schema:** PK/FK, NOT NULL, CHECK, units, currencies, indexes, permissions, retention.
5. **Expand:** deploy new tables/columns while keeping legacy EAV live.
6. **Backfill with validation:** handle malformed text, unit conversions, duplicates, and missing values; route errors to quarantine for decisions.
7. **Switch write paths cleanly:** one authoritative writer, avoiding uncoordinated dual-writes.
8. **Shadow read:** compare detail payloads, filters, sorts, metrics, and access controls.
9. **Phased cutover** with telemetry, fallbacks, and rollback/roll-forward plans.
10. **Reconcile:** compare values, coverage, counts, and sums at matching grain and currency.
11. **Retire legacy writers** and drain queued events/replays.
12. **Contract:** drop EAV core fields once zero consumers remain, retention permits, and verification passes.

### 18.1. Never Coerce Bad Values to Zero

A `storage_gb` attribute holds:

~~~text
"128"
"128.0"
"128 GB"
"128GiB"
"unknown"
~~~

Never `INSERT` unparseable entries as `0` and declare migration done. Instead:

- Choose canonical units and documented conversion rules.
- Define numeric parsing, decimal precision, and rounding.
- Distinguish **missing**, **unknown**, and **invalid**.
- Flag records ineligible for publishing if required values are missing.
- Maintain a remediation queue for authoritative owners.
- Enforce a **cutover quality gate** and re-reconcile after fixes.

### 18.2. Preserve Transaction History

If **size_code**, color, price, or variant configuration participated in a confirmed OrderLine, historical records must preserve **the price, variant, and snapshot at transaction time**. Querying live EAV values when rendering old invoices falsifies history.

Maintain approved snapshots, source events, or SCD Type 2 / as-of dimensions per business rules; metadata renames must never rewrite historical evidence.

## 19. Pre-Deployment EAV Review Checklist

| Question | Required Evidence |
| --- | --- |
| What are the entity and grain of one value? | Single/multi, tenant, temporal scope |
| Which core attributes are stable? | Business invariants and access patterns |
| How often are new fields genuinely added? | Historical schema change frequency |
| Is the data truly sparse? | Fill rates by category |
| Are numeric range filters or sorts needed? | Query workload and indexes |
| Where are types enforced? | Typed storage, validators, and tests |
| How are required and allowed values checked? | Versioned metadata and coverage checks |
| Are real relationships hidden inside values? | PK/FK, N:M, domain entities |
| What do NULL and missing mean? | Unknown, not applicable, or withheld |
| Are any attributes multi-valued? | Value ID/position or junction tables |
| Is effective time tracked? | Versioning, intervals, as-of semantics |
| How are PII and secrets protected? | Attribute allowlists, auth, retention |
| Does analytics preserve grain? | Anti-fan-out and additivity rules |
| What happens when metadata changes? | Contract versioning and migrations |
| Are projections rebuildable? | Authoritative source, checkpoints, idempotency |
| Were alternatives benchmarked? | p95/p99, storage/index bytes, write cost |
| Who owns governance? | Named owner for metadata, schemas, and SLOs |

## 20. Practice Exercises

### Exercise 1 — NUMBER Metadata With Arbitrary TEXT

`storage_gb` has metadata NUMBER, while `value_text` holds **"128"**, **"256"**, **"128 GB"**, and **"unknown"**.

**Question:** do FKs guarantee type validity? What breaks with `ORDER BY value_text` and direct `CAST`?

### Exercise 2 — Missing Required Attribute

PHONE requires `has_nfc`, yet variant P-101 has no `has_nfc` row.

**Question:** why do EAV PK and NOT NULL constraints still pass? What rule and coverage check are needed?

### Exercise 3 — Multiple Authors in One String

A book EAV row stores **authors = "An, Binh, Chi"**. Later, the business needs book counts per author and co-author ordering.

**Question:** which relationship and grain are missing?

### Exercise 4 — Six Search Filters

The UI filters on color, storage, NFC, screen size, battery, and release region, then sorts by storage.

**Question:** what are the costs in EAV TEXT? When should you move to typed columns, typed EAV, or a read projection?

### Exercise 5 — Join Multiplying Measures

One variant has three tags and two campaigns. A report joins both and runs `SUM(list_price_amount)`.

**Question:** why does the sum multiply? How do you preserve grain?

### Exercise 6 — JSONB Type Drift

One producer writes **storageGb: "128"** and another writes **storageGb: 128** into JSONB.

**Question:** is JSONB alone sufficient? Which contracts and validators are needed?

### Exercise 7 — Inventory Over Time

Yesterday `on_hand_quantity=25`, today `=20`. A dashboard sums both snapshots and reports current stock as 45.

**Question:** what measure-type error occurred? How should balances and movements be modeled?

### Exercise 8 — Changing Units

Metadata renames **weight_kg** to **weight_g** while leaving the stored value as 2.5.

**Question:** why is this more than a rename? What is the right migration path?

### Exercise 9 — EAV Mixing PII With Public Data

An admin creates **recipient_email** and **internal_supplier_cost**. The public API returns all attributes.

**Question:** what is the leak path and which controls are missing?

### Exercise 10 — Analytics Reading Current Dimensions

A warehouse pivots **current** EAV attributes and joins them to 3-year-old sales facts to report product color at purchase time.

**Question:** why can the results be wrong? How should history be stored?

### Exercise 11 — Choosing an Architecture

100,000 variants: 95% always carry `color_code`, `storage_gb`, and `has_nfc`; 90% of searches filter on those three. Only a few rare fields are added monthly.

**Question:** which model fits best and what should be measured?

### Exercise 12 — 2% Backfill Parse Failures

Migrating `storage_gb` to INTEGER fails to parse 2% of rows. The team plans to set those rows to 0 and cut over.

**Question:** is that acceptable? Propose a cutover gate and remediation plan.

### Exercise 13 — Attribute Rename Breaking Consumers

Metadata renames `color_code` to `colour`, while APIs, caches, and ETL still expect `color_code`.

**Question:** is this a breaking schema change at the contract level? How do you maintain compatibility?

### Exercise 14 — Typed EAV Still Allows Invalid Domain Values

A typed numeric table allows `battery_capacity_mah = -500`, while `temperature_celsius = -5` in the same table is completely valid.

**Question:** why can't a table-wide `CHECK(value_numeric >= 0)` fix this? What rules or design are needed?

### Solution Hints

1. FKs only confirm the attribute exists; they do not validate `value_text` against `value_kind`. TEXT sorts lexicographically and direct casts crash on dirty text. Use typed storage/validation and normalize units before querying.
2. Absent rows never violate NOT NULL on nonexistent rows. Use versioned `category_attribute_rules` and verify required coverage before publishing.
3. Author is its own entity; books and authors form an N:M `book_authors` relationship with PK/FK and `author_order`/role. Comma-separated strings are not trustworthy relationships.
4. EAV TEXT incurs self-joins/pivots, type risks, and weak statistics. Move core filters to typed `phone_specifications`, keep rare fields in typed EAV/JSONB, and add a read projection if workload/SLOs demand it.
5. Joining 3 × 2 yields 6 rows per variant. Use `EXISTS` for filtering or aggregate each relationship before joining; never sum header prices after fan-out.
6. No. JSONB preserves JSON types yet does not stop producers from sending inconsistent types. Add JSON schemas/validators, required/range/unit rules, and compatibility tests.
7. `on_hand_quantity` is a **snapshot**, non-additive across time. Model balances by SKU × warehouse × time plus a movement ledger for inflows/outflows, selecting the proper period-end snapshot.
8. 2.5 kg is not 2.5 g. You need unit conversion, metadata versioning, precision rules, mapping, and consumer updates—never rename and reinterpret old numbers silently.
9. Public and restricted attributes are mixed in responses. Add metadata creation permissions, sensitivity tags, field allowlists, tenant/object/attribute authorization, audits, and copy governance.
10. Current values need not match purchase-time values. Store snapshots on OrderLine or maintain SCD Type 2 / temporal dimensions with as-of joins.
11. Favor typed columns for the three stable, heavily queried fields; keep rare traits in EAV/JSONB. Measure p95/p99, index footprint, write cost, validation error rates, and migration overhead.
12. Never fabricate 0 for unknown/invalid values. Classify failures, quarantine them, remediate at the authoritative source, track coverage, and pass the validation gate before cutover.
13. Yes: metadata acts as application-level schema. Use aliases/versioning, dual-read support, coordinated writer/ETL/cache updates, and consumer tracking before retiring old names.
14. Domain bounds vary per attribute: negative Celsius is valid while negative battery capacity is not. Enforce governed per-attribute metadata validation and/or typed columns with domain-specific CHECKs rather than an incorrect table-wide CHECK.

## 21. Key Takeaways

**EAV turns attributes into data for flexibility, yet does not eliminate data modeling.** It shifts part of the schema into **metadata, validators, joins/pivots, indexes, access controls, and evolution workflows**. One `INSERT` to add an attribute looks cheap; the total lifecycle cost of keeping that attribute accurate and queryable is not.

Sound EAV must answer: **what is the entity, what is the grain of each value, where are types/units/required/allowed values enforced, who has read/write authority, which filters must be fast, and what happens when metadata changes**.

**Use typed relational tables/columns for core facts**—especially identities, prices, payments, inventory, statuses, transaction records, and business invariants. Use **typed EAV or JSONB for genuinely dynamic, sparse, governed extensions**, and introduce search projections when workload measurements justify them.

Before choosing EAV, ask: **"How frequently do we truly add attributes, and what cost are we willing to pay to validate, search, aggregate, secure, evolve, and recover them?"** A good model is not merely **easy to append fields to**, but **easy to interpret accurately and hard to misuse**.
