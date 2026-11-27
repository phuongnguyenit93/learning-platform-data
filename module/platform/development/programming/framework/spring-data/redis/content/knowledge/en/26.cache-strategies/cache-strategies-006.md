# Adding TTL Jitter to Prevent Simultaneous Expirations

In a caching strategy using Spring Data Redis, **TTL (time to live)** defines how long a key is allowed to remain from when it is written or assigned an expiration. TTL removes outdated data and bounds cache size. However, if an application writes tens of thousands of keys in a single batch and assigns **the exact same fixed TTL**, they can also expire almost simultaneously. Many requests then switch from cache hits to cache misses together, forcing the system to reload data from the database or origin service.

One way to mitigate this risk is adding **TTL jitter**: each cache write chooses a slightly different TTL around a baseline or within a configured range. By spreading expiration timestamps over time, cache-rebuild load gets distributed instead of spiking in one short burst.

This lesson focuses on designing jitter ranges, applying them with `RedisTemplate` and Spring Cache using `RedisCacheManager`, testing actual TTLs, and understanding the limits of this technique when caches contain hot data or strict freshness requirements.

## 1. The problem: many keys expiring together cause load spikes

Suppose a service displays 60,000 products. During a new release or a cache-warming job, the application writes nearly all keys into Redis within one minute. Every key receives a fixed 10-minute TTL:

~~~java
redis.opsForValue().set(
    "product:101",
    serializedProduct,
    Duration.ofMinutes(10)
);
~~~

About 10 minutes later, huge numbers of keys reach expiration within the same short interval. The first requests arriving after keys expire must reload products from the data source.

~~~text
Without jitter:

Time             10:00        10:05        10:10        10:15
                  |            |            |            |
Cache write      ██████████
Cache alive      ────────────────────────────
Expired                                      ██████████
Cache misses                                 ▲▲▲▲▲▲▲▲
Database load                                █████████

With jitter:

Time             10:00        10:05        10:09  10:10  10:11
                  |            |            |      |      |
Cache write      ██████████
Expired                                  ░░▒▒▓▓▒▒░░░░░░
Cache misses                             ↑ ↑ ↑ ↑ ↑ ↑ ↑
Database load                            ▒ ▒ ▒ ▒ ▒ ▒
~~~

The diagram illustrates only the general trend. Redis does not guarantee an absolutely uniform spread of expiring keys, and actual cache misses also depend on per-key traffic.

Many keys expiring close together is commonly called a **cache avalanche**. Distinguish it from several related problems:

| Phenomenon | What happens | How far does TTL jitter help? |
| --- | --- | --- |
| **Cache avalanche** | Many keys expire close together, spiking data-source load | Spreads key expiration timestamps apart |
| **Cache stampede / thundering herd** | Many concurrent requests rebuild **one key** that just missed | Does not fully solve it; still need single-flight, locking, or source protection |
| **Cache penetration** | Requests repeatedly query non-existent keys that aren't cached | Does not solve it; consider negative caching, validation, rate limiting |
| **Cache cold start** | Cache is empty after deploy, Redis data loss, or mass deletion | Jitter only helps once data is rewritten; requires warm-up or reload throttling |
| **Cache eviction** | Redis deletes keys due to memory pressure or eviction policy | Jitter does not replace sizing, memory policies, and Redis monitoring |

Thus, TTL jitter is **one defense layer for expiration timing distribution**, not a silver bullet for every kind of cache miss.

## 2. How does jitter vary TTL?

A fixed TTL looks like:

~~~text
TTL = 10 minutes for every key
~~~

With symmetric jitter:

~~~text
baseTTL = 10 minutes
jitter  = 1 minute

Actual TTL per write ∈ [9 minutes, 11 minutes]
~~~

This can be expressed as:

\[
T_i = T_{\text{base}} + U(-J,+J)
\]

Where:

- `T_base` is the baseline TTL from cache policy.
- `J` is the maximum deviation amplitude.
- `U(-J,+J)` is a random value drawn from `-J` to `+J`.
- `T_i` is the TTL applied on the `i`-th write.

If 60,000 keys are written nearly together with an exact 600-second TTL, many expirations cluster around second 600. If each key independently picks a TTL between 540 and 660 seconds, expirations spread across a 120-second window. Assuming uniform distribution and fairly steady access traffic, the average keys expiring per second will be roughly:

