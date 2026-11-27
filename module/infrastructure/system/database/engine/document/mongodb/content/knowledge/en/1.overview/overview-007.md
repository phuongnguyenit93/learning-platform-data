# Prerequisites and Learning Path for MongoDB: From Document to Operations

MongoDB is a document-oriented database (document database). To use MongoDB effectively, learners need to progress through a connected chain of capabilities: **understanding how data is represented as documents → designing collections around how applications access them → reading, writing, and aggregating data correctly → measuring and optimizing queries → ensuring consistency and safety → deploying, backing up, monitoring, and troubleshooting**.

This guide builds a learning roadmap from basic programming knowledge to participating in operating a MongoDB system. Illustrative commands use **mongosh**, JavaScript, and a practice database named **`mongo_learning`**. Collection names, sample data, and figures are for learning purposes only; in real deployments, adjust them to your requirements, workload, and version in use.

## 1. Destination: What Should You Be Able to Do?

Someone completing this roadmap should be able to answer three groups of questions:

1. **Data:** Which document should represent an entity? When should you embed vs. reference? How do you protect data validity?
2. **Access:** Given real queries and updates, which indexes are needed? How do you tell whether MongoDB is scanning too many documents, where time is spent, and when transactions are required?
3. **Operations:** How does the system tolerate server failures? Is data backed up, recoverable, and secured? When latency spikes, disk nears capacity, or replication lags, in what order should you observe and respond?

### Knowledge Dependency Map

~~~mermaid
flowchart TD
    A["Foundations: JSON, HTTP, applications, data querying"] --> B["BSON, document, collection, _id"]
    B --> C["CRUD and queries"]
    C --> D["Schema design by access pattern"]
    D --> E["Validation, indexes, explain"]
    E --> F["Aggregation and performance"]
    F --> G["Atomicity, concurrency, transactions"]
    G --> H["Applications, drivers, connections"]
    H --> I["Replica sets and high availability"]
    I --> J["Sharding, horizontal scaling"]
    H --> K["Security, backup, recovery"]
    I --> K
    J --> L["Monitoring, tuning, and runbooks"]
    K --> L
~~~

This diagram shows the **recommended learning priority order**; in real projects, data design, indexing, security, and operational observability must be revisited iteratively together.

## 2. Prerequisites

| Foundation | How Deep Should You Know It? | Why Is It Needed? |
|---|---|---|
| Programming | Variables, functions, conditionals, loops, objects, arrays, exceptions | Read mongosh/driver examples, handle results and errors |
| JSON and data types | Nested objects, arrays, strings, numbers, booleans, null | Recognize document structure and understand differences from BSON |
| Databases | Persistent storage concepts, keys, queries, indexes, data constraints | Compare relational and document models accurately |
| Backend applications | HTTP → service → database flow, pagination, filtering, updates | Design data around how applications actually use it |
| Command line | Running programs, configs, reading logs, environment variables | Set up environments, diagnose issues, and run backups |
| Networking | Host, port, DNS, TLS, timeouts, dropped connections | Understand connection strings, client connections, and network failures |
| Operating systems | Processes, RAM, CPU, disk, file systems, permissions | Distinguish MongoDB issues from infrastructure issues |

Prior knowledge of relational databases or distributed systems is **not strictly required**, though SQL knowledge helps for comparison. If you are unfamiliar with indexes, transactions, or replication, you can learn them directly in the corresponding stages.

### Terminology Map

| SQL-Adjacent Concept | MongoDB | Key Difference to Remember |
|---|---|---|
| Database | Database | Contains collections |
| Table | Collection | Collections hold documents and do not require all documents to share the same fields |
| Row | Document | A BSON structure that can contain nested objects and arrays |
| Column | Field | A field can be a scalar value, object, or array |
| Primary key | `_id` | Unique within a collection; typically ObjectId, though other types can be used |
| Join | `$lookup` or embedding/referencing design | Not every relationship needs a join at read time |
| Index | Index | Accelerates certain queries while consuming storage and write overhead |

Do not think of MongoDB simply as “SQL with JSON data.” How you draw document boundaries and choose indexes heavily determines performance, consistency, and operational complexity.

## 3. Setting Up the Practice Lab

You need a compatible MongoDB server and **mongosh**. You can use a personal machine, a provisioned lab environment, or a managed cluster. Run write/delete examples only in a test environment.

Example running MongoDB with Docker for local learning:

~~~bash
docker run --name mongo-learning \
  -p 127.0.0.1:27017:27017 \
  -d mongo:8

mongosh "mongodb://127.0.0.1:27017"
~~~

The illustrative container does not have authentication enabled; use it locally only with the port bound to loopback. **Never expose an unauthenticated service to a public network**, and do not use this lab configuration in production. Production environments require access control, TLS, durable storage configuration, and recovery plans.

In mongosh:

~~~javascript
use mongo_learning
db.getName()
db.runCommand({ ping: 1 })
~~~

If the command returns `ok: 1`, the connection is working. When practicing replica set behavior, multi-document transactions, or sharding, you need a dedicated environment configured accordingly; **standalone MongoDB does not provide every cluster feature**.

### Running Dataset

Assume an e-commerce application with products, customers, and orders. For readability, IDs in the lab are human-readable strings; in a real application, choose a consistent ID strategy.

~~~javascript
use mongo_learning

