# Reactive Repository Limitations and Template Alternatives in Spring Data Redis

> **Module:** Spring Data Redis  
> **Chapter:** Reactive Redis (*Reactive Redis*)  
> **Lesson:** Distinguish imperative Redis Repository support from reactive Redis APIs, understand why `CrudRepository` cannot simply be swapped for `ReactiveCrudRepository`, and design with `ReactiveRedisTemplate`/`ReactiveStringRedisTemplate` without misconceptions about mapping, TTLs, indexes, transactions, or network errors.

## 1. Context: Why Discuss Reactive Redis Repositories Separately?

A Spring WebFlux application commonly uses `Mono<T>` and `Flux<T>` to handle many I/O-bound requests without dedicating a waiting thread per request. Redis may store caches, sessions, tokens, rate limits, counters, or real-time data structures.

Spring Data Redis provides both **imperative** and **reactive** Redis access APIs. Yet not every imperative feature has an equivalent reactive counterpart.

Example of an imperative Repository:

~~~java
import org.springframework.data.repository.CrudRepository;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.annotation.Id;

@RedisHash("products")
public class ProductRedisEntity {
    @Id
    private String id;
    private String name;
    // Constructor, getters, setters...
}

public interface ProductRedisRepository
        extends CrudRepository<ProductRedisEntity, String> {
}
~~~

This repository provides operations such as `save`, `findById`, and `deleteById` synchronously. When the repository accesses Redis, the calling thread waits for the I/O operation to complete.

Another declaration looks tempting:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface ReactiveProductRedisRepository
        extends ReactiveCrudRepository<ProductRedisEntity, String> {
}
~~~

**You must not assume the second interface works as a Redis Repository.** Across Spring Data Redis releases documented with Reactive Redis support, **Redis repositories do not have equivalent reactive repository support**. The existence of `ReactiveCrudRepository` in Spring Data Commons **does not mean** the Spring Data Redis module builds reactive repository proxies for Redis.

If you want true reactive Redis access, the direct choices are:

- `ReactiveRedisTemplate<K, V>`.
- `ReactiveStringRedisTemplate`, optimized for String keys and values.
- `ReactiveRedisOperations<K, V>` for programming to an interface.
- Reactive Redis connections or scripting/Streams APIs when lower-level control is required.

This **does not mean Redis only supports blocking APIs**. On the contrary, Reactive Redis Template sends commands over a non-blocking driver; the gap lies in the **repository abstraction layer**, not in the Redis server's ability to process commands.

## 2. Three Layers to Distinguish

### 2.1. Spring Data Commons

Spring Data Commons defines shared interfaces such as:

- `Repository<T, ID>`.
- `CrudRepository<T, ID>`.
- `PagingAndSortingRepository<T, ID>`.
- `ReactiveCrudRepository<T, ID>`.
- `ReactiveSortingRepository<T, ID>`.

These interfaces are only general programming contracts. For a working implementation to exist, **a specific Spring Data store module** must provide the repository factory, mapping layer, query execution, and store-specific operations.

For instance, Reactive MongoDB Repositories and R2DBC Repositories provide reactive repository implementations, yet you must not infer that every datastore module offers the same support.

### 2.2. Spring Data Redis Repository

Redis Repositories use entity mapping to store objects as Redis Hashes. An entity can use:

- `@RedisHash` for keyspace and default TTL.
- `@Id` for the identifier.
- `@TimeToLive` for lifetime management.
- `@Indexed` for secondary indexes and supported finder methods.
- `RedisConverter`, mapping context, and Spring Data metadata.
- Key expiration event mechanisms to clean up secondary indexes.

This is a **higher-level feature layer** beyond running `SET`/`GET` against Redis.

### 2.3. Spring Data Redis Reactive Template

The Reactive Template focuses on **Redis operations** returning Reactor publishers:

~~~java
Mono<String> value = reactiveRedisTemplate
        .opsForValue()
        .get("cache:product:101");
~~~

With `ReactiveRedisTemplate`, the application owns key schemas, data formats, TTLs, indexes, and error logic. The template does not become a full Redis Repository with query derivation and entity mapping just because it returns `Mono` or `Flux`.

### 2.4. Boundary diagram

~~~mermaid
flowchart TD
    APP["WebFlux / Reactive service"] --> CHOICE{"Data access choice"}
    CHOICE --> R["ReactiveCrudRepository"]
    CHOICE --> T["ReactiveRedisTemplate / ReactiveStringRedisTemplate"]
    CHOICE --> I["Imperative Redis CrudRepository"]
    R --> STORES["Store modules with reactive repository implementations, e.g. R2DBC"]
    T --> OPS["ReactiveRedisOperations"]
    OPS --> FACTORY["ReactiveRedisConnectionFactory"]
    FACTORY --> DRIVER["Non-blocking Redis driver, typically Lettuce"]
    DRIVER --> REDIS["Redis server"]
    I --> BLOCK["Imperative Repository + Redis mapping"]
    BLOCK --> REDIS
    R -. "Does not automatically create a reactive Redis repository" .-> REDIS
~~~

Before choosing an API, ask: **does the application need reactive Redis commands, or does it also need repository entity mapping/query abstraction?** Those are two different requirements.

## 3. Imperative Repositories Are Not Equivalent to ReactiveRedisTemplate

| Capability | Imperative Redis Repository | ReactiveRedisTemplate |
|---|---|---|
| API style | `CrudRepository`, find-by-id, supported derived queries | Reactive Redis commands |
| Return types | Object/`Optional`/`Iterable`, synchronous | `Mono`/`Flux`, asynchronous |
| Entity mapping with `@RedisHash` | Yes | Not automatic like a repository |
| Key generation from id/keyspace | Yes, per mapping | Application designs keys |
| Secondary indexes via `@Indexed` | Yes, within repository support | Must maintain manually if desired |
| `@TimeToLive` on entity | Yes, per mapping | Does not inspect POJO annotations |
| Index-based finders | Yes, per repository support | Write explicit Redis commands/query model |
| Key expiration handling | Dedicated repository mechanism | Application subscribes/designs if needed |
| Redis Hash mapping | Yes | Has `opsForHash()`, requires explicit map/serializer |
| Native Redis types/counters/lists/sets/streams | Not the primary focus | Provides dedicated operation groups |
| Reactor-style non-blocking I/O | No | Yes, with suitable connection factory/driver |
| Automatic multi-key transaction guarantees | No | No |
| `ReactiveTransactionManager` committing DB and Redis together | No | Not automatic |

**Important caveat:** "Yes" in the Repository column means within Spring Data Redis's mapping and repository scope; not every SQL/JPA query feature exists for Redis. "Yes" in the Template column means providing appropriate Redis operations, not that every command behaves identically across all driver versions.

## 4. Why Cannot You Simply Switch extends to ReactiveCrudRepository?

Spring can generate a Repository implementation only when a store module supplies:

1. A **repository factory** that understands how to identify Redis entities.
2. A **mapping layer** converting entities to and from Redis Hashes.
3. **Query execution** handling IDs, criteria, and derived finders.
4. A **reactive execution model** backed by reactive Redis connections.
5. **Lifecycle/TTL/index management** integrated with reactive pipelines.

