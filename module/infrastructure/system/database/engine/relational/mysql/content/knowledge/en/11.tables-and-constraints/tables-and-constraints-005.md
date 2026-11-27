# ON DELETE/ON UPDATE, CASCADE, SET NULL, and RESTRICT

A foreign key keeps the relationship between a parent table and a child table valid. When a row in the parent table is deleted or a referenced key is updated, MySQL needs a rule defining what happens to the child rows. The `ON DELETE` and `ON UPDATE` clauses declare that rule. The common options are `CASCADE`, `SET NULL`, `RESTRICT`, and `NO ACTION`.

Choosing the right referential action protects business data, prevents accidental cascading deletions, and clarifies the application's responsibilities when modifying data. In the `DATABASE_MYSQL` module, this is an important part of table design, keys, transactions, and relational data operations. This lesson focuses on InnoDB in MySQL 8.x.

## Objectives

After this lesson, you will be able to:

- Explain when `ON DELETE` and `ON UPDATE` apply and their scope of impact.
- Distinguish `CASCADE`, `SET NULL`, `RESTRICT`, and `NO ACTION`.
- Choose the appropriate action based on the business data lifecycle.
- Design nullable or NOT NULL foreign key columns matching the referential action.
- Recognize the impact of multi-level cascades, transactions, locks, and triggers.
- Inspect constraints, handle delete/update errors, and deploy migrations safely.

## 1. Parent-Child Relationships and Foreign Keys

Suppose a customer has many orders. The `customers` table is the parent table; the `orders` table is the child table. The `orders.customer_id` column references `customers.customer_id`.

```sql
CREATE TABLE customers (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE orders (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    order_status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (order_id),
    KEY idx_orders_customer_id (customer_id),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers (customer_id)
) ENGINE=InnoDB;
```

In this example, the foreign key guarantees that every non-`NULL` `orders.customer_id` must point to an existing customer. MySQL/InnoDB requires the foreign key column to have a suitable index; InnoDB can automatically create an index if a suitable one is absent. You should declare indexes explicitly so naming and column order are controlled in the schema.

When deleting or changing `customers.customer_id`, the constraint must know how to handle orders currently referencing that customer. If no action is declared, the default behavior is to reject changes that violate the foreign key (equivalent to `RESTRICT`/`NO ACTION` in InnoDB).

## 2. Two Events That Trigger Referential Actions

| Clause | When Evaluated? | Example |
|---|---|---|
| `ON DELETE` | When deleting a parent row referenced by a foreign key | Deleting a customer who has orders |
| `ON UPDATE` | When updating the referenced key value in a parent row | Changing a parent key from 100 to 200 |

An action only applies when an operation on the parent side alters the referenced key and related child rows exist. Deleting a child row does not alter the parent row. Updating a column that is not part of the referenced key also does not trigger `ON UPDATE` for that foreign key.

For each event, you can pick one of these actions:

| Action | When Deleting/Updating a Parent Row | Outcome on Child Table |
|---|---|---|
| `CASCADE` | Permits the parent operation | Deletes matching child rows or updates child foreign keys to the new value |
| `SET NULL` | Permits the parent operation | Sets the child foreign key columns to `NULL` |
| `RESTRICT` | Rejects the parent operation if referencing child rows exist | Child rows remain unchanged; the parent statement raises an error |
| `NO ACTION` | In InnoDB, equivalent to `RESTRICT` and checked immediately | Child rows remain unchanged; the parent statement raises an error |

`ON DELETE` and `ON UPDATE` can use two different actions. For example, deleting a customer is blocked to protect order history, whereas if customer codes can change, key updates may be cascaded.

## 3. CASCADE: Propagating Changes to the Child Table

`CASCADE` automatically applies the corresponding operation to child rows whose foreign key references the parent row.

### 3.1. `ON DELETE CASCADE`

When a parent row is deleted, child rows referencing it are also deleted. For example, an order has multiple line items; when the order is deleted in a lab data model, its line items are deleted with it:

```sql
CREATE TABLE orders_cascade (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_code VARCHAR(40) NOT NULL,
    PRIMARY KEY (order_id)
) ENGINE=InnoDB;

CREATE TABLE order_items_cascade (
    item_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    order_id BIGINT UNSIGNED NOT NULL,
    product_name VARCHAR(150) NOT NULL,
    quantity INT UNSIGNED NOT NULL,
    PRIMARY KEY (item_id),
    KEY idx_order_items_order_id (order_id),
    CONSTRAINT fk_order_items_order_cascade
        FOREIGN KEY (order_id)
        REFERENCES orders_cascade (order_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB;
```

Insert sample data:

```sql
INSERT INTO orders_cascade (order_code)
VALUES ('ORD-LAB-001');

INSERT INTO order_items_cascade (order_id, product_name, quantity)
VALUES
    (1, 'Keyboard', 1),
    (1, 'Mouse', 2);
```

Delete the order:

```sql
DELETE FROM orders_cascade
WHERE order_id = 1;
```

Both rows in `order_items_cascade` are automatically deleted in the same referential operation. With InnoDB, the parent delete and cascaded changes belong to the same transaction; if the statement fails and the transaction rolls back, all transactional changes are rolled back together.

`ON DELETE CASCADE` is appropriate when child rows have no independent meaning once the parent row is deleted—such as line items of an unpublished draft, tokens tied to a login session, or junction tables representing many-to-many links.

Do not use cascade merely to reduce the number of SQL statements. If child rows represent financial history, invoices, transactions, audit logs, or regulated records, deleting the parent can destroy business evidence. For data that must be retained, consider `RESTRICT`, soft deletes, or historical archival models.

### 3.2. `ON UPDATE CASCADE`

When the referenced key value in the parent changes, MySQL updates the corresponding foreign key columns in the child:

```sql
CREATE TABLE region (
    region_code CHAR(5) NOT NULL,
    region_name VARCHAR(100) NOT NULL,
    PRIMARY KEY (region_code)
) ENGINE=InnoDB;

CREATE TABLE branch (
    branch_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    region_code CHAR(5) NOT NULL,
    branch_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (branch_id),
    KEY idx_branch_region_code (region_code),
    CONSTRAINT fk_branch_region
        FOREIGN KEY (region_code)
        REFERENCES region (region_code)
        ON DELETE RESTRICT
        ON UPDATE CASCADE
) ENGINE=InnoDB;
```

If the region code is changed:

```sql
UPDATE region
SET region_code = 'N01'
WHERE region_code = 'NORTH';
```

`branch` rows using `NORTH` are updated to `N01`. In new designs, a surrogate primary key such as `region_id` is usually more stable than a business code; when the display code changes, only an attribute column needs updating. `ON UPDATE CASCADE` is useful when a referenced key genuinely can change, but it should not be treated as a justification for picking mutable primary keys or changing IDs routinely.

### 3.3. Multi-Level Cascades

Cascade actions can propagate along a chain of relationships. For example:

```text
orders
  └── order_items
        └── item_notes
```

If `orders` cascades deletes to `order_items`, and `order_items` in turn cascades deletes to `item_notes`, deleting an order can delete rows across both descendant tables. A seemingly simple operation can affect a massive volume of data.

Diagram all foreign keys before enabling cascades on tables with many relationships. Check affected row counts, child-side indexes, locking, and execution duration. InnoDB limits the depth of nested cascade chains; do not design overly deep hierarchies or complex dependency cycles without testing on the exact target version.

## 4. SET NULL: Keep Child Rows but Detach the Link

`SET NULL` preserves child rows and sets the foreign key column to `NULL` when the parent row is deleted or the referenced key is updated. This action fits when the relationship is optional and child rows retain independent meaning.

For example, an article may have an editor, yet the article must be preserved even if the editor's account is deleted:

```sql
CREATE TABLE editor (
    editor_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    editor_name VARCHAR(120) NOT NULL,
    PRIMARY KEY (editor_id)
) ENGINE=InnoDB;

CREATE TABLE article (
    article_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    editor_id BIGINT UNSIGNED NULL,
    title VARCHAR(200) NOT NULL,
    body TEXT,
    PRIMARY KEY (article_id),
    KEY idx_article_editor_id (editor_id),
    CONSTRAINT fk_article_editor
        FOREIGN KEY (editor_id)
        REFERENCES editor (editor_id)
        ON DELETE SET NULL
        ON UPDATE CASCADE
) ENGINE=InnoDB;
```

When deleting an editor:

```sql
DELETE FROM editor
WHERE editor_id = 10;
```

Articles managed by that editor remain; `article.editor_id` becomes `NULL`. The application can display "Unassigned editor" or use a dedicated business status.

### 4.1. Foreign Key Columns Must Allow NULL

`SET NULL` cannot assign `NULL` to a column declared `NOT NULL`. In the example above, `article.editor_id` must be `BIGINT UNSIGNED NULL`. If the column is not nullable, the constraint design is rejected or the referential action cannot execute as requested.

With multi-column foreign keys, child columns are set to `NULL` by the action; all involved columns must be designed to accept `NULL` and you must understand composite foreign key semantics. Do not use `0`, an empty string, or a dummy ID in place of `NULL` when the goal is to represent a detached link.

