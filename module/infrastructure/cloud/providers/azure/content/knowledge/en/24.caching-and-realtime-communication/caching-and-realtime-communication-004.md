# Connecting Securely to Redis from Java Applications

A Java API backed by Azure SQL Database may read the same product catalog thousands of times per minute. Redis stores a temporary copy of data to cut latency and database query load. Yet if the Redis connection is unencrypted, authentication is misconfigured, passwords leak, cache keys ignore tenant isolation, or retries run unbounded when Redis fails, an acceleration layer can turn into a security vulnerability and a trigger for cascading outages.

**Connecting securely to Redis from Java applications** spans multiple layers: selecting the right Azure Redis service; identifying the endpoint and TLS port; verifying server certificates; choosing Microsoft Entra ID or credentials per service support; protecting secrets; configuring private networking; managing the Lettuce/Spring Redis client lifecycle; bounding timeouts, retries, and concurrency; and ensuring cached data never breaks business correctness.

This lesson belongs to the **Caching and Real-time Communication** chapter of the **CLOUD_PROVIDERS_AZURE** module. Along the Azure learning path from subscriptions, resource groups, and Microsoft Entra ID to virtual networks, compute, storage, and data, this skill ties directly into deploying, monitoring, securing, and controlling application architecture costs.

> **Note:** Azure currently offers **Azure Managed Redis** alongside existing **Azure Cache for Redis** deployments. Products, tiers, hostnames, TLS ports, Redis protocol modes, and authentication mechanisms can differ. Azure Cache for Redis has migration/retirement schedules by SKU; when building new systems, check current documentation and announcements. Never hardcode a single connection config across all Azure Redis services.

## Learning objectives

After this lesson, you will be able to:

1. Distinguish a Redis cache from the authoritative data source and from an in-JVM cache.
2. Identify the right Redis endpoint, TLS port, authentication mode, and topology.
3. Enforce **TLS and certificate/hostname verification** in Java Lettuce.
4. Understand Microsoft Entra ID/managed identity, Redis ACLs/passwords, and access key management.
5. Write Lettuce code to read and write TTL-bounded keys in a safe lab environment.
6. Configure Spring Boot and Spring Data Redis while managing long-lived Redis clients.
7. Design **cache-aside**, TTLs, multi-tenant cache keys, and invalidation.
8. Configure timeouts, retries, backoff, pooling, and fallbacks so a Redis outage never takes down the database.
9. Diagnose DNS, Private Endpoint, TLS, AUTH, cluster routing, and capacity issues.
10. Design logging, metrics, testing, and production checklists for Java workloads on Azure.

## 1. Where does Redis fit in the architecture?

~~~text
Browser / Mobile
       |
       v
Java API (AKS / App Service / Container Apps)
       |
       v
Redis cache on Azure
   | HIT              | MISS
   v                  v
Return value     Azure SQL / Cosmos DB
                      |
                      v
                SET Redis with TTL
                      |
                      v
                  Return response
~~~

In a **cache-aside** architecture, Redis holds data reproducible from the backend; Azure SQL/Cosmos DB remains the **source of truth**. When the cache is cleared, expires, or fails over, the application must know how to fetch from the primary source or degrade per policy.

Redis does not replace end-user authorization, provide atomic transactions with Azure SQL, guarantee every cache hit is the newest state, or offer Azure Service Bus semantics for critical job queues.

## 2. Azure Managed Redis vs Azure Cache for Redis

| Criterion | Azure Managed Redis | Legacy Azure Cache for Redis |
|---|---|---|
| Purpose | Azure-managed Redis service for modern architectures | Redis cache deployed across many existing Azure systems |
| Endpoint | FQDN/port provided by the resource | FQDN/port provided by the resource |
| Common TLS port | **10000** in many configurations | **6380** in many configurations |
| Authentication | Entra ID/ACL/access key per config, tier, and support | Access keys/Entra ID per SKU and capability |
| Network | Private networking and access restrictions per service/tier | Private Endpoint/VNet integration per tier |
| Cluster/HA | Based on deployment mode, shards/replicas, and SKU | Based on tier/replicas/clustering |
| Lifecycle | Evaluate for new architectures | Check migration notices and support timelines |

**Never guess the actual port solely from the product name.** A Java application should receive **REDIS_HOST, REDIS_PORT, and auth mode** from environment configuration verified against the exact Azure resource.

### Preflight before writing code

1. Is the resource Azure Managed Redis or Azure Cache for Redis?
2. Which hostname and **TLS port** are listed in its connection details?
3. Does the service use **Entra tokens**, Redis ACL username/password, or access keys?
4. Does the Java workload connect over a private endpoint or a firewalled public endpoint?
5. Does the client need a standard **RedisClient** or a **Redis Cluster-aware client** matching the topology?

Calling a Redis deployment "managed" does not guarantee every client mode and every Redis command behaves identically to a local OSS Redis instance.

## 3. How does an in-JVM cache differ from Redis?

| Characteristic | Caffeine/JVM local cache | Redis |
|---|---|---|
| Storage location | Heap of each Java process | External cache service |
| Network | None | TCP/TLS/network latency |
| Shared across replicas | Not automatically | Shared across pods |
| Pod restart | Local data is lost | Redis has an independent lifecycle |
| Cost | JVM RAM/CPU | Redis SKU, network, ops, monitoring |
| Invalidation | Must synchronize across instances | Shared keys, still needs TTL/invalidation |

Both cache layers can coexist. However, updating a Redis key **does not automatically clear** Caffeine entries sitting inside dozens of Java pods. Each layer adds a freshness problem.

## 4. Cache-aside and TTL

~~~text
GET product 123
     |
     v
GET Redis key
     |
     +-- HIT -> return acceptable cached data
     |
     +-- MISS -> read DB -> SET Redis TTL -> return data
~~~

**TTL (time to live)** is the lifetime of a cache entry. Pick TTLs from business requirements, not one system-wide constant.

| Data | Should you cache? | Staleness considerations |
|---|---|---|
| Country reference list | Usually appropriate | Can tolerate long TTLs |
| Public product catalog | Appropriate with invalidation | Prices/stock require re-verification |
| Aggregate dashboards | Depends on freshness SLO | Can display data age |
| Balances or payment state | Never cache casually | Requires authoritative source/transactions |
| Tokens/passwords | Only inside specialized security designs | Secret exposure and revocation lifecycle |

### Invalidation when data changes

