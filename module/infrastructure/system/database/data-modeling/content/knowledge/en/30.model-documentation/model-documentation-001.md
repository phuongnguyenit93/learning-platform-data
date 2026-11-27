# Choosing Diagram Detail Levels by Audience and Discussion Purpose

## 1. One Data Model, Multiple Presentations

In the **DATABASE_DATA_MODELING** module, learners develop the ability to translate business requirements into a clear data model: identifying entities, relationships, constraints, normalization, keys, indexes, and storage structures; while also comparing relational, document, graph, and analytical models to choose the right solution. In the **Model Documentation** chapter, a key skill is **choosing the diagram's level of detail based on the audience and what needs to be discussed**.

Suppose an e-commerce platform wants to support **ordering, partial payments, and returns**. For the same system, three meetings raise three very different questions:

- **Product owner and business staff:** "How does an order relate to customers, product lines, and payments? Can it be paid in multiple installments?"
- **Analysts and architects:** "Which identifying keys do the entities have? Are the relationships 1–N or N–N in cardinality? How are state and history represented?"
- **Developers and DBAs:** "Which tables are created, what are the PRIMARY KEY/FOREIGN KEYs, data types, indexes, CHECK constraints, uniqueness constraints, and exact migrations?"

If you bring every column name, VARCHAR type, index, and foreign key into the first meeting, business stakeholders have to hunt for order logic among hundreds of technical details. Conversely, if you only use a rectangle "Order → Payment" when reviewing a migration, the engineering team cannot tell what the design guarantees.

**A good level of detail is not the one with the most information; it is the minimum information sufficient for the audience to accurately answer the question that needs a decision.**

This lesson focuses on creating **multiple controlled views from the same model**, rather than using one giant ERD for every person and every purpose.

### Learning Objectives

After this lesson, learners can:

1. Distinguish a **data model** from a **diagram presenting the model**.
2. Choose **conceptual**, **logical**, or **physical** diagrams according to the audience and the decision to be made.
3. Choose scope, grain, and details that can be hidden without distorting meaning.
4. Represent entities, relationships, cardinality, optionality, and critical constraints at the right level.
5. Create a multi-layered diagram set from the same e-commerce scenario, synchronized with the data dictionary and DDL.
6. Write legends, assumptions, business rules, unresolved notes, and document versions.
7. Review model changes and avoid diagrams that cause misunderstandings, technical errors, or sensitive data leaks.

## 2. Distinguishing Model, Diagram, View, and Documentation

A **data model** is the set of decisions regarding entities, attributes, relationships, keys, integrity rules, time, and business semantics. A model does not exist solely as drawings.

A **diagram** is a finite **view** of the model, selected and presented for a specific purpose.

**Model documentation** typically includes several components:

| Component | What It Explains | Can a Diagram Replace It? |
|---|---|---|
| Conceptual diagram | Core business concepts and relationships | Cannot fully replace rule descriptions |
| Logical diagram | Entities, key attributes, logical PK/FK, cardinality | Cannot replace edge-case examples |
| Physical diagram | Tables/collections/nodes/edges, column types, constraints, indexes | Cannot replace migrations/runbooks |
| Data dictionary | Definitions of each entity and field | No, drawings usually lack enough space |
| Business-rule catalog | Rules, exceptions, invariants | Some rules are hard to express with connector lines |
| ADR/decision log | Rationale for choices and rejected alternatives | Diagrams only describe state, not full reasoning |
| DDL/migration | Executable DB structure | Does not by itself prove business requirement compliance |
| Test cases | Evidence that the design satisfies invariants | A diagram is not a test |
| Ownership/lineage | Who owns the data and where it flows | Needs a dedicated view if spanning multiple systems |

A drawing can be **syntactically valid** yet wrong for the business. Conversely, a SQL schema may be deployable yet still fail to help the product owner confirm the meaning of "order," "refund," and "return."

### 2.1. A Diagram Does Not Need to Show Everything

There is no reasonable requirement forcing **every diagram to contain every table**. There should be a linked set of diagrams sharing a controlled source of truth, where each diagram answers a specific group of questions.

The key is **not omitting information that determines the reader's conclusion**. You may hide indexes in a business diagram; you must not hide that an order can have **multiple payments** if business stakeholders are validating that exact rule.

## 3. Three Core Levels of Detail: Conceptual, Logical, Physical

| Criterion | **Conceptual** | **Logical** | **Physical** |
|---|---|---|---|
| Question | What concepts and relationships exist in the business? | How is data structured and constrained? | How does a specific database store and enforce it? |
| Primary audience | Product owner, domain expert, PM | BA, architect, developer, data engineer | DBA, backend engineer, data engineer, deployment reviewer |
| Display unit | Business concepts/entities | Entities, attributes, keys, relationships | Tables, columns, types, indexes, constraints, partitions |
| Identifiers | May note business identifiers if important | PK/BK/surrogate keys per the model | Concrete PRIMARY KEY, UNIQUE, FK, sequence/UUID |
| Cardinality | Core relationships only, may note 1–N | Must specify 0..1, 1, 0..N, 1..N | FK/NOT NULL/UNIQUE and supplementary rules |
| Rules | Written as business statements | Attached to entities/relationships and invariants | CHECK/EXCLUDE/trigger/transaction/validator |
| DBMS-dependent | No | Strives to be DBMS-agnostic | Yes, e.g., PostgreSQL, MongoDB |
| Need all columns? | No | Only attributes needing alignment | Columns within deployment scope; full list in data dictionary |
| Review outcome | Shared business language | Shared data structure | Sufficient basis for implementation and testing |

The three levels are **a thinking framework**, not three mandatory files for every project. A **business-oriented logical** diagram can be used in discussions with non-SQL stakeholders, provided non-essential technical details are hidden and notations are explained.

### 3.1. Level of Detail Is Not Just Table Count

A diagram with **five entities and 70 fields** can be harder to read than a diagram with **12 entities showing only names and relationships**.

Level of detail also includes:

- Number of displayed entities.
- Number of attributes per entity.
- Number of relationships and cardinality/multiplicity.
- Whether PK, FK, and alternate keys are shown.
- Whether time, state, and history are represented.
- Whether special business conditions are displayed.
- Whether DDL, physical types, indexes, and constraints are included.
- Whether source/target systems and data ownership are shown.

Therefore, choose the **level of detail based on the question**, rather than fixing a table or column count as a universal standard.

## 4. Start with the Question and the Decision to Be Reached