\[
\frac{60\,000}{120} \approx 500\ \text{keys/s}.
\]

This is an **expected estimate**, not a hard cap. Randomness, per-key traffic skew, and actual write times can still make some seconds busier than others. Moreover, Redis does not necessarily purge keys physically at the exact millisecond TTL hits 0; accessing an expired key triggers Redis to handle its expiration state.

### Symmetric, additive-only, or subtractive-only jitter?

There are three main styles:

| Policy | Formula | When suitable | Trade-off |
| --- | --- | --- | --- |
| Symmetric | `base ± jitter` | Want spread centered around baseline TTL | Some keys expire earlier and some live longer than baseline TTL |
| Additive only | `base + random(0, J)` | Baseline TTL is the **minimum** lifetime, tolerating longer retention | Data can stay older than the original TTL |
| Subtractive only | `base - random(0, J)` | Baseline TTL is the **hard maximum** staleness bound | Some keys refresh earlier, raising average reload rate |

Never pick a jitter style just because a formula is easy to write. Define the business meaning of `baseTTL`:

- If data **must never be older than 10 minutes**, do not use a policy that stretches TTL to 11 minutes. Choose subtractive-only or enforce a hard cap.
- If data may be up to 12 minutes stale while aiming to refresh around minute 10, symmetric ±1 minute jitter can fit.
- If TTL is tied to sessions, tokens, or permissions, the **business expiration deadline** must be an absolute boundary. Never extend TTL past that time in the name of avalanche prevention.

## 3. Principles for choosing jitter amplitude

Deviation must be wide enough to spread expirations without undermining data freshness semantics.

Example policy:

~~~yaml
cache:
  product:
    base-ttl: 10m
    max-jitter: 1m
~~~

This is an illustrative application configuration, **not built-in Spring Boot properties**. If used, the application must bind and apply these parameters via `@ConfigurationProperties` or custom configuration.

Questions to decide:

1. **What is the maximum allowed staleness?** If the data contract requires freshness within 10 minutes, actual TTL must never exceed 10 minutes.
2. **What is the shortest tolerable reload interval?** Overly wide jitter can expire many keys too early and raise source read frequency.
3. **Are there seasonal spikes or batched cache-warming runs?** TTL jitter helps most when writes cluster closely in time.
4. **Is traffic heavily skewed across keys?** A single ultra-hot key still needs dedicated stampede mitigation even when other keys' TTLs are spread out.
5. **Is cache refreshed on every read or only on write?** If using time-to-idle (TTI) or continuous TTL renewal, expiration distribution rules must account for that behavior.

There is no single percentage valid for every application. You can begin testing with roughly 5–15% of baseline TTL for caches that aren't ultra-freshness-sensitive, then tune using real metrics. This is a **benchmarking starting point**, not a Spring Data Redis guaranteed default.

## 4. Building a reusable TTL jitter policy

We create a Java class whose sole job is generating valid TTLs within bounds. Each call to `nextTtl()` picks a new offset. The code uses Java 21, `Duration`, and `ThreadLocalRandom`:

~~~java
package com.example.redis.cache;

import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.ThreadLocalRandom;

public final class TtlJitterPolicy {

    private final long baseMillis;
    private final long maxDeviationMillis;

    public TtlJitterPolicy(Duration base, Duration maxDeviation) {
        Objects.requireNonNull(base, "base");
        Objects.requireNonNull(maxDeviation, "maxDeviation");

        long baseMs = base.toMillis();
        long deviationMs = maxDeviation.toMillis();

        if (baseMs <= 0) {
            throw new IllegalArgumentException(
                "Base TTL must be at least one millisecond"
            );
        }
        if (deviationMs < 0 || deviationMs >= baseMs) {
            throw new IllegalArgumentException(
                "Jitter must be non-negative and smaller than base TTL"
            );
        }

        // Prevent overflow when computing maximum TTL bound.
        Math.addExact(baseMs, deviationMs);
        this.baseMillis = baseMs;
        this.maxDeviationMillis = deviationMs;
    }

    public Duration nextTtl() {
        if (maxDeviationMillis == 0) {
            return Duration.ofMillis(baseMillis);
        }

        // nextLong(origin, bound) excludes bound.
        // +1L lets both endpoints -J and +J be selectable.
        long offsetMillis = ThreadLocalRandom.current().nextLong(
            -maxDeviationMillis,
            maxDeviationMillis + 1L
        );

        return Duration.ofMillis(baseMillis + offsetMillis);
    }
}
~~~

