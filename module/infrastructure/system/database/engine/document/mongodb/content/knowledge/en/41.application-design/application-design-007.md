# Choosing Standalone MongoDB vs. Combining with Other Data Systems

> **Module:** MongoDB Document Database Engine  
> **Chapter:** Application Design  
> **Lesson:** Choosing Standalone MongoDB vs. Combining with Other Data Systems

## 1. Opening Scenario: Should One Database Do Everything?

An e-commerce platform needs to store:

- A product catalog with attribute structures that vary by category.
- Orders and payments that must prevent duplicate writes and enforce state transitions.
- Carts and sessions with high read/write throughput and short lifetimes.
- Product search with Vietnamese language support, attribute filtering, ranking, and suggestions.
- Revenue dashboards and multi-year historical analytics.
- Product images, attachments, and large files.
- Data exported to an accounting system already running on PostgreSQL.

One proposal says: **“Use MongoDB for everything because a document database is flexible.”** Another says: **“Use the best database engine for each problem.”**

Both can be right in one context and wrong in another. A system with too many data stores can become harder to operate than the product requirements themselves; conversely, forcing one database to handle queries and contracts it fits poorly increases cost, latency, and inconsistency risks.

**Question to resolve:** When should MongoDB serve as a **standalone storage platform**, and when should it be **one component in a polyglot persistence architecture**—combining multiple data management systems as needed?

### 1.1. Learning Outcomes

After this lesson, you will be able to:

1. Evaluate MongoDB based on **access patterns, invariants, SLOs, costs, and operational capacity**, rather than NoSQL/SQL labels.
2. Recognize cases where MongoDB alone suffices: document data, aggregations, indexes, transactions, change streams, TTL, and integrated search where supported.
3. Recognize cases where relational databases, caches, search engines, message brokers, object storage, or data warehouses offer clear advantages.
4. Distinguish **source of truth**, caches, search indexes, read models, event logs, and analytical copies.
5. Design clear data boundaries in a system combining MongoDB with PostgreSQL, Redis, OpenSearch, Kafka, or other storage.
6. Analyze the dual-write problem, event ordering, retries, at-least-once delivery, idempotency, and reconciliation.
7. Apply transactional outboxes, change streams, CQRS, cache-aside, and backfills where appropriate.
8. Determine the required consistency level for each business path.
9. Build decision matrices with measurable criteria, failure simulations, and rollback plans.
10. Build prototypes on a test MongoDB instance with clear test data and cleanup boundaries.
11. Explain trade-offs across total cost, backups, access control, schema evolution, team capability, and future architectural evolvability.

## 2. Choose the Problem First, Not the Product Name

Database design should start from these questions:

- **Which data is read and written together?**
- Which queries generate most of the load?
- Which correctness invariants must never break, even during failover?
- How often do document structures and query shapes evolve?
- Is the data a source of truth or a derived copy for search/display?
- Do operations require multi-table/multi-collection transactions?
- Can search results and reports tolerate a few seconds of lag?
- If an auxiliary system goes down, must core business operations keep running?
- Does the team have the capacity to operate an extra cache, broker, and search cluster?

### 2.1. Workload Assessment Table

| Evaluation dimension | What to know | Why it matters |
| --- | --- | --- |
| Write patterns | Inserts/updates/deletes, batches, write amplification | Indexes, contention, durability |
| Read patterns | By ID, filtered lists, full-text, aggregations, graph traversals | Determines indexes, engines, and projections |
| Data shape | Nested documents, many-to-many relations, semi-structured data | Embedding vs. referencing strategy |
| Atomic boundary | Single document, multiple documents, multiple systems | Transactions and consistency |
| SLO | p95/p99 latency, uptime, RPO/RTO | Capacity and replication |
| Growth | Records, bytes, hot keys, tenants, retention | Sharding, partitioning, storage |
| Security | PII, tenancy, residency, auditing | Access control, encryption, compliance |
| Operations | Backups, upgrades, observability, runbooks | Total cost of ownership |
| Analytics | OLTP queries vs. multi-year scans | Separating analytical workloads |
| Team | Skills in MongoDB, SQL, Redis, Kafka, search | Operational complexity |
| Integration | Accounting, CRM, APIs, data lakes | Ownership and synchronization |

### 2.2. Never Decide Based on Data Volume Alone

A collection with 10 million records can run smoothly on MongoDB if queries are served by well-designed indexes. A collection with 20,000 records can still crawl if every request requires complex joins, unindexed sorts, repeated `$lookup` calls, or unbounded documents.

**Data volume does not replace workload analysis.** You need query shapes, cardinality, read/write ratios, skew, caching, query plans, and business invariants.

## 3. What Does Standalone MongoDB Mean?

In this lesson, “standalone MongoDB” means MongoDB acts as **the primary data management system sufficient for the application's storage and query needs**; it does not mean a single `mongod` server.

Production typically needs:

- A replica set for high availability, durability, and change streams.
- Sharding when workload or capacity demands it.
- Indexes, validators, TTL, and aggregations.
- Backups, PITR where supported, monitoring, and access control.
- Depending on platform: integrated Search/Vector Search or MongoDB-bundled services.

A “MongoDB-only” architecture can still include load balancers, object storage for large assets, application workers, and monitoring; the question here is **whether to add another stateful data store that requires synchronization**.

### 3.1. A Simple Architecture

```text
              Browser / Mobile
                    |
                 API layer
                    |
              Application services
                    |
          +---------+---------+
          |                   |
     Reads & writes      Background jobs
          |                   |
          +---------+---------+
                    |
              MongoDB cluster
         +----------+-----------+
         |          |           |
       Indexes   Aggregation  Change streams
         |          |           |
       Fast API    Reports   Internal workflows
```

If requirements are well served inside one cluster with clean collection boundaries, this can be cheaper and simpler to operate than adding 3–5 auxiliary systems.

### 3.2. What Does MongoDB Offer Beyond CRUD?

Do not rely on the stereotype that “a document database only looks up by `_id`”.

Depending on version and deployment, MongoDB provides:

- Secondary, compound, multikey, partial, unique, and TTL indexes.
- Aggregation pipelines including `$match`, `$group`, `$lookup`, `$facet`, `$setWindowFields`, and `$unionWith`.
- Document-level atomicity.
- Multi-document transactions on supported deployments.
- Schema validation via `$jsonSchema`.
- Change streams on replica sets and sharded clusters.
- Geospatial indexes and queries.
- Time-series collections.
- Basic full-text indexes; **MongoDB Search/Atlas Search** offers richer search depending on product/deployment.
- Vector Search on supported platforms/versions (not built into every standalone `mongod` by default).

However, having these capabilities **does not mean every workload runs optimally**. A supported `$lookup` still requires checking CPU, indexes, cardinality, network overhead, and p99 latency.

## 4. When Is MongoDB Alone a Reasonable Choice?

### 4.1. Documents Are the Natural Read/Write Unit

For example, products with attributes varying by category:

```javascript
{
  _id: "SKU-CHAIR-100",
  tenantId: "store-A",
  type: "furniture",
  title: "Office chair",
  priceCents: NumberLong("24500000"),
  attributes: {
    color: "black",
    material: "mesh",
    adjustableHeight: true
  },
  images: [
    {
      fileKey: "products/SKU-CHAIR-100/main.webp",
      role: "main"
    }
  ],
  updatedAt: ISODate("2026-11-14T04:00:00Z")
}
```

Another category has different attributes. When most APIs read one product document together and updates are product-scoped, the MongoDB document model helps:

- Read a product in minimal round trips.
- Store nested attributes without multiple auxiliary tables.
- Apply type/version-appropriate validation.
- Index frequently queried fields.
- Evolve schemas via controlled data migrations.

This is **not** a recommendation to cram all product-related data into one unbounded document.

### 4.2. Child Data Whose Lifecycle Is Bound to the Parent Document

An order snapshot:

```javascript
{
  _id: "order-123",
  customerId: "customer-9",
  status: "CREATED",
  lines: [
    {
      productId: "SKU-1",
      titleAtPurchase: "Notebook",
      unitPriceCents: NumberLong("300000"),
      quantity: NumberInt(2)
    }
  ],
  totalCents: NumberLong("600000"),
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

A snapshot of product names and prices at purchase time usually belongs inside the order because:

- Orders must be read as a unit.
- Live product price changes must never alter historical orders.
- Orders have bounded line items in most models.
- Order status updates can be atomic single-document updates.

However, if an “order” has millions of lines or continuously appended event histories, embedding creates huge documents, hotspots, and heavy update costs. Always check the **BSON document size limit (16 MiB)** and growth patterns.

### 4.3. Queries Served Clearly by Indexes

Example:

```javascript
db.orders.find({
  tenantId: "store-A",
  status: "PAID"
}).sort({ createdAt: -1 }).limit(30);
```

A candidate compound index:

```javascript
db.orders.createIndex(
  {
    tenantId: 1,
    status: 1,
    createdAt: -1
  },
  {
    name: "orders_tenant_status_created"
  }
);
```

If this is your core workload, MongoDB can serve it very well once index fit, dataset size, and read/write SLOs are verified in practice.

Do not add Elasticsearch just to filter by tenant/status and sort by timestamp when a MongoDB index already solves it.

### 4.4. Moderate Rate of Multi-Document Transactions

MongoDB supports multi-document transactions. If the application occasionally needs to update an order and a ledger entry atomically, you do not have to migrate the entire system to an RDBMS.

However:

- Transactions have overhead, especially long-running or cross-shard ones.
- Never put external HTTP, email, or payment calls inside a MongoDB transaction.
- Sessions, write concerns, and retry labels are required.
- Transactions do not automatically normalize data like a relational schema.

### 4.5. Sufficient Aggregation Instead of a Data Warehouse

A small operational dashboard over recent data:

```javascript
db.orders.aggregate([
  {
    $match: {
      tenantId: "store-A",
      status: "PAID",
      createdAt: {
        $gte: ISODate("2026-11-01T00:00:00Z")
      }
    }
  },
  {
    $group: {
      _id: {
        day: {
          $dateTrunc: {
            date: "$createdAt",
            unit: "day",
            timezone: "Asia/Ho_Chi_Minh"
          }
        }
      },
      count: { $sum: 1 },
      revenueCents: { $sum: "$totalCents" }
    }
  },
  { $sort: { "_id.day": 1 } }
]);
```

For bounded time windows and moderate frequency, aggregation can suffice. If hundreds of analysts continuously scan years of data joined with finance/marketing datasets, a dedicated analytical store makes more sense.

## 5. When Should You Consider a Relational Database?

### 5.1. Relationships Are Central to the Domain

A system with many interconnected entities:

```text
Customers --< Orders --< OrderItems >-- Products
    |           |
    |           +--< Payments
    |
    +--< Addresses
