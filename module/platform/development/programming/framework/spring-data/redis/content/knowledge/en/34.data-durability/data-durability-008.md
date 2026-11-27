# Migrating Data When Changing Namespaces, Serializers, or Storage Structures

## 1. Problem: upgrading the application while Redis data still persists

A Spring Boot application using Spring Data Redis has been running in production for a long time. The older version might store customer profiles via Java serialization under keys like:

```text
customer:42
```

After upgrading, the development team wants to:

1. Rename keys to an explicitly versioned namespace: `app:customer:profile:v2:42`.
2. Replace Java serialization with JSON for readability and independence from Java class definitions.
3. Change storage from a single Redis String containing an object to a Redis Hash to update only individual fields.

If you simply update the code and deploy:

```java
redisTemplate.opsForValue().get("app:customer:profile:v2:42");
```

the new application will miss old data even though Redis still holds many prior-version keys. Even if the key name matches, the new serializer cannot decode bytes written by the old serializer. Switching from String to Hash causes `HGETALL` on an existing String key to fail with `WRONGTYPE`.

A continuously running system must also account for:

- Some instances still running old code during a rolling deployment.
- Keys carrying TTLs that may expire while being copied.
- Users updating data while a backfill job runs.
- Redis replicas, Sentinel, or Cluster experiencing failover.
- Multiple application versions reading and writing concurrently.
- A rollback path allowing old versions to keep working if deployment fails.

**Migrating Redis data is a storage-protocol change across application versions, not just changing a prefix string.**

This lesson belongs to the **Data Durability** chapter in **Spring Data Redis**. The focus is planning transitions across namespaces, serializers, and Redis structures in phases that are observable, preserve semantics, and support safe recovery on failure.

## 2. Three types of changes to distinguish

### 2.1. Changing key namespaces

Before and after:

```text
Old: profile:42
New: app:profile:v2:42
```

Data may still be a Redis String with the same encoding, yet **the key lookup path** changed.

In Spring Data Redis, the key serializer determines raw key bytes. So even when Java calls `"profile:42"`, Redis may actually store JDK-serialized bytes if the legacy key serializer was not `StringRedisSerializer`.

**Classic mistake:** changing only the prefix in code turns every read into a miss. If Redis is a cache, the app rebuilds from origin; if Redis holds authoritative data, users see vanished records.

### 2.2. Changing serializers

The exact same logical object:

```json
{
  "id": 42,
  "displayName": "Lan",
  "level": 3
}
```

serializes into completely different bytes:

```text
Java serialization -> binary stream with class metadata
JSON serialization -> UTF-8 JSON string
String serializer   -> UTF-8 bytes of the string
Custom binary codec -> application-defined custom format
```

Merely changing:

```java
template.setValueSerializer(...);
```

does not convert existing values already inside Redis.

If the legacy serializer was JDK and the new serializer is JSON, reading old entries throws decoding errors. If the key serializer also changed, `GET` will not even locate the key.

For serializer migrations, explicitly define **the legacy reader**, **the new writer**, and schema mapping from old model to new model.

### 2.3. Changing data structures

Suppose the old format stores a JSON String:

```redis
SET app:profile:v1:42 "{\"displayName\":\"Lan\",\"level\":3}"
```

The new version switches to a Hash:

```redis
HSET app:profile:v2:42 displayName "Lan" level "3"
```

This is not just a serializer change. The Redis data type itself changed:

| Redis type | Common commands | Characteristics |
|---|---|---|
| String | `GET`, `SET` | Single monolithic value, suitable for blobs/JSON |
| Hash | `HGET`, `HSET`, `HGETALL` | Multiple field/value pairs under one key |
| List | `LPUSH`, `LRANGE` | Ordered elements with head/tail operations |
| Set | `SADD`, `SMEMBERS` | Unordered collection of unique members |
| Sorted Set | `ZADD`, `ZRANGE` | Members paired with scores |
| Stream | `XADD`, `XREADGROUP` | Event log entries with IDs and consumer groups |

You cannot swap `GET` for `HGETALL` and expect Redis to parse JSON into Hash fields automatically. Accessing the wrong type returns `WRONGTYPE`.

### 2.4. All three changes can happen at once

Example:

```text
Version 1:
  key      = profile:42
  type     = String
  encoding = JDK Serializable object

Version 2:
  key      = app:profile:v2:42
  type     = Hash
  encoding = UTF-8 String fields
```

Changing everything in one unphased deploy carries far higher risk than changing a prefix alone.

## 3. First: determine whether Redis is a cache or an authoritative data source

The same Redis engine implies very different migration requirements.

### 3.1. Redis is only a cache

Suppose the authoritative source lives in PostgreSQL:

```text
PostgreSQL (source of truth)
           |
           v
       Redis cache
           |
           v
      Spring API
```

If the entire cache can be rebuilt from PostgreSQL, a simple rollout can:

1. Introduce the new namespace.
2. Have the new version write only to the new cache namespace.
3. Warm the new cache gradually or via bounded prewarming.
4. Keep old keys alive during the rolling deployment.
5. Delete old keys after all old instances stop and legacy TTLs expire.

You do not necessarily have to copy every cached key. Still account for **cache stampedes**: if millions of new keys miss at once, the database can overload.

### 3.2. Redis holds data that cannot be easily rebuilt

Examples:

- Counters written solely to Redis.
- Session or workflow state with no database copy.
- Queues, Streams, or Sorted Sets holding unprocessed jobs.
- Locks, idempotency records, or business-critical entitlements.

For these, "switch namespaces and let it repopulate" causes real data loss.

You need to:

- Inventory structures and state.
- Identify the authoritative source and recovery path.
- Ensure no concurrent writes are dropped during migration.
- Preserve counter monotonicity and competitive state invariants.
- Avoid recreating processing state merely by copying payloads when critical metadata lives in Redis.

**Never apply a disposable-cache workflow to durable data simply because both live in Redis.**

## 4. Build an inventory before changing schemas

Migration documentation should specify both **logical structure** and **actual on-the-wire bytes**.

| Item | Example to specify |
|---|---|
| Old keyspace | `profile:*` |
| New keyspace | `app:profile:v2:*` |
| Key serializer | UTF-8 String vs. JDK binary |
| Value serializer | JDK, JSON, String, custom |
| Redis type | String, Hash, Set, Stream... |
| Old schema | Fields, types, optional values |
| New schema | Renamed fields, enums, defaults |
| TTL | Expiring, persistent, expiration rules |
| Data source | Database, primary Redis, event log |
| Writers | APIs, jobs, listeners, consumers |
| Readers | Web, batch, cron, other services |
| Accuracy requirements | Whether stale/legacy reads are allowed |
| Retention | When old data may be deleted |
| Topology | Standalone, Sentinel, Cluster |
| Rollback capability | Which data old code can still read |
| Backup & restore | Verified restorable backups exist |

An easily missed detail is **writers outside HTTP paths**: scheduled jobs, consumer groups, Lua scripts, internal services, or lingering old app instances. They can keep writing legacy schema data after the main API cuts over.

### 4.1. Inspecting actual data types in Redis

For a known key:

```redis
TYPE profile:42
PTTL profile:42
```

`TYPE` reveals the current Redis data type. `PTTL` returns remaining TTL in milliseconds.

Example:

```text
TYPE => string
PTTL => 29500
```

Avoid running `GET` on arbitrary keys and logging values, as payloads may be large or sensitive.