Usage:

~~~java
TtlJitterPolicy policy = new TtlJitterPolicy(
    Duration.ofMinutes(10),
    Duration.ofMinutes(1)
);

Duration ttl1 = policy.nextTtl();
Duration ttl2 = policy.nextTtl();
Duration ttl3 = policy.nextTtl();

// Each value lies in [9 minutes, 11 minutes].
// Values may repeat due to random sampling.
~~~

Constructor checks avoid zero/negative TTLs and millisecond `Duration` overflow. Since this example uses millisecond precision, it isn't suited for sub-millisecond requirements; multi-minute lifetimes here have no such constraint.

`ThreadLocalRandom` fits concurrent cache-writing threads without locking a shared PRNG. It is not a cryptographic PRNG; TTL jitter does not need token-grade security.

### Why not generate a single value at bean creation time?

The snippet below looks like jitter yet **does not spread TTLs across keys**:

~~~java
Duration oneTimeTtl = policy.nextTtl();

// Defeats the purpose if oneTimeTtl is reused for all keys:
for (String key : keys) {
    redis.opsForValue().set(key, "value", oneTimeTtl);
}
~~~

Choosing one random value once and reusing it for every key simply shifts the entire batch expiration earlier or later together. **TTL must be computed on every write** (or at least per key per design policy), especially during bulk cache warming.

## 5. Applying directly with `StringRedisTemplate`

In Spring Data Redis, `opsForValue().set(key, value, Duration)` sets the value and expiration in one Redis operation. This fits applications managing caches directly via `RedisTemplate`.

Example cache storing JSON strings serialized by the business layer:

~~~java
package com.example.redis.cache;

import java.time.Duration;
import java.util.Objects;
import java.util.function.Supplier;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSummaryCache {

    private final StringRedisTemplate redis;
    private final TtlJitterPolicy ttlPolicy = new TtlJitterPolicy(
        Duration.ofMinutes(10),
        Duration.ofMinutes(1)
    );

    public ProductSummaryCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void put(String productId, String summaryJson) {
        Objects.requireNonNull(productId);
        Objects.requireNonNull(summaryJson);

        String key = "cache:product-summary:" + productId;
        Duration ttl = ttlPolicy.nextTtl(); // Pick a fresh TTL for the key.

        // Redis writes value and TTL in one operation.
        redis.opsForValue().set(key, summaryJson, ttl);
    }

    public String getOrLoad(
            String productId,
            Supplier<String> loadJsonFromSource) {
        String key = "cache:product-summary:" + productId;

        String hit = redis.opsForValue().get(key);
        if (hit != null) {
            return hit;
        }

        // Cache miss: fetch data from source.
        String loaded = Objects.requireNonNull(loadJsonFromSource.get());
        redis.opsForValue().set(key, loaded, ttlPolicy.nextTtl());
        return loaded;
    }
}
~~~

For a typical cache, the flow is:

~~~text
Request looking up product
         |
         v
   GET cache key
    /         \
   hit        miss
    |          |
    v          v
Return value  Read database/service
               |
               v
          Compute fresh TTL
               |
               v
         SET key value PX/EX TTL
               |
               v
            Return value
~~~

The `getOrLoad` example shows **where to apply TTL jitter**. It does not yet stop multiple requests missing the same key from invoking `loadJsonFromSource.get()` together. If that product is very hot, add cache stampede protection from the previous lesson.

### Setting TTL together with the value

Avoid splitting into two commands:

~~~java
redis.opsForValue().set(key, value);
redis.expire(key, ttlPolicy.nextTtl());
~~~

Between `SET` and `EXPIRE`, if the process dies or the network fails, the key can remain without the desired TTL. Whenever the API supports it, use directly:

~~~java
redis.opsForValue().set(key, value, ttlPolicy.nextTtl());
~~~

Redis `SET` supports expiration directly within the write command; Spring Data Redis issues the appropriate operation with duration. This is **atomic for writing a single key's value and expiration**. It does not make fetching from the database and writing cache into a single transaction.

## 6. Applying with Spring Cache and `RedisCacheManager`

