# Memorystore and Caching Tool Choices

A Java `catalog-api` service on Cloud Run reads products from Cloud SQL PostgreSQL. When a sales campaign multiplies traffic severalfold, most requests read only the same few thousand products. If every request hits the database, latency, connection count, and cost rise even when the data has not changed. A **cache** temporarily stores computed or fetched results to reduce load on the primary datastore.

On Google Cloud, you must pick the right **cache placement**: in-process application memory (Caffeine), a shared cache via **Memorystore for Valkey/Redis**, or edge HTTP caching (**Cloud CDN**). **Memorystore** is a high-speed managed in-memory data service, yet it does not guarantee cache freshness by itself, solve order transactions, or act as a backup replacing the database.

This lesson belongs to the **Bigtable and Memorystore** chapter of the `CLOUD_PROVIDERS_GCP` module: spanning projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, and databases, learners need to choose services, secure resources, release safely, and monitor reliability and cost. Examples use Java 21, Redis-compatible Valkey, and an in-memory simulated source to avoid touching production.

## Learning Objectives

After this lesson, you will be able to:

1. Distinguish **in-process L1** caches, **shared L2** caches, **HTTP/CDN** caches, and the system of record.
2. Choose among Memorystore for **Valkey**, **Redis Cluster**, **Redis**, and how to handle legacy Memcached systems.
3. Explain **cache-aside**, hit/miss, TTL, eviction, invalidation, and consistency.
4. Write a Java example using **Lettuce** with cache-aside, TTL, post-update cache deletion, and fallback on cache failure.
5. Recognize **cache stampedes**, hot keys, sensitive data, connection failures, and failover.
6. Design private networking, IAM/TLS, and clients suited to cluster vs. non-cluster modes.
7. Measure hit ratio, latency, memory, and cost, and determine whether caching is warranted.

## 1. Where Does Caching Sit in the Architecture?

~~~mermaid
flowchart LR
    U["Web/mobile client"] --> CDN["Cloud CDN<br/>HTTP responses/assets"]
    CDN --> API["catalog-api<br/>Cloud Run/GKE"]
    API --> L1["L1: Caffeine<br/>per process"]
    L1 -. "miss" .-> L2["L2: Memorystore<br/>Valkey/Redis"]
    L2 -. "miss" .-> DB[("Cloud SQL/Firestore/Bigtable<br/>system of record")]
    DB -->|"fill cache"| L2
~~~

| Layer | Shared across replicas? | Best suited for | Limitations |
| --- | --- | --- | --- |
| **In-process**: Caffeine, TTL Map | **No** | Ultra-hot, small data tolerating a few seconds of staleness | Each Pod/instance keeps its own copy; lost on restart |
| **Distributed**: Memorystore | **Yes**, among authorized connected clients | Catalogs, feature flags, query results, conditional rate-limit counters | Adds a network hop, memory cost, and stale-data risk |
| **HTTP edge**: Cloud CDN | Shared across edge cache locations | Images, CSS/JS, cacheable HTTP pages/responses | Unsuitable for private data if cache keys/headers are misconfigured |
| **System of record**: Cloud SQL/Firestore/Bigtable | Per DB semantics | Inventory, orders, payments, durable data | Usually slower/costlier than a cache hit |

**Principle:** cache only data **that can be regenerated or lost without breaking business correctness**. If the cache starts empty after a restart, the application must have a safe path back to the source of truth to recover.

## 2. What Memorystore Options Are Available?

Google Cloud currently offers four Memorystore product lines. **Valkey** is the primary candidate to evaluate for new systems needing a Redis-compatible cache with shard-based scaling.

| Service | Architecture | When it fits | Pitfalls to avoid |
| --- | --- | --- | --- |
| **Memorystore for Valkey** | Supports **Cluster Mode Enabled** (multiple shards) and **Disabled** (single shard) | New caches; choosing between single-shard and scale-out; configurable IAM authentication/TLS | Mode is chosen at instance creation and cannot be switched directly in place |
| **Memorystore for Redis Cluster** | Multi-shard Redis cluster with optional replicas | Workloads already relying on Redis Cluster semantics needing horizontal scaling | Client must support cluster topology and `MOVED` redirections |
| **Memorystore for Redis** | Single primary, **Basic** or **Standard** tier | Existing standalone Redis apps whose size/throughput fits | **Basic has no HA**; Standard adds replication and automatic failover; cannot switch Basic ↔ Standard in place |
| **Memorystore for Memcached** | Managed Memcached, simple key/value | **Mainly sustaining legacy workloads during migration** | **Deprecated**; not recommended for new deployments |

