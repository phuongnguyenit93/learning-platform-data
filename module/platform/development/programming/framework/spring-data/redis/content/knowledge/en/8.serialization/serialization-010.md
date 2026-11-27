# JSON Schema Changes and Legacy Data Migration Planning in Spring Data Redis

In a Spring Data Redis application, a Java object can be serialized to JSON and stored as the value of a Redis string, or JSON can be used within a specific cache component. When Java classes change, old JSON remains in Redis: Redis does not automatically rename fields, convert data types, or add values expected by the new application version. Without advance preparation, a deployment that looks like a simple DTO tweak can cause `SerializationException`, mass cache misses, wrong business values, or cross-version read failures.

**JSON schema evolution** means changing the contract of stored payloads: field names, data types, nested structures, timestamp/currency representations, Java type metadata, or data interpretation rules. **Legacy data migration** is the process of transitioning existing payloads to the new contract while controlling compatibility, TTLs, concurrent writes, conversion errors, and rollback capability.

This lesson builds a running example with Spring Boot 3.x, Spring Data Redis, and Jackson; compares migration strategies; provides Java code for compatible reads and new-schema writes; and explains how to roll out safely while Redis holds live data.

## 1. Where Does the JSON Schema Actually Live?

Redis stores keys and values as binary data. If an application uses `StringRedisTemplate` to write a JSON string, or `RedisTemplate` with a JSON serializer, Redis receives those JSON bytes under a **Redis key**. Redis does not know the value must contain `productId`, `name`, or `priceMinor`.

Example first version of a product record:

```json
{
  "id": "p42",
  "name": "Notebook",
  "priceMinor": 199000
}
```

This payload might reside at:

```text
Redis key  : shop:prod:catalog:product:v1:p42
Redis type : string
Value      : UTF-8 JSON as shown above
TTL        : 15 minutes (if this is a cache)
```

The new application wants a cleaner structured model:

```json
{
  "schemaVersion": 2,
  "id": "p42",
  "displayName": "Notebook",
  "money": {
    "amountMinor": 199000,
    "currency": "VND"
  }
}
```

This change covers three decisions: renaming `name` to `displayName`, restructuring `priceMinor` into a `money` object, and adding `schemaVersion`. In this instructional example, the system **already had an established version 1 convention that all prices were in VND in minor units (dong)**; therefore `currency: "VND"` can be populated on a sound basis. If legacy data spanned multiple currencies or lacked currency certainty, migration would have to look up a trusted business source rather than guessing `VND`.

Redis keeps the v1 payload untouched until a client overwrites it, the key expires, or an intentional migration runs.

## 2. What Can Break When the Application Changes Java Classes?

Suppose version 1 used a record:

```java
public record ProductV1(String id, String name, long priceMinor) {}
```

Version 2 changes to:

```java
public record MoneyV2(long amountMinor, String currency) {}

public record ProductV2(
        int schemaVersion,
        String id,
        String displayName,
        MoneyV2 money) {}
```

If new code reads old JSON directly as `ProductV2`, the outcome depends on Jackson configuration and type constraints:

- The old `name` field may be treated as an unknown property and throw an error if `FAIL_ON_UNKNOWN_PROPERTIES` is enabled, or be ignored if configured to allow unknown properties.
- `displayName` and `money` do not exist in old JSON, so they may become `null` if the model/mapper does not require them.
- `schemaVersion` is a primitive `int` and can receive default value `0` when absent, misleading the application into thinking the data is valid.
- If code assumes `product.money().amountMinor()`, `money == null` triggers a `NullPointerException` after deserialization appeared to succeed.

The dangerous aspect is that **not every incompatibility surfaces as an exception during JSON parsing**. A payload can deserialize into an incomplete object and cause business failures downstream.

A stable JSON contract must clarify both directions:

1. **Writer:** which fields and values are written?
2. **Reader:** which versions and validity conditions are accepted?

In rolling-deployment systems, both directions are especially critical because old and new versions run side by side.

## 3. Distinguishing Java Class Changes, JSON Schema Changes, and Key Changes

Three changes often occur together yet are distinct problems:

| Change | Example | Impact |
|---|---|---|
| Java class/package rename | `ProductDto` to `CatalogProduct` | May not affect plain JSON if field names stay identical; breaks compatibility if JSON embeds class-name metadata |
| Payload schema change | `priceMinor` to `money.amountMinor` | Old/new readers may not understand each other's payloads |
| Redis key change | `product:p42` to `shop:prod:catalog:product:v2:p42` | New application cannot automatically find data at old keys |
| Serializer change | JDK serialization to JSON | Byte format changes completely; reading old keys with new serializer normally fails |
| Redis data type change | JSON String to Redis hash | `GET` and `HGETALL` are different commands; access logic must change |

For example, with `GenericJackson2JsonRedisSerializer`, JSON may contain type metadata to reconstruct polymorphic values. If metadata points to a Java class that no longer exists after moving packages or renaming classes, deserialization can fail even though business JSON fields stayed identical. In that case, you need a type-metadata migration strategy, controlled mapping configuration, or to stop relying on Java class names in long-lived payloads.

`Jackson2JsonRedisSerializer<T>` uses a fixed target type and has a different contract from generic JSON serializers. When planning, always document the **actual serializer and `ObjectMapper` configuration used when writing v1 data**; merely seeing `{` at the start of a value does not prove all payloads share the same schema.

