# Scope Boundary: Analytical Data Modeling vs. Full ETL Pipeline Implementation

## Learning Objectives and Scope

A revenue report can display exact column names, run fast, and still **return wrong numbers** if each row lacks clear meaning, an order is counted multiple times, or "revenue" means different things across teams. Therefore, before building a data pipeline, the team must define the **analytical data model**: which events the data represents, across which dimensions it aggregates, how metrics compute, and which constraints must be protected.

Conversely, even with a stellar fact–dimension schema, data does not populate the analytical warehouse on its own. Reading sources, syncing changes, handling errors, scheduling runs, backfilling history, and monitoring operations belong to the scope of the **ETL/ELT data pipeline**.

This lesson belongs to the **Analytical Modeling** chapter of the **DATABASE_DATA_MODELING** module. The module trains you to turn business requirements into clear data models—from entities, relationships, and constraints to normalization, keys, indexes, and physical schemas—while comparing relational, document, graph, and analytical modeling to choose evolvable, verifiable structures. This lesson clarifies the **deliverables of analytical data modeling**, without expanding into a guide for building a complete ETL platform.

After this lesson, learners will be able to:

1. Distinguish **"What structure and meaning does target data hold?"** from **"Through which operational steps does data travel from source to target?"**.
2. Define the **grain**, **facts**, **dimensions**, **measures**, business/surrogate keys, and temporal rules of an analytical model.
3. Author **data contracts** and business-level transformation rules to hand off to ETL/ELT implementation teams without confusing them with pipeline code.
4. Clearly divide decisions around **SCDs, late-arriving data, refunds, history updates, freshness, and quality** between modeling and implementation.
5. Read and evaluate star schemas and illustrative reporting SQL without having to deploy ingestion, schedulers, or monitoring infrastructure.
6. Define acceptance criteria for **modeling** deliverables and hand off **pipeline operations** to a separate implementation phase.

> **Intentional boundary:** This lesson uses PostgreSQL and illustrative SQL to clarify target schemas, JOINs, and metric assumptions. It **does not** build ingestion connectors, batch/streaming jobs, orchestration DAGs, retry/backfill logic, or deployment configurations. Those are vital, yet belong to a separate implementation scope.

## 1. Two Different Yet Tightly Coupled Questions

### 1.1. Analytical Data Modeling Answers "What Is Stored and How Is It Interpreted?"

An **analytical data model** is the set of decisions governing the structure and semantics of analytical data, for example:

- Does one row in **`fact_sales_line`** represent **one order line recognized as sold** or one order status transition?
- Does **net revenue** equal gross revenue minus discounts? Have returns been subtracted yet?
- Can quantities and monetary amounts be summed across dates, products, and customer segments?
- Are customers grouped by **segment at purchase time** or **current** segment?
- Can a customer have multiple versions in a dimension? Which version attaches to a historical transaction?
- Which key guarantees a transaction line appears at most once in the fact table?
- Which assumptions does the data store enforce via PK, FK, `UNIQUE`, `CHECK`, or data quality assertions?

These decisions establish a **semantic contract** for report authors, analysts, applications, and ETL teams.

### 1.2. ETL/ELT Implementation Answers "How Does Data Get There?"

**ETL** stands for *Extract–Transform–Load*: extract, transform, then load data. **ELT** stands for *Extract–Load–Transform*: load raw data into the target environment, then transform inside it. Both describe ways to organize **data processing flows**, not the definition of fact grains or business metrics.

ETL/ELT implementation typically addresses:

- Connecting to operational databases, APIs, files, or event streams.
- Choosing full load, incremental load, CDC, or streaming ingestion.
- Standardizing formats, handling malformed source data, and executing transformations.
- Looking up dimension keys, handling late-arriving data, duplicates, deletes, and updates.
- Scheduling, job dependencies, retries, idempotency, and backfills.
- Managing connection secrets, infrastructure, permissions, compute resources, and cost.
- Monitoring latency, record counts, pipeline failures, alerting, and recovery.

Those steps must **comply with the target model**, yet they are not the target model itself.

### 1.3. Concise Boundary Table

| Question | Analytical Modeling | ETL/ELT Implementation |
| --- | --- | --- |
| What is one fact row? | **Define the grain** | Load data matching the agreed grain |
| What does net revenue mean? | **Formula and business scope** | Compute or ingest values and verify formulas |
| How do customer segment changes behave? | **Choose SCD1, SCD2, or another view** | Detect changes, close/open versions, assign keys |
| What if one transaction arrives twice? | **Uniqueness rule by event key** | Deduplication, upsert, and safe replay mechanics |
| Report must be fresh within 30 minutes? | **Specify target freshness SLA/SLO** | Choose schedule, streaming, alerts, and breach handling |
| Product lacks a matching dimension? | **Define missing-reference status rules** | Quarantine queues, unknown records, backfills, reconciliation |
| Which systems supply source data? | **Identify authoritative sources and conceptual mappings** | Configure connectors, auth, retries, incremental pulls |
| Which columns exist in target tables? | **Logical/target schema, keys, constraints** | Provision, migrate, and populate physical tables |
| Job failed at 02:00? | **Not a modeling structure decision** | Inspect logs, retry, recover, and page on-call |

**These are not two isolated silos.** For instance, grain and versioning rules dictate loading mechanics; conversely, source limitations and update constraints may require adjusting the model. What matters is **stating clearly who decides what, which artifact is verified, and which scope remains unimplemented**.

## 2. Core Concepts for Designing Analytical Data

### 2.1. OLTP Sources Differ from Analytical Serving Models

Operational systems (**OLTP**) prioritize recording transactions accurately and preventing update anomalies. For example, **`orders`**, **`order_lines`**, **`customers`**, and **`products`** enforce foreign keys, state machines, and point-in-time operational rules.

Analytical systems (**OLAP** or analytical warehouses) prioritize questions such as:

- What is total net revenue by **sale date** and **customer segment**?
- Which products generated the highest sales in the quarter?
- What is the return rate by category and origination month?
- Are analytical results reproducible under the exact same **metric definition**?

Never copy an OLTP schema verbatim and call it an analytical model. Source tables answer "what is the operational system currently storing?", while analytical models answer "which events/metrics must users evaluate, and at what grain?".

### 2.2. Grain: Define Before Picking Columns

**Grain** is the exact meaning of **a single row** in a fact table. Example:

> Each row in `fact_sales_line` represents **one order line recognized as a valid sale once the order reaches completed status per business rules**; the row's business key is `order_line_id`.

This grain **differs from**:

- One row per **order**.
- One row per **order-line status change**.
- One row per **shipment batch**.
- One row per **day–product** aggregate.

Mixing different grains inside one fact without explicit rules causes `SUM` and `COUNT` queries to double-count easily.

### 2.3. Facts, Dimensions, and Measures

- A **fact table** stores events, dimension keys, and measurable/aggregatable **measures** (e.g., `quantity`, `gross_amount`, `discount_amount`).
- A **dimension table** supplies context for grouping and filtering (e.g., date, product, customer, region).
- A **measure** is a quantitative metric with a clear definition: quantity, gross sales, discount, net sales.
- A **dimension attribute** like `customer_segment` or `product_name` is a descriptive analytical attribute and should never be summed (`SUM`).

A **star schema** places a fact at the center linked to dimensions. It is a widespread pattern, though not every analytical model must be a star: wide tables, semantic layers, Data Vault, OLAP cubes, or summary tables fit different contexts.

### 2.4. Measure Additivity

| Measure Type | Example | Aggregation Method |
| --- | --- | --- |
| **Additive** | Per-line sales amount, units sold | Safely summed (`SUM`) across dimensions that do not duplicate facts |
| **Semi-additive** | End-of-day balance, end-of-day stock | Additive across certain dimensions, **never summed across multiple dates** like revenue |
| **Non-additive** | Conversion rate, profit margin %, average price | Must recompute from numerators/denominators or proper rules; never `SUM` directly |

Example return rate:

\[
\text{Return rate}
=\frac{\text{Returned quantity}}{\text{Valid sold quantity}}
\]

