# Grain: What One Object or Record Represents

In data modeling, **grain** describes precisely what a single object, event, or record represents in the business domain. When someone says "an order record", we must know whether that record represents the entire order, a line item within the order, a payment attempt, or a shipped package. These objects are related, yet they are not interchangeable.

Defining grain is a critical step in conceptual modeling. It helps the analysis team establish entity boundaries, attribute meanings, relationship multiplicities, and the level of detail the system needs to manage. In analytical modeling, grain also determines whether a row describes a transaction, a point-in-time state snapshot, or an aggregated result.

This lesson focuses on expressing grain in business language, testing grain with examples, and applying that result when building relational, document, graph, and analytical models.

**After this lesson, you will be able to:**

- Explain what a single instance or record represents.
- Distinguish the grain of entities, detail lines, events, state snapshots, and aggregated data.
- Write grain statements specific enough for business stakeholders to confirm.
- Recognize the mistake of mixing multiple grains inside the same data structure.
- Deduce relationship questions and identification needs from an agreed grain.

## 1. What Is Grain?

Grain answers the question:

> Which single business unit does one individual object or record in the model represent?

That unit must have a clear meaning within the system scope. For example:

- One **customer** represents one subject having a buying/selling relationship with the business.
- One **order** represents one purchase request created under the ordering workflow.
- One **order line** represents one selected item line and its specific sale terms within an order.
- One **payment attempt** represents one request by the system or user to process a payment.
- One **inventory snapshot** represents the stock quantity of one item at one location at a defined point in time.

Each statement above defines a different unit. If a team only says "the system stores orders and payments" without clarifying whether a payment record represents a payment settlement, an attempt, a capture, or a refund, the model will lack essential clarity.

You can think of grain like the zoom level of a map: a country-level map, a province-level map, and a street-level map all depict the same region yet answer different questions. Likewise, an order and its line items describe the same transaction at two different levels of detail.

### 1.1. Grain Is Not Just Data Volume

Grain does not merely mean "more data" or "less data". It defines **the meaning of one unit of data**.

For example, a table with 10,000 records might contain:

- 10,000 orders;
- 10,000 order lines;
- 10,000 payment attempts;
- or 10,000 inventory snapshots by item, location, and time.

The row count is identical, yet the business meaning is completely different. Therefore, you cannot determine grain simply by looking at row counts or table names.

### 1.2. Grain and Level of Detail

Within one business domain, multiple structures can exist at different levels of detail:

| Representation Level | One Unit Represents | Typical Questions Answered |
|---|---|---|
| Order | One purchase transaction | Which orders did the customer place? |
| Order line | One item line inside an order | Which items and quantities does this order contain? |
| Payment event | One occurrence of a payment action | Which payments or payment attempts occurred? |
| Inventory snapshot | One stock state at a point in time | At snapshot time, how much stock remained? |
| Daily sales summary | Sales result by day and chosen dimensions | What are sales by day, product, or store? |

An aggregated structure generally holds less detail than a transactional structure. During aggregation, some original details may no longer be recoverable. Thus, you must clearly establish which detail level is the source of truth and which level is derived for querying or reporting.

## 2. Distinguishing Grain Across Entities, Events, and Analytical Data

The word "record" is often used for many kinds of data. You must recognize whether a record describes an existing object, something that happened, or an observed state.

### 2.1. Entity Grain

An entity describes an object of interest to the business that must be distinguished from other objects.

Examples:

- One customer;
- One product;
- One order;
- One warehouse;
- One shipping method.

The grain statement should specify the condition under which an instance counts as a distinct object. For an order, that may be an order created after a customer confirms a purchase. For a product, the business must clarify whether the managed object is the general product or each sellable variant.

Not every noun in requirements becomes an entity. A phrase may denote a role, attribute, state, or event. Grain helps verify whether the concept under review has an independent unit of existence in the business.

### 2.2. Detail Line Grain

A header-level object often contains components at a finer grain. For example, an order has order lines.

- One order represents one purchase placement.
- One order line represents one line recorded in an order, with that line's item, quantity, and sale terms.

If an order has three line items, the model has one order object and three order line objects. Each line item must not be mistaken for an independent order.

Line-creation rules must also be verified. If a buyer adds the same SKU twice under two different prices or two different promotions, the system may keep two separate lines. Hence, stating "one line per product in the order" may not be accurate enough. A safer phrasing is "one line per line item recorded in the order under business line-creation rules".

### 2.3. Event Grain

An event records something that occurred, typically tied to a timestamp and an actor.

Examples:

- One customer order placement;
- One payment attempt;
- One order status transition;
- One parcel scan at a sorting hub;
- One inventory quantity adjustment.

