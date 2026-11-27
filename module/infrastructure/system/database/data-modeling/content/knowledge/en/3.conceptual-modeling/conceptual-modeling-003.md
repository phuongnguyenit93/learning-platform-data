# Defining Model Scope and Eliminating Premature Implementation Details

In the **DATABASE_DATA_MODELING** module, the goal is to build the skill of turning business requirements into clear data models—from entities, relationships, and constraints to deployable schemas—while knowing how to compare relational, document, graph, and analytical data organizations. At the conceptual modeling stage, the first decision is determining **which part of the business world the model describes, who it serves, and which questions it answers**.

If the scope is unclear, the model easily bloats into a replica of the entire enterprise or omits data needed for a workflow. If you jump too early into tables, columns, SQL types, indexes, or JSON structures, the design team risks optimizing one representation before properly understanding the problem. This lesson explains how to establish business boundaries, choose the right level of detail, and keep implementation decisions in their proper phase.

## 1. What Is Model Scope?

Data model scope is a deliberate definition of:

- **Business domain:** the area or capability being described, such as order management, appointment scheduling, or learner management.
- **Intended use:** the decisions, workflows, queries, reports, or data exchanges the model must support.
- **Objects and events:** the concepts that need to be described because they matter for that purpose.
- **Responsibility boundaries:** which data is managed within this scope and which data belongs to another system or department.
- **Level of detail:** whether the model describes a customer, an order, a line item, a payment attempt, or a finer-grained event.
- **Time and lifecycle boundaries:** current data, historical data, transient data, and data retained for auditing or reconciliation.

Scope is not simply a list of anticipated tables. It is an agreement about the meaning and ownership of the model. Two teams may both refer to "customer" yet need different slices of data: the order team needs an identifier and delivery details as of order placement; the customer care team may need contact history and preferences. Do not assume both needs must share the exact same structure or own all the same data.

### Distinguishing Three Kinds of Boundaries

| Boundary Type | Question to Answer | Example |
|---|---|---|
| Business boundary | Which process or capability is being described? | Managing orders from creation to confirmation or cancellation |
| Data boundary | Which concepts are managed in this model, and which are only referenced? | Orders are in scope; canonical customer profiles belong to the customer system |
| Deployment boundary | Which service, database, or team will store and process the data? | An order service and a separate payment system |

These three boundaries are related, yet they do not have to coincide. A conceptual model can describe relationships across multiple systems without yet deciding whether they share a database or run as separate services. Do not infer data boundaries solely from an org chart or current deployment diagram.

## 2. Start from Goals and Business Questions

Before listing entities, write a brief scope statement. This statement should specify the audience, purpose, and start/end points of the process.

Example:

> The order management model describes the creation, confirmation, tracking, and cancellation of customer orders. The model must support inspecting order contents as of placement time, checking payment outcomes, and providing information needed for fulfillment/shipping. Customer profiles, product catalogs, payment processing, and shipping dispatch belong to other business scopes.

After the scope statement, list the questions the model must answer:

- Who can create an order, and when is an order created?
- Which line items make up an order?
- Are product prices and names interpreted as of placement time or current catalog data?
- Can an order have multiple payments or payment attempts?
- What happens when payment fails, an order is cancelled, or delivery fails?
- How do staff inspect order history to resolve complaints?

Questions test the practical scope. If a concept does not help answer a question, enforce a rule, or describe a required interface, it may not need to be in the model yet. Conversely, if an important question has no supporting concept or data, the scope is missing something.

Do not rely solely on nouns in requirements documents. The word "order" can encompass many distinct concepts: order, line item, payment attempt, packing slip, delivery attempt, refund, and status history. Examine accompanying verbs and events: create, add line, confirm, pay, cancel, refund, hand over, deliver successfully.

## 3. Drawing Boundaries with Systems and Stakeholders

A context diagram shows the scope under consideration and the actors or systems exchanging data with it. This diagram does not need to depict technologies or protocols; the goal is to clarify what information crosses the boundary.

Example for the order management scope:

~~~mermaid
flowchart LR
    Customer[Customer]
    subgraph OrderScope["Scope: Order Management"]
        Order[Order]
        Lines[Line Items]
        Snapshot[Product & Delivery Snapshot at Placement]
        Order --> Lines
        Order --> Snapshot
    end
    Payment[Payment System]
    Shipping[Shipping System]
    Customer -->|Place or cancel request| Order
    Order -->|Charge request| Payment
    Payment -->|Result and transaction ID| Order
    Order -->|Shipment details| Shipping
    Shipping -->|Delivery status| Order
~~~

The diagram shows that the order scope needs to know payment results and delivery status. It does not need to describe how the payment system validates cards, connects to banks, or updates ledgers; nor does it need to describe route optimization algorithms. Those belong to other scopes.

For each exchange path, document:

1. Who is the sender and who is the receiver?
2. Which event triggers the exchange?
3. What minimal data must cross the boundary?
4. Which side owns the meaning and correctness of the data?
5. How does the business handle late, duplicate, or missing data?

