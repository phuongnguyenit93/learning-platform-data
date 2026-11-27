# Comparing MongoDB with Relational Databases and Other NoSQL Models

MongoDB is a **document-oriented database** management system (document database). Data is organized as BSON documents inside collections rather than being forced into rows split across multiple relational tables. MongoDB belongs to the NoSQL family, but **NoSQL is not a single data model**: key–value, wide-column, graph, and search engines also have their own organization, query models, and trade-offs.

This lesson places MongoDB alongside relational databases (such as PostgreSQL and MySQL) and popular NoSQL models, focusing on the practical questions: **how is the data structured, how does the application typically read/write it, and what level of correctness guarantee is required?**

## 1. Overview of Storage Models

| Model | Example Systems | Data Unit and Primary Query Style | Typically Suitable When |
|---|---|---|---|
| Relational | PostgreSQL, MySQL, SQL Server | Tables, rows, columns; SQL, `JOIN`, key constraints | Complex relationships, strict integrity, reporting, and multi-entity transactions |
| Document | MongoDB, Couchbase | JSON-like/BSON documents; queries on fields, arrays, nested documents | Nested structures, variation across record types, frequently read as a single aggregate |
| Key–value | Redis, Amazon DynamoDB (also supports attribute-based queries) | Keys mapped to values; access primarily by key | Caching, sessions, fast state lookup, workloads with clear key-based access |
| Wide-column / column-family | Apache Cassandra, ScyllaDB, HBase | Partition key, clustering key, partition-organized rows/columns | Large-scale distributed writes, known-in-advance queries, data distributed across many nodes |
| Graph | Neo4j, JanusGraph | Vertices, edges, properties; path- and relationship-based queries | Multi-hop connected networks, relationship-based recommendations, fraud detection |
| Search engine / search-oriented | Elasticsearch, OpenSearch | Inverted index, text search, and relevance ranking | Full-text search, fuzzy matching, log analytics, and faceted filtering |

The product names in the table are representative examples, not rigid classifications: a single system can support multiple query styles and storage patterns. For instance, PostgreSQL has `jsonb`, MongoDB has aggregation and `$lookup`, Redis has multiple data structures, and DynamoDB supports secondary indexes and conditional queries in addition to key lookups. Therefore, **the actual capabilities of the specific version/configuration and the workload matter more than the “SQL” or “NoSQL” label**.

## 2. The Same Business Case: Orders in SQL and MongoDB

Suppose an e-commerce system needs to store customers, orders, and product line items. An order has multiple line items; after purchase, the product price and name at the time of ordering must be preserved for invoicing and history.

### 2.1. Relational Design: Multiple Tables Linked by Keys

The following SQL example is illustrative and uses common data types:

```sql
CREATE TABLE customers (
    id VARCHAR(40) PRIMARY KEY,
    full_name VARCHAR(200) NOT NULL
);

CREATE TABLE orders (
    id VARCHAR(40) PRIMARY KEY,
    customer_id VARCHAR(40) NOT NULL REFERENCES customers(id),
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE order_items (
    order_id VARCHAR(40) NOT NULL REFERENCES orders(id),
    line_no INTEGER NOT NULL,
    sku VARCHAR(40) NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents BIGINT NOT NULL CHECK (unit_price_cents >= 0),
    PRIMARY KEY (order_id, line_no)
);
```

The schema separates entities and uses `FOREIGN KEY` constraints to enforce links. To retrieve order details, the application can use `JOIN`:

```sql
SELECT o.id, o.status, c.full_name,
       i.sku, i.product_name, i.quantity, i.unit_price_cents
FROM orders AS o
JOIN customers AS c ON c.id = o.customer_id
JOIN order_items AS i ON i.order_id = o.id
WHERE o.id = 'ord-1001'
ORDER BY i.line_no;
```

The result returns one row per product line item. The application layer typically aggregates those rows into a single order object containing an `items` list.

### 2.2. MongoDB Design: A Document Representing an Order

One modeling approach is to place line items **inside** the order document; the customer can still be referenced by ID:

```javascript
db.orders.insertOne({
  _id: "ord-1001",
  customerId: "cus-42",
  status: "PAID",
  createdAt: ISODate("2026-01-15T10:00:00Z"),
  items: [
    { sku: "book-01", productName: "MongoDB Book", quantity: 2,
      unitPriceCents: 150000 },
    { sku: "pen-07", productName: "Note Pen", quantity: 1,
      unitPriceCents: 25000 }
  ],
  totalCents: 325000
});
```

In MongoDB, `orders` is a **collection** and each entry is a **BSON document**. BSON supports data types such as dates, integers, decimals, and ObjectId; MongoDB does not store a plain JSON string for every document. The example uses integers representing the smallest currency unit (cents) to avoid precision errors common when using binary floating-point numbers for money.

Reading an order can be done with a single query:

```javascript
db.orders.findOne({ _id: "ord-1001" });
```

The application receives the entire `items` array in one document, which fits scenarios where a screen usually displays the full order. This is an advantage of **embedding** when data components share the same lifecycle and are frequently read together.

Even so, choosing documents **does not mean embedding everything**. Customer information can live in `customers`, products can live in `products`, and relationships remain represented by `customerId` and `sku`. When data from another collection must be combined, MongoDB can use `$lookup` or perform multiple queries at the application layer.

### 2.3. How Do the Two Models Differ?

```text
Relational (typical)               MongoDB document (typical)

customers                          customers
  cus-42                             cus-42
     |                                  |
orders                              orders
  ord-1001                            ord-1001
     |                                  |
order_items                          +-- items[0]
  (ord-1001, 1)                      +-- items[1]
  (ord-1001, 2)

Multiple rows, joined at query     One document containing line items
```

Neither model is inherently faster or more economical. In a relational model, joins with appropriate indexes can be very efficient; in MongoDB, embedding data reduces round trips to fetch data but can make documents larger and increase update costs.

## 3. MongoDB vs. Relational Databases

| Criterion | Relational Databases | MongoDB |
|---|---|---|
| Core structure | Tables with declared columns and data types | Collections holding BSON documents, which may have differing fields |
| Schema | Typically specified explicitly with DDL, keys, and constraints | More flexible; JSON Schema validation can be used at the collection level |
| Relationships | `PRIMARY KEY`, `FOREIGN KEY`, and `JOIN` are core mechanisms | Referencing by ID or embedding; has `$lookup`, but no automatic foreign keys like standard SQL |
| Normalization | Easy to normalize to reduce duplication and share entities | Can embed/denormalize intentionally to optimize common operations |
| Queries | SQL, multi-table joins, group/order/window functions depending on system | Query API, aggregation pipeline, indexes, and `$lookup` |
| Transactions | Multi-row/multi-table ACID is the common usage pattern | Single-document writes are atomic; supports multi-document, multi-collection, and cross-shard transactions under corresponding deployment conditions |
| Integrity | Foreign keys, CHECK, UNIQUE, NOT NULL, and transactions | Unique indexes, validation, transactions; many business links must be enforced by the application |
| Scaling | Vertical scaling, read replicas, partitioning, or sharding depending on product | Built-in replica sets and sharding; still requires choosing an appropriate shard key |
| Schema evolution | Migrations typically alter schemas and data | Usually easy to add fields, though the application still needs document versioning and migrations |
| Analytics & reporting | SQL is very strong at complex joins and aggregations | Aggregation is strong for document data; multi-dimensional reporting may require additional design or a dedicated analytics system |

### 3.1. Flexible Schema Does Not Mean No Schema

MongoDB allows two documents in the same collection to have different fields:

```javascript
{ _id: "p-1", name: "Keyboard", attributes: { layout: "US" } }
{ _id: "p-2", name: "Jacket", attributes: { size: "M", color: "black" } }
```

This is convenient for product catalogs where attributes vary by product category. However, if the application arbitrarily stores `price` in one place and `unitPrice` in another, or sometimes stores strings and sometimes numbers, reading code becomes complex and error-prone. MongoDB can enforce structural checks via a **collection validator**, in addition to validation at the API/application layer. Flexibility is only valuable when backed by **clear conventions for field names, data types, document versions, and strategies for upgrading old data**.