```

If business operations routinely require:

- Joining many tables naturally.
- Database-enforced foreign keys and referential integrity.
- Complex multi-table constraints.
- Ad hoc SQL queries by analysts and operations teams.
- Multi-entity transactional schemas.
- Integration with an SQL-based ERP/accounting ecosystem.

then PostgreSQL, MySQL, or a suitable RDBMS may be the **better primary database**.

MongoDB offers `$lookup` and transactions, yet it **does not enforce RDBMS-style foreign-key constraints across collections**. Choose based on the invariants you must enforce and your query shapes, not merely whether joins can be emulated.

### 5.2. A Referential Integrity Example

In PostgreSQL:

```sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    email TEXT NOT NULL
);

CREATE TABLE orders (
    order_id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL
        REFERENCES customers(customer_id),
    amount_cents BIGINT NOT NULL
        CHECK (amount_cents >= 0)
);
```

`REFERENCES` guarantees orders cannot point to non-existent customers within RDBMS transaction semantics.

In MongoDB, you can store `customerId` on an order, yet preventing orphan references requires application logic and/or transactions and reconciliation. If this is a core invariant and relationships mutate constantly, an RDBMS can be simpler.

### 5.3. Do Not Assume SQL Is Always Faster at Every Join

SQL query planners, indexes, and relational constraints are powerful, yet an RDBMS also slows down under poorly designed queries, indexes, and schemas. Likewise, MongoDB `$lookup` works well on bounded datasets with good indexes.

Evaluate with **representative queries + data shapes + p95/p99 + operations**, not single microbenchmarks or “SQL vs. NoSQL” slogans.

### 5.4. When an RDBMS Is Already the Source of Truth

Never mirror all data from PostgreSQL into MongoDB simply because a new team prefers document models. Answer first:

- Which use case cannot be served reasonably by PostgreSQL?
- Could a view, materialized view, JSONB column, or index solve it first?
- Is MongoDB the primary store for a new bounded context, or merely a read projection?
- Who owns consistency and gap recovery?
- Do the benefits outweigh the cost of another cluster, outbox, and CDC pipeline?

**A healthy existing system does not need another database just to adopt new technology.**

## 6. When Does Combining MongoDB with PostgreSQL/MySQL Make Sense?

### 6.1. Separating Bounded Contexts by Ownership

Example:

```text
                 API Gateway
                     |
           +---------+---------+
           |                   |
      Catalog Service      Billing Service
           |                   |
       MongoDB             PostgreSQL
     products / offers    invoices / ledger
           |                   |
           +------ Events -----+
                     |
              Read projections
```

Catalog has rich, fast-evolving attributes; Billing needs transactional ledgers, constraints, and SQL integrations. Each service owns writes to its own database.

**Principle:** database ownership per bounded context beats letting every service write directly into every database.

### 6.2. Avoid Cross-Database Transactions Unless Truly Necessary

An operation:

```text
1. Insert product into MongoDB
2. Insert billing record into PostgreSQL
```

If step 1 succeeds and step 2 fails, data becomes temporarily inconsistent. A MongoDB transaction covers only MongoDB; a PostgreSQL transaction covers only PostgreSQL. Two separate transactions do not create system-wide atomicity.

Approaches:

- Choose **one source of truth** per business event.
- Use outbox/event-driven projections so the other system receives a derived copy.
- For workflows genuinely spanning two owners, use sagas/compensation with intermediate states.
- If an indivisible synchronous invariant is mandatory, consider keeping both writes inside one database's transaction boundary.

### 6.3. MongoDB Can Serve as an RDBMS Read Projection

Suppose Accounting/PostgreSQL is the source of truth for invoices, and MongoDB holds a read model:

```javascript
{
  _id: "invoice-123",
  customerId: "customer-9",
  invoiceNumber: "INV-123",
  amountCents: NumberLong("450000"),
  status: "PAID",
  searchTokens: ["INV-123", "customer-9"],
  sourceVersion: NumberLong("18"),
  projectedAt: ISODate("2026-11-14T04:30:00Z")
}
```

When receiving events:

- Only the Billing writer updates PostgreSQL.
- A MongoDB projector upserts by invoice ID.
- `sourceVersion` stops older events from overwriting newer ones.
- Projections can be rebuilt if events are missed.
- Never let APIs write directly to the projection and treat it as a real invoice change.

### 6.4. An RDBMS Can Serve as a MongoDB Read Projection

Conversely, MongoDB can be the source of truth for catalog/orders while PostgreSQL stores reporting tables for SQL BI.

Both directions work when **ownership is clear**, whereas letting two databases act as “co-primaries” for the same field without a conflict-resolution protocol is a recipe for bugs.

## 7. MongoDB and Redis: A Cache Is Not an Automatic Transactional Replica

### 7.1. When Redis Helps

Redis is commonly evaluated for:

- Caching hot reads with short TTLs.
- Session/ephemeral state when requirements match.
- Rate limiting and lightweight counters with purpose-built correctness.
- Queues/streams where workload and durability semantics align.
- Ultra-low-latency reads to offload the primary database.

You do not need Redis right away if MongoDB indexes already meet SLOs and the cluster is not under read strain.

### 7.2. Cache-Aside

```text
            Application
                |
        GET product by ID
                |
           Redis cache?
             /       \
          HIT        MISS
           |           |
         return     MongoDB read
                       |
                    cache set
                       |
                     return
```

Flow:

1. Read from cache using a tenant/version-aware key.
2. On miss, read from MongoDB.
3. Cache the result with a TTL.
4. On successful MongoDB update, invalidate the cache.
5. During cache outages, fall back to MongoDB with backpressure.

### 7.3. Subtle Race Conditions

```text
T1 Reader misses cache, reads old product from MongoDB
T2 Writer updates product in MongoDB
T3 Writer invalidates Redis key
T4 Reader caches old product
```

At T4, the cache holds stale data **after** invalidation. Mitigations include:

- Versioned cache keys.
- CAS/version checks on cache set.
- Short TTLs + stale-data budgets.
- Versioned invalidation events.
- Single-flight/request coalescing where suitable.
- Avoiding caching fields requiring strong consistency.

Never claim “update DB then DEL Redis is always consistent”.

### 7.4. Never Put Critical Balances or Inventory Only in Cache

If Redis is the sole store for a balance and persistence/recovery does not meet business contracts, restarts, evictions, or failovers can violate invariants.

When caching balances from MongoDB, decide whether stale reads are tolerable during transactional decisions. For charges or settlements, verify against the authoritative store via atomic operations or transactions.

### 7.5. Redis Adds Operational Overhead

Adding Redis introduces:

- Cache keys and versioning.
- Eviction and TTL policies.
- Memory sizing.
- Warm-up and cache stampede protection.
- Purpose-appropriate backup and failover.
- Security and credentials.
- Consistency and correctness tests.
- Fallback behavior when Redis is unavailable.

**Only add it when latency or cost gains clearly outweigh these costs.**

## 8. MongoDB and Elasticsearch/OpenSearch: Specialized Search

### 8.1. When a Dedicated Search Engine Helps

When you need:

- Multi-field full-text search.
- Vietnamese analyzers and tokenization.
- Relevance ranking, fuzzy matching, synonyms, and autocomplete.
- Multi-dimensional facets/analytics for search UIs.
- Highlighting and complex scoring.
- Search workloads scaling independently from OLTP.
- Engine-specific search/vector/hybrid features.

an engine like OpenSearch or Elasticsearch can be a strong fit.

### 8.2. Yet MongoDB Also Has Search

Before adding a search cluster, check:

- Do basic MongoDB compound/text indexes already suffice?
- Is MongoDB Search/Atlas Search available on your tier, region, and version?
- Do its search features satisfy the product team?
- When using integrated search, do you still meet SLOs and independent scaling needs?

Never state “MongoDB doesn't support full-text” or “vector search requires another engine” without checking your exact product and deployment capabilities.

### 8.3. Search Indexes Should Be **Derived State**

```text
MongoDB (products authoritative)
               |
          Change stream / Outbox
               |
               v
        Search indexer
               |
       OpenSearch index
               |
        Search API / UI
```

A search hit does not prove a product is still active or in stock. Purchase flows must verify state against the source of truth.

### 8.4. Late Events and Update Ordering

```text
Product P version 12 -> price 100
Product P version 13 -> price 120
Events arrive search indexer as: 13, then 12
```

If the indexer writes blindly, search price regresses to 100. Remedies:

- Emit `sourceVersion` or monotonic per-document event sequences.
- Index/update with version checks.
- Deduplicate events by event ID.
- Record versioned tombstones for deletes.
- Support backfills/reindexing and monitor index lag.
- Handle out-of-order and duplicate deliveries in consumers.

### 8.5. Indexing Must Not Sit Inside Order Transactions

Never put an HTTP call to OpenSearch inside a MongoDB transaction expecting joint atomicity. Commit the authoritative product and outbox inside MongoDB, then let an indexer update search asynchronously.

If the search engine goes down, product writes still succeed while search UI shows slightly stale data for a bounded window. If business rules forbid that lag, revisit data boundaries or synchronous verification.

## 9. MongoDB and Kafka/Message Brokers: Events Differ from Current State

### 9.1. Different Roles

MongoDB stores current state and document histories per your data model. A broker like Kafka provides event-log/stream distribution, retention, and partitioned consumer offsets per its architecture.

```text
                  MongoDB
              Order source of truth
                      |
             Outbox / CDC relay
                      |
                      v
                 Kafka topic
                 /    |    \
                v     v     v
          Search   Billing  Analytics
