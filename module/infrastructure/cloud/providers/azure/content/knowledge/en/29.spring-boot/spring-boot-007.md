# Integrating Cosmos DB with Spring Data

## 1. Problem: Spring Boot Needs to Store NoSQL Documents on Azure

A Spring Boot service manages orders for multiple stores. Each order has an identifier, tenant, customer, status, monetary amount, and update timestamp. The system needs to:

- Store JSON documents without designing relational tables for every additional attribute.
- Read and update orders by tenant while isolating data between customers.
- Run reliably when request rates surge and Azure Cosmos DB returns throttling responses.
- Authenticate using **Microsoft Entra ID/managed identity** when deployed on App Service, Azure Functions, or AKS.
- Monitor **RU/s, HTTP 429, latency, request charges, and cost**.
- Support testing, multi-environment deployments, and failure recovery.

**Spring Data Cosmos** lets you use familiar entities, repositories, and Spring Data conventions to work with **Azure Cosmos DB for NoSQL**. However, using a repository does not remove distributed-system constraints: **partition keys, throughput, consistency, idempotency, and authorization** still require careful design.

This lesson belongs to the **Spring Boot on Azure** chapter in the **CLOUD_PROVIDERS_AZURE** module. The overarching context is building Azure applications from subscriptions/resource groups, Microsoft Entra ID, virtual networking, compute, and storage through monitoring, security, and cost control. This content focuses on *integrating Cosmos DB with Spring Data* and does not replace dedicated lessons covering every Cosmos DB API.

## 2. Learning Objectives

After this lesson, you can:

1. Explain a Cosmos account, database, container, item, logical/physical partitions, and RUs.
2. Distinguish **Azure Cosmos DB for NoSQL** from MongoDB/Cassandra/Gremlin APIs and other SDKs.
3. Choose the **Spring Cloud Azure Starter Data Cosmos** dependency compatible with your Spring Boot version.
4. Configure endpoints, databases, and credentials without hard-coding secrets.
5. Build entities with **@Container**, **@Id**, **@PartitionKey** and repositories with **CosmosRepository**.
6. Implement save, find, query, and delete operations aligned with access patterns.
7. Recognize when a Spring Data repository call is not equivalent to an efficient point read.
8. Integrate async/reactive flows with **ReactiveCosmosRepository**, `Mono`/`Flux`, and WebFlux when appropriate.
9. Estimate RU/s, recognize HTTP 429 throttling, and apply bounded retries and backpressure.
10. Understand optimistic concurrency, ETags, and transaction boundaries.
11. Enforce tenant authorization boundaries and data-plane RBAC for managed identities.
12. Design indexing, TTL, schema evolution, and partition key migrations.
13. Monitor latency, request charges, partition skew, errors, and budgets.
14. Test with mocks/labs, build an API with proper error mapping, and deploy safely on Azure.

## 3. Where Does Spring Data Cosmos Sit in the Architecture?

A typical architecture:

~~~mermaid
flowchart LR
    USER[Web / Mobile] --> API[Spring Boot REST API]
    API --> AUTH[Authentication + Authorization]
    AUTH --> SVC[OrderService]
    SVC --> REPO[Spring Data Cosmos Repository]
    REPO --> SDK[Azure Cosmos Java SDK]
    SDK --> NET[HTTPS / Private Endpoint]
    NET --> DB[(Azure Cosmos DB for NoSQL)]
    ID[Microsoft Entra / Managed Identity] --> SDK
    API --> OBS[Application Insights]
    DB --> MON[Azure Monitor]
~~~

Here:

- **Spring MVC/WebFlux** receives and responds to HTTP requests.
- **Business service** enforces business rules and authorization.
- **Spring Data Cosmos** maps Java documents to items and generates repository query methods.
- **Cosmos DB Java SDK v4** is the client layer communicating with Cosmos DB for NoSQL.
- **Cosmos DB service** stores data and manages partitioning, indexing, replication, and throughput.
- **Azure Monitor/Application Insights** monitors both the database and application tiers.

**A repository is a programming abstraction, not a security boundary.** Just because the app can read a container does not mean every HTTP caller may read every item.

## 4. Service Scope: Cosmos DB for NoSQL

Spring Data Cosmos covered here targets **Azure Cosmos DB for NoSQL**, whereas Azure Cosmos DB also supports other APIs and models.

| Component | Role |
|---|---|
| **Cosmos account** | Azure resource holding endpoint, regions, authentication, and service settings |
| **Database** | Logical grouping of containers |
| **Container** | Collection of JSON items, partition key path, indexing/TTL/throughput |
| **Item** | JSON document with an `id` property and business fields |
| **Logical partition** | Items sharing the same partition key value |
| **Physical partition** | Underlying infrastructure unit serving data and capacity managed by the service |
| **RU** | Request Unit, the measure of resource cost for an operation |
| **RU/s** | Request unit capacity per second per capacity model |
| **429** | Request throttled due to insufficient capacity in the relevant scope |

### 4.1. Do Not Confuse Spring Data Cosmos with Spring Data MongoDB

Cosmos DB offers a separate MongoDB API, whereas **Spring Data Cosmos** uses the Cosmos DB for NoSQL SDK and query model. Never mix MongoDB dependencies or query annotations into this pattern.

### 4.2. Do Not Confuse Flexible JSON with "No Schema Needed"

Documents can vary in attributes, yet your Java application still needs validation, schema versioning, and a migration strategy. A type change from number to string can still break deserialization.

### 4.3. When Should You Avoid Cosmos DB?

If your workload relies heavily on complex joins, relational transactions spanning multiple aggregates, or OLAP reporting scanning massive datasets, compare Azure SQL, PostgreSQL, analytics engines, and Cosmos DB against real access patterns. Never choose NoSQL solely for entity-mapping convenience.

## 5. Design the Data Model Before Writing the Repository

An example document:

~~~json
{
  "id": "ORD-1001",
  "tenantId": "shop-42",
  "customerId": "C-20",
  "status": "CREATED",
  "amountMinor": 125000,
  "updatedAtUtc": "2026-11-20T10:00:00Z",
  "schemaVersion": 1
}
~~~

Container **orders** uses partition key path **/tenantId**.

### 5.1. Partition Key Path vs. Partition Key Value

- **/tenantId** is the field path configured on the container.
- **shop-42** is the document's partition key value.
- **id + tenantId** together identify an item for point reads, updates, and deletes.
- Two items in different tenants can share the same `id` within their own logical partitions.

### 5.2. Why Does `tenantId` Fit Some Applications?

Operations frequently query orders for a single tenant. Filtering by `tenantId` scopes queries tightly, especially in multi-tenant apps. However, if one tenant generates the bulk of writes, **/tenantId** risks creating a hot logical partition.

### 5.3. Choose the Partition Key Around Access Patterns

| Model | Partition key to consider | Trade-off |
|---|---|---|
| Multi-tenant orders | `/tenantId` | A very large tenant can become a hot key |
| User profiles | `/userId` | Convenient point reads per user |
| IoT telemetry | `/deviceId` | High-volume devices can run hot |
| User shopping carts | `/customerId` | Fits customer queries; check distribution |
| Heavily skewed load | Synthetic or hierarchical partition key | Complex query routing and transaction boundaries |

**There is no single optimal partition key for every system.** Analyze data volume, peak load, queries, and transaction boundaries before creating the container.

## 6. RUs, Throughput, and Why They Matter Early

Cosmos DB bills request charges in **Request Units (RUs)**. Charges depend on operation type, data size, indexing, query complexity, payload size, and other factors.

Hypothetical examples:

| Operation | Measured RUs in example |
|---|---:|
| Small-item point read | 1 |
| Create item | 5 |
| Single-logical-partition query | 12 |
| Cross-partition query | 80 |

**These numbers are illustrative only**, not fixed Cosmos DB pricing or charges. Always measure on your actual workload.

If a container has 1,000 RU/s and each request averages 5 RUs, the theoretical RU ceiling is about 200 requests/second, before accounting for bursts, hot partitions, and other bottlenecks:

\[
\text{requests/second} \approx \frac{\text{available RU/s}}{\text{average RU/request}}
\]

### 6.1. Capacity Models

- **Manual provisioned throughput:** configures a steady RU/s allocation.
- **Autoscale provisioned throughput:** scales within configured bounds under supported rules.
- **Serverless:** billed per consumption within the mode's feature and scale limits.

Autoscale and serverless **do not guarantee zero HTTP 429s**. A hot logical partition can still hit physical partition limits even when total container RU/s looks underutilized.

### 6.2. Database-Level vs. Container-Level Throughput

Some setups let multiple containers share database-level throughput; others provision throughput per container. When workloads share an RU budget, a batch job on one container can starve an interactive API on another.

### 6.3. Repository Abstractions Do Not Erase Request Charges

`findAll()`, derived queries, and paging still consume RUs and can fan out across partitions. Choosing the right query matters far more than keeping Java code brief.

## 7. Preparing the Lab Environment

Assumed prerequisites:

- JDK 17+ matching your chosen Spring Boot and SDK versions.
- Maven or Gradle per project standards.
- Spring Boot and Spring Cloud Azure releases that are **officially compatible with each other**.
- Lab Azure subscription/resource group, quota, and budget.
- Azure Cosmos DB **for NoSQL** account and database **shopdb**.
- Container **orders** with partition key path **/tenantId**.
- Authorized Azure identity/data-plane role or lab key.
- Network path from the Java runtime to the Cosmos endpoint.

### 7.1. Never Auto-Create Production Resources at Startup

Provision databases, containers, indexing policies, and throughput via IaC and approvals in production. Never let a Java service adjust RU/s or recreate containers whenever a Pod scales out.

### 7.2. Keep One Verified Dependency Path