### 4.2. Key serializers are part of the schema

These two Java calls produce **two distinct physical keys** despite having the same logical key string:

```java
stringRedisTemplate.opsForValue().set("profile:42", "...");
```

and:

```java
redisTemplateWithJdkKeySerializer.opsForValue()
        .set("profile:42", someValue);
```

One writes UTF-8 bytes; the other writes JDK-serialized bytes of a Java `String`. Running `SCAN MATCH profile:*` in `redis-cli` matches raw UTF-8 prefixes and will **miss** binary-serialized keys that the app treats as `"profile:42"`.

Inventories must therefore inspect the legacy version's actual serializer, not just string literals in code.

## 5. Common migration strategies

### 5.1. Big-bang: cut over during a write freeze

```text
Pause writers
      |
      v
Read all legacy data
      |
      v
Transform + write new data
      |
      v
Reconcile
      |
      v
Deploy new code everywhere
      |
      v
Resume writers
```

Pros:

- Minimal race conditions with live mutations.
- Clean snapshot boundary if writers are truly paused.
- Simpler reasoning.

Cons:

- Requires downtime or write restrictions.
- Large datasets make maintenance windows unpredictable.
- Mid-run failures require rollback or idempotent reruns.

Suitable for moderate datasets, businesses accepting maintenance windows, or systems able to freeze all writers cleanly.

### 5.2. Lazy migration: transform on read

```text
App v2 receives GET
      |
      v
Read v2 key
      |
    +-----+
    |     |
   Hit   Miss
    |     |
    v     v
  Return  Read v1 key
                 |
          +------+------+
          |             |
         Hit           Miss
          |             |
          v             v
      Convert      Not found /
       to v2        read origin
          |
          v
      Write v2 key
          |
          v
      Return data
```

Pros:

- Conversion cost spreads over live traffic.
- Cold keys incur zero upfront backfill load.
- Supports gradual rollout.

Cons:

- Unread keys never migrate.
- First read incurs extra latency.
- Races can occur between reading the old key and writing the new key.
- If both writer generations remain active, data can diverge.

Lazy migration fits caches or reconcilable data. Durable data needing complete conversion typically pairs this with **backfill**.

### 5.3. Batch backfill and cutover

```text
Phase 1: Deploy code capable of reading both v1 and v2
Phase 2: Begin writing v2 data per policy
Phase 3: Scan v1 and convert in batches to v2
Phase 4: Reconcile and shadow-read
Phase 5: Switch primary reads to v2
Phase 6: Maintain rollback capability
Phase 7: Drop v1 support and clean up legacy data
```

This is the **expand → migrate → contract** strategy: expand compatibility first, migrate data next, and finally remove the legacy path.

### 5.4. Dual-write and dual-read

For continuous uptime, both write paths can run during a transition period:

```text
Write business data
          |
      +---+---+
      |       |
      v       v
   Write v1  Write v2
```

However, **two independent Redis commands are not a cross-topology transaction**, especially when keys land in different hash slots in Redis Cluster. Writing v1 can succeed while v2 fails.

When an authoritative database exists, prefer writing business state to the database and rebuilding cache deterministically. When Redis is the primary store, enforce versioning/atomicity/idempotency or a durable event log; never treat dual-write alone as a consistency guarantee.

## 6. Designing evolvable key namespaces

A key name should carry clear context without turning unwieldy.

Example:

```text
svc:catalog:product:v2:42
```

Readable as:

- `svc`: application group.
- `catalog`: business domain.
- `product`: data entity type.
- `v2`: schema or storage version.
- `42`: logical identifier.

For multi-tenant data:

```text
tenant:acme:catalog:product:v2:42
tenant:other:catalog:product:v2:42
```

Omitting tenant identifiers from keys risks cross-tenant data leakage.

### 6.1. Never mix Redis types under the same key

Never let legacy code execute:

```redis
SET profile:42 "{\"name\":\"Lan\"}"
```

while new code executes:

```redis
HSET profile:42 name "Lan"
```

If `profile:42` is a String, `HSET` returns `WRONGTYPE`. Deleting the String and creating a Hash under the same name immediately breaks legacy readers.

Use **separate new keys**:

```text
profile:v1:42  -> Redis String
profile:v2:42  -> Redis Hash
```

so both application versions can run concurrently during transition.

### 6.2. Key schema version vs. data revision

Example:

```text
Key schema version: profile:v2:42
Data revision:      revision=187
```

`v2` indicates the **storage protocol**. `revision=187` indicates the **content version** used to resolve concurrent update races.

Never treat `v2` as proof that a payload is newer than every entry in `v1`.

### 6.3. Redis Cluster hash slots note

Redis Cluster assigns every key to a hash slot. To run a Lua script atomically across both old and new keys, both must map to the same hash slot.

You can use matching hash tags:

```text
profile:{42}:v1
profile:{42}:v2
```

Redis hashes only the `{42}` substring, placing both keys in the same slot.

Example:

```redis
CLUSTER KEYSLOT profile:{42}:v1
CLUSTER KEYSLOT profile:{42}:v2
```

If legacy v1 keys lacked hash tags, you cannot assume a Lua script can touch both v1 and v2 keys in Redis Cluster. **`CROSSSLOT`** is a classic error when migrating namespaces with atomic scripts.

Never force all keys in a system onto one static hash tag, as that hotspots a single slot.

## 7. Managing Spring Data Redis serializers explicitly

### 7.1. Configuring key and value independently

`RedisTemplate` configures serializers for keys, values, and optionally hash keys/hash values.

Example JSON template for Redis Strings:

```java
package com.example.migration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ProfileRedisConfig {

    @Bean("profileV2Template")
    public RedisTemplate<String, ProfileV2> profileV2Template(
            RedisConnectionFactory factory) {

        RedisTemplate<String, ProfileV2> template =
                new RedisTemplate<>();

        template.setConnectionFactory(factory);
        template.setKeySerializer(
                new StringRedisSerializer()
        );
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(
                        ProfileV2.class
                )
        );

        template.afterPropertiesSet();
        return template;
    }
}
```

Here:

- Keys are stored as UTF-8 Strings.
- Values are JSON-serialized `ProfileV2` objects.
- Nothing automatically migrates data written by legacy templates.
- Switching later to Hashes requires changing both data access APIs and hash serializers.

Spring Data Redis provides several serializers whose constructors vary across versions; match your application's Spring Data Redis and Jackson versions.

### 7.2. Why native Java serialization requires caution

Java serialization embeds JVM class metadata and serialization rules. Upgrade issues include:

- Package/class renames break or complicate deserialization.
- Class field edits can break compatibility.
- Payloads are opaque in `redis-cli`.
- Never deserialize untrusted JDK bytes; native Java deserialization carries a significant security attack surface.

A safe migration can retain a **legacy JDK reader** strictly for reading internal system data, lock down access, and retire the legacy path promptly after cutover. JSON with explicit versioning evolves far more cleanly, while still requiring schema validation and security controls.

### 7.3. Changing hash serializers also changes the format

If legacy data used a Hash:

```redis
HSET profile:42 name "Lan" points "20"
```

but Java used a JDK serializer for **hash field names**, another app using `StringRedisSerializer` will fail to locate field `name` even though the Redis key exists.

Inventory all four:

```text
keySerializer
valueSerializer
hashKeySerializer
hashValueSerializer
```

Do not inspect only String value serializers.

## 8. Example: migrating from JDK serialization to JSON

