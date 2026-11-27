# Choosing Flat Hash, JSON, or Multiple Separate Keys

In Spring Data Redis, a Java object can be stored as **a Redis Hash**, **a Redis String containing JSON**, or **multiple independent Redis keys**. All three approaches can represent the same business entity, yet they produce different characteristics for querying, updates, TTL, memory usage, serialization, and concurrency handling.

The most important selection rule is: **the Redis model must reflect the operations the application performs most frequently**. Having a DTO with many fields does not automatically mean it should be a Redis Hash; having a nicely structured JSON document does not automatically make it optimal if the application only increments a single counter.

## 1. Three Ways to Represent the Same Data

Suppose the application has a user profile:

~~~java
public record UserProfile(
        String userId,
        String displayName,
        String city,
        long loginCount,
        boolean verified
) {}
~~~

Sample values:

~~~text
userId      = 42
displayName = Linh
city        = Ha Noi
loginCount  = 7
verified    = true
~~~

### 1.1. Flat Hash: One Key Containing Many Fields

~~~text
Redis key: user:42:profile
Redis TYPE: hash

displayName  -> Linh
city         -> Ha Noi
loginCount   -> 7
verified     -> true
~~~

~~~redis
HSET user:42:profile displayName "Linh" city "Ha Noi" loginCount 7 verified true
HGET user:42:profile city
HINCRBY user:42:profile loginCount 1
HGETALL user:42:profile
~~~

This is a Redis Hash. `city` is a **field inside the key**, not a separate key in the keyspace.

### 1.2. JSON: One Key Containing the Entire Document

~~~text
Redis key: user:42:profile
Redis TYPE: string
~~~

~~~json
{
  "userId": "42",
  "displayName": "Linh",
  "city": "Ha Noi",
  "loginCount": 7,
  "verified": true
}
~~~

~~~redis
SET user:42:profile '{"userId":"42","displayName":"Linh","city":"Ha Noi","loginCount":7,"verified":true}'
GET user:42:profile
~~~

Redis sees a **String containing JSON bytes**. In this storage model, Redis does not natively understand properties like `city` or `loginCount` as Hash fields.

### 1.3. Multiple Keys: One Key per Attribute or Attribute Group

~~~text
user:42:displayName -> Linh
user:42:city        -> Ha Noi
user:42:loginCount  -> 7
user:42:verified    -> true
~~~

~~~redis
SET user:42:displayName "Linh"
SET user:42:city "Ha Noi"
SET user:42:loginCount 7
SET user:42:verified true

INCR user:42:loginCount
GET user:42:city
~~~

The colon is purely a naming convention. Redis does not create folders or parent–child relationships between keys that share a prefix.

## 2. Comparison Table for Decision-Making

| Question | Flat Hash | JSON in String | Multiple Separate Keys |
|---|---|---|---|
| Reading one attribute? | Direct `HGET` | Usually `GET` whole document then parse | `GET` corresponding key |
| Reading several fields? | `HMGET` | Usually fetch whole document | Multiple `GET` or `MGET` |
| Reading the whole object? | `HGETALL` and assemble fields | `GET` + deserialize | Assemble from multiple keys |
| Modifying one attribute? | `HSET` | Usually re-serialize entire object | `SET` individual key |
| Incrementing a counter? | `HINCRBY` | Read–modify–write unless using another mechanism | `INCR`/`INCRBY` |
| Complex nested objects? | Must flatten or serialize per field | Very natural | Can group into separate keys |
| Typical TTL? | TTL on the entire Hash key | TTL on the entire String key | Independent TTL per key |
| Deleting the whole object? | Single `DEL` | Single `DEL` | Delete all component keys |
| Footprint? | Small Hashes can save memory | Includes JSON property names | Overhead per key |
| Clear Java schema needed? | Per-field mapping | JSON serializer/DTO | Per-key convention |
| Redis Cluster? | One key belongs to one hash slot | One key belongs to one hash slot | Keys may reside in different slots |

Do not treat this table as benchmark results. Real-world performance depends on field count, payload size, update rate, Redis internal encoding, key count, and network round-trips.

## 3. Flat Hash: Choosing It for Independent Fields

A Hash fits a group of relatively flat attributes that are frequently read or modified individually:

~~~text
user:42:profile [Hash]
  displayName   "Linh"
  city          "Ha Noi"
  locale        "vi"
  verified      "true"
  loginCount    "7"
