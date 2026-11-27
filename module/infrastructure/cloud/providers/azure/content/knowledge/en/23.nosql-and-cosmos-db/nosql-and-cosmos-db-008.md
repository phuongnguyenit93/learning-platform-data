# Transactions Within a Logical Partition and Transactional Batch

An e-commerce application needs to create an order and simultaneously write an **outbox** record to emit an `OrderPlaced` event. If the order write succeeds while the outbox write fails, downstream workers will never learn about the new order. If the outbox write succeeds while the order does not exist, event consumers will encounter inconsistent state. In **Azure Cosmos DB for NoSQL**, the safe design places documents requiring atomic updates inside the **same logical partition** of the **same container**, and executes them together via **Transactional Batch**.

The key point: Transactional Batch is not a “system-wide SQL transaction.” It only guarantees **all-or-nothing** execution for supported point operations **within a single logical partition key**. It does not turn all documents in a container or across multiple containers into a single ACID transaction.

This lesson belongs to the **NoSQL Data with Cosmos DB** chapter of the `CLOUD_PROVIDERS_AZURE` module. This module explores the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID through virtual networks, compute, storage, data, deployment, monitoring, security, and cost. Beyond writing a successful batch, this lesson covers partition key selection, business consistency design, RU management, connection security, and troubleshooting.

> The primary scope is **API for NoSQL (Azure Cosmos DB for NoSQL)**. Azure Cosmos DB offers other APIs and data models with different semantics and SDKs; never apply these Transactional Batch examples verbatim to MongoDB, Cassandra, Gremlin, or Table. SDKs, limits, and features can evolve by version and tier; commands and sample data are strictly for approved lab environments.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Distinguish **container, partition key path, partition key value, logical partition, and physical partition**.
2. Explain what **transactional scope** means in Cosmos DB for NoSQL.
3. Contrast single-logical-partition transactions against **cross-partition bulk**, independent requests, and distributed transactions.
4. Identify point operations commonly supported in Transactional Batch (**create, read, replace, upsert, delete, patch**) per SDK capabilities.
5. Build an atomic **Order + OutboxEvent** batch and inspect per-operation results.
6. Apply **ETag / optimistic concurrency** to prevent lost updates across concurrent clients.
7. Explain **snapshot isolation**, atomicity, rollback failures, and how one failing operation fails the entire batch.
8. Design partition keys so co-transacting documents share a scope without creating hot partitions.
9. Handle **409 Conflict, 412 Precondition Failed, 429 throttling, timeouts**, and retries with ambiguous outcomes.
10. Separate **ACID inside Cosmos DB** from **eventual consistency, multi-region replication**, and external side effects like Service Bus.
11. Apply the **transactional outbox + change feed processor** pattern with idempotent event consumption.
12. Observe request charges (RUs), latency, and diagnostic logs, and test failure and retry scenarios.
13. Contrast Transactional Batch against **JavaScript stored procedures** and **sagas/outbox**.
14. Complete a hands-on lab with two same-partition documents and a cross-partition negative test.

## 2. Context: One Order Needs Two Consistent Records

Suppose the API handles a request:

```json
{
  "tenantId": "tenant-a",
  "orderId": "ORD-1042",
  "customerId": "C-81",
  "amount": 250000,
  "currency": "VND"
}
```

Inside a single `orders` container, the system needs to write two items:

```json
{
  "id": "order:ORD-1042",
  "orderScope": "tenant-a|ORD-1042",
  "docType": "Order",
  "tenantId": "tenant-a",
  "orderId": "ORD-1042",
  "status": "Pending",
  "amount": 250000,
  "currency": "VND"
}
```

```json
{
  "id": "outbox:evt-1042-created",
  "orderScope": "tenant-a|ORD-1042",
  "docType": "OutboxEvent",
  "eventId": "evt-1042-created",
  "eventType": "OrderPlaced",
  "orderId": "ORD-1042",
  "publishState": "Pending"
}
```

Both carry `orderScope = "tenant-a|ORD-1042"`. When the container is configured with **partition key path `/orderScope`**, both items reside in the **same logical partition**.

Transaction goals:

- **Either both Order and OutboxEvent are created**, or **neither new item is created**.
- On an ID collision or ETag conflict, never leave behind an “order without an outbox” state.
- After commit, a separate processor publishes the event to Service Bus asynchronously; never confuse broker publishing with the database's ACID boundary.

### Why Not Issue Two Separate `CreateItemAsync` Calls?

```text
Create Order → succeeds
                  |
                  v
       Create OutboxEvent → times out / fails
                  |
                  v
          Order exists, yet
          outbox may be missing
```

Even with retries, idempotency and indeterminate commit states are far harder to manage. Transactional Batch eliminates the inconsistency window **between items in the same logical partition**, though it never extends transactions to external systems.

## 3. Distinguishing Account, Database, Container, and Partition

A typical hierarchy:

```text
Azure subscription / resource group
└── Azure Cosmos DB account (API for NoSQL)
    └── Database: commerce
        └── Container: orders
            ├── Logical partition "tenant-a|ORD-1042"
            │   ├── Order: order:ORD-1042
            │   └── OutboxEvent: outbox:evt-1042-created
            │
            ├── Logical partition "tenant-a|ORD-1043"
            │   ├── Order: order:ORD-1043
            │   └── OutboxEvent: outbox:evt-1043-created
            │
            └── Logical partition "tenant-b|ORD-9001"
                └── Order: order:ORD-9001
```

| Component | Role | Transaction Relationship |
|---|---|---|
| **Account** | Endpoint, regions, auth, consistency, service configuration | Not an arbitrary account-wide ACID boundary |
| **Database** | Groups containers; can share throughput where applicable | Does not create cross-container transactions |
| **Container** | Stores items; defines indexing, partition key path, throughput | A batch must target **one container** |
| **Partition key path** | Property path used for partitioning, e.g., `/orderScope` | Determines how items group into logical partitions |
| **Partition key value** | Concrete value on a document, e.g., `tenant-a|ORD-1042` | A batch must specify **one key value** |
| **Logical partition** | Set of items sharing the **same full partition key value** in a container | Unit of ACID transactions / Transactional Batch |
| **Physical partition** | Underlying storage and RU unit holding many logical partitions | **Not** a boundary allowing one batch to span multiple logical keys |

## 4. How Do Logical Partitions Differ from Physical Partitions?

Azure Cosmos DB distributes data to scale horizontally. **Logical partitions** are defined by the application and partition key; **physical partitions** are internal infrastructure units managed by the service.

```text
Container: orders, partition key /orderScope

Physical partition P0
  ├── Logical key tenant-a|ORD-1042
  │      ├── order document
  │      └── outbox document
  └── Logical key tenant-b|ORD-9001
         └── order document

Physical partition P1
  └── Logical key tenant-a|ORD-1043
         ├── order document
         └── outbox document
```

Suppose two logical keys happen to sit on the **same physical partition**. You **still cannot** use a Transactional Batch to write across both logical keys at once. The transaction boundary is **logical**, not physical.

The service can split or rebalance physical partitions as scale grows; applications must never depend on physical partition placement for transaction semantics. What you control is the **partition key path and value**.

### Two Items with the Same `id` but Different Keys?

In API for NoSQL, an item's point-lookup identity is the **pair `(partition key, id)`**. Two items can share the same `id` if their partition keys differ, per container semantics. Using `id` alone without the matching partition key fails to pinpoint an item or forces expensive cross-partition queries.

## 5. Why Does Cosmos DB Scope Transactions to a Logical Partition?

Distributing data across partitions unlocks throughput and scale, whereas coordinating multi-partition transactions adds complexity, latency, and concurrency/failure overhead.

Cosmos DB for NoSQL therefore provides **ACID transactions within one logical partition**, allowing operations on co-located items sharing a key to execute as one consistent unit.

When designing, ask:

1. Which documents must commit **together**?
2. Can they share a partition key while preserving balanced distribution and throughput?
3. Do any operations write to a **different container**?
4. Do any steps call **external services** such as a payment provider, SQL Database, or Service Bus?
5. Can the system accept eventual consistency across distinct aggregates?
6. Can sagas, outboxes, or idempotency handle steps outside the transaction scope?

