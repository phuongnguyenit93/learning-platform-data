# Primary Keys, Foreign Keys, Unique Constraints, and Data Integrity

## 1. Objectives and Context

After this lesson, you will be able to:

- Distinguish `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `NOT NULL`, and `CHECK`, and choose the constraint matching each data rule.
- Design parent–child relationships, single/composite keys, and behavior when updating or deleting referenced records.
- Explain why checks in Java/Spring cannot replace database constraints, especially under concurrent requests.
- Create and test a SQL schema, identify constraint errors, handle them via Spring JDBC or JPA, and roll out schema changes safely.

Suppose an application manages customers, orders, and order line items. Each customer has a distinct identifier; emails cannot repeat; each order belongs to a real customer; within an order, line numbers cannot repeat; and line item quantities must be positive. If you only check with a `SELECT` before `INSERT`, data can still become corrupted when two requests run concurrently. The final safeguard for these invariants is the database (DB).

**Data integrity** is the state in which data adheres to declared rules across all valid operations, even when the application crashes, requests run in parallel, or another program writes to the DB.

## 2. Layers of Integrity to Distinguish

| Category | Question to Guarantee | Common Tools |
| --- | --- | --- |
| Entity integrity | How is a record uniquely identified? | `PRIMARY KEY` |
| Referential integrity | Does a child record reference a valid parent record? | `FOREIGN KEY` |
| Business uniqueness | Can emails or order numbers repeat? | `UNIQUE`, unique index |
| Domain integrity | Is the value required and within a valid domain? | `NOT NULL`, `CHECK`, data types |
| Cross-operation consistency | Do all operations succeed together or cancel together? | Transaction, `@Transactional` |
| Multi-row / multi-table rules | Are totals, balances, limits, or states valid? | Transactions, concurrency locks, sometimes specialized triggers/constraints |

A DB constraint protects a declared invariant. A transaction ensures a group of changes commits or rolls back together; the two concepts complement each other. API validation helps report errors earlier and more clearly, but it does not replace DB constraints.

## 3. Primary Key: Unique Identifier of Each Row

`PRIMARY KEY` (PK) identifies a row in a table. According to the relational model and standard implementations, a PK must be **unique** and **non-NULL**. A table has at most one PK constraint, though that PK can span multiple columns.

Single-column key example:

```sql
CREATE TABLE categories (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL
);
```

`id` is a DB-generated surrogate key; do not treat ID continuity as a business guarantee, because sequences can skip numbers when transactions roll back. Compared to a natural key (such as a controlled identification number), a surrogate key is usually more stable when business attributes can change.

Composite key example:

```sql
CREATE TABLE enrollment (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    CONSTRAINT pk_enrollment PRIMARY KEY (student_id, course_id)
);
```

The pair `(student_id, course_id)` is the identifier; `student_id` or `course_id` individually can repeat. This example only illustrates the PK: if the system has `students` and `courses` tables, you must add the corresponding FKs to ensure both IDs actually exist. A PK **does not automatically** create a referential relationship.

In PostgreSQL, declaring a PK automatically creates a unique B-tree index for uniqueness checking and key lookups. An index does not make a PK a business rule; choosing a PK requires considering stability, referenceability, and key size.

**Design consideration:** if a table uses `id` as its PK yet the domain requires `(tenant_id, external_code)` to be unique, you must add `UNIQUE (tenant_id, external_code)`. A PK on `id` does not protect the uniqueness of that pair.

## 4. UNIQUE: Non-Duplicate Rules Outside the Primary Key

`UNIQUE` prevents two rows from having the same combination of values in the declared columns. A table can have multiple `UNIQUE` constraints.

```sql
CREATE TABLE accounts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username VARCHAR(80) NOT NULL,
    tenant_id BIGINT NOT NULL,
    CONSTRAINT uq_accounts_tenant_username UNIQUE (tenant_id, username)
);
```

In this example, a username can be identical across two different tenants, but cannot repeat within the **same** tenant. If usernames must be unique system-wide, the constraint must apply only to `username`.

### 4.1. UNIQUE Is Not Identical to PRIMARY KEY

- `PRIMARY KEY`: unique, non-NULL; the row's primary identifier; at most one PK per table.
- `UNIQUE`: independent of the PK; multiple constraints per table allowed; rules for `NULL` depend on the DBMS and declaration.
- `UNIQUE (a, b)` checks the pair `(a, b)` as a whole; it does not mean `a` and `b` must each be unique individually.

**Common NULL pitfall:** in PostgreSQL, `UNIQUE (email)` by default allows multiple rows with `email IS NULL`, because NULL values are treated as distinct when checking uniqueness. To require an email to be both present and unique, declare **`email ... NOT NULL UNIQUE`**. PostgreSQL 15+ also supports `UNIQUE NULLS NOT DISTINCT` if you want multiple NULLs treated as duplicates. Other DBMSs may have different semantics; do not generalize from one DBMS to another.

### 4.2. Normalization and Business Uniqueness

If `Alice@Example.test` and `alice@example.test` must be treated as the same email, `UNIQUE (email)` on raw strings may not satisfy the rule; the outcome depends on collation and data type. A PostgreSQL-specific option is a unique expression index:

```sql
CREATE UNIQUE INDEX uq_accounts_username_lower
    ON accounts (tenant_id, lower(username));