```

This architecture shines when multiple independent subscribers need buffering and scaled event processing. Conversely, a small app with a single background worker can often consume a change stream directly without a broker.

### 9.2. Change Streams Are Not Equivalent to Kafka Consumer Groups

MongoDB change streams:

- Read changes from oplog history.
- Use resume tokens.
- Retain finite history bounded by the oplog.
- Deliver the same events to each independent watcher.
- Do not natively provide Kafka-style consumer-group partition load balancing.

Kafka:

- Retains records by topic/partition and retention policy.
- Consumer groups manage partition assignments and offsets.
- Requires key/ordering design, retries, and DLQs.
- Brings broker, topic, schema evolution, and operational costs.

The two systems do not replace each other automatically; a CDC pipeline often pairs them.

### 9.3. Domain Events Differ from Database Changes

A change event:

```javascript
{
  operationType: "update",
  documentKey: { _id: "order-123" },
  updateDescription: {
    updatedFields: { status: "PAID" }
  }
}
```

only reports a document mutation. A domain event:

```javascript
{
  eventId: "order-123:paid:version-7",
  eventType: "OrderPaid",
  orderId: "order-123",
  paymentId: "payment-1",
  occurredAt: ISODate("2026-11-14T04:00:00Z"),
  schemaVersion: NumberInt(1)
}
```

captures **business intent**. Not every status update represents an actual payment; translating change events into domain events must respect invariants and source fields.

### 9.4. Reliability Still Matters Without a Broker

A consumer reading a change stream directly still requires:

- Durable resume-token checkpoints.
- Idempotent processing.
- Monitoring oplog history windows.
- Recovery from `ChangeStreamHistoryLost`.
- Graceful shutdown.
- Worker ownership across multiple pods.
- Re-bootstrapping when tokens expire.

Never use “we didn't add Kafka” as an excuse to skip delivery guarantees.

## 10. MongoDB and Data Warehouses/Lakehouses: OLTP Differs from OLAP

### 10.1. Distinguishing Goals

**OLTP (online transaction processing)** focuses on:

- Point reads and writes.
- Queries by key/tenant.
- Low latency and high concurrency.
- Business operation correctness.
- Hot working sets and indexes.

**OLAP (online analytical processing)** focuses on:

- Large columnar/partitioned scans.
- Aggregations and joins across huge datasets.
- Long-term historical data.
- Analysts, BI, and scheduled reporting.
- Cost-effective batch/scan throughput.

MongoDB aggregation handles many operational reports well; there is no rule saying “every `$group` requires a warehouse”. However, if analytical queries routinely scan massive transactional tables and spike API p99, offloading OLAP may be necessary.

### 10.2. Architecture for Separating Analytical Copies

```text
Operational APIs
      |
      v
   MongoDB
      |
      +------ CDC / export / ETL ------+
                                      |
                                      v
                                 Data Lake /
                                Data Warehouse
                                      |
                            BI / SQL / ML / Reports
```

Analytical data is a **lagged, schema-versioned copy**, never the authoritative write path for orders.

### 10.3. Choosing a Refresh Model

| Sync method | Best fit | Risk |
| --- | --- | --- |
| Nightly batch export | Daily reports | Stale data, job failures |
| Incremental CDC | Near-real-time analytics | Event replays, ordering, schema drift |
| Snapshot + CDC | Bootstrapping large datasets | Snapshot-to-stream gaps |
| Scheduled aggregates | Bounded dashboards | Skew from late events |
| Recompute from source | Periodic reconciliation | Scan cost |

Explicitly define **freshness SLOs**: “revenue report updates within 5 minutes” differs fundamentally from “account balance is always exact before payment”.

### 10.4. Reconciling Analytical Numbers

Numbers can diverge due to:

- Timezones and day boundary definitions.
- Data windows and watermarks.
- Late-arriving events.
- Deletes, updates, and event retractions.
- Duplicates from CDC retries.
- Different exchange rates or tax rules.
- Aggregation semantics for cancelled/refunded statuses.

Never compare two dashboards and declare one database “wrong” before aligning metric definitions.

## 11. MongoDB and Object Storage: Not Every Byte Belongs in a Document

### 11.1. Images and Large Files

MongoDB documents have a **16 MiB size limit**. While MongoDB provides GridFS for files exceeding that limit, most web apps favor object storage (S3-compatible, Google Cloud Storage, Azure Blob, etc.) paired with CDNs for images, videos, and large files.

Example where MongoDB stores metadata:

```javascript
{
  _id: "product-SKU-1",
  title: "Office chair",
  assets: [
    {
      assetId: "asset-100",
      objectKey: "products/SKU-1/main.webp",
      contentType: "image/webp",
      sizeBytes: NumberLong("310000"),
      checksumSha256: "hash-of-file",
      status: "READY"
    }
  ]
}
```

Binary bytes live in object storage; MongoDB holds keys, references, and metadata.

### 11.2. Two Systems Lack a Shared Transaction

Upload flow:

```text
Client uploads object
          |
          v
Object storage write
          |
          v
MongoDB metadata write
```

If object upload succeeds and MongoDB insert fails, you get an orphan file. If metadata writes first and upload fails, the API points to a missing file.

Use a state machine:

```text
INITIATED -> UPLOADING -> READY
                 |
                 +------> FAILED / CLEANUP_PENDING
```

Include orphan cleanup and reconciliation in runbooks instead of assuming two systems commit atomically.

### 11.3. Enforcing Permissions on `objectKey`

An object key is not an authorization token. The API must verify tenant/ownership when issuing signed URLs, uploading/downloading, and modifying metadata.

Never store expiring signed URLs long-term; store the object key/asset ID and generate URLs on demand once authorized.

## 12. Combining MongoDB with Graph Databases or Vector Stores

### 12.1. Graphs: When Multi-Hop Traversal Is the Primary Workload

A social or fraud-network platform must query:

- Friends of friends of friends.
- Shortest paths.
- Subgraphs and cycle detection.
- Constantly shifting multi-hop connections.

MongoDB offers `$graphLookup` and document references, which cover moderate use cases. However, when deep, dynamic graph traversals over dense edges dominate the workload, a dedicated graph database may be worth evaluating.

Never pick a graph database merely because an order references a `userId`.

### 12.2. Vector Search

If the application needs semantic search or RAG:

- MongoDB Vector Search is available on certain deployments/tiers with specific index/config requirements.
- Dedicated vector databases can be evaluated if specific scale, filtering, model operations, or recall/latency targets demand them.
- OpenSearch/Elasticsearch and some RDBMSs also provide vector capabilities via extensions/products.
- Outcomes depend on embedding models, chunking, filter selectivity, recall targets, p95/p99, costs, and data privacy.

Never claim one engine is “always best” for vector search. Prototype with representative data, ground-truth relevance, and load tests.

### 12.3. Vectors/Indexes Are Derived State

If content is edited or deleted in MongoDB before the vector index updates, RAG may answer from stale or revoked documents. Enforce event versions, delete propagation, ACL filters, freshness SLOs, and reindexing/reconciliation.

## 13. Overview Table: Appropriate Roles for Each System

| Component | Typical best role | Authoritative source? | Key pitfalls to watch |
| --- | --- | --- | --- |
| MongoDB | Document OLTP, nested entities, aggregations, change streams | Can be source of truth | Indexes, data model, transactions |
| PostgreSQL/MySQL | Relational transactions, FKs, SQL workloads | Can be source of truth | Joins, constraints, migrations |
| Redis | Caching, ephemeral state, rate limits | Usually not for critical data | Staleness, eviction, persistence |
| OpenSearch/Elasticsearch | Full-text, relevance, facets | Usually a projection | Reindexing, ordering, lag |
| Kafka/broker | Event distribution, retention, buffering | Event log can be source by architecture | Offsets, schemas, partitions |
| Warehouse/lakehouse | BI/OLAP, long-history analytics | Usually an analytical copy | Freshness, late data, cost |
| Object storage | Large files/media, archival blobs | Source for binary bytes | Orphan cleanup, ACLs, checksums |
| Graph database | Relationship traversal workloads | Depends on bounded context | Syncing edges, identifiers |
| Vector store | Semantic similarity retrieval | Usually a derived index | Recall, ACLs, stale embeddings |

This table describes **roles**, not a shopping list. Many products need neither Redis, Kafka, a warehouse, nor a search cluster if MongoDB and clean application design already satisfy requirements.

## 14. Sources of Truth and Replicas: The Most Important Rule in Polyglot Systems

### 14.1. Each Data Field Should Have One Write Owner

Suppose product `priceCents` appears in:

- The MongoDB product document.
- The Redis cache.
- The OpenSearch search index.
- The Warehouse reporting table.

Who decides the new price? If every component updates and pushes back against each other, uncontrollable conflicts follow.

A clean ownership layout:

```text
Catalog Service owns price
             |
             v
MongoDB authoritative product
             |
             +----> Redis cache (derived)
             +----> OpenSearch (derived)
             +----> Warehouse (derived)
```

Never let a web admin edit prices directly in OpenSearch and expect MongoDB to sync backward automatically.

### 14.2. Authority Need Not Be One Database for the Entire Enterprise

For instance:

- Catalog owns product attributes in MongoDB.
- Billing owns invoices/payments in PostgreSQL.
- Identity service owns user credentials in an identity provider.
- Media service owns file bytes in object storage.
- Search serves an indexed copy.

**One owner per aggregate/business fact**, not “one database as source of truth for every system”.

### 14.3. Defining Data Flow and Contracts

In design documentation:

```yaml
dataProduct: ProductCatalog
owner: CatalogService
authoritativeStore: MongoDB/products
eventContract: ProductChanged/v2
derivedStores:
  - Redis/product-cache
  - OpenSearch/product-index
  - Warehouse/dim_products
freshnessSlo:
  redis: "seconds"
  search: "under 1 minute"
  analytics: "under 30 minutes"
rebuildSource: MongoDB/products + versioned events
conflictResolution: authoritative source version wins
```

This is application design YAML, **not a MongoDB configuration file**. Sample SLOs must be measured and agreed upon per product.

## 15. What Kind of Consistency Do You Need?

Not every API requires the same consistency.

### 15.1. Classifying by Impact

| Use case | Example | Consistency typically needed |
| --- | --- | --- |
| Financial decision | Charge payment, withdraw, settle | Very strict, enforced at source |
| Inventory reservation | Hold remaining units | Atomic conditional update/transaction |
| Product detail | Name, description, images | Short cache staleness acceptable |
| Search results | Product index | Eventual consistency with freshness SLO |
| Dashboard | Hourly revenue | Batch or near-real-time per business |
| User authentication | Sessions/permissions | Must not be stale in ways that grant wrong access |
| Audit/retention | Business history | Durability, immutability policy, backups |
| Recommendations | Product suggestions | Lagged data acceptable |

### 15.2. Strong Consistency Lives on the Authoritative Write Path

If a transaction depends on available inventory, never read a stale Redis cache and assume the authoritative store will agree.

In MongoDB, you can use:

```javascript
db.inventory.updateOne(
  {
    _id: "SKU-1",
    available: { $gte: 2 }
  },
  {
    $inc: {
      available: -2,
      reserved: 2
    }
  }
);
```

This is a single-document atomic conditional update. If order/stock/ledger span multiple collections and must stay synchronized, use transactions or compensation per business boundaries. If inventory lives in PostgreSQL, enforce the invariant in PostgreSQL—not in Redis.

### 15.3. Read-Your-Writes and Secondary Lag

MongoDB replica sets offer read concern, write concern, and read preference, plus causal consistency per session where eligible.

A `w:"majority"` acknowledgment does **not** automatically mean **every secondary query will immediately see the new version**, especially if secondary replication/application lags. In MongoDB 8.0, majority acknowledgment semantics also changed with respect to secondary oplog durability vs. collection application.

If an API updates status and immediately reads it back for the response, route the read to guarantee required visibility; never assume secondary `readPreference` provides read-your-writes.

### 15.4. Cross-DB Consistency Is Not Free

```text
MongoDB product price=120
Redis cache price=100
Search index price=100
Warehouse price=80
```

This may be an acceptable transient state within freshness SLOs, or a live incident if strict immediate propagation is required.

Distinguish **permitted inconsistency within a window** from **correctness violations** before designing synchronization.

## 16. The Dual-Write Problem: The Biggest Risk in Polyglot Persistence

### 16.1. Two Separate Writes Have Many Failure States

Broken pattern:

```java
mongoProducts.replaceOne(...);
searchClient.index(...);
```

What can happen:

1. MongoDB succeeds, search fails.
2. MongoDB times out yet actually succeeded; search may or may not be called.
3. Search succeeds, MongoDB fails (if reversed).
4. Both succeed, yet the API response is lost.
5. Concurrent updates/events arrive out of order.
6. The process crashes between the two writes.

There is no shared distributed transaction across MongoDB and OpenSearch/Redis/Kafka in standard calls.

### 16.2. Reversing the Order Does Not Fix It

Switching:

```text
MongoDB -> Redis
```

to:

```text
Redis -> MongoDB
```

does not achieve atomicity—it merely moves the crash window.

### 16.3. Write to the Authoritative System First, Then Sync Derived Stores

```text
                 Business request
                        |
                        v
             Authoritative DB commit
                        |
                        v
                Durable change/event
                        |
                   Async delivery
                 /      |       \
                v       v        v
             Cache    Search    Analytics