Conversely, modern RDBMSs also support JSON/JSONB columns and can combine relational data with flexible attributes. Having records with variable fields is not by itself sufficient reason to choose MongoDB.

### 3.2. `JOIN` vs. Embedding and `$lookup`

In relational databases, relationships are foundational. Applications can combine customers, orders, line items, and promotions without duplicating every detail into each row.

MongoDB supports `$lookup` to join collections when needed—for example, retrieving the customer name for an order:

```javascript
db.orders.aggregate([
  { $match: { _id: "ord-1001" } },
  { $lookup: {
      from: "customers",
      localField: "customerId",
      foreignField: "_id",
      as: "customer"
  } },
  { $unwind: "$customer" },
  { $project: { status: 1, items: 1, customerName: "$customer.fullName" } }
]);
```

This demonstrates that MongoDB **can perform joins at the query level**, though `$lookup` should not be treated as the default strategy for every relationship. Performance depends on data volume, indexes, filters, data distribution, and the execution plan. If business requirements demand ad hoc queries across many linked entities, a relational model is often more natural and easier to maintain.

### 3.3. Examples of Common Queries

**Retrieve the most recent orders for a customer:**

```sql
-- SQL
SELECT id, status, created_at
FROM orders
WHERE customer_id = 'cus-42'
ORDER BY created_at DESC
LIMIT 10;
```

```javascript
// MongoDB (mongosh)
db.orders.find(
  { customerId: "cus-42" },
  { status: 1, createdAt: 1 }
).sort({ createdAt: -1 }).limit(10);

// Useful index for this filter + sort
db.orders.createIndex({ customerId: 1, createdAt: -1 });
```

**Count orders by status:**

```sql
SELECT status, COUNT(*) AS total
FROM orders
GROUP BY status;
```

```javascript
db.orders.aggregate([
  { $group: { _id: "$status", total: { $sum: 1 } } },
  { $sort: { total: -1 } }
]);
```

Both SQL and MongoDB handle common filtering, sorting, counting, and aggregation tasks. Compare **real queries against real data** rather than drawing conclusions from syntax alone.

## 4. When to Embed Documents, When to Reference?

This is the most critical design decision when using MongoDB.

### Consider Embedding When

- Child components are **read together with** the parent object in most queries, such as line items of an order.
- The relationship has a **bounded and predictable** number of children, such as an invoice's shipping address or a few configuration parameters.
- Child data shares the same lifecycle as the parent, rarely needs independent querying, and requires atomic updates within the **same document**.
- Storing a point-in-time snapshot is acceptable: `productName` and `unitPriceCents` on historical orders do not need to change automatically when the current product changes.

### Consider Referencing When

- Child data grows without bound, such as millions of events from a device or comments on an article.
- An entity is shared by multiple objects and needs a single source of current truth, such as a user account or product inventory.
- Child data has a distinct lifecycle, access permissions, update cadence, or independent query patterns.
- Relationships are complex many-to-many or documents risk bloating, wasting bandwidth and resources on reads/writes.

**Limit to remember:** each BSON document in MongoDB has a maximum size of **16 MiB**. Embedded arrays that grow indefinitely over time will hit this limit and cause performance issues well before reaching it. For continuously growing logs or events, use a separate collection, an appropriate bucket/time-series pattern, or a specialized platform depending on the workload.

A practical model can combine both: `orders.items` embeds line-item snapshots; `orders.customerId` references the customer; `products` and `inventory` are separate collections. **Model around business boundaries and queries**, not a blanket rule of “embed everything” or “separate everything.”

## 5. Transactions, Atomicity, and Consistency

A common misconception is that “NoSQL has no transactions” or “MongoDB does not guarantee ACID.” Neither statement is true as an absolute.

### 5.1. Single-Document Updates

MongoDB guarantees that a write operation on a **single document** is atomic, even when modifying multiple fields or elements within that document. Example of decrementing stock conditionally if available:

```javascript
const result = db.inventory.updateOne(
  { _id: "book-01", stock: { $gte: 1 } },
  { $inc: { stock: -1 } }
);

if (result.modifiedCount !== 1) {
  print("Out of stock or product does not exist");
}
```

