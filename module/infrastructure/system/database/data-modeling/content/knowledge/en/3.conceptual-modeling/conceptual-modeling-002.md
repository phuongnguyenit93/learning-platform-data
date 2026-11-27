# Distinguishing Entities, Attributes, Relationships, and Events

When reading business requirements, we often encounter sentences such as "a customer places an order", "an order contains multiple products", "a product belongs to a category", "the customer makes a payment", and "the warehouse reserves stock for the order". These sentences contain different kinds of concepts. If we immediately turn all of them into tables or columns, the model easily confuses an identifiable object, a descriptive property, a link between objects, and something that occurred at a specific point in time.

In a conceptual data model, these four concepts each play a distinct role:

- **Entity**: a business object or concept that needs to be identified and tracked over time.
- **Attribute**: information describing an entity or a relationship.
- **Relationship**: describes how entities connect to one another, along with the cardinality and mandatory participation of the link.
- **Event**: something that happened at a point in time, which may change business state or produce historical facts.

This lesson uses an online store example consisting of customers, categories, products, orders, payments, and inventory. We will classify each concept, draw a conceptual model, and validate the model using concrete scenarios. This is a foundational step in turning business requirements into a clear, verifiable, and evolvable data model.

## 1. Four Concepts Answer Four Different Questions

Let us start with a requirement excerpt:

> A customer has a profile and multiple shipping addresses. A customer can place multiple orders. Each order consists of multiple line items; each line item references a product and records the quantity and price at the time of purchase. A product can belong to multiple categories. When the customer submits an order, the system records the order placement timestamp. When payment succeeds, the system records the transaction and changes the order status. The warehouse reserves stock for the order before delivery.

We can ask four questions to separate the concepts:

| Question | Concept | Example in the Store |
|---|---|---|
| Who or what does the system need to identify? | Entity | Customer, product, order, warehouse |
| What do we need to know about each object? | Attribute | SKU, product name, creation date, quantity |
| How are objects linked to one another? | Relationship | Customer places order; order contains line item |
| What happened, when, and involving whom/what? | Event | Order placed, payment confirmed, stock reserved |

One sentence can contain multiple kinds of concepts. "Customer places an order at 10:00" contains:

- **Customer** and **SalesOrder** are two entities.
- **places** is the relationship between customer and order.
- **OrderPlaced** is the event occurring at 10:00.
- **placed_at** may be a timestamp attribute on the order or an attribute on the event record, depending on storage and audit requirements.

Do not decide based solely on part of speech. A noun is not automatically an entity, and a verb is not automatically an event. Consider the concept's identity, lifecycle, reusability, history, and business rules.

## 2. Entity: An Object That Needs to Be Identified

An entity is something the business needs to distinguish one instance of from other instances. It has an identifier and usually its own lifecycle.

### 2.1. Signs of an Entity

A concept is likely an entity when it exhibits one or more of the following signs:

- Users need to search, view, create, update, or manage individual instances.
- It can be referenced by multiple other objects.
- It has its own state or lifecycle.
- It needs to preserve change history.
- Two instances can have identical descriptive attributes yet still need to be told apart.

In the store, two customers may share the same name and city yet still be two different people. Thus, **Customer** needs its own identifier. Two products with the same display name yet different SKUs must also be identified separately.

Examples of core entities:

| Entity | Why Individual Identification Is Needed | Possible Business Identifier |
|---|---|---|
| Customer | Has profile, addresses, orders, and purchase history | Customer code |
| Product | Has SKU, price, selling status, and categories | SKU |
| Category | Has parent–child structure, name, and status | Slug or category code |
| SalesOrder | Has a lifecycle from draft to completed/cancelled | Order number |
| OrderItem | A specific line inside an order | Line number within the order |
| Payment | Has amount, provider, and transaction outcome | Provider transaction ID |
| Warehouse | Has location and distinct storage operations | Warehouse code |
| InventoryMovement | Every movement must be traceable | Movement ID |

An entity does not have to be a physical object. Orders, payments, contracts, accounts, and bookings can all be business entities.

### 2.2. Identifiers Differ from Descriptive Attributes

