# Criteria for a Concept to Have Its Own Identity and Lifecycle

When translating business requirements into a data model, a foundational decision is determining which concepts need to be modeled as an **entity**. If every noun in the requirements is turned into a table or class with its own key, the model becomes complex and creates duplicated data. Conversely, if objects with distinct identities and lifecycles are collapsed into a few attributes inside one large record, the system struggles to reference them, track history, and control changes.

A concept is usually suited to become an entity when the business needs to recognize each individual instance of that concept over time, distinguish it from other instances, and manage its changes across a meaningful lifecycle. An identifier lets the system refer to the exact same object even when its name, address, status, or descriptive attributes change.

For example, a customer can change their display name, email, or address and still remain the same customer. An order can transition from newly created to confirmed, shipping, and then completed, and still remain the same order. In contrast, an amount of 250,000 VND is typically a descriptive value; if the amount changes, we have a different value, not necessarily a monetary object whose own lifecycle needs to be tracked.

This lesson focuses on how to identify the boundary between an entity and other concepts, determine identification needs, choose identifier scope, and evaluate lifecycles before designing tables, keys, or relationships.

## 1. What Is an Entity?

An entity is a business object that can be individually identified and distinguished from other objects of the same kind. Each entity has an identity that persists across permissible changes to its descriptive attributes.

For example:

- A specific customer in a sales system.
- A product managed in a catalog.
- An order placed by a customer.
- A specific payment for an order.
- A warehouse at a location.
- A contract signed between parties.

An entity can be a person, thing, organization, location, account, transaction, or an abstract concept managed by the business. It does not have to be a physical object.

### 1.1. Identity vs. Descriptive Attributes

Identity answers the question "which object is this?". Attributes answer the question "what characteristics does this object have?".

For example, for a customer:

| Component | Example | Role |
|---|---|---|
| customer_id | CUS-10482 | Identifies the customer record within system scope |
| full_name | Nguyễn An | Descriptive attribute, mutable |
| email | an@example.test | Contact attribute, mutable or shared |
| birth_date | 1994-08-12 | Descriptive attribute |
| status | active | Lifecycle status |

If a customer changes their email, the system updates the email attribute of the same customer. If email were used as the sole identity without investigation, changing the email could make the system treat them as a new customer or break existing references.

### 1.2. An Entity Is Not Synonymous with a Database Row

An entity is a business concept. A table, document, or graph node is how that concept is represented in a storage technology.

One entity can be stored across multiple tables; conversely, one table can store data for multiple kinds of objects if the model is designed that way. In a document database, an entity may be stored together with its dependent components in a single document. In a graph database, it may be a node. In an analytical model, it may be represented by a dimension or other structures.

Therefore, decide on the business concept first, and only then choose its physical representation. Do not conclude a concept is an entity merely because it currently has a table in a legacy system.

## 2. Signs That a Concept Needs Its Own Identifier

No single sign is always decisive. Consider the following questions together.

### 2.1. Is It Necessary to Distinguish Specific Instances?

If the business needs to refer to one specific instance among many instances of the same type, that is a strong indicator of an identification need.

For example:

- "This order is awaiting payment" requires identifying one exact order.
- "This customer has verified their identity" requires identifying one exact customer profile.
- "This parcel has been handed over to the carrier" requires identifying one exact parcel.

Conversely, a value such as "blue" or "currency unit VND" may just be an attribute value or reference data. If there is a need to manage a catalog of colors or currency units with their own codes and rules, that catalog may have a reference entity; however, each value appearing in an attribute does not automatically become an independent business entity.

### 2.2. Does the Object Retain Its Identity When Attributes Change?

Ask: if the name, address, status, display value, or configuration changes, does the business still consider it the same object?

- A customer changes their name: usually still the same customer.
- A product changes its description: still the same product if the product code and product meaning do not change.
- An order changes status: still the same order.
- A phone number is reassigned from one person to another: the phone number value does not represent the same person across all time.

