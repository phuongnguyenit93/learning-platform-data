# Hash Tags to Place Multiple Keys in the Same Slot in Redis Cluster with Spring Data Redis

## 1. The problem to solve

When migrating from standalone Redis to **Redis Cluster**, an application can no longer assume every key resides on the same Redis server. Redis Cluster partitions the keyspace into **16,384 hash slots**; primary nodes take responsibility for serving different slots.

Some commands that operate on multiple keys require all participating keys to be in the **same hash slot**. If an application uses two key names that were not designed with this in mind:

```text
order:101:status
order:101:updatedAt
```

then even though both keys belong to order `101`, they are **not guaranteed** to land in the same slot. An `MGET`, `MSET`, or Lua script accessing both can fail with:

```text
CROSSSLOT Keys in request don't hash to the same slot
```

Redis Cluster provides the **hash tag** mechanism: the non-empty substring inside the first valid `{...}` pair of braces in a key name is used to calculate the slot instead of the entire key name.

Example:

```text
order:{101}:status
order:{101}:updatedAt
order:{101}:items
```

All three keys have the hash tag `101`, so Redis computes the slot from the exact same string `101`. As a result, they land in the same hash slot, regardless of differences in the parts before or after `{101}`.

**A hash tag is not a transaction marker, not a new data type, not a physical Redis namespace, and not an automatic data distribution tool.** It is strictly a key-naming convention that alters the **input to the hash slot calculation**.

This lesson covers the mechanics from the Redis layer up to Spring Data Redis: hash tag syntax, slot inspection, choosing aggregate boundaries, multi-key commands, Lua/transactions, key serializer rules, hot slot load issues, and common operational mistakes.

### Learning outcomes

After completing this lesson, you will be able to:

1. Explain how Redis Cluster partitions data into 16,384 hash slots and the formula used to determine slots.
2. Identify which part of a key name Redis hashes when `{...}` is present.
3. Design groups of keys sharing a tag to use multi-key commands and Lua scripts.
4. Distinguish **same hash slot** from **same primary node**.
5. Use `CLUSTER KEYSLOT` to verify key names before going to production.
6. Understand why multi-key commands still fail even when the client supports automatic `MOVED`/`ASK` redirects.
7. Organize keys for entities, tenants, orders, carts, and inventory along proper atomicity boundaries.
8. Use `StringRedisTemplate` and `RedisScript` to operate on keys in the same slot.
9. Recognize the risk of creating a **hot slot** if an overly broad tag is used.
10. Design a migration when legacy keys lack hash tags or use an unsuitable tag.

## 2. How does Redis Cluster partition by hash slot?

In Redis Cluster, every key maps to an integer in the range:

```text
0 .. 16383
```

Total number of slots:

```text
16384 = 2^14
```

In principle, Redis applies CRC16 to the bytes of the key name or valid hash tag, then takes the remainder:

```text
HASH_SLOT = CRC16(hash_input_bytes) mod 16384
```

In this formula:

- `CRC16` is the CRC16 algorithm specified by Redis Cluster; if implementing it yourself, use the exact Redis-compatible variant rather than an arbitrary library CRC16 function.
- `hash_input_bytes` is the full key name if no valid hash tag is present, or the byte slice inside the `{...}` pair selected by Redis.
- `mod 16384` keeps the result within the 16,384-slot space.
- Redis Cluster maintains a **slot → primary node** mapping table and can update it during resharding or failover.

Conceptual flow:

```text
Key bytes
   |
   +--> Has valid hash tag?
   |        |
   |        +-- Yes --> Take only bytes inside {...}
   |        |
   |        +-- No  --> Take all key name bytes
   |
   v
CRC16(...)
   |
   v
mod 16384
   |
   v
Slot 0..16383
   |
   v
Primary owning the slot
```

Example of a Redis Cluster with three primaries:

```text
Primary A: slots     0..5460
Primary B: slots  5461..10922
Primary C: slots 10923..16383
```

This is an illustrative split. Actual Cluster setups may distribute slots differently, include replicas, and move slots between nodes.

**A key name does not select a server directly.** It selects a slot; the slot is assigned to a current node. When a slot moves to another node, keys belonging to that slot move with the Cluster mechanism, even though their key names and hash tags stay unchanged.

### 2.1. There is no "same prefix means same slot" rule

The names:

```text
order:101:status
order:101:items
order:101:total
```

all share the prefix `order:101:`, yet Redis does not parse prefixes to identify aggregates. Without a valid `{...}`, the **entire name** is fed into CRC16. Differing only in suffix can place them in different slots.

Therefore:

```text
Same prefix       != guaranteed same slot
Same tenant ID    != guaranteed same slot
Same order ID     != guaranteed same slot
Same hash tag     == same slot
```

Two completely different random key names can still **happen to collide in the same slot due to modulo 16384**. Never rely on accidental collisions: key naming must explicitly express why two keys belong in the same slot.

### 2.2. "Same slot" vs. "same node"

A primary node usually manages many slots. Two keys in different slots can still happen to reside on the same primary at a given point in time.

Example:

```text
Key A -> slot 1000 -> Primary A
Key B -> slot 1001 -> Primary A
```

Both are on the same node, yet in two different slots. Redis Cluster can still reject a multi-key command requiring same-slot because it checks the **slot**, not just whether the node addresses match.

This also matters during resharding: slot 1001 might move to another node in the future while slot 1000 remains on the old node. Correct design must never rely on two slots happening to be served by the same node today.

## 3. Hash tag syntax `{...}`

Hash tags are recognized from the **bytes of the key name** according to Redis Cluster rules.

Example:

```text
user:{u-42}:profile
user:{u-42}:settings
user:{u-42}:sessions
```

The portion used to compute CRC16 for all three is:

```text
u-42
```

The rest of the key name is still preserved by Redis to distinguish the entries:

```text
user:{u-42}:profile   != user:{u-42}:settings
```

Two **distinct** keys, sharing the **same slot**.

### 3.1. Rules Redis uses to pick a tag

Conceptually, Redis processes as follows:

1. Find the first `{` character in the key name.
2. Find the first `}` character appearing **after** that `{`.
3. If no `}` is found, or the substring between them is empty, hash the **entire key name**.
4. If the substring between them is non-empty, hash only that substring.
5. If multiple brace pairs exist, subsequent pairs are **not automatically used** to re-select a tag.

This rule is not a JSON structural parser or nested-brace matcher. Redis does not understand tenants, entities, UUIDs, or event types; Redis inspects raw key name bytes only.

### 3.2. Example table

| Key Name | Input Used for Slot Calculation | Explanation |
|---|---|---|
| `order:101:status` | Entire `order:101:status` | No hash tag |
| `order:{101}:status` | `101` | Valid `{101}` pair |
| `order:{101}:items` | `101` | Same slot as the key above |
| `{101}:items` | `101` | Tag at start of key name is valid |
| `orders:{101}` | `101` | Tag at end of key name is valid |
| `a{101}b{202}c` | `101` | Picks tag from the first pair |
| `a{}b` | Entire `a{}b` | First tag is empty |
| `a{}b{101}` | Entire `a{}b{101}` | Does not fall back to second tag if first tag is empty |
| `a{101` | Entire `a{101` | No closing `}` |
| `a}b{101}c` | `101` | A `}` before `{` does not form a tag |
| `a{abc}x` | `abc` | Parts outside braces do not affect the slot |
| `b{abc}y` | `abc` | Same slot as `a{abc}x` |
| `a{ABC}x` | `ABC` | Not guaranteed same slot as tag `abc` |

Important example:

```text
cart:{c-7}:items
cart:{c-7}:total
```

are guaranteed to share the same hash slot.

Meanwhile:

```text
cart:{c-7}:items
cart:{c-8}:total
```

are not guaranteed to share a slot, because the hashed parts are `c-7` and `c-8` respectively.

### 3.3. Only one tag is used to select the slot

Suppose a key contains both a tenant ID and an order ID:

```text
tenant:{t-7}:order:{o-101}:status
```

Redis uses **`t-7`**, not `o-101`, because `{t-7}` is the first valid tag pair.

This is an easy pitfall in key design:

- If you intended to partition by tenant, the example reflects that intent.
- If you intended to partition **per order**, the key above does the wrong thing: all orders for tenant `t-7` land in a single slot instead of spreading across orders.