```

This statement adds a rule forbidding duplicate lowercase usernames within the same tenant. You must decide on Unicode normalization, whitespace, and comparison scope policies before implementing; `lower` does not solve every international normalization problem.

With soft deletes, the requirement that "only active rows may not duplicate" often uses a PostgreSQL **partial unique index**, such as `CREATE UNIQUE INDEX ... ON ... (email) WHERE deleted_at IS NULL`. This is a DBMS-specific feature, not standard `UNIQUE` syntax applicable across every system.

## 5. Foreign Key: Protecting Referential Relationships

`FOREIGN KEY` (FK) requires values in a child table to point to valid values of a referenced key in a parent table. In PostgreSQL, referenced columns are usually a PK, a UNIQUE constraint, or a suitable non-partial unique index. An FK protects the relationship; it **does not imply** that the child and parent tables are updated in the same transaction, nor does it automatically determine every deletion policy if you have not declared one.

```sql
CREATE TABLE departments (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE employees (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    department_id BIGINT NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    CONSTRAINT fk_employees_department
        FOREIGN KEY (department_id) REFERENCES departments (id)
        ON DELETE RESTRICT
);
```

An employee cannot be saved with `department_id = 999` if there is no department `id = 999`. While employees still reference it, `ON DELETE RESTRICT` prevents deleting the department. `department_id NOT NULL` also prevents an "employee without a department"; an FK alone without `NOT NULL` can still allow NULL values.

### 5.1. Actions on Parent Deletion

| Option | Effect on Child Rows When Parent Is Deleted | When to Consider |
| --- | --- | --- |
| `NO ACTION` (often the default) | FK violation if references still exist at check time; check can be deferred if the FK is declared deferrable and the DB supports it | Do not want deletion while dependencies remain |
| `RESTRICT` | Blocks deletion while referenced; in PostgreSQL, the check cannot be deferred like `NO ACTION` | Relationship needs strict immediate protection at operation time |
| `CASCADE` | Automatically deletes referencing child rows | Components dependent on parent's lifecycle, such as order line items belonging to an order |
| `SET NULL` | Sets child row's FK to NULL | Optional relationship; FK column must allow NULL |
| `SET DEFAULT` | Assigns default value to FK | Valid only if the default value satisfies the FK |

For `ON UPDATE`, similar mechanisms apply when the referenced key changes. In practice, avoid updating PK identifiers unnecessarily; choosing `CASCADE` is a data-lifecycle decision, not a way to "make FK errors go away."

**Important distinction:** DB `ON DELETE CASCADE` differs from `CascadeType.REMOVE` in JPA. One is enforced by the DB when executing the parent SQL delete; the other is an operation-propagation mechanism across entities in the persistence context. Do not assume the two are equivalent in execution timing, lifecycle callbacks, and cache behavior.

### 5.2. Composite Foreign Keys and NULL

A composite FK must reference a matching unique key column set in the parent table, in the exact mapped order. For multi-column FKs, PostgreSQL defaults to `MATCH SIMPLE`: it may skip the referential check if any component is NULL. `MATCH FULL` accepts either all components NULL or all valid; to require the link to exist, still declare `NOT NULL` on the relevant columns. This is one reason not to assume an FK automatically replaces `NOT NULL`.

## 6. NOT NULL, CHECK, and Constraint Scope

`NOT NULL` ensures a column has a value (it does not ensure a string is non-empty). `CHECK` evaluates an expression per row; for instance, `CHECK (quantity > 0)` prevents zero or negative quantities. In PostgreSQL, `CHECK` is considered satisfied if the expression evaluates to TRUE **or NULL/UNKNOWN**; therefore, combine it with `NOT NULL` when the column is required.

```sql
CREATE TABLE prices (
    sku VARCHAR(40) PRIMARY KEY,
    amount NUMERIC(12, 2) NOT NULL,
    currency CHAR(3) NOT NULL,
    CONSTRAINT ck_prices_amount CHECK (amount >= 0),
    CONSTRAINT ck_prices_currency CHECK (currency IN ('VND', 'USD'))
);
```

You can use `CHECK` for single-row rules (such as `end_at > start_at`), whereas rules involving sums across multiple rows or multiple tables typically cannot be modeled with a standard `CHECK`. In those cases, you need transactional operations, appropriate concurrency/locking mechanisms, and sometimes triggers or a different data model. Java Bean Validation such as `@NotBlank`, `@Email`, and `@Positive` improves input user experience; only the DB protects data from every client.

## 7. Complete Example: PostgreSQL Schema for Orders

The following statements run on **an empty test schema/database**, using PostgreSQL syntax. Parent tables are created before child tables. Constraint names are chosen explicitly for readable logs and migration management.

```sql
CREATE TABLE customers (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    email VARCHAR(254) NOT NULL,
    full_name VARCHAR(120) NOT NULL,
    CONSTRAINT pk_customers PRIMARY KEY (id),
    CONSTRAINT uq_customers_email UNIQUE (email)
);

CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY,
    customer_id BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL,
    total_amount NUMERIC(12, 2) NOT NULL,
    CONSTRAINT pk_orders PRIMARY KEY (id),
    CONSTRAINT uq_orders_number UNIQUE (order_number),
    CONSTRAINT ck_orders_total_amount CHECK (total_amount >= 0),
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id)
        ON DELETE RESTRICT
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(50) NOT NULL,
    qty INTEGER NOT NULL,
    CONSTRAINT pk_order_items PRIMARY KEY (order_id, line_no),
    CONSTRAINT ck_order_items_qty CHECK (qty > 0),
    CONSTRAINT fk_order_items_order
        FOREIGN KEY (order_id) REFERENCES orders (id)
        ON DELETE CASCADE
);

