# FOREIGN KEY, Parent-Child Relationships, and Deletion Behaviors in Oracle Database

In a relational database, an `ORDERS` table typically has a `CUSTOMER_ID` column pointing to the customer who placed the order. An order should not reference a nonexistent customer; at the same time, if a customer is deleted, what should happen to the order data? **`FOREIGN KEY`** is the Oracle Database constraint used to protect these relationships.

Three common ways to handle deleting a **parent table** row in Oracle are:

- **Default — block deletion while referencing child rows exist:** Oracle rejects deleting the parent if doing so violates the foreign key.
- **`ON DELETE CASCADE`:** deleting a parent row automatically deletes referencing child rows.
- **`ON DELETE SET NULL`:** deleting a parent row keeps the child rows, setting their corresponding foreign key column(s) to `NULL`.

This is a data-design decision, not merely a syntax choice. Using `CASCADE` on a customer → invoice relationship means a single accidental `DELETE` can wipe out transaction history. Using `SET NULL` where a parent is mandatory causes application errors or strips records of required context. This lesson explains how to declare, test, and choose the right behavior in Oracle Database.

> Examples use tables prefixed with `DEMO_` and assume a practice schema/PDB. Statements such as `CREATE TABLE`, `INSERT`, `DELETE`, and `ALTER TABLE` modify data or structure; do not run them verbatim in a production schema. Oracle DDL generally performs an implicit commit, so `ROLLBACK` should not be relied upon to undo table creation or alteration statements.

## 1. Parent-Child Relationships in a Relational Database

### 1.1. What Are Parent Tables and Child Tables?

Consider a customer and orders model:

```text
        DEMO_CUSTOMERS (parent table)
        +-------------+-----------+
        | CUSTOMER_ID | FULL_NAME |
        +-------------+-----------+
        | 1           | An        |
        | 2           | Binh      |
        +-------------+-----------+
              |
              | 1 customer has many orders
              |
              v
        DEMO_ORDERS (child table)
        +----------+-------------+--------------+
        | ORDER_ID | CUSTOMER_ID | TOTAL_AMOUNT |
        +----------+-------------+--------------+
        | 101      | 1           | 150000       |
        | 102      | 1           | 200000       |
        | 103      | 2           | 70000        |
        +----------+-------------+--------------+
```

- **Parent:** `DEMO_CUSTOMERS`, with primary key `CUSTOMER_ID`.
- **Child:** `DEMO_ORDERS`, with foreign key `CUSTOMER_ID` referencing the key of `DEMO_CUSTOMERS`.
- **One-to-many (1:N) relationship:** one customer can have many orders; each order in this model links to one customer.
- **Valid reference:** `DEMO_ORDERS.CUSTOMER_ID = 1` is valid when `DEMO_CUSTOMERS.CUSTOMER_ID = 1` exists.

A child row with a non-`NULL` foreign key value must reference an **actual parent key value** when the constraint is checked. Otherwise, Oracle rejects the violating operation, except in special cases such as deferred checking or administratively disabled constraints.

### 1.2. Primary Key, Unique Key, and Foreign Key Differ

| Constraint Type | Placed On | Meaning |
| --- | --- | --- |
| `PRIMARY KEY` | Usually the parent table; can also appear on a child table | Uniquely identifies each row; key columns cannot be `NULL` |
| `UNIQUE` | Can be on either parent or child table | Enforces uniqueness under Oracle rules; can serve as a referenced key |
| `FOREIGN KEY` | Child table | Ensures foreign key values match a valid referenced parent key |

In Oracle, a foreign key must reference a **`PRIMARY KEY` or `UNIQUE` key backed by a proper constraint** on the parent table. It is not enough for the parent column to "look unique" or be checked only in application code.

A foreign key **does not make values unique in the child table**. Many orders can share `CUSTOMER_ID=1`. If you want a one-to-one (1:1) relationship, you may also need `UNIQUE` on the child-side foreign key column along with appropriate `NULL` rules.

### 1.3. FOREIGN KEY Enforces Checks in Two Directions

When operating on the **child** table:

- `INSERT` a child row whose foreign key points to a nonexistent parent: blocked.
- `UPDATE` a child row's foreign key to a value nonexistent in the parent: blocked.
- `DELETE` a child row: generally allowed; does not automatically delete the parent.

When operating on the **parent** table:

- `DELETE` a parent with no related children: generally allowed.
- `DELETE` a parent while children remain: governed by the foreign key's `ON DELETE` policy.
- `UPDATE` a parent key column currently referenced by children: blocked if it creates invalid references; Oracle does not offer a direct `ON UPDATE CASCADE` clause like some other RDBMSs.

In all cases, privileges, other constraints, triggers, transaction state, and operational conditions can also cause operations to fail.

## 2. Creating a Basic Foreign Key in Oracle

### 2.1. Creating the Parent Table with a PRIMARY KEY

```sql
CREATE TABLE demo_customers (
    customer_id NUMBER(10) NOT NULL,
    full_name   VARCHAR2(100) NOT NULL,
    CONSTRAINT pk_demo_customers PRIMARY KEY (customer_id)
);
```

The name `PK_DEMO_CUSTOMERS` makes the constraint easy to identify in metadata and error messages. If you omit constraint names, Oracle generates system names like `SYS_C...`, which are harder to tie back to business rules.

### 2.2. Creating the Child Table with a FOREIGN KEY

```sql
CREATE TABLE demo_orders (
    order_id     NUMBER(10) NOT NULL,
    customer_id  NUMBER(10) NOT NULL,
    total_amount NUMBER(12,2) NOT NULL,
    CONSTRAINT pk_demo_orders PRIMARY KEY (order_id),
    CONSTRAINT fk_demo_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_customers (customer_id)
);
```

In the syntax:

- `FOREIGN KEY (customer_id)`: column(s) on the **child** table.
- `REFERENCES demo_customers(customer_id)`: **parent** table and referenced key column(s).
- Without `ON DELETE ...`: the default parent deletion behavior is **block deletion if referencing children exist**.
- `customer_id NUMBER(10) NOT NULL`: in this example, an order must belong to a customer.

Child and parent columns must have compatible data types for the constraint, and the referenced columns must form a valid parent key. Oracle also supports referencing multi-column unique/primary keys; composite key examples appear later.

### 2.3. Inline Declaration Syntax

When a foreign key has a single column, Oracle also supports inline declaration inside `CREATE TABLE`:

```sql
CREATE TABLE demo_order_notes (
    note_id    NUMBER(10) PRIMARY KEY,
    order_id   NUMBER(10)
               CONSTRAINT fk_demo_note_order
               REFERENCES demo_orders(order_id),
    note_text  VARCHAR2(200)
);
```

