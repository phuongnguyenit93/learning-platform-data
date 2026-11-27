# Suitable Use Cases, Limitations, and Selection Criteria for PostgreSQL

Choosing a database management system is more than picking a product with a long feature list. The right decision must start from **data characteristics, consistency requirements, query patterns, workload scale, operational capability, and future cost of change**.

**PostgreSQL** is an open-source relational database management system supporting SQL, ACID transactions, integrity constraints, MVCC concurrency control, multiple index types, and extensibility via extensions. PostgreSQL suits many business applications that require structured data and high correctness while also handling some semi-structured data via `JSONB`.

However, PostgreSQL is not the optimal choice for **every** workload. A petabyte-scale analytical system, massive real-time event streaming ingestion, a large binary object store, or specialized semantic search may require dedicated components or a hybrid architecture.

This lesson helps identify **when to choose PostgreSQL, when to consider other technologies, and what to verify before going to production**. SQL examples use modern PostgreSQL; exact behavior also depends on version, configuration, and installed extensions.

## 1. The Short Answer: Where Does PostgreSQL Excel?

PostgreSQL is often a strong candidate when a system needs a combination of:

- **Clear relational data:** customers–orders–order lines–products, accounts–transactions, classes–students–enrollments.
- **Data integrity:** `PRIMARY KEY`, `FOREIGN KEY`, `UNIQUE`, `CHECK`, `NOT NULL`, and transactions.
- **Flexible SQL querying:** `JOIN`, `GROUP BY`, CTEs, window functions, subqueries, aggregates, and reporting queries.
- **Reliable transactions:** multiple write operations that must succeed or fail together.
- **Controlled schema flexibility:** heterogeneous attributes stored in `JSONB` and queried with appropriate operators/indexes.
- **Long-term evolvability:** schema migrations, extensions, access control, backup/recovery mechanisms, and replication.
- **Concurrent transactional workloads:** many users reading and writing while requiring well-defined constraints and transaction behavior.

For example, an order management application must ensure **every order belongs to a valid customer**, **every order line references an existing product**, and **stock cannot go negative** under concurrent updates. PostgreSQL provides database-level primitives to express and enforce most of these invariants.

Conversely, if the problem is primarily serving static assets via a CDN, ultra-low-latency caching, or storing large video files, PostgreSQL should generally **not be the sole component** fulfilling every role.

## 2. Define Requirements Before Choosing a DBMS

Do not start with "Is PostgreSQL or another database faster?" Turn system requirements into verifiable questions.

| Evaluation Axis | Questions to Answer | Why It Matters |
| --- | --- | --- |
| Data structure | Are there many related entities and foreign keys? | Determines the value of the relational model |
| Consistency | Are multi-table transactions and orphan/duplicate prevention required? | Affects concurrency mechanisms and correctness |
| Query patterns | Primarily key lookups, joins, filtering, reporting, text search, or vector search? | Determines suitable indexes and engines |
| Write frequency | How many writes/sec, transaction size, and contention level? | Affects primary architecture, locks, WAL, and I/O |
| Data volume | Initial size, 1–3 year growth, hot/cold data? | Affects partitioning, backups, and storage |
| Latency | P95/P99 targets, time budgets for APIs and reports? | Affects configuration, indexes, caching, and query plans |
| Availability | What are RPO/RTO, is multi-region failover needed? | Determines replication, backups, and orchestration |
| Operations | Can the team manage VACUUM, backups, upgrades, and monitoring? | Determines true total cost of ownership |
| Integrations | Which ORMs, CDC, BI, search, migration tools, and extensions are needed? | Affects compatibility and dependencies |
| Cost | Compute, RAM, SSD, replication, network traffic, staffing? | Affects long-term efficiency |

No technology can answer these requirements for you. For example, a workload of 10,000 transactions/sec where each transaction updates a different row is completely different from 10,000 transactions/sec contending on a single balance record.

## 3. Primary Fit #1: OLTP with Relational Data

**OLTP (Online Transaction Processing)** is a workload processing many small business operations: creating orders, updating payment statuses, scheduling appointments, adjusting inventory counts, registering accounts, or confirming transactions.

Characteristics that make PostgreSQL a good fit:

1. Data has clear identifier keys and inter-table relationships.
2. Constraints need enforcement in the database itself, rather than trusting application validation alone.
3. Data writes require atomicity.
4. Queries commonly involve filtering, sorting, pagination, and `JOIN`s.
5. The system requires controlled schema evolution through migrations.

### 3.1. Example Order Schema

~~~sql
CREATE TABLE customers (
    customer_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL
);

