# One-to-One, One-to-Many, and Many-to-Many Relationships in PostgreSQL

When designing a relational schema, choosing data types for individual columns is only the first step. The next crucial step is determining **how entities relate to one another**: how many orders can a customer have, how many products can an order contain, or does each customer have at most one extended profile?

In PostgreSQL, the three most common relationship types are:

- **One-to-one (1:1):** each record on side A corresponds to at most one record on side B, and vice versa.
- **One-to-many (1:N):** one record A can relate to many records B, while each B relates to at most one or exactly one A according to the data rules.
- **Many-to-many (N:M):** one A can relate to many B, and one B can also relate to many A. In a relational schema, this is typically represented using a **junction table**.

Relationships are implemented primarily through **primary keys (`PRIMARY KEY`), foreign keys (`FOREIGN KEY`), unique constraints (`UNIQUE`), and `NULL` allowability**. Designing these constraints properly lets PostgreSQL safeguard data integrity even when multiple applications or concurrent transactions write at the same time.

This lesson builds a small e-commerce example with `customers`, `customer_profiles`, `orders`, `products`, and `order_items`, then uses SQL to demonstrate how to query, verify, and maintain each relationship type.

## 1. Cardinality and Optionality: Two Questions to Separate

**Cardinality** describes the maximum number of records an entity can relate to: one or many. **Optionality** describes whether an association is mandatory or optional: a minimum of zero or one.

For example, the statement "A customer has a profile" is ambiguous:

- **Must every customer have exactly one profile**, or can a customer exist without having created one yet?
- **Must every profile belong to a customer**, or can it be saved as a draft unattached to any customer?
- Does the system allow storing multiple profile versions?

Depending on the answers, the table structure and constraints will differ.

### Common Multiplicity Notations

| Notation | Meaning | Example |
| --- | --- | --- |
| `0..1` | Zero or one | A customer may not have an extended profile yet |
| `1..1` | Exactly one | Every order must belong to one customer |
| `0..N` | Zero or many | A new customer has no orders yet |
| `1..N` | At least one, possibly many | A completed order must have at least one line item, if required by the business |

**1:N does not mean every A must always have at least one B.** A `NOT NULL` foreign key column on table B guarantees that every B must reference a valid A; it does not by itself force every A to have a B.

### Overview Diagram for the Lab

