# Reading and Writing Multiple Keys with `multiGet` and `multiSet` in Spring Data Redis

When a page needs to display 20 products, an API needs to fetch statuses for multiple accounts, or a job needs to preload several cache entries, calling Redis `GET` individually for each key increases network round-trips. Redis supports multi-key operations via **`MGET`** (read multiple values) and **`MSET`** (write multiple key–value pairs). In Spring Data Redis, these two commands are exposed through `ValueOperations.multiGet(...)` and `ValueOperations.multiSet(...)`.

Both APIs are useful when working with **Redis strings**: each Redis key stores a binary value, which can be a UTF-8 string, JSON, or a format defined by the application's serializer. To use them properly, you need to understand result ordering, non-existent keys, TTL, overwrite behavior, atomicity, and Redis Cluster constraints.

## 1. Problem: Reading and Writing Keys One by One or in Groups?

Suppose a catalog service caches product names under keys:

```text
shop:catalog:product-name:p101 -> "Keyboard"
shop:catalog:product-name:p102 -> "Mouse"
shop:catalog:product-name:p103 -> "Monitor"
```

If reading one key at a time:

```redis
GET shop:catalog:product-name:p101
GET shop:catalog:product-name:p102
GET shop:catalog:product-name:p103
```

The application must execute three Redis command operations. When each command is sent and awaited separately, network overhead grows with the number of keys.

Replace with a single command:

```redis
MGET shop:catalog:product-name:p101 shop:catalog:product-name:p102 shop:catalog:product-name:p103
```

Redis returns the values in the exact order of the requested keys:

```text
1) "Keyboard"
2) "Mouse"
3) "Monitor"
```

Similarly, instead of sending three separate `SET` commands, you can write with:

```redis
MSET shop:catalog:product-name:p101 "Keyboard" shop:catalog:product-name:p102 "Mouse" shop:catalog:product-name:p103 "Monitor"
```

That is the basis for these Spring Data Redis methods:

| Redis Command | Spring Data Redis API | Meaning |
|---|---|---|
| `GET key` | `opsForValue().get(key)` | Read one value |
| `SET key value` | `opsForValue().set(key, value)` | Write one value |
| `MGET key1 key2 ...` | `opsForValue().multiGet(keys)` | Read values of multiple keys |
| `MSET key1 value1 key2 value2 ...` | `opsForValue().multiSet(map)` | Write multiple key–value pairs |
| `MSETNX key1 value1 ...` | `opsForValue().multiSetIfAbsent(map)` | Write all only if every key does not exist yet |

`multiGet` and `multiSet` are APIs of **`ValueOperations<K,V>`**, so they apply to **Redis string value** operations. Do not confuse them with operations on multiple fields inside a single Redis hash.

## 2. Processing Flow in Spring Data Redis

In a Spring Boot application, we typically use `StringRedisTemplate` when both keys and values are strings:

```text
Controller / Service
       |
       v
StringRedisTemplate
       |
       v
ValueOperations<String, String>
       |                 |
       | multiGet(keys)  | multiSet(map)
       v                 v
RedisConnectionFactory (Lettuce or Jedis)
       |
       v
Redis connection
       |
       v
MGET / MSET on Redis
```

With `RedisTemplate<String, Product>`, behavior is similar, except `keySerializer` encodes key names and `valueSerializer` encodes objects into `byte[]` before sending commands. On read, values are decoded using the configured serializer.

Neither method **chooses a Redis data type based on a Java class**: Redis receives keys and values as bytes. JSON stored via `multiSet` remains a **Redis string containing JSON**, and does not automatically become a Redis hash.

## 3. Basic Spring Boot Configuration

Example for Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
```

Spring Boot typically provides `RedisConnectionFactory` and `StringRedisTemplate` automatically when auto-configuration conditions match. A service can inject the template:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CatalogCache {
    private final StringRedisTemplate redis;

    public CatalogCache(StringRedisTemplate redis) {
        this.redis = redis;
    }
}
```

The example assumes Redis is running at `localhost:6379`. When the application runs inside a container, the Redis address must be configured according to the actual network; `localhost` inside a container does not point to another Redis container.

## 4. `multiGet`: Reading Multiple Keys in Exact Order

Method signature:

```java
List<V> multiGet(Collection<K> keys);
```

