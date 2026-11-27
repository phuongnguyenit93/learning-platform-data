# Naming Keys by Application, Business Domain, and Identifier in Spring Data Redis

Redis stores data by **key** and **value**. For a small application, names like `user:1` or `cart:5` might seem clear enough. However, when multiple services, deployment environments, and data groups share Redis, short keys lacking context soon become a source of confusion: two applications overwrite each other's data, the same key name is used for two different Redis data types, it becomes hard to tell who owns the data, and migrating when the system structure changes becomes very difficult.

In Spring Data Redis, key naming design is an **architectural convention**: the key name should clearly state *which application owns it*, *which business domain it belongs to*, *what type of data it represents*, and *which specific object identifier it refers to*. This convention should be consistent across `RedisTemplate`, `StringRedisTemplate`, Spring Cache, Redis Repository, and any other component writing data to the same Redis.

This lesson builds naming rules from basic components, applies them in Java, distinguishes namespaces from true isolation, and explains how to maintain key contracts when using Redis Cluster or when schema changes are needed.

## 1. Why is the key name part of system design?

Redis does not have tables and schemas in the way relational databases do. A Redis string, a Redis hash, and a Redis set are all accessed through a key name. Redis can report what data type a key holds, but **does not inherently know** which service owns that key or what business meaning it carries.

For example, in an e-commerce system:

```text
Catalog service:
    user:42     -> user recently viewed a product

Identity service:
    user:42     -> user login information

Checkout service:
    user:42     -> current shopping cart
```

If all three services point to the same Redis DB and write the same name `user:42`, one can overwrite another's value. The outcome depends on write order; readers may also encounter a `WRONGTYPE` error or deserialization error because the value no longer matches the expected format.

Naming with sufficient context avoids confusion:

```text
shop:prod:catalog:recent-view:u42
shop:prod:identity:profile:u42
shop:prod:checkout:cart:u42
```

From the key, operators can recognize three independent data groups, even though they all relate to user `u42`. Key names also help troubleshoot incidents, define observability rules, choose appropriate ACL patterns, and plan migrations.

**Principle:** A key should have a single owner and a clear business meaning. If two applications intentionally share a key, the data format, write permissions, TTL, and schema change process must be an agreed-upon contract.

## 2. Recommended structure: application → environment → domain → type → identifier

An easy-to-apply rule for a multi-service system is:

```text
<application>:<environment>:<domain>:<entity-or-purpose>:<identity>
```

Examples:

```text
shop:prod:catalog:product:p42
shop:prod:checkout:cart:c817
shop:prod:orders:order:o2026-1201
shop:staging:identity:session:s912
```

| Component | Answers the question | Examples |
|---|---|---|
| `application` | Which system or application does the data belong to? | `shop`, `billing`, `learning` |
| `environment` | Which runtime environment does the data belong to? | `dev`, `staging`, `prod` |
| `domain` | Which business domain or bounded context owns it? | `catalog`, `checkout`, `identity`, `orders` |
| `entity-or-purpose` | What is the entity type or storage purpose? | `product`, `cart`, `session`, `rate-limit` |
| `identity` | Which specific record/object is it? | `p42`, `c817`, `s912` |

The business domain name should reflect the **ubiquitous business language shared by the development team**, rather than arbitrary Java class names. For instance, `checkout:cart` is more durable than `CartRedisServiceImpl`, because class names can change during refactoring while shopping cart semantics remain the same.

There is no mandatory namespace syntax enforced by Redis. The `:` character is simply a common convention in key names that helps humans and tools recognize groups. Redis treats the entire key string as a binary identifier; it **does not automatically create folders or database boundaries** for each `:`.

### When should components be added or removed?

The structure above is a template, not a mandatory law for every key type. It can be extended purposefully:

```text
# Add tenant when the system is multi-tenant.
shop:prod:t27:orders:order:o501

# Add version when data representation changes incompatibly.
shop:prod:catalog:product:v2:p42

# Add sub-components for keys related to one object.
shop:prod:checkout:cart:c817:items
shop:prod:checkout:cart:c817:total

# Key representing a global state of a domain, without an entity ID.
shop:prod:catalog:sync:last-success
```

For keys not tied to an entity, the final part still needs to be a **sufficiently clear functional identifier**, such as `last-success`, `leader`, or `sequence`. Do not force a dummy ID like `0` if it has no meaning.

Choose a stable component order across the entire system. Using `shop:prod:orders:order:o501` in one place and `orders:shop:o501:prod` in another makes pattern-based key searches and ownership management harder.