~~~

Key commands:

~~~redis
HSET user:42:profile displayName "Linh" city "Ha Noi"
HGET user:42:profile displayName
HMGET user:42:profile displayName city
HEXISTS user:42:profile verified
HINCRBY user:42:profile loginCount 1
HDEL user:42:profile locale
HLEN user:42:profile
~~~

**Main advantage:** when changing only one field, `HSET` does not have to read and rewrite all the other fields. `HINCRBY` can increment an integer field with a single atomic Redis command.

A single `HSET` with multiple field/value pairs updates those fields in one command execution. If you need to run multiple independent commands and want them committed at the same logical instant, you still need an appropriate transaction or script mechanism.

### 3.1. Fields and Values Do Not Have Automatic Java Types

A Redis Hash stores fields/values as byte data; the application chooses the serializers:

~~~text
field           stored value    expected Java type
displayName     "Linh"          String
loginCount      "8"             long
verified        "true"          boolean
updatedAt       "1790000000"    epoch seconds
~~~

Another service could easily write `loginCount="eight"` with `HSET`. Redis does not treat that as a Hash schema violation; the bug only surfaces when code runs `HINCRBY` or parses the number. Thus, field naming contracts and data formats must still be governed by the application.

If you want to use integer operations like `HINCRBY`, the field must contain a valid integer representation. For monetary values, usually adopt a convention using the smallest integer unit; avoid mixing values like `100.50` with integer-only commands.

### 3.2. Nested Objects Make Hashes Harder to Read

Suppose a user has:

~~~json
{
  "displayName": "Linh",
  "address": {
    "city": "Ha Noi",
    "district": "Ba Dinh"
  },
  "tags": ["premium", "beta"]
}
~~~

You can define flattened field names manually:

~~~text
displayName       -> Linh
address.city      -> Ha Noi
address.district  -> Ba Dinh
tags              -> ["premium","beta"]
~~~

However, `address.city` is simply **a single field name**; Redis does not interpret the dot as a JSON path. If field names are generated from external input, define escaping rules to avoid collisions. Here `tags` is a JSON string, not a Set that supports `SADD`/`SISMEMBER`.

When schemas are deeply nested, have complex arrays, or involve multiple subtypes, JSON can be much clearer. If `tags` needs set operations, splitting it into a dedicated Redis Set is usually the better fit.

### 3.3. Avoid HGETALL for Huge Hashes

~~~redis
HGETALL user:42:profile
HSCAN user:42:profile 0 COUNT 100
~~~

For small Hashes, `HGETALL` is convenient because it fetches every field and value. For very large Hashes, reading everything consumes bandwidth, memory, and Java deserialization time.

If you only need a few fields, use `HMGET`; if you must traverse a large Hash, consider `HSCAN` with a cursor. `COUNT` in SCAN is a hint, not a guarantee of a fixed result size per step.

### 3.4. Hash TTL

~~~redis
HSET user:42:profile displayName "Linh"
EXPIRE user:42:profile 900
TTL user:42:profile
~~~

This TTL is attached to **the entire Hash key**, not automatically to `displayName` or `city` individually. When the key expires, all fields vanish.

An `HSET` updating a field on an existing Hash key normally does not reset the TTL. If sliding expiration is desired, the application must explicitly call `EXPIRE` per its policy.

Some newer Redis versions support per-field Hash expiration. Actual usability depends on the Redis version and driver / Spring Data Redis APIs, so do not assume it is universally available across every system. When independent TTLs and portability across deployments are required, separating keys remains an easy-to-understand model.

## 4. HashOperations in Spring Data Redis

For string-valued fields, `StringRedisTemplate` makes inspection easy via Redis CLI:

~~~java
import java.time.Duration;
import java.util.Map;

import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserProfileHashRepository {

    private final StringRedisTemplate redis;
    private final HashOperations<String, Object, Object> hashes;

    public UserProfileHashRepository(StringRedisTemplate redis) {
        this.redis = redis;
        this.hashes = redis.opsForHash();
    }

    private String key(String userId) {
        return "user:" + userId + ":profile";
    }

    public void saveBasicProfile(String userId, String name, String city) {
        String key = key(userId);

        hashes.putAll(key, Map.of(
                "displayName", name,
                "city", city,
                "verified", "false"));

        redis.expire(key, Duration.ofMinutes(30));
    }

    public String findCity(String userId) {
        Object value = hashes.get(key(userId), "city");
        return value == null ? null : value.toString();
    }

    public long recordLogin(String userId) {
        return hashes.increment(key(userId), "loginCount", 1L);
    }
}
~~~