~~~mermaid
erDiagram
    CUSTOMERS ||--o| CUSTOMER_PROFILES : "has zero or one"
    CUSTOMERS ||--o{ ORDERS : "places"
    ORDERS ||--o{ ORDER_ITEMS : "contains"
    PRODUCTS ||--o{ ORDER_ITEMS : "appears in"
    CUSTOMERS {
        bigint customer_id PK
        text email UK
        text full_name
    }
    CUSTOMER_PROFILES {
        bigint customer_id PK, FK
        text bio
    }
    ORDERS {
        bigint order_id PK
        bigint customer_id FK
    }
    PRODUCTS {
        bigint product_id PK
        text product_name
    }
    ORDER_ITEMS {
        bigint order_id PK, FK
        bigint product_id PK, FK
        integer quantity
    }
~~~

In the diagram, the **orders–products** relationship is N:M conceptually, but at the storage level it is decomposed into two 1:N relationships from `orders` and `products` to `order_items`.

## 2. What Problems Do Primary Keys and Foreign Keys Solve?

### PRIMARY KEY: Uniquely Identifying a Record

~~~sql
CREATE TABLE example_customers (
    customer_id bigint PRIMARY KEY,
    email text NOT NULL
);
~~~

`PRIMARY KEY` guarantees that every row has a non-`NULL`, non-duplicate key value. PostgreSQL creates a matching **unique B-tree index** to enforce the primary key constraint.

A primary key can be a single column or a combination of multiple columns:

~~~sql
CREATE TABLE example_pairs (
    left_id bigint NOT NULL,
    right_id bigint NOT NULL,
    PRIMARY KEY (left_id, right_id)
);
~~~

With a composite primary key, the pair of values must be unique; each individual column may still repeat.

### FOREIGN KEY: Ensuring the Target Reference Exists

~~~sql
CREATE TABLE example_orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES example_customers(customer_id)
);
~~~

The foreign key ensures that an order's `customer_id` points to an existing customer (unless the column allows `NULL` and uses appropriate `NULL` semantics).

There are two independent constraints here:

1. `FOREIGN KEY`: whenever a referencing value is present, it must match a valid value in the parent table.
2. `NOT NULL`: the column cannot be left empty, meaning every order must be tied to a customer.

**A foreign key alone does not limit how many orders a customer can have.** Multiple rows in `example_orders` can share the same `customer_id`; that is the foundation of a 1:N relationship.

### UNIQUE: Limiting Records on the Referencing Side

If a foreign key column is also declared `UNIQUE`, multiple child rows cannot reference the same non-null parent value. This is one way to implement 1:1.

In PostgreSQL, a foreign key must reference a primary key or a suitable unique key/column on the referenced table. You cannot arbitrarily reference a column with duplicate values and expect the database to determine the parent row.

## 3. 1:1 Relationship: Each Customer Has at Most One Profile

Suppose `customers` holds core account data, while `customer_profiles` holds extended profile details:

~~~text
customers
---------
customer_id (PK)
email
full_name

customer_profiles
-----------------
customer_id (PK, FK -> customers.customer_id)
bio
birthday
~~~

This option is called a **shared primary key**: the profile record's primary key is simultaneously a foreign key to the customer.

### SQL to Create 1:1 Tables

~~~sql
CREATE TABLE customers (
    customer_id bigint PRIMARY KEY,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL
);

CREATE TABLE customer_profiles (
    customer_id bigint PRIMARY KEY
        REFERENCES customers(customer_id)
        ON DELETE CASCADE,
    birthday date,
    bio text
);
~~~

Guarantees enforced by PostgreSQL:

- Two profiles cannot have the same `customer_id` because the column is `PRIMARY KEY`.
- A profile cannot point to a non-existent customer because of `FOREIGN KEY`.
- A valid profile always has a non-`NULL` `customer_id` because the column is the primary key.
- A customer **may not have a profile yet**, because no constraint forces every `customers` row to appear in `customer_profiles`.

Thus this is a **customers 0..1 profiles** relationship, while each profile attaches to **exactly one customer**.

### Why Use a Shared Primary Key?

Advantages:

1. No extra `profile_id` column is needed just to identify an entity whose lifecycle is tied directly to the customer.
2. The shared key clearly expresses "one profile per customer".
3. `JOIN` queries are simple, with no extra unique constraint required.
4. If deleting a customer is permitted by policy, `ON DELETE CASCADE` can automatically delete the dependent profile.

Limitation: if a customer later needs **multiple historical profiles**, a 1:1 relationship no longer fits; you will need versioning or a 1:N relationship.

### Alternative: Separate Primary Key + UNIQUE Foreign Key

Another valid option is:

~~~sql
CREATE TABLE customer_profiles_v2 (
    profile_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL UNIQUE
        REFERENCES customers(customer_id),
    bio text
);
~~~

`profile_id` identifies the profile, while `UNIQUE(customer_id)` ensures at most one profile per customer. This suits cases where a profile needs an independent ID referenced elsewhere.

Do not write only:

~~~sql
customer_id bigint REFERENCES customers(customer_id)
~~~

and call it 1:1. Without `UNIQUE` or a shared primary key, multiple profile rows can point to the same customer, making the actual relationship 1:N.

### Is Every Customer Forced to Have a Profile?

Not yet. Making `customer_profiles.customer_id` a `PRIMARY KEY`/`FOREIGN KEY` only guarantees that **any existing profile has a valid customer**. It does not force inserting a profile whenever a customer is inserted.

If the requirement truly is **every customer must always have exactly one profile**, an additional design mechanism is needed, such as:

- Merging attributes into the same table if they share the same lifecycle and always exist together.
- Creating the customer and profile inside one business transaction, alongside safeguards against other write paths breaking the invariant.
- Designing deferred constraints/circular dependencies or suitable triggers when splitting tables is mandatory, with a thorough understanding of constraint check timing.

**A one-way foreign key does not by itself express "every customer must have a profile".**

## 4. 1:N Relationship: A Customer Has Many Orders

In the order model:

~~~text
customers (1) ---- (0..N) orders
~~~

Each order belongs to **exactly one** customer, whereas a customer can have 0, 1, or many orders.

~~~sql
CREATE TABLE orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES customers(customer_id)
        ON DELETE RESTRICT,
    ordered_at timestamptz NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled'))
);
~~~

The key design principle is that **the foreign key sits on the many side**: `orders.customer_id`. Placing a list of `order_id`s inside a column on `customers` makes existence checks and relationship queries much harder.

### Reading the Constraints

| Constraint | What Is Protected |
| --- | --- |
| `orders.order_id PRIMARY KEY` | No two orders share the same ID |
| `orders.customer_id REFERENCES customers` | Cannot attach an order to a non-existent customer |
| `orders.customer_id NOT NULL` | No order can exist without a customer |
| **No UNIQUE on orders.customer_id** | Multiple orders are allowed to belong to the same customer |
| `ON DELETE RESTRICT` | Cannot delete a customer still referenced by orders |

`ON DELETE RESTRICT` in this example reflects the principle of **not deleting a customer while transactional orders must be retained**. Systems with invoice/accounting retention rules may require stricter immutability and long-term archival policies.

### When a 1:N Relationship Is Optional on the Child Side

Sometimes a ticket has not yet been assigned to an owner:

~~~sql
assignee_id bigint NULL REFERENCES employees(employee_id)
~~~

Here a task row may **have no assigned employee**. This is still a one-to-many relationship from employees to tasks, except each task links to **0 or 1** employee rather than exactly 1.

Deciding between `NULL` and `NOT NULL` must be based on business rules, not merely on the phrase "one-to-many".

### Does PostgreSQL Automatically Index Foreign Keys?

PostgreSQL creates indexes backing `PRIMARY KEY` and `UNIQUE` constraints on the referenced side. However, it **does not automatically create indexes on foreign key columns in child tables**.

For `orders.customer_id`, it is often worth considering:

~~~sql
CREATE INDEX idx_orders_customer_id
ON orders(customer_id);
~~~

The index can speed up "fetch orders for customer X" queries as well as foreign key checks when updating/deleting parent rows. The final decision still depends on row count, query predicates, write frequency, and execution plans.

## 5. N:M Relationship: Orders Contain Many Products, Products Appear in Many Orders

At the business level:

~~~text
orders (0..N) <----> (0..N) products
~~~

An order can contain multiple products; a product can appear across many different orders. Relational schemas typically do not store N:M relationships as a list-of-IDs column, but instead create a **junction table**:

~~~text
orders (1) --- (0..N) order_items (0..N) --- (1) products
~~~

Each row in `order_items` links **one order** with **one product**. Together, these rows form the many-to-many relationship.

### SQL for Designing the Junction Table

~~~sql
CREATE TABLE products (
    product_id bigint PRIMARY KEY,
    product_name text NOT NULL,
    current_price numeric(12,2) NOT NULL CHECK (current_price >= 0)
);

CREATE TABLE order_items (
    order_id bigint NOT NULL
        REFERENCES orders(order_id)
        ON DELETE CASCADE,
    product_id bigint NOT NULL
        REFERENCES products(product_id)
        ON DELETE RESTRICT,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price_at_order numeric(12,2) NOT NULL
        CHECK (unit_price_at_order >= 0),
    PRIMARY KEY (order_id, product_id)
);
~~~

`order_items` contains:

- `order_id`: foreign key to the order.
- `product_id`: foreign key to the product.
- `quantity`: quantity of the product in the order.
- `unit_price_at_order`: **price at the time of purchase**, preventing historical orders from recalculating against current catalog prices.
- `PRIMARY KEY(order_id, product_id)`: a product has at most one consolidated line per order.

Example rows:

| order_id | product_id | quantity | Meaning |
| ---: | ---: | ---: | --- |
| 1001 | 501 | 2 | Order 1001 buys two units of product 501 |
| 1001 | 502 | 1 | Order 1001 buys one unit of product 502 |
| 1002 | 503 | 3 | Order 1002 buys three units of product 503 |
| 1003 | 501 | 1 | Product 501 also appears in order 1003 |

Thus **one order contains many products**, and simultaneously **one product belongs to many orders**, while every link record remains guarded by two foreign keys.

### When Should the ID Pair Not Be the PRIMARY KEY?

If the business allows the same product to appear multiple times in one order—for example, lines with different discount tiers, lot batches, or configurations—`PRIMARY KEY(order_id, product_id)` is too restrictive.

In that case, you can use:

~~~sql
CREATE TABLE order_item_lines (
    order_item_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_id bigint NOT NULL REFERENCES orders(order_id),
    product_id bigint NOT NULL REFERENCES products(product_id),
    line_number integer NOT NULL CHECK (line_number > 0),
    quantity integer NOT NULL CHECK (quantity > 0),
    UNIQUE (order_id, line_number)
);
~~~

This design allows two distinct rows with the same `product_id` within one `order_id`, while keeping line numbers unique per order. Choose constraints based on the **actual business unit**, rather than forcing a composite key just because it is the textbook pattern.

### Should You Use a product_id Array Instead of a Junction Table?

A column such as `orders.product_ids bigint[]` or a string `'501,502,503'` can store a list, yet it is not equivalent to an N:M table with foreign keys and relational data:

- Standard foreign keys cannot easily guarantee that **every element** in the array references an existing product.
- There is no natural place for link attributes such as quantity and purchase price.
- It is difficult to enforce `UNIQUE(order_id, product_id)`, prevent duplicates, or cascade per link.
- Joins, aggregations, and element-level updates become much more complex.

PostgreSQL supports arrays and JSONB for suitable use cases, but for entity relationships requiring referential integrity, a **junction table** is usually the clearer choice.

## 6. Complete Practice SQL Set in a Dedicated Schema

This section combines all three relationships into a runnable example in a lab database. Create a dedicated development database, such as `relationship_lab`, and connect with a role permitted to create schemas. **Run the reset statement only when you are sure the `relation_lab` schema belongs to this exercise and holds no data you need to keep.**

### Step 1: Recreate the Schema and Tables

~~~sql
-- RUN ONLY IN a practice database.
DROP SCHEMA IF EXISTS relation_lab CASCADE;
CREATE SCHEMA relation_lab;

-- Root table: customers.
CREATE TABLE relation_lab.customers (
    customer_id bigint PRIMARY KEY,
    email text NOT NULL UNIQUE,
    full_name text NOT NULL
);

-- Optional 1:1: each customer has at most one profile.
CREATE TABLE relation_lab.customer_profiles (
    customer_id bigint PRIMARY KEY
        REFERENCES relation_lab.customers(customer_id)
        ON DELETE CASCADE,
    birthday date,
    bio text
);

-- 1:N: every order must belong to one customer.
CREATE TABLE relation_lab.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES relation_lab.customers(customer_id)
        ON DELETE RESTRICT,
    ordered_at timestamptz NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled'))
);

