# Business Keys, Surrogate Keys, and Descriptive Attributes of a Dimension

## 1. The problem: one product with multiple names, codes, and classification versions

In the **DATABASE_DATA_MODELING** module, good design must translate business requirements into entities, relationships, keys, constraints, and physical schemas that can be explained, verified, and evolved. For the **Dimension Tables** chapter, the key question is not merely "what columns does the product table have?", but rather:

> When a product changes its name, brand, or category, should historical transactions link to the **logical product** or to the **descriptive version of the product at the time of the transaction**?

Suppose a product has code **P01** in the ERP system:

- From 2026-01-01 until before 2026-08-01, the product belongs to category **FOOD**.
- From 2026-08-01 onward, the business moves it to category **GIFT**.
- Sales line **L-501** on 2026-07-15 and sales line **L-502** on 2026-08-15 both sell the same logical product P01.
- A report **by category at the time of sale** needs to place L-501 in FOOD and L-502 in GIFT.

If the product dimension table only has a single row for P01 with the current category GIFT, July's report will be rewritten under the new category. If a new business product code is created every time the category changes, continuity of the same product is lost.

To avoid both mistakes, we must distinguish:

1. **Business/natural key**: identifies an object within the scope of the source system.
2. **Surrogate key**: identifies a row in the dimensional model; with SCD Type 2, this is typically **one version** of the object.
3. **Descriptive attributes**: information used to filter, group, display, and interpret events along a dimension, such as name, brand, category, and region.

A complex system may also have a **durable key** for an entity to connect multiple versions of the same object without confusing it with the version key. This lesson explains when that key layer is useful, rather than assuming every system must use all three key types.

**Goal:** design dimension tables at the right grain; choose keys and uniqueness scopes; understand the difference between source IDs and surrogate keys; build attribute history with SCD; bind facts to the right version; and handle duplicate source codes, late-arriving data, unknown members, and data quality checks.

## 2. What does a dimension table hold and what questions does it answer?

A **dimension table** describes the entities or context by which a measure needs to be analyzed. It provides meaning to a **fact table**, which stores measurements at a defined grain.

Example:

~~~text
fact_sales_line
  source_line_id = L-501
  sale_date = 2026-07-15
  product_version_key = 101
  quantity = 2
  net_amount = 180000 VND

dim_product
  product_version_key = 101
  product_business_key = P01
  product_name = Nutrition Cake
  category_code = FOOD
  category_name = Food
~~~

From a measure of **180,000 VND**, the dimension enables querying revenue by category, brand, product group, or other attributes.

| Concept | Example | Purpose |
|---|---|---|
| **Fact** | A recorded sales line | Store measurements and keys to dimensions |
| **Measure** | Quantity, net revenue, cost of goods sold | SUM, COUNT, or compute metrics |
| **Dimension** | Product, customer, store, date | Filter, group, drill-down |
| **Dimension attribute** | Category, brand, region, segment | Explain measurements |
| **Business key** | ERP/P01 | Identify the product according to the source |
| **Version surrogate key** | product_sk = 101 | Identify a descriptive row with specific validity |

Dimension tables typically have **many descriptive attributes, few measurements**, and usually fewer rows than fact tables. However, this is a common characteristic, not a law. A customer or device dimension can be very large and change frequently.

### 2.1. The grain of a dimension must also be declared

For a dimension that does not store history (Type 1), one row can be:

> One logical product described using the latest known information.

For SCD Type 2, one row is:

> One **descriptive version** of a logical product, valid over a defined date range.

Two different grains lead to two different unique keys. If the grain has not been defined, debates over PRIMARY KEY, UNIQUE, and JOIN have no foundation.

## 3. Business key: the ID the source system understands

A **business key (BK)** is a code or set of attributes used by a business source system to identify an object.

Examples:

- Product code **P01** in the ERP system.
- Customer code **C-482** in the CRM.
- Store code **HCM-07** in the retail system.
- Branch code + account number in a banking system.
- Legal entity code + contract number in a multi-company platform.

A business key can be a **natural key** that already exists in the business domain, or an identifier issued by a source system. What matters is that it **has semantics for identifying an object within a defined scope**, not necessarily that it was manually assigned by humans.

### 3.1. Uniqueness scope: is P01 truly global?

If ERP Vietnam and ERP Thailand both have a product with code P01, these two codes do not automatically represent the same product.

A complete business key might be:

~~~text
(tenant_id, source_system, product_bk)

(1, "ERP-VN", "P01") ≠ (1, "ERP-TH", "P01")
(1, "ERP-VN", "P01") ≠ (2, "ERP-VN", "P01")
~~~

When modeling, you must ask:

1. Who issues the code, and within what scope is it unique?
2. Can a code be reused after a product is discontinued?
3. Can a product change its business code?
4. Can two sources use two different codes for the same object?
5. Can the code's formatting change due to whitespace, letter case, or leading zeros?
6. Are there multiple tenants, legal entities, countries, or namespaces that need to be separated?

A standalone **UNIQUE(product_bk)** constraint may be wrong if the code is only unique within **(tenant, source)**. Conversely, putting too many columns into the key can create two different records for the same product when the source changes a non-identifying field.

### 3.2. Business keys must be normalized carefully

The string **"0012"** is not necessarily equal to **"12"**. If a product code has meaningful leading zeros, do not convert the code to an integer.

The two strings **"p01"** and **"P01"** may be treated as the same or different objects depending on the source's rules. Normalization, collation, and lookup rules must be agreed upon before defining a unique constraint. Do not blindly convert every BK to uppercase if the source is case-sensitive.

When sources use codes with hyphens, spaces, or prefixes, ETL must separate the **raw code** from the **normalized code** if reconciliation is needed. Lossy normalization must not be treated as harmless simply because a JOIN runs.

### 3.3. Business keys are not always stable forever

A store is renumbered from **HCM-07** to **HCM-107**; a customer has profiles merged; a product moves to a new ERP and receives a new code. This creates two separate needs:

- Retain **all previously used code values** to look up source documents.
- Still recognize that this is **one logical object** after the code change, if confirmed by the business.

If a BK change breaks historical linkage, an alias/crosswalk mapping table or a governed durable key is required. Do not merge two codes automatically just because product names look similar; identity merging requires a verification process.

## 4. Surrogate key: the internal ID of a dimension row