Suppose the legacy app used:

```text
Key:        profile:v1:42
Redis type: String
Key bytes:  UTF-8
Value:      JDK-serialized LegacyProfile
```

The new app wants:

```text
Key:        profile:v2:42
Redis type: String
Key bytes:  UTF-8
Value:      JSON ProfileV2
```

### 8.1. Legacy and new models

```java
package com.example.migration;

import java.io.Serializable;

public record LegacyProfile(
        String displayName,
        int points
) implements Serializable {
    private static final long serialVersionUID = 1L;
}
```

New model:

```java
package com.example.migration;

public record ProfileV2(
        long id,
        String displayName,
        int loyaltyPoints,
        int schemaVersion
) {
}
```

This is an illustrative example. For real JDK-serialized data, preserve exact compatibility with the original class and `serialVersionUID` used when writing; merely creating a similarly named class does not guarantee existing bytes deserialize.

### 8.2. Two templates with different serializers

```java
package com.example.migration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class LegacyProfileTemplateConfig {

    @Bean("legacyProfileTemplate")
    public RedisTemplate<String, LegacyProfile> legacyProfileTemplate(
            RedisConnectionFactory factory) {

        RedisTemplate<String, LegacyProfile> template =
                new RedisTemplate<>();

        template.setConnectionFactory(factory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new JdkSerializationRedisSerializer()
        );

        template.afterPropertiesSet();
        return template;
    }
}
```

The new reader uses `profileV2Template` with `Jackson2JsonRedisSerializer<ProfileV2>` defined earlier.

**Assumed condition:** the legacy key serializer was UTF-8 String. If legacy keys used a JDK key serializer, configure the legacy reader with that exact same key serializer; you cannot silently swap key serializers and expect to find legacy keys.

### 8.3. Lazy migration of a single key

The service below:

1. Reads the v2 key first.
2. If v2 does not exist, reads v1 using the legacy serializer.
3. Converts the old model to the new model.
4. Preserves remaining TTL at migration time instead of resetting it.
5. Inserts v2 **only if absent**, avoiding overwriting a newer v2 key created concurrently.

```java
package com.example.migration;

import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.TimeUnit;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProfileLazyMigrationService {

    private final RedisTemplate<String, LegacyProfile> oldTemplate;
    private final RedisTemplate<String, ProfileV2> newTemplate;

    public ProfileLazyMigrationService(
            @Qualifier("legacyProfileTemplate")
            RedisTemplate<String, LegacyProfile> oldTemplate,
            @Qualifier("profileV2Template")
            RedisTemplate<String, ProfileV2> newTemplate) {

        this.oldTemplate = oldTemplate;
        this.newTemplate = newTemplate;
    }

    public Optional<ProfileV2> find(long id) {

        String oldKey = "profile:v1:" + id;
        String newKey = "profile:v2:" + id;

        // 1. Read new first.
        ProfileV2 current = newTemplate.opsForValue().get(newKey);
        if (current != null) {
            return Optional.of(current);
        }

        // 2. Fall back to the legacy serializer.
        LegacyProfile legacy = oldTemplate.opsForValue().get(oldKey);
        if (legacy == null) {
            return Optional.empty();
        }

        // 3. Check the source key's remaining TTL.
        Long ttlMillis = oldTemplate.getExpire(
                oldKey,
                TimeUnit.MILLISECONDS
        );

        // The key might have disappeared between GET and PTTL.
        if (ttlMillis == null || ttlMillis == -2 || ttlMillis == 0) {
            return Optional.empty();
        }

        ProfileV2 converted = new ProfileV2(
                id,
                legacy.displayName(),
                legacy.points(),
                2
        );

        Boolean inserted;

        if (ttlMillis == -1) {
            // Explicit temporary policy for legacy values with no TTL.
            // In a real system choose a documented retention policy.
            inserted = newTemplate.opsForValue().setIfAbsent(
                    newKey,
                    converted,
                    Duration.ofMinutes(5)
            );
        } else {
            inserted = newTemplate.opsForValue().setIfAbsent(
                    newKey,
                    converted,
                    Duration.ofMillis(ttlMillis)
            );
        }

        // If another request populated the new key first, prefer it.
        ProfileV2 latest = newTemplate.opsForValue().get(newKey);
        if (latest != null) {
            return Optional.of(latest);
        }

        // The newly inserted key could already have expired.
        // Do not treat this best-effort migration as strong consistency.
        return Optional.empty();
    }
}
```

Notes:

- `getExpire` in milliseconds can return `-1` when a key exists with no TTL and `-2` when the key does not exist.
- When a key has no TTL, applying a **new 5-minute rule** is an explicit policy choice, **not preserving infinite retention**.
- `setIfAbsent` prevents overwriting an **already existing** new key, yet does not solve every race with writers mutating both v1 and v2.
- If a v2 key exists yet fails to decode, reads should report errors, quarantine, or handle per policy—never treat deserialization errors as cache misses and overwrite with legacy data.
- Returning `Optional.empty()` when a key vanishes mid-flight lets the app fall back to an authoritative source or bounded retry; never interpret that automatically as "customer does not exist" if Redis is only a cache.
- This snippet is **best-effort lazy migration**, not strong consistency under concurrent writes.

### 8.4. Why not call SET directly?

Risk scenario:

```text
T0: Migration reads v1 profile: points=10.
T1: New app updates v2 profile: points=20.
T2: Migration calls SET profile:v2:42 points=10.
```

An unconditional `SET` **overwrites newer data**.

`SET ... NX` or `setIfAbsent` blocks overwrites when target exists, yet still must contend with:

- A writer deleting target for invalidation, followed by migration repopulating stale data.
- Legacy writers continuing to mutate the v1 namespace.
- Target creation and new updates interleaving out of order.
- Migration reading from a source modified after `GET`.
- Target being created and then updated/deleted before re-reading.

For authoritative data, combine revisions/versions, transactions at the authoritative source, or a cutover barrier preventing legacy writes.

## 9. Migrating from Redis String to Hash

Suppose v1:

```redis
SET cart:v1:42 "{\"userId\":42,\"status\":\"OPEN\",\"items\":3}"
```

V2:

```redis
HSET cart:v2:42 userId "42" status "OPEN" items "3"
```

Because `cart:v1:42` and `cart:v2:42` are distinct keys, both data types can coexist.

### 9.1. Reading the JSON String in Spring

```java
String json = stringRedisTemplate
        .opsForValue()
        .get("cart:v1:42");
```

Decode with Jackson (example):

```java
CartV1 cart = objectMapper.readValue(json, CartV1.class);
```

Illustrative model:

```java
public record CartV1(
        long userId,
        String status,
        int items
) {
}
```

### 9.2. Writing to a Hash

```java
Map<String, String> fields = Map.of(
        "userId", Long.toString(cart.userId()),
        "status", cart.status(),
        "items", Integer.toString(cart.items())
);

stringRedisTemplate.opsForHash()
        .putAll("cart:v2:42", fields);
```

Reading after conversion:

```java
Map<Object, Object> migrated =
        stringRedisTemplate.opsForHash()
                .entries("cart:v2:42");
```

If Hash field types evolve over time, parsing code must handle validation: `items` parses as a valid integer, `status` belongs to the expected enum, and missing fields either default or fail cleanly.

### 9.3. HSET does not preserve TTL the way readers often assume

