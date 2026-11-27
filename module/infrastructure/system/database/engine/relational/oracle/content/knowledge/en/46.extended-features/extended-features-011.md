# Sharding, Shard Keys, and Transaction Routing

When a single database approaches its limits in CPU, I/O, storage, or vertical scalability, data can be horizontally split across multiple independent databases. Each database stores a subset of data and together they serve one application. This technique is called **sharding**. In Oracle, Oracle Sharding provides data distribution, topology management, and connection routing based on a shard key.

The most important concept when designing sharding is the **shard key**: one or more columns determining which shard holds a row of data. The application supplies the shard key when opening a connection or issuing a request via a supported mechanism so the Shard Director or connection pool routes to the right shard. When all operations in a transaction fall within the same shard, the transaction can execute as a local transaction. If a transaction touches multiple shards, the system must coordinate across databases and typically requires a distributed transaction with two-phase commit, increasing latency and complexity.

Sharding is therefore not merely splitting a table into parts. It is an architectural decision affecting data keys, API design, transaction boundaries, queries, security, operations, and scalability. A good shard key routes most requests to a single shard; a poor shard key can create hot shards, force many queries to fan out, or force transactions to span multiple databases frequently.

## 1. What Is Sharding?

Sharding partitions data into subsets according to a deterministic rule and stores each subset in a separate database called a **shard**. Together the shards form one logical sharded database, yet each shard is an independent Oracle Database in terms of storage and processing.

Consider an e-commerce system with 100 million customers. Instead of storing all customers and orders in one database, data can be distributed by `CUSTOMER_ID`:

```text
                     Application
                        |
                        v
                Shard Director (GSM)
                        |
          +-------------+-------------+
          |             |             |
          v             v             v
      Shard 1        Shard 2        Shard 3
    Customer A-H   Customer I-P   Customer Q-Z
    Orders ...     Orders ...     Orders ...
```

The diagram only illustrates splitting by customer range. In Oracle Sharding, actual distribution depends on the sharding method, shard key, chunk map, and topology configuration.

### 1.1. Shards Are Independent Databases

Each shard can have its own:

- Database instance and Oracle processes.
- Datafiles, control files, redo logs, and undo.
- Schemas, tables, indexes, and data for its shard portion.
- Users, privileges, services, and operational settings.
- Backup, recovery, and HA strategy.

Shards do not share a single set of datafiles concurrently accessed like instances in Oracle RAC. This is a *shared-nothing* model at the shard level: each shard owns its data and coordinates with other shards over the network, Shard Catalog, Shard Director, and supported replication/transaction mechanisms.

### 1.2. Goals of Sharding

Sharding is commonly considered when you need to:

- Scale capacity beyond the practical limits of a single database.
- Distribute CPU, I/O, and workloads across multiple database servers.
- Isolate load by tenant, customer, region, or business group.
- Place data closer to user regions to meet latency or regulatory requirements.
- Scale out by adding shards instead of only scaling up one server.
- Limit blast radius of failures or maintenance to part of the topology, if applications and HA are designed properly.

Sharding does not automatically make every query faster. It distributes load when requests can route to one shard or a small group of shards. Queries scanning all data may have to run across multiple shards and aggregate results, increasing network traffic and processing time.

## 2. Distinguishing Sharding from Partitioning, RAC, and Data Guard

These technologies all relate to scaling or protecting databases, yet solve different problems.

| Technology | Where Is It Split? | Primary Goal | Characteristics |
|---|---|---|---|
| Table partitioning | Inside one database | Manage large tables, partition pruning, data lifecycle | Partitions remain inside the same database |
| Oracle RAC | Multiple instances accessing one database | High availability and scale-out for one database | Instances share database storage and coordinate caches/locks |
| Oracle Sharding | Multiple independent databases | Horizontal scale-out of data and workload | Each shard stores a subset of data per shard key |
| Oracle Data Guard | Primary and standby databases | Disaster recovery and data protection | Standby maintains a redo replica of primary |
| Oracle GoldenGate | Across databases/systems | Logical replication and CDC | Captures, transports, and applies logical changes |

Sharding can be combined with table partitioning inside each shard. Each shard can also have its own HA strategy; specific configurations may use Data Guard or methods supported by Oracle for the deployed release. RAC and sharding are not two names for the same architecture: RAC scales one database across multiple instances, whereas sharding splits data across multiple databases.

## 3. Components of Oracle Sharding

Oracle Sharding adds a topology management and routing layer so applications do not have to maintain shard lists and data distribution algorithms manually.

### 3.1. Sharded Database

A sharded database is the entire logical system comprising shards, metadata, routing services, and management components. Each shard holds a subset of sharded tables. Small shared tables can be configured as duplicated tables so each shard holds a copy.

### 3.2. Shard Catalog

The Shard Catalog is a database storing administrative metadata for the sharded database, such as:

- Topology and shard details.
- Sharding method and shard key definitions.
- Mapping between shard keys/chunks and shards.
- Configuration details for managing and orchestrating shards.

The Shard Catalog does not hold all business data of the application. Customer and order data reside in shards per distribution rules. The catalog serves as the metadata source so management tools and components understand the topology.

### 3.3. Shard Director / Global Service Manager