Here `StringRedisTemplate` uses string serializers for keys, hash keys, and hash values. The `loginCount` field is updated via an atomic increment on Redis, though if another client wrote non-integer content, the operation will fail.

Do not confuse:

~~~java
hashes.put("user:42:profile", "address", someJavaObject);
~~~

with automatically splitting `someJavaObject` into multiple fields. `put` writes only **one field**, and the value object is processed by the configured **hash value serializer**.

If you need to convert a POJO into a field/value map, Spring Data Redis offers Hash mapping mechanisms, or you can define your own mapper. Doing so requires explicitly deciding field names, data types, flattening behavior, null handling, and schema compatibility.

## 5. JSON in a String: The Choice for Structured Snapshots

JSON fits when the application usually reads **the entire document** and the DTO has nested structures.

Example snapshot of an order:

~~~json
{
  "orderId": "O-1001",
  "status": "PAID",
  "customer": {
    "userId": "42",
    "name": "Linh"
  },
  "items": [
    {"sku": "SKU-A", "quantity": 2, "price": 120000},
    {"sku": "SKU-B", "quantity": 1, "price": 80000}
  ],
  "totalAmount": 320000
}
~~~

A single `GET order:O-1001:snapshot` fetches the entire document, and Jackson maps it back into a DTO. This model is far more natural than creating `items.0.sku`, `items.0.quantity`, `items.1.sku`, ... as numerous Hash fields.

### 5.1. Storing JSON with Spring Data Redis

Illustrative DTOs:

~~~java
import java.util.List;

public record OrderLine(String sku, int quantity, long price) {}

public record OrderSnapshot(
        String orderId,
        String status,
        String customerId,
        List<OrderLine> items,
        long totalAmount) {}
~~~

Configuring a template with an explicit target type (e.g., Spring Data Redis 3.x, Jackson 2):

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class OrderCacheRedisConfiguration {

    @Bean("orderSnapshotTemplate")
    RedisTemplate<String, OrderSnapshot> orderSnapshotTemplate(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper) {

        RedisTemplate<String, OrderSnapshot> template =
                new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(
                        objectMapper, OrderSnapshot.class));

        return template;
    }
}
~~~

Service using the template:

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderSnapshotCache {

    private final RedisTemplate<String, OrderSnapshot> redis;

    public OrderSnapshotCache(
            @Qualifier("orderSnapshotTemplate")
            RedisTemplate<String, OrderSnapshot> redis) {
        this.redis = redis;
    }

    public void save(OrderSnapshot snapshot) {
        redis.opsForValue().set(
                "order:" + snapshot.orderId() + ":snapshot",
                snapshot,
                Duration.ofMinutes(10));
    }

    public OrderSnapshot find(String orderId) {
        return redis.opsForValue().get(
                "order:" + orderId + ":snapshot");
    }
}
~~~

Because `OrderSnapshot` is a concrete target type, the serializer can reconstruct the DTO without embedding Java class names in the root payload. If the DTO contains polymorphic fields such as interfaces or abstract classes, subtype resolution must be configured separately.

**A Redis String containing JSON is still a String.** You cannot call `opsForHash().get(key, "status")` on that same key: Redis will return a `WRONGTYPE` error.

### 5.2. Weakness of JSON: Updating a Single Field

Suppose you want to increment `loginCount` inside a JSON String:

~~~text
GET <key>
   |
   v
Deserialize JSON -> Java object
   |
   v
Increment loginCount in Java
   |
   v
Serialize object -> new JSON
   |
   v
SET <key> <new JSON>
~~~

This is a **multi-command sequence** without end-to-end atomicity.

Example of two concurrent requests:

~~~text
Initial value: {"city":"Ha Noi","loginCount":7}

Thread A reads the old version.
Thread B reads the old version.

A changes city to "Da Nang", SETs the whole JSON.
B increments loginCount to 8, SETs the whole JSON.

The result may be:
{"city":"Ha Noi","loginCount":8}

A's update is overwritten.
~~~