db.products.insertMany([
  {
    _id: "p-101",
    name: "Keyboard",
    category: "accessory",
    status: "ACTIVE",
    price: NumberDecimal("125000.00"),
    stock: 10,
    tags: ["office", "usb"],
    createdAt: ISODate("2026-01-01T08:00:00Z")
  },
  {
    _id: "p-102",
    name: "Mouse",
    category: "accessory",
    status: "ACTIVE",
    price: NumberDecimal("99000.00"),
    stock: 20,
    tags: ["office", "wireless"],
    createdAt: ISODate("2026-01-02T08:00:00Z")
  },
  {
    _id: "p-103",
    name: "Monitor",
    category: "display",
    status: "HIDDEN",
    price: NumberDecimal("2900000.00"),
    stock: 4,
    tags: ["office"],
    createdAt: ISODate("2026-01-03T08:00:00Z")
  }
])

db.customers.insertOne({
  _id: "c-001",
  name: "Lan",
  contact: { email: "lan@example.test" },
  addresses: [
    { label: "home", city: "Hanoi", isDefault: true }
  ],
  createdAt: ISODate("2026-01-01T09:00:00Z")
})

db.orders.insertOne({
  _id: "o-1001",
  customerId: "c-001",
  status: "PAID",
  items: [
    {
      productId: "p-101",
      productName: "Keyboard",
      qty: 2,
      unitPrice: NumberDecimal("125000.00")
    }
  ],
  total: NumberDecimal("250000.00"),
  createdAt: ISODate("2026-01-05T10:00:00Z")
})
~~~

If you run the sample data script a second time, `insertOne/insertMany` with the same `_id` values will raise a duplicate key error. That is expected behavior; use a fresh database or intentionally clear lab data before repeating. **Never copy data-deletion commands into a live environment**.

## 4. Stage 1 — Understanding Documents, BSON, and Collection Boundaries

### 4.1. Documents Are Not Plain JSON

MongoDB stores documents as **BSON** (Binary JSON), supporting types beyond standard JSON, such as:

- `ObjectId`: an identifier value typically generated by MongoDB by default for `_id`.
- `Date`: a point in time; distinguish timezone-aware timestamp values from date strings.
- `Decimal128`: decimal numbers with precision suitable for many financial calculations.
- `Int32`, `Int64`, `Double`: distinct numeric representations.
- `Binary`, `Boolean`, `String`, `Array`, nested objects, and `Null`.

Example:

~~~javascript
db.examples.insertOne({
  title: "BSON types",
  publishedAt: new Date(),
  amount: NumberDecimal("19.95"),
  active: true,
  labels: ["intro", "database"],
  author: { name: "Mai", level: 2 },
  optionalNote: null
})
~~~

**A missing field differs from a field with value `null`**. This difference affects validation, filtering, and updates. When you need to filter strictly for field existence, use `$exists` and understand operator behavior when `null` is present.

A BSON document has a size limit of **16 MiB**. This is a critical architectural signal: do not embed unbounded event histories, comment lists, or endlessly growing data into a single document.

### 4.2. Thinking in Aggregates and Access Patterns

Ask “Which fields are usually fetched, displayed, and updated together?” before asking “Should every object be its own collection?”. For example:

- Customer shipping addresses can be embedded inside the customer document if the list is small and always displayed with the profile.
- Order line items are usually embedded inside the order; each line preserves `unitPrice` at purchase time so historical prices do not change when the catalog changes.
- Full product information belongs in the `products` collection; the order only retains necessary snapshots such as name and price.
- Continuously growing event streams or logs belong in a separate collection, partitioned or lifecycle-bounded as needed.

MongoDB guarantees atomicity for **a single write operation on a single document**. That is one reason document boundaries matter so much.

**Practice exercise:** Sketch the `customers`, `products`, and `orders` collections, marking which parts are owned data, which are snapshots, and which are references. Explain how to handle renaming a product after orders already exist.

**Done when:** You can read BSON documents, distinguish `_id`/fields/arrays, correctly identify three embedding/referencing structures, and point out at least one risk of unbounded document growth.

## 5. Stage 2 — CRUD: Reading, Filtering, Updating, Deleting

CRUD is the foundation for all data operations. You must be able to read filters, projections, sorts, limits, and common update operators.

### 5.1. Querying

~~~javascript
// Fetch active products without returning _id
db.products.find(
  { status: "ACTIVE" },
  { _id: 0, name: 1, price: 1, stock: 1 }
)

// Price at least 100000, sorted ascending
db.products.find({
  price: { $gte: NumberDecimal("100000.00") }
}).sort({ price: 1, _id: 1 }).limit(10)

// Filter tags array by a single element
db.products.find({ tags: "wireless" })

// Filter nested object using dot notation
db.customers.find({ "contact.email": "lan@example.test" })
~~~

In array queries, single-element matching like `{ tags: "wireless" }` matches documents containing that element. When multiple conditions must hold on the **same object element inside an array**, learn `$elemMatch`.

### 5.2. Updating

~~~javascript
// Update only specified fields without replacing the entire document
db.products.updateOne(
  { _id: "p-101" },
  {
    $set: { status: "ACTIVE" },
    $inc: { stock: 5 },
    $currentDate: { updatedAt: true }
  }
)

// Add a tag if not already present
db.products.updateOne(
  { _id: "p-101" },
  { $addToSet: { tags: "featured" } }
)