CREATE TABLE products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    price NUMERIC(12, 2) NOT NULL CHECK (price >= 0),
    stock_qty INTEGER NOT NULL CHECK (stock_qty >= 0)
);

CREATE TABLE orders (
    order_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(customer_id),
    status TEXT NOT NULL
        CHECK (status IN ('pending', 'paid', 'cancelled')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL REFERENCES orders(order_id),
    product_id BIGINT NOT NULL REFERENCES products(product_id),
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0),
    PRIMARY KEY (order_id, product_id)
);
~~~

This is a compact illustrative schema, excluding shipping fees, multi-line purchases of the same SKU, or cancellation/refund policies. Notable points:

- An `order_line` cannot reference a nonexistent `order_id` or `product_id` per the enforced foreign keys.
- Line-item `quantity` must be greater than 0; product `stock_qty` must be non-negative.
- Email and SKU have unique constraints.
- `NUMERIC(12,2)` suits decimal values needing higher precision than approximate floating-point types.
- `TIMESTAMPTZ` stores a point in time convertible across time zones; display formatting is affected by the session's time zone.

**PostgreSQL's core value here is protecting data rules inside the database.** Two services written in different languages are still bound by the same constraints, even if one service omits validation.

### 3.2. Multi-Table Transactions

Suppose the application creates an order and deducts inventory. The steps must be wrapped in an appropriate transaction:

~~~sql
BEGIN;

-- Deduct stock only when sufficient quantity remains.
UPDATE products
SET stock_qty = stock_qty - 2
WHERE product_id = 101
  AND stock_qty >= 2
RETURNING product_id, stock_qty;

-- The application must verify that UPDATE returned exactly one row
-- before proceeding to create the order and order lines.
-- INSERT INTO orders ... RETURNING order_id;
-- INSERT INTO order_lines ...;

COMMIT;
~~~

The example assumes product `101` exists. **If `UPDATE ... RETURNING` returns no rows, the application must `ROLLBACK`**, rather than blindly continuing and committing. A transaction does not automatically know that "out of stock" is a reason to abort unless application code checks the result.

Under high contention, combining the check and update in the **same UPDATE statement** as above avoids a common race condition: two requests both reading sufficient stock and both deducting based on stale reads. A complete design still needs handling for locks, deadlocks, transaction retries, and business idempotency.

## 4. ACID and MVCC: Key Strengths That Must Be Understood Correctly

PostgreSQL supports ACID transactions:

| Property | Meaning for Applications |
| --- | --- |
| Atomicity | Transaction changes commit together or roll back together |
| Consistency | Database constraints are preserved according to their rules |
| Isolation | Concurrent transactions are observed and coordinated per the isolation level |
| Durability | Committed changes are protected by WAL/durability mechanisms and system configuration |

### What Is MVCC?

**Multi-Version Concurrency Control (MVCC)** enables PostgreSQL to manage multiple row versions so normal read queries and write transactions can run concurrently without locking all reads exclusively.

For example, while one transaction updates an order's status without committing yet, a regular `SELECT` in another session sees the committed version matching its snapshot. This helps concurrent read performance.

However, MVCC **does not eliminate all locks or conflicts**:

- Two transactions updating (`UPDATE`) the same row concurrently still wait on each other.
- `SELECT ... FOR UPDATE` is a locking read that explicitly acquires row locks.
- DDL may acquire strong locks and block other queries.
- Stricter isolation levels, especially `SERIALIZABLE`, can raise errors requiring **retrying the entire transaction**.
- Long-running transactions can prevent old row versions from being reclaimed promptly.

Therefore, when evaluating PostgreSQL for concurrent-write workloads, measure real workloads, lock wait rates, deadlocks, transaction durations, and application retry logic—not just a simple throughput chart.

### Choose Isolation Levels Based on Invariants

PostgreSQL commonly defaults to `READ COMMITTED`. Consider `REPEATABLE READ` or `SERIALIZABLE` when business invariants require stronger visibility guarantees, keeping in mind their different costs and retry behaviors.

Example:

~~~sql
BEGIN ISOLATION LEVEL SERIALIZABLE;

-- Read, validate invariants, and update related data.
-- A concurrent transaction may cause this transaction
-- to receive serialization_failure (SQLSTATE 40001).

COMMIT;
~~~

Choosing `SERIALIZABLE` does not mean "concurrency errors never happen." The application must handle serialization failures by starting a new transaction, re-reading data, and retrying the operation under a bounded retry policy.

## 5. Rich SQL Queries: JOINs, CTEs, Window Functions, and Reporting

PostgreSQL excels when query logic goes beyond single-key record lookups:

- Combining multiple tables with `JOIN`.
- Aggregating with `GROUP BY`, `HAVING`, and aggregate functions.
- Organizing multi-step queries with CTEs.
- Using window functions for rankings, running totals, or comparing rows against groups.
- Using date/time, range, array, and JSON types for specific needs.
- Using materialized views when precomputed query results with a refresh strategy are desired.

Example counting orders per customer:

~~~sql
SELECT
    c.customer_id,
    c.full_name,
    COUNT(o.order_id) AS order_count
FROM customers AS c
LEFT JOIN orders AS o
    ON o.customer_id = c.customer_id
GROUP BY c.customer_id, c.full_name
ORDER BY order_count DESC, c.customer_id;
~~~

Example selecting the latest order per customer via a window function:

~~~sql
WITH ranked_orders AS (
    SELECT
        o.*,
        ROW_NUMBER() OVER (
            PARTITION BY customer_id
            ORDER BY created_at DESC, order_id DESC
        ) AS rn
    FROM orders AS o
)
SELECT order_id, customer_id, status, created_at
FROM ranked_orders
WHERE rn = 1;
~~~

This allows serving complex business queries inside the same relational DBMS, reducing the need to offload every small report to another system.

However, **do not turn the OLTP primary into an unbounded heavy analytics warehouse**. A dashboard scanning billions of rows and competing for I/O with payment operations can degrade transactional quality. As analytical load grows, offload it to a replica, a dedicated analytical engine, or an ETL/ELT pipeline.

## 6. JSONB: Flexible Yet Still Inside a Relational Database

One strength of PostgreSQL is the `JSONB` type, which stores JSON objects or arrays in an internally normalized binary format supporting query operators and appropriate indexes.

Example product catalog with attributes varying by product category:

~~~sql
CREATE TABLE catalog_products (
    product_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    attributes JSONB NOT NULL DEFAULT '{}'::jsonb,
    CHECK (jsonb_typeof(attributes) = 'object')
);

INSERT INTO catalog_products (sku, name, category, attributes)
VALUES
    (
      'KB-01', 'Bàn phím cơ', 'keyboard',
      '{"switch":"brown","layout":"TKL","wireless":true}'
    ),
    (
      'BK-01', 'SQL Book', 'book',
      '{"author":"Nguyen A","pages":320,"language":"vi"}'
    );
~~~

Querying by attributes:

~~~sql
SELECT sku, name
FROM catalog_products
WHERE attributes ->> 'layout' = 'TKL';

SELECT sku, name
FROM catalog_products
WHERE attributes @> '{"wireless":true}'::jsonb;
~~~

A GIN index can support many JSONB queries:

~~~sql
CREATE INDEX idx_catalog_attributes_gin
ON catalog_products
USING GIN (attributes);
~~~

A general GIN index can accelerate appropriate JSONB matches such as containment `@>`. However, not every expression like `attributes ->> 'layout' = 'TKL'` will automatically use a full-column GIN index effectively. For a frequently queried key, consider an **expression index**:

~~~sql
CREATE INDEX idx_catalog_layout
ON catalog_products ((attributes ->> 'layout'));
~~~

### When Is JSONB Suitable?

- Some attributes are optional or vary across product types.
- The core still has stable IDs, relationships, and constraints.
- There is a need to query specific JSON paths with clear index designs.
- You want flexible attribute evolution without continually adding columns for every variant.

### When Should You Avoid Overusing It?

- Critical fields needing `FOREIGN KEY`, `UNIQUE`, frequent updates, and high-frequency queries.
- Most business expressions must extract and cast values from JSON.
- Large JSON payloads updated constantly, inflating write, WAL, and bloat costs.
- Structure is actually stable and easy to model as relational tables.

**JSONB does not turn PostgreSQL into a document database identical to every NoSQL product.** PostgreSQL handles semi-structured data well, yet a sound design usually keeps **keys and core attributes in relational columns, and variable details in JSONB**.

## 7. The Extension Ecosystem: Conditional Extensibility

PostgreSQL supports extensions to add data types, functions, operators, and additional capabilities. Common examples:

| Extension / Capability | Problems It Can Help Solve | Things to Verify |
| --- | --- | --- |
| PostGIS | Geospatial data, geometry, spatial measurements and queries | Resources, spatial indexing, version compatibility |
| pg_trgm | Fuzzy string search, trigrams, and certain `LIKE`/`ILIKE` patterns | Index size, match quality |
| pgcrypto | Certain encryption/hashing functions per extension docs | Key management rules, system-wide security posture |
| citext | Case-insensitive text comparison for certain use cases | Locale/collation and actual comparison rules |
| Appropriate vector extension | Storing and searching approximate/exact vectors per extension capabilities | Accuracy, indexing, memory, and deployability |