Learning examples use **Spring Cloud Azure Starter Data Cosmos** rather than mixing in legacy deprecated Cosmos Spring Data libraries. Check the compatibility matrix across **Spring Boot**, **Spring Cloud Azure**, and the Azure SDK beforehand.

### 7.3. Permissions and Networking Are Separate Concerns

An app with the proper data-plane role still cannot connect if private DNS is misconfigured. Conversely, resolving the endpoint does not grant a user or managed identity permission to read the container.

## 8. Maven Dependencies: Spring Cloud Azure Starter Data Cosmos

Sample **`pom.xml` fragment**:

~~~xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.azure.spring</groupId>
      <artifactId>spring-cloud-azure-dependencies</artifactId>
      <version>VERSION_COMPATIBLE_WITH_SPRING_BOOT</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
  </dependency>
  <dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-data-cosmos</artifactId>
  </dependency>
</dependencies>
~~~

**VERSION_COMPATIBLE_WITH_SPRING_BOOT** is a placeholder that must be replaced with an approved, compatible BOM version. Spring Boot, Spring Data, Spring Cloud Azure, and Cosmos SDK versions evolve over time; this lesson does not assert a single fixed number for every project.

### 8.1. Why Use the BOM?

The BOM aligns compatible Azure library versions, reducing the risk of mixing **azure-core**, **azure-cosmos**, and starters from mismatched generations.

### 8.2. Do You Need to Add `azure-cosmos` Directly?

The starter normally pulls the core libraries required. If you invoke **CosmosClient** directly or use extra SDK features, inspect the dependency tree and declare it explicitly only if needed, governed by the BOM. Never pin an arbitrary `azure-cosmos` version that breaks compatibility.

### 8.3. Java / Spring Boot Compatibility

Spring Boot 3.x typically requires Java 17+, while other Boot releases have different requirements. Verify your Java baseline, migration notes, and dependency security policies when choosing a release.

## 9. Configuring the Spring Boot Application

Common property settings for **Spring Cloud Azure Cosmos integration**:

~~~properties
spring.application.name=orders-api
spring.cloud.azure.cosmos.endpoint=https://YOUR_ACCOUNT.documents.azure.com:443/
spring.cloud.azure.cosmos.database=shopdb
~~~

Replace endpoint, account, and database with your actual lab resources. In cloud environments, never put API keys inside committed property files.

### 9.1. Configuration via Environment Variables

Spring Boot supports relaxed binding; matching environment variables typically look like:

~~~text
SPRING_CLOUD_AZURE_COSMOS_ENDPOINT
SPRING_CLOUD_AZURE_COSMOS_DATABASE
~~~

In lab environments that allow only key-based auth, inject the secret into **spring.cloud.azure.cosmos.key** via a secret store or the corresponding environment variable:

~~~text
SPRING_CLOUD_AZURE_COSMOS_KEY
~~~

**Never commit real secrets**, and never place them in READMEs, container images, or Dockerfiles.

### 9.2. Identity-Based Auth

In Azure environments supporting Entra-based authentication, configure `TokenCredential`/managed identity for your starter version, and **never include account keys in production config**. Some versions support multiple credential routes with slightly different properties; check the docs for your exact version.

### 9.3. Misconfigurations Commonly Mistaken for Database Failures

- The Cosmos DB endpoint must be the **account endpoint**, not the Azure Portal URL.
- The database name must match the provisioned resource.
- The data-plane role must belong to the actual runtime identity.
- DNS/TLS/firewalls must allow connectivity from the runtime.
- The starter version must match the Spring Boot release.

### 9.4. Never Mix Configuration Property Families

Properties from an older Spring Cloud Azure generation or legacy SDK configuration may be ignored by the current starter. Inspect actual auto-configuration bindings rather than stacking two overlapping configs.

## 10. Sample Data Model and Entity Mapping

Entity model stored in the **orders** container:

~~~java
package example.orders.data;

import com.azure.spring.data.cosmos.core.mapping.Container;
import com.azure.spring.data.cosmos.core.mapping.PartitionKey;
import org.springframework.data.annotation.Id;

@Container(containerName = "orders")
public class OrderDocument {

    @Id
    private String id;

    @PartitionKey
    private String tenantId;

    private String customerId;
    private String status;
    private long amountMinor;
    private String updatedAtUtc;
    private int schemaVersion;

    public OrderDocument() { }

    public OrderDocument(
            String id, String tenantId, String customerId,
            String status, long amountMinor, String updatedAtUtc) {
        this.id = id;
        this.tenantId = tenantId;
        this.customerId = customerId;
        this.status = status;
        this.amountMinor = amountMinor;
        this.updatedAtUtc = updatedAtUtc;
        this.schemaVersion = 1;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getTenantId() { return tenantId; }
    public void setTenantId(String tenantId) {
        this.tenantId = tenantId;
    }

    public String getCustomerId() { return customerId; }
    public void setCustomerId(String customerId) {
        this.customerId = customerId;
    }

    public String getStatus() { return status; }
    public void setStatus(String status) {
        this.status = status;
    }

    public long getAmountMinor() { return amountMinor; }
    public void setAmountMinor(long amountMinor) {
        this.amountMinor = amountMinor;
    }

    public String getUpdatedAtUtc() { return updatedAtUtc; }
    public void setUpdatedAtUtc(String updatedAtUtc) {
        this.updatedAtUtc = updatedAtUtc;
    }

    public int getSchemaVersion() { return schemaVersion; }
    public void setSchemaVersion(int schemaVersion) {
        this.schemaVersion = schemaVersion;
    }
}
~~~

### 10.1. @Container

**@Container(containerName = "orders")** binds the entity to the Cosmos container. Provision the container with the exact name and partition key path before running in production.

### 10.2. @Id

**@Id** maps the document identifier. In a partitioned container, **id + partition key value** form the complete address for point operations; `id` alone may not suffice.

### 10.3. @PartitionKey

**@PartitionKey** on **tenantId** must match the container's partition key path **/tenantId**. Do not confuse Java field names, JSON serialization names, and container paths.

### 10.4. Timestamps and Money

This example stores **amountMinor** in the currency's smallest integer unit to avoid floating-point rounding errors. **updatedAtUtc** uses an ISO-8601 string for readability; production may use `Instant`/`OffsetDateTime` with verified serialization mappings.

### 10.5. Constructors, Getters, and Schema Evolution

Spring Data mapping requires valid instantiation/deserialization per framework version. A no-args constructor and getters/setters keep the example clear; real data also requires validation, schema versioning, migrations, and handling older documents with missing fields.

## 11. Defining `CosmosRepository`

A simple repository:

~~~java
package example.orders.data;

import com.azure.spring.data.cosmos.repository.CosmosRepository;
import org.springframework.stereotype.Repository;

import java.util.List;

@Repository
public interface OrderRepository
        extends CosmosRepository<OrderDocument, String> {

    List<OrderDocument> findByTenantId(String tenantId);

    List<OrderDocument> findByTenantIdAndStatus(
        String tenantId, String status);

    List<OrderDocument> findByCustomerIdAndTenantId(
        String customerId, String tenantId);
}
~~~

### 11.1. What Spring Data Handles for You

- Maps Java entities to/from JSON items.
- Provides CRUD and repository abstractions.
- Generates derived query methods following Spring Data Cosmos conventions.
- Integrates configured clients from the Spring context.
- Simplifies dependency injection and unit testing.

### 11.2. Do Not Assume `findById` Always Equals an Optimal Partition Read

A repository method taking only **id** without a partition key does not behave identically to a **point read with `id` + `tenantId`** across all implementations and setups. To optimize RUs and authorization, measure query plans/charges or call the Cosmos SDK directly when strict point operations are needed.

### 11.3. Repository Methods Do Not Enforce Authorization

`findByTenantId("shop-42")` is strictly a data query. The backend must verify the caller is authorized for `shop-42` before calling it.

### 11.4. Never Call `findAll()` in Normal HTTP Requests

On a container holding millions of items, `findAll()` scans broadly, burning RUs, network bandwidth, and JVM heap; enforce filters, pagination, and quotas in APIs.

## 12. Derived Queries and Parameterized Queries

More complex queries can use Spring Data Cosmos's **@Query** annotation following the Cosmos DB for NoSQL SQL-style contract:

~~~java
package example.orders.data;

import com.azure.spring.data.cosmos.repository.CosmosRepository;
import com.azure.spring.data.cosmos.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.List;

public interface OrderQueryRepository
        extends CosmosRepository<OrderDocument, String> {

    @Query("SELECT * FROM c WHERE c.tenantId = @tenantId "
         + "AND c.status = @status")
    List<OrderDocument> findByTenantStatusQuery(
        @Param("tenantId") String tenantId,
        @Param("status") String status);
}
~~~

**Note:** exact custom query syntax and parameter binding depend on your Spring Data Cosmos version. Run integration tests against your project's actual starter before production.

### 12.1. Derived Queries Can Implicitly Generate SQL Queries

`findByTenantIdAndStatus` is readable, yet it does not guarantee a point read. With many matching documents, returning a `List` can pull large datasets into memory; cap result sizes at the API boundary.

### 12.2. Partition-Scoped vs. Cross-Partition Queries

When a query filters by `tenantId`, execution targets that logical partition. Filtering solely by `status` when statuses span many tenants fans out across partitions and consumes more RUs.

### 12.3. Custom Queries Still Depend on Indexing Policies

Writing `@Query` does not automatically create optimal indexes for every access pattern. Identify fields used in `WHERE`/`ORDER BY`, estimate request charges, and tune indexing policies accordingly.

### 12.4. SQL Injection and Identifiers

Never concatenate user input into query strings. Always bind parameters via the SDK/repository API. If dynamic queries must choose field or container names, pull identifiers strictly from a backend allowlist.

## 13. Separating REST Controller, Service, and Repository

A suggested package layout:

~~~text
example.orders
  OrdersApplication.java
  api/
    OrderController.java
    CreateOrderRequest.java
    OrderResponse.java
  service/
    OrderService.java
    TenantAuthorization.java
  data/
    OrderDocument.java
    OrderRepository.java
  config/
    CosmosConfiguration.java
  monitoring/
    CosmosMetrics.java
~~~

### 13.1. Services Own Business Rules

Repositories perform data operations only. Services must:

- Derive the **trusted tenant** from the authenticated principal/context.
- Validate request fields.
- Assign server-side idempotency/business operation IDs.
- Select the proper persistence pattern.
- Verify authorization before querying, updating, or deleting.
- Translate Cosmos exceptions into domain errors.

### 13.2. DTOs Differ from Entities

Never accept a raw **OrderDocument** from a client and persist it verbatim: a caller could supply a different `tenantId`, a `PAID` status, a fake `schemaVersion`, or someone else's `id`. DTOs should expose only caller-permitted input fields.

~~~java
package example.orders.api;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record CreateOrderRequest(
    @NotBlank String customerId,
    @Min(1) long amountMinor
) {}
~~~

### 13.3. Derive Tenant from Identity, Not from the Request Body

If a user sends `"tenantId": "admin-tenant"` in the JSON body, the controller must never trust it. The tenant must come from verified claims/sessions and application authorization policy.

## 14. `OrderService`: Writing and Querying by Tenant

Example service for creating orders and listing by tenant:

~~~java
package example.orders.service;

import example.orders.api.CreateOrderRequest;
import example.orders.data.OrderDocument;
import example.orders.data.OrderRepository;
import org.springframework.stereotype.Service;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

@Service
public final class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public OrderDocument create(
            String authorizedTenant,
            CreateOrderRequest request) {

        if (authorizedTenant == null
                || authorizedTenant.isBlank()) {
            throw new IllegalArgumentException("Tenant required");
        }
        if (request.amountMinor() <= 0) {
            throw new IllegalArgumentException("Invalid amount");
        }

        OrderDocument item = new OrderDocument(
            UUID.randomUUID().toString(),
            authorizedTenant,
            request.customerId(),
            "CREATED",
            request.amountMinor(),
            Instant.now().toString()
        );

        return repository.save(item);
    }