### 4.2. SET NULL on Parent Key Update

You can declare `ON UPDATE SET NULL`, meaning when the parent's referenced key value changes, the child link is cleared by setting the foreign key to `NULL`. This case is far less common than `ON DELETE SET NULL`; if the parent code changes while the relationship remains valid, `ON UPDATE CASCADE` usually expresses the intent better.

## 5. RESTRICT and NO ACTION: Block Integrity-Breaking Changes

`RESTRICT` rejects deleting or updating a parent key if referencing child rows still exist. This is the protective choice when child rows must be handled first or the relationship must be preserved.

For example, a customer with orders cannot be deleted directly:

```sql
CREATE TABLE customer_restrict (
    customer_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (customer_id)
) ENGINE=InnoDB;

CREATE TABLE order_restrict (
    order_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    customer_id BIGINT UNSIGNED NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id),
    KEY idx_order_restrict_customer (customer_id),
    CONSTRAINT fk_order_restrict_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer_restrict (customer_id)
        ON DELETE RESTRICT
        ON UPDATE RESTRICT
) ENGINE=InnoDB;
```

If the customer has orders, the statement:

```sql
DELETE FROM customer_restrict
WHERE customer_id = 1;
```

will be rejected with a foreign key violation error (typically MySQL error 1451 when deleting/updating a parent row). The application must process the orders per business workflow or mark the customer inactive instead of deleting directly.

### 5.1. NO ACTION in InnoDB

In InnoDB, `NO ACTION` behaves identically to `RESTRICT`: it checks the foreign key immediately when the statement executes and rejects the operation if referencing child rows remain. It does not mean "defer checking until the end of the transaction". MySQL/InnoDB does not provide deferred foreign key constraints like some other database systems.

Therefore, in InnoDB schemas, writing `RESTRICT` is usually clearer when you want immediate blocking. `NO ACTION` can be used to express standard SQL syntax, but it produces no execution difference compared to `RESTRICT` in InnoDB.

### 5.2. Default Behavior

If `ON DELETE` or `ON UPDATE` is omitted, InnoDB defaults to rejecting changes that violate the relationship, equivalent to `RESTRICT`/`NO ACTION`. To make schemas easier to read and prevent misunderstandings, explicitly declare important actions—especially on relationships carrying cascading deletion risk.

## 6. Choosing Actions Based on Data Lifecycle

| Business Relationship | Commonly Considered Action | Reason |
|---|---|---|
| Order and line items of a fully deletable draft | `ON DELETE CASCADE` | Line items have no meaning if the draft is deleted |
| Customer and existing invoices/transactions | `ON DELETE RESTRICT` | Protects history and auditable data |
| Article and optional editor | `ON DELETE SET NULL` | Article still exists when the editor leaves the system |
| User-role junction table | `ON DELETE CASCADE` from user or role to junction row | Role assignment loses meaning when either endpoint is deleted |
| Mutable category code where child records stay linked | `ON UPDATE CASCADE` or use a stable surrogate key | Maintains linkage if the referenced key changes |
| Historical record that must retain original subject identity | `RESTRICT`, soft delete, or store a snapshot | Do not let cascade/SET NULL erase historical context |

These are design guidelines, not mechanical rules. The essential questions are: can child rows exist independently, must history be retained, and who is authorized to decide on deletion? Foreign key actions must reflect the data policy agreed upon with the business.

## 7. Behavior in Transactions and Locking

InnoDB's referential actions execute within the parent statement's transaction. During a cascade delete, InnoDB must locate related child rows, lock the necessary rows, and apply changes. An index on the foreign key column helps locate child rows efficiently and avoids table scans.

Example transaction deleting a draft:

```sql
START TRANSACTION;

DELETE FROM orders_cascade
WHERE order_id = 1;

-- You can check the state of related tables inside the transaction.
SELECT COUNT(*)
FROM order_items_cascade
WHERE order_id = 1;

COMMIT;
```

If you need to cancel the operation before committing, `ROLLBACK` undoes both the parent delete and the cascaded child deletions, provided the tables use a transactional engine like InnoDB.

### 7.1. Deleting Many Parent Rows Can Trigger a Large Cascade

```sql
DELETE FROM orders_cascade
WHERE order_id BETWEEN 1000 AND 5000;
```

A single statement deleting many orders can pull along a huge number of child rows. Impacts can include:

- Numerous row locks and long lock hold times.
- Large undo logs, increased redo logs, and higher I/O.
- Increased replication or binary log volume and apply lag.
- Other transactions blocking or encountering deadlocks.
- Longer rollback times if the operation fails midway.

