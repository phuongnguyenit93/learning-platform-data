# Starting from Analytical Questions, Business Processes, and Grain

## Learning Objectives

In the **DATABASE_DATA_MODELING** module, data design is not merely translating entities and relationships into tables, keys, and indexes. When building an analytical system, the first question **should not** be "which source tables are available to copy?", but rather "**what decision does the user want to make, which business event produces the numbers, and what does a single row of analytical data represent?**"

This lesson in the **Analytical Modeling** chapter helps you:

- Move from an **analytical question** to KPI definitions, business processes, data to collect, and the limits of the answer.
- Choose the right **grain** of a **fact table** before selecting measures and analytical dimensions.
- Distinguish **transaction fact**, **periodic snapshot**, **accumulating snapshot**, and **factless fact**.
- Define **measures**, **dimensions**, business keys, surrogate keys, and time semantics.
- Avoid errors such as **double-counting, multiplying revenue on JOINs, summing balances incorrectly, or miscomputing averages**.
- Sketch a star schema, KPI SQL queries, data quality tests, and source reconciliation.
- Compare analytical modeling with transactional, document, and graph models to choose a suitable, verifiable, and evolvable structure.

## 1. Three Decisions to Lock Down in the Right Order

A solid analytical design flow:

~~~text
Decision question
    ↓
Business process and measured event
    ↓
Grain: what exactly does one fact row represent?
    ↓
Measures and dimensions aligned with the grain
    ↓
Schema, data sources, keys, and history rules
    ↓
Queries, reconciliation, testing, and physical optimization
~~~

Do not invert this into:

~~~text
We have tables orders, customers, products
    ↓
JOIN them all
    ↓
Name the result "data mart"
    ↓
Hope every KPI calculates correctly
~~~

The second approach easily conflates **an order** with **an order line**, **a payment**, **a shipment**, or **a refund**. Those entities all relate to the same order, yet they do not share the same grain.

> Core principle: **Declare the grain in one clear sentence before choosing columns for a fact table.**

## 2. Start with Business Questions, Not Table Names

Suppose a retailer wants to evaluate business performance. Initial requests:

1. What are order sales by month and product category?
2. How many orders are placed each day?
3. What is each carrier's on-time delivery rate?
4. What is net revenue after returns?
5. What is the conversion rate from visits to purchases?

These five questions **do not belong to a single fact table** and may not share the same data sources.

| Question | Business Process | Counted/Measured Object | Definitions Needed |
|---|---|---|---|
| Value of ordered goods by month, category | Ordering | Order line at the time the order is confirmed | Price before/after discount? Tax, shipping fee, currency? |
| Orders per day | Ordering | A confirmed order | Include orders cancelled later? Created date or confirmed date? |
| On-time delivery rate | Fulfillment | Delivery order, parcel, or trip? | One order can have multiple parcels; promised milestone vs. completion time? |
| Net value after returns | Sales and returns | Separate sales and return transactions | Based on sale date or return date? Partial returns? |
| Conversion rate | Browsing and purchasing | Session, user, or pageview? | Attribution window, bots, multi-device, and customer identity? |

For example, a **confirmed order line** table can answer the first question. It **cannot** accurately compute conversion rate without visit or session data as the **denominator**.

### Define the KPI Before Implementation

A KPI needs at least:

| KPI Attribute | Question to Answer |
|---|---|
| Name and purpose | Which decision does this metric support? |
| Numerator and denominator | What is counted; is division required? |
| Event scope | Which events are included, and which are excluded? |
| Date/time | Use occurred, recorded, paid, or delivered timestamp? |
| Grain | What does one row of underlying data represent? |
| Dimensions | By product, customer, region, channel, or date? |
| Currency/unit | Can values be summed directly, or is conversion needed? |
| History | Group by current category or category at purchase time? |
| Data latency | Does the report update in real time, hourly, or daily? |
| Revision rules | How are late events, cancellations, returns, and adjustments handled? |

For instance, "revenue" can mean **booked order value**, **paid amount**, **accounting recognized revenue**, or **post-return value**. They are not automatically equal. In the examples below, we use the precise term **booked merchandise amount** (after line discounts) to avoid falsely claiming it is accounting revenue.

## 3. Identify the Business Process and the Event That Actually Generates the Data

An order may pass through these stages:

~~~mermaid
flowchart LR
    A["Create cart"] --> B["Confirm order"]
    B --> C["Payment"]
    C --> D["Pack / ship"]
    D --> E["Delivered"]
    E --> F["Possible return"]
~~~

Each step can have its own timestamp, key, grain, and measures:

| Process | Example Event | Potential Fact Needed |
|---|---|---|
| Ordering | Confirming a multi-line order | `fact_order_lines`, `fact_orders` depending on the question |
| Payment | A capture/refund attempt | `fact_payment_transactions` |
| Fulfillment | A parcel dispatched/delivered | `fact_shipments` or fulfillment process snapshot |
| Returns | A line item partially returned | `fact_return_lines` |
| Inventory | End-of-day stock for a warehouse–product | `fact_inventory_daily` |
| Web browsing | A page view or visit session | `fact_pageviews` or `fact_sessions` |

A **business process** does not necessarily correspond one-to-one with a single source table. For example, an order confirmation event might originate from a transaction writing to `orders` and `order_items`, emit via an event stream, and be enriched with customer/product attributes. Conversely, one source `orders` table might store confirmed, paid, packed, and delivered timestamps; yet measurements at each step still carry distinct semantics.