At the conceptual stage, answers can remain at the business level. For example, "the payment system sends the outcome and transaction ID" is enough to define required information; there is no need yet to choose webhooks, queues, REST, or JSON formats.

### Distinguishing Owned Data from Referenced Data

A concept can appear in the model without implying that this scope owns all of its data.

| Concept | Role in Order Scope | How Responsibility Is Defined |
|---|---|---|
| Order | Central object with its own lifecycle | Managed by the order scope |
| Customer | Subject placing the order | Customer system owns the canonical profile; Order retains the identifier and transaction-relevant details |
| Product | Purchased item | Product catalog owns current data; Order retains snapshot info needed to explain the transaction |
| Payment result | Info needed to confirm or process the order | Payment system owns payment processing; Order references the result and transaction ID |
| Shipping | Fulfillment execution status | Shipping system owns delivery workflow; Order receives status needed for users |

This distinction prevents two mistakes: copying an entire external system's data into the current model, or storing only a reference without keeping the historical snapshot the business requires.

## 4. Deciding Which Concepts Belong in Scope

You can evaluate a candidate concept using these questions:

- Does it have its own identity or lifecycle in the business?
- Does it have attributes, relationships, or rules that need management?
- Must it be retained after the process completes?
- Does a question or scenario within the model's goal require it?
- Is the current scope responsible for its canonical data, or does it only need a reference?
- If removed, would any business rule or decision become unexplainable?

A concept generally belongs in the model when it has independent business meaning or is necessary to express an in-scope rule. External concepts may still appear as references or exchange payloads.

### In-Scope, Out-of-Scope, and Interface Table

| Category | Meaning | Example in Order Management |
|---|---|---|
| In scope | Described and managed directly | Order, line items, order status |
| Out of scope | Has its own domain logic, not modeled in detail here | Payment authentication, inventory management, delivery routing |
| Interface/Reference | Needs a slice of info to execute the workflow | Customer ID, product SKU, payment result, delivery status |

Do not interpret "out of scope" as "irrelevant". An out-of-scope process can still supply essential data. What must be documented clearly is what information the current model receives or sends, and who is accountable for its meaning.

### Explicitly Recording Unresolved Items

Create a list of assumptions and open questions rather than silently turning assumptions into design decisions. For example:

| Question | Temporary Assumption | When a Decision Is Needed |
|---|---|---|
| Can one order contain products from multiple sellers? | Multi-seller orders not yet supported | Before expanding into marketplace capabilities |
| Can an order have multiple payment attempts? | Multiple payment attempts allowed | When confirming payment and reconciliation workflows |
| Must every shipping address edit be retained historically? | Save address snapshot at placement plus major change events | When audit or dispute requirements arise |
| Can a cancelled order be restored? | Restoration not allowed yet | When the business defines a recovery workflow |

Each assumption should have a confirming owner or review trigger. If an assumption affects keys, lifecycles, relationships, or historical retention, resolve it before locking the logical model.

## 5. Keeping the Right Level of Abstraction: Conceptual Model Is Not Implementation Design

A conceptual model describes domain concepts, meaningful attributes, relationships, and rules. It should be readable by both business and technical stakeholders without requiring knowledge of the underlying database engine.

| Question | At the Conceptual Level | Details Saved for Later Phases |
|---|---|---|
| Which objects exist? | Customer, Order, Line Item | Table names, class names, collection names |
| What characteristics do objects have? | Placement date, status, quantity, price at purchase | `VARCHAR(…)`, `DECIMAL(p,s)`, engine-specific enum types |
| What does identity mean? | Each order is uniquely identified in the business | Auto-increment `BIGINT`, UUID, sequence, or ID generation scheme |
| How do objects relate? | An order has one or more line items | FK columns, join tables, embedding, or document references |
| Which rules must hold? | Positive quantity; confirmed order must have line items | `CHECK`, trigger, transaction, validator, or stored procedure |
| Which queries must be supported? | Look up customer orders chronologically | B-tree, composite index, partition, cache, or query plan |
| How is data organized? | An order comprises line items and related snapshots | Table normalization, document aggregate, graph traversal, or fact table |

Certain technical notes can be captured in a separate decision log, but they should not dictate the conceptual diagram. For example, the relationship "an order has many line items" remains true regardless of whether line items are later stored in a separate table, embedded in a document, or transformed into an analytical structure.

### Signs You Are Jumping into Implementation Too Early

- Starting a diagram with `CREATE TABLE`, SQL types, or physical column names before aligning on business terminology.
- Picking UUIDs, auto-increment integers, or key generation rules before defining identity meaning and uniqueness scope.
- Deciding indexes, partitions, sharding, or caching before knowing target queries and scale.
- Modeling directly after ORM classes, API DTOs, or current UI screen layouts.
- Embedding or splitting documents solely because the chosen database technology encourages one style.
- Adding technical fields like `created_by_service`, `retry_count`, or `json_payload` to the conceptual model without establishing business meaning.
- Using table or column names as a substitute for a clear definition of a concept.

This does not mean ignoring non-functional requirements. Security, retention, auditability, volume, and latency can directly affect data scope. Capture them as requirements or constraints; simply defer the specific implementation mechanism until enough context is available.

