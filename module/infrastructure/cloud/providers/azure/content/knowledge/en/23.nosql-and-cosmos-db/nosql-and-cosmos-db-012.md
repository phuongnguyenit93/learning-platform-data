# Cosmos DB Java SDK and Throttling Handling

## 1. When a NoSQL Database Is Fast but the Application Still Receives 429 Errors

A Java e-commerce application stores shopping carts, orders, and operation history in **Azure Cosmos DB**. On a normal day, the APIs respond quickly. When a promotional campaign starts, write volume spikes, many requests slow down, and the logs show **HTTP 429 Too Many Requests**.

The natural reaction is to scale up the number of Pods or create more Java threads. However, if the data in Cosmos DB is constrained by **Request Units per second (RU/s)**, increasing concurrent requests can cause even more throttling, longer wait times, and higher retry overhead without a corresponding increase in successful operations.

This lesson explains how to use the **Azure Cosmos DB Java SDK v4 for Azure Cosmos DB for NoSQL**, handle responses, read diagnostics, manage retries, and optimize throughput. It is part of the **NoSQL Data with Cosmos DB** chapter in the Microsoft Azure exploration module, tied to resource groups, Microsoft Entra ID, App Service/AKS/Functions, networking, security, monitoring, and cost control.

**Distinguish these three points immediately:**

- **429** usually indicates that a request was rate-limited because there were not enough available RU/s within a time window at the relevant scope.
- **SDK retry** can wait for the duration requested by the broker and resend the request. It helps the application survive brief throttling bursts, but it does not increase RU/s capacity.
- **Root-cause fixes** may involve query optimization, partition key design, reducing request charge, throttling concurrency, or appropriately increasing throughput—not necessarily adding more Java workers.

## 2. Learning Objectives

After completing this lesson, you will be able to:

1. Explain the database, container, item, id, and logical partition model in Cosmos DB for NoSQL.
2. Understand RUs, RU/s, request charge, and provisioned, autoscale, and serverless throughput.
3. Choose a partition key that serves queries and distributes load effectively.
4. Create a CosmosClient/CosmosAsyncClient using Java SDK v4 with secure credentials.
5. Perform create, read, upsert, replace, delete, and query operations with the correct partition key.
6. Read status codes, request charge, activity IDs, and Cosmos diagnostics.
7. Explain HTTP 429, retry-after, and automatic SDK retries.
8. Design bounded retries, jitter, deadlines, idempotency, and backpressure.
9. Tune sync/async concurrency, pagination, and bulk workloads.
10. Distinguish a hot logical partition from container-wide throughput exhaustion.
11. Monitor throttled requests, RU consumption, latency, and failures with Azure Monitor.
12. Build load tests, incident runbooks, and appropriate cost plans.

## 3. Scope: Cosmos DB for NoSQL, Not Every Cosmos DB API

Azure Cosmos DB provides different API models, including **Azure Cosmos DB for NoSQL**. This lesson focuses on the Java SDK package **com.azure.cosmos**, which supports the API for NoSQL.

| Concept | Role |
|---|---|
| **Cosmos account** | Azure resource that manages endpoints, regions, authentication, and service settings |
| **Database** | Logical grouping of containers |
| **Container** | Unit that stores items and configures partition key, indexing, TTL, and throughput at the appropriate scope |
| **Item** | JSON document with an id property and business fields |
| **Logical partition** | Items that share the same partition key value |
| **Physical partition** | Infrastructure unit responsible for storing and serving a portion of data and throughput |
| **RU (Request Unit)** | Unit measuring the resource cost of an operation |
| **RU/s** | Available RU rate according to capacity configuration/mode |
| **429** | Request rate-limited/throttled when capacity is insufficient at that moment |

SDKs and semantics for MongoDB, Cassandra, or Gremlin can differ. Do not assume that Java SDK for NoSQL configurations or methods apply across all Cosmos DB APIs.

## 4. Typical Application Architecture

~~~mermaid
flowchart LR
    CLIENT[Web / Mobile] --> API[Java API on AKS / App Service]
    API --> SDK[Azure Cosmos DB Java SDK]
    SDK --> NET[Private endpoint / Network / TLS]
    NET --> COSMOS[(Cosmos DB for NoSQL)]
    COSMOS --> MON[Azure Monitor]
    API --> APPMON[Application Insights]
    ID[Microsoft Entra ID / Managed identity] --> SDK
~~~

The data path should be viewed across multiple layers:

1. The client calls the API with its own deadline and retry policy.
2. The Java API uses the Cosmos DB SDK and its connection pool/resource scheduling.
3. The SDK routes operations to the appropriate service/replica.
4. Cosmos DB calculates RUs for the request.
5. The request succeeds or receives an error such as 429/400/404/409/412/503.
6. The SDK may automatically retry certain conditions depending on configuration.
7. The application records the business outcome and telemetry.

**Measure Java API latency separately from actual request latency after SDK retries.** A Java call that returns HTTP 200 after three Cosmos DB retries may still have taken a long time.

## 5. Getting the JSON Model and Partition Key Right from the Start

Example storing each order as an item:

~~~json
{
  "id": "ORD-1001",
  "tenantId": "tenant-42",
  "customerId": "C-20",
  "status": "CREATED",
  "amount": 125000,
  "schemaVersion": 1
}
~~~

Suppose the container is created with a **partition key path** of **/tenantId**. Then:

- An item with tenantId = tenant-42 belongs to the corresponding logical partition.
- Most point operations must supply both the **id and partition key value**.
- Items with the same tenantId can concentrate into a hot logical partition if that tenant generates too much traffic.
- Queries without tenantId may have to query multiple partitions and consume more RUs.

### 5.1. Do Not Confuse the Partition Key Path and Value

- Container partition key path: **/tenantId**.
- Item partition key value: **tenant-42**.
- The Java SDK passes the value via **new PartitionKey("tenant-42")**, not the string **"/tenantId"**, for a point read.

### 5.2. An id Is Not Necessarily Unique Across the Entire Container

For a partitioned container, the **id + partition key value** pair identifies an item under the model semantics. Two different tenants can use the same id in appropriate designs. Therefore, attempting to read an item by id alone without knowing the partition key is a common design mistake.

### 5.3. Choose the Key Based on Access Patterns

| Workload | Suggested partition key | Considerations |
|---|---|---|
| Multi-tenant orders | /tenantId | Large tenants can become hot |
| Shopping carts | /customerId or an application-designed composite key | Check carts per customer and hot spots |
| IoT telemetry | /deviceId if per-device load is balanced | One very busy device can become a bottleneck |
| User profiles | /userId | Point reads are cheap when id and userId are known |
| Heavily skewed data | Synthetic or hierarchical key when supported | Design for queries, hot keys, and older data |

There is no universally optimal partition key for every application. Test load distribution with expected data rather than picking a field simply because its name sounds natural.

## 6. What Are Request Units and Request Charge?

A **Request Unit (RU)** is a measure of the resources Cosmos DB needs to execute an operation: CPU, I/O, and related components. Every request consumes a measurable **request charge**.

Different operations consume different amounts of RUs:

- A point read of a small item with id and partition key is usually efficient.
- A filtered query missing the partition key may need to read across multiple partitions.
- A query that scans many documents can cost far more RUs than fetching a single item.
- Writing large items or updating indexed fields can increase the charge.
- Query complexity, result size, indexing policy, and data shape all affect RUs.

To understand the general trend, suppose a test measures:

| Sample operation | Measured request charge (example) |
|---|---:|
| Small item point read | 1 RU |
| Create item | 5 RU |
| Single-partition query | 12 RU |
| Cross-partition query | 80 RU |

**These numbers are illustrative examples, not unit prices or guaranteed service charges.** Use **response.getRequestCharge()** on an actual request to observe real values.

### 6.1. RU/s Is a Rate Budget

If a container is provisioned with 1,000 RU/s and the average workload requires 5 RU/request, the ideal throughput is near 200 requests/second, assuming even distribution and no other bottlenecks:

\[
\text{Max requests/second by RU}
\approx \frac{\text{Available RU/s}}{\text{Average RU/request}}
\]

However, this division does not account for traffic spikes, physical partitions, hot keys, multi-region replication, consistency, payload variation, retries, or connection limits.

## 7. Provisioned Throughput, Autoscale, and Serverless

Three capacity models to consider depending on current feature/tier/region support:

| Model | Idea | Best suited when |
|---|---|---|
| **Manual provisioned throughput** | Allocates a configured amount of RU/s | Load is relatively steady and predictable |
| **Autoscale throughput** | Scales capacity within a supported range up to a configured maximum | Load fluctuates significantly by hour or event |
| **Serverless** | Billed per request consumption within feature/limit bounds | Low or intermittent workloads with little need for always-on throughput |

### 7.1. Autoscale Does Not Mean Unlimited

Autoscale has a maximum RU/s ceiling, capacity scaling mechanics, and per-physical-partition limits. If the workload exceeds the ceiling or concentrates on a hot partition, 429 errors can still occur.

### 7.2. Serverless Also Has Throttling

Serverless is not an option that allows sending arbitrary request volumes at any moment. Check actual RU/s limits, storage limits, and regional/feature availability before choosing it.

### 7.3. Database-Level and Container-Level Throughput

Throughput can be configured at the container level or shared across a database under supported models. When multiple containers share database-level throughput, they can affect one another.

### 7.4. Choosing a Model for the Workload

- Steady web APIs with SLOs: measure RUs and choose manual or autoscale appropriately.
- Flash-sale traffic: autoscale plus backpressure; verify peak limits.
- Infrequent batch jobs: evaluate serverless or throughput/cost caps under supported conditions.
- Multi-tenant workloads with a massive tenant: resolve partition skew even if overall RU/s is increased.

## 8. Logical Partitions, Physical Partitions, and Hot Partitions

A **logical partition** consists of items that share the same partition key value. The underlying infrastructure divides data into **physical partitions**, each with resource limits and an allocated share of RU/s.

~~~mermaid
flowchart TD
    APP[Requests from Java SDK] --> PK{Partition key}
    PK --> A[tenant-42 - logical partition]
    PK --> B[tenant-17 - logical partition]
    PK --> C[tenant-88 - logical partition]
    A --> P1[(Physical partition A)]
    B --> P2[(Physical partition B)]
    C --> P2
~~~

This is a conceptual diagram. Physical partition placement is managed by the platform and can change as data volume or provisioned capacity grows.

### 8.1. Why Increasing Total RU/s Sometimes Fails to Eliminate 429s

Suppose 80% of writes go to a single tenant. Even if the account/container has high total RU/s, physical partition limits or a hot logical key can cause that tenant to be throttled while other partitions have unused capacity.

### 8.2. Signs of a Hot Partition

- 429 errors occur predominantly for one tenant/key.
- Normalized RU utilization across physical partitions is uneven when telemetry is available.
- Increasing total RU/s does not yield a proportional improvement.
- One key has disproportionately high writes or queries.
- Latency for other tenants remains healthy.

### 8.3. Mitigation Options

1. Measure RUs by operation and key.
2. Check whether the chosen partition key is too coarse.
3. Distribute the workload using a business subkey or synthetic key if queries allow it.
4. Use hierarchical partition keys when compatible and appropriate for the model.
5. Avoid business transactions requiring atomicity across multiple logical partitions if the architecture cannot support them.
6. Plan a migration when changing the partition key path, since you cannot simply alter it in place on an existing container with data.

## 9. Preparing the Java Project and SDK v4

This lesson assumes a Java project configured with Maven or Gradle using **Azure Cosmos DB Java SDK v4**, artifact **com.azure:azure-cosmos**. If using Microsoft Entra identity, also add **com.azure:azure-identity**.

Example Maven dependencies:

~~~xml
<dependencies>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-cosmos</artifactId>
    <version>YOUR_COMPATIBLE_4_X_VERSION</version>
  </dependency>
  <dependency>
    <groupId>com.azure</groupId>
    <artifactId>azure-identity</artifactId>
    <version>YOUR_COMPATIBLE_IDENTITY_VERSION</version>
  </dependency>
</dependencies>
~~~

Replace placeholders with stable versions compatible with your JDK and project SDK policy. You can manage versions using an organization-approved BOM. Do not hardcode an old version and assume it remains safe forever.

### 9.1. Commonly Used Classes

| Class | Purpose |
|---|---|
| **CosmosClientBuilder** | Builds a sync or async client |
| **CosmosClient** | Synchronous client reused across many requests |
| **CosmosAsyncClient** | Asynchronous/reactive client |
| **CosmosDatabase** | Represents a database |
| **CosmosContainer** | Performs CRUD/query operations on a container |
| **PartitionKey** | Partition key value for a request |
| **CosmosItemResponse** | Status, item, request charge, diagnostics |
| **CosmosException** | HTTP/service errors and metadata |
| **CosmosQueryRequestOptions** | Query options |
| **CosmosPagedIterable** | Paginated query results |

### 9.2. Do Not Create a Client per Request

CosmosClient is designed to be **reused across the application**. Creating a new client on every HTTP request wastes resources, causes connection churn, and increases latency.

### 9.3. Do Not Hardcode Keys in Source Code

For demos, an account key may be passed from a secret store at runtime; production should prefer Microsoft Entra data-plane RBAC and managed identity when supported by the architecture and SDK.

## 10. Authentication, Microsoft Entra ID, and Data-Plane RBAC

There are two common options:

1. **Account key:** simple for labs, but grants broad permissions and requires strict control.
2. **Microsoft Entra token credential:** suited for identity-based access, requiring a role assignment on the **Cosmos DB SQL data plane** and appropriate permissions.

### 10.1. Initializing the Java Client with an Entra Credential

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.identity.DefaultAzureCredentialBuilder;

public final class CosmosConnection {
    public static CosmosClient connect() {
        String endpoint = System.getenv("COSMOS_ENDPOINT");
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalArgumentException("COSMOS_ENDPOINT missing");
        }

        return new CosmosClientBuilder()
            .endpoint(endpoint)
            .credential(new DefaultAzureCredentialBuilder().build())
            .buildClient();
    }
}
~~~

**Note:** this example is for an SDK v4 version that supports TokenCredential. Role assignments and permissions must exist before access; an Azure ARM Reader or Contributor role does not automatically grant permission to read or write items.

### 10.2. Data-Plane Roles vs. Management-Plane Roles

- **Azure RBAC management:** creates/modifies resources and settings.
- **Cosmos DB for NoSQL data-plane RBAC:** authorizes reading/writing items and running queries via built-in/custom data roles at the appropriate scope.
- **SDK identity:** managed identity, Workload Identity, or developer credentials depending on the environment.

Examples of data roles include **Cosmos DB Built-in Data Reader** or **Cosmos DB Built-in Data Contributor** (role names under the NoSQL RBAC model). Grant the minimum required scope; do not assign account Owner arbitrarily just to silence a 403 error.

### 10.3. Managed Identity on AKS / App Service / Functions

These runtimes can use managed identity or AKS Workload Identity. Verify the correct tenant, client ID, token, role scope, and propagation delay. DefaultAzureCredential can select different credentials locally versus in the cloud, so log the identity type safely when debugging.

## 11. Initializing Synchronous CosmosClient

In a lab where your organization has not configured Entra identity yet, you can retrieve a key from environment variables or a secret store:

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.ConsistencyLevel;

public final class CosmosClientFactory {
    private CosmosClientFactory() {}

    public static CosmosClient build() {
        String endpoint = require("COSMOS_ENDPOINT");
        String key = require("COSMOS_KEY");

        return new CosmosClientBuilder()
            .endpoint(endpoint)
            .key(key)
            .consistencyLevel(ConsistencyLevel.SESSION)
            .buildClient();
    }

    private static String require(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing " + name);
        }
        return value;
    }
}
~~~

**An account key is a secret**: never place COSMOS_KEY in committed files, container images, or public commands/logs. Key-based examples are only for introducing the SDK. Production should prefer identity-based access whenever supported and applicable.

### 11.1. Closing the Client Properly Across Its Lifecycle

Create one client per application/bean and close it when the application shuts down:

~~~java
CosmosClient client = CosmosClientFactory.build();
try {
    // Execute business operations...
} finally {
    client.close();
}
~~~

Do not close the client after every database call in a multi-request application.

### 11.2. Synchronous vs. Asynchronous

- **CosmosClient:** sync API, easy to learn, calls block the thread.
- **CosmosAsyncClient:** reactive API built on Reactor, well suited for I/O-heavy pipelines when operated in a properly nonblocking manner.

Do not pick async just because it sounds "fast": unbounded concurrency can overload the SDK, the application, or Cosmos DB.

## 12. Databases/Containers and the Role of Infrastructure Provisioning

In production, **creating databases, containers, indexing policies, partition keys, and throughput** usually belongs to an approved IaC/management pipeline. A runtime application should not attempt to create databases/containers or modify throughput on every startup.