If identity must persist independently of mutable attributes, the concept usually needs a stable identifier.

### 2.3. Does the Object Have Its Own Business Lifecycle?

An entity often has milestones such as creation, activation, modification, suspension, completion, closure, or cancellation. Not every entity needs many states, but if the business has distinct actions and needs to track the progress of each instance, that is an important sign.

For example:

- An order is created, confirmed, partially shipped, fully delivered, or canceled.
- An account is opened, locked, reopened, or closed.
- A contract is drafted, signed, effective, renewed, or terminated.
- A goods receipt voucher is created, approved, received, and closed.

An entity's lifecycle must be distinguished from a simple attribute changing. An `is_active` flag is not enough to prove a concept has its own lifecycle if there are no other independent business rules or operations.

### 2.4. Is the Object Referenced from Elsewhere?

If multiple processes need to reference the same object stably, a dedicated identifier helps avoid duplicating information and reduces confusion.

For example:

- An order references a customer.
- An order line references a product.
- A stock issue voucher references a warehouse.
- A refund transaction references the original payment.
- An appointment references a patient and an assigned staff member.

A reference does not have to be a foreign key within the same database. It can be an identifier passed via an API, message, document reference, or link between nodes. What matters is that the object is consistently identified within the defined scope.

### 2.5. Does the Object Require Its Own Rules or Permissions?

If a concept has its own validation rules, access permissions, states, retention policies, or processing workflows, it may need a separate entity boundary.

For example, a login account and a customer profile may be related, yet are not necessarily a single object. An account has authentication status, login credentials, and account lockout rules; a customer profile has a name, contact details, and purchase history. One customer may have multiple accounts, or an account may be linked to multiple roles, depending on the business domain.

### 2.6. Is Separate History or Traceability Required?

If it is necessary to know how an object changed, who made the change, or what its state was at a given point in time, a stable identifier helps link versions and events together.

For example, the system needs to look up all status transitions of an order. If only a summary status record is stored without a stable order identifier and history, investigation becomes difficult.

### 2.7. Identification Question Checklist

| Question | Sign That an Entity Is Needed |
|---|---|
| Are there multiple distinct instances of the same kind? | Need to distinguish individual instances |
| Can attributes change while it remains the same object? | Identity is independent of description |
| Does it have its own lifecycle or business actions? | Has dedicated states and transitions |
| Do other processes need to reference the object? | Needs a stable identifier |
| Does it have its own rules, permissions, or policies? | Has a separate management boundary |
| Is history or traceability needed per instance? | Needs version/event linking |

These questions serve as an analytical guide, not a mechanical scoring rubric. A concept does not need to exhibit every single sign to be considered an entity. Prioritize confirmed business requirements and the consequences of lacking a separate identifier.

## 3. Distinguishing Entities from Similar Concepts

### 3.1. Entities and Value Objects

A **value object** is defined primarily by the values that compose it, rather than an independent identity. Two value objects with identical values under comparison rules can be treated as equivalent.

For example:

- Money consisting of an amount and a currency.
- A time interval consisting of a start time and an end time.
- A shipping address captured at the time an order is placed.
- Geographic coordinates consisting of longitude and latitude.
- A set of dimensions consisting of length, width, and height.

If a value changes, we typically have a new value object replacing the old one. We do not necessarily have to ask "is this still the same money or address object?" as we would with a customer.

However, the same concept may be modeled differently depending on the business domain:

- An address captured inside an order can be a value object, because it describes the delivery destination at the time of ordering.
- A delivery location managed by multiple units, with a code, operational status, history, and referenced by many orders, can be an entity.
- A personal address book entry managed and edited independently may also need its own identifier.

Do not conclude "an address is always a value object" or "an address is always an entity." Evaluate its purpose, ownership, and lifecycle.

### 3.2. Entities and Attributes

An attribute describes an entity. It usually does not need its own identifier if it only exists as a descriptive part of an object and is not managed independently.

