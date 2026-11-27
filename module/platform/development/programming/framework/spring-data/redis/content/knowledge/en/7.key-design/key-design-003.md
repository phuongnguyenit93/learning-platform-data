# Choosing Key Length and Controlling Key Cardinality

In Redis, every **key** is an identifier for a value or data structure. With Spring Data Redis, keys can be created directly via `StringRedisTemplate`, `RedisTemplate`, or indirectly through Redis Repository, Spring Cache, and other integrated components. Key naming and key count directly impact **memory, performance, data growth, model clarity, and operability**.

Two objectives must be balanced:

- **Key length**: names short enough not to waste memory, yet clear enough, stable, collision-free, and free of sensitive information.
- **Key cardinality**: avoiding excessive unique keys caused by timestamps, request IDs, parameter combinations, or temporary data lacking expiration.

Shortening key names does not solve creating hundreds of millions of keys. Packing everything into a single Hash to reduce key count can also create a **big key**, causing memory and latency problems. Therefore, choosing key length must go hand in hand with **data modeling, TTL, Redis data structures, memory budgeting, and monitoring**.

## 1. Distinguishing key length, key count, and value size

Suppose an e-commerce application has the following keys:

~~~text
shop:production:catalog:product:detail:0000000000000042
shop:prod:product:42
product:42
p:42
~~~

All four names might identify the same product. Longer names add bytes stored and sent over the network; overly short names make it hard to identify the owner in a multi-service system.

| Metric | Unit | Impact | How to control |
|---|---|---|---|
| Key name length | Bytes after serialization | Storage bytes, command payload bytes, log readability | Consistent naming, drop redundant segments, short and stable IDs |
| Number of distinct keys | Keys | Redis metadata, RAM, TTL, scanning | TTL, quotas, cardinality design |
| Value size | Bytes | RAM, bandwidth, serialization/deserialization | Store only necessary data, enforce size limits |
| Fields/members per Hash/Set/ZSet/List | Element count | Big keys, command complexity | Trim items, quotas, partitioning |
| Traffic to a single key | Commands/sec | Hot keys, resource contention | Load distribution, bucketing, appropriate caching |

A String key with a one-byte value still consumes memory for the object and metadata. Conversely, a Hash with millions of fields counts as **one key** yet can still consume massive RAM.

### 1.1. Why do key bytes matter at large scale?

Suppose two key conventions differ by 24 bytes. With 8 million live keys:

~~~text
24 bytes/key × 8,000,000 keys
= 192,000,000 bytes
≈ 183 MiB
~~~

That is only the **theoretical key-name byte difference**, excluding memory allocation overhead, values, expiry metadata, replication, allocator fragmentation, and internal Redis structures. Actual memory should be measured.

With 1,000 keys, the difference is only about 24 KB. Do not sacrifice clarity or increase collision risk just to save a few kilobytes.

### 1.2. Do not confuse Java character count with Redis byte count

Redis keys are byte sequences. If using `StringRedisTemplate` with UTF-8, a name containing multi-byte characters will have a different size than `String.length()` in Java.

~~~java
import java.nio.charset.StandardCharsets;

String key = "shop:prod:user:42";
int byteLength = key.getBytes(StandardCharsets.UTF_8).length;

System.out.println("Key bytes = " + byteLength);
~~~

`String.length()` counts UTF-16 code units; do not use it as the byte count for keys containing Unicode. For namespaces, codes, and technical IDs, using ASCII consistently simplifies estimation and handling.

Redis has a very large theoretical limit on key length, but that is not a design target. Establish a **practical length threshold in the application** based on key type and expected volume—for example, 128 bytes for a key group that could reach millions of entries. That threshold is merely an example policy, not a default Redis limit.

## 2. Key naming convention: meaningful, stable, and owned

An easy-to-follow template:

~~~text
<application>:<environment>:<domain>:<entity-id>[:<purpose>]
~~~

Examples:

~~~text
shop:prod:product:42
shop:prod:cart:user:782
shop:prod:inventory:sku:K83Z
shop:prod:rate-limit:user:782
shop:prod:report:job:9e5d2c
~~~

