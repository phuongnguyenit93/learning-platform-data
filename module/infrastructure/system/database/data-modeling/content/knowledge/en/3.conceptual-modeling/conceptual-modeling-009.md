# Moving from a Conceptual Model to a Logical Model While Preserving Meaning

A conceptual model describes the business domain using concepts such as customer, order, product, payment, and the relationships among them. A logical model turns that understanding into data structures that can be organized and verified: data types, attributes, identifiers, relations, keys, and constraints. This transformation must preserve the confirmed business meaning.

If you simply turn entity names into table names and attribute names into column names, the model may look reasonable while still losing information. A many-to-many relationship might get turned into an incorrect one-to-many relationship; a multi-valued attribute might be stuffed into a string; a uniqueness rule might be overlooked; or a weak entity might lose its identifying dependency on its parent entity.

This lesson presents a systematic conversion approach, how to choose appropriate logical structures, and how to verify whether the logical model still fully expresses the rules in the conceptual model.

**After this lesson, you will be able to:**

- Distinguish between a conceptual model, a logical model, and a physical model.
- Transform entities, attributes, and relationships into appropriate logical structures.
- Correctly represent one-to-one, one-to-many, many-to-many, recursive, and n-ary relationships.
- Preserve identifiers, uniqueness, optionality, value domains, and business rules.
- Identify cases where attributes must be split, associative entities must be created, or history must be stored.
- Validate the logical model using business scenarios and invariant rules.

## 1. The Three Modeling Levels and the Goal of Transformation

### 1.1. Conceptual Model

The conceptual model answers the question: **What concepts does the business care about, and how do they relate to one another?**

It typically captures:

- Business entity types or concepts;
- Meaningful attributes;
- Relationships between concepts;
- Cardinalities and mandatory or optional participation;
- Key business rules;
- The scope and definition of each concept.

The conceptual model prioritizes shared understanding among business experts, analysts, developers, and testers. It does not need to decide storage details specific to a particular database management system.

### 1.2. Logical Model

The logical model answers the question: **What structures must data be organized into—with which attributes, identifiers, relations, and constraints—to accurately represent the business?**

For a relational logical model, these structures typically include:

- Relations, typically implemented as tables;
- Attributes, value domains, and nullability (mandatory vs. optional);
- Primary keys, candidate keys, and foreign keys;
- Uniqueness, referential, and check constraints;
- Associative relations for cases requiring many-to-many representation or relationship attributes;
- History structures if the business needs to track changes.

A logical model can use abstract terms and data types such as **Money**, **Date**, **Identifier**, **Boolean**, or defined status domains. There is no need yet to pick DBMS-specific physical types.

### 1.3. Physical Model

The physical model answers the question: **How will the logical structure be implemented on a specific platform?**

It can decide exact data types, key generation strategies, indexes, partitioning, storage, compression, system-convention object naming, and performance optimizations.

For example, the logical model may have an **order_created_at** attribute representing when an order was created. The physical model decides the exact timestamp type, precision, time zone handling, indexing, and storage layout on the chosen DBMS.

| Modeling Level | Focus | Example Decision |
|---|---|---|
| Conceptual | Business meaning | One order has many order lines |
| Logical | Data structures and constraints | Relation ORDER_LINE references ORDER and PRODUCT_VARIANT |
| Physical | Platform implementation | Column types, indexes, partitions, tablespaces, or storage strategy |

You should not skip the logical model and jump straight from a conceptual diagram to `CREATE TABLE` statements. Without clarifying keys, value domains, relationships, and constraints first, physical decisions easily lock in a flawed understanding.

## 2. Principles for Preserving Business Meaning

A successful transformation does not mean keeping the diagram's exact shape. One conceptual entity may become one or more logical relations; one conceptual relationship may be represented by a foreign key or an associative relation. The shape changes, yet the facts and rules the system can represent must remain equivalent to the requirements.

Preserve at least the following elements:

1. **Definitions:** each logical structure still represents the exact confirmed concept.
2. **Granularity:** one row or record represents exactly one business unit.
3. **Identifiers:** objects can be stably distinguished and referenced.
4. **Cardinalities:** the permitted number of objects participating in a relationship remains accurate.
5. **Participation:** mandatory vs. optional participation is not altered.
6. **Value domains:** attributes accept only business-permitted values.
7. **Invariant rules:** conditions such as uniqueness, non-negativity, non-overlapping ranges, or matching scopes remain preserved.
8. **Time and history:** effective timestamps, recording timestamps, and traceability requirements are not lost.
9. **Context:** same-named concepts with different meanings remain separated; aliases do not create new concepts when they are truly synonymous.

A useful evaluation question is: "With this logical model, can the system store and validate every valid case while preventing cases forbidden by the business?"

## 3. Step-by-Step Process from Conceptual to Logical

You can follow this sequence:

### Step 1: Finalize Definitions and Scope

Review the definition, role, rules, and scope of each concept. If an entity or attribute name is still ambiguous, clarify it before mapping. Never infer structure solely from a name.

### Step 2: Confirm Granularity

Explicitly state what a single instance represents. For example, one `ORDER` record represents one created order; one `ORDER_LINE` record represents one line item recorded within an order. This prevents placing line-level attributes at the order level or counting one order as multiple orders.

### Step 3: Determine the Logical Structure Type

For each concept, decide whether it becomes:

- An independent relation;
- An attribute of another relation;
- An associative relation;
- A value domain or reference catalog;
- A history structure;
- Or a calculated-only concept that does not necessarily get stored as source data.

### Step 4: Map Attributes

Identify single-valued, multi-valued, composite, derived, or time-effective attributes. Check value domains, units of measure, precision, and nullability.

### Step 5: Choose Identifiers and Keys

Identify candidate keys from business rules, then choose the primary key in the logical model. Document alternate keys and any other uniqueness conditions.

### Step 6: Map Relationships and Cardinalities

Convert each conceptual relationship into an appropriate foreign key or associative relation. Preserve both minimum and maximum cardinalities as well as participation conditions.

### Step 7: Express Constraints

Translate business rules into verifiable logical constraints: mandatory checks, uniqueness, referential integrity, value domains, cross-attribute conditions, and temporal rules.

### Step 8: Verify Semantic Integrity

Use concrete examples, boundary cases, and exception scenarios to test the model. Cross-check against the conceptual model and source requirements.

~~~mermaid
flowchart TD
    A["Confirmed conceptual model"] --> B["Finalize definitions, scope, and granularity"]
    B --> C["Map entities and attributes"]
    C --> D["Identify identifiers and candidate keys"]
    D --> E["Map relationships and cardinalities"]
    E --> F["Represent value domains and constraints"]
    F --> G["Create logical model"]
    G --> H["Test scenarios and business rules"]
    H --> I{"Is meaning preserved?"}
    I -->|No| J["Adjust mapping or clarify business rules"]
    J --> C
    I -->|Yes| K["Finalize logical model"]
~~~

## 4. Mapping Entities to Logical Relations

In the relational model, an entity type is typically mapped to a relation. Each entity instance becomes a row; single-valued attributes become attributes of the relation.

For example, the conceptual entity `CUSTOMER` has the attributes:

- Customer code;
- Display name;
- Registration date;
- Contact email.

It can be mapped to the logical relation:

**CUSTOMER**

| Attribute | Meaning | Logical Notes |
|---|---|---|
| customer_id | Customer identifier | Primary key |
| display_name | Display name | Mandatory if required by business |
| registered_at | Registration timestamp | Timestamp |
| contact_email | Contact email | May be optional; whether unique must be confirmed |

An entity does not necessarily map to a single table in every case. When attributes have their own lifecycle, access permissions, or granularity, additional relations may be needed. Conversely, some concepts are only roles or attributes and do not require an independent relation.