Specify matching time windows, product scope, units of measure, and zero-denominator handling. **Never** sum or take an unweighted average of per-line percentages to derive a system-wide rate.

## 3. Running Example: Sales Revenue Analytical Model

Assume a company has a transactional ordering system. Reporting needs:

1. Net revenue by date, product, and customer segment.
2. Counts of sales lines, total units, and total value for completed orders.
3. When a customer changes segments, historical reports preserve **the segment at sale time**.
4. Returns and refunds are tracked **separately**; do not fold refund amounts directly into the sales fact in this example.
5. Currency is **VND**; all monetary measures in this fact share the same unit.

These are **illustrative assumptions**. If a business uses multiple currencies, split shipments, taxes, post-completion cancellations, or other revenue recognition rules, clarify them before deploying to production.

### 3.1. Start with Questions and Definitions, Not Tools

| Modeling Decision | Locked-In Assumption for Example |
| --- | --- |
| Event | One order line **recognized as sold** when order reaches valid completed status |
| Grain | One row per business **`order_line_id`** |
| Analysis timestamp | `sold_at` of valid sale event, converted to **date in `Asia/Ho_Chi_Minh`** |
| Quantity | `quantity > 0`, measured in each product's **selling unit** |
| Gross revenue | `gross_amount`, in VND |
| Discount | `discount_amount`, in VND, from `0` to `gross_amount` |
| Net sales revenue | `net_amount = gross_amount - discount_amount`; **excludes returns**, does not infer taxes/fees |
| Customer | Time-versioned dimension preserving **segment at time of sale** |
| Product | Dimension holding product attributes for grouping; category-change policy decided separately |
| Deduplication key | `order_line_id` unique within the fact at declared grain |
| Reporting target | One detailed fact and dimensions supporting `GROUP BY`/`WHERE` |

**Note on "revenue":** In this example `net_amount` is **net order-line sales after discounts**, not automatically accounting revenue recognized under formal standards, nor post-refund revenue. Name measures clearly so distinct concepts are never conflated.

### 3.2. Conceptual Star Schema