**Memcached lifecycle milestones (as of Nov 19, 2026):** starting **Jan 20, 2026**, it is no longer a recommended service; after **Feb 1, 2027**, new projects that never had an instance cannot create one; **Jan 31, 2029** is the end-of-service date. Google recommends migrating to **Memorystore for Valkey**. During migration, test client compatibility, key types, eviction, TTL, and operations; **never assume every Memcached command translates identically to Valkey**.

### 2.1. When Do You Not Need Memorystore?

- Cache holds only a few hundred records, each Cloud Run instance reads fast, and invalidation is loose: consider **Caffeine with a short TTL**.
- Data consists of public responses/static assets from Cloud Storage or HTTP backends: consider **Cloud CDN**, `Cache-Control`, and proper cache keys.
- Need ACID transactions or non-negative inventory invariants: use **Cloud SQL, Spanner, or Firestore transactions** as the source of truth.
- Need massive, **durable** key-value/time-series storage: evaluate **Bigtable**; Bigtable is a database, **not a drop-in in-memory cache replacement for Valkey**.

## 3. Cluster Mode, Replication, and Durability

For **Memorystore for Valkey**:

- **Cluster Mode Enabled**: the keyspace is partitioned into hash slots for horizontal scaling across shards; use a **cluster-aware client**. Multi-key commands, scripts, or transactions generally require keys to map to the **same hash slot**.
- **Cluster Mode Disabled**: single shard, simpler for apps using standalone Redis/Valkey and multi-key commands; does not scale shards horizontally like Cluster Mode Enabled.
- **Replicas** can be configured for availability/read scaling where supported. Failover can still **drop connections**, so clients must reconnect with backoff.
- **Persistence** such as AOF or RDB is optional and configurable with its own cost and limits; **replication does not replace backups or the system of record**.

For standalone **Memorystore for Redis**, Basic tier suits caches that tolerate data loss; Standard tier provides a replica and automatic failover. HA lowers outage risk, **but does not guarantee zero-second downtime or zero cache loss**.

| Topic | Accurate mental model |
| --- | --- |
| Fast cache hits | Reduce DB load and p95, though still incur a network hop |
| Failover | Pooled connections can break; the SDK must reconnect |
| Key loss from TTL/eviction | Normal behavior; the app must handle misses |
| Full cache flush/loss | Can trigger a **thundering herd** on the DB if fills are unthrottled |
| AOF/RDB | Useful for certain workloads, but does not turn a cache into a transactional DB by default |

## 4. Cache-Aside: The Common Pattern for Java Apps

**Cache-aside** (*lazy loading*): the application checks the cache first. On a miss, it reads the system of record, then writes the result to the cache with a **TTL**.

~~~mermaid
flowchart TD
    R["GET product(sku-01)"] --> C{"Cache has key?"}
    C -->|"Hit"| H["Return cached value"]
    C -->|"Miss"| DB["Read Cloud SQL/Firestore"]
    DB --> V{"Data found?"}
    V -->|Yes| SET["SET key EX TTL"]
    SET --> RETURN["Return result"]
    V -->|No| N["Return not found; short negative-cache when appropriate"]
    C -. "Redis temporarily failing" .-> FALL["Fallback to source of truth + alert"]
    FALL --> DB
~~~

- **Cache hit**: data is present; skip the DB.
- **Cache miss**: missing, expired, or evicted; fall back to DB.
- **TTL**: maximum lifetime of a cached entry if not refreshed.
- **Eviction**: key removed due to memory pressure under `maxmemory-policy`, potentially **before its TTL expires**.

Example keys managed by namespace/version:

~~~text
catalog:v1:product:sku-01
catalog:v1:product:sku-02
catalog:v1:tenant:tenant-7:sku-03
~~~

Never use unvalidated raw user input as keys, and never mix data across tenants. If an API changes the schema of cached values, **bump the key namespace/version** to avoid deserialization errors on stale payloads.

## 5. TTL, Invalidation, and Stale Data

Choose TTLs based on your **staleness budget**, not one arbitrary default across every business field.