~~~text
PUT product 123
    |
    v
Commit change in database
    |
    v
DEL Redis key product 123
    |
    v
Next read -> MISS -> load fresh data
~~~

If cache deletion fails after database commit, stale values can persist until TTL expires. **Latency optimization must never unconditionally trade away business data correctness.**

## 5. TLS protects the Redis transport

TLS encrypts traffic and verifies server identity:

~~~text
Java client                     Redis server
     |                              |
     | ClientHello + SNI FQDN       |
     +----------------------------->|
     | Server certificate           |
     |<-----------------------------+
     | Validate CA + hostname       |
     | AUTH per supported mode      |
     +----------------------------->|
     | GET/SET over encrypted pipe  |
     +=============================>|
~~~

**Four mandatory checks:**

1. Connect to the **TLS port** of the exact resource.
2. Enable SSL/TLS on the client.
3. Verify the certificate chain and hostname; never use **trust-all**.
4. Connect using the official FQDN, not an IP address to dodge DNS.

**Private Endpoint does not replace TLS.** Private Endpoint restricts the network path; TLS protects payload confidentiality and peer identity.

### Dangerous mistakes to avoid

- Disabling **verifyPeer** to bypass PKIX errors.
- Connecting over a non-encrypted Redis port just because traffic stays inside a private VNet.
- Pointing production at a dev hostname.
- Connecting directly to a private IP, breaking SNI/hostname verification.
- Logging Redis URLs containing passwords or tokens.

An **SSLHandshakeException** or **PKIX path building failed** error must be resolved by checking CA certificates, truststores, DNS, and certificates—not by disabling server verification.

## 6. Hostname, SNI, and Java truststore

A lab config should separate:

~~~text
REDIS_HOST=<Azure-provided FQDN>
REDIS_PORT=<exact TLS port>
REDIS_USERNAME=<username if required by auth mode>
REDIS_PASSWORD=<secret, injected only at runtime>
~~~

Java relies on the JDK truststore (or a managed custom store) to verify certificate chains. A stripped-down Java container image missing system CAs or running an outdated JDK may fail to trust certificates that a laptop browser accepts.

### What to verify

- The JDK version still receives security updates.
- The hostname Lettuce connects to matches the certificate.
- DNS resolves to the Private Endpoint route when used.
- No custom trust manager is configured to **accept every certificate**.
- No unverified CA/certificates are imported blindly.

If an organization uses TLS inspection, truststore updates must go through security review; never trust an unknown CA just to make a connection pass.

## 7. Authentication and Redis permissions

| Mechanism | How it works | Notes |
|---|---|---|
| **Microsoft Entra ID** | Redis data access via tokens/identities when supported | Tokens expire; requires refresh/re-auth |
| **Redis ACL username/password** | Authenticates user and scopes commands/keys | Requires proper ACLs and rotation |
| **Access key/password** | Static secret issued by the service | Must be kept secret and rotated |
| **Azure RBAC management plane** | Manages Redis resources in the subscription | Does not grant GET/SET over the Redis protocol |
| **Application authorization** | Which end user may access which data | Never skip just on a cache hit |

### Prefer identity over long-lived secrets

For Java workloads running on Azure, evaluate **managed identity** or **AKS Workload Identity** to connect with Microsoft Entra ID whenever supported by the Redis service/tier and SDK integration.

Conceptual flow:

~~~text
Java app with managed identity
       |
       v
Entra ID issues access token for target audience
       |
       v
Redis client AUTH in service-supported format
       |
       v
Redis data-plane authorization
       |
       v
GET/SET per granted permissions
~~~

**Tokens are not permanent passwords.** If a client authenticates once at startup with a token and never refreshes/re-auths, it will fail after token expiry or reconnection. Choose a Java library/integration supporting **token renewal** compatible with the specific Azure Redis product.

## 8. Three permission layers you must not confuse

1. **Management plane:** who can create, delete, or reconfigure Redis in Azure.
2. **Redis data plane:** who can run AUTH, GET, SET, DEL, or other Redis commands.
3. **Application layer:** which end user or tenant may view business data.

For instance, a Java service with Redis GET access across keys must still enforce that **user A cannot request user B's cart**. Key prefixes organize data; they do not enforce authorization.

### Least privilege

- Grant runtime identities only the commands and key patterns needed when ACLs are supported.
- Never share admin credentials across all Java pods.
- Separate dev, staging, and production.
- Protect read access to Key Vault secrets and managed identity attachments.
- Maintain revocation and rotation procedures.
- Never grant subscription-wide Owner to troubleshoot Redis AUTH errors.

## 9. Managing credentials with Key Vault

When a resource uses access keys/passwords, never place secrets in:

- Java source files, tests, or repositories.
- Maven/Gradle build scripts.
- Dockerfiles, container images, or Kubernetes ConfigMaps.
- URLs or command lines that may be logged.
- CI pipeline output, exception stack traces, or application diagnostics.

A safer pattern:

~~~text
AKS Workload Identity / App Service Managed Identity
           |
           v
Azure Key Vault
           |
           | tightly scoped secret read
           v
Java app receives secret at runtime
           |
           v
Lettuce / Spring Data Redis -> TLS -> Redis
~~~

Depending on the architecture, you can use Key Vault references, the Kubernetes Secrets Store CSI Driver, or platform secret injection. **Environment variables are not an impenetrable vault**: anyone with process/container inspection or memory dump access can read them.

### Credential rotation

1. Check whether the Redis service supports dual active keys or a specific rotation workflow.
2. Provision the new secret via change approval.
3. Ensure the app reloads and reconnects/re-auths with the new secret.
4. Verify connections, commands, and metrics.
5. Revoke the old secret once no clients depend on it.
6. Maintain a rollback plan in case Redis AUTH breaks.

**Never reset production access keys to test a lab exercise.**

## 10. What is Lettuce?

**Lettuce** is a Netty-based Java Redis client supporting synchronous, asynchronous, and reactive operations. It is commonly used underneath Spring Data Redis in Spring Boot.

### When to use Lettuce directly?

- Non-Spring Java applications.
- Explicit control over connection lifecycle, RedisURI/TLS, and error handling.
- Specific async/reactive pipelines.
- Writing a clean standalone lab connection test.

### Maven dependency

~~~xml
<dependency>
  <groupId>io.lettuce</groupId>
  <artifactId>lettuce-core</artifactId>
  <version>APPROVED_VERSION</version>
