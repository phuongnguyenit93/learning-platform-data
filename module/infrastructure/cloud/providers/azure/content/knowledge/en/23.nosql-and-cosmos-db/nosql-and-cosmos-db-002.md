# Account, Database, Container, and Document Data Modeling

When starting an application with **Azure Cosmos DB**, especially **Azure Cosmos DB for NoSQL**, the first question should not merely be “how many tables do we need?”. You need to know **which documents the application reads and writes, by which keys, and at what rate**, before deciding how to structure the account, databases, containers, and items. Good document design can turn an order screen requiring multiple JOINs into a single **point read**, whereas a poorly chosen partition key or over-embedded documents can cause hot partitions, HTTP 429 throttling, write conflicts, and high RU costs.

This lesson belongs to the **NoSQL Data with Cosmos DB** chapter of the **CLOUD_PROVIDERS_AZURE** module. It is part of the journey through Microsoft Azure from subscriptions, resource groups, and Microsoft Entra ID to networking, compute, storage, and data. The goal is not just to provision resources, but to design, deploy, monitor, secure, and control the cost of application architectures on Azure.

The focus is **API for NoSQL** and **JSON document** data, structured as:

~~~text
Azure subscription
└── Resource group
    └── Cosmos DB account (API for NoSQL)
        ├── Database: commerce
        │   ├── Container: orders
        │   │   ├── Item: order-481
        │   │   └── Item: order-482
        │   ├── Container: customers
        │   └── Container: products
        └── Database: internal-tools
            └── Container: audit-events
~~~

> **Principle:** The account is the global service/configuration boundary; a database organizes containers and can optionally share throughput; a container defines the partition key and core data policies; and an item is a JSON document carrying an **id** field and a partition key value. Solid design starts from **access patterns, partition distribution, transaction boundaries, and Request Unit (RU) cost**.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **account**, **database**, **container**, **item**, **logical partition**, and **physical partition**.
2. Explain JSON documents, the **id** field, partition keys, nested objects, arrays, `schemaVersion`, and **_etag/_ts** metadata.
3. Compare Cosmos DB for NoSQL against relational tables, foreign keys, and JOINs.
4. Design data models from read/write scenarios: **embed**, **reference**, denormalization, snapshots, and materialized views.
5. Select a partition key based on cardinality, load distribution, queryability, immutability, and transaction scope.
6. Understand provisioned RU/s, autoscale, shared database throughput, and serverless.
7. Use the Azure CLI to create an account, database, and container in an approved lab, and inspect metadata and costs.
8. Use Java SDK v4 with Microsoft Entra credentials to create, point read, query, update, and delete items.
9. Apply ETag optimistic concurrency and transactional batches within the **same logical partition**.
10. Explain indexing, unique keys, TTL, Change Feed, and consistency levels.
11. Design data-plane RBAC security, networking, backup/DR, RU/429 monitoring, and migrations.
12. Evaluate an Orders–Customers–Inventory case study before going to production.

## 2. Mental Model: How Does Cosmos DB for NoSQL Differ from an RDBMS?

**Azure Cosmos DB** is a family of Azure-managed data services offering different supported APIs and models. In this lesson, **API for NoSQL** stores data as **JSON items** and queries them using a SQL-like language tailored to JSON—not Azure SQL Database's T-SQL.

| Criterion | Relational Database (e.g., Azure SQL) | Cosmos DB for NoSQL |
|---|---|---|
| Data unit | Table / row | Container / JSON item |
| Schema | Columns and constraints | Flexible JSON; the application must enforce the schema contract |
| Relationships | Foreign keys and JOINs | Embed/reference, intra-item queries; no arbitrary cross-container JOINs |
| Common optimal access | Indexed SQL queries | Point read using **id + partition key** |
| Partitioning | Available, though not every table requires choosing a key | Partition key is a core architectural decision |
| Atomic transactions | Database-wide via the transaction engine | Operations are typically atomic within **a single logical partition** |
| Capacity | vCore / DTU / IOPS... | RU/s, storage, regions/replication, and related costs |
| Structure changes | Schema migrations | Item `schemaVersion`, multi-version readers, data migration |
| Analytics | JOINs, relational reporting | Document queries/projections; often paired with stream/analytical platforms |

Cosmos DB works well when workloads have **well-known partition key access paths**, benefit from flexible JSON, and need distributed scale. If most operations involve complex relational JOINs across many entities or wide-ranging transactions, **Azure SQL Database or PostgreSQL** may be a better fit.

Never assume:

- “NoSQL means no schema is needed.”
- “All queries are cheap.”
- “All documents always live on a single physical partition.”
- “Cosmos DB supports distributed ACID transactions across multiple containers.”
- “Picking Strong consistency is always best.”
- “Adding more RU/s fixes every hot partition.”

## 3. Hierarchy: account → database → container → item

~~~mermaid
flowchart TB
    SUB["Azure subscription"] --> RG["Resource group"]
    RG --> ACCOUNT["Cosmos DB account<br/>API, endpoint, regions, consistency, security"]
    ACCOUNT --> DB1["Database commerce"]
    ACCOUNT --> DB2["Database internal-tools"]
    DB1 --> ORDERS["Container orders<br/>partition key /tenantId"]
    DB1 --> CUSTOMERS["Container customers<br/>partition key /tenantId"]
    DB1 --> PRODUCTS["Container products<br/>partition key /categoryId"]
    ORDERS --> O1["JSON item order-481"]
    ORDERS --> O2["JSON item order-482"]
    CUSTOMERS --> C1["JSON item customer-91"]
~~~

### 3.1. Account

The **Account** is the Azure resource holding the connection endpoint and global settings such as:

- API chosen at creation (here, NoSQL).
- Primary region, additional regions/replication, and failover settings.
- Default consistency level.
- Network access, firewalls, and private endpoints per feature support.
- Identity, keys, and control-plane/data-plane security.
- Throughput model and billing capabilities based on creation options.
- Monitoring, backups, and governance metadata.

A Cosmos DB for NoSQL endpoint typically looks like:

~~~text
https://<cosmos-account-name>.documents.azure.com:443/
~~~

The account name must be globally unique and meet the service's naming constraints. An account is not a document or a table.

### 3.2. Database

A **Database** groups containers belonging to an application or domain, such as **commerce**. It can carry **shared provisioned throughput** for containers configured to share that RU/s pool.

A database **is not inherently a dedicated compute cluster** or an absolute standalone trust boundary. Actual access controls also depend on account settings, data-plane RBAC, scope, networking, and application authorization.

### 3.3. Container

A **Container** is a collection of JSON items sharing a partitioning scheme. Here you typically define:

- Container name/ID.
- **Partition key path** (for example, **/tenantId**).
- Indexing policy.
- Unique key policy, if needed.
- Default or per-item TTL, if enabled.
- Dedicated throughput or shared database throughput.
- Additional service-supported feature settings.

Items in a container are distributed by Cosmos DB across physical partitions according to the partition key and scaling needs.

### 3.4. Item

An **Item** is a JSON document. Directly reading a single item typically requires its **id** and its **partition key** value.

~~~json
{
  "id": "order-481",
  "tenantId": "tenant-hcm",
  "type": "order",
  "status": "PAID",
  "currency": "VND",
  "totalMinorUnits": 350000,
  "createdAtUtc": "2026-11-20T03:03:20Z",
  "customer": {
    "customerId": "customer-91",
    "displayName": "Sample customer"
  },
  "lines": [
    { "sku": "SKU-12", "quantity": 2, "unitPriceMinorUnits": 125000 },
    { "sku": "SKU-80", "quantity": 1, "unitPriceMinorUnits": 100000 }
  ]
}
~~~

You do not need to declare SQL columns before inserting documents, but you must **validate fields, versions, and types** in your application.

## 4. Choosing the Right API and Service

Cosmos DB offers multiple experiences, such as **API for NoSQL**, **API for MongoDB**, and other current service models/APIs.

| Requirement | Consideration |
|---|---|
| JSON data and the Cosmos partition/query model | Cosmos DB **for NoSQL** |
| Application requires MongoDB wire protocol/tooling | Corresponding **Cosmos DB for MongoDB** model |
| Heavy relationships, JOINs, and complex relational transactions | Azure SQL / PostgreSQL |
| Graph traversals are central | Appropriate graph-capable database/API |
| Long-term reporting requiring large-scale analytics | Fabric / Synapse / Data Lake / ADX or an analytical path |

Do not apply NoSQL Java SDK syntax or **az cosmosdb sql container** commands to an account created with a different API without verifying compatibility.

## 5. Account: Decisions Before Creation

1. **Region and data residency:** Where does the app run, where must data reside, and what is the target user latency?
2. **Availability:** Single region, or multiple read/write regions as supported?
3. **Consistency:** Session, Eventual, Strong, etc., based on business needs.
4. **Billing/throughput mode:** Provisioned manual/autoscale or serverless.
5. **Network:** Restricted public access or Private Endpoint.
6. **Credentials:** Microsoft Entra identity and data permissions; avoid account keys in code.
7. **Backup/restore:** Supported backup model and RPO/RTO requirements.
8. **FinOps:** Owner, tags, budgets, and cost tracking.

