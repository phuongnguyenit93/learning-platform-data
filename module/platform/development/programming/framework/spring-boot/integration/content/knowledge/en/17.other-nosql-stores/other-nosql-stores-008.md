# Couchbase Cluster, Bucket, Scope, and Collection

## 1. Why understand Couchbase's data hierarchy?

In a Spring Boot application integrating multiple systems, Couchbase can store order state, integration configs, lookup data, or event-processing markers as JSON documents. Before calling read or write APIs, the application must determine **which cluster to connect to, which bucket, which scope, and which collection to target**. Selecting the wrong level can cause the app to read the wrong dataset, hit authorization errors, or miss a document even though the key exists elsewhere.

For instance, an order-processing service stores data at the logical address:

`commerce.sales.orders`

Here `commerce` is the bucket, `sales` is the scope, and `orders` is the collection. A document carries ID `order::tenant-42::ORD-10021`. The cluster is the Couchbase system hosting that entire hierarchy and serving data access services.

After this lesson, you should be able to distinguish the roles of all four levels, design a clean namespace, route operations from Spring Boot to the right collection, and understand how indexes, consistency, permissions, and fault tolerance come into play.

## 2. Four levels: cluster → bucket → scope → collection

~~~text
Couchbase Cluster
├── Node A: Data Service, Query Service
├── Node B: Data Service, Index Service
└── Node C: Data Service
    (nodes jointly serving cluster data and services)

Bucket: commerce
├── Scope: sales
│   ├── Collection: orders
│   │   ├── ID: order::tenant-42::ORD-10021
│   │   └── ID: order::tenant-42::ORD-10022
│   └── Collection: payment_receipts
└── Scope: integration
    ├── Collection: webhook_inbox
    └── Collection: partner_settings
~~~

The diagram separates two perspectives: **cluster/node** represents infrastructure and services; **bucket/scope/collection** represents logical data organization. One node does not “own” an entire collection alone; Couchbase distributes a bucket's data partitions across Data Service nodes.

| Level | Primary role | Design decisions |
| --- | --- | --- |
| **Cluster** | Collection of Couchbase nodes, service layout, scaling/availability | Node count, Data/Query/Index service placement, TLS, HA, monitoring |
| **Bucket** | Storage space with resource quotas, durability, and operational policies | Separating data by operational needs, capacity, backup, and retention |
| **Scope** | Logical namespace grouping related collections | Grouping by business domain or application; organizing access control |
| **Collection** | Set of documents with IDs and JSON bodies; direct KV target and index target | Categorizing documents by purpose, indexes, permissions, and TTL |
| **Document** | Single JSON record identified by document ID inside a collection | JSON shape, key structure, versioning, update rules |

### Cluster and services

`Cluster` is the deployment and administration unit. Applications connect via the Couchbase SDK using `couchbase://...` or `couchbases://...` (TLS), authenticate credentials, and obtain bucket/scope/collection handles. One SDK `Cluster` object can access multiple buckets if authorized.

Couchbase separates specialized services: **Data Service** handles key-value (KV) access, **Query Service** executes SQL++, and **Index Service** maintains secondary indexes, among other services depending on deployment. These services can be allocated across distinct nodes. Not every access goes through Query Service: `collection.get(id)` performs a direct KV lookup against Data Service.

Bucket data is split into virtual partitions (vBuckets) distributed across Data Service nodes. Replicas and failover improve fault tolerance per configuration, yet **in-cluster replicas do not replace independent backups**. Recovering from accidental deletions, application bugs, or cluster-wide loss still requires a backup/restore strategy.

### Bucket: operational boundary of data

Buckets hold key storage settings such as bucket type, resource allocation, replica count, expiration policies, and backup scope depending on edition/deployment. One bucket contains many scopes; each scope contains many collections.

Do not create a separate bucket for every entity type out of relational table habits. If `orders` and `payment_receipts` share operational requirements, they can live in two collections inside the same `commerce` bucket. Conversely, short-TTL cache entries and long-lived business records may belong in separate buckets or storage configurations.

### Scope: domain-aligned namespace

Scopes group related collections. For example, `sales` holds `orders` and `payment_receipts`, while `integration` holds `webhook_inbox` and `partner_settings`. Two scopes can each contain a collection named `events` without keyspace collision.

Scopes help structure RBAC and namespaces, yet **a scope is not an independent cluster**, does not allocate isolated physical resources, and does not replace application-layer tenant authorization. For multi-tenancy, evaluate scope/collection limits and operational overhead before creating one scope per tenant.

### Collection: direct target of documents

Collections are where KV APIs operate. **Document IDs only need to be unique within a collection**, so `order::42` can exist simultaneously in two different collections as completely independent documents.