-- Product catalog.
CREATE TABLE relation_lab.products (
    product_id bigint PRIMARY KEY,
    product_name text NOT NULL,
    current_price numeric(12,2) NOT NULL
        CHECK (current_price >= 0)
);

-- N:M orders - products via junction table.
CREATE TABLE relation_lab.order_items (
    order_id bigint NOT NULL
        REFERENCES relation_lab.orders(order_id)
        ON DELETE CASCADE,
    product_id bigint NOT NULL
        REFERENCES relation_lab.products(product_id)
        ON DELETE RESTRICT,
    quantity integer NOT NULL CHECK (quantity > 0),
    unit_price_at_order numeric(12,2) NOT NULL
        CHECK (unit_price_at_order >= 0),
    PRIMARY KEY (order_id, product_id)
);

-- Additional indexes often helpful for child-side access paths.
CREATE INDEX idx_orders_customer
    ON relation_lab.orders(customer_id);

CREATE INDEX idx_order_items_product
    ON relation_lab.order_items(product_id);
~~~

All tables use schema-qualified names `relation_lab.table_name`, avoiding dependence on `search_path`. Primary key and `UNIQUE` indexes are created by PostgreSQL to enforce constraints; `idx_orders_customer` and `idx_order_items_product` are added explicitly for foreign-key access paths.

### Step 2: Load Fixed Seed Data

~~~sql
BEGIN;

INSERT INTO relation_lab.customers
    (customer_id, email, full_name)
VALUES
    (1, 'an@example.test',   'An'),
    (2, 'binh@example.test', 'Binh'),
    (3, 'chi@example.test',  'Chi');

INSERT INTO relation_lab.customer_profiles
    (customer_id, birthday, bio)
VALUES
    (1, DATE '1998-05-10', 'Loyal customer'),
    (2, DATE '2000-09-02', 'Same-day delivery preferred');

INSERT INTO relation_lab.orders
    (order_id, customer_id, ordered_at, status)
VALUES
    (1001, 1, '2026-11-01 08:00:00+00', 'paid'),
    (1002, 1, '2026-11-02 09:00:00+00', 'paid'),
    (1003, 2, '2026-11-03 10:00:00+00', 'pending');

INSERT INTO relation_lab.products
    (product_id, product_name, current_price)
VALUES
    (501, 'Mouse',    200.00),
    (502, 'Keyboard', 400.00),
    (503, 'Cable',     50.00);

INSERT INTO relation_lab.order_items
    (order_id, product_id, quantity, unit_price_at_order)
VALUES
    (1001, 501, 2, 180.00),
    (1001, 502, 1, 400.00),
    (1002, 503, 3,  50.00),
    (1003, 501, 1, 200.00),
    (1003, 503, 1,  50.00);

COMMIT;
~~~

Intentional dataset design:

- Customer **An** has a profile and two orders.
- **Binh** has a profile and one order.
- **Chi** has neither a profile nor any orders yet.
- Order **1001** contains two products; product **501** appears in both order 1001 and order 1003.
- Product 501's price at purchase in order 1001 is 180.00, different from its current `current_price` of 200.00.

With fixed data, we can predict query results deterministically without depending on runtime timestamps.

## 7. Querying 1:1 with LEFT JOIN

To retrieve **all customers**, including those who have not created a profile yet:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    p.birthday,
    p.bio
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.customer_profiles AS p
    ON p.customer_id = c.customer_id
ORDER BY c.customer_id;
~~~

Expected output:

| customer_id | full_name | birthday | bio |
| ---: | --- | --- | --- |
| 1 | An | 1998-05-10 | Loyal customer |
| 2 | Binh | 2000-09-02 | Same-day delivery preferred |
| 3 | Chi | NULL | NULL |

`LEFT JOIN` preserves customer Chi. Using `INNER JOIN` would exclude Chi because there is no matching row in `customer_profiles`.

### Finding Customers Without a Profile

~~~sql
SELECT c.customer_id, c.full_name
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.customer_profiles AS p
    ON p.customer_id = c.customer_id
WHERE p.customer_id IS NULL
ORDER BY c.customer_id;
~~~

Result: customer Chi, ID 3.

You can also use `NOT EXISTS`:

~~~sql
SELECT c.customer_id, c.full_name
FROM relation_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM relation_lab.customer_profiles AS p
    WHERE p.customer_id = c.customer_id
)
ORDER BY c.customer_id;
~~~