### 5.1. Consistency Cannot Be Chosen Arbitrarily

Cosmos DB for NoSQL provides **Strong**, **Bounded staleness**, **Session**, **Consistent prefix**, and **Eventual** consistency levels with distinct read guarantees.

The default level is configured at the account level, and requests/SDKs can request weaker or matching levels within allowed bounds; you cannot simply override an account config with a **stronger** level via a single line of code.

### 5.2. Multi-Region Does Not Replace Backup

Replication and failover protect availability, but an application bug that accidentally deletes documents or writes bad data will replicate those changes too. You still need backup/restore, auditing, and dedicated DR procedures.

### 5.3. Serverless or Provisioned?

**Provisioned throughput** allocates processing capacity in **RU/s** at the database or container level. **Serverless** bills per consumed request RUs under its own model and limits, making it well-suited for some small or spiky workloads.

Never assume you can switch freely back and forth between serverless and provisioned on the same account without migration; verify the mode decision upfront.

## 6. Databases and Throughput Allocation

Example layout:

~~~text
Database: commerce
    Container orders
    Container customers
    Container products

Database: internal-tools
    Container audit-events
~~~

### 6.1. Shared Database Throughput

Allocates an RU/s pool at the **database scope** for containers configured to share that pool.

**Advantages:** Many small containers can share capacity, reducing management overhead.

**Trade-offs:** One hot container can consume the budget and throttle sibling containers. Monitor per-container metrics, not just total RUs.

### 6.2. Dedicated Container Throughput

Assigns dedicated RU/s to a high-traffic container or one with strict SLOs. This simplifies budget isolation, though total minimum RU/s and baseline cost may be higher.

### 6.3. Autoscale

Autoscale lets Cosmos DB adjust throughput within a configured range as supported. However, it does not mean “zero traffic equals zero cost.” Billing follows autoscale max/scaling rules and actual tier pricing, which should always be verified against the pricing schedule.

| Scenario | Suggested Model |
|---|---|
| Many small containers with light, scattered traffic | Shared database throughput |
| Very large Orders container, tiny Products container | Dedicated throughput for Orders, small or separate pool for Products |
| Traffic peaks during specific hours | Autoscale where appropriate |
| Light lab, low/irregular request volume | Evaluate serverless and its constraints |
| Continuous reporting across all tenants | Use an analytical/read model instead of just raising RU/s |

## 7. Container: The Most Critical Unit in the Model

A container's partition key path, unique key policy, and indexing policy are difficult to change once significant data is stored.

### 7.1. A Single Container Can Hold Multiple Document Types

~~~text
Container: commerce-data
Partition key: /tenantId

type = order
type = customer
type = cart
type = audit
~~~

This can make sense when document types share query patterns and transaction boundaries. However, avoid merging domains when:

- TTL requirements differ.
- Access permissions differ.
- One document type generates hot traffic.
- Unique key constraints differ.
- Indexing and retention needs diverge.

**Do not reflexively create a container for every Java class**, and do not assume a single-container design fits every NoSQL system.

### 7.2. Naming Conventions

~~~text
Account       = cosmos-commerce-prod-sea
Database      = commerce
Container     = orders
Partition key = /tenantId
Document type = order
Schema        = schemaVersion: 2
~~~

Example names must still be checked for validity and global availability; they do not represent pre-existing resources in your subscription.

## 8. Document Schema and System Metadata

~~~json
{
  "id": "order-481",
  "tenantId": "tenant-hcm",
  "type": "order",
  "schemaVersion": 2,
  "orderNumber": "HN-2026-00481",
  "status": "PAID",
  "createdAtUtc": "2026-11-20T03:03:20Z",
  "updatedAtUtc": "2026-11-20T03:10:00Z",
  "currency": "VND",
  "totalMinorUnits": 350000,
  "customerSnapshot": {
    "id": "customer-91",
    "displayName": "Sample customer"
  },
  "lines": [
    { "sku": "SKU-12", "nameSnapshot": "T-shirt", "quantity": 2, "unitPriceMinorUnits": 125000 },
    { "sku": "SKU-80", "nameSnapshot": "Shipping", "quantity": 1, "unitPriceMinorUnits": 100000 }
  ],
  "labels": ["online", "paid"]
}
~~~

### 8.1. Key Fields

| Field | Source | Purpose |
|---|---|---|
| **id** | Application | Item identifier within the logical partition |
| **tenantId** | Application | Partition key value when the path is `/tenantId` |
| **type** | Application | Distinguishes JSON item types |
| **schemaVersion** | Application | Manages schema evolution |
| **status** | Application | Business state |
| **createdAtUtc** | Application | Timestamp following an ISO 8601 contract |
| **lines** | Application | Embedded array of line items |
| **_etag** | Cosmos DB | Optimistic concurrency token |
| **_ts** | Cosmos DB | Service-managed timestamp |
| **_rid**, **_self**... | Cosmos DB | Internal system metadata |

Never manually modify system metadata or treat **_rid** as a business ID. Never assume **_ts** equals `createdAtUtc`; it reflects service-managed metadata updates.

### 8.2. Flexible Schemas Still Require Validation

The following two items can coexist in the same container, making queries error-prone:

~~~json
{"id":"o-1","tenantId":"t-1","status":"PAID","totalMinorUnits":200000}
{"id":"o-2","tenantId":"t-1","state":"PAID","amount":"200000"}
~~~

Your design needs:

- JSON Schema or application-level validators.
- Clear required vs. optional fields.
- Consistent types for currency, timestamps, and enums.
- `schemaVersion` tracking and backward-compatible readers.
- Contract tests between APIs and workers.
- Data migrations when fields are renamed.
- Guards against null/missing values skewing queries.

### 8.3. Dates and Currency

JSON has no dedicated Date type; use ISO 8601 UTC strings or a well-defined timestamp contract. For money, avoid unrounded floating-point numbers. Use integer minor units or decimal-as-string depending on currency and business rules.

### 8.4. Items Must Not Grow Unbounded

If you embed millions of audit events inside a single order document:

- Point reads return oversized payloads.
- Read and write RU charges climb.
- ETag contention spikes when multiple workers update the document.
- You risk exceeding the maximum item size limit (typically around **2 MiB** for NoSQL; verify current quotas).
- History cannot have an independent lifecycle.

Split history into separate items—in the same logical partition if transactionality is required, or in a separate container if lifecycle or throughput differs.

## 9. Logical Partitions and Physical Partitions

### 9.1. Logical Partition

A container with partition key path **/tenantId** creates logical partitions grouped by **value**:

~~~text
tenant-hcm:
    order-481
    order-482
    order-483

tenant-hn:
    order-601
    order-602
~~~

Items with the same partition key value belong to **a single logical partition**, which is also a critical transaction boundary.

### 9.2. Physical Partition

Cosmos DB places logical partitions onto service-managed **physical partitions**. You do not manually create **P0/P1** partitions or assign items to them in code.

~~~mermaid
flowchart TB
    C["Container orders"] --> L1["Logical partition tenant-hcm"]
    C --> L2["Logical partition tenant-hn"]
    C --> L3["Logical partition tenant-dn"]
    L1 --> P1["Physical partition A"]
    L2 --> P1
    L3 --> P2["Physical partition B"]
~~~

This diagram is illustrative only. Actual mappings can shift as Cosmos DB scales.

### 9.3. `id` Is Not Necessarily Globally Unique Across the Container

In a partitioned container:

~~~text
(id=order-481, partitionKey=tenant-hcm) → Item A
(id=order-481, partitionKey=tenant-hn)  → Item B
~~~

Two items can share the same **id** if they reside in different logical partitions. Point reads require **both the exact id and the partition key**.

### 9.4. The Partition Key Is Not Just an Index

The partition key governs:

- Query and read routing.
- Storage and RU distribution.
- Hot partitions and throughput scaling.
- Atomic transaction boundaries.
- Whether an item can be found when the API only knows a single business ID.
- Migration complexity if a business key changes.

Fixing a poor partition key choice is usually much harder than adding a missing index.

## 10. Five Criteria for Selecting a Partition Key

1. **High cardinality:** Enough distinct values.
2. **Even load distribution:** Avoid concentrating reads/writes on a single value.
3. **Present in frequent queries:** The app knows the partition key for point reads and single-partition queries.
4. **Stability:** Not a frequently mutated business field.
5. **Transaction alignment:** Data needing atomic updates shares the same logical partition when appropriate.

| Candidate Key | Benefit | Risk |
|---|---|---|
| **/status** | Filtering by status looks convenient | Only a handful of values (NEW/PAID); severely hot and oversized |
| **/createdDate** | Aids certain daily reports | Today's date is always hot |
| **/tenantId** | Multi-tenant isolation by key, tenant-scoped APIs, intra-tenant transactions | Very large tenants create hot partitions |
| **/orderId** | High cardinality, great per-order distribution | Querying all orders for a tenant requires cross-partition fan-out |
| **/customerId** | Retrieves a customer's order history | Tenant-wide reporting and very active customers |
| **Synthetic bucket** | Actively spreads load | App must manage buckets; tenant queries span buckets |