`ReactiveCrudRepository` merely defines a contract in Spring Data Commons. It never generates a Redis implementation by itself.

### 4.1. Possible outcomes when declared anyway

If you declare:

~~~java
public interface ReactiveProductRepository
        extends ReactiveCrudRepository<ProductRedisEntity, String> {
}
~~~

without a store module claiming the interface, startup may fail or misbehave by:

- Creating no repository bean.
- Throwing an injection failure for the missing bean.
- Failing Spring Data repository scanning when multiple modules exist without clear store assignment.
- Getting picked up by **another** module if entities/packages/configurations are not strictly separated.

Do not rely on memorizing one exact exception message, as messages change across Spring Data versions and scanning configurations.

### 4.2. Why does wrapping in Mono not solve it?

Example:

~~~java
public Mono<ProductRedisEntity> find(String id) {
    return Mono.justOrEmpty(repository.findById(id));
}
~~~

`repository.findById(id)` **already executed before** `Mono.justOrEmpty(...)` returned; the calling thread still blocked. This is not native reactive I/O.

Even with:

~~~java
public Mono<ProductRedisEntity> find(String id) {
    return Mono.fromCallable(() -> repository.findById(id))
            .flatMap(Mono::justOrEmpty);
}
~~~

`findById` is deferred until subscription, yet **still blocks** whichever thread executes the callable. Distinguish **lazy execution** (*lazy*) from **non-blocking I/O** (*non-blocking*).

## 5. Primary Alternative: ReactiveRedisTemplate

Spring Data Redis provides:

- `ReactiveRedisOperations<K,V>`: interface for reactive Redis operations.
- `ReactiveRedisTemplate<K,V>`: general-purpose implementation.
- `ReactiveStringRedisTemplate`: template for string data, often convenient with explicit JSON encoding.
- `ReactiveRedisConnectionFactory`: factory issuing reactive Redis connections.
- `ReactiveValueOperations`, `ReactiveHashOperations`, `ReactiveListOperations`, `ReactiveSetOperations`, and other operation groups.

### 5.1. Typical commands

~~~java
Mono<String> read =
        redis.opsForValue().get("products:101");

Mono<Boolean> write =
        redis.opsForValue().set(
                "products:101", "json-payload",
                Duration.ofMinutes(10));

Mono<Long> deleted =
        redis.delete("products:101");

Mono<Boolean> exists =
        redis.hasKey("products:101");

Mono<Duration> remaining =
        redis.getExpire("products:101");
~~~

Here `redis` is `ReactiveStringRedisTemplate`. Signatures illustrate common usage; consult your project's Spring Data Redis version for advanced overloads.

Difference from the imperative API: every operation returns `Mono` or `Flux`. To execute, it must be subscribed to by the framework (e.g., WebFlux) or a valid subscriber. Never call `block()` on the Netty event-loop.

### 5.2. Choosing the driver

Spring Data Redis Reactive support is typically paired with **Lettuce** and `LettuceConnectionFactory`, which provide non-blocking/reactive Redis access. Never assume that having Jedis/imperative `RedisTemplate` implies equivalent reactive support.

Even with a non-blocking client, the Redis server still faces CPU, memory, network, and connection limits. Reactive I/O reduces waiting threads on the application side; **it does not make Redis commands "free."**

### 5.3. What the Template does not create automatically

When calling:

~~~java
redis.opsForValue().set("products:101", json);
~~~

the Template has no awareness of:

- Whether `products:101` belongs to a `@RedisHash("products")` keyspace.
- Whether `101` is an entity `@Id`.
- Whether the ID must be added to a secondary index like `products:name:Desk`.
- Whether a phantom copy is needed for expiration events.
- Whether to read-through a database when the key is missing.
- How long the value should live if you omit a TTL.
- Which Redis Hash field maps to a Java property.

These become **the application's responsibility** once you step outside the repository abstraction.

## 6. Configuring Spring Boot for Reactive Redis

### 6.1. Dependencies

With Spring Boot using Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.boot:spring-boot-starter-data-redis-reactive")
}
~~~

Some Spring Boot projects already pull the corresponding transitive dependencies, yet listing these clarifies use of the Reactive Redis starter. Keep versions managed by Spring Boot dependency management; avoid mixing standalone Spring Data Redis versions arbitrarily.

### 6.2. Application configuration

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

If Redis requires ACLs, TLS, Cluster, or Sentinel, configure the matching connection properties for your infrastructure. Never hard-code passwords or tokens inside source code or deployment examples.

### 6.3. Injecting ReactiveStringRedisTemplate

