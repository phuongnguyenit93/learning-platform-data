# Repeating Attribute Groups and Signs to Extract a Separate Structure

In the **DATABASE_DATA_MODELING** module, a sound data model must accurately reflect business objects, rules, and how data is used. When analyzing attributes, we sometimes discover that an entity has multiple groups of information of the same kind: a customer has multiple contact numbers, an order has multiple line items, an employee has multiple certifications, or a product has multiple variants. This is when we need to recognize **repeating attribute groups** and decide whether to extract them into a separate structure.

If the model keeps repeating groups as fixed columns such as `phone_1`, `phone_2`, `phone_3`, capacity is capped by design and every expansion requires altering the schema. If we stuff the entire list into a string or a JSON field without examining the rules, searching, validating, and updating individual elements can become difficult. Conversely, extracting every small group into a separate table also complicates the model and increases query cost. Decisions must be based on element count, the meaning of each element, lifecycle, relationships, and workload.

## 1. What Is a Repeating Attribute Group?

A **repeating group** is a set of identically structured attributes that can appear multiple times for the same entity or the same business object.

For example, an employee profile may contain these groups:

- Certifications: certificate name, issuing organization, issue date, expiration date.
- Contact numbers: contact type, value, label, verification status.
- Employment history: organization, job title, start date, end date.
- Skills: skill name, proficiency level, years of experience.

Each occurrence of the group has the same shape yet different values. One employee may have two certifications, three contact numbers, or multiple employment periods.

~~~mermaid
flowchart TD
    E["Employee"] --> G["Repeating certificate group"]
    G --> C1["Certificate 1"]
    G --> C2["Certificate 2"]
    G --> C3["Certificate 3"]
    C1 --> A1["Name / Issuer / Issue date / Expiration"]
    C2 --> A2["Name / Issuer / Issue date / Expiration"]
    C3 --> A3["Name / Issuer / Issue date / Expiration"]
~~~

The key point is that each repetition shares the same attribute structure. If a customer has both a billing address and a shipping address, that is not necessarily a repeating group. The two addresses can carry distinct business roles, have separate rules, and have a fixed count. Only when a customer can store arbitrarily many addresses with the same structure does it become a repeating set of elements.

### Identifying via Data Structure

Common signs in requirements, spreadsheets, forms, or legacy schemas:

- Number-suffixed columns: `phone_1`, `phone_2`, `phone_3`.
- Column pairs repeated in a pattern: `certificate_name_1`, `certificate_issuer_1`, `certificate_name_2`, `certificate_issuer_2`.
- Fields such as `item1`, `item2`, `item3` or `address_a`, `address_b`.
- A field containing a list separated by commas, semicolons, or arbitrary delimiters.
- An information group that can be added multiple times in the UI, while the database only has a few fixed columns.
- Application logic repeating conditional branches by position: processing the first, second, and third phone numbers.

Repeated column names are a signal to investigate, not sole proof that a table must be split. Confirm the business rules: is the count fixed, does every element share the same structure, and do users need to operate on individual elements independently?

## 2. Distinguishing Repeating Groups from Similar Structures

Several structures look similar yet carry different meanings.

| Structure | Nature | Example |
|---|---|---|
| Composite attribute | A single value composed of multiple parts | An address consisting of street, city, and country |
| Single multi-valued attribute | One entity has multiple values of the same kind | A customer has multiple phone numbers |
| Repeating attribute group | One entity has multiple occurrences of the same group of fields | An employee has multiple certifications, each with a name, issuer, and expiration date |
| Two fixed roles | Attributes differ by role, with a clearly defined count | Billing address and shipping address on an order |
| Many-to-many relationship | Multiple entities on both sides can link to one another | Students enroll in multiple courses and each course has multiple students |

A repeating group can often be modeled as a child entity, a child value object, or a collection. Do not assume every repeating group is an independent entity; extracting a structure is a decision about representation and data responsibility.

### Example: Shipping Address and Billing Address