Many Spring Boot applications use `@Cacheable`, `@CachePut`, and `@CacheEvict` instead of calling `RedisTemplate` directly:

~~~java
@Cacheable(cacheNames = "productSummaries", key = "#productId")
public String loadSummary(String productId) {
    return productService.fetchSummaryJson(productId);
}
~~~

With Redis as backend, Spring Cache routes through `RedisCacheManager`. Static per-cache TTL is simple, yet if all entries are written together, they can still expire close together.

For **Spring Data Redis 3.2 and later**, `RedisCacheConfiguration` accepts a **TTL function** via `entryTtl(...)` to decide the lifetime per cache entry. A policy can be configured as follows:

~~~java
package com.example.redis.cache;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class RedisCacheJitterConfiguration {

    @Bean
    TtlJitterPolicy ttlJitterPolicy() {
        return new TtlJitterPolicy(
            Duration.ofMinutes(10),
            Duration.ofMinutes(1)
        );
    }

    @Bean
    RedisCacheManager cacheManager(
            RedisConnectionFactory factory,
            TtlJitterPolicy policy) {

        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .disableCachingNullValues()
                .entryTtl((key, value) -> policy.nextTtl());

        return RedisCacheManager.builder(factory)
            .cacheDefaults(defaults)
            .build();
    }
}
~~~

The lambda `(key, value) -> policy.nextTtl()` is evaluated whenever a cache entry is written. This gives writes distinct TTLs even when generated by the same `@Cacheable` method.

**These two configurations are not equivalent:**

~~~java
// Fixed TTL: policy is called once when constructing configuration.
RedisCacheConfiguration.defaultCacheConfig()
    .entryTtl(policy.nextTtl());

// Dynamic TTL: policy is called on each cache write.
RedisCacheConfiguration.defaultCacheConfig()
    .entryTtl((key, value) -> policy.nextTtl());
~~~

In real deployments:

- Confirm your Spring Data Redis version supports TTL functions. On older versions, consider `RedisTemplate` or a verified custom cache writer.
- Defining a custom `RedisCacheManager` bean affects Spring Boot auto-configuration. Re-apply serializers, key prefixes, null caching, transaction awareness, and any other project settings.
- The example applies one policy to **every cache** managed by that manager. Systems with product caches, permission caches, and config caches should assign per-type TTL policies rather than copying one policy everywhere regardless of business needs.
- For non-`String` values, define serializers and cross-version compatibility so cached entries deserialize accurately.

### Applying jitter only to selected cache regions

For instance, `productSummaries` tolerates 9–11 minutes of staleness, while `featureFlags` must update faster. Instead of one global policy, declare per-cache-name configurations:

~~~java
TtlJitterPolicy productPolicy = new TtlJitterPolicy(
    Duration.ofMinutes(10), Duration.ofMinutes(1)
);

RedisCacheConfiguration productConfig =
    RedisCacheConfiguration.defaultCacheConfig()
        .entryTtl((key, value) -> productPolicy.nextTtl());

RedisCacheConfiguration featureConfig =
    RedisCacheConfiguration.defaultCacheConfig()
        .entryTtl(Duration.ofSeconds(30));

RedisCacheManager manager = RedisCacheManager.builder(factory)
    .withInitialCacheConfigurations(java.util.Map.of(
        "productSummaries", productConfig,
        "featureFlags", featureConfig
    ))
    .build();
~~~

This snippet demonstrates the manager builder API; inside `@Configuration`, merge it into your actual manager bean instead of creating redundant `RedisCacheManager` beans.

Spring Cache does not offer a standard per-call annotation like `@Cacheable(ttl = random)`. The **cache manager/writer configuration** decides entry TTL in the setup above.

## 7. Repositories and `@TimeToLive`: using entities as cache

Some systems use **Spring Data Redis Repositories** with `@RedisHash` for short-lived data. In that case, entity TTL can be expressed with `@TimeToLive`:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("temporary-products")
public class TemporaryProduct {

    @Id
    private String id;

    private String name;

    @TimeToLive
    private Long ttlSeconds;

    public TemporaryProduct() {
    }

    public TemporaryProduct(String id, String name, long ttlSeconds) {
        this.id = id;
        this.name = name;
        this.ttlSeconds = ttlSeconds;
    }
}
~~~