| Data | Policy suggestion | Reason |
| --- | --- | --- |
| Versioned images/assets | Long TTL / CDN | Immutable URLs are safe to cache |
| Catalog names/descriptions | Tens of seconds/minutes TTL + invalidate on edit | Short staleness acceptable |
| Promotional pricing | Short TTL + version, re-verify at checkout | Prices can change |
| Inventory counts and payment amounts | DB/transactions are the decision authority | Cache cannot enforce transactional invariants |
| 404 results | Very short **negative cache** TTL when suitable | Prevents repeated DB misses without hiding newly created items |
| Tokens, PII, secrets | Avoid, or enforce threat model, TLS, encryption, TTL, and access control | A cache is not automatically a secure vault |

### 5.1. Update the Database First, Delete the Cache Second

~~~text
BEGIN / UPDATE DB / COMMIT
              |
              v
          DEL cache-key
              |
              v
  Next request misses → reads new DB state → fills cache
~~~

**Always commit to the source of truth before invalidating the cache.** Deleting the cache first before a DB transaction rolls back can leave stale data refilled into the cache unnecessarily.

**Race warning:** cache-aside + post-commit `DEL` **does not guarantee immediate consistency**. Request A may read old data from the DB, request B commits an update and deletes the key, and then A populates the cache with the stale value. For strict freshness requirements, use **versioned keys, verified event-driven invalidation, optimistic versions, or bypass the cache for critical reads**. TTL only bounds maximum staleness under normal conditions; it does not replace correctness controls.

### 5.2. Preventing Synchronized Expirations

Give keys slightly varied TTLs (TTL + **jitter**, e.g., 60–75 seconds) to avoid expiring together. Do not set unbounded random TTLs; stay within acceptable staleness bounds. Security or permission changes typically require active invalidation rather than waiting out a TTL.

## 6. Java with Lettuce: Cache-Aside and Fallback

The sample below uses **local standalone Valkey** over the Redis protocol. `SOURCE` simulates Cloud SQL; in production use a real repository rather than a `ConcurrentHashMap`. **This is not a preconfigured client for Memorystore for Valkey Cluster Mode Enabled**; cluster deployments require a cluster-aware client, discovery endpoints, and TLS/auth matching instance settings.

### 6.1. Maven Project

Structure:

~~~text
cache-lab/
├── pom.xml
└── src/main/java/lab/cache/CacheAsideDemo.java
~~~

Minimal `pom.xml` for Java 21:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>lab.cache</groupId>
  <artifactId>cache-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>io.lettuce</groupId>
      <artifactId>lettuce-core</artifactId>
      <version>6.6.0.RELEASE</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.14.0</version>
      </plugin>
      <plugin>
        <groupId>org.codehaus.mojo</groupId>
        <artifactId>exec-maven-plugin</artifactId>
        <version>3.6.4</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Dependency versions are for illustration: before production, use the latest **vetted** releases and scan for vulnerabilities. Never embed Redis passwords or IAM tokens into URIs in source code.

### 6.2. `CacheAsideDemo.java`

~~~java
package lab.cache;

import io.lettuce.core.RedisClient;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

public class CacheAsideDemo {
    // DEMO: Map stands in for the source database. Production uses a repository/Cloud SQL.
    private static final Map<String, String> SOURCE = new ConcurrentHashMap<>();

    static String getProduct(String sku, RedisCommands<String, String> cache) {
        String key = "catalog:v1:product:" + sku;
        if (cache != null) {
            try {
                String hit = cache.get(key);
                if (hit != null) {
                    System.out.println("HIT " + sku);
                    return hit;
                }
            } catch (RuntimeException unavailable) {
                System.err.println("CACHE_READ_FAILED; use source");
            }
        }

        System.out.println("MISS " + sku);
        String fromSource = SOURCE.get(sku);
        if (fromSource != null && cache != null) {
            try {
                cache.setex(key, 30, fromSource); // 30-second TTL.
            } catch (RuntimeException unavailable) {
                System.err.println("CACHE_FILL_FAILED; source value returned");
            }
        }
        return fromSource;
    }

    static void updateProduct(String sku, String value,
            RedisCommands<String, String> cache) {
        SOURCE.put(sku, value); // DEMO: production must COMMIT to DB first.
        if (cache != null) {
            try {
                cache.del("catalog:v1:product:" + sku);
            } catch (RuntimeException unavailable) {
                System.err.println("CACHE_INVALIDATION_FAILED; stale until TTL");
            }
        }
    }