CREATE INDEX idx_orders_customer_id ON orders (customer_id);
```

**Design explanation:**

- `customers.id` and `orders.id` are surrogate PKs; `order_items` uses the composite PK `(order_id, line_no)` because the line number is only unique within an order.
- `uq_customers_email` and `uq_orders_number` are two business invariants independent of the PKs.
- `fk_orders_customer` disallows orphan orders; `RESTRICT` protects order history when deleting a customer.
- `fk_order_items_order` chooses `CASCADE` because line items depend directly on the order; deleting an order deletes that order's line items.
- `qty` and `total_amount` have both `NOT NULL` and `CHECK`; without both constraints, NULL or out-of-domain values could slip through.
- `idx_orders_customer_id` improves queries by customer and referential checks when deleting/updating a customer. In PostgreSQL, an FK **does not automatically create an index on the child table**. The composite PK `(order_id, line_no)` already creates an index prefixed by `order_id`, suiting many order-scoped queries.

### 7.1. Valid Data and Expected Result

Run in order in the newly created empty database:

```sql
INSERT INTO customers (email, full_name)
VALUES ('an@example.test', 'An Nguyen'),
       ('binh@example.test', 'Binh Tran');

INSERT INTO orders (customer_id, order_number, total_amount)
VALUES (1, 'ORD-001', 120.00);