## 3. Defining application and business domain boundaries

**Application** defines ownership boundaries at the product/system level. **Business domain** defines data boundaries within an application or between bounded contexts belonging to the same system.

For example, a company has two independent systems:

```text
shop:prod:billing:invoice:inv1001
crm:prod:billing:invoice:inv1001
```

They might both call the object `invoice` and both use ID `inv1001`, which does not mean the two records are the same. The prefixes `shop` and `crm` eliminate name collisions.

Within the `shop` system, domains can also share entity names:

```text
shop:prod:identity:token:t55
shop:prod:payments:token:t55
```

Login tokens and payment tokens do not share the same semantics, TTL, or security conditions. The `domain` segment helps distinguish them even when `entity` or `identity` happens to match.

In a microservices architecture, you can consistently choose one of two approaches:

- All services of the same product use a unified application prefix and then add the domain, e.g., `shop:prod:catalog:...`.
- Independently deployed systems use separate application prefixes, e.g., `catalog-api:prod:...` and `payment-api:prod:...`.

The priority is determining **who actually owns write permissions and the data lifecycle**. A key owned by the `orders` service should not be arbitrarily modified by the `catalog` service just because both have access to Redis.

### Do not name keys after implementation class names

Names like the following easily become outdated:

```text
ShopController:product:42
ProductServiceImpl:42
com.example.shop.model.Product:42
```

They depend on source code structure and can become overly long. When packages are renamed or code is refactored, old key names remain in Redis while no longer being accessed by the new code. Prefer stable meaning such as `shop:prod:catalog:product:p42`.

## 4. Identifier: one object must have one consistent representation

The final segment of the key name identifies the **specific record**. ID selection rules directly affect uniqueness and the ability to read data back.

For example, the original product ID is the number `42`. If service A uses `42` while service B uses `00042`, Redis treats these as two different keys:

```text
shop:prod:catalog:product:42
shop:prod:catalog:product:00042
```

Similarly, `P42` and `p42` are different because Redis keys are case-sensitive. A UUID with hyphens and a UUID without hyphens are two different strings. Therefore, you must standardize how IDs are canonicalized **right at the application boundary**.

Common choices:

| Identifier type | Example | Notes |
|---|---|---|
| Business integer | `42` | Specify whether zero-padding is used; avoid arbitrary ID reuse |
| Standard UUID | `8be0b730-85cd-4f2b-b82a-5ef09ca79e37` | Standardize lowercase and hyphens |
| ULID or stable code | `01JC5R4M7D8VY6Q9G2PEAC7Z0M` | Must preserve canonical format; do not arbitrarily change case |
| Tenant-scoped ID | `t27:o501` in separate segments | Put tenant in the namespace to avoid ID collisions across tenants |
| Email or username | `an@example.com` | Avoid putting personal information in key names; use an opaque ID |

Identifiers used in keys must remain stable for the lifetime of the data. If you use a mutable username instead of an immutable user ID, every username change can leave orphaned old keys behind or create two coexisting versions.

### Separate user IDs from personal data

Do not write:

```text
shop:prod:identity:session:an@example.com
shop:prod:customer:profile:+84901234567
shop:prod:auth:token:eyJhbGciOi...
```

Key names can appear in command traces, metrics, backups, and administrative tools. Instead:

```text
shop:prod:identity:session:s912
shop:prod:customer:profile:u42
shop:prod:auth:token-ref:trf928
```

These IDs should be system-generated/managed and must not expose secrets. When lookup by email or phone number is needed, handle it through a controlled data/mapping layer and do not allow sensitive information to appear arbitrarily in keys.

## 5. Choosing character and key length rules

Redis allows keys to contain binary data and does not restrict key names to ASCII. However, for multi-service systems requiring operational visibility, **structured, readable UTF-8 text keys** are usually the convenient choice.

Recommended conventions:

- Use lowercase for system-controlled segments such as `shop`, `prod`, `catalog`, `product`.
- Use `:` to separate components; use `-` inside compound-word components, e.g., `rate-limit`.
- Normalize identifiers according to the source contract; avoid arbitrarily lowercasing a case-sensitive ID.
- Do not let `null`, empty strings, or whitespace become a key segment without explicit meaning.
- Do not concatenate raw user-supplied strings directly into a key if they may contain delimiters or control characters; validate or encode the ID segment using a deterministic rule.
- Keep keys concise enough for operations; overly long prefixes repeated millions of times consume memory and bandwidth.