Place the tag around the exact **aggregate boundary that needs atomicity**, for example:

```text
tenant:t-7:order:{t-7|o-101}:status
tenant:t-7:order:{t-7|o-101}:items
```

Both use the tag `t-7|o-101`. The `tenant:t-7:` portion outside the tag does not interfere with the slot.

### 3.4. Tags are not wildcards

In Redis naming:

```text
orders:{o-101}:status
```

braces select the hash input.

Whereas in:

```text
orders:*
```

the `*` character acts as a glob in pattern-matching commands like `SCAN MATCH`, and **does not put keys prefixed with `orders:` into the same slot**.

Key names and patterns serve two distinct purposes:

- Hash tag: determines the slot of **a specific key**.
- Glob pattern: determines which **multiple names** match a search or Pub/Sub subscription.

Do not confuse Pub/Sub `PatternTopic` or `SCAN MATCH` with the hash tag mechanism.

## 4. Checking slots with CLUSTER KEYSLOT

The most important diagnostic command:

```redis
CLUSTER KEYSLOT <key>
```

Example in Redis CLI connected to a Cluster:

```redis
CLUSTER KEYSLOT order:{101}:status
CLUSTER KEYSLOT order:{101}:items
CLUSTER KEYSLOT order:{101}:updatedAt
```

All three calls must return **the same slot number**. The specific number matters less than the fact that all three match.

Compare:

```redis
CLUSTER KEYSLOT order:101:status
CLUSTER KEYSLOT order:101:items
```

Two names without hash tags may return two different slots.

Using the CLI from a terminal:

```bash
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'order:{101}:status'
redis-cli -c -h 127.0.0.1 -p 7000 CLUSTER KEYSLOT 'order:{101}:items'
```

Host/port `127.0.0.1:7000` only illustrates a local Redis Cluster; use the actual addresses in your deployment environment.

**Note:** `CLUSTER KEYSLOT` calculates the slot from the **key name passed to the command**; the key does not need to exist yet. It is very useful for validating designs before writing any data.

### 4.1. Verifying with MGET

With same-tag keys:

```redis
SET order:{101}:status PENDING
SET order:{101}:updatedAt 2026-11-13T00:00:00Z
MGET order:{101}:status order:{101}:updatedAt
```

In a Cluster, `MGET` can be served as a valid multi-key operation when the keys are in the same slot and other system conditions are met.

Change one key to a name in a different slot:

```redis
MGET order:{101}:status order:{102}:updatedAt
```

If the two tags map to different slots, Redis rejects it with `CROSSSLOT`. Two different tags **can coincidentally hash to the same slot**, so if you want to demonstrate the error for a specific pair, check their `CLUSTER KEYSLOT` values first.

Never treat two different tags coincidentally working together as a stable contract on data boundaries.

### 4.2. Do not use CLUSTER KEYSLOT in place of data checks

Two keys sharing a slot **may not exist yet**, may not have the expected Redis type, and may not hold valid values. `CLUSTER KEYSLOT` only answers the routing question.

A sound diagnostic workflow:

```text
1. Check key naming.
2. CLUSTER KEYSLOT each key.
3. Check which node owns the slot.
4. Check whether keys exist and their types.
5. Check whether the multi-key command/API is supported on Cluster.
6. Check actual errors from client/driver and topology.
```

## 5. Why do multi-key commands hit CROSSSLOT?

In standalone Redis, all keys reside in the same logical server space. The command:

```redis
MGET order:101:status order:101:updatedAt
```

normally faces no slot barrier, provided the keys and command are valid.

In Redis Cluster, each key has its own slot. Some commands require Redis to process **multiple keys in a single operation** that cannot be transparently split across multiple primaries because of semantic and atomicity requirements.

Examples that typically require the same slot:

```redis
MGET key1 key2
MSET key1 value1 key2 value2
DEL key1 key2
EXISTS key1 key2
RENAME source destination
```

Additionally, multi-key Set operations, some Sorted Set operations, scripting, and transactions are subject to their own constraints.

**Not every API that accepts multiple keys always sends a single Redis multi-key command.** A client may fan out or split certain operations across multiple nodes depending on implementation and version. However, that does not turn the result into a cross-slot atomic operation.

Distinguish the two cases:

```text
One Redis multi-key command:
    MGET k1 k2
    -> must obey Cluster command constraints.

Two independent commands:
    GET k1
    GET k2
    -> cluster-aware client can send to two nodes,
       but there is no atomically consistent snapshot.
```

### 5.1. Example of an unsuitable design

Initial keys:

```text
cart:77:items
cart:77:coupon
```

The application wants:

```redis
MGET cart:77:items cart:77:coupon
```

Without a tag, the two keys are not guaranteed to be in the same slot. On Redis Cluster, the command can fail.

Redesign:

```text
cart:{77}:items
cart:{77}:coupon
```

Now every key in cart 77 hashes from `77`.

However, this comes with an architectural decision: keys belonging to the same cart will not be spread across multiple primaries. That is a deliberate trade-off in exchange for atomic multi-key operations scoped to that cart.

### 5.2. Multi-key does not mean system-wide multi-object

Suppose you need to transfer funds between two different wallets:

```text
wallet:{u-1}:balance
wallet:{u-2}:balance
```

The two keys have different tags, usually landing in different slots. Both being `wallet` types does not make a transfer an atomic cross-shard transaction.

You could try placing both under a common tag, but doing so for all users creates a system-wide hot slot. When transactions across distributed entities are required, look toward transactional databases at the source of truth, saga/compensation architectures, or changing aggregate boundaries.

## 6. Hash tags enable atomicity, but do not provide atomicity by themselves

This is a crucial distinction:

```text
Same hash slot
    -> necessary routing prerequisite for many atomic/multi-key commands.

Same hash slot
    != any sequence of GET -> check -> SET automatically becomes atomic.
```

Example with two keys in the same slot:

```text
stock:{sku-42}:available
stock:{sku-42}:reserved
```

Java executes:

```text
GET stock:{sku-42}:available
IF available >= 3
    DECRBY stock:{sku-42}:available 3
    INCRBY stock:{sku-42}:reserved 3
```

Even though the keys share a slot, if these are separate Redis calls, two requests can interleave:

```text
Request A GET available -> 5
Request B GET available -> 5
Request A decrements 3
Request B decrements 3
```

The stock invariant can be violated.

To make check-and-update execute as an un-interleaved unit, you need a **Lua script, properly used transaction**, or an appropriate atomic command.

Hash tags make related keys **eligible** to participate in those mechanisms within a Cluster; they do not execute business logic on your behalf.

### 6.1. A single Redis command

Redis commands execute atomically at the command level per Redis semantics. For instance, if a valid `MSET` runs on keys in the same slot, `MSET` itself has the semantics of updating multiple keys in one command.

If Java splits this into two independent `SET` calls, do not assume they are mutually atomic just because both keys share a tag.

### 6.2. MULTI/EXEC

In a Cluster, `MULTI`/`EXEC` transactions touching multiple keys must satisfy Redis Cluster slot constraints. Keys in different slots cannot be bundled into a distributed transaction simply by calling `MULTI` on a connection.

Example using keys:

```text
order:{101}:status
order:{101}:updatedAt
```

to design a same-slot transaction.

Keys such as:

```text
order:{101}:status
order:{102}:updatedAt
```

are not guaranteed to share a slot and must not be treated as a valid transaction set.

One more caution: Redis transactions do not provide SQL-style rollback for commands that already succeeded before a subsequent runtime error. To protect business invariants, carefully validate inputs, data state, and error handling.

### 6.3. WATCH

`WATCH` supports optimistic locking by tracking key modifications prior to `MULTI/EXEC`. However, if a workflow involves multiple keys in different slots, hash tags remain a prerequisite for a valid Cluster transaction design.

`WATCH` does not stitch observations across multiple primaries into a global transaction.

### 6.4. Lua scripts and Redis Functions

Lua scripts can inspect and update multiple keys without other commands interleaving during execution. However, in Redis Cluster:

- Redis keys accessed by the script must be explicitly declared via `KEYS`.
- Participating keys must satisfy the same hash slot constraint.
- Hiding a key name inside `ARGV` and constructing a Redis command inside the script is not a valid way to bypass routing.
- Scripts do not create distributed transactions across primaries.
- If a script performs some writes and then hits a runtime error, those earlier writes are not automatically rolled back.

