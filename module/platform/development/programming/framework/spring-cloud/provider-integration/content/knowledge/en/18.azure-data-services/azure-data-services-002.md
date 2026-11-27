# Partition Keys, Document Mapping, and Repositories

When using Azure Cosmos DB for NoSQL with Spring Data Cosmos, three decisions are tightly coupled: the **partition key** determines how data is distributed and routed; **document mapping** determines how Java objects become JSON items; and **repositories** determine the access patterns the application uses to read and write items. If an unsuitable partition key is chosen, a repository with very short methods can still generate fan-out queries, consume excessive Request Units (RU), or concentrate load onto a single logical partition. If field names or partition values are mapped incorrectly, point reads and queries may fail to find items even when the data exists.

This lesson belongs to the **Azure Data Services** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers practical integration of Spring Boot with managed services across AWS, Azure, and Google Cloud via their respective Spring Cloud libraries, including identity/permission configuration, storage access, messaging, data, secret protection, integration testing, and evaluating differences between cloud providers. This lesson dives into the Cosmos DB for NoSQL data model and how to express that model through entities, repositories, and queries in Spring Data Cosmos.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Design a partition key based on access patterns, load distribution, cardinality, and transaction boundaries.
- Distinguish between item ID, partition key value, logical partition, and physical partition.
- Map Java documents to JSON items using `@Container`, `@Id`, `@PartitionKey`, and mapping conventions.
- Write CRUD repositories, derived queries, parameterized custom queries, and point reads with a partition key.
- Evaluate the cost of cross-partition queries, pagination, and unindexed queries.
- Design concurrent updates using ETag/optimistic locking and handle partition key changes.
- Test mapping, repositories, and partition behavior using the emulator and an Azure environment.

## 2. Item, ID, and Partition Key Form the Data Address

In Cosmos DB for NoSQL, data is stored as **JSON items** inside a **container**. Each item has a system property `id`; the container has a partition key path, such as `/tenantId`. The value of the field at that path is the **partition key value**.

For a container with partition key path `/tenantId`, the following item belongs to logical partition `tenant-42`:

~~~json
{
  "id": "order-1001",
  "tenantId": "tenant-42",
  "status": "PAID",
  "total": 125.50,
  "createdAt": "2026-11-24T08:30:00Z"
}
~~~

Three concepts to distinguish:

| Concept | Meaning | Example |
| --- | --- | --- |
| **Item ID** | Item identifier within the container; typically mapped from the `id` field | `order-1001` |
| **Partition key path** | JSON path declared for the container | `/tenantId` |
| **Partition key value** | Value of the field at that path for a specific item | `tenant-42` |

In the API for NoSQL, an item is uniquely identified by its **ID and partition key value** within a container. Two items can share the same `id` if they reside in different logical partitions; within the same logical partition, that combination must be unique. Therefore, keeping only the ID in a URL may not be sufficient to perform an efficient point read.

~~~mermaid
flowchart TD
    A[Container: orders] --> P1[Logical partition tenant-42]
    A --> P2[Logical partition tenant-77]
    P1 --> I1[Item id=order-1001]
    P1 --> I2[Item id=order-1002]
    P2 --> I3[Item id=order-1001]
    K[Point read address] --> V[container + partition key + id]
~~~

A **logical partition** is the group of items sharing the same partition key value. The service distributes logical partitions onto **physical partitions** managed by Cosmos DB. The application chooses the partition key path and value; it does not manually assign items to a specific physical partition.

## 3. Choosing a Partition Key from Access Patterns

A partition key should be chosen after listing the operations the application actually needs:

- Reading a single item when its ID is known.
- Listing items by tenant, status, or time.
- Writing/updating multiple items in a single use case.
- Paginating large lists.
- Running reports or aggregate queries across multiple tenants.
- Handling skewed traffic across data groups.

A good partition key generally has **sufficiently high cardinality**, distributes load relatively evenly, appears in critical queries, and has a stable value over the item's lifecycle. There is no single default field that fits every application.

### 3.1. Orders Container Example

