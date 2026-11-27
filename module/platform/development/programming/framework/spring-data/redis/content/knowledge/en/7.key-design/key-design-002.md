# Designing Namespaces for Multiple Environments and Tenants in Spring Data Redis

When an application stores data in Redis, each key is a byte sequence used by Redis Server to identify a value. Redis does not inherently know whether a key belongs to the **development, staging, or production environment** or to a specific **tenant**. If applications write key names like `cart:42` or `session:123`, name collisions, reading the wrong data, or accidentally deleting another system's data can easily occur.

A **namespace** is a convention for embedding information about the system, environment, structural version, data scope, and tenant into the Redis key name. For example:

```text
shop:prod:v1:tenant:acme:cart:c-42
shop:prod:v1:tenant:beta:cart:c-42
shop:staging:v1:tenant:acme:cart:c-42
shop:prod:v1:global:feature:checkout
```

These four keys are distinct even though both tenants share cart ID `c-42`. Namespaces help applications identify and manage data consistently, yet **are not a security boundary**: Redis still treats each key as a name inside the same Redis database keyspace. Protecting data across tenants also requires application-level access checks and, when high isolation is required, separate Redis instances/clusters or appropriate access mechanisms.

In Spring Data Redis, namespaces must be accounted for on every read/write path: `StringRedisTemplate`, `RedisTemplate`, `RedisCacheManager`, Redis Repository, sessions, distributed locks, rate limiters, and background jobs. Adding a prefix to just a few `SET` calls will not produce a unified namespace architecture.

## 1. Why are namespaces needed?

Suppose an e-commerce service has:

- Three environments: `dev`, `staging`, `prod`.
- Two tenants: `acme` and `beta`.
- Multiple data types: product cache, shopping cart, login session, pricing results, and idempotency keys.
- One Redis Server serving multiple services or multiple environments.

If `cart:42` is used everywhere:

| Activity | Possible consequence |
|---|---|
| Dev overwrites production's `cart:42` | Production data is altered |
| Tenants `acme` and `beta` both use cart ID `42` | One tenant can see another tenant's data if the app accesses the key improperly |
| Cart service and payment service both use `lock:42` | Two business flows accidentally block each other |
| A software version changes the data type under the same key | Older versions hit format errors or overwrite data |
| A cache cleanup script deletes by an overly broad pattern | Deletes data outside the intended cleanup scope |

Namespaces solve the problem of **structured naming** and provide a foundation for scoped operations. They do not automatically control who is allowed to invoke Redis commands.

## 2. Recommended key naming model

A readable and extensible structure:

```text
<application>:<environment>:<schema-version>:<scope>:<tenant-id?>:<resource>:<object-id>
```

Here, `:` is a separator chosen by team convention, not a special Redis namespace syntax.

| Component | Purpose | Examples |
|---|---|---|
| `application` | Identifies the owning application/service | `shop`, `billing` |
| `environment` | Distinguishes deployment environments | `dev`, `staging`, `prod` |
| `schema-version` | Distinguishes format generation and key convention | `v1`, `v2` |
| `scope` | Indicates the data scope type | `tenant` or `global` |
| `tenant-id` | Tenant identifier within `tenant` scope | `acme`, `beta` |
| `resource` | Business entity type or data structure | `cart`, `product`, `rate-limit` |
| `object-id` | Object ID or operation target | `c-42`, `sku-100` |

Example for tenant-scoped data:

```text
shop:prod:v1:tenant:acme:cart:c-42
│    │    │  │      │    │    └── cart ID
│    │    │  │      │    └─────── data type
│    │    │  │      └──────────── tenant ID
│    │    │  └─────────────────── tenant-scoped data
│    │    └────────────────────── convention version
│    └─────────────────────────── environment
└──────────────────────────────── application owning the key
```

Example for shared data **within one environment**:

```text
shop:prod:v1:global:feature:checkout
shop:prod:v1:global:currency-rate:usd-vnd
```

Here, `global` simply means not belonging to a specific tenant; it **does not mean shared across environments**, nor is it implicitly public data.

### Consistency rules

1. Use one consistent casing and delimiter style, such as lowercase and `:`.
2. Define component order clearly; avoid `tenant:app:...` in one place and `app:tenant:...` in another.
3. For tenant-bound data, **tenant ID is mandatory**. Never silently omit the tenant when context is missing.
4. Do not place readable personal data such as emails, phone numbers, access tokens, or passwords into keys.
5. Separate the **resource** name from the **ID**; an object can share an ID with another resource without colliding.
6. Define specific conventions for auxiliary keys such as indexes, locks, counters, and format versions rather than inventing new prefixes in every service.

