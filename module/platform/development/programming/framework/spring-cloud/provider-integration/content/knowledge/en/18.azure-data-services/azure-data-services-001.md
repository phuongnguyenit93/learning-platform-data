# Integrating Azure Cosmos DB with Spring Data Cosmos

**Azure Cosmos DB for NoSQL** is a globally distributed database service that stores data as JSON items in containers. When integrated with Spring Boot, the **Azure Spring Data Cosmos** library provides the familiar Spring Data model: entities are mapped to containers, repositories perform CRUD operations and queries, and the Azure Cosmos DB Java SDK handles communication with the service. The repository layer reduces data access boilerplate, but it does not remove important Cosmos DB characteristics such as **partition keys, Request Units (RU), consistency, indexing, and transaction boundaries**.

This lesson belongs to the **Azure Data Services** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers practical integration of Spring Boot with managed services across AWS, Azure, and Google Cloud via their respective Spring Cloud libraries, including identity/permission configuration, storage, messaging, data, secret protection, integration testing, and evaluating differences between cloud providers. In this lesson, we focus on Azure Cosmos DB for NoSQL and Spring Data Cosmos, from client configuration to partition design and query operations.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Distinguish between account, database, container, item, and logical partition in Cosmos DB.
- Explain the roles of the Spring Cloud Azure starter, Spring Data Cosmos, repository/template, and the Azure Cosmos DB Java SDK.
- Configure the endpoint, database, and Microsoft Entra ID/Managed Identity for a Spring Boot application.
- Map a Java entity using `@Container`, `@Id`, `@PartitionKey` and write sync/reactive repositories.
- Choose a partition key based on queries and expected load; perform point reads with both item ID and partition key.
- Read RU charges, optimize indexing/queries, use optimistic locking, and run transactions within the scope of a single logical partition.
- Test with the Cosmos DB Emulator and real Azure environments, and diagnose permission, partition, throttling, and consistency errors.

## 2. Azure Cosmos DB for NoSQL and Where Spring Data Cosmos Fits

Azure Cosmos DB supports multiple compatible APIs such as NoSQL, MongoDB, Cassandra, Gremlin, and Table. **Spring Data Cosmos in this lesson targets Azure Cosmos DB for NoSQL** (formerly commonly known as the SQL API). It is a JSON document/item database with Cosmos DB's own SQL-like query language; it is **not** a relational database like SQL Server/PostgreSQL and does not provide cross-table joins or multi-table transactions like JPA.

Main components:

| Component | Role | Example |
| --- | --- | --- |
| **Account** | Service boundary, endpoint, region, consistency, and global configuration | A Cosmos DB account for the production environment |
| **Database** | Group of containers, can optionally share throughput depending on configuration | `orders-db` |
| **Container** | Boundary for storing items, partition key, indexing policy, and throughput | `orders` |
| **Item** | A JSON document with an `id` and a partition key | A customer order |
| **Logical partition** | Group of items sharing the same partition key value | All orders with `tenantId = tenant-42` |
| **Physical partition** | Infrastructure unit self-managed by the service to distribute data and throughput | The application does not specify physical partition placement |

~~~mermaid
flowchart TD
    A[Cosmos DB account] --> D[Database: orders-db]
    D --> C[Container: orders]
    C --> P1[Logical partition tenant-42]
    C --> P2[Logical partition tenant-77]
    C --> P3[Logical partition tenant-91]
    P1 --> I1[Item order-1001]
    P1 --> I2[Item order-1002]
    P2 --> I3[Item order-2001]
    P3 --> I4[Item order-3001]
~~~

The partition key value and item ID together identify an item in a container. Partition design directly impacts scalability, RU distribution, query cost, and transaction scope. Therefore, when using Spring Data Cosmos, **choosing a partition key is a data design decision**, not merely adding an annotation to make a repository work.

## 3. Integration Layers in Spring Boot

The path of a read/write operation typically looks like this:

~~~mermaid
flowchart LR
    H[Controller / application service] --> R[CosmosRepository]
    R --> T[CosmosTemplate / ReactiveCosmosTemplate]
    T --> S[Azure Cosmos DB Java SDK]
    S --> N[HTTPS / Direct or Gateway mode]
    N --> C[Azure Cosmos DB for NoSQL]
    A[Spring Cloud Azure auto-configuration] -. creates client / template .-> T
    I[Managed Identity / TokenCredential] -. authenticates .-> S