A strong NoSQL schema is shaped around **access patterns and transaction boundaries**, rather than copying relational tables straight into JSON.

## 6. What Does ACID Mean Inside a Logical Partition?

The four ACID properties:

| Property | Meaning in Transactional Batch |
|---|---|
| **Atomicity** | All operations in the batch **commit together or roll back together**. |
| **Consistency** | The transaction preserves storage-enforced invariants, alongside business invariants enforced by code, ETags, and validation. |
| **Isolation** | Transactional operations within the logical partition execute under service-provided **snapshot isolation**; no partially committed intermediate state is visible. |
| **Durability** | Once committed per service contract, mutations persist under the configured durability, replication, and consistency guarantees. |

**ACID Consistency** is distinct from **Cosmos DB consistency levels** (Strong, Bounded Staleness, Session, Consistent Prefix, Eventual). Keep those two concepts separate.

For example:

- Transactional Batch creates Order and Outbox atomically within one partition.
- A client reading from another region/replica under a lag-tolerant consistency level might not yet see the commit.
- Never misinterpret that replication lag as a “partial commit” inside Cosmos DB.

### Atomicity Does Not Prove Business Correctness

If you write two items with an invalid monetary amount, both commit atomically, yet the data is **business-wrong**. Database transactions never replace schema validation, bounds checks, authorization, pricing math, or business rules.

## 7. Which Operations Does Transactional Batch Support?

In supported Azure Cosmos DB for NoSQL SDKs, **Transactional Batch** groups **point operations** targeting the same logical partition into a single request.

Common operations:

| Operation | Meaning | When to Use |
|---|---|---|
| **Create** | Insert a new item; duplicate ID in the partition fails with conflict | Creating a new Order and Outbox |
| **Read** | Read an item by ID/partition key inside the batch where SDK-supported | Verifying state within the batch |
| **Replace** | Replace an existing item, usually paired with an ETag | Transitioning Order status with version guard |
| **Upsert** | Insert if absent or overwrite if present per SDK semantics | Syncing a record where overwrites are acceptable |
| **Delete** | Delete an item by ID | Removing auxiliary records when allowed by policy |
| **Patch** | Modify specific paths/properties without sending the full document | Updating fields/counters where API-supported |

### What Is Not Allowed in an Arbitrary Batch

- Arbitrary cross-partition SQL queries.
- Transactions spanning two containers.
- Calling Service Bus or sending emails **inside the ACID commit**.
- Holding a transaction open across multiple HTTP requests.
- Running external code between batch operations.
- Two-phase prepare/commit distributed transactions across database regions.
- Automatically validating business invariants unless explicitly encoded in operations/ETags.

**If you need to evaluate a complex query and conditionally apply writes**, redesign the aggregate or evaluate stored procedures within the single logical partition and its runtime limits.

## 8. Limits of Transactional Batch

A Transactional Batch is designed for **short operation sets**. Commonly documented API for NoSQL limits include:

- Up to **100 operations** per batch.
- Maximum **batch payload size around 2 MB**.
- **Server-side execution timeout of a few seconds** (commonly cited as 5 seconds).

**Verify current SDK and service limits before implementation**; these figures are design guidelines, not fixed guarantees across every API, region, or version.

### What to Avoid

- Stuffing 20,000 invoice line items into one batch.
- Holding a transaction open while waiting on an HTTP payment gateway.
- Splitting a 150-operation transaction into two batches and claiming all 150 are atomic.
- Using Transactional Batch as a substitute for cross-partition bulk ingestion.
- Packing so many operations that batches routinely blow RU budgets or time out.

### Contrast with Bulk Mode

**Bulk** in the SDK optimizes throughput by dispatching many point operations concurrently, often across many logical partitions. However, **Bulk does not provide a single ACID transaction** spanning all those operations.

| Tool | Goal | Atomicity |
|---|---|---|
| Transactional Batch | Group operations sharing one key into one commit | Single logical partition |
| Bulk operations | Maximize throughput across many operations, including multi-partition | Per individual operation/transaction; not cross-key atomic |
| Stored procedure | Server-side JavaScript logic within a partition | Single logical partition where supported |
| Saga / outbox | Coordinate distributed workflows | No global ACID commit across services; uses state, retries, and compensation |

## 9. Choosing the Partition Key Around Aggregate Boundaries

This is the single most important decision when co-transacting multiple items.

Suppose each order is an **aggregate** containing `Order`, `PaymentAttempt` metadata, and `OutboxEvent`. You want atomic updates scoped to **one Order ID**.

Three options:

| Partition Key | Strengths | Weaknesses |
|---|---|---|
| `/tenantId` | Multiple items for the same tenant can share a transaction | Large tenants easily become hot logical partitions and hit size/throughput limits |
| `/orderId` | Items for the same order share a partition | Must guarantee `orderId` uniqueness across tenants; tenant-wide queries fan out |
| `/orderScope` = `tenantId|orderId` | Clear aggregate boundary, avoids cross-tenant ID collisions, spreads load by order | Listing all orders for a tenant fans out without a secondary query/index model |

For this lab, choose **`/orderScope`**.

### Avoid “Hot Partitions”

If every customer writes to `orderScope="global"`, one logical partition absorbs almost the entire workload. Even if the container has high total RU/s, a single logical partition / hot physical partition enforces its own ceiling—throttling batches while sibling partitions sit idle.

**Never pick an overly broad partition key just to expand transaction scope.** Keep atomic aggregates small, well-distributed, and aligned with frequent point reads and writes.

## 10. Single-Container vs. Multi-Container Design

A relational schema might suggest:

```text
Container Orders
Container OrderItems
Container OutboxEvents
```

However, if a Transactional Batch must update `Order` and `OutboxEvent` **in one ACID commit**, three separate containers **cannot meet that requirement**.

An alternative is **co-locating multiple document types in one container**:

```text
Container orders, partition key: /orderScope
  - docType=Order, id=order:<orderId>
  - docType=OutboxEvent, id=outbox:<eventId>
  - docType=OrderItem, id=item:<sku> (if needed)
```

Advantages:

- Items sharing `orderScope` share the same transaction boundary.
- Point reads and updates use `(id, partition key)`.
- Orders and outbox events commit atomically.
- Change feed captures new records for downstream processing.

Trade-offs:

- Query and indexing design changes when multiple doc types share a container.
- RU budgets and TTL policies must fit all co-located types.
- Querying all orders for a tenant fans out across partitions when keyed by order.
- Logical partition size, document counts, and write rates can still create hot keys.
- Not every business relationship belongs in one aggregate.

### What If Two Separate Containers Are Mandatory?

Use **sagas, outbox relays, change feed, reconciliation**, or a different data architecture. Never claim a cross-container transaction by issuing two sequential batches.

## 11. Partition Key Path, Value, and Immutability

When creating a container, you set the **partition key path**, e.g.:

```text
/orders container:
  partition key path = /orderScope
```

Every document must carry a matching value:

```json
{
  "id": "order:ORD-1042",
  "orderScope": "tenant-a|ORD-1042",
  "status": "Pending"
}
```

The batch is scoped to a partition key value:

```text
PartitionKey("tenant-a|ORD-1042")
```

**You cannot open a batch with partition key A and write an item carrying partition key B.** The SDK or server rejects out-of-scope operations.

### Never Use a Mutable Status Field as the Partition Key

If you choose `/status` as the partition key:

- Moving an order from `Pending` to `Paid` requires changing its partition key.
- An item's partition key cannot be updated in place via `Replace`/`Patch` like a regular property.
- Moving keys requires **create new + delete old**, which is not atomic across two logical partitions.
- Query routing and transaction boundaries break down.

Choose keys that remain **immutable over the aggregate's lifetime**, such as tenant or order IDs, rather than volatile business state.

## 12. Hierarchical Partition Keys: All Levels Are Required

In containers using **hierarchical partition keys (HPKs)**, a logical partition is defined by the **full key tuple**, not just the top-level prefix.

Example:

```text
Partition key paths:
  /tenantId
  /orderId

Full key:
  ("tenant-a", "ORD-1042")
```

Both Order and Outbox must share the **same `tenantId` AND `orderId`** to sit in the same logical partition. Two orders `("tenant-a", "ORD-1042")` and `("tenant-a", "ORD-1043")` do not share a transaction just because they belong to the same tenant.

