# Comparing the Document Model with Relational and Key-Value Models

## 1. Why distinguish the three data models?

When building an application, how you choose to **organize data** directly affects reads, writes, consistency guarantees, scalability, and long-term maintenance. Three common models are:

- **Relational:** data lives in tables composed of rows and columns; tables relate via keys and are typically queried with SQL. PostgreSQL and MySQL are familiar examples.
- **Document:** data is grouped into hierarchically structured documents that commonly contain nested objects and arrays. MongoDB stores documents in BSON format; Spring Data MongoDB maps documents to Java objects and operates on them via `MongoTemplate` or repositories.
- **Key-value:** each value is accessed primarily through a unique key. Redis is a classic example; beyond strings, Redis also supports data structures such as hashes, sets, and sorted sets.

These three models do not divide applications into mutually exclusive camps. A single system can use a relational database for transactional records, MongoDB for business documents with flexible structures, and Redis for caching or sessions. What needs to be decided is **which data is commonly read and modified together**, how strictly relationships must be enforced, and which query patterns the application must support.

## 2. The same problem: storing an order

Suppose an e-commerce system needs to store an order containing an order ID, customer, shipping address, line items, quantities, unit prices at purchase time, and order total. Typical operations are:

1. Display an entire order by order ID.
2. List the 20 most recent orders for a customer.
3. Update an order's status without losing other data.
4. Aggregate quantities of products sold over a time range.

### 2.1. Relational model: splitting into tables

A standard design uses `customers`, `products`, `orders`, and `order_items` tables. The example below focuses on the two order tables, assuming `customers(id)` and `products(id)` already exist:

```sql
CREATE TABLE orders (
    id          VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) NOT NULL REFERENCES customers(id),
    created_at  TIMESTAMP NOT NULL,
    status      VARCHAR(32) NOT NULL,
    total       DECIMAL(18, 2) NOT NULL
);

CREATE TABLE order_items (
    order_id              VARCHAR(32) NOT NULL REFERENCES orders(id),
    line_no               INTEGER NOT NULL,
    product_id            VARCHAR(32) NOT NULL REFERENCES products(id),
    product_name_snapshot VARCHAR(200) NOT NULL,
    quantity              INTEGER NOT NULL,
    unit_price            DECIMAL(18, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no)
);
```

When retrieving an order along with its line items, the application can use a `JOIN`:

```sql
SELECT o.id, o.customer_id, o.status,
       i.line_no, i.product_id, i.quantity, i.unit_price
FROM orders AS o
JOIN order_items AS i ON i.order_id = o.id
WHERE o.id = 'order-1001'
ORDER BY i.line_no;
```

The query returns multiple rows, one per line item. The application or ORM assembles them into an `Order` object. Foreign keys help ensure each line item belongs to an existing order; transactions can coordinate changes across multiple tables atomically.

**Strengths:** entities and relationships are explicit; it is straightforward to enforce data constraints, run `JOIN`s, execute ad-hoc queries, and update shared entities in one place. **Costs:** a business workflow spanning many tables may require `JOIN`s or multiple data accesses. That is not inherently slow: actual performance depends on indexes, query plans, data volume, and how the application loads associations.

### 2.2. Document model: grouping data into one document

In MongoDB, if the application usually reads an entire order together, tightly coupled order data can be stored in a single document in the `orders` collection:

```json
{
  "_id": "order-1001",
  "customerId": "customer-01",
  "createdAt": "2026-10-15T08:30:00Z",
  "status": "PAID",
  "shippingAddress": {
    "recipient": "Nguyen An",
    "city": "Da Nang",
    "street": "12 Nguyen Van Linh"
  },
  "items": [
    {
      "productId": "product-10",
      "productNameSnapshot": "Mechanical keyboard",
      "quantity": 1,
      "unitPrice": 1200000
    },
    {
      "productId": "product-20",
      "productNameSnapshot": "Wireless mouse",
      "quantity": 2,
      "unitPrice": 450000
    }
  ],
  "total": 2100000
}
```