For example, a delimiter inside an ID can make the key structure ambiguous:

```text
shop:prod:catalog:product:region:42
```

Here, is `region:42` one ID or two different components? The application convention must decide. If an ID can contain arbitrary characters, encode **only the ID segment** deterministically—such as unpadded URL-safe Base64—or use a system-assigned opaque ID. Readers must decode according to the same contract; do not use an encoding that changes between deployment versions.

**Key length:** Redis allows long keys, but very long keys cause memory, network, and logging overhead. A key like `shop:prod:catalog:product:p42` is longer than `p42`, in exchange for clearer operations and collision avoidance. Do not optimize to the point of losing ownership information, yet also avoid embedding JSON, stack traces, or long payloads in key names.

## 6. Naming by Redis data type and access purpose

A business entity can be stored in multiple models: a Redis string containing JSON, a Redis hash with multiple fields, a Redis set containing related IDs, a Redis sorted set containing rankings, etc. The key name should convey **the purpose and logical structure**, though it does not necessarily need to repeat words like `string` or `hash` in the name.

Examples for a retail system:

| Key | Redis type | Content | Suggested lifecycle |
|---|---|---|---|
| `shop:prod:catalog:product:p42` | String | Cached product JSON information | TTL per cache policy |
| `shop:prod:checkout:cart:c817` | Hash | Current shopping cart fields | Shopping cart session TTL |
| `shop:prod:identity:session:s912` | String or Hash | Session state | Short TTL per session policy |
| `shop:prod:catalog:popular-products` | Sorted set | Product IDs and ranking scores | Updated per statistics strategy |
| `shop:prod:orders:pending-ids` | Set | Set of pending order IDs | Business-dependent; do not delete arbitrarily |
| `shop:prod:limits:user:u42` | String | Counter enforcing user rate limit | TTL per limit window |

These Redis types are illustrative design choices; Redis does not infer the type from the key name. When there are multiple distinct access patterns on the same entity, you can add suffixes to distinguish related keys:

```text
shop:prod:checkout:cart:c817:items
shop:prod:checkout:cart:c817:total
shop:prod:checkout:cart:c817:updated-at
```

However, if those three values are fields of the **same Redis hash**, they can share a single Redis key `shop:prod:checkout:cart:c817` with hash fields `items`, `total`, `updatedAt`. Do not create multiple keys merely because there are multiple Java properties. Choose the storage model first, then name keys to match that model.

### Avoid using the same key for multiple Redis types

For example:

```redis
SET shop:prod:catalog:product:p42 '{"name":"Notebook"}'
HSET shop:prod:catalog:product:p42 price 120000
```

The `HSET` command is incompatible with a key that currently holds a Redis string and typically returns `WRONGTYPE Operation against a key holding the wrong kind of value`.

If you want to switch from a JSON string to a Redis hash, treat it as a key schema/lifecycle change. Use a new versioned name for a controlled transition rather than trying to reuse the old key while two application versions are running simultaneously.

## 7. Deployment environments: `dev`, `staging`, `prod`

If environments run on the same Redis instance or Cluster (primarily suited for controlled testing scenarios), an environment prefix helps reduce the risk of key collisions:

```text
shop:dev:catalog:product:p42
shop:staging:catalog:product:p42
shop:prod:catalog:product:p42
```

Thus, a `SET` operation in dev does not directly overwrite a prod key name. However, **a prefix does not provide isolation for CPU, RAM, network, eviction policies, or access permissions**. A dev environment writing too many keys can still put pressure on a Redis shared with production.

If production requires independent availability, access control, and resource limits, provision a **dedicated Redis deployment**. Environment prefixes remain useful there for data provenance transparency, though they are not the primary protection mechanism.

Do not hard-code `prod` in source code and deploy the same artifact to staging. Put the application/environment portion into deployment-provided configuration and build keys centrally in the storage layer.

## 8. Multi-tenancy: add tenant when identifiers are not globally unique

In SaaS, each customer (tenant) may have identical `orderId` values. If you name keys solely by order ID:

```text
shop:prod:orders:order:501
```

then two tenants both having order `501` will collide. You can place the tenant in a consistent position:

```text
<application>:<environment>:<tenant>:<domain>:<entity>:<identity>

shop:prod:t27:orders:order:501
shop:prod:t91:orders:order:501
```

The tenant ID should be a stable system-assigned identifier, not necessarily a mutable company name. When an app is not multi-tenant, avoid inserting a `tenant:default` segment into every key solely out of anticipation for the future.