```

If a derived store fails, the primary business write is not left in an ambiguous state just because search indexing failed—unless the business contract explicitly demands synchronous coupling.

## 17. Transactional Outbox When MongoDB Is the Source of Truth

### 17.1. The Outbox Pattern

Within **the same MongoDB transaction**, write the business document and the outbox record:

```text
begin transaction
    |
    +--> update products
    |
    +--> insert outbox event
    |
commit
    |
relay watches/polls outbox
    |
publish to broker/search/cache worker
```

If commit succeeds, both business state and outbox record coexist; if aborted, both roll back. This closes the gap where “business committed yet no record remembers to sync”.

### 17.2. An Outbox Event Document

```javascript
{
  _id: "product-SKU-1:version-8",
  aggregateType: "Product",
  aggregateId: "SKU-1",
  aggregateVersion: NumberLong("8"),
  eventType: "ProductChanged",
  eventSchemaVersion: NumberInt(1),
  payload: {
    title: "Office chair",
    priceCents: NumberLong("24500000")
  },
  state: "NEW",
  createdAt: ISODate("2026-11-14T04:00:00Z")
}
```

Notes:

- `_id` is a stable, unique event identity.
- `aggregateVersion` stops stale replays from overwriting newer state.
- Payloads carry only what consumers need; avoid leaking excessive PII.
- Include mechanisms for event schema evolution, retention, and replay.
- Never equate `state:"SENT"` with exactly-once external delivery if ACKs can be lost.

### 17.3. Relays Can Deliver Events Multiple Times

```text
Read outbox E8
      |
Publish E8 to broker
      |
ACK lost
      |
Relay retries E8
      |
Broker/consumer may see duplicate
```

Consumers must be **idempotent**:

- Deduplicate by event ID.
- Unique inbox keys.
- Upsert projections by aggregate ID.
- Compare incoming version against processed version.
- Retries with backoff and DLQs.
- Monitor backlogs and lag.

A transactional outbox ensures **publishing intent** is never lost after commit, yet does not eliminate duplicate deliveries by itself.

### 17.4. Change Streams Can Act as the Relay

MongoDB change streams can watch outbox inserts and checkpoint resume tokens. However:

- Requires a replica set or sharded cluster.
- Oplog history is finite.
- Resume tokens must be saved only after side effects succeed.
- History loss requires backfill/reconciliation.
- Multi-pod relays need ownership/fencing or partitioning.
- Since un-dispatched outbox records remain `NEW`, a polling/recovery sweep can rescue events missed due to history loss.

Design outboxes with durable state and retries as **a complete workflow**; never treat change streams alone as an infinite-retention broker.

## 18. CQRS: Separate Read and Write Models When Benefits Are Clear

### 18.1. Concept

**CQRS (Command Query Responsibility Segregation)** separates the write model enforcing invariants from read models optimized for queries.

```text
       Commands                        Queries
           |                              |
           v                              v
      Write Model                    Read Model
       MongoDB                        MongoDB /
           |                         Search / SQL
           |
        Outbox events
           |
           +----------------------------->+
```

You do not need two different database technologies. CQRS can use **two MongoDB collections** with different schemas.

### 18.2. When Separating Read Models Helps

An API renders an order dashboard showing:

- Customer name.
- Product names at purchase time.
- Payment status.
- Order total.
- Fulfillment status.
- Multi-field sorting and filtering.

Instead of running `$lookup` across 4 collections on every request, build a projection:

```javascript
{
  _id: "order-123",
  tenantId: "store-A",
  customerName: "Demo customer",
  productNames: ["Notebook", "Pen"],
  orderTotalCents: NumberLong("600000"),
  paymentStatus: "PAID",
  fulfillmentStatus: "PACKED",
  sourceVersion: NumberLong("12"),
  projectedAt: ISODate("2026-11-14T04:00:00Z")
}
```

Read models can lag. The UI must understand the freshness SLO and re-verify at the source for decisions that cannot tolerate stale reads.

### 18.3. CQRS Has Costs

- Event schemas and versioning.
- Backfills.
- Rebuilding broken projections.
- Event delivery, idempotency, and ordering.
- Lag metrics and reconciliation.
- API consistency contracts.
- Duplicated storage.

If a simple index on the source collection already solves the query, splitting out a projection adds unnecessary complexity.

## 19. Identity and Versioning: Two Prerequisites for Safe Synchronization

### 19.1. IDs Must Be Stable

A product record may live in several stores. Establish a shared identity:

```text
MongoDB _id:      SKU-1
Redis key:        product:SKU-1:v8
Search document:  SKU-1
Warehouse key:    SKU-1
```

Avoid inventing unrelated IDs per layer without an explicit mapping, as deduplication, deletion, and reconciliation become painful.

### 19.2. Versions Prevent Backward Overwrites

Example current projection:

```javascript
{
  _id: "SKU-1",
  sourceVersion: NumberLong("11"),
  title: "Chair A"
}
```

The indexer receives version 12 before version 10. With a conditional update:

```javascript
db.product_projection.updateOne(
  {
    _id: "SKU-1",
    sourceVersion: { $lt: NumberLong("12") }
  },
  {
    $set: {
      sourceVersion: NumberLong("12"),
      title: "Chair B"
    }
  }
);
```

you still must handle **the document not existing yet** and concurrent upsert races. One approach routes events by aggregate ID to an ordered consumer, or uses transactions/CAS and unique `_id` with duplicate-key retry handling. Never run a naive `upsert:true` with a `sourceVersion:$lt` filter without accounting for duplicate `_id` insert collisions.

### 19.3. Deletes Need Tombstones or Versions

If a delete immediately erases the search document, a delayed older event can recreate the deleted product. Store a tombstone:

```javascript
{
  _id: "SKU-1",
  sourceVersion: NumberLong("13"),
  deleted: true,
  deletedAt: ISODate("2026-11-14T05:00:00Z")
}
```

Consumers ignore events with versions lower than 13. Tombstone retention must cover the retry/replay window and data governance rules. When deleting for privacy compliance, design tombstone/payload retention so unnecessary PII is not kept.

### 19.4. Versions Must Have Clear Semantics

- `updatedAt` is not always safe due to clock skew and precision.
- `ObjectId` embeds a timestamp but provides no global ordering guarantee.
- `clusterTime` is not a per-aggregate business version.
- Per-aggregate sequences managed by the authoritative writer are easiest to reason about.
- In multi-region/multi-writer setups, conflict resolution takes more than a single integer.

Never use `Date.now()` as a global cross-database version.

## 20. Guaranteeing Atomicity at the Source Before Emitting Events

### 20.1. Single-Document Atomicity

A command updating price and incrementing version:

```javascript
db.products.updateOne(
  {
    _id: "SKU-1",
    tenantId: "store-A",
    version: NumberLong("7")
  },
  {
    $set: {
      priceCents: NumberLong("25000000"),
      updatedAt: new Date()
    },
    $inc: {
      version: 1
    }
  }
);
```

If the product document holds all required state, an atomic update is a solid foundation. If the outbox event lives in another collection, ensuring both the product update and outbox insert commit together normally requires a transaction.

### 20.2. Transactions in MongoDB

```javascript
const session = db.getMongo().startSession();
const sdb = session.getDatabase("commerce");

try {
  session.withTransaction(() => {
    // Update product and insert outbox event.
    // Every operation must use the same session.
    // Never call external services inside the callback.
  });
} finally {
  session.endSession();
}
```

This is a skeleton; real implementations must handle versions, transaction retries, write concerns, session lifecycles, supported commands, and namespaces. Callbacks can retry, so external side effects inside callbacks can repeat.

### 20.3. Never Span a Transaction Across an Entire Business Workflow

An order → payment gateway → shipping provider workflow can take minutes or hours. Never hold a MongoDB transaction open across that span.

Use a **saga / state machine**:

```text
OrderCreated
    |
ReserveInventory
    |
RequestPayment
    |
PaymentConfirmed/Failed
    |
