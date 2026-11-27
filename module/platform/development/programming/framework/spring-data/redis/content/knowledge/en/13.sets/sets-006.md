# Creating Secondary Indexes with Sets in Spring Data Redis

Redis is a key–value store: once you know the exact key, an application can read data very quickly. However, business questions such as **"Fetch all products in the keyboard category"**, **"Find products that are both in the keyboard category and made by brand Acme"**, or **"Find accounts with the admin role"** cannot be answered by a single `GET` if data is only stored by ID.

One way to add attribute-based lookup capabilities is to use **Redis Sets as secondary indexes**. Each index key represents a condition; the Set's elements are the **IDs of records** matching that condition. Spring Data Redis provides `SetOperations<K, V>` to create, update, check, and combine ID sets using commands like `SADD`, `SREM`, `SMEMBERS`, `SISMEMBER`, `SINTER`, and `SUNION`.

This approach is straightforward and effective when filters involve few attributes, data is clearly structured, and the application manages index synchronization itself. The hard part lies not in `SADD`, but in **keeping index Sets consistent with primary data**, controlling cardinality, avoiding stale results, and understanding multi-key operation limits in Redis Cluster.

## 1. What Is a Secondary Index?

Suppose product data is stored by ID:

```text
shop:prod:catalog:product:p101
    -> {id: p101, category: keyboard, brand: acme, name: "Keyboard A"}

shop:prod:catalog:product:p102
    -> {id: p102, category: mouse, brand: acme, name: "Mouse B"}

shop:prod:catalog:product:p103
    -> {id: p103, category: keyboard, brand: nova, name: "Keyboard C"}
```

The keys `product:p101`, `product:p102`, and `product:p103` allow lookup by ID, yet they do not provide a ready-made list of IDs belonging to `category=keyboard`.

We create additional Redis Sets:

```text
shop:prod:catalog:idx:category:keyboard
    -> {p101, p103}

shop:prod:catalog:idx:category:mouse
    -> {p102}

shop:prod:catalog:idx:brand:acme
    -> {p101, p102}

shop:prod:catalog:idx:brand:nova
    -> {p103}
```

When finding products in the `keyboard` category, the application retrieves IDs from Set `idx:category:keyboard`, then reads each record by ID. When adding the `brand=acme` condition, take the **intersection** of the two Sets.

Data diagram:

```text
                  PRIMARY RECORDS
            +---------------------------+
            | product:p101  keyboard    |
            | product:p102  mouse       |
            | product:p103  keyboard    |
            +---------------------------+
                       ^
                       | lookup by ID
                       |
                 SECONDARY INDEX
      +----------------+------------------+
      |                                   |
idx:category:keyboard               idx:brand:acme
      |                                   |
   {p101, p103}                       {p101, p102}
      |                                   |
      +------------ SINTER ---------------+
                       |
                     {p101}
                       |
              GET/HGETALL product:p101
```

**Primary records** hold the product content. **Secondary indexes** merely map a search condition to IDs. Indexes should typically be rebuildable from primary data; they should not become an independent source of truth unless explicitly designed as such.

## 2. Why Use Redis Sets?

A Redis Set is a collection of **unique** elements with **no guaranteed sort order**.

Example:

```redis
SADD shop:prod:catalog:idx:category:keyboard p101 p103
SADD shop:prod:catalog:idx:category:keyboard p101
SMEMBERS shop:prod:catalog:idx:category:keyboard
```

Element `p101` is not duplicated when added a second time. Redis does not promise returning `SMEMBERS` in the order `p101` then `p103`; Sets are built for membership checks and intersection/union/difference operations, not chronological sorting or ranking.

Properties that make Sets suitable as indexes:

- **Uniqueness:** an ID appears only once per Set.
- **Fast membership lookup:** `SISMEMBER` checks whether an ID belongs to an index.
- **Combining conditions:** `SINTER` for AND, `SUNION` for OR, `SDIFF` for set difference.
- **Simple updates:** `SADD` adds IDs, `SREM` removes IDs.
- **Counting elements:** `SCARD` returns the Set's cardinality, keeping stale-index caveats in mind.

Redis Sets do not understand product attributes automatically. When `category` changes, **the application must explicitly** remove the ID from the old index Set and add the ID to the new index Set.

## 3. Naming Conventions for Keys and Index Elements

A useful convention:

```text
<application>:<environment>:<domain>:idx:<attribute>:<normalized-value>
```

Example:

```text
shop:prod:catalog:idx:category:keyboard
shop:prod:catalog:idx:brand:acme
shop:prod:identity:idx:role:admin
shop:prod:orders:idx:status:pending
```

Primary record keys:

```text
<application>:<environment>:<domain>:<entity>:<id>

shop:prod:catalog:product:p101
shop:prod:orders:order:o501
```

This naming separates two concepts:

| Key Kind | Example | Redis Type / Meaning |
|---|---|---|
| Primary data | `shop:prod:catalog:product:p101` | Hash or string holding product data |
| Category index | `shop:prod:catalog:idx:category:keyboard` | Set holding product IDs with category=keyboard |
| Brand index | `shop:prod:catalog:idx:brand:acme` | Set holding product IDs with brand=acme |
| Role index | `shop:prod:identity:idx:role:admin` | Set holding user IDs with role admin |

Values inside the Set should be **stable IDs**, not full JSON payloads or Java objects. Storing JSON copies across multiple Sets forces updating multiple copies whenever product info changes and increases memory overhead quickly.

Normalize `category`, `brand`, `status`, or `tenantId` before constructing keys. If `Keyboard`, `keyboard`, and `KEYBOARD` all mean the same category, normalize to a **canonical slug** like `keyboard`. Conversely, do not alter case on IDs where the system treats letter case as significant.

Never embed emails, tokens, passwords, or plaintext sensitive data in key names. Key names can show up in logs, backups, and admin tools.

