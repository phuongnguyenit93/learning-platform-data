# Distinguishing Real-World Data, Business Concepts, and System Representations

## Lesson Objectives

After this lesson, you will be able to distinguish a real-world object or event from the business concept used to understand it and the record stored by software. You will learn why these three layers may not correspond one-to-one, how to transform real-world events into data with clear semantics, and how to verify whether a system representation preserves the necessary meaning.

## 1. Three Layers to Distinguish

When designing data, a common mistake is treating what exists in a table or JSON payload as if it were the real-world object itself. In reality, several steps of interpretation lie between the real world and a software record.

Three layers can be distinguished:

1. **Reality:** objects, people, organizations, actions, events, states, and phenomena that exist in the observed domain.
2. **Business concept:** how an organization interprets and names a part of reality according to its goals, rules, and language.
3. **System representation:** concrete data stored, transmitted, or processed in applications, databases, APIs, files, or reports.

These three layers are closely related, yet not identical. One real-world person may appear under multiple business roles; one business concept may be represented across multiple tables or documents; one record may aggregate information from multiple sources and points in time.

### Example: An Online Order

Consider a person purchasing two keyboards from an online store.

| Layer | What Is Being Referred To | Example |
|---|---|---|
| Reality | What actually happened | A shopper selects items, confirms the purchase, the payment system receives a request, and the carrier delivers the parcel |
| Business concept | How the store understands and manages the event | Customer, order, line item, payment attempt, shipment |
| System representation | Data structures used for recording | `customer`, `orders`, `order_items`, `payments` records, `OrderPlaced` event, and payload sent to the carrier |

The `orders` record is not the order itself in the sense of the entire real-world occurrence. It is a representation designed for the system to manage orders. It might omit shipping details, or store only the latest status while delivery history lives in another service.

If the development team treats a record as reality itself, they easily make flawed assumptions: deleting a record erases an event that occurred; changing the current status alters history; a customer ID equals a human identity; or one record corresponds to exactly one real-world object.

## 2. Reality: Objects, Events, and States

**Reality** is the scope of phenomena an organization wants to observe or manage. In a retail domain, reality may include people buying goods, products being traded, a payment transaction, a parcel being shipped, and the customer receiving the package.

Not everything in reality is recorded by the system. A system captures only the subset of information relevant to its purpose and authority. Therefore, data always has an observation scope and context.

### 2.1. Objects and Roles

One real-world person may act as the buyer, the recipient, the contact person, or the payer. These roles can belong to the same person or to different people.

For example, a company's purchasing employee may place an order for the company, have the goods delivered to a branch office, and have the invoice sent to the accounting department. If the model only has one `customer_name` field and one address, the system cannot accurately represent these roles.

When analyzing, distinguish:

- **Real-world entity:** an actual person or organization.
- **Role in a process:** buyer, recipient, approver, payer.
- **Account or system profile:** how the application identifies an actor for authentication or data management.

An account is not necessarily one person. One person can have multiple accounts; an organizational account can be shared across multiple employees according to permissions. You must determine business boundaries before choosing how to store them.

### 2.2. Events and States

An **event** is something that happened at a point in time or over a period of time, such as an order being created, a payment being declined, or a parcel being delivered.

A **state** describes the condition of an entity at a given moment, such as an order awaiting payment or being completed.

Events and states are related, but cannot replace each other. A current state can be derived from preceding events. If only the current state is stored, the system may be unable to answer why the order reached that state or which steps it went through.

Example:

```text
OrderCreated
    |
    v
PaymentRequested
    |
    +----> PaymentFailed
    |          |
    |          v
    |     PaymentRetried
    |          |
    |          v
    +------> PaymentSucceeded
                   |
                   v
              OrderConfirmed
```

This is an illustrative event sequence. The current state may be `CONFIRMED`, yet history still needs to retain both the failed payment attempt and the successful one. Whether to persist all events depends on auditing, traceability, and recovery requirements; whichever approach you choose, you must know which data is historical and which is merely current state.

### 2.3. Observations, Measurements, and Conditional Truth

A system rarely observes all of reality directly. It receives data through forms, sensors, external services, or human entry. That data is an **observation** or **measurement**.

For example, a sensor records a temperature of 28.4°C at 10:00. This value only carries meaning together with the measuring device, location, unit, timestamp, and precision. If only the number `28.4` is stored, a reader cannot tell whether it is temperature, humidity, or another metric.

An observation can also be wrong or incomplete. A user enters the wrong address; a sensor drifts; a partner service sends delayed data; two sources define a term differently. Hence, a model needs to consider the source, recording time, reliability, and how to handle changes in information.

## 3. Business Concepts: How the Organization Understands Reality

A **business concept** is how an organization partitions the world into objects, events, roles, and rules that are meaningful to its operations. Concepts enable different departments to speak the same language and decide how to handle situations.