Suppose most requests operate on data for one tenant: creating orders, reading orders, finding orders by status, and loading history. A `/tenantId` partition key can be a good fit because tenant-scoped queries can be routed to a single logical partition.

| Partition Key | Pros | Risks |
| --- | --- | --- |
| `/tenantId` | Convenient tenant-scoped queries; a tenant's items share one logical partition | A large or hot tenant can cause skew and limit scalability |
| `/id` | High cardinality; convenient point reads if ID is always known | Queries by tenant/status typically fan out across many partitions |
| `/status` | Single-status queries have simple predicates | Few status values; some partitions can become very hot and accumulate excessive data |
| `/createdMonth` | Useful for monthly queries and time-based archiving | Tenant queries may cross multiple partitions; transactions across months are split |
| Synthetic key `tenantId#bucket` | Can spread load for a large tenant | Requires stable bucket calculation; tenant queries must aggregate across multiple logical partitions |

**High cardinality is not the only criterion.** A key with millions of distinct values that rarely appears in common queries can force frequent fan-outs. A key with fewer values whose load is evenly distributed can still work well for a specific workload; measure with representative data.

### 3.2. Hot Partitions and Skew

A logical partition can become a **hot partition** if it receives far more requests/RUs than other partitions. For example, if one tenant accounts for 40% of traffic and all of that tenant's items share `tenantId`, one partition can hit throughput limits even while total container RU/s capacity remains unused on other partitions.

Monitor:

- RUs consumed per partition key range and the rate of throttled requests.
- Distribution of item counts and data size by key.
- Read/write frequency by tenant, status, or time window.
- Fan-out queries and the number of partitions involved.
- Largest size of a single logical partition.

Do not try to fix a hot partition simply by throwing more RU/s at it. If one key is too hot, higher throughput may delay failures without changing the underlying skew. Revisit the key, data model, or workload partitioning.

### 3.3. Synthetic Keys and Hierarchical Partition Keys

A **synthetic partition key** is a value constructed by the application from multiple attributes, such as `tenantId#yyyyMM` or `tenantId#shardNumber`. This can spread load, but queries looking up all data for a tenant may need to compute all buckets and read multiple partitions. The key construction function must be deterministic, clearly versioned, and never rely on arbitrary values sent by callers.

**Hierarchical partition keys (HPK)** allow declaring multiple levels in the partition key path within the capabilities supported by Cosmos DB for NoSQL. This structure helps distribute large datasets across levels—such as tenant followed by a subgroup—while still supporting queries with a hierarchy prefix. However, check the limits, API, SDK, and support in your Spring Data Cosmos version; do not assume a single-field `@PartitionKey` annotation represents every HPK configuration.

Only use HPK when access patterns and scale truly require it. It does not turn every query into a point read, does not automatically guarantee balanced load, and does not turn transactions into cross-level operations.

## 4. Partition Keys Define Transaction Boundaries

Cosmos DB for NoSQL supports ACID transactions within **a single logical partition key**. A transactional batch can group operations on items in the same container and with the same partition key value; the batch rolls back if an operation fails per the API contract.

This directly shapes the data model:

~~~text
Order(orderId, tenantId)
OrderLine(lineId, orderId, tenantId)
PaymentRecord(paymentId, orderId, tenantId)
~~~

If an order, its order lines, and its payment record need to be updated atomically together, placing them in the same container with the same partition key value can enable a transactional batch. If each data type lives in a different container or has a different partition key value, there is no atomic transaction across those boundaries.

| Design | Can Use a Single Transactional Batch? | Consequence |
| --- | --- | --- |
| Multiple items in the same container, same partition key value | Yes, if the operations are supported by the API | Suitable for atomic updates within a logical partition |
| Items in the same container but different partition key values | No | Requires a multi-step workflow/saga or aggregate redesign |
| Items in two different containers | Not with a single-container transactional batch | Must coordinate separately |
| Cosmos database and Azure Blob Storage | No | Requires state tracking, retries, outbox, or compensation |

If business logic requires transactions across multiple tenants, reconsider the aggregate boundary. Do not pick `/tenantId` merely for convenience and then expect a batch to update multiple tenants at once.

