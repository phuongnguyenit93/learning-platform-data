# Bounded Contexts and the Consistency Scope of a Model

## Learning Objectives

After this lesson, you will be able to:

- Explain **bounded contexts** and why a single business term can carry multiple valid meanings within the same system.
- Distinguish between a model's **semantic consistency boundary**, an aggregate's **transactional consistency boundary**, and **physical storage boundaries**.
- Partition a business domain into models with clear responsibilities and data ownership; identify which constraints must hold immediately and which are synchronized over time.
- Translate those boundaries into verifiable schemas, keys, relationships, update rules, and integration contracts.

In data design, identifying all entities, attributes, and keys solves only part of the problem. If you put every piece of information named "Product", "Customer", or "Order" into a single shared model, you easily end up with a schema that is hard to change: the sales team wants to store the price at the time of purchase, the catalog team wants to update the current price, and the warehouse wants to manage available stock quantities. These requirements relate to the same product code, yet **they do not require the same data object or the same consistency rules**.

## 1. What Is a Bounded Context?

In Domain-Driven Design (DDD), a **bounded context** is the boundary within which a domain model and its business language are consistently defined. Inside that boundary, terms, rules, and the meaning of data must be unambiguous to the people using the model. Outside that boundary, another team may have a different model for the same real-world concept.

For example, when a customer buys a laptop:

| Context | What does "Product" mean? | Data to manage |
| --- | --- | --- |
| Catalog | An item currently listed for sale | Name, description, category, current list price |
| Sales | An item selected at the time an order is placed | Reference ID, name and unit price at time of purchase, quantity |
| Inventory | A unit of stock that can be received, issued, and reserved | SKU, warehouse, available quantity, reserved quantity |

Today's list price in Catalog might be 24 million VND, while the line item in an order confirmed yesterday must still retain the unit price of 23 million VND from the transaction that took place. Two different values **are not a synchronization bug**: each value answers a different business question.

Core concepts:

- **Domain:** the entire problem space that the software supports, such as online retail.
- **Subdomain:** a cohesive area of business capability, such as order management or inventory management.
- **Bounded context:** the scope where a specific model applies, with its own language and rules. A single subdomain can contain multiple contexts; the two concepts are not synonymous.
- **Domain model:** the concepts, relationships, states, behaviors, and invariants that express the business logic within that context. A model is more than just a list of database tables.
- **Ubiquitous language:** the shared terminology agreed upon by domain experts and developers **within the same context**.

Sharing the same name does not imply sharing the same structure. Conversely, the same external identifier can be kept across multiple contexts for cross-referencing without merging the models into one.

## 2. Three Types of Boundaries to Separate

The phrase "the consistency scope of a model" is often confused with the scope of an ACID transaction. To choose accurate data structures, you need to identify three distinct layers:

| Layer | Design question | Example | What must **not** be inferred |
| --- | --- | --- | --- |
| **Semantic – bounded context** | Which terms and rules belong together in one model? | In Sales, "confirmed order" has a well-defined meaning | Does not mean every change in Sales must happen in a single transaction |
| **Invariant/transactional – aggregate** | Which data must change together so a rule always holds after each operation? | An order and its line items; disallowing negative or zero line quantities | Does not mean the entire Sales context has only one aggregate |
| **Physical – database/schema/service** | Where are the models stored and deployed? | The sales and catalog schemas reside together in PostgreSQL | Does not automatically prove two schemas are two independent bounded contexts |

An **invariant** is a condition that must always hold true across all valid states of an object or aggregate—for example, every order line has a quantity greater than 0, and a confirmed order cannot have its purchase price modified. An **aggregate** is a cluster of objects with an **aggregate root** coordinating changes, typically designed as a transactional consistency boundary. This is a design principle, not a property automatically obtained simply by creating tables and foreign keys.