~~~java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class GreetingStore {

    private final ReactiveStringRedisTemplate redis;

    public GreetingStore(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Boolean> save(String userId, String greeting) {
        return redis.opsForValue().set(
                "greetings:" + userId, greeting);
    }

    public Mono<String> read(String userId) {
        return redis.opsForValue().get("greetings:" + userId);
    }
}
~~~

In a WebFlux application, a controller can return `Mono<String>` directly. WebFlux subscribes at the HTTP boundary, so the service does not call `subscribe()`.

~~~java
@RestController
@RequestMapping("/greetings")
public class GreetingController {

    private final GreetingStore store;

    public GreetingController(GreetingStore store) {
        this.store = store;
    }

    @GetMapping("/{userId}")
    public Mono<String> greeting(@PathVariable String userId) {
        return store.read(userId);
    }
}
~~~

This controller example only illustrates wiring. When a key does not exist, `Mono.empty()` should be converted by the controller into HTTP 404 or another API-contract response; WebFlux does not automatically assume "cache miss = 404" for every system.

## 7. Replacing Repositories with Templates: Key and Serializer Design

Consider an earlier imperative entity:

~~~java
@RedisHash(value = "products", timeToLive = 600)
public class ProductRedisEntity {

    @Id
    private String id;

    @Indexed
    private String category;

    private String name;
}
~~~

Redis Repository manages IDs, Hash mapping, TTLs, and secondary indexes according to internal conventions. Moving to `ReactiveStringRedisTemplate` with JSON Strings requires **designing your own schema**:

~~~text
Key:
  app:products:v1:p-101

Value JSON:
  {
    "id": "p-101",
    "category": "furniture",
    "name": "Adjustable Desk"
  }

TTL:
  600 seconds on write
~~~

### 7.1. Why not write directly to the Repository's old keys?

Repositories may store entities as Redis Hashes along with index Sets and metadata. If `ReactiveStringRedisTemplate` overwrites that exact key with a Redis String:

- The Redis data type flips from `hash` to `string`.
- Any Repository still reading the Hash throws `WRONGTYPE`.
- Index Sets retain dangling references.
- TTLs and expiration cleanup stop behaving as expected.
- Auxiliary keys managed by the Repository become orphaned.

Therefore, **never assume data can be shared seamlessly between Redis Repositories and Reactive Templates using the exact same key layout**. Separate namespaces and plan a proper migration.

### 7.2. Choose an explicit serializer

Two directions:

**Option A: `ReactiveStringRedisTemplate` + explicit JSON Strings.**

- Keys are UTF-8 strings.
- Values are JSON strings serialized via Jackson/`ObjectMapper`.
- The application controls schema and versioning.
- Easier interoperability with non-Java services.

**Option B: `ReactiveRedisTemplate<K,V>` with a custom `RedisSerializationContext`.**

- The template serializes keys and values automatically.
- Can use Jackson serializers or codecs matching your Spring Data Redis version.
- Must align across all writers/readers and manage versioning.

For Option B, `RedisSerializationContext<K,V>` is central. It specifies serialization pairs for key, value, hash key, and hash value, and must stay consistent across read/write paths. Avoid uncontrolled default binary serializers for long-lived or multi-service data.

### 7.3. Prefix and version conventions

Example:

~~~text
cache:products:v1:p-101
cache:products:v1:p-102
views:product:p-101
rate-limit:user:u-123
~~~

Do not dump all data under one generic prefix and delete via wildcards in production Redis. Partition keyspaces by feature, ownership, and TTL lifecycle.

When changing serializers or schemas:

~~~text
cache:products:v1:p-101 -> old format
cache:products:v2:p-101 -> new format
~~~

Including a version in the prefix prevents new consumers from trying to deserialize legacy payloads with a new codec. `v1` keys can expire via TTL or be cleaned up during migration.

## 8. Complete Example: Reactive Cache-Aside with JSON and TTL

Problem: fetch product information from a reactive data source. Serve from Redis if cached; on a cache miss, query the source, serialize to JSON, and store in Redis with a 10-minute TTL.

### 8.1. Define the DTO and data source

~~~java
// File ProductView.java
public record ProductView(
        String id,
        String name,
        long priceMinor,
        String currency) {
}
~~~

~~~java
// File ReactiveProductSource.java
import reactor.core.publisher.Mono;

public interface ReactiveProductSource {
    Mono<ProductView> findById(String id);
}
~~~

`ReactiveProductSource` is an **application-defined interface**. Its implementation can use an R2DBC Repository, Reactive MongoDB Repository, WebClient, or any suitable non-blocking source. It is not a Redis reactive repository.

### 8.2. Reactive cache service

~~~java
import java.time.Duration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveProductCache {

    private static final Duration TTL = Duration.ofMinutes(10);

    private final ReactiveStringRedisTemplate redis;
    private final ReactiveProductSource source;
    private final ObjectMapper mapper;

    public ReactiveProductCache(
            ReactiveStringRedisTemplate redis,
            ReactiveProductSource source,
            ObjectMapper mapper) {
        this.redis = redis;
        this.source = source;
        this.mapper = mapper;
    }

    public Mono<ProductView> findById(String id) {
        String key = "cache:products:v1:" + id;

        return redis.opsForValue()
                .get(key)
                .flatMap(json -> Mono.fromCallable(
                        () -> mapper.readValue(
                                json, ProductView.class)))
                .switchIfEmpty(Mono.defer(
                        () -> loadAndCache(id, key)));
    }

    private Mono<ProductView> loadAndCache(
            String id, String key) {

        return source.findById(id)
                .flatMap(product ->
                        Mono.fromCallable(
                                () -> mapper.writeValueAsString(product))
                            .flatMap(json ->
                                    redis.opsForValue()
                                            .set(key, json, TTL)
                                            .thenReturn(product)));
    }

    public Mono<Long> evict(String id) {
        return redis.delete("cache:products:v1:" + id);
    }
}
~~~

Flow:

~~~mermaid
sequenceDiagram
    participant C as WebFlux Controller
    participant S as ReactiveProductCache
    participant R as Redis
    participant D as ReactiveProductSource
    C->>S: findById("p-101")
    S->>R: Reactive GET cache:products:v1:p-101
    alt Cache hit
        R-->>S: JSON
        S->>S: Deserialize ProductView
        S-->>C: Mono<ProductView>
    else Cache miss
        R-->>S: Empty
        S->>D: findById("p-101")
        D-->>S: ProductView
        S->>S: Serialize JSON
        S->>R: SET key JSON EX 600
        R-->>S: OK
        S-->>C: ProductView
    end
~~~

Notes:

1. `switchIfEmpty(Mono.defer(...))` runs the fallback only when Redis lacks a value, not when Redis fails.
2. `ObjectMapper` serializes objects inside the pipeline as CPU work. For small payloads this is generally fine; for huge payloads, monitor event-loop latency and offload heavy CPU work appropriately.
3. `opsForValue().set(key, json, TTL)` instructs Redis to store the value **with TTL** in one supported operation, avoiding the gap of separate `SET` and `EXPIRE` commands.
4. `thenReturn(product)` emits the product once the cache write completes. If Redis `SET` errors, this code **propagates the error** instead of silently returning the product.
5. If `source.findById` returns `Mono.empty()`, the service also returns empty and does not negative-cache.
6. This snippet does not prevent cache stampedes or stale data from concurrent writes; those require separate design.

### 8.3. Why use Mono.defer?

Compare:

~~~java
// Avoid triggering eager side effects or blocking computation outside the publisher.
return cacheRead.switchIfEmpty(loadSourceEagerly());

// Proper pattern when fallback should be constructed upon subscribe/miss.
return cacheRead.switchIfEmpty(
        Mono.defer(() -> loadFromSource()));
~~~

If `loadSourceEagerly()` returns a pure cold Mono with no side effects, it may not run the query prematurely; however, `Mono.defer` defers constructing the fallback flow and any side effects until actually needed. In reactive code, **subscription** controls when the command chain runs.

### 8.4. Separate cache error policies from source error policies

In cache-aside, if Redis is unavailable while the authoritative store is healthy, you may want to return data from the source. Yet a misplaced `onErrorResume` can swallow database errors too.

Example falling back only on **cache read** errors:

~~~java
public Mono<ProductView> findWithReadFallback(String id) {
    String key = "cache:products:v1:" + id;

    Mono<ProductView> readCache =
            redis.opsForValue()
                    .get(key)
                    .flatMap(json ->
                            Mono.fromCallable(
                                    () -> mapper.readValue(
                                            json, ProductView.class)))
                    .onErrorResume(
                            org.springframework.data.redis.RedisConnectionFailureException.class,
                            ex -> Mono.empty());

    return readCache.switchIfEmpty(
            Mono.defer(() -> source.findById(id)));
}
~~~

This sample **does not refill the cache on miss**, isolating the error-handler placement. In production, chain `loadAndCache` or a dedicated "best-effort cache put," record metrics, and protect the database against traffic surges.

Never blindly use:

~~~java
return redisOperation.onErrorResume(error -> Mono.empty());
~~~

across every failure. It hides serialization bugs, bad data, and even programming defects. For critical data, fail-open caching is not always safe.

## 9. TTL with Reactive Templates vs. Redis Repository TTL

### 9.1. Redis Repository

~~~java
@RedisHash(value = "sessions", timeToLive = 900)
public class SessionEntity {
    @Id
    private String id;
}
~~~

In repositories, framework mapping applies the 900-second TTL convention and coordinates expiration events and indexes.

### 9.2. Reactive Template

~~~java
Mono<Boolean> saved =
        redis.opsForValue().set(
                "session:v1:" + sessionId,
                json,
                Duration.ofMinutes(15));
~~~

With templates, **TTLs must be specified on the write operation**, or applied later with `expire(...)` per your protocol. Placing `@TimeToLive` on a DTO does nothing inside `ReactiveStringRedisTemplate`.

### 9.3. What are the risks of calling expire separately?

~~~java
redis.opsForValue().set(key, value)
    .then(redis.expire(key, Duration.ofMinutes(15)));
~~~

These two commands are not one atomic Redis operation. If the connection drops after `SET` and before `EXPIRE`, the key lives indefinitely with no TTL. For Redis String values, prefer `set(key, value, Duration)` to combine them into a single operation.

For Redis Hashes with multiple fields, you typically execute `HSET`/`HSETALL` followed by `EXPIRE`. When atomicity across multiple commands is mandatory, consider Redis Lua/Redis Functions or same-slot mechanisms; never assume Reactor `.then(...)` creates a Redis transaction.

### 9.4. TTL does not equal expiration events

Redis evicts expired keys even if Spring registers no listener. If you need reactive handling on expiration, understand keyspace notifications, server configuration privileges, and the non-durable nature of Pub/Sub.

Reactive Templates **do not synthesize** Redis Repository `RedisKeyExpiredEvent` events or maintain shadow copies. When notifications are lost, application-written index cleanup will miss them; build compensating sweeps.

## 10. Reactive Templates Can Store Redis Hashes, Yet Do Not Become Repositories

Suppose you store products in a Redis Hash instead of a JSON String:

~~~text
HSET product:p-101 id p-101 name Desk category furniture
EXPIRE product:p-101 600
~~~

Reactive Redis provides `opsForHash()` to manage hash fields. Conceptually:

~~~java
// Pseudocode for operation structure; types and serializers
// must match the configured ReactiveRedisTemplate.
return redis.opsForHash()
        .putAll(
                "product:p-101",
                Map.of(
                        "id", "p-101",
                        "name", "Desk",
                        "category", "furniture"))
        .then(redis.expire(
                "product:p-101",
                Duration.ofMinutes(10)));
~~~

This snippet is *illustrative*: `ReactiveHashOperations` types and serializers must align with the actual `ReactiveRedisTemplate` bean generics.

### 10.1. Differences from @RedisHash

`@RedisHash` + repository can:

- Build keys from IDs and keyspaces per mapping.
- Map entity fields to Hash fields.
- Maintain metadata and secondary indexes.
- Apply TTLs from annotations.
- Hydrate entities back from Hashes.

Meanwhile, `opsForHash().putAll(...)` simply writes the provided fields. It **does not**:

- Read `@Id` from an entity.
- Build key names from `@RedisHash`.
- Create secondary indexes for `@Indexed`.
- Honor `@TimeToLive` on the entity.
- Emit Spring repository lifecycle events.
- Clean up secondary indexes upon TTL expiration.

To get repository-like semantics, the application must implement those mechanisms itself or pick a different architecture.

### 10.2. Why avoid copying the Repository's internal key layout?

Redis Repositories maintain index sets, keyspace metadata, and phantom copies using internal conventions. Manually reproducing all of those across multiple Redis commands:

- Couples you to internal details of a specific Spring Data Redis version.
- Leaks orphaned index entries on writes, updates, and deletes.
- Lacks atomicity under concurrent service updates.
- Becomes brittle across upgrades and failovers.

A **custom reactive store** should define its own clean data model, explicit schema, and operational tests rather than imitating legacy Redis Repository internal keys.

## 11. Without Repository Query Derivation, How Do You Query?

Repositories support certain finder methods backed by indexes. With templates, you design query patterns directly on Redis primitives.

For example, looking up products by category:

~~~text
products:v1:p-101          -> JSON for product 101
products:v1:p-102          -> JSON for product 102
products:by-category:desk  -> Redis Set containing p-101, p-102
~~~

The write path can:

1. Write the product value.
2. Add the ID to the category's Redis Set.
3. When category changes, remove the ID from the old Set and add to the new Set.
4. When deleting a product, delete the key and remove the ID from related indexes.
5. On TTL expiration, prevent stale IDs in indexes via a lifecycle strategy.

### 11.1. Index consistency

If saving the JSON succeeds while updating the index fails, category queries miss the product. If updating category adds to the new Set without removing from the old Set, the ID shows up in the wrong category.

When multiple keys must stay consistent together, define:

- Redis transactions or Lua scripts when on the same node/hash slot and supported.
- Idempotency rules for retries.
- Recovery for network errors leaving write outcomes uncertain.
- Index rebuild jobs from the source of truth.
- Acceptable eventual-consistency bounds.

**Never call `reactiveRedisTemplate.opsForHash()` and assume multi-step updates are atomic.** Redis guarantees atomicity per individual command (`HSET`/`SADD`), not across separate commands.

### 11.2. Redis Cluster

In Redis Cluster, multi-key commands and Lua scripts enforce **hash slot** constraints. Keys updated atomically together must share a slot, or else use eventual consistency.

Hash tag example:

~~~text
products:{p-101}:value
products:{p-101}:metadata
~~~

Two keys sharing `{p-101}` normally land in the same slot. Never place all products under one global tag, or a single shard becomes a hot spot.

### 11.3. When should you avoid secondary indexes in Redis?

If requirements include complex searches, multi-field filtering/sorting/pagination, joins, and flexible queries, let a database or dedicated search engine handle queries while Redis caches results. Building a custom query engine out of Redis Sets and ZSets usually costs more to maintain than it saves.

## 12. ReactiveRedisTemplate Is Not a Reactive Repository, Yet Offers Powerful Redis Primitives

### 12.1. Atomic counters

For view counts or rate metrics:

~~~java
public Mono<Long> incrementViewCount(String productId) {
    return redis.opsForValue()
            .increment("stats:views:" + productId);
}
~~~

`INCR` is an atomic Redis command; no repository abstraction or read-modify-write loop is needed.

### 12.2. Rate limiting

Use Redis counters with TTLs or Lua scripts to check quotas and update atomically. Never write:

~~~text
GET counter
if counter < limit:
    SET counter + 1
~~~

under concurrent requests, as it races. Reactive APIs organize asynchronous I/O, yet **never replace atomic server-side logic**.

### 12.3. Collections and data structures

Reactive Redis operation groups support:

- String values.
- Hashes.
- Lists.
- Sets.
- Sorted Sets.
- Geo structures.
- Streams and Pub/Sub depending on API/version capabilities.

Each structure has distinct semantics: Sorted Sets fit leaderboards, Hashes fit field updates, and Streams fit retained event logs—no need to force everything into Repository entities.

### 12.4. Lua and server-side execution

When checking and updating Redis atomically is required, a server-side Redis Lua script fits well. Logic sequence:

~~~lua
local current = tonumber(redis.call('GET', KEYS[1]) or '0')
local limit = tonumber(ARGV[1])

if current >= limit then
    return 0
end

return redis.call('INCR', KEYS[1])
~~~

This script assumes the key holds a valid counter and a limit is passed; real systems also handle TTLs, input validation, and Redis Cluster constraints. The Redis server runs the script atomically regarding command interleaving, though long-running scripts block Redis.

Spring Data Redis provides reactive scripting execution; select `RedisScript`, serializers, and argument types per your version. Never rely on `flatMap` to make check-quota-and-increment atomic.

## 13. Reactive Does Not Mean Automatic Parallelism or Pipelining

Three easily confused concepts:

| Concept | Purpose | Guarantees multi-command atomicity? |
|---|---|---|
| **Reactive** | Non-blocking composition, handling results as Mono/Flux | No |
| **Pipelining** | Sending multiple Redis commands without waiting per reply to cut round trips | No |
| **Transaction/Lua** | Protecting multi-command operations or conditional server-side logic | Has specific semantics; requires proper setup |

A reactive client can manage many in-flight Redis commands and share connections efficiently, yet `Mono.zip(...)` never turns commands into a Redis transaction.

Example:

~~~java
Mono<String> a = redis.opsForValue().get("cache:a");
Mono<String> b = redis.opsForValue().get("cache:b");

Mono<Tuple2<String, String>> both = Mono.zip(a, b);
~~~

`Mono.zip` combines results from two publishers without guaranteeing a consistent snapshot across both keys. If another client updates data during reads, each `GET` can observe a different point in time.

When a native command fits better—such as `MGET` on one Redis instance or same-slot Cluster keys—it can outperform separate `GET`s. When atomic conditions are required, use Redis commands/Lua/transactions.

## 14. Controlling Concurrency and Backpressure When Reading Redis

Reactive does not make firing unlimited commands safe.

Example processing many IDs:

~~~java
Flux<ProductView> products =
        Flux.fromIterable(productIds)
                .flatMap(cache::findById, 16);
~~~

The parameter `16` bounds how many inner publishers `flatMap` subscribes to concurrently. This enforces **application-level concurrency control**, preventing thousands of simultaneous `GET`s and database fallbacks.

### 14.1. flatMap and concatMap

- `flatMap` executes inner publishers concurrently; output order may differ from input order.
- `concatMap` preserves order by awaiting each inner publisher sequentially; throughput can drop for independent I/O.
- `flatMapSequential` runs inner subscriptions concurrently while emitting in input order, buffering early completions.

Choose per business rules. For independent product ID lookups, `flatMap(..., concurrency)` usually works well; for strictly ordered updates on the same entity, higher-level serialization/ordering may be needed.

### 14.2. What does backpressure limit?

Reactor supports demand and backpressure between Publisher and Subscriber. However, Redis cannot "un-send" commands already dispatched; depending on driver and command, responses may already sit in memory buffers.

Therefore:

- Bound concurrency upfront.
- Avoid unbounded `Flux.range(1, millions).flatMap(...)`.
- Consider batching/paging when reading many keys.
- Monitor Redis latency, connection queues, CPU, and memory.
- Apply timeouts and circuit breakers when Redis is overloaded.

Backpressure helps, yet **never replaces rate limiting and capacity planning** for Redis.

### 14.3. Do not call subscribe inside services

Broken lifecycle structure:

~~~java
public Mono<Void> save(String key, String value) {
    redis.opsForValue().set(key, value).subscribe();
    return Mono.empty();
}
~~~

This detaches the write from the caller:

- Callers can observe completion before Redis finishes writing.
- Redis errors fail to propagate properly.
- Cancellation, retries, tracing, and transaction context break.

Return the publisher instead:

~~~java
public Mono<Void> save(String key, String value) {
    return redis.opsForValue()
            .set(key, value)
            .then();
}
~~~

WebFlux or the owning caller subscribes at the proper boundary.

### 14.4. Do not call block on the event loop

Incorrect:

~~~java
String value = redis.opsForValue().get(key).block();
~~~

On Netty event-loop/WebFlux request threads, `block()` defeats non-blocking I/O and can throw errors or exhaust request capacity under load.

If calling an imperative API is unavoidable, isolate it behind a `boundedElastic` boundary (see migration section). Never use `block()` as a shortcut to turn reactive APIs into synchronous Repositories on request paths.

## 15. What If You Must Use an Imperative Redis Repository Inside a Reactive Flow?

Some systems already have:

- Redis `CrudRepository` and complex entity mappings.
- Many finder methods using secondary indexes.
- Existing logic coupled to `@RedisHash` and `@Indexed`.
- A phased migration plan where immediate rewrites are not feasible.

You can **wrap blocking calls on the `boundedElastic` scheduler** to shield the event-loop:

~~~java
import org.springframework.data.repository.CrudRepository;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public class TransitionalProductAccess {

    private final ProductRedisRepository repository;

    public TransitionalProductAccess(
            ProductRedisRepository repository) {
        this.repository = repository;
    }

    public Mono<ProductRedisEntity> findById(String id) {
        return Mono.fromCallable(
                    () -> repository.findById(id))
                .subscribeOn(Schedulers.boundedElastic())
                .flatMap(optional -> Mono.justOrEmpty(optional));
    }
}
~~~

This **does not create a native reactive repository**. The repository stays blocking; it simply runs on a scheduler built for blocking tasks instead of tying up the event-loop.

### 15.1. Limits of the boundedElastic strategy

- Every I/O call still holds a worker thread while waiting.
- Thread/queue capacity is bounded; throughput hits a ceiling when Redis slows down.
- Does not benefit from Lettuce's reactive multiplexing.
- Requires careful handling of cancellation, timeouts, and retries.
- High parallel call volume can saturate the thread pool.
- Imperative repository transaction/session context does not carry over into reactive context.

This wrapper works as a **temporary bridge**, not a long-term substitute for high-volume non-blocking Redis operations.

### 15.2. When to choose phased migration?

If a legacy Repository powers complex queries, you can:

1. Keep the Repository behind a blocking adapter on `boundedElastic`.
2. Migrate simple cache/`GET`/`SET` paths to `ReactiveStringRedisTemplate`.
3. Measure latency, throughput, and memory as traffic shifts.
4. Design separate namespaces/schemas instead of overwriting old keys.
5. Retire the Repository only after mapping, indexing, and TTL logic have explicit replacements.

This carries far less risk than blindly switching every interface to an unsupported `ReactiveCrudRepository`.

## 16. When You Need a Real Reactive Repository: Re-Evaluate Where Data Lives

Not every piece of data belongs in Redis as a primary entity.

### 16.1. Reactive database repository + reactive Redis cache

A common architecture:

~~~text
WebFlux Controller
      |
      v
Reactive Service
      |
      +--> ReactiveRedisTemplate: cache/fast lookup
      |
      +--> R2DBC Repository / Reactive Mongo Repository: authoritative source
~~~

Example:

- PostgreSQL via Spring Data R2DBC manages `Product` entities and queries.
- Reactive Redis Template holds JSON caches with TTLs.
- Database updates invalidate caches post-commit via an appropriate mechanism.

Benefit: leverage reactive repositories where they are truly supported, while Redis handles caching and native Redis structures.

### 16.2. When Redis is the primary data store

Build a **custom reactive data-access adapter** on top of `ReactiveRedisTemplate`:

~~~java
public interface ReactiveProductStore {
    Mono<ProductView> save(ProductView product);
    Mono<ProductView> findById(String id);
    Mono<Boolean> deleteById(String id);
}
~~~

The implementation must define:

- Key schemas, IDs, serialization.
- TTLs and data lifecycles.
- Attribute-based query patterns.
- Secondary index consistency.
- Atomicity and concurrency control.
- Errors, timeouts, retries, and idempotency.
- Migration and backward compatibility.

Naming the interface `ReactiveProductStore` or `ProductGateway` helps prevent mistaking it for a framework-managed Spring Data Redis reactive repository.

### 16.3. Do not abuse Redis as a general query engine

If you need joins, dynamic filters, multi-criteria pagination, relational transactional constraints, and reporting, a reactive database repository fits far better. Manual indexing with Redis Sets/Sorted Sets often costs more in consistency and maintenance than it delivers.

**Choose your datastore from your data model first**, not just from wanting every API to return `Mono`.

## 17. Does Spring Cache Annotation Replace a Reactive Redis Repository?

Some applications use:

~~~java
@Cacheable(cacheNames = "products", key = "#id")
public Mono<ProductView> findProduct(String id) {
    return reactiveDatabase.findById(id);
}
~~~

Distinguish:

- `@Cacheable` is **Spring Cache abstraction** at the method-result level.
- `RedisCacheManager` is a Redis-backed cache manager implementation.
- `ReactiveRedisTemplate` is the non-blocking Redis operations API.
- `ReactiveCrudRepository` is a repository abstraction in Spring Data Commons.

Since Spring Framework 6.1, the cache abstraction adds specialized support for reactive return types under specific conditions; actual runtime behavior depends on the `CacheManager`/`Cache` implementation and setup. **Never infer that `@Cacheable` + `RedisCacheManager` guarantees native non-blocking Redis cache I/O.** `RedisCacheManager` has imperative/blocking roots and does not turn into a reactive Redis repository.

When end-to-end non-blocking HTTP execution is mandatory, evaluate your exact cache stack. Often, explicitly composing `ReactiveRedisTemplate` with reactive sources gives clearer control.

Another pitfall is caching the `Mono` object itself rather than its emitted result. Reactive publisher caching varies by Spring Framework version and cache implementation; verify exact semantics before mixing annotations with Reactor.

## 18. Consistency with Databases and Transactions

A reactive chain looks very clean:

~~~java
return productRepository.save(product)
        .flatMap(saved ->
                redis.delete("cache:products:v1:" + saved.getId())
                     .thenReturn(saved));
~~~

Its actual semantics:

1. Database persists the record.
2. Redis cache key is deleted.
3. Caller receives the result if both succeed.

**There is no automatic distributed transaction** between the database and Redis.

If the database commits and Redis `DELETE` fails, the database holds new data while the cache retains stale data. The caller receives an error, yet blind retries can double-write records or emit duplicate events.

### 18.1. Ways to improve reliability

- Invalidate cache **after database commit** via reactive transaction synchronization or durably persisted events.
- Use a transactional outbox/CDC when updating caches across services.
- Set fallback TTLs so stale entries cannot live forever.
- Use versioned cache keys where suitable.
- Design idempotent retries with backoff and caps.
- Define maximum acceptable staleness.

R2DBC's `@Transactional` never pulls Redis commands into the same ACID transaction. Nor do Redis transactions/Lua merge database and Redis commits into one.

### 18.2. Race between cache miss and update

Suppose:

~~~text
T1  Reader fetches v1 from source, prepares to cache
T2  Writer updates database to v2, deletes cache
T3  Reader writes v1 to cache after Writer deleted it
T4  Subsequent requests read stale v1
~~~

Even when both flows use non-blocking `Mono`/`Flux`, the race still exists. Enforce tight TTLs matching freshness SLAs, or use version checks and careful invalidation protocols.

### 18.3. Reactive cancellation and side effects

An HTTP client disconnect can make the subscriber cancel the reactive pipeline. Yet any Redis command already sent **may still execute on Redis**; cancellation does not mean rollback. Critical business writes need idempotency and durable state rather than assuming "cancel = never written."

## 19. Errors, Timeouts, and Retries in Reactive Redis

### 19.1. Timeouts

~~~java
Mono<String> response = redis.opsForValue()
        .get("cache:product:101")
        .timeout(Duration.ofSeconds(2));
~~~

Timeouts protect the application's wait budget, yet do not prove Redis did not execute the command. For read-only `GET`s, retries are simpler. For `INCR` or writes with side effects, retrying after a timeout can apply the change **twice** if the first command ran.

### 19.2. Conditional retries

For reads:

~~~java
Mono<String> read = redis.opsForValue()
        .get(key)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                     .filter(this::isTransientRedisFailure));