## 5. Mapping Java Objects to JSON Items

Spring Data Cosmos provides mapping annotations to describe containers and fields:

- `@Container`: binds the entity to a container.
- `@Id`: marks the field mapped to the `id` system property.
- `@PartitionKey`: marks the field carrying the partition key value.
- Appropriate Spring Data/Jackson annotations or converters can support specific mapping cases, though you should verify the actual serializer in the version being used.

Example entity:

~~~java
import com.azure.spring.data.cosmos.core.mapping.Container;
import com.azure.spring.data.cosmos.core.mapping.PartitionKey;
import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.data.annotation.Id;

@Container(
    containerName = "orders",
    autoCreateContainer = false
)
public class OrderDocument {
    @Id
    private String id;

    @PartitionKey
    private String tenantId;

    private String status;
    private BigDecimal total;
    private Instant createdAt;

    public OrderDocument() {
    }

    public OrderDocument(
            String id,
            String tenantId,
            String status,
            BigDecimal total,
            Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.status = status;
        this.total = total;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getStatus() { return status; }
    public BigDecimal getTotal() { return total; }
    public Instant getCreatedAt() { return createdAt; }

    public void setId(String id) { this.id = id; }
    public void setTenantId(String tenantId) { this.tenantId = tenantId; }
    public void setStatus(String status) { this.status = status; }
    public void setTotal(BigDecimal total) { this.total = total; }
    public void setCreatedAt(Instant createdAt) { this.createdAt = createdAt; }
}
~~~

If a container is created with partition key path `/tenantId`, the entity's `tenantId` field must serialize cleanly as the `tenantId` property at the JSON root. Field names, annotations, serializer behavior, and the partition key path must all match. Renaming a Java field without updating the mapping can cause requests to miss the partition key or queries to filter on the wrong property.

### 5.1. Container Mapping Does Not Create Relational Schemas

`@Container(containerName = "orders")` specifies the container name. Cosmos DB is schema-flexible: items in the same container are not required to have identical sets of properties. Entity annotations do not automatically create foreign keys, joins, relational constraints, or indexes as in a JPA database.

`autoCreateContainer = false` is appropriate when containers are provisioned by IaC/deployment pipelines. If enabling auto-create in development, understand what partition key/throughput the library will use and whether provisioning permissions exist. Never allow multiple production instances to create or alter containers outside infrastructure management workflows.

### 5.2. Optional Fields, Nulls, and Data Types

Mapping must clearly decide how to represent:

- **Missing fields vs. null:** these two states can behave differently in queries and updates. Do not assume serializers always write or omit null fields identically.
- **Timestamps:** standardize on UTC and ISO 8601/`Instant`; avoid storing local timestamps without offsets if querying by time.
- **Currency:** use `BigDecimal` or integer minor units paired with a currency code; avoid float/double for values requiring exactness.
- **Enums:** decide whether to serialize by stable name or code; renaming a Java enum can break deserialization of older data if mapped by name.
- **Nested objects/collections:** control item size and shape; queries on nested paths must be supported by the indexing policy.
- **Sensitive fields:** never serialize credentials/tokens/secrets into an item just because the entity has that field.

If using Jackson annotations or custom converters, test the actual JSON sent/received by the SDK; do not infer behavior solely from Java getters/setters.

### 5.3. Mapping Data Versions

Item schemas evolve over time. When adding new fields, set sensible defaults in the application model and ensure older consumers can ignore unknown fields. When renaming or changing semantics:

1. Add the new field or version marker first.
2. Allow code to read both old and new formats during the transition period.
3. Backfill in batches with bounded RUs.
4. Switch writes to the new format.
5. Remove the old field only after reconciliation and once no dependent consumers remain.

Do not treat renaming a Java property as an implicit data migration. Cosmos DB does not rename properties in existing items when an application deploys new code.

## 6. Repository Interfaces and Core Operations

Spring Data Cosmos provides `CosmosRepository<T, ID>` for synchronous APIs. Example:

~~~java
import com.azure.spring.data.cosmos.repository.CosmosRepository;
import java.util.List;
import java.util.Optional;
import org.springframework.data.repository.query.Param;
import com.azure.spring.data.cosmos.repository.Query;

public interface OrderRepository
        extends CosmosRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantIdAndStatus(
        String tenantId, String status);