~~~

- **Spring Cloud Azure starter** bundles dependencies and auto-configuration, helping Spring create/configure clients and integration components.
- **Spring Data Cosmos** provides entity mapping, repositories, query methods, `CosmosTemplate`, and `ReactiveCosmosTemplate`.
- **Azure Cosmos DB Java SDK** executes requests, manages connections, retries, tokens, and diagnostics.
- **Cosmos DB service** checks permissions, partitions, indexing, consistency, and RUs, then returns the result.

A repository is a convenient API for common operations. When specialized SDK features are needed—such as the change feed processor, advanced transactional batches, stored procedures, or detailed diagnostics—the application can use the Spring-managed SDK client. There is no need to abandon Spring Data just because one use case requires an additional SDK call.

## 4. Adding Dependencies and Managing Versions

### 4.1. Using the Spring Cloud Azure Starter for Spring Data Cosmos

For a Spring Boot project using the Spring Cloud Azure ecosystem, you can import the compatible BOM and add the Cosmos data starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-data-cosmos</artifactId>
    </dependency>
</dependencies>
~~~

Set `spring-cloud-azure.version` according to the compatibility matrix between **Spring Boot, Spring Cloud Azure, and Spring Data Cosmos**. Different library branches support different Spring Boot lines; do not pick an arbitrary latest version and pair it with an older project. Spring Cloud Azure documentation currently distinguishes 5.x, 6.x, and 7.x lines based on Spring Boot versions; check the version mapping at upgrade time.

### 4.2. Using the Azure Spring Data Cosmos Library Directly

If the application configures the Cosmos SDK itself instead of using the Spring Cloud Azure starter, the primary dependency is:

~~~xml
<dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-spring-data-cosmos</artifactId>
</dependency>
~~~

In direct configuration, the application can extend `AbstractCosmosConfiguration`, declare a `CosmosClientBuilder`, and enable `@EnableCosmosRepositories`. Avoid simultaneously creating duplicate clients/templates alongside the starter's auto-configuration. Choose **one clear client ownership mechanism**, and inspect the bean graph and lifecycle at startup.

## 5. Configuring Endpoint, Database, and Identity

Example configuration for the Spring Cloud Azure starter:

~~~yaml
spring:
  cloud:
    azure:
      cosmos:
        endpoint: ${AZURE_COSMOS_ENDPOINT}
        database: orders-db
        credential:
          managed-identity-enabled: true
          # Only declare client-id when using a user-assigned identity:
          # client-id: ${AZURE_MANAGED_IDENTITY_CLIENT_ID}
~~~

`AZURE_COSMOS_ENDPOINT` is the account endpoint, typically of the form `https://<account>.documents.azure.com:443/`. `database` is the database used by the application. When running on Azure, **Managed Identity** allows the workload to acquire Microsoft Entra ID tokens without storing an account key in configuration. If using a user-assigned identity, add the corresponding client ID; with a system-assigned identity, no client ID is needed.

On a development machine, `DefaultAzureCredential` can be used to obtain identity from the Azure CLI, IDE, or credential sources supported by the Azure Identity SDK. In production environments, prefer Managed Identity/workload identity. If an account key must be used, store the key in a secret manager and maintain a rotation process; never commit keys to repositories or logs.

### 5.1. Distinguishing Resource Management Permissions and Data Permissions

Cosmos DB for NoSQL has its own **native data-plane RBAC**, separate from Azure Resource Manager control-plane RBAC:

| Built-in Data Role | Primary Permissions |
| --- | --- |
| **Cosmos DB Built-in Data Reader** | Read items, run queries, and read change feed |
| **Cosmos DB Built-in Data Contributor** | Create, read, update, and delete items |

Assign the role to the workload identity at the smallest appropriate scope (account/database/container if available). **Contributor** permissions are generally suitable for services that need to write data; read-only services should use Reader or a narrower custom data role. Creating an account, database, container, or changing management configuration may require a separate **control-plane role**. Having permission to read/write items does not imply permission to provision resources.

