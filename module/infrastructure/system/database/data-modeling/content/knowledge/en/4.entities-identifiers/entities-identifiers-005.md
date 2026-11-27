# Simple Keys, Composite Keys, and Contextual Uniqueness Scope

## 1. Why Must Keys and Uniqueness Scope Be Defined?

A data model must distinguish each object and reject records that violate business identification rules. A key provides a way to identify a record; a unique constraint guarantees that a value or combination of values does not repeat within a defined scope.

Some values must be unique across the entire system, such as an order's identifier. Other values are unique only within a context: a meeting room code unique within a building, a line item number unique within an order, or a username unique within an organization. Ignoring scope can cause the model to reject valid data or permit duplicate data that breaks business rules.

This lesson focuses on three related decisions:

- **Simple key:** a single attribute sufficient to identify a record.
- **Composite key:** two or more attributes combined to identify a record.
- **Uniqueness scope:** where and under what conditions values must be unique—such as globally, per organization, per parent record, over time, or only among active records.

These decisions lie at the core of data modeling. They affect primary keys, foreign keys, table joins, data ingestion, concurrency handling, and how integrity is preserved as the system evolves.

## 2. Key Concepts to Distinguish

### 2.1. Superkey and Candidate Key

A **superkey** is a set of attributes capable of uniquely identifying a record in a relation. The attribute set may contain more attributes than necessary.

A **candidate key** is a minimal superkey: no attribute can be removed without losing the guarantee of unique identification.

For example, a `customer` table has the attributes:

- `customer_id`: customer ID.
- `email_normalized`: email normalized according to system rules.
- `full_name`: full name.
- `phone`: phone number.

Suppose `customer_id` and `email_normalized` are both unique system-wide. Then each attribute individually can be a candidate key. The combination `(customer_id, email_normalized)` also uniquely identifies a record, yet is not minimal because either `customer_id` or `email_normalized` alone suffices. That combination is a superkey, not a candidate key.

Minimality matters greatly when designing composite keys. Do not add attributes to a key merely to make it look more "specific." Every component must be necessary for uniqueness under defined rules.

### 2.2. Primary Key and Alternate Key

Among candidate keys, the model selects one key as the **primary key**. The remaining candidate keys are **alternate keys**.

For example:

```sql
CREATE TABLE customer (
    customer_id BIGINT PRIMARY KEY,
    email_normalized VARCHAR(320) NOT NULL UNIQUE,
    full_name VARCHAR(200) NOT NULL
);
```

Here:

- `customer_id` is the primary key.
- `email_normalized` is an alternate key protected by a `UNIQUE` constraint.

A table has only one primary key, though a primary key can consist of multiple columns. A table can also have multiple unique constraints to protect other candidate keys.

Never assume only the primary key needs uniqueness. If email must be unique under business rules, creating only a regular (non-unique) index will not stop two records from sharing an email. Use an appropriate unique constraint or unique index.

### 2.3. Natural Key and Surrogate Key

A **natural key** comes from data or business rules, such as an ISBN, tax ID, SKU, or employee number. Natural keys can be readable and helpful when communicating with users, yet require evaluating stability, issuance scope, editability, and security concerns.

A **surrogate key** is a system-generated technical identifier, such as an auto-incrementing number or UUID. It typically carries no direct business meaning and keeps record links stable when business attributes change.

For example, a customer can change their email while `customer_id` stays unchanged. If email were used as the primary key, changing email would require updating every foreign key referencing that customer. Using a surrogate key decouples internal identity from mutable business attributes.

However, using a surrogate key does not eliminate the need to protect natural keys. If email must be unique within a tenant, the system still needs `UNIQUE (tenant_id, email_normalized)`. The surrogate key answers "which record?", while the unique constraint enforces "which business value cannot be duplicated?".

## 3. Simple Keys

A simple key is a key consisting of a single attribute. For example, `order_id` can uniquely identify an order:

```sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    status VARCHAR(30) NOT NULL
);
```

Each `order_id` value belongs to only one order. Simple keys are typically easy to use in foreign keys, URLs, APIs, and lookup queries.

### 3.1. When Is a Simple Key Appropriate?

A simple key fits when a single stable attribute suffices to identify each record. For example:

- A UUID assigned by the system to each transaction.
- A dossier code issued uniquely across the entire system.
- An internal identifier that does not change over the record's lifecycle.

A simple key can be a natural key or a surrogate key. What matters is that uniqueness matches business scope, values are not improperly reused, and other tables can reference it stably.

### 3.2. Considerations When Choosing a Simple Key

An attribute that appears unique right now is not guaranteed to be a good key. Check:

- Can the value change?
- Can the value be reissued after a record is deleted?
- Does any other source also generate this code?
- Is its scope limited by organization, branch, or country?
- Does the value contain sensitive data?
- Are the data type and length suitable for foreign keys and indexes?

For instance, a phone number is not always a stable identifier: users can change numbers, or a number can be reassigned to someone else. If using phone number as a candidate key, clarify verification, reuse, and change-history rules.

## 4. Composite Keys

A composite key consists of two or more attributes. Only the full combination uniquely identifies a record; individual components may repeat.

For example, an order has multiple order lines. The line sequence number is unique only within each order, not across the entire system. You can use the pair `(order_id, line_no)` as the primary key:

```sql
CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(18, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no)
);
```

Sample data:

| order_id | line_no | product_id | quantity |
|---:|---:|---:|---:|
| 7001 | 1 | 120 | 2 |
| 7001 | 2 | 135 | 1 |
| 7002 | 1 | 120 | 4 |

`line_no = 1` appears in both order 7001 and 7002, so it is not globally unique. However, the pair `(order_id, line_no)` does not repeat, and therefore identifies a specific order line.

### 4.1. When Is a Composite Key Appropriate?

A composite key fits when a record's identity is genuinely determined by multiple components within the same scope. Examples:

- `(order_id, line_no)`: a line item within an order.
- `(student_id, course_id, term_id)`: a student's course enrollment in a term.
- `(building_id, room_code)`: a room within a building.
- `(tenant_id, username_normalized)`: a username within a tenant.
- `(product_id, warehouse_id)`: inventory balance of a product at a warehouse.

In these examples, the first component or subset of components establishes context; the remaining component identifies the object within that context.

### 4.2. Advantages and Costs of Composite Keys

Advantages:

- Directly expresses the business identification rule.
- Can eliminate a technical ID column when the natural combination is already stable.
- Clarifies dependence on a parent record or context.
- Helps enforce uniqueness with a database-level constraint.

Costs to consider:

- Referencing foreign keys must carry all components of the composite key.
- Queries and APIs may need to pass multiple values.
- Indexes on composite keys are larger than single-column keys when containing multiple or wide columns.
- Changing one component of the key can impact many referencing relationships.
- Column order in a composite index affects which query patterns can utilize the index.

Not all composite keys are bad. What matters is that the key accurately reflects business rules and carries costs appropriate for how the system accesses data.

### 4.3. Composite Keys in Many-to-Many Relationships

A junction table often has a composite key made of two foreign keys:

```sql
CREATE TABLE student_course (
    student_id BIGINT NOT NULL,
    course_id BIGINT NOT NULL,
    enrolled_at TIMESTAMP NOT NULL,
    PRIMARY KEY (student_id, course_id),
    FOREIGN KEY (student_id) REFERENCES student(student_id),
    FOREIGN KEY (course_id) REFERENCES course(course_id)
);
```

The composite key guarantees a student cannot have two enrollment records for the same course under the rule in this example.

If the business allows re-enrolling in the same course across multiple terms, the current key is no longer sufficient. Add a context component, for example:

```sql
PRIMARY KEY (student_id, course_id, term_id)
```

This is a vital point: the key must accurately describe the identity of the business event. When rules change, the candidate key may change as well.

## 5. Contextual Uniqueness Scope

### 5.1. Global Uniqueness vs. Scoped Uniqueness

A value can be unique across the entire system or only within a subset of records.

For example:

| Value | Uniqueness Scope | Explanation |
|---|---|---|
| `order_id` | System-wide | Every order has its own ID |
| `room_code` | Within a building | Two different buildings can both have room A101 |
| `username` | Within a tenant | Two organizations can use the same login username |
| `line_no` | Within an order | Many orders can have line number 1 |
| `sku` | Per supplier or store | Depends on how the business issues product codes |

A uniqueness rule must always answer: **unique within what scope?** Without explicitly stating scope, design teams easily pick the wrong key or constraint.

