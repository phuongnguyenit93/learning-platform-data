# Declare the Grain Before Choosing Keys and Measures

## Learning Objectives

After this lesson, you will be able to:

- State the **grain** of a **fact table** as a business sentence precise enough for others to verify.
- Distinguish **transaction**, **periodic snapshot**, **accumulating snapshot**, and **factless** fact tables, and understand why each type has different keys and update semantics.
- Choose **identifying keys**, **dimension keys**, and **measures** based on the grain, rather than picking available columns first and trying to explain their meaning afterward.
- Prevent amount multiplication bugs caused by joining multiple 1:N relationships, summing metrics at the wrong level, double-counting, and aggregating across incompatible currencies.
- Design an order-line fact table in PostgreSQL, clarifying timestamps, historically changing dimensions, measure additivity, and reconciliation.
- Define verification criteria for grain across relational schemas, analytical warehouses, document stores, and graph databases.

This lesson belongs to the **Fact Tables** chapter of **DATABASE_DATA_MODELING**. In analytical data modeling, we do not merely translate business requirements into tables, keys, indexes, and constraints; we must clarify **exactly what event or state a single row represents**. That answer determines how dimensions are joined, how totals are computed, how the physical schema is organized, and how results are verified.

## 1. What Is Grain, and Why Must It Be Declared First?

**Grain** is the exact definition of **what one row of a fact table corresponds to in the business domain**. It is not just "this table contains sales data" or "this table is grouped by day." A good declaration needs to clarify:

1. **Object or event:** a transaction, order line, payment capture, inventory item, work shift, etc.
2. **Time anchor:** the timestamp when an event occurred, a snapshot date, or the lifecycle of a process.
3. **Unit of repetition:** one row per entity, per event, per entity–time pair, or per completed state.
4. **Valid scope:** confirmed, paid, not canceled, which tenant it belongs to, and how edits/refunds are handled.
5. **Identifiability:** how to determine whether two rows represent the same fact.

Examples of grain statements:

- **Sales transactions:** "Each row is **one unique order line of a confirmed order**, with quantity, unit price, and discount locked at confirmation time."
- **Payments:** "Each row is **one successful payment capture**, identified by the payment provider's capture ID."
- **End-of-day inventory:** "Each row is the **end-of-day on-hand balance of one product at one warehouse**, according to the defined business date."
- **Order fulfillment progress:** "Each row represents **one order**, updated as it passes through ordered, packed, shipped, and delivered milestones."
- **Attendance events:** "Each row records **one person attending one session**; the row itself represents presence and does not necessarily require a quantity column."

Only after locking down one of those statements do you have a sound basis for choosing keys, dimensions, and measures.

> **If you do not know what one row means, you do not yet know what COUNT counts, what SUM adds, or what case UNIQUE must prevent.**

### 1.1. Grain Is Not Key Width or Dataset Size

A table with a primary key **fact_id BIGINT** does not have a grain of "one fact_id." That is merely a technical identifier. Grain must be expressed in terms of a **business event**.

A table with one million rows is not necessarily finer-grained than a table with one thousand rows; the two tables may cover different time periods and datasets. The phrase "daily grain" is also insufficient: is it **one row per day across the entire system**, or **one row per day × warehouse × product**?

Example of an inadequate statement:

> The fact_sales table stores order and product information.

A more verifiable statement:

> One row of **fact_sales_line** corresponds to one initially confirmed **(order_id, line_no)**, storing the quantity and amounts of that line; post-confirmation adjustments or refunds are recorded as separate events.

The second sentence makes it possible to determine the business key, time anchor, write rules, and what does not belong in the table.

## 2. Example: Going Wrong Immediately When Choosing Measures at an Unclear Level

Suppose there are two orders, both in VND, **excluding tax and shipping**:

| Order | Line | Product | Quantity | Locked Unit Price | Gross Line Amount | Allocated Discount | Net Line Amount |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| **O-1001** | 1 | A | 2 | 100,000 | 200,000 | 6,000 | 194,000 |
| **O-1001** | 2 | B | 1 | 120,000 | 120,000 | 4,000 | 116,000 |
| **O-1002** | 1 | C | 1 | 90,000 | 90,000 | 0 | 90,000 |

At the **order-line** grain there are **3 rows**, total quantity sold is **4 units**, total gross amount is **410,000**, total discount is **10,000**, and total net amount is **400,000 VND**. Yet there are only **2 orders**.

Suppose the **orders** table also stores:

| order_id | total_items_net |
| --- | ---: |
| O-1001 | 310,000 |
| O-1002 | 90,000 |

If you JOIN **orders** with **order_items** and SUM **orders.total_items_net**, order O-1001 appears twice:

~~~sql
-- Wrong: the order-grain amount is repeated across each order line.
SELECT SUM(o.total_items_net) AS wrong_total
FROM orders AS o
JOIN order_items AS i
  ON i.order_id = o.order_id
WHERE o.order_id IN ('O-1001', 'O-1002');
-- 310000 + 310000 + 90000 = 710000, wrong.
~~~

The correct total is **310,000 + 90,000 = 400,000 VND**, or summing **net_amount** across the three lines if discounts were allocated consistently to each line.

**The bug is not in SUM or JOIN.** The bug lies in bringing an **order-grain** measure into an **order-line-grain** dataset, then summing it as if every row were an independent order.

Likewise, **COUNT(*) = 3** at the order-line grain does not mean "3 orders." When you genuinely need to count orders, you can use **COUNT(DISTINCT order_id)** on an appropriate dataset, or build a fact table at the order grain with its own definition. However, **distinct** counts within groups are not always additive across groups.

### 2.1. One Business Process Has Multiple Valid Facts at Different Grains

In the same example, there can be:

- **2 confirmed orders**: one-order grain.
- **3 confirmed order lines**: one-order-line grain.
- **4 product units sold**: sum of quantity from the order-line grain; units may differ if items are sold by kg, box, or piece.
- **N payments**: capture or payment-attempt grain; a single order can have multiple captures.
- **M shipments**: shipment or delivery-event grain; a single order can have multiple packages.

You cannot put all of those numbers into a single table without clarifying **whether each row corresponds to an order, line, capture, or shipment**. The right approach may be **multiple fact tables at different grains**, each serving an analytical group with clear semantics.

## 3. Design Process: Choose the Business Process, Then Declare the Grain

A practical workflow for dimensional modeling:

1. **Choose the business process:** order confirmation, payment capture, shipment, end-of-day inventory snapshot, etc.
2. **Declare the grain:** write a concrete sentence describing **each fact row**.
3. **Choose the dimensions:** who, what, where, when, which channel, and which status **at that grain**.
4. **Choose the measures:** the quantities, amounts, or counts **that are truly well-defined at that grain**.
5. **Design keys and physical layout:** business/natural keys, surrogate keys, FKs to dimensions, partitioning, indexes, ingestion mechanism, and reconciliation.

These steps depend on one another: only after defining the grain do you know **whether each fact row takes a single dimension value or requires a multi-valued relationship**. Only after defining the measures do you know which columns are additive.

### 3.1. Declare the Grain Using a Testable Template

A short template:

~~~text
Fact name: <fact_name>
Process: <business process>
One row represents: one <event / entity / state>
Scope: <business conditions, tenant, included statuses>
Time anchor: <event time / snapshot date / milestone>
Unique business key: <identifying attributes>
Edits/cancellations/refunds: <replacement or offsetting rules>
Available dimensions: <one corresponding value per row>
Measures: <units, formulas, and additivity>
~~~

You do not necessarily have to store this template as a table; it needs to be **written down as a contract** for reviewing schemas, queries, and pipelines.

### 3.2. Questions to Ask Before Locking the Design

- Can an order line be edited after confirmation? If edited, is there a **line revision** or an **adjustment event**?
- Can one order be paid across multiple captures?
- Can the same product appear on multiple lines of one order due to promotions or configurations?
- Do reports need to be grouped by **confirmation date**, **payment recognition date**, **delivery date**, or all three?
- Can an order contain multiple currencies? If so, what is the rule for total amounts?
- Can a single sales line belong to multiple promotion codes or multiple salespeople?
- Do reports need **customers by current state** or **customer segment at the time of sale**?

If any answer changes, the grain or dimension mapping may have to change. Do not choose keys upfront and force the system to answer in whatever way happens to be convenient.

## 4. Four Fact Table Types and Typical Grain Statements

### 4.1. Transaction Fact — One Row per Event or Event Item

Example:

> One row of **fact_order_line** is an order line confirmed for the first time, identified by **(order_id, line_no)**.

Common fields include **order_id**, confirmation timestamp, product/customer/date keys, quantity, gross amount, and allocated discount.

**Characteristics:** rows are created when the event occurs and usually preserve history; analyzed by date, product, customer, and channel. If a refund or cancellation occurs later, you can create **fact_return_line** or **fact_adjustment** at its own event grain rather than silently overwriting the original values.

Another transaction fact:

> One row of **fact_payment_capture** represents a **capture_id** confirmed by the payment provider.

If an order has multiple captures, **capture_id** is the proper identifier for this table; **order_id** is not unique.

### 4.2. Periodic Snapshot Fact — One Row per Dimension Combination per Period

Example:

> One row of **fact_inventory_eod** is the inventory balance **at the end of a business day** for **one product at one warehouse**, measured in a defined unit of measure.

Grain: **(business_date, warehouse_id, product_id)**, plus tenant/lot if the business distinguishes them.

**on_hand_quantity = 50** at the end of Monday and **on_hand_quantity = 55** at the end of Tuesday does not mean "two-day total inventory = 105." Inventory is **semi-additive across products/warehouses at the same point in time**, but **non-additive over time** for computing current inventory.

A periodic snapshot may contain a **0** row for combinations with no remaining stock if the rule requires covering all products/warehouses, or only emit rows when stock or activity exists. The row-emission policy must be documented in the contract so a **missing row** is not mistaken for **0**.

### 4.3. Accumulating Snapshot Fact — One Row per Entity Lifecycle

Example:

> One row of **fact_order_lifecycle** represents **one order**, updated as it reaches **ordered, paid, packed, shipped, and completed** milestones.

Each row may contain **ordered_date_key**, **paid_date_key**, **shipped_date_key**, and **delivered_date_key**; some milestones may not have occurred yet and require an appropriate unknown-value representation.

This table **receives updates** and has an order-level grain, unlike a transaction fact that records each event. If the workflow can loop backward, have multiple delivery attempts, or have multiple completions, you must clearly define **which milestone** is recorded (first, last, successful) or use a separate event fact table.

### 4.4. Factless Fact — Presence or Coverage Is the Information

Example:

> One row of **fact_attendance** represents a **person attending a session**.

The dimensions are person, session, location, and time. **No amount column is needed**: counting rows already represents attendance count. You may store a constant **1** column to sum, though it is optional.

Another factless fact may record **eligible attendance slots** (*coverage*) and compare them against actual attendance. You must distinguish whether a **missing row** means non-participation, uningested data, or exclusion from the tracked cohort. You cannot infer a "did not attend" event solely from an absent row without first defining the coverage scope.

### 4.5. Grain Comparison Table