For example, an API that only operates on the `orders` container needs data-plane permissions on that container. Do not grant subscription administrator permissions just so a service can write orders. When receiving a 403 error, check the actual principal, role assignment, scope, data action, and endpoint/account.

### 5.2. Enabling Repository Scanning

For explicit repository configuration, you can declare:

~~~java
import com.azure.spring.data.cosmos.repository.config.EnableCosmosRepositories;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCosmosRepositories(basePackages = "com.example.orders.persistence")
public class CosmosRepositoryConfiguration {
}
~~~

If the starter/version in use already enables repository scanning per your application configuration, do not add duplicate scanning configuration. Specify repository packages clearly to avoid scanning the wrong module or creating two repository beans for the same entity.

## 6. Mapping Entities to Containers

Suppose an application manages orders per tenant. Each item has `id`, `tenantId`, status, total amount, and creation timestamp. The container uses `/tenantId` as the partition key:

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

Key annotations:

- `@Container` binds the entity to a container name and certain container settings such as auto-create, TTL, throughput, or partition path depending on the version.
- `@Id` maps a Java field to the item's `id` system property. If the field is already named `id`, the library may map it by convention; using the annotation makes intent explicit.
- `@PartitionKey` identifies the Java field corresponding to the container's partition key.
- `autoCreateContainer = false` is suitable for production when containers are provisioned via IaC/deployment pipelines. This prevents the application from automatically creating or altering data resources unexpectedly on every startup.

The actual container must be created with a partition key path matching the entity, for example `/tenantId`. Annotations do not automatically migrate existing data or change the partition key of an existing container.

## 7. Repositories: CRUD, Derived Queries, and Point Reads

Spring Data Cosmos supports synchronous repositories via `CosmosRepository` and asynchronous repositories via `ReactiveCosmosRepository`. Synchronous example:

~~~java
import com.azure.spring.data.cosmos.repository.CosmosRepository;
import java.util.List;
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

Repositories provide familiar operations such as `save`, `findAll`, find by ID, delete item, and query methods. `@Query` uses the Cosmos DB for NoSQL query language, not JPA's JPQL. You should inspect the query plan/RU charge and check whether the partition key appears in the predicate.

### 7.1. Reading an Item by ID and Partition Key

For a partitioned container, an efficient point read requires **both the item ID and the partition key value**:

~~~java
import com.azure.cosmos.models.PartitionKey;
import java.util.Optional;
import org.springframework.stereotype.Service;

@Service
public class OrderQueryService {
    private final OrderRepository orders;

    public OrderQueryService(OrderRepository orders) {
        this.orders = orders;
    }

    public Optional<OrderDocument> findOrder(
            String tenantId, String orderId) {
        return orders.findById(orderId, new PartitionKey(tenantId));
    }
}
~~~

If only the ID is provided without a partition key, the library may have to perform a broader query depending on the API and version; do not assume every `findById(id)` is a point read. When an endpoint has already authenticated the tenant, pass the verified partition value into the read operation. Never trust an arbitrary partition key supplied by a caller while bypassing authorization.

### 7.2. Derived Queries and Parameterized Queries

The `findByTenantIdAndStatus` example shows that Spring Data can derive a query from a method name. For more complex queries, use `@Query` and `@Param` to write predicates explicitly. Parameter values must be bound, never concatenated from user input into the query string. Queries with a partition key equality filter can generally be routed more efficiently; queries missing a partition key may become cross-partition queries.

Not all Spring Data JPA keywords have the same semantics or are supported in Spring Data Cosmos. Check the documentation/version and the actual generated query before relying on complex derived methods.

### 7.3. Pagination

Spring Data Cosmos supports types such as `Pageable`, `Slice`, and `Sort` depending on the query/API. Cosmos DB uses continuation tokens to resume queries; the number of items returned in a page may be **fewer than the requested page size** due to RU limits/execution conditions. Do not assume a fixed total page count or use large `offset` values like in a relational database without measuring cost.

For large lists, prefer iterating via continuation/next page and fetching only the needed fields. Do not load an entire container into memory just to paginate in Java.

## 8. Choosing a Partition Key by Access Pattern