Before running on large datasets, estimate child row counts, inspect indexes, test on staging, and batch by a stable key if business rules allow. Batching must be designed so intermediate states do not violate business invariants.

### 7.2. Deadlocks and Operation Ordering

Multiple concurrent transactions deleting/updating parent-child rows in different orders can cause deadlocks. InnoDB selects a victim transaction and rolls it back. Applications must implement bounded retry logic for deadlock/lock timeout errors, while keeping transactions short and accessing tables in a consistent order.

Do not assume `CASCADE` is free or always faster than the application deleting tables explicitly. Cascades enforce relational integrity at the database, but locking costs and affected data volume still apply.

## 8. Cascades and Triggers

An easily overlooked detail: operations performed by foreign key cascades in InnoDB do not fire triggers on the child table. For example, if deleting a parent row causes InnoDB to automatically delete child rows via `ON DELETE CASCADE`, an `AFTER DELETE` trigger declared on the child table will not run for rows deleted by the cascade.

This matters for audit logs and data synchronization. If a system relies on child-table triggers to record history or emit events, do not assume cascade operations generate audit records. Design auditing at the business level or explicitly log parent operations and their scope. If per-child-row auditing is required, the application or a tested database workflow must handle it explicitly.

Triggers attached directly to the SQL statement executed on the parent table still follow normal parent-table trigger rules; the caveat here is specifically that automatic cascade actions on child tables do not fire child triggers.

## 9. Composite Foreign Keys and Referential Actions

A foreign key can consist of multiple columns. With `CASCADE`, all matching foreign key components are updated to follow the parent key; with `SET NULL`, child foreign key columns are set to `NULL`.

Example of a tenant and project relationship using a composite key:

```sql
CREATE TABLE tenant_project (
    tenant_id BIGINT UNSIGNED NOT NULL,
    project_id BIGINT UNSIGNED NOT NULL,
    project_name VARCHAR(150) NOT NULL,
    PRIMARY KEY (tenant_id, project_id)
) ENGINE=InnoDB;

CREATE TABLE project_task (
    task_id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    tenant_id BIGINT UNSIGNED NOT NULL,
    project_id BIGINT UNSIGNED NOT NULL,
    task_name VARCHAR(200) NOT NULL,
    PRIMARY KEY (task_id),
    KEY idx_project_task_project (tenant_id, project_id),
    CONSTRAINT fk_project_task_project
        FOREIGN KEY (tenant_id, project_id)
        REFERENCES tenant_project (tenant_id, project_id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB;
```

Deleting a project within a tenant deletes the tasks belonging to that exact key pair. Do not check `project_id` alone, because the same `project_id` value could exist under another tenant in a multi-tenant model.

For `SET NULL` on a composite key, all component columns on the child side must allow `NULL`. If only one column is nullable, setting the entire foreign key to null cannot satisfy the remaining `NOT NULL` definition.

## 10. Limitations and Caveats When Designing Foreign Keys

- InnoDB requires parent and child tables to use compatible foreign-key-supporting engines; the standard case is both using InnoDB.
- Referencing columns must have compatible types; integer types must match in size and signedness.
- Referenced columns should be a `PRIMARY KEY` or `UNIQUE KEY`; avoid relying on non-unique parent keys, as this non-standard reference style is restricted/deprecated in newer MySQL releases.
- Child-side foreign key columns need a suitable index; declare indexes explicitly.
- `SET NULL` requires nullable child columns.
- InnoDB checks foreign keys immediately and does not support deferred checking at transaction commit.
- `SET DEFAULT` is not supported by InnoDB for referential actions; do not use it in place of `SET NULL` or application default values.
- Constraint names must be unique within the schema per MySQL rules; use recognizable names to ease error handling and migrations.

### 10.1. Do Not Disable `foreign_key_checks` to Bypass Actions

MySQL allows disabling foreign key checks within a session:

```sql
SET SESSION foreign_key_checks = 0;
```

This option is useful during certain controlled import or restore workflows, not as a fix for design flaws. When re-enabled:

```sql
SET SESSION foreign_key_checks = 1;
```

MySQL does not automatically scan and re-verify all data loaded while checks were off. Orphan data may remain. Only use it in workflows with an independent data verification plan, appropriate privileges, and a controlled environment.

## 11. Inspecting Referential Actions in a Schema

Read the table definition:

```sql
SHOW CREATE TABLE order_items_cascade\G
```

Detailed constraint metadata can be queried from `information_schema`:

```sql
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    REFERENCED_TABLE_NAME,
    UPDATE_RULE,
    DELETE_RULE
FROM information_schema.REFERENTIAL_CONSTRAINTS
WHERE CONSTRAINT_SCHEMA = DATABASE()
ORDER BY TABLE_NAME, CONSTRAINT_NAME;
```