### Complete examples

| Purpose | Key |
|---|---|
| Cart for tenant `acme` | `shop:prod:v1:tenant:acme:cart:c-42` |
| Cart for tenant `beta` with the same ID | `shop:prod:v1:tenant:beta:cart:c-42` |
| Tenant's product | `shop:prod:v1:tenant:acme:product:sku-100` |
| Request count per tenant and user | `shop:prod:v1:tenant:acme:rate-limit:user-9` |
| Idempotency key for an order | `shop:prod:v1:tenant:acme:idempotency:req-7f1` |
| Environment feature flag | `shop:prod:v1:global:feature:new-checkout` |
| Same cart in staging | `shop:staging:v1:tenant:acme:cart:c-42` |
| Different service owning data | `billing:prod:v1:tenant:acme:invoice:inv-52` |

**Note:** If a data type truly belongs to a user inside a tenant, you can add a `user` level when needed, such as `shop:prod:v1:tenant:acme:user:u-9:preferences`. That is a data-modeling decision, not a reason to skip user authorization checks.

## 3. Distinguishing environments: prefixes vs. infrastructure isolation

There are three common deployment strategies:

| Strategy | Level of separation | Best suited for |
|---|---|---|
| Same Redis database, different prefix per environment | **Logical** separation by key name; shares RAM/CPU/network/config | Small test environments where resource sharing is acceptable |
| Same Redis instance, different Redis logical DB numbers | Separation by Redis DB in certain standalone modes; still shares resources and limits | Limited scenarios; not to be used as a security boundary |
| Dedicated Redis instance/cluster for production vs. other environments | Better isolation of config, resources, and operational blast radius | Production, critical data, strict deployment safety requirements |

**Recommendation:** Production should generally use a dedicated Redis instance/cluster separate from development and staging. Even with physical isolation, keep application and version prefixes to prevent collisions across services in the same environment and aid debugging.

Do not rely on `SELECT 1`, `SELECT 2` as a universally applicable namespace strategy: Redis Cluster uses DB 0 and does not support switching logical databases like traditional standalone Redis. Additionally, logical DBs on the same instance still share processing capacity, memory, eviction configuration, and administrative mistake risks.

### Deployment-based configuration

Spring Boot example:

```yaml
# application.yml
app:
  redis:
    namespace:
      application: shop
      environment: prod
      schema: v1

spring:
  data:
    redis:
      host: redis-prod.internal
      port: 6379
```

Values are illustrative; in real systems, `environment` and the Redis endpoint should come from deployment configuration or appropriate profiles. **Never hardcode `prod` in Java code**, never let a local profile accidentally point to production Redis, and never treat an environment name variable as proof of access permission.

When running multiple application instances belonging to the **same environment and structural version**, they must use the same namespace convention. If each instance appends its hostname or a random UUID to the prefix, instances will not share the cache as designed.

## 4. Multi-tenancy: tenant ID must be part of the data identity

A multi-tenant system may choose a dedicated database per tenant or multiple tenants sharing one Redis. With a shared model, keys need to include a **stable tenant ID**:

```text
shop:prod:v1:tenant:acme:cart:c-42
shop:prod:v1:tenant:beta:cart:c-42
```

Two keys with identical object names still do not collide thanks to the tenant ID.

However, **prefixes do not replace authorization**. If an application lets a user of `acme` pass `tenantId=beta` directly and constructs `beta`'s key name, they can still access the wrong data. Key separation is only effective when the system validates a trusted tenant context on the server side.

### Trusted source of tenant ID

In a web application:

1. Authenticate the request via session, access token, or an accepted identity mechanism.
2. From the authenticated identity, determine which tenants the user is authorized to access.
3. For operations allowing tenant selection, verify the user has permission on the selected tenant.
4. Only after that step pass the verified tenant ID into services/repositories and the key builder.

A request header such as `X-Tenant-Id` is **merely client-supplied input** if unverified. Do not take that header and concatenate Redis keys directly.

### Passing tenant explicitly into services

Design business methods to accept an already verified tenant:

```java
String saveCart(String authorizedTenantId, String cartId, String cartJson);
String findCart(String authorizedTenantId, String cartId);
```

This makes the tenant → data relationship immediately visible in the service API and safe to use in background tasks. If the application uses `ThreadLocal` to store the current tenant, pay special attention to async threads, thread pools, and WebFlux/Reactor: context may not propagate automatically across threads, causing lost or leaked tenants. Do not rely on a single global mutable tenant ID across requests.

### Tenant ID format