    public static void main(String[] args) {
        SOURCE.put("sku-01", "Laptop 16GB");
        RedisClient client = RedisClient.create("redis://127.0.0.1:6379");
        StatefulRedisConnection<String, String> connection = null;
        try {
            try {
                connection = client.connect();
            } catch (RuntimeException unavailable) {
                System.err.println("CACHE_UNAVAILABLE; source-only mode");
            }
            RedisCommands<String, String> cache =
                connection == null ? null : connection.sync();

            System.out.println(getProduct("sku-01", cache)); // First run: MISS.
            System.out.println(getProduct("sku-01", cache)); // HIT if cache is healthy.
            updateProduct("sku-01", "Laptop 32GB", cache);
            System.out.println(getProduct("sku-01", cache)); // Updated value.
        } finally {
            if (connection != null) {
                connection.close();
            }
            client.shutdown();
        }
    }
}
~~~

**Intentional limitations:**

- This is a **synchronous single-process demo**, without connection pooling/reconnect topology, metrics, tracing, jittered TTLs, or coordination for concurrent misses.
- `SOURCE` is an in-memory `Map`; if the cache dies, the example reads the Map. In production, the fallback is the **source database**, which must be protected by timeouts, connection pools, and backpressure.
- `updateProduct` illustrates **commit then `DEL`** but does not eliminate the fill race described in Section 5.1.
- Cache failures must not corrupt DB writes; for counters enforcing **security/rate limits**, never default blindly to "fail-open."

## 7. Local Lab Without Creating Billable Memorystore Instances

Requires Docker, Java 21, Maven, and free local port 6379. Run a **standalone Valkey** instance to learn the protocol:

~~~bash
# Bind only to loopback on the lab machine, never expose publicly.
docker run -d --name memorystore-cache-lab \
  -p 127.0.0.1:6379:6379 \
  valkey/valkey:8.1

docker exec memorystore-cache-lab valkey-cli ping
# Expected: PONG
~~~

Create the Maven project and Java file from Section 6, then run:

~~~bash
mvn -B -ntp compile
mvn -q exec:java \
  -Dexec.mainClass=lab.cache.CacheAsideDemo

docker exec memorystore-cache-lab valkey-cli \
  TTL catalog:v1:product:sku-01

docker exec memorystore-cache-lab valkey-cli \
  GET catalog:v1:product:sku-01
~~~

Data expires after 30 seconds, so `TTL = -2` or `GET = nil` afterward is expected. Never run `FLUSHALL`/`FLUSHDB` on production or shared instances.

**Testing failure safely in the lab:** stop the local container before running Java, observe `CACHE_UNAVAILABLE`, and verify data still comes from `SOURCE`; never stop a managed production instance to test fallback. Clean up the container:

~~~bash
docker stop memorystore-cache-lab
docker rm memorystore-cache-lab
~~~

This lab demonstrates `GET → MISS → SETEX → HIT → DEL`. You cannot extrapolate from a local container lab that Memorystore HA, PSC, IAM auth, TLS, or real sharding have been tested.

## 8. Inspecting Existing Memorystore Instances with gcloud (Read-Only)

Scope: project `PROJECT_ID`, region `asia-southeast1`. Requires Memorystore view permissions; **creates or modifies no resources**:

~~~bash
gcloud auth list
gcloud config get-value project

# Valkey and newer API-managed Memorystore instances:
gcloud memorystore instances list \
  --location=asia-southeast1 --project=PROJECT_ID

# Redis Basic/Standard tier:
gcloud redis instances list \
  --region=asia-southeast1 --project=PROJECT_ID

# Once an ID is verified:
gcloud memorystore instances describe INSTANCE_ID \
  --location=asia-southeast1 --project=PROJECT_ID

gcloud redis instances describe REDIS_INSTANCE_ID \
  --region=asia-southeast1 --project=PROJECT_ID
~~~

Do not use `gcloud redis instances ...` to manage **Valkey**, or use `gcloud memorystore instances ...` assuming it lists all **Redis Basic/Standard** instances. **Redis Cluster** has its own CLI group (`gcloud redis clusters ...`); verify the exact product before writing automation.

To **create** Memorystore for Valkey in a cloud lab, you must prepare a **VPC, Private Service Connect service connection policy**, location/zones, node type, shard count, replica count, mode, IAM/TLS, and Billing. Avoid copying a `create` command without PSC prerequisites and blaming Redis/Java. **`shared-core-nano` node types are for dev/test and carry no SLA**; production requires proper sizing and HA.

## 9. Security and Connectivity from Cloud Run/GKE/Compute Engine

