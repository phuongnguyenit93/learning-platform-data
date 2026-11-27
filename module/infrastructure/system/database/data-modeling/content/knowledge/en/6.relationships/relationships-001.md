# One-to-One, One-to-Many, and Many-to-Many Relationships

In a sales system, a customer may have one login account, a customer can place many orders, and a product can be assigned to many categories. These three examples represent the three common relationship types in data modeling: one-to-one (1:1), one-to-many (1:N), and many-to-many (N:N).

Classifying relationships correctly helps the model accurately reflect business rules and avoid invalid links, data loss, or duplicate records. When mapped to a relational database, each relationship type also has an implementation pattern using foreign keys, unique constraints, and junction tables.

This lesson uses an online store example to explain how to identify relationships, read cardinality, determine mandatory participation, translate relationships into a schema, and verify them with data. The focus is on understanding relationships from a business perspective before choosing storage structures.

## 1. What does a relationship represent?

A relationship describes how entities are connected according to a business rule. For example:

- A customer **owns** a customer account profile.
- A customer **places** many orders.
- An order **contains** many order items.
- A product **is classified into** many categories.
- A category **contains** many products.

A relationship name should express the action or meaning of the association. Read it from both directions:

- A customer places an order.
- An order is placed by a customer.

Both sentences describe the same relationship while clarifying the role of each entity.

A relationship needs to answer two independent questions:

1. How many instances on side B can or must an instance on side A be associated with?
2. How many instances on side A can or must an instance on side B be associated with?

The maximum count determines whether the relationship is one-to-one, one-to-many, or many-to-many. The minimum count indicates whether the relationship is mandatory. Do not simply say "one-to-many" while ignoring that a customer might have no orders yet or a draft order might have no order items yet.

## 2. Cardinality and participation

### 2.1. Cardinality: maximum count

Cardinality describes the maximum number of instances that can participate in the relationship on each side.

| Type | Meaning | Example |
|---|---|---|
| 1:1 | Each instance on side A links to at most one instance on side B, and vice versa | Customer profile and login account, if business rules mandate one-to-one |
| 1:N | One instance on side A can link to many instances on side B; each instance B links to at most one A | Customer and order |
| N:N | Each instance on both sides can link to many instances on the other side | Product and category |

The symbols 1 and N express maximum limits; they do not by themselves indicate whether the relationship is mandatory.

### 2.2. Participation: minimum count

Participation indicates whether an instance is required to take part in the relationship.

- **Optional participation:** the minimum count is 0. An instance can exist without a link.
- **Mandatory participation:** the minimum count is 1. A valid instance must have at least one link.

You can combine min/max to state the rule clearly:

| Min..Max | Interpretation |
|---|---|
| 0..1 | Zero or at most one |
| 1..1 | Required, exactly one |
| 0..N | Zero or many |
| 1..N | Must have at least one, possibly many |

Examples:

- A customer can place 0..N orders.
- Each order must belong to exactly 1 customer.
- A draft order can have 0..N order items.
- A confirmed order must have 1..N order items.

The last rule depends on order status. A standard ER diagram cannot capture all of these conditions; they must be documented as business rules and enforced during the order confirmation flow.

### 2.3. Reading min/max from both sides

For the Customer–SalesOrder relationship:

| Side | Min..Max | Business statement |
|---|---:|---|
| Customer → SalesOrder | 0..N | A customer may have placed no orders yet or placed many orders |
| SalesOrder → Customer | 1..1 | Every order must belong to exactly one customer |

For the Product–Category relationship:

| Side | Min..Max | Business statement |
|---|---:|---|
| Product → Category | 0..N or 1..N | A product may be uncategorized yet or must have at least one category |
| Category → Product | 0..N or 1..N | A category may currently be empty or must contain products |

The min/max values on both sides must come from actual business rules. Do not assume by default that a product must always have a category or that a category must always contain products; a catalog may allow creating items first and classifying them later.

## 3. One-to-One Relationship (1:1)

A 1:1 relationship means each instance of entity A links to at most one instance of entity B, and each instance of B links to at most one instance of A.

For example, a store system might specify that every customer profile has exactly one login account and every login account belongs to exactly one customer profile.

~~~mermaid
erDiagram
    CUSTOMER ||--|| CUSTOMER_ACCOUNT : has
~~~

This diagram represents a mandatory one-to-one relationship on both sides. If the account is only created when the customer activates login, the relationship can be optional from the Customer side:

~~~mermaid
erDiagram
    CUSTOMER ||--o| CUSTOMER_ACCOUNT : may_have
~~~

How to read this: each account belongs to exactly one customer; a customer may not have an account yet or may have at most one account.

### 3.1. When should you use 1:1?

A 1:1 relationship can be useful when:

- Two groups of data have different lifecycles.
- There are different security boundaries or access permissions.
- One group of attributes is created only after a specific business step.
- A portion of data is large or rarely accessed and should be separated from the main record.
- Two systems or business teams manage two separate parts independently.

For example, Customer and CustomerAccount can be separated because the customer profile belongs to sales operations, while authentication credentials belong to the security domain. An account can be locked or disabled through its own workflow while the customer profile is retained for orders and support.

However, if two groups of data are always created, read, updated, and deleted together with no separate security boundary or lifecycle, splitting them into two 1:1 entities can add unnecessary complexity. You can merge them into a single entity.

### 3.2. Implementing 1:1 with a foreign key

One implementation approach is placing the foreign key in the dependent table and adding UNIQUE to ensure each parent record has at most one child record.

~~~sql
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);

CREATE TABLE customer_account (
    account_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL UNIQUE
        REFERENCES customer(customer_id)
        ON DELETE RESTRICT,
    login_name VARCHAR(120) NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
~~~

Meaning:

- FOREIGN KEY ensures the account references an existing customer.
- NOT NULL ensures every account must belong to a customer.
- UNIQUE(customer_id) ensures a customer cannot have two accounts.
- A customer may not have an account yet because the foreign key resides in CustomerAccount, so Customer is not forced to have a child row.

This is a 0..1 relationship on the CustomerAccount side when viewed from Customer, and 1..1 from the account back to the customer.

If business rules require every customer to have an account immediately upon creation, a foreign key on the child table is not enough to enforce the reverse direction. Consider merging the tables, creating both records within the same transaction in the application workflow, or using deferred constraints/triggers supported by the DBMS. Do not assume UNIQUE and NOT NULL automatically guarantee that every Customer has a CustomerAccount.

### 3.3. Choosing which side holds the foreign key

Typically, place the foreign key on the side that:

- Has mandatory participation referencing the other side.
- Is created later or depends on the other's lifecycle.
- Can exist optionally relative to the other side.
- Holds data isolated for security or ownership reasons.

If both sides are mandatory and created together, choosing where to put the foreign key requires considering the data creation flow and transaction handling. Sometimes merging the two tables is the simpler choice.

### 3.4. Common mistakes with 1:1

- **Missing UNIQUE:** a foreign key only guarantees valid references; it does not prevent multiple child rows from referencing the same parent row. In that case, the actual relationship is 1:N.
- **Putting NOT NULL on the wrong side:** can force a mandatory link even though the business allows the related object not to exist yet.
- **Assuming a foreign key enforces both directions:** an FK on the child table does not guarantee that every parent row has at least one child record.
- **Splitting tables just to have more tables:** without separate lifecycles, access controls, or operational reasons, splitting can increase joins and transaction overhead.

## 4. One-to-Many Relationship (1:N)

A 1:N relationship means one instance on side A can link to many instances on side B, while each instance on side B links to at most one instance of A.

Examples:

- A customer can place many orders.
- Each order belongs to one customer.
- An order has many order items.
- Each order item belongs to one order.

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--o{ ORDER_ITEM : contains
~~~

In the Customer–SalesOrder relationship, the customer side is 1 and the order side is N. Every order must reference a customer; a customer may have no orders yet.

In the SalesOrder–OrderItem relationship, a confirmed order has at least one line item. In practice, a draft order may not have any items yet, so mandatory participation must be tied to the status.

### 4.1. Implementing 1:N with a foreign key on the N side

In the relational model, the foreign key usually resides in the table on the many side.

~~~sql
CREATE TABLE customer (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);

CREATE TABLE sales_order (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    customer_id BIGINT NOT NULL
        REFERENCES customer(customer_id)
        ON DELETE RESTRICT,
    status VARCHAR(24) NOT NULL,
    placed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ix_sales_order_customer
    ON sales_order(customer_id);
~~~

Each SalesOrder row stores customer_id. Multiple order rows can share the same customer_id. Because the column does not have UNIQUE, one customer can be referenced by many orders.

NOT NULL expresses that every order must belong to a customer. If draft orders are allowed without an attached customer yet, you can allow NULL or use a separate guest-checkout model; this decision must align with business rules and audit requirements.

### 4.2. Why does the foreign key reside on the many side?

Suppose you placed a list column order_id inside Customer to store all of a customer's orders. That approach makes it difficult to:

- Verify that each order exists.
- Find the customer of a given order.
- Add or remove a single link without rewriting the list.
- Query, paginate, and index orders.
- Guarantee that each order belongs to exactly one customer.

Placing customer_id in SalesOrder allows each order row to reference exactly one customer via an FK, while many orders can reference the same customer. This is the natural relational mapping for 1:N.

### 4.3. One-to-many can have an optional side

Example of a customer and saved addresses:

- A customer can save 0..N addresses.
- Each address must belong to exactly one customer.

~~~mermaid
erDiagram
    CUSTOMER ||--o{ CUSTOMER_ADDRESS : owns
~~~

The address table has customer_id NOT NULL. If an address can be shared across multiple profiles, this is no longer a simple 1:N relationship; it must be modeled according to the sharing rule, potentially as N:N.

### 4.4. One-to-many relationships with historical attributes

Suppose an employee is assigned to one department at a time. If employees can transfer departments and history must be preserved, storing only the current department_id on Employee is not enough to know where an employee worked in the past.

You can create an EmployeeDepartmentAssignment entity:

- Employee 1:N EmployeeDepartmentAssignment.
- Department 1:N EmployeeDepartmentAssignment.
- Each assignment has valid_from, valid_to, role, or allocation percentage.

Here, two 1:N relationships form an associative model with history. If an employee can work in multiple departments simultaneously, consider an N:N relationship instead of assuming a single current department.

### 4.5. Common mistakes with 1:N

- Putting the FK on the one side and storing a list of IDs in a single column.
- Forgetting NOT NULL when the many side requires a parent.
- Adding UNIQUE on the FK, accidentally turning the relationship into 1:1.
- Failing to index the FK even when queries frequently filter by that key.
- Using ON DELETE CASCADE without reviewing lifecycle and history retention requirements.
- Confusing maximum count with minimum count: 1:N does not mean every parent must have children.

## 5. Many-to-Many Relationship (N:N)

An N:N relationship means each instance on side A can link to many instances on side B, and vice versa.

Example with products and categories:

- A product can belong to many categories.
- A category can contain many products.

~~~mermaid
erDiagram
    PRODUCT ||--o{ PRODUCT_CATEGORY : classified_by
    CATEGORY ||--o{ PRODUCT_CATEGORY : includes
~~~

In a relational schema, N:N is typically implemented via an associative (junction) entity—here, ProductCategory. Each ProductCategory row represents a link between one product and one category.

### 5.1. Why is a junction table needed?

Do not store a list of category_id values in a Product column or a list of product_id values in Category. That makes foreign keys, queries, and updates difficult to keep consistent.

A junction table solves this by storing each key pair in its own row:

~~~sql
CREATE TABLE product (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(80) NOT NULL UNIQUE,
    name VARCHAR(250) NOT NULL
);

CREATE TABLE category (
    category_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug VARCHAR(160) NOT NULL UNIQUE,
    name VARCHAR(200) NOT NULL
);

CREATE TABLE product_category (
    product_id BIGINT NOT NULL
        REFERENCES product(product_id)
        ON DELETE RESTRICT,
    category_id BIGINT NOT NULL
        REFERENCES category(category_id)
        ON DELETE RESTRICT,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (product_id, category_id)
);

CREATE INDEX ix_product_category_category
    ON product_category(category_id, product_id);
~~~

The composite primary key (product_id, category_id) prevents the same product from being assigned to the same category multiple times. Both foreign keys ensure that both the product and the category exist.

Because the composite primary key starts with product_id, it supports looking up categories for a product. The reverse index (category_id, product_id) supports finding products within a category.

If business rules allow a product to have many categories but only one primary category, you can add a partial unique index:

~~~sql
CREATE UNIQUE INDEX uq_product_one_primary_category
    ON product_category(product_id)
    WHERE is_primary;
~~~

This constraint guarantees each product has at most one primary category. It does not guarantee that every product has a primary category; that minimum requirement must be checked when publishing the product or enforced via an additional mechanism.

### 5.2. Associative relationships with their own attributes

An N:N relationship can carry its own data:

- The date the product was added to the category.
- The user who performed the classification.
- The role of the product within the category.
- The display order of the product.
- The status or effective period of the link.

This data describes the Product–Category assignment itself, not Product or Category individually. Therefore, it belongs in ProductCategory.

Similarly, the order–product relationship in practice is usually modeled as OrderItem because each purchase line has its own quantity, price, discount, tax, and line number.

~~~mermaid
erDiagram
    SALES_ORDER ||--o{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : referenced_by
~~~

OrderItem is an associative/detail entity between SalesOrder and Product. Each OrderItem references exactly one order and one product; an order can have many line items, and a product can appear in many line items across many orders.

### 5.3. Choosing keys for a junction table

There are two common approaches:

**Composite primary key:** use the pair of FKs as the primary key. Suitable when each pair is allowed to appear only once, as in the current ProductCategory table.

**Surrogate key:** add a dedicated relationship_id when each link needs an independent identifier, when the same entity pair can repeat over time, or when other tables reference the link.

For example, a product might be assigned to a category, removed later, and assigned again. If you need to keep each assignment period, a simple composite key (product_id, category_id) is insufficient because the pair can repeat across periods. You can use:

~~~sql
CREATE TABLE product_category_assignment (
    assignment_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES product(product_id),
    category_id BIGINT NOT NULL REFERENCES category(category_id),
    valid_from TIMESTAMPTZ NOT NULL,
    valid_to TIMESTAMPTZ,
    CHECK (valid_to IS NULL OR valid_to > valid_from)
);

CREATE INDEX ix_assignment_product_period
    ON product_category_assignment(product_id, valid_from DESC);

CREATE INDEX ix_assignment_category_period
    ON product_category_assignment(category_id, valid_from DESC);
~~~

This schema supports multiple assignment periods over time. If effective intervals must not overlap, add an exclusion constraint or an equivalent transactional control. A per-row CHECK constraint alone cannot prevent two different rows from having overlapping periods.

### 5.4. When should you avoid keeping a direct N:N relationship?

In a conceptual model, you can draw N:N directly for clarity. When translating to a relational model, an associative entity is required. When the relationship has its own lifecycle, attributes, identifier, or is referenced by other entities, the junction table increasingly needs to be treated as a first-class business entity.

For example, the relationship between employees and projects may have a role, start date, end date, and allocation hours. In that case, Assignment is a clearer entity than an unnamed join table.

## 6. Comparing the three relationship types through an example

| Criterion | 1:1 | 1:N | N:N |
|---|---|---|---|
| Maximum rule | Each side links to at most one | One side many, the other at most one | Both sides can link to many |
| Example | Customer–CustomerAccount | Customer–SalesOrder | Product–Category |
| Relational mapping | FK + UNIQUE | FK on the N side | Junction table with two FKs |
| Key constraints | FK, UNIQUE, NOT NULL depending on participation | FK, NOT NULL/NULL depending on participation | Two FKs, composite PK or UNIQUE |
| Questions to clarify | Do the two entities need to be separated? | Must a child have a parent? | Can the linked pair repeat? |
| Common risk | Missing UNIQUE turns it into 1:N | Storing a list of children on the parent side | Missing junction table or duplicate-prevention key |

A combined store model:

~~~mermaid
erDiagram
    CUSTOMER ||--o| CUSTOMER_ACCOUNT : may_have
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : appears_in
    PRODUCT ||--o{ PRODUCT_CATEGORY : classified_by
    CATEGORY ||--o{ PRODUCT_CATEGORY : includes
~~~

The notation reflects the assumptions of this example:

- A customer may not have a login account yet or may have at most one account.
- Every login account belongs to exactly one customer.
- A customer may have placed no orders yet or placed many orders.
- Every confirmed order has at least one order item; if draft orders exist, the order-item relationship requires status-dependent rules.
- Products and categories have a many-to-many relationship via ProductCategory.

## 7. Mapping relationships to a relational database

### 7.1. General rules

| Relationship type | Common mapping |
|---|---|
| 1:1 | Place FK in one table and add UNIQUE on the FK |
| 1:N | Place FK in the table on the many side |
| N:N | Create a junction table with FKs to both sides |

Additional constraints:

- **NOT NULL:** expresses a mandatory FK on the referencing side.
- **UNIQUE:** limits an FK value to at most one link.
- **PRIMARY KEY:** guarantees unique identification for a row or linked pair.
- **FOREIGN KEY:** ensures the referenced side exists.
- **CHECK:** validates conditions on data within a single row, such as valid_to > valid_from.

Not every cardinality rule can be enforced with a single FK. For example, "every customer must have at least one order" is a multi-row constraint and should generally not be enforced if the business allows new customers who have not purchased yet. If truly mandatory, use transactions, deferred triggers, or an appropriate publishing workflow.

### 7.2. Mandatory participation and NULL

If the foreign key on the many side is NOT NULL, every row on the many side must reference a row on the one side. If the FK allows NULL, a row on the many side can exist without being attached to a parent row yet.

For example, an order might be created in draft status before the customer logs in. You can allow customer_id to be NULL in draft status, while requiring a valid customer upon confirmation. A simple CHECK constraint can validate the relationship between status and customer_id on the same row:

~~~sql
CHECK (
    status = 'DRAFT'
    OR customer_id IS NOT NULL
)
~~~

This only illustrates a single-row condition. Rules spanning multiple tables, such as requiring a confirmed order to have at least one OrderItem, must be checked in an appropriate transaction or trigger.

### 7.3. Choosing ON DELETE behavior

When a referenced row is deleted, the database needs a rule:

- **RESTRICT / NO ACTION:** reject deletion if references still exist. Suitable for transactional data requiring history retention.
- **CASCADE:** delete dependent rows. Suitable for child data whose lifecycle is completely dependent and does not need to be retained independently.
- **SET NULL:** clear the link while keeping the child row. Use only when the FK allows NULL and the business accepts losing the link.
- **SET DEFAULT:** replace with a default value if meaningful and valid.

Do not choose CASCADE just to make deletion convenient. Deleting a customer and cascading to orders and payments poses a major risk. For commercial data, disabling or hiding records via status is typically used instead of physical deletion.

## 8. Cardinality in conceptual models vs. enforced constraints

An ER diagram helps align with business stakeholders, but it is not enough on its own to enforce every rule when multiple transactions run concurrently.

For example, a product can have at most one primary category. A partial unique index can enforce that maximum limit. However, the rule "every active product for sale must have at least one primary category" must be checked when publishing the product or via a transaction/trigger.

A confirmed order must have at least one order item. The FK from OrderItem to SalesOrder only guarantees that each order item has a parent order. It does not guarantee that each order has children. This is the difference between checking a reference from child to parent and checking the existence of at least one child from parent to child.

Similarly, for a 1:1 relationship mandatory on both sides, FK + UNIQUE on the dependent table does not guarantee the parent table always has a child row. You need a synchronized creation flow or additional constraint mechanisms.

Let's classify these rules:

| Rule | Can be protected by |
|---|---|
| FK references an existing row | FOREIGN KEY |
| Each customer has at most one account | UNIQUE on customer_id in CustomerAccount |
| Each account must belong to a customer | NOT NULL + FOREIGN KEY |
| An order must belong to a customer when confirmed | Row-level status CHECK or transaction workflow |
| A confirmed order must have at least one item | Transaction / trigger / confirmation workflow |
| A product has at most one primary category | Partial UNIQUE index |
| A product must have at least one primary category when published | Publishing workflow / transaction / trigger |
| No two category assignment periods overlap | Exclusion constraint or equivalent concurrency control |

## 9. Common modeling mistakes

### Mistake 1: Confusing 1:N with 1:1

The table on the many side has an FK, but UNIQUE is accidentally added to the FK. As a result, each customer can only have one order.

Fix: remove UNIQUE if the business allows multiple orders; keep only the FK and an appropriate index.

### Mistake 2: Confusing N:N with 1:N

Placing category_id directly on Product when a product can belong to multiple categories. This forces each product to have only one category.

Fix: create ProductCategory with two FKs and a unique constraint on the pair if each pair is allowed only once.

### Mistake 3: Storing a list of IDs in one column

Storing product_ids = "12,13,14" in Category loses FK enforcement and makes querying by product hard to optimize.

Fix: each link is one row in a junction table.

### Mistake 4: Writing only "many" without min/max

It remains unclear whether a new customer can have no orders yet or a draft order can have no order items yet.

Fix: specify 0..N or 1..N and note status-dependent conditions where applicable.

### Mistake 5: Ignoring relationship attributes

A bare ProductCategory join table cannot store the assignment date, the person who assigned it, or the primary category flag without dedicated columns.

Fix: model a relationship that has attributes as an associative entity.

### Mistake 6: Using a composite key unsuitable for history

The pair product_id and category_id appears only once in a current-state table, yet the business wants to retain multiple assignment periods over time.

Fix: add assignment_id or use a key including a timestamp; define effective period rules and prevent overlaps.

### Mistake 7: Using CASCADE on auditable data

Deleting a parent wipes out critical transactional rows.

Fix: use RESTRICT, disable the entity, or archive according to data retention policies.

## 10. Process for determining relationship types

When reading a requirement, follow these steps:

1. Identify the two entities participating in the relationship.
2. Name the relationship using a clear verb or phrase.
3. Ask: for one instance of A, how many instances of B can it link to at most?
4. Ask: for one instance of B, how many instances of A can it link to at most?
5. Determine the minimum count on both sides: 0 or 1?
6. Check whether mandatory participation changes by status or over time.
7. If 1:1, evaluate whether the two entities have separate lifecycles or management boundaries.
8. If 1:N, place the FK on the many side and decide between NULL and NOT NULL.
9. If N:N, create an associative entity; identify attributes and the lifecycle of the relationship.
10. Choose appropriate keys, UNIQUE constraints, indexes, and delete behavior.
11. Test with valid data, invalid data, and concurrent operations to verify.

## 11. Practice exercises

### Exercise 1: Customer and login account

A customer may not have registered a login account yet. Each account must belong to exactly one customer. A customer must not have two active accounts.

Identify:

- The relationship type and min/max on both sides.
- Which table should hold the FK?
- Is UNIQUE needed?
- Is a partial unique index needed if locked accounts are kept for history?

Hint: Customer–CustomerAccount is 1:1 optional from the Customer side. Place the FK in CustomerAccount with NOT NULL and UNIQUE(customer_id). If account history can have multiple rows over time while only one row is active, use a dedicated account identifier and a partial unique index for active rows.

### Exercise 2: Customer and orders

A customer can place many orders. Each order must belong to exactly one customer.

Identify:

- Cardinality and participation.
- FK placement.
- Should draft orders without an attached customer be allowed?

Hint: Customer 0..N SalesOrder; SalesOrder 1..1 Customer. Place customer_id in SalesOrder. If draft orders are allowed without a customer attached, allow NULL in draft status and validate before confirmation.

### Exercise 3: Products and categories

A product can belong to many categories. A category can contain many products. Every product on sale must have one primary category, and may also have secondary categories.

Identify:

- Why is a junction table needed?
- What is the primary key of the junction table?
- How do you guarantee at most one primary category?
- How do you guarantee at least one primary category when a product is published?

Hint: ProductCategory has a composite key (product_id, category_id). Use a partial unique index to limit each product to one row with is_primary = true. The rule requiring at least one primary row must be verified in the publishing transaction or an equivalent mechanism.

### Exercise 4: Employees and projects

An employee can participate in many projects. A project has many employees. Each participation has a start date, end date, role, and allocation percentage.

Identify:

- Which entity implements the N:N relationship?
- Is assignment_id needed?
- Can an employee participate in the same project across multiple periods?
- What time constraints are needed?

Hint: use ProjectAssignment with two FKs, start/end dates, role, and allocation percentage. If multiple participation periods are allowed, use a surrogate key or a composite key including valid_from; check that the end date is greater than the start date and prevent overlapping periods if the business disallows them.

### Review checklist

- Has the relationship been read accurately from both sides?
- Does the maximum cardinality match business rules?
- Is minimum participation explicitly documented?
- Are there status- or time-based conditions?
- Is the FK placed on the appropriate side?
- Is UNIQUE accidentally restricting a 1:N relationship into 1:1?
- Does N:N have a junction table with two FKs?
- Does the relationship have its own attributes or lifecycle?
- Does the junction table's key allow history and valid repetitions?
- Does delete behavior protect transactional and historical data?
- Which min/max rules cannot yet be enforced by single-row constraints?
- Do common queries have appropriate indexes?

1:1, 1:N, and N:N relationships describe the maximum number of links between entities. To model business rules accurately, you must also capture minimum counts and mandatory participation on each side. When mapping to a relational database, 1:1 typically uses an FK with UNIQUE, 1:N places the FK on the many side, and N:N uses a junction table. Reviewing constraints, lifecycles, and relationship attributes ensures the schema accurately reflects current data while supporting history and evolving business rules.