The tenant ID should be a **stable internal code containing no sensitive data and never reused for another tenant**. For example, `acme` or an opaque ID like `t-8f21`. Do not use a mutable company display name, administrator email, or domain name as the primary identifier.

Choose one of these two approaches and apply it consistently:

- **Restrict character set**: allow only `[a-z0-9_-]` with a defined length; use an ID normalized when the tenant is created.
- **Encode components**: if you truly must accept IDs containing special characters, use a deterministic, unambiguous encoding algorithm so delimiters inside the ID cannot alter the key structure.

Never concatenate raw user input—such as an email containing `:` or a string containing `*`—into key search or deletion tools. Wildcard characters and delimiters can cause out-of-scope operations if they appear in a `MATCH` expression.

## 5. Centralized key construction in Spring Data Redis

To ensure every service generates keys the same way, consolidate naming rules into a shared component. The examples below use Spring Boot 3.x, Java 21, and `StringRedisTemplate`.

### 5.1. Binding namespace configuration

```java
package com.example.shop.redis;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.redis.namespace")
public record RedisNamespaceProperties(
        String application,
        String environment,
        String schema
) {
}
```

Register this configuration with `@EnableConfigurationProperties`:

```java
package com.example.shop.redis;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(RedisNamespaceProperties.class)
public class RedisNamespaceConfiguration {
}
```

### 5.2. Key builder validating each component

```java
package com.example.shop.redis;

import java.util.regex.Pattern;
import org.springframework.stereotype.Component;

@Component
public final class RedisKeys {
    // Restrict component names for this learning example; production IDs need a clear contract.
    private static final Pattern COMPONENT =
            Pattern.compile("[a-zA-Z0-9_-]{1,64}");

    private final String root;

    public RedisKeys(RedisNamespaceProperties properties) {
        root = component(properties.application()) + ":"
             + component(properties.environment()) + ":"
             + component(properties.schema());
    }

    public String root() {
        return root;
    }

    public String tenant(String tenantId, String resource, String objectId) {
        return root + ":tenant:"
                + component(tenantId) + ":"
                + component(resource) + ":"
                + component(objectId);
    }

    public String global(String resource, String objectId) {
        return root + ":global:"
                + component(resource) + ":"
                + component(objectId);
    }

    public String cacheItem(String tenantId, String objectId) {
        // Used with RedisCacheManager's own prefix.
        return "tenant:" + component(tenantId) + ":id:" + component(objectId);
    }

    private static String component(String value) {
        if (value == null || !COMPONENT.matcher(value).matches()) {
            throw new IllegalArgumentException(
                    "Invalid Redis key component"
            );
        }
        return value;
    }
}
```

Examples:

```java
redisKeys.tenant("acme", "cart", "c-42");
// shop:prod:v1:tenant:acme:cart:c-42

redisKeys.tenant("beta", "cart", "c-42");
// shop:prod:v1:tenant:beta:cart:c-42

redisKeys.global("feature", "checkout");
// shop:prod:v1:global:feature:checkout
```

The example code only accepts components without `:`, `*`, or whitespace. If real-world IDs contain Unicode, dots, slashes, or other characters, decide on a **stable normalization/encoding method** instead of silently stripping characters. If IDs are overly long, use opaque IDs or an intentionally generated digest; ensure the encoding does not break any required reverse mapping to the business identifier.

Validating `tenantId` syntax **does not verify access rights**. It only prevents malformed keys. Authorization must still occur before using that tenant to read or write.

### 5.3. Using the same key builder for reads, writes, and deletes

```java
package com.example.shop.redis;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CartCache {
    private final StringRedisTemplate redis;
    private final RedisKeys keys;

    public CartCache(StringRedisTemplate redis, RedisKeys keys) {
        this.redis = redis;
        this.keys = keys;
    }

    public void save(
            String authorizedTenantId,
            String cartId,
            String cartJson
    ) {
        String key = keys.tenant(authorizedTenantId, "cart", cartId);
        redis.opsForValue().set(key, cartJson, Duration.ofMinutes(30));
    }

    public String find(String authorizedTenantId, String cartId) {
        String key = keys.tenant(authorizedTenantId, "cart", cartId);
        return redis.opsForValue().get(key);
    }

    public void delete(String authorizedTenantId, String cartId) {
        String key = keys.tenant(authorizedTenantId, "cart", cartId);
        redis.delete(key);
    }
}
```

Note that `cartJson` is just an illustrative string; in a real project, standardize serialization and data validation. The main point is that **all three operations go through the same key builder**, preventing scenarios where writes include the tenant while reads or deletes forget it.