## 4. Classifying Compatibility Levels of JSON Changes

Not every change requires migrating every key. Classify changes according to active readers and writers:

| Change Type | Example | Risk | Common Approach |
|---|---|---|---|
| Add optional field | Add `description` | Old readers may reject unknown properties; new readers must tolerate missing fields | Allow reading extra fields intentionally; apply well-founded defaults |
| Add required field | Add `currency` | Legacy payloads lack info; `null` causes errors | Migration from authoritative source or explicit policy; validate integrity |
| Rename field | `name` → `displayName` | New reader misses old field | `@JsonAlias` during transition or explicit migrator |
| Remove field | Drop `legacyCode` | Old readers may still need it | Deploy new readers before stopping old writers; phase out in stages |
| Change type | `"199000"` → `199000` | Parsing or value interpretation differs | Controlled converter checking overflow and invalid data |
| Change unit | Dong → thousands of dong | Readable yet yields wrong monetary amounts | Version schema, convert with deterministic formula and rounding |
| Change nested structure | `priceMinor` → `money.amountMinor` | Old readers unaware of new structure | Version key/payload, adapters, and synchronized rollout plan |
| Change time format | Epoch millis → ISO-8601 | Timezone errors or parse failures | Explicitly specify units, timezone, and supporting serializer/modules |
| Change type metadata | Rename package/class in polymorphic JSON | Fails to instantiate objects | Migrate metadata/schema or use class-independent wire DTOs |
| Change Redis data type | String → Hash | Mismatched commands return `WRONGTYPE` | Move to a separate key and migrate data |

**Forward/backward compatibility** is not an intrinsic property of JSON itself. A payload is compatible only when the exact reader can read and interpret it with the same semantics. Systems must define explicitly which versions can read which versions.

## 5. JSON Contracts Should Be Independent of Domain Objects

One way to reduce risk is decoupling the **Redis storage model** from domain models and API responses. When internal classes evolve, the Redis format can remain stable; when the format truly must change, the conversion layer handles migration.

```text
REST Controller / Domain Service
              |
              v
       Product domain model
              |
        explicit mapper
              |
              v
        ProductRedisV2
              |
     ObjectMapper / serializer
              |
              v
     UTF-8 JSON in Redis
```

Example v2 data rule:

```json
{
  "schemaVersion": 2,
  "id": "p42",
  "displayName": "Notebook",
  "money": {
    "amountMinor": 199000,
    "currency": "VND"
  }
}
```

Validity checks might include `schemaVersion == 2`, non-blank `id`, non-null `money`, `currency` in the supported set, and `amountMinor >= 0` if required by domain rules. Enforce these checks **after JSON parsing**, as Jackson does not automatically know all business invariants.

To stay compatible with non-Java consumers, keep Java class/package names out of Redis payloads. Using a version field and implementation-independent wire DTOs keeps the contract far easier to maintain.

## 6. Two Places to Store the Schema Version

You can record versions **inside the payload**, **inside the Redis key name**, or in both when there is a specific reason.

### 6.1. Version Inside JSON

```text
Key: shop:prod:catalog:product:p42
```

```json
{
  "schemaVersion": 2,
  "id": "p42",
  "displayName": "Notebook",
  "money": {"amountMinor": 199000, "currency": "VND"}
}
```

Pros: the application reads `schemaVersion` and selects the matching decoder without changing key identifiers. Cons: if old/new writers write to the same key during a rolling deployment, they can **overwrite each other's schemas**, and old readers may fail on new payloads. Write paths must be carefully coordinated.

### 6.2. Version Inside the Key Name

```text
shop:prod:catalog:product:v1:p42
shop:prod:catalog:product:v2:p42
```

Pros: old/new payloads coexist cleanly, each reader knows the exact format it expects, and preferring v2 with v1 fallback is straightforward. Cons: requires policies for preserving TTL, cleaning old data, reading two keys on cache miss, and handling divergence between the two versions.

Adding version to the key does not solve multi-writer consistency on its own. If v1 updates after v2 was created, v2 becomes stale; establish a source of truth and synchronization rules.

### 6.3. Which One to Choose?

| Context | Appropriate Option to Consider |
|---|---|
| Short-TTL cache rebuildable from database | Change cache prefix/version and let v1 expire naturally; usually no key-by-key migration needed |
| Same key must stay fixed due to external references | Version inside payload with multi-schema readers, then coordinate writer upgrade |
| New payload differs substantially, two versions run concurrently | Parallel v1/v2 keys with fallback and synchronization plan |
| Long-lived data or source of truth | Controlled migration, backfill, verification, and contract-aligned rollback |
| Redis hash/repository with secondary keys/indexes | Design migration for the entire structure, not just the main JSON value |

You do not need `v1`, `v2` on every Redis key. Versioning earns its keep when separating **incompatible** representations or supporting controlled rollouts/rollbacks.

## 7. Choosing a Legacy Data Migration Strategy

Four strategies are commonly used. They can be combined, provided you define clearly which is primary and what marks migration completion.

### 7.1. Discard Old Cache, Build New Cache

For caches regenerable from a trusted source of truth, simply switch the cache prefix to v2:

```text
Cache v1: shop:prod:cache:catalog-products:v1::p42
Cache v2: shop:prod:cache:catalog-products:v2::p42
```