In both approaches, **finding no profile** is a valid business fact, not inherently a constraint error when the 1:1 relationship is optional.

## 8. Querying 1:N and Counting Correctly

### Fetching Orders for One Customer

~~~sql
SELECT
    o.order_id,
    o.ordered_at,
    o.status
FROM relation_lab.orders AS o
WHERE o.customer_id = 1
ORDER BY o.order_id;
~~~

Expected orders: 1001 and 1002.

### Counting Orders per Customer, Including 0 Orders

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Result:

| customer_id | full_name | order_count |
| ---: | --- | ---: |
| 1 | An | 2 |
| 2 | Binh | 1 |
| 3 | Chi | 0 |

**Do not use `COUNT(*)` to count orders** after a `LEFT JOIN` in this example. For Chi, the outer join still produces one row with `NULL`s in the `orders` columns; `COUNT(*)` would return 1, whereas `COUNT(o.order_id)` returns 0.

### Filtering by Status Without Dropping Customers Without Orders

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS paid_orders
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
   AND o.status = 'paid'
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Result: An 2, Binh 0, Chi 0. Placing `o.status = 'paid'` in the `WHERE` clause would filter out rows with no matching orders under SQL semantics, defeating the purpose of `LEFT JOIN`.

## 9. Querying N:M via the Junction Table

### Listing Products in an Order

~~~sql
SELECT
    o.order_id,
    p.product_id,
    p.product_name,
    oi.quantity,
    oi.unit_price_at_order,
    (oi.quantity * oi.unit_price_at_order)
        AS line_amount
FROM relation_lab.orders AS o
JOIN relation_lab.order_items AS oi
    ON oi.order_id = o.order_id
JOIN relation_lab.products AS p
    ON p.product_id = oi.product_id
WHERE o.order_id = 1001
ORDER BY p.product_id;
~~~

Expected output:

| order_id | product_id | product_name | quantity | unit_price_at_order | line_amount |
| ---: | ---: | --- | ---: | ---: | ---: |
| 1001 | 501 | Mouse | 2 | 180.00 | 360.00 |
| 1001 | 502 | Keyboard | 1 | 400.00 | 400.00 |

**Order 1001 total = 760.00.** Do not use product 501's current price to recalculate historical lines because catalog prices can change after purchase.

### Computing Total Amount for Every Order

~~~sql
SELECT
    o.order_id,
    COALESCE(
        SUM(oi.quantity * oi.unit_price_at_order), 0
    )::numeric(14,2) AS order_amount
FROM relation_lab.orders AS o
LEFT JOIN relation_lab.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY o.order_id
ORDER BY o.order_id;
~~~

Result:

| order_id | order_amount |
| ---: | ---: |
| 1001 | 760.00 |
| 1002 | 150.00 |
| 1003 | 250.00 |

`LEFT JOIN` ensures even orders with no line items yet (when permitted by the schema) still appear. `COALESCE` turns a `NULL` `SUM` result into 0 in that case.

### Seeing Which Orders Contain a Given Product

~~~sql
SELECT
    p.product_id,
    p.product_name,
    o.order_id,
    o.status,
    oi.quantity
FROM relation_lab.products AS p
JOIN relation_lab.order_items AS oi
    ON oi.product_id = p.product_id
JOIN relation_lab.orders AS o
    ON o.order_id = oi.order_id
WHERE p.product_id = 501
ORDER BY o.order_id;
~~~

Product 501 appears in orders 1001 and 1003. This is the reverse traversal of the N:M relationship, using the exact same junction table.

### Counting How Many Orders Include Each Product

~~~sql
SELECT
    p.product_id,
    p.product_name,
    COUNT(oi.order_id) AS number_of_orders
FROM relation_lab.products AS p
LEFT JOIN relation_lab.order_items AS oi
    ON oi.product_id = p.product_id
GROUP BY p.product_id, p.product_name
ORDER BY p.product_id;
~~~

Because `PRIMARY KEY(order_id, product_id)` ensures at most one row per pair, `COUNT(oi.order_id)` in this design gives the number of distinct orders containing that product. With an `order_item_lines` design allowing multiple rows for the same product in an order, you must use `COUNT(DISTINCT oi.order_id)` if the goal is order count rather than line count.

## 10. Row Multiplication Trap When Joining Multiple 1:N Relationships

A customer has two orders; each order in turn has multiple line items. When joining all three tables:

~~~sql
SELECT
    c.customer_id,
    o.order_id,
    oi.product_id
FROM relation_lab.customers AS c
JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
JOIN relation_lab.order_items AS oi
    ON oi.order_id = o.order_id
WHERE c.customer_id = 1
ORDER BY o.order_id, oi.product_id;
~~~

Customer An has **two orders**, yet the result has **three item rows**: two products in order 1001 and one product in order 1002.

If you write:

~~~sql
SELECT
    c.customer_id,
    COUNT(o.order_id) AS order_count
FROM relation_lab.customers AS c
JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
JOIN relation_lab.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY c.customer_id;
~~~

the `o.order_id` count gets **inflated** because each order repeats once per line item.

A fix matching the goal "count orders with at least one item":

~~~sql
SELECT
    c.customer_id,
    COUNT(DISTINCT o.order_id) AS order_count
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN relation_lab.order_items AS oi
    ON oi.order_id = o.order_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

However, if you only need to **count all orders** regardless of items, the better approach is **not joining `order_items` unnecessarily**. Understand how relationships multiply row sets before aggregating, instead of habitually sprinkling `DISTINCT` to mask issues.

### Pre-Aggregating Before Joining

For multi-level reports, it is often cleaner to aggregate at the order level first:

~~~sql
WITH order_totals AS (
    SELECT
        oi.order_id,
        SUM(oi.quantity * oi.unit_price_at_order) AS amount
    FROM relation_lab.order_items AS oi
    GROUP BY oi.order_id
)
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count,
    COALESCE(SUM(ot.amount), 0)::numeric(14,2)
        AS total_amount
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
LEFT JOIN order_totals AS ot
    ON ot.order_id = o.order_id
GROUP BY c.customer_id, c.full_name
ORDER BY c.customer_id;
~~~

Expected result: An has two orders totaling 910.00, Binh has one order totaling 250.00, and Chi has zero orders totaling 0.00. This illustrates separating **aggregation granularity** to avoid multiplying figures when combining multiple relationships.

## 11. What Happens When Data Violates Relationship Rules?

A key benefit of encoding relationships with constraints is that PostgreSQL rejects invalid operations regardless of which client writes.

### 11.1. Duplicate Profile in 1:1

