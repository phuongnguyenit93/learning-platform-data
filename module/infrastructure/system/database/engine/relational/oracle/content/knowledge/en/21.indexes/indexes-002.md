# Unique/Nonunique Indexes and Their Relationship with Constraints in Oracle

In Oracle Database, **indexes** and **constraints** frequently appear together, yet they solve two different problems. An index is a storage structure that speeds up row retrieval and can carry a uniqueness attribute. A constraint is a data integrity rule that Oracle must enforce. A unique index can be used to enforce a unique constraint, but a unique index itself does not automatically create a constraint in metadata.

This distinction matters when designing primary keys, natural keys, foreign keys, data containing `NULL`, or when allowing multi-row updates within a transaction and checking uniqueness at commit time. Choosing the wrong index type can cause `INSERT`/`UPDATE` operations to fail, prevent queries from using the expected access path, or lead applications to mistakenly assume data is protected by a constraint.

This lesson belongs to the **Indexes** topic of *Database Engine Relational Oracle*. It focuses on:

- How unique indexes and nonunique indexes differ at the storage and key-checking level.
- The relationship between indexes and `PRIMARY KEY` and `UNIQUE` constraints.
- `NULL` in unique keys, composite keys, and edge cases.
- How Oracle creates, reuses, and manages indexes supporting constraints.
- `DEFERRABLE` constraints and uniqueness checking at `COMMIT`.
- Foreign key indexes, function-based unique indexes, and conditional uniqueness.
- Querying metadata, reading execution plans, and hands-on SQL practice.

## 1. Indexes and Constraints Have Different Roles

### An index is an access structure

An index is a data structure stored separately from a table, typically a B-tree in OLTP examples. An index contains keys built from one or more columns/expressions and location information for the corresponding rows. Oracle can use an index to:

- Locate rows using equality or range conditions.
- Support `JOIN` and sorting operations in certain execution plans.
- Enforce uniqueness if the index is unique.
- Reduce the number of table blocks to read when predicates have appropriate selectivity.

An index is a physical/logical schema object with a name, status, type, and storage attributes. Creating an index does not equate to declaring all business rules related to the columns.

### A constraint is an integrity rule

A constraint defines a condition that data must obey. Common types include:

| Constraint | Rule |
| --- | --- |
| PRIMARY KEY | Uniquely identifies each row; key columns cannot be NULL. |
| UNIQUE | Disallows duplicate key values according to constraint rules. |
| FOREIGN KEY | Foreign key value must reference a valid key in the parent table, unless NULL is allowed. |
| NOT NULL | Column must have a non-NULL value. |
| CHECK | Value must satisfy a conditional expression. |

Constraints are stored in the data dictionary with a name, `ENABLE`/`DISABLE` status, `VALIDATED`/`NOT VALIDATED` state, and optional `DEFERRABLE` attribute. Constraints express schema-level data rules that every application writing to the table must obey.

### A unique index does not automatically create a UNIQUE constraint

~~~sql
CREATE TABLE app_users (
    user_id NUMBER PRIMARY KEY,
    email   VARCHAR2(320)
);

CREATE UNIQUE INDEX ux_app_users_email
ON app_users(email);
~~~

The index on `email` prevents duplicate key values according to unique index semantics, but there is no corresponding `UNIQUE` constraint in the data dictionary on the `EMAIL` column. If an application or DBA looks only at the index and concludes the schema has declared a `UNIQUE` constraint, that would be a mistake.

Conversely, when declaring a constraint:

~~~sql
ALTER TABLE app_users
ADD CONSTRAINT uq_app_users_email UNIQUE (email);
~~~

Oracle enforces the uniqueness rule at the constraint level. To enforce it efficiently, Oracle normally uses an appropriate index; if no suitable index exists, it can create one to support the constraint.

### A constraint can be enforced using an index

For `PRIMARY KEY` and `UNIQUE` constraints, Oracle usually uses a unique index to check uniqueness when the constraint is checked immediately. If the constraint is `DEFERRABLE`, Oracle must allow temporary duplicate states within a transaction, so the supporting index is nonunique; rule checking occurs at the time the constraint must be validated.

Therefore:

- An index can be the mechanism that enforces a constraint.
- The constraint remains the object describing the integrity rule.
- Not every unique index is a constraint.
- Not every index backing a unique constraint is necessarily a unique index.

## 2. Unique Indexes and Nonunique Indexes

### Unique index

A unique index guarantees that no two index entries share the same key under Oracle's uniqueness rules. Example:

~~~sql
CREATE UNIQUE INDEX ux_employees_badge
ON employees(badge_no);
~~~

Once created successfully, Oracle rejects `INSERT`/`UPDATE` statements that produce duplicate keys. A unique index can span one column or multiple columns:

~~~sql
CREATE UNIQUE INDEX ux_employee_dept_email
ON employees(department_id, email);
~~~

In this example, uniqueness applies to the combination of both values; it does not require each individual column to be unique.

### Nonunique index

A nonunique index allows multiple rows to share the same index key:

~~~sql
CREATE INDEX ix_orders_customer
ON orders(customer_id);
~~~

Many orders can belong to the same customer. A nonunique index is appropriate for columns frequently used in filters, `JOIN`s, or sorting that have no uniqueness rule.

### Comparison

| Characteristic | Unique index | Nonunique index |
| --- | --- | --- |
| Duplicate keys | Prevented per unique index rules | Allowed |
| Purpose | Access and index-level uniqueness enforcement | Data access |
| Automatically creates a constraint? | No | No |
| Can support PK/UNIQUE constraint? | Yes, in appropriate cases | Can be used in some cases, especially DEFERRABLE constraints |
| Can span multiple columns? | Yes | Yes |
| Can be function-based? | Yes | Yes |

### A unique index does not mean each column individually is unique

~~~sql
CREATE UNIQUE INDEX ux_order_line
ON order_lines(order_id, line_no);
~~~

The index allows multiple rows with the same `ORDER_ID`, as long as `LINE_NO` differs within the same `ORDER_ID`. For example, `(100, 1)` and `(100, 2)` are valid; two duplicate `(100, 1)` rows are rejected.

## 3. PRIMARY KEY, UNIQUE Constraints, and Supporting Indexes

### PRIMARY KEY

`PRIMARY KEY` both enforces uniqueness and forbids `NULL` on the columns making up the key:

~~~sql
CREATE TABLE departments (
    department_id NUMBER
        CONSTRAINT pk_departments PRIMARY KEY,
    department_name VARCHAR2(100) NOT NULL
);
~~~

Oracle usually creates a unique index to enforce the primary key unless an existing suitable index is specified or reused. Primary keys are stored in the dictionary under constraint type `P`.

### UNIQUE constraint

A `UNIQUE` constraint guarantees no two rows violate the uniqueness rule across the declared column set:

~~~sql
CREATE TABLE app_users (
    user_id NUMBER CONSTRAINT pk_app_users PRIMARY KEY,
    email   VARCHAR2(320),
    CONSTRAINT uq_app_users_email UNIQUE(email)
);
~~~

A `UNIQUE` constraint differs from `PRIMARY KEY` in that unique columns can allow `NULL` unless `NOT NULL` is also declared. If the business requires every row to have an email and emails must not repeat, declare both:

~~~sql
email VARCHAR2(320) NOT NULL,
CONSTRAINT uq_app_users_email UNIQUE(email)
~~~

### A table can have multiple UNIQUE constraints

~~~sql
CREATE TABLE employees (
    employee_id NUMBER
        CONSTRAINT pk_employees PRIMARY KEY,
    national_code VARCHAR2(30),
    work_email    VARCHAR2(320),
    CONSTRAINT uq_employees_national_code UNIQUE(national_code),
    CONSTRAINT uq_employees_work_email UNIQUE(work_email)
);
~~~

Each constraint expresses an independent rule. Oracle can create a separate index for each constraint, or use an existing suitable index if specified and eligible.

### Using an existing index to support a constraint

You can create an index first, then add a constraint and specify that index:

~~~sql
CREATE UNIQUE INDEX ux_app_users_email
ON app_users(email);

ALTER TABLE app_users
ADD CONSTRAINT uq_app_users_email UNIQUE(email)
USING INDEX ux_app_users_email;
~~~

This gives the DBA control over the index name and attributes. The index must match the columns/expressions and requirements of the constraint. If the index is incompatible or existing data violates uniqueness, adding the constraint fails.

## 4. NULLs in Oracle Unique Keys

`NULL` is not an ordinary numeric or string value; it represents an unknown or missing value. Consequently, uniqueness has special cases to distinguish.

### UNIQUE on a single column

With a unique constraint on a nullable column, Oracle allows multiple rows to contain `NULL` in that column. Non-NULL values must still be unique:

~~~sql
CREATE TABLE lab_unique_email (
    id    NUMBER PRIMARY KEY,
    email VARCHAR2(100),
    CONSTRAINT uq_lab_unique_email UNIQUE(email)
);