Invoked via `redisTemplate.opsForValue()`. Returned values correspond to the keys **in the iteration order of the passed collection**.

Example:

```java
List<String> keys = List.of(
        "shop:catalog:product-name:p101",
        "shop:catalog:product-name:p102",
        "shop:catalog:product-name:p103"
);

List<String> values = redis.opsForValue().multiGet(keys);
```

If all three keys exist, `values` corresponds to:

```text
[
  "Keyboard",
  "Mouse",
  "Monitor"
]
```

Crucially, **the value at index `i` corresponds to the key at index `i`**. Redis does not return a `Map<String,String>` containing both keys and values; it returns a sequence of values. Spring Data Redis decodes that sequence into a `List<V>`.

### 4.1. Non-Existent Keys Are Represented by `null`

Suppose `p102` is not cached yet:

```redis
MGET shop:catalog:product-name:p101 shop:catalog:product-name:p102 shop:catalog:product-name:p103
```

Redis-level result:

```text
1) "Keyboard"
2) (nil)
3) "Monitor"
```

At the Java level, the typical result behaves like:

```java
List<String> values = List.of(...); // Illustrates the idea; do not use List.of with null.
```

The actual data representation must allow `null` elements, such as:

```text
values.get(0) == "Keyboard"
values.get(1) == null
values.get(2) == "Monitor"
```

`List.of(...)` in Java **does not allow `null` elements**. Therefore, you cannot use it to build a mock list containing missing returned values. The list returned by `multiGet` can contain `null` at positions for non-existent keys.

Additional note: Redis `MGET` returns nil for any key without a valid string value, including both non-existent keys and keys holding a non-string Redis type. If an unexpected `null` appears, check `TYPE key` and the serializer contract; do not immediately assume it is merely a cache miss.

### 4.2. Choose a Collection with Stable Ordering

Pass a `List<String>` if you need to zip results back to the original IDs. `HashSet` provides no business-guaranteed iteration order; creating a `Map` from results can also lose duplicate-key positions.

Example:

```java
List<String> keys = List.of("k3", "k1", "k2");
List<String> values = redis.opsForValue().multiGet(keys);

// values[0] belongs to k3
// values[1] belongs to k1
// values[2] belongs to k2
```

If the input has duplicate keys, the output sequence still matches each requested position. When converting to a `Map`, duplicate keys merge; that may be intentional, yet it no longer preserves the full input list.

### 4.3. The Return Value of the Call Itself Can Also Be `null`

In normal synchronous execution, `multiGet` returns a list of elements matching the keys. However, Spring Data Redis APIs may return **`null` for the method result itself** when the operation is queued inside a pipeline or transaction: actual results are collected and returned later.

Therefore, distinguish:

- `values != null` with `values.get(i) == null`: usually the `i`-th key has no readable string value.
- `values == null`: may be due to a pipeline/transaction context; you cannot conclude all keys are missing.

When using regular `multiGet` in a service, check `values == null` so you do not accidentally equate this case with a cache miss.

## 5. Complete Java Example: Reading Multiple Products and Preserving ID Mapping

Suppose a service receives a list of product IDs and wants to return data in the same input order. A result record keeps both ID and payload explicit:

```java
package com.example.shop.redis;

public record CachedProduct(String productId, String json) {
    public boolean found() {
        return json != null;
    }
}
```

Service:

```java
package com.example.shop.redis;

import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductBatchCache {

    private final StringRedisTemplate redis;

    public ProductBatchCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private static String key(String id) {
        Objects.requireNonNull(id, "productId");
        if (id.isBlank()) {
            throw new IllegalArgumentException("productId must not be blank");
        }
        return "shop:catalog:product-json:v1:" + id;
    }

    public List<CachedProduct> readMany(List<String> productIds) {
        Objects.requireNonNull(productIds, "productIds");

        if (productIds.isEmpty()) {
            return List.of();
        }

        List<String> keys = productIds.stream()
                .map(ProductBatchCache::key)
                .toList();

        List<String> payloads = redis.opsForValue().multiGet(keys);

        if (payloads == null) {
            throw new IllegalStateException(
                    "multiGet result unavailable in this execution context");
        }
        if (payloads.size() != productIds.size()) {
            throw new IllegalStateException(
                    "Unexpected number of Redis values");
        }

        List<CachedProduct> result = new ArrayList<>(productIds.size());
        for (int i = 0; i < productIds.size(); i++) {
            result.add(new CachedProduct(
                    productIds.get(i),
                    payloads.get(i)
            ));
        }
        return result;
    }
}
```