    public List<OrderDocument> listByTenant(
            String authorizedTenant) {
        return repository.findByTenantId(authorizedTenant);
    }
}
~~~

**Illustrates data access only.** Callers are responsible for authenticating and authorizing the tenant; production code also requires item caps, pagination, idempotency, and error mapping.

### 14.1. Watch Out for `UUID.randomUUID()` When Retrying POST

If the first write succeeds yet the response drops, a client retry generating a brand-new UUID creates **two orders**. Enforce a client-supplied **idempotency key**, a marker record, or a stable operation ID with duplicate detection.

### 14.2. `save` Is Not a Multi-Service Business Transaction

`repository.save` creates or updates a single document per library semantics. It does not make payment processing, email delivery, and Service Bus publishing atomic.

### 14.3. Never Accept Client-Specified Order Status

The application sets `CREATED` itself. Transitions to `PAID` or `SHIPPED` require business validation and optimistic concurrency—never allow arbitrary client upserts.

### 14.4. Lists Must Not Be Unbounded

Returning `List` keeps the sample concise. Production HTTP APIs must use filters, paging/continuation tokens, maximum page sizes, and request deadlines; loading all orders for a massive tenant risks memory and RU exhaustion.

## 15. REST Controller and HTTP Error Contract

Example controller skeleton:

~~~java
package example.orders.api;

import example.orders.data.OrderDocument;
import example.orders.service.OrderService;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/orders")
public class OrderController {
    private final OrderService service;
    private final TenantAuthorization tenantAuth;

    public OrderController(
            OrderService service,
            TenantAuthorization tenantAuth) {
        this.service = service;
        this.tenantAuth = tenantAuth;
    }

    @PostMapping
    public ResponseEntity<OrderDocument> create(
            @Valid @RequestBody CreateOrderRequest request) {
        String tenant = tenantAuth.requireAuthorizedTenant();
        OrderDocument item = service.create(tenant, request);
        return ResponseEntity.status(201).body(item);
    }

    @GetMapping
    public ResponseEntity<List<OrderDocument>> list() {
        String tenant = tenantAuth.requireAuthorizedTenant();
        return ResponseEntity.ok(
            service.listByTenant(tenant));
    }
}
~~~

**`TenantAuthorization` is an application interface/service, not a built-in Spring Cloud Azure class.** No implementation is shown here; implement it using Spring Security and verified tenant policies. Return response DTOs instead of exposing raw entities with internal fields in production.

### 15.1. Recommended HTTP Mapping

| Case | API response |
|---|---|
| Invalid request | 400 Bad Request |
| Unauthenticated | 401 Unauthorized |
| Unauthorized tenant/document | 403 Forbidden or 404 hiding existence per policy |
| Item not found | 404 Not Found |
| Duplicate business request | 409 Conflict or idempotent replay response |
| ETag/precondition conflict | 409/412 per API contract |
| Cosmos DB throttling/timeout | 429/503 or overload response with `Retry-After` per contract |
| Other dependency failures | 5xx with correlation ID and telemetry |

### 15.2. Never Expose Raw Cosmos Exceptions

Raw exceptions can leak endpoints, metadata, SQL queries, or sensitive details. Use `@RestControllerAdvice` and redacted logs to translate failures into clean status codes.

### 15.3. A Controller Without Authentication Is Incomplete

This skeleton relies on `TenantAuthorization` for clarity. In production, Spring Security must verify JWT/OIDC tokens, map principals to tenants, and enforce object-level access controls.
## 16. Repository Queries and Point Reads Are Not the Same

In Cosmos DB for NoSQL, the most efficient way to fetch a known item is a **point read** using:

- the exact **id**;
- the exact **partition key value**.

For example, fetching `ORD-1001` belonging to `shop-42`:

~~~text
id = ORD-1001
partitionKeyValue = shop-42
~~~

A repository method like `findByTenantIdAndStatus` executes a **query** over fields and can scan multiple items. Calling `findById(id)` does not always accept an independent partition key value in every repository contract; never assume it always runs as a point read.

### 16.1. When Are Queries Appropriate?

- Finding multiple orders by status.
- Reading a customer's order history.
- Retrieving paginated lists.
- Filtering on multiple indexed fields.

### 16.2. When Is a Point Read Better?

- Viewing details of one order with known `id` and `tenant`.
- Reading the state of a workflow object.
- Checking an idempotency marker.
- Updating a document using its ETag.

### 16.3. Spring Data Cosmos or Cosmos SDK Directly?

| Need | Tool |
|---|---|
| Standard CRUD and query methods | `CosmosRepository` |
| Reactive queries/services | `ReactiveCosmosRepository` |
| Exact point reads with partition key | Cosmos DB Java SDK v4 or verified template API |
| Granular diagnostics, RUs, ETags, request options | SDK v4 is typically more transparent |
| Transactional batch within one partition | Cosmos SDK transactional batch |
| Complex aggregations/reporting | Purpose-built query/sink architecture, not just repositories |

Not every app needs raw SDK calls everywhere, yet **pairing a repository with an SDK adapter** works well for operations needing strict partition control or response metadata.

## 17. Cosmos SDK v4: Point Read with `tenantId` and Request Charge

An adapter using SDK v4 for point reads:

~~~java
package example.orders.data;

import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;
import com.azure.identity.DefaultAzureCredentialBuilder;

public final class OrderPointReader {
    private final CosmosContainer container;

    public OrderPointReader(CosmosClient client) {
        this.container = client
            .getDatabase("shopdb")
            .getContainer("orders");
    }

    public OrderDocument read(String orderId, String authorizedTenant) {
        CosmosItemResponse<OrderDocument> response =
            container.readItem(
                orderId,
                new PartitionKey(authorizedTenant),
                OrderDocument.class);

        double ru = response.getRequestCharge();
        System.out.println("Point read RU=" + ru);
        return response.getItem();
    }

    public static CosmosClient newClient(String endpoint) {
        return new CosmosClientBuilder()
            .endpoint(endpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
    }
}
~~~

### 17.1. Prerequisites for This Pattern

- Compatible Java Cosmos SDK v4 and Azure Identity versions.
- Cosmos account for NoSQL configured to allow Microsoft Entra authentication.
- Principal granted a **Cosmos DB data-plane role** for read access.
- Database **shopdb** and container **orders** already exist.
- Partition key path is **/tenantId**.
- Endpoint comes from trusted configuration.

### 17.2. Never Instantiate `CosmosClient` per HTTP Request

**newClient** only illustrates construction; invoke it once at startup as a DI bean and **close it on shutdown**. Creating a client per request causes connection churn, resource exhaustion, and latency spikes.

### 17.3. Request Charge Measures Operation RU Cost

`response.getRequestCharge()` reveals the real cost of a point read. Compare it against repository queries on the same data to evaluate access patterns. Avoid noisy `System.out.println` per request in production; emit sampled structured metrics/telemetry instead.

### 17.4. Ensure the Tenant Is Authorized

The `authorizedTenant` parameter must come from the authorization layer, never directly from an HTTP query parameter. Knowing a partition key never grants an end user permission.

## 18. Reactive Spring Data Cosmos Repository

If your app uses Reactor and Spring WebFlux, Spring Data Cosmos provides a reactive repository in supported releases:

~~~java
package example.orders.data;

import com.azure.spring.data.cosmos.repository.ReactiveCosmosRepository;
import reactor.core.publisher.Flux;

public interface ReactiveOrderRepository
        extends ReactiveCosmosRepository<OrderDocument, String> {

    Flux<OrderDocument> findByTenantId(String tenantId);

    Flux<OrderDocument> findByTenantIdAndStatus(
        String tenantId, String status);
}
~~~

### 18.1. `Mono` and `Flux`

- **`Mono<T>`**: 0 or 1 item, completing or erroring.
- **`Flux<T>`**: 0 to N items, completing or erroring.
- **Publishers** generally execute only upon subscription, per reactive driver semantics.

### 18.2. Do Not Enable Sync and Reactive Repositories Accidentally

This lesson presents two architectural options; **it does not ask you to run both repository interfaces on the same entity package simultaneously** in one app. If combining both, configure repository scanning, bean names, and dependency lifecycles carefully for your framework version.

### 18.3. Reactive Does Not Automatically Reduce RUs

A reactive query over the same data and indexes still consumes Cosmos DB RUs. Reactive changes how Java manages I/O and concurrency—it does not grant infinite database throughput.

### 18.4. Lazy Execution

In reactive pipelines, constructing a `Mono`/`Flux` without subscribing or returning the publisher to the framework means the operation never runs. Never call `subscribe()` and immediately return HTTP success, as errors may vanish silently.

## 19. WebFlux Controller: Returning `Flux` to the Framework

Assuming the app configures WebFlux, authz, and `ReactiveOrderRepository`:

~~~java
package example.orders.api;

import example.orders.data.OrderDocument;
import example.orders.data.ReactiveOrderRepository;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/api/reactive/orders")
public class ReactiveOrderController {
    private final ReactiveOrderRepository repository;
    private final TenantAuthorization tenantAuth;