Before opening a drawing tool, write one sentence:

> "After reading this diagram, group **X** needs to be able to decide/verify **Y**."

Examples:

| Decision to Reach | Audience | Preferred View |
|---|---|---|
| Can an order be paid multiple times? | Product owner, accounting | Conceptual with cardinality and illustrative rules |
| Are orders and payments identified independently? | BA, architect | Logical with business keys and relationships |
| Can a refund attach to one payment or multiple payments? | Refund operations, backend | Logical scoped to refund workflow, with semantic boundaries |
| How do we guarantee amount is non-negative? | Backend, DBA | Physical DDL + tests |
| How should a 3-year reporting query be partitioned? | DBA, data engineer | Physical + query workload and retention |
| Which services does customer data pass through? | Security, DPO, architect | Context/data-flow + sensitivity labels, not a full-table ERD |
| Where does an "order count" KPI come from? | BI, analytics | Fact grain + conformed dimensions + lineage |
| Does a retroactive category fix affect past reports? | Data architect, business | Temporal logical view + timeline |
| Do two systems share the same source ID? | Integration, architect | Boundary/identity mapping view |
| Will a schema migration break old consumers? | Developer, reviewer | Before/after physical + dependency/contract |

**If you don't yet know what question must be answered, you usually shouldn't start with a full physical diagram.**

### 4.1. A Diagram Brief Must Include Time Scope and Target Audience

Compare two different briefs:

- "Describe current orders and payments for sales operations."
- "Verify keys and payment history across multiple refunds, as of date T and according to what the system knew at time K."

The second brief requires temporal and audit logic that the first does not. Using the same simple drawing for both cases easily hides the core distinction.

## 5. Classifying the Audience: Speak Their Language

### 5.1. Business Stakeholders

They typically need to know:

- What objects mean.
- What can or cannot happen.
- What information is needed to operate.
- Which edge cases matter.
- How a change will impact processes.

Use **business names**, short annotations, simple cardinality, and concrete examples. Avoid cramming in GUIDs, byte lengths, indexes, or unnecessary constraint names.

Do not omit a rule just because it is hard to draw. For example:

> An order can receive multiple payments, but the total validly recorded amount must not arbitrarily exceed the amount due.

A 1–N relationship captures the first part; the monetary cap should be noted as a rule for business confirmation.

### 5.2. Analysts and Architects

They need:

- Entity definitions and grain.
- Natural keys, alternate keys, surrogate keys.
- Cardinality and optionality.
- Resolution of many-to-many relationships.
- Normalization/denormalization trade-offs.
- Effective time and relationships that change over time.
- Bounded context scope and ownership.

A logical diagram is usually the central view. Pair it with a **data dictionary** and a list of assumptions/open items.

### 5.3. Developers, DBAs, and Data Engineers

They need:

- Table/column names and types.
- PK, FK, UNIQUE, NOT NULL, CHECK/EXCLUDE.
- State and time-tracking columns.
- Indexes, partitions, and caches/materializations when present.
- Migration, backfill, and rollback strategies.
- Critical queries, concurrency, and performance evidence.

A physical diagram is necessary, though it still does not replace DDL, tests, and runbooks. For large schemas, split diagrams by subsystem and link to specific migrations.

### 5.4. Security/Privacy and Audit

They typically need **data flows**, data classification, copy storage locations, purpose, ownership, retention, deletion triggers, and access controls.

An ERD showing Customer referencing Order **does not tell** which third parties receive customer emails. A different view is needed, potentially adding **PII** labels, owners, and retention; never expose real sensitive values in a diagram.

### 5.5. New Team Members

They need a high-level map first before diving deep. A suitable reading path:

~~~text
Context / domain map
        ↓
Conceptual model
        ↓
Logical model by subsystem
        ↓
Physical tables and data dictionary
        ↓
Migration, tests, ADR
~~~

Sending newcomers straight to a 200-table ERD usually increases onboarding cost without improving understanding.

## 6. Step 1: Define System Boundaries and Diagram Scope

A data diagram is only useful if readers know **what is in scope and out of scope**.

For example, an e-commerce system has:

- **Sales**: placing and managing orders.
- **Payments**: receiving and reconciling payments.
- **Fulfillment**: shipping deliveries.
- **Catalog**: product information.
- **Identity**: accounts and principals.
- **Analytics**: reporting and analytical models.

A meeting about orders and payments does not have to put **every** table from Catalog, Identity, and Analytics into the drawing. However, boundaries must not be misrepresented when an object belongs to another service.

~~~mermaid
flowchart LR
    U["Customer"] --> S["Sales / Order"]
    S --> P["Payments"]
    S --> F["Fulfillment"]
    S --> C["Catalog"]
    S --> A["Analytics events"]
~~~

The diagram above is a **context/dependency flow view**, not yet an ERD. It is useful for identifying data ownership and integration points.

### 6.1. Do Not Confuse Business Relationships with Cross-Service FOREIGN KEYs

Sales may store **customer_id** or **payment_id** from other services. That **does not mean** there is a physical FK between two independent databases.

In a conceptual diagram, you can draw "Order belongs to Customer" to show the business relationship. In the physical view, note:

~~~text
orders.customer_id: logical reference to Identity
No cross-database FOREIGN KEY.
Consistency is controlled via API/event/reconciliation.
~~~

This distinction must be shown with a clear legend/note rather than drawing a line that looks like a real FK and letting reviewers infer incorrectly.

### 6.2. Scope by Use Case

A use case should have a **central entity/aggregate**. For example, "Refunding from a payment" puts PAYMENT/REFUND at the center, including ORDER and CUSTOMER only if they affect the rules.

If a diagram cannot be read at normal size and must be zoomed out until names are illegible, split it into **multiple views within the same namespace** instead of shrinking fonts to fit one page.

## 7. Conceptual Diagrams: Validating Business Language

Set the goal: **"Right entities and right relationships as understood by business stakeholders."**