If the business always has exactly two roles, each with its own rules, the model can represent them as two composite attributes:

- `billing_address`: the address used for invoicing.
- `shipping_address`: the address used for delivery.

If customers can save multiple addresses and assign each address to different purposes, consider an address collection with a type field or a role-association table. The latter structure is more flexible when a single address can serve as both shipping and billing address.

## 3. Why Can Repeating Columns and Embedded Lists Cause Problems?

### Fixed Repeating Columns

Suppose an employee table has the following columns:

~~~sql
CREATE TABLE employee_legacy (
    employee_id BIGINT PRIMARY KEY,
    certificate_name_1 VARCHAR(200),
    certificate_issuer_1 VARCHAR(200),
    certificate_expiry_1 DATE,
    certificate_name_2 VARCHAR(200),
    certificate_issuer_2 VARCHAR(200),
    certificate_expiry_2 DATE,
    certificate_name_3 VARCHAR(200),
    certificate_issuer_3 VARCHAR(200),
    certificate_expiry_3 DATE
);
~~~

This design has several limitations:

- The maximum number of certifications is hardcoded by the number of column groups.
- When a fourth group is needed, both the schema and application must change.
- Many columns can be NULL, making it unclear whether no certification exists or information was not collected yet.
- Querying, sorting, and filtering across all positions require repeating conditions.
- Attaching verification status, file attachments, or history to each individual certification is difficult.
- Unique constraints on certificate name or code are hard to enforce consistently across positions.

### Delimited Lists in a Single Column

For example, storing `certificates = "AWS,Oracle,Java"` or `phones = "090...,091..."` may look simple yet causes problems:

- Foreign keys cannot be used to reference individual elements.
- Hard to enforce uniqueness and value domains for each element.
- Hard to update or delete exactly one value.
- Searches can mistake one value for a substring of another.
- Per-element metadata cannot be attached cleanly.
- You must define escaping rules for delimiters, whitespace, and special characters yourself.

### When a JSON List Can Still Be Appropriate

A document or JSON array can be a good option if the group of values is read and updated together with a single aggregate, the structure evolves flexibly, and neither referential relationships nor strict per-element constraints are needed. However, you must evaluate size, update frequency, query patterns, and per-element validation. JSON does not eliminate the need to define schemas and data rules.

## 4. Signs That a Repeating Group Should Be Extracted

No single criterion decides every case. The following signs indicate you should consider extracting the repeating group.

### Variable Element Count

If the number of elements can grow or shrink by business need, fixed columns do not naturally reflect cardinality. For instance, an order can have from one to hundreds of line items; you should not create `item_1` through `item_100`.

### Each Element Has Its Own Attributes

If each element has its own creation date, status, type, verifier, priority, or notes, the element already has its own structure. Extracting it into a child record enables cleaner constraints and updates.

### Need to Query or Update Individual Elements

If users need to find employees with valid certifications, delete a contact number, edit the expiration date of one certification, or aggregate element counts by type, a separate structure provides better support.

### Integrity Rules Across the Set of Elements

Examples:

- No two certifications may share the same serial number for the same employee.
- Each customer may have at most one active primary phone number.
- An order line must have a positive quantity.
- An employee cannot have two overlapping employment periods if policy prohibits it.
- The sum of allocation percentages across components must equal 100%.

These rules are generally difficult to express using repeating columns or delimited strings.

### Elements Have Their Own Lifecycle or Relationships

If a certification can be verified, revoked, have documents attached, be referenced by a competency profile, or carry status history, it may need its own identity. In that case, modeling it as a child entity is reasonable.

### Need to Retain History

If each change to an element must record effective time, modifier, or prior state, a child structure allows clear history management. Never overwrite an old value when the business requires traceability.

## 5. Choosing the Separate Structure: Child Entity or Value Object?

Once you decide not to keep the repeating group in fixed columns, choose the appropriate level of structure.