For instance, if the environment supports `pg_trgm`, a similarity name search can be accelerated with an appropriate index instead of scanning a large text column.

~~~sql
-- Run only after the DBA confirms the extension is allowed in deployment.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX idx_catalog_name_trgm
ON catalog_products
USING GIN (name gin_trgm_ops);

SELECT sku, name
FROM catalog_products
WHERE name ILIKE '%ban phim%';
~~~

This sample query searches for an accent-free substring in `name`; the sample data `'Bàn phím cơ'` (mechanical keyboard) contains diacritics, so matching is **not automatically guaranteed**. `pg_trgm` enhances indexing for string pattern searches, **it does not automatically strip diacritics from accented text**. If business rules require accent-insensitive search, design appropriate text normalization and collations.

**Extensions are not guaranteed to be available on every managed PostgreSQL service.** Check the supported extension list, installation privileges, upgrade policies, and vendor lock-in risks. Never pick a product merely because "PostgreSQL has extension X" if your target hosting environment prohibits installing it.

## 8. Full-Text Search, Geospatial, and Specialized Needs

PostgreSQL includes rich capabilities beyond transactional relational queries:

### Full-Text Search

You can use `tsvector`, `tsquery`, and GIN indexes for token-based and dictionary-configured text search:

~~~sql
CREATE TABLE knowledge_articles (
    article_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    body TEXT NOT NULL
);

CREATE INDEX idx_knowledge_fts
ON knowledge_articles
USING GIN (
    to_tsvector('simple', title || ' ' || body)
);

SELECT article_id, title
FROM knowledge_articles
WHERE to_tsvector('simple', title || ' ' || body)
      @@ plainto_tsquery('simple', 'postgresql index');
~~~

This illustration uses the `simple` configuration; tokenization, diacritic handling, stemming, and relevance for Vietnamese must be evaluated against real datasets and configurations. PostgreSQL supports full-text search, yet does not natively provide every feature such as typo tolerance, advanced autocomplete, broad multi-language analyzers, or large-scale custom ranking.

### Geospatial Data

With PostGIS, PostgreSQL becomes a strong foundation for spatial intersections, distances, coordinates, and geometries. This is a compelling reason when an application needs both relational transactions and GIS inside one database.

However, large-scale GIS systems must verify coordinate systems/SRIDs, indexes, data quality, and resources; installing PostGIS does not replace proper geospatial modeling.

### Vectors and Similarity Search

Ecosystem extensions support storing and searching vectors. They can fit well when scale and requirements align closely with the relational workload. If vector counts are very large, update rates are high, or search algorithms have specialized demands, benchmark latency, recall, storage, and cost against dedicated vector engines.

## 9. Key Limitation: PostgreSQL Does Not Scale Writes Horizontally Out of the Box

A PostgreSQL instance typically has **one primary accepting writes** in a traditional replication topology. Adding read replicas offloads **a portion of read queries**, but does not linearly increase write capacity on the primary.

Factors to consider:

- Primary CPU, RAM, SSD, and network have finite limits.
- WAL, fsync, replication, and checkpointer generate I/O overhead.
- Hot rows and hot indexes can create contention even when overall transaction volume is modest.
- A transaction updating many rows or holding locks for a long time impacts other transactions' latency.
- Indexes speed up reads but increase write overhead and storage footprint.

### Vertical Scaling, Partitioning, and Sharding Are Different

| Approach | Primarily Solves | Does Not Automatically Solve |
| --- | --- | --- |
| Scaling primary CPU/RAM/SSD | Adds resources to one instance | Does not eliminate hot rows or architectural limits |
| Read replicas | Offloads read queries, supports HA | Does not split writes |
| Native partitioning | Manages large tables, narrows eligible query scopes, data lifecycle | Does not turn one primary into multiple independent writers |
| Sharding | Distributes data/write load across nodes | Introduces routing, cross-shard transactions, and operational complexity |
| Caching | Reduces repeated query hits | Does not replace a consistent source-of-truth database |

PostgreSQL offers **declarative partitioning**, which is helpful when data has a natural partition key, such as monthly event logs. Yet partitioning is not a magic switch making every query faster; check partition pruning, partition counts, index design, and global constraints.

If you anticipate millions of events per second across multiple regions that cannot funnel through a single writer, run an early proof of concept for distributed architectures, event ingestion, or sharding instead of assuming a single PostgreSQL node will suffice.

## 10. MVCC Comes with VACUUM and Bloat Management Responsibilities

A key PostgreSQL characteristic is that update/delete transactions leave behind old row versions. PostgreSQL uses **VACUUM** to reclaim reusable space and maintain system metadata.