A **surrogate key (SK)** is a key assigned by the data model to identify a row, without depending directly on how the business code is written.

Example:

| product_sk | product_bk | category_code | Validity |
|---:|---|---|---|
| 101 | P01 | FOOD | [01/01, 08/01) |
| 102 | P01 | GIFT | [08/01, open-ended) |

Both rows share BK P01 but have **different product_sk values**, because they are two descriptive versions from two periods.

**product_sk = 101** does not mean the product is ranked 101st, belongs to category 101, or was sold before products with larger numbers. It is the technical ID of **one dimension version**.

### 4.1. Why should a fact reference the version surrogate key?

If the sales line fact only stores product_bk = P01 and joins to all dimension rows by P01, one transaction can match both the FOOD and GIFT versions. The JOIN result experiences **row multiplication**, double-counting revenue.

If the fact stores **product_sk = 101**, resolved according to the sale date, each line references one definite descriptive version.

~~~text
L-501, date 2026-07-15, product_sk=101 → FOOD
L-502, date 2026-08-15, product_sk=102 → GIFT
~~~

A foreign key from the fact to product_sk guarantees that the referenced dimension row exists. However, **an FK alone does not prove** that the version was valid on the sale date; ETL and data quality checks must validate the temporal condition.

### 4.2. Pros and cons of surrogate keys

| Pros | Trade-offs |
|---|---|
| Independent of source code renames or format changes | Requires a BK → SK lookup/mapping step |
| Allows multiple SCD2 versions of one object | Must avoid using MAX(SK) to infer current state |
| Fact FK is simple, fixed, and typically compact | Requires managing Unknown/unresolved members |
| Supports multi-source integration via mapping | Requires policies against accidental identity merging |
| Isolates the analytics system from source codes | Increases ETL and data reprocessing complexity |

Not every dimension is **required** to have a surrogate key. For an immutable date dimension with an integer key YYYYMMDD and simple relationships, a convention-based date_key can suffice. However, with SCD2 or multi-source integration, surrogate keys generally make the design clearer and safer.

### 4.3. Do not use auto-incrementing numbers as a measure of time

SK 102 being greater than 101 **does not prove** that version 102 has a later effective date in every case. A retroactive decision can be loaded later and receive a larger SK even though it applies to an earlier validity period.

Never use **MAX(product_sk)** as a general rule to retrieve the currently effective version. Use the **effective validity interval** or a clearly defined version condition.

## 5. Durable key: stable at the entity level, distinct from the version key

In data warehouses with SCD2, it is sometimes necessary to distinguish:

1. **Business key**: the source code within the source namespace, e.g., (tenant 1, ERP, P01).
2. **Durable key**: the internal ID of **one logical product**, unchanged across versions.
3. **Version surrogate key**: the internal ID of **one descriptive version**.

Example:

| tenant | source | product_bk | product_dk | product_sk | Category |
|---|---|---|---:|---:|---|
| 1 | ERP | P01 | 7 | 101 | FOOD |
| 1 | ERP | P01 | 7 | 102 | GIFT |

**product_dk = 7** links the two rows as the same logical product. **product_sk** is what the fact uses to bind to a historical version.

A durable key must not be confused with a key that is "eternally immutable under every circumstance." If two profiles are merged or one profile is split after investigation, an **identity resolution** policy and mapping history are still needed so source lineage is not erased.

A durable key can be implemented via a separate **product_identity** table, or as a repeated durable_key column across version rows with a governed assignment/reconciliation process. This lesson uses a separate table to provide a stable row for locking during SCD2 updates.

## 6. Descriptive attributes of a dimension: what is grouped, filtered, and displayed

A product table may contain:

- **Identification and display**: product code, name, short name.
- **Classification**: category_code, category_name, department, product group.
- **Brand**: brand_code, brand_name.
- **Characteristics**: size, color, material, packaging type.
- **Operational attributes**: discontinued flag, launch date, item type.
- **Derived attributes**: price band or customer age band at a defined period.
- **Governance/support attributes**: source, load timestamp, decision_ref, verification status.

These fields can be used for **drill-down**, filtering, and grouping. They are **not necessarily measures** even if they have a numeric data type.

| Attribute | Role | Further considerations |
|---|---|---|
| product_name | Display label | Should fixing a typo create an SCD2 version? |
| category_code | Group code | Does it change over time? |
| category_name | Group label | Is it multilingual or subject to renaming? |
| brand_code | Brand grouping | Can brand ownership be transferred? |
| package_size | Specification | Is it an SKU attribute or does it need a unit of measure? |
| color_code | Product variant | Does it make the SKU a different logical object? |
| launch_date | Business milestone | Calendar date by market or timestamp? |
| price_band | Derived grouping | Based on which price list, at what point in time? |
| loaded_at | ETL metadata | Not the date the product became effective |

### 6.1. Choose the grain before adding attributes

If product P01 has three color/size variants, **color** may be an attribute of an SKU variant, not a single-valued attribute of the product master. Stuffing all colors into one P01 row creates multi-valued fields or lists that are hard to filter and easily corrupt the grain.

You can choose:

~~~text
Product (product model) 1 -- N ProductVariant/SKU
~~~

Then the sales fact typically references the **specific SKU**, not only the product master, if each variant has its own price and inventory.

**There is no single "product" dimension table that fits every need.** You must decide whether sales, inventory, and returns facts are measured at the grain of SKU, product family, or commercial product.

### 6.2. Descriptive attributes can change at different cadences

Fixing a typo in a product name, changing a category for merchandising strategy, and changing a tax class due to regulations have different lifecycles. If every minor change snapshots the entire dimension, the table bloats and facts must deal with dense versioning.

Classify the level of history required:

- **Immutable or near-immutable**: standardized country codes under governance.
- **Changes, but the new value should appear in all periods**: fixing a product name typo.
- **Changes, and state at transaction time must be preserved**: category, customer segment, sales region.
- **Multiple concurrent values**: multiple tags/categories — requires an associative or bridge table.
- **Attributes needing independent history**: market selling price, promotional programs, regulatory status.

Do not force every kind of change into a single SCD Type 2 if they require different relationships, ownership, or validity rules.

### 6.3. Code and label are not the same attribute

**category_code = FOOD** is usually suited as a stable classification value; **category_name = Food** is a display label that may be translated into other languages.