The new app reads/writes only v2. Old v1 data expires via TTL. Expect elevated cache miss rates after deployment; if too many concurrent requests reload data at once, origin databases can face load spikes. Use prewarming or phased rollouts as needed.

This option is unsuitable if Redis holds irrecoverable state or business data lacking an origin source.

### 7.2. Lazy Migration / Read Repair

The new app reads key v2 first. If v2 does not exist, it reads v1, decodes using the old schema, transforms to v2, writes the new key, and returns the result.

```text
GET key:v2
   |
   +-- HIT ----------> parse/validate v2 --> return
   |
   +-- MISS
        |
      GET key:v1
        |
        +-- MISS ------> fetch origin data / return cache miss
        |
        +-- HIT ------> parse v1 -> transform -> write v2 -> return
```

Pros: migrates only actively accessed keys. Cons: read misses cost extra Redis commands, rarely read keys may never migrate, and reading v1 while it receives concurrent writes needs dedicated consistency rules.

### 7.3. Batch Backfill

A dedicated job scans v1 keys in rate-limited batches, converts payloads to the new schema, and tracks progress. On standalone Redis you can use `SCAN MATCH <pattern>`; on Redis Cluster use a topology-aware client/tool scanning appropriate primaries.

`SCAN` does not provide a consistent snapshot and may return the same key multiple times, so migration jobs must be **idempotent**. Never use `KEYS *` to scan millions of keys in production. Backfill is useful when unaccessed keys must also migrate, while controlling contention with active writers.

### 7.4. Dual-Write During Transition

While both v1 and v2 consumers still run, new writers can write both representations:

```text
Business update
   |
   +--> write v1 for old readers
   |
   +--> write v2 for new readers
```

Writing two keys with two separate commands **is not automatically atomic**. If one succeeds and the other fails, data diverges. In Redis Cluster, if keys land in different hash slots, you cannot wrap them in a single multi-key transaction/Lua script. Pick consistency mechanisms suited to your requirements: an external source of truth, replayable events, re-runnable migrations, or same-slot co-location only when truly justified.

Dual-write is a temporary phase with an end date; maintaining two formats forever increases divergence risk and maintenance cost.

## 8. Comparing Strategies by Data Characteristics

| Strategy | Best Suited For | Benefits | Risks to Manage |
|---|---|---|---|
| Change prefix and rebuild | Caches with origin source, short TTL | Simple, no parsing of legacy data | Cache miss spikes and origin load |
| Lazy migration | Large keysets mostly cold | Migrates only active data | Legacy read errors on request path; stale writes |
| Batch backfill | Long-lived data needing complete migration | Clear progress and metrics | Redis load, concurrent mutations, missed keys |
| Dual-write | Rolling deployments with coexisting old/new consumers | Keeps both readers served | Non-atomic writes; must end transition window |
| Big-bang migration with write freeze | Small datasets allowing downtime | Easy consistency cutoff | Write freeze/downtime and complex rollback |

Systems often pair **dual-read + v2-only-write + backfill** for gradual migration, yet only after all v1 writers have stopped writing or old writers no longer create diverging updates. Otherwise, resolve write conflicts instead of assuming v2 is always fresher.

## 9. Practical Example: Schema v1 and Schema v2 with Jackson

Suppose a Spring Boot 3.x / Java 21 application uses `StringRedisTemplate` to store UTF-8 JSON. Both schemas have Redis type **string**; changing schemas does not turn Redis into a hash.

### JSON v1

```json
{
  "id": "p42",
  "name": "Notebook",
  "priceMinor": 199000
}
```

### JSON v2

```json
{
  "schemaVersion": 2,
  "id": "p42",
  "displayName": "Notebook",
  "money": {
    "amountMinor": 199000,
    "currency": "VND"
  }
}
```

DTOs dedicated to the Redis format:

```java
public record ProductV1(String id, String name, long priceMinor) {}

public record MoneyV2(long amountMinor, String currency) {}

public record ProductV2(
        int schemaVersion,
        String id,
        String displayName,
        MoneyV2 money) {}
```

Business transformation function:

```java
public final class ProductSchemaMigration {
    private ProductSchemaMigration() {}

    public static ProductV2 toV2(ProductV1 legacy) {
        if (legacy == null || legacy.id() == null || legacy.id().isBlank()) {
            throw new IllegalArgumentException("Invalid legacy product id");
        }
        if (legacy.name() == null || legacy.name().isBlank()) {
            throw new IllegalArgumentException("Invalid legacy product name");
        }
        if (legacy.priceMinor() < 0) {
            throw new IllegalArgumentException("Invalid legacy price");
        }
        // This example's v1 data contract defines all prices in VND.
        return new ProductV2(
                2,
                legacy.id(),
                legacy.name(),
                new MoneyV2(legacy.priceMinor(), "VND"));
    }
}
```

This is a **semantically meaningful transformation**: beyond renaming a field, it builds a new money structure. With real data, add rules for nulls, currencies, negative amounts, deleted products, or previously malformed v1 records.

## 10. Example: Compatible Reading and On-Access Migration

The code below illustrates **read v2 → fallback v1 → convert → write v2**, while attempting to preserve key v1's remaining lifetime. It fits a cache with **a coordinated single writer**, where v1 stops receiving updates once v2 is deployed. Multi-writer and high-consistency setups need additional design covered in later sections.