This is a readable JSON representation; in actual storage, MongoDB uses BSON and can employ specialized types such as `ObjectId`, `Date`, or `Decimal128`. In production data, choose appropriate types for timestamps and currency rather than assuming JSON strings or numbers in the example reflect the final storage types.

A single query can retrieve the complete document:

```javascript
db.orders.findOne({ _id: "order-1001" });

db.orders.find({ customerId: "customer-01" })
         .sort({ createdAt: -1 })
         .limit(20);
```

`shippingAddress` and `items` are **embedded** because they serve reading a single order. `customerId` and `productId` act as **references** to entities with independent lifecycles. Product names and unit prices are kept inside the order as *snapshots*: changing a product's current price must not retroactively alter historical purchases.

**Strengths:** storage structure aligns closely with domain objects; convenient for reading or updating data that belongs together; documents can carry optional fields and nested structures. **Costs:** when the same piece of information is duplicated across documents, the application must distinguish historical snapshots from data that must stay synchronized; complex cross-collection relationships may require additional queries or `$lookup` aggregations.

### 2.3. Key-value model: accessing by known key

With Redis, a simple approach is to store the entire order as a JSON string under a key. This example illustrates key-based retrieval thinking, not a recommendation to use Redis as the primary source of truth for orders:

```text
SET order:1001 '{"id":"order-1001","customerId":"customer-01","total":2100000}'
GET order:1001
```

`GET` is very convenient when the application already knows `order:1001`. However, if you want to find *all orders for customer-01*, the basic key-value model does not automatically infer relationships from inside JSON values. The application can maintain a secondary index structure:

```text
SADD customer:customer-01:orders order:1001
SMEMBERS customer:customer-01:orders
```

Whenever an order is added or deleted, the application must update both the primary entry and the secondary key set. `SMEMBERS` also does not sort by time; querying the newest orders may require a sorted set and extra synchronization rules. Some key-value stores and extensions provide richer query capabilities, but those are product-specific features rather than default traits of every key-value model.

**Strengths:** direct key lookups are fast and well suited for caches, sessions, counters, temporary tokens, and certain real-time state. **Costs:** queries beyond the primary key require the application to design its own indexes, update multiple keys, or rely on engine-specific extensions.

## 3. Technical comparison table

| Criterion | Relational | Document (MongoDB) | Key-Value (e.g., Redis) |
| --- | --- | --- | --- |
| Primary data unit | Table rows; multiple tables linked by keys | BSON document with fields, nested objects, and arrays | Key and associated value/data structure |
| Structure design | Explicit table schemas and constraints | Flexible schema across documents; optional schema validation | Structure typically defined by the application or value type |
| Data relationships | Foreign keys, `JOIN`, integrity constraints | Embedded data or reference IDs; `$lookup` available | Typically linked via key naming conventions and app-managed indexes |
| Multi-criteria queries | SQL with filtering, `JOIN`, grouping, aggregation | Filters, projections, indexes, aggregation pipelines | Key lookup is primary; additional capabilities depend on the store/modules |
| Schema evolution | Typically via schema and data migrations | New fields can be added gradually, though document versioning is still needed | Usually changes value format and handles compatibility in the application |
| Multi-entity updates | Transactions spanning multiple rows/tables are standard | Single-document writes are atomic; multi-document transactions available | Single commands are typically atomic; command grouping, transactions, or scripts vary by product |
| Data duplication | Reduced via normalization; denormalization applied when needed | Intentional when embedding/copying to optimize read paths | Often stores snapshots or maintains multiple keys for access paths |
| Scaling | Replication and partitioning/sharding depending on the RDBMS | Built-in replication and sharding | Replication/clustering depending on the store |
| Strong fit cases | Complex relationships, cross-entity constraints, and ad-hoc SQL reporting | Hierarchical data and business aggregates read together | Key lookups, caching, sessions, simple access patterns |

Do not conclude that one model is always faster or more consistent than the other two. For example, a MongoDB query without an appropriate index can end up scanning many documents; an SQL query with well-chosen indexes and `JOIN`s can be very fast. Performance must be evaluated against the same dataset, access patterns, and latency requirements.

## 4. Distinguishing embedding, referencing, and normalization

