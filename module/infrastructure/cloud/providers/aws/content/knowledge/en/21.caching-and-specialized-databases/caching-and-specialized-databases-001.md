# Choosing Cache, Document, Graph, and Time-Series Databases

An e-commerce system might use **Amazon Aurora** to store orders, need fast product list responses with a **cache**, store a product catalog with frequently changing attributes using a **document model**, detect fraud rings using **graph relationships**, and analyze temperature/latency over time with a **time-series database**. All four needs can appear at the same time, yet you do not necessarily have to use a single database type for everything.

This lesson belongs to the **Caching and Specialized Databases** chapter of the **CLOUD_PROVIDERS_AWS** module. Its goal is to build the ability to select AWS services based on **access patterns**, data model, latency, consistency, scalability, durability, security, recovery, and cost; while connecting the design with Regions/AZs, IAM, VPC, compute, storage, databases, integration, and serverless.

Core services covered:

- **Cache:** Amazon ElastiCache (Valkey, Redis OSS, Memcached) and the case for a durable in-memory primary database with **Amazon MemoryDB**.
- **Document:** **Amazon DocumentDB (with MongoDB compatibility)**; consider **Amazon DynamoDB** when document-like JSON is primarily accessed by keys/access patterns.
- **Graph:** **Amazon Neptune Database** for graph applications and **Neptune Analytics** for graph exploration/algorithms.
- **Time series:** **Amazon Timestream for InfluxDB**, especially **InfluxDB 3 Core/Enterprise** for new workloads; distinguish this from **Timestream for LiveAnalytics**, which is currently not open to new customers.

**Guiding principle:** choose a database based on **the questions the application needs to answer**, not merely because data can be represented as JSON, a graph, or timestamps.

## 1. Learning Objectives

After this lesson, learners can:

1. Identify **cache-aside, read-through, write-through, TTL, invalidation, and cache stampede**.
2. Compare **ElastiCache for Valkey/Redis OSS/Memcached**, **serverless/node-based**, and **MemoryDB** based on their role as a cache or a primary database.
3. Choose **DocumentDB** or **DynamoDB** based on query patterns, indexes, document structure, and MongoDB compatibility needs.
4. Distinguish between a **property graph** and an **RDF graph**, and know when to use **Neptune Database** or **Neptune Analytics**.
5. Design a **time-series schema** around timestamps, measurements, tags/dimensions, retention, and cardinality.
6. Understand the product status of **Timestream for LiveAnalytics** for new systems and how to evaluate **Timestream for InfluxDB 2/3**.
7. Design multi-datastore architectures with a clear **source of truth**, synchronization mechanism, consistency, and DR.
8. Build an evaluation matrix for **latency, throughput, HA, backup, security, monitoring, and cost**, and validate it with benchmarks.
9. Use AWS CLI/Java/pseudocode to inspect services, handle errors, and work through practical scenarios.

## 2. Asking the Right Questions Before Choosing a Database

A JSON document can be stored in S3, DynamoDB, DocumentDB, or PostgreSQL JSONB. A relationship between two accounts can be stored as two foreign keys in RDS or as an edge in Neptune. A CPU measurement with a timestamp can appear in CloudWatch, OpenSearch, S3, or a time-series DB. **The storage data format alone is not enough to make a decision.**

### 2.1. Six Architectural Questions

| Question | Signals to watch for | Impact on selection |
|---|---|---|
| **Access pattern** | Key lookup, nested filter, graph traversal, time-window aggregation | Matters more than the data format name |
| **Latency/SLO** | p95/p99 in a few ms, dashboards in seconds, batch in minutes | Cache/in-memory, indexes, or analytics engine |
| **Consistency** | Is stale data acceptable? Is read-your-writes required? | Cache invalidation, read/write consistency, transactional DB |
| **Durability** | Can lost cache data be rebuilt? Is it the authoritative record? | ElastiCache vs durable primary, backups/replication |
| **Scale/cardinality** | How do keys/edges/series/attributes grow? | Partitioning, high-cardinality indexing, cluster sizing |
| **Operations/cost** | Variable traffic, data retention, HA, security | Serverless/node, storage tiers, Multi-AZ, observability |

### 2.2. Distinguishing Source of Truth from Derived Data

The **source of truth** is where authoritative records are governed and recovered. A **cache** is typically a speed-optimized copy of the source of truth; it can be deleted/rebuilt when TTL expires or eviction occurs. **Graph projections** and **time-series analytics** can also be derived data from events, yet still require backfill and rebuild mechanisms if the source system retains history.

Do not assume every in-memory service is only a cache: **MemoryDB** is designed as a durable in-memory database, and ElastiCache durability features can vary by **engine/version/deployment option**. Therefore, evaluate the **actual durability contract of the selected version**, rather than relying on generic slogans.

## 3. AWS Service Selection Matrix by Workload

| Need | Service to evaluate first | Data/query shape | Cautions |
|---|---|---|---|
| Accelerate product queries / sessions / rate limits | **ElastiCache for Valkey** or Redis OSS | Key-value, hash, set, sorted set, and TTL | Invalidation, eviction, failover, hot keys |
| Simple key-value cache with multi-threading | **ElastiCache for Memcached** | Ephemeral key-value | Fewer features/data models than Valkey, different HA/persistence |
| Primary database needing in-memory speed and durability | **Amazon MemoryDB** | Valkey/Redis-compatible structures and queries | Durability/consistency, topology, write latency/cost |
| Flexible catalog/profiles, nested document filters | **Amazon DocumentDB** | JSON/BSON documents, MongoDB-compatible API | Not 100% MongoDB compatible, query/index migration |
| JSON profiles/orders accessed primarily by clear partition/sort keys | **Amazon DynamoDB** | Key-value/document attributes, predefined access patterns | Query key/index design, hot partitions, scan cost |
| Multi-hop relationships: fraud rings, social connections | **Amazon Neptune Database** | Property graph or RDF, Gremlin/openCypher/SPARQL | Do not turn every SQL JOIN into a graph |
| Community detection, centrality algorithms on large graphs | **Neptune Analytics** | In-memory graph analytics, algorithms | Does not automatically replace a transactional graph database |
| Sensor/IoT/observability metrics, time-based queries | **Timestream for InfluxDB 3** | Timestamps, tags, fields, range/aggregation | Cardinality, retention, write batching, edition |
| Existing Timestream LiveAnalytics deployments | **Timestream for LiveAnalytics** (eligible existing customers) | Time-series analytical queries | **Closed to new customers since 2025-06-20** |
| Very old batch data, infrequent queries | **Amazon S3 + Parquet + Athena** | Data lake/scan/analytics | Does not replace OLTP/low-latency cache |
| Full-text search and log search | **Amazon OpenSearch Service** | Text relevance, inverted indexes, aggregation | Not by default a transactional source of truth |

**Example:** an application needs low-p99 product price lookups by ID ⇒ DynamoDB/Aurora as the data source, ElastiCache as the acceleration layer. An application needs to find accounts connected to a fraudulent account across **4 relationship hops** ⇒ Neptune is worth evaluating instead of storing arrays of IDs inside a document.

### 3.1. Simple Decision Tree

~~~mermaid
flowchart TD
    REQ["Define workload + SLO"] --> Q{"What are most queries?"}
    Q -->|"Very fast key lookup,<br/>rebuildable data"| CACHE["ElastiCache<br/>Valkey / Redis OSS / Memcached"]
    Q -->|"Durable primary<br/>in-memory"| MEM["MemoryDB or ElastiCache<br/>with appropriate durability"]
    Q -->|"Nested documents,<br/>rich filters/aggregation"| DOC["DocumentDB<br/>or RDS JSONB"]
    Q -->|"Key-driven NoSQL<br/>JSON attributes"| DDB["DynamoDB"]
    Q -->|"N-hop graph<br/>traversal/relationships"| GRAPH["Neptune Database"]
    Q -->|"Graph algorithms<br/>exploration"| ANALYTICS["Neptune Analytics"]
    Q -->|"Timestamp + window<br/>aggregation"| TIME["Timestream for InfluxDB"]
    Q -->|"Cold historical<br/>data scans"| LAKE["S3 + Parquet + Athena"]
    CACHE --> SAFE["Verify consistency,<br/>IAM/VPC, HA, benchmark, cost"]
    MEM --> SAFE
    DOC --> SAFE
    DDB --> SAFE
    GRAPH --> SAFE
    ANALYTICS --> SAFE
    TIME --> SAFE
    LAKE --> SAFE
~~~

This is a **starting point**, not a mandatory formula. A system can use **one primary database plus several specialized projections** if the data and SLOs genuinely demand it. Each additional database increases **sync complexity, credentials, KMS, backup, and operational cost**.

## 4. How Caching Works and When It Helps

A cache reduces latency and read pressure on the primary database. In the common **cache-aside** pattern, the application decides to read the cache, fall back to the DB, and repopulate the cache after a miss.

~~~mermaid
sequenceDiagram
    participant U as API request
    participant APP as Java service
    participant C as ElastiCache
    participant DB as Aurora / DynamoDB
    U->>APP: GET /products/42
    APP->>C: GET product:42
    alt Cache hit
        C-->>APP: Cached JSON / value
    else Cache miss
        C-->>APP: nil
        APP->>DB: Read product 42
        DB-->>APP: Authoritative record
        APP->>C: SET product:42 TTL 120s
    end
    APP-->>U: Product response
~~~

### 4.1. Common Patterns