### 5.2. Per-Tenant Uniqueness

In a multi-tenant system, the same username may be used across different organizations. If each tenant manages its own namespace, use the combination `(tenant_id, username_normalized)`:

```sql
CREATE TABLE app_user (
    user_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    username_normalized VARCHAR(100) NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    CONSTRAINT uq_user_tenant_username
        UNIQUE (tenant_id, username_normalized)
);
```

Valid data can look like this:

| tenant_id | username_normalized | user_id |
|---:|---|---:|
| 10 | an.nguyen | 1001 |
| 10 | binh.tran | 1002 |
| 20 | an.nguyen | 2001 |

Two tenants can both have a user named `an.nguyen`, yet duplicates are disallowed within the same tenant.

If usernames must be unique system-wide, the constraint must be `UNIQUE (username_normalized)` instead of including `tenant_id`. This is a business decision, not something to infer from system structure.

### 5.3. Per-Parent Record Uniqueness

Some codes only have meaning inside a parent object, such as a room code in a building or a line number in an order. In that case, a composite key or unique constraint combines the parent key and local code:

```sql
CREATE TABLE building_room (
    building_id BIGINT NOT NULL,
    room_code VARCHAR(20) NOT NULL,
    floor_no INTEGER,
    PRIMARY KEY (building_id, room_code)
);
```

If a surrogate ID is desired for referencing rooms from many tables, combine a surrogate key with a scoped unique constraint:

```sql
CREATE TABLE building_room (
    room_id BIGINT PRIMARY KEY,
    building_id BIGINT NOT NULL,
    room_code VARCHAR(20) NOT NULL,
    CONSTRAINT uq_room_code_per_building
        UNIQUE (building_id, room_code)
);
```

The second approach separates the technical identifier `room_id` from the business rule that room codes are unique only within a building. Both approaches can be valid; the choice depends on natural key stability, number of referencing relationships, and API needs.

### 5.4. Multi-Dimensional Contextual Uniqueness

Scope can consist of multiple components. For instance, a shelf code is unique only within a warehouse belonging to a branch:

```sql
UNIQUE (branch_id, warehouse_id, shelf_code)
```

Before adding the constraint, determine whether every component is truly necessary. If `warehouse_id` is already globally unique and uniquely determines `branch_id`, adding `branch_id` may be redundant. However, if the system requires composite keys to enforce tenant boundaries or composite foreign keys, the combination may still serve a distinct purpose.

Do not add columns to a unique key merely because they appear in queries. Unique constraints express data rules; query indexes can be designed separately for the workload.

## 6. Conditional and Temporal Uniqueness Scope

### 6.1. Requiring Uniqueness Only for Active Records

Some business domains allow reusing a code after an old record is soft-deleted or deactivated. For example, a closed account may release its username for a new account if policy permits.

If usernames should be unique only among non-deleted records, a partial unique index can be used in PostgreSQL:

```sql
CREATE UNIQUE INDEX uq_active_user_name
ON app_user (tenant_id, username_normalized)
WHERE deleted_at IS NULL;
```

This index applies only to rows where `deleted_at IS NULL`. Many DBMSs have similar mechanisms, though syntax and support vary; check the target engine.

If rules require closed names to remain reserved, the partial unique index above is inappropriate. In that case, an unconditional unique constraint or an explicit allocation-status model is needed.

### 6.2. Effective-Time Uniqueness

A meeting room can be booked multiple times as long as the time intervals do not overlap. This is not a simple unique rule on `(room_id, start_time)`, because two bookings can have different start times yet still overlap partially in time.

The rule to express is: for the same room, no two active time intervals may overlap.