### One Process, Multiple Timestamps

Do not call every timestamp `date`. For example:

- `created_at`: order initialized, possibly not yet confirmed.
- `confirmed_at`: order placed/confirmed.
- `paid_at`: payment confirmed.
- `shipped_at`: goods begin transit.
- `delivered_at`: delivery completed.
- `ingested_at`: when the analytical system received the record, **not necessarily when the business event occurred**.

A question asking for "monthly booked merchandise value" must specify the month of `confirmed_at` or another defined milestone. Using the month of `ingested_at` can shift late-arriving transactions into the wrong period.

## 4. Grain Is the Contract of a Fact Table

**Grain** answers: **"Exactly what single object, event, or time slice does one row of this table represent?"**

Examples:

~~~text
fact_order_lines:
    One row corresponds to one (order_id, line_no)
    at the time the order is first confirmed.

fact_payments:
    One row corresponds to one actual monetary transaction
    with a unique payment_transaction_id.

fact_inventory_daily:
    One row corresponds to one (snapshot_date, warehouse_id, product_id)
    at the daily inventory cutoff time.
~~~

This is not just prose: grain determines the **unique key**, the permitted row multiplicity, measure semantics, JOIN patterns, and test assertions.

### Why Must Time Be Included in the Grain Statement?

"One row per order" is insufficient if records are updated multiple times:

- **Current state table:** one row per order, values overwritten over time.
- **Status transition event table:** one row per status change.
- **Daily snapshot table:** one row per order **per day**.
- **Accumulating snapshot table:** one row per order with multiple milestone timestamps updated as the workflow progresses.

All four may contain `order_id`, yet their **grain and analytical meaning differ**.

### One Fact Table Should Have Only One Grain

Do not place **order-level** measures onto every row of an **order-line** fact table and casually run `SUM`. For example, `order_shipping_fee = 40,000` for a three-line order: copying 40,000 onto all three rows makes `SUM(order_shipping_fee)` equal 120,000 — triple the true value.

Better options:

1. Keep shipping fees in an **order-level fact**.
2. If the business requires allocating fees to lines, define an explicit **allocation rule** (by value share, weight, quantity, etc.), name it `allocated_shipping_fee`, and verify the allocated sum equals the order fee.
3. Aggregate two facts to a **compatible grain** before joining, rather than directly JOINing detail rows of different grains.

## 5. Step-by-Step Example: Booked Merchandise Value by Category and Month

Consider the requirement:

> "For confirmed orders, show total **merchandise value after line discounts** by order confirmation month and product category **at the time of ordering**. Exclude shipping fees, taxes, payments, and refunds. Report cutoffs follow the designated business timezone."

Business assumptions:

- `order_id` is unique within the system scope considered.
- `line_no` is unique **within an order**.
- At order confirmation, each line has one product, quantity, unit price, and line discount.
- An order line is recorded **once at confirmation**; if later modified/cancelled/refunded, adjustments flow through appropriate processes/facts rather than silently overwriting historical events.
- Monetary amounts in the example use **a single currency**, with an agreed rounding rule.

### 5.1. From Question to Grain

Appropriate grain:

~~~text
One row of fact_order_lines =
    one order line (order_id, line_no)
    in a confirmed order,
    recorded using information at confirmation time.
~~~

The **fact row business key** is `(order_id, line_no)` under these assumptions.

### 5.2. Selecting Dimensions

| Dimension | Meaning | Questions Supported |
|---|---|---|
| Order confirmation date | Business date derived from `confirmed_at` | By month/quarter/day |
| Product | Product identifier and attributes | By product/category |
| Customer | Customer linked to the order at confirmation | By segment/region |
| Store/channel (if applicable) | Sales source/business unit | By channel, store |
| `order_id` | Transaction identifier for drill-through | Distinct order counts, auditing |

`order_id` is often kept directly inside the fact as a **degenerate dimension**: it is valuable for filtering, grouping, and lookup without necessarily requiring a separate dimension table holding only that key.

**History note:** to report by product category **at the time of ordering**, you must store the dimension version valid at event time (such as SCD Type 2) or a controlled attribute snapshot. A `dim_product` holding only the **current** category will reclassify historical reports whenever a product changes categories.

### 5.3. Selecting Measures

Example:

~~~text
quantity
unit_price_at_order
line_discount_amount
booked_amount = quantity × unit_price_at_order
                - line_discount_amount
~~~

`booked_amount` is the booked merchandise value after line discounts — **not automatically cash collected or recognized revenue**. If an order is cancelled after confirmation, the initial booking fact row still exists by definition, while **net revenue** reports need cancellation/refund rules and additional facts.

### 5.4. Illustrative Data

| order_id | line_no | confirmed_day | category_at_order | quantity | unit_price | line_discount | booked_amount |
|---|---:|---|---|---:|---:|---:|---:|
| D01 | 1 | 2026-11-01 | Books | 2 | 100,000 | 0 | 200,000 |
| D01 | 2 | 2026-11-01 | Accessories | 1 | 50,000 | 10,000 | 40,000 |
| D02 | 1 | 2026-11-02 | Books | 1 | 150,000 | 0 | 150,000 |

With these three rows:

- **Total booked merchandise value:** \(200,000+40,000+150,000=390,000\).
- **Order line count:** 3.
- **Confirmed order count:** 2, not 3.
- **Booked merchandise value in Books:** \(200,000+150,000=350,000\).
- **Units ordered:** \(2+1+1=4\), assuming `quantity` units are uniform and summation is meaningful.