| Pattern | Read | Write/Update | Trade-offs |
|---|---|---|---|
| **Cache-aside / lazy loading** | App reads cache; on miss, reads DB and populates cache | App updates DB then invalidates cache | Miss penalty, prone to stale data if invalidation is missed |
| **Read-through** | Cache layer fetches from source on miss per client/provider design | Depends on layer | Integration complexity; not natively supported by every engine |
| **Write-through** | Reads from cache or source depending on design | Synchronously updates cache and source on the write path | Can increase write latency; requires failure atomicity handling |
| **Write-behind / write-back** | Cache serves first | Writes asynchronously to source later | Risk of data loss or delayed writes; unsuitable for critical financial data without durability |
| **TTL** | Key expires automatically | No manual invalidation needed for every case | Can remain stale until TTL expires |
| **Explicit invalidation** | Cache hits for still-valid data | Deletes/updates key immediately after DB commit | Requires managing races, event delivery, and namespaces |
| **Negative caching** | Short-lived cache for "not found" | Expires quickly once data appears | Can hide newly created data if TTL is too long |

### 4.2. When Caching Does Not Make Everything Faster

- **Low cache hit ratio:** data is rarely accessed again, wasting memory inefficiently.
- **Payloads too large:** serialization/deserialization and network transfer can exceed an indexed DB lookup.
- **Hot keys:** a single key receives massive traffic, creating shard/node bottlenecks.
- **Simultaneous cache misses:** a cache stampede floods the DB with a surge of queries.
- **Rapidly changing data:** complex invalidation where stale data is unacceptable.
- **Cache loss causing outages:** if the app treats the cache as the source of truth without durability/backup design, failover can lose critical data.

### 4.3. Cache Stampede and Protection Techniques

A popular key expires while 10,000 requests arrive; all requests miss simultaneously and hit the database. Common protection techniques:

1. **TTL jitter:** add controlled randomness so keys do not expire at the exact same moment.
2. **Request coalescing / single-flight:** allow only one request to fetch from the DB for the same key at a time.
3. **Stale-while-revalidate:** return slightly stale values if business logic permits, refreshing in the background with bounded concurrency.
4. **Rate limiting/backpressure:** cap DB fallbacks when the cache fails.
5. **Selective warm-up:** pre-warm frequently accessed keys on deploy/failover rather than scanning the entire DB indiscriminately.
6. **Circuit breaker:** cache timeouts must not hang the entire API; however, fallbacks must also limit DB pressure.

### 4.4. Calculating Cache Hit Ratio

**Hit ratio** = cache hits / (cache hits + misses) over a measurement window. For example, 9,000 hits and 1,000 misses ⇒ **90%** ratio. SLOs must measure **p95/p99 on both hits and misses**, not just average latency. Do not assume a 90% hit ratio is always enough: 10% misses at 20,000 RPS is still 2,000 RPS hitting the database.

## 5. ElastiCache: Valkey, Redis OSS, or Memcached?

**Amazon ElastiCache** supports **Valkey, Redis OSS, and Memcached** with capabilities varying by engine version, node type, and deployment option.

| Criterion | **Valkey** | **Redis OSS** | **Memcached** |
|---|---|---|---|
| Data model | Key-value, hashes, lists, sets, sorted sets, and version-specific features | Redis data structures per supported version | Simple key-value |
| TTL/eviction | Yes | Yes | Yes |
| Replication/failover | Yes, depending on configuration | Yes, depending on configuration | Simpler architecture, different HA/replication |
| Cluster/sharding | Yes, depending on engine deployment | Yes | Key distribution via client/cluster |
| Pub/Sub | Yes | Yes | No |
| Multi-threaded engine | Various I/O threading features by version; execution semantics should be measured | Depends on version | Multi-threaded architecture |
| Rich data types / atomic commands | Broad | Broad | More limited |
| Persistence/durability | Depends on engine/version/configuration; **evaluate new ElastiCache durability features** | Depends on support and configuration | Ephemeral cache, not a primary durable DB |
| Use when | General-purpose caching, rate limits, rankings, sessions | Existing Redis OSS workloads with specific compatibility needs | Simple cache aiming to minimize complexity |

AWS is actively developing **Valkey** with new capabilities (such as vector/full-text/durability depending on version). **Do not treat the table above as a guarantee that every feature is available in all Regions and engine versions.** For code currently using Redis OSS modules/commands, check **compatibility and supported commands** before switching to Valkey or Memcached.

### 5.1. How Do ElastiCache Serverless and Node-Based Differ?

| Criterion | **ElastiCache Serverless** | **Node-based cluster** |
|---|---|---|
| Capacity management | Service automatically adjusts capacity | You choose node family/count, shards, and replicas |
| Billing | Based on current storage/processing units model | Node-hours/capacity by node type |
| Operations | Less granular scaling management | Full control over topology, placement, and hardware |
| Engine support | Limited to supported serverless engines/versions | Broader range of engines/versions/nodes |
| Client behavior | Valkey/Redis OSS serverless uses cluster mode enabled | Cluster mode selectable depending on configuration |
| Best fit | Variable traffic, simplified operations | Steady workloads, specialized sizing, or cost optimization |

**Serverless does not mean unlimited**: there are still service quotas, memory/compute pricing, networking requirements, and client compatibility constraints. With Valkey/Redis OSS serverless, clients require **cluster-mode support**; an older Java library configured with a single-node connection string may not behave as expected.

### 5.2. TTL and Eviction Are Not Durability

**TTL** is a time-based key expiration rule. **Eviction** is the engine removing keys under memory pressure according to the configured policy. **Durability** is the guarantee of preserving data across failures/replication/persistence per engine features. A key with a 24-hour TTL can still be evicted earlier if the cache fills up.

Do not store session tokens, shopping carts, or locks with strict recovery requirements relying solely on default cache behavior; before storing durable state in an in-memory service, evaluate **ElastiCache durability** features or **MemoryDB** for your specific version/SLA and test failure scenarios.

## 6. MemoryDB and the Role of a Durable In-Memory Primary Database

**Amazon MemoryDB** is designed for applications requiring an **in-memory database with durability**, using **Valkey/Redis OSS**-compatible APIs/data structures within supported limits. It is not merely a caching layer in front of another data source: applications can treat MemoryDB as a **primary database** for suitable workloads.

| Question | **ElastiCache** | **MemoryDB** |
|---|---|---|
| Default role | Acceleration cache in front of a DB/source of truth | Durable in-memory primary database |
| On key/cache loss | Usually rebuildable from the DB | Must treat backup/replication/recovery as a primary data system |
| Data durability | Multiple levels/features depending on Valkey engine, version, and deployment | Engineered to persist data durably per service contract |
| Read latency | Very low when data is in memory | Very low when data is in memory |
| Write latency | Depends on async/sync durability and topology | Includes overhead from durable write mechanisms |
| Multi-Region | Depends on features/version | Active-active options available per supported features |
| Cost/TCO | Cache capacity/processing; may still need a backing DB | DB capacity, replication/durability, and potential elimination of a separate backing DB if suitable |

**Do not apply a rigid rule that "ElastiCache is never durable, and MemoryDB is always required for any persistence."** AWS has added durability capabilities to certain **ElastiCache for Valkey** configurations. Base your choice on **RPO, consistency, replica failover, write acknowledgment, backup, and cross-Region recovery** requirements, and verify capabilities for your exact current engine version.

### 6.1. When MemoryDB Makes More Sense Than Cache-Aside

- The application has a **working set that fits entirely in memory** with fast queries over hashes/sets/sorted sets.
- **The data is the authoritative record** and cannot simply be deleted and rebuilt from another Aurora/DynamoDB store.
- You want Valkey/Redis-compatible data types for **real-time scoring, critical sessions/state, or microservices**, with engineered durability and HA.
- You need **replication/multi-Region active-active** under supported features, after verifying conflict resolution semantics.

**Example:** a game leaderboard can live in a cache if it can be reconstructed from an event log. If scores exist only in the in-memory store and must survive failures, the architecture must use **durable primary storage** (MemoryDB or another durable system), not just a TTL cache.

### 6.2. Questions to Test Before Production

1. Is an acknowledged write recovered after a primary node failure?
2. What happens when writes exceed replica/transaction log capacity?
3. What are the RPO/RTO and region failure strategies?
4. When a client reconnects, do read-your-writes/consistency meet business requirements?
5. When migrating from an existing Redis OSS/Valkey setup, are any unsupported commands/modules used?
6. How do replication, memory overhead, backup, and operational costs compare against DynamoDB/Aurora + cache?

## 7. Document Databases: Why JSON Data Alone Is Not Enough to Choose

The **document model** groups related information into flexible documents with nested objects/arrays. It fits when records **vary in attributes**, are typically read/written as a logical unit, and the application needs to **query fields inside the document**.

Example **product catalog**:

~~~json
{
  "_id": "sku-2048",
  "name": "Wireless headset",
  "category": "audio",
  "attributes": {
    "batteryHours": 24,
    "color": "black",
    "connectivity": ["bluetooth", "usb-c"]
  },
  "offers": [
    {"seller": "seller-a", "price": 79.9, "currency": "USD"}
  ],
  "status": "ACTIVE",
  "updatedAt": "2026-11-20T02:00:00Z"
}
~~~

Such a document can be fetched by **_id**, filtered by **category** and **attributes.color**, or aggregated across sellers. Still, ask about the **real queries**: lookup by SKU ⇒ DynamoDB may suffice; many filters/ad hoc aggregations/indexes on nested fields ⇒ DocumentDB is worth evaluating.

### 7.1. Amazon DocumentDB (with MongoDB compatibility)

**Amazon DocumentDB** is an AWS-managed document database service compatible with the **MongoDB API** across AWS-published versions/features. DocumentDB supports CRUD operations, indexes, aggregations, and transactions depending on the specific engine version. AWS-published MongoDB-compatible versions include **4.0, 5.0, and 8.0**, with documented API scope and functional differences.