Never pick **/status** simply because the app filters by status. A partition key must balance **query routing and scalability**.

### 10.1. Multi-Tenant `/tenantId`

If every API call knows `tenantId`, **/tenantId** is an intuitive option. However, you must evaluate whether a massive tenant could exceed the capacity or storage limits of a single logical partition.

For large-scale needs, consider:

- Hierarchical partition keys.
- Synthetic keys such as tenant + bucket or order prefix.
- Moving large tenants to dedicated containers or accounts when necessary.
- Materialized views or lookup containers to support secondary access patterns.
- Validating logical partition limits and real throughput metrics.

### 10.2. Hierarchical Partition Keys

Some API for NoSQL configurations support multi-level hierarchical partition keys, such as:

~~~text
Level 1: /tenantId
Level 2: /orderId
~~~

This helps distribute large tenants while still enabling prefix-based query routing where supported. However, the full logical partition is defined by **all configured key levels**, so do not assume items sharing only the first level (`tenantId`) can participate in a transactional batch when their second-level keys differ.

Do not enable this option without checking SDK/API/feature compatibility and migration plans. Benchmark against real queries and transaction boundaries.

### 10.3. Do Not Pick a Frequently Changing Field as the Partition Key

If the partition key is **/country** and a customer moves countries, updating it is not like running an in-place SQL column `UPDATE`. You generally have to insert the item under the new partition, handle references/idempotency, and delete the old item via a workflow.

Prefer immutable keys like `tenantId` or `orderId` over mutable fields like status or account tier.

## 11. Access Patterns Before Data Model

Write out an operations table:

| Access Pattern | Frequency | Available Inputs | Goal |
|---|---:|---|---|
| Get order details | Very high | `tenantId` + `orderId` | Point read one item |
| List 20 latest orders in a tenant | High | `tenantId` | Single-partition indexed query |
| Update order status | High | `tenantId` + `orderId` | Conditional patch/replace |
| Get customer profile | Medium | `tenantId` + `customerId` | Point read customer |
| Display price at purchase time | High | `orderId` + `tenantId` | Embed price snapshot |
| Find order by email | Medium | `email` | Lookup/read model keyed by email |
| Monthly report across all tenants | Batch | Date interval | Analytical projection/pipeline |
| Audit status history | Medium | `orderId` | Separate event items |
| Update SKU inventory | Very high | `warehouseId` + `sku` | Separate domain/partition |

### 11.1. API Knows Both `id` and Partition Key

~~~text
GET /tenants/tenant-hcm/orders/order-481
~~~

With container **orders** partitioned by **/tenantId** and item **id=order-481**, the app can execute a direct point read.

### 11.2. API Only Has `orderId`

~~~text
GET /orders/order-481
~~~

If the partition key is `/tenantId`, the application **lacks the routing key**. Options include:

- Requiring `tenantId` in the route, token, or request context.
- Maintaining an **orderId → tenantId** lookup.
- Choosing a different key if lookup by `orderId` is the dominant access pattern.
- Accepting cross-partition queries with budgets/telemetry if rare.
- Maintaining a materialized lookup projection updated via Change Feed or outbox.

Do not finalize a partition key only to realize later that critical API calls lack it.

## 12. Embed or Reference?

### 12.1. Embedding Data Owned by the Order

~~~json
{
  "id": "order-481",
  "tenantId": "tenant-hcm",
  "type": "order",
  "lines": [
    { "sku": "SKU-12", "quantity": 2, "unitPriceMinorUnits": 125000 },
    { "sku": "SKU-80", "quantity": 1, "unitPriceMinorUnits": 100000 }
  ]
}
~~~

Advantages: one point read fetches both order and lines, fewer round trips, and prices act as a point-in-time snapshot. Trade-offs: larger items, write contention, and trouble with unbounded arrays.

### 12.2. Referencing Live Data

~~~json
{
  "id": "order-481",
  "tenantId": "tenant-hcm",
  "customerId": "customer-91",
  "lineItemIds": ["line-1", "line-2"]
}
~~~

Advantages: entities update, scale, and expire independently. Trade-offs: extra round trips, application-side read orchestration, and no arbitrary cross-container JOINs.

### 12.3. Rules of Thumb

**Embed** when data is small, bounded, frequently read together, shares a lifecycle, and needs a historical snapshot.

**Reference** when data is large or unbounded, shared in many places, updated independently and frequently, or has separate access patterns, throughput, TTL, or permissions.

Hybrid designs are common: store **customerId** to link to the live profile alongside **customerNameSnapshot** inside the order for accurate invoicing.

## 13. Order Modeling: From Tables to Documents

### 13.1. Initial Relational Model

~~~text
Orders(orderId, tenantId, customerId, status, createdAt)
OrderLines(lineId, orderId, sku, qty, price)
Customers(customerId, tenantId, name)
Products(sku, currentPrice)
OrderStatusHistory(eventId, orderId, eventTime)
~~~

An order detail screen typically joins several tables.

### 13.2. Document Optimized for Order Detail Reads

~~~json
{
  "id": "order-481",
  "tenantId": "tenant-hcm",
  "type": "order",
  "schemaVersion": 2,
  "customerId": "customer-91",
  "customerSnapshot": {
    "displayName": "Sample customer",
    "membershipTierAtPurchase": "GOLD"
  },
  "lines": [
    {
      "sku": "SKU-12",
      "nameSnapshot": "T-shirt",
      "quantity": 2,
      "unitPriceMinorUnits": 125000
    }
  ],
  "totalMinorUnits": 250000,
  "status": "PAID",
  "createdAtUtc": "2026-11-20T03:03:20Z"
}
~~~

The order detail view reads a single item. The live Product catalog remains separate because catalog prices and stock change independently, while the order preserves the purchase-time price snapshot.

### 13.3. Status History as Event Items

~~~json
{
  "id": "order-481-event-0001",
  "tenantId": "tenant-hcm",
  "orderId": "order-481",
  "type": "order-status-event",
  "eventType": "PAID",
  "eventTimeUtc": "2026-11-20T03:10:00Z"
}
~~~

If the order and its audit events live in the **same container and logical partition**, they can use a transactional batch; if placed in **different containers**, there is no arbitrary cross-container transaction.

### 13.4. Denormalization Requires Synchronization Rules

If a customer changes their name:

- The Customer profile stores the current name.
- Historical Order snapshots may intentionally preserve the name shown at purchase time.
- If a snapshot ever needs correction per business rules, maintain versioning/auditing.
- For non-snapshot read models, push projection updates via Change Feed or an outbox.

Never treat denormalization as “copying data and leaving nobody responsible for keeping it accurate.”

## 14. Queries: Point Reads, Single-Partition, and Cross-Partition

### 14.1. Point Read

~~~text
Container: orders
id: order-481
partitionKey: tenant-hcm

ReadItem(id, PartitionKey("tenant-hcm"))
~~~

Point reads usually deliver the lowest latency and RU cost when both keys are known and item sizes are reasonable.

### 14.2. Query Within One Tenant

~~~sql
SELECT c.id, c.status, c.createdAtUtc, c.totalMinorUnits
FROM c
WHERE c.tenantId = "tenant-hcm"
  AND c.type = "order"
  AND c.status = "PAID"
ORDER BY c.createdAtUtc DESC
~~~

In the SDK, pass the partition key in query options whenever it is known. Watch indexing, `ORDER BY`, pagination, and RU consumption.

### 14.3. Cross-Partition Query

~~~sql
SELECT * FROM c
WHERE c.status = "PAID"
~~~

With partition key **/tenantId**, this query may scan all partitions, driving high RU usage and latency. If cross-tenant reporting is frequent, consider materialized views or an analytical store (ADX, Fabric, Synapse) as supported.

### 14.4. JOIN in Cosmos SQL

~~~sql
SELECT c.id, line.sku, line.quantity
FROM c
JOIN line IN c.lines
WHERE c.tenantId = "tenant-hcm"
~~~

This is an **intra-item array JOIN**, not an arbitrary JOIN across the **orders** and **products** containers.

## 15. RU/s, Costs, and HTTP 429

A **Request Unit (RU)** measures the resources consumed by an operation: reads, writes, queries, indexing, and related work. Provisioned throughput allocates capacity in **RU/second**.

| Operation | RU Characteristics |
|---|---|
| Point read of a small item | Usually efficient |
| Query with partition filter and index | More efficient than broad scans |
| Cross-partition aggregate | Can consume high RUs |
| Write of a large item with many indexed properties | Costs more RUs than a small item write |
| Updating a single field by replacing the item | Incurs full write and index update costs |
| TTL/deletes/change projections | Carry specific overhead and billing behaviors |

### 15.1. RU Estimation Example

~~~text
Measured in load test:
  Point read: 5 RU/request
  Write:     12 RU/request

Peak:
  600 reads/s  → 600 × 5  = 3,000 RU/s
  100 writes/s → 100 × 12 = 1,200 RU/s

Preliminary total        ≈ 4,200 RU/s
~~~

This is only a rough estimate; it excludes queries, retries, indexing, cross-region traffic, and hot partitions. Do not treat this example as an Azure benchmark or pricing quote.

### 15.2. Hot Partitions and 429