This illustrates the difference between **counting rows**, **counting orders**, and **summing monetary values** at the same grain.

## 6. Types of Fact Tables and How to Choose Right

### 6.1. Transaction Fact — One Row per Transaction/Event

Example:

~~~text
fact_payment_transactions(
    payment_transaction_id,
    order_id,
    transaction_time,
    transaction_type,
    amount
)
~~~

**Grain:** one capture, refund, or adjustment transaction with its own ID. One order can have **multiple** payment transactions, so `order_id` must not be treated as a unique key.

Suitable when asking "how many transactions occurred, how much money moved, and when?". If the same transaction is resent by the source, ingestion must be **idempotent** by transaction identifier.

### 6.2. Periodic Snapshot — One Row per Entity per Period

Example:

~~~text
fact_inventory_daily(
    snapshot_date_key,
    warehouse_key,
    product_key,
    on_hand_quantity
)
~~~

**Grain:** one `(cutoff date, warehouse, product)` at the agreed cutoff timestamp.

Suitable for end-of-day stock, month-end account balances, or active customers in a period. Data may have **periods with zero transactions** yet still require a snapshot row to represent state.

**Do not sum stock across days** if the goal is point-in-time inventory. Having 10 units at the end of Monday and 10 units at the end of Tuesday **does not mean** you have 20 units in stock.

### 6.3. Accumulating Snapshot — One Row Representing a Multi-Milestone Process

Example:

~~~text
fact_order_fulfillment(
    order_id,
    confirmed_date_key,
    packed_date_key,
    shipped_date_key,
    delivered_date_key,
    promised_delivery_date_key
)
~~~

**Grain:** one **fulfillment workflow instance** spanning milestones — e.g., an order if business rules guarantee one shipment flow per order, or a **parcel** if an order can split into multiple parcels.

A row **is updated** as the process advances; ideal for measuring cycle times between milestones. Picking the wrong tracked object is a common error: if an order ships in three parcels on three different days, `order_id` is **no longer** sufficient as the grain for "one delivery".

### 6.4. Factless Fact — Recording an Event/Relationship Without Numeric Measures

Example:

~~~text
fact_event_attendance(
    event_id,
    participant_id,
    attendance_date_key
)
~~~

**Grain:** one valid attendance event of a participant at an activity under confirmed identity rules. Attendance counts can use `COUNT(*)`; no monetary or quantity column is required.

Factless facts can also record **coverage** (permitted combinations) to compare against actual events; clearly distinguish "eligible to attend" from "actually attended".

### Quick Comparison Table

| Fact Type | What Is One Row? | Changes Over Time | Example Measures |
|---|---|---|---|
| Transaction | One event/transaction detail | Usually appends new events | `amount`, `quantity` |
| Periodic snapshot | One entity at a cutoff period | Appends snapshot for new period | `on_hand_quantity`, `balance` |
| Accumulating snapshot | One process instance across milestones | Updates the same row as milestones occur | `days_to_ship`, `days_to_deliver` |
| Factless | One event/relationship without numeric measures | Usually appended or status-updated per definition | Event counts via `COUNT(*)` |

**Selection rule:** pick the structure by **time semantics and grain**, not because a source table happens to be named "transaction" or "snapshot".

## 7. Measures: Additivity Depends on Grain

Not every numeric column can be summed. In analytical modeling, distinguish:

| Measure | Additivity Type | Handling |
|---|---|---|
| `booked_amount` on order line | **Additive** across compatible dimensions under same currency and no row multiplication | `SUM(booked_amount)` |
| `quantity` | Usually additive when units of measure are compatible | `SUM(quantity)`, avoid adding kg with pieces |
| End-of-day `on_hand_quantity` | **Semi-additive**: additive across warehouses/products at one point in time, not across days | Filter to the target snapshot date, then `SUM` |
| `account_balance` | Semi-additive across certain dimensions, not across time | Period-end point or defined progression |
| `unit_price` | **Non-additive** | Compute in context, never `SUM(unit_price)` |
| `discount_rate` | Non-additive | Do not arbitrarily sum or average ratios |
| `distinct_customers` | Cannot sum directly across overlapping sets | `COUNT(DISTINCT customer_id)` over the target scope |
| `conversion_rate` | Non-additive ratio | Divide summed compatible numerators by summed compatible denominators |

### Correct Average Example

Two order lines:

~~~text
Line 1: quantity = 1, unit_price = 100
Line 2: quantity = 9, unit_price = 10
~~~

The **unweighted** average unit price is \((100+10)/2=55\), whereas the **quantity-weighted** average unit price is:

\[
\frac{1\times100+9\times10}{1+9}=\frac{190}{10}=19.
\]

These two numbers answer two different questions. With `line_discount_amount`, realized average price per unit can be defined yet another way; specify it before building the KPI.

### A Conversion Rate Example

If channel A yields 10 orders from 100 sessions and channel B yields 5 orders from 10 sessions, their respective conversion rates are 10% and 50%. The overall conversion rate is **not** the simple average 30%, but:

\[
\frac{10+5}{100+10}\approx13.64\%.
\]

This example holds only when "orders" and "sessions" share the same attribution scope; if one session generates multiple orders or uses a multi-day attribution window, adjust the numerator definition and attribution rules. **You cannot compute a valid rate merely by dividing two semantically incompatible tables.**