## 4. Foundational Redis Commands for Building Indexes

Suppose data is created in a practice Redis environment:

```redis
HSET shop:demo:catalog:product:p101 id p101 name "Keyboard A" category keyboard brand acme
HSET shop:demo:catalog:product:p102 id p102 name "Mouse B" category mouse brand acme
HSET shop:demo:catalog:product:p103 id p103 name "Keyboard C" category keyboard brand nova
```

Add IDs into the index Sets:

```redis
SADD shop:demo:catalog:idx:category:keyboard p101 p103
SADD shop:demo:catalog:idx:category:mouse p102
SADD shop:demo:catalog:idx:brand:acme p101 p102
SADD shop:demo:catalog:idx:brand:nova p103
```

Commonly used commands:

| Redis Command | Meaning | Return Value / Characteristics |
|---|---|---|
| `SADD key member...` | Add one or more IDs | Number of **newly** added members |
| `SREM key member...` | Remove one or more IDs | Number of members actually removed |
| `SISMEMBER key member` | Check if ID belongs to Set | 1 if present, 0 if absent |
| `SMEMBERS key` | Fetch all IDs | No guaranteed order |
| `SCARD key` | Count IDs | Number of elements in the Set |
| `SINTER key1 key2 ...` | Intersect Sets | IDs matching **all** conditions |
| `SUNION key1 key2 ...` | Union Sets | IDs matching **at least one** condition |
| `SDIFF key1 key2 ...` | Set difference | IDs in the first Set not in subsequent Sets |
| `SSCAN key cursor ...` | Incrementally scan IDs | Not a stable snapshot while Set mutates |

Example membership check:

```redis
SISMEMBER shop:demo:catalog:idx:category:keyboard p101
# (integer) 1

SISMEMBER shop:demo:catalog:idx:category:keyboard p102
# (integer) 0
```

Example count:

```redis
SCARD shop:demo:catalog:idx:category:keyboard
# (integer) 2
```

These results are illustrated on the static sample data above. In an application with multiple writers, Sets can change between observation commands.

## 5. Searching by One Condition: `SMEMBERS` and `SISMEMBER`

Requirement: **"Find all products in the keyboard category"**.

Step 1, retrieve IDs:

```redis
SMEMBERS shop:demo:catalog:idx:category:keyboard
```

The result is a set containing `p101` and `p103`, in undefined order.

Step 2, read each record's content:

```redis
HGETALL shop:demo:catalog:product:p101
HGETALL shop:demo:catalog:product:p103
```

Not every Redis Set member is guaranteed to still have an existing primary record. Between step 1 and step 2, a product may have been deleted or expired via TTL. An index may contain stale IDs if updates are asynchronous. Readers should handle missing IDs, and when correctness matters, re-verify attributes from the primary data.

If you already know the ID and only need to answer **"does p101 still belong to the keyboard category?"**, use `SISMEMBER` instead of loading the entire Set:

```redis
SISMEMBER shop:demo:catalog:idx:category:keyboard p101
```

`SISMEMBER` returns membership in **the current index**. If the index is stale, it does not replace checking authoritative product state.

## 6. Combining Multiple Conditions via Set Intersection: `SINTER`

Requirement: **"Find products with category=keyboard and brand=acme"**.

We already have:

```text
Category keyboard = {p101, p103}
Brand acme        = {p101, p102}
```

Intersection of the two Sets:

```redis
SINTER shop:demo:catalog:idx:category:keyboard shop:demo:catalog:idx:brand:acme
```

Result:

```text
{p101}
```

Logical representation:

```text
category = keyboard  AND  brand = acme

Set(category:keyboard) ∩ Set(brand:acme)
                        |
                        v
                      {p101}
```

You can add a third condition if a corresponding index exists, such as `status=active`:

```redis
SINTER shop:demo:catalog:idx:category:keyboard shop:demo:catalog:idx:brand:acme shop:demo:catalog:idx:status:active
```

**Note:** This is a multi-key Redis operation. When using Redis Cluster, Set keys must satisfy `SINTER` hash slot constraints; this will be analyzed separately in the Cluster section.

## 7. OR Conditions and Exclusions with `SUNION`, `SDIFF`

Requirement: **"Products in category keyboard or mouse"**:

```redis
SUNION shop:demo:catalog:idx:category:keyboard shop:demo:catalog:idx:category:mouse
```

Result:

```text
{p101, p102, p103}
```

Union deduplicates IDs even when an ID appears in both Sets.

Requirement: **"Keyboard products not belonging to brand=nova"**:

```redis
SDIFF shop:demo:catalog:idx:category:keyboard shop:demo:catalog:idx:brand:nova
```

Result:

```text
{p101}
```

For difference, **Set order matters**:

```text
A - B != B - A
```

`SDIFF A B C` selects members in `A` that are not in `B` and `C`. It does not mean "NOT brand=nova" across the entire system without specifying the **base set** to which the exclusion applies.

Intersection, union, and difference all return **IDs**, not entity payloads or paginated record ordering.

## 8. Spring Data Redis Provides `SetOperations<K,V>`

With `StringRedisTemplate`, you can obtain:

```java
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;

SetOperations<String, String> sets = redis.opsForSet();
```

Basic APIs:

```java
Long added = sets.add(indexKey, "p101", "p103");
Long removed = sets.remove(indexKey, "p103");

Boolean member = sets.isMember(indexKey, "p101");
Long count = sets.size(indexKey);

Set<String> ids = sets.members(indexKey);
```

Mapping to Redis:

| Spring Data Redis | Redis Command |
|---|---|
| `sets.add(key, members...)` | `SADD` |
| `sets.remove(key, members...)` | `SREM` |
| `sets.isMember(key, value)` | `SISMEMBER` |
| `sets.members(key)` | `SMEMBERS` |
| `sets.size(key)` | `SCARD` |
| `sets.intersect(keyA, keyB)` | `SINTER` |
| `sets.union(keyA, keyB)` | `SUNION` |
| `sets.difference(keyA, keyB)` | `SDIFF` |
| `sets.scan(key, options)` | `SSCAN` |

`StringRedisTemplate` stores IDs as UTF-8 strings, which is convenient when multiple applications share Redis. With `RedisTemplate<String, UUID>` or other objects, the configured serializer determines Set member bytes; readers must share the exact same format contract.

Some methods can return `null` inside Redis pipelines/transactions because results are collected later. The Java examples below assume direct synchronous Redis calls outside pipelines and transactions.

## 9. Spring Boot Configuration for Examples

Gradle Groovy DSL dependency for Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

A standalone Redis configuration in `application.yml`:

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

Spring Boot can auto-configure `StringRedisTemplate` and `RedisConnectionFactory` when auto-configuration conditions are met. In the examples, `StringRedisTemplate` is used for both product hashes and index Sets; key naming and serialization are managed explicitly by the application.

When running in Docker Compose or Kubernetes, replace `localhost` with the Redis endpoint reachable from the application. For Redis Cluster, configure `spring.data.redis.cluster.nodes` and respect multi-key operation constraints; a standalone config only illustrates basic access.

## 10. Building the Product Model and Key Generator Class

Simple business data:

```java
package com.example.catalog;

public record Product(
        String id,
        String name,
        String category,
        String brand
) {}
```

Centralizing key definitions in one place prevents typos:

```java
package com.example.catalog;

import java.util.Objects;
import java.util.regex.Pattern;

public final class CatalogRedisKeys {
    private static final String PREFIX = "shop:demo:catalog";
    private static final Pattern SAFE_SEGMENT =
            Pattern.compile("[a-z0-9_-]+");

    private CatalogRedisKeys() {}

    public static String product(String id) {
        return PREFIX + ":product:" + segment(id);
    }

    public static String categoryIndex(String category) {
        return PREFIX + ":idx:category:" + segment(category);
    }

    public static String brandIndex(String brand) {
        return PREFIX + ":idx:brand:" + segment(brand);
    }

    private static String segment(String value) {
        Objects.requireNonNull(value, "Redis key segment");
        if (!SAFE_SEGMENT.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid Redis key segment");
        }
        return value;
    }
}
```

Examples use ID `p101`, category `keyboard`, and brand `acme`, all already normalized. If the domain includes Unicode, `:` characters, or case-sensitive IDs, use appropriate canonicalization/encoding rules rather than mechanically applying this regex.

In production, environment prefixes like `shop:prod`/`shop:staging` should come from deployment configuration. Do not hard-code `prod` across source files and run the same binary across multiple environments sharing Redis.

## 11. Java Service: Writing Primary Data and Updating Index Sets

An illustrative implementation using Redis hashes for primary data and Redis Sets as secondary indexes:

```java
package com.example.catalog;

import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.springframework.data.redis.core.HashOperations;
import org.springframework.data.redis.core.SetOperations;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductIndexStore {

    private final StringRedisTemplate redis;
    private final HashOperations<String, String, String> hashes;
    private final SetOperations<String, String> sets;

    public ProductIndexStore(StringRedisTemplate redis) {
        this.redis = redis;
        this.hashes = redis.opsForHash();
        this.sets = redis.opsForSet();
    }

    public void save(Product p) {
        Objects.requireNonNull(p, "product");
        String productKey = CatalogRedisKeys.product(p.id());
        String categoryKey = CatalogRedisKeys.categoryIndex(p.category());
        String brandKey = CatalogRedisKeys.brandIndex(p.brand());

        // Only for illustrating index updates on standalone Redis.
        String oldCategory = hashes.get(productKey, "category");
        String oldBrand = hashes.get(productKey, "brand");

        hashes.putAll(productKey, Map.of(
                "id", p.id(),
                "name", p.name(),
                "category", p.category(),
                "brand", p.brand()
        ));

        if (oldCategory != null && !oldCategory.equals(p.category())) {
            sets.remove(CatalogRedisKeys.categoryIndex(oldCategory), p.id());
        }
        if (oldBrand != null && !oldBrand.equals(p.brand())) {
            sets.remove(CatalogRedisKeys.brandIndex(oldBrand), p.id());
        }

        sets.add(categoryKey, p.id());
        sets.add(brandKey, p.id());
    }

    public Product find(String id) {
        Map<String, String> row =
                hashes.entries(CatalogRedisKeys.product(id));

        if (row.isEmpty()) {
            return null;
        }

        String name = row.get("name");
        String category = row.get("category");
        String brand = row.get("brand");

        if (name == null || category == null || brand == null) {
            return null;
        }

        return new Product(id, name, category, brand);
    }

    public List<Product> findByCategoryAndBrand(
            String category,
            String brand) {

        Set<String> ids = sets.intersect(
                CatalogRedisKeys.categoryIndex(category),
                CatalogRedisKeys.brandIndex(brand)
        );

        if (ids == null || ids.isEmpty()) {
            return List.of();
        }

        return ids.stream()
                .map(this::find)
                .filter(Objects::nonNull)
                // Filter out stale IDs if primary data changed attributes.
                .filter(p -> category.equals(p.category()))
                .filter(p -> brand.equals(p.brand()))
                .toList();
    }

    public void delete(String id) {
        Product current = find(id);
        if (current == null) {
            return;
        }

        sets.remove(
                CatalogRedisKeys.categoryIndex(current.category()), id);
        sets.remove(
                CatalogRedisKeys.brandIndex(current.brand()), id);
        redis.delete(CatalogRedisKeys.product(id));
    }
}
```

Usage:

```java
store.save(new Product("p101", "Keyboard A", "keyboard", "acme"));
store.save(new Product("p102", "Mouse B", "mouse", "acme"));
store.save(new Product("p103", "Keyboard C", "keyboard", "nova"));

List<Product> selected =
        store.findByCategoryAndBrand("keyboard", "acme");
```

The expected result on stable data is a list containing product `p101`. **Return order is not guaranteed**, because `SINTER` returns a Set, so if an API requires sorting, apply a sort step by business criteria.

> **Important limitation of this example:** `save` and `delete` consist of multiple separate Redis commands, and `save` reads old attributes before writing. Thus this code **does not guarantee atomic updates across primary data and indexes**, nor is it safe against every race across multiple writers. It demonstrates each command's role for learning purposes; subsequent sections present strategies needed in real deployments.

## 12. Keeping Indexes Synchronized When Updating Attributes

Suppose product `p101` initially has:

```text
category = keyboard
brand    = acme
```

Later the category changes to `accessories`. If you only update the hash:

```redis
HSET shop:demo:catalog:product:p101 category accessories
```

Without updating the index:

```text
idx:category:keyboard    -> still contains p101
idx:category:accessories -> missing p101
```

Outcome: searching `keyboard` can return the wrong product (false positive), while searching `accessories` misses the product (false negative).

Updating Sets manually:

```redis
SREM shop:demo:catalog:idx:category:keyboard p101
SADD shop:demo:catalog:idx:category:accessories p101
```

Once both the primary data and the Sets finish updating, the index reflects the new category.

Transition diagram:

```text
BEFORE: category keyboard
  product:p101          -> keyboard
  idx:category:keyboard -> {p101, p103}

ATTRIBUTE CHANGE:
  1. Update primary data to accessories
  2. SREM p101 from keyboard index
  3. SADD p101 into accessories index

AFTER:
  product:p101             -> accessories
  idx:category:keyboard    -> {p103}
  idx:category:accessories -> {p101}
```

However, these three steps do not form an atomic transaction. If the application crashes after step 1, the Set becomes stale. If two writers concurrently edit the category, each writer reading old state and mutating indexes can lose or leave behind members. You cannot solve this completely merely by reordering `SREM` and `SADD`.

## 13. Why Can Primary Data and Indexes Drift Apart?

Common drift scenarios:

| Situation | Consequence |
|---|---|
| Primary write succeeds, adding to Set fails | Record exists, yet attribute search misses it |
| `SADD` succeeds, primary write fails | Set contains an ID whose record is missing |
| Category changes but old index `SREM` is forgotten | Search results include IDs no longer in that category |
| Record deleted without removing from Sets | Index points to a nonexistent record |
| Record has a TTL and expires automatically | Set may still retain the expired ID |
| Two writers update the same ID concurrently | Index state may depend on interleaved command order |
| An index key's TTL expires before primary data | Lookup for an entire group is lost even though records still exist |

Therefore, when high index accuracy is required, maintaining consistency **must be part of the write design**, not an afterthought bolted on later.

### Can You Re-Verify Primary Data at Read Time?

Yes. In `findByCategoryAndBrand`, the service fetches IDs from Set intersection, loads each product, and re-checks `category` and `brand`. This eliminates many false positives from stale indexes. However, it **does not fix false negatives**: an ID missing from the new Set is never retrieved to check, even if the primary record actually matches.

That is the difference between **filtering out wrong results** and **guaranteeing complete index coverage**. If business results cannot omit valid matches, ensure index quality on the write path and build a reconciliation/recovery mechanism.

## 14. Consistent Update Strategies

Several options exist, depending on where primary data lives and your infrastructure:

### 14.1. Atomic Operations on a Single Redis Server

When primary data and related index keys live on the same Redis server, a **Lua script** or an appropriate Redis transaction model can update them together.

A script can accept the record key, old Set keys, new Set keys, and new values, then:

1. Check previous state / expected preconditions.
2. Write primary data fields.
3. Remove the ID from old Sets if needed.
4. Add the ID to new Sets.
5. Return success or conflict status.

Commands inside a Redis Lua script execute atomically at the server command-execution level. Still, **Lua atomicity does not automatically roll back prior writes if the script hits an error mid-way**. Validate inputs and error-prone conditions before writing; keep script runtime short to avoid blocking Redis.

With Redis Cluster, **all keys touched by the script must satisfy hash slot constraints** and be declared/passed through the proper APIs. If primary records and indexes sit in different slots, a single script cannot form an atomic transaction across primary nodes.

### 14.2. Redis Transactions with `WATCH`/`MULTI`/`EXEC`

On standalone Redis, `WATCH` can monitor keys and `MULTI`/`EXEC` can execute a batch of commands if watched keys were not modified concurrently.

However, Spring Data Redis abstracts connections, so using transactions properly requires ensuring dependent commands share **the same connection/transaction context**. Calling multiple template methods under JPA's `@Transactional` does not automatically wrap them into a Redis transaction.

`MULTI`/`EXEC` also differs semantically from SQL transactions: if a queued command fails at execution time, Redis does not roll back other successful commands by default. Design error handling according to Redis semantics.

### 14.3. Primary Data Lives in Another Database

If primary products reside in PostgreSQL/MySQL and Redis Sets are only a fast lookup index, never assume a Redis transaction can commit atomically with a SQL transaction.

A common pattern:

```text
Product update API
    |
    v
SQL transaction updates product
    |
    +--> writes outbox event in the same SQL transaction
              |
              v
        Worker reads outbox
              |
              v
    Redis: updates/rebuilds Set indexes
```

The worker needs retries, idempotency, event version ordering, and error handling. During the sync lag window, the Redis index exhibits **eventual consistency**. If business logic requires strict read-your-writes accuracy immediately after saving, choose an authoritative read path or an appropriate sync-wait policy.