| Question | Child value object | Child entity |
|---|---|---|
| Does it have an independent identity? | Usually no | Yes |
| Does it have its own lifecycle? | Usually tied to the owner | Can be independent within the owner's scope |
| Is it referenced from elsewhere? | Usually no | Possibly |
| Does it have its own metadata? | May have some, dependent on owner | Usually yes |
| Deleting the parent owner | Usually deleted together | Depends on ownership and retention rules |
| Example | A snapshot address on an order | A certification verified and referenced across multiple profiles |

A **child value object** fits when an element has meaning only in the owner's context, is created and deleted with the owner, and needs no independent references. For example, line items of an order can belong to the order aggregate; each line is identified by its line number within the order.

A **child entity** fits when an element has its own identity, is managed independently, or is referenced from multiple places. For example, a verified certification can link to an employee profile, a competency profile, and an audit workflow.

You can start with a value object and promote it to an entity when lifecycle, referencing, or history requirements emerge. What matters is preserving business meaning and having a transition plan if the structure is already in use.

## 6. Modeling Repeating Groups in Relational Databases

In the relational model, a repeating group is typically extracted into a child table. The child table holds a foreign key to the parent entity and columns describing one occurrence of the group.

Instead of reserving slots such as `certificate_1`, `certificate_2`, `certificate_3`, each occurrence is stored as a row in the child table. This represents the element count by row count, allowing elements to be added without altering the schema whenever demand grows. Columns within a row still describe one specific element of the group.

### Example: Employee with Multiple Certifications