## 8. Designing a Star Schema from the Chosen Grain

A **star schema** typically places the fact in the center, linked directly to descriptive dimensions providing context:

~~~mermaid
flowchart LR
    D["dim_date"] --> F["fact_order_lines"]
    C["dim_customer"] --> F
    P["dim_product"] --> F
    F --> O["order_id, line_no\n(booked_amount, quantity, discount)"]
~~~

The **fact** holds dimension keys and the measures of **one event at the declared grain**. **Dimensions** hold attributes used for filtering, grouping, and display, such as product category, customer segment, and geography.

### Surrogate Keys and Business Keys

- `product_id` is the stable **business key** in the source within the confirmed scope.
- `product_key` is the **surrogate key** of the dimension record inside the analytical warehouse.
- When **SCD Type 2 history** is needed, one `product_id` can have multiple dimension versions, each with a distinct `product_key`.
- `(order_id,line_no)` can still serve as the **fact row business key**, even when dimensions use surrogate keys.

Never use surrogate keys to mask **invalid duplicate business keys**. Test uniqueness at the declared grain.

### Simple PostgreSQL DDL Example

The SQL below uses **Type 1 dimensions** (holding current state) to demonstrate the basic structure. If reporting requires categories **at the time of ordering**, you must apply the history techniques in the next section; do not misread current `category_name` as historical category.

~~~sql
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,       -- Example: 20261101
    calendar_date DATE NOT NULL UNIQUE,
    calendar_year INTEGER NOT NULL,
    calendar_month INTEGER NOT NULL CHECK (calendar_month BETWEEN 1 AND 12)
);

CREATE TABLE dim_customer (
    customer_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id VARCHAR(40) NOT NULL UNIQUE,
    customer_segment VARCHAR(80)
);

CREATE TABLE dim_product (
    product_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id VARCHAR(40) NOT NULL UNIQUE,
    product_name VARCHAR(200) NOT NULL,
    category_name VARCHAR(120) NOT NULL
);

CREATE TABLE fact_order_lines (
    order_id VARCHAR(40) NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    confirmed_date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    customer_key BIGINT NOT NULL REFERENCES dim_customer(customer_key),
    product_key BIGINT NOT NULL REFERENCES dim_product(product_key),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_order NUMERIC(18,2) NOT NULL
        CHECK (unit_price_at_order >= 0),
    line_discount_amount NUMERIC(18,2) NOT NULL
        CHECK (line_discount_amount >= 0),
    booked_amount NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    CHECK (line_discount_amount <= quantity * unit_price_at_order),
    CHECK (booked_amount =
           quantity * unit_price_at_order - line_discount_amount)
);

CREATE INDEX idx_fact_order_lines_date_product
    ON fact_order_lines (confirmed_date_key, product_key);
~~~

This is an **illustrative model** and does not solve every requirement out of the box:

- `NUMERIC` and the formula assume appropriate rounding rules; taxes, shipping fees, cancellations, and refunds are excluded from this `booked_amount`.
- A single currency is assumed. With multiple currencies, you need `currency_code` and a conversion strategy with confirmed exchange rates/timestamps.
- `customer_id` and `product_id` are assumed globally unique within the dimension scope; if sources are multi-tenant, keys must include tenant scope or globally normalized identifiers.
- `fact_order_lines` stores records **at order confirmation**; if the source only keeps mutable current state, you must build an event/pipeline mechanism that preserves history.
- Production indexes should reflect actual queries, selectivity, and execution plans; do not blindly index every foreign key without measuring.

### Querying Total Booked Value by Month and Category

~~~sql
SELECT
    DATE_TRUNC('month', d.calendar_date)::date AS order_month,
    p.category_name,
    SUM(f.booked_amount) AS booked_amount,
    SUM(f.quantity) AS units_ordered,
    COUNT(*) AS order_lines,
    COUNT(DISTINCT f.order_id) AS orders_with_this_category
FROM fact_order_lines AS f
JOIN dim_date AS d
  ON d.date_key = f.confirmed_date_key
JOIN dim_product AS p
  ON p.product_key = f.product_key
GROUP BY
    DATE_TRUNC('month', d.calendar_date)::date,
    p.category_name
ORDER BY order_month, p.category_name;
~~~

`orders_with_this_category` counts **orders containing at least one line in that category**. An order spanning two categories is counted in **both groups**. Therefore, **do not sum per-category order counts** to derive total system-wide orders when groups can overlap.

Similarly, with a Type 1 `dim_product`, the category returned is the **current category**. Retaining history at order time requires point-in-time dimension versioning.

## 9. Dimension History: Answer "As Of Then" or "As Of Today"?

Suppose product `SP01` used to belong to "Accessories", then moved to "Electronics".

Both reports can be valid:

1. **By current category:** all past transactions of `SP01` are grouped under "Electronics".
2. **By category at order time:** older transactions prior to the move remain under "Accessories".

If the requirement is the second option, a Type 1 dimension lacks the information once the category is overwritten.

### SCD Type 2 for Historical Attributes

Example versions:

| product_key | product_id | category_name | valid_from | valid_to |
|---:|---|---|---|---|
| 101 | SP01 | Accessories | 2025-01-01 | 2026-07-01 |
| 205 | SP01 | Electronics | 2026-07-01 | infinity |

The effective interval convention is **half-open**:

\[
[\text{valid\_from},\text{valid\_to})
\]