Example accessing existing resources:

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.CosmosDatabase;

public final class CosmosResources {
    public static CosmosContainer orders(CosmosClient client) {
        CosmosDatabase database = client.getDatabase("shopdb");
        return database.getContainer("orders");
    }
}
~~~

Obtaining a proxy object does not necessarily validate that the resource or permissions exist right away; errors may surface only when an actual operation runs.

### 12.1. Important Container Settings

- Partition key path, for example **/tenantId**.
- Indexing policy and indexed fields.
- Unique key policy if required by the application.
- TTL when storing data with a defined lifecycle.
- Provisioned throughput/autoscale or chosen capacity mode.
- Account regions and consistency settings.

### 12.2. Choosing the Wrong Partition Key Usually Requires Migration

The partition key path is a critical architectural decision at container creation time; do not assume it can simply be changed in place on a container that already holds data. When a change is needed, you normally must plan to create a new container and migrate the data.

## 13. Java POJOs and Serialization

The SDK for NoSQL stores documents as JSON. A simple Java POJO:

~~~java
public class OrderDocument {
    public String id;
    public String tenantId;
    public String customerId;
    public String status;
    public long amount;
    public int schemaVersion;

    public OrderDocument() { }

    public OrderDocument(String id, String tenantId, long amount) {
        this.id = id;
        this.tenantId = tenantId;
        this.amount = amount;
        this.status = "CREATED";
        this.schemaVersion = 1;
    }
}
~~~

Public fields keep the example concise; real projects can use getters/setters, immutable models, validation, and appropriate Jackson annotations.

### 13.1. id and Partition Key Must Be Consistent

If the container partition key path is **/tenantId**, the item must include a tenantId field of the right type and value. Passing a PartitionKey value that differs from tenantId in the body can cause an error.

### 13.2. Choose a Safe Currency Representation

This example uses **long amount** to represent currency in the smallest unit per business convention; avoid floating-point types for financial values requiring exact precision. Decimal serialization can be used when supported by the data contract.

### 13.3. Schema Version

Include **schemaVersion** to support consumer upgrades, migrations, and distinguishing old vs. new documents. Schema flexibility in Cosmos DB does not mean the application can skip a data contract.

## 14. Java CRUD: Create, Point Read, Upsert, and Delete

Suppose the **orders** container has partition key path **/tenantId**.

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;

public final class OrdersStore {
    private final CosmosContainer container;

    public OrdersStore(CosmosContainer container) {
        this.container = container;
    }

    public void create(OrderDocument order) {
        CosmosItemResponse<OrderDocument> response =
            container.createItem(
                order,
                new PartitionKey(order.tenantId),
                new CosmosItemRequestOptions());

        System.out.println(
            "create RU=" + response.getRequestCharge());
    }

    public OrderDocument read(String id, String tenantId) {
        CosmosItemResponse<OrderDocument> response =
            container.readItem(
                id,
                new PartitionKey(tenantId),
                OrderDocument.class);

        System.out.println(
            "read RU=" + response.getRequestCharge());

        return response.getItem();
    }

    public void delete(String id, String tenantId) {
        container.deleteItem(
            id,
            new PartitionKey(tenantId),
            new CosmosItemRequestOptions());
    }
}
~~~

### 14.1. Create vs. Upsert

- **createItem:** creates a new item; can return **409 Conflict** if an item with the same unique identity already exists.
- **upsertItem:** inserts if absent or updates if present, according to SDK/API semantics.
- **replaceItem:** replaces an existing item, optionally paired with an ETag check for version validation.
- **deleteItem:** deletes by id and partition key.

Do not use upsert carelessly for retry handling if business logic needs to detect duplicates rather than silently overwrite data.

### 14.2. Point Reads Are Usually More Efficient Than Querying by id

If you already have **id + partition key**, use **readItem** instead of a SQL query searching by id. It avoids query planning/cross-partition overhead and typically has a lower request charge.

### 14.3. A Response Alone Does Not Prove Full Business Completion

HTTP 200/201 confirms that the Cosmos operation succeeded, not that the entire payment flow, email delivery, or Service Bus publish succeeded. Use transactions/outbox/idempotency at the business layer.

## 15. Optimistic Concurrency with ETag

Multiple clients may read and modify the same item simultaneously. Unconditional replaces allow one client to overwrite another client's changes.

Cosmos DB provides **ETag** and conditional writes to detect concurrent modifications.

Workflow:

1. Read the item and its ETag.
2. Perform business validation on that snapshot.
3. Replace with **If-Match ETag**.
4. If the item changed before the replace, receive **412 Precondition Failed** and handle the conflict.

Example:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;

public void updateStatus(CosmosContainer container,
                         String id,
                         String tenantId,
                         String newStatus) {

    PartitionKey pk = new PartitionKey(tenantId);

    CosmosItemResponse<OrderDocument> current =
        container.readItem(id, pk, OrderDocument.class);

    OrderDocument order = current.getItem();
    order.status = newStatus;

    CosmosItemRequestOptions options =
        new CosmosItemRequestOptions();
    options.setIfMatchETag(current.getETag());

    container.replaceItem(order, id, pk, options);
}
~~~

### 15.1. 412 Is Not 429

**412** is an optimistic concurrency conflict, not an RU/s shortage. Retry by reading the latest item and re-evaluating business logic rather than blindly repeating the replace.

### 15.2. Conditional Writes and Idempotency

ETag prevents lost updates, but it does not replace a business idempotency key. A "debit funds" operation executed twice can still cause double charging if each retry fetches a fresh ETag without checking an operation ID.

## 16. Querying with Partition Keys and Parameters

Example querying orders for a specific tenant:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.models.CosmosQueryRequestOptions;
import com.azure.cosmos.models.PartitionKey;
import com.azure.cosmos.models.SqlParameter;
import com.azure.cosmos.models.SqlQuerySpec;

import java.util.Arrays;

CosmosQueryRequestOptions options =
    new CosmosQueryRequestOptions()
        .setPartitionKey(new PartitionKey("tenant-42"));

SqlQuerySpec query = new SqlQuerySpec(
    "SELECT * FROM c WHERE c.tenantId = @tenant AND c.status = @status",
    Arrays.asList(
        new SqlParameter("@tenant", "tenant-42"),
        new SqlParameter("@status", "CREATED")
    )
);

container.queryItems(
    query, options, OrderDocument.class
).forEach(order -> {
    System.out.println(order.id);
});
~~~

### 16.1. Queries Without a Partition Key

If no partition key is specified, a query may fan out across multiple partitions. That increases RUs, latency, and the likelihood of throttling. Some analytical workloads genuinely require cross-partition queries, but they must be measured and budgeted.

### 16.2. Use Parameterized Queries

Do not concatenate user input directly into SQL text. Using SqlQuerySpec with SqlParameter ensures controlled parameter handling.

### 16.3. Avoid SELECT * Out of Habit

Project only the fields you actually need, add appropriate indexes, and paginate results. Large response bodies add network overhead and can increase request charges.

## 17. Reading Request Charge and SDK Diagnostics

To address throttling effectively, measure **RU/operation** rather than only counting requests.

~~~java
import com.azure.cosmos.models.CosmosItemResponse;

CosmosItemResponse<OrderDocument> response =
    container.readItem(
        "ORD-1001",
        new com.azure.cosmos.models.PartitionKey("tenant-42"),
        OrderDocument.class);

double charge = response.getRequestCharge();
int status = response.getStatusCode();

System.out.println(
    "Cosmos response status=" + status + " RU=" + charge);
~~~

Different SDK response objects (item responses, query feed pages, stored procedures, etc.) expose request charge and diagnostics accordingly. For paginated queries, the total RU of the **entire query** is the sum of charges across all pages actually read, not just the first result.

### 17.1. Cosmos Diagnostics

The SDK provides diagnostics to inspect latency, backend requests, regions, retries, and network behavior using available telemetry. You can log diagnostics whenever a request exceeds a latency threshold.

**Do not log full diagnostics at high throughput** without checking log volume, overhead, and sensitive fields. Use sampling/thresholds and correlation IDs.

### 17.2. Activity ID

Service responses and errors can include an **activity ID** for tracing and troubleshooting. Record activity IDs safely in logs and incident tickets, but do not treat them as business idempotency keys.

### 17.3. Three Separate Metrics

- **RU/request:** per-operation efficiency cost.
- **Requests/second:** load and actual throughput.
- **p95/p99 latency:** application experience, including retry delays.

Optimizing one metric while ignoring the other two can lead to misleading conclusions.