Even though each `SET` is atomic, the read–modify–write cycle can cause a **lost update**. You can use optimistic locking (`WATCH`/`MULTI`/`EXEC`) or scripts when necessary, but if a field increments frequently, a Hash field or separate String counter key can be much simpler.

### 5.3. How SET Affects TTL

~~~redis
SET order:O-1001:snapshot '{"status":"PAID"}' EX 600
TTL order:O-1001:snapshot

SET order:O-1001:snapshot '{"status":"SHIPPED"}'
TTL order:O-1001:snapshot
~~~

The second `SET` does not ask to keep the TTL or set a new TTL, so by default it clears the prior expiration. The cache may stay alive longer than expected.

Therefore, when updating a JSON cache, standardize a policy: reset the TTL, preserve the TTL via the corresponding API option, or invalidate and let the service reload a fresh snapshot.

### 5.4. Distinguishing JSON String from RedisJSON

A Redis deployment may expose commands like `JSON.GET`/`JSON.SET` via RedisJSON capabilities in that deployment. However, that is **a different feature** from storing JSON bytes in a String via `SET`.

Do not assume:

~~~java
redis.opsForValue().get("order:O-1001:snapshot");
~~~

automatically supports `$.customer.name` or JSON paths. With a plain JSON String, you must read the whole value. If the system plans to use RedisJSON, verify Redis version, server configuration, client support, and deployment requirements.

## 6. Multiple Separate Keys: When Independent Lifecycles Are Needed

Suppose a user has these data groups:

~~~text
user:42:profile      [Hash]   name, city, verified
user:42:session      [String] token, TTL 30 minutes
user:42:loginCount   [String] counter
user:42:tags         [Set]    premium, beta
user:42:preferences  [String] JSON, TTL 1 day
~~~

You do not have to store every single attribute as its own String key. **"Multiple separate keys" lets each key use the right Redis data structure.**

~~~redis
SET user:42:session "session-abc" EX 1800
INCR user:42:loginCount
SADD user:42:tags "premium" "beta"
SET user:42:preferences '{"theme":"dark"}' EX 86400
~~~

Benefits:

- The session has a short TTL while the counter follows its own lifecycle.
- Incrementing the counter with `INCR` does not touch the profile.
- The tag set uses `SADD` and `SISMEMBER` without parsing JSON arrays.
- Each group can be deleted or refreshed independently.

Trade-offs:

- Extra metadata overhead per key; if each user has dozens of tiny keys, total overhead can grow large.
- Deleting a user requires knowing all component keys.
- Combining multiple keys does not automatically guarantee a point-in-time snapshot.
- Multi-key operations in Redis Cluster must obey hash-slot rules.

### 6.1. Spring Data Redis with Separate Keys