Standard Redis TTLs attach to the **key**, not individual Hash fields. For a **newly created** Hash target key, `HSET`/`putAll` **does not automatically inherit the TTL of the source String**.

Set it explicitly:

```java
stringRedisTemplate.expire(
        "cart:v2:42",
        Duration.ofMinutes(10)
);
```

Still, `putAll` followed by `expire` are **two commands**. If the process crashes between them, the v2 key survives without a TTL.

Stricter options:

- Use `MULTI/EXEC` or a Lua script to set fields and TTL atomically **when all participating keys map to the same slot** and those commands are permitted.
- Use versioned data structures to avoid overwriting concurrent changes.
- Run reconciliation scans flagging v2 keys unexpectedly missing a TTL.
- If Redis is purely a cache, accept clearing malformed keys on read.

### 9.4. When is a Hash better than a JSON String?

Redis Hashes enable per-field commands:

```redis
HGET cart:v2:42 status
HSET cart:v2:42 status CHECKED_OUT
```

Yet they carry trade-offs:

- Requires managing both field-name and field-value serializers.
- Nested objects still require a serialization strategy.
- Reading the whole object can still transfer significant bytes.
- Individual field updates must respect schema and revision rules.
- Moving from `String` to `Hash` does not automatically improve memory or speed in every workload.

Base the choice on actual read/write patterns, not merely because Hashes offer more commands.

## 10. Preserving TTL during migration

### 10.1. Special return values of PTTL

```redis
PTTL profile:v1:42
```

| Result | Meaning |
|---|---|
| Positive number | Remaining milliseconds |
| `-1` | Key exists with no TTL |
| `-2` | Key does not exist |
| `0` | Can appear right at the moment of expiration |

During migration, never blindly pass every value into `Duration.ofMillis(ttl)`; `-1` and `-2` mean completely different things.

### 10.2. The TTL-reset bug when copying

Example:

```text
Old key:
  17 seconds remaining TTL

Migration:
  SET newKey value EX 3600
```

Data meant to expire in 17 seconds suddenly lives **an extra hour**. For sessions, permissions, tokens, or business locks, that can be a serious bug.

For expiring entries, preserve the **expected expiration timestamp** or apply an explicitly approved policy—never reset TTLs accidentally.

### 10.3. PTTL followed by SET still races

Sequence:

```text
T0: PTTL oldKey => 17,000 ms
T1: App processing + network delay of 3 seconds
T2: SET newKey PX 17,000
```

The new key expires roughly 3 seconds later than the source.

Moreover, the source can be deleted or updated between `GET`, `PTTL`, and `SET`:

```text
GET old value
  |
PTTL old
  |
[old is DELeted]
  |
SET new value
```

**Never treat `GET` + `PTTL` + `SET` as an atomic transaction.**

### 10.4. Using absolute expiration timestamps when appropriate

Redis provides:

```redis
PEXPIRETIME profile:v1:42
```

On supporting Redis versions, this returns the expiration time as a Unix epoch timestamp in milliseconds (or special codes for persistent/missing keys). Copying the absolute deadline avoids extending TTLs due to processing delays.

Representation:

```text
Source expireAt = T
Target expireAt = T
```

Even so, **reading the deadline and writing the target still races** against source updates/deletions without synchronization. Check current wall-clock time, revisions, and how mid-flight source expiration is handled.

### 10.5. COPY, RENAME, and TTL

Redis commands like `COPY` or `RENAME` can help when moving or duplicating **the exact existing data type and raw bytes**.

Example:

```redis
RENAME profile:v1:42 profile:v2:42
```

`RENAME` renames the key and preserves its value and TTL, yet **overwrites the target key if it already exists**—risking data loss if the target held newer state.

To prevent overwrites:

```redis
RENAMENX profile:v1:42 profile:v2:42
```

`RENAMENX` renames only if the target does not exist. However, it **moves** the key, removing the source key needed for rolling deployments or rollbacks.

Copying without deleting the source:

```redis
COPY profile:v1:42 profile:v2:42
```

`COPY` changes neither serializer nor Redis type. It duplicates raw data; you still must manage TTL policies, existing targets, and versioning.

In Redis Cluster, multi-key commands like `RENAME`/`COPY` typically require both keys to be in the same hash slot. Never assume they freely move keys across arbitrary slots.

**Serializer changes or String ↔ Hash conversions cannot be solved by `RENAME`/`COPY`.** They apply only when existing bytes remain valid as-is.

## 11. Scanning many keys: use SCAN, not KEYS, in production

Migrating hundreds of thousands of keys requires controlled keyspace traversal.

### 11.1. KEYS causes severe load spikes

Example:

```redis
KEYS profile:v1:*
```

`KEYS` scans the entire keyspace in a way that can stall Redis. Avoid using it on large production datasets just to enumerate keys for migration.

### 11.2. SCAN returns batches incrementally

Example:

```redis
SCAN 0 MATCH profile:v1:* COUNT 500
```

Redis returns a **new cursor** and a batch of keys. Keep passing the cursor until it returns to `0`.

Conceptual flow:

```text
SCAN cursor=0
    |
    +--> cursor=1048, 120 keys
    |
SCAN cursor=1048
    |
    +--> cursor=200, 80 keys
    |
SCAN cursor=200
    |
    +--> cursor=0, 110 keys
```

`COUNT 500` is only a **work hint**, not a guarantee that every call returns exactly 500 keys.

Key characteristics of `SCAN`:

- Can return duplicate keys across iterations.
- Can return an empty list before cursor reaches `0`.
- Is not an atomic keyspace snapshot.
- Keys created or deleted during scanning mean results do not match one single point in time.
- Migration handlers must be **idempotent** to handle duplicate keys safely.
- Never fire unbounded concurrent requests for every scanned batch.

### 11.3. Spring Data Redis scan

With String key serialization:

```java
package com.example.migration;

import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public class ProfileKeyScanner {

    private final StringRedisTemplate redis;

    public ProfileKeyScanner(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void scanOldKeys() {

        ScanOptions options = ScanOptions.scanOptions()
                .match("profile:v1:*")
                .count(500)
                .build();

        try (Cursor<String> cursor = redis.scan(options)) {

            while (cursor.hasNext()) {
                String oldKey = cursor.next();

                // Invoke rate-limited idempotent migration.
                // Do not DELETE the source here.
                System.out.println(oldKey);
            }
        }
    }
}
```

This illustrates traversal only. Production jobs must not dump sensitive key names to stdout; record progress metrics and sampled logs instead.

**Redis Cluster:** nodes own different keyspace partitions. Use verified cluster-aware scanning in your client/library or scan each primary separately—never assume one `SCAN` against one endpoint covers all slots. If topology shifts mid-run, plan rescan passes.

### 11.4. Cursors, checkpoints, and reruns

A backfill job should track progress:

```text
migrationRunId
namespaceVersion
scanTarget / node
cursor / partition range
processedCount
convertedCount
skippedCount
failedCount
lastCheckpointTime
```

Because `SCAN` is not a snapshot and cursors depend on scan state, cursor checkpoints do not replace idempotency. After crashes or topology shifts, a safe pattern is rerunning scans per policy and **skipping keys whose target already holds a valid newer state**.

Do not delete sources right after a single scan pass. Independently reconcile that new data is readable and old writers can no longer produce un-migrated records.

## 12. Migrating under concurrent writes

This is the hardest part for non-reproducible data.

### 12.1. Race: backfill overwrites newer data