In Spring Data MongoDB, the most important decision is usually not naming collections, but **choosing document boundaries**.

### When should you embed?

Embedding makes sense when child data's lifecycle depends on the parent, the element count stays reasonably bounded, and most reads and writes happen together. The shipping address captured at checkout and an order's line items are classic examples. A single-document update can atomically modify multiple fields within the same document.

### When should you reference?

Referencing makes sense when an entity is shared, has an independent lifecycle, or an associated list can grow without bound. A customer could place millions of orders: you must not stuff every order into an array inside the customer document. Instead, store `customerId` on each order and index it for customer queries.

In relational modeling, normalization splits entities into tables and manages links via keys. In MongoDB, **embedding and referencing can coexist** inside a single aggregate. Spring Data supports reference mechanisms such as `@DBRef` and `@DocumentReference`, but they do not turn MongoDB into a database with foreign keys or automatically generate an SQL `JOIN`. Weigh the extra reads generated, update semantics, and whether automatic dereferencing is genuinely needed. In many cases, storing plain IDs and querying deliberately is enough.

### Two limits that are easy to overlook

- **Unbounded arrays:** lists of events, page views, or all orders inside one document can bloat the document, increase update cost, and hit MongoDB's document size limit (16 MiB for standard BSON documents). Move unbounded collections into separate documents/collections.
- **Undisciplined duplication:** `productNameSnapshot` on an order should stay fixed historically; a product's current display name, if duplicated in many places and expected to update everywhere at once, needs a synchronization strategy or a switch to referencing. Not all duplicated data is bad, but every copy must have a clear semantic purpose.

## 5. How do consistency and transactions differ?

Consider the workflow **placing an order and decrementing inventory**:

- **Relational:** if orders, order lines, and inventory reside in separate tables, the application typically uses a transaction so all changes succeed or roll back together. Isolation levels and concurrency anomalies still depend on configuration and specific statements.
- **MongoDB:** an update to *a single* document is atomic, even when modifying multiple fields and nested elements within that document. If writing to an `orders` document and a separate `inventory` document, you must handle errors and race conditions; MongoDB supports multi-document transactions when the deployment meets the requirements. Multi-document transactions carry overhead, so examine business boundaries and access patterns before relying on them routinely.
- **Key-value:** a Redis command like `INCR` is atomic with respect to the key/value it operates on. Redis also offers `MULTI`/`EXEC` and scripts for coordinating commands; however, guarantees, error handling, and durability should not be assumed to match relational transactions, especially when operations span external systems.

Do not conflate **atomicity** (an operation applies all-or-nothing), **isolation** (how concurrent operations observe one another), **durability** (persistence across failures), and **business consistency** (such as never overselling stock). To evaluate accurately, identify the invariants that must hold, the scope of changes, and the exact guarantees provided by the database engine.

## 6. Queries, indexes, and read/write costs

### 6.1. Same query need, different optimization paths

For the requirement *20 most recent orders for a customer*:

**Relational:** use `WHERE customer_id = ? ORDER BY created_at DESC LIMIT 20` and typically consider a composite index `(customer_id, created_at)` based on table characteristics, database engine, and query plans.

**MongoDB:** filter on `customerId`, sort on `createdAt`, and add a compound index:

```javascript
db.orders.createIndex({ customerId: 1, createdAt: -1 });

db.orders.find({ customerId: "customer-01" })
         .sort({ createdAt: -1 })
         .limit(20);
```

A well-designed index can serve both the filter and the sort. When analyzing real performance, use `explain("executionStats")` to inspect the query plan and metrics such as examined documents and index keys:

```javascript
db.orders.find({ customerId: "customer-01" })
         .sort({ createdAt: -1 })
         .limit(20)
         .explain("executionStats");
```

**Key-value:** if `order:1001` is already known, key lookup is trivial. To maintain a time-ordered list of orders per customer, you can maintain a sorted set using timestamps as scores, while also keeping that set updated whenever order data changes. Application-level index correctness therefore becomes part of the design.

### 6.2. Aggregation and `JOIN`