Redis Functions are subject to the same partitioning constraints for key access.

## 7. Design keys by aggregate, not for the entire system

The most important question when choosing a hash tag:

> **Which keys genuinely need to be read/updated together in a single atomic operation or multi-key command?**

These are usually keys belonging to **one aggregate**, **one session**, **one order**, **one shopping cart**, or **one resource with a clear transaction boundary**.

Example:

```text
order:{o-101}:status
order:{o-101}:items
order:{o-101}:total
order:{o-101}:version
```

This group uses tag `o-101`; every other order uses a different tag:

```text
order:{o-102}:status
order:{o-102}:items
order:{o-102}:total
order:{o-102}:version
```

Redis can distribute different orders across many slots. Within each order, however, its keys remain colocated in the same slot.

### 7.1. Recommended structure

```text
<domain>:<optional-context>:{<aggregate-id>}:<component>
```

Example:

```text
order:{o-101}:status
order:{o-101}:items
cart:{c-77}:items
cart:{c-77}:coupon
inventory:{sku-42}:available
inventory:{sku-42}:reserved
```

Actual names should follow a consistent project convention; Redis only cares about bytes and brace pairs.

### 7.2. Is a tenant ID needed in the tag?

If `orderId` is globally unique, using only the order ID may suffice. If order IDs are only unique **within each tenant**, combine tenant and order into the tag identifier:

```text
tenant:t-7:order:{t-7|o-101}:status
tenant:t-7:order:{t-7|o-101}:items

tenant:t-8:order:{t-8|o-101}:status
tenant:t-8:order:{t-8|o-101}:items
```

Here:

- `t-7|o-101` and `t-8|o-101` are two distinct hash tags.
- There is no accidental tag sharing between identical order IDs across different tenants.
- Components of the same order/tenant still share a slot.

**Tags do not enforce uniqueness constraints**; two key names with the same tag remain two distinct keys if the rest of the name differs. Business identifier design is responsible for preventing collisions/erroneous aggregate merging.

### 7.3. When to tag by tenant?

One option:

```text
tenant:{t-7}:config
tenant:{t-7}:quota
tenant:{t-7}:audit
tenant:{t-7}:order:o-101
tenant:{t-7}:order:o-102
```

All hash from `t-7`.

This is useful **if you genuinely need atomic multi-key operations spanning tenant-wide data** and tenant size/load is bounded. However, if a tenant has millions of orders and very high QPS, it funnels the entire workload into one slot/primary, defeating Redis Cluster distribution.

There is no universal rule that "all keys of a tenant should share a tag". Tag granularity should be driven by the **unit requiring atomicity**, not merely authorization or namespace models.

## 8. How to choose the size of a key group?

Three common choices exist:

| Tag Design | Example | Advantage | Risk |
|---|---|---|---|
| System-wide tag | `app:{global}:...` | All app keys in one slot | Extremely prone to hot slots; loses almost all sharding benefits |
| Tenant-level tag | `tenant:{t-7}:...` | Multiple tenant keys can share a slot | Large tenants create hotspots |
| Aggregate-level tag | `order:{t-7|o-101}:...` | Atomicity within one order; distributes across orders | Not atomic across two orders |
| Small entity tag | `sku:{sku-42}:...` | Good for per-SKU inventory | A hot SKU can still create a hot slot |
| No hash tag | `order:o-101:status` | Natural full-key distribution | Multi-key within the same order is not guaranteed |

**Design recommendation:** start from the business boundary needing simultaneous operations. Choose a tag small enough to avoid coupling unrelated data, yet wide enough so keys needing atomicity share one slot.

Shopping cart example:

```text
cart:{c-77}:items      -- Redis Set/Hash
cart:{c-77}:coupon     -- Redis String
cart:{c-77}:totals     -- Redis Hash
cart:{c-77}:version    -- Redis String
```

If transitioning cart state via script is required, this design permits accessing multiple components of the **same cart**.

If you want to update cart `c-77` and the inventory of dozens of independent SKUs in a single transaction, the inventory keys may span many slots. No small tag can satisfy both models simultaneously without sacrificing load distribution or changing the architecture.

## 9. Spring Data Redis example: reading multiple keys with StringRedisTemplate

In Spring Boot, you can use `spring-boot-starter-data-redis` with Lettuce and `StringRedisTemplate`.

Maven dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Illustrative Redis Cluster configuration:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - 127.0.0.1:7000
          - 127.0.0.1:7001
          - 127.0.0.1:7002
      timeout: 3s
```

This is a development topology example; do not use `127.0.0.1` as a production address unless the application runs on the same host environment. Specific auto-configuration options depend on Spring Boot and Lettuce versions.

Service:

```java
package com.example.order;

import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderSnapshotCache {

    private final StringRedisTemplate redis;

    public OrderSnapshotCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void write(String orderId, String status, String updatedAt) {
        String tag = "{" + orderId + "}";

        redis.opsForValue().set(
            "order:" + tag + ":status",
            status
        );

        redis.opsForValue().set(
            "order:" + tag + ":updatedAt",
            updatedAt
        );
    }

    public List<String> read(String orderId) {
        String tag = "{" + orderId + "}";

        return redis.opsForValue().multiGet(
            List.of(
                "order:" + tag + ":status",
                "order:" + tag + ":updatedAt"
            )
        );
    }
}
```

With the same tag, the keys are designed into the same slot. The `multiGet` call normally maps to `MGET` at the Redis level per the corresponding API.

**Important note:** the `write` method above uses two independent `SET` calls, so it is **not an atomic update across both keys**. If one call succeeds and the other fails, the cache can hold an inconsistent state. Use this approach only when brief inconsistency is acceptable or another strategy protects the invariant.

If both keys must be updated together consistently, use same-slot `MSET` or a properly designed script/transaction.

### 9.1. `multiSet` with two keys sharing a tag

Example:

```java
import java.util.LinkedHashMap;
import java.util.Map;

String tag = "{o-101}";

Map<String, String> values = new LinkedHashMap<>();
values.put("order:" + tag + ":status", "PAID");
values.put("order:" + tag + ":updatedAt", "2026-11-13T02:00:00Z");

stringRedisTemplate.opsForValue().multiSet(values);
```

In Redis Cluster, the keys of a multi-key `MSET` must reside in the same slot. This tagging convention satisfies that condition.

Do not assume that placing two entries in a single Java `Map` causes Redis to automatically route them to the same node/slot. Removing `{o-101}` eliminates the key-naming guarantee required by `MSET`.

### 9.2. The key serializer determines the slot

`StringRedisTemplate` uses string serializers for keys and values, so a Java name such as:

```text
order:{o-101}:status
```

is sent as matching string bytes, and Redis sees `{o-101}` as intended.

With a differently configured `RedisTemplate<String, Object>`, the **key serializer might not be String**. If keys are serialized using Java native serialization, the actual Redis key bytes do not match the displayed Java string, and Redis's search for `{`/`}` may fail to behave as expected.

Hash slots are always computed from the **wire bytes of the Redis key**, not from the Java String abstraction.

To make hash tags predictable, commonly configure `StringRedisSerializer` for keys:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisTemplateConfiguration {

    @Bean
    RedisTemplate<String, Object> appRedisTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, Object> template =
            new RedisTemplate<>();

        template.setConnectionFactory(factory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setHashKeySerializer(new StringRedisSerializer());

        // Choose value/hashValue serializer per the application's
        // schema (JSON, String, binary...).
        // Do not mix formats with existing data.
        template.afterPropertiesSet();
        return template;
    }
}
```

This illustrates standardizing the **key serializer**; a real application must explicitly configure value serializers according to its contract and beans in use. Configuring the key serializer does not automatically convert existing keys previously stored with another encoding.

### 9.3. Key names have `{...}` yet still land in different slots?

Possible causes:

- One service uses a different key serializer.
- One service inserts an extra `{...}` pair before the intended tag.
- `orderId` contains unnormalized `{` or `}` characters.
- Tags differ in character casing.
- One service uses `o-101` while another uses `tenant-7|o-101`.
- One service alters Unicode normalization or ID encoding.
- Some keys were created by tooling/CLI with a different format than the application sends.
- Some keys lack a tag or have an empty tag.

