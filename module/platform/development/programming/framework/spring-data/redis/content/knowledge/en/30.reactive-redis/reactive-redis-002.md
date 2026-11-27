# Configuring ReactiveRedisConnectionFactory and ReactiveRedisTemplate

In **Spring Data Redis**, an application can access Redis synchronously via `RedisTemplate` or reactively via `ReactiveRedisTemplate<K,V>`. The reactive model fits Spring WebFlux and Project Reactor when an application needs to compose asynchronous I/O operations without tying up an application thread merely waiting for Redis to reply.

Two key components are:

- `ReactiveRedisConnectionFactory`: the interface providing Redis connections with a reactive API;
- `ReactiveRedisTemplate<K,V>`: the high-level Redis operations class returning `Mono`/`Flux` and using a serialization context for keys and values.

Proper configuration requires more than renaming a bean from `RedisTemplate` to `ReactiveRedisTemplate`. You must choose a reactive-capable client, configure endpoints/topology and TLS, align serializers, understand how subscriptions trigger I/O, handle timeouts, and avoid confusing reactive Redis with distributed transactions or always-consistent caching.

## 1. Distinguishing Imperative and Reactive Redis

With synchronous RedisTemplate:

```java
String status =
        stringRedisTemplate.opsForValue().get("user:42:status");
```

The calling thread waits for a result to be returned. With Reactive Redis:

```java
Mono<String> status =
        reactiveStringRedisTemplate.opsForValue()
                .get("user:42:status");
```

`Mono<String>` is not the String value already read; it is a publisher describing an asynchronous result. Once subscribed to, the Redis execution path runs and the publisher emits data, completes empty, or emits an error.

| Aspect | Imperative | Reactive |
|---|---|---|
| Template | `RedisTemplate`, `StringRedisTemplate` | `ReactiveRedisTemplate`, `ReactiveStringRedisTemplate` |
| Factory | `RedisConnectionFactory` | `ReactiveRedisConnectionFactory` |
| Single result | `String`, `Long`, `Boolean`, or `null` | `Mono<T>` |
| Multiple results | Collection, cursor, callback | `Flux<T>` |
| Coordinating operations | Sequential calls | `map`, `flatMap`, `then`, `zip`, etc. |
| Error reporting | Exception | `onError` signal in the publisher |
| Missing data | `null` or empty collection depending on API | `Mono.empty()` or `Flux.empty()` |
| Waiting for results | Thread may block | No need to block request threads when used reactively end-to-end |

**Reactive does not inherently make Redis faster.** It helps the application use thread resources efficiently while waiting for I/O. If code still invokes synchronous JDBC or `Thread.sleep` on the event-loop, the benefit can be negated.

## 2. Architecture Flow from WebFlux to Redis

```text
HTTP Client
    |
    v
Spring WebFlux Controller
    |
    v
Service returning Mono/Flux
    |
    v
ReactiveRedisTemplate<K, V>
    |
    +--> SerializationContext: key/value/hash
    |
    v
ReactiveRedisConnectionFactory
    |
    v
Lettuce reactive connection
    |
    v
Redis Standalone / Sentinel / Cluster
```

`ReactiveRedisConnectionFactory` is a connection abstraction. It is not a Redis server and does not automatically perform entity mapping like a Repository. `ReactiveRedisTemplate` uses the connection factory and serializers to issue Redis commands.

In Spring Data Redis, **Lettuce** is the standard Redis client supporting reactive operations. `LettuceConnectionFactory` can implement both the imperative and reactive contracts, so an application can run both API styles if genuinely needed.

## 3. Dependencies and Environment

Gradle example for Spring Boot WebFlux:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("io.projectreactor:reactor-test")
}
```

The Redis starter provides Spring Data Redis along with a suitable client under Spring Boot dependency management. `spring-boot-starter-webflux` is needed when building WebFlux HTTP APIs; if you only want to call reactive Redis inside another application, WebFlux is not mandatory across the entire app.

Prerequisites:

1. Redis is reachable from the machine running the application.
2. The driver genuinely supports `ReactiveRedisConnectionFactory`.
3. Determine whether Redis is standalone, Sentinel, or Cluster before configuring.
4. Authentication/TLS/timeouts are managed via environment variables or a secret manager.
5. Spring Data Redis and Lettuce use compatible versions (let the Spring Boot BOM manage them).
6. Code calling reactive Redis is not turned into blocking via `block()` on the WebFlux path.

## 4. Using Spring Boot Auto-Configuration

When the Redis starter and Lettuce are present, the simplest approach is usually to let Spring Boot create `LettuceConnectionFactory` from `application.yml`.

Example for a local Redis environment:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
```

