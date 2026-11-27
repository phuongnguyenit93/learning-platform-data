# Choosing Relational, Key–Value, Document, Graph, and Time-Series Databases

A database choice is an architectural decision with long-term impact. A booking system must ensure two people cannot reserve the same room simultaneously; a shopping cart needs fast reads and updates by user; a product catalog has attributes that vary by item category; a relationship network needs to find connection paths; and a monitoring system must ingest and query millions of measurements over time. No single data model is optimal for all of these cases.

Common database families address different access patterns:

- **Relational:** structured data, clear relationships, join queries, and transactions.
- **Key–value:** direct access to a value by key, typically optimized for low latency and high throughput.
- **Document:** stores objects close to the domain structure, flexible in fields and nesting.
- **Graph:** represents entities and relationships, supporting queries along paths and multi-hop connections.
- **Time-series:** optimized for timestamped measurement data, time-window queries, and periodic aggregations.

These are **data models and workload types**, not a one-to-one list of products. A single database may support multiple models, but with different levels of optimization and trade-offs. Good design starts from business requirements, read/write patterns, consistency, scale, security, operations, and cost—and only then selects the technology.

This lesson belongs to the **Database Architecture** chapter of the **CLOUD_ARCHITECTURE** module. The goal is to understand how to choose the right database for cloud applications, define data ownership, and evaluate trade-offs across performance, reliability, scalability, security, cost, and operations using a Well-Architected mindset.

## 1. Learning Objectives

After completing this lesson, learners can:

1. Distinguish relational, key–value, document, graph, and time-series models.
2. Translate business requirements into entities, relationships, access patterns, and workloads.
3. Choose a data model based on transactions, consistency, queries, read/write rates, and scaling approach.
4. Explain the differences between flexible schema and controlled schema, and between normalization and denormalization.
5. Design keys, indexes, partitions/shards, and TTLs based on access patterns.
6. Identify risks when using multiple databases, synchronizing data, and building projections.
7. Evaluate HA/DR, backup/restore, security, data residency, observability, and full-lifecycle cost.
8. Make justified decisions using a decision matrix, prototype, benchmark, and Architecture Decision Record (ADR).

## 2. Start from the Workload Rather Than Product Names

### 2.1. Describe How the Application Uses Data

Before choosing a database, answer these questions:

| Question Group | Examples to Clarify |
|---|---|
| Entities | Booking, Customer, Listing, Payment, Device, Relationship? |
| Relationships | One-to-many, many-to-many, hierarchical, multi-hop paths? |
| Queries | Lookup by ID, multi-field filters, joins, aggregations, traversals, time-range queries? |
| Load | Read/write QPS, concurrency, bursts, batch jobs, daily data growth? |
| Transactions | Do multiple records need atomic updates? Where are the transaction boundaries? |
| Consistency | Strong, read-your-writes, eventual, monotonic, or is approximate data acceptable? |
| Latency | Target p95/p99; synchronous or asynchronous? |
| Retention | How long to retain, under what rules to delete, is archiving required? |
| Availability/DR | SLO, RTO, RPO, failure domains, and recovery procedures? |
| Security | Data classification, tenant isolation, encryption, audit, residency? |
| Operations | What does the team know how to administer, and what backup/restore and migration tooling exists? |

A system with 10 million records does not necessarily need a distributed database. A system with 100 thousand records that requires multi-hop graph queries at very low latency may need a model different from relational.

### 2.2. Access Pattern Matrix

Example of a booking platform:

| Use Case | Primary Access Pattern | Characteristics |
|---|---|---|
| Create booking | Check availability then write booking/hold | Requires correctness and transactions |
| View booking by ID | Read a single record by key | Low latency, frequent |
| Display listing | Read profile with many attributes | Query by ID and filters |
| Recommend similar listings | Traverse relationships, attributes, and connections | May require a graph or specialized search/index |
| Analyze conversion | Aggregate events over time ranges | Batch/analytics or time-series/warehouse |
| Monitor service health | Continuously ingest metrics, query time windows | Time-series/metrics store |
| Cart/session | Read/write by user key, with TTL | Key–value/cache |

Different access patterns may call for different models. You should not put all data into a single database merely for initial convenience, nor should you distribute prematurely and force the team to operate many systems.

### 2.3. Five Quick Decision Questions

1. **Does the data have many relationships and require transactions across multiple entities?** Look at relational first.
2. **Are most operations getting/putting a single value by key?** Look at key–value.
3. **Do objects have nested structures and fields that vary by type?** Look at document.
4. **Do core queries traverse multiple relationships or need pathfinding?** Look at graph.
5. **Is the data primarily timestamped measurements/events queried by time?** Look at time-series.

This is a first filter, not an absolute rule. Afterward, you still need to check transactions, indexes, consistency, scaling capabilities, quotas, query limits, and the cost of specific products.

## 3. Relational Databases

### 3.1. Table, Row, Column, and Key Model

A relational database organizes data into tables. Each table represents an entity type or relationship; rows are records; columns are attributes. A primary key identifies a row; a foreign key links records across tables.

Booking model example:

~~~sql
CREATE TABLE customers (
    customer_id BIGINT PRIMARY KEY,
    email       VARCHAR(255) NOT NULL UNIQUE,
    full_name   VARCHAR(200) NOT NULL
);

CREATE TABLE listings (
    listing_id BIGINT PRIMARY KEY,
    title      VARCHAR(300) NOT NULL,
    city_code  VARCHAR(30) NOT NULL
);

CREATE TABLE bookings (
    booking_id  BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    listing_id  BIGINT NOT NULL REFERENCES listings(listing_id),
    check_in    DATE NOT NULL,
    check_out   DATE NOT NULL,
    status      VARCHAR(30) NOT NULL,
    created_at  TIMESTAMP NOT NULL
);
~~~

This model clearly expresses which customer and listing a booking belongs to. The database can enforce certain constraints through foreign keys, unique constraints, check constraints, and transactions.

### 3.2. ACID and Transactions

Relational databases typically provide transactions with ACID properties:

- **Atomicity:** operations within a transaction either all succeed or all roll back together.
- **Consistency:** a transaction transitions data from one valid state to another valid state according to defined constraints and invariants.
- **Isolation:** concurrent transactions are controlled according to an isolation level, preventing unwanted interactions depending on the guarantee level.
- **Durability:** after a successful commit per the database's guarantees, changes are persisted across the failure conditions supported by the system.

ACID does not automatically guarantee that business logic is correct. For example, two transactions that both read one available room and then write a booking can create a double booking if the locking/constraint model and transaction design do not protect the invariant. You must design appropriate unique/exclusion constraints, locks, isolation levels, or a reservation mechanism.

### 3.3. JOINs and Relational Queries

SQL supports querying combined data:

~~~sql
SELECT
    b.booking_id,
    c.full_name,
    l.title,
    b.check_in,
    b.check_out,
    b.status
FROM bookings AS b
JOIN customers AS c
  ON c.customer_id = b.customer_id
JOIN listings AS l
  ON l.listing_id = b.listing_id
WHERE b.customer_id = 10042
ORDER BY b.created_at DESC;
~~~

JOINs avoid duplicating full customer/listing information into every booking. However, joining many tables and running queries without proper indexes can consume significant resources when data grows large.

### 3.4. Normalization and Denormalization

**Normalization** splits data to reduce duplication and prevent insert/update/delete anomalies. **Denormalization** stores pre-aggregated or intentionally duplicated data to optimize read queries.

| Approach | Benefits | Trade-offs |
|---|---|---|
| Normalize | Standardized data, single place to update, clear constraints | More JOINs, some complex queries |
| Denormalize | Fast reads, fewer joins, suitable for read models | Requires syncing copies, possible eventual consistency, increased storage |

For example, a booking can store `listing_title_at_booking` to preserve the display title at the time of booking. That is not necessarily redundant duplication; it can be an intentional business snapshot. Conversely, copying a customer's current email into every table just to avoid a join can cause data drift when the user changes their email.

### 3.5. When Is Relational a Good Fit?

- Business transactions with clear invariants and transactional requirements.
- Data with many-to-many relationships or JOIN queries.
- Need for constraints, unique keys, foreign keys, and SQL.
- Flexible reporting/querying over structured data.
- A team skilled in schema migrations, indexing, transactions, and backups.

### 3.6. Limitations to Watch Out For

- Scaling writes horizontally across multiple shards can complicate transactions and joins.
- Connections, locks, hot rows, and indexes can become bottlenecks.
- Schema migrations must remain compatible with running applications.
- Read replicas can lag; reading from a replica does not always satisfy read-after-write.
- A single database still needs HA, backups, and DR; ACID does not replace those mechanisms.

## 4. Key–Value Databases

### 4.1. Key and Value Model

A key–value store saves a mapping between a unique key and a value. The application retrieves data by key, usually without scanning or joining across multiple attributes.

~~~text
Key: session:user:10042
Value: {
  "cartId": "cart_913",
  "locale": "vi-VN",
  "lastActivity": "2026-11-18T09:30:00Z"
}
~~~

Some systems store values as strings/bytes; others support structures such as hashes, lists, sets, or sorted sets. You need to check the semantics and atomic operations of the specific product.

### 4.2. Priority Access Patterns

Key–value stores fit well when queries are primarily:

- `GET(key)` – read a value.
- `PUT/SET(key, value)` – create or overwrite.
- `DELETE(key)` – delete.
- Atomic partial updates or counters if supported.
- TTL for automatic expiration of sessions/caches.

Do not pick a key–value store and expect flexible JOIN queries or arbitrary multi-field filtering like a relational database, unless the product provides suitable query/indexing capabilities and has been benchmarked.

### 4.3. Cart/Session Example

~~~text
cart:user:10042 -> {
  items: [
    { listingId: "L-42", quantity: 1 },
    { listingId: "L-57", quantity: 2 }
  ],
  updatedAt: "2026-11-18T09:30:00Z"
}

TTL = inactivity duration accepted by the business
~~~

The application retrieves the cart in a single lookup by key. When the user logs back in, the system can load the cart from the store. However, the cart is not the authoritative source for inventory or booking confirmation; at checkout, the system must still check and execute the transaction in the authoritative data service.

### 4.4. Cache or Key–Value Database?