In the .NET SDK, build the full key like:

```csharp
PartitionKey fullKey = new PartitionKeyBuilder()
    .Add("tenant-a")
    .Add("ORD-1042")
    .Build();
```

### When to Consider HPK?

- Multi-tenant apps with huge tenants needing finer distribution than `tenantId` alone.
- Query patterns that filter by tenant prefix while spreading leaf data across sub-keys.
- You want transaction scope per sub-aggregate under a tenant.
- You have planned logical/physical partition capacities and RU distribution.

Never treat HPK as a way to expand transactions from one order to **all orders in a tenant**. Transactional Batch still requires every operation to use the **same full logical partition key** per API rules.

## 13. Setting Up Lab Resources in the Azure Portal

Illustrative lab setup:

| Resource | Illustrative Value |
|---|---|
| Resource group | `rg-cosmos-lab` |
| Cosmos DB account | `cosmos-shop-lab-unique` |
| API | **Azure Cosmos DB for NoSQL** |
| Database | `commerce` |
| Container | `orders` |
| Partition key | `/orderScope` |
| Order scope | `tenant-a|ORD-1042` |
| Execution | Azure Cosmos DB .NET SDK with authorized identity |
| Data | 100% synthetic; zero real customer data |
| Verification | Both documents appear together or neither appears |

Steps:

1. Open the Azure Portal and confirm your tenant, subscription, and budget.
2. Create an **API for NoSQL** Cosmos DB account in an approved lab environment, selecting region and capacity per policy.
3. Choose an appropriate throughput mode (manual provisioned, autoscale, or serverless where supported); never assume all modes share identical billing.
4. Create database `commerce` and container `orders` with partition key path **`/orderScope`**.
5. Enable required authentication, RBAC, and network restrictions.
6. Assign the appropriate data-plane role to the identity running the SDK.
7. Confirm the endpoint, database/container names, and throughput settings.
8. Record configuration without storing account keys or tokens in repositories.
9. Use an approved local developer identity or runtime managed identity.
10. After completing the lab, clean up resources per permissions—never delete shared accounts.

**Changing the partition key path** once a container holds data is not a simple field rename; it normally requires migrating to a new container. Validate key choices before loading real workloads.

## 14. Azure CLI: Read-Only Metadata Inspection

Before running the SDK, verify the account and container:

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table

az cosmosdb show \
  --resource-group "<RESOURCE_GROUP>" \
  --name "<COSMOS_ACCOUNT_NAME>" \
  --query "{Name:name,Location:location,Endpoint:documentEndpoint}" \
  --output json

az cosmosdb sql database show \
  --resource-group "<RESOURCE_GROUP>" \
  --account-name "<COSMOS_ACCOUNT_NAME>" \
  --name "commerce" \
  --output json

az cosmosdb sql container show \
  --resource-group "<RESOURCE_GROUP>" \
  --account-name "<COSMOS_ACCOUNT_NAME>" \
  --database-name "commerce" \
  --name "orders" \
  --query "{Name:name,PartitionKey:resource.partitionKey}" \
  --output json
```

Output field paths can vary across ARM/CLI versions, so inspect the raw container metadata if a JSON `--query` returns empty. Check `az cosmosdb sql container show --help` if schemas differ.

### What the CLI Does Not Prove

These commands only verify **metadata and configuration**. They do not prove:

- Your data-plane identity can create items.
- A batch commits atomically.
- Your app sees read-your-writes across regions/consistencies.
- RUs suffice for peak load.
- The outbox processor successfully published to Service Bus.
- Logical partitions avoid hotspots or size limits.

Acceptance requires running batches on lab data and verifying postconditions with the exact partition key.

## 15. Preparing the .NET SDK and Identity

SDK examples use the **Azure Cosmos DB for NoSQL .NET SDK v3** alongside `Azure.Identity` to demonstrate Transactional Batch calls without requiring builds/tests inside this lesson repository.

In your own approved **lab** .NET project, add the packages:

```bash
dotnet add package Microsoft.Azure.Cosmos
dotnet add package Azure.Identity
```

Configure an environment variable with the **keyless endpoint URL**:

```text
COSMOS_ENDPOINT=https://cosmos-shop-lab-unique.documents.azure.com:443/
```

Ensure the identity holds an appropriate Cosmos DB **data-plane** role. Local runs can use a developer identity via `DefaultAzureCredential`; Azure deployments should prefer managed identity or Workload Identity.

### Control-Plane RBAC vs. Data-Plane RBAC

Permissions to create accounts/containers via Azure Resource Manager **do not automatically grant item read/write permissions** in the SDK. For Cosmos DB for NoSQL, check **Cosmos DB built-in data-plane roles** and supported scopes. Never hand out account keys to the whole team just to bypass a 403 error.

**Never print real credentials in test commands or logs.** Lab snippets below use only placeholder resource names and non-sensitive data.

## 16. .NET SDK Sample: Creating Order and Outbox in One Batch

Complete single-file C# example (matching .NET SDK), assuming container partition key `/orderScope`:

```csharp
using Azure.Identity;
using Microsoft.Azure.Cosmos;

string endpoint = Environment.GetEnvironmentVariable("COSMOS_ENDPOINT")
    ?? throw new InvalidOperationException("Missing COSMOS_ENDPOINT");

using var cosmosClient = new CosmosClient(
    endpoint,
    new DefaultAzureCredential());

Container container = cosmosClient.GetContainer("commerce", "orders");

string tenantId = "tenant-a";
string orderId = "ORD-1042";
string orderScope = $"{tenantId}|{orderId}";

var order = new
{
    id = $"order:{orderId}",
    orderScope,
    docType = "Order",
    tenantId,
    orderId,
    status = "Pending",
    amount = 250000,
    currency = "VND"
};

var outbox = new
{
    id = "outbox:evt-1042-created",
    orderScope,
    docType = "OutboxEvent",
    eventId = "evt-1042-created",
    eventType = "OrderPlaced",
    orderId,
    publishState = "Pending"
};

using TransactionalBatchResponse response = await container
    .CreateTransactionalBatch(new PartitionKey(orderScope))
    .CreateItem(order)
    .CreateItem(outbox)
    .ExecuteAsync();

Console.WriteLine($"Batch status: {response.StatusCode}");
Console.WriteLine($"Success: {response.IsSuccessStatusCode}");
Console.WriteLine($"Request charge: {response.RequestCharge} RU");

if (!response.IsSuccessStatusCode)
{
    // Do not assume any single operation succeeded independently.
    // Inspect operation results to locate the root cause of batch failure.
    for (int i = 0; i < response.Count; i++)
    {
        Console.WriteLine(
            $"Operation {i} status: {response[i].StatusCode}");
    }
    throw new InvalidOperationException(
        "Order + outbox transaction failed");
}

Console.WriteLine("Order and outbox committed atomically.");
```

**Key takeaways:**

1. `GetContainer("commerce", "orders")` targets **one container**.
2. `CreateTransactionalBatch(new PartitionKey(orderScope))` binds **one logical partition key** to the entire batch.
3. Both `order` and `outbox` carry the exact same `orderScope`.
4. `CreateItem(order)` and `CreateItem(outbox)` enqueue **two operations** in one transaction.
5. `ExecuteAsync()` submits the atomic transaction to Cosmos DB.
6. `IsSuccessStatusCode` indicates batch success—always check it, not merely that an HTTP response arrived.
7. `response[i].StatusCode` pinpoints which operation failed when the batch rolls back.
8. `RequestCharge` exposes the RU cost of the batch.
9. Success means **Order + Outbox committed inside the container**; it does not mean Service Bus has received the event yet.

Never log entire documents if they contain real user data. The console output above prints only statuses and RUs.

## 17. Negative Test: One Failing Operation Rolls Back the Entire Batch

Suppose the Order already exists in the logical partition. You attempt to create the same Order ID alongside a brand-new outbox event:

```text
Batch partition key = tenant-a|ORD-1042

Operation 0: CREATE id=order:ORD-1042   → ID conflict (409)
Operation 1: CREATE id=outbox:new-event → not committed

Expected: outbox:new-event must NOT exist
          just because it was the second operation.