### 5.4. Do not concatenate prefixes solely in the controller layer

A hard-to-maintain design:

```java
// Avoid letting each call site decide its own format:
redis.opsForValue().set("prod:cart:" + cartId, json);
redis.opsForValue().get("tenant:" + tenantId + ":cart:" + cartId);
redis.delete("cart:" + cartId);
```

Three statements produce three different key structures. As the system grows, the same service could operate on three separate copies of data without realizing it. A centralized key builder also enables a controlled transition from `v1` to `v2`.

## 6. Integrating namespaces with Spring Cache

When using `@Cacheable`, the final key name can be built from multiple parts: **cache name**, **cache key**, and the **key prefix** configured on `RedisCacheManager`. Therefore, you cannot assume the Redis key name will literally match the value passed to `@Cacheable(key = ...)`.

### 6.1. Configuring a fixed prefix for environment and cache

```java
package com.example.shop.redis;

import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class RedisCacheConfig {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory factory,
            RedisKeys keys
    ) {
        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                .computePrefixWith(cacheName ->
                        keys.root() + ":cache:" + cacheName + ":")
                .entryTtl(Duration.ofMinutes(10));

        return RedisCacheManager.builder(factory)
                .cacheDefaults(defaults)
                .build();
    }
}
```

Here, the prefix for the `priceByProduct` cache becomes:

```text
shop:prod:v1:cache:priceByProduct:
```

Because `RedisCacheManager` already adds the application/environment/version/cache-name prefix, the key generated by the `@Cacheable` method must still **include the tenant**.

### 6.2. Including the tenant in the cache key

```java
package com.example.shop.service;

import com.example.shop.redis.RedisKeys;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class PriceService {

    @Cacheable(
        cacheNames = "priceByProduct",
        key = "@redisKeys.cacheItem(#p0, #p1)"
    )
    public String loadPrice(
            String authorizedTenantId,
            String productId
    ) {
        // Query tenant-specific pricing from the primary data source.
        return loadFromPrimaryStore(authorizedTenantId, productId);
    }

    private String loadFromPrimaryStore(String tenantId, String productId) {
        // Illustrative code: a real application delegates to a repository/business service.
        return "price-for-" + tenantId + "-" + productId;
    }
}
```

With the configuration above, the Redis key for `loadPrice("acme", "sku-100")` looks like:

```text
shop:prod:v1:cache:priceByProduct:tenant:acme:id:sku-100
```

This is a valid variant of the namespace schema specifically for Spring Cache: **the cache name comes before the tenant scope** because `RedisCacheManager` builds the prefix at the cache level. This ordering must be documented and applied consistently across similar caches.

**Critical bug to avoid:**

```java
@Cacheable(cacheNames = "priceByProduct", key = "#p1")
public String loadPrice(String tenantId, String productId) { ... }
```

If two tenants both use `productId=sku-100`, they will share the same cache entry. For tenant-specific data, results could leak or show incorrect prices. Even strong authorization checks in the primary data source **cannot save you from a cache hit returning another tenant's result**, because the method body may not be executed on a cache hit.

The same applies to `@CachePut` and `@CacheEvict`: annotations reading, writing, and evicting the same cache must use compatible key calculations. If prices depend on currency, region, user type, or business variants, consider including those dimensions in the cache key or separating caches by context appropriately.

### 6.3. Do not assume the cache prefix changes per request

`computePrefixWith(cacheName -> ...)` is configured at the cache name level; the callback does not receive the authenticated tenant of each individual request. If you want a shared cache handling multiple tenants, include the tenant in the **key portion** generated by `@Cacheable` or write an appropriate `KeyGenerator`. Avoid pulling the tenant from a global variable or `ThreadLocal` lacking safe context propagation.

## 7. Namespaces when using Redis Repository

Redis Repository stores entities by keyspace and ID and may maintain auxiliary keys such as ID sets and secondary indexes. This mechanism must be handled explicitly; you cannot assume `@RedisHash` automatically uses the current tenant.

Example:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("orderViews")
public class OrderView {
    @Id
    private String id;

    @Indexed
    private String tenantId;

    private String orderNumber;

    // Constructors, getters, setters...
}
```

With keyspace `orderViews`, an entity with ID `42` from tenant `acme` and an entity with ID `42` from tenant `beta` will **collide** if sharing a Redis database. An ID-level solution is constructing a composite identifier:

```text
acme~42
beta~42
```

In this example, `~` is simply a separator chosen because both input components are constrained not to contain `~`. You can alternatively use globally unique opaque/UUID identifiers.

The repository will form corresponding keys like:

```text
orderViews:acme~42
orderViews:beta~42
```

Example interface:

```java
import java.util.List;
import org.springframework.data.repository.CrudRepository;

