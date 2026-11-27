# Globally Distributed Application Lab with Cosmos DB

## 1. Problem Statement and Target Outcomes

A retail application serving customers across multiple regions must respond quickly to catalog browsing, order status checks, and order creation. If the entire API and database sit in a single region, distant users incur extra network latency; if that region suffers an outage, the entire application can go down. Deploying the API across multiple regions solves only half the problem: the data layer also needs appropriate distribution, consistency, write handling, and recovery mechanisms.

In the **Architecture and Capstone Labs** chapter of the `CLOUD_PROVIDERS_AZURE` module, this lab ties together subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, storage/data, observability, security, and cost into a globally distributed application architecture built on **Azure Cosmos DB for NoSQL**.

Learners will design and test a simple order system where:

- The API is deployed in **two regions**, fronted by an entry point supporting routing and health checks.
- An **Azure Cosmos DB for NoSQL** account is configured to distribute data across supported regions.
- A Java application uses the Cosmos DB SDK to read/write JSON documents with a **partition key**, stable identifiers, and error handling.
- The team selects **consistency levels** aligned with each business journey's requirements.
- Test scenarios cover an API region outage, primary write-region unavailability, and throttling.
- Results are measured using **latency, request charge (RU), HTTP 429 rate, observed data staleness, cost, and resilience**.

**Boundaries:** This is a design and hands-on exercise. All metrics, resource names, regions, SKUs, and load levels are illustrative; real capability must be verified against your subscription, regions, and configuration. Never trigger failovers affecting production accounts just to complete an exercise.

### 1.1. Lab Deliverables

By the end, learners should have: an architecture diagram, a consistency/partition-key selection table, a working Java program writing and reading test documents, two-region measurement tables, failure scenarios and recovery runbooks, an estimated cost table, and an explanation of trade-offs across performance, consistency, and reliability.

## 2. What Is Azure Cosmos DB and Which Model Fits?

**Azure Cosmos DB** is a family of managed database services on Azure offering multiple models/APIs. This lesson focuses on **Azure Cosmos DB for NoSQL** (API for NoSQL) for its JSON document model, SQL-style queries, mature SDKs, and multi-region data distribution capabilities.

Core concepts:

| Term | Role in lab |
| --- | --- |
| **Account** | Cosmos DB account where regions, write mode, and default consistency are configured |
| **Database** | Logical grouping containing containers |
| **Container** | Collection of JSON documents with partition key, throughput, and indexing settings |
| **Item** | A JSON document identified by `id` within a logical partition |
| **Logical partition** | Items sharing the same partition key value; key boundary for routing and transactions |
| **Physical partition** | Internal deployment unit managed and split by Cosmos DB |
| **RU (Request Unit)** | Normalized resource cost unit for executing an operation |
| **RU/s** | Provisioned or scaled throughput capacity per selected mode |
| **Consistency level** | Guarantee on data freshness and ordering observable by clients |
| **Region** | Geographic location hosting data replicas and serving account requests |
| **Partition key** | Property used to distribute documents and route queries |

A *container* is not identical to a relational table in every respect. Azure Cosmos DB for NoSQL does not natively offer arbitrary cross-table JOINs, multi-partition ACID transactions, or RDBMS relational constraints. Data modeling must follow **access patterns**, partitioning, and transaction boundaries.

### 2.1. When It Fits and When to Reconsider

Cosmos DB for NoSQL fits workloads needing low latency, data distribution, partition-based scaling, JSON documents, and well-defined access patterns. However, never choose it merely because of "global distribution":

- If you need heavy multi-entity ACID transactions across many tables and complex joins, compare against relational solutions.
- If most data is large read-heavy media/files, **Azure Blob Storage + CDN** is likely better; Cosmos DB does not replace object storage.
- If a workload is single-region with low traffic, multi-region replica costs may outweigh latency gains.
- If regulations forbid data from leaving a jurisdiction, verify **data residency** before enabling additional replication regions.

## 3. Reference Architecture: Global Entry Point, Regional APIs, Distributed Data

Assume two Azure regions meet service and data requirements:

- **Region A:** primary write region, hosting API A.
- **Region B:** secondary data region, hosting API B.
- **Azure Front Door:** terminates user HTTP(S), probes API origin health, and routes per configured policy.
- **Azure Cosmos DB for NoSQL:** single account with configured locations/regions and write mode.
- **Azure Monitor/Application Insights:** measures end-to-end SLIs, dependency latency, and failures; Cost Management tracks spend.

~~~mermaid
flowchart TB
    EU["Users across locations"] --> FD["Azure Front Door<br/>TLS, WAF, health probes, origin groups"]
    FD --> A["API Region A<br/>Java + Cosmos SDK"]
    FD --> B["API Region B<br/>Java + Cosmos SDK"]
    A --> C["Azure Cosmos DB for NoSQL<br/>one account, multiple regions"]
    B --> C
    C --> PA["Replica / write Region A"]
    C --> PB["Replica Region B"]
    OBS["Azure Monitor + App Insights"] -.-> FD
    OBS -.-> A
    OBS -.-> B
    OBS -.-> C
    IAM["Managed Identity / RBAC / Key Vault"] -.-> A
    IAM -.-> B
~~~

The diagram depicts a **logical model**; apps do not connect directly to individual replica IPs. The Cosmos DB SDK uses account/region metadata and internal routing per configuration. In **single-region write** mode, Region B can serve reads closer to local clients, **but writes still route to the write region**. Therefore, never claim write latency is identical across both regions.

### 3.1. Avoiding Confusion Between Two Types of Failover

| Layer | Component that can fail | Recovery mechanism |
| --- | --- | --- |
| **API/ingress** | API A is unhealthy while Cosmos DB remains healthy | Front Door removes the unhealthy origin and routes new requests to API B per probe/routing |
| **Database** | Cosmos DB write region becomes unavailable | Account fails over write capability per configured failover mode, subject to conditions and convergence time |
| **Other dependencies** | Identity, DNS, queues, payment provider, secrets | Require separate HA/DR design; Cosmos DB does not heal them |
| **Logic/data errors** | Item accidentally deleted or app writes bad data | Backups/restore, versioning, validation, and separate data recovery workflows |

