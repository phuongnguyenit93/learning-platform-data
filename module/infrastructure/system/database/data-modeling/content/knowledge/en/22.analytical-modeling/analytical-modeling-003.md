# Measures, Dimensions, and Their Relationships

## 1. Why Does Analytical Modeling Start from Questions, Not Tables?

The **DATABASE_DATA_MODELING** module builds the skill of translating requirements into data models with appropriate entities, relationships, constraints, keys, and physical schemas. In the **Analytical Modeling** chapter, the goal is not merely to store orders or products for daily transactions, but to consistently answer aggregate questions:

- What is July's net sales revenue by product category?
- Is unit sales volume by region increasing or decreasing?
- Which customer segment generates the highest profit?
- How many orders make up the Average Order Value (AOV)?
- What is the month-end inventory balance, and why cannot daily balances be summed?
- If a product changes categories, do historical reports use the category at sale time or today's category?

The three concepts governing answer quality are **measures**, **dimensions**, and **the relationships between them**. Yet before laying out fact and dimension tables, you must first define the **grain**: what exactly does each row represent?

In this lesson, examples use an e-commerce system with orders, products, customers, stores, revenue, inventory, and marketing campaigns. Learners progress from business definitions to star schemas, PostgreSQL SQL, Slowly Changing Dimensions (SCD), aggregations, avoiding double-counting, and data test suites.

**After this lesson, you should be able to:** define fact grain and keys; classify additive and non-additive measures; separate dimensions from measures; construct fact–dimension relationships with proper cardinality; compute derived metrics with clear denominators; handle many-to-many relationships and time-varying attributes; and verify figures via reconciliation.

## 2. What Is a Measure? What Is a Dimension?

A **measure** is a quantitative value recorded or computed at a specific grain. For example, on a single sales line: quantity 2, unit price 100,000 VND, discount 20,000 VND, net revenue 180,000 VND, and cost of goods sold 120,000 VND.

A **dimension** describes the context of a measure and enables filtering, grouping, and slicing. Examples: sale date, product name, category, city, region, sales channel, customer segment.

| Field | Role | Why? |
|---|---|---|
| `quantity = 2` | Measure | Unit quantities sold can be summed across periods if units match |
| `net_amount = 180000` | Measure | Monetary amount on one sales line |
| `cogs_amount = 120000` | Measure | Cost of goods sold recorded for the line |
| `unit_price = 100000` | Base quantitative attribute | Participates in revenue calculation but cannot be arbitrarily summed across rows |
| `product_id = P01` | Dimension identifier | Links to the product; IDs are never summed |
| `category_name = Food` | Dimension attribute | Used to group revenue |
| `year = 2026` | Time dimension attribute | Used for grouping/filtering, not a business measure |
| `order_number = O100` | Transaction identifier | Can be `COUNT DISTINCT`, never `SUM` |
| `gross_margin_pct = 34.29%` | Derived metric | Must be computed from total profit divided by total revenue |

**Do not classify measures solely by numeric data type.** Postal codes, product codes, and phone numbers may be numeric yet carry no additive meaning. Conversely, a categorical status may require counting records to become a measure.

### 2.1. Breaking a BI Question into Components

Question: **"Net sales revenue in July 2026 by product category in the South region"**.

- Measure: total net sales.
- Time dimension: month and year of the sales recognition date.
- Product dimension: category **at transaction time** if reporting as-was.
- Store dimension: region `SOUTH`.
- Filter: only eligible recognized sales lines; cancelled orders are excluded.
- Currency: VND, or amounts converted under an explicit rule.
- Grain: one **sold order line**, not one order or one day.

Every choice must be settled before writing SQL. The same label "net revenue" may be interpreted differently if the sales team calculates it before returns while finance calculates it after returns and taxes.

## 3. Grain Is the Contract of a Fact Row

A **fact table** stores analyzable events or states. Grain answers: **what entity, point in time, and level of detail does one fact row represent?**

| Grain | What One Row Means | Example Measures |
|---|---|---|
| Sales line | One product line of a recognized sales order | `quantity`, `net_amount`, `cogs_amount` |
| Order | One recognized order | `order_total`, `shipping_fee`, `item_count` |
| SKU–warehouse–day | Stock of one SKU at one warehouse at end of day | `closing_qty` |
| Customer–month | State of one customer in a monthly period | MRR, subscription status |
| Visit session | One valid session | `page_views`, `duration` |
| Payment attempt | One payment transaction | `paid_amount`, `fee_amount` |
| Shipment | One shipment | `delivered_qty`, `shipping_cost` |

**Grain must be written in business language before assigning technical keys.** For instance, in a sales-line fact, order `O100` may have two lines `L1` and `L2`. `COUNT(*) = 2` is the line count, not the order count. To count orders, use `COUNT(DISTINCT order_number)` within the appropriate scope or use an order-grain fact.

### 3.1. Wrong Grain Multiplies Measures

A shipping fee of 30,000 VND belongs to **order `O100`**. If you copy that same 30,000 onto every line of the order and `SUM` on the product-line fact, a three-line order fabricates 90,000 VND in shipping fees.

There are three options:

1. Store `shipping_fee` in **`fact_order`** at order grain.
2. **Allocate** `shipping_fee` down to each line using a justified rule; summing at line grain is then valid if the allocated total matches the order fee.
3. Maintain both `fact_order` and `fact_sales_line`, aggregating and joining only at a compatible grain.

Never force order-level measures into line-level rows and expect `SUM` to infer cardinality.

### 3.2. Transaction Grain Differs from Snapshot Grain

- Sales lines measure **events that occurred**.
- Daily inventory measures **stock levels at end of day**.
- Monthly subscriptions measure **periodic state**.

Merely sharing `date_key` and `product_key` across two tables does not mean they can be joined row-for-row without multiplying data.

## 4. Additivity of Measures

Measures must be classified by **the dimensions across which addition makes sense**.

| Type | Definition | Examples |
|---|---|---|
| **Additive** | Can be summed across compatible dimensions without duplicating observed units | Quantity sold, net sales, discounts, COGS |
| **Semi-additive** | Additive across some dimensions, not across others | Inventory, account balance, period-end MRR |
| **Non-additive** | Cannot be summed directly | Conversion rate, profit margin %, unit price, AOV |
| **Distinct count** | Counts unique keys; cannot be summed across overlapping groups | Unique customers, distinct orders |

### 4.1. Even Additive Measures Have Conditions

Revenue can be summed across date, store, and product only if fact rows are **not duplicated**, transactions share the same recognition rules, and currency is consistent. Summing 100 USD and 100 VND without conversion is meaningless.

Quantity sold also requires compatible units of measure. Summing 10 pieces with 5 kg into "15 items" is not interpretable without a unit conversion policy.

### 4.2. Semi-Additive: End-of-Day Inventory

| Date | Closing Stock |
|---|---:|
| Jul 01 | 30 |
| Jul 02 | 27 |
| Jul 03 | 40 |

Period-end stock is **40**, not `30 + 27 + 40 = 97`. You can sum stock across multiple warehouses **on the same date** if product, unit, and ownership scope match; never sum snapshots across dates.

An "average inventory" measure requires sampling rules and time weighting. `AVG(30, 27, 40) ≈ 32.33` only means the average of three observed snapshots, not necessarily the minute-by-minute average if levels fluctuate between snapshots.

### 4.3. Non-Additive: Ratios Must Be Recomputed from Numerator and Denominator

Suppose Region A has 10 orders and 1 million revenue; Region B has 90 orders and 4.5 million revenue:

~~~text
AOV_A = 1,000,000 / 10 = 100,000
AOV_B = 4,500,000 / 90 = 50,000

Overall_AOV = 5,500,000 / 100 = 55,000
Not (100,000 + 50,000) / 2 = 75,000
~~~

For profit margin, cancellation rate, conversion, and churn: divide **summed numerators by summed denominators** under consistent filters and analytical grain. Storing only rounded percentages loses the information needed for accurate roll-ups.

### 4.4. Distinct Counts Are Not Additive Across Overlapping Groups

A customer who shops at two stores appears in the customer count of both. Summing per-store customer counts can exceed the company-wide customer count. Likewise, an order containing products from two categories is counted in both categories.

If you need overall unique customers or orders, you must **recount at the overall level**, never sum pre-grouped distinct counts. Approximate counting structures like sketches must also state error bounds and merge rules.

## 5. Dimensions and Descriptive Attributes

Dimensions answer **"by what?"**, **"where?"**, **"when?"**, and **"which group does it belong to?"**.

- **Date:** day, day of week, month, quarter, year, fiscal period.
- **Product:** code, name, category, department, brand.
- **Customer:** customer ID, segment, region, account type.
- **Store:** store code, city, region, sales channel.
- **Campaign:** campaign name, target group, marketing channel.
- **Currency:** currency code and display/unit rules.
- **Channel:** web, app, partner, physical store.

### 5.1. Hierarchies and Drill-Down

~~~text
Department → Category → Subcategory → Product
Year → Quarter → Month → Day
Country → Region → City → Store
~~~

Hierarchies support roll-up (SKU → subcategory) and drill-down (year → month). Yet a hierarchy is not guaranteed to be a rigid tree: products may belong to multiple categories, sales regions reorganize, and fiscal calendars differ from calendar years. Explicitly note if parent nodes can change or if multiple parents exist.

### 5.2. Natural Keys and Surrogate Keys

The **business key** identifies the entity in operations, such as `product_id = P01`.

The **surrogate key** identifies **one dimension row**, such as `product_key = 1001`, which is crucial when the dimension stores multiple SCD Type 2 versions:

~~~text
product_key | product_id | category | valid period
1001        | P01        | Food     | [01/01, 08/01)
1002        | P01        | Gifts    | [08/01, +∞)
~~~

A sale on Jul 01 must link to `product_key = 1001` if reporting uses **classification as of sale date**. Never grab the latest `product_key` for `product_id` and attach it to all historical transactions.

### 5.3. Conformed, Role-Playing, and Degenerate Dimensions

**Conformed dimensions** share consistent meaning across multiple facts: unified Product/Date/Store dimensions allow comparing revenue, returns, and inventory under identical definitions.