View columns belonging to each foreign key:

```sql
SELECT
    CONSTRAINT_NAME,
    TABLE_NAME,
    COLUMN_NAME,
    REFERENCED_TABLE_NAME,
    REFERENCED_COLUMN_NAME,
    ORDINAL_POSITION
FROM information_schema.KEY_COLUMN_USAGE
WHERE CONSTRAINT_SCHEMA = DATABASE()
  AND REFERENCED_TABLE_NAME IS NOT NULL
ORDER BY TABLE_NAME, CONSTRAINT_NAME, ORDINAL_POSITION;
```

Before migrating, compare `DELETE_RULE` and `UPDATE_RULE` against business requirements. Do not just read constraint names; a name like `fk_order_customer` does not reveal the actual action.

## 12. Changing Referential Actions

MySQL does not provide a dedicated `ALTER CONSTRAINT` syntax to directly change `ON DELETE` or `ON UPDATE` on a foreign key. Typically, you must drop the old foreign key and recreate it with the desired actions.

Example:

```sql
ALTER TABLE order_items_cascade
    DROP FOREIGN KEY fk_order_items_order_cascade;

ALTER TABLE order_items_cascade
    ADD CONSTRAINT fk_order_items_order_cascade
    FOREIGN KEY (order_id)
    REFERENCES orders_cascade (order_id)
    ON DELETE RESTRICT
    ON UPDATE CASCADE;
```

Before dropping/recreating:

1. Confirm the constraint name and current definition using `SHOW CREATE TABLE`.
2. Verify child data has no orphans and column types are compatible.
3. Evaluate locking, metadata locks, DDL duration, and application impact.
4. Prepare a rollout and rollback plan; during the change, avoid letting the application write relationship-violating data.
5. After recreating, verify with `SHOW CREATE TABLE` and `information_schema.REFERENTIAL_CONSTRAINTS`.

If drop/add is not executed within an atomic DDL workflow supported by your version/tooling, there may be a window without the constraint. Perform this during a maintenance window or use a tested migration strategy.

## 13. Hands-on Lab

Perform in a dedicated lab schema, never on production data:

1. Create a parent-child table pair with `ON DELETE CASCADE`; insert one parent row and multiple child rows, delete the parent, and verify the child rows are deleted.
2. Create a relationship with `ON DELETE SET NULL`; delete the parent row and verify child rows remain with a `NULL` foreign key.
3. Create an `ON DELETE RESTRICT` relationship; try deleting a referenced parent and record the MySQL error.
4. Compare `RESTRICT` with `NO ACTION` in InnoDB; confirm both reject the operation immediately when child rows exist.
5. Create a mutable business key and test `ON UPDATE CASCADE`; observe the foreign key values in the child table.
6. Create a three-table parent-child-grandchild cascade chain, delete a root row, and count affected rows at each level.
7. Create an `AFTER DELETE` trigger on the child table in the lab, then delete a parent row via cascade; verify the child trigger does not log audits for cascade-deleted rows.
8. Query `information_schema.REFERENTIAL_CONSTRAINTS` to report `DELETE_RULE`/`UPDATE_RULE` actions for every constraint.
9. Practice changing a foreign key via drop/recreate and re-verify both schema and data post-migration.
10. Write design decisions for three relationships: order-line items, customer-invoices, and article-editor; justify the chosen actions based on data lifecycle.

You have completed this lesson when you can accurately predict the impact of parent delete/update operations, choose actions aligned with data policy, and verify the active rules from MySQL metadata.

## 14. Principles to Remember

- `ON DELETE` handles deleting a parent row; `ON UPDATE` handles changing a referenced parent key.
- `CASCADE` deletes or updates child rows following parent changes; weigh cascading deletion risks carefully.
- `SET NULL` retains child rows while detaching the link; all foreign key columns must allow `NULL`.
- `RESTRICT` blocks parent operations while child rows remain; `NO ACTION` is equivalent to `RESTRICT` and checked immediately in InnoDB.
- Do not use cascade to delete historical data required for auditing or business retention.
- Cascades can generate substantial row locks, undo/redo logs, and replication lag; always index the child side.
- InnoDB cascade actions on a child table do not fire child-table triggers.
- Do not disable `foreign_key_checks` as a workaround for design flaws; re-enabling it does not verify imported data.
- Inspect `SHOW CREATE TABLE` and `information_schema.REFERENTIAL_CONSTRAINTS` before and after migrations.
- Design stable primary keys to minimize the need for `ON UPDATE CASCADE`.
