# Analytical Hierarchies and Conformed Dimensions Across Multiple Fact Tables

## Learning Objectives

In an analytical data model, a **fact table** answers "what happened and how much was measured?", while a **dimension table** answers "when did that event occur, who was involved, which product, where, and under which group?". A dimension does more than store display names. It also defines **analytical levels** that help users navigate from detailed data up to summary levels or vice versa.

For example, from the revenue of each **product**, we can sum up to **product subcategory**, **category**, and then the entire company. If both sales data and returns data use the same category concept, the two facts can be compared along the same analytical axis. However, if two systems define categories differently or join two facts at incompatible levels of detail, a report can duplicate monetary amounts even when every foreign key is valid.

This lesson belongs to the **Dimension Tables** chapter of the **DATABASE_DATA_MODELING** module. The overall goal of the module is to turn business requirements into a clear data model—from entities, relationships, constraints, normalization, keys, and indexes to the physical schema—while comparing relational, document, graph, and analytical models so you can choose structures that are easy to evolve and verify. This lesson focuses on **hierarchy semantics within dimensions** and **consistency of shared dimensions across multiple fact tables**, rather than serving as a guide to building an entire ETL/ELT pipeline.

After this lesson, you will be able to:

1. Describe a dimension's **hierarchy** and the **roll-up, drill-down, slice, and dice** operations on analytical data.
2. Distinguish between **strict/non-strict**, **complete/incomplete**, and **balanced/ragged** hierarchies, as well as alternative and time-varying hierarchies.
3. Explain the conditions required for an aggregation to be **accurate and free of double counting** (*summarizability*), including single-valued hierarchy paths, completeness, and measure additivity.
4. Compare ways of storing hierarchies using a **flattened dimension**, **snowflake**, **parent–child relationship**, or **bridge table**.
5. Define a truly **conformed dimension**: consistent identifiers, attributes, domain values, hierarchies, effective dates, and business scope.
6. Design a **bus matrix** for sales, returns, and inventory processes; distinguish a **shared dimension** from a **role-playing dimension**.
7. Write safe **drill-across** queries spanning multiple facts by aggregating **each fact independently to a common grain before joining**.
8. Verify designs using PostgreSQL SQL, identifying traps involving **fanout, SCDs, many-to-many relationships, missing dimension rows, units of measure, and snapshots**.

> **Guiding Principle:** Two facts having the same column name does not mean they share the same dimension definition. A hierarchy that looks like a tree does not mean SUM is always correct; you must check how members are assigned to each level and the properties of the measure.

## 1. What Is a Hierarchy in a Dimension Table?

### 1.1. From Detailed Members to Summary Levels

Suppose a business sells:

~~~~text
Category: Office Supplies
  Subcategory: Paper
    Product: Notebook
    Product: Printer Paper
  Subcategory: Pens
    Product: Ballpoint Pen
    Product: Pencil

Category: Home Goods
  Subcategory: Drinkware
    Product: Glass Tumbler
~~~~

This is a three-level product hierarchy:

\[
\text{Product}\longrightarrow\text{Subcategory}\longrightarrow\text{Category}
\]

Each arrow means "a member at the detailed level belongs to a member at the higher level" according to the **applicable classification rule**. If every product belongs to exactly one subcategory and every subcategory belongs to exactly one category, this hierarchy has **single-valued** paths.

Given a fact row for selling the product **Notebook**, a reader can analyze revenue:

- At the **product** level: Notebook alone.
- At the **subcategory** level: sum of products belonging to the Paper subcategory.
- At the **category** level: sum of subcategories belonging to the Office Supplies category.
- At the **system-wide** level: sum of all valid categories in the dataset.

### 1.2. Roll-up and Drill-down

**Roll-up** moves from a detailed level up to a summary level, for example:

\[
\text{Revenue by product}
\ \Rightarrow\
\text{Revenue by subcategory}
\ \Rightarrow\
\text{Revenue by category}
\]

**Drill-down** does the opposite: moving from category down to subcategory and then to product to pinpoint the source of a change.

**Slice** fixes a single dimension value, such as only the "Office Supplies" category. **Dice** filters a set of values across multiple dimensions, such as "Office Supplies" in Q4 and at Southern stores. **Drill-through** typically navigates from an aggregated cell down to the underlying event rows or detailed records, if the system supports that data lineage path.

These operations only make sense accurately when the **grain of the fact**, the **hierarchy of the dimension**, and the **measure aggregation rules** are clear.

### 1.3. Hierarchies Are Not Limited to Products

| Dimension | Example hierarchy | Points to clarify |
| --- | --- | --- |
| **Time** | Day → Month → Quarter → Year | Calendar or fiscal calendar, time zone, which year a week belongs to |
| **Geography** | Point of Sale → City → Province/Region → Country | Regional boundaries and effective dates |
| **Organization** | Employee → Team → Department → Division | Whether employees hold concurrent roles, whether branches skip levels |
| **Product** | SKU → Subcategory → Category | Whether one SKU belongs to multiple categories simultaneously |
| **Customer** | Customer → Segment → Segment Group | Segment at transaction time or current segment |
| **Distribution** | Store → Area → Region | When a store changes area |

A single dimension can have **multiple hierarchies**. For example, time simultaneously has the **day → calendar month → calendar year** hierarchy and the **day → fiscal period → fiscal year** hierarchy. These are two different roll-up paths; you should not merge "month" from both calendars into one just because the level names sound similar.

### 1.4. Overview Diagram

~~~~mermaid
flowchart BT
    P1["Notebook (P01)"] --> G1["Paper Subcategory"]
    P2["Printer Paper (P02)"] --> G1
    P3["Ballpoint Pen (P03)"] --> G2["Pens Subcategory"]
    G1 --> C1["Office Supplies"]
    G2 --> C1
    P4["Glass Tumbler (P04)"] --> G3["Drinkware Subcategory"]
    G3 --> C2["Home Goods"]
~~~~

The diagram above assumes **each lower-level member has exactly one path to an upper level at the time of analysis**. That is an assumption to verify, not a default property of every dimension.

## 2. Hierarchy Properties That Affect Analytical Results

### 2.1. Strict and Non-strict Hierarchies

**Strict hierarchy**: each member at a lower level is assigned to **at most one** member at the immediately higher level within the same hierarchy and at the same point in time/context.

For example, product P01 belongs **exclusively to the Paper subcategory**; the Paper subcategory belongs **exclusively to the Office Supplies category**. A revenue row for P01 has a unique path when rolling up to category.

**Non-strict hierarchy**: a lower-level member **can belong to multiple upper-level members**. For example, a product is included in two marketing collections simultaneously, or an employee has two managers in a matrix structure.

Suppose P01 has revenue of 100,000 VND and simultaneously belongs to two collections, "Back to School" and "Gifts". If you join the membership relationship and SUM:

| Collection | P01 Revenue |
| --- | ---: |
| Back to School | 100,000 |
| Gifts | 100,000 |

The sum of the two rows is 200,000 VND even though the source revenue is only 100,000 VND. There are two valid but **different** interpretations:

- **Unallocated tagged reporting**: each collection shows the full revenue associated with the product; collections must not be summed together to produce a company-wide total.
- **Allocated reporting**: weights are used, such as 70% for Back to School and 30% for Gifts, so that the allocated total equals 100% of the source value.

This trap cannot be fixed with a simple SELECT DISTINCT: the two groups have different meanings, and how to allocate is a **business decision**.

### 2.2. Complete and Incomplete Hierarchies

A hierarchy is **complete** at the analyzed level when every detailed member that needs to be included in the report has an assignment path up to an appropriate summary-level member.

If product P99 does not yet have a subcategory, an INNER JOIN from the fact through the subcategory table can cause P99's revenue to **disappear** from the report. An incomplete hierarchy risks making the category total **smaller than the fact total**.

Selectable policies include:

1. **Do not publish unclassified rows**, accompanied by a remediation queue rule.
2. Place them in a clearly defined **Unclassified/Unknown** member; revenue still appears in aggregations.
3. Enrich hierarchy data from a trusted source prior to analysis.

Choosing a policy must depend on whether the requirement is **full revenue completeness** or **reporting only classified data**, and must be explicitly documented in the data contract.

### 2.3. Balanced, Unbalanced, and Ragged Hierarchies

In a **balanced** hierarchy, paths to the summary level have uniform depth. In an **unbalanced** hierarchy, different branches have varying lengths; a **ragged** hierarchy can skip levels that do not apply.

Organizational example:

~~~~text
Company
  Commercial Division
    Sales Department
      Retail Team
  Operations Division
    Operations Department
  Executive Office
    (reports directly to Company, no Division or Department)
~~~~

If every unit is forced to have a Division and Department, the designer may have to:

- Use a clearly meaningful **"Not Applicable"** member.
- Use a parent–child relationship table, displaying a flexible hierarchy instead of forcing a fixed number of columns.
- Define roll-up logic so a unit neither drops out of reports nor gets double-counted.

**NULL**, **Unknown**, and **Not applicable** have distinct meanings. NULL may mean data is not yet known; "not applicable" is a valid state for a level-skipping branch. You should not arbitrarily collapse both into a single bucket without an explicit decision.

### 2.4. Alternative and Parallel Hierarchies

A single product can be grouped according to:

- **Operational catalog:** SKU → Product Subcategory → Category.
- **Marketing campaigns:** SKU → Collection → Program.
- **Regulatory rules:** SKU → Tax Group → Tax Type.

These can be **hierarchies serving different purposes**. A marketing hierarchy is often many-to-many, whereas an operational catalog may be strictly one-to-many. Copying every attribute into a single category column erases these distinct semantics.

### 2.5. Time-Varying Hierarchies

Suppose product P01 moves from the **Office Supplies** category to **Gifts** effective Nov 1. A report covering October and November may require:

- **Current classification:** recomputing all history under today's category.
- **Historical classification:** October transactions are tagged with the old category, November transactions with the new category.

Both definitions can be valid for different questions. They require an appropriate dimension policy, such as **SCD Type 1** for current values or **SCD Type 2** for historical versions. Simply adding a changed_at column without storing or assigning the right versions is **insufficient** to answer both perspectives accurately.

## 3. Conditions for Accurate Roll-up: Summarizability

**Summarizability** is the ability to aggregate measures from a detailed level to a higher level **without distorting totals, omitting rows, or duplicating the contribution of underlying events**. It is not merely a matter of using valid SUM syntax.

### 3.1. How Many Hierarchy Paths Does an Event Have?

Let \(F\) be a set of fact rows with an additive measure \(m(f)\), and \(H\) be the set of members at the summary level. If each fact belongs to **exactly one** member \(h\in H\), we have:

\[
M(h)=\sum_{\substack{f\in F\\group(f)=h}}m(f)
\]

When the groups form **a complete, non-overlapping partition** of F:

\[
\sum_{h\in H}M(h)=\sum_{f\in F}m(f).
\]

This equality rests on the following assumptions:

1. Each fact row has **exactly one group** when classified at level H, if the report must cover all of F.
2. No fact row is duplicated by JOINs or uncontrolled many-to-many relationships.
3. The measure is valid to **sum across the dimension under consideration**.
4. The data and the selected hierarchy versioning rule are consistent at the time of analysis.

If a fact row belongs to two groups, it may be summed **twice**. If it belongs to no group, it may be **omitted**. If the measure is an end-of-day balance, summing across multiple days remains meaningless even though daily groups do not overlap.

### 3.2. Three Requirements for a Safe Roll-up Path

| Requirement | Meaning | Consequence if violated |
| --- | --- | --- |
| **Disjoint membership** | Each lower-level member contributes to at most one upper-level group in the same hierarchy and point in time | Double counting when a member appears in multiple groups |
| **Complete coverage** | Every row to be reported has a group at the summary level | Dropped rows; group totals fall below source total |
| **Measure compatibility** | The aggregation function matches the measure type and unit | Meaningless totals, such as summing inventory across days |

A hierarchy design that is **strict but incomplete** can still lose revenue due to unassigned groups. A design that is **complete but non-strict** can still multiply revenue. You must analyze **all three conditions**, not just check UNIQUE in the dimension table.

### 3.3. Additive, Semi-additive, and Non-additive

| Measure | Can SUM by product? | Can SUM across multiple days? | Notes |
| --- | --- | --- | --- |
| **Sales line revenue** | Usually yes, if same currency | Yes, by consistent recognition timestamp | Additive across appropriate dimensions |
| **Quantity sold** | Conditionally, if units of measure are compatible | Usually yes | Do not add kg and pieces without conversion |
| **End-of-day inventory** | Can be summed across compatible products/warehouses | **Do not** sum like revenue | Semi-additive over time |
| **Average selling price** | **Do not** SUM | **Do not** SUM | Recompute from total amount and compatible total quantity |
| **Return rate** | **Do not** SUM | **Do not** SUM | Compute from numerator/denominator after aggregation |
| **Distinct customer count** | Do not sum from overlapping groups | Do not sum daily DISTINCT counts into monthly customers | Non-additive; must deduplicate over the target scope |

For example, customer C01 buys products in both subcategories A and B. The DISTINCT customer count of A = 1, and of B = 1, yet company-wide there is still only **one customer**. Even when the product hierarchy is strict, **distinct customer count is not additive across product subcategories**, because the same customer can appear in multiple subcategories across multiple fact rows.

### 3.4. Time Hierarchies Have Traps Too

A day belongs to exactly one month in the **calendar** year, but an **ISO week** can span two calendar months. Therefore:

- **Day → Month → Year** in the calendar system can form a strict hierarchy path.
- **Day → ISO Week → Calendar Month** does not naturally form a strict tree: a week can cross a month boundary.
- **Day → ISO Week → ISO Year** has its own rules; the first/last week of an ISO year can differ from the calendar year.

If a report must roll up from week to month, you must define how weeks map to months: by start date, end date, majority of days, or daily allocation. Which rule to choose is a **business rule**, not an inherent property of SQL DATE_TRUNC.

### 3.5. Hierarchy Correctness Depends on Scope

Subcategory code **VPP** may be unique within one tenant, not unique system-wide. A hierarchy that is strict within each tenant can become non-strict or ambiguous if a JOIN matches only on category_code without tenant_id.

Similarly, product catalogs may differ by market. You must explicitly specify keys, versions, and scope:

~~~~text
tenant_id + product_id + effective_time
    → appropriate classification version
    → subcategory belonging to that tenant and point in time
    → category belonging to that tenant and point in time
~~~~

Do not treat the display label "Office Supplies" as a cross-system key; labels can change or collide. Stable keys and mapping rules are what must anchor JOINs.

## 4. Ways to Store Hierarchies in a Relational Model

A conceptual hierarchy **does not force a single physical table layout**. You can use a flattened dimension, snowflake, parent–child table, or bridge table depending on analytical needs.

### 4.1. Flattened (Denormalized) Dimension

A flattened product dimension can store:

~~~~text
DIM_PRODUCT(
  product_key,
  product_id,
  product_name,
  subcategory_code,
  subcategory_name,
  category_code,
  category_name
)
~~~~

Example:

| product_key | product_id | product_name | subcategory | category |
| ---: | --- | --- | --- | --- |
| 101 | P01 | Notebook | Paper | Office Supplies |
| 102 | P02 | Ballpoint Pen | Pens | Office Supplies |
| 103 | P03 | Glass Tumbler | Drinkware | Home Goods |

Advantages:

- Grouping by product, subcategory, and category is simple; a single fact → dimension JOIN suffices.
- Fits many star schemas and BI tools well.
- Reduces the number of JOINs in queries compared to splitting across multiple dimension tables.

Trade-offs:

- category_name repeats across many product rows; updating a category name may require modifying multiple rows.
- You must enforce **subcategory_code → category_code** and **category_code → category_name** within the proper business scope.
- Historical attributes can cause multiple product versions to coexist; queries must use the **appropriate versioned product_key**, not join arbitrarily on product_id.

A flattened dimension **does not inherently suffer from unusable normalization flaws**: analytical models prioritize query ergonomics and governed consistency. What must be proven is that repeated attributes are **synchronized from a single source of truth** and the hierarchy introduces no contradictions.

### 4.2. Snowflake: Normalizing Dimension Levels into Tables

A normalized alternative:

~~~~text
DIM_CATEGORY(category_key PK, category_code UNIQUE, category_name)
       ↑
DIM_SUBCATEGORY(
  subcategory_key PK,
  subcategory_code UNIQUE,
  category_key FK,
  subcategory_name
)
       ↑
DIM_PRODUCT(
  product_key PK,
  product_id,
  subcategory_key FK,
  product_name
)
       ↑
FACT_SALES(product_key FK, ...)
~~~~

Foreign keys from product to subcategory and from subcategory to category enforce a **well-defined one-to-many** relationship. If the business shifts hierarchies historically, keys and structures must be designed for versions rather than simply overwriting the current category_key.

Advantages:

- Classification relationships are governed in one place; category details are not repeated on every product row.
- Reduces update anomalies for names or hierarchy links when governed centrally.
- Suits complex taxonomies, shared subgroups, and level-specific governance.

Trade-offs:

- Queries require more JOINs; some BI tools prefer flattened dimensions.
- Level-skipping branches can be awkward to represent if foreign keys are mandatory.
- If the business is truly many-to-many, merely adding a single FK on the child table misrepresents reality.

**Snowflake and star schemas are not absolute rivals.** You can keep the fact at the center and selectively normalize only dimensions whose hierarchies require strict governance.

### 4.3. Parent–Child Table for Unbalanced Organizational Hierarchies

For organizational structures with variable depth, a member table with a parent key:

~~~~sql
CREATE TABLE org_unit_example (
    unit_id BIGINT PRIMARY KEY,
    unit_name VARCHAR(120) NOT NULL,
    parent_unit_id BIGINT
        REFERENCES org_unit_example(unit_id),
    CONSTRAINT ck_org_no_self_parent
        CHECK (parent_unit_id IS NULL OR parent_unit_id <> unit_id)
);
~~~~

This model allows trees of varying depths. However:

- The CHECK constraint above only blocks **a node from pointing to itself**; it does **not** prevent longer cycles such as A → B → C → A.
- If a unit needs multiple parents at the same time, a single parent_unit_id column is insufficient; a many-to-many relationship model and appropriate allocation/read rules are needed.
- For historical analysis, parent–child relationships need effective dates or versioning under an agreed policy.

An illustrative PostgreSQL recursive query walking from a unit up to its ancestors, assuming data has been verified to be acyclic:

~~~~sql
WITH RECURSIVE ancestors AS (
    SELECT unit_id, parent_unit_id, unit_name, 0 AS depth
    FROM org_unit_example
    WHERE unit_id = 10

    UNION ALL

    SELECT p.unit_id, p.parent_unit_id, p.unit_name, a.depth + 1
    FROM org_unit_example AS p
    JOIN ancestors AS a ON p.unit_id = a.parent_unit_id
)
SELECT unit_id, unit_name, depth
FROM ancestors
ORDER BY depth;
~~~~

This is an **illustrative query on a valid tree**, not an algorithm for handling arbitrary graphs or cycles. In production systems, you must implement cycle checks, depth limits, or recursive cycle-detection mechanisms if data can be malformed.

### 4.4. Bridge Table for Many-to-Many Relationships

Suppose P01 belongs to two collections simultaneously and revenue must be allocated:

~~~~text
DIM_PRODUCT(product_key, ...)
DIM_COLLECTION(collection_key, collection_name, ...)
BRIDGE_PRODUCT_COLLECTION(
    product_key,
    collection_key,
    allocation_weight
)
~~~~