A key–value cache may store regenerable data and use TTL/eviction. A key–value database may be designed for durability, replication, and business state. You must distinguish:

- Cache misses can be re-fetched from the authoritative source.
- Durable business data cannot be lost simply due to eviction.
- Cache invalidation and write-through/write-behind have different semantics.
- If using a cache as an authoritative store, verify the persistence, backup, consistency, and recovery capabilities of that exact product.

### 4.5. Partitioning and Hot Keys

Keys are typically hashed or distributed across partitions/shards. Good keys distribute load evenly. A popular key accessed too frequently (a hot key) can overload one partition even when the cluster has overall spare capacity.

For example, using a single global homepage counter as a key for every visit can concentrate load onto one node. You can shard/bucket the counter and aggregate it if the business does not require instantaneous updates to a single global key.

### 4.6. When Is Key–Value a Good Fit?

- Sessions, token metadata, carts, and preferences accessed by ID.
- Caches, feature flags, counters, or rate limits.
- Key-based lookups requiring low latency and high throughput.
- Device or job state identified by a key.

It is not suitable when the workload primarily requires complex relational queries, multi-entity transactions, or arbitrary attribute searches that the store does not support.

## 5. Document Databases

### 5.1. Organizing Data as Documents

A document database stores records as documents, typically in JSON/BSON or a similar format. A document can contain nested objects, arrays, and optional fields.

~~~json
{
  "_id": "listing_42",
  "title": "Apartment near city center",
  "location": {
    "city": "Da Nang",
    "district": "Hai Chau"
  },
  "amenities": ["wifi", "parking", "kitchen"],
  "pricing": {
    "currency": "VND",
    "basePrice": 950000
  },
  "policies": {
    "smokingAllowed": false,
    "checkInFrom": "14:00"
  }
}
~~~

Documents map closely to application objects and can be read/written as aggregates. Many document databases support indexes on nested fields, filtering, aggregation, and single- or multi-document transactions depending on the product.

### 5.2. Embed or Reference?

**Embed** child data inside the same document when it is usually read together, has bounded size, and shares the lifecycle of the parent document.

**Reference** by ID when child data has an independent lifecycle, can grow unboundedly, is shared across many objects, or needs separate updates.

| Case | Consideration |
|---|---|
| Snapshot display address of a listing | Can embed |
| Small list of amenities frequently read with the listing | Can embed |
| Millions of paginated reviews | Store in a separate collection, referencing `listingId` |
| Customer referenced by many bookings | Usually store separately and reference |
| Small policies belonging only to one document | Embedding may be simpler |

Over-embedding can make documents large, increasing write amplification and contention when multiple processes update the same document. Over-referencing causes multiple round-trips or requires application-level joins.

### 5.3. Flexible Schema Does Not Mean No Schema

A document database may allow documents in the same collection to have different fields, but the application still needs conventions:

- Required fields, data types, defaults, and formats.
- Versioning rules and migration for legacy documents.
- Required indexes and query patterns.
- Conventions for null, missing fields, and default values.
- Data validation at the application layer or via database schema validation.

Without governance, the same concept might end up stored over time as `price`, `basePrice`, `amount`, or mixed number/string types, making queries and reporting unreliable.

### 5.4. Indexes and Queries

Indexes speed up field queries but increase storage and write overhead. Compound indexes depend on field order and access patterns. You must analyze query plans, selectivity, sorting, pagination, and index coverage.

Avoid indexing every field "just in case": each write must update additional indexes, and large indexes affect cache and backups. Design indexes around actual queries.

### 5.5. When Is Document a Good Fit?

- Profiles with rich, nested structures that vary by type.
- Reads/writes typically centered around a single document or aggregate.
- Need to evolve fields flexibly at product development speed.
- Queries mainly based on IDs and defined filters/indexes.

It is not automatically suitable when multiple documents must be updated atomically together or when complex joins and relational constraints are required. Check the product's transaction scope and document size limits before deciding.

## 6. Graph Databases

### 6.1. Nodes and Edges

A graph database represents data using:

- **Nodes/vertices:** entities such as `Customer`, `Listing`, `Device`, or `Organization`.
- **Edges/relationships:** connections between nodes such as `BOOKED`, `FRIEND_OF`, `LOCATED_IN`, or `DEPENDS_ON`.
- **Properties:** attributes attached to nodes or edges.

~~~mermaid
flowchart LR
    C[Customer A] -->|BOOKED| B[Booking 913]
    B -->|FOR_LISTING| L[Listing 42]
    C -->|REFERRED| C2[Customer B]
    C2 -->|BOOKED| B2[Booking 821]
    B2 -->|FOR_LISTING| L2[Listing 57]
    L -->|NEAR| L2
~~~

The strength of a graph database lies in querying relationships and multi-hop paths. For example: finding customers connected by referral to someone who booked a listing in a given area, or analyzing services that depend directly or indirectly on a failing service.

### 6.2. Traversal Queries

In a relational database, multi-hop queries may require multiple recursive JOINs or recursive CTEs. A graph database can express edge traversal using a dedicated query language (such as Cypher in some products).

