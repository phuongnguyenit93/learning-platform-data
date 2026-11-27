# What Is Data Modeling and What Problems Does It Solve?

## Lesson Objectives

After this lesson, you will be able to explain what data modeling is, recognize the problems that arise when a system lacks a clear data model, and describe how to turn a business requirement into meaningful data components. You will also understand why the same business domain can be represented using a relational, document, graph, or analytical model depending on how the system uses the data.

## 1. What Is Data Modeling?

**Data modeling** is the process of discovering, describing, and organizing the data of a business domain: what data needs to be stored, what each piece of data means, how pieces of data relate to one another, what rules must always hold true, and how the system needs to read or modify the data.

The output of this process is a **data model**. A model is a structured description of data and its rules. Depending on the level of detail, a model can take the form of a conceptual diagram, a logical model, a database schema, a data dictionary, constraints, or data contracts between software components.

You can think of a data model as answering six questions:

1. **What data exists?** For example: customers, orders, products, payments.
2. **What does the data mean?** For example: a "confirmed order" differs from a "paid order".
3. **How does the data relate?** A customer can have many orders; each line item belongs to one order.
4. **What must always be true?** The ordered quantity must be greater than 0; a line item must belong to a valid order.
5. **How does the data change over time?** A product's current price can change, but the price applied to a past order needs to be preserved.
6. **How does the system use the data?** Recording transactions, searching, tracing relationships, or aggregating reports all create different requirements.

Data modeling is not merely naming tables or choosing column types. It starts from understanding the business domain and ends with a structure clear enough for humans, applications, and databases to follow consistently.

### How Does a Data Model Differ from a Database Schema?

The two concepts are related, yet distinct:

- A **data model** describes the meaning, structure, relationships, and rules of data. It can be independent of any specific storage technology.
- A **database schema** is how the model is implemented in a specific database management system—such as tables, columns, data types, keys, indexes, and SQL constraints.

For example, the business specifies that an order belongs to a customer and has multiple line items. That is a rule in the model. When implemented in a relational database, that rule may be expressed using an `orders` table, an `order_items` table, foreign keys, and constraints. When implemented in a document database, an order may be stored as a single document containing an `items` array.

A good model can lead to different physical schemas. Conversely, a schema that runs without errors does not guarantee it accurately reflects the business domain.

## 2. Why Does a System Need a Data Model?

When a system is small, a development team sometimes stores data in whatever way is most convenient for the screen or code currently being written. This approach may work in the short term, but implicit assumptions accumulate. As new features, integrations, or reports are added, those assumptions begin to conflict.

Data modeling solves the following categories of problems.

### 2.1. Creating a Shared Understanding of the Business

A single word can carry multiple meanings if not clearly defined. "Customer" could mean the buyer, the recipient, the payer, or an organization with multiple accounts. "Revenue" could be calculated at the time of order placement, payment, or delivery completion.

A model helps the team align on concepts, definitions, and relationships. As a result, APIs, user interfaces, reports, and background services do not independently interpret the same concept in different ways.

For example, an e-commerce system needs to distinguish:

- `Order`: a recorded purchase request.
- `Payment`: an attempt or a record of payment for an order.
- `Shipment`: the delivery of part or all of the goods.
- `Customer`: the entity placing the order.

If all of these are collapsed into a single "order" object, the system will struggle to represent a failed payment followed by a retry, or an order delivered across multiple shipments.

### 2.2. Ensuring Correctness and Consistency

Data can go wrong in many ways: references to nonexistent records, negative quantities, duplicate identifiers, invalid states, or two copies of the same information holding different values.

The model identifies the rules that need to be protected. During implementation, those rules can be enforced using:

- primary keys and foreign keys;
- `NOT NULL`, `UNIQUE`, and `CHECK` constraints;
- data types and value domains;
- business logic inside transactions or domain services;
- validation at API boundaries and data contracts.

Not every rule can or should be enforced solely by a single database constraint. However, the model must state the rule clearly and identify which layer is responsible for enforcing it.

### 2.3. Reducing Redundancy and Avoiding Inconsistent Updates

Suppose a customer's name and address are copied into every order line item. When the customer changes their address, the system must decide whether to update all copies or keep the historical address. Without deliberate design, those copies easily drift out of sync.

A model helps distinguish what is source data, what is referenced data, what is a point-in-time snapshot, and what data is intentionally duplicated to serve queries. This is the foundation for applying normalization or controlled denormalization.

Note: **not all duplicated data is an error**. For example, the shipping address and unit price at the time of purchase often need to be stored as a snapshot inside the order. What matters is understanding the reason for duplication and defining the source of truth for each field.

### 2.4. Supporting Queries and Business Workflows

Data structure directly affects how applications query and update data. A good model helps answer key questions:

- Retrieve a customer's orders within a given time range?
- Find all products frequently bought together?
- Trace all accounts associated with a transaction?
- Aggregate sales by day, product, and region?

If data is designed solely around write operations, important queries can become overly complex or expensive. If it is optimized for only a single screen, other workflows may be forced to read excessive data or perform awkward joins.

Therefore, a model must consider both the data itself and how the data is used.

### 2.5. Enabling Safe System Evolution

Business requirements evolve: orders may allow split shipments, products may have variants, customers may have multiple addresses, or payments may support multiple providers. A clear model helps the team see which entities, relationships, rules, and historical data are affected by a change.

When the model and schema are intentional, adding fields, changing relationships, migrating data, and maintaining API compatibility become much easier to evaluate. A model does not eliminate the cost of change, but it surfaces the blast radius early and reduces hidden dependencies.

## 3. From Business Requirements to a Data Model

Consider the requirement: "Customers can order products. Each order has one or more line items. Selling prices can change over time. Customers can retry payment multiple times if the first attempt fails."

If you start immediately with table creation statements, you may miss important concepts. Instead, analyze it step by step.

### Step 1: Clarify Language and Scope

Ask specific questions:

- Is a "customer" an individual, a business, or both?
- Is an order created before payment occurs?
- Can an order have multiple payment attempts?
- Which price is used to calculate the total: the current price or the price at the time of ordering?
- Can an order exist without any line items?
- Does the system need to store state history or only the current state?

These questions turn a general description into verifiable rules. If an answer is not yet clear, document the assumption and who needs to confirm it rather than treating an assumption as fact.

### Step 2: Identify Entities and Values

An **entity** is a business object that needs to be identified and managed continuously, usually with its own identifier. In the example, this could include `Customer`, `Order`, `Product`, and `Payment`.

A **value** describes a characteristic or concept that does not necessarily have an independent identity lifecycle. For example, `Money` may consist of an amount and a currency; `ShippingAddress` may be a group of attributes representing the delivery address at the time of ordering.

Not every noun in a requirement needs to become a table or collection. A noun might simply be an attribute, a value, a role, or a term that needs clarification.

### Step 3: Define Attributes and Identifiers

Some attributes might be:

- `Customer`: customer ID, display name, contact email.
- `Product`: product ID, name, commercial status, current price.
- `Order`: order ID, ordering customer, creation timestamp, status.
- `OrderItem`: product, quantity, unit price at the time of ordering.
- `Payment`: order, amount, payment method, result, and processing timestamp.

Each entity needs a stable way to be identified. You can use a **natural key** if the value has business meaning and is truly stable, or a **surrogate key** such as an integer or UUID if you want an identifier independent of mutable attributes.

Email is usually not an ideal long-term identifier: users can change their email, or an email can be shared or recycled according to policy. Key selection must be based on domain rules, not merely on which field currently looks unique.

### Step 4: Describe Relationships and Cardinality

A **relationship** describes how entities connect to one another. For the example above:

- A customer can have 0 to many orders.
- Each order belongs to exactly one customer.
- An order has one or more line items once confirmed.
- Each line item references one product.
- An order can have multiple payments.

When describing a relationship, specify:

- **Cardinality:** one-to-one, one-to-many, or many-to-many.
- **Optionality:** whether the relationship is mandatory or optional.
- **Lifecycle:** whether an object can exist independently or depends on another object.

A many-to-many relationship often needs an associative entity when the relationship itself carries attributes. For example, the relationship between orders and products includes quantity, unit price, and discount; therefore, `OrderItem` is a useful business concept, not just a technical join table.

### Step 5: Write Down Invariant Rules

An **invariant** is a condition that must always hold true within the defined business scope. For example:

- The quantity of a line item must be a positive integer.
- The unit price at the time of ordering cannot be negative.
- Every line item must belong to an existing order.
- The total payment amount must follow the system's currency and rounding rules.
- Only permitted state transitions may occur.

Distinguish between a constraint on a single value and a state transition workflow. `CHECK (quantity > 0)` can protect quantity at the database level. However, a rule such as "a cancelled order cannot transition directly to delivered" typically needs to be enforced in state transition logic or an appropriate domain mechanism.

### Step 6: Identify How Data Is Read and Written

List key operations and queries before choosing a storage structure:

- Create an order together with its line items.
- View order details and payment history.
- Look up orders by customer or order ID.
- Aggregate sales by day and product.
- Find products that frequently appear in the same order.

The same data may require different access patterns. The model must support the primary workflows and preserve correctness rules under concurrent updates.

## 4. Three Levels of Data Modeling

In practice, teams typically move from a technology-independent model toward an implementable one.