```text
T0: Backfill reads v1, revision=10.
T1: API updates v2, revision=11.
T2: Backfill writes v2 from revision=10.
```

Outcome: v2 reverts to an older revision if backfill uses unconditional `SET`.

The fix is not "run SCAN faster", but conditional update logic:

- Create target only when absent (`SET NX`) where appropriate.
- Or update target **only when source revision is newer than target revision**.
- Revision comparison and write must be **atomic**.
- Revisions must be issued monotonically by an authoritative source.
- If deletes/updates occur, tombstones or delete markers must also participate in version comparison.

### 12.2. Race: legacy writer makes v1 newer than v2

```text
T0: Backfill copies v1(revision=10) to v2.
T1: Legacy instance updates v1(revision=11).
T2: New app reads only v2(revision=10).
```

V2 is now stale. `SET NX` fails whenever **target already exists while legacy data keeps changing**.

Mitigations:

1. During transition, all writers update the canonical path and emit changes per contract.
2. If dual-writing, implement retries/reconciliation when one branch fails.
3. Retire all remaining legacy writers before final cutover.
4. Track revision/sequence markers and run a catch-up pass for writes occurring during backfill.
5. After cutover, block or remove v1 write paths so no "ghost writers" linger.

### 12.3. Race: deleted data gets resurrected

```text
T0: Backfill reads profile v1:42.
T1: User deletes profile in canonical source.
T2: System deletes profile v2:42.
T3: Backfill writes profile v2:42 from stale read.
```

Deleted data **resurrects**.

Solutions:

- Use versioned delete markers / tombstones.
- Or re-verify against the authoritative source inside a transaction/sync check.
- Or enforce a migration write freeze.
- Never rely on plain `setIfAbsent` if deletions carry business meaning and old keys still exist.

### 12.4. Choosing by required consistency

| Consistency requirement | Approach |
|---|---|
| Rebuildable cache | New namespace + TTL, lazy warm, no key-by-key copy needed |
| Valuable cache tolerating slight staleness | Dual-read + throttled backfill + TTL + reconciliation |
| Sole Redis store allowing maintenance | Pause writers → snapshot/convert → reconcile → cutover |
| Sole Redis store requiring zero downtime | Revisions/CDC or event log + backfill + catch-up + write barrier |
| Very strict consistency needs | Use an authoritative transactional/coordinated store; not just `SCAN` + `SET` |

## 13. Controlling rollout with feature flags

Never hardcode every migration phase into an unconfigurable code deploy.

Useful control flags:

```text
profile.readPolicy = OLD_ONLY | NEW_THEN_OLD | NEW_ONLY
profile.writePolicy = OLD_ONLY | DUAL | NEW_ONLY
profile.backfillEnabled = true/false
profile.shadowCompareEnabled = true/false
profile.deleteLegacyEnabled = false
```

Compatibility read flow example:

```text
          Read API
             |
        readPolicy?
             |
    +--------+----------+
    |        |          |
OLD_ONLY NEW_THEN_OLD NEW_ONLY
    |        |          |
    v        v          v
    v1      v2          v2
            |             |
           miss           |
            |             |
            v             v
            v1         return/error
```

**Never enable `NEW_ONLY` while any legacy writer writes exclusively to v1**, or those updates become invisible to new readers.

Feature flags require disciplined change plans: who toggles them, in what order, which metrics must pass, and when rollbacks apply.

### 13.1. Repeatable transition sequence

A typical sequence for durable data:

| Phase | Readers | Writers | Backfill | Clean v1 |
|---|---|---|---|---|
| Prepare | v1 | v1 | No | No |
| Compatibility rollout | Prefer v2, fallback v1 | Write via designed compatibility path | Off / small test | No |
| Migrate data | Prefer v2, fallback v1 | Revision-checked | Yes, rate-limited | No |
| Catch-up | Prefer v2 | Switch canonical writes to v2 | Catch-up pass | No |
| Cutover | v2, fallback per plan | v2 | Reconcile | No |
| Stabilize | v2 | v2 | Optional repair scan | No |
| Contract | v2 | v2 | Stop | Delete after retention |

This table is a **process framework**, not a rigid timeline. For rebuildable caches, many steps simplify dramatically.

## 14. Choosing safe cutover and rollback plans

### 14.1. Cutover is more than flipping one flag

Before turning off v1 reads, verify:

- Are any old application instances still running?
- Do any background jobs or consumers still write v1?
- How many unconverted keys remain?
- Do new keys carry proper types, serializers, and TTLs?
- Were failed conversions investigated and resolved?
- Is there a policy for keys never read during transition?
- If cutover fails, what exact state can we roll back to?

A classic operational mistake is deploying v2 code and **immediately deleting v1 keys**. When bugs force rolling binaries back to v1, old code finds no data left to read.

### 14.2. Rollback once new code has written new data

Suppose v2 writes only Redis Hashes, while v1 code expects JDK-serialized Strings. Rolling back to v1 while v1 stopped receiving recent writes reverts user state backward.

Rollback tiers therefore include:

- **Code-only rollback:** viable only if legacy code still reads current updated data.
- **Dual-write compatible rollback:** verify both v1 and v2 stayed consistently updated with zero lost writes.
- **Reverse-migration rollback:** transform v2 back into v1 with reconciliation and versioning.
- **No direct rollback:** apply a forward-fix or switch to read-only mode during recovery.

**Never promise rollback safety merely because v1 keys were not deleted.** Once v1 stops receiving updates, it goes stale immediately after cutover.

### 14.3. Cleaning up legacy data after retention

Delete only when:

1. All readers and writers have moved.
2. The rollback window has closed.
3. Reconciliation metrics pass.
4. Backups and restore paths align.
5. No consumer groups or scripts still depend on v1.
6. TTL and retention policies permit deletion.

For cached keys, simply letting TTL expire them is often cleanest. When deleting large numbers of keys actively, consider `UNLINK` instead of `DEL` where appropriate, since `UNLINK` reclaims memory asynchronously.

Delete **strictly within the target namespace**; never run broad wildcards that risk wiping active version keys.

## 15. Spring Data Redis Repositories: auxiliary structures to account for

With `@RedisHash` in Spring Data Redis Repositories, changing a keyspace name or object mapping affects **multiple Redis keys**, not just one String or Hash.

Example model:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash("profiles")
public class ProfileEntity {

    @Id
    private String id;

    private String displayName;
}
```

Repositories maintain keyspace structures and metadata to support entity lookups and queries.

Depending on annotations and configuration, Redis may store:

- The entity Hash key.
- A Set tracking all entity IDs in the keyspace.
- Secondary index Sets for indexed fields.
- Auxiliary TTL keys, keyspace notification markers, or phantom copies for expiry events.
- Repository relationship metadata.

If you change:

```java
@RedisHash("profiles")
```

to:

```java
@RedisHash("profilesV2")
```

never assume renaming one set of Hash keys makes the new Repository work properly. **Indexes, ID sets, and auxiliary metadata** may need rebuilding or dedicated migration.

### 15.1. Safely rebuilding indexes

One strategy:

1. Keep legacy readers running.
2. Define the new mapping and namespace.
3. Read old entities via the legacy repository/template.
4. Save via the new repository so Spring constructs all matching auxiliary structures.
5. Reconcile lookups by ID and by secondary indexes.
6. Cut over only after critical queries validate cleanly.

Never manually `RENAME` primary Hashes and expect Repository secondary indexes to update automatically.

### 15.2. TTLs and shadow copies

Repository TTL features can create auxiliary keys to support expiration events, depending on configuration. When switching namespaces, verify:

- Whether primary keys have TTLs.
- Whether shadow copies or temporary keys exist.
- Whether auxiliary keys follow different retention from primary keys.
- Whether listeners/notifications still watch the old namespace.

Migrating auxiliary keys accidentally as primary entities creates corrupt records and broken mappings.

## 16. Redis Streams cannot be copied like plain Strings

Migrating Redis Streams requires respecting Stream-specific semantics.

A Stream includes:

- Entry IDs and field/value payloads.
- Consumer groups.
- Pending Entries Lists (PEL).
- Consumer ownership, delivery counts, and processing progress.
- Retention/trimming policies.

Simply reading entries with `XRANGE` and writing via `XADD` into a new Stream **fails to preserve consumer group and pending state**, and can mint new entry IDs or alter ordering/semantics.

Example:

```text
orders:stream:v1
  entries + group billing + group analytics + pending