~~~

In this sample, `isTransientRedisFailure` is an application-defined predicate. Bound retry counts, total pipeline timeouts, and concurrent requests; never retry schema errors or invalid inputs.

For writes, distinguish:

- `SET key fixedValue` can be relatively safe to retry if no ordering/concurrency semantics change.
- `INCR`/`LPUSH`/event appends can duplicate side effects.
- Scripts with idempotency keys or conditional writes enable safe retry protocols.

### 19.3. Redis failing while the primary source is healthy

In cache-aside, a fail-open policy can still read the database when Redis `GET` fails. However, if the entire Redis cluster fails, massive traffic surges can hit the database at once. Use:

- Concurrency limits.
- Circuit breakers/cooldowns.
- Rate limiting and bulkheads.
- Cache read failure monitoring.
- Primary-source protection against miss storms.

Never hide Redis errors everywhere via `onErrorResume(error -> Mono.empty())`, as doing so masks logic bugs and failed cache invalidations.

## 20. Reactive Streams and Redis Pub/Sub Are Not Repositories

Beyond simple key/value lookups, Spring Data Redis provides reactive access for messaging use cases.

### 20.1. Redis Pub/Sub

Pub/Sub suits real-time notifications where missing messages while a subscriber is offline is acceptable. Reactive APIs expose a `Flux` of messages.