**MongoDB-compatible does not mean running native MongoDB unchanged on AWS**:

- Certain **commands, aggregation operators, transactions, TTL/indexes, and driver behaviors** differ by version.
- **Retryable writes** and query planner behavior can vary by DocumentDB engine version; do not copy driver defaults blindly while ignoring the compatibility matrix.
- Query results **are not guaranteed to be ordered by default** without an explicit **sort**.
- Connections typically go over **TLS** with VPC security groups and database credentials; the backend needs credential rotation and roles/privileges.
- Workload migrations must test **functional differences** and real performance, not just verify that basic CRUD runs.

### 7.2. Document Modeling: Embedding or Referencing?

| Design | Example | Pros | Cons |
|---|---|---|---|
| **Embedding** | Product contains a few variations or recent reviews | Fast single-document read, good for aggregates | Document bloat, complex concurrent updates |
| **Referencing** | Separate product; reviews/orders reference productId | Prevents unbounded document growth, avoids rewriting entire blocks | More queries/joins or lookup aggregations |
| **Hybrid** | Product stores summary and top 3 reviews; full reviews in another collection | Optimizes hot reads while isolating historical data | Must keep summary and source synchronized |

**Do not embed unbounded events, reviews, or transactions into a single document.** As array elements grow continuously, document size, index updates, and write contention become bottlenecks. Test on data with realistic sizes and distributions.

### 7.3. Illustrative MongoDB-Style Query

~~~javascript
// Example mongosh syntax; requires appropriate collection/indexes.
db.products.find(
  {
    category: "audio",
    "attributes.color": "black",
    status: "ACTIVE"
  },
  {
    _id: 1,
    name: 1,
    "offers.price": 1
  }
).sort({updatedAt: -1}).limit(20);
~~~

To optimize, measure **index selectivity, query plan/explain, document size, and write amplification**. Check compatibility with your target DocumentDB engine before applying indexes or aggregation pipelines. Do not assume MongoDB-specific vector, text, or TTL features behave identically across every release.

## 8. DynamoDB Also Stores Documents, but Optimizes Different Access Patterns

**Amazon DynamoDB** is a fully managed NoSQL database storing **items** composed of string/number/binary/Map/List attributes, capable of representing nested JSON-like data. Data is accessed most efficiently when queried via designed **partition keys**, **sort keys**, and **secondary indexes**.

### 8.1. A Document-Like Item in DynamoDB

~~~json
{
  "PK": "PRODUCT#sku-2048",
  "SK": "META",
  "category": "audio",
  "name": "Wireless headset",
  "attributes": {
    "color": "black",
    "batteryHours": 24
  },
  "status": "ACTIVE"
}
~~~

An item can hold rich **Map/List** structures, but a **FilterExpression does not replace key design**: filters are generally applied **after data has been read by Query/Scan**, so they do not reduce read capacity the way a proper index does. DynamoDB enforces a **400 KiB item size limit** per service quota; oversized documents should be split into multiple items or have large blobs stored in S3.

### 8.2. Choosing Between DynamoDB and DocumentDB

| Criterion | **DynamoDB** | **DocumentDB** |
|---|---|---|
| Primary query pattern | Keys, sort keys, GSIs, and known access patterns | Nested field filters, Mongo-compatible queries, and aggregations |
| Scalability | Serverless-managed capacity/partitions | Cluster/instance/elastic deployment depending on engine and model |
| Document model | Map/List attributes inside an item | BSON-like documents/collections |
| Ad hoc queries | Requires Scan or redesigned schema/indexes; not optimized by default | Stronger for varied document queries, though indexes still matter |
| Transactions | Transactional APIs within service quotas | Transactions per engine version/support scope |
| Consistency | Eventual/strong reads per API/table/index; Global Tables have distinct semantics | Primary/replica read semantics by engine and topology |
| Drivers | AWS SDK DynamoDB APIs | MongoDB-compatible drivers within supported scope |
| Migration from MongoDB | Requires significant key and query redesign | May reduce code changes, but still needs compatibility assessment |

**Example 1:** looking up prices by SKU and fetching orders by userId + timestamp ⇒ DynamoDB fits very well with properly designed partitioning/GSIs. **Example 2:** an admin portal allowing catalog filtering across dozens of category-specific attributes, needing aggregation pipelines, with an existing MongoDB codebase ⇒ DocumentDB is worth evaluating.

### 8.3. When Should You Still Choose PostgreSQL JSONB?

If the workload relies on **SQL JOINs/transactions**, core relational data, and just some flexible JSON metadata, **Aurora/RDS PostgreSQL JSONB** can reduce the number of databases you operate. Do not spin up a separate DocumentDB cluster solely because a few fields are JSON. Inspect **SQL query plans/indexes, throughput, schema evolution, and data consistency** before adding specialization.

### 8.4. Migration Checklist for DocumentDB

1. Inventory MongoDB commands, driver versions, aggregation operators, indexes, change streams, and retry behaviors.
2. Run the **AWS DocumentDB compatibility assessment** and review release-specific functional differences.
3. Choose cluster topology, reader replicas, backup/restore, storage encryption, and VPC/TLS.
4. Migrate using AWS DMS or supported MongoDB tools, with **full load + change capture** where appropriate.
5. Run tests validating **p95/p99 query latency**, explain plans, correctness, and consistency under realistic workloads.
6. Prepare a rollback/dual-read/migration cutover plan; never declare a migration complete after a single data import.

## 9. Graph Databases: Modeling Relationships as First-Class Entities

In a relational model, **users, devices, orders, and payment_methods** tables use foreign keys and JOINs. If queries are primarily **"which orders belong to this customer?"**, SQL or a DynamoDB key query works well. But when the question becomes:

> "Within up to four connection hops, which accounts share devices, addresses, or payment cards and link back to a confirmed fraudulent account?"

Then **relationships** become the core problem. A graph models **vertices/nodes** and **edges**, enabling path, pattern, and neighborhood queries.

~~~mermaid
flowchart LR
    U1["User A"] -->|"USES"| D1["Device X"]
    U2["User B"] -->|"USES"| D1
    U2 -->|"PAID_WITH"| CARD["Card Y"]
    U3["User C"] -->|"PAID_WITH"| CARD
    U3 -->|"FLAGGED_AS"| FRAUD["Fraud risk"]
    U1 -->|"PLACED"| ORDER["Order #123"]
~~~

### 9.1. Property Graph vs. RDF Graph

| Model | Data shape | Query languages in Neptune Database | Examples |
|---|---|---|---|
| **Property graph** | Nodes/edges with labels and properties | **openCypher** or **Apache TinkerPop Gremlin** | Fraud rings, social connections, recommendations |
| **RDF graph** | **Subject-predicate-object** triples | **SPARQL** | Knowledge graphs, ontologies, semantic metadata |

**Do not mix the two models in the same query just because Neptune supports all three query languages.** In Neptune, **openCypher and Gremlin** query property graphs; **SPARQL** is used for RDF graphs. Choose the model upfront when designing input, schema, and queries.

### 9.2. Graph Data Model for Fraud Detection

| Node/edge | Properties | Meaning |
|---|---|---|
| **User** | userId, riskLevel, createdAt | User identity |
| **Device** | fingerprint hash, os | Device used |
| **Card** | tokenizedCardId (never store PAN) | Encrypted/tokenized payment method |
| **Order** | orderId, total, timestamp | Order |
| **USES (User→Device)** | firstSeen, lastSeen | User used device |
| **PAID_WITH (User→Card)** | lastSeen | Account used card |
| **PLACED (User→Order)** | timestamp | Account placed order |

Never put raw card PANs, passwords, or unprotected PII into vertex IDs/properties; still design **IAM/VPC/TLS/KMS, tenant isolation, retention, and query authorization**. Graphs make finding links easy, which also creates risk of exposing entire relationship networks if the query API lacks authorization.

### 9.3. Illustrative openCypher Query

~~~cypher
// Find other users sharing the same device with user-123.
MATCH (u:User {userId: 'user-123'})-[:USES]->(d:Device)<-[:USES]-(other:User)
WHERE other.userId <> u.userId
RETURN DISTINCT other.userId AS relatedUser, d.deviceId AS sharedDevice
LIMIT 25
~~~

With Neptune Database, use the appropriate **openCypher** endpoint/protocol and query syntax supported by the engine version. Do not assume every **Neo4j Cypher** feature is compatible: Neptune supports **openCypher** with its own list of limitations/functional differences.

### 9.4. When Are Gremlin and SPARQL Used?

**Gremlin** is a graph traversal API using programmatic traversal steps, shown conceptually below:

~~~groovy
// Illustrative Gremlin on a property graph; IDs/labels for learning only.
g.V().has('User', 'userId', 'user-123').
  out('USES').
  in('USES').
  dedup().
  values('userId')
~~~

**SPARQL** queries RDF triples:

~~~sparql
PREFIX ex: <https://example.org/>
SELECT ?related WHERE {
  ex:user123 ex:usesDevice ?device .
  ?related ex:usesDevice ?device .
  FILTER (?related != ex:user123)
}
LIMIT 25
~~~

Choose Gremlin or openCypher for property graphs based on team expertise and query patterns; choose RDF/SPARQL when ontologies, linked data, or semantic reasoning representations fit the domain. **Do not push long-term log events into Neptune just because they carry a userId**; typically you keep S3/time-series for event history and project only valuable traversal edges into the graph.

## 10. Neptune Database or Neptune Analytics?

**Amazon Neptune Database** serves **application graph queries/transactions** over operational graph data. **Neptune Analytics** focuses on **large-scale graph analysis**, algorithms for community detection, centrality, shortest paths, anomaly/risk, and exploratory workloads over datasets from Neptune Database or S3.