### 4.1. Strong Entities and Dependent Entities

A strong entity can be identified independently via its own identifier. A dependent entity (weak entity) relies on a parent entity for identification or existence under business rules.

For example, `ORDER_LINE` usually has no independent meaning outside the order containing it. Some systems identify a line by the pair `(order_id, line_number)`.

| Attribute | Role |
|---|---|
| order_id | References parent order |
| line_number | Distinguishes lines within an order |
| product_variant_id | Selected variant |
| quantity | Quantity |
| unit_price | Price applied to the line |

The logical key can be `(order_id, line_number)` if line numbers are unique within each order. If the business uses an independent stable line code, that code may be chosen as the primary key alongside a uniqueness constraint on the order-and-line-number pair. The decision must reflect actual identification rules.

### 4.2. Single-Valued and Composite Attributes

A single-valued attribute holds one value at the chosen granularity. A composite attribute consists of multiple components, each carrying its own meaning.

For example, `ADDRESS` may include:

- Street and house number;
- Ward or commune;
- District;
- Province or city;
- Postal code;
- Country.

If the system must search, validate, or analyze by individual component, the logical model should split them into appropriate attributes. If an address is stored solely for verbatim display and requires no part-level processing, keeping a single address line may suffice. Base this on requirements rather than mechanically splitting every string into multiple columns.

### 4.3. Multi-Valued Attributes

An attribute may have multiple values for a single instance—for instance, a customer with multiple contact phone numbers or a product with multiple tags.

In a relational model, do not store a list of values inside a single string if you need to query, enforce uniqueness, or link individual values. Create a separate relation:

**CUSTOMER_PHONE**

| Attribute | Meaning |
|---|---|
| customer_id | Customer owning the phone number |
| phone_number | A phone number |
| phone_type | Number type, if categorized by business |
| is_primary | Whether this is the primary number |

The key can be `(customer_id, phone_number)` if a number appears only once in a customer's profile. If phone numbers need independent identifiers or history, the structure may need to expand.

If the order of values matters—such as contact priority—store an explicit position or sequence number. Never rely on arbitrary database return order.

### 4.4. Derived Attributes

A derived attribute is calculated from other data, such as age from date of birth or order total from order lines and associated charges.

In the logical model, clearly document the formula and source data. Derived values do not necessarily need to be stored as source data. If a copy must be persisted for historical or performance reasons, define when it is recalculated, which source is authoritative, and how changes to source data are handled.

For example, `order_total` may combine line totals, taxes, shipping fees, and discounts per pricing rules. Never assume an order total is simply the sum of `quantity * unit_price` when the business includes other components.

## 5. Mapping Relationships and Cardinalities

Conceptual relationships describe how instances connect to one another. In a relational logical model, foreign keys and associative relations are typically used to represent them.

### 5.1. One-to-Many Relationship (1:N)

For example, one customer can place many orders; each order belongs to one customer under system rules.

Logical structure:

- `CUSTOMER` holds primary key `customer_id`.
- `ORDER` holds foreign key `customer_id` referencing `CUSTOMER`.

| CUSTOMER | ORDER |
|---|---|
| customer_id (PK) | order_id (PK) |
| display_name | customer_id (FK) |
| ... | created_at |

The foreign key goes on the "many" side because each order must point to its associated customer. If the business allows guest orders without a customer profile, `customer_id` may be optional or another way to represent the buyer is required. Never default to `NOT NULL` if minimum participation has not been confirmed.

### 5.2. One-to-One Relationship (1:1)

For example, one employee may have one supplementary profile, and each profile belongs to exactly one employee.

You can place the foreign key in one of the two relations and add a uniqueness constraint so an employee cannot have multiple corresponding profiles. If the relationship is mandatory on both sides and their lifecycles always move together, the team should consider whether the two concepts truly belong in one relation.