The partition key determines how items are distributed and how queries are routed. A good key should:

- Have sufficiently high cardinality to distribute data and RUs.
- Appear in common queries, especially point reads or equality filters.
- Have a stable value throughout the item's lifecycle.
- Not create an overly large or overly hot logical partition.

For example, `tenantId` fits well if most requests always operate on a single tenant's data and load across tenants is relatively balanced. If one large tenant generates most of the traffic, `tenantId` can become a **hot partition**. You can consider hierarchical partition keys or synthetic keys, but you must analyze query patterns and transaction requirements first.

| Choice | Pros | Risks |
| --- | --- | --- |
| `/tenantId` | Convenient tenant-scoped queries, tenant data grouped in the same logical partition | An overly large/high-traffic tenant can create a hot partition and hit storage limits |
| `/id` | High cardinality, very convenient point reads when ID is always known | Queries by tenant/status typically become cross-partition |
| Synthetic key such as `tenantId#month` | Distributes data/load by tenant and time | Queries by tenant alone hit multiple partitions; transactions are split |
| Hierarchical key such as `tenantId/orderGroup` | Supports multi-level querying and distribution | Requires designing key level order and matching predicates carefully |

**A partition key is immutable after item creation**. If you need to change the partition key value, you must create the item in the target partition/container and delete the old item; there is no in-place update operation to move an item between logical partitions. Changing the partition key for an existing container typically requires migrating to a new container.

In the API for NoSQL, a logical partition is also the transaction boundary. According to current service documentation, a logical partition has its own storage and throughput limits; check current quotas before designing for extremely large tenants. Do not choose a key merely because a field name is convenient.

## 9. RU, Throughput, and Query Cost

Cosmos DB measures operation cost in **Request Units (RU)**. An RU is a normalized unit of processing, I/O, and memory resources; every read, write, delete, or query request consumes RUs. Responses/diagnostics can provide the request charge so development teams can understand which operations consume resources.

Common throughput modes:

| Mode | Capacity Allocation | Best Fit |
| --- | --- | --- |
| **Provisioned throughput** | Allocates RU/s to a database or container | Steady workloads needing predictable capacity control |
| **Autoscale** | Throughput automatically scales within configured bounds | Fluctuating traffic with peak loads |
| **Serverless** | Billed per RU consumed, no fixed RU/s provisioning needed | Intermittent workloads or low/unpredictable traffic within service limits |

A point read by **ID + partition key** is typically cheaper than a query that scans multiple partitions. Actual RU consumption also depends on item size, number of properties, indexing policy, predicates, number of items returned, consistency, and number of regions.

### 9.1. Indexing Policy

By default, a container has an indexing policy that automatically indexes many properties to support flexible queries. While convenient initially, indexing many fields can increase write RUs and index storage size. For workloads with known query patterns, consider include/exclude paths, composite indexes, and required index types. Changing an indexing policy can trigger an index transformation process; monitor its status before relying on new indexes.

Spring Data Cosmos provides annotations/configuration to customize indexing policies, such as `@CosmosIndexingPolicy` in supported versions. Manage containers/indexes via IaC or controlled migrations in production; do not alter policies ad hoc from multiple application instances.

### 9.2. Query Metrics and Diagnostics

Spring Data Cosmos supports configuring query metrics, index metrics, and response diagnostics via `CosmosConfig` or equivalent version-specific configuration. When a query is slow or consumes high RUs:

1. Record the RU charge, latency, status/substatus, and activity/request ID.
2. Enable query metrics in testing/investigation environments.
3. Check whether the query filters on the partition key, uses an index, and returns too many fields/items.
4. Inspect the indexing policy, document size, pagination, and parallelism.
5. Re-measure with data and throughput close to production.

Do not log credentials, tokens, or full documents containing PII. Diagnostics may contain sensitive metadata; log levels and log access permissions must be configured appropriately.

## 10. Consistency and Multi-Region Distribution

Cosmos DB for NoSQL offers five consistency levels:

1. **Strong** — reads see the latest committed version with linearizability guarantees.
2. **Bounded staleness** — data lag is bounded according to configuration.
3. **Session** — guarantees read-your-writes and monotonic reads within the appropriate session.
4. **Consistent prefix** — write order is preserved, though older states may be read.
5. **Eventual** — replicas converge over time, with no strong ordering guarantees.