Crucially, **the tenant must be determined from a trusted authentication/authorization context**. Do not accept a tenant string from a request and arbitrarily build a key to read another tenant's data. Prefixes are key organization tools; access rights must be enforced at the application layer and supplemented with dedicated Redis ACLs/credentials where appropriate.

### Tenants and data deletion policies

Having a tenant namespace helps list keys to evaluate when deleting a tenant's data:

```text
shop:prod:t27:orders:*
shop:prod:t27:checkout:*
shop:prod:t27:identity:*
```

However, do not treat wildcards as an unconditionally safe deletion operation. Beyond direct keys, the system may have secondary indexes, streams, delayed jobs, shared caches, repository metadata, and other keys that do not follow the pattern above. A tenant deletion workflow must account for **every component owning data**, retention requirements, and the possibility of concurrent writes.

## 9. Java example: a unified key builder class

Spring Data Redis does not force applications to name keys under a single schema. To avoid scattered string concatenation across services, you can create a dedicated key builder class.

Example application configuration:

```yaml
# application.yml
app:
  redis:
    namespace: shop:dev

spring:
  data:
    redis:
      host: localhost
      port: 6379
```

`app.redis.namespace` is an **application-defined custom property**, not a built-in standard Spring Data Redis property. Redis connection configuration still belongs under `spring.data.redis.*`.

Key builder class:

```java
package com.example.shop.redis;

import java.util.Objects;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public final class ShopRedisKeys {
    private static final Pattern ID_PATTERN =
            Pattern.compile("[A-Za-z0-9_-]+");

    private final String namespace;

    public ShopRedisKeys(@Value("${app.redis.namespace}") String namespace) {
        if (!namespace.matches("[a-z0-9-]+:[a-z0-9-]+")) {
            throw new IllegalArgumentException("Invalid Redis namespace");
        }
        this.namespace = namespace;
    }

    public String product(String productId) {
        return namespace + ":catalog:product:v1:" + segment(productId);
    }

    public String cart(String cartId) {
        return namespace + ":checkout:cart:v1:" + segment(cartId);
    }

    public String session(String sessionId) {
        return namespace + ":identity:session:v1:" + segment(sessionId);
    }

    private static String segment(String input) {
        Objects.requireNonNull(input, "Redis key ID cannot be null");
        if (!ID_PATTERN.matcher(input).matches()) {
            throw new IllegalArgumentException("Invalid Redis key ID");
        }
        return input;
    }
}
```

This example adopts a policy of **rejecting** IDs containing characters outside the allowed set, preventing the key structure from being altered by `:` or control characters in input. If business IDs are hyphenated UUIDs, the pattern above accepts them; if IDs are emails, strings with `:`, or Unicode, agree on a canonical encoding before calling the key builder rather than removing validation. There is no single regex suitable for every system.

When switching environments:

```text
app.redis.namespace=shop:staging
    product("p42") -> shop:staging:catalog:product:v1:p42

app.redis.namespace=shop:prod
    product("p42") -> shop:prod:catalog:product:v1:p42
```

Services storing and reading data simply call the same key builder:

```java
package com.example.shop.redis;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheStore {
    private final StringRedisTemplate redis;
    private final ShopRedisKeys keys;

    public ProductCacheStore(StringRedisTemplate redis, ShopRedisKeys keys) {
        this.redis = redis;
        this.keys = keys;
    }

    public void cacheJson(String productId, String productJson) {
        redis.opsForValue().set(
                keys.product(productId),
                productJson,
                Duration.ofMinutes(15));
    }

    public String findJson(String productId) {
        return redis.opsForValue().get(keys.product(productId));
    }

    public Boolean remove(String productId) {
        return redis.delete(keys.product(productId));
    }
}
```

This is a JSON cache stored as a Redis string, with `StringRedisTemplate` storing the value as a UTF-8 string. The code does not validate JSON or convert DTOs itself; if the application works with Java objects, configure an appropriate serializer on the corresponding template. The `remove` method returns `Boolean` because the `delete` API can return `null` in certain contexts such as pipelines or transactions.

The benefit of a centralized key builder class is that a naming rule, input validation, or namespace version change can be updated in one place. However, changing the key builder when old data already exists is still a **storage contract change** requiring a strategy to read or migrate legacy data—it cannot be treated as a pure code refactor.

## 10. Spring Cache: cache names and cache prefixes are also namespaces