**Global distribution does not replace full-system DR.** APIs must be deployed and verified in both regions, Front Door needs accurate health probes, permissions and DNS/private networking must work in both regions, and data recovery must meet agreed RTO/RPO targets.

### 3.2. Single-Write or Multi-Write?

**Single-region write (common default):**

- One region serves primary writes; other regions serve reads per account topology.
- Easier to maintain a single write coordinator for ordered operations.
- When the write region fails, promoting another write region requires failover; apps may see transient errors.
- Writes from distant API regions incur added network RTT back to the write region.

**Multi-region writes (optional where supported and configured):**

- Multiple regions accept writes, reducing write network distance for eligible workloads.
- Introduces **write conflicts** across regions or concurrent edits to the same document; requires a deliberate conflict-resolution policy.
- Money or inventory operations demand strict idempotency, invariants, concurrency control, and transaction scoping.
- Cost, test complexity, and consistency constraints differ from single-write mode.

**Lab decision:** start with **single-region write and two read regions**, focusing on measuring read latency and failover. Then *analyze* multi-write as a scaling extension. Never enable multi-write on an order system handling real financial transactions without proving business invariants and conflict resolution.

## 4. Document and Partition Key Design for Global Apps

In Cosmos DB for NoSQL, the **partition key** determines how items are distributed and heavily influences latency, RUs, scalability, and transaction scope. Design it around application query patterns rather than picking an arbitrary property.

### 4.1. Sample Order Document

~~~json
{
  "id": "order-10001",
  "tenantId": "tenant-a",
  "customerId": "customer-009",
  "regionOfCustomer": "apac",
  "status": "CREATED",
  "currency": "USD",
  "amount": 125.50,
  "createdAtUtc": "2026-11-20T10:00:00Z",
  "lastUpdatedAtUtc": "2026-11-20T10:00:00Z"
}
~~~

The container uses partition key path `/tenantId`. The pair **`id` + partition key value** uniquely identifies an item for point reads—for example, `order-10001` inside logical partition `tenant-a`.

### 4.2. Why Choose `/tenantId`?

Suppose a SaaS application primarily displays orders by enterprise/tenant and fetches items by `tenantId` plus `id`:

- Queries/filters for a single tenant stay scoped to a single logical partition.
- Point reads by `id` and `tenantId` let the SDK route directly, typically costing far fewer RUs than queries lacking a partition key.
- Transactional batch operations can span items **within the same logical partition** per service constraints.
- Data grouping aligns with tenant business boundaries for querying and governance.

**Risk:** one huge tenant can become a **hot logical partition** or hit logical partition storage/throughput limits. Never pick a partition key with a single constant value across all items or extreme skew.

### 4.3. Comparing Partition Key Choices

| Partition key | Advantages | Risks |
| --- | --- | --- |
| `/tenantId` | Efficient single-tenant queries and intra-tenant batches | Large tenants can create hot partitions |
| `/orderId` | Even per-order distribution; fast point reads by `orderId` | Listing all orders for a tenant requires cross-partition queries |
| `/customerId` | Easy per-customer order history | Huge customers can run hot; tenant-wide transactions impractical |
| `/regionOfCustomer` | Easy regional grouping | Low cardinality; hotspots and logical partition size limits |
| **Hierarchical partition key** (where supported) | Improves multi-tenant scale when levels are chosen well | Must understand query patterns, service limits, and SDK support |

Values like `apac` or `eu` do not keep data inside those geographic regions. **Partition keys are not a data residency mechanism.** Account region replication is configured separately; every replicated region must satisfy data compliance rules.

### 4.4. Write Model and Concurrency

For orders:

1. Client supplies a stable `orderId` or idempotency key.
2. API validates tenant access rights and business rules.
3. Write the item with `id` and `tenantId` matching the partition key.
4. On client retry of the same request, return the existing record or handle safely; **never create two distinct orders**.
5. For updates, use **ETag / optimistic concurrency** to prevent overwriting concurrent updates.
6. If multiple items must update atomically, evaluate transactional batch / same-partition rules or use a saga/outbox pattern.

**Do not treat `upsert` as complete idempotency.** Upserting the same ID can silently overwrite newer state from another request. For sensitive workflows, prefer `create` with conflict detection, valid state transitions, and version checks.

## 5. Five Consistency Levels and Real-World Impact

Azure Cosmos DB for NoSQL provides five consistency levels:

1. **Strong** – reads guarantee linearizability within supported topology/configuration constraints; can increase latency and constrain availability/topology.
2. **Bounded Staleness** – reads lag writes by at most a configured version/time bound per service parameters.
3. **Session** – operations within a session guarantee *read-your-writes* when session context is preserved.
4. **Consistent Prefix** – reads see updates in order as a prefix, though not necessarily the latest.
5. **Eventual** – replicas converge once writes stop, but reads may observe stale values before convergence.

Actual guarantees also depend on **single-write vs. multi-write, regions, account config, SDK usage, and read/write patterns**. Never assume every consistency level is available in every topology or yields identical latency.

| Journey | Candidate to evaluate | What must be verified |
| --- | --- | --- |
| Rarely changing catalog display | Eventual / Consistent Prefix if staleness is acceptable | Convergence time and tolerable staleness |
| User creates an order then views it immediately | Session can fit well | Is the session token preserved/forwarded across requests and API instances? |
| Non-real-time analytics reports | Eventual or asynchronously processed data | Reporting lag SLA and completeness |
| Critical balance/inventory updates | Requires proper invariants and transaction design | Consistency alone does not make multi-partition/region writes safe |
| Order status dashboard from a distant region | Session or UX-appropriate level | Stale reads, retries, token propagation, failover |