You do not need to apply every prefix layer to every system. A Redis deployment dedicated exclusively to one application and environment may not need to repeat the application name in every key. However, on shared Redis, namespaces help prevent collisions and simplify per-group accounting.

Key principles:

1. **One entity, one naming formula:** the same input and purpose must generate the same key.
2. **Clear delimiters or encoding:** avoid concatenating two IDs into one string prone to collisions.
3. **Defined owner:** know which service/module creates, reads, updates, and deletes it.
4. **Use short, stable IDs:** do not stuff full URLs, JSON, query strings, or objects into keys.
5. **Do not expose sensitive data:** avoid access tokens, passwords, emails, and personal information in key names because keys can appear in logs or admin tools.
6. **Do not vary key names on every request unnecessarily:** millisecond timestamps, per-read UUIDs, or trace IDs quickly inflate key counts.
7. **Plan key schema changes:** if changing prefixes/versions, use TTL or migration so old keys do not persist forever.

### 2.1. Avoiding collisions when concatenating components

Concatenating two numbers directly without a separator:

~~~text
userId=12, productId=34 -> "1234"
userId=1, productId=234 -> "1234"
~~~

Two distinct pairs produce the same key. Prefer:

~~~text
shop:prod:user:12:product:34
shop:prod:user:1:product:234
~~~

If a component itself contains `:`, normalize or escape the ID by convention. An undelimited schema can overwrite data even when keys are very short.

### 2.2. Are long prefixes truly necessary?

Compare:

~~~text
com.company.shopping.production.inventory.product.byId.42
shop:prod:inventory:product:42
~~~

The second name is usually clear enough. If a Redis instance serves only `inventory` in production, you could shorten it further. Yet `p:42` is easily confused with `payment:42` or `promotion:42` in a large application.

Principle: **cut useless repetition first; keep the segments that distinguish meaning and ownership**.

## 3. When inputs are URLs, queries, or very long strings

Suppose you need to cache search results by user filters:

~~~text
shop:prod:search:category=book&sort=price&brand=...&filters=...
~~~

If keys embed raw URLs/queries, lengths can reach thousands of bytes, risk containing sensitive info, and equivalent strings can yield multiple keys:

~~~text
?sort=price&category=book
?category=book&sort=price
~~~

When two queries have the same meaning, **canonicalize the input** before generating the key: standardize parameter order, casing rules, encoding, default values, and filter representation.

When a canonicalized string is still long, you can compute a digest:

~~~text
shop:prod:search-result:<sha256-hex>
~~~

Java 17+ example:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.HexFormat;

public final class RedisKeys {

    private RedisKeys() {}

    public static String searchResult(String canonicalQuery) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(canonicalQuery.getBytes(StandardCharsets.UTF_8));
            return "shop:prod:search-result:"
                    + HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

A hex-encoded SHA-256 digest is 64 ASCII characters long. For URLs spanning several kilobytes, this can reduce length substantially; for an ID of only 5–10 characters, hashing the ID usually makes the key **longer**. Do not hash every key mechanically.

A digest is not secret encryption; if the input space is small, others can guess and recompute the digest. Avoid putting secrets into key schemas and manage Redis access controls separately.

Over-truncating a digest increases collision probability; evaluate collision odds against the **maximum keys generated over the entire lifecycle**, not just a small test session.

## 4. Key cardinality: how large will the key count grow?

The bigger concern is usually not a 50-byte key, but **every user action creating a new key**.

Suppose:

~~~text
200,000 active users
× 50 views/day
= 10,000,000 views/day
~~~

If storing one key per view for 30 days:

~~~text
10,000,000 × 30 = 300,000,000 concurrent keys
~~~

This is an estimate assuming unique keys, steady rate, and an exact 30-day TTL. Even 30-byte key names alone create gigabytes of key bytes; values and metadata can consume even more.

If the actual requirement is only the most recently viewed product, you can use:

~~~text
shop:prod:user:last-viewed:782
~~~

and overwrite the value for the same user. Instead of a new key per event, the key count stays close to the number of users with recent activity.

### 4.1. Formula for estimating keys with TTL

~~~text
Approximate live keys
= unique key creation rate/sec × average lifetime (seconds)
~~~

For example, 500 new keys/sec with a 1-hour TTL:

~~~text
500 × 3600 = 1,800,000 keys
~~~

This forecast assumes a roughly steady rate. If the same keys are overwritten repeatedly or TTLs are refreshed, the live key count and effective lifetime will differ.

Without TTL, the growth model is:

~~~text
Ending keys
= starting keys + newly created keys - deleted keys
~~~

If new keys are continuously created with almost no deletions, the keyspace grows over time. Running Redis with `maxmemory` does not turn unbounded growth into a proper data lifecycle policy.

### 4.2. Cardinality is the product of multiple dimensions

A key:

~~~text
shop:prod:tenant:<tenant>:user:<user>:report:<report-id>:day:<date>
~~~

can vary by tenant, user, report, and day. Theoretical upper bound example:

~~~text
100 tenants × 20,000 users/tenant × 40 reports/user × 30 days
= 2,400,000,000 combinations
~~~

Not every combination exists simultaneously; however, this calculation reveals the explosion potential if the system creates keys per combination. Adding a `requestId`, `deviceId`, or timestamp dimension can turn a previously stable model into an unbounded keyspace.

When designing, ask: **does this component truly belong in the key name, or can it live as a field/member, bucket, or value?**

## 5. TTL and deletion policies: bounding key lifetimes

For temporary data, TTL should be part of the write API from day one.

~~~java
import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class TemporaryMarkerStore {

    private static final Duration TTL = Duration.ofMinutes(15);

    private final StringRedisTemplate redis;

    public TemporaryMarkerStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String requestId) {
        String key = "shop:prod:processed-request:" + requestId;
        redis.opsForValue().set(key, "1", TTL);
    }
}
~~~