meaning inclusive start, exclusive end. There must never be two versions of the same `product_id` with **overlapping** effective intervals within a linear history.

When loading a fact row with `confirmed_at = 2026-06-15`, look up `product_key = 101`; for `confirmed_at = 2026-08-10`, use `product_key = 205`.

**Crucial point:** `product_key` in the fact must resolve to the **version valid at the business event time**. A JOIN solely on `product_id` against the entire SCD2 table will multiply one fact row across multiple rows.

Example version lookup from staging:

~~~sql
SELECT
    s.order_id,
    s.line_no,
    v.product_key
FROM staging_confirmed_order_lines AS s
JOIN dim_product_version AS v
  ON v.product_id = s.product_id
 AND s.confirmed_at >= v.valid_from
 AND (v.valid_to IS NULL OR s.confirmed_at < v.valid_to);
~~~

This query **only illustrates the lookup principle**; `dim_product_version` must be defined, enforced for single matching versions, and able to handle late-arriving transactions. If an event matches zero versions or multiple versions, that is a data quality defect to resolve before aggregation — never a reason to accept multiplied revenue.

### Event Time vs. Load Time

An order confirmed on Oct 31 but ingested by the pipeline on Nov 02 must be attributed to **confirmation date** when reporting as of order time, not silently shifted to November. Design watermarks, late-arriving data windows, and rerun mechanisms for published figures where appropriate.

If historical category metadata itself is retroactively corrected, the problem may require tracking both **business valid time** and **system transaction time**. Do not equate "Type 2 history" with a complete solution for every temporal anomaly.

## 10. Bus Matrix: Sharing Dimensions Across Processes

Once processes and grains are known, build a **bus matrix** to identify shared dimensions (**conformed dimensions**).

| Process / Fact | Date | Customer | Product | Store | Carrier | Payment Method |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Confirmed order line | ✓ | ✓ | ✓ | ✓ |  |  |
| Payment transaction | ✓ | ✓ |  | ✓ |  | ✓ |
| Delivered parcel | ✓ | ✓ | Possible via order line | ✓ | ✓ |  |
| Return order line | ✓ | ✓ | ✓ | ✓ | Possible |  |
| End-of-day inventory | ✓ |  | ✓ | ✓ / warehouse |  |  |
| Session event | ✓ | Possibly anonymous | Possibly by view | Channel |  |  |

Marking "Possible" does not mean you can directly JOIN a dimension that the pipeline never captured. For example, an order-wide payment transaction does not inherently attach to **a single product**; an explicit allocation rule is required before analyzing payments by product category.

**Conformed dimensions** demand consistent keys, attributes, and scope across facts. If `store_id` means selling store in one process but dispatch warehouse in another, do not merge those two roles just because the column names match.

### Role-Playing Dimensions

A single `dim_date` can serve multiple roles:

~~~text
confirmed_date_key  → dim_date
paid_date_key       → dim_date
shipped_date_key    → dim_date
delivered_date_key  → dim_date
~~~

When querying, use distinct table aliases for each role. Each date carries its **own business meaning**. Never collapse them into a single generic `date_key` when questions distinguish multiple milestones.

## 11. Avoiding Row-Multiplication JOIN Errors (*Fanout*)

Suppose the order-line fact contains one row:

~~~text
order_id = D01, line_no = 1, customer_id = KH01, booked_amount = 200000
~~~

In a customer address table, `KH01` has three addresses. If joined directly:

~~~sql
SELECT SUM(f.booked_amount)
FROM fact_order_lines AS f
JOIN dim_customer AS c
  ON c.customer_key = f.customer_key
JOIN customer_addresses AS a
  ON a.customer_id = c.customer_id;
~~~

Here `customer_addresses` is an additional illustrative table holding multiple addresses per customer. The sales row gets **multiplied by three**, corrupting the sum. Moreover, an `INNER JOIN` can **drop** rows for customers who have no recorded address.

The bug is not solved by `SUM(DISTINCT booked_amount)`: two genuinely different order lines can easily have identical monetary amounts, so `DISTINCT` on the measure will **wrongly eliminate valid values**.

### Correct Handling

Before JOINing, confirm the dimension side is **unique at the join grain**. For instance:

- For a Type 1 customer dimension, `customer_key` must identify **exactly one row**.
- For default address, verify **at most one default address per customer and timestamp**, then select the appropriate version before joining.
- For true many-to-many relationships, use a **bridge table**, an allocation rule, or aggregate each side to a compatible grain.
- For two facts at different grains, usually **aggregate independently** by shared dimensions and then combine the aggregated results at a defined grain.

**Never use `DISTINCT` as a universal bandage for fanout bugs.** It masks modeling defects instead of fixing them.

### Example of Two Processes That Cannot Be Joined Directly

`fact_order_lines`: 3 rows for order D01.

`fact_payment_transactions`: 2 payments for order D01.

Joining both tables on `order_id` produces \(3\times2=6\) rows. `SUM(fact_order_lines.booked_amount)` repeats twice; `SUM(payment_amount)` repeats three times.

A sound approach to compare **booked total vs. paid total by order**:

~~~sql
WITH booked_by_order AS (
    SELECT order_id, SUM(booked_amount) AS booked_amount
    FROM fact_order_lines
    GROUP BY order_id
),
paid_by_order AS (
    SELECT order_id, SUM(payment_amount) AS payment_amount
    FROM fact_payment_transactions
    WHERE transaction_type = 'CAPTURE'
    GROUP BY order_id
)
SELECT
    b.order_id,
    b.booked_amount,
    p.payment_amount