</dependency>
~~~

With Gradle:

~~~groovy
dependencies {
    implementation("io.lettuce:lettuce-core:APPROVED_VERSION")
}
~~~

**APPROVED_VERSION** is a placeholder; use a project-approved version vetted for compatibility and security. When using Spring Boot, let the **Spring Boot dependency BOM** manage versions.

## 11. Java Lettuce: secure TLS connection example

This is a **Java lab example performing SET/GET/DEL** against a test Redis instance. It applies when the endpoint supports **username/password ACL-style auth**. For Microsoft Entra ID, use an integration with dedicated token refresh; never fake a token as a static password.

~~~java
import io.lettuce.core.RedisClient;
import io.lettuce.core.RedisURI;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;
import java.time.Duration;
import java.util.UUID;

public final class RedisTlsLab {
    private static String required(String name) {
        String value = System.getenv(name);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                "Missing environment variable: " + name);
        }
        return value;
    }

    public static void main(String[] args) {
        String host = required("REDIS_HOST");
        int port = Integer.parseInt(required("REDIS_PORT"));
        String username = required("REDIS_USERNAME");
        String password = required("REDIS_PASSWORD");

        RedisURI uri = RedisURI.Builder.redis(host, port)
            .withAuthentication(username, password.toCharArray())
            .withSsl(true)
            .withVerifyPeer(true)
            .withTimeout(Duration.ofSeconds(3))
            .build();

        RedisClient client = RedisClient.create(uri);
        try {
            try (StatefulRedisConnection<String, String> conn =
                    client.connect()) {
                RedisCommands<String, String> redis = conn.sync();
                String key = "lab:java:tls:" + UUID.randomUUID();

                redis.setex(key, 30, "connected");
                String value = redis.get(key);
                if (!"connected".equals(value)) {
                    throw new IllegalStateException(
                        "Redis lab value mismatch");
                }
                System.out.println("Redis TLS/auth lab: PASS");
                redis.del(key);
            }
        } finally {
            client.shutdown();
        }
    }
}
~~~

### What this example guarantees—and does not guarantee

- Enables TLS, verifies the peer, and reads host/port from configuration.
- Keeps passwords out of source code and stdout.
- A 30-second TTL ensures the lab key does not linger forever if the client crashes before DEL.
- Uses a single-endpoint logical `RedisClient`; Redis Cluster topologies may require a cluster-aware client.
- **Never run against production**: this executes writes and deletes.
- Not production-ready for pooling, retries, token refresh, or metrics.
- A Java `String` holding a password cannot easily be zeroed from memory; production needs proper secret management.

### If the endpoint uses password-only auth

Swap the auth builder call for Lettuce's password-only API after verifying the resource:

~~~java
RedisURI uri = RedisURI.Builder.redis(host, port)
    .withPassword(password.toCharArray())
    .withSsl(true)
    .withVerifyPeer(true)
    .withTimeout(Duration.ofSeconds(3))
    .build();
~~~

Do not invent a **default** username unless the resource's auth mode specifies it.

## 12. Spring Boot and Spring Data Redis

Spring Data Redis provides **RedisConnectionFactory**, **RedisTemplate**, and **StringRedisTemplate**, along with cache abstractions via **@Cacheable** when Spring caching is enabled.

### Spring Boot dependency

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
~~~

### application.yml for Spring Boot 3.x

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      client-type: lettuce
      connect-timeout: 3s
      timeout: 2s
      ssl:
        enabled: true
~~~

**Conditions:**

- The **spring.data.redis** prefix applies to modern Spring Boot versions such as 3.x; check your exact version as property namespaces can differ.
- For password-only auth, `username` may be unnecessary.
- For Entra authentication, this static username/password config **is insufficient**: use a client integration with token refresh.
- **3s/2s** are illustrative values; size them against your SLO.
- Never hardcode production hostnames/ports in code; ensure the Redis TLS port matches the resource.

## 13. Spring Java: GET, SET TTL, and DEL operations

Example service using **StringRedisTemplate** to store JSON for a **public** product:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public final class CatalogCache {
    private final StringRedisTemplate redis;

    public CatalogCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String read(String productId) {
        return redis.opsForValue().get(key(productId));
    }

    public void write(String productId, String publicJson) {
        redis.opsForValue().set(
            key(productId), publicJson, Duration.ofSeconds(60));
    }

    public void invalidate(String productId) {
        redis.delete(key(productId));
    }

    private String key(String productId) {
        return "public:catalog:product:" + productId + ":v1";
    }
}
~~~

This code assumes **productId has been validated by the API**, **publicJson** genuinely contains no private fields, and a valid `RedisConnectionFactory`/TLS setup is configured. It is a storage helper, not a full cache-aside pipeline with database fallback, circuit breakers, and monitoring.

### Note on serializers

If another app writes the same key in a different binary format, Spring's `StringRedisTemplate` will not automatically understand it. Agree on a shared format/version and never enable unrestricted Java native serialization on untrusted data.

## 14. Cache keys and tenant isolation

A structured key format:

~~~text
<environment>:<service>:<entity>:<tenant>:<identifier>:<schema-version>

Examples:
lab:catalog:product:public:123:v2
prod:catalog:product:tenant-A:123:v2
prod:catalog:product:tenant-B:123:v2
~~~

**Key prefixes do not replace authorization.** The application must still authenticate the caller and ensure the tenant ID used to construct the key comes from a trusted identity, never an unverified client header.

### Information that must never appear in keys

- Passwords, Redis access keys, or Entra tokens.
- Unnecessary emails, phone numbers, or personal IDs.
- Confidential documents or sensitive payloads.
- URLs containing SAS tokens.
- Full SQL queries carrying sensitive parameters.

Long keys also consume memory; balance debuggability with key size.

## 15. Cache-aside has race conditions

Consider this sequence:

~~~text
Thread A: GET Redis -> MISS
Thread A: read DB -> product v1

Thread B: UPDATE DB -> product v2
Thread B: DEL Redis key

Thread A: SET Redis -> product v1 with TTL
~~~

Afterward, the cache can serve v1 even though the database holds v2. Cache-aside **does not provide atomicity** between Redis and Azure SQL/Cosmos DB.

Mitigations depending on data sensitivity:

- Sufficiently short TTLs.
- Versioned keys or ETags.
- Conditional population when a version mechanism exists.
- Reliable post-transaction invalidation.
- Never relying on the cache to confirm final prices or balances.
- Business-level freshness tests.