```

When any operation fails, **the entire transaction rolls back**. Sibling operations typically report **`424 Failed Dependency`** in the batch response because they were aborted due to another operation's failure. Look for the **first operation carrying the root error code** rather than treating 424 as an independent item failure.

### Verification

1. Pick an outbox ID that does not exist yet.
2. Intentionally include a duplicate `order:ORD-1042` `CreateItem` in the batch.
3. Confirm the batch reports failure.
4. Read the existing Order: confirm it was not overwritten.
5. Point-read the new Outbox using the **same partition key**: confirm 404 Not Found.
6. Log status/error codes and RUs (never sensitive payloads).
7. Never delete production items to stage negative tests.

### Another Failure Case

If one item has `orderScope="tenant-a|ORD-1042"` and another has `orderScope="tenant-a|ORD-1043"`, the batch violates the single logical partition requirement. The SDK/server rejects the mismatch as a bad request. **There is no mode that splits a Transactional Batch into two independent transactions while preserving end-to-end atomicity.**

## 18. ETags and Optimistic Concurrency Control

Two workers updating an Order concurrently can cause a **lost update**:

```text
T0: Order.status = Pending, version = V1

Worker A reads V1
Worker B reads V1

Worker A changes status to Paid
Worker B changes status to Cancelled

Without version checks:
  the later write silently overwrites the earlier write.
```

Cosmos DB attaches an **ETag** to each item; clients pass **`If-Match` ETag** on replace, delete, or patch calls where supported. If the ETag changed in the meantime, the operation fails with **`412 Precondition Failed`** instead of blindly overwriting.

### Why Are ETags Valuable Inside a Batch?

You can:

1. Point-read the Order to obtain its document and ETag.
2. Compute the next state from what was read.
3. Build a batch containing **Replace Order with `IfMatchEtag`** plus **Create OutboxEvent**.
4. If the ETag no longer matches, **the entire batch rolls back**, ensuring no outbox event is emitted for an uncommitted state transition.

## 19. .NET SDK Sample: Replace + Outbox with `If-Match`

The snippet below demonstrates optimistic concurrency when transitioning an Order to `Paid`. Run only against an existing lab container.

```csharp
using Azure.Identity;
using Microsoft.Azure.Cosmos;

using var client = new CosmosClient(
    Environment.GetEnvironmentVariable("COSMOS_ENDPOINT")!,
    new DefaultAzureCredential());

Container container = client.GetContainer("commerce", "orders");
string scope = "tenant-a|ORD-1042";
string orderDocId = "order:ORD-1042";
var pk = new PartitionKey(scope);

// OrderDoc at the bottom defines the matching JSON fields.
ItemResponse<OrderDoc> current = await container.ReadItemAsync<OrderDoc>(
    id: orderDocId,
    partitionKey: pk);

if (current.Resource.status != "Pending")
{
    throw new InvalidOperationException(
        "Order must be Pending before marking Paid.");
}

current.Resource.status = "Paid";
current.Resource.updatedAtUtc = DateTimeOffset.UtcNow.ToString("O");

var evt = new
{
    id = "outbox:evt-1042-paid",
    orderScope = scope,
    docType = "OutboxEvent",
    eventId = "evt-1042-paid",
    eventType = "OrderPaid",
    orderId = "ORD-1042",
    publishState = "Pending"
};

using TransactionalBatchResponse result = await container
    .CreateTransactionalBatch(pk)
    .ReplaceItem(
        orderDocId,
        current.Resource,
        new TransactionalBatchItemRequestOptions
        {
            IfMatchEtag = current.ETag
        })
    .CreateItem(evt)
    .ExecuteAsync();

if (!result.IsSuccessStatusCode)
{
    Console.WriteLine($"Batch failed: {result.StatusCode}");
    for (int i = 0; i < result.Count; i++)
    {
        Console.WriteLine($"Op {i}: {result[i].StatusCode}");
    }
    // On ETag conflict: re-read current state and decide,
    // never overwrite blindly or emit stale events.
}
else
{
    Console.WriteLine("OrderPaid + outbox committed.");
}

public sealed class OrderDoc
{
    public string id { get; set; } = "";
    public string orderScope { get; set; } = "";
    public string docType { get; set; } = "Order";
    public string status { get; set; } = "";
    public string updatedAtUtc { get; set; } = "";
}
```

> This example illustrates Cosmos DB .NET SDK v3 APIs using a minimal type. When real applications store additional properties on an Order, preserve all fields and serialization rules during `Replace`; otherwise replacing the entire document drops properties missing from the C# class. When only updating a few fields, evaluate `Patch` with appropriate preconditions per SDK version.

### What Happens When Another Worker Wins the Race?

If Worker A commits first, the Order's ETag advances from `V1` to `V2`. Worker B's batch carrying `IfMatchEtag = V1` is rejected. Worker B must **re-read the latest state** and re-evaluate business rules—never drop `IfMatchEtag` to force an overwrite.

### What If You Skip ETags?

Transactional Batch still executes operations **inside the batch** atomically, yet it cannot protect business decisions derived from **stale reads taken before the batch**. If the item can change between `ReadItemAsync` and `ExecuteAsync`, you need optimistic concurrency or an equivalent conditional guard.

## 20. `Patch` Inside a Batch to Avoid Full Replaces

**Patch** avoids sending the entire document when modifying only a couple of paths, depending on SDK version and supported patch operations.

Idea:

```text
Batch(pk = "tenant-a|ORD-1042"):
  PATCH order:ORD-1042
    set /status = "Paid"
    set /updatedAtUtc = <time>
  CREATE outbox:evt-1042-paid
```

Advantages:

- Avoids transmitting the full document just to mutate two properties.
- Reduces risk of partial C# models dropping unmapped fields on replace.
- Combines cleanly with other operations in the same logical partition.

However, **Patch does not automatically enforce valid state transitions**. Supply preconditions—such as verifying `status == "Pending"` via a conditional filter predicate or `IfMatchEtag` where supported by the SDK—otherwise a delayed payment callback could overwrite a `Cancelled` order back to `Paid`.

**Never assume Patch is always cheaper or conflict-free.** Measure actual RUs, operation semantics, and indexing impact.

## 21. `Upsert`: Convenient, Yet Risky for Event Idempotency

Upsert is convenient for “create or overwrite” semantics by ID. However, using Upsert casually for Orders or Outbox records can mask duplicate deliveries.

Suppose event `evt-1042-created` is processed twice:

- With **`CreateItem`** and a deterministic ID, the second attempt returns **`409 Conflict`**—a clear signal to check whether the operation already completed.
- With **`UpsertItem`**, the second attempt overwrites the existing item, mutating timestamps/metadata and triggering unwanted change-feed activity.

Therefore:

- Prefer **`Create` + deterministic idempotency ID** when an event must only be recorded once.
- Use `Upsert` only when overwrites are explicitly part of the business contract.
- Never replace ETag conditional updates with `upsert` on critical financial states.
- On 409, verify the existing item matches the **same business payload and operation ID**; never blindly treat every 409 as “already succeeded.”

## 22. Every Document in a Batch Must Share the Full Partition Key

A common bug:

```json
{
  "id": "order:ORD-1042",
  "orderScope": "tenant-a|ORD-1042"
}
```

and:

```json
{
  "id": "outbox:evt-1042-created",
  "orderScope": "tenant-a|ORD-1043"
}
```

Even though both share `tenantId=tenant-a` in another property, **their full partition keys do not match**.

### Pre-`ExecuteAsync` Checklist

1. Is `Container` pointing to the intended container?
2. Is the actual partition key path `/orderScope`?
3. Does every document carry `orderScope` as a matching string?
4. Are values **byte-for-byte identical** (including casing, whitespace, encoding)?
5. Was the batch opened with the exact `new PartitionKey(scope)`?
6. Are document IDs distinct yet unique **within that partition**?
7. Do any operations touch another container or external REST API?
8. Are operation count and payload size within service limits?
9. Does the SDK receive the right partition key shape (flat vs. hierarchical)?
10. Are secrets and PII stripped from logs?

**Cosmos DB never auto-corrects a mismatched partition key** by fetching an item from another partition into the transaction.

## 23. RU/s and the Cost of Transactional Batch

Azure Cosmos DB uses **Request Units (RUs)** to express the relative resource cost of data operations based on item size, indexing, query/workload shape, and other factors. Throughput is provisioned in **RU/s** under provisioned/autoscale models or billed per request under serverless SKUs.

### Factors That Raise RUs

- More `Create`/`Replace`/`Delete`/`Patch` operations per batch.
- Larger items and more indexed properties.
- Index updates triggered by modified fields.
- High write rates concentrated on a single partition key.
- Failed batches being retried repeatedly.
- Pre-batch point reads, ETag checks, and validation queries.
- Stored procedures, change feed, or downstream consumers running alongside.

**One batch HTTP call does not mean “1 RU.”** The server bills RUs proportional to actual work performed and returns the exact `RequestCharge`.

### Illustrative Planning Example

Suppose an Order + Outbox batch averages **12 RUs** in lab testing. At 200 requests/second:

```text
Write demand ≈ 200 batches/s × 12 RU/batch
             ≈ 2,400 RU/s