For example, the current color of a product can be a `color` attribute. If the enterprise needs to manage a standard color chart, color codes, multilingual names, and usage status, each color in the catalog may become a reference data record. Having its own code in a catalog does not mean a color becomes a business entity with a lifecycle like an order.

Ask whether the attribute is shared, referenced, governed, or has an independent history.

### 3.3. Entities and Reference Data

Reference data is a managed set of values used to standardize how data is categorized or interpreted—for example, currency types, order types, region codes, or status lists.

Reference data typically has stable codes and clear definitions, while its lifecycle may be very simple: adding values, renaming labels, and deprecating them. It can be stored in a separate table without needing to be modeled as a behavior-rich business entity.

If the catalog has an approval workflow, effective dating, hierarchy, relationships, or its own owner, it may need to be modeled as a reference entity. The degree of modeling depends on actual requirements.

### 3.4. Entities and Events

An event describes something that happened at a point in time, such as `OrderPlaced`, `PaymentCaptured`, or `AddressChanged`. Events are typically immutable once recorded and carry a timestamp, originating source, and related payload.

An entity describes an object that has identity and can undergo multiple changes. An order is an entity; the order placement event and status change events describe what happened to that order.

An event may also have its own identifier for deduplication, traceability, and referencing. That does not mean an event has the same kind of lifecycle as a business entity. An event ID typically identifies a single occurrence, whereas an order ID identifies the order object across many events.

### 3.5. Entities and Processes

A process describes a sequence of activities aimed at achieving an outcome. A process step may just be a status or an event, whereas a specific execution instance of a process may need its own entity.

For example:

- "Order approval workflow" is a concept describing how work is done.
- A specific order approval request with a requester, approver, deadline, outcome, and history can be an `ApprovalRequest` entity.
- The `pending` status is merely one state of the approval request, not necessarily a separate entity.

### 3.6. Entities and Classification Groups

A role such as `admin`, a customer tier such as `VIP`, or a status such as `pending` is usually a classification value. If a catalog of roles or statuses needs to be managed, a reference table can be used. However, separate business entities should not be created for every value merely because they are nouns or can appear in a list.

## 4. Decision Process for Whether a Concept Needs Its Own Entity

The following process can be applied to each noun or concept that appears in business requirements.

~~~mermaid
flowchart TD
    A["Concept appears in requirements"] --> B{"Need to identify specific instances?"}
    B -->|No| C["Consider attribute, value object, or reference value"]
    B -->|Yes| D{"Does identity persist when descriptive attributes change?"}
    D -->|No| E["Consider value object or value record"]
    D -->|Yes| F{"Does it have its own lifecycle, rules, or references?"}
    F -->|Unclear| G["Investigate further scenarios and business impact"]
    F -->|Yes| H["Propose entity with dedicated identifier"]
    G --> F
    H --> I["Define identifier scope and lifecycle"]
    I --> J["Validate with examples, exceptions, and consumers"]
~~~

### Step 1: Write a Business Definition

Describe the concept in one sentence stating clearly what it is and what purpose it serves. Avoid circular definitions like "a customer is a customer."

For example: "An order is a purchase request recorded by the system with a customer, line items, locked-in prices, and its own processing status."

The definition should be confirmed by domain experts. The same term can carry different meanings across departments.

### Step 2: List Distinct Instances

Use real or hypothetical examples: two customers with the same name, a customer changing their email, an order having multiple payments, an address used by multiple orders. If the system needs to distinguish these cases, specify how.

### Step 3: Test Identity When Attributes Change

Ask whether the object remains the same object after changing its name, address, status, owner, or configuration. If the answer is yes, identity should not depend entirely on that mutable attribute.

### Step 4: Identify Actions and Lifecycle

List the operations for creating, editing, suspending, activating, completing, canceling, merging, or closing. Specify which operations change state, who is authorized to perform them, and what conditions must be satisfied.

### Step 5: Check Relationships and References