## 16. Java client lifecycle and pooling

A classic mistake is creating a new `RedisClient` on every HTTP request:

~~~text
Request 1 -> Create client -> TCP/TLS -> GET -> Close
Request 2 -> Create client -> TCP/TLS -> GET -> Close
...
~~~

This multiplies TLS handshakes, sockets, CPU, and latency. **RedisClient / Lettuce ConnectionFactory should be long-lived** across the application lifecycle.

| Scenario | Connection management guidance |
|---|---|
| Frequent GET/SET | Reuse client and connection per thread-safety contract |
| Blocking Redis commands | Use dedicated connections appropriately |
| Pub/Sub subscriptions | Dedicated connection/subscription |
| Transactions/stateful commands | Control connection ownership and scope |
| Many Java pods | Cap total connections within cache capacity |

Lettuce's **StatefulRedisConnection** supports concurrent operations per the client contract, yet stateful or blocking commands should not be shared arbitrarily. **Pooling does not always make things faster**: excessive connections only add resource pressure.

### Connection budget math

~~~text
25 pods x 40 connections/pod
= 1,000 potential connections
~~~

And that excludes monitoring clients, dual-version rollouts, and reconnect storms. Measure **active, idle, pending, and reconnect counts** alongside Redis limits before enlarging pools.

## 17. Timeouts must fit inside the API budget

| Timeout | Purpose |
|---|---|
| **Connect** | Bounds TCP connection establishment |
| **TLS handshake** | Bounds secure channel setup |
| **Command** | Bounds GET/SET wait time |
| **Pool acquisition** | Bounds waiting when the pool is exhausted |
| **HTTP request** | Bounds total business operation time |

Suppose an API has a **300 ms** p95 SLO, where Redis should occupy only a small slice. Setting a 10-second Redis command timeout lets requests blow past the SLO even when SQL is healthy.

No single timeout value fits every workload; measure TLS handshakes, regional network RTT, p95/p99, failovers, and Redis load. **Too-short timeouts** also trigger false errors and amplify retries.

## 18. Retries must be safe

Transient errors happen during failovers, network jitter, DNS updates, server busy periods, or client reconnects. Apply:

1. Bounded retries.
2. Exponential backoff + jitter.
3. Overall request deadline.
4. Circuit breaker when Redis is unavailable.
5. Concurrency limits to avoid retry storms.
6. Data-appropriate fallbacks.

### Redis commands differ in retry safety

| Command | Retry after timeout? | Reason |
|---|---|---|
| **GET** | Usually relatively safe | No side effects |
| **SET** with same value | Depends on TTL/version semantics | Retry may refresh TTL |
| **INCR** | Never retry blindly | Can double-increment |
| **LPUSH** | Never retry blindly | Can push duplicates |
| **PUBLISH** | Never retry blindly | Can re-emit signals |
| **DEL** | Usually idempotent, check business logic | Key could be recreated between DELs |

A client timeout **does not prove Redis never executed the command**. Business-significant writes require idempotency or a durable data store for reconciliation.

## 19. Safe fallback when Redis fails

~~~text
GET /catalog
      |
      v
GET Redis (short timeout)
    | HIT            | MISS / cache unavailable
    v                v
Return cache       Read Azure SQL
                        |
                        v
                     Return data
~~~

A cache outage should not drop orders. Yet if every request falls back to the database simultaneously, a **DB stampede** can widen the outage.

Safeguards:

- Circuit breakers.
- Bounded DB concurrency and rate limits.
- Per-key single-flight.
- Brief local cache for public data when appropriate.
- Serving stale **only when business rules allow**.
- Fail closed for security functions rather than permitting blindly.

**Redis acting as a rate limiter or distributed lock must not be bypassed using the same fallback logic as a public catalog.**

## 20. Cache stampedes, hot keys, and TTL jitter

When a popular key's TTL expires, thousands of requests can miss at once and hit the database:

~~~text
Key public:catalog:123 expires
     |
     +-- Request A -> DB
     +-- Request B -> DB
     +-- Request C -> DB
     ...
~~~

Mitigations:

- Single-flight/coalescing for the same key.
- Cache warm-up for popular keys.
- TTL jitter within allowed staleness bounds.
- Very short negative caching when permitted by contract.
- Bounded concurrency and backend rate limiting.
- Key distribution monitoring to spot **hot keys**.

For example, a nominal 300-second TTL plus 0–30s jitter works only if business rules tolerate up to 30 seconds of extra staleness. Never add arbitrary jitter to data that must expire strictly on time for security reasons.

## 21. Serialization and schema versioning

Redis stores values as raw bytes/strings over the Redis protocol. Java objects need a suitable serializer—commonly JSON, MessagePack, or an explicit-schema binary format.

### Risk when changing Java models

~~~text
Deployment v1 writes cache:
  {"schemaVersion":1,"productId":"123","price":100000}

Deployment v2 changes contract:
  {"schemaVersion":2,"productId":"123","priceMinor":100000}

If v2 reads old key without migration:
  Deserialization or pricing logic can fail or miscalculate.
~~~

Best practices:

- Include **schemaVersion** in payloads and/or key suffixes.
- Bound item sizes; never cache huge object graphs.
- Avoid unrestricted Java native deserialization on untrusted data.
- Test cross-version compatibility for rolling deployments.
- Never let clients dictate class names or deserializer types.
- Plan key deletion or version bumps when schemas change.

Example public JSON payload:

~~~json
{
  "schemaVersion": 2,
  "productId": "123",
  "name": "Lab Product",
  "priceDisplay": "100000 VND",
  "cachedAt": "2026-11-20T08:00:00Z"
}
~~~

The **cachedAt** field aids debugging, yet **does not replace TTLs and business freshness checks**.

## 22. Multi-tenancy and data leak risks

In SaaS, a key built solely from `productId` fails when two tenants have custom pricing.

~~~text
INSUFFICIENT for tenant-specific responses:
  catalog:product:123

Clearer partitioning:
  catalog:tenant-A:product:123:v2
  catalog:tenant-B:product:123:v2
~~~

Still, **a key prefix is not access control**. The Java API must:

1. Authenticate the user/tenant from a trusted source.
2. Verify authorization before returning data—even on a Redis hit.
3. Derive tenant ID from verified identity claims, never self-asserted headers.
4. Never cache user profiles under shared keys.
5. Protect secrets/tokens/PII per data classification.
6. Isolate Redis workloads or ACLs when stronger separation is required.