Inline syntax is more concise for single-column keys. For **multi-column** foreign keys, use an out-of-line declaration: `CONSTRAINT ... FOREIGN KEY (col1, col2) REFERENCES ...`.

### 2.4. Adding a Foreign Key After the Table Already Exists

If a table was created without the constraint, use `ALTER TABLE ... ADD CONSTRAINT`:

```sql
ALTER TABLE demo_orders
    ADD CONSTRAINT fk_demo_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_customers (customer_id);
```

**Note:** this syntax illustrates the case where the child table **does not yet have** a constraint with that name. If you already ran Section 2.2, the constraint already exists; do not re-run `ADD CONSTRAINT`. On a table with existing rows, Oracle validates existing data when enabling the constraint with `VALIDATE`, and raises an error if any violating rows exist.

You do not create foreign keys on both tables: the constraint lives on the **child table**, yet it controls modifications to the referenced key on the **parent table**.

## 3. Default Behavior: Blocking Parent Deletion While Children Exist

### 3.1. Preparing Data

Using the two tables from Section 2, run:

```sql
INSERT INTO demo_customers (customer_id, full_name)
VALUES (1, 'An');

INSERT INTO demo_customers (customer_id, full_name)
VALUES (2, 'Binh');

INSERT INTO demo_orders (order_id, customer_id, total_amount)
VALUES (101, 1, 150000);

INSERT INTO demo_orders (order_id, customer_id, total_amount)
VALUES (102, 1, 200000);

INSERT INTO demo_orders (order_id, customer_id, total_amount)
VALUES (103, 2, 70000);

COMMIT;
```

Now both orders 101 and 102 reference customer 1.

### 3.2. Deleting the Parent Is Rejected

```sql
DELETE FROM demo_customers
WHERE customer_id = 1;
```

When the default constraint is enabled and checked immediately, Oracle raises an error like:

```text
ORA-02292: integrity constraint (SCHEMA.FK_DEMO_ORDERS_CUSTOMER)
           violated - child record found
```

`SCHEMA` will show your actual schema name. Meaning: Oracle found at least one child row referencing the parent key being deleted. No parent row is deleted by that failed statement.

This protects **referential integrity**: it prevents leaving orders with `CUSTOMER_ID=1` after customer 1 no longer exists.

### 3.3. To Delete the Parent, Handle the Children First

One business approach is controlled deletion:

```sql
SAVEPOINT before_demo_delete;

DELETE FROM demo_orders
WHERE customer_id = 1;

DELETE FROM demo_customers
WHERE customer_id = 1;

-- Inspect after both DELETEs, before COMMIT.
SELECT *
FROM demo_customers
ORDER BY customer_id;

SELECT *
FROM demo_orders
ORDER BY order_id;

-- Undo the DELETEs in this lab test.
ROLLBACK TO before_demo_delete;
```

Before `ROLLBACK`, orders 101 and 102 were deleted first, allowing customer 1 to be deleted. `ROLLBACK TO before_demo_delete` reverts DML changes made after the savepoint, assuming no DDL or `COMMIT` intervened.

**Operation order matters** under immediately checked constraints: process **children first, parent second**. If the business requires retaining orders, do not delete them casually; choose another policy or disallow deleting the customer.

### 3.4. Why Is There No ON DELETE RESTRICT in Oracle Syntax?

Some RDBMSs allow writing `ON DELETE RESTRICT` or `ON DELETE NO ACTION`. For `FOREIGN KEY` constraints in Oracle SQL, the supported deletion-behavior syntax options are:

- Omit `ON DELETE`: uses the default behavior blocking parent deletion when referencing children exist.
- `ON DELETE CASCADE`.
- `ON DELETE SET NULL`.

Do not copy `ON DELETE RESTRICT`, `NO ACTION`, or `SET DEFAULT` from another database's syntax into an Oracle `CREATE TABLE` expecting it to be accepted.

In business discussions, the default behavior is often called "restrict/no action," but that is **not a keyword to write** in an Oracle DDL statement.

## 4. ON DELETE CASCADE: Deleting a Parent Also Deletes Its Children

### 4.1. How to Declare It

Example of departments and members under a policy where **deleting a department also deletes its sample member rows** (suitable for demo data only, not automatically good design for HR records):

```sql
CREATE TABLE demo_departments (
    department_id NUMBER(10) PRIMARY KEY,
    department_name VARCHAR2(100) NOT NULL
);

CREATE TABLE demo_department_members (
    member_id NUMBER(10) PRIMARY KEY,
    department_id NUMBER(10) NOT NULL,
    member_label VARCHAR2(100) NOT NULL,
    CONSTRAINT fk_demo_member_department
        FOREIGN KEY (department_id)
        REFERENCES demo_departments(department_id)
        ON DELETE CASCADE
);
```

Look at the end of the foreign key definition:

```sql
ON DELETE CASCADE
```

This applies when **deleting a parent row** from `DEMO_DEPARTMENTS`; any `DEMO_DEPARTMENT_MEMBERS` rows referencing that parent are deleted by Oracle as well.

### 4.2. Testing the Delete Operation

```sql
INSERT INTO demo_departments VALUES (10, 'Research');
INSERT INTO demo_departments VALUES (20, 'Support');

INSERT INTO demo_department_members VALUES (1001, 10, 'Member A');
INSERT INTO demo_department_members VALUES (1002, 10, 'Member B');
INSERT INTO demo_department_members VALUES (1003, 20, 'Member C');

COMMIT;

SAVEPOINT before_cascade;

DELETE FROM demo_departments
WHERE department_id = 10;

SELECT member_id, department_id, member_label
FROM demo_department_members
ORDER BY member_id;

ROLLBACK TO before_cascade;
```

After the `DELETE`, within the same transaction, member rows **1001** and **1002** disappear because they referenced department 10; member **1003** in department 20 remains. After `ROLLBACK TO before_cascade`, the data returns to its pre-test state.

Important implication:

> With `ON DELETE CASCADE`, a single `DELETE FROM parent ...` statement can delete **many child rows** even though the statement never explicitly mentions `DELETE FROM child`.

### 4.3. Cascading Can Span Multiple Levels

Consider this hierarchy:

```text
DEMO_CUSTOMERS
     |
     | FK on ORDERS: ON DELETE CASCADE
     v
DEMO_ORDERS
     |
     | FK on ORDER_ITEMS: ON DELETE CASCADE
     v
DEMO_ORDER_ITEMS
```

If both foreign keys use `ON DELETE CASCADE`, deleting a customer deletes that customer's orders, which in turn deletes the order items belonging to those orders.