A bounded context can contain multiple aggregates; a single service can deploy multiple bounded contexts; and a single bounded context can span multiple deployment components. Choose the deployment architecture after understanding the business boundaries, rather than using the number of tables, repositories, or microservices as the criterion for splitting contexts.

## 3. Partitioning Models Through a Sales Workflow

Consider a customer purchase flow with four contexts:

1. **Catalog** owns item presentation details and currently published prices.
2. **Sales** owns orders, order lines, locked-in prices, and order processing state.
3. **Inventory** owns stock levels, stock reservations, and releasing reserved stock.
4. **Payment** owns payment requests, authorization or capture outcomes, and the payment provider's transaction ID.

~~~mermaid
flowchart LR
    C["Catalog<br/>Current item information"]
    S["Sales<br/>Orders and locked-in prices"]
    I["Inventory<br/>Stock levels and reservations"]
    P["Payment<br/>Payment transactions"]

    C -->|"Item details / suggested price"| S
    S -->|"Reservation request"| I
    I -->|"Reservation result"| S
    S -->|"Payment request"| P
    P -->|"Payment result"| S
~~~

The arrows represent **information exchange contracts**; they do not mean the contexts share a single table or always call one another synchronously. They can be implemented via APIs, events, or a combination of both.

Identify authoritative data versus purpose-built copies:

| Data | Authoritative owner | Consumer and how it is used |
| --- | --- | --- |
| Current name/description/published price | Catalog | Sales reads it for display and creating draft orders |
| Unit price accepted at order placement | Sales | Sales stores a **snapshot** to preserve transaction history |
| Available quantity and reservation records | Inventory | Sales receives the reservation outcome rather than deducting stock directly in the order table |
| Transaction status with the payment gateway | Payment | Sales receives the outcome to determine the order state |

An identifier like `productId` in an order line is a **reference to an external concept**. It does not grant Sales permission to modify Catalog. When two contexts share the same database, adding direct foreign keys across boundaries can create lifecycle, deployment, and deletion coupling; instead, consider integration contracts, business reference keys, and existence validation at the time data is received. Foreign keys **inside** each context remain very useful.

## 4. Finding the Right Transaction Scope for Invariants

In Sales, suppose an "Order" aggregate consists of an order header and its order lines. Rules that must be enforced consistently could include:

- Each line has a positive quantity; the order must have at least one line before it can be confirmed.
- The unit price and currency locked in at checkout must remain unchanged after confirmation.
- State transitions follow permitted paths: "PENDING" to "CONFIRMED" or "CANCELLED"; a cancelled order cannot return to pending via an arbitrary update command.
- If the total amount is stored on the order header, that total must match the sum of the lines and the agreed rounding rules.

These rules are the responsibility of Sales and can be checked within a single transaction that updates the Order. By contrast, the rule "an order is only confirmed after the warehouse reserves sufficient stock and payment succeeds" requires **outcomes from multiple contexts**. You should not default to a SQL transaction spanning Sales, Inventory, and Payment, especially when they are independent systems.

One coordination approach is a workflow (**saga/process manager**) with explicit intermediate states:

1. Sales creates a "PENDING" order with locked-in prices and line items.
2. Sales sends a reservation command with the order ID; Inventory atomically processes its stock rules and returns "RESERVED" or "REJECTED".
3. If the reservation succeeds, Sales requests Payment to authorize/capture payment. If it fails, Sales asks Inventory to release the reservation and transitions the order to the appropriate state.
4. Once all required conditions are met, Sales transitions the order to "CONFIRMED".

During the waiting period, the overall system can be **eventually consistent**: Inventory has already reserved the stock while Sales has not yet received the confirmation event. This is acceptable as long as the intermediate state is accurately surfaced and recovery mechanisms are in place.

To keep the flow safe when messages are redelivered, responses are lost, or messages arrive out of order:

- Use a unique request/reservation ID for **idempotent** processing (receiving the same command again does not reserve stock twice).
- Store state and version numbers to control concurrent updates.
- Consider a **transactional outbox** when you need to reliably persist data and event messages in the same local transaction; the receiver tracks processed events.
- Define reservation expiration times, retry policies, and **compensation** actions when a later step fails. A compensation action is a new business operation, not a cross-service "rollback" button.