**TLS only protects transport**; it will not stop a Java bug from returning tenant A's cached data to tenant B.

## 23. Redis does not replace a durable database

Cache entries can vanish due to TTL, memory eviction, maintenance, failovers, or operational actions. Redis persistence, replication, and durability (where supported by tier) must be evaluated independently.

Never use Redis as the source of truth for:

- Account balances and payment transactions.
- Confirmed orders.
- Inventory without durable coordination and persistence.
- Audit logs required for regulatory compliance.

A cache can lose all its keys and the system **must still recover from its primary store**—or degrade intentionally.

### Redis Pub/Sub vs Azure Service Bus

Redis Pub/Sub fits ephemeral signals between currently online subscribers; offline subscribers miss messages. It does not offer settlement, DLQs, or redelivery like Service Bus Peek-Lock.

~~~text
Java Publisher
      |
      v
Redis Pub/Sub channel
      |
      +-- Subscriber A online -> receives
      +-- Subscriber B online -> receives
      +-- Subscriber C offline -> may miss
~~~

If a system must guarantee eventual processing and failure investigation, evaluate **Azure Service Bus** or a properly designed durable pipeline instead of treating Redis Pub/Sub as a durable queue.

## 24. VNet, Private Endpoint, and DNS

A secure topology:

~~~text
Public Internet
       |
       v
API ingress / gateway
       |
       v
Java application inside VNet
       |
       | DNS resolves Redis FQDN to private route
       v
Redis Private Endpoint
       |
       v
Azure Redis service
~~~

Private Endpoint/VNet integration capabilities depend on **product and tier**. Do not assume every Redis deployment configures identically.

### Network checklist

- Does the Java workload have VNet integration / a route to the endpoint?
- Does DNS inside the **actual pod/VM/process** resolve to the Private Endpoint address?
- Is the Private Endpoint connection Approved?
- Do NSGs, UDRs, Azure Firewall, and egress rules allow the **exact TLS port**?
- Are firewalls and public network access restricted appropriately?
- Does Java still connect via the **official FQDN** for TLS hostname verification?
- Does Redis data-plane authentication work over that network path?

### Common DNS mistake

An administrator creates a Private Endpoint, yet Java pods still resolve the hostname to a public IP because of a missing Private DNS zone link or custom resolver forwarding. Never work around this by hardcoding the private IP in Java: that breaks TLS/SNI and becomes brittle if the IP changes.

## 25. Reading Redis errors layer by layer

| Layer | Symptom | Check |
|---|---|---|
| **DNS** | UnknownHostException | FQDN, Private DNS zone, and resolver |
| **TCP** | Connect timeout/refused | TLS port, NSGs/UDRs, firewall, endpoint approval |
| **TLS** | SSLHandshakeException/PKIX | Certificate chain, truststore, SNI/hostname |
| **AUTH** | NOAUTH, WRONGPASS, or token error | Auth mode, Redis ACLs, token expiry, and permissions |
| **Topology** | MOVED/ASK or redirect errors | Cluster-aware client, topology, and networking |
| **Server** | OOM/command latency, evictions | Memory, CPU, Redis maxmemory policy, hot keys |
| **Client** | Pool timeout, reconnect loops | Connection lifecycle, pool size, threads |
| **Application** | Cross-tenant leak, stale data | Key schema, auth, TTL, invalidation |

### Troubleshooting order

1. Confirm service type, hostname, port, and auth mode.
2. Resolve DNS from where Java actually runs.
3. Verify TCP connectivity to the TLS port.
4. Verify TLS, certificate chain, and hostname.
5. Verify AUTH using the right mechanism.
6. Test PING or a tiny GET in the lab.
7. Measure latency, reconnects, and resource utilization.

**Never change every setting at once.** If DNS is broken, rotating passwords accomplishes nothing; if TLS fails, granting subscription Owner accomplishes nothing.

## 26. Testing DNS/TLS with diagnostic tools

The commands below verify connectivity in authorized environments; they do not delete or alter Redis resources.

### Checking DNS

~~~bash
nslookup "$REDIS_HOST"
~~~

### Checking the TLS certificate

~~~bash
openssl s_client \
  -connect "$REDIS_HOST:$REDIS_PORT" \
  -servername "$REDIS_HOST" \
  -verify_return_error < /dev/null
~~~

This checks the TLS certificate chain and SNI—**it does not prove Redis AUTH succeeds**.

### Testing with redis-cli without passing passwords in arguments

~~~bash
# Use only with valid lab endpoint/credentials.
redis-cli \
  -h "$REDIS_HOST" \
  -p "$REDIS_PORT" \
  --tls \
  --user "$REDIS_USERNAME" \
  --askpass \
  PING
~~~

**Note:** requires a TLS-capable `redis-cli`; adjust per docs if using password-only auth. For Entra token auth, this command does not handle token refresh automatically. Avoid **`-a password`** on the command line, which leaks via process listings and shell history.

### Commands never to use for production diagnostics

- **FLUSHALL/FLUSHDB**: risks wiping all data.
- **KEYS \***: can stall large keyspaces.
- **CONFIG SET**: mutates Redis behavior and may be blocked.
- Prolonged **MONITOR**: heavy overhead and may expose sensitive data.

For key inventories, rely on telemetry or operations-approved observability tools; if scanning keyspaces, run bounded scans in a lab.

## 27. Redis Cluster and client modes

Redis on Azure may expose a single logical endpoint or multiple shards/Redis Cluster protocol depending on service/tier. A large instance does not automatically mean **RedisClusterClient**, nor does every deployment accept a single-node **RedisClient**.

### MOVED/ASK

In the Redis Cluster protocol, **MOVED/ASK** replies redirect clients to another node/slot. If you see these errors:

1. Verify whether the Redis instance uses cluster protocol or an Enterprise-managed single routing endpoint.
2. Pick the client mode/version matching the real topology.
3. Verify SSL and DNS/port reachability to discovered nodes.
4. Never "fix" it by connecting to shard IPs and disabling TLS.

### Never rely on Redis logical DB indexes for tenant isolation

Redis Cluster restricts **SELECT** and multiple logical databases. Use tenant key prefixes, Redis ACLs, separate resources, and application authorization as required; **`SELECT 1` is not a tenant security boundary**.

## 28. Metrics to monitor