In production deployments, host, port, password, and certificates should come from environment configuration or a secret manager. Do not hard-code real passwords in code or files committed to a repository.

In modern Spring Boot versions, Redis properties typically reside under `spring.data.redis`; verify against the Spring Boot version in use so no property goes unrecognized.

Once the connection factory is created by Boot, the application can inject it via the reactive interface:

```java
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.stereotype.Component;

@Component
public class RedisConnectionHolder {
    private final ReactiveRedisConnectionFactory factory;

    public RedisConnectionHolder(
            ReactiveRedisConnectionFactory factory) {
        this.factory = factory;
    }
}
```

This example only demonstrates wiring. Business services should call `ReactiveRedisTemplate` rather than acquiring low-level connections for everyday commands.

### 4.1. One LettuceConnectionFactory for two APIs

```text
LettuceConnectionFactory
    |
    +--> RedisConnectionFactory
    |        |
    |        +--> RedisTemplate
    |
    +--> ReactiveRedisConnectionFactory
             |
             +--> ReactiveRedisTemplate
```

Sharing the same factory does not mean imperative and reactive commands share the same transaction or thread context. If both are needed, separate the use cases clearly and avoid accidental blocking in WebFlux.

### 4.2. Do not add duplicate beans if Boot already provides one

If auto-configuration already supplies the factory, adding a manual `LettuceConnectionFactory` can make injection ambiguous or cause two different Redis configurations to be used. Only create a dedicated factory when there is a real reason such as custom connection tuning, multiple Redis deployments, or driver options that must be customized.

## 5. Declaring LettuceConnectionFactory Manually

When not using auto-configuration or when explicit configuration is required:

```java
package example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;

@Configuration
public class ManualRedisConnectionConfig {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration standalone =
                new RedisStandaloneConfiguration("localhost", 6379);

        return new LettuceConnectionFactory(standalone);
    }
}
```

A Spring-managed bean performs lifecycle initialization and destruction according to the factory's contracts.

This is only a **standalone** example and should not be copied as-is for Redis Cluster or Sentinel:

| Environment | Must configure |
|---|---|
| Standalone | Endpoint, TLS, username/password, timeout |
| Sentinel | Master name and sentinel endpoints |
| Cluster | Node list, slot routing, topology refresh, failover |
| Managed Redis | Endpoint/ACL/TLS and provider-specific limits |

A configuration that only knows a single standalone endpoint does not fully describe a Redis Cluster topology. When multiple factories exist, select the specific bean with `@Qualifier` for each template.

## 6. Declaring ReactiveRedisTemplate<String, String>

To start, choosing string keys and values avoids converter complexity:

```java
package example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializationContext;

@Configuration
public class ReactiveRedisTemplateConfig {

    @Bean("appReactiveStringTemplate")
    public ReactiveRedisTemplate<String, String> appReactiveStringTemplate(
            ReactiveRedisConnectionFactory factory) {

        return new ReactiveRedisTemplate<>(
                factory,
                RedisSerializationContext.string());
    }
}
```

`RedisSerializationContext.string()` provides a serialization context suitable for working with string keys and values.

Service using the template:

```java
package example.redis;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class UserStatusCache {

    private final ReactiveRedisTemplate<String, String> redis;

    public UserStatusCache(
            @Qualifier("appReactiveStringTemplate")
            ReactiveRedisTemplate<String, String> redis) {
        this.redis = redis;
    }

    public Mono<Boolean> put(String userId, String status) {
        String key = "user:status:" + userId;
        return redis.opsForValue()
                .set(key, status, Duration.ofMinutes(5));
    }

    public Mono<String> get(String userId) {
        return redis.opsForValue().get("user:status:" + userId);
    }

    public Mono<Long> delete(String userId) {
        return redis.delete("user:status:" + userId);
    }
}
```

`set(...)` emits a Boolean result; `get(...)` emits a String or completes empty if the key does not exist; `delete(...)` reports the number of deleted keys. Redis error signals travel through the publisher and can be handled with Reactor operators.

### ReactiveStringRedisTemplate