INSERT INTO order_items (order_id, line_no, sku, qty)
VALUES (1, 1, 'SKU-01', 2);

SELECT c.email, o.order_number, i.line_no, i.sku, i.qty
FROM customers c
JOIN orders o ON o.customer_id = c.id
JOIN order_items i ON i.order_id = o.id
ORDER BY o.id, i.line_no;
```

The logical result of `SELECT` is **one row**: `an@example.test | ORD-001 | 1 | SKU-01 | 2`. `ID = 1` in this example relies on fresh tables and fresh sequences; in real environments, capture the ID returned by `INSERT ... RETURNING id` rather than hard-coding it.

### 7.2. Testing Rejected Cases

**Run each statement independently** after inserting the valid data above. If executed inside the same PostgreSQL transaction and one SQL error occurs, that transaction is marked aborted; you must `ROLLBACK` or use a savepoint before running the next statement.

```sql
-- Duplicate email: uq_customers_email
INSERT INTO customers (email, full_name)
VALUES ('an@example.test', 'Another An');

-- Non-existent customer: fk_orders_customer
INSERT INTO orders (customer_id, order_number, total_amount)
VALUES (999, 'ORD-002', 10.00);

-- Email must not be NULL
INSERT INTO customers (email, full_name)
VALUES (NULL, 'No Email');

-- Invalid quantity: ck_order_items_qty
INSERT INTO order_items (order_id, line_no, sku, qty)
VALUES (1, 2, 'SKU-02', 0);

-- Duplicate composite PK (order_id, line_no)
INSERT INTO order_items (order_id, line_no, sku, qty)
VALUES (1, 1, 'SKU-OTHER', 1);

-- Cannot delete customer 1 while referencing orders still exist
DELETE FROM customers WHERE id = 1;
```

Expected outcome: all statements above are rejected by the DB, while the previously inserted valid data remains intact (if each statement runs in its own transaction). In PostgreSQL, common SQLSTATEs are: `23505` = PK/UNIQUE violation; `23503` = FK violation; `23502` = NOT NULL violation; `23514` = CHECK violation. SQLSTATE and constraint name metadata are more reliable than parsing raw error text from the DB.

To verify cascade behavior after finishing the tests above:

```sql
DELETE FROM orders WHERE id = 1;
SELECT COUNT(*) AS remaining_items FROM order_items WHERE order_id = 1;
```

`remaining_items` equals `0`: when the order is deleted, the DB deletes its line items. Afterward, customer `id = 1` is no longer blocked from deletion by this order, unless other relationships exist.

## 8. Integrity Under Concurrent Requests

An error-prone implementation:

```text
Request A: SELECT checks that email X does not exist yet -> TRUE
Request B: SELECT checks that email X does not exist yet -> TRUE
Request A: INSERT email X -> succeeds
Request B: INSERT email X -> ?
```

Without `UNIQUE` in the DB, both requests can write duplicate rows. With `UNIQUE`, the DB lets one operation succeed and rejects the other or requires conflict handling per transaction semantics. `existsByEmail(...)` is useful for showing an early message, but **cannot serve as the lock protecting uniqueness**.

In PostgreSQL, when business logic wants to create only if absent, you can consider `INSERT ... ON CONFLICT (...) DO NOTHING/DO UPDATE`. This is a SQL-level idempotency/upsert strategy depending on business conditions, and does not mean you should drop `UNIQUE`. If you need to distinguish "newly created" from "already existed," check the actual result of the write statement.

Constraints also interact with transactions: an order and its line items must be written in the same transaction to avoid a state where an order exists without items if a subsequent operation fails. However, a transaction **does not automatically provide** uniqueness or FK checks; both must be used together.

## 9. Applying in Spring JDBC

Spring `JdbcTemplate` helps bind parameters, manage JDBC resources, and translate many SQL errors into the `DataAccessException` hierarchy. The example below is **a class used in a Spring Boot 3.x / Spring Framework 6.x project configured with a PostgreSQL DataSource and `spring-boot-starter-jdbc`**; it is not a standalone plain Java program runnable with `javac` without dependencies.

File `OrderWriter.java`:

```java
package example.orders;