public interface OrderViewRepository
        extends CrudRepository<OrderView, String> {

    List<OrderView> findByTenantId(String tenantId);
}
```

With `@Indexed` on `tenantId`, Spring Data Redis can maintain a secondary index to look up `OrderView` records by tenant. However:

- `@RedisHash("orderViews")` is a static keyspace from entity metadata in this example; it **does not automatically turn into `orderViews:<tenantId>` per request**.
- ID sets and indexes managed by the repository may hold data from multiple tenants inside the same keyspace.
- Composite IDs reduce key collisions, but do not automatically enforce access policies. A call to `findById("beta~42")` must still undergo tenant authorization checks in the business layer.
- `findAll()` on a shared repository can return data across multiple tenants. Never expose it directly to the current tenant.
- Modifying data via direct Redis commands bypassing the repository can cause indexes to become stale.

If an application **must use a full namespace with environment/tenant directly in every repository key**, design dedicated keyspace/mapping configuration, ID schemes, and appropriate secondary indexes, or use `RedisTemplate` with a key builder for that dataset. Do not assume adding a `tenantId` parameter to a repository method changes the `@RedisHash` keyspace.

In multi-tenant production, the correctness of tenant isolation outweighs `CrudRepository` convenience. Evaluate when a shared repository is suitable versus when a dedicated Redis data model or isolated storage should be used.

## 8. Redis Cluster: hash tags affect namespaces

Redis Cluster distributes keys across **hash slots**. If a key contains a valid pair of curly braces `{...}`, the portion between the braces can be used as a **hash tag** to determine the slot.

Examples:

```text
shop:prod:v1:tenant:{acme}:cart:c-42
shop:prod:v1:tenant:{acme}:cart:items:c-42
shop:prod:v1:tenant:{beta}:cart:c-42
```

Keys with the same hash tag `{acme}` are placed into the same hash slot. This is useful when a multi-key operation, script, or Redis Cluster transaction requires participating keys to be on the same slot.

However, **do not mechanically wrap the entire tenant ID in `{...}` on every key**. If tenant `acme` has heavy traffic, every key carrying tag `{acme}` will pile into a single slot, easily creating a hotspot and degrading cluster data distribution.

Use hash tags only when there is a specific multi-key operation requirement. For example, to keep two keys of the same cart in the same slot:

```text
shop:prod:v1:tenant:acme:cart:{acme~c-42}:header
shop:prod:v1:tenant:acme:cart:{acme~c-42}:items
```

Both keys share tag `{acme~c-42}`. Other carts have different tags, allowing distribution across more slots. The contents inside the braces must still be derived from validated and normalized IDs.

**Remember:** Prefixes before `{...}` do not put two keys into the same slot if their hash tags differ. Conversely, identical hash tags share a slot even if the outer prefixes differ. Redis hash slots are a data routing mechanism, not a tenant access-control mechanism.

## 9. TTL, eviction, and per-tenant quotas

Namespaces identify who owns a key and what it is used for, but **do not automatically allocate dedicated memory or lifetimes** per tenant.

Examples:

```redis
SET shop:prod:v1:tenant:acme:cart:c-42 "{\"count\":2}" EX 1800
SET shop:prod:v1:tenant:beta:cart:c-42 "{\"count\":1}" EX 1800
TTL shop:prod:v1:tenant:acme:cart:c-42
```

Each key has its own TTL. Upon expiration, Redis handles expiry; if Redis has a `maxmemory` limit and an eviction policy, keys may be evicted due to memory pressure before their TTL expires. Redis does not inherently reserve "30 minutes per tenant".

| Need | How to handle |
|---|---|
| Cart must expire after 30 minutes | Set TTL on the cart key when writing |
| Cache of recomputable data | Set TTL, handle cache misses, and monitor eviction |
| Large tenant must not exhaust RAM of other tenants | Design application-level quotas/data limits, monitor per tenant, or separate Redis instances |
| Per-tenant rate limiting | Use a key containing tenant ID, update counters and TTL per the algorithm |
| Tokens/sessions must expire per policy | Ensure TTL or application-level expiration logic; handle premature key loss |

Redis `maxmemory-policy` generally applies at the Redis instance level and **is unaware of which prefix segments correspond to tenants**. One tenant creating excessive keys can trigger eviction of another tenant's keys when sharing memory. If strict quotas or independent resources are required, add enforcement mechanisms or infrastructure isolation rather than just prefixes.

## 10. Safely deleting data by namespace

When you need to clear a tenant's cache or clean up staging keys, ensure the **scope** is exact. Any cleanup command can cause disruption, so test in an appropriate environment and estimate key counts before acting.

### 10.1. Inspecting with `SCAN`

Instead of `KEYS *` on a large Redis, iterate with a cursor using `SCAN`:

```redis
SCAN 0 MATCH shop:staging:v1:tenant:acme:* COUNT 100
```

Redis returns a new cursor and a batch of keys. Continue `SCAN <cursor> ...` until the cursor returns `0`. `COUNT` is a hint for work per iteration, not a guarantee of returning that exact number of keys.

`SCAN` does not produce a consistent snapshot: data can change during scanning, a key may appear across multiple iterations, and not every call returns keys. In Redis Cluster, full traversal must run across the nodes holding relevant keys; scanning one node does not represent the whole cluster.

When only statistics are needed, avoid reading the values of all keys unnecessarily; use metrics, business-level counts, or appropriate tracking structures.

### 10.2. Deleting individual keys, in batches, scoped to the right tenant

For a specific key, you can call:

```java
redisTemplate.delete(redisKeys.tenant("acme", "cart", "c-42"));
```

For thousands of keys belonging to a tenant, a job can iterate with `SCAN` and use `UNLINK` or controlled batched deletes. Rate-limit the work and carefully verify the target Redis; `UNLINK` reclaims memory asynchronously on the Redis side while removing keys logically right away.

Never use `FLUSHDB`, `FLUSHALL`, or an overly broad pattern to clean up a single tenant on a shared Redis. No matter how well key prefixes are designed, `FLUSHDB` and `FLUSHALL` have no awareness of application namespaces.

### 10.3. When large frequent cleanups are needed

Scanning the entire keyspace can be expensive at large data volumes. Consider:

- Using TTL so short-lived keys expire automatically.
- Maintaining a tracking set of keys belonging to a tenant if explicit lifecycle management is required; keep metadata synchronized on writes/deletes.
- Using version/generation in keys for rebuildable caches, switching reads to the new namespace instead of deleting all old keys immediately, and letting TTL drain old entries.
- If a tenant holds huge data volumes or has strict independent deletion requirements, consider separate Redis instances or a different data ownership model.

Tracking sets can also become stale if keys expire or get evicted. If using them to purge all tenant data, design metadata cleanup and memory bounds carefully; do not treat a tracking set as absolute proof of every currently existing key.

## 11. Schema upgrades and namespace migration

Namespaces often need to change when data structures change. For example, `v1` stores a cart as a JSON string, whereas `v2` stores carts as hashes or changes pricing logic. If you only change code while keeping the same key name, new releases can hit Redis `WRONGTYPE` errors or read data under the old schema.

A controlled strategy:

```text
Old version:
shop:prod:v1:tenant:acme:cart:c-42