INSERT INTO lab_unique_email VALUES (1, 'a@example.com');
INSERT INTO lab_unique_email VALUES (2, NULL);
INSERT INTO lab_unique_email VALUES (3, NULL);
~~~

The two `NULL` rows are valid; inserting another row with email `a@example.com` violates the unique constraint.

To disallow `NULL`, you must declare `NOT NULL`:

~~~sql
ALTER TABLE lab_unique_email
MODIFY email NOT NULL;
~~~

This statement succeeds only if existing data contains no `NULL` values.

### UNIQUE on multiple columns

For a composite key, uniqueness is evaluated across the combination of columns. Oracle has specific semantics for `NULL` in compound keys: a combination containing `NULL` is not treated like an ordinary value in SQL comparisons; rows with one or more `NULL` components may be accepted depending on the combination, while all-NULL combinations have their own rules. Do not deduce that one `UNIQUE` constraint on two columns is equivalent to two separate unique constraints.

Example to test directly in a lab schema and observe:

~~~sql
CREATE TABLE lab_unique_pair (
    id NUMBER PRIMARY KEY,
    a  NUMBER,
    b  NUMBER,
    CONSTRAINT uq_lab_unique_pair UNIQUE(a, b)
);

INSERT INTO lab_unique_pair VALUES (1, 10, NULL);
INSERT INTO lab_unique_pair VALUES (2, 10, NULL);
INSERT INTO lab_unique_pair VALUES (3, NULL, 20);
INSERT INTO lab_unique_pair VALUES (4, NULL, 20);
INSERT INTO lab_unique_pair VALUES (5, NULL, NULL);
~~~

Observe each `INSERT` on your Oracle version and check the constraint metadata. When designing business rules, if uniqueness must apply even when a component is `NULL`, express the rule explicitly using `NOT NULL` or an appropriate function-based unique index/normalized expression rather than relying on intuition about `NULL`.

### Unique B-tree indexes and all-NULL keys

Standard Oracle B-tree indexes do not store entries when all index key columns are `NULL`. With a composite index, an entry can exist if at least one component has a value. This affects using a unique index to express rules for `NULL` combinations.

If you must enforce a special rule involving `NULL`, design an explicit index expression and test it with sample data. Do not replace `NULL` with an arbitrary sentinel if that sentinel could appear in real data.

## 5. DEFERRABLE Constraints and Nonunique Indexes

By default, `PRIMARY KEY` and `UNIQUE` constraints are usually checked immediately after each statement. Oracle also supports constraints whose checking can be deferred until the end of the transaction:

- `NOT DEFERRABLE`: cannot be deferred.
- `DEFERRABLE INITIALLY IMMEDIATE`: can be deferred per transaction, but checked immediately by default.
- `DEFERRABLE INITIALLY DEFERRED`: checked at transaction end by default.

Example:

~~~sql
CREATE TABLE lab_account_codes (
    id NUMBER PRIMARY KEY,
    code NUMBER,
    CONSTRAINT uq_lab_account_codes
        UNIQUE(code)
        DEFERRABLE INITIALLY DEFERRED
);
~~~

With a deferred constraint, a transaction can temporarily create duplicate states while executing multiple steps, as long as it resolves to a valid state before commit:

~~~sql
SET CONSTRAINTS uq_lab_account_codes DEFERRED;

UPDATE lab_account_codes SET code = 20 WHERE id = 1;
UPDATE lab_account_codes SET code = 10 WHERE id = 2;

COMMIT;
~~~

Swapping two codes can cause a temporary duplicate if checked after each statement. A deferred constraint allows the intermediate state and validates uniqueness when the transaction ends.

### Why is the index supporting a DEFERRABLE constraint nonunique?

During a deferred transaction, two index entries with the same key can temporarily exist before the transaction finishes. A physical unique index would reject the duplicate as soon as DML occurs, contradicting the requirement to allow deferred checking. Therefore, Oracle uses a nonunique index to support a `DEFERRABLE` constraint and enforces uniqueness at the point when the constraint must be validated.

You can inspect the index associated with a constraint via `USER_CONSTRAINTS` and `USER_INDEXES`. Do not conclude that a constraint is non-unique just because you see a nonunique index; the constraint may still be `UNIQUE` with deferred checking.

### SET CONSTRAINTS

Within a transaction, you can change the checking mode for `DEFERRABLE` constraints:

~~~sql
SET CONSTRAINTS uq_lab_account_codes DEFERRED;