FROM booked_by_order AS b
LEFT JOIN paid_by_order AS p
  ON p.order_id = b.order_id;
~~~

In this example, `payment_amount` and `transaction_type` are **assumed columns of the payment fact**, not part of the `fact_order_lines` DDL above. Payment rules may also involve refunds/reversals, multiple currencies, or uncaptured authorizations; never assume "booked = paid".

## 12. Designing Data Tests Directly from the Grain

A trustworthy fact table needs **verifiable invariants**.

### 12.1. One Business Key Equals One Row at the Declared Grain

~~~sql
SELECT order_id, line_no, COUNT(*) AS row_count
FROM fact_order_lines
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

With DDL enforcing `PRIMARY KEY(order_id,line_no)`, this query normally returns zero rows when the constraint is active; it is especially valuable when validating **staging before load** or in engines that do not enforce keys.

If future requirements allow a line to be revised across multiple versions, do not simply drop `UNIQUE`: redefine the grain, such as **one row per version** with `revision_no`, or keep the original fact immutable and record separate adjustment events.

### 12.2. Validating Amounts Against Business Formulas

~~~sql
SELECT
    order_id, line_no,
    quantity, unit_price_at_order,
    line_discount_amount, booked_amount
FROM fact_order_lines
WHERE booked_amount <>
      quantity * unit_price_at_order - line_discount_amount;
~~~

This example uses the stated formula for **a single currency and simple rounding**. Systems with multiple currencies, tiered promotions, taxes, or allocated fees must substitute the approved KPI formula.

### 12.3. Validating Dimension References

~~~sql
SELECT f.order_id, f.line_no, f.product_key
FROM fact_order_lines AS f
LEFT JOIN dim_product AS p
  ON p.product_key = f.product_key
WHERE p.product_key IS NULL;
~~~

With enforced foreign keys, this case normally does not occur. In data warehouses where FKs are unenforced, or when dimensions load slower than facts, this test is vital. Never **silently drop unmatched fact rows** during KPI calculation: doing so understates sales without warning.

### 12.4. Source-to-Fact Reconciliation

Suppose the transactional source provides `staging_confirmed_order_lines` at the same grain containing confirmed lines. First **normalize keys, filter statuses, and deduplicate reload duplicates**. Only then compare:

~~~sql
WITH source_totals AS (
    SELECT
        CAST(confirmed_at AS DATE) AS confirmed_day,
        COUNT(*) AS source_lines,
        SUM(quantity * unit_price_at_order - line_discount_amount)
            AS source_booked
    FROM staging_confirmed_order_lines
    GROUP BY CAST(confirmed_at AS DATE)
),
fact_totals AS (
    SELECT
        d.calendar_date AS confirmed_day,
        COUNT(*) AS fact_lines,
        SUM(f.booked_amount) AS fact_booked
    FROM fact_order_lines AS f
    JOIN dim_date AS d
      ON d.date_key = f.confirmed_date_key
    GROUP BY d.calendar_date
)
SELECT
    COALESCE(s.confirmed_day, f.confirmed_day) AS confirmed_day,
    s.source_lines,
    f.fact_lines,
    s.source_booked,
    f.fact_booked
FROM source_totals AS s
FULL OUTER JOIN fact_totals AS f
  ON f.confirmed_day = s.confirmed_day
WHERE s.source_lines IS DISTINCT FROM f.fact_lines
   OR s.source_booked IS DISTINCT FROM f.fact_booked;
~~~

**Limitation of this example:** `CAST(confirmed_at AS DATE)` depends on the DB session timezone. Normalize both source dates and `dim_date` to **the same business timezone** before real reconciliation. Also align ingestion lag, cutoff timestamps, late-arriving data, currency, cancellation filters, and rounding rules. Until those conditions match, a discrepancy is not necessarily a fact bug.

### 12.5. Validating Historical Dimension Quality

For SCD Type 2 dimensions, check at minimum:

- No business key has **two overlapping effective intervals** within the same scope.
- Every event resolves to **exactly one dimension version** at its event timestamp.
- Events with no matching version have an explicit strategy: quarantine, tracked unknown member, or backfill.
- Business keys are not reused outside their defined scope.

An "unknown dimension" member prevents losing fact rows when dimensions arrive late, but you must **never treat unclassified data as accurate** or skip subsequent backfills.

## 13. Turning Requirements into Reviewable Design Docs

A concise template per fact:

| Component | Example for `fact_order_lines` |
|---|---|
| **Priority question** | Booked merchandise value after discounts by month/category |
| **Process** | Order confirmation |
| **Grain** | One row per `(order_id,line_no)` at order confirmation |
| **Trigger event** | Order successfully confirmed |
| **Business key** | `order_id + line_no` |
| **Measures** | `quantity`, `line_discount_amount`, `booked_amount` |
| **Dimensions** | Confirmation date, customer, product at order time |
| **Monetary definition** | Single reporting currency; excludes tax, shipping, and refunds |
| **Source** | Controlled order confirmation events/snapshots |
| **History** | Point-in-time dimension version resolution |
| **Latency** | E.g., hourly load, late-arriving data handling included |
| **Tests** | Grain uniqueness, amount formula, FK checks, source reconciliation |
| **Do not use to answer** | Accounting revenue, web conversion rate without session source |