For multilingual reporting, consider a locale-based label table or a dedicated semantic layer rather than repeating multiple language names on every version. If a category is renamed without changing its meaning, you must decide whether to update the label as Type 1 or treat it as a new classification.

## 7. Relationship diagram: logical object, dimension version, and fact

~~~mermaid
erDiagram
    PRODUCT_IDENTITY ||--o{ DIM_PRODUCT : "has descriptive versions"
    DIM_PRODUCT ||--o{ FACT_SALES_LINE : "referenced by fact"
    DIM_DATE ||--o{ FACT_SALES_LINE : "sale date"
    PRODUCT_IDENTITY {
        bigint product_dk PK
        bigint tenant_id
        text source_system
        text product_bk
    }
    DIM_PRODUCT {
        bigint product_sk PK
        bigint product_dk FK
        text product_name
        text category_code
        daterange valid_period
    }
    DIM_DATE {
        int date_key PK
        date calendar_date
    }
    FACT_SALES_LINE {
        bigint sales_line_sk PK
        text source_line_bk
        bigint product_sk FK
        int date_key FK
        int quantity
        decimal net_amount
    }
~~~

The diagram clearly shows three relationships:

- **ProductIdentity → DimProduct**: one logical product has multiple descriptive versions.
- **DimProduct → FactSalesLine**: one descriptive version can be referenced by multiple sales lines.
- **DimDate → FactSalesLine**: one date contains multiple sales lines.

When the fact stores product_sk, it points to the exact version, not directly to product_dk. However, reports that want to aggregate across all versions of P01 can still JOIN **dim_product → product_identity**, then group by product_dk or BK when appropriate.

Not every system needs a separate identity table; this split-table design simply illustrates the need for an **entity-level durable key**, while also providing a stable row to lock when updating versions.

## 8. PostgreSQL design: business key and identity table

This PostgreSQL example uses **date/daterange** because product classification is defined as effective by business date. If changes need hourly or sub-day precision, choose **timestamptz/tstzrange**, standardizing the timezone and transaction timestamp rules.

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE product_identity (
    product_dk     bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    tenant_id      bigint NOT NULL,
    source_system  text NOT NULL,
    product_bk     text NOT NULL,

    CONSTRAINT uq_product_business_identity
        UNIQUE (tenant_id, source_system, product_bk),

    CONSTRAINT ck_product_bk_not_blank
        CHECK (length(btrim(product_bk)) > 0),

    CONSTRAINT ck_source_system_not_blank
        CHECK (length(btrim(source_system)) > 0)
);
~~~

Explanation:

- **product_dk** is warehouse-assigned and remains stable across descriptive versions.
- **tenant_id + source_system + product_bk** is the complete source identifier under the business assumption.
- **UNIQUE** ensures no two identities are created for the same code within the same source/tenant.
- **CHECK** forbids whitespace-only codes, though it does not automatically normalize case or strip all invalid characters.
- DDL alone does not prove that a source code will never be reused. If codes are reused for different objects, a mapping policy with an additional identifying or temporal dimension is required.

The **product_dk** number is the technical key for a **logical object in the analytics warehouse**, not a version key. Another source having P01 will produce a different product_dk unless there is a process confirming both codes refer to the same object and mapping them to a canonical identity.

## 9. PostgreSQL design: dimension versions and descriptive attributes

Each **dim_product** row corresponds to one version of one product_dk.

~~~sql
CREATE TABLE dim_product (
    product_sk       bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    product_dk       bigint NOT NULL
                     REFERENCES product_identity(product_dk),
    product_name     text NOT NULL,
    brand_code       text,
    category_code    text NOT NULL,
    category_name    text NOT NULL,
    valid_period     daterange NOT NULL,
    decision_ref     text NOT NULL,
    loaded_at        timestamptz NOT NULL DEFAULT statement_timestamp(),

    CONSTRAINT ck_product_valid_period
        CHECK (
            NOT isempty(valid_period)
            AND NOT lower_inf(valid_period)
            AND lower_inc(valid_period)
            AND NOT upper_inc(valid_period)
        ),

    CONSTRAINT ex_product_version_no_overlap
        EXCLUDE USING gist (
            product_dk WITH =,
            valid_period WITH &&
        )
);

CREATE INDEX ix_product_dim_by_entity_start
    ON dim_product (product_dk, lower(valid_period));
~~~

**product_sk** is the version surrogate key; **product_dk** is the FK to identity; **valid_period** describes the interval during which the accompanying attributes are accepted as effective according to business rules.

Intervals use the **[valid_from, valid_to)** convention:

~~~text
[2026-01-01, 2026-08-01)  FOOD
[2026-08-01, unbounded)   GIFT
~~~

August 1 belongs solely to the GIFT version. The two intervals are **contiguous but non-overlapping**.

### 9.1. What do database constraints protect?

| Constraint | What is protected |
|---|---|
| PRIMARY KEY(product_sk) | Each version row has its own ID |
| FOREIGN KEY(product_dk) | Each version belongs to a logical object with an identity |
| NOT NULL | Core attributes/columns are not left empty |
| CHECK NOT isempty(valid_period) | Prevents creating versions with empty ranges |
| CHECK lower_inc AND NOT upper_inc | Consistent half-open boundary interpretation |
| EXCLUDE(product_dk WITH =, valid_period WITH &&) | At most one descriptive version for the same product on any date |
| INDEX(product_dk, lower(valid_period)) | Supports reading a product's timeline when appropriate |

**EXCLUDE** prevents overlap; **it does not automatically prevent gaps**. A product might have no version on 2026-07-05 if data is missing. When mapping facts by sale date, such cases must be detected and handled.

Using **btree_gist** enables combining equality comparisons on bigint with range overlap operators in GiST. Extensions must be deployed according to database privilege policies; migrations should not arbitrarily alter extensions in production.

### 9.2. ETL metadata is not validity time

**loaded_at** states when the system loaded the data into the warehouse, not the date from which the product belonged to that category. **decision_ref** enables tracing the classification decision.

A version might be loaded on August 10 while being retroactively effective from August 1. If loaded_at were used as valid_from, reports for transactions from August 1 through August 9 would be wrong.

If requirements also demand answering **"on August 5, what group did the analytics warehouse believe the product belonged to?"**, add known/system time or historical snapshots/revisions; a single loaded_at column on updated rows is not sufficient for bitemporality.

## 10. Sample data: two versions of one product

~~~sql
INSERT INTO product_identity (
    product_dk, tenant_id, source_system, product_bk
)
VALUES (7, 1, 'ERP', 'P01');

INSERT INTO dim_product (
    product_sk, product_dk, product_name,
    brand_code, category_code, category_name,
    valid_period, decision_ref
)
VALUES
(
    101, 7, 'Nutrition Cake',
    'BR-N', 'FOOD', 'Food',
    daterange(DATE '2026-01-01', DATE '2026-08-01', '[)'),
    'CATEGORY-2026-H1'
),
(
    102, 7, 'Nutrition Cake',
    'BR-N', 'GIFT', 'Gift',
    daterange(DATE '2026-08-01', NULL, '[)'),
    'CATEGORY-2026-AUG'
);
~~~

In the sample data, SK values are explicitly specified for readability. **In real ETL**, let the system generate IDs and use INSERT/RETURNING results or lookup tables; do not hardcode 101/102 and treat them as having business meaning.

Timeline query:

~~~sql
SELECT
    i.tenant_id,
    i.source_system,
    i.product_bk,
    p.product_dk,
    p.product_sk,
    p.category_code,
    lower(p.valid_period) AS valid_from,
    upper(p.valid_period) AS valid_to,
    p.decision_ref
FROM product_identity i
JOIN dim_product p
  ON p.product_dk = i.product_dk
WHERE i.tenant_id = 1
  AND i.source_system = 'ERP'
  AND i.product_bk = 'P01'
ORDER BY lower(p.valid_period);
~~~

The result has two rows with the same BK, but different SKs and different validity intervals.

### 10.1. Finding the right version on a given date

~~~sql
SELECT p.product_sk, p.product_name, p.category_code
FROM product_identity i
JOIN dim_product p
  ON p.product_dk = i.product_dk
WHERE i.tenant_id = 1
  AND i.source_system = 'ERP'
  AND i.product_bk = 'P01'
  AND p.valid_period @> DATE '2026-07-15';
-- product_sk = 101, category_code = FOOD
~~~

Changing the query date to **2026-08-15** selects SK 102 and category GIFT.

The **@>** operator in PostgreSQL checks whether the range on the left contains the date on the right. This is a lookup by **business time**, not by the time the record was loaded.

## 11. Fact table: reference the version key, not the source code by mistake

In this example, a fact row is **one recorded sales line**. Each row belongs to one product (version), one sale date, and has measurements.

~~~sql
CREATE TABLE dim_date (
    date_key      integer PRIMARY KEY, -- YYYYMMDD in this example
    calendar_date date NOT NULL UNIQUE
);

CREATE TABLE fact_sales_line (
    sales_line_sk  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id      bigint NOT NULL,
    sales_source   text NOT NULL,
    source_line_bk text NOT NULL,
    order_bk       text NOT NULL,
    date_key       integer NOT NULL REFERENCES dim_date(date_key),
    product_sk     bigint NOT NULL REFERENCES dim_product(product_sk),
    quantity       integer NOT NULL CHECK (quantity > 0),
    currency_code  char(3) NOT NULL,
    net_amount     numeric(18, 2) NOT NULL,

    CONSTRAINT uq_sales_line_from_source
        UNIQUE (tenant_id, sales_source, source_line_bk)
);

CREATE INDEX ix_fact_sales_date_product
    ON fact_sales_line (date_key, product_sk);
~~~

Here:

- **source_line_bk** identifies the sales line from the source system within **tenant_id + sales_source**.
- **sales_line_sk** identifies the fact row in the analytics warehouse.
- **order_bk** is a *degenerate dimension*: an order identifier used for COUNT DISTINCT and traceability, without necessarily needing a separate dimension table.
- **product_sk** is the FK to the **product descriptive version**; the fact does not use product_dk in its place.
- **date_key** is the FK to the date dimension.

The distinction between **sales_source** and the product's **source_system** is intentional: sales orders may come from a POS system, while authoritative product codes come from an ERP. ETL must resolve the correct mapping between sources; do not assume the two source fields are equal.

### 11.1. Binding two transactions to two versions

~~~sql
INSERT INTO dim_date (date_key, calendar_date)
VALUES
    (20260715, DATE '2026-07-15'),
    (20260815, DATE '2026-08-15');

INSERT INTO fact_sales_line (
    tenant_id, sales_source, source_line_bk,
    order_bk, date_key, product_sk,
    quantity, currency_code, net_amount
)
VALUES
    (1, 'POS', 'L-501', 'O-100', 20260715, 101, 2, 'VND', 180000),
    (1, 'POS', 'L-502', 'O-101', 20260815, 102, 1, 'VND', 120000);
~~~

Expected result:

| Sales line | Date | Product BK | Version SK | Resolved category | Net |
|---|---|---|---:|---|---:|
| L-501 | 2026-07-15 | P01 | 101 | FOOD | 180,000 VND |
| L-502 | 2026-08-15 | P01 | 102 | GIFT | 120,000 VND |

This is an example at the **sales line grain**; quantities and monetary amounts are summed across lines when units, currencies, and recognition rules match. If the fact contains data in multiple currencies, you must filter or convert before applying SUM.

### 11.2. Why is an FK not enough to validate the mapping?

The FK only guarantees that product_sk 101 exists in dim_product. It does **not** prevent ETL from binding L-502 on August 15 to product_sk 101, even though 101's validity period ends before August 1.

Therefore, we need a check:

~~~sql
SELECT
    f.source_line_bk,
    d.calendar_date,
    p.product_sk,
    p.valid_period
FROM fact_sales_line f
JOIN dim_date d ON d.date_key = f.date_key
JOIN dim_product p ON p.product_sk = f.product_sk
WHERE NOT (p.valid_period @> d.calendar_date);
-- With valid sample data, this returns no rows.
~~~

In multi-tenant systems, you must also reconcile the **fact's tenant** against the **product's identity**; an FK on product_sk alone does not prove they belong to the same tenant. You can strengthen guarantees with a matching composite key/FK design, or mandatory ETL validation at the ingestion boundary.

## 12. Two ways to group history: as-was and as-is

When P01 changes FOOD → GIFT, there are two different reports that can both be valid.

**As-was** (*by classification at the time of sale*): July facts fall under FOOD because the fact points to SK 101; August facts fall under GIFT because the fact points to SK 102.

~~~sql
SELECT
    p.category_code,
    SUM(f.net_amount) AS net_sales
FROM fact_sales_line f
JOIN dim_product p ON p.product_sk = f.product_sk
WHERE f.currency_code = 'VND'
GROUP BY p.category_code
ORDER BY p.category_code;
-- FOOD = 180000, GIFT = 120000
~~~

**As-is** (*by classification on a currently selected reference date*): groups historical revenue by the product's category on the **current evaluation date**. In this example, choosing 2026-11-15:

~~~sql
SELECT
    current_p.category_code,
    SUM(f.net_amount) AS net_sales
FROM fact_sales_line f
JOIN dim_product sold_p
  ON sold_p.product_sk = f.product_sk
JOIN dim_product current_p
  ON current_p.product_dk = sold_p.product_dk
 AND current_p.valid_period @> DATE '2026-11-15'
WHERE f.currency_code = 'VND'
GROUP BY current_p.category_code;
-- GIFT = 300000, under the 2026-11-15 as-is definition
~~~

This as-is query is **only accurate insofar as there is exactly one version per product on the reference date**. If the dimension has a gap on that date, INNER JOIN will drop facts; missing mappings must be controlled. If the product changes category again after 2026-11-15, as-is on a different date may differ.

**Do not change report labels** from as-was to as-is without informing users. The difference is an **analytical definition**, not an arithmetic error.

## 13. SCD Type 2 update: closing the old version, creating the new version

When a category changes, historical data must be preserved so old facts continue pointing to the right version. Transition diagram:

~~~text
Before change:
SK 101: P01, FOOD, [2026-01-01, +∞)

After decision effective from 2026-08-01:
SK 101: P01, FOOD, [2026-01-01, 2026-08-01)
SK 102: P01, GIFT, [2026-08-01, +∞)
~~~

This transaction example **illustrates the initial state where only SK 101 is open-ended**. Do not re-run it verbatim after the sample data in section 10 has already created SK 102.

~~~sql
BEGIN;

-- Lock P01's stable identity so version changes
-- for the same product are serialized.
SELECT product_dk
FROM product_identity
WHERE tenant_id = 1
  AND source_system = 'ERP'
  AND product_bk = 'P01'
FOR UPDATE;

UPDATE dim_product
SET valid_period = daterange(
    lower(valid_period),
    DATE '2026-08-01',
    '[)'
)
WHERE product_dk = 7
  AND lower(valid_period) < DATE '2026-08-01'
  AND upper_inf(valid_period)
RETURNING product_sk;

-- The application must verify that exactly 1 row was updated;
-- otherwise ROLLBACK to recompute the timeline.

INSERT INTO dim_product (
    product_dk, product_name, brand_code,
    category_code, category_name, valid_period, decision_ref
)
VALUES (
    7, 'Nutrition Cake', 'BR-N',
    'GIFT', 'Gift',
    daterange(DATE '2026-08-01', NULL, '[)'),
    'CATEGORY-2026-AUG'
)
RETURNING product_sk;

COMMIT;
~~~

**Only COMMIT** if you have verified the decision scope, updated row count, effective intervals, and rule compliance. If the INSERT fails, the transaction must roll back so you are not left with only a closed old version.

If a future version is already scheduled starting 2026-09-15, an UPDATE that truncates an open-ended range and inserts [2026-08-01, +∞) will be wrong. You must **read the actual timeline**, identify the affected segments, split intervals at the appropriate boundaries, and preserve non-superseded future decisions.

### 13.1. Concurrency and locking the durable identity

Locking the **product_identity** row is a useful synchronization point because that row exists stably across versions. Locking only the current dimension row may fail to lock cases where no version exists yet or where two concurrent inserts race.

The **EXCLUDE** constraint remains necessary because it protects the database even if a write path bypasses the update protocol. Transactions, version/revision checks, and retries must work together so valid decisions are not lost.

### 13.2. Does fixing a typo require SCD2?

If product_name was initially **"Nutriton Cake"** due to a typing mistake and the business wants all historical reports to display **"Nutrition Cake"**, a Type 1 update may be appropriate:

~~~sql
UPDATE dim_product
SET product_name = 'Nutrition Cake'
WHERE product_dk = 7;
~~~

This statement intentionally replaces the label across all versions of the same product. It **does not** retain the erroneous name previously shown; if auditability is required, store a separate audit/decision log. For a commercial rebranding effective on a specific date, SCD2 may be more appropriate.

Principle: **which attributes retain history must be driven by reporting and business questions**, not by creating a new version on every UPDATE.

## 14. Unknown member, late-arriving data, and unresolved mappings

In practice, facts can arrive before dimensions. For example, POS sends L-503 with product_bk = P09, but ERP has not yet synced product P09.

Options:

| Option | When appropriate | What must be controlled |
|---|---|---|
| **Quarantine/staging** | Data must be accurate before publication | Log source and unresolved reason; provide retry |
| **Unknown dimension member** | Facts must load on time with an unknown label | Do not mix Unknown with real products |
| **Inferred member** | BK is known, but descriptive attributes are missing | Backfill attributes when dimension arrives; preserve identity per rules |
| **Late-arriving restatement** | Fact version key must be corrected once data is complete | Maintain audit/revision and impact reconciliation |

### 14.1. Unknown is not the same as Not applicable

There are several distinct cases:

- **Unknown**: may be determined later.
- **Not applicable**: this dimension is not relevant to the transaction.
- **Anonymous**: the business does not collect customer identity.
- **Data error**: the source code is invalid or conflicting.
- **Deleted/restricted**: data is not permitted to be displayed.

Lumping all of these into a single Unknown SK makes reports confusing and can mask source errors. If special members are used, they must be explicitly declared in the dimension and audited separately.

### 14.2. Should product_sk in a fact be updated later?

If a fact was initially bound to an Unknown SK and the right version of P09 for the sale date is found later, the fact mapping can be updated via a controlled **restatement** process. However, if the fact has already been published in reports or used for closed financial statements, you must know whether updating it alters published figures.

In event-sourced or immutable fact architectures, you may record adjustment entries or rebuild projections instead of silently issuing an UPDATE. The choice depends on audit obligations.

### 14.3. Inferred members and SCD2

If only BK P09 is known on August 5, the system can create an identity and a placeholder descriptive version, but **must not automatically assign the current category to the entire past** without evidence. When full data arrives, determine the true valid period, create or revise versions, and inspect affected facts.

The key distinction is that an **intentional placeholder** must be clearly flagged with an unverified status and never masquerade as data confirmed by the business source.

## 15. Multiple sources and identity mapping table management

Suppose ERP has code P01 while the PIM system has code PRD-0001; both describe the same logical product according to a business decision. This cannot be determined solely from how the codes are formatted.

An integration model might look like:

~~~text
canonical_product_id = 7

source mapping:
  ERP / P01      → canonical 7
  PIM / PRD-0001 → canonical 7
~~~

In the design from section 8, product_identity uses one BK per namespace to issue product_dk. **If two sources need to be merged into the same canonical object**, you can add a **source_product_mapping** table pointing multiple source BKs to one canonical durable key. Do not alter the identity UNIQUE constraint to blindly equate P01 across two sources.

### 15.1. Rules for identity resolution

**Identity resolution** can rely on GTIN/ISBN where applicable, certification numbers, organization-issued keys, or governance decisions. You should record:

- The source of each code.
- Evidence confirming both codes refer to the same object.
- Effective date of the mapping if it changes.
- Who approved the merge/split.
- How to handle facts already bound under the old mapping.

**Having the same product name is not sufficient proof of shared identity.** Conversely, two products of the same model but different SKU variants may need to stay separate due to different pricing, inventory, or ownership.

### 15.2. Avoid making fact FKs depend directly on source codes

If a fact uses code P01, other source systems may supply P01 with a different meaning. Joining on a standalone code is highly error-prone. Once ETL maps to product_sk belonging to a canonical version, analytical queries do not need to reapply all source-identification rules on every read.

Even so, keep **source_system, source_line_bk, and source_product_bk** in staging or lineage to investigate bad mappings; surrogate keys should never erase source traceability.

## 16. Descriptive attributes with many-to-many relationships and independent history

A product can have multiple **tags**, belong to multiple **collections**, link to multiple **suppliers**, or be sold across multiple **channels**. Not every value belongs in a single-valued column in dim_product.

Example:

~~~text
P01 → Category FOOD
P01 → Category HEALTHY
~~~

If a sales fact for P01 with net = 180,000 is joined to two categories, revenue will appear twice. You must distinguish:

- **Revenue present in each category**: each category can show 180,000, but the sum of categories does not equal the system-wide total.
- **Weighted allocated revenue**: a 60/40 rule keeps the category sum equal to 180,000.
- **Single primary category**: pick one primary_category effective on the sale date; secondary categories serve filtering/tagging.

An illustrative bridge table:

~~~sql
CREATE TABLE dim_category (
    category_sk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_code text NOT NULL UNIQUE,
    category_name text NOT NULL
);

CREATE TABLE bridge_product_category (
    product_sk bigint NOT NULL REFERENCES dim_product(product_sk),
    category_sk bigint NOT NULL REFERENCES dim_category(category_sk),
    allocation_weight numeric(8, 6) NOT NULL
        CHECK (allocation_weight >= 0 AND allocation_weight <= 1),
    PRIMARY KEY (product_sk, category_sk)
);
~~~

Here the relationship is attached to the **version product_sk**. If an entity has multiple categories versioned independently of other product attributes, a bridge keyed by **product_dk + relationship validity interval** may be needed to avoid duplicating the entire product dimension whenever only category relationships change.

A CHECK on each individual bridge row does not prove the weights sum to 1. If full revenue allocation is required, you must validate the sum of weights per product_sk or per effective time interval, including under concurrent updates.

## 17. Derived attributes and hierarchical dimensions

A dimension table may hold **price_band**, **customer_age_band**, **store_region**, or **customer_value_segment** derived from other data. These can still serve as descriptive attributes for filtering/grouping, but require control over:

- **Formula and calculation source**: is price_band based on list price or promotional price?
- **Calculation timing**: end-of-month segment or segment when the transaction occurred?
- **Grain**: is age the age on the transaction date or current age?
- **History**: groups change over time; is SCD2 or a snapshot fact needed?
- **Reliability**: are values recalculated when source data is retroactively adjusted?

For example, **current customer age** is not an immutable attribute for analyzing revenue from 5 years ago. If grouping by age at purchase, compute age from date of birth and transaction date (if permitted to use that data), or store the age band at the time of sale under privacy rules. Do not join to current age_band and label it "age at purchase."

### 17.1. Hierarchies can cause fanout

~~~text
Department → Category → Group → SKU
~~~

This is a tree only if one SKU has one parent group at the point of analysis. If an SKU belongs to multiple groups simultaneously or groups change over time, joining the hierarchy without proper conditions will multiply revenue.

When designing a snowflake dimension, determine the key of each level, cardinalities, and relationship history; never assume every table with **category** in its name is permanently one-to-many.

## 18. Data quality: checking uniqueness and version correctness

Key checks before exposing a dimensional model to reporting:

| Check | Meaning |
|---|---|
| BK unique within namespace (tenant, source) | No duplicate identities for one source code |
| SK unique and NOT NULL | Every version row is stably identified |
| Valid product_dk FK | Every version has an identity |
| No overlapping valid_period for the same product_dk | No two competing versions on the same date |
| No empty or inverted ranges | Temporal data is meaningful |
| No gaps in required periods | Fact mapping does not miss periods |
| Fact product_sk exists | No orphan foreign keys |
| Fact sale date falls within product_sk's valid_period | FK points to the temporally correct version |
| Fact and dimension share tenant when required | No data leakage or cross-tenant binding |
| Codes/labels conform to reference data | No fragmented groups caused by typos |
| Unknown/inferred members have clear status | Missing data is not treated as verified |
| Multi-system source mappings are approved | No accidental identity merges |
| Queries after JOIN preserve row counts/totals when expected | Detects fanout |

### 18.1. Finding overlaps in staging tables without constraints

The following pattern is useful on staging loads structured like dim_product:

~~~sql
SELECT
    a.product_dk,
    a.product_sk AS first_sk,
    b.product_sk AS second_sk,
    a.valid_period AS first_period,
    b.valid_period AS second_period
FROM dim_product a
JOIN dim_product b
  ON a.product_dk = b.product_dk
 AND a.product_sk < b.product_sk
 AND a.valid_period && b.valid_period;
~~~

On a dim_product table with an active exclusion constraint, this result must be empty. When migrating from legacy sources, run this style of query **on staging before applying constraints** to catch data needing repair.

### 18.2. Finding gaps between versions

~~~sql
WITH timeline AS (
    SELECT
        product_dk,
        upper(valid_period) AS valid_to,
        LEAD(lower(valid_period)) OVER (
            PARTITION BY product_dk
            ORDER BY lower(valid_period)
        ) AS next_valid_from
    FROM dim_product
)
SELECT
    product_dk,
    valid_to AS gap_start,
    next_valid_from AS gap_end
FROM timeline
WHERE valid_to IS NOT NULL
  AND next_valid_from IS NOT NULL
  AND valid_to < next_valid_from;
~~~

This checks for **internal gaps**. It does not detect missing coverage before the first version or after the last version; those must be reconciled against the product's actual lifecycle and fact range.

### 18.3. Checking facts bound to the wrong point in time

~~~sql
SELECT
    f.sales_line_sk,
    f.source_line_bk,
    d.calendar_date,
    p.product_sk,
    p.valid_period
FROM fact_sales_line f
JOIN dim_date d ON d.date_key = f.date_key
JOIN dim_product p ON p.product_sk = f.product_sk
WHERE NOT (p.valid_period @> d.calendar_date);
~~~

This query must return empty if every fact is bound to the right version on the sale date. You should also verify the source and tenant of the mapped product, as well as any other dimensions that track history.

### 18.4. Do not let dimension errors turn into measure errors

If a single 180,000 VND sales line joins to two dimension rows, SUM becomes 360,000 VND. Add a reconciliation test:

~~~sql
WITH source_total AS (
    SELECT SUM(net_amount) AS amount
    FROM fact_sales_line
    WHERE currency_code = 'VND'
),
joined_total AS (
    SELECT SUM(f.net_amount) AS amount
    FROM fact_sales_line f
    JOIN dim_product p ON p.product_sk = f.product_sk
    WHERE f.currency_code = 'VND'
)
SELECT
    s.amount AS source_amount,
    j.amount AS joined_amount
FROM source_total s
CROSS JOIN joined_total j;
~~~

When FKs are valid and joining on the product_sk PK, the two totals must match. However, matching totals are **not sufficient** to prove every fact is bound to the right version; date-based mapping still must be verified.

## 19. Special cases: date dimensions, role-playing dimensions, and degenerate dimensions

### 19.1. Date dimension

A date dimension can use **date_key = 20260815** and **calendar_date = 2026-08-15**. This is a case where a convention-based key is meaningful and stable, removing the need for a random sequence for each day.

However, time has multiple meanings: order date, payment date, ship date, revenue recognition date. One fact can have multiple FKs to the same dim_date, each acting as a **role** (*role-playing dimension*).

### 19.2. Degenerate dimension

**order_bk** can be stored directly in fact_sales_line for drill-through and COUNT(DISTINCT order_bk), if it has no separate set of attributes requiring a dimension. That is a **degenerate dimension**, unlike product_sk which is an FK to a descriptive dimension.

Pay attention to order_bk scope: code O100 may collide across two POS systems, so system-wide order counts may require the tuple (tenant, sales_source, order_bk), not a single code string.

### 19.3. Conformed dimension

If fact_sales_line and fact_inventory_daily use the same product and category definitions, they can compare revenue against inventory by product. However, if one fact uses product family while the other uses SKU, an explicit grain mapping is required before drilling across.

A **conformed dimension** is consistency in **meaning, keys, and classification** across analytical models, not merely having two tables both named dim_product.

### 19.4. Mini-dimension for rapidly changing attributes

If certain customer attributes change very frequently (e.g., activity tier, score band), creating SCD2 rows across all of dim_customer for every change can cause version bloat. You can split rapidly changing attributes into a **mini-dimension**, with the fact referencing the appropriate mini-dim.

However, the grain and temporal meaning of that link must be clear. Do not split out a mini-dim solely to save storage if it destroys the ability to explain the segment at transaction time.

## 20. ETL operations: loading, idempotency, and retroactive corrections

A typical pipeline:

~~~mermaid
flowchart LR
    A["Source ERP/PIM/POS"] --> B["Staging + BK normalization"]
    B --> C["Identity mapping / durable key"]
    C --> D["SCD dimension versions"]
    D --> E["Map fact to version SK"]
    E --> F["Data quality + reconciliation"]
    F --> G["Analytics warehouse / semantic layer"]
~~~

The workflow should separate these steps:

1. **Ingest data with source keys**: tenant, source, BK, source version or update timestamp.
2. **Normalize codes within the source contract**: without losing leading zeros or namespaces.
3. **Find or create identity**: prevent duplicates when two workers run concurrently.
4. **Compare attributes needing Type 1/Type 2**: separate label fixes from effective classification changes.
5. **Compute valid timeline**: handle future/retroactive dates, split intervals when needed, preserve non-overlap constraints.
6. **Write transactionally**: ensure identity/version changes are atomic in the database when in the same system.
7. **Map facts**: use source BK together with business date to select the matching product_sk.
8. **Test and reconcile**: check missing dimensions, duplicated facts, and accurate totals/groupings.
9. **Publish dataset versions**: do not silently alter locked dashboards when the business requires revision history.
10. **Monitor quality and retries**: re-running loads must not create duplicate identities or versions.

### 20.1. Idempotency does not mean ignoring every redelivery

If a source resends the same decision, ETL must recognize it and avoid creating an identical SCD2 row. However, if the redelivery carries an **authoritative correction**, it must be processed as a correction rather than dropped simply because the BK already exists.

You can store decision_id/source_event_id and revision to distinguish **retries**, **new updates**, and **corrections**. A unique BK only protects identity; it does not replace update deduplication.

### 20.2. Retroactive changes affecting closed facts

Suppose on August 10 it is discovered that P01 actually had to move to GIFT starting July 20, not August 1.

- Under the new timeline, transaction L-501 on July 15 remains FOOD.
- A transaction L-501B on July 25, if previously bound to FOOD, now needs review to rebind to the GIFT version for **as-was reporting under currently recognized information**.
- The July report published before the correction may differ from the report recomputed after the correction.

You need a restatement policy, report/snapshot versioning, or bitemporality if you must prove what the warehouse **knew at time K**. Do not arbitrarily UPDATE historical facts or dimensions without preserving evidence of the impact.

### 20.3. Difference between a modeling error and a source data error

If BK is not unique within the defined scope, it may be a **wrong design assumption** or **source data violating the contract**. The two cases require different actions.

Do not "fix" it by appending a random number to BK to make each row unique; that hides identity conflicts instead of resolving them.

## 21. Physical optimization, security, and dimension evolution

### 21.1. Indexes for primary queries

For this model, typical access paths:

| Query | Useful key or index |
|---|---|
| BK → durable key | UNIQUE(tenant_id, source_system, product_bk) |
| durable key + date → version SK | GiST exclusion and valid_period lookup |
| SK → description | PRIMARY KEY(product_sk) |
| Timeline of one product | INDEX(product_dk, lower(valid_period)) |
| Facts by date/product | INDEX(date_key, product_sk) |
| Report by category | Group/scan facts through dimension; measure on real workload |

Do not create an index merely because a column appears in SELECT. Measure with **EXPLAIN (ANALYZE, BUFFERS)** and evaluate SCD2 write overhead, selectivity, memory, and fact volume.

### 21.2. Large attributes, multilingual support, and privacy

Dimensions may hold long names, HTML descriptions, image lists, or sensitive data. Large fields rarely used for grouping should be considered for separation into supplemental tables or dedicated descriptive stores to reduce I/O during BI scans.

For customer dimensions, do not replicate email, address, and personal data into every version if analytical requirements only need segments. Apply read-access policies, retention, encryption, minimization, and deletion/anonymization under applicable regulations.

### 21.3. Standardized data and preventing label drift

If category_code FOOD is displayed sometimes as **"Food"**, sometimes as **"Foods"**, and sometimes as **"Groceries"**, BI tools may render three separate display groups despite sharing one category. Govern the code → label mapping (by locale if needed), test canonical values, and maintain a versioning strategy if a classification changes meaning.

The schema can transition from relational to document or lakehouse storage while keeping the three core concepts: **business identity**, **version identifier**, and **attributes meaningful at the point of analysis**.

## 22. Practice exercise: building a customer dimension with segment history

An e-commerce platform has the requirement:

> "By month, calculate revenue by customer segment on the purchase date. Customers can transition from REGULAR to VIP. Customer data comes from CRM and POS; some customers make purchases before their CRM profile is synced."

Sample data:

~~~text
CRM / C-501 (tenant 1)
  REGULAR: [2026-01-01, 2026-07-01)
  VIP:     [2026-07-01, +∞)

Order O100 on 2026-06-20: net = 100,000 VND
Order O101 on 2026-07-10: net = 200,000 VND
~~~

Tasks:

1. **Define BK:** specify scope (tenant_id, source_system, customer_bk). If POS has a different customer ID than CRM, what mapping is needed to recognize the same customer?
2. **Choose durable key:** a stable customer_dk for the logical customer; describe the case where a customer changes their CRM code.
3. **Choose version SK:** create two SCD2 dim_customer rows, each with its own customer_sk and valid_period.
4. **Choose descriptive attributes:** segment_code, region_code, loyalty_level; determine which are Type 1, Type 2, and why.
5. **Fact mapping:** O100 must point to the REGULAR customer_sk, O101 to the VIP customer_sk.
6. **As-was vs as-is:** by segment at sale time, REGULAR = 100,000 and VIP = 200,000. By segment on 2026-11-15, the total 300,000 may be classified as VIP.
7. **Late-arriving dimension:** if O101 arrives before the CRM profile, how are quarantine or Unknown/inferred members handled?
8. **Multi-tenant scenario:** two tenants both have C-501; what prevents accidental merging?
9. **Concurrency:** two workers concurrently update the segment on 2026-07-01; what locking mechanism and constraints are needed?
10. **Retroactive correction:** on August 15, it is confirmed that VIP was effective from June 15. Does Order O100 on June 20 change segment in recomputed reports? What policy is needed for fact updates, revisions, and closed reports?
11. **Testing:** duplicate BK, SCD2 overlap, gaps, orphan FK, fact bound to wrong date, wrong tenant, and fanout when joining across both BK and version.

**Acceptance criteria:** BK has a namespace, SK matches the version grain, descriptive attributes have change strategies, facts bind to the right version, and late-arriving data and retroactive rules are unambiguous.

## 23. Design approval checklist

Before deploying a dimension table, verify:

- **Grain:** does each dimension row represent one logical object or one descriptive version?
- **Business key:** who issues the source code; is the tenant/source namespace sufficient; can codes be reused or changed?
- **Surrogate key:** is SK a row ID or entity ID; is a separate durable key needed?
- **Fact FK:** does the fact reference the appropriate version SK, or only join on BK causing row multiplication?
- **Descriptive attributes:** are they at the right grain, single-valued or multi-valued; are codes and labels governed consistently?
- **History:** which fields use Type 1, Type 2, or relationship history; are time boundaries clearly defined?
- **Constraints:** are PK, FK, UNIQUE, CHECK, and non-overlap constraints along the right business key sufficient?
- **Late-arriving data:** are Unknown, Not applicable, inferred members, and quarantine distinguished?
- **Multi-source:** does identity resolution have approved sources rather than accidentally merging matching BKs?
- **As-was/as-is:** do report consumers know which point in time's classification they are viewing?
- **Validation:** are duplicates, missing dimensions, temporal mismatches, cross-tenant mappings, and fanout checked automatically?
- **Retroactive changes:** do corrections have transactional workflows, restatement, and evidence preservation when reports are closed?
- **Performance:** have indexes, partitioning, and scan needs for dimension attributes been measured?
- **Security:** is personal and confidential data kept from being duplicated or exposed through historical versions?

**Conclusion:** the business key answers **"which object is this in the source?"**, the version surrogate key answers **"which exact descriptive row does the fact reference?"**, and dimension attributes answer **"how is the object classified, named, and explained at the point of analysis?"**. When needed, a durable key connects versions belonging to the same logical object. Clearly separating these roles is the foundation for building dimensions that evolve cleanly, query accurately, avoid double-counting measures, and can be verified against real data.
