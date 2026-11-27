# Trade-offs Between Correctness, Evolvability, Performance, and Complexity

A good data model helps a system store the exact facts the business needs to remember, query them within acceptable time, and adapt as workflows evolve. However, these four goals often pull design in different directions. Normalization reduces duplicate data and prevents conflicting updates, yet can require queries to perform more joins. Pre-computing aggregated data can speed up reads, yet introduces synchronization responsibilities. A highly flexible schema can accept varied data shapes, yet makes validation and comprehension harder.

Within **data modeling**, the designer's job is to translate business requirements into entities, relationships, attributes, keys, constraints, and storage structures. A model must express data meaning accurately, support key operations, and offer a clear evolution path. No single structure is universally optimal for every system; sound choices depend on business invariants, query patterns, rate of change, and the team's operational capability.

This lesson uses an e-commerce order system as a running example to examine how to balance correctness, evolvability, performance, and complexity, while comparing relational, document, graph, and analytical models.

## 1. Four Goals to Balance

| Goal | Question to Answer | Signs of Good Design |
|---|---|---|
| Correctness | Does the data accurately reflect reality and business rules? | Invariants are explicit; invalid data is blocked; transactions preserve consistency |
| Evolvability | When the business changes, can the model evolve without breaking existing data and systems? | Clear data boundaries; changes can roll out incrementally; history keeps its accurate meaning |
| Performance | Do key operations meet desired latency, throughput, and resource costs? | Queries match access patterns; indexes are purposeful; measurements confirm bottlenecks |
| Complexity | Can the team understand, test, deploy, and operate this structure? | Few implicit rules; an identifiable single source of truth; explainable sync and recovery mechanisms |

These goals interact with one another. Correctness is foundational: a fast query returning the wrong price is still a bug. Evolvability lets the system survive across multiple business iterations. Performance determines whether the system handles real-world load. Complexity limits how many mechanisms the team can safely maintain.

Balancing does not mean splitting priorities equally. In a payment system, correctness and auditability usually outweigh shaving off a few milliseconds. In a product recommendation system, some staleness in updates may be acceptable in exchange for fast reads. For a low-traffic internal tool, a simple query may be far better than adding a caching layer and sync pipeline.

## 2. Starting from Business Rules

Designing a schema by listing tables first often leads to modeling by technological habit. Begin by asking what the system needs to remember, who owns that data, when it changes, and which conditions must always hold true.

For an e-commerce system, some rules might be:

- A customer can create many orders; each order belongs to exactly one customer.
- An order must have at least one line item before being confirmed.
- The quantity of a line item must be a positive integer.
- The unit price at purchase time must be preserved, even when the product's current price changes.
- Each order uses a single defined currency; never sum amounts in different currencies without conversion.
- A paid order cannot be silently altered into a different transaction.
- Two concurrent requests must not drive inventory quantity below zero.

These statements carry more design information than table names. They reveal entities, relationships, lifecycles, historical data, and constraints. They also distinguish current state from data locked in at a point in time.

### 2.1. From Concepts to Schema

Distinguish three modeling levels:

1. **Conceptual model** describes business concepts and their relationships, independent of any DBMS.
2. **Logical model** defines attributes, keys, relationships, cardinalities, and data rules. Normalization and aggregate boundaries can be decided here.
3. **Physical model** selects data types, indexes, partitioning, storage layouts, and implementation details tailored to a specific DBMS.

Do not push physical decisions prematurely into the conceptual model. For example, the business has an "order" concept regardless of whether data is eventually stored across relational tables or inside a document. Conversely, a sound logical model still needs physical adjustments once real load and query metrics arrive.

### 2.2. Entities, Relationships, and Lifecycles

A simple conceptual diagram can be represented as follows:

~~~mermaid
erDiagram
    CUSTOMER ||--o{ ORDER : places
    ORDER ||--|{ ORDER_ITEM : contains
    PRODUCT ||--o{ ORDER_ITEM : referenced_by
    CUSTOMER {
        bigint customer_id
        string email
    }
    ORDER {
        bigint order_id
        bigint customer_id
        string status
        datetime created_at
    }
    ORDER_ITEM {
        bigint order_id
        int line_no
        bigint product_id
        int quantity
        decimal unit_price_snapshot
    }
    PRODUCT {
        bigint product_id
        string sku
        decimal current_price
    }
~~~

Order and line item have a one-to-many relationship. A line item has no independent meaning outside an order, so its key can combine the order ID and line sequence number. A product can be referenced by many line items, yet its name and price at order time must be captured inside the line item so order history does not change alongside the current product catalog.

Cardinality must be derived from business rules. Do not set a one-to-one limit just because the current UI accepts only one address. Even if customers can store multiple addresses in the future, the chosen shipping address must still be captured as a historical snapshot on the order; addresses in the customer profile are mutable data.

## 3. Protecting Correctness Through Data Structure

Correctness should not rely solely on promises in application code. Every rule should live in a layer that has sufficient information and can enforce it across all write paths.

### 3.1. Keys and Constraints

Common constraints play distinct roles:

- **Primary key** uniquely identifies a record and cannot be null.
- **Foreign key** protects referential integrity, preventing records from pointing to nonexistent objects.
- **Unique constraint** prevents two records from sharing the same candidate key value, such as a normalized login email.
- **Not null** requires an attribute to have a value.
- **Check constraint** validates a condition within a row, such as quantity being greater than zero.

For example, a relational database can express part of an order's rules in SQL:

~~~sql
CREATE TABLE customers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE
);

CREATE TABLE products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    current_price NUMERIC(14, 2) NOT NULL
        CHECK (current_price >= 0),
    stock_quantity INTEGER NOT NULL DEFAULT 0
        CHECK (stock_quantity >= 0)
);

CREATE TABLE orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES customers(id) ON DELETE RESTRICT,
    status TEXT NOT NULL
        CHECK (status IN ('draft', 'confirmed', 'paid', 'cancelled')),
    currency CHAR(3) NOT NULL,
    grand_total NUMERIC(14, 2) NOT NULL
        CHECK (grand_total >= 0),
    ship_to_name TEXT NOT NULL,
    ship_to_address TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_items (
    order_id BIGINT NOT NULL
        REFERENCES orders(id) ON DELETE RESTRICT,
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    product_id BIGINT
        REFERENCES products(id) ON DELETE RESTRICT,
    product_name_snapshot TEXT NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_snapshot NUMERIC(14, 2) NOT NULL
        CHECK (unit_price_snapshot >= 0),
    PRIMARY KEY (order_id, line_no)
);
~~~

This example uses a two-decimal monetary type for readability. Multi-currency systems must explicitly specify decimal places, rounding rules, and how amounts are stored per currency; never assume every currency shares the same minor unit.

Surrogate primary keys such as auto-incrementing integers keep relationships stable when business attributes change. Natural keys like email or SKU may still need unique constraints, yet do not have to serve as foreign-key targets. If an email changes, the customer key does not need to change with it.

Composite keys also carry business meaning. Here, `(order_id, line_no)` identifies a line within an order's scope. This key clearly expresses the uniqueness scope and automatically creates an index leading with `order_id` in many DBMSs.

### 3.2. Constraints Must Be Placed in the Right Layer

A check constraint typically validates attributes of a single row. It cannot automatically enforce a rule requiring comparison across multiple rows or tables—such as order total equaling the sum of line items plus taxes and fees. Cross-row rules require transactional design, appropriate locking, triggers when truly warranted, or a reconcilable ledger model.

Critical rules must withstand concurrent writes. For example, if two customers simultaneously buy the last remaining unit of a product, reading stock and deducting in two separate steps can let both requests see a quantity of one. Use a conditional update in a single atomic statement:

~~~sql
UPDATE products
SET stock_quantity = stock_quantity - :requested_quantity
WHERE id = :product_id
  AND stock_quantity >= :requested_quantity;
~~~

The application checks the affected row count. If zero, either the product does not exist or inventory is insufficient. Checking and deducting happen together, avoiding any gap between read and write. For multi-step workflows, wrap related operations in a transaction and choose an appropriate isolation level or locking strategy.

A unique constraint is also the final barrier against two concurrent requests creating the same account. Running a pre-check `SELECT` in application code is insufficient because two requests can both see no existing row and then both insert. The database must enforce uniqueness.

### 3.3. NULL and Data Semantics

`NULL` signifies a missing or unknown value, not an empty string, zero, or "not applicable." Each attribute needs clear rules: whether it is required, when it lacks a value, and what a missing value means.

`NULL` also affects comparisons and constraints. In SQL, comparisons against `NULL` typically evaluate to `UNKNOWN`; you must use `IS NULL` or `IS NOT NULL`. How `UNIQUE` behaves with multiple `NULL` values can depend on the DBMS and configuration. Therefore, uniqueness rules for missing data must be verified against the target DBMS.

Do not overload one field with multiple meanings. For instance, using an empty string to represent "not yet shipped", "customer did not provide", and "no shipping needed" forces queries and reports to guess intent. A dedicated status or clearer structure may be needed.

## 4. Normalization and Denormalization

Normalization organizes data to reduce duplication and prevent insert, update, and delete anomalies. It is a useful starting point for relational modeling.

Suppose every line item stored customer email, product name, customer address, and current product price. When an email changes, many historical rows would have to be updated. If a product has never been ordered, there is no suitable place to store its details in the order table. When deleting the last line item referencing a product, product data could accidentally vanish. These anomalies stem from mixing multiple concepts into one structure.

Common normal forms:

- **1NF**: each cell holds a single value within its defined domain; do not stuff unstructured lists into a column to substitute for a relationship.
- **2NF**: non-key attributes depend fully on the entire candidate key, especially important when keys are composite.
- **3NF**: non-key attributes have no transitive dependency on the key through another non-key attribute.

For example, product name and current price belong to the product, not to individual line items. They belong in the product entity. However, the product name and price applied at purchase time are a distinct historical fact; storing a snapshot in the line item is not meaningless duplication. The two fields have different semantics and lifecycles.

### 4.1. When Should You Denormalize?

Denormalization is intentionally storing additional data that could be derived elsewhere to serve an important access pattern. Examples include:

- Storing the locked-in `grand_total` on an order for fast display and reconciliation.
- Storing an order count on a customer profile to avoid repeated aggregation on a high-read screen.
- Storing a copy of a name or address at transaction time to preserve history.
- Embedding items frequently read together into a single document to reduce query round-trips.

Every copy raises a question: when the source data changes, must the copy change too? If yes, who updates it, is it updated in the same transaction or asynchronously, how are failed updates handled, and how is drift detected?

Not every copy needs synchronization. Historical snapshots intentionally keep old values after source data changes. A locked-in grand total is also part of the order event and should not necessarily be recalculated from current product prices. By contrast, an order count displayed on a customer profile is derived data that can be rebuilt from orders; if stored, you must define how it is updated and reconciled.

A helpful rule is explicit classification:

| Data Category | Example | Update Rule |
|---|---|---|
| Current authoritative data | Product catalog price | Updated along the product lifecycle |
| Historical snapshot | Unit price on a confirmed order | Preserved as recorded for the past event |
| Derived data | Total order count for a customer | Recomputable; if persisted, requires sync or reconciliation |
| Temporary cache | Popular query results | Can expire and regenerate under clear policies |

Denormalization is justified when access gains are measured or business rules require a snapshot. If you do not yet know which queries are slow, start with a clear, reasonably normalized model and add optimizations after measuring.

## 5. Performance Starts with Access Patterns

Performance is not merely table count or number of `JOIN`s. A multi-table model can still be fast with proper indexes and queries. A large document can be slow when forced to read unused payload or frequently update a small nested portion.

Before optimizing, identify:

- What are the primary queries: lookup by ID, filter by status, view history, aggregate, or traverse relationships?
- What are the read and write frequencies of each operation?
- Does data grow evenly or cluster around hot keys?
- What are the target latency and concurrency levels?
- Which data requires immediate consistency, and which tolerates delayed updates?

### 5.1. Indexes Are a Trade-Off

Indexes locate rows without full table scans, yet consume storage space and must be updated whenever data changes. Too many indexes raise write costs, lengthen maintenance, and can make it harder for the query optimizer to pick good plans.

For instance, if a screen frequently shows a customer's newest orders, a composite index by customer then creation time can support the query:

~~~sql
CREATE INDEX idx_orders_customer_created
ON orders (customer_id, created_at DESC);
~~~

Column order in a composite index matters. An index leading with `customer_id` fits queries filtering by `customer_id` and sorting by `created_at`. It is not necessarily optimal for queries filtering solely by `created_at`. Design indexes from actual filter predicates, sort orders, and returned columns.

Not every column deserves an index. Low-cardinality columns rarely help on their own; heavily updated columns inflate index maintenance overhead. Unique indexes serve double duty by both accelerating lookups and enforcing a business rule.

Foreign keys do not always create indexes automatically on the referencing table. If the application regularly searches line items by `product_id`, or deletes/checks whether a product has referencing line items, a dedicated index on `order_items(product_id)` may be needed. Verify the exact behavior of your DBMS.

Measure execution plans using tools like `EXPLAIN` or `EXPLAIN ANALYZE` against realistic data sizes. A query that runs quickly on a few hundred rows can become a bottleneck at tens of millions of rows. Never judge performance on intuition or tiny test datasets.

### 5.2. Optimizing Reads and Writes

If a workload is read-heavy and write-light, extra read replicas or indexes may pay off. If data is updated constantly, maintaining extra copies and indexes may cost more than the read benefit.

Splitting one document into separate entities can shrink update payloads and reduce contention when multiple processes update different parts. Conversely, grouping data belonging to one aggregate can reduce read round-trips and simplify atomic operations.

Caching is also a form of denormalization at the access layer. Caching lowers read load but introduces expiration, invalidation, stale reads, and cache-miss handling. Never use caching to mask an unclear data model before identifying real bottlenecks.

## 6. Designing for Change

Business domains evolve over time: orders may gain promo codes, multiple shipping addresses, new payment methods, or new tax rules. Evolvability depends on whether the model clearly separates concepts, preserves history, and allows phased rollouts.

### 6.1. Avoid Models That Are Too Rigid or Too Unstructured

One table with dozens of nullable columns for every object variant creates many invalid states. One unstructured JSON column holding every attribute makes validation, indexing, and relationship analysis difficult. At the other extreme, breaking every attribute into generic key-value tables complicates queries and sacrifices type constraints.

Use explicit types and relationships for stable concepts that carry business meaning or require frequent querying and constraints. Use JSON/documents for extensible sections whose shape varies across record types, while defining minimum schemas, validation rules, and indexing for queried fields.

Do not overload a single status column with too many meanings. If a workflow has valid state transitions, define a state machine: which states can transition to which, under what conditions, and whether transition history must be saved. A list of allowed values in a `CHECK` constraint only blocks unknown values; it does not enforce valid transition sequences.

### 6.2. Multi-Step Schema Changes

Changing a column actively used by applications often requires coordinating application versions, database structures, and legacy data. A common strategy is **expand–migrate–contract**:

1. **Expand**: add new structures compatibly, such as adding a nullable column or a new table.
2. **Migrate**: deploy applications able to read/write during the transition; backfill legacy data in batches; check counts and discrepancies.
3. **Switch**: shift primary reads to the new structure once data is ready.
4. **Contract**: in a later release, deprecate and then drop old columns or paths once no application version depends on them.

For example, splitting `full_name` into `first_name` and `last_name` should not immediately drop `full_name` while older application versions still read it. Add the two new columns, backfill, update applications, verify, and only then drop the old field.

On large tables, migrations also risk table locks, I/O spikes, or large data copies. Consider low-locking index creation if supported by your DBMS, batch backfills, monitoring replication lag, and having safe pause/resume plans.

### 6.3. History and Time

Not every attribute carries the same meaning across time. A product's current price can change; the price applied to an old order must stay intact. A customer's profile address can change; the shipping address of a dispatched order must reflect where it was delivered. That is why current state and historical snapshots must be kept distinct.

If the business needs to know who changed what and when, storing only the latest value is insufficient. Add history tables, event logs, or audit logs recording actor, timestamp, before/after values, and reason. Choose storage mechanisms based on querying and audit needs; do not turn every table into event sourcing if the system does not need full event replay.

## 7. Choosing a Model Family by Data Nature

Relational, document, graph, and analytical models address different access patterns. You can combine multiple models within one system, provided every data copy has a clear purpose and source of truth.

| Model | Best Suited When | Strengths | Costs and Limits to Consider |
|---|---|---|---|
| Relational | Well-structured data, rich relationships and constraints; consistent transactions needed | Keys, foreign keys, transactions, and flexible joins | Requires join design, indexes, and migrations; structural changes need coordination |
| Document | Data is typically read/written as a nested aggregate | Groups co-accessed data; flexible schema for extensions | Nested data can duplicate; large updates and cross-document relations require careful design |
| Graph | Relationships are central and multi-hop or varied link traversals are needed | Natural representation of nodes, edges, and paths | Tabular aggregations and reports can be awkward; must manage edge types and traversal bounds |
| Analytical | Large-scale historical aggregations by time, product, region, or segment | Optimized for scans and aggregations; fact/dimension layout aids reporting | Typically derived from operational systems; updates may lag and require ingestion/reconciliation pipelines |

### 7.1. Relational Model

The relational model fits well when integrity across multiple entities is crucial. Orders, customers, products, payments, and inventory typically have clear relationships and require transactions. Separating tables keeps each fact managed in one place, while foreign keys and unique constraints protect relationships.

Practical drawbacks usually come from query and operational design: excessive `JOIN`s, poorly chosen indexes, heavy migrations, or long-running transactions holding locks. These are issues to measure and tune for the workload, not automatic reasons to abandon the relational model.

### 7.2. Document Model

If an order is routinely read alongside all its line items and shipping address, it can be stored as a document:

~~~json
{
  "orderId": "O-1042",
  "customerId": "C-18",
  "status": "paid",
  "currency": "VND",
  "grandTotal": 1250000,
  "shipTo": {
    "name": "Nguyen Van A",
    "address": "12 Example Street"
  },
  "items": [
    {
      "productId": "P-7",
      "productName": "Keyboard",
      "quantity": 1,
      "unitPrice": 1250000
    }
  ]
}
~~~

Line items live inside the document because they belong to the order lifecycle and are usually read together with the order. Names and prices are stored as snapshots. Customer profiles and product catalogs can still live as separate documents because they have independent lifecycles and access patterns.

Embed data when it belongs to the aggregate, has bounded size, and is commonly read together. Use references when data is shared, has an independent lifecycle, may grow unbounded, or is queried independently on a regular basis. If the same data is embedded into many documents and requires synchronous updates, consistency costs climb rapidly.

Document databases do not imply "schemaless" or "no transactions." Document engines can still validate structure, maintain indexes, and support transactions; the scope and cost of those features depend on the specific product. Evaluate the actual capabilities of the chosen engine.

### 7.3. Graph Model

The graph model fits when questions focus primarily on paths through relationships. Examples include finding users connected to a fraudulent account within three hops, finding products frequently bought together, or mapping service dependency chains.

Graphs represent entities as nodes and relationships as edges. Relationships can carry properties such as start time, role, or confidence level. Multi-hop path queries are often much more natural than writing deeply nested `JOIN`s.

If most operations just look up records by key, update a few fields, and aggregate daily totals, a graph model adds overhead without proportional return. Do not choose a graph just because a domain has many relationships; choose it when traversing relationships is the core operation.

### 7.4. Analytical Model

Operational systems typically optimize for small transactions, accurate updates, and fast responses. Analytical systems must scan large data volumes to aggregate across dimensions like time, customer, product, or region. These two workloads often call for different structures.

A star schema typically pairs a fact table storing events or measures with dimension tables describing context:

~~~mermaid
flowchart TD
    SALES[Fact_Sales]
    DATE[Dim_Date]
    PRODUCT[Dim_Product]
    CUSTOMER[Dim_Customer]
    STORE[Dim_Store]
    DATE --> SALES
    PRODUCT --> SALES
    CUSTOMER --> SALES
    STORE --> SALES
~~~

`Fact_Sales` may hold quantities, revenue, and keys to each dimension. `Dim_Date` describes day, week, and month; `Dim_Product` describes product groups; `Dim_Customer` describes customer segments. Some dimensions may need change history—for instance, if a customer changes region while historical reports must retain the region at transaction time.

Analytical data is usually ingested from operational systems via ETL/ELT or event streams. Define acceptable latency, how late-arriving records, duplicates, replayed events, and total reconciliations are handled. Avoid letting heavy reporting queries contend for resources with critical transactions whenever workloads can be separated.

## 8. Comprehensive Example: Order Data Design

Consider the requirement: customers create orders, select products and quantities, confirm prices, pay, and later look up order history. The design must protect transactional data while supporting a changing product catalog.

### 8.1. Model Decisions

- Use a relational model as the operational source of truth because orders link with customers, products, and payments, and many rules require transactions and referential constraints.
- Separate `customers`, `products`, `orders`, and `order_items` because they have distinct meanings and lifecycles.
- Snapshot product names, unit prices, and shipping addresses at order time to preserve history.
- Use stable primary keys; use foreign keys and `CHECK`/`UNIQUE` constraints to enforce database-expressible rules.
- Store the locked-in `grand_total` because it represents the confirmed order amount; update it within the same transaction as order components and payments. If detailed reconciliation is required, also store taxes, fees, discounts, and rounding rules.
- Add indexes strictly for real queries, such as looking up a customer's newest orders or finding line items by product.

### 8.2. Reviewing the Four Goals

**Correctness:** foreign keys ensure referenced customers and products exist. `CHECK` constraints enforce non-negative quantities and prices. Transactions ensure inventory, orders, and payments update consistently together. Snapshots preserve historical values. Cross-table rules are verified inside transactions or proper reconciliation checks.

**Evolvability:** adding a new delivery method does not necessarily alter the core order structure. If each method carries varied attributes, use a dedicated delivery method table or a schema-controlled document segment. When adding fields, roll out phased migrations so older application versions do not fail.

**Performance:** an index on `(customer_id, created_at)` supports the order history screen. An index on `product_id` supports checking which orders contain a product. Revenue analytics queries should run against an analytical warehouse or summary tables updated under clear policies, rather than scanning live transactional tables continuously.

**Complexity:** each table represents a clearly named concept. Snapshots have explicit business justification. Aggregated copies are added only when backed by measured demand and reconciliation checks. The team can explain which data is current, which is historical, and which can be rebuilt.

### 8.3. Choices to Confirm Before Implementation

An example model does not replace business clarification. Before locking down the schema, confirm:

- Can a single order contain multiple currencies or only one?
- Are line-item edits allowed after payment? If so, how must adjustments be recorded?
- Can customers or products referenced in past transactions ever be deleted?
- Does cancelling an order restore inventory, and can that operation be retried safely (idempotently)?
- When are taxes, shipping fees, and discounts calculated, and how are they rounded?
- Is state transition history with actor and reason required?
- Do reports need near-real-time freshness or can they tolerate minutes or hours of lag?

These answers can change keys, constraints, transaction boundaries, history tables, and analytical models. Recording decisions alongside rationale helps future engineers understand why structures were chosen.

## 9. Practical Decision-Making Process

When designing a new model or reviewing an existing one for optimization, follow this sequence:

1. **List business facts and invariants.** Explicitly state which data must exist, which relationships are valid, which values are forbidden, and which events need history.
2. **Define the workload.** List key reads and writes, frequencies, data sizes, concurrency levels, and latency targets.
3. **Establish data boundaries.** Identify entities, aggregates, ownership, and lifecycles. Separate data with independent lifecycles; group data commonly modified together when that clarifies transactions.
4. **Design normalized foundations.** Use explicit keys and constraints. Avoid duplicating data unless justified by history or access patterns.
5. **Identify where strong consistency is required.** Decide which operations need transactions, locks, unique constraints, or concurrency safeguards.
6. **Optimize from measurements.** Measure queries, inspect execution plans, and add indexes or derived copies only when backed by evidence.
7. **Plan the evolution path.** Account for legacy data, version compatibility, backfills, lock durations, and safe rollback or forward-recovery steps.
8. **Test and reconcile.** Test constraints, concurrent load, migrations on realistic data, and discrepancy-detection reports.

A sound design decision should document at least: context, options considered, rationale, accepted trade-offs, workload assumptions, and signals to monitor. When load or business rules change, the team has objective grounds to revisit decisions instead of arguing over technology preferences.

## 10. Common Mistakes

**Optimizing before knowing key queries.** Creating many indexes, caches, or summary tables upfront increases write and operational costs. Measure first, then optimize actual bottlenecks.

**Dumping everything into JSON for "flexibility."** A flexible schema does not automatically produce safe evolution. If important fields lack validation, constraints, and indexing, data quickly becomes inscrutable.

**Normalizing dogmatically regardless of workload.** Splitting data is a solid baseline, yet snapshots or derived data may be needed to preserve history and serve reads. What matters is keeping the source of truth clearly distinct from copies.

**Using the application as the sole safeguard.** Pre-write checks cannot protect all write paths and do not prevent race conditions on their own. Enforce constraints and transactions in the database wherever possible.

**Using `CASCADE` by default.** Deleting a customer or product can accidentally wipe out transaction history. Deletion policies must reflect the lifecycle and retention needs of child data.

**Changing schemas in one big bang.** Dropping or renaming columns while older application instances still run causes deployment outages. Use compatible changes and multi-stage migrations.

**Using one model for both transactions and heavy reporting.** The two workloads have distinct characteristics. A separate analytical warehouse or summary model—with proper ingestion and reconciliation—may be required.

## 11. Model Review Checklist

Before finalizing a design, verify:

- [ ] Every entity and attribute has a clear business meaning.
- [ ] Primary keys, candidate keys, and referential relationships are defined.
- [ ] Critical invariants are protected by appropriate constraints or transactions.
- [ ] `NULL`, defaults, deletions, and data lifecycles have explicit semantics.
- [ ] Current data, historical snapshots, and derived data are clearly distinguished.
- [ ] Primary access patterns are listed; every index has a concrete justification.
- [ ] Concurrent operations that could overwrite data or violate limits are handled.
- [ ] A migration plan exists that stays compatible with live data and running app versions.
- [ ] Acceptable staleness/latency for aggregated or analytical data is agreed upon.
- [ ] The team can explain the source of truth, sync mechanisms, and discrepancy checks.

## Conclusion

A data model is a set of decisions about meaning, ownership, relationships, lifecycles, and data access. Correctness is protected through constraints, transactions, and faithful representation of business facts. Evolvability comes from clear boundaries, intentional snapshots, and phased migrations. Performance comes from understanding workloads, measuring queries, and fixing real bottlenecks. Complexity stays under control when every added mechanism has a clear reason, owner, and verification method.

Choose models based on data characteristics and core operations. The relational model fits most constraint-heavy transactional workflows; documents work well for co-accessed aggregates; graphs shine when path traversal is central; analytical models serve large-scale historical aggregations. When combining models, define the source of truth, synchronization lag, and reconciliation checks so performance gains never compromise data trustworthiness.
