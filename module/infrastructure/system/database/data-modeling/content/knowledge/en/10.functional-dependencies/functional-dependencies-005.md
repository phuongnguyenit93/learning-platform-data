# Do Not Infer Dependency Rules from Sample Rows Alone

## Learning Objectives

In the **DATABASE_DATA_MODELING** module, a key task is turning business requirements into verifiable entities, relationships, keys, constraints, and physical schemas. A common mistake at this stage is looking at a few rows of data, noticing that one column appears to determine another, and assuming it is a **functional dependency** (FD) that must hold across the entire system.

This lesson in the **Data Dependencies** topic helps you:

- Distinguish **business-guaranteed functional dependencies** from **accidental patterns** in existing data.
- Explain why sample data can **refute** a dependency but cannot **prove** it holds for all valid data.
- Recognize causes of false inference: small samples, near-unique keys, identifier scope, history, missing values, and unrepresentative data.
- Use SQL to **discover candidates and counterexamples**, then verify them with business questions.
- Translate confirmed dependencies into appropriate keys, constraints, normalization, and history tracking.

## 1. Functional Dependencies Are Rules Over All Valid Data States

Consider relation \(R(U)\), where \(U\) is the set of attributes. A functional dependency:

\[
X\rightarrow Y \quad (X,Y\subseteq U)
\]

means: **in every valid data state of the relation**, if two records agree on all attributes in \(X\), they must agree on all attributes in \(Y\).

\[
\forall r\text{ valid},\ \forall t_1,t_2\in r:
\quad t_1[X]=t_2[X]\Rightarrow t_1[Y]=t_2[Y].
\]

For example, if business policy states that **each order ID belongs to a single customer**, then:

~~~text
order_id → customer_id
~~~

The substance of the rule is: the system **must not contain** two valid rows with the same `order_id` but different `customer_id`. The fact that there are currently only three orders and all three satisfy the rule is not the reason to assert it. The reason lies in **the meaning of the order ID and business policy**.

A functional dependency is a statement about **determined uniqueness**, not necessarily a calculation formula and not necessarily a causal relationship. Multiple distinct order IDs can map to the same customer ID, so `order_id → customer_id` **does not imply** `customer_id → order_id`.

### Two Levels of Checking That Are Easily Confused

| Level | Question | Value of the result |
|---|---|---|
| **Concrete data state** \(r\) | Are there two rows with the same \(X\) and different \(Y\) in this dataset? | Detects violations **in the sample** |
| **Schema and business rules** \(R,F\) | Must all future valid states satisfy \(X\rightarrow Y\)? | Establishes **design constraints** |

Finding no counterexample at the first level is **not enough** to draw a conclusion at the second level.

## 2. Example: Three Rows Make Several False Dependencies Look True

Suppose a transaction export consists of:

~~~text
ORDER_LINE(
    order_id, line_no, customer_id,
    product_id, quantity, unit_price_at_sale
)
~~~

Each row represents **one product on one line of an order**. Initially, the analysis team has only three rows:

| order_id | line_no | customer_id | product_id | quantity | unit_price_at_sale |
|---|---:|---|---|---:|---:|
| DH01 | 1 | KH01 | SP01 | 2 | 10000 |
| DH02 | 1 | KH01 | SP01 | 1 | 11000 |
| DH03 | 1 | KH02 | SP02 | 3 | 20000 |

On this sample, **none** of the following statements yet has a counterexample:

~~~text
order_id → customer_id
order_id → product_id
order_id → quantity
order_id → unit_price_at_sale
~~~

Because each `order_id` **appears only once**, any attribute on the right-hand side will have a unique value for each order ID in the sample. This is called **vacuous satisfaction** due to no repetition on the left-hand side.

Suppose the next day the system receives another completely valid row:

| order_id | line_no | customer_id | product_id | quantity | unit_price_at_sale |
|---|---:|---|---|---:|---:|
| DH01 | 2 | KH01 | SP02 | 1 | 22000 |

Now the two rows of `DH01` have the **same order ID** but different `product_id`, `quantity`, and `unit_price_at_sale`. Those dependencies that looked true earlier are refuted on the expanded dataset:

~~~text
order_id ↛ product_id
order_id ↛ quantity
order_id ↛ unit_price_at_sale
~~~