A very hot partition key can be throttled even while the container still has spare RUs on other physical partitions. When seeing **429 Request Rate Too Large**:

1. Inspect `retry-after` and SDK retry behavior.
2. Measure normalized RU consumption and per-partition heat.
3. Check for keyless queries and broad scans.
4. Check large writes and indexing policies.
5. Consider bounded concurrency, caching, or batching.
6. Re-evaluate the partition strategy if a genuine hot key exists.
7. Increase provisioned RUs only after identifying the bottleneck.

Do not retry infinitely or spin up unbounded workers, which can worsen saturation.

## 16. Indexing, Unique Keys, and TTL

### 16.1. Indexing

Cosmos DB for NoSQL indexes most property paths under its **default indexing policy**, enabling flexible queries at the expense of write overhead.

- Exclude paths that are never queried if doing so meaningfully lowers write costs.
- Create **composite indexes** when queries sort or filter across multiple `ORDER BY` fields.
- Inspect query metrics, index metrics, and RU charges.
- Do not confuse “having an index on `status`” with “turning a cross-partition query into a single-partition query.”

Example:

~~~sql
SELECT * FROM c
WHERE c.tenantId = "tenant-hcm"
ORDER BY c.status ASC, c.createdAtUtc DESC
~~~

This may require a matching composite index aligned with the fields, sort directions, and active policy.

### 16.2. Unique Key Policy

Unique keys enforce uniqueness on one or more property paths **within a logical partition**.

~~~text
Partition key /tenantId
Unique key /normalizedEmail

tenant-hcm + alice@example.invalid → unique within tenant-hcm
tenant-hn  + alice@example.invalid → can exist independently
~~~

Plan this at container creation: changing a unique key policy generally requires creating a new container and migrating data. Test case sensitivity, missing/null fields, and normalization.

### 16.3. TTL

Time to Live automatically expires items based on container and item configuration. Example:

~~~json
{
  "id": "session-481",
  "tenantId": "tenant-hcm",
  "type": "session",
  "ttl": 3600
}
~~~

Item-level TTL takes effect when TTL is enabled on the container; values are typically in seconds. Expiration is tied to service-managed timestamps rather than an application-supplied **createdAtUtc** field.

TTL fits sessions, caches, and temporary telemetry; never enable short TTLs on Orders or audit records subject to retention rules.

## 17. Change Feed and Consistency

### 17.1. Change Feed

The **Change Feed** lets consumers read document changes according to supported modes and semantics, powering:

- Search and read-model updates.
- Pushing data into analytical pipelines.
- Application synchronization.
- Cross-tenant projections.
- Event-driven processing after item mutations.

Every projection needs idempotency, checkpoints, and schema versioning. Behavior around deletes, TTL, and full modification history depends on the **change feed mode**; do not assume every mode emits all before/after states.

### 17.2. Consistency Levels

| Level | Conceptual Meaning |
|---|---|
| **Strong** | Reads return the latest state under supported strong guarantees |
| **Bounded staleness** | Staleness/lag bounded by configured versions or time |
| **Session** | Per-session guarantees, including read-your-writes when propagating the session token |
| **Consistent prefix** | Observes a valid ordered prefix of writes |
| **Eventual** | Replicas converge eventually; reads may be stale |

**Session** is often a balanced default for web APIs, provided session tokens are properly handled across services and clients. **Strong** carries multi-region trade-offs and limitations; do not choose Strong solely because “the data is important.”

### 17.3. Consistency Does Not Replace Transactions

Even under Strong reads, two workers can race on updating the same item; ETag conditional updates are still required. Conversely, Session consistency does not make writes across Cosmos DB and Service Bus atomic.

## 18. Transactions and Optimistic Concurrency

### 18.1. Transactional Batch Scoped to One Logical Partition

Cosmos DB for NoSQL supports **transactional batch** operations across items in the **same container and same logical partition**, subject to API quotas and limits.

Example:

~~~text
Container orders, partition key /tenantId

Logical partition tenant-hcm:
    Replace order-481: status=PAID
    Create order-481-event-0001: type=order-event

Transactional batch:
    Both operations commit together or roll back together
~~~

If status history lives in a separate **audit** container, Cosmos DB does not provide an atomic transaction spanning both containers. Nor is there an automatic distributed transaction spanning Cosmos DB, Azure SQL, Blob Storage, and Service Bus.

### 18.2. ETag and `If-Match`

Two workers read the same order concurrently:

~~~text
Worker A: reads order-481, ETag=e1
Worker B: reads order-481, ETag=e1

Worker A: replace If-Match e1 → succeeds, new ETag e2
Worker B: replace If-Match e1 → HTTP 412 Precondition Failed
~~~

The application handles 412 by re-reading the latest state, validating business invariants, and either merging/retrying with bounded attempts or surfacing a conflict. **Never blindly retry with `upsert`**: that can silently overwrite another worker's valid update.

### 18.3. Create, Replace, Patch, and Upsert Are Not Identical

| Operation | When to Use | Risk If Misused |
|---|---|---|
| **Create item** | Only allow if item does not yet exist | 409 if `id` already exists in the logical partition |
| **Replace item** | Controlled full-item replacement | Dropping newer fields added by another writer causes data loss |
| **Patch item** | Modify specific paths where supported | Must still manage preconditions, atomicity, and concurrency |
| **Upsert item** | Insert if new, replace if existing | Can mask conflicts or overwrite fields |
| **Delete item** | Remove per policy | Must account for auditing, backups, and legal retention |

For financial histories, overwriting an earlier event solely to reflect current state is usually unacceptable; maintain an append-only ledger/audit trail and idempotent business state.

## 19. Preparing for the Azure Cosmos DB for NoSQL Lab

This lab uses the following illustrative resources:

| Setting | Example Value |
|---|---|
| Azure region | `southeastasia` |
| Resource group | `rg-cosmos-lab` |
| Account | `cosmosorderslabxyz` (must be globally unique) |
| API | `for NoSQL` |
| Database | `commerce` |
| Container | `orders` |
| Partition key path | `/tenantId` |
| Throughput | 400 RU/s manual on provisioned model, if permitted |
| Test tenant | `tenant-hcm` |
| Test item | `order-481` |

**Prerequisites:**

1. Approved lab subscription/budget and resource creation permissions.
2. Verify account ownership and ensure no production resources are touched.
3. Appropriate Azure Resource Manager role to create accounts, databases, and containers.
4. For the Java Entra SDK, an identity assigned the proper **Cosmos DB data-plane role**.
5. Java 17+, Maven, and project-approved SDK versions.
6. Working network/DNS/TLS connectivity to the Cosmos endpoint (configured via Private Endpoint if required).
7. Synthetic test data only—no real customer data.
8. A lab cleanup plan; provisioned RU/s continues accruing charges even when the app is idle.

Do not create a new account if your organization already provides a dedicated lab account, database, and container.

## 20. Azure CLI: Creating the Account, Database, and Container

Examples use **Azure Cloud Shell Bash** or a shell with the Azure CLI installed. These **operations can incur charges**—run them only in an approved lab subscription.

### 20.1. Create Resource Group and Account

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-cosmos-lab"
REGION="southeastasia"
ACCOUNT="<globally-unique-cosmos-account>"
DB="commerce"
CONTAINER="orders"

az group create \
  --name "$RG" \
  --location "$REGION"

az cosmosdb create \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --locations regionName="$REGION" failoverPriority=0 \
  --default-consistency-level Session
~~~

This example provisions a **provisioned-throughput account**, not serverless syntax. Serverless is an account-level capability/model with its own flags and limits; consult the current documentation if choosing that mode.

If the account already exists, **do not re-run create**; inspect its metadata using read commands instead.

### 20.2. Create the Database

~~~bash
az cosmosdb sql database create \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --name "$DB"
~~~

This example omits shared database throughput because throughput will be set at the container level. If using database-level shared RU/s, configure it consistently so you do not inadvertently assign dedicated RU/s to every container as well.

### 20.3. Create the Container and Partition Key

~~~bash
az cosmosdb sql container create \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --database-name "$DB" \
  --name "$CONTAINER" \
  --partition-key-path "/tenantId" \
  --throughput 400
~~~

**Never pick a throwaway partition key** and load real data into it. Changing the key afterward normally requires creating a new container and migrating data.

400 RU/s is an illustrative lab figure subject to current tier, quota, and pricing rules. Do not assume it is the universal default or minimum for every configuration.

### 20.4. Inspect Account, Database, and Container

~~~bash
az cosmosdb show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name,endpoint:documentEndpoint,consistency:consistencyPolicy,locations:readLocations}" \
  --output json

az cosmosdb sql database show \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --name "$DB" \
  --output json

az cosmosdb sql container show \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --database-name "$DB" \
  --name "$CONTAINER" \
  --output json
~~~

In the container output, check `partitionKey` paths, indexing policy, TTL, and related fields. Azure CLI flags and JSON output schemas can vary by CLI/API version; if a `--query` projection prints `null`, inspect the full JSON before assuming the resource is misconfigured.

### 20.5. Lab Cleanup

