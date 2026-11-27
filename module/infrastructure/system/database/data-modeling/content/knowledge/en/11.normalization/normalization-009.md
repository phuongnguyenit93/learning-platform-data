# Step-by-Step Normalization Process from an Unnormalized Order Table

An initial order schema is often designed directly around a data-entry screen: **an order has a customer, a shipping address, a list of products, quantities, prices, and categories**. If you copy that screen verbatim into one large table, anomalies quickly appear: renaming a customer requires updating many rows, deleting the last line item wipes out the order, renaming a category forces updates across many products, or you cannot create an order before adding products.

**Data normalization** is the process of determining **which entity each fact belongs to**, writing out **functional dependencies**, identifying **candidate keys**, and decomposing relations to reduce redundancy without losing information. This lesson belongs to the **Normalization** chapter of the **DATABASE_DATA_MODELING** module, focusing on one end-to-end example from an unnormalized structure to **1NF → 2NF → 3NF** relations while distinguishing current business data from **historical transaction snapshots**.

After this lesson, you will be able to:

- Define the *grain* (what one row represents) for orders and order lines.
- Spot repeating groups, partial dependencies, transitive dependencies, and insertion/update/deletion anomalies.
- Decompose step by step and apply appropriate **PRIMARY KEY**, **FOREIGN KEY**, **UNIQUE**, and **CHECK** constraints.
- Reconcile joins and verify data when migrating from a legacy structure to the normalized schema.
- Explain why price at purchase time or shipping address at order placement **is not necessarily bad redundant data**.

## 1. Start from Business Requirements, Not from CREATE TABLE

Suppose a sales system in Vietnam has the following rules:

1. An **order** has a unique **order_id**, an order date, and one customer who placed it.
2. A **customer** has a unique **customer_id**, a name, and one **current** contact phone number within the scope of this example. A customer can place many orders.
3. An order has **multiple line items**. **line_no** numbers the lines within each order, so two different orders can both have **line_no = 1**.
4. A **product** has a unique **product_id**, a current name, and belongs to one current category. A category contains many products.
5. Each line item has **one product**, a positive **quantity**, and **unit_price_vnd_at_order**, which is the VND unit price locked in for **that specific line**. Two orders can purchase the same product at different unit prices.
6. **ship_to_address_at_order** is the shipping address locked in when the order was placed—**not** the current contact address in the customer profile.
7. The same product **can appear on multiple lines of the same order**, for instance due to promotional pricing or different delivery terms. Therefore, do not assume **(order_id, product_id)** is a key.
8. Orders and products exist independently: an order can be created before it has line items; a product can be cataloged before anyone orders it.

An order-entry screen might produce raw payloads shaped like:

~~~json
{
  "order_id": "O1001",
  "placed_on": "2026-11-20",
  "customer": {
    "customer_id": "C01",
    "customer_name": "An",
    "customer_phone": "+84901234567"
  },
  "ship_to_address_at_order": "12 Nguyen Hue, TP.HCM",
  "items": [
    {
      "line_no": 1,
      "product_id": "P10",
      "product_name": "Keyboard",
      "category_id": "CAT10",
      "category_name": "Peripherals",
      "quantity": 2,
      "unit_price_vnd_at_order": 300000
    },
    {
      "line_no": 2,
      "product_id": "P20",
      "product_name": "Mouse",
      "category_id": "CAT10",
      "category_name": "Peripherals",
      "quantity": 1,
      "unit_price_vnd_at_order": 200000
    }
  ]
}
~~~

This JSON payload is **not inherently a bad design**: in an API or a document database, embedding line items inside an order document can be a reasonable choice. The problem arises when you try to manage multiple independent facts inside a single string or a single SQL cell without per-line keys, constraints, and operations. In this lesson, the target is a **relational schema** and how to verify its invariants.

### 1.1. The Initial Unnormalized Table

Suppose a designer places everything into a hypothetical table **order_input_raw**:

~~~text
order_id
placed_on
customer_id
customer_name
customer_phone
ship_to_address_at_order
items = "P10 x 2 @ 300000; P20 x 1 @ 200000; ..."
~~~

If **items** is a list of lines that must be searched, added, deleted, and validated individually, a column holding the whole list cannot directly declare a key per line or enforce **quantity > 0** on each element using ordinary numeric column types. Using delimiters also creates fragility when real data contains delimiter characters, missing values, or inconsistent formatting.

This is the starting point for turning a **repeating group** into independent rows.

## 2. Step 1 — Bring Data to 1NF: One Order Line per Relational Row

**First Normal Form (1NF)** requires attribute values to be represented according to their chosen domains; in modeling practice, avoid hiding independently managed business elements inside one cell. "Atomicity" depends on **domain and business needs**: the order date is a single **DATE** value, whereas the collection of line items is multiple facts requiring their own keys.

After extracting the **items** list, the table **order_lines_flat** has the *grain* of **one line item within one order**. We keep all columns describing the order, customer, and product so we can observe the issues that remain unresolved:

~~~text
order_lines_flat(
    order_id,
    line_no,
    placed_on,
    customer_id,
    customer_name,
    customer_phone,
    ship_to_address_at_order,
    product_id,
    product_name,
    category_id,
    category_name,
    quantity,
    unit_price_vnd_at_order
)
~~~

The condensed sample table below omits wider columns for readability; the omitted columns are still part of the structure listed above:

| order_id | line_no | customer_id | customer_name | product_id | product_name | category_id | quantity | unit_price_vnd_at_order |
| --- | ---: | --- | --- | --- | --- | --- | ---: | ---: |
| O1001 | 1 | C01 | An | P10 | Keyboard | CAT10 | 2 | 300000 |
| O1001 | 2 | C01 | An | P20 | Mouse | CAT10 | 1 | 200000 |
| O1002 | 1 | C01 | An | P10 | Keyboard | CAT10 | 1 | 290000 |
| O1002 | 2 | C01 | An | P30 | Monitor | CAT20 | 1 | 2500000 |
| O1003 | 1 | C02 | Bình | P20 | Mouse | CAT10 | 3 | 210000 |

The **candidate key** under the section 1 assumptions is **(order_id, line_no)**: it identifies exactly one line. **order_id** alone is insufficient because one order has multiple lines; **line_no** alone is insufficient because every order can have line 1. A superset adding **product_id** is a superkey but not minimal. Do not use **(order_id, product_id)** as a key because the business allows the same product to appear on multiple lines of one order.

An SQL schema capturing the 1NF stage—**not yet the final design**:

~~~sql
CREATE TABLE order_lines_flat (
    order_id VARCHAR(10) NOT NULL,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    placed_on DATE NOT NULL,
    customer_id VARCHAR(10) NOT NULL,
    customer_name VARCHAR(100) NOT NULL,
    customer_phone VARCHAR(20),
    ship_to_address_at_order TEXT NOT NULL,
    product_id VARCHAR(10) NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    category_id VARCHAR(10) NOT NULL,
    category_name VARCHAR(100) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd_at_order BIGINT NOT NULL
        CHECK (unit_price_vnd_at_order >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

Each column now holds an individual value, with a primary key and **CHECK** constraints for quantity and unit price. Yet data **is still redundant**: order header attributes repeat across every line, customer names repeat across orders, and product names and categories repeat across sold lines.

### 2.1. Anomalies That Remain After 1NF

- **Update:** renaming product P10's current name requires updating every row containing P10, if the flat table serves as the source of current names.
- **Insertion:** you cannot register a new order that has no products yet, because the key requires **line_no** and product columns are required.
- **Deletion:** deleting the last line item of O1003 simultaneously wipes out the order date, customer ID, and shipping address of O1003.

**Step 1 conclusion:** representing each line item as a relational row is necessary, **yet insufficient for a properly normalized design**.

## 3. Step 2 — Identify Functional Dependencies and Candidate Keys

A functional dependency **X → Y** is a rule: in every valid data state, one value of X determines at most one value of Y. Never infer dependencies merely because values happen to match across a few sample rows.

From the business requirements:

~~~text
order_id
  -> placed_on, customer_id, ship_to_address_at_order

customer_id
  -> customer_name, customer_phone

product_id
  -> product_name, category_id

category_id
  -> category_name

(order_id, line_no)
  -> product_id, quantity, unit_price_vnd_at_order
~~~

Transitive dependencies can also be derived, such as:

~~~text
order_id -> customer_id -> customer_name
product_id -> category_id -> category_name
~~~

Data granularity determines the distinctions:

- **order_id → placed_on** because an order has one order date.
- **customer_id → customer_name** because we are modeling the customer's **current name**.
- **product_id → product_name** because we are modeling the product's **current name**.
- **(order_id, line_no) → unit_price_vnd_at_order** because the transaction unit price belongs to the **order line**. **Do not** assume **product_id → unit_price_vnd_at_order**: the same product can be sold at different prices across purchases.
- **order_id → ship_to_address_at_order** because each order in this example has one locked-in shipping address. **Do not** assign **customer_id → ship_to_address_at_order**: one customer can place orders to different addresses.

~~~mermaid
flowchart TD
    K["Key (order_id, line_no)"]
    O["order_id"]
    C["customer_id"]
    P["product_id"]
    CAT["category_id"]
    OD["placed_on, ship_to_address_at_order"]
    CN["customer_name, customer_phone"]
    PN["product_name"]
    CT["category_name"]
    LV["quantity, unit_price_vnd_at_order"]
    K -->|"contains"| O
    K --> P
    K --> LV
    O --> OD
    O --> C
    C --> CN
    P --> PN
    P --> CAT
    CAT --> CT
~~~

A **full key dependency** requires the entire key to determine an attribute. A **partial dependency** occurs when a **proper subset** of a candidate key already determines a non-prime attribute. In the 1NF table with key **(order_id, line_no)**, attributes such as **placed_on** and **customer_id** require only **order_id**; hence they are partially dependent.

## 4. Step 3 — Achieve 2NF: Separate Order Header and Line Items

**2NF** requires the relation to be in 1NF and **every non-prime attribute to be fully dependent on every candidate key**. Pay special attention to composite keys.

From the dependency:

~~~text
order_id -> placed_on, customer_id, ship_to_address_at_order
~~~

we move the attributes belonging to the **order** into a separate table. An intermediate schema:

~~~text
orders_2nf(
    order_id PRIMARY KEY,
    placed_on,
    customer_id,
    customer_name,
    customer_phone,
    ship_to_address_at_order
)

order_lines_2nf(
    order_id,
    line_no,
    product_id,
    product_name,
    category_id,
    category_name,
    quantity,
    unit_price_vnd_at_order,
    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES orders_2nf(order_id)
)
~~~

**orders_2nf** has the grain of one order; **order_lines_2nf** has the grain of one line item. As a result, an order can exist before any line items are added, and deleting the last line item does not delete the order record.

In **orders_2nf**, the candidate key **order_id** is a single attribute, so there are no ordinary partial dependencies on a composite key. In **order_lines_2nf**, product attributes are determined via **product_id**, yet **product_id is not a subset of the key (order_id,line_no)**. That is a transitive dependency issue for the 3NF step, **not a 2NF partial dependency**.

### 4.1. What Did 2NF Fix and What Remains?

| Change | After the 2NF Step |
| --- | --- |
| Create order O1004 with no line items yet | Can insert into **orders_2nf** |
| Delete the last line of O1003 | **orders_2nf** retains order date/customer/address |
| Change customer C01's current name | Still requires updating multiple orders of C01 |
| Change product P10's current name | Still requires updating many line items with P10 |
| Rename category CAT10 | Still requires updating very many line items |

Therefore, **reaching 2NF does not mean all redundancy has been eliminated**.

### 4.2. Why Does Splitting into Two Tables Not Lose Information?

The original relation has key **(order_id,line_no)**. The intersection of the two attribute sets in the decomposition is **{order_id}**, and **order_id** determines all attributes of **orders_2nf** under the assumed dependencies. By the binary decomposition criterion, the split is a **lossless join** across valid original states.

When joining lines to orders on **order_id**, each line matches exactly one order. The orders table can store **orders with zero lines** without inventing dummy line rows; to inspect those orders, query starting from the orders table using a **LEFT JOIN**.

## 5. Step 4 — Achieve 3NF: Move Customer, Product, and Category Names to Their Owners

**3NF** governs non-trivial functional dependencies **X → A**: either X must be a **superkey** or A must be a **prime attribute** (belonging to at least one candidate key). In the intermediate tables above, the classic sign is a **transitive dependency** from the key to attributes of another entity.

In **orders_2nf**:

~~~text
order_id -> customer_id -> customer_name, customer_phone
~~~

**customer_id** is not a superkey of the orders table because one customer can place many orders. **customer_name** and **customer_phone** do not belong to any candidate key of the orders table. Hence **customer_id → customer_name, customer_phone** violates 3NF on **orders_2nf**.

In **order_lines_2nf**:

~~~text
(order_id, line_no) -> product_id
product_id         -> product_name, category_id
category_id        -> category_name
~~~

**product_id** is not a superkey of the line items table; product name and category ID are current attributes belonging to the product. **category_id** likewise does not identify a line item, and **category_name** belongs to the category. Thus these two levels of information must be split out according to the domain.

### 5.1. Target Schema

~~~text
customers(
    customer_id PRIMARY KEY,
    customer_name,
    customer_phone
)

categories(
    category_id PRIMARY KEY,
    category_name
)

products(
    product_id PRIMARY KEY,
    product_name,
    category_id REFERENCES categories(category_id)
)

orders(
    order_id PRIMARY KEY,
    placed_on,
    customer_id REFERENCES customers(customer_id),
    ship_to_address_at_order
)

order_lines(
    order_id REFERENCES orders(order_id),
    line_no,
    product_id REFERENCES products(product_id),
    quantity,
    unit_price_vnd_at_order,
    PRIMARY KEY (order_id, line_no)
)
~~~

Each table has a single *grain*:

| Table | What Is One Row? | Candidate Key Chosen as Primary Key |
| --- | --- | --- |
| **customers** | One customer | customer_id |
| **categories** | One product category | category_id |
| **products** | One product | product_id |
| **orders** | One order | order_id |
| **order_lines** | One line item of an order | (order_id, line_no) |

Customer names are updated in **customers**; product names in **products**; category names in **categories**. An **orders** record holds a foreign key to the customer, while **order_lines** holds foreign keys to the order and product.

### 5.2. Relational Diagram After Normalization

~~~mermaid
erDiagram
    CUSTOMERS ||--o{ ORDERS : "places"
    ORDERS ||--o{ ORDER_LINES : "contains"
    PRODUCTS ||--o{ ORDER_LINES : "appears in"
    CATEGORIES ||--o{ PRODUCTS : "categorizes"
    CUSTOMERS {
        varchar customer_id PK
        varchar customer_name
        varchar customer_phone
    }
    ORDERS {
        varchar order_id PK
        date placed_on
        varchar customer_id FK
        text ship_to_address_at_order
    }
    ORDER_LINES {
        varchar order_id PK, FK
        integer line_no PK
        varchar product_id FK
        integer quantity
        bigint unit_price_vnd_at_order
    }
    PRODUCTS {
        varchar product_id PK
        varchar product_name
        varchar category_id FK
    }
    CATEGORIES {
        varchar category_id PK
        varchar category_name
    }
~~~

With this schema, creating a new customer **does not require** an order; creating a new product **does not require** an order line; deleting an order line **does not erase** the product, customer, or category record.

### 5.3. Dependencies Placed in Their Proper Relations

~~~text
customers:
  customer_id -> customer_name, customer_phone

categories:
  category_id -> category_name

products:
  product_id -> product_name, category_id

orders:
  order_id -> placed_on, customer_id, ship_to_address_at_order

order_lines:
  (order_id, line_no)
    -> product_id, quantity, unit_price_vnd_at_order
~~~

Each dependency is determined by **the key of the table containing it** under the stated assumptions. Thus these relations satisfy **3NF**, and given the simple functional dependencies here, they also satisfy **BCNF**. Do not claim 4NF or 5NF without additionally inspecting the business for multivalued or join dependencies.

**Dependency preservation:** the primary rules are enforced locally inside individual component tables via keys or suitable constraints. **Lossless join:** every order line references exactly one order, every order references exactly one customer, every line references exactly one product, and every product references exactly one category. Joining along foreign keys reconstructs the valid original sales rows while allowing independent entities to exist before any transactions occur.

## 6. Step 5 — Implement the Normalized Schema in PostgreSQL

The example below can run on an empty database or a dedicated practice schema. Table names are the **final** names, without **_2nf** suffixes.

### 6.1. Creating Tables and Constraints

~~~sql
CREATE TABLE customers (
    customer_id VARCHAR(10) PRIMARY KEY,
    customer_name VARCHAR(100) NOT NULL,
    customer_phone VARCHAR(20)
);

CREATE TABLE categories (
    category_id VARCHAR(10) PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL
);

CREATE TABLE products (
    product_id VARCHAR(10) PRIMARY KEY,
    product_name VARCHAR(100) NOT NULL,
    category_id VARCHAR(10) NOT NULL
        REFERENCES categories(category_id)
);

CREATE TABLE orders (
    order_id VARCHAR(10) PRIMARY KEY,
    placed_on DATE NOT NULL,
    customer_id VARCHAR(10) NOT NULL
        REFERENCES customers(customer_id),
    ship_to_address_at_order TEXT NOT NULL
);

CREATE TABLE order_lines (
    order_id VARCHAR(10) NOT NULL
        REFERENCES orders(order_id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id VARCHAR(10) NOT NULL
        REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_vnd_at_order BIGINT NOT NULL
        CHECK (unit_price_vnd_at_order >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

**Why these constraints?**

- **PRIMARY KEY** uniquely identifies each entity or line item.
- **FOREIGN KEY** blocks attaching a line to a nonexistent order, referencing a nonexistent product, or assigning a product to a nonexistent category.
- **NOT NULL** protects fields required by the domain.
- **CHECK (quantity > 0)** rejects zero or negative quantities; if returns exist, model explicit return or adjustment workflows rather than overloading negative quantities.
- **CHECK (unit_price_vnd_at_order >= 0)** blocks negative prices. Zero remains valid if promotional free items exist; otherwise tighten the check per business rules.
- Omit **UNIQUE(order_id, product_id)** because one product may appear on multiple lines of the same order. The key **(order_id, line_no)** is sufficient under the chosen assumptions.

In this example, foreign keys use PostgreSQL's default behavior, so deleting an order or product does not silently cascade-delete order lines; if you want **ON DELETE CASCADE**, **RESTRICT**, or soft-deletion statuses, define explicit lifecycle rules.

### 6.2. Loading Sample Data

~~~sql
INSERT INTO customers
    (customer_id, customer_name, customer_phone)
VALUES
    ('C01', 'An',   '+84901234567'),
    ('C02', 'Bình', '+84907654321');

INSERT INTO categories (category_id, category_name) VALUES
    ('CAT10', 'Peripherals'),
    ('CAT20', 'Monitors');

INSERT INTO products (product_id, product_name, category_id) VALUES
    ('P10', 'Keyboard', 'CAT10'),
    ('P20', 'Mouse',    'CAT10'),
    ('P30', 'Monitor',  'CAT20');

INSERT INTO orders
    (order_id, placed_on, customer_id, ship_to_address_at_order)
VALUES
    ('O1001', DATE '2026-11-20', 'C01',
     '12 Nguyen Hue, TP.HCM'),
    ('O1002', DATE '2026-11-21', 'C01',
     '99 Le Loi, TP.HCM'),
    ('O1003', DATE '2026-11-22', 'C02',
     '7 Tran Hung Dao, Da Nang');

INSERT INTO order_lines
    (order_id, line_no, product_id, quantity, unit_price_vnd_at_order)
VALUES
    ('O1001', 1, 'P10', 2,  300000),
    ('O1001', 2, 'P20', 1,  200000),
    ('O1002', 1, 'P10', 1,  290000),
    ('O1002', 2, 'P30', 1, 2500000),
    ('O1003', 1, 'P20', 3,  210000);
~~~

From this data, C01 placed two orders with **two different shipping addresses**; P10 was purchased at two prices, **300000 VND** and **290000 VND**. Neither fact **contradicts** C01 having a single customer profile record or P10 having a single product catalog record.

### 6.3. Querying Back the Order Table for the UI

~~~sql
SELECT
    o.order_id,
    o.placed_on,
    c.customer_id,
    c.customer_name,
    o.ship_to_address_at_order,
    ol.line_no,
    p.product_id,
    p.product_name,
    cat.category_name,
    ol.quantity,
    ol.unit_price_vnd_at_order,
    ol.quantity::numeric * ol.unit_price_vnd_at_order
        AS line_total_vnd
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
JOIN order_lines AS ol
    ON ol.order_id = o.order_id
JOIN products AS p
    ON p.product_id = ol.product_id
JOIN categories AS cat
    ON cat.category_id = p.category_id
ORDER BY o.order_id, ol.line_no;
~~~

The query reconstructs a display shape with **one result row per order line**. Having customer or product columns repeat in the **SELECT result** is normal; unlike the flat table, they are not duplicated as source-of-truth storage across rows.

### 6.4. Computing Order Totals Without Duplicate Storage

For this example computing only **quantity × locked unit price**, before discounts, taxes, or shipping fees:

~~~sql
SELECT
    o.order_id,
    COUNT(ol.line_no) AS line_count,
    COALESCE(
        SUM(ol.quantity::numeric * ol.unit_price_vnd_at_order),
        0
    ) AS merchandise_total_vnd
FROM orders AS o
LEFT JOIN order_lines AS ol
    ON ol.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Expected result:

| order_id | line_count | merchandise_total_vnd |
| --- | ---: | ---: |
| O1001 | 2 | 800000 |
| O1002 | 2 | 2790000 |
| O1003 | 1 | 630000 |

Using **COUNT(ol.line_no)** instead of **COUNT(*)** ensures an order with no line items gets **line_count = 0** under **LEFT JOIN**. Casting **quantity** to **numeric** before multiplication avoids relying on 32-bit/64-bit integer multiplication limits when totals grow very large.

### 6.5. Re-testing the Anomalies

**Updating a customer's current name in exactly one place:**

~~~sql
UPDATE customers
SET customer_name = 'An Nguyễn'
WHERE customer_id = 'C01';
~~~

Both O1001 and O1002 will show the updated current name when querying that customer. No per-order updates are needed.

**Updating a category name in exactly one place:**

~~~sql
UPDATE categories
SET category_name = 'Peripheral Devices'
WHERE category_id = 'CAT10';
~~~

All products in CAT10 now reference the updated current name.

**Creating an order with no line items yet:**

~~~sql
INSERT INTO orders
    (order_id, placed_on, customer_id, ship_to_address_at_order)
VALUES
    ('O1004', DATE '2026-11-22', 'C01',
     '12 Nguyen Hue, TP.HCM');
~~~

**Deleting a line item without deleting the order:**

~~~sql
DELETE FROM order_lines
WHERE order_id = 'O1003' AND line_no = 1;

SELECT order_id, placed_on, customer_id
FROM orders
WHERE order_id = 'O1003';
-- O1003 remains intact in the orders table.
~~~

These statements demonstrate independent operations; if executed sequentially on the sample data, totals and line counts after deletion update accordingly.

## 7. Step 6 — Migrating Legacy Data and Verifying Consistency

In real projects, the hardest part is usually not writing five **CREATE TABLE** statements, but migrating legacy data into the new tables **without losing line items, creating duplicate entities, or silently legitimizing conflicting records**.

A sound migration workflow:

1. **Lock down the business specification.** Confirm whether orders can have zero lines, how many phone numbers each customer has, whether products can repeat across lines, and which name/price columns are current vs. historical.
2. **Load raw data into staging.** Parse the item list at ingest; emit one row per item, standardize codes and types, and log malformed records.
3. **Validate keys.** In staging, every **(order_id, line_no)** must be unique with no missing key components.
4. **Validate functional dependencies.** Does one **customer_id** carry two different current names? Is one **product_id** assigned two current categories? Does one **order_id** have multiple order dates or customers?
5. **Resolve conflicting data before inserting.** Determine the authoritative value with the business or convert inconsistencies into properly effective-dated history; **never use SELECT DISTINCT to sweep conflicts under the rug**.
6. **Load parent tables before child tables.** Insert **customers, categories**, then **products, orders**, and finally **order_lines** inside an appropriate transaction.
7. **Reconcile row counts and tuple sets.** Compare row counts, key sets, and joined query results from the new model against staging.
8. **Cut over application write paths.** Stop writing to the flat table as a source of truth; switch to the new write path only after addressing transition plans, concurrency, and rollback.

### 7.1. Queries to Detect Conflicting Data in Staging

Once data has been flattened into rows in **order_lines_flat** as in section 2, run:

~~~sql
-- Does one order ID have multiple customers or order dates?
SELECT
    order_id,
    COUNT(DISTINCT customer_id) AS customer_count,
    COUNT(DISTINCT placed_on) AS placed_date_count
FROM order_lines_flat
GROUP BY order_id
HAVING COUNT(DISTINCT customer_id) > 1
    OR COUNT(DISTINCT placed_on) > 1;

-- Does one customer ID have multiple current names?
SELECT
    customer_id,
    COUNT(DISTINCT customer_name) AS name_count
FROM order_lines_flat
GROUP BY customer_id
HAVING COUNT(DISTINCT customer_name) > 1;

-- Does one product ID have multiple current names or categories?
SELECT
    product_id,
    COUNT(DISTINCT product_name) AS name_count,
    COUNT(DISTINCT category_id) AS category_count
FROM order_lines_flat
GROUP BY product_id
HAVING COUNT(DISTINCT product_name) > 1
    OR COUNT(DISTINCT category_id) > 1;

-- Does one category ID have multiple current names?
SELECT
    category_id,
    COUNT(DISTINCT category_name) AS category_name_count
FROM order_lines_flat
GROUP BY category_id
HAVING COUNT(DISTINCT category_name) > 1;
~~~

**These queries only detect conflicts that have already occurred.** Zero results **do not prove** a functional dependency holds in all future states; dependencies must be confirmed by the business specification and enforced by the schema/constraints. **COUNT(DISTINCT column)** also ignores NULLs in SQL, so if staging contains NULLs, check nullability and NULL consistency separately.

### 7.2. Example Migration from a Cleaned 1NF Table

Once the checks above are resolved and business dependencies hold, you can load empty target tables **instead of** the sample inserts in section 6.2 using:

~~~sql
BEGIN;

INSERT INTO customers
    (customer_id, customer_name, customer_phone)
SELECT DISTINCT
    customer_id, customer_name, customer_phone
FROM order_lines_flat;

INSERT INTO categories (category_id, category_name)
SELECT DISTINCT
    category_id, category_name
FROM order_lines_flat;

INSERT INTO products (product_id, product_name, category_id)
SELECT DISTINCT
    product_id, product_name, category_id
FROM order_lines_flat;

INSERT INTO orders
    (order_id, placed_on, customer_id, ship_to_address_at_order)
SELECT DISTINCT
    order_id, placed_on, customer_id, ship_to_address_at_order
FROM order_lines_flat;

INSERT INTO order_lines
    (order_id, line_no, product_id, quantity, unit_price_vnd_at_order)
SELECT
    order_id, line_no, product_id, quantity, unit_price_vnd_at_order
FROM order_lines_flat;

COMMIT;
~~~

**Prerequisite:** each customer, category, product, and order ID must already have a single chosen set of current attributes. If the same ID appears with multiple attribute versions, **SELECT DISTINCT** produces multiple rows with the same key and **INSERT** will fail—a signal that conflicts must be resolved first, never bypassed casually. You must also check formatting, missing values, and negative/invalid lines.

If the source system includes **orders with no lines yet**, a line-grain staging table **cannot recover those orders**. You must also ingest from the order header source or a separate event source; never assume all valid states appear in a flat line-level table.

### 7.3. Post-Load Verification

Compare row counts:

~~~sql
SELECT
    (SELECT COUNT(*) FROM order_lines_flat) AS old_line_count,
    (SELECT COUNT(*) FROM order_lines) AS new_line_count;
~~~

**Equal row counts are necessary but not sufficient**: two lines could accidentally swap products while keeping the total count unchanged. Compare tuple contents as well, especially **(order_id, line_no, product_id, quantity, unit_price_vnd_at_order)**:

~~~sql
-- Original lines no longer matching in the new schema.
SELECT
    order_id, line_no, product_id,
    quantity, unit_price_vnd_at_order
FROM order_lines_flat
EXCEPT
SELECT
    order_id, line_no, product_id,
    quantity, unit_price_vnd_at_order
FROM order_lines;

-- Lines in the new model missing from the original table.
SELECT
    order_id, line_no, product_id,
    quantity, unit_price_vnd_at_order
FROM order_lines
EXCEPT
SELECT
    order_id, line_no, product_id,
    quantity, unit_price_vnd_at_order
FROM order_lines_flat;
~~~

If both results are empty, the **compared line-item data** matches under set semantics. Continue reconciling order dates, customer IDs, addresses, and category info via join queries; for auditable financial systems, also verify totals, order counts, and historical figures. **EXCEPT** deduplicates under set semantics, so if staging lacks a unique key, verify multiplicity per tuple separately. Run these checks **before any new transactional writes** or against a consistent snapshot.

## 8. When Does "Repeated Data" Not Violate Normalization?

A common mistake during normalization is **splitting away every value that looks repeated** and accidentally destroying temporal meaning. Distinguish clearly:

| Data | Valid Dependency | How It Is Stored in the Example |
| --- | --- | --- |
| **Current** customer name | **customer_id → customer_name** | Once in **customers** |
| **Current** product name and category | **product_id → product_name, category_id** | Once in **products** |
| **Current** category name | **category_id → category_name** | Once in **categories** |
| **Locked-in** order shipping address | **order_id → ship_to_address_at_order** | In **orders** |
| **Locked-in** line item unit price | **(order_id, line_no) → unit_price_vnd_at_order** | In **order_lines** |

### 8.1. Unit Price at Purchase Time Differs from Current List Price

Product P10 can be sold on O1001 for **300000 VND** and on O1002 for **290000 VND**, due to purchase timing or promotions. If you add a **product_prices** table for current list prices, you must **not** retroactively overwrite the locked-in prices on those two order lines with the new list price.

If financial reports require prices, taxes, discounts, and currency at transaction time, those historical figures must have an **exact grain and meaning**. You may store **discount_vnd_at_order**, **tax_vnd_at_order**, or an adjustment detail table; these values must be determined by the line item, transaction, or version rule that owns them.

### 8.2. Order Shipping Address Is Not the Customer's Current Address

The same C01 can ship O1001 to one address and O1002 to another. If you only store **customers.current_address** and derive shipping addresses from it, historical shipping records break whenever the customer moves.

Keeping **ship_to_address_at_order** in **orders** is not an erroneous copy of a current attribute: it is a **fact belonging to the order**. For orders split across multiple destinations or packages, the address grain may change to **shipment_id** and require a dedicated **shipments** table.

### 8.3. Product Name at Purchase Time Can Be Its Own Historical Fact

In the basic example, reports display the current **products.product_name**. If invoices must preserve the item name exactly as shown at checkout, you can add **product_name_at_order** to the order line as a **historical snapshot**, alongside product_id referencing the product. Document clearly that this field does not automatically update when the current product name changes.

Never judge functional dependencies merely because two columns both contain the word **name** or happen to hold identical values today. Always ask **what point in time the attribute represents** and **whether changing the parent object ought to change this value**.

### 8.4. Totals and Derived Values

In the example, **merchandise_total_vnd** can be computed from line items. If you store an order total in the orders table for payment, reconciliation, or invoicing, the system must define rounding rules, taxes, shipping, discounts, and the lock-in moment. A derived value can be justified for business reasons, yet it demands a **consistent update mechanism**—3NF alone does not make derived fields safe.

## 9. Beyond 3NF: Additional Constraints and Physical Optimization

### 9.1. Are BCNF, 4NF, or 5NF Needed?

Under the assumed dependencies, the five final tables have clear keys and no remaining 3NF violations. Still, as the business expands, re-evaluate:

- **BCNF:** if a table has overlapping candidate keys, is there any non-trivial functional dependency whose left-hand side is not a superkey?
- **4NF:** if a product has multiple independent tags and sales channels, are you multiplying every combination in one table?
- **5NF:** if a **supplier–product–warehouse** triple is determined entirely by binary relationships, does a matching join dependency hold?

**Never split tables automatically** just to chase a higher normal form. Every decomposition must rest on valid dependencies and be checked for **lossless join** and constraint preservation.

### 9.2. Indexes Depend on Queries, Not as a Substitute for Normalization

Examples of common queries:

- List orders by **customer_id**, most recent first.
- View sales history for a **product_id**.
- Fetch all lines of an **order_id** ordered by **line_no**.

**PRIMARY KEY (order_id, line_no)** already supports fetching lines by order_id. You may consider:

~~~sql
CREATE INDEX idx_orders_customer_date
ON orders (customer_id, placed_on DESC);

CREATE INDEX idx_order_lines_product
ON order_lines (product_id);
~~~

These indexes are **suggestions**. Validate them against real data, read/write volume, and query plans. Adding indexes speeds up specific reads at the cost of extra write overhead and storage; adding an index cannot fix a broken functional dependency.

### 9.3. Relational Data, Documents, and Analytical Models

A relational design separating headers, lines, and catalogs works well when multiple workflows update customers, products, and orders independently and need referential integrity.

In a document DBMS, you might **embed order lines inside the order document** when orders are typically read/written as a whole and transaction isolation at the document boundary is desired. Even then, current customer/product data still needs an authoritative source or sync strategy, and cross-document invariants must be designed explicitly.

In an analytical warehouse, a line-item fact table combined with customer, product, and date dimensions may intentionally repeat keys or snapshots for historical reporting. There, design around fact grain, dimension versioning, and authoritative sources rather than mechanically copying OLTP tables.

## 10. Practice Exercises with Solutions

### Exercise 1. Identifying Normalization Steps

An input table has:

~~~text
order_id
order_date
buyer_id
buyer_name
items = [
  {sku, sku_name, quantity, paid_unit_price},
  ...
]
~~~

Rules: a buyer places multiple orders; each order has multiple numbered lines; SKU name is **current**; paid price is the **locked-in price of the line**, not necessarily equal to the list price.

**Tasks:** identify flaws in the initial storage form; propose a key for the line table; write the functional dependencies; normalize to 3NF and explain where **paid_unit_price** lives.

<details>
<summary>Suggested Solution for Exercise 1</summary>

If an SQL table stores the entire items list in one cell while the business needs to manage individual lines separately, extract the lines to achieve a clear grain and enforce per-element constraints.

~~~text
(order_id, line_no) -> sku, quantity, paid_unit_price
order_id            -> order_date, buyer_id
buyer_id            -> buyer_name
sku                 -> sku_name
~~~

From the flat 1NF lines table, extract **orders(order_id, order_date, buyer_id)** to eliminate partial dependencies on the composite key, keeping **order_lines(order_id, line_no, sku, quantity, paid_unit_price)**. Then extract **buyers(buyer_id, buyer_name)** and **skus(sku, sku_name)** so current data resides in its owning tables.

**paid_unit_price** stays in **order_lines**, because by business rules it belongs to the transaction line; do not assume **sku → paid_unit_price**.

</details>

### Exercise 2. Choosing a Key When Products Can Repeat

Order O2001 has two lines for the same SKU P10: line 1 at price 300000, line 2 at price 270000 due to a promotion.

**Questions:** is **(order_id, product_id)** still a candidate key of the line item table? If you add **order_line_id** as a surrogate key, should you still keep **UNIQUE(order_id, line_no)**?

<details>
<summary>Suggested Solution for Exercise 2</summary>

No. **(order_id, product_id)** appears twice and therefore does not uniquely identify a line. You can use **(order_id, line_no)** as the primary key.

If you use **order_line_id** as the primary key for easier referencing, you should still keep **UNIQUE(order_id, line_no)** if business rules dictate that **line_no** is unique within each order; at the same time, both **order_id** and **line_no** must be **NOT NULL** to properly protect the business key.

A surrogate key only changes how rows are identified; it does not eliminate partial or transitive dependencies on its own.

</details>

### Exercise 3. Verifying Data After Migration

The legacy table has 120 orders and 318 line items; some customers appear across multiple orders. The team has created the five normalized tables.

**State:** three minimum checks before shutting off the legacy write path; why **318 rows after migration** is not enough to prove accuracy; and how to detect a **product_id** assigned two different current names in staging.

**Approach:** check keys and FDs in legacy data; reconcile **(order_id,line_no)** key sets along with product, quantity, and price in both directions; reconcile order counts including orders with zero lines, addresses, and totals. Two datasets with identical row counts can still contain different records. Grouping by **product_id** and filtering **COUNT(DISTINCT product_name) > 1** catches existing conflicts; confirm the current catalog value with the authoritative business source.

## 11. Self-Assessment Checklist for an Order Schema

| Check Question | Sign of a Sound Design |
| --- | --- |
| What does one **orders** row describe? | One order with ID, order date, buyer, and order-level facts |
| What does one **order_lines** row describe? | One line within an order with key **(order_id,line_no)** or a surrogate key plus business uniqueness constraint |
| Is an item list still hidden inside a cell that needs per-item operations? | Every independently updatable line is explicitly modeled |
| Does a composite key have attributes depending on only part of it? | Header attributes are separated from line items |
| Where are current customer, product, and category names stored? | Single authoritative source in their respective owning tables |
| Is purchase price mistakenly pulled from current product price? | Historical price belongs to the transaction/line item |
| Does shipping address change when the customer profile changes? | Stores the exact locked-in address of the order |
| Can orders exist with no lines and products exist with no orders? | Parent tables exist independently; child tables use FKs |
| Do joins multiply rows or create spurious tuples? | Keys and dependencies protect join semantics |
| Was legacy imported data checked for conflicts and reconciled? | Includes error reports and checks on keys, FDs, counts, tuple sets, and totals |
| Are indexes grounded in actual query patterns? | Validated against workload and execution plans |

## 12. Key Takeaways

The step-by-step normalization process from an unnormalized order table is not a mechanical exercise of "splitting one table into many." **Step 1** defines grain and pulls independently managed lines out of list cells to reach 1NF relational form. **Step 2** writes candidate keys and functional dependencies, then separates **orders** from **order lines** to eliminate partial dependencies toward 2NF. **Step 3** separates **customers, products, and categories** along transitive dependencies toward 3NF.

The outcome should deliver **primary keys, foreign keys, domain constraints, lossless joins, and a verifiable data migration strategy**. At the same time, distinguish current data from historical data: **unit price at order time** and **locked-in shipping address** belong to the transaction and must not be "normalized away" into product or customer tables. Only once the business rules are sound should you evaluate BCNF, 4NF, 5NF, indexes, and read structures tailored to operational needs.