The Shard Director, typically deployed using Global Service Manager (GSM), routes connections and provides global services. Clients connect through the Shard Director and supply the shard key via supported mechanisms. It uses the shard map to route connections to the appropriate shard.

The Shard Director also participates in managing services, topology, and shard health. In production, deploy multiple Shard Directors or appropriate redundancy so the routing tier does not become a single point of failure.

### 3.4. Global Services

Global services provide logical connection endpoints for applications. Services can be configured by workload, role, region, or access purpose. The Shard Director uses service info and the shard key to select where to serve requests per configuration.

Service names and connection settings must be aligned between DBAs and application teams. Applications should use published service names instead of hardcoding SIDs or connecting directly to a specific instance.

### 3.5. Chunks and Shard Map

In system-managed sharding, data is divided into logical chunks by shard key. A chunk is the unit of data management/distribution and maps to a shard. The shard map represents how shard key values or chunks are allocated.

When adding shards or rebalancing capacity, Oracle can move chunks via supported mechanisms. This lets DBAs adjust data distribution without applications computing the physical location of every customer.

### 3.6. Shard Groups and Shardspaces

In advanced topologies, shards can be organized into shard groups and shardspaces to represent storage groups, data scopes, or replication/HA layouts. Exact meanings of each component depend on the sharding method and deployment architecture. When designing, use the topology model of your exact Oracle Database release rather than assuming shard groups are like clusters or RAC groups.

## 4. What Is a Shard Key?

A shard key is one or more columns used to determine which shard stores a row of data. When the application knows a request's shard key, the system can route directly to the shard owning that data.

Example customer table:

```sql
CREATE TABLE customers (
    customer_id   NUMBER(12) NOT NULL,
    customer_name VARCHAR2(200) NOT NULL,
    email         VARCHAR2(320),
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL
);
```

If `CUSTOMER_ID` is the shard key, all rows sharing the same `CUSTOMER_ID` route to the corresponding shard. Customer-dependent business tables such as `ORDERS`, `ADDRESSES`, and `PAYMENTS` can be designed to distribute by the same customer key so operations for a single customer mostly occur within one shard.

### 4.1. Simple Shard Keys and Composite Shard Keys

A simple shard key consists of one column, e.g. `CUSTOMER_ID`.

A composite shard key consists of multiple columns, e.g.:

```text
(TENANT_ID, CUSTOMER_ID)
```

Composite keys are useful when an ID is unique only within a tenant. For instance, two tenants can both have `CUSTOMER_ID = 1001`, while the pair `(TENANT_ID, CUSTOMER_ID)` forms the complete distribution identifier.

When using a composite shard key, all clients and related tables must agree on key component order. Missing part of a shard key can prevent routing from identifying a single shard and force a broader execution path.

### 4.2. Shard Key vs. Primary Key

A primary key uniquely identifies a row within the scope enforced by its constraint. A shard key determines where that row is stored. The two concepts can overlap but do not have to be identical.

Example:

```text
Shard key:   CUSTOMER_ID
Primary key: (CUSTOMER_ID, ORDER_ID)
```

An order is uniquely identified per customer, and `CUSTOMER_ID` is also used for routing. For sharded tables, follow Oracle's primary key/unique constraint restrictions; typically local unique keys must include the shard key columns so the database can enforce uniqueness without checking every shard.

If an application needs `ORDER_ID` to be globally unique without containing the shard key, design globally unique IDs or an appropriate identification mechanism. Never assume a local unique constraint per shard guarantees uniqueness across the entire sharded database.

### 4.3. Criteria for Choosing a Shard Key

A good shard key should satisfy these criteria:

1. **Balanced distribution:** data and workload do not pile onto a few shards.
2. **Present in requests:** the application usually knows the key before querying or updating.
3. **Stable:** rarely changes during the record's lifecycle.
4. **Preserves locality:** tables frequently queried together can co-locate.
5. **Sufficient cardinality:** enough distinct values to distribute data.
6. **Avoids hotspots:** does not create an overly popular or monotonically increasing key concentrating load.
7. **Meets regulations:** if data must stay in a specific region/tenant, the key and mapping can express that.

There is no good shard key based on cardinality alone. A column with millions of values where most requests hit one huge tenant can still create a hot shard. Evaluate both data distribution and request distribution.

## 5. Sharding Methods in Oracle

Oracle Sharding supports different distribution methods. Your choice affects locality, load balance, and manageability.

### 5.1. System-Managed Sharding

System-managed sharding typically uses consistent hashing on the shard key. Oracle manages splitting into chunks and distributing chunks across shards. DBAs do not need to map individual key values to shards manually.

Illustrative DDL example for a sharded table:

```sql
CREATE SHARDED TABLE customers (
    customer_id   NUMBER(12) NOT NULL,
    customer_name VARCHAR2(200) NOT NULL,
    email         VARCHAR2(320),
    CONSTRAINT customers_pk PRIMARY KEY (customer_id)
)
PARTITION BY CONSISTENT HASH (customer_id)
PARTITIONS AUTO
TABLESPACE SET ts_customers;
```

This is a conceptual example; exact syntax and tablespace sets must match the deployed version, shard catalog, and topology. Consistent hashing distributes keys relatively evenly and supports moving chunks when topology changes.

Advantages:

- Reduces manual range/list mapping work.
- Supports balanced hash-based data distribution.
- Easy to add shards and rebalance via chunk movement.
- Fits key-based access workloads that do not require range locality.