If Redis has `p101` and `p103` but lacks `p102`, `readMany(List.of("p101","p102","p103"))` returns three elements, where the second has `json == null` and `found() == false`.

In a cache-reading API, you can collect the missing IDs, query the primary data source, and backfill the cache. Handle each missing ID carefully, and **never strip `null` positions before zipping the remaining values sequentially**, as that will assign products to the wrong IDs.

The `key(...)` helper above only illustrates centralized key naming. When IDs come from external input, the application should validate or encode IDs under an agreed namespace rule, especially if IDs could contain delimiters, control characters, or sensitive data.

## 6. `multiSet`: Writing Multiple Key–Value Pairs in One Command

`ValueOperations` method:

```java
void multiSet(Map<? extends K, ? extends V> m);
```

Example:

```java
Map<String, String> products = new LinkedHashMap<>();
products.put("shop:catalog:product-name:p101", "Keyboard");
products.put("shop:catalog:product-name:p102", "Mouse");
products.put("shop:catalog:product-name:p103", "Monitor");

redis.opsForValue().multiSet(products);
```

`LinkedHashMap` makes the example easy to read and deterministic in insertion order, though `MSET` does not require ordered key–value pairs for correctness: each key is bound to its own value.

`multiSet` typically does not return a list of values or count of written keys. If the command completes successfully, the pairs are written according to Redis `MSET` semantics.

### 6.1. `MSET` Overwrites Existing Keys

If Redis already holds:

```text
shop:catalog:product-name:p101 -> "Old keyboard"
```

Calling `multiSet` with `"Keyboard"` replaces the current value. `MSET` is not a write-only-if-absent operation.

When a key of another Redis type already exists, `MSET` can replace that key with a Redis string. Clear key naming and write ownership are therefore essential, especially when multiple services share Redis.

### 6.2. `MSET` Does Not Set TTL

Redis `MSET` does not accept per-key expiration parameters like `SET key value EX seconds`. Every pair is written without a new expiry; **existing TTLs on replaced keys are also dropped** under `MSET` overwrite semantics.

Example:

```redis
SET demo:batch:a "old" EX 30
TTL demo:batch:a
MSET demo:batch:a "new" demo:batch:b "second"
TTL demo:batch:a
```

After `MSET`, `TTL demo:batch:a` typically returns `-1`, meaning the key exists without an expiration time. This is critical if the keys represent caches or sessions intended to be short-lived.

### 6.3. `MSET` Is Atomic at the Single-Command Level on One Redis Server

On a single Redis server, `MSET` writes all key–value pairs as **one atomic command**: another client cannot observe an intermediate state where only some keys from the same `MSET` command are updated before the rest.

However, that atomicity does not cover other commands before or after it, does not guarantee relational data consistency in an external database, and does not constitute a distributed business transaction.

## 7. Java Example: Writing Multiple JSON Payloads

In an application using `StringRedisTemplate`, you can serialize objects to JSON at the application layer and use `multiSet` to write multiple values:

```java
package com.example.shop.redis;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductBatchWriter {

    private final StringRedisTemplate redis;

    public ProductBatchWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void writeMany(Map<String, String> jsonByProductId) {
        Objects.requireNonNull(jsonByProductId, "jsonByProductId");

        if (jsonByProductId.isEmpty()) {
            return;
        }

        Map<String, String> redisEntries = new LinkedHashMap<>();

        jsonByProductId.forEach((id, json) -> {
            Objects.requireNonNull(id, "productId");
            Objects.requireNonNull(json, "json");
            if (id.isBlank()) {
                throw new IllegalArgumentException("productId must not be blank");
            }
            redisEntries.put(
                    "shop:catalog:product-json:v1:" + id,
                    json
            );
        });

        redis.opsForValue().multiSet(redisEntries);
    }
}
```

Example input:

```java
writer.writeMany(Map.of(
        "p101", "{\"name\":\"Keyboard\"}",
        "p102", "{\"name\":\"Mouse\"}"
));
```

