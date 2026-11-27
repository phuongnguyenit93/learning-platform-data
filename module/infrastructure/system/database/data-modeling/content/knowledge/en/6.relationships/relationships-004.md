# Identifying and Non-Identifying Relationships

## Lesson Objectives

After this lesson, you will be able to distinguish **identifying relationships** from **non-identifying relationships** in a relational data model; identify classification criteria based on primary keys and foreign keys; explain how each relationship type affects child entity identification; and choose a design approach that aligns with the business lifecycle.

You will also learn how to read ERD notation, design composite or surrogate keys, translate relationships into SQL schemas, and avoid confusing identifying relationships with mandatory participation, cardinality, and delete behavior.

## 1. Why distinguish between the two relationship types?

In a data model, a child entity frequently references a parent entity. For example:

- An order item belongs to an order.
- An order is placed by a customer.
- An invoice line belongs to an invoice.
- An employee is assigned to a department.

These relationships may share the same cardinality: one parent entity has many child entities, and each child entity references one parent entity. However, the way the child entity is identified can differ.

For an order item, the line number may only have meaning within the scope of an order. If an item were moved to a different order, it would become a different order item. In that case, the order item's key usually includes the order's key.

Conversely, an order has its own order ID independent of the customer who placed it. The customer might even change under an allowed workflow while the order ID stays the same. In that case, the customer foreign key does not need to participate in the order's primary key.

This difference is described by two concepts:

- **Identifying relationship:** the parent entity's primary key is included in the child entity's primary key.
- **Non-identifying relationship:** the child entity has its own primary key; the foreign key to the parent is not part of that primary key.

Distinguishing the two types clarifies the scope within which a child entity is identified, how tightly its key depends on the parent, and how changing the relationship affects identity.

## 2. Core criterion: does the foreign key participate in the primary key?

The most reliable way to tell them apart is to examine the key structure of the child entity.

### 2.1. Identifying relationship

A relationship is **identifying** when the parent entity's primary key is included in the child entity's primary key, typically as part of a composite primary key.

For example, an order has many order items. Each item is numbered within the scope of that order:

~~~text
ORDER
  PK: order_id

ORDER_ITEM
  PK: (order_id, line_no)
  FK: order_id -> ORDER.order_id
~~~

The primary key of ORDER_ITEM consists of:

- `order_id`: identifier of the parent order;
- `line_no`: line sequence number within that order.

Knowing `line_no = 1` alone is not enough to identify an order item across the entire system. You must also know which order it belongs to. Thus, `order_id` participates in identifying the order item.

### 2.2. Non-identifying relationship

A relationship is **non-identifying** when the child entity has its own primary key, and the foreign key to the parent only represents the association.

For example, an order has its own `order_id` and references a customer:

~~~text
CUSTOMER
  PK: customer_id

ORDER
  PK: order_id
  FK: customer_id -> CUSTOMER.customer_id
~~~

`order_id` is sufficient to identify an order. `customer_id` indicates the associated customer but does not participate in ORDER's primary key.

### 2.3. Comparison table

| Criterion | Identifying relationship | Non-identifying relationship |
|---|---|---|
| Child primary key | Contains the parent's key | Independent of the parent's key |
| Foreign key to parent | Part of the PK and simultaneously an FK | Separate FK, outside the PK |
| Child identity | Typically scoped to the parent | Has its own identity |
| Moving child to another parent | Typically changes the child's PK | May only update the FK if business rules permit |
| Example | Order item within an order | Order belonging to a customer |
| Common implementation | Composite PK | Surrogate key or standalone natural key |

This criterion is based on key structure. You cannot conclude the type merely by looking at entity names, connecting lines, or whether an object "seems dependent".

## 3. Examples of identifying relationships

### 3.1. Order and order item

In this illustrative domain, an order item has no standalone code. It is identified by the order and the line number:

~~~sql
CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, line_no),
    FOREIGN KEY (order_id) REFERENCES orders(order_id)
);
~~~

Here:

- `order_id` is both a foreign key referencing ORDER and part of ORDER_ITEM's primary key.
- `line_no` is unique only within the scope of one `order_id`.
- Two order items can share the same `line_no` if they belong to different orders.
- An order item cannot be identified without `order_id`.

If an item is moved from order A to order B, the composite key changes. Under this model, that is typically a replacement of the line item within the new order rather than merely updating a descriptive attribute.

### 3.2. Invoice lines

An invoice can contain multiple detail lines. The line sequence number only has meaning within the invoice:

~~~text
INVOICE
  PK: invoice_id

INVOICE_LINE
  PK: (invoice_id, line_number)
  FK: invoice_id -> INVOICE.invoice_id
~~~

The INVOICE–INVOICE_LINE relationship is identifying if `invoice_id` participates in the PK of INVOICE_LINE.

If the system uses a separate `line_id` as the PK and `invoice_id` is solely an FK, the relationship is non-identifying by key structure, even though the detail line still depends on the invoice in business terms.

### 3.3. Components dependent on a parent entity

Other examples that may fit identifying relationships:

- Numbered contact addresses within a customer profile, if the sequence number is unique only within that profile.
- Translations of a document, if the language code forms the remainder of a composite key with `document_id`.
- Steps in a workflow, if `step_number` only has meaning within `workflow_id`.
- Sub-versions within a document, if the version number is unique only within that document.

Do not apply an identifying relationship just because one object appears nested inside another in the UI. Always confirm how the business identifies it.

## 4. Examples of non-identifying relationships

### 4.1. Customer and order

An order has its own ID. The customer ID only describes who placed the order:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);
~~~

Here:

- `order_id` is the PK of ORDER.
- `customer_id` is an FK, not part of the PK.
- One customer can have many orders.
- Every order must reference a customer because `customer_id` is NOT NULL.

This is a non-identifying relationship even though the customer link is mandatory.

### 4.2. Employee and department

An employee has an employee ID independent of their department:

~~~sql
CREATE TABLE departments (
    department_id BIGINT PRIMARY KEY,
    department_name VARCHAR(150) NOT NULL
);

CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY,
    department_id BIGINT NOT NULL,
    full_name VARCHAR(200) NOT NULL,
    FOREIGN KEY (department_id) REFERENCES departments(department_id)
);
~~~

If an employee transfers departments, `employee_id` stays the same. Only `department_id` changes per the business workflow. This relationship is non-identifying.

### 4.3. Records with independent lifecycles

Examples that usually fit non-identifying relationships:

- A payment with its own `payment_id` referencing an order.
- A support ticket with its own `ticket_id` referencing a customer.
- A device with its own `device_id` assigned to an employee.
- A transaction with its own `transaction_id` referencing an account.

These entities can have their own lifecycles, statuses, or histories. Their keys do not need to include the parent key.

## 5. Relationship type does not determine cardinality

Four separate questions must be kept distinct:

1. **Identifying or non-identifying?** Does the parent key participate in the child's PK?
2. **One-to-one or one-to-many?** How many records on each side can be linked?
3. **Mandatory or optional?** Can the relationship be absent?
4. **What are the lifecycle and delete behaviors?** When the parent is deleted, are children kept, deleted, reassigned, or blocked?

These are independent dimensions.

For example, ORDER–ORDER_ITEM can be identifying and one-to-many. CUSTOMER–ORDER can be non-identifying and also one-to-many. Both can be mandatory on the child side, yet their PK structures differ.

A non-identifying relationship can still have a NOT NULL FK. An identifying relationship typically has a non-null FK because the FK column belongs to the PK, and PK components cannot be NULL in standard relational models.

Never infer `ON DELETE CASCADE` behavior merely from the label "identifying". Deletion policy is a separate decision grounded in business rules and history retention needs.