Suppose a customer profile has a name, email, and phone number. Name is descriptive information, insufficient to distinguish two people. Email can serve as a business key if the store guarantees each email belongs to only one customer and policy forbids sharing; however, email can still change. A phone number can be changed, reassigned to someone else, or shared within a family.

An identifier should have these properties:

- Distinguishes instances within the defined scope.
- Remains stable throughout the tracked lifecycle.
- Avoids volatile meaning unless necessary.
- Has a clear uniqueness rule.

In a conceptual model, you only need to specify which identifier an entity has and its uniqueness scope. Choosing surrogate keys, integer types, or UUIDs is a logical/physical design decision.

### 2.3. Independent and Dependent Entities

Some entities can exist independently. For example, **Product** can be created before any order exists.

Some entities only make sense within the context of another entity. **OrderItem** is an example: a line item belongs to a specific order. Line number 1 only has meaning within a specific order; another order can also have line number 1. We can identify a line item by the pair of order number and line number.

Dependent entities typically have one or more of these traits:

- No business lifecycle separate from the parent entity.
- Identity depends partially or wholly on the parent entity.
- When the parent entity is cancelled, the child entity follows an associated rule.
- Its attributes only make sense in the parent's context.

However, not every table with a foreign key is a dependent entity. A **Payment** links to a **SalesOrder**, yet the payment transaction may need to be retained for reconciliation even when the order changes status. Dependency is a business decision, not just a technical detail.

### 2.4. When Does a Group of Attributes Become an Entity?

Consider a customer address:

- If the address is just a few fields used once when delivering an order, it can be a group of value attributes attached to the order.
- If the customer saves multiple addresses, names each address, picks a default address, edits, and reuses them, **CustomerAddress** has its own lifecycle and should be modeled as an entity.
- If the shipping address must remain frozen as of order placement, **DeliveryAddressSnapshot** is a historical value attached to the order. It does not necessarily have to reference the customer's current address record.

The same concept "address" can be modeled differently depending on how the business uses it. Ask: does it have its own identity, is it reused, who manages it, and are changes to it allowed to affect historical data?

## 3. Attribute: Information Describing an Entity or Relationship

Attributes answer the question "what do we need to know about this object?". For example, **Product** has SKU, name, description, and current price; **SalesOrder** has order number, placement timestamp, and status.

### 3.1. Identifying Attributes and Descriptive Attributes

- Identifying attributes participate in distinguishing an instance or a group of instances.
- Descriptive attributes provide information about an instance but are not necessarily unique.

Examples:

| Entity | Identifying Attribute | Descriptive Attributes |
|---|---|---|
| Product | SKU | Name, description, current price |
| Category | Slug/category code | Name, description, status |
| Warehouse | Warehouse code | Warehouse name, location |
| SalesOrder | Order number | Creation timestamp, status |
| Payment | Transaction ID | Amount, transaction type, status |

An entity can have multiple candidate keys. For instance, a product has an internal `product_id` and a business-facing SKU. At the conceptual level, document all meaningful identification rules first, then choose the primary key during logical design.

### 3.2. Simple and Composite Attributes

A simple attribute is a value treated as an indivisible unit within the modeling context, such as an SKU or a status.

A composite attribute can be broken into components with their own meaning. For example, a shipping address has recipient name, phone number, street address, ward/commune, city, and country. If the business needs to search or validate by component, the conceptual model should expose those components.

It is not always necessary to split a person's name into first, middle, and last name. Naming conventions vary across countries and cultures; only split them when there is a concrete business requirement such as sorting, salutation formatting, or system integration.

### 3.3. Single-Valued and Multi-Valued Attributes

A single-valued attribute has at most one value per instance at a given point in time. For example, an order has one order number.

A multi-valued attribute can hold multiple values. A customer can have multiple phone numbers or contact emails. You should not store them as a comma-separated string if the system needs to verify them, label them, prioritize them, or track effective dates.

When a multi-valued attribute carries its own data, consider modeling it as a child entity:

- **CustomerContact:** contact type, value, verified flag.
- **CustomerAddress:** address type, address details, default flag.
- **ProductCategory:** which category the product is assigned to, when assigned, whether it is the primary category.

### 3.4. Mandatory, Optional, and Conditional Attributes