One object can participate in many events. An order can undergo multiple status transitions; a payment can have multiple processing attempts depending on the workflow. If you only store the current state, the system may be unable to answer who changed the state, when it changed, and what the prior state was.

When modeling events, ask whether one record represents **each action occurrence**, each dispatched request, each confirmed outcome, or each state transition. These interpretations do not always match.

### 2.4. State Snapshot Grain

A state snapshot records the value of an object or set of objects at a point in time or period.

Examples:

- Inventory of an SKU at a warehouse at 08:00;
- Account balance at end of day;
- Number of pending orders at report cutoff time;
- Contract status on the last day of the month.

The grain statement must specify the observed unit and the time anchor. "One inventory record per day" is insufficient if the business has multiple warehouses, multiple SKUs, or multiple snapshots per day.

A more specific statement is: "One snapshot per SKU per warehouse at the daily inventory cutoff time." If the system captures multiple snapshots per day, the snapshot timestamp or snapshot run ID also belongs to the grain definition.

### 2.5. Aggregated Data Grain

Aggregated data combines multiple events or objects into one result across chosen dimensions.

Example: sales by day, store, and product. One record does not represent an individual order, but rather the aggregated result of all transactions belonging to that day, store, and product combination under the calculation rules.

Specify clearly:

- The dimensions used to group data;
- The time interval;
- Filtering conditions for including data in the aggregation;
- Metric calculation formulas;
- Rules for handling cancellations, refunds, adjustments, and late-arriving data.

If a dimension is dropped during aggregation, you cannot slice by that dimension again from the stored summary. For example, sales aggregated by day and store cannot automatically be broken down accurately by product if product detail was excluded from the grain.

## 3. Writing a Grain Statement

A good grain statement must be clear enough for two independent readers to understand the exact same business unit.

You can use this template:

> One record represents **[business unit]**, within the scope of **[object or process]**, at **[point in time or time interval, if applicable]**, under **[recording condition or distinguishing rule]**.

Examples:

- One order record represents one order created when a customer completes the purchase checkout action.
- One order line record represents one item line recorded inside an order, with that line's quantity and sale terms.
- One payment attempt record represents one payment processing request sent to a payment provider.
- One inventory snapshot record represents the quantity of one SKU at one warehouse at the inventory cutoff time.

For analytical data, you can use this template:

> One data row represents **[one event or state]** at the combination of **[dimensions]**, during **[point in time or period]**, after applying **[filtering and aggregation rules]**.

Example:

> One sales data row represents the revenue of one product at one store on one day, aggregated from order lines eligible for revenue recognition on that day.

### 3.1. Questions to Test the Statement

Once written, ask:

1. If another object or event of the same type occurs, under what condition does it create a separate record?
2. Can two records represent the same business object? If so, are they history, versions, or duplicate data?
3. What scope does the record belong to: a customer, an order, a line item, a location, or a period?
4. What point in time causes the record to be created, take effect, or end?
5. Do all described attributes apply cleanly to every record at this grain?
6. Which one-to-one, one-to-many, or many-to-many relationships follow from this definition?
7. By what business rule can one record be distinguished from another?

If the answers remain vague, the grain statement must be clarified with the business owner.

## 4. End-to-End Example: Defining Grain in a Sales System

Suppose a system needs to manage customers, orders, items, payments, and shipping. An initial description might say:

> Customers place orders containing multiple products. Customers pay for the order. The warehouse prepares the goods and ships them to the customer. The system stores inventory for staff to monitor.

This description does not yet define what a single record represents in each area. We must separate the business units.

### 4.1. Orders and Order Lines

Suppose a customer places an order consisting of:

| Order | Line | Item | Quantity |
|---|---:|---|---:|
| ORD-1001 | 1 | Keyboard | 1 |
| ORD-1001 | 2 | Mouse | 2 |
| ORD-1001 | 3 | Headset | 1 |

There are two grains:

- **Order:** one order created by one purchase placement. The order record holds header info such as buyer, creation timestamp, and order-level totals.
- **Order line:** one line recorded inside an order. The line record holds the item, quantity, and terms applicable to that line.

If everything is stored at the order level, the team struggles when an order has multiple items. If each line item is treated as an order, order counts and order-level revenue can be overcounted.

The conceptual relationship is usually one order having one or more order lines. However, the minimum condition and whether a draft order may have zero lines must be confirmed against actual business workflows.

### 4.2. Payments and Payment Attempts

An order can be paid across multiple processing steps. For example:

1. The customer submits a first payment request, but the bank declines it.
2. The customer retries, and the transaction is approved.
3. Later, the business issues a partial refund.

