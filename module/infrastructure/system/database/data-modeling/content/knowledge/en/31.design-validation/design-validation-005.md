# Testing the Correctness of Joins, Aggregations, and Temporal History

A SQL query can execute successfully, return plausible-looking data, and still be **business-incorrect**. When an order has multiple lines, a customer has multiple historical versions, or a payment consists of multiple events, a **JOIN** with an improper key can multiply fact rows. Subsequent **SUM**, **COUNT**, and **COUNT(DISTINCT)** calculations then produce numbers that look valid but no longer reflect what actually happened. With respect to time, a record can be attributed to the customer's **current** segment instead of the segment **at the time of the transaction**.

**Design validation** does not stop at verifying that DDL is valid, foreign keys exist, or queries return results. We must test **invariants of grain, cardinality, identity, relationships, measure additivity, and temporal semantics** using purposeful sample data, reconciliation queries, and counterexamples.

This lesson belongs to the **Design Validation** chapter of the **DATABASE_DATA_MODELING** module. Its goal is to build the ability to turn business requirements into a **testable data contract**, from keys and relationships in a relational model to facts/dimensions, historical data, and analytical schemas—while also recognizing when a document, graph, or other analytical system requires equivalent invariants.

## 1. At What Level Is Correctness Measured?

A query can be "correct" at the syntax level yet "wrong" at every other level.

| Validation Level | Question | Counterexample |
| --- | --- | --- |
| **Syntax and types** | Does the SQL run and are data types compatible? | SQL runs, but the date column is cast using the server timezone |
| **Grain and keys** | What does one row represent, and can it duplicate? | An order line is doubled when joined to payments |
| **Join cardinality** | How many right-hand rows may each left-hand row match? | Joining a fact to two dimension versions of the same customer |
| **Completeness** | Are rows dropped by an INNER JOIN or filter? | Orders with unmapped customer codes are excluded from the report |
| **Measures and aggregations** | Are we summing the right measure type at the right grain? | Summing end-of-day balances across multiple days |
| **Business time (valid time)** | Which attribute value applies, and when was it in effect? | Past transactions are attributed to a newly assigned department |
| **System knowledge time** | Can an as-of report reproduce a previously published version? | Late-arriving data silently alters historical reports without versioning |
| **Operational reliability** | Do reruns, backfills, and schema changes preserve invariants? | A consumer ingests a duplicate event during a retry |

A very useful validation rule:

> **State in plain words what a single row represents, then turn that statement into keys, constraints, test queries, and expected results.**

Without clearly stating the grain, any calculation after a JOIN—no matter how well optimized—is hard to prove correct.

### 1.1. Example of the Same Figure Counted Different Ways

An order **O1001** has two order lines and two payments. There are at least three valid counts:

- **Number of order lines:** 2.
- **Number of distinct orders:** 1.
- **Number of payment events:** 2.

If you JOIN order lines with payment events on `order_id` and use `COUNT(*)`, the result can become **4**. That is neither the number of order lines, nor the number of orders, nor the number of payments; it is the **number of line–payment pairs produced by the join**.

### 1.2. Four Deliverables Required in a Validation Suite

1. **Data contract:** grain, keys, source, filter conditions, measure definitions, timezone, and validity intervals.
2. **Fixture:** a small dataset covering normal cases, many-to-many cases, time boundaries, orphans, and late-arriving data.
3. **Assertions:** queries that return an empty discrepancy set or raise errors with specific messages.
4. **Reconciliation:** comparing key sets, row counts, monetary amounts, and groups between the authoritative source and derived outputs.

A few tests returning PASS on clean data are not enough; there must be **negative tests** proving that each check catches the exact class of bugs it was designed to detect.

## 2. Grain, Key, and Measure Contracts Before Writing a JOIN

### 2.1. Every Table Must Have a Grain Statement

Throughout our examples, we use three tables:

| Table | Grain | Key | Role |
| --- | --- | --- | --- |
| **fact_order_line** | One line item of a finalized order | line_id | Quantity, line amount |
| **payment_event** | One recorded payment event | payment_id | Paid amount |
| **dim_customer_history** | One customer classification version valid over a time interval | customer_sk | Historical dimension (SCD Type 2) |

In a multi-tenant system, the pair **(tenant_id, customer_code)** is the business customer identifier in this example; **customer_sk** is the surrogate key of a *historical version*. The system must never conflate a customer with a single version of that customer.

### 2.2. Specifying Measures to Avoid "Summing Everything"

| Measure or Attribute | Base Grain | Valid Aggregation | Common Mistake |
| --- | --- | --- | --- |
| **line_amount_vnd** | One order line | SUM across eligible lines | Joining to payment_event multiplies rows |
| **quantity** | One order line | SUM if units/products share the same meaning | Summing incompatible units without conversion |
| **paid_vnd** | One payment event | SUM over valid payment events | Summing after joining multiple order lines |
| **order count** | Order with at least one valid line | COUNT DISTINCT order key within scope | COUNT(*) on a line-grain fact table |
| **unique customer count** | Business customer | COUNT DISTINCT proper tenant–customer key | Summing daily customer counts across multiple days |
| **end-of-day balance** | Account at a snapshot point | Summing across accounts at the same timestamp may be valid | SUMming balances over time |
| **conversion rate** | Numerator/denominator over target population | Sum numerators and sum denominators, then divide | Unweighted average of group rates with different sizes |

An **additive measure** such as order-line amount can be summed across independent dimensions compatible with its grain. A **semi-additive measure** such as an account balance can be summed across certain dimensions (accounts at the same point in time), but not across time. A **non-additive measure** such as a ratio usually must be recomputed from its numerator and denominator.

### 2.3. Aligning on the Eligible Population

Two reports can diverge if one includes **successfully placed orders**, another includes **paid orders**, or one excludes refunded orders. Before reconciling, confirm:

- Which transaction statuses are included?
- Are cancelled, test, or refunded records included?
- Is the metric gross amount, post-discount amount, or net amount?
- Order date, payment date, or accounting posting date?
- Currency unit and conversion policy?
- Data ingestion cutoff (**cutoff/watermark**) and formula version?

An arithmetic reconciliation between two **different business definitions** does not prove a design is wrong; it proves we have not yet agreed on what is being compared.

## 3. Self-Contained PostgreSQL Dataset

The examples use PostgreSQL and fixed records to illustrate validation queries. The queries below are presented so learners can run them in **an empty practice schema**; they do not execute automatically while reading the lesson. To avoid depending on the SQL session timezone, all timestamps in the fixture carry an explicit **+07** offset, and reports explicitly use **Asia/Ho_Chi_Minh**.

### 3.1. DDL