CreateShipment / ReleaseInventory
```

Each step uses a local transaction, idempotency key, retries, timeouts, and compensation. State transitions require auditing and recovery.

## 21. Data Format and Schema Rules Across Systems

### 21.1. BSON Differs from JSON and SQL Types

MongoDB has:

- Int32, Int64, Double, Decimal128.
- Date, Timestamp.
- ObjectId.
- Binary UUID with subtypes.
- Embedded documents/arrays.
- Distinct null vs. missing.

When transferring to SQL, Redis JSON, Kafka JSON, or search indexes:

- `NumberLong("9007199254740993")` loses precision if parsed as a JavaScript Number.
- Decimal128 must not become Double for money.
- ObjectId does not automatically equal a String ID.
- BSON Date is a UTC instant and stores no original timezone.
- Missing differs from explicit null.
- Arrays of objects map differently than normalized SQL rows.

### 21.2. Mapping Contracts Need a Specification Table

| MongoDB field | Source type | Projection type | Rule |
| --- | --- | --- | --- |
| `_id` | String or ObjectId | String key | Stable canonical mapping |
| `amountCents` | Int64 | BIGINT/long | Never pass through floating point |
| `priceDecimal` | Decimal128 | DECIMAL(p,s) | Verify precision and scale |
| `createdAt` | BSON Date | TIMESTAMP WITH TIME ZONE | Preserve UTC instant |
| `tags` | Array String | Array/child rows | Define ordering and duplicates |
| `optionalField` | Missing/null/String | Nullable + presence marker | Do not collapse if domain distinguishes them |
| `schemaVersion` | Int32 | Integer | Versioned evolution |

### 21.3. How Do Event Schemas Evolve?

Event v1:

```javascript
{
  eventType: "ProductChanged",
  schemaVersion: 1,
  payload: { price: "120.00" }
}
```

Event v2:

```javascript
{
  eventType: "ProductChanged",
  schemaVersion: 2,
  payload: { priceCents: NumberLong("12000") }
}
```

Consumers must:

1. Read both v1 and v2 during transition periods.
2. Map units and decimals accurately.
3. Never read only the new field and drop older backlog events.
4. Run backfill/replay tests against retained events.
5. Define when v1 support can be retired.

Stream contracts can be harder to migrate than collections because consumers deploy independently.

## 22. Backfilling When Adding a Derived Store for the First Time

### 22.1. Mistake: Scanning First and Starting CDC Afterward

```text
T0 Snapshot MongoDB products starts
T1 Product SKU-1 updated
T2 Snapshot finishes
T3 Search indexer starts watching changes
```

The update at T1 can be missed. This is the **snapshot-to-stream gap**.

### 22.2. A Checkpointed Process

```text
Establish CDC start boundary
           |
Start capturing/buffering changes
           |
Scan authoritative snapshot in batches
           |
Build derived projection with version checks
           |
Replay buffered/new events
           |
Reconcile counts, checksums, versions
           |
Cut over read traffic when lag acceptable
```

Exact details depend on MongoDB version, oplog window, topology, CDC tooling, snapshot strategy, and target system. Never assume opening a change stream suffices if a backfill takes days while the oplog holds only a few hours.

### 22.3. If Oplog History Is Lost

When the resume token falls out of history, never silently “watch from now” and claim search/warehouse is consistent.

Instead:

- Raise an alarm.
- Pause cutover while the projection is untrusted.
- Rebootstrap or reconcile from source data.
- Establish a gap-free new boundary.
- Log the decision/audit trail.
- Track recovery progress.

### 22.4. Backfills Need Versioning/CAS

If a snapshot reads version 5 while CDC already applied version 6, backfill must never overwrite version 6 with version 5. Use ordered commits, conditional version checks, or post-backfill reconciliation.

## 23. Phased Migration from MongoDB-Only to Polyglot

### 23.1. Phase 0 — Identify the Real Root Cause

Do not add Redis because a few requests are slow due to a missing index; do not add a search cluster because a query uses an unoptimized `$regex` on a small collection.

Collect:

- Top queries and slow queries.
- `explain` `totalKeysExamined`/`totalDocsExamined`.
- p50/p95/p99 and throughput.
- CPU, memory, WiredTiger cache, and disk latency.
- Required query semantics (relevance, fuzzy, facets, etc.).
- Current and projected costs.
- Team support burden.

### 23.2. Phase 1 — Optimize MongoDB First

Try:

- Compound indexes tailored to query patterns.
- Projections to shrink payloads.
- Bounded keyset pagination.
- Reviewing embedding vs. referencing.
- Separating hot and cold data cleanly.
- Optimizing aggregation pipelines.
- Materialized views inside MongoDB where suitable.
- MongoDB's built-in search capabilities on your existing deployment.
- Business-aligned read/write concerns.

This does not mean optimizing at any cost; the goal is discovering **which genuine limits force splitting**.

### 23.3. Phase 2 — Add the Derived Store in Shadow Mode

```text
Production reads -> MongoDB
        |
     CDC/outbox
        |
        v
New Search/Cache/Read model (not serving users yet)
```

Use the shadow store to:

- Populate data.
- Reconcile versions and IDs.
- Measure lag and cost.
- Verify correctness.
- Test fallback when the target is unavailable.
- Audit ACLs and PII.

### 23.4. Phase 3 — Canary Read Traffic

Only once shadow checks pass:

- Route a small read-only cohort.
- Compare results and freshness.
- Keep fallback to authoritative reads if policy allows.
- Set SLOs and error budgets.
- Put routing behind a feature flag for quick rollback.

For search UIs, ranking differences may be expected; measure relevance/recall and product acceptance rather than exact JSON equality.

### 23.5. Phase 4 — Ramp Up and Operate

After canary:

- Scale the target store.
- Enable alerts on lag, backlogs, and version mismatches.
- Train on-call engineers on runbooks.
- Test backups, reindexing, and recovery.
- Update security and retention policies.
- Compare actual vs. projected costs.
- Retire old code paths only after evidence and a rollback window.

## 24. What If You Must Move Primary Ownership to Another System?

This is harder than adding a cache or search projection.

For example, moving Orders authority from MongoDB to PostgreSQL:

```text
Old ownership: MongoDB orders
New ownership: PostgreSQL orders
```

Challenges include:

- BSON → relational schema mapping.
- Business constraints and ID mapping.
- Historical data and backfills.
- Concurrent writes and conflicts.
- Cutover atomicity.
- API and client compatibility.
- Transaction and session semantics.
- Rollback after writes occur on the new primary.

A process typically requires:

1. Defining ownership at every phase.
2. Dual-read/shadow comparisons without letting both systems accept arbitrary authoritative writes.
3. Checkpointed, versioned synchronization.
4. Quiesce/cutover or explicit writer fencing protocols.
5. Read-after-write validation.
6. Tested reconciliation and rollback plans.
7. Marking the old system read-only during cutover.
8. Retiring old paths only after verifying data and consumers.

Never use “permanent dual-writes to two primaries” as a simplistic shortcut for ownership migration.

## 25. Full Example: Rental Management Application

Suppose an application manages:

- `properties`: diverse property attributes.
- `availability`: open dates and bookings.
- `bookings`: rental contracts.
- `payments`: transactions and reconciliation.
- `search`: search by location, amenities, price, keywords.
- `analytics`: revenue by region and month.
- `photos`: property images and videos.

### 25.1. Option A — MongoDB as Primary with Minimal Components

```text
Web / Mobile
     |
API services
     |
MongoDB
  properties
  bookings
  availability
  payment references
  query indexes / aggregation
     |
Object storage for images
```

Viable when:

- Reading property documents is the main workload.
- Booking invariants are enforced via atomic conditional updates or transactions.
- Available search/aggregation suffices.
- Volume and SLOs fit cleanly.
- The team wants minimal operational overhead.

Do not stuff entire payment-gateway state machines into property documents; payments are a separate bounded context with their own security and transaction contracts.

### 25.2. Option B — Role-Based Polyglot

```text
                  API Gateway
                       |
             +---------+---------+
             |                   |
       Listing Service       Booking Service
             |                   |
          MongoDB           PostgreSQL
             |                   |
        Catalog events       Booking events
             |                   |
             +--------+----------+
                      |
             Event relay / broker
              /       |       \
             v        v        v
        Search idx   Redis    Warehouse
             |
        Search API
             
   Object storage <- Media Service
```

This makes sense when:

- Listing attributes vary heavily.
- Bookings need relational constraints and integrations.
- Search relevance/facets require a dedicated engine.
- Analytics scan deep historical volumes.
- Request scale and team ownership justify operational complexity.

### 25.3. Bookings Must Never Be Decided Solely from Search or Cache

Search may display a room as “available” due to projection lag. At booking time:

1. API calls the authoritative Booking service.
2. The service checks availability/invariants and holds inventory via atomic write or transaction.
3. Commits with appropriate durability.
4. Emits an event to update search/cache.
5. If events lag, the UI may show stale availability briefly, yet the booking service **never oversells**.

Temporary display lag is tolerable; double-booking the same room/time slot is not.

### 25.4. Do Not Propagate Renter Data Everywhere

Renter PII should not land in search indexes, caches, and warehouses simply by replicating entire MongoDB documents. Design minimal projections:

```javascript
{
  propertyId: "property-123",
  city: "HCM",
  amenityTags: ["wifi", "parking"],
  nightlyPriceCents: NumberLong("750000"),
  availableFrom: ISODate("2026-12-01T00:00:00Z"),
  sourceVersion: NumberLong("30")
}
```

Never send customer phone numbers, ID documents, or payment details into search if unnecessary.

## 26. Second Example: IoT and Time-Series

A sensor ingestion system:

```javascript
{
  sensorId: "sensor-100",
  observedAt: ISODate("2026-11-14T04:10:00Z"),
  temperatureC: 28.3,
  humidityPct: 70.0,
  siteId: "site-A"
}
```

### 26.1. MongoDB-Only Can Suffice

- Time-series collections fit well where supported by version and deployment.
- Queries filter by sensor and time window.
- TTL retention matches needs.
- Moderate-frequency alerts and aggregations.
- No immediate requirement for full-history SQL BI.

### 26.2. When Other Systems Are Needed

- Kafka/broker when ingest bursts are massive and require partitioned buffering and fan-out.
- Warehouse/data lake for multi-year analytics.
- Search for log text if full-text querying is required.
- Redis for hot dashboard caching.
- Object storage for raw payloads and files.

### 26.3. Tiered Storage Design

```text
Sensors -> Ingest API / Broker
                 |
          MongoDB hot operational window
                 |
          Scheduled/CDC export
                 |
          Object storage / Warehouse
                 |
          Long-term analytics
```

Define retention, archival, replay, and which system holds the source of truth for raw events. If TTL deletes hot MongoDB data before export finishes, historical data is lost.

## 27. Total Cost of Ownership: A Second Database Is More Than Hardware

### 27.1. How to Calculate

Evaluation framework:

```text
TCO =
  Infrastructure cost