### 14.4. Rebuildable Indexes

Since Sets are derived data, a crucial risk-reduction measure is a **rebuild/reconciliation job**. The job reads the authoritative data source, populates index Sets under a new versioned namespace, verifies counts/samples, and switches readers to the new version. Never assume every update event will always be delivered once and in order.

## 15. Deleting a Record: Which Sets Must Be Cleaned Up?

Deleting product `p101` requires cleaning at least:

```text
product:p101
idx:category:keyboard -> SREM p101
idx:brand:acme        -> SREM p101
```

If the product has multiple tags, such as `gaming` and `wireless`, it is also a member of:

```text
idx:tag:gaming
idx:tag:wireless
```

Thus, when deleting a record, the application needs to know **all indexed attribute values** to remove corresponding memberships. You can read them from the current record prior to deletion, or maintain per-ID metadata/reverse-index references when dynamic index counts grow large.

Example per-product reverse index:

```text
shop:prod:catalog:idx-refs:p101
    -> {
         category:keyboard,
         brand:acme,
         tag:gaming,
         tag:wireless
       }
```

A reverse index helps locate which index Sets to clean up, though it is itself extra state that must be kept consistent. Avoid building a reverse index for a simple model with 2–3 fixed attributes.

When `SREM` removes the last member of a Redis Set, that Set key ceases to exist. If the application later calls `SMEMBERS` on an empty index, the normal outcome is an empty set; there is no need to create empty Redis Set keys as pre-allocated "containers".

## 16. Multi-Valued Indexes: Tags, Roles, Permissions

Not every attribute has a single value. A product can carry multiple tags:

```text
p101: [gaming, wireless]
p102: [wireless]
p103: [gaming]
```

Create a Set per tag:

```redis
SADD shop:demo:catalog:idx:tag:gaming p101 p103
SADD shop:demo:catalog:idx:tag:wireless p101 p102
```

Query products having **both** tags:

```redis
SINTER shop:demo:catalog:idx:tag:gaming shop:demo:catalog:idx:tag:wireless
# {p101}
```

Query products having **at least one** of the two tags:

```redis
SUNION shop:demo:catalog:idx:tag:gaming shop:demo:catalog:idx:tag:wireless
# {p101, p102, p103}
```

If `p101` drops the `gaming` tag, run:

```redis
SREM shop:demo:catalog:idx:tag:gaming p101
```

If you only `SADD` new tags without diffing old vs. new tags, the index gradually accumulates invalid memberships.

The same applies to user roles, articles in topics, labeled documents, or orders with multiple sub-statuses. For roles/permissions, Set indexes are merely lookup data; **do not replace authorization checks against the authoritative source by blindly trusting a potentially stale index**.

## 17. Limitations of Using `SMEMBERS` to Load the Entire Set

`SMEMBERS key` returns **all** Set members. For a Set of a few dozen IDs, this is simple. For a Set of millions of IDs, returning everything can cause:

- Redis having to read and transmit huge payloads.
- Network bandwidth and JVM memory spikes.
- Increased request latency, especially when many requests query the same Set.
- No stable ordering for offset pagination.

`SMEMBERS` complexity scales with the number of returned members (commonly expressed as **O(N)**). In Spring Data Redis, `sets.members(indexKey)` constructs a Java `Set<String>`, so the application must have enough heap to hold the result.

### `SSCAN` for Incremental Traversal

Redis provides `SSCAN`. In Spring Data Redis:

```java
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import java.util.ArrayList;
import java.util.List;

public List<String> firstUpTo(
        StringRedisTemplate redis,
        String indexKey,
        int limit) {

    if (limit <= 0) {
        return List.of();
    }

    List<String> result = new ArrayList<>(limit);

    try (Cursor<String> cursor = redis.opsForSet().scan(
            indexKey,
            ScanOptions.scanOptions().count(100).build())) {

        while (cursor.hasNext() && result.size() < limit) {
            result.add(cursor.next());
        }
    }

    return result;
}
```

`count(100)` is only a **hint** for how many elements to process per scan pass, not a guarantee Redis always returns 100 elements. `SSCAN` can return duplicate members during a scan, and if the Set mutates concurrently, some results may be skipped or appear additionally. Therefore, **`SSCAN` does not provide a consistent snapshot or stable page-numbered pagination**.

If you need a stable list sorted by creation date, price, or ranking score, consider adding a **Sorted Set**, another query layer, or a dedicated search engine instead of trying to force `SMEMBERS`/`SSCAN` into ordered pagination.

## 18. Optimizing Multi-Condition Queries

Suppose:

```text
idx:category:keyboard -> 500,000 IDs
idx:brand:acme        -> 2,000 IDs
idx:status:active     -> 10,000,000 IDs
```

If all three conditions are required, logically you can use `SINTER` across the Sets. However, processing huge Sets—especially in Cluster—can be slow/network-heavy or impossible in a single native cross-slot command.

An alternative strategy:

1. Check `SCARD` on the relevant Sets.
2. Pick the Set with the fewest members as the **candidate set**.
3. Iterate candidate IDs and check remaining conditions with `SISMEMBER`.
4. Read primary records and re-verify attributes before returning.

For instance, `brand=acme` has only 2,000 IDs, so using it as the candidate set drastically reduces the IDs fetched and checked compared to pulling all 10 million active IDs.

This is an **application-layer** strategy, not a transactional snapshot. Between `SCARD`, `SSCAN`, and `SISMEMBER`, data can change. When strictly consistent results are required, design a synchronization/versioning mechanism or read from the authoritative source.

### Typical Complexities

| Command | General Cost Characteristics |
|---|---|
| `SADD` / `SREM` single member | Average O(1) per member |
| `SISMEMBER` | Average O(1) |
| `SCARD` | O(1) |
| `SMEMBERS` | O(N), where N is returned members |
| `SINTER` | Depends on number of Sets and members scanned/matched |
| `SUNION` / `SDIFF` | Depends on total elements and number of Sets |
| `SSCAN` | Incremental traversal; total cost depends on full scan and member count |