This acts as a contract among business stakeholders, data engineers, analysts, and operations. When a KPI definition changes, you can trace exactly which facts, queries, and tests need updating.

### Questions to Ask Before Finalizing

1. Do we need **current figures** or figures **as they were at a point in time**?
2. Is the calculation at **order**, **order line**, **payment**, **shipment**, **refund**, or **inventory snapshot** level?
3. Can any entity appear **multiple times** within one process?
4. Across which time/dimensions are measures additive, and across which are they non-additive?
5. Are identifiers globally unique or scoped by tenant/store?
6. Should dimension history reflect transaction time or current classification?
7. How should late, edited, or cancelled data appear in reports?
8. Does any report require a **denominator** when the source only provides the numerator?
9. What reconciliation benchmark proves the numbers are accurate?
10. Which queries are most critical for selecting partitions, indexes, clustering, or materialization?

## 14. Avoid Copying the OLTP Model Directly into a Data Mart

Transactional systems (OLTP) organize data to **record current state accurately, eliminate redundancy, and enforce constraints**. Analytical systems organize around **processes and measurement grain**, optimizing multi-dimensional aggregations.

Example:

~~~text
OLTP:
    orders
    order_items
    customers
    products
    payments
    shipments

Analytics:
    fact_order_lines
    fact_payment_transactions
    fact_shipments / fulfillment_snapshot
    dim_customer
    dim_product
    dim_date
~~~

Not every OLTP table maps to a corresponding fact or dimension. Determine **which events constitute analytical data** and **which relationships can be joined without distorting grain**.

### Star Schema, Snowflake, and Wide Tables

| Structure | Strengths | Controls Needed |
|---|---|---|
| **Star schema** | Clear facts–dimensions, intuitive GROUP BY across dimensions, transparent grain | Dimension history, fanout, conformed dimensions |
| **Snowflake** | Deeply normalizes certain dimensions, shares hierarchies | More JOINs and query complexity |
| **One big table / wide table** | Convenient for specific queries or columnar engines | Repeated dimension attributes, harder SCD handling, fanout if grains mix |
| **KPI-oriented data mart** | Optimizes critical reports, pre-aggregation | Must document sources, formulas, and refresh timestamps |

No single choice fits every system. The invariant is that **grain and KPIs must be unambiguous**, whether stored across star tables, one wide table, or a dedicated serving model.

### Document, Graph, and Analytics

- **Document:** an order may embed an array of line items for whole-order reads; when analyzing amounts by product, **unnest the array to the right grain** and never copy order-level totals onto every line.
- **Graph:** multi-hop relationships suit network analysis, yet path counts do not necessarily equal transaction counts. Define the counted object and avoid duplicate paths.
- **Normalized relational:** ideal as a transactional source with explicit keys/constraints; analytical models can transform it into facts–dimensions.
- **Columnar analytical stores:** suited for scanning and aggregating at scale, while still requiring key definitions, grain, and quality checks even when the DBMS does not enforce FKs.

Differences in storage engines do not replace the thinking sequence: **process → grain → measures → dimensions**.

## 15. Common Mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Starting from the list of source tables | Model lacks clear measurement questions | Write questions/KPIs and processes first |
| Claiming "one row per order" when the fact is actually at line level | Wrong order counts and sales totals | Declare grain with keys and timestamp |
| Mixing booking, payment, and refund events into one undefined measure | Confuses booked amount with net revenue | Separate processes, define adjustments |
| JOINing two detail facts on `order_id` | Multiplies rows by the Cartesian product | Aggregate each fact to a compatible grain first |
| Summing `inventory_on_hand` across multiple days | Double-counts balances | Pick snapshot cutoff and proper aggregation rule |
| Averaging group-level ratios | Overall KPI skewed by differing denominators | Divide summed numerators by summed denominators |
| JOINing an SCD2 dimension solely on business key | Multiplies fact rows across dimension versions | Join on surrogate key or effective time window |
| Using current attributes for historical questions silently | Past reports get reclassified | Intentionally choose Type 1, Type 2, or snapshot |
| Using `SUM(DISTINCT amount)` to fix fanout | Wrongly drops distinct transactions with equal amounts | Fix join keys and grain |
| Using `ingested_at` instead of business event date | Late-arriving data lands in the wrong period | Distinguish event time from load time |
| Dropping rows with missing dimension matches | KPIs quietly undercount without alerting | Monitor late dimensions, unknown members, and backfill |
| Treating one payment transaction as one order | Under/overcounts amounts on split payments | Choose transaction grain and define aggregation |
| Counting customers by summing monthly `COUNT(DISTINCT)` | Customers active across multiple months get counted repeatedly | Compute distinct across the entire target window |

## 16. Practice Exercises with Solutions

### Exercise 1 — Choosing Grain for Booked Value

An order D01 has three lines, each with a different product, quantity, and price. Requirement: "booked merchandise value by product category and confirmation month". Which fact grain is suitable?

**Solution:** One row per **`(order_id,line_no)` at confirmation time**, assuming lines do not have multiple versions at the same timestamp. The fact needs confirmation date and point-in-time product/category dimensions, along with `quantity`, `unit_price_at_order`, `line_discount_amount`, and the defined measure. An order-level fact cannot allocate value across categories when an order spans multiple categories.

### Exercise 2 — Order Count vs. Line Count