A standalone DDL example illustrating this chain (using distinct table names so earlier tables remain untouched):

```sql
CREATE TABLE demo_sales_customers (
    customer_id NUMBER PRIMARY KEY
);

CREATE TABLE demo_sales_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER NOT NULL,
    CONSTRAINT fk_demo_sales_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_sales_customers(customer_id)
        ON DELETE CASCADE
);

CREATE TABLE demo_sales_order_items (
    item_id NUMBER PRIMARY KEY,
    order_id NUMBER NOT NULL,
    quantity NUMBER NOT NULL,
    CONSTRAINT fk_demo_sales_item_order
        FOREIGN KEY (order_id)
        REFERENCES demo_sales_orders(order_id)
        ON DELETE CASCADE
);
```

With this design, deleting a `DEMO_SALES_CUSTOMERS` row that has child data also deletes its related orders and line items.

This is convenient for data **whose lifecycle strictly depends on the parent**, such as detail lines of a temporary staging record. However, for invoices, payment logs, or records subject to legal/compliance retention, cascading deletes are usually inappropriate.

### 4.4. Operational Impacts of CASCADE

When using `CASCADE`, watch out for:

- **Number of affected rows:** child row counts can be vastly larger than the number of parent rows the application explicitly deletes.
- **Redo and undo:** Oracle must record all changes for recovery/rollback; a large delete can consume significant I/O and undo space.
- **Locks and concurrent transactions:** related rows and structures must be protected under Oracle's concurrency mechanisms.
- **Triggers:** cascading DML may fire applicable triggers per Oracle rules, introducing side effects or extra business logic.
- **Dependency chains:** evaluate the entire foreign key tree, not just one direct child table.
- **Execution time:** a short SQL statement on the parent does not mean low database cost.

If data is governed by audit, retention, or business recovery requirements, explicitly design archival, controlled cleanup, or logical deactivation (soft delete) instead of choosing CASCADE simply for brevity.

### 4.5. CASCADE Does Not Delete the Parent When Deleting a Child

`ON DELETE CASCADE` works in one direction:

```text
DELETE parent  --->  Oracle DELETEs referencing children
DELETE child   -X->  Does NOT automatically DELETE parent
```

Deleting a `DEMO_DEPARTMENT_MEMBERS` row leaves its corresponding department intact. Foreign keys have no automatic "clean up childless parents" behavior.

## 5. ON DELETE SET NULL: Keeping Children and Detaching the Parent Link

### 5.1. Suitable Model

Suppose a task can be assigned to a project, yet still remains meaningful if that project is deleted. In that case, `DEMO_TASKS` can allow `PROJECT_ID` to be `NULL`.

```sql
CREATE TABLE demo_projects (
    project_id NUMBER(10) PRIMARY KEY,
    project_name VARCHAR2(100) NOT NULL
);

CREATE TABLE demo_tasks (
    task_id NUMBER(10) PRIMARY KEY,
    project_id NUMBER(10),
    task_title VARCHAR2(150) NOT NULL,
    CONSTRAINT fk_demo_task_project
        FOREIGN KEY (project_id)
        REFERENCES demo_projects(project_id)
        ON DELETE SET NULL
);
```

Notice: `PROJECT_ID` **must not be declared `NOT NULL`**. If Oracle needs to set it to `NULL` when deleting a parent, the column must allow `NULL`.

### 5.2. Testing Project Deletion

```sql
INSERT INTO demo_projects (project_id, project_name)
VALUES (50, 'Internal Portal');

INSERT INTO demo_tasks (task_id, project_id, task_title)
VALUES (501, 50, 'Write documentation');

INSERT INTO demo_tasks (task_id, project_id, task_title)
VALUES (502, 50, 'Review UI');

COMMIT;

SAVEPOINT before_set_null;

DELETE FROM demo_projects
WHERE project_id = 50;

SELECT task_id, project_id, task_title
FROM demo_tasks
ORDER BY task_id;

ROLLBACK TO before_set_null;
```

After deleting the parent and before rolling back:

```text
TASK_ID  PROJECT_ID  TASK_TITLE
-------  ----------  -------------------
501      NULL        Write documentation
502      NULL        Review UI
```

The two task rows **are not deleted**; Oracle updates their `PROJECT_ID` foreign key to `NULL`. After rollback, the project and links are restored within the practice transaction.

### 5.3. What Does SET NULL Mean in Business Terms?

`NULL` in a foreign key column can represent:

- A task not yet assigned to a project.
- A link that no longer applies.
- A former parent that was deleted while the system required retaining child data.

However, `NULL` **does not explain why** it is null, nor does it preserve the deleted parent's ID or name. If you need to know which project a task previously belonged to, record history or audit logs separately.

Do not use `SET NULL` in models where a child **must always belong to a parent**, such as a payment that must always be tied to a valid invoice by business rule.

### 5.4. What If the Foreign Key Column Is NOT NULL?

Suppose `DEMO_TASKS.PROJECT_ID` is declared `NOT NULL` while the FK is `ON DELETE SET NULL`. When deleting a project that has tasks, Oracle attempts to set `PROJECT_ID` to `NULL` to satisfy the FK policy, which violates the `NOT NULL` constraint.

Consequently, the operation **fails with a null-constraint violation** (such as `ORA-01407`) instead of succeeding. During design, `SET NULL` must be consistent with all `NOT NULL`, `CHECK`, and other constraints on the child table.

### 5.5. SET NULL Is Not Orphaned Data

A child row with `PROJECT_ID=NULL` **is not an invalid reference to a nonexistent parent** under SQL semantics for a single-column nullable FK. It simply has **no parent link**.

By contrast, a child row with `PROJECT_ID=50` when `DEMO_PROJECTS.PROJECT_ID=50` no longer exists is an invalid reference if the constraint is enabled and validated.

This distinction matters in reporting:

```sql
SELECT COUNT(*) AS unassigned_tasks
FROM demo_tasks
WHERE project_id IS NULL;
```

This query counts tasks with no linked project; do not assume they are "corrupt data."

## 6. Comparing the Three ON DELETE Options

| Criterion | Default (no ON DELETE clause) | `ON DELETE CASCADE` | `ON DELETE SET NULL` |
| --- | --- | --- | --- |
| When parent has no children | Deletes parent | Deletes parent | Deletes parent |
| When parent still has children | **Blocks parent deletion** if it violates FK | **Deletes related children**, then deletes parent | **Keeps children**, sets FK to `NULL` |
| Do child records survive? | Yes, because parent delete fails | No children referencing deleted parent remain | Yes |
| Must FK column be nullable? | Not required | Not required | **Yes**, if parent deletion with children must succeed |
| Business risk | Cannot delete parent before handling children | Cascading delete may wipe out critical data | Loses historical link; callers must handle `NULL` semantics |
| Best suited for | Orders/invoices needing strict referential preservation | Data wholly dependent on the parent | Optional links where children remain meaningful independently |