| Rule | Common Logical Representation |
|---|---|
| An employee has at most one profile | FK `employee_id` in `EMPLOYEE_PROFILE` |
| Every profile must belong to an employee | Mandatory FK |
| An employee has only one profile | FK with `UNIQUE` constraint |

A unique foreign key enforces "at most one"; a mandatory foreign key enforces "at least one" on the profile side. Check both directions so a 1:1 relationship is not mistaken for 1:N.

### 5.3. Many-to-Many Relationship (M:N)

For example, one order contains many products and one product can appear in many orders. You cannot place a single foreign key on one side to fully represent a many-to-many relationship.

Create the associative relation `ORDER_LINE`:

- `order_id` references `ORDER`;
- `product_variant_id` references `PRODUCT_VARIANT`;
- `quantity`, `unit_price`, and other attributes describe the product selection within the order.

An associative relation is not merely a technical bridge between two tables. It carries its own business meaning: a specific line item within an order. When a relationship has attributes or needs its own identifier, creating an associative structure is necessary.

### 5.4. Recursive Relationship

A recursive relationship is a relationship between instances of the same entity type.

For example, an employee can manage other employees. In the logical model, you can use a foreign key `manager_employee_id` in `EMPLOYEE` referencing `employee_id` in the same relation.

Clarify:

- Can an employee have no direct manager?
- Can an employee manage multiple people?
- Is self-management allowed?
- Are management cycles allowed?

A foreign key guarantees the referenced manager exists, yet does not automatically prevent every cycle in a management hierarchy. Anti-cycle rules may require business logic or additional validation mechanisms.

### 5.5. N-ary Relationship

A relationship can link three or more entity types. For instance, a supplier supplies a product to a warehouse under specific contract terms. Splitting it into three binary relationships can lose the fact that a supply arrangement is a combination of all three parties.

You can create an associative relation `SUPPLIER_PRODUCT_WAREHOUSE` containing foreign keys referencing supplier, product, and warehouse, alongside attributes such as supply price, effective date, or expected lead time.

The primary key or uniqueness constraint must reflect what distinguishes an agreement. Do not assume every n-ary relationship has a composite key of all its foreign keys; confirm whether a supplier can have multiple agreements for the same product and warehouse across different time periods or contracts.

## 6. Preserving Identifiers and Keys

An identifier describes how a business instance is recognized. A logical key is the attribute structure used to distinguish and reference rows in a relational model.

Distinguish:

- **Candidate key:** a minimal set of attributes that can uniquely identify a row.
- **Primary key:** the candidate key chosen as the main identifier in the relation.
- **Alternate key:** another candidate key not chosen as the primary key.
- **Foreign key:** an attribute or set of attributes referencing a key of another relation.

For example, a customer may have `customer_id` and a business customer code. If the business code is unique across the enterprise, it can serve as an alternate candidate key. Email should usually not be chosen automatically as a key because it can change, be shared, or follow varying uniqueness rules across businesses.

### 6.1. Simple Keys and Composite Keys

A simple key uses one attribute. A composite key uses multiple attributes together.

For example, `(order_id, line_number)` can distinguish a line item within a single order. `line_number` alone repeats across different orders and is insufficient to identify a line system-wide.

Composite keys must be checked for minimality and stability. Do not add attributes to a key merely to feel safer about uniqueness if they are unnecessary for identification.

### 6.2. Surrogate Keys and Business Keys

A surrogate key such as a technical ID can be helpful when a business key is long, mutable, or dependent on external systems. However, adding an ID does not eliminate business uniqueness rules.

For example, even with `customer_id` as the primary key, the system may still need a uniqueness constraint on customer code within an organization. Dropping that constraint allows creating two profiles with the same business code even though each row has its own ID.

### 6.3. Foreign Keys and Referential Integrity

A foreign key ensures a referenced value points to an existing row in the target relation. It prevents orphaned data, yet does not express every business rule on its own.