Spring Cache with Redis can construct keys from a **cache name** and a **cache key**. For example:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public Product findProduct(String productId) {
    // ... read data from primary source
}
```

The physical key name is produced by `RedisCacheConfiguration` and the key serialization mechanism. With common default configurations, there is a prefix based on the cache name, such as `products::p42`. If multiple applications use a cache named `products` on the same Redis, they still risk key collisions if the prefix lacks ownership information.

You can configure a dedicated namespace for the cache:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Configuration(proxyBeanMethods = false)
public class RedisCacheNamingConfig {

    @Bean
    RedisCacheConfiguration redisCacheConfiguration(
            @Value("${app.redis.namespace}") String namespace) {

        return RedisCacheConfiguration.defaultCacheConfig()
                .computePrefixWith(cacheName ->
                        namespace + ":cache:" + cacheName + "::");
    }
}
```

For example, the `products` cache with key `p42` gets the prefix:

```text
shop:prod:cache:products::p42
```

This is key naming configuration for **Spring Cache**, independent of how `ShopRedisKeys.product(...)` is used for `StringRedisTemplate`. Do not automatically mix both rules into the same key if they store different payloads.

If you want to reflect the business domain more clearly, you can name the cache `catalog-products` and define:

```text
shop:prod:cache:catalog-products::p42
shop:prod:cache:identity-users::u42
```

Cache names should be fixed and have an owner. Do not disable key prefixes when multiple caches share Redis without a collision-avoidance design. Check the cache key generator, serializer, and TTL alongside the prefix; the prefix solves only part of the problem.

## 11. Redis Repository: `@RedisHash` generates keys in its own keyspace

Spring Data Redis Repository stores entities via a mapping mechanism, typically as a Redis hash. The `@RedisHash` annotation specifies the entity's keyspace:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("catalog:product")
public class ProductRedisEntity {
    @Id
    private String id;
    private String name;

    // Appropriate constructor, getters, and setters.
}
```

With ID `p42`, a keyspace like `catalog:product` normally produces a Redis key of the form:

```text
catalog:product:p42
```

**Important:** `@RedisHash("catalog:product")` is a repository keyspace configuration; it **does not automatically prepend** `app.redis.namespace=shop:prod` from the key builder example or pick up the prefix declared by `RedisCacheConfiguration`. Therefore, if environments share Redis, repositories must also have their own keyspace strategy appropriate for the environment and data lifecycle.

Do not assume that renaming a `RedisTemplate` bean or configuring `keySerializer` will automatically change a repository's keyspace. Redis Repository has its own mapping mechanism, `RedisKeyValueAdapter`, and metadata; auxiliary keys for indexes or relationships may be generated by the framework under different rules than the primary key. Review the full scope of repository-managed data when designing namespaces, backups, or data deletion.

When a dynamic keyspace per environment is needed, use the keyspace/mapping context configuration points supported by Spring Data Redis in your project's version, or organize separate Redis deployments. Avoid hard-coding `prod` into annotations and reusing the exact same class in staging if both environments share Redis.

## 12. Spring Session and components creating keys outside business code

Not only code calling `RedisTemplate` writes keys. Libraries can manage their own keys, for example:

- **Spring Session**: session keys and metadata/indexes in Spring Session's own namespace.
- **Spring Cache**: keys by cache name and cache key, created by Redis Cache configuration.
- **Spring Data Redis Repository**: entity keyspaces and auxiliary keys for mapping/indexing.
- **Rate limiters or distributed locks**: keys by resource/action/owner, with very specific TTL and value rules.
- **Message streams/consumer groups**: the stream is a Redis key; the consumer group name is an identifier inside the stream, not a separate Redis key.

Therefore, a system sharing Redis must maintain a **key-group ownership registry**, including keys created by frameworks and libraries. With Spring Session, Spring Boot/Spring Session versions provide namespace configuration properties, such as `spring.session.redis.namespace`; verify the exact version when using it. Do not assume that every library automatically reads a custom `app.redis.namespace` property.

When upgrading libraries, key structures and metadata may change. Existing session or repository data should be evaluated for compatibility before changing key naming or serialization rules.

## 13. Key names and Redis Cluster: hash slots are not based on `:`

Redis Cluster distributes keys across **16,384 hash slots**. Clients and Redis determine the slot from the bytes of the key; `:` characters in a namespace do not create shards or pin keys to a node.

Two keys with the same prefix can still reside in two different slots:

```text
shop:prod:checkout:cart:c817
shop:prod:checkout:cart:c818
```

Redis Cluster has **hash tag** syntax: if a key contains a valid `{...}` pair, the part inside the braces is used when computing the hash slot. For example, if you want two keys tied to the same cart to be processed together in a multi-key operation on the same slot:

```text
shop:prod:checkout:cart:{c817}:items
shop:prod:checkout:cart:{c817}:total
```

Both keys have the same hash tag `c817`, so they map to the same slot. This is useful when commands or transactions spanning multiple keys require the same slot. However:

- Not every key in the same application/domain needs to share a slot.
- Using a broad hash tag like `{shop}` for the entire system can concentrate load onto a single slot/node and defeat Cluster load distribution.
- Hash tags **do not create a separate logical database**, nor do they create a security boundary.
- In multi-tenancy, a hash tag for a co-located group should include enough context to be unique (such as tenant and cart) if cart IDs can overlap across tenants.

Example checking slots in a test Cluster environment:

```bash
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT \
  'shop:prod:checkout:cart:{c817}:items'

redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT \
  'shop:prod:checkout:cart:{c817}:total'
```

Both commands return the same slot number. The address `redis-node-1` is illustrative; replace it with the actual endpoint of your test environment.

### Key serializer affects the slot

`StringRedisTemplate` typically encodes keys as UTF-8. If another `RedisTemplate` uses JDK serialization for keys, two Java objects with the same `toString()` will not necessarily produce the same key bytes; Cluster may also compute a different slot. When multiple clients and languages share keys, **standardize the key serializer and encoding convention**. The key name you see in Java must correspond to the bytes Redis actually receives.

## 14. Namespaces and Redis logical databases are two different concepts

Standalone Redis can support multiple logical databases, selected via `SELECT`. However, in Redis Cluster only database `0` exists. Key-name namespaces work across both topologies:

```text
DB 0 / Cluster keyspace
    shop:prod:catalog:product:p42
    shop:prod:orders:order:o501
    billing:prod:invoice:inv1001
```

Choosing DB 1 or DB 2 does not replace the need for meaningful key design. When migrating from standalone to Cluster, databases other than 0 are no longer supported; if services were previously separated solely by database index, ownership information must be moved into key names and a migration plan must be created.

Previous example:

```text
Standalone DB 1: user:42  -> identity data
Standalone DB 2: user:42  -> checkout data
```

When moving to Cluster DB 0, you cannot keep both `user:42` names as-is. A new mapping could be:

```text
shop:prod:identity:profile:u42
shop:prod:checkout:cart:u42
```

Namespaces clarify meaning and prevent key collisions; they do not guarantee separate RAM, CPU, or failover isolation per group. If strong isolation is needed, separate infrastructure and appropriate access policies are required.

## 15. Key names, TTL, and data lifecycle

Proper key naming also requires defining **how long a key lives and who may delete it**. A session with a 30-minute TTL differs from an order requiring long-term retention; do not just look at `shop:prod:...` and apply the same TTL to everything.

Examples:

```text
shop:prod:catalog:product:v1:p42      -> cache, 15-minute TTL
shop:prod:identity:session:v1:s912    -> session, 30-minute TTL
shop:prod:limits:user:u42             -> request limit, window-based TTL
shop:prod:orders:order:o501           -> business data, per retention policy
```

A Redis key can have no TTL or an explicit TTL. In Redis, `TTL` returns:

```text
> 0 : remaining seconds (can practically be 0 right before expiration)
-1  : key exists but has no expiration
-2  : key does not exist
```

Note that `SET key value` without an option to preserve TTL normally **removes the existing TTL** of the key. In Spring Data Redis, specify TTL explicitly when writing cache entries:

```java
redis.opsForValue().set(
        keys.product("p42"),
        productJson,
        Duration.ofMinutes(15));
```

Redis hashes, sets, and sorted sets also have TTL at the **Redis key level**. If a Redis hash has 10 fields, setting a TTL on the hash does not give each field an independent TTL by default. When one object spans multiple auxiliary Redis keys, decide how they will be renewed, deleted, or rebuilt to avoid orphaned keys.

### Do not use cache keys as the business source of truth without designing for it

For example, `catalog:product` might only be a cache rebuildable from the primary database; losing this key increases latency without losing source data. Conversely, if balances, orders, or transaction histories are stored only in Redis, changing TTL or eviction policies can have severe consequences. Naming rules should be accompanied by documentation on data criticality and lifecycle.

## 16. Prefix-based debugging and observability

Namespaces assist incident investigation when millions of keys exist. For example, to inspect a key's data type, TTL, and value in an authorized environment:

```bash
redis-cli TYPE shop:prod:catalog:product:v1:p42
redis-cli TTL shop:prod:catalog:product:v1:p42
redis-cli EXISTS shop:prod:catalog:product:v1:p42