If "one payment record" means one attempt, the system can track both failed and successful attempts. If a record only represents collected funds, failed attempts do not belong to the same grain. Refunds may also be a distinct financial transaction type.

Verify these concepts:

| Concept | One Record Represents | Questions to Clarify |
|---|---|---|
| Payment request | One created processing request | Can one request be resubmitted multiple times? |
| Payment attempt | One submission or execution try | Does an attempt have its own system or provider ID? |
| Capture transaction | One amount actually settled/recorded | Is partial capture allowed? |
| Refund transaction | One amount refunded | Can one capture transaction have multiple refunds? |

The label "payment" can be used for the workflow, the request, and the transaction. Clarify the recorded unit before designing relationships.

### 4.3. Orders and Shipped Parcels

One order may be split into multiple parcels because items sit in different warehouses or ship in multiple waves. In that case:

- One order represents one purchase placement.
- One parcel or shipment represents one shipping unit handed over for delivery.
- One shipment line represents the portion of an order line's quantity allocated into a parcel.

If you assume "one order corresponds to one shipment", the model cannot represent multi-wave shipping. Conversely, if every barcode scan at a transit hub is treated as a parcel, the system confuses tracking events with the shipped object.

Distinguish **parcel/shipment** from **shipping event**. One parcel can have many scan or location-update events along its journey.

### 4.4. Inventory and Inventory Snapshots

Inventory can be managed by SKU, warehouse, storage bin, and timestamp. A record containing only SKU and quantity is insufficient if the same SKU exists across multiple warehouses.

Example statement:

> One inventory snapshot record represents the available quantity of one SKU at one warehouse at the end-of-day cutoff.

If bin-level tracking is needed, the grain must include storage bin. If multiple snapshots per day are needed, each capture must be distinguished. If receipts, issues, and adjustments are needed, that is the grain of an inventory movement event, distinct from a state snapshot.

### 4.5. Sales Aggregation

A report may ask for sales by day, store, and product. Grain statement:

> One record represents total sales of one product at one store on one business day.

The combination of day, store, and product defines the scope of one aggregated record. If the report needs slicing by sales channel or promotion, those dimensions must be preserved or backed by detail-level data for recomputation.

Do not mix order records, order line records, and aggregated sales records in the same dataset without clearly distinguishing type and grain.

## 5. Grain Determines Attribute Meaning and Relationships

Grain is the basis for checking whether an attribute belongs on the right object.

For instance, if the grain is **one order line**, attributes such as quantity, unit selling price at placement, and line discount make direct sense. If the grain is **one order**, total amount or placement timestamp belongs at the order level. Product name and current list price may belong to the product catalog, with their own change rules.

An attribute that seems clear at one level can become ambiguous at another:

- **Quantity:** quantity of one line item, or total quantity of the entire order?
- **Price:** current list price, locked price at placement, or post-discount price?
- **Status:** order status, individual line status, payment status, or delivery status?
- **Timestamp:** order creation time, payment time, delivery time, or revenue recognition time?

If an attribute has multiple values at the same grain, revisit the model or clarify the value set. For instance, an order has multiple products, so "product" is not a simple single-valued attribute of an order.

### 5.1. Grain and Relationship Multiplicity

From grain statements, you can derive cardinality questions:

- How many order lines can one order have?
- Into how many parcels can one order line be split?
- How many payment attempts can one order have?
- How many orders can one customer create?
- How many SKUs can one warehouse store?

Illustrative conceptual diagram:

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

The diagram illustrates only one common interpretation. Minimum cardinalities, line-splitting rules, partial payments, and multi-parcel shipping must still be confirmed. Grain helps you ask the right questions, though it does not replace confirming business rules.

## 6. Grain Across Data Model Paradigms

One business concept can be represented using different structures. Regardless of the storage model chosen, the meaning of a single instance or record must remain consistent.

| Model Paradigm | Grain to Clarify | Example |
|---|---|---|
| Relational | What one row of an entity or detail table represents | One order row; one order line row |
| Document | What one document represents as an aggregate or business object; what nested items represent | One document per order; line-item array has one element per order line |
| Graph | What type of object one node represents; whether one edge represents a relationship or an occurrence | `Order` node; `PLACED` edge representing customer placing order |
| Analytical | Which event, state, or dimension combination one fact row represents | One sales row per order line; one stock snapshot per SKU, warehouse, and day |

### 6.1. Relational Model

In a relational model, a table's grain is usually expressed by the meaning of one row. An `ORDER` table may have one row per order; `ORDER_LINE` has one row per line item.