## 18. HTTP 429 Errors: What Happens?

When a request requires more RUs than are currently available within the relevant scope, Cosmos DB may return **HTTP 429 Too Many Requests**. The server typically includes a wait hint before retrying, such as **Retry-After** or the **x-ms-retry-after-ms** header depending on protocol/SDK.

~~~mermaid
sequenceDiagram
    participant A as Java application
    participant S as Cosmos DB Java SDK
    participant C as Azure Cosmos DB
    A->>S: CreateItem
    S->>C: Request needing RUs
    C-->>S: 429 + retry-after
    S->>S: Wait per retry policy
    S->>C: Retry request
    C-->>S: 201 + request charge
    S-->>A: Success response
~~~

### 18.1. A 429 Does Not Always Mean the System Is Broken

In a cost-optimized system, a small rate of internal 429s may be retried successfully by the SDK without the caller seeing an error. However, **sustained 429s, excessive retries, or SLO-breaching latency** are issues that require resolution.

### 18.2. 429s Can Still Originate from a Hot Partition

If a single logical partition is hot, simply increasing total container throughput may not allocate enough resources to that partition due to physical limits or key design. Always inspect partition-level metrics and workload distribution.

### 18.3. When Does the Client See CosmosException 429?

If SDK retries exhaust their retry budget or duration, the request is canceled, or the policy does not retry that case, the application can receive a CosmosException with status 429. Do not mistakenly assume every initial 429 surfaces directly to Java code.

## 19. Automatic Retries in the Cosmos DB Java SDK

Java SDK v4 includes built-in retry handling for throttling and related transient conditions per the configured policy and SDK version implementation. Its goal is to honor server hints and recover from brief RU exhaustion bursts.

**Key points:**

- The SDK may retry some requests transparently while application code sees only the final response.
- Retries **increase end-to-end latency**.
- SDK retries are no substitute for increasing throughput or fixing a hot partition.
- Retry count and maximum wait limits depend on SDK version and configuration; do not assume a single universal default fits every project.
- Do not wrap every SDK call in an unbounded retry loop at the application layer.

### 19.1. Avoid Double Retries

If the SDK already retries several times, then the application retries the whole operation multiple times, and the API gateway also retries HTTP calls, total attempt volume can multiply dramatically.

Mental model:

~~~text
SDK retry budget
     x
Application retry budget
     x
HTTP client retry budget
     =
Far more attempts than expected
~~~

Define clearly which layer owns retries and cap total latency and attempts.

### 19.2. Retry-After Is a Throttling Signal

When writing outer retry logic for cases where the SDK surfaces a 429 to the application, honor the **retry-after** hint provided by the service instead of retrying immediately. Add jitter and a deadline so workers do not burst in lockstep.

### 19.3. Do Not Sleep Indefinitely on Java Request Threads

Use bounded backoff in sync apps where appropriate, or nonblocking scheduler delays in reactive pipelines. Never call Thread.sleep for minutes inside request handlers to mask long-term throughput shortages.

## 20. Reading and Classifying CosmosException

An error handler should classify status codes carefully:

| Status | Typical meaning | Handling approach |
|---|---|---|
| **400 Bad Request** | Invalid payload, query, partition key, or request | Fix input/code; do not blindly retry |
| **401 Unauthorized** | Invalid or expired credential/token | Check authentication |
| **403 Forbidden** | Missing permissions or policy restriction | Check data RBAC/firewall/permissions by substatus |
| **404 Not Found** | Item/container/database not found for request | Verify id + partition key + resource names |
| **409 Conflict** | Duplicate item creation or unique constraint conflict | Check idempotency |
| **412 Precondition Failed** | ETag mismatch | Re-read current item and resolve conflict |
| **429 Too Many Requests** | RU/capacity throttling | Honor retry-after, shed load, optimize RUs |
| **408/503** | Timeout or service unavailable under specific conditions | Bounded retry; inspect service/network |
| **Other 5xx** | Server or intermediary error | Classify per SDK docs and policy |

Example:

~~~java
import com.azure.cosmos.CosmosException;

try {
    store.create(order);
} catch (CosmosException ex) {
    int status = ex.getStatusCode();

    if (status == 429) {
        System.err.println("Cosmos DB throttling: review RU and latency");
    } else if (status == 409) {
        System.err.println("Document already exists: check idempotency");
    } else {
        System.err.println("Cosmos operation failed, status=" + status);
    }

    throw ex; // Caller decides the appropriate error mapping.
}
~~~

In production, do not map every CosmosException to HTTP 500. For example, 404 may represent a business "not found," 409 is a conflict, and 429 may warrant returning 503/429 or responding per your API contract and deadline, accompanied by telemetry and retry hints for callers.
## 21. Application-Level Retries: Bound Attempts and Honor Retry-After

The SDK normally already retries certain 429 errors under its internal policy. Therefore, **application-level retries should be a bounded outer safeguard**, used only when the SDK still throws an error and budget remains within the deadline. Never create infinite loops.

The following synchronous Java example applies only to an **idempotent point read**:

~~~java
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.CosmosException;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;

import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class SafeRead {
    public static OrderDocument readWithBudget(
            CosmosContainer container,
            String id,
            String tenantId) throws InterruptedException {

        int maxOuterAttempts = 3;
        long deadline = System.nanoTime()
            + Duration.ofSeconds(5).toNanos();

        for (int attempt = 1; attempt <= maxOuterAttempts; attempt++) {
            try {
                CosmosItemResponse<OrderDocument> result =
                    container.readItem(
                        id,
                        new PartitionKey(tenantId),
                        OrderDocument.class);
                return result.getItem();

            } catch (CosmosException ex) {
                if (ex.getStatusCode() != 429
                        || attempt == maxOuterAttempts) {
                    throw ex;
                }

                long remainingMs =
                    Duration.ofNanos(Math.max(
                        0, deadline - System.nanoTime()))
                        .toMillis();

                if (remainingMs <= 0) {
                    throw ex;
                }

                Duration retryAfter = ex.getRetryAfterDuration();
                long waitMs = retryAfter == null
                    ? 250
                    : Math.max(0, retryAfter.toMillis());

                long jitterMs =
                    ThreadLocalRandom.current().nextLong(0, 101);

                long delayMs =
                    Math.min(remainingMs, waitMs + jitterMs);

                if (delayMs <= 0) {
                    throw ex;
                }

                Thread.sleep(delayMs);
            }
        }

        throw new IllegalStateException("Retry budget exhausted");
    }
}
~~~

### 21.1. Important Details

- **getRetryAfterDuration()** is used per the appropriate SDK v4 API; verify compatibility with your project version.
- The SDK already performs retries; this code retries **only after the SDK still propagates a 429 outward**.
- The 5-second deadline in this example is checked **between calls**; it does not cancel an in-flight blocking SDK call. Production systems need operation/client timeouts and cancellation at the proper layer.
- Thread.sleep ties up a thread; avoid running thousands of sleeping retries simultaneously inside HTTP handlers.
- This demo retries only **reads**. Retrying writes requires evaluating idempotency and the possibility that the prior write actually committed.

### 21.2. Retry-After and Jitter

When the server gives a wait hint, honor it to reduce pressure. Jitter prevents workers from retrying at the exact same instant. Still, retries do not replace provisioned capacity or ingress rate limiting.

### 21.3. Do Not Retry Every Status Code

400 from a bad query, 403 from permissions, 409 from duplicates, and 412 from ETag conflicts each require specific handling; repeating the same request indefinitely will never fix the root cause.

## 22. Write Retries and Idempotency

Suppose:

~~~text
Client sends CREATE Order id=ORD-1001
  -> Cosmos DB commits the write
  -> Network drops before client receives the response
  -> Client assumes failure and resends
~~~

If each retry generates a **new id**, duplicate orders can be created.

### 22.1. Preserve a Business Operation ID

Use a fixed **id + partition key** pair along with an operationId to identify the same business action. If create returns **409**, read the existing item and verify its data/operationId. Treat the duplicate as success only when the same operation is confirmed committed.

### 22.2. Upsert Is Not Always Safe

Upsert can overwrite newer state if an older delayed request is retried. For critical workflows, use **ETag/If-Match**, business versioning, and explicit state-transition rules.

### 22.3. Writing to Cosmos DB Then Publishing to Service Bus

These two operations do not automatically share an atomic transaction. Consider the **transactional outbox** pattern, Change Feed, or checkpointed/idempotent event publishing to reduce the risk of committed data without an emitted message.