orders:stream:v2
  entries copied over
  but lacks matching group/PEL state
```

Stream migrations must explicitly decide:

- At what point do producers/consumers stop?
- Must entry IDs remain identical or can new ones be generated?
- From which offset do new consumer groups start?
- Will old pending entries drain before cutover or be claimed/replayed?
- Does an `XACK` on the old Stream mean anything on the new Stream?
- Are consumers idempotent if events redeliver?

Never apply a naive `SCAN key -> GET -> SET` loop to Streams or stateful processing structures.

## 17. Counters and distributed locks need dedicated rules

### 17.1. Counters

A Redis counter:

```redis
INCR stats:orders:v1
```

If migration reads `100` and writes `100` to v2 while an old writer runs `INCR` to `101`, v2 silently falls behind.

For authoritative counters:

- Switch writers at a crisp cutover barrier.
- Or track delta changes occurring during the copy.
- Or use an atomic transaction/protocol to transfer the baseline.
- Never copy solely via separate `GET` and `SET` calls.

### 17.2. Distributed locks and fencing sequences

A lease key with TTL:

```text
lock:job:42
```

must never be copied into a new namespace like a normal cache entry.

If both old and new lock namespaces coexist, **two workers can simultaneously believe they hold the exclusive lock**:

```text
Worker v1 holds lock:v1:job42
Worker v2 holds lock:v2:job42
```

For locking:

- Design an explicit handoff protocol between worker generations.
- Never maintain two independent lock namespaces guarding the same resource.
- Fencing tokens/sequences must remain strictly monotonic and non-reused.
- Never reset sequences simply because key prefixes changed.
- Enforce token validation at the protected target resource.

Exclude lock keys from pattern-based backfill scripts unless governed by dedicated coordination logic.

## 18. Redis Cluster, replicas, and failover during migration

### 18.1. Scanning and writing must respect topology

In Redis Cluster, every key maps to a hash slot. During migration:

- `SCAN` must cover every active primary.
- `GET`/`HGETALL` must route to the slot owner.
- Multi-key commands or Lua scripts must obey same-slot rules.
- Keys with new prefixes can land in different slots from old keys.
- Resharding shifts slot ownership dynamically mid-run.

Scanning only one primary and reporting "100% migrated" silently skips keys on other primaries.

### 18.2. Do not backfill solely from stale replicas without accounting for lag

Redis replication is usually asynchronous. Backfilling from a replica while writers update the primary can read stale state and copy it into the new namespace.

For data intolerant of staleness, read from the authoritative/canonical source or enforce revision checks on conditional writes.

### 18.3. Redis persistence does not replace reconciliation

RDB snapshots, AOF, and replication support Redis durability and recovery, yet cannot verify that:

- Every v1 key migrated to v2.
- Every payload decoded cleanly.
- New TTLs match expectations.
- Concurrent writes were preserved.
- New Repository indexes were populated.
- New Stream consumer groups hold accurate offsets.

You need both **backup/restore** and **business-level data reconciliation**.

### 18.4. Failover can roll migration progress backward

Under async replication, primary failure can drop acknowledged writes not yet replicated to the promoted replica. That risk affects both application state and migration checkpoints if checkpoints live solely inside that Redis cluster.

For critical data:

- Evaluate real persistence and failover behavior.
- Never trust an in-memory "N keys migrated" counter as final proof.
- Keep migration jobs safely idempotent and re-runnable.
- Reconcile source and target after topology stabilizes.
- Persist checkpoints in a durable system with stronger guarantees where appropriate.

## 19. Reconciling data before cutover

### 19.1. Counting keys is not enough

Even if v1 has 100,000 keys and v2 has 100,000 keys, data may still be broken:

- Duplicate or colliding logical IDs.
- Invalid payload schemas in v2.
- Old revisions overwriting newer revisions.
- Accidentally reset TTLs.
- Missing or wrongly typed Hash fields.
- Resurrected deleted records.
- Unbuilt Repository auxiliary keys.

### 19.2. Define a canonical comparison mapping

Instead of comparing raw JDK vs. JSON bytes:

```text
old bytes -> LegacyProfile -> canonical view
new bytes -> ProfileV2     -> canonical view
```

Compare shared business fields:

```text
logicalId
displayName
loyaltyPoints
revision
expiresAt (for expiring records)
```

Example:

```text
Old:  LegacyProfile("Lan", 20)
New:  ProfileV2(42, "Lan", 20, 2)

=> Semantically equivalent business data
```

You cannot compare raw JDK-serialized bytes against JSON bytes and flag differences as bugs—they differ by design.

### 19.3. Metrics to capture

| Metric | Explanation |
|---|---|
| `keys_scanned` | Keys returned by `SCAN` iterations |
| `unique_ids_seen` | Distinct logical IDs observed via suitable tracking |
| `converted_success` | Successful conversions |
| `already_current` | Target already holds matching version |
| `skipped_expired` | Source expired prior to conversion |
| `decode_errors` | Legacy serializer failed to decode |
| `schema_errors` | Data violates new schema constraints |
| `write_conflicts` | Target newer or CAS condition failed |
| `ttl_mismatches` | TTL/`expireAt` outside allowed tolerance |
| `missing_in_target` | Valid source lacking target entry |
| `revision_mismatches` | Target lags behind source revision |
| `scan_rate` | Keys converted per second |
| `redis_latency_p99` | Redis p99 latency during migration |

Good telemetry separates **legitimate TTL expirations** from **keys lost to migration bugs**.

### 19.4. Shadow reads

During transition, the app can:

```text
Production reader -> reads v1 per live contract
                  -> reads v2 in background for verification
                  -> compares canonical views
                  -> returns official result from active path
```

Shadow reads catch drift before users ever see new-path results. Still:

- It doubles part of the read load on Redis.
- Never log full user payloads.
- Sample traffic at a controlled percentage.
- Concurrent writes between the two reads can cause transient diffs; check revisions.
- Do not flag errors when a key legitimately expires between the two reads.

## 20. Throttling backfill to protect production Redis

Migrations can run for hours or days. Issuing tens of thousands of `GET`s and `SET`s per second competes directly with production traffic.

A backfill worker needs:

- **Batch sizes** bounded by key count and payload bytes.
- **Concurrency limits** on in-flight Redis commands.
- **Rate limits** capping commands per second.
- **Timeouts** and retries with backoff and jitter.
- **Pause/resume switches** if Redis overloads.
- **Checkpoints** and progress metrics.
- **Dead-lettering / error reports** for un-decodable payloads.
- **Idempotent conditional writes** that never overwrite newer revisions.

```text
SCAN keys
    |
    v