Only delete the account, database, container, or resource group if they were **created exclusively for this lab** and hold no shared team resources or data. Export any test evidence needed and verify Azure Cost Management afterward, keeping in mind billing metrics may lag.

## 21. Microsoft Entra ID and Cosmos DB Data-Plane RBAC

### 21.1. Two Authorization Layers

**Control plane (ARM / Azure RBAC)** governs who can create, modify, or delete Azure resources and manage regions, networking, and throughput.

**Cosmos DB for NoSQL data plane** governs who can read, query, and write items using **Cosmos DB native data-plane RBAC** roles such as:

- **Cosmos DB Built-in Data Reader**.
- **Cosmos DB Built-in Data Contributor**.

**Having Azure `Contributor` on a resource group does not grant permission to query or write documents** via Entra data-plane identities. Nor should you fall back to handing out account keys simply because a user has Azure Contributor.

### 21.2. Controlled Data-Plane Role Assignment

In a lab, an administrator can list available role definitions:

~~~bash
az cosmosdb sql role definition list \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --output json
~~~

Once authorized by the resource owner, use the actual role definition ID and the managed identity's principal object ID to create a scoped role assignment. Structural example:

~~~bash
PRINCIPAL_ID="<managed-identity-principal-object-id>"
ROLE_DEF_ID="<data-contributor-role-definition-id>"

az cosmosdb sql role assignment create \
  --resource-group "$RG" \
  --account-name "$ACCOUNT" \
  --principal-id "$PRINCIPAL_ID" \
  --role-definition-id "$ROLE_DEF_ID" \
  --scope "/dbs/commerce/colls/orders"
~~~

Check the current Azure CLI/API documentation for exact role definition ID formats, scopes, and required assignment permissions. **Do not execute with placeholders.** Scope `/dbs/commerce/colls/orders` restricts access to one container; avoid granting account-wide `/` scope when only `orders` is needed.

### 21.3. Keep Account Keys Out of Source Code

Account keys and connection strings grant broad key-based access. Never commit them to Git, logs, Dockerfiles, or application telemetry. When keys are unavoidable in exceptional scenarios, store them in Key Vault with rotation and tight access controls.

For App Service, AKS, Functions, and VMs, prefer **managed identity / Workload Identity** wherever supported by the SDK and data plane, paired with RBAC and network controls.

### 21.4. Private Networking

If the account uses a Private Endpoint:

- The application's VNet/subnet must have routing to the private endpoint.
- DNS must resolve the Cosmos endpoint to the private IP.
- The NoSQL Private DNS zone typically uses **`privatelink.documents.azure.com`**.
- HTTPS/TLS traffic must be permitted through firewalls and NSGs along the path.
- Managed identity / Entra token issuance carries its own authentication network dependencies.

**A Private Endpoint does not grant data-plane roles.** If the SDK returns 403, check data-plane RBAC; if DNS or network requests time out, inspect Private Link, routing, and TLS; if 429 occurs, check RU budgets.

## 22. Java SDK v4: Dependencies and Client Setup

The Azure SDK for API for NoSQL typically uses Maven artifact **`com.azure:azure-cosmos`** (v4) paired with **`com.azure:azure-identity`** for Entra authentication.

Example dependencies in **`pom.xml`**:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-cosmos</artifactId>
    <version>REPLACE_WITH_TESTED_COSMOS_V4_VERSION</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>REPLACE_WITH_TESTED_IDENTITY_VERSION</version>
  </dependency>
</dependencies>
~~~

**Versions are placeholders:** fill in project-approved versions or use a compatible Azure SDK BOM/dependency management block before running Maven. The snippet shows dependencies only, not a complete POM.

### 22.1. Creating a `CosmosClient`

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.ConsistencyLevel;
import com.azure.cosmos.CosmosContainer;
import com.azure.identity.DefaultAzureCredentialBuilder;

String endpoint = System.getenv("COSMOS_ENDPOINT");
if (endpoint == null || endpoint.isBlank()) {
    throw new IllegalArgumentException("Missing COSMOS_ENDPOINT");
}

CosmosClient client = new CosmosClientBuilder()
    .endpoint(endpoint)
    .credential(new DefaultAzureCredentialBuilder().build())
    .consistencyLevel(ConsistencyLevel.SESSION)
    .buildClient();

CosmosContainer orders = client
    .getDatabase("commerce")
    .getContainer("orders");

// Manage client lifecycle and call client.close() on application shutdown.
~~~

This is a **snippet inside a class/method**, without a `main` method or full imports. Ensure the identity holds the proper **Cosmos DB data-plane RBAC** role before testing—do not run Create/Read with an unassigned managed identity and conclude the SDK is broken.

### 22.2. Reusing the Client

In long-running applications, **reuse `CosmosClient`** rather than creating and closing it on every HTTP request. Each client maintains connection pools and metadata caches; recreating it repeatedly increases latency and resource overhead.

However, in a multi-tenant app, never conflate client reuse with tenant trust boundaries; application-level authorization must still validate `tenantId`.

## 23. Java CRUD: Complete Partition-Key Example

The code below demonstrates **create, read, query, conditional replace, and delete** on the container created via the Azure CLI. It operates on a single lab item. Running it requires compatible SDK versions, `COSMOS_ENDPOINT` configured, and an authenticated Entra/managed identity with data permissions.

### 23.1. `OrdersCrudDemo` Class

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.ConsistencyLevel;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.CosmosQueryRequestOptions;
import com.azure.cosmos.models.PartitionKey;
import com.azure.cosmos.models.SqlParameter;
import com.azure.cosmos.models.SqlQuerySpec;
import com.azure.cosmos.util.CosmosPagedIterable;
import com.azure.identity.DefaultAzureCredentialBuilder;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class OrdersCrudDemo {
    public static void main(String[] args) {
        String endpoint = System.getenv("COSMOS_ENDPOINT");
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException("Missing COSMOS_ENDPOINT");
        }

        CosmosClient client = new CosmosClientBuilder()
            .endpoint(endpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .consistencyLevel(ConsistencyLevel.SESSION)
            .buildClient();

        try {
            CosmosContainer container = client
                .getDatabase("commerce")
                .getContainer("orders");

            String tenant = "tenant-hcm";
            String orderId = "order-lab-481";
            PartitionKey pk = new PartitionKey(tenant);

            Map<String, Object> order = new HashMap<>();
            order.put("id", orderId);
            order.put("tenantId", tenant);
            order.put("type", "order");
            order.put("schemaVersion", 1);
            order.put("status", "NEW");
            order.put("totalMinorUnits", 350000);
            order.put("currency", "VND");
            order.put("createdAtUtc", "2026-11-20T03:03:20Z");

            CosmosItemResponse<Map> created = container.createItem(
                order, pk, new CosmosItemRequestOptions());

            System.out.printf("Created RU=%.2f%n",
                created.getRequestCharge());

            CosmosItemResponse<Map> fetched = container.readItem(
                orderId, pk, Map.class);

            System.out.println("Read item: " + fetched.getItem());
            System.out.printf("Read RU=%.2f%n",
                fetched.getRequestCharge());

            // Conditional replace with ETag protects against concurrent writers.
            Map<String, Object> latest = fetched.getItem();
            latest.put("status", "PAID");

            CosmosItemRequestOptions replaceOptions =
                new CosmosItemRequestOptions()
                    .setIfMatchETag(fetched.getETag());

            CosmosItemResponse<Map> updated =
                container.replaceItem(
                    latest, orderId, pk, replaceOptions);

            System.out.printf("Updated RU=%.2f%n",
                updated.getRequestCharge());

            // Query scoped to a single tenant to avoid unnecessary fan-out.
            SqlQuerySpec query = new SqlQuerySpec(
                "SELECT * FROM c WHERE c.tenantId = @tenant " +
                "AND c.type = @type",
                List.of(
                    new SqlParameter("@tenant", tenant),
                    new SqlParameter("@type", "order")
                )
            );

            CosmosQueryRequestOptions queryOptions =
                new CosmosQueryRequestOptions()
                    .setPartitionKey(pk);

            CosmosPagedIterable<Map> results =
                container.queryItems(query, queryOptions, Map.class);

            results.iterableByPage().forEach(page -> {
                System.out.printf("Query page RU=%.2f%n",
                    page.getRequestCharge());
                page.getResults().forEach(System.out::println);
            });

            // Only delete the demo item after confirming both id and PK.
            container.deleteItem(
                orderId, pk, new CosmosItemRequestOptions());

        } finally {
            client.close();
        }
    }
}
~~~

### 23.2. Things to Understand Before Running

- **Create** returns a conflict if the same `id` already exists in that partition; the lab demo should run once or use a fresh ID.
- **Read** uses both `id` and partition key rather than a cross-partition `SELECT`.
- **Conditional replace** with ETag can return **412 Precondition Failed** if another worker modified the item first.
- **Queries** are parameterized; never concatenate raw user input into SQL text.
- **Query page request charge** lets you measure actual RU consumption.
- **Delete** performs a real deletion even in a lab. Never change the ID to a production order.
- `DefaultAzureCredential` credential resolution differs across local dev, CI, App Service, and AKS; verify the exact active identity and its role.
- If SDK/library APIs change across versions, adjust per your pinned Java SDK documentation without altering partition key semantics.

