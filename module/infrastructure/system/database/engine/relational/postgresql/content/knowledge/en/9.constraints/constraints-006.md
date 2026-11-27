# ON DELETE, ON UPDATE, and Choosing Referential Actions in PostgreSQL

When two tables are linked by a **foreign key**, PostgreSQL does not merely verify that a child record references a valid parent record. The database engine also needs rules for what happens when a parent record **is deleted** or **the referenced key value is updated**.

Suppose `orders` contains `customer_id` pointing to `customers.customer_id`:

- If a customer with existing orders is deleted, should those orders also be deleted?
- If the customer is deleted, should the orders be kept with the customer link cleared?
- If a customer ID changes from 10 to 20, does the foreign key in `orders` update automatically?
- If orders must be preserved for accounting compliance, how do you prevent accidental deletion?

In PostgreSQL, the **`ON DELETE`** and **`ON UPDATE`** clauses inside a `FOREIGN KEY` definition let you choose the corresponding behavior. The five standard options are `NO ACTION`, `RESTRICT`, `CASCADE`, `SET NULL`, and `SET DEFAULT`.

This choice is not just SQL syntax. It reflects **data lifecycle and business rules**: whether child rows can exist independently, whether keys may mutate, whether historical records must be preserved, and how many tables a single operation might cascade through.

## 1. Reviewing Parent–Child Relationships and Foreign Keys

A foreign key links values in the **referencing table (commonly called the child table)** to a valid unique key in the **referenced table (commonly called the parent table)**.

Example:

~~~sql
CREATE TABLE customers (
    customer_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
~~~

Here:

| Component | Value in Example |
| --- | --- |
| Parent table | `customers` |
| Referenced key | `customers.customer_id` |
| Child table | `orders` |
| Foreign key column | `orders.customer_id` |
| Constraint | `fk_orders_customer` |

PostgreSQL guarantees that every non-`NULL` `orders.customer_id` matches an existing `customers.customer_id`. In this example, `NOT NULL` also requires every order to have a customer.

~~~mermaid
flowchart LR
    P["customers: customer_id PRIMARY KEY"] -->|"Referenced by"| C["orders: customer_id FOREIGN KEY"]
    P --> D{"Delete or key update on customers?"}
    D --> R["ON DELETE / ON UPDATE decides"]
    R --> A["Block, cascade, or update FK"]
~~~

An `INSERT` or `UPDATE` on the **child table** must still satisfy the foreign key. The `ON UPDATE` clause does **not** mean updating the FK column in the child automatically modifies the parent table; it defines **what happens when the referenced key in the parent table changes**.

## 2. General Syntax

A foreign key can specify actions for both directions:

~~~sql
CREATE TABLE child_table (
    child_id bigint PRIMARY KEY,
    parent_id bigint NOT NULL,

    CONSTRAINT fk_child_parent
        FOREIGN KEY (parent_id)
        REFERENCES parent_table(parent_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);
~~~

This assumes `parent_table(parent_id)` already exists with a primary key or qualifying unique constraint.

Single-column foreign keys can also be declared inline:

~~~sql
parent_id bigint
    REFERENCES parent_table(parent_id)
    ON DELETE SET NULL
    ON UPDATE CASCADE
~~~

For multi-column foreign keys, explicit table-level `FOREIGN KEY (...) REFERENCES ...` syntax is clearer and easier to manage.

**Two independent clauses:** `ON DELETE` handles **deleting a parent row**; `ON UPDATE` handles **changing a parent row's referenced key value**. You can combine `ON DELETE RESTRICT ON UPDATE CASCADE` on the same constraint.

If omitted, PostgreSQL defaults to:

~~~sql
ON DELETE NO ACTION
ON UPDATE NO ACTION
~~~

## 3. Comparison of the Five Actions

| Action | On Parent Delete (`ON DELETE`) | On Parent Key Update (`ON UPDATE`) | Key Notes |
| --- | --- | --- | --- |
| **`NO ACTION`** | Disallows ending check state violating FK; check can be deferred if `DEFERRABLE` | Same | Default; differs from `RESTRICT` in deferrability |
| **`RESTRICT`** | Blocks deletion while referenced by child rows | Blocks key change if restriction violated | Cannot defer this restriction check like `NO ACTION` |
| **`CASCADE`** | Deletes referencing child rows | Updates child FK values to the new parent key | Can affect many rows/tables in a chain |
| **`SET NULL`** | Sets child FK column(s) to `NULL` | Sets child FK column(s) to `NULL` | Column must allow NULL; composite FKs have special rules |
| **`SET DEFAULT`** | Resets child FK to declared default value | Resets FK to default when parent key changes | Default value must still satisfy FK and other constraints |

This can be visualized as a decision tree:

~~~mermaid
flowchart TD
    A["Parent DELETE or key UPDATE"] --> B{"How should child react?"}
    B -->|"Preserve link and block violation"| C["NO ACTION / RESTRICT"]
    B -->|"Child shares lifecycle or FK must follow"| D["CASCADE"]
    B -->|"Child survives with optional link"| E["SET NULL"]
    B -->|"Child moves to valid default parent"| F["SET DEFAULT"]
    C --> G["Check DEFERRABLE requirement"]
    D --> H["Assess cascading blast radius"]
    E --> I["Check NOT NULL and composite FK"]
    F --> J["Verify DEFAULT has valid parent"]
~~~

This tree aids reasoning—it does not make business decisions on its own. A syntactically valid choice can still be **seriously wrong for data retention**.

## 4. NO ACTION: The Default Behavior

`NO ACTION` means: if an operation on the parent table leaves child rows with invalid references, PostgreSQL raises an error when the constraint is checked.

Example:

~~~sql
CREATE TABLE departments_na (
    department_id integer PRIMARY KEY,
    department_name text NOT NULL
);

CREATE TABLE employees_na (
    employee_id integer PRIMARY KEY,
    department_id integer NOT NULL,
    CONSTRAINT fk_employee_department_na
        FOREIGN KEY (department_id)
        REFERENCES departments_na(department_id)
        ON DELETE NO ACTION
        ON UPDATE NO ACTION
);
~~~

Seed data:

~~~sql
INSERT INTO departments_na
    (department_id, department_name)
VALUES (10, 'Engineering');

INSERT INTO employees_na
    (employee_id, department_id)
VALUES (100, 10);
~~~

Attempting to delete department 10:

~~~sql
DELETE FROM departments_na
WHERE department_id = 10;
~~~

PostgreSQL rejects it because employee 100 still references department 10. The error has SQLSTATE **`23503`** (`foreign_key_violation`).

**Omitting `ON DELETE` is still `NO ACTION`.** Never assume omitting the clause causes PostgreSQL to delete child rows or set them to NULL.

### NO ACTION Does Not Mean “Do Nothing and Allow the Delete”

The name is misleading. PostgreSQL **does not ignore referential integrity**. It simply performs no automatic modifying action on child rows (like `CASCADE` or `SET NULL`). If no parent remains for a required FK, the operation is blocked at constraint check time.

## 5. RESTRICT: Blocking Changes While References Exist

`RESTRICT` also prevents deleting or modifying a parent key while referencing child rows would become invalid.

~~~sql
CREATE TABLE customers_restrict (
    customer_id integer PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE orders_restrict (
    order_id integer PRIMARY KEY,
    customer_id integer NOT NULL
        REFERENCES customers_restrict(customer_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
);
~~~

This clearly models **“cannot delete a customer who has orders”**. Real data governance may still require soft deletes, anonymization, or retention policies; `RESTRICT` alone does not implement all of those workflows.

### How Does RESTRICT Differ from NO ACTION?

In simple cases, the two actions **look identical**: deleting a customer with orders fails with an error.

The key difference lies in **whether the check can be deferred**:

- `NO ACTION` allows validation to be deferred **to transaction end** if the constraint is declared `DEFERRABLE` and set to deferred mode.
- `RESTRICT` **cannot be deferred that way**. Attempting the parent operation while referencing child rows exist is blocked immediately, even if you intend to update the child rows in the next SQL statement.

For example, if you need to update a parent code first and then update child rows inside one transaction, `NO ACTION DEFERRABLE` supports that workflow, whereas `RESTRICT` does not.

Beyond deferrability, PostgreSQL also has subtle semantic differences between `NO ACTION` and `RESTRICT` for certain key updates under special equality/collation rules. Base your choice on the required invariant rather than treating them as strictly identical.

## 6. DEFERRABLE and Two-Step Key Updates

By default, most FKs are checked immediately under non-deferrable semantics. PostgreSQL allows declaring a constraint `DEFERRABLE` and controlling check timing.

The experiment below creates two standalone tables:

~~~sql
CREATE TABLE parent_codes (
    code integer PRIMARY KEY
);

CREATE TABLE child_codes (
    child_id integer PRIMARY KEY,
    parent_code integer NOT NULL,
    CONSTRAINT fk_child_parent_codes
        FOREIGN KEY (parent_code)
        REFERENCES parent_codes(code)
        ON UPDATE NO ACTION
        ON DELETE NO ACTION
        DEFERRABLE INITIALLY IMMEDIATE
);

INSERT INTO parent_codes (code) VALUES (10);
INSERT INTO child_codes (child_id, parent_code)
VALUES (1, 10);
~~~

Running:

~~~sql
UPDATE parent_codes
SET code = 20
WHERE code = 10;
~~~

without updating the child simultaneously fails under the default immediate check mode.

However, it works inside a **controlled transaction**:

~~~sql
BEGIN;

SET CONSTRAINTS fk_child_parent_codes DEFERRED;

UPDATE parent_codes
SET code = 20
WHERE code = 10;

UPDATE child_codes
SET parent_code = 20
WHERE parent_code = 10;

COMMIT;
~~~

By commit time, every FK is valid again. The intermediate step is permitted because the `NO ACTION` check was deferred. If the child update failed to run or left any row pointing to the old key, `COMMIT` would fail.

**Note:** `SET CONSTRAINTS ... DEFERRED` applies only to constraints declared `DEFERRABLE`. `RESTRICT` cannot have its restriction check deferred. With `CASCADE`, `SET NULL`, or `SET DEFAULT`, the child modification executes when the parent event occurs; do not assume those actions are postponed until commit just because the FK is declared deferrable.

### When Should You Use DEFERRABLE?

Typical cases include cyclic dependencies, multi-step key renumbering, or bulk data loads/transformations that require integrity **at transaction end**.

In everyday application design, it is better **not to change primary keys frequently**. If a business code must be editable, consider separating an **immutable surrogate identifier** from the **mutable business code**, reducing the need to defer FKs.

## 7. CASCADE: Deleting or Updating Along Relationships

`CASCADE` tells PostgreSQL to automatically modify referencing child rows when a parent row is changed.

### 7.1. ON DELETE CASCADE

~~~sql
CREATE TABLE carts (
    cart_id bigint PRIMARY KEY
);

CREATE TABLE cart_items (
    cart_id bigint NOT NULL
        REFERENCES carts(cart_id)
        ON DELETE CASCADE,
    product_code text NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (cart_id, product_code)
);
~~~

Seed data:

~~~sql
INSERT INTO carts (cart_id) VALUES (1);

INSERT INTO cart_items (cart_id, product_code, quantity)
VALUES
    (1, 'MOUSE', 2),
    (1, 'CABLE', 1);
~~~

When running:

~~~sql
DELETE FROM carts
WHERE cart_id = 1;
~~~

PostgreSQL deletes cart 1 **and** its two dependent `cart_items` rows. Neither child row remains once the transaction commits.

A cart–cart_items relationship has a tightly coupled lifecycle: when a draft cart is discarded, its line items have no standalone meaning. This is an appropriate fit for `ON DELETE CASCADE`.

### 7.2. ON UPDATE CASCADE

Suppose a parent identifier key can change:

~~~sql
CREATE TABLE product_codes (
    product_code text PRIMARY KEY,
    product_name text NOT NULL
);

CREATE TABLE stock_by_product (
    stock_id integer PRIMARY KEY,
    product_code text NOT NULL
        REFERENCES product_codes(product_code)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    quantity integer NOT NULL
);

INSERT INTO product_codes
    (product_code, product_name)
VALUES ('SKU-OLD', 'Mouse');

INSERT INTO stock_by_product
    (stock_id, product_code, quantity)
VALUES (1, 'SKU-OLD', 15);
~~~

Update the parent code:

~~~sql
UPDATE product_codes
SET product_code = 'SKU-NEW'
WHERE product_code = 'SKU-OLD';
~~~

PostgreSQL automatically updates `stock_by_product.product_code` from `SKU-OLD` to `SKU-NEW`.

This is **key-reference propagation**, not automatic synchronization of unrelated columns like `product_name` or `quantity`. Updating `product_name` without changing `product_code` does not alter child rows via `ON UPDATE CASCADE`.

### 7.3. Cascading Can Span Multiple Levels

~~~mermaid
flowchart TD
    A["DELETE order"] --> B["ON DELETE CASCADE: order_items"]
    B --> C{"Is order_items referenced by another table?"}
    C -->|"Has matching cascade"| D["Propagates to dependent tables"]
    C -->|"Has RESTRICT or NO ACTION"| E["Operation may be rejected"]
    C -->|"No"| F["Completes within transaction"]
    D --> F
~~~

If a child row is itself a parent of another table, cascading changes can trigger constraints at deeper levels. Thus a single `DELETE FROM orders WHERE ...` can affect multiple tables.

**`CASCADE` does not stop at “just the direct child rows the author happened to think of”.** Before enabling it in production, trace the full FK dependency graph and business data lifecycle.

## 8. SET NULL: Keeping Child Rows While Clearing the Link

`SET NULL` fits when child records remain meaningful after the referenced object disappears and the relationship is optional.

Example of tasks assigned to employees:

~~~sql
CREATE TABLE employees (
    employee_id integer PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE tasks (
    task_id integer PRIMARY KEY,
    assignee_id integer NULL
        REFERENCES employees(employee_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE,
    title text NOT NULL
);

INSERT INTO employees
    (employee_id, full_name)
VALUES (11, 'An');

INSERT INTO tasks
    (task_id, assignee_id, title)
VALUES
    (701, 11, 'Handle request'),
    (702, NULL, 'Unassigned');
~~~

When employee 11 is deleted:

~~~sql
DELETE FROM employees
WHERE employee_id = 11;
~~~

Task 701 is **not deleted**; instead, `assignee_id` becomes `NULL`. Task 702, which was already unassigned, remains untouched.

### Is NOT NULL Compatible with SET NULL?

No, if setting that column to NULL is actually triggered:

~~~sql
-- Incompatible design for deletion behavior:
assignee_id integer NOT NULL
    REFERENCES employees(employee_id)
    ON DELETE SET NULL
~~~

PostgreSQL may allow creating that DDL, but when a parent with child rows is deleted, attempting to set `assignee_id = NULL` hits `NOT NULL` and the delete fails.

Therefore:

- If a child may survive without a parent, use a nullable column with `SET NULL`.
- If a child **must always have a parent**, use `RESTRICT`/`NO ACTION` or reassign children before deleting.
- If parent and child must disappear together, consider `CASCADE` after reviewing lifecycle rules.

### What Does ON UPDATE SET NULL Mean?

If you set `ON UPDATE SET NULL` and change a **parent key**, PostgreSQL clears the link in child rows instead of updating them to the new key. That is rarely desired when merely “renaming an employee ID”.

Hence our example uses **`ON DELETE SET NULL ON UPDATE CASCADE`**: deleting an employee leaves tasks unassigned, while updating an employee ID keeps tasks linked to that employee.

## 9. SET DEFAULT: Moving Child Rows to a Valid Default Value

`SET DEFAULT` resets the child's foreign key column to its declared `DEFAULT` expression. This action **does not bypass foreign key validation**.

Suppose products belong to categories, and deleting a category moves its products to an “Uncategorized” category.

~~~sql
CREATE TABLE categories (
    category_id integer PRIMARY KEY,
    category_name text NOT NULL
);

-- ID 0 is a real parent row protected by business rules.
INSERT INTO categories
    (category_id, category_name)
VALUES
    (0, 'Uncategorized'),
    (10, 'Accessories');

CREATE TABLE products (
    product_id integer PRIMARY KEY,
    category_id integer NOT NULL DEFAULT 0
        REFERENCES categories(category_id)
        ON DELETE SET DEFAULT
        ON UPDATE CASCADE,
    product_name text NOT NULL
);

INSERT INTO products
    (product_id, category_id, product_name)
VALUES (501, 10, 'Mouse');
~~~

When category 10 is deleted:

~~~sql
DELETE FROM categories
WHERE category_id = 10;
~~~

Product 501 remains, with `category_id` set to `0`, referencing the “Uncategorized” category row.

### Why Must a Parent Row Exist for the Default ID?

If `products.category_id` has `DEFAULT 0` while `categories` has **no row 0**, `SET DEFAULT` writes an invalid FK value and the delete fails.

Similarly, a default of `NULL` works only if the column and other constraints permit `NULL`. `SET DEFAULT` **never creates a missing parent row** or bypasses referential integrity.

### Protect the “Uncategorized” Sentinel Row

In this example, category 0 is a **sentinel row** used as a fallback target. If someone deletes row 0 while products reference it, `SET DEFAULT 0` cannot recover because parent 0 itself no longer exists.

In real environments, enforce explicit safeguards around sentinel rows rather than assuming “nobody would ever delete row 0”.

### Is ON UPDATE SET DEFAULT Usually Useful?

Much less common than `ON UPDATE CASCADE`. When a parent key changes, `SET DEFAULT` severs the relationship and falls back to the default instead of **preserving the business link**. Use it only when that is explicitly intended.

## 10. Comprehensive Lab in a Dedicated Schema

To compare all behaviors in one system, create a **dedicated practice database** (e.g., `fk_actions_lab`) and run all examples inside schema `lab_fk`.

**Warning:** the setup block contains `DROP SCHEMA ... CASCADE`. Run it only in a practice database you own after confirming there is no data to preserve.

### 10.1. Creating Schema and Tables

~~~sql
BEGIN;

DROP SCHEMA IF EXISTS lab_fk CASCADE;
CREATE SCHEMA lab_fk;

-- Customers: parent of orders.
CREATE TABLE lab_fk.customers (
    customer_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

-- Orders: cannot delete a customer who still has orders.
CREATE TABLE lab_fk.orders (
    order_id bigint PRIMARY KEY,
    customer_id bigint NOT NULL,
    status text NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_fk.customers(customer_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);

-- Product categories, including sentinel category_id = 0.
CREATE TABLE lab_fk.categories (
    category_id bigint PRIMARY KEY,
    category_name text NOT NULL
);

-- When deleting a category, products move to category_id 0.
CREATE TABLE lab_fk.products (
    product_id bigint PRIMARY KEY,
    category_id bigint NOT NULL DEFAULT 0,
    product_name text NOT NULL,
    CONSTRAINT fk_products_category
        FOREIGN KEY (category_id)
        REFERENCES lab_fk.categories(category_id)
        ON DELETE SET DEFAULT
        ON UPDATE CASCADE
);

-- Order–product line items.
CREATE TABLE lab_fk.order_items (
    order_id bigint NOT NULL,
    product_id bigint NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    PRIMARY KEY (order_id, product_id),

    CONSTRAINT fk_items_order
        FOREIGN KEY (order_id)
        REFERENCES lab_fk.orders(order_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    CONSTRAINT fk_items_product
        FOREIGN KEY (product_id)
        REFERENCES lab_fk.products(product_id)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
);

-- Employees and tasks: tasks survive if an employee is deleted.
CREATE TABLE lab_fk.employees (
    employee_id bigint PRIMARY KEY,
    full_name text NOT NULL
);

CREATE TABLE lab_fk.tasks (
    task_id bigint PRIMARY KEY,
    assignee_id bigint NULL,
    title text NOT NULL,
    CONSTRAINT fk_tasks_assignee
        FOREIGN KEY (assignee_id)
        REFERENCES lab_fk.employees(employee_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
);

COMMIT;
~~~

This schema makes all four core behaviors easy to observe:

| Relationship | ON DELETE | ON UPDATE | Business Rationale |
| --- | --- | --- | --- |
| customers → orders | `RESTRICT` | `CASCADE` | Keep orders, block deleting active customers; allow key change |
| orders → order_items | `CASCADE` | `CASCADE` | Line items belong strictly to their order |
| products → order_items | `RESTRICT` | `CASCADE` | Do not delete products already used in orders |
| categories → products | `SET DEFAULT` | `CASCADE` | Deleting a category moves products to “Uncategorized” |
| employees → tasks | `SET NULL` | `CASCADE` | Tasks persist when an assignee is removed |

`NO ACTION` is the default and was demonstrated separately with deferrable constraints; there is no need to force every action onto one foreign key.

### 10.2. Loading Sample Data

~~~sql
BEGIN;

INSERT INTO lab_fk.customers
    (customer_id, full_name)
VALUES
    (1, 'An'),
    (2, 'Binh'),
    (3, 'Chi');

INSERT INTO lab_fk.orders
    (order_id, customer_id, status)
VALUES
    (1001, 1, 'paid'),
    (1002, 2, 'pending');

INSERT INTO lab_fk.categories
    (category_id, category_name)
VALUES
    (0, 'Uncategorized'),
    (10, 'Accessories'),
    (20, 'Cables');

INSERT INTO lab_fk.products
    (product_id, category_id, product_name)
VALUES
    (501, 10, 'Mouse'),
    (502, 20, 'Cable'),
    (503, 10, 'Keyboard');

INSERT INTO lab_fk.order_items
    (order_id, product_id, quantity)
VALUES
    (1001, 501, 2),
    (1001, 502, 1),
    (1002, 501, 1);

INSERT INTO lab_fk.employees
    (employee_id, full_name)
VALUES
    (11, 'Lan'),
    (12, 'Minh');

INSERT INTO lab_fk.tasks
    (task_id, assignee_id, title)
VALUES
    (701, 11, 'Review document'),
    (702, NULL, 'Pending assignment');

COMMIT;
~~~

Seeded state:

- Customer 1 has order 1001; customer 2 has order 1002; customer 3 has no orders.
- Order 1001 has two items (products 501, 502); order 1002 has one item (product 501).
- Products 501 and 503 belong to category 10; product 502 belongs to category 20.
- Employee 11 is assigned task 701; task 702 is unassigned.
- Category 0 exists for `SET DEFAULT`.

### 10.3. Demonstrating ON DELETE CASCADE Inside a Rolled-Back Transaction

~~~sql
BEGIN;

DELETE FROM lab_fk.orders
WHERE order_id = 1001;

SELECT order_id, product_id, quantity
FROM lab_fk.order_items
ORDER BY order_id, product_id;

ROLLBACK;
~~~

Inside the transaction before `ROLLBACK`, both item rows of order 1001 disappear via `ON DELETE CASCADE`, while order 1002's item remains. After `ROLLBACK`, order 1001 and both items are restored to their pre-transaction state.

This confirms that cascading is a **transactional data operation**, not an irreversible background job outside transaction control.

### 10.4. Demonstrating ON DELETE SET NULL

~~~sql
BEGIN;

DELETE FROM lab_fk.employees
WHERE employee_id = 11;

SELECT task_id, assignee_id, title
FROM lab_fk.tasks
ORDER BY task_id;

ROLLBACK;
~~~

Inside the transaction, task 701 gets `assignee_id IS NULL`; task 702 remains `NULL`. After rollback, task 701 points to employee 11 again.

### 10.5. Demonstrating ON DELETE SET DEFAULT

~~~sql
BEGIN;

DELETE FROM lab_fk.categories
WHERE category_id = 10;

SELECT product_id, category_id, product_name
FROM lab_fk.products
ORDER BY product_id;

ROLLBACK;
~~~

Inside the transaction, products 501 and 503 move to `category_id = 0`, while product 502 stays in category 20. After rollback, category 10 and the original links return.

### 10.6. Demonstrating ON UPDATE CASCADE

~~~sql
BEGIN;

UPDATE lab_fk.products
SET product_id = 601
WHERE product_id = 501;

SELECT order_id, product_id, quantity
FROM lab_fk.order_items
ORDER BY order_id, product_id;

ROLLBACK;
~~~

Inside the transaction, item rows previously pointing to `product_id = 501` now reference `601`. After rollback, original ID 501 is restored.

**In real designs, do not mutate immutable primary keys just to exercise CASCADE.** This lab scenario illustrates semantics; keep surrogate IDs stable and store mutable product codes in a separate column.

### 10.7. Demonstrating RESTRICT Without Corrupting the Lab Dataset

Try deleting customer 1, who still has orders:

~~~sql
-- This statement INTENTIONALLY triggers a foreign key error.
DELETE FROM lab_fk.customers
WHERE customer_id = 1;
~~~

PostgreSQL refuses to delete the customer due to `fk_orders_customer ON DELETE RESTRICT`. Similarly:

~~~sql
-- Product 501 is referenced in order_items.
-- This statement INTENTIONALLY triggers a foreign key error.
DELETE FROM lab_fk.products
WHERE product_id = 501;
~~~

To test this on a terminal, run it **outside scripts configured with `ON_ERROR_STOP`**. Inside an active transaction, an error leaves the transaction aborted; run `ROLLBACK` or `ROLLBACK TO SAVEPOINT` before proceeding.

Savepoint example for error experiments:

~~~sql
BEGIN;

SAVEPOINT before_attempt;

-- Expected to fail due to RESTRICT:
DELETE FROM lab_fk.customers WHERE customer_id = 1;

-- After the error, roll back to the savepoint:
ROLLBACK TO SAVEPOINT before_attempt;

SELECT customer_id, full_name
FROM lab_fk.customers
WHERE customer_id = 1;

ROLLBACK;
~~~

In `psql` with `ON_ERROR_STOP=1`, a script aborts at the failing `DELETE`; use an interactive session or wrap expected-failure scenarios in a test harness that catches errors.

## 11. Evaluating DELETE and UPDATE Outcomes with a State Table

Starting from the seeded dataset, each operation below is assumed to run **independently** and without committing (so it does not affect subsequent tests):

| Parent Table Operation | Relationship | Expected Observation Before Rollback |
| --- | --- | --- |
| Delete `orders.order_id = 1001` | ON DELETE CASCADE to items | Both items of order 1001 are deleted |
| Delete `employees.employee_id = 11` | ON DELETE SET NULL to tasks | Task 701 survives with `assignee_id = NULL` |
| Delete `categories.category_id = 10` | ON DELETE SET DEFAULT to products | Products 501 and 503 move to category 0 |
| Delete `customers.customer_id = 1` | ON DELETE RESTRICT to orders | FK error; customer is not deleted |
| Delete `products.product_id = 501` | ON DELETE RESTRICT to items | FK error; product is not deleted |
| Update `products.product_id 501 → 601` | ON UPDATE CASCADE to items | Item rows now reference ID 601 |
| Update `customers.customer_id 1 → 10` | ON UPDATE CASCADE to orders | Order 1001 updates `customer_id` to 10 |

This table shows that **the same parent UPDATE or DELETE can trigger completely different behaviors across different relationships**. The behavior belongs to each individual foreign key, not a database-wide setting.

## 12. SET NULL on Multi-Column Foreign Keys: Nullifying Only Selected Columns

Composite foreign keys are common in multi-tenant schemas. Suppose users are scoped within a tenant by `(tenant_id, user_id)`, and a post should retain its `tenant_id` if its author is deleted.

~~~sql
CREATE TABLE lab_fk.tenants (
    tenant_id bigint PRIMARY KEY,
    tenant_name text NOT NULL
);

CREATE TABLE lab_fk.tenant_users (
    tenant_id bigint NOT NULL
        REFERENCES lab_fk.tenants(tenant_id),
    user_id bigint NOT NULL,
    user_name text NOT NULL,
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE lab_fk.posts (
    tenant_id bigint NOT NULL
        REFERENCES lab_fk.tenants(tenant_id),
    post_id bigint NOT NULL,
    author_id bigint NULL,
    title text NOT NULL,
    PRIMARY KEY (tenant_id, post_id),

    CONSTRAINT fk_posts_author
        FOREIGN KEY (tenant_id, author_id)
        REFERENCES lab_fk.tenant_users(tenant_id, user_id)
        ON DELETE SET NULL (author_id)
);
~~~

Notable syntax:

~~~sql
ON DELETE SET NULL (author_id)
~~~

In PostgreSQL versions supporting a column list in `ON DELETE SET NULL`, this sets **only `author_id`** to `NULL` while preserving **`tenant_id`**, because `tenant_id` is part of the post's primary key and cannot be `NULL`.

Without the column list, `SET NULL` on a composite foreign key targets **all referencing columns** by default, which would collide with `NOT NULL` or `PRIMARY KEY` on `tenant_id`.

### When Is a Column List Especially Important?

- Composite foreign keys include a mandatory tenant or scope column.
- Only one part of the relationship—such as author, assignee, or reviewer—is optional.
- You want the record to remain scoped to the right tenant after deleting the dependent entity.

**Syntax note:** PostgreSQL supports column lists for `ON DELETE SET NULL` and `ON DELETE SET DEFAULT`, not for `ON UPDATE SET NULL` / `ON UPDATE SET DEFAULT`. If parent keys will be updated, evaluate full-FK update behavior.

This example uses default `MATCH SIMPLE` semantics: when one FK column is `NULL`, the composite parent existence check is skipped. Because `tenant_id` still has its own independent FK to `tenants`, the post stays validly linked to its tenant even without an author.

## 13. MATCH SIMPLE, MATCH FULL, and NULL Validity

For single-column foreign keys, `NULL` typically represents an optional link. For multi-column FKs, the rules are subtler.

Consider:

~~~sql
FOREIGN KEY (tenant_id, author_id)
REFERENCES tenant_users (tenant_id, user_id)
~~~

Under **`MATCH SIMPLE`** (the default), if any referencing column is `NULL`, the composite parent existence check does not require a matching parent pair.

Under **`MATCH FULL`**, a row is valid only when:

- **All** foreign key columns are `NULL`; or
- **None** of them are `NULL` and the full tuple matches a parent row.

Partially NULL and partially non-NULL tuples are rejected under `MATCH FULL`.

| Composite FK Values | MATCH SIMPLE | MATCH FULL |
| --- | --- | --- |
| (tenant=10, author=501), parent exists | Valid | Valid |
| (tenant=10, author=999), parent missing | Invalid | Invalid |
| (tenant=10, author=NULL) | Valid for composite FK | Invalid |
| (tenant=NULL, author=NULL) | Valid for composite FK, if other constraints allow | Valid for composite FK |

Hence **`ON DELETE SET NULL (author_id)`** in the tenant example intentionally pairs with default `MATCH SIMPLE`. Switching to `MATCH FULL` would conflict semantically with setting only `author_id` to `NULL` while `tenant_id` remains non-NULL.

This illustrates that `ON DELETE` choices cannot be separated from `NOT NULL`, `MATCH`, and primary/unique constraints on the columns involved.

## 14. Actions on Composite Foreign Keys and ON UPDATE CASCADE

A foreign key can reference a multi-column composite key:

~~~sql
CREATE TABLE lab_fk.region_accounts (
    region_code text NOT NULL,
    account_no text NOT NULL,
    account_name text NOT NULL,
    PRIMARY KEY (region_code, account_no)
);

CREATE TABLE lab_fk.region_transactions (
    transaction_id bigint PRIMARY KEY,
    region_code text NOT NULL,
    account_no text NOT NULL,

    CONSTRAINT fk_transactions_account
        FOREIGN KEY (region_code, account_no)
        REFERENCES lab_fk.region_accounts(region_code, account_no)
        ON UPDATE CASCADE
        ON DELETE RESTRICT
);
~~~

If `region_code` or `account_no` changes on a parent row, `ON UPDATE CASCADE` updates **the corresponding foreign key components** on referencing child rows.

Understand that a composite key identifies the parent row; changing part of it can affect multiple tables. If `region_code` is merely a mutable business attribute, using a stable `account_id bigint PRIMARY KEY` alongside a separate `UNIQUE(region_code, account_no)` avoids wide cascading key updates.

In PostgreSQL, an FK can reference a primary key, a qualifying unique constraint, or columns with a valid non-partial unique index per system rules. You cannot reference a non-unique combination and expect `CASCADE` to locate a single parent row.

## 15. Impact of ON DELETE CASCADE on Transactions and Triggers

Cascading actions execute inside the **same transaction** modifying the parent row:

~~~sql
BEGIN;

DELETE FROM lab_fk.orders WHERE order_id = 1002;

-- Items for order 1002 are gone inside this transaction.
SELECT * FROM lab_fk.order_items WHERE order_id = 1002;

ROLLBACK;
~~~

After rollback, both the order and its items are restored to their pre-transaction state.

PostgreSQL implements FK enforcement via internal mechanisms/triggers, and child row modifications from referential actions interact with other triggers, constraints, and data logic. Consequently:

- If a cascade traverses multiple tables, a constraint failure on one branch causes **the entire statement/transaction to fail**.
- Business triggers on child tables can fire due to cascaded changes, which must be accounted for in audit designs.
- Deleting a heavily referenced parent row can generate substantial writes, WAL, and locks on child tables.
- Never treat cascading as an asynchronous, “eventually consistent”, or background task.

Once a transaction commits, a later rollback cannot undo the cascade. Backups, PITR, or dedicated recovery mechanisms are required if committed data is deleted by mistake.

## 16. TRUNCATE Differs from DELETE: Do Not Confuse Cascading Behavior

`TRUNCATE` does not execute row-by-row `DELETE` operations, so it **does not invoke `ON DELETE` actions like an ordinary `DELETE`**.

For example, when another table references a parent:

~~~sql
TRUNCATE TABLE lab_fk.customers;
~~~

PostgreSQL refuses to truncate the parent table alone if referencing tables are not also included in the truncate command, even if the foreign key declares `ON DELETE CASCADE`.

You may see the syntax:

~~~sql
-- DANGEROUS: illustration only; never run on data you need to keep.
TRUNCATE TABLE lab_fk.customers CASCADE;
~~~

`TRUNCATE ... CASCADE` is a **separate mechanism** that expands truncation to **all dependent tables in their entirety**, rather than deleting only child rows linked to specific deleted parent rows. Its blast radius can be far wider than expected.

**Never use `TRUNCATE CASCADE` as a substitute for `DELETE ... ON DELETE CASCADE`** to remove a few records or execute business deletions. Understand the differences in table scope, triggers, and constraints.

## 17. Choosing ON DELETE by Business Lifecycle

Several common relationships often start with patterns like those below. These are **analytical starting points**, not rigid defaults:

| Relationship | Common Direction | Why |
| --- | --- | --- |
| Order → line items | `ON DELETE CASCADE` for deletable draft orders | Line items have no meaning without their order |
| Customer → paid orders | `RESTRICT` or `NO ACTION` | Prevents losing transaction and invoice history |
| Employee → tasks | `SET NULL` if tasks may be unassigned | Keeps tasks when an employee leaves |
| Category → products | `SET NULL`, `SET DEFAULT`, or `RESTRICT` | Depends on whether products may lose their category |
| Product → historical order lines | Usually `RESTRICT`, retaining product row or full snapshot | Preserves referential integrity and price history |
| Role group → user-role links | Usually `CASCADE` when intentionally deleting a group | Permission links are meaningless without the group |
| Country/region lookup → addresses | Usually `RESTRICT` | Do not delete reference codes actively in use |
| Author → posts | `SET NULL` if anonymous posts are allowed, or `RESTRICT` per policy | Ownership boundary and content preservation |

### Key Questions Before Choosing CASCADE

1. Can child rows **meaningfully exist independently** after the parent disappears?
2. Is deleting the parent even permitted by business rules, or should the parent only be **deactivated**?
3. Do child rows hold history needed for reporting or auditing?
4. Will the cascade pull in other tables or third-party data?
5. Are there triggers, CDC streams, audit logs, or caches that must stay synchronized?
6. Is the volume of linked rows large enough to cause prolonged locks or WAL spikes?

Dangerous deletion behavior usually stems not from bad SQL syntax, but from **overlooking data lifecycle and cascade blast radius**.

## 18. Choosing ON UPDATE by Identifier Key Policy

Before choosing `ON UPDATE`, ask: **does the referenced key genuinely ever need to change?**

If the key is a `bigint GENERATED ... AS IDENTITY`, UUID, or stable technical ID, applications normally **never change primary keys**. In that case, `NO ACTION`/`RESTRICT` is plenty to guard referential integrity.

If the key is a mutable business code—such as a product SKU, department code, or region code—`ON UPDATE CASCADE` can keep child rows linked to the same entity when the code changes.

~~~sql
CREATE TABLE lab_fk.skus (
    sku text PRIMARY KEY,
    label text NOT NULL
);

CREATE TABLE lab_fk.sku_inventory (
    warehouse_id integer NOT NULL,
    sku text NOT NULL REFERENCES lab_fk.skus(sku)
        ON UPDATE CASCADE
        ON DELETE RESTRICT,
    stock_count integer NOT NULL CHECK (stock_count >= 0),
    PRIMARY KEY (warehouse_id, sku)
);
~~~

Still, if the SKU appears in external APIs, contracts, caches, or message queues, an `ON UPDATE CASCADE` inside **one database** only updates FKs managed by PostgreSQL. It **does not automatically update external files, messages, or downstream systems**.

An alternative design:

~~~sql
CREATE TABLE lab_fk.stable_products (
    product_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku text NOT NULL UNIQUE,
    name text NOT NULL
);
~~~

Child tables reference the immutable `product_id`; when `sku` changes, internal FKs do not need to cascade. This is usually simpler for systems where business codes change.

## 19. Soft Deletes Do Not Trigger ON DELETE CASCADE

Many applications mark parent rows deleted instead of removing them physically:

~~~sql
UPDATE lab_fk.customers
SET full_name = full_name
WHERE customer_id = 1;
~~~

This update does not alter the key, so it does not trigger FK `ON UPDATE`. Likewise, with a column:

~~~sql
deleted_at timestamptz
~~~

running:

~~~sql
UPDATE some_table
SET deleted_at = now()
WHERE id = 1;
~~~

is an **UPDATE to a non-key attribute**, not a `DELETE`. `ON DELETE CASCADE` will not delete child rows.

When adopting soft deletes, explicitly define:

- Should child rows stay visible when their parent is soft-deleted?
- Should new links to a soft-deleted parent be blocked?
- Which queries and indexes exclude deleted records?
- When does physical purging happen, and what should FK behavior be at purge time?
- How do you prevent business-level orphan states even though the FK remains valid?

Do not treat `ON DELETE` as a substitute for a soft-delete policy. They operate at two different layers.

## 20. Optimizing Child-Table Indexes

PostgreSQL creates indexes for `PRIMARY KEY` and `UNIQUE` on the parent table, but **does not automatically create indexes on child FK columns**.

Suppose one customer has millions of orders. Deleting or updating `customers.customer_id` requires PostgreSQL to locate any `orders` referencing that key. Without a suitable index on `orders.customer_id`, scanning child rows becomes expensive.

In the lab you can add:

~~~sql
CREATE INDEX idx_lab_fk_orders_customer
    ON lab_fk.orders(customer_id);

CREATE INDEX idx_lab_fk_products_category
    ON lab_fk.products(category_id);

CREATE INDEX idx_lab_fk_tasks_assignee
    ON lab_fk.tasks(assignee_id);

CREATE INDEX idx_lab_fk_items_product
    ON lab_fk.order_items(product_id);
~~~

`order_items` has primary key `(order_id, product_id)`, so its PK index already supports queries filtering with **`order_id` leading**. However, queries filtering on `product_id` alone typically need a separate index considered.

### When Is a Child Index Necessary?

Not every FK strictly needs its own dedicated index. Evaluate:

- Parent/child row counts and key selectivity.
- Frequency of parent key deletes or updates.
- Query filtering and `JOIN`s on the child FK column.
- Index maintenance overhead on writes.
- Whether existing composite indexes already cover the access path.

Use `EXPLAIN` or `EXPLAIN (ANALYZE, BUFFERS)` on representative read queries to inspect plans. `EXPLAIN ANALYZE` executes the SQL statement; never run it casually on production `DELETE`/`UPDATE` statements.

## 21. Locks, Performance, and Transaction Scope

Referential actions are not free. When deleting or updating a parent key:

- PostgreSQL must locate/check affected child rows.
- For `CASCADE`, `SET NULL`, and `SET DEFAULT`, it may update or delete many child rows.
- Those changes generate WAL and touch indexes, triggers, and MVCC state.
- Long transactions hold locks longer, increasing lock waits in other sessions.
- Two sessions touching parent/child tables in opposite orders can hit deadlocks.

Consider a single command:

~~~sql
DELETE FROM lab_fk.categories
WHERE category_id = 10;
~~~

If that category holds millions of products, `SET DEFAULT` must update millions of product rows. Never assume an operation is fast merely because the SQL statement is short.

### Safe Approach for Large Datasets

1. Count or estimate affected child rows beforehand.
2. Verify indexes on FK columns.
3. Identify triggers and downstream dependent tables.
4. Schedule an appropriate window, or design batched migrations/purges if business rules permit.
5. Monitor locks, WAL, I/O, and replication lag.
6. Ensure verified backups, recovery plans, and clear stopping criteria before altering critical data.

**Do not assume a massive cascade can simply be replaced by batched DELETEs without changing business semantics.** Batch cleanup must explicitly preserve consistency, handle concurrent writes, and satisfy FK rules at every step.

## 22. Reading Existing Constraints in PostgreSQL

Before changing `ON DELETE`/`ON UPDATE` behavior, inspect the actual constraints in the database instead of trusting comments in application code.

In `psql`:

~~~text
\d lab_fk.orders
\d lab_fk.order_items
\d lab_fk.products
~~~

`\d` displays columns, indexes, and foreign keys. It is a `psql` meta-command, not standard SQL sent over JDBC.

### Using pg_constraint

~~~sql
SELECT
    n.nspname AS schema_name,
    t.relname AS table_name,
    c.conname AS fk_name,
    pg_get_constraintdef(c.oid) AS fk_definition
FROM pg_constraint AS c
JOIN pg_class AS t
    ON t.oid = c.conrelid
JOIN pg_namespace AS n
    ON n.oid = t.relnamespace
WHERE n.nspname = 'lab_fk'
  AND c.contype = 'f'
ORDER BY t.relname, c.conname;
~~~

`pg_get_constraintdef` returns the PostgreSQL constraint definition, such as:

~~~text
FOREIGN KEY (customer_id) REFERENCES lab_fk.customers(customer_id)
ON UPDATE CASCADE ON DELETE RESTRICT
~~~

To inspect the catalog's raw action codes:

~~~sql
SELECT
    conname,
    confdeltype,
    confupdtype,
    condeferrable,
    condeferred
FROM pg_constraint
WHERE contype = 'f'
  AND connamespace = 'lab_fk'::regnamespace
ORDER BY conname;
~~~

In `pg_constraint`, the action codes are:

| Code | Action |
| --- | --- |
| `a` | NO ACTION |
| `r` | RESTRICT |
| `c` | CASCADE |
| `n` | SET NULL |
| `d` | SET DEFAULT |

`condeferrable` shows whether the FK can be deferred; `condeferred` shows whether it starts deferred or immediate. Do not inspect only action codes while ignoring other constraint attributes.

## 23. Changing ON DELETE or ON UPDATE on an Existing FK

Do not assume there is a direct `ALTER FOREIGN KEY ... ON DELETE ...` command for switching actions. Typically, changing from `NO ACTION` to `CASCADE` or `SET NULL` requires **dropping and recreating the foreign key constraint** with the new definition.

Example changing `lab_fk.tasks` from `SET NULL` to `RESTRICT`:

~~~sql
-- Illustration in the lab schema ONLY; do not run in production
-- without an approved migration plan and data audit.
BEGIN;

ALTER TABLE lab_fk.tasks
    DROP CONSTRAINT fk_tasks_assignee;

ALTER TABLE lab_fk.tasks
    ADD CONSTRAINT fk_tasks_assignee
    FOREIGN KEY (assignee_id)
    REFERENCES lab_fk.employees(employee_id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;

COMMIT;
~~~

After this change, deleting an employee referenced by tasks is rejected instead of unassigning their tasks.

**Checks before doing this in real systems:**

- Is the new constraint valid against existing data?
- Does application logic depend on the old action?
- Are any jobs deleting parents or changing keys concurrently?
- Do triggers, audit logs, or CDC pipelines expect specific propagation behavior?
- What locks and duration will drop/add take on a large table?
- Are rollback/forward-fix plans and migration monitoring ready?

Switching an FK from `RESTRICT` to `CASCADE` is a **business behavior change**: deletions that previously failed will now cascade across data. Review it like a major behavioral migration, not a syntax tweak.

### Adding an FK to Large Tables with NOT VALID

PostgreSQL supports adding an FK without scanning all historical rows at creation time, then validating separately:

~~~sql
-- Syntax example when adding a new FK:
ALTER TABLE lab_fk.tasks
    ADD CONSTRAINT fk_tasks_assignee_new
    FOREIGN KEY (assignee_id)
    REFERENCES lab_fk.employees(employee_id)
    ON DELETE SET NULL
    ON UPDATE CASCADE
    NOT VALID;
~~~

Followed by:

~~~sql
ALTER TABLE lab_fk.tasks
    VALIDATE CONSTRAINT fk_tasks_assignee_new;
~~~

`NOT VALID` does not let new writes bypass the FK: it mainly defers **verifying rows that already existed before the constraint was added**. New writes must still satisfy the constraint per PostgreSQL rules.

The example above creates **an additional constraint** named `fk_tasks_assignee_new` rather than replacing the old one automatically. In real migrations, plan the exact drop/add sequence, privileges, lock levels, and validation window; never add duplicate constraints just to “test it out”. Validation on large tables still consumes resources and should be scheduled carefully.

## 24. Common Mistakes When Using Referential Actions

### 24.1. Mistaking CASCADE for the Default Behavior

The default is `NO ACTION`. PostgreSQL never deletes child rows just because a foreign key exists.

### 24.2. Treating NO ACTION and RESTRICT as Completely Identical

They usually behave identically on simple `DELETE`s, but `NO ACTION` allows deferred checks on deferrable constraints, whereas `RESTRICT` does not defer its restriction check.

### 24.3. Using ON DELETE CASCADE on Long-Lived Historical Data

Deleting a customer can wipe orders or invoices if cascade is configured carelessly. Define archival/soft-delete models and explicit retention policies instead.

### 24.4. Using SET NULL on a NOT NULL FK

When the action tries to set the FK to `NULL`, `NOT NULL` rejects it. Align column nullability with the relationship lifecycle.

### 24.5. Using SET DEFAULT When the Default References No Parent Row

The default value must still satisfy the foreign key. `SET DEFAULT` never creates parent rows or bypasses constraints.

### 24.6. Assuming ON UPDATE CASCADE Copies All Attributes

It propagates **only the referenced key values**, never arbitrarily syncing names, addresses, statuses, or other identically named columns in child tables.

### 24.7. Treating Foreign Keys as Complete Business Invariant Protection

An FK enforces reference existence, not rules like “only draft orders may be deleted”, “issued invoices cannot be canceled”, or “an employee belongs to exactly one active department”. Those need additional constraints, transactions, or application logic.

### 24.8. Forgetting Child-Table Indexes on FKs

Parent deletes/updates and child lookups can slow down as tables grow. Evaluate child-side indexes, especially on columns used to find referencing rows.

### 24.9. Confusing TRUNCATE CASCADE with ON DELETE CASCADE

`TRUNCATE CASCADE` can empty entire dependent tables rather than running row-level `DELETE` semantics.

### 24.10. Forgetting to ROLLBACK During Lab Exercises

A successful `DELETE` that commits modifies the sample data, altering results for later exercises. Use a dedicated database and wrap experiments in transactions that roll back.

### 24.11. Not Handling Aborted Transactions After an FK Error

Inside a transaction, a constraint failure puts the transaction in an aborted state; issue `ROLLBACK` or `ROLLBACK TO SAVEPOINT` before running further commands. Do not keep sending queries and assume PostgreSQL “stopped accepting SQL”.

### 24.12. Inspecting Only the Direct Parent Without Checking the Full Dependency Graph

A cascade can continue through child tables that are parents of other tables, or be blocked by a `RESTRICT` branch elsewhere. Inspect the entire constraint graph.

### 24.13. Using ON UPDATE CASCADE to Mask an Unstable Key Design

If a business key mutates constantly, using a stable internal surrogate key while keeping the mutable business code in a separate unique column is often cleaner.

### 24.14. Relying Only on UI Permissions While Ignoring Database Actions

SQL deletions, background jobs, and admin tools are all governed by FK rules. Operational safety cannot live solely in a UI “Delete” button.

## 25. Review Exercises with Answers

The exercises below use the `lab_fk` schema created and seeded in Section 10, assuming no experimental changes were committed.

### Exercise 1: Why Does Deleting Customer An Fail?

~~~sql
DELETE FROM lab_fk.customers WHERE customer_id = 1;
~~~

**Answer:** Order 1001 references customer 1 and `fk_orders_customer` uses `ON DELETE RESTRICT`. PostgreSQL blocks the deletion with an FK error.

### Exercise 2: Which Items Remain After Deleting Order 1001?

~~~sql
BEGIN;
DELETE FROM lab_fk.orders WHERE order_id = 1001;

SELECT order_id, product_id
FROM lab_fk.order_items
ORDER BY order_id, product_id;
ROLLBACK;
~~~

**Answer:** Inside the transaction, only the item for order 1002 (product 501) remains. Both items for order 1001 are deleted via `ON DELETE CASCADE`. After rollback, the original data returns.

### Exercise 3: Does Deleting Employee Lan Delete Tasks?

~~~sql
BEGIN;
DELETE FROM lab_fk.employees WHERE employee_id = 11;

SELECT task_id, assignee_id
FROM lab_fk.tasks
ORDER BY task_id;
ROLLBACK;
~~~

**Answer:** No. Task 701 survives with `assignee_id = NULL` due to `ON DELETE SET NULL`; task 702 stays `NULL`.

### Exercise 4: What Happens to Product 501 When Category 10 Is Deleted?

~~~sql
BEGIN;
DELETE FROM lab_fk.categories WHERE category_id = 10;

SELECT product_id, category_id
FROM lab_fk.products
ORDER BY product_id;
ROLLBACK;
~~~

**Answer:** Products 501 and 503 move `category_id` to `0`. This is a valid `DEFAULT` value because category `0` exists.

### Exercise 5: Updating Product ID 501 to 601

~~~sql
BEGIN;
UPDATE lab_fk.products
SET product_id = 601
WHERE product_id = 501;

SELECT order_id, product_id
FROM lab_fk.order_items
ORDER BY order_id, product_id;
ROLLBACK;
~~~

**Answer:** Item rows referencing product 501 update to 601 via `ON UPDATE CASCADE`. After rollback, 501 returns.

### Exercise 6: Is Replacing NO ACTION with RESTRICT Always Equivalent?

**Answer:** No. When updating parent and child keys across multiple statements in one transaction, `NO ACTION DEFERRABLE` can defer validation until commit; `RESTRICT` does not allow deferring that restriction check.

### Exercise 7: Should customers → invoices Use ON DELETE CASCADE?

**Suggested answer:** Usually exercise extreme caution because invoices/financial documents must often be retained long-term. Use `RESTRICT`/`NO ACTION`, customer deactivation, and proper archival/anonymization policies. No single action fits every regulatory and business context.

### Exercise 8: Why Does SET NULL Fail on a Required Column?

**Answer:** `ON DELETE SET NULL` attempts to write `NULL` into the FK, which `NOT NULL` rejects. Either the design must allow an unlinked child, or a different action must be chosen.

### Exercise 9: Why Can SET DEFAULT 0 Fail?

**Answer:** If the parent table has no row with key `0` (or another constraint fails), writing `0` to the child violates the FK. A real, business-protected default parent row is required.

### Exercise 10: Behavior When Using TRUNCATE?

**Answer:** `TRUNCATE` does not execute `ON DELETE CASCADE` row by row. It has its own referential rules and `TRUNCATE ... CASCADE` behavior, which truncates entire dependent tables.

### Exercise 11: Should You Create an Index on orders.customer_id?

**Answer:** Worth considering when querying orders by customer or deleting/updating customer keys on large tables. PostgreSQL does not automatically index child FK columns. Exact indexing depends on workload and existing composite indexes.

### Exercise 12: Designing for Frequently Changing Department Codes

**Suggested answer:** If `department_code` is a mutable business code, use a stable `department_id` as the PK and place `UNIQUE` on `department_code`. Employees reference `department_id`, so FKs never need cascading updates when the code changes.

## 26. Process for Choosing ON DELETE / ON UPDATE

When designing a new foreign key, walk through this decision checklist:

1. **Identify the true relationship:** which table is parent and which is child? Can child records exist independently?
2. **Determine minimum requirement:** must the child always have a parent? Should the FK be `NOT NULL` or nullable?
3. **Determine allowed deletions:** is deleting the parent valid in business terms, or must history be retained?
4. **Choose the delete action:** block (`NO ACTION`/`RESTRICT`), delete together (`CASCADE`), unlink (`SET NULL`), or move to a default parent (`SET DEFAULT`).
5. **Determine whether the parent key changes:** if immutable, no cascade needed; if mutable, weigh `ON UPDATE CASCADE` vs. introducing a stable surrogate key.
6. **Cross-check constraints:** are `NOT NULL`, `DEFAULT`, composite FKs, `MATCH`, and uniqueness compatible with the chosen action?
7. **Check deferrability needs:** do transactions need multi-step key swaps? If so, evaluate `NO ACTION DEFERRABLE`.
8. **Trace the dependency graph:** will an action cascade into further tables or interact with triggers/CDC/audits?
9. **Assess load:** are child row counts, FK indexes, locks, WAL, and replication lag acceptable?
10. **Test in a lab database:** use transactions and rollbacks to verify both valid paths and expected rejections.
11. **Document in migration/runbook:** record constraint names, rationale for actions, and how to modify or roll back if rules change.

Without a clear business reason to automatically delete or rewrite child rows, **never choose `CASCADE` just to write less SQL**. First define precisely what data state is allowed to survive after a parent change.

## 27. Summary

`ON DELETE` and `ON UPDATE` are how PostgreSQL enforces part of **relational lifecycle rules** directly in the database.

- **`NO ACTION`:** default; prevents invalid FK states and can defer checks when the constraint is `DEFERRABLE`.
- **`RESTRICT`:** blocks changes to referenced parent rows without deferring the restriction check like `NO ACTION`.
- **`CASCADE`:** deletes child rows or updates child FK values to match parent key updates.
- **`SET NULL`:** keeps child rows while clearing the link, valid only when columns and constraints permit `NULL`.
- **`SET DEFAULT`:** sets the FK to its default value, which **must still be a valid** foreign key reference.

For `ON DELETE`, the decision revolves around **whether child data lives and dies with its parent or must survive independently**. For `ON UPDATE`, it revolves around **whether the referenced key can mutate and whether links must follow**.

Good design always coordinates FK actions with `NOT NULL`, `UNIQUE`, transactions, indexes, privileges, and business rules. That way, even when multiple applications write concurrently or errors occur mid-flow, PostgreSQL preserves the referential invariants your system intentionally defined.