Bounded queue
    |
    v
Rate limiter + concurrency limit
    |
    v
Read old -> convert -> conditional write new
    |
    +---- Success ------> metrics
    |
    +---- Conflict -----> metrics / skip or reconcile
    |
    +---- Decode error -> quarantine + investigate
```

Never load the entire keyspace into a JVM list before migrating. Process in bounded pages/batches.

In reactive Spring Data Redis, `flatMap(..., concurrency)` caps concurrency within a single pipeline, not across the whole app or global QPS. Budget total rate across all parallel workers.

## 21. Redis commands that assist migration

| Command | When to use | Limitations to remember |
|---|---|---|
| `SCAN` | Batch key enumeration | Not a snapshot, may duplicate, must cover all Cluster nodes |
| `TYPE` | Confirm Redis data type | Does not decode application objects |
| `PTTL` | Relative remaining TTL | Races with elapsed wall time |
| `PEXPIRETIME` | Absolute deadline where supported | Still races against mutations/deletes |
| `RENAME` | Rename key keeping raw data | Overwrites existing target, deletes old key |
| `RENAMENX` | Rename only if target absent | Changes neither serializer nor type |
| `COPY` | Duplicate key keeping type | Does not transform schema |
| `DUMP` / `RESTORE` | Transfer Redis-internal encoding | Does not convert JDK bytes to JSON |
| `MIGRATE` | Move keys between Redis instances | Not an app schema converter; operational risks |
| `MULTI/EXEC` | Group Redis commands on node/slot | Not a cross-DB transaction; slot constraints apply |
| `EVAL` | Atomic Lua logic on node/slot | Does not natively decode Java objects |
| `UNLINK` | Async memory reclaim on key deletion | Still deletes data |
| `MEMORY USAGE` | Estimate single key memory | Does not replace total load/memory monitoring |
| `INFO` / `SLOWLOG` | Inspect server health | Does not replace app-side latency measurement |

### 21.1. DUMP/RESTORE does not convert application value serializers

Example:

```redis
DUMP profile:v1:42
```

returns data serialized in **Redis's internal encoding**, which wraps rather than alters JSON or JDK bytes inside the value.

If a source String contains JDK-serialized bytes, `DUMP` and `RESTORE` under a new name still store JDK-serialized bytes. The new JSON template still cannot decode it.

**Changing serializers** requires an application reader that understands the old schema and a writer emitting the new schema.

### 21.2. Do not misuse MIGRATE as a schema transformation

`MIGRATE` transfers keys between Redis instances; it never converts Strings into Hashes or Java binaries into JSON. It also carries auth, topology, TTL, and operational hazards on live data.

If the goal is changing object models within the same Redis, build an application-level migration job rather than infrastructure key-movement commands.

## 22. Recovery planning when migration hits errors

A real migration must expect failures at multiple stages.

### 22.1. Decode errors

When an old value fails to deserialize:

```text
Key exists
    |
    v
Legacy deserializer throws
    |
    v
Do not write target with default/blank object
    |
    v
Record ID in error list + increment metric
    |
    v