~~~cypher
MATCH (c:Customer {id: "customer_100"})
      -[:REFERRED*1..3]->(other:Customer)
      -[:BOOKED]->(b:Booking)
      -[:FOR_LISTING]->(l:Listing)
WHERE l.city = "Da Nang"
RETURN DISTINCT other, b, l;
~~~

This is an example of Cypher syntax; exact syntax, capabilities, and performance depend on the graph engine. You must bound traversal depth and result limits, because unbounded traversal expansion can escalate cost very quickly.

### 6.3. When Is Graph a Good Fit?

- Social, referral, or organizational relationship networks.
- Fraud detection across chains of accounts/devices/transactions.
- Knowledge graphs and semantic link-based search.
- Dependency graphs, impact analysis, and topology.
- Pathfinding and multi-hop connection queries as a core workload.

A graph database is not inherently better than a relational database for all relational data. If queries simply fetch a booking by ID or join two stable tables, a relational database can be simpler and more efficient.

### 6.4. Graph Modeling Requires Discipline

Define node labels, edge types, direction, cardinality, and properties. Avoid creating many near-duplicate relationship types or allowing unbounded traversals. You must evaluate node-property indexing, uniqueness, transactions, partitioning, and the graph engine's HA capabilities.

## 7. Time-Series Databases

### 7.1. Data Characteristics

A time-series database is optimized for time-stamped data points: timestamp, metric name, tags/dimensions, and value.

Example:

~~~text
timestamp             metric             service       value
2026-11-18T09:00:00Z  api_latency_ms     booking-api   42
2026-11-18T09:00:05Z  api_latency_ms     booking-api   51
2026-11-18T09:00:10Z  api_latency_ms     booking-api   47
2026-11-18T09:00:15Z  cpu_utilization    worker-2      68.2
~~~

Workloads typically involve continuous, append-heavy writes, time-window queries, and periodic aggregations. The database can optimize compression, retention, downsampling, and time-based partitioning.

### 7.2. Time, Tags, and Cardinality

A data point may include:

- Timestamp with standardized precision and timezone.
- Measurement/metric name.
- Tags/dimensions such as `service`, `region`, `environment`.
- Numeric value or field data.

High-cardinality tags such as `requestId`, `userId`, or `bookingId` can generate a massive number of series, driving up memory, index size, and cost. Choose dimensions that serve aggregate queries, rather than turning every unique ID into a tag.

### 7.3. Retention, Downsampling, and Rollups

Not all measurement data must be kept at high resolution forever. You can:

- Keep raw data for a short window for investigation.
- Roll up into minute/hour/day aggregates for long-term trend analysis.
- Apply different retention policies by metric type and audit requirements.
- Archive long-term data in object storage/a warehouse when needed.

Downsampling reduces storage but can lose short spike details. Choose appropriate aggregation functions: averages can hide outliers; max/p95/count may be necessary for monitoring goals.

### 7.4. When Is Time-Series a Good Fit?

- Infrastructure and application metrics.
- Device/IoT telemetry.
- Prices, exchange rates, or measurements changing over time.
- Tracking behavior/load across time windows.
- Trend analysis, alerting, rollups, and retention management.

A time-series store is not the default choice for booking/customer transactions. When you need to update current business state and enforce relational constraints, relational or key–value is usually more appropriate.

## 8. Comprehensive Comparison of the Five Models

| Criterion | Relational | Key–Value | Document | Graph | Time-Series |
|---|---|---|---|---|---|
| Structure | Tables, explicit schema | Key → value | Nested documents | Nodes and edges | Timestamp + measurement/tags |
| Primary Queries | SQL, JOINs, aggregations | Lookup by key | Filter/index by fields | Traversal and paths | Time ranges, rollups |
| Transactions | Typically strong, ACID | Depends on product/key scope | Depends on engine and scope | Depends on engine | Typically optimized for ingest/time queries rather than cross-entity transactions |
| Schema | Explicitly declared | Flexible value | Flexible but requires validation | Schema/labels/relationships depend on engine | Measurement/tag/field |
| Scaling | Vertical, read replicas, sharding | Partition/hash, distributed | Shard/partition by key | Depends on graph engine, traversal locality | Partition by time/tag/shard |
| Best Fit | Transactions and relationships | Sessions, caches, lookups | Profiles, catalogs, aggregates | Multi-hop relationships | Metrics, telemetry, measurements |
| Risks | Locks, joins, connections, sharded transactions | Hot keys, limited querying | Large documents, schema drift | Traversal explosion, graph partitioning | Cardinality, retention, ingest bursts |

No single column is sufficient criteria for selecting a database. You must evaluate specific products on durability, HA, backups, consistency, encryption, regions, quotas, SLAs, and operational readiness.

## 9. Schemas, Keys, and Indexes

### 9.1. Choosing Identifiers

Keys should be stable, unique within the required scope, and supportive of access patterns. Common choices:

- **Natural key:** email or business code; can change and may contain sensitive information.
- **Surrogate key:** system-generated ID; decoupled from business content.
- **Composite key:** combining `tenantId` and `entityId`, or partition key + sort key.

In a multi-tenant system, consider including tenant ID in keys/indexes/partitions to prevent cross-tenant data leaks and keep one large tenant from creating a hotspot. Keys are not an authorization mechanism; the service must still enforce tenant and resource access checks.