A mandatory attribute must be present for every valid instance, such as the SKU of a product published for sale. An optional attribute may be unknown or not applicable, such as address line 2.

Distinguish among three states:

- **No value because not applicable:** e.g., an address has no second line.
- **Unknown:** e.g., customer's date of birth has not been provided yet.
- **Pending verification:** e.g., email has been entered but not yet verified.

If these states carry different business meanings, do not collapse all of them into a single blank/null value without accompanying rules.

Some attributes become mandatory only when a condition holds. For example, a tracking number is mandatory only after the order has been handed over to the carrier. Record that condition as a business rule, because a simple ER diagram may not express it completely.

### 3.5. Stored, Derived, and Historical Attributes

A derived attribute can be computed from other data:

- Age calculated from date of birth and current date.
- Order total calculated from line items, discounts, taxes, and fees.
- Available-to-sell quantity calculated as on-hand quantity minus reserved quantity.

A derived attribute may be stored to speed up reads or capture a value at a point in time. When storing it, define the source of truth and synchronization rules to avoid data drift.

Historical attributes change over time. A product's current price is a value as of now; the price applied to an order line item is a fact from a past transaction. A product name may change, yet the name printed on an old invoice should be preserved.

There are two common ways to model history:

1. Store a snapshot at the event, e.g., name and unit price inside **OrderItem**.
2. Store versions with effective date intervals, e.g., price history or customer tier history.

Which approach to choose depends on the question you need to answer: "What was the price on this order at purchase time?" differs from "What was the product's list price during each period?".

## 4. Relationship: How Entities Connect

A relationship expresses how one entity participates with one or more other entities according to business rules. Relationship names should be meaningful verbs or verb phrases.

Examples:

- Customer **places** SalesOrder.
- SalesOrder **contains** OrderItem.
- OrderItem **references** Product.
- Product **belongs to** Category.
- Warehouse **stores** Product.
- Payment **settles** SalesOrder.

A good model should make both reading directions clear. For instance, "customer places order" and "order is placed by customer" describe the same link while helping verify rules from both sides.

### 4.1. Cardinality and Optionality

Cardinality specifies how many instances on one side can link to one instance on the other side. Two questions must be answered:

- What is the minimum number of valid links?
- What is the maximum number of valid links?

Common notations:

| Notation | Meaning | Example |
|---|---|---|
| 0..1 | Zero or at most one | An order may not yet have a selected address while in draft status |
| 1..1 | Mandatory, exactly one | Every confirmed order belongs to one customer |
| 0..* | Zero or many | A customer may not have placed any orders yet |
| 1..* | At least one, possibly many | A confirmed order has at least one line item |

Do not just write "one-to-many". Write full statements for both sides:

- One customer can place **0 to many** orders.
- Each order must belong to **exactly one** customer.

Considering order lifecycle, a draft order may have zero line items; upon confirmation, it must have at least one line item. Thus, the `1..*` rule applies only in the confirmed state. The model should explicitly document this temporal/state condition rather than applying one static cardinality across all states.

### 4.2. One-to-One, One-to-Many, and Many-to-Many Relationships

**One-to-one (1:1)** occurs when each instance on either side links to at most one instance on the other side. For example, if every login account belongs to one customer profile and each profile has one login account, you can model a 1:1 relationship. Before splitting two concepts into two entities, ask whether they have independent lifecycles, access permissions, or data sources.

**One-to-many (1:N)**: one customer has many orders, while each order belongs to one customer. This is the most common pattern in transactional systems.

**Many-to-many (M:N)**: one product can belong to many categories and one category can contain many products. This relationship is typically implemented via an associative entity in the logical model.