Investigate class version / payload / serializer
```

Never:

- Swallow exceptions and pretend the key is missing.
- Write an empty placeholder object into v2.
- Delete the v1 key before diagnosing the cause.
- Log raw payload bytes containing sensitive data.

### 22.2. Target already holds different data

If target exists with a different revision:

```text
source revision = 12
target revision = 14
```

Never overwrite target with older source data. Log the conflict and reconcile against the canonical source.

Conversely, if source revision exceeds target, still avoid unconditional `SET` if another writer could update target concurrently. Enforce atomic/version-checked writes.

### 22.3. Half-failed dual-writes

```text
Write v1: succeeded
Write v2: timeout / error
```

State has diverged. Apply one of:

- Write to the canonical source and drive target via outbox/changelog.
- Idempotent retries keyed by operation ID and revision.
- Pause cutover and reconcile divergent keys.
- Within same-slot constraints, wrap updates atomically using Lua or Redis transactions.

Never assume retrying a non-idempotent write after a timeout is safe; Redis may have executed it even if the response was lost.

### 22.4. Backfill crashes mid-batch

Jobs must be safely restartable:

```text
Batch 1: done
Batch 2: done
Batch 3: partial -> crash
Restart -> re-process conditionally/idempotently
```

Never rely on `SCAN` yielding each key strictly once.

### 22.5. Failover mid-migration

After failover, migration checkpoints or in-flight writes may roll back if replication lagged. Re-read live state, check canonical sources, and rerun catch-up scans as needed. Never mark migration complete solely from in-memory counters.

## 23. Common pitfalls

### Pitfall 1: Changing key prefixes in code without migrating data

Old keys persist, while new readers look solely in the new namespace and see misses.

### Pitfall 2: Changing only valueSerializer

Bytes stored by the legacy serializer do not self-convert. Decoding fails on every legacy key.

### Pitfall 3: Forgetting keySerializer or hashKeySerializer

Physical key names or Hash field names mismatch Java strings, causing new readers to miss existing data.

### Pitfall 4: Calling HGETALL on legacy Strings

Redis does not convert JSON Strings to Hashes automatically and throws `WRONGTYPE`. Use a new key and explicit transformation.

### Pitfall 5: Resetting TTLs during copy

Keys meant to expire in seconds get extended for hours or made permanent.

### Pitfall 6: Copying expired keys and resurrecting them

Source expired or was deleted mid-migration, yet the job writes target from an earlier read.

### Pitfall 7: Running KEYS on large production Redis

Stalls Redis during traversal and spikes latency for live traffic. Use throttled `SCAN` while accounting for non-snapshot semantics.

### Pitfall 8: Assuming SCAN yields each key once

`SCAN` can emit duplicates; non-idempotent workers duplicate side effects or overwrite state.

### Pitfall 9: Scanning one node and declaring Cluster done

Hash slots span multiple primaries. Cover all primaries and handle resharding/failover.

### Pitfall 10: Backfill SET overwriting newer target writes

A new writer updated v2 while backfill copied v1. Compare revisions and write conditionally.

### Pitfall 11: Leaving old writers active past cutover

A lingering instance or cron job keeps writing v1 while apps read `NEW_ONLY`, causing silent divergence.

### Pitfall 12: Deleting old keys too early

Rolling back app binaries leaves old code with nothing to read—especially dangerous for authoritative data.

### Pitfall 13: Treating two dual-write commands as atomic

One branch can fail, or keys in different slots cannot share a Redis transaction.

### Pitfall 14: Checking only total key counts

Counts can match while payloads, revisions, TTLs, and secondary indexes differ.

### Pitfall 15: Changing @RedisHash without rebuilding auxiliary metadata

New Repositories lack ID sets, secondary indexes, or TTL expiration structures.

### Pitfall 16: Copying Streams like Strings

Copying entry payloads omits consumer groups and PELs, losing processing progress.

### Pitfall 17: Resetting fencing sequences on namespace change

Tokens can repeat, breaking stale-worker protection.

### Pitfall 18: Backfilling solely from stale replicas

Migration copies outdated values into the new namespace even though the primary already holds newer writes.

### Pitfall 19: Unthrottled backfill

Backfill starves production traffic, spiking p99 latency and triggering timeouts/retry storms.

### Pitfall 20: Assuming backups prove migration correctness

Backups preserve a point in time; they do not verify schema mapping, TTL fidelity, or cutover accuracy.

## 24. Hands-on exercises

### Exercise A: Namespace change without serializer change

1. Create a demo key:

```redis
SET demo:profile:v1:42 "{\"name\":\"Lan\"}" EX 120
```

2. Inspect:

```redis
TYPE demo:profile:v1:42
PTTL demo:profile:v1:42
```

3. Use `COPY` to v2:

```redis
COPY demo:profile:v1:42 demo:profile:v2:42
```

4. Compare `GET`, `TYPE`, `PTTL` and note: **copying identical bytes is not schema migration**.

5. Test behavior when the target key already exists. Never pass `REPLACE` without an explicit overwrite policy.

### Exercise B: Converting JSON String to Hash

1. Create String:

```redis
SET demo:cart:v1:42 "{\"userId\":42,\"status\":\"OPEN\",\"items\":3}" EX 120
```

2. Read legacy JSON using Java `ObjectMapper`.
3. Write a new Hash under `demo:cart:v2:42`.
4. Explicitly preserve TTL.
5. Verify with `TYPE`, `HGETALL`, and `PTTL`.
6. Try `HGETALL` on the v1 String to observe the type error.

### Exercise C: Observing backfill races

1. Backfill reads `revision=10` from v1.
2. Write a newer state to v2 with `revision=11`.
3. Attempt an unconditional `SET` with revision 10 to observe the lost update.
4. Replace with conditional/version-checked writes to prevent overwrites.

Run on demo namespaces, never on production data.

### Exercise D: Simulating near-expiry TTLs

1. Create a short-TTL key.
2. Read `PTTL`, wait several seconds, then create the target with the old TTL.
3. Observe the target outliving the original deadline.
4. Discuss using `PEXPIRETIME` and verifying source liveness during transfer.

### Exercise E: Restartable backfill

1. Create a few hundred test keys in v1.
2. Iterate using batched `SCAN`.
3. Interrupt the job mid-run.
4. Restart and ensure no duplicates or newer-data overwrites occur.
5. Report `converted`, `already_exists`, `expired`, and `failed` counts.

### Exercise F: Rolling deployment

Simulate two service versions:

```text
App v1: understands v1 keys only
App v2: reads v2 then falls back to v1
```

Run both concurrently. Write via v1 after v2 backfilled, and explain why writer cutover or catch-up passes must precede enabling `NEW_ONLY`.

### Exercise G: Rollback planning

Suppose 10 minutes after cutover, the new JSON serializer fails on a specific enum value. Describe:

- Can we temporarily fall back to reading v1?
- Does v1 still hold all latest writes?
- Is a reverse migration required?
- Can writers be paused briefly to protect data?
- What criteria allow resuming v2 once fixed?

## 25. Self-check questions

**1. Why can changing `profile:42` to `profile:v2:42` make an app see empty data?**

Because the physical key name changed. Redis does not migrate legacy keys into a new namespace automatically.

**2. Does changing `JdkSerializationRedisSerializer` to a JSON serializer convert old data automatically?**

No. Existing bytes stay in the old format; you need a legacy reader and a converter/new writer.

**3. Is `RENAME` enough when migrating a Redis JSON String to a Hash?**

No. `RENAME` only changes the key name while keeping the Redis type unchanged; it does not split JSON into Hash fields.

**4. Why avoid setting a fresh 1-hour TTL when the source key has 10 seconds left?**

It extends data lifetime beyond policy, potentially keeping expired sessions, permissions, or metadata alive.

**5. Does `SCAN` guarantee a consistent snapshot?**

No. `SCAN` can return duplicates and reflects additions/deletions occurring during traversal.

**6. Does `SET NX` solve every race between backfill and writers?**

No. It prevents overwriting an existing target, yet fails when legacy writers mutate v1 afterward, when records are deleted and resurrected, or when targets are deleted.

**7. When can backfill be skipped entirely?**

When Redis is strictly a rebuildable cache backed by an authoritative source and origin load during warm-up is safely bounded.

**8. When must Spring Data Redis Repository indexes be accounted for?**

Whenever changing keyspaces, serializers, or structures for Repository entities, especially with secondary indexes or TTL metadata.

**9. Why does rolling back code not guarantee rolling back data?**

Old versions may not parse new schemas, and v1 keys may have stopped receiving recent writes.

**10. If Redis Cluster has three primaries, is scanning one primary enough?**

No. Scan all primaries covering relevant slots and handle topology changes.

**11. Why avoid copying a Stream with active consumer groups naively?**

Entry payloads alone omit delivery progress, Pending Entries Lists, and consumer ownership.

**12. Can `DUMP`/`RESTORE` convert Java-serialized objects into JSON?**

No. `DUMP`/`RESTORE` preserves Redis internal encoding without understanding Java schemas or transforming application value serializers.

**13. To certify a migration complete, is matching key counts enough?**

No. Reconcile logical IDs, field values, revisions, TTLs, indexes, writer coverage, and conversion errors.

**14. If one writer still emits the old schema, what happens after cutover?**

v1 keeps changing while v2 stays frozen, causing new readers to see stale data or miss updates.

**15. Why is changing a distributed lock namespace riskier than changing a cache namespace?**

Two lock namespaces allow two workers to acquire exclusive locks on the same resource simultaneously. Locks and fencing sequences need dedicated handoff protocols rather than key copying.

## 26. Key takeaways

- **Redis migrations must preserve both data and semantics.** Namespace, serializer, and Redis type changes are three distinct dimensions.
- **Classify Redis as a cache vs. authoritative store.** Caches can warm anew; durable business data requires careful transformation and reconciliation.
- **Manage key/value/hash serializers explicitly** and retain legacy readers during compatibility phases. Never deserialize untrusted native Java payloads.
- **Use versioned namespaces** so two schemas coexist during rolling deployments, avoiding `WRONGTYPE` and target overwrites.
- **Preserve TTLs and expiration timestamps.** `GET` + `PTTL` + `SET` is non-atomic; avoid accidentally extending key lifetimes.
- **Traverse with throttled `SCAN`**, handling duplicates and live mutations; in Cluster, cover all primaries.
- **Make backfill idempotent and revision-checked.** `SET NX` helps partially, yet does not solve concurrent writes or deletes alone.
- **Follow expand → migrate → contract**, with controlled cutover, shadow reads, metrics, reconciliation, and real rollback plans.
- **Clean up legacy keys only after the rollback window closes**, all writers have migrated, and retention allows.
- **Streams, Repository indexes, counters, and distributed locks need dedicated migration workflows**, never plain String-cache treatment.

### References

- [Spring Data Redis — Serializers](https://docs.spring.io/spring-data/redis/reference/redis/template.html#redis:serializer).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html).
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html).
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/).
- [Redis — TYPE](https://redis.io/docs/latest/commands/type/).
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/).
- [Redis — PEXPIRETIME](https://redis.io/docs/latest/commands/pexpiretime/).
- [Redis — COPY](https://redis.io/docs/latest/commands/copy/).
- [Redis — RENAME](https://redis.io/docs/latest/commands/rename/).
- [Redis — XINFO](https://redis.io/docs/latest/commands/xinfo/).
- [Redis — UNLINK](https://redis.io/docs/latest/commands/unlink/).
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/).