New version:
shop:prod:v2:tenant:acme:cart:c-42
```

Steps applicable depending on business needs:

1. **Define the new schema:** specify `v2` in the key, value format, TTL, and how indexes are handled.
2. **Implement appropriate reading:** for rebuildable caches, try `v2` and on cache miss compute from the authoritative source. For data requiring migration, design `v1` reading and conversion with tenant authorization checks.
3. **Switch write routing:** new application instances write to `v2`; prevent older versions from overwriting incompatible data.
4. **Monitor cutover:** track cache hit/miss rates, deserialization errors, memory usage, and remaining `v1` data ratio.
5. **Clean up `v1`:** let TTL expire or run a controlled deletion task once certain no consumers still use the old format.

If using **dual-write** during transition, define which data is authoritative, how to handle one write succeeding while the other fails, and how to avoid reading inconsistent states. Dual-write does not automatically provide atomicity across two keys.

For cache-only data, **namespace versioning + cache miss rebuild** is usually simpler than converting every key. For non-rebuildable business data, a full migration plan and a reliable primary store are required.

Another simple approach is adding a generation to the cache:

```text
shop:prod:v1:tenant:acme:cache-g3:product:sku-100
shop:prod:v1:tenant:acme:cache-g4:product:sku-100
```

When switching generations, the app reads namespace `g4` and ignores `g3`. This enables group invalidation, though it can increase memory during overlap; TTL and old-generation cleanup must still be managed.

## 12. Multi-environment, multi-tenant observability and troubleshooting

When a key is "not found", first verify the **actual key** the application sent to Redis rather than looking only at the business ID:

```text
application = shop
environment = staging
schema = v1
tenant = acme
resource = cart
id = c-42
result = shop:staging:v1:tenant:acme:cart:c-42
```

Common issues:

| Symptom | Likely causes to check |
|---|---|
| Data exists locally but cannot be read in staging | Different environment/endpoint/DB/prefix |
| Tenant A reads Tenant B's data | Missing tenant in cache key, unvalidated tenant from input, or authorization bug |
| Repository `findById` returns another tenant's object | ID lacks tenant and there is no corresponding permission check |
| Many cache misses appear after deployment | Schema version/generation changed, cache prefix changed, or TTL expired |
| Cleared tenant cache but some keys remain | `SCAN` did not finish all cursors, missed other key/index types, or concurrent writes occurred |
| Redis is full despite tenant-prefixed keys | Prefixes do not create quotas; check TTL, eviction, key counts, and key sizes |
| Redis Cluster reports cross-slot errors | Keys in multi-key operations have different hash slots |
| Multiple environments affect each other's performance | Environments are sharing physical Redis infrastructure |
| Key version changed but old app still reads old keys | Rolling deployments need compatibility windows or clear cutover plans |

### Logging and metrics

For troubleshooting, log **non-sensitive** components such as application, environment, resource, cache hit/miss status, and appropriately encoded or masked internal tenant IDs. Do not log raw keys containing tokens/PII. Avoid putting high-cardinality tenant IDs into every metric label; time-series counts can explode. For high-priority tenants or dedicated analysis, use logs or summary tables outside aggregate metrics.

Also monitor:

- Total keys, memory, evictions, and expirations on Redis Server.
- Hit/miss rates and latency by cache/resource.
- Data size and growth rate per tenant if the system has an appropriate statistics mechanism.
- Errors from namespace mismatches, tenant permissions, or incompatible Redis types.
- Outcomes of cleanup/migration jobs, especially the scope of scanned keys.

## 13. What namespaces cannot solve

### 13.1. Namespaces do not automatically enforce Redis ACLs

Redis ACLs can restrict commands and key patterns when configuring Redis users, but a prefix inside a key name **does not automatically activate ACLs**. If an application uses one Redis credential authorized to read all keys, an application bug can still allow cross-tenant access.

To isolate permissions at the Redis level, design appropriate users/credentials, access patterns, connection lifecycles, and deployment scopes. A single application sharing one connection across thousands of tenants generally cannot treat prefixes as a substitute for per-request authorization checks.

### 13.2. Namespaces do not automatically limit tenant CPU/RAM

Redis does not parse `:tenant:acme:` to enforce separate quotas. Tenants on the same instance can still impact each other across RAM, CPU, network, and eviction policies. For strict isolation or independent performance SLAs, consider dedicated instances/clusters or resource limits outside Redis.

### 13.3. Namespaces do not replace data modeling

For instance, merely naming a key `shop:prod:v1:tenant:acme:order:42` does not guarantee that:

- Order creation occurs only once.
- Multi-key updates are always atomic.
- Critical events are never lost.
- A tenant does not exceed an order limit.
- Data can be recovered after infrastructure failure without proper persistence/backups.

These guarantees must be designed at the business layer, in Redis algorithms, transactions/scripts, persistence mechanisms, or infrastructure.

## 14. Hands-on exercise: two tenants, two environments

You can practice this on a dedicated learning Redis.

### Step 1 — Create keys with the same object ID

```redis
SET shop:dev:v1:tenant:acme:cart:c-42 "dev-acme" EX 120
SET shop:dev:v1:tenant:beta:cart:c-42 "dev-beta" EX 120
SET shop:staging:v1:tenant:acme:cart:c-42 "staging-acme" EX 120
```

### Step 2 — Read each scope

```redis
GET shop:dev:v1:tenant:acme:cart:c-42
GET shop:dev:v1:tenant:beta:cart:c-42
GET shop:staging:v1:tenant:acme:cart:c-42
```

All three commands return three different values despite sharing the same cart ID. When TTL expires, Redis removes each key independently.

### Step 3 — Inspect namespaces

```redis
SCAN 0 MATCH shop:dev:v1:tenant:acme:* COUNT 100
SCAN 0 MATCH shop:staging:v1:* COUNT 100
```

If the returned cursor is not `0`, continue scanning with subsequent cursors to traverse everything. Do not use the result of a single `SCAN` call as proof that a namespace has only a few keys.

### Step 4 — Verify with Spring

Create `RedisKeys` as shown above, then use `CartCache.save("acme", "c-42", ...)` and `CartCache.find("acme", "c-42")`. Change the `environment` config from `dev` to `staging` in a separate run on your learning Redis to observe how changing the prefix changes which key is accessed.

To test tenant isolation, try `save("acme", "c-42", "A")` and `save("beta", "c-42", "B")` and read them back respectively. Both values must reside under two different keys. Try passing a `tenantId` containing `:` and confirm it is rejected by the key builder according to the example's naming contract.

### Step 5 — Try the version convention

Additionally create:

```redis
SET shop:dev:v2:tenant:acme:cart:c-42 "new-format" EX 120
GET shop:dev:v1:tenant:acme:cart:c-42
GET shop:dev:v2:tenant:acme:cart:c-42
```

Both versions can coexist; the application decides which version to read and when to clean up old data.

## 15. Production project checklist

When building a multi-tenant Spring Data Redis module, standardize and enforce these rules in code:

1. **One published key schema:** `application:environment:version:scope:tenant:resource:id`, with intentional exceptions for caches/repositories.
2. **No tenant keys without a tenant ID:** every API reading/writing/deleting tenant data accepts a verified tenant.
3. **One shared key builder:** do not scatter string-concatenation logic across controllers, services, and scheduled tasks.
4. **Control characters and length:** key components use an unambiguous format; never embed personal data or secrets.
5. **Separate namespaces from access control:** Spring Security/authorization decides who may use a tenant; prefixes only locate keys.
6. **Intentional TTL and retention:** every resource type defines its lifetime, rebuildability, and missing-key handling.
7. **Define invalidation mechanisms:** `@CacheEvict`, cleanup jobs, and data mutations all follow the same convention.
8. **Account for infrastructure limits:** critical production workloads should have dedicated Redis; prefixes do not create quotas or fault isolation.
9. **Preserve compatibility across schema changes:** use versions/generations and rollout plans rather than changing data formats under the same key uncontrolled.
10. **Observe within safe boundaries:** log appropriate metadata, track cache misses/evictions, and keep secrets out of key names.

### Conceptual summary

A namespace is a **naming contract** across components using Redis:

```text
Application authenticates tenant
           │
           ▼