At this point Redis stores **two string keys**, each holding JSON text. `StringRedisTemplate` does not validate JSON syntax. If you want to write Java objects directly, use `RedisTemplate<String, Product>` with an appropriate serializer and ensure all readers share the same format contract.

**Note:** This approach fits data that needs no TTL or has an intentionally separate expiry policy. For caches that must expire, consider the alternatives in the next section.

## 8. TTL: When Should You Avoid `multiSet`?

`ValueOperations.set(key, value, timeout)` lets you set a TTL per write:

```java
redis.opsForValue().set(
        "shop:catalog:product-json:v1:p101",
        "{\"name\":\"Keyboard\"}",
        Duration.ofMinutes(10)
);
```

Meanwhile, `multiSet(Map)` has no corresponding overload accepting a TTL for the whole map. One might try:

```java
redis.opsForValue().multiSet(values);
values.keySet().forEach(key ->
        redis.expire(key, Duration.ofMinutes(10))
);
```

However, **these are multiple commands**: `MSET` finishes first, then `EXPIRE` commands are sent one by one. If the application loses connection midway, keys may remain without TTL. Other clients can also read the keys before all `EXPIRE` commands complete.

For caches, a clearer and generally safer approach is calling `set(key, value, ttl)` per key and, when round-trips must be reduced, **pipelining** the independent `SET` commands. This reduces round-trip cost, though it does not turn multiple commands into one combined atomic operation.

If multiple keys must be updated and given TTLs **in a single atomic operation**, design a suitable solution such as a Lua script or Redis transaction, verifying Redis Cluster constraints. A Lua script/chunk must be designed with bounded work and careful data-type and error handling; do not introduce it solely to avoid a few network commands when data does not require atomicity.

| Need | Typically Suitable Approach |
|---|---|
| Write multiple string values, no TTL needed | `multiSet(map)` |
| Write one value with TTL | `set(key, value, Duration)` |
| Write multiple values with individual TTLs | Loop `set(..., ttl)`, optionally pipelined |
| Multiple keys must update atomically in same slot | Consider `MSET` or same-slot script/transaction |
| Cache can be recomputed when missing | Allow cache misses and refill; avoid overcomplicating |

## 9. `multiSetIfAbsent`: Write Only When All Keys Do Not Exist Yet

Alongside `multiSet`, `ValueOperations` also provides:

```java
Boolean multiSetIfAbsent(Map<? extends K, ? extends V> m);
```

This corresponds to Redis `MSETNX`. Unlike individual `SETNX` commands, `MSETNX` checks **the entire group of keys**: if **any key** already exists, the command writes none of the pairs in the group.

Example:

```redis
SET demo:batch:existing "value"
MSETNX demo:batch:existing "new" demo:batch:other "other"
```

The result is `0` (nothing written). `demo:batch:existing` keeps `"value"`, and `demo:batch:other` is still not created.

If none of the keys exist yet:

```redis
MSETNX demo:batch:new1 "a" demo:batch:new2 "b"
```

The result is `1` and both keys are created.

In Java:

```java
Map<String, String> initial = Map.of(
        "demo:batch:new1", "a",
        "demo:batch:new2", "b"
);

Boolean inserted = redis.opsForValue().multiSetIfAbsent(initial);

if (Boolean.TRUE.equals(inserted)) {
    // All keys were absent and were written.
} else if (Boolean.FALSE.equals(inserted)) {
    // At least one key already existed; no keys were written.
} else {
    // Result may be returned later in a pipeline/transaction.
}
```

`MSETNX` does not set TTL automatically and is not a full distributed locking mechanism. For locks, you must design leases, owner tokens, safe release, and crashed-process handling.

## 10. Distinguishing `multiGet` from Multi-Field Operations in a Redis Hash

Two Spring Data Redis APIs share the name `multiGet` but belong to two different groups:

| API | Equivalent Command | Data Model |
|---|---|---|
| `redis.opsForValue().multiGet(redisKeys)` | `MGET` | Multiple Redis keys, each holding a string value |
| `redis.opsForHash().multiGet(redisKey, fields)` | `HMGET` | Multiple fields inside **one** Redis hash key |

Example data:

```redis
HSET shop:catalog:inventory:p101 available 25 reserved 4 warehouse "HCM"
```