## 23. CosmosAsyncClient and Reactor: Bounded Asynchrony

**CosmosAsyncClient** suits Java applications using reactive programming, but it does not automatically save RUs or eliminate 429s. If flatMap is left unbounded, the application can fire far too many concurrent operations.

Reactive pipeline example:

~~~java
import com.azure.cosmos.CosmosAsyncClient;
import com.azure.cosmos.CosmosAsyncContainer;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.PartitionKey;
import reactor.core.publisher.Flux;

import java.util.List;

CosmosAsyncClient client = new CosmosClientBuilder()
    .endpoint(System.getenv("COSMOS_ENDPOINT"))
    .credential(
        new com.azure.identity.DefaultAzureCredentialBuilder().build())
    .buildAsyncClient();

CosmosAsyncContainer container =
    client.getDatabase("shopdb").getContainer("orders");

List<OrderDocument> orders = loadOrdersFromApprovedSource();

Flux.fromIterable(orders)
    .flatMap(order ->
        container.createItem(
            order,
            new PartitionKey(order.tenantId),
            new CosmosItemRequestOptions()
        ).doOnNext(result ->
            System.out.println("RU=" + result.getRequestCharge())
        ),
        8
    )
    .blockLast();

client.close();
~~~

**loadOrdersFromApprovedSource() is a placeholder**, not a built-in method. This snippet illustrates wiring the SDK with Reactor; you must build proper data sourcing, per-item error handling, and lifecycle management before running it.

### 23.1. Why flatMap Concurrency = 8?

This caps the **number of concurrent subscriptions/operations** in this pipeline stage, not a universal Azure default recommendation. Tune it based on RU budget, latency, and item size.

### 23.2. Avoid Blocking on the Event Loop

blockLast can make sense in a batch main/CLI program. Never call blocking methods on the Reactor event loop of a reactive HTTP service when avoidable.

### 23.3. Reactive Error Semantics

If one operation fails, a Flux can terminate early. Production pipelines require per-item error handling, bounded retries or dead-lettering/quarantine, and preserving remaining records. Never apply onErrorContinue blindly without understanding its side effects.

## 24. Concurrency Is Not Throughput

Suppose you run 10 AKS Pods, each issuing 100 in-flight Cosmos requests:

\[
10 \times 100 = 1{,}000\text{ in-flight requests}
\]

If the database only has RU/s capacity for a smaller rate at the current charge per operation, a thousand in-flight requests can trigger massive 429s without increasing completed requests proportionally.

### 24.1. Symptoms

- 429s increase as Pods or threads are scaled up.
- p99 rises while successful throughput stays nearly flat.
- SDK retries stretch out request duration.
- JVM memory/GC and pending request queues grow.
- API timeouts or backlogs spike.

### 24.2. Mitigation Strategies

- Reduce per-Pod concurrency.
- Use a rate limiter aligned with your RU budget.
- Move batch work onto queues and throttle workers.
- Consider increasing RU/s after measuring actual demand.
- Split hot tenants and optimize partition keys.
- Enforce deadlines and controlled load shedding.

### 24.3. A Per-Pod Semaphore Does Not Bound the Whole Cluster

A semaphore with 20 permits per Pod still allows 30 Pods to run 600 concurrent operations combined. With shared RU capacity, you need cluster-wide or per-tenant/per-workload rate limiting and coordination.

## 25. Backpressure: Concurrency Limits, Rate Limits, and Queue Budgets

**Backpressure** keeps the send rate to Cosmos DB within what actual capacity can sustain.

| Mechanism | Meaning | Effect |
|---|---|---|
| Concurrency limit | Maximum simultaneous active requests | Limits memory, threads, and in-flight work |
| Rate limit | Maximum requests/sec or estimated RU/sec | Prevents exceeding sustained RU/s |
| Queue capacity | Maximum waiting items | Prevents unbounded RAM growth |
| Timeout/deadline | Maximum lifetime of a request | Avoids holding clients past SLO |
| Fairness | Allocates capacity across tenants/workloads | Prevents heavy tenants from starving others |

### 25.1. RU-Based Token Bucket Example

Suppose a container is provisioned at 2,000 RU/s and you reserve 20% headroom:

~~~text
RU budget allocated to API: 1,600 RU/s
Measured point read: 2 RU/read
Measured write: 8 RU/write

If reads only:  ~800 reads/s
If writes only: ~200 writes/s
~~~

These are hypothetical estimates. In practice, RU/operation varies by document size, indexing, consistency, and query shape. Feed real measured request charges into your rate limiter.

### 25.2. Low Concurrency Can Still Send Requests Too Fast

If each operation is fast, a concurrency of 8 can still push thousands of requests per second. A rate limit protects RU/s differently from how a concurrency limit caps in-flight operations.

### 25.3. Avoid Overloading During Retries

When the server returns 429, slow down or pause dispatching new work rather than piling more requests into a local queue. Prevent retry storms and unbounded queue growth.

## 26. Bulk Operations: Performance and Correctness

Ingesting millions of documents often calls for async/bulk capabilities supported by your SDK version. Even with bulk support, you must manage:

- Input chunking and memory pressure.
- Degree of parallel operations.
- RU budget and retry counts.
- Per-item success/failure tracking.
- Write idempotency.
- Import progress checkpoints.
- Throttling at the physical/logical partition level.
- Impact on live APIs sharing throughput.

### 26.1. Bulk Is Not Atomic by Default

A bulk import batch can partially succeed. Never log "batch complete" simply because some writes succeeded.

### 26.2. Transactional Batch vs. Bulk

Cosmos DB supports transactional batches subject to constraints within the **same logical partition**, depending on API and service limits. Do not treat them as transactions spanning all partition keys.

### 26.3. SDK Versions Have Different APIs

Bulk features and concurrency tuning options can vary across SDK versions. Verify the documentation and release notes for your project's exact SDK version and measure actual RU/throughput rather than copying legacy tuning flags.

## 27. Pagination and Total Query Request Charge

Queries can return multiple pages. **The total RU cost of a query is not the RU cost of the first page alone.**

Example:

~~~java
import com.azure.cosmos.models.CosmosQueryRequestOptions;
import com.azure.cosmos.models.FeedResponse;

CosmosQueryRequestOptions options =
    new CosmosQueryRequestOptions();

double totalRu = 0;
long totalItems = 0;

for (FeedResponse<OrderDocument> page :
        container.queryItems(
            "SELECT * FROM c WHERE c.status = 'CREATED'",
            options,
            OrderDocument.class
        ).iterableByPage(100)) {

    totalRu += page.getRequestCharge();
    totalItems += page.getResults().size();
}

System.out.println(
    "Result items=" + totalItems + ", total RU=" + totalRu);
~~~

This query intentionally omits a partition key to demonstrate cross-partition cost in a lab. Do not use it as a default pattern on every HTTP request.

### 27.1. Continuation Tokens

The SDK supports pagination/continuation handling through the appropriate APIs. Persist tokens per contract to resume reading rather than re-running the entire query from scratch. A continuation token is not an immutable business cursor across arbitrary data mutations.

### 27.2. Page Size Affects Round Trips

Smaller page sizes can increase network round trips, while total RUs still depend on indexing, data volume, and query structure. Measure the full query instead of guessing.

## 28. Indexing Policies and Document Size

Cosmos DB indexing supports flexible query patterns, but indexes add write overhead.

### 28.1. Optimize Around Access Patterns

- Identify frequently used WHERE and ORDER BY fields.
- Review indexing policies and composite indexes where appropriate.
- Exclude unneeded paths on write-heavy workloads when supported and safe.
- Measure read/write request charges after every change.

### 28.2. Avoid Oversized Documents

If an item embeds an ever-growing event history array, write RUs and network overhead increase steadily. Consider separating event history into distinct items or containers aligned with access patterns.

### 28.3. Return Only Required Fields

Avoid SELECT * when the API only needs id, status, and amount. Projections reduce payload/network cost and can lower portions of query execution cost.

### 28.4. Do Not Disable Indexing Just to Lower Write RUs

Missing indexes can make critical queries consume far more RUs. Always evaluate the combined read/write mix.

## 29. Autoscale Still Requires Preventing Limit-Exceeding Bursts

Example changing workload:

~~~text
Normal:     200 RU/s consumed
Weekend:  1,500 RU/s consumed
Flash sale: 8,000 RU/s demanded
~~~

If the autoscale max is below demand, or a hot logical partition hits its limit, 429s will still occur.

### 29.1. Base Autoscale Max on Peak Demand