When customer 1 already has a profile:

~~~sql
-- Example intentionally triggering a unique/primary key error:
INSERT INTO relation_lab.customer_profiles
    (customer_id, bio)
VALUES
    (1, 'A second profile');
~~~

PostgreSQL raises a primary/unique key violation (SQLSTATE `23505`). This proves the **at most one profile per customer** constraint is active.

### 11.2. Profile Pointing to a Non-Existent Customer

~~~sql
-- Example intentionally triggering a foreign key error:
INSERT INTO relation_lab.customer_profiles
    (customer_id, bio)
VALUES
    (9999, 'No customer 9999');
~~~

PostgreSQL rejects it with a foreign key error (SQLSTATE `23503`), because customer 9999 does not exist.

### 11.3. Order Without a Customer

~~~sql
-- Example intentionally triggering a NOT NULL error:
INSERT INTO relation_lab.orders
    (order_id, customer_id, ordered_at, status)
VALUES
    (2000, NULL, now(), 'pending');
~~~

The `customer_id NOT NULL` column causes the SQL statement to fail (SQLSTATE `23502`). Having `FOREIGN KEY` without `NOT NULL` would fail the rule "every order must have a customer".

### 11.4. Two Rows with the Same Order–Product Pair

~~~sql
-- Order 1001 already contains product 501.
INSERT INTO relation_lab.order_items
    (order_id, product_id, quantity, unit_price_at_order)
VALUES
    (1001, 501, 1, 180.00);
~~~

The SQL statement fails due to `PRIMARY KEY(order_id, product_id)`. If the intent is to increase the quantity of an existing product, the application should run **UPDATE** or **INSERT ... ON CONFLICT ... DO UPDATE** according to business semantics, rather than inserting a duplicate key row.

**The statements above are error-testing exercises, not valid seed statements.** In `psql`, after an error inside an open transaction, the transaction enters an aborted state and requires `ROLLBACK` before proceeding; run each test separately or use savepoints/controlled transactions.

## 12. INSERT ... ON CONFLICT in Junction Tables

Because `order_items` has a composite key, it works well with certain upsert operations.

For example, to add 2 more units of product 501 to order 1001 while keeping the locked-in unit price unchanged:

~~~sql
INSERT INTO relation_lab.order_items
    (order_id, product_id, quantity, unit_price_at_order)
VALUES
    (1001, 501, 2, 180.00)
ON CONFLICT (order_id, product_id)
DO UPDATE SET
    quantity = relation_lab.order_items.quantity
             + EXCLUDED.quantity;
~~~

`EXCLUDED.quantity` holds the proposed value from the `INSERT` clause. On the initial dataset, quantity for `(1001, 501)` increases from 2 to 4. This operation **mutates the lab data**: if you want to keep the earlier sum exercise results intact, wrap it in a transaction and `ROLLBACK`, or reset the lab afterward.

Do not assume every additive upsert is **idempotent**. If a request is retried, quantity keeps increasing. Production systems need explicit idempotency keys and duplicate-request handling rules.

## 13. How ON DELETE and ON UPDATE Actions Affect Relationships

When deleting a parent record, the foreign key must specify how child rows are handled. PostgreSQL supports several referential actions:

| Action | Behavior When Referenced Row Is Deleted/Updated |
| --- | --- |
| `NO ACTION` | Allows the operation if the constraint is still satisfied when checked; can be deferred if the constraint permits |
| `RESTRICT` | Immediately blocks the operation if referenced, without allowing deferral like `NO ACTION` |
| `CASCADE` | Automatically deletes or updates matching keys in child rows accordingly |
| `SET NULL` | Sets the child FK column to `NULL`, valid only if constraints/nullability permit |
| `SET DEFAULT` | Sets the FK column to its default value; that value must still satisfy related constraints |

In our lab example:

- Deleting a customer with a profile: `customer_profiles ON DELETE CASCADE` can delete the profile automatically.
- Deleting a customer with orders: `orders ON DELETE RESTRICT` blocks deleting the customer.
- Deleting an order: `order_items ON DELETE CASCADE` deletes the order's line items.
- Deleting a product already used in orders: `order_items.product_id ON DELETE RESTRICT` blocks deleting the product, preserving historical references.

**Do not treat CASCADE as the simplest default.** In transactional systems, deleting customers, orders, or products can affect legal retention and audit trails; cascading deletes can wipe out critical data.

### SET NULL Example for Optional Relationships

A support ticket may not yet have an assigned employee:

~~~sql
CREATE TABLE employees (
    employee_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE support_tickets (
    ticket_id bigint PRIMARY KEY,
    assignee_id bigint NULL
        REFERENCES employees(employee_id)
        ON DELETE SET NULL
);
~~~

When an assigned employee is deleted, the ticket remains and `assignee_id` becomes `NULL`. If `assignee_id` were declared `NOT NULL`, `ON DELETE SET NULL` would conflict with the constraint and the delete would fail. That is why **deletion behavior and relationship optionality** must be chosen together.

## 14. Junction Tables Have Their Own Lifecycle and Attributes

An N:M table does not have to contain only two foreign keys. Many real-world relationships carry **attributes belonging to the link itself**:

| Business Relationship | Junction Table | Potential Link Attributes |
| --- | --- | --- |
| Student – course | `enrollments` | Enrollment date, grade, status |
| User – role | `user_roles` | Granted by, expiration, grant source |
| Order – product | `order_items` | Quantity, unit price at purchase, discount |
| Doctor – patient | `care_assignments` | Role, start/end timestamps |
| Employee – project | `project_members` | Role, join date |

Student–course example:

~~~sql
CREATE TABLE students (
    student_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE courses (
    course_id bigint PRIMARY KEY,
    course_name text NOT NULL
);

CREATE TABLE enrollments (
    student_id bigint NOT NULL REFERENCES students(student_id),
    course_id bigint NOT NULL REFERENCES courses(course_id),
    enrolled_at timestamptz NOT NULL DEFAULT now(),
    grade numeric(4,2),
    PRIMARY KEY (student_id, course_id)
);
~~~

Here `enrolled_at` and `grade` belong to the **enrollment**, not to the student alone or the course alone.

If students are allowed to retake the same course across multiple semesters, `PRIMARY KEY(student_id, course_id)` is too rigid. You can add `semester_id` to the composite key or use a dedicated `enrollment_id` with an appropriate constraint. The choice depends on what the business defines as "one enrollment".

## 15. Composite Key vs. Surrogate Key for Junction Tables

Two common approaches:

**Natural composite key for the relationship:**

~~~sql
PRIMARY KEY (student_id, course_id)
~~~

Pros: clearly expresses no duplicate links for the same pair; no extra ID needed. Cons: other tables referencing an enrollment may have to carry two FK columns; when multiple versions of the relationship are allowed, the key must be expanded.

**Surrogate key:**

~~~sql
enrollment_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
student_id bigint NOT NULL REFERENCES students(student_id),
course_id bigint NOT NULL REFERENCES courses(course_id),
UNIQUE (student_id, course_id)
~~~

If the business **still** forbids duplicate pairs, `UNIQUE(student_id, course_id)` must be kept. Adding `enrollment_id` while dropping uniqueness easily allows duplicate relationship rows.

Neither option is universally optimal. When a junction table is referenced by external systems, holds many attributes, or has its own lifecycle, a surrogate key can be convenient. When the link is simple and a pair occurs only once, a composite key is usually concise.

## 16. UNIQUE, NULL, and Optional 1:1 Relationships

Suppose you design a table with a nullable and unique `customer_id`:

~~~sql
CREATE TABLE draft_profiles (
    draft_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint UNIQUE REFERENCES relation_lab.customers(customer_id),
    draft_text text
);
~~~

Under PostgreSQL's default `UNIQUE` semantics, multiple rows with `customer_id IS NULL` **can coexist**, while each non-`NULL` `customer_id` may appear at most once.

This can be valid if drafts are not yet tied to a customer. However, if the rule states "every draft must belong to exactly one customer", `customer_id NOT NULL` is required.

Starting in PostgreSQL 15, `UNIQUE NULLS NOT DISTINCT` treats `NULL` values as indistinct for uniqueness checks. That is an option for special rules, **not a mandatory requirement of every 1:1 model**.

### Uniqueness Condition Applying Only to a Subset of Rows

Suppose a customer has many addresses, yet **at most one default address**. This is not 1:1 between customers and all addresses; overall it remains 1:N, plus the rule "at most one default address".

PostgreSQL supports **partial unique indexes**:

~~~sql
CREATE TABLE customer_addresses (
    address_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id bigint NOT NULL
        REFERENCES relation_lab.customers(customer_id),
    address_text text NOT NULL,
    is_default boolean NOT NULL DEFAULT false
);

CREATE UNIQUE INDEX uq_one_default_address_per_customer
ON customer_addresses(customer_id)
WHERE is_default = true;
~~~

Only rows with `is_default = true` enter this unique index. A customer can have many addresses, yet cannot have **two default addresses simultaneously**. However, that constraint **does not force at least one** default address to exist.

This example shows why you should distinguish **overall cardinality** from **filtered uniqueness rules** in the business domain.

## 17. Indexes for Foreign Keys and JOIN Directions

Logically correct relationships still require performance awareness.

- `PRIMARY KEY` and `UNIQUE` automatically create backing indexes on their defined columns.
- PostgreSQL **does not by default create indexes on every FOREIGN KEY column on the child side**.
- A composite primary key `(order_id, product_id)` normally supports lookups by its leading column `order_id`.
- Queries looking up orders by `product_id` should consider a dedicated index because `product_id` is the second column in the composite key.
- Deleting or updating parent rows may need to look up referencing child rows; FK indexes are often helpful on large tables.

That is why the lab includes:

~~~sql
CREATE INDEX idx_orders_customer
ON relation_lab.orders(customer_id);

CREATE INDEX idx_order_items_product
ON relation_lab.order_items(product_id);
~~~

Example plan inspection:

~~~sql
EXPLAIN
SELECT order_id
FROM relation_lab.orders
WHERE customer_id = 1;
~~~

And:

~~~sql
EXPLAIN
SELECT order_id
FROM relation_lab.order_items
WHERE product_id = 501;
~~~

**A table with only a few rows may still be sequentially scanned** despite having an index. That does not mean the index is broken: PostgreSQL may pick a sequential scan because it is cheaper on tiny datasets. On realistic datasets, inspect `EXPLAIN (ANALYZE, BUFFERS)`, row distributions, statistics, and workloads. Note that `EXPLAIN ANALYZE` actually executes the SQL statement; for `UPDATE`/`DELETE`, use a safe environment and proper transactions.

## 18. N:M Relationships Can Carry Complex Business Attributes

A junction table is not merely a "technical table". In many systems, it becomes a full-fledged business entity.

For instance, `order_items` has `quantity` and `unit_price_at_order`. If extended:

~~~sql
ALTER TABLE relation_lab.order_items
ADD COLUMN discount_amount numeric(12,2) NOT NULL DEFAULT 0
    CHECK (discount_amount >= 0);
~~~

Then the discount belongs to the **order line item**, not to the product globally. Product 501 can be sold with different prices or promotions in different orders.

If the business requires `discount_amount <= quantity * unit_price_at_order`, you can add a `CHECK` constraint referencing columns on the same row:

~~~sql
ALTER TABLE relation_lab.order_items
ADD CONSTRAINT chk_discount_not_over_line_total
CHECK (
    discount_amount <= quantity * unit_price_at_order
);
~~~

PostgreSQL `CHECK` constraints are designed to evaluate expressions on the **current row**, not as a general mechanism to enforce cross-table aggregates like "total order discount must not exceed the customer's budget". Cross-table invariants require transactions, triggers, or other appropriate mechanisms.

## 19. "At Least One" Cardinality Often Needs Dedicated Protection

In the lab schema, `orders` can exist without `order_items`. From a business perspective, a `draft` order may be valid before products are added. However, upon transitioning to `paid`, the system usually requires **at least one line item**.

The foreign key from `order_items.order_id` to `orders.order_id` only guarantees "every item has an order". It does **not** guarantee "every order has at least one item".

Options to consider:

1. Allow orders in `pending`/`draft` state with no items; when transitioning to `paid`, verify item existence inside the same transaction with proper race-condition safeguards.
2. Use triggers/constraint triggers with the required logic and careful attention to check timing.
3. Design order + line item creation as a single atomic transaction before moving to a publicly visible status.

Do not try to stretch a simple foreign key into a guarantee for bidirectional invariants.

Similarly, `UNIQUE` in 1:1 guarantees **at most one**, not **at least one**; `PRIMARY KEY(order_id, product_id)` guarantees pair uniqueness, not that an order contains items.

## 20. Transactions When Creating Parent and Child Records

Suppose an application wants to insert a customer and profile together:

~~~sql
BEGIN;

INSERT INTO relation_lab.customers
    (customer_id, email, full_name)
VALUES
    (4, 'dung@example.test', 'Dung');

INSERT INTO relation_lab.customer_profiles
    (customer_id, birthday, bio)
VALUES
    (4, DATE '1997-01-01', 'New customer');

COMMIT;
~~~

Inside a transaction, if creating the profile fails and the application runs `ROLLBACK`, the newly inserted customer is also rolled back, avoiding half-completed business state.

Similarly, creating an order and its line items in the same transaction:

~~~sql
BEGIN;

INSERT INTO relation_lab.orders
    (order_id, customer_id, ordered_at, status)
VALUES
    (1004, 1, '2026-11-04 09:00:00+00', 'pending');

INSERT INTO relation_lab.order_items
    (order_id, product_id, quantity, unit_price_at_order)
VALUES
    (1004, 502, 1, 400.00);

COMMIT;
~~~

To experiment without persisting data:

~~~sql
BEGIN;

INSERT INTO relation_lab.orders
    (order_id, customer_id, ordered_at, status)
VALUES
    (9999, 1, '2026-11-05 09:00:00+00', 'pending');

ROLLBACK;
~~~

`ROLLBACK` reverts the uncommitted order 9999. **Transactions do not replace constraints**, and constraints do not replace transactions: both mechanisms work together to ensure correctness when multiple operations must succeed together.

## 21. Evolving Relationships as Data Grows

A relationship often starts simple and evolves with the business.

### From 1:1 to 1:N

Initially a customer has one shipping address:

~~~text
customers (1) -- (0..1) shipping_address
~~~

Later the app supports multiple addresses; you need a `customer_addresses` table with its own primary key and a non-`UNIQUE` `customer_id`. If there is a one-default-address rule, use a partial unique index as in section 16.

When migrating, manage data migration, API changes, and how `JOIN` queries may multiply rows.

### From 1:N to N:M

Initially an employee belongs to only one team:

~~~text
employees.team_id -> teams.team_id
~~~

When cross-team membership is allowed, refactor into an `employee_teams(employee_id, team_id, ...)` table. Do not add `team_id_2`, `team_id_3`, or a list string inside the employees table.

### When Should You Not Split 1:1?

If a group of columns shares the exact same lifecycle, is always read together, and has no distinct permission or isolation needs, keeping them in one table simplifies the model. Splitting 1:1 should have a clear rationale: separate lifecycles, permission boundaries, large optional blobs, modularization, or other scaling needs.

Blindly splitting tables increases joins and dependencies without delivering matching benefits.

## 22. Inspecting Constraints and Relationships in PostgreSQL

### Via psql

In the `psql` CLI:

~~~text
\d relation_lab.customers
\d relation_lab.customer_profiles
\d relation_lab.orders
\d relation_lab.products
\d relation_lab.order_items
~~~

This outputs columns, primary keys, indexes, and foreign keys. These are `psql` meta-commands, not standard SQL sent directly from JDBC.

### Via the pg_constraint Catalog

~~~sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    c.conname AS constraint_name,
    c.contype AS constraint_type,
    pg_get_constraintdef(c.oid) AS definition
FROM pg_constraint AS c
JOIN pg_class AS t
    ON t.oid = c.conrelid
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'relation_lab'
ORDER BY t.relname, c.conname;
~~~

`contype` commonly uses codes such as `p` (primary key), `f` (foreign key), `u` (unique), and `c` (check). `pg_get_constraintdef` lets you inspect the actual constraint definition stored in the database rather than relying solely on design docs.

### Listing Foreign Key Tables and Columns

~~~sql
SELECT
    tc.table_schema,
    tc.table_name,
    tc.constraint_name,
    kcu.column_name
FROM information_schema.table_constraints AS tc
JOIN information_schema.key_column_usage AS kcu
    ON tc.constraint_catalog = kcu.constraint_catalog
   AND tc.constraint_schema = kcu.constraint_schema
   AND tc.constraint_name = kcu.constraint_name
   AND tc.table_name = kcu.table_name
WHERE tc.table_schema = 'relation_lab'
  AND tc.constraint_type = 'FOREIGN KEY'
ORDER BY tc.table_name, tc.constraint_name, kcu.ordinal_position;
~~~

`information_schema` visibility can depend on the querying role's privileges. If a table or constraint does not appear, check both permissions and schema scope before concluding no foreign key exists.

## 23. Common Design Mistakes

### Mistake 1: Writing 1:1 While Forgetting UNIQUE on the Child Table

A `FOREIGN KEY` alone allows many child records to reference the same parent record. Use `UNIQUE(fk)` or a shared primary key if the limit must be at most one.

### Mistake 2: Putting FOREIGN KEY on the Wrong Side of a 1:N Relationship

One customer has many orders, so `customer_id` belongs in `orders`. Trying to store multiple order IDs inside a `customers` column makes referential integrity and updates difficult.

### Mistake 3: Allowing NULL When Business Requires a Mandatory Relationship

A nullable foreign key permits rows without a parent. Combine `NOT NULL` whenever every child row must belong to a parent.

### Mistake 4: Assuming UNIQUE Guarantees at Least One Linked Row

`UNIQUE` only prevents duplicates; it does not create a child row for every parent. Enforcing "at least one" typically requires workflow/application logic or additional design mechanisms.

### Mistake 5: Storing N:M Relationships as a Comma-Separated ID String

Makes per-element reference checks, deletions, link attributes, and joins painful. Use a junction table when relational referential integrity is needed.

### Mistake 6: Adding an Auto-Increment ID and Forgetting Business Uniqueness

A standalone `order_item_id` does not prevent two identical `(order_id, product_id)` rows. If each pair may appear only once, `UNIQUE(order_id, product_id)` is still required.

### Mistake 7: Using COUNT(*) After LEFT JOIN to Count Child Records

Parent rows without children still produce one preserved row. Use `COUNT(child.id)` to count actual child rows.

### Mistake 8: Joining Multiple Relationships and Multiplying SUM/COUNT

Chained 1:N relationships cause parent entities to repeat across multiple rows. Identify the **aggregation unit**, use `COUNT(DISTINCT ...)` or pre-aggregate by level before joining when appropriate.

### Mistake 9: Using ON DELETE CASCADE Without Considering Data Lifecycle

Deleting a customer can wipe out order and invoice history if cascading is applied carelessly. Choose `RESTRICT`/`NO ACTION`, soft deletion, or an appropriate retention policy.

### Mistake 10: Assuming FOREIGN KEY Automatically Indexes the Child Table

PostgreSQL does not automatically create every index on the referencing side. Evaluate JOIN workloads, FK filters, and parent delete/update checks to decide on extra indexes.

### Mistake 11: Forgetting That Product Catalog Prices Can Change

If historical order reports read `products.current_price` instead of `order_items.unit_price_at_order`, past totals shift incorrectly. Relationship attributes must live on the appropriate entity.

### Mistake 12: Changing Cardinality Without Data Migration and Query Updates

Moving from 1:1 to 1:N or 1:N to N:M demands data migration, index updates, permissions, API changes, and updated aggregations. Altering DDL alone is not enough.

## 24. Practice Exercises and Expected Outputs

The exercises below reuse the schema and seed data from section 6, **before running the extended INSERT/UPDATE examples**.

### Exercise 1: Customers Without a Profile

Write SQL using `LEFT JOIN` or `NOT EXISTS` to find customers who have no profile.

**Sample Answer:**

~~~sql
SELECT c.customer_id, c.full_name
FROM relation_lab.customers AS c
WHERE NOT EXISTS (
    SELECT 1
    FROM relation_lab.customer_profiles AS p
    WHERE p.customer_id = c.customer_id
);
~~~

Result: Chi, ID 3.

### Exercise 2: Order Count per Customer

~~~sql
SELECT c.customer_id, COUNT(o.order_id) AS order_count
FROM relation_lab.customers AS c
LEFT JOIN relation_lab.orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id
ORDER BY c.customer_id;
~~~

Result: `(1,2)`, `(2,1)`, `(3,0)`. Using `COUNT(*)` gives the wrong value for Chi when counting actual orders.

### Exercise 3: Total Amount per Order

~~~sql
SELECT
    oi.order_id,
    SUM(oi.quantity * oi.unit_price_at_order)
        AS total_amount
FROM relation_lab.order_items AS oi
GROUP BY oi.order_id
ORDER BY oi.order_id;
~~~

Result: order 1001 = 760.00, order 1002 = 150.00, order 1003 = 250.00. This query only shows orders **that have items**; to include empty orders, `LEFT JOIN` starting from `orders`.

### Exercise 4: In How Many Orders Was Each Product Purchased?

~~~sql
SELECT
    p.product_id,
    p.product_name,
    COUNT(oi.order_id) AS order_count
FROM relation_lab.products AS p
LEFT JOIN relation_lab.order_items AS oi
    ON oi.product_id = p.product_id
GROUP BY p.product_id, p.product_name
ORDER BY p.product_id;
~~~

Result: Mouse (501) in 2 orders, Keyboard (502) in 1 order, Cable (503) in 2 orders.

### Exercise 5: Why Can't An Have Two Profiles?

Try inserting another profile with `customer_id = 1`. Which constraint blocks it? If you switch to a table with its own `profile_id PRIMARY KEY`, what must be added to keep it 1:1?

**Answer:** `PRIMARY KEY(customer_id)` blocks it; with a separate primary key, you need `UNIQUE(customer_id)` plus `NOT NULL` when every profile must attach to a customer.

### Exercise 6: Student–Course Design

Design three tables `students`, `courses`, and `enrollments`. Rule: each student can take many courses; each course has many students; a student may enroll at most once per course per semester.

**Hint:** `enrollments` carries three foreign keys/identifying attributes, and `UNIQUE(student_id, course_id, semester_id)` or a corresponding composite primary key. Decide explicitly whether semester should be a separate table or a domain value in a real design.

### Exercise 7: Choosing Deletion Behavior

A system allows deleting a draft order along with its line items, yet forbids deleting a customer who still has orders and forbids deleting a product that has appeared in any order. Which `ON DELETE` actions fit?

**Answer per lab model:** `orders.customer_id ON DELETE RESTRICT`, `order_items.order_id ON DELETE CASCADE`, and `order_items.product_id ON DELETE RESTRICT`. However, "only draft orders may be deleted" must still be enforced in business/transaction logic or an appropriate constraint; `ON DELETE CASCADE` alone does not distinguish order statuses.

### Exercise 8: Explaining the JOIN Trap

An has two orders yet three `order_items` rows. Why does `COUNT(o.order_id)` return 3 instead of 2 after joining `order_items`?

**Answer:** Each order row is repeated once per line item. You must count at the right relationship granularity—for example, querying `orders` directly or using `COUNT(DISTINCT o.order_id)` when the goal and join structure match.

## 25. Decision Process When Designing Relationships

When turning business requirements into a PostgreSQL schema, follow this sequence:

1. **Identify entities:** who or what has an independent identity? For example, customer, order, product.
2. **Determine maximum cardinality in both directions:** how many B can A have, and how many A can B have? Never ask in only one direction.
3. **Determine minimum cardinality:** must B attach to A? Must A have at least one B?
4. **Decide where the foreign key goes:** 1:N puts the FK on the many side; 1:1 uses a unique FK or shared PK; N:M uses a junction table.
5. **Add NOT NULL/UNIQUE/PRIMARY KEY/CHECK:** enforce rules directly expressible via constraints.
6. **Choose delete/update actions:** `CASCADE`, `RESTRICT`, `NO ACTION`, or `SET NULL` aligned with data lifecycles.
7. **Design link attributes:** e.g., quantity/price belong on `order_items`, not forced onto either parent side.
8. **Create needed indexes:** especially on child-side FKs and common query access paths.
9. **Test realistic queries:** `JOIN`, `LEFT JOIN`, `COUNT`, and `SUM` can multiply row counts.
10. **Verify invariants beyond FK scope:** "at least one item", business status workflows, concurrency, and state transitions need complementary solutions.

Do not start from "how many tables should we have?" and force the business to fit. Start from **the true constraints of the data**, then select the model and SQL that represent them accurately.

## 26. Summary

The three fundamental relationship types in PostgreSQL have clear storage patterns:

| Relationship | Common Representation | Key Constraints |
| --- | --- | --- |
| **1:1** | Child table with shared PK or unique FK | `FOREIGN KEY` + `PRIMARY KEY` / `UNIQUE` |
| **1:N** | FK placed on the many-side table | `FOREIGN KEY`, plus `NOT NULL` if mandatory on the child side |
| **N:M** | Junction table holding FKs to both sides | Two `FOREIGN KEY`s and composite PK/`UNIQUE` on the link unit |

**Cardinality and optionality must be determined separately.** Foreign keys guarantee valid references; unique prevents duplicates; not null requires a value. Rules such as "every customer must have a profile" or "paid orders must have items" require additional design beyond a plain foreign key.

Once you master these three relationships, you can design schemas with less duplication, express business rules through constraints, write accurate multi-table joins, and maintain PostgreSQL schemas cleanly as applications evolve.