An order-line fact contains D01 with three rows and D02 with one row. What do `COUNT(*)` and `COUNT(DISTINCT order_id)` return?

**Solution:** `COUNT(*) = 4` order lines, while `COUNT(DISTINCT order_id) = 2` orders. When grouping by category, one order may appear in multiple categories; never sum distinct order counts across categories to infer the overall total.

### Exercise 3 — Selecting Fact Type for Inventory

Management wants to inspect remaining quantity in each warehouse at the end of every day, including days with zero receipts/issues. Which fact type should you choose?

**Solution:** **Periodic snapshot** at grain `(snapshot_date,warehouse_id,product_id)` at the agreed cutoff time. Inventory is a **semi-additive** measure: it can be summed across warehouses/products at the same timestamp, but must not be summed across days to represent "monthly stock".

### Exercise 4 — Multi-Parcel Fulfillment Process

An order is packed into three parcels; two are delivered today and one tomorrow. If the KPI is on-time parcel delivery rate, which grain should be used?

**Solution:** Grain at the **parcel/shipment level** per business identifier, not one row per order. You need `shipment_id` or parcel ID, promised delivery date, and actual delivery date. A parcel-level accumulating snapshot works well if tracking multiple milestones.

### Exercise 5 — Fanout Between Orders and Payments

Order D01 has three order lines and two capture transactions. Joining the order-line fact with the payment fact on `order_id` yields how many rows? Can you directly SUM both measures?

**Solution:** It produces \(3\times2=6\) rows. You must not SUM directly because measures from both sides repeat. Aggregate booked value by order and captured payments by order **independently**, then JOIN the two order-level totals on `order_id` before further dimensional breakdown.

### Exercise 6 — Historical Category Classification

Product SP01 switched from "Accessories" to "Electronics" in July. June reports must preserve the category active at purchase time. How should the dimension be handled?

**Solution:** Use **SCD Type 2** or point-in-time attribute snapshots, linking June facts to the "Accessories" version. Never join the version table solely on `product_id`, as that multiplies rows; use the surrogate key resolved at event time or non-overlapping effective range predicates.

### Exercise 7 — Successfully Paid Orders

The payment source contains `CAPTURE`, `REFUND`, and `RETRY` transactions. Can the requirement "number of successfully paid orders" use `COUNT(*)` on the transaction fact?

**Solution:** No. One order can have multiple captures, retries, or refunds. Define what **successfully paid** means, filter to valid transaction statuses, establish timing rules, and aggregate at the **order** level (e.g., aggregating payments by `order_id`) rather than counting raw transactions.

### Exercise 8 — Conversion Rate Missing Denominator

The analytics team has `fact_orders` but no visit/session table. Can you accurately calculate session-to-order conversion rate?

**Solution:** No. Order facts only supply one side of the equation. You need **session or user traffic data** with definitions for eligible visits, attribution windows, and how orders link to sessions/channels; never substitute customer counts from `orders` as a proxy denominator when that violates the KPI definition.

### Exercise 9 — Choosing an Additive Measure Calculation

Two lines have `(quantity=1, unit_price=100)` and `(quantity=9, unit_price=10)`. What is the **quantity-weighted** average unit price?

**Solution:** \((1\times100+9\times10)/(1+9)=19\). The unweighted arithmetic mean of the two prices is 55, which ignores quantity weights. Also specify whether discounts, taxes, or currency conversions apply.

### Exercise 10 — Request with Ambiguous Date

Business asks for "October sales". The data contains `created_at`, `confirmed_at`, `paid_at`, and `ingested_at`. What should you clarify before writing the query?

**Solution:** Clarify whether "sales" means booked, paid, or recognized value; **which event timestamp** defines October; which timezone; which cancellation/refund statuses apply; how late-arriving events are handled; and report cutoff timing. Only then choose the matching fact and date dimension.

## 17. Pre-Sign-Off Checklist for Analytical Modeling

- [ ] Analytical questions and **business decisions** are explicitly documented.
- [ ] KPIs clearly define numerator, denominator, event scope, timestamps, and exclusions.
- [ ] The **business process** generating the measured events/objects is identified.
- [ ] Each fact's **grain** is written as a testable sentence with an appropriate key.
- [ ] Measures of **different grains** are not mixed in one fact without allocation rules.
- [ ] Transaction, periodic snapshot, accumulating snapshot, or factless fact is chosen to match the question.
- [ ] Every measure is classified as **additive/semi-additive/non-additive** with currency and unit boundaries.
- [ ] Dimensions have clear definitions, keys, and shared scope; date roles are explicit.
- [ ] Decided intentionally between analyzing by **current vs. event-time** attributes.
- [ ] Fact–dimension JOINs guarantee **exactly one version** or use proper bridge/allocation rules.
- [ ] Two multi-row facts are never joined without first aggregating to a compatible grain.
- [ ] Pipelines handle late-arriving events, duplicate events, adjustments, and idempotent reloads.
- [ ] Tests cover grain uniqueness, measure formulas, dimension references, and source reconciliation.
- [ ] Model validated against real questions, including **cases unanswerable with current sources**.
- [ ] Physical design, indexes/partitioning, and data marts align with workload without blurring grain.

**Remember:** Good analytical modeling does not start with "what tables do we have?" but with **"what question must we answer, which process creates that truth, and what exactly does one fact row represent?"** Lock down those three things first, and you can choose measures, dimensions, keys, and history consistently — avoiding fanout JOINs and building reconcilable reports.
