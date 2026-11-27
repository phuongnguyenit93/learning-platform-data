# Translating Data Domains and Business Relationships into MySQL Tables

## Lesson Objectives

After this lesson, you will be able to:

- Distinguish entities, attributes, relationships, and business rules in a domain model.
- Identify appropriate tables, columns, primary keys, foreign keys, and constraints.
- Translate one-to-one, one-to-many, and many-to-many relationships into relational structures.
- Choose natural keys, surrogate keys, and composite keys based on data lifecycle.
- Normalize data to limit duplication, update anomalies, and accidental deletions.
- Use data types and constraints to enforce validity directly in MySQL.
- Validate the model using practical queries and real-world business scenarios.

Table design starts from how the business operates, not from picking column names. Before writing CREATE TABLE, you need to understand which objects the system manages, how each object is identified, how they relate to one another, and which rules must always hold true. When a domain model is translated into well-structured tables, queries become clearer, data has fewer contradictions, and business changes are easier to control.

This lesson uses an e-commerce sales system as a running example, though the process applies equally to student management, inventory, appointment booking, customer support, and other business systems.

## 1. Starting from the Business Domain

### 1.1. Finding Nouns, Verbs, and Rules

Read the business requirements and identify:

- **Nouns:** objects that need to be stored long-term, such as customer, product, order, payment, category.
- **Verbs:** actions and relationships, such as customer places order, order contains product, product belongs to category, order receives payment.
- **Rules:** conditions that must hold true, such as an order belongs to one customer, order quantity must be greater than 0, product SKU must not be duplicated, an order item must reference a product.

Example requirement:

> A customer can save multiple addresses. A customer can place multiple orders. Each order contains one or more line items. Each line item references a product and stores the quantity along with the unit price at the time of ordering. A product can belong to multiple categories; a category can contain multiple products. An order can be paid in multiple installments.

From the requirement above, we identify the entities and relationships:

| Business Component | Initial Representation |
|---|---|
| Customer | CUSTOMER |
| Customer's address | CUSTOMER_ADDRESS |
| Product | PRODUCT |
| Category | CATEGORY |
| Order | SALES_ORDER |
| Order line item | ORDER_ITEM |
| Payment | PAYMENT |
| Product - category relationship | PRODUCT_CATEGORY |

This is only the initial model. You still need to verify cardinality, optionality, identifiers, and lifecycle before finalizing the tables.

### 1.2. Entities and Value Objects

An **entity** has its own identity and persists over time. Two entities can have identical attributes and still be two distinct objects. For example, two customers with the same name are still two different customers.

A **value object** is identified by its values within a context and does not necessarily have an independent identity. For example, a shipping address captured at the time of placing an order can be a set of values consisting of recipient, street, district, city, and postal code.

An address can be modeled as a CUSTOMER_ADDRESS table if customers manage, edit, re-select, or label multiple addresses. Conversely, shipping information on an order usually needs to be a snapshot: if a customer edits their default address later, old invoices or order history must still preserve the address used when the order was placed.

Therefore, not every group of attributes needs to become a separate table. Create a separate table when a data group has an independent identity, lifecycle, relationships, or querying/management needs. You can keep a value object as columns in the same table when it only has meaning within the scope of its parent object.

### 1.3. Every Table Should Answer One Clear Question

A table should describe one consistent type of object or one consistent type of relationship. If a single table stores customers, orders, and a list of products using repeated columns, that table mixes multiple concepts and becomes difficult to maintain.

Describe each table in a single sentence:

- CUSTOMER stores the identity and basic contact information of a customer.
- PRODUCT stores current product information.
- SALES_ORDER stores an order placement and the status of that order.
- ORDER_ITEM stores each line item belonging to an order.
- PAYMENT stores a payment attempt or a payment record for an order.
- PRODUCT_CATEGORY links products with categories.

If it is hard to describe a table in one sentence, review whether the table contains multiple entities or multiple types of relationships.