Conversely, both `DH01` rows still have `customer_id = KH01`. This is **consistent** with `order_id → customer_id`, yet by itself it does not prove the rule. To adopt that rule for design, we must confirm: "**By business definition, an order can only be attached to one customer at the time in question.**"

In the same example, `product_id → unit_price_at_sale` **already had a counterexample in the very first sample**: `SP01` was sold at 10000 and 11000. If both transactions are valid, the price at sale time cannot be determined solely by product ID.

### Lesson About Grain

If each row represents **one order**, `order_id` can be the table's key. If each row is **one line item**, the natural key typically consists of `(order_id, line_no)` under the rule that line numbers are unique within each order.

Sampling only the first line of each order **hid the actual grain** and created the illusion that order ID determines every attribute on the row. Always confirm "**what does one record represent?**" before inferring dependencies.

## 3. Why Sample Data Cannot Prove a Dependency

Suppose \(r\) is the current dataset and no two rows are found with the same \(X\) and different \(Y\). We can only assert:

\[
r\models X\rightarrow Y.
\]

This states that **data state \(r\)** satisfies the dependency; it does not imply that **all business-valid states** satisfy it. A future valid state \(r'\) can contain a case that has never appeared before.

### Sources of Functional Dependency Illusions

| Phenomenon | What the sample tricks us into thinking | Counterexample or question to check |
|---|---|---|
| **Non-repeating left-hand side** | `order_id → product_id` because each order has one row in the sample | What happens when one order has multiple product lines? |
| **Filtered sample** | `customer_id → country` in a dataset containing only customers in Vietnam | Does the full dataset include customers who changed address or live in other countries? |
| **Two attributes coinciding by chance** | `job_title → salary` across five employees on the same pay grade | Can one job title have multiple salary levels? |
| **Identifier unique only within a scope** | `invoice_no → total` when looking at data from a single store | Can two stores share the same invoice number? |
| **Current data differs from historical data** | `customer_id → customer_name` in the latest snapshot | Does a history table store multiple names over time? |
| **Missing values or inconsistent normalization** | Only one non-NULL `Y` value seen per `X` | NULL rows are missing data, not evidence for uniqueness |
| **Pre-aggregated table** | `product_id → total_sales` in a single-period report | If there are multiple dates or markets, what scope attributes are needed? |

**Even a hundred thousand rows can mislead** if all data is filtered to a single state or if every \(X\) value appears only once. Large sample size is no substitute for business understanding.

### Distinguishing Correlation, Formulas, and Functional Dependencies

- "Sale prices usually rise over time" is a **trend** description, not a functional dependency.
- "The `total` field is computed as `quantity × unit_price`" is a calculation rule. If the inputs and rounding rules are strictly defined, a dependency from the input attributes to `total` can be derived; however, you must verify whether taxes, discounts, shipping, or adjustments also apply.
- "Each order ID determines one customer" is an **identification** rule, well suited for representation as a functional dependency.

A functional dependency requires **strict determinism across the valid data domain**. High-probability statistical relationships that occasionally fail are not exact functional dependencies.

## 4. A Counterexample in Data: Verify Validity Before Concluding

Mathematically, a set of rows containing two records with the same \(X\) and different \(Y\) is a **counterexample** to \(X\rightarrow Y\) on that row set. In a real system, however, a counterexample in a staging table can also be:

- **Corrupted data:** two rows with the same `order_id` but different `customer_id` due to a faulty sync job.
- **Missing scope attribute:** the same `invoice_no = 001` in two stores; the true rule may be `(store_id, invoice_no) → invoice_date`.
- **Mixed versions:** old and new records of an entity stored together; the key of a **historical record** must include an appropriate version or effective timestamp.
- **Semantic misunderstanding:** `customer_name_at_order` is a snapshot captured at purchase time; the same `customer_id` can appear with different names on different orders.
- **Duplicates from bad ETL/joins:** joining on an insufficient key causes a transaction to be duplicated or attached to wrong details.

Therefore, separate two questions:

1. **Does this data state violate the dependency?** — checked directly via query.
2. **Is the dependency rule wrong from a business standpoint?** — conclude only after verifying that the violating rows are **valid and allowed to exist**.

For example, if policy confirms `order_id → customer_id` and staging contains two customer IDs for the same order ID, that is a **data error to fix**. Do not silently change the rule to `(order_id, line_no) → customer_id` just to make the violations disappear.

## 5. Scope and Time Can Completely Change the Left-Hand Side

### Case A — Identifiers Across Multiple Stores

Business rule: "Invoice numbers increment from 1 in each store and may collide across stores."

**Do not infer**:

~~~text
invoice_no → invoice_date
~~~

A better-grounded rule may be:

~~~text
(store_id, invoice_no) → invoice_date
~~~

If invoice numbers reset each year, you must also confirm `fiscal_year` or a global identifier. Do not add columns blindly without knowing the numbering policy.

### Case B — Current Data vs. Historical Data

A table `CUSTOMER_CURRENT(customer_id, customer_name)` holds only the **current name**. When each customer ID has one current record, we have:

~~~text
customer_id → customer_name
~~~

In `CUSTOMER_NAME_HISTORY(customer_id, valid_from, customer_name, valid_to)`, the same customer can change names multiple times. Then:

~~~text
customer_id ↛ customer_name
~~~

If each `(customer_id, valid_from)` uniquely identifies a version, we can confirm:

~~~text
(customer_id, valid_from) → customer_name, valid_to
~~~

Assuming `customer_id → customer_name` over the **entire history table** confuses "one value at any given time" with "one value across all time". An ordinary functional dependency does not express **non-overlapping time intervals** on its own; that is a temporal constraint requiring separate enforcement.

### Case C — Current Price vs. Sold Price

- `(product_id, price_list_id, effective_from) → list_price` may be valid if a price list identifies each version by this attribute tuple.
- `product_id → unit_price_at_sale` is usually false for a transaction detail table, because a product can sell under different promotions, customers, or times.
- `(order_id, line_no) → unit_price_at_sale` can hold when each order line records one transaction price.

Columns with similar-looking names do not necessarily obey the same dependencies. **Business semantics and grain** determine the left-hand side.

## 6. Using SQL to Explore Candidates and Find Counterexamples

The queries below are for **data profiling**, not self-certifying rules. Assume staging table:

~~~text
staging_order_lines(
    order_id, line_no, customer_id, product_id, unit_price_at_sale
)
~~~

### 6.1. Find Groups with the Same \(X\) but Different \(Y\)

To check whether existing data contains counterexamples to `order_id → customer_id`:

~~~sql
SELECT
    order_id,
    COUNT(*) AS row_count,
    COUNT(DISTINCT customer_id) AS distinct_customer_count
FROM staging_order_lines
WHERE order_id IS NOT NULL
  AND customer_id IS NOT NULL
GROUP BY order_id
HAVING COUNT(DISTINCT customer_id) > 1;
~~~

Each returned row is an `order_id` appearing with **at least two distinct non-NULL customer IDs**. Inspect the source records for those IDs to verify the data and business semantics.

Here `WHERE ... IS NOT NULL` states the **scope of the check**. If fields can be missing, check missing data and `NOT NULL` rules separately; excluding `NULL` does not prove a dependency across the whole table.

### 6.2. Check Observability: Do Any \(X\) Groups Repeat?

Even when there are no violations, check whether the data actually had enough opportunity to expose a false dependency:

~~~sql
WITH groups_by_order AS (
    SELECT
        order_id,
        COUNT(*) AS row_count,
        COUNT(DISTINCT product_id) AS distinct_products
    FROM staging_order_lines
    WHERE order_id IS NOT NULL
      AND product_id IS NOT NULL
    GROUP BY order_id
)
SELECT
    COUNT(*) AS orders_observed,
    SUM(CASE WHEN row_count > 1 THEN 1 ELSE 0 END)
        AS orders_with_multiple_rows,
    SUM(CASE WHEN distinct_products > 1 THEN 1 ELSE 0 END)
        AS orders_with_multiple_products
FROM groups_by_order;
~~~

If `orders_with_multiple_rows = 0`, the dependency `order_id → product_id` **has not been meaningfully tested** by the sample because every left-hand value appears once. If `orders_with_multiple_products > 0`, a counterexample already exists in the inspected data.

**Be careful:** `row_count > 1` is sometimes merely caused by duplicate rows from ETL; repeated rows do not guarantee multiple independent business events. Inspect `line_no` and row lineage as well.

### 6.3. Retrieve Specific Conflicting Records

~~~sql
WITH conflicting_orders AS (
    SELECT order_id
    FROM staging_order_lines
    WHERE order_id IS NOT NULL
      AND customer_id IS NOT NULL
    GROUP BY order_id
    HAVING COUNT(DISTINCT customer_id) > 1
)
SELECT
    s.order_id,
    s.line_no,
    s.customer_id,
    s.product_id
FROM staging_order_lines s
JOIN conflicting_orders c
    ON s.order_id = c.order_id
ORDER BY s.order_id, s.line_no;
~~~

The query returns the rows needing investigation, helping determine whether it is a **data entry error**, **bad join**, or **valid exception**.

### 6.4. Check a Proposed Business Key

If `(order_id, line_no)` is assumed unique at the line-item level:

~~~sql
SELECT
    order_id,
    line_no,
    COUNT(*) AS occurrences
FROM staging_order_lines
GROUP BY order_id, line_no
HAVING COUNT(*) > 1;
~~~

Any returned rows are duplicate keys in the sample. However, a clean dataset does not prove the uniqueness rule is **correct for the business**. In addition, check whether `order_id` and `line_no` may be `NULL` before implementing the key.

### Interpreting Results Appropriately

| Observation from profiling | What can be concluded | What cannot be concluded |
|---|---|---|
| No group has two different \(Y\) values | The inspected sample **has no counterexample yet** within query scope | \(X\rightarrow Y\) is a global rule |
| Two different \(Y\) values exist for the same \(X\) | The inspected rows **do not jointly satisfy** \(X\rightarrow Y\) | Business policy is wrong, before verifying the data |
| Every \(X\) appears exactly once | The sample lacks power to distinguish many false dependencies | \(X\) is definitely a candidate key |
| Many \(X\) groups repeat and all share the same \(Y\) | The sample provides supporting evidence for a **candidate** | The dependency will always hold in the future |

Counts also have limitations around string normalization, collation, whitespace, and representation of missing values. These issues must be handled consistently according to the DBMS in use.

## 7. Workflow to Verify Dependencies from Business Requirements

Instead of taking a dependency list straight from statistics, build a **profile for each candidate dependency**.

### Step 1 — Determine Grain and Attributes

Ask: "Does one row represent **an order**, **an order line**, **a version**, or **a change event**?" Record data point-in-time and organizational scope. A dependency can hold at the order level yet fail at the line-item level.

### Step 2 — Write a Falsifiable Rule Statement

Turn a vague sentence like "each customer usually has one address" into a testable statement:

> "In the **current default shipping address** table, each `customer_id` has at most one `default_shipping_address_id` at any one time."

This is only an **example statement to confirm**; if the business allows multiple default addresses per sales channel, an appropriate scope must be added.

### Step 3 — Actively Hunt for Exceptions

Ask the business owner:

- Can two distinct entities share the same code \(X\)?
- Are codes issued globally, per store, per year, or per organization?
- Can one entity have multiple \(Y\) values at the same time?
- When \(Y\) changes, does the system **overwrite** or **store multiple versions**?
- Is data imported from systems with different identification conventions?

It is the "awkward" or rare cases that distinguish true dependencies from coincidence.

### Step 4 — Use Data Exploration to Support Verification

Check across multiple periods, multiple branches, and data before and after business rule changes. Inspect duplicate \(X\) groups, counterexamples, NULL rates, and source records. If violations are found, **classify their root cause** before changing the design.

### Step 5 — Document and Approve Assumptions

Every dependency brought into the design needs a definition, scope, rule owner, and enforcement plan. Example:

| Field | Example entry |
|---|---|
| Candidate | `order_id → customer_id` |
| Definition | Each order has one owning customer |
| Grain | Order header records and their order lines |
| Scope | `order_id` globally unique across the system |
| Time | Current order state; change history stored separately if needed |
| Exceptions | Two current customers on one order are not permitted |
| Confirmed by | Order process owner |
| Enforcement mechanism | `orders.order_id` primary key; `customer_id` column on `orders` |
| Supporting evidence | Business rule + data quality violation query |

If the owner has not confirmed it yet, mark it **"unverified assumption"**. Do not treat a candidate as an established dependency when computing keys, minimal covers, or normalization.

## 8. Consequences of Putting False Dependencies into a Design

### 8.1. Choosing the Wrong Candidate Key

A sample with one product per order makes `order_id` look like the key of the line-item table. If you declare `PRIMARY KEY(order_id)`, adding a second product line to an order will **fail to insert**; or developers will be forced to overwrite existing data.

The right key must follow the rule "line numbers do not repeat within an order", i.e., `(order_id, line_no)` in the example.

### 8.2. Wrong Normalization and Decomposition

Suppose you assume `product_id → unit_price_at_sale` and move `unit_price_at_sale` into `PRODUCTS`. Historical transaction prices when discounts apply or price lists change may get **overwritten**, corrupting invoices and reports.

Conversely, the real dependency `order_id → customer_id` should be represented in `ORDERS` to prevent repetition and conflicting customer IDs across lines.

### 8.3. Enforcing Constraints That Are Too Strict or Too Loose

- An **overly strict** constraint like `UNIQUE(order_id, product_id)` blocks valid cases where one product appears on multiple lines in an order.
- An **overly loose** constraint like dropping a business key just because staging had dirty data lets invalid states keep being written.

Database constraints should reflect **confirmed rules**, not the accidental condition of today's data.

### 8.4. SQL Design Example Based on Confirmed Grain

Suppose each order has one current customer and line numbers are unique within each order:

~~~sql
CREATE TABLE customers (
    customer_id VARCHAR(30) PRIMARY KEY,
    customer_name VARCHAR(200) NOT NULL
);

CREATE TABLE products (
    product_id VARCHAR(30) PRIMARY KEY,
    product_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id VARCHAR(30) PRIMARY KEY,
    customer_id VARCHAR(30) NOT NULL REFERENCES customers(customer_id),
    order_date DATE NOT NULL
);

CREATE TABLE order_items (
    order_id VARCHAR(30) NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id VARCHAR(30) NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_sale DECIMAL(12, 2) NOT NULL
        CHECK (unit_price_at_sale >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

This schema enforces the confirmed dependencies:

~~~text
order_id            → customer_id, order_date
product_id          → product_name
customer_id         → customer_name
(order_id, line_no) → product_id, quantity, unit_price_at_sale
~~~

Sale-time price stays on the **transaction line**. `PRIMARY KEY`, `FOREIGN KEY`, `NOT NULL`, and `CHECK` work together to guard different categories of rules; functional dependencies **do not replace** all domain and referential integrity constraints.

## 9. Automated Dependency Discovery: Useful, but Must Be Confirmed

*Data profiling* or *functional dependency discovery* tools can scan data and output:

~~~text
candidate: X → Y
support: number of observable X groups
violations: number of X groups with two or more distinct Y values
null_rate: rate of missing data in X/Y
scope: source, time range, and filters of the sample
~~~

This is a **candidate list and data evidence**, not a business contract. Pay special attention to:

- A near-unique column causes **a huge number of spurious dependencies** to report zero violations.
- An *approximate FD* permits an exception rate; it does not have the same meaning as a hard FD constraint that must always hold.
- Results can change when expanding data sources, adding time periods, or including rare exception records.
- An anomaly flagged as a "statistical outlier" may turn out to be the most important **valid business case** the model needs to support.

If the design requires the system to **enforce** a dependency, there must be a confirmed rule statement. Never add `UNIQUE` just because a profiling tool reports "99.9% confidence".

## 10. Applying This Mindset to Other Modeling Approaches

In the **relational model**, functional dependencies are a formal concept used for key identification and normalization.

In a **document model**, embedded data may be chosen for query optimization, yet you must know which fields are historical snapshots and which are current information. One order document does not mean an order ID can contain only one product.

In a **graph model**, nodes can have system IDs, business IDs, and mutable attributes. Seeing no duplicate `external_id` across nodes in a sample export does not prove `external_id` is a globally unique key across the graph.

In an **analytical model**, fact table grain, time dimension, partitioning, and dimension versioning determine whether a column combination genuinely identifies an event. A monthly summary table cannot serve as direct evidence for dependencies in a detailed event table.

The common thread is establishing **grain, identifier scope, history, and exceptions** before choosing structures or optimizing indexes. Each storage engine has different constraint enforcement mechanisms; never assume SQL constraints are enforced identically in document or graph databases.

## 11. Practice Exercises with Solutions

### Exercise 1 — Coincidental Dependency from a Unique Left-Hand Side

Given data `SALES(order_id, product_id)`:

| order_id | product_id |
|---|---|
| D1 | P1 |
| D2 | P2 |
| D3 | P3 |

**Question:** Can we assert `order_id → product_id` as a business rule?

**Solution:** No. The sample satisfies the dependency only because each `order_id` appears once. If a valid order can have multiple products, the dependency will fail on a detail table. You must ask "is one row an order or a line item?" and whether an order can contain multiple products.

### Exercise 2 — Counterexamples and Data Quality

A staging table has:

~~~text
(order_id = D1, customer_id = C1)
(order_id = D1, customer_id = C2)
~~~

The business process confirms each order belongs to only one customer. What should you do?

**Solution:** The two rows are a counterexample **in staging**. Inspect source systems, history, and join logic; fix the corrupted data or buggy sync job per process. Do not unilaterally rewrite the rule to `(order_id, customer_id) → ...` and drop `order_id → customer_id` if the business does not allow multiple customers on one order.

### Exercise 3 — Keys Scoped by Organization

Three stores all use invoice number `0001`. In a single-store sample, `invoice_no → invoice_date` shows zero violations. Propose the dependency to verify when combining chain-wide data.

**Solution:** Test and verify `(store_id, invoice_no) → invoice_date` if invoice numbers are unique within each store. If numbers reset annually, you must also confirm a time scope or a global invoice ID. Do not extrapolate `invoice_no → invoice_date` from a single-store sample.

### Exercise 4 — Current Information vs. History

Customer `KH01` had the name "An" in 2024 records and "An Nguyễn" after a name change in 2026. Does `customer_id → customer_name` hold?

**Solution:** On a **multi-version history** table, no. On a table **holding only current records**, it can hold if each customer ID has exactly one current name. If using a versioned history table, you must confirm a composite key like `(customer_id, valid_from)`; non-overlapping effective-date intervals require a separate modeling mechanism.

### Exercise 5 — Large Dataset That Still Lacks Diagnostic Power

A tool reports "`receipt_id → product_id`: 0 violations across 2 million rows". Further stats show there are exactly 2 million distinct `receipt_id` values. What conclusion is reasonable?

**Solution:** The sample cannot test whether a receipt can have multiple lines. Each `receipt_id` appears once, so any attribute will appear determined by it. You must check the grain, inspect true line-level data, and ask business stakeholders before making any claim.

### Exercise 6 — Query Returning 0 Rows

A query checking `COUNT(DISTINCT customer_id) > 1` grouped by `order_id` returns no rows. Can we immediately create a constraint treating `order_id` as determining `customer_id`?

**Solution:** Not enough evidence yet. You must check NULL rates, how many order IDs appear on multiple rows, whether the data covers the necessary branches and time periods, and most importantly whether the business owner confirms the one-customer-per-order rule. Only after confirmation should you choose the appropriate structure and constraint.

## 12. Checklist Before Adding a Dependency to the Model

- [ ] Correctly identified the **grain**: what entity or event one row represents.
- [ ] Defined \(X\) and \(Y\) by **business semantics**, not just column names.
- [ ] Confirmed identifier scope: system-wide, tenant, store, year, or version.
- [ ] Distinguished **current**, **transaction-time snapshot**, and **historical** attributes.
- [ ] Actively sought valid exceptions instead of looking only at typical rows.
- [ ] Used profiling to find counterexamples while recording filters, NULL rates, and left-hand repetition.
- [ ] Verified whether violating rows are data errors or valid business cases.
- [ ] Obtained confirmation from the business owner for every dependency used in design.
- [ ] Used only **confirmed dependencies** for closure, candidate keys, minimal cover, and normalization.
- [ ] Selected appropriate keys, `UNIQUE`, `FOREIGN KEY`, `NOT NULL`, `CHECK`, and history management mechanisms.

**Takeaway:** **Seeing no two rows with the same \(X\) and different \(Y\) only proves the current sample has not yet exposed a violation.** A counterexample in data can flag an issue to investigate; only a **business-valid** counterexample refutes a proposed rule. For a clear, evolvable, and verifiable data model, start from **business rules, grain, scope, and time**, and use data as supporting evidence.