# Only use GET if TYPE indicates this is a Redis string.
redis-cli --raw GET shop:prod:catalog:product:v1:p42
```

To incrementally iterate keys matching a prefix in standalone Redis:

```bash
redis-cli --scan --pattern 'shop:prod:catalog:*'
```

`SCAN` paginates key traversal, making it more suitable than `KEYS shop:prod:catalog:*` when Redis holds many keys. However, `SCAN` **is not a consistent snapshot**: during scanning, keys may be created or deleted, and the same key can be returned multiple times. Any aggregation tool must deduplicate and handle concurrent changes.

In Redis Cluster, `SCAN` on one node only iterates keys belonging to that node. Passing `redis-cli -c` does not automatically turn a single `SCAN` into a full Cluster scan; cluster-wide statistics require a topology-aware tool iterating the respective primaries.

### Do not perform bulk deletion based solely on a prefix

Commands like `DEL`, `UNLINK`, `FLUSHDB`, or pattern-based deletion scripts can all cause data loss. Even if keys start with `shop:dev:`, important data or active jobs may still rely on them. Before bulk deletion, operational procedures must verify the owner, environment, key nature, application impact, and auxiliary keys.

Never run `KEYS *` and delete all results in a production script. For large datasets, iterate in bounded batches and use operations compliant with operational policy. `UNLINK` can asynchronously reclaim memory for deleted keys, yet it remains a data deletion operation itself.

## 17. Namespaces assist ACLs but do not create security by themselves

Redis ACLs can restrict which key patterns a user is allowed to access. A namespace like `shop:prod:catalog:*` makes it easier to describe a service's data boundary.

Example authorization concept:

```text
Catalog service  -> only allowed to operate on keys shop:prod:catalog:*
Checkout service -> only allowed to operate on keys shop:prod:checkout:*
```

However, a prefix by itself **does not prevent service A from reading B's keys** if both use the same broad-access credential. If enforcement is needed, provision valid accounts/ACLs and control connections. In Redis Cluster, ensure authentication and authorization policies are consistently applied across nodes according to the cluster's operational setup.

Furthermore, Redis ACLs do not replace business authorization: a user in tenant A must not read tenant B's orders simply because the application can access both keys in Redis. Access control must be evaluated against the request's principal and tenant context before constructing the key name to read data.

Do not place passwords, access tokens, or personal data into keys under the assumption that Redis sits solely on an internal network. Key names can be logged and appear in backups and monitoring commands.

## 18. Changing key naming rules is a migration

Suppose version one cached data with the key:

```text
product:p42
```

The next version wants a richer, context-aware key:

```text
shop:prod:catalog:product:v2:p42
```

If you deploy the new code without a plan, the application may not find legacy data and may rebuild it; old keys stay in Redis until their TTL expires or they are deleted. For rebuildable caches, that behavior may be acceptable. For critical business data, legacy data cannot simply be ignored.

A controlled transition strategy:

1. **Inventory** legacy keys: prefix, Redis type, value serializer, TTL, owner, estimated count, and read/write call sites.
2. **Define the new key contract**: component order, canonical ID, version if needed, and payload format.
3. **Deploy a compatible reader**: read the new key first; if absent, read the legacy key with the exact legacy serializer and convert/write back under the new key when valid.
4. **Control concurrent writes**: if legacy app versions still write legacy keys, clearly decide on dual-write, write cutover timing, or an appropriate downtime window.
5. **Preserve TTL semantics**: if a legacy key has only 3 minutes left, do not extend it to 24 hours unless that is an intentional business decision. Read remaining `PTTL`/TTL and handle `-1` and `-2` cases during migration.
6. **Observe and retire the legacy path**: monitor fallback reads, deserialization errors, and unmigrated keys, then disable legacy writers and clean up data per approved procedure.

Illustrative dual-read model:

```text
read(productId)
    |
    +-- GET shop:prod:catalog:product:v2:<id>
    |       |
    |       +-- valid value present -> return
    |
    +-- GET product:<id> using legacy serializer
            |
            +-- value present -> convert to new format
            |                    and write v2 key with appropriate TTL
            +-- absent        -> cache miss / read primary source