Example:

| product_key | collection | allocation_weight |
| ---: | --- | ---: |
| 101 | Back to School | 0.70 |
| 101 | Gifts | 0.30 |

If P01 revenue is 100,000 VND, the **allocated revenue** metric is:

\[
100000\times 0.70=70000
\]

and

\[
100000\times 0.30=30000.
\]

For each product and applicable scope/time period, if you want to preserve total revenue after allocation, you must ensure:

\[
\sum_{\text{valid collection}}allocation\_weight=1.
\]

A row-level CHECK constraint between 0 and 1 is **not enough** to guarantee **weights sum to 1** across the group; a dedicated cross-row check or enforcement mechanism is needed. If allocation is unnecessary and you want to view **full revenue associated with each collection**, you can publish tagged reports while clearly stating that **collection totals cannot be summed together**.

For time-effective bridge tables, assignment keys and weights must be evaluated **at the event timestamp** or according to another approved analytical rule. Do not implicitly apply current weights to all historical events.

## 5. Shared Dimensions Across Multiple Fact Tables: Conformed Dimensions

A **conformed dimension** is a dimension whose **definitions, keys, attributes, and hierarchy levels are consistent enough to be used compatibly across business processes or fact tables**. It is the foundation for comparing metrics from multiple event sources within the same reporting system.

For example, suppose a company has:

- **FACT_SALES_LINE:** each row is a valid sales line item.
- **FACT_RETURN_LINE:** each row is a line-level return event.
- **FACT_INVENTORY_DAILY:** each row is **end-of-day** inventory, by product and warehouse.

All three processes may need analysis by **product**, **date**, and **location**. Yet their measure properties and fact grains differ.

### 5.1. Sharing a Dimension Name Is Not Enough to Be Conformed

Suppose the sales department has a **sales_product** table and the returns department has **returns_product**. Both have a category_name column, yet:

- Sales classifies P01 as **Office Supplies**.
- Returns classifies P01 as **Gifts** under the customer care team's taxonomy.
- Sales uses category_code = VPP, while Returns uses category_code = OFFICE.
- Sales assigns category as of **sale date**, while Returns assigns category as of **return receipt date**.

If reports are combined by category_name or category_code without an approved mapping, figures can be:

1. **Split into two groups** even though users think they are the same category.
2. **Merged into the wrong group** merely because display labels happen to collide.
3. **Historically misaligned** because the two facts apply classification rules from different points in time.

To have a conformed dimension, you must verify **shared semantics or exact mappability to a shared set of attributes/hierarchy levels**.

### 5.2. Levels of Consistency to Check

| Aspect | Design question |
| --- | --- |
| **Business identity** | Does P01 represent the exact same product in both processes? Does the key include tenant/source? |
| **Surrogate key** | Do both facts reference the same key pointing to a centrally governed dimension? |
| **Attribute definitions** | Do category, brand, and size share the same meaning and cleansing rules? |
| **Domain values** | Are VPP, OFFICE, NULL, and Unknown used consistently or mapped transparently? |
| **Hierarchy paths** | Does P01 roll up to the same subcategory and category for the same scope and point in time? |
| **History policy** | Is classification current, as of sale time, or as of return time? |
| **Granularity** | Does one fact store SKU while another stores only subcategory? Is there a shared roll-up level? |
| **Scope/security** | Do keys distinguish tenant, market, or business unit? |
| **Ownership/versioning** | Who is authorized to change the taxonomy? When it changes, how are facts and reports transitioned? |

A solid model typically has **one centrally managed dimension** whose surrogate keys are shared across facts. However, a conformed dimension is a **semantic contract**, not necessarily a single physical table: independent data marts can also use synchronized dimension copies or common attributes that have been accurately mapped.

If each mart independently generates **product_key = 101** yet refers to different products, you must not join two facts on 101. **Matching surrogate key integers does not prove shared business identity.** Governance or a verified identity mapping table is required.

### 5.3. Conformance Does Not Require All Facts to Have the Same Grain

FACT_SALES_LINE has a grain of **one sales line**, FACT_RETURN_LINE has a grain of **one return event**, and FACT_INVENTORY_DAILY has a grain of **product–warehouse–day**.

These facts can still share DIM_PRODUCT and DIM_DATE. The conditions are:

- Dimension keys have unified semantics.
- Hierarchies in the dimension can provide a **shared grouping level** for the comparison question.
- Each fact's measures and timing are explicitly described.
- Reports aggregate **each fact separately at the shared level before comparing**.

You do not need to force every fact into "one row per order" just to share dimensions. **Dimension conformance** and **fact grain** are two separate design decisions.

### 5.4. Bus Matrix: Mapping Business Processes and Analytical Dimensions

A **bus matrix** places **processes/facts on rows** and **conformed dimensions on columns**. It helps identify which dimensions are shared and where definitions must be harmonized.

| Process / fact | Date | Product | Store | Customer | Warehouse |
| --- | :---: | :---: | :---: | :---: | :---: |
| **Sales — FACT_SALES_LINE** | ✓ | ✓ | ✓ | ✓ | — |
| **Returns — FACT_RETURN_LINE** | ✓ | ✓ | ✓ | ✓ if source provides | — |
| **End-of-day inventory — FACT_INVENTORY_DAILY** | ✓ | ✓ | — | — | ✓ |

From the matrix:

- **Date** and **Product** are candidate conformed dimensions for all three processes.
- **Store** applies to sales and returns; distinguish the selling store from the return-receiving location if business rules differ.
- **Customer** does not belong to the end-of-day inventory grain, because inventory does not "belong to a customer".
- **Warehouse** is an inventory dimension; do not assume it is interchangeable with a store if separate fulfillment relationships exist.

The matrix does not replace grain definitions. A ✓ mark only indicates the process **can be analyzed along that dimension**; it does not mean the facts have the same row count or that measures are additive across processes.

### 5.5. Conformed Attributes and Roll-up on a Shared Column Set

Sometimes two detailed dimensions differ but share consistent higher-level attributes. For example:

~~~~text
DIM_PRODUCT_SALES:
  product_id, sales_sku_variant, category_code, category_name

DIM_PRODUCT_RETURNS:
  product_id, return_reason_group, category_code, category_name
~~~~

If **category_code and category_name are governed with the same definition**, the two marts can analyze by **category** even without sharing all detailed columns. This is a form of conformance **at a shared subset of attributes or summary level**.

However, if one fact only has category_code and the other has SKU, comparing at the SKU level requires verifying whether complete mappings exist. Conformance at the **category** level does not automatically imply conformance at the **SKU** level.

### 5.6. A Conformed Dimension as a Contract Between Teams

For report authors to trust that sales and return amounts are grouped into the exact same categories, documentation should explicitly state:

> DIM_PRODUCT governs product_key and product_id system-wide; category_code, category_name, and subcategory–category relationships are shared across sales and returns facts under the same history policy. Any taxonomy change must have an owner, effective timestamp, and verification of affected fact rows.

Such a definition prevents the situation where "both dashboards are right according to their own systems yet cannot be compared against each other."

## 6. Shared, Role-Playing, and Time Dimensions

### 6.1. Role-Playing Dimension: One Table, Multiple Roles

A single **DIM_DATE** can be referenced multiple times within the same fact:

~~~~text
FACT_ORDER(
    order_date_key  FK → DIM_DATE.date_key,
    ship_date_key   FK → DIM_DATE.date_key,
    delivery_date_key FK → DIM_DATE.date_key
)
~~~~

Same date table, yet three distinct roles:

- **Order date**.
- **Ship-to-carrier date**.
- **Customer delivery date**.

If a user asks for "orders by order date", you must JOIN via **order_date_key**. If they ask for "delivered orders by delivery date", you must JOIN via **delivery_date_key**.

Example:

~~~~sql
-- Syntax example; assumes FACT_ORDER and DIM_DATE are declared
-- with appropriate keys and constraints.
SELECT d.full_date AS order_date, COUNT(*) AS orders
FROM fact_order AS f
JOIN dim_date AS d ON d.date_key = f.order_date_key
GROUP BY d.full_date
ORDER BY d.full_date;
~~~~

Do not substitute delivery_date_key for order_date_key merely because both reference DIM_DATE. **The dimension table is the same, but the foreign key roles differ**, yielding different analytical meanings.

### 6.2. A Shared Dimension Does Not Make Event Dates Equivalent

In a sales and returns model:

~~~~text
FACT_SALES_LINE.sale_date_key   → DIM_DATE.date_key
FACT_RETURN_LINE.return_date_key → DIM_DATE.date_key
~~~~

A return row on Nov 3 may relate to a sales order from Oct 1. If we compare **October sales revenue** with **October return amounts**, we are using **two different event dates along the same calendar-month axis**.

If you want the metric "returns for orders sold in October", the returns fact needs a key or path back to the **original sale date**, and the model must explicitly name the roles:

~~~~text
return_date_key        = time when the return occurred
original_sale_date_key = time when the returned line was sold
~~~~

Arbitrarily using original sale date in one report and return date in another yields two numbers both labeled "October returns" with different semantics.

### 6.3. Calendar and Fiscal Calendars

A single DIM_DATE can contain:

~~~~text
date_key
full_date
calendar_month
calendar_year
fiscal_period
fiscal_year
iso_week
iso_week_year
~~~~

These columns form **multiple hierarchies** over the same set of dates. When reporting:

- Group by **calendar_year + calendar_month** for calendar months.
- Group by **fiscal_year + fiscal_period** for fiscal periods.
- Group by **iso_week_year + iso_week** for ISO weeks.

Do not GROUP BY calendar_month alone without calendar_year if the data spans multiple years: Oct 2025 and Oct 2026 will be merged. Similarly, do not pair calendar_year with iso_week under ISO week rules, because year boundaries can differ.