The consistency level is configured at the account level and can be relaxed per client/request within service-allowed bounds. Stronger levels can increase read latency/cost and affect availability in multi-region scenarios. Do not pick a consistency level just because its name sounds "strongest"; determine whether the business logic needs read-your-writes, ordering, or stale tolerance.

When multiple regions are enabled, understand preferred regions, read/write regions, failover, and conflict resolution if multi-region writes are enabled. A successful request in one region does not mean every replica immediately observes the same data under all consistency levels. Test read-after-write and failover on a realistic topology if the use case depends on it.

## 11. Transactions, Optimistic Locking, and Atomicity Limits

### 11.1. Transactions Within a Single Logical Partition Only

Cosmos DB for NoSQL supports ACID transactions with snapshot isolation within **the same logical partition key**. You can use a transactional batch to group create/replace/delete/patch point operations in the same partition; if one operation fails, the batch is rolled back. Stored procedures/triggers also have transaction scope limited to a logical partition.

There are no atomic transactions across multiple logical partitions or multiple containers. Therefore, do not apply JPA `@Transactional` thinking and expect updates to items across different tenants to commit/rollback together.

For example, two items with the same `tenantId = tenant-42` can be placed in a transactional batch if they are in the same container and meet API requirements; items belonging to another tenant cannot participate in the same batch transaction.

### 11.2. Optimistic Locking with ETag

Spring Data Cosmos supports optimistic locking for supported containers/operations. You can map the ETag to the `_etag` field using `@Version`:

~~~java
import com.azure.spring.data.cosmos.core.mapping.Container;
import com.azure.spring.data.cosmos.core.mapping.PartitionKey;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;

@Container(containerName = "inventory")
public class InventoryItem {
    @Id
    private String id;

    @PartitionKey
    private String warehouseId;

    private int availableQuantity;

    @Version
    private String _etag;

    public InventoryItem() {}
}
~~~

When two processes read the same version and attempt to update it, the operation from the process using the stale ETag can be rejected rather than silently overwriting newer data. The application service needs to catch the conflict, re-read, and apply business rules (such as recalculating inventory). Never blindly retry updates with a stale payload.

## 12. Change Feed and Processing Changes

Change Feed allows applications to read item changes to build projections, sync search indexes/caches, emit events, or move data to other systems. This is an SDK/processor-level API; do not confuse it with calling `findAll()` on a schedule.

Key points:

- Change order is guaranteed within a partition key value; there is no global ordering across partition keys.
- Latest version mode focuses on the latest version of an item; intermediate updates may not be emitted if an item changes rapidly multiple times.
- Latest version mode does not provide delete events as a complete log; soft-delete markers can be used if consumers need to know about deletions.
- All versions and deletes mode has retention tied to the account's continuous backup; do not treat it as an infinitely retained event log.
- Consumers need checkpointing, idempotent processing, lag monitoring, and a recovery strategy on restart.

If using the change feed to publish events to a message broker, do not assume reading the feed and publishing the event form a single transaction. Persist checkpoints at the right time and handle the case where publishing succeeds before the checkpoint is saved (events may be replayed).

## 13. Error Handling and Retries

| Symptom | Causes to Check | Remediation |
| --- | --- | --- |
| **401/403** | Invalid token/key, wrong identity, missing native data-plane role or scope | Verify principal, Entra token, role assignment, and data permissions |
| **404** | Wrong endpoint/account/database/container, item does not exist, or wrong partition key | Check resource name, database, container, item ID, and partition value |
| **409 Conflict** | Item ID/unique key already exists or operation-level conflict | Map to a business conflict; do not retry like a network error |
| **412 Precondition Failed** | ETag/version/precondition is no longer valid | Re-read, handle optimistic concurrency, and decide whether to re-apply |
| **429 Too Many Requests** | Exceeded RU/s or hot partition | Honor retry-after, reduce concurrency, optimize partition/query/index, and evaluate throughput |
| Timeout / connection error | Network, endpoint, TLS, DNS, or lost response | Check diagnostics; for writes, the outcome may be uncertain so use operation IDs/idempotency |
| Slow query, high RUs | Cross-partition, unsuitable index, large payload/query | Inspect query metrics, partition predicates, projections, and indexing policy |