### 6.1. Choosing Based on Business Relationship

**Choose the default** if a child row **cannot legitimately exist without its parent**, and parent deletion must be explicitly controlled by users or workflows. Example: disallow deleting a customer who still has active contracts.

**Choose `CASCADE`** if child rows are truly **part of the parent's lifecycle** and have no value once the parent disappears. Example: temporary configuration lines or detail lines of a draft record (when retention policy permits deletion).

**Choose `SET NULL`** if child rows can continue existing **unattached to a parent**, and the application supports an unassigned/unlinked state. Example: tasks that remain valid after an experimental project is removed.

**Never pick a behavior out of habit.** Ask: if a user deletes the parent, must child data still be retrievable for reporting, auditing, reconciliation, or legal compliance?

### 6.2. What If Physical Deletion Should Be Avoided Altogether?

Some domains prefer retiring parent rows while keeping full history. You can design a **soft delete**:

```sql
ALTER TABLE demo_customers
ADD (is_active CHAR(1) DEFAULT 'Y' NOT NULL);

ALTER TABLE demo_customers
ADD CONSTRAINT chk_demo_customer_active
    CHECK (is_active IN ('Y', 'N'));
```

Then replace physical deletion with a status update:

```sql
UPDATE demo_customers
SET is_active = 'N'
WHERE customer_id = 1;
```

This preserves the parent row and all FK references. However, the application must consistently filter/display inactive records, handle uniqueness rules, and manage archival policies. Soft delete is a custom business pattern—**not an Oracle `ON DELETE` option**.

## 7. Foreign Keys with NULL and Composite Keys

### 7.1. A FOREIGN KEY Can Allow NULL

Consider a child table:

```sql
CREATE TABLE demo_optional_contacts (
    contact_id   NUMBER PRIMARY KEY,
    customer_id  NUMBER,
    contact_name VARCHAR2(100),
    CONSTRAINT fk_demo_contact_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_customers(customer_id)
);
```

Because `CUSTOMER_ID` lacks `NOT NULL`, the following values are valid from a foreign-key standpoint:

- `CUSTOMER_ID = 1` when parent row 1 exists.
- `CUSTOMER_ID = 2` when parent row 2 exists.
- `CUSTOMER_ID = NULL` when the contact is not yet linked to a customer.

`CUSTOMER_ID = 9999` is rejected if parent 9999 does not exist while the constraint is enabled and checked immediately.

If the business requires every contact to belong to a customer, add `NOT NULL` to the child column.

### 7.2. Composite Foreign Keys (Multi-Column FKs)

Some tables use a multi-column parent key—for example, warehouse codes that are unique only per region:

```sql
CREATE TABLE demo_warehouses (
    region_id     NUMBER(10) NOT NULL,
    warehouse_id  NUMBER(10) NOT NULL,
    warehouse_name VARCHAR2(100),
    CONSTRAINT pk_demo_warehouses
        PRIMARY KEY (region_id, warehouse_id)
);

CREATE TABLE demo_stock_moves (
    move_id      NUMBER(10) PRIMARY KEY,
    region_id    NUMBER(10),
    warehouse_id NUMBER(10),
    quantity     NUMBER(10) NOT NULL,
    CONSTRAINT fk_demo_move_warehouse
        FOREIGN KEY (region_id, warehouse_id)
        REFERENCES demo_warehouses(region_id, warehouse_id)
        ON DELETE SET NULL
);
```

With composite keys, **child column order must match the referenced parent key column order**. A region + warehouse value is validated as a pair, not as two independent constraints.

### 7.3. Composite Keys Containing NULL

In Oracle, for a composite foreign key, if **one or more FK components are `NULL`**, referential checking follows different rules from when all components are non-`NULL`. As a result, a partially null combination may not require matching a full parent row the way a complete key pair does.

If the business requires **either both columns populated or both NULL**, add a check constraint:

```sql
ALTER TABLE demo_stock_moves
ADD CONSTRAINT chk_demo_warehouse_pair
CHECK (
    (region_id IS NULL AND warehouse_id IS NULL)
    OR
    (region_id IS NOT NULL AND warehouse_id IS NOT NULL)
);
```

When using `ON DELETE SET NULL` on a composite key, ensure the FK columns allow null as intended, and confirm that nullifying the link fits the data model.

### 7.4. Self-Referencing Foreign Keys

A table can be both **parent and child of itself**, such as employees referencing a manager or organizational units referencing a parent unit:

```sql
CREATE TABLE demo_org_units (
    unit_id        NUMBER PRIMARY KEY,
    parent_unit_id NUMBER,
    unit_name      VARCHAR2(100) NOT NULL,
    CONSTRAINT fk_demo_org_parent
        FOREIGN KEY (parent_unit_id)
        REFERENCES demo_org_units(unit_id)
        ON DELETE SET NULL
);
```

In this example, deleting a parent unit leaves direct child units intact with their parent link cleared. If you choose `CASCADE` on a hierarchy, carefully assess cascading deletion across the entire subtree.

A self-referencing foreign key by itself **does not prevent complex logical cycles** in a hierarchy. If the application requires an acyclic graph, add checks in the business layer or a dedicated mechanism.

## 8. Common Oracle Errors with FOREIGN KEY

### 8.1. ORA-02291: parent key not found

Example:

```sql
INSERT INTO demo_orders (order_id, customer_id, total_amount)
VALUES (104, 9999, 100000);
```

If customer 9999 does not exist, Oracle raises:

```text
ORA-02291: integrity constraint (...) violated - parent key not found
```

**Meaning:** a child row was inserted or updated with a foreign key value lacking a valid parent.

Troubleshooting steps:

1. Verify whether `CUSTOMER_ID` has the expected value.
2. Verify the parent row exists in the **right schema/PDB**.
3. If inside a transaction, check parent/child creation order and commit/visibility state.
4. Never disable the FK just to let an invalid row pass validation.

### 8.2. ORA-02292: child record found

Example:

```sql
DELETE FROM demo_customers WHERE customer_id = 1;
```

When orders still point to customer 1 and the default FK is active:

```text
ORA-02292: integrity constraint (...) violated - child record found
```

**Meaning:** one or more child rows still reference the parent key being deleted/updated.

Troubleshooting steps:

1. Identify the exact constraint named in the error.
2. Query metadata to find the child table and FK columns.
3. Inspect the actual child rows.
4. Apply the right business policy: retain the parent, handle children in a controlled manner, or redesign `ON DELETE` if genuinely appropriate.

Never treat `ORA-02292` as a technical bug to "turn off" via `DISABLE CONSTRAINT`. It usually indicates the data protection mechanism is working properly.

### 8.3. ORA-02270: no matching unique or primary key

This error occurs when creating an FK referencing a parent column or column set **not protected by an appropriate `PRIMARY KEY` or `UNIQUE` constraint**.

For example, the parent table has `CATEGORY_NAME` without `UNIQUE`, and a child table tries to reference it. Even if the application believes category names never duplicate, Oracle has no valid parent key constraint to bind against.

The fix is to identify the true candidate key, add the proper parent constraint (once existing data satisfies uniqueness), and then create the FK.

### 8.4. ORA-02298 When Enabling Validation on Existing Data

If a child table already contains invalid references because a constraint was previously disabled or unvalidated, running `ENABLE VALIDATE` fails:

```text
ORA-02298: cannot validate (...) - parent keys not found
```

Identify and clean up orphan child rows according to data policy; never assume adding an FK will automatically repair legacy data.

### 8.5. Other Errors Are Not Always Directly FK Violations

An `ON DELETE SET NULL` operation can fail due to a child `NOT NULL` column, triggers, `CHECK` constraints, or storage/transaction conditions. When a `DELETE` fails, read the **actual error code**, constraint name, and logs rather than assuming every parent-delete failure is `ORA-02292`.

## 9. Impact of FOREIGN KEY on Performance and Locking

### 9.1. Oracle Does Not Automatically Index Foreign Key Columns

When you declare:

```sql
CONSTRAINT fk_demo_orders_customer
FOREIGN KEY (customer_id)
REFERENCES demo_customers(customer_id)
```

Oracle **does not automatically create an index on `DEMO_ORDERS.CUSTOMER_ID` just because an FK exists**. In many workloads, DBAs consider adding an index:

```sql
CREATE INDEX idx_demo_orders_customer
ON demo_orders(customer_id);
```

This index can help:

- Locate children of a given parent, e.g., `WHERE customer_id = :id`.
- Verify references when deleting a parent or updating a parent key.
- Reduce full child-table scans and unnecessary locking/contention in concurrent workloads.
- Speed up parent-child join queries when the optimizer chooses an index path.

However, **not every FK requires its own index**. If the child table is tiny, rarely updated, or already has a composite index leading with the FK column, a new index may offer negligible benefit while increasing `INSERT`/`UPDATE`/`DELETE` overhead.

### 9.2. Missing FK Indexes Can Affect Concurrency

In certain scenarios where Oracle must protect referential integrity during parent-key operations, lacking a suitable index on the child FK can trigger expensive checks or table-level locking behavior on the child table that contends with concurrent transactions.

Example:

- Transaction A is about to delete a customer.
- Transaction B is inserting many orders into the child table.
- Oracle must maintain consistent FK verification between both transactions.

Exact wait behavior depends on Oracle release, DML type, indexes, isolation, and load. Never conclude a `DELETE` is slow solely because "the FK lacks an index"; examine execution plans, wait events, locking, and actual data.

### 9.3. Cascade Delete Can Remove Vast Numbers of Rows

`ON DELETE CASCADE` can expand deleting a single parent row into deleting thousands or millions of child rows, which:

- Generates substantial **undo/redo** and I/O.
- Extends transaction duration and lock hold times.
- Makes business-level recovery harder after accidental deletion.
- Impacts triggers, materialized view logs, replication, and downstream jobs depending on configuration.

For large datasets, establish maintenance strategies and check blast radius before deleting. Avoid running cascading deletes in production merely because the SQL syntax looks simple.

### 9.4. Counting Children Before Deleting

To inspect the scope for a given customer:

```sql
SELECT customer_id, COUNT(*) AS order_count
FROM demo_orders
WHERE customer_id = 1
GROUP BY customer_id;
```

Across multi-level hierarchies, count downstream child tables too. A point-in-time count **does not guarantee the exact same count at delete time**, because other sessions may continue writing data. For critical operations, define explicit transaction workflows and concurrency/locking controls.

## 10. Foreign Keys, Transactions, and DEFERRABLE

### 10.1. Normally Oracle Checks Immediately

Constraints created without special options default to **`NOT DEFERRABLE`**: Oracle validates integrity at statement execution time under standard constraint rules.

For example, trying to insert an order for a nonexistent customer:

```sql
INSERT INTO demo_orders (order_id, customer_id, total_amount)
VALUES (105, 500, 250000);
```

This fails immediately because customer 500 does not exist. Even if the application intends to insert customer 500 in the very next SQL statement, a standard FK does not permit temporary broken references.

### 10.2. DEFERRABLE Allows Deferring Checks Appropriately

For complex data-ingestion workflows, Oracle supports **`DEFERRABLE`** constraints, allowing validation to be deferred until commit time when the transaction places the constraint in deferred mode.

Example using a dedicated pair of lesson tables:

```sql
CREATE TABLE demo_import_parents (
    parent_id NUMBER PRIMARY KEY
);

CREATE TABLE demo_import_children (
    child_id NUMBER PRIMARY KEY,
    parent_id NUMBER NOT NULL,
    CONSTRAINT fk_demo_import_parent
        FOREIGN KEY (parent_id)
        REFERENCES demo_import_parents(parent_id)
        DEFERRABLE INITIALLY IMMEDIATE
);
```

Within a transaction, you can switch the checking mode of a constraint declared deferrable:

```sql
SET CONSTRAINTS fk_demo_import_parent DEFERRED;

INSERT INTO demo_import_children (child_id, parent_id)
VALUES (1, 900);

INSERT INTO demo_import_parents (parent_id)
VALUES (900);

COMMIT;
```

Because the parent row is inserted **before COMMIT**, the final transaction state satisfies the FK at deferred check time. If the parent is still missing at commit time, Oracle raises an error and the transaction must be handled per policy; deferring checks does not mean bypassing the constraint.

**Note:** a constraint declared `NOT DEFERRABLE` cannot be made deferred via `SET CONSTRAINTS`. Deferrability is part of the constraint's initial design.

### 10.3. DEFERRABLE Does Not Replace ON DELETE CASCADE

These two options answer different questions:

- **`ON DELETE CASCADE` / `SET NULL`:** when a parent is deleted, what happens to its children?
- **`DEFERRABLE`:** can constraint checking be postponed until commit?

Never infer cascading delete behavior from `DEFERRABLE`, and never infer temporary constraint violations until commit from `CASCADE`.

### 10.4. DDL Performs an Implicit Commit