Example:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : "places"
    ORDER ||--|{ ORDER_LINE : "contains"
    PRODUCT ||--o{ ORDER_LINE : "purchased in"
    ORDER ||--o{ PAYMENT : "paid by"
    PAYMENT ||--o{ REFUND : "may incur"
~~~

At this level, there is no need to list ORDER's 40 columns. Yet the diagram already shows:

- A customer can place multiple orders.
- An order contains at least one product line **in the business state under consideration**.
- A product can appear in multiple order lines.
- An order can have multiple payments.
- A payment can have multiple refunds.

**Lifecycle note:** a newly created order in draft state might not have lines yet, depending on requirements. In that case, use **ORDER ||--o{ ORDER_LINE** and note the rule "an order can only be confirmed when it has at least one line." Do not keep the "at least one" notation across all states if the business allows empty draft orders.

### 7.1. Questions Matter More Than Data Columns

Right on the diagram, include a **Rules to Confirm** section:

1. Can an order be paid by multiple transactions?
2. Can one payment fund multiple different orders?
3. Can a refund be issued partially multiple times?
4. Does an order line lock the price at purchase time or always read the current price?
5. Can customers order as guests, or must every order have an account?

If the answer to item 2 is "yes," a 1–N ORDER–PAYMENT relationship may be insufficient: you will need PaymentAllocation or an N–N relationship with an allocated amount.

### 7.2. Do Not Confuse a Scenario Illustration with a Complete Model

A conceptual diagram **intentionally omits** taxes, discounts, shipping fees, inventory, ledgers, or anti-fraud systems. Add a caption:

> Scope: basic ordering, payment, and refund. Taxes, accounting, and promotions are not yet modeled; relationships are shown for confirmed order states.

Without a caption, readers might assume omitted elements were excluded from the overall design.

## 8. Logical Diagrams: From Concepts to Verifiable Entities and Relationships

Set the goal: **"What does each row represent; how is it identified and linked?"**

For the same example:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--o{ ORDER_LINE : contains
    PRODUCT ||--o{ ORDER_LINE : sold_as
    SALES_ORDER ||--o{ PAYMENT : receives
    PAYMENT ||--o{ REFUND : refunds

    CUSTOMER {
        uuid customer_id PK
        string customer_type
    }
    SALES_ORDER {
        uuid order_id PK
        uuid customer_id FK
        string order_number UK
        string order_status
        datetime placed_at
    }
    ORDER_LINE {
        uuid line_id PK
        uuid order_id FK
        uuid product_id FK
        int line_no
        decimal quantity
        decimal captured_unit_price
    }
    PRODUCT {
        uuid product_id PK
        string sku UK
        string product_name
    }
    PAYMENT {
        uuid payment_id PK
        uuid order_id FK
        string provider_transaction_ref UK
        decimal captured_amount
        string payment_status
    }
    REFUND {
        uuid refund_id PK
        uuid payment_id FK
        decimal refund_amount
        string refund_status
    }
~~~

This is an **illustrative logical representation**, not DDL. For instance, it does not yet show currency conditions, refund states, multiple payment allocations, or guest accounts.

### 8.1. Attach Grain to Each Entity

| Entity | Grain | Logical Primary Key | Key Invariant |
|---|---|---|---|
| CUSTOMER | One identified customer profile | customer_id | Guest/merge mechanism requires policy |
| SALES_ORDER | One sales order | order_id | order_number unique within defined namespace |
| ORDER_LINE | One product line of one order | line_id | line_no unique within order |
| PRODUCT | One commercial SKU/product as defined | product_id | sku unique within catalog scope |
| PAYMENT | One recorded payment | payment_id | provider ref not duplicated per provider |
| REFUND | One refund request/execution tied to payment | refund_id | Does not exceed refundable amount per policy |

The rule "refunds must not exceed successful payments" usually **cannot be expressed with simple PK/FK alone**, as it is a sum across multiple rows filtered by status. It requires a business rule and dedicated transactions/tests.

### 8.2. Determine Optionality Before Setting NOT NULL

A guest order without a valid customer account can be modeled in one of several ways:

- Nullable customer_id with order contact details stored per policy.
- A GuestCustomer entity with its own identifier.
- An identity reference typed as account/guest.

This is a **business and data choice**, not something to decide unilaterally just because an ORM demands a NOT NULL FK.

### 8.3. Minimum and Maximum Cardinality Must Be Justified

A 1–N line says too little if we don't know **whether N can be 0**. There are two kinds of rules:

- **Structural constraint**: an ORDER_LINE must belong to exactly one ORDER.
- **State-dependent constraint**: a draft ORDER may have 0 lines, a confirmed ORDER must have at least 1 line.

The second part should be explicitly documented as a rule, typically enforced during the order confirmation workflow rather than only on the diagram.

## 9. Physical Diagrams: How Data Is Stored and Protected by a Specific DBMS

Set the goal: **"Can it be implemented, migrated, and constraint-reviewed?"**

At the physical level, column names must match the actual schema, and data types and constraints must carry exact semantics. Minimal PostgreSQL example:

~~~sql
CREATE TABLE sales_order (
    order_id uuid PRIMARY KEY,
    tenant_id bigint NOT NULL,
    order_number text NOT NULL,
    order_status text NOT NULL
        CHECK (order_status IN (
            'DRAFT', 'CONFIRMED', 'CANCELLED', 'COMPLETED'
        )),
    placed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT statement_timestamp(),

    UNIQUE (tenant_id, order_number),
    UNIQUE (tenant_id, order_id)
);

CREATE TABLE order_line (
    line_id uuid PRIMARY KEY,
    tenant_id bigint NOT NULL,
    order_id uuid NOT NULL,
    line_no integer NOT NULL CHECK (line_no > 0),
    product_id uuid NOT NULL,
    quantity numeric(18, 3) NOT NULL CHECK (quantity > 0),
    captured_unit_price numeric(18, 2) NOT NULL
        CHECK (captured_unit_price >= 0),
    currency_code char(3) NOT NULL,

    FOREIGN KEY (tenant_id, order_id)
        REFERENCES sales_order(tenant_id, order_id),

    UNIQUE (tenant_id, order_id, line_no)
);

CREATE INDEX ix_sales_order_tenant_created
    ON sales_order (tenant_id, created_at DESC);

CREATE INDEX ix_order_line_by_order
    ON order_line (tenant_id, order_id);
~~~

This is an **illustrative DDL snippet** focused on ORDER and ORDER_LINE, not yet a complete schema for payments/refunds. Dimensions such as customer_id, product policies, taxes, fees, statuses, and history need further design based on business decisions.

### 9.1. What the Physical View Adds

- **uuid** for technical PK, avoiding inferring meaning from numeric sequence.
- **tenant_id** and **UNIQUE(tenant_id, order_number)** for namespace-scoped display codes.
- **CHECK** for status, quantity, and price.
- **FK (tenant_id, order_id)** prevents a line from another tenant from pointing to the wrong tenant's order via a composite key.
- **INDEX** supports reading recent orders and lines within an order.
- **timestamptz** stores absolute instants, separating created_at from placed_at.

### 9.2. DDL Still Does Not Replace Metrics and Transaction Rules

Even with CHECK(quantity > 0), the system still needs rules:

- Can quantity be edited after order confirmation?
- Can locked prices change when catalog prices change?
- Can an order with 0 lines be confirmed?
- Which payments count as completed?
- Can multiple refunds sum to more than the successful payment?
- Which changes must emit audit logs/events?

A physical diagram with every column and constraint **still does not replace workflows or cross-table conditions**. Link it to the business-rule catalog and test cases.

## 10. Same Reality, Three Diagram Levels Must Be Consistent

An important principle: **the three levels must not contradict each other**.

Example rule:

> "An order has many lines; each line belongs to exactly one order."

Three layers express it differently:

| Layer | Representation |
|---|---|
| Conceptual | "Order contains order lines"; cardinality 1–N |
| Logical | ORDER_LINE has mandatory order_id; logical FK to SALES_ORDER |
| Physical | order_line.order_id NOT NULL + FOREIGN KEY |
| Verification | INSERT line with non-existent order_id must be rejected |

If conceptual shows "one order has one payment" while logical allows ORDER 1–N PAYMENT, clarify whether this is an approved rule change or a **documentation error**. Do not silently let two diagrams diverge and leave readers guessing.

### 10.1. Mapping Between Levels

A minimal mapping:

~~~text
Business concept: Order
  Logical entity: SALES_ORDER
    Physical table: sales_order
      PK: order_id
      Business key: (tenant_id, order_number)

Business concept: Order line
  Logical entity: ORDER_LINE
    Physical table: order_line
      PK: line_id
      FK: (tenant_id, order_id)
      Alternate key: (tenant_id, order_id, line_no)
~~~

When physical names differ from business names, **mapping** is mandatory to prevent misunderstandings. Just because the schema names a table sales_order while business calls it "purchase order" does not mean there are two different entities.

### 10.2. Conceptual Does Not Need 1-to-1 Parity with Tables

One "Payment" concept may require multiple tables: **payment_attempt**, **payment_transaction**, **payment_allocation**, and **payment_method_snapshot**. The difference reflects model decomposition, not necessarily a wrong conceptual diagram.

Conversely, a denormalized dimension table may hold attributes from multiple logical entities to accelerate analytics. Explicitly document **grain and mapping** rather than assuming one box on a diagram always equals one physical table.

## 11. Cardinality and Optionality: What Information Should Not Be Hidden?

In ERDs, cardinality often carries greater business impact than dozens of rarely used attributes.

Common Crow's Foot notations can represent:

| Conceptual Notation | Meaning at One End of a Relationship |
|---|---|
| **0..1** | Zero or exactly one |
| **1** | Mandatory, exactly one |
| **0..N** | Zero or many |
| **1..N** | Mandatory, at least one |
| **N..M** | Many-to-many relationship, requiring associative entity analysis |

Examples:

- An **ORDER_LINE** must belong to one **ORDER**.
- An **ORDER** in draft state may not yet have a **PAYMENT**.
- A **PAYMENT** may have multiple **REFUND**s.
- A **PRODUCT** may be assigned to multiple **CATEGORY** values if the business permits.

Do not write "1..N" simply because current sample data happens to have at least one child; it must be a **business constraint**, not a temporary observation of sample data.

### 11.1. Many-to-Many Must Be Explained

Suppose a product can belong to multiple categories:

~~~mermaid
erDiagram
    PRODUCT ||--o{ PRODUCT_CATEGORY : assigned_to
    CATEGORY ||--o{ PRODUCT_CATEGORY : contains
    PRODUCT {
        uuid product_id PK
        string sku
    }
    CATEGORY {
        uuid category_id PK
        string category_name
    }
    PRODUCT_CATEGORY {
        uuid product_id FK
        uuid category_id FK
        date valid_from
        date valid_to
        boolean is_primary
    }
~~~

A conceptual view may only draw PRODUCT N–N CATEGORY. A logical view should expose **PRODUCT_CATEGORY** when discussing:

- Does the relationship have effective dates?
- Can a product have at most one primary category on a given date?
- Can a category be deleted while referenced?

A physical view needs to specify the corresponding PK/FK, UNIQUE/EXCLUDE, or transaction rules.

### 11.2. Hiding Associative Entities Can Distort Meaning

If **PAYMENT_ALLOCATION** stores the amount allocated from a payment to an order, omitting it from a diagram reviewing payment rules may lead readers to think a payment pays for only one order.

Only hide an associative entity when **it does not affect the audience's question**. When the audience is reviewing monetary allocation, it is the central entity.

## 12. Choosing Which Attributes to Put on the Drawing

A Customer entity can have hundreds of attributes, but not every meeting needs to see them.

### 12.1. Minimal Attributes for Conceptual

Usually only needed:

- Concept name.
- A 1–2 line description.
- Business code if identification is a central debate.
- Critical rules/cardinality.

Example:

~~~text
Customer
- Can have multiple orders.
- Guest customers require a separate policy.
~~~

### 12.2. Attributes That Should Appear in Logical

Prioritize:

- Primary keys and business keys.
- Logical FKs or relationship identifiers.
- Attributes determining grain.
- State/type attributes if they alter relationships.
- Effective timestamps.
- Fields whose definitions need alignment.
- Alternate keys and unique business rules.

It is not necessary to display every ETL metadata field (loaded_at, batch_id) when it does not affect logical modeling decisions.

### 12.3. Attributes That Should Appear in Physical

Within implementation review scope:

- Column name, database type, nullability.
- PK, FK, UNIQUE, and references.
- CHECK/EXCLUDE or related constraint names.
- Indexes, partition keys, generated columns if affecting workload.
- Default values, collation, precision, timezone.
- Migration/backfill notes when breaking changes exist.

**A physical diagram does not need every secondary index and every column comment if readers can consult a reliable data dictionary or DDL.** The goal remains readability and accurate review.

### 12.4. Attribute Filtering Rule

An attribute should appear when it serves at least one purpose:

1. Distinguishes two business interpretations.
2. Expresses identity or a constraint.
3. Represents a key dimension/time aspect of the use case.
4. Impacts migration, quality, or performance.
5. Needs confirmation from the reader.

If it meets none of these, put it in the data dictionary rather than forcing every diagram to display it.

## 13. Beyond Level: Also Choose the Right Diagram Type

An ERD cannot answer every question about data.

| Question | Appropriate View |
|---|---|
| What objects exist in the system? | Conceptual data model |
| Which tables/documents/nodes connect? | Logical ERD/document/graph model |
| What keys, indexes, and columns does the DB store? | Physical schema/DDL view |
| How does data move between services? | Context/data-flow diagram |
| Which fields travel from source to KPI? | Lineage diagram/metric lineage |
| Through which steps does a record change state? | State machine/sequence diagram |
| When is an attribute effective? | Timeline/temporal model |
| Who can access which data type? | Data classification/authorization matrix |
| How does a migration change the schema? | Before/after physical + dependency map |
| How do entities in a graph have multi-hop paths? | Graph domain view |
| How is an event received and its projection updated? | Event flow/projection diagram |

### 13.1. When to Add a Sequence Diagram?

If the question is "when two workers confirm an order simultaneously, who wins the write?", an ERD only shows static structure. A **sequence diagram** or transaction description is needed to explain:

- Locks or version checks.
- Transaction boundaries.
- Retries.
- Outbox publishing.
- Consumer idempotency.

Do not try to cram all concurrency handling onto ERD arrows; they express a different category of information.

### 13.2. When to Add a Timeline?

If a problem involves **valid_from/valid_to**, two SCD2 versions, or a retroactive correction, a timeline is often easier to explain than a list of datetime columns:

~~~text
Product P01:
[01/01, 01/08)   FOOD
[01/08, +∞)      GIFT

Sold on 15/07 → FOOD
Sold on 15/08 → GIFT
~~~

An ERD shows there is a PRODUCT_VERSION table, whereas a timeline shows exactly **which boundaries are inclusive**, preventing misunderstandings on crossover dates.

## 14. What Does a Data Dictionary Add Where Diagrams Lack Space?

Good model documentation pairs diagrams with a **data dictionary** attached to each entity/attribute.

Abbreviated example:

| Entity/field | Definition | Logical type | Nullable | Rules | Source |
|---|---|---|---|---|---|
| sales_order.order_id | Global identifier of the order | UUID | No | Unique in authoritative DB | Sales |
| sales_order.order_number | Customer-facing code | String | No | Unique per tenant | Sales |
| sales_order.placed_at | When order placement was confirmed | Instant | Yes while draft | Must not default to created_at | Sales |
| order_line.line_no | Line position within an order | Positive integer | No | Unique per order | Sales |
| order_line.captured_unit_price | Unit price locked at sale time | Money | No | Does not auto-read current catalog price | Sales/Catalog |
| order_line.quantity | Line quantity | Decimal | No | > 0; unit per SKU | Sales |
| order_line.currency_code | Currency of captured price | ISO code/string | No | Must be consistent with amount | Sales |

Beyond definitions, a data dictionary can record:

- Owner and approver.
- API/source name.
- Unit/precision/format.
- Valid values and defaults.
- Cardinality and effective time.
- PII/sensitivity classification.
- Retention and masking.
- Lineage/quality checks.
- Deprecated/replaced-by and migration milestones.

**Do not put all of this information inside ERD boxes.** It belongs somewhere searchable, versionable, and independently reviewable.

### 14.1. Assign Stable IDs to Entities and Rules

Example:

~~~text
ENT-SALES-ORDER      Order
ENT-ORDER-LINE       Order line
REL-ORDER-HAS-LINE   An order has many lines
BR-ORDER-001         A line belongs to only one order
BR-ORDER-002         A CONFIRMED order must have at least one line
BR-ORDER-003         line_no is unique within an order
~~~

The diagram links to **BR-ORDER-003**, while the DDL has UNIQUE(tenant_id, order_id, line_no). When a rule changes, reviewers can trace the impact across diagrams, migrations, and tests.

## 15. Which Business Rules Need Prose Instead of Symbols?

Not every constraint can be described using cardinality.

Example:

> "The total successful refunds for a payment must not exceed the actual refundable amount."

An ERD showing PAYMENT 1–N REFUND cannot express a sum cap. CHECK(refund_amount >= 0) on a single row also does not guard the sum across rows.

A rule should state:

~~~text
BR-REFUND-004

Scope:
- Payment is in CAPTURED/SETTLED status as defined.
- Count only SUCCESS refunds under the applicable policy.

Invariant:
SUM(successful_refund_amount) <= refundable_payment_amount

Enforcement:
- Transaction with lock/version or reservation.
- Prevent two concurrent refunds from exceeding the limit.

Verification:
- Two concurrent refunds do not exceed the remaining balance.
- Retrying the same refund request does not create a new refund.
~~~

The logical diagram can annotate **rule BR-REFUND-004** next to PAYMENT–REFUND. Algorithmic details reside in the rules document and tests.

### 15.1. A Formula Does Not Equal a Database-Enforced Constraint

A document stating **amount = quantity × unit_price** does not prove the DDL has a generated column or CHECK constraint. Reviewers need to know:

- The confirmed **business invariant**.
- Whether the **enforcement location** is the DB, service, ETL, or a combination.
- Where the concrete **test evidence** lives.
- Whether any write path bypasses enforcement.

Each diagram level only needs to show its appropriate part, but the overall documentation set must connect these pieces.

## 16. Time-Sensitive Topics Need Dedicated Views

When a system maintains history, a connector line can be **true today yet wrong in the past**.

For instance, an employee transfers from department A to B on 01/08. A model having only:

~~~text
EMPLOYEE.department_id
~~~

will return current department B for all historical events. If reporting requires "which department did the employee belong to when the transaction occurred," you need:

~~~text
EMPLOYEE_DEPARTMENT_HISTORY
(employee_id, department_id, valid_from, valid_to)
~~~

In the conceptual diagram, business stakeholders only need to see:

> An employee can change departments over time; historical reports evaluate the relationship as of the transaction date.

In the logical diagram, include the history entity and cardinality. In the physical diagram, include time types, [from,to), keys, and anti-overlap constraints.

### 16.1. Timeline with Half-Open Intervals

~~~text
employee E1 → department A: [2026-01-01, 2026-08-01)
employee E1 → department B: [2026-08-01, +∞)
~~~

Date 01/08 belongs solely to B. Do not draw two arrows E1 → A and E1 → B without timestamps, leading viewers to think the employee belongs to two departments simultaneously.

### 16.2. When Is a Bitemporal View Needed?

If a change can be corrected **retroactively**, requirements may involve two questions:

- Which state was **in business effect** on date B?
- What **did the system know** at point in time K?

The logical diagram needs both **valid time** and **known/system time** axes if both questions are mandatory. Business readers can grasp this via a 2D table/timeline; DBAs need the range constraint model and revision write strategy.

Do not put bitemporal modeling into every diagram merely because the schema has updated_at. **updated_at is not by itself known-period history.**

## 17. Documentation for Relational, Document, Graph, and Analytical Models

The DATABASE_DATA_MODELING module is not just about relational tables. The framework of **choosing detail level by audience** applies equally across different data organizations.

### 17.1. Relational Model

- Conceptual: Customer – Order – Product.
- Logical: ORDER_LINE resolves Order–Product, defining PK/FK and optionality.
- Physical: tables, columns, types, UNIQUE, CHECK, FOREIGN KEY, indexes, and partitions.

### 17.2. Document Model

An order document may contain nested items:

~~~json
{
  "orderId": "O-100",
  "status": "CONFIRMED",
  "items": [
    {
      "lineNo": 1,
      "sku": "P01",
      "quantity": 2,
      "capturedUnitPrice": 100000
    }
  ]
}
~~~

This is merely an **illustrative shape**, not a production contract for currency/numeric types and write permissions.

- Conceptual: Order has OrderLines.
- Logical: items can be embedded because they share the aggregate/order lifecycle; explain why.
- Physical: JSON schema/validator, document size limits, indexes on orderId/status, update and versioning strategy.

If payments are processed independently with many events/partial captures, do not embed the entire payment history inside the order by default just because the document engine allows it. Decide based on **boundaries, workload, and consistency**.

### 17.3. Graph Model

A graph with Customer, Product, Category, and PURCHASED/INTERESTED_IN/BELONGS_TO relationships:

- Conceptual: node types and relationship types.
- Logical: identity keys, edge direction, cardinality where applicable, edge properties, and effective dates.
- Physical: labels/types, constraints/indexes, query patterns, and which data is updated concurrently.

If a product belongs to multiple categories, it cannot be simplified to a single-valued "product.category" in a diagram used to discuss multi-category logic.

### 17.4. Analytical/Star Schema

- Conceptual: revenue by date, product, and store.
- Logical: **fact grain**, measures, dimensions, conformed dimensions, and additivity.
- Physical: fact_sales_line, dim_date, dim_product, surrogate keys, SCD, partitioning, clustering, and materialized aggregates.

A dashboard saying "revenue" whose diagram fails to specify **grain** and **net vs gross vs after returns** formulas can lead to miscalculations no matter how pretty the drawing is.

### 17.5. Key Differences

A data model diagram is not required to use **Crow's Foot** if the technology demands a different notation. However, the legend must be clear enough for readers to know:

- What nodes/boxes represent.
- What connector lines/edges mean.
- Whether relationships restrict cardinality.
- Which data is embedded versus merely referenced.
- Which parts belong to the logical model versus implementation details.

## 18. Data Flow and Privacy Views: Showing Risk Without Exposing Secrets

Diagrams can be used to review **data protection**, provided the right kind of information is selected.

A useful privacy-aware view:

~~~mermaid
flowchart LR
    C["Customer UI"] --> S["Order Service"]
    S --> DB["Order DB / tenant-scoped"]
    S --> P["Payment Provider"]
    S --> E["Event Stream"]
    E --> A["Analytics Warehouse"]
~~~

Annotate externally:

- Which fields contain identifying or sensitive data.
- Who is the controller/processor or business owner.
- Purpose of data transmission.
- Whether data is transferred to external partners.
- Level of minimization, masking, encryption, and retention.
- Access permissions by tenant and role.
- Whether any other snapshots/backups/caches hold copies.

### 18.1. Do Not Put Real Data into Diagram Examples

There is no need to include real names, phone numbers, account numbers, tokens, or emails to explain Customer–Order relationships. Use synthetic values and keep secrets out of artifacts.

### 18.2. Do Not Treat a PII Label Alone as a Security Control

A **PII** label on a diagram helps reviewers spot risk locations, but it does not implement access control or retention. Link to policies, DDL/API controls, audit systems, and tests.

The right diagram for privacy teams must **highlight where controls are needed**, not claim the system is secure simply because labels exist.

## 19. Legends, Color, and Grouping Conventions

A hard-to-read diagram is sometimes caused by a missing **legend**, not wrong data.

Convention example:

| Visual Representation | Agreed Meaning |
|---|---|
| Shape/box | Entity or table depending on level |
| Solid line | Defined data relationship |
| Dashed line | Logical reference across boundaries, no physical FK |
| Crow's Foot notation | Cardinality/optionality |
| [External] label | Data owned by another system |
| [SCD2] label | Entity with effective-dated versions |
| [PII] label | Contains data requiring classification/protection |
| [Derived] label | Projection/materialized/aggregate, not source of truth |
| Note BR-xxx | Business rule beyond line expressiveness |

Color should be **supplementary**, never the sole channel of information. Readers printing in black and white or using accessibility tools still need to distinguish elements via text, symbols, and legends.

### 19.1. Layout Should Reflect Reading Flow

- Place the central entity near the middle of the diagram.
- Group by bounded context or subject area.
- Minimize unnecessary crossing lines.
- Use consistent names large enough to read.
- Include title, purpose, scope, date/version, and link to dictionary.
- If the drawing overflows the page, split by use case rather than shrinking all fonts.

### 19.2. Avoid Ambiguous Notation

A plain line "CUSTOMER — ORDER" without labels/cardinality is easily misinterpreted as:

- How many orders can a customer have?
- Can an order have no customer?
- Is Customer an account or a real person?
- Is the relationship an in-DB FK or merely a business association?

At the conceptual level, it can be simplified yet still needs at least a "places" label and an optionality note. At the logical level, cardinality or an equivalent rule is required.

## 20. How to Build a "Top-Down Overview to Detail" Diagram Set

An accessible documentation structure:

~~~text
/Architecture/Orders
  00-context
    - boundary Sales / Payments / Catalog

  01-conceptual
    - order-payment-refund overview
    - key business rules

  02-logical
    - order-and-lines
    - payment-and-refunds
    - temporal-relationships

  03-physical
    - PostgreSQL order storage
    - payment constraints and indexes
    - migration before/after

  04-supporting
    - data dictionary
    - business rules
    - decision log
    - query examples
    - tests / lineage / privacy
~~~

This is an **illustrative documentation set structure**, not a requirement to create these files in the current task.

### 20.1. Every Diagram Needs Minimal Metadata

A good header:

~~~yaml
diagram_id: DM-ORD-LOGICAL-01
title: "Orders and order lines"
level: logical
audience: ["BA", "Backend", "Data Architect"]
purpose: "Confirm grain, keys, and cardinality of orders"
scope: "Sales bounded context, excluding payment settlement"
model_version: "2.3"
status: "Reviewed"
source_of_truth: "Model repository / revision tag"
reviewed_at: "2026-11-20"
owner: "Sales Domain Team"
~~~

This metadata block is an **example of documentation content**, not metadata to add to the lesson's YAML. A documentation management system may store metadata in many formats.

### 20.2. Link Rather Than Duplicate Every Detail

On the conceptual view, entity Order links to logical entity SALES_ORDER; logical links to physical table and dictionary; physical links to migrations and tests. If the same rule is rewritten in 7 places, it will easily drift upon change.

Use **unique rule IDs** and tailor presentations by audience while maintaining one shared source of meaning.

## 21. Diagram Collaboration and Review Process

### 21.1. Before the Workshop

1. Write down the decision question and approvers.
2. Pick a business scenario and a few data examples.
3. Sketch scope/boundaries.
4. Select the appropriate level, removing details that don't serve the question.
5. Mark assumptions and uncertainties.
6. Check the diagram against the existing dictionary/version.

### 21.2. During the Workshop

Ask business stakeholders:

- Are any entities misnamed or misunderstood?
- Does this one-to-many case have exceptions?
- Does any state change optionality?
- When an object is cancelled/deleted, what happens to related records?
- Are there historical periods where relationships changed?
- Are there two different interpretations of the same term?

Ask engineering:

- Which keys are truly unique and within what scope?
- Which rules are enforced in the database versus in the service?
- If two transactions run concurrently, can any invalid state slip through?
- Does migration/backfill impact legacy data?
- Which queries will hit this structure most frequently?

### 21.3. After the Workshop

- Record decisions and rejected alternatives.
- Update diagrams at the right level.
- Document mappings to rules, schema, and migrations.
- Assign owners and review status.
- Confirm open questions.
- Save version/commit to compare changes.

**"Drawn" does not mean "agreed upon or deployed."** Document status should distinguish Draft, Reviewed, Approved, and Implemented/Deployed when workflows require it.

## 22. Document Versioning and Drift from the Actual Schema

A diagram captured last month may not reflect a newly deployed schema. A process is needed to detect and resolve **documentation drift**.

### 22.1. Two Sources of Change

- **Design-first:** the team agrees on the model, then creates migrations.
- **Schema-first:** the schema changes first, then tools extract metadata to generate physical views.

Both have their place. However, **reverse-engineering the schema alone is insufficient** to understand business rationale, bounded contexts, or service-level constraints. Conversely, a design diagram never compared against the production database can turn into wishful documentation rather than reflecting the real system.

### 22.2. Linking Diagrams to Migrations

Example change:

> Starting in version 2.3, allow multiple payments for one order.

Verify:

1. Conceptual view shifts from 1–1 assumption to 1–N.
2. Logical view confirms PAYMENT has its own identity and FK/order relationship.
3. Physical view drops UNIQUE(payment.order_id) if it previously banned multiple payments, while keeping necessary FKs and indexes.
4. Migration handles backfill/write-path switching and rollback verification.
5. Business rules on valid payment totals are updated.
6. Tests verify creating two payments for the same order succeeds; retries do not create duplicate payments.
7. Consumers/reports no longer assume an order has only one payment.

A documentation change is complete when **all views and rules match the approved state**, not just when a line on a drawing is edited.

### 22.3. Semantic Diff

PNG image diff tools usually cannot distinguish moving a box from changing cardinality. Good reviews should state:

~~~text
Model change:
- SALES_ORDER -> PAYMENT: 0..1 changed to 0..N.
- PAYMENT has payment_id as its own identity.
- Added business rule on total captured_amount.
- Impact: API, schema, reporting, reconciliation.
~~~

Text/Mermaid-based models or data modeling tools with semantic diff can be used, though a reviewer who understands the business is still essential.

## 23. Common Mistakes When Choosing Detail Levels

| Mistake | Consequence | Fix |
|---|---|---|
| One 200-table ERD for all readers | Readers lose the core question | Split views by audience/use case |
| Business diagram showing all indexes/types | Obscures entities and rules | Move details to physical view |
| Physical view with only table names | Cannot review constraints/migrations | Add PK/FK/types and link DDL |
| Missing grain on entity/fact | Double counting, wrong key choices | Add a grain statement in the dictionary |
| Drawing cross-DB FKs like real FKs | Readers assume strong referential integrity | Distinguish logical reference from physical FK |
| Hiding bridge tables in M–N discussions | Wrong assumptions on amounts/counts | Show associative entity and allocation rules |
| Writing 1–N without clarifying 0 or 1 | Wrong NOT NULL/workflow | State optionality and state-specific rules |
| Missing timestamp semantics | Wrong historical reports | Add temporal view + interval definition |
| Repeating rule definitions across diagrams | Documentation drift | Shared rule ID, link to dictionary |
| Relying solely on color for meaning | Hard to read, poor accessibility | Text/legend/symbols alongside color |
| Mixing data models and processing sequences | Blurs static/dynamic boundaries | Use separate sequence/state diagrams |
| Using old schema screenshots as source of truth | Reviewers approve stale state | Attach version/migration and compare schemas |
| Leaving open decisions unmarked | Assumptions become "approved" | Mark open questions and owners |
| Copying real data onto diagrams | Sensitive data leak | Use synthetic examples and classify data |
| Only reverse-engineering DDL | Cannot capture business meaning | Add conceptual/logical + ADR |
| Adding aggregate tables without grain | KPI sums incorrectly across dimensions | Specify fact grain/measure contract |

## 24. Quick Level-Selection Pattern by Decision Risk

A self-check:

### Step A — Who Will Act on the Diagram?

- Business stakeholders **confirming concepts** → conceptual.
- Design team **finalizing identity, structure, constraints** → logical.
- Engineering team **implementing, tuning performance, migrating** → physical.
- Security team **checking data destinations and access** → data-flow/privacy view.
- BI team **verifying metrics and lineage** → fact/dimension + lineage view.

### Step B — What Wrong Decision Might Readers Make If Information Is Hidden?

For example, if PAYMENT_ALLOCATION is hidden, they might allow invalid payment totals. So show it even if the diagram looks denser.

If index names are hidden, the product owner can still confirm "one order, many payments," so they can be hidden.

### Step C — Is a Supplementary Diagram Needed?

- Has history → timeline/temporal view.
- Has concurrent workflows → sequence/state view.
- Has multiple services → context/data-flow view.
- Has migration → before/after physical view.
- Has multiple data models → dedicated notation for relational/document/graph.
- Has KPIs → metric/grain/lineage view.

### Step D — Is Sufficient Supporting Evidence Linked?

A good diagram needs links to definitions, rules, tests, and versions so readers can verify it. If a diagram looks pretty but cannot trace back to design decisions, it is not complete model documentation.

## 25. Practice Exercise: Designing Three Diagrams for Delivery and Returns

A retail chain wants to build data structures for:

> "Customers create multi-line orders. One order can be delivered in multiple shipments, and each shipment can have multiple delivery attempts. Customers can return partial quantities per line; refunds can be split across multiple payments. The business team needs to confirm the process; the architecture team needs to confirm relationships; the database team needs PostgreSQL migrations."

Additional requirements:

- An order in DRAFT status may have no lines yet.
- When CONFIRMED, an order must have at least one line.
- The same order line can be split across multiple shipments.
- One shipment can contain multiple order lines, each with its own quantity.
- One payment may cover only part of the order total.
- Refunds may only be issued within the refundable balance.
- Upon return, the original order line and actual returned quantity must be preserved.
- Report users want to know who/what was effective on the delivery date.
- Customer data must be classified and protected; do not put real information on drawings.

### 25.1. Part A — Conceptual for the Product Owner

Draw at most one view focused on:

~~~text
Customer
Order
Order Line
Shipment
Payment
Return
Refund
~~~

Name relationships in business language, indicating those that can be many-to-many or repeated. Write at least five confirmation questions, such as "Can a shipment contain lines from multiple orders?" and "Can a refund belong to multiple payments?".

**Do not** draw UUIDs, decimal types, or index names here.

### 25.2. Part B — Logical for Architects

Determine:

- Grain and business keys for Order, Line, Shipment, ShipmentLine, Payment, Refund, ReturnLine.
- Whether **ORDER_LINE ↔ SHIPMENT** needs **SHIPMENT_LINE** holding quantity.
- Whether **PAYMENT ↔ ORDER** needs PAYMENT_ALLOCATION if a payment applies to multiple orders.
- Which statuses a shipment has and whether redeliveries are modeled via DeliveryAttempt or versions.
- Whether a return must link to the original line and optionally link to a shipment.
- Cardinality/optionality for DRAFT and CONFIRMED.
- Cross-table rules on total shipped quantity, returned quantity, and refunded money.
- Which timestamps and historical links need effective-dating.

Include a rule ID table and at least two illustrative timelines.

### 25.3. Part C — Physical for Backend/DBA

Provide a PostgreSQL design with:

- PKs and FKs, including composite tenant keys if data is multi-tenant.
- UNIQUE constraints for source requests and line numbers.
- CHECK constraints for quantity/amount.
- Indexes serving queries for shipments by order and payments/refunds by status.
- Transaction rules preventing two concurrent refunds from exceeding the remaining balance.
- A migration strategy from an old schema allowing only one shipment per order.
- Tests for late-arriving data and retroactively corrected statuses.
- Permissions and retention for customer data.

Do not assume every rule can be expressed as a single-row CHECK. For multi-row aggregate rules, specify locking, idempotency, and testing approaches.

### 25.4. Part D — Distributing the Documentation Set

Create a table:

| Recipient | Primary Diagram | Supporting Documents |
|---|---|---|
| Product owner | Conceptual | Business-rule questions |
| BA/architect | Logical | Data dictionary, temporal rules |
| Backend/DBA | Physical | DDL, migration, index/query tests |
| Analytics | Fact/lineage view | Metric contract and grain |
| Security/privacy | Data-flow view | PII classification, retention |
| QA | Logical + physical | Business invariants, test matrix |

**Passing criteria:** a business conclusion is expressed consistently across views; every diagram is sufficient for its target group to make decisions; hidden details do not distort assumptions; data has owners, versions, and verification evidence.

## 26. Approval Checklist and Conclusion

Before publishing a data model diagram, verify:

- **Audience:** who is the actual reader? Do they understand the notation used?
- **Purpose:** is the question/decision clearly written?
- **Level:** is conceptual, logical, or physical appropriate, or is another data-flow/timeline view needed?
- **Scope:** are bounded contexts and excluded cases clearly stated?
- **Grain:** what kind of single record does each entity/fact represent?
- **Semantics:** are business terms consistently defined and easy to understand?
- **Identity:** are PK, business key, surrogate key, and namespace placed at the right layer?
- **Cardinality:** are 0..1, 1, 0..N, 1..N, and N–N accurately interpreted?
- **Optionality:** are state-dependent constraints documented separately if FK cannot express them?
- **Relationships:** are cross-DB logical references kept distinct from enforced physical FKs?
- **Business rules:** do total caps, time rules, and concurrency rules have rule IDs/links attached?
- **Temporal:** are valid time, known time, timezone, and [from,to) shown when relevant?
- **Physical:** are DB types, constraints, indexes, partitions, and migrations traceable to schema/tests?
- **Privacy:** is real data avoided, and are classification/retention and boundaries at the right level?
- **Consistency:** are there no cardinality or semantic contradictions across conceptual/logical/physical?
- **Readability:** does the drawing have a clear title, legend, readable fonts, and non-color-only cues?
- **Traceability:** can you trace from rule to entity, DDL, migration, and test?
- **Version:** are owner, model version, review status, and update timestamp recorded?
- **Change impact:** could model changes break APIs, consumers, reports, or historical data?
- **Verification:** has it been validated against real examples, edge-case data, and appropriate reviewers?

**Core principle:** a diagram is not a decorative copy of a database, but a **tool for communicating a modeling decision**. Business stakeholders need to see entities and rules; analysts need to see grain, keys, and relationships; implementation teams need to see tables, constraints, and operations. Choosing the right detail level keeps documentation **readable**, **verifiably grounded**, and **consistently evolvable** as requirements and schemas change.