    @Query("SELECT * FROM c WHERE c.tenantId = @tenantId AND c.status = @status")
    List<OrderDocument> findOrders(
        @Param("tenantId") String tenantId,
        @Param("status") String status);
}
~~~

Commonly used repository methods:

| Method | Meaning | Notes |
| --- | --- | --- |
| `save(entity)` | Creates or updates an item per repository/SDK semantics | Not equivalent to create-only by default; check upsert and concurrency behavior |
| `findById(id)` | Finds an item by ID via the repository | Without a partition key, may not achieve point-read efficiency |
| `findById(id, partitionKey)` | Finds by ID and partition key | Preferred when the partition value is known |
| `findAll()` | Retrieves data via the repository | May read across many partitions; do not treat as a cheap default operation |
| `deleteById(id)` | Deletes an item by ID | For partitioned containers, use a partition-key-aware API/overload when available |
| Derived query | Generates a query from the method name | Only use keywords supported by Spring Data Cosmos |
| `@Query` | Declares a Cosmos SQL query | Bind parameters; check partition predicates and RUs |

Not all Spring Data JPA method signatures carry the same semantics or are supported in Spring Data Cosmos. Read the documentation for your exact version and test real repositories, especially methods using `Pageable`, `Sort`, `Optional`, projections, or derived updates/deletes.

## 7. Point Reads: Passing Both ID and Partition Key

When both item ID and partition key value are known, a point read is the direct read path of choice. With Spring Data Cosmos, you can use the repository overload accepting `PartitionKey`:

~~~java
import com.azure.cosmos.models.PartitionKey;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class OrderReadService {
    private final OrderRepository orders;

    public OrderReadService(OrderRepository orders) {
        this.orders = orders;
    }

    public Optional<OrderDocument> find(
            String authenticatedTenantId,
            String orderId) {
        return orders.findById(
            orderId,
            new PartitionKey(authenticatedTenantId));
    }
}
~~~

In a multi-tenant application, `authenticatedTenantId` must come from an authenticated security context or have ownership verified. Never trust a caller-supplied partition key to read items belonging to another tenant. An endpoint that only receives `orderId` may need to look up a trusted routing/metadata record to resolve the tenant/partition key before calling a point read.

**Point reads** and **queries** are distinct:

- A point read uses **container + item ID + partition key value**, and is typically the most efficient read path for a known item.
- A query uses predicates and can return multiple items; if not scoped by partition key, the service may have to fan out across many partitions.
- A derived query containing the partition key in its method name does not automatically guarantee the SDK performs a point read; only an explicit item ID + partition key point-read API expresses the direct read path.

## 8. Derived Queries and Custom Cosmos SQL

### 8.1. Derived Queries

Example:

~~~java
List<OrderDocument> findByTenantIdAndStatus(
    String tenantId, String status);

List<OrderDocument> findByTenantIdAndCreatedAtAfter(
    String tenantId, Instant from);
~~~

Spring Data parses method names to generate queries based on entity properties. Property names must match the Java mapping. A method like `findByStatus("PAID")` without a tenant predicate can become a cross-partition query on a partitioned container.

### 8.2. Custom Parameterized Queries

~~~java
@Query("""
    SELECT * FROM c
    WHERE c.tenantId = @tenantId
      AND c.status = @status
    ORDER BY c.createdAt DESC
    """)
List<OrderDocument> findRecentByStatus(
    @Param("tenantId") String tenantId,
    @Param("status") String status);
~~~

This is a Cosmos DB SQL-like query; `@Param` binds values instead of concatenating inputs into a query string. Avoid concatenating request strings into `@Query`, as it easily produces malformed queries and injection risks. If dynamic property/field names are needed, use a whitelist and an appropriate query API rather than letting callers supply arbitrary SQL fragments.