**Autovacuum** handles much of this routine maintenance automatically, though that does not mean the system is completely hands-off:

- Frequently updated/deleted tables can accumulate dead tuples and bloat.
- Long-running transactions holding old snapshots can block reclamation of dead row versions.
- Abandoned replication slots or snapshot/WAL-retaining mechanisms can cause storage pressure.
- Planner statistics must stay current so the optimizer chooses good plans.
- Monitoring transaction ID age and anti-wraparound status is a serious operational duty.

Initial observation of table status:

~~~sql
SELECT
    schemaname,
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;
~~~

Row counts in statistics views are **estimates**, not exact snapshot counts. Do not disable autovacuum to "boost write performance" without understanding long-term consequences, especially transaction ID wraparound risks.

Teams migrating from other databases must budget for learning and monitoring PostgreSQL's MVCC, VACUUM, WAL, and replication behaviors.

## 11. Indexes Accelerate Reads but Carry a Cost

PostgreSQL supports multiple index methods suited to different query patterns:

| Index Type | Typical Use Cases |
| --- | --- |
| B-tree | Equality, range comparisons, ordered sorting |
| GIN | JSONB containment, full-text search, arrays with matching operators |
| GiST | Certain spatial data, range types, and specialized match operators |
| BRIN | Very large tables whose values correlate with physical order, e.g., ascending timestamps |
| Partial index | Indexes only rows satisfying a predicate |
| Expression index | Indexes values computed from an expression, e.g., `lower(email)` |

Example index supporting queries for pending orders:

~~~sql
CREATE INDEX idx_orders_pending_created
ON orders (created_at)
WHERE status = 'pending';
~~~

This can fit well if only a small fraction of orders are `pending` and the application frequently fetches pending orders chronologically. If most queries filter by other statuses, evaluate further before adding more indexes.

Measure access paths using:

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT order_id, created_at
FROM orders
WHERE status = 'pending'
ORDER BY created_at
LIMIT 50;
~~~

`EXPLAIN ANALYZE` **actually runs the SQL statement**, so be especially careful with DML; the example above uses only `SELECT`. Plans on small lab tables can differ from production due to differing statistics and selectivity.

Do not conclude "PostgreSQL is slow" when a query lacks an index or is poorly designed; nor conclude "PostgreSQL is fast" from a tiny demo with a few dozen rows. Evaluate using representative data, workloads, and configurations.

## 12. High Availability and Recovery: Provides the Tools, Does Not Run Itself

PostgreSQL uses **Write-Ahead Logging (WAL)** to support crash recovery, physical backups, and replication via appropriate mechanisms.

Commonly used capabilities:

- **Streaming physical replication:** replicas receive and replay WAL from the primary.
- **Read replicas:** serve part of the read load within acceptable lag bounds.
- **Point-in-time recovery (PITR):** restore a base backup and replay WAL archives to a chosen timestamp or stop point.
- **Logical replication:** replicate logical changes via publication/subscription within supported scope.
- **Logical backups:** e.g., `pg_dump`, useful for schema/data exports and certain migration scenarios.
- **Physical backups:** protect the cluster at file/WAL level using compatible procedures.

### Limitations to Understand

- Asynchronous replicas can **lag behind the primary**; failover risks losing un-replicated transactions.
- Synchronous replication reduces certain data-loss risks at the cost of latency or availability depending on quorum and configuration.
- Safe primary promotion requires **election/fencing** mechanisms to prevent split-brain; standalone PostgreSQL does not replace an HA orchestrator.
- `pg_dump` does not by itself provide full PITR like a physical backup combined with WAL archiving.
- WAL must be retained sufficiently for replicas and backups; misconfigured archiving or replication slots can fill the disk.
- Being able to take a backup does not guarantee being able to **restore within RTO**; recovery drills are necessary.

If an application requires RPO = 0 and RTO of a few seconds across multiple regions, evaluate network topology, latency, consensus/replication mechanisms, and specific providers. Never infer from "PostgreSQL supports replication" that every SLA tier is automatically achievable.

## 13. PostgreSQL Does Not Replace Every Specialized Data System

A practical architecture often combines multiple tools, each solving part of the problem:

| System / Workload Type | What PostgreSQL Can Do | When to Consider Another Component |
| --- | --- | --- |
| Web OLTP application | Primary relational source of truth, transactions, constraints | When complex global/multi-region multi-writer scaling is required |
| Light/medium analytics | SQL aggregates, CTEs, materialized views, reporting | When scanning massive datasets requiring a columnar warehouse/OLAP |
| Hot-access cache | Store consistent source data | When needing TTL, eviction, and ultra-low-latency caching |
| Text search | Built-in FTS, trigram extension | When needing a dedicated search engine with ranking, typo tolerance, advanced analyzers |
| Vector search | Appropriate extensions | When scale/recall/latency demand a dedicated vector database |
| GIS | PostGIS is a strong choice when supported | When processing satellite imagery or specialized workloads beyond SQL DBs |
| Streaming events | Can serve as source of truth and emit changes via CDC | When needing a large-scale event broker with replay/consumer groups |
| Storing large images/videos/files | Can store metadata and small binary payloads | When object storage/CDN is more appropriate |
| Telemetry/time-series | SQL, partitioning, and extensions handle many loads | When extreme ingest rates, retention, compression, and rollups need a specialized engine |

A hybrid architecture does not mean you always need multiple databases on day one. For small teams, **one well-managed PostgreSQL instance is often simpler than premature data distribution**. However, design clean extension points for when real workloads hit limits.

## 14. Directional Comparison with Common Alternatives

The table below compares **use-case fit**, not an absolute product ranking.

| Option | Typical Strengths | What to Evaluate vs. PostgreSQL |
| --- | --- | --- |
| PostgreSQL | Rich SQL, relational integrity, extensibility, JSONB, ecosystem | Operational overhead, write scaling, tuning, HA |
| MySQL | Popular relational OLTP, broad app ecosystem, many managed offerings | Fit for specific SQL query features and operational behavior |
| SQLite | Embedded directly in the app, simple, no separate server | Multi-client concurrent writes to a centralized server |
| Document database | Flexible document model, document-oriented access | Multi-entity joins/constraints/transactions, reporting queries |
| Columnar analytical warehouse | Efficient large-scale scans and aggregations | OLTP transactions and pipeline maintenance cost |
| Search engine | Specialized search/ranking/analyzers | Transactional source of truth, relational constraints |
| Distributed SQL | Designs supporting distributed data and writes | Latency, SQL feature limitations, complexity, and cost |

Never conclude "PostgreSQL is always better than MySQL" or "NoSQL is always faster than SQL." Performance also depends on **schema, queries, indexes, data, configuration, and consistency goals**. A well-tuned PostgreSQL system may outperform another engine on one workload while trailing on another.

## 15. Selection Criteria by Application Type

### 15.1. E-Commerce or Business SaaS

**Good fit when:** customer–order–product relationships are clear, multi-table transactions are needed, duplicate/orphan data must be prevented, SQL reporting is required, and there is one primary write stream.

**Verify:** p95/p99 latency during concurrent checkout, hot-row inventory updates, retry logic, tenant isolation, HA, and backups. Flexible product specs can live in `JSONB` while keeping core business keys in columns.

### 15.2. Accounting, Payments, and Booking Systems

**Good fit when:** transactional correctness and constraints are top priority, auditability is required, and consistency across multiple records is essential.

**Verify:** isolation levels, balance/ledger design, idempotency, concurrency testing, and audit trails. PostgreSQL supplies strong primitives, yet does not design a valid ledger or safe payment flow for the application.

### 15.3. Dashboards and Reporting

**Good fit when:** report volumes are moderate, joins with OLTP data are needed, and latency budgets are reasonable.

**Consider another system when:** massive scans run frequently and complex BI queries compete for resources with core transactions. In that case, isolate analytical workloads to protect the primary.

### 15.4. Content Management Systems

**Good fit when:** articles, authors, permissions, tags, and comments have clear relationships, while some metadata varies flexibly.

**Verify:** search quality, file/media management, hot reads, and cache/CDN layers. Avoid storing large images or videos directly in PostgreSQL rows when object storage fits better.

### 15.5. Telemetry, Clickstreams, Logs, and Events

**Can fit when:** scale is moderate, SQL querying is valuable, retention is clear, and time-based partitioning is used.

**Re-evaluate when:** continuous event ingestion is massive, retention is long, and queries primarily scan/aggregate billions of rows. Partitioning, compression, streaming, and OLAP strategies may outweigh relational transaction constraints.

## 16. Security and Multi-Tenancy Capabilities

PostgreSQL provides roles, privileges, schemas, and **Row-Level Security (RLS)**, which are valuable in multi-tenant applications.

Example table with a tenant key:

~~~sql
CREATE TABLE tenant_documents (
    document_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id BIGINT NOT NULL,
    title TEXT NOT NULL
);

CREATE INDEX idx_tenant_documents_tenant
ON tenant_documents (tenant_id);
~~~

An essential first step is that **every application query must filter by a verified tenant**:

~~~sql
SELECT document_id, title
FROM tenant_documents
WHERE tenant_id = $1;
~~~