```java
package com.example.catalog.redis;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class ProductRedisStore {

    public record ProductV1(String id, String name, long priceMinor) {}
    public record MoneyV2(long amountMinor, String currency) {}
    public record ProductV2(
            int schemaVersion,
            String id,
            String displayName,
            MoneyV2 money) {}

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;

    public ProductRedisStore(StringRedisTemplate redis, ObjectMapper mapper) {
        this.redis = redis;
        this.mapper = mapper;
    }

    public ProductV2 read(String productId) throws JsonProcessingException {
        String id = validId(productId);
        String currentKey = keyV2(id);

        String currentJson = redis.opsForValue().get(currentKey);
        if (currentJson != null) {
            return parseV2(currentJson, id);
        }

        String legacyKey = keyV1(id);
        String legacyJson = redis.opsForValue().get(legacyKey);
        if (legacyJson == null) {
            return null; // Cache miss across both versions.
        }

        ProductV1 old = mapper.readValue(legacyJson, ProductV1.class);
        if (!id.equals(old.id()) || old.name() == null || old.name().isBlank()
                || old.priceMinor() < 0) {
            throw new IllegalStateException("Invalid ProductV1 payload");
        }

        ProductV2 converted = new ProductV2(
                2, old.id(), old.name(),
                new MoneyV2(old.priceMinor(), "VND"));

        // Fetch TTL after reading v1 value; key might expire in between.
        Long ttlMillis = redis.getExpire(legacyKey, TimeUnit.MILLISECONDS);
        if (ttlMillis == null || ttlMillis == -2L || ttlMillis == 0L) {
            return null;
        }

        String migratedJson = mapper.writeValueAsString(converted);
        if (ttlMillis == -1L) {
            // V1 has no TTL: only keep persistent if the contract explicitly permits it.
            redis.opsForValue().setIfAbsent(currentKey, migratedJson);
        } else if (ttlMillis > 0L) {
            redis.opsForValue().setIfAbsent(
                    currentKey, migratedJson, Duration.ofMillis(ttlMillis));
        }

        // Another writer might have written v2 first; read final v2 value.
        String finalJson = redis.opsForValue().get(currentKey);
        return finalJson == null ? null : parseV2(finalJson, id);
    }

    private ProductV2 parseV2(String json, String expectedId)
            throws JsonProcessingException {
        ProductV2 value = mapper.readValue(json, ProductV2.class);
        if (value.schemaVersion() != 2
                || !expectedId.equals(value.id())
                || value.displayName() == null
                || value.displayName().isBlank()
                || value.money() == null
                || value.money().amountMinor() < 0
                || !"VND".equals(value.money().currency())) {
            throw new IllegalStateException("Invalid ProductV2 payload");
        }
        return value;
    }

    private static String validId(String id) {
        if (id == null || !id.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid product ID");
        }
        return id;
    }

    private static String keyV1(String id) {
        return "shop:prod:catalog:product:v1:" + id;
    }

    private static String keyV2(String id) {
        return "shop:prod:catalog:product:v2:" + id;
    }
}
```

**What this example guarantees conceptually:** the reader prioritizes schema v2, uses a separate v1 class to read old payloads, avoids overwriting an existing v2 key via `setIfAbsent`, validates required fields, and preserves remaining TTL in milliseconds where possible.

**Limitations to understand before production use:**

- `GET v1`, `PTTL v1`, and `SET ... NX v2` are separate commands. V1's value or TTL can change between commands; this snippet **provides no snapshot/transaction** and does not guarantee strict consistency with concurrent writers.
- TTL counts down while commands execute; the TTL set on v2 is best-effort and may drift slightly in real time. For data needing exact expiration timestamps, store a business-meaningful `expiresAt` and use appropriate conversion logic.
- If key v1 vanishes by the time TTL is checked, the snippet returns a cache miss; the system must reload from the primary source rather than reviving a just-expired key.
- `setIfAbsent` returns `Boolean` or `null` in certain contexts; here we do not rely on its return value, instead reading v2 back. If Redis read/write access fails, the exception propagates to the caller rather than silently returning an empty result.
- The code assumes all v1 data is in `VND`, defined by the example's historical contract. Never infer currency from field names or numeric magnitudes in real data.
- Prefix `shop:prod` is hardcoded for illustration; in real apps, construct it from environment configuration and a central key builder.

Systems requiring strict prevention of stale reads while v1 updates must add origin version numbers, fencing, event sequences, appropriate locks, or load directly from the authoritative database. Never use simple read repair as a multi-writer authoritative state sync mechanism.

## 11. Separating Readers and Writers to Avoid Backward Schema Overwrites

In multi-version rollouts, a safer pattern is making **read capability** and **write authority** explicit per phase:

```text
Phase A: old app          -> read v1, write v1
Phase B: new app          -> read v1/v2, write v1 (if old readers still need it)
Phase C: all readers      -> read v1/v2; writers switch to v2
Phase D: backfill         -> migrate remaining v1 to v2
Phase E: end fallback     -> read/write v2 only
```

This diagram shows **capability sequencing**; exact execution depends on whether old readers run alongside new writers. If old readers cannot read v2 on the same key, never mutate the payload in key v1 while old readers remain live.