Creating, dropping, or altering constraints via `CREATE TABLE` and `ALTER TABLE` is **DDL**. Oracle normally executes an implicit commit before and after successful DDL statements. Therefore:

- `ROLLBACK` can undo uncommitted `INSERT`/`UPDATE`/`DELETE` statements.
- `ROLLBACK` **cannot undo executed `CREATE TABLE` or `ALTER TABLE` statements**.
- When practicing, separate schema setup from transaction and savepoint experiments.

This is why examples in this lesson create tables first, and only afterward use `SAVEPOINT` and `ROLLBACK TO` to observe delete behavior on sample rows.

## 11. Inspecting Foreign Key Metadata via Data Dictionary Views

The following queries are **read-only**. Run them in the proper PDB/schema; metadata visibility depends on privileges. Useful views include:

| View | Purpose |
| --- | --- |
| `USER_CONSTRAINTS` | Constraints in the currently connected schema |
| `USER_CONS_COLUMNS` | Columns participating in constraints in the current schema |
| `ALL_CONSTRAINTS` | Constraint metadata the user is permitted to view |
| `ALL_CONS_COLUMNS` | Corresponding constraint column metadata |
| `DBA_CONSTRAINTS` / `DBA_CONS_COLUMNS` | Container-wide metadata with administrative privileges |
| `CDB_CONSTRAINTS` | Constraint metadata across containers when authorized at root |

### 11.1. Listing FKs in the Current Schema

```sql
SELECT constraint_name,
       table_name,
       r_constraint_name,
       delete_rule,
       status,
       validated,
       deferrable,
       deferred
FROM   user_constraints
WHERE  constraint_type = 'R'
ORDER  BY table_name, constraint_name;
```

Key columns:

- `CONSTRAINT_TYPE='R'`: Referential integrity constraint — foreign key.
- `TABLE_NAME`: name of the **child table** holding the FK.
- `R_CONSTRAINT_NAME`: name of the referenced parent key constraint (`PRIMARY KEY` or `UNIQUE`), not the parent table name.
- `DELETE_RULE`: typically `NO ACTION`, `CASCADE`, or `SET NULL` in Oracle metadata. **`NO ACTION` in metadata does not mean the `ON DELETE NO ACTION` keyword is supported in FK creation syntax.**
- `STATUS`: `ENABLED` or `DISABLED`.
- `VALIDATED`: reflects whether data has been validated against the constraint.
- `DEFERRABLE` and `DEFERRED`: reflect deferrability and default checking mode.

### 11.2. Joining Child Tables to Parent Tables

Using metadata accessible via `ALL_CONSTRAINTS`:

```sql
SELECT child.owner           AS child_owner,
       child.table_name      AS child_table,
       child.constraint_name AS foreign_key_name,
       parent.owner          AS parent_owner,
       parent.table_name     AS parent_table,
       child.delete_rule,
       child.status
FROM   all_constraints child
JOIN   all_constraints parent
       ON parent.owner = child.r_owner
      AND parent.constraint_name = child.r_constraint_name
WHERE  child.constraint_type = 'R'
AND    child.owner = USER
ORDER  BY child.table_name, child.constraint_name;
```

The join uses `R_OWNER` and `R_CONSTRAINT_NAME` to locate the **parent key constraint**, because an FK targets a PK/UK constraint on the parent table.

If a query returns no tables, you may be in the wrong schema/PDB or lack privileges to view the metadata; do not conclude no FKs exist in the entire database.

### 11.3. Viewing Corresponding Child and Parent Columns

```sql
SELECT child.owner           AS child_owner,
       child.table_name      AS child_table,
       child_col.column_name AS child_column,
       parent.owner          AS parent_owner,
       parent.table_name     AS parent_table,
       parent_col.column_name AS parent_column,
       child_col.position    AS key_position,
       child.delete_rule
FROM   all_constraints child
JOIN   all_cons_columns child_col
       ON child_col.owner = child.owner
      AND child_col.constraint_name = child.constraint_name
JOIN   all_constraints parent
       ON parent.owner = child.r_owner
      AND parent.constraint_name = child.r_constraint_name
JOIN   all_cons_columns parent_col
       ON parent_col.owner = parent.owner
      AND parent_col.constraint_name = parent.constraint_name
      AND parent_col.position = child_col.position
WHERE  child.constraint_type = 'R'
AND    child.owner = USER
ORDER  BY child.table_name,
          child.constraint_name,
          child_col.position;
```

This query is especially useful for **composite FKs**: `POSITION` pairs each child column with its corresponding parent column in exact order. When a child table has multiple FKs, distinguish them by `CONSTRAINT_NAME`, not just `TABLE_NAME`.

### 11.4. Distinguishing ENABLE/DISABLE and VALIDATE/NOVALIDATE

In Oracle administration, constraint states include:

- **`ENABLE VALIDATE`:** the constraint is enabled and existing data has been verified; new operations must also comply.
- **`ENABLE NOVALIDATE`:** Oracle may not have verified all legacy rows as `VALIDATE` does, while enforcing rules on new operations per this mode.
- **`DISABLE`:** the constraint is not enforced the way an enabled constraint is; invalid references can be introduced if processes do not guard against them.

Never assume all existing rows are valid merely because `STATUS='ENABLED'`; inspect `VALIDATED` and administrative history. And never toggle FKs off/on in production simply to bypass a business data error.

## 12. Changing the Delete Behavior of an Existing FK

### 12.1. Can You Directly ALTER ON DELETE?

In Oracle practice, to switch from the default behavior to `ON DELETE CASCADE` or `SET NULL`, the clean approach is to **drop the old FK constraint and recreate it with the desired option**. Do not assume `ON DELETE` can be altered directly in place via `ALTER CONSTRAINT ... ON DELETE ...`.

**Illustrative example** on `DEMO_ORDERS`:

```sql
-- DDL operation: perform only after assessing data,
-- constraints, applications, and cascading delete effects.
ALTER TABLE demo_orders
    DROP CONSTRAINT fk_demo_orders_customer;

ALTER TABLE demo_orders
    ADD CONSTRAINT fk_demo_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES demo_customers(customer_id)
        ON DELETE CASCADE;
```

After this change, deleting a customer who has orders behaves very differently from the original example. **Do not run these commands simply to work around `ORA-02292`** without agreeing on deletion policy with the data owner.

### 12.2. What to Assess Before Changing the Policy