A **partition predicate** should be included in queries whenever the access pattern allows it, such as `c.tenantId = @tenantId`. This enables the service to route to the relevant partition. However, having a partition key predicate does not mean every query costs a fixed single RU; cost still depends on item count, indexes, projections, consistency, and actual data.

### 8.3. Projections and Fetching Only Needed Fields

If a view only needs `id`, `status`, and `total`, there is no need to read full items with large payloads. You can design projection DTOs/queries according to the Spring Data Cosmos features in your version. Verify mapped return types, nullability, and system fields; never return persistence entities directly from public APIs if they contain internal fields.

## 9. Cross-Partition Queries, Pagination, and RUs

A query missing a partition key may execute across multiple logical/physical partitions. This is valid for reports or global searches, but carries costs:

- More partitions involved, more backend requests, and higher total RUs.
- Latency depends on the slowest partition and degree of parallelism.
- Large result sets require continuation tokens/pages; never load all items onto the heap.
- Throttling can occur if parallelism/query concurrency is too high.

Example query for all orders by status:

~~~sql
SELECT * FROM c
WHERE c.status = "PAID"
~~~

If `tenantId` is the partition key, the query above does not specify a tenant and may run cross-partition. That may be a valid requirement for system-wide reporting; in such cases, consider a projection/reporting store or change feed rather than running heavy queries on the request path.

### 9.1. Pagination and Continuation

Cosmos DB uses continuation tokens to resume a query. A page may return fewer items than the requested page size due to RU limits, execution time, or response limits. Do not assume `Pageable` on every repository provides free total page counts like a relational database.

For public APIs, you can wrap continuation tokens inside an opaque cursor. Tokens must be protected from tampering and bound to the original query/filter/tenant context; never reuse tenant A's token for tenant B. If framework abstractions do not expose tokens the way you need, use the corresponding template/SDK API inside an adapter while keeping the pagination contract at the application boundary.

### 9.2. RUs and Query Diagnostics

RU charge reflects operation cost. To optimize queries:

1. Record request charge, latency, status/substatus, and activity ID.
2. Confirm the query includes a partition key predicate whenever possible.
3. Inspect the indexing policy, sort/order, composite indexes, and projections.
4. Reduce returned fields/items, use pagination, and bound concurrency.
5. Compare on data with a distribution resembling production.

Do not measure latency only in an emulator or small dataset. RUs, throttling, and hot partitions only surface clearly under representative data and load.

## 10. Concurrent Updates with ETag and Optimistic Locking

Two workers may read the same item and then update it concurrently. Without concurrency control, the later write can overwrite the earlier write's changes. Cosmos DB uses ETags to support optimistic concurrency.

With Spring Data Cosmos, you can map the ETag to the `_etag` field using `@Version` on supported operations/versions:

~~~java
import com.azure.spring.data.cosmos.core.mapping.Container;
import com.azure.spring.data.cosmos.core.mapping.PartitionKey;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;

@Container(containerName = "inventory")
public class InventoryDocument {
    @Id
    private String id;

    @PartitionKey
    private String warehouseId;

    private int availableQuantity;

    @Version
    private String _etag;

    public InventoryDocument() {}
}
~~~

When a repository updates an entity carrying a stale ETag, the service can return a conflict/precondition failure (typically HTTP 412 at the underlying API). The application service must decide to:

- Re-read the item and recompute business logic (e.g., deduct inventory).
- Return a conflict so the caller retries against the fresh state.
- Reject if business preconditions no longer hold.

Do not infinitely retry the same stale payload, as that will never resolve the conflict. Test two concurrent processes updating the same item and verify that one detects the stale version.

## 11. Changing Partition Keys and Data Migration

**A partition key value cannot be updated in place to move an item to another logical partition.** If you need to change `tenantId` or change the partition key path, you must create a new item at the target location and delete the old item via a controlled process. Changing the partition key path for an existing container typically requires a new container and data migration.

A migration workflow may include:

1. Creating the target container with the new partition key path and appropriate indexing/throughput.
2. Backfilling old data in batches with bounded RUs and checkpoints.
3. Syncing changes occurring during backfill (e.g., change feed or controlled dual-write).
4. Reconciling item counts, IDs, partition values, checksums, and business invariants.
5. Cutting traffic over to the new container with a cutover/rollback plan.
6. Keeping the old container during the rollback window, then retiring it per retention policy.

If changing from `/tenantId` to `/tenantId/orderGroup`, the application must also update mapping and queries/repositories accordingly; merely editing Java annotations does not migrate existing data.

## 12. Synchronous and Reactive Repositories

Spring Data Cosmos provides synchronous and reactive repositories depending on dependency/version:

~~~java
import com.azure.spring.data.cosmos.repository.ReactiveCosmosRepository;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository
        extends ReactiveCosmosRepository<OrderDocument, String> {

    Flux<OrderDocument> findByTenantIdAndStatus(
        String tenantId, String status);

    Mono<OrderDocument> findByTenantIdAndId(
        String tenantId, String id);
}
~~~

Reactive repositories fit when the entire processing pipeline uses WebFlux/Reactor and the underlying driver/client supports non-blocking execution. Do not wrap a synchronous repository in `Mono.just(...)` and claim reactive I/O; the blocking call still executes when constructing the value. If a blocking operation must be bridged, isolate it from the event loop with an appropriate scheduler, though it remains blocking I/O.

For reactive methods, handle `Mono.empty()`, `onError`, cancellation, and retries according to contract. Retrying a write with side effects can produce duplicate operations; use stable IDs, ETag/preconditions, or idempotency. Never call `subscribe()` inside a service to fire-and-forget a repository call and return a response before the operation finishes.

## 13. When to Use Repository, Template, or Direct SDK?

| Need | Suitable Option to Evaluate | Why |
| --- | --- | --- |
| Common entity CRUD and queries | `CosmosRepository` | Reduces boilerplate, integrates with Spring Data |
| Derived field queries and custom Cosmos SQL | Repository + `@Query` | Clear data-access contract, parameter binding |
| Point read requiring explicit partition key | Repository overload or template/SDK | Controls the ID + partition read path |
| Need response diagnostics/RUs or custom request options | `CosmosTemplate` or SDK | Lower-level option access |
| Change Feed Processor, transactional batches, or specialized SDK features | Appropriate SDK/client | Repositories do not necessarily expose full capabilities |
| Multiple coordinated operations in a workflow | Application service + repository/port | Keeps business transaction boundaries clear |

There is no need to drop down to the direct SDK for every method just to "optimize." Measure first, then move only the parts needing specialized capabilities into an adapter. Conversely, do not force a specialized SDK operation into a derived query just because you want all data access to be repositories.

## 14. Testing Mapping, Repositories, and Partitions

### 14.1. Application Service Unit Tests

Mock repositories/ports to test business rules, tenant authorization, and how the service constructs entities. Unit tests require no Cosmos endpoint, credentials, or emulator.

### 14.2. Mapping Tests

Verify the actual JSON:

- `id` field exists and has the right type.
- Partition property serializes with the expected name/path and is non-null.
- Enums, timestamps, decimals, nested objects, and optional fields are represented accurately.
- Sensitive fields never appear in the document.
- Older data still deserializes after schema changes.

Do not test only getters/setters. Use the library's actual serializer/mapping and read items back from the emulator or a test account.

### 14.3. Repository Integration Tests

| Test Case | What to Verify |
| --- | --- |
| Save then point read | Same ID + partition key retrieves the exact item |
| Same ID across two different partitions | Items are not mixed up across tenants |
| Derived query with partition predicate | Results and RU/latency match expectations |
| Query missing partition predicate | Cross-partition behavior and cost are recognized |
| Pagination | Continuation/page neither drops nor duplicates items outside contract |
| Optimistic locking | Stale ETag raises a conflict rather than silently overwriting |
| Transactional batch | Only items sharing a logical partition commit atomically |
| Schema changes | Old and new entities are read according to the migration plan |