Simple diagram:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : referenced_by
    PRODUCT ||--o{ PRODUCT_CATEGORY : classified_by
    CATEGORY ||--o{ PRODUCT_CATEGORY : includes
~~~

In the diagram above, **||** represents exactly one, **o{** represents zero or many, and **|{** represents one or many. Notation must be read alongside business rules; the diagram alone does not express conditions such as "one or many after the order is confirmed".

### 4.3. Recursive Relationships

An entity can link to itself. Categories have a parent–child relationship:

- A category may have no parent category if it is a root category.
- A parent category may have many child categories.
- Each child category has at most one parent if the category tree disallows multiple parents.

This is a one-to-many recursive relationship. When modeling it, assign clear role names such as **parent category** and **child category**, avoiding generic labels that leave readers unsure which side is the parent.

More complex recursive relationships can also be many-to-many. For instance, an employee mentors many other employees, and an employee can have many mentors.

### 4.4. Relationships with Attributes and Associative Entities

A relationship sometimes carries its own data. For example, since when a product has belonged to a category, who assigned it, or whether it is the primary category. Those facts do not describe Product or Category individually—they describe the assignment of the product to the category itself.

In that case, model the relationship as an associative entity **ProductCategory**:

| ProductCategory Attribute | Meaning |
|---|---|
| Product | Assigned product |
| Category | Category receiving the product |
| AssignedAt | Assignment timestamp |
| AssignedBy | Person or system performing the assignment |
| IsPrimary | Whether this is the primary category |

Similarly, **OrderItem** is the element of the "order contains product" relationship. This relationship carries quantity, unit price, discount, and line number. You cannot merely store an Order–Product link and lose the transaction-specific facts of that purchase.

Practical rule of thumb: if a many-to-many relationship has its own attributes, needs to be queried, has a lifecycle, or is referenced elsewhere, treat it as an associative entity.

### 4.5. Binary and Higher-Degree Relationships

Most business models use binary relationships between two entities. However, some rules involve three or more entities simultaneously.

Example: an employee counts the stock quantity of a product at a warehouse at a specific time. The stock count record involves three roles: **Employee**, **Product**, and **Warehouse**, along with the timestamp and counted quantity.

You can model this as a **StockCount** entity linked to employee, product, and warehouse. This is usually clearer to interpret when the business also needs count status, variance reason, or an approver.

Do not decompose a higher-degree relationship into multiple binary relationships if doing so loses the meaning of the original combined association.

## 5. Event: Something That Happened at a Point in Time

An event is a business fact that has occurred. It typically has a timestamp, actor, involved objects, and data describing the outcome.

Examples in the store:

- **CustomerRegistered:** customer registered.
- **OrderPlaced:** order submitted.
- **PaymentAuthorized:** payment authorized.
- **PaymentCaptured:** funds captured successfully.
- **StockReserved:** quantity reserved for an order.
- **ShipmentDispatched:** package handed over for shipping.
- **StockAdjusted:** warehouse quantity adjusted after a stock count.

An event typically contains these components:

| Component | Question to Answer | Example |
|---|---|---|
| Event identity | Which specific event instance? | `event_id` |
| Event type | What happened? | `PaymentCaptured` |
| Timestamp | When did it occur? | `occurred_at` |
| Actor | Who or which system performed it? | customer, employee, payment provider |
| Related objects | Who/what did the event affect? | `order_id`, `payment_id` |
| Event payload | What values were recorded? | amount, currency, quantity |
| Source and correlation | Where did it come from, and which flow does it belong to? | source, `correlation_id` |
| Deduplication | Could the same event arrive more than once? | `provider_event_id` or `idempotency_key` |

### 5.1. Long-Lived Relationships vs. Point-in-Time Events

"Customer places an order" can be viewed from two angles:

- The relationship **Customer places SalesOrder** tells us which customer the order belongs to. This link remains meaningful even after the order is delivered or cancelled.
- The event **OrderPlaced** records when the order submission occurred and with what data.

Relationships express structural links; events express occurrences. They complement one another.

Another example:

- **Payment** is an entity representing a payment transaction with an identity and lifecycle.
- **PaymentCaptured** is an event confirming that money has been collected.
- **SalesOrder.status** is the order's current state.
- **OrderStatusChanged** is an event or history record showing what state transitioned to what, when, and by whom.

If you only store current state, you can tell the order is **PAID**, but you cannot answer who confirmed it, when it was confirmed, what state it was in before, or how many failed payment attempts occurred.

### 5.2. Events Are Not Commands

A command asks the system to do something; an event records what has already happened.

| Command | Event After Successful Processing |
|---|---|
| PlaceOrder | OrderPlaced |
| CapturePayment | PaymentCaptured |
| ReserveStock | StockReserved |
| CancelOrder | OrderCancelled |
| DispatchShipment | ShipmentDispatched |

A command can be rejected due to insufficient stock, an invalid order, or declined payment. Do not emit a success event before business conditions have been confirmed.

This distinction keeps APIs, logs, and messaging systems unambiguous. **ReserveStockRequested** may be a request; **StockReserved** must reflect a successful stock reservation outcome.

### 5.3. State Is a Snapshot; Events Are History

An order can transition through states:

~~~mermaid
stateDiagram-v2
    [*] --> DRAFT
    DRAFT --> PENDING_PAYMENT: OrderPlaced
    PENDING_PAYMENT --> PAID: PaymentCaptured
    PENDING_PAYMENT --> CANCELLED: OrderCancelled
    PAID --> PROCESSING: FulfillmentStarted
    PROCESSING --> SHIPPED: ShipmentDispatched
    SHIPPED --> COMPLETED: DeliveryConfirmed
    PAID --> REFUNDED: RefundCompleted
~~~

The **status** column on the order gives the current state for fast application reads. The event log or status history table shows the path that occurred.

Valid state transitions must be defined. For instance, an order cannot jump directly from **DRAFT** to **SHIPPED** without confirmation and fulfillment steps. This rule should be captured in the business workflow and enforced at the appropriate execution layer.

### 5.4. Inventory: Balance Is State, Movements Are Events

Current quantity in a warehouse is a state. Every receipt, reservation, reservation release, shipment, or adjustment is an event/movement.

For example, product A in warehouse H has:

- On-hand quantity: 20.
- Reserved quantity: 3.
- Available-to-sell quantity: 17.

When an order reserves 2 more units:

- A **StockReserved** event records product A, warehouse H, the order, quantity 2, and the timestamp.
- On-hand quantity remains 20.
- Reserved quantity increases from 3 to 5.
- Available-to-sell quantity decreases from 17 to 15.

When the order is shipped, both on-hand quantity and reserved quantity decrease by 2. When the order is cancelled before shipping, reserved quantity decreases by 2 while on-hand quantity stays unchanged.

If you only update balances without recording movements, the system struggles to trace the cause of discrepancies. If you only record movements without an efficient way to read balances, recomputation can be expensive. Many systems store both current state and a movement ledger, with rules to update both consistently within the same transaction.

### 5.5. How Can Events Be Stored?

Not every system needs an event streaming platform or event sourcing. There are several levels:

1. **Timestamp attributes on entities:** `created_at`, `placed_at`, `paid_at`. Simple and suitable when only key milestone timestamps are needed.
2. **History tables:** `OrderStatusHistory`, `PaymentEvent`, `InventoryMovement`. Suitable when every change must be traceable.
3. **Event log or message stream:** records events for consumption by multiple services or analytics systems. Requires identity, ordering, retries, deduplication, and late-arriving data handling.
4. **Event sourcing:** events are the primary source of truth; current state is reconstructed by replaying events. Powerful for history, yet demands careful design for versioning, replay, snapshots, and error correction.

Storing events is not synonymous with event sourcing. A standard relational system can still maintain history tables and a transactional outbox without turning every operation into an event-sourced model.

## 6. Conceptual Model for the Online Store

We can combine all four concept types in one model. Entities and relationships describe business structure; event entities record significant occurrences.

~~~mermaid
erDiagram
    CUSTOMER ||--o{ CUSTOMER_ADDRESS : owns
    CUSTOMER ||--o{ SALES_ORDER : places
    SALES_ORDER ||--o{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : referenced_by
    PRODUCT ||--o{ PRODUCT_CATEGORY : classified_by
    CATEGORY ||--o{ PRODUCT_CATEGORY : includes
    CATEGORY o|--o{ CATEGORY : parent_of
    SALES_ORDER ||--o{ PAYMENT : has
    SALES_ORDER ||--o{ ORDER_EVENT : records
    PAYMENT ||--o{ PAYMENT_EVENT : records
    PRODUCT ||--o{ INVENTORY : stocked_as
    WAREHOUSE ||--o{ INVENTORY : stores
    PRODUCT ||--o{ INVENTORY_MOVEMENT : affected_by
    WAREHOUSE ||--o{ INVENTORY_MOVEMENT : records
    SALES_ORDER o|--o{ INVENTORY_MOVEMENT : may_cause
~~~

### 6.1. Classification of Each Component

| Component | Type | Key Attributes or Role |
|---|---|---|
| Customer | Entity | Customer ID, name, email, creation timestamp |
| CustomerAddress | Business-dependent entity | Recipient, phone number, address, address type |
| Product | Entity | SKU, name, current price, status |
| Category | Entity | Code, name, parent category |
| ProductCategory | Associative entity | Product, category, assignment timestamp, primary category flag |
| SalesOrder | Entity | Order number, customer, status, total amount |
| OrderItem | Dependent/detail entity | Product, quantity, snapshot price at purchase time |
| Payment | Transaction entity | Transaction ID, amount, provider, status |
| Warehouse | Entity | Warehouse code, name, location |
| Inventory | Stock state by product and warehouse | On-hand quantity, reserved quantity |
| OrderEvent | Event or history record | Event type, timestamp, actor, payload |
| PaymentEvent | Payment event | Provider event ID, type, timestamp |
| InventoryMovement | Warehouse event/movement | Product, warehouse, movement type, delta quantity |

Events can be modeled as entities when individual occurrences need identification and querying. The name **OrderEvent** in the diagram is a general concept; in a concrete system, you may use separate tables per event type or one event table with a discriminator column. That decision belongs to logical design.

### 6.2. Distinguishing Attributes from Entities in the Example

| Business Question | Reasonable Modeling Approach | Why |
|---|---|---|
| Does a product have a current price? | `current_price` attribute on Product | Current price describes the product |
| Does an order have the purchase price at placement time? | `unit_price_snapshot` attribute on OrderItem | It is a transaction fact of the line item |
| Does a customer have multiple saved addresses? | `CustomerAddress` entity | Each address can be managed and reused |
| Must an order preserve the delivery address at placement time? | Snapshot attribute group on SalesOrder | Order history does not depend on the customer's current address profile |
| Which categories is a product assigned to? | Product–Category relationship | It is a link between two entities |
| Does the assignment record timestamp and actor? | `ProductCategory` associative entity | The link carries its own data |
| What status is the order in right now? | Current status attribute | Reflects the current snapshot |
| How did the order change statuses? | Event / `OrderStatusHistory` table | Records each transition |
| How much stock is currently in the warehouse? | `Inventory` state | Current balance by product and warehouse |
| Why did the quantity change? | `InventoryMovement` | Records each receipt, reservation, release, shipment, or adjustment |

### 6.3. A Single Requirement Line Can Produce Multiple Components

Consider the requirement: "When a customer orders two units of product A, the system must reserve two units at the selected warehouse and record the reservation timestamp."

We break it down into:

1. **Entities:** Customer, SalesOrder, Product, Warehouse.
2. **Relationships:** Customer places SalesOrder; SalesOrder contains OrderItem; OrderItem references Product.
3. **Attributes:** `OrderItem.quantity = 2`; `OrderItem.unit_price_snapshot`; order placement timestamp.
4. **Event:** `StockReserved` with quantity 2, product A, selected warehouse, order, and timestamp.
5. **State:** `Inventory.reserved_quantity` increases by 2; available-to-sell quantity decreases by 2.

If you only add a `reserved = true` column on the product, you lose the quantity, warehouse, reserving order, and reservation/release history. A sound conceptual model catches missing information before designing tables.

## 7. How to Turn a Business Paragraph into a Model

An iterative workflow can be applied to each group of requirements.

### Step 1: Find Identifiable Objects

Read the text and mark concepts that must be managed over time. Ask:

- Are there multiple instances of the same kind?
- Do users need to open individual instances?
- Does it need to be referenced from elsewhere?
- Does it have its own state or history?

If yes, consider an entity.

### Step 2: Separate Descriptive Information

For each entity, list the facts to store. Label them as:

- Identifying vs. descriptive.
- Mandatory vs. optional.
- Single-valued vs. multi-valued.
- Derived vs. stored.
- Changing over time vs. historical snapshot.

Do not rush to pick data types or SQL column names. First understand what each fact means in the business.

### Step 3: Find Verbs and Identify Relationships

Verbs often suggest relationships: places, contains, belongs to, owns, pays, stores. Write relationship names in natural reading order and verify both sides.

Do not assume every verb is a table. "Customer places order" is typically a relationship; "when the order was placed" may be a timestamp attribute or an `OrderPlaced` event.

### Step 4: Record Min/Max on Both Sides

Do not stop at "one-to-many". Write:

- Each customer can place `0..*` orders.
- Each order must belong to exactly `1` customer.
- Each draft order can have `0..*` line items.
- Each confirmed order must have `1..*` line items.
- Each line item references exactly `1` product.

If cardinality varies by state or time, record that condition as a business rule.

### Step 5: Look for Relationship-Specific Data

If a link has quantity, price, role, start/end timestamps, or an actor, consider an associative entity. `OrderItem` and `ProductCategory` are classic examples.

### Step 6: Find What Has Happened

Phrases like "placed", "captured payment", "shipped", and "adjusted" often suggest events. For each event, ask:

- What is confirmed to have happened?
- When did it happen?
- Who or which system performed it?
- Which objects were affected?
- Can duplicate or late events arrive?
- Do before/after data or reasons need to be saved?

### Step 7: Write Rules Not Captured in the Diagram

An ER diagram cannot express every rule. Document conditions separately, such as:

- SKU must be unique.
- Order quantity must be greater than 0.
- A confirmed order must have at least one line item.
- Reserved quantity must not exceed on-hand quantity.
- A payment counts as successful only with valid confirmation.
- A webhook event must not be applied twice.

These rules will become constraints, transactions, application checks, or reconciliation processes in later steps.

## 8. Common Confusions and How to Fix Them

| Confusion | Consequence | How to Rethink It |
|---|---|---|
| Treating every noun as an entity | Too many tables, confusing model | Check identity and lifecycle |
| Treating a multi-valued attribute as a single string | Hard to verify, search, and attach metadata | Split into a child entity/relationship if needed |
| Treating many-to-many as a single ID column | Loses the ability to represent multiple links | Model M:N and an associative entity |
| Treating a relationship as an event | Blurs current association vs. individual occurrence | Separate relationship from event history |
| Storing only current state | Cannot trace history | Add events or history tables when needed |
| Storing events without identifying linked objects | Hard to trace origin and reconcile | Attach events to entities and sources |
| Turning every fact into an event | Harder operations, noisy data with no historical value | Record only business-meaningful events |
| Using name or email as an identifier without stability rules | Duplicates or changes break references | Define stable identity and uniqueness scope |
| Confusing associative entities with independent entities | Unclear lifecycle and ownership | Determine whether the link can exist independently |
| Drawing cardinality without conditions | State-dependent rules get missed | Record min/max and applicable conditions |

### Bad Example: Storing Order Products as a Text List

An order has a column `items = "A:2:500000,B:1:100000"`. This approach fails to give each line item a clear identity, makes it hard to check whether a product is still active, or how to update inventory per product. Moreover, multiple data types are packed into a single string.

A clearer way to model it:

- `SalesOrder` is an entity.
- `OrderItem` is a dependent detail entity.
- `SalesOrder contains OrderItem` is a 1:N relationship.
- `OrderItem references Product` is an N:1 relationship.
- `quantity` and `unit_price_snapshot` are attributes of `OrderItem`.

### Bad Example: Storing `status = PAID` and Deleting Previous Payments

This approach cannot answer which attempts failed, which transaction succeeded, whether a refund occurred, or which webhooks were processed. A better approach is keeping `Payment` as a transaction entity, storing current status, and recording `PaymentEvent` when auditing is required.

## 9. Validating the Model with Scenarios

After drawing the model, test it with business questions to see if it can answer them.

| Scenario | What the Model Must Show |
|---|---|
| A customer has three addresses | Which customer owns each address, and which address is default |
| A product belongs to multiple categories | Which categories link to the product and what metadata the link carries |
| An order has two lines for the same product | How the two lines are distinguished and whether they can have different prices/promotions |
| Customer edits address after ordering | Older orders still retain the shipping address at placement time |
| Customer attempts payment twice | Each attempt and outcome is identified individually |
| Provider sends a webhook twice | Duplicate event does not double-count collected money |
| Two orders reserve the last unit simultaneously | System can determine and record only one successful reservation |
| Staff adjusts inventory | Who adjusted, at which warehouse, which product, quantity delta, and reason |
| Order is cancelled after reserving stock | Release event is recorded and available balance is restored |
| Product changes name after purchase | Historical order line items still show the name captured at purchase time |

Test normal cases, edge cases, and failure cases. A model that only supports the happy path is rarely sufficient for a real system.

### Review Checklist

- Does every entity have a clear identifier and reason to exist?
- Does each attribute describe the right entity, or does it actually describe a relationship?
- Should any multi-valued attribute be extracted for independent management?
- Do relationships specify min/max and optionality on both sides?
- Do many-to-many relationships with their own data have an associative entity?
- Do events include timestamp, actor, affected objects, and required payload?
- Is current state distinguished from state transition history?
- Are rules depending on state or multiple entities documented separately?
- Can the model answer audit and reconciliation questions?

## 10. From Conceptual Model to Storage Models

A conceptual model captures business language and core rules. It is not tied to how a specific database engine stores data.

When moving to a relational model, map entities to tables, attributes to columns, relationships to foreign keys or junction tables, and events to history or event tables. Cardinality and uniqueness rules are implemented using keys and constraints.

When moving to a document database, certain entities and attributes may be embedded in the same document if they are frequently read/written together and share a compatible lifecycle. For example, `Order` may embed `OrderItem` and `DeliveryAddressSnapshot`; `Payment` and `InventoryMovement` typically have independent lifecycles and can reside in separate collections.

In a graph database, entities become nodes, relationships become edges, and attributes describe nodes or edges. This model is helpful when business queries traverse multi-hop links, such as frequently co-purchased products or networks linking customers and addresses.

In an analytical model, transaction events typically become facts with a clear grain, while descriptive entities become dimensions. For example, each order line item is a sales fact; Product, Customer, Category, and Date are dimensions. Payment events and inventory movements have their own grains and should not be arbitrarily merged into the same fact table.

| Conceptual Component | Relational | Document | Graph | Analytical |
|---|---|---|---|---|
| Entity | Table | Document or collection | Node | Dimension or object in fact |
| Attribute | Column | Field | Node/edge property | Dimension attribute or measure |
| Relationship | Foreign key / junction table | Reference or embedding | Edge | Foreign key in dimension/fact |
| Event | Event / history table | Event document | Timestamped node/edge | Event fact with defined grain |

Do not pick a storage model merely because the conceptual diagram has many relationships or many events. Choose based on workload, consistency requirements, query patterns, scale, history needs, and operational capabilities. The same conceptual model can be realized across multiple different physical models.

## 11. Short Practice Workflow

When receiving a new business requirement, build an initial classification table:

| Phrase in Requirement | Preliminary Classification | Verification Question |
|---|---|---|
| Customer | Entity | Does it have its own profile and identifier? |
| Customer email | Attribute or contact entity | Are there multiple emails, verification, and history? |
| Place order | Relationship and possibly event | Store just the link or also the placement timestamp? |
| Line item | Associative/detail entity | Does it have its own quantity, price, and promotions? |
| Belongs to category | Relationship | Can one product belong to multiple categories? |
| Payment succeeded | Event related to Payment entity | Which reference code, amount, and timestamp must be stored? |
| Inventory | State | Managed per product, warehouse, or batch? |
| Inventory adjustment | Event | Who adjusted, why, and by how much? |

Then:

1. Align on terminology with business owners. Terms like "customer", "account", or "buyer" may refer to different concepts.
2. Identify entities and identifiers.
3. Classify attributes by meaning, optionality, multiplicity, and history.
4. Draw relationships, labeling roles and min/max on both sides.
5. Extract relationships with their own data into associative entities.
6. Identify key events, timestamps, actors, and affected objects.
7. Document rules not fully expressible in the diagram.
8. Validate the model with real scenarios before moving to the logical schema.

Properly distinguishing entities, attributes, relationships, and events enables a data model to accurately represent the business. Entities tell us which objects to manage; attributes tell us what describes them; relationships tell us how they connect; events tell us what happened over time. When these four parts are clear, choosing keys, normalization, constraints, indexes, and storage models in subsequent steps rests on solid ground.