The filter and update execute as a single operation on the document, so two concurrent requests cannot simply read the same stale stock value and overwrite each other. You must check `modifiedCount` and handle errors in the application; this example alone does not solve the entire order placement workflow.

### 5.2. Multi-Document Transactions

A workflow like “create order + decrement inventory + record internal payment” can involve multiple documents. MongoDB **supports multi-document transactions** in appropriate deployments (replica sets or sharded clusters). Inside a transaction, changes can be committed together or rolled back on failure. However, transactions carry coordination and resource overhead; good document design should still prioritize sensible atomic boundaries.

RDBMSs typically provide a very convenient ecosystem of constraints and multi-table transactions for multi-entity operations. Whether using MongoDB or SQL, you must think carefully about **concurrency conditions**, retries, network failures, idempotency, and business invariants. Payments with external systems also require integration patterns (such as outbox/saga or idempotency keys), because a database transaction does not automatically make an external payment API part of the transaction.

### 5.3. Replica Sets, Read Concern, and Write Concern

MongoDB supports **replica sets** with a primary that receives normal writes and secondaries that replicate data. Reading from a secondary can observe data slightly behind the primary due to replication lag.

- **Write concern** specifies the acknowledgment level for a write operation; for example, `w: "majority"` requires acknowledgment from a majority of voting members according to MongoDB's mechanism.
- **Read concern** defines the consistency properties of data that a read operation is allowed to see, such as `majority` or `snapshot` in supported contexts.
- **Read preference** chooses where to read from (primary or secondary); it is distinct from read concern and affects data freshness.

You should not claim that “MongoDB is always strongly consistent” or “MongoDB is always eventually consistent” while ignoring these parameters and read/write patterns. Specific guarantees depend on read preference, read/write concern, sessions, and deployment topology. If business logic requires read-your-writes, causal consistency, or linearizable reads, you must choose the corresponding configuration and operation sequence, and verify against the documentation for your version.

### 5.4. CAP Is Not a Product Ranking

The CAP theorem describes a trade-off between **consistency** and **availability during a network partition** in distributed systems, with specific technical definitions. You cannot label “all RDBMSs as CA” or “all NoSQL as AP.” A single-node PostgreSQL instance, a MongoDB replica set, and a Cassandra cluster have different replication configurations leading to different behaviors. Beyond CAP, you must also consider latency, durability, transaction isolation, and conflict handling; during normal operation, these are the trade-offs encountered every day.

## 6. MongoDB vs. Other NoSQL Models

### 6.1. MongoDB and Key–Value Stores (e.g., Redis)

A key–value store optimizes get/set operations by key:

```text
SET session:abc123 "{...}"
GET session:abc123
EXPIRE session:abc123 1800
```

Redis supports many data structures and additional mechanisms beyond plain key–value strings; the commands above only illustrate a simple case. For expiring sessions, key-based caching, counters, or frequently accessed state data, key–value stores are often more natural than document databases.

MongoDB is more convenient when you need **multi-field filtering**, searching inside nested documents, indexing on attributes, and long-term data aggregation. Redis can persist data durably when configured, so do not equate Redis with “RAM that never writes to disk.” Choosing between Redis and MongoDB also depends on SLAs, working set size, storage model, and operational cost.

### 6.2. MongoDB and Wide-Column Stores (e.g., Cassandra)

Cassandra typically starts from the **queries to support** in order to design partition keys, clustering keys, and potentially denormalized tables. It excels when workloads involve heavy writes across a distributed cluster, high throughput, and predictable query patterns—for example, device events queried by `(device_id, day)` and ordered by timestamp.

MongoDB is more convenient for nested document structures, flexible attribute queries, and evolving product requirements. Cassandra does not provide RDBMS-style ad hoc joins or aggregations; conversely, MongoDB does not automatically outperform Cassandra across all write workloads. You must avoid oversized or hot partitions, define consistency requirements, and benchmark against selected queries.

### 6.3. MongoDB and Graph Databases (e.g., Neo4j)