When creating an entity, the application can set `ttlSeconds` using a jitter policy in seconds and save via repository:

~~~java
long seconds = 600
    + java.util.concurrent.ThreadLocalRandom.current()
        .nextLong(-60, 61); // 540..660 seconds

repository.save(new TemporaryProduct(
    "p-101", "Redis Guide", seconds
));
~~~

In the repository model, `@TimeToLive` marks a property holding the entity's TTL. It differs from `@Indexed` (secondary index) and `@Transient` (excluded from mapping). When the repository reads the entity back, the TTL property may reflect **remaining lifetime** of the key depending on mapping config and read timing.

If the app already sets a fixed TTL via `@RedisHash(timeToLive = ...)`, clarify which source governs the final TTL; never attach multiple TTL mechanisms without understanding precedence. For standard `@Cacheable` caching, apply jitter in `RedisCacheManager` rather than adding `@TimeToLive` to DTOs not managed by Redis Repositories.

## 8. Never violate business expiration deadlines

TTL jitter must never extend data past safety boundaries. For example, a voucher is valid only until 18:00; at 17:55, the application must not assign a 10–11 minute TTL and continue treating the voucher as valid after 18:00.

Define two limits:

1. **Performance-oriented cache TTL**, with jitter.
2. **Actual remaining validity of the data**, from now until the deadline.

Final TTL must never exceed the business deadline:

\[
TTL_{\text{effective}}
= \min\left(TTL_{\text{jitter}},\
T_{\text{deadline}}-T_{\text{now}}\right)
\]

If remaining time is non-positive, skip caching or handle expiration per business logic.

Example:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;

public Duration boundedTtl(
        TtlJitterPolicy policy,
        Instant validUntil,
        Clock clock) {

    Duration remaining =
        Duration.between(clock.instant(), validUntil);

    if (remaining.isZero() || remaining.isNegative()) {
        return Duration.ZERO; // Caller must skip cache write.
    }

    Duration candidate = policy.nextTtl();
    return candidate.compareTo(remaining) <= 0
        ? candidate
        : remaining;
}
~~~

Usage:

~~~java
Duration ttl = boundedTtl(policy, voucherValidUntil, clock);
if (ttl.compareTo(Duration.ZERO) > 0) {
    redis.opsForValue().set(key, voucherJson, ttl);
}
~~~

`Clock` makes deadline math testable without relying on wall-clock time. However, advancing a Java `Clock` does not advance Redis's clock; testing actual expiration still requires real Redis and real elapsed time or an appropriate abstraction.

### Absolute freshness vs. sliding TTL

Even with jitter, if every cache hit extends the expiration time, data can persist far past when it was originally fetched from the source. Distinguish between:

- **Write-based TTL**: key expires after the chosen duration from creation/update.
- **Time-to-idle (TTI)**: an access can renew the lifetime if supported and enabled.
- **Absolute source freshness**: data must be fetched fresh after a hard interval regardless of read count.

If a requirement says "no older than 10 minutes since source validation," store and check the source timestamp or a hard deadline; TTL alone can fall short if reads renew the key.

## 9. Does jitter actually prevent cache stampedes?

Suppose a popular product receives 2,000 requests/second and lives in **one Redis key**. When that key expires, hundreds of requests can simultaneously see a miss before the first request finishes reloading it.

TTL jitter only changes **when** a key expires, not **how many requests rebuild** that key concurrently upon a miss.

~~~text
                    Hot key expires
                          |
            +-------------+-------------+
            |             |             |
           Req A         Req B         Req C ... Req N
            |             |             |
          GET miss      GET miss      GET miss
            |             |             |
          DB query      DB query      DB query
            |             |             |
           SET           SET           SET
~~~

For a hot key, pair TTL jitter with:

| Measure | Purpose | Note |
| --- | --- | --- |
| **In-JVM single-flight** | Requests in the same process share one load per key | Protects only within one instance |
| **Distributed lock** | Only one instance gets the right to rebuild the key at a time | Needs lock timeout, ownership, and proper error handling |
| **Stale-while-revalidate** | Return stale data briefly while updating in background | Use only when business permits stale |
| **Refresh-ahead** | Rebuild key before expiration | Cap refresh jobs and avoid synchronized bursts |
| **Rate limit / backpressure** | Protect database or upstream when misses rise | Must have clear fallback behavior |
| **Rate-limited cache warming** | Gradually preload critical data before peak traffic | Must not overload upstream during warm-up |