Setting max too low throttles peak traffic; setting it far higher than needed can raise costs depending on billing model and utilization.

### 29.2. Multi-Region Capacity

In a multi-region account, examine per-region distribution and throughput under the current service contract. Do not treat the sum of theoretical regional RU/s as a single budget available to a client in one region.

### 29.3. Autoscale Does Not Replace Query Tuning

A query that scans huge numbers of documents still burns excessive RUs, even if autoscale temporarily provides additional headroom.

## 30. Hot Logical Partitions in Multi-Tenant Systems

Suppose a container uses partition key **/tenantId**, and one tenant generates 75% of writes and heavy queries:

~~~text
tenant-big:    75% of request volume
tenants-other: 25% of request volume
~~~

### 30.1. Options

1. Optimize the heavy tenant's reads and writes.
2. Apply per-tenant rate limiting to protect other tenants.
3. Isolate the hot tenant into a dedicated container/capacity if architecture permits.
4. Use synthetic keys or hierarchical partition keys where supported.
5. Redesign the data model and query routing based on measurements.

### 30.2. Trade-Offs of Synthetic Keys

Splitting one tenant across multiple buckets reduces hotspots, but tenant-wide queries may fan out and single-partition transactions will no longer cover the entire tenant.

### 30.3. Changing the Partition Key Requires Migration

An existing container holding data cannot simply change its partition key path by editing a field. You need a plan to create the destination container, copy data, catch up changes, cut over, validate, and clean up.

## 31. Direct Mode vs. Gateway Mode

The Cosmos DB Java SDK offers connection modes such as Direct and Gateway depending on SDK configuration and features.

| Mode | Concept | Considerations |
|---|---|---|
| **Direct** | Connects more directly to backend partitions/replicas where supported | Ports, private networking, connection counts, NAT |
| **Gateway** | Sends operations through the HTTPS gateway | Proxy/network policies, latency, and gateway capacity |

Do not assume one mode is universally best everywhere. Measure on your actual network topology.

### 31.1. Client Reuse and Networking

Never create a CosmosClient per HTTP request. Each client manages its own connections and background threads/resources.

### 31.2. Private Endpoints and DNS

Verify FQDNs/private DNS zones, VNet integration, routing/firewalls, and connection mode requirements. Never disable TLS or open wide public Internet access as a workaround for private DNS misconfigurations.

### 31.3. Do Not Blindly Increase Connection Settings

Raising connection limits across many Pods increases memory, port, and NAT pressure without creating any new RU/s.

## 32. Consistency Levels and Latency

Cosmos DB supports consistency levels such as Strong, Bounded Staleness, Session, Consistent Prefix, and Eventual depending on configuration and capabilities.

### 32.1. Impact of Consistency

- Freshness and consistency guarantees of read data.
- Read-after-write semantics.
- Availability and latency across multiple regions.
- Resource cost under certain patterns and configurations.

### 32.2. Session Consistency

Session consistency is widely used; client/session tokens provide guarantees under the service contract. If independent clients do not share the session context, read-after-write guarantees may require explicit application handling.

### 32.3. Do Not Lower Consistency at All Costs

Payments and inventory may have strict business rules requiring fresh state on critical steps. Optimizing RUs must never violate business invariants.

## 33. Change Feed, Azure Functions, and Background Workloads

~~~mermaid
flowchart LR
    APP[Java orders-api] --> COSMOS[(Cosmos DB)]
    COSMOS --> FEED[Change Feed]
    FEED --> WORKER[Azure Function / Java worker]
    WORKER --> Q[Service Bus / Analytics]
~~~

Change Feed provides a stream of changes from Cosmos DB so processors can handle updates asynchronously according to the feed mode's semantics and features.

### 33.1. Not Automatically Exactly-Once

A worker may emit a downstream message and crash before checkpointing Change Feed progress. Upon restart, the event can be reprocessed. Implement idempotency at downstream sinks and checkpoints.

### 33.2. Change Feed Consumes Resources

Reading the feed contributes to request charge and throughput consumption. Monitor RUs so background analytics do not degrade live API SLOs.

### 33.3. Batch Jobs Need Their Own Budget

A backfill scanning millions of documents can trigger 429s for an API sharing the same container. Rate-limit batch jobs, schedule them off-peak, or isolate capacity when appropriate.
## 34. TTL and Data Lifecycle

Cosmos DB supports **Time-to-Live (TTL)** on items and containers according to their configuration.

TTL is well suited for:

- Time-bounded session data and caches.
- Temporary workflow state.
- Telemetry that does not require long-term retention.
- Transient processing outputs or audit records with approved retention windows.

### 34.1. TTL Is Not a Backup

When data expires and is deleted by lifecycle policy, TTL does not create a recoverable copy. If backup and restore are required, use mechanisms supported by Cosmos DB and approved by your organization.

### 34.2. Consider RUs and Storage

Expiration/lifecycle processing, indexes, and item sizes can affect resource usage and billing depending on the capacity mode. Do not assume all TTL expirations carry the exact same charge profile as manual deletes.

### 34.3. Data Retention Compliance

Never set short TTLs on orders, payments, or records subject to legal retention requirements without explicit approval.

## 35. Java SDK and Cosmos DB Security

Core principles:

- Prefer **Microsoft Entra ID/managed identity** and Cosmos DB for NoSQL data-plane RBAC where architecture and SDK support it.
- Separate read, write, admin, and migration permissions.
- Enforce TLS and private networking per security policy.
- Never hardcode account keys, tokens, or connection strings.
- Store account keys in Key Vault or a secret manager if keys must be used.
- Enforce tenant authorization in the application layer.
- Do not log raw documents containing personal data.
- Do not dump full Cosmos diagnostics to public logs.
- Manage secret/credential rotation and revocation.
- Maintain audit trails for sensitive operations.

### 35.1. 403 Is Not 429

HTTP 403 normally points to permissions, credentials, network policies, or substatus errors; increasing RU/s will not fix it.

### 35.2. Knowing the Partition Key Does Not Authorize Tenant Access

The API must verify that the authenticated principal is authorized for the requested tenantId before calling Cosmos DB. Never treat client knowledge of a tenantId as authorization.

### 35.3. Development Identity vs. Production Identity

DefaultAzureCredential might pick an Azure CLI credential on a developer workstation and a managed identity in the cloud. Verify the role scope and effective identity in each environment; never hand out production account keys as a shortcut for developers.

## 36. Azure Monitor, SDK Metrics, and Application Insights

An operational dashboard should combine Cosmos DB resource metrics with application telemetry:

| Layer | Metric | Question answered |
|---|---|---|
| RU consumption | Total consumed RU/s and RU per operation | Is capacity sufficient? |
| Throttling | 429 count/rate | Is throttling increasing? |
| Successful throughput | Completed ops/s | Does raising concurrency increase useful output? |
| Latency | p50/p95/p99 request & API latency | Are SDK retries delaying users? |
| Retry | SDK retries / outer retries from diagnostics | Is there a retry storm? |
| Partition usage | Normalized RU utilization / hot partition (when supported) | Is one key overheating? |
| Request type | Point read, create, query, patch, bulk | Which operations spend the most RUs? |
| Client health | JVM CPU, GC, in-flight count, network connections | Is the app itself bottlenecked? |
| Errors | 400/401/403/404/409/412/429/503 | Data, permission, capacity, or service issue? |
| Cost | Provisioned throughput, autoscale, storage, logs | Is spend aligned with expectations? |

### 36.1. Do Not Measure Only Final API Errors

The SDK may hit 429s and retry them successfully. Callers still see HTTP 200, yet p99 latency climbs. Always inspect service-side 429 metrics, SDK diagnostics, and end-to-end API durations.

### 36.2. Attribute Request Charges to Specific Operations

Break down RUs by endpoint, query shape, tenant group, and payload size (without logging sensitive data). A single aggregate RU sum makes it hard to pinpoint which query needs tuning.

### 36.3. Metrics Can Vary by Configuration

Azure Monitor metric names, diagnostic log categories, and KQL tables depend on account type and configuration. Verify your actual schema before deploying queries; do not assume all granular metrics are enabled by default.

### 36.4. Sampling and p99

Rare slow traces can be dropped by trace sampling. Combine aggregated metrics, slow-operation diagnostics, and intentional sampling policies.

## 37. Distinguishing Acceptable 429s from Incidents

Not every internal 429 is an incident if the SDK recovers cleanly and the application continues meeting its SLOs.

Warning signs that require action:

- p95/p99 exceeds SLOs.
- Final 429/5xx responses or timeouts rise.
- Retry budgets are frequently exhausted.
- Queues/backlogs keep growing.
- Autoscale reaches its configured ceiling.
- One tenant experiences chronic throttling.
- JVM resources are tied up by thousands of waiting requests.
- Total spend rises while successful throughput stays flat.

Illustrative SLO example:

~~~text
p95 API latency: under 500 ms
p99 API latency: under 1,500 ms
successful operations: over 99.9% per measurement window
background queue age: under 2 minutes
~~~

These numbers are not a universal Cosmos DB SLA. Set targets based on your application requirements, subscription, region, traffic, and contracts.

### 37.1. Watch Both Retries and Final Outcomes

If 100 requests all succeed after 5 retries each, the API success rate remains 100%, yet the system is burning extra latency and load unnecessarily. Both must be measured.

## 38. Production 429 Investigation Runbook

### Step 1 — Isolate the Scope

Are 429s happening across all requests or mainly one tenant, endpoint, or partition key? Did they start after a deployment or backfill job?

### Step 2 — Assess Impact

Measure p95/p99, final error rates, queue age, API latency, and business success rates. Do not treat every internal-retry 429 the same way as user-facing failures.

### Step 3 — Measure RUs and Query Shapes

Look for operations whose request charge jumped suddenly, fan-out queries, or larger document sizes after a schema change.

### Step 4 — Check Capacity

Manual, autoscale, or serverless? Has it hit max RU/s or service limits? Are multiple containers sharing database-level throughput?

### Step 5 — Identify Hot Partitions

Are normalized RU per physical partition, tenant distribution, and request charges skewed? If all load hits one hot key, raising total RU/s may not help.

### Step 6 — Inspect SDK Diagnostics

Check retries, activity IDs, network timings, regions, Direct/Gateway behavior, and client timeouts. Redact sensitive information before sharing diagnostics.

### Step 7 — Check the Java Application

Check Pod count, executor threads, Reactor flatMap concurrency, number of CosmosClient instances, JVM memory/GC, and multi-layer retry policies.

### Step 8 — Choose Evidence-Based Remediations

- Convert id-based queries into point reads when id + partition key are known.
- Tune indexing, filters, and pagination.
- Throttle background workers and ingestion rates.
- Lower concurrency or introduce rate limiting.
- Raise RU/s or autoscale max when capacity is genuinely the bottleneck.
- Redesign partition keys or isolate hot tenants if needed.
- Check networking if non-429 transport issues are suspected.

### Step 9 — Re-Measure and Roll Back if Needed

Compare same-workload p95/p99, successful throughput, 429/retry rates, RU/operation, and cost.

## 39. Common Errors Not to Confuse with 429

### 39.1. 400 Bad Request

Invalid query, payload, or partition key. Fix the data or code; do not blindly retry.

### 39.2. 401/403

Invalid credential, expired token, missing data-plane role, or network policy block. Inspect identity, scope, and substatus.

### 39.3. 404 Not Found

The item might exist under a **different partition key value**. Verify the id + partition key pair and resource names before assuming data loss.

### 39.4. 409 Conflict

Duplicate item creation. Handle business idempotency or genuine conflict properly; never invent a random new id just to dodge a conflict.

### 39.5. 412 Precondition Failed

The ETag changed concurrently. Re-read the latest state and re-apply business rules instead of unconditionally retrying replace.

### 39.6. 503 and Connection Timeouts

Inspect service/network regions, private DNS, Direct/Gateway mode, proxies, and client resource exhaustion. Apply bounded retries and alert if sustained.

### 39.7. High Latency with Few 429s

Possible causes include cross-partition queries, oversized payloads, app CPU/GC pauses, network RTT, or repeatedly creating new CosmosClient instances.

## 40. Capacity Planning from Measured RU Data

Sample workload:

| Operation | Peak rate | Illustrative RU/operation | RU/s |
|---|---:|---:|---:|
| Point reads | 300/s | 2 | 600 |
| Create orders | 100/s | 8 | 800 |
| Tenant queries | 30/s | 15 | 450 |
| Background writes | 50/s | 6 | 300 |
| **Total** | | | **2,150** |

This is an example calculation showing how to sum an RU budget, not standard guaranteed charges per operation type.

### 40.1. Headroom

Reserve headroom for traffic bursts, charge variance, retries, and secondary workloads. Do not rely on one fixed headroom factor for every system; load test against realistic distributions.

### 40.2. Do Not Rely Only on Average RUs

A query for a small tenant might cost 5 RUs while the same query for a large tenant costs 200 RUs. Track p95/p99 request charges and per-tenant distributions.

### 40.3. Autoscale Max and Physical Partitions

Even if total math looks sufficient, a hot logical partition can still hit local limits. Always check partition distribution and regional metrics.

### 40.4. Replays and Backfills Have RU Costs

One million writes represent substantial RU consumption. Plan them around budget, scheduling windows, rate caps, and API impact.

## 41. Cost and Economic Optimization

Primary cost drivers:

- Provisioned RU/s or autoscale throughput.
- Serverless request consumption when using that mode.
- Data storage and index storage size.
- Multi-region replication and read/write topology.
- Network egress / Private Link.
- Azure Functions, AKS, and App Service compute.
- Azure Monitor / Log Analytics ingestion and retention.
- Backup/DR per configuration and pricing model.
- Background imports, bulk jobs, and retries.

### 41.1. Changes That Reduce Both RUs and Latency

- Point reads instead of querying by id.
- Including the partition key in queries.
- Appropriate indexing policies and projections.
- Trimming document size where business rules permit.
- Splitting hot workloads with an appropriate key strategy.
- Capping batch concurrency and avoiding duplicate writes.
- Avoiding cross-partition fan-out on every HTTP request.

### 41.2. When Is Increasing Throughput the Right Call?

When queries and the data model are already well optimized and the workload genuinely requires more RU/s; size capacity from measurements, SLOs, and budget.

### 41.3. When Is Increasing Throughput the Wrong First Move?

If the application scans the entire container for a single item or hits one ultra-hot tenant, fixing the access pattern or partitioning strategy first is usually far more effective.

## 42. Sync vs. Async: Choosing the Right Java Model

| Aspect | CosmosClient sync | CosmosAsyncClient reactive |
|---|---|---|
| Call style | Imperative; thread waits on I/O | Mono/Flux |
| Simplicity | Usually straightforward | Requires managing reactive lifecycle |
| Concurrency | Executors / thread pools | flatMap / schedulers / backpressure |
| Risk | Many blocked threads | Firing too many requests if unbounded |
| Request charge | Billed by Cosmos DB | Equivalent operations have the same RUs; not automatically cheaper |
| Retry | SDK + bounded outer policy if needed | SDK + reactive error/deadline logic |
| Best fit | Imperative Java APIs and batch tools | I/O-heavy reactive services |

### 42.1. Async Does Not Fix Throttling by Itself

If 1,000 sync requests hit 429s due to insufficient RUs, converting them into 1,000 async requests creates zero extra RU/s.

### 42.2. Do Not Block the Reactor Event Loop

In reactive web handlers, avoid calling block() and starving event-loop threads. In a CLI batch entry point, blockLast() may be appropriate to wait for completion.

### 42.3. Size Concurrency Using Telemetry

Measure request charges, throughput, SDK diagnostics, JVM memory, and p95/p99; do not pick concurrency solely from CPU core counts.

## 43. Lab: Provision Cosmos DB for NoSQL and Connect the SDK

**Prerequisites:** use an authorized Azure subscription/resource group with quota/budget and zero production data.

### 43.1. Provision Resources

In the Azure Portal:

1. Create a dedicated resource group, e.g., **rg-cosmos-sdk-lab**.
2. Create an **Azure Cosmos DB for NoSQL account**.
3. Choose a region and capacity mode suitable for a lab.
4. Create database **shopdb**.
5. Create container **orders** with partition key path **/tenantId**.
6. Record the throughput/capacity limit.
7. Configure networking, TLS, and access permissions.
8. Assign an appropriate data-plane role to your managed or developer identity if using Entra.
9. Enable Azure Monitor metrics.
10. Record the account endpoint for Java configuration.

### 43.2. Prepare the Java App

1. Add approved versions of the azure-cosmos v4 and azure-identity dependencies.
2. Set **COSMOS_ENDPOINT** to the actual endpoint.
3. Use DefaultAzureCredential with an identity holding a data-plane role.
4. If the lab uses an account key, store it in a secret store or uncommitted environment variables.
5. Instantiate one CosmosClient for the application lifecycle.
6. Create and read several items with id + tenantId.