~~~java
import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class UserKeysRepository {

    private final StringRedisTemplate redis;

    public UserKeysRepository(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private String prefix(String userId) {
        return "user:" + userId + ":";
    }

    public void updateCity(String userId, String city) {
        redis.opsForValue().set(prefix(userId) + "city", city);
    }

    public long incrementLoginCount(String userId) {
        Long value = redis.opsForValue()
                .increment(prefix(userId) + "loginCount");

        if (value == null) {
            throw new IllegalStateException("No Redis result");
        }
        return value;
    }

    public void saveSession(String userId, String session) {
        redis.opsForValue().set(
                prefix(userId) + "session",
                session,
                Duration.ofMinutes(30));
    }
}
~~~

For a set of tags:

~~~java
redis.opsForSet().add("user:42:tags", "premium", "beta");

Boolean isPremium = redis.opsForSet()
        .isMember("user:42:tags", "premium");
~~~

A `user:42:tags` key using a Redis Set is more efficient than a JSON array if the main operations are membership checks, deduplication, and set operations.

### 6.2. Reading the Whole Object Across Multiple Keys

If all attributes are Strings:

~~~java
String name = redis.opsForValue().get("user:42:name");
String city = redis.opsForValue().get("user:42:city");
String verified = redis.opsForValue().get("user:42:verified");
~~~

You can use `multiGet` for compatible keys:

~~~java
import java.util.List;

List<String> values = redis.opsForValue().multiGet(List.of(
        "user:42:name",
        "user:42:city",
        "user:42:verified"));
~~~

This reduces round-trips when an appropriate multi-key command can execute. You must handle missing keys, result ordering, and Redis Cluster constraints. If each key is updated at different times, assembling them into a DTO can still yield values from different versions.

If the application frequently needs a **consistent snapshot**, a single Hash or JSON key can be easier to manage.

### 6.3. Deleting Keys by Prefix Is Not Automatic

~~~redis
DEL user:42
~~~

does not delete:

~~~text
user:42:name
user:42:city
user:42:loginCount
~~~

If the key set is known beforehand, delete by explicit list. If keys are dynamic, maintain an index/membership tracking structure or use controlled `SCAN` passes within appropriate bounds. Avoid `KEYS user:42:*` on large keyspaces because it can cause undesirable blocking load.

## 7. TTL Often Decides Whether to Split Keys

Ask the question: **do the attributes share the same lifecycle?**

| Scenario | Suggestion |
|---|---|
| Entire cached profile expires after 30 minutes | Hash or JSON |
| Session expires after 30 minutes, profile after 30 days | Split session into a separate key |
| Daily visit counter | Separate per-day key with TTL |
| Some attributes never have a TTL | Separate from short-lived cache groups |
| Each field needs its own TTL | Consider multiple keys or field expiration where supported |
| Want to extend the entire object on activity | Hash/JSON sharing one TTL can be simpler |

Example:

~~~text
user:42:profile     -> TTL 30 days
user:42:session     -> TTL 30 minutes
user:42:lastSeen    -> TTL 5 minutes
~~~

A single Redis Hash generally does not fit if individual attributes must expire on different schedules and the system does not use field expiration. Conversely, if all fields expire together, splitting into 20 String keys adds unnecessary management overhead.

## 8. Atomicity and Consistency Under Concurrent Writes

Atomicity of a single Redis command differs from atomicity of an entire workflow.

### 8.1. Hash: Updating One Field with One Command

~~~redis
HINCRBY user:42:profile loginCount 1
~~~

Two clients concurrently incrementing the same field with `HINCRBY` will not suffer lost updates like manual `HGET` then `HSET`. If two clients both `HSET city` with different values, the final value still depends on whichever command executes later.

### 8.2. JSON: SET Is Atomic, the GET–SET Sequence Is Not

~~~redis
SET user:42:snapshot '{"city":"Da Nang","loginCount":8}'
~~~

`SET` replaces the whole JSON as one value. However, two threads reading the same old version to edit two different properties can overwrite each other. If you need version checks before writing, consider `WATCH`/transactions or scripts with an appropriate retry policy.

### 8.3. Multiple Keys: Each SET Is a Separate Command

~~~redis
SET user:42:city "Da Nang"
SET user:42:verified "true"
~~~

These are two separate updates. An interleaved reader can observe the new `city` with the old `verified`.

When business logic requires all attributes to change as a single unit, you can package them in one JSON String, one multi-field `HSET`, or use transactions/scripts with proper semantics; never assume consecutive commands are atomic.

### 8.4. Atomicity Does Not Guarantee Retry Safety

If the network drops after Redis executes `INCR` or `HINCRBY` but before the client receives the reply, a retry may increment a second time for the same event. When using Redis for critical workflows, add idempotency or an appropriate result-confirmation mechanism.

## 9. Memory, Network, and Performance

The most important metric is not the DTO's field count, but the **actual access pattern and data size**.

Suppose a JSON object is 20 KB, yet every request only needs `verified`:

- Hash: `HGET key verified` returns one tiny field.
- JSON String: `GET key` returns all 20 KB to parse, even though only one property is needed.
- Separate key: `GET user:42:verified` returns one small value.

Conversely, if the screen always needs **all 20 KB**, a JSON String requires only one `GET` and one deserialization; multiple separate keys might have to stitch many responses together.

### 9.1. Per-Key Overhead

Every Redis key carries metadata, allocator, and structural overhead. With one million users and 20 fields per user:

~~~text
One Hash per user:
    roughly 1 million Hash keys

One String key per field:
    roughly 20 million String keys
~~~

Total key count can affect memory, expiration sweeps, scans, and operations. Small Hashes can also use compact internal encodings within specific configuration/version limits. Still, large Hashes carry their own costs; never assume exact memory savings without measuring.

### 9.2. Inspection Commands

~~~redis
MEMORY USAGE user:42:profile
HLEN user:42:profile
STRLEN user:42:snapshot
INFO memory
DBSIZE
~~~

For the multi-key model, sum `MEMORY USAGE` across all component keys. Comparing one Hash key holding 20 fields against one String key holding one field is not an apples-to-apples comparison.

When benchmarking, measure:

- Number of Redis commands and round-trips per request.
- Bytes transferred over the network.
- Object/cache size and per-field update frequency.
- JVM CPU spent on serialization/deserialization.
- Redis memory and latency under high load.
- Total key count and cleanup/expiration overhead.

## 10. Redis Cluster and Multi-Key Considerations

Redis Cluster partitions the keyspace into hash slots.

Both Hash and JSON each use **one key**, so all data for that key belongs to one hash slot. Redis does not automatically distribute fields of the same Hash across multiple nodes.

With multiple keys:

~~~text
user:42:name
user:42:city
user:42:loginCount
~~~

the keys may map to different slots. Multi-key commands can only execute within Cluster's same-slot constraints when required.

When related keys genuinely must reside in the same slot, you can use **hash tags**:

~~~text
user:{42}:name
user:{42}:city
user:{42}:loginCount
~~~

Keys sharing hash tag `42` map to the same slot. Do not group all users under a tag like `{users}`: all keys would pile into one slot, defeating load distribution.

An excessively large Hash can also create a hotspot because all fields live inside one key. Never store all users as fields of a single `all-users` key just to reduce key count.

## 11. Business Examples for Choosing Properly

### 11.1. User Profile

~~~text
name, city, locale, verified, loginCount
~~~

If frequently reading/editing individual fields with a shared TTL, choose:

~~~text
user:42:profile [Hash]
~~~

`HMGET` fetches needed fields; `HINCRBY` increments `loginCount` when the data contract fits.

### 11.2. Order Snapshot

~~~text
orderId, customer {...}, items [...], shipping {...}, totals {...}
~~~

If the UI typically loads the entire snapshot, JSON String fits. Primary transactional data should live in the canonical business store, with the Redis snapshot invalidated or refreshed when data changes.

### 11.3. Shopping Cart with Per-SKU Quantities

~~~text
cart:42 [Hash]
  SKU-A -> 2
  SKU-B -> 1
~~~

~~~redis
HSET cart:42 SKU-A 2 SKU-B 1
HINCRBY cart:42 SKU-A 1
HDEL cart:42 SKU-B
EXPIRE cart:42 604800
~~~

A Hash works well when each field is a quantity for a SKU. If each item contains rich nested options, a different schema may be needed.

### 11.4. Session and Separate Counter

~~~text
user:42:session     [String, TTL 30 minutes]
user:42:loginCount  [String, counter]
~~~

~~~redis
SET user:42:session "session-abc" EX 1800
INCR user:42:loginCount
~~~

Separate keys because TTL and operation types differ.

### 11.5. Tags

~~~text
user:42:tags [Set]
~~~

~~~redis
SADD user:42:tags premium beta
SISMEMBER user:42:tags premium
~~~

When you need unique element sets or set intersections/unions, a Redis Set fits better than either a JSON array or a bunch of String keys.

## 12. Hybrid Modeling in Real Applications

A product might use:

~~~text
product:1001:profile      [Hash]
  name, category, brand

product:1001:snapshot     [String JSON]
  images, description, specifications, ...

product:1001:stock        [String counter]
  25

product:1001:tags         [Set]
  keyboard, accessory

product:1001:views:daily  [String counter]
  820
~~~

Each group serves one access pattern:

- Flat profile for reading/editing short fields.
- JSON snapshot for rendering the detail page.
- Stock/counter with dedicated increment/decrement rules (actual inventory must be protected by appropriate business logic).
- Tags needing set operations.
- Views having a TTL per reporting window.

If product information is duplicated across both profile and snapshot, identify **which data source is canonical**, when caches must be refreshed, and how the application handles stale data. The convenience of having multiple copies always comes with synchronization responsibility.

## 13. Mistakes to Avoid

### "One Java DTO = One Redis Hash"

No. Multi-level nested DTOs that are typically read as a whole may fit JSON better. A Redis Hash fits field-level access.

### "With JSON, updating one property is also cheap"

With standard Redis String JSON, the application must read/write the entire value. JSON-path operations require other capabilities, such as RedisJSON if infrastructure and client support it.

### "Hashes allow per-field TTL on every Redis"

Normally TTL attaches to the key. Field expiration depends on version and support level; do not assume it exists in every environment.

### "One key per attribute is always more flexible"

Many keys increase overhead and complicate snapshots and cleanup. Split only when access patterns, TTLs, or data types differ.

### "HGETALL is always good because it is just one command"

If the Hash is large, the reply can be massive. Use `HGET`/`HMGET` when only a few fields are needed.

### "Using the same prefix makes Redis manage the key group automatically"

Redis has no parent–child relationship based on `:`. To clean up all related keys, maintain a list, an index, or run controlled scans.

### "SET with new JSON preserves the old TTL"

Standard `SET` does not preserve TTL by default. Set, extend, or keep TTL explicitly using the appropriate API.

### "Two threads updating via RedisTemplate are automatically consistent"

The template can be shared safely across threads, but it does not turn a read–modify–write sequence into a transaction. Use atomic commands, optimistic locking, or appropriate business mechanisms.

## 14. Migrating Between Hash, JSON, and Multiple Keys

Suppose you previously stored JSON at:

~~~text
user:42:profile [String JSON]
~~~

and want to switch to a Hash. Do not run `HSET` directly on the key that is currently a String, because Redis will return `WRONGTYPE`.

A migration approach for reconstructible caches:

1. Design the new schema, serializers, and TTL.
2. Use a new namespace such as `user:42:profile:v2`.
3. Have new application instances write/read the v2 structure; on miss, load from the primary data source.
4. Maintain compatibility reads or let old keys expire via TTL during rollout.
5. Monitor cache misses, deserialization errors, and v1 key presence.
6. Remove legacy reads/writes once no application depends on them.

If Redis data is the primary store, migration requires stricter control: snapshots, data reconciliation, write coordination during cutover, and a rollback plan. Do not treat cache migration and primary business-data migration as the same thing.

Schemas can also change while **the Redis data type stays the same**. JSON serializers may use class metadata or schema versions; Hashes need explicit field conventions. Keep a compatible format across rolling-deployed instances, or use versioned namespaces so old and new writers/readers do not overwrite each other with incompatible data.

## 15. Decision Tree

~~~mermaid
flowchart TD
    A[Need to store an object in Redis] --> B{Does app usually read whole object?}
    B -->|Yes| C[JSON String with explicit DTO]
    B -->|No| D{Are fields mostly flat?}
    D -->|Yes| E{Do they share the same TTL?}
    E -->|Yes| F[Redis Hash]
    E -->|No| G[Split keys by lifecycle]
    D -->|No| H[JSON or split data groups]
    G --> I{Need specialized operations?}
    I -->|Yes| J[String counter, Set, ZSet, List, Stream...]
    I -->|No| K[String keys or grouped Hashes]
    C --> L[Verify concurrency, TTL, and serializers]
    F --> L
    H --> L
    J --> L
    K --> L
~~~

After making a preliminary choice, check:

1. Does a request fetch one field, a group of fields, or the entire object?
2. Which attributes change frequently and can leverage atomic commands?
3. Which attributes need independent TTLs?
4. Does the data have nested objects or complex arrays?
5. Must multiple fields/keys update as a single unit?
6. Does Redis Cluster require the same hash slot for multi-key operations?
7. What are the actual key counts and data sizes?
8. Are schemas/serializers compatible across services and application versions?
9. Is Redis a reconstructible cache or data that must persist reliably?

## 16. Conclusion

**Choose a flat Hash** when an object consists of simple fields, is often read or updated field-by-field, and most fields share a lifecycle. The primary API is `opsForHash()`, with `HGET`, `HMGET`, `HSET`, and `HINCRBY`.

**Choose JSON in a Redis String** when an object has nested structure and the application usually reads the whole snapshot. Use `opsForValue()` with explicit JSON serializers/schemas; watch out for full-document read–write costs, TTL handling, and lost updates.

**Choose multiple separate keys** when groups of data differ in TTL, update frequency, access control, or operation types. Pick String counters, Sets, Sorted Sets, Hashes, or other structures per group while managing key counts, cleanup, and consistency.

In practice, **an intentional hybrid design** is usually more effective than forcing all data into a single type. A good Redis model enables the application to perform the exact operations it needs with balanced round-trips, storage cost, and coordination complexity.