The Cosmos SDK includes retry mechanisms for certain throttling/transient errors. Do not add unbounded retries in an outer repository/service; stacked retry layers can multiply request counts. Bound total deadlines, concurrency, and retry attempts; honor `Retry-After` when provided by the SDK.

For timed-out writes, you cannot always conclude the item was not written. Use stable IDs/operation IDs, read-back verify by partition key, and design idempotency before resending. Upsert semantics on `save` are not a substitute for a "create once only" business rule.

## 14. Testing with the Emulator and Real Azure

### 14.1. Unit Tests

Application service unit tests should mock repositories/ports to verify business rules: which tenant can be accessed, which states transition, and what data is saved. No Azure credentials or network access are required.

### 14.2. Cosmos DB Emulator

The Azure Cosmos DB Emulator provides a local development/testing environment for supported APIs. The emulator's HTTPS certificate is **self-signed**; the Java runtime needs to trust the certificate per emulator instructions before the SDK connects. Do not arbitrarily disable TLS verification just to make tests pass.

Integration tests should verify:

- Entities serialize/deserialize properly, with `id` and partition key fields populated.
- Repository save/read/query work within the expected partition.
- Cross-partition queries and pagination behave as expected.
- Optimistic locking/conflicts are mapped properly.
- Container provisioning and indexing policies are not unexpectedly modified.

### 14.3. Cloud Integration Tests

The emulator does not replace testing identity and role assignments on real Azure. Create a dedicated test account/database/container, use Managed Identity or a test principal, grant least-privilege native data-plane roles, and verify:

- Entra ID tokens are acquired from the intended workload identity.
- Data-plane roles grant access at the right scope.
- Endpoints, preferred regions, firewalls/private networks, and DNS are configured correctly.
- RUs, throttling, diagnostics, and failover match workload expectations.
- Cleanup never deletes shared resources or production data.

## 15. End-to-End Flow Example: Creating and Finding an Order

A simple use case might follow this path:

~~~text
POST /tenants/{tenantId}/orders
  -> Controller authenticates request
  -> Application service verifies tenant/caller
  -> Creates OrderDocument with id and tenantId
  -> OrderRepository.save(document)
  -> Spring Data Cosmos / CosmosTemplate
  -> Azure Cosmos DB Java SDK
  -> Cosmos DB container orders
  <- Stored item / diagnostics / RU charge
  <- HTTP 201

GET /tenants/{tenantId}/orders/{orderId}
  -> Application service
  -> OrderRepository.findById(orderId, PartitionKey(tenantId))
  -> Point read by id + partition key
  <- OrderDocument or not found
~~~

In this flow, the tenant ID must come from the authenticated context or have ownership verified. Never allow callers to supply an arbitrary partition key and read items outside their authorized scope. If the service returns sensitive data, filter fields at the application/DTO layer before sending the response.

## 16. Common Design Pitfalls

| Pitfall | Consequence | Fix |
| --- | --- | --- |
| Choosing a partition key based on an easy-to-write field rather than query patterns | Cross-partition queries, high RUs, or hot partitions | Design around access patterns and load distribution |
| Using `findById(id)` without passing the partition key when the key is already known | May lose point-read benefits or trigger a broader query | Use the appropriate overload accepting the partition key |
| Treating Cosmos DB like SQL Server/JPA | Expecting unsupported equivalent joins/transactions | Design documents and denormalize around queries |
| Auto-creating containers on every production startup | Hard to control throughput/index/partition policies | Provision via IaC; disable auto-create where appropriate |
| Indexing every field without measuring | Higher write RUs and index storage | Tune indexing policy to match queries |
| Ignoring RU charges and 429s | Repeated throttling, increased latency | Monitor RUs, retry-after, autoscale/provisioned throughput |
| Using account keys in committed appsettings | Credential exposure, hard rotation | Managed Identity + native data-plane RBAC |
| Using transactions across items in multiple partitions | Lacks expected atomicity | Place items needing atomicity in the same partition or use saga/outbox |
| Treating the change feed as a lossless/duplicate-free event log | Missing intermediate updates or duplicate processing | Choose the right mode, checkpoint, and build idempotent consumers |
| Testing only against the emulator | Misses missing RBAC, private endpoints, and quotas | Add cloud smoke tests using real identities |