However, Pub/Sub **offers no persistence/replay** for offline subscribers. Using a reactive `Flux` only improves I/O consumption, without changing Redis delivery semantics.

### 20.2. Redis Streams

Redis Streams retain entries until trimmed, supporting consumer groups and `XACK`. Spring Data Redis Reactive Streams APIs return Map/Object records per configured serializers/mappers.

Streams fit better than Pub/Sub when history, pending/reclaim, and policy-driven retries are required. Still:

- Consumers must manage offsets, ACKs, and idempotency.
- Streams have their own retention/trimming limits.
- Reactive processing does not guarantee exactly-once business effects.
- `MapRecord`/`ObjectRecord` for Streams **do not constitute a reactive entity repository**.

When the application needs an event log, choose Stream operations directly rather than forcing them into a CRUD repository interface.

## 21. Mapping and Migration from Legacy Repositories

When migrating from an imperative Redis Repository to Reactive Templates, build a feature-by-feature comparison table:

| Legacy feature | Previous Repository | Reactive Template alternative |
|---|---|---|
| `save(entity)` | Persists entity via Redis mapping | Serialize DTO and `SET`/`HSET` |
| `findById(id)` | Reads entity from Hash | `GET`/`HGETALL` + decode |
| `deleteById(id)` | Deletes entity and related metadata | `DEL`/`UNLINK` + manual cleanup |
| `@TimeToLive` | Applies TTL via mapping | Pass `Duration` on write or call `expire` |
| `@Indexed` | Manages index metadata | Redis Sets/ZSets or database queries |
| Field finders | Backed by supported secondary indexes | Design explicit queries/indexes |
| Expiration events | Repository event listener | Explicit keyspace notifications or avoid relying on events |
| Object mapping | `RedisConverter` | Application-chosen JSON serializer/Hash mapper |
| Schema version | Per mapping and application contract | Explicit versioned prefixes/schemas |
| Multi-key atomicity | Not guaranteed by default | Lua/transactions/consistency protocols |