-- DML can temporarily create duplicates.

SET CONSTRAINTS uq_lab_account_codes IMMEDIATE;
~~~

When switching to `IMMEDIATE`, Oracle validates current changes; if data violates the rule, the `SET CONSTRAINTS` statement can fail. A `NOT DEFERRABLE` constraint cannot be switched to `DEFERRED`.

## 6. Relationship with FOREIGN KEY and Child Table Indexes

A foreign key references a `PRIMARY KEY` or `UNIQUE` constraint on the parent table. A standalone unique index on the parent column does not substitute for the constraint object that a foreign key must reference.

Example:

~~~sql
CREATE TABLE customers (
    customer_id NUMBER
        CONSTRAINT pk_customers PRIMARY KEY,
    email VARCHAR2(320)
);

CREATE TABLE orders (
    order_id NUMBER
        CONSTRAINT pk_orders PRIMARY KEY,
    customer_id NUMBER,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
~~~

The index backing `CUSTOMERS`'s `PRIMARY KEY` helps Oracle look up and validate parent keys. However, Oracle does not automatically create an index on the `FOREIGN KEY` column of the child table:

~~~sql
CREATE INDEX ix_orders_customer_id
ON orders(customer_id);
~~~

This is normally a nonunique index because one customer can have many orders.

### Why is an index on a foreign key often useful?

- Speeds up `JOIN`s from `orders` to `customers` on `CUSTOMER_ID`.
- Supports queries filtering orders by customer.
- Helps Oracle locate child rows when validating parent row deletions or parent key updates.
- Can prevent certain broad locking situations on the child table when a parent key is deleted/updated while the FK has no index.

An FK index is not mandatory for every table. If the child table is very small, the FK is rarely queried, or parent keys are never deleted/updated, the benefit may be lower than the index maintenance cost. Every `INSERT`/`UPDATE`/`DELETE` affecting the FK column also has to maintain the index, increasing DML work and redo.

### An FK does not require a unique index on the child table

~~~sql
CREATE INDEX ix_order_lines_order
ON order_lines(order_id);
~~~

Many `order_lines` rows share the same `ORDER_ID`, so a nonunique index is the natural choice. Creating a unique index on `ORDER_ID` in the child table would accidentally forbid an order from having multiple line items.

### When might an FK column need to be unique?

If the business relationship is one-to-one, the FK column in the child table can have a `UNIQUE` constraint:

~~~sql
CREATE TABLE employee_profiles (
    profile_id NUMBER PRIMARY KEY,
    employee_id NUMBER NOT NULL,
    CONSTRAINT uq_employee_profiles_employee UNIQUE(employee_id),
    CONSTRAINT fk_employee_profiles_employee
        FOREIGN KEY (employee_id)
        REFERENCES employees(employee_id)
);
~~~

The `UNIQUE` constraint guarantees each employee has at most one profile. That is a data rule; the index backing it is an implementation detail.

## 7. Function-Based Unique Indexes

Unique indexes do not apply only to raw column values. Oracle supports function-based indexes, where the index key is computed from an expression. This is useful when uniqueness must be evaluated after normalization.

### Case-insensitivity

Suppose email is considered case-insensitive. A standard unique constraint on `EMAIL` may treat two strings differing only in case as two distinct values depending on current collation/semantics. You can create a unique function-based index:

~~~sql
CREATE UNIQUE INDEX ux_users_email_ci
ON app_users(LOWER(email));
~~~

The index guarantees no two `LOWER(email)` values are identical. Thus `Alice@example.com` and `ALICE@example.com` conflict if both are non-NULL.

Lookup queries should use the matching expression:

~~~sql
SELECT user_id, email
FROM app_users
WHERE LOWER(email) = LOWER(:email);
~~~

Notes:

- This is a unique index; it does not automatically create a `UNIQUE` constraint on the `EMAIL` column.
- The normalization expression must match business rules and supported language/collation requirements.
- Function-based indexes incur maintenance overhead when input columns change.
- If explicit constraint metadata is needed, consider a virtual column representing the normalized value and declaring a `UNIQUE` constraint on the virtual column, depending on version capabilities and schema design.

### Conditional uniqueness: unique only within a given status

A common requirement: email must be unique among `ACTIVE` users, but may repeat among `INACTIVE` or archived accounts. You can use `CASE` in a unique function-based index:

~~~sql
CREATE UNIQUE INDEX ux_active_users_email
ON app_users (
    CASE
        WHEN status = 'ACTIVE' THEN LOWER(email)
    END
);
~~~

For `ACTIVE` rows, the expression returns `LOWER(email)`, so duplicate normalized emails are rejected. For non-ACTIVE rows, the expression returns `NULL`; B-tree indexes do not store entries when the entire key is `NULL`, so those rows do not conflict via this index.

This is a way to express conditional uniqueness using an index. It is not a standard `UNIQUE` constraint with an equivalent `WHERE` condition. If status changes from `INACTIVE` to `ACTIVE`, DML will generate an index key and may fail if another `ACTIVE` user already has the same email.

### Multi-component normalization

~~~sql
CREATE UNIQUE INDEX ux_active_tenant_login
ON app_users (
    CASE WHEN status = 'ACTIVE' THEN tenant_id END,
    CASE WHEN status = 'ACTIVE' THEN LOWER(login_name) END
);
~~~

The goal is uniqueness of the tenant/login pair within the `ACTIVE` set. Clearly define `NULL` behavior and non-ACTIVE rows, because composite unique indexes have specific semantics with `NULL`. If `tenant_id` or `login_name` is allowed to be `NULL` in `ACTIVE` rows, add appropriate `NOT NULL`/`CHECK` rules if required by the business.

## 8. Inspecting Constraints and Indexes in the Data Dictionary

Do not guess the relationship between constraints and indexes from object names. Oracle provides dictionary views to inspect them.

### USER_CONSTRAINTS

Useful columns:

- `CONSTRAINT_NAME`: constraint name.
- `CONSTRAINT_TYPE`: `P` (primary key), `U` (unique), `R` (foreign key), `C` (check/not null).
- `TABLE_NAME`: table containing the constraint.
- `STATUS`: `ENABLED` or `DISABLED`.
- `VALIDATED`: `VALIDATED` or `NOT VALIDATED`.
- `DEFERRABLE` and `DEFERRED`: deferrability and deferral mode.
- `INDEX_NAME`: associated index enforcing PK/UNIQUE, if any.

### USER_INDEXES and USER_IND_COLUMNS

`USER_INDEXES` shows index attributes:

- `INDEX_NAME`, `TABLE_NAME`.
- `UNIQUENESS`: `UNIQUE` or `NONUNIQUE`.
- `INDEX_TYPE`, `STATUS`, and other attributes.

`USER_IND_COLUMNS` shows columns and column order in an index. `USER_CONS_COLUMNS` shows the columns making up a constraint.

### Viewing PK/UNIQUE constraints and associated indexes

~~~sql
SELECT c.constraint_name,
       c.constraint_type,
       c.status AS constraint_status,
       c.validated,
       c.deferrable,
       c.deferred,
       c.index_name,
       i.uniqueness AS index_uniqueness,
       i.status AS index_status
FROM user_constraints c
LEFT JOIN user_indexes i
  ON i.index_name = c.index_name
WHERE c.table_name = 'APP_USERS'
  AND c.constraint_type IN ('P', 'U')
ORDER BY c.constraint_type, c.constraint_name;
~~~

If a constraint is `UNIQUE` while `INDEX_UNIQUENESS` is `NONUNIQUE`, check `DEFERRABLE`/`DEFERRED` and how the index is used. This may be intentional design rather than a metadata error.

### Viewing constraint columns

~~~sql
SELECT constraint_name,
       table_name,
       column_name,
       position
FROM user_cons_columns
WHERE table_name = 'APP_USERS'
ORDER BY constraint_name, position;
~~~

### Viewing index columns

~~~sql
SELECT index_name,
       table_name,
       column_name,
       column_position,
       descend
FROM user_ind_columns
WHERE table_name = 'APP_USERS'
ORDER BY index_name, column_position;
~~~

### Viewing foreign keys and parent tables

~~~sql
SELECT fk.constraint_name,
       fk.table_name AS child_table,
       fkc.column_name AS child_column,
       pk.table_name AS parent_table,
       pk.constraint_name AS parent_constraint
FROM user_constraints fk
JOIN user_cons_columns fkc
  ON fkc.constraint_name = fk.constraint_name
JOIN user_constraints pk
  ON pk.constraint_name = fk.r_constraint_name
WHERE fk.constraint_type = 'R'
  AND fk.table_name = 'ORDERS'
ORDER BY fkc.position;
~~~

`USER_` views show only objects owned by the current schema. Use `ALL_` views for objects accessible to the user or `DBA_` views when appropriate administrative privileges are available. Object names in the dictionary are normally stored in uppercase if created without quoted identifiers.

## 9. Lifecycle of Indexes Attached to Constraints

An index backing a constraint can be created automatically or created beforehand by a DBA and attached to the constraint. How it was created affects how the index behaves when the constraint is disabled or dropped.

### Oracle creates the index automatically

~~~sql
CREATE TABLE lab_products (
    product_id NUMBER,
    sku        VARCHAR2(40),
    CONSTRAINT pk_lab_products PRIMARY KEY(product_id),
    CONSTRAINT uq_lab_products_sku UNIQUE(sku)
);
~~~

If no suitable index exists, Oracle creates indexes to support PK and `UNIQUE`. The Oracle-generated index name may differ from the constraint name. Check `USER_CONSTRAINTS.INDEX_NAME` rather than assuming the two names match.

### Using a pre-created index

~~~sql
CREATE UNIQUE INDEX ux_lab_products_sku
ON lab_products(sku);

ALTER TABLE lab_products
ADD CONSTRAINT uq_lab_products_sku UNIQUE(sku)
USING INDEX ux_lab_products_sku;
~~~

Once the constraint is created, the index becomes associated with the constraint. You should not drop an index while a constraint relies on it; Oracle will reject it or require changing the constraint/index first.

### Disabling or dropping a constraint

When disabling a PK/`UNIQUE` constraint, Oracle may drop an automatically created index that was enforcing it. If the index was created independently and used by the constraint, a DBA can choose to keep the index when disabling via the `KEEP INDEX` option:

~~~sql
ALTER TABLE lab_products
DISABLE CONSTRAINT uq_lab_products_sku KEEP INDEX;
~~~

Whether the index is kept or dropped depends on the index's origin and the exact statement. Before disabling/dropping a constraint in a real environment, check `USER_CONSTRAINTS.INDEX_NAME` and `USER_INDEXES`, and confirm whether applications rely on the index for queries.

### ENABLE VALIDATE and ENABLE NOVALIDATE

When re-enabling a constraint, you may need to specify how existing data is checked:

- `ENABLE VALIDATE`: verifies existing data complies with the constraint and enforces the constraint on subsequent DML.
- `ENABLE NOVALIDATE`: does not re-verify all historical data, though the constraint is enforced for new/modified data per Oracle rules.

Example:

~~~sql
ALTER TABLE lab_products
ENABLE VALIDATE CONSTRAINT uq_lab_products_sku;
~~~

If existing data contains duplicate SKUs, `ENABLE VALIDATE` will fail. Do not use `NOVALIDATE` to hide violations without a cleanup plan; `VALIDATED` status is important information for both DBAs and the optimizer.

## 10. Impact of Unique/Nonunique Indexes on DML and Queries

### Write cost

Every index on a table must be maintained when DML changes key columns or corresponding ROWIDs:

- `INSERT` must create an index entry.
- `DELETE` must remove the index entry.
- `UPDATE` of a column inside an index key may need to delete the old entry and insert the new entry.
- `UPDATE` of a column not in an index key may not need to alter that index's entry, depending on structure and operation.

Unique indexes also need to check for key conflicts, including interactions with other concurrent transactions creating the same key. Thus, adding indexes to help queries is not free; it can increase CPU, redo, and I/O for `INSERT`/`UPDATE`/`DELETE`.

### Unique indexes can help the optimizer

The optimizer is aware of the uniqueness property of a unique index/constraint and can use that information to estimate cardinality or select appropriate join methods/access paths. For example, an equality condition on a validated unique key returns at most one row.

However, an index does not guarantee Oracle will always use it. If the table is small, the query returns a large percentage of rows, statistics are stale, or a full scan is cheaper, the optimizer may choose a full table scan.

### Nonunique indexes suit foreign keys and repeating filters

Columns such as `CUSTOMER_ID`, `DEPARTMENT_ID`, and `STATUS` often have many rows with the same value. A nonunique index can support queries like:

~~~sql
SELECT order_id, order_date, amount
FROM orders
WHERE customer_id = :customer_id;
~~~

If each customer has many orders, a nonunique index matches the semantics. A unique index would turn a one-to-many relationship into an unintended uniqueness constraint.

### Do not create a unique index to replace complex business checks

If a uniqueness rule depends on multiple tables, effective dates, statuses, or conditions involving other rows, a simple unique index may not be expressive enough. Model the rule with appropriate constraints, function-based indexes, triggers, or controlled transactional workflows. Triggers that check uniqueness via `SELECT` before `INSERT`/`UPDATE` can suffer from race conditions unless proper locking/constraints are used; prefer declarative constraints/indexes whenever possible.

## 11. Common Errors and Resolutions

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Unique index creation fails | Existing data has duplicate keys | Find and resolve duplicates before creating the index. |
| Adding UNIQUE constraint fails | Existing data violates uniqueness or supporting index is incompatible | Check duplicates, index type, and constraint state. |
| ORA-00001 | INSERT/UPDATE produces a duplicate key against a unique index/constraint | Identify the object name, check key-generation logic, and handle retries/idempotency. |
| ORA-01452 during CREATE UNIQUE INDEX | Duplicate keys exist in the data | `GROUP BY` key columns with `HAVING COUNT(*) > 1` to find duplicate groups. |
| ORA-02299 during ENABLE/VALIDATE UNIQUE constraint | Existing data contains duplicates | Clean up the data, then run `ENABLE VALIDATE`. |
| Foreign key cannot reference a standalone unique index | Oracle requires a PRIMARY KEY or UNIQUE constraint on the parent table | Create a `UNIQUE` constraint on the parent column and reference that constraint. |
| A customer can only have one order | Accidentally created a UNIQUE index/constraint on `CUSTOMER_ID` | Use a nonunique index if the relationship is one-to-many. |
| UNIQUE constraint allows multiple NULLs | Column is nullable and NULLs are permitted per Oracle semantics | Add `NOT NULL` if every row must have a value. |
| Constraint is UNIQUE but index is NONUNIQUE | Likely a `DEFERRABLE` constraint | Check `DEFERRABLE`/`DEFERRED` and `INDEX_NAME` in the dictionary. |
| Dropping constraint removes the index | Index was auto-created to enforce the constraint | Create/keep an independent index or use `KEEP INDEX` when appropriate. |
| Query does not use the index | Cost, selectivity, statistics, or expression mismatch | Check actual plan and stats; do not force an index solely because it exists. |
| INSERT slows down after adding many indexes | Index maintenance cost increased | Evaluate each index against read/write workload and remove redundant ones via change control. |

### Finding duplicates before creating a unique index

~~~sql
SELECT email,
       COUNT(*) AS duplicate_count
FROM app_users
WHERE email IS NOT NULL
GROUP BY email
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;
~~~

For composite keys:

~~~sql
SELECT department_id,
       email,
       COUNT(*) AS duplicate_count
FROM employees
GROUP BY department_id, email
HAVING COUNT(*) > 1;
~~~

`GROUP BY` also groups `NULL`s together for aggregation. Compare against unique constraint semantics and real data before concluding whether a group would definitely be rejected by a constraint.

## 12. Comprehensive Hands-On Lab

Examples use a learning schema with `CREATE TABLE` privileges and appropriate quota. DDL causes an implicit commit in Oracle; do not run on real business tables.

### Step 1: Create the customers table

~~~sql
CREATE TABLE lab_customers (
    customer_id NUMBER,
    email       VARCHAR2(100),
    status      VARCHAR2(20),
    CONSTRAINT pk_lab_customers PRIMARY KEY(customer_id),
    CONSTRAINT uq_lab_customers_email UNIQUE(email)
);
~~~

### Step 2: Test the UNIQUE constraint and NULLs

~~~sql
INSERT INTO lab_customers VALUES (1, 'a@example.com', 'ACTIVE');
INSERT INTO lab_customers VALUES (2, NULL, 'ACTIVE');
INSERT INTO lab_customers VALUES (3, NULL, 'INACTIVE');
~~~

Try inserting another row with email `a@example.com` and observe the error. Then query:

~~~sql
SELECT constraint_name,
       constraint_type,
       status,
       deferrable,
       index_name
FROM user_constraints
WHERE table_name = 'LAB_CUSTOMERS';
~~~

### Step 3: Create a nonunique index on status

~~~sql
CREATE INDEX ix_lab_customers_status
ON lab_customers(status);
~~~

Insert multiple customers with the same `STATUS` and observe that the nonunique index does not prevent duplicates.

### Step 4: Test a function-based unique index

~~~sql
CREATE UNIQUE INDEX ux_lab_customers_email_ci
ON lab_customers(LOWER(email));
~~~

Try inserting `Alice@example.com` and then `ALICE@example.com` for two different customers. Observe the conflict because `LOWER(email)` produces the same key.

### Step 5: Test conditional uniqueness

To test conditional uniqueness independently, drop the table-wide `UNIQUE` constraint and the unconditional function-based index created in earlier steps:

~~~sql
ALTER TABLE lab_customers
DROP CONSTRAINT uq_lab_customers_email;

DROP INDEX ux_lab_customers_email_ci;
~~~

Then create the conditional index:

~~~sql
CREATE UNIQUE INDEX ux_lab_customers_active_email
ON lab_customers (
    CASE WHEN status = 'ACTIVE' THEN LOWER(email) END
);
~~~

Try two `INACTIVE` rows with the same email and observe both can coexist. Try two `ACTIVE` rows with the same normalized email and observe the second row is rejected. Explain why the index only enforces uniqueness on keys produced by the `CASE` expression.

### Step 6: Test a foreign key supporting index

~~~sql
CREATE TABLE lab_orders (
    order_id NUMBER PRIMARY KEY,
    customer_id NUMBER,
    CONSTRAINT fk_lab_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES lab_customers(customer_id)
);

CREATE INDEX ix_lab_orders_customer
ON lab_orders(customer_id);
~~~

Insert multiple orders for the same customer. Observe that the child table index is nonunique while the FK still guarantees `customer_id` references a valid customer.

### Step 7: Inspect index and constraint metadata

~~~sql
SELECT i.index_name,
       i.uniqueness,
       c.constraint_name,
       c.constraint_type,
       c.deferrable,
       c.index_name AS constraint_index
FROM user_indexes i
LEFT JOIN user_constraints c
  ON c.index_name = i.index_name
WHERE i.table_name IN ('LAB_CUSTOMERS', 'LAB_ORDERS')
ORDER BY i.table_name, i.index_name;
~~~

Explain why an index can have no corresponding constraint and why an index backing a constraint may not have the same name as the constraint.

### Step 8: Clean up data

~~~sql
DROP TABLE lab_orders PURGE;
DROP TABLE lab_customers PURGE;
~~~

Run only after completing the exercise and when you no longer need the data. `DROP TABLE` is DDL with an implicit commit; `PURGE` bypasses the Recycle Bin.

## 13. Self-Check Questions

1. **What is a unique index?** An index that guarantees key entries do not duplicate per Oracle unique index rules.
2. **What is a nonunique index?** An index that allows multiple rows to share the same key.
3. **Does creating a unique index automatically create a UNIQUE constraint?** No; indexes and constraints are separate objects.
4. **Can a UNIQUE constraint be enforced by an index?** Yes; Oracle normally uses an appropriate index to check uniqueness.
5. **How does PRIMARY KEY differ from a UNIQUE constraint?** Primary key disallows NULLs and there is only one primary key per table; a table can have multiple unique constraints.
6. **Does a UNIQUE constraint on a nullable column allow multiple NULLs?** Yes; if the business forbids NULLs, add `NOT NULL`.
7. **What does a composite unique index guarantee?** The combination of values across the entire column list is unique per Oracle semantics.
8. **Why can a DEFERRABLE constraint use a nonunique index?** To allow temporary duplicate keys within a transaction and validate when the constraint must be checked.
9. **What is SET CONSTRAINTS used for?** Changing the checking timing for `DEFERRABLE` constraints within a transaction.
10. **Can a foreign key reference a standalone unique index?** No; it requires a `PRIMARY KEY` or `UNIQUE` constraint on the parent table.
11. **Does Oracle automatically create an index for a foreign key on a child table?** No; DBAs/developers decide whether to create a nonunique index based on workload.
12. **When is a function-based unique index useful?** When uniqueness must be evaluated on a normalized value or expression such as `LOWER(email)`.
13. **How can conditional uniqueness be expressed?** Using a unique function-based index with `CASE` to generate keys only for rows in the controlled status.
14. **Where can you see which index supports a constraint?** `USER_CONSTRAINTS.INDEX_NAME`, combined with `USER_INDEXES.UNIQUENESS`.
15. **Why must duplicates be resolved before creating a unique index?** A unique index cannot be created if existing data contains duplicate keys.
16. **What is the impact of increasing the number of indexes?** It can speed up queries, but increases DML maintenance work, redo, I/O, and storage space.

Unique/nonunique describes an **index** property, whereas `PRIMARY KEY` and `UNIQUE` describe **integrity rules**. In Oracle, a unique constraint typically relies on an index for enforcement; a `DEFERRABLE` constraint may require a nonunique index to allow temporary duplicate states. Inspect the dictionary rather than inferring from index names, choose nonunique indexes for one-to-many relationships such as foreign keys when the workload warrants it, and use function-based or conditional unique indexes only when normalization or conditional uniqueness rules are clearly defined.