To fetch the two fields `available` and `reserved`:

```java
List<Object> values = redis.opsForHash().multiGet(
        "shop:catalog:inventory:p101",
        List.of("available", "reserved")
);
```

Corresponding Redis command:

```redis
HMGET shop:catalog:inventory:p101 available reserved
```

Do not pass the **fields** `available`, `reserved` to `opsForValue().multiGet`, because they are not independent Redis keys.

Likewise, `opsForHash().putAll(redisKey, map)` writes multiple fields of one Redis hash; `opsForValue().multiSet(map)` writes multiple Redis string keys. They differ in data type, access semantics, and keyspace design.

## 11. Redis Cluster: Hash Slot Limits for Multi-Key Commands

Redis Cluster distributes keys across **16,384 hash slots**. Redis requires keys involved in an atomic multi-key command on a node to reside in the **same slot**. For native `MGET`, `MSET`, and `MSETNX`, sending keys belonging to different slots directly to Cluster can return a `CROSSSLOT` error.

Example:

```text
shop:cart:101:items
shop:cart:101:total
```

Even though both names share a prefix, they do not automatically share a hash slot. Redis computes the slot from the key content, not from a `:`-delimited prefix segment.

### 11.1. Use Hash Tags When Multiple Keys Must Share a Slot

Redis Cluster supports **hash tags**: if a key name contains a valid pair of curly braces, Redis hashes only the substring inside the braces to compute the slot.

```text
shop:cart:{101}:items
shop:cart:{101}:total
```

Both keys have hash tag `101`, so they land in the same slot and can participate in a single `MGET` or `MSET` command on Cluster.

Verify with Redis CLI:

```bash
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT 'shop:cart:{101}:items'
redis-cli -c -h redis-node-1 -p 6379 CLUSTER KEYSLOT 'shop:cart:{101}:total'
```

Both outputs must match. The node address is only an example; substitute your lab environment's Redis Cluster endpoint.

Hash tags should only group keys that **truly need to be operated on together**. Using `{shop}` on every key in the application forces all of them into one slot, leading to poor load distribution and hot spots.

### 11.2. Clients May Handle Cross-Slot Operations Differently

Some clients/frameworks may split multi-key reads into commands sent to individual nodes and aggregate the results. That depends on the driver, version, and API. Never assume every cross-slot `multiGet` runs a single atomic native `MGET`; nor assume a cross-slot `multiSet` has the same atomicity as a single command on one node.

If the application requires **guaranteed atomic semantics**, design related keys into the same slot and use commands/transactions supported by Redis Cluster for that case. If the application only reads independent cached entries across slots, aggregating or grouping by slot may fit, subject to verifying the specific driver's behavior.

### 11.3. Key Namespaces and Serializers Also Affect Slots

`StringRedisTemplate` typically uses a UTF-8 serializer for keys. Another template using a binary key serializer produces **different key bytes**, which can map to different hash slots even when the Java strings look identical. In multi-service or polyglot architectures, standardize key rules and key serializers.

Redis Cluster only supports logical database `0`; using DB 1 to group related keys is a standalone-Redis practice and does not solve Cluster slot constraints.

## 12. Is `multiGet` a Consistent Snapshot?

For a native `MGET` command executed on a single Redis server, Redis processes that command atomically in server command order: no other command interleaves while fetching the elements of that `MGET`.

However, this **does not guarantee that the keys previously formed a consistent business version** if writers updated each key via multiple separate commands.

Example:

```text
Initial state: price=100, discount=10

Writer:
    SET price 120
    SET discount 20

Reader runs MGET between the two SET commands:
    price=120, discount=10
```

The reader receives a combination of state that may violate the business invariant intended by the writer. `MGET` does not wrap two separate `SET` calls into a transaction; for readers to observe them changing together, writers must update via a suitable atomic operation such as `MSET` when keys share the same execution scope.

Even with `MSET`, a subsequent update in another system or database can still fail. For data requiring cross-source transactions, Redis `MGET`/`MSET` does not replace an overall consistency mechanism.

In Redis Cluster, reading keys across multiple slots/nodes can involve multiple network operations, so there is no Cluster-wide atomic snapshot merely from calling an aggregating client API.