### 9.2. Indexes Have a Cost

Indexes accelerate reads but consume storage and slow down some write operations. You should:

- Create indexes based on real queries.
- Analyze selectivity and query plans.
- Check sorting/pagination and composite index column order.
- Account for index maintenance and index builds on large tables.
- Remove unused indexes once production metrics are available.

### 9.3. Partitioning and Sharding

**Partitioning** splits data into segments for manageability or query efficiency; it can be by range, list, hash, or time. **Sharding** distributes data across multiple nodes/databases to scale capacity and throughput.

Choosing a partition/shard key requires balancing:

- Evenly distributing load and storage.
- Keeping common queries within few partitions.
- Supporting required transactions and ordering.
- Minimizing hot partitions/hot tenants.
- Allowing changes or rebalancing as scale grows.

Daily partitioning helps manage time-series data, but a query without a time filter may scan many partitions. Sharding by `customerId` helps per-customer queries, but platform-wide reporting may require fan-out.

### 9.4. Pagination and Unbounded Queries

Deep `OFFSET` can be expensive on large tables. Keyset pagination based on a stable sort key can be more efficient:

~~~sql
SELECT booking_id, created_at, status
FROM bookings
WHERE customer_id = 10042
  AND (created_at, booking_id) < (:last_created_at, :last_booking_id)
ORDER BY created_at DESC, booking_id DESC
LIMIT 50;
~~~

Tuple comparison syntax varies by database. You need an appropriate index and a strategy for handling newly inserted records while a client continues paginating.

## 10. Consistency and Transaction Boundaries

### 10.1. Strong Consistency and Eventual Consistency

Some business flows must immediately read newly committed changes; some read models can lag by a few seconds. Database selection must match requirements:

- **Strong/read-after-write consistency:** suited for confirming bookings, deducting inventory, or invariant-sensitive operations.
- **Eventual consistency:** may fit search projections, analytics, or caches.
- **Monotonic/read-your-writes:** needed when clients must not regress to stale state after an update.
- **Bounded staleness:** acceptable maximum lag if supported and verified by the database/application.

Do not use the "eventual" label as an excuse to skip reconciliation design or tolerate data loss.

### 10.2. Transactions Within a Service

A service should own the transactions and invariants of the data it manages. For example, the Booking Service can commit a booking and an outbox record within the same database transaction. Other services consume events and update their own projections.

Do not assume one database's transaction automatically spans a key–value store, event broker, graph store, and time-series database. When coordinating across systems, consider Sagas, outbox/inbox, idempotency, and reconciliation.

### 10.3. Read Models and CQRS

You can use a relational database as the authoritative source for transactions while building document/search/graph/time-series projections for specialized queries. This separates the write model from the read model (CQRS) when the benefits are significant.

Trade-offs:

- Data is replicated and has synchronization lag.
- More schemas, indexes, consumers, and rebuild procedures to maintain.
- Must monitor freshness, lag, duplicates, and projection errors.
- Clients must know which source is authoritative for the question being asked.

Do not adopt CQRS just to use multiple technologies. Start with a single simple database if it meets the workload and SLOs.

## 11. Multi-Database and Polyglot Persistence

### 11.1. Choosing Stores by Access Pattern

Polyglot persistence uses multiple database types within one system, each serving a workload it fits well. Example:

~~~mermaid
flowchart TB
    APP[Application services]
    APP --> SQL[(Relational: booking / payment)]
    APP --> KV[(Key-value: session / cache)]
    APP --> DOC[(Document: listing profile)]
    APP --> GRAPH[(Graph: recommendation relations)]
    APP --> TS[(Time-series: metrics / telemetry)]
    SQL --> OUT[Outbox / event pipeline]
    OUT --> PROJ[Projection consumers]
    PROJ --> DOC
    PROJ --> GRAPH
    PROJ --> TS
~~~

### 11.2. Benefits and Costs

**Benefits:** stores optimized per workload, fewer mismatched queries, independent component scaling, and access to specialized capabilities.

**Costs:** additional systems needing backups, security patches, monitoring, capacity planning, schema/versioning, failover, on-call rotation, and credential management. Cross-store synchronization can be eventually consistent and prone to drift.

### 11.3. Defining the System of Record

Every data domain needs a clear owner:

| Data | Possible System of Record | Replicas / Projections |
|---|---|---|
| Booking status | Booking relational database | Search index, analytics |
| Payment status | Payment database/provider reconciliation record | Booking projection, ledger/report |
| Listing profile | Listing database/document store | Cache, search, graph features |
| Session | Key–value store or identity/session service | May not need long-term copies |
| Service metrics | Metrics/time-series backend | Archive/warehouse |
| Recommendation relationships | Graph/feature store depending on domain | Cache/model inputs |

Do not let two databases both be treated as the authoritative source for the same state field without explicit write-ownership and sync rules. When conflicts occur, it must be clear which owner decides.

### 11.4. Data Synchronization

Outbox/CDC, event streams, or batch ETL can synchronize from the system of record to projections. You must define:

- Event schemas and versioning.
- Deduplication and ordering.
- Retries, DLQs, and replay.
- Handling deletes and expired data.
- Backfills/rebuilds.
- Freshness SLOs and reconciliation.