Example using separate v1 and v2 keys:

```text
Old application: GET/SET key:v1
New application: GET key:v2; fallback key:v1; SET key:v2
```

If the old application keeps updating v1, a newly migrated v2 key can go stale. To run concurrently, choose one of:

- Designate an external source of truth and invalidate both caches on update events.
- Dual-write with failure handling when writing either version fails.
- Pause or transfer v1 write authority before backfilling and preferring v2.
- Attach a business-meaningful `revision` or `updatedAt`, comparing versions to decide which source is fresher.

Avoid assuming "v2 is always right because its number is higher" without proof of write ordering.

## 12. Rolling Deployment: Write the Read/Write Matrix Upfront

A decision matrix exposes rollout hazards before deployment:

| Application Version | Reads v1 | Reads v2 | Writes v1 | Writes v2 |
|---|---|---|---|---|
| Old application | Yes | No | Yes | No |
| Compatibility release (bridge) | Yes | Yes | Phased | Phased |
| Final new application | Temporarily, then dropped | Yes | No | Yes |

Never rely on "deploy all pods really fast" as a substitute for a compatibility plan. With Kubernetes, rolling updates, or multiple concurrent instances, even a single lingering old writer can break migration assumptions.

For schemas sharing **the same key**, the safe sequence is deploying **new readers that accept the old schema**, confirming all readers are upgraded, and only then switching the writer format. If rolling back to the old version becomes necessary after writers emitted v2 JSON, check whether the old version can read v2 JSON; rolling back code alone may not restore readability.

With **two separate versioned keys**, you can keep v1 for a defined rollback window, provided you decide how updates stay synchronized and when old keys get cleaned up.

## 13. Batched Migration: Algorithm and Idempotency Conditions

A batch migrator should follow an explicit workflow:

```text
1. Define scope: namespace, environment, tenant, source schema/version.
2. Incrementally traverse v1 keys using SCAN with bounded batch sizes.
3. Verify TYPE, read value and TTL with appropriate APIs.
4. Parse using v1 schema/serializer; validate source data.
5. Transform to v2 via a pure function with clear business rules.
6. Write to v2 key conditionally without overwriting newer data.
7. Record counts: succeeded, skipped, failed, expired.
8. Resume from recoverable checkpoints and reconcile data.
9. Once read fallback drops near zero and owners approve, close migration.
```

Example scan command on a standalone test instance:

```bash
redis-cli --scan --pattern 'shop:prod:catalog:product:v1:*'
```

Never use `KEYS shop:prod:catalog:product:v1:*` as a default on large datasets because `KEYS` can occupy Redis processing huge key counts in a single blocking command.

`SCAN` is not a snapshot and does not guarantee each key appears only once while the keyspace mutates. Migrators must handle duplicates, keys expiring mid-read, overwritten keys, and newly created keys between scan cycles. A `lastKey` checkpoint is not a safe cursor when traversal order is non-sequential; complete migration may require multiple passes or iterating IDs from an independent source of truth.

### Idempotency Rules

If a job migrates `p42` from v1 to v2 and stops, re-running must not corrupt v2 or endlessly extend TTLs. Writing with `SET ... NX`/`setIfAbsent` avoids overwriting v2, yet if v1 changed after v2 was created, merely "not overwriting" **does not ensure consistency**. Know whether v1 writes have stopped, or use revisions/versions to pick the right state.

For conversion errors, classify metrics into buckets like `invalid-json`, `missing-required-field`, `unknown-currency`, `serializer-mismatch`, `expired-during-migration`, and `redis-write-error`. Never dump full user payloads or secrets into logs or dead-letter queues just for easier debugging.

## 14. Preserving TTL During Schema Migration

TTL is part of the data contract, especially for caches, sessions, tokens, and rate limits. If key v1 has 120 seconds left and the migrator writes key v2 with a default 24-hour TTL, the application holds stale data far longer than intended.

Redis provides:

```redis
TTL shop:prod:catalog:product:v1:p42
PTTL shop:prod:catalog:product:v1:p42
```

Meaning of results:

| Result | `TTL` | `PTTL` |
|---|---|---|
| Positive number | Remaining seconds | Remaining milliseconds |
| `-1` | Key exists with no expiry | Same |
| `-2` | Key does not exist | Same |
| `0` | Under one respective time unit left before expiry | May expire right around measurement time |

When creating key v2, choose an explicit rule:

1. **Preserve equivalent expiry:** read remaining TTL and apply to v2, accounting for migration latency; suited to caches/sessions that must not extend lifetimes.
2. **Preserve absolute expiry:** if business data stores `expiresAt` in a trusted source, use that timestamp consistently across writers to avoid latency drift.
3. **Issue new TTL:** only when domain rules allow resetting lifetimes on data refresh.
4. **No TTL:** only when data may persist indefinitely; never turn a TTL-bound cache key into a permanent key by omitting `EXPIRE`.

Separate `GET`, `PTTL`, and `SET` commands have race conditions. On a single node or same-slot keys in Cluster, a Lua script or appropriate transaction can group atomic steps; design and verify feasibility rather than assuming every old/new key pair can be updated atomically in Cluster.

For keys **with no TTL**, check whether they are genuinely long-lived data or keys missing expiry configuration in an old release. Migration should not silently legitimize a legacy TTL bug without a business decision.