import java.math.BigDecimal;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWriter {

    public record ItemInput(int lineNo, String sku, int quantity) {}

    private final JdbcTemplate jdbc;

    public OrderWriter(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public long createOrder(
            long customerId,
            String number,
            BigDecimal total,
            List<ItemInput> items
    ) {
        Long orderId = jdbc.queryForObject(
                """
                INSERT INTO orders (customer_id, order_number, total_amount)
                VALUES (?, ?, ?)
                RETURNING id
                """,
                Long.class,
                customerId,
                number,
                total
        );
        if (orderId == null) {
            throw new IllegalStateException("Database did not return order id");
        }

        for (ItemInput item : items) {
            jdbc.update(
                    """
                    INSERT INTO order_items (order_id, line_no, sku, qty)
                    VALUES (?, ?, ?, ?)
                    """,
                    orderId,
                    item.lineNo(),
                    item.sku(),
                    item.quantity()
            );
        }
        return orderId;
    }
}
```

**Execution flow explanation:**

1. Spring invokes the method through a transaction-managing bean/proxy; `@Transactional` starts or joins a transaction according to configuration.
2. `INSERT ... RETURNING id` obtains the real ID from the DB (PostgreSQL syntax) rather than guessing IDs sequentially.
3. Each line item `INSERT` uses the returned ID, so the FK to `orders` is valid.
4. If the customer does not exist, the order number is duplicated, `qty <= 0`, or the line PK is duplicated, the DB rejects the operation. When the error is translated into an unchecked exception and propagates out of the method, the transaction by default rolls back both the order and any inserted items.
5. On success, the transaction commits. If the order total must strictly match the sum of line items, you need appropriate pricing structures/calculation logic; the schema shown above **does not** enforce that sum rule by itself.

`JdbcTemplate.update(sql, args...)` returns the affected row count for regular `INSERT/UPDATE/DELETE` statements. With `RETURNING`, the example uses `queryForObject` to receive the result row. `?` is a bind parameter, avoiding concatenating input values into SQL strings.

**Proxy note:** calling `this.createOrder(...)` from another method within the same object may bypass the Spring proxy, causing `@Transactional` not to apply as expected under standard proxy configuration. Place the transaction boundary on a service called from another bean or configure accordingly.

## 10. JPA/Hibernate Mapping and Limits of Annotations

In Spring Data JPA, `@Id` marks the entity identifier; `@Table(uniqueConstraints = ...)` or `@Column(unique = true)` can express schema-generation intent, while `@JoinColumn` describes the FK in an entity association. Example of **a mapping snippet inside an entity of a JPA project**, not a standalone application:

```java
import jakarta.persistence.*;

@Entity
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_customers_email",
        columnNames = "email"
    )
)
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "email", nullable = false, length = 254)
    private String email;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    protected Customer() {}

    public Customer(String email, String fullName) {
        this.email = email;
        this.fullName = fullName;
    }
}
```

In the `Order` entity, the association can be declared as follows:

```java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(
    name = "customer_id",
    nullable = false,
    foreignKey = @ForeignKey(name = "fk_orders_customer")
)
private Customer customer;
```

The second snippet is **only a field mapping**, which must reside in a valid `@Entity` class with a PK and other attributes. `optional = false` expresses intent in the entity model; `nullable = false` reflects the non-NULL column requirement during DDL generation. `ON DELETE RESTRICT/CASCADE` behavior must be finalized in DB migrations; do not infer it from `@ManyToOne` or `CascadeType`.

In production, manage DDL with **Flyway/Liquibase** (or a controlled migration process), verify the actual schema after deployment, and do not rely solely on `hibernate.hbm2ddl.auto=update` to infer constraints on a system with existing data.

`JpaRepository.save(...)` may only queue operations in the persistence context; constraint errors may surface at `flush` or `commit`, not necessarily on the `save` line itself. `saveAndFlush(...)` pushes changes to the DB earlier, yet **is not synonymous with commit**. Therefore, design exception handling outside the appropriate transaction boundary and do not assume a `try/catch` around `save` always catches every uniqueness error.

## 11. Classifying Data Errors in Spring

When using Spring JDBC, exception translation typically converts constraint violations into `org.springframework.dao.DataIntegrityViolationException` (or subclasses such as `DuplicateKeyException` depending on driver/translator). With JPA, the exception type and timing also depend on the provider and translation mechanism; do not hard-code a single path.

Sensible handling flow:

```text
HTTP request
  -> validate input data (DTO/Bean Validation)
  -> Service @Transactional
  -> Repository/JdbcTemplate
  -> DB checks PK, FK, UNIQUE, NOT NULL, CHECK
  -> DB accepts or returns constraint violation
  -> Spring translates error when supported
  -> transaction rollback
  -> API converts error into a safe, meaningful response