```

This is **not a fixed RU rate** for every two-item batch. Always measure `RequestCharge` on real payloads and indexing policies, factoring in retries, read traffic, change feed, and partition spread.

### 429 Throttling

When demand exceeds available capacity, Cosmos DB returns **429 Too Many Requests** with retry hints. The SDK retries within configured policies, yet you must:

- Track 429 rates and true end-to-end latency, not just final failures.
- Set bounded retry budgets and backoff.
- Check for **hot single partition keys** before blindly raising total RUs.
- Tune batch sizes, write rates, and indexing policies.
- Prevent thousands of clients from storming retries simultaneously.
- Monitor cost increases when raising RU/s or autoscale ceilings.

## 24. Hot Logical Partitions and Scale Limits

Picking a partition key merely to bundle “everything for a tenant” can turn large tenants into bottlenecks.

```text
Container throughput is ample overall

Logical key "tenant-enterprise"
  90% writes + 90% transactions → hotspot

Logical keys tenant-small-1, tenant-small-2
  minimal traffic
```

The system can throttle `tenant-enterprise` even while sibling partitions sit idle. Meanwhile, logical partitions remain subject to documented storage caps and HPK/large-partition rules.

### Reducing Risk

1. Define a **narrower aggregate boundary**, such as `tenant + order` instead of `tenant`.
2. Rank top partition keys by RUs, storage, and request volume.
3. Offload historical or analytical data from hot transactional containers where appropriate.
4. Use HPKs when access patterns align and full-tuple transaction rules are well understood.
5. If an aggregate grows too large to stay atomic in one logical partition, adopt sagas or redesign domain boundaries.
6. Never scatter an aggregate that needs atomicity across random keys without a consistency strategy.

**There is no universally “best” partition key:** you must balance transaction scope, point-read efficiency, query fan-out, capacity, and tenant isolation.

## 25. Snapshot Isolation and Consistent Reads

Transactional Batch executes under Cosmos DB's transactional isolation within a logical partition. When multiple operations create or update co-located items, the batch preserves all-or-nothing atomicity and snapshot semantics per service guarantees.

Avoid two misconceptions:

1. **A cross-partition query run after a batch** does not create an account-wide snapshot. Other partitions may mutate concurrently.
2. **A consumer reading from another region** may see consistency or replication lag; never assume an open snapshot spans all regions.

### Business Read Example

If an API needs to return “Order + Outbox” after creation:

- Both items commit atomically when the batch succeeds.
- Reading within the **same partition** under matching consistency and session context verifies the committed state.
- Do not issue two weak-consistency cross-region reads and mistake replication lag for a partial commit.
- To read **one aggregate** in the same partition, use point reads or partition-scoped queries with suitable consistency.

### Separating Database Consistency from Transactions

Cosmos DB supports consistency levels such as **Strong, Bounded Staleness, Session, Consistent Prefix, and Eventual**. Choosing a level affects latency, availability, and freshness, yet **never changes the rule that Transactional Batch scopes to one logical partition**.

If your app requires **read-your-writes** after a batch, manage session tokens, region routing, and `CosmosClient` lifetimes properly instead of assuming every reader in every region observes the commit instantaneously.

## 26. Multi-Region Writes: Transactions Still Are Not Global ACID

A Cosmos DB account can span multiple read regions and, in supported setups, multiple write regions—which complicates consistency and conflict resolution.

Keep these distinctions clear:

- Transactional Batch ACID scope remains bound to **one logical partition**, not a distributed transaction across all regions.
- Multi-region replication and consistency levels govern **when mutations become visible in other regions**.
- Under multi-write, you must understand **conflict resolution**, write collisions, and service semantics.
- Never assume two writers in two regions mutating one business aggregate obey global serialization or uniqueness constraints unless your architecture enforces it.
- Design idempotency keys, bounded retries, regional failover, and reconciliation carefully.
- Client timeouts during regional failover can produce ambiguous outcomes even when a batch committed in one region.

For financial transactions, simply “enabling multi-region” never proves an exactly-once business outcome. Explicitly design write topology, aggregate ownership, and conflict handling.

## 27. Transactional Outbox: Bridging Cosmos DB ACID to Service Bus

This is a flagship use case for Transactional Batch:

```text
Orders API
   |
   v
Transactional Batch in 1 logical partition
   +-- CREATE/UPDATE Order
   +-- CREATE OutboxEvent
   |
   v
Cosmos DB COMMIT succeeds
   |
   v
Change Feed Processor / Outbox relay
   |
   +-- Reads new/updated OutboxEvent
   +-- Publishes to Azure Service Bus / Event Hubs
   +-- Records status/marker per design
   |
   v
Downstream worker
   +-- Idempotent event processing
   +-- Persists business result
```

**Writing Order + Outbox** sits inside ACID. **Publishing to Service Bus** sits outside the Cosmos DB transaction, so the system must tolerate and handle:

1. Cosmos DB commits, yet the relay has not run yet.
2. The relay publishes the message and crashes before marking it sent.
3. The relay republishes the same event upon restart or lease rebalance.
4. A Service Bus receiver processes the message and times out before calling `Complete`.
5. A downstream database processes the event cleanly and later sees a duplicate delivery.
6. The outbox grows or processor lag rises, delaying event delivery.

### Role of the Change Feed

The change feed exposes item mutations in a container to consumers using a cursor/checkpoint model—making it the standard way to drive an outbox relay without polling the whole container.

However:

- Consumers can **redeliver** events; idempotency is mandatory.
- Filter for `docType = "OutboxEvent"` inside the processor/application when multiple doc types share the container.
- Behavior for **deletes, TTL expirations, and intermediate updates** depends on the active change feed mode and features; never assume every change emits like a full audit log.
- Processor checkpoints and leases are separate from the Order + Outbox ACID commit.
- Change feed processing can lag or stall; monitor lag and alert on it.
- Keep unnecessary secrets and sensitive records out of outbox payloads.

## 28. Outbox Relays and Duplicate Publishing

Consider `OutboxEvent` `evt-1042-created`:

```text
T0: OutboxEvent committed
T1: Relay publishes to Service Bus successfully
T2: Relay crashes before writing publishState=Sent
T3: Relay restarts
T4: Relay republishes the event with the same eventId
```

A Cosmos DB transaction **cannot be atomic** with a Service Bus publish. Combine these safeguards:

- **Deterministic Message ID** (`eventId`) assigned when creating the outbox record.
- **Inbox / idempotent handler** on the consumer, such as a unique constraint on `eventId`.
- Relay retries with backoff and dead-letter/quarantine policies.
- Event status tracking and reconciliation when relays lag.
- Broker duplicate detection where supported, without relying on it as a substitute for consumer idempotency.
- Alerts on pending event counts, oldest pending age, and retry counts.
- Never mark an outbox record `Sent` **before** broker acknowledgment if doing so risks silent event loss.

### Note on `Sent` Status Updates and the Change Feed

If the same outbox item is updated multiple times during dispatch, the change feed may emit the updated version; processors must avoid **re-triggering themselves** on events already marked `Sent`. Some designs keep outbox documents immutable and track progress in external leases/checkpoints or separate state records—validate this against your actual change feed mode and retry semantics.

## 29. Idempotency When Clients Retry the Same Batch

An API request can time out right after Cosmos DB **commits**, leaving the client unaware of the outcome:

```text
Client → ExecuteAsync(Order + Outbox)
           |
       Cosmos DB COMMIT
           |
       Response lost to network timeout
           |
       Client retries