| Group | Metric/telemetry | Meaning |
|---|---|---|
| Cache | Hit rate, miss rate | Database-offloading effectiveness |
| Latency | GET/SET p50/p95/p99 | Does cache latency meet API SLOs? |
| Connections | Active/idle, reconnects, handshake errors | Diagnose pool/connection storms |
| Security | AUTH errors, token refresh failures | Are credentials/identities healthy? |
| Memory | Used memory, fragmentation, evictions | Spot RAM exhaustion/evictions |
| Capacity | CPU/server load, bandwidth/ops | Track tier limits |
| Data freshness | Cache age, stale responses | Verify business correctness |
| Backend | SQL/Cosmos DB calls during misses | Spot cascading cache outages |
| Cost | Redis SKU, data transfer, logs, DB savings | Measure real ROI |

Not every item exists as an Azure Monitor metric with that exact name. Per-method Redis p99, business hit rate, or token refresh failures often require **Micrometer/OpenTelemetry/client instrumentation**.

### Safe logging

~~~json
{
  "service": "catalog-api",
  "operation": "GET",
  "cache": "publicCatalog",
  "result": "HIT",
  "durationMs": 8,
  "environment": "lab",
  "correlationId": "req-lab-42"
}
~~~

Never log access keys, Entra tokens, Redis URIs with secrets, raw customer data, or full keys containing PII.

## 29. Observability: hit rate is not enough

Example:

~~~text
100,000 requests/day
Cache hit rate = 80% (assumed)

Theoretical backend fetches:
  100,000 x (1 - 0.80) = 20,000/day

Avoided backend reads:
  80,000/day
~~~

This is only a rough model. Cache warm-ups, retries, evictions, multi-key requests, and thundering-herd DB reads alter real numbers.

**A cache returning wrong-tenant data or wrong checkout prices is still a failure** even at a 99% hit rate. Pair performance telemetry with correctness testing.

### Alerts you should have

- Rising TLS/AUTH/connect errors.
- Redis command p99 exceeding latency budget.
- Sudden cache hit rate drop after a deployment.
- Rising memory pressure/evictions.
- Redis outage triggering spikes on SQL/Cosmos DB.
- Secret/token rotation failures.
- Unauthorized changes to Private DNS/endpoints.
- Rising cache spend without reduced backend reads.

## 30. Spring Cache abstraction and @Cacheable

Spring Boot supports **RedisCacheManager** and annotations:

- **@Cacheable**: fetch from cache or execute the method to populate.
- **@CacheEvict**: remove entries conditionally.
- **@CachePut**: update cache with the method's return value.

Conceptual example, public catalog only:

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public final class PublicCatalogService {
    private final CatalogRepository repository;

    public PublicCatalogService(CatalogRepository repository) {
        this.repository = repository;
    }

    @Cacheable(
        cacheNames = "publicCatalog",
        key = "#productId"
    )
    public ProductDto getPublicProduct(String productId) {
        return repository.loadPublicProduct(productId);
    }
}
~~~

**CatalogRepository** and **ProductDto** are omitted; this snippet only illustrates the annotation. Production requires configuring `RedisCacheManager`, serializers, TTLs, key prefixes, validation, auth, metrics, fallbacks, and invalidation.

### Common pitfalls

- Spring proxy-based caching is bypassed on **self-invocation** within the same bean.
- Default `CacheManager` may set no TTL or an unsuitable TTL.
- A `cacheName`/key lacking tenant isolation can leak data.
- Missing a cache error handler can turn a Redis outage into full API failures.
- Changing serializers between deployments breaks existing cached entries.

## 31. Microsoft Entra ID from Java: token refresh

When the Redis instance supports Entra auth, a secure connection follows:

~~~text
Java app on Azure
        |
        | Managed Identity / Workload Identity
        v
Microsoft Entra ID
        |
        | Access token with matching audience/resource
        v
Redis client AUTH in service-supported format
        |
        v
Redis data-plane permissions
        |
        v
Commands over TLS
~~~

### Implementation steps

1. Verify the Redis resource supports Entra auth and the corresponding user/account permissions.
2. Grant least-privilege data-plane permissions to the managed identity.
3. Use the Azure Identity SDK to acquire tokens for the resource scope required by the Redis service.
4. Use a Lettuce/Jedis integration supporting **AUTH, token renewal, and reconnect/re-auth**.
5. Test near token expiration and across Redis failovers.
6. Never print tokens or embed them in URLs or command lines.
7. Retire legacy access keys per migration plan once no longer needed.

### Why not show an AUTH command with a hardcoded token?

An access token acquired at startup expires. When it expires, the client cannot open new connections or gets challenged to re-authenticate. **Token lifecycle management is a mandatory part of secure connectivity**, not an optional detail. Furthermore, username mapping, audiences, and library integrations vary across Azure Redis products/tiers.

Therefore, use the Java library/integration recommended by the documentation for **your exact Redis service**, rather than pasting a token into a password field and letting the app run indefinitely.

## 32. Managed identity across Java hosting platforms

| Compute | Suggested identity | What to verify |
|---|---|---|
| App Service | System/user-assigned managed identity | Identity, Redis permissions, VNet integration |
| AKS | Microsoft Entra Workload ID | ServiceAccount federation, OIDC issuer, network policies |
| Azure Container Apps | Managed identity | Identity attachment, VNet ingress/egress |
| Azure VM | Managed identity | VM identity, NSGs/UDRs, endpoint routing |
| Local developer | Authorized developer identity | Correct tenant/subscription, no production privileges |

Managed identity **does not automatically grant Redis permissions**, open firewalls, fix DNS, or configure token-refresh integrations. Verify every layer.

## 33. Handling zero-downtime secret rotation

~~~text
App uses credential A
            |
            v
Issue credential B as supported by the resource
            |
            v
Update Key Vault / secret store
            |
            v
Roll out Java instances -> reconnect/auth with B
            |
            v
Verify Redis commands, logs, and error metrics
            |
            v
Revoke A per change plan
~~~

Not every Redis deployment offers **two active keys** or the same rotation workflow. Verify resource capabilities and never revoke the old key before updated apps have reconnected.

Errors to watch for:

- Key Vault updated, yet running processes cache the old secret.
- Rolling deployments open too many simultaneous connections.
- New Entra tokens carry the wrong audience or ACL mapping.
- New container instances lack Workload Identity federation.
- Secrets printed in deployment diffs or CI logs.

## 34. Redis caches and distributed locks