Identify which objects need to link to this concept. If a concept is shared across multiple workflows, evaluate assigning a dedicated identifier and managing its lifecycle independently.

### Step 6: Determine Which Data Truly Needs Independent Storage

Do not separate a concept just to have its own table. Weigh whether it needs independent storage, querying, authorization, history, quality checks, or evolution.

### Step 7: Check Edge Cases

Consider cases such as merging two profiles, splitting one organization into two, changing codes, transferring ownership, deleting, or restoring. If these cases are meaningful to the business, the model must account for identity before and after the change.

## 5. Defining the Scope of an Identifier

After deciding an entity is needed, determine within what scope the identifier is meaningful. A code unique within one table may not suffice when data is exchanged across multiple systems or multiple organizations.

### 5.1. Distinguishing Identity, Identifier, and Key

- **Identity:** the concept that lets us recognize the same object over time.
- **Identifier:** a value or set of values used to point to the object.
- **Key:** an attribute or set of attributes used to identify a record according to the rules of the data model.

One entity can have multiple identifiers: an internal ID, a business code, a partner ID, or a legacy ID. They may all refer to the same identity while having different scopes and lifetimes.

### 5.2. Internal Identifiers and Business Codes

An internal identifier is managed by the system for stable referencing. A business code is used by users or partners in workflows.

For example:

- `customer_id = 8f...` is an internal identifier.
- `customer_number = KH-2026-0042` is a displayed business code.
- `legacy_customer_code = A01983` is a code from a legacy system.

It is not necessary to use the same value for all three purposes. A business code may have formatting rules and may change during system mergers or when the business changes processes. An internal identifier should generally be more stable.

### 5.3. Uniqueness Scope

Determine where the code must be unique:

- Within a single table.
- Within a tenant or organization.
- Within a source system.
- Across the entire enterprise.
- Across the entire partner network.
- Within a specific time period.

For example, `employee_number` may be unique within each subsidiary but collide between two companies. In that case, the pair `(organization_id, employee_number)` uniquely identifies an employee within organizational scope.

### 5.4. Identifiers Should Not Depend on Mutable Data

Email, phone number, name, address, username, or classification codes can change, be reused, or be non-unique. Only use them as a primary key when the business can prove stability, uniqueness, and non-reuse throughout the entire timeframe references are needed.

For example, a phone number can be reassigned to someone else after a period of time. If the phone number is the customer key, contact history could be mistakenly attached to the new owner. Store the phone number as an effective-dated attribute or create a separate contact entity if it needs to be managed independently.

### 5.5. Do Not Reuse Identifiers

If a customer is closed or deleted by policy, their identifier should generally not be reissued to a new customer. Reusing it can cause order history, logs, or old references to point to the wrong object.

If the business requires reusing a display code, separate the display code from the internal identifier and explicitly define the effective period or uniqueness scope.

### 5.6. Cross-System Identifiers

When multiple systems have their own codes, a clear mapping mechanism is required:

| Field | Example | Meaning |
|---|---|---|
| entity_id | 01J... | Stable internal identifier |
| source_system | CRM | External code issuing source |
| external_id | C-00982 | Customer ID in the CRM |
| valid_from | 2026-01-01 | Effective start time of the mapping |
| valid_to | NULL | End time, if applicable |

The mapping table needs appropriate constraints, such as ensuring one pair `(source_system, external_id)` maps to only one entity at any given time within the defined scope. When two records are merged, retain the old code information and redirection rules so consumers do not lose traceability.

## 6. Choosing a Key Type for an Entity

### 6.1. Natural Keys

A natural key is an attribute that carries business meaning and can identify an object—such as an identifier issued by a competent authority, a standardized product code, or an established contract code.

Advantages:

- Meaningful to the business.
- Can be used to reconcile against external sources.
- Can avoid creating an extra ID if the value is already stable and reliable.

Risks:

- Values may change due to regulations or processes.
- Uniqueness scope may not be global.
- May contain sensitive information.
- May be mistyped or reissued.
- May be awkward to use as a technical reference if long or complexly formatted.

Before using a natural key as a primary key, verify whether it is unique, non-null, stable, non-reusable, and permitted to be stored or shared.

### 6.2. Surrogate Keys

A surrogate key is a system-generated code carrying no direct business meaning. Examples include auto-incrementing integers, UUIDs, or another generated identifier.

Advantages:

- Decouples technical identity from business attributes.
- Can remain stable when business codes change.
- Easy to reference in relationships.
- Can reduce exposure of business information in URLs or logs if designed appropriately.

Risks:

- Does not automatically guarantee uniqueness across all systems if the generation method is unsuitable.
- Does not replace uniqueness constraints on business codes.
- Can introduce an extra mapping step during integration.
- Sequential IDs can leak scale or creation order if exposed publicly.

A common choice is to use a surrogate key as the internal primary key and add a unique constraint on business codes that have uniqueness rules. This is a design choice, not a mandatory rule for every model.

### 6.3. Simple Keys and Composite Keys

A simple key uses a single attribute for identification. A composite key combines multiple attributes.

For example, in a class membership table, if a student can only enroll once per class, the composite key `(class_id, student_id)` may fit well. However, if an enrollment can be canceled and re-created and the history of each attempt must be stored, a dedicated identifier for each enrollment or an additional component distinguishing each enrollment attempt is needed.

Composite keys reflect business rules directly, but they can make foreign keys wide and make changing key components difficult. Choose based on the actual lifecycle and referencing patterns.

### 6.4. Candidate Keys, Primary Keys, and Alternate Keys

An entity can have multiple sets of attributes that uniquely identify it:

- **Candidate key:** a minimal set of attributes capable of unique identification.
- **Primary key:** the candidate key chosen as the main key.
- **Alternate key:** another candidate key not chosen as the primary key.

For example, a product has an internal `product_id` and a `sku` unique within a store scope. We can choose `product_id` as the primary key and place a unique constraint on `sku` as an alternate key.

An identifier does not replace data constraints. If `sku` must be unique, the model must express that rule via an appropriate constraint or enforcement mechanism.

## 7. Evaluating an Entity's Lifecycle

A stable identifier tells us which object is being discussed; a lifecycle describes the states and events that the object can go through.

### 7.1. Identifying Lifecycle Milestones

For each entity, investigate:

- Who or which process is allowed to create it?
- When is the object considered to officially exist?
- Is there a validation or approval step before activation?
- What are the valid states?
- Who is allowed to transition states?
- What preconditions must be met before transitioning?
- Can it return to a previous state?
- When is the object considered completed, closed, or expired?
- Can it be restored after closing?
- When is the data deleted, anonymized, or archived?

Not every entity needs a complex state machine. Model the exact states that carry business meaning and avoid creating states just to reflect every internal technical step.

### 7.2. Distinguishing Current State from State Transition History

A `status` column usually represents the current state. If you need to know which states an object has passed through, you need an additional history or event structure.

For example:

| order_id | current status | created_at |
|---|---|---|
| ORD-104 | shipped | 2026-04-02 09:00 |

State transition history can store:

| order_id | from_status | to_status | changed_at | actor |
|---|---|---|---|---|
| ORD-104 | NULL | pending | 2026-04-02 09:00 | customer |
| ORD-104 | pending | confirmed | 2026-04-02 09:03 | order-service |
| ORD-104 | confirmed | packed | 2026-04-02 10:20 | warehouse |
| ORD-104 | packed | shipped | 2026-04-02 13:15 | carrier |

The table above is illustrative only. Determine which states belong to the order lifecycle and which belong to shipping or payment. Do not merge states of different objects into a single column if they have separate lifecycles.

### 7.3. Lifecycle of Dependent Objects

Some objects only make sense within the scope of a parent entity. For example, an order line item depends on an order; an address detail in a profile may depend on a customer; a line in a statement may depend on a voucher.