Here `$1` is a PostgreSQL prepared statement parameter placeholder matching driver/protocol syntax; never trust an unauthenticated tenant ID supplied directly by a client.

RLS can add a database-level defense layer, though you must understand policy definitions, table owner behavior, superusers, `BYPASSRLS` roles, and session/connection-pool context. **Enabling RLS with a misconfiguration does not automatically guarantee tenant isolation.**

If the application requires audit compliance, encryption, key management, data residency, and strict access controls, evaluate the infrastructure provider and operational processes as well. The DBMS is one layer, not the entire security model.

## 17. Managed PostgreSQL vs. Self-Managed?

### Managed Service

Advantages typically include reduced operational effort for instance provisioning, snapshots, patching/monitoring, and certain HA features depending on the plan.

Decisions you still own:

- Instance sizing, indexes, SQL queries, and transaction design.
- Actual RPO/RTO versus provider SLAs.
- Point-in-time restore capability and backup testing.
- Extension limits, superuser restrictions, and custom tuning flexibility.
- Costs for I/O, storage, snapshots, replicas, and network egress.
- Vendor lock-in risk from platform-specific features.

### Self-Managed

Offers greater control over configuration, extensions, networking, and HA/backup workflows, while placing full responsibility for security patching, recovery, monitoring, capacity planning, failover, and incident drills on your team.

**Total Cost of Ownership (TCO)** must include on-call engineering time. A managed service with a higher subscription fee is sometimes cheaper than self-hosting once effort and risk are fully accounted for.

## 18. Technical Checklist for a Proof of Concept

Before committing PostgreSQL to a critical system, run a PoC with realistic data and workload profiles.

### 18.1. Describe the Workload

Gather:

- Row counts and average/maximum row sizes per table.
- Read/write ratio and common operations.
- Critical queries, joins, and sorts.
- Concurrent transactions and rate of updates to the same record.
- p50/p95/p99 latency targets for key APIs.
- Data growth rate and retention duration.
- Acceptable replica lag and RPO/RTO targets.

### 18.2. Build a Realistic Schema and Indexes

Do not benchmark a single `id, value` table if the real system has 15 relational tables, JSONB, reports, and inventory updates. Design a representative schema with constraints, indexes, and production-like data skew.

### 18.3. Measure Queries with EXPLAIN

~~~sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.order_id, o.created_at, c.email
FROM orders AS o
JOIN customers AS c
    ON c.customer_id = o.customer_id
WHERE o.status = 'pending'
ORDER BY o.created_at
LIMIT 100;
~~~

Inspect actual row counts, index usage, join strategies, and I/O costs. Do not judge purely by "total execution time" on a tiny table fully cached in memory.

### 18.4. Measure Write Contention and Transactions

Run realistic transactions under workload-representative connection counts. Track serialization/deadlock errors, lock waits, throughput, and p99 latency. Tune transaction duration and connection pooling before scaling up instance size.

### 18.5. Drill Backups and Failover

An infrastructure PoC should simulate:

1. Losing the primary in a test environment.
2. Promoting a replica using the chosen orchestrator.
3. Ensuring the old writer is fenced off to prevent split-brain.
4. Switching application endpoints and verifying transactions.
5. Restoring from backup and WAL archive to a target timestamp.
6. Measuring RTO and actual transactions at risk of loss.

Documentation claiming "replication is enabled" never replaces live drills.

### 18.6. Operational Assessment

~~~sql
SELECT version();

SHOW server_version;

SELECT
    datname,
    numbackends,
    xact_commit,
    xact_rollback,
    deadlocks
FROM pg_stat_database
WHERE datname = current_database();
~~~

These metrics are a starting point for observation, not a complete performance report. Complement them with monitoring for CPU/memory/IOPS, slow queries, WAL/archive status, autovacuum, connections, and backup health.

## 19. Weighted Decision Matrix

A pragmatic approach is scoring PostgreSQL and alternatives **against your specific requirements**. The example below illustrates the method, not objective product scores.

| Criterion | Example Weight | What Must PostgreSQL Prove? |
| --- | ---: | --- |
| Integrity and transactions | 25% | Constraints + concurrency tests pass |
| Query suitability | 20% | SQL/JSONB/indexes match the workload |
| Performance/scalability | 20% | P95/P99 and throughput hold at projected load |
| Backup and availability | 15% | Restore/failover meet RPO/RTO |
| Team operational readiness | 10% | Clear owner, runbooks, monitoring |
| Cost and lock-in risk | 10% | Reasonable TCO, extensions, migration path |