### 5.1. Session Tokens Across Multiple Instances

A web app often runs multiple API instances across two regions. Never assume a user's requests always hit the same process. **Session consistency** may require preserving session context or explicitly passing session tokens per SDK and architecture.

For example, a client creates an order via API A, and Front Door routes the immediate read to API B. If both APIs hold independent SDK client contexts, API B may **lack the session token from the prior write**. Design session affinity, explicit token propagation, or appropriate read-after-write flows; never promise "global read-your-writes" without testing cross-region API switching.

### 5.2. Choosing Consistency Through Testing

For each journey, document:

- Data freshness target: how much staleness is acceptable?
- Are strict event ordering and atomic transactions needed?
- Which regions issue writes and which regions issue reads?
- During a regional outage, is halting writes acceptable to preserve strict consistency?
- How are session tokens carried across requests and services?

Then measure latency and observed behavior in a real configuration rather than picking consistency solely from a theory chart.

## 6. Throughput, RU/s, and Latency

A **Request Unit (RU)** measures the normalized compute/memory/IO cost of an operation. RU cost depends on item size, indexing, query patterns, item count, partitioning, consistency, and other factors.

Cosmos DB for NoSQL capacity modes include **provisioned throughput** (manual), **autoscale throughput** where suitable, and **serverless** in supported configurations/regions. Not every mode shares the same multi-region capabilities or pricing model; verify before creating the account.

### 6.1. Illustrative RU/s Calculation

Suppose a benchmark for a workload yields:

- Average point read: **1 RU** (assumed for calculation).
- Average item create: **6 RU** (assumed for calculation).
- Peak second: **600 reads** and **100 writes**.

~~~text
Estimated RU/s
  = 600 × 1 + 100 × 6
  = 1,200 RU/s
~~~

Adding a simple 25% headroom buffer:

~~~text
Target capacity >= 1,200 × 1.25 = 1,500 RU/s
~~~

**These are not guaranteed live Cosmos DB RU numbers.** Measure actual RU charges from response headers/metrics in your environment, and verify provisioned throughput minimums, increments, partition limits, and autoscale rules. Adding regions or indexing paths changes RU and dollar costs.

### 6.2. Why Does HTTP 429 Happen?

**429 Too Many Requests** signals throttling when demand exceeds provisioned capacity at that moment or on a specific partition. Total container RU/s may still look underutilized while a single hot partition throttles.

Inspect:

- Total RU consumption and normalized RU utilization per container/partition.
- Request charge of point reads, queries, and writes.
- 429 rate, retry counts, and wait times.
- Partition key distribution, document sizes, query scans, and indexing policies.
- Client-side vs. server-side request latency, network RTT, and app CPU.

The SDK includes built-in 429 retry handling within configured limits. **Never write unbounded or synchronized retry loops**: retry storms inflate latency and mask design flaws. Use backoff, total-time bounds, timeouts, idempotency, and retry telemetry.

### 6.3. Point Reads vs. Cross-Partition Queries

When both `id` and the partition key are known, a point read is usually the cheapest and fastest operation. Queries lacking a partition key filter may fan out across physical partitions, burning RUs and increasing latency.

Example well-scoped tenant query:

~~~sql
SELECT c.id, c.status, c.createdAtUtc
FROM c
WHERE c.tenantId = @tenantId
  AND c.status = @status
ORDER BY c.createdAtUtc DESC
~~~

Parameterize queries and align indexes and partition keys with access patterns. Inspect query metrics, RU charges, composite index rules for `ORDER BY`/filters, and selectivity. Never assume every SQL-style query automatically hits an optimal index without deliberate design.

## 7. Preparing the Lab Environment Safely

### 7.1. Prerequisites

- Azure subscription with permissions to create/read Cosmos DB, resource groups, and observability resources per organizational rules.
- Isolated test account separate from production data, with a budget and cleanup date.
- Java 17+ and Maven/Gradle for the SDK example.
- Organization-vetted **`azure-cosmos` v4** SDK version, plus Azure CLI for read-only config inspection.
- Permissions to configure regions, databases/containers, and network restrictions if deployed live.
- A **synthetic** JSON dataset containing zero PII or payment card data.
- If deploying APIs across two regions, appropriate compute, ingress, and telemetry; you do not have to deploy a live Front Door just to test basic SDK reads/writes.

### 7.2. Region and Data Decisions

Pick two regions supported by your account/offer, with sufficient quota and compliance approval. Examples often use **Southeast Asia** and **East Asia**, but verify live availability by subscription, account type, zone support, quota, and service limits.

**Data residency note:** Adding Region B replication means account data replicates to that region per service behavior. Never add regions lacking legal/business approval. If regulations restrict data to specific geographies, adjust account/partitioning topology accordingly; **partition keys do not stop cross-region replication**.

### 7.3. Sample Resource Plan

| Resource | Illustrative name | Role |
| --- | --- | --- |
| Resource group | `rg-cosmos-global-lab` | Groups test resources and simplifies cleanup |
| Cosmos DB account | `cosmos-orders-global-unique` | NoSQL account; real name must be globally unique per service rules |
| Database | `commerce` | Holds containers |
| Container | `orders` | JSON items, partition key `/tenantId` |
| API Region A/B | `orders-api-a` / `orders-api-b` | Equivalent app deployments in two regions |
| Front Door | `fd-orders-lab` | Routing and health probes across both origins |
| Monitoring | App Insights / Log Analytics | Observes app and Cosmos SDK telemetry |
| Budget | `budget-global-lab` | Spend alerts at supported scope |

This is **strictly a plan**; provisioning Azure resources can incur charges as soon as throughput, replication, logging, and ingress are enabled.

## 8. Creating a Multi-Region Cosmos DB Account in Azure Portal

Azure Portal screens and fields evolve, though the core flow is:

1. Open **Azure Portal → Create a resource → Azure Cosmos DB**, and choose **Azure Cosmos DB for NoSQL**.
2. Select the test subscription/resource group; name the account and select a compliant primary region.
3. Choose a throughput model suited to a **multi-region lab**. For provisioned throughput, select manual or autoscale as appropriate; check pricing and minimums.
4. Under **Replicate data globally** (or equivalent), add a second read region and inspect failover priority order. Start with **single-write** to keep consistency simple.
5. Check the **automatic failover** option if studying automatic write-region failover; review its behavior, conditions, and failover timing.
6. Check zone redundancy against **regional support and account choices**—never assume two regions imply single-zone fault tolerance inside each region.
7. Choose a supported backup policy matching logical recovery requirements; review periodic vs. continuous options.
8. Configure identity, networking, firewall/Private Endpoints, and monitoring. Restrict public access per lab design.
9. Create database `commerce` and container `orders` with partition key **`/tenantId`**. Decide **database-level vs. container-level** throughput based on how RU/s should be allocated and shared.
10. Document the account endpoint, database/container, region list, consistency, write mode, backup, throughput, and estimated cost.

**Do not toggle on multi-region writes just because the button exists.** Base that decision on application semantics and conflict-resolution design. Some settings cannot be changed easily once an account exists; read Portal warnings before confirming.

### 8.1. Inspecting Configuration via Azure CLI (Read-Only)

~~~bash
# Verify subscription/tenant before accessing resources.
az account show --query "{subscription:id,tenant:tenantId}" -o json

# Inspect account settings and configured regions.
az cosmosdb show \
  --resource-group rg-cosmos-global-lab \
  --name cosmos-orders-global-unique \
  --query "{name:name,kind:kind,locations:locations,automaticFailover:enableAutomaticFailover,multiWrite:enableMultipleWriteLocations,consistency:consistencyPolicy}" \
  -o json

# Inspect database and container.
az cosmosdb sql database show \
  --resource-group rg-cosmos-global-lab \
  --account-name cosmos-orders-global-unique \
  --name commerce \
  -o json

az cosmosdb sql container show \
  --resource-group rg-cosmos-global-lab \
  --account-name cosmos-orders-global-unique \
  --database-name commerce \
  --name orders \
  -o json
~~~

The account and resource group names are **illustrative placeholders**, not pre-existing resources. These commands only read metadata; compare outputs against Portal settings, RBAC rules, and live throughput choices.

## 9. Writing a Java Application with the Cosmos DB SDK

The lab uses Java to create items and execute point reads. All data is synthetic; the program does not create accounts/databases/containers and must run **only after the container exists**.

### 9.1. Declaring the Dependency

In your lab project's `pom.xml`, use a supported **`azure-cosmos` 4.x** version vetted for Java compatibility in your organization:

~~~xml
<dependency>
  <groupId>com.azure</groupId>
  <artifactId>azure-cosmos</artifactId>
  <version>4.x.y</version>
</dependency>
~~~

`4.x.y` is a **placeholder, not a valid Maven version**. Replace it with a concrete stable version after checking your BOM/dependency management and SDK release notes. Never paste `4.x.y` into a pipeline expecting Maven to guess a version.

### 9.2. Environment Variables

~~~bash
# Use only a test account and an organization-approved secret store.
export COSMOS_ENDPOINT="https://<test-cosmos-account>.documents.azure.com:443/"
export COSMOS_KEY="<test-key-from-approved-secret-store>"
export COSMOS_DATABASE="commerce"
export COSMOS_CONTAINER="orders"
export COSMOS_PREFERRED_REGION_1="Southeast Asia"
export COSMOS_PREFERRED_REGION_2="East Asia"
~~~

**In production, prefer Microsoft Entra ID / Managed Identity with Cosmos DB data-plane RBAC where supported by the SDK/API and architecture**; never place account keys in code, repositories, logs, or shared configs. Key-based auth here merely illustrates the SDK flow in a controlled lab; Azure Cosmos DB account keys grant broad permissions, so protect them under least privilege and rotate them regularly.

### 9.3. Java Program Creating and Reading an Order

Example `CosmosGlobalLab` class. Uses the Azure Cosmos DB for NoSQL v4 SDK; supply a valid dependency version before running.

~~~java
import com.azure.cosmos.CosmosClient;
import com.azure.cosmos.CosmosClientBuilder;
import com.azure.cosmos.CosmosContainer;
import com.azure.cosmos.ConsistencyLevel;
import com.azure.cosmos.models.CosmosItemRequestOptions;
import com.azure.cosmos.models.CosmosItemResponse;
import com.azure.cosmos.models.PartitionKey;
import com.azure.cosmos.CosmosException;

import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.UUID;

public class CosmosGlobalLab {
    private static String requiredEnv(String key) {
        String value = System.getenv(key);
        if (value == null || value.isBlank()) {
            throw new IllegalStateException("Missing environment variable: " + key);
        }
        return value;
    }

    public static void main(String[] args) {
        String endpoint = requiredEnv("COSMOS_ENDPOINT");
        String accountKey = requiredEnv("COSMOS_KEY");
        String databaseName = requiredEnv("COSMOS_DATABASE");
        String containerName = requiredEnv("COSMOS_CONTAINER");
        String region1 = requiredEnv("COSMOS_PREFERRED_REGION_1");
        String region2 = requiredEnv("COSMOS_PREFERRED_REGION_2");

        CosmosClient client = new CosmosClientBuilder()
            .endpoint(endpoint)
            .key(accountKey)
            .consistencyLevel(ConsistencyLevel.SESSION)
            .preferredRegions(List.of(region1, region2))
            .buildClient();

        try {
            CosmosContainer container = client
                .getDatabase(databaseName)
                .getContainer(containerName);

            String tenantId = "tenant-lab";
            String orderId = "order-" + UUID.randomUUID();

            Map<String, Object> order = new HashMap<>();
            order.put("id", orderId);
            order.put("tenantId", tenantId);
            order.put("status", "CREATED");
            order.put("amount", 125.50);
            order.put("createdAtUtc", Instant.now().toString());

            CosmosItemResponse<Map> written = container.createItem(
                order,
                new PartitionKey(tenantId),
                new CosmosItemRequestOptions()
            );

            System.out.printf(
                "Created order: %s, write RU: %.2f%n",
                orderId,
                written.getRequestCharge()
            );

            CosmosItemResponse<Map> read = container.readItem(
                orderId,
                new PartitionKey(tenantId),
                Map.class
            );

            System.out.printf(
                "Read status: %s, read RU: %.2f%n",
                read.getItem().get("status"),
                read.getRequestCharge()
            );
        } catch (CosmosException error) {
            System.err.printf(
                "Cosmos operation failed. HTTP status=%d%n",
                error.getStatusCode()
            );
            // Never log account keys, PII, or raw request payloads.
            throw error;
        } finally {
            client.close();
        }
    }
}
~~~