```

If multiple application versions run concurrently, determine which data is the source of truth to prevent older versions from overwriting newer data or losing updates. A migration plan is more than changing a prefix in a Java helper.

### Should `v1` be added to every key?

It is not mandatory. A version in the key is useful for **incompatible** changes such as switching a Redis string to a hash, altering payload structure, or running two schemas side by side. For a temporary counter with a few seconds of TTL, versioning may add little value. What matters is having a **consistent policy for schema changes**, not mechanically appending `v1` to every key.

## 19. Anti-patterns and how to fix them

| Problematic naming | Problem | Clearer approach |
|---|---|---|
| `user:42` | Unknown application/domain | `shop:prod:identity:profile:u42` |
| `prod:42` | Unknown entity type | `shop:prod:catalog:product:p42` |
| `com.example.Product:42` | Coupled to Java package/class | `shop:prod:catalog:product:p42` |
| `shop:prod:user:an@example.com` | Exposes personal data | `shop:prod:identity:profile:u42` |
| `shop:prod:cart:null` | Invalid ID concatenated as string | Reject null IDs and validate in key builder |
| `shop:prod:cart:42` across all tenants | Collisions when ID is only tenant-unique | `shop:prod:t27:checkout:cart:42` |
| `shop:prod:{shop}:catalog:p42` | Overly broad hash tag in Cluster | Omit hash tag if unneeded, or tag per multi-key group |
| `shop:prod:catalog:product:p42` used as both JSON string and hash | Redis type conflict | Use a new schema/version key and migrate |
| `serviceA:key` while all services use broad credentials | Namespace alone does not protect data | Add ACLs/authorization and ownership policy |

These examples do not mandate that every application pick the exact `shop:prod:...` names; the goal is establishing a **stable, explainable structure** within your real system's scope.

## 20. Hands-on exercise with `StringRedisTemplate` and Redis CLI

Suppose application `shop`, environment `dev`, has two domains `catalog` and `checkout`. We want to create two distinct keys sharing ID `42`:

```text
shop:dev:catalog:product:42
shop:dev:checkout:cart:42
```

On a test standalone Redis:

```bash
redis-cli SET shop:dev:catalog:product:42 '{"name":"Notebook"}' EX 60
redis-cli SET shop:dev:checkout:cart:42 '{"items":2}' EX 120

redis-cli --raw GET shop:dev:catalog:product:42
redis-cli --raw GET shop:dev:checkout:cart:42

redis-cli TTL shop:dev:catalog:product:42
redis-cli TTL shop:dev:checkout:cart:42

redis-cli --scan --pattern 'shop:dev:*'
```

The two keys do not collide despite both having `identity=42`, and each key has an independent TTL. Note that in this example both Redis keys are **strings containing JSON**; do not use `HGET` because they are not Redis hashes.

If you change `shop:dev:catalog:product:42` to `shop:dev:catalog:product:v2:42`, a `GET` on the new name will not automatically read the old key. This directly illustrates that the key name is the storage identifier.

### Self-check questions

1. Why does `user:42` risk key collisions when multiple services share Redis?
2. If `orderId=501` is unique only within each tenant, which component must be included in the key?
3. Does the prefix `shop:prod:` automatically create a Redis database or restrict access permissions?
4. Why might two keys sharing the prefix `shop:prod:checkout:` not land in the same Redis Cluster slot?
5. Does changing `@RedisHash("product")` affect an already stored repository keyspace, and does it automatically change Spring Cache keys?
6. Why can running `SET` on a cache key without an expiry create a data lifecycle bug even if the key name is completely right?
7. When migrating from `product:42` to `shop:prod:catalog:product:v2:42`, why must you inspect both the serializer and TTL of the legacy key?

Hint: every answer relates to four distinct yet interconnected contracts: **key namespace**, **Redis data type/payload**, **data lifecycle**, and **ownership boundaries**.

## 21. Conclusion

In Spring Data Redis, name keys so that each key clearly reflects the **application**, **environment if needed**, **business domain**, **data type or purpose**, and a **stable identifier**. Centralizing key construction in the storage layer, aligning key serializers, unifying prefixes across Spring Cache/Redis Repository/Spring Session, and deciding TTLs based on data lifecycle help systems avoid collisions, stay observable, and remain maintainable.

String-based namespacing is a valuable design convention, but it does not replace ACLs, business authorization, or resource isolation. With Redis Cluster, you also need to understand hash slots and use hash tags only when specific multi-key operations require them. When changing key names for existing data, treat it as a **schema migration** with a compatibility plan, because Redis will not automatically know that two different names represent the same object.