### 23.3. Why Are Both `id` and `tenantId` Present?

**`id`** identifies the document within a partition. **`tenantId`** is the field at path `/tenantId`. Together they form the logical address:

~~~text
(tenantId="tenant-hcm", id="order-lab-481")
~~~

Passing the wrong partition key (such as **`tenant-hn`**) will return 404 on a point read even though an item with that `id` exists under `tenant-hcm`.

### 23.4. Map or POJO in Java?

POJOs offer explicit annotations, serialization constraints, and stronger validation; `Map` is convenient for short demos but prone to type errors. Production code should use DTO/domain models, schema versioning, migration tests, and strict allowlists of user-writable fields.

## 24. Transactional Batch in Java

When two operations target the **same container and same logical partition**, use a transactional batch as supported by the SDK.

~~~java
import com.azure.cosmos.models.CosmosBatch;
import com.azure.cosmos.models.CosmosBatchResponse;
import com.azure.cosmos.models.PartitionKey;

import java.util.Map;

// Assumes container is an initialized CosmosContainer,
// and both items have tenantId="tenant-hcm".
PartitionKey pk = new PartitionKey("tenant-hcm");

Map<String, Object> order =
    Map.of("id", "order-lab-481",
           "tenantId", "tenant-hcm",
           "type", "order",
           "status", "PAID");

Map<String, Object> event =
    Map.of("id", "order-lab-481-event-1",
           "tenantId", "tenant-hcm",
           "type", "order-event",
           "eventType", "PAID");

CosmosBatch batch = CosmosBatch.createCosmosBatch(pk);
batch.upsertItemOperation(order);
batch.createItemOperation(event);

CosmosBatchResponse response = container.executeCosmosBatch(batch);
if (!response.isSuccessStatusCode()) {
    throw new IllegalStateException(
        "Transactional batch not committed");
}
~~~

This is a **Java snippet intended for a method with an initialized container and imports**, not a standalone class. It assumes the event ID does not yet exist and the order meets business rules. If the event ID already exists, the batch will fail; use deterministic event IDs, inspect the batch response, and build idempotent workflows.

**Limitation:** this code provides zero atomicity guarantees if the order and event are moved to separate containers or use different partition key values.

### 24.1. When Both SQL and Cosmos DB Must Be Updated in One Workflow

Do not pretend to have a distributed transaction. Use the **outbox pattern**, sagas/compensation, and idempotent consumers:

~~~mermaid
flowchart LR
    API["Orders API"] --> TX["Business database transaction"]
    TX --> STATE["Order state"]
    TX --> OUT["Outbox"]
    OUT --> PUB["Publisher"]
    PUB --> BUS["Service Bus / Event Grid"]
    BUS --> WORKER["Idempotent consumer"]
    WORKER --> COSMOS["Cosmos DB document/read model"]
~~~

Side effects outside the DB/broker can still be replayed on retries; require an `eventId` and idempotent consumers.

## 25. Multi-Tenant Patterns and Avoiding Hot Partitions

### 25.1. Small, Medium, and Large Tenants

Suppose a SaaS platform has:

~~~text
Tenant A:     10,000 orders / year
Tenant B:     60,000 orders / year
Tenant C: 20,000,000 orders / year
~~~

**/tenantId** may work well for A and B, while C could make a single logical partition oversized or hot. Evaluating a partition key solely by the average tenant count is insufficient.

### 25.2. Options

| Option | Benefit | Trade-off |
|---|---|---|
| **/tenantId** | Tenant grouping by key, simple tenant queries | Large tenant / hot key |
| **/orderId** | Very high cardinality | Tenant-wide queries need secondary views or fan-out |
| **/tenantBucket** | Splits large tenants across buckets | App must manage buckets; tenant queries hit multiple buckets |
| **Hierarchical key** | Supports tenant prefix queries and sub-level spread | Feature, API, and transaction semantics require testing |
| **Dedicated container/account per tenant** | Clear quota, cost, and permission isolation | More resources and operational overhead |

### 25.3. Mandatory Authorization

Cosmos DB partition keys do not check whether a caller belongs to a given tenant. An API accepting `tenantId` must:

1. Authenticate the JWT/identity.
2. Verify tenant membership in business authorization logic.
3. Derive the trusted `tenantId` from verified claims/context.
4. Supply that partition key to Cosmos DB requests.
5. Never allow callers to arbitrarily swap `tenantId` to access another tenant's data.

A managed identity's data-plane role often spans multiple tenants; **tenant isolation must still be enforced in API code**.

## 26. Modeling Catalog, Inventory, and Orders

### 26.1. Products / Catalog

Catalog workloads rely on SKU/`productId` lookups, search, and category filtering. If the API predominantly knows `productId`, partition by `productId` or design around that lookup. Never pick **/categoryId** if 80% of point reads only know `productId` without the category.

Example:

~~~json
{
  "id": "SKU-12",
  "productId": "SKU-12",
  "type": "product",
  "name": "T-shirt",
  "categoryId": "apparel",
  "currentPriceMinorUnits": 125000,
  "version": 7
}
~~~

### 26.2. Inventory

Inventory follows a **warehouse + SKU** access pattern with continuous updates and high concurrency. Pick a key aligned with item uniqueness and update volume, while watching for **hot SKUs**. Never store stock for thousands of SKUs inside one giant document updated concurrently by every order.

For reservations or ledgers:

- Use optimistic concurrency or transactional batches within an appropriate logical partition.
- Use idempotent reservation IDs.
- Separate ledger entries if history grows continuously.
- Monitor RU limits on hot SKUs.
- If business rules demand ACID across inventory and ledgers spanning multiple partitions, evaluate an RDBMS or alternative architecture.

### 26.3. Orders

Order details are commonly read with line items and a customer snapshot. An **orders container with `/tenantId`** is a sensible starting model for many moderately sized tenants.

~~~mermaid
flowchart TB
    API["Orders API"] --> OR["Container orders<br/>/tenantId"]
    API --> CA["Container customers<br/>/tenantId"]
    API --> PR["Container products<br/>/productId"]
    API --> INV["Container inventory<br/>keyed by warehouse + SKU"]
    OR --> CF["Change Feed"]
    CF --> PROJ["Materialized analytics/search projection"]
~~~

**Do not try to force writes across all four containers into a single Cosmos transaction.** Business workflows must rely on state machines, idempotency, and compensation.

## 27. Optimizing Queries and Measuring Request Charges

### 27.1. Projection

~~~sql
SELECT c.id, c.status, c.totalMinorUnits
FROM c
WHERE c.tenantId = "tenant-hcm"
  AND c.type = "order"
~~~

Select only the fields the UI needs instead of returning large raw payloads. Note that projection alone will not drastically slash RUs if the query still scans across many partitions.

### 27.2. Pagination

Returning millions of items in one request is an anti-pattern. Use SDK page sizes and continuation tokens, enforce API limits, and avoid treating deep `OFFSET` pagination as cheap when query costs do not support it.

Clients must treat continuation tokens as opaque within the same query, partition, and version—never edit them like custom IDs.

### 27.3. Multi-Condition Queries

Monitor:

- Query metrics.
- Index utilization.
- Request Charge.
- Result count.
- Query latency p95/p99.
- Cross-partition fan-out.
- Composite index requirements.
- Hot key values and normalized RUs.

### 27.4. How Costs Vary by Access Pattern

| API | Design | Behavior to Measure |
|---|---|---|
| GET order detail | Point read `id` + PK | RU/read and latency |
| GET latest tenant orders | Filter `/tenantId` + index on `createdAt` | RU/page |
| Search by email across all tenants | Cross-partition query | High RU/latency; consider a lookup model |
| Yearly revenue dashboard | Aggregate across all orders | Offload to Change Feed / analytical pipeline |
| Update single status | Conditional patch/replace | ETag conflicts, RU/write |
| Fetch oversized order item | Unbounded embedded rows | Item size, response payload, RUs |

## 28. Backup, DR, Consistency, and Regional Topology

### 28.1. Backup Is Not Replication

Cosmos DB provides backup and restore modes according to configuration and service capabilities—such as periodic or continuous backup under supported conditions.

- **Replication** protects availability and distributes reads/writes.
- **Backup/restore** recovers from data corruption or accidental deletion per supported RPO/RTO.
- **Business event ledgers** support auditing and domain state reconstruction.

Do not assume all accounts or tiers share the same retention, restore granularity, or cost. Choose based on production requirements and run restore drills.

### 28.2. Multi-Region Trade-Offs

- Users near a read region experience lower read latency.
- Write-region topology and consistency affect read-after-write, conflicts, and latency.
- Multi-write requires a carefully designed and tested conflict resolution policy.
- Costs scale with replicated storage, throughput, and cross-region data transfer.
- Networking, private endpoints, and DNS must be configured in every region.
- Applications need SDK preferred-region lists and failover strategies as supported.

Never assume “adding two regions equals zero RTO/RPO” without testing failover, conflict handling, client retries, and data correctness.

## 29. Migration and Changing a Partition Key

A classic production scenario: you started with **/tenantId**, and a year later your largest tenant becomes too hot.