A system with many expiring keys plus a few ultra-hot keys usually needs **both TTL distribution and single-key reload protection**.

## 10. Be careful with how random values are chosen

### Compute jitter per write, not once per batch

When writing a batch of 1,000 keys:

~~~java
for (CacheEntry entry : entries) {
    Duration ttl = policy.nextTtl();
    redis.opsForValue().set(entry.key(), entry.value(), ttl);
}
~~~

Each iteration picks an independent TTL. Pulling `ttl = policy.nextTtl()` outside the loop gives the whole batch the exact same TTL again.

With pipelining, the same idea holds—pick a TTL per command:

~~~java
redis.executePipelined(
    (org.springframework.data.redis.core.SessionCallback<Object>) ops -> {
        for (CacheEntry entry : entries) {
            ops.opsForValue().set(
                entry.key(),
                entry.value(),
                policy.nextTtl()
            );
        }
        return null;
    }
);
~~~

`CacheEntry` in the example is a type holding `key` and `value`, e.g., a Java record:

~~~java
public record CacheEntry(String key, String value) {
}
~~~

Pipelining cuts network round-trips, yet does not turn the batch into a transaction. To bound response memory and latency when writing huge key counts, split pipelines into bounded chunks rather than queuing infinitely.

### Do not re-jitter TTL on read requests

Without new data, continually assigning a new TTL just because a request read the key can unintentionally extend cache lifetime. Apply TTL jitter on **actual writes or refreshes**, aligned with the cache freshness policy.

### Does randomness need to be strictly "fair"?

No. The goal is decorrelating expiration timestamps across keys. A simple, independent, bounded distribution is enough to start. For massive systems with concurrent batches, evaluate distribution via metrics rather than assuming randomness always yields a perfect spread.

Sometimes **key-stable jitter** is helpful (e.g., deterministic hashing of the key into buckets) so the same key keeps a fixed offset across writes. This can be convenient in certain systems, though coarse buckets risk grouping keys onto the same offset. Choose deterministic jitter only when reproducibility or partitioned expiration windows are needed; per-write randomness is simpler for general caches.

## 11. Testing TTL policies without relying on exact sleeps

Testing should separate two goals:

1. **Policy unit test**: verify generated TTLs are positive and within range.
2. **Redis integration test**: verify TTL is actually attached to keys on write.

Never create a 10-minute key and make tests sleep 10 minutes to verify it. Tests only need to read remaining lifetime right after writing; a separate test for actual expiration can use a short TTL and timed polling.

### 11.1. Unit test for TTL range

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class TtlJitterPolicyTest {

    @Test
    void returnsPositiveTtlWithinConfiguredRange() {
        TtlJitterPolicy policy = new TtlJitterPolicy(
            Duration.ofMinutes(10),
            Duration.ofMinutes(1)
        );

        for (int i = 0; i < 1000; i++) {
            Duration ttl = policy.nextTtl();
            assertThat(ttl)
                .isBetween(Duration.ofMinutes(9), Duration.ofMinutes(11));
        }
    }

    @Test
    void rejectsJitterThatCanProduceNonPositiveTtl() {
        assertThatThrownBy(() -> new TtlJitterPolicy(
            Duration.ofSeconds(30),
            Duration.ofSeconds(30)
        )).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void zeroJitterKeepsBaseTtl() {
        TtlJitterPolicy policy = new TtlJitterPolicy(
            Duration.ofMinutes(10), Duration.ZERO
        );

        assertThat(policy.nextTtl()).isEqualTo(Duration.ofMinutes(10));
    }
}
~~~

This test verifies **bounds across all samples**; it does not assert that 1,000 draws must hit the exact min, max, or 1,000 distinct values. Assertions expecting exact random outcomes produce flaky tests.

### 11.2. Integration test with real Redis

The example below uses Spring Boot, JUnit 5, Spring Data Redis, and Testcontainers. The test creates an isolated key, assigns a jittered TTL, and reads back remaining TTL in milliseconds.

With Gradle Groovy and dependency versions managed by Spring Boot:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

~~~java
package com.example.redis.cache;

import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest(classes = TtlJitterRedisIntegrationTest.TestApp.class)
class TtlJitterRedisIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisConnection(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
    }

    @Autowired
    StringRedisTemplate redis;

    @Test
    void writesValueWithBoundedRandomTtl() {
        String key = "test:ttl-jitter:" + UUID.randomUUID();
        TtlJitterPolicy policy = new TtlJitterPolicy(
            Duration.ofMinutes(10), Duration.ofMinutes(1)
        );

        try {
            redis.opsForValue().set(key, "cached", policy.nextTtl());

            assertThat(redis.opsForValue().get(key)).isEqualTo("cached");

            Long remaining = redis.getExpire(
                key, TimeUnit.MILLISECONDS
            );

            // Allow latency between SET and PTTL on CI machines.
            // Still tight enough to catch missing or wrong TTLs.
            assertThat(remaining)
                .isNotNull()
                .isGreaterThan(Duration.ofMinutes(8).toMillis())
                .isLessThanOrEqualTo(Duration.ofMinutes(11).toMillis());
        } finally {
            redis.delete(key);
        }
    }
}
~~~