Limitations:

- Key-range queries may need to hit multiple shards.
- DBAs have less direct control over which shard holds a specific range.
- Hot keys can still create hotspots even if hashing spreads other keys evenly.

### 5.2. User-Defined Sharding

User-defined sharding lets DBAs control mapping data to shards by range or list value. For example, data is split by geographic region, organization code, or tenant group.

Conceptual design example:

```text
REGION = NORTH   -> Shard group North
REGION = CENTRAL -> Shard group Central
REGION = SOUTH   -> Shard group South
```

Advantages:

- Explicit control over which shard holds which data.
- Can place data close to users or within required jurisdictions.
- Can tune workloads per region/tenant.

Limitations:

- DBAs must manage mappings and capacity per region.
- Skew occurs if one region grows much larger than others.
- Adding regions or changing mappings may require explicit data migration procedures.

User-defined sharding fits when data boundaries have clear business meaning and remain relatively stable. Do not pick ranges just because they are easy to understand if one range can outgrow others rapidly.

### 5.3. Composite Sharding

Composite sharding combines two distribution levels, such as range/list at the top level and hashing at the second level. This preserves locality along one business dimension while spreading data within each group to reduce hotspots.

Conceptual example:

```text
REGION
  +-- NORTH   -> hash CUSTOMER_ID -> multiple shards/chunks
  +-- CENTRAL -> hash CUSTOMER_ID -> multiple shards/chunks
  +-- SOUTH   -> hash CUSTOMER_ID -> multiple shards/chunks
```

Composite sharding helps when a large business key must be subdivided further, or when data must be organized by region while still balancing load within each region. Understand which partitioning/sharding combinations your Oracle release supports and how the shard map represents both levels.

### 5.4. Comparing Methods

| Criterion | System-Managed Hash | User-Defined Range/List | Composite |
|---|---|---|---|
| Mapping | Oracle manages via hash/chunks | DBA defines mappings | Combines multiple levels |
| Data balance | Usually favorable with well-distributed keys | Depends on mapping and group sizes | Balances within each group |
| Range/region locality | More limited | Good if mapping matches | Preserves locality while spreading further |
| Operations | More automated | Requires maintaining mappings | More complex |
| Risks | Hot keys/hot shards | Skewed ranges/lists | Complex key and mapping design |

## 6. Co-Location and Table Families

One of the greatest benefits of sharding is keeping data frequently accessed together on the same shard. This concept is called **co-location**.

For example, a request displaying a customer's orders typically needs:

- Customer details.
- Customer's orders.
- Order items.
- Shipping addresses.

If these tables share `CUSTOMER_ID` as the shard key and are defined in the same table family, related data can reside on the same shard. Joins and transactions then typically need only one database.

### 6.1. Parent-Child Tables Sharing a Shard Key

Model:

```text
CUSTOMERS
  shard key: CUSTOMER_ID
       |
       +------ ORDERS
       |        shard key: CUSTOMER_ID
       |            |
       |            +---- ORDER_ITEMS
       |                   shard key: CUSTOMER_ID
       |
       +------ ADDRESSES
                shard key: CUSTOMER_ID
```

Tables sharing the same shard key and distribution rules allow a customer and all dependent data to route to one shard.

### 6.2. Table Families

A table family describes a group of sharded tables with parent-child relationships co-located by shard key. The top table is the root table; dependent tables use the same shard key and appropriate foreign key relationships.

This design enables:

- Local joins inside a single shard.
- Local referential integrity enforcement where supported.
- Executing business transactions inside one shard.
- Reducing requests that must fan out or use distributed transactions.

### 6.3. Foreign Keys in a Sharded Database

Do not assume a foreign key on a sharded table can arbitrarily reference rows in another shard as in a single database. To enforce referential integrity efficiently, parent/child tables usually must be co-located and foreign keys must align with the shard key/table family.

If a business relationship must reference across shards, design validation at the application/service layer or reconsider the data model. Verify foreign key and table family restrictions for your exact Oracle version.

### 6.4. Duplicated Tables for Reference Data

Small, rarely changing tables used by many shards can be deployed as duplicated tables so each shard holds a local copy. Examples:

- Country catalogs.
- Currency codes.
- Shared status tables.
- Small reference configuration tables.

Duplicated tables avoid querying remote shards just to fetch a lookup value. When data changes, Oracle Sharding's replication mechanism maintains the copies per configuration. Weigh sync costs and change frequency; large or rapidly changing tables are usually unsuitable.

## 7. Designing Shard Keys Around Access Patterns

Shard keys must be chosen based on how the application accesses data, not solely on table structure.

### 7.1. Requests Usually Have Customer ID

If most requests start from a customer, `CUSTOMER_ID` is a strong candidate:

```sql
SELECT order_id, order_date, order_status
FROM orders
WHERE customer_id = :customer_id
ORDER BY order_date DESC;
```

When the application provides `CUSTOMER_ID`, the Shard Director can route to the shard holding that customer. The query does not need to scan all shards.

### 7.2. Requests Only Have Order ID

If an API only receives `ORDER_ID` while the shard key is `CUSTOMER_ID`, the system cannot infer the shard from order ID without extra mapping. Options:

- Include customer ID in the request or token for routing.
- Encode shard info inside IDs using a managed convention.
- Maintain a lookup service/global index mapping order ID to shard key.
- Accept cross-shard queries if frequency is low and cost is acceptable.

This is a critical API design decision. If the application frequently looks up by a key other than the shard key, re-evaluate the design before deploying sharding.

### 7.3. Hot Keys and Skew

A high-cardinality shard key can still cause load skew. For example, `TENANT_ID` distributes across thousands of tenants, yet one giant tenant generates 70% of requests. If all data for that tenant lives on one shard, that shard becomes a hot shard.

Potential remedies include:

- Splitting huge tenants into sub-tenants or buckets.
- Using a composite shard key like `(TENANT_ID, BUCKET_ID)` if business logic permits.
- Isolating large workloads into dedicated shardspaces or models.
- Caching read-heavy data.
- Using read replicas/replication architectures suited to read-heavy workloads.

Every approach that subdivides a tenant adds complexity when tenant-wide transactions or aggregate queries are needed. Balance locality against load distribution.

### 7.4. Monotonic Keys

Using a continuously increasing value like a timestamp or global sequence as a range shard key can pile new records onto the last range and create a hot shard. Hash-based sharding usually spreads keys out, yet time-range queries may need to hit multiple shards.

There is no rule that sequences are always bad shard keys; what matters is distribution and access patterns. Measure insert rates, requests per key, and per-shard utilization.

### 7.5. Should a Shard Key Change?

A shard key should remain stable over a record's lifetime. Changing a shard key may require moving data to another shard along with parent-child relationships, caches, transactions, and routing. Direct shard key updatability depends on sharding type and version; do not assume it behaves like an ordinary UPDATE.

If business workflows frequently reassign tenants or regions, design controlled data migration procedures or pick a more stable key to avoid frequent row movement.

## 8. Creating Sharded Tables and Duplicated Tables

Exact DDL depends on Oracle Database release, sharding method, shard catalog, and tablespace sets. The following example illustrates system-managed consistent hashing:

```sql
CREATE SHARDED TABLE customers (
    customer_id   NUMBER(12) NOT NULL,
    customer_name VARCHAR2(200) NOT NULL,
    created_at    TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT customers_pk PRIMARY KEY (customer_id)
)
PARTITION BY CONSISTENT HASH (customer_id)
PARTITIONS AUTO
TABLESPACE SET ts_customers;
```

Table `ORDERS` in the same table family can share the shard key and link to its parent per Oracle Sharding rules. Logical example:

```sql
CREATE SHARDED TABLE orders (
    customer_id  NUMBER(12) NOT NULL,
    order_id     NUMBER(12) NOT NULL,
    order_date   TIMESTAMP NOT NULL,
    order_status VARCHAR2(20) NOT NULL,
    CONSTRAINT orders_pk PRIMARY KEY (customer_id, order_id),
    CONSTRAINT orders_customer_fk
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
)
PARTITION BY REFERENCE (orders_customer_fk);
```

The second snippet illustrates reference partitioning within a table family; verify exact syntax and applicability for your Oracle Sharding release, sharding type, and root table declaration. Never copy both DDL snippets directly as a complete bootstrap script before creating the topology, tablespace sets, and table family configuration.

### 8.1. Primary Keys and Unique Constraints

For sharded tables, unique constraints must be designed so Oracle can enforce uniqueness within the distributed scope. Typically the shard key must appear in the primary key or unique key of a sharded table. If you need a globally unique code across the sharded database without embedding the shard key, generate globally unique IDs or use an appropriate uniqueness control mechanism.

### 8.2. Indexes Within Each Shard

Indexes on sharded tables are created and managed per object definitions across shards. Local indexes accelerate local queries by shard key and other predicates. Inspect execution plans, cardinality, and workloads on real shards; an index that helps on a single database may not solve scatter-gather queries.

### 8.3. Duplicated Tables

Duplicated tables hold copies of reference data across shards. DDL for duplicated tables differs from `CREATE SHARDED TABLE`; use syntax supported by Oracle Sharding for your release and manage changes through the shard catalog. Never manually create a same-named table on each shard and treat it as a duplicated table, as Oracle will lack the corresponding replication metadata.

## 9. Routing Connections Using Shard Keys

Routing determines which shard serves a request. In Oracle Sharding, the client or connection pool must supply the shard key via supported APIs/drivers.

### 9.1. Routing via Shard Director

General flow:

1. The application opens a connection to a global service via Shard Director.
2. The application supplies the shard key.
3. Shard Director looks up the shard map.
4. The connection is routed to the matching shard.
5. Subsequent SQL on that connection executes on that shard.

When clients omit or provide an incomplete shard key, the system may fall back to non-targeted routing or cross-shard paths depending on API and configuration. Having a shard key predicate in SQL is not always equivalent to supplying the shard key when acquiring a connection; routing behavior depends on how the client/driver and service are configured.

### 9.2. Proxy Routing vs. Direct Routing

**Proxy routing**: clients connect through the Shard Director, which receives the shard key and forwards the connection to the shard. This model is easy to reason about and suits scenarios requiring a centralized routing layer.

**Direct routing**: clients or shard-aware connection pools use the shard map to connect directly to the shard after resolving the key. This eliminates an extra router hop and reduces load on the routing tier, yet clients/pools must manage topology and routing properly.