`set(key, value, timeout)` sets the value and TTL in one operation, avoiding the gap between separate `SET` and `EXPIRE` commands where a key could persist without TTL if the process fails. However, the example above overwrites the marker, so it **does not guarantee duplicate-processing prevention on its own**.

When you need to create the key only if absent:

~~~java
public boolean markIfAbsent(String requestId) {
    String key = "shop:prod:processed-request:" + requestId;

    Boolean created = redis.opsForValue()
            .setIfAbsent(key, "1", Duration.ofMinutes(15));

    return Boolean.TRUE.equals(created);
}
~~~

This shows a method on the class with the `StringRedisTemplate redis` field above. `setIfAbsent` combines the non-existence condition and TTL in Redis. Even so, a marker succeeding before business execution finishes can block retries after a failure. Systems requiring true idempotency must design state, recovery, and consistency with the business transaction.

### 5.1. TTL must match data semantics

| Key type | Lifecycle policy |
|---|---|
| Rebuildable result cache | TTL matching acceptable staleness, invalidation when source data changes |
| Windowed rate-limit counter | TTL matching window length plus margin for delayed processing |
| Request processing marker | TTL matching business retry/idempotency window |
| OTP or temporary token | Short TTL, attempt limits, and invalidation upon completion |
| Temporary job output | TTL covering how long users need to download results |
| Session | Let Spring Session manage session inactivity/expiration |
| Critical source data | Do not attach arbitrary TTLs; define recovery capabilities clearly |

**Not every key should have a TTL.** However, any key without a TTL must have a reason, an owner, and a deletion process when data loses value.

### 5.2. Refreshing TTL can keep keys from ever expiring

If every user visit resets a 30-day TTL on the same key, the key can live forever for regularly active users. Distinguish between:

- **Absolute TTL**: lifetime measured from creation; updates do not extend it.
- **Sliding TTL**: new activity extends the expiration.
- **Event-driven expiry**: deleted after an order closes, a campaign ends, or a job completes.

Sliding TTL fits certain session states, yet is unsuitable for all audit/idempotency keys. Choose deliberately.

### 5.3. TTL is not an absolute cardinality quota

With a 60-minute TTL and 500 new keys/sec, steady state is around 1.8 million keys. If traffic spikes to 5,000 keys/sec, live keys can climb to 18 million. You still need **rate limits, quotas, backpressure, and memory budgets**.

## 6. When should you use a Hash to reduce key count?

Instead of one key per attribute:

~~~text
shop:prod:user:42:name   -> An
shop:prod:user:42:locale -> vi
shop:prod:user:42:theme  -> dark
~~~