In Redis, `PTTL` (and `getExpire(key, TimeUnit.MILLISECONDS)`) returns `-1` if the key exists without expiration, or `-2` if the key does not exist. Hence a positive TTL assertion catches writes that forgot to set expiration. Never assert remaining TTL equals the **exact** assigned duration, because time elapses between the two commands.

### 11.3. Testing expiration behavior separately

If the goal is confirming the key disappears after expiration, use a shorter TTL and bounded polling:

~~~java
redis.opsForValue().set(
    key, "short-lived", Duration.ofMillis(1200)
);

org.awaitility.Awaitility.await()
    .atMost(Duration.ofSeconds(8))
    .pollInterval(Duration.ofMillis(50))
    .untilAsserted(() ->
        assertThat(redis.opsForValue().get(key)).isNull()
    );
~~~

This illustration needs the test dependency `org.awaitility:awaitility` if not already present. Polling finishes as soon as the condition passes, instead of calling `Thread.sleep(...)` for a fixed duration and inferring state from a single read.

**Testing a jitter policy does not require running a benchmark inside the JUnit test.** Benchmarks measuring load-distribution impact should run separately against representative workloads and real server/database metrics.

## 12. Monitoring the effectiveness of TTL jitter

To tell whether jitter actually dampens load spikes, measure several metrics before and after enabling it. A pretty TTL histogram alone does not prove database load dropped.

| Metric | What to observe |
| --- | --- |
| Cache hit rate / miss rate over time | Are synchronized miss spikes gone after batch writes? |
| Expiring keys per time interval | Are expiration timestamps better distributed? |
| Database/upstream QPS | Did load peaks at cache-miss intervals drop? |
| API p95/p99 latency | Do users still hit slow windows near expiration marks? |
| Rebuild count for the same key | Is there a hot-key stampede needing its own fix? |
| Redis memory, evictions, and CPU | Did raising TTL bounds keep more keys alive and add memory pressure? |
| Actual TTL at write time | Is randomness actually applied per entry rather than chosen once? |

Redis exposes diagnostics like `INFO stats` with `expired_keys`, `keyspace_hits`, and `keyspace_misses`. These are **cumulative counters**; compute deltas between observations to derive per-interval rates. Also, `expired_keys` reflects Redis's expiration activity, not a complete log of every key hitting TTL 0 at exact precision.

At the application layer, you can record a histogram of chosen TTLs and miss/refill counters:

~~~java
Duration ttl = policy.nextTtl();

// Example metric names; recording depends on your observability stack.
// cache.ttl.assigned.seconds: distribution of assigned lifetimes
// cache.miss.count: number of misses
// cache.refill.duration: time to rebuild data

redis.opsForValue().set(key, value, ttl);
~~~

Do not turn high-cardinality IDs/keys into per-key metric labels. Group by cache name, data type, or TTL policy to avoid overloading the monitoring system.

### Evaluating by workload type

Measure at least two scenarios:

1. **Synchronized warm-up:** write many keys in a short window, then send requests near their expiration times.
2. **Realistic workload:** keys created/updated at staggered times, mixing hot and cold keys, with representative hit/miss ratios.

If traffic to expired keys is sparse, spreading TTL may barely affect actual load. If most traffic hits a single hot key, jitter across thousands of cold keys does not replace single-flight for that hot key.