1. **Business relationship:** do child rows still have standalone value if the parent is deleted?
2. **Existing data:** are there FK violations or invalid rows that must be fixed before validation?
3. **Cascading blast radius:** will child tables of the child table also cascade or block?
4. **Compliance and history:** must data be retained for audit, tax, contractual, or security reasons?
5. **Load and transactions:** row counts, undo/redo volume, execution time, and locking.
6. **Indexes:** do the child FK columns already have appropriate indexes?
7. **Recoverability:** backups, flashback, and recovery procedures if a delete goes wrong.
8. **Deployment timing:** DDL performs implicit commits and can affect running applications.

When replacing a constraint, review existing attributes such as constraint name, deferrability, validation state, privileges, and dependencies; do not just copy `FOREIGN KEY ... REFERENCES` and accidentally drop critical settings.

## 13. Handling Parent Deletion Requests in Applications

An API exposing a "Delete Customer" action should align with whichever policy the database enforces before calling `DELETE`.

### 13.1. With Default Behavior

A typical business flow looks like:

```text
[User requests Customer deletion]
            |
            v
[Check related contracts/orders]
            |
      +-----+------+
      |            |
   Has children   No children
      |            |
      v            v
[Block & report] [DELETE Customer]
      |            |
      +-----+------+
            |
         [Response]
```

Even if the application counts zero children, another session could insert a new child row before `DELETE` runs. **Database constraints remain the final defense** against race conditions; the application should catch `ORA-02292` and return a clear business-level message.

### 13.2. With CASCADE

The API must make it clear that deleting the parent also deletes its children. If multiple levels are involved, consider:

- Displaying or estimating the number of records likely to be deleted.
- Verifying permissions commensurate with the impact.
- Running inside managed transactions and monitoring duration/volume.
- Recording audit logs as required.
- Defining error handling and rollback behavior if the transaction fails.

Do not rely solely on a single successful `DELETE` to know all side effects if the schema has additional constraints, triggers, or logic; review the full data design.

### 13.3. With SET NULL

APIs and UIs must accept that after deleting a parent:

- Child rows remain.
- The foreign key column becomes `NULL`.
- `INNER JOIN` queries between child and parent will no longer return unlinked children.
- Reports needing to include those child rows may require `LEFT JOIN` and `NULL` handling.

Example:

```sql
SELECT t.task_id,
       t.task_title,
       p.project_name
FROM demo_tasks t
LEFT JOIN demo_projects p
       ON p.project_id = t.project_id
ORDER BY t.task_id;
```

When `PROJECT_ID` is `NULL`, `PROJECT_NAME` is also `NULL` in the `LEFT JOIN` output, yet the task row still appears.

## 14. Hands-On Lab: Testing Each Deletion Policy

The goal is to observe the difference among all three behaviors directly **in a learning schema**, without touching production data. Create the tables from Sections 2, 4, and 5 before running the corresponding exercises.

### Exercise 1 — Default: Parent Blocked

1. Create `DEMO_CUSTOMERS` and `DEMO_ORDERS` with an FK that has no `ON DELETE` clause.
2. Insert customer 1 and two orders referencing that customer.
3. Try `DELETE FROM demo_customers WHERE customer_id = 1`.
4. Observe `ORA-02292` and confirm both parent and child rows remain intact.

Inspection query:

```sql
SELECT customer_id, COUNT(*) AS order_count
FROM demo_orders
WHERE customer_id = 1
GROUP BY customer_id;
```

**Question:** Why can deleting another customer who has no orders succeed? Because there are no child references to protect.

### Exercise 2 — CASCADE: Deleting Parent Deletes Children

Using `DEMO_DEPARTMENTS` and `DEMO_DEPARTMENT_MEMBERS`:

```sql
SAVEPOINT test_cascade;

DELETE FROM demo_departments
WHERE department_id = 10;

SELECT *
FROM demo_department_members
WHERE department_id = 10;

ROLLBACK TO test_cascade;
```

**Expected:** after `DELETE`, no members with `DEPARTMENT_ID=10` remain; after rollback, the members return.

### Exercise 3 — SET NULL: Children Are Preserved

Using `DEMO_PROJECTS` and `DEMO_TASKS`:

```sql
SAVEPOINT test_set_null;

DELETE FROM demo_projects
WHERE project_id = 50;

SELECT task_id, project_id
FROM demo_tasks
WHERE task_id IN (501, 502)
ORDER BY task_id;

ROLLBACK TO test_set_null;
```

**Expected:** `PROJECT_ID` on tasks 501 and 502 temporarily becomes `NULL`; after rollback, they return to 50.

### Exercise 4 — Querying Metadata

After creating the constraints:

```sql
SELECT table_name,
       constraint_name,
       delete_rule
FROM user_constraints
WHERE constraint_type = 'R'
AND   table_name IN (
        'DEMO_ORDERS',
        'DEMO_DEPARTMENT_MEMBERS',
        'DEMO_TASKS'
      )
ORDER BY table_name;
```

**Goal:** compare `DELETE_RULE` across the three FKs. Oracle displays `NO ACTION` for the default behavior, and `CASCADE` and `SET NULL` for the two explicit configurations.

### Exercise 5 — Verifying FKs Do Not Auto-Create Indexes

Query index metadata on the child table:

```sql
SELECT index_name, table_name, uniqueness
FROM user_indexes
WHERE table_name = 'DEMO_ORDERS'
ORDER BY index_name;
```

The existence of an index backing `PRIMARY KEY (ORDER_ID)` **does not mean** `CUSTOMER_ID` is indexed. To see which columns each index contains, query `USER_IND_COLUMNS`:

```sql
SELECT index_name,
       column_name,
       column_position
FROM user_ind_columns
WHERE table_name = 'DEMO_ORDERS'
ORDER BY index_name, column_position;
```

This is a read-only observation query; you do not need to create indexes on every FK in this lab unless conducting a specific performance measurement.

## 15. Common Misconceptions

**"Having a FOREIGN KEY means Oracle automatically deletes child rows when the parent is deleted."**  
No. Oracle only deletes children under an explicit `ON DELETE CASCADE` policy. Without an `ON DELETE` clause, deleting a parent that still has children is blocked.

**"ON DELETE CASCADE can automatically delete the parent when a child is deleted."**  
No. Cascading applies when **deleting the parent**. Deleting a child never deletes the parent.

**"SET NULL still works even if the FK column is NOT NULL."**  
No. If Oracle attempts to set the FK to null while `NOT NULL` forbids it, the delete fails with a constraint violation.

**"A FOREIGN KEY automatically creates an index on the child column."**  
No. Oracle requires a valid parent key constraint, but does not automatically create indexes on child FK columns. DBAs evaluate FK indexes based on workload.

**"A FOREIGN KEY guarantees the child column has no duplicates."**  
No. Many children can reference the same parent. Add `UNIQUE` if the business requires each value to appear at most once in the child table.