```

When using two `Create` operations with **deterministic IDs**, a post-commit retry returns 409 because the items already exist. Yet never blindly map every 409 to HTTP 200/202:

1. Point-read the items using the exact partition key.
2. Compare the stored business operation/`requestId` against the retried request.
3. Verify the critical payload matches (not just the ID).
4. If both Order and Outbox exist in the expected state, return the idempotent “accepted” response per API contract.
5. If the ID collides with a different payload, treat it as an **idempotency key reuse error** and return Conflict.
6. If network errors prevent verification, return an indeterminate status and rely on status polling / reconciliation.

### Never Generate Random IDs on Retry

Calling `Guid.NewGuid()` on every retry creates a brand-new `eventId`, spawning duplicate outbox records for the same order operation. Derive IDs once from the incoming business operation or validate a caller-supplied idempotency key.

## 30. Handling Per-Operation Batch Errors

Common status codes:

| Code / Status | Likely Meaning | Investigation / Response |
|---|---|---|
| **2xx** | Batch accepted and committed per SDK | Inspect entire batch and emit metrics/diagnostics |
| **400 Bad Request** | Partition key mismatch, malformed op, or invalid config | Check paths, types, IDs, and payload |
| **401 / 403** | Invalid credentials, missing data-plane role, or network/policy block | Check Entra identity, role assignments, keys/tokens, and networking |
| **404 Not Found** | `Replace`/`Delete`/`Read` targeted a missing item or wrong PK | Point-read with the exact key; never guess global IDs |
| **409 Conflict** | Duplicate `(id, partition key)` on `Create` or unique constraint violation | Verify idempotency against the existing record |
| **412 Precondition Failed** | `ETag`/`IfMatch` or optimistic concurrency check failed | Re-read state and evaluate valid transitions |
| **424 Failed Dependency** | Operation aborted because another operation in the batch failed | Locate the operation carrying the root error code |
| **429 Too Many Requests** | RU / capacity throttled | Retry with backoff; inspect hot partitions and RUs |
| **413 Request Entity Too Large** or batch limit | Batch payload exceeds limits | Split aggregates cleanly; never hide broken atomicity |
| **Timeout / network error** | Unknown whether server received or committed request | Read-after-error and idempotency; avoid blind retries |
| **5xx / 503** | Transient service or connectivity issue | Check Azure status, diagnostics, retry policy, and RTO |

### Batch Failure Triage Sequence

1. Log operation count, **sanitized** partition key, timing, and correlation/`ActivityId`.
2. Inspect batch-level status, request charge, and diagnostics.
3. Loop through per-operation statuses to isolate the **root** error code.
4. Verify the container's partition key path, key value, and item IDs.
5. On 409/412, point-read and compare state and idempotency keys.
6. On 429, check RUs, throttling, and hot partitions.
7. On timeout, never assume the batch rolled back; verify state once connectivity returns.
8. Retry only when semantically safe and within retry budgets.
9. Alert on sustained failures or repeated failures for the same aggregate.
10. Keep logs minimal without printing sensitive payloads.

## 31. Key Distinction: Returned Errors vs. Transport Failures

If Cosmos DB returns a **batch response** with a failure status, you know the server evaluated the request per API contract and rolled back the batch, with per-operation diagnostics intact.

If the **connection drops before the response reaches the client**, the application cannot know whether the server committed or not. That is an **ambiguous outcome**, fundamentally different from an explicit rollback response.

For example:

- Returning 409 confirms a `Create` collided; inspect the whole batch.
- Returning 412 confirms an optimistic concurrency check failed.
- Losing the connection after a server-side commit leaves the client seeing a timeout even though the transaction succeeded.

**Never equate a network timeout with “the transaction definitely failed.”** Retry logic must combine state re-reads with idempotency.

## 32. Comparing Transactional Batch and JavaScript Stored Procedures

Azure Cosmos DB for NoSQL also supports **JavaScript stored procedures** for transactions within one logical partition under specific runtime semantics and limits.

| Criterion | Transactional Batch | Stored Procedure |
|---|---|---|
| Where logic lives | Client SDK (C#/.NET, Java, supported languages) | JavaScript executing inside the service |
| Primary operations | SDK-supported point operations | JavaScript logic using scoped context/collection APIs |
| ACID scope | One logical partition in one container | One logical partition in one container |
| Control flow between ops | Client constructs operations upfront; pairs with ETags/conditions | Can branch dynamically inside the stored procedure per API |
| Deployment | Application SDK code | Must deploy and manage stored procedure resources |
| Latency | Single batch request avoiding multiple round-trips | Server-side execution, subject to runtime/code limits |
| Maintainability | Easy to test in app codebase and CI | Requires managing server-side JS and compatibility |
| Cross-partition | No | No |

### Which to Choose?

- **Transactional Batch:** Clear sets of point writes with minimal server-side branching, kept in application code alongside optimistic concurrency.
- **Stored procedure:** When dynamic intra-partition transactional logic cannot be expressed easily as a client batch and fits runtime limits.
- **Saga / outbox:** When workflows span multiple keys, containers, or services.

**Never treat stored procedures as a shortcut to cross-partition ACID.** Calling a stored procedure also requires supplying a single matching partition key.

## 33. Cross-Partition Transactions: Use Sagas Instead of ACID Illusions

Suppose you transfer 100 loyalty points from Account A to Account B residing in two different logical partitions:

```text
Partition A: LoyaltyAccount A
Partition B: LoyaltyAccount B
```

You **cannot** use a single Transactional Batch to atomically update both A and B across different keys.

One design approach is a **saga / process manager**:

```text
Transfer request + operationId
        |
        v
Saga state = Pending
        |
        +-- Step 1: reserve/deduct A (idempotent)
        |
        +-- Step 2: credit B (idempotent)
        |
        +-- Success → saga Completed
        |
        +-- Failure → retry / compensating action
                         |
                         +-- reconcile / alert