## 12. Security, Tenancy, and Data Governance

### 12.1. Layered Security

- Network: private endpoints, subnets, firewalls/security groups, and egress policies.
- Identity: workload identity, IAM/DB roles, and least privilege.
- Data: encryption at rest/in transit, key management, and rotation.
- Query: parameterized queries to prevent SQL/NoSQL injection.
- Audit: logging access and sensitive configuration changes.
- Backup: encryption, separate access permissions, and restore testing.

### 12.2. Tenant Isolation

Common models:

| Model | Isolation Mechanism | Trade-offs |
|---|---|---|
| Shared database/shared schema | `tenantId` in row/key | Low cost; requires every query/rule to filter tenant accurately |
| Shared database/separate schema | One schema per tenant | Better logical isolation; complex migrations/connections |
| Database per tenant | Dedicated database per tenant | Stronger isolation; higher cost and operational overhead |
| Hybrid | Dedicated for large tenants, shared for small tenants | Flexible, but requires routing and tiered management |

Tenant isolation must be enforced via server-side authorization and appropriate database policies. Never trust a `tenantId` from a request without validating it against the authenticated identity.

### 12.3. Data Residency and Lifecycle

Classify data and verify processing/storage regions across primaries, replicas, backups, archives, and logs. Even if a database resides in an approved region, replicating, exporting, running CDC, or sending analytics to another region can still violate policy.

Define retention by data type, deletion workflows, legal holds, backup expiration, and how copies in caches/indexes are handled. Never assume a cache TTL replaces deletion obligations in the system of record and projections.

## 13. HA, Backup, and Disaster Recovery

### 13.1. High Availability Is Not Backup

HA keeps the service running when a component fails within a supported failure domain. Backup restores data from a point in time or snapshot; it also protects against accidental deletions or logic corruption that replication would propagate to replicas.

Replication is not backup. If an application accidentally deletes millions of records and the changes replicate, replicas can lose that data too.

### 13.2. RPO and RTO

- **RPO (Recovery Point Objective):** maximum acceptable data loss, measured in data time.
- **RTO (Recovery Time Objective):** target time to restore service.

Choose HA/DR based on business criticality. A multi-zone database handles zone failures but does not necessarily protect against region outages, account compromise, or logical corruption. Multi-region reduces certain risks but adds replication lag, conflicts, and cost.

### 13.3. Backup/Restore Must Be Tested

The plan must verify:

- Automated backups, retention, and point-in-time recovery.
- Snapshot consistency and transaction log coverage.
- Encryption keys remaining available during restore.
- Restoring into a standby account/region if required by the scenario.
- Post-restore data verification procedures.
- Actual RTO/RPO measured during drills.

A backup job reporting `SUCCESS` does not prove the application can boot from that backup. Only a restore test verifies data usability.

## 14. Database Performance and Capacity

### 14.1. Limits to Measure

| Resource | Metrics |
|---|---|
| Compute | CPU, memory, cache, connection pool |
| Storage | Capacity, IOPS, throughput, disk latency |
| Query | p50/p95/p99 latency, slow queries, scanned rows |
| Concurrency | Active connections, locks, waits, transaction duration |
| Replication | Lag, apply rate, failover time |
| Network | Throughput, round-trip time, cross-zone/region traffic |
| Workload | Read/write QPS, transaction rate, payload size, bursts |

### 14.2. Connection Pooling

Serverless applications can spin up many concurrent function instances, each opening multiple database connections. Connection counts can spike sharply even when each function is lightweight. Use appropriate connection pools/proxies, cap concurrency, and test cold starts/fan-out.

A pool that is too large can saturate the database; a pool that is too small makes requests queue. Size the pool based on concurrency, connection hold duration, and database limits.

### 14.3. Read Replicas and Caching

Read replicas offload read queries but introduce replication lag. Caches reduce queries to the source but introduce invalidation, staleness, and privacy risks for sensitive data. Identify which use cases tolerate stale reads, along with TTLs, cache keys, and read-after-write fallbacks.

### 14.4. Query Plans and Benchmarks

Measure using realistic workloads, sufficient data volume, and production-like distribution. Inspect query plans, indexes, locks, cache hit ratios, connections, concurrency, and tail latency. A query running fast on a small table does not prove it will scale on large datasets.

## 15. Migrations and Schema Evolution

### 15.1. Schema Migration

Schema changes can affect running applications. Use the expand–migrate–contract strategy:

1. Expand: add new columns/tables/indexes in a backward-compatible way.
2. Deploy application versions capable of reading/writing both old and new structures during transition.
3. Backfill data in rate-limited batches.
4. Switch reads to the new structure and verify.
5. Contract: drop old structures once all application instances have stopped using them.

### 15.2. Document Schema Evolution

In a document store, older documents may lack new fields or use legacy types. You can migrate on read, run batch backfills, or use dual-read/dual-write during transitions. Track the percentage of migrated documents and set a deadline to retire legacy compatibility code.

### 15.3. Graph and Time-Series Evolution