| Fact Type | Per-Row Statement | Suggested Business Key | Write Pattern | Measure Notes |
| --- | --- | --- | --- | --- |
| Transaction | One confirmed order line | **(order_id, line_no)** | Append when event occurs | Quantity/amount are usually additive if units match |
| Transaction payment | One successful capture | **capture_id** | Append, deduplicate events | Capture ≠ order |
| Periodic snapshot | One day × warehouse × product | **(date, warehouse, product)** | Load/reconcile per period | Inventory is not additive over time |
| Accumulating snapshot | One order across its lifecycle | **order_id** | Update milestones | Future milestones and durations must be defined |
| Factless | One person × attended session | **(person, session)** | Append presence | COUNT rows, no amount needed |

Putting the same word **fact** on these tables does not mean they share a grain or an ingestion mechanism.

## 5. From Grain to Keys: Surrogate and Business Keys Have Different Jobs

For **fact_order_line**, having locked in "one order line of an initially confirmed order":

- **(order_id, line_no)** is the **business key** that distinguishes two lines. If a multi-tenant system can have colliding order_ids, **tenant_id** must be added to the identifier.
- **sales_line_fact_key** can be a technical surrogate ID for the fact row, convenient for internal pipeline operations.
- **date_key**, **product_key**, and **customer_key** are **dimension foreign keys**, not proof of grain.
- **source_event_id**, **source_version**, and **loaded_at** are metadata for lineage, deduplication, and operations.

**A surrogate key does not replace the grain's unique constraint.** If you only have **sales_line_fact_key PRIMARY KEY**, the same line **(O-1001, 1)** can be loaded twice with two different IDs. Then SUM(amount) is wrong even though every primary key is valid.

Dimensions can use surrogate keys because a single business entity can have multiple **historical versions** (SCD Type 2). For example, **product_id = A** stays the same while category attributes may change; **product_key** at the sale date attaches the right dimension version.

### 5.1. Degenerate Dimensions and Role-Playing Dates

**order_id** often resides directly in the fact table because filtering and tracing by order is needed, yet it does not necessarily have enough distinct attributes to warrant an ID-only dimension table. This is an example of a **degenerate dimension**.

A process with multiple dates—confirmation, payment, shipment—can have multiple **role-playing date keys** pointing to the same **dim_date**. Do not collapse them into one semantically vague **date_key** column and call it "transaction date."

### 5.2. Dimension Keys Are Not Always Available When the Event Arrives

An order is confirmed, but the analytics system has not yet received the product or customer dimension record. In that case, you need a **late-arriving dimension** policy:

- Temporarily use a clearly identified **unknown/pending dimension member**, then update the reference once data arrives.
- Create a minimal **inferred member** with the natural ID and backfill attributes later.
- Or defer loading the fact within a controlled window while monitoring the backlog.

**Do not automatically join to the current product record** and assume it matches the transaction time. For dimensions that change over time, you must select the version valid at event time or according to a published business rule.

## 6. From Grain to Measures: Classifying Additivity

Every measure must be able to answer:

1. At **what grain** is it generated?
2. What is its unit: **pieces, kg, VND, USD, seconds, percent**?
3. Across **which dimensions** can it be **SUMmed** and remain valid?
4. Is it a **flow/event value**, a **point-in-time state**, or a **precomputed ratio**?

### 6.1. Additive Measures — Summable Across Appropriate Dimensions

In **fact_order_line**:

- **quantity** can be summed across lines when units of measure are compatible; if one line is in kg and another is in pieces, a total of "4 units" is meaningless without grouping by unit.
- **gross_amount** can be summed by date/product/customer **if the currency and value definition match**.
- **discount_allocated** can be summed if every discount has been allocated exactly once.
- **net_line_amount = gross_amount − discount_allocated** can be summed to produce total line net revenue **before unmodeled components**.

If you need to report on cash collected, **do not treat a confirmed order as captured payment**. Use the payment source and a capture fact table with its own grain.

### 6.2. Semi-Additive Measures — Summable Only Across Some Dimensions

**End-of-day inventory** and **end-of-day balances** are examples:

- Summing inventory across **products** on **a single day** can be valid if units and aggregation rules match.
- Summing end-of-day inventory for **Monday + Tuesday** does not yield end-of-week inventory.
- To compute weekly average inventory, you must specify **AVG over days with snapshots**, handling missing days and weighting rules.

A periodic snapshot fact must explicitly attach the date; otherwise, SUM queries easily return large but meaningless numbers.

### 6.3. Non-Additive Measures — Cannot Be Summed Directly

- **Average selling price = SUM(amount) / SUM(quantity)**; do not sum or take an unweighted average of group averages.
- **Conversion rate = conversions / eligible_visits**; store numerator and denominator if aggregation across groups is needed.
- **Gross margin % = margin_amount / sales_amount**; do not sum product percentages.
- **COUNT(DISTINCT customer_id)**; daily unique customers **cannot be summed across days** when the same customer appears on multiple days.
- **Median / percentile**; requires distribution data, algorithms, or appropriate aggregation structures—you cannot sum sub-group percentiles to get an overall percentile.

A well-designed fact table generally stores **additive components** rather than every precomputed ratio, unless there is a clear use case and operational contract.

### 6.4. Avoid "Floating" Measures at a Different Grain

For example, **shipping_fee** is charged **once per order**. If you place that value on **every order line** without allocating it, summing by product multiplies the fee by the number of lines.

Valid options include:

1. **Keep shipping_fee in fact_order** at the one-order grain.
2. **Allocate shipping_fee down to each line** using a business-approved rule, store **allocated_shipping_fee**, and verify that the allocated sum equals the order-level fee.
3. **Exclude that metric from fact_order_line**, analyzing it only at the order level or combining the two sources at an appropriate aggregation level.

Choose based on the reporting questions. Do not "copy a field onto every row" just to have every column available in one table.

## 7. PostgreSQL Design for a Confirmed Order-Line Grain

Let us pick an illustrative contract:

> **fact_sales_line** contains exactly one row for each initially confirmed **(order_id, line_no)**; product name/price/quantity and discounts are locked at confirmation; subsequent refunds and adjustments are modeled in separate fact tables.