Whether to choose synchronous or asynchronous communication depends on the business's tolerance for latency and failure. "Eventual consistency" does not mean abandoning constraint enforcement; it requires explicitly defining intermediate states, terminal states, and error-handling workflows.

## 5. From Domain Boundaries to a Relational Schema

The example below illustrates this in **PostgreSQL**. Catalog and Sales use two schemas in the same database to demarcate logical ownership. This is a deployment option for a modular monolith; the databases can be split later when operational independence is needed.

~~~sql
CREATE SCHEMA catalog;
CREATE SCHEMA sales;

CREATE TABLE catalog.product (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    current_list_price NUMERIC(14, 2) NOT NULL
        CHECK (current_list_price >= 0),
    currency CHAR(3) NOT NULL
);

CREATE TABLE sales.orders (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    buyer_id BIGINT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING'
        CHECK (status IN ('PENDING', 'CONFIRMED', 'CANCELLED')),
    version BIGINT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE sales.order_line (
    order_id BIGINT NOT NULL REFERENCES sales.orders(id),
    line_no INTEGER NOT NULL CHECK (line_no > 0),
    catalog_product_id BIGINT NOT NULL,
    product_name_snapshot TEXT NOT NULL,
    unit_price_snapshot NUMERIC(14, 2) NOT NULL
        CHECK (unit_price_snapshot >= 0),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    currency CHAR(3) NOT NULL,
    PRIMARY KEY (order_id, line_no)
);
~~~

Intentional design decisions:

- "sales.order_line" has a foreign key to "sales.orders" because they belong to the same model and have a tightly coupled lifecycle.
- "catalog_product_id" is a reference to Catalog, with **no cross-schema foreign key** in this example. Sales verifies the product through a business contract when creating the order and stores the ID for reconciliation.
- "product_name_snapshot" and "unit_price_snapshot" are intentional historical data. Updating the current name or price must not alter a finalized order.
- The composite primary key "(order_id, line_no)" guarantees unique line numbers within an order and supports querying lines by "order_id". Add new indexes only when actual query needs arise.
- "CHECK" constraints protect row-level conditions. Multi-row rules—such as "a confirmed order must have at least one line"—or state transition rules must be handled within a transaction at the domain/application layer, or via an appropriate database mechanism if carefully designed. Note that "CHECK(status IN (...))" alone **does not** validate legal state transitions.

Example to prevent two users from simultaneously confirming or modifying the same order version:

~~~sql
UPDATE sales.orders
SET status = 'CONFIRMED',
    version = version + 1
WHERE id = :order_id
  AND status = 'PENDING'
  AND version = :expected_version;
~~~

The application must check the number of updated rows. If it is 0, the data or status has already changed; it must re-read and decide how to handle the business logic rather than overwriting. Before running this statement, the application must also verify that it has received both the reservation and payment outcomes corresponding to the order. **Optimistic locking** only handles write contention; it does not enforce the full confirmation rule by itself.

In a multi-currency system, values with different "currency" codes must never be added directly; explicitly define the order currency, the exchange rate at calculation time, and the rounding policy. The example above is simplified to focus on model boundaries.

## 6. Designing Contracts Between Contexts

When Sales receives information from Catalog or Inventory, describe the contract at the business level:

| Contract | Minimum payload | What the consumer needs to know |
| --- | --- | --- |
| ProductPublished / ProductChanged | productId, version, name, listPrice, currency | Describes the **current price**; does not replace prices on existing orders |
| ReserveStock (command) | requestId, orderId, sku, quantity | The same requestId must produce a consistent outcome on redelivery |
| StockReserved / StockRejected | eventId, requestId, reservationId, outcome | Sales correlates the outcome with the issued request |
| PaymentAuthorized / PaymentFailed | eventId, orderId, paymentId, outcome | Trust outcomes only from Payment; handle duplicates and out-of-order delivery |

The event names here are examples, not a mandatory standard. In particular, a **command** asks for something to be done, whereas an **event** announces something that has already happened. When designing messages, specify the contract owner, schema version, temporal semantics, and backward-compatibility policy.

If Sales uses the term "paid" while Payment distinguishes between "AUTHORIZED" and "CAPTURED", you need a translation/mapping layer (**anti-corruption layer**) to avoid misinterpreting the semantics. Joining two tables on identically named status columns does not resolve semantic mismatches.

A **context map** documents contexts, their dependencies, and their integration patterns. It is far more useful than a system-wide table diagram when determining where rules change, where data is consumed, and where contract changes must be coordinated.

## 7. Consistency for Queries and Reporting

An "order details" screen often combines data from Sales, Inventory, and Payment. Two common strategies are:

- **Read-time composition:** call the APIs of the respective contexts; data may be fresh, but latency and availability depend on those calls.
- **Dedicated read model:** consume events to build a projection tailored for lookups, dashboards, or reports. The read model may lag and should clearly display "last updated".

Do not turn a reporting model into the "source of truth" for modifying orders, adjusting inventory, or processing payments. If displayed quantities temporarily lag behind the authoritative source, define the acceptable staleness window, refresh cadence, reconciliation process, and UI behavior. For critical financial queries, you may require verification against the authoritative source before taking action.

## 8. Domain Boundaries Independent of Storage Technology

A bounded context does not necessarily map one-to-one to a table, a schema, a database engine, or a microservice. When choosing a physical storage model, start from invariants, query patterns, and scalability needs:

| Storage model | When it helps | What to watch out for regarding consistency boundaries |
| --- | --- | --- |
| **Relational** | Multi-row transactions, locks, constraints, and structured queries | Use transactions and constraints for local invariants; avoid creating arbitrary dependencies across contexts |
| **Document** | Data read/written as a cluster, flexible nested structures | A single document may be the atomic update unit depending on the DBMS; do not endlessly embed entities with independent lifecycles |
| **Graph** | Multi-hop relationships, interconnected networks requiring flexible traversal | Edges connecting multiple entities do not automatically indicate data ownership or which operations must be atomic |
| **Analytical/Columnar** | Large-scale reporting and aggregations | Typically a read-only replica; has ingestion latency and does not replace the transactional source |

For example, Sales can use "orders"/"order_line" tables or an Order document containing an array of lines. What matters most remains: Sales owns the locked-in price, which invariants must be protected, and which changes originate from other contexts.

## 9. Process for Identifying Boundaries from Requirements

**Step 1 – Gather business scenarios.** Ask the people doing the work: Who creates an order? When is the price locked in? Who is allowed to cancel a reservation? Does "paid" mean authorized or captured?

**Step 2 – Build a glossary by role.** Record each department's definition and examples for the same term. Places where the same word obeys different rules signal a need to separate contexts.

**Step 3 – Identify the authoritative data source.** For each piece of information, record who can create/update/delete it and who may only read or store a snapshot. Avoid letting two contexts both act as owners of the same value without an arbitration mechanism.

**Step 4 – Write down invariants and timing requirements.** Mark conditions that must hold immediately on commit, conditions that can wait for messages, and the maximum latency the business can tolerate. Group entities that must change atomically into appropriate aggregates.

**Step 5 – Design integrations.** Specify APIs, commands, events, identifiers, retry/idempotency policies, versioning, and compensation mechanisms. For reporting, distinguish the authoritative source from read replicas.

**Step 6 – Translate into schemas and verify.** Create keys, types, constraints, query-driven indexes, access permissions, and migrations; test concurrency scenarios, duplicate events, and rule changes.

The deliverables should include, at a minimum: a context map, a data ownership matrix, a list of invariants, key aggregate diagrams, integration contracts, and acceptance scenarios. Simply drawing an enterprise-wide ERD while skipping these questions hides where each model begins and ends.

## 10. Signs of Poor Partitioning

| Symptom | Consequence | Remedy |
| --- | --- | --- |
| A single "product" table shared across catalog, historical orders, and stock | Updating prices or attributes can corrupt history; write contention | Assign an owner, use snapshots, and translate data by purpose |
| Treating every table or every service as its own bounded context | Fragmented models, excessive integration overhead, hard-to-execute business transactions | Partition by language and rules first, then design deployment |
| Requiring every constraint to be ACID across multiple contexts | Cross-context locks, infrastructure coupling, poor fault tolerance | Keep invariants local to aggregates; design stateful workflows with compensation |
| Sharing ORM entities or schemas across teams | Schema changes on one side silently break the model on the other | Use versioned contracts and map at the boundary |
| Replicating data without knowing who owns it | Both sides allow edits, causing irreconcilable divergence | Only one source has authority; copies must document their purpose and staleness |
| Validating "status" only with CHECK constraints | Still allows jumping directly from CANCELLED to CONFIRMED | Enforce state transition rules in domain operations with concurrency control |

## 11. Practice Exercise with Guided Solution

**Scenario:** A movie ticket booking platform has three capabilities: (A) publishing showtimes and list prices; (B) holding seats for 5 minutes to prevent double-booking; (C) creating orders and collecting payment. After a customer buys a ticket, the theater may change the list price, but the price on the purchased ticket must remain unchanged. A payment command may be retried due to a lost connection.

**Tasks:**

1. Propose the bounded contexts and the data owned by each context.
2. Write two invariants that must be guaranteed immediately within a local transaction and one rule that must be coordinated across multiple contexts.
3. Explain how to store the purchased ticket price, how to prevent double-booking seats, and how to handle duplicate payment commands.

**A valid solution approach:**

- **Showtime/Catalog** owns showtimes, movie details, and current prices. **Seat Inventory** owns available seats, seat holds, and hold expirations. **Booking** owns ticket orders and locked-in prices. **Payment** owns payment transactions and idempotency keys.
- Local invariant for Seat Inventory: a single seat for a specific showtime cannot have two active holds/bookings at the same time; the hold operation must handle concurrency atomically. Local invariant for Booking: the total amount and unit prices of a confirmed booking do not automatically change when Catalog updates its prices. Cross-context rule: only issue a valid ticket after obtaining a successful seat hold/booking and a payment status that meets the requirement.
- Booking stores a "price_snapshot" along with the currency. Seat Inventory uses locks/constraints and conditional operations suited to how seats and expirations are modeled; hold expirations must be handled by an explicit release process. Payment stores an idempotency key so the same command does not charge twice; Booking handles duplicate outcomes using event IDs and known states.

Also test additional scenarios: two customers holding the same seat simultaneously, a hold expiring before payment settles, a customer clicking "Pay" twice, and a price change between viewing the showtime and confirming the booking. Each scenario should specify the deciding context, modified data, transaction scope, and recovery mechanism.

## 12. Model Review Checklist

- Can the meaning of every key term be explained **within its exact context**?
- Does every piece of data have a single owner, and do copies have a clearly defined purpose, freshness, and update policy?
- Which aggregate/local transaction owns each critical invariant? Are any rules silently requiring a transaction across multiple systems?
- Which relationships are internal foreign keys, and which are references across contracts?
- Are concurrent updates, duplicate commands, out-of-order/late events, partial failures, and compensation steps handled?
- Do the schema, storage engine, indexes, and deployment topology serve the business rather than dictating how the model is partitioned?

**Conclusion:** A bounded context defines **where a model and its language apply**. An aggregate defines **which changes must be immediately consistent within a single transaction**. Databases, schemas, and services are **deployment choices**. Clearly separating these three layers helps translate business requirements into data models that are accurate, evolvable, and verifiable against real-world scenarios.