Service receives authorizedTenantId
           │
           ▼
Key builder: app + env + version + tenant + resource + ID
           │
           ├── RedisTemplate / StringRedisTemplate
           │
           ├── RedisCacheManager + tenant-aware cache key
           │
           └── Redis Repository (check keyspace and ID carefully)
           │
           ▼
Redis Server: keys reside in the same Redis database/cluster
```

With namespaces, services and tenants avoid name collisions and manage data lifecycles in an organized manner. Access permissions, memory quotas, transactions, and durability still require dedicated mechanisms.

## 16. Self-check questions

**1. Why is using just `cart:<id>` unsuitable for a multi-tenant application?**  
Because an ID unique within one tenant can collide with an ID in another tenant, causing two objects to share the same Redis key.

**2. On the same Redis instance, if dev uses `shop:dev:...` and prod uses `shop:prod:...`, are they completely isolated?**  
No. Namespaces separate keys at the naming level, yet both still share memory, CPU, Redis configuration, permissions of the active credential, and administrative operation risks.

**3. Why can `@Cacheable(key = "#p1")` be dangerous when the method receives `tenantId` and `productId`?**  
Because the cache key contains only the product ID. Two tenants with the same product ID can share a cache entry; furthermore, a cache hit skips executing the method body, where data-retrieval logic typically resides.

**4. Does `@RedisHash("orders")` automatically create a tenant prefix for a Redis Repository?**  
No. The keyspace is declared as static metadata in the example; you must design IDs, mappings/indexes, permission checks, and/or specialized keyspace configurations.

**5. Does Redis Cluster require adding `{tenantId}` to every key?**  
No. Hash tags are useful for multi-key operations needing the same slot, but packing all keys of a large tenant into a single slot can create a hotspot.

**6. Can all data for tenant `acme` be deleted with `FLUSHDB` just because prefixes are used?**  
No. `FLUSHDB` deletes all keys in the Redis logical database without filtering by prefix. You must design controlled, key-scoped cleanup tasks that account for shared infrastructure impact.

**7. Does switching from `v1` to `v2` mean old data has disappeared?**  
No. Both namespaces can coexist until TTLs expire or a cleanup task runs; the deployment must define which version is read and the transition plan.

**8. Why is validating the tenant ID format still not enough for security?**  
Because a syntactically valid ID like `beta` may still be a tenant the current user is not permitted to access. Identity and permissions must be verified before building keys.

**Core takeaway:** Design Redis namespaces as an explicit contract, enforced uniformly with Spring Data Redis and bound to a verified tenant. Prefixes distinguish data; access control and resource isolation remain separate responsibilities of the application and deployment architecture.