Actual cost is also influenced by ID size, index count, network speed, client concurrency, Redis CPU, and JVM deserialization overhead. Do not rely on Big-O alone to predict production latency; benchmark with realistic data and cardinalities.

## 19. Redis Cluster: `SINTER` Across Sets Can Trigger `CROSSSLOT`

Redis Cluster distributes keys across **16,384 hash slots**. Multi-key Redis commands such as `SINTER`, `SUNION`, and `SDIFF` require participating keys to reside in the **same hash slot** to run as a native Cluster command.

These key names share a prefix:

```text
shop:prod:catalog:idx:category:keyboard
shop:prod:catalog:idx:brand:acme
```

Yet `:` and the prefix `shop:prod:catalog:` **do not guarantee the same slot**. Consequently:

```redis
SINTER shop:prod:catalog:idx:category:keyboard shop:prod:catalog:idx:brand:acme
```

may be rejected in Redis Cluster with a `CROSSSLOT` error.

### 19.1. Hash Tags: Same Slot When Multi-Key Commands Are Needed

Redis Cluster supports hash tags via curly braces. If you write:

```text
shop:prod:catalog:{catalog-index}:idx:category:keyboard
shop:prod:catalog:{catalog-index}:idx:brand:acme
```

then both keys compute their slot from `catalog-index`, allowing `SINTER` to run in the same slot.

However, this carries a **major trade-off**: every index sharing that hash tag is forced into **one slot**, owned by one primary node at a time. If the index set is large and heavily queried, it becomes a hotspot; such a design can negate Cluster's data distribution benefits.

Do not apply a single global hash tag across the whole application just to make every multi-key command work.

### 19.2. When Indexes Span Multiple Slots

You can use an application-layer strategy:

```text
1. Fetch candidate IDs from a selective Set.
2. For each ID, check membership in the other Sets via SISMEMBER.
3. Only fetch primary product records for candidates passing all checks.
4. Re-verify actual attributes and handle stale results.
```

Each `SISMEMBER` targets **one key**, so a Cluster-aware driver routes it to the appropriate slot. In return, command count rises, RTT/pipelining must be considered, and there is no atomic cross-node snapshot.

If you need frequent dynamic AND/OR queries over large datasets with ordering/pagination, a dedicated search/indexing system may fit better than cramming many Redis Sets into one slot.

### 19.3. Multi-Key Updates Are Also Restricted

A Lua script or Redis transaction updating a product hash and multiple index Sets simultaneously must obey slot constraints. If the primary record and secondary indexes live in different slots, **an atomic Redis transaction spanning the whole Cluster is impossible** using `MULTI` or Lua alone.

In Cluster deployments, explicitly choose a strategy: accept eventual consistency for indexes with reconciliation, confine atomic operations within a single slot, or use a data system with richer query/transaction support.

## 20. TTL: Index Sets and Primary Data Do Not Expire Together

Redis TTLs are set on **the entire Set key**, not on individual members. Example:

```redis
EXPIRE shop:demo:catalog:idx:category:keyboard 600
```

After 600 seconds, the entire index Set disappears, not just the oldest ID.

If primary records have a 5-minute TTL while the index Set has no TTL:

```text
product:p101 expires
idx:category:keyboard still contains p101
```

The index now holds a **dangling reference** to a product that no longer exists.

Conversely, if the index Set key expires before primary records expire:

```text
idx:category:keyboard expires
product:p101 still exists
```

Queries by category can **miss an entire group**, even though primary records are still intact.

### TTL Policies Should Reflect Data Semantics

- For indexes acting as **lookup structures for durable data**, do not put arbitrary short TTLs on index Sets; update membership on every record add/delete.
- For indexes derived from **TTL-cached records**, build a strategy to align expirations, repair stale indexes, and recover missing indexes.
- For temporary index sets used in a report or query session, a TTL can make sense; ensure readers recognize it as ephemeral data.
- If `SREM` removes the last member, Redis deletes the Set key. When `SADD` recreates it later, the old TTL is not restored automatically.

Redis keyspace notifications can help listen for expiration events when configured, yet they are **not a durable event log guaranteed never to drop events**. Workers can go offline, events are not buffered for replay like a durable queue, or notifications may not be enabled. Never rely solely on expiry events as the only safeguard for critical index accuracy.

## 21. Materializing Set Intersection Results with `SINTERSTORE`

Sometimes a query runs repeatedly with the same filter set. Redis provides a command to save intersection results into another Set:

```redis
SINTERSTORE shop:demo:catalog:tmp:keyboard-acme shop:demo:catalog:idx:category:keyboard shop:demo:catalog:idx:brand:acme
```

The destination key `tmp:keyboard-acme` stores the result set as of command execution time. Redis also provides `SUNIONSTORE` and `SDIFFSTORE` with analogous semantics for union and difference.

This is a **point-in-time materialization**, not a self-updating view. After a product changes brand, the temporary Set **does not auto-sync** with the two source Sets.

If the result is only needed briefly, attach a TTL:

```redis
EXPIRE shop:demo:catalog:tmp:keyboard-acme 60
```

Two separate `SINTERSTORE` and `EXPIRE` commands leave a gap between them; if TTL must be guaranteed atomically, design accordingly.

In Redis Cluster, the destination key and all source keys of `SINTERSTORE` must satisfy the same-slot rule. Moreover, materializing many large results increases memory usage; enforce cleanup policies and cap temporary result sets.

## 22. When to Use Redis Repository `@Indexed`?

Spring Data Redis Repositories provide entity mapping to Redis and can support **secondary indexes via metadata/annotations like `@Indexed`** for supported repository queries.