Graph schemas require managing node labels, relationship types, and properties; renaming an edge can break traversal queries. Time-series schemas require managing measurements/tags, cardinality, and retention; changing tag dimensions can create new series and inflate index/storage usage.

## 16. Architectural Decision Example for a Booking Platform

Suppose the platform needs to:

- Never confirm two bookings for the same inventory/time slot.
- Read a booking by ID and list bookings for a customer.
- Display listings with attributes varying by category.
- Search listings by location/amenities.
- Recommend related items via relationships.
- Monitor application metrics and analyze history.

### 16.1. Proposed Models

| Workload | Candidate Model | Why |
|---|---|---|
| Booking and payment ledger | Relational | Transactions, constraints, and relational queries |
| Session/cart/cache | Key–value | Key lookups, TTL, low latency |
| Listing profile | Document or relational depending on access pattern | Varied attributes, aggregate reads |
| Search by location/amenities | Dedicated search index or read projection | Full-text/filter/geospatial queries |
| Recommendation relationships | Graph when traversal is a primary requirement | Multi-hop path/relationship queries |
| API/infra metrics | Time-series/metrics store | Continuous ingestion and time-window aggregation |

This is an illustrative option, not a mandate to deploy six databases. If a relational database and search service meet requirements well, you can defer adding a graph or document store to reduce operational overhead.

### 16.2. Booking Write Flow

~~~mermaid
sequenceDiagram
    participant API as Booking API
    participant SQL as Relational DB
    participant OUT as Outbox
    participant BUS as Event broker
    participant SEARCH as Search projection
    API->>SQL: Begin transaction
    API->>SQL: Validate inventory / create booking
    API->>OUT: Insert BookingConfirmed
    API->>SQL: Commit
    OUT->>BUS: Publish via CDC/publisher
    BUS->>SEARCH: Deliver event
    SEARCH->>SEARCH: Idempotent projection update
~~~

The relational database holds the authoritative data for bookings. The search index is updated asynchronously; if a user needs to read status immediately after writing, the API reads from the authoritative source or uses a read-your-writes strategy.

### 16.3. Risks to Capture in the ADR

- Which system is the system of record for each entity/field?
- How are double bookings prevented under concurrent requests?
- What is the maximum acceptable search lag?
- From which source are document/graph projections rebuilt?
- How does cache invalidation happen when bookings/listings change?
- How are tenant isolation, backups, encryption, and residency enforced on each store?
- Who is on-call and responsible for recovery if a store/broker/CDC connector fails?
- Does the operational cost of adding another database justify the query benefits?

## 17. Decision Matrix and Selection Process

### 17.1. Weighted Matrix

The architecture team can score each model per criterion from 1–5. Weights depend on project priorities.

| Criterion | Example Weight | Relational | Key–Value | Document | Graph | Time-Series |
|---|---:|---:|---:|---:|---:|---:|
| Multi-entity transactions | 5 | 5 | 2 | 3 | 3 | 1 |
| Lookup by key | 3 | 4 | 5 | 4 | 3 | 2 |
| Flexible nested document | 3 | 3 | 2 | 5 | 2 | 1 |
| Multi-hop relationship traversal | 4 | 2 | 1 | 2 | 5 | 1 |
| Time-window analytics | 4 | 3 | 1 | 2 | 1 | 5 |
| Telemetry ingest workload | 3 | 2 | 2 | 3 | 1 | 5 |
| SQL/reporting flexibility | 3 | 5 | 1 | 3 | 2 | 3 |

The scores above are high-level illustrations, not product benchmarks. In a real decision record, replace them with prototype results and verification for the target product, version, and region.

### 17.2. Selection Process

1. Gather access patterns, volume, latency, consistency, retention, security, and SLOs.
2. Define the system of record and transaction boundaries.
3. Eliminate models that fail mandatory requirements.
4. Build a prototype with representative data and queries.
5. Benchmark peak/burst load, concurrency, data growth, and recovery.
6. Evaluate backup/restore, replication, failover, quotas, encryption, and regions.
7. Calculate Total Cost of Ownership (TCO), including licenses/managed services, storage, I/O, network, backups, and engineering effort.
8. Record an ADR with the chosen option, rejected alternatives, and conditions to revisit.

### 17.3. Reference ADR Content

~~~markdown
# ADR: Choose a Relational Database as the System of Record for Booking

## Context
- Booking requires checking invariants and updating transactional state.
- Read patterns include lookup by ID and listing by customer.
- Search and analytics can be eventually consistent.

## Decision
- The relational database owns bookings and business transactions.
- Events/outbox are used to update read projections.
- Cache only stores regenerable data.

## Alternatives
- Document database as the authoritative source.
- Key-value store as the booking source.

## Consequences
- Must design indexes, transactions, and connection pools.
- Search projection has lag and requires reconciliation.
- Must evaluate HA, backups, restores, and regional quotas.

## Revisit when
- Write/scale workload exceeds benchmarked capacity.
- Access patterns or consistency requirements change significantly.
~~~

## 18. Common Pitfalls