**"You can write ON UPDATE CASCADE just like ON DELETE CASCADE."**  
Oracle SQL does not provide an `ON UPDATE CASCADE` clause for FKs. Prefer immutable parent keys and design a dedicated workflow if key updates are ever truly required.

**"`ORA-02292` is a technical error you should fix with DISABLE constraint."**  
No. It usually means a delete violates the data model. Handle the parent-child relationship or business workflow rather than disabling data protection.

**"Using SET NULL preserves historical relationships."**  
No. `SET NULL` **clears the current link**. If you need to know which parent previously existed, store that history separately per business design.

**"If deleting a parent succeeds, the total deleted rows equals the single count Oracle reports for that DELETE statement."**  
You cannot rely on a single row count alone to capture full cascading impact. Account for multi-level FKs, triggers, and related logic.

**"If the application checks for children, we don't need a FOREIGN KEY."**  
No. Concurrent transactions, admin scripts, and other write paths can bypass application logic. Database constraints remain essential for integrity.

## 16. Self-Check Questions

### Question 1 — Relationship Meaning

Table `ORDERS` has `CUSTOMER_ID` pointing to the primary key of `CUSTOMERS`. Which table is the parent, and which is the child? Can one customer have multiple orders?

**Hint:** `CUSTOMERS` is the parent; `ORDERS` is the child; multiple orders can share the same `CUSTOMER_ID` because an FK does not enforce uniqueness on the child table.

### Question 2 — Default Behavior

With an FK that has no `ON DELETE` clause, how does Oracle respond if you try to `DELETE` a customer who currently has orders?

**Hint:** Under standard immediate checking, Oracle blocks the delete and raises `ORA-02292`.

### Question 3 — CASCADE

The foreign key on `ORDER_ITEMS.ORDER_ID` specifies `ON DELETE CASCADE` referencing `ORDERS.ORDER_ID`. What happens to related order items when an order is deleted?

**Hint:** Child rows referencing that order are deleted by cascade. Deleting an order item, however, does not delete the order.

### Question 4 — SET NULL

If rows in `TASKS` must survive after `PROJECTS` deletes a project, should you consider `ON DELETE SET NULL` or `CASCADE`? What condition must `TASKS.PROJECT_ID` satisfy?

**Hint:** `SET NULL`, provided business semantics allow a task without a project; the FK column must allow `NULL` for deleting a parent with children to succeed.

### Question 5 — ORA-02291 Error

An `INSERT INTO ORDERS(..., CUSTOMER_ID=999)` fails with `ORA-02291`. What should you check first?

**Hint:** Whether a parent row with customer key 999 exists in the right schema/PDB, and whether parent/child inserts occurred in the proper order and transaction.

### Question 6 — ORA-02292 Error

A `DELETE FROM CUSTOMERS WHERE ID=1` fails with `ORA-02292`. Should you immediately disable the FK to let the delete succeed?

**Hint:** No. Identify the child table and business policy, then decide whether to keep the parent or handle child rows in a controlled way.

### Question 7 — Composite FK

An FK references a composite key `(REGION_ID, WAREHOUSE_ID)`. Why does metadata querying need `POSITION` to pair child and parent columns?

**Hint:** Key components must be matched by exact position in the column list, not merely by table or constraint name.

### Question 8 — Indexes

There is an FK on `ORDERS.CUSTOMER_ID`. Can you assume Oracle created an index on this column? When is an index helpful?

**Hint:** No. Check `USER_IND_COLUMNS`; an index helps queries looking up orders by customer as well as parent-key checks/deletes in concurrent workloads.

### Question 9 — DEFERRABLE

Do `ON DELETE CASCADE` and `DEFERRABLE` mean the same thing?

**Hint:** No. Cascade defines what happens to children when a parent is deleted; deferrable controls when the constraint is checked.

### Question 10 — Business Rules

A financial system must retain invoices for seven years after a customer stops using the service. Should you put `ON DELETE CASCADE` from customers to invoices just to simplify deletion?

**Hint:** Generally no. Design retention, inactive status, scheduled archival/purging, and access controls while preserving referential integrity.

### Question 11 — NULL and Foreign Keys

A child row has `PARENT_ID = NULL` and the FK allows NULL. Is this always a broken reference?

**Hint:** No. For a nullable single-column FK, NULL indicates no parent reference—unlike a non-null ID missing from the parent table.

### Question 12 — Reading DELETE_RULE

In `USER_CONSTRAINTS`, an FK shows `DELETE_RULE='NO ACTION'`. Does that mean recreating the FK requires writing `ON DELETE NO ACTION`?

**Hint:** No. That metadata value represents the default behavior; Oracle FK creation syntax simply omits `ON DELETE`.

## 17. Oracle Reference Documentation

- [Oracle Database SQL Language Reference — CREATE TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/CREATE-TABLE.html): declaring primary keys, unique keys, foreign keys, and `ON DELETE` behavior.
- [Oracle Database SQL Language Reference — constraint](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/constraint.html): constraint types, `references_clause` syntax, `ON DELETE CASCADE` and `SET NULL`, `DEFERRABLE`.
- [Oracle Database SQL Language Reference — ALTER TABLE](https://docs.oracle.com/en/database/oracle/oracle-database/19/sqlrf/ALTER-TABLE.html): adding, dropping, and managing constraints on existing tables.
- [Oracle Database Concepts](https://docs.oracle.com/en/database/oracle/oracle-database/19/cncpt/): relational databases, constraint types, and referential integrity.
- [Oracle Database Reference — USER_CONSTRAINTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/USER_CONSTRAINTS.html): constraint metadata and `DELETE_RULE` (refer to the corresponding user-scoped view).
- [Oracle Database Reference — ALL_CONSTRAINTS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_CONSTRAINTS.html): names, types, statuses, and links to parent constraints.
- [Oracle Database Reference — ALL_CONS_COLUMNS](https://docs.oracle.com/en/database/oracle/oracle-database/19/refrn/ALL_CONS_COLUMNS.html): identifying columns in FK/PK/UK constraints and `POSITION` ordering.
- [Oracle Database Administrator's Guide](https://docs.oracle.com/en/database/oracle/oracle-database/19/admin/): constraint administration, data dictionary, and schema operations.

When designing parent-child relationships in Oracle, start from **data rules**: must a child always have a parent, can it survive if the parent is removed, and is cascading deletion permitted? Only then choose between **default behavior**, **`ON DELETE CASCADE`**, or **`ON DELETE SET NULL`**. Combine constraint metadata checks, appropriate indexes, and sound transaction management so deletions remain both business-accurate and integrity-safe.