## 15. Handling Concurrent Updates and Version Ordering

Dangerous scenario:

```text
T1: Migrator reads v1 = price 100
T2: Old app updates v1 = price 120
T3: Migrator writes v2 = price 100
T4: New app reads v2 = price 100 (stale)
```

If Redis is only a cache, handle this by invalidating v2 whenever price changes in the primary database and reloading. If Redis owns authoritative updates, define tighter concurrency controls.

Common techniques:

- **Transfer write authority:** disable v1 writers, verify no v1 updates remain, then batch migrate remaining entries.
- **Revisions/sequences:** each record carries a monotonically increasing version from the business source; migrators write only if the source revision matches and is not older than v2.
- **Compare-and-set:** read version and perform conditional writes via topology-appropriate atomic primitives.
- **Event-driven synchronization:** persist mutations to a durable store and emit replayable events applied in version order to cache v2.
- **Single source of truth:** always derive authoritative state from the business database, keeping Redis a rebuildable projection.

Never address concurrency merely by "running migration during off-peak hours": lower traffic lowers race probability, yet never guarantees v1 stops changing.

### What Does Redis Cluster Do Differently?

Redis Cluster requires atomic multi-key operations to operate on keys in the same hash slot. Two keys such as:

```text
shop:prod:catalog:product:v1:p42
shop:prod:catalog:product:v2:p42
```

may map to different slots. A client can `GET` from one slot and `SET` in another, yet there is no standard single-command atomic transaction/Lua script spanning two keys in different slots on Redis Cluster.

If you know from the start that multiple versions of the same entity need atomic operations, design hash tags around the ID:

```text
shop:prod:catalog:product:{p42}:v1
shop:prod:catalog:product:{p42}:v2
```

These two keys share a slot. Still, renaming existing keys to add hash tags is itself another migration; never casually rename production keys just to run a short-term script. Grouping all keys under one broad hash tag like `{catalog}` creates hot shards and defeats load distribution.

## 16. Using Jackson to Support Minor Transitions

For minor changes, an immediate batch migration may not be necessary. Jackson can help new readers accept old field shapes during transition.

For example, simply renaming `name` to `displayName`:

```java
import com.fasterxml.jackson.annotation.JsonAlias;

public record ProductCompatible(
        String id,
        @JsonAlias("name") String displayName,
        long priceMinor) {}
```

`@JsonAlias("name")` accepts the old field name on reads; when writing via normal Jackson serialization, the primary property name `displayName` is emitted. **Aliases do not rewrite old JSON bytes in Redis** and do not solve scenarios where multiple writers continue emitting two different field names.

A DTO can tolerate unknown properties:

```java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public record ProductReader(
        String id,
        String displayName,
        long priceMinor) {}
```

This helps readers tolerate extra fields, yet can hide schema bugs if a field was misnamed or required data is missing. Always run **post-deserialization data validation** when business accuracy matters.

Other options include `@JsonProperty`, `@JsonCreator`, custom deserializers, and multi-schema adapter readers. Choose the tool matching the change size:

- **Aliases** suit simple field renames during a compatibility window.
- **Custom deserializers** suit differing structures with clear mapping rules.
- **Versioned DTOs + migrators** suit major schema changes requiring audits, backfills, or rollback support.

Never overload one DTO with dozens of aliases and defaults to read every historical schema indefinitely. Once old readers retire and legacy data drains, remove legacy code paths to reduce maintenance overhead.

## 17. `RedisTemplate`, Spring Cache, and Repositories Have Their Own Contracts

Migrations must identify **what produced the payload**, because serialization settings differ across Spring Data Redis APIs.

### 17.1. `RedisTemplate` with a JSON Serializer

Example:

```java
RedisTemplate<String, ProductV2> template = new RedisTemplate<>();
template.setConnectionFactory(connectionFactory);
template.setKeySerializer(new StringRedisSerializer());
template.setValueSerializer(
        new Jackson2JsonRedisSerializer<>(ProductV2.class));
template.afterPropertiesSet();
```

This illustrates a configuration pattern: UTF-8 string keys and `ProductV2` JSON values. If values were previously written with `Jackson2JsonRedisSerializer<ProductV1>` or a different `ObjectMapper`, do not assume the v2 serializer reads all v1 keys cleanly. Verify the source format and provide a matching converter or v1 read path.

If `RedisTemplate` handles multiple value types via a polymorphic serializer, type metadata and trust settings are part of the contract. Never enable default typing carelessly just to read "any JSON"; restrict permitted types and prevent untrusted data from instantiating unintended classes.

### 17.2. Spring Cache Uses `RedisCacheConfiguration`

`@Cacheable` typically stores entries via `RedisCacheManager`, with its own key prefix, TTL, and value serializer settings. Changing the serializer on a `RedisTemplate` bean **does not guarantee** caches switch formats. For rebuildable caches, a simple approach is changing the cache name or Redis Cache prefix/version to create new v2 keys and letting v1 expire.

```text
Before: shop:prod:cache:products:v1::p42
After:  shop:prod:cache:products:v2::p42
```

To perform lazy migration from v1 to v2 in Spring Cache, fallback logic typically belongs in an explicit cache adapter/custom wrapper. Changing `@Cacheable(cacheNames = "products")` alone does not give you a two-version JSON reader.