In PostgreSQL, range types and exclusion constraints can be used. Illustrative example:

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE room_booking (
    booking_id BIGINT PRIMARY KEY,
    room_id BIGINT NOT NULL,
    during TSTZRANGE NOT NULL,
    EXCLUDE USING gist (
        room_id WITH =,
        during WITH &&
    )
);
```

The `&&` operator tests whether two ranges overlap. The exclusion constraint prevents two records with the same `room_id` and overlapping time ranges. This syntax is PostgreSQL-specific; for other DBMSs, an equivalent mechanism is needed such as specialized constraints, transaction locking, or controlled validation to prevent two concurrent requests from booking the same slot.

This example shows that uniqueness scope can be a multi-dimensional condition, not merely equality comparisons on a few columns.

### 6.3. Normalizing Values Before Uniqueness Comparison

Two strings may look similar while differing in representation. For example, emails may differ in letter casing, usernames may contain leading/trailing spaces, and product codes may have specific casing rules.

Before defining a unique constraint, agree on:

- Should leading/trailing whitespace be trimmed?
- Should Unicode be normalized?
- Is comparison case-sensitive or case-insensitive?
- Should separators or formatting characters be stripped?
- Should comparison follow a specific locale/collation?

A common pattern is storing the original value for display and a normalized value for lookups, such as `email_normalized`. Normalization rules must be applied consistently across every write path. If normalization occurs in one API yet is skipped in another ingestion flow, duplicate records can still slip in.

Do not arbitrarily lowercase every field or strip diacritics. Base decisions on business rules and the semantics of each code type.

## 7. Choosing Primary Keys and Unique Constraints

### 7.1. When to Choose a Simple Key vs. a Composite Key?

| Condition | Simple Key | Composite Key |
|---|---|---|
| One stable attribute suffices for identification | Suitable | No need to add components |
| Identity depends on context | Can use surrogate ID and contextual unique constraint | Directly expresses identification scope |
| Junction table has a natural key of multiple FKs | Can add a surrogate ID | Often aligns with business candidate key |
| Many tables reference the record | Simple key is usually simpler | Foreign keys must carry all components |
| Natural key can change | Surrogate ID is usually more stable | Must weigh cost of updating relationships |
| Business rule requires uniqueness within a group | Requires an additional unique constraint | Can use the combination as the key |

There is no one-size-fits-all choice. A design can use a single surrogate key as the primary key and a composite unique constraint to enforce business rules.

For example:

```sql
CREATE TABLE inventory_balance (
    balance_id BIGINT PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    warehouse_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity DECIMAL(18, 3) NOT NULL,
    CONSTRAINT uq_inventory_scope
        UNIQUE (tenant_id, warehouse_id, product_id)
);
```

`balance_id` allows other tables to reference it with a single value. The composite constraint guarantees there is only one balance per combination of tenant, warehouse, and product.

### 7.2. Unique Constraints Must Live Where Data Is Protected

Duplicate checks in the UI or application code are not enough. Two concurrent requests can both check that an email does not exist yet and then both insert a record. Without a unique constraint, both writes succeed and create duplicate data.

The database must be the final line of defense for uniqueness rules:

```sql
ALTER TABLE app_user
ADD CONSTRAINT uq_user_tenant_email
UNIQUE (tenant_id, email_normalized);
```

The application can still pre-check to display friendly messages, yet must handle unique constraint violation errors on writes. Under concurrent inserts, the constraint guarantees at most one transaction can persist a duplicate value in the same scope.

### 7.3. Unique Constraints, Unique Indexes, and NULL

Many DBMSs implement unique constraints via a unique index, though the two concepts are not completely identical across all engines. A constraint expresses an integrity rule; an index is a structure supporting enforcement and queries.

Pay special attention to how the DBMS handles `NULL` in unique constraints. Many DBMSs by default allow multiple rows with `NULL` in a unique column because `NULL` is not considered equal to another `NULL`; some DBMSs or options have different semantics. For identifying keys and mandatory uniqueness scopes, declare components `NOT NULL` to avoid loopholes from missing values.

For example:

```sql
CREATE TABLE tenant_user (
    tenant_id BIGINT NOT NULL,
    username VARCHAR(100) NOT NULL,
    CONSTRAINT uq_tenant_username UNIQUE (tenant_id, username)
);
```

If `tenant_id` or `username` is allowed to be `NULL`, review the DBMS's exact semantics and decide whether records missing values are permitted to exist.

## 8. Composite Keys and Foreign Keys

When a table references a record with a composite key, the foreign key must reference all columns forming that key.

For example, if `project` is identified by `(tenant_id, project_code)`, the `task` table must carry both components when referencing it:

```sql
CREATE TABLE project (
    tenant_id BIGINT NOT NULL,
    project_code VARCHAR(30) NOT NULL,
    project_name VARCHAR(200) NOT NULL,
    PRIMARY KEY (tenant_id, project_code)
);