| Criterion | **Neptune Database** | **Neptune Analytics** |
|---|---|---|
| Purpose | Graph database for applications | Graph analysis/algorithmic processing |
| Workload | Multi-hop queries on operational graphs updated by business events | Community detection, centrality, paths, graph ML/analytics |
| Latency | Targets online graph queries per SLO | Optimized for graph analytics depending on size and algorithm |
| Input | Operational graph data | Graph snapshot/dataset from Neptune or S3 |
| Data lifetime | Long-lived database with HA/backups | Analytical graph with separate lifecycle/capacity |
| Choose when | Per-order fraud alerts, recommendation traversals | Nightly jobs finding fraud communities or network threats |

### 10.1. A Combined Graph Architecture

~~~mermaid
flowchart LR
    EVENTS["Orders / Payments / User events"] --> ETL["Stream / ETL transform"]
    ETL --> GRAPH["Neptune Database<br/>Operational property graph"]
    GRAPH --> API["Fraud detection API<br/>N-hop traversal"]
    GRAPH --> ANALYZE["Neptune Analytics<br/>Community / centrality"]
    ANALYZE --> INSIGHTS["Fraud risk score / patterns"]
    INSIGHTS --> GRAPH
    EVENTS --> RAW["S3 event archive"]
~~~

**Consistency note:** if a graph projection is updated asynchronously from events, there may be **lag** relative to the transactional database. Do not automatically block a transaction based solely on a graph that has not yet ingested recent events without handling **unknown/outdated** states. Design `lastUpdated`/version tracking and backfill.

### 10.2. When You Do Not Need Neptune

- Relationships only involve 1–2 well-indexed JOINs in PostgreSQL.
- The primary need is free-text filtering and search relevance ⇒ consider OpenSearch.
- The need is "count clicks per minute" ⇒ time-series/analytics, not a graph.
- Graph data is tiny, queries are simple, and syncing a secondary graph costs more than it returns.

**Before adding a graph DB**, benchmark **query complexity, number of hops, degree distribution, update rate, projection lag, hot vertices, and graph storage cost** against your existing SQL solution.

## 11. Time-Series Databases: Querying by Time Instead of Single Keys/Documents

**Time-series data** is a sequence of timestamped observations, such as server CPU utilization, industrial machine temperature, device telemetry, transactions per minute, or p99 API latency.

A measurement point consists of:

- **Measurement:** data type, e.g., **temperature**, **http_request**, **cpu**.
- **Timestamp:** observation time, requiring consistent timezone/precision.
- **Tags/dimensions:** metadata for filtering and grouping, e.g., **deviceId, region, service**.
- **Fields/measures:** measured values such as **temperatureC, latencyMs, count**.

Conceptual record example:

~~~json
{
  "measurement": "temperature",
  "time": "2026-11-20T03:00:00Z",
  "tags": {"site": "factory-2", "deviceId": "sensor-17"},
  "fields": {"temperatureC": 28.4, "humidityPercent": 67.2}
}
~~~

Typical queries include:

1. **Last value:** the latest temperature of a device.
2. **Time window:** 5-minute average/maximum over 24 hours.
3. **Grouping:** p95 latency by service/Region over one hour.
4. **Alerting:** detect sensors exceeding a threshold for 10 minutes.
5. **Downsampling:** roll up 1-second data into 1-minute or 1-hour aggregates for long-term storage.
6. **Retention:** keep raw metrics for 7–30 days, aggregates for months/years as required.

### 11.1. Why Not Just Write Every Point to RDS?

RDS can store timestamped rows and run SQL well for many workloads. However, high ingestion throughput, time-based retention, downsampling, and time-window queries across billions of records can require complex **partitioning, indexes, compression, data tiering, and lifecycle** management. Purpose-built time-series engines optimize their storage and execution models for these workloads.

**A time-series database is not mandatory** if you only write a few hundred rows per day and SQL time-window queries already meet SLOs. An existing Postgres/Aurora system may be sufficient and simpler than operating an additional service.

## 12. Amazon Timestream for InfluxDB: Modern Options with InfluxDB 2/3

**Amazon Timestream for InfluxDB** provides managed InfluxDB on AWS. For **InfluxDB 3**, AWS distinguishes between **Core** and **Enterprise**; the InfluxDB 3 architecture uses Arrow/DataFusion, **Parquet**-formatted data, and an **Amazon S3**-backed storage layer per the engine design. This is a different product from traditional **Timestream for LiveAnalytics**.

### 12.1. InfluxDB 3 Core vs. Enterprise

| Criterion | **InfluxDB 3 Core** | **InfluxDB 3 Enterprise** |
|---|---|---|
| Node topology | Single-node | Single-node or multi-node options depending on supported configuration |
| Best suited for | Dev/test, near-real-time recent data | Production HA, long-term retention, and complex analytics |
| Long-term data | Not ideal due to lack of compaction | Includes compaction and historical optimization |
| HA | Single node has availability limits | Multi-node can span multiple AZs |
| Read/write scaling | Bounded by single-node resources | Scales across roles/nodes depending on version |
| Cost | Simpler for small/short-lived workloads | Higher capacity/cluster/storage and networking costs |

**Do not choose Core for multi-year retention just because it looks cheaper at creation time.** AWS recommends Core for recent data due to compaction limitations; Enterprise is better suited for historical analytics, high-cardinality data, and high availability. Node limits, instance classes, and Regions change over time; verify current console/docs.

### 12.2. InfluxDB 2 and InfluxDB 3 Differ Beyond Version Numbers

InfluxDB 2 is commonly associated with InfluxQL/Flux and the TSM engine depending on version/configuration; InfluxDB 3 uses a different architecture and query mechanisms. When migrating, verify:

- **Write API/line protocol compatibility** and retention semantics.
- **Query languages** used in applications/dashboards (InfluxQL/Flux/SQL) per version.
- **Tags/fields cardinality**, schema, and timestamp precision.
- **Client libraries, authentication tokens, permissions**, endpoints, and SSL/TLS.
- **Backup/restore, HA, compaction, plugins/extensions** across Core/Enterprise.

Do not assume every Flux query from InfluxDB 2 runs unmodified on InfluxDB 3.

### 12.3. Illustrative Line Protocol

An InfluxDB line protocol measurement looks like:

~~~text
temperature,site=factory-2,deviceId=sensor-17 temperatureC=28.4,humidityPercent=67.2
~~~

This is an **illustrative line protocol sample without an explicit timestamp** (the server can assign the write timestamp per write API semantics). When sending real telemetry, define timestamp precision, clock synchronization, retry/deduplication, and late-arriving data handling. Examples illustrate data syntax only, not production access commands.

### 12.4. Avoiding Tag Cardinality Explosion

**Cardinality** is the number of series or unique tag value combinations that can occur per engine/schema. Using a unique **requestId** tag across billions of requests can cause cardinality to explode, driving up indexes, cache, memory, and cost. Tags like region/service/device are often useful, though they still require real measurement. **Raw requestId** is usually better kept in logs/traces/S3 rather than used as a grouping time-series tag.

Example:

| Tag | Approximate cardinality | Consideration |
|---|---|---|
| **region** | 3–20 | Usually manageable |
| **service** | 20–500 | Generally suitable for aggregation |
| **deviceId** | 100,000+ | Requires sizing for high-cardinality workloads |
| **requestId** | Millions/day | High risk of cardinality explosion; avoid indiscriminate use |

**There is no universal cardinality threshold for every time-series engine.** Benchmark with production-like tag volumes, retention, write throughput, query shapes, and instance sizes.

## 13. Timestream for LiveAnalytics: Important Product Status

**Amazon Timestream for LiveAnalytics** is a time-series analytics service previously widely used to ingest, store, and query timestamped data with **memory/magnetic storage tiers**, retention policies, and scheduled queries as documented for the service.

**Service selection update:** AWS **closed Timestream for LiveAnalytics access to new customers as of June 20, 2025**. Eligible existing customers whose payer accounts already used the service may continue operating or onboarding users/linked accounts under AWS terms. For **new customers**, AWS recommends evaluating **Amazon Timestream for InfluxDB**, and **InfluxDB 3** fits many modern analytics workloads.

| Scenario | Recommendation |
|---|---|
| **New time-series application, account never used LiveAnalytics** | **Do not design new dependencies on LiveAnalytics**; evaluate InfluxDB 3 Core/Enterprise and alternatives |
| **Existing system already running LiveAnalytics** | May continue per AWS eligibility; review support, quotas, retention, lifecycle, and migration readiness |
| **Need long-term analytics with compression/historical queries** | Evaluate **InfluxDB 3 Enterprise** or S3/Parquet/Athena based on SLOs |
| **Only need dashboards for the latest few days of metrics** | Consider **InfluxDB 3 Core** if single-node availability is acceptable |
| **Need CloudWatch application metrics/alerts** | Check **Amazon CloudWatch** before running a separate time-series DB |

**Do not treat LiveAnalytics and InfluxDB as two names for the same API.** They have **different ingestion/query APIs, IAM/auth, pricing, and migration semantics**. Moving off LiveAnalytics requires building **data export/backfill, query translation, retention, and validation**—not merely swapping endpoints.

### 13.1. When Are S3/Athena or OpenSearch Better Fits?

| Workload | Typically evaluate |
|---|---|
| **Observability metrics/alarms** already inside AWS | CloudWatch metrics/alarms, with exporter pipelines if needed |
| **Raw events kept for years, queried a few times a month** | Partitioned S3 Parquet + Athena |
| **Full-text log search and exploratory log dashboards** | OpenSearch / CloudWatch Logs Insights |
| **High-throughput timestamped measurements, last-value, time windows** | Timestream for InfluxDB matching SLOs |