```

- **Duplicate business key:** typically return `409 Conflict`, e.g., email already in use.
- **Non-existent reference:** return `400/404/422` depending on resource design and API contract, after confirming the exact cause.
- **Out-of-domain input:** typically `400 Bad Request` or `422 Unprocessable Content`; validate upfront to send helpful feedback.
- **Unexpected internal invariant violation:** log the constraint name, correlation ID, and root cause; never expose raw stack traces/SQL or sensitive information to clients.

Do not map every `DataIntegrityViolationException` to "duplicate email": this exception class can also represent FK, CHECK, or NOT NULL violations. Prefer distinguishing by **explicitly named constraints**, SQLSTATE/vendor codes when truly necessary, and business context. Do not parse raw messages that depend on version or locale. Inside a PostgreSQL transaction, once a SQL statement fails, the entire transaction usually must roll back; catching and continuing to write on the already-aborted transaction does not recover it.

## 12. Migrations and Operations on Live Data

On an empty database, `CREATE TABLE ... CONSTRAINT ...` is simple. On a table with millions of rows, adding a constraint requires inspection and preparation:

1. **Define the invariant** in business terms: "system-wide unique email" or "unique per tenant"? "Does deleting a customer delete order history?"
2. **Find violating data first:** duplicate groups, orphan FKs, NULL values, negative quantities. Agree on a data-cleanup policy with system owners.
3. **Design an ordered migration:** clean up/backfill, create indexes where appropriate, add constraints, verify success. For large tables, check locking impact and mechanisms like PostgreSQL's `NOT VALID`/`VALIDATE CONSTRAINT` for supported constraint types; do not assume they apply to every type.
4. **Deploy compatibly:** old and new code may run concurrently during a rolling deployment. Do not add `NOT NULL` before all write paths satisfy it.
5. **Test against a real DBMS:** use integration tests (e.g., Testcontainers PostgreSQL) for PK/FK/UNIQUE/CHECK, deletion order, and transaction rollback. Different embedded DBs may differ in NULL, constraint, DDL, and locking semantics.
6. **Monitor post-deployment:** error rate by constraint, write latency, lock contention, and query plans for queries affected by new indexes.

Sample pre-migration inspection queries (adjust table/column names to your actual schema):

```sql
-- Duplicate emails in a table with existing data
SELECT email, COUNT(*) AS occurrences
FROM customers
GROUP BY email
HAVING COUNT(*) > 1;

-- Orphan orders before adding FK (if old schema did not have FK)
SELECT o.id, o.customer_id
FROM orders o
LEFT JOIN customers c ON c.id = o.customer_id
WHERE c.id IS NULL;