For each option, score 1 to 5 based on **experimental evidence**. Compute total score as the sum of `weight × score`. Mandatory criteria such as integrity, regulatory compliance, or RPO can act as **hard disqualifiers**—never let a high total score mask failure on a non-negotiable requirement.

For instance, if the business mandates ultra-low-latency multi-region writes with a tight RPO, single-primary PostgreSQL may require additional architecture or fail the hard gate—even if its SQL and extensibility are strong.

## 20. Common Misconceptions

### "PostgreSQL Is SQL, So It Cannot Handle JSON"

Incorrect. `JSON` and `JSONB` are first-class data types with dedicated operators and indexes. However, keep relational structure for core keys and invariants.

### "With MVCC, Reads and Writes Never Block Each Other"

Incorrect. MVCC supports consistent reads, yet concurrent updates to the same row, locking reads, and DDL can still cause lock waits. Long transactions also strain VACUUM.

### "Adding More Read Replicas Increases Write Capacity"

Incorrect in a standard single-primary topology. Replicas offload reads and support HA; all writes still go to the primary. Horizontal write scaling is a separate architectural problem.

### "Partitioning Solves Every Large Table"

No. Partitioning helps when partition keys and query predicates align. It can complicate administration if too many partitions are created or queries do not filter on the partition key.

### "Streaming Replication Means Zero Data Loss"

No. Asynchronous replication has lag; failover can lose transactions not yet replicated. RPO depends on replication mode, configuration, and failover orchestration.

### "Automated Backups Guarantee Successful Recovery"

No. You must verify backup scope, continuous WAL archiving, restore capability, and RTO compliance through drills.

### "JSONB Completely Replaces Schema Design"

No. JSONB adds flexibility, yet key references, uniqueness enforcement, numeric typing, and data normalization still require careful design.

### "PostgreSQL Is Free, So Total Cost Is Zero"

The software has a permissive open-source license, but operations, storage, CPU, replication, backups, engineering time, and incident response still carry real costs.

### "Having an Extension for Every Feature Is Always Better"

Not necessarily. Extensions add capabilities but introduce upgrade lifecycles, compatibility checks, and hosting environment restrictions.

## 21. Architecture Scenarios

**Scenario A — Small-Team E-Commerce App:** Customers, carts, orders, order items, payments; a few million records, needing transactions and SQL reports. **PostgreSQL is typically a very sensible choice.** Start with a relational schema, indexes, and backup/monitoring before adding other data stores.

**Scenario B — Behavioral Analytics Warehouse with Hundreds of Billions of Events:** Mostly scanning large datasets for aggregates, rare row-level updates, prioritizing columnar queries. **Evaluate a dedicated warehouse/OLAP engine**, potentially keeping PostgreSQL as the transactional source and streaming events to analytics.

**Scenario C — High-Concurrency Reservation System:** Must prevent double booking and commit multiple updates atomically. PostgreSQL fits well for transactions and constraints, provided locks, isolation, and retries are designed properly. No DBMS understands business invariants automatically if schemas or statements are flawed.

**Scenario D — Product Catalog with Variable Specs:** Core entities are relational tables, while specs vary by product category. PostgreSQL with `JSONB` can offer a clean hybrid model. If most queries involve advanced natural-language document search, consider a dedicated search engine.

**Scenario E — Offline-First Mobile App:** Needs an embedded database directly on the device. SQLite or local storage is typically better suited than a PostgreSQL server; PostgreSQL can still serve as the sync backend.

**Scenario F — Multi-Region Write-Distributed System:** Independent writers across regions, cross-region network partitions, tight latency budgets. **Do not assume single-primary PostgreSQL meets the requirement.** Evaluate distributed SQL, partitioning/sharding, and consistency–availability trade-offs.

## 22. Conclusion: Choose PostgreSQL When Its Core Strengths Match Your Needs

PostgreSQL is a strong choice when you need **a reliable relational data platform**, rich SQL, clear transactions, integrity constraints, and schema evolvability. `JSONB` and extensions broaden its reach without removing the need for careful data modeling or limit analysis.

Before deciding, obtain data-backed answers to five questions:

1. Are **data and business invariants** cleanly expressed and protected by PostgreSQL?
2. Do **critical queries and transactions** meet latency and throughput targets under projected load?
3. Are **growth and concurrency** handled through proven indexes, resources, partitioning/replicas, or architecture?
4. Do **backups, failover, and operations** satisfy RPO/RTO, staffing, and security standards?
5. Are **total cost and evolvability** more favorable than alternatives for this specific problem?

If a representative PoC validates all five answers, PostgreSQL is a highly dependable foundation for many business applications. If a hard criterion fails, adjust the architecture or choose a more fitting technology rather than forcing every data type and query workload into a single DBMS.