Memorystore for Valkey uses **Private Service Connect (PSC)** without exposing endpoints to the public Internet. Older Redis products use different networking/authorized-VPC models; consult the exact product documentation.

| App origin | Connectivity checks |
| --- | --- |
| **Cloud Run** | Use **Direct VPC egress** (recommended) or Serverless VPC Access; subnets, routes, firewall/network tags, and PSC endpoint |
| **GKE** | Node/Pod egress to VPC/PSC, `NetworkPolicy`, firewalls, DNS, and multi-zone reachability |
| **Compute Engine** | VM in a network with routing to the private endpoint; firewall/ports and service account |
| **Local developer** | Never expose Redis publicly; use an organization-approved private path or an emulator/local Valkey |
| **Shared VPC/cross-project** | Verify PSC project/network policies, endpoint creation permissions, and ingress/egress constraints |

### 9.1. Distinguishing Admin IAM from Data Authentication IAM

- **Control plane IAM**: who can create/describe/delete instances.
- **Data plane authentication**: who can send `GET`/`SET` commands to the cache. **Not granted automatically** just because a caller holds IAM Viewer.
- **Valkey IAM authentication**: can use `roles/memorystore.dbConnectionUser` and access tokens via `AUTH` when enabled. Short-lived tokens must be **refreshed when opening new connections**; never hard-code them.
- **TLS in-transit**: must be **enabled and configured on the client**; IAM AUTH alone does not imply every connection is encrypted. Valkey supports token auth/ACLs per configuration and supported features.
- **Redis Basic/Standard**: AUTH/TLS mechanisms depend on product capabilities; do not mechanically apply Valkey IAM auth rules to them.

Never store passwords, access tokens, session cookies, or sensitive customer data in CLI history or logs. A private VPC endpoint **does not replace application-level authorization**.

### 9.2. Cluster-Aware Clients and Key Slots

With **Valkey Cluster Mode Enabled / Redis Cluster**, use a Redis/Valkey client supporting cluster discovery, `MOVED`, `ASK`, and topology refresh. Connecting to the discovery endpoint with a standalone client fails with `MOVED` when a key lives on another shard.

Example grouping keys that must operate in the same hash slot:

~~~text
cart:{user-123}:items
cart:{user-123}:totals
~~~

`{user-123}` is a **hash tag** pinning both keys to the same slot, though it creates a hot slot if one tenant dominates traffic. Multi-key atomic operations work only within **the same slot** under cluster semantics; never design cross-shard transactions using a single `MULTI`/`EXEC` block.

## 10. Caching Patterns and Data Invariants

| Pattern | How it works | When to use |
| --- | --- | --- |
| **Cache-aside** | App checks cache; on miss, reads DB and populates cache | Default choice for catalogs/read-heavy workloads |
| **Read-through** | Cache layer/library fetches from source on miss automatically | Compatible framework/provider simplifying app code |
| **Write-through** | Writes pass through cache/coordinator to source | When adapter semantics are clear; handle partial-write failures |
| **Write-behind** | Writes to cache then flushes to DB asynchronously | Only if durability lag/loss risk is acceptable with queues/replay |
| **L1 + L2** | In-process Caffeine plus shared Valkey | Very high read volume; requires two-tier TTL/invalidation |
| **Stale-while-revalidate** | Serves stale copy briefly while refreshing in background | Catalogs/HTTP caches tolerating bounded staleness |

**Never call write-behind a safe transaction** for orders/payments: if the cache loses data before flushing to the DB, the business can lose transactions. For critical data, **the database is the system of record**, while the cache purely optimizes speed.

## 11. Cache Stampedes, Hot Keys, and Protecting the Source Datastore

**Cache stampede**: a hot key's TTL expires, thousands of requests miss simultaneously, and all hit the DB at once.

Mitigation techniques:

1. **TTL + jitter**: prevents simultaneous expirations.
2. **Request coalescing / single-flight**: for a given key, only one request fills the cache per instance.
3. **Short-lived distributed lock** when truly needed: `SET key value NX PX timeout` so one worker populates, using an ownership token and safe release; never issue an unconditional `DEL` on another worker's lock.
4. **Stale-while-revalidate** for data tolerating bounded staleness.
5. **Short negative caching** for missing keys (never cache `permission-denied` results).
6. **Rate limiting/backpressure/circuit breakers** when the cache is unavailable, preventing fallback traffic from overwhelming the database.