For example, `ORDER.customer_id` references an existing customer. Yet the rule "a blocked customer cannot create new orders" is an additional business rule that a foreign key alone cannot enforce.

## 7. Mapping Value Domains and Constraints

Every attribute needs a clear value domain. A domain can describe abstract type, bounds, unit of measure, valid value set, and mandatory conditions.

Example:

| Attribute | Logical Domain or Rule |
|---|---|
| quantity | Positive quantity by item unit; whether fractional values are allowed must be confirmed |
| unit_price | Non-negative monetary amount, tied to currency and rounding rules |
| order_status | One of the valid states per order lifecycle |
| registered_at | Registration timestamp, with time zone rules |
| email | String matching accepted format; uniqueness scope must be specified |

### 7.1. Mandatory and Optional Constraints

A mandatory attribute cannot be missing a value in valid records. An optional attribute may be absent or not applicable.

Do not use `NULL` to represent every state of "unknown", "not yet provided", "not applicable", and "pending". Those meanings differ. When the distinction carries business value, use explicit statuses or structures.

### 7.2. Uniqueness Constraints

Uniqueness rules can apply to a single attribute or a combination of attributes.

Examples:

- Customer code unique within an organization;
- Line number unique within an order;
- Each warehouse has at most one default configuration record for a configuration type;
- One SKU has only one primary scan barcode within a defined scope.

Specify the uniqueness scope explicitly. "Unique email" might mean globally unique across the system, per tenant, or only among active accounts.

### 7.3. Domain and Check Constraints

Domain constraints validate whether a value is legal—for instance, quantity greater than 0, end date not earlier than start date, or rate within an allowed range.

Cross-attribute constraints validate multiple attributes or multiple relations together. Examples:

- End date must be greater than or equal to start date;
- A delivered order must have valid delivery details;
- A shipment line must not allocate more than the remaining shippable quantity;
- Total refunded amount must not exceed total collected amount under financial rules.

Some rules can be expressed as declarative constraints in the logical model; others require workflows or business logic because they span multiple rows, steps, or states over time.

### 7.4. Relationship Participation Constraints

Minimum and maximum cardinalities must be preserved. Examples:

- Every order line must belong to exactly one order;
- An order must have one or more lines once confirmed;
- An order may have no payment yet if post-payment is allowed;
- A shipment package must belong to a specific delivery workflow.

A foreign key guarantees that a parent reference exists, yet does not automatically enforce minimum conditions on the parent side. For example, it does not guarantee a confirmed order has at least one order line; that rule may need enforcement during order state transitions.

## 8. Comprehensive Example: From a Sales Conceptual Model to a Logical Model

Suppose the business has confirmed:

- A customer can create multiple orders.
- Each order belongs to one customer within the registered sales scope.
- An order has at least one line when confirmed.
- Each line belongs to exactly one order and references one product variant.
- An order can have multiple payment attempts.
- An order can be shipped across multiple packages (shipments).
- An order line can be allocated across multiple shipments.
- The selling price at placement time must be preserved to explain historical transactions.