// Decrement stock only if sufficient: filter and update happen atomically
const result = db.products.updateOne(
  { _id: "p-101", stock: { $gte: 2 } },
  { $inc: { stock: -2 } }
)
print(result.modifiedCount)
~~~

In the final example, `modifiedCount === 1` indicates one document had its stock decremented. If it is 0, check whether the filter did not match or the condition was unmet, and return an appropriate business error. Avoid the **read quantity → check in application → write new quantity** pattern because concurrent requests can race.

### 5.3. Deletes, Upserts, and Idempotency

`deleteOne` and `deleteMany` permanently remove data; use them only on intentionally targeted records. `updateOne(..., { upsert: true })` can insert a document when none exists, but you must understand the matching key and the risk of duplicate creation under concurrent operations. Use unique indexes to enforce uniqueness when business logic requires it.

Do not use `skip` with very large offsets as your default pagination strategy. At a more advanced step, learn **keyset pagination**: fetching the next page via conditions on a stably ordered key tuple, such as `(createdAt, _id)`.

**Practice exercise:** Build a filter combining category/status/price returning at most 10 records; update tags and stock; use `$elemMatch` on a self-created array of objects; explain the conditions required so an update operation can be retried safely without inflating quantities.

**Done when:** You can write CRUD operations yourself, understand how `matchedCount` differs from `modifiedCount`, handle missing documents, and prevent lost updates caused by separating checks from write commands.

## 6. Stage 3 — Designing Schemas Around Access Patterns

MongoDB allows flexible documents, yet **flexible schema does not mean skipping data design**. Design starts with a list of use cases and query shapes, not solely with an entity diagram.

### 6.1. Gather Access Patterns Before Choosing a Model

Example for an e-commerce application:

| Business Workflow | Primary Read/Write | Modeling Suggestion |
|---|---|---|
Viewing cart/order with line items | One order, all `items` | Embed `items` in `orders` |
| Looking up a customer's order history | Multiple orders by `customerId`, newest first | Reference customer; index on `customerId, createdAt` |
| Displaying latest product price | Read `products` by `_id` | Product has its own source of truth |
| Viewing a price-locked order | Price at time of purchase | Snapshot `unitPrice` inside order |
| Continuously logging action events | High write frequency, continuously growing data | Separate log/event collection with appropriate retention |

### 6.2. Choosing Embed or Reference

**Prefer embedding** when child data has bounded size, shares the same lifecycle, is frequently retrieved together, and needs atomic updates within the same document.

**Prefer referencing** when data has an independent lifecycle, is shared across many documents, grows without bound, or needs independent querying. Referencing can lead to multiple queries or `$lookup`; measure its cost against real data and workloads.

Scenarios to watch:

- **One-to-one:** can be combined when lifecycles match and independent access is rare.
- **Bounded one-to-many:** embed as an array when size is controlled.
- **Unbounded one-to-many:** do not embed every element inside one parent document.
- **Many-to-many:** usually requires references or an intermediate structure; decide based on specific queries.
- **Snapshot data:** intentionally duplicating part of the data preserves accurate history; clearly distinguish synced fields from immutable fields.

### 6.3. Managing Schema Changes

As an application evolves, old and new documents can coexist. Determine:

1. Which fields are added, renamed, or changed in type?
2. Can older application versions still read newer documents?
3. Does historical data need backfilling, and can backfills run in batches?
4. Are new indexes created before deploying new queries?
5. Is an application rollback compatible with already-written data?

You can add `schemaVersion` when complex migrations are needed, but do not turn it into an excuse to bypass validation. For critical data, define and validate schemas even though the database allows flexibility.

**Practice exercise:** Redesign an article-commenting system where comment counts can grow very large. Write three target queries; decide which fields live in the article document, which live in the comments collection, planned indexes, and pagination strategy.

**Done when:** Every embed/reference decision is tied to a specific access pattern, size bound, atomicity requirement, or data lifecycle.

## 7. Stage 4 — Validation, Constraints, and Data Correctness

You cannot rely on document flexibility and assume all data is valid. Combine application-layer checks with **collection validation** and **unique indexes** when needed.

Example creating a separate collection with schema validation:

~~~javascript
db.createCollection("products_validated", {
  validator: {
    $jsonSchema: {
      bsonType: "object",
      required: ["name", "price", "stock", "status"],
      properties: {
        name:   { bsonType: "string", minLength: 1 },
        price:  { bsonType: "decimal" },
        stock:  { bsonType: ["int", "long"], minimum: 0 },
        status: { enum: ["ACTIVE", "HIDDEN"] }
      }
    }
  },
  validationLevel: "strict",
  validationAction: "error"
})
~~~

This example creates a new collection. The insert commands into `products` earlier in the guide are **not automatically** constrained by the validator on `products_validated`. In real applications, verify numeric types written by drivers: `2` may be encoded as different BSON number types depending on the driver or how the value is constructed.

### Three Layers of Correctness

- **Application validation:** business checks and user-friendly error messages, such as requiring quantity to be positive.
- **Database validation:** blocks malformed types or missing critical fields right at the storage layer; does not replace complex business logic.
- **Unique indexes:** for example, normalized email must be unique across users even when two account-creation requests arrive concurrently. Pay attention to missing/`null` values, collation, and whether the index is partial.

Reading write error outputs: `duplicate key` differs from `document validation failure` and from `network timeout`. A timed-out write **does not prove** the write failed to commit; retry strategies must consider idempotency, retryable writes, business locks, and actual state.