SQL supports joining and summarizing across tables via `JOIN`, `GROUP BY`, window functions, and related constructs. MongoDB provides the **aggregation pipeline** with stages such as `$match`, `$unwind`, `$group`, `$project`, `$sort`, and `$lookup` to process data within or across collections. Example calculating total units ordered per customer:

```javascript
db.orders.aggregate([
  { $unwind: "$items" },
  {
    $group: {
      _id: "$customerId",
      totalUnits: { $sum: "$items.quantity" }
    }
  },
  { $sort: { totalUnits: -1 } }
]);
```

This pipeline is useful when aggregating nested data; at large scale, consider filtering early with `$match`, suitable indexes, the fan-out of `$unwind`, and processing cost. If the business needs arbitrary multi-entity joins and complex relational reporting, a relational database or dedicated analytics store may fit better.

### 6.3. Flexible schema does not mean abandoning control

MongoDB allows two documents in the same collection to have different field sets. This helps for products with varying attributes, yet Java code still relies on a stable data contract: field names, types, required fields, default rules, and an upgrade path for older documents. You can combine MongoDB **schema validation**, Bean Validation in the application, and migrations when structural changes have broad impact.

A new attribute such as `deliveryInstructions` can be added to new orders, while code reading older orders must tolerate the missing field. Relational systems normally handle such changes via table migrations; key-value models typically version or encode value formats. All three require a data compatibility strategy.

## 7. Applying this in Spring Data MongoDB

Spring Data MongoDB is a data access layer for Java/Spring applications. It **does not alter MongoDB's fundamental traits**, but provides Java-to-document mapping, repositories, `MongoTemplate`, aggregation support, index management, and reactive access.

### 7.1. Mapping a document with nested data

Example using Java records to model the same order aggregate:

```java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "orders")
public record OrderDocument(
    @Id String id,
    String customerId,
    Instant createdAt,
    String status,
    Address shippingAddress,
    List<OrderLine> items,
    BigDecimal total
) {}

record Address(String recipient, String city, String street) {}

record OrderLine(
    String productId,
    String productNameSnapshot,
    int quantity,
    BigDecimal unitPrice
) {}
```

`@Document` identifies the collection, `@Id` maps the document identifier, and `Address` and `OrderLine` records are persisted as nested structures. This illustrates modeling; in a production system, standardize monetary storage (`BigDecimal`/`Decimal128` or minor currency units), validate inputs, and plan schema versioning. Exact BSON types and numeric encoding depend on the application's converter configuration.

### 7.2. Querying with repositories or `MongoTemplate`

Repositories fit straightforward queries with recurring patterns:

```java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface OrderRepository
        extends MongoRepository<OrderDocument, String> {
    Page<OrderDocument> findByCustomerId(String customerId, Pageable pageable);
}
```

When called with a `PageRequest` sorted descending by `createdAt`, the repository returns a page of a customer's orders. `Page` can trigger an extra count query for total elements; if you only need to know whether a next page exists, consider `Slice` to avoid unnecessary counting.

`MongoTemplate` fits when building filters, sorts, projections, or specialized updates dynamically:

```java
Query query = Query.query(Criteria.where("customerId").is(customerId))
    .with(Sort.by(Sort.Direction.DESC, "createdAt"))
    .limit(20);

List<OrderDocument> orders =
    mongoTemplate.find(query, OrderDocument.class);
```

This snippet assumes `mongoTemplate`, `customerId`, and imports for `Query`, `Criteria`, `Sort`, and `List` are present in the service. Both repository and template execute queries against the same MongoDB collection; API choice depends on the level of query control needed.

### 7.3. Capabilities that tie back to document design