~~~mermaid
erDiagram
    EMPLOYEE ||--o{ EMPLOYEE_CERTIFICATE : holds
    EMPLOYEE {
        bigint employee_id PK
        string employee_name
    }
    EMPLOYEE_CERTIFICATE {
        bigint certificate_id PK
        bigint employee_id FK
        string certificate_code
        string certificate_name
        string issuer
        date issued_on
        date expires_on
        string status
    }
~~~

Illustrative DDL:

~~~sql
CREATE TABLE employee (
    employee_id BIGINT PRIMARY KEY,
    employee_name VARCHAR(160) NOT NULL
);

CREATE TABLE employee_certificate (
    certificate_id BIGINT PRIMARY KEY,
    employee_id BIGINT NOT NULL,
    certificate_code VARCHAR(100) NOT NULL,
    certificate_name VARCHAR(200) NOT NULL,
    issuer VARCHAR(200) NOT NULL,
    issued_on DATE,
    expires_on DATE,
    status VARCHAR(20) NOT NULL,
    CONSTRAINT fk_certificate_employee
        FOREIGN KEY (employee_id) REFERENCES employee(employee_id),
    CONSTRAINT uq_employee_certificate_code
        UNIQUE (employee_id, certificate_code),
    CONSTRAINT ck_certificate_dates
        CHECK (expires_on IS NULL OR issued_on IS NULL OR expires_on >= issued_on)
);
~~~

Each `employee_certificate` row is one occurrence of the certificate attribute group. The foreign key identifies the owning parent. The surrogate key `certificate_id` is used because a certification can be independently verified or referenced; `UNIQUE(employee_id, certificate_code)` enforces the rule that certificate codes do not repeat within the same profile under the example's assumption.

If a certification has no separate identity and is not referenced elsewhere, a composite key `(employee_id, certificate_code)` may suffice. Choosing a surrogate key does not eliminate business constraints.

### Example: Order with Multiple Line Items

~~~mermaid
erDiagram
    CUSTOMER_ORDER ||--|{ ORDER_LINE : contains
    PRODUCT ||--o{ ORDER_LINE : identifies
    CUSTOMER_ORDER {
        bigint order_id PK
        datetime placed_at
        string status
    }
    ORDER_LINE {
        bigint order_id PK, FK
        int line_no PK
        bigint product_id FK
        int quantity
        decimal unit_price_snapshot
    }
~~~

Here, each line item is a group comprising product, quantity, and price at order placement. Line items belong to the order; the line number has meaning within the order's scope. A composite key `(order_id, line_no)` can be used if lines do not need an independent ID. If other systems must reference individual lines, `line_id` can be added while retaining `UNIQUE(order_id, line_no)`.

If DDL for the line-item table is needed, assuming `customer_order` and `product` already exist, a composite key can be declared as follows:

~~~sql
CREATE TABLE order_line (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price_snapshot DECIMAL(12, 2) NOT NULL,
    CONSTRAINT pk_order_line PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_line_order
        FOREIGN KEY (order_id) REFERENCES customer_order(order_id),
    CONSTRAINT fk_line_product
        FOREIGN KEY (product_id) REFERENCES product(product_id),
    CONSTRAINT ck_line_quantity CHECK (quantity > 0),
    CONSTRAINT ck_line_price CHECK (unit_price_snapshot >= 0)
);
~~~

### Indexes for Child Tables

Common queries may include:

- Retrieving all certifications for an employee.
- Finding employees holding a specific certification type or an unexpired certification.
- Retrieving the line items of an order.
- Finding orders containing a specific product.

A primary key or index leading with the foreign key usually supports parent-based lookups. Indexes on filter attributes such as `status`, `expires_on`, or `product_id` should only be added when required by the workload. Every index consumes storage and increases write overhead; validate with representative queries and data.

## 7. Modeling in Document, Graph, and Analytical Databases

Extracting a repeating group into a separate structure does not necessarily mean creating a separate relational table in every model family.

| Model family | How repeating groups are represented | When suitable |
|---|---|---|
| Relational | Child table with FK; each repetition is a row | Need per-element querying, constraints, joins, or independent updates |
| Document | Array of objects or child documents in a separate collection | Elements are usually read/written with the aggregate or need an independent lifecycle |
| Graph | Multiple edges or child nodes linked to a parent node | Elements have multi-hop relationships, are shared, or are referenced |
| Analytical | Fact, dimension, or bridge table at a defined grain | Need aggregation, historical analysis, or linking one record to many values |

### Document: Embed or Reference?

An employee profile can embed an array of certifications if the count is moderate, certifications are read together with the profile, and updates typically happen within the same aggregate. If certifications carry large documents, are referenced by multiple profiles, or need high-volume independent querying, a separate collection may fit better.

~~~json
{
  "employeeId": "emp_102",
  "name": "Le Minh",
  "certificates": [
    {
      "code": "DB-2025-01",
      "name": "Database Fundamentals",
      "issuer": "Training Institute",
      "issuedOn": "2025-03-10",
      "expiresOn": "2028-03-10",
      "status": "VERIFIED"
    },
    {
      "code": "SEC-2024-09",
      "name": "Security Essentials",
      "issuer": "Professional Board",
      "issuedOn": "2024-08-01",
      "expiresOn": null,
      "status": "PENDING"
    }
  ]
}
~~~

The `certificates` array is a structured repeating group. Each element has its own metadata. If updating an element must preserve consistency with the parent profile, define the aggregate boundary and the DBMS's atomic update mechanism.

### Graph: Node or Edge?

If a repeating group is simply a list of values belonging to one entity, it can be represented by multiple edges from the parent node to child nodes or by properties on edges. If an element has its own identity and can connect to many other nodes, model it as its own node.

For example, employee skills can be shared `Skill` nodes. The `HAS_SKILL` relationship can store proficiency level, assessment date, and verifier. Here, proficiency level is not a shared property of `Skill` itself, but a property of the relationship between a specific employee and skill.

~~~mermaid
flowchart LR
    E["Employee"] -->|HAS_SKILL| S1["Skill: SQL"]
    E -->|HAS_SKILL| S2["Skill: Data Modeling"]
    S1 --> M1["level: ADVANCED"]
    S2 --> M2["level: INTERMEDIATE"]
~~~

### Analytical: Mind the Grain and Measure Fan-Out

If each employee has multiple certifications, a bridge table can link the employee dimension with the certificate dimension. Before joining tables, determine the fact grain. If the fact is at the per-employee grain yet joins to three certifications, the employee's revenue or headcount metric could be tripled.

Decide whether the report needs to count employees, count certifications, or allocate measures across certifications. Never assume a one-to-many join preserves totals from the "one" side.

## 8. Business Rules for Repeating Groups

When extracting a repeating group, document the rules governing both the overall set of elements and each individual element.

### Cardinality

Record minimum and maximum counts, for example:

- An employee has 0..N certifications.
- A draft order may have 0..N lines; a confirmed order has 1..N lines.
- Each customer has 0..N contact numbers.
- An account has exactly one active primary identifier if rules require it.

Do not place `NOT NULL` or maximum caps in the schema unless confirmed by the business. Rules can depend on status or point in time.

### Uniqueness

Determine which elements must not repeat:

- Is a certificate code unique within an employee or across the entire organization?
- Can one phone number belong to multiple customers?
- Can a product appear multiple times in the same order or must quantities be merged?
- Can an employee have multiple skills with the same name yet different levels or assessment sources?

Uniqueness scope is often a combination of the parent key and element attributes, yet it must follow business rules.

### Ordering

A repeating group is ordered when position carries meaning: workflow steps, address priority, display line order, or chronological periods. In those cases, store an explicit position or timestamp. If order has no meaning, never rely on physical row order or array order.

### Validity and History

An element may be active, expired, revoked, or superseded. Determine whether the system stores only the current state or every version over time. If storing history, define effective dates, end dates, modifier, and non-overlap rules if required by the business.

### Set-Wide Rules

For instance, at most one active primary contact number or allocation percentages summing to 100% are rules spanning multiple rows. A simple per-row `CHECK` cannot enforce them. Use appropriate DBMS mechanisms, transactions, advanced constraints, or concurrency-controlled business workflows. Test cases where two transactions update the element set concurrently.

## 9. When Not to Extract a Separate Structure

Extracting a structure helps when it solves a concrete need, yet it also adds relationships, queries, and management rules. You can keep the group inside the parent structure when:

- The number of elements is fixed and small, determined by the business rather than an arbitrary cap.
- Elements serve different roles rather than being repetitions of the same kind.
- Components are always read and written as a single unit.
- There is no need to query, constrain, or reference individual elements independently.
- Elements have no separate lifecycle or history.
- Embedded structures stay within size limits and update patterns suited to the DBMS.

For example, shipping address and billing address can be two separate composite attributes if every order has strictly these two roles with different rules. Splitting them into a child table solely for "clean normalization" can increase joins without delivering business value.

A structure can start simple and be extracted when workload or rules change. Still, document assumptions and monitor signs such as growing element counts, per-element queries, sharing needs, and history requirements so you know when to evolve it.

## 10. Decision Process for Extracting Repeating Groups

You can follow these steps when analyzing a group of fields:

1. **Identify repeating patterns:** look for suffixed fields, embedded lists, or data groups entered multiple times.
2. **Confirm semantics:** ask whether each repetition shares the same meaning and structure or represents distinct fixed roles.
3. **Determine cardinality:** are minimum/maximum counts fixed, or can they grow over time?
4. **Identify metadata:** does each element have its own status, timestamps, order, creator, label, or attributes?
5. **Check lifecycle:** are elements created, edited, verified, revoked, or deleted independently?
6. **Check relationships:** are elements referenced from elsewhere or shared across multiple owners?
7. **Determine workload:** to what extent must individual elements be searched, filtered, aggregated, or updated?
8. **Choose the structure:** child table, associative entity, nested object in a document, separate collection, node/edge, or analytical bridge.
9. **Define integrity rules:** keys, uniqueness, cardinality, ordering, validity, and set-wide constraints.
10. **Validate trade-offs:** test with representative data and queries, verify concurrency, and assess cost of change.

### Quick Decision Matrix

| Signal | Keep in parent structure | Extract separate structure |
|---|---|---|
| Count | Fixed, small, role-specific | Variable or not bounded upfront |
| Metadata | None or minimal | Each element has multiple attributes of its own |
| Queries | Always read with parent | Need to search/filter/aggregate individual elements |
| Lifecycle | Fully dependent on parent | Has separate status, history, or handling |
| Relationships | Not referenced separately | Can link to other entities |
| Integrity | Simple rules inside parent | Needs keys, uniqueness, or set-wide rules |
| Size | Small and bounded | Grows significantly or includes large documents/files |

This matrix supports discussion. The final decision should be justifiable by business rules and actual queries.

## 11. Validating the Model After Extraction

After converting a repeating group into a separate structure, verify:

- Is a parent record with zero child elements valid?
- Can multiple child elements be created for the same parent?
- Do unique constraints cover the right scope?
- When deleting or archiving a parent, how are child elements handled?
- Are orphaned elements prevented?
- Are rules such as at most one primary element protected under concurrent updates?
- Do common queries have appropriate indexes?
- Is historical data preserved when an element changes or is revoked?

Example query finding employees with expired certifications:

~~~sql
SELECT
    e.employee_id,
    e.employee_name,
    c.certificate_name,
    c.expires_on
FROM employee e
JOIN employee_certificate c
  ON c.employee_id = e.employee_id
WHERE c.expires_on < CURRENT_DATE
  AND c.status = 'VERIFIED';
~~~

This query illustrates the benefit of storing each certification as its own row: you can filter and return individual certifications by expiration date and status. When designing indexes, base them on data distribution, predicates, and the actual DBMS execution plan.

When migrating from repeating columns to a child table, the migration must specify the mapping order clearly: each old column group becomes one child row; how empty groups are handled; whether incomplete data is retained; and what rules merge duplicate records. After backfilling, reconcile element counts and component values before switching the application to the new structure.

## 12. Practice Exercises and Evaluation Criteria

### Exercise 1 — Employee Profile

An employee has multiple contact numbers, certifications, skills, and employment periods. Each certification has a name, issuer, code, issue date, and expiration date. Each skill has a proficiency level and assessment date.

Classify the repeating groups and determine which groups are value objects and which require separate entities. Propose cardinality, keys, and uniqueness rules.

### Exercise 2 — Orders

An order has multiple line items. Each line has a product, quantity, unit price at purchase time, discount, and notes. A product may appear at most once in an order, or appear multiple times if split across different delivery batches.

Explain the two assumptions that lead to two different models. Propose keys and constraints for each case.

### Exercise 3 — Product with Multiple Images

Each image has a URL, image type, display order, moderation status, and upload timestamp. One image may be reused across multiple products.

Determine whether images should be a single multi-valued attribute, an embedded object group, or an independent entity. Explain based on sharing, lifecycle, and moderation.

### Exercise 4 — Schema Migration

A legacy table has columns `phone_1`, `phone_2`, `phone_3`. Design the new child table, backfill rules, duplicate-number handling, and reconciliation queries before dropping the old columns.

### Self-Evaluation Rubric

| Criterion | Meets expectations when |
|---|---|
| Identification | Detects repeating field groups and explains their meaning |
| Classification | Distinguishes repeating groups from composite attributes, multi-valued attributes, and fixed roles |
| Boundaries | Chooses accurately between value objects and child entities |
| Cardinality | Defines counts, ordering, and uniqueness |
| Integrity | Protects foreign keys, primary elements, and set-wide rules |
| Workload | Representation supports actual queries and updates |
| Evolution | Supports adding elements, retaining history, and safe migrations |

An attribute group should be extracted when the current representation can no longer cleanly express the count, structure, relationships, or lifecycle of individual elements. The goal is to select a structure just sufficient to protect business meaning, querying, and controlled data evolution. When these decisions are documented explicitly, relational, document, graph, and analytical models can be evaluated against the same requirements baseline.