This program uses a **synchronous client** for readability. For real web apps, evaluate the async SDK, singleton client reuse, connection tuning, and metrics/tracing; never instantiate a new `CosmosClient` per HTTP request. `preferredRegions` sets the SDK's **read/routing preference order** within the account's configured regions; it **does not add regions to the account** and does not guarantee every request executes in the top region if that region cannot handle writes or is unavailable.

**Expected result:** Creates an item with `id` and `tenantId`, then reads it back with the same partition key. Logs show write and point-read RU charges; real numbers depend on document size, indexing, and config, and will not necessarily match the illustrative 1 RU / 6 RU figures above.

### 9.4. Idempotent Duplicate Handling

In the demo, `UUID` generates a new ID on every run, which is **unsuitable** as an idempotency key for a retried business request. A real API should accept a stable client-generated request ID or store a `clientRequestId → orderId` mapping.

For example, retrying `createItem` with the same `id` in the same partition after an earlier success returns HTTP 409 Conflict. A safe handler should:

1. Catch 409 and fetch the existing item by `id + partition key`.
2. Check owner/tenant, payload hash, or business attributes to confirm it is the **same request**.
3. Return the stored outcome if identical; if the payload differs, report a genuine conflict rather than overwriting.
4. For concurrent updates, use ETags and `If-Match` conditions per SDK support.
5. Never retry an ambiguous write by generating a brand-new ID each time.

### 9.5. Testing Consistency Across Two API Instances

Design an experiment with two app instances configured with opposite preferred-region lists:

- **App A** prefers Region A; **App B** prefers Region B.
- Create an item via API A and immediately read via API A; record latency and RUs.
- Read the newly created item via API B; record result, retries, and time until visible.
- Measure across consistency levels **supported by the account**, comparing impact.
- For Session, design session context/token forwarding or verify how sessions behave when switching instances. Note explicitly if the test does not propagate tokens.

Never use one fast read as proof that all requests in every region will always observe the latest write.

## 10. Security and Networking for the Lab

Even a synthetic-data lab should follow security practices close to production.

### 10.1. Identity and Access Control

- Separate **management-plane RBAC** (creating/modifying accounts) from **Cosmos DB data-plane access** (reading/writing items).
- For production Java apps, evaluate **Managed Identity** with identity-based auth and least-privilege Cosmos DB for NoSQL data-plane roles.
- Never share account keys across teams; restrict or disable local authentication where policy and tooling permit.
- Limit who can delete accounts or modify replication, failover, backups, and networking.
- Keep audit trails for sensitive changes using Entra ID and change approvals.

### 10.2. Private Networking and Regional Paths

If APIs must reach Cosmos DB over private networks, design **Private Endpoints, Private DNS Zones, VNet links, firewalls/NSGs, and routing** per supported topology. Running APIs in two regions does not mean a single Private Endpoint or DNS link in Region A suffices; verify private connectivity to the account from **each regional VNet/app**.

- DNS must resolve to Private Endpoint IPs along the intended lookup path; custom DNS/forwarders need matching rules.
- Keep TLS/hostname validation enabled with the standard account endpoint; never hard-code private IPs in client configs.
- Choose an SDK connection/routing mode compatible with your network rules and supported features.
- When a region or private endpoint fails, verify failover connectivity—not just Cosmos account health.
- Never leave public network access open indefinitely just to bypass a DNS issue in a test.

### 10.3. Data Protection and Tenant Access Control

The partition key `/tenantId` **is not a tenant security control by itself**. The API must authenticate users, derive tenant identity from trusted tokens, enforce per-tenant authorization, and **never trust an arbitrary `tenantId` passed by the client**. Otherwise, users could guess `id + tenantId` pairs and read other tenants' data.

For sensitive data, check encryption, key management, retention, auditing, and data residency rules. Enabling global replication without checking legal/residency constraints creates compliance risk.

## 11. Implementing Dual-Region APIs and Front Door Routing

Adding read regions in Cosmos DB does not automatically make an app a **global application**. You need at least two API deployments serving identical contracts, compatible schema/logic versions, and equivalent configuration.

### 11.1. Entry Point Design

With Azure Front Door, an example setup includes:

1. Two origins pointing to API A and API B endpoints, with HTTPS and health endpoints.
2. Health probes testing **real readiness** without causing side effects or knocking out all backends over a minor shared-dependency hiccup.
3. Routing rules, priority/weight, or latency-based routing per tier capabilities.
4. Proper TLS, WAF, custom domains, caching rules (if applicable), and header forwarding.
5. Telemetry on frontend responses, origin health, and traffic distribution.

Avoid overly deep health probes that mark a region down for a brief auxiliary glitch; conversely, a probe returning 200 when the API cannot reach Cosmos DB misleads routing. Distinguish **liveness, readiness, and end-to-end synthetic transactions**.

### 11.2. APIs Must Manage Retries and Timeouts

A typical request flows:

~~~text
Client -> Azure Front Door -> API Region A/B
       -> Cosmos DB SDK -> eligible write or read region
       -> Response -> Client
~~~

The application layer must enforce bounded timeouts, bounded retries, backoff/jitter, circuit breakers where appropriate, and write idempotency. In Cosmos DB, **429 is throttling**, whereas timeouts or regional endpoint errors may signal connectivity/SDK failover issues. Never treat all errors as infinitely retryable.

### 11.3. Observing Sessions When Users Switch Regions

Front Door can route consecutive requests from the same user to different API regions during failover or latency shifts. Under Session consistency, decide explicitly how session tokens are handled. Cookie affinity does not survive every failure mode, and an in-memory cache on API A does not update API B.

In the lab, test **write A → read A → read B** and compare results before and after swapping preferred-region order.

## 12. Drilling Failures in Region A or Region B

Design at least two separate scenarios. **Never trigger live failovers on production**; run drills only in authorized lab accounts with rollback and cleanup plans.

### 12.1. Scenario A: Only API Region A Fails

**Given:** Cosmos account is healthy in both regions; API A and API B are healthy; Front Door probes are active.

**When:** In staging, intentionally take API A out of rotation (e.g., disabling the test origin via an approved procedure).

**Then:** Front Door shifts new traffic to API B; reads/writes continue within Cosmos account capabilities and configured consistency.

Observe:

- Elapsed time from `T_impact` until user SLIs recover.
- Failed or timed-out requests during origin failover.
- Client p95/p99 latency from multiple locations.
- Session tokens/caching, in-flight requests, and idempotency behavior.
- Cosmos DB read/write RUs and status codes.

**Do not fail over the database** when only API A fails; changing multiple layers simultaneously obscures root causes and raises risk.

### 12.2. Scenario B: Cosmos DB Write Region Unavailable

In a **single-write** account with eligible regions and automatic failover enabled where appropriate, a write-region outage can trigger write-role promotion to another region per service behavior. This is distinct from Front Door API origin routing.

Steps in a **controlled environment**:

1. Snapshot region settings, failover priorities, consistency, write mode, networking, and replication state before testing.
2. Verify data sources, recovery point, and lab RTO/RPO targets; create synthetic items with independent IDs and ack timestamps.
3. Choose an **Azure-supported safe test method** with approval and stop conditions. For pure architectural reviews, use tabletop exercises or simulated SDK endpoint failures instead of forcing a live account failover.
4. Observe SDK diagnostics, errors, request routing, role/failover events, and write interruption/recovery times.
5. Once data service resumes, reconcile acknowledged IDs, duplicates, ambiguous commits, and update ordering.
6. Verify reads/writes from both API regions, monitoring, and remaining capacity.
7. Restore desired topology via a separate controlled procedure; check replication and permissions rather than forcing failback carelessly.

**Never promise RTO=0 or RPO=0** across all Cosmos DB configurations. Replication can be asynchronous depending on consistency and topology; understand failure modes and service guarantees, then measure against business rules. Seeing the SDK return HTTP 200 later does not by itself prove zero data loss.

### 12.3. Scenario C: Multi-Region Writes and Conflicts (Extension Design)

If the business chooses multi-write, model two APIs writing concurrently to the same `id` in the same partition from two regions with conflicting payloads.

~~~text
Region A: order-10001.status = "PAID"
Region B: order-10001.status = "CANCELLED"

Business requirements:
  - Cannot simultaneously be PAID and CANCELLED without an explicit rule.
  - Never issue double refunds or double charges.
  - Every resolution needs an audit trail and authoritative state.
~~~

Conflict policies like **Last Writer Wins (LWW)** or built-in defaults may violate business logic: the latest wall-clock timestamp does not prove a payment is valid. An ordering system should evaluate **state machines, versioning, idempotency, append-only/event patterns, and scoped transactions** instead of trusting automatic conflict policies blindly.

The lab **does not require enabling live multi-write**. Designing the scenario, correctness criteria, and extension tests suffices.

## 13. Measuring Outcomes with Reconcilable Evidence

A capstone report must include SLIs and metrics across three layers: user, API/ingress, and Cosmos DB.

### 13.1. Telemetry Collection Table

| Layer | Metrics / evidence | Meaning |
| --- | --- | --- |
| Front Door | Request success, origin health, latency, route distribution | Are users reaching healthy origins in the right region? |
| API | 5xx, p95/p99, timeouts, retries, thread/connection metrics | Did the application truly recover? |
| Cosmos DB | Request Units, normalized RU consumption, 429 throttled requests | Are sizing and partitioning sufficient? |
| Cosmos DB | End-to-end/client latency, service latency where available | Separates RTT/SDK retries from backend service time |
| Cosmos DB | Region availability, failover events, diagnostics | When did routing or failover change? |
| Data | Order IDs, ack timestamps, versions, observed reads | Measures staleness/missing/duplicates and correctness |
| SRE | `T_impact`, `T_detected`, `T_recovered` | Compares against RTO/SLO |
| Cost | Regional throughput, storage, networking, monitoring | Controls budget when adding replicas |

**RU/s is provisioned capacity; RU is per-operation cost.** Never infer latency or reliability from total RU consumption alone; evaluate workload distribution, partitioning, and topology.

### 13.2. Dual-Region Measurement Matrix

| Test | API A | API B | What to conclude |
| --- | --- | --- | --- |
| Point read same tenant | Record p95 and RU | Record p95 and RU | Are reads served closer to users? |
| Create item | Record latency and RU | Record latency and RU | How does the primary write region affect write latency? |
| Write A → read B | Record write success | Record time until item visible | Are session/consistency semantics handled properly? |
| Peak load | 429, p95, errors | 429, p95, errors | Are throughput, hotspots, and retries healthy? |
| API A unavailable | Stops receiving new traffic | Meets SLI in window | Does Front Door failover work? |
| Database write-region disruption | Errors and timeouts | Errors and timeouts | Does data failover meet targets and preserve integrity? |