### 29.1. Do Not Attempt Ad Hoc In-Place Key Edits

Usually you must:

1. Design a new container with the improved partition key.
2. Build a migration job to copy items while preserving schemas/IDs per policy.
3. Use Change Feed, dual-writes, or an outbox to catch ongoing mutations.
4. Reconcile item counts, checksums, and sample queries.
5. Shift reads gradually via feature flags or canary releases.
6. Switch writes to the new path with idempotency.
7. Monitor RUs, 429s, p95 latency, and correctness.
8. Keep a rollback route/backup and bound the parallel-run window.
9. Decommission the old container only after validation and an appropriate retention window.

### 29.2. Evolving `schemaVersion`

For example, v1 stored **amount** as a string, while v2 uses **totalMinorUnits**:

~~~json
{"id":"order-1","tenantId":"t-1","schemaVersion":1,"amount":"350000"}
{"id":"order-2","tenantId":"t-1","schemaVersion":2,"totalMinorUnits":350000}
~~~

Readers must:

- Detect the schema version.
- Convert values faithfully to business semantics.
- Avoid arbitrary defaults that distort monetary amounts.
- Support rolling forward during blue-green deployments.
- Maintain a migration plan and audit trail.

### 29.3. Never Migrate with `SELECT *` Directly Against Production

Full-container scans consume massive RUs and can trigger throttling. Migrations require:

- Partition-aware reading.
- Bounded concurrency and rate limiting.
- Stable cursors, continuation tokens, or a Change Feed strategy.
- Resumable checkpoints.
- Idempotent writes.
- Data comparison and reconciliation reports.
- Cost and timeout budgets.
- Isolation from live API SLAs.

## 30. Monitoring and Cost Control

### 30.1. Signals to Track

| Signal | Purpose |
|---|---|
| **Total Request Units** | Understand overall RU consumption |
| **Normalized RU Consumption** | Assess capacity saturation and hot partitions |
| **Throttled Requests / 429** | Detect quota/load saturation |
| **Server-side latency** | Measure service processing time |
| **Client-side latency/retries** | Separate network, SDK retry, and app latency |
| **Data Usage / Storage** | Track data and index storage growth |
| **Partition key statistics** (where supported) | Pinpoint hot logical partitions |
| **Availability / regional events** | Monitor DR and failover health |
| **Change Feed lag / projection delay** | Gauge freshness of read models and analytics |
| **Azure Activity Log** | Audit account, network, and throughput changes |
| **Data-plane diagnostics** | Inspect queries and operations per logging policy |

Do not assume every metric or diagnostic log is enabled by default or exported at the same granularity. Diagnostic settings and Log Analytics ingestion incur additional costs.

### 30.2. Analyzing Your Bill

Costs can come from:

- Provisioned RU/s or serverless RU consumption.
- Data storage and index storage.
- Replicated regions and multi-write capabilities per tier.
- Backup/restore per configured mode.
- Data transfer and private networking.
- Client compute, serverless processing, and ETL jobs.
- Azure Monitor / Log Analytics ingestion and retention.
- Migrations, backfills, and cross-partition queries.

Adding indexed paths can raise write RUs and storage. Assigning dedicated throughput per container increases baseline cost. Serverless can be inexpensive for tiny loads, yet costly for steady high traffic.

### 30.3. Forecasting Costs from Real Workloads

A practical approach:

1. Inventory request types and call frequencies per API endpoint.
2. Measure average and p95 RUs by operation, partition, and item size.
3. Multiply by peak requests/s to size capacity and headroom.
4. Inspect hourly/weekly traffic shapes to pick manual, autoscale, or serverless.
5. Factor in storage growth plus backup and region multipliers.
6. Account for log retention and data transfer.
7. Set budgets and alerts; periodically track **cost per completed order**.

Never optimize total RUs at the cost of business correctness, stale reads, or missed latency SLOs.

## 31. Troubleshooting Common Issues

| Symptom | Possible Cause | Resolution |
|---|---|---|
| **404 Not Found** on `readItem` | Wrong `id`/partition key or item missing | Verify both `id` and `tenantId` |
| **409 Conflict** on create | `id` already exists in logical partition, or unique key violation | Check idempotency and business keys |
| **412 Precondition Failed** | Stale ETag, concurrent writers | Bounded read-reconcile-retry loop |
| **429 Request Rate Too Large** | Insufficient RU/s, hot partition, costly query | Inspect RUs, partition stats, query/index |
| **403 Forbidden** | Missing/mis-scoped data-plane role or network policy | Check principal, Cosmos role, firewall |
| **401 Unauthorized** | Invalid token or key | Verify Entra credential, token scope/expiry |
| **Timeout / connection failure** | DNS, Private Endpoint, firewall, TLS, or routing | Check route, endpoint, certs, SDK |
| Very slow query | Cross-partition scan, index mismatch, paging | Inspect query metrics, partition filter, indexes |
| Cost spike after update | New indexes, higher writes/queries, autoscale peaks | Compare RU charges, storage, meters |
| One tenant throttled while total RUs remain | Hot logical partition | Adjust partition strategy/key |
| Duplicate data on retry | At-least-once delivery, missing unique event ID | Idempotent writes, unique keys, ledger |
| Lost updates | Unconditional `upsert`/`replace` | Use ETag, patch, or conditional updates |
| Item too large | Unbounded embedded history/arrays | Split into event items or Blob references |
| Broken queries after schema change | Readers not handling `schemaVersion` | Contract tests and migrations |
| Stale Change Feed projection | Consumer errors, checkpoint or idempotency bugs | Monitor lag; reconcile source and projection |
| SDK returns 403 despite Azure Contributor role | Confused management vs. data-plane roles | Grant Cosmos native data-plane RBAC at proper scope |

### 31.1. Debugging 404 When You Know the Order Exists

1. Verify the Cosmos account endpoint.
2. Verify the database and container names.
3. Verify the exact casing and format of **`id`**.
4. Verify the container's partition key path.
5. Verify the item's actual **`tenantId`** value.
6. Check whether the app is pointing to a different environment.
7. Run a controlled cross-partition query only during investigation if truly needed; never turn it into a production workaround.

### 31.2. Debugging 429

1. Record the operation type and request charge.
2. Inspect normalized RU consumption by container and partition.
3. Review index/query metrics and hot keys.
4. Check client retry policies and `Retry-After` handling.
5. Check the number of client instances and concurrency levels.
6. Review manual/autoscale capacity and usage peaks.
7. Optimize queries, partitioning, and caching before adjusting capacity.
8. Re-measure application p95/p99 latency, not just server-side 429 counts.

### 31.3. Debugging Concurrency Conflicts

1. Identify the item `id` and partition key.
2. Read the current ETag.
3. Inspect the concurrent writers and business rules.
4. Distinguish a retried duplicate command from two genuinely competing commands.
5. On 412, reconcile state rather than blindly overwriting.
6. If multiple items must change atomically, verify transaction boundaries.
7. Cross-check the audit ledger rather than looking only at the latest status.

## 32. Design Anti-Patterns

| Anti-Pattern | Why It Fails | How to Improve |
|---|---|---|
| Choosing **/status** as partition key | Low cardinality, hot partition | Use high-cardinality, query-aligned keys |
| Using **`SELECT *` cross-partition** for all reads | High latency and RU cost | Point reads, tenant filters, projections |
| Storing all history in one document | Oversized items, write contention | Separate items, Change Feed, or Blob |
| Creating a container per Java class | Throughput/cost overhead, hard transactions | Group by access patterns and ownership |
| Dumping every domain into one container | Conflicting TTL, indexing, and permissions | Split along real domain boundaries |
| Copying an RDBMS schema expecting cross-container JOINs | Excessive network calls, awkward queries | Embed snapshots or build read models |
| Using **upsert** for every write | Masks duplicates and lost updates | Use create, conditional replace, or patch |
| Omitting `schemaVersion` | Readers break on field changes | Version documents and add contract tests |
| Ignoring idempotency | Retries create duplicate orders/events | Stable business IDs and unique constraints |
| Hardcoding account keys in source | Credential leakage | Managed identity + data-plane RBAC |
| Assuming Azure Contributor can read data | Confuses control plane with data plane | Assign Cosmos native data roles |
| Using mutable status/region as partition key | Hard to relocate items | Stable keys + migration plan |
| Skipping real RU measurements | Mis-sized capacity, 429s, surprise bills | Log SDK request charges and load test |
| Treating multi-region as backup | Accidental deletes replicate too | Backup/restore, auditing, DR drills |
| Updating all orders when product prices change | Expensive, destroys historical snapshots | Keep live catalog separate from order snapshots |
| Ignoring tail writes during migration | Lost updates at cutover | Change Feed/outbox and reconciliation |

## 33. Pre-Production Checklist