**Hot keys** differ from stampedes: one key is constantly hit at extreme rates even without misses; you may need L1 caching, read-load sharding, immutable-data replication, or client-side distribution fixes.

### 11.1. Eviction and Memory Policies

Redis/Valkey can use policies such as `allkeys-lru`, `volatile-ttl`, or `noeviction` depending on product/instance. With `noeviction`, hitting the memory limit causes new writes to fail; with eviction enabled, keys can vanish **before their TTL**. Monitor **evicted keys, hit/miss ratio, and max memory** with alerts. Never treat a cache as the sole datastore if eviction/data loss is unacceptable.

## 12. Choosing the Right Cache Per Scenario

| Problem | First option to evaluate | Why |
| --- | --- | --- |
| Public static JS/CSS/images | **Cloud CDN + `Cache-Control`** | Edge caching reduces application load |
| Product catalog across many Cloud Run instances | **Memorystore for Valkey** cache-aside | Shared cache, TTL, and invalidation |
| Small, rarely changing config per Pod | **Caffeine** | Zero network hop or managed-instance fee |
| Web sessions | Valkey/Redis if shared state is needed, **TTL and auth** | Independent of single-instance memory; avoid raw PII |
| Service-wide rate limiting | Valkey/Redis **atomic commands/scripts** per key slot | Consistent across replicas; design fail-open/closed by risk |
| Inventory/orders/payments | **Cloud SQL/Spanner/Firestore transactions** | Enforces business invariants; never decide via cache |
| Large-scale durable time-series/key-value | **Bigtable** | High-throughput database, not a memory cache |
| Legacy Memcached systems | **Plan migration to Valkey** | Memcached is deprecated |

With CDNs, cache only shareable responses; configure `Cache-Control: private, no-store` for account/cart data unless strict cache-key design and controls exist. `Cache-Control`, `CDN-Cache-Control`, and backend cache modes govern behavior; never assume "turning on Cloud CDN" automatically caches every API.

## 13. Measuring Effectiveness, Reliability, and Cost

Monitor both **cache and DB**, because a cache can look "healthy" while saving nothing if requests still hit the DB.

| Category | Metrics | Operational question |
| --- | --- | --- |
| **Effectiveness** | Cache hit/miss counts, hit ratio | Is it actually reducing database reads? |
| **Latency** | p50/p95/p99 cache `GET`, end-to-end API | Is L2 meaningfully faster than DB fallback? |
| **Capacity** | Memory utilization, evictions, fragmentation, hot shards | Is RAM tight or load skewed? |
| **Connections** | Active/new connections, reconnects, timeouts | Are there connection storms after deploys/failovers? |
| **Reliability** | Failed requests, failovers, errors, cache-down duration | Does the app fall back safely with bounded load? |
| **DB** | QPS, connections, CPU, p95 query latency | Did cache hits truly relieve DB pressure? |
| **Cost** | Provisioned nodes/replicas, PSC network, logging, egress | Do benefits outweigh total cache cost? |

Example with 8,000 hits and 2,000 misses out of 10,000 lookups:

~~~text
Hit ratio = 8,000 / (8,000 + 2,000) = 80%

Follow-up metrics: How much did DB QPS drop?
How much did API p95 improve? Were there stale-data incidents?
~~~

Memorystore provides Cloud Monitoring metrics for keyspace hits/misses, CPU, memory, and connections per product. For multi-shard Valkey, watch **maximum utilization/hot node**, not just averages.

**Cost:** Memorystore is a **provisioned-capacity** service: instances can incur charges **as soon as they are created, even with zero requests**. Valkey bills by node type, shard/replica count, region, persistence, and associated networking/backups. Redis Basic/Standard has its own hourly capacity pricing. Adding standby nodes, extra replicas, or VPC connectors increases total cost. Use Cloud Billing Reports and budget alerts; **budget notifications are not hard spending caps**.

## 14. Common Troubleshooting