Systems often pair **Timestream for InfluxDB for near-real-time queries** with **S3 for long-term historical data**. Align timestamps, retention, data ownership, and replay pipelines so results do not diverge.

## 14. Combined Architecture: One Source of Truth, Multiple Read Models

Example of a marketplace operating with **polyglot persistence**:

~~~mermaid
flowchart TD
    USER["Web / Mobile / Partner API"] --> API["Java API<br/>Lambda / ECS"]
    API --> MAIN["Aurora / DynamoDB<br/>Orders & user source of truth"]
    API --> CACHE["ElastiCache Valkey<br/>Product/session hot reads"]
    API --> DOC["DocumentDB<br/>Flexible catalog projection"]
    MAIN --> OUTBOX["Transactional outbox<br/>or DynamoDB Streams / CDC"]
    OUTBOX --> BUS["EventBridge / SQS / Kinesis"]
    BUS --> PROJECT["Idempotent projection workers"]
    PROJECT --> CACHE
    PROJECT --> DOC
    PROJECT --> GRAPH["Neptune Database<br/>User-device-payment links"]
    BUS --> TS["Timestream for InfluxDB<br/>Operational metrics"]
    BUS --> ARCHIVE["S3 Parquet<br/>Immutable event archive"]
    GRAPH --> ANALYTICS["Neptune Analytics<br/>Fraud graph algorithms"]
    ANALYTICS --> API
~~~

### 14.1. Why Not Write Directly to Five Databases in One HTTP Transaction?

An API attempting to write the same event to Aurora, cache, DocumentDB, Neptune, and a time-series DB **lacks an automatic shared distributed transaction**. If the third write fails, the system drifts out of sync. Instead:

1. Write the **business transaction** to the source of truth.
2. Emit events via a **transactional outbox, DynamoDB Streams, or CDC** depending on the source store.
3. Publish events to **EventBridge/SQS/Kinesis** with retries, DLQs, and schema versioning.
4. Have projection workers update DocumentDB, Neptune, cache, or time-series DB using an **idempotency key**.
5. Record **lastProcessedEventId/version/timestamp** to measure **projection lag**.
6. Maintain the ability to **rebuild projections** from an event archive or source snapshots.

**Eventual consistency must be communicated clearly to users:** right after a product updates at the source, the cache or catalog projection may still lag. If a workflow requires **read-your-writes**, the API can read from the source based on session/version or wait until the projection reaches the committed version.

### 14.2. Consistency Policy per Layer

| Data | Primary source | Derived copy | Consistency SLA |
|---|---|---|---|
| Price/stock at checkout | Aurora/DynamoDB per transaction design | Cache, catalog read model | Checkout reads/updates the authoritative source, never relying on stale cache |
| Product description | Catalog DocumentDB or explicit source | ElastiCache/CDN | May be stale for seconds/minutes depending on requirements |
| Fraud relationships | Events/source updating graph | Neptune/Neptune Analytics | Has lag; explicitly surface update timestamps |
| IoT telemetry | Stream/event archive or authoritative time-series store | Aggregated dashboards | Late-arriving data/backfill handled |
| User sessions | Per system durable/cache contract | Local cache | Expiry, logout/revocation, and failover designed |

**Never allow the same field to be edited independently in two places without conflict resolution.** Establish clear ownership for price, stock, status, and rules; projections should only change through defined events/commands.

### 14.3. Failure Recovery and Backfill

If Neptune experiences a 2-hour outage, the orders API can continue operating when the graph is a projection. After Neptune recovers, workers read from the **event backlog or archive** and apply missing updates; **idempotency** is mandatory so replaying an event does not create duplicate edges. If a time-series sink fails, retain events in SQS/Kinesis/S3 with appropriate retention, monitor DLQ/iterator age, and backfill.

**Do not rely on SQS TTL as a long-term backup.** For data that must remain rebuildable months later, an S3 event archive or separate durable source needs explicit retention and protection policies.

## 15. Security and Networking Across All Four Data Groups

### 15.1. Separating IAM Control Plane from Data Plane

| Service | Control plane authorization | Data plane authorization |
|---|---|---|
| **ElastiCache** | IAM create/modify/delete cluster/cache | Valkey/Redis ACLs, AUTH/TLS, or supported IAM-auth mechanisms by engine/config; Memcached per engine networking/security |
| **MemoryDB** | IAM manage clusters/users/ACLs | Database ACLs/users, TLS, credentials per engine mechanism |
| **DocumentDB** | IAM Create/Describe/Modify cluster | MongoDB-compatible database users/roles, TLS |
| **DynamoDB** | IAM AWS APIs | IAM GetItem/Query/UpdateItem on tables/indexes with conditions |
| **Neptune Database** | IAM manage DB resources | IAM database authentication when enabled, graph endpoint/query permissions |
| **Timestream for InfluxDB** | IAM manage instances/clusters | InfluxDB auth tokens/users, TLS/network per version/edition |

**IAM permission to create ElastiCache does not automatically grant GET on a cache key.** Likewise, **rds:DescribeDBClusters** for DocumentDB/Neptune does not grant data-plane query access. Clearly design the **Java app principal** and each database engine's authentication method.

### 15.2. VPC, Security Groups, and TLS

- Place databases and caches in **private subnets** with security groups allowing traffic only from the **application security group** or approved sources.
- Enforce **TLS in transit** and **at-rest encryption** as supported by each engine/version, managing certificates and key policies.
- Never enable public access or open **0.0.0.0/0** on database ports for quick testing.
- For Lambda/ECS/EKS inside a VPC, verify **subnet placement, DNS, NAT/VPC endpoints, IP capacity, network routing**, and **connection pooling**.
- For time-series ingestion from IoT/internet, use an **authenticated, rate-limited ingestion API/gateway** rather than exposing DB endpoints directly to the Internet.
- Separate admin, application read/write, and read-only analytics permissions; document ownership, resource ARNs, secrets, and rotation policies.

### 15.3. Secrets Management and Authentication

**AWS Secrets Manager** stores and rotates credentials for supported database engines; some services have their own user/ACL/secret management. For a Java application:

1. Use a **Lambda execution role, ECS task role, EKS Pod Identity/IRSA, or EC2 instance profile**.
2. Grant **secretsmanager:GetSecretValue** only on authorized secrets; add **kms:Decrypt** if required by a customer managed key policy.
3. Cache retrieved secrets with a **TTL/refresh-on-failure** and never log passwords/tokens.
4. Enforce **TLS verification** and never disable certificate validation to "fix a timeout."
5. Rotate secrets/ACLs on a maintenance schedule and test reconnect/failover behavior.

**Aurora/RDS IAM database authentication** does not apply automatically to DocumentDB/Neptune/Valkey/InfluxDB. Each engine has its own auth path; always check the relevant data-plane documentation.

### 15.4. Encryption, KMS, and Derived Data

KMS keys for source RDS/Aurora, DocumentDB, Neptune, backups, S3 archives, and Secrets Manager **may all be distinct keys**. Do not grant **kms:* to every application role**. Managed database storage encryption typically uses the key via service grants/policies; a Java app does not need direct `kms:Decrypt` on the storage key merely to query rows the DB already authorizes.

**Data minimization:** graph nodes, cache keys, logs, time-series tags, and object names can expose sensitive information outside the payload body; avoid putting plaintext emails, card numbers, or birth dates in keys/tags. Use internal IDs, tokenization, or salted hashes according to your threat model and access controls.

## 16. Availability, Consistency, Backup, and Recovery

| Service | HA/replication notes | Backup/recovery and consistency |
|---|---|---|
| **ElastiCache Valkey/Redis OSS** | Shards, replicas, Multi-AZ/failover per deployment | Cache rebuild or durable mode/snapshots per engine/version |
| **ElastiCache Memcached** | Keys distributed across nodes; cache loss possible on node failure | Design cache-miss recovery; do not treat as a durable DB |
| **MemoryDB** | Multi-AZ durable log/replication per features | Backups, point-in-time considerations, RPO/RTO, and active-active per mode |
| **DocumentDB** | Cluster/replica topology, failover | Backups/snapshots, engine consistency, read preference |
| **DynamoDB** | Managed availability within a Region | PITR, on-demand backups, Global Tables for Multi-Region |
| **Neptune Database** | Multi-AZ instances/serverless deployment per features | Continuous backup/snapshots, reader endpoints, graph versioning |
| **Neptune Analytics** | Graph lifecycle/analytics capacity | Reload data from Neptune/S3 and protect derived outputs |
| **Timestream for InfluxDB 3** | Core single-node; Enterprise multi-node HA per config | Backups, S3 persistence/compaction per engine; test restores |

### 16.1. Consistency Must Be Measured per Specific Query

A document replica can lag behind the writer. A TTL cache can return stale data. A graph update over an event queue can lag. A time-series point can arrive late, altering minute-level aggregates when re-queried. **Do not apply a blanket "eventually consistent" label to everything**; define:

- What does a source write commit acknowledgment guarantee?
- Does a read immediately after a write need to see the update?
- Is there replica lag, cache invalidation lag, or stream processing lag?
- After failover, can retries cause duplicate side effects?
- Can you rebuild from snapshots/event logs and verify RPO/RTO?

### 16.2. Test Failures Instead of Just Configuring HA

Practice failover, restarts, and rescaling in staging: observe p95/p99 latency, error rates, connection retries, DNS refresh, cache-miss bursts, and keyspace behavior. For document/graph/time-series stores, test snapshot/backup restores and verify **schema, indexes, grants, and data integrity**. Multi-AZ does not mean **automatic Multi-Region disaster recovery**.

## 17. Performance, Sizing, and Cost: Build on Measurements