## 6. Identifying relationships and weak entities

### 6.1. Weak entities

A **weak entity** is a modeling concept whose identity depends on an owner entity or another identifying scope. It typically lacks an independent natural key sufficient to identify it globally across the domain.

For example, an order item has sequence numbers 1, 2, 3 within each order. The sequence number only has meaning alongside the order.

~~~text
ORDER
  order_id

ORDER_ITEM
  order_id
  line_no
~~~

ORDER_ITEM is a classic example close to a weak entity: its identity depends on ORDER.

In the relational model, identifying relationships are commonly used to express this structure. However, "weak entity" is a concept about identity and dependency semantics in the model, whereas "identifying relationship" is a key-structure mechanism between parent and child. The two concepts are closely related, yet should not be used interchangeably in every situation.

### 6.2. Existence dependency vs. identity dependency

An entity can be existence-dependent on a parent while still having its own key.

For example, an order item has its own UUID `line_id` and a NOT NULL `order_id`. The order item has no business meaning without belonging to an order, yet its PK does not include `order_id`. By key criteria, this relationship is non-identifying despite existence dependency.

Conversely, when the child's PK contains the parent's PK, the child is identity-dependent on the parent. This makes the identification scope explicit and usually means moving the child to another parent changes its key.

## 7. Choosing keys for child entities

### 7.1. Using a composite key when identity depends on parent scope

A composite key is suitable when:

- the local code is unique only within the parent scope;
- the child does not need to be referenced independently across many systems;
- moving the child to another parent means changing its identity;
- the domain wants to express the parent–child structure explicitly.

Example:

~~~sql
PRIMARY KEY (order_id, line_no)
~~~

Advantages:

- makes the identification scope explicit;
- avoids adding a separate ID solely to identify the row;
- naturally reflects rules such as "line 2 of order X".

Trade-offs to consider:

- the key spans more columns;
- every table referencing the order item must carry the full composite key;
- changing the parent key can cascade across many child keys;
- column ordering in indexes must match query patterns.

### 7.2. Using a surrogate key for child entities

You can use a dedicated ID even when the child depends on the parent in business terms:

~~~sql
CREATE TABLE order_items (
    order_item_id UUID PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    UNIQUE (order_id, line_no)
);
~~~

In this design:

- `order_item_id` is an independent PK;
- `order_id` is a mandatory FK outside the PK;
- `UNIQUE (order_id, line_no)` still guarantees line numbers do not collide within the same order;
- the ORDER–ORDER_ITEM relationship is non-identifying by PK structure.

This approach can be useful when order items are referenced by many services, messages, or other tables via a simple single-column ID. It also narrows foreign keys in dependent tables.

However, a standalone ID does not remove the rule that an order item must belong to an order. That rule still needs protection via an FK, NOT NULL, and business logic.

### 7.3. Evaluating by usage

| Question | Design suggestion |
|---|---|
| Does the child code only have meaning inside the parent? | Consider a composite PK containing the parent key |
| Is the child referenced independently in many places? | Consider a surrogate key |
| Do we need to preserve a local business code? | Use UNIQUE over the parent key and local code |
| Can the child move to another parent? | Assess the impact of changing the PK vs. updating only an FK |
| Is the composite key too wide? | Consider a dedicated ID plus an additional UNIQUE constraint |
| Do we need identity history? | Design aliases or a dedicated history table |

No single choice fits every system. Evaluate business identity, query workloads, integration needs, and change costs.

## 8. ERD notation and how to read it

Many ERD tools represent identifying relationships with a solid line and non-identifying relationships with a dashed line. This is a widespread convention in certain notations, though you should always check the legend of the tool in use.

Illustrative example:

~~~text
Identifying relationship:
ORDER ━━━━━ ORDER_ITEM
       order_id is part of the PK of ORDER_ITEM

Non-identifying relationship:
CUSTOMER - - - ORDER
          customer_id is not part of the PK of ORDER