A concept is not merely a word in a document. It requires a definition, scope, meaningful attributes, relationships with other concepts, and applicable rules.

### 3.1. Defining Terms and Conceptual Boundaries

Suppose a store uses the word "customer". It is necessary to clarify whether this concept means:

- an individual who has previously made a purchase;
- someone with an account on the website;
- an organization that signed a contract;
- the party responsible for payment;
- or a composite profile spanning multiple roles.

Each interpretation produces a different model. If the website allows guest checkout without registration, "buyer" and "user account" are clearly not the same concept.

A **business glossary** might record:

| Term | Definition | Distinctions to Note |
|---|---|---|
| Buyer | The actor initiating a purchase request | May differ from the recipient or payer |
| Account | A profile for authentication and system access control | Does not automatically map to a single person |
| Order | A purchase commitment/request accepted under store rules | Not synonymous with payment or delivery |
| Payment attempt | A single processing attempt to collect money for a payable amount | One order may have multiple attempts |
| Shipment | The process of delivering goods to an address or recipient | May consist of multiple parcels |

A glossary helps uncover homonyms or near-synonyms being used differently across sales, accounting, warehousing, and engineering.

### 3.2. Context-Dependent Attribute Meaning

An attribute only has meaning when you know what it describes and which concept it belongs to.

For instance, `created_at` might mean when a profile was created, when an order was received, or when a record was inserted into the database. These timestamps are not necessarily identical.

A technical field name is not enough to define business meaning. You should document:

- the attribute's definition;
- unit of measure or value domain;
- effective time;
- data source;
- mandatory or optional conditions;
- update and history retention rules.

### 3.3. Boundaries and Lifecycles

A business concept has its own lifecycle when it can be created, modified, completed, or cancelled under independent rules.

For example, an order and a payment are closely connected yet have distinct lifecycles. An order can exist before it is paid; a payment attempt can fail while the order remains valid; an order can be paid across multiple transactions.

Separating the two concepts allows the workflow to be represented accurately. Collapsing them into a simple status like `order_status = PAID` can lose information about retries, refunds, or partial payments.

## 4. System Representation: Data Is a Description

**Data representation** is how a system encodes a concept or observation into a form that can be stored, transmitted, and processed. A representation can be a row in a table, a JSON document, nodes and edges in a graph, a message on a queue, a CSV file, or a cell in a report.

A representation must retain enough meaning for its intended use. A representation can be syntactically valid yet semantically wrong.

For example, the value `100` is a valid number, but without knowing whether it means 100 VND, 100,000 VND, or 100 USD, it cannot be used correctly in business operations.

### 4.1. A Representation Is Not a Perfect Copy of Reality

Every system has limits on scope, precision, update timeliness, and structure. A customer record may store only a name and email; it does not describe the entire person.

A system can also produce derived data, such as an order total, a ranking score, or a status computed from events. Derived data is the result of calculation rules, not always a directly observed event.

When using derived data, clearly document:

- the formula or calculation rule;
- source data;
- calculation timing;
- how changes to source data are handled;
- whether the value is persisted or recomputed on each query.

### 4.2. One Concept Can Have Multiple Representations

The "order" concept can be represented in several ways within the same system:

- `orders`, `order_items`, and `payments` tables in a relational database;
- a JSON document for the order detail screen;
- an `OrderPlaced` message sent to the warehouse system;
- a row in a fact table for revenue aggregation;
- an `Order` node in a graph for tracing relationships.

These representations can serve different purposes and carry different amounts of information. They need mapping rules to avoid each place interpreting the "order" concept in incompatible ways.

### 4.3. One Representation Can Combine Multiple Concepts

An order document may embed the shipping address, line items, and recipient details. That does not mean all those parts are the same business concept. They are placed together because they are usually read or managed together.

Conversely, a single concept can span multiple records. Customer information may live across a customer table, an address table, a contact table, and an account table. You cannot look at just one table and conclude that the entire business concept resides there.

## 5. Mapping Between the Three Layers

**Mapping** describes how a business concept is translated into a concrete data structure and how data is interpreted back into business meaning.

A good mapping must explain the source, target, transformation rules, missing-data cases, and how conflicts between two sources are resolved.

### 5.1. Illustrative Mapping Table

| Reality or Observation | Business Concept | System Representation | Questions to Clarify |
|---|---|---|---|
| Someone places an order | Buyer | `buyer_id`, customer profile, or guest checkout info | Does the buyer need an account? |
| A purchase request is accepted | Order | `orders` or `Order` document | When is an order considered accepted? |
| Two products are ordered | Line item | `order_items` or `items` array | When are quantity and unit price locked in? |
| Payment provider returns a result | Payment attempt | `payments`, payment event | Is the external transaction ID unique? |
| Parcel reaches the recipient | Shipment | `shipments`, tracking event | Can one order be delivered in multiple parcels? |