```

Sagas introduce real complexity:

- **Intermediate states** and eventual consistency.
- Compensation is not an instantaneous ACID rollback.
- External side effects like emails or bank transfers may be irreversible.
- Requires timeouts, retries, idempotency, and audit trails.
- Must prevent double-spending or double-deduction under concurrency.
- Business owners must accept processing windows and `Pending` states.

If the domain truly requires strict multi-record atomicity system-wide, evaluate whether the Cosmos DB NoSQL data model and partition boundaries fit, or whether a relational ledger/transactional database is more appropriate.

## 34. Security: Identity and Least Privilege

An app creating `Order + Outbox` needs item read/write permissions in Cosmos DB, not permissions to reconfigure accounts, alter throughput, or delete containers.

### Security Layers

| Layer | Purpose | Common Mistake |
|---|---|---|
| Azure Resource Manager RBAC | Create/modify accounts, databases, containers, networking | Assuming `Contributor` automatically grants data-plane operations |
| Cosmos DB for NoSQL data-plane RBAC | Read/write items at scoped container/database levels | Issuing account-wide master keys when container read/write suffices |
| Network restrictions | Public/private endpoints, VNets, firewalls, TLS | Opening public Internet access to mask a 403 permission error |
| Application authorization | Tenant/order ownership checks on callers | Treating the partition key as an access-control boundary |
| Secrets / keys | Account keys, managed identities, credentials | Committing keys to Git or printing them in terminal logs |

### A Partition Key Is Not a Security Boundary

Knowing `tenant-a|ORD-1042` does not mean a caller is authorized to mutate that Order. Cosmos DB transaction scope **does not enforce tenant authorization** inside application code. Always:

1. Authenticate the client/user.
2. Verify the caller owns or has access to the tenant/order.
3. Scope data-plane identities to the narrowest container role.
4. Never trust an unvalidated client-supplied partition key for another tenant.
5. Audit sensitive state transitions.
6. Protect PII, encryption, backups, and key rotation per policy.

### Managed Identity

On AKS, Azure Functions, Container Apps, or VMs, prefer managed identity / Workload Identity via `Azure.Identity`. Enabling an identity does not grant data-plane access automatically—role assignments and network rules must also match.

## 35. Networking and Multi-Region: Connection Failures Are Not Transaction Bugs

A batch can fail or time out because of:

- Misconfigured Private Endpoint / Private DNS resolution.
- NSGs, Azure Firewall, UDRs, or outbound rules blocking traffic.
- TLS certificate errors or wrong endpoint URLs.
- Incorrect regional endpoint routing.
- Misconfigured SDK retry policies or preferred regions.
- Transient Cosmos DB service disruptions.
- Exhausted RU capacity or a hot partition.

### Triage Workflow

1. Verify `COSMOS_ENDPOINT` targets the exact API for NoSQL account.
2. Test DNS and TLS from the **live runtime**, not only a developer laptop.
3. Confirm the principal holds the Cosmos DB data-plane role.
4. Run a read-only point-read probe in a lab to isolate data-plane connectivity.
5. Inspect `ActivityId` and diagnostics to separate transport failures from server status codes.
6. On 429, focus on RUs and hot partitions; on 403, focus on permissions and firewalls.
7. Never enable verbose generic HTTP logging that dumps keys or bearer tokens.
8. During region switches, account for consistency, session tokens, and failover semantics.

**An account showing “Online” in the Azure Portal does not prove your app can execute transactions.** Always verify with controlled data-plane probes.

## 36. Observability: Tracking Batches Properly

Production batches should emit:

- Business **`operationId` / `requestId`**.
- **Sanitized partition key fingerprint** (avoiding raw PII in logs).
- **Batch operation count** and operation types.
- **Batch-level status** and failing operation index.
- **`RequestCharge` (RUs)**.
- End-to-end **latency** and retry counts.
- **Cosmos DB `ActivityId` / diagnostics** when exposed by the SDK.
- **429 rate**, hot-partition metrics, and throughput utilization.
- **Outbox pending age / change feed lag** when using an outbox.
- **Downstream publish/processing outcomes**, not merely batch commits.
- **Conflict rates (409/412)** and optimistic concurrency failure rates.

### Minimal Dashboard

| Metric | Why It Matters |
|---|---|
| Batch success vs. failure count over time | Health of the write path |
| P50/P95/P99 batch latency | API responsiveness |
| RUs per successful order | Cost tracking and indexing regression detection |
| 429 rate + retry delay | Capacity saturation or hot keys |
| 409 / 412 conflict rate | Retries, race conditions, duplicate requests |
| Outbox pending count / oldest age | Stalled relay detection |
| Change feed processor lag / lease health | Ability to keep up with committed events |
| Service Bus publish/consume failures | End-to-end business flow reliability |

### Azure Monitor and Diagnostics

Depending on configuration, Azure Monitor exposes Cosmos DB metrics and diagnostic logs. Data-plane logs can stream to Log Analytics via supported categories/tables. Never assume “zero errors” simply because diagnostic settings are off or ingestion lags.

Avoid logging full document bodies containing PII, payment metadata, or sensitive internal identifiers. Emit **policy-compliant sanitized IDs**, status codes, and timings sufficient for investigation.

## 37. Runbook: Batch 409 Caused by Client Retries

**Symptom:** A customer clicks “Place Order,” and the API times out. Clicking again triggers `409 Conflict` from the transaction.

### Investigation

1. Capture `requestId`, `orderId`, and UTC timestamp.
2. Inspect batch-level and per-operation statuses.
3. Confirm the target Cosmos account, container, and partition key.
4. Point-read `Order` by key and ID.
5. Point-read `OutboxEvent` using the same key.
6. Compare stored payload and business operation ID against the retried request.
7. Verify Order and Outbox states are consistent.
8. Never mint a fresh outbox event ID just to dodge a 409.

### Remediation

- If the prior batch **committed with identical content**, return the idempotent success result per API contract.
- If the ID collided with a different payload, return a business conflict without overwriting.
- If the transaction truly never committed, retry safely with deterministic IDs.
- If status remains indeterminate due to network errors, return a queryable status and trigger reconciliation.
- Monitor abnormal 409 spikes caused by client retry storms.

**Lesson:** A 409 can signal a post-commit retry, yet you must **verify state** rather than blindly treating every 409 as success.

## 38. Runbook: 412 ETag and State Transition Contention

**Symptom:** Workers A and B concurrently update a `Pending` Order to `Paid` and `Cancelled`. One batch fails with 412.

### Investigation

1. Re-read the Order and its latest ETag.
2. Inspect current status and business operation IDs.
3. Determine valid transitions under the state machine.
4. Never strip `If-Match` to force a `Replace` overwrite.
5. If another worker already processed the exact same operation, return the idempotent result.
6. If the losing worker's transition is now invalid, route to conflict handling/alerts per business rules.

### Remediation

- Retry only after **re-reading and recomputing**—never resubmit stale bodies.
- When two transitions are mutually exclusive, allow only one winner.
- Create the `OutboxEvent` **in the same batch** as the committed transition.
- Ensure no event is ever emitted for a transition rolled back by a 412.
- Track conflict rates under high concurrency.

**Lesson:** Atomicity prevents partial commits, while ETags prevent **lost updates across concurrent transactions**.

## 39. Runbook: 429s Despite Apparent Headroom in Total RU/s

**Symptom:** An API has 20,000 RU/s provisioned and aggregate utilization looks moderate, yet a group of Orders repeatedly receives 429s.

### Hypotheses

- Writes concentrate on one logical partition key (hot key).
- Indexing or update costs spiked for an item type.
- One physical partition is saturated while others sit underutilized.
- Batches are oversized or trapped in retry storms.
- An outbox relay repeatedly hammers the same key.

### Remediation

1. Inspect 429 diagnostics and partition-level statistics where available.
2. Identify top keys by RUs and write rate.
3. Audit payload sizes, operations per batch, and indexing.
4. Throttle concurrent retries and apply backoff.
5. Reduce write frequency, trim batch payloads, and optimize event cadence.
6. If the key design is flawed, plan a **data migration to a new container**—never assume an update command changes the partition key path in place.
7. Increase throughput if capacity is genuinely the bottleneck and budget permits.
8. Re-test latency, 429s, and business consistency.

**Lesson:** Raising total RUs cannot cure every hotspot; partition design is foundational.

## 40. Hands-On Lab: Making `Order + Outbox` Atomic

**Context:** Your organization provides an API for NoSQL lab Cosmos DB account. The Orders API must write two documents inside one logical partition and prepare events for a separate relay.

### Resources and Data

| Component | Value |
|---|---|
| Database | `commerce` |
| Container | `orders` |
| Partition key path | `/orderScope` |
| Order scope | `tenant-lab|ORD-LAB-1042` |
| Order ID | `order:ORD-LAB-1042` |
| Outbox ID | `outbox:evt-lab-1042-created` |
| Order status | `Pending` |
| Event type | `OrderPlaced` |
| SDK | Azure Cosmos DB for NoSQL .NET SDK |
| Authentication | Lab-authorized managed identity / `DefaultAzureCredential` |
| Prohibited risk | Zero real data; never print credentials or PII |

### Tasks

1. Sketch Account → Database → Container → logical partition → two documents.
2. Explain why sharing a physical partition is insufficient for an ACID batch.
3. Create the container with `/orderScope` or verify the existing lab container.
4. Choose a stable partition key value for an order.
5. Insert Order and Outbox together in one Transactional Batch.
6. Inspect `response.IsSuccessStatusCode`, per-operation status codes, and `RequestCharge`.
7. Point-read both items using the exact partition key.
8. Re-run the batch with identical IDs and explain the 409 / idempotent outcome.
9. Construct a batch conflict using a new outbox ID; prove rollback occurs.
10. Intentionally give the two items different `orderScope` values; record the expected failure.
11. Update the Order via `Replace` with `IfMatchEtag` and create an `OrderPaid` outbox in the same batch.
12. Simulate two workers reading the same ETag; explain why one receives 412.
13. Compute required write RU/s from measured `RequestCharge` and transaction rate.
14. Explain why an atomic transaction cannot span two Orders with different keys.
15. Design a change feed / outbox relay publishing to Service Bus post-commit.
16. Explain the scenario where the relay publishes successfully and crashes before marking `Sent`.
17. Add a consumer idempotency key to prevent duplicate side effects.
18. Define alerts for 429s, conflict rates, outbox age, and lag.
19. Propose a schema for a tenant with 100,000 Orders avoiding a hot `tenantId` key.
20. Describe the impact of using an HPK of `(tenantId, orderId)`.
21. Run negative tests strictly in the lab environment, never against Production.
22. Gather evidence and clean up lab resources per permissions.

### Expected Flow Diagram

```text
POST /orders (deterministic requestId)
         |
         v