+ Data transfer/network cost
+ Storage/replication/backups
+ Engineering development
+ Operations/on-call
+ Security/compliance
+ Failure recovery/reconciliation
+ Migration and future change cost
```

When adding an auxiliary database, include:

- Storage for duplicated data.
- Indexes and replication on both systems.
- CDC pipelines and brokers.
- SLO monitoring and alerting.
- Reindexing, replays, and backfills.
- Schema migrations and versioning.
- Credential/key rotation and access reviews.
- Disaster recovery when systems restore from snapshots at different timestamps.
- Staffing for operations and training.

### 27.2. Resource Savings vs. Synchronization Cost

Suppose Redis cuts MongoDB read load by 40%, yet:

- Cache invalidation races trigger incidents.
- Redis memory and on-call support add overhead.
- Stale product prices hurt UX.
- Data contracts become harder to test.

If MongoDB only needed a better index or modest scaling to meet SLOs, Redis may yield negative net value.

### 27.3. Split When Independent Scaling Is Required

A strong reason for polyglot: search or analytics need to scale independently from OLTP. If heavy reports on MongoDB keep pushing API p99 up, offloading to a warehouse delivers:

- Steadier API SLOs.
- Purpose-built batching and compute.
- Clear workload cost attribution.
- Isolation preventing analyst queries from starving primary resources.

The trade-off is data freshness lag and pipeline operations.

## 28. Security and Governance Across Multiple Data Stores

### 28.1. Duplicating Data Expands the Blast Radius

MongoDB provides RBAC, encryption, and network controls. Copying data to Redis, Search, and a Warehouse places the same PII in 3–4 places, each with its own:

- Credentials.
- Backups and snapshots.
- Logs and profiling.
- Retention policies.
- Access policies.
- Audit trails.
- Deletion obligations.

“MongoDB is already encrypted” does not mean the copy in Search is protected.

### 28.2. Tenant Isolation Is Not Just in MongoDB

If source queries always filter `tenantId` yet OpenSearch queries omit it, the system leaks data across tenants.

Every projection must:

- Carry tenant scope or ACL metadata.
- Enforce authorization at the API layer.
- Never rely on frontend filtering as a security boundary.
- Verify index/search permissions.
- Pass negative cross-tenant access tests.
- Keep sensitive data out of public search.

### 28.3. Right to Erasure and Data Retention

When a user requests deletion or retention expires:

```text
Delete from authoritative store
             |
        Deletion event
          /   |    \
         v    v     v
      Cache Search Analytics
```

If a target is offline, deletion events must retry; source deletion alone does not fulfill compliance obligations. Track completion states, alerts, and audits. Apply appropriate retention/legal holds to backups.

### 28.4. Multi-System Disaster Recovery

A restore mismatch:

```text
MongoDB restore to 10:05
Search restore to 10:15
Warehouse snapshot at 09:00
```

Search may hold product events that MongoDB rolled back or lost. Do not merely restore each system independently—**rebuild or reconcile derived stores from the authoritative state** after DR.

If another system holds its own source of truth, maintain a per-bounded-context recovery plan instead of blindly “replaying every event”.

## 29. Observability: Measure Drift, Not Just Uptime

### 29.1. Metrics for the MongoDB Authoritative Path

- Read/write p50/p95/p99.
- QPS and error rates.
- CPU, WiredTiger cache, disk IOPS/latency.
- Replication lag and elections.
- Connections and pool wait times.
- Slow queries and examined/returned ratios.
- Transaction retry and commit error rates.
- Oplog history window.

### 29.2. Metrics for Derived Stores

- CDC/outbox backlog.
- Last processed event/version per partition.
- Projection lag and freshness age.
- Failed and retried events.
- Duplicate and out-of-order event counts.
- Reindex/backfill progress.
- Source-target mismatches.
- Redis hit ratio, evictions, and stale hits.
- Search latency and relevance.
- Warehouse data completeness.

### 29.3. Suggested Dashboard

```text
+-----------------------------+----------------------------+
| MongoDB OLTP p95/p99        | Primary write errors       |
+-----------------------------+----------------------------+
| CDC / outbox backlog        | Resume/history lost        |
+-----------------------------+----------------------------+
| Search index freshness      | Search API relevance/lat.  |
+-----------------------------+----------------------------+
| Cache hit ratio/evictions   | Cache stale-version count  |
+-----------------------------+----------------------------+
| Warehouse watermark         | Reconciliation mismatches  |
+-----------------------------+----------------------------+
| Source/target event version | End-to-end cost per query  |
+-----------------------------+----------------------------+
```

A “healthy” search cluster that is 3 days behind source data is still a business incident. **Operational health and data correctness must be monitored together.**

## 30. Typical Failures and Resilient Design

### 30.1. Redis Goes Down

**Expected behavior when Redis is strictly a cache:**

1. Reads fall back to MongoDB.
2. Rate limits/backpressure protect MongoDB from cache stampedes.
3. Business writes are never lost because cache is unavailable.
4. Once Redis recovers, warm up caches with version checks.
5. Never serve expired cached authorization decisions.

If a Redis outage completely breaks order placement, check whether the cache accidentally became a source of truth.

### 30.2. OpenSearch/Indexer Stops

1. Authoritative MongoDB writes still confirm.
2. Outbox/CDC buffers the backlog within the retention budget.
3. Search UI surfaces degraded/stale state.
4. Relay retries with idempotent events.
5. If history expires, reindex/reconcile.
6. Never edit product prices directly in search to “work around lag” while bypassing the source.

### 30.3. Kafka Broker Slowdown or Outage

- Business writes + outbox still commit if architecture allows.
- Relay backlog grows.
- Never delete unacknowledged outbox rows.
- Monitor storage/retention and prevent retry storms.
- Consumers rely on deduplication/inboxes.
- When the broker recovers, replay by event IDs/versions.

If business rules require synchronous publish confirmation before acknowledging a command, define explicit failure semantics instead of mixing an outbox with hot-path broker timeouts.

### 30.4. Warehouse Falls Behind

- Reports must display watermarks/data-as-of timestamps.
- Inspect ingestion jobs and late events.
- Support partition rebuilds.
- Never use lagged warehouse totals to authorize immediate balances.
- Reconcile totals against authoritative sources.

### 30.5. PostgreSQL Billing Failure

If Billing owns the ledger, Catalog can keep serving products, while booking/payment workflows must enter a pending state or fail gracefully. Never use a MongoDB invoice projection to mark “paid” while the Billing source is unavailable.

## 31. Decision Matrix: Score Measurable Criteria Instead of Debating Preferences

An illustrative scoring template (not a universal benchmark):

| Criterion | Example weight | MongoDB-only | MongoDB + other systems |
| --- | ---: | --- | --- |
| Queries fit indexes/aggregation | 20% | Advantageous if fully met | Advantageous when specialized engines close gaps |
| Consistency/invariants | 20% | Fewer boundaries, easier to enforce | Sync risk rises when workflows span systems |
| p95/p99 & throughput | 20% | Requires real benchmarking | Independent scaling may perform better |
| Team operational skill | 15% | Fewer systems to run | Requires additional operational skills |
| Cost/TCO | 15% | Usually simpler | Can be cost-effective at large scale |
| Security/compliance | 10% | Fewer data copies | More stores requiring policy enforcement |

### 31.1. Using the Matrix Properly

1. Define criteria ratified by product and engineering.
2. Assign weights matching strategic priorities.
3. Score using measured metrics rather than gut feelings.
4. Enforce **hard constraints**: failing invariants or security disqualifies an option regardless of total score.
5. Record assumptions and uncertainty ranges.
6. Benchmark a realistic POC workload.
7. Schedule periodic reviews as scale evolves.

Never pick a database by saying “MongoDB scored 87 vs. PostgreSQL's 82” when scores are subjective opinions.

### 31.2. A Pragmatic Decision Tree

```text
Do reads/writes naturally fit bounded documents?
       |
     +-- No --> Consider relational/graph/other primary
     |
     +-- Yes
          |
          v
Can MongoDB meet invariants with atomic ops,
transactions, indexes and validation?
          |
        +-- No --> Redesign model or choose another primary
        |
        +-- Yes
              |
              v
Can MongoDB meet measured SLO/cost for key queries?
              |
            +-- Yes --> Prefer simpler MongoDB-first solution
            |
            +-- No
                  |
                  v
Is problem a specialist workload?
   - caching -> Redis?
   - text relevance -> Search?
   - event fan-out -> Broker?
   - large analytics -> Warehouse?
   - file bytes -> Object Storage?
                  |
                  v
Add a derived store with ownership,
event delivery, idempotency and recovery
```

## 32. POC: Defining What Must Be Measured

### 32.1. Representative Dataset

A meaningful POC requires:

- Production-like document sizes and payload distributions.
- Tenant skew and hot products.
- Realistic array child counts.
- Index cardinality.
- Read/write ratios.
- Real query shapes.
- Burst workloads and peak traffic.
- Legacy, invalid, or missing fields if present in real data.
- Backfill and incremental sync volumes.

Never declare one engine superior based on 1,000 documents on localhost.

### 32.2. Performance Experiments

Example questions:

- Can a MongoDB compound index serve the list API under 50 ms p95?
- Does Vietnamese fuzzy search meet relevance targets?
- What is the search index lag at 10,000 product updates/sec?
- When the Redis cache is cold, can MongoDB survive a miss storm?
- If the broker goes down for 10 minutes, does the outbox hold enough data and catch up?
- Do warehouse ETL scans degrade OLTP?
- What are storage, index, and network costs at 10× scale?

### 32.3. Correctness Experiments

Do not measure speed alone:

- Two writers updating the same product version.
- Event v12 arriving before v11.
- Delete event arriving before a delayed update.
- Indexer crashing after applying an update yet before acking.
- Oplog history loss.
- HTTP gateway timeout after source commit.
- Redis invalidation race.
- Source restored from backup while projection is ahead.
- Tenant A querying tenant B's data.
- Price converting from Decimal128 to floating point.
- GDPR/retention deletion while a target store is offline.

## 33. Safe Lab: MongoDB as Authoritative Store + Internal Projection

The lab's goal is **simulating a MongoDB-only approach before introducing external databases**. It uses two MongoDB collections: a source and a read projection. No Redis/Kafka/OpenSearch installation or server configuration changes are required.

### 33.1. Conditions

- Use only a test MongoDB instance with CRUD and collection-creation permissions.
- Never use real data or production credentials.
- Create collections **scoped by `runId`**.
- Never drop databases or delete collections belonging to others.
- Do not intentionally induce failovers or network partitions.
- Clean up data using `_id + runId`.
- This demo does **not** provide full production CDC guarantees; its limitations are noted below.

### 33.2. Initializing Namespaces

```javascript
const lab = db.getSiblingDB("mongo_polyglot_row453_lab");
const runId = "row453_" + new ObjectId().toHexString();
const sourceName = "products_" + runId;
const projectionName = "product_read_" + runId;

for (const name of [sourceName, projectionName]) {
  if (lab.getCollectionNames().includes(name)) {
    throw new Error("Lab namespace already exists");
  }
}

lab.createCollection(sourceName);
lab.createCollection(projectionName);

const products = lab.getCollection(sourceName);
const readModel = lab.getCollection(projectionName);

printjson({
  database: lab.getName(),
  sourceName,
  projectionName,
  runId
});
```

### 33.3. Creating a Mock Product

```javascript
const productId = "SKU_" + runId;