SQL++ indexes target collection keyspaces; ACLs can be scoped at bucket, scope, or collection granularity per role. Expiration (TTL) can be set per document or collection depending on server capabilities and needs. Always choose TTL intentionally: letting order documents expire automatically due to a misconfigured cache setting causes silent data loss.

In Couchbase versions supporting collections, buckets include a default `_default` scope and `_default` collection for backward compatibility. Failing to specify scope and collection explicitly can easily write documents into `_default._default` while queries read `sales.orders`.

## 3. Designing namespaces for Spring Boot integration

Suppose we have three requirements: storing orders, deduplicating partner webhooks, and managing per-partner configurations.

| Data | Proposed keyspace | Example ID | Rationale |
| --- | --- | --- | --- |
| Orders | `commerce.sales.orders` | `order::tenant-42::ORD-10021` | Business records persisted and queried by status |
| Received webhook events | `commerce.integration.webhook_inbox` | `webhook::partner-a::evt-853` | Event key for duplicate detection; TTL matches replay window |
| Partner configuration | `commerce.integration.partner_settings` | `partner::tenant-42::partner-a` | Separates config write access from order write access |

A document inside `orders`:

~~~json
{
  "tenantId": "tenant-42",
  "orderId": "ORD-10021",
  "status": "PAID",
  "createdAt": "2026-11-21T03:20:00Z"
}
~~~

The ID lives in **document metadata**, so an `id` field inside the JSON body is optional. You may store an ID field inside JSON if queries or payloads need it, provided synchronization with the document ID is clearly defined. Including `tenantId` in the key aids identification, yet **does not enforce authorization**: every operation must validate tenant identity from the user context and filter queries accordingly.

Design principles:

1. Pick buckets by operational profile, scopes by functional boundary, and collections by document group and index/access policy.
2. Design deterministic document IDs with normalization rules and unambiguous delimiters. Never generate random IDs for events needing idempotency on an external event ID.
3. Avoid dynamically creating scopes or collections per HTTP request. Provision namespaces and indexes via controlled deployment/migration pipelines.
4. Enforce least privilege for runtime accounts; an order-writing service rarely needs permission to create buckets, scopes, collections, or indexes.

## 4. Creating scopes, collections, and indexes

Administrators or deployment pipelines create the `commerce` bucket first using the appropriate management tool. Then, with administrative privileges, execute SQL++ DDL:

~~~sql
CREATE SCOPE `commerce`.`sales`;
CREATE SCOPE `commerce`.`integration`;

CREATE COLLECTION `commerce`.`sales`.`orders`;
CREATE COLLECTION `commerce`.`integration`.`webhook_inbox`;
CREATE COLLECTION `commerce`.`integration`.`partner_settings`;
~~~

This is **provisioning**, not logic to run inside Spring Boot HTTP request handlers. For repeatable migrations, check existence or use idempotent syntax supported by your server version. After structural changes, verify the application account holds the right permissions on the new keyspaces.

KV lookups by ID need no secondary index. However, filtering orders by tenant, status, and timestamp requires an appropriate index:

~~~sql
CREATE INDEX `idx_orders_tenant_status_created`
ON `commerce`.`sales`.`orders`(tenantId, status, createdAt);

SELECT META(o).id AS documentId,
       o.orderId, o.status, o.createdAt
FROM `commerce`.`sales`.`orders` AS o
WHERE o.tenantId = $tenantId
  AND o.status = $status
ORDER BY o.createdAt DESC
LIMIT 50;
~~~

Here `$tenantId` and `$status` are SQL++ parameters—**never concatenate user input strings** into query text. Query Service relies on indexes built by Index Service; in real systems, inspect query plans, statistics, and index selectivity. Creating a primary index just “to make every query run” is rarely optimal in production. Indexes may also require build time before becoming online for queries.

## 5. Connecting from Spring Boot to the right collection

Example using Spring Boot 3.x, Java 17+, and Couchbase Java SDK 3.x via the starter:

~~~kotlin
// build.gradle.kts
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-couchbase")
}
~~~

Connection configuration in `application.yml`:

~~~yaml
spring:
  couchbase:
    connection-string: ${COUCHBASE_CONNECTION_STRING}
    username: ${COUCHBASE_USERNAME}
    password: ${COUCHBASE_PASSWORD}
  data:
    couchbase:
      bucket-name: commerce
~~~

Placeholders `${COUCHBASE_CONNECTION_STRING}`, `${COUCHBASE_USERNAME}`, and `${COUCHBASE_PASSWORD}` pull values from environment variables. Never store passwords directly in Git. Use `couchbases://...` with proper certificate trust configuration when TLS is required.

`spring.data.couchbase.bucket-name` only chooses the **default bucket** for Spring Data Couchbase. It does not automatically target scope `sales` or collection `orders` across SDK calls. When using KV APIs, specify them explicitly:

~~~java
// CouchbaseCollectionConfig.java
import com.couchbase.client.java.Bucket;
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.Collection;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CouchbaseCollectionConfig {

    @Bean("ordersCollection")
    public Collection ordersCollection(Cluster cluster) {
        Bucket bucket = cluster.bucket("commerce");
        bucket.waitUntilReady(Duration.ofSeconds(15));
        return bucket.scope("sales").collection("orders");
    }
}
~~~

`Cluster` is configured by Spring Boot; `Bucket`, `Scope`, and `Collection` are lightweight SDK handles pointing to targets—**not loading all documents into memory**. Waiting for the bucket at startup catches connectivity issues early, yet runtime calls still need timeouts, health checks, and error handling.

Adapter reading and writing orders in the exact collection:

~~~java
// CouchbaseOrderAdapter.java
import com.couchbase.client.core.error.DocumentNotFoundException;
import com.couchbase.client.core.msg.kv.DurabilityLevel;
import com.couchbase.client.java.Collection;
import com.couchbase.client.java.kv.InsertOptions;
import java.util.Optional;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Repository;

@Repository
public class CouchbaseOrderAdapter {
    private final Collection orders;

    public CouchbaseOrderAdapter(
            @Qualifier("ordersCollection") Collection orders) {
        this.orders = orders;
    }

    public void create(OrderDocument order) {
        String key = key(order.tenantId(), order.orderId());
        orders.insert(
                key,
                order,
                InsertOptions.insertOptions()
                        .durability(DurabilityLevel.MAJORITY));
    }

    public Optional<OrderDocument> findById(
            String tenantId, String orderId) {
        try {
            return Optional.of(
                    orders.get(key(tenantId, orderId))
                          .contentAs(OrderDocument.class));
        } catch (DocumentNotFoundException exception) {
            return Optional.empty();
        }
    }

    private String key(String tenantId, String orderId) {
        // In real apps, validate and normalize key components.
        return "order::" + tenantId + "::" + orderId;
    }
}

record OrderDocument(
        String tenantId,
        String orderId,
        String status,
        String createdAt) {}
~~~

This illustrates **KV access by document ID**. `insert` creates only if the key is absent; if the key already exists, the SDK throws `DocumentExistsException`. That suits create-once flows better than `upsert`, which silently overwrites. `DurabilityLevel.MAJORITY` requests stronger replication confirmation per cluster setup, trading higher latency and failure risk if too few replicas are available. Pick durability according to business needs and deployment topology.

When using Spring Data Couchbase's `CouchbaseRepository` instead of the direct SDK, annotate `@Document` and configure scope/collection mapping per your Spring Data version. Verify the repository truly targets `commerce.sales.orders` rather than falling into `_default._default`. Never assume target routing from Java class names alone.

## 6. KV, SQL++, and consistency

Two common read paths carry different costs and behavior:

| Operation | Path | Index needed | Notes |
| --- | --- | --- | --- |
| `collection.get(documentId)` | KV / Data Service | No secondary index needed | Optimal when ID and collection are known |
| `collection.insert(id, json)` | KV / Data Service | No secondary index needed | Fails if ID exists; good for create-only / deduplication |
| `collection.replace(id, json, options)` | KV / Data Service | No secondary index needed | Accepts CAS to prevent overwriting newer updates |
| `cluster.query("SELECT ...")` | Query Service + usually Index Service | Usually needs a matching secondary index | Queries multiple documents by attributes and predicates |

Java SDK executing parameterized SQL++:

~~~java
import com.couchbase.client.java.Cluster;
import com.couchbase.client.java.json.JsonObject;
import com.couchbase.client.java.query.QueryOptions;
import com.couchbase.client.java.query.QueryResult;
import com.couchbase.client.java.query.QueryScanConsistency;
import org.springframework.stereotype.Repository;

@Repository
public class OrderQueryReader {
    private final Cluster cluster;

    public OrderQueryReader(Cluster cluster) {
        this.cluster = cluster;
    }

    public QueryResult findPaidOrders(String tenantId) {
        String statement = """
            SELECT META(o).id AS documentId, o.orderId, o.status
            FROM `commerce`.`sales`.`orders` AS o
            WHERE o.tenantId = $tenantId AND o.status = $status
            """;

        return cluster.query(
                statement,
                QueryOptions.queryOptions()
                        .parameters(JsonObject.create()
                                .put("tenantId", tenantId)
                                .put("status", "PAID"))
                        .scanConsistency(QueryScanConsistency.REQUEST_PLUS));
    }
}
~~~

SQL++ queries rely on indexes updated asynchronously. Consequently, immediately after writing a document via KV, an index query at default scan consistency may miss the recent change. `REQUEST_PLUS` instructs Query Service to wait for indexes to catch up to mutations prior to the query, at the cost of higher latency—without turning the entire app into a linearizable distributed transaction system. When the document ID is known, KV `get` is usually the better path for read-your-own-writes.