Proxy/direct routing capabilities and configuration depend on the Oracle client, JDBC driver, UCP, and release. Check documentation for your exact version instead of assuming all drivers support identical APIs.

### 9.3. Sharding API in JDBC

JDBC 4.3 defines APIs for sharding keys and connection builders. Drivers must support those APIs. Conceptual example:

```java
ShardingKey shardingKey = dataSource.createShardingKeyBuilder()
        .subkey(customerId, JDBCType.NUMERIC)
        .build();

Connection connection = dataSource.createConnectionBuilder()
        .shardingKey(shardingKey)
        .build();
```

This snippet illustrates standard JDBC; your Oracle JDBC/UCP version and DataSource configuration must support the corresponding sharding APIs. For composite shard keys, the builder may need multiple subkeys in the exact order and data types defined in the shard catalog.

In Spring applications, connection pools must track shard affinity when lending connections. Never borrow a connection routed to shard A and reuse it for a shard B request without using supported switching/routing mechanisms.

### 9.4. Shard-Aware Connection Pools

Traditional connection pools reuse connections by database/service. In a sharded database, the pool must understand shard keys to hand out connections to the right shard or manage per-shard pools. Oracle Universal Connection Pool (UCP) integrates with Oracle Sharding in supported releases.

A shard-aware pool helps:

- Reduce the cost of opening new connections.
- Reuse connections on the right shard.
- Route by shard key.
- Support affinity and topology management per driver/pool capabilities.

Pools must bound total connections across all shards. If an application runs many instances and each keeps large pools for every shard, connection counts can multiply by application instances × shards × pool size. Perform capacity planning and control idle connections.

### 9.5. Have the Shard Key Before Acquiring a Connection

If the API knows `CUSTOMER_ID` upfront, pass the key before acquiring a connection. If the shard key is only discovered after querying another table, the initial step may need a lookup service or another route.

API designs should pass shard keys via path, request context, or authenticated tokens when appropriate. Never trust an arbitrary client-supplied shard key if it impacts tenant isolation; the server must validate the key against request identity/authorization.

## 10. Transaction Routing

Once a connection is routed to a shard, statements on that connection typically execute on the chosen shard. A local transaction can update multiple co-located tables and commit like a normal Oracle transaction.

### 10.1. Single-Shard Transactions

Example request updating a customer and creating an order:

```sql
UPDATE customers
SET customer_name = :name
WHERE customer_id = :customer_id;

INSERT INTO orders(customer_id, order_id, order_date, order_status)
VALUES (:customer_id, :order_id, SYSTIMESTAMP, 'NEW');

COMMIT;
```

If both tables are co-located by `CUSTOMER_ID` and the connection was routed using the customer key, all operations occur on one shard. The transaction can use a local commit, avoiding cross-network coordination and keeping familiar Oracle semantics.

### 10.2. Multi-Shard Transactions

If a transaction must update data on two shards—for example, transferring inventory between warehouses on different shards—the system must coordinate the transaction across multiple databases.

Oracle Sharding can support multi-shard transactions using distributed transaction mechanisms. To ensure atomicity, systems typically use two-phase commit (2PC):

1. **Prepare phase:** the coordinator asks participants to prepare to commit and record required state.
2. **Commit phase:** once all participants are ready, the coordinator directs them to commit; if failures occur per protocol, the transaction follows distributed transaction recovery rules.

2PC preserves atomicity yet adds round-trips, resource lock duration, and recovery complexity. If the network or a participant fails during commit, in-doubt transactions may require recovery.

### 10.3. Costs of Multi-Shard Transactions

Multi-shard transactions can increase:

- Network latency between coordinator and shards.
- Open transaction duration.
- Lock duration on participants.
- Recovery/metadata management overhead.
- Likelihood of distributed transaction failures or in-doubt states.
- Retry complexity when commit outcomes are momentarily uncertain at the client.

Accordingly, sharding architectures strive to keep frequent operations of a business transaction inside a single shard. Reserve multi-shard transactions for cases genuinely requiring cross-shard atomicity.

### 10.4. When to Use Sagas or Eventual Consistency?

Not every cross-shard business flow requires 2PC. Workflows can be broken into local steps using sagas/outboxes and compensation when business rules permit.

Example transferring inventory between regions:

1. Create a transfer request on the source shard.
2. Reserve or deduct inventory on the source shard in a local transaction.
3. Emit a transfer event.
4. Destination shard consumes the event and adds inventory in a local transaction.
5. If a later step fails, execute compensation or move the request to a manual-handling state.

Sagas do not provide immediate atomic commits like 2PC. They provide workflow-level consistency and compensation. Choose 2PC vs. sagas based on business requirements, latency, failure models, and tolerance for intermediate states.

## 11. Single-Shard Queries vs. Multi-Shard Queries

### 11.1. Shard-Key Lookups

Queries supplying the full shard key typically route directly to the shard owning the data:

```sql
SELECT order_id,
       order_date,
       order_status
FROM orders
WHERE customer_id = :customer_id
  AND order_id = :order_id;
```

If the connection was opened with shard key `CUSTOMER_ID`, the query runs locally. This is the pattern to optimize for OLTP.

### 11.2. Queries Without a Shard Key

Example:

```sql
SELECT COUNT(*)
FROM orders
WHERE order_status = 'NEW';
```

The predicate lacks the shard key. The system cannot pinpoint a single shard from this condition alone. Depending on services and APIs, the query may need to run across multiple shards and aggregate, or be dispatched through a multi-shard query mechanism.

Fan-out queries incur network, CPU, and latency costs scaling with shard count. As shard count grows, coordination and aggregation overhead rises.

### 11.3. Cross-Shard Joins

Joins between two tables co-located by the same shard key usually execute locally on the shard. Joins between non-co-located tables may require shipping data across the network or complex distributed queries.

For example, joining orders with customers on `CUSTOMER_ID` works cleanly when both belong to the same table family. Joining orders with a global transaction table distributed by `TRANSACTION_ID` can turn into a cross-shard join.

### 11.4. System-Wide Aggregations

Reports such as total revenue across all shards usually aggregate on each shard and then combine results. Verify correctness of aggregations, filters, timezones, and data timestamps across shards.

For heavy reporting, consider a data warehouse, materialized/reporting layer, or CDC pipeline instead of running fan-out OLTP queries across every shard.

## 12. Tenant-Based Routing and Security

A common pattern is sharding by `TENANT_ID`. Each tenant's data resides on one shard or a key-distributed group. This improves locality and can support data residency requirements.

### 12.1. Validating the Shard Key

A shard key is routing metadata, not an authorization mechanism. If a client sends another tenant's `TENANT_ID`, routing to the right shard does not prevent unauthorized access.

Applications must:

- Derive tenant identity from an authenticated token/session.
- Verify the user has permission to access that tenant.
- Never trust `TENANT_ID` from query parameters without verification.
- Include the tenant key in all necessary queries.
- Protect connection contexts so connections are never reused across tenants improperly.

### 12.2. Tenant Isolation

Sharding by tenant does not automatically guarantee security isolation of tenant data. Combine schema privileges, application authorization, auditing, and query predicate checks. When multiple tenants share a shard, still enforce tenant filters in the application or appropriate database security policies.

### 12.3. Data Residency

User-defined sharding can map tenants/regions to shard groups in desired regions. However, check replicas, backups, archive logs, monitoring, and duplicated tables as well. Data stays compliant only when the entire pipeline and HA topology honor residency rules.

## 13. Topology Changes and Rebalancing Data

As tenant counts, storage, or traffic grow, DBAs may need to add shards or move chunks to rebalance.

### 13.1. Adding a Shard

General workflow:

1. Provision new servers/storage and database.
2. Configure the shard per topology, services, and replication/HA policies.
3. Register the shard with the Shard Catalog using management tools.
4. Confirm shard readiness and active services.
5. Run rebalancing/chunk movement per policy.
6. Monitor data, lag, throughput, and chunk transfer status.

Adding a database to the topology does not automatically redistribute existing data instantaneously. Understand the chunk movement mechanics and rebalance statuses of your Oracle release.

### 13.2. Chunk Movement

Chunks are the unit of data distribution in system-managed sharding. During rebalancing, Oracle can move chunks from source shards to target shards and update the shard map. The goal is balancing capacity/workload without forcing applications to write row-by-row migration logic.

During movement, monitor:

- Chunk movement progress.
- Temporary space and network traffic.
- Impact on request latency.
- Availability of source/target shards.
- Shard map and routing status after completion.

### 13.3. Hot Shards Are Not Caused Only by Data Volume

A shard can hold little data yet still run hot because traffic concentrates on one tenant or key. Rebalancing by storage size does not always resolve hot keys. Inspect CPU, I/O, sessions, request rates, top SQL, and key distribution metrics.

If a single tenant exceeds a shard's capacity, you may need sub-sharding, caching, workload isolation, or data model changes. Moving the entire tenant to another shard only helps if the target shard has headroom and the key stops concentrating further.

## 14. High Availability and Backups per Shard

Because shards are independent databases, each shard needs its own backup, recovery, monitoring, and HA strategy. Do not assume backing up the Shard Catalog replaces backing up shard data.

### 14.1. Data Guard per Shard

An architecture can deploy standbys for each shard using Data Guard per Oracle-supported models. When a primary shard fails, its standby can take over per runbook. The Shard Catalog and Shard Director also require their own HA.

### 14.2. Distinguishing Shard Failures from Router Failures

Layers can fail independently:

- A shard database becomes unavailable.
- Shard Director/GSM becomes unavailable.
- Shard Catalog becomes unavailable.
- Network between application and shard drops.
- Replication/standby lag or incomplete failover.

Monitoring must distinguish these layers to avoid misdiagnosis. If the router fails while shards are healthy, restoring routing is top priority. If a shard fails, handle that shard's database/standby.

### 14.3. Backup and Restore

Backup policies must cover every shard, catalog, and metadata needed to rebuild the topology. Restoring one shard to a different point in time than other shards can cause cross-shard inconsistency if business workflows include multi-shard transactions.

DR runbooks must document how to recover shards, synchronize catalog/routing, verify the shard map, and reconcile data. Test restores periodically instead of merely checking that backup jobs report success.

## 15. Administering Oracle Sharding

Oracle provides the `GDSCTL` utility to manage Shard Directors, shards, services, and topologies. Exact commands vary by release and deployment mode.