products.insertOne({
  _id: productId,
  runId,
  tenantId: "tenant_" + runId,
  title: "Demo chair",
  priceCents: NumberLong("1250000"),
  status: "ACTIVE",
  tags: ["furniture", "office"],
  version: NumberLong("1"),
  updatedAt: new Date()
});

printjson(products.findOne({ _id: productId, runId }));
```

### 33.4. Creating an Index for Source Queries Before Adding Another System

```javascript
products.createIndex(
  {
    tenantId: 1,
    status: 1,
    updatedAt: -1
  },
  { name: "tenant_status_updated" }
);

printjson(
  products.find({
    tenantId: "tenant_" + runId,
    status: "ACTIVE"
  }).sort({ updatedAt: -1 })
    .limit(10)
    .explain("executionStats")
);
```

A single-document collection may prompt the planner to do a collection scan simply because it is tiny. The goal is practicing **query design and inspection**, not proving speed on a micro-lab.

### 33.5. Building a Simple Read Projection

```javascript
const product = products.findOne({
  _id: productId,
  runId
});

if (!product) {
  throw new Error("Source product not found");
}

readModel.updateOne(
  { _id: product._id, runId },
  {
    $set: {
      tenantId: product.tenantId,
      title: product.title,
      priceCents: product.priceCents,
      status: product.status,
      tags: product.tags,
      sourceVersion: product.version,
      projectedAt: new Date()
    },
    $setOnInsert: { runId }
  },
  { upsert: true }
);

printjson(readModel.findOne({ _id: productId, runId }));
```

Here the projection is built synchronously via script for learning purposes. In production, re-running a script with an older `sourceVersion` could overwrite newer data; proper version/CAS checks, ordering, and a source-to-projection pipeline are required.

### 33.6. Updating Source with CAS

```javascript
const changed = products.updateOne(
  {
    _id: productId,
    runId,
    version: NumberLong("1")
  },
  {
    $set: {
      priceCents: NumberLong("1350000"),
      updatedAt: new Date()
    },
    $inc: { version: NumberLong("1") }
  }
);

if (changed.matchedCount !== 1) {
  throw new Error("Version mismatch; stop");
}

printjson(products.findOne({ _id: productId, runId }));
```

Now `readModel` is not yet synchronized, illustrating **eventual consistency**:

```javascript
printjson({
  authoritative: products.findOne({
    _id: productId, runId
  }).priceCents,
  projected: readModel.findOne({
    _id: productId, runId
  }).priceCents
});
```

### 33.7. Syncing a Simulated Event

```javascript
const latest = products.findOne({
  _id: productId,
  runId
});

const currentProjection = readModel.findOne({
  _id: productId,
  runId
});

if (!latest || !currentProjection) {
  throw new Error("Lab expected source and projection");
}

if (latest.version > currentProjection.sourceVersion) {
  readModel.updateOne(
    {
      _id: productId,
      runId,
      sourceVersion: currentProjection.sourceVersion
    },
    {
      $set: {
        tenantId: latest.tenantId,
        title: latest.title,
        priceCents: latest.priceCents,
        status: latest.status,
        tags: latest.tags,
        sourceVersion: latest.version,
        projectedAt: new Date()
      }
    }
  );
}

printjson(readModel.findOne({ _id: productId, runId }));
```

This is a **single-worker sequential** demo. With multiple consumers, implement CAS retries/ordering and handle missing projections. This example does not claim exactly-once or gap-free rebootstrapping.

### 33.8. Simulating a Stale Event

```javascript
const staleEvent = {
  productId,
  sourceVersion: NumberLong("1"),
  title: "Old name"
};

const projection = readModel.findOne({
  _id: productId,
  runId
});

if (staleEvent.sourceVersion < projection.sourceVersion) {
  print("Ignore stale event; projection remains newer");
} else {
  throw new Error("Unexpected version ordering");
}
```

In this demo, business versions increment sequentially. Production consumers need version-aware conditional writes in the database or single-owner ordered delivery rather than checking versions only in RAM under concurrent writers.

### 33.9. Comparing Source and Projection

```javascript
const src = products.findOne({
  _id: productId, runId
});
const dst = readModel.findOne({
  _id: productId, runId
});

printjson({
  sourceVersion: src.version,
  projectionVersion: dst.sourceVersion,
  sameTitle: src.title === dst.title,
  samePrice: src.priceCents.toString()
          === dst.priceCents.toString()
});
```

This is a simple reconciliation check for one product. Production needs partitioned scans, reconciliation metrics, domain-specific comparisons, and load throttling.

### 33.10. Cleaning Up Only This Run's Data

Before deleting, verify:

```javascript
printjson({
  db: lab.getName(),
  sourceName,
  projectionName,
  runId
});

const sourceDocs = products.find(
  { runId }, { _id: 1, runId: 1 }
).toArray();

const projectionDocs = readModel.find(
  { runId }, { _id: 1, runId: 1 }
).toArray();

printjson({
  sourceOwned: sourceDocs.length,
  projectionOwned: projectionDocs.length
});
```

After confirming the right namespace and `runId`:

```javascript
for (const item of sourceDocs) {
  products.deleteOne({
    _id: item._id, runId
  });
}

for (const item of projectionDocs) {
  readModel.deleteOne({
    _id: item._id, runId
  });
}

printjson({
  sourceRemaining: products.countDocuments({ runId }),
  projectionRemaining: readModel.countDocuments({ runId })
});
```

Never run `dropDatabase()` or `deleteMany({})` on a shared environment. Empty lab collections/indexes remain after deleting records; cleaning up random namespaces is an environment-admin task with ownership verification.

## 34. Java Service Design: Gateways and Repositories by Bounded Context

### 34.1. Never Let an App Service Write Directly to Two Databases

A service owning product state should expose an interface:

```java
public interface ProductRepository {
    Product findById(String tenantId, String productId);
    boolean updatePriceIfVersion(
        String tenantId,
        String productId,
        long expectedVersion,
        long priceCents
    );
}
```

The MongoDB implementation handles atomic source updates and, where needed, transactional outbox inserts.

The search indexer should have a separate interface:

```java
public interface ProductSearchProjection {
    void upsert(
        String productId,
        long sourceVersion,
        ProductSearchDocument document
    );
    void delete(String productId, long sourceVersion);
}
```

Never combine MongoDB and search writes inside one simple method and return “success” when only one side succeeded.

### 34.2. Atomic Conditional Update Example with Java Sync Driver

```java
import com.mongodb.client.MongoCollection;
import com.mongodb.client.model.Filters;
import com.mongodb.client.model.Updates;
import com.mongodb.client.result.UpdateResult;
import org.bson.Document;

import static com.mongodb.client.model.Filters.*;
import static com.mongodb.client.model.Updates.*;