Inspect the actual **key bytes and hash input**, not just logged Java objects.

## 10. Building keys through a unified KeyFactory

To prevent each service from concatenating key names differently, create a central component to build key names.

Java example:

```java
package com.example.order;

import java.util.Objects;
import java.util.regex.Pattern;

public final class OrderRedisKeys {

    private static final Pattern SAFE_ID =
        Pattern.compile("[A-Za-z0-9_-]+");

    private OrderRedisKeys() {
    }

    public static String status(
            String tenantId,
            String orderId) {

        return prefix(tenantId, orderId) + ":status";
    }

    public static String updatedAt(
            String tenantId,
            String orderId) {

        return prefix(tenantId, orderId) + ":updatedAt";
    }

    public static String items(
            String tenantId,
            String orderId) {

        return prefix(tenantId, orderId) + ":items";
    }

    private static String prefix(
            String tenantId,
            String orderId) {

        requireSafeId(tenantId);
        requireSafeId(orderId);

        String tag = tenantId + "|" + orderId;

        return "order:{" + tag + "}";
    }

    private static void requireSafeId(String value) {
        Objects.requireNonNull(value, "id");

        if (!SAFE_ID.matcher(value).matches()) {
            throw new IllegalArgumentException(
                "Unsupported identifier characters"
            );
        }
    }
}
```

Usage:

```java
String statusKey = OrderRedisKeys.status("t-7", "o-101");
String updatedKey = OrderRedisKeys.updatedAt("t-7", "o-101");
String itemsKey = OrderRedisKeys.items("t-7", "o-101");
```

Result:

```text
order:{t-7|o-101}:status
order:{t-7|o-101}:updatedAt
order:{t-7|o-101}:items
```

All three share the tag `t-7|o-101`.

Here, the ID regex is only an **illustrative convention**; Unicode IDs or other formats can still work if the application applies consistent encoding/canonicalization rules. The key point is **never allowing untrusted input to alter the brace structure of the tag**.

### 10.1. Why must braces be avoided in input data?

Suppose the application intends to construct:

```text
order:{tenant|orderId}:status
```

but `tenantId` or `orderId` comes from unvalidated data containing `{` or `}`. The first brace pair Redis recognizes might then not be the intended tag.

Example failure shape:

```text
prefix:{unexpected}:order:{t-7|o-101}:status
```

Redis selects `unexpected`, not `t-7|o-101`.

Therefore, a good KeyFactory should:

1. Normalize identifiers in a single place.
2. Reject or encode characters that alter name structure, especially `{` and `}`.
3. Enforce a consistent format across all services.
4. Separate data identifiers from the `{...}` syntax generated by the application.
5. Control how multiple IDs are joined to avoid ambiguity.

### 10.2. Delimiters inside a tag must also be unambiguous

If you use:

```text
{tenant|order}
```

and a tenant value could contain `|`, it becomes difficult to distinguish components during debugging or canonical ID construction.

You can:

- Forbid `|` in identifiers.
- Encode each component with Base64url or a canonical escaping scheme, eliminating any chance of injecting `{`/`}`.
- Use standardized technical UUIDs/IDs.
- Use a length-prefixed format if combining segments with arbitrary characters.

A good solution produces the **exact same tag for the same aggregate** across all instances and **different tags for genuinely different aggregates**, aside from unavoidable CRC16 hash collisions.

## 11. Multi-key Lua scripts in the same slot

One scenario needing atomicity is transitioning an order's status from `PENDING` to `PAID` and updating `updatedAt` simultaneously **only if the current status matches**.

Two keys:

```text
order:{t-7|o-101}:status
order:{t-7|o-101}:updatedAt
```

Lua script (stored under `src/main/resources/scripts/transition-order.lua`):

```lua
-- KEYS[1]: order status
-- KEYS[2]: order updatedAt
-- ARGV[1]: expected current status
-- ARGV[2]: next status
-- ARGV[3]: new updatedAt text

if #KEYS ~= 2 or #ARGV ~= 3 then
    return redis.error_reply('INVALID_ARGUMENT_COUNT')
end

local current = redis.call('GET', KEYS[1])

if current ~= ARGV[1] then
    return 0
end

redis.call(
    'MSET',
    KEYS[1], ARGV[2],
    KEYS[2], ARGV[3]
)

return 1
```

Return contract:

| Redis result | Meaning |
|---:|---|
| `1` | Status transitioned and timestamp updated |
| `0` | Current status did not match `expected`; no update performed |
| Error reply | Contract violation, Redis command error, or operational issue |

The purpose of using Lua is to combine the **conditional read** and **multi-key update** into a single un-interleaved operation. `MSET` itself has multi-key update semantics in one command, but lacks the `current == expected` check; that is why the script is useful.

### 11.1. Declaring the script in Spring Boot

```java
package com.example.order;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class OrderScriptConfiguration {

    @Bean
    RedisScript<Long> transitionOrderScript() {
        return RedisScript.of(
            new ClassPathResource(
                "scripts/transition-order.lua"
            ),
            Long.class
        );
    }
}
```

Specify `Long.class` so Spring Data Redis interprets the Redis integer reply corresponding to `return 0` or `return 1`.

### 11.2. Executing via StringRedisTemplate

```java
package com.example.order;

import java.time.Instant;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class OrderTransitionService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> transitionOrderScript;

    public OrderTransitionService(
            StringRedisTemplate redis,
            RedisScript<Long> transitionOrderScript) {
        this.redis = redis;
        this.transitionOrderScript = transitionOrderScript;
    }

    public boolean markPaid(
            String tenantId,
            String orderId) {

        String statusKey =
            OrderRedisKeys.status(tenantId, orderId);

        String updatedAtKey =
            OrderRedisKeys.updatedAt(tenantId, orderId);

        Long result = redis.execute(
            transitionOrderScript,
            List.of(statusKey, updatedAtKey),
            "PENDING",
            "PAID",
            Instant.now().toString()
        );

        if (result == null) {
            throw new IllegalStateException(
                "Lua did not return an expected status"
            );
        }

        return result == 1L;
    }
}
```

`OrderRedisKeys` is the KeyFactory from the previous section. Both keys passed via `List.of(...)` use the **same hash tag**. `ARGV` carries business values only and is never used to hide key names.

To test it:

```redis
SET order:{t-7|o-101}:status PENDING
```

Then call `markPaid("t-7", "o-101")`; the script transitions the status to `PAID` and writes `updatedAt`.

If two concurrent `markPaid` requests arrive, the second request sees the updated status and receives `0`, instead of both observing `PENDING` and overwriting independently.

### 11.3. Remaining limitations

- Both keys must share a slot; hash tags enforce this routing condition.
- The script does not form a transaction with a SQL database, HTTP service, or external queue.
- If the script hits a runtime error after performing writes, Redis does not automatically roll back earlier successful commands like a SQL transaction.
- If the client times out, Redis may have executed the script while the reply was lost; design operations to be idempotent or check state.
- If the application adds a third key, that key must also be declared in `KEYS` and share the same slot.
- Long-running scripts can hurt Redis latency; avoid expensive commands or unbounded loops over large datasets.

## 12. How key naming affects RedisScript KEYS/ARGV

A common mistake is passing a key as an argument:

```java
redis.execute(script, List.of(statusKey), updatedAtKey);
```

and inside Lua:

```lua
redis.call('SET', ARGV[1], 'NEW')
```

From a Cluster design standpoint, this is not the right way to declare keys accessed by a script. Redis Cluster needs to know the script's keys up front to enforce hash slot constraints and routing.

The explicit way:

```java
redis.execute(
    script,
    List.of(statusKey, updatedAtKey),
    "NEW"
);
```

Lua:

```lua
redis.call('SET', KEYS[1], ARGV[1])
redis.call('SET', KEYS[2], ARGV[1])
return 1
```

On Redis Cluster, every Redis key touched by a script must be explicitly identified up front—never dynamically compute new key names from data stored in Redis or hide them inside JSON in `ARGV` to touch arbitrary slots.

### 12.1. Value deserialization differs from hash slot calculation

Redis calculates slots from the **bytes of the key name**. Meanwhile, data stored in the value may use String, JSON, or a binary serializer.