This is a separate path from manually using `StringRedisTemplate.opsForSet()`:

| Self-Managed Set Index | Repository-Managed Index |
|---|---|
| Application chooses index keys and member IDs | Framework applies repository mapping/index conventions |
| Application writes `SADD`, `SREM`, Set combinations | Repository manages indexes on save/delete according to its mechanism |
| Application queries via `SINTER`/`SISMEMBER` | Queries go through repository methods for indexed properties |
| Must handle all write paths that could bypass indexes | Still must use repository paths consistently and understand updates/expiry |
| Fits direct `RedisTemplate` usage or custom key rules | Fits application models structured around Spring Data Redis Repositories |

Conceptual example with a repository entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.index.Indexed;

@RedisHash("products")
public class ProductEntity {
    @Id
    private String id;

    @Indexed
    private String category;

    private String name;

    // Appropriate constructor, getters/setters...
}
```

When using Redis Repositories, metadata on `category` can be used to maintain an index and support querying by category where supported by Spring Data Redis. Do not assume arbitrary complex query expressions, full-text search, sorting, or pagination are all automatically translated into optimal indexes by Redis Repositories.

**Important:** Repository indexes use key structures and metadata managed by the framework. Do not manually run `SREM`/`SADD` against repository internal keys just because you recognize them as Redis Sets. Likewise, do not expect modifying data via `RedisTemplate` outside the repository to automatically update repository indexes.

This lesson focuses on **manually building secondary indexes with Redis Sets** to understand the underlying mechanics. When a project already uses repositories, define clearly who owns the index so two mechanisms do not maintain the same truth differently.

## 23. Reconciling and Rebuilding Indexes

A long-lived system will encounter process crashes, network failures, multi-version deployments, TTL changes, or schema updates. Therefore, plan how to verify indexes do not drift permanently.

Discrepancies to detect:

1. **Dangling IDs:** Set contains `p101` while the primary record does not exist.
2. **Wrong membership:** Set `category:keyboard` holds an ID whose primary record now has `category=mouse`.
3. **Missing membership:** primary record has `category=keyboard` yet the Set lacks its ID.
4. **Orphan indexes:** an index key for a retired category still lingers with many IDs.
5. **Version drift:** an older app version still writes indexes under an old namespace or serializer.

Example rebuild flow from the authoritative data source:

```text
Authoritative data source (SQL or canonical product store)
        |
        v
Iterate all products in batches
        |
        v
Build new Sets:
    idx:v2:category:keyboard
    idx:v2:brand:acme
    ...
        |
        v
Reconcile counts, sample memberships, and update stream
        |
        v
Switch readers to v2 index namespace per deployment strategy
        |
        v
Stop v1 index writers and clean up v1 per procedure
```

Avoid rebuilding by deleting live index keys serving traffic and repopulating from scratch if losing results mid-rebuild is unacceptable. Build into a **new namespace**, then switch reader configuration/version in a controlled way.

If new writes occur during a rebuild, add a catch-up mechanism: event log/outbox, controlled dual-write, or a brief write pause during cutover. Otherwise, the freshly rebuilt index may already miss updates that happened during the scan.

Checking `SCARD` on index Sets is a useful operational signal, yet **does not prove index correctness**. Two sets with the exact same member count can contain completely different IDs. Reconciling actual membership against primary data is what uncovers content drift.

## 24. Security and Multi-Tenant Boundaries

In multi-tenant systems, include the tenant in the namespace:

```text
shop:prod:t27:catalog:idx:category:keyboard
shop:prod:t91:catalog:idx:category:keyboard
```

Those Sets hold IDs scoped only to their respective tenants. However, the tenant ID must come from the request's authenticated/authorized context—never let clients pick another tenant arbitrarily via a parameter.

An index Set can leak **the existence of objects** if unauthorized callers can read members. Redis ACLs can restrict which key patterns a credential may access; business-level authorization checks are still mandatory before returning data to users.

A prefix like `t27` does not create a security boundary by itself. Applications sharing broad Redis credentials can still read another tenant's Set if application code fails to enforce isolation.

If a user is allowed to query `category=keyboard` yet may only view a subset of products, fetching all IDs from the index and returning them externally is a bug. Combine access filters at the appropriate layer, design indexes matching safe access policies, or re-verify permissions on each fetched record.

## 25. Redis Set Indexes vs. Other Approaches

| Requirement | Redis Set Index | Alternative That May Fit Better |
|---|---|---|
| Exact-match ID lookup on one attribute | Very suitable | Database index if primary data lives in SQL |
| AND/OR across a few small groups | `SINTER`/`SUNION` convenient | Database/search engine query planner for complex combinations |
| Check if an ID belongs to a group | Fast `SISMEMBER` | Primary record lookup when strict accuracy is mandatory |
| Sort by price, score, creation date | Sets are unordered | Redis Sorted Set or database ORDER BY |
| Stable pagination over millions of results | Sets lack stable order | Cursor on an appropriate database/search index |
| Full-text search, prefix, fuzzy, ranking | Hard to scale manually with Sets | Dedicated search engine or Redis Search when supported |
| Multi-condition queries across Cluster slots | Native multi-key commands restricted | Client-side filtering, intentional slot layout, or another query system |
| Atomic primary + index updates across SQL + Redis | Not supported natively | Outbox/event-driven sync and reconciliation; DB as source of truth |

Set indexes fit well when the application knows upfront which few attributes to index, most queries are membership checks or set combinations, and index maintenance costs are understood and managed.

If you need dozens of dynamic filter fields, multi-column sorting, stable pagination, complex aggregations, and concurrent transactions, reconsider building a hand-rolled query engine out of Sets.

## 26. Hands-On Practice with the Redis CLI

Commands in this section write test data under the prefix `demo:lesson141:`. Run them only on a Redis instance permitted for practice, never on a system holding important data without approval.

### Step 1 — Create Three Records

```bash
redis-cli HSET demo:lesson141:product:p101 id p101 name "Keyboard A" category keyboard brand acme
redis-cli HSET demo:lesson141:product:p102 id p102 name "Mouse B" category mouse brand acme
redis-cli HSET demo:lesson141:product:p103 id p103 name "Keyboard C" category keyboard brand nova
```

### Step 2 — Build Secondary Indexes with Sets

```bash
redis-cli SADD demo:lesson141:idx:category:keyboard p101 p103
redis-cli SADD demo:lesson141:idx:category:mouse p102
redis-cli SADD demo:lesson141:idx:brand:acme p101 p102
redis-cli SADD demo:lesson141:idx:brand:nova p103
```

### Step 3 — Search and Check Membership

```bash
redis-cli SISMEMBER demo:lesson141:idx:category:keyboard p101
redis-cli SCARD demo:lesson141:idx:category:keyboard
redis-cli SMEMBERS demo:lesson141:idx:category:keyboard