CREATE TABLE task (
    tenant_id BIGINT NOT NULL,
    project_code VARCHAR(30) NOT NULL,
    task_no INTEGER NOT NULL,
    title VARCHAR(200) NOT NULL,
    PRIMARY KEY (tenant_id, project_code, task_no),
    FOREIGN KEY (tenant_id, project_code)
        REFERENCES project (tenant_id, project_code)
);
```

This design guarantees a task references a project within the same tenant. Referencing only `project_code` when that code is unique only per tenant could allow misdirected links or prevent the database from fully enforcing integrity.

If simpler foreign keys are preferred, `project_id` can serve as a global surrogate key while preserving the unique constraint `(tenant_id, project_code)` to protect project codes within tenant scope. In that case, evaluate whether relationships require tenant-boundary enforcement. In some multi-tenant designs, composite foreign keys help prevent cross-tenant links right inside the database.

## 9. Process for Defining Keys and Uniqueness Scope

Follow this sequence for each entity or data group:

1. **Identify what is being identified:** is the record a customer, order, line item, enrollment, or a time-bounded version?
2. **List candidate attributes:** find business codes, system identifiers, and attribute combinations capable of identification.
3. **Verify uniqueness:** check business rules, existing data, and issuing sources.
4. **Verify minimality:** test removing each attribute from the combination; if it stays unique, the original set is not a candidate key.
5. **Define scope:** system-wide, per tenant, per organization, per parent record, over time, or by status.
6. **Assess stability:** can the value change, be reused, or be re-normalized?
7. **Choose the primary key:** select a candidate key suited to lifecycle and referencing relationships; guard remaining candidate keys with unique constraints.
8. **Design foreign keys:** ensure child tables carry all components required to reference the parent record accurately.
9. **Place constraints in the database:** use `PRIMARY KEY`, `UNIQUE`, `NOT NULL`, or an appropriate mechanism for conditional rules.
10. **Test concurrency and edge cases:** two concurrent requests creating the same code, `NULL` values, tenant transfers, soft deletes, code reuse, and scope changes.

Every decision should be documented with its rationale. If a code is unique only within a branch, documentation must explicitly state branch as the scope and who is responsible for issuing codes.

## 10. Common Mistakes

- Choosing a key based on values that happen not to collide in sample data without confirming business rules.
- Using email or phone number as a primary key even though they can change or be reused.
- Adding a surrogate ID while forgetting unique constraints on business keys.
- Using a composite key without verifying whether every component is truly necessary.
- Treating a local code as globally unique, causing rejection of valid data from other tenants or organizations.
- Omitting a scope component in a foreign key, causing cross-context linking bugs.
- Checking duplicates only in the application without a database-level constraint.
- Overlooking `NULL`, collation, letter casing, and normalization rules.
- Using a simple unique constraint for conditional or non-overlapping temporal uniqueness rules.
- Allowing code reuse without defining how to handle history, old links, and soft-deleted records.
- Adding columns to a unique constraint solely to serve a query, altering the meaning of the data rule.

## 11. Checklist for Verifying Keys and Uniqueness Scope

Before finalizing the model, confirm:

- [ ] Every entity has a clear identification mechanism.
- [ ] Candidate keys are minimal yet uniquely identifying attribute sets.
- [ ] Primary key selection has clear rationale and stability across the record's lifecycle.
- [ ] Remaining candidate keys are protected with appropriate unique constraints.
- [ ] Composite keys accurately reflect identification context and contain no redundant attributes.
- [ ] Uniqueness scope is explicitly documented: global, tenant, parent-child, temporal, or status-based.
- [ ] Mandatory key components are declared `NOT NULL`.
- [ ] String normalization and comparison rules are consistently defined.
- [ ] Composite foreign keys reference all columns of the target key.
- [ ] Concurrent scenarios cannot produce duplicate data.
- [ ] Soft-delete, code-reuse, and history retention rules are defined.
- [ ] Constraint syntax and semantics have been verified on the target DBMS.

Simple keys, composite keys, and uniqueness scope are all ways of expressing data identity. When scope is properly defined, the model both allows valid codes to recur across different contexts and prevents duplicates within the exact business scope that must be protected.