For a script:

```lua
local state = redis.call('GET', KEYS[1])
```

if the value was previously written using JDK serialization, `state` is not plain text `"PENDING"`. Checking `state == ARGV[1]` can fail even though the logical Java objects look identical.

Therefore:

- Standardize the **key serializer** so hash tags are recognized accurately.
- Standardize **value/args serialization** so Lua can interpret payloads.
- Standardize the **result serializer/RedisScript result type** so Java receives the right response.

These are three separate concerns. Sharing a slot does not solve serialization mismatches.

## 13. Other data types and commands also depend on slots

Hash tags are not limited to String values and `MGET`.

Example of a cart:

```text
cart:{c-77}:items        -> Redis Hash or Set
cart:{c-77}:coupon       -> Redis String
cart:{c-77}:discounts    -> Redis Hash
cart:{c-77}:total        -> Redis String
```

A Lua script can access those keys via `HGETALL`, `GET`, `HSET`, `SET`, and appropriate commands to perform a single cart operation.

For set intersections:

```text
user:{u-42}:follows
user:{u-42}:followers
```

appropriate multi-key set operations can be performed when both keys share a slot.

For Sorted Sets:

```text
leaderboard:{season-2026}:points
leaderboard:{season-2026}:bonuses
```

can be useful when operating on multiple Sorted Sets of the **same season**. However, if all seasons share the tag `{leaderboard}`, their entire load risks piling onto a single slot.

### 13.1. Do not group unrelated keys just to make commands run

Poor choice:

```text
order:{global}:101:status
order:{global}:102:status
order:{global}:103:status
```

Even though multi-key commands can run across them, you have forced every order into one slot. Ask whether the application genuinely needs a transaction across **all orders**.

If you only need to display a list of multiple orders, you can usually:

- Read individual keys via a cluster-aware client.
- Use a materialized view or dedicated index.
- Use a database/search system suited for queries.
- Use driver-supported batching/pipelining, accepting no atomic cross-slot snapshot.

Overly broad hash tags just for "convenient `MGET`" can strip Redis Cluster of its ability to scale.

### 13.2. TTLs of keys sharing a tag remain independent

Example:

```redis
SET session:{s-101}:state ACTIVE EX 60
SET session:{s-101}:lastSeen 2026-11-13T00:00:00Z EX 120
```

Both keys share a slot yet have independent TTLs. Hash tags **do not merge TTLs, do not create atomic expiration, and do not automatically clean up all keys of an aggregate simultaneously**.

If business logic requires an entire session's state to expire together, you can:

- Store state in **a single Hash key** with one TTL.
- Assign the same deadline across keys via appropriate operations while accepting operational edge cases.
- Have read logic check a central deadline.
- Use Lua/transactions when adjusting deadlines across multiple keys in one same-slot step.

Even then, expiration notifications are not millisecond-accurate timers and do not guarantee all keys with the same tag are physically purged in the exact same millisecond.

## 14. One Hash key or multiple keys sharing a hash tag?

Suppose an order has status, total amount, timestamp, and some auxiliary fields:

**Option A — one Redis Hash:**

```text
order:o-101
    status = PENDING
    total = 500000
    updatedAt = ...
```

**Option B — multiple Redis keys sharing a tag:**

```text
order:{o-101}:status
order:{o-101}:total
order:{o-101}:updatedAt
```

Comparison:

| Criterion | One Redis Hash | Multiple keys with the same hash tag |
|---|---|---|
| Number of Redis keys | Few | Many |
| Overall TTL | One TTL on the Hash key | Each key has its own TTL |
| Multiple fields | Use `HGET`, `HSET`, `HMGET` | Can use `MGET`, Lua, or multi-key commands |
| Same slot | Naturally, since it is one key | Must follow hash tag rules |
| Metadata memory | Can be more compact depending on data/encoding | Multiple keys incur per-key overhead |
| Updating one field | `HSET` | `SET` the corresponding key |
| Heterogeneous data types | Hash field-values only | Can combine Set, Hash, ZSet, String |
| Per-component TTL freedom | Limited by standard key-level TTL | More flexible |
| Multi-component transaction | Single-key operations are simpler to manage | May need same-slot script/transaction |

Consider **one Hash** if the data is naturally a small object needing a shared TTL. Choose **multiple tagged keys** when components have different data types, lifecycles, or access patterns and still need multi-key operations within an aggregate.

Hash tags are a tool to place multiple keys in the same slot, **not a reason to split a single object into many keys without clear benefit**.

## 15. Risk of hot slots and load imbalance

One hash slot belongs to one primary at a time. When many keys or heavy workloads share the same tag, they converge onto **one slot** and hence one primary.

Very broad example:

```text
order:{all-orders}:1
order:{all-orders}:2
order:{all-orders}:3
...
```

All of them hash from `all-orders`.

Even with many primaries in the Redis Cluster, traffic for these keys concentrates on the node owning that slot. Consequences can include:

- Higher CPU on that node compared to the rest.
- Increased network traffic to that node.
- Elevated p95/p99 latency for that key group.
- Skewed memory distribution.
- Expensive resharding of an oversized slot.
- Scaling out by adding primaries does not automatically distribute keys forced into the same tag.

### 15.1. Low-cardinality tags

A tag by `region` or `tenant` may create very few groups:

```text
{north}
{central}
{south}
```

If the whole system only has three tags, data primarily uses at most three slots, leaving almost all of the 16,384 slots unused.

Tagging by order ID has much higher cardinality:

```text
{t-7|o-101}
{t-7|o-102}
{t-8|o-103}
...
```

which spreads many aggregates across the slot space via the hash function.

**High cardinality does not guarantee even QPS.** A single extremely hot aggregate still concentrates on one slot. For instance, a bestselling SKU can create a hot slot even when every SKU has its own tag.

### 15.2. Evenly distributed data does not mean evenly distributed workload

Suppose there are 100,000 orders tagged by order ID, yet 80% of traffic targets `order:{o-hot}:...`. The slot for `o-hot` becomes a hot slot.

Hash tags colocate keys needing atomicity, but they cannot split **one single aggregate** across multiple slots while preserving old-style Redis Cluster multi-key atomicity.

Options when an aggregate gets hot:

- Reduce Redis commands on the hot path.
- Use a single appropriate key/data type instead of multiple operations.
- Cache at the application tier if the workload permits.
- Partition read-heavy data under an eventual consistency model.
- Design sharded counters when business logic tolerates non-instantaneous atomic totals.
- Use another database/transactional service when strong cross-partition consistency is needed.
- Revisit aggregate boundaries if the business domain allows.

Do not "fix" a hot slot by arbitrarily changing the tag on a few keys within the same transaction: doing so breaks the same-slot invariant.

### 15.3. Measure actual load rather than just key counts

`CLUSTER COUNTKEYSINSLOT` reports how many keys sit in a slot on the queried node, but **key count does not directly reflect QPS or CPU**. One hot key can generate more load than thousands of cold keys.

Monitor:

- Command rate and latency per node/slot/key where telemetry allows.
- Redis CPU, memory, network, and evictions.
- Client-side latency, timeouts, and redirects.
- Slot distribution across primaries.
- Hot keys/commands and access patterns.
- Volume, execution duration, and concurrency of multi-key scripts.

An application with hash tags that are completely correct functionally may still require performance tuning.

## 16. Choosing realistic transaction boundaries

Consider an ordering service with these data groups:

```text
Order:
    order:{o-101}:status
    order:{o-101}:total
    order:{o-101}:items

Inventory:
    stock:{sku-42}:available
    stock:{sku-42}:reserved

Customer:
    customer:{u-7}:profile
    customer:{u-7}:loyalty
```

Within each aggregate, keys share a tag. However, a checkout flow may need to modify **order + inventory + customer**.

You have two broad design paths:

**Approach 1 — place everything under one transaction tag:** usually infeasible when participating data spans multiple orders, SKUs, and customers; creates tight coupling and massive hot slots.

**Approach 2 — keep aggregate boundaries small and coordinate steps across aggregates:** use transactions in an appropriate source-of-truth datastore, sagas, reservations, idempotency, outbox, pending states, and compensating actions.

Example workflow:

```text
1. Reserve inventory for sku-42 using an atomic operation in sku-42's slot.
2. Create/update order state in o-101's slot.
3. Record outcomes of steps 1 and 2 via eventId/idempotency key.
4. If step 2 fails, run reservation compensation logic.
5. Reconcile to handle mid-flight timeouts/crashes.
```

This is more complex than a single Redis script, yet reflects the reality that **Redis Cluster does not provide built-in distributed transactions** across multiple slots.

### 16.1. Can tagging by request ID rescue cross-aggregate transactions?

Suppose you create:

```text
order:{request-1}:status
stock:{request-1}:reserved
```

These two keys share a slot, but they are **per-request keys**, no longer the shared SKU inventory or canonical order keys. If you try to bind shared state to a request tag, concurrent requests will not see the same state.

A single tag cannot simultaneously represent multiple independent aggregates in a way that lets every aggregate update atomically in arbitrary transaction combinations. That is a property of a partitioned data model, not a missing Redis syntax feature.

## 17. Hash tags and Redis Streams

Streams are also Redis keys. If a workflow needs to append an event to a Stream alongside updating other data in a Lua script, every key used in the atomic operation must be slot-compatible.

Example:

```text
order:{o-101}:status
order:{o-101}:events
```

If `events` is a per-order Redis Stream holding only events for order `o-101`, both keys share a slot and can participate in an appropriate same-slot atomic mechanism.

Conversely:

```text
order:{o-101}:status
orders:global:events
```

a system-wide aggregated Stream can live in another slot. You cannot assume updating status and issuing `XADD` to the global Stream form an atomic transaction on Redis Cluster.

Options:

- Scope Streams per aggregate/partition.
- Use a transactional outbox in the source system and then publish to the Stream.
- Accept two steps and implement retry/reconciliation.
- If co-location is needed, consider tagging by small partition, while avoiding turning a single Stream into a hot slot.

**Redis Stream consumer groups do not change the hash slot of the Stream key.** The PEL is group metadata attached to the Stream; it does not create cluster-wide transactions across arbitrary Streams.

## 18. Hash tags and Redis Repository

Spring Data Redis Repository provides mechanisms for storing entities, secondary indexes, TTLs, and queries. Repository operations may touch **multiple Redis keys**, not just the primary entity Hash key.

Conceptual model:

```text
Entity Hash
Secondary index Set
TTL/shadow copy
Index cleanup metadata
```

Even if the entity Hash key carries its own tag, shared index keys may land in other slots. Thus, never assume:

> "I added `{id}` to an entity key name, so all Redis Repository features automatically become valid multi-key Cluster transactions."

Inspect the mapping, serializers, index mechanisms, actual Redis commands issued, and Cluster limitations for your Spring Data Redis version.

One design approach is keeping **simple key-value or Hash access** for workloads easy to tag, and using a dedicated search/query system if cross-entity/cross-slot queries are needed. If atomic secondary-index updates are required, carefully evaluate your data model and library capabilities.

### 18.1. Hash tags do not turn cross-slot lookups into cluster-wide queries

Suppose the application wants to find all orders currently `PENDING`. If each order has its own tag:

```text
order:{o-101}:status
order:{o-102}:status
order:{o-103}:status
```

hash tags do not magically build a centralized index by status. A Redis Set holding all pending orders is a separate key that can live in another slot.

If you want to update a global Set simultaneously with each order inside one script, you run into slot boundaries. The system may need eventual index maintenance, background reconciliation, or a different query engine instead of forcing every order into one slot.

This is a fundamental trade-off:

```text
Atomic per aggregate + good distribution
    vs
Global index/aggregate updated atomically with every entity
```

No single pair of curly braces can satisfy both simultaneously across all designs.

## 19. Transactions, pipelines, and batches are not the same thing

A Java API can send multiple Redis commands, so distinguish carefully:

| Mechanism | Goal | Same-slot and atomicity |
|---|---|---|
| Single `GET key` command | Read one key | No key grouping required |
| Single `MGET k1 k2` command | Read multiple keys in one command | Redis Cluster requires command slot compatibility |
| Two `GET k1`, `GET k2` commands | Independent reads | Cluster-aware client can route to different nodes; not atomic |
| Pipeline | Reduce network overhead and batch requests | Does not turn commands into a transaction |
| `MULTI`/`EXEC` | Execute a command batch under Redis transaction semantics | Does not support multi-slot transactions |
| Lua/Redis Function | Execute server-side logic un-interleaved | Key access must obey Cluster constraints |
| Distributed workflow | Coordinate operations across services/slots | Requires dedicated consistency/retry design |

### 19.1. Why don't pipelines fix CROSSSLOT?

Suppose a client pipelines:

```text
GET order:{o-101}:status
GET order:{o-102}:status
```

Two single-key reads can be sent individually to the proper primaries by a cluster-aware client. That is not an atomic `MGET`.

If a pipeline contains an `MGET` with keys in different slots, the `MGET` itself can still fail with `CROSSSLOT`. Pipelining does not bypass slot calculation.

### 19.2. Do multi-slot reads provide a consistent snapshot?

No. If Java runs:

```text
GET keyA on primary A
GET keyB on primary B
```

data can change between the two reads. Proper routing by a cluster-aware client does not guarantee a **point-in-time snapshot** across keys on different primaries.

If you only need to display a dashboard with eventual consistency, distributed reads may be fine. If strong business invariants are required, move consistency logic into an appropriate transactional boundary.

## 20. How do MOVED, ASK, and resharding relate?

When the Cluster changes topology or moves slots:

- `MOVED` signals a redirect to the node owning the new slot.
- `ASK` relates to active slot migration and requires a temporary redirect per Cluster protocol.
- Cluster-aware clients like Lettuce can refresh topology and handle redirects according to capabilities/configuration.
- Some multi-key operations or commands during migration can hit transient limits/errors and need bounded retries.

Key insight:

```text
Hash tag -> determines a stable slot from the key name.
Slot owner -> can change with topology.
```

Example:

```text
order:{o-101}:status -> slot S
order:{o-101}:items  -> slot S
```

After resharding, both keys still belong to slot `S`, though slot `S` may move to a different primary.

**Hash tags do not pin keys forever to one specific node.** They only ensure both keys always map to the same slot algorithmically.

### 20.1. Redirects do not bypass CROSSSLOT

A redirect resolves a client sending a command to a node that does not own the key's slot. It **does not change** the fact that two keys in the same command belong to two different slots.

Example:

```text
MGET k1 k2
   |
   +-- k1 in slot S1
   +-- k2 in slot S2
   |
   v
CROSSSLOT
```

No single node becomes a valid destination for an `MGET` spanning two different slots simply because the client knows the topology.

### 20.2. Do not blindly retry every write

When a connection timeout or failover occurs, the client may not know whether Redis executed the command. Retrying:

```redis
INCR order:{o-101}:counter
```

blindly can increment it twice if the first attempt succeeded and the reply was lost.

Hash tags do not eliminate outcome ambiguity after a timeout. Use idempotency tokens, compare-and-set scripts, or proper state modeling when business logic cannot tolerate duplicates.

## 21. Migrating from untagged keys to tagged keys

An application previously on standalone might store:

```text
order:o-101:status
order:o-101:items
```

After moving to Cluster, you want:

```text
order:{o-101}:status
order:{o-101}:items
```

**Adding a hash tag changes the actual key name**, not just a routing setting. Redis treats them as completely different keys.

Consequently, changing only the key-building function in Java without migrating data can cause the application to read `null` and appear as though the cache was wiped.

### 21.1. Controlled migration steps

A general strategy:

1. Identify all key producers: HTTP services, background workers, Lua scripts, repositories, schedulers, batch tools.
2. Define the new KeyFactory and required tags.
3. Inventory legacy data: key names, types, TTLs, serialization, volume.
4. Decide whether you can **rebuild caches** from the source of truth or must migrate state.
5. If rebuildable, let old cache keys expire or delete them systematically, then switch readers/writers.
6. If state must be preserved, implement controlled copy/restore/dual-read mechanisms.
7. Use versioned key namespaces so old/new readers do not misinterpret formats.
8. Roll out gradually by traffic slice and monitor Redis errors.
9. Once all services use the new format, clean up old keys per retention policy.
10. Keep rollback capability until migration stabilizes.