~~~~mermaid
erDiagram
    DIM_DATE ||--o{ FACT_SALES_LINE : sale_date
    DIM_CUSTOMER ||--o{ FACT_SALES_LINE : customer_at_sale
    DIM_PRODUCT ||--o{ FACT_SALES_LINE : product

    DIM_DATE {
        integer date_key PK
        date full_date
        smallint calendar_year
        smallint calendar_month
    }
    DIM_CUSTOMER {
        bigint customer_key PK
        varchar customer_id
        varchar customer_segment
        timestamptz effective_from
        timestamptz effective_to
        boolean is_current
    }
    DIM_PRODUCT {
        bigint product_key PK
        varchar product_id
        varchar product_name
    }
    FACT_SALES_LINE {
        bigint sales_line_key PK
        varchar order_line_id UK
        varchar order_id
        integer date_key FK
        bigint customer_key FK
        bigint product_key FK
        timestamptz sold_at
        integer quantity
        decimal gross_amount
        decimal discount_amount
        decimal net_amount
    }
~~~~

**Key explanations:**

- **`sales_line_key`** is the fact row's surrogate key; **`order_line_id`** is the event's unique business key.
- **`customer_key`** points to a **specific version** of the customer in the dimension, not merely the current `customer_id`.
- **`product_key`** and **`date_key`** reference their respective dimensions.
- **`order_id`** lives directly in the fact for lookups or order counts, acting as a **degenerate dimension** when no separate order dimension table is needed for this report.
- FK constraints ensure referenced rows exist, yet **do not automatically enforce that `customer_key` is the version valid at `sold_at`**; that temporal rule requires additional verification.

### 3.3. Why Not One Fact Row per Order?

Suppose order `O100` contains two products. If you store one row per order with `total_amount` and join to a product detail list during reporting, summing revenue by product **repeats the entire order total** for each product.

Instead:

| order_id | order_line_id | product_id | quantity | net_amount |
| --- | --- | --- | ---: | ---: |
| O100 | O100-L1 | P01 | 2 | 90000 |
| O100 | O100-L2 | P02 | 1 | 20000 |

Revenue for order `O100` is **110000**, calculated by summing `net_amount` across both lines. If another fact uses **one row per order** for order-level KPIs, use each fact in its proper context; never join two detail facts directly and blindly sum.

### 3.4. One Dimension Record Can Represent One Version

Customer `C001` upgrades from **Retail** to **Enterprise** at the start of Oct 02, 2026 Vietnam time. When reports require segment at time of sale, overwriting `customer_segment` on a single row retroactively misattributes Oct 01 transactions to Enterprise.

An **SCD Type 2** (*Slowly Changing Dimension*) model stores:

| customer_key | customer_id | customer_segment | effective_from (+07 time) | effective_to (+07 time) |
| ---: | --- | --- | --- | --- |
| 101 | C001 | Retail | 2026-01-01 00:00 | 2026-10-02 00:00 |
| 102 | C001 | Enterprise | 2026-10-02 00:00 | None (current) |
| 103 | C002 | Retail | 2026-01-01 00:00 | None (current) |

`C001`'s Oct 01 transactions reference **`customer_key = 101`**, while Oct 02 transactions reference **`customer_key = 102`**. Selecting SCD2 is a **modeling decision**; detecting upstream changes, creating versions, backfilling, and assigning the right keys are **data pipeline work**.

## 4. Target Schema and Illustrative SQL: Design, Not Yet ETL

The DDL below demonstrates **one possible PostgreSQL target schema implementation**. It clarifies grain, keys, and several invariants; it **does not extract data from sources**, build automated jobs, or guarantee complete data quality via DDL alone.

### 4.1. Creating the Dimensions

~~~~sql
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    calendar_year SMALLINT NOT NULL,
    calendar_month SMALLINT NOT NULL,
    CONSTRAINT ck_date_month CHECK (calendar_month BETWEEN 1 AND 12)
);

CREATE TABLE dim_customer (
    customer_key BIGINT PRIMARY KEY,
    customer_id VARCHAR(40) NOT NULL,
    customer_segment VARCHAR(40) NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL,
    effective_to TIMESTAMPTZ,
    is_current BOOLEAN NOT NULL,
    CONSTRAINT uq_customer_version
        UNIQUE (customer_id, effective_from),
    CONSTRAINT ck_customer_interval
        CHECK (effective_to IS NULL OR effective_to > effective_from),
    CONSTRAINT ck_customer_current
        CHECK (
            (is_current = TRUE AND effective_to IS NULL)
            OR
            (is_current = FALSE AND effective_to IS NOT NULL)
        )
);

-- At most one current version per customer_id.
CREATE UNIQUE INDEX uq_customer_one_current
    ON dim_customer (customer_id)
    WHERE is_current = TRUE;

CREATE TABLE dim_product (
    product_key BIGINT PRIMARY KEY,
    product_id VARCHAR(40) NOT NULL UNIQUE,
    product_name VARCHAR(150) NOT NULL,
    product_category VARCHAR(80) NOT NULL
);
~~~~

**Key modeling decisions:**

- **`dim_customer`** uses surrogate `customer_key` to distinguish **versions of the same `customer_id`**. `(customer_id, effective_from)` must be unique.
- SCD2 effective intervals follow **`[effective_from, effective_to)`**: inclusive start, **exclusive** end; a `NULL` `effective_to` indicates no known end timestamp.
- The filtered `UNIQUE` index blocks **two versions simultaneously marked `is_current = TRUE`** for one `customer_id`.
- These `CHECK` constraints do not prevent **two closed versions from having overlapping intervals**. Non-overlap rules require additional data checks or range constraints.
- **`dim_product`** here holds one row per `product_id`, matching a current-attribute update policy (*Type 1*) for `product_name`/`category`. If reporting needs product category **at time of sale**, change the dimension policy accordingly rather than treating current metadata as history.

In practice, many warehouses auto-generate surrogate keys and include metadata columns like source system, load timestamp, and pipeline version. Here `customer_key`/`product_key` are supplied explicitly so the example is easy to verify; **key generation and source-ID mapping mechanisms** sit outside this lesson's implementation scope.

### 4.2. Creating the Order-Line Fact

~~~~sql
CREATE TABLE fact_sales_line (
    sales_line_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_line_id VARCHAR(40) NOT NULL UNIQUE,
    order_id VARCHAR(40) NOT NULL,
    date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    customer_key BIGINT NOT NULL
        REFERENCES dim_customer(customer_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    sold_at TIMESTAMPTZ NOT NULL,
    quantity INTEGER NOT NULL,
    gross_amount NUMERIC(18, 2) NOT NULL,
    discount_amount NUMERIC(18, 2) NOT NULL,
    net_amount NUMERIC(18, 2)
        GENERATED ALWAYS AS (gross_amount - discount_amount) STORED,
    currency_code CHAR(3) NOT NULL DEFAULT 'VND',
    CONSTRAINT ck_sales_qty CHECK (quantity > 0),
    CONSTRAINT ck_sales_gross CHECK (gross_amount >= 0),
    CONSTRAINT ck_sales_discount
        CHECK (discount_amount >= 0 AND discount_amount <= gross_amount),
    CONSTRAINT ck_sales_currency CHECK (currency_code = 'VND')
);
~~~~

**What this DDL guarantees:**

- `order_line_id` appears **at most once** in the fact, upholding the declared grain.
- Dimension foreign keys reference existing dimension rows.
- Quantity and base measures obey valid domains.
- `net_amount` computes consistently from `gross_amount` and `discount_amount` **within the same row**.
- Monetary amounts are strictly `VND`, preventing accidental cross-currency sums.

**What this DDL does NOT guarantee:**

- That the source line actually satisfied "valid/completed sale" rules.
- That `sold_at` mapped to the right `date_key` in the agreed timezone.
- That `customer_key` is the SCD2 version whose effective interval contains `sold_at`.
- That `order_line_id` from the source truly represents one unique sale event across replays or status edits.
- That source data is complete, without missing transactions, extra rows, or stale updates.

Those guarantees require **semantic contracts and pipeline checks/implementation**, not an assumption that one `CREATE TABLE` solves everything.

### 4.3. Loading Known Test Data

The `INSERT` statements below merely **populate an illustrative test dataset** to validate the model and queries. They are **not an ETL program** extracting from an ordering system.

~~~~sql
INSERT INTO dim_date
    (date_key, full_date, calendar_year, calendar_month)
VALUES
    (20261001, DATE '2026-10-01', 2026, 10),
    (20261002, DATE '2026-10-02', 2026, 10);

INSERT INTO dim_customer
    (customer_key, customer_id, customer_segment,
     effective_from, effective_to, is_current)
VALUES
    (101, 'C001', 'Retail',
     TIMESTAMPTZ '2026-01-01 00:00:00+07',
     TIMESTAMPTZ '2026-10-02 00:00:00+07', FALSE),
    (102, 'C001', 'Enterprise',
     TIMESTAMPTZ '2026-10-02 00:00:00+07',
     NULL, TRUE),
    (103, 'C002', 'Retail',
     TIMESTAMPTZ '2026-01-01 00:00:00+07',
     NULL, TRUE);

INSERT INTO dim_product
    (product_key, product_id, product_name, product_category)
VALUES
    (201, 'P01', 'Notebook', 'Stationery'),
    (202, 'P02', 'Pen', 'Stationery');

INSERT INTO fact_sales_line
    (order_line_id, order_id, date_key, customer_key, product_key,
     sold_at, quantity, gross_amount, discount_amount)
VALUES
    ('O100-L1', 'O100', 20261001, 101, 201,
     TIMESTAMPTZ '2026-10-01 09:00:00+07', 2, 100000, 10000),
    ('O100-L2', 'O100', 20261001, 101, 202,
     TIMESTAMPTZ '2026-10-01 09:00:00+07', 1, 20000, 0),
    ('O101-L1', 'O101', 20261002, 102, 201,
     TIMESTAMPTZ '2026-10-02 10:00:00+07', 1, 50000, 5000),
    ('O102-L1', 'O102', 20261002, 103, 202,
     TIMESTAMPTZ '2026-10-02 12:00:00+07', 3, 60000, 0);
~~~~

The data describes three orders (`O100`, `O101`, `O102`) and four sales lines: `O100` has two lines; `O101` belongs to `C001` after upgrading to Enterprise; `O102` belongs to `C002`.

### 4.4. Reporting Queries Against the Model

**Daily net sales and units sold by customer segment:**

~~~~sql
SELECT
    d.full_date,
    c.customer_segment,
    SUM(f.quantity) AS units_sold,
    SUM(f.net_amount) AS net_sales_vnd
FROM fact_sales_line AS f
JOIN dim_date AS d ON d.date_key = f.date_key
JOIN dim_customer AS c ON c.customer_key = f.customer_key
GROUP BY d.full_date, c.customer_segment
ORDER BY d.full_date, c.customer_segment;
~~~~

Expected results from sample data:

| full_date | customer_segment | units_sold | net_sales_vnd |
| --- | --- | ---: | ---: |
| 2026-10-01 | Retail | 3 | 110000 |
| 2026-10-02 | Enterprise | 1 | 45000 |
| 2026-10-02 | Retail | 3 | 60000 |

**Total net sales:** `110000 + 45000 + 60000 =` **215000 VND**. Total units sold = **7 units** under the assumption that selling units are additive here; if products use incompatible units, define separate metrics or conversions before summing.

**Counting orders and sales lines:**

~~~~sql
SELECT
    COUNT(*) AS sale_lines,
    COUNT(DISTINCT order_id) AS orders,
    SUM(net_amount) AS net_sales_vnd
FROM fact_sales_line;
-- sale_lines = 4, orders = 3, net_sales_vnd = 215000
~~~~

**Computing segment share with the proper formula:**

~~~~sql
WITH revenue_by_segment AS (
    SELECT c.customer_segment, SUM(f.net_amount) AS sales_vnd
    FROM fact_sales_line AS f
    JOIN dim_customer AS c ON c.customer_key = f.customer_key
    GROUP BY c.customer_segment
)
SELECT customer_segment,
       sales_vnd,
       ROUND(
           100 * sales_vnd / NULLIF(SUM(sales_vnd) OVER (), 0),
           2
       ) AS share_percent
FROM revenue_by_segment
ORDER BY customer_segment;
~~~~

Retail holds **170000 VND** (approx. **79.07%**) and Enterprise holds **45000 VND** (approx. **20.93%**). Never sum or average per-row shares; compute from **segment total revenue divided by overall revenue across the same dataset**.

### 4.5. Why Queries Verify the Model Contract Yet Do Not Prove the Pipeline?

These `SELECT` queries validate:

- Whether **grain and measure semantics** match expectations on sample data.
- Whether fact–dimension pairs join cleanly on declared keys.
- Whether historical segmentation rules appear properly at sale time.

They **do not** prove that upstream sources are connected, tomorrow's data will arrive automatically, jobs run on schedule, duplicates are filtered, or pipelines recover cleanly after CDC outages. Proving those belongs to **pipeline implementation and testing** in a separate phase.

## 5. SCDs, Late-Arriving Data, and History Changes: Model Decisions First, Load Algorithms Second

One of the easiest places to blur analytical modeling and ETL is handling **time-varying data**. The model must declare **how history is interpreted**; the pipeline implements the updates to uphold that policy.

### 5.1. SCD Type 1 and Type 2 Answer Different Questions

| Aspect | SCD Type 1 | SCD Type 2 |
| --- | --- | --- |
| Perspective | **Current** or most recently corrected value | Value **effective during each time period** |
| Attribute mutation | Update in place on one row | Insert new version, close prior version |
| Impact on past reports | Past reports change when current value changes | Preserves historical grouping as of event time |
| Dimension keys | Typically one row per business key | Multiple surrogate keys per business key |
| Best suited for | Typo fixes, attributes needing no history | Segments, regions, tiers requiring point-in-time analysis |
| Trade-offs | Simpler, fewer versions | More rows, requires accurate version assignment and interval validation |

**Modeling decision:** `customer_segment` must be accurate **at transaction time**, so this example chooses SCD2. That is a semantic commitment about data meaning.

**ETL implementation decision:** how to detect upstream changes, close prior versions, mint new `customer_key`s, update late arrivals, and prevent race conditions creating duplicate versions. That is data-flow engineering, never implied automatically merely by naming SCD2.

### 5.2. Event Time Differs from Processing Time

Distinguish at least three timestamps:

- **Event time:** when the business event actually happened, e.g., `sold_at`.
- **Processing/ingestion time:** when the analytical system received or processed the message.
- **Dimension effective time:** when a dimension version became valid per business policy.

For example, a sale happens at **21:00 on Oct 01**, yet the source sends it to the warehouse at **03:00 on Oct 02**. When reporting by sale date, that line still belongs to **Oct 01**, not shifted to Oct 02 merely because it loaded late.

If `customer_segment` changed at **00:00 on Oct 02**, the Oct 01 sale must link to the Retail version even when ETL runs after the segment change. Therefore the model needs **`sold_at`** and dimension validity intervals, while the pipeline performs an **as-of lookup** by timestamp.

Logical condition for assigning a version:

\[
customer\_id_{\mathrm{fact}}=customer\_id_{\mathrm{dim}}
\]

and

\[
effective\_from\le sold\_at < effective\_to
\]

or **`effective_to` is null** for the active version.

An analytical query illustrating the version-lookup rule (not the full load algorithm):

~~~~sql
-- Assumes a verified event source supplying customer_id/sold_at.
-- This query only illustrates the temporal join rule.
SELECT d.customer_key
FROM dim_customer AS d
WHERE d.customer_id = 'C001'
  AND d.effective_from <= TIMESTAMPTZ '2026-10-01 09:00:00+07'
  AND (
      d.effective_to > TIMESTAMPTZ '2026-10-01 09:00:00+07'
      OR d.effective_to IS NULL
  );
-- Expected result: 101.
~~~~

If upstream data supplies only dates without sufficiently precise timestamps, define version assignment rules matching available resolution; you cannot infer history finer than source timestamp precision.

### 5.3. Late-Arriving Data

Separate two scenarios:

**Late-arriving fact:** An order sold yesterday arrives today. The model must preserve **sale date**, business key, and customer version at sale time; ETL decides how to backfill and refresh affected reports.

**Late-arriving dimension:** A fact arrives before customer or product metadata has synced. The model must state how missing references are represented:

- **Quarantine / withhold fact publication** until the reference resolves.
- **Unknown member** with a dedicated surrogate key and flags indicating unresolved status.
- An **inferred member** placeholder enriched later when authoritative metadata arrives.

These are **decisions to make upfront**. Using an unknown member keeps totals complete while surfacing an "Unknown" bucket; it is not inherently superior to holding facts. Choice depends on **strict accuracy, freshness, restatement capability, and tolerance for missing attributes**.

The **model** specifies validity rules and the meaning of unknown groups. **Implementation** chooses retry jobs, dead-letter queues, lookups, key backfills, and orchestration tools.

### 5.4. Edits, Cancellations, and Refunds Are Not the Same Operation

Revenue reporting may encounter:

- A sales line **edited** due to pricing error prior to close.
- An order **cancelled** before qualifying as a valid sale.
- A sold order where the customer **partially returns** items later.
- A transaction **refunded** at a different timestamp from item return.

Never spot a "negative number" and toss it into `fact_sales_line` without defining business semantics. One clean design uses:

~~~~text
FACT_SALES_LINE
  grain   = one valid sales line
  measure = quantity and net sales after discount

FACT_RETURN_LINE
  grain   = one recorded return line
  measure = returned quantity, returned amount
  link    = order_line_id or sales_line_key, where available
~~~~

Then the metric:

\[
\text{Revenue after returns}
=\text{Net sales revenue}-\text{Return value per policy}
\]

must specify **return recognition timing**, tax/fee rules, and reporting period. Some reports classify returns by **return date**; others evaluate order quality by **original sale date**. The two views are not equivalent and must be modeled transparently.

**Out of scope here:** writing jobs to process cancellation events, reconcile payments, replay refund streams, or merge payment and order states. Those depend on model requirements as inputs, yet form a separate processing system.

### 5.5. Idempotency: Requirement Belongs to Grain, Execution Belongs to Pipeline

If an upstream source emits two sales events with the same **`order_line_id`**, the fact must hold **at most one row** per the declared grain. `UNIQUE(order_line_id)` states this requirement in the target schema.

However, `UNIQUE` alone does not define everything:

- Is an identical second message ignored?
- Does a second message with modified values **update** the row or become a separate adjustment event?
- When rerunning a day's data, does the job overwrite partitions, merge by key, or reconcile before updating?
- If a source `order_line_id` can be **reused** across tenants or system versions, must the true business key include `tenant_id`/`source_system`?

These are **ingestion protocol and idempotency design** questions. The model defines **unique identity and how edits are interpreted**, while the pipeline safely executes replay and upsert mechanics.

## 6. Where Does Data Flow Appear in the Architecture?

We can outline **ETL/ELT stages** to clarify handoff boundaries without **implementing them**.

~~~~mermaid
flowchart LR
    S["OLTP / API / Event Sources"] --> I["Extract / CDC / ingestion"]
    I --> R["Raw / landing"]
    R --> T["Transform / validate / lookup"]
    T --> W["Load / merge / publish"]
    W --> M["Fact / dimension / semantic model"]
    M --> B["BI / reports / queries"]

    D["Design: grain, measures, dims, keys, SCD, DQ"] -. "Defines data contract" .-> T
    D -. "Specifies target schema" .-> M
    O["Operations: scheduler, retry, backfill, alerts"] -. "Orchestrates & monitors" .-> I
    O -. "Orchestrates & monitors" .-> W
~~~~

This diagram does not require every organization to deploy identical Raw, Staging, and Warehouse tiers. Some ELT systems transform inside the warehouse, some stream continuously, and others use lakehouses. The **conceptual boundary** remains clear: model design defines the rules and target contracts, while pipelines move data from source to target under those rules.

### 6.1. ETL/ELT Stages and Required Inputs from the Model

| ETL/ELT Stage | Implementation Team Decides | Model Must Provide Upfront |
| --- | --- | --- |
| Extract / ingest | Connectors, auth, CDC logs, polling cadence, partitioning | Authoritative sources, required event/attribute inventory |
| Landing / raw | File format, retention, schema evolution, encryption | Source field contracts and lineage requirements |
| Clean / standardize | Parsing, timezone conversion, null/dirty handling | Value domains, time rules, invalid-data policies |
| Transform | Transformation SQL/jobs, batch vs. stream | Grain, measure formulas, business-level source–target map |
| Dimension processing | Change detection, surrogate key generation, SCD2 updates | SCD policy, business keys, effective interval rules |
| Fact loading | Merge/upsert, dedup, backfill, partition management | Event keys, grain, edit/cancel/return handling |
| Quality checks | Test framework, thresholds, pass/fail gating | Invariants to verify, reconciliation benchmarks, tolerances |
| Publish | Publish gating, snapshots, dashboard refresh | Reporting periods, consistency and freshness requirements |
| Orchestration | DAGs, schedulers, dependencies, retries | Contract-level data dependencies, target deadlines |
| Monitoring | Logs, metrics, alerts, runbooks, on-call | Accuracy/completeness/freshness criteria, dataset criticality |

**Never blur these:** Stating "data must refresh within 30 minutes" is a **data product quality requirement**; choosing Airflow, Kafka, cron, or another mechanism to achieve it is an **implementation decision**. No specific tool is inherently part of defining facts and dimensions.

### 6.2. Business-Level Source-to-Target Mapping vs. Transformation Code

A model document should include a **semantic source-to-target mapping**:

| Target Field | Meaning | Expected Logical Source | Business Rules |
| --- | --- | --- | --- |
| `order_line_id` | Sales line identifier | Order line ID from ordering system | Unique at grain, qualified by source/tenant if needed |
| `order_id` | Parent order | Business order ID | Supports drill-down and `COUNT DISTINCT` |
| `sold_at` | Sale recognition timestamp | Valid completion timestamp | Retain timezone-aware timestamp |
| `date_key` | Reporting date | Derived from `sold_at` | Calendar date in `Asia/Ho_Chi_Minh` |
| `customer_key` | Customer version | `customer_id` + `sold_at` | Dimension lookup within effective interval |
| `product_key` | Analytical product | Source `product_id` | Resolve matching product dimension |
| `quantity` | Units sold | Valid order line | Positive; standardized unit of measure |
| `gross_amount` | Pre-discount value | Authoritative line value | VND; non-negative |
| `discount_amount` | Line discount | Promo/sales-line contract | VND; from `0` to `gross_amount` |
| `net_amount` | Net sales after discount | Computed from gross and discount | Never subtract refunds/taxes unless specified |

Source names like **`orders`** and **`order_lines`** are logical placeholders; real projects must verify concrete tables, APIs, events, and access rights. This mapping contains **no** polling loops, watermark logic, cleanup code, or scheduler config—and **needs none** to be a complete, useful modeling artifact.

### 6.3. Intersection Points: Questions to Answer Before Coding

Several decisions warrant joint discussion:

1. **Is the event key truly stable?** If `order_line_id` changes when an order splits, the model needs a more durable business key.
2. **Are sale time and load time separated?** If the source lacks `sold_at`, design must choose a fallback timestamp with documented reliability.
3. **Does the source retain customer segment history?** If not, "segment at sale time" cannot be reconstructed completely for past years.
4. **Can all products convert quantity compatibly?** If not, adjust measures/units before summing.
5. **Are order and payment states consistent?** If revenue depends on payment, the event model must define exactly when transactions qualify.

This is not an excuse to start coding pipelines immediately. It is a **feasibility checkpoint**: a model must never promise historical data the source lacks or measures the business has not defined.

## 7. Data Quality: Defining Checks vs. Building Execution Engines

**Model design** states what **must always hold** for a dataset and what **tolerances are acceptable**. Implementation teams then decide where checks execute, cadence, publish-blocking behavior, alerts, and recovery.

### 7.1. Four Core Check Categories

| Check Category | Modeling Question | Example on Sales Fact |
| --- | --- | --- |
| **Validity** | Do row values satisfy domain and formula rules? | `quantity > 0`, `gross ≥ discount ≥ 0` |
| **Uniqueness** | Do two rows ever represent the same event? | `order_line_id` unique |
| **Referential / temporal integrity** | Do dimension references exist and match valid versions? | `customer_key` exists and is active at `sold_at` |
| **Completeness / reconciliation** | Does target match authoritative source coverage? | Valid sales row counts/totals match source reconciliation |

**Freshness** is an orthogonal criterion: did the latest dataset meet the business deadline? A dataset can be **accurate yet stale**, or **very fresh yet wrong**. Never equate freshness with correctness.

### 7.2. Illustrative SQL Checks After Data Is Loaded

**Detect rows whose date mismatches the business date:**

~~~~sql
SELECT
    f.order_line_id,
    f.sold_at,
    d.full_date
FROM fact_sales_line AS f
JOIN dim_date AS d ON d.date_key = f.date_key
WHERE d.full_date IS DISTINCT FROM
      (f.sold_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE;
~~~~

Expected result on sample data is **0 violating rows**. If the organization defines sale date in a different timezone, update both the contract and the validation query.

**Verify facts reference the customer version valid at sale time:**

~~~~sql
SELECT
    f.order_line_id,
    f.sold_at,
    c.customer_id,
    c.customer_key,
    c.effective_from,
    c.effective_to
FROM fact_sales_line AS f
JOIN dim_customer AS c ON c.customer_key = f.customer_key
WHERE NOT (
    c.effective_from <= f.sold_at
    AND (
        c.effective_to > f.sold_at
        OR c.effective_to IS NULL
    )
);
~~~~

Expected result is **0 violating rows**. This join checks whether the referenced version's effective interval covers `sold_at`; it does not prove the source sent the **right `customer_id`** for the event, since the sample fact stores only `customer_key`.

**Detect overlapping SCD2 intervals for the same customer:**

~~~~sql
SELECT
    a.customer_id,
    a.customer_key AS version_a,
    b.customer_key AS version_b
FROM dim_customer AS a
JOIN dim_customer AS b
    ON a.customer_id = b.customer_id
   AND a.customer_key < b.customer_key
   AND a.effective_from <
       COALESCE(b.effective_to, 'infinity'::TIMESTAMPTZ)
   AND b.effective_from <
       COALESCE(a.effective_to, 'infinity'::TIMESTAMPTZ);
~~~~

Expected result is **0 overlapping pairs**. Because intervals follow `[from,to)`, adjacent versions where one ends as the next begins are **not** flagged as overlapping. Databases may offer stricter range constraints, evaluated per target DBMS.

**Verify detail totals match expected sample benchmarks:**

~~~~sql
SELECT
    COUNT(*) AS line_count,
    COUNT(DISTINCT order_id) AS order_count,
    SUM(quantity) AS total_quantity,
    SUM(net_amount) AS total_net_amount
FROM fact_sales_line;
-- Expected on test data: 4, 3, 7, 215000.
~~~~

Against real sources, **completeness** requires reconciling with selected upstream records across **identical time windows, status filters, currency, and grain**. Running `COUNT(*)` on the target table alone never proves completeness against the source.

### 7.3. Defining Checks Does Not Mean Operating the Check Runner

In a modeling doc, you can write:

> For every published fact row, the date in `dim_date` must equal the date of `sold_at` in `Asia/Ho_Chi_Minh`; every `customer_key` must reference a customer version effective at `sold_at`.

That is a **testable rule**. Downstream implementation decides:

- At which step checks run: pre-load, post-merge, pre-publish, or continuously?
- On failure, halt the whole batch, quarantine failing rows, or publish with warnings?
- Who receives alerts, severity thresholds, and recovery workflows?
- How check results persist for lineage and audit?

A modeling specification need not implement all of that machinery. Yet **never omit writing quality rules** merely because the execution engine belongs to ETL.

### 7.4. DDL Protects Partially, Never Replaces Source Reconciliation

`UNIQUE(order_line_id)` blocks **two rows with the same ID** in the fact. It cannot detect a **dropped source row**, nor detect if a line's revenue is wrong yet still positive.

`FK(customer_key)` guarantees **the dimension version exists**, not that it is the **right version at sale time**. A temporal check catches that defect; blocking it at write time inside the DB requires extra constraints evaluated for cost.

That is why **model definitions + SQL constraints + source reconciliation + pipeline operations** form distinct layers of defense.

## 8. What Should an Analytical Model Handoff Document Contain?

A design doc need not span hundreds of pages. What matters is containing enough **verifiable decisions** so ETL, BI, and data teams share one interpretation.

### 8.1. Recommended Document Structure

| Document Section | What It Must Answer |
| --- | --- |
| **Business questions** | Which reports/KPIs are supported, and who owns definitions? |
| **Scope and non-scope** | Which datasets are modeled, and which source/pipeline pieces are out of scope? |
| **Grain and population** | What is one fact row; which events are included or excluded? |
| **Facts and measures** | Metrics, units, additivity, formulas, and cancellation/refund rules |
| **Dimensions** | Analytical attributes, keys, and value domains |
| **History policy** | SCD1/SCD2, effective timestamps, current vs. historical perspectives |
| **Time semantics** | Event time, business date, timezone, load timestamp |
| **Keys and relationships** | Business keys, surrogate keys, FKs, nullability, cardinality |
| **Data contracts** | Minimum input fields, semantic mappings, missing-data handling |
| **Quality rules** | Invariants, counterexamples, and reconciliation criteria |
| **Freshness requirement** | Allowed lag, measurement points, never confused with implemented SLOs |
| **Example queries** | Sample SQL demonstrating metrics and analytical dimensions |
| **Open decisions** | Unresolved requirements or upstream source gaps |
| **Handoff** | Remaining tasks for ETL, BI, Security, and Operations |

### 8.2. Sample One-Page Decision Sheet for `fact_sales_line`

~~~~text
DATA PRODUCT: Daily Sales Analysis

Dataset:
  fact_sales_line

Grain:
  1 row per order_line_id recognized as a valid sale.

Included:
  Transactions reaching completed status per sales policy.

Excluded:
  Draft orders, orders cancelled prior to sale recognition.
  Returns: modeled in a separate dataset.

Time:
  Event timestamp: sold_at.
  Reporting date: Asia/Ho_Chi_Minh calendar date of sold_at.

Measures:
  quantity > 0, product selling units.
  gross_amount >= 0 VND.
  0 <= discount_amount <= gross_amount.
  net_amount = gross_amount - discount_amount.

Keys:
  UNIQUE(order_line_id) within verified source scope.
  customer_key linked to SCD2 version at sold_at.

Required dimensions:
  dim_date, dim_customer, dim_product.

Freshness target:
  Valid data should appear in reports within 30 minutes of source
  sale confirmation (business target, not yet implemented).

Non-scope of this model specification:
  Connectors, CDC, batch/streaming, scheduler, retries,
  backfill, deployment, monitoring implementation.

Unresolved:
  Post-completion order edit policy; split refunds;
  whether sales-line IDs remain stable across upstream systems.
~~~~

**A good document can contain unresolved questions.** Unverified details must be logged as **open decisions**, rather than silently guessing defaults and letting pipelines lock in unapproved semantics.

### 8.3. Acceptance Criteria Specific to Model Design

A model specification is ready for **design handoff** when:

1. Business stakeholders confirm **questions and KPI definitions**.
2. Every fact has a **concrete grain**, inclusion/exclusion scope, and deduplication key.
3. Every dimension has an identity source, keys, history semantics, and required attributes.
4. Measures specify **units, formulas, time scope, and additivity**.
5. Relationship diagrams and key/relationship tables exist.
6. Change, late-arrival, missing-dimension, and return/cancellation rules are finalized or flagged open.
7. Data contracts, validation rules, and a sample dataset with **expected query answers** exist.
8. Implementation teams can clearly see missing source metadata or feasibility risks.
9. The document states explicitly that **ETL/ELT is not yet implemented**; sample queries are not proof of automated execution.

Never declare **"pipeline complete"** merely because tables, sample rows, and a few `SELECT` queries exist. That is a **verifiable design deliverable**, not an accepted operational system.

## 9. Dividing Responsibilities in Real Projects

These responsibilities may be held by one person or multiple teams; the boundaries below are **functional responsibilities**, not rigid org-chart mandates.

| Role / Function | Core Responsibility | Handoff / Sync Point |
| --- | --- | --- |
| **Business / Product Owner** | KPI definitions, event inclusion criteria, effective timing | Signs off on what "revenue" actually means |
| **Data Modeler / Analytics Engineer** | Grain, facts, dimensions, semantic definitions, history policy, data contracts | Verifiable schemas/definitions, sample SQL queries |
| **Data Engineer** | Ingestion, transforms, lookups, execution, backfills, idempotency, recovery | Pipelines adhering to contract; operational test evidence |
| **BI / Analytics** | Dashboards, metric presentation, drill-downs, user-perspective validation | Queries/charts using proper grain and measures |
| **Data Quality / Governance** | Data ownership, sensitivity classification, quality standards, lineage | Control policies and check results |
| **Platform / SRE / Security** | Permissions, secrets, infrastructure, cost, monitoring, alerting | Operational reliability, security, and recovery |

For example, one analytics engineer might both define fact tables and write ELT transformation SQL. That **does not collapse the two deliverables into one**. Model specs are reviewed for semantic accuracy, while pipeline code is accepted for **executability, source fidelity, safety, and recoverability**.

### 9.1. When ETL Must Escalate Back to the Model

The ETL team discovers the source does not store `customer_segment` history—only the **current** segment. The initial model promised "segment at sale time" for the past three years.

You cannot solve this by **backfilling today's segment across all three years and calling it history**. Options to escalate and decide include:

- Locate another trustworthy historical source if one exists.
- Limit historical segment reporting to the date change logging started.
- Attach a **confidence flag** or "historical unknown" label to earlier periods.
- Revise the requirement to "current segment" if business stakeholders approve.

This is a **semantic contract change** requiring model/business owner approval. Never let a pipeline silently alter a KPI's meaning.

### 9.2. Schema Changes Impact Pipelines, Yet Are Not Pipelines

Adding `product_category_history` or changing a fact's grain requires a new design version, compatibility rules, and a historical data plan. Implementation executes **migrations, reprocessing/backfills, job updates**, and dashboard impact checks.

In short: the model is the **target contract evolving under control**; ETL/ELT is the **mechanism realizing and synchronizing that contract**. One change can touch both sides while keeping responsibilities distinct.

## 10. Scenarios That Easily Creep Out of Scope When Studying Analytical Modeling

During design exercises, many tasks sound like "modeling" while actually crossing into **data-flow implementation**. To draw the line, ask: **is the deliverable a set of rules and data structures, or an automated runtime process?**

### 10.1. "Design a Monthly Revenue Model"

**Within modeling scope:**

- Define "month" by calendar and timezone.
- Lock down source event grain, summation into monthly metrics, and non-additive measures.
- Define date, customer, product dimensions, and grouping attributes.
- Decide whether returns count in the sale month or return month.
- Design the detailed fact and optionally a monthly **aggregate table** if queries warrant it.
- Write verification SQL confirming a month's revenue matches settled lines.

**Outside pure modeling scope:**

- Scheduling end-of-month jobs.
- Configuring incremental refreshes or materialized view refresh jobs.
- Coding reprocessing logic for prior months affected by late returns.
- Integrating dashboards, report permissions, and job failure alerts.

A model can **specify that monthly tables must refresh when late transactions arrive**, without building the DAG to execute it.

### 10.2. "Design SCD Type 2 for Customers"

**Within modeling scope:**

- Specify which attributes require history.
- Customer business key and versioned surrogate keys.
- `[from, to)` effective intervals and open/close boundary rules.
- How facts link to versions by event time.
- Non-overlap and single-current-version invariants.

**Outside pure modeling scope:**

- CDC code detecting segment changes.
- Partitioning strategies, transactional `MERGE` statements, locking, and retries.
- Closing old rows and inserting new rows under concurrent writes.
- Historical backfills and production late-arriving dimension pipelines.

An illustrative SQL version-lookup query does not equal completing a resilient SCD2 implementation.

### 10.3. "Ensure Reports Are Always Complete and Accurate"

**Within modeling scope:**

- Define **complete** relative to which upstream events and time windows.
- Define **accurate** by keys, measures, status filters, and temporal rules.
- Specify desired reconciliation checks and acceptable variance tolerances.
- Distinguish "missing", "not applicable", and "unrecoverable history".

**Outside pure modeling scope:**

- Building scheduled validation runners.
- Configuring lag and discrepancy alerts.
- Investigating logs, rerunning jobs, and remediating bad records.
- Designing SLA operations dashboards and recovery runbooks.

### 10.4. "Integrate Three Data Sources for Customer Analytics"

**Within modeling scope:**

- Define what constitutes **one customer** across sources.
- Unified identity keys and source precedence rankings.
- Conflict resolution rules for attributes like address, segment, and status.
- Conformed customer dimension and authoritative source of truth.
- Acceptable tolerances for lag or missing fields.

**Outside pure modeling scope:**

- Building API ingestion, scheduled syncs, CDC, or file importers.
- Implementing programmatic fuzzy matching or entity resolution.
- Building ID-consolidation pipelines and maintaining mapping tables over time.
- Managing API quotas, connection secrets, and retries.

Consolidation rules can be **specified in the model/data contract**, whereas building the execution engine is a separate engineering deliverable.

## 11. Analytical Model Trade-Offs to State Without Premature Infrastructure

### 11.1. Star Schema vs. Normalized Structures

Normalized relational models protect transactional integrity and minimize redundancy. Analytical models use attribute-rich dimensions and foreign-key facts to streamline aggregation.

| Aspect | Normalized Transactional Model | Analytical Star Model |
| --- | --- | --- |
| Primary optimization | Writing/updating transactions | Filtering, grouping, aggregating metrics |
| Grain | Per business entity or relation | Fact at explicit event/snapshot grain |
| Descriptive attributes | Spread across normalized tables | Typically co-located in dimensions |
| Temporal data | Current state or OLTP audit history | Historical policies serving analytical questions |
| Risks if poorly designed | Update anomalies, orphans, missing keys | Double-counting, wrong metrics, cross-grain JOINs, wrong versions |

Choosing a star schema never permits dropping uniqueness or referential checks. Conversely, keeping raw OLTP tables untouched never guarantees reports obey proper grain.

### 11.2. Detail Grain or Pre-Aggregated?

An order-line fact supports flexible slicing yet grows large. A daily–product–segment aggregate table reduces scan volume for common reports:

~~~~text
AGG_DAILY_PRODUCT_SEGMENT:
  grain    = one row / day / product / customer segment
  measures = total quantity, gross, discount, net
~~~~

When introducing aggregates, specify:

- Grouping dimensions and time periods.
- Which measures can be summed and which must be recomputed.
- Whether the aggregate is **derived from the detail fact** or computed independently.
- Reconciliation checks ensuring the aggregate matches the detail fact.
- Rules for handling late data that alters older daily groups.

The **model** owns the aggregate's grain and semantics. The **pipeline** owns computing, loading, refreshing, correcting, or replacing aggregated rows. Designing an aggregate does not mean coding refresh jobs.

### 11.3. Snapshots vs. Transaction Facts

Not every fact represents "a sales event". Common patterns include:

- **Transaction fact:** one row per event or transaction line.
- **Periodic snapshot fact:** one row per period, e.g., **end-of-day** inventory per warehouse–product.
- **Accumulating snapshot fact:** one row per workflow entity tracking milestone progress, e.g., order fulfillment lifecycle.

Grain governs which measures can be summed across dimensions. For end-of-day inventory, summing Oct 01 stock with Oct 02 stock **never produces a meaningful stock figure**. You can report averages, deltas, or ending balances—provided definitions are explicit.

How nightly snapshot jobs run, store watermarks, and handle missing days remains **pipeline implementation**.

### 11.4. Conformed Dimensions and Multiple Facts

With both `FACT_SALES_LINE` and `FACT_RETURN_LINE`, both facts can share `DIM_DATE`, `DIM_PRODUCT`, and `DIM_CUSTOMER` when dimension definitions align.

Still, clarify:

- **Which date:** `sale_date` or `return_date`? Both can point to `DIM_DATE` in different roles (*role-playing dimension*).
- **Which customer:** buyer at sale time or customer initiating the return?
- **Which product:** current product identity or version at transaction time?
- **Measures:** across which periods can sales and refund amounts offset each other?

Shared dimensions make reports consistent when definitions match. Yet **never join two detail facts directly on `date_key`/`product_key` and `SUM`**, because multiple sales lines and multiple return lines on the same day/product multiply combinations. Aggregate each fact to **the same comparison grain** before joining, or use a properly engineered semantic layer.

### 11.5. Speed Requirements Do Not Dictate the Entire Model Structure

A target like "dashboards must respond in 2 seconds" is insufficient to mandate one flat table or a specific database. First verify:

- Which questions does the report answer, and at what grain?
- How many rows exist, and how often do they mutate?
- Which filter dimensions are most common?
- What freshness lag is acceptable?
- Is detail drill-through required, or only summary groups?

Only after the model is semantically sound does implementation evaluate **partitioning, clustering, indexing, materialized views, caching, query engines, incremental processing**, and real cost. Physical tuning is important, yet never substitutes for business definitions.

## 12. Pre-Handoff Checklist for the ETL Team

This is a checklist for a **design deliverable**, not a pipeline coding tracker:

- [ ] Business questions and KPI approvers are documented.
- [ ] Every fact has a one-sentence grain statement and inclusion/exclusion criteria.
- [ ] Measures specify units, formulas, additivity rules, and effective timing.
- [ ] Dimensions specify business keys, surrogate keys, and attribute-change policies.
- [ ] Fact–dimension relationships and null/unknown members are described.
- [ ] Event timestamps, reporting timezone, and KPI date boundaries are decided.
- [ ] Cancellations, edits, refunds, late arrivals, and duplicate deliveries have explicit rules or are flagged open.
- [ ] Source-to-target contracts define minimum fields and authoritative sources.
- [ ] Validity, uniqueness, referential, and reconciliation checks are specified.
- [ ] Freshness targets/latencies are stated as requirements, not claimed as achieved by pipelines.
- [ ] A small sample dataset and queries with expected results validate the logic.
- [ ] Documentation separates what is **designed** from what **needs implementation**.

If an item is incomplete, document **assumptions, consequences, and the decision owner**. Never mask unclear business definitions behind complex tools or pipelines.

## 13. Practice Exercises with Answers

### Exercise 1 — Classifying Work Scope Properly

A project requires:

1. Defining a fact row representing one completed sales line.
2. Building a CDC connector reading changes from source PostgreSQL.
3. Selecting SCD Type 2 to track customer segment history.
4. Configuring alerts when a load job lags beyond 30 minutes.
5. Writing daily source-to-target total revenue reconciliation rules.
6. Implementing retries with exponential backoff.

**Question:** Which items are modeling or data-contract decisions, and which are ETL implementation?

**Answer:** Items **1, 3, 5** belong to **model design and verification contracts**; items **2, 4, 6** belong to **pipeline implementation/operations**. Note that **executing** the reconciliation in item 5 and acting on failures belongs to ETL/data quality operations. The 30-minute target is a freshness requirement, while **configuring alerts** to monitor it is operational implementation.

### Exercise 2 — Choosing the Right Grain for Product Reporting

Order `O100` has 2 lines: line 1 sells a notebook for 90000 VND after discount; line 2 sells a pen for 20000 VND. Someone proposes a one-row-per-order fact holding 110000 VND and joining product details during reporting.

**Question:** Why is this error-prone? Which grain fits product-level revenue?

**Answer:** Joining one order row to two products and summing order revenue **double-counts 110000**. For product-level revenue, use a **one-row-per-sales-line** fact with unique `order_line_id` and per-line `net_amount` (90000 and 20000). An order-grain fact can still serve order-level metrics, provided two differing grains are never joined and summed blindly.

### Exercise 3 — Distinguishing Two Definitions of "Net Revenue"

Sales defines net sales as `gross_amount - discount_amount`. Finance defines net revenue as revenue after subtracting returns, taxes, and adjustments.

**Question:** Should you use a single `net_amount` column without documenting the formula?

**Answer:** No. **Define and name metrics with explicit scope**: e.g., `net_sales_after_discount` or another agreed name, stating the formula and what is **excluded**. If finance needs adjusted revenue, introduce the required return/tax events and rules rather than silently changing the meaning of an existing column.

### Exercise 4 — SCD Type 2 vs. Type 1

Customer `C001` belongs to Retail on Oct 01 and switches to Enterprise at 00:00 on Oct 02. Reports require segment **at time of purchase**.

**Question:** Choose SCD1 or SCD2? Which segment applies to transactions at 09:00 Oct 01 and 10:00 Oct 02?

**Answer:** Choose **SCD2** or an equivalent historical model; the Oct 01 sale belongs to **Retail**, and Oct 02 belongs to **Enterprise**. Facts must link to the dimension version matching `sold_at`. Updating only current state via SCD1 retroactively misassigns Enterprise to both historical events.

### Exercise 5 — Event Time vs. Load Time

An order sells at 23:50 Oct 01 Vietnam time and arrives at the warehouse at 02:00 Oct 02.

**Question:** If dashboards report by "Vietnam sale date", which day does this order belong to, and who owns what?

**Answer:** It belongs to **Oct 01**, because `date_key` derives from **event time `sold_at`** in `Asia/Ho_Chi_Minh`. **Modeling** defines that rule. **Pipelines** ingest the late record, compute `date_key`, load into the proper partition, and refresh affected reports. Never substitute ingestion date when the metric specifies sale date.

### Exercise 6 — Is `UNIQUE` Enough to Catch Missing Data?

A fact table enforces `UNIQUE(order_line_id)`. The source generates 100 sales lines, yet the pipeline loads only 98 with no duplicate keys.

**Question:** Is `UNIQUE` violated? What check is required?

**Answer:** `UNIQUE` is not violated. `UNIQUE` only blocks **duplicate keys**; it cannot detect **missing rows**. You must reconcile valid source event counts against target counts across **identical time windows, status filters, and source scope**, optionally comparing summed `quantity`/`net_amount` and missing IDs. Defining reconciliation belongs to the model contract; running it automatically belongs to the pipeline.

### Exercise 7 — Designing Unknown Dimension Members

A validated sales line arrives, but the warehouse lacks a dimension record for source product `P999`.

**Question:** Which handling strategies can the model specify? Must the fact always load immediately?

**Answer:** You can **quarantine/hold the row** until dimension data arrives, use a **governed unknown member** with defined semantics, or insert a temporary inferred member enriched later. No single option fits every system. Clarify impacts on **freshness, completeness, and historical restatement** before building load jobs.

### Exercise 8 — Overlapping Customer Versions

`DIM_CUSTOMER` stores two versions for `C001`:

~~~~text
customer_key=101, [2026-01-01, 2026-10-05)
customer_key=102, [2026-10-02, 2026-11-01)
~~~~

**Question:** What is wrong? Do `PK(customer_key)` and `UNIQUE(customer_id, effective_from)` prevent this?

**Answer:** The two intervals **overlap from Oct 02 up to Oct 05**, leaving facts in that window ambiguous. Those PK and `UNIQUE` constraints **do not prevent overlapping effective intervals**. Add a non-overlap rule in the model and enforce appropriate temporal checks/constraints.

### Exercise 9 — Counting Orders from an Order-Line Fact

The sample dataset has four fact rows:

~~~~text
O100-L1 → O100
O100-L2 → O100
O101-L1 → O101
O102-L1 → O102
~~~~

**Question:** What do `COUNT(*)` and `COUNT(DISTINCT order_id)` return? Which measures order count?

**Answer:** **`COUNT(*) = 4`** is the **sales-line** count; **`COUNT(DISTINCT order_id) = 3`** is the **distinct order** count in the fact. Never label `COUNT(*)` as order count when grain is order line.

### Exercise 10 — Computing Segment Revenue and Share Correctly

In the sample data, three Retail lines have net sales 90000, 20000, and 60000 VND; Enterprise has one line of 45000 VND.

**Question:** What are total revenue and Retail's share?

**Answer:** Retail = **170000 VND**, Enterprise = **45000 VND**, total = **215000 VND**. Retail share = \(170000/215000\times100\%\approx79.07\%\). Always sum numerators and denominators first rather than averaging per-line percentages.

### Exercise 11 — Is End-of-Day Stock Additive Over Time?

Warehouse A holds 100 units at the end of Oct 01 and 120 units at the end of Oct 02.

**Question:** Does summing them to report "two-day stock = 220" make business sense?

**Answer:** No, because **end-of-day inventory is semi-additive over time**. Period-end stock is **120**, and two-day average stock is **110** if defined that way; summing to 220 does not represent stock at any point in time. The model specifies aggregation rules, while snapshot jobs belong to pipeline scope.

### Exercise 12 — Is ETL Done Once SQL Exists?

An engineer creates `dim_date`, `dim_customer`, `dim_product`, and `fact_sales_line`, inserts four sample rows, and runs a query returning 215000 VND.

**Question:** Can they announce "ETL pipeline complete"? What evidence is still missing?

**Answer:** No. That only proves **the schema and sample calculations work on test data**. It proves nothing about source connectivity, incremental/CDC ingestion, scheduling, deduplication, SCD2 updates, error handling, reconciliation, backfills, security, or monitoring. Those must be implemented and accepted separately.

### Exercise 13 — Separating Aggregates from Refresh Implementation

A dashboard needs revenue by day–product–segment at massive scale.

**Question:** When proposing an aggregate table, what belongs in the model doc and what hands off to ETL?

**Answer:** The **model** defines aggregate grain, grouping keys, measure formulas, units, late-data behavior, and reconciliation rules against the detail fact. **Implementation** decides incremental refresh logic, schedules, partitioning, historical recomputation, and drift alerts.

### Exercise 14 — Source Without History

Business requests customer segment at time of sale for 2023–2026. The source only keeps current segment and began change logging in 2026.

**Question:** Can you guarantee accurate 2023–2025 history merely by building SCD2 today?

**Answer:** No. SCD2 can only preserve versions **backed by observable data**. Without upstream historical logs, either locate another source, restrict history scope, flag uncertainty, or adjust KPI expectations with business sign-off. **Never fabricate history** by stamping today's segment onto old transactions and labeling it "at sale time".

### Exercise 15 — Joining Two Detail Facts

`FACT_SALES_LINE` has three rows for `P01` in a month, and `FACT_RETURN_LINE` has two return rows for `P01` that month. A report joins both facts directly on `product_key` and month, then sums sales and returns.

**Question:** Why does this risk doubling figures? What is safer?

**Answer:** A many-to-many join between three sales lines and two return lines produces **6 pairs**; each side's measures repeat by the other side's row count. **Aggregate each fact to the same reporting grain** (e.g., month + `product_key`) before joining results, or use a fanout-safe semantic layer. That is a **query semantics and grain** decision, not an ETL network error.

### Exercise 16 — Turning a Vague Request into Concrete Deliverables

Stakeholder request: "Build a sales data warehouse and run it automatically every 15 minutes."

**Question:** Split this into two workstreams and list missing questions before accepting.

**Answer:**

- **Model design:** clarify revenue definition, grain, qualifying sales events, cancellations/returns, currency, timestamps, dimensions, customer history, business keys, data contracts, and sample queries.
- **Pipeline implementation:** survey sources, select ingestion, write transforms/loads, incremental updates, 15-minute schedule, retries/errors, security, monitoring, reconciliation tests, and backfill workflows.
- **Mandatory questions:** from what start/end point is "15 minutes" measured; how much source lag is tolerated; do sources keep history and stable IDs; who owns KPIs; what discrepancy threshold is allowed; who is on-call when jobs fail?

Design deliverables are accepted only once data rules are crystal clear. Pipeline deliverables are accepted only with **real operational evidence** proving accuracy, completeness, freshness, and recoverability.

## 14. Summary: The Model Is the Data Contract; ETL/ELT Is the Execution Mechanism

| Topic | Belongs to Analytical Modeling | Belongs to ETL/ELT Implementation |
| --- | --- | --- |
| **Grain** | Which event/snapshot one fact row represents | Processing sources to emit exact grain rows |
| **Measures** | Meaning, units, formulas, additivity | Computing and checking values during load/refresh |
| **Dimensions** | Attributes, business keys, surrogate keys, history | Minting keys, detecting changes, resolving versions |
| **SCD2** | Effective interval rules and historical reporting semantics | CDC/change detection, version merges, backfills |
| **Time** | Event time, reporting date, timezone | Parsing timestamps, handling late-arriving events |
| **Duplicates** | Business key definitions and uniqueness | Deduplication, idempotent loads, safe replays |
| **Returns/corrections** | Event semantics and KPI formulas | Loading and adjusting events per rules |
| **Quality** | Invariants, checks, reconciliation criteria | Running tests, publish gating, alerting, recovery |
| **Freshness** | Target lag and measurement boundaries | Schedulers/streaming, monitoring, breach handling |
| **Schema** | Fact/dimension structure and constraints | Migrations, deployments, physical tuning |
| **Operations** | Required inputs, dependencies, and limits | Connectors, secrets, retries, backfills, logs, runbooks |

**Final principle:** To design analytical data properly, start from **business questions, grain, facts/dimensions, measures, keys, history, time axes, and verification contracts**. Use SQL schemas, sample data, and check queries to validate the design—yet **never mistake those illustrations for a running ETL system**. ETL/ELT must be built and accepted separately against connectivity, processing, accuracy/completeness, freshness, recovery, and operational criteria. When this boundary is clear, both the model and the pipeline become straightforward to review, evolve, and defend.