### 13.3. Hypothetical Results Example

Suppose a defined low-load staging test yields:

~~~text
API Region A, read p95:                 35 ms
API Region B, read p95:                 42 ms
API Region A, write p95:                70 ms
API Region B, write p95:               145 ms
API failover observed disruption:       18 s
Cosmos DB throttling (429):             0.4% requests
Observed stale read without shared token: observed in cases
Total test period:                       15 minutes
~~~

These are **not guaranteed Azure numbers**. Record load rate, load generator, client location, consistency, SDK config, partition key, and statistical confidence. If failover testing altered data or permissions, note the exact scope and timing.

**Never conclude production availability readiness from a 15-minute low-load test.** Add peak, burst, dependency failures, rollback verification, consistency checks, and reconciled data evidence.

## 14. Cost Optimization for Multi-Region Architectures

Global distribution improves latency and resilience while increasing costs across several layers:

| Component | Why cost increases | How to evaluate |
| --- | --- | --- |
| Cosmos DB throughput | RU/s and replicas scaled across multiple regions | Monitor per-region throughput, utilization, and 429s |
| Cosmos DB storage | Data and indexes replicated per account topology | Review storage size, TTL, indexing policy, region count |
| Multi-region writes | Write/distribution pricing/terms can differ | Check pricing sheets and configuration rules |
| Dual-region apps | Compute, autoscale minimums, networking, ingress | N-1 capacity, active hours, and traffic |
| Azure Front Door / WAF | Traffic routing, requests, bandwidth, security features | Choose appropriate tier and estimate actual usage |
| Network egress | Cross-region, Internet, or intermediate transfer fees | Map data flows and region placement |
| Monitoring | Logs, traces, and retention in two regions | Tune sampling/retention while preserving audit needs |
| DR/backups | Continuous backup/restore and drill execution | Match RTO/RPO, retention, and test costs |

**This lesson states no fixed prices**, as rates vary by region, throughput, configuration, agreements, terms, and time. Before provisioning, check the Azure Pricing Calculator/Cost Management and applicable limits/options.

### 14.1. Cost per Successful Transaction

Suppose the entire workload (Cosmos DB, APIs, Front Door, networking, logs, and shared costs) costs **2,400 USD/month** and processes **120,000 valid transactions**:

~~~text
Cost per successful transaction
  = 2,400 / 120,000
  = 0.02 USD / transaction
~~~

If adding a region raises total cost to 3,000 USD while enabling 180,000 valid transactions:

~~~text
3,000 / 180,000 ≈ 0.0167 USD / transaction
~~~

Total spend rose while unit cost fell. Decisions must still weigh SLOs, data residency, RTO/RPO, and operational risk—never optimize on a single metric alone.

### 14.2. FinOps Guardrails for the Lab

- Set budgets and alerts at the test scope; **budgets do not stop resources automatically**.
- Start with modest throughput matching features; avoid provisioning production peak defaults.
- Time-box multi-region accounts and apps with a named cleanup owner.
- Measure RUs per operation and tune partition keys/queries before raising RU/s.
- Track resources that still bill when apps are stopped—especially provisioned throughput/replicas and monitoring.
- Never strip backups, security telemetry, or required reliability just to cut production bills.

## 15. Step-by-Step Lab Workflow

A sequential workflow for learners to execute and document evidence:

### Step 1 — Prepare Design

Create a design brief covering: SLO/RTO/RPO and data residency rules, two target regions, API endpoint list, account write mode, consistency, `/tenantId`, target RU/s, budget, and owner.

**Deliverable:** diagram, single-write vs. multi-write decision, and risk table.

### Step 2 — Provision Test Resources

Create the resource group, Cosmos DB for NoSQL account, two regions, `commerce` database, and `orders` container. Verify replication and read/write regions in Portal/CLI. Enable monitoring/diagnostics and save *sanitized* configuration snapshots.

**Deliverable:** account configuration, region list, consistency, container partition path.

### Step 3 — Run the Java SDK

Set the endpoint and safe test credentials in environment variables, specify the SDK version, run `CosmosGlobalLab`, and record create/read request charges. Verify the item appears in Data Explorer under logical partition `tenant-lab`.

**Deliverable:** one synthetic item, read output, RU/operation.

### Step 4 — Deploy Dual-Region APIs

Deploy two API instances sharing the same contract, differing only in preferred regions and telemetry tags. Add a readiness health endpoint. Configure Front Door or safe HTTP routing simulation in test.

**Deliverable:** two API endpoints, routing table, and health checks.

### Step 5 — Test Consistency

Create an order via API A; immediately read via API A and B, test Session consistency, document your session token strategy, observed delay, and read results. When stale reads occur, explain why rather than blaming the SDK.

**Deliverable:** write/read experiment log and consistency decision record.

### Step 6 — Load and Partitioning Test

Generate point reads/creates at test load; measure p95, RU/operation, 429s, and retries. Test skewed tenant traffic (e.g., 80% of requests to one tenant) in test to observe hotspots without hitting production.

**Deliverable:** time-series charts, hotspot analysis, and tuning plan.

### Step 7 — Drill Application-Layer Failure

Disable **origin API A** in the test environment via approved steps; observe Front Door shifting traffic to API B and convergence delay. Do not alter the database account at the same time.

**Deliverable:** `T_impact`/`T_recovered` and application failover evidence.

### Step 8 — Analyze Data Failover

Run a tabletop or service-supported test failover on the lab account, focusing on write region promotion, sessions, acknowledged items, and connectivity from both APIs. Define stop conditions to prevent unintended data loss.

**Deliverable:** runbook, observed RTO/RPO (if tested live) or explicit list of unverified assumptions.

### Step 9 — Cost Assessment and Cleanup