General inspection examples:

```text
GDSCTL> config shard
GDSCTL> status
GDSCTL> config gsm
```

These commands illustrate viewing shard configuration, topology status, and Global Service Manager state. When running in practice, check help and documentation for your exact version to confirm syntax, privileges, and options.

### 15.1. Shard Catalog Views

The Shard Catalog provides data dictionary views for inspecting sharding metadata. Views can include shard details, shard groups, sharding keys, sharding methods, and mappings. Exact view/column names depend on release and privileges; DBAs can check `DBA_SHARDS`, `DBA_SHARDING_KEYS`, and related views in their version's data dictionary.

Do not hardcode administrative queries based on column names from a different version. Before writing automation, check `DESC` or the data dictionary reference in your actual environment.

### 15.2. Per-Shard Monitoring

Track at minimum:

- CPU, memory, I/O, and storage per shard.
- Session counts and connection pool utilization.
- Throughput, latency, and error rates per shard.
- Top SQL and execution plans.
- Transaction duration, lock waits, and deadlocks.
- Tablespace growth and archive log generation.
- Replication/standby lag if HA is configured.
- Chunk movement/rebalance progress.
- Shard Director/GSM availability and routing errors.

Aggregate metrics can hide skew. One shard can hit 95% CPU while the cluster average sits at 35%. Dashboards should show per-shard breakdowns, not just a single average.

## 16. Designing Spring/Java Applications for Sharded Databases

Applications must carry the shard key end-to-end through requests, from API to repositories and connection acquisition.

### 16.1. Putting the Shard Key in Application Context

Example request:

```text
GET /tenants/42/customers/1001/orders
```

The server authenticates tenant 42, verifies customer 1001 belongs to that tenant, and builds a routing context:

```java
public record TenantContext(long tenantId) {}
```

Repositories/services receive the tenant key explicitly or read the validated context. Avoid uncleaned ThreadLocals in thread pools, which can leak tenant context across requests.

### 16.2. Selecting the Shard Before Opening a Transaction

Transactions must start after the shard key is determined and the connection is routed properly. If a Spring transaction opens a connection first and sets the shard key later, the connection may stay bound to the initial shard.

Routing DataSource/connection pool design must coordinate with the transaction manager. Write integration tests confirming every repository within the same transaction hits the right shard and never accidentally grabs a connection from a different pool.

### 16.3. Do Not Route Arbitrarily with Plain ThreadLocal

A custom `AbstractRoutingDataSource` can pick a DataSource by context, yet hand-rolling a router does not turn multiple Oracle databases into Oracle Sharding. It only picks a DataSource via application logic. When using Oracle Sharding, use the Shard Director, shard-aware drivers/pools, and Oracle-supported mechanisms synchronized with the shard map.

Managing custom routing outside Oracle Sharding forces the application to handle topology changes, failovers, data movement, connection pools, stale mappings, and transaction boundaries itself—a major operational burden.

### 16.4. Transaction Propagation

In Spring, `@Transactional` manages transactions on the connection acquired by the transaction manager. If a service calls a repository with a different shard key inside the same transaction, do not assume Spring automatically switches the transaction to another shard. An acquired connection typically remains tied to one database.

For multi-shard transactions, use supported distributed transaction capabilities and configure the transaction manager accordingly; do not simply call two DataSources inside one method and expect an atomic commit.

## 17. Global IDs and Sequences in Sharding

If each shard has its own sequence starting from the same value, two shards can generate identical IDs. That does not necessarily violate local uniqueness, yet causes collisions when data is aggregated or moved.

Common strategies:

- **Composite key:** `(SHARD_KEY, LOCAL_ID)` as the unique key.
- **UUID/GUID:** distributed ID generation with extremely low collision probability, trading off size/index footprint.
- **Shard prefix:** embedding a shard identifier into IDs under a system-wide convention.
- **Scalable sequences:** using sequence features of your Oracle version when requirements allow.
- **Central ID service:** issues global IDs, though it can introduce a dependency/throughput bottleneck.

Never assume Oracle sequences are gapless or globally coordinated across shards. Sequences can cache and produce gaps on rollback or restart. If using shard prefixes, manage topology changes carefully and avoid reusing prefixes.

## 18. Common Design Mistakes

### 18.1. Picking a Shard Key Absent from APIs

The application must look up the shard key before querying, adding round-trips or forcing fan-outs. Verify whether critical APIs know the shard key upfront.

### 18.2. Picking a Heavily Skewed Key

One large tenant or region creates a hot shard. Analyze workload percentiles, not just total distinct keys.

### 18.3. Related Tables Not Co-Located

Creating an order must update inventory on another shard. This turns a simple OLTP transaction into a multi-shard transaction. Define aggregate boundaries and locality before choosing the key.

### 18.4. Using Fan-Out Queries for OLTP APIs

Every request queries all shards and aggregates. As shard count grows, latency and network traffic climb. If queries frequently need global lookups, consider duplicated/reference tables, global indexes/services, or a data warehouse.

### 18.5. Ignoring Connection Pool Overhead

Each application instance maintaining pools across many shards can create thousands of connections. Do holistic capacity planning and monitor idle/active connections.

### 18.6. Treating the Shard Key as a Security Boundary

Routing to the right shard does not replace authorization. Always authenticate tenants/users and enforce data permissions.