you can create one Hash:

~~~text
shop:prod:user:42
    name   = An
    locale = vi
    theme  = dark
~~~

A Redis Hash can reduce top-level key count and associated metadata. For small Hashes, Redis can use an optimized internal representation. However, actual savings depend on field/value sizes, Redis encoding thresholds, and workload.

Spring Data Redis example:

~~~java
import java.util.Map;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class UserPreferenceStore {

    private final StringRedisTemplate redis;

    public UserPreferenceStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(long userId, String locale, String theme) {
        String key = "shop:prod:user-preferences:" + userId;

        redis.opsForHash().putAll(
                key,
                Map.of("locale", locale, "theme", theme)
        );
    }

    public Object getLocale(long userId) {
        return redis.opsForHash().get(
                "shop:prod:user-preferences:" + userId,
                "locale"
        );
    }
}
~~~

Fields in the same Hash typically share a **key-level TTL**; wanting field A to expire in 5 minutes and field B in 7 days requires checking support in your Redis features/version, or using separate keys and alternative controls.

**Grouping into a Hash works well when** multiple attributes of the same entity share a similar lifecycle, field count is bounded, and fields are frequently accessed together.

**It works poorly when** stuffing all users into `shop:prod:all-users` with an unbounded field count. Redis ends up with a massive key; key count drops, yet load and data concentrate into a big key/hot key that is hard to distribute across Redis Cluster.

## 7. Bounding member counts in Lists, Sets, and Sorted Sets

If the requirement is keeping the "100 most recently viewed products per user", you do not need one key per view. You can use a **per-user List** and trim it.

~~~java
import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RecentProductStore {

    private final StringRedisTemplate redis;

    public RecentProductStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void record(long userId, long productId) {
        String key = "shop:prod:user:recent-products:" + userId;

        redis.opsForList().leftPush(key, Long.toString(productId));
        redis.opsForList().trim(key, 0, 99);
        redis.expire(key, Duration.ofDays(14));
    }

    public List<String> latest(long userId) {
        return redis.opsForList().range(
                "shop:prod:user:recent-products:" + userId, 0, 99
        );
    }
}
~~~

Sequentially, this keeps at most 100 recent elements. However, `leftPush`, `trim`, and `expire` are three separate commands. Under concurrent requests, intermediate states or unexpected ordering can occur. If **atomicity** is needed, wrap the operations in a Lua script on the same key, which fits Redis Cluster semantics.

When deduplicated items are required, prefer a Set or Sorted Set depending on business semantics. For Sorted Sets, bound members with a trim policy; otherwise, you merely shift the problem from **too many keys** to **one key with unbounded members**.

| Data to keep | Reference model | Key limit to enforce |
|---|---|---|
| Current values per user | One String or Hash/user | User count, TTL |
| Last 100 events | One List/user | Max 100 items, TTL |
| Recent unique items | Sorted Set/user | Member count, score/order |
| Per-product counter | String/product | Product count, cleanup on product deletion |
| Total views per minute | Per-minute bucket | Live bucket count, retention window |
| Work queue | List/Stream per design | Queue length, ack, cleanup, retention |

## 8. Time bucketing to avoid one key per event

There is no need to write:

~~~text
shop:prod:pageview:2026-11-12T15:30:01.124
shop:prod:pageview:2026-11-12T15:30:01.125
shop:prod:pageview:2026-11-12T15:30:01.126
...
~~~

if the business only needs pageview counts per minute. You can use:

~~~text
shop:prod:pageviews:2026-11-12T15:30 -> 128
shop:prod:pageviews:2026-11-12T15:31 -> 135
~~~

or one Hash per day with minute fields:

~~~text
shop:prod:pageviews:2026-11-12
    "15:30" -> 128
    "15:31" -> 135
~~~

With 7-day retention and 1-minute buckets:

~~~text
7 days × 24 hours × 60 minutes = 10,080 buckets
~~~

This is the bucket count for **one metric without extra dimensions**. If creating separate buckets for 100,000 products, maximum combinations can skyrocket. Account for data sparsity, create keys only when traffic occurs, and enforce retention rules.

Closed buckets generally do not need TTL refreshed on reads. For late-arriving events, define explicitly whether to write to the old bucket, backfill via long-term storage, or drop them.