For concurrent updates, the SDK returns a **CAS** (compare-and-swap) token when reading a document. Passing that CAS into `replace` enforces “update only if the document has not changed since read.” On CAS mismatch, handle conflicts per business rules; `upsert` alone does not prevent lost updates.

## 7. Integration failures, permissions, and operations

| Symptom | Causes to check | Action |
| --- | --- | --- |
| KV reports document not found though visible in UI | Wrong bucket/scope/collection, wrong ID, or document expired | Log keyspace and safe ID; check TTL and key construction rules |
| Cannot open bucket/collection | Not provisioned, typo, or missing permissions | Verify namespace, service account, and RBAC roles |
| SQL++ fails while KV `get` works | Missing Query/Index Service, missing/building index, or Query RBAC differs from KV | Check cluster services, indexes, query plan, and roles |
| Query misses newly written document | Secondary index update lag | Use KV `get` when ID is known, or select suitable scan consistency |
| Retries produce duplicate side effects | Timeout left commit ambiguous; non-idempotent flow | Use deterministic IDs, `insert`/dedup checks, handle ambiguous outcomes, bound retries |
| Concurrent update race on same document | Multiple writers overwriting via `upsert` | Use CAS, state transition modeling, and conflict policy |
| Documents vanish over time | Bucket/collection/document TTL or purge policy | Align expiration settings with retention requirements |

### Permissions

Grant runtime app accounts read/write privileges strictly on required collections; reserve namespace and index creation for separate deployment accounts. Remember that **KV Data Reader/Writer** privileges do not automatically grant **Query** permissions, and permissions on one collection do not carry over to another. When logging errors, omit passwords, personal data, and full sensitive documents.

### Retries, idempotency, and transactions

In webhook or broker consumers, a document ID can serve as a deduplication marker—for instance `webhook::partner-a::evt-853` in `integration.webhook_inbox`. Using `insert` detects duplicate deliveries, yet **recording the marker and updating the order are two separate writes**; if atomicity across multiple documents is required, evaluate Couchbase transactions or explicit state/compensation designs. Couchbase transactions still do not span Kafka/RabbitMQ commits or external HTTP calls. Therefore, design retries, acknowledgments, inbox/outbox patterns, and recovery at system boundaries.

A `TimeoutException` or network failure never proves a write did not apply. Before retrying side-effecting operations, check whether the operation is idempotent; when `insert` encounters an already-existing document after a retry, inspect its content or business state rather than blindly failing.

### Testing and observability

Run integration tests against a compatible Couchbase cluster with buckets, scopes, collections, and indexes provisioned beforehand. Key cases include: reading/writing the exact keyspace; missing collections; missing permissions; duplicate IDs; read-after-write; queries without indexes; concurrent update races; timeouts; and webhook replays. Unit tests can mock adapters, yet never replace real Couchbase tests for queries, indexes, and ACLs.

In production, monitor KV and SQL++ latencies, timeouts, connection counts, node/service status, index state/lag, replica lag, memory/disk usage, authorization errors, and document expiration rates. Tune timeouts and retries per API characteristics rather than applying infinite retries or one-size-fits-all policies.

## 8. Design scenario and self-check questions

**Scenario:** A Spring Boot app writes `order::tenant-42::ORD-10021` into `commerce.sales.orders`, then a SQL++ listing endpoint fails to show the new order. Another query against `commerce._default._default` also returns nothing.

Analysis steps:

1. Verify the adapter targets `bucket("commerce").scope("sales").collection("orders")` with the exact document ID; check existence via KV `get` first.
2. If KV finds the document, check whether the SQL++ query targets `commerce.sales.orders` and whether the collection's secondary index is built and online.
3. Check the query's scan consistency and Index Service lag; select `REQUEST_PLUS` if immediate freshness is required and the latency trade-off is acceptable.
4. If the issue only affects another tenant, inspect key construction, `tenantId` filter predicates, and access controls—never remove the tenant filter as a “fix.”

Self-check: (a) Can two collections hold the same document ID? **Yes**, because IDs are unique per collection. (b) Does a scope allocate isolated physical resources like a bucket? **No**. (c) Does KV `get` need a SQL++ index? **No**. (d) Why is `upsert` not always suitable for webhook deduplication? **Because it can overwrite an existing ID**, so conditional create and idempotency checks are needed. (e) Why separate deployment accounts from runtime application accounts? **To uphold least privilege for runtime operations**.

When deploying Couchbase in Spring Boot, always trace the full path **cluster → bucket → scope → collection → document ID**, then match access style (KV vs. SQL++), permissions, and consistency guarantees to your integration flow. Explicit keyspace addressing prevents misrouted data and supports solid deduplication, retry, and monitoring designs.