redis-cli SINTER demo:lesson141:idx:category:keyboard demo:lesson141:idx:brand:acme
redis-cli SUNION demo:lesson141:idx:category:keyboard demo:lesson141:idx:category:mouse
redis-cli SDIFF demo:lesson141:idx:category:keyboard demo:lesson141:idx:brand:nova
```

Expected output:

```text
SISMEMBER keyboard p101 -> 1
SCARD keyboard          -> 2
SINTER keyboard acme    -> {p101}
SUNION keyboard mouse   -> {p101, p102, p103}
SDIFF keyboard nova     -> {p101}
```

The order of IDs printed by `SMEMBERS`, `SINTER`, `SUNION`, or `SDIFF` may vary across runs and must not be used to infer ranking.

### Step 4 — Change Category and Update Indexes

```bash
redis-cli HSET demo:lesson141:product:p101 category accessories
redis-cli SREM demo:lesson141:idx:category:keyboard p101
redis-cli SADD demo:lesson141:idx:category:accessories p101

redis-cli SISMEMBER demo:lesson141:idx:category:keyboard p101
redis-cli SISMEMBER demo:lesson141:idx:category:accessories p101
```

Expected final result:

```text
keyboard     -> 0
accessories  -> 1
```

If you only run `HSET` without running `SREM`/`SADD`, the Set index does not automatically update to match the category field in the Redis hash. That is the core takeaway of this exercise.

### Step 5 — Inspect Redis Type and TTL

```bash
redis-cli TYPE demo:lesson141:product:p101
# hash

redis-cli TYPE demo:lesson141:idx:category:accessories
# set

redis-cli TTL demo:lesson141:idx:category:accessories
# -1 when the key exists with no expiry attached
```

To repeat the exercise, use a fresh test ID/prefix or clean up only the created keys using approved commands. Do not use `FLUSHDB` to reset a shared Redis server.

## 27. Self-Check Questions

**1. Why do Set indexes normally store IDs instead of full objects?**

Because storing IDs avoids duplicating payloads across multiple indexes. On query, the application fetches IDs and then reads primary records; updating a single field does not force updating multiple JSON copies across Sets.

**2. If `SADD key p101` is called twice, will the Set contain two `p101` entries?**

No. A Redis Set holds each member at most once. The second `SADD` returns 0 because no new member was added.

**3. Which Set operation finds products belonging to both category keyboard and brand acme?**

Use intersection `SINTER` between `idx:category:keyboard` and `idx:brand:acme` when topology/slot rules permit.

**4. Changing a product's category from keyboard to mouse by updating only the hash causes what error?**

The old index retains the ID (false positive), while the new index misses the ID (false negative). Membership must be updated alongside attribute changes.

**5. Is `SMEMBERS` suitable for a paginated API sorted by creation date?**

No. Sets have no guaranteed order; `SMEMBERS` returns the whole Set, and `SSCAN` is an incremental traversal rather than a stable snapshot. Use an ordered data structure/sorted index when needed.

**6. Why can `SINTER` fail with `CROSSSLOT` in Redis Cluster?**

Because the Set keys fall into different hash slots. Sharing a key prefix does not guarantee the same slot; hash tags can place keys in the same slot, at the risk of creating hotspots.

**7. A primary record has a 5-minute TTL, while the index Set has no TTL. What happens after the record expires?**

The Set can still hold the ID of the vanished record. An index cleanup policy or rebuild/reconciliation job is needed; Redis does not remove Set members based on another key's TTL.

**8. Do Redis Repository `@Indexed` and manually written Set indexes stay in sync automatically?**

Do not assume so. Repositories manage indexes via their own mapping conventions, while `RedisTemplate.opsForSet()` executes whatever Set commands the application sends. Define index ownership and write paths clearly.

**9. Does re-checking a record's category after reading IDs from the Set fix all index errors?**

No. It filters out false positives, yet cannot recover IDs omitted from the new index Set (false negatives).

## 28. Conclusion

Building secondary indexes with Redis Sets means **mapping an attribute value to a set of matching record IDs**. In Spring Data Redis, `SetOperations` provides the foundational tools: `add`/`remove` to maintain indexes, `isMember` to check membership, `members`/`scan` to inspect entries, and `intersect`/`union`/`difference` to combine search conditions.

Most importantly, treat secondary indexes as **derived data with their own lifecycle**. Every record creation, attribute change, deletion, and expiration can cause indexes to drift from primary data unless synchronization is designed upfront. For critical data, control concurrent writes, provide retries/reconciliation, and support rebuilding. In Redis Cluster, account for hash slots across every multi-key operation and weigh co-location against load distribution. When these limits are well understood, Set indexes are a simple, effective way to add attribute-based lookup to Spring Data Redis applications.