From this, an illustrative logical model can be constructed:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_LINE : contains
    PRODUCT_VARIANT ||--o{ ORDER_LINE : selected_as
    ORDER ||--o{ PAYMENT_ATTEMPT : has
    ORDER ||--o{ SHIPMENT : fulfilled_by
    SHIPMENT ||--o{ SHIPMENT_LINE : includes
    ORDER_LINE ||--o{ SHIPMENT_LINE : allocated_to
~~~

The logical relations can be described as follows:

**CUSTOMER**

| Attribute | Rule |
|---|---|
| customer_id | PK |
| customer_code | Unique within organization scope if confirmed by business |
| display_name | Mandatory |
| registered_at | Registration timestamp |

**ORDER**

| Attribute | Rule |
|---|---|
| order_id | PK |
| customer_id | FK to CUSTOMER, mandatory per business assumption |
| order_number | Business lookup code; unique within confirmed scope |
| created_at | Order creation timestamp |
| order_status | Belongs to order status domain |

**ORDER_LINE**

| Attribute | Rule |
|---|---|
| order_id | FK to ORDER |
| line_number | Sequential line number within order |
| product_variant_id | FK to PRODUCT_VARIANT |
| quantity | Valid quantity by item unit |
| unit_price | Price locked at placement time |
| line_discount | Line discount per sales rules |

The reference logical key of `ORDER_LINE` is `(order_id, line_number)`. If an independent `order_line_id` is used, retain the uniqueness constraint on `(order_id, line_number)` if required by the business.

**PAYMENT_ATTEMPT**

| Attribute | Rule |
|---|---|
| payment_attempt_id | PK |
| order_id | FK to ORDER |
| attempted_at | Attempt timestamp |
| amount | Amount requested for processing |
| result_status | Attempt outcome domain |
| provider_reference | Provider reference code, unique within appropriate scope |

**SHIPMENT**

| Attribute | Rule |
|---|---|
| shipment_id | PK |
| order_id | FK to ORDER |
| shipment_number | Shipment or dispatch code per shipping rules |
| handed_over_at | Handover timestamp if occurred |
| shipment_status | Shipping status domain |

**SHIPMENT_LINE**

| Attribute | Rule |
|---|---|
| shipment_id | FK to SHIPMENT |
| order_id | Order-line reference component if using composite key |
| line_number | Order-line reference |
| shipped_quantity | Quantity allocated to this shipment |

In this example, `SHIPMENT_LINE` references an order line and a shipment. Keys and composite foreign keys must be designed so that the allocated line genuinely belongs to the order being shipped by that shipment. A surrogate key may be used for `ORDER_LINE`, yet constraints preserving order membership are still required.

This is an illustrative logical model, not a complete physical schema. Rules such as capping total shipped quantity, refund amounts, state transitions, and guest order handling must be documented and implemented at the appropriate stage.

## 9. Preserving Meaning Across Different Model Paradigms

A relational logical model is one common representation, yet a conceptual model can also be mapped to document, graph, or analytical models. Structural differences do not change business definitions.

| Model Paradigm | Transformation Approach | What Must Be Preserved |
|---|---|---|
| Relational | Entities become relations; relationships become FKs or associative relations | Keys, cardinalities, value domains, referential integrity |
| Document | Objects or aggregates become documents; nested parts become objects/arrays | Aggregate boundaries, element identifiers, updates, and history |
| Graph | Entities become nodes; relationships become edges or relationship nodes | Node/edge types, direction, cardinalities, properties, and validity |
| Analytical | Events or snapshots become facts; descriptive concepts become dimensions | Fact granularity, dimensions, measures, additivity rules, and time |

### 9.1. Document Models

A document can represent an order containing nested order lines. This works well when an order and its lines are usually read or updated together. Still, each line element needs an identifier or distinguishing rule if the business needs to edit, reference, partially ship, or track line-level history separately.

If one order line can be linked from multiple shipments, simple nesting may not suffice. Design explicit references or a separate aggregate to represent shipment allocations without falsely duplicating the original line's meaning.

### 9.2. Graph Models

A customer and an order can be two node types, with placing an order as an edge. If the edge only represents a current relationship, a single edge between customer and order may suffice. If you need to record every interaction or change history, event nodes or temporal properties on edges may be needed.

Crucially, clarify whether an edge represents an ongoing relationship or a single event occurrence. Never overload the same edge for two distinct meanings.

### 9.3. Analytical Models

An analytical model must determine fact granularity before choosing dimensions and measures. For instance, a sales fact at order-line granularity can link to product, customer, store, and date dimensions. If the fact is instead at order granularity, product-level quantity metrics may become inaccurate when an order contains multiple products.

In particular, distinguish additive, semi-additive, and non-additive measures. Quantities sold can be summed across lines; point-in-time balances and inventory levels are state snapshots and should not be summed across multiple timestamps to produce a total.

## 10. Logical Normalization and Avoiding Data Loss

After mapping, inspect dependencies and structures for duplication or update anomalies. Normalization ensures every fact and attribute is stored where it aligns with its meaning and dependencies.

For example, if product name and manufacturer info are repeated on every order line, changing the manufacturer name may require updating many places. However, the selling price at placement time is historical information belonging to the order line and must not be replaced by the current price in the product catalog.

Do not remove every copy of data mechanically. Certain values are intentionally captured as snapshots to preserve historical facts—such as locked prices, display names on documents, or shipping addresses at placement time. Distinguish duplication that causes anomalies from necessary snapshot data.

When normalizing, verify:

- Does every attribute depend properly on the relation's key?
- Are attributes of another entity repeated across multiple rows?
- Are many-to-many relationships represented by an appropriate structure?
- Are multi-valued attributes stored inside strings or repeating columns?
- Does historical data change when current catalog data changes?
- Does decomposing relations preserve the full ability to reconstruct the original data?

## 11. Verifying Whether the Logical Model Preserves Meaning

A logical model must be checked structurally and behaviorally. Seeing a diagram full of tables and keys is not enough to conclude the model is right.

### 11.1. Traceability Check

Every logical entity, attribute, relationship, and constraint should trace back to a business concept or rule. Conversely, every important business rule must have a place of representation or enforcement mechanism in the model.

You can build a traceability table:

| Requirement or Rule | Related Logical Structure | Verification Method |
|---|---|---|
| Each order belongs to one customer | ORDER.customer_id | Attempt creating an order without a valid customer |
| Each line belongs to one order | ORDER_LINE.order_id | Attempt creating a line referencing a non-existent order |
| Line number unique within an order | ORDER_LINE(order_id, line_number) | Attempt creating two lines with the same sequence number in one order |
| One line can ship across multiple shipments | SHIPMENT_LINE references ORDER_LINE | Attempt allocating one line across two shipments |
| Historical price is preserved | ORDER_LINE.unit_price | Change catalog price after ordering and check old order lines |

### 11.2. Valid Scenario Testing

Test business-permitted cases:

- One customer places multiple orders;
- One order has multiple order lines;
- One order has multiple payment attempts;
- One order line ships across multiple packages;
- One SKU exists in multiple warehouses;
- A product is renamed while past documents retain transaction-time details.

The model must represent these cases without distorting record meaning.

### 11.3. Prohibited Scenario Testing

Test business-forbidden cases:

- An order line references a non-existent order;
- Two lines in the same order violate the unique line-number rule;
- Negative quantity when the business permits only positive quantities;
- A shipment allocates more than the remaining shippable quantity;
- One unique code is used by two objects within the same scope.

If the logical model cannot represent or control a rule, add a constraint or explicitly document the enforcement mechanism at the application/business layer.

### 11.4. Information Reconstruction Check

After conversion, try joining relations to reconstruct conceptual-level information:

- From an order, can you identify the customer and order lines?
- From a shipment line, can you tell which order line was shipped and which order it belongs to?
- From payment attempts, can you trace the order's payment processing history?
- From detailed records, can you recalculate aggregate metrics per published rules?

If splitting relations loses the ability to reconstruct data or introduces invalid joins, revisit the mapping.

## 12. Common Mistakes During Conversion

1. **Turning every noun into a table:** a noun might be a role, attribute, event, or concept that does not require independent storage.
2. **Ignoring granularity:** a table has the right name, yet rows represent mixed types of business units.
3. **Placing the foreign key on the wrong side:** a 1:N relationship is inverted or the foreign key fails to reflect the participating side.
4. **Omitting associative relations for M:N:** leads to lists of IDs inside one column or losing relationship attributes.
5. **Losing optionality:** an optional business relationship gets forced as mandatory in the model.
6. **Using a surrogate key instead of a uniqueness rule:** IDs differ, yet business codes can still be duplicated.
7. **Stuffing multi-valued attributes into strings:** makes validation, searching, updating, and referencing difficult.
8. **Over-splitting attributes:** complicates the structure when there is no need to process components individually.
9. **Storing derived values without sync rules:** aggregates or totals drift out of sync with source data.
10. **Losing history:** overwriting current attributes makes past transactions unexplainable.
11. **Mapping n-ary relationships into non-equivalent binary pairs:** loses constraints across the combined tuple.
12. **Introducing physical details too early:** picking column types, indexes, or partitions before logical meaning and constraints are agreed upon.

## 13. Logical Model Completion Checklist

- [ ] Every logical structure has a clear definition and granularity.
- [ ] Every conceptual entity requiring persistence is mapped, or its exclusion is justified.
- [ ] Single-valued, composite, multi-valued, and derived attributes are distinguished.
- [ ] Candidate keys, primary keys, alternate keys, and foreign keys are defined.
- [ ] 1:1, 1:N, M:N, recursive, and n-ary relationships are accurately represented.
- [ ] Maximum and minimum cardinalities, mandatory participation, and optionality are preserved.
- [ ] Value domains, units of measure, precision, and uniqueness scopes are documented.
- [ ] Cross-attribute and temporal rules are captured.
- [ ] Historical data and snapshots are preserved for their intended business purpose.
- [ ] No attributes or relationships are lost during mapping.
- [ ] Valid cases can be represented and forbidden cases are prevented or detected.
- [ ] Logical decisions trace back to requirements and the conceptual model.
- [ ] The model has been confirmed by accountable business stakeholders.

## 14. Practice Exercise

A sales system has the following conceptual model:

- Customers place orders.
- Orders contain order lines.
- Each order line selects one product variant.
- One order can have multiple payment attempts.
- An order can be shipped in multiple packages.
- One order line can be split across multiple packages.
- Each package has multiple shipment tracking events.
- The selling price at placement time must be preserved.

Propose a relational logical model, including:

1. The list of required relations.
2. Key attributes of each relation.
3. Primary keys, foreign keys, and uniqueness constraints.
4. How to represent the many-to-many relationship between order lines and shipments.
5. How to distinguish shipments from shipment tracking events.
6. Business rules that cannot be expressed by foreign keys alone.

**Suggested Answer:**

| Relation | Granularity | Primary Keys and References |
|---|---|---|
| CUSTOMER | One customer | customer_id PK |
| ORDER | One order | order_id PK; customer_id FK |
| ORDER_LINE | One line within an order | (order_id, line_number) PK or order_line_id PK with UNIQUE |
| PRODUCT_VARIANT | One sellable variant | product_variant_id PK |
| PAYMENT_ATTEMPT | One payment attempt | payment_attempt_id PK; order_id FK |
| SHIPMENT | One package or dispatch | shipment_id PK; order_id FK |
| SHIPMENT_LINE | Portion of a line allocated to a shipment | FKs to SHIPMENT and ORDER_LINE; key per allocation rule |
| SHIPMENT_EVENT | One tracking event for a shipment | shipment_event_id PK; shipment_id FK |

`SHIPMENT_LINE` is an associative relation representing that one order line can be allocated across multiple shipments and one shipment can contain parts of multiple lines. `SHIPMENT_EVENT` has the granularity of a single scan or shipping update, so one shipment can have multiple events.

`unit_price` must be stored on `ORDER_LINE` to preserve the price locked at placement time even when product catalog prices change. Rules such as total shipped quantity not exceeding ordered quantity, confirmed orders requiring at least one line item, or shipping events following a valid sequence must be checked via cross-attribute constraints or appropriate business logic.

The exercise is complete when the logical model distinguishes orders, order lines, payment attempts, shipments, and tracking events while preserving multi-wave shipping and price history.