| Symptom | Likely cause | What to inspect |
| --- | --- | --- |
| Cloud Run times out reaching cache | Missing Direct VPC egress/subnet/PSC/firewall | Network routes, endpoint, service connection policy |
| `MOVED` or `CROSSSLOT` | Standalone client or cross-slot keys on a cluster | Cluster client/topology/hash tags |
| `NOAUTH`/`WRONGPASS` | Bad AUTH token, IAM principal, or TLS/config | Data-plane auth, token refresh, TLS handshake |
| `READONLY` after failover | Client still bound to replica or wrong endpoint | Reconnect/refresh topology, backoff |
| `OOM` or rejected writes | Full memory, `noeviction`, or oversized keys | Memory/evictions, `maxmemory-policy`, sizing |
| Low hit ratio | Short TTL, inconsistent key versions, high cardinality | Key naming, TTL, hit/miss sampling |
| Persistent stale values | Cache-aside race, failed `DEL`, long TTL | Invalidation logs, versioning, freshness budget |
| DB overloaded when cache fails | Unthrottled concurrent fallbacks | Circuit breaker, coalescing, backpressure |
| Cache latency rises while avg CPU is low | Single hot shard/key, connection pool bottleneck | Max per-node metrics, load tests |
| High bill during low traffic | Provisioned instances/replicas, network connectors | Billing SKUs, instance sizing, cleanup |

**Never fix connectivity by opening Redis ports to the Internet**; use VPC/PSC/TLS and least privilege. Also never log `AUTH` tokens when debugging.

## 15. Capstone Scenario: Optimizing a Catalog API

**Assumptions:** a Java `catalog-api` on Cloud Run serves 20,000 requests/minute, 90% product GETs, backed by Cloud SQL PostgreSQL. The team wants to lower p95 from 250 ms without letting the cache decide inventory during checkout.

Design:

~~~mermaid
flowchart TD
    API["GET /products/:sku"] --> L1{"Caffeine (L1)"}
    L1 -->|"miss"| L2{"Valkey (L2)"}
    L2 -->|"miss"| DB["Cloud SQL SELECT"]
    DB -->|"fill L2 + L1"| OUT["Response"]
    L1 -->|"hit"| OUT
    L2 -->|"hit + fill L1"| OUT
    CHANGE["Admin updates product"] --> COMMIT["Cloud SQL COMMIT"]
    COMMIT --> INVALIDATE["Invalidate L2 + publish L1 invalidation event"]
~~~

**Rollout plan:**

1. Measure baseline DB QPS, API p95, query latency, and cost.
2. Cache **descriptions/images/public attributes** with short jittered TTLs; never cache inventory counts as checkout truth.
3. Add L2 Valkey with cache-aside; add L1 only when clearly beneficial and extra staleness is acceptable.
4. Commit to DB then invalidate; monitor races, key versions, and missed invalidations.
5. Build dashboards for hits/misses, memory, evictions, cache errors, and DB traffic; simulate cache outage in staging.
6. Bound fallback with pools/circuit breakers; keep SLOs and roll back if stale data occurs or p95 fails to improve.
7. Calculate total cost of Valkey nodes/replicas/PSC, Cloud Run egress, and Cloud SQL savings.

**Success criteria:** hit ratio/latency meet SLOs, DB QPS drops, cache outages never drop transactions, and total cost stays within budget. Never judge success solely by "`GET` on Redis is fast."

## 16. Practice Exercises and Self-Check Questions

**Exercise 1 — Local cache-aside.** Run the Section 7 lab and observe `MISS → HIT → update → MISS`. After 30 seconds, check `TTL`/`GET`.

*Pass criteria:* data falls back to `SOURCE` on miss, TTL expires properly, and the updated value appears after invalidation.

**Exercise 2 — Cache down.** Stop local Valkey before running Java.

*Pass criteria:* the simulated source still returns data; production requires timeouts and bounded fallback.

**Exercise 3 — TTL and freshness.** Product prices change after 10 seconds while TTL is 5 minutes. What is wrong?

*Answer:* prices can stay stale for 5 minutes if invalidation fails; shorten TTL, actively invalidate, version keys, and re-verify prices at checkout.

**Exercise 4 — Stampede.** 10,000 requests miss the same key simultaneously, hammering the DB. Name two mitigations.

*Answer:* single-flight/request coalescing; TTL jitter and stale-while-revalidate when permitted; plus bounded fallback.

**Question 5.** Does Redis Basic tier include automatic failover?

*Answer:* No. Standard tier provides replication/automatic failover.

**Question 6.** Can a standalone client reliably access every shard in Valkey Cluster Mode Enabled?

*Answer:* No; you must use a cluster-aware client with slot routing.

**Question 7.** Are cache and database guaranteed immediately consistent after `COMMIT → DEL`?

*Answer:* No; concurrent cache-fill races can still write stale data.

**Question 8.** Is Memorystore for Memcached still recommended for new systems in 2026?

*Answer:* No; deprecated on Jan 20, 2026—plan migration to Valkey or another suitable service.