### 21.1. Safe migration by namespace

Phased plan:

~~~text
Phase 1:
  Old reader -> Repository in old namespace
  New reader -> Template in v2 namespace
  Authoritative source unchanged

Phase 2:
  Populate/backfill v2 namespace
  Verify functionality and load profile

Phase 3:
  Gradually shift traffic to v2 reader
  Monitor cache misses, latency, serializer errors

Phase 4:
  Stop writing to old namespace
  Clean up old indexes/keys carefully
~~~

If Redis is the sole source of truth, migration demands safe snapshot/backfill/dual-write strategies rather than waiting for old cache keys to expire by TTL.

### 21.2. Dual writes are not automatically atomic

During transition, the application may write to both the legacy repository and the new template. If one write succeeds and the other fails, the two namespaces diverge. You need:

- A designated source of truth.
- Replay/reconciliation jobs.
- Versioned records and idempotent upserts.
- Mismatch monitoring.
- Clear cutover criteria to the new format.

Never assume a Reactor `.then(...)` chain makes dual writes atomic.

## 22. Testing Reactive Templates Properly

### 22.1. StepVerifier

For `Mono`-returning methods:

~~~java
import reactor.test.StepVerifier;

@Test
void shouldSaveAndRead() {
    StepVerifier.create(store.save("u-101", "Hello"))
            .expectNext(true)
            .verifyComplete();

    StepVerifier.create(store.read("u-101"))
            .expectNext("Hello")
            .verifyComplete();
}
~~~