-- Out-of-domain order items before adding CHECK
SELECT order_id, line_no, qty
FROM order_items
WHERE qty IS NULL OR qty <= 0;
```

Do not automatically delete duplicate or orphan data just to make a migration pass. You must know which record is canonical and whether records should be merged, archived, or reported to related systems.

## 13. Common Mistakes and Self-Check

| Design/Coding Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Calling `existsByEmail` then `save` alone | Race condition between two requests | Add `UNIQUE` in the DB and handle conflicts |
| Putting `@NotNull` only on DTO/entity | Other clients can bypass validation | Add `NOT NULL` in the DB |
| Assuming FK blocks NULL automatically | FKs often allow NULL | Add `NOT NULL` if the relationship is required |
| Adding `UNIQUE(a,b)` when `a` alone must be unique | Composite unique checks the combination | Declare the exact unique key matching the invariant |
| Assuming FK auto-creates an index on child table | PostgreSQL does not create that index automatically | Review query patterns, add an index if needed |
| Using `ON DELETE CASCADE` on data needing history | Deleting parent unintentionally deletes children | Choose `RESTRICT` or an appropriate retention model |
| Using transactions alone without constraints | Atomicity does not prevent duplicate emails | Combine transactions and DB constraints |
| Treating JPA `save` as already written/committed | JPA can defer SQL until flush/commit | Test exception timing and transaction boundaries |
| Catching errors and continuing SQL in an aborted PostgreSQL transaction | The transaction must be rolled back or use savepoints | Let rollback happen properly; design controlled retries |
| Updating production schema automatically via JPA | Risk of DDL and constraint drift | Manage migrations and verify the actual schema |

## 14. Practice Exercises

**Exercise 1 — Design:** A multi-tenant document management app has `tenant_id`, `document_code`, `owner_id`, and `status`. Requirements: document code is unique **within a tenant**, owner must exist, and status only accepts `DRAFT`, `PUBLISHED`, or `ARCHIVED`. Choose the PK, composite UNIQUE, FK, NOT NULL, and CHECK constraints, and explain the behavior when deleting an owner.

**Exercise 2 — Concurrency:** Two requests concurrently create customers with the same email. Write a timeline allowing both past the `SELECT` step, then explain the result when the DB has `UNIQUE` and how the API should report the conflict.

**Exercise 3 — Integration testing:** Use the schema in section 7 and test four cases: valid creation, duplicate `order_number`, nonexistent `customer_id`, and `qty = 0`. Create an order and line items in one transaction, intentionally trigger an error on the second item, and verify no order was committed. Test `RESTRICT` and `CASCADE` behaviors separately.

**Answer hints:** Exercise 1 can use a surrogate `id` as PK, `UNIQUE(tenant_id, document_code)`, `FOREIGN KEY(owner_id)` to the owner table's PK, `owner_id NOT NULL`, and `CHECK(status IN (...))`; the owner deletion policy depends on document retention rules and usually warrants `RESTRICT`. Exercise 2 shows `UNIQUE` is the concurrency enforcement point. Exercise 3 must inspect DB state **after rollback/commit**, not just check that an exception was thrown.

## 15. Pre-Implementation Decision Checklist

- Does each table have a stable identifying key? Is a composite key genuinely the business identifier?
- Do all required relationships have `FK + NOT NULL` and an agreed `ON DELETE/UPDATE` behavior?
- Is uniqueness scoped table-wide, per tenant, per status, or over a normalized expression?
- Does the DB have accurate rules for NULL, collation, soft delete, and concurrency handling?
- Do domain rules have `NOT NULL/CHECK`, and do multi-table operations have appropriate transactions?
- Do indexes for queried keys and the referencing side of FKs match actual query patterns?
- Has the migration scanned for violating data, been tested on a real DBMS, and included rollback/observability plans?
- Are errors sent to clients meaningful without leaking SQL, stack traces, or sensitive data?

**Takeaway:** PK answers "who is this row?", UNIQUE answers "which value or combination cannot repeat?", FK answers "is this relationship valid?", NOT NULL/CHECK answers "is this value in the allowed domain?", and a transaction answers "is this group of changes consistent on commit/rollback?". Describe invariants first, enforce constraints in the DB, and then build validation and error handling in Spring to provide a proper experience.

## References

- PostgreSQL — Constraints: https://www.postgresql.org/docs/current/ddl-constraints.html
- Spring Framework — JDBC core and exception translation: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Transactional annotations and rollback: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Data JPA — JpaRepository (flush, saveAndFlush): https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html