**Question 9.** When Cloud Run scales to zero, does Memorystore automatically stop billing?

*Answer:* No. Memorystore bills for provisioned capacity even when idle.

**Question 10.** Does IAM Viewer on a project automatically grant permission to send `GET` to a Valkey instance?

*Answer:* No. Control-plane IAM differs from data-plane authentication; Valkey IAM auth must be enabled with appropriate connection permissions.

**Question 11.** If the cache stores inventory counts, can `DECR` guarantee orders never exceed Cloud SQL stock?

*Answer:* No. The system of record and business transactions must enforce invariants; a cache counter is not atomic with the DB.

**Question 12.** Should a response containing personal data be cached with `Cache-Control: public`?

*Answer:* No. That risks leaking private data through shared caches/CDNs; use `private`/`no-store` or an audited custom design.

**Question 13.** When cache misses are high, should you simply add Redis replicas without investigating?

*Answer:* No. Inspect TTLs, key naming, evictions, traffic distribution, upstream DB, and cost.

**Question 14.** Do HA Valkey/Redis instances preserve open TCP connections across failover?

*Answer:* Not guaranteed; clients must reconnect, refresh topology, and perform bounded retries.

## 17. Production Checklist and Conclusion

- [ ] Classified cached data by **freshness, security, and system of record**.
- [ ] Selected L1/Caffeine, L2/Memorystore, CDN, or DB per workload rather than one-size-fits-all.
- [ ] Selected the right Memorystore product, cluster mode, shards/replicas, HA, and Memcached migration roadmap.
- [ ] Designed namespace/versioned keys, TTLs, and invalidation.
- [ ] Never cached transactional data as the sole decision authority.
- [ ] Added stampede protection, hot-key mitigation, and bounded fallbacks with timeouts/backpressure.
- [ ] Configured cluster-aware clients for Redis/Valkey clusters to handle topology changes.
- [ ] Verified VPC/PSC paths, TLS, and product-appropriate data-plane auth from Cloud Run/GKE/VMs.
- [ ] Avoided storing passwords/PII/tokens in caches or logs without a threat model.
- [ ] Load-tested hits/misses, p95/p99, DB QPS, key evictions, and failover.
- [ ] Set up dashboards for CPU/memory/connections/evictions, alerts, and rollback procedures.
- [ ] Accounted for provisioned node/replica/network costs and authorized lab cleanup.

**Conclusion:** Caching reduces latency and database load, yet **it is only a copy that can expire, be evicted, or vanish during failures**. For Java apps on Google Cloud, a sound approach starts with **cache-aside + TTL + invalidation + a system of record**, adding Caffeine, Memorystore for Valkey, or Cloud CDN where benchmarks prove value. Data correctness, safe fallback, connection security, and cost must all be verified alongside performance.

## Official Reference Documentation

- [Memorystore overview](https://cloud.google.com/memorystore/docs)
- [Memorystore for Valkey overview](https://cloud.google.com/memorystore/docs/valkey/product-overview)
- [Valkey: Cluster Mode Enabled vs Disabled](https://cloud.google.com/memorystore/docs/valkey/cluster-mode-enabled-and-disabled)
- [Valkey: Networking](https://cloud.google.com/memorystore/docs/valkey/networking)
- [Valkey: IAM authentication](https://cloud.google.com/memorystore/docs/valkey/about-iam-auth)
- [Valkey: Persistence](https://cloud.google.com/memorystore/docs/valkey/persistence-overview)
- [Memorystore for Redis Cluster overview](https://cloud.google.com/memorystore/docs/cluster/memorystore-for-redis-cluster-overview)
- [Memorystore for Redis: Basic vs Standard tiers](https://cloud.google.com/memorystore/docs/redis/redis-tiers)
- [Memorystore for Memcached deprecation timeline](https://cloud.google.com/memorystore/docs/memcached/deprecation/memcached)
- [Connect Memorystore Redis from Cloud Run](https://cloud.google.com/memorystore/docs/redis/connect-redis-instance-cloud-run)
- [Cloud Run Direct VPC egress](https://cloud.google.com/run/docs/configuring/connecting-vpc)
- [Cloud CDN caching overview](https://cloud.google.com/cdn/docs/caching)
- [Memorystore for Valkey pricing](https://cloud.google.com/memorystore/valkey/pricing)
- [Memorystore for Redis pricing](https://cloud.google.com/memorystore/docs/redis/pricing)