This tests against a live Redis instance; it requires `reactor-test` and test Redis infrastructure. Verifying `Mono<Boolean>` depends on the Redis command outcome and valid keys.

### 22.2. Using a test Redis instance

Testcontainers or a dedicated test Redis instance verifies:

- Real serialized bytes.
- TTLs via `TTL`/`PTTL`.
- `Mono.empty()` when keys do not exist.
- Error handling when Redis disconnects.
- Duplicate writes and concurrent updates.
- Redis Cluster slot rules if production uses Cluster.
- Reactive listeners/Streams offsets if used by business logic.

Mocks alone cannot prove key/value serializers match Redis behavior.

### 22.3. Do not use block in production just because tests do

In unit/integration tests, using `StepVerifier` (or `block()` on a test thread) is fine when testing a publisher. That **does not mean** `block()` is safe inside reactive HTTP request handlers.

### 22.4. Metrics to validate your choice

Measure:

- P50/P95/P99 latency of Redis `GET`/`SET`.
- Lettuce connection counts and pending requests.
- Reactor event-loop blocked time.
- `flatMap` concurrency.
- Cache hit/miss rates and fallback DB QPS.
- Redis CPU/memory/evictions.
- Serialization overhead and payload sizes.
- Retry counts, timeouts, and errors.
- Secondary index drift if maintained manually.

A codebase full of `Mono` is not effectively reactive if underneath it relies mostly on blocking repository calls or heavy serialization CPU work on the event-loop.

## 23. Practical Decision Scenarios

### Scenario A: Product cache in WebFlux

**Requirement:** read products from a reactive database and cache in Redis for 10 minutes; no field-level Redis queries needed.

**Choice:** `ReactiveStringRedisTemplate` + JSON DTO + TTL.

Reason: simple key-value access, easy cache-aside composition, no repository emulation needed. Watch stale data and post-commit invalidation.

### Scenario B: Redis stores entities indexed by email

**Requirement:** entity CRUD, find by email, and keep indexes consistent on TTL expiration.

**Choice:** consider keeping the imperative Redis Repository behind an isolated adapter (if load permits), or design a custom reactive store with explicit index lifecycles. If strong consistency, unique constraints, and rich queries are central, consider a datastore with real reactive repository support.

Reason: Templates do not automatically maintain derived finders, secondary indexes, or expiration cleanup.

### Scenario C: High-concurrency rate limiter

**Requirement:** atomically count and check quotas at low latency.

**Choice:** `ReactiveRedisTemplate` for Redis primitives/Lua scripts.

Reason: this is a Redis command and atomic server-side logic problem, not an entity repository query problem.

### Scenario D: Existing system with Redis CrudRepository

**Requirement:** migrate incrementally to WebFlux while preserving correctness.

**Choice:** temporary `boundedElastic` adapter for the repository, migrating simple paths to reactive templates once dedicated namespaces/schemas are ready.

Reason: avoids blocking the event-loop and avoids corrupting the legacy key layout.

### Scenario E: Events needing reprocessing

**Requirement:** offline subscribers must still catch up on events, with ACKs and retries.

**Choice:** reactive Redis Streams operations or a suitable durable broker.

Reason: reactive Pub/Sub provides no retention; Streams offer log/consumer-group models while requiring pending management and idempotency.

### Scenario F: Complex search and pagination

**Requirement:** multi-field filtering, sorting, pagination, frequent updates.

**Choice:** reactive repositories for R2DBC/MongoDB/search services where querying is natively supported; use Redis templates for caching or Redis-suited operations.

Reason: never build a manual indexing engine in Redis merely to achieve a "Reactive Redis Repository."

## 24. Common Misconceptions

### 24.1. "Spring Data has ReactiveCrudRepository so Redis must have it too"

False. The interface lives in Spring Data Commons, while implementation support depends on each store module. Never assume Redis supports reactive repositories like Reactive MongoDB or R2DBC.

### 24.2. "Wrapping in Mono.just(repository.findById()) is non-blocking"

False. The repository already executed before `Mono` was created. Changing the return type alone never changes I/O behavior.

### 24.3. "Mono.fromCallable converts blocking I/O to a reactive driver"

False. It defers execution, yet the callable remains blocking. You can pair it with `subscribeOn(Schedulers.boundedElastic())` to isolate blocking code, though that is only a bridge.

### 24.4. "ReactiveRedisTemplate supports @RedisHash/@Indexed/@TimeToLive automatically"

False. Those annotations belong to repository mapping. With Templates, the application owns data layout, secondary indexes, and TTLs.

### 24.5. "Switching Repository Hashes to Redis Strings on the same key is harmless"

False. Redis Hashes and Strings are incompatible data types. Colliding keys trigger `WRONGTYPE` errors and corrupt index metadata.

### 24.6. "Using flatMap makes operations atomic"