static boolean updatePrice(
        MongoCollection<Document> products,
        String tenantId,
        String productId,
        long expectedVersion,
        long newPriceCents) {

    if (newPriceCents < 0) {
        throw new IllegalArgumentException(
            "Price cannot be negative"
        );
    }

    UpdateResult result = products.updateOne(
        and(
            eq("_id", productId),
            eq("tenantId", tenantId),
            eq("version", expectedVersion)
        ),
        combine(
            set("priceCents", newPriceCents),
            currentDate("updatedAt"),
            inc("version", 1L)
        )
    );

    return result.getMatchedCount() == 1;
}
```

For monetary values, verify business units and conversions. For updating product + outbox in one transaction, pass a `ClientSession` with appropriate write concern and retry semantics. This snippet illustrates a single source update, **not a full outbox implementation**.

### 34.3. Query-Side Fallback

Pseudocode:

```java
ProductSearchResult searchProducts(Query q) {
    try {
        return searchProjection.search(q);
    } catch (SearchUnavailableException e) {
        // Fall back only when MongoDB source has an equivalent
        // query meeting SLOs and budget.
        return mongoSearchFallback.search(q);
    }
}
```

You cannot fall back a complex full-text relevance query to `find({})` and filter in RAM without indexes or SLO capacity. Fallbacks may instead return a degraded response or report search unavailable; design this explicitly.

## 35. Anti-Pattern Matrix and Alternatives

| Anti-pattern | Why it is problematic | Better approach |
| --- | --- | --- |
| “MongoDB is always best for flexible schemas” | Ignores FKs, joins, SQL workloads | Evaluate invariants and query patterns |
| “SQL is always better for ACID” | MongoDB has atomic documents/transactions | Benchmark and define transaction boundaries |
| “Document DBs can't join” | MongoDB has `$lookup` | Measure join frequency and cost |
| “Every microservice needs a different DB type” | Unnecessary operational bloat | Choose by bounded context |
| “Relational data always requires SQL” | Bounded embedded aggregates can fit well | Decide by lifecycle and access patterns |
| “MongoDB-only means one server” | Lacks HA and durability | Use replica sets/sharding as needed |
| “Slow queries? Add Redis first” | Might just lack an index | Explain and optimize the source |
| “Redis invalidation is always synchronous” | Read/fill/invalidation races | Versioning, TTLs, consistency budgets |
| “Search index is the price authority” | Projections can be stale | Re-verify source at checkout |
| “Full-text always needs a search engine” | MongoDB has text/Search per deployment | Evaluate existing capabilities |
| “Kafka is a transactional database” | Broker offsets differ from business invariants | Source owner + events |
| “MongoDB change streams are consumer groups” | Every watcher receives all events | Explicit ownership and partitioning |
| “Outbox equals exactly-once” | Publish ACKs can be lost | Idempotent consumers |
| “Dual-writing Mongo + SQL is atomic” | No shared default transaction | Single owner, outbox/saga |
| “Both DBs can edit prices” | Split authority conflicts | One source of truth |
| “Events always arrive in order” | Multi-consumer retries/partitioning | Aggregate versions/CAS |
| “Snapshot then CDC is safe” | Snapshot-to-stream gap | Coordinated bootstrap |
| “Resume tokens keep history forever” | Finite oplog window | Monitoring and rebootstrap |
| “Warehouse numbers are always realtime” | Batching, lag, late events | Watermarks and freshness SLOs |
| “Object storage file + Mongo metadata are atomic” | Two separate systems | State machine and reconciliation |
| “Vector DB is mandatory for RAG” | Multiple options per workload | POC recall, latency, and cost |
| “Copying data adds no security risk” | More copies holding PII | Minimization, ACLs, audits, deletion |
| “Deleting source deletes all copies” | Derived stores may be offline | Deletion propagation audit |
| “DR only needs restoring each DB” | Snapshots sit at different timestamps | Rebuild/reconcile derived stores |
| “No errors means sync is healthy” | Silent lag and drift | Metrics + reconciliation |
| “Switch databases on first slow query” | Masks poor query design | Profile, index, explain |
| “Schema-less means no data contracts” | Consumer and mapping bugs | Validators and schema versioning |
| “Localhost benchmark settles architecture” | Ignores real load and failures | Representative POC |
| “More tech makes it future-proof” | Higher TCO and on-call burden | Start simple, evolve deliberately |

## 36. Interview Questions and Design Exercises

### Exercise A — Is MongoDB Alone Enough?

An app stores 200,000 product profiles, mostly queried by `productId` and filtered by `category`, operated by just 3 developers.

1. Which measurements are needed before adding Redis?
2. What can MongoDB indexes/aggregations solve?
3. When is a search engine actually warranted?
4. How does TCO affect the decision?

### Exercise B — Choosing SQL vs. Document Model

An accounting system requires journal entries, constraints, and heavy joined reports. Compared to a product catalog with varying attributes, where does MongoDB fit and where should an RDBMS be considered? Specify access patterns, invariants, and transaction boundaries.

### Exercise C — Dual Writes

```text
write MongoDB -> write OpenSearch
```

1. List at least 4 failure windows.
2. Why doesn't reversing the order solve it?
3. Design an outbox/CDC flow.
4. When search fails, how should the catalog API respond?

### Exercise D — Cache Invalidation Race

```text
T1 cache miss
T2 MongoDB update
T3 cache DEL
T4 old reader cache SET
```

Propose a versioned cache key or CAS logic. Contrast the stale-data budgets for product title vs. payment status.

### Exercise E — Event Ordering

Product version 13 reaches the indexer before version 12.

1. Why can search regress?
2. Where does the version come from?
3. What happens when a delete event arrives before a delayed update?
4. How does tombstone retention help?

### Exercise F — CQRS

A dashboard needs 8 fields across 5 collections. Compare live `$lookup` against a read projection across query frequency, indexes/plans, freshness, rebuilds, and cost.

### Exercise G — Analytical Workloads

A BI team runs queries scanning 3 years of orders every 2 minutes, spiking API p99.

1. How can MongoDB be tuned first?
2. When is a warehouse justified?
3. How do you export/CDC without losing updates?
4. Which watermark explains lagged reports?

### Exercise H — Object Storage Metadata

A file upload succeeds yet inserting MongoDB metadata fails.

1. What state is the file in?
2. Design a state machine.
3. How do you clean up orphans safely?
4. Can the two writes be called atomic?

### Exercise I — Booking Availability

Search shows a room available yet the authoritative Booking service reports none left.

1. Which system decides?
2. Which scenarios tolerate eventual consistency?
3. How must inventory reservation be atomic?
4. If search lag exceeds SLOs, what should the UI do?

### Exercise J — Outbox Retries

A relay publishes event E10 successfully, loses the ACK, and publishes again.

1. Why can't this be called exactly-once?
2. Which key should consumers use to deduplicate?
3. How do you handle E11 arriving before E10?
4. What DLQ, retry, and reconciliation mechanisms are needed?

### Exercise K — MongoDB + PostgreSQL Ownership

Catalog uses MongoDB; Billing uses PostgreSQL. A checkout API needs product info and creates an invoice.

1. How should the two systems coordinate via APIs/events?
2. Where does the checkout-time price snapshot live?
3. If Catalog is unavailable, can an invoice still be created?
4. Without a cross-DB MongoDB/PostgreSQL transaction, how is business correctness preserved?

### Exercise L — Multi-System Security

Customer data exists in MongoDB, Redis, Search, and a Warehouse. A tenant requests deletion.

1. List all places that must be handled.
2. If Search is offline, how is deletion handled?
3. What policies do backups and retention need?
4. What evidence proves deletion propagated?

### Exercise M — Recovery

MongoDB source restores to a 10:00 snapshot, while Search restores to 10:15.

1. What data inconsistencies can appear?
2. How do you rebuild from the source?
3. Are tombstones/versions needed?
4. Can you trust Search simply because it is “newer”?

### Exercise N — Transaction Boundaries

A service updates orders, ledgers, and an outbox. Design the MongoDB transaction and contrast it with calling a payment gateway. Why must external calls stay out of retry callbacks?

### Exercise O — Graph/Vector

A social app has 5-hop relationships; a customer support app needs semantic search. Define benchmarks and criteria to choose between MongoDB `$graphLookup`/Vector Search and specialized graph/vector engines.

### Exercise P — Decision Record

Write an ADR for adding OpenSearch to a MongoDB system:

- Context.
- Current pain.
- Alternatives (indexes/MongoDB Search/OpenSearch).
- Data owner.
- Read/write paths.
- Consistency SLOs.
- Failure modes.
- Backfill/CDC.
- Security.
- Cost and operations.
- Rollout/rollback criteria.

### Exercise Q — Do Not Add Databases

A team proposes Kafka + Redis + OpenSearch + PostgreSQL for an internal app serving 300 users. Argue for a simple MongoDB-first architecture, the limits to measure, and specific thresholds that would change your decision.

## 37. Architecture Decision Record (ADR) Template

```markdown
# ADR: MongoDB-Only vs. MongoDB + Search

## Context
- Source data: products
- Access patterns: read by ID + faceted full-text search
- Current latency: p95...
- Expected growth: ...
- Team/on-call capacity: ...

## Decision drivers
- Search relevance and latency
- OLTP SLO isolation
- Security/tenant filtering
- Freshness allowed
- Cost/TCO

## Options
1. MongoDB indexes + aggregation
2. MongoDB Search on available deployment
3. MongoDB + OpenSearch projection

## Decision
- Choose ... because ...
- MongoDB remains source of truth
- Search target is derived and rebuildable

## Synchronization
- Outbox/change stream + stable event IDs
- Source version and tombstones
- Retry/backoff/idempotency
- Rebootstrap procedure

## Failure behavior
- Search unavailable -> ...
- CDC history lost -> ...
- Source restore -> ...

## Validation
- P95/p99 load test
- Relevance tests
- Version mismatch count
- Security negative tests
- Recovery drill

## Rollout
- Shadow index
- Reconcile
- Canary reads
- Gradual cutover
- Feature-flag rollback

## Ownership
- Catalog writes MongoDB only
- Search team owns projection and on-call
```

ADRs should document **the decision and the conditions under which it changes**, not just product names. As workloads or platform capabilities evolve, the team can revisit with fresh data.

## 38. References

Read documentation matching your exact MongoDB server version, FCV, driver, topology, and managed-service tier; never assume every feature exists on every deployment:

### Official MongoDB Docs

- [Data Modeling](https://www.mongodb.com/docs/manual/data-modeling/) — embedding, references, access patterns.
- [Indexes](https://www.mongodb.com/docs/manual/indexes/) — compound, multikey, partial, TTL, and unique indexes.
- [Aggregation Pipeline](https://www.mongodb.com/docs/manual/core/aggregation-pipeline/) — `$match`, `$group`, `$lookup`, and transformations.
- [`$lookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/lookup/) — joining collections inside aggregations.
- [Transactions](https://www.mongodb.com/docs/manual/core/transactions/) — multi-document atomicity and trade-offs.
- [Change Streams](https://www.mongodb.com/docs/manual/changestreams/) — CDC, resume tokens, and oplog history.
- [Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/) — durability and replication guarantees.
- [Read Concern](https://www.mongodb.com/docs/manual/reference/read-concern/) — visibility and consistency.
- [Schema Validation](https://www.mongodb.com/docs/manual/core/schema-validation/) — document contracts.
- [Sharding](https://www.mongodb.com/docs/manual/sharding/) — scale-out and shard key design.
- [Time Series Collections](https://www.mongodb.com/docs/manual/core/timeseries-collections/) — time-series storage.
- [GridFS](https://www.mongodb.com/docs/manual/core/gridfs/) — storing large files when appropriate.
- [MongoDB Search](https://www.mongodb.com/docs/atlas/atlas-search/) — integrated full-text/search capabilities per tier.
- [MongoDB Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/) — semantic/vector capabilities per deployment.
- [`$graphLookup`](https://www.mongodb.com/docs/manual/reference/operator/aggregation/graphLookup/) — recursive graph traversals.
- [MongoDB Atlas Monitoring](https://www.mongodb.com/docs/atlas/monitor-cluster-metrics/) — cluster metrics.

### Complementary Technologies (Vendor Documentation)

- [PostgreSQL Documentation](https://www.postgresql.org/docs/) — relational schemas, constraints, transactions, SQL.
- [Redis Documentation](https://redis.io/docs/latest/) — caching, persistence, eviction, streams.
- [OpenSearch Documentation](https://docs.opensearch.org/latest/) — search indexes, ingestion, relevance.
- [Elasticsearch Documentation](https://www.elastic.co/guide/) — full-text/search engine features.
- [Apache Kafka Documentation](https://kafka.apache.org/documentation/) — topics, partitions, offsets, consumers.
- [Debezium Documentation](https://debezium.io/documentation/) — change data capture patterns.
- [AWS S3 Documentation](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Welcome.html) — object storage semantics.

Never choose a technology solely because docs say a feature is “supported”. For performance, correctness, and security, validate on representative datasets and recovery drills for your own application.

## 39. Conclusion

**Choosing standalone MongoDB vs. combining with other data systems is a decision about data boundaries and operational capacity, not a feature-count contest.**

- **Prefer MongoDB-first** when document models fit, core queries are served by available indexes/aggregations/search, invariants are enforceable, and SLOs/costs meet targets.
- **Consider an RDBMS** when relational data, referential constraints, SQL joins, and relational transactional workflows dominate.
- **Add Redis** when caching demonstrably improves latency/cost and the app handles staleness and fallbacks.
- **Add a search engine** when relevance/facets/fuzzy/scoring demands exceed available search options.
- **Add a broker** when fan-out, buffering, retention, or consumer-group scaling exceed direct change streams.
- **Add a warehouse/lakehouse** when historical OLAP impacts OLTP or requires joining multiple data sources.
- **Use object storage** for large files/binaries with clear metadata and ownership management.
- **Evaluate graph/vector engines** when multi-hop traversals or semantic retrieval dominate workloads, grounded in benchmarks and real deployment capabilities.

When running multiple systems, the decisions that matter more than database brand names are:

1. **Who owns the authoritative source data and is allowed to write?**
2. **Which copies may be stale, and for how long?**
3. **Which events/outboxes/CDC pipelines synchronize data, with what IDs and versions?**
4. **If events duplicate, arrive late, lose history, or a target goes down, how does recovery work?**
5. **Which invariants must never trust a cache or search projection?**
6. **Does the system have sufficient observability, backups, reconciliation, security, and operators?**

**Core principle:** start with the simplest model **that accurately meets your workload and business contracts**. Add another data store only when measurable technical or business value exceeds synchronization and operational costs. Once added, design it as a **component with explicit ownership, consistency contracts, failure behavior, and recovery paths**—not merely another place holding a copy.
