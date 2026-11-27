# Grouping Low-Cardinality Flags and Codes into a Junk Dimension

A fact table in a data warehouse often holds millions of rows, yet each row carries several **Yes/No** flags, short status codes, or classification labels with only a few distinct values. For example, at order placement time, the system records **whether gift wrapping was requested**, **whether a discount coupon was applied**, and **whether the fulfillment method is delivery or store pickup**. These flags carry clear analytical value, yet each flag on its own is too small to warrant a dedicated dimension table.

A **junk dimension** is a dimensional modeling technique that groups **a set of low-cardinality classification attributes** into a single dimension table storing **valid combinations of values**, which the fact table then references via **a single surrogate key**. The word *junk* does not imply useless data: these are meaningful business attributes that simply lack enough substance to become standalone specialized dimensions.

This lesson belongs to the **Dimension Tables** chapter of the **DATABASE_DATA_MODELING** module. We will progress from business questions to grain, star schema, PostgreSQL SQL, data-loading pipelines, quality checks, historical semantics, and physical trade-offs. The goal is to understand **when grouping flags clarifies an analytical model, and when you should not group them**.

## 1. The Problem: Too Many Small Flags and Codes on a Fact Table

Suppose the analytics warehouse needs to model an **order successfully placed** event. The operational source sends:

~~~text
order_number
placed_on
customer_id
is_gift_wrap
is_coupon_applied
fulfillment_mode
merchandise_total_vnd
~~~

Three classification attributes:

- **is_gift_wrap**: Was gift wrapping requested at placement? Takes **TRUE/FALSE**.
- **is_coupon_applied**: Was at least one coupon offer **successfully applied** at order confirmation? Takes **TRUE/FALSE**.
- **fulfillment_mode**: Delivery method **selected at placement**, either **SHIP** (delivery) or **PICKUP** (store pickup).

These differ from measures such as **merchandise_total_vnd**, because you do not sum a TRUE flag across orders the way you sum monetary amounts. To find how many orders had gift wrapping, you **count orders** matching that condition.

### 1.1. Three Initial Ways to Organize Them

| Storage approach | Conceptual structure | Strengths | Limitations |
| --- | --- | --- | --- |
| **Keep flags directly on the fact** | Fact has three flag/code columns | Simple, direct filtering, easy to understand at small scale | Many small descriptive columns widen the fact table and make governing consistent classification labels harder |
| **Create separate mini-dimensions** | `dim_gift_wrap`, `dim_coupon`, `dim_fulfillment` | Clear per-concept separation | Fact accumulates many foreign keys; adding several 2–3 row tables can be overkill |
| **Group into a junk dimension** | `dim_order_junk(gift_wrap, coupon, fulfillment)`, fact stores only `junk_key` | Single place expressing combinations, easy multi-flag grouping | Requires a JOIN, combination-count management, and load/historization handling |

**No single approach is right for every system.** If there are only two flags and a columnar engine compresses repeated values very well, keeping them directly on the fact can be simpler and faster. A junk dimension is a **deliberate design choice**, not a mandatory requirement to achieve 3NF or BCNF.

### 1.2. What Qualifies as a Junk Dimension?

In this lesson, the junk dimension contains:

~~~text
dim_order_junk(
    junk_key,
    is_gift_wrap,
    is_coupon_applied,
    fulfillment_mode
)
~~~

Example valid or observed combinations:

| junk_key | is_gift_wrap | is_coupon_applied | fulfillment_mode |
| ---: | --- | --- | --- |
| 1 | FALSE | FALSE | SHIP |
| 2 | TRUE | FALSE | SHIP |
| 3 | FALSE | TRUE | PICKUP |
| 4 | TRUE | TRUE | SHIP |
| 5 | FALSE | FALSE | PICKUP |

The fact references **junk_key**. Thus, a value like **junk_key = 4** tells us that at order placement: **gift wrap was selected, a coupon was applied, and delivery was chosen**.

**`junk_key` is not a business code with fixed meaning.** In the example, numbers 1–5 are purely illustrative IDs. Production systems must look up combinations by attribute columns—never hardcode rules like “junk_key = 4 means the order has a coupon,” because surrogate keys can be assigned differently across environments.

## 2. Lock Down the Grain Before Grouping Flags

**Grain** is the exact statement of what one fact row represents. Without clarifying grain, a junk dimension can corrupt both counts and flag meanings.

In our example:

> One row of **fact_order_placed** represents **one order successfully placed at `placed_on`**. The flags reflect choices and conditions **at placement time**, not current status later on.

Let us distinguish:

| Attribute | Grain and timing | Belongs in the order-placed junk dimension? |
| --- | --- | --- |
| Gift wrap at placement | One order at placement | **Yes** |
| Coupon applied at confirmation | One order at placement | **Yes** |
| Fulfillment method chosen at placement | One order at placement | **Yes** |
| Product on an order line | One order line | **No**: belongs to the product dimension of a line fact |
| Customer of the order | One customer, many descriptive attributes | **No**: should use `dim_customer` |
| Order number | One order, many unique values | **No**: usually a *degenerate dimension* on the fact |
| Order merchandise value | A measure at order grain | **No**: stored in the fact as a measure |
| Delivered successfully as of today | Current status that can change after placement | **No** for an immutable event fact like this example |

If instead you have **fact_order_line** at line-item grain, you cannot implicitly assume **one row = one order**. Order-level flags would repeat across multiple lines: **`COUNT(*)`** would count lines, not orders. Storing them on a line fact can be valid if the flags apply to every line and analyses are carefully defined; to count orders, use a unique order key or an order-level fact.

### 2.1. Distinguishing Flags, Descriptive Attributes, and Measures

- **Flags/classification codes** answer “which category/group?”: gift wrap, coupon applied, fulfillment type.
- **Rich dimension attributes** answer “which entity and what properties?”: customer, product, store, campaign.
- **Measures** answer “how much/how many?”: amount, quantity, cost.
- **Transaction identifiers** answer “which event?”: `order_number`, `transaction_id`.

Do not throw **amount**, **product_id**, or **order_number** into a junk dimension merely because they sit next to the flags in the same source payload.

## 3. Which Flags and Codes to Group

A good candidate typically satisfies several criteria:

1. **Low cardinality:** few distinct values, such as BOOLEANs or classification codes with a handful of states.
2. **Same grain and same point-in-time semantics** as the fact or snapshot it describes.
3. **Lacks its own rich attribute set**: no standalone descriptions, hierarchies, history, ownership, or business keys justifying a dedicated dimension.
4. **Used as filters/group-bys** in reporting.
5. **Manageable actual combination count**: does not explode into hundreds of thousands or millions of hard-to-maintain combinations.