A primary key is chosen to distinguish rows, yet **a key does not define the business meaning of the grain on its own**. A unique ID can make two rows technically distinct while still failing to tell whether they represent two events, two versions, or an accidentally duplicated entry.

Define grain first, then determine suitable identifiers and constraints.

### 6.2. Document Model

A document can represent an aggregate, such as an order along with its line items. In that case, the document's grain is one order, while each element in the line-item array has the grain of one order line.

Do not assume every array in a document shares the same grain or can be replaced by an unidentifiable set of values. If individual elements must be updated, queried, versioned, or referenced independently, their unit must be clearly understood.

### 6.3. Graph Model

In a graph, nodes carry the grain of the objects they represent; edges carry the grain of the represented relationship.

For instance, a `CUSTOMER` node represents one customer, an `ORDER` node represents one order, and a `PLACED` edge represents that the customer placed the order. If multiple interactions between the same two subjects must be retained, clarify whether the edge represents the current relationship or each individual occurrence. A time-bounded membership relationship may require validity attributes or an intermediate event node, depending on query and history needs.

### 6.4. Analytical Model

In an analytical model, the grain of an event or fact table must be stated before selecting metrics and dimensions.

Examples:

- Sales fact at the grain of one order line;
- Payment event fact at the grain of one attempt or one capture transaction;
- Inventory snapshot fact at the grain of one SKU, one warehouse, and one snapshot timestamp;
- Sales summary fact at the grain of one product, one store, and one day.

Different metric types aggregate differently. Sold quantity per order line can be summed over time under appropriate business rules; end-of-day inventory balances typically cannot be summed across multiple days to form "total inventory". Understand grain and metric additivity before designing reports.

## 7. Grain and Identification

After defining what one record represents, the next step is deciding how to distinguish two valid records.

Three concepts must be kept separate:

- **Grain:** which business unit a record represents.
- **Identifier:** how a specific instance is recognized.
- **Key:** attribute or set of attributes used in a storage model to reference or enforce uniqueness.

For example, order line grain may be "each line item recorded in an order". The identifier may be a line sequence number within the order or a dedicated line ID. Choosing a concrete key requires considering editability, integration, history, and technical constraints in the next design step.

Check questions:

- Is the identifier unique across the entire system or only within one order?
- Can a line be deleted and recreated with the same code?
- When an order is duplicated or imported from another system, is the identifier preserved?
- Must two occurrences of the same type for the same object be distinguished?
- Does the record need version history or effective dating?

Do not use an auto-increment ID to mask an undefined grain. Technical uniqueness does not guarantee that the model reflects business reality.

## 8. Time-Varying Grain and History

Some concepts need to store multiple changes over time. Distinguish among current records, historical versions, and change events.

For example, a customer can change addresses multiple times. There are at least three different interpretations:

- One customer record holding the current address;
- One address record per effective version;
- One event for each time the customer changes address.

These three options have different grains and answer different questions. If requirements only ask for the current address, storing every change may be unnecessary. If auditing or reconstructing historical orders is required, address history may need to be managed.

Similarly, current order status is not the same as status transition history. A current status record represents the condition at read time; a status transition history record represents one transition from a prior status to a new status.

When history requirements arise, ask whether the business wants to:

- Know the current value;
- Know the value at a past point in time;
- Know who changed it and when;
- Or reconstruct the entire chain of events leading to the current state.

Each goal may require a different grain and structure.

## 9. Process for Defining and Confirming Grain

You can use the following process during discovery and conceptual modeling sessions.

### Step 1: Pick the Concept or Process to Model

Start from a specific business requirement, such as ordering, payment, shipping, or inventory management. Note key verbs and nouns, without deciding yet that every noun is an entity.

### Step 2: Identify the Tracked Unit

Ask whether the system needs to distinguish each object, each occurrence, or each state. Does it require one record per customer, per order, per line item, per attempt, or per snapshot?

### Step 3: Describe the Instance Creation Condition

Identify the event or condition under which an object is considered to exist. For example, when is an order created: upon starting a cart, upon submitting a purchase request, or after system confirmation?

### Step 4: Define Scope and Time

Clarify which scope the object belongs to—whether it must be distinguished by warehouse, store, organization, channel, or time period. If data has history, define effective time and recording time.

### Step 5: Write a One-Sentence Grain Statement

Use a short sentence; avoid vague words like "a transaction", "a record", or "an item" unless the specific unit is explained.

### Step 6: Check Attributes and Relationships

Check whether each attribute has one clear value at the chosen grain. Determine how many other instances one instance relates to, and whether splitting, merging, or repetition can occur.

### Step 7: Test with Sample Data and Exceptions