**Role-playing dimensions** reuse the same `dim_date` in multiple roles: `order_date_key`, `paid_date_key`, `shipped_date_key`. Queries use separate aliases and state clearly which milestone applies.

A **degenerate dimension** is a business identifier placed directly in the fact table, such as `order_number`, when it needs no separate descriptive dimension table. It serves order counting, drill-through, and reconciliation, not summation.

## 6. Fact–Dimension Relationships in a Star Schema

A **star schema** places the fact at the center, with dimensions describing the context of each record.

~~~mermaid
erDiagram
    DIM_DATE ||--o{ FACT_SALES_LINE : "sale date"
    DIM_PRODUCT ||--o{ FACT_SALES_LINE : "product version"
    DIM_STORE ||--o{ FACT_SALES_LINE : "store"
    DIM_CUSTOMER ||--o{ FACT_SALES_LINE : "customer"
    DIM_DATE {
        int date_key PK
        date calendar_date
        int calendar_year
        int calendar_month
    }
    DIM_PRODUCT {
        bigint product_key PK
        text product_id
        text category_name
        date valid_from
        date valid_to
    }
    DIM_STORE {
        bigint store_key PK
        text store_id
        text region_code
    }
    DIM_CUSTOMER {
        bigint customer_key PK
        text customer_id
        text segment_code
    }
    FACT_SALES_LINE {
        bigint sales_line_key PK
        text source_line_id UK
        text order_number
        int sale_date_key FK
        bigint product_key FK
        bigint store_key FK
        bigint customer_key FK
        int quantity
        decimal net_amount
        decimal cogs_amount
    }
~~~

Each sales-line fact links to one date, one product version, one store, and optionally one customer. One dimension row may be referenced by many fact rows, but each fact row must select the exact matching version.

### 6.1. Why Is the Star Schema Commonly Used?

A star schema optimizes high-volume aggregate reads: the fact holds measures and keys; dimensions hold descriptions. It is usually simpler than joining a deeply normalized OLTP model across numerous intermediate tables.

A **snowflake schema** normalizes dimensions further, e.g., `dim_product → dim_category → dim_department`. It reduces attribute duplication and can help when hierarchies are centrally governed, at the expense of extra JOINs and cross-level history management. Choose star or snowflake based on workload and governance rather than dogma.

### 6.2. One-to-Many Relationships Must Preserve Grain

Joining a fact row to a dimension on a **unique primary/surrogate key** does not increase row count. Conversely, joining to dimension history solely on `product_id` without filtering the effective interval multiplies each transaction by the number of historical versions.

If a product has three category versions, joining a fact to all three triples summed revenue. Use the `product_key` resolved during ETL, or a temporal join with date in `[from, to)` backed by non-overlap constraints.

## 7. Analytical Modeling Design Workflow

A verifiable sequence:

1. **Select the business process:** sales, returns, inventory, visits, payments.
2. **State the grain:** one sales line, one order, one SKU–warehouse–day, one session.
3. **List dimensions** used for filtering/grouping at that grain.
4. **List measures** and additivity properties: additive, semi-additive, non-additive.
5. **Define constraints:** unique source key, FKs, dimension versions, currency/unit validity, transaction statuses.
6. **Design ETL/ELT workflows:** dimension version lookup, deduplication, late data, retroactive corrections.
7. **Verify** using a small dataset with known outcomes, then reconcile against real source data.
8. **Optimize physically** after measuring query patterns and refresh frequency.

Never start with "what columns does the fact table need?" while skipping grain. Chosen columns must align with a single unified unit of observation.

## 8. Measure Calculation Example: Three Lines Across Two Orders

Suppose on Jul 01, 2026 at one store, three completed sales lines occur, all in **VND**, tax-exclusive, and before any returns:

| Line | Order | Product | Category | Qty | Unit Price | Gross | Discount | Net | COGS |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| L1 | O100 | P01 | Food | 2 | 100,000 | 200,000 | 20,000 | 180,000 | 120,000 |
| L2 | O100 | P02 | Home Goods | 1 | 80,000 | 80,000 | 0 | 80,000 | 50,000 |
| L3 | O101 | P01 | Food | 1 | 100,000 | 100,000 | 10,000 | 90,000 | 60,000 |
| **Total** | **2 orders** | | | **4** | | **380,000** | **30,000** | **350,000** | **230,000** |

~~~text
gross_amount = quantity × unit_price
net_amount = gross_amount - discount_amount
gross_profit = net_amount - cogs_amount

Total units sold     = 4
Total gross          = 380,000
Total discount       = 30,000
Total net            = 350,000
Total COGS           = 230,000
Gross profit         = 120,000
Distinct orders      = 2
AOV                  = 350,000 / 2 = 175,000
Net per unit         = 350,000 / 4 = 87,500
Gross margin rate    = 120,000 / 350,000 ≈ 34.29%
~~~

### 8.1. Breakdown by Category

| Category | Units Sold | Net Sales | COGS | Gross Profit |
|---|---:|---:|---:|---:|
| Food | 3 | 270,000 | 180,000 | 90,000 |
| Home Goods | 1 | 80,000 | 50,000 | 30,000 |
| **Total** | **4** | **350,000** | **230,000** | **120,000** |

The Food category has 2 orders, Home Goods has 1 order. **Adding per-category order counts to get 3 is wrong** when you want total system orders; there are actually only 2 orders because `O100` spans both categories.

### 8.2. "Average" Depends on the Denominator

- Average net per line: `350,000 / 3 ≈ 116,666.67 VND/line`.
- AOV: `350,000 / 2 = 175,000 VND/order`.
- Average net selling price per unit: `350,000 / 4 = 87,500 VND/unit`.

All three metrics are valid for their respective denominators, yet answer different questions. Never take `AVG(net_amount)` on a line-level fact to report AOV.

## 9. PostgreSQL Schema: Building the Dimensions

This example constructs a minimal model with **SCD Type 2 on `dim_product`**; store and customer dimensions remain unversioned to keep the illustration focused. If historical store region or customer segment at sale date is needed, add SCD handling to those dimensions as well.

### 9.1. Date Dimension

~~~sql
CREATE TABLE dim_date (
    date_key         integer PRIMARY KEY, -- e.g. 20260701
    calendar_date    date NOT NULL UNIQUE,
    calendar_year    integer NOT NULL,
    calendar_month   integer NOT NULL CHECK (calendar_month BETWEEN 1 AND 12),
    calendar_quarter integer NOT NULL CHECK (calendar_quarter BETWEEN 1 AND 4)
);
~~~

You need a date dimension generator and consistency checks across `date_key`, `calendar_date`, and `calendar_month`. Fiscal periods or holidays can be added as dimension attributes per organizational rules.

### 9.2. Product Dimension with Effective Intervals

~~~sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE dim_product (
    product_key   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id    text NOT NULL,
    product_name  text NOT NULL,
    category_name text NOT NULL,
    valid_from    date NOT NULL,
    valid_to      date,

    CONSTRAINT ck_product_period
        CHECK (valid_to IS NULL OR valid_from < valid_to),

    CONSTRAINT ex_product_version_no_overlap
        EXCLUDE USING gist (
            product_id WITH =,
            daterange(valid_from, valid_to, '[)') WITH &&
        )
);
~~~

One `product_id` can have multiple `product_key` rows as its category or tracked attributes change. The exclusion constraint forbids two versions of the same `product_id` from having overlapping effective dates. It **does not guarantee gapless coverage**; if continuous coverage is required, add explicit checks.

This model assumes each product has **one primary category** on any given date. If multiple concurrent categories are valid in the business, use a many-to-many or bridge table rather than forcing an invalid `UNIQUE`.

### 9.3. Store and Customer Dimensions

~~~sql
CREATE TABLE dim_store (
    store_key   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    store_id    text NOT NULL UNIQUE,
    store_name  text NOT NULL,
    region_code text NOT NULL
);

CREATE TABLE dim_customer (
    customer_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id  text NOT NULL UNIQUE,
    segment_code text NOT NULL
);
~~~

In this example, segment and region hold current values. If the organization needs revenue analysis by **segment at the time of sale**, apply SCD2 to `dim_customer` or freeze the attribute in the fact. Never silently present current segments as historical segmentation.

## 10. Sales-Line Fact and Grain Constraints

~~~sql
CREATE TABLE fact_sales_line (
    sales_line_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_line_id text NOT NULL UNIQUE,
    order_number   text NOT NULL, -- degenerate dimension
    sale_date_key  integer NOT NULL REFERENCES dim_date(date_key),
    product_key    bigint NOT NULL REFERENCES dim_product(product_key),
    store_key      bigint NOT NULL REFERENCES dim_store(store_key),
    customer_key   bigint REFERENCES dim_customer(customer_key),
    currency_code  char(3) NOT NULL,

    quantity       integer NOT NULL CHECK (quantity > 0),
    unit_price     numeric(18, 2) NOT NULL CHECK (unit_price >= 0),
    discount_amount numeric(18, 2) NOT NULL
                    CHECK (
                        discount_amount >= 0
                        AND discount_amount <= quantity * unit_price
                    ),
    cogs_amount    numeric(18, 2) NOT NULL CHECK (cogs_amount >= 0),

    gross_amount   numeric(18, 2)
                   GENERATED ALWAYS AS (quantity * unit_price) STORED,
    net_amount     numeric(18, 2)
                   GENERATED ALWAYS AS
                       (quantity * unit_price - discount_amount) STORED
);

CREATE INDEX ix_sales_date_product
    ON fact_sales_line (sale_date_key, product_key);
~~~

Explanation:

- **`source_line_id` UNIQUE** prevents duplicate loading of a sales line; confirm the source ID is truly unique within system/tenant scope.
- **`order_number`** supports `COUNT DISTINCT` orders and drill-through, not summation.
- **`product_key`** references the **SCD2 version selected** on the sale date.
- **Nullable `customer_key`** represents unidentified customers; reports must handle Unknown/Anonymous grouping explicitly instead of silently dropping rows.
- **`currency_code`** is mandatory before summing amounts across multiple markets.
- Gross/net in this DDL use simplified line formulas. Real systems may require currency-specific rounding, taxes, tiered discounts, and must not recompute finalized historical amounts when formulas change.

**This fact only holds recognized sales lines.** Draft or cancelled orders must not automatically count as revenue; returns require dedicated recognition rules, such as a returns fact keyed by return date or adjustment entries.

### 10.1. Selecting `product_key` for the Business Date

~~~sql
SELECT product_key, category_name
FROM dim_product
WHERE product_id = 'P01'
  AND valid_from <= DATE '2026-07-01'
  AND (
      valid_to IS NULL
      OR DATE '2026-07-01' < valid_to
  );
~~~

With non-overlapping SCD2 intervals, this query returns at most one row. If no row matches, ETL needs a policy for **quarantine**, a governed Unknown dimension member, or late-arriving data handling. Never default to the highest `product_key` or current version.

## 11. Correct SQL Aggregations and Derived Calculations

### 11.1. Revenue, Units, and Margin by Month and Category

~~~sql
SELECT
    d.calendar_year,
    d.calendar_month,
    p.category_name,
    SUM(f.quantity) AS units_sold,
    SUM(f.gross_amount) AS gross_sales,
    SUM(f.discount_amount) AS discounts,
    SUM(f.net_amount) AS net_sales,
    SUM(f.cogs_amount) AS cogs,
    SUM(f.net_amount - f.cogs_amount) AS gross_profit,
    ROUND(
        100 * SUM(f.net_amount - f.cogs_amount)
        / NULLIF(SUM(f.net_amount), 0), 2
    ) AS gross_margin_pct
FROM fact_sales_line f
JOIN dim_date d ON d.date_key = f.sale_date_key
JOIN dim_product p ON p.product_key = f.product_key
WHERE d.calendar_year = 2026
  AND d.calendar_month = 7
  AND f.currency_code = 'VND'
GROUP BY d.calendar_year, d.calendar_month, p.category_name
ORDER BY p.category_name;
~~~

`gross_margin_pct` must be calculated as **total profit divided by total revenue**, never `AVG` of per-row margins. Clarify that profit here strictly means **gross profit = net sales - COGS**, excluding marketing, operating expenses, or taxes.

### 11.2. AOV from Distinct Orders

~~~sql
SELECT
    d.calendar_year,
    d.calendar_month,
    SUM(f.net_amount) AS net_sales,
    COUNT(DISTINCT f.order_number) AS order_count,
    SUM(f.net_amount)
        / NULLIF(COUNT(DISTINCT f.order_number), 0) AS aov
FROM fact_sales_line f
JOIN dim_date d ON d.date_key = f.sale_date_key
WHERE d.calendar_year = 2026
  AND d.calendar_month = 7
  AND f.currency_code = 'VND'
GROUP BY d.calendar_year, d.calendar_month;
~~~

This formula assumes all lines of an order share the same recognition period and currency under reporting rules. If an order has lines recognized across multiple dates, redefine the `order_count` denominator or use an order-grain `fact_order` table.

### 11.3. Quantity-Weighted Average Price

~~~sql
SELECT
    SUM(net_amount)
        / NULLIF(SUM(quantity), 0) AS avg_net_unit_price
FROM fact_sales_line
WHERE currency_code = 'VND';
~~~

This is the unit-weighted average price. `AVG(unit_price)` matches only in special cases, never as a general rule.

## 12. SCD and "As-Was" vs. "As-Is" Analysis

Suppose `P01` belonged to **Food** prior to Aug 01, 2026 and moved to **Gifts** starting Aug 01:

~~~text
P01, product_key 1001: [01/01, 08/01)  → Food
P01, product_key 1002: [08/01, +∞)     → Gifts
~~~

**As-was:** view July revenue by the category active when the transaction occurred. `L1` and `L3` remain under Food.

**As-is:** view all historical revenue under today's category. Those same `L1` and `L3` lines may be reclassified under Gifts.

Both perspectives can be useful, provided **report names and policies are explicit**. Storing historical `product_key` on a fact does not force every query to be as-was; conversely, never switch to as-is silently without notifying consumers.

### 12.1. Types of Slowly Changing Dimensions

| Type | Mechanism | When to Use |
|---|---|---|
| **Type 0** | Retain original value | Attributes that must remain immutable |
| **Type 1** | Overwrite value | Typo fixes; old values need no history |
| **Type 2** | Create new row with effective interval | Analyze by state valid at transaction date |
| **Type 3** | Store current value and a few prior values | Limited historical comparison needs |
| **Bridge/temporal relation** | Many-to-many relation, optionally time-bounded | Multi-category products, multi-segment customers |

SCD Type 2 by valid time **is not automatically bitemporal**. If the warehouse retroactively edits past effective dates and overwrites prior knowledge, it can no longer answer "at time K, which group did the warehouse believe this product belonged to?". When that matters, you need system/known time or published report snapshots/revisions.

### 12.2. Late-Arriving Dimensions and Facts

A transaction occurring on Jul 28 that reaches the analytical warehouse on Aug 02 must be placed on its **business date** per the metric contract, not arbitrarily pushed into August because of ingestion timestamp. Similarly, a category change effective Aug 01 entered on Aug 03 requires remapping fact dimension keys from Aug 01 onward if needed.

Options: hold facts waiting for dimensions, link to a governed Unknown row and backfill carefully, or reprocess affected partitions/periods. Always reconcile so no transactions are dropped or double-counted.

## 13. Many-to-Many Relationships and the Fanout Trap

One sales line may be influenced by multiple campaigns. Suppose line `L1` has net revenue **100,000 VND** and links to Campaign A and Campaign B.

~~~text
fact_sales_line:
L1 → net_amount = 100,000

bridge:
L1 → Campaign A
L1 → Campaign B
~~~

Joining directly and running `SUM(net_amount)` produces **200,000**. That is **fanout**.

### 13.1. Two Definitions to Distinguish

**Influenced/touched revenue:** each campaign receives credit for "touching" 100,000 in revenue. Here A = 100,000 and B = 100,000, but you **must not sum** the two groups to claim total revenue.

**Attributed revenue:** allocate revenue by weights, e.g., A 60%, B 40%:

~~~text
A: 100,000 × 0.60 = 60,000
B: 100,000 × 0.40 = 40,000
Total allocated = 100,000
~~~

Weights must derive from an approved attribution policy, not arbitrary numbers picked by engineering.

### 13.2. Bridge Table and Allocation Query

~~~sql
CREATE TABLE dim_campaign (
    campaign_key bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    campaign_code text NOT NULL UNIQUE,
    campaign_name text NOT NULL
);

CREATE TABLE bridge_sales_line_campaign (
    sales_line_key bigint NOT NULL
                   REFERENCES fact_sales_line(sales_line_key),
    campaign_key   bigint NOT NULL
                   REFERENCES dim_campaign(campaign_key),
    attribution_weight numeric(8, 6) NOT NULL
                        CHECK (
                            attribution_weight >= 0
                            AND attribution_weight <= 1
                        ),
    PRIMARY KEY (sales_line_key, campaign_key)
);

SELECT
    c.campaign_name,
    SUM(f.net_amount * b.attribution_weight) AS attributed_net_sales
FROM fact_sales_line f
JOIN bridge_sales_line_campaign b
  ON b.sales_line_key = f.sales_line_key
JOIN dim_campaign c
  ON c.campaign_key = b.campaign_key
WHERE f.currency_code = 'VND'
GROUP BY c.campaign_name;
~~~

If policy requires **100% of revenue to be allocated**, weights for each sales line must sum to 1 (potentially including an Unattributed campaign). A row-level `CHECK` **cannot enforce the sum across multiple rows**; use transaction validation or ETL checks grouped by `sales_line_key`.

If campaigns have effective dates, verify the bridge links fall within valid dates for the sales line. Never join July measures to a September campaign mapping unintentionally.

## 14. Multiple Facts with Different Grains: Aggregate Before Combining

Suppose you need a daily/SKU report showing:

- Units sold from **`fact_sales_line`** (many rows/day/SKU).
- Closing stock from **`fact_inventory_daily`** (one row/day/SKU/warehouse).

Directly joining the sales fact to the inventory fact on date and SKU repeats an inventory row for every matching sales line, multiplying closing stock.

Instead, **aggregate each fact to the same reporting level first**, then join the two aggregated sets:

~~~sql
WITH sales_by_day_product AS (
    SELECT
        sale_date_key AS date_key,
        product_key,
        SUM(quantity) AS units_sold
    FROM fact_sales_line
    GROUP BY sale_date_key, product_key
),
inventory_by_day_product AS (
    SELECT
        snapshot_date_key AS date_key,
        product_key,
        SUM(closing_qty) AS closing_qty
    FROM fact_inventory_daily
    GROUP BY snapshot_date_key, product_key
)
SELECT
    COALESCE(s.date_key, i.date_key) AS date_key,
    COALESCE(s.product_key, i.product_key) AS product_key,
    s.units_sold,
    i.closing_qty
FROM sales_by_day_product s
FULL JOIN inventory_by_day_product i
  ON i.date_key = s.date_key
 AND i.product_key = s.product_key;
~~~

**Note:** `fact_inventory_daily` here is an illustrative table that must be created separately; it is not part of the DDL in sections 9–10. Assume each warehouse has one valid `closing_qty` per day/SKU in consistent units; select the accepted revision if snapshots are republished.

When reporting by category, both facts must share a consistent classification or explicitly explain why sales are computed **as-was** while inventory uses current category. This is the role of **conformed dimensions**.

### 14.1. Never Build Ratios from Incompatible Denominators

Conversion rate may require successful purchase sessions / eligible visit sessions. Those two sources have distinct grains and keys; define sessions, attribution, timeout windows, and whether one session can generate multiple orders. Never use order-line counts as the denominator for conversion since each order can span multiple lines.

## 15. Fact Types and Their Corresponding Measures

### 15.1. Transaction Fact

Each row is a recognized transaction or event line: sales line, return, payment. Quantities and monetary amounts are typically additive across many dimensions. Define which statuses qualify, retry/dedup handling, and revenue recognition timing.

### 15.2. Periodic Snapshot Fact

Each row is state at a period cutoff, e.g., SKU–warehouse–day:

~~~text
(date_key, warehouse_key, product_key) → closing_qty
~~~

If multiple revisions exist for the same day, select the **accepted version**; never sum revisions as independent states.

Inventory is semi-additive: sum across SKUs and warehouses on one day when appropriate, **never SUM across days** to compute month-end inventory.

### 15.3. Accumulating Snapshot Fact

Each row is a workflow instance with evolving milestones:

~~~text
order_id
created_date_key
paid_date_key
shipped_date_key
delivered_date_key
fulfillment_days
~~~

Rows are updated as the process advances. If you need to reconstruct past workflow states, maintain a separate version/event history; an accumulating snapshot holding only final milestones is insufficient.

### 15.4. Factless Fact

Tables recording only an event or relationship, with no monetary columns:

~~~text
fact_attendance:
(date_key, student_key, class_key) → one attendance check-in
~~~

`COUNT(*)` or `COUNT DISTINCT` derives measures from row existence. Still distinguish logging class attendance from holding an active enrollment across many days; their grains and semantics differ.

## 16. Metric Contracts and the Semantic Layer

To prevent two dashboards from calculating different numbers under the same metric name, standardize definitions in a **metric catalog/semantic layer**.

| Attribute | Example: `net_sales` |
|---|---|
| Metric name | `net_sales_amount` |
| Definition | Total sales revenue after line discounts |
| Grain | Completed sales line |
| Formula | `SUM(quantity × unit_price − discount_amount)` |
| Business date | `sale_date_key` |
| Unit | VND in this view |
| Tax | Excluded |
| Returns | Not subtracted directly here; separate net-after-returns metric exists |
| Dimensions | Date, Product SCD2, Store, Customer |
| Unknown handling | Rules for anonymous customers and missing product mappings |
| Data SLA | Load latency and late-fact handling |
| Reconciliation | Total against sales ledger for matching period and scope |

For margin percentage, the metric contract should state explicitly:

~~~text
gross_margin_pct =
   100 × SUM(net_amount - cogs_amount)
         / NULLIF(SUM(net_amount), 0)
~~~

Never define `AVG(line_margin_pct)` when the goal is group-wide profit margin.

### 16.1. A Different Definition Version Is a Different Metric

If net sales previously excluded returns and the organization now wants a post-returns metric, do not silently edit the formula and overwrite all published reports. Establish definition versioning, effective dates, approvers, backfill/revision rules, and unambiguous display names.

A semantic layer is **a contract between engineering and business**, not just a storage folder for SQL snippets.

## 17. Testing Correctness and Detecting Row Multiplication

| Check | Expectation |
|---|---|
| One `source_line_id` maps to one fact row | `UNIQUE` constraint and source reconciliation |
| Fact has `product_key` matching sale date | SCD2 mapping within effective interval |
| One `product_id` has no overlapping SCD2 versions | Exclusion constraint or DQ test |
| Fact–dimension JOIN does not multiply fact rows | Dimension side unique on join key |
| Line discount does not exceed line gross per contract | `CHECK` constraint or test |
| Net, gross, and COGS share currency and units | Data contract and currency code check |
| `COUNT DISTINCT` orders never summed across categories | Recomputed at overall level |
| Campaign bridge weights sum properly | Transaction validation/reconciliation |
| Snapshot fact selects one revision per period | Unique business grain + revision policy |
| Late-arriving data lands on business date | Compare event time vs. load time |
| Ratios aggregate from proper numerators/denominators | Compare roll-ups against recomputation from fact |

### 17.1. SQL Duplicate Check

~~~sql
SELECT source_line_id, COUNT(*) AS number_of_rows
FROM fact_sales_line
GROUP BY source_line_id
HAVING COUNT(*) > 1;
~~~

With `UNIQUE` enabled in DDL, this returns zero rows; it is far more useful on staging tables before constraints are applied.

### 17.2. Demonstrating Fanout from a Bridge Table

~~~sql
WITH source_total AS (
    SELECT SUM(net_amount) AS net
    FROM fact_sales_line
),
naive_join_total AS (
    SELECT SUM(f.net_amount) AS net
    FROM fact_sales_line f
    JOIN bridge_sales_line_campaign b
      ON b.sales_line_key = f.sales_line_key
)
SELECT
    s.net AS original_net,
    j.net AS incorrectly_joined_net
FROM source_total s CROSS JOIN naive_join_total j;
~~~

This is **not a dashboard revenue query**. It illustrates how a JOIN inflates totals when one line touches multiple campaigns, or deflates totals if an `INNER JOIN` drops lines with no campaign.

### 17.3. Sample Dataset Test Matrix

| Metric | Expected Value |
|---|---:|
| Fact row count | 3 |
| Distinct orders | 2 |
| Total quantity | 4 |
| Gross | 380,000 VND |
| Discount | 30,000 VND |
| Net | 350,000 VND |
| COGS | 230,000 VND |
| Gross profit | 120,000 VND |
| AOV | 175,000 VND/order |
| Net per unit | 87,500 VND |
| Margin rate | Approx. 34.29% |
| Food Net | 270,000 VND |
| Home Goods Net | 80,000 VND |

## 18. Performance, Physical Governance, and Technology Choice

In OLTP, tables are normalized for accurate transactions and frequent updates. In OLAP, facts/dimensions serve large read scans, dimensional filtering, and aggregations. You can keep the OLTP model as the **transactional source**, then ETL/ELT into a star schema for BI.

### 18.1. Indexes, Partitions, and Aggregate Tables

Large facts are commonly filtered by date and dimension keys. Measure with `EXPLAIN (ANALYZE, BUFFERS)` — inspecting scan speeds, selectivity, write overhead, and planner statistics — before adding many indexes. Time partitioning aids pruning and retention when queries consistently filter by date; avoid applying it blindly when workloads filter primarily by customer or when it breaks global uniqueness enforcement.

**Aggregate tables** by month–category–store can accelerate dashboards. However, if you store `order_count` per category, **never SUM those distinct counts** to obtain system-wide orders when orders span categories. Build separate summary levels with explicit semantics or recompute from sufficient detail grain.

### 18.2. Columnar Warehouses

Columnar warehouses accelerate scanning a subset of measure and dimension columns across massive facts. Still, a fast engine cannot fix grain errors, many-to-many JOIN fanout, mismatched currencies, or wrong effective dates.

### 18.3. Document, Graph, and Analytics

- **Document:** can store an order with an embedded items array; to calculate revenue by category, unnest items to line grain and avoid multiplying order-level charges.
- **Graph:** suits path analysis, communities, and multi-hop relationships; when a node belongs to multiple groups, define whether to count with overlap or allocate.
- **Relational/star:** suits additive metrics sliced by dimensions with clear keys and relationships.
- **Analytical/lakehouse:** combines event, CDC, transactional, and snapshot sources; the more sources combined, the greater the need for conformed dimensions, a metric catalog, and reconciliation.

The criterion for choosing a model is **its ability to preserve required semantics, constraints, and queries**, not merely technology names.

## 19. Practical Exercise: Sales, Inventory, and Campaign Dashboard

A retail chain requests a dashboard:

> By day, region, category, and campaign, display net revenue, units sold, closing daily stock, distinct orders, AOV, gross margin rate, and campaign-attributed revenue. Products can change categories; an order can be touched by multiple campaigns.

Complete the following:

1. **Declare the grain** of the sales fact and inventory fact, explaining why measures of different grains cannot be merged arbitrarily onto one row.
2. **Design dimensions** Date, Product, Store, Customer, and Campaign; identify which dimensions are conformed across facts.
3. **Classify measures:** `quantity`/`net`/`cogs`, `closing_qty`, AOV, gross margin, distinct orders.
4. **Choose keys:** `source_line_id`, SCD2 `product_key`, `store_key`, and surrogate keys per dimension version.
5. **Handle many-to-many campaigns:** compare influenced revenue vs. attributed revenue; propose a bridge table with weights summing to 1 if allocation is required.
6. **Write temporal mapping** so a Jul 01 transaction attaches to the category valid on that day.
7. **Write queries** for revenue by category; compute margin via summed numerator over summed denominator.
8. **Compute AOV** across orders `O100`/`O101` totaling 350,000 net, yielding 175,000 VND; explain why `COUNT(*) = 3` is wrong.
9. **Select period-end stock** from the SKU–warehouse–day fact without summing stock across days.
10. **Drill-across** both facts at day–product grain after aggregating each fact independently.
11. **Test retroactive corrections** when Product `P01` changes category effective Aug 01 but the update reaches the warehouse on Aug 03. Distinguish as-was, as-is, and published revisions.
12. **Test** duplicate source lines, orphan dimensions, SCD2 overlaps, bridge fanout, and multi-category orders.

**Success criteria:** every metric has a formula, unit, and filter; every fact has an explicit grain; no JOIN alters measures unintentionally; derived metrics use proper denominators; and monetary totals reconcile against source data.

## 20. Checklist for Designing Measures, Dimensions, and Relationships

- **Business question:** What must the report answer, for which period, and at what detail level?
- **Grain:** What exactly does one fact row represent?
- **Measures:** Are formulas, units, valid statuses, returns, taxes, and currencies explicit?
- **Additivity:** Do additive, semi-additive, non-additive, and distinct-count measures have proper roll-up rules?
- **Dimensions:** Are business keys, surrogate keys, attributes, and hierarchies defined?
- **Relationships:** Do fact–dimension JOINs preserve grain; do many-to-many relationships use bridges, weights, or separate metrics?
- **Time:** Which business date drives `date_key`; are role-playing dimensions and SCDs handled properly?
- **History:** Are as-was/as-is, late-arriving facts, Type 1/2, and retroactive corrections agreed upon?
- **Multiple facts:** Are sales, returns, inventory, and sessions aggregated independently before combining?
- **Reconciliation:** Have duplicates, orphans, overlaps, monetary totals, order counts, and access permissions been verified?
- **Semantic layer:** Do all teams share the same metric definitions and change versions?
- **Performance:** Have indexes, partitions, aggregates, and warehouse structures been measured against real workloads?

**Conclusion:** Measures answer **"how much?"**, dimensions answer **"from which perspective?"**, grain answers **"what does each row represent?"**, and relationships determine **"which dimension version and how many links attach to those measures?"**. Only when all four align do `SUM`, `COUNT DISTINCT`, and `GROUP BY` produce numbers that are both fast and explainable, verifiable, and auditable.