### 3.1. Examples of What to Group and What Not to Group

| Attribute | Suggested conclusion | Reason |
| --- | --- | --- |
| `is_gift_wrap` | Consider grouping | Two values, describes order choice |
| `is_coupon_applied` | Consider grouping | Two values, condition confirmed at placement |
| `fulfillment_mode = SHIP/PICKUP` | Consider grouping | Low-cardinality code, assuming no complex hierarchy or lifecycle |
| `promotion_id` / `coupon_code` | **Do not group** | Potentially high cardinality with its own attributes; fits a promotion dimension or relationship |
| `customer_id` | **Do not group** | Independent entity with rich attributes and history |
| `payment_amount` | **Do not group** | Monetary measure |
| `transaction_id` | **Do not group** | High-cardinality identifier, typically a degenerate dimension |
| `product_category` | Depends on model | Usually belongs in `dim_product` or `dim_category` with hierarchies and history |
| `current_delivery_status` | Usually **do not group with immutable placement flags** | Different update timing and its own state machine |

**The word “junk” refers only to the structural role of small flags in dimensional modeling**, not a lack of business value. Even a low-cardinality code may still need its own dimension if it has definitions, multilingual descriptions, hierarchies, effective dates, or independent governance rules.

### 3.2. Can Correlated Codes Be Grouped?

**Yes**, provided the combinations have **valid business semantics** and are validated. Flags do not have to be statistically independent. For instance, certain fulfillment methods may restrict a service option; the dimension can store only permitted combinations.

However, avoid grouping flags with **unverified implicit constraints**. If the source allows:

~~~text
fulfillment_mode = PICKUP
is_home_delivery_requested = TRUE
~~~

then those two attributes appear contradictory under normal definitions. Ask the business: is “home delivery requested” a prior request, a current request, or the finalized choice? If the combination is genuinely forbidden, block it during ingestion or enforce a **CHECK** constraint on the dimension; do not just hope source data never produces it.

## 4. Estimating Combination Counts: Avoiding Cardinality Explosion

For classification columns having **c₁, c₂, …, cₙ** distinct values respectively, the **maximum** number of combinations is:

\[
N_{\max} = \prod_{i=1}^{n} c_i
\]

With **b binary flags** having independent value domains, the maximum is:

\[
N_{\max} = 2^b
\]

| Number of binary flags | Maximum combinations |
| ---: | ---: |
| 3 | 8 |
| 8 | 256 |
| 12 | 4,096 |
| 16 | 65,536 |
| 20 | 1,048,576 |

With **3 flags** in our example (2 × 2 × 2), there are at most **8 combinations**. The sample currently uses **5 combinations**. You can pre-generate all 8 if all are valid and the count is small, though there is no requirement to generate rows for combinations that never occur.

If each flag expands from **TRUE/FALSE** to **YES/NO/UNKNOWN**, eight such flags can produce **3⁸ = 6,561** combinations; **12 three-state flags** can produce **3¹² = 531,441** combinations.

### 4.1. Theoretical vs. Valid vs. Observed Combinations

Distinguish three sets:

- **Theoretical combinations:** the Cartesian product of all listed codes/flags.
- **Valid combinations:** combinations actually permitted by business rules.
- **Observed combinations:** combinations that have appeared in loaded facts.

The typical relationship is:

~~~text
observed combinations ⊆ valid combinations ⊆ theoretical combinations
~~~

When source data is clean and rules are thorough, not every junk dimension needs every valid combination pre-loaded. Two common policies are **prepopulate** for small approved combination sets or **insert-on-demand** when a valid combination first arrives.

To keep dimension row counts controlled, you can **split into several subject-area junk dimensions** (such as fulfillment flags and promotion flags) or keep attributes directly on the fact, depending on workload. Never bundle 20 flags together solely because they are all BOOLEANs.

## 5. Star Schema for Placed Orders

The following diagram shows a one-row-per-order fact at placement time, referencing date, customer, and junk dimensions:

~~~mermaid
erDiagram
    DIM_DATE ||--o{ FACT_ORDER_PLACED : "order date"
    DIM_CUSTOMER ||--o{ FACT_ORDER_PLACED : "ordering customer"
    DIM_ORDER_JUNK ||--o{ FACT_ORDER_PLACED : "classification"
    DIM_DATE {
        integer date_key PK
        date full_date
    }
    DIM_CUSTOMER {
        bigint customer_key PK
        varchar customer_code
        varchar customer_name
    }
    DIM_ORDER_JUNK {
        bigint junk_key PK
        boolean is_gift_wrap
        boolean is_coupon_applied
        varchar fulfillment_mode
    }
    FACT_ORDER_PLACED {
        bigint order_fact_key PK
        varchar order_number UK
        integer date_key FK
        bigint customer_key FK
        bigint junk_key FK
        bigint merchandise_total_vnd
    }
~~~

**`fact_order_placed`** holds the measure **`merchandise_total_vnd`**, while **`dim_order_junk` has no measures**; it holds only classification attributes. **`order_number`** is a transaction identifier (degenerate dimension) on the fact; **`junk_key`** is the surrogate key representing the attribute combination.

### 5.1. PostgreSQL SQL: Dimensions and Fact

~~~sql
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE
);

CREATE TABLE dim_customer (
    customer_key BIGINT PRIMARY KEY,
    customer_code VARCHAR(20) NOT NULL UNIQUE,
    customer_name VARCHAR(100) NOT NULL
);

CREATE TABLE dim_order_junk (
    junk_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    is_gift_wrap BOOLEAN NOT NULL,
    is_coupon_applied BOOLEAN NOT NULL,
    fulfillment_mode VARCHAR(10) NOT NULL
        CHECK (fulfillment_mode IN ('SHIP', 'PICKUP')),
    UNIQUE (
        is_gift_wrap,
        is_coupon_applied,
        fulfillment_mode
    )
);

CREATE TABLE fact_order_placed (
    order_fact_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(20) NOT NULL UNIQUE,
    date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    customer_key BIGINT NOT NULL REFERENCES dim_customer(customer_key),
    junk_key BIGINT NOT NULL REFERENCES dim_order_junk(junk_key),
    merchandise_total_vnd BIGINT NOT NULL
        CHECK (merchandise_total_vnd >= 0)
);
~~~

Key design points:

- **`junk_key`** is database-generated, not a code carrying business meaning.
- **`UNIQUE(is_gift_wrap, is_coupon_applied, fulfillment_mode)`** prevents two dimension rows from sharing the same combination, giving ETL a one-to-one mapping.
- **`NOT NULL`** with **`CHECK`** on the dimension keeps codes unambiguous in this example; **UNKNOWN/NOT_APPLICABLE** policies are discussed separately in Section 9.
- The fact holds **one foreign key `junk_key`** instead of three inline classification columns.
- **`UNIQUE(order_number)`** fits because the fact records only **one placement event** per order. If the fact records multiple events per order, grain and keys must change.
- Foreign keys and unique constraints guard relational invariants, but do not automatically verify that flag definitions match transaction history.

### 5.2. Loading Dimensions and Sample Data

~~~sql
INSERT INTO dim_date (date_key, full_date) VALUES
    (20261119, DATE '2026-11-19'),
    (20261120, DATE '2026-11-20'),
    (20261121, DATE '2026-11-21');

INSERT INTO dim_customer
    (customer_key, customer_code, customer_name)
VALUES
    (1, 'C01', 'An'),
    (2, 'C02', 'Bình'),
    (3, 'C03', 'Chi');

INSERT INTO dim_order_junk
    (is_gift_wrap, is_coupon_applied, fulfillment_mode)
VALUES
    (FALSE, FALSE, 'SHIP'),
    (TRUE,  FALSE, 'SHIP'),
    (FALSE, TRUE,  'PICKUP'),
    (TRUE,  TRUE,  'SHIP'),
    (FALSE, FALSE, 'PICKUP');
~~~

**Never assume** IDs are generated sequentially in exact `VALUES` order or match across environments. When loading the fact, look up the combination by **flag/code values** to retrieve the actual **`junk_key`**:

~~~sql
INSERT INTO fact_order_placed
    (order_number, date_key, customer_key,
     junk_key, merchandise_total_vnd)
SELECT
    src.order_number,
    src.date_key,
    src.customer_key,
    junk.junk_key,
    src.merchandise_total_vnd
FROM (
    VALUES
        ('O1001', 20261119, 1::BIGINT,
         FALSE, FALSE, 'SHIP',   120000::BIGINT),
        ('O1002', 20261119, 2::BIGINT,
         TRUE,  FALSE, 'SHIP',   230000::BIGINT),
        ('O1003', 20261120, 1::BIGINT,
         FALSE, TRUE,  'PICKUP', 150000::BIGINT),
        ('O1004', 20261120, 3::BIGINT,
         TRUE,  TRUE,  'SHIP',   320000::BIGINT),
        ('O1005', 20261121, 2::BIGINT,
         FALSE, FALSE, 'SHIP',   180000::BIGINT),
        ('O1006', 20261121, 3::BIGINT,
         FALSE, FALSE, 'PICKUP',  90000::BIGINT)
) AS src(
    order_number, date_key, customer_key,
    is_gift_wrap, is_coupon_applied, fulfillment_mode,
    merchandise_total_vnd
)
JOIN dim_order_junk AS junk
  ON junk.is_gift_wrap = src.is_gift_wrap
 AND junk.is_coupon_applied = src.is_coupon_applied
 AND junk.fulfillment_mode = src.fulfillment_mode;
~~~

After loading, the fact contains **6 orders** with a total merchandise value of **1,090,000 VND**. Subsequent queries assume the incremental load step in Section 8 has not yet run.

## 6. Analyzing with a Junk Dimension

### 6.1. Counting and Summing Amounts by Fulfillment Method

~~~sql
SELECT
    junk.fulfillment_mode,
    COUNT(*) AS order_count,
    SUM(f.merchandise_total_vnd) AS merchandise_total_vnd
FROM fact_order_placed AS f
JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key
GROUP BY junk.fulfillment_mode
ORDER BY junk.fulfillment_mode;
~~~

Sample result:

| fulfillment_mode | order_count | merchandise_total_vnd |
| --- | ---: | ---: |
| PICKUP | 2 | 240000 |
| SHIP | 4 | 850000 |

The JOIN does not multiply rows because each **`junk_key`** on the fact matches **one** dimension row (primary key of `dim_order_junk`). Using a dimension attribute, facts can be grouped cleanly without writing conditional logic over cryptic technical codes.

### 6.2. Counting Orders with Gift Wrap or Coupon

~~~sql
SELECT
    COUNT(*) AS all_orders,
    COUNT(*) FILTER (WHERE junk.is_gift_wrap)
        AS gift_wrap_orders,
    COUNT(*) FILTER (WHERE junk.is_coupon_applied)
        AS coupon_orders,
    COUNT(*) FILTER (
        WHERE junk.is_gift_wrap AND junk.is_coupon_applied
    ) AS both_flags_orders,
    SUM(f.merchandise_total_vnd) FILTER (
        WHERE junk.is_coupon_applied
    ) AS coupon_order_merchandise_vnd
FROM fact_order_placed AS f
JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key;
~~~

Result:

| all_orders | gift_wrap_orders | coupon_orders | both_flags_orders | coupon_order_merchandise_vnd |
| ---: | ---: | ---: | ---: | ---: |
| 6 | 2 | 2 | 1 | 470000 |

Both TRUE flags can occur together on one order, so **2 gift-wrap orders + 2 coupon orders** does not mean **4 distinct orders** satisfy at least one condition. To count orders matching at least one flag, use **`OR`**:

~~~sql
SELECT COUNT(*) AS orders_with_either_flag
FROM fact_order_placed AS f
JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key
WHERE junk.is_gift_wrap OR junk.is_coupon_applied;
-- Result: 3 orders (O1002, O1003, O1004).
~~~

### 6.3. Analyzing Multiple Flags Simultaneously by Date

~~~sql
SELECT
    d.full_date,
    junk.fulfillment_mode,
    junk.is_coupon_applied,
    COUNT(*) AS order_count,
    SUM(f.merchandise_total_vnd) AS total_vnd
FROM fact_order_placed AS f
JOIN dim_date AS d ON d.date_key = f.date_key
JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key
GROUP BY
    d.full_date,
    junk.fulfillment_mode,
    junk.is_coupon_applied
ORDER BY d.full_date, junk.fulfillment_mode, junk.is_coupon_applied;
~~~

**The count is accurate** because the fact grain is one order. If the fact later stores **multiple status updates per order**, this query would count update events rather than unique orders. The fix is not sprinkling `DISTINCT` arbitrarily; it is redefining grain and metrics cleanly.

### 6.4. Report Labels Provided by the Dimension

If multiple reports share Vietnamese display names for `fulfillment_mode`, you can add a governed descriptive column in the dimension, such as **`fulfillment_label_vi`**, or reference a dedicated code table when labels have multilingual/independent metadata.

Example projection that preserves grain:

~~~sql
SELECT
    CASE junk.fulfillment_mode
        WHEN 'SHIP' THEN 'Giao hàng'
        WHEN 'PICKUP' THEN 'Nhận tại cửa hàng'
    END AS fulfillment_label_vi,
    COUNT(*) AS order_count
FROM fact_order_placed AS f
JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key
GROUP BY junk.fulfillment_mode;
~~~

This is a short presentation expression in an illustrative query. In larger models, labels should be centrally governed so dashboards do not define conflicting names. If a classification code has rich, hierarchical, or multilingual metadata, consider a dedicated dimension instead of stuffing all metadata into a junk dimension.

## 7. Should a Junk Dimension Hold All Combinations or Only Used Ones?

### 7.1. Prepopulate All Valid Combinations

When the combination space is small and stable, you can pre-load all **valid combinations**. In this lesson, there are at most 8 combinations, so prepopulating all 8 is straightforward.

Pros:

- Every valid fact can look up its key without inserting new dimension rows.
- Each combination can be reviewed and approved before loading facts.
- Reduces first-time load contention when encountering a new combination.

Cons:

- Unreferenced dimension rows exist with zero matching facts.
- Generating combinations via **`CROSS JOIN`** can produce combinations **prohibited by business rules**.
- With many flags/codes, the Cartesian product can vastly exceed actual combinations.

### 7.2. Insert Combinations on Demand (Insert-on-Demand)

When valid combinations are numerous yet only a subset actually occurs:

1. Land fact data in staging.
2. Standardize flags/codes against the business dictionary.
3. Extract **`DISTINCT` combinations** from staging.
4. Insert valid combinations not yet present in `dim_order_junk`.
5. Look up **`junk_key`** using all combination attributes.
6. Load facts while reconciling row counts and checking for unmapped combinations.

The advantage is keeping the dimension compact to observed combinations without materializing every theoretical possibility. The trade-off is that the pipeline must handle new combinations, duplicate keys, invalid codes, and concurrent writes. A **`UNIQUE` constraint on the flag/code tuple** is an essential safeguard.

### 7.3. Comparing the Two Approaches

| Criterion | Prepopulate valid | Insert-on-demand |
| --- | --- | --- |
| Very few, stable combinations | Usually convenient | Also works |
| Many invalid theoretical combinations | Must filter before generating | Must validate each new combination |
| New combination seen in ETL | Key usually already exists | Must allocate new key |
| Key governance and domain checks | Easy if code tables are stable | Requires normalization, load, and reconciliation logic |
| Growth in combinations over time | Must expand valid set | Grows with observed data |

There is no benefit in keeping invalid combinations just to “have all rows”; doing so can let ETL silently accept corrupt data.

## 8. Load Pipeline: Standardize, Upsert Combinations, Look Up Keys

Suppose two new orders arrive with combination **(FALSE, TRUE, SHIP)**, which was not loaded in the earlier sample dimension table. The step below shows the **combination being created once** and both orders referencing the resulting key.

**Preconditions:** DDL and sample data from Section 5 have been executed; referenced dates and customers exist. The ETL block below runs in a separate transaction; fact counts and totals **after loading** differ from Section 6 results.

~~~sql
BEGIN;

CREATE TEMP TABLE staged_orders (
    order_number VARCHAR(20) PRIMARY KEY,
    date_key INTEGER NOT NULL,
    customer_key BIGINT NOT NULL,
    is_gift_wrap BOOLEAN NOT NULL,
    is_coupon_applied BOOLEAN NOT NULL,
    fulfillment_mode VARCHAR(10) NOT NULL,
    merchandise_total_vnd BIGINT NOT NULL
) ON COMMIT DROP;

INSERT INTO staged_orders (
    order_number, date_key, customer_key,
    is_gift_wrap, is_coupon_applied, fulfillment_mode,
    merchandise_total_vnd
) VALUES
    ('O1007', 20261121, 1,
     FALSE, TRUE, 'SHIP', 70000),
    ('O1008', 20261121, 2,
     FALSE, TRUE, 'SHIP', 80000);

-- Deduplicate combinations; the dimension's UNIQUE constraint handles races.
INSERT INTO dim_order_junk (
    is_gift_wrap, is_coupon_applied, fulfillment_mode
)
SELECT DISTINCT
    is_gift_wrap, is_coupon_applied, fulfillment_mode
FROM staged_orders
ON CONFLICT (
    is_gift_wrap, is_coupon_applied, fulfillment_mode
) DO NOTHING;

-- Never guess junk_key = max(junk_key) + 1.
-- Look up the key using the full tuple of flag/code values.
INSERT INTO fact_order_placed (
    order_number, date_key, customer_key,
    junk_key, merchandise_total_vnd
)
SELECT
    src.order_number,
    src.date_key,
    src.customer_key,
    junk.junk_key,
    src.merchandise_total_vnd
FROM staged_orders AS src
JOIN dim_order_junk AS junk
  ON junk.is_gift_wrap = src.is_gift_wrap
 AND junk.is_coupon_applied = src.is_coupon_applied
 AND junk.fulfillment_mode = src.fulfillment_mode
WHERE TRUE
ON CONFLICT (order_number) DO NOTHING;

COMMIT;
~~~

In this example, **`dim_order_junk`** grows from **5 to 6 combinations**, and the fact grows from **6 to 8 orders**. The dimension does not add two rows for two orders because both orders share the same combination of values.

### 8.1. Why Use UNIQUE and ON CONFLICT?

Two concurrent pipelines may encounter the same new combination simultaneously and both attempt an `INSERT`. If they only run **`SELECT` to check absence** followed by **`INSERT`** without a constraint, they can create two equivalent rows with different `junk_key` values. A **`UNIQUE` constraint on the full combination** protects against this at the database level; **`ON CONFLICT DO NOTHING`** lets one writer skip the row already inserted by the other.

**`ON CONFLICT (order_number) DO NOTHING`** is only appropriate when already-loaded orders should not be overwritten. If the system must correct **`merchandise_total_vnd`** or reprocess modified events, you need an **explicit fact correction/upsert policy**; ignoring all conflicts can mask updated source data.

### 8.2. Catching Unmapped Staging Rows

Example query to detect staging combinations missing from the dimension:

~~~sql
SELECT
    src.order_number,
    src.is_gift_wrap,
    src.is_coupon_applied,
    src.fulfillment_mode
FROM staged_orders AS src
LEFT JOIN dim_order_junk AS junk
  ON junk.is_gift_wrap = src.is_gift_wrap
 AND junk.is_coupon_applied = src.is_coupon_applied
 AND junk.fulfillment_mode = src.fulfillment_mode
WHERE junk.junk_key IS NULL;
~~~

**Note:** `staged_orders` in the example was created with **`ON COMMIT DROP`**, so this query only works **inside the transaction before `COMMIT`**, or requires switching to a persistent staging table. This is an **ETL test/monitoring check**; never let an **`INNER JOIN`** silently drop facts missing a combination and report the load as successful.

In production systems, pipelines typically add a **persistent raw/staging zone, error logs, source watermarks, row-count checks**, and recovery mechanisms. The minimal SQL example only demonstrates creating and looking up `junk_key`.

### 8.3. Reconciling Row Counts and Source Keys

A pipeline should verify:

~~~text
eligible source orders
  = newly loaded orders + pre-existing orders (if skips allowed)
    + rejected orders with logged reasons
~~~

Comparing total record counts alone is insufficient because **dropping one order and double-loading another** leaves totals identical. Reconcile **`order_number`**, date, customer, monetary amount, and flags/codes. When business rules require preserving correction history, record change versions and adjustment events rather than overwriting arbitrarily.

## 9. UNKNOWN, NOT APPLICABLE, and NULL: Do Not Equate Them with FALSE

In real data, a flag may lack an explicit confirmed value:

- **FALSE/NO:** the business confirmed the condition is **not true**.
- **UNKNOWN:** data has not arrived yet, is missing from the source, or cannot be determined.
- **NOT_APPLICABLE (N/A):** the condition **does not apply** to this type of event.
- **TRUE/YES:** the condition is confirmed true.

For example, **`is_coupon_applied = FALSE`** means no coupon was successfully applied. Yet if the payment system failed to transmit coupon details, inferring **`NULL → FALSE`** causes reports to understate coupon adoption.

### 9.1. Two Common Policies

**Policy A — reject or quarantine incomplete records:** suitable when flags are mandatory for publishing metrics and records can be reprocessed. The fact is not loaded into the main analytical table; bad rows wait in staging/quarantine with clear error reasons.

**Policy B — represent undetermined states with explicit domain codes:** suitable when facts must still be visible, yet unknown must remain distinct from negative. Replace BOOLEANs with state codes having domains like:

~~~text
gift_wrap_state  ∈ {YES, NO, UNKNOWN}
coupon_state     ∈ {YES, NO, UNKNOWN, NOT_APPLICABLE}
fulfillment_mode ∈ {SHIP, PICKUP, UNKNOWN}
~~~

Under Policy B, the dimension might store:

| gift_wrap_state | coupon_state | fulfillment_mode | Meaning |
| --- | --- | --- | --- |
| YES | NO | SHIP | Gift wrap requested, no coupon applied, delivery |
| UNKNOWN | YES | SHIP | Gift wrap unknown, coupon confirmed, delivery |
| NO | NOT_APPLICABLE | PICKUP | No gift wrap, coupon not applicable for this transaction type |

**UNKNOWN/N/A codes must be explicitly defined.** Do not collapse everything into a single special `junk_key` if you need to analyze **which specific flag is missing** while the remaining flags are known.

### 9.2. Why Did the SQL Example Use NOT NULL?

In Section 5, the three flag/code columns of the junk dimension were **`NOT NULL`** because the sample problem assumed complete, valid source inputs. When adding UNKNOWN, change the **domain model** rather than casually allowing SQL NULLs.

If any component of the combination allows **`NULL`**, a constraint like:

~~~sql
UNIQUE (is_gift_wrap, is_coupon_applied, fulfillment_mode)
~~~

under many PostgreSQL configurations may **not prevent rows containing NULLs from being treated as distinct rather than duplicates**, because NULL semantics differ from ordinary values. Similarly, JOIN predicates using **`=`** do not match two NULLs. While SQL offers explicit NULL-safe mechanisms, modeling **UNKNOWN/NOT_APPLICABLE with defined domain values** is usually easier to govern and explain in a junk dimension.

Never turn every missing value into an UNKNOWN label and ignore investigating source quality. Reports should track the **rate of unknown rows** and their root causes.

## 10. Historical Semantics: Flags at Placement Differ from Current Status

A junk dimension only stores value combinations; **when a combination holds true belongs to fact grain and load rules**.

For `fact_order_placed`:

~~~text
is_coupon_applied = TRUE
~~~

means **a coupon was applied when the order was placed**. If the order is refunded a month later, do not flip this flag to FALSE to turn it into “net coupon usage as of today,” because doing so alters historical fact and report definitions.

### 10.1. Mutable States Require an Appropriate Temporal Model

| Question | Suggested model |
| --- | --- |
| Which fulfillment method did the order choose at placement? | Snapshot flags/codes in **`fact_order_placed`** and junk dimension |
| What is the **current** delivery status? | Operational status table, accumulating snapshot, or current-state model with clear source and timestamp |
| Which delivery statuses has the order passed through? | Status event fact with **event timestamp** and event type |
| What did the system know about delivery as of Nov 20? | Fact/snapshot with recorded-at timestamps or history model supporting **as-of** queries |
| How many orders were refunded after placement? | Refund/adjustment fact or dedicated business event, not redefining placement flags |

**You do not necessarily need SCD Type 2 for every junk dimension.** A combination **`(TRUE, FALSE, SHIP)`** has stable semantics; if **`(TRUE, TRUE, SHIP)`** appears, you insert a **new combination row**. History here is primarily preserved by **the fact keeping the `junk_key` chosen when the event occurred**.

If the display label for SHIP changes from “Giao hàng” to “Giao tận nơi” while the code and meaning remain unchanged, you can update the label (per descriptive governance policy) without automatically creating historical combination versions. If the **business meaning of a code changes**, introduce a new code/version or historical mechanism; editing a label to mask a semantic change breaks historical reports.

### 10.2. Flag Changes from Data Corrections vs. Business State Changes

Suppose the source erroneously sent **`is_coupon_applied = FALSE`** for order O1003, when a coupon actually applied at confirmation. That is **correcting a misrecorded historical fact**. The process might:

1. Log a correction ticket with old and new values.
2. Locate the true combination in `dim_order_junk`; create it if absent.
3. Update the fact's **`junk_key`** per published restatement policy.
4. Retain an audit trail and trigger recalculation of affected summary/reconciliation tables.

Conversely, if a coupon is **reversed/refunded** after placement, model a proper reversal/adjustment event rather than converting “applied at placement” into “still active today.”

### 10.3. Beware When the Customer Dimension Is SCD Type 2

In our example, **`dim_customer`** is a simple dimension with one row per `customer_code`. If it later adopts SCD Type 2 to track which segment a customer belonged to **at order placement**, the table will hold multiple **`customer_key`** values per `customer_code`.

The fact must reference **the `customer_key` version valid at placement time**. Never JOIN a fact via `customer_code` to all versions and multiply order counts and revenue. That is a historical dimension concern **separate** from the junk dimension, yet very easy to misapply alongside it in a star schema.

## 11. Practical Trade-Offs: Is a Junk Dimension Always Better Than Flags on the Fact?

### 11.1. Key Benefits

- **Cleaner fact structure:** multiple flags collapse into one foreign key; helpful when facts are very wide or flags require shared governance.
- **Consistent classification:** reports share code names, labels, and permitted combinations.
- **Explicit observed combinations:** querying the dimension reveals which combinations occur and allows documenting them.
- **Convenient multi-condition grouping:** JOIN one small dimension to filter/group across flags and codes.
- **Source combination validation:** a dimension lookup catches unknown codes or invalid combinations from sources.

### 11.2. Costs and Limitations

- **Extra JOIN:** filtering a single flag may require a JOIN, depending on analytical engine optimization.
- **Multiplicative cardinality:** too many attributes in one junk dimension prevent the table from staying small.
- **ETL overhead:** must create/look up combinations, handle unknown codes, NULLs, late data, and duplicate keys.
- **Compression trade-off:** in columnar data warehouses, a few low-cardinality BOOLEAN/code columns often compress extremely well; replacing them with a `junk_key` **is not automatically smaller**.
- **Sargability/pruning:** flags directly on the fact sometimes aid predicate pushdown or partitioning; inspect real query plans.
- **Interpretability:** if report builders see only `junk_key` without the dimension or semantic layer, values are opaque.

| System condition | Consideration |
| --- | --- |
| Many low-cardinality flags, frequently analyzed together, modest actual combinations | Junk dimension may fit well |
| Only 1–2 flags, columnar engine optimizes well | Keeping flags directly on the fact is often enough |
| A code has important hierarchies and metadata | Create a dedicated dimension |
| Flags have different grains or effective timestamps | Do not group arbitrarily; separate by true fact/timing |
| Theoretical combination count is huge | Split into subject groups, drop attributes, or keep inline |
| Codes change with auditable history | Design appropriate SCD, event, or snapshot models first |

### 11.3. When to Split One Junk Dimension into Multiple Groups

Suppose a fact has 12 flags: 4 for **promotions**, 4 for **fulfillment**, and 4 for **payment risk**. Combining all into one table yields up to **2¹² = 4,096 combinations** if all are binary.

Consider splitting:

~~~text
dim_promotion_flags   : 4 flags -> max 16 combinations
dim_fulfillment_flags : 4 flags -> max 16 combinations
dim_risk_flags        : 4 flags -> max 16 combinations

fact:
    promotion_flags_key
    fulfillment_flags_key
    risk_flags_key
~~~

The theoretical maximum total dimension rows drops to **16 + 16 + 16 = 48**, instead of **4,096** in a single table; in exchange, the fact carries **three foreign keys** and some queries JOIN more tables.

This illustrates **subject-area grouping**, not proof that three tables are always optimal. Compare actual combination counts, key/column widths, user personas, and workloads. If risk flags only become meaningful after payment while promotion flags are recorded at placement, differing **effective timing** is an even stronger reason not to combine them.

### 11.4. Relationship to Normalization and Other Data Models

In **relational OLTP**, flags may live on the `orders` table or in specialized business relationships if they carry their own history/rules. You do not apply junk dimensions to redesign transactional tables.

In **analytical star schemas**, a junk dimension aims to **organize classification filters and slim descriptive columns on facts**, not fulfill a mandatory 3NF normalization step. Treat it as **a structural choice serving querying and dimension governance**.

In **document databases**, an order-placed event can embed flags and codes directly inside the document; there is no reason to build a relational-star “junk dimension” unless workloads require it. In **graph databases**, flags can be node/edge properties or separate relationships depending on the domain; grain and effective timing still apply.

Regardless of storage model, **business definitions must stay consistent**: “coupon applied” must not mean different things across transactional sources, analytical tables, and dashboards.

## 12. Data Quality and Performance Testing

### 12.1. Verify Every Dimension Combination Is Unique

In our sample schema, the **`UNIQUE`** constraint blocks duplicates. If loading from legacy files or reconciling, check:

~~~sql
SELECT
    is_gift_wrap,
    is_coupon_applied,
    fulfillment_mode,
    COUNT(*) AS duplicate_count
FROM dim_order_junk
GROUP BY is_gift_wrap, is_coupon_applied, fulfillment_mode
HAVING COUNT(*) > 1;
~~~

This query must return zero rows. If two `junk_key` values exist for the same combination, reports grouping by flags might still sum correctly, yet the dimension is no longer one-to-one, making incremental loads and surrogate-key queries error-prone.

### 12.2. Verify No Fact Points to a Missing Dimension Row

With **`FOREIGN KEY`** enforcement enabled, facts cannot reference a nonexistent `junk_key`. If ETL disables constraints during bulk loads or queries external sources without FKs, check:

~~~sql
SELECT f.order_number, f.junk_key
FROM fact_order_placed AS f
LEFT JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key
WHERE junk.junk_key IS NULL;
~~~

This query must return empty. In warehouses adopting a valid **UNKNOWN** row policy, pointing to the UNKNOWN `junk_key` is not a referential error; instead, monitor the UNKNOWN rate and assignment logic.

### 12.3. Verify Order Counts Before and After JOIN

~~~sql
SELECT COUNT(*) AS fact_count
FROM fact_order_placed;

SELECT COUNT(*) AS joined_count
FROM fact_order_placed AS f
JOIN dim_order_junk AS junk
  ON junk.junk_key = f.junk_key;
~~~

On the initial sample data, both equal **6**. After the Section 8 load, both equal **8**. Matching counts are a useful sanity check yet **insufficient** to prove each order's flags mapped accurately: reconcile individual orders against source combinations, especially when edits can occur.

### 12.4. Filtering by Dimension and Indexing

PostgreSQL can use the fact's foreign key to JOIN to the junk dimension; `dim_order_junk`'s primary key is already indexed. If queries frequently filter/group by `junk_key` on a huge fact table, consider:

~~~sql
CREATE INDEX idx_fact_order_placed_junk_date
ON fact_order_placed (junk_key, date_key);
~~~

This is a **suggestion**, not a universal rule. Check `junk_key` selectivity, fact row count, engine type, storage format, statistics, partitioning, write overhead of indexes, and actual query plans. A dimension with only a few combinations can have **low selectivity**, making a full scan or another strategy better than a B-tree index.

In columnar stores or cloud data warehouses, compression, clustering, partition pruning, and JOIN execution differ from PostgreSQL OLTP. Never claim a junk dimension saves space or speeds up queries without benchmarking.

### 12.5. Minimum Pipeline Tests

| Scenario | Expected result |
| --- | --- |
| Load two new orders sharing an unseen combination | Creates **one** new junk row; both facts point to it |
| Reload the same `order_number` | No duplicate fact row created; update/skip behavior matches policy |
| Receive `fulfillment_mode` outside SHIP/PICKUP | Rejected or routed to standardization/UNKNOWN per policy |
| Source omits coupon flag | Not silently coerced to FALSE if unconfirmed |
| Concurrent loads encounter same new combination | Only one row created thanks to `UNIQUE` |
| Source sends business-invalid combination | Clear quality error raised; no silent junk row created |
| Order status changes after placement | Historical snapshot flags remain unchanged unless true correction |
| JOIN fact to dimension | No valid fact rows duplicated or dropped |

## 13. Decision Workflow for Using a Junk Dimension

1. **Define reporting questions and fact grain:** does one row represent an order, order line, payment event, or daily snapshot?
2. **Build a flag/code dictionary:** what do TRUE/FALSE mean, are UNKNOWN/N/A needed, and at what timestamp do they apply?
3. **Exclude unfit candidates:** high-cardinality IDs, measures, attributes with rich hierarchies, and statuses at other grains.
4. **Estimate theoretical and actual cardinality:** how many combinations are possible, valid, and observed?
5. **Group logically:** if one dimension grows too large or mixes different timestamps, split by subject area.
6. **Choose load strategy:** prepopulate vs. insert-on-demand, surrogate key generation, deduplication, and unknown-code checks.
7. **Design constraints:** `UNIQUE` on the combination tuple, explicit `NOT NULL`/UNKNOWN codes, FKs from the fact, and invalid-combination guards.
8. **Define historical semantics:** keep snapshot flags on the fact, and specify how status changes and historical corrections work.
9. **Validate metrics:** order counts, merchandise totals, flagged order counts, and time breakdowns suffer zero duplication.
10. **Benchmark performance and operational cost:** compare against keeping flags directly on the fact or using multiple small dimensions.

### 13.1. A Pragmatic Rule of Thumb

Whenever a flag definition, code, or member in the group needs to change, ask:

> Does this change force redesigning the fact grain, rewriting historical data, or altering relationships with other business entities?

If **yes**, it is likely no longer a “small flag” suitable for a junk dimension. For example, once coupon tracking evolves from **applied or not** into analyzing **multiple coupons, application order, and discount amount per coupon**, you need a bridge/detail relationship or dedicated promotion fact rather than stuffing coupon codes into a junk dimension.

## 14. Applied Exercises

### Exercise 1 — Counting Combinations and Grouping

An order fact has four classification attributes: **`is_gift_wrap`** (2 values), **`is_coupon_applied`** (2 values), **`customer_order_type`** (3 values: FIRST, REPEAT, UNKNOWN), and **`fulfillment_mode`** (2 values).

**Tasks:**

1. Compute the maximum theoretical combinations.
2. If business rules forbid gift wrapping on PICKUP orders, how many maximum valid combinations remain?
3. Is it mandatory to prepopulate every valid combination?
4. Why can't seeing only 5 combinations in source data guarantee a sixth combination will never occur?

<details>
<summary>Suggested solution for Exercise 1</summary>

Theoretical combinations: **2 × 2 × 3 × 2 = 24**.

For each `(coupon, customer_order_type)` pair there are **2 × 3 = 6** choices. Under **SHIP**, `gift_wrap` has 2 choices, giving **12** combinations. Under **PICKUP**, `gift_wrap` can only be FALSE, giving **6** combinations. Maximum valid total is **18 combinations**, assuming no extra restrictions.

You can prepopulate all 18 when small and stable, or load observed combinations via insert-on-demand. Five observed combinations only describe data seen so far, not a proof that other valid combinations will never occur.

</details>

### Exercise 2 — Reading Metrics Accurately from Sample Data

Use the six orders **O1001–O1006** from Section 5.

**Tasks:**

1. Count orders with gift wrap.
2. Count orders with an applied coupon and sum their merchandise total.
3. Count orders with at least one of the two flags TRUE.
4. Count SHIP orders and sum their merchandise total.
5. Explain why gift-wrap order count plus coupon order count can exceed the union of the two sets.

<details>
<summary>Suggested solution for Exercise 2</summary>

- Gift wrap: **2 orders** (O1002, O1004).
- Coupon applied: **2 orders** (O1003, O1004), merchandise total **470,000 VND**.
- At least one flag TRUE: **3 orders** (O1002, O1003, O1004).
- SHIP: **4 orders**, merchandise total **850,000 VND**.
- O1004 has **both gift wrap and a coupon**, so adding the two group counts without subtracting the overlap double-counts O1004. Formula: **|A ∪ B| = |A| + |B| − |A ∩ B| = 2 + 2 − 1 = 3**.

</details>

### Exercise 3 — Missing Flags in Source Data

A batch contains:

~~~text
order | gift_wrap | coupon_applied | fulfillment
------+-----------+----------------+------------
O2001 | FALSE     | FALSE          | SHIP
O2002 | TRUE      | UNKNOWN        | SHIP
O2003 | FALSE     | TRUE           | PICKUP
O2004 | FALSE     | NOT_APPLICABLE | PICKUP
~~~

**Tasks:**

1. Why shouldn't UNKNOWN be converted to FALSE?
2. To load all four orders, how must the junk dimension model in Section 5 change?
3. For a “coupon usage rate” report, how should UNKNOWN and NOT_APPLICABLE be treated in the denominator?

<details>
<summary>Suggested solution for Exercise 3</summary>

**UNKNOWN** means we do not know whether a coupon was applied, whereas **FALSE** confirms no coupon was applied. Arbitrary conversion skews results.

Replace the coupon BOOLEAN column with **`coupon_state`** having domain **`YES, NO, UNKNOWN, NOT_APPLICABLE`**, keeping `NOT NULL` and `UNIQUE` across all combination columns; alternatively, enforce a quarantine policy for incomplete rows.

The denominator must be **defined by the business**. For instance, if measuring the rate among orders **eligible for coupons with known outcomes**, exclude **UNKNOWN** and **NOT_APPLICABLE** from the denominator and report the excluded count. If measuring across **all placed orders**, you may need range bounds or known-data rates accompanied by coverage metrics. No single formula exists until the metric definition is confirmed.

</details>

### Exercise 4 — Wrong Grain Breaks Counts

A line-item fact contains:

~~~text
order_number | line_no | is_gift_wrap
-------------+---------+-------------
O3001        | 1       | TRUE
O3001        | 2       | TRUE
O3001        | 3       | TRUE
O3002        | 1       | FALSE
~~~

Here the flag belongs to the **order**, yet was repeated onto each line for query convenience.

**Tasks:** What does **`COUNT(*)`** return after filtering `is_gift_wrap = TRUE`? How many actual gift-wrapped **orders** exist? How should the query or model change?

<details>
<summary>Suggested solution for Exercise 4</summary>

**`COUNT(*)` = 3 lines**, whereas there is only **1 gift-wrapped order** (`O3001`). If the data remains at line grain, you can write:

~~~sql
SELECT COUNT(DISTINCT order_number)
FROM fact_order_line
WHERE is_gift_wrap = TRUE;
~~~

A cleaner-grain modeling solution is using **`fact_order_placed`** at order level and attaching the order-level `junk_key` there, while `fact_order_line` serves line-level quantities and amounts. If you intentionally repeat order flags onto a line fact, guarantee all lines of an order share the same value and always match counts to the question's grain.

</details>

### Exercise 5 — New Combinations and Duplicate Loads

The dimension has the five combinations from Section 5. Two new orders **O1007** and **O1008** both have **(FALSE, TRUE, SHIP)**.

**Tasks:**

1. How many new rows are needed in the junk dimension to load both orders?
2. What happens if two jobs detect the new combination simultaneously and both try to insert a row?
3. Which constraint ensures one combination never maps to two `junk_key` values?
4. Should the new key be calculated via **`MAX(junk_key) + 1`**?

**Guidance:** only **one new dimension row** is needed. **`UNIQUE(is_gift_wrap, is_coupon_applied, fulfillment_mode)`** protects against concurrent duplicate inserts; ETL can use an appropriate upsert/`ON CONFLICT`. Never use `MAX + 1` because two transactions can compute the same value and collide; use the database's ID/sequence generator and look up the key by tuple values.

### Exercise 6 — Correcting a Finalized Fact

O1004 had **`coupon_applied = TRUE`** at placement. Two weeks later, the order was refunded. The reporting team proposes updating the coupon flag to FALSE on `fact_order_placed` so it “no longer counts as a coupon order.”

**Task:** propose a modeling approach that preserves the truth at placement while supporting “net coupon value after refunds” reports.

**Guidance:** preserve **`coupon_applied_at_order = TRUE`** on the placement event. Record refund/adjustment events with timestamp, amount, reason, and order reference. Derive **net value** metrics from the base facts per company policy rather than overwriting the nature of the placement event. If the source genuinely misrecorded placement data initially, that is an audited **historical restatement**, distinct from a subsequent refund.

## 15. Common Misconceptions

| Misconception | Correct understanding |
| --- | --- |
| “A junk dimension holds worthless data.” | It holds **low-cardinality flags and codes that carry real analytical value**. |
| “Every BOOLEAN must go into a junk dimension.” | Weigh flag count, grain, timing, workload, and JOIN cost. |
| “All theoretical combinations must exist in the dimension.” | Only valid combinations are needed under prepopulate or insert-on-demand policies. |
| “Flags in a junk dimension must be independent.” | Not required; govern **valid combinations**, including inter-flag constraints. |
| “`junk_key = 4` always means coupon is TRUE.” | Surrogate keys **carry no global meaning**; always JOIN to the dimension. |
| “UNKNOWN and FALSE both mean no coupon.” | UNKNOWN means **undetermined**, FALSE means confirmed negative. |
| “When order status changes, update all placement flags.” | Snapshot flags belong to placement time; later events have their own grain and timing. |
| “Changing a label requires SCD Type 2.” | Rewording a label with unchanged meaning can be a descriptive update; semantic changes need a history policy. |
| “Joining a junk dimension multiplies order counts.” | With `junk_key` as PK, each fact matches one dimension row; fan-out comes from wrong JOINs or duplicate data. |
| “A junk dimension always saves storage.” | Columnar engines often compress inline flags very well; benchmark first. |
| “If a code gains many values, just expand the junk.” | Metadata-rich or high-cardinality codes may need a dedicated dimension. |
| “`COUNT(*)` on a line fact gives order count.” | `COUNT(*)` counts **rows at the fact's grain**; order counts require matching models or metrics. |

## 16. Key Takeaways

A **junk dimension** groups low-cardinality flags and codes sharing **the same grain and point-in-time semantics** into a dimension of **classification combinations**. Each fact references its combination through one **surrogate key**. This works well when a fact has many small classification attributes, needs consistent label governance, and has a manageable observed combination count.

When designing one, **lock down grain first**, clarify TRUE/FALSE/UNKNOWN/N/A meanings, estimate cardinality via the **product of value domains**, enforce **`UNIQUE` on the combination**, look up keys by attributes rather than guessing IDs, and verify JOINs neither duplicate nor drop rows. Transaction-time snapshot flags **must not be mutated into current status** by later updates.

Not every flag belongs here: attribute-rich dimensions, high-cardinality IDs, measures, differently timed states, or too many flags will distort semantics or add complexity. A well-built junk dimension comes from **clear business definitions → sound flag selection → clean combination and key design → verified data loading → measured query and operational costs**.