## 9. Do not rely on Redis maxmemory as the sole solution

Redis can be configured with:

~~~conf
maxmemory 2gb
maxmemory-policy allkeys-lru
~~~

When the limit is reached and the policy calls for eviction, Redis can evict keys to make room for new data. However, eviction:

- Does not understand **per-tenant or per-feature quotas**.
- Can evict critical keys if the policy permits.
- Does not guarantee a stable cache hit rate as the keyspace grows.
- Does not replace TTL, cleanup, and capacity planning.
- Does not fix a poorly designed big key or hot key.

If a shared Redis server stores rebuildable caches alongside business state that must not be lost, evaluate eviction policies and availability very carefully. When purposes have vastly different requirements, separate Redis deployments.

### 9.1. Exact key quotas differ from periodic counting

Suppose each tenant may keep at most 500 temporary jobs. If two requests execute concurrently:

~~~text
A: counts 499 jobs
B: counts 499 jobs
A: creates new job
B: creates new job
Result: 501 jobs
~~~

A `SCAN` followed by `SET` is not atomic. If a quota must be exact, state/membership/quota must be updated **atomically** with the creation decision; Lua scripts on co-slotted keys in Redis Cluster can help. You must also synchronize state when TTL deletes job keys, on retries, during cleanup, and after timeout errors. Quota counters must not be assumed to match actual key counts if deletions/expirations happen independently.

If you only want **operational alerts**, periodic counts per key group may suffice without locking every request under a complex quota protocol.

## 10. Spring Data Redis behaviors that alter key length and count

### 10.1. Serializers determine actual key bytes

`StringRedisTemplate` uses a string serializer. When calling:

~~~java
redis.opsForValue().set("shop:prod:product:42", "active");
~~~

the key in Redis is encoded using the string scheme (usually UTF-8).

With `RedisTemplate<K,V>`, the key serializer may be JDK serialization or a custom serializer. **Never assume** that a key looking like `shop:prod:product:42` in Java has the same bytes as that ASCII string in Redis.

Example template configuration with String keys:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisTemplateConfig {

    @Bean
    RedisTemplate<String, byte[]> byteValueRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, byte[]> template = new RedisTemplate<>();
        template.setConnectionFactory(factory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(RedisSerializer.byteArray());
        template.afterPropertiesSet();
        return template;
    }
}
~~~

In this example, keys are Strings and values are byte arrays. Switching serializers on a system with existing data requires a compatibility or migration plan to read legacy keys/values.

### 10.2. Spring Cache generates keys from method and parameters

~~~java
@Cacheable(cacheNames = "products", key = "#id")
public ProductView getProduct(Long id) {
    // Query primary data source
}
~~~

An entry may be stored under a name resembling:

~~~text
products::42
~~~

under the default Redis Cache prefix in many common configurations. Caching multiple lookup paths for the same product can create multiple entries:

~~~text
products::42
productsBySku::K83Z
featuredProducts::42
~~~

Thus, cache cardinality depends on **parameter combinations and cache names**, not just product count.

For queries with filters, sorting, paging, locale, and user ID, combinations can grow huge with low hit rates. Sometimes the right optimization is **not caching rare queries**, rather than merely shortening keys.

Redis Cache configures TTL via `RedisCacheManager` or Spring Boot properties such as:

~~~yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 10m
      cache-null-values: false
~~~

TTL limits entry lifetime, but does not keep live entry counts under a quota if creation rates are high.

### 10.3. Spring Session and Redis Repository can generate auxiliary keys

Spring Session manages session keys and, depending on the implementation, may use supporting keys or indexes for expiration. Spring Data Redis Repository with `@RedisHash` may maintain entity keys, indexes, or expiration metadata depending on configuration.

Therefore:

~~~text
Number of business entities/sessions ≠ always equal to actual Redis key count
~~~

Do not manually delete framework-managed internal keys just because their names look long or numerous. Instead, control session counts, inactivity timeouts, and session attribute sizes; for Repositories, review index needs and entity lifecycle policies.

## 11. Redis Cluster: designing keys for slots

In Redis Cluster, keys are partitioned across **16,384 hash slots** distributed among multiple primaries. Normal keys like:

~~~text
shop:prod:product:42
shop:prod:product:43
~~~

can land in different slots.

If a command or Lua script needs multiple keys on the same slot, use a valid hash tag:

~~~text
shop:prod:cart:{user42}:items
shop:prod:cart:{user42}:summary
~~~

Both keys use hash tag `{user42}` and map to the same slot.

**Do not create every key with the same hash tag**:

~~~text
shop:{prod}:product:1
shop:{prod}:product:2
shop:{prod}:product:3
~~~

All of them land in the same slot, risking resource imbalance and a hot slot. Normal prefixes like `shop:prod:` are not an issue; curly braces used as a hash tag are what control slot placement.

Total Cluster key count is the sum distributed across primaries; when measuring with node-level commands, know which node owns which slots. A measurement on a single node does not automatically represent the whole Cluster.

## 12. Monitoring key count, length, and memory

### 12.1. Total key count and resource usage

On standalone Redis:

~~~bash
redis-cli INFO keyspace
redis-cli DBSIZE
redis-cli INFO memory
redis-cli INFO stats
~~~

| Command | Provides | Limitations |
|---|---|---|
| `INFO keyspace` | Keys and expiry info per logical DB | Does not break down by prefix |
| `DBSIZE` | Key count in current DB | Not the total key count of an entire Cluster |
| `INFO memory` | Used memory, fragmentation, and RAM info | Does not immediately show which namespace consumes RAM |
| `INFO stats` | Counters like `expired_keys`, `evicted_keys`, cache hits/misses | Must be compared over time; not a per-key snapshot |

Watch trends: **continuously rising key counts**, `used_memory` approaching budget, rising `evicted_keys`, or mismatched TTLs are all signals worth investigating.

### 12.2. Measuring a specific key

~~~bash
redis-cli TYPE shop:prod:product:42
redis-cli MEMORY USAGE shop:prod:product:42
redis-cli TTL shop:prod:product:42
redis-cli STRLEN shop:prod:product:42
~~~

- `TYPE` identifies String, Hash, List, Set, ZSet, or another supported type.
- `MEMORY USAGE` estimates RAM associated with a key/value according to Redis accounting.
- `TTL` returns remaining seconds; `-1` means the key exists without TTL, `-2` means the key does not exist.
- `STRLEN` returns the **String value** byte length, not the length of the key name.

To inspect big keys containing many elements:

~~~bash
redis-cli HLEN shop:prod:user-preferences:42
redis-cli LLEN shop:prod:user:recent-products:42
redis-cli SCARD shop:prod:active-users
redis-cli ZCARD shop:prod:leaderboard
~~~

Do not treat raw key count alone as a complete memory metric.

### 12.3. Scanning keys by prefix with SCAN

Avoid calling:

~~~bash
redis-cli KEYS 'shop:prod:*'
~~~

on a large production keyspace because `KEYS` scans everything and can block Redis for a long time. Instead, iterate in batches:

~~~bash
redis-cli --scan --pattern 'shop:prod:product:*'
~~~

or interactively:

~~~text
SCAN 0 MATCH shop:prod:product:* COUNT 500
~~~

`SCAN` returns a cursor and a batch of keys. Clients loop until the cursor returns to `0`.

Key points to remember:

- `COUNT 500` is only a work hint, not a guarantee of always returning 500 keys.
- **Duplicates** can appear across iterations; deduplicate if you need a distinct key list.
- The keyspace mutates continuously, so scan output cannot be treated as a consistent snapshot.
- A full scan still traverses large amounts of data; run admin scans in batches rather than scanning all of Redis per request.
- In Redis Cluster, understand which node/primary is being scanned and collect across topology appropriately.

Redis CLI also provides statistical scan modes such as:

~~~bash
redis-cli --bigkeys
~~~

Depending on tool version, additional memory inspection modes may exist. Before running on data-heavy production, evaluate scan impact and speed.

## 13. Scanning keys with Spring Data Redis

`StringRedisTemplate` supports `scan(ScanOptions)`:

~~~java
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class KeyInventoryService {

    private final StringRedisTemplate redis;

    public KeyInventoryService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long estimateProductKeyCount() {
        ScanOptions options = ScanOptions.scanOptions()
                .match("shop:prod:product:*")
                .count(500)
                .build();

        long count = 0;
        try (Cursor<String> cursor = redis.scan(options)) {
            while (cursor.hasNext()) {
                cursor.next();
                count++;
            }
        }
        return count;
    }
}
~~~

The method is named `estimateProductKeyCount` because the count can be affected by duplicate keys from scanning and a changing keyspace. This pattern works for standalone Redis or when the connection's scan scope is clearly understood. With Cluster, do not assume a single cursor automatically scans all primaries.

`Cursor` must be closed to release resources. This is a **batch/administration** task, not something to run inside a fast-response user-facing endpoint.

If exact, continuous statistics per tenant/feature are required, design an index or appropriate metrics system directly where keys are created/deleted, and handle atomicity when syncing quotas.

## 14. Estimating memory budgets per key group

An illustrative forecast table:

| Key group | Expected keys | Value | TTL | Action when exceeded |
|---|---:|---|---|---|
| `shop:prod:product:*` | 300,000 | DTO | 30 minutes | Reduce cache variants, check hit rate |
| `shop:prod:processed-request:*` | 1,800,000 | Marker | 1 hour | Rate-limit markers, tune TTL appropriately |
| `shop:prod:user:recent-products:*` | 200,000 | List of max 100 IDs | 14 days | Bound items and active user count |
| `shop:prod:report:job:*` | 10,000 | Result JSON | 24 hours | Per-tenant job quota and cleanup |

These are **illustrative figures**, not guaranteed Redis capacity baselines.

To estimate RAM:

1. Define the key schema, current key count, and peak key count.
2. Measure serialized key byte length, value size, and structure element count.
3. Use realistic sample data to measure `INFO memory` and `MEMORY USAGE`.
4. Factor in allocator overhead, fragmentation, replication, persistence, and peak load.
5. Monitor per **node/primary** in Redis Cluster to spot skewed distributions.
6. Set early alerts and have a plan to throttle key creation or purge stale data.

Saving another 15 bytes/key matters little if every value holds hundreds of kilobytes, or if cache entries have a hit rate near zero.

## 15. Key design workflow for a new feature

Suppose the application wants to cache filtered product search results.

**Step 1 — Define the purpose.** Results are rebuildable from the DB so they can be cached short-term; if immediate updates are required after changes, implement invalidation.

**Step 2 — Design the name.** Normalize filters/sorts and generate a stable key. Use a digest only when parameter strings are long or involve hard-to-manage combinations.

**Step 3 — Estimate cardinality.** How many filter combinations actually repeat? Are there random parameters making every cache key unique? If hit rates are low, consider caching only popular queries.

**Step 4 — Set TTL and size bounds.** Pick a TTL matching acceptable staleness; cap payload sizes and avoid caching huge results.

**Step 5 — Estimate the budget.** Sample keys/values and load-test to measure memory footprint, including peak conditions.

**Step 6 — Set up monitoring.** Track key counts, expired/evicted keys, used memory, cache hit rates, key creation rates, and big keys.

**Step 7 — Identify the owner and cleanup plan.** Every key schema must have someone responsible for its lifecycle; when changing prefixes, plan how old data will be deleted or allowed to expire.

~~~text
             New data to store in Redis
                        |
             One key per event?
                   /            \
                 No             Yes
                   |              |
              Stable key      Can it be grouped into
              by entity       buckets/List/Stream?
                   |              |
                   +------+-------+
                          |
              Multiple fields on same entity,
              same lifecycle/TTL?
                   /          \
                 Yes           No
                  |              |
             Consider Hash   Separate keys
                   \          /
                    +--------+
                        |
             Estimate key count
             × key bytes × value bytes
                        |
               Has TTL or cleanup?
                  /            \
                Yes             No
                 |               |
              Set TTL       Owner & deletion mechanism
                 \               /
                  +-------------+
                        |
             Measure, quota, and alert
~~~

## 16. Common mistakes

### Mistake 1 — Creating one key per request

Request IDs or timestamps make keys almost never repeat. If you only need a counter, latest state, or aggregated data, use a stable key and bound its lifecycle.

### Mistake 2 — Stripping keys of all meaning