### 17.3. Redis Repositories Use Their Own Mapping

Spring Data Redis Repositories with `@RedisHash` typically map objects to **Redis hashes** via `MappingRedisConverter`, often accompanied by metadata/index keys. This is not a single JSON string read via `GET`.

If a repository entity changes fields or converters, migration may need to handle hash field names, keyspaces, indexes, `_class` metadata, and framework-managed auxiliary keys. Do not copy the `StringRedisTemplate` v1/v2 example above verbatim for repositories when storage is actually a Redis hash. Check `TYPE <key>` and the data-writing API before building a migrator.

## 18. When the Old Serializer Is Not JSON

A system might start with `JdkSerializationRedisSerializer` and later move to JSON. That is a **byte-format** conversion, not merely a JSON schema change.

```text
V1: Java native serialization bytes
V2: UTF-8 JSON
```

You cannot ask Jackson to read JDK serialization bytes directly as JSON. Migration needs a decoder compatible with the old format, a conversion step from the Java object to a v2 DTO, and then a new JSON writer.

Deserializing Java native payloads poses security risks when data is untrusted or dangerous classes sit on the classpath. If a legacy system must decode JDK bytes, restrict data sources and apply JVM/library type filters; never build a generic migration tool that blindly deserializes arbitrary bytes found in Redis.

Likewise, if the source uses MessagePack, CBOR, Protocol Buffers, or compressed JSON, use the matching decoder and schema. Never guess serializers from key suffixes or the first few payload characters.

## 19. End-to-End Rollout Plan

Suppose you need to transition a product cache from v1 to v2 without API downtime. A plan can be phased as follows:

### Phase 0 — Inventory and Lock Contracts

Document `key pattern`, owner, Redis type, serializer, `ObjectMapper`, schema fields, lifetimes, estimated key counts, active writers/readers, and business rules. Separate origin-backed caches from data acting as a source of truth. Inventory framework-managed keys too, not only keys created explicitly by business code.

### Phase 1 — Build Compatible Readers

Create v1 and v2 DTOs, validated transformation functions, and clear error categories. With key versioning, new readers check v2 first and fall back to v1. Deploy readers before modifying writers to minimize risk during rolling deployments.

### Phase 2 — Coordinate Write Paths

Define exactly when v1 writers stop or when dual-writing starts. While old readers remain active, preserve the old contract where old readers read. If migration risks write contention, use an origin of truth, revisions, or proper synchronization.

### Phase 3 — Enable Throttled Migration

For lazy migration, cap conversion rates on request paths if latency rises; for batch migration, cap concurrency, commands/second, and Redis load. Monitor conversion success/failure counts and payload quality. Handle invalid payloads per policy rather than silently writing bad defaults.

### Phase 4 — Verify New Data

Spot-check representative samples across tenants/domains/schemas: numeric values, timestamp formats, nulls, Unicode text, empty arrays, expired keys, and previously invalid records. For critical data, verify against the business origin or revisions, not just key counts.

### Phase 5 — Retire Legacy Support

Once no v1 readers/writers remain, fallback rates drop within acceptable thresholds, and all required data has migrated, remove the v1 read path. V1 keys with TTLs can expire naturally; long-lived keys require an explicitly scoped cleanup job.

### Phase 6 — Close Out and Document Contracts

Record the v2 schema, key version, serializer, TTL, owner, which release retired the old path, and remaining rollback scope. Remove temporary DTOs/converters once the support window closes; retain migration notes so operators know why v1/v2 keys existed.

## 20. Which Signals Should You Monitor During Migration?

Do not merely watch whether a job "finished." These metrics tell you whether it is safe to advance to the next phase:

| Signal | Meaning |
|---|---|
| v2 read success rate | How much traffic the new reader serves via the new schema |
| v1 fallback rate | How many requests still depend on legacy data |
| v1/v2 key counts by pattern | Remaining scale estimate; understand SCAN and cluster topology |
| Schema parse/validation errors | Malformed data or serializer mismatches |
| Keys expired mid-migration | Clarifies TTL behavior and cache misses |
| Write conflicts / skipped because v2 exists | Surfaces write contention or idempotency triggers |
| Read path p95/p99 latency | Whether fallback/migration slows requests |
| Redis CPU/network/memory and origin load | Whether migration impacts primary workloads |
| Active consumers/writers still on v1 | Practical gate for retiring the old path |

Never treat `DBSIZE` or a single-node `SCAN` as the key count of an entire Redis Cluster. For cluster-wide inventories, aggregate across primary nodes per current topology. For TTL-bounded caches, **fallback and error rates** are usually more actionable than chasing an exact absolute count of v1 keys.

In migration error logs, record only diagnostic fields such as schema version, exception category, shortened key prefix or hashed ID, correlation ID, and timestamp; never log sensitive payloads or tokens.

## 21. Rollback Must Be Designed Before Writing v2 Data

Rolling back application code to an older version does not automatically roll back Redis data. For example:

```text
v1 app: only understands JSON schema v1
v2 app: writes JSON schema v2 into the same key
Rollback to v1: v1 reads v2 payload -> errors
```

To stay rollback-ready, keep separate v1 keys for a defined window, maintain controlled dual-writes, or ship a bridge release able to read v2. Every option has trade-offs: if new writers add v2 fields that cannot be expressed in v1, "writing backward" loses data.