### 21.2. RENAME is not a general cross-slot solution

In standalone Redis, `RENAME old new` renames a key directly. In Redis Cluster, `RENAME` requires key names to satisfy slot constraints.

An untagged old name and a tagged new name usually hash to two different slots. Therefore, **never assume `RENAME` can migrate between them**.

You may need client-assisted copy/move supported by drivers/tools—which crosses two nodes and is not atomic—or rebuild state from the source of truth. Ensure TTLs and metadata transfer properly and handle races while the application still writes to old keys.

### 21.3. TTLs must be preserved if state is not pure cache

If an old key has 30 seconds remaining, yet during migration you recreate the new key with a 1-hour TTL, you might accidentally extend an expiring token, lock, or session.

During migration:

- Read the remaining TTL or absolute deadline using supported commands.
- Preserve valid expiration deadlines.
- Distinguish `-1` (no expiration) from `-2` (does not exist).
- Avoid resurrecting already-expired entries.
- Guard against races between reading TTL, copying value, and writing the new key.
- Prefer migrating at the data owner if the data has security or business significance.

For sensitive tokens/leases, migration logic must be much stricter than for rebuildable caches.

## 22. Common errors and how to diagnose them

### 22.1. `CROSSSLOT Keys in request don't hash to the same slot`

**Cause:** at least two keys in a command requiring same-slot belong to different slots.

**Resolution:** inspect the exact keys passed, run `CLUSTER KEYSLOT` on each key, then fix key naming or redesign the operation. Do not fix via repeated retries.

### 22.2. "Keys share the same order yet MGET still fails"

The names might be:

```text
order:o-101:status
order:o-101:items
```

They share a prefix but lack a hash tag. Switch to:

```text
order:{o-101}:status
order:{o-101}:items
```

and migrate data as needed.

### 22.3. "I added a tag yet the keys still land in different slots"

Inspect the first `{`/`}` characters, empty tags, misplaced tags, a service passing a different tag, or a different key serializer. Redis only uses the **first valid tag according to parser rules**, not arbitrary brace pairs in the name.

### 22.4. "Both keys are on the same node, why does MSET fail?"

Because same-node is not same-slot. Redis Cluster enforces the constraint on the hash slots of multi-key commands. Current primary address is not a sufficient condition.

### 22.5. "Cluster-aware Lettuce can GET both, why does MGET fail?"

Two independent `GET` calls are routed to two slots. One `MGET` is a single command with multi-key constraints. A client may support splitting in some versions, yet you must not assume identical atomic semantics.

### 22.6. "Lua script failed even though both keys were created on the same server"

Lua in a Cluster requires key access to satisfy same-slot constraints and proper `KEYS` declarations. Same server is insufficient.

### 22.7. "After adding `{tenant}`, the system slowed down"

Many keys of a single tenant were funneled into one slot. If that tenant is hot, that slot/node gets overloaded. Consider tagging by order, cart, SKU, or a smaller aggregate.

### 22.8. "After resharding, keys moved to another node"

That is normal Redis Cluster behavior. Hash tags determine the slot, not a pinned node. Use a cluster-aware client and redirect handling.

### 22.9. "Changing key format lost data"

The new key name differs from the old name; Redis does not automatically rename/migrate when `{}` is added. Migration or rebuilding is required.

### 22.10. "Tag is right, yet Lua reads garbled data"

Slots do not determine value serialization. If keys were stored using JSON/JDK serialization while Lua expects plain String, comparisons/`tonumber` will fail. Verify the wire format.

### 22.11. "Keys share a tag yet transactions remain inconsistent"

The application may be issuing two independent `SET` calls or the script may hit a runtime error after partial writes. Hash tags only satisfy placement constraints; atomic operation design must still be sound.

### 22.12. "One tenant has tens of millions of keys in one slot"

Tenant-level tagging is too broad. You may need to move to aggregate-level tags and adopt cross-aggregate workflows instead of tenant-wide Redis transactions.

### 22.13. "A key lost its old TTL after changing tags"

Renaming or copying data does not automatically preserve deadlines the way the application expects. Check migration and expiration logic.

### 22.14. "Reads sometimes succeed and sometimes return MOVED/TRYAGAIN"

Topology may be updating or slots may be migrating. Use a Cluster-aware client, logging, bounded retries, and monitor node health. Never alter hash tags based on which node address responded.

## 23. Checklist when designing a multi-key workflow

Instead of starting from a Redis command, state the invariant first:

**Example:** "Transitioning cart status and updating the total must be an atomic operation for exactly one cart."

Step 1 — Identify the aggregate:

```text
Aggregate = cartId
```

Step 2 — List the keys:

```text
cart:{c-77}:status
cart:{c-77}:total
cart:{c-77}:discount
```

Step 3 — Choose a shared tag:

```text
c-77
```

Step 4 — Verify:

```redis
CLUSTER KEYSLOT cart:{c-77}:status
CLUSTER KEYSLOT cart:{c-77}:total
CLUSTER KEYSLOT cart:{c-77}:discount
```

Step 5 — Select the atomic primitive:

```text
If only writing multiple Strings: MSET may suffice.
If conditions/comparisons are needed: Lua or WATCH/MULTI fits.
```

Step 6 — Define outcomes and errors:

```text
SUCCESS
INVALID_STATE
MISSING_CART
RETRYABLE_INFRA_ERROR
UNKNOWN_AFTER_TIMEOUT
```

Step 7 — Control TTL, serialization, and idempotency.

Step 8 — Measure per-cart QPS and cart distribution across slots.

Step 9 — Test failover/resharding in an appropriate environment and verify client handling.

Step 10 — Whenever adding a new key to the workflow, require it to use the same KeyFactory and tag.

### 23.1. Quick decision table

| Question | If Yes | Consequence |
|---|---|---|
| Do these keys need a single `MGET`/`MSET`? | Yes | Place in the same slot with an appropriate tag |
| Does a script need to read and update the whole group? | Yes | Keys accessed by the script must share a slot |
| Only need to read each key independently? | Yes | Does not necessarily need the same slot |
| Is one key accessed at extremely high rates? | Yes | Beware hot slots if grouping additional keys |
| Does the workflow span multiple orders/SKUs/customers? | Yes | Re-examine transaction boundaries; distributed coordination may be needed |
| Do existing key names lack tags? | Yes | Plan for migration or rebuild |
| Are keys created by multiple serializers? | Yes | Standardize wire keys before relying on hash tags |
| Do multiple environments/tenants share IDs? | Yes | Include namespace identifiers in keys and tags per rules |

## 24. Lab 1 — Visualizing hash slots

Connect to a test Redis Cluster and run:

```redis
CLUSTER KEYSLOT profile:{u-7}:name
CLUSTER KEYSLOT profile:{u-7}:avatar
CLUSTER KEYSLOT profile:{u-7}:settings
```

Record the three slot numbers.

Compare with:

```redis
CLUSTER KEYSLOT profile:u-7:name
CLUSTER KEYSLOT profile:u-7:avatar
CLUSTER KEYSLOT profile:u-7:settings
```

Explain why sharing `u-7` is insufficient to force all keys into the same slot without a tag.

Extension:

```redis
CLUSTER KEYSLOT profile:{u-8}:name
```

Compare with `profile:{u-7}:name`. Two different tags are **not guaranteed** to return different slots because CRC16 modulo 16384 can collide; what matters is that there is no same-slot contract between two distinct aggregates.

## 25. Lab 2 — Analyzing brace rules

Without creating keys first, predict which portion Redis hashes for these names:

```text
a{tenant-7}x
b{tenant-7}y
a{}b{tenant-7}
a{tenant-7
a{tenant-7}{order-101}
a{order-101}
a{Tenant-7}
```

Then run `CLUSTER KEYSLOT` to verify which groups share a slot.

Questions:

1. Why do `a{tenant-7}x` and `b{tenant-7}y` share a slot?
2. Why does `a{}b{tenant-7}` not pick the second tag?
3. Why should `{tenant-7}` and `{Tenant-7}` not be treated as the same tag?
4. For `a{tenant-7}{order-101}`, does Redis use tenant or order?
5. If you want to tag by both tenant and order, where should the identifiers be combined?

## 26. Lab 3 — MGET/MSET and CROSSSLOT

Create:

```redis
SET cart:{c-77}:status ACTIVE
SET cart:{c-77}:coupon SAVE10
MGET cart:{c-77}:status cart:{c-77}:coupon
```

Next run:

```redis
CLUSTER KEYSLOT cart:{c-77}:status
CLUSTER KEYSLOT cart:{c-88}:coupon
```

If the two slots differ, try:

```redis
MGET cart:{c-77}:status cart:{c-88}:coupon
```

Observe the error. If the two tags happen to collide on the same slot, change `c-88` to another ID with a different slot and retry.

Explain: `MGET` cannot turn into an atomic snapshot across two primaries simply because the CLI uses `-c` to follow redirects.

## 27. Lab 4 — Java KeyFactory

Write the `OrderRedisKeys` class as shown in section 10.

Requirements:

1. `status("t-7", "o-101")` and `items("t-7", "o-101")` must share the same tag.
2. `status("t-7", "o-102")` must use a different tag from aggregate `o-101`.
3. Inputs containing `{` or `}` must be rejected or safely encoded.
4. Different services must generate identical strings for the same IDs.
5. Use `CLUSTER KEYSLOT` to verify the generated key bytes.
6. Add a `version` component without breaking the tag format.

Discuss why a shared KeyFactory is preferable to each controller concatenating Redis key Strings manually.

## 28. Lab 5 — Lua order state transition

Use the `transition-order.lua` script from section 11.

1. Initialize:

   ```redis
   SET order:{t-7|o-101}:status PENDING
   ```

2. Call `OrderTransitionService.markPaid("t-7", "o-101")`.
3. Read `status` and `updatedAt` to verify the outcome.
4. Call `markPaid` a second time and observe the status code.
5. Change one key to `{t-7|o-102}` and inspect the slot and execution behavior.
6. Explain why comparing inside Lua prevents the `GET -> SET` race under concurrent requests.
7. Discuss a script timeout after Redis has already updated the state: how should a retry behave?

## 29. Lab 6 — Hot slots from overly broad tags

Suppose a system has 1 million keys:

```text
order:{global}:<id>:status
```

and a 10-primary Redis Cluster.

Answer:

- How many distinct slots do these keys use under hash tag rules?
- Will adding more primaries automatically split those keys?
- If switched to `order:{<orderId>}:status`, how does the number of distinct tags increase?
- Can a single extremely hot order still be an issue?
- If the business needs to read 1,000 independent orders on a dashboard, is a single atomic `MGET` required?
- What strategies are better than forcing all data into a global tag?

Use `CLUSTER KEYSLOT` on a few representative keys to illustrate. You do not need to actually create one million keys.

## 30. Lab 7 — Migration and TTL

Suppose legacy data:

```text
session:s-101:state
session:s-101:lastSeen
```

needs to change to:

```text
session:{s-101}:state
session:{s-101}:lastSeen
```

Requirements:

1. Explain why Redis treats these as new keys.
2. Explain the limitation of `RENAME` in a Cluster if old and new names land in different slots.
3. List the data to preserve: value, type, TTL/deadline, serialization.
4. Outline a dual-read/rebuild approach with a writer cutover plan.
5. Identify what happens if the old key's TTL expires during migration.
6. Propose post-deploy metrics to watch: cache misses, CROSSSLOT, timeouts, old-key reads, and new-key reads.

## 31. Lab 8 — Designing business boundaries

Problem: checkout requires:

```text
order status
cart total
inventory available
customer loyalty balance
```

The data belongs to four different aggregates.

Design:

- Hash tags for each aggregate.
- Which operations can be atomic via scripts within a single aggregate.
- Which operations require cross-aggregate coordination.
- Where the idempotency token belongs.
- How to handle inventory deduction succeeding while order recording fails.
- How reconciliation recovers after timeouts or crashes.

Explain why tagging all keys with `{checkout-global}` is not a scalable solution.

## 32. Self-assessment questions

1. How many hash slots does Redis Cluster have?
2. What is the basic formula to compute a slot from a key name?
3. Which part of the CRC16 input does a hash tag change?
4. Why are `order:101:status` and `order:101:items` not guaranteed to share a slot?
5. Why are `order:{101}:status` and `order:{101}:items` guaranteed to share a slot?
6. If two `{...}` pairs appear in a key, which pair does Redis use?
7. What happens when the first pair is an empty `{}`?
8. Is being on the same primary node sufficient for a multi-key command to run?
9. Does `CLUSTER KEYSLOT` require the key to exist?
10. Does a cluster-aware client automatically following `MOVED` redirects solve `CROSSSLOT`?
11. Can a key using `StringRedisSerializer` and a key using Java serialization land in different slots despite similar Java Strings?
12. Why do same-slot `MSET` and two separate `SET` commands differ in atomicity?
13. Where must Lua in Redis Cluster declare key names?
14. Why is hiding keys in `ARGV` an anti-pattern?
15. Do hash tags automatically guarantee rollback on runtime errors inside a script?
16. Why is using `{global}` for all keys risky?
17. When might a tenant-level tag fit, and when should it be per-order?
18. Can you design an atomic transaction across two SKUs in different slots using `MULTI` alone?
19. Why is a single Redis Hash sometimes better than multiple keys sharing a hash tag?
20. Why does adding a hash tag to legacy key names require migration or rebuilding?
21. What happens to a slot when its primary owner changes due to resharding?
22. If one SKU is extremely hot, what limit can per-SKU tagging run into?
23. Why do TTLs of keys sharing a tag remain independent?
24. How can you verify two different keys share a slot without writing any data?
25. When a workflow spans multiple aggregates, what principle should guide transaction boundaries?

## 33. Key takeaways

- Redis Cluster computes slots via `CRC16(hash_input_bytes) mod 16384`, with a fixed **16,384 slots**.
- When a key name has a valid `{...}` hash tag, Redis uses the **non-empty bytes inside the first selected brace pair** as hash input; otherwise, Redis uses the entire key name.
- Keys such as `order:{o-101}:status` and `order:{o-101}:items` **are guaranteed to share the same hash slot** despite different names; each key remains an independent Redis key.
- **Same slot differs from same node.** Redis Cluster enforces slot checks for applicable multi-key commands, even when two slots happen to be served by the same primary.
- Use `CLUSTER KEYSLOT` to verify key naming. Matching prefixes, tenants, or aggregate IDs outside `{}` are **not enough**.
- Hash tags satisfy constraints for `MGET`, `MSET`, Lua, transactions, and other multi-key operations, yet **do not turn multiple independent calls into an atomic operation**.
- Design tags around the **aggregate needing atomicity**, avoiding putting all keys under `{global}` or overly broad tenant tags that cause **hot slots**.
- In Spring Data Redis, standardize the **key serializer** (commonly `StringRedisSerializer`) so actual key bytes carry the desired tag; value serialization is a separate contract.
- Use a centralized **KeyFactory** to normalize tenant/order IDs, prevent `{}` in input data from altering tags, and enforce consistent key names across services.
- Scripts must declare keys via `KEYS`; do not hide Redis keys in `ARGV` to bypass partitioning. `MOVED`/`ASK` redirects do not make cross-slot transactions valid.
- Changing legacy keys to a tagged format changes **actual key names**, requiring migration/rebuilding and preserving TTLs for critical state.
- When workflows must update multiple independent aggregates, design idempotency, source-of-truth transactions, events/outbox, or sagas rather than collapsing the whole system into one slot.
- Hash tags are a **deliberate tool for colocating data in the same slot**, not a promise that every operation across tagged keys is consistent, durable, or infallible after crashes.

### Official references

- [Redis — Redis Cluster specification: key distribution model](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Redis — Redis Cluster tutorial](https://redis.io/docs/latest/operate/oss_and_stack/management/scaling/)
- [Redis — CLUSTER KEYSLOT](https://redis.io/docs/latest/commands/cluster-keyslot/)
- [Redis — MGET](https://redis.io/docs/latest/commands/mget/)
- [Redis — MSET](https://redis.io/docs/latest/commands/mset/)
- [Redis — MULTI](https://redis.io/docs/latest/commands/multi/)
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/)
- [Redis — RENAME](https://redis.io/docs/latest/commands/rename/)
- [Redis — SET](https://redis.io/docs/latest/commands/set/)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