## 6. Example: Defining Scope for Order Management

Suppose the store needs a model to create orders, review purchased contents, confirm payments, and track deliveries. The business team agrees on the following:

- A customer can create multiple orders.
- Each order has one or more line items once confirmed.
- Each line item references a product and records its name and price at placement time.
- An order can have multiple payment attempts.
- The order needs to know the payment result and delivery status.
- Customer profiles, product catalog, payment processing, and delivery dispatch are managed in other scopes.

### Chosen Boundaries

| Item | Decision | Rationale |
|---|---|---|
| Order and line items | Modeled directly | Core data of the workflow |
| Customer identifier | Referenced | Canonical profile is managed by the customer system |
| Product name and price at placement | Stored as historical order data | Current prices and names may change |
| Card details and charge processing | Out of scope | Payment system is responsible |
| Transaction ID and payment result | Modeled for received info | Needed for confirmation, reconciliation, and order handling |
| Delivery route selection algorithm | Out of scope | Shipping system is responsible |
| Delivery status | Referenced as status info | Users need to track order progress |

### Initial Conceptual Model

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--o{ ORDER_LINE : contains
    PRODUCT ||--o{ ORDER_LINE : identifies
    ORDER ||--o{ PAYMENT_ATTEMPT : has
~~~

The diagram depicts only the necessary concepts and relationships. Here, `CUSTOMER` and `PRODUCT` are referenced concepts; this does not imply the order scope owns the full customer profile or product catalog. `PAYMENT_ATTEMPT` represents the attempts and outcomes that the order workflow needs to know about, not the internal details of external payment processing.

Several points require business verification before moving to the logical model:

1. Does "one or more line items" apply from order creation or only upon order confirmation? Can a draft order have zero line items?
2. Can payment be retried after failure? Does each attempt have its own reference code?
3. Does a paid order that gets cancelled trigger a refund event? If so, does the order scope only need the refund outcome or the full refund lifecycle?
4. Are line item modifications allowed after payment? If so, what must history show?
5. Is the shipping address captured at placement or changeable prior to handover?

These questions determine data meaning and lifecycle. They must be answered before choosing whether to store data as tables, documents, or another structure.

## 7. Workflow for a Scoping Session

You can use the following workflow for a new problem:

1. **Write the objective:** state the process, users, and decisions the model must support.
2. **List scenarios:** describe happy paths, exception paths, and data-changing events.
3. **Create a candidate concept list:** extract from nouns, verbs, states, and rules; do not turn them into tables yet.
4. **Draw a context diagram:** place the scope at the center, showing actors, related systems, and data crossing boundaries.
5. **Classify concepts:** in scope, out of scope, or referenced; document rationale and canonical source.
6. **Choose level of detail:** identify which objects, events, and history need description; omit details that do not serve the goal.
7. **Record assumptions and open questions:** state the impact of each assumption, who must confirm, and by when.
8. **Validate with scenarios:** trace data end-to-end across the workflow, including failures, cancellations, edits, and history lookups.
9. **Publish outputs:** release the scope statement, context diagram, glossary, concept list, and open decisions.

### Minimum Output Package

| Output | Required Content |
|---|---|
| Scope statement | Objective, users, process start/end points |
| Context diagram | Actors, related systems, and data exchanges |
| Concept list | Definitions, roles, in-scope/out-of-scope/referenced status |
| Glossary | Canonical names, definitions, and examples |
| Rule list | Conditions, exceptions, lifecycle, and history |
| Assumptions/open questions | Unconfirmed items, impact, and accountable owner |
| Decision log | Rationale for scope choices, rejected options, and review triggers |

## 8. Checking Scope Before Moving to Logical Modeling

A scope is clear enough when business and technical stakeholders can consistently answer the following checks:

- [ ] The model's objective and target users are clearly stated.
- [ ] Process start points, end points, and core scenarios are defined.
- [ ] Core concepts have agreed definitions.
- [ ] Boundaries with other systems and referenced data are clearly specified.
- [ ] Decisions exist on current data, snapshots, and historical data to retain.
- [ ] Important rules and exception cases are documented.
- [ ] Out-of-scope items have stated reasons and responsible owners.
- [ ] High-impact assumptions have a confirming owner or resolution schedule.
- [ ] The model is not yet dictated by table names, SQL types, indexes, ORMs, or specific storage tech.
- [ ] Diagrams and examples can explain the scope to someone newly joining the project.

Once scope is aligned, the team translates concepts into a logical model: identifying candidate keys, relationships, constraints, and data dependencies; only afterward do they consider normalization, data types, indexes, and physical schemas. When choosing relational, document, graph, or analytical models, evaluate them against the same confirmed requirements and boundaries. That way, options can be compared fairly without mistaking technology choices for business meaning.

A strong conceptual model begins with an explainable boundary. It includes enough data to answer in-scope questions, references only what belongs to external owners, and defers implementation details to the right phase. When goals, concepts, responsibilities, and assumptions are clear, transitioning to logical and physical models rests on a solid foundation for verification and evolution.