In social networks, each person may have thousands of connections; questions like “friends of friends,” “shortest path,” or “suspicious link patterns” require multi-hop traversals. Graph databases store **vertices and edges** as first-class elements and typically provide dedicated path-query languages (such as Cypher in Neo4j).

MongoDB can store linked IDs in arrays, use `$lookup`, and use graph operators like `$graphLookup`. For shallow relationships or sparsely connected data, this can suffice. When graphs are large, densely connected, and multi-hop traversals dominate the workload, a graph database warrants thorough evaluation.

### 6.4. MongoDB and Search Engines (Elasticsearch/OpenSearch)

Looking up by `_id`, filtering `status`, and sorting by `createdAt` differ from text search requiring **stemming, typo tolerance, relevance ranking, autocomplete**, and multi-faceted analytics. MongoDB has indexes and text search capabilities; some deployments or services also provide dedicated search engines. Elasticsearch/OpenSearch are built around search and analytical indexes, fitting when search quality is a core requirement.

A common architecture is keeping transactional data in MongoDB or SQL and syncing searchable fields to a search index. In that setup, you must manage sync latency, retries, stale indexes, and index rebuild capabilities; **never implicitly assume two data stores synchronize instantaneously**.

## 7. Performance and Scalability: Factors to Measure

You cannot deduce speed from “documents are faster than joins” or “NoSQL scales horizontally better than SQL” without knowing the queries. Important factors include:

1. **Access patterns:** reading a single order with `items`, finding orders by `customerId`, aggregating monthly revenue, or traversing multi-hop relationship networks?
2. **Indexes:** indexes serving filters and sorts reduce scanned data, but each index consumes RAM/disk and increases write cost. Use `explain()` to inspect actual query plans.
3. **Document size:** embedding too many elements inflates payloads, makes updates expensive, and increases contention on the same document.
4. **Partitioned query patterns:** under sharding, shard key distribution determines load balancing. Low-cardinality or monotonically increasing keys can cause hot shards; queries without the shard key may need to scatter across multiple shards.
5. **Concurrent load and durability:** benchmarks must reflect read/write mix, p95/p99 latency, write concern, read concern, whether working sets fit in cache, index count, and hardware configuration.
6. **Operational cost:** RAM, disk, replicas, backup/restore, security, observability, version upgrades, and team expertise are all real costs.

MongoDB provides replication and sharding; RDBMSs also have replication, partitioning, extensions, or distributed SQL platforms. Do not choose MongoDB **solely because** you anticipate “needing horizontal scale later.” If queries depend heavily on relationships or complex constraints, distribution can make the problem harder regardless of which DBMS is chosen.

## 8. Scenario-Based Selection Matrix

| Scenario | First Option to Evaluate | Rationale and Considerations |
|---|---|---|
| Accounting ledger, balances, core payments | RDBMS with strong transactions/constraints | Multi-table invariants, auditing, and reconciliation matter more than attribute flexibility |
| Product catalog with diverse attribute types | MongoDB documents **or** PostgreSQL `jsonb` | Documents are flexible and easy to return in nested form; still requires schema/index management |
| Orders with bounded item lists | MongoDB (embedded snapshots) **or** RDBMS | MongoDB reads the aggregate conveniently; SQL fits if heavy cross-table queries and constraints are needed |
| Sessions/cache with TTL, accessed mainly by ID | Redis/key–value | Key-based access flow and short lifecycle; decide persistence/cache-miss policies |
| Massive event streams, read by device and time | Cassandra/ScyllaDB, time-series DB, or MongoDB time series | Compare ingest, retention, partitioning, query flexibility, and operations on real data |
| Friend recommendations, detecting anomalous link chains | Graph database | Path-based queries and multi-hop connections are the core business logic |
| Product search with typo tolerance and relevance ranking | Dedicated search engine or suitable integrated search | Search quality, indexing, and synchronization are critical requirements |
| Ad hoc financial reporting with many joins | RDBMS/analytics warehouse | SQL and multi-source aggregations typically fit better than a single-aggregate read model |

