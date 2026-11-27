# When Is Normalization Enough and How to Avoid Pointless Table Splitting

## Learning Objectives

In **DATABASE_DATA_MODELING**, normalization is not a contest to create as many tables as possible or chase the highest normal form at any cost. The real goal is to translate **business rules** into a data structure that is clear, consistent, enforceable, and efficient enough for reads and writes. A good design must also evolve gracefully as the business changes, remain verifiable via constraints and tests, and fit the chosen paradigm—whether relational, document, graph, or analytical.

After this lesson, you will be able to:

1. Determine a **sensible stopping point** for normalization based on data dependencies, update anomalies, constraints, and query needs.
2. Distinguish **meaningful table decomposition** from splits that merely multiply joins.
3. Understand why reaching **3NF or BCNF** is often a solid starting point for transactional systems without being an absolute rule, and recognize when to evaluate **4NF/5NF**.
4. Weigh trade-offs among **lossless join**, **dependency preservation**, business rule enforcement, and performance.
5. Deliberately choose controlled denormalization when backed by evidence, instead of duplicating data arbitrarily.
6. Use checklists, SQL examples, and real-world scenarios to defend design decisions before implementation.

## 1. Normalization Enough for What Purpose?

**Normalization** organizes attributes and relations so that confirmed data dependencies are properly represented, reducing redundancy that causes **insertion, update, and deletion anomalies**.

However, **there is no "standard" number of tables that fits every system**. When asking "is it normalized enough?", you must answer all of the following together:

- **Semantic accuracy:** does each table clearly represent an entity, relationship, or event, and what is the grain of each row?
- **Constraint fidelity:** are the important keys, functional dependencies (FDs), multivalued dependencies (MVDs), or join dependencies (JDs) reflected and enforced?
- **Absence of harmful anomalies:** does a single business fact have to be edited across multiple independent rows (risking contradictions), and can events be recorded before related entities occur?
- **Safe decomposition:** when tables are split, do projecting and rejoining **recover the exact original data** without manufacturing spurious tuples?
- **Acceptable cost:** do primary queries, writes, operations, migrations, access controls, and history tracking meet requirements?

A pragmatic stopping point is: **all major anomalies caused by real data dependencies have been resolved; every table carries clear meaning; essential constraints are enforceable; and further splitting adds negligible value compared to its cost**.

This is a **decision criterion**, not a formal definition of a normal form.

## 2. Distinguishing "Meets a Normal Form" from "Fits the System"

| Normalization Level | Focus | Decision Question |
|---|---|---|
| **1NF** | Value domains and attribute structure in the relational model | Does each column have a clear meaning and domain, avoiding repeating groups such as `phone_1,phone_2,...`? |
| **2NF** | **Partial** dependencies of non-key attributes on candidate keys | Are attributes at a coarser grain being repeated across rows of a composite key? |
| **3NF** | Redundancy-causing functional dependencies via non-superkey attributes | Is there a non-trivial `X → A` where `X` is not a superkey and `A` belongs to no candidate key? |
| **BCNF** | Every non-trivial FD must have a superkey on the left-hand side | Is there an FD causing inconsistency despite 3NF? Does decomposing hurt dependency preservation? |
| **4NF** | Non-trivial **multivalued** dependencies | Are two independent value sets stored together as all combinations, growing data as their product? |
| **5NF** | Non-trivial **join** dependencies not implied by candidate keys | Does a true business rule allow reconstructing a multi-way relation from smaller projections? |

For **3NF**, the formal condition is that for every non-trivial FD `X → A` implied by valid rules: **`X` is a superkey or `A` is a prime attribute** (belonging to at least one candidate key). For **BCNF**, the left-hand side must be a superkey. Thus **BCNF is stronger than 3NF**, yet a BCNF decomposition can sometimes fail to preserve all FDs locally.

**Starting guideline:** many OLTP systems target **3NF as a baseline**, considering **BCNF** when the split fits cleanly and constraints remain enforceable. Evaluate **4NF/5NF** only when real multivalued or join rules cause problems. This is a **default exploration strategy**, not a claim that 3NF is always optimal or that every table must be pushed to BCNF.

### When Should You Stop Splitting?