## 13. Common mistakes

| Symptom | Possible cause | Fix |
| --- | --- | --- |
| Keys still expire together despite randomness | Picked one random TTL at bean startup and reused for all keys | Pick a fresh TTL **on every cache entry write** |
| Cached longer than business rules allow | Positive jitter exceeded freshness cap | Use subtractive-only jitter or cap against deadline |
| Cache misses rose before baseline TTL | Symmetric jitter expired some keys early | Re-evaluate minimum TTL and refill load |
| Requests still slam DB together | A single hot key expired and many threads missed together | Add single-flight/lock/refresh-ahead |
| No TTL found on key | Wrote `SET` without expiration, or overwrote key dropping TTL | Use `opsForValue().set(key, value, Duration)` |
| `@Cacheable` still has fixed TTL | Cache manager only configured `entryTtl(Duration)` | Use per-entry TTL function if supported by version |
| Tests occasionally fail | Asserted PTTL equals exact assigned TTL or slept near boundary | Use tolerance bounds and timed polling |
| Redis memory grew after adding jitter | Keys live longer than before | Lower max TTL, switch to subtractive jitter, or resize capacity |
| Jitter didn't help after `FLUSHALL`/cache loss | Cache emptied immediately before expiration phase | Design dedicated warm-up/refill throttling |
| Every key refreshes on read | Time-to-idle policy alters expiry distribution | Clarify TTL vs. TTI and cap total data age |
| Batch writes choke database during warm-up | Source queried concurrently at load time | Limit concurrency, batch size, and warm-up QPS |
| Cache write retries extend TTL unintentionally | `SET` with expiration sets a fresh deadline | Redesign with absolute deadlines if required |

## 14. Adopting in a real project

A practical rollout can start with the cache showing the clearest spike load:

1. **Measure baseline:** record cache load times, miss spikes, database QPS, p95/p99 API latency, and Redis memory.
2. **Define freshness contract:** max TTL, valid min TTL, and differences between transactional data and display-only data.
3. **Choose distribution and amplitude:** symmetric, additive-only, or subtractive-only; ensure positive TTLs within deadlines.
4. **Apply policy at the exact write path:** `RedisTemplate`, `RedisCacheManager` TTL function, or entity `@TimeToLive` property.
5. **Add reload limits:** single-flight for hot keys and database backpressure on misses.
6. **Test:** unit test TTL bounds, integration test PTTL, verify bulk writes assign distinct TTLs per entry.
7. **Observe results:** compare miss graphs, p95/p99, and upstream load before/after; tune jitter based on data.

Example policy table:

| Data type | Baseline TTL | Suggested jitter to test | Constraint |
| --- | --- | --- | --- |
| Slowly changing product catalog | 10 minutes | ±1 minute | Allows up to 11 minutes lifetime |
| Time-insensitive recommendations | 30 minutes | +0–5 minutes additive | Tolerates up to 35 minutes staleness |
| Product prices needing freshness within 5 min | 5 minutes | -0–30 seconds subtractive | Never extend beyond 5 minutes |
| Permissions/tokens | Per actual validity period | Only within deadline cap | Never exceed validity or weaken security |
| Negative cache for non-existent IDs | 15 seconds | -0–3 seconds subtractive | Must handle newly created data |

These parameters only illustrate policy definition; real systems must evaluate data update traits, freshness requirements, and read traffic.

## 15. Conclusion

Adding TTL jitter is a simple yet effective technique for **staggering expiration times** across many keys in Spring Data Redis. Rather than applying the same TTL to batches of entries written closely together, the application chooses an independent, bounded lifetime on each write. This smooths out cache-miss spikes and rebuild load when many keys come due simultaneously.

To apply it well, distinguish baseline TTL from **business freshness limits**, choose amplitudes that never yield invalid TTLs, recompute jitter **per entry**, and write values together with expiration in a single Redis operation. In Spring Cache, configure a TTL function on `RedisCacheManager` when supported; with `RedisTemplate` pass `Duration` directly; with Redis Repositories control TTL on the entity.

Finally, jitter alone does not stop concurrent requests from rebuilding a single hot key, does not solve cold starts, and does not replace capacity planning for Redis/databases. Pairing it with refill throttling, single-flight where needed, real-Redis TTL tests, and operational metrics makes your caching strategy far more resilient.
