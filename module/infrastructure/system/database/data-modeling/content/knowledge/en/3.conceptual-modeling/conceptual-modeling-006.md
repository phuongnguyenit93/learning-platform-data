# Cardinality, Optionality, and Crow's Foot Notation

## Lesson Objectives

After this lesson, you will be able to read and draw relationships between entities in a data model by specifying **cardinality** and **optionality (participation)** at both ends of a relationship. You will understand the circle, single bar, and crow's foot symbols; translate business rules into Crow's Foot notation; recognize one-to-one, one-to-many, and many-to-many relationships; and validate models using concrete examples and edge cases.

## 1. Why Must Cardinality and Optionality Be Specified?

A sentence like "a customer has orders" only tells us that two concepts are related. It does not answer:

- Can a customer exist with no orders yet, or must a customer have at least one order?
- Can a customer have multiple orders?
- Can an order belong to multiple customers or exactly one customer?
- Can an order exist without being linked to a customer yet?

Without stating these limits clearly, every reader may interpret the diagram differently. Consequences show up in foreign key design, validation, APIs, test data, and business workflows.

**Cardinality** describes how many objects at one end of a relationship can or must link to one object at the other end. **Optionality** describes whether a relationship may be absent or must exist. Both aspects are commonly expressed together using min–max ranges, such as:

- `0..1`: zero or at most one.
- `1..1`: mandatory, exactly one.
- `0..*`: zero or many.
- `1..*`: at least one, possibly many.

Crow's Foot notation visually depicts these limits on an Entity–Relationship Diagram (ERD).

## 2. Distinguishing Cardinality, Optionality, and Relationship Multiplicity

In practice, references may use the terms cardinality, multiplicity, optionality, and participation with slightly different phrasing. To avoid confusion, this lesson uses these definitions:

- **Cardinality / Multiplicity:** the minimum and maximum number of objects that can participate in a relationship.
- **Optionality:** whether an object is allowed not to participate in the relationship; this corresponds to the minimum bound of 0 or 1 in basic examples.
- **Relationship multiplicity (degree/ratio):** the general term for link counts, typically described as one-to-one, one-to-many, or many-to-many.

A relationship is not merely "one" or "many". It can be "zero or one", "exactly one", "zero or many", or "at least one". Therefore, specifying min–max bounds is more precise than simply writing `1:1` or `1:N`.

### 2.1. Four Common Min–Max Ranges

| Range | Meaning | Example |
|---|---|---|
| `0..1` | Zero or at most one | An employee profile may not yet have an access badge; each profile has at most one active badge |
| `1..1` | Mandatory, exactly one | Each order line belongs to exactly one order |
| `0..*` | Zero or many | A customer may have placed zero orders or many orders |
| `1..*` | Mandatory, at least one | A confirmed order must have at least one order line |

The `*` symbol means no upper limit in the conceptual model. In a physical system, operational limits such as capacity, quotas, or other business rules may still apply.

### 2.2. Reading a Relationship from Both Sides

Suppose a customer can place many orders, and each order must belong to exactly one customer.

We must be able to read two statements:

- For any given Customer, there can be 0 to many Orders.
- For any given Order, there must be exactly one Customer.

Do not merely say "Customer–Order is 1:N" and ignore the other end. Cardinality and optionality are defined independently at each end of the relationship.

## 3. Crow's Foot Notation

Crow's Foot notation places symbols at both ends of the line connecting entities. Each end describes how many records of the entity at that end can link to one record on the opposite side.

Three basic symbols:

| Symbol | Meaning | Bound |
|---|---|---|
| Circle (`o`) | Relationship may be absent | Min = 0 |
| Single bar (vertical stroke) | Limits count to one at that end | Max = 1; doubled bars mean exactly one |
| Crow's foot (three prongs) | Multiple objects may exist | Max = many (`*`) |

Combining two symbols at the same end yields the min–max range:

| Crow's Foot Symbol | Min–Max | How to Read |
|---|---:|---|
| Circle + bar | `0..1` | Zero or one |
| Two bars | `1..1` | Exactly one |
| Circle + crow's foot | `0..*` | Zero or many |
| Bar + crow's foot | `1..*` | One or many |

Across different ERD tools, the crow's foot may look like three prongs or a fork. Drawing styles vary slightly, yet the meaning of the circle, bar, and many-prong remains the same.

### 3.1. Important Note on Symbol Placement

The symbol next to an entity describes how many instances of **that** entity can link to **one** instance on the opposite end.

Example:

~~~text
CUSTOMER || —— o{ ORDER
~~~

- `||` on the Customer side: each Order is tied to exactly one Customer.
- `o{` on the Order side: each Customer can have 0 or many Orders.

This is easy to read backwards. Try picking one record on the left end and asking how many records on the right end can link to it; then reverse direction and read again.

## 4. Reading the Three Basic Relationship Types

### 4.1. One-to-One

A one-to-one relationship means each object on one side links to at most one object on the other side. Optionality at the two ends may differ.

Example: an employee profile may have one active access card; each active access card belongs to exactly one employee profile.

~~~text
EMPLOYEE || —— o| ACCESS_CARD
~~~

How to read:

- Each Employee can have 0 or 1 AccessCard.
- Each AccessCard must belong to exactly 1 Employee.

If both sides require exactly one, the notation is:

~~~text
EMPLOYEE || —— || EMPLOYEE_PROFILE
~~~

Not every one-to-one relationship needs to be split into two tables. If two concepts always share the same lifecycle and are always accessed together, they may simply be one entity with various attributes. Splitting makes sense when they have independent lifecycles, access permissions, optionality, or data sources.

### 4.2. One-to-Many

Common example: a customer can have many orders; each order belongs to exactly one customer.

~~~text
CUSTOMER || —— o{ ORDER
~~~

How to read:

- One Customer can have 0 or many Orders.
- Each Order must belong to exactly 1 Customer.

Another variant is that a confirmed order must have at least one line item:

~~~text
ORDER || —— |{ ORDER_ITEM
~~~

How to read:

- Each Order has 1 to many OrderItems under the confirmed rule.
- Each OrderItem belongs to exactly 1 Order.

Pay attention to state scope. A draft order may temporarily have no line items, whereas a confirmed order must have at least one line item. If a rule varies by state, document that condition in the business description or corresponding constraint; static ERD notation alone cannot express every temporal condition.

### 4.3. Many-to-Many

Example: a student can enroll in many courses, and a course has many students.

~~~text
STUDENT }o —— o{ COURSE
~~~

In a conceptual model, this is a many-to-many relationship. When implemented in a relational model, an associative entity such as `Enrollment` is typically needed to store each enrollment instance.

~~~text
STUDENT || —— o{ ENROLLMENT
COURSE  || —— o{ ENROLLMENT
~~~

Each `Enrollment` must reference exactly one `Student` and one `Course`; each `Student` or `Course` can have 0 or many `Enrollments`.

If the relationship carries its own attributes such as enrollment date, grade, status, or term, an associative entity is especially helpful. Those attributes describe the enrollment itself, not the student or course independently.

## 5. ERD Example for a Sales System

Consider the following business rules:

1. A customer may have zero orders or many orders.
2. Each order is created for exactly one customer.
3. A confirmed order must have at least one line item.
4. Each line item references exactly one product.
5. A product may never have been ordered or may appear in many line items.
6. An order may have zero payments or multiple payment attempts.

Illustrative ERD:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : appears_in
    ORDER ||--o{ PAYMENT_ATTEMPT : has
~~~

Reading each relationship:

| Relationship | Reading from the First Entity | Reading from the Second Entity |
|---|---|---|
| Customer–Order | One Customer has `0..*` Orders | Each Order has exactly 1 Customer |
| Order–OrderItem | One Order has `1..*` OrderItems under confirmed rule | Each OrderItem belongs to exactly 1 Order |
| Product–OrderItem | One Product has `0..*` OrderItems | Each OrderItem references exactly 1 Product |
| Order–PaymentAttempt | One Order has `0..*` PaymentAttempts | Each PaymentAttempt belongs to exactly 1 Order |

A conceptual ERD does not have to display every attribute. When advancing to the logical model, we will add keys, attributes, and concrete constraints.

### 5.1. Why Is OrderItem an Associative Entity?

The relationship between `Order` and `Product` is inherently many-to-many: an order has many products and a product can appear in many orders. Yet the relationship itself carries data:

- ordered quantity;
- unit price at purchase time;
- discount amount;
- notes or variant selection.

Therefore, `OrderItem` is an associative entity. It represents one instance of a product being included in a specific order.

### 5.2. Do Not Mechanically Infer Business Rules from Notation

For example, the diagram shows an `Order` having `1..*` `OrderItem`. This must be grounded in the rule "a confirmed order must have at least one line item". If the system permits saving draft orders without line items yet, the model must clearly state the scope of applicability:

- either represent draft Orders with `0..*` `OrderItem`;
- or separate state/aggregate models by stage;
- or annotate a conditional constraint: only confirmed Orders must have at least one `OrderItem`.

Do not force a single symbol to represent multiple state-dependent rules if it misleads readers.

## 6. Translating Crow's Foot Notation to a Relational Model

Crow's Foot notation describes relationships at the conceptual or logical level. When implemented in a relational database, relationships are typically realized using foreign keys and constraints.

### 6.1. One-to-Many: Place the Foreign Key on the Many Side

For `Customer–Order`, each `Order` belongs to one `Customer`. The many-side table (`orders`) holds a foreign key referencing the one-side table (`customers`).

~~~sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);
~~~

- `NOT NULL` expresses the requirement that every `Order` must have a `Customer`.
- The foreign key guarantees the referenced `Customer` exists.
- One `Customer` can have many `Orders` because multiple rows in `orders` can reference the same `customer_id`.

If an `Order` is allowed to exist without an assigned `Customer`, the foreign key column can allow `NULL`. However, define the meaning of a missing link clearly; `NULL` should not arbitrarily represent multiple unrelated business states.

### 6.2. One-to-One: Combining Foreign Key and UNIQUE

If each employee has at most one card and each card belongs to exactly one employee, place a unique foreign key on the cards table:

~~~sql
CREATE TABLE employees (
    employee_id BIGINT PRIMARY KEY
);

CREATE TABLE access_cards (
    card_id BIGINT PRIMARY KEY,
    employee_id BIGINT NOT NULL UNIQUE,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);
~~~

- `NOT NULL` requires every card to have an employee.
- `UNIQUE` prevents one employee from being referenced by multiple cards in this table.
- Allowing an employee not to have a card yet works because no constraint forces every `Employee` to have an `AccessCard`.

### 6.3. Many-to-Many: Using a Junction Table

For `Student–Course`, the `enrollments` table holds foreign keys to both sides:

~~~sql
CREATE TABLE students (
    student_id BIGINT PRIMARY KEY
);

CREATE TABLE courses (
    course_id BIGINT PRIMARY KEY
);

CREATE TABLE enrollments (
    student_id BIGINT NOT NULL REFERENCES students(student_id),
    course_id BIGINT NOT NULL REFERENCES courses(course_id),
    enrolled_at TIMESTAMP NOT NULL,
    PRIMARY KEY (student_id, course_id)
);
~~~

The composite primary key prevents one student from having duplicate enrollment records for the same course within the same course scope. If business rules allow retaking a course by term, the key may need `term_id` or a dedicated enrollment identifier.

### 6.4. Limitations of Foreign Keys

Foreign keys and `NOT NULL` enforce many rules, yet not every min–max rule can be enforced directly by a single simple constraint.

For example, the foreign key in `order_items` guarantees each line item belongs to a valid order. It does not automatically guarantee that every `Order` has at least one `OrderItem`. To enforce "a confirmed order must have at least one line", the system may need a business transaction, a pre-transition validation check, a trigger, or a DBMS-appropriate constraint mechanism.

Therefore, distinguish among:

- what the model requires;
- constraints directly declarable in the schema;
- rules that must be checked inside transactions or application logic.

## 7. How to Determine Cardinality from Business Requirements

Do not start by picking symbols. Start by asking questions about each side of the relationship.

### Step 1: Identify Both Concepts

Example: `Department` and `Employee`.

Define each concept clearly. `Department` is an organizational unit; `Employee` is an HR personnel record. Avoid ambiguous labels like "user" when multiple distinct roles exist.

### Step 2: Write Sentences in Both Directions

- How many `Employees` can one `Department` have?
- How many `Departments` can one `Employee` belong to at the same time?

The answers might be: one department can have `0..*` employees; each employee belongs to exactly one current department.

### Step 3: Ask About Minimum Cases

- Can a newly created department have no employees yet?
- Can a new employee not yet be assigned to a department?

This question determines whether a relationship end is optional or mandatory. Do not infer from current manual processes if the business permits intermediate states.

### Step 4: Ask About Maximum Limits

- Can an employee work in multiple departments simultaneously?
- Can a department have an unbounded number of employees from a business standpoint?

If an employee can belong to multiple departments, the relationship may be many-to-many and require an `Assignment` concept with effective dates and roles.

### Step 5: Check Lifecycle and Time

Does the relationship change over time? If an employee transfers departments, does the system need only the current department or full assignment history?

If history is needed, a direct `Employee–Department` link may be insufficient. An `Assignment` entity can hold `valid_from`, `valid_to`, job title, or allocation percentage.

### Step 6: Write Rules in Plain Language

Examples:

- A `Department` may have zero employees or many employees.
- Every active `Employee` must have exactly one primary `Department`.
- An `Employee` may have multiple historical `Assignments`, but primary assignment intervals must not overlap.

These statements can be reviewed and translated into an ERD, schema, and acceptance criteria.

## 8. Advanced Cases to Watch For

### 8.1. Recursive Relationships

An entity can relate to itself. For example, an employee can report to a manager who is also an employee.

~~~text
EMPLOYEE (manager) o| —— o{ EMPLOYEE (subordinate)
~~~

Read the roles at both ends clearly:

- An `Employee` in the manager role can manage `0..*` employees.
- An `Employee` in the subordinate role can have `0..1` direct manager, depending on organizational policy.

If every employee (except the top executive) must have a manager, the subordinate side's manager end would be `||` instead of `o|`. Always name roles to avoid confusing both ends referencing the same table.

### 8.2. Time-Effective Relationships

One person can belong to multiple groups at different times. If you only store a single current `group_id` foreign key, history is lost.

You can use an associative entity `Membership` with:

- `member_id`;
- `group_id`;
- `valid_from`;
- `valid_to`;
- `role`.

Then the membership relationship has its own lifecycle, and non-overlapping temporal rules must be defined. Current-point-in-time multiplicity may differ from cumulative historical multiplicity.

### 8.3. Ternary or Multi-Way Relationships

Some rules cannot be accurately expressed by splitting into multiple binary relationships. For example, a supplier supplies a product to a branch under a specific contract. The meaning depends simultaneously on `Supplier`, `Product`, and `Branch`.

Splitting into three binary relationships can lose the constraint that only that specific triple of objects is valid. In that case, consider an associative entity like `SupplyAgreement` or a ternary relationship in the conceptual model.

### 8.4. Conditional Cardinality

A relationship may depend on state, object subtype, or time:

- A draft order may have zero line items.
- A confirmed order must have at least one line item.
- Full-time employees must have a department; contractors may not.
- An account has only one active verification profile, yet may have multiple historical profiles.

Document conditions explicitly. If the ERD tool cannot depict them, add constraint notes or model the state/relationship as its own entity.

## 9. Validating ERDs and Common Mistakes

An ERD must do more than use valid symbols. It must accurately reflect business rules and be clear enough for the implementation team to share a common understanding.

### 9.1. Review Checklist

For each relationship, check:

1. Can the relationship name be read as a clear business sentence?
2. Has it been read from both sides?
3. Are min and max confirmed at each end?
4. Is optionality accurate for the relevant states and lifecycles?
5. Does a many-to-many relationship need an associative entity?
6. Does the relationship have its own attributes or effective dates?
7. Are there rules that simple Crow's Foot symbols cannot express?
8. Can the relationship translate cleanly into appropriate keys and constraints?
9. Are there any data scenarios that contradict the diagram?

### 9.2. Common Mistakes

- **Writing only `1:N` without optionality:** readers do not know whether the many side can be 0 or must have at least one.
- **Reading symbols backwards:** the symbol at an entity's end describes how many of *that* entity correspond to one record on the opposite side.
- **Confusing "max one" with "exactly one":** `0..1` is optional; `1..1` is mandatory.
- **Assuming every one-to-one relationship needs a separate table:** can overcomplicate the model when both parts share the same lifecycle and access pattern.
- **Leaving many-to-many in a relational schema without a junction table:** typically makes it impossible to store per-link attributes or enforce uniqueness cleanly.
- **Forgetting state-dependent rules:** a draft order and a confirmed order may have different line-item requirements.
- **Assuming a foreign key enforces all cardinalities:** an FK protects referential integrity, yet does not automatically ensure a parent has at least one child row.
- **Omitting role names on recursive relationships:** readers cannot tell manager from subordinate.
- **Ignoring history:** current-state multiplicity does not necessarily describe the relationship across all time.

## 10. From ERD to Acceptance Criteria

Once cardinalities are aligned, write testable criteria. For example, for `Customer–Order`:

- When creating an `Order`, the system requires a valid `Customer`.
- A `Customer` who has never ordered can still exist.
- A `Customer` can have multiple `Orders`.
- An `Order` cannot be created referencing a non-existent `Customer`.

For `Order–OrderItem`, if the rule applies only to confirmed orders:

- An `Order` in Draft status may have zero `OrderItems`.
- When transitioning an `Order` to Confirmed, at least one valid `OrderItem` must exist.
- Every `OrderItem` must reference exactly one `Order`.
- When deleting or cancelling an `Order`, handle `OrderItems` according to the confirmed history retention policy.

Acceptance criteria clarify what must hold true and provide concrete test cases. They also help identify which constraints must be enforced by the database and which require business workflow enforcement.

## 11. Conclusion

Cardinality defines the minimum and maximum number of links between entities; optionality indicates whether a relationship may be absent or must exist. Crow's Foot notation combines circles, bars, and crow's feet to depict those bounds at both ends of a relationship.

When designing an ERD, first define concepts, write business rules in both directions, confirm min–max bounds, and only then choose symbols. Afterward, validate with edge cases and translate rules into appropriate keys, constraints, or business logic. A sound diagram helps everyone share the exact same understanding and enables consistent implementation and testing.

## Self-Check

1. What does the `o{` symbol mean? How does it differ from `|{`?
2. Given `CUSTOMER ||--o{ ORDER`, interpret the relationship from both sides.
3. Why is the foreign key typically placed on the many side in a one-to-many relationship?
4. Does a foreign key alone guarantee every `Order` has at least one `OrderItem`? Explain.
5. When does a many-to-many relationship require an associative entity?
6. How would you represent an employee transferring departments when history must be preserved?
7. Pick a relationship in a system you know, write two bidirectional min–max statements, draw Crow's Foot notation, and propose acceptance criteria to test it.