Spring Data Redis also provides a shortcut for string data:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class FeatureFlagReader {
    private final ReactiveStringRedisTemplate redis;

    public FeatureFlagReader(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<String> read(String name) {
        return redis.opsForValue().get("feature:" + name);
    }
}
```

With proper Spring Boot configuration, `ReactiveStringRedisTemplate` can be auto-configured. If that bean already exists and you only use string keys/values, there is no need to create an equivalent typed template.

## 7. RedisSerializationContext Is a Critical Part of Configuration

When creating `ReactiveRedisTemplate<K,V>`, the constructor requires a `RedisSerializationContext<K,V>` to know how to convert Java types into bytes accepted by Redis.

| Data role | Java type | Serialization example |
|---|---|---|
| Key | `String` | UTF-8 string |
| Value | `String` | UTF-8 string |
| Value | `ProductSnapshot` | JSON with an explicit schema |
| Hash key | `String` | UTF-8 field name |
| Hash value | String/DTO | String or JSON per application contract |

If a key is written with `StringRedisSerializer` but the reading template uses JDK serialization, the two sides can produce **different key bytes** for the same Java string. Redis holds the key, yet the template still returns a cache miss.

For example, created via Redis CLI:

```redis
SET product:42:name Desk
```

A template using a binary key serializer will not automatically read this key when calling Java `get("product:42:name")`. Align wire formats across writers and readers rather than manually altering Redis keys when serialization is the root cause.

## 8. Configuring a Template for JSON DTOs

When storing objects, choose an explicit target Java type and serializer.

DTO:

```java
package example.product;

public record ProductSnapshot(
        String productId,
        String name,
        long priceVnd,
        long sourceVersion
) {}
```

JSON template:

```java
package example.redis;

import example.product.ProductSnapshot;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.ReactiveRedisConnectionFactory;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class ProductReactiveRedisConfig {

    @Bean("productSnapshotRedisTemplate")
    public ReactiveRedisTemplate<String, ProductSnapshot> productTemplate(
            ReactiveRedisConnectionFactory factory) {

        var keySerializer = new StringRedisSerializer();
        var jsonSerializer =
                new Jackson2JsonRedisSerializer<>(ProductSnapshot.class);

        RedisSerializationContext<String, ProductSnapshot> context =
                RedisSerializationContext
                        .<String, ProductSnapshot>newSerializationContext(
                                keySerializer)
                        .value(jsonSerializer)
                        .hashKey(keySerializer)
                        .hashValue(jsonSerializer)
                        .build();

        return new ReactiveRedisTemplate<>(factory, context);
    }
}
```

The configuration above keeps keys as Strings and values as JSON. A key like `cache:product:v1:42` holds a `ProductSnapshot` payload. Likewise, the hash value serializer is only valid when every hash field genuinely holds an object of that format; if hash fields are strings or numbers, choose a serializer appropriate for the actual data model.

Constructor APIs and Jackson serializer options may change or be deprecated across Spring Data Redis branches. When upgrading versions, check the dependencies in use. The unchanging rule: **the serialization context must match both the Redis data and the Java types the application expects**.

### Schema migration

A new deployment may read entries created by an older version. If the DTO changes structure, deserialization errors can occur. You can use version prefixes:

```text
cache:product:v1:42
cache:product:v2:42
```

Combine TTL, controlled migration/rebuild, and JSON backward compatibility to handle legacy schemas. Do not assume changing a Java record causes Redis to convert existing entries to the new format.

## 9. Reactive Publishers Execute When Subscribed

The following **is not a complete write command if the publisher is discarded**:

```java
public void setFlag() {
    redis.opsForValue().set("flags:checkout", "ENABLED");
    // Mono is discarded; there is no subscriber.
}
```

Return the publisher instead:

```java
public Mono<Boolean> setFlag() {
    return redis.opsForValue().set("flags:checkout", "ENABLED");
}
```

If you want to ensure the write completes before reading:

```java
public Mono<String> writeThenRead() {
    return redis.opsForValue()
            .set("flags:checkout", "ENABLED")
            .then(redis.opsForValue().get("flags:checkout"));
}
```

`then(...)` orders two operations within the same reactive chain, but **does not make them atomic**. Another client can still modify the key between `SET` and `GET`.

### Do not call subscribe() arbitrarily inside a service

```java
public Mono<ProductSnapshot> save(ProductSnapshot product) {
    redis.opsForValue()
            .set("cache:product:v1:" + product.productId(), product)
            .subscribe();  // Fire-and-forget, hard to manage errors.

    return Mono.just(product);
}
```

The flaw here is that the subscription creates side work outside the pipeline observed by the caller. The response can return before Redis finishes writing, and Redis errors are no longer propagated along the return path.

When the Redis write must be observed:

```java
public Mono<ProductSnapshot> save(ProductSnapshot product) {
    return redis.opsForValue()
            .set("cache:product:v1:" + product.productId(), product)
            .thenReturn(product);
}
```

If Redis is only a best-effort cache, the application can decide to ignore cache errors after writing to the primary source, but it must have clear logging/metrics and consistency rules rather than solving it casually with detached `subscribe()` calls.

## 10. WebFlux Controllers Return Mono

```java
package example.redis;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class UserStatusController {
    private final UserStatusCache cache;

    public UserStatusController(UserStatusCache cache) {
        this.cache = cache;
    }

    @GetMapping("/users/{id}/status")
    public Mono<ResponseEntity<String>> read(@PathVariable String id) {
        return cache.get(id)
                .map(ResponseEntity::ok)
                .defaultIfEmpty(ResponseEntity.notFound().build());
    }
}
```

WebFlux subscribes when it needs to build the response. There is no need to call `block()` or `subscribe()` in the controller.

If the Redis key does not exist, `Mono.empty()` can be mapped to HTTP 404 per the API contract. If Redis is unreachable, the error flows through `onError` and **infrastructure failures should not blindly be turned into 404**.

## 11. Distinguishing Mono.empty and Mono.error

Three distinct result shapes:

- `Mono.just(value)`: has one value;
- `Mono.empty()`: emits no value and completes;
- `Mono.error(exception)`: failed during execution.

Example default value for a missing key:

```java
public Mono<String> readOrUnknown(String userId) {
    return redis.opsForValue()
            .get("user:status:" + userId)
            .defaultIfEmpty("UNKNOWN");
}
```

Example intentional fallback when Redis errors:

```java
public Mono<String> flagOrSafeDefault(String name) {
    return redis.opsForValue()
            .get("feature:" + name)
            .onErrorResume(ex -> Mono.just("DISABLED"));
}
```

A `DISABLED` fallback may be appropriate for a feature flag. However, for access permissions, quotas, or money, using a default can introduce security/business bugs. Decide fail-open vs. fail-closed per requirements; do not use `onErrorResume` carelessly to hide incidents.

## 12. Reactive Cache-Aside with a Dedicated Data Source

Suppose authoritative data comes from a reactive source:

```java
public interface ReactiveProductSource {
    Mono<ProductSnapshot> findById(String productId);
}
```

Cache service:

```java
import java.time.Duration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.ReactiveRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveProductCacheService {

    private final ReactiveRedisTemplate<String, ProductSnapshot> redis;
    private final ReactiveProductSource source;

    public ReactiveProductCacheService(
            @Qualifier("productSnapshotRedisTemplate")
            ReactiveRedisTemplate<String, ProductSnapshot> redis,
            ReactiveProductSource source) {
        this.redis = redis;
        this.source = source;
    }

    public Mono<ProductSnapshot> findById(String id) {
        String key = "cache:product:v1:" + id;

        return redis.opsForValue()
                .get(key)
                .switchIfEmpty(Mono.defer(() ->
                        source.findById(id)
                                .flatMap(product ->
                                        redis.opsForValue()
                                                .set(key, product,
                                                        Duration.ofMinutes(5))
                                                .thenReturn(product))));
    }
}
```

Meaning:

```text
Redis GET
  |
  +-- HIT --> return ProductSnapshot
  |
  +-- MISS --> source.findById
                  |
                  +-- no data --> Mono.empty()
                  |
                  +-- data found --> Redis SET TTL 5 minutes
                                       |
                                       v
                                 return ProductSnapshot
```

`Mono.defer(...)` ensures the source-read path is created when a cache miss occurs. The example waits for the cache SET to finish before returning the product; this policy can be adjusted if Redis is only a best-effort cache.

### Cache failure fallback

If the authoritative source can still serve requests when Redis disconnects, you can choose to fall back:

```java
public Mono<ProductSnapshot> findByIdWithFallback(String id) {
    String key = "cache:product:v1:" + id;

    return redis.opsForValue().get(key)
            .switchIfEmpty(Mono.defer(() ->
                    source.findById(id).flatMap(product ->
                            redis.opsForValue()
                                    .set(key, product, Duration.ofMinutes(5))
                                    .onErrorResume(error -> Mono.just(false))
                                    .thenReturn(product))))
            .onErrorResume(error -> source.findById(id));
}
```

Every fallback needs metrics/logs for Redis errors; otherwise the application can silently push all cache traffic onto the database. Do not apply fallback when Redis is the sole source of business truth or the feature requires fail-closed behavior.

### Cache stampede

When many concurrent requests miss the cache, multiple queries may hit the source simultaneously and all write back to Redis. Reactive I/O does not automatically provide single-flight deduplication or prevent stale refills. Options depending on requirements include concurrency limits, per-key deduplication, TTL jitter, version-aware updates, and reliable invalidation.

## 13. Timeouts, Retries, and Connection Error Handling

When Redis stops responding, the reactive API does not automatically guarantee processing stays within HTTP request SLAs. Distinguish:

- **Connection timeout:** time limit to establish a TCP/TLS connection;
- **Redis command timeout:** time the client waits for a command to complete;
- **Pipeline timeout:** business-rule limit on how long a publisher is allowed to take before emitting a result.

Reactor timeout example:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;

public Mono<String> readWithTimeout(String key) {
    return redis.opsForValue()
            .get(key)
            .timeout(Duration.ofSeconds(1));
}
```

Upon expiration, the publisher emits a timeout error. **A client-side timeout does not guarantee the Redis server did not execute the command.** The command may already have reached Redis and run before the client stopped waiting for the response.

### Retries must consider idempotency

```java
import java.time.Duration;
import reactor.util.retry.Retry;

public Mono<String> readWithRetry(String key) {
    return redis.opsForValue().get(key)
            .timeout(Duration.ofSeconds(1))
            .retryWhen(Retry.backoff(
                    2, Duration.ofMillis(100)));
}
```

This only illustrates the structure; production code must cap retries and **filter for transient errors**, avoiding unconditional retries on authentication, serializer, or permission errors.

| Redis command | Retry after timeout | Risk |
|---|---|---|
| `GET` | Usually relatively safe | Increases load and latency; data may change between attempts |
| `SET key value` | Depends on semantics | Duplicate write can be idempotent, though TTL may be refreshed |
| `DEL key` | Usually idempotent in final state | Deleted key count changes |
| `INCR`/`DECR` | Should not retry blindly | First command may have run, causing double increment/decrement |
| `XADD` | Should not retry blindly | May create duplicate messages |
| Lua with side effects | Depends on script body | Atomicity does not mean safe to retry |

If a critical operation could be executed twice, use an operation ID, idempotency key, or version to detect prior processing.

### Fallback when Redis is only a cache

You can read from the authoritative source if the cache fails:

```java
return redis.opsForValue().get(key)
        .onErrorResume(error -> source.findById(id));
```

Log/emit metrics for fallbacks so a Redis outage does not silently overload the database. Do not apply the same fallback to rate limiting, access control, or values used in financial decisions without evaluating fail-open/fail-closed semantics.

## 14. Do Not Block on the WebFlux Event-Loop

Anti-pattern:

```java
@GetMapping("/users/{id}/status")
public String get(@PathVariable String id) {
    return redis.opsForValue()
            .get("user:status:" + id)
            .block();
}
```

`block()` waits for the publisher on the current thread. In a WebFlux application, this destroys non-blocking benefits, increases latency, and throws errors if called on a thread that disallows blocking.

Keep the publisher across the HTTP boundary:

```java
@GetMapping("/users/{id}/status")
public Mono<String> get(@PathVariable String id) {
    return redis.opsForValue().get("user:status:" + id);
}
```

If a data source is still blocking JDBC:

```java
return Mono.fromCallable(() -> jdbcDao.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
```

This isolates blocking work onto an appropriate scheduler during migration; it **does not turn JDBC into a reactive API**. For high throughput, consider a reactive datasource/driver or clear service boundaries.

`subscribeOn` and `publishOn` do not inherently speed up Redis commands; adding schedulers unnecessarily only increases context switching. Lettuce already performs Redis I/O asynchronously.

## 15. Managing the Connection Factory in Production

A connection factory should be reused and lifecycle-managed by Spring, never created anew per HTTP request.

| Aspect | Must determine |
|---|---|
| Topology | Standalone/Sentinel/Cluster and failover behavior |
| Credentials | Redis ACL user/password, secret rotation, never log secrets |
| TLS | Whether encrypted connections and certificate verification are required |
| Timeout | Connect/command/request timeouts and retry policy |
| Connection reuse | How the driver multiplexes/shares connections |
| Serializer | Consistent key/value wire format between writers and readers |
| Cluster routing | Client slot awareness, topology refresh, and resharding |
| Shutdown | Closing factory/client and background resources via Spring lifecycle |
| Metrics | Command latency, timeouts, reconnects, connection count |

Do not increase connection or thread counts unboundedly. With Lettuce, asynchronous I/O can serve many commands on modest connection resources; optimal tuning depends on throughput, payload size, latency, memory, and actual Redis limits.

If the application connects to two Redis deployments, create two clearly named factories and templates with `@Qualifier` to avoid hitting the wrong cluster. In managed Redis environments, pay attention to TLS, ACLs, and per-tenant connection limits.

## 16. Reactive Redis Does Not Automatically Create Distributed Transactions

A database transaction and a Redis write operate on two separate resources:

```text
SQL BEGIN
    |
    +--> UPDATE database
    |
    +--> Reactive Redis SET (if subscribed)
    |
SQL COMMIT or ROLLBACK
```

If Redis completes its write and SQL rolls back, Redis can retain invalid state. If SQL commits and Redis fails, the cache can go out of sync.

Do not conflate distinct mechanisms:

- `RedisTemplate.setEnableTransactionSupport(true)` on the imperative template;
- `ReactiveRedisTemplate` returning Reactor publishers;
- `@Transactional` using `JpaTransactionManager` or `DataSourceTransactionManager`;
- Reactor transaction context of a `ReactiveTransactionManager`.

They have different lifecycles and contracts. Do not assume an annotation on a Java method places all Redis publishers into the same atomic commit as SQL.

When conditional read-then-update on a Redis key is needed, you can use atomic Redis commands or a Lua script within valid key/slot scope. Still, Redis atomicity does not combine SQL and Redis into one transaction.

If Redis caches database data, choose post-commit invalidation, a transactional outbox, version gating, or retry/reconciliation according to consistency requirements.

## 17. Operation Groups on ReactiveRedisTemplate

String operations example:

```java
Mono<Boolean> wrote =
        redis.opsForValue().set("config:mode", "READY");

Mono<String> loaded =
        redis.opsForValue().get("config:mode");

Mono<Boolean> hasExpiry =
        redis.expire("config:mode", Duration.ofMinutes(3));

Mono<Long> removed =
        redis.delete("config:mode");
```

Hash operations are provided via `opsForHash()`; use appropriate serializers for hash keys/values.

```java
Mono<Boolean> wroteField =
        redis.opsForHash()
                .put("user:42", "status", "ACTIVE");

Mono<?> value =
        redis.opsForHash()
                .get("user:42", "status");
```

Java generic types for hash operations may need explicit specification via `ReactiveHashOperations` to match the template and compiler. Do not assume a DTO value serializer works for every string hash field.

### Scanning keys with Flux

```java
import org.springframework.data.redis.core.ScanOptions;
import reactor.core.publisher.Flux;

Flux<String> keys =
        redis.scan(ScanOptions.scanOptions()
                .match("cache:product:v1:*")
                .count(100)
                .build());
```

`SCAN` does not provide an atomic snapshot: while Redis writes/deletes, it may return duplicate keys or observe a changing key set. In Redis Cluster, understand which node the API scans and how primaries are covered; do not scan the entire keyspace on hot HTTP request paths.

### Backpressure

`Flux` supports downstream demand, but that does **not** mean every Redis command or every downstream system automatically has backpressure guarantees. Limit concurrency when needed:

```java
Flux<String> ids = Flux.just("42", "43", "44");

Flux<ProductSnapshot> products =
        ids.flatMap(id -> cacheService.findById(id), 4);
```

Concurrency `4` is illustrative only. The right number depends on Redis, the database, memory, and downstream speed. If the consumer is slow, merely increasing concurrency can overload the system.

## 18. Common Configuration Mistakes

### ReactiveRedisConnectionFactory not found

Possible causes include a missing reactive starter/client, a connector that only supports imperative mode, excluded auto-configuration, or beans outside Spring component scan scope. Inspect actual dependencies and beans before creating a new factory.

### Multiple connection factories

If both Boot auto-configuration and a manual factory are present, injection can become ambiguous or services may talk to the wrong Redis deployment. Use clear bean names/qualifiers and one configuration source per topology.

### Redis has the key but get() returns empty

Check key serializer, database index, prefix, topology, TTL, whether the publisher was subscribed to, and whether an operator converted an error into empty. Do not jump to the conclusion that Redis lost data.

### SET command does not run

If a service calls `set(...)` and discards the `Mono`, the publisher may never be subscribed to. Return the publisher or chain it into the reactive flow with `flatMap`/`then`.

### block() on the event-loop

If code calls `block()` in a WebFlux controller or runs blocking JDBC directly on the event-loop, throughput and latency can degrade severely. Keep flows non-blocking and isolate only genuinely necessary blocking work.

### Serializer errors after an upgrade

Changing DTO/JSON format while old entries remain in Redis causes deserialization errors. Use versioned key namespaces, migration/TTL, and aligned codecs.

### Timeout followed by retrying side effects

`INCR` or `XADD` may already have run before the caller lost the response. Retrying without an operation ID can cause double increments or duplicate messages.

### Cache fallback hides an outage

`onErrorResume(ex -> Mono.empty())` can turn a Redis connection error into a cache miss. Without metrics, the system is failing while the API appears to respond normally. Classify errors explicitly.

## 19. Observability and Security

A reactive application can handle high concurrent load, so measure both Redis and downstream paths:

| Metric | Meaning |
|---|---|
| Redis command latency | Duration of GET/SET/DELETE by operation |
| Redis error/timeout rate | Connection, timeout, authentication, or command errors |
| Redis reconnect count | Network/failover instability level |
| Cache hit/miss rate | Effectiveness at offloading the primary source |
| Fallback-to-source rate | Traffic falling back to the database during Redis errors |
| Reactor pipeline timeout | HTTP requests exceeding I/O wait thresholds |
| Serializer errors | Mismatch between Redis data and Java DTOs |
| Redis memory/eviction | RAM pressure and keys evicted by eviction policy |
| Connection/event-loop saturation | Client-side resource exhaustion |
| Downstream datasource latency | Avoid blaming Redis for a slow database |

Never log Redis passwords, access tokens, session secrets, or user payloads. In tracing, prefer operation name, duration, error type, and masked/namespaced keys.

Use Redis ACLs to restrict commands and keyspaces to what the service actually needs. If TLS is required, validate certificates properly rather than disabling certificate verification. With multiple instances, account for total connections to Redis, not just a single process's connection count.

## 20. Testing Reactive Redis with StepVerifier

Project Reactor provides `StepVerifier` to verify signals emitted by a `Mono` or `Flux`. Example:

```java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class UserStatusCacheTest {

    private final UserStatusCache cache;

    UserStatusCacheTest(UserStatusCache cache) {
        this.cache = cache;
    }

    @Test
    void writesAndReadsStatus() {
        StepVerifier.create(cache.put("lab-42", "ACTIVE"))
                .expectNext(true)
                .verifyComplete();

        StepVerifier.create(cache.get("lab-42"))
                .expectNext("ACTIVE")
                .verifyComplete();
    }
}
```

This is an illustrative test body; running under Spring requires initializing a test context and injecting `UserStatusCache`, e.g., via `@SpringBootTest`, with a test Redis instance. Do not use production Redis in integration tests.

Scenarios to test:

1. `put()` executes upon subscription, then `get()` returns the data.
2. A non-existent key causes `Mono` to complete empty, without emitting an error.
3. Writing with TTL and verifying key expiration over Redis time.
4. JSON values serialize/deserialize cleanly into `ProductSnapshot`.
5. Redis unavailable: publisher emits an error or runs fallback per contract.
6. Timeouts are bounded, and retries do not duplicate side effects.
7. Concurrent cache misses: how many requests query the source simultaneously.
8. Whether two application versions share compatible key schemas/serializers.
9. Keyspace, Redis database index, and cluster routing match configuration.
10. When a request is canceled, no unexpected fire-and-forget side effects continue running.

### Inspecting with Redis CLI

In an isolated practice environment:

```bash
redis-cli PING
redis-cli SET user:status:lab-42 ACTIVE
redis-cli GET user:status:lab-42
redis-cli TTL user:status:lab-42
redis-cli TYPE user:status:lab-42
```

With JSON templates or custom serializers, `GET` may return JSON or raw bytes, not necessarily a plain readable String. Connect to the right Redis instance/database with proper TLS and auth when inspecting via CLI.

## 21. Guided Hands-On Exercises

### Exercise 1 — Connecting to reactive Redis

Use the Spring Boot Redis and WebFlux starters. Configure a local endpoint and inject `ReactiveRedisConnectionFactory`. Declare `ReactiveRedisTemplate<String,String>` using `RedisSerializationContext.string()`.

Write three publisher-returning APIs:

```java
Mono<Boolean> put(String id, String value);
Mono<String> get(String id);
Mono<Long> delete(String id);
```

Verify `put` with TTL, `get` on a missing key returning empty, and `delete` returning the number of removed keys.

### Exercise 2 — Configuring a JSON serializer

Create `ProductSnapshot` with `sourceVersion`. Declare a template with a string key serializer and a JSON value serializer. Use a schema-versioned namespace, such as `cache:product:v1:42`.

Try writing, reading back, changing a type or adding a field, and determining a migration plan. Compare data read via Redis CLI with data deserialized in Java.

### Exercise 3 — Cache-aside with a reactive source

Create a mock `ReactiveProductSource` with a call counter. Test a cache miss followed by a cache hit and measure source calls. Send multiple concurrent missing requests to observe cache stampede behavior.

### Exercise 4 — Redis disconnection

In a test environment, make Redis unavailable. Test a pipeline with `timeout(...)` and `onErrorResume(...)`. Record error signals, fallback counts, and response times. Never deliberately disrupt connections in production.

### Exercise 5 — Verifying a non-blocking WebFlux path

Write a GET endpoint returning `Mono` directly. Compare it with a version calling `block()` and identify why the second approach does not fit the event-loop. If a data source is still blocking, isolate it at a managed boundary and monitor scheduler saturation.

### Exercise 6 — Retries with side effects

Perform an `INCR` via the reactive Redis API, simulating a client losing the response after the command was sent. Analyze why retrying can double-increment the counter. Design an operation ID or idempotent script and test again in the lab environment.

## 22. Self-Assessment Questions

**1. How does `ReactiveRedisConnectionFactory` differ from `ReactiveRedisTemplate`?**  
The factory provides reactive connections; the template uses those connections together with serializers to execute high-level Redis operations.

**2. Can `LettuceConnectionFactory` provide both imperative and reactive connections?**  
Yes, under supported configurations. However, the two API paths do not automatically share transactions or execution contexts.

**3. Why might calling `set(...)` and discarding the `Mono` fail to write to Redis?**  
Publishers usually only perform I/O upon subscription. Services should return `Mono`/`Flux` or compose them into a reactive chain subscribed to by the framework.

**4. When should you use `ReactiveStringRedisTemplate`?**  
When the application's keys and values both follow a string contract. A typed `ReactiveRedisTemplate` fits when custom serializers or configurations are needed.

**5. Why is RedisSerializationContext important?**  
It determines the bytes for keys, values, and hashes. Two writers with different serializers may target different key bytes even with identical Java Strings.

**6. Does `Mono.empty()` mean Redis cannot be reached?**  
No. Empty means the publisher completed without emitting a value, such as a missing key. Connection failures are typically `onError`.

**7. Why avoid `block()` in a WebFlux handler?**  
It blocks the reactive processing thread, which can degrade throughput and throw errors on event-loop threads.

**8. If `timeout()` emits an error, is it certain the Redis command did not run?**  
No. The command may already have executed before the client lost the response; retrying side effects requires idempotency.

**9. Does ReactiveRedisTemplate make SQL and Redis commit atomically?**  
No. A reactive API does not replace a distributed transaction coordinator.

**10. Does reactive automatically eliminate cache stampedes and stale data?**  
No. You still need caching policies, concurrency limits, version-aware writes, and proper invalidation/repair.

## 23. Implementation Takeaways

- `ReactiveRedisConnectionFactory` is the reactive connection abstraction; `LettuceConnectionFactory` is commonly used to provide the implementation.
- `ReactiveRedisTemplate<K,V>` requires a factory and a `RedisSerializationContext<K,V>` consistent with the Redis wire format.
- String data can use `ReactiveStringRedisTemplate` or `RedisSerializationContext.string()`.
- DTOs need explicit serializers and schema versions; avoid relying on defaults you do not understand.
- WebFlux services should **return `Mono`/`Flux`**, never calling `block()` on the event-loop or arbitrary `subscribe()` calls.
- Distinguish cache misses from Redis errors; timeouts/retries require idempotency considerations and metrics.
- Use a lifecycle-managed singleton connection factory, with environment-appropriate Redis topology, TLS, ACLs, and timeouts.
- Reactive improves I/O efficiency, yet **does not create SQL + Redis transactions**, eliminate race conditions, or guarantee fresh cache data.
- Test publishers with `StepVerifier` and a test Redis instance, covering schemas, timeouts, retries, and failover.

**Successful reactive Redis configuration** is not just about getting Spring to inject the bean: it requires matching serializers, keeping WebFlux threads unblocked, handling errors per business contracts, and maintaining clear operational recovery paths when Redis or upstream data sources fail.

## References

- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html): reactive Redis access model.
- [Spring Data Redis — Template API](https://docs.spring.io/spring-data/redis/reference/redis/template.html): template configuration and operations.
- [Spring Data Redis — Serialization](https://docs.spring.io/spring-data/redis/reference/redis/serializer.html): serializers, RedisSerializationContext, and wire formats.
- [Spring Data Redis — ReactiveRedisTemplate API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/ReactiveRedisTemplate.html): operations and publisher return types.
- [Spring Data Redis — ReactiveRedisConnectionFactory API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/ReactiveRedisConnectionFactory.html): reactive connection contract.
- [Spring Data Redis — LettuceConnectionFactory API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/connection/lettuce/LettuceConnectionFactory.html): Lettuce connection factory.
- [Spring Framework — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): non-blocking endpoints and reactive HTTP.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): Mono, Flux, subscriptions, errors, schedulers, and backpressure.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/): Redis key TTL.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): cursor-based keyspace scanning.