If a table's attributes depend solely on **the table's own key**, no independent business dependency causes anomalies, and all data updates along the same lifecycle, further splitting usually brings no normalization benefit.

For example:

~~~text
ORDERS(order_id, customer_id, ordered_at, status)
~~~

If `order_id` determines all remaining attributes, `status` is the **current status of the order**, and no other FDs exist among those attributes, splitting into:

~~~text
ORDERS(order_id, customer_id, ordered_at)
ORDER_STATUS(order_id, status)
~~~

solves no normalization anomaly. The two tables join one-to-one on `order_id`, while adding extra writes, foreign keys, and a join just to read a complete order.

That **does not mean every one-to-one split is wrong**: you might split for security isolation, large rarely read columns, separate ownership, update frequency differences, or independent lifecycles. In those cases, the reason is **architecture, operations, or access control**, not a normalization FD forcing a split.

## 3. Case Requiring Normalization: A Flat Order Table

Suppose initial sales data is exported as a single table:

~~~text
ORDER_LINE_FLAT(
    order_id, ordered_at,
    customer_id, customer_name_current,
    line_no, product_id, product_name_current,
    quantity, unit_price_at_sale
)
~~~

**Grain:** each row is **one product line of an order**, not one order.

Confirmed business rules:

~~~text
order_id             → ordered_at, customer_id
customer_id          → customer_name_current
product_id           → product_name_current
(order_id, line_no)  → product_id, quantity, unit_price_at_sale
~~~

Assume `order_id` is globally unique, `line_no` is unique **within an order**, and customer and product names in the flat table represent **current information**. The same product can be sold many times at different unit prices.

### Data Anomalies in the Flat Table

| Issue | Symptom | Cause |
|---|---|---|
| Update | Customer changes name, yet only some order lines get updated | `customer_name_current` is repeated across many rows despite depending on `customer_id` |
| Update | Renaming a product requires updating thousands of historical rows | Current product details sit inside individual transaction lines |
| Insertion | Hard to create an order before adding products if `line_no` is required | Mixes **order** grain and **order-line** grain |
| Deletion | Deleting the last line item can wipe out the entire order record | Order info exists only inside line items |
| Inconsistency | Two lines of the same order hold different `customer_id`s | Table permits violating `order_id → customer_id` without extra checks |

Here, normalization has a **clear purpose** because it separates facts with **different keys and lifecycles**.

### Justified Decomposition

~~~text
CUSTOMERS(customer_id, customer_name_current)
PRODUCTS(product_id, product_name_current)
ORDERS(order_id, ordered_at, customer_id)
ORDER_ITEMS(order_id, line_no, product_id, quantity, unit_price_at_sale)
~~~

Under the rules above:

- `customer_id` identifies a customer and their current name.
- `product_id` identifies a product and its current name.
- `order_id` identifies **order-level** facts.
- `(order_id,line_no)` identifies **line-item-level** facts.

This decomposition is grounded in FDs, rather than arbitrarily splitting tables out of a gut feeling that "the table has too many columns."

### SQL Schema Example

~~~sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    customer_name_current VARCHAR(200) NOT NULL
);

CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    product_name_current VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    ordered_at TIMESTAMP NOT NULL,
    status VARCHAR(30) NOT NULL
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_at_sale DECIMAL(12, 2) NOT NULL
        CHECK (unit_price_at_sale >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Adding `status` to `orders` serves the **current** order status; it does not require a separate table without a concrete need. `unit_price_at_sale` stays on the order line because it is a **transaction unit price**, not an attribute determined by `product_id` across all orders.

In the deployed schema, an order can exist before it has line items. That is a **new valid business state the split model can represent**; it does not contradict the lossless decomposition of the initial flat table under the assumed FDs. If the business forbids empty orders, enforce that via application workflow or constraints beyond simple foreign keys.

## 4. Decomposition Must Prove Two Distinct Properties

### 4.1. Lossless Join

A decomposition \(R(U)\rightarrow R_1(U_1),\ldots,R_n(U_n)\) is lossless under the confirmed constraints if:

\[
\forall r\text{ valid},\quad
r=\pi_{U_1}(r)\bowtie\cdots\bowtie\pi_{U_n}(r).
\]

This guarantees that projecting and rejoining **recovers the exact tuples of the original table**, generating no **spurious tuples**.

For a **binary decomposition under FDs**, the necessary and sufficient condition is:

\[
(U_1\cap U_2)\rightarrow U_1
\quad\text{or}\quad
(U_1\cap U_2)\rightarrow U_2
\]

is implied by the FD set \(F\). For instance, splitting order and order-item data on `order_id` is lossless when `order_id → ordered_at, customer_id` holds and the two child relations are formed by proper projections.

For multi-relation decompositions, prove losslessness via a **sequence of lossless binary splits** or the *chase* method. When MVDs or JDs apply, use the appropriate dependency type; never equate "fails the two-table FD test" with "always lossy."

### 4.2. Dependency Preservation

A decomposition can join accurately yet force checking an original FD to **join multiple tables**. The two criteria are distinct:

| Criterion | Question | Practical Consequence If Unmet |
|---|---|---|
| **Lossless** | Do projections followed by a join recover the **exact data**? | Generates spurious tuples or loses true combinations |
| **Dependency preservation** | Can the original FDs be inferred from FDs checked on **individual child tables**? | Requires cross-table checks, triggers, or other workflows |

Formal example:

~~~text
R(A,B,C)
F = { AB → C, C → B }
~~~

Splitting into `R1(C,B)` and `R2(A,C)` is **lossless** because the intersection `C` determines `B`. Yet the dependency `AB → C` **is not preserved by local FDs alone**.

Therefore, **do not split further merely to reach BCNF** if losing table-level enforcement of a critical rule forces the system into harder cross-table exception handling. Standard **3NF synthesis** guarantees both lossless join and FD preservation; that is a sound reason to stay at 3NF in certain designs.

## 5. Signs of Pointless Table Splitting

### 5.1. One Table per Field

Consider this design:

~~~text
USER_IDENTITY(user_id, email)
USER_DISPLAY_NAME(user_id, display_name)
USER_TIMEZONE(user_id, timezone)
USER_PREFERENCES(user_id, theme)
~~~

When all of these are single-valued current attributes updated in the same user lifecycle, and the only rule is:

~~~text
user_id → email, display_name, timezone, theme
~~~

splitting into four tables **resolves zero partial or transitive dependencies**. It increases join counts, risks missing satellite records, and complicates transactions.

A single table:

~~~text
USERS(user_id, email, display_name, timezone, theme)
~~~

is already sufficiently normalized. If `email` is confirmed unique by the business, add `UNIQUE(email)`; there is no need to create a separate email table merely to enforce uniqueness.

**Justified exceptions:** isolating sensitive fields to restrict read permissions, separating very large rarely accessed blobs, separating data owned by another subsystem, or storing multi-version history.

### 5.2. Turning "Every Noun" into an Independent Entity

Street names, colors, or statuses do not automatically deserve separate lookup tables. Before creating `STATUS_LOOKUP`, `COLOR_LOOKUP`, or `UNIT_LOOKUP`, ask:

- Does the value have **its own identifier and lifecycle**?
- Does it carry descriptions, hierarchies, state-transition rules, translations, or dedicated owners?
- Is **consistent referencing** needed in many places, or is it just a small, stable value domain?
- Can it be enforced with a `CHECK`, a suitable enum type, or application validation?

If the answer is "just to give the table fewer columns," the split is likely pointless. If a status carries **its own approval workflow and operational configuration**, an entity/status table may be warranted.

### 5.3. Abusing Surrogate IDs to Hide Business Keys

Example:

~~~text
ENROLLMENTS(enrollment_id, student_id, course_id, enrolled_at)
~~~

If the business states **a student may enroll in a course at most once**, adding `enrollment_id` as the primary key **does not remove the requirement** that `(student_id,course_id)` be unique. You must retain `UNIQUE(student_id,course_id)` with appropriate non-NULL columns.

If retakes are allowed, confirm the new business key, e.g., `(student_id,course_id,attempt_no)`. Never add a surrogate ID and accept meaningless duplicate records.

### 5.4. Splitting Based on a Dependency Inferred from Sample Data

A sample where each order happens to contain only one product makes `order_id → product_id` look true. If you split `ORDER_PRODUCTS(order_id,product_id)` allowing one product per order, the model will block or corrupt multi-line orders. **FDs must come from business rules**, not coincidences in sample data.

### 5.5. Using EAV Models Without Real Need

`ENTITY_ATTRIBUTE_VALUE(entity_id,attribute_name,value)` can suit dynamic attributes rarely defined up front, yet using it in place of a stable product table undermines data types, `NOT NULL`, `CHECK`, candidate keys, indexes, and queries.

"Every table has three columns" does not mean "well normalized." When a business schema is stable, strongly typed columns are usually far easier to verify and operate.

## 6. When Values Are Multi-Valued: Split True Relationships, Not Attributes Arbitrarily

Suppose a user has multiple shipping addresses:

~~~text
USER_SHIPPING_ADDRESSES(
    user_id, address_id, recipient_name, street, city, is_default
)
~~~

Because a person can have multiple addresses, this is a **child entity set**, not a single-valued attribute of `USERS`. A separate table makes sense because each address has its own identity, lifecycle, and attributes.

Conversely, a single current address with `street, city, postal_code` does not have to be split into three tables just because it spans three columns. It can live in the parent table or a value object depending on usage and business requirements.

### Two Independent Sets and 4NF

Consider:

~~~text
EMPLOYEE_PROFILE(employee_id, skill, language)
~~~

If each employee has multiple **skills** and multiple **languages** that are **independent**, skill–language combinations can grow the table as the product of their counts. The multivalued dependency `employee_id ↠ skill` leads to decomposing into:

~~~text
EMPLOYEE_SKILLS(employee_id, skill)
EMPLOYEE_LANGUAGES(employee_id, language)
~~~

This split is **purposeful**: it eliminates MVD redundancy and achieves 4NF under the confirmed rules.

However, if `SKUS(product_id,color,size)` stores only **color–size variants actually sold**, you must never split it into a colors list and a sizes list and rejoin all combinations. Joining would manufacture nonexistent variants. Splitting under 4NF/5NF requires a **grounded MVD/JD**, not merely seeing two multi-valued columns.

## 7. A Crucial Exception: Historical Data and Transaction Snapshots

Normalization does not mean "forbid repeating a value in any table." Distinguish **current values** from **point-in-time event values**.

Example:

~~~text
PRODUCTS(product_id, current_name, current_list_price)
ORDER_ITEMS(order_id, line_no, product_id, product_name_at_sale,
            quantity, unit_price_at_sale)
~~~

A product's current name can change. Yet an issued invoice must show **the name and price at sale time**. In `ORDER_ITEMS`, snapshot values are determined by the **transaction line key**, such as `(order_id,line_no)`; they are **not required** to obey `product_id → product_name_at_sale` across all transactions.

Refusing to store a snapshot because "there is already a products table" causes historical reports to mutate whenever the product catalog changes. This is **intentional duplication with different temporal semantics**, not a normalization anomaly.

Always document clearly:

- Source of truth for **current data** is the product table.
- Source of truth for **transaction snapshots** is the transaction record at confirmation time.
- Snapshot rules: written once at checkout, whether corrections are allowed, and how audit trails work if amended.
- Queries must explicitly choose the current column vs. the event-time column.

Similarly, a **status history table** `ORDER_STATUS_EVENTS(order_id,event_no,status,occurred_at)` is warranted when recording every state transition. That is completely different from splitting `ORDERS.status` into a one-to-one table just to "normalize more."

## 8. How Many Joins Are Acceptable?

The slogan "joins are slow" is not enough to reject normalization; "normalized is always fast" is equally false. Performance depends on row counts, predicate selectivity, indexes, many-to-many joins, query patterns, and the DBMS.

Example order-detail query:

~~~sql
SELECT
    o.order_id,
    o.ordered_at,
    c.customer_name_current,
    i.line_no,
    p.product_name_current,
    i.quantity,
    i.unit_price_at_sale
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
JOIN order_items AS i
    ON i.order_id = o.order_id
JOIN products AS p
    ON p.product_id = i.product_id
WHERE o.order_id = 1001
ORDER BY i.line_no;
~~~

A query with several `JOIN`s along **primary/foreign keys** can perform well with proper indexes and statistics. Re-merging all columns into a flat table just to avoid joins reintroduces update anomalies and storage bloat.

Conversely, if analytical reports must join dozens of many-to-many relations across billions of rows, a **dedicated** read model such as a materialized view or data mart may be appropriate.

### What to Measure Before Splitting or Merging

Define concrete metrics:

| Metric Category | Examples to Measure | Meaning |
|---|---|---|
| Reads | p50/p95/p99 latency, rows scanned, CPU/I/O time | Are joins truly the bottleneck? |
| Writes | Rows modified per operation, lock contention, deadlocks, transaction count | Does duplicated data force multi-row writes or sync bugs? |
| Storage | Table/index size, growth rate, intermediate row counts | How does splitting/merging impact footprint? |
| Correctness | Constraint violations, sync drift, orphaned records | Which model minimizes contradiction risk? |
| Evolution | Services affected by schema changes, migration complexity | Does splitting actually reduce coupling? |

Use query plans such as `EXPLAIN` or your DBMS's observability tools, testing with representative data and critical query shapes. Never infer performance solely from **table count**.

## 9. Evidence-Based Controlled Denormalization

**Denormalization** intentionally introduces a redundant or pre-aggregated representation to serve queries. It differs from **forgetting to normalize** because you explicitly define the source of truth, purpose, and synchronization mechanism.

For example, suppose an order listing page needs each order's line count. The system can:

1. Compute it from `ORDER_ITEMS` at query time if volume permits.
2. Use a **view** to reuse the aggregation query.
3. Use a **materialized view** or dedicated read table `ORDER_SUMMARY(order_id,item_count,total_amount)` when benchmarks prove the benefit.
4. Maintain an application-layer cache with expiration and stale-data handling.

If you store `item_count` directly on `ORDERS`, define the **invariant**:

\[
\text{ORDERS.item\_count}
=\#\{\text{valid order lines in ORDER\_ITEMS}\}.
\]

Clarify how `item_count` updates on line add/remove/return/cancel; whether it updates in the same transaction or asynchronously; and how drift is reconciled if synchronization fails.

### Denormalization Decision Template

| Question | What to Record |
|---|---|
| Why is it needed? | Which specific query fails which measured target |
| Source of truth? | Which table/stream holds the authoritative writable data |
| Duplicated/aggregated data? | Exact columns, grain, and time scope |
| Consistency level? | Strong within one transaction or bounded eventual consistency |
| Sync mechanism? | Transaction, trigger, CDC, event, batch job, or view |
| Recovery? | Periodic reconciliation, recomputation, and drift detection |
| Success metrics? | Latency, resource usage, error counts before/after |

If you cannot answer these questions, merging tables to be "faster" usually creates **uncontrolled technical debt**.

## 10. Choosing by Workload Type

| Scenario | Suitable Starting Point | Watch Out For |
|---|---|---|
| **OLTP: orders, payments, inventory** | Relational 3NF/BCNF depending on dependencies, clear keys and transactions | Business keys, foreign keys, consistency, avoiding multi-copy updates |
| **Catalogs with many optional attributes** | Typed relational columns, child entities if independent lifecycle; consider document for flexible attribute groups | Do not turn every nullable column into a 1-to-1 table or arbitrary EAV |
| **Profiles with independent lists** | Separate junction tables or document arrays with independent semantics | Do not take Cartesian products and treat combinations as facts |
| **Multi-hop network relationships** | Graph model when relationship traversal dominates | Do not treat every binary edge as proof of an n-ary event |
| **BI/OLAP: revenue aggregation** | Event-grain fact + dimensions, commonly a **star schema** | Avoid many-to-many joins inflating metrics; manage dimension history |
| **Read-heavy, rarely updated reports** | Read model/materialized view built from normalized sources | Synchronization, staleness window, and rebuild procedures |

In analytical warehouses, a **star schema** may bundle descriptive attributes into dimensions to simplify queries. That is a choice driven by **read workload and analytical grain**, not a claim that data dependencies cease to matter. With documents, embedding order details can fit whole-order reads, provided you specify whether embedded fields are **snapshots** or **current data**.

## 11. Decision Flowchart: Keep, Split, or Build a Read Model?

~~~mermaid
flowchart TD
    A["Start: understand grain and business rules"] --> B{"Are there dependencies causing data anomalies?"}
    B -->|Yes| C["Propose decomposition based on confirmed dependencies"]
    C --> D{"Lossless and constraints still enforceable?"}
    D -->|No| E["Revise design, review assumptions or enforcement"]
    D -->|Yes| F["Test workload, access permissions, and history"]
    B -->|No| G{"Measurable architectural/performance reason to split?"}
    G -->|No| H["Keep table; do not split just for having many columns"]
    G -->|Yes| F
    F --> I{"Goals met?"}
    I -->|Yes| J["Finalize structure and constraints"]
    I -->|No| K["Optimize queries/indexes or create a reconciled read model"]
    K --> F
~~~

This flowchart is a **thinking process**. When domain-specific, safety, regulatory, or data governance constraints apply, the decision may differ; document the rationale rather than forcing every system through a single mold.

## 12. A Review-Ready Design Decision Table

Suppose a team proposes splitting `ORDERS.status` into its own table. Instead of asking only "is it BCNF?", build a table:

| Criterion | Notes on Proposing `ORDER_STATUS(order_id,status)` |
|---|---|
| New FD rule addressed | **None** if `order_id → status` already holds and no other FDs exist |
| Anomalies eliminated | **None demonstrated** |
| Independent key and lifecycle | Same `order_id`, usually same lifecycle as the order |
| Operational benefit | Possible only if separate permissions or very high-frequency status updates apply |
| Cost | Extra join, potential missing child row, migration, multi-table write transactions |
| Performance evidence | Requires actual update contention or query telemetry |
| Default conclusion | **Keep `status` on `ORDERS`** unless a concrete need exists |

Conversely, if **status transition history** is required, propose:

~~~text
ORDER_STATUS_EVENTS(
    order_id, event_no, previous_status, new_status, changed_at, changed_by
)
~~~

with a confirmed business key (e.g., `(order_id,event_no)`). This is a **multi-row event relation** serving a new requirement—not a pointless one-to-one split.

## 13. Migration and Verification Before Changing Schemas

Design does not end on a diagram. Moving from a flat table to child tables requires a migration plan:

1. **Lock down semantics and grain**: confirm which FDs actually hold, which fields are current vs. historical, and edge exceptions.
2. **Audit keys and dirty data**: detect duplicate `order_id`s, duplicate `(order_id,line_no)`s, broken reference codes, and invalid `NULL`s.
3. **Create child schemas and constraints**: appropriate primary keys, foreign keys, `UNIQUE`, `NOT NULL`, and `CHECK`.
4. **Migrate data under control**: ensure backfills drop no records and handle concurrent changes occurring during migration.
5. **Reconcile datasets**: join post-migration projections and diff against source data using set checks, not just row counts.
6. **Run read/write scenarios**: insert orders with zero lines, multi-line orders, product renames, refunds/cancellations, and historical checks.
7. **Measure and monitor**: latency, constraint errors, sync lag, join fan-out, plus a rollback plan if needed.

### SQL to Detect Dependency Violations Before Splitting

Suppose source table `staging_order_lines` must satisfy `order_id → customer_id`:

~~~sql
SELECT order_id, COUNT(DISTINCT customer_id) AS customers_per_order
FROM staging_order_lines
WHERE order_id IS NOT NULL
  AND customer_id IS NOT NULL
GROUP BY order_id
HAVING COUNT(DISTINCT customer_id) > 1;
~~~

The result highlights orders with **multiple non-NULL customer IDs** in staging; check whether that is dirty source data, a missing `tenant_id`/store scope, or a valid domain exception. Zero rows **does not prove** the FD holds across all future business states.

### SQL Comparison After Decomposition

Once you have the source table `staging_order_lines(order_id,customer_id,line_no,product_id,quantity)` and target tables `orders`, `order_items`, you can reconcile **non-NULL tuple sets** using set difference:

~~~sql
WITH original_rows AS (
    SELECT DISTINCT
        order_id, customer_id, line_no, product_id, quantity
    FROM staging_order_lines
    WHERE order_id IS NOT NULL
      AND customer_id IS NOT NULL
      AND line_no IS NOT NULL
      AND product_id IS NOT NULL
      AND quantity IS NOT NULL
),
reconstructed_rows AS (
    SELECT DISTINCT
        o.order_id, o.customer_id, i.line_no, i.product_id, i.quantity
    FROM orders AS o
    JOIN order_items AS i ON i.order_id = o.order_id
),
missing_rows AS (
    SELECT * FROM original_rows
    EXCEPT
    SELECT * FROM reconstructed_rows
),
extra_rows AS (
    SELECT * FROM reconstructed_rows
    EXCEPT
    SELECT * FROM original_rows
)
SELECT 'missing' AS issue, * FROM missing_rows
UNION ALL
SELECT 'extra' AS issue, * FROM extra_rows;
~~~

**Note:** this SQL example uses `EXCEPT` (syntax may vary by DBMS), `DISTINCT` to compare value sets, and intentionally scopes the source to non-NULL rows. During real migrations, also reconcile **NULLs, duplicate records, orphaned keys, and timestamp drift**. An empty result proves the two sets match **on the compared snapshot**, not that the decomposition is lossless for all future data.

## 14. Common Decision Mistakes

| Mistake | Why It Is Risky | Fix |
|---|---|---|
| "More tables always means better normalization" | Can create pointless one-to-one tables that fix no anomalies | Every new table needs a **business or operational reason** |
| "A table with many columns is wrong" | Column count is not a 3NF/BCNF criterion | Check keys, FDs, MVDs/JDs, and grain |
| "Once in 3NF, nothing else matters" | BCNF-violating FDs, MVDs, or JDs may still exist | Inspect further **when real rules and issues exist** |
| "BCNF is always better than 3NF" | Some decompositions lose FD preservation | Weigh cross-table enforcement cost |
| "Storing snapshots violates normalization" | Snapshots describe a **different point in time** than current data | Define clear semantics and sources of truth |
| "Many joins mean merge everything back" | Reintroduces anomalies and may not even be faster | Measure, add indexes, tune queries, or build read models |
| "Switching primary key to UUID fixes duplicates" | Surrogate keys do not replace business uniqueness | Maintain appropriate `UNIQUE` and candidate keys |
| "A lookup table for every value is optimal" | Adds joins and mapping logic for values with no lifecycle | Split only when management/referencing needs exist |
| "Once split, FKs guarantee every rule" | FKs cannot express all FDs, JDs, temporal rules, or business invariants | List constraints and enforcement mechanisms per rule |
| "Sample queries look fine so the split is right" | Small samples may hide spurious tuples | Prove losslessness from real dependencies, then test with SQL |

## 15. Practice Exercises with Solutions

### Exercise 1 — Is a One-to-One Split Mandatory?

Given `EMPLOYEES(employee_id,full_name,department_id,hire_date)`. Only `employee_id → full_name,department_id,hire_date` is confirmed, with no other FDs. Must you split out `EMPLOYEE_HIRE_DATES(employee_id,hire_date)` to achieve 3NF?

**Solution:** No. All attributes depend on the single-column key `employee_id` and no other non-trivial FDs violate 3NF under the assumptions. A one-to-one split could be considered for access control or operations, yet is **not required for normalization**.

### Exercise 2 — Purposeful Splitting

Given `ORDER_LINE_FLAT(order_id,customer_id,line_no,product_id,quantity)` with `order_id → customer_id` and `(order_id,line_no) → product_id,quantity`. How should it be split?

**Solution:** Create `ORDERS(order_id,customer_id)` and `ORDER_ITEMS(order_id,line_no,product_id,quantity)`. Their intersection is `order_id`; from `order_id → customer_id`, the intersection determines all of `ORDERS`. Thus the split is **lossless**, while separating order-level facts from line items.

### Exercise 3 — Same Name, Different Semantics

`PRODUCTS` has `current_name`; `ORDER_ITEMS` has `name_at_sale`. Should `name_at_sale` be deleted to avoid name duplication?

**Solution:** Do not delete it blindly. `name_at_sale` is a **transaction-time snapshot**, determined by the line-item key, whereas `current_name` is the product's current value. Deleting the snapshot would retroactively alter historical invoices when products are renamed. Define clear snapshot storage and correction rules.

### Exercise 4 — Checking a BCNF Decision

Given `R(A,B,C)` with `F=\{AB→C,\ C→B\}`. The two candidate keys are `AB` and `AC`. The relation satisfies 3NF yet fails BCNF. Can you split into `CB` and `AC` losslessly? Is `AB→C` preserved?

**Solution:** The decomposition is **lossless** because the intersection `C` determines `CB`. However, `AB→C` is **not preserved** by local FDs. If that rule is important and hard to enforce across tables, keeping the **3NF** design can be a sensible choice.

### Exercise 5 — Two Independent Lists

A system stores `PROFILE(user_id,skill,language)`, where skills and languages are two independent lists. Should all skill–language combinations be stored?

**Solution:** In a normalized relational model, split into `USER_SKILLS(user_id,skill)` and `USER_LANGUAGES(user_id,language)` if the independence MVD holds. This avoids a Cartesian product and satisfies 4NF. However, if each `(skill,language)` pair represents a genuinely coupled capability, do **not** split them and fabricate nonexistent pairs.

### Exercise 6 — When to Create a Summary Table?

An order list page reads `item_count` thousands of times per second. Computing `COUNT(*)` from the line-items table is a measured cause of missing latency targets. Should `item_count` be copied into a read table?

**Solution:** You can consider a read model/materialized view or summary column **after** trying query and index optimizations. You must designate `ORDER_ITEMS` as the source of truth, define which lines count, specify update timing, handle order cancellations, clarify consistency guarantees, and set up reconciliation. This is **controlled denormalization**.

### Exercise 7 — Sample Data and Business Keys

Across 100 rows of `ENROLLMENTS`, no duplicate `(student_id,course_id)` pair appears. Can you immediately add `UNIQUE(student_id,course_id)`?

**Solution:** Not enough evidence. Ask the business whether a student can retake the same course and whether terms/attempts are tracked. If each pair is allowed at most once, the constraint fits; if retakes are allowed, add an attempt identifier or matching structure.

### Exercise 8 — Many Columns, One Key

A table `DEVICE_READING(reading_id,device_id,observed_at,temperature,humidity,battery_level)` stores one measurement event, each with a unique `reading_id`. All readings occur together in a single event; no other FDs are confirmed. Should each measurement be split into its own one-to-one table?

**Solution:** Not necessary for 3NF. Splitting would complicate atomic writes and reading a whole measurement event. If later the metrics diverge in sampling frequency, source, or lifecycle, revisit the **event grain**—do not split merely over column count.

## 16. Checklist for Concluding "Normalized Enough"

- [ ] Defined the **grain** of every relation and the scope of every identifier.
- [ ] Listed **business-confirmed dependencies**, rather than inferring them from sample data.
- [ ] Identified all necessary candidate keys and expressed them via appropriate `PRIMARY KEY`/`UNIQUE` constraints.
- [ ] Eliminated major insertion, update, and deletion anomalies or established clear controls.
- [ ] Justified every proposed decomposition and verified **lossless join**.
- [ ] Evaluated **dependency preservation** and enforcement mechanisms for any unpreserved rules.
- [ ] Pursued BCNF/4NF/5NF only for dependencies that **truly exist** and problems **worth solving**.
- [ ] Avoided creating one-to-one, lookup, or EAV tables merely to reduce column count.
- [ ] Distinguished **current data** from **transaction snapshots** and **version history**.
- [ ] Tested critical queries with representative data, execution plans, and concrete metrics.
- [ ] If denormalized, documented the **source of truth, synchronization mechanism, consistency level, and reconciliation method**.
- [ ] Prepared a migration plan, data verification checks, and rollback path for schema changes.

**Key Takeaway:** Being normalized **enough** does not mean "stop at exactly 3NF" or "push everything to 5NF." It is the point where the model accurately reflects **business rules and grain**, curbs anomaly-causing redundancy, preserves data recoverability and enforceable constraints, and further splitting yields **no clear business or operational benefit**. Use data dependencies as your foundation, workload metrics as your test, and explicit design intent as your stopping rule.