- **Indexes:** design around actual filters, sorts, and pagination. You can declare `@Indexed`/`@CompoundIndex` annotations or create indexes via administrative/migration processes. Never assume index annotations automatically create indexes across all Spring Data MongoDB configurations.
- **Aggregation:** use `MongoTemplate.aggregate(...)` when multi-stage pipelines are needed; check index utilization and intermediate dataset sizes.
- **Transactions:** use `MongoTransactionManager` with a transaction-capable MongoDB deployment when multi-document operations genuinely require atomicity; weigh overhead and deployment prerequisites.
- **Reactive:** `ReactiveMongoRepository` and `ReactiveMongoTemplate` support non-blocking access streams in reactive applications. Reactive does not make MongoDB queries faster on its own; benefits depend on concurrent load, architecture, and avoiding thread blocking.
- **Testing:** verify document mapping, documents with missing fields, nested-field queries, critical indexes, and transaction behavior using integration tests against real MongoDB (e.g., via Testcontainers) with matching deployment settings.
- **Diagnostics:** use `explain`, slow query statistics, and examined document counts to diagnose bottlenecks. Improve performance via indexes, projections, result limits, and adjusted document boundaries before concluding the wrong data model was chosen.

## 8. Choosing a model by business characteristics

| Specific Requirement | Model Worth Considering First | Main Rationale and What to Verify |
| --- | --- | --- |
| Ledgers, journal entries across many accounts, strict constraints | Relational | Multi-row/table transactions and constraints; still design isolation levels, auditing, and business invariants |
| Reading an order together with shipping address and line items | Document or Relational | Document works well when aggregate boundaries are clear; relational is also strong if heavy joins and reporting exist |
| Product catalogs with varying attribute sets per category | Document | Flexible structure; still needs schema validation, indexes, and clear search rules |
| Session lookup by token, TTL-cached responses | Key-value | Straightforward key reads and expiration handling; evaluate durability and cache refresh strategies |
| Cross-entity reporting with arbitrary ad-hoc joins | Relational or Analytics Engine | SQL and analytical engines may fit better; evaluate data volume, frequency, and query patterns |
| Very long event streams per user | Separate documents or table rows | Do not pile all events into an ever-growing array; plan pagination, archiving, and retention |

A sound design method starts from **queries and business invariants**, and only then shapes storage structures:

1. List critical read/write operations, their frequencies, and target latencies.
2. Identify data that always changes together versus objects with independent lifecycles.
3. Flag unbounded growth, many-to-many relationships, and shared values.
4. Enumerate consistency invariants that must hold under concurrent operations.
5. Design indexes and benchmark representative queries on realistic datasets, including pagination and data growth.

If an application uses both MongoDB and Redis, define which is the **source of truth**, when caches expire or invalidate, and how the system behaves if the cache fails. Adding another database engine also increases synchronization, operational, and testing overhead.

## 9. Common misconceptions

**"MongoDB has no schema."** MongoDB does not require every document in a collection to look identical, yet data still has structure. Schema validation can be enforced; Java code, queries, indexes, and reports all depend on field contracts.

**"Documents are data without relationships."** Documents can hold nested data and references to other documents. The difference lies in how relationships are represented and managed, not that relationships disappear.

**"MongoDB does not support transactions or joins."** MongoDB has multi-document transactions and `$lookup`. The real question is their cost and fit for your workload; do not assume they behave identically to SQL.

**"Redis only stores strings, or cannot support queries other than GET."** Redis offers multiple data structures and extension modules. Even so, arbitrary ad-hoc lookups across every field inside a JSON value do not come naturally from plain key-value pairs alone.

**"Embedding everything is always faster."** Embedding unbounded collections or shared, independently updated data can bloat documents and create excessive write amplification. Establish aggregate boundaries before embedding.

**"NoSQL always scales better than SQL."** Scalability depends on the product, partitioning setup, shard keys, indexes, queries, and infrastructure limits. Relational systems also have scaling mechanisms, while MongoDB and Redis each have access patterns that create bottlenecks.

## 10. Conclusion for Spring Data MongoDB learners

The **relational** model prioritizes representing entities and links through tables, keys, and constraints; the **document** model prioritizes grouping data around business aggregates that are read and written together; the **key-value** model prioritizes direct access by key and key-scoped structures. No single model is best for every application.

When using Spring Data MongoDB, treat `@Document`, repositories, and `MongoTemplate` as tools to realize your chosen design. System quality rests on choosing sound embed/reference boundaries, preserving business invariants, indexing for real queries, and verifying performance on realistic data. That is the foundation for deeper study into aggregation, transactions, reactive access, and MongoDB optimization.