Ask:

- Can the child object exist independently if the parent object is deleted or closed?
- Can it be moved to a different parent?
- Does it need to be referenced or queried directly?
- Does it have its own lifecycle or only change alongside the parent?
- Does it need its own identifier to distinguish identical occurrences?

If a line item only has meaning within one order, a composite key `(order_id, line_number)` may suffice. If the line item can be referenced by shipping, refunds, or audits over a long period, a stable `order_item_id` can be useful.

### 7.4. Merging, Splitting, and Replacing Objects

These are scenarios where identity consistency is easily lost:

- **Merging:** two customer profiles are determined to be the same person. A canonical profile must be chosen, old code mappings preserved, and references handled.
- **Splitting:** an organization profile contains two independent units and must be split into two. It is necessary to determine which data and transactions belong to each object.
- **Replacing:** an old device is replaced by a new device. Do not keep the same identity if the business treats them as two different devices.
- **Transferring ownership:** an asset transfers from one person to another, yet remains the same asset.
- **Changing codes:** the business code changes, yet the object retains its identity.

Do not confuse changing an owner or identification code with creating a new entity. Base the decision on the business definition and history tracking rules.

## 8. Cases Prone to Wrong Decisions

### 8.1. Email and Phone Number

A customer can have multiple emails or phone numbers; a contact point can be shared; values can change or be reused. If the business needs to manage each contact method, verification status, priority level, effective period, and change history, `ContactPoint` can be modeled as a dependent entity with its own identifier.

If only a display email needs to be stored and no independent management is required, email can be an attribute or value object.

### 8.2. Address

An address can be:

- A value object captured inside an order.
- A managed, shared location entity.
- A customer contact address entity with multiple effective versions.
- Reference data pointing to an externally standardized location.

Distinguish between physical address, mailing address, shipping address, and billing address. They may share identical values while carrying different business meanings.

### 8.3. Order Line Items

Line items often need their own identifier because two lines can have the same product but different prices, promotions, notes, delivery batches, or processing statuses. If only `product_id` is used as the line identifier, two occurrences of the same product in one order can collide.

A line item can be an entity dependent on the order. Its identity can be defined by `order_item_id` or the pair `(order_id, line_number)` depending on requirements.

### 8.4. Monetary Amounts and Unit Prices

A monetary amount is typically a value object consisting of a numeric value and a currency. A unit price applied to a line item can be captured in the transaction. If the system needs to manage price lists, price versions, effective periods, and approval workflows, `PriceList` or `PriceRule` can be separate entities.

Do not create an entity for every monetary figure simply because it is stored in a column.

### 8.5. Statuses

`pending`, `approved`, `closed` are typically status values. A status may reside in a reference catalog, while each status transition is an event or history record. The object undergoing the state transitions is the entity with the lifecycle.

### 8.6. Login Sessions and Accounts

An account has an identity and lifecycle that outlives a login session. A login session is a single authentication instance with its own start time, expiration, device, and status. If individual sessions need to be revoked, audited, or device-limited, `session` can be a technical entity with its own identifier, even though it is not a core business entity like customer.

## 9. End-to-End Example: Identifying Entities in a Sales System

Suppose the business requirement is: customers browse products, add them to a cart, place an order, pay, and receive goods.

### 9.1. Concept Classification

| Concept | Initial Proposal | Rationale |
|---|---|---|
| Customer | Entity | Has its own identity, profile, permissions, and history |
| Product | Entity | Has a code, description, commercial status, and is referenced by many processes |
| ShoppingCart | Entity | Has an owner, lifetime, status, and mutable contents |
| CartItem | Dependent component or child entity | Needs to distinguish individual lines and quantity changes |
| Order | Entity | Has its own identifier, transaction, and lifecycle |
| OrderItem | Dependent entity | Has locked-in price, quantity, discount, and its own processing history |
| Payment | Entity | Has its own transaction ID, status, result, and reconciliation |
| Money | Value object | Defined by amount and currency |
| ShippingAddressSnapshot | Value object | Describes the address locked in at order placement |
| OrderStatus | Reference value or enum | Describes the current status |
| OrderStatusChange | Event/history record | Records a single status transition |
| EmailAddress | Attribute/value object or dependent entity | Depends on whether verification, multiple addresses, and separate history are needed |