## 13. Comparing `multiGet` with Pipelining and Multiple `GET` Commands

**`multiGet`** issues a multi-key read operation (when topology/driver permits). **Pipelining** sends multiple commands without waiting for each response before sending the next. They solve related problems but are not identical.

| Approach | Logical Commands | Reduces Round-Trips? | Multi-Key Atomic? | Notes |
|---|---:|---|---|---|
| Synchronous `GET` loop | N commands | No, if waiting per command | No | Easy to write, but many network round-trips |
| `MGET` | 1 native Redis command where supported | Yes | One command on one server/slot | Only for Redis strings; Cluster slot constraints |
| Pipeline of N `GET`s | N commands | Yes | No | Extra memory to buffer results; fits independent commands |
| `HMGET` | 1 command reading multiple fields | Yes | One Redis hash key | Not for reading multiple Redis keys |
| `MULTI`/`EXEC` transaction | N commands inside transaction | Depends on sending mode | Per Redis transaction semantics | Must check Cluster, command errors, and result format |

Synchronous loop example:

```java
List<String> values = new ArrayList<>();
for (String key : keys) {
    values.add(redis.opsForValue().get(key));
}
```

This is straightforward, yet if each `get` waits for its response before proceeding, the application pays many round-trips. `multiGet` is usually the natural choice when fetching multiple Redis string keys together.

Pipelining is useful when issuing different commands or commands with separate TTLs:

```text
SET key1 value1 EX 60
SET key2 value2 EX 120
SET key3 value3 EX 180
```

Using a pipeline to send those three commands quickly does not make them atomic. If the application loses connection after part of the batch reaches the server, uncertain completion state must be handled. Returned values are also collected when the pipeline finishes rather than at each individual queued API call.

## 14. Batch Size: Fewer Commands Is Not Always Faster

`MGET` reduces round-trips, yet a single call with hundreds of thousands of keys can still produce a massive payload, forcing Redis to process lots of data and the application to hold a huge result list in memory.

Factors to monitor:

- **Number of keys per call:** too many items inflate request and response sizes.
- **Size of each value:** fetching 100 keys of 1 KB JSON differs vastly from fetching 100 keys of 1 MB payloads.
- **Network latency:** when RTT is high, reducing call counts usually yields major gains.
- **Serialization/deserialization:** decoding huge numbers of JSON objects can consume JVM CPU even when Redis responds quickly.
- **Hash slots and topology:** on Cluster, slot grouping or command splitting affects behavior and throughput.
- **Connection/pool limits:** many concurrent large batches can keep connections busy longer, queuing other requests.

There is no single universal batch size for every system. Choose based on observed payload sizes and latency. For very large lists, split into bounded batches:

```java
public List<String> readByChunks(
        StringRedisTemplate redis,
        List<String> keys,
        int chunkSize) {

    if (chunkSize <= 0) {
        throw new IllegalArgumentException("chunkSize must be positive");
    }

    List<String> all = new ArrayList<>(keys.size());
    for (int start = 0; start < keys.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, keys.size());
        List<String> part = redis.opsForValue()
                .multiGet(keys.subList(start, end));

        if (part == null) {
            throw new IllegalStateException(
                    "Unexpected multiGet result in pipeline/transaction");
        }
        all.addAll(part);
    }
    return all;
}
```

This code illustrates splitting a list into multiple `multiGet` calls. Each chunk is appended in exact input order, including `null` entries. If a later chunk fails after earlier chunks succeeded, the caller must decide whether to retry or fail; chunking does not produce a consistent snapshot across the entire list.

## 15. Serializers and Multi-Type Value Scenarios

`StringRedisTemplate` uses strings for keys and values, fitting product names or pre-serialized JSON payloads. To read/write Java objects:

```java
public record ProductSnapshot(String id, String name, long priceMinor) {}
```

You can configure a `RedisTemplate<String, ProductSnapshot>` using `StringRedisSerializer` for keys and a typed JSON serializer for values:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ProductRedisConfig {

    @Bean
    RedisTemplate<String, ProductSnapshot> productRedisTemplate(
            RedisConnectionFactory connectionFactory) {

        RedisTemplate<String, ProductSnapshot> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(ProductSnapshot.class));
        template.afterPropertiesSet();
        return template;
    }
}
```

Then you can use:

```java
Map<String, ProductSnapshot> values = Map.of(
        "catalog:product:v1:p101",
        new ProductSnapshot("p101", "Keyboard", 350000),
        "catalog:product:v1:p102",
        new ProductSnapshot("p102", "Mouse", 180000)
);