Assume the order locks **a single currency**, and tax and shipping are excluded from this fact's measures. If business terms change after confirmation, an adjustment event at its own grain must be emitted rather than silently overwriting rows, preserving the definition here.

### 7.1. Minimal Dimensions

~~~sql
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,              -- Example: 20261122
    calendar_date DATE NOT NULL UNIQUE
);

CREATE TABLE dim_product (
    product_key BIGINT PRIMARY KEY,            -- Surrogate key
    product_id TEXT NOT NULL,                 -- Natural ID
    product_name TEXT NOT NULL,
    category_name TEXT NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    UNIQUE (product_id, effective_from)
);

CREATE TABLE dim_customer (
    customer_key BIGINT PRIMARY KEY,           -- Surrogate key
    customer_id TEXT NOT NULL,
    segment_name TEXT NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    CHECK (effective_to IS NULL OR effective_to > effective_from),
    UNIQUE (customer_id, effective_from)
);
~~~

**dim_product** and **dim_customer** illustrate an SCD Type 2 structure. **UNIQUE (natural_id, effective_from)** prevents duplicate start timestamps, but **does not automatically prevent overlapping effective intervals**. The pipeline must enforce non-overlapping intervals, or use an appropriate exclusion constraint in PostgreSQL once time representation and write permissions are decided.

Not every dimension must use SCD Type 2. If the business only needs analysis by current attributes, Type 1 can be used; if products need to be grouped by their category at the time of sale, historical versions must be retained and resolved. **The fact grain remains the order line**, while history management is a property of the dimension and time-aware joins.

### 7.2. Fact Table and Grain Constraints

~~~sql
CREATE TABLE fact_sales_line (
    sales_line_fact_key BIGINT GENERATED ALWAYS AS IDENTITY
        PRIMARY KEY,
    order_id TEXT NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    source_confirmation_event_id TEXT NOT NULL,
    confirmed_at TIMESTAMPTZ NOT NULL,
    confirmed_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    customer_key BIGINT NOT NULL
        REFERENCES dim_customer(customer_key),
    currency CHAR(3) NOT NULL,
    quantity NUMERIC(18, 3) NOT NULL CHECK (quantity > 0),
    unit_price_at_confirmation NUMERIC(18, 2) NOT NULL
        CHECK (unit_price_at_confirmation >= 0),
    gross_amount NUMERIC(22, 2) NOT NULL
        CHECK (gross_amount >= 0),
    discount_allocated NUMERIC(22, 2) NOT NULL
        CHECK (discount_allocated >= 0),
    net_amount NUMERIC(22, 2) NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_fact_sales_line_grain
        UNIQUE (order_id, line_no),
    CONSTRAINT ck_fact_sales_line_discount
        CHECK (discount_allocated <= gross_amount),
    CONSTRAINT ck_fact_sales_line_net
        CHECK (net_amount = gross_amount - discount_allocated),
    CONSTRAINT ck_fact_sales_line_gross
        CHECK (
            gross_amount = ROUND(
                quantity * unit_price_at_confirmation, 2
            )
        )
);

CREATE INDEX ix_fact_sales_line_date_product
    ON fact_sales_line (confirmed_date_key, product_key);
~~~

**Design explanation:**