**Practice exercise:** Create a users collection enforcing unique emails per business rules and intentionally insert a duplicate; add a validator requiring `name` and `createdAt`; record the exact error types observed.

**Done when:** You clearly state which constraints live in the application, which live in the database, and explain why checking existence before inserting is insufficient to guarantee uniqueness.

## 8. Stage 5 — Indexes, Query Planner, and `explain`

Having a query return the right result is not enough; you must know how it performs as data grows. MongoDB can use indexes to avoid scanning many documents, yet every index consumes disk, memory, and increases update overhead.

### 8.1. Start from a Real Query

Suppose a catalog page requires: `status = ACTIVE`, `category = accessory`, sorted by price ascending.

~~~javascript
db.products.find({
  status: "ACTIVE",
  category: "accessory"
}).sort({ price: 1 }).explain("executionStats")

db.products.createIndex({
  status: 1,
  category: 1,
  price: 1
})

db.products.find({
  status: "ACTIVE",
  category: "accessory"
}).sort({ price: 1 }).explain("executionStats")
~~~

Metrics to compare include **`winningPlan`**, `totalKeysExamined`, `totalDocsExamined`, `nReturned`, and observed execution time. `COLLSCAN` generally indicates a collection scan; `IXSCAN` indicates a plan branch using an index. Merely seeing `IXSCAN` does not mean the query is optimal: it can still examine too many keys or fetch/filter many documents.

Because the sample dataset is tiny, the query planner may choose a full collection scan; that does not mean the index is wrong. Measure with representative data and production-like query shapes.

### 8.2. Index Types to Learn in Order

| Type | When to Learn/Use? | Things to Watch |
|---|---|---|
| Single-field | Filtering or sorting on one field | May not satisfy combined multi-field queries |
| Compound | Filtering multiple fields, sorting, ranges | Field order depends on workload; consider equality, sort, and range |
| Multikey | Field is an array | Indexes have specific semantics and restrictions when data is an array |
| Unique | Enforcing uniqueness | Existing duplicate data causes index creation to fail |
| Partial | Indexing only documents matching a filter | Queries must be compatible with the filter condition to use it |
| TTL | Automatically expiring lifecycle-bounded data | Deletion does not occur at the exact expiration second; does not replace retention/backup schedules |
| Text / dedicated search | Text search | Distinguish native text index capabilities from dedicated full-text search services |
| Wildcard / hashed / geospatial | Specialized workloads | Use only after understanding the queries and corresponding limits |

**Learning rule:** write the query first, inspect the plan, choose an index, re-run `explain`, and measure write and storage impact. Avoid creating indexes “on every field.”

### 8.3. Sorting and Pagination

A deterministic sort needs a tie-breaker for records with identical sort keys. Example for order history:

~~~javascript
db.orders.createIndex({ customerId: 1, createdAt: -1, _id: -1 })

db.orders.find({ customerId: "c-001" })
  .sort({ createdAt: -1, _id: -1 })
  .limit(20)
~~~

When order counts are large, you can use keyset pagination based on `createdAt` and `_id` of the last item on the previous page; construct comparison conditions matching the sort order and account for newly inserted data during pagination.

**Practice exercise:** Insert more demo documents, collect `explain("executionStats")` before and after indexing, and explain both scan counts and actual benefit. Write two queries with different access patterns and discuss whether one index can serve both.

**Done when:** You choose indexes from filters/sorts, read `explain`, understand read–write trade-offs, and never declare optimization based on a single run on a tiny dataset.

## 9. Stage 6 — Aggregation Pipeline

Aggregation processes data through a sequence of stages. Start with `$match`, `$project`, `$unwind`, `$group`, `$sort`, `$limit` before moving on to `$lookup`, `$facet`, and specialized stages.

Example calculating revenue per customer from paid orders:

~~~javascript
db.orders.aggregate([
  { $match: { status: "PAID" } },
  { $unwind: "$items" },
  {
    $group: {
      _id: "$customerId",
      revenue: {
        $sum: { $multiply: ["$items.qty", "$items.unitPrice"] }
      },
      itemCount: { $sum: "$items.qty" }
    }
  },
  { $sort: { revenue: -1 } }
])
~~~

Here, `$unwind` turns each `items` element into a separate input for grouping. If an order has multiple line items, doing `$sum: "$total"` after `$unwind` would **double-count the order total**; therefore, clearly define the unit of aggregation. Try adding an order with two line items to verify this in practice.

### Questions to Answer for Every Pipeline

1. What document shape does each stage receive and emit?
2. Does filtering early reduce the volume passed to later stages?
3. Does `$unwind` or `$lookup` multiply the row count?
4. Which stages use indexes and which must process/sort large volumes of data?
5. Do results depend on time zones, currencies, null/missing fields, or concurrent writes?

`$lookup` can join data from another collection, but if a screen frequently triggers heavy lookups, revisit your data model, indexes, and latency targets. Do not force an entire workflow into an overly complex pipeline solely to reduce API calls.

**Practice exercise:** Write a pipeline computing monthly order count and total revenue; add a date-range filter; compare filtering first/counting later against the reverse order; state which timezone defines month boundaries.

**Done when:** You can trace document shapes through each stage, catch double-counting bugs yourself, and analyze the costs of `$unwind`, `$sort`, `$group`, and `$lookup`.