This matrix is a **starting point for experimentation**, not a mandatory decision. For example, an e-commerce application might use PostgreSQL for payments/orders, MongoDB for rich catalogs, Redis for caching, and OpenSearch for search. Conversely, small applications are often more effective starting with **one suitable database** and adding new systems only when evidence justifies the need.

## 9. Decision-Making Process for a Project

**Step 1 — List business workflows and invariants.** For example: “never oversell inventory,” “each transaction ID is processed only once,” “product name on an invoice does not change after ordering.” Identify transaction boundaries and what requires exact references.

**Step 2 — List the top 5–10 primary queries.** Specify filter conditions, number of returned records, read/write frequency, sorting, aggregations, data freshness requirements, and SLAs. Query patterns matter more than initial object diagrams.

**Step 3 — Sketch the data model around the workload.** For MongoDB, mark what is embedded and what is referenced; check for unbounded arrays, concurrent update contention, and index needs. For SQL, define keys, constraints, join tables, and multi-join queries.

**Step 4 — Define operations and distributed data behavior.** How should backup/restore work? What is the SLA after node failure? Are reads from secondaries needed? Is eventual propagation between the primary store and search index acceptable? Choose read/write concerns or isolation levels tailored to each workflow.

**Step 5 — Prototype and benchmark.** Load data at realistic scale, distribution, and churn; run primary queries and concurrent workloads. Measure p95/p99 latency, throughput, CPU/RAM, index size, code complexity, and operational effort. Also test node loss or network faults if the system requires high availability.

**Step 6 — Finalize data ownership.** When using multiple systems, designate the source of truth, synchronization mechanism, reconciliation procedures, and how to rebuild replicas. Avoid letting multiple systems be updated independently without consistency rules.

## 10. Misconceptions to Avoid

| Inaccurate Claim | Accurate Understanding |
|---|---|
| “MongoDB has no schema.” | Schemas can be flexible, yet data structure still exists and can be enforced by validators/application logic. |
| “MongoDB does not support transactions or joins.” | MongoDB has multi-document transactions and `$lookup`; evaluate cost and usage conditions. |
| “RDBMSs cannot store JSON.” | Many modern RDBMSs support JSON along with indexes and query operators. |
| “If you use MongoDB, just embed everything.” | Embedding has size, update, and lifecycle limits; referencing remains essential. |
| “NoSQL is always faster than SQL.” | Performance depends on queries, data model, indexes, caching, concurrency, and configuration. |
| “NoSQL doesn't need to worry about consistency.” | Every storage system must clearly specify guarantees and business invariants. |
| “One NoSQL product replaces all others.” | Key–value, document, wide-column, graph, and search optimize for different access patterns. |

## 11. Applied Exercises

**Scenario A — User Profile.** A profile includes name, UI settings, and up to three shipping addresses. The profile screen always loads all information; each user usually edits only their own profile. Propose an embedding approach and explain why. What changes if a single address is shared across thousands of accounts?

**Scenario B — Article Comments.** An article can have millions of comments, and comments are loaded paginated, sorted newest first. Should all comments be embedded in one article document? Propose appropriate collections, reference fields, and indexes.

**Scenario C — Placing Orders and Decrementing Inventory.** A customer sends two nearly simultaneous order requests while only one item remains in stock. Distinguish an atomic stock-decrement operation on a single document from a transaction that creates an order + decrements stock. If an external payment gateway already captured funds but the DB transaction fails, how should the system design compensation and idempotency?

**Scenario D — Product Search.** An application needs to filter by category, price, and brand while supporting typo tolerance and relevance ranking. Identify which parts MongoDB queries/indexes can solve and when to evaluate a dedicated search engine.

## Conclusion

MongoDB fits well when data has a document/nested structure, parts of an aggregate are frequently read together, and the schema must adapt to entity-specific attributes. Relational databases typically excel at tightly coupled relational models, integrity constraints, multi-entity transactions, and diverse SQL queries. Other NoSQL models—key–value, wide-column, graph, and search—address distinct access patterns that MongoDB is not necessarily optimized for.

A sound choice relies on **data model + real queries + business invariants + operations + benchmarks**, not on assumptions like “SQL is old, NoSQL is new” or “MongoDB is faster because it has no joins.”