productRedisTemplate.opsForValue().multiSet(values);

List<ProductSnapshot> products = productRedisTemplate.opsForValue()
        .multiGet(List.of(
                "catalog:product:v1:p101",
                "catalog:product:v1:p102"
        ));
```

Read outcomes depend on the **serializer used at write time**. If keys already contain JDK serialization payloads or hash data, switching the serializer to Jackson and calling `multiGet` will not automatically convert legacy data. When changing formats, adopt key versioning, migration, or cache rebuild strategies.

For complex Java types like `Instant`, polymorphic types, and custom JSON formats, configure the Jackson mapper/modules appropriately for your framework version. Do not assume every serializer automatically inherits the application's global `ObjectMapper` configuration.

## 16. Handling Batch Cache Misses Without Losing Order

A practical scenario: an API receives `["p101","p102","p103"]`, and Redis only has `p101` and `p103`. The typical flow is:

```text
Input IDs:       p101, p102, p103
                    |
multiGet(keys)       v
Cache result:    hit,  null, hit
                    |
                    +----> find missing IDs: p102
                                  |
                              read database
                                  |
                              fill cache
                                  |
API result:      p101, p102, p103
```

When refilling data, pay attention to:

1. Only truly missing IDs need database queries; Redis may return `null` for wrong data types, so keep the contract in mind during diagnostics.
2. Database query results may not match the requested ID order, so join by **ID**, never by positional guesswork.
3. Deleted or non-existent database rows need a clear policy: return missing, cache a sentinel value, or skip caching.
4. When refilling cache entries that require TTL, use writes supporting expiration; `multiSet` does not set expiry.
5. Multiple concurrent cache misses on the same key can all hit the database (cache stampede); `multiGet` does not solve this by itself.

Pseudocode example:

```text
ids = ["p101", "p102", "p103"]
redisValues = multiGet(makeKeys(ids))
missedIds = select ids[i] where redisValues[i] is null

dbRows = database.findByIds(missedIds)
dbById = indexById(dbRows)