Redis can assist task coordination, but a TTL lock key does not guarantee absolute business exclusivity:

~~~text
Worker A acquires lock -> runs slow
        |
        v
Lock TTL expires
        |
        +--> Worker B acquires new lock
        |
        v
Worker A can still emit side effects
~~~

Critical workflows must evaluate **lock ownership tokens, lease renewal, fencing tokens, conditional writes, idempotency**, and the authoritative store. A Redis cache cannot replace SQL transactions or Cosmos DB optimistic concurrency with a single `SET NX`.

## 35. Redis in Azure real-time architectures

| Need | Service / capability to evaluate |
|---|---|
| Catalog/product lookup cache | Redis |
| Ephemeral signals between online processes | Redis Pub/Sub depending on requirements |
| Jobs needing ACK, retries, and DLQs | Azure Service Bus |
| Telemetry streams, partitions, and replay | Azure Event Hubs |
| Routing BlobCreated/resource events | Azure Event Grid |
| Real-time browser WebSockets | Azure Web PubSub / Azure SignalR Service |

Never push payment transactions onto Redis Pub/Sub assuming offline consumers will receive them later. Redis can assist real-time flows, yet durability, ordering, and recovery must match the right service.

## 36. Redis cost vs benefit

Cost factors:

- Redis SKU/tier, memory/compute, and availability options.
- Networking / Private Endpoints / data transfer.
- Monitoring and Log Analytics ingestion.
- Connections, TLS handshakes, and client CPU.
- Dataset/structure footprint, serialization overhead, and evictions.
- Azure SQL/Cosmos DB reads avoided thanks to caching.
- Operational effort, incident response, and migrations.

### Cache sizing math

Do not just sum JSON value bytes. Redis also uses memory for **keys, metadata, allocator overhead, internal data structures**, and fragmentation. A cache sitting at 95% RAM may lack headroom for writes, failovers, or spikes.

Scaling Redis capacity can help, yet inspect key cardinality, big keys, eviction policies, and TTLs first. Never pick a "safe guess" GB number and ignore metrics afterward.

## 37. Safe lab procedure: Java connecting to Redis on Azure

**Goal:** verify TLS, AUTH, and TTL-bounded lab key SET/GET in an authorized environment.

### Prerequisites

1. A lab Redis instance with verified product/tier.
2. Real FQDN, TLS port, and auth mode of that instance.
3. Java runtime with a valid network path.
4. Lab credentials or verified Entra integration.
5. Compatible Lettuce dependency; do not run Gradle commands from unrelated lesson repositories.
6. Scoped read access to logs and metrics.

### Steps

1. Record FQDN/port/auth mode—never write passwords into docs.
2. Test DNS from where the Java process actually runs.
3. Verify the TLS certificate/hostname.
4. Inject credentials via secret store or identity.
5. Run the Java Lettuce lab from section 11 (or the password-only variant if matching the auth mode).
6. Confirm SET/GET returns the expected value and the key carries a TTL.
7. Confirm the client prints no secrets and closes cleanly.
8. Inspect Redis command latency and connect/auth errors.
9. Simulate Redis unavailability **in the lab only** to verify timeouts and fallback.
10. Delete any remaining lab key or let TTL expire; never delete production resources.

### Acceptance table

| Check | Passing outcome |
|---|---|
| Host/port | Correct Redis instance and TLS port |
| DNS/private route | FQDN resolves/routes per architecture |
| TLS | Certificate chain/hostname verified |
| AUTH | Valid Redis data-plane permission |
| SET/GET | Expected lab value returned, TTL applied |
| Cleanup | Lab key expires or is deleted; client shuts down cleanly |
| Failure | Bounded timeouts; HTTP never hangs indefinitely |
| Logging | No tokens, passwords, or PII exposed |
| Monitoring | Connect/command latency and error counters active |

A single PASS **does not prove** token refresh, failover, cluster topology, high concurrency, or multi-region routing. Test those separately.

## 38. Case study: Java catalog API running on AKS

An enterprise deploys **catalog-api** across 20 Java pods on AKS:

- Azure SQL Database stores products and pricing.
- Redis caches public catalog data, never checkout prices.
- GET volume is dozens of times higher than UPDATE volume.
- Redis uses a Private Endpoint and allows TLS only.
- Workload Identity/Entra is preferred if supported by the resource.
- API p95 SLO is 200 ms.
- A Redis outage must not crash Azure SQL.
- Parts of catalog data vary by tenant.

### Tasks

1. Trace the request path from ingress through Java, Redis, and SQL.
2. Identify where TLS, DNS, and Private Endpoint apply.
3. Explain how to verify the exact Redis TLS port.
4. Choose the auth mode and describe token renewal if using Entra.
5. Explain how to grant Redis data-plane access to AKS Workload Identity.
6. Calculate potential connections if each pod has a max pool of 40.
7. Propose TTLs and invalidation when prices change.
8. Explain why checkout must verify prices from the authoritative source.
9. Design keys separating tenant and schemaVersion.
10. Choose Redis timeouts fitting a 200 ms p95 API SLO.
11. Design a circuit breaker and bounded DB fallback.
12. Name five meaningful metrics/alerts.
13. Describe zero-downtime credential rotation.
14. If real-time notifications are added, explain why Redis Pub/Sub is unsuitable for dispatching payment jobs.

### Solution outline

**Networking and security:** AKS pod → private DNS → Redis FQDN/Private Endpoint → TLS hostname verification → AUTH via refreshed managed identity tokens or authorized secret store.

**Caching:** cache-aside for public catalog, validated short TTLs, post-commit DB invalidation; tenant-specific entries enforce namespacing and authorization, while checkout reads authoritative data.

**Resilience:** tight Redis command deadlines, bounded retries, circuit breakers, single-flight, and capped DB fallback concurrency.

**Operations:** monitor hit rate, Redis p99, evictions, auth/connect failures, DB CPU/IO during cache outages, and monthly cost.

## 39. Common errors and how to resolve them