This is an initial proposal and must be confirmed with the business. For example, an anonymous cart may be transferred to a customer after login; a cart may expire; an order may have multiple payments. These scenarios affect boundaries and relationships.

### 9.2. Testing Identity Across Changes

- Customer changes email: keep `customer_id`.
- Product changes display name: keep `product_id`.
- Product price changes: keep the product, create an appropriate price version or record.
- Order changes status: keep `order_id`.
- A payment is declined and the customer retries: determine whether each attempt is a separate payment attempt or an update to the same transaction.
- Shipping address changes after the order is placed: the profile address can change, while the order's address snapshot preserves the confirmed facts.

### 9.3. High-Level Identity Model

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : referenced_by
    ORDER ||--o{ PAYMENT : has
    ORDER ||--o{ ORDER_STATUS_CHANGE : records
    CUSTOMER ||--o{ SHOPPING_CART : owns
    SHOPPING_CART ||--o{ CART_ITEM : contains
    PRODUCT ||--o{ CART_ITEM : selected
~~~

The diagram only illustrates conceptual relationships at a high level. It does not yet decide physical keys, optionality, exact multiplicity for every case, or how snapshot addresses are stored. Those decisions must be verified against business rules.

### 9.4. Questions to Finalize Before Table Design

- Can one customer have multiple accounts?
- Can a shopping cart exist before a customer logs in?
- Can the same product appear multiple times in the same order?
- Does each payment attempt have its own identifier?
- Can an order be split into multiple delivery shipments?
- Can a shipping address be edited after confirmation? If so, which version must be retained?
- Is the order number unique across the entire enterprise or only within one channel?
- When two customer profiles are merged, which identifier do historical orders reference?

The answers will determine entity boundaries, keys, and relationships; do not make assumptions based on the structure of an existing application.

## 10. Translating Conceptual Decisions into a Data Model

After identifying entities, record the minimum information needed to move to logical design.

| Aspect | What Needs to Be Defined |
|---|---|
| Name and definition | Standard name and business meaning |
| Scope | Which organization, tenant, or domain the object belongs to |
| Identity | What distinguishes one instance from another |
| Identifier | Internal key, business code, and external codes |
| Uniqueness | Scope and timeframe of uniqueness |
| Lifecycle | States, events, and transition rules |
| Ownership | Who is responsible for creating, editing, closing, and merging |
| Relationships | Which objects reference the entity |
| History | Which attributes or events require history retention |
| Retention | When data is archived, anonymized, or deleted |

### 10.1. Do Not Create Keys Before Defining Uniqueness Rules

An `id` column can identify a record, but it does not prove business data is free of duplicates. For instance, two customer records with two different `customer_id` values can still be the same customer due to data entry creating duplicate profiles.

Identify candidate keys and duplicate-detection rules. For data that can legitimately collide—such as two people sharing a name or an address—never merge solely on a single descriptive attribute.

### 10.2. Identifiers and Relationships Must Be Consistent

If an entity is referenced from many places, changing identifiers or merging records requires an update or mapping procedure. Do not delete the original record and create a new ID without handling foreign keys, events, reports, and consumers.

In a relational model, this typically involves primary keys, foreign keys, unique constraints, and mapping tables. In a document model, related documents may need references or updates. In a graph model, node identities and referencing edges must be managed. Technologies differ, yet business requirements regarding identity must remain clear.

### 10.3. Identifiers Do Not Replace Access Control

Knowing a `customer_id` does not mean a user has permission to view that customer. An identifier only identifies the object; access permissions must be checked by role, ownership relationship, tenant, and purpose.

Do not treat hard-to-guess UUIDs as an authorization mechanism. APIs must still verify permissions on each object.

## 11. Common Mistakes When Identifying Entities

- **Turning every noun into a table:** leaves the model with too many reference tables or tables lacking business meaning.
- **Using mutable attributes as primary keys:** changing an email or display code breaks references.
- **Confusing statuses with entities:** creating a table for every status when it is merely a value or event.
- **Confusing events with objects:** using an event ID in place of the entity identifier across its lifecycle.
- **Merging multiple lifecycles into one entity:** account, customer, and login session have different rules yet are placed together.
- **Over-splitting value objects:** creating separate entities for every address or monetary amount despite no need for independent management.
- **Failing to define uniqueness scope:** a code unique within one tenant is treated as globally unique.
- **Reusing IDs after deletion:** historical references may end up pointing to a new object.
- **Ignoring profile merges:** other systems keep using old codes and create orphaned data.
- **Relying solely on surrogate keys:** omitting unique constraints on business keys.
- **Using one status for multiple objects:** payment, order, and shipping statuses get mixed together.
- **Designing around legacy tables:** keeping old technical structures even when current business rules have changed.

## 12. Verification Criteria for Entity Decisions

A modeling decision should have examples and test scenarios. The following cases help surface mistakes:

**Changing attributes while preserving identity**

- Given: a customer has a stable `customer_id`.
- When: the customer changes their name or email.
- Then: prior orders and history still reference that exact customer.

**Distinguishing two instances with identical attributes**

- Given: two customers share the same display name.
- When: the system creates profiles for both.
- Then: the system does not automatically treat them as one person based solely on name.

**Testing uniqueness scope**

- Given: two organizations may use the same employee number.
- When: each organization creates an employee with the same `employee_number`.
- Then: the model still distinguishes the two employees within each organization's scope.

**Preserving identity when changing business codes**

- Given: an order has an old display code.
- When: the order numbering rule changes.
- Then: internal references and history still point to the same order.

**Handling dependent entities**

- Given: an order has two lines for the same product with different locked-in prices.
- When: the system saves the line items.
- Then: each line is distinguished and can be referenced separately during refunds or fulfillment.

**Merging profiles**

- Given: two customer profiles are confirmed to be duplicates.
- When: the business merges them.
- Then: there is a canonical profile, old code mapping, reference handling, and change audit trail.

**Managing lifecycles**

- Given: an account has been locked.
- When: a user attempts to log in or an administrator requests reopening.
- Then: the system applies the correct state transition rules and records history as required.

## 13. Pre-Finalization Checklist for Entities

- [ ] A clear business definition exists for the concept.
- [ ] Whether individual instances must be distinguished has been determined.
- [ ] Whether identity persists when descriptive attributes change has been verified.
- [ ] Specific actions, states, and lifecycles (if any) have been identified.
- [ ] Whether other processes need to reference the object has been checked.
- [ ] Entities have been distinguished from attributes, value objects, reference data, events, and processes.
- [ ] Identifier scope and uniqueness rules have been defined.
- [ ] Natural keys, surrogate keys, and composite keys have been evaluated.
- [ ] Internal IDs, business codes, and external system IDs have been identified.
- [ ] Handling for code changes, merges, splits, and object deletion has been defined.
- [ ] Dependent relationships and whether child objects can exist independently have been determined.
- [ ] History, retention, and traceability requirements have been defined.
- [ ] Verification scenarios exist for normal and exception cases.
- [ ] The decision has been confirmed by the business owner.

A concept should be modeled as an entity when the business needs to recognize each individual instance, preserve its identity across valid changes, and manage it as an object with defined responsibilities or lifecycles. The chosen identifier must accurately reflect uniqueness scope and not depend on volatile attributes. Clarifying these points before creating tables and keys will keep the data model easy to reference, preserve history, and evolve alongside the business.