Calculate multi-region costs from actual configuration and compare against unit-cost targets. Delete resources **strictly inside the lab-owned test resource group** per approved steps; confirm no real data or external dependencies remain. For shared resources, clean up individual objects rather than deleting the whole group.

**Deliverable:** budget report, cost/transaction, cleanup checklist.

## 16. Troubleshooting by Symptom

| Symptom | Possible cause | Check / resolution |
| --- | --- | --- |
| HTTP 404 on item read | Wrong `id`, `tenantId`, DB/container, or not yet replicated/visible | Verify partition key and session state; inspect item in Data Explorer |
| HTTP 409 on create | Same `id` already exists in that logical partition | Check idempotency key, payload, and transaction history |
| Frequent HTTP 429 | Insufficient RU/s, expensive queries, hot logical partition | Measure RUs, normalized consumption, 429/partition, autoscale/indexes |
| HTTP 403 | Credential/RBAC, firewall, network rules, data-plane role | Inspect error substatus, principal, and network path |
| Immediate read in Region B misses new write | Consistency/session context, replication, and routing | Check session token, consistency level, preferred regions, and timeline |
| Writes from API B slower than A | Single-write mode, network distance to write region | Measure RTT, client diagnostics; evaluate if business needs multi-write |
| Front Door keeps routing to failed API | Misconfigured probe/route/origin or convergence lag | Check probe, host header, origin status, logs |
| SDK cannot connect from VNet B | Private DNS/Endpoint, routes, firewall/TLS, connection mode | Test DNS/TCP/TLS directly from VNet B; check account networking |
| Multi-write causes data conflicts | Concurrent writes to same item, unsuitable conflict policy | Design state machine, ETags, idempotency, and conflict handling |
| Raising RU/s does not lower latency | Network RTT, retries, query logic, app bottleneck | Separate client/server latency, profile queries/partitions, p95 |
| Costs higher than expected | Added regions, RU/s, replica storage, Front Door/logs | Check Cost Analysis, region count, and budgets |
| Missing/duplicate items after failover | Replication lag, ambiguous in-flight writes, retries | Reconcile by ID/ack and data runbook, not just HTTP 200 |

## 17. Capstone Report and Grading Rubric

### 17.1. Team Report Template

~~~markdown
# Cosmos DB Global Distribution Lab — <exercise-id>

## Architecture and Objectives
- Workload, owner, regions, account read/write mode:
- SLO, RTO/RPO, data residency:
- Front Door → API A/B → Cosmos DB diagram:
- Partition key, document schema, consistency:

## Functional Results
- Item create/read via Java SDK:
- Idempotency and 409 handling:
- Read-after-write across API A/B:
- Session token / consistency notes:

## Performance Results
| Test | Region/client | p95 | RU/op | HTTP 429 | Notes |
| --- | --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... | ... |

## Resilience
- API region failure injection:
- Database write-region scenario:
- T_impact, T_recovered, data evidence:

## Security and Cost
- RBAC/credential handling, network isolation:
- Cost drivers, budget, and unit cost:

## Recommendations
- Residual risks and trade-offs:
- Action items, owners, acceptance tests:
- Verified cleanup:
~~~

### 17.2. Acceptance Rubric

| Criterion | Meets bar when |
| --- | --- |
| **Proper scope** | Distinguishes regional APIs, Cosmos DB account/replicas, entry point, and dependencies |
| **Partitioning** | Explains `/tenantId` choice, hotspot risks, and mitigations |
| **Consistency** | Justifies choice by business need and tests cross-region read-after-write |
| **Working basic CRUD** | Creates and reads items via SDK; measures request charge |
| **Failover clarity** | Separates origin failover from database write-region failover |
| **Data safety** | Uses synthetic data only, zero secrets in report, idempotency addressed |
| **Performance** | Measures p95, 429, RU/operation, and analyzes behavior under load |
| **Cost** | Includes budget, per-region cost drivers, and unit cost |
| **Verification** | Provides timeline, evidence, and clear pass/fail criteria |
| **Operations** | Includes runbooks, rollback/cleanup, owners, and next steps |

## 18. Misconceptions to Avoid

**"Adding two regions automatically makes the app global."** False. If the API runs in only one region or Front Door does not shift traffic on failure, users still suffer outages.

**"Cosmos DB reads always return the newest data everywhere."** Freshness depends on consistency, session context, account configuration, and region. Propagating session tokens across API instances is an app-level design requirement to test.

**"The partition key chooses which region stores data."** False. The partition key governs logical distribution; Cosmos DB region replication is configured separately.

**"Just raising RU/s eliminates all 429 errors."** A hot partition, cross-partition scans, or poorly indexed queries can still throttle and inflate bills.

**"Enabling multi-write has no conflict risk."** False. Multi-region writes require conflict resolution and business-correctness rules; LWW does not fit every domain.

**"Automatic failover means zero downtime and zero data loss."** Never generalize this across all topologies and consistency modes; measure SDK/client errors, RTO/RPO, and reconcile transactions.

**"A 100% budget alert automatically stops Cosmos DB."** Budgets notify; they are not hard spending caps. Govern throughput, regions, active resources, and cleanup explicitly.

**"Cosmos DB replicas eliminate the need for backups."** Replicas faithfully replicate logic bugs and accidental deletes; backup/restore and data recovery remain separate safeguards.

## 19. Summary

A strong globally distributed application takes more than **Cosmos DB in multiple regions**. It requires multi-region API ingress, partition keys matched to queries, business-appropriate consistency, identity and data protection, safe 429/retry handling, separate failover plans for API and database layers, plus monitoring and cost governance.

This lab connected foundational Azure pieces: **subscriptions/resource groups** for isolation, **Entra ID/RBAC and private networking** for access security, **compute/Front Door** for multi-region delivery, **Cosmos DB for NoSQL** for data distribution, **Azure Monitor** for SLI verification, and **Cost Management** for unit economics. The most reliable deliverable is a **repeatable set of measurements and evidence**, not merely seeing resources turn `Running`.