### 6.4. SCD Type 2 and Shared Dimensions

If DIM_PRODUCT uses SCD2 to preserve category history, P01 might have:

| product_key | product_id | category | effective_from | effective_to |
| ---: | --- | --- | --- | --- |
| 101 | P01 | Office Supplies | 2026-01-01 | 2026-11-01 |
| 104 | P01 | Gifts | 2026-11-01 | open-ended |

A sales fact on Oct 1 points to product_key 101. A return fact on Nov 3 **could** point to:

- **104**, if the report uses **classification at the time of return**.
- **101**, if the report ties returns to the **classification at the original time of sale**.

Both approaches can be valid decisions, yet they are **not implicitly compatible** for historical category drill-across. You must specify each report's exact question, or store an additional versioned key role if both perspectives are needed.

When the same SCD2 dimension is shared across multiple facts, **defining which timestamp selects the version** is part of the conformance contract, not just a surrogate key lookup detail.

## 7. Hands-On Example: Sharing DIM_PRODUCT and DIM_DATE for Sales and Returns

This section builds **a standalone PostgreSQL schema**, using DIM_DATE, DIM_PRODUCT, DIM_STORE, and two sales/returns facts. The goal is to demonstrate how **two facts with different grains use shared dimensions**, and then run queries comparing revenue and returns without causing fanout.

### 7.1. Business Rules of the Example

Assume:

1. **Each row in FACT_SALES_LINE is a valid recorded sales line**; an order may have multiple lines.
2. **Each row in FACT_RETURN_LINE is a sales-line return event**; one sales line may have multiple partial return events.
3. All monetary measures are in **VND**, excluding tax and fees; **net_amount = gross_amount - discount_amount** in the sales fact.
4. Each return record has a non-negative **returned_amount**. Total returns across installments for the same sales line require a separate validation rule.
5. **Sale date** and **return date** are two roles of the **same DIM_DATE**; sales revenue and returns are grouped by **each event's respective occurrence date**.
6. DIM_PRODUCT is a **shared conformed dimension**; each product has exactly one current subcategory/category in this example. This is **Type 1**: classification change history is not retained.
7. Each fact points to the same **product_key**, **date_key**, and **store_key** from centrally governed dimensions.
8. "Sales after returns" in this example is defined as **net sales line revenue minus return amounts recorded in the period**, which is not assumed to equal accounting revenue.

### 7.2. Diagram of Two Facts Sharing Dimensions