return ids.map(id ->
    cached value if present
    else dbById.get(id)
)
```

For reconstructible caches, correctness of ID-based merging usually matters far more than shaving off one extra Redis command.

## 17. Common Errors and Misconceptions

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `multiGet` result has `null` in the middle | Key does not exist, TTL expired, or incompatible Redis type | Check original key and `TYPE`/`EXISTS` in an allowed environment |
| `multiGet` returns `null` overall | Called inside pipeline/transaction or deferred-result context | Check `executePipelined` / `SessionCallback` usage |
| Results mapped to wrong IDs | List zipped out of input order; `null` entries stripped before mapping | Keep an ordered key `List` and zip by index |
| `multiSet` writes keys that never expire | `MSET` sets no TTL and clears old TTLs on overwrite | Inspect `TTL key`, adjust write strategy |
| `multiSetIfAbsent` creates nothing even though some keys are missing | One key in the group already exists, so `MSETNX` writes none | Use `EXISTS` on relevant keys or change business semantics |
| `CROSSSLOT` error | Keys in native multi-key command span multiple Cluster slots | Check `CLUSTER KEYSLOT`; design hash tags when truly needed |
| Deserialization failure on multi-key read | Writer and reader use different serializers/schemas | Check serializer/encoding/key version |
| `MGET` sees `nil` while `EXISTS` shows key present | Key holds non-string Redis type or state changed between commands | Check `TYPE` and how other services write the key |
| Huge batch slows down requests | Too many keys or large payloads; deserialization CPU/memory/connection busy | Limit batch size; measure latency and response size |

Commands such as `TYPE` and `TTL` aid diagnostics, yet results from separate commands **do not form a consistent snapshot** if concurrent writers are modifying keys.

## 18. Hands-On Practice with Redis CLI

On a standalone test Redis instance, write a group of keys:

```bash
redis-cli MSET demo:multikey:p1 "A" demo:multikey:p2 "B" demo:multikey:p3 "C"
```

Read individually and together:

```bash
redis-cli GET demo:multikey:p1
redis-cli GET demo:multikey:p2
redis-cli MGET demo:multikey:p3 demo:multikey:p1 demo:multikey:missing
```

The final `MGET` command is expected to display:

```text
1) "C"
2) "A"
3) (nil)
```

Notice that the results follow the **requested order** (`p3`, `p1`, `missing`), not the order in which they were written (`p1`, `p2`, `p3`).

Verify overwrite behavior and TTL:

```bash
redis-cli SET demo:multikey:expire "old" EX 120
redis-cli TTL demo:multikey:expire
redis-cli MSET demo:multikey:expire "new" demo:multikey:p4 "D"
redis-cli TTL demo:multikey:expire
```

After `MSET`, `demo:multikey:expire` still exists without a TTL, so `TTL` returns `-1` if no concurrent operation alters the key.

Try `MSETNX`:

```bash
redis-cli MSETNX demo:multikey:p1 "overwritten?" demo:multikey:only-if-all-new "X"
redis-cli EXISTS demo:multikey:only-if-all-new
```

Because `p1` already exists, `MSETNX` returns `0` and the new key is not created either. This exercise uses only the `demo:multikey:` prefix to avoid affecting business keys; when working on a shared Redis instance, confirm the environment and permissions before writing.

### Testing on Redis Cluster

If you have a test Cluster, use two keys with the same hash tag:

```bash
redis-cli -c -h redis-node-1 -p 6379 MSET 'demo:{batch42}:a' "A" 'demo:{batch42}:b' "B"
redis-cli -c -h redis-node-1 -p 6379 MGET 'demo:{batch42}:a' 'demo:{batch42}:b'
```

Because the hash tag `batch42` is identical, both keys belong to the same slot. When working with keys across different slots, evaluate client/framework behavior per the Redis Cluster section above; do not run multi-key operations assuming cross-node atomicity.

## 19. Self-Check Questions

**1. Why does `multiGet` return a `List` rather than a `Map`?**

`MGET` returns a list of values matching the supplied key order. Position distinguishes present keys from missing keys and preserves duplicate key entries if the input contains duplicates.

**2. If Redis lacks the second of three requested keys, what is the output?**

Typically a three-element list where the second element is `null`. Never strip `null` before zipping back to IDs, as that misaligns positions.

**3. Can `multiSet` replace `set(key, value, Duration)` when writing cache entries?**

They are not equivalent. `multiSet` takes no TTL parameter; overwriting can drop existing TTLs. If TTL is required, pick a write strategy supporting expiry.

**4. How does `multiSetIfAbsent` differ from calling `setIfAbsent` multiple times?**

`multiSetIfAbsent` uses `MSETNX` semantics: if any key already exists, none of the group is written. Calling `setIfAbsent` key by key can create part of the group before encountering an existing key.

**5. Is reading 100 keys with `multiGet` always atomic in Redis Cluster?**

Do not assume so. Native multi-key commands have same-slot constraints; some clients split reads across nodes, in which case there is no Cluster-wide atomic snapshot.

**6. Can `multiGet` read both `name` and `price` fields from the same Redis hash?**

Use `opsForHash().multiGet(hashKey, fields)`, which corresponds to `HMGET`. `opsForValue().multiGet(keys)` is for multiple Redis string keys.

**7. Why can `multiGet` reduce network overhead yet still slow down the server?**

Too many keys or huge payloads force Redis, the JVM, and the network to handle substantial data at once. Measure latency and split into appropriate batches rather than growing batch size unboundedly.

## 20. Conclusion

In Spring Data Redis, **`opsForValue().multiGet(keys)`** reads multiple Redis string keys and returns values in the exact order of input keys; missing keys can produce `null` elements. **`opsForValue().multiSet(map)`** writes multiple key–value pairs using Redis `MSET` semantics, overwriting existing data and **never setting a TTL automatically**. To write conditionally for an entire group, use `multiSetIfAbsent` and keep in mind the "all-or-nothing" semantics of `MSETNX`.

In real applications, keep key namespaces and serializers consistent, join results by ID rather than skipping missing positions, choose sensible batch sizes, and distinguish single-command atomicity from business transactions. In Redis Cluster, design hash slots and hash tags to match the multi-key operations that must run together.