- [ ] Confirmed workload fits **API for NoSQL**, without relying primarily on relational joins/transactions.
- [ ] Account region, availability, data residency, consistency, and billing mode explicitly chosen.
- [ ] Database and container boundaries derived from ownership and access patterns.
- [ ] Top reads, writes, and queries documented with input keys and SLOs.
- [ ] Partition key has high cardinality, even distribution, stability, and presence in hot queries.
- [ ] Logical partition limits and large-tenant behavior verified.
- [ ] Avoided low-cardinality status/date partition keys chosen solely for filtering.
- [ ] `id` + partition key passed into point-read APIs.
- [ ] JSON items include `schemaVersion`, validation, and enum/date/currency contracts.
- [ ] Bounded data embedded; large, shared, or independently mutable data referenced.
- [ ] Historical snapshots separated from live mutable profiles and catalogs.
- [ ] Document sizes and indexed paths kept under control.
- [ ] Unique keys, TTL, and indexing policies finalized prior to container creation.
- [ ] Cross-partition queries measured for RUs and budgeted.
- [ ] Manual, autoscale, or serverless mode load-tested and cost-estimated.
- [ ] ETag conditional updates and idempotency implemented.
- [ ] Transactional batches strictly respect single logical partition boundaries.
- [ ] No expectation that Cosmos DB transactions span Service Bus or SQL.
- [ ] Change Feed consumers implement idempotency, checkpoints, and reconciliation.
- [ ] Entra/managed identities and Cosmos native data-plane roles follow least privilege.
- [ ] Backend enforces tenant authorization rather than trusting arbitrary user-supplied `tenantId`.
- [ ] TLS, firewalls, Private Endpoints, and DNS aligned with network requirements.
- [ ] Backup/restore, DR, and failover drills validated against RPO/RTO.
- [ ] Monitoring covers RUs, 429s, latency, normalized consumption, storage size, and hot keys.
- [ ] CI/CD/IaC, canary rollouts, schema migrations, and rollback paths established.
- [ ] Cost dashboard tracks RUs, storage, replication, logs, and data transfer.
- [ ] Never delete lab or production resources without confirming ownership.

## 34. Hands-On Exercises

### Exercise 1: Inspecting Resources

In an approved lab:

1. Create an API for NoSQL account in one region.
2. Create the **commerce** database.
3. Create the **orders** container partitioned by **/tenantId**.
4. Inspect the endpoint, partition key, throughput, and indexing policy.
5. Identify which steps used the Azure ARM control plane versus the Cosmos data plane.

### Exercise 2: Point Reads and Cross-Partition Queries

1. Create three order items for **tenant-hcm** and two order items for **tenant-hn**.
2. Point read an order using `id` + partition key.
3. Attempt to read with the wrong partition key and record the status code.
4. Query all paid orders for `tenant-hcm`.
5. Query all paid orders across the entire container.
6. Measure request charges and explain the difference.

### Exercise 3: Choosing a Partition Key

A system has 2,000 tenants; the largest tenant generates 50% of total writes, and the API frequently looks up **`orderId`** without knowing `tenantId`.

Evaluate **/tenantId**, **/orderId**, hierarchical keys, and synthetic buckets. Determine the lookup path, query patterns, transactional needs, and migration cost.

### Exercise 4: Embed or Reference?

Design for the following:

- Each order has 5–20 lines.
- Each customer has 1,000–100,000 orders.
- Product catalog prices change daily.
- Order status history can grow indefinitely.
- Invoices must retain the price and details from purchase time.

Specify which fields to embed, reference, snapshot, or place in separate items/containers, and explain why.

### Exercise 5: Concurrency

Two workers update **order-481** concurrently:

1. Simulate both reading the same ETag.
2. Worker A succeeds with `replace`.
3. Worker B receives 412.
4. Implement a reconcile/retry policy capped at 3 attempts.
5. Explain why `upsert` could cause a lost update.

### Exercise 6: Transaction Boundaries

You need to update an Order status to `PAID` and record an `order-status` event.

- If both are in the same container and same `tenantId`, what should you use?
- If they are in different containers, what design is required?
- If a Service Bus message must also be sent, where do outbox and idempotency fit?

### Exercise 7: RUs and Cost

Assume a point read costs 4 RUs and a write costs 15 RUs, with peak traffic of 300 reads/s and 200 writes/s.

1. Calculate the preliminary RU/s requirement.
2. Add 20% headroom for load testing.
3. Explain why this calculation does not prevent 429s if a single partition runs hot.
4. Compare manual, autoscale, and serverless for this workload.

### Exercise 8: Security

A Java Function uses a managed identity to read and write orders.

1. Distinguish ARM Contributor from Cosmos DB Built-in Data Contributor.
2. Assign the role at the proper container scope.
3. Verify the 403 behavior before the role propagates.
4. Configure a Private Endpoint and DNS.
5. Explain why the API must still enforce tenant authorization.

### Exercise 9: Migration

An old container is partitioned by **/country**. Countries change over time and data is skewed.

Plan the new container, initial copy, Change Feed/tail updates, reconciliation, canary cutover, rollback, metrics, and cost controls.

### Exercise 10: Orders–Catalog–Inventory Case Study

Design three containers or a coherent model for these APIs:

~~~text
GET /tenants/{tenantId}/orders/{orderId}
GET /products/{productId}
POST /warehouses/{warehouseId}/inventory/{sku}/reserve
GET /tenants/{tenantId}/orders?status=PAID
GET /reports/revenue/monthly
~~~

Define item shapes, partition keys, unique identities, ETag/concurrency handling, and a reporting read model.

### Self-Check Questions

1. How do account, database, container, and item differ?
2. Can a single Cosmos DB account serve multiple databases?
3. Does a database always have its own throughput?
4. At which level is the partition key path defined?
5. How does a logical partition differ from a physical partition?
6. Is `id` automatically unique across the entire container?
7. Which values are needed for a point read?
8. Why is a low-cardinality `status` field a poor partition key?
9. Does a hierarchical partition key allow all items in a tenant to share one transaction?
10. When is embedding better than referencing?
11. Why should a product price snapshot live inside the order?
12. Does a flexible JSON schema mean no validation is needed?
13. Can Cosmos SQL `JOIN` arbitrarily join two containers?
14. Are cross-partition queries as cheap as point reads?
15. What does an RU measure?
16. Can 429 errors always be fixed by raising RU/s?
17. Does autoscale cost zero when idle?
18. Does default indexing add write overhead?
19. Are unique keys enforced across the entire account?
20. Do TTL and application `createdAtUtc` share the same semantics?
21. Does the Change Feed include all deletes in every mode?
22. Does Session consistency automatically guarantee atomic transactions?
23. Can a transactional batch write across two containers?
24. Which bug does ETag protect against?
25. Why do `create` and `upsert` have different semantics?
26. Why might an Azure Contributor still be unable to read items?
27. Does a Private Endpoint automatically grant database permissions?
28. Should changing the partition key for millions of items be done by editing fields in place?
29. Why does multi-region replication not replace backups?
30. Which RU, latency, and cost metrics should be monitored in production?

## 35. References

- [Azure Cosmos DB documentation — Microsoft Learn](https://learn.microsoft.com/azure/cosmos-db/)
- [Azure Cosmos DB for NoSQL overview](https://learn.microsoft.com/azure/cosmos-db/nosql/overview)
- [Resource model — accounts, databases, containers and items](https://learn.microsoft.com/azure/cosmos-db/resource-model)
- [Modeling and partitioning data](https://learn.microsoft.com/azure/cosmos-db/nosql/modeling-data)
- [Partitioning and horizontal scaling](https://learn.microsoft.com/azure/cosmos-db/partitioning-overview)
- [Hierarchical partition keys](https://learn.microsoft.com/azure/cosmos-db/hierarchical-partition-keys)
- [Request Units and throughput](https://learn.microsoft.com/azure/cosmos-db/request-units)
- [Provisioned throughput](https://learn.microsoft.com/azure/cosmos-db/set-throughput)
- [Autoscale throughput](https://learn.microsoft.com/azure/cosmos-db/provision-throughput-autoscale)
- [Indexing policies](https://learn.microsoft.com/azure/cosmos-db/index-policy)
- [Unique key constraints](https://learn.microsoft.com/azure/cosmos-db/unique-keys)
- [Time to live (TTL)](https://learn.microsoft.com/azure/cosmos-db/nosql/time-to-live)
- [Change Feed overview](https://learn.microsoft.com/azure/cosmos-db/change-feed)
- [Consistency levels](https://learn.microsoft.com/azure/cosmos-db/consistency-levels)
- [Transactional batch in Azure Cosmos DB for NoSQL](https://learn.microsoft.com/azure/cosmos-db/nosql/transactional-batch)
- [Optimistic concurrency control](https://learn.microsoft.com/azure/cosmos-db/nosql/database-transactions-optimistic-concurrency)
- [Azure Cosmos DB for NoSQL security and data-plane RBAC](https://learn.microsoft.com/azure/cosmos-db/nosql/security/how-to-grant-data-plane-role-based-access)
- [Azure Cosmos DB for NoSQL Java SDK v4](https://learn.microsoft.com/java/api/overview/azure/cosmos-readme)
- [Cosmos DB Java SDK performance tips](https://learn.microsoft.com/azure/cosmos-db/nosql/performance-tips-java-sdk-v4)
- [Back up and restore Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/online-backup-and-restore)
- [Azure Cosmos DB pricing](https://azure.microsoft.com/pricing/details/cosmos-db/autoscale-provisioned/)