## 2. Identifying Attributes and Data Types

After identifying entities, list their attributes and determine data types based on value domain, precision, and usage.

| Business Attribute | Common MySQL Type | Reason |
|---|---|---|
| Auto-incrementing numeric ID | BIGINT UNSIGNED | Large value range, suitable for surrogate keys |
| SKU or order number | VARCHAR(n) | Variable length, may contain letters and digits |
| Name, short description | VARCHAR(n) | Bounded string |
| Long content | TEXT | Long text |
| Quantity | INT or DECIMAL | Chosen based on whether items can be fractional |
| Monetary price | DECIMAL(p,s) | Avoids binary floating-point rounding errors of FLOAT/DOUBLE |
| Rate / percentage | DECIMAL(p,s) | Controls decimal precision |
| Birth date or business date | DATE | Only calendar date is needed |
| Order creation timestamp | DATETIME or TIMESTAMP | Chosen based on instant and timezone storage conventions |
| Active status | BOOLEAN/TINYINT or constrained string | Small value domain, requires clear convention |
| Optional note | TEXT NULL | Content may be absent |

Do not choose data types based solely on current sample values. For example, postal codes can start with 0, so they usually must be stored as strings. Phone numbers are not quantities for arithmetic either; storing them as VARCHAR preserves the plus sign, leading zeros, and international formatting.

### 2.1. Business Values and Snapshots

An order needs to retain the unit price at the time of ordering. If you only store `product_id` and always join to PRODUCT to fetch the current price, historical reports can change whenever a product's price is updated.

Therefore, ORDER_ITEM typically stores both `product_id` and `unit_price_at_order`. This is intentional snapshot data. The product name at the time of ordering can also be captured if documents must preserve the exact description sold.

Repeating a snapshot value is not the same as accidentally duplicating catalog data. A snapshot records a fact at a point in time; the current product data continues to be managed in PRODUCT.

## 3. Identifying Identifiers and Keys

### 3.1. Primary Key (PRIMARY KEY)

Every table needs a way to uniquely identify each row. A primary key:

- Has no duplicates.
- Does not accept NULL.
- Remains stable throughout the record's lifecycle.
- Is used for referencing from other tables.

For example, `customer_id` is the primary key of CUSTOMER. You should not use the customer's name as a primary key because names can duplicate and change.

### 3.2. Natural Keys and Surrogate Keys

A **natural key** is an attribute or set of attributes that has business meaning and can identify an object, such as an SKU, tax ID, or order number.

A **surrogate key** is an identifier generated primarily for linking data, such as `BIGINT AUTO_INCREMENT`.

A design often uses both:

- `product_id` is the stable PRIMARY KEY.
- `sku` has UNIQUE to ensure SKU codes do not duplicate.

If an SKU changes due to business rules, `product_id` remains unchanged so historical tables do not have to update their foreign keys. A surrogate key does not replace business constraints; if the SKU must be unique, UNIQUE is still required.

Not every table needs AUTO_INCREMENT. A pure junction table can use a composite primary key made of two foreign keys. Some domains have immutable and stable natural codes that can be used directly, though you must consider index size, mutability, and how external systems reference them.

### 3.3. Candidate Keys and Unique Alternate Keys

A table may have multiple attributes or attribute groups that qualify to uniquely identify a row. These are candidate keys. Pick one as the PRIMARY KEY; the remaining ones can be enforced with UNIQUE.

For example:

- `customer_id` is the PRIMARY KEY.
- `email` can be UNIQUE if the business requires each email to be tied to only one account.
- `external_customer_code` can be UNIQUE if issued by an integrated system with stable rules.

Only add UNIQUE after clearly defining the scope of uniqueness: system-wide, per tenant, per branch, or within a time range. A code unique within each tenant needs a composite unique key `(tenant_id, code)`, not a table-wide `UNIQUE(code)`.

### 3.4. Composite Keys

A composite key consists of multiple columns. For example, each order has multiple lines and `line_no` is only unique within that order:

~~~sql
PRIMARY KEY (order_id, line_no)
~~~

The pair `(order_id, line_no)` identifies a single line item. `line_no = 1` can appear across many different orders.

Composite keys fit junction tables or entities dependent on a parent. However, wide composite keys can enlarge indexes and foreign keys in other tables. If a table is widely referenced or needs a simple ID for APIs, you can use a surrogate key and add UNIQUE for the business pair.

## 4. Translating Relationship Types into Tables

Cardinality indicates how many objects each side can relate to. Optionality indicates whether the relationship is mandatory. Together, these two factors determine the placement of foreign keys, UNIQUE, and NULL.

### 4.1. One-to-Many Relationship (1:N)

For example, a customer can have many addresses, but each address belongs to exactly one customer.

Place the foreign key on the "many" side, meaning CUSTOMER_ADDRESS has `customer_id` referencing CUSTOMER.

~~~sql
CREATE TABLE customer (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    full_name VARCHAR(150) NOT NULL,
    email VARCHAR(254) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (customer_id),
    UNIQUE KEY uq_customer_email (email)
) ENGINE = InnoDB;

CREATE TABLE customer_address (
    address_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    recipient_name VARCHAR(150) NOT NULL,
    address_line VARCHAR(255) NOT NULL,
    city VARCHAR(100) NOT NULL,
    postal_code VARCHAR(20) NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (address_id),
    KEY idx_customer_address_customer (customer_id),
    CONSTRAINT fk_customer_address_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
) ENGINE = InnoDB;
~~~

A customer can have 0, 1, or many addresses. Each address must have a customer because `customer_id` is NOT NULL and has a foreign key.

`UNIQUE(email)` follows the column's collation. Before applying it, agree on whether email comparison is case-sensitive or case-insensitive and normalize inputs according to the same rule. The DDL example above intentionally lets the column inherit the schema collation; in a real system, choose a collation matching your identity policy and check for duplicate data before creating UNIQUE.

If `customer_id` allows NULL, the model permits an address that belongs to no customer. Only do this when the business genuinely has shared addresses or unowned addresses; do not use NULL to mask a mandatory relationship that has not been cleanly designed.

The `is_default` column only stores a flag on each address; it does not automatically guarantee that each customer has at most one default address. If that invariant is needed, you must design an additional uniqueness mechanism per `customer_id` (such as a generated column that holds a value only for the default row and then placing UNIQUE on it) or coordinate updates in a transaction with appropriate constraints. A row-level CHECK cannot inspect other rows.

### 4.2. One-to-One Relationship (1:1)

For example, each customer has at most one optional profile containing supplemental information. Use `customer_id` as both the PRIMARY KEY of the child table and its FOREIGN KEY:

~~~sql
CREATE TABLE customer_profile (
    customer_id BIGINT UNSIGNED NOT NULL,
    birth_date DATE NULL,
    preferred_language VARCHAR(20) NULL,
    profile_note TEXT NULL,
    PRIMARY KEY (customer_id),
    CONSTRAINT fk_customer_profile_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT
) ENGINE = InnoDB;
~~~

Because `customer_id` is the primary key, each customer has at most one profile. A customer may not yet have a row in CUSTOMER_PROFILE; the relationship is optional from the customer side. If a profile row exists, it must belong to exactly one customer.

If you use a separate `customer_id` column in the child table instead of making it the PRIMARY KEY, you need to place `UNIQUE(customer_id)` to limit each customer to at most one child row.

Note: a foreign key in the child table does not automatically guarantee that every customer must have a profile. If the business requires both sides to always exist in a strict one-to-one pair, control it at the transaction/application layer or reconsider merging the data into the same table. A one-sided FK constraint cannot enforce that every parent row must have a child row.

### 4.3. Many-to-Many Relationship (M:N)

A product can belong to multiple categories; a category can contain multiple products. Do not put a comma-separated list of `category_id` values inside PRODUCT. Create a junction table PRODUCT_CATEGORY:

~~~sql
CREATE TABLE product (
    product_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    sku VARCHAR(64) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    current_price DECIMAL(12, 2) NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (product_id),
    UNIQUE KEY uq_product_sku (sku),
    CONSTRAINT chk_product_current_price
        CHECK (current_price >= 0)
) ENGINE = InnoDB;

CREATE TABLE category (
    category_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    category_name VARCHAR(120) NOT NULL,
    slug VARCHAR(140) NOT NULL,
    PRIMARY KEY (category_id),
    UNIQUE KEY uq_category_slug (slug)
) ENGINE = InnoDB;

CREATE TABLE product_category (
    product_id BIGINT UNSIGNED NOT NULL,
    category_id BIGINT UNSIGNED NOT NULL,
    assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (product_id, category_id),
    KEY idx_product_category_category (category_id, product_id),
    CONSTRAINT fk_product_category_product
        FOREIGN KEY (product_id)
        REFERENCES product (product_id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT fk_product_category_category
        FOREIGN KEY (category_id)
        REFERENCES category (category_id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT
) ENGINE = InnoDB;
~~~

`PRIMARY KEY(product_id, category_id)` prevents the same product from being assigned to the same category multiple times. The reverse index `(category_id, product_id)` supports queries looking up products from a category.

If the relationship has its own attributes, place those attributes in the junction table. For example, `assigned_at` is the timestamp when the category was assigned. If you need to store who assigned it, sort priority, status, or effective period, those columns also belong in PRODUCT_CATEGORY.

### 4.4. Dependent Entities and Detail Tables

A line item has no independent meaning if it does not belong to an order. This is an example of a dependent entity. You can use a composite key `order_id + line_no`:

~~~sql
CREATE TABLE sales_order (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_no VARCHAR(40) NOT NULL,
    customer_id BIGINT UNSIGNED NOT NULL,
    ordered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    order_status VARCHAR(30) NOT NULL DEFAULT 'pending',
    PRIMARY KEY (order_id),
    UNIQUE KEY uq_sales_order_no (order_no),
    KEY idx_sales_order_customer_date (customer_id, ordered_at),
    CONSTRAINT fk_sales_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer (customer_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
) ENGINE = InnoDB;

CREATE TABLE order_item (
    order_id BIGINT UNSIGNED NOT NULL,
    line_no SMALLINT UNSIGNED NOT NULL,
    product_id BIGINT UNSIGNED NOT NULL,
    product_name_at_order VARCHAR(200) NOT NULL,
    quantity DECIMAL(12, 3) NOT NULL,
    unit_price_at_order DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    KEY idx_order_item_product (product_id),
    CONSTRAINT chk_order_item_line_no
        CHECK (line_no > 0),
    CONSTRAINT chk_order_item_quantity
        CHECK (quantity > 0),
    CONSTRAINT chk_order_item_unit_price
        CHECK (unit_price_at_order >= 0),
    CONSTRAINT fk_order_item_order
        FOREIGN KEY (order_id)
        REFERENCES sales_order (order_id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT fk_order_item_product
        FOREIGN KEY (product_id)
        REFERENCES product (product_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
) ENGINE = InnoDB;
~~~

An order can have many lines; each line has its own sequence number within the order. `order_id` is an FK to SALES_ORDER. `product_id` is an FK to PRODUCT. `product_name_at_order` and `unit_price_at_order` are snapshots to preserve what was sold even if the current product name or price changes.

In this example, deleting an order deletes its detail lines via `ON DELETE CASCADE`. Deleting a product referenced by an order item is rejected by `RESTRICT` to preserve history. In many systems, products are discontinued via `is_active = FALSE` rather than physical deletion.

## 5. Constraints Protect Business Rules

A constraint is a rule checked by the database when writing data. You should not rely solely on the UI or service layer to ensure data validity, because data can be written from multiple applications, batch jobs, scripts, or admin tools.

### 5.1. NOT NULL

Use NOT NULL when an attribute is mandatory.

For example, `order_item.product_id` must exist and `quantity` must have a value. If `quantity` is NULL, total price calculations and reports can produce unexpected results.

Do not make every column NOT NULL out of habit. A NULL column should represent a clear state of "unknown", "not yet available", or "not applicable". Distinguish NULL from an empty string or the number 0.

### 5.2. PRIMARY KEY and UNIQUE

PRIMARY KEY identifies a row; UNIQUE ensures no two rows duplicate according to the comparison rules of the columns in the key.

For example, SKU must be unique:

~~~sql
ALTER TABLE product
    ADD UNIQUE KEY uq_product_sku (sku);
~~~

Before adding UNIQUE to a table with existing data, search for duplicate groups under the target collation and resolve them first. Nullable columns in UNIQUE can contain multiple NULL rows; if the business requires every row to have a unique code, combine UNIQUE with NOT NULL.

### 5.3. FOREIGN KEY

A foreign key ensures values in a child table reference a valid row in a parent table. For example, `order_item.order_id` must exist in `sales_order`.

When designing an FK:

- Both columns must have compatible data types; for numeric types, pay attention to signed/unsigned and size.
- For string columns, pay attention to compatible character sets and collations.
- Related tables should use InnoDB for transactions and referential integrity.
- The referenced column needs an appropriate index, typically PRIMARY KEY or UNIQUE.
- The referencing column needs an index; InnoDB can automatically create an index if a suitable one does not exist, though you should verify and design indexes for actual queries.

Do not treat an FK as mere documentation on a diagram. An FK is an enforced database constraint that prevents orphan data.

### 5.4. ON DELETE and ON UPDATE

Common referential actions:

| Action | Meaning | When to Consider |
|---|---|---|
| RESTRICT | Reject deleting/updating the parent key if referencing child rows still exist | Protecting historical data |
| NO ACTION | In InnoDB, behaves equivalently to RESTRICT at check time | Usually no need to choose separately |
| CASCADE | Delete or update child rows along with the parent row | Junction tables or details with a clearly dependent lifecycle |
| SET NULL | Set the child FK to NULL when the parent row is deleted/updated | Only when the FK column is nullable and the relationship can be detached |

For example, deleting a product can delete its PRODUCT_CATEGORY link rows because that is a dependent relationship. However, you should not delete a product that already appears in ORDER_ITEM if transaction history must be kept. Using RESTRICT and a discontinued status is usually safer.

Do not choose CASCADE out of habit. A single parent delete can propagate across multiple levels and wipe out large amounts of data. Trace the cascade path, estimate the blast radius, and test on representative data.

### 5.5. CHECK

CHECK expresses a condition that must hold true for every row:

~~~sql
quantity DECIMAL(12, 3) NOT NULL,
CONSTRAINT chk_quantity_positive CHECK (quantity > 0)
~~~

MySQL enforces CHECK starting from version 8.0.16 and above. If a system uses an older version, do not assume the constraint is enforced; check the version and use alternative safeguards. CHECK does not replace rules that must validate across multiple rows or multiple tables, such as the sum of line items equaling the order total.

### 5.6. DEFAULT

DEFAULT provides a value when an INSERT statement omits that column. For example, `order_status` defaults to `pending` or `created_at` defaults to `CURRENT_TIMESTAMP`.

DEFAULT does not mean every explicitly sent NULL value automatically converts into the default value. If a column allows NULL and the application passes NULL, MySQL stores NULL. Distinguish "omitting a value" from "passing NULL".

## 6. Normalization to Reduce Duplicate Data

Normalization organizes data so each fact is stored in its proper place, reducing update anomalies and maintaining consistency.

### 6.1. First Normal Form (1NF)

Each cell should hold a single value from the column's domain, rather than stuffing a multi-value list into one cell.

Unsuitable design:

| order_id | product_ids |
|---:|---|
| 1001 | 12,18,25 |

Relational design:

| order_id | line_no | product_id |
|---:|---:|---:|
| 1001 | 1 | 12 |
| 1001 | 2 | 18 |
| 1001 | 3 | 25 |

The second structure can join to PRODUCT, enforce FKs, be indexed, and query individual products. A comma-separated string cannot enforce an FK per element and makes preventing duplicates difficult.

### 6.2. Second Normal Form (2NF)

For a table with a composite primary key, non-key attributes must depend on the entire key, not just part of the key.

Suppose ORDER_ITEM has the key `(order_id, line_no)`. `quantity` depends on the specific line item in the order. However, `order_date` only depends on `order_id`, not `line_no`. Putting `order_date` in every line item duplicates order data; `order_date` should be stored in SALES_ORDER.

### 6.3. Third Normal Form (3NF)

Non-key attributes should depend on the key, not transitively through another non-key attribute.

For example, if PRODUCT stores `category_id` and `category_name`, `category_name` actually depends on `category_id`. When a category name changes, many products must be updated. Extracting CATEGORY and keeping `category_id` in the linking table gives category data a single source of truth.

### 6.4. Avoid Over-Normalization

Normalization does not mean every column must be split into a separate table. If a shipping address is an immutable snapshot of an order, storing the snapshot fields alongside the order can be more appropriate than joining to the customer's current address.

Some aggregated values such as `order_total` may be stored to optimize reporting or serve as a document snapshot, but you must define the source of truth and how to keep it synchronized with line items, discounts, taxes, and fees. Do not store a derived value without clear update rules.

The goal is a model that accurately reflects the business, ensures consistency, and supports required queries. Read optimization may require intentional denormalization, but it must be measured and its synchronization managed.

## 7. Assembling the Sales Model into a Complete Schema

High-level relationship diagram:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ CUSTOMER_ADDRESS : has
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : referenced_by
    PRODUCT ||--o{ PRODUCT_CATEGORY : assigned
    CATEGORY ||--o{ PRODUCT_CATEGORY : groups
    SALES_ORDER ||--o{ PAYMENT : receives
~~~

Relationships in the diagram:

- CUSTOMER can have multiple addresses and multiple orders.
- SALES_ORDER has at least one ORDER_ITEM by business rule; an FK alone does not automatically enforce at least one line item.
- Each ORDER_ITEM belongs to exactly one order and references one product.
- PRODUCT and CATEGORY have a many-to-many relationship via PRODUCT_CATEGORY.
- An order can have multiple payments, such as a deposit and a remaining balance payment.

Illustrative PAYMENT table:

~~~sql
CREATE TABLE payment (
    payment_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    payment_ref VARCHAR(80) NOT NULL,
    amount DECIMAL(12, 2) NOT NULL,
    payment_status VARCHAR(24) NOT NULL DEFAULT 'pending',
    paid_at DATETIME NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (payment_id),
    UNIQUE KEY uq_payment_ref (payment_ref),
    KEY idx_payment_order_created (order_id, created_at),
    CONSTRAINT chk_payment_amount CHECK (amount > 0),
    CONSTRAINT fk_payment_order
        FOREIGN KEY (order_id)
        REFERENCES sales_order (order_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
) ENGINE = InnoDB;
~~~

If each order may only have a single payment record, you can add `UNIQUE(order_id)`. However, if you support multiple installments, refunds, or multiple payment methods, model monetary transactions according to specific rules; do not force 1:1 when the business is 1:N.

The PAYMENT DDL above illustrates incoming receipts with a positive `amount`. If you need to store refunds, explicitly model the event type and money direction (or use a separate REFUND table referencing the original payment); do not silently insert a negative `amount` into a table with `CHECK(amount > 0)`.

## 8. Queries to Validate the Model

### 8.1. Fetching an Order with Its Customer

~~~sql
SELECT
    o.order_id,
    o.order_no,
    o.ordered_at,
    o.order_status,
    c.customer_id,
    c.full_name,
    c.email
FROM sales_order AS o
JOIN customer AS c
  ON c.customer_id = o.customer_id
WHERE o.order_id = 1001;
~~~

INNER JOIN returns the order with its matching customer. The FK ensures there are no orphan `sales_order` rows when constraints are enabled and data is written through MySQL.

### 8.2. Fetching Line Items of an Order

~~~sql
SELECT
    oi.order_id,
    oi.line_no,
    oi.product_id,
    oi.product_name_at_order,
    oi.quantity,
    oi.unit_price_at_order,
    oi.quantity * oi.unit_price_at_order AS line_amount
FROM order_item AS oi
WHERE oi.order_id = 1001
ORDER BY oi.line_no;
~~~

Use the snapshot price in ORDER_ITEM to recalculate the value at the time of ordering. If you join PRODUCT to read `current_price`, the result may differ from the historical price.

### 8.3. Finding Products by Category

~~~sql
SELECT
    p.product_id,
    p.sku,
    p.product_name
FROM product AS p
JOIN product_category AS pc
  ON pc.product_id = p.product_id
WHERE pc.category_id = 5
  AND p.is_active = TRUE;
~~~

An index starting with `category_id` supports querying products from a category. If you frequently query categories starting from `product_id`, the primary key `(product_id, category_id)` already supports that direction.

### 8.4. Finding Records Without Relationships

For example, customers who have not placed any orders:

~~~sql
SELECT
    c.customer_id,
    c.full_name
FROM customer AS c
LEFT JOIN sales_order AS o
  ON o.customer_id = c.customer_id
WHERE o.order_id IS NULL;
~~~

This anti-join query pattern is useful for auditing data and business logic. You can also use `NOT EXISTS`. An index on `sales_order.customer_id` speeds up relationship lookups.

## 9. Indexes Must Serve Queries and Relationships

Primary keys and unique keys create corresponding indexes. Foreign keys generally need an index on the child table side; InnoDB can automatically create an appropriate index if none exists. Beyond constraint-backing indexes, design indexes based on actual queries.

For example:

- CUSTOMER: lookup by email -> `UNIQUE(email)`.
- SALES_ORDER: list a customer's orders chronologically -> `INDEX(customer_id, ordered_at)`.
- ORDER_ITEM: fetch lines of an order -> `PRIMARY KEY(order_id, line_no)`.
- ORDER_ITEM: find orders containing a product -> `INDEX(product_id)`.
- PRODUCT_CATEGORY: find categories of a product -> `PRIMARY KEY(product_id, category_id)`.
- PRODUCT_CATEGORY: find products in a category -> `INDEX(category_id, product_id)`.
- PAYMENT: list payments of an order chronologically -> `INDEX(order_id, created_at)`.

Column order in a composite index matters greatly. An index `(customer_id, ordered_at)` supports queries filtering by `customer_id` and can support sorting by `ordered_at` within that customer's scope. It is not equivalent to an index on `ordered_at` alone for all queries.

Do not add an index to every column. Indexes consume storage space and increase the cost of INSERT, UPDATE, and DELETE operations. Use EXPLAIN, query statistics, and real workloads to identify needed indexes.

## 10. Design Workflow from Requirements to DDL

You can repeat the following process for every feature:

1. **Write out business rules:** what objects exist, who owns them, what is mandatory, what may repeat.
2. **List entities:** distinguish entities, value objects, lookup lists, and relationships.
3. **Define attributes:** value domains, lengths, precision, mandatory or optional.
4. **Define identifiers:** primary keys, natural keys, candidate keys, and UNIQUE scopes.
5. **Map cardinality and optionality:** 1:1, 1:N, M:N; whether the relationship is mandatory on each side.
6. **Translate relationships:** FK on the many side; junction table for M:N; UNIQUE on the child side of 1:1.
7. **Normalize:** eliminate repeating groups, partial dependencies, and transitive dependencies.
8. **Add constraints:** NOT NULL, PK, UNIQUE, FK, CHECK, and DEFAULT.
9. **Design indexes for queries:** filtering, joining, sorting, and pagination.
10. **Test boundary data:** NULLs, duplicates, parent deletion, key updates, zero/negative quantities, long strings, and failed transactions.
11. **Review migrations:** evaluate existing data, metadata locks, DDL duration, and application compatibility.

## 11. Common Modeling Mistakes

| Mistake | Resulting Problem | Remediation |
|---|---|---|
| Storing multiple IDs in a CSV column | No FK per element, hard to join and filter | Use a junction table |
| Using a name as PRIMARY KEY | Duplicate or changed names break references | Use a stable key and UNIQUE for business codes |
| Repeating customer info in every order | Divergent updates and redundancy | Reference `customer_id`; keep snapshots only when history is needed |
| Storing current price instead of price at sale time | Order history changes when product price changes | Store `unit_price_at_order` |
| Using CASCADE on every FK | Deleting one row can cascade-delete historical data | Choose actions based on lifecycle and retention requirements |
| Using NULL to represent multiple unclear states | Hard to understand and validate business rules | Define NULL meaning clearly, split out status if needed |
| Omitting UNIQUE on business codes | Duplicate data despite having a primary key | Add candidate key / unique constraint |
| Checking relationships only in application code | Scripts or other services can create orphan data | Enforce FKs at the database level |
| Splitting every attribute into its own table | Complex JOINs and hard-to-follow model | Split only when there is an independent lifecycle/relationship/management need |
| Using a single EAV table for all attribute types | Loses strong data types and clear constraints | Use typed columns or an intentional extension model |

## 12. Hands-on Exercises

### Exercise 1: Requirement Analysis

Design an appointment booking system consisting of patients, doctors, specialties, appointments, and clinics. List entities, attributes, rules, and cardinalities. Determine whether a patient can have multiple appointments and whether an appointment can have multiple doctors.

### Exercise 2: M:N Relationship Modeling

Design a course system: a student enrolls in multiple courses, and a course has multiple students. Create STUDENT, COURSE, and ENROLLMENT tables. Define a composite key or a surrogate key with UNIQUE; add `enrollment_date` and `enrollment_status`.

### Exercise 3: Testing 1:1 and Optionality

Create CUSTOMER_PROFILE using `customer_id` as PK/FK. Try inserting two profiles for the same customer and observe the constraint. Try deleting a customer who has a profile to test the FK action.

### Exercise 4: Testing Constraints

Create ORDER_ITEM with `CHECK (quantity > 0)` and NOT NULL. Try inserting quantity as 0, a negative number, and NULL. Verify the MySQL version enforcing CHECK.

### Exercise 5: Detecting Denormalized Data

Create an order table with a `product_ids` column holding a comma-separated string. Write the queries needed to find products, then refactor to ORDER_ITEM and compare query complexity and FK capability.

### Exercise 6: Designing Snapshots

Create a product with `current_price = 100.000`, place an order with `unit_price_at_order = 100.000`, then change `current_price` to `120.000`. Write a query proving the order history still preserves the price `100.000`.

### Exercise 7: Schema Review

Pick a feature in a personal project. Write a one-sentence description for each table, draw the relationships, list PK/FK/UNIQUE/CHECK constraints, and explain why each index exists. Ask someone else to propose invalid data cases to test your model.

## Conclusion

Translating a business domain into MySQL tables is the process of defining entities, attributes, identifiers, relationships, and rules that must always hold true. Primary keys identify rows; foreign keys protect relationships; UNIQUE and CHECK preserve invariants; normalization reduces duplicate data; indexes serve queries.

A good schema must reflect the true data lifecycle. Distinguish current data from historical snapshots, clearly define whether relationships are mandatory or optional, and choose delete/update actions according to business rules. When a model is designed from requirements and verified with queries and edge-case data, MySQL can protect consistency right where the data is stored.