### 43.3. Classify Connection Errors

- 403: likely missing data-plane role or policy restriction.
- 401: invalid credential/token.
- 404: wrong resource name, id, or partition key.
- Timeout: DNS, firewall, or Direct/Gateway settings.
- 429: insufficient RU capacity at request time; inspect metrics.

Do not raise RU/s to fix a 401 or DNS issue.

## 44. Lab: Safely Measure 429s and Backpressure

**Goal:** demonstrate RU/request, throughput, 429s, and the impact of concurrency/retries using a small, cost-controlled test.

### A. Baseline

1. Create a few hundred synthetic items across multiple tenantIds.
2. Read items using point reads with id + partition key.
3. Query within a single tenant.
4. Run a bounded cross-partition query.
5. Record RU per request and total query RUs.
6. Measure p50/p95/p99 and successful requests/second.

### B. Increase Load in Small Steps

1. Test concurrency 1.
2. Test concurrency 4 and 8 if the environment permits.
3. Observe 429s in metrics, retries, and final errors.
4. Stop immediately if safe load or cost thresholds are exceeded.
5. Never intentionally exhaust shared quotas or disrupt shared accounts.

### C. Test a Hot Partition

1. Send a burst of requests to one synthetic tenantId.
2. Send the same request volume distributed across many tenants.
3. Compare latency, throttling, and RU distribution.
4. Do not draw conclusions from a single run; repeat under comparable conditions.

### D. Optimize One Factor at a Time

- Replace id queries with point reads.
- Include the partition key in queries.
- Reduce projected fields returned.
- Cap Reactor concurrency.
- Apply a rate limiter aligned with measured RU budgets.
- If permitted, adjust RU throughput or autoscale max and compare.

### E. Summary Report Table

| Metric | Baseline | After optimization |
|---|---|---|
| Successful operations/s | Measured | Measured |
| RU/operation | Measured | Measured |
| p95/p99 latency | Measured | Measured |
| Service 429 count | Measured | Measured |
| SDK retry count | Measured | Measured |
| Final 429/5xx | Measured | Measured |
| In-flight requests | Measured | Measured |
| Max partition usage | Measured | Measured |
| Estimated cost | Measured | Measured |

**Completion criteria:** concrete evidence that a change reduced RUs/429s or improved p95/p99 without data loss or unreasonable cost.

## 45. Real-World Application Scenarios

### 45.1. Flash Sale Causes 429s Across All Tenants

Check overall RU utilization, autoscale max, API burst rate, batch workers, SDK retries, and latency. Throttle ingress, offload long work to queues, raise capacity where justified, and re-test.

### 45.2. One Large Tenant Sees More 429s Than Others

Inspect partition key path /tenantId, hot partitions, per-tenant RU consumption, and data distribution. Optimize by key or plan tenant isolation/migration.

### 45.3. Backfill Slows Down the Live API

A background job scanning many documents can consume shared RU budgets. Add a job rate limit, lower concurrency, schedule off-peak, or use separate capacity.

### 45.4. API Returns 200 but p99 Rises

The SDK may be retrying 429s internally. Inspect diagnostics, RU metrics, and total elapsed time instead of looking only at final HTTP status codes.

### 45.5. App Creates a CosmosClient per Request

Causes connection churn, excess background resources, and startup overhead. Reuse one client for the app lifecycle and re-measure.

### 45.6. CreateItem Returns 409 After a Timeout

The first request may have committed while the client missed the response. Read the item by id + partition key and compare operationId; never generate a different id to bypass the conflict.

## 46. Production Checklist

- [ ] Use SDK v4 for Cosmos DB for NoSQL and pin an appropriate version.
- [ ] Account/database/container are provisioned in a controlled manner.
- [ ] Partition key is chosen from access patterns and load distribution.
- [ ] Hot logical partitions and large tenants have been evaluated.
- [ ] Items carry appropriate business ids and idempotency keys.
- [ ] CosmosClient is reused rather than created per request.
- [ ] Identity and data-plane RBAC are preferred wherever feasible.
- [ ] Secrets are excluded from source code, container images, and logs.
- [ ] TLS and private networking have been tested.
- [ ] Point reads supply the exact id + partition key.
- [ ] Queries are parameterized and scoped with a partition key when appropriate.
- [ ] Pagination is implemented and total query RUs are measured.
- [ ] Indexing policy reflects the real query/write mix.
- [ ] Request charge is tracked per operation/tenant.
- [ ] Metrics cover 429s, RU consumption, and normalized partition usage.
- [ ] p95/p99 latency and final error rates are monitored.
- [ ] SDK automatic retry behavior is understood for the pinned version.
- [ ] Outer retries enforce deadlines and bounded attempt limits.
- [ ] Retry-After is honored with jitter, preventing retry storms.
- [ ] 400/403/409/412 errors are never blindly retried.
- [ ] Writes enforce idempotency and ETags where required.
- [ ] Reactor/executor concurrency is bounded.
- [ ] Rate limiting, admission control, and backpressure are in place.
- [ ] Batch jobs cannot exhaust live API RU budgets.
- [ ] Manual, autoscale, or serverless is selected from load measurements.
- [ ] Autoscale max and multi-region capacity behavior are verified.
- [ ] Plans exist for hot tenants or partition key migration.
- [ ] SDK diagnostics are sanitized and appropriately sampled.
- [ ] Runbooks exist for 429, 503, DNS, auth, and client overload.
- [ ] Budgets/alerts cover RUs, storage, compute, and logs.
- [ ] Load tests reflect production-like data and consistency settings.
- [ ] Timeouts, throttling, and pod restarts have been rehearsed.

## 47. Self-Check Questions

1. How does a Request Unit differ from RU/s?
2. Why does Cosmos DB return 429?
3. What server signal does Java SDK v4 use when automatically retrying 429s?
4. Why can an application still appear slow even when SDK retries eventually succeed?
5. Why can excessive outer retries trigger a retry storm?
6. When should you honor Retry-After and add jitter?
7. How does a partition key path differ from a PartitionKey value?
8. Besides id, what else is required for a point read?
9. Why can cross-partition queries consume more RUs?
10. Can a container with 10,000 RU/s always give all of its capacity to one hot logical partition?
11. Does scaling out Java Pods automatically increase Cosmos RU/s?
12. Can autoscale still encounter 429 errors?
13. Does serverless mean unlimited throughput?
14. What lifecycle should CosmosClient follow for creation and closing?
15. Does CosmosAsyncClient automatically reduce request charges?
16. What problems does excessively high flatMap concurrency cause?
17. Why does a semaphore inside one Pod not enforce a cluster-wide limit?
18. How does backpressure differ from retries?
19. What metrics are needed to implement RU-based rate limiting?
20. Why can a 409 from createItem after a timeout indicate a retry of an already-committed write?
21. Is upsert always idempotent under business semantics?
22. What problem does ETag 412 help detect?
23. How do you retrieve request charge from a Java SDK response?
24. Why must you sum RUs across all query pages?
25. Should full diagnostics be logged for every production request?
26. How do Direct mode and Gateway mode differ in network path?
27. How does consistency level affect read-after-write behavior?
28. If a background job triggers API 429s, what throttling controls can you apply?
29. How does Cosmos DB data-plane RBAC differ from Azure ARM Contributor?
30. When 429s increase, should you optimize queries/partitioning or raise RU/s first?

## 48. Summary

**Azure Cosmos DB Java SDK v4** provides CosmosClient/CosmosAsyncClient, CRUD operations, queries, request charges, and diagnostics for Java applications working with Cosmos DB for NoSQL. Effective design starts with the **partition key, RU/operation, throughput model, and access patterns**.

**HTTP 429** indicates that a request exceeded available capacity at that moment and scope. The SDK can retry based on server hints, but retries never create extra RU/s. Applications must use **bounded retries, Retry-After, deadlines, backpressure, concurrency limits, and idempotency** to avoid amplifying pressure.

Sustainable optimization relies on **point reads, partition-scoped queries, tailored indexing, reasonable document sizes, summing RUs across all pages, watching for hot partitions, and tracking p95/p99 latency alongside successful throughput**. Increase provisioned or autoscale capacity only when measurements justify the demand and fit the budget.

Combining **Microsoft Entra ID/data-plane RBAC, private networking, Java SDK diagnostics, Azure Monitor/Application Insights, and Azure Cost Management** lets you run Cosmos DB securely with predictable throughput, proper throttling handling, and minimal Azure waste.