| Symptom | Likely cause | How to check |
|---|---|---|
| UnknownHostException | Wrong FQDN or private DNS | Resolve from a pod/VM in the target VNet |
| Connect timeout | Wrong port, firewall, NSG/UDR, endpoint | Check TCP path and TLS port |
| SSLHandshakeException | CA/truststore/hostname/SNI | Verify chain; never disable TLS |
| NOAUTH/WRONGPASS | Bad credential or Entra token/ACL | Confirm auth mode and permissions |
| Works initially then fails AUTH | Token expired without refresh or key rotated | Check token lifecycle and reconnection |
| Repeated MOVED/ASK | Mismatched client mode/topology | Verify Redis Cluster protocol |
| Too many connections | Client created per request or oversized pool | Calculate total pods × connections |
| Redis timeouts cause API 5xx | Missing fallback/circuit breaker | Enforce timeout budgets and graceful degradation |
| Low cache hit rate | Short TTL, fragmented keys, frequent invalidation | Measure hit rate by cache group |
| Cache returns another tenant's data | Missing tenant scope in key or missing authz | Security investigation; fix keys/authz |
| Database spikes when Redis fails | Cache stampede / unbounded fallback | Single-flight, DB concurrency cap |
| Evictions/OOM | Memory pressure, key explosion, oversized values | Inspect TTLs, sizing, Redis metrics |
| Old keys fail deserialization | Schema/serializer change | Key versioning and migration strategy |
| Tokens appear in logs | Overly verbose logging | Redact, run incident response, rotate |

### Six-step troubleshooting flow

1. **Resource:** confirm exact Azure Redis product/tier, FQDN, and port.
2. **Network:** DNS, Private Endpoint, VNet, NSGs/UDRs/firewalls.
3. **TLS:** certificate, SNI, hostname, JDK truststore.
4. **AUTH:** data-plane roles, access keys/ACLs, or token renewal.
5. **Client:** Lettuce/Spring versions, topology, connection pools, timeouts, reconnects.
6. **Business:** cache keys, TTL, consistency, fallbacks, tenant isolation.

Never modify production firewalls or enable trust-all before identifying which layer failed.

## 40. Production checklist

| Area | PASS criterion |
|---|---|
| Product lifecycle | Approved Redis type, SKU, and support/migration policy |
| Endpoint | Instance FQDN/TLS port; never hardcode IPs |
| Encryption | TLS enabled, verifying chain and hostname/SNI |
| Identity | Entra auth if supported, or tightly managed secrets |
| Token lifecycle | Refresh, re-auth, and reconnect tested |
| ACLs | Least-privilege data plane; admin/runtime separated |
| Secret handling | Key Vault/secret injection plus rotation/rollback |
| Networking | Private Endpoint/VNet/DNS/firewalls verified |
| Java runtime | Supported JDK/Lettuce/Spring versions |
| Client lifecycle | Reused clients, bounded pools, connection budgets |
| Resilience | Timeouts, bounded retry/backoff, circuit breakers |
| Fallback | Prevents DB stampedes; business-appropriate fail-open/closed |
| Cache model | Clear cache-aside, TTL, and invalidation design |
| Data isolation | Tenant-scoped key schema, authz checks, no PII logs |
| Serialization | Schema versioning, input validation, safe deserializers |
| Monitoring | Hit/miss, latency, connection errors, memory/evictions |
| Cost | Redis size/tier/network/monitoring weighed against DB savings |
| Drills | Tested cache outage, reconnect, secret rotation, failover |
| Runbook | Named owner, review cadence, and scoped key purge procedure |

## 41. Self-check questions

1. Why should a Redis cache never be the authoritative store for orders and balances?
2. How does a local in-JVM cache differ from shared Redis?
3. Do Azure Managed Redis and Azure Cache for Redis always use the same TLS port?
4. Why connect via FQDN rather than IP while preserving SNI/hostname verification?
5. Does Private Endpoint replace TLS?
6. How should a PKIX error be resolved?
7. Does a managed identity automatically grant Redis GET/SET permissions?
8. Can an Entra token be used indefinitely like a static password?
9. How do Redis ACLs differ from application-level end-user authorization?
10. Why must passwords never be placed in a Git-committed `application.yml`?
11. Should `RedisClient` be created per request or reused?
12. When are dedicated connections needed for blocking commands, transactions, or Pub/Sub?
13. How do connect timeouts differ from command timeouts?
14. Why can blindly retrying `INCR` corrupt data?
15. Does cache-aside have a race condition during DB updates and invalidation?
16. Does TTL replace cache invalidation?
17. When must a key schema distinguish tenant and version?
18. Why should key prefixes never serve as authorization?
19. What is a cache stampede?
20. Which types of data carry risk when using TTL jitter?
21. Why can a Redis outage trigger a database outage?
22. What do Redis Cluster `MOVED`/`ASK` responses indicate?
23. Why should `SELECT` DB indexes never be used as a security boundary?
24. How many potential connections can a 20-pod system with 40 connections/pod open?
25. Does a high cache hit rate prove cached data is correct?
26. How does Redis Pub/Sub differ from Azure Service Bus?
27. What risks does Java native serialization pose on untrusted Redis data?
28. Why doesn't Spring `@Cacheable` automatically solve business TTL and invalidation needs?
29. Which metrics should you inspect when Redis timeouts appear after a deploy?
30. What are the three most critical tests to run before production?

## References

- Microsoft Learn — *Azure Managed Redis*: https://learn.microsoft.com/azure/redis/
- Microsoft Learn — *Azure Cache for Redis*: https://learn.microsoft.com/azure/azure-cache-for-redis/
- Microsoft Learn — *Best practices for Azure Cache for Redis connections*: https://learn.microsoft.com/azure/azure-cache-for-redis/cache-best-practices-connection
- Microsoft Learn — *Microsoft Entra ID authentication for Azure Cache for Redis*: https://learn.microsoft.com/azure/azure-cache-for-redis/cache-azure-active-directory-for-authentication
- Microsoft Learn — *Azure Private Endpoint overview*: https://learn.microsoft.com/azure/private-link/private-endpoint-overview
- Microsoft Learn — *Azure Key Vault overview*: https://learn.microsoft.com/azure/key-vault/general/overview
- Microsoft Learn — *Microsoft Entra Workload ID on AKS*: https://learn.microsoft.com/azure/aks/workload-identity-overview
- Lettuce documentation: https://redis.github.io/lettuce/
- Spring Data Redis reference: https://docs.spring.io/spring-data/redis/reference/
- Spring Boot Redis configuration: https://docs.spring.io/spring-boot/reference/data/nosql.html#data.nosql.redis
- Redis documentation — *Security*: https://redis.io/docs/latest/operate/oss_and_stack/management/security/
- Redis documentation — *Caching*: https://redis.io/docs/latest/develop/use-cases/caching/