## 10. Stage 7 — Atomicity, Concurrency, and Transactions

This stage bridges “a write command works” to “business logic stays correct when many requests arrive simultaneously.”

### 10.1. Single Document vs. Multiple Documents

MongoDB guarantees that a single write operation on one document is **atomic**. For an order embedding its items, updating status and adding fields within a single `updateOne` can be an atomic write.

When business logic must update multiple documents/collections—such as **decrementing stock and creating an order**—a distributed transaction may be needed. Before reaching for a transaction, still consider:

- Can data be structured so a single-document update suffices?
- Can a state workflow, reservation, outbox, or compensation pattern work cleanly?
- Is immediate cross-document consistency required?
- What are the transaction overhead, retry semantics, and cluster prerequisites?

### 10.2. Transaction Example in a Replica Set

The example below requires connecting to a replica set or sharded cluster supporting transactions. Use a fresh order ID and ensure repeated calls do not create duplicates:

~~~javascript
const session = db.getMongo().startSession()
try {
  await session.withTransaction(async () => {
    const txDb = session.getDatabase("mongo_learning")
    const stockResult = await txDb.products.updateOne(
      { _id: "p-101", stock: { $gte: 2 } },
      { $inc: { stock: -2 } }
    )
    if (stockResult.modifiedCount !== 1) {
      throw new Error("INSUFFICIENT_STOCK")
    }

    await txDb.orders.insertOne({
      _id: "o-1002",
      customerId: "c-001",
      status: "CREATED",
      items: [{
        productId: "p-101",
        productName: "Keyboard",
        qty: 2,
        unitPrice: NumberDecimal("125000.00")
      }],
      total: NumberDecimal("250000.00"),
      createdAt: new Date()
    })
  }, {
    readConcern: { level: "snapshot" },
    writeConcern: { w: "majority" }
  })
} finally {
  await session.endSession()
}
~~~

This example illustrates multi-document atomicity, **not a production checkout function**: you must handle uncertain commit outcomes, transient retryable errors, timeouts, duplicate orders, and request-level idempotency rules. Drivers usually provide dedicated transaction helpers; follow the documentation for your deployed driver/version. Do not blindly retry every error, and never place external side effects (sending emails, calling payment APIs) inside a callback that may re-execute without deduplication.

### 10.3. Read Concern, Write Concern, and Read Preference

| Setting | Question It Answers |
|---|---|
| Write concern | What write acknowledgment level is required before returning? E.g., `w: "majority"` |
| Read concern | What consistency/durability guarantees must read data satisfy? |
| Read preference | Read from primary or which secondary, and at what latency/staleness trade-off? |
| Retryable writes/transactions | Which retry conditions apply and when is repeating an operation safe? |

Do not equate `writeConcern: "majority"` with transactions, do not assume secondary reads return the latest data, and do not treat a timeout as proof that an operation never executed.

**Practice exercise:** Describe the race condition when two customers simultaneously buy an item with only one unit remaining; use a conditional update to handle stock deduction. Identify when a transaction is needed to write the order; design a rule preventing two orders when a request is retried.

**Done when:** You distinguish single-document atomicity from multi-document transactions and explain read/write concerns along with retry strategies.

## 11. Stage 8 — Application Connectivity and Data in Production