- **PRIMARY KEY (sales_line_fact_key)** provides a technical identifier; **UNIQUE (order_id, line_no)** expresses the business grain under our stated assumptions.
- **source_confirmation_event_id** is not unique because **one order confirmation event can generate multiple fact rows**.
- **confirmed_at** preserves the original timestamp; **confirmed_date_key** is the business date used for grouping on **dim_date**. If a specific timezone applies, the pipeline must convert it properly.
- **product_key**/**customer_key** must point to the dimension version valid under the agreed rule, not arbitrarily the latest record.
- **gross_amount**, **discount_allocated**, and **net_amount** are all at the **line grain** and carry formula constraints. The example uses **ROUND(..., 2)** to illustrate a two-decimal-place rule. Real currency systems may use **integer minor units** or per-currency scale and rounding.
- **net_amount** here is strictly **net line amount after allocated discount**, automatically excluding tax, shipping, and refunds.
- **quantity** uses NUMERIC because some businesses deal in fractional quantities (kg, meters, etc.), but the **unit of measure** must be recorded or aggregated rows must be guaranteed to share the same unit. This demo table assumes uniform units when summing quantity.

### 7.3. Sample Data and Query Results

To verify, assume the date and dimension tables have been loaded correctly:

~~~sql
INSERT INTO dim_date (date_key, calendar_date)
VALUES (20261122, DATE '2026-11-22');

INSERT INTO dim_product (
    product_key, product_id, product_name, category_name,
    effective_from, effective_to
) VALUES
    (101, 'A', 'Product A', 'Supplies',
        TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL),
    (102, 'B', 'Product B', 'Supplies',
        TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL),
    (103, 'C', 'Product C', 'Supplies',
        TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL);

INSERT INTO dim_customer (
    customer_key, customer_id, segment_name,
    effective_from, effective_to
) VALUES
    (201, 'C1', 'RETAIL',
        TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL),
    (202, 'C2', 'RETAIL',
        TIMESTAMPTZ '2026-01-01 00:00:00+07', NULL);
~~~

Three fact rows matching the table in Section 2:

~~~sql
INSERT INTO fact_sales_line (
    order_id, line_no, source_confirmation_event_id,
    confirmed_at, confirmed_date_key,
    product_key, customer_key, currency,
    quantity, unit_price_at_confirmation,
    gross_amount, discount_allocated, net_amount
) VALUES
    ('O-1001', 1, 'confirm-O-1001',
     TIMESTAMPTZ '2026-11-22 08:00:00+07', 20261122,
     101, 201, 'VND', 2, 100000, 200000, 6000, 194000),
    ('O-1001', 2, 'confirm-O-1001',
     TIMESTAMPTZ '2026-11-22 08:00:00+07', 20261122,
     102, 201, 'VND', 1, 120000, 120000, 4000, 116000),
    ('O-1002', 1, 'confirm-O-1002',
     TIMESTAMPTZ '2026-11-22 10:00:00+07', 20261122,
     103, 202, 'VND', 1, 90000, 90000, 0, 90000);
~~~

Query at the **date × currency grain**:

~~~sql
SELECT
    d.calendar_date,
    f.currency,
    COUNT(*) AS order_line_count,
    COUNT(DISTINCT f.order_id) AS distinct_order_count,
    SUM(f.quantity) AS sold_quantity,
    SUM(f.gross_amount) AS gross_amount,
    SUM(f.discount_allocated) AS discount_amount,
    SUM(f.net_amount) AS net_line_amount
FROM fact_sales_line AS f
JOIN dim_date AS d
    ON d.date_key = f.confirmed_date_key
GROUP BY d.calendar_date, f.currency
ORDER BY d.calendar_date, f.currency;
~~~

Expected output for the sample data: **1 date**, **3 lines**, **2 distinct orders**, **4 units**, **410,000 VND gross**, **10,000 VND discount**, and **400,000 VND net_line_amount**.

Pay attention to **COUNT(DISTINCT order_id)**: when grouped by product, a multi-product order can be counted in multiple groups. **Summing distinct order counts across products does not necessarily equal the system-wide distinct order count.** When a report changes aggregation level, distinct counts must be computed over the target set or pulled from an order-grain fact table with its own rules.

## 8. Selecting Dimension Versions at the Declared Timestamp

Grain does not only determine the unique key; it also determines **the point in time at which dimension joins are meaningful**.

Suppose product A moves from the **Supplies** category to **Stationery** on December 1. November reports may ask:

1. **Sales by category at the time of sale:** use the **dim_product** version effective when the order line was confirmed.
2. **Historical sales classified under the current category:** use the latest classification, while explicitly stating that this is a historical reclassification.

Both questions can be valid, **and they are not the same metric**.

A point-in-time dimension version lookup:

~~~sql
SELECT
    p.product_key
FROM dim_product AS p
WHERE p.product_id = $1
  AND p.effective_from <= $2::TIMESTAMPTZ
  AND (
      p.effective_to IS NULL
      OR $2::TIMESTAMPTZ < p.effective_to
  );
~~~

This query **must return exactly one row** if dimension history is complete and non-overlapping. Returning 0 rows indicates a late-arriving dimension or a gap in effective intervals. Returning multiple rows indicates an overlapping SCD bug; never pick an arbitrary version with LIMIT 1 and silently hide the error.

Half-open boundaries **[effective_from, effective_to)** prevent double-counting at version transitions when two intervals are contiguous. To support this join at scale, the pipeline must resolve dimension keys by natural key + event time with appropriate performance and indexing.

### 8.1. Business Dates Must Have a Defined Timezone

An order confirmed at **2026-11-22 00:30 in Vietnam** has a different date in UTC. If reporting follows the **Asia/Ho_Chi_Minh** business date, the date assigned to **dim_date** must be computed in that timezone, not defaulted to UTC.

In PostgreSQL:

~~~sql
SELECT
    (TIMESTAMPTZ '2026-11-22 00:30:00+07'
        AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS business_date;
-- 2026-11-22
~~~

If the company operates across multiple timezones, you must specify whether the date follows the **point of sale, legal entity, or global reporting**. A "daily" grain is incomplete until you know **whose day it is**.

## 9. Breaking Grain by Putting Multiple 1:N Relationships into One Fact

Imagine an order with:

- **3 order lines**,
- **2 payment captures**,
- **2 shipment packages**.

An uncontrolled join across order, items, captures, and shipments can produce up to **3 × 2 × 2 = 12 rows** for one order. If you then SUM the line amounts, each line can be multiplied **4 times**.

~~~sql
-- DANGEROUS PATTERN: three 1:N branches joined directly.
SELECT
    o.order_id,
    SUM(i.line_amount) AS wrong_amount
FROM orders AS o
JOIN order_items AS i ON i.order_id = o.order_id
JOIN payment_captures AS p ON p.order_id = o.order_id
JOIN shipments AS s ON s.order_id = o.order_id
GROUP BY o.order_id;
~~~

This is an **anti-pattern snippet**; table and column names are illustrative, not the schema created in Section 7. **SUM(DISTINCT i.line_amount)** is not a general fix: two legitimate lines can share the same monetary amount and be wrongly collapsed.

### 9.1. Designing Properly by Grain

- **fact_sales_line**: one locked order line; do not pull payments/shipments directly into the line grain.
- **fact_payment_capture**: one capture, with its own capture ID, captured amount, and timestamp.
- **fact_shipment_event**: one shipping event, with its own shipment/event ID.
- If a report needs to combine them, **aggregate each branch by order_id at the appropriate level before joining**, or query separate fact tables through conformed dimensions with rules that prevent row multiplication.

Example summing payments per order before joining to an order-grain table:

~~~sql
WITH capture_by_order AS (
    SELECT order_id, currency,
           SUM(captured_amount) AS captured_total
    FROM payment_captures
    WHERE status = 'SUCCEEDED'
    GROUP BY order_id, currency
)
SELECT
    o.order_id,
    c.currency,
    c.captured_total
FROM orders AS o
LEFT JOIN capture_by_order AS c
    ON c.order_id = o.order_id;
~~~

If an order has captures in multiple currencies, the join can return **multiple rows per order**. Therefore, keep **currency** in the payment total's grain and do not use the result to sum order-level measures indiscriminately. Requiring one row per order demands explicit conversion rules or corresponding business constraints.

## 10. Multi-Valued Dimensions, Bridge Tables, and Allocation

A sales line can apply **two promotion codes**, an article can have multiple authors, or a customer can belong to multiple segments simultaneously. You cannot assume every fact row has only one value for every dimension.

For example, line **O-1001/1** has a net amount of **194,000 VND** and two promotions **PROMO-A** and **PROMO-B**. Joining through a bridge table and directly summing net_amount yields **388,000**, double the true amount.

A **bridge table** can model many-to-many relationships, but monetary aggregations require explicit rules:

- **Presence checks only:** filter facts with EXISTS or DISTINCT fact keys without double-summing.
- **Allocating amounts across promotions:** store an **allocation_weight** or allocated amount so the parts for one fact follow the contract, e.g., 0.6 + 0.4 = 1.
- **Dedicated reporting on promotion participation counts:** counting a line multiple times may be acceptable **if the metric is defined as promotion participations**, not revenue.

**Do not use DISTINCT on amount** to make multiplication bugs disappear. Two different transactions with the same amount must still be counted twice.

## 11. Grain Reconciliation: Checking Independently of Measures

A fact table can coincidentally return the right total amount while missing rows and duplicate rows cancel each other out. Therefore, reconciliation must separate **grain**, **scope**, and **measures**.

### 11.1. Checking for Duplicate Business Keys

~~~sql
SELECT order_id, line_no, COUNT(*) AS duplicated_rows
FROM fact_sales_line
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

With the unique constraint from Section 7, this query must return zero rows if all writes go through the table properly. It remains useful for staging tables, file exports, or target warehouses without enforced constraints.

If the fact truly has a grain of **one line revision**, the **(order_id, line_no)** key is too strict; you need to add **revision_id/event_id** and rewrite the grain statement. That is not a flaw in UNIQUE, but a business distinction that needs clarification.

### 11.2. Checking Dimension Keys and Date Coverage

If a warehouse omits physical FKs to optimize load performance, equivalent pipeline checks are required:

~~~sql
SELECT f.order_id, f.line_no
FROM fact_sales_line AS f
LEFT JOIN dim_product AS p
  ON p.product_key = f.product_key
WHERE p.product_key IS NULL;
~~~

Use the same pattern to verify **customer_key** and **date_key**. You also need to verify that **product_key** points to the right **product_id** and the **SCD version effective at confirmed_at**; key existence alone does not prove version correctness.

### 11.3. Reconciling Row Counts and Totals Against the Source at the Same Grain

Suppose the source system has **source_confirmed_order_lines** with **(order_id, line_no, gross_amount, discount_allocated, net_amount)** at confirmation time. The table below is an illustrative name for a normalized source, not a table created in this lesson's DDL.

~~~sql
WITH source_by_order AS (
    SELECT
        order_id,
        COUNT(*) AS source_line_count,
        SUM(net_amount) AS source_net
    FROM source_confirmed_order_lines
    GROUP BY order_id
),
fact_by_order AS (
    SELECT
        order_id,
        COUNT(*) AS fact_line_count,
        SUM(net_amount) AS fact_net
    FROM fact_sales_line
    GROUP BY order_id
)
SELECT
    COALESCE(s.order_id, f.order_id) AS order_id,
    s.source_line_count,
    f.fact_line_count,
    s.source_net,
    f.fact_net
FROM source_by_order AS s
FULL OUTER JOIN fact_by_order AS f
  ON f.order_id = s.order_id
WHERE s.order_id IS NULL
   OR f.order_id IS NULL
   OR s.source_line_count IS DISTINCT FROM f.fact_line_count
   OR s.source_net IS DISTINCT FROM f.fact_net;
~~~

A **FULL OUTER JOIN** catches orders present only in the source or only in the fact table, in addition to line-count and monetary mismatches. However, comparisons must align on **the same confirmed status, time window, currency, and watermark**. If the fact table is loaded asynchronously, newly committed source data may not have arrived yet; that can be acceptable lag within bounds, not necessarily an immediate bug.

To ensure rows were not swapped while still matching totals, you also need to compare detail attributes, unit prices, quantities, and data fingerprints by **(order_id, line_no)**. A matching total amount does not guarantee every row is right.

### 11.4. Edge Cases to Include in the Test Suite

- **Zero-line** orders still in DRAFT: must not be loaded into the confirmed-line fact table.
- Multi-line orders with the same **product_id**: remain multiple rows if they are distinct business lines.
- Two lines with identical **gross_amount**: neither line is dropped by SUM(DISTINCT).
- Orders confirmed and then **canceled/refunded**: preserve fact history per contract and model adjustments separately.
- Replayed confirmation events: do not create duplicate-grain records.
- A line whose **quantity** is edited before vs. after confirmation: the two points in time follow different rules.
- Missing or late-arriving dimensions: covered by an inferred/unknown member or retry policy.
- Different **currencies**, different **timezones**, product category changes, and customer segment changes.
- Multiple payments/shipments for the same order: do not multiply rows.
- Historical backfills and post-fix reconciliation: do not alter finalized facts without evidence.

## 12. Loading and Correcting Facts According to Grain

### 12.1. Idempotency When the Same Event Is Replayed

With the **(order_id, line_no)** grain, a unique constraint can prevent duplicate inserts:

~~~sql
INSERT INTO fact_sales_line (
    order_id, line_no, source_confirmation_event_id,
    confirmed_at, confirmed_date_key,
    product_key, customer_key, currency,
    quantity, unit_price_at_confirmation,
    gross_amount, discount_allocated, net_amount
)
VALUES (
    'O-1001', 1, 'confirm-O-1001',
    TIMESTAMPTZ '2026-11-22 08:00:00+07', 20261122,
    101, 201, 'VND',
    2, 100000, 200000, 6000, 194000
)
ON CONFLICT (order_id, line_no) DO NOTHING;
~~~

This prevents inserting same-grain rows on retries, but **it is not enough** to deem the pipeline fully correct. If two different events share the same key yet have **different quantities or prices**, **DO NOTHING** hides the conflict. You need to compare payloads, distinguish equivalent retries from **business edits**, and raise an error/quarantine records that violate the contract.

If the business requires multiple confirmed versions, there are two standard patterns:

- Change the grain to **(order_id, line_no, revision_id)** and define each revision as an event row, with a clear rule for querying the latest state.
- Keep the initially confirmed line fact table and record **fact_order_line_adjustment** at an adjustment-event grain, referencing the original line and delta amounts.

You cannot update a single keyed row while keeping the old grain statement without redefining what the measures mean.

### 12.2. Late-Arriving Facts, Backfills, and Consistent Snapshots

An event confirmed yesterday that arrives in the warehouse today **belongs to the confirmation date**, not automatically to the worker's ingestion date. Both **confirmed_at** and **loaded_at** can be stored; the two timestamps answer different questions.

When backfilling millions of rows:

1. Choose a source **snapshot/checkpoint** and a mechanism to capture changes occurring during the load.
2. Resolve dimension keys to the version valid at event time.
3. Load according to the grain, deduplicate, and compare row counts/amounts.
4. Catch up with new data; prevent old backfill jobs from overwriting newer versions if the design supports updates.
5. Reconcile at the same watermark and switch read traffic only after passing criteria.

Note that transaction facts defined as **immutable events** can append by grain; periodic snapshots may require **recomputing/overwriting a period** per policy; accumulating snapshots require **milestone updates**. The loading strategy must follow the **fact type and grain**, rather than using the same MERGE for every table.

## 13. Grain Drives Queries, Partitioning, and Physical Modeling

Only after locking down the grain and keys should you consider physical organization:

- **Partitioning by confirmed_date_key** can speed up date-range scans when row counts grow very large. However, if the database requires **unique constraints on partitioned tables to include the partition key**, verify whether the business key **(order_id, line_no)** is still protected across all partitions; never silently drop uniqueness guarantees.
- **An index on (confirmed_date_key, product_key)** serves certain date-and-product queries, but selectivity, sort order, and workload must be verified; too many indexes increase ingestion cost.
- **Clustered/columnar warehouses** typically optimize analytical scans better than OLTP row stores; the same fact grain can be stored under a different physical layout.
- **A materialized view or aggregate table** at the **(day, product, currency)** grain can accelerate reports, but it is a **higher-grain derived table**, not a replacement for the line-level fact source.
- **Rollups** are only valid for measures with appropriate additivity; distinct counts, ratios, or period-end states require different formulas.
- **Dimension cardinality** and the number of distinct keys affect storage size and performance; do not choose a coarser grain just to save space if business questions require line-level detail.

### 13.1. Unit of Storage and Unit of Analysis Are Different Concepts

An **Order** document may embed multiple **items[]**, yet in analytics each item element can still be **one fact row at the order-line grain**. Conversely, a relational table with one row per order may still lack enough detail for product analysis.

Therefore, grain is the **logical semantics of one unit of observation**, independent of whether it lives in a PostgreSQL row, a JSON array element, or a record in a Parquet file.

## 14. Comparison Across Relational, Document, Graph, and Analytics

| Model | What Does One "Fact Row" Correspond To? | Representation | What Must Be Preserved |
| --- | --- | --- | --- |
| **Relational OLTP** | Order line, capture, shipment event, etc., in operational tables | PK/FK, transactions, event history | Business keys, no row multiplication via JOINs |
| **Dimensional/OLAP** | One observation at the declared grain | Fact + dimension keys + measures | SCD, additivity, lineage, period/timezone |
| **Document** | Order containing an items array; when exported for analytics, each item can be a fact | Embedded snapshot or lines exploded from array | Do not duplicate items when processing payments/shipments; preserve IDs/amounts |
| **Graph** | A purchase edge, interaction event, or relationship | Edge properties or event nodes | Distinguish a single current edge from multiple historical events; avoid counting duplicate edges |
| **Aggregate/read projection** | One day × product × currency or another grouping | Aggregate table, materialized view, search analytics | Traceability from source fact to group; know which measures are additive |

In a **document database**, embedding items inside an Order works well for detail reads, but does not make an **order-level total** an additive measure **per item**. When **unwinding items**, you must distinguish order-level measures from line-level measures.

In a **graph database**, a **Customer–PURCHASED–Product** relationship can lack distinction across purchase occurrences, line numbers, and timestamps if only a single edge is kept. If you want to count transactions, you need a **PurchaseEvent/OrderLine** entity or edge with an ID and appropriate grain, not just an "ever purchased" relationship.

In **analytics**, a fine-grained fact table serves as the source to build multiple coarser-grained aggregates; the coarser the grain, the more you lose the ability to query dimensions that are no longer present. Choose grain based on the set of questions to answer, privacy requirements, and storage cost.

## 15. Grain Contract Template for Design Reviews

A team can use the following checklist before approving a fact table:

| Question | Expected Evidence |
| --- | --- |
| What is the business process? | Order-line confirmation, capture, end-of-day inventory, etc. |
| What exactly is one row? | A single sentence describing the unit of observation |
| When is a row created? | Event / snapshot point / process completion |
| Does the grain change on business edits? | Append, correction, or milestone update |
| What is the business key? | Natural combination and UNIQUE/idempotency |
| Is there a tenant or partitioning unit? | Actual uniqueness scope |
| Which dimensions are valid on that row? | Product/customer/date/warehouse and historical version |
| Are there multi-valued dimensions? | Bridge, filtering, or explicit allocation |
| Which measures make sense at this grain? | Units, formulas, NULL semantics, rounding rules |
| Across which dimensions is SUM valid? | Additive, semi-additive, non-additive |
| How many time concepts are needed? | Business event time, snapshot date, loaded time |
| What happens on refunds/cancellations/adjustments? | Separate fact, delta/version, or published procedure |
| How are late and duplicate data handled? | Event ID, checkpoint, SCD matching, reconciliation |
| How is it verified against the source? | Distinct grain count, row count, amounts, ID-by-ID match |
| Do physical queries meet SLOs? | Explain plans, benchmarks, workload-aligned partitioning/indexing |

If the answer to "what is one row" is still vague, **do not start with CREATE TABLE or picking measures**. Clarify the business semantics first; that saves far more effort than refactoring entire ETL pipelines and reports later.

## 16. Practice Exercises

### Exercise 1 — Choose Grain and Key for Sales Lines

The system has an order **ORD-88** containing three lines; the same product can appear on two lines because different pricing policies apply. The requirement is to analyze quantity and net amount by product at confirmation time.

**Question:** What grain and business key should you choose? Is using **(order_id, product_id)** as UNIQUE safe?

### Exercise 2 — Order SUM After a JOIN

An order has three order lines and **total_items_net = 500,000 VND**. A report joins orders with order lines and sums total_items_net, getting **1,500,000 VND**.

**Question:** Where is the bug? What are two ways to fix it according to grain?

### Exercise 3 — Two-Day End-of-Day Inventory

Warehouse K has end-of-day stock of 10 units of product A on Monday and 12 units of product A on Tuesday. The team reports "two-day inventory" as SUM(10+12)=22.

**Question:** What does the number 22 mean? How should you calculate Tuesday's closing stock or the daily average?

### Exercise 4 — Sales and Captures at Different Grains

An order has 2 order lines, while the payment gateway allows 3 captures. The team wants one fact table keyed by **order_id** with a **capture_amount** column, while also reporting by product.

**Question:** Can one row per order accurately represent every capture and every product? How should the fact tables be split?

### Exercise 5 — Daily Average Price

Day A has 2 sales lines with total amount 300,000 VND and total quantity 3. Day B has 7 lines with total amount 700,000 VND and total quantity 14. The team takes **(300,000/3 + 700,000/14)/2** as the average selling price for the whole period.

**Question:** Is the formula correct? What is the true volume-weighted average price?

### Exercise 6 — Product Changes Category

On Nov 15, product P is in category A and has one sales line. On Dec 1, P moves to category B. A report asks for "November sales by **category at the time of sale**."

**Question:** Should you use the current dimension or the SCD version effective at the time of sale? If both classifications are needed, how can they be presented?

### Exercise 7 — Two Promotions on the Same Line

An order line has a net_amount of 200,000 VND and is linked to two promotions. Joining with a bridge table creates two rows, each keeping net_amount = 200,000; the report sums them to 400,000.

**Question:** What went wrong? Propose one method to count presence and one method to allocate the amount.

### Exercise 8 — Retried Confirmation Event

The source replays the same event containing the lines of order O-200. The pipeline generates a new surrogate fact ID on every load and has no grain-level UNIQUE constraint. Total amounts are doubled.

**Question:** Why is a surrogate PK insufficient? What key is needed, and how should cases with the same key but different amounts be handled?

### Suggested Solutions

1. Grain: **one locked order line**, key **(order_id, line_no)** or a stable line ID; add tenant ID if needed. **(order_id, product_id)** is unsafe because one product can legitimately appear on multiple lines.
2. An order-level measure was duplicated across three lines. You can either **aggregate orders at the one-order grain**, or **allocate/sum line-level measures** if monetary terms have been properly allocated. Do not fix it with a generic SUM(DISTINCT amount).
3. **22** is not closing inventory; it is the sum of two point-in-time snapshots, which is usually meaningless. Tuesday's closing stock is **12**. A simple average across two days that both have snapshots is **(10+12)/2 = 11**, assuming policy permits an equal-weighted daily average.
4. No, because **order, order line, and capture** are three different grains. Use **fact_sales_line** and **fact_payment_capture** with a unique capture ID; optionally add an order/order-lifecycle fact table if needed. When combining them, aggregate to the matching level and avoid row multiplication.
5. Wrong, because it takes an unweighted average of daily ratios rather than weighting by quantity. The weighted average price per unit sold is **(300,000+700,000)/(3+14) ≈ 58,823.53 VND/unit**. Total amount and total quantity are the two additive components to sum before dividing.
6. Use the **dim_product version effective at confirmed_at** to report the category at sale time: A. If analysis by current category is also needed, build a separate current-attribute join/classification and name the two metrics clearly.
7. Joining the bridge table caused one fact row to appear twice. To check whether a promotion applied, use **EXISTS** or count distinct fact keys. To allocate amounts, use weights summing to 1—for example 0.6 and 0.4—producing **120,000** and **80,000 VND** per policy.
8. A surrogate PK only protects each technical INSERT, not the same business line. Add **UNIQUE(order_id, line_no)** or a true line ID, and verify idempotent retries. If payloads differ for the same key, investigate corrections/versions rather than hiding conflicts with **ON CONFLICT DO NOTHING**.

## 17. Takeaways

**Declaring the grain is the foundational decision of a fact table.** It comes before keys, measures, dimensions, and physical tuning because it specifies **what fact a single row represents**. Keys must enforce the grain; measures must be meaningful at the grain; JOINs and SUMs must preserve row counts, units, and additivity.

**One business process may require multiple fact tables at different grains**: sales lines, captures, shipments, end-of-day inventory, and order lifecycle. Never force all events into a single table just because they share **order_id** or **product_id**.

The shortest self-check: **"If I duplicate this row, what gets double-counted? If I merge two rows, what fact is lost? If I SUM this column across time or another dimension, does the result still make sense?"** Being able to answer these three questions is the foundation for designing analytical data that is unambiguous, evolvable, and verifiable.