~~~~mermaid
erDiagram
    DIM_DATE ||--o{ FACT_SALES_LINE : sale_date
    DIM_DATE ||--o{ FACT_RETURN_LINE : return_date
    DIM_PRODUCT ||--o{ FACT_SALES_LINE : sold_product
    DIM_PRODUCT ||--o{ FACT_RETURN_LINE : returned_product
    DIM_STORE ||--o{ FACT_SALES_LINE : selling_store
    DIM_STORE ||--o{ FACT_RETURN_LINE : return_store

    DIM_DATE {
        integer date_key PK
        date full_date UK
        smallint calendar_year
        smallint calendar_month
    }
    DIM_PRODUCT {
        bigint product_key PK
        varchar product_id UK
        varchar subcategory_code
        varchar category_code
        varchar category_name
    }
    DIM_STORE {
        bigint store_key PK
        varchar store_code UK
        varchar store_name
    }
    FACT_SALES_LINE {
        varchar sale_line_id PK
        varchar order_id
        integer sale_date_key FK
        bigint product_key FK
        bigint store_key FK
        integer quantity
        decimal net_amount
    }
    FACT_RETURN_LINE {
        varchar return_line_id PK
        varchar original_sale_line_id FK
        integer return_date_key FK
        bigint product_key FK
        bigint store_key FK
        integer returned_qty
        decimal returned_amount
    }
~~~~

A single DIM_DATE is referenced **in two roles**. A single DIM_PRODUCT is shared **with the same product_key and hierarchy**. This enables rolling up to the same category_code to compare both fact types.

### 7.3. Dimension DDL in PostgreSQL

Run these statements in an empty test database/schema:

~~~~sql
CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,
    calendar_year SMALLINT NOT NULL,
    calendar_month SMALLINT NOT NULL,
    CONSTRAINT ck_dim_date_month CHECK (calendar_month BETWEEN 1 AND 12)
);

CREATE TABLE dim_product (
    product_key BIGINT PRIMARY KEY,
    product_id VARCHAR(30) NOT NULL UNIQUE,
    product_name VARCHAR(150) NOT NULL,
    subcategory_code VARCHAR(30) NOT NULL,
    subcategory_name VARCHAR(100) NOT NULL,
    category_code VARCHAR(30) NOT NULL,
    category_name VARCHAR(100) NOT NULL
);

CREATE TABLE dim_store (
    store_key BIGINT PRIMARY KEY,
    store_code VARCHAR(30) NOT NULL UNIQUE,
    store_name VARCHAR(150) NOT NULL
);
~~~~

The hierarchy columns in DIM_PRODUCT follow a **flattened dimension** layout. The DDL above ensures each product_id is unique, but does not yet enforce that **all rows using the same subcategory_code share the same category_code**. Hierarchy consistency checks are presented later; in production systems, you can govern the taxonomy in separate tables and publish the flattened dimension from that source.

### 7.4. DDL for Two Facts with Different Grains

~~~~sql
CREATE TABLE fact_sales_line (
    sale_line_id VARCHAR(30) PRIMARY KEY,
    order_id VARCHAR(30) NOT NULL,
    sale_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL
        REFERENCES dim_store(store_key),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    gross_amount NUMERIC(14, 2) NOT NULL
        CHECK (gross_amount >= 0),
    discount_amount NUMERIC(14, 2) NOT NULL
        CHECK (discount_amount >= 0 AND discount_amount <= gross_amount),
    net_amount NUMERIC(14, 2)
        GENERATED ALWAYS AS (gross_amount - discount_amount) STORED,
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    -- Allows the returns composite FK to validate both sales line and product.
    CONSTRAINT uq_sale_line_product UNIQUE (sale_line_id, product_key)
);

CREATE TABLE fact_return_line (
    return_line_id VARCHAR(30) PRIMARY KEY,
    original_sale_line_id VARCHAR(30) NOT NULL,
    return_date_key INTEGER NOT NULL
        REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL
        REFERENCES dim_product(product_key),
    store_key BIGINT NOT NULL
        REFERENCES dim_store(store_key),
    returned_qty INTEGER NOT NULL CHECK (returned_qty > 0),
    returned_amount NUMERIC(14, 2) NOT NULL
        CHECK (returned_amount >= 0),
    currency_code CHAR(3) NOT NULL DEFAULT 'VND'
        CHECK (currency_code = 'VND'),
    CONSTRAINT fk_return_source_sale_product
        FOREIGN KEY (original_sale_line_id, product_key)
        REFERENCES fact_sales_line (sale_line_id, product_key)
);
~~~~

The UNIQUE(sale_line_id, product_key) constraint on the sales fact may look **redundant** for uniqueness because sale_line_id is already the PK. However, it is declared so PostgreSQL permits the **composite FK (original_sale_line_id, product_key)** from the returns fact, ensuring a return event **cannot reference a sales line of a different product**.

This constraint does **not** mean both facts have the same grain:

- sale_line_id is the PK of a sales line.
- return_line_id is the PK of a return event.
- original_sale_line_id is **not UNIQUE** in the returns fact because one sales line can be returned across multiple installments.

**DDL Limitation:** There is no cumulative constraint preventing total returned_qty or returned_amount across multiple return events from exceeding the original sales line's quantity/amount. That rule must be defined and verified through cross-row checks or appropriate business logic. The composite FK only guarantees that **the referenced sale exists and the product matches**.

### 7.5. Loading Sample Data with Expected Results

The following INSERTs are **model verification fixtures**, not an ETL program.

~~~~sql
INSERT INTO dim_date
    (date_key, full_date, calendar_year, calendar_month)
VALUES
    (20261001, DATE '2026-10-01', 2026, 10),
    (20261002, DATE '2026-10-02', 2026, 10),
    (20261103, DATE '2026-11-03', 2026, 11);

INSERT INTO dim_product
    (product_key, product_id, product_name,
     subcategory_code, subcategory_name,
     category_code, category_name)
VALUES
    (101, 'P01', 'Notebook',
     'GIAY', 'Paper', 'VPP', 'Office Supplies'),
    (102, 'P02', 'Ballpoint Pen',
     'BUT', 'Pens', 'VPP', 'Office Supplies'),
    (103, 'P03', 'Glass Tumbler',
     'LY', 'Drinkware', 'GD', 'Home Goods');

INSERT INTO dim_store (store_key, store_code, store_name)
VALUES
    (11, 'HN', 'Hanoi Store'),
    (12, 'HCM', 'Ho Chi Minh City Store');

INSERT INTO fact_sales_line
    (sale_line_id, order_id, sale_date_key,
     product_key, store_key, quantity,
     gross_amount, discount_amount)
VALUES
    ('S1', 'O100', 20261001, 101, 11, 2, 200000, 20000),
    ('S2', 'O101', 20261001, 101, 11, 1, 100000, 0),
    ('S3', 'O102', 20261002, 102, 11, 3, 90000, 0),
    ('S4', 'O103', 20261103, 103, 12, 1, 80000, 0);

INSERT INTO fact_return_line
    (return_line_id, original_sale_line_id,
     return_date_key, product_key, store_key,
     returned_qty, returned_amount)
VALUES
    ('R1', 'S1', 20261002, 101, 11, 1, 90000),
    ('R2', 'S1', 20261002, 101, 11, 1, 90000),
    ('R3', 'S3', 20261103, 102, 11, 1, 30000);
~~~~

Data summary:

| Fact | Line | Date | Product | Category | Quantity | Value VND |
| --- | --- | --- | --- | --- | ---: | ---: |
| Sales | S1 | Oct 1 | P01 | Office Supplies | 2 | 180,000 |
| Sales | S2 | Oct 1 | P01 | Office Supplies | 1 | 100,000 |
| Sales | S3 | Oct 2 | P02 | Office Supplies | 3 | 90,000 |
| Sales | S4 | Nov 3 | P03 | Home Goods | 1 | 80,000 |
| Return | R1 | Oct 2 | P01 | Office Supplies | 1 | 90,000 |
| Return | R2 | Oct 2 | P01 | Office Supplies | 1 | 90,000 |
| Return | R3 | Nov 3 | P02 | Office Supplies | 1 | 30,000 |

**Total sales** = 450,000 VND; **total returns** = 210,000 VND; sales minus returns across the entire dataset = **240,000 VND** by the example's definition.

### 7.6. Rolling Up the Sales Fact Independently by Category and Month

~~~~sql
SELECT
    d.calendar_year,
    d.calendar_month,
    p.category_code,
    p.category_name,
    SUM(s.quantity) AS units_sold,
    SUM(s.net_amount) AS sales_vnd
FROM fact_sales_line AS s
JOIN dim_date AS d ON d.date_key = s.sale_date_key
JOIN dim_product AS p ON p.product_key = s.product_key
GROUP BY
    d.calendar_year,
    d.calendar_month,
    p.category_code,
    p.category_name
ORDER BY d.calendar_year, d.calendar_month, p.category_code;
~~~~

| Year | Month | Category | Units Sold | Sales Revenue VND |
| ---: | ---: | --- | ---: | ---: |
| 2026 | 10 | Office Supplies | 6 | 370,000 |
| 2026 | 11 | Home Goods | 1 | 80,000 |

The result from the three October sales lines is 180,000 + 100,000 + 90,000 = **370,000**. Grouping by both year and month prevents merging same-numbered months from different years.

### 7.7. Rolling Up the Returns Fact Independently by Category and Month

~~~~sql
SELECT
    d.calendar_year,
    d.calendar_month,
    p.category_code,
    p.category_name,
    SUM(r.returned_qty) AS units_returned,
    SUM(r.returned_amount) AS returns_vnd
FROM fact_return_line AS r
JOIN dim_date AS d ON d.date_key = r.return_date_key
JOIN dim_product AS p ON p.product_key = r.product_key
GROUP BY
    d.calendar_year,
    d.calendar_month,
    p.category_code,
    p.category_name
ORDER BY d.calendar_year, d.calendar_month, p.category_code;
~~~~

| Year | Month | Category | Units Returned | Return Amount VND |
| ---: | ---: | --- | ---: | ---: |
| 2026 | 10 | Office Supplies | 2 | 180,000 |
| 2026 | 11 | Office Supplies | 1 | 30,000 |

The returns fact has event R3 in **November** for sales line S3, which occurred in **October**. This report uses **return date**, not original sale date. Sharing DIM_DATE does not turn two event dates into one.

### 7.8. The Wrong Way: Joining Two Detailed Facts Through a Shared Dimension

An error-prone report design:

~~~~sql
-- INTENTIONALLY DEMONSTRATES A WRONG JOIN: do not use results for real reporting.
SELECT
    SUM(s.net_amount) AS sai_tong_ban,
    SUM(r.returned_amount) AS sai_tong_hoan
FROM fact_sales_line AS s
JOIN fact_return_line AS r
    ON r.product_key = s.product_key
JOIN dim_date AS ds ON ds.date_key = s.sale_date_key
JOIN dim_date AS dr ON dr.date_key = r.return_date_key
WHERE s.product_key = 101
  AND ds.calendar_year = 2026
  AND ds.calendar_month = 10
  AND dr.calendar_year = 2026
  AND dr.calendar_month = 10;
~~~~

In October, P01 has:

- **Two sales lines:** S1 = 180,000, S2 = 100,000.
- **Two return lines:** R1 = 90,000, R2 = 90,000.

Joining on product_key yields **2 × 2 = 4 result rows**:

| Sales line | net_amount | Return line | returned_amount |
| --- | ---: | --- | ---: |
| S1 | 180,000 | R1 | 90,000 |
| S1 | 180,000 | R2 | 90,000 |
| S2 | 100,000 | R1 | 90,000 |
| S2 | 100,000 | R2 | 90,000 |

If you SUM directly after joining:

\[
\text{sai\_tong\_ban}=2\times(180000+100000)=560000
\]

\[
\text{sai\_tong\_hoan}=2\times(90000+90000)=360000
\]

Whereas the correct figures for P01 are **280,000 sales** and **180,000 returns**. This is a **fanout** bug caused by joining two facts that each have multiple rows per dimension member.

A valid FK does not prevent fanout. Both facts referencing product P01 does **not** mean one sales line matches one-to-one with one return line at the product_key level. Even if you join on original_sale_line_id, the relationship can still be **1:N** because one sales line can have multiple return installments; summing sales after that JOIN still risks duplication if grain is not handled.

Do not use **SUM(DISTINCT net_amount)** to "patch" the bug. Two valid sales lines can have the exact same monetary value, and SUM(DISTINCT) would drop a legitimate amount. The fix is to design aggregations around grain, not deduplicate measure values.

### 7.9. The Right Way: Drill-Across Using Multipass SQL

**Drill-across** compares measures across multiple facts along **a shared set of conformed dimensions**. Safe rules:

1. Decide the **result grain**: in this example, one row per **year + month + category**.
2. Aggregate **each fact independently** to that exact result grain.
3. JOIN the **two pre-aggregated result sets** on the **shared dimension member keys**, never on detailed fact rows.
4. Preserve groups appearing on only one side using FULL OUTER JOIN or an equivalent approach.
5. Replace NULL for a missing measure with 0 **only when the true meaning is zero events in that group**, never replace missing source data NULLs arbitrarily.

SQL:

~~~~sql
WITH sales_by_month_category AS (
    SELECT
        d.calendar_year AS yr,
        d.calendar_month AS mo,
        p.category_code,
        p.category_name,
        SUM(s.net_amount) AS sales_vnd
    FROM fact_sales_line AS s
    JOIN dim_date AS d ON d.date_key = s.sale_date_key
    JOIN dim_product AS p ON p.product_key = s.product_key
    GROUP BY
        d.calendar_year,
        d.calendar_month,
        p.category_code,
        p.category_name
),
returns_by_month_category AS (
    SELECT
        d.calendar_year AS yr,
        d.calendar_month AS mo,
        p.category_code,
        p.category_name,
        SUM(r.returned_amount) AS returns_vnd
    FROM fact_return_line AS r
    JOIN dim_date AS d ON d.date_key = r.return_date_key
    JOIN dim_product AS p ON p.product_key = r.product_key
    GROUP BY
        d.calendar_year,
        d.calendar_month,
        p.category_code,
        p.category_name
)
SELECT
    COALESCE(s.yr, r.yr) AS calendar_year,
    COALESCE(s.mo, r.mo) AS calendar_month,
    COALESCE(s.category_code, r.category_code) AS category_code,
    COALESCE(s.category_name, r.category_name) AS category_name,
    COALESCE(s.sales_vnd, 0) AS sales_vnd,
    COALESCE(r.returns_vnd, 0) AS returns_vnd,
    COALESCE(s.sales_vnd, 0)
        - COALESCE(r.returns_vnd, 0) AS sales_after_returns_vnd
FROM sales_by_month_category AS s
FULL OUTER JOIN returns_by_month_category AS r
    ON s.yr = r.yr
   AND s.mo = r.mo
   AND s.category_code = r.category_code
ORDER BY
    calendar_year,
    calendar_month,
    category_code;
~~~~

Result:

| Year | Month | Category | Sales VND | Returns VND | Sales After Returns VND |
| ---: | ---: | --- | ---: | ---: | ---: |
| 2026 | 10 | Office Supplies | 370,000 | 180,000 | 190,000 |
| 2026 | 11 | Home Goods | 80,000 | 0 | 80,000 |
| 2026 | 11 | Office Supplies | 0 | 30,000 | -30,000 |

**The negative row in November is meaningful:** return amounts for the Office Supplies category occurred in November even though the dataset has no sales transactions for that category in November. That is the right result **under the example's event-date and formula definitions**, not an error to clamp to 0. If you need "returns on transactions sold in October", you must use **original sale date** as the grouping key instead of return date.

In this query, **category_code** is the conformed category-level key; category_name is the shared label under the example's Type 1 policy. If the same category_code had multiple category_names in the dimension, one CTE could produce **multiple rows** for the same JOIN key and reintroduce fanout. Therefore, **checking the uniqueness of the code–name relationship** is a prerequisite before promoting the query to production.

### 7.10. Can Quantity Be Added to the Drill-Across Query?

You can add SUM(quantity) and SUM(returned_qty) to both CTEs, provided you note clearly:

- Sharing the name "quantity" does not prove identical units of measure.
- Sales and return quantities may be measured in **selling units, cases, pieces, or kg** depending on business rules.
- If products use different units, summing by category may be **physically meaningless**.
- A quantity-based return rate must use **numerator and denominator in the same unit and over the same defined transaction set**.

A ratio of "monthly returned quantity / monthly sold quantity" can exceed 100% when returns from prior months arrive late. If the goal is the return rate of sales cohorts, you must define a **cohort by sale date**, not just two event-calendar measures.

## 8. Proving Conformed Dimensions and Correct Hierarchies with Data Checks

A clean diagram does not prove classification data is consistent. You must verify **logical invariants**, distinguishing what PK/FK/UNIQUE already protect from what requires multi-row checks.

### 8.1. A Subcategory Code Must Not Point to Multiple Categories in a Strict Hierarchy

For the flattened DIM_PRODUCT example, check:

~~~~sql
SELECT
    subcategory_code,
    COUNT(DISTINCT category_code) AS category_count
FROM dim_product
GROUP BY subcategory_code
HAVING COUNT(DISTINCT category_code) > 1;
~~~~

Expect **0 rows** if subcategory_code is globally unique under a Type 1 policy. If subcategory codes are unique only per tenant, the check must add **tenant_id** to GROUP BY and the classification key; if the hierarchy changes over time, you must evaluate **effective date ranges/versions** rather than banning all historical changes.

**Check that category labels are consistent with category_code:**

~~~~sql
SELECT
    category_code,
    COUNT(DISTINCT category_name) AS name_count
FROM dim_product
GROUP BY category_code
HAVING COUNT(DISTINCT category_name) > 1;
~~~~

Expect **0 rows** for the sample dataset. If one code has multiple labels due to translations or history, the model must specify a language/version dimension rather than merely storing similar-looking labels.

### 8.2. Totals by Category Must Reconcile with the Fact Total

~~~~sql
WITH totals AS (
    SELECT SUM(net_amount) AS fact_total
    FROM fact_sales_line
),
rolled AS (
    SELECT SUM(s.net_amount) AS category_total
    FROM fact_sales_line AS s
    JOIN dim_product AS p ON p.product_key = s.product_key
)
SELECT
    totals.fact_total,
    rolled.category_total,
    totals.fact_total - rolled.category_total AS difference
FROM totals CROSS JOIN rolled;
-- Expected: 450000, 450000, 0.
~~~~

Here, the JOIN uses **product_key, which is unique in dim_product**, so each fact row matches at most one product. The NOT NULL FK constraint guarantees an existing product provided constraints are enforced and data is not altered out-of-band. If you replace DIM_PRODUCT with a **many-to-many bridge**, reconciliation must account for allocation/weights; simply summing after a JOIN is no longer safe.

### 8.3. Checking That Returned Quantities Do Not Exceed Sold Line Quantities

The FK from the returns fact to the sales fact is unaware of cumulative returned quantities across multiple events:

~~~~sql
SELECT
    s.sale_line_id,
    s.quantity AS sold_qty,
    SUM(r.returned_qty) AS total_returned_qty
FROM fact_sales_line AS s
JOIN fact_return_line AS r
    ON r.original_sale_line_id = s.sale_line_id
GROUP BY s.sale_line_id, s.quantity
HAVING SUM(r.returned_qty) > s.quantity;
~~~~

Expect **0 rows** in the sample dataset: S1 sold 2 and was returned twice, 1 each; S3 sold 3 and had 1 returned.

This query only **detects** existing violations; to **prevent** two concurrent return transactions from exceeding the sold quantity, the system needs safely designed business logic or database transactions. This also shows that conformed dimensions do not replace cross-event integrity rules.

### 8.4. Checking Two Facts Sharing a Dimension Does Not Imply the Same Event

If reconciling returns by **return month**, summing via DIM_DATE must match the return-event calendar; if reconciling returns by **original sale month**, you must follow the lineage through original_sale_line_id and sale_date_key to determine the sales calendar:

~~~~sql
SELECT
    d.calendar_year,
    d.calendar_month,
    SUM(r.returned_amount) AS returns_by_original_sale_month
FROM fact_return_line AS r
JOIN fact_sales_line AS s
    ON s.sale_line_id = r.original_sale_line_id
JOIN dim_date AS d ON d.date_key = s.sale_date_key
GROUP BY d.calendar_year, d.calendar_month
ORDER BY d.calendar_year, d.calendar_month;
-- With sample data: all 210000 is attributed to sales month 10/2026.
~~~~

In this query, each return event points to **exactly one** sale_line_id, so joining to the sales fact is used to **read the original sale date attribute for each return event**. We only SUM **returned_amount** (the measure on the "many" side), and **do not SUM net_amount from the sales side** on this 1:N join result. This is a crucial distinction between a targeted context-lookup JOIN and blindly joining two facts to sum all measures.

### 8.5. Pre-Publication Testing Review

| Guarantee needed | Feasible check | Notes |
| --- | --- | --- |
| Each fact has the right grain | UNIQUE sale_line_id / return_line_id | Keys must be stable within source/tenant scope |
| No orphaned product_key | FK to DIM_PRODUCT | Does not prove category assignment is business-accurate |
| Subcategory has one category in a strict hierarchy | GROUP BY subcategory_code and COUNT DISTINCT category_code | Scope properly by tenant/version |
| category_code has a consistent name | GROUP BY category_code | Account for language and history rules |
| Roll-up neither drops nor multiplies rows | Reconcile fact total against post-dimension-JOIN total | Choose additive measures |
| Allocation bridge preserves total | Verify sum of weights and post-allocation total | Per group and effective timestamp |
| Returns fact matches product on sales line | Composite FK on sales line + product_key | Does not prevent over-returning quantities |
| Multiple facts share dimension definitions | Audit identity, taxonomy, and time mappings | Cannot rely solely on matching column names |
| Drill-across query avoids fanout | Aggregate each fact separately to shared keys before joining | Each CTE must have at most one row per JOIN key |

## 9. Advanced Scenarios in Shared Dimensions

### 9.1. Hierarchy Changes While Still Requiring Historical Reconciliation

Suppose P01 is classified as follows:

~~~~text
Before 2026-11-01:
    product_id=P01, product_key=101, category=VPP

From 2026-11-01:
    product_id=P01, product_key=104, category=QUATANG
~~~~

In an **SCD Type 2** dimension, each version has its **own surrogate key**. A historical report by category at the time of sale keeps October facts on product_key 101 and November facts on 104.

If another fact only stores product_id = P01 and joins DIM_PRODUCT on product_id, it can match **both versions** and double the rows. Therefore:

- When using SCD2, facts must point to the **appropriate dimension version** or follow a verified "as-of" lookup rule.
- If you want classification **as of the current state**, use a mapping path to the current version or a dedicated current-attribute/dimension structure; never accidentally join all versions and sum.
- Both facts must agree on **which timestamp and event select the version** to perform historical drill-across.

With a time dimension, a hierarchy can be **strict at every point in time** yet change across points in time. If you validate across all versions using GROUP BY product_id HAVING COUNT(DISTINCT category_code) > 1, you will flag **legitimate** historical changes. A proper check must distinguish **valid history** from **two conflicting classifications active simultaneously**.

### 9.2. A Shared Dimension Should Not Have Its Definition Altered Unilaterally

When marketing wants to move several SKUs between categories, taxonomy changes can impact:

- Revenue reports by category.
- Return reports by category.
- Inventory and stock-turnover dashboards.
- Previously published period-over-period trend metrics.

You must decide on **taxonomy versioning** and how historical figures are treated, publish schema/contract changes, and test impacts across all facts. If one team updates DIM_PRODUCT while another keeps an outdated copy, the two are no longer conformed on the affected attributes.

**A conformed dimension is a governance and data-evolution commitment**, not just a table reused across queries.

### 9.3. Handling Missing Product Codes

When a sales_line contains a product not yet present in DIM_PRODUCT, you can:

- Hold the row in staging until the corresponding dimension arrives.
- Assign an **unknown product member** with its own product_key and category_code = UNKNOWN, then backfill once trusted data arrives.
- Temporarily display a clearly named "Unclassified" group.

If reporting **complete company revenue** is mandatory before product onboarding finishes, using an unknown member can be a pragmatic choice. From a hierarchy standpoint, however, "Unknown" is **not a real business category**. When computing category mix or taxonomy quality KPIs, unclassified revenue must be separated clearly.

Do not use a single blank label for two distinct states:

- **Unknown** which category the product belongs to.
- Category classification is **not applicable** to the product.

They lead to different operational actions and reporting rules.

### 9.4. Same category_code Across Different Tenants or Markets

In a multi-tenant system, category code **GD** in tenant A can mean something completely different from tenant B. You must scope the conformed dimension appropriately:

~~~~text
product_business_key = (tenant_id, product_id)
category_business_key = (tenant_id, category_code)
~~~~

A model may assign a system-wide surrogate key to these members, but mapping from business keys must still include tenant. If tenant is omitted in a JOIN, reports may attribute revenue to another customer's or company's category.

Furthermore, rolling up revenue across tenants only makes sense if **currency, revenue definitions, return policies, and time windows** are aligned. "Both having an amount column" does not make two measures additive together.

### 9.5. Multi-Currency Data

Suppose a sales fact is recorded in VND and a returns fact in USD. Even if both share DIM_PRODUCT and DIM_DATE, you must not directly compute:

\[
SUM(\text{sales\_amount})-SUM(\text{return\_amount})
\]

unless values have been converted to a common currency under an approved policy.

A model can:

- Store currency_code alongside the original amount and group by currency.
- Store an additional converted amount along with exchange rate, rate timestamp, and rate source columns.
- Use a currency dimension and a time-varying exchange-rate model.

This is a **measure semantic constraint**, not an issue solved merely by adding an FK. Conformed dimensions solve **analytical axes**; arithmetic across facts still requires **compatible measures**.

### 9.6. Multiple Different Classifications for the Same Product

If marketing wants to classify products for two campaigns, you can build:

~~~~text
DIM_PRODUCT
DIM_CATEGORY
DIM_MARKETING_COLLECTION
BRIDGE_PRODUCT_COLLECTION
~~~~

Do not merge **category_code** and **collection_code** into one "group" column, because category can form a strict tree while collection is typically many-to-many. When drilling across revenue and returns by collection:

1. Select the same **product–collection relationship version** for both facts.
2. Specify whether **weight allocation** applies.
3. If allocating, apply weights at the appropriate grain before aggregating.
4. Never sum overlapping totals from unallocated tagged groups.

### 9.7. Hierarchies with Loops and Cycles

In a parent–child organizational dimension, a cycle A → B → C → A prevents recursive roll-up from ever reaching a true root. Likewise, if a unit has two paths up to the same level, a recursive query can count it twice.

You must enforce:

- **Acyclicity** under the accepted tree/DAG structure.
- **Correct parent cardinality** per strict or non-strict rules.
- **Temporal validity**, preventing two parent links from being active simultaneously under a strict model.
- **Unit/tenant scoping** if identical unit codes appear across systems.

Never assume a single FK(parent_id) proves the hierarchy is an acyclic tree; an FK only guarantees **the parent exists** when parent_id is non-null.

## 10. Adding a Snapshot Fact: A Shared Dimension Does Not Make Measures Additive Over Time

Suppose the warehouse team wants to report **end-of-day inventory by product and warehouse**. This is a third fact with a different grain from sales and returns:

> Each row in FACT_INVENTORY_DAILY represents the end-of-day inventory of one product at one warehouse, identified by **(date_key, product_key, warehouse_key)**.

### 10.1. Inventory Schema and Sample Data

This SQL continues on the test database created in section 7:

~~~~sql
CREATE TABLE dim_warehouse (
    warehouse_key BIGINT PRIMARY KEY,
    warehouse_code VARCHAR(30) NOT NULL UNIQUE,
    warehouse_name VARCHAR(150) NOT NULL
);

CREATE TABLE fact_inventory_daily (
    date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    product_key BIGINT NOT NULL REFERENCES dim_product(product_key),
    warehouse_key BIGINT NOT NULL REFERENCES dim_warehouse(warehouse_key),
    on_hand_qty INTEGER NOT NULL CHECK (on_hand_qty >= 0),
    PRIMARY KEY (date_key, product_key, warehouse_key)
);

INSERT INTO dim_warehouse
    (warehouse_key, warehouse_code, warehouse_name)
VALUES (21, 'WH-HN', 'Hanoi Warehouse');

INSERT INTO fact_inventory_daily
    (date_key, product_key, warehouse_key, on_hand_qty)
VALUES
    (20261001, 101, 21, 200),
    (20261002, 101, 21, 180);
~~~~

FACT_INVENTORY_DAILY reuses **DIM_DATE and DIM_PRODUCT**, but adds **DIM_WAREHOUSE**; do not force warehouse_key into store_key. A warehouse and a store may be related logistically yet **are not the same analytical location type**.

### 10.2. Why Is SUM(200 + 180) Wrong?

The warehouse held:

- 200 units of product P01 **at the end of Oct 1**.
- 180 units of product P01 **at the end of Oct 2**.

These two numbers are **two point-in-time snapshots** of the same stock. Summing them to 380 is not period-ending inventory. Depending on the question:

- **Period-ending inventory** on Oct 2 is **180**.
- **Average balance across the two snapshots** is **190**, if an average across those two snapshots is meaningful and approved.
- **Net change from opening to closing** is -20.

Inventory is a **semi-additive measure over time**. It can be summed **across warehouses** or **across products** at the **same point in time**, provided units of measure match and double counting is avoided, but must not be summed across days like sales revenue.

SQL for end-of-day inventory on Oct 2:

~~~~sql
SELECT
    d.full_date,
    p.product_id,
    SUM(i.on_hand_qty) AS on_hand_end_of_day
FROM fact_inventory_daily AS i
JOIN dim_date AS d ON d.date_key = i.date_key
JOIN dim_product AS p ON p.product_key = i.product_key
WHERE d.full_date = DATE '2026-10-02'
GROUP BY d.full_date, p.product_id
ORDER BY p.product_id;
-- P01: 180 units at warehouse WH-HN.
~~~~

### 10.3. Comparing Sales Velocity and Inventory

To calculate "sales-to-stock ratio" or "days of inventory", you cannot simply join all three facts on product_key and SUM every measure:

- Sales is a **stream of events** over a time interval.
- Returns is a **stream of events** over a time interval.
- Inventory is a **snapshot** at a point in time.

You must align on:

1. **The sales measurement window**, such as the entire month of October.
2. **The inventory point in time** (month-end, month-start, or average across snapshots).
3. Whether **units of measure** are compatible and converted where needed.
4. **The shared analytical level**: SKU, subcategory, or category; and whether warehouses must be distinguished from stores.
5. **The ratio formula and zero-denominator handling**.

Then aggregate each fact to the appropriate level before computing the ratio. **Sharing DIM_PRODUCT** ensures accurate grouping by product/category, but does not replace measurement rules.

## 11. Hierarchy and Conformed Dimension Design Checklist

Before publishing a shared dimension across multiple facts, complete these steps:

1. **Lock down business questions.** At what levels must revenue, returns, and inventory be analyzed? Do reports share the same timeframes and scope?
2. **Define the grain of each fact.** Sales line, return event, inventory snapshot; never assume facts share the same detail level.
3. **List candidate conformed dimensions.** Date, product, customer, location; determine which are truly shared versus merely sharing a name.
4. **Define business keys and surrogate keys.** Include tenant/source/version when required; avoid joining on display labels.
5. **Map every hierarchy path.** SKU → subcategory → category; day → month → year; distinguish alternative hierarchies.
6. **Assess strictness, completeness, and raggedness.** How many parents can each member have? Are missing groups allowed? Are levels skipped?
7. **Evaluate measures.** Can SUM, DISTINCT, end-of-day stock, and ratios be recomputed cleanly from proper components?
8. **Choose relational representations.** Flattened dimension, snowflake, parent–child, or weighted bridge matching business rules.
9. **Finalize the history policy.** Use current classification or classification at event time? By what rule do facts link to dimension versions?
10. **Build the bus matrix.** Explicitly document roles of the same DIM_DATE and distinctions between DIM_STORE and DIM_WAREHOUSE.
11. **Design drill-across queries.** Choose a common output grain; aggregate each fact before joining; preserve one-sided groups.
12. **Run quality checks.** No orphans, no conflicting hierarchies, no invalid overlapping versions, total reconciliation, and bridge weight checks.
13. **Test counterexamples.** Two facts with multiple rows per product; one SKU in two collections; unclassified products; multi-version SCDs; weeks crossing months.
14. **Assign dimension ownership.** Who approves taxonomy changes, refreshes conformed copies, and alerts affected reports?
15. **Optimize physically only afterward.** Tune indexes, partitions, pre-aggregations, and caching based on real queries; never alter semantics to avoid a JOIN.

### Minimum Deliverable Documentation

| Deliverable | Minimum required contents |
| --- | --- |
| **Dimension specification** | Members, keys, attributes, scope, Unknown handling, history policy |
| **Hierarchy specification** | Names/levels, strict/completeness, level-skipping/multi-parent rules, time rules |
| **Bus matrix** | List of processes/facts and shared dimensions |
| **Metric contract** | Formulas, units, time boundaries, additivity conditions, and reconciliation |
| **Drill-across contract** | Shared output grain, result JOIN keys, missing-group handling policy |
| **Quality tests** | Uniqueness, conformance, overlap, bridge weights, and roll-up rules |
| **Versioning/governance** | Taxonomy owner, change effective dates, historical reporting policy |

Such documentation serves as a **design contract** for ETL/ELT, BI, data governance, and operations teams. Implementing dimension sync jobs, fact loads, SCD backfills, or automated test execution belongs to subsequent implementation phases; those tasks do not change the correct definition of the model.

## 12. Practice Exercises with Answers

### Exercise 1 — Roll-up by Subcategory and Category

In October, P01 generated 280,000 VND in revenue and belongs to the Paper subcategory, while P02 generated 90,000 VND and belongs to the Pens subcategory. Both Paper and Pens belong to the Office Supplies category. The hierarchy is strict and complete; revenue is additive.

**Question:** What is the revenue for each subcategory and for the category?

**Answer:** Paper subcategory = **280,000**, Pens subcategory = **90,000**; Office Supplies category = **370,000 VND**. The two subcategories do not overlap and cover the relevant rows, so the category total equals the sum of the two subcategories. If a product belonged to both subcategories, straight addition would no longer be safe.

### Exercise 2 — Strict Hierarchy Lacking Complete Coverage

A fact table has total revenue of 380,000 VND. Of this, 370,000 VND is classified by category, while 10,000 VND comes from product P99, which has no category assigned yet.

**Question:** If you only use an INNER JOIN to the classified catalog, is the report wrong? What options exist?

**Answer:** The category report sums only to **370,000**, dropping 10,000; if published as the **company-wide total**, it is wrong. You can use an **Unclassified** group, hold the rows until the taxonomy is updated, or apply an agreed handling rule. Never silently change the scope to "classified revenue" while keeping a company-total label.

### Exercise 3 — Many-to-Many Hierarchy and Allocation

Product P01 sold 100,000 VND and appears in two collections, A and B. The allocation rule is A = 0.7 and B = 0.3.

**Question:** If the full amount is tagged to both collections, what is the sum? If allocated, what is the result?

**Answer:** Full tagging produces A = 100,000 and B = 100,000, totaling **200,000**, which cannot be treated as company-wide revenue. Weighted allocation yields A = **70,000** and B = **30,000**, totaling **100,000**. You must verify that weights sum to 1 per product, scope, and time period.

### Exercise 4 — Bus Matrix for Three Facts

You have FACT_SALES_LINE, FACT_RETURN_LINE, and FACT_INVENTORY_DAILY. Date and product appear in all three facts. Sales and returns have store; inventory has warehouse.

**Question:** Which dimensions are shared candidates? Should store and warehouse be treated as one dimension just because both are locations?

**Answer:** DIM_DATE and DIM_PRODUCT are **candidate conformed dimensions** for all three. DIM_STORE can be shared between sales and returns if roles and definitions align; DIM_WAREHOUSE is separate for inventory. Do not automatically equate store_key and warehouse_key: a store can receive stock from multiple warehouses and one warehouse serves multiple stores.

### Exercise 5 — Same Name but Not Conformed

Sales maps P01 → category_code VPP; Returns maps P01 → category_code GIFT because Returns uses a marketing classification. Both tables have a category_code column.

**Question:** Can you GROUP BY category_code and FULL JOIN both reports?

**Answer:** You cannot yet treat both columns as the same category-level dimension. You must standardize the taxonomy or define an **explicit mapping to a shared level** with valid business meaning. Joining directly on category_code can split or merge metrics incorrectly. **Matching attribute names does not mean conformed.**

### Exercise 6 — Drill-Across Revenue and Returns

Sample data:

- October, Office Supplies: sales 370,000 VND, returns 180,000 VND.
- November, Office Supplies: no new sales, returns 30,000 VND.
- November, Home Goods: sales 80,000 VND, no returns.

**Question:** Calculate sales minus returns per month/category and the overall total. Why does November show a negative number?

**Answer:** October Office Supplies = **190,000**; November Office Supplies = **-30,000**; November Home Goods = **80,000**. Total = **240,000 VND**. The negative row appears because the report uses **return occurrence date**, so November includes returns from earlier sales. It does not indicate bad data.

### Exercise 7 — Joining Detailed Facts Corrupts Totals

In October, P01 has two sales lines of 180,000 and 100,000, and two return lines of 90,000 and 90,000. A developer joins both facts directly on product_key and sums both measures.

**Question:** How many rows result from the JOIN? How are the SUMs distorted?

**Answer:** There are **4 rows** (2 × 2). Total sales becomes **560,000** instead of 280,000; total returns becomes **360,000** instead of 180,000. You must aggregate sales and returns separately to **P01 + month** (or the target shared level), then join the two results.

### Exercise 8 — Can SUM(DISTINCT) Fix Fanout?

Two separate sales lines for a product both have net_amount = 90,000 VND.

**Question:** If SUM(DISTINCT net_amount) is used, what is the result? Is it correct?

**Answer:** SUM(DISTINCT) returns **90,000**, whereas valid total sales is **180,000**. DISTINCT removes **duplicate measure values**, without distinguishing **two legitimate events**. Fix fanout with proper grain and JOIN patterns, not with DISTINCT on monetary values.

### Exercise 9 — Role-Playing DIM_DATE

An order is placed on Oct 1, handed to the carrier on Oct 2, and delivered to the customer on Oct 5. Three columns—order_date_key, ship_date_key, and delivery_date_key—all reference DIM_DATE.

**Question:** Which key must a report of "orders by order date" use? Why not substitute delivery_date_key?

**Answer:** Use **order_date_key**. DIM_DATE is one reused table, yet each FK plays a **distinct business role**. Substituting delivery_date_key produces a report by **delivery date**, not order date, even though both JOINs are syntactically valid.

### Exercise 10 — Timing of an SCD2 Dimension

P01 belonged to VPP through Oct 31; effective Nov 1 it moved to Gifts. A P01 line sold on Oct 1 is later returned on Nov 3.

**Question:** Should the returns fact point to the VPP or Gifts version?

**Answer:** **It depends on the report definition.** If asking "returns generated in the category active at the time of return", use the Gifts version. If asking "returns attributed to the category of the original sale", use the VPP version from the sale date. Both can be valid; document the role/time conformance policy clearly to avoid invalid comparisons.

### Exercise 11 — Type 2 and Joining on Business Key

DIM_PRODUCT has two rows for product_id P01 with product_keys 101 and 104 due to SCD2. FACT_SALES_LINE stores product_id P01, and a developer joins DIM_PRODUCT solely on product_id.

**Question:** What happens? How should it be fixed?

**Answer:** One P01 sales line can join into **two rows**, doubling the measures. The fact should store the **versioned surrogate key selected for the right point in time**, or apply a clearly ruled effective-range lookup. Do not join all versions on the business key without filtering by timestamp or version.

### Exercise 12 — Inventory Is Non-Additive Over Time

P01 at warehouse W1 has end-of-day inventory of 200 on Oct 1 and 180 on Oct 2.

**Question:** What is the end-of-day inventory on Oct 2? Can "two-day" inventory be reported using SUM = 380?

**Answer:** End-of-day inventory on Oct 2 is **180**. SUM = 380 is not a meaningful inventory balance. You may compute a snapshot average = **190** if the KPI is truly the average across two snapshots; distinguish **semi-additive measures** from revenue that is additive over time.

### Exercise 13 — ISO Weeks and Calendar Months

An ISO week begins at the end of September and ends at the beginning of October. A designer proposes the path Day → ISO Week → Calendar Month.

**Question:** Is this naturally a strict hierarchy path?

**Answer:** No. An ISO week can **span two months**, so Week → Month is not naturally a unique many-to-one relationship. You need a rule assigning weeks to months (by start date, end date, or majority of days), or you must aggregate from **day** up to month and up to week along **two separate hierarchies**.

### Exercise 14 — Tenant-Scoped Category Codes

Tenant A and tenant B both use category_code = GD, but with different meanings and labels.

**Question:** Can two marts be joined solely on GD? What key design is appropriate?

**Answer:** No. Define the category key scoped as **(tenant_id, category_code)** or a system-wide surrogate key with explicit mapping. If cross-tenant analysis is desired, a harmonization policy is also required: do the two groups truly share the same meaning to be combined?

### Exercise 15 — Summing After a Bridge Table

A product is allocated across three groups with weights 0.4, 0.4, and 0.3.

**Question:** Even though every weight is within [0,1], does the allocation preserve the total?

**Answer:** **No.** The sum of weights is **1.1**, turning 100,000 revenue into **110,000 VND** after allocation. A per-row CHECK from 0 to 1 is insufficient; you must verify that weights sum **to 1 for each product and applicable time scope**.

### Exercise 16 — Are Distinct Customers Additive Across Product Subcategories?

Customer C01 buys one product in category VPP and one product in category GD. Each category has one DISTINCT customer.

**Question:** Is the company-wide customer count 1 + 1 = 2?

**Answer:** No, the total DISTINCT customer count is **1**. The same customer appears in both categories, making distinct customer count **non-additive across categories**. You must compute COUNT(DISTINCT customer_id) over the company-wide transaction set or use a distinct mechanism matching the report grain.

### Exercise 17 — Testing Conformance at the Category Level

Two independent data marts share similar category groups. Mart A and Mart B both report VPP and GD, yet product_key 101 in A is P01, while product_key 101 in B is P99.

**Question:** Can you join product_key directly? To compare at the category level, what is required?

**Answer:** You cannot join product_key across two marts if surrogate keys were generated independently. You can compare at **category_code** once you prove it shares the same meaning, scope, and versioning across both marts. Comparing at the product level requires reliable, verified product identity mapping.

### Exercise 18 — Designing Tests for a Shared Dimension

A project created DIM_PRODUCT, FACT_SALES_LINE, and FACT_RETURN_LINE. The lead says "because both facts have product_key, accurate comparison is already guaranteed."

**Question:** List at least four checks required before accepting that conclusion.

**Answer guidelines:**

1. Do both FKs truly reference the **same identifier set in DIM_PRODUCT** or have a verified conformed mapping?
2. Does each product_key have a unique **hierarchy path** at the reporting level and applicable scope/timestamp?
3. Do both facts apply **historical classification policies** compatible with the KPI being compared?
4. Have **measure and currency** compatibility been verified?
5. Do queries **aggregate each fact independently** before joining, avoiding fanout?
6. Have **missing dimensions, multiple versions, many-to-many bridges, and total reconciliations** been tested?

Merely sharing a key column name is only an initial technical condition, insufficient to guarantee analytical semantics.

## 13. Summary

| Topic | Core rule |
| --- | --- |
| **Hierarchy** | Path from detailed members to summary levels; define rules assigning members to levels |
| **Roll-up / drill-down** | Changing aggregation level; must respect grain and measure properties |
| **Strict hierarchy** | Lower-level member has at most one parent in the same scope and point in time |
| **Complete hierarchy** | Every member to be reported has a valid path to an appropriate level |
| **Non-strict hierarchy** | Multiple parents; preserving totals may require allocation via bridge weights |
| **Ragged hierarchy** | Hierarchy paths with skipped levels or uneven depth; requires display and aggregation rules |
| **Summarizability** | Single-valued paths, completeness, compatible measures, and fanout-free JOINs |
| **Flat dimension** | Multiple hierarchy levels in one table for easy querying; must enforce dependencies and consistency |
| **Snowflake** | Splits levels into FK-linked tables; aids hierarchy governance at the cost of extra JOINs |
| **Parent–child** | Flexible for unbalanced trees; must control cycles, effective dates, and parent counts |
| **Conformed dimension** | Consistent identity, values, hierarchies, history, and scope usable across facts |
| **Bus matrix** | Process/fact × dimension matrix identifying shared dimensions and distinct roles |
| **Role-playing dimension** | One dimension reused across multiple FK roles, e.g., sale date vs. return date |
| **SCD2** | Facts must link to the right dimension version and point-in-time semantics |
| **Drill-across** | Aggregate each fact independently to a shared conformed level before joining results |
| **Fact-to-fact fanout** | Joining detailed facts across shared dimension keys multiplies rows and corrupts measures |
| **Semi-additive** | End-of-day inventory must not be SUMmed over time like revenue |
| **Verification** | Audit taxonomy consistency, keys, versions, weights, total reconciliation, and fanout counterexamples |

**Conclusion:** Dimension hierarchies turn catalogs, calendars, and organizations into meaningful **roll-up/drill-down axes**, yet accurate aggregation is only possible when membership relationships are sound, data coverage is handled, and measures are additive. **Conformed dimensions** allow multiple facts to share analytical semantics despite differing grains and event timestamps. To compare sales, returns, and inventory, define **keys, hierarchies, time roles, history policies, and a shared output grain**, then **aggregate each fact before joining**. This is the foundation for an analytical model whose numbers remain consistent, explainable, and verifiable as the business evolves.