False. `flatMap` is Reactor composition. Redis atomicity exists only per individual command or via transactions/Lua.

### 24.7. "Reactive code cannot be overloaded"

False. Too many in-flight publishers still spike pending commands, connections, memory, and Redis load. Concurrency caps, timeouts, and bounded queues are essential.

### 24.8. "Calling subscribe() in a service is the best way to run saves"

False. Manual `subscribe()` detaches side effects from the caller, breaking error propagation and cancellation. Return the publisher to the owning layer.

### 24.9. "RedisCacheManager with @Cacheable equals ReactiveRedisTemplate"

Not equivalent. Cache abstraction/`RedisCacheManager` has its own semantics and I/O model; annotations support reactive return types in recent Spring versions, yet never create a reactive Redis repository.

### 24.10. "Reactive Redis solves transactions between databases and Redis"

No. Reactive composition does not create distributed transactions. You need consistency strategies, outboxes, versioning, and retries.

## 25. Self-Check Questions

**Question 1. Does Spring Data Redis provide a drop-in reactive repository replacement for CrudRepository?**

No, under Reactive Redis support documented in Spring Data Redis's Redis Repository and Reactive Redis documentation. The primary API for non-blocking Redis access is `ReactiveRedisTemplate` and Reactive Redis operations. Always verify your project's version in case framework capabilities evolve.

**Question 2. When you only need GET/SET with TTL in WebFlux, what should you use?**

`ReactiveStringRedisTemplate` with String/JSON, or `ReactiveRedisTemplate` with a matching serialization context.

**Question 3. Why doesn't ReactiveRedisTemplate automatically clean up `@Indexed` secondary indexes?**

Because the template simply executes the requested Redis commands and does not run Redis Repository mapping or index lifecycles.

**Question 4. Is `Mono.fromCallable` + `boundedElastic` native reactive Redis I/O?**

No. It isolates blocking calls off the event-loop, yet still consumes a thread per blocking call.

**Question 5. Should you call `block()` inside a WebFlux handler?**

No. `block()` blocks the executing thread and can ruin throughput or throw errors on the event-loop.

**Question 6. On a cache miss, does `findById` call the database automatically?**

No, unless the application explicitly composes a fallback such as `switchIfEmpty(source.findById(...))`. Templates have no built-in cache-aside behavior.

**Question 7. Is TTL automatically read from `@TimeToLive` on a DTO?**

No. With reactive templates, pass TTL explicitly on write operations or via separate commands.

**Question 8. Does `ReactiveRedisTemplate` prevent races when multiple workers modify one key?**

No. Use atomic commands like `INCR`, or Lua/transactions and idempotency.

**Question 9. If Redis is only a cache, where should authoritative data live?**

In a primary datastore meeting business requirements, such as a database with a supported reactive repository; Redis holds reconstructible data with TTL/invalidation.

**Question 10. Can reactive Redis Streams replace a Repository?**

Streams fit retained event logs and consumer groups. They do not provide a query-by-entity repository abstraction or entity CRUD/index management.

**Question 11. Does Spring `@Cacheable` on a Mono mean all Redis I/O is non-blocking?**

Do not assume that. Check the Spring Framework version, `CacheManager`/`Cache` implementation, and how Redis I/O is actually executed.

**Question 12. Why use a new namespace during migration?**

To prevent data-type collisions, serializer mismatches, and keyspace metadata/TTL/index conflicts between the old repository and the new template.

## 26. Brief Decision Guide

~~~mermaid
flowchart TD
    A["App needs Redis in a reactive flow"] --> B{"Need entity CRUD + automatic finders/indexes?"}
    B -- "No" --> C{"Using simple Strings/JSON?"}
    C -- "Yes" --> D["ReactiveStringRedisTemplate"]
    C -- "No" --> E["ReactiveRedisTemplate + serialization context"]
    B -- "Yes" --> F{"Is Redis the primary data source?"}
    F -- "No" --> G["Reactive R2DBC/Mongo repository + reactive Redis cache"]
    F -- "Yes" --> H["Custom reactive Redis data-access adapter; design mapping/indexes/TTL"]
    H --> I{"Legacy Redis repository to retain?"}
    I -- "Yes" --> J["Temporary boundedElastic bridge + namespace migration"]
    I -- "No" --> K["Deploy and measure non-blocking I/O"]
~~~

Key design questions to settle:

- Is the data a **cache** or the **authoritative source**?
- Do you need **direct Redis commands** or **automatic entity mapping/queries**?
- Are secondary indexes or TTLs needed?
- Are multi-key atomicity or business confirmations required?
- Is event replay needed?
- Does the connection factory support proper reactive I/O?
- What is the expected concurrent request load and Redis capacity?
- Must existing data be migrated?

## 27. Summary

**Reactive Redis does not mean Reactive Redis Repository.** Spring Data Redis provides Reactive Template and Reactive Operations APIs for Redis commands and data structures, yet you cannot simply extend `ReactiveCrudRepository` to obtain a reactive Redis Repository with mapping, query derivation, TTLs, and indexes like the imperative version.

For **caching, counters, rate limiting, key-value data, Hashes, Sets, Sorted Sets, or Streams**, the direct choice is `ReactiveRedisTemplate` or `ReactiveStringRedisTemplate` with explicit serializers, key schemas, and TTLs. For **entity CRUD/queries needing a repository abstraction**, use a reactive datastore repository that is genuinely supported, or build a custom Reactive Template adapter and take ownership of mapping, indexing, and consistency.

When an imperative Redis Repository already exists, avoid calling blocking methods on the WebFlux event-loop; `boundedElastic` is a limited transitional bridge. During migration, never overwrite legacy namespaces or Hash layouts with new String/template writes without a migration plan. Even when code uses `Mono`/`Flux`, correctness still rests on atomic Redis commands, TTLs, transaction boundaries, retries, idempotency, and error handling—**reactive only changes the I/O programming model, never replacing sound data design**.

## References

- Spring Data Redis — [Reactive Redis support](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html): ReactiveRedisOperations, ReactiveRedisTemplate, and reactive connections.
- Spring Data Redis — [Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html): entity mapping, repository model, keyspaces, and indexes.
- Spring Data Redis — [Redis Templates](https://docs.spring.io/spring-data/redis/reference/redis/template.html): RedisTemplate, serialization, and Redis operations.
- Spring Data Redis — [Redis Serialization](https://docs.spring.io/spring-data/redis/reference/redis/serializers.html): RedisSerializer, serialization contexts, and formats.
- Spring Data Redis — [Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): Stream operations, consumer groups, and record mapping.
- Spring Data Commons — [Reactive Repositories](https://docs.spring.io/spring-data/commons/reference/repositories/core-concepts.html): repository interfaces and store-specific implementations.
- Spring Framework — [WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive request handling and non-blocking execution.
- Project Reactor — [Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono/Flux, composition, scheduling, and backpressure.
- Redis — [Key expiration](https://redis.io/docs/latest/commands/expire/): server-side Redis TTL.
- Redis — [Transactions](https://redis.io/docs/latest/develop/interact/transactions/): MULTI/EXEC, atomicity, and limitations.