Use realistic examples: multi-line orders, failed-then-retried payments, multi-parcel deliveries, multi-warehouse inventory, or the same product appearing multiple times in one order. If the statement cannot explain these cases, adjust or split the grain.

### Step 8: Confirm with the Business Owner

Read the statement and a few examples aloud to the accountable stakeholder. Confirm both normal cases and exceptions. Document the decision, confirming person, confirmation date, and open questions.

~~~mermaid
flowchart TD
    A["Business requirement or process"] --> B["Select concept to model"]
    B --> C["Identify object, event, or state"]
    C --> D["Describe what one instance represents"]
    D --> E["Define scope and time"]
    E --> F["Check attributes, relationships, and exceptions"]
    F --> G{"Confirmed by business?"}
    G -->|No| H["Log questions and refine statement"]
    H --> D
    G -->|Yes| I["Record agreed grain"]
    I --> J["Proceed to model identifiers and constraints"]
~~~

## 10. Common Mistakes When Defining Grain

1. **Using a table name instead of a grain statement:** the name `ORDER` does not tell whether one row is an order, an order line, or an order modification.
2. **Mixing header level and detail level:** storing line-level attributes alongside multiple lines in one structure without defining how individual lines are distinguished.
3. **Mixing events and states:** a state transition is an event; current state is the outcome after events.
4. **Mixing transactions and summaries:** a daily sales summary record does not represent an individual order.
5. **Ambiguous time descriptions:** "daily" could mean calendar day, business day, end-of-day cutoff, or a rolling 24-hour window.
6. **Assuming one object links to only one related object:** one order can ship in multiple parcels or have multiple payment attempts.
7. **Using a key as a substitute for business definition:** a unique ID does not explain what the record represents.
8. **Skipping exception testing:** a model works for trivial cases yet fails when orders have multiple lines, multiple payments, or partial shipments.
9. **Changing grain silently:** when a report switches from order level to order-line level, metrics and counts can change significantly.
10. **Summing non-additive metrics:** point-in-time balances and inventory generally cannot be summed across periods like transactional sales.

## 11. Pre-Signoff Conceptual Model Checklist

- [ ] Every important entity or record type has a grain statement.
- [ ] The statement specifies the business unit, scope, and time anchor if applicable.
- [ ] Objects, detail lines, events, snapshots, and aggregated data are clearly distinguished.
- [ ] The condition for creating an instance is defined.
- [ ] All attributes make sense at the chosen grain.
- [ ] Cases where one object links to multiple others have been checked.
- [ ] Repetition, splitting, multi-wave shipping, retries, and refunds have been tested if applicable.
- [ ] Analytical data grain explicitly names dimensions and aggregation periods.
- [ ] Technical keys are not used to paper over an ambiguous business definition.
- [ ] Business owners have confirmed, or remaining open questions are documented.

## 12. Practice Exercise

A sales system has the following requirements:

- A customer can create multiple orders.
- Each order can contain multiple product lines.
- A customer can attempt payment multiple times.
- An order can be delivered in multiple parcels.
- The system records stock quantities by product, warehouse, and daily cutoff time.
- Reports need sales by day, store, and product.

Write a grain statement for each of the following concepts or datasets:

1. Customer.
2. Order.
3. Order line.
4. Payment attempt.
5. Parcel.
6. Shipment line.
7. Inventory snapshot.
8. Aggregated sales record.

**Suggested Answers:**

| Concept | Reference Grain Statement |
|---|---|
| Customer | One instance represents one customer subject managed by the business within the sales scope. |
| Order | One instance represents one purchase placement recorded by the system under the ordering workflow. |
| Order line | One instance represents one item line recorded within an order under business line-creation rules. |
| Payment attempt | One instance represents one payment processing request submitted for an order or receivable. |
| Parcel | One instance represents one unit of goods packed and handed over as a single shipping unit. |
| Shipment line | One instance represents the portion of an order line's quantity allocated to a specific parcel. |
| Inventory snapshot | One instance represents the stock quantity of one product at one warehouse at the daily inventory cutoff. |
| Aggregated sales | One record represents the sales of one product at one store on one business day under agreed revenue recognition rules. |

The answers above are starting statements. In a real project, verify assumptions such as whether an order can contain duplicate product lines, whether one payment attempt can generate multiple transactions, whether a parcel can combine lines from multiple orders, and whether revenue is recognized by order date or transaction completion date.

**Target outcome:** every structure in the model has one clear unit meaning. Once grain is confirmed, the team can move forward to define identifiers, attributes, cardinalities, constraints, and suitable representations without confusing orders with line items, events, or summary metrics.