    public ReactiveOrderController(
            ReactiveOrderRepository repository,
            TenantAuthorization tenantAuth) {
        this.repository = repository;
        this.tenantAuth = tenantAuth;
    }

    @GetMapping
    public Flux<OrderDocument> list() {
        String tenant = tenantAuth.requireAuthorizedTenant();
        return repository.findByTenantId(tenant)
            .take(100);
    }
}
~~~

`TenantAuthorization` remains an application service built with Spring Security. In reactive stacks, authentication context lives in the Reactor Context rather than a `ThreadLocal` across schedulers; production implementations must extract principals in a reactive-safe way.

### 19.1. Why Not Call `block()`?

WebFlux event-loop threads serve many concurrent requests. Calling `Mono.block()` or `Flux.blockLast()` on an event-loop thread stalls it on network I/O and causes starvation. Return the `Publisher` so the framework subscribes.

### 19.2. `take(100)` Is Not an Absolute SQL `LIMIT`

`take(100)` stops emitting items downstream after 100 elements; depending on driver paging, the backend may already have fetched larger pages. For heavy queries, use supported repository/query pagination limits and measure actual request charges.

### 19.3. Backpressure Is Not a Cosmos DB Rate Limiter

Reactor demand regulates downstream flow inside the pipeline, whereas query paging, retries, and request serialization depend on the driver. Enforce explicit concurrency/rate limits when database RU/s is the bottleneck.

### 19.4. Reactive Error Propagation

If a subscription hits `CosmosException` or `Spring DataAccessException`, the `Flux` terminates with an error signal. Map errors cleanly in controllers/services—never apply `onErrorResume` returning `Flux.empty()` and falsely report success during a database outage.

## 20. Spring MVC or Spring WebFlux?

| Aspect | MVC + `CosmosRepository` | WebFlux + `ReactiveCosmosRepository` |
|---|---|---|
| Style | Imperative, blocking | Reactive `Publisher` |
| Threads | Worker thread awaits call | Non-blocking pipeline when all dependencies are reactive |
| Multi-item queries | `List`/`Iterable`/`Page` per API | `Flux` |
| Debugging | Traditional stack traces | More complex reactive assembly/context |
| Backpressure | Executors, queues, rate limiters | Reactor operators + capacity controls |
| Concurrency | Bounded threads or virtual threads | Bounded reactive concurrency |
| Sync JDBC in same pipeline | Natural fit | Risks blocking the event loop if misused |
| RUs per request | Determined by Cosmos DB | Not automatically reduced by async |

### 20.1. When MVC Is Good Enough

Moderate request rates, a few DB operations per request, a team experienced in imperative Java, and latency meeting SLOs. Do not rewrite an entire app to reactive simply because the database is NoSQL.

### 20.2. When WebFlux Is Worth Considering

High I/O-bound concurrency, an already-reactive pipeline, streaming responses, or reducing platform threads. Requires discipline in debugging, cancellation, context propagation, and load testing.

### 20.3. Spring Boot and Java Virtual Threads

With Java 21 and supported runtimes, virtual threads let you keep blocking-style code while reducing I/O-wait overhead on certain workloads. Virtual threads **do not create extra RU/s** or eliminate hot-partition risks; benchmark before adopting.

## 21. Pagination: Never Return Every Document

For a tenant with 2 million orders, returning an unbounded `List<OrderDocument>` per request is dangerous:

- Massive RUs per query.
- Many pages and network round trips.
- Rising Java heap usage.
- Spiking p99 latency.
- HTTP responses exceeding client or proxy limits.
- Throttling triggering prolonged retries.

### 21.1. Pagination with Spring Data

Repositories can support `Pageable`, `Page`/`Slice`, or paging mechanisms depending on version and API; Cosmos DB exposes **continuation tokens** at the SDK layer. Pick the right API and verify how pages/tokens map in your Spring Data Cosmos version.

Do not assume SQL `OFFSET/LIMIT` performs like a relational database; for large datasets, favor **continuation tokens**, consistent ordering/indexing, and read consistency semantics.

### 21.2. Stable Limits and Matching Indexes

For an API returning the 20 newest orders, define the sort key/version, maximum page size, tenant partition, and indexing/composite indexes supporting that query.

### 21.3. Paging Risks While Data Mutates

Between two page fetches, items may be inserted, updated, or deleted. Define cursor/consistency expectations clearly and avoid treating multi-page reads as an immutable snapshot unless guaranteed by the service.

### 21.4. Sum RUs Across Every Page

A query spanning multiple pages incurs the sum of request charges across all actually fetched pages. Never measure only page 1 and conclude the query is cheap.

## 22. Indexing Policies and Query Performance

Cosmos DB for NoSQL indexing accelerates reads while adding write overhead.

### 22.1. Entity Mapping Does Not Tune Indexes Automatically

A Java field like `status` may be queried frequently, yet the container's indexing policy must match the access pattern. Tune included/excluded paths or add composite indexes for `ORDER BY` and multi-filter predicates.

### 22.2. Factors Affecting RU Cost

- Document size.
- Query predicates, projections, and aggregations.
- Cross-partition fan-out.
- Indexing policy and data distribution.
- Number of returned items.
- Write frequency and number of indexed fields.

### 22.3. Avoid Unnecessary `SELECT *`

If the UI only needs `orderId`, `status`, and `amount`, evaluate projections/DTOs instead of fetching entire documents with large fields. Verify projection behavior and DTO mapping with your library version.

### 22.4. Systematic Optimization

1. Measure baseline RUs/request and latency.
2. Group operations by endpoint and query pattern.
3. Review indexing policies and query shapes.
4. Test point reads or partition-scoped queries.
5. Verify correctness and data validation.
6. Re-benchmark p95/p99, RUs/operation, and successful throughput.

## 23. HTTP 429 Throttling and RU/s in Spring Boot

When a workload demands more RUs than available capacity in the relevant scope, Cosmos DB returns **HTTP 429 Too Many Requests**.

~~~mermaid
sequenceDiagram
    participant U as HTTP Client
    participant S as Spring Boot
    participant R as Spring Data Cosmos / SDK
    participant C as Cosmos DB
    U->>S: GET /api/orders
    S->>R: Repository query
    R->>C: Query request
    C-->>R: HTTP 429 + retry-after
    Note over R: SDK may retry within budget
    R->>C: Retry after delay
    C-->>R: Success + RU charge
    R-->>S: Data
    S-->>U: HTTP 200
~~~

### 23.1. 429s Can Be Retried Internally by the SDK

A repository call that eventually returns HTTP 200 may still have hit internal 429 retries inside the SDK, inflating latency. Watching only final API status 200 misses RU contention.

### 23.2. A 429 Does Not Always Mean Total RU/s Is Too Low

One tenant sending heavy traffic to a single partition key can create a **hot logical partition**; total container RU/s looks plentiful while that single physical partition hits its ceiling. Inspect normalized RU utilization and per-partition metrics where available.

### 23.3. Never Retry 400/401/403/404/409/412 as Throttling Errors

- **400:** invalid request/schema/query.
- **401/403:** authentication/authorization or policy denial.
- **404:** item/resource not found.
- **409:** conflict/duplicate.
- **412:** ETag/precondition mismatch.
- **429:** capacity/throttling.
- **503/timeout:** transient service/network failure depending on context.

Classify responses accurately before retrying or mapping HTTP errors.

## 24. Retry Policies: SDK, Spring, and API Gateway

Retries can stack across multiple layers:

~~~text
HTTP client retry
    x
Spring service retry
    x
Cosmos SDK retry
    x
Background job replay
    =
Far more attempts than intended
~~~

### 24.1. Respect `Retry-After`

Cosmos DB provides retry-delay hints, and the SDK already retries throttling errors. If adding an outer retry in Spring, ensure:

- Retries apply only to retryable errors with remaining time budget.
- Finite **max attempts**.
- **Total deadline** and jittered backoff.
- No unbounded queues or `Thread.sleep` blocking thousands of requests.
- Writes are idempotent.
- Metrics track retry attempts and final errors.

### 24.2. Do Not Blindly Enable `@Retryable`

Spring Retry/Resilience4j helps when tuned carefully, yet slapping a generic retry annotation onto repository calls multiplies with SDK retries. Configure policies per operation type and status code, never retrying conflicts or auth failures.

### 24.3. HTTP Responses to Callers

If capacity remains exhausted after the retry budget, return 429/503 per API contract with guidance to back off—never stall HTTP requests indefinitely. For background jobs, route to queues, dead-letter queues, or retryable states instead of dropping data.

### 24.4. Retry Duration Affects SLOs

An SDK call might succeed after several retries while blowing past the API's p99 SLO. Enforce end-to-end deadlines and monitor tail latency, not just success counts.

## 25. Concurrency Control and Backpressure

Suppose 20 AKS Pods each permit 50 concurrent repository operations:

\[
20 \times 50 = 1,000\text{ possible in-flight operations}
\]

If Cosmos DB RU capacity supports fewer than 1,000 concurrent operations, adding concurrency only drives more retries and higher latency without lifting throughput.

### 25.1. Three Distinct Mechanisms

| Mechanism | Protects |
|---|---|
| **Semaphore / max in-flight** | Threads, memory, connections |
| **Requests/RU rate limiter** | Cosmos DB capacity over time |
| **Bounded queue** | Prevents unbounded pending work and OOM |

### 25.2. Rate Limiting by RUs

If a write consumes ~8 RUs and an API-dedicated container has 1,600 RU/s, the ideal budget is roughly 200 writes/second before headroom and charge variance.

These numbers are illustrative only. When multiple workloads share a container, allocate explicit budgets so an import job cannot starve interactive APIs.

### 25.3. Reactor `flatMap` Concurrency

In reactive ingestion, pass bounded concurrency to `flatMap(fn, concurrency)` to avoid unbounded subscriptions. Keep in mind a per-Pod concurrency limit does not automatically cap cluster-wide concurrency.

### 25.4. Bulk Ingestion and Batch Jobs

When importing data, use SDK-supported bulk/batch features with pacing. Bulk execution does not automatically provide cross-item atomicity or exactly-once guarantees; track per-item outcomes and support idempotent replay.

## 26. ETags and Optimistic Concurrency

Two clients can read the same document and overwrite each other. **ETags** enable conditional updates: write only if the version originally read is still current.

~~~text
Client A reads ORD-1001, ETag = V1
Client B reads ORD-1001, ETag = V1
Client B writes update -> ETag V2
Client A writes with If-Match V1 -> HTTP 412
~~~

### 26.1. `@Version` in Spring Data Cosmos

Some Spring Data Cosmos versions support optimistic locking via ETag-backed version annotations/mappings. **Verify syntax and behavior in your exact version**, including field serialization and ETag mapping; never assume a generic annotation works without the proper mapping.

### 26.2. Explicit Control via Cosmos SDK

Example conditional replace using the SDK:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;

CosmosItemResponse<OrderDocument> current =
    container.readItem(
        "ORD-1001",
        new PartitionKey("shop-42"),
        OrderDocument.class);

OrderDocument order = current.getItem();
order.setStatus("PAID");

CosmosItemRequestOptions options =
    new CosmosItemRequestOptions();
options.setIfMatchETag(current.getETag());

container.replaceItem(
    order,
    order.getId(),
    new PartitionKey(order.getTenantId()),
    options);
~~~

In this fragment, `container` is an initialized `CosmosContainer`. When an ETag mismatches, re-read current state and re-evaluate business rules—never blindly retry replace.

### 26.3. 412 Differs from 429

**412 Precondition Failed** indicates a state conflict; raising RU/s will not fix it. **429** indicates capacity throttling; rate-limit and retry appropriately.

### 26.4. Business Idempotency Remains Necessary

ETags prevent lost updates, yet they do not prevent a workflow from issuing two refunds if each retry creates a fresh operation. Enforce `operationId` and state-transition rules.

## 27. Transactions in Cosmos DB and Spring's `@Transactional`

Cosmos DB supports transactions within specific boundaries, notably **transactional batches across items sharing one logical partition**.

**Never assume Spring's `@Transactional` turns multiple `repository.save()` calls across different partitions into an ACID Cosmos DB transaction.**

### 27.1. Why Does Sharing a Logical Partition Matter?

Items sharing a partition key value can participate in Cosmos DB's supported transactional mechanisms within service limits; items in different partitions do not automatically share a transaction.

### 27.2. Transactional Batch via SDK

When atomicity is needed between `Order` and `OutboxEvent`, design both documents with the same partition key and use `CosmosBatch`/`executeTransactionalBatch` in SDK v4. Verify API signatures, batch limits, and item size caps for your version.

### 27.3. When Service Bus Side Effects Exist

Writing to Cosmos DB and publishing to Service Bus are not automatically a single distributed transaction. Use an outbox/change-feed pattern or idempotent workflows to recover if the DB commits before the message sends.

### 27.4. Distributed Workflows Need Sagas / Compensation

Payments spanning Cosmos DB, Azure SQL, and external APIs generally require Sagas, retries/idempotency, and compensating actions rather than expecting one `@Transactional` to wrap the entire system.

## 28. Consistency Levels and Read-After-Write Behavior

Cosmos DB for NoSQL supports configurable consistency levels where available:

- Strong.
- Bounded Staleness.
- Session.
- Consistent Prefix.
- Eventual.

### 28.1. Session Consistency and Spring Boot

Session consistency fits many apps, yet multiple service instances or calls from different clients may not automatically share the same session token/context as expected. If business logic requires read-your-writes across instances, verify consistency semantics, token propagation, and SDK usage.

### 28.2. Consistency Shapes Business Behavior

If an order succeeds and the UI immediately reads from another region or connection, the business contract must specify when the updated state becomes visible. Never change consistency levels without testing workflow correctness.

### 28.3. Consistency vs. RUs and Latency

Consistency choices carry latency, availability, and cost trade-offs in certain setups. Benchmark production-like settings rather than extrapolating costs from a differently configured local or staging environment.

## 29. Schema Evolution, TTL, and Lifecycle

Having no rigid relational schema does not mean documents need no versioning.

### 29.1. Schema Version

Include `schemaVersion` in `OrderDocument`:

~~~json
{
  "id": "ORD-1001",
  "tenantId": "shop-42",
  "amountMinor": 125000,
  "schemaVersion": 2
}
~~~

When adding new fields, mappers and controllers must tolerate older documents missing those fields, upgrading via migrations or lazy evolution per contract.

### 29.2. TTL

Cosmos DB supports Time-to-Live at container or item scope per configuration. TTL suits sessions, caches, or temporary jobs, yet **it is not a backup**. Never apply TTL to orders or financial records without a retention policy.

### 29.3. Changing the Partition Key Path Is Not Trivial

If a container was created with **/tenantId**, switching to `/customerId` normally requires creating a target container, copying data, syncing changes, cutting over, and validating. Updating `@PartitionKey` in Java code does not alter an existing container's partition key path.

### 29.4. Container Migrations Differ from Java Deployments

Editing entity annotations does not safely migrate database containers, indexes, or throughput. Maintain dedicated IaC and migration runbooks.

## 30. Detecting and Handling Hot Partitions

Suppose a container holds tenants:

~~~text
shop-big   -> 75% write requests
shop-small -> 15% write requests
others     -> 10% write requests
~~~

With **/tenantId**, `shop-big` can create a hot logical partition even if total provisioned RU/s is large.

### 30.1. Warning Signs

- 429 errors concentrated on a single tenant or key.
- Elevated p99 latency for the largest tenant compared to others.
- Skewed normalized RU utilization across physical partitions where metrics exist.
- Raising total throughput yields less improvement than expected.
- Dense read/write bursts targeting one tenant.

### 30.2. Prioritized Remediation

1. Measure request charges, key distribution, and latency.
2. Optimize point reads, queries, indexing, and document sizes.
3. Enforce per-tenant rate limits.
4. Separate background jobs or isolate heavy tenants into dedicated containers if justified.
5. Evaluate synthetic or hierarchical partition keys where supported by the model and service.
6. Plan a container migration if the partition key truly must change.

### 30.3. Trade-Offs of Synthetic Keys

Splitting one tenant across buckets reduces hotspots, yet whole-tenant queries can become fan-out queries and same-partition transactions get harder. Never redesign a partition key solely to flatten charts while breaking business access patterns.
## 31. Microsoft Entra Data-Plane RBAC and Managed Identity

In production, **managed identity** lets the app authenticate to Cosmos DB without storing long-lived account keys when supported by the API, SDK, and resource settings.

### 31.1. Distinguish Three Permission Layers

| Layer | Scope | Interchangeable? |
|---|---|---|
| **Azure management RBAC** | Administering Cosmos account/resources | Does not automatically permit querying items |
| **Cosmos DB for NoSQL data-plane RBAC** | Query/read/write items within granted scope | Does not govern specific HTTP end users |
| **Spring Security / business authorization** | Which user/tenant/document is permitted | Does not replace the workload's data-plane role |

Two common built-in data roles are **Cosmos DB Built-in Data Reader** and **Cosmos DB Built-in Data Contributor**. Verify exact role scopes/actions on the target resource; never grant account Owner just to fix a 403.

### 31.2. Service Managed Identity Is Not End-User Authorization

If the Java app identity can read the container, Cosmos DB authenticates the app's service principal. Spring Security must still verify the HTTP user is authorized for `shop-42` before querying `shop-42` orders.

### 31.3. Runtime Environments

- **App Service:** system-assigned or user-assigned managed identity, plus VNet integration when required.
- **AKS:** Microsoft Entra Workload ID or approved identity mechanism.
- **Azure Functions:** managed identity with appropriate hosting plan and network settings.
- **Local:** Azure CLI/IDE developer identity against a separate test account and scoped role.

### 31.4. Debugging HTTP 403

Inspect principal ID, tenant, token audience, Cosmos data role, scope, role-assignment propagation delay, and firewall/network policies. Resolving the endpoint does not mean data-plane permissions exist.

## 32. Key Vault, Configuration, and Secrets Management

Because Cosmos DB supports identity-based data access, **direct managed identity** eliminates most needs to store account keys. If an environment constraint still requires a key, protect it with Key Vault/secret management and rotation.

### 32.1. Mandatory Practices

- Never commit `spring.cloud.azure.cosmos.key` or connection strings with keys.
- Never print keys in application logs, exceptions, actuator `env`, or metric tags.
- Separate credentials and Cosmos resources across dev, test, and prod.
- Allow only required identities to read secrets.
- Maintain secret rotation/revocation policies and post-rotation tests.

### 32.2. Spring Boot Configuration

Use approved environment injection, App Configuration, or Key Vault integrations for your version. Verify actual property binding and which identity the starter uses; never mix legacy properties when troubleshooting 401/403 errors.

### 32.3. Spring Actuator Can Expose Configuration

Restrict endpoints like `env`, `configprops`, `beans`, `heapdump`, and `mappings` via authorization and network policies. Even when values are masked, operational metadata needs protection.

### 32.4. Never Log Full Cosmos Error Bodies

Error bodies may contain endpoints or query metadata; log sanitized error codes, statuses, activity IDs, and correlation IDs instead of dumping raw exceptions to broad logs.

## 33. Private Endpoints, VNet, and Connectivity

~~~mermaid
flowchart LR
    APP[Spring Boot on AKS / App Service] --> VNET[Azure VNet]
    VNET --> DNS[Private DNS]
    DNS --> PE[Private Endpoint]
    PE --> DB[(Cosmos DB Account)]
    ID[Managed Identity] --> APP
    APP --> MON[Application Insights]
~~~

### 33.1. Ordered Verification

1. Does the endpoint/FQDN match the right Cosmos DB for NoSQL account?
2. Are the Private DNS zone, VNet links, and DNS resolution working?
3. Do firewalls/routes allow egress from the Pod or App Service?
4. Are TLS certificate chains and truststores valid?
5. Do SDK connection mode and ports match the network topology?
6. Is the managed identity's data-plane role valid?

### 33.2. Direct vs. Gateway Mode

The Azure Cosmos DB Java SDK supports Direct and Gateway connection modes per configuration. Networking, ports, proxies, and private connectivity requirements differ; pick based on benchmarks and security requirements rather than assuming one mode fits everywhere.

### 33.3. Never Disable TLS to Work Around DNS

Never enable trust-all SSL or open public Internet access to dodge 403s or timeouts. Fix the actual DNS, routing, TLS, or permission error.

### 33.4. Scaling Pods Increases Connection Pressure

If each Pod instantiates an SDK client, total open connections, memory, and SNAT port usage scale with Pod count. Monitor pools, GC, and networking, and reuse clients across the app lifecycle.

## 34. Azure Monitor and Application Insights

The system needs metrics across **Spring Boot**, the **Cosmos SDK**, and the **Cosmos DB service**.

| Scope | Metrics | Question answered |
|---|---|---|
| HTTP API | p50/p95/p99 latency | Are users experiencing slowness? |
| Business service | Query duration, result counts | Which endpoints are expensive? |
| SDK | Retry count, dependency latency, error/status | Is there a retry storm? |
| Cosmos DB | Consumed RU/s, 429 counts | Are we hitting capacity limits? |
| Partitions | Normalized RU utilization (if available) | Which tenant/partition is hot? |
| Data | RUs/query page, storage growth | Are queries and indexes efficient? |
| JVM | Heap, GC, CPU, threads | Is the app bottlenecked? |
| Networking | DNS/TLS failures, connections | Are there connectivity issues? |
| Cost | Provisioned/consumed RUs, storage, logs | Are we within budget? |

### 34.1. Internal 429s May Not Surface in Final API Errors

When the SDK retries a 429 and succeeds, the controller still returns HTTP 200 while p99 latency climbs. Inspect Cosmos service-side metrics and SDK diagnostics, not just final HTTP status codes.

### 34.2. Measure Request Charges with the SDK When Needed

`CosmosItemResponse.getRequestCharge()` reports RUs for specific point reads and writes. If Spring Data Repository abstractions do not expose charges directly, use SDK/transport instrumentation or an SDK adapter for operations needing precise measurement.

### 34.3. Multi-Page Queries Must Sum All Pages

Total query RU cost equals the sum of RUs across all actually read pages. Never judge total cost by page 1 alone.

### 34.4. Metric Instrumentation Varies by Version

Do not assume metric or log table names stay identical across Azure Monitor, OpenTelemetry, and Application Insights. Verify the active exporter and instrumentation on your runtime.

### 34.5. Never Put PII in Metric Dimensions

Use operation type, status, deployment/environment, and grouped/hashed tenant labels where needed. Avoid raw user IDs, full blob paths, or customer data in metric tags.

## 35. Spring Boot Actuator and Health Checks

Spring Boot Actuator can expose health and metrics endpoints for liveness and readiness depending on configuration.

### 35.1. Liveness Must Not Depend on Expensive Cosmos Queries

If the database slows briefly, a liveness probe querying remote dependencies can cause AKS to restart healthy Pods en masse, triggering a retry storm.

### 35.2. Distinguish Three Levels

- **Liveness:** is the process still functioning properly?
- **Readiness:** is the instance ready to receive traffic?
- **Business dependency health:** is Cosmos DB serving workflows cleanly? Monitor separately against SLOs.

### 35.3. Never Call `findAll` in a Health Probe

A health check scanning a large container burns RUs and can trigger 429s itself. If a dependency probe is required, keep it lightweight with strict intervals/timeouts and monitor its impact.

### 35.4. Protect Actuator

Never expose `env`, `configprops`, `heapdump`, or `mappings` publicly; enforce authentication, private networking, and access logging per policy.
## 36. Unit Testing Services and Tenant Boundaries

Because `OrderRepository` is an interface, you can mock it to test `OrderService` logic without an Azure account.

JUnit 5 and Mockito example:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.*;

import example.orders.api.CreateOrderRequest;
import example.orders.data.OrderDocument;
import example.orders.data.OrderRepository;
import example.orders.service.OrderService;
import org.junit.jupiter.api.Test;

class OrderServiceTest {
    @Test
    void createUsesTrustedTenant() {
        OrderRepository repo = mock(OrderRepository.class);
        when(repo.save(any(OrderDocument.class)))
            .thenAnswer(call -> call.getArgument(0));

        OrderService service = new OrderService(repo);
        OrderDocument item = service.create(
            "shop-42", new CreateOrderRequest("C-20", 125000L));

        assertEquals("shop-42", item.getTenantId());
        assertEquals("CREATED", item.getStatus());
        verify(repo).save(any(OrderDocument.class));
    }