### 17.1. How Cache Capacity Differs from Database Capacity

**ElastiCache:** memory working set, average key/value size, eviction, hot keys, throughput, replication, ECPUs/serverless or node size drive cost. **DocumentDB:** document/index size, query plans, reader/writer instances, I/O, and cluster topology. **Neptune:** node/edge counts, traversal depth, query cardinality, graph instance capacity. **InfluxDB:** points/second, tag cardinality, time range, downsampling, query concurrency, retention, and compaction.

| Service | Sizing variables to measure | Scenarios causing unexpected cost spikes |
|---|---|---|
| **ElastiCache** | Hot key count, average value size, hit ratio, eviction, network bytes, ECPUs/node count | Caching the entire DB with low hits, key churn, overprovisioned nodes |
| **MemoryDB** | Working set + persistence/replication, write rate, replicas | Keeping all transient events in an expensive in-memory primary |
| **DocumentDB** | Document/index sizes, aggregations/scans, replicas, I/O | Unindexed ad hoc queries, writes causing index amplification |
| **DynamoDB** | RCU/WCU or on-demand requests, item size, GSIs, hot partitions | Scans, unnecessary GSIs, large items, retries/throttling |
| **Neptune Database** | Vertices/edges, degrees, query depth, NCUs/instances | Unbounded traversals, graph scans, oversizing |
| **Neptune Analytics** | Graph load size, algorithm count, runtime/capacity | Keeping graph analytics capacity running when no jobs execute |
| **Timestream for InfluxDB** | Ingested points, tag cardinality, retention, node topology/storage | Tag series explosion, excessive tiny writes/queries, unbounded historical retention |
| **S3 + Athena** | Storage bytes, scanned bytes, requests/queries | Unpartitioned CSV instead of Parquet, every query scanning full history |

### 17.2. p95/p99 Performance Matters More Than Sample Benchmarks

A cache with **1 ms average read** but **300 ms p99** during eviction or CPU contention can violate SLOs. DocumentDB with good median queries yet high p99 on **$lookup/aggregation** queries needs **index/query plan** inspection. Neptune traversal cost depends on **node degree, path length, and filtering**; time-series query cost depends on **tag selectivity and time-range scans**.

Benchmark using:

- Production-like key/document/edge/series distributions, including **hot keys/hot vertices/hot partitions**.
- Realistic read/write ratios, burst traffic, retry rates, and failover/rebalancing.
- Data volume exceeding the working set/cache and simulating real retention.
- Real serverless/node parameters, AZ topology, instance classes, versions, and security configs.
- Compare **p50/p95/p99, errors, throttles, cost per 1,000 requests, or cost per GB stored/year**, rather than picking based on marketing peak benchmarks.

### 17.3. Cost Is More Than Database List Price

**TCO = service fees + data storage + replication/backups + network + logs/metrics + migration/development + on-call incidents.**

Example 1: adding a cache increases the ElastiCache bill but **reduces RDS reads** and allows downsizing the DB instance class. Example 2: splitting DocumentDB off Aurora speeds up catalog queries but adds **CDC pipelines, SQS, DLQs, and data consistency monitors**. Example 3: using Neptune for a simple JOIN increases cost and complexity without real benefit.

**Do not assume fixed unit prices** because AWS pricing varies by Region, engine version, serverless/node mode, resource size, and over time. Use the **AWS Pricing Calculator** and empirical measurements to decide.

## 18. Java Practice: Safe Cache-Aside with a Source of Truth

The example below uses custom interfaces to focus on logic; **it will not compile standalone** without Product, CacheClient, ProductRepository, and JSON serialization implementations. The principles apply to Java services using ElastiCache and Aurora/DynamoDB.

~~~java
import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;

public final class ProductReadService {
    private final CacheClient cache;
    private final ProductRepository repository;

    public ProductReadService(CacheClient cache, ProductRepository repository) {
        this.cache = cache;
        this.repository = repository;
    }

    public Optional<Product> findProduct(String productId) {
        // Do not use email/PII as a key name.
        String cacheKey = "product:v4:" + productId;

        try {
            Optional<Product> hit = cache.getProduct(cacheKey);
            if (hit.isPresent()) {
                return hit;
            }
        } catch (RuntimeException cacheError) {
            // Cache is an optimization layer: emit alert metric, fall back with limits.
            recordCacheFailure();
        }

        // Repository is the product source of truth.
        Optional<Product> product = repository.findById(productId);

        if (product.isPresent()) {
            // TTL jitter to prevent many keys from expiring simultaneously.
            long ttlSeconds = 120 + ThreadLocalRandom.current().nextLong(0, 30);
            try {
                cache.putProduct(cacheKey, product.get(), Duration.ofSeconds(ttlSeconds));
            } catch (RuntimeException cacheError) {
                recordCacheFailure();
            }
        }

        return product;
    }

    public void updateProduct(Product product) {
        repository.updateTransactional(product);
        // Only invalidate after the source-of-truth commit succeeds.
        cache.delete("product:v4:" + product.id());
    }

    private void recordCacheFailure() {
        // Replace with redacted Micrometer/CloudWatch metric/log.
    }
}
~~~

**What is right:** reading the cache first, falling back to the DB on a miss, applying TTL jitter, updating the DB before invalidating the cache, and isolating cache failures from authoritative data access. **What is still needed for production:** cache timeouts, bounded retries/circuit breakers, per-key single-flight, sensible negative caching, idempotent invalidation, read/update race handling, authentication/TLS, schema versioning, and tracing.

### 18.1. Cache Invalidation Race Condition

Example:

1. Request A misses the cache and reads the old price from the DB, but has not written to the cache yet.
2. Request B writes the new price and deletes the cache key.
3. Request A arrives late and writes the **old price** into the cache with a 120-second TTL.

**Simply doing "DB update then DEL cache" is not enough to eliminate every stale-write race.** For critical prices/stock, use **version numbers, conditional cache writes, compare-and-set, event sequence checks**, or bypass the cache during checkout decisions. Match complexity to your consistency requirements.

### 18.2. Negative Caching and Missing Records

If a productId does not exist and receives heavy traffic, briefly caching a **not-found marker** with a short TTL can reduce DB reads. However, when a new product is created, invalidate the marker; never cache missing IDs indefinitely. Avoid caching 403 errors as a shared "not found" across all users, as that can leak state or mask differing permissions.

### 18.3. Do Not Casually Use a Cache as a Distributed Lock

A **SET NX EX** command can help with short-lived coordination, but relying on that lock to guarantee **exactly-once payment** is risky if a process pauses, a lease expires, a failover happens, or a network split occurs. For critical transactions, use **conditional writes/transactions** on the source of truth along with idempotency keys. A cache lock should only be part of an explicitly analyzed concurrency contract.

## 19. AWS CLI: Inventorying Services Without Modifying Resources

The commands below **only read metadata**. They do not connect directly to the data plane and **do not prove** that a user/password/ACL can query data. Replace Region and resource names for your real environment, and use a scoped read-only IAM role. A recent AWS CLI v2 is needed for **Timestream for InfluxDB 3** commands.

### 19.1. Verify Caller, Region, and ElastiCache

~~~bash
aws sts get-caller-identity --output json

# Node-based Valkey/Redis OSS replication groups.
aws elasticache describe-replication-groups \
  --region ap-southeast-1 \
  --output json

# ElastiCache Serverless (Valkey/Redis OSS/Memcached as supported).
aws elasticache describe-serverless-caches \
  --region ap-southeast-1 \
  --output json

# Memcached/other node-based cache clusters metadata.
aws elasticache describe-cache-clusters \
  --region ap-southeast-1 \
  --output json
~~~

Inspect **Engine, EngineVersion, CacheNodeType, Status, cluster/shard/replica counts, endpoints, and TLS/at-rest encryption flags** for each resource type. **DescribeReplicationGroups** applies to Valkey/Redis OSS and does not replace **DescribeCacheClusters** for Memcached. A cluster existing does not guarantee the app has **GET/SET** permissions: also verify engine ACLs/auth and networking.

### 19.2. MemoryDB

~~~bash
aws memorydb describe-clusters \
  --region ap-southeast-1 \
  --output json

aws memorydb describe-acls \
  --region ap-southeast-1 \
  --output json
~~~

Read cluster metadata, nodes/shards, engine, endpoints, ACLs, and encryption without exposing passwords. Before relying on it as a durable primary, verify **backup/restore, replication, and post-failover data** through controlled testing.

### 19.3. DocumentDB and DynamoDB

~~~bash
# DocumentDB clusters and engine versions.
aws docdb describe-db-clusters \
  --region ap-southeast-1 \
  --output json

# DynamoDB: inspect a table's key schema and indexes.
aws dynamodb describe-table \
  --region ap-southeast-1 \
  --table-name products \
  --query 'Table.{Name:TableName,Status:TableStatus,KeySchema:KeySchema,GSIs:GlobalSecondaryIndexes}' \
  --output json
~~~

**Do not read collections/table rows during an inventory step** without an explicit purpose and appropriate permissions. DocumentDB uses a **DB data plane** with MongoDB-compatible users/TLS; DynamoDB uses AWS IAM APIs. Check IAM and VPC endpoints separately rather than assuming a single access model across engines.

### 19.4. Neptune Database

~~~bash
aws neptune describe-db-clusters \
  --region ap-southeast-1 \
  --filters Name=engine,Values=neptune \
  --output json
~~~

Neptune Database can use provisioned or serverless capacity depending on configuration. Verify the **graph model/query language, cluster endpoints, authentication mode, backup/reader topology, and KMS**. AWS CLI commands only return configuration; evaluating the graph requires querying via **Gremlin/openCypher/SPARQL** over an authorized data plane.