`p:42` is not inherently safer than `shop:prod:product:42`. When teams share Redis without conventions, the risk of accidental overwrites or deletions outweighs minor byte savings.

### Mistake 3 — Assuming one giant Hash saves endlessly

Fewer keys with huge values/fields can still cause big keys, latency, and backup or slot-balancing issues. Bounding members is always part of design.

### Mistake 4 — Ignoring framework-generated keys

Spring Cache, Spring Session, and Redis Repository can generate keys with their own logic, including auxiliary keys. Measure the actual keyspace, not just `StringRedisTemplate.set()` calls in code.

### Mistake 5 — Relying solely on TTL

TTL still allows massive concurrent key counts if write rates are high. You also need quotas, rate limits, and memory budgeting.

### Mistake 6 — Using Redis `KEYS` for per-request counting

Scanning the whole keyspace on every HTTP request can degrade Redis. Use metrics/indexes or batch scans for operations.

### Mistake 7 — Looking only at key count, ignoring value size

A few huge Hashes, Streams, or Sorted Sets can use more RAM than hundreds of thousands of small String keys. Measure key count, value size, and field/member counts together.

### Mistake 8 — Treating prefixes as resource protection

Prefixes organize the keyspace; they do not create dedicated quotas, ACLs, or per-namespace RAM limits. Design appropriate infrastructure policies.

### Mistake 9 — Using the same Cluster hash tag on every key

Putting `{prod}` in every key pushes everything into a single hash slot, negating Redis Cluster's load distribution.

### Mistake 10 — Failing to manage key schema changes

If every deployment changes prefixes without expiring old keys, parallel key generations can grow memory even when current logic no longer reads them.

## 17. Practice calculations

**Exercise 1.** A system creates 250 unique markers per second with a 20-minute TTL. Steady-state live markers are approximately:

~~~text
250 × 20 × 60 = 300,000 keys
~~~

If traffic spikes to 1,000 markers/sec over 20 minutes, newly created keys in that window can reach 1.2 million, excluding previously live keys.

**Exercise 2.** Two key naming schemas differ by 30 bytes across 100,000 keys:

~~~text
30 × 100,000 = 3,000,000 bytes ≈ 2.86 MiB
~~~

In this case, clarity may matter far more than a few MiB. If key counts grow to 50 million, measure and consider optimizing the prefix.

**Exercise 3.** Each user needs the 50 most recently viewed products over 14 days; there are 500,000 active users and 30 million views/day.

- One key per event over 14 days could create roughly **420 million keys** if every event is unique.
- One List/ZSet per user could use roughly **500,000 top-level keys**, provided each structure is bounded to 50 elements with an appropriate business TTL.
- If long-term event history is truly needed, Redis can hold a fast summary while a long-term event store owns the complete data.

## 18. Summary of choices

| Question | Decision direction |
|---|---|
| How long should keys be? | Just long enough to distinguish semantics, namespace, and owner; measure in **bytes**, not by guesswork |
| Should every key be hashed? | No; only useful for long inputs or multi-form inputs needing canonicalization |
| Can keys include timestamps? | Yes, with bounded buckets and clear retention; avoid per-event timestamps when only aggregates are needed |
| String or Hash? | Based on lifecycle, field count, and access patterns; Hashes must not grow unbounded |
| Should everything have a TTL? | Temporary data needs TTL; persistent data needs a clear owner and deletion process |
| Is TTL enough to bound RAM? | No; account for creation rate, value size, peaks, and quotas |
| What should be used to count keys? | `INFO keyspace`, `DBSIZE`, `SCAN`, per-type metrics, and real measurements |
| Does `SCAN` give an exact snapshot? | Not guaranteed when the keyspace mutates, and it may return duplicate keys |
| Does Redis Cluster change key design? | Yes; understand hash slots, hash tags, key distribution, and hot slots |
| Is fewer keys always better? | No; excessive grouping can create big keys or hot keys |

**Choosing key length** avoids storing unnecessary bytes while keeping clarity. **Controlling key cardinality** keeps the keyspace from outgrowing RAM and operational capacity. In Spring Data Redis, key design must align with serializers, TTLs, data structures, creation rates, business bounds, and measurement practices right when building the feature.