    @Test
    void invalidAmountDoesNotSave() {
        OrderRepository repo = mock(OrderRepository.class);
        OrderService service = new OrderService(repo);

        assertThrows(IllegalArgumentException.class,
            () -> service.create(
                "shop-42", new CreateOrderRequest("C-20", 0L)));

        verifyNoInteractions(repo);
    }
}
~~~

### 36.1. Mocks Do Not Verify Cosmos Mappings

Unit tests do not exercise `@Container`/`@PartitionKey`, SDK serialization, RBAC, networking, throughput, or query translation; integration tests are required.

### 36.2. Testing Tenant Authorization

Use a Spring Security test principal for `shop-A` attempting to read `shop-B` data. Authorization must be enforced inside `TenantAuthorization`/services rather than trusting a user-supplied `tenantId`.

### 36.3. Testing Idempotency

Simulate a committed write whose response is lost, followed by a retry carrying the same `operationId`. Confirm no duplicate business orders are created when business rules demand a single outcome.

## 37. Integration Testing Against a Lab Cosmos DB

Use only isolated test resources and synthetic datasets—never write real data.

### 37.1. Setup

1. Test Cosmos DB for NoSQL account.
2. Database `shopdb` and container `orders` with `/tenantId`.
3. Managed identity with data-plane role or test secret in a secret store.
4. Network/DNS reachability from runner or IDE to the endpoint.
5. Test RU budget and cleanup policy.
6. Synthetic test entities/tenants containing zero PII.

### 37.2. Test Cases

- `repository.save` writes valid JSON.
- `findByTenantId` and `@Query` return only the target tenant.
- Point read with matching `id` + partition key succeeds.
- Wrong partition key with valid `id` returns Not Found.
- Concurrent writes trigger ETag/412 when using conditional replace.
- Field serialization and `schemaVersion` backward compatibility.
- Multi-page queries, paging boundaries, and data consistency.
- Unauthorized identity cannot read or write.
- Throttling/timeout policies classify errors properly.

### 37.3. Isolate Test Data

Each test run uses a distinct `tenantId`/`runId` and cleans up only items it created. Never call `deleteAll` on a shared container.

### 37.4. Emulators Do Not Replicate Everything

If using the Cosmos DB emulator, verify supported versions, platforms, and features. Never assume the emulator mirrors Entra RBAC, private endpoints, multi-region latency, RU/429s, or every production API.
## 38. Failure Tests: Do Not Harm Live Accounts with Load

To test resilience, prefer fake adapters or HTTP stubs over trying to force 429s on a shared or production Cosmos DB.

| Failure case | Expected outcome |
|---|---|
| 400 invalid schema/query | Do not retry blindly |
| 401 expired/invalid token | Authentication failure |
| 403 missing role | Inspect data-plane permissions/networking |
| 404 item not found | Domain Not Found |
| 409 duplicate | Idempotency/business conflict |
| 412 stale ETag | Re-read state and resolve conflict |
| 429 with `retry-after` | Bounded retry and load shedding |
| 503/network timeout | Bounded retry, then clear failure |
| Response with older schema | Mapping or migration policy |

### 38.1. Testing Replay After Write Timeout

A write may commit before the client drops the response. Test that retrying with the same `operationId` never creates two business orders.

### 38.2. End-to-End Budget Testing

Bound total elapsed time from the HTTP caller through service and SDK retries. Never leave an API with a 3-second timeout while the SDK retries in the background for minutes.

### 38.3. Lab Load Testing

Define clear stop thresholds, quotas, and budgets; measure successful throughput, p95/p99, RUs/request, hot partitions, and final error rates. Never load test with real production data.

## 39. Deploying Spring Boot on App Service, AKS, or Functions

| Host | Best fit | Notes |
|---|---|---|
| **Azure App Service** | PaaS Java REST APIs | Managed identity, VNet, scaling |
| **AKS** | Kubernetes/microservices | Workload Identity, HPA, Pod limits, DNS |
| **Azure Container Apps** | Containerized APIs and background jobs | Identity, ingress, scale rules |
| **Azure Functions** | Event-driven or scheduled jobs | Hosting plan, timeouts, cold start |
| **Azure VM** | Specialized host configuration needs | OS security, maintenance |

### 39.1. IaC Manages Database Resources

Provision accounts, containers, indexing, throughput, and RBAC through approved governance tooling. Never let Pod startup mutate schemas, indexes, or throughput.

### 39.2. Managed Identity Must Match the Intended Principal

App Service uses system-assigned or user-assigned identities; AKS Workload Identity relies on service accounts and federation. Verify the exact principal used by the Java SDK and its assigned roles.

### 39.3. Scaling Java Does Not Scale Cosmos RU/s

Adding Pods increases concurrent repository calls. If RU/s or a hot partition is the bottleneck, 429s will rise. Throttle load and size database capacity properly.

### 39.4. Secrets and Private Networking

Never bake Cosmos account keys into Dockerfiles or application artifacts. Configure networking, Key Vault, and identities per policy—never open public access casually to bypass connectivity errors.

## 40. CI/CD, IaC, and Document Schema Migration

A single release can change multiple layers at once:

- Java/Spring Boot/Spring Cloud Azure dependencies.
- Entity annotations, DTOs, and API fields.
- Container indexing, TTL, and throughput.
- Partition key strategies and query patterns.
- Managed identity and data-plane RBAC.
- Document `schemaVersion`.
- Alert thresholds and dashboards.

### 40.1. Recommended Deployment Order

1. Review code and data migrations.
2. Provision/update Cosmos resources via controlled IaC.
3. Verify networking, identity, and data RBAC in staging.
4. Run backfills/migrations if required.
5. Deploy Spring Boot to staging.
6. Run integration and failure tests.
7. Canary/roll out to production.
8. Monitor 429s, RU cost, p99, and correctness.
9. Roll back or forward-fix per compatibility plan.

### 40.2. `git revert` Does Not Roll Back Data

If the new app writes `schemaVersion=2`, the older app version may fail to parse it. Design backward/forward compatibility and data migration procedures.

### 40.3. Never Run Migrations Concurrently Across Every Pod

When 20 Pods boot simultaneously, avoid having each Pod execute destructive migrations. Run a dedicated job with clear ownership, locking/approvals, and auditing.

### 40.4. Protect CI/CD Logs

Never print account keys, tokens, connection strings, or document PII in build logs, pipeline outputs, or error traces.
## 41. Change Feed and Asynchronous Processing

Spring Data Cosmos fits CRUD and queries well. For continuous processing of data changes, pair the **Cosmos DB Change Feed** with Azure Functions or a Java worker.

~~~mermaid
flowchart LR
    APP[Spring Boot Orders API] --> COSMOS[(Cosmos DB)]
    COSMOS --> FEED[Change Feed]
    FEED --> WORKER[Azure Function / Java worker]
    WORKER --> BUS[Service Bus / Analytics]
~~~

### 41.1. Change Feed Is Not `repository.findAll`

`repository.findAll` reads current items. Change Feed tracks changes per supported semantics, avoiding full-container scans every minute to find new records.

### 41.2. Checkpoints and Leases

Processors must coordinate workers and track progress (leases/checkpoints) via SDK/runtime support. Never use a Pod-local static variable as the system-wide checkpoint.

### 41.3. Downstream Idempotency

A worker can send a message and crash before checkpointing. On replay, the event gets processed again; consumers need idempotency keys, deduplication, and dead-letter policies.

### 41.4. No Automatic Cross-Service Exactly-Once

Writing to Cosmos and publishing to Service Bus touch separate resources. Use outbox/change-feed or Saga patterns per business contract—never treat the two steps as one distributed transaction.

## 42. Cosmos DB and Spring Boot Costs

| Cost driver | Factors |
|---|---|
| Cosmos throughput | Manual RU/s, autoscale, or serverless per capacity mode |
| Storage/indexes | Data size, index size, retention |
| Multi-region | Replication and read/write topology |
| Java compute | App Service/AKS/Functions |
| Networking | Private Link, NAT, egress where applicable |
| Monitoring | Application Insights/Log Analytics ingestion |
| Backup/DR | Backup settings and restore mechanisms |
| Background workloads | Imports, change feed, migrations, replays |
| Retries | Extra requests and latency overhead |

### 42.1. Reduce RUs per Operation

Prefer point reads by `id` + partition key, partition-scoped queries, projections, tuned indexing, smaller documents, and avoiding duplicate writes. Measure actual request charges before resizing capacity.

### 42.2. Optimize for Successful Throughput and SLOs

Throttling requests solely to eliminate 429s can leave backlogs unprocessed. Measure cost per successful operation, p95/p99 latency, freshness, and data correctness.

### 42.3. When to Increase RU/s

Increase manual/autoscale capacity after measuring workloads and optimizing queries/partitioning when more throughput is still genuinely needed. Hot partitions may not resolve simply by raising total RUs.

### 42.4. Pricing Varies by Region and Mode

Never hardcode unit prices in design docs; compute estimates with the Azure Pricing Calculator and Cost Management at planning time.

## 43. Runbook: Spiking 429s and p99 Latency

Example timeline:

~~~text
10:00  API p95 = 150 ms
10:05  Batch import starts
10:07  Cosmos 429s rise
10:08  SDK retries rise
10:10  API p99 breaches SLO; some requests time out
~~~

### Step 1 — Isolate Scope

One tenant, endpoint, container, or the whole system? Did a deployment or batch job just start?

### Step 2 — Assess Impact

Measure p95/p99, final error rates, request charges, queues/backlogs, SDK retry attempts, and JVM memory.

### Step 3 — Inspect RUs

Manual, autoscale, or serverless? Did consumption hit the configured ceiling, or do multiple containers share a database RU budget?

### Step 4 — Check for Hot Partitions

Which tenant drives the most writes? Is normalized RU utilization skewed across physical partitions? Does raising total throughput help?

### Step 5 — Audit Queries

Did new code introduce `findAll`, filters missing partition keys, deep multi-page scans, or oversized documents?

### Step 6 — Protect the Application

Throttle background concurrency, enforce admission control, rate-limit callers, and bound retries. Never hold thousands of HTTP requests open indefinitely.

### Step 7 — Fix and Verify

Optimize queries, indexing, or key distribution, or raise capacity cleanly; re-measure successful operations/s, p99, RUs/operation, 429s, and cost.

### Step 8 — Post-Incident Review

Save correlation/activity IDs, timeline, root cause, and rollback procedures. Never copy raw customer data or keys into incident reports.
## 44. Lab 1: Connecting Spring Boot to Cosmos DB for NoSQL

Run strictly on isolated lab resources with zero production data.
### Part A — Azure Resources

1. Create a dedicated lab resource group and Cosmos DB **for NoSQL** account.
2. Create database **shopdb** and container **orders** with partition key **/tenantId**.
3. Pick a capacity mode and RU allocation within your lab budget.
4. Grant a test identity the proper data-plane role or store a lab key in a secret store.
5. Verify endpoint, DNS/TLS, firewall/private networking, and Azure Monitor.
6. Record resource names for post-lab cleanup.

### Part B — Spring Boot

1. Pick compatible Spring Boot and Spring Cloud Azure BOM versions.
2. Add `spring-cloud-azure-starter-data-cosmos`, Spring Web, and Validation.
3. Configure `spring.cloud.azure.cosmos.endpoint` and `database` via environment.
4. Enable managed identity/Entra auth where supported, or inject the lab key safely.
5. Create `OrderDocument`, `OrderRepository`, and `OrderService`.
6. Create a controller using DTOs and `TenantAuthorization`/Spring Security.
7. Run the app, then save and query synthetic tenant documents.

### Part C — Troubleshooting

| Symptom | Check |
|---|---|
| Bean creation failed | BOM, Boot compatibility, auto-configuration |
| DNS/TLS failure | Endpoint, private DNS, VNet, truststore |
| 401/403 | Credentials, data-plane role, network policies |
| 404 resource | Database/container names and existence |
| 400 partition mismatch | Entity mapping and `/tenantId` |
| 429 | RU/s capacity, throttling metrics, retries |

**Never raise RU/s to fix DNS errors, bean creation failures, or missing RBAC.**

### Part D — Verification and Cleanup

Confirm the app creates repository beans, writes/reads `shop-42` documents cleanly, logs zero keys, and reports metrics. Stop the app/test jobs, delete **only authorized lab data/resources**, and check billing.
## 45. Lab 2: CRUD, Partition Keys, and Optimistic Concurrency
### A. Seed Documents

1. Create three synthetic orders for **shop-42** and two for **shop-17**.
2. Record `id`, `tenantId`, `status`, and `amountMinor`.
3. Verify entity mapping in Cosmos DB Data Explorer/SDK.

### B. Repository Queries

1. Call `findByTenantId("shop-42")`.
2. Call `findByTenantIdAndStatus("shop-42", "CREATED")`.
3. Confirm no `shop-17` items appear in results.
4. Record request charges and latency from telemetry.

### C. Point Read via SDK

1. Pick `ORD-1001` in `shop-42`.
2. Read using `CosmosContainer.readItem(id, new PartitionKey("shop-42"), OrderDocument.class)`.
3. Record RU charge and latency.
4. Read the same `id` with partition key `shop-17` and confirm Not Found.
5. Compare against a repository query for the same item.

### D. Tenant Authorization

1. `shop-42` user accesses `shop-42` documents.
2. `shop-17` user requests a `shop-42` order.
3. Spring Security/`TenantAuthorization` blocks access.
4. HTTP errors/logs disclose zero contents from the other tenant.

### E. ETag Conflict

1. Two clients both read ETag V1.
2. Client B updates to V2.
3. Client A replaces with `If-Match V1`.
4. Confirm HTTP 412 without overwriting newer state.
5. Read current state and handle the business conflict.

### F. Idempotency

1. Submit create with a stable `operationId`.
2. Simulate DB commit with lost response via a fake adapter.
3. Retry with the same `operationId`.
4. Confirm no duplicate business orders exist.

| Test | Expected result |
|---|---|
| Query `shop-42` | Only `shop-42` items |
| Point read right PK | Item returned + RU charge |
| Point read wrong PK | Not Found |
| Unauthorized tenant | Blocked |
| Stale ETag replace | HTTP 412 |
| Replayed `operationId` | No duplicate |

**Criteria:** tenant isolation, point reads, concurrency, and idempotency are all verified.
## 46. Lab 3: Reactive, Throttling, and Monitoring

### A. Compare Spring MVC vs. WebFlux

1. Use `CosmosRepository` in a small sync API.
2. Use `ReactiveCosmosRepository` in a separate lab WebFlux API.
3. Over identical datasets and logic, measure p95/p99, JVM threads, CPU, and success rate.
4. Never call `Mono.block()` inside the WebFlux event loop.
5. Bound concurrent operations in both variants.

### B. Mock Failures

Build a fake gateway/stub to simulate:

- 400 invalid payload/query.
- 401/403 wrong identity or role.
- 404 item not found.
- 409 business duplicate.
- 412 stale ETag.
- 429 with `retry-after`.
- 503/timeout exhausting the retry budget.

Never intentionally flood a shared or production Cosmos account to induce 429s.

### C. Measure Results

| Metric | Sync | Reactive |
|---|---|---|
| Successful operations/s | Measure | Measure |
| p95/p99 latency | Measure | Measure |
| Total Cosmos RUs consumed | Measure | Measure |
| Final 429/5xx | Measure | Measure |
| Retry count | Measure | Measure |
| JVM heap/threads | Measure | Measure |
| Per-item correctness | Verify | Verify |

### D. Simulated Hot Partition

1. Generate light load spread across multiple `tenantId` values.
2. Compare against the same request count focused on one tenant in the lab.
3. Observe RU usage, latency, and 429s if triggered.
4. Repeat at lower concurrency under similar conditions.
5. Analyze why adding Java threads or Pods does not generate more RU/s.

### E. Completion Criteria

Recommend sync vs. reactive for the measured workload, verify bounded retries/authorization/idempotency, and prove zero data-correctness regressions while tuning performance.
## 47. Production Checklist

- [ ] Use Azure Cosmos DB **for NoSQL**; never mix MongoDB APIs.
- [ ] Spring Boot, Spring Cloud Azure, and Cosmos SDK versions are compatible.
- [ ] Dependency BOM and vulnerability scans verified.
- [ ] Container created with exact name and partition key path **/tenantId**.
- [ ] Partition key chosen around query patterns and load distribution.
- [ ] Hot partitions, tenant skew, and peak workloads evaluated.
- [ ] Data contract, `schemaVersion`, and migration strategy defined.
- [ ] Entity `@Id` and `@PartitionKey` match JSON layout.
- [ ] Containers and throughput are never created/altered on Pod startup.
- [ ] Managed identity/Entra credentials used wherever supported.
- [ ] Cosmos data-plane RBAC scoped to least privilege.
- [ ] Spring Security enforces user/tenant/document authorization.
- [ ] No plaintext account keys in Git, images, or logs.
- [ ] Networking, private endpoints, DNS, and TLS tested from real runtime.
- [ ] Cosmos clients, credentials, and HTTP transports reused via DI/lifecycle.
- [ ] `findAll()` never called on production endpoints.
- [ ] Tenant-scoped queries, pagination, and result limits enforced.
- [ ] Point reads (`id` + partition key) used where appropriate.
- [ ] RUs per request/query and total RUs across multi-page queries measured.
- [ ] Indexing policies match reads/writes without wasteful scans.
- [ ] Optimistic concurrency/ETags or version checks enforced where needed.
- [ ] Create/update APIs enforce idempotency keys.
- [ ] `@Transactional` never assumed atomic across partitions.
- [ ] Retry budgets, `Retry-After`, deadlines, and status classifiers configured.
- [ ] 400/403/409/412 never retried like 429s.
- [ ] Concurrency/rate limits, bounded queues, and backpressure configured.
- [ ] Background jobs cannot exhaust RU budgets of interactive APIs.
- [ ] Manual, autoscale, or serverless chosen based on measurements.
- [ ] 429s, RUs, p95/p99, retries, and request failures monitored.
- [ ] Partition-level metrics and tenant isolation monitoring active.
- [ ] Logs and metrics contain zero raw PII or secrets.
- [ ] Liveness/readiness probes designed safely.
- [ ] Unit tests, integration tests, and fake failure tests complete.
- [ ] Load tests run against production-like data distributions.
- [ ] CI/CD covers staging, IaC, schema migrations, and rollbacks.
- [ ] Backup/restore/DR policies aligned with requirements.
- [ ] Cost budgets/alerts set for compute, RUs, storage, and logs.
- [ ] Runbooks ready for 401/403/404/412/429/503/timeouts.
- [ ] Cleanup process defined for test resources and temporary roles.
## 48. Self-Check Questions
1. Which Cosmos DB API is Spring Data Cosmos built for?
2. How do a Cosmos account, database, and container differ?
3. How does partition key path `/tenantId` differ from value `shop-42`?
4. Why are `id` + partition key essential for point reads?
5. What does `CosmosRepository` do for you, and what does it not do?
6. Is a derived query always a point read?
7. Why can `findAll()` burn RUs and memory?
8. When should you use Cosmos SDK v4 directly?
9. What do `@Container`, `@Id`, and `@PartitionKey` do?
10. What happens if `@PartitionKey` mismatches the container path?
11. Why choose a BOM compatible with your Spring Boot version?
12. What extra risks does key auth carry compared to Entra/managed identity?
13. Does Azure ARM Contributor automatically grant permission to read items?
14. Why is Spring Security still necessary even when the app identity can read the container?
15. Why never accept `tenantId` from the request body as access proof?
16. How does `ReactiveCosmosRepository` differ from `CosmosRepository`?
17. Do `Mono`/`Flux` automatically reduce RUs per request?
18. Why must you never call `block` on a WebFlux event-loop thread?
19. What problems do pagination and continuation tokens prevent?
20. Why are queries lacking a partition key usually more expensive?
21. Which factors determine Cosmos DB RUs per request?
22. What does HTTP 429 indicate?
23. Why can autoscale still return 429s?
24. How does a hot logical partition differ from insufficient total RU/s?
25. What problem can arise when combining SDK retries with Spring outer retries?
26. Which risks do `Retry-After` and deadlines reduce?
27. How do ETags prevent lost updates?
28. Why must 412 not be retried like 429?
29. Is `@Transactional` atomic across Cosmos partitions by default?
30. Why do writing to Cosmos and sending to Service Bus require idempotency/outbox?
31. What role does `schemaVersion` play during migrations?
32. Why does editing `@PartitionKey` not alter an existing container's partition key path?
33. Why should a liveness probe never call `findAll`?
34. Which metrics should be measured to compare sync vs. reactive?
35. Can HTTP 200 mask internal SDK 429 retries?
36. How does data-plane RBAC differ from Spring tenant authorization?
37. What data must be excluded from logs and metrics?
38. When Change Feed events replay, what must consumers handle?
39. What cost drivers exist beyond RU/s?
40. When production hits 429s, what are the first steps in the runbook?
## 49. Summary

**Integrating Cosmos DB with Spring Data** lets Spring Boot apps use entities, repositories, derived queries, and dependency injection to work with **Azure Cosmos DB for NoSQL**. Annotations and interfaces like **@Container, @Id, @PartitionKey, and `CosmosRepository`** keep code concise, yet they never replace designing partition keys, indexing, authorization, and RU/s.

For multi-tenant data, derive **tenantId** from verified authorization, minimize cross-partition queries, use **point reads with `id` + partition key** for efficiency, and implement pagination/continuation tokens. Pay close attention to **ETags, idempotency, and transaction boundaries**, because `repository.save` or `@Transactional` cannot make multi-service workflows atomic on their own.

In production, prefer **managed identity + Cosmos data-plane RBAC**, private networking, secrets governance, bounded retries, and backpressure. Monitor **HTTP 429s, request charges, normalized RU utilization, p95/p99 latency, successful throughput, and cost** across both Cosmos DB and Spring Boot. Choose between **`CosmosRepository` and `ReactiveCosmosRepository`** based on your execution model and benchmarks—never assuming async is automatically better.

A complete deployment connects Spring Boot with **Microsoft Entra ID, App Service/AKS/Functions, Azure networking, Application Insights, CI/CD, and Cost Management** to ensure data correctness, application security, testability, recoverability, and predictable cost.