| Level | Focuses On | Example Outputs |
|---|---|---|
| Conceptual model | Core business concepts and high-level relationships | Customer — Order — Product diagram |
| Logical model | Attributes, identifiers, relationships, cardinality, and rules | Entity descriptions, ERD, data dictionary |
| Physical model | Implementation on a specific technology | Tables/columns, documents, data types, keys, indexes, partitions |

The **conceptual model** helps domain experts and engineers align on scope. At this level, there is no need to decide whether a table uses `BIGINT` or `UUID`.

The **logical model** clarifies structure and rules without tying closely to a specific database management system. This is where attributes, keys, many-to-many relationships, mandatory constraints, and concepts that need separation are defined.

The **physical model** translates the design into an implementation structure. Only at this stage do you decide column types, foreign key syntax, indexes, partitioning, storage strategies, and DBMS-specific choices.

These three levels do not have to be three separate documents. For a small system, they can live in a single document; for a large system, separating levels makes managing change and communicating across teams much clearer.

## 5. Choosing the Right Data Representation

There is no single best database type for every problem. Choosing a model should be based on the nature of the data, consistency rules, query patterns, read/write volume, and evolution requirements.

### 5.1. Relational Model

The relational model organizes data into relations, typically implemented as tables of rows and columns. Tables link together via primary keys and foreign keys. SQL supports joins, constraints, and transactions.

Simple example:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    order_item_id BIGINT PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(12, 2) NOT NULL CHECK (unit_price >= 0)
);
```

The `order_items` table represents each line item as part of an order. `unit_price` is recorded at purchase time so that order history does not change when a product's current price is updated. In a complete system, `product_id` would also reference a products table, and the unit price would typically include a currency.

The relational model fits well when data has a clear structure, relationships between objects matter, and integrity constraints plus reliable transactions are required. Things to consider include handling flexible structures or deeply nested data, which may require many joins and careful table design.

### 5.2. Document Model

The document model stores an object along with its attributes and nested data, typically as JSON or a similar structure. A document can group data that is commonly read or updated together.

Example of an order document:

```json
{
  "orderId": "ORD-1042",
  "customerId": "CUS-18",
  "status": "CONFIRMED",
  "shippingAddress": {
    "recipient": "Nguyen An",
    "city": "Da Nang"
  },
  "items": [
    {
      "productId": "P-20",
      "productName": "Keyboard",
      "quantity": 2,
      "unitPrice": 850000,
      "currency": "VND"
    }
  ]
}
```

The shipping address and product name are captured inside the order to preserve context at the time of purchase. These details may differ from the current address or name in the customer profile and product catalog.

Documents fit well when data is usually accessed by aggregate or business object, structures may vary across record types, and reading the entire object is common. Considerations arise when many documents duplicate frequently changing information, when complex cross-entity queries are needed, or when updates across multiple documents require atomicity.

### 5.3. Graph Model

The graph model represents data using **nodes**, **edges**, and properties. Nodes represent entities; edges represent directed or undirected relationships between entities.

Example in an e-commerce system:

```text
(Customer: CUS-18)
       |
       | PLACED
       v
(Order: ORD-1042)
       |
       | CONTAINS {quantity: 2, unitPrice: 850000}
       v
(Product: P-20)
```

This structure is useful when questions focus on paths and relationship networks: which accounts a customer is connected to, which products are often bought together, or how many relationship hops separate one entity from another.

The graph model suits multi-hop relationship queries and data where the connections themselves carry significant meaning. If most queries simply fetch a record by key or aggregate large tables, a graph may not provide benefits that justify its operational and modeling overhead.

### 5.4. Analytical Model

The analytical model organizes data for aggregation, comparison, and analysis across dimensions such as time, product, customer, or region. A common design is the **star schema**, consisting of fact tables and dimension tables.

For example, a row in `FactSales` may represent one sold line item. This is the **grain** of the table. The fact table stores measures such as quantity and revenue; dimension tables describe dates, products, customers, and stores.

```text
                 DimDate
                    |
DimProduct -- FactSales -- DimCustomer
                    |
                 DimStore