A mapping table exposes gaps between the business and the data. If a question cannot be answered, the concept may not yet be defined or the representation may be insufficient.

### 5.2. Example: Turning a Requirement into Data

Requirement: "A customer can place many orders. Each order contains multiple products. Product prices can change, but past orders must preserve the exact price at the time of purchase."

**At the reality layer**, someone buys goods at a point in time, products are selected, quantities are confirmed, and a price is applied.

**At the business layer**, we define:

- `Customer`: the entity managed by the store as a customer.
- `Order`: an accepted purchase request.
- `Product`: an item offered for sale.
- `OrderItem`: a product along with its quantity and applied price within an order.

**At the representation layer**, a relational model may use:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY
);

CREATE TABLE products (
    product_id BIGINT PRIMARY KEY,
    current_price DECIMAL(12, 2) NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(12, 2) NOT NULL
);
```

In this design, `products.current_price` represents the current catalog price of the product; `order_items.unit_price` stores the price applied to the transaction. Both fields relate to "product price", yet they have different meanings and effective times.

If you only store `product_id` and always read the current price, order history will change whenever the catalog updates its price. If you store only a single price in the products table, you have collapsed two distinct temporal concepts into one value.

### 5.3. Do Not Assume a One-to-One Relationship

Relationships across reality, concepts, and representations are often many-to-many:

- One real-world person may have multiple accounts or profiles across systems.
- One customer concept may combine data from CRM, storefront, and support systems.
- One order may be represented in a transactional database, integration messages, and an analytical warehouse.
- One record may contain aggregated data from multiple events.

Therefore, when synchronizing data across systems, you need rules for identity resolution, merging, source precedence, and conflict resolution. Never assume that two records sharing the same name or email belong to the same entity.

## 6. Factors That Determine the Meaning of Data

Data is more than a raw value. Interpreting it correctly usually requires identifiers, context, time, units, and rules.

### 6.1. Identifiers and Identity

An **identifier** is a value used to reference an entity within a defined scope. Customer code `CUS-18` may be unique within the store system, but it is not globally unique across the world.

Distinguish between:

- **Identity:** which specific object is being referred to.
- **Identifier:** the value used to reference the object.
- **Database key:** a column or set of columns used to identify a row.
- **Business code:** a code meaningful to users or workflows.

One object can have multiple identifiers: an internal ID, a displayed customer code, an ID in a partner system. These can vary across scopes and over time. Determine which identifier is stable, who issues it, and which system owns its management.

### 6.2. Time and Validity

A value can change over time. At minimum, distinguish:

- **Event time:** when the real-world occurrence happened.
- **Recorded time:** when the system received or stored the information.
- **Valid time:** the time interval during which the value is considered true in the business domain.

For example, a customer moves to a new address on May 10, but the system only receives the update on May 12. Valid time and recorded time differ. If a historical report needs to know which address was in effect on May 11, storing only the latest update timestamp is not enough.

For timestamps, specify timezone, precision, and how date-only values are handled. Do not store time strings without conventions and assume every system interprets them identically.

### 6.3. Units and Value Domains

Measurements require units: kilograms, meters, seconds, degrees Celsius. Monetary amounts require currency and rounding rules. Ratios need clarity on whether they are expressed as percentages or decimals.

For example, `0.15` might mean 15% or 0.15%; `1000` might mean grams or kilograms. If the unit is not conveyed in the field name, schema, or data contract, systems can miscalculate without triggering any syntax error.

Use data types and value domains that make meaning explicit. For money, use exact decimal types or an appropriate monetary type along with a currency code; never use binary floating-point numbers for financial calculations requiring decimal precision.

### 6.4. Missing Data and Unknown States

A missing value can carry multiple meanings:

- not yet provided;
- not yet verified;
- not applicable;
- does not exist;
- hidden due to access permissions;
- not yet synchronized.

Do not use the same `NULL`, empty string, or `0` for all cases if the business needs to distinguish them. For example, "delivery date not yet known" differs from "order does not require delivery". Some cases require an explicit status or missing-data reason.

### 6.5. Provenance and Reliability

**Data provenance** tells you where data came from and how it was created or transformed. For example, an address may have been entered by the customer, confirmed by staff, or received from a delivery partner.

When multiple sources exist, define:

- which source is authoritative for each attribute;
- whether data is synchronized in real time or in batches;
- rules for selecting values when conflicts occur;
- how provenance and update timestamps are recorded;
- who has permission to modify the data.

No single source is always authoritative for every attribute. A CRM system may be the source of truth for contact details, while an invoicing system is the source of truth for the legal name on invoices.

## 7. Choosing a Representation Structure by Purpose

Only after understanding the business concepts should you decide on the physical representation. Each model type has different storage and query characteristics.

| Representation Type | How Concepts Are Expressed | Best Suited For |
|---|---|---|
| Relational | Tables, rows, columns, keys, and relationships | Transactions, integrity constraints, data with clear relationships |
| Document | Objects and nested data | Read/write by aggregate or records with flexible structure |
| Graph | Nodes, edges, and relationship properties | Multi-hop queries, networks, and paths |
| Analytical | Facts, dimensions, and grain | Aggregation, reporting, and dimensional comparisons |

Regardless of the structure chosen, business meaning must remain consistent. For example, `OrderPlaced` in an integration message and a row in `orders` may refer to the same order, yet their emission timing, state, and contents differ. Data contracts must define those differences precisely.

### 7.1. Data Contracts

A **data contract** describes the data structure and semantics that a provider commits to for its consumers. A contract can include:

- field names, data types, and formats;
- the business meaning of each field;
- required fields, optional fields, and validity conditions;
- units, timezones, encoding, and null conventions;
- identifiers and uniqueness rules;
- provenance, update frequency, and latency;
- compatibility policies for schema changes.

For example, an API returning `createdAt` must specify whether that is when the order was created in business terms or when the record was written to the database, what timezone format is used, and whether precision is in seconds or milliseconds.

A valid JSON schema only proves that a payload has the right structure. A good data contract must also ensure the consumer understands the exact meaning of each field.

## 8. Checking the Quality of a Representation

A representation can be evaluated across several dimensions:

- **Syntactic validity:** does the data conform to formats, types, and schemas?
- **Semantic validity:** does the value match its intended business meaning?
- **Completeness:** is all necessary information present for the intended use?
- **Consistency:** do related fields and sources agree without contradiction?
- **Accuracy:** does the data reflect verified observations or reality?
- **Timeliness:** is the data fresh enough for the decision being made?
- **Traceability:** can you determine the source, transformation rules, and history of the data?

For example, the date string `2026-13-40` is syntactically invalid. The string `2026-11-21` is syntactically valid, yet semantically wrong if the field requires a date of birth and the source data supplied an account creation date. A monetary amount with a valid decimal type but the wrong currency code is also invalid data.

### 8.1. Scenario-Based Validation

For every important concept, test scenarios such as:

1. **One entity with multiple roles:** buyer and recipient may be different people.
2. **One actor with multiple profiles:** the same organization appears in multiple systems under different codes.
3. **Changes over time:** address, price, or status changes; how must history be retained?
4. **Late-arriving events:** a delivery notification arrives after the system has already received a newer update.
5. **Conflicting sources:** two systems send two different addresses.
6. **Missing information:** not-applicable cases must be distinguished from unknown cases.
7. **Different units:** one source sends kilograms while another sends grams.
8. **Duplicate messages:** the same event is delivered multiple times; does the system create duplicate records?

If the model cannot explain these scenarios, revisit the concept definitions, mapping rules, or data contracts.

## 9. Common Mistakes

- **Equating records with real-world objects:** deleting or editing a record does not make a real-world event disappear. Clarify whether data represents current state, history, or a copy.
- **Equating accounts with people:** one person can have multiple accounts, while an organizational account can be used by multiple people.
- **Using one term for multiple concepts:** "customer", "user", "buyer", and "payer" must be defined per workflow.
- **Treating state as history:** current state does not explain the steps that occurred. Store events or history when the business requires traceability.
- **Storing numbers without units:** data may remain type-valid while being completely wrong in meaning.
- **Failing to distinguish event time from recorded time:** late updates can corrupt historical reports.
- **Assuming all sources are equally authoritative:** define source-of-truth rules per attribute.
- **Checking schemas only:** structurally valid data can still be semantically wrong, lack context, or be inconsistent.

## 10. Conclusion

Reality consists of the objects, events, and states an organization wants to observe. Business concepts are how the organization interprets and manages that slice of reality. System representations are the data structures created to store, transmit, and process information for a specific purpose.

Keeping these three layers distinct prevents confusing records with real-world objects, terminology with database structure, and syntactically valid data with semantically correct data. When designing, define concepts first, clarify rules and context, and only then choose representations and validate mappings.

## Self-Check

1. Why is an `orders` record not the entire real-world ordering event?
2. Distinguish between buyer, recipient, and user account using an example.
3. An order can have multiple failed and successful payment attempts. Why is the current state insufficient to describe the full history?
4. Why is the value `100` lacking sufficient meaning without a unit or currency code?
5. Distinguish between event time, recorded time, and valid time.
6. How can one business concept be represented across multiple system structures?
7. Pick a data field in a system you know and describe its definition, unit, source, valid time, missing-data rules, and how to validate its semantics.