Validate schema + tenant authorization
         |
         v
TransactionalBatch (key tenant-lab|ORD-LAB-1042)
         |
         +-- Create Order
         |
         +-- Create OutboxEvent
         |
         v
     Atomic commit
         |
         +---- Failed → zero new items committed
         |
         +---- Succeeded → response accepted
                             |
                             v
                       Change Feed Relay
                             |
                             v
                         Service Bus
                             |
                             v
                      Idempotent consumer
```

### Guidance Answers

- **Two items, same key:** Batch executes with ACID guarantees.
- **Two items, different keys:** Batch cannot run as a cross-partition transaction.
- **Re-creating same ID:** 409 conflict; inspect existing record to tell duplicate retry from collision.
- **ETag 412:** Another worker modified the item; re-read and re-evaluate transition.
- **Timeout post-commit:** Ambiguous outcome; resolve via point reads and deterministic IDs.
- **Outbox:** Makes DB commit of Order + Event atomic; Service Bus publish remains a separate at-least-once step.
- **RUs:** Measure on real requests rather than guessing from operation counts.
- **Partition key:** Align with aggregates and scale; avoid packing giant tenants into one logical key.
- **Security:** Combine data-plane RBAC/identity, network controls, and app-level tenant authorization.

### Acceptance Criteria

1. One **successful batch** leaving both items persisted under the same key.
2. One **intentional failing batch** leaving zero “half-committed” items behind.
3. One ETag demonstration preventing lost updates.
4. Idempotency handling for client retries after timeouts.
5. Clear separation between DB transactions and external message publishing.
6. Recorded RU/latency figures and 429 threshold checks.
7. Zero real credentials or sensitive payloads in source code or logs.
8. Documented strategy for workflows spanning multiple logical partitions.

## 41. Self-Check Questions

**Question 1.** How wide is the transaction scope of a Cosmos DB for NoSQL Transactional Batch?

**Answer:** Supported point operations sharing the **same full logical partition key** within the **same container**.

**Question 2.** Can two logical partitions residing on the same physical partition join one atomic batch?

**Answer:** No. Sharing a physical partition does not extend ACID scope across two logical keys.

**Question 3.** Does the same `id` under two different partition keys refer to the same document?

**Answer:** No. Item identity and point lookups are scoped to `(partition key, id)`.

**Question 4.** Why is putting `Order` and `Outbox` under the same `orderScope` useful?

**Answer:** It lets a Transactional Batch commit both documents atomically, preventing an Order from committing without its outbox record.

**Question 5.** Can you call Service Bus inside a Transactional Batch so it commits atomically with the Order?

**Answer:** No. Service Bus sits outside Cosmos DB's transaction boundary; use an outbox/relay with idempotency.

**Question 6.** If a batch fails because `Create Order` hits a duplicate ID, does the subsequent `OutboxEvent` commit anyway?

**Answer:** No. The transaction rolls back the entire batch.

**Question 7.** What does status `424` on other operations in a batch usually indicate?

**Answer:** Those operations were aborted because another operation in the batch failed. Find the root error code such as 409 or 412 first.

**Question 8.** Does a successful batch mean the change feed relay has already published the event?

**Answer:** No. Committing to Cosmos DB and publishing to Service Bus are two separate steps.

**Question 9.** What bug do ETags help prevent?

**Answer:** Optimistic concurrency detects concurrent modifications via `IfMatch`, preventing lost updates.

**Question 10.** Does Transactional Batch automatically protect a business decision calculated from an earlier read outside the batch?

**Answer:** No. Pair it with ETags, preconditions, or appropriate transactional checks.

**Question 11.** Should a 412 error be resolved by stripping `IfMatch` and retrying the stale write?

**Answer:** No. Re-read the latest state and verify the transition is still valid.

**Question 12.** Can a 409 after a timeout happen when the earlier request actually committed?

**Answer:** Yes. Inspect the existing items and business IDs before deciding to return an idempotent success.

**Question 13.** What risk does using `Upsert` for outbox events introduce?

**Answer:** Retries can overwrite existing events and mask duplicate deliveries; `Create` with a deterministic ID is usually safer for write-once events.

**Question 14.** Why is `/status` a poor partition key for Orders?

**Answer:** Status changes over an order's lifecycle, and an item's partition key cannot be updated in place like a normal field.

**Question 15.** With HPK `(/tenantId, /orderId)`, do two Orders in the same tenant share a transactional scope?

**Answer:** Not if their `orderId` values differ. They must match on the **full hierarchical key tuple**.

**Question 16.** Can a Transactional Batch run a cross-partition SQL query before committing?

**Answer:** No. Batch APIs operate on supported point operations within one logical key.

**Question 17.** Does one batch HTTP call cost only 1 RU?

**Answer:** No. RUs scale with operation count, item size, indexing, and workload; measure `RequestCharge`.

**Question 18.** Why can 429s appear before container-wide RUs are exhausted?

**Answer:** A single hot key/physical partition can saturate locally, or throughput distribution across partitions may be uneven.

**Question 19.** Does Transactional Batch snapshot isolation make cross-region reads strongly consistent?

**Answer:** No. Consistency levels, region routing, and replication visibility are separate concerns.

**Question 20.** What happens if an outbox relay publishes a message and crashes before marking it `Sent`?

**Answer:** The event may be republished; consumers need idempotency and deterministic event IDs.

**Question 21.** Are multi-partition Bulk operations equivalent to a Transactional Batch?

**Answer:** No. Bulk optimizes throughput without providing cross-partition atomicity.

**Question 22.** Can a stored procedure span beyond one logical partition?

**Answer:** No. Transactional stored procedures in API for NoSQL are also scoped to one logical partition.

**Question 23.** To transfer loyalty points between two accounts with different keys, can you use one atomic Batch?

**Answer:** No. Design a saga/compensation workflow or choose a data model/system supporting the required transaction scope.

**Question 24.** Does knowing a partition key authorize a user to read another tenant's Order?

**Answer:** No. Partition keys are not authorization; enforce authentication and tenant ownership in the app and data-plane policies.

**Question 25.** If a JSON document misspells the partition key field, will the SDK automatically place it properly to preserve atomicity?

**Answer:** No. Field/key mismatches fail; schemas and container definitions must align strictly.

**Question 26.** Should you enable infinite retries for batch 429s or timeouts?

**Answer:** No. Use bounded backoff, retry caps, and idempotency/read-after-error to avoid retry storms inflating load and cost.

**Question 27.** Why shouldn't a committed batch be treated as proof that payment succeeded?

**Answer:** A batch only commits Cosmos DB data; payment providers, brokers, and downstream services have independent outcomes.

**Question 28.** If a batch accidentally deletes an Order and commits, does atomicity restore the Order?

**Answer:** No. Atomicity guarantees all-or-nothing commit/rollback, not backup. Rely on backup/restore, change feed, and audit logs.

**Question 29.** Which metrics confirm Transactional Batch health?

**Answer:** Success/failure rates, per-operation status codes, latency, RUs, 429s, 409/412 conflicts, hot partitions, outbox pending age, and downstream processing health.

**Question 30.** When should you redesign the partition key instead of expanding batches?

**Answer:** When transaction boundaries misalign with aggregates, one key grows too hot or large, or atomic workflows span multiple keys—revisit the data model and saga/outbox patterns.

**Summary:** **Transactional Batch in Azure Cosmos DB for NoSQL** provides ACID transactions for **point operations within a single logical partition of one container**. Reliable design starts with an **aggregate-aligned partition key**, pairs with **ETags to prevent lost updates**, **deterministic IDs to make retries safe**, **outbox + change feed** to integrate external systems, and **RU/hot-partition monitoring** for steady operations. A batch is not a distributed transaction, nor does it replace backups or idempotency. Respecting that boundary lets you build **atomic, measurable, and resilient** multi-document updates without compromising business consistency.