~~~sql
CREATE TABLE dim_customer_history (
    customer_sk BIGINT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    customer_code TEXT NOT NULL,
    department TEXT NOT NULL,
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE TABLE fact_order_line (
    line_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    customer_code TEXT NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    line_amount_vnd NUMERIC(20, 0) NOT NULL
        CHECK (line_amount_vnd >= 0)
);

CREATE TABLE payment_event (
    payment_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL,
    order_id TEXT NOT NULL,
    paid_at TIMESTAMPTZ NOT NULL,
    paid_vnd NUMERIC(20, 0) NOT NULL CHECK (paid_vnd > 0)
);

CREATE INDEX idx_order_line_tenant_order
    ON fact_order_line (tenant_id, order_id);

CREATE INDEX idx_payment_tenant_order
    ON payment_event (tenant_id, order_id);

CREATE INDEX idx_customer_history_lookup
    ON dim_customer_history (
        tenant_id, customer_code, valid_from
    );
~~~

**Intentional DDL limitation:** the key on **dim_customer_history** ensures each `customer_sk` version is unique and each interval is properly ordered, but it **does not yet prevent two versions of the same `customer_code` from having overlapping validity intervals**. That will be a key invariant to test; a later section introduces a stronger constraint.

### 3.2. Loading a Dimension with Department Changes Over Time

~~~sql
INSERT INTO dim_customer_history (
    customer_sk, tenant_id, customer_code,
    department, valid_from, valid_to
) VALUES
    (101, 'T01', 'C01', 'North',
     TIMESTAMPTZ '2026-01-01 00:00:00+07',
     TIMESTAMPTZ '2026-11-20 00:00:00+07'),
    (102, 'T01', 'C01', 'South',
     TIMESTAMPTZ '2026-11-20 00:00:00+07',
     NULL),
    (103, 'T01', 'C02', 'North',
     TIMESTAMPTZ '2026-01-01 00:00:00+07',
     NULL),
    (104, 'T02', 'C03', 'South',
     TIMESTAMPTZ '2026-01-01 00:00:00+07',
     NULL);
~~~

Customer **T01/C01** moved from **North** to **South** at the exact start of **2026-11-20 in Vietnam time**. Validity interval convention:

\[
[\text{valid\_from}, \text{valid\_to})
\]

This means **inclusive of the start boundary, exclusive of the end boundary**; **valid_to = NULL** means no end time has been recorded yet.

### 3.3. Loading Six Order Lines Across Five Orders

~~~sql
INSERT INTO fact_order_line (
    line_id, tenant_id, order_id, customer_code,
    placed_at, quantity, line_amount_vnd
) VALUES
    ('L01', 'T01', 'O1001', 'C01',
     TIMESTAMPTZ '2026-11-19 10:00:00+07', 1, 100000),
    ('L02', 'T01', 'O1001', 'C01',
     TIMESTAMPTZ '2026-11-19 10:00:00+07', 2, 200000),
    ('L03', 'T01', 'O1002', 'C01',
     TIMESTAMPTZ '2026-11-20 09:00:00+07', 3, 300000),
    ('L04', 'T01', 'O1003', 'C02',
     TIMESTAMPTZ '2026-11-20 12:00:00+07', 1, 150000),
    ('L05', 'T02', 'O1004', 'C03',
     TIMESTAMPTZ '2026-11-21 00:30:00+07', 5, 250000),
    ('L06', 'T01', 'O1005', 'C01',
     TIMESTAMPTZ '2026-11-21 16:00:00+07', 2, 100000);
~~~

### 3.4. Loading Six Payment Events

~~~sql
INSERT INTO payment_event (
    payment_id, tenant_id, order_id, paid_at, paid_vnd
) VALUES
    ('P01', 'T01', 'O1001',
     TIMESTAMPTZ '2026-11-19 10:05:00+07', 200000),
    ('P02', 'T01', 'O1001',
     TIMESTAMPTZ '2026-11-19 10:06:00+07', 100000),
    ('P03', 'T01', 'O1002',
     TIMESTAMPTZ '2026-11-20 09:05:00+07', 300000),
    ('P04', 'T01', 'O1003',
     TIMESTAMPTZ '2026-11-20 12:05:00+07', 150000),
    ('P05', 'T02', 'O1004',
     TIMESTAMPTZ '2026-11-21 00:35:00+07', 250000),
    ('P06', 'T01', 'O1005',
     TIMESTAMPTZ '2026-11-21 16:05:00+07', 100000);
~~~

Order O1001 has **two order lines and two payment events**, intentionally created to test the case where a JOIN produces a **Cartesian product within a single order**.

### 3.5. Reference Oracle Figures

| Metric on Source Data | Expected Result |
| --- | ---: |
| Order lines | 6 |
| Distinct orders by (tenant_id, order_id) | 5 |
| Distinct business customers by (tenant_id, customer_code) | 3 |
| Payment events | 6 |
| Total line_amount_vnd | 1,100,000 |
| Total paid_vnd | 1,100,000 |

~~~sql
SELECT COUNT(*) AS lines,
       SUM(line_amount_vnd) AS sales_vnd,
       SUM(quantity) AS units
FROM fact_order_line;
-- lines = 6; sales_vnd = 1100000; units = 14.

SELECT COUNT(*) AS payments, SUM(paid_vnd) AS paid_vnd
FROM payment_event;
-- payments = 6; paid_vnd = 1100000.
~~~

These source figures are the **oracle for this fixture**; in real-world systems, total sales do not always equal total payments. In production systems, paid amounts can differ due to holds, taxes, fees, partial payments, refunds, and transaction statuses.

## 4. Testing JOIN Cardinality and Completeness

### 4.1. JOIN Outcomes Depend on Key Relationships

| Expected Relationship | Example | Validation Check |
| --- | --- | --- |
| 1–1 | One source order ↔ one summary order row | Each left key has exactly one match on the right |
| N–1 | Many order lines ↔ one point-in-time dimension version | Each line matches **exactly one** dimension row |
| 1–N | One order ↔ many order lines | Row multiplication is acceptable if the question is about **lines** |
| N–M | Order lines ↔ payment events on the same order | Do not sum measures at both grains directly after JOIN |
| 0–1 or 0–N | Optional data | Requires an explicit policy for unmatched rows |

A common mistake is assuming a JOIN on identically named columns is **N–1**, when the dimension side actually has multiple versions or the payment side has multiple events.

### 4.2. Incorrect JOIN with an SCD: Omitting the Time Condition

~~~sql
-- ANTI-PATTERN: do not use to calculate revenue.
SELECT
    COUNT(*) AS joined_rows,
    SUM(f.line_amount_vnd) AS joined_amount_vnd
FROM fact_order_line AS f
JOIN dim_customer_history AS c
  ON c.tenant_id = f.tenant_id
 AND c.customer_code = f.customer_code;
~~~

The fixture returns **10 rows** and **1,800,000 VND**, instead of 6 rows and 1,100,000 VND. Each of T01/C01's four lines matches **two historical versions**, inflating the total by **700,000 VND**.

This is a **fanout** bug: a single fact row is multiplied into multiple rows because the JOIN condition is not unique under the intended semantics.

### 4.3. Correct JOIN by Effective Timestamp

~~~sql
SELECT
    f.line_id,
    f.tenant_id,
    f.customer_code,
    f.line_amount_vnd,
    c.customer_sk,
    c.department
FROM fact_order_line AS f
JOIN dim_customer_history AS c
  ON c.tenant_id = f.tenant_id
 AND c.customer_code = f.customer_code
 AND f.placed_at >= c.valid_from
 AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
ORDER BY f.line_id;
~~~

Row-by-row result:

| line_id | customer_sk | department | line_amount_vnd |
| --- | ---: | --- | ---: |
| L01 | 101 | North | 100000 |
| L02 | 101 | North | 200000 |
| L03 | 102 | South | 300000 |
| L04 | 103 | North | 150000 |
| L05 | 104 | South | 250000 |
| L06 | 102 | South | 100000 |

After the correct JOIN, the total must still be **1,100,000 VND**. However, **two SUMs matching once does not prove general correctness**, because one row could be dropped while another row of the same value is duplicated. We must test **uniqueness by `line_id`** and **the existence of every match**.

### 4.4. Test: "Each Fact Matches Exactly One Dimension Row"

~~~sql
WITH matches AS (
    SELECT
        f.line_id,
        COUNT(c.customer_sk) AS match_count
    FROM fact_order_line AS f
    LEFT JOIN dim_customer_history AS c
      ON c.tenant_id = f.tenant_id
     AND c.customer_code = f.customer_code
     AND f.placed_at >= c.valid_from
     AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
    GROUP BY f.line_id
)
SELECT line_id, match_count
FROM matches
WHERE match_count <> 1
ORDER BY line_id;
~~~

**Expected passing result: empty set.** It distinguishes:

- **match_count = 0:** the dimension has no valid version at that time, data is missing, or timestamps are wrong.
- **match_count > 1:** validity intervals overlap, join keys are incomplete, or versions are duplicated.

This test is stronger than a standalone SUM check because it validates at the **exact fact-line grain**. If `line_id` is only unique within a tenant, you must `GROUP BY` both `tenant_id` and `line_id`.

### 4.5. Testing for Dropped Rows When Using INNER JOIN

In a streaming or incremental ingestion pipeline, facts may arrive before dimensions. An **INNER JOIN** silently drops unmapped rows, lowering revenue without raising any SQL error.

~~~sql
SELECT
    f.line_id,
    f.tenant_id,
    f.customer_code,
    f.placed_at
FROM fact_order_line AS f
WHERE NOT EXISTS (
    SELECT 1
    FROM dim_customer_history AS c
    WHERE c.tenant_id = f.tenant_id
      AND c.customer_code = f.customer_code
      AND f.placed_at >= c.valid_from
      AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
);
~~~

On the sample data, the result is empty. In production data, **no match** can result from an unknown customer code, a late-arriving dimension, a gap in validity intervals, or an incorrect timestamp. The handling policy depends on business rules: **quarantine**, late-arriving dimension handling, an explicitly governed **Unknown** row, or waiting for reload. You must never treat rows silently dropped by an INNER JOIN as "not needing to be counted" if business requirements say they belong in the total.

Try intentionally inserting an unmatched line, then rolling back:

~~~sql
BEGIN;

INSERT INTO fact_order_line (
    line_id, tenant_id, order_id, customer_code,
    placed_at, quantity, line_amount_vnd
) VALUES (
    'L_BAD', 'T01', 'O_BAD', 'C99',
    TIMESTAMPTZ '2026-11-21 12:00:00+07', 1, 90000
);

-- Re-run the NOT EXISTS query above:
-- it must detect L_BAD.

ROLLBACK;
~~~

This is a **negative test**: we intentionally inject a fault to verify that the validation check actually catches it. This differs from running tests only against perpetually clean datasets.

### 4.6. Testing That JOIN Keys Include Tenant Scope

In a multi-tenant system, **customer_code = C01** can exist in two different tenants. If a JOIN matches only on `customer_code`, a fact from tenant T01 can join to a dimension row from tenant T02. Therefore, the condition must include **tenant_id** whenever customer codes are only unique per tenant.

Similarly, the order line ↔ payment event join in this example must use **(tenant_id, order_id)**, not `order_id` alone, if the business does not guarantee globally unique `order_id` values.

For sensitive data, a cross-tenant JOIN bug both corrupts reports and creates a **cross-tenant data leak**. Beyond checking row counts and totals, tests should include a fixture that intentionally reuses the same business code across two tenants and verify that results never bleed across tenants.

## 5. Joining Multiple Facts at Different Grains: Dangerous Fanout

### 5.1. Counterexample with Order Lines and Payment Events

~~~sql
-- ANTI-PATTERN: two 1-N sets joined directly at order level.
SELECT
    COUNT(*) AS joined_rows,
    SUM(l.line_amount_vnd) AS inflated_sales_vnd,
    SUM(p.paid_vnd) AS inflated_payments_vnd
FROM fact_order_line AS l
JOIN payment_event AS p
  ON p.tenant_id = l.tenant_id
 AND p.order_id = l.order_id;
~~~

The fixture returns **8 rows**, not 6; both the line-amount total and payment total become **1,400,000 VND**, wrong compared to the two independent source totals of **1,100,000 VND**.

Why? For order O1001:

~~~text
Order lines: L01 = 100,000; L02 = 200,000
Payments:    P01 = 200,000; P02 = 100,000

After JOIN on order:
  (L01, P01)
  (L01, P02)
  (L02, P01)
  (L02, P02)

SUM(line_amount) for O1001 = 600,000 (true value is 300,000)
SUM(paid_vnd) for O1001    = 600,000 (true value is 300,000)
~~~

A report that coincidentally shows **sales_vnd = payments_vnd = 1,400,000** will look "balanced," yet **both sides are doubled**. Two wrong numbers being equal **does not prove the model is correct**.

### 5.2. Correct Pattern: Aggregate Each Fact to the Same Grain Before Joining

When comparing order-line amounts and payment amounts **per order**, bring both sources to **(tenant_id, order_id)** first:

~~~sql
WITH line_totals AS (
    SELECT
        tenant_id,
        order_id,
        COUNT(*) AS line_count,
        SUM(line_amount_vnd) AS line_total_vnd
    FROM fact_order_line
    GROUP BY tenant_id, order_id
),
payment_totals AS (
    SELECT
        tenant_id,
        order_id,
        COUNT(*) AS payment_count,
        SUM(paid_vnd) AS paid_total_vnd
    FROM payment_event
    GROUP BY tenant_id, order_id
)
SELECT
    l.tenant_id,
    l.order_id,
    l.line_count,
    l.line_total_vnd,
    COALESCE(p.payment_count, 0) AS payment_count,
    COALESCE(p.paid_total_vnd, 0) AS paid_total_vnd
FROM line_totals AS l
LEFT JOIN payment_totals AS p
  ON p.tenant_id = l.tenant_id
 AND p.order_id = l.order_id
ORDER BY l.tenant_id, l.order_id;
~~~

Result:

| order_id | line_count | line_total_vnd | payment_count | paid_total_vnd |
| --- | ---: | ---: | ---: | ---: |
| O1001 | 2 | 300000 | 2 | 300000 |
| O1002 | 1 | 300000 | 1 | 300000 |
| O1003 | 1 | 150000 | 1 | 150000 |
| O1004 | 1 | 250000 | 1 | 250000 |
| O1005 | 1 | 100000 | 1 | 100000 |

**COALESCE(paid_total_vnd, 0)** is meaningful only if policy confirms that **"no payment events in a complete source"** should be represented as 0 paid. If payment data has not finished syncing yet, 0 can be misleading; in that case, use a separate **unknown/unsynced** status.

### 5.3. Testing for Payments Without a Matching Order

A LEFT JOIN from orders to payments cannot detect a **payment-only order**. Check for it separately:

~~~sql
SELECT DISTINCT p.tenant_id, p.order_id
FROM payment_event AS p
WHERE NOT EXISTS (
    SELECT 1
    FROM fact_order_line AS l
    WHERE l.tenant_id = p.tenant_id
      AND l.order_id = p.order_id
);
~~~

On the fixture, the query returns no rows. If rows appear, you must distinguish between **true orphans**, **late-arriving order data**, or **unattached payments** permitted by business rules. Do not blindly force all orphans into errors without checking business exceptions.

### 5.4. Testing Row Counts Before and After Each Join

When an **N–1** JOIN is expected, a necessary condition is:

\[
\text{count(join result)} = \text{count(left input)}
\]

and each left-hand key must have **exactly one** match. However, when a 1–N JOIN is intentional (one order expanding to multiple lines), an increasing row count is expected. Therefore, you must validate **the exact cardinality allowed by the contract**; there is no universal rule that "every JOIN must preserve row count."

A diagnostic query for chained JOIN stages:

~~~sql
WITH stage AS (
    SELECT '01_fact' AS stage_name, COUNT(*) AS row_count
    FROM fact_order_line

    UNION ALL

    SELECT '02_temporal_customer', COUNT(*)
    FROM fact_order_line AS l
    JOIN dim_customer_history AS c
      ON c.tenant_id = l.tenant_id
     AND c.customer_code = l.customer_code
     AND l.placed_at >= c.valid_from
     AND (l.placed_at < c.valid_to OR c.valid_to IS NULL)

    UNION ALL

    SELECT '03_naive_payment_join', COUNT(*)
    FROM fact_order_line AS l
    JOIN payment_event AS p
      ON p.tenant_id = l.tenant_id
     AND p.order_id = l.order_id
)
SELECT * FROM stage ORDER BY stage_name;
~~~

The results are **6**, **6**, and **8** respectively. This table is a *debugging* tool, not a sufficient correctness test; you still need to check **row-level keys** and **measures**.

### 5.5. Using EXISTS When Only Existence Matters

If the question is "order lines belonging to orders that **have at least one payment**," there is no need to JOIN individual payment events:

~~~sql
SELECT
    l.line_id,
    l.tenant_id,
    l.order_id,
    l.line_amount_vnd
FROM fact_order_line AS l
WHERE EXISTS (
    SELECT 1
    FROM payment_event AS p
    WHERE p.tenant_id = l.tenant_id
      AND p.order_id = l.order_id
)
ORDER BY l.line_id;
~~~

**EXISTS** tests existence without multiplying rows by payment count. If the question is **"has it been paid in full?"**, checking EXISTS for one payment is insufficient; you must define payment status and compare appropriate aggregates or ledgers, accounting for refunds and timing.

## 6. Testing Aggregations and Counts at the Right Grain

### 6.1. Line, Order, and Customer Counts Are Not Interchangeable

~~~sql
SELECT
    COUNT(*) AS line_count,
    COUNT(DISTINCT (tenant_id, order_id)) AS distinct_orders,
    COUNT(DISTINCT (tenant_id, customer_code))
        AS distinct_customers,
    SUM(line_amount_vnd) AS total_sales_vnd
FROM fact_order_line;
~~~

The result is **6 lines**, **5 orders**, **3 customers**, **1,100,000 VND**. These are three counts at **three different grains**.

If a dashboard needs unique customers per **year**, you cannot sum the unique customer counts of each **day**:

~~~sql
SELECT
    (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS local_day,
    COUNT(DISTINCT (tenant_id, customer_code))
        AS unique_customers
FROM fact_order_line
GROUP BY 1
ORDER BY 1;
~~~

Daily customer counts are **1, 2, 2**, which sum to **5 customer-days**, whereas the distinct customers across all three days are only **3**. The customer sets **are not disjoint**, so the sum of daily distinct counts **is not** the distinct count for the entire period.

### 6.2. Total Sales by Local Day and Tenant

~~~sql
SELECT
    tenant_id,
    (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS local_day,
    COUNT(*) AS line_count,
    SUM(line_amount_vnd) AS sales_vnd
FROM fact_order_line
GROUP BY
    tenant_id,
    (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
ORDER BY tenant_id, local_day;
~~~

| tenant_id | local_day | line_count | sales_vnd |
| --- | --- | ---: | ---: |
| T01 | 2026-11-19 | 2 | 300000 |
| T01 | 2026-11-20 | 2 | 450000 |
| T01 | 2026-11-21 | 1 | 100000 |
| T02 | 2026-11-21 | 1 | 250000 |

The group totals sum to **6 lines** and **1,100,000 VND**. When grouping by **disjoint groups that cover the entire source set**, the **SUM of the SUMs** must match the source SUM; this is a solid invariant to test.

### 6.3. Two-Way Reconciliation Tests Instead of Period-Only SUM Comparisons

Suppose a materialized report table exists with grain **(tenant_id, local_day)** and column **sales_vnd**. The illustrative table name **daily_sales_report** is not created by the DDL in Section 3; the following query is a **validation template to apply after creating the report table**, not a continuous execution step of the fixture.

~~~sql
WITH expected AS (
    SELECT
        tenant_id,
        (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
            AS local_day,
        SUM(line_amount_vnd) AS sales_vnd
    FROM fact_order_line
    GROUP BY tenant_id, local_day
),
actual AS (
    SELECT tenant_id, local_day, sales_vnd
    FROM daily_sales_report
)
SELECT
    COALESCE(e.tenant_id, a.tenant_id) AS tenant_id,
    COALESCE(e.local_day, a.local_day) AS local_day,
    e.sales_vnd AS expected_sales_vnd,
    a.sales_vnd AS actual_sales_vnd
FROM expected AS e
FULL OUTER JOIN actual AS a
  ON a.tenant_id = e.tenant_id
 AND a.local_day = e.local_day
WHERE e.tenant_id IS NULL
   OR a.tenant_id IS NULL
   OR e.sales_vnd IS DISTINCT FROM a.sales_vnd
ORDER BY tenant_id, local_day;
~~~

When both sets match, the result is **empty**. A FULL OUTER JOIN finds **groups present only in the source** or **groups present only in the target**, which an INNER JOIN would hide. You also must test **UNIQUE(tenant_id, local_day)** on the report table; if the target contains two rows for the same group, reconciliation could fail to spot duplicates or return multiple rows even when amounts appear equal.

### 6.4. Ratios Must Be Computed from Numerator and Denominator

Suppose:

~~~text
Group A: 90 conversions / 100 opportunities = 90%
Group B:  1 conversion  /  10 opportunities = 10%
~~~

The simple average of the two rates is **50%**, whereas the rate across all opportunities is:

\[
\frac{90 + 1}{100 + 10} \times 100\%
= \frac{91}{110}\times100\%
\approx 82.73\%.
\]

**Validation rule:** if the metric contract calls for the rate over the total opportunity population, compute **SUM(numerator) / NULLIF(SUM(denominator), 0)**, never `AVG(rate)`. When the denominator is 0, the rate is typically **undefined (NULL)** rather than silently defaulting to 0%.

### 6.5. Summing Balances Over Time: An Invalid Aggregation

For example, an account has end-of-day balances:

~~~text
Nov 19: 100,000 VND
Nov 20: 120,000 VND
Nov 21:  90,000 VND
~~~

**SUM = 310,000 VND** is not the account balance at any point in time. If asking for the period-ending balance, pick the **latest valid snapshot as of the reporting point**, which here is **90,000 VND**. If asking for the daily average balance, you can use AVG with a clear weighting/day-count definition. Tests must verify **semi-additive** behavior over time and handle periods with missing snapshots, rather than merely checking whether the SQL executes.

### 6.6. Late-Arriving Data and Reporting Scope

If an order is placed on Nov 20 but ingested on Nov 23, a Nov 20 report run on Nov 21 can differ from a report recomputed on Nov 24. To compare two versions, specify:

- **event time:** the date the order was actually placed.
- **ingestion/knowledge time:** the time the system received the data.
- **cutoff/watermark:** the allowed input set and source synchronization boundary.
- **report version/run ID:** which execution produced the published output.

A difference between two runs **is not automatically a JOIN bug**; it can stem from late-arriving data or updated formulas/reference sources. Reconciliation must compare **using the same data, same version, and same cutoff** before concluding which model is wrong.

## 7. Testing Validity History: SCD Type 2 and AS-OF JOIN

A historical dimension can store multiple rows for the same customer, each carrying attributes accurate within a **business validity interval (valid time)**. To classify a fact accurately at transaction time, three invariants typically must be tested:

1. Every fact **has exactly one matching dimension version**.
2. Versions for the same customer **do not overlap in validity intervals**, unless the model intentionally supports concurrent relationships and defines a different grain.
3. Conventions for **time boundaries, timezones, and start/end bounds** are applied consistently.

### 7.1. Half-Open Interval [from, to) Prevents Matching Two Rows at a Boundary

Fixture:

~~~text
T01/C01:
  customer_sk = 101, North, [2026-01-01 00:00 +07, 2026-11-20 00:00 +07)
  customer_sk = 102, South, [2026-11-20 00:00 +07, ∞)
~~~

At exactly **2026-11-20 00:00 +07**, the **North** record has **ended**, and the **South** record **begins**. Using **placed_at BETWEEN valid_from AND valid_to** with both ends **inclusive** causes boundary timestamps to match two versions. Use:

~~~sql
f.placed_at >= c.valid_from
AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
~~~

to express the half-open interval convention accurately.

Test both sides of the boundary:

~~~sql
WITH probe_times AS (
    SELECT TIMESTAMPTZ '2026-11-19 23:59:59+07'
               AS probe_at
    UNION ALL
    SELECT TIMESTAMPTZ '2026-11-20 00:00:00+07'
)
SELECT
    p.probe_at,
    c.customer_sk,
    c.department
FROM probe_times AS p
JOIN dim_customer_history AS c
  ON c.tenant_id = 'T01'
 AND c.customer_code = 'C01'
 AND p.probe_at >= c.valid_from
 AND (p.probe_at < c.valid_to OR c.valid_to IS NULL)
ORDER BY p.probe_at;
~~~

Expected result is **exactly two rows**: the timestamp just before the boundary matches **101/North**, and the exact boundary matches **102/South**. Never rely on the default session timezone to evaluate timestamp comparisons.

### 7.2. Testing for Overlapping Validity Intervals

Two historical rows can have different `customer_sk` values while being simultaneously valid. `PRIMARY KEY(customer_sk)` **does not detect** this bug.

~~~sql
SELECT
    a.tenant_id,
    a.customer_code,
    a.customer_sk AS first_version,
    b.customer_sk AS second_version,
    a.valid_from AS first_from,
    a.valid_to AS first_to,
    b.valid_from AS second_from,
    b.valid_to AS second_to
FROM dim_customer_history AS a
JOIN dim_customer_history AS b
  ON a.tenant_id = b.tenant_id
 AND a.customer_code = b.customer_code
 AND a.customer_sk < b.customer_sk
 AND (a.valid_to IS NULL OR b.valid_from < a.valid_to)
 AND (b.valid_to IS NULL OR a.valid_from < b.valid_to);
~~~

On the fixture, the result must be **empty**. The condition uses **<**, not **<=**, so two intervals that **touch at a boundary** without overlapping are not flagged as errors.

To verify that the test catches faults, run a negative test:

~~~sql
BEGIN;

INSERT INTO dim_customer_history (
    customer_sk, tenant_id, customer_code,
    department, valid_from, valid_to
) VALUES (
    199, 'T01', 'C01', 'TestOverlap',
    TIMESTAMPTZ '2026-11-19 00:00:00+07',
    TIMESTAMPTZ '2026-11-21 00:00:00+07'
);

-- Re-run overlap test: must detect pairs (101, 199) and (102, 199).
-- Run Section 4.4 match-count test: some lines will have 2 matches.

ROLLBACK;
~~~

**Never run negative tests in a production environment.** For real schemas, execute them on a test database or an authorized isolated transaction. A check that only returns an empty set on clean data could simply be broken; testing with deliberately injected faults increases confidence.

### 7.3. Can Overlap Be Blocked in the Database?

In PostgreSQL, you can use an **exclusion constraint** with a range type when you have permission to enable an extension supporting equality operators on `TEXT`:

~~~sql
-- Subject to system privileges and extension policy.
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE dim_customer_history
ADD CONSTRAINT ex_customer_no_overlapping_valid_time
EXCLUDE USING gist (
    tenant_id WITH =,
    customer_code WITH =,
    tstzrange(valid_from, valid_to, '[)') WITH &&
);
~~~

With **valid_to = NULL**, the range has no upper bound. This constraint prevents **two overlapping validity intervals for the same tenant/customer_code**, even under concurrent writes from two transactions. It is appropriate when business rules dictate **only one version is valid at any point in time**. Do not apply this constraint if the relationship legitimately allows parallel statuses at a different grain.

Note: add the constraint **only after cleaning up existing overlapping historical data**; if conflicting rows already exist, PostgreSQL will reject creating the constraint. If extensions or constraints cannot be used in your current infrastructure, enforce this via a locking write protocol and periodic overlap tests—keeping in mind that "running SELECT and seeing no overlaps" does not by itself stop two new transactions from creating overlaps later.

### 7.4. Gap Tests Must Follow Business Policy

**No overlap** does not imply **full coverage across all time**. For instance, C01 could have one interval ending on Nov 19 and the next starting only on Nov 21; a fact on Nov 20 would find no valid version.

Whenever every fact must have a valid dimension, **match-count = 1** from Section 4.4 already detects gaps affecting actual facts. If the model requires a **continuous history** for every `customer_code`, even on days with no facts, add a check between consecutive intervals:

~~~sql
WITH sequenced AS (
    SELECT
        tenant_id,
        customer_code,
        customer_sk,
        valid_from,
        valid_to,
        LAG(valid_to) OVER (
            PARTITION BY tenant_id, customer_code
            ORDER BY valid_from, customer_sk
        ) AS previous_valid_to,
        ROW_NUMBER() OVER (
            PARTITION BY tenant_id, customer_code
            ORDER BY valid_from, customer_sk
        ) AS version_index
    FROM dim_customer_history
)
SELECT
    tenant_id,
    customer_code,
    customer_sk,
    previous_valid_to,
    valid_from
FROM sequenced
WHERE version_index > 1
  AND previous_valid_to IS DISTINCT FROM valid_from;
~~~

The result is empty on the fixture. This query reports both gaps and certain overlaps between adjacent rows, but it **does not replace the overlap test** and is only suitable when the model commits to a **contiguous chain of versions**. A customer might leave a service and return later, making an unrepresented interval **valid**; in that case, tests should focus on intervals where the business requires active existence.

### 7.5. Aggregating by Attributes Valid at Transaction Time

~~~sql
SELECT
    c.department,
    COUNT(*) AS line_count,
    SUM(f.line_amount_vnd) AS sales_vnd
FROM fact_order_line AS f
JOIN dim_customer_history AS c
  ON c.tenant_id = f.tenant_id
 AND c.customer_code = f.customer_code
 AND f.placed_at >= c.valid_from
 AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
GROUP BY c.department
ORDER BY c.department;
~~~

Result:

| department at order time | line_count | sales_vnd |
| --- | ---: | ---: |
| North | 3 | 450000 |
| South | 3 | 650000 |

The two groups sum to **6 lines and 1,100,000 VND**. Using the **current** dimension (where C01 is in South) would reclassify all of C01's history into South, corrupting past department reports even though **system-wide total revenue remains unchanged**. Thus, tests must compare **along historical dimensions**, not just grand totals.

### 7.6. When Facts Store customer_sk, How Should We Validate?

In a star schema, facts often store **customer_sk** resolved during ingestion. A simple JOIN `fact.customer_sk = dim.customer_sk` ensures every fact finds one dimension row via FK/PK.

However, **a one-to-one JOIN does not prove `customer_sk` was assigned to the right historical version**. Tests must cross-check against the business key and timestamp:

~~~text
for each fact:
  dim.customer_sk = fact.customer_sk
  dim.tenant_id/customer_code matches fact source identity
  dim.valid_from <= fact.placed_at < dim.valid_to
~~~

If a fact mistakenly stored `customer_sk = 102` for L01 (on Nov 19), PK/FK integrity still holds, yet **department will be wrong**. Persisting surrogate keys does not eliminate the need to validate temporal assignment.

## 8. Distinguishing Valid Time, System Time, and Two Ways of Asking Historical Questions

### 8.1. Two Distinct Historical Questions

**Valid time** asks: *"What was true in the business domain at time T?"*

**System/knowledge time** asks: *"At time K, what did the system know/record as true for time T?"*

Suppose on **Nov 23**, staff confirm that customer C01 actually switched departments starting **Nov 19**, not **Nov 20** as previously published. A new report can be restated retroactively, yet the report users saw on **Nov 22** was still based on the older information.

| Transaction Time to Classify | Data Known on Nov 22 | Data After Nov 23 Correction |
| --- | --- | --- |
| Nov 19 10:00 +07 | North | South |
| Nov 20 09:00 +07 | South | South |

If you only store **current `valid_from`/`valid_to`**, editing history can erase the audit trail of "what the system once believed." To reproduce both reports, you need **per-run dimension snapshots/versions** or **bitemporal modeling**.

### 8.2. Bitemporal Modeling

A richer history table can store:

~~~text
customer_code
department
valid_from, valid_to       -- business validity
recorded_from, recorded_to -- interval recorded in the system
~~~

Both intervals follow the **[from, to)** convention. Querying "what was known at K to be valid at T?" must filter **both axes**:

~~~sql
-- Condition pattern when a bitemporal_customer table exists.
-- This is not a table from the Section 3 fixture.
SELECT b.department
FROM bitemporal_customer AS b
WHERE b.tenant_id = 'T01'
  AND b.customer_code = 'C01'
  AND b.valid_from <= TIMESTAMPTZ '2026-11-19 10:00:00+07'
  AND (
      b.valid_to > TIMESTAMPTZ '2026-11-19 10:00:00+07'
      OR b.valid_to IS NULL
  )
  AND b.recorded_from <= TIMESTAMPTZ '2026-11-22 12:00:00+07'
  AND (
      b.recorded_to > TIMESTAMPTZ '2026-11-22 12:00:00+07'
      OR b.recorded_to IS NULL
  );
~~~

This is a **semantic query template**. To guarantee exactly one result, a bitemporal table must enforce **non-overlapping valid-time intervals within any given system-time slice** for the same entity—not just a PK on a surrogate key. For retroactive corrections, preserve old records in system-time history rather than overwriting them without a trace.

### 8.3. Facts and Dimensions Must Use the Same Point-of-View Version

If a fact snapshot **run 9001** was computed using dimension data as known on Nov 22, you must not attempt to reproduce that report by joining against dimension history retroactively corrected on Nov 23 and then conclude run 9001 was "calculated wrong" against the new data. There are two distinct goals:

- **Reproduce:** recreate exactly what run 9001 knew and published.
- **Restate:** recompute historical results using newly accepted facts/logic, producing **run 9002** with clear metadata and deltas.

Both are valuable. Tests must specify whether they verify **reproducibility** or **correctness against corrected data**, never mixing two knowledge timestamps to manufacture false discrepancies.

### 8.4. Late-Arriving Data and Upstream Corrections

A fact occurring on Nov 19 but ingested on Nov 23 may need to join with the dimension effective on **Nov 19**, not the current dimension on **Nov 23**. If historical dimensions also arrive late, the pipeline must handle:

- **late-arriving fact:** facts arriving after the business period closes.
- **late-arriving dimension:** dimensions or effective versions not yet present when the fact is loaded.
- **retrospective correction:** editing historical effective dates.
- **out-of-order events:** events arriving out of source order.

When corrections occur, department/day summary tables may require **backfill/restatement**, even if fact `amount_vnd` values remain unchanged. That is why temporal tests belong inside the **model evolution workflow**, not just in read-only queries.

## 9. Testing Dates, Timezones, and Time Boundaries

### 9.1. Never Rely on Implicit Session Timezone

In PostgreSQL, **TIMESTAMPTZ** represents an absolute instant. Casting **placed_at::DATE** depends on the session timezone. If a report requires local Vietnam dates, write it explicitly:

~~~sql
(placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
~~~

For line **L05**:

~~~text
local occurred_at: 2026-11-21 00:30:00 +07
UTC instant:       2026-11-20 17:30:00 Z
report_day VN:     2026-11-21
report_day UTC:    2026-11-20
~~~

Validation query:

~~~sql
SELECT
    line_id,
    (placed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::DATE
        AS vietnam_day,
    (placed_at AT TIME ZONE 'UTC')::DATE
        AS utc_day
FROM fact_order_line
WHERE line_id = 'L05';
-- L05: vietnam_day = 2026-11-21; utc_day = 2026-11-20.
~~~

If a rule switches from UTC to Vietnam local day, revenue can **shift between adjacent days** even though the period total stays unchanged. Tests should therefore include transactions right before and right after local midnight.

### 9.2. Testing [start, end) Intervals for Transactional Data

A single-day report should normally filter as:

~~~sql
SELECT SUM(line_amount_vnd) AS sales_vnd
FROM fact_order_line
WHERE placed_at >= TIMESTAMPTZ '2026-11-20 00:00:00+07'
  AND placed_at <  TIMESTAMPTZ '2026-11-21 00:00:00+07';
-- 450000 VND, comprising L03 and L04.
~~~

Avoid **BETWEEN** with closed timestamp endpoints when chaining consecutive day intervals: an event at exactly 00:00 can be counted in **both intervals**. In regions with Daylight Saving Time (DST), the span from one local midnight to the next may not always be exactly 24 hours; convert **both local calendar boundaries** to absolute instants instead of assuming every day worldwide is 24 hours long.

### 9.3. Boundary Cases Required in Fixtures

| Test Case | Why It Is Needed |
| --- | --- |
| Event exactly at **valid_from** | Must belong to the new version |
| Event exactly at **valid_to** of the old version | Must not belong to the old version under `[from, to)` |
| Event 1 second away from a version transition | Catches off-by-one boundary mistakes |
| Transaction at 00:00 or 23:59:59 in report timezone | Catches daily grouping bugs |
| Fact arriving late relative to its business date | Tests as-of / cutoff / backfill |
| Retroactive effective-date correction | Tests restatement and reproducibility |
| Missing dimension in an interval | Catches orphan/gap issues |
| Two overlapping historical versions | Catches fanout issues |

**A temporal test dataset using only mid-month timestamps** rarely catches boundary bugs, which is where many real-world failures occur.

## 10. From Discrepancy Queries to Automated Tests

To turn the checks in this lesson into regression tests, establish these conventions:

- **Discrepancy-query checks:** pass when the result has **zero rows**.
- **Invariant-measure checks:** pass when actual figures equal approved expected figures.
- **Exception checks:** pass when invalid operations are blocked or the expected error type is raised.
- **Historical regression checks:** pass when the same fixture, version, and cutoff produce the exact same output set.

### 10.1. Wrapping Assertions in a PostgreSQL DO Block

The following test block can be run **after the DDL and INSERTs in Section 3**:

~~~sql
DO $$
DECLARE
    v_line_count BIGINT;
    v_total NUMERIC;
    v_bad_matches BIGINT;
BEGIN
    SELECT COUNT(*), COALESCE(SUM(line_amount_vnd), 0)
    INTO v_line_count, v_total
    FROM fact_order_line;

    IF v_line_count <> 6 OR v_total <> 1100000 THEN
        RAISE EXCEPTION
            'Invalid fixture: lines=%, total=% (expected 6, 1100000)',
            v_line_count, v_total;
    END IF;

    WITH match_counts AS (
        SELECT
            f.line_id,
            COUNT(c.customer_sk) AS matches
        FROM fact_order_line AS f
        LEFT JOIN dim_customer_history AS c
          ON c.tenant_id = f.tenant_id
         AND c.customer_code = f.customer_code
         AND f.placed_at >= c.valid_from
         AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
        GROUP BY f.line_id
    )
    SELECT COUNT(*)
    INTO v_bad_matches
    FROM match_counts
    WHERE matches <> 1;

    IF v_bad_matches <> 0 THEN
        RAISE EXCEPTION
            'Temporal JOIN is not 1-1 at line grain: % failing rows',
            v_bad_matches;
    END IF;

    RAISE NOTICE 'PASS: fixture and temporal JOIN match grain';
END $$;
~~~

This block is an **assertion illustration** for the fixture, not proof that PostgreSQL was executed while authoring the document. In CI, **RAISE EXCEPTION** must fail the test job; never configure the runner to ignore non-zero exit codes.

### 10.2. Comparing SQL Output Against an Oracle Instead of Checking Row Counts Alone

With fixed fixture data, you can use a **symmetric EXCEPT** to compare value sets:

~~~sql
WITH actual AS (
    SELECT
        c.department,
        COUNT(*)::BIGINT AS line_count,
        SUM(f.line_amount_vnd) AS sales_vnd
    FROM fact_order_line AS f
    JOIN dim_customer_history AS c
      ON c.tenant_id = f.tenant_id
     AND c.customer_code = f.customer_code
     AND f.placed_at >= c.valid_from
     AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
    GROUP BY c.department
),
expected AS (
    SELECT *
    FROM (
        VALUES
            ('North'::TEXT, 3::BIGINT, 450000::NUMERIC),
            ('South'::TEXT, 3::BIGINT, 650000::NUMERIC)
    ) AS x(department, line_count, sales_vnd)
),
differences AS (
    (SELECT * FROM expected EXCEPT SELECT * FROM actual)
    UNION ALL
    (SELECT * FROM actual EXCEPT SELECT * FROM expected)
)
SELECT * FROM differences;
~~~

Expect **zero rows**. **EXCEPT** uses set semantics and deduplicates tuples; it works when each group must be unique. If you need to compare **multisets** preserving multiplicity, use **EXCEPT ALL** or check uniqueness separately. A dataset with two identical duplicate rows must never pass simply because set comparison deduplicated them.

### 10.3. Testing Metrics Across Multiple Dimensions, Not Just One Total

A useful test suite can assert simultaneously:

~~~text
source:
  line_count = 6
  distinct_order_count = 5
  sales = 1,100,000
  quantity = 14

historical_join:
  rows = 6
  unmatched = 0
  multiply_matched = 0
  North.sales = 450,000
  South.sales = 650,000

payment:
  payment_events = 6
  paid_sum = 1,100,000
  O1001 has 2 lines and 2 payments

daily:
  T01/19-11 = 300,000
  T01/20-11 = 450,000
  T01/21-11 = 100,000
  T02/21-11 = 250,000
~~~

These expected values apply only to the **fixture in this lesson**. In real systems, the oracle may be an approved export from the system of record, a reviewed golden dataset, or an independent calculation—never values automatically generated by the very query under test.

### 10.4. Avoiding "Testing the Same Bug as the Code Under Test"

If both the pipeline and the test call the same buggy date helper, they can **agree while both being wrong**. Combine:

1. **Business-approved fixed expected values** for small fixtures.
2. **Independent invariant tests:** grain, match-count, key sets, source sums.
3. **Boundary behavior tests:** timestamps on both sides of `valid_from`/`valid_to` and midnight.
4. **Cross-source checks:** ledger/payments or specialized reports with reconciled definitions.
5. **Rule review:** does the SQL truly express the business question accurately?

A test cannot prove absolute correctness; it increases the likelihood of catching bugs under **the conditions it was designed to check**.

## 11. Negative Tests and Property / Metamorphic Testing

### 11.1. Suite of Intentional Faults to Inject into Test Fixtures

| Injected Fault | Expected Symptom | Responsible Test |
| --- | --- | --- |
| Add an overlapping dimension row for C01 | Some lines have **match_count > 1** | Temporal join match-count, overlap |
| Add a fact for customer C99 with no dimension | One line has **match_count = 0** | Anti-join / left match-count |
| Omit tenant_id from JOIN | Data may match a same-code customer in another tenant | Cross-tenant isolation |
| JOIN lines directly to O1001's two payments | Total jumps from 1.1M to **1.4M** | Aggregate reconciliation and fanout |
| JOIN facts to all SCD versions | Total jumps to **1.8M** | Fanout + as-of |
| Replace VN date with UTC date for L05 | L05 shifts from Nov 21 to Nov 20 | Day-boundary oracle |
| Use BETWEEN inclusive of valid_to | Boundary fact matches two versions | Boundary test |
| Sum daily DISTINCT customer counts | 5 customer-days instead of 3 unique customers | Distinct-count rule |
| Duplicate a payment with a new ID on retry | Paid sum increases | Idempotency / source event uniqueness |
| Report drops one tenant–day group | Total may be wrong or offset | FULL OUTER JOIN or symmetric EXCEPT |
| Retroactively edit historical dimension | Past department group totals change | Bitemporal / restate regression |

These tests should run in an isolated test environment with proper cleanup, never mutating live user operational data.

### 11.2. Metamorphic Testing: Under Controlled Input Changes, What Must Hold?

For some queries, building a full oracle across millions of records is difficult, yet we can still define **invariant relationships under input transformations**.

**Property A — reordering source rows:** when merely summing over the same row set, results must not change if INSERT or read order changes. If SQL relies on "the first row" without a deterministic `ORDER BY`, that signals an under-specified design.

**Property B — splitting one order line into two valid lines:** if a 300,000 line is split into 100,000 and 200,000 within **the same order, same tenant, and same classification timestamp**, total revenue must stay constant while **line count increases by one**. Tests must therefore distinguish `line_count` from `sales_vnd`.

**Property C — adding a payment to the same order:** when computing only **line_amount_vnd**, adding a new payment event **must not change total sales**. If total sales rise with payment count, the JOIN is multiplying rows.

**Property D — adding a future-effective SCD version:** for facts occurring **before the new version's `valid_from`**, historical classifications must stay unchanged unless the business intentionally performs a retroactive correction.

**Property E — adding records outside the filter scope:** tenant T01's figures must not change when a transaction belonging solely to tenant T02 is inserted, assuming no cross-tenant sharing rule exists.

**Property F — partitioning and re-aggregating:** the SUM of sums across **disjoint groups covering the whole source** must equal the source SUM. Do not apply this additive property to `COUNT DISTINCT` customers if customers appear across multiple groups.

### 11.3. Example Test for Payment-Count Independence

Run inside a transaction so test data is not persisted:

~~~sql
BEGIN;

-- Source sales total before adding a payment:
SELECT SUM(line_amount_vnd) AS sales_before
FROM fact_order_line;
-- 1100000.

-- Add a new payment event for O1001 in the test fixture.
INSERT INTO payment_event (
    payment_id, tenant_id, order_id, paid_at, paid_vnd
) VALUES (
    'P_TEST', 'T01', 'O1001',
    TIMESTAMPTZ '2026-11-19 10:07:00+07', 10000
);

-- Independent sales total from fact lines must still be 1100000.
SELECT SUM(line_amount_vnd) AS sales_after
FROM fact_order_line;

-- If the sales query depends on payment count,
-- the buggy JOIN result from Section 5.1 will change.

ROLLBACK;
~~~

The goal is not to argue that the extra payment is business-valid; this is a **test transformation** proving that a metric's calculation is invariant to an unrelated relationship outside its grain.

### 11.4. Why Randomized Testing Still Needs Fixed Boundary Cases

Property-based testing can generate varying order-line counts, payment counts, valid-time intervals, tenants, and timestamps to verify invariants:

~~~text
For every generated fact line:
  count(as_of_dimension_matches) == 1

For any payment fanout change:
  total_sale_amount == SUM(source_line_amount)

For any pair of customer history rows:
  no overlapping valid-time intervals within the same business key
~~~

However, if a random generator rarely hits **2026-11-20 00:00:00+07** exactly, boundary bugs can still slip through. Always **keep fixed boundary cases**, use randomization to expand coverage, and save **seed + fixture + transform version** on failure for reproducibility.

## 12. Testing When Models and Pipelines Evolve

### 12.1. Schema Changes Must Not Unintentionally Alter Metric Semantics

Suppose v1 used **customer_code** to join current customer attributes, and v2 adds historical **customer_sk**. The schema migration may deploy cleanly, yet historical reports can shift department distributions.

A validation process should compare:

- **Metrics guaranteed unchanged:** total line count, total line value, source order identities.
- **Metrics allowed to change:** point-in-time department reports may differ from current-state department reports because **the semantics were fixed**.
- **Blast radius:** which tenants/days/orders changed and why?
- **Replayability:** do identical input snapshots and transform versions yield identical outputs?

Do not aim for "every pre- and post-migration figure must be identical" when a migration is fixing a previously broken metric. Define precisely **which invariants must hold** and **which differences are approved**.

### 12.2. Reconciliation During Historical Backfills

Fact table backfills often run in batches. Matching checkpoints and row counts is insufficient:

1. **Source snapshot and transform version:** pin the exact comparison dataset.
2. **Key coverage:** every eligible source record has a target fact, with no extra facts.
3. **Row-level values:** amounts, tenant, timestamps, customer identity, and SCD classification are accurate.
4. **Group aggregates:** totals by day, tenant, and department.
5. **Late events / corrections:** after the snapshot, run catch-up according to policy to publish current data.
6. **Publish / rollback:** switch dashboards to the new version only after sign-off and shadow comparison monitoring.

If the source receives live writes, **MAX(id)** or ingestion timestamps alone do not guarantee a consistent snapshot; use gap-free snapshots/captures, commit positions, or appropriate synchronization mechanisms.

### 12.3. Testing "As-of Published Version" Results

In a system with multiple runs:

~~~text
run_id = 9001, source_cutoff = 2026-11-22 00:00 +07,
dim_history_version = V1, metric_version = M1

run_id = 9002, source_cutoff = 2026-11-24 00:00 +07,
dim_history_version = V2, metric_version = M1
~~~

A comparison can treat run 9001 as **evidence of published figures** and run 9002 as **restated figures**. Tests must explain the delta: late arrivals, corrections, or dimension history changes. Never JOIN summary tables from two runs while omitting `run_id` and conclude there are duplicates.

### 12.4. Testing Against Real Data Within Controlled Resource Bounds

Small fixtures explain bugs clearly, whereas real workloads produce rare relationships:

- One order with hundreds of lines and dozens of payments.
- One customer with dozens of SCD versions and multiple retroactive edits.
- One tenant sharing an ID with another tenant in separate source systems.
- A payment arriving before its order or retried with duplicate IDs.
- A reporting day with differing timezone rules due to geography/DST.
- A dimension table with orphans, gaps, or overlapping intervals from legacy data.

On production data, run **resource-bounded data quality tests**, or run them against an appropriate replica/snapshot; full-table GROUP BYs and large FULL OUTER JOINs can be expensive. Choose targeted partitions/samples and schedule full audits according to risk.

### 12.5. Performance Testing After Correctness Testing

A correct model can still miss SLOs:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT
    c.department,
    SUM(f.line_amount_vnd)
FROM fact_order_line AS f
JOIN dim_customer_history AS c
  ON c.tenant_id = f.tenant_id
 AND c.customer_code = f.customer_code
 AND f.placed_at >= c.valid_from
 AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
GROUP BY c.department;
~~~

`EXPLAIN ANALYZE` actually executes the `SELECT`; in real environments, run it only with proper authorization and resource windows. Evaluate the `(tenant_id, customer_code, valid_from)` index, time distribution, history depth, and the feasibility of a **GiST range index** if supported by the DBMS.

**Never optimize by dropping the temporal condition**: it may speed up the JOIN while corrupting the data. Any decision to use materialized views, denormalization, or pre-aggregation must be paired with tests protecting grain and recomputability.

## 13. Applying Validation Principles to Other Models

### 13.1. Relational OLTP

In a normalized transactional design, **PRIMARY KEY**, **UNIQUE**, **FOREIGN KEY**, **CHECK**, and interval constraints prevent many bugs at write time. Yet they do not automatically protect aggregations in a query with the wrong grain:

- An FK from order line to order only confirms the line has a parent; it does not prevent joining multiple payments from multiplying lines.
- `UNIQUE(customer_sk)` does not guard against overlapping SCD intervals.
- `CHECK(amount >= 0)` does not prevent summing an amount twice.
- `UNIQUE` on `order_id` alone can be wrong if order IDs are only unique per tenant.

Best practice combines **schema constraints** to block invalid states at the root, **query assertions** to check relationships, and **reconciliation** to verify derived metrics.

### 13.2. Star Schema and Data Warehouse

In an analytical warehouse, clarify:

- Which facts are **transaction facts**, **periodic snapshots**, or **accumulating snapshots**?
- Does a dimension have a single-version **surrogate key** or a multi-version history table?
- Which measures are **additive**, **semi-additive**, or **non-additive**?
- Are **conformed dimensions** used consistently across facts?
- Are there many-to-many **bridge tables** requiring weight allocation?

If an order has multiple tags using an **order_tag** bridge, tag totals may **intentionally appear under multiple tags**. In that case, **SUM across all tags** exceeding the order total is **valid under an "unallocated tag attribution" metric**, yet wrong if presented as **non-overlapping unique revenue**. State the allocation policy explicitly—for example, if an order has three tags, each receives 1/3 of the value under a rule version—and verify that weights sum to 1 per order.

### 13.3. Document Databases

An order document might look like:

~~~json
{
  "order_id": "O1001",
  "line_items": [
    {"line_id": "L01", "amount_vnd": 100000},
    {"line_id": "L02", "amount_vnd": 200000}
  ],
  "payments": [
    {"payment_id": "P01", "amount_vnd": 200000},
    {"payment_id": "P02", "amount_vnd": 100000}
  ]
}
~~~

If a pipeline **unwinds** both `line_items` and `payments` before summing amounts, it can generate **2 × 2 = 4 combinations**, identical to an N–M JOIN in SQL. Embedding data in JSON **does not eliminate fanout**. You must validate the grain at each unnest/unwind stage and never multiply one array's measures by the length of another array.

### 13.4. Graph Databases

In a graph, a customer can connect to multiple labels, multiple organizations, and multiple paths to the same order. A traversal returning **multiple paths** does not imply multiple **unique orders**. If the metric is order count, verify **deduplication by order identity**; if the metric is connection path count, counting paths may be right.

For edges carrying temporal validity, graph traversals must also pick **edges valid at the event timestamp**, rather than defaulting to current edges. Invariants for cardinality, time, and tenant isolation still apply.

### 13.5. Event-Sourced and Streaming Analytics

A state record updated multiple times does not necessarily represent multiple revenue transactions. Consumers can also receive retries or out-of-order events. Blindly summing all update records:

~~~text
order O1001 version 1: total = 300000
order O1001 version 2: total = 320000
~~~

produces an erroneous **620,000** if the two records are **two state snapshots**, not two independent financial events. You must distinguish **snapshot updates**, **delta events**, and **immutable transaction facts**, then validate `source_event_id`/`source_version`, checkpoints, deduplication, and late-arriving events.

This is a fundamental difference in **event grain**, not a simple SUM error. Good validation starts with the source contract, not by slapping `DISTINCT` onto a query.

## 14. Practice Exercises

### Exercise 1. Measuring the Impact of an SCD JOIN Without a Time Condition

Review the sample data in Section 3. Customer T01/C01 has **two dimension versions** and appears in four fact lines.

**Requirements:**

1. After joining `fact_order_line` with `dim_customer_history` solely on `tenant_id`/`customer_code`, how many rows are returned?
2. What is the post-JOIN `SUM(line_amount_vnd)`?
3. Why did the total increase even though the fact table has no duplicate rows?
4. Write the correct JOIN condition to classify by department **at order placement time**.
5. What should the row count and total amount be after the correct JOIN?

<details>
<summary>Solution Hint for Exercise 1</summary>

A JOIN without the time condition produces **10 rows**. Each of C01's four lines is doubled, adding **700,000 VND** and inflating sales to **1,800,000 VND**.

Correct condition:

~~~sql
ON c.tenant_id = f.tenant_id
AND c.customer_code = f.customer_code
AND f.placed_at >= c.valid_from
AND (f.placed_at < c.valid_to OR c.valid_to IS NULL)
~~~

After the correct JOIN, there must be **6 rows, 1,100,000 VND**; North **450,000**, South **650,000**. Beyond checking totals, verify that **each `line_id` has exactly one `c.customer_sk`**.

</details>

### Exercise 2. Two 1–N Sources and Row Multiplication

Order O1001 has:

~~~text
line_items: L01 = 100000, L02 = 200000
payments:   P01 = 200000, P02 = 100000
~~~

**Requirements:**

1. How many rows does joining the two tables on `order_id` produce for O1001?
2. What do `SUM(line_amount_vnd)` and `SUM(paid_vnd)` become on the JOIN for O1001 alone?
3. Why are both totals wrong even though they equal each other?
4. To compare merchandise value with total paid per order, which SQL solution preserves the right grain?

<details>
<summary>Solution Hint for Exercise 2</summary>

The JOIN creates **2 × 2 = 4** rows. Each order line appears twice and each payment appears twice; both SUMs become **600,000 VND**, even though each source's true total is only **300,000 VND**.

You must **GROUP BY (tenant_id, order_id)** independently on each fact:

~~~sql
WITH sales AS (
    SELECT tenant_id, order_id, SUM(line_amount_vnd) AS amount
    FROM fact_order_line
    GROUP BY tenant_id, order_id
),
payments AS (
    SELECT tenant_id, order_id, SUM(paid_vnd) AS amount
    FROM payment_event
    GROUP BY tenant_id, order_id
)
SELECT s.tenant_id, s.order_id,
       s.amount AS sales_vnd,
       p.amount AS paid_vnd
FROM sales AS s
LEFT JOIN payments AS p
  ON p.tenant_id = s.tenant_id
 AND p.order_id = s.order_id
WHERE s.order_id = 'O1001'
  AND s.tenant_id = 'T01';
~~~

Correct result: **sales_vnd = 300000**, **paid_vnd = 300000**.

</details>

### Exercise 3. Counting Unique Customers Across Multiple Days

The sample data has daily unique customers:

~~~text
Nov 19: {T01/C01}
Nov 20: {T01/C01, T01/C02}
Nov 21: {T01/C01, T02/C03}
~~~

**Requirements:**

1. What is the sum of daily `COUNT(DISTINCT customer)` values?
2. What is `COUNT DISTINCT` across the entire period?
3. What does the difference represent?
4. If only the `daily_unique_customer_count` table remains, can you compute the exact unique customers for the whole period from those three numbers?

<details>
<summary>Solution Hint for Exercise 3</summary>

The sum of daily unique customers is **1 + 2 + 2 = 5 customer-days**. The number of distinct business customers across the whole period is **3**: T01/C01, T01/C02, and T02/C03.

If you only keep the three numbers 1, 2, 2 without retaining **customer identities or mergeable set structures**, you cannot deduce the exact period-wide unique count. The sets can overlap to varying degrees. You need `COUNT DISTINCT` over sufficiently granular data or specialized structures with explicitly stated accuracy/estimation bounds.

</details>

### Exercise 4. Testing Validity Boundaries and Day Boundaries

C01's dimension has:

~~~text
North: valid_to   = 2026-11-20 00:00 +07
South: valid_from = 2026-11-20 00:00 +07
~~~

L05 was placed at **2026-11-21 00:30 +07**.

**Requirements:**

1. Does a C01 fact at exactly Nov 20 00:00 +07 belong to North or South?
2. Why should you avoid `BETWEEN` with two closed boundaries?
3. Which day does L05 fall on when grouped by UTC vs. `Asia/Ho_Chi_Minh`?
4. When is adding 24 hours from midnight unsuitable for calculating a local calendar day?

<details>
<summary>Solution Hint for Exercise 4</summary>

At exactly Nov 20 00:00 +07, **South** is in effect and North has ended, because we use **[from, to)**. `BETWEEN` with two closed bounds can cause both versions to match at the transition instant.

L05 is at **2026-11-20 17:30 UTC**, so its UTC day is **Nov 20** and its Vietnam day is **Nov 21**. In timezones observing DST, a calendar day can be **23 or 25 hours** long, so compute start/end instants in the local timezone rather than assuming every day is 24 hours.

</details>

### Exercise 5. Overlaps, Orphans, and Match-Count Conditions

A team adds a row to `dim_customer_history` with **customer_sk = 199**, for the same **T01/C01**, with interval:

~~~text
[2026-11-19 00:00 +07, 2026-11-21 00:00 +07)
~~~

Then a new fact for **tenant T01 / customer C99** is loaded without a corresponding dimension row.

**Requirements:**

1. Which of lines L01–L06 can match more than one historical version?
2. Which test finds dimension overlaps without joining facts?
3. Which test detects both unmatched rows and multiply-matched rows?
4. Why doesn't `PRIMARY KEY(customer_sk)` block overlaps?

<details>
<summary>Solution Hint for Exercise 5</summary>

L01 and L02 on Nov 19 match both North and version 199; L03 on Nov 20 matches both South and version 199. L06 on Nov 21 16:00 falls outside version 199's interval. Thus **L01, L02, and L03** have **match_count = 2**.

An overlap test self-joins `dim_customer_history` on the same tenant/customer_code, two distinct `customer_sk` values, and an interval intersection condition. A **LEFT JOIN fact → SCD followed by GROUP BY line_id, HAVING COUNT(customer_sk) <> 1** detects both **0** and **> 1** matches.

`PRIMARY KEY(customer_sk)` only protects each version's surrogate ID, not **uniqueness over the business key and time range**. An exclusion constraint on a range type can enforce this if infrastructure policy permits.

</details>

### Exercise 6. Retroactive Correction Shifts Distribution Without Changing Total

Initially, the system knew T01/C01 moved from North to South on **Nov 20 00:00 +07**. On Nov 23, a correction states the actual move date was **Nov 19 00:00 +07**.

**Requirements:**

1. Does the total `line_amount_vnd` across the fixture change?
2. What are the North and South totals after restatement?
3. What conditions/metadata are needed to reproduce the report as known on Nov 22?
4. Why can directly `UPDATE`-ing `valid_from` in the current dimension destroy auditability?

<details>
<summary>Solution Hint for Exercise 6</summary>

The total remains **1,100,000 VND**, because no lines or amounts changed. Lines L01 and L02 (totaling **300,000 VND**) shift classification from North to South.

Therefore, **new North = 450,000 − 300,000 = 150,000 VND**, and **new South = 650,000 + 300,000 = 950,000 VND**. This is a **restatement based on retroactively corrected truth**, not newly added revenue.

To reproduce the Nov 22 published report, you need per-run dimension snapshots/versions, or bitemporal history storing both valid-time and recorded/system-time, along with transform version and cutoff. Overwriting the old record in place without keeping recorded history makes it hard to prove why two report versions differ.

</details>

### Exercise 7. Totals and Row Counts Match—Can It Still Be Wrong?

A source table has rows:

~~~text
id=A, amount=100000
id=B, amount=200000
id=C, amount=300000
~~~

Target table:

~~~text
id=A, amount=150000
id=B, amount=150000
id=C, amount=300000
~~~

**Requirements:** evaluate `COUNT(*)` and `SUM(amount)` checks. Propose a test that catches the discrepancy even though both checks pass.

**Solution approach:** both source and target have **3 rows and a total of 600,000 VND**, so COUNT/SUM miss the error. Use a **FULL OUTER JOIN on `id`** comparing `amount` via **IS DISTINCT FROM**, or `EXCEPT ALL` across all reconciled columns. Also check **key sets** to catch a missing row and an extra row cancelling each other out.

### Exercise 8. Designing a Validation Gate Before Cutover

A new data mart has passed row-count and system-wide revenue checks, but has not yet been tested for SCD intervals, late-arriving data, or per-tenant queries. The team wants to switch all dashboards to the new model immediately.

**Requirements:** propose at least six conditions required before approving publication.

**Solution approach:** require grain and source/cutoff contracts; key/duplicate/orphan checks; SCD match-count = 1, overlap/gap, and as-of checks; monetary reconciliation by tenant/day/department; payment-fact fanout checks; late-event/correction handling; shadow-query comparison; tenant isolation checks; SLO/performance checks; run versioning, rollback plan, and post-cutover monitoring. Row counts and period-wide totals are **not sufficient**.

## 15. Acceptance Checklist for Joins, Aggregations, and History

| Area | Validation Question | Example Evidence |
| --- | --- | --- |
| **Fact grain** | Is one fact row a line, an order, or an event? | Data contract, PK, duplicate checks |
| **Business key** | Is the ID unique per tenant, per source, or globally? | Properly scoped UNIQUE, cross-tenant duplicate-code fixture |
| **N–1 Join** | Does every fact have exactly one dimension match? | `COUNT(dim_key)` per fact key equals 1 |
| **1–N Join** | Is row multiplication intentional to count child entities? | Expected multiplicity per parent key |
| **N–M Join** | Are measures pre-aggregated to the same grain first? | Independent source totals vs. post-JOIN totals |
| **Orphans** | Are unmatched rows hidden by an INNER JOIN? | NOT EXISTS / anti-join |
| **JOIN key completeness** | Are tenant/source/ID/version all included? | Cross-tenant negative test |
| **Historical dimension** | Do validity intervals overlap? | Overlap test or exclusion constraint |
| **Historical dimension** | Does any fact fall into a gap? | AS-OF match-count equals 1 |
| **Time boundaries** | Is the `[from,to)` convention consistent? | Facts on exact `valid_from`/`valid_to` |
| **Reporting time** | UTC day, local day, or ingestion day? | Fixtures around 00:00; explicit timezone |
| **Valid/system time** | Do we want truth at T or what the system knew at K? | Run/version, bitemporal/snapshot if needed |
| **Additive measure** | Is SUM adding independent, non-duplicated components? | Source total vs. sum of group totals |
| **Semi-additive** | Are snapshot balances summed across time? | Period-end / average tests matching contract |
| **Distinct count** | Are distinct counts summed across overlapping groups? | Direct COUNT DISTINCT over the period set |
| **Ratio** | Are ratios recomputed from numerator/denominator? | `SUM(numerator)/SUM(denominator)` |
| **Reconciliation** | Are key sets and values checked, not just counts/sums? | FULL OUTER JOIN, EXCEPT ALL when needed |
| **Late-arriving data** | Are cutoff, watermark, and input versions tracked? | Run metadata and source checkpoints |
| **Retroactive edits** | Are reproduce and restate clearly separated? | Old vs. new run comparison and delta explanation |
| **Deployment** | Are consumers, schemas, and feature flags ready? | Shadow reads, rollback checklist |
| **Operations** | Are fault-injection tests and long-term monitoring in place? | CI assertions, data-quality alerts, ownership |

### 15.1. Recommended Testing Layers by Stage

| Stage | Priority Tests | Rationale |
| --- | --- | --- |
| **Schema definition** | Grain, keys, domains, UNIQUE/FK, non-overlap | Block invalid data at the root |
| **SQL/ETL pull requests** | Small fixtures, oracle, fanout, as-of, timezone, negative tests | Catch logic bugs before deployment |
| **Real-data backfills** | Count + key set + values + partition aggregates | Spot large-scale historical drift |
| **Pre-cutover** | Shadow queries, source/version equivalence, tenant isolation, SLO | Avoid switching read paths prematurely |
| **Post-publish** | Freshness, match-count, overlap, late-event diff, reconciliation drift | Catch source-induced drift and data evolution |

Assign an **owner and remediation runbook** to each check. An alert saying "JOIN fanout exceeded threshold" with no owner, no identification of the failing group, and no rollback path rarely acts as real protection.

### 15.2. Sample Acceptance Criteria for the Lesson Fixture

~~~text
CONTRACT:
  fact grain = one order line
  customer business key = tenant_id + customer_code
  historical dimension = valid interval [from, to)
  reporting timezone = Asia/Ho_Chi_Minh

BASELINE:
  order lines = 6
  distinct orders = 5
  distinct customers = 3
  sales total = 1,100,000 VND
  payment events = 6
  paid total = 1,100,000 VND

RELATIONSHIPS:
  missing historical dimension matches = 0
  multiple historical dimension matches = 0
  overlapping customer validity ranges = 0
  payment-only orders = 0 (fixture-specific)

AGGREGATION:
  sales by tenant-local-day:
    T01/19 = 300,000
    T01/20 = 450,000
    T01/21 = 100,000
    T02/21 = 250,000
  sales by event-time department:
    North = 450,000
    South = 650,000

NEGATIVE TEST:
  naive SCD join -> fanout detectable
  naive order-payment join -> fanout detectable
  orphan customer -> missing match detectable
  overlap history -> multiple matches detectable
  UTC/VN day boundary -> different group detectable
~~~

These are **expected values for learners to run and verify themselves**. Having SQL queries in the article does not imply they have been executed, benchmarked, or put through a formal technical QA cycle. A separate QA pass is still needed to evaluate the lesson's overall accuracy and suitability.

## 16. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "If the SQL runs, the numbers are right." | You still have grain, JOIN cardinality, time, and measure definitions to verify. |
| "With FOREIGN KEYs, a JOIN cannot multiply rows." | FKs do not stop joining two 1–N relationships into an N–M fanout. |
| "One customer_code is one customer, so joining once is safe." | SCDs hold multiple versions per business key; an AS-OF condition is required. |
| "Having customer_sk in the fact means no temporal testing is needed." | A surrogate key can be assigned to the wrong point-in-time version even when the FK is valid. |
| "A proper N–1 JOIN always preserves row count." | You must still check 0 matches and >1 matches; OUTER JOINs also introduce null cases. |
| "Any JOIN that increases row count is wrong." | A 1–N JOIN can intentionally produce child rows; judge against the target grain. |
| "If payment total equals sales total after a JOIN, it's correct." | Both totals may have been equally doubled. |
| "COUNT(*) equals the number of orders." | `COUNT(*)` counts result rows; verify the grain. |
| "COUNT DISTINCT always fixes fanout." | It can mask bugs and drop legitimate occurrences, and it does not protect SUM. |
| "Equal row counts mean nothing was lost or duplicated." | One row can be dropped while another is duplicated; compare key sets. |
| "If period-wide SUM matches, every group matches." | Values may have swapped across tenants, days, or departments. |
| "Group rates can be summed or averaged." | Usually you must sum numerators and denominators, then divide per the definition. |
| "End-of-day balances can be SUMmed across multiple days." | Balances are semi-additive over time. |
| "SCD intervals have valid_to, so BETWEEN is convenient." | `BETWEEN` is inclusive on both ends and can match two versions at the boundary. |
| "No overlaps means a dimension exists at all times." | Gaps can still exist; test coverage according to business rules. |
| "Casting DATE from TIMESTAMPTZ always gives the same date." | Date casting depends on session timezone unless explicitly specified. |
| "If an old report differs from a new one, one of them must be buggy." | They may differ due to input cutoffs, corrections, or metric versions. |
| "Valid time alone is enough to reproduce any published report." | Retroactive corrections require knowledge time / snapshots or bitemporal history. |
| "When source data changes, updating the dimension table is enough." | Aggregates and materialized views must be restated, reconciled, and published by version. |
| "Running tests on clean data is enough." | Negative tests prove that validation checks catch the intended faults. |

## 17. Key Takeaways

**JOIN correctness** starts with **grain and cardinality**. When an order line is joined to multiple payment events or multiple dimension versions, **SUM and COUNT can inflate without any syntax error**. Check match counts **per fact key**, use **EXISTS** when testing existence only, **pre-aggregate each fact to the same grain before joining**, and reconcile **key sets, row values, groups, and source totals**.

**Aggregation correctness** depends on measure definitions. Line amounts can be summed across independent lines; unique customer counts cannot be summed across overlapping groups; ratios must be computed from numerators and denominators; snapshot balances must not be summed across timestamps. A correct system-wide total does not guarantee correct breakdowns by tenant or department.

**Temporal correctness** requires separating **business keys** from **version keys**, using **[valid_from, valid_to)** intervals and **AS-OF joins at transaction time**, and checking overlaps, gaps, day boundaries, and timezones. When retroactive corrections happen, separate **"what was true at time T"** from **"what the system knew about T at time K"**, preserving versions so you can reproduce or restate cleanly for the intended purpose.

A reliable validation workflow is **write a data contract → build fixtures with counterexamples → test keys and match counts → reconcile metrics at grain → test temporal boundaries → validate on real data under matching snapshots/versions → sign off cutover and monitor continuously**. That is how you turn a plausible-looking data diagram into a design that is **provable, testable, and safe to evolve**.