A rollback checklist should answer:

| Question | Why It Must Be Answered |
|---|---|
| Can the old version read v2? | Avoids code rollback still failing deserialization |
| After cutover, who still writes v1? | Reveals whether v1 data stays fresh or becomes stale |
| Is information lost converting v2 → v1? | Prevents rollback from overwriting and losing data |
| Are TTLs still valid? | Avoids reviving keys that should have expired |
| When can v1 keys be deleted? | Preserves an adequate rollback window per policy |
| What if Redis disconnects during dual-write? | Requires a reconciliation and resync plan |

For rebuildable caches, rollback can revert to the v1 prefix and repopulate cache via the old writer. For source-of-truth data, data rollback demands a stricter conversion and verification plan.

## 22. Common Pitfalls

**"Simply renaming a Java field makes Redis understand the new schema."**

No. Redis holds bytes written by the old writer. Jackson can support aliases or custom deserialization rules, yet does not rewrite existing JSON in Redis.

**"JSON readable in `redis-cli` means the schema is compatible."**

No. Syntactically valid JSON can still lack required fields, carry wrong currency units, use the wrong timezone, or contain obsolete Java type metadata.

**"Changing `RedisTemplate`'s `valueSerializer` migrates every cache."**

No. Spring Cache uses `RedisCacheConfiguration`, Spring Session has its own config, and Redis Repository usually uses hash mapping via converters. Identify what actually created the data.

**"Having `@JsonIgnoreProperties(ignoreUnknown = true)` makes every version compatible."**

No. Skipping unknown fields does not populate missing required values and can mask schema bugs.

**"Switching to key v2 finishes the migration."**

Not enough. Account for TTLs, active v1 writers, long-lived v1 entries, cache miss spikes, secondary indexes/keys, and rollback plans.

**"`setIfAbsent` guarantees keeping the newest data."**

No. It only avoids overwriting an existing key at execution time. If v1 updates after v2 is created, v2 can still become stale.

**"Migrating `v1` to `v2` in Cluster can always use one Lua script."**

No. Atomic multi-key Lua in Redis Cluster requires keys to share the same hash slot. Keys `v1` and `v2` built from differing names can land in different slots.

**"You can delete all v1 keys as soon as the batch job finishes."**

Unsafe. Verify whether the batch skipped keys due to keyspace mutations, whether old writers remain live, whether data passed verification, and whether the rollback window still relies on v1 keys.

## 23. Controlled Hands-On Practice

In a test Redis environment, manually create v1 and v2 JSON under two separate keys:

```bash
redis-cli SET shop:dev:catalog:product:v1:p42 \
  '{"id":"p42","name":"Notebook","priceMinor":199000}' EX 300

redis-cli --raw GET shop:dev:catalog:product:v1:p42
redis-cli PTTL shop:dev:catalog:product:v1:p42
```

After running a compatible reader like the Java example, inspect:

```bash
redis-cli --raw GET shop:dev:catalog:product:v2:p42
redis-cli PTTL shop:dev:catalog:product:v2:p42
redis-cli TYPE shop:dev:catalog:product:v2:p42
```

When key v2 exists, its Redis type remains `string`, yet the JSON holds `schemaVersion: 2`, `displayName`, and `money`. Key v2's TTL should reflect the chosen policy—typically close to v1's remaining lifetime if preserving expiry.

Practice three extra scenarios:

1. Omit `name` from v1 to see the converter reject invalid payloads.
2. Create v2 first, then trigger v1 fallback to confirm conditional writes do not overwrite v2.
3. Let v1 expire and verify the reader returns a cache miss so the app reloads from the primary source.

In real environments, never run experimental migrations against production Redis; constrain scope and prepare observability and rollback plans.

## 24. Self-Check Questions

1. How does adding a required field to JSON differ from adding an optional field for old readers vs. new readers?
2. Why does `@JsonAlias` support reading legacy data yet not rewrite JSON stored in Redis?
3. When should you change the key prefix/schema version instead of overwriting payloads on the same key?
4. How can lazy migration leave staler data in v2 when a v1 writer is still active?
5. Why must `PTTL == -1` and `PTTL == -2` be handled differently?
6. If cache v1 can be rebuilt from a database, why might migrating every v1 key individually be unnecessary?
7. In Redis Cluster, what condition enables running an atomic script touching both v1 and v2 keys?
8. Why can rolling back application code fail even when the old code did not change at all?
9. Do `RedisCacheManager`, `RedisTemplate`, and `@RedisHash` necessarily share the same serializer?
10. For legacy monetary data lacking a currency field, what basis is required before filling in `currency` in the new schema?

## 25. Conclusion

In Spring Data Redis, JSON schemas and byte encodings are **storage contracts across application versions**, not internal details of a single Java class. When renaming fields, changing data types, or altering payload structures, define compatible readers/writers, pick payload or key versioning, align migration with data lifecycles, and preserve TTL semantics.

For rebuildable caches, changing namespaces and letting legacy entries expire is often simple enough. For data that must be preserved, use compatible readers, explicit transformations, controlled batch/lazy migrations, concurrent-write protection, and completion metrics before retiring legacy schemas. A migration is truly finished only when all consumers support the new format, critical data is verified, legacy writes have ceased, and rollback plans no longer rest on wrong assumptions about bytes in Redis.