Learn a driver (Java, Node.js, Python, or your stack's language) after mastering queries in mongosh. In application environments, focus on:

- Managing `MongoClient`/connection pools across the application lifecycle rather than creating a new client per request.
- Connection strings and TLS, authentication, DNS, and timeout settings; store secrets in a secret manager or appropriate environment variables, never committed to Git.
- Mapping BSON types to application types: `ObjectId`, UTC timestamps, `Decimal128`, and 64-bit integers.
- Mapping exceptions to business errors: duplicate key, validation failure, timeout, transient error, unavailable primary.
- Pagination, projection, bounding returned document counts, cancellation/timeouts, and backpressure on large reads.
- Executing controlled migrations compatible with multiple application versions during rolling deployments.
- Collecting telemetry per operation/request while avoiding logging personal or sensitive data.

### An Observable Request Flow

~~~text
HTTP POST /orders
  -> authenticate and validate input
  -> resolve idempotency key / order identifier
  -> check and update data under concurrency rules
  -> write order/stock with appropriate atomic/transaction mechanism
  -> confirm outcome or classified error
  -> emit metrics/logs with correlation ID
  -> return stable HTTP status code and response
~~~

Evaluate designs with the question: “If the connection drops right after the server commits the write, what does the app return, is retrying safe, and can the user end up creating two orders?”.

**Practice exercise:** Build a minimal API to create and fetch orders. Test two concurrent requests buying the same product, resend the same idempotency key, and simulate a dropped connection. Observe responses, inventory, and order count.

**Done when:** The application leaks no credentials, uses proper pooling/timeouts, returns clear errors, and creates no duplicate data on valid retries.

## 12. Stage 9 — Replica Sets and High Availability

MongoDB typically uses **replica sets** to improve availability and maintain data copies. A replica set has a primary that receives most write operations and secondaries that replicate changes via replication. When the primary becomes unavailable, eligible members can elect a new primary.

~~~mermaid
flowchart LR
    App["Application / Driver"] --> P["Primary"]
    P -->|replication| S1["Secondary A"]
    P -->|replication| S2["Secondary B"]
    S1 -. "election when eligible" .-> P
    S2 -. "election when eligible" .-> P
~~~

This diagram simplifies the architecture. There is no guarantee that “losing primary = instantaneous zero-downtime failover”: elections take time, some in-flight operations must be retried, and applications need proper timeouts and recovery handling.

### Concepts to Distinguish

- **Primary / secondary:** member roles; the primary can change after an election.
- **Oplog:** operation log enabling secondaries to stay caught up; oplog window length matters for lagging or disconnected replicas.
- **Replication lag:** replication delay; affects data freshness when reading from secondaries and recovery capability.
- **Majority:** requires votes/acknowledgments matching configuration; not simply “write to every node.”
- **Election, quorum, partition:** determine which node can act as primary during network or server faults.
- **Read preference / concern:** select target node and consistency level; must align with API expectations.

Observation commands in a replica set environment:

~~~javascript
rs.status()
db.adminCommand({ hello: 1 })
~~~

Never reconfigure a replica set or intentionally step down/kill a primary on a live user-facing system just to test knowledge. Perform failover drills in a controlled lab cluster.

**Practice exercise:** Stand up a lab replica set following the guide for your deployed version; inspect node roles, trigger an intentional failover in the lab, record client symptoms and retry behavior. Explain why secondary lag does not mean data has been lost.

**Done when:** You can diagram the write/replication/election path, understand majority, and describe real availability limits during failover.

## 13. Stage 10 — Sharding and Scaling

**Replica sets** are usually introduced first to learn availability; **sharding** distributes data and load across multiple shards when a dataset or workload outgrows a simpler topology. A sharded cluster adds routers and placement metadata management.

~~~mermaid
flowchart TB
    Client["Client / Driver"] --> Router["mongos router"]
    Router --> S1["Shard 1 (replica set)"]
    Router --> S2["Shard 2 (replica set)"]
    Router --> S3["Shard 3 (replica set)"]
    Config["Config server replica set"] -. "cluster metadata" .-> Router
~~~

### The Shard Key Is a Major Design Decision

The shard key affects query routing, data distribution, write distribution, and the likelihood of **hotspots**. Evaluate:

1. Frequency and distribution of shard key values.
2. Do critical queries include shard key filters so they target the right shard?
3. Does the key have sufficient cardinality?
4. Do writes concentrate onto a monotonically increasing key range?
5. Are unique indexes, transactions, joins, and administrative operations constrained by sharding?

Do not learn sharding as “whenever data gets big, add shards.” Many problems are solved earlier through sound schemas, proper indexes, query tuning, vertical capacity, or retention policies.

**Practice exercise:** Assume 100 million orders where the main query is “orders by customer.” Compare sharding by `customerId`, `createdAt`, and a compound key; identify skew/hotspot risks and scatter-gather queries. Then observe routing in a lab cluster.

**Done when:** You distinguish replica sets from sharding, explain `mongos`, and build a shard key evaluation matrix grounded in workload rather than arbitrary guesses.

## 14. Stage 11 — Security and Access Governance

Security must be designed in early, though after understanding applications and clusters you can configure it more thoroughly:

- **Authentication:** authenticate clients and operators; configure it in managed environments instead of leaving databases open.
- **Authorization:** grant each app, migration job, and operator permissions matching its function; apply least privilege.
- **TLS:** encrypt connections and verify server identities/certificates properly; never disable certificate verification just “to make it work.”
- **Network isolation:** restrict allowed connection sources; do not expose database ports publicly when unnecessary.
- **Secrets management:** rotate passwords/tokens/certificates; never store raw passwords in source code, public URLs, logs, or screenshots.
- **Encryption at rest / backup protection:** review encryption mechanisms, key management, and replica storage policies.
- **Auditing and data governance:** define who can access/modify critical data, retention schedules, and deletion on request.

Example identity separation: an application only needs read/write privileges on its business database; cluster admin accounts and backup accounts should be separate from application accounts. Creating users, roles, or enabling authentication must follow the specific guide for your topology and deployment method.

**Practice exercise:** Build a permission matrix for the backend API, reporting jobs, backup jobs, and operators. For each role, specify database, collection, required actions, and revocation procedure. Test TLS/auth connectivity in the lab.

**Done when:** You no longer use admin accounts for every connection and can explain four defense layers: network, authentication, authorization, and secrets management.

## 15. Stage 12 — Backup, Restore, and Recovery Planning

**A replica set is not a backup.** If an application accidentally deletes data, the delete can replicate to secondaries. Backups must meet recovery goals for application bugs, accidental deletions, operator mistakes, or infrastructure failures.

### 15.1. Two Objectives Needed Before Choosing Tools

- **RPO (Recovery Point Objective):** how much data loss is acceptable, measured back from the incident?
- **RTO (Recovery Time Objective):** how quickly must the service be restored?

For example, “lose no more than 15 minutes of data” is an RPO requirement; “service back online within 2 hours” is an RTO requirement. A nightly dump usually cannot meet a 15-minute RPO without supplemental mechanisms.

### 15.2. Options to Understand

| Approach | Advantages | Limitations / What to Verify |
|---|---|---|
| `mongodump` / `mongorestore` | Logical backup, useful for labs and some data transfers | Must evaluate consistency, dump/restore duration, and system load |
| Storage snapshots | Can be efficient at the volume level | Must ensure snapshots are consistent with database state and topology |
| Managed backups / PITR | Can provide scheduled backups and point-in-time recovery | Depends on provider, retention, permissions, limits, and cost |
| Off-cluster backups | Isolated from cluster failure domains | Must encrypt, restrict access, test restores, and monitor capacity |

Example logical backup for the **lab** using the database created earlier:

~~~bash
mongodump --uri="mongodb://127.0.0.1:27017/mongo_learning" \
  --archive=mongo-learning.archive.gz --gzip

# Restore may append/overwrite depending on namespace and chosen options.
# Execute only into a prepared target lab database.
mongorestore --uri="mongodb://127.0.0.1:27017" \
  --archive=mongo-learning.archive.gz --gzip \
  --nsFrom="mongo_learning.*" --nsTo="mongo_restore_lab.*"
~~~

The multiline commands above assume a shell supporting `\` line continuations; in PowerShell, write on one line or use appropriate continuation syntax. Always test restores into an isolated target namespace/database and verify the outcome; never conclude restored data is usable merely because the tool exited with success.

### 15.3. A Successful Restore Requires Evidence

1. Verify the backup timestamp, retention policy, and access permissions.
2. Restore in an isolated environment using compatible configuration and version.
3. Verify document counts, critical collections, indexes, and validation rules.
4. Run representative business queries and check referential consistency.
5. Measure elapsed time from start until the application can use the data again.
6. Record deviations against RPO/RTO targets and update procedures.

**Practice exercise:** Create a lab backup, restore it into `mongo_restore_lab`, read back an order and its related product, and measure elapsed time. Write a recovery plan for accidentally dropping a collection at 14:00 when the latest backup was at 00:00.

**Done when:** You distinguish replication from backups, state RPO/RTO targets, and demonstrate a real restore + data verification.

## 16. Stage 13 — Observability, Tuning, and Incident Response

Once queries, data models, and clusters are running, operate using **measurable signals**. Rising query latency is not always caused by a missing index; it can stem from connection pool exhaustion, slow disks, memory pressure, replication lag, or traffic spikes.

### 16.1. Minimum Signals to Monitor

| Category | Representative Signals | Investigation Questions |
|---|---|---|
| Queries | p50/p95/p99 latency, slow operations, `explain`, scanned/returned ratio | Which queries are expensive and did plans change? |
| Load | Query/insert/update rates, connections, concurrency | Did traffic spike or did the pool saturate? |
| Resources | CPU, RAM/cache pressure, disk usage, disk I/O latency | Which resource limit was hit first? |
| Replica set | Member health, primary changes, replication lag, oplog window | Are reads lagging or is a failover underway? |
| Sharding | Data/load distribution, targeted vs. scatter-gather queries, hot shards | Is the shard key or data distribution skewing load? |
| Data | Collection/index growth rate, backup age, restore success | Is data outgrowing forecasts and still recoverable? |
| Security | Authentication failures, role changes, audit events | Is there anomalous access or a privilege change? |

In a lab environment, you can inspect tools/commands such as:

~~~javascript
db.stats()
db.products.stats()
db.serverStatus()
db.products.find({ status: "ACTIVE" }).explain("executionStats")
~~~

These commands require appropriate privileges and can return verbose output; in production, prefer controlled dashboards and telemetry. `explain` reflects the plan and stats for a single execution and does not replace long-term monitoring.

### 16.2. Runbook for Investigating a Slow API

1. **Define scope:** one endpoint, one collection, or the entire service? Start from p95/p99 latency and user-facing errors.
2. **Correlate timeline:** recent deployment, added index, schema change, traffic surge, failover, or backup job?
3. **Capture a representative query:** obtain real filter/sort/projection shapes with sensitive values redacted; run `explain` in an appropriate environment.
4. **Inspect the plan:** are there large scans, blocking sorts, or stages processing excessive documents?
5. **Inspect infrastructure:** pool usage, connection count, CPU, cache, storage latency, replication lag, and sharding routing.
6. **Propose a small measurable change:** adjust an index, query, projection, pagination, schema, or allowed setting; check write/disk impact.
7. **Monitor after change:** verify latency/error rates and rollback readiness; document root cause in the runbook.

### 16.3. Operational Scenarios to Practice

**Scenario A — Query jumps from 40 ms to 2 s.** Compare new requests/filters, `explain`, and scanned/returned ratios; check changes in document counts, indexes, sorts, and I/O pressure. Do not add indexes blindly.

**Scenario B — Writes fail during a primary step-down.** Check replica set health, verify application retry/timeout behavior, and check whether operations committed on the server without client acknowledgment. Verify idempotency before letting users retry manually.

**Scenario C — Disk nearly full.** Distinguish data size, index size, logs, backups, and abnormal growth. Prepare a safe capacity or retention plan; avoid deleting database data files directly.

**Scenario D — Restore succeeds yet API still errors.** Check namespaces, versions, indexes, validation rules, access permissions, connection strings, and business consistency. A restore is only complete when the application can serve data meeting targets.

**Done when:** You have a minimal dashboard, know how to select symptoms and measure before changing anything, have walked through at least one complete runbook, and documented root cause/evidence.

## 17. Suggested Week-by-Week Learning Sequence

Timelines are indicative only; extend any stage as needed. Do not study sharding merely because last week ended if you have not yet mastered documents, indexes, and concurrency.

| Phase | Priority Topics | Deliverable |
|---|---|---|
| Week 1 | Foundations, BSON, CRUD | Sample dataset + annotated query script |
| Week 2 | Access patterns, embed/reference, validation | Collection diagram, 5 key queries, and schema rules |
| Week 3 | Indexes, `explain`, aggregation | Before/after index report, 3 accurate pipelines |
| Week 4 | Atomic writes, transactions, driver/API | Order API preventing negative stock, handling retries/idempotency |
| Week 5 | Replica sets, read/write concern, security, sharding basics | Topology diagram and lab failover exercise |
| Week 6 | Backup/restore, metrics, capacity, incident response | Restore drill and incident-response runbook |

### Stage-Gate Rule

Each stage should produce **one runnable/verifiable artifact**: mongosh scripts, schemas, `explain` outputs, concurrency tests, topology diagrams, a restored backup, or a dashboard. Memorizing every operator is unnecessary; explaining your choices and showing how to verify them matters far more.

## 18. Capstone Integration Project

**Prompt:** Build an order-management backend with at least `customers`, `products`, `orders`, and an appropriate log/event collection. Minimum business requirements:

1. Create, edit, and search products by status, category, and price with stable pagination.
2. Place orders with multiple items, storing price snapshots at purchase time; never oversell inventory under concurrent requests.
3. View a customer's chronological order history and compute monthly total revenue.
4. Protect data using validation, unique indexes, and scoped application permissions.
5. Provide indexes matching real queries, accompanied by `explain` analysis.
6. Run the application against a lab replica set and record how the client handles a primary change.
7. Back up and restore into a separate environment, verifying data integrity and recovery duration.
8. Produce a dashboard or metrics report, along with a runbook for handling slow queries or disk pressure.

### Design Defense Questions

- Why are line items embedded in orders while the product catalog lives in a separate collection?
- If a product price changes after payment, are historical orders affected?
- If two requests decrement stock simultaneously, what condition prevents negative inventory?
- If the client times out after commit, what mechanism prevents creating a duplicate order on retry?
- Which index serves customer order history, and what is the evidence from `explain`?
- When reading from a secondary, under what circumstances can data be stale?
- If 10,000 orders are accidentally deleted, can a replica set recover them?
- What are the project's RPO/RTO targets, and have they been verified through a restore drill?

### Self-Assessment Rubric

| Competency | Foundational Level | Operations-Ready Level |
|---|---|---|
| Data model | Creates valid documents and collections | Justifies embed/reference using queries, growth, and atomicity |
| Querying | Writes accurate CRUD/aggregations | Analyzes plans/indexes, pagination, and workload limits |
| Consistency | Understands single-document atomicity | Handles concurrency, idempotency, transactions, and retries properly |
| Topology | Knows primary, secondary, shard | Understands lag trade-offs, failover, shard keys, and client impact |
| Safety | Knows authentication and backups | Implements least privilege, TLS, restore drills, and RPO/RTO targets |
| Operations | Reads basic metrics | Investigates with evidence, proposes changes, verifies after fixing |

## 19. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| “NoSQL means no schema” | Schema exists as data structure and application contracts; validation can and should be used |
| “The more you embed, the faster it gets” | Embed only when access patterns, size, and lifecycle fit; unbounded arrays create risks |
| “Having an index makes queries always fast” | Indexes only help matching workloads; queries can still scan many keys or trigger sorts |
| “Transactions solve everything” | Transactions add overhead and do not automatically solve idempotency or external side effects |
| “A replica set is a backup” | Replication copies bad changes too; backups must be independent and restorable |
| “Reading secondaries is always fast with no trade-off” | Can return stale data, affected by replication lag and consistency requirements |
| “Sharding just means adding machines” | Shard key, query routing, and load distribution determine scaling effectiveness |
| “Having a backup file means we are safe” | You need retention, access control, verified restores, and realistic RPO/RTO |
| “Every slow query is fixed by an index” | Slowness can come from schema, network, pools, hardware resources, contention, or topology |

## 20. Self-Study Checklist and Priority Order When Short on Time

If you are just starting out, study **document/BSON → CRUD → embed/reference → validation/indexes/`explain` → concurrency → backup/replica sets** first. Topics such as sharding, specialized indexes, and advanced cluster tuning should be studied deeply when real project requirements call for them.

- [ ] I can distinguish documents, collections, BSON, `_id`, and size limits.
- [ ] I can justify embed/reference choices from at least three real queries.
- [ ] I can use CRUD, update operators, array queries, and projections.
- [ ] I have validation, unique indexes, and data error handling in place.
- [ ] I can read `explain`, measure scans, and choose indexes based on workload.
- [ ] I can write pipelines using `$match`, `$unwind`, and `$group` without double-counting.
- [ ] I can handle inventory contention and request retries without creating corrupt data.
- [ ] I can distinguish atomic writes, transactions, read/write concerns, and read preferences.
- [ ] I understand replica sets/elections/lag and distinguish them from sharding.
- [ ] I apply least privilege, TLS, and secrets management.
- [ ] I have successfully restored lab data and checked against RPO/RTO targets.
- [ ] I can investigate a slow query using metrics, query plans, and resource status.

**The ultimate outcome of learning MongoDB** is not merely knowing query syntax, but building a data model that serves the business, proving its performance, and keeping the service recoverable when failures happen. Every decision should be backed by **representative queries, load assumptions, correctness invariants, and empirical verification**.