## 17. Practice Exercises

**Exercise 1 — Choosing a partition key.** A SaaS application stores orders across many tenants. Most queries fetch orders by tenant and status; one large tenant generates 40% of the traffic. Compare `/tenantId`, `/id`, and a hierarchical partition key. Propose how to avoid a hot partition while keeping key queries efficient.

**Exercise 2 — Repository and point read.** Write an `OrderDocument` entity with `@Container`, `@Id`, and `@PartitionKey`; write an `OrderRepository` with a derived query by tenant/status. Explain why looking up an item by ID requires the partition key value.

**Exercise 3 — RUs and indexing.** A query filtering by tenantId, status, and createdAt consumes high RUs. Inspect the partition predicate, index policy, returned fields, page size, and query metrics. Propose changes and a before/after measurement approach.

**Exercise 4 — Optimistic locking.** Two workers read the same inventory item and update its quantity. Use `@Version` with ETag to prevent lost-update overwrites. Describe how to handle 412 and test the race condition.

**Exercise 5 — Transactional batch.** An order and its order lines must be written atomically. Identify why the items must share the same partition key, design the batch, and state what happens if one operation fails. What changes if order lines belong to a different partition?

**Exercise 6 — Identity.** Migrate an application from account keys to Managed Identity. Explain the difference between Azure management-plane roles and Cosmos DB native data-plane roles; determine least-privilege permissions for a read-only service and a write-enabled service.

**Exercise 7 — Change Feed.** A projection updates a search index from the change feed. Design checkpointing, idempotency, and delete handling; explain why ordering is only guaranteed within a partition key value and why latest version mode can skip intermediate updates.

**Exercise 8 — Test strategy.** Design unit tests, emulator integration tests, and cloud smoke tests for a Cosmos DB repository. List what the emulator cannot prove regarding identity, RBAC, networking, and quotas.

## 18. Key Takeaways

- **Spring Data Cosmos is a Spring Data layer for Azure Cosmos DB for NoSQL**, not JPA for a relational database. Repositories use the underlying Cosmos client/SDK.
- **The partition key governs routing, RUs, hot partitions, and transaction scope.** Choose it based on access patterns; a partition key value cannot be changed in place after an item is created.
- **Point reads require both item ID and partition key.** Queries without a partition predicate can cost more RUs and latency; measure query metrics and request charges.
- **RUs are the processing cost unit for each operation.** Item size, indexing, query shape, consistency, and region count all impact consumption.
- **ACID transactions/transactional batches stay within a single logical partition key.** For concurrent updates, use ETag/`@Version` and handle conflicts.
- **Managed Identity + Cosmos DB native data-plane RBAC** is the preferred choice for workloads on Azure; resource management permissions and data read/write permissions are two distinct scopes.
- The emulator helps with integration testing, but does not replace cloud tests for identity, RBAC, networking, quotas, and failover.

## 19. References

- [Azure Cosmos DB Developer Guide for Java](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/how-to-guides-spring-data-cosmosdb)
- [Azure Spring Data Cosmos client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/spring-data-cosmos-readme?view=azure-java-stable)
- [Spring Cloud Azure — modules, starters, and BOM](https://github.com/Azure/azure-sdk-for-java/tree/main/sdk/spring)
- [Partitioning and horizontal scaling](https://learn.microsoft.com/en-us/azure/cosmos-db/partitioning)
- [Request Units in Azure Cosmos DB](https://learn.microsoft.com/en-us/azure/cosmos-db/request-units)
- [Consistency level choices](https://learn.microsoft.com/en-us/azure/cosmos-db/consistency-levels)
- [Transactional batch operations](https://learn.microsoft.com/en-us/azure/cosmos-db/transactional-batch)
- [Connect using role-based access control and Microsoft Entra ID](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/how-to-connect-role-based-access-control)
- [Change Feed design patterns](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/change-feed-design-patterns)