### 19.5. Timestream for InfluxDB

~~~bash
# InfluxDB 3 cluster-based resources.
aws timestream-influxdb list-db-clusters \
  --region ap-southeast-1 \
  --output json

# InfluxDB instance-based resources.
aws timestream-influxdb list-db-instances \
  --region ap-southeast-1 \
  --output json
~~~

Before provisioning new resources, verify **AWS Region availability, EngineVersion, Core/Enterprise edition, cluster configuration, authentication, TLS, subnet groups, storage, and pricing**. The control-plane CLI does not replace the data-plane InfluxDB query API or line protocol.

### 19.6. Good Read-Only Workflow

1. Verify the caller IAM role/account and Region to avoid mixing up test/prod environments.
2. Read metadata: engine/version, serverless/node deployment, endpoints, encryption, HA, backups.
3. Read metrics/alarms and cost allocation tags using authorized permissions.
4. Test data queries only with a **read-only application principal** in staging; keep sensitive data out of CLI logs.
5. Record the service-choice assessment and dependency contracts rather than modifying clusters "just to test."

## 20. Troubleshooting by Data Model

| Symptom | Possible cause | What to check |
|---|---|---|
| Low cache hit ratio | TTL too short, mismatched key schema, large working set | Cache hits/misses, key distribution, request traces |
| DB overload when cache TTL expires | Cache stampede, synchronized expirations | Single-flight, TTL jitter, DB connections, fallback limiter |
| Cache returns stale prices | Missing invalidation, race between read and update | Key versions, event delivery, source commit time |
| ElastiCache serverless client fails to connect | Client lacks cluster-mode support, wrong TLS/SG/DNS | Engine/client compatibility, endpoint, VPC |
| Cache evictions/OOM | Memory working set exceeds capacity, hot keys | Evictions, memory utilization, key sizes/policy |
| Increased MemoryDB write latency | Durable write overhead/replication/capacity pressure | Node metrics, throughput, replicas, network |
| Slow DocumentDB queries | Missing indexes, large aggregations, collection scans | Explain/query profiler, index stats, document sizes |
| MongoDB app fails on DocumentDB | Unsupported command/operator, driver, retryable writes | Compatibility matrix for exact engine version |
| DynamoDB throttling | Hot partition, WCU/RCU/GSI capacity limits | Partition-key distribution, throttling metrics |
| Neptune traversal timeout | Dense vertices, unbounded depth/paths, query plan | Query profile, traversal expansion, graph schema |
| Missing graph results | Lagging/failed projection events or bad schema mapping | Event backlog, lastProcessedEventId, DLQ |
| Neptune Analytics runs too long | Graph too large or unsuitable algorithm/capacity | Graph size, algorithm, analytics capacity |
| Slow InfluxDB ingestion | Tiny writes, high cardinality, node capacity | Write batches, tag cardinality, CPU/memory |
| Slow historical queries on InfluxDB Core | Lack of compaction/edition unsuitable for long-term data | Retention, Core/Enterprise, historical data size |
| Cannot create LiveAnalytics in a new account | Service closed to new customers since 2025-06-20 | AWS availability notice; choose InfluxDB |
| Multi-store inconsistency | CDC/outbox stream lag, consumer errors | Source version, event DLQ, projection checkpoint |
| Data decryption failure after restore | KMS key lacks permissions or is disabled | Key state/policy, backup encryption, account/Region |
| Unexpected cost increase | Extra replicas, indexes, high cardinality, scans, logs | Cost Explorer, per-service metrics, tag costs |

### 20.1. Quick Diagnostic Runbook

~~~mermaid
flowchart TD
    A["SLO violation / incorrect data"] --> CLASS{"What is the failure domain?"}
    CLASS -->|"Cache miss/stale"| C["Check hit ratio,<br/>TTL, hot keys, invalidation"]
    CLASS -->|"Document query"| D["Query plan/indexes,<br/>schema, driver/version"]
    CLASS -->|"Graph traversal"| G["N-hop depth, degree,<br/>projection lag, IAM"]
    CLASS -->|"Time-series"| T["Tags/cardinality,<br/>retention, node/compaction"]
    CLASS -->|"Network/auth"| S["VPC SG, TLS,<br/>data-plane ACL, KMS/secret"]
    C --> FIX["Fix one measured root cause"]
    D --> FIX
    G --> FIX
    T --> FIX
    S --> FIX
    FIX --> VERIFY["Load test + correctness<br/>p95/p99 + cost + rollback"]
~~~

When an incident occurs:

1. Identify the exact **service/Region/engine/version** and endpoint, plus the real **caller IAM identity**.
2. Inspect error codes, traceId/correlationId, and **latency, error, capacity, and connection count** metrics.
3. Separate **authentication/network/KMS** issues from **data/query/model** issues; never broaden IAM permissions to fix an index scan.
4. Cross-check the source of truth against the read model and record the **last-known-good record version**.
5. During a cache outage, protect the backing DB with **fallback rate limits** rather than letting every client query the DB simultaneously.
6. For projection lag, temporarily show a "updating" status or read from the authoritative source as business logic requires.
7. Fix in staging, verify request/quota/cost impact and rollback plan, then deploy to production.

### 20.2. Backup/Restore Is More Than Seeing an "Automated Backup" Button

Rehearse **restoring a backup**, connect with fresh roles/credentials, and verify sample queries, record counts, indexes, and performance. For graph/time-series stores, verify schema files, sampling/retention, timestamp precision, and projection rebuildability. For caches, simulate losing all nodes to confirm the source database can survive **cold-cache traffic**.

## 21. Decision-Making Practice Scenarios

### Scenario A — High p99 on a Product Read API

A Spring Boot application stores products in Aurora PostgreSQL. Traffic is 15,000 requests/second, 95% reads and 5% updates. The same set of 20,000 products is read repeatedly. Current p99 exceeds SLO due to database read load.

**Question:** Should you migrate all products to DocumentDB, or add a cache?

**Guidance:** First benchmark **ElastiCache for Valkey/Redis OSS** with cache-aside, TTL, and post-commit invalidation, since the data already has a clear source of truth and hot read patterns. Measure hit ratio, DB fallback QPS, p95/p99, and total cost. Do not migrate the source to DocumentDB merely to solve read latency when specialized document queries are not needed.

### Scenario B — Does a Shopping Cart Need Durable In-Memory Storage?

A shopping cart service stores all state in a standard key-value cache with no backing database or event log. When the cache fails over, some carts lose data and customers complain.

**Question:** How should ElastiCache and MemoryDB be evaluated?

**Guidance:** The shopping cart is **primary business state**. It requires a storage contract with clear durability, backup, HA, and RPO/RTO. Evaluate **MemoryDB**, newer durability capabilities of **ElastiCache for Valkey** per engine version, or DynamoDB/Aurora as the source with a cache in front. Do not try to solve this by increasing TTL.

### Scenario C — Variable-Structure Product Catalog

A marketplace spans electronics, furniture, and clothing. Each vertical has dozens of specialized fields, admins need rich filters on nested attributes and aggregations by seller/category, and the application previously used MongoDB.

**Question:** DocumentDB or DynamoDB?

**Guidance:** **DocumentDB** is a strong candidate to test if you need MongoDB-compatible drivers and rich document queries. You must verify **engine/API compatibility, indexes, aggregation operators, and query plans**. If the real API only runs `GetByProductId` and `QueryBySellerId` with fixed access patterns, **DynamoDB** can be simpler. If the app needs SQL transactions and simple JSON metadata, try Aurora PostgreSQL JSONB before adding a new DB.

### Scenario D — Using DynamoDB Scan for Every Filter

A service stores its catalog as DynamoDB Maps/Lists, but the frontend lets users filter on any attribute, so the backend continuously runs **Scan + FilterExpression** across millions of items. Costs and latency surge.

**Question:** Can you fix this simply by increasing read capacity?

**Guidance:** FilterExpression after a Scan does not turn it into an indexed query. Analyze filter frequencies and design **GSIs/materialized read models**, or evaluate DocumentDB/OpenSearch for flexible query/search needs. Raising capacity masks the symptom without changing the underlying access pattern.

### Scenario E — Detecting Fraud Rings Across Multiple Relationship Layers

Millions of users have **USES device**, **PAID_WITH card token**, and **REFERRED user** relationships. The risk team wants to find accounts connected to a fraudulent account within up to four hops, inspect paths, and identify anomalous communities.

**Question:** SQL joins, Neptune Database, or Neptune Analytics?

**Guidance:** Evaluate **Neptune Database** for online N-hop traversals returning decisions at order time. Use **Neptune Analytics** for scheduled or investigative community detection/centrality. Stick to SQL only if the graph is small and queries require limited joins. Measure degree distribution, latency, projection freshness, IAM, and backfill duration.

### Scenario F — IoT Metrics with Rapidly Growing Series Counts

50,000 sensors send telemetry every 5 seconds. Each point includes **deviceId, location, firmwareVersion, and requestId**. Requirements include time-window dashboards, 12-month retention, and annual reporting.

**Question:** Choose a time-series store and classify the tags.

**Guidance:** Evaluate **Timestream for InfluxDB 3 Enterprise** if you need HA and compaction/historical queries; pair with S3 Parquet/Athena for long-term archiving. The **deviceId** tag requires high-cardinality sizing, while **requestId** will cause series explosion if used as a tag. Apply batching, timezone/precision standards, downsampling, retention, and backfill.

### Scenario G — A New Team Wants to Provision Timestream LiveAnalytics

A new 2026 project plans to adopt **Timestream for LiveAnalytics** based on an old blog post describing SQL queries and memory/magnetic tiers.

**Question:** How should the selection plan change?