```

This model supports questions like "revenue by month and product category" or "units sold by region". It is crucial to define the grain before selecting measures. If one row represents a line item, you cannot arbitrarily mix in order-level figures without handling the risk of double counting.

Analytical models typically receive data from transactional systems via ETL/ELT pipelines or data streams. They are optimized for reading and aggregating large volumes; they are generally not the right place for business applications to update order statuses directly.

### 5.5. Quick Comparison

| Model | Best Suited When | Strengths | Considerations |
|---|---|---|---|
| Relational | Transactions, clear relationships and constraints | Transactions, keys, constraints, join queries | Relationship design and joins; schema evolution requires management |
| Document | Read/write by object or aggregate | Nested data, flexible structure, document-level access | Duplicated data, cross-document updates, relational queries |
| Graph | Queries depend on multi-hop relationships | Natural representation and traversal of relationships | Operational model and tabular aggregation queries |
| Analytical | Reporting, aggregation, and historical analysis | Dimensional and measure queries over large datasets | Update pipelines, grain, latency, and consistency with source |

A single system can use multiple models for different purposes. For example, a relational database manages transactional orders, documents store certain flexible configurations, a graph supports relationship tracing, and an analytical warehouse serves reporting. When doing so, you must define the source of truth, synchronization mechanism, acceptable latency, and how discrepancies are handled.

## 6. Normalization, Denormalization, and Physical Choices

Once you have a logical structure, the team needs to decide how to organize the data physically.

**Normalization** decomposes data to reduce redundancy and prevent anomalies when inserting, updating, or deleting. For example, customer information is typically stored once in the `customers` table, while the `orders` table references it via `customer_id`.

**Denormalization** intentionally duplicates or pre-aggregates data to improve read performance, reduce joins, or serve a specific workload. For example, storing product names and unit prices inside order line items may be necessary to preserve transaction history, or a projection may store total sales to speed up reporting queries.

Both are deliberate design decisions. When denormalizing, you must answer: which data is the source of truth, when are copies updated, what happens if synchronization fails, and how are discrepancies detected?

At the physical level, you also need to consider:

- **Data types:** sufficient value range and precision; currency should not use floating-point numbers for calculations requiring decimal accuracy.
- **Keys and constraints:** protect uniqueness, referential integrity, and value domains.
- **Indexes:** support real queries; indexes speed up certain reads but consume storage and increase write costs.
- **Partitioning:** can help manage and query large datasets when the partition key aligns with the workload.
- **History and time:** determine whether to store current state, change events, or point-in-time snapshots.
- **Data protection:** classify sensitive data, restrict access permissions, and define retention periods.

Do not choose indexes, partitioning, or storage techniques just because they are popular. Base them on actual queries, measured data, and operational goals.

## 7. Validating a Data Model

A model that looks reasonable on a diagram can still fail when confronted with real-world scenarios. Validate it using concrete examples:

1. **Happy path:** a customer creates an order, adds two line items, and pays successfully.
2. **Failure path:** payment fails and the customer retries; the system records both attempts.
3. **Changes over time:** product price changes after an order is confirmed; order history still retains the original unit price.
4. **Edge cases:** a customer with no orders yet, an order with many line items, or a discontinued product.
5. **Concurrent updates:** two requests update inventory simultaneously or process the same order at the same time.
6. **Key queries:** find orders by customer, view order details, and aggregate monthly revenue.

For each scenario, check:

- Can the model represent all required data?
- Can every object be uniquely identified?
- Are mandatory relationships protected?
- Which rules are enforced in the database and which in the business layer?
- Can the data be queried at reasonable cost?
- When data changes, what history must be preserved?
- Can data be migrated and transformed as the schema evolves?

A model can be considered ready for implementation when core concepts and rules have been confirmed, key workflows are fully represented, and physical choices meet the expected workload. After deployment, continue observing queries, data errors, and business changes to refine the model.

## 8. Common Mistakes

- **Designing by screen:** creating a separate structure for each UI page causes the same concept to be stored in multiple ways. Start from the business domain and shared data flows.
- **Turning every noun into a table:** a noun may simply be an attribute or a value object. Extract an entity only when it has a distinct identity, lifecycle, or relationships that need separate management.
- **Choosing technology before understanding queries:** adopting document, graph, or relational databases simply because of trends can result in a model poorly suited to the workload.
- **Ignoring rules and history:** storing only the current state or current price can destroy the ability to explain a past transaction.
- **Using mutable identifiers as keys:** emails, names, or codes subject to reuse policies can cause referential issues when they change.
- **Denormalizing without a source of truth:** duplicating data without synchronization rules creates conflicting versions.
- **Skipping edge-case testing:** a model that only works with clean sample data can break on missing records, concurrent updates, or failed workflows.

## 9. Conclusion

Data modeling translates business understanding into meaningful data structures, clear relationships, and verifiable rules. It helps teams align on language, protect correctness, support queries, and control the cost of change.

A good model is not judged merely by the number of tables or the complexity of its diagram. Judge it by its ability to represent the business accurately, preserve necessary history, support critical data usage patterns, and evolve safely as requirements change.

## Self-Check

1. Why is a data model not synonymous with a database schema?
2. In the e-commerce example, why can `OrderItem` be a separate entity?
3. If a product's price changes, what data needs to be preserved to explain past orders?
4. When might a document model be a better fit than a relational model? When does a graph model offer an advantage?
5. Why should you define the grain before designing a fact table in an analytical model?
6. Pick a familiar business process and list its entities, attributes, relationships, invariants, and three key queries.