### 18.7. Failing to Test Topology Changes

Adding shards, moving chunks, or failing over can alter routing/caches. Test applications during live topology changes and confirm connection pools handle stale routing in supported ways.

## 19. Sharding Design Workflow

A design workflow can follow these steps:

1. **Measure current workload:** capacity, throughput, latency, CPU, I/O, hot SQL, and growth rate.
2. **Identify business aggregates:** which data must be read/written in the same transaction?
3. **List access patterns:** do APIs look up by customer, tenant, order, or time?
4. **Propose shard keys:** evaluate cardinality, skew, stability, and locality.
5. **Choose sharding method:** system-managed hash, user-defined range/list, or composite.
6. **Design table families:** co-locate parent-child tables and identify duplicated/reference tables.
7. **Design global IDs:** guarantee uniqueness and data mobility.
8. **Design routing:** Shard Director, global services, JDBC/UCP, and connection pools.
9. **Classify transactions:** single-shard, multi-shard 2PC, or saga/eventual consistency.
10. **Design queries:** targeted queries, cross-shard queries, reporting, and global lookups.
11. **Design HA/DR:** backups, Data Guard/replication, catalog, and director availability.
12. **Test:** skew, hot keys, fan-out, latency, failover, rebalance, and transaction recovery.
13. **Operate:** per-shard metrics, capacity, chunk movement, backups, and runbooks.

## 20. Hands-On Design Exercise: Sharding a Multi-Tenant System

Suppose a SaaS application serves many tenants. Each tenant has customers, orders, order details, and addresses. Most APIs receive `TENANT_ID` in the access token.

### Step 1: Identify Aggregates

The following data is commonly accessed together:

```text
TENANT
  +-- CUSTOMERS
  |     +-- ADDRESSES
  |     +-- ORDERS
  |            +-- ORDER_ITEMS
  +-- TENANT_SETTINGS
```

### Step 2: Choose the Shard Key

Propose `TENANT_ID` or composite `(TENANT_ID, CUSTOMER_ID)` depending on uniqueness and load distribution. If a single tenant has massive traffic, bucketing or sub-sharding may be needed; evaluate that against transaction requirements.

### Step 3: Choose the Sharding Method

If tenants are relatively evenly sized with no fixed region rules, system-managed consistent hashing is a strong candidate. If tenants must reside in specific regions, user-defined mappings or composite sharding may fit better.

### Step 4: Design Table Families

Give business tables the shared shard key so tenants and child data co-locate. Small, rarely changing lookup tables can be considered as duplicated tables.

### Step 5: Design API Routing

Access tokens identify the tenant. Middleware authenticates the tenant and passes the shard key down to connection acquisition. Repositories never guess shards from unmapped IDs.

### Step 6: Design Transactions

Creating orders and order items within the same tenant executes in one shard transaction. System-wide or tenant-wide revenue reports may require multi-shard queries or a reporting pipeline. Transferring resources between two tenants/shards requires choosing 2PC or sagas per business rules.

### Step 7: Test Distribution

Create small tenants, large tenants, and high-request-rate tenants. Measure:

- Tenant count and row count per shard.
- Request rate, CPU, and I/O per shard.
- Ratio of targeted queries vs. fan-out queries.
- Number of multi-shard transactions.
- p50/p95/p99 latency per shard.

If one shard runs hot, adjust keys/mappings or split workloads before mechanically adding more shards.

## 21. Pre-Production Checklist for Oracle Sharding

| Area | Question to Confirm |
|---|---|
| Business boundary | Which aggregates require local transactions and which data can tolerate eventual consistency? |
| Shard key | Do requests have the key upfront; is it stable and well-distributed? |
| Sharding method | Does hash, range/list, or composite match access patterns and residency? |
| Table family | Are parent-child tables co-located; do FKs meet Oracle restrictions? |
| Reference data | Which small tables should be duplicated; how are copies updated? |
| Global ID | Are IDs globally unique without depending on local sequences? |
| Routing | Do GSM/global services, JDBC driver/UCP, and pools support the chosen routing? |
| Security | Is the shard key validated; is tenant isolation enforced in app/database? |
| Transactions | Which transactions are single-shard; which use 2PC or sagas? |
| Queries | Are there excessive fan-outs, cross-shard joins, or global lookups? |
| Capacity | Are connection pools, CPU, I/O, storage, and per-shard growth sized? |
| HA/DR | Do every shard, Shard Catalog, and Shard Director have backups/standbys/runbooks? |
| Rebalance | Have adding shards, chunk movement, and topology refresh been tested? |
| Monitoring | Do dashboards show per-shard metrics and per-route latency? |
| Recovery | Have network failures, shard outages, in-doubt transactions, and restores been tested? |

Sharding pays off when the shard key accurately reflects how the application accesses data. Oracle Sharding provides the shard catalog, shard director, chunk map, and routing to direct requests to the database holding the data. When related tables are co-located, most transactions can execute within a single shard at lower cost. Cross-shard queries or transactions remain possible via supported mechanisms, yet typically incur network coordination and may need two-phase commit. Therefore, the single most critical decision is picking a stable, load-balanced shard key available upfront in requests that keeps each aggregate's data on the same shard—and then designing routing, transactions, HA, rebalancing, and monitoring around that choice.