| Pitfall | Consequence | Improvement |
|---|---|---|
| Choosing a database by trend | Mismatched with access patterns | Benchmark real queries and workloads |
| Using one store for every data type | Some queries perform poorly, schema hard to manage | Classify workloads; adopt polyglot only with clear benefit |
| Thinking document DBs need no schema | Data drift, consumer compatibility breaks | Enforce validation, versioning, and migrations |
| Using key–value for complex JOIN queries | Query logic moves to application, many round-trips | Consider relational or an appropriate projection |
| Using graph for simple relationships | Increased complexity and cost | Choose graph when multi-hop traversal is a core workload |
| Using time-series as a transactional system of record | Hard to protect invariants and update entities | Separate metrics from business transactions |
| Creating too many indexes | Slow writes and bloated storage | Index by access pattern and inspect query plans |
| Sharding too early | Complex transactions, joins, migrations, and ops | Scale vertically, use read replicas, or partition before sharding |
| Treating replicas as backups | Accidental deletes/corruption propagate to replicas | Independent backups and restore tests |
| Treating cache as authoritative source | Data loss or stale state | Clarify source of truth and cache invalidation |
| Not defining data ownership | Multiple stores write the same state, causing conflicts | Define system of record and clear write permissions |
| Ignoring operational cost of multiple stores | Growing operational debt and incident risk | Calculate TCO and assess on-call capacity |

## 19. Applied Exercises

### Exercise A — Booking and Transactions

A booking flow needs to check inventory, create a booking, and record a payment in a single invariant-preserving workflow. A team proposes a key–value store because lookups by `bookingId` are fast.

**Question:** Why is fast lookup insufficient to justify choosing key–value?

**Hint:** You must evaluate transactions, constraints, relational queries, concurrency, and the authoritative source. Key–value can handle caching/lookups, while booking/payment transactions may require a relational store or another design providing equivalent invariant guarantees.

### Exercise B — Multi-Type Profiles

Listings include apartments, hotels, and homestays; each type has unique attributes, yet all are read by `listingId`.

**Question:** What benefits and risks does the document model bring?

**Hint:** Nested fields and flexible schemas help store aggregates close to access patterns. You need validation/versioning, size limits, indexing, embed/reference rules, and migration for older documents.

### Exercise C — Multi-Hop Relationships

The system needs to find all listings within three hops of a given listing through regional/partner relationships and related recommendations.

**Question:** When is a graph database worth considering?

**Hint:** When multi-hop traversal is a core, frequent query and benchmarks show clear gains over relational/search. You must limit traversal depth, cardinality, indexes, and traversal cost.

### Exercise D — High-Cardinality Metrics

The system records metrics with tags `service`, `region`, `environment`, and a unique `requestId` for every request.

**Question:** What problem arises from making `requestId` a tag?

**Hint:** Cardinality explodes, driving up index size, memory consumption, and cost. Put `requestId` in traces/logs; keep metric dimensions to bounded-cardinality values.

### Exercise E — Multi-Database Consistency

The booking relational database commits successfully; the search document projection has not updated yet due to CDC lag.

**Question:** Where should the API read when looking up a booking immediately after writing?

**Hint:** Read from the Booking system of record or apply read-your-writes using versioning. Search is an eventually consistent projection and must not be used to conclude a booking does not exist.

### Exercise F — Choosing Databases by TCO

The team can run a single managed relational database or add key–value, document, and graph stores. Adding three stores speeds up some queries but increases on-call, backup, schema, and sync overhead.

**Question:** What evidence is needed before choosing polyglot persistence?

**Hint:** Prototypes/benchmarks, latency/throughput requirements, full-lifecycle costs, operational readiness, query benefits, and consistency/rebuild plans—not just comparing compute pricing.

## 20. Checklist Before Approving Database Architecture

- [ ] Access patterns and read/write/transaction workloads are quantified.
- [ ] Entities, relationships, keys, schemas, and systems of record have clear owners.
- [ ] The data model satisfies required queries, constraints, consistency, and transactions.
- [ ] Indexes, partition/shard keys, and pagination are designed around real queries.
- [ ] Volume, growth, bursts, connections, IOPS, throughput, and hot keys are forecasted.
- [ ] Prototypes/load tests exist using representative data and query distributions.
- [ ] HA, replication, backup/restore, RTO/RPO, and DR have been evaluated.
- [ ] Schema migrations, versioning, backfills, and rollbacks are planned.
- [ ] Multi-database setups have clear authoritative sources, outbox/CDC/inbox, and reconciliation where needed.
- [ ] Tenant isolation, IAM, encryption, secret rotation, and auditing are designed.
- [ ] Regions for primaries, replicas, backups, logs, CDC, and analytics comply with data policies.
- [ ] Retention, TTLs, delete propagation, archiving, and legal holds are defined.
- [ ] Monitoring covers slow queries, p95/p99 latency, connections, locks, lag, storage, and quotas.
- [ ] TCO includes database compute, I/O, storage, egress, backups, licenses, staffing, and on-call effort.
- [ ] An ADR documents the choice, alternatives, trade-offs, and conditions to revisit.

**Key takeaway:** Relational excels at structured relationships and transactions; key–value optimizes key-based access; document fits flexible profiles; graph shines on multi-hop relationship queries; time-series suits timestamped measurements. Choosing the right database means matching the model to workload, consistency, and data ownership while proving operational readiness, recoverability, and cost in the cloud.