~~~

Line style is only a visual cue. The deciding criterion remains the key structure in the logical model or schema.

### 8.1. Reading a combined example

~~~mermaid
erDiagram
    CUSTOMER ||..o{ ORDER : places
    ORDER ||--|{ ORDER_ITEM : contains
~~~

In the illustrative diagram:

- CUSTOMER–ORDER is drawn as non-identifying: `order_id` is independent, `customer_id` is an FK.
- ORDER–ORDER_ITEM is drawn as identifying: `order_id` participates in the PK of ORDER_ITEM.

Line syntax can vary between Mermaid and dedicated ERD tools. When a tool does not support line styles or follows a different convention, document the relationship type explicitly in a legend or model notes.

### 8.2. Do not confuse line style with optionality

Solid or dashed lines indicate identifying vs. non-identifying by convention. Circles, bars, and crow's feet indicate min–max cardinality. These two sets of symbols answer different questions and can appear together on the same relationship.

For example, an ORDER may mandatorily reference a CUSTOMER with a NOT NULL FK while the relationship remains non-identifying. In an ERD tool, a dashed line can appear alongside a mandatory bar symbol at the ORDER end.

## 9. Impact on key changes and moving child entities

### 9.1. When a parent key changes

If the parent PK is part of the child PK, changing the parent key can require updating child keys and every FK referencing the child. For mutable natural keys, this incurs significant cost.

For instance, if `order_id` is part of ORDER_ITEM's PK, changing `order_id` may require updating line items and all tables referencing them. Some DBMSs support `ON UPDATE CASCADE`, yet you must evaluate scope, foreign keys, and operational safety.

Therefore, parent keys included in child PKs should be stable. If a parent code can change for business reasons, consider using a surrogate key as the PK and storing the business code separately.

### 9.2. When moving a child to another parent

With an identifying relationship, moving an ORDER_ITEM to another ORDER changes part of its PK. That can be viewed as altering the identity of the line item.

With a non-identifying relationship, if business rules allow reassignment, you can update the `order_id` FK while `order_item_id` stays unchanged. Still, preserving the ID does not mean reassignment is valid: verify history, status, auditing, and external system references.

### 9.3. Evolving the model over time

If you initially used a composite key and later need to reference child rows independently, you can introduce a surrogate key. Migration requires:

1. adding the new ID column;
2. generating stable IDs for existing rows;
3. creating a UNIQUE constraint for the old business key;
4. updating referencing FKs;
5. rolling out compatible changes in applications and APIs;
6. validating data and migrating transactions;
7. dropping the old primary key only when no dependencies remain.

Because this schema change has broad impact, plan the migration carefully and test against realistic data.

## 10. Deletion policies and lifecycles are separate decisions

Identifying relationships often appear between an owner entity and a dependent entity, yet you must never automatically conclude that deleting the parent must delete the child.

Common FK behaviors:

- **RESTRICT/NO ACTION:** block deleting the parent while child records still reference it.
- **CASCADE:** delete child records when the parent is deleted.
- **SET NULL:** set the child FK to NULL if the column permits it.
- **SET DEFAULT:** set the FK to a default value if the DBMS and constraints permit it.

The choice depends on business rules:

- Line items of an issued order may need to be retained for auditing.
- Draft details can be deleted along with a draft.
- Customer profiles may be anonymized instead of deleting historical orders.
- Payment records usually must be retained even if an order is canceled.

With an identifying relationship, the FK is part of the child's PK and therefore cannot be set to NULL while keeping a valid PK. To detach the link, redesign the identity or use a different model. Even so, CASCADE remains an explicit policy choice rather than an automatic consequence.

Do not use CASCADE merely because an ERD tool draws an identifying line. Document delete behavior as a testable decision.

## 11. From model to acceptance criteria

You can write test criteria to verify relationship types and key rules.

### 11.1. Criteria for identifying ORDER–ORDER_ITEM

- Every ORDER_ITEM must reference an existing ORDER.
- The pair `(order_id, line_no)` must be unique.
- Two different orders can have items with the same `line_no`.
- An ORDER_ITEM cannot be created without `order_id`.
- Changing `order_id` must follow the defined key and referential policies.

### 11.2. Criteria for non-identifying CUSTOMER–ORDER

- Every ORDER has a unique `order_id`, independent of `customer_id`.
- `customer_id` must reference a valid CUSTOMER if required by business rules.
- One CUSTOMER can have many ORDERS.
- Changing the customer link, if permitted, does not alter `order_id`.
- A CUSTOMER cannot be deleted while referenced by an ORDER when the policy is RESTRICT.

### 11.3. Verification with sample data

For ORDER_ITEM with a composite PK:

~~~sql
INSERT INTO orders(order_id, created_at)
VALUES (1001, CURRENT_TIMESTAMP), (1002, CURRENT_TIMESTAMP);

INSERT INTO order_items(order_id, line_no, product_id, quantity, unit_price)
VALUES
    (1001, 1, 501, 2, 100.00),
    (1002, 1, 501, 1, 100.00);
~~~

Two rows sharing `line_no = 1` are valid because their `order_id` values differ. Inserting another row with `(1001, 1)` must be rejected by the database due to primary key duplication.

For CUSTOMER–ORDER, you can verify that `order_id` remains unchanged when `customer_id` is updated under an allowed workflow. Tests must reflect the actual link-change policy rather than assuming every system allows changing an order's customer.

## 12. Common mistakes

- **Assuming an identifying relationship means mandatory:** mandatory participation and PK structure are two separate dimensions. An FK outside the PK can still be NOT NULL.
- **Assuming every child entity must have a composite key:** a child can have its own ID even when existence-dependent on a parent.
- **Assuming a non-identifying relationship is optional:** the FK in a non-identifying relationship can still be mandatory.
- **Using solid/dashed lines to infer cardinality:** line style describes relationship type by tool convention; min–max requires separate notation.
- **Equating identifying relationships with ON DELETE CASCADE:** delete behavior requires a separate decision.
- **Putting mutable parent codes into child PKs:** causes cascading identity changes. Favor stable parent keys.
- **Dropping UNIQUE when adding a surrogate key:** a dedicated ID does not prevent duplicate line numbers within the same order.
- **Overlooking tables referencing the child:** changing a composite PK or relationship type can impact all dependent FKs.
- **Equating business dependency with key dependency:** an entity may not exist without its parent while still having its own PK.

## 13. Conclusion

An identifying relationship is defined when the parent entity's primary key participates in the child entity's primary key. A non-identifying relationship occurs when the child entity has its own primary key and the FK to the parent sits outside the PK. This is a structural distinction in identity.

When designing, determine how the business identifies the child entity, the uniqueness scope of local codes, needs for independent referencing, and the stability of parent keys. Then choose a composite PK or surrogate key, add appropriate FKs and UNIQUE constraints, and document optionality, cardinality, and delete policies separately. A clear model keeps identity stable, makes relationship changes controllable, and enables thorough verification of data rules.

## Self-check

1. What technical criterion distinguishes identifying from non-identifying relationships?
2. Why can ORDER–ORDER_ITEM use a composite PK `(order_id, line_no)`?
3. An ORDER must have a CUSTOMER, yet `customer_id` is not in the PK. What type of relationship is this, and why?
4. Can a child entity be existence-dependent on a parent while still having a non-identifying relationship?
5. Why does an identifying relationship not automatically imply `ON DELETE CASCADE`?
6. When should you use a surrogate key for a child entity instead of a composite PK?
7. If a parent key can change, what risk arises from including it in the child PK?
8. Pick two relationships in a system and specify their relationship type, PK/FK, optionality, cardinality, and delete policy for each.