The Cosmos DB Emulator supports local testing for supported APIs, but does not replace cloud tests for Managed Identity, native data-plane RBAC, firewall/private endpoints, RU quotas, multi-region failover, and production-like workloads. The emulator uses a self-signed certificate; the Java runtime must trust the certificate per instructions rather than disabling TLS verification.

## 15. Common Design Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Choosing `/status` as partition key because queries filter by status | Low key cardinality, can create hot partitions | Analyze cardinality, traffic, and tenant/ID queries |
| Using `/id` when most queries are by tenant | Many fan-out queries | Pick keys by access pattern or design projections |
| Storing only ID and forgetting partition key on read | Cannot perform optimal point reads | Pass verified ID + partition value |
| Renaming Java fields without checking JSON | Queries/mapping diverge from property paths | Mapping tests and schema migrations |
| Calling `findAll()` in request paths | Broad scans, high RU/latency | Filtered queries, pagination, or read models |
| Expecting JPA joins/transactions on Cosmos | Wrong data and transaction model | Denormalize by access pattern; transact within one logical partition |
| Editing partition key annotation and deploying | Old items remain under the old partition path | Create target container and migrate data |
| Retrying updates with a stale ETag | Repeated conflicts or lost business updates | Re-read and recompute state |
| Testing only with mocked repositories | Misses partition/mapping/query behavior | Emulator and cloud integration tests |

## 16. Practice Exercises

**Exercise 1 — Choosing a partition key.** A system stores orders by tenant. 90% of requests read by `tenantId + orderId`, 8% query by `tenantId + status`, and 2% run system-wide reports. Choose a partition key, explain how to handle an extremely large tenant, and evaluate cross-partition queries for reports.

**Exercise 2 — Entity mapping.** Write `OrderDocument` with `@Container`, `@Id`, and `@PartitionKey`; specify the container partition key path and expected JSON item. Add timestamp, currency, enum, and nested address fields; define stable formats as the schema evolves.

**Exercise 3 — Repository.** Write `OrderRepository` with a derived query by tenant/status, a custom `@Query` by time, and a point-read method taking `PartitionKey`. Explain which methods can be cross-partition and how to verify queries/RUs.

**Exercise 4 — Hot partition.** One tenant generates 40% of total RUs. Propose a synthetic key or hierarchical key; list which queries must change, how transactions are maintained, and the cost of aggregating across multiple buckets.

**Exercise 5 — Transactions.** An order has multiple lines that must be updated atomically. Design the container/partition so a transactional batch works. What happens if lines belong to a different partition or container?

**Exercise 6 — Optimistic locking.** Two workers update inventory concurrently. Use ETag/`@Version`, simulate a 412, and write the re-read/recalculate quantity logic. Why is retrying a stale payload unsafe?

**Exercise 7 — Partition migration.** A system currently uses `/tenantId` and needs to move to `/tenantId/orderGroup`. Write a plan covering new container creation, backfill, change sync, reconciliation, cutover, and rollback.

**Exercise 8 — Test strategy.** Build a test suite covering JSON mapping, repositories, partition routing, pagination, RUs, and RBAC. Categorize which tests use mocks, the emulator, and real Azure.

## 17. Key Takeaways

- **Partition key path and value are part of an item's address.** For a point read, you need the container, item ID, and partition key value; ID alone is insufficient for direct routing.
- Choose keys by **access pattern, cardinality, load distribution, and transaction boundaries**. Skewed keys can create hot partitions even when overall throughput remains available.
- **Java mapping must match the JSON path** declared by the container. `@Container`, `@Id`, and `@PartitionKey` do not migrate data or alter partition keys of existing items.
- **CosmosRepository** fits common CRUD/queries; `@Query` uses Cosmos SQL-like syntax and requires bound parameters. Cross-partition queries, pagination, and RUs must be measured.
- **Transactional batches are atomic only within the same logical partition key**; ETag/`@Version` detects stale updates, while the application must resolve conflicts.
- Changing a partition key is a **data migration**, not just an annotation edit. It requires a target container, backfill, change sync, reconciliation, and a cutover with rollback.
- Test mapping/repositories with the emulator, then verify identity, native data-plane RBAC, quotas, and failover on real Azure.