**Guidance:** AWS closed new-customer access on **2025-06-20**. Do not build a new architecture on a service closed to new accounts. Evaluate **Timestream for InfluxDB 3** (Core/Enterprise depending on retention/HA), CloudWatch/OpenSearch for observability, or S3/Athena for historical analytics, and verify current Regional availability and pricing.

### Scenario H — Cache Invalidation Runs After DB Commit Yet Data Is Still Stale

Request A reads the old price from the DB after a cache miss; request B writes the new price and deletes the cache; request A then writes the old price back to the cache after B.

**Question:** Why is "write DB then DEL cache" not enough?

**Guidance:** Because of the race between a read miss and a concurrent update. You can use **versioned cache entries**, conditional version-checked sets, sequenced event updates, or avoid caching prices during checkout. Measure and define stale tolerance per business rules rather than promising strong consistency for cache-aside via TTL alone.

### Scenario I — Graph Projection Falls Behind Events

The source of truth records user-device relationships accurately, but the SQS event worker fails for three hours. The online fraud API keeps querying Neptune as if data were complete, missing many new links.

**Question:** How do you coordinate recovery?

**Guidance:** Monitor **event lag/lastProcessedEventId**, DLQs, and worker errors with bounded retries/backpressure. When the graph misses its freshness SLO, the API must distinguish unknown/stale results; after fixing the worker, replay from the event archive and verify **idempotent edge updates**. Never claim graph results always reflect the source instantaneously.

### Scenario J — Cache Lost During Peak Traffic

ElastiCache fails, shifting 30,000 requests/second onto Aurora; the database exhausts connections and the API starts timing out.

**Question:** How do you protect the system?

**Guidance:** A cache is an acceleration layer, so the backend needs **fallback limiters, request coalescing, warm-up, circuit breakers, and adequate read replicas/DB capacity**. Account for **cold-cache traffic** in capacity planning; run chaos/failover drills and alert on cache hit ratio, DB connections, errors, and p99.

### Scenario K — MongoDB Driver Runs, but Aggregations Produce Wrong Results

A team runs migrated MongoDB code on DocumentDB. Basic CRUD works, yet an aggregation pipeline returns different results and retryable writes throw errors depending on engine version.

**Question:** Is data being lost on the network?

**Guidance:** Do not jump to conclusions. Check the **DocumentDB compatibility matrix, functional differences, engine version, retryable writes support**, indexes, and ordering. Test correctness and query plans on real data rather than equating MongoDB wire-protocol compatibility with identical behavior.

### Scenario L — Wanting One Database for Everything

A startup wants to use ElastiCache for caching, orders, document catalog, fraud relationships, and metrics, arguing that everything "can be stored as key-value."

**Question:** Counter this using the decision matrix.

**Guidance:** You can encode the data, but query capability, consistency, durability, and cost will likely not fit. Separate **source of truth**, access patterns, multi-step graph traversals, time-window queries, and backup requirements. Start with the **simplest** database meeting SLOs, adding specialized stores only when benchmarks prove the benefit; if an in-memory store is the primary, enforce an explicit durability contract.

## 22. Production Checklist When Selecting Specialized Databases

- [ ] Documented the **top 5–10 access patterns**, rather than picking a service solely by data format.
- [ ] Identified the **source of truth**, read models, derived data, and field-level ownership.
- [ ] Defined **p95/p99, throughput, consistency, RPO/RTO, retention, and data sensitivity**.
- [ ] For caches, tested **cache-aside, TTL/invalidation, eviction, stampede, hot keys, and cold-cache failures**.
- [ ] Selected **ElastiCache Valkey/Redis OSS/Memcached** based on data structures, clients, and engine version.
- [ ] Compared **serverless vs. node-based** across traffic, instance management, ECPUs/node hours, and cost.
- [ ] If using an in-memory store as **primary**, evaluated **MemoryDB/ElastiCache durability** for the exact engine/version and tested recovery.
- [ ] For documents, compared **DocumentDB, DynamoDB, and PostgreSQL JSONB** against access patterns.
- [ ] Checked **DocumentDB MongoDB compatibility**, indexes, transactions, retryable writes, and migration tests.
- [ ] For graphs, distinguished **property graph/openCypher/Gremlin** from **RDF/SPARQL**.
- [ ] Chose **Neptune Database** for operational graphs or **Neptune Analytics** for graph algorithms.
- [ ] For time series, designed timestamp precision, tags/fields, cardinality, retention, and batching/downsampling.
- [ ] For new projects, avoided dependencies on **Timestream for LiveAnalytics** since new-customer access is closed.
- [ ] Selected **InfluxDB 3 Core/Enterprise** based on recent-vs-historical data, HA/compaction, and Region support.
- [ ] Evaluated alternatives like **S3/Parquet/Athena/OpenSearch/CloudWatch** where appropriate.
- [ ] Implemented **outbox/CDC/stream events, idempotency, projection lag alerts, and backfill** when using multiple data stores.
- [ ] Reviewed IAM/data-plane ACLs, Secrets Manager, KMS, TLS, VPC/SGs, and least privilege.
- [ ] Tested **Multi-AZ/failover, backup/restore, key rotation, and DNS/client reconnect** per engine.
- [ ] Simulated hot partitions, high-cardinality tags, dense graph vertices, and long-tail p99 queries.
- [ ] Measured **cost per request/query/GB retained**, compute, replicas, logs, network, and operational effort.
- [ ] Prepared clear runbooks for **cache outage, data lag, document query errors, graph traversal timeouts, and time-series ingestion backlogs**.
- [ ] Defined **migration rollback, schema/versioning, and cutover plans** before switching a source of truth.

## 23. Key Takeaways

A **cache** reduces latency and read load using refreshable or rebuildable data: choose **ElastiCache** across Valkey/Redis OSS/Memcached, serverless/node-based modes, and explicit TTL/invalidation policies. If **in-memory is the primary data store**, evaluate the actual **durability and consistency** of **MemoryDB** or appropriate ElastiCache configurations—not just GET/SET speed.

**Document databases** like **DocumentDB** fit nested documents, rich filters, and MongoDB-compatible APIs; **DynamoDB** fits application data with **clear key/access patterns** even when storing nested Maps/Lists. **Graph databases** like **Neptune Database** fit multi-hop relationship queries; **Neptune Analytics** fits graph analytics algorithms. **Time-series databases** like **Timestream for InfluxDB** fit timestamped measurements, time windows, retention, and tag cardinality. **Timestream for LiveAnalytics has been closed to new customers since June 20, 2025**, so new architectures must plan around actively open AWS options.

A sound architecture usually **does not need multiple databases from day one**. Start with the simplest database that meets the workload, and add specialized caches or read models only when backed by evidence from **SLOs, query patterns, consistency, resilience, and TCO**. When running multiple data stores, design the **source of truth, event delivery, idempotency, freshness, and backfill** so data never drifts out of sync.

### Official AWS Documentation for Reference

- [AWS Decision Guide – Choosing an AWS database service](https://docs.aws.amazon.com/decision-guides/latest/decision-guides/databases-on-aws-how-to-choose.html) — choosing a data model based on access patterns.
- [Amazon ElastiCache – Choose engine](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/SelectEngine.html) — Valkey, Redis OSS, and Memcached.
- [Amazon ElastiCache – Deployment options](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/WhatIs.deployment.html) — serverless and node-based.
- [Amazon ElastiCache – Related services/MemoryDB](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/related-services-choose-between-memorydb-and-redis.html) — comparing cache and durable in-memory.
- [Amazon MemoryDB – Related services](https://docs.aws.amazon.com/memorydb/latest/devguide/related-services-choose-between-memorydb-and-redis.html) — durable in-memory database.
- [Amazon DocumentDB compatibility](https://docs.aws.amazon.com/documentdb/latest/devguide/compatibility.html) — MongoDB API/driver versions.
- [Amazon DocumentDB functional differences](https://docs.aws.amazon.com/documentdb/latest/devguide/functional-differences.html) — query/index/transaction differences.
- [Amazon DocumentDB migration runbook](https://docs.aws.amazon.com/documentdb/latest/devguide/docdb-migration-runbook.html) — migration planning and testing.
- [DynamoDB data types](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBMapper.DataTypes.html) — documents, Map/List, and keys.
- [Accessing graph data in Amazon Neptune](https://docs.aws.amazon.com/neptune/latest/userguide/get-started-access-graph.html) — Gremlin, openCypher, SPARQL.
- [Neptune Database versus Neptune Analytics](https://docs.aws.amazon.com/neptune-analytics/latest/userguide/neptune-analytics-vs-neptune-database.html) — operational vs. analytical graphs.
- [Amazon Timestream for InfluxDB 3](https://docs.aws.amazon.com/timestream/latest/developerguide/influxdb3.html) — time-series engine, architecture, and data model.
- [InfluxDB 3 Core and Enterprise](https://docs.aws.amazon.com/timestream/latest/developerguide/core-and-enterprise-versions.html) — compaction, HA, and long-term data.
- [Timestream for LiveAnalytics availability change](https://docs.aws.amazon.com/timestream/latest/developerguide/AmazonTimestreamForLiveAnalytics-availability-change.html) — closed to new customers June 20, 2025.
- [Amazon ElastiCache pricing](https://aws.amazon.com/elasticache/pricing/), [Amazon MemoryDB pricing](https://aws.amazon.com/memorydb/pricing/), [Amazon DocumentDB pricing](https://aws.amazon.com/documentdb/pricing/), [Amazon Neptune pricing](https://aws.amazon.com/neptune/pricing/), [Amazon Timestream pricing](https://aws.amazon.com/timestream/pricing/), and [AWS Pricing Calculator](https://calculator.aws/) — controlling costs by Region/configuration.
