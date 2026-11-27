# Namespace Isolation and Safe Test Data Cleanup in Spring Data Redis

## 1. Why Isolate Data When Testing Redis?

Redis persists state outside the JVM. Unlike a local variable scoped to one test, Redis keys survive after a test finishes, after a Spring `ApplicationContext` closes, or when another CI job starts using the same Redis server.

Suppose two integration tests share a key:

```text
Test A:
  SET product:SKU-001 "Blue pen"
  Verify reading back the same value

Test B:
  GET product:SKU-001
  Expect the key not to exist
```

If Test A runs first, Test B fails. Under parallel execution, outcomes depend on command interleaving, producing **flaky tests**—unpredictable failures that are hard to reproduce. Worse, a test “cleaning up” with `FLUSHALL` can wipe data belonging to sibling tests, local services, or an unintended Redis server.

Therefore, a trustworthy Spring Data Redis suite needs two layers of protection:

1. **Isolation:** test keys, caches, repositories, Streams, and Redis resources must never collide with or disturb data outside their own scope.
2. **Safe cleanup:** delete only the resources the test created, never issuing broad wipes without confirming the test owns the entire Redis server.

Key distinction: **namespace isolation and Redis server isolation operate at different levels**. Unique prefixes prevent most naming collisions, yet cannot stop another test from exhausting memory, running `FLUSHDB`, altering `CONFIG`, or saturating connections. When stronger isolation is needed, use dedicated Redis containers/instances.

## 2. Learning Objectives

By the end of this lesson, you will know how to:

- Choose the right isolation level: per test method, test class, test suite, CI job, or Redis container.
- Name namespaces with unique identifiers and distinguish namespaces from Redis logical databases.
- Enforce explicit key prefixes for `StringRedisTemplate`, `RedisTemplate`, and `RedisCacheManager`.
- Use Testcontainers to run real Redis without touching dev or production instances.
- Delete tracked keys via a registry, and handle operations that generate auxiliary keys indirectly.
- Use bounded `SCAN` when cleaning by prefix, avoiding `KEYS` and `FLUSHALL` on shared Redis.
- Avoid leaving behind Redis Repository secondary indexes, consumer groups, TTL shadow copies, or Pub/Sub subscriptions.
- Structure `@BeforeEach`/`@AfterEach`, failure cleanup, parallel runs, and CI around the principle: **delete only what you own**.

This guide focuses on **testing Spring Data Redis applications**. Never use production Redis as a “temporary sandbox,” even if you intend to delete keys afterward.

---

## 3. Redis Isolation Levels

Isolation options vary in protection and overhead:

| Level | Example | What It Protects | Limitations |
|---|---|---|---|
| Unique key | `test:sku:UUID` | Prevents overwriting one specific key | Other keys, cache indexes, and server config stay shared |
| Per-method namespace | `it:runId:methodId:*` | Prevents collisions in parallel runs | Shares memory, DB, config, Pub/Sub |
| Per-class namespace | `it:classId:*` | Easy to reuse container/context | Methods still need distinct keys/IDs or cleanup |
| Separate logical Redis DB | DB 1, DB 2 | Separates keyspaces on standalone Redis | Same server and resources; Cluster usually uses DB 0 only |
| Dedicated Redis container | Testcontainers with independent keyspace | Isolates data and most configuration | Startup, CPU/RAM cost; still shares host |
| Dedicated job Redis deployment | Per-job Redis in CI | Isolates jobs and replicates topologies | Infra cost; requires lifecycle management |

### Practical Defaults

- **Mocked Redis unit tests:** create no server keys, require no cleanup.
- **Simple integration tests:** one Redis container per test class or suite, unique prefix/ID per test.
- **Spring Cache and Redis Repository tests:** dedicated containers are usually safer than deleting individual keys, since frameworks generate auxiliary keys.
- **Redis Cluster/Sentinel tests:** dedicated topology deployments, never the team's shared Redis.
- **Tests against a shared staging Redis:** unique namespaces, restricted ACL delete permissions, controlled cleanup, never `FLUSHDB`.

**Selection rule:** the harder it is to enumerate every key a test creates, the more you should lean toward container- or deployment-level isolation.

## 4. What Is a Namespace?

In Redis, a namespace is typically a **key-prefixing convention**, such as:

```text
app:environment:component:resource-id
```

Redis has no physical folders or schemas separated by `:`. Two keys:

```text
it:run-01:products:SKU-01
it:run-02:products:SKU-01
```

are completely independent keys because their bytes differ. Colons simply help humans and tools read key segments.

Recommended integration-test namespace structure:

```text
it:<run-id>:<test-class>:<test-method>:<logical-key>
```

Examples:

```text
it:7f63aa1:ProductCacheIT:cacheMiss:SKU-001
it:7f63aa1:ProductCacheIT:cacheHit:SKU-001
it:7f63aa1:CartRepositoryIT:saveCart:user-31
```

You can substitute UUIDs for method names if test names contain accents, unstable characters, or exceed reasonable lengths:

```text
it:4fcae0b2-...:8db13f2a-...:SKU-001
```

### Essential Requirements

1. Test prefixes have a **clear delimiter**, usually ending in `:`.
2. Run/test IDs are generated by the test runner, never relying solely on potentially colliding timestamps.
3. Keys built by application code follow the **same prefixing rule**, with no hidden branch writing global unprefixed keys.
4. Parallel tests never share a mutable key unless explicitly testing contention.
5. Cleanup touches only the prefix assigned to that test.
6. Key names never embed passwords, tokens, emails, or sensitive data.

Unsafe example:

```text
test*
```

Deleting with that pattern can match `test-a`, `testing-shared`, or non-test namespaces. Better:

```text
it:4fcae0b2:*
```

using a strong identifier owned strictly by the current run.

---

## 5. Dedicated Namespaces Are Not Absolute Protection

Two tests with distinct prefixes still share server resources:

```text
Redis instance (shared)
  ├── it:run-A:*      <-- Test A
  ├── it:run-B:*      <-- Test B
  └── app:local:*     <-- Another application
```

These actions still cross-contaminate despite separate prefixes:

- Test A runs `FLUSHALL` or `FLUSHDB`.
- Test A fills memory, causing Redis to evict B's keys.
- Test A runs a slow Lua script, stalling B's commands.
- Test A changes server-level `notify-keyspace-events` or `maxmemory-policy`.
- Test A opens many blocking clients, straining connections.
- Test A runs `CONFIG SET` during an experiment without reverting.
- Test A triggers failover or restarts the shared node.

Therefore, **key-prefix isolation protects naming; instance isolation protects data and configuration at a deeper level**. For destructive, resilience, memory-pressure, or config-mutating tests, always use a dedicated Redis.

## 6. Redis Logical Databases Do Not Replace Namespaces

Standalone Redis supports `SELECT` to switch logical databases:

```redis
SELECT 1
SET it:products:SKU-01 example
```

Keys in DB 1 are separate from identically named keys in DB 0. Spring Boot configures this via:

```yaml
spring:
  data:
    redis:
      database: 1
```

Keep in mind:

- Logical DBs separate only key names, not process, CPU, or memory resources.
- `FLUSHALL` wipes all logical DBs on the server.
- `FLUSHDB` wipes the entire **current DB**, not just the test's prefix.
- Two tests both choosing DB 1 still overwrite each other's keys.
- Redis Cluster supports only DB 0 in standard Cluster deployments.
- Some managed Redis offerings restrict logical DB counts or `SELECT`.
- Connecting to the wrong DB can cause cleanup to delete unintended data.

Thus, even when using a separate DB, retain prefixes and explicit test endpoints. **Never treat `SELECT 1` as license to run broad wipes** on a shared server.

---

## 7. Simplest Approach: Dedicated Redis Container via Testcontainers

In integration tests, Testcontainers spins up a temporary Redis server exclusively for testing. It binds a dynamic host port, avoiding collisions with any Redis running locally.

### 7.1. Dependencies

Gradle Kotlin DSL example for Spring Boot:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:testcontainers")
}

tasks.test {
    useJUnitPlatform()
}
```

When using the Spring Boot BOM or project dependency management, versions are managed centrally. Otherwise, specify compatible Testcontainers versions.

Testcontainers requires Docker or a compatible container runtime locally and in CI.

### 7.2. Spring Boot Integration Test Using Real Redis

**`RedisNamespaceIsolationIT.java`**

```java
package com.example.redis;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.UUID;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
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

@Testcontainers
@SpringBootTest(
        classes = RedisNamespaceIsolationIT.TestApplication.class
)
class RedisNamespaceIsolationIT {

    private static final int REDIS_PORT = 6379;

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine")
            ).withExposedPorts(REDIS_PORT);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(REDIS_PORT)
        );
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApplication {
    }

    @Autowired
    StringRedisTemplate redis;

    private String prefix;
    private String key;

    @BeforeEach
    void allocateNamespace() {
        prefix = "it:" + UUID.randomUUID() + ":";
        key = prefix + "product:SKU-1";
    }

    @AfterEach
    void cleanupOnlyMyKey() {
        if (key != null) {
            redis.delete(key);
        }
    }

    @Test
    void eachTestUsesItsOwnRedisKey() {
        redis.opsForValue().set(key, "Notebook");

        assertThat(redis.opsForValue().get(key))
                .isEqualTo("Notebook");
    }

    @Test
    void aFreshNamespaceDoesNotSeePreviousTestData() {
        assertThat(redis.hasKey(key)).isFalse();

        redis.opsForValue().set(key, "Pen");

        assertThat(redis.opsForValue().get(key))
                .isEqualTo("Pen");
    }
}
```

Here:

- `@Container` manages Redis for the test class.
- `@DynamicPropertySource` pulls the actual endpoint from Testcontainers.
- `@BeforeEach` allocates a fresh UUID so every test gets an independent key.
- `@AfterEach` deletes only **the key owned by the test**.
- `FLUSHDB` is unnecessary because each test has its own key name.
- Tests never depend on leftover keys from prior tests.

Pick a Redis image version matching your project and test compatibility during upgrades. The tag shown is illustrative; pin versions intentionally rather than pulling `latest`.

### 7.3. Mind Spring Context and Container Lifecycles

Spring Test may **cache `ApplicationContext` instances** across test classes with identical configurations. If a `@Container static` stops after one class while the cached `RedisConnectionFactory` is reused by another class, the context points to a stopped container.

Choose a consistent lifecycle strategy:

- Align container and context lifecycles per class; if context sharing causes mismatches, separate contexts or manage context lifecycles explicitly.
- Or run a suite-wide shared Redis container whose lifecycle genuinely spans the whole suite.
- Leverage Spring Boot's Testcontainers integration when supported, verifying container and context lifecycles stay aligned.
- Avoid spinning up a fresh container per method needlessly; use namespaces to isolate methods inside one container.

**Per-class containers** cut collisions, yet do not guarantee Spring beans rebuild unless context caching is accounted for.

---

## 8. Apply Namespaces at the Right Layer of the Application

A common mistake is adding a prefix only in test code while production code still writes unprefixed keys:

```java
// Test wants "it:UUID:product:SKU-1",
// yet production service always writes:
String key = "product:" + sku;
```

As a result, tests still collide on `product:SKU-1`.

Solve this by extracting key naming into a configurable component.

### 8.1. A Small Keyspace Abstraction

**`RedisKeyspace.java`**

```java
package com.example.redis;

public final class RedisKeyspace {

    private final String prefix;

    public RedisKeyspace(String prefix) {
        if (prefix == null || prefix.isBlank()
                || !prefix.endsWith(":")) {
            throw new IllegalArgumentException(
                    "Redis prefix must be non-empty and end with ':'"
            );
        }

        this.prefix = prefix;
    }

    public String key(String namespace, String id) {
        return prefix + namespace + ":" + id;
    }

    public String prefix() {
        return prefix;
    }
}
```

Service using `RedisKeyspace`:

```java
package com.example.redis;

import org.springframework.data.redis.core.StringRedisTemplate;

public class ProductCacheAdapter {

    private final StringRedisTemplate redis;
    private final RedisKeyspace keyspace;

    public ProductCacheAdapter(
            StringRedisTemplate redis,
            RedisKeyspace keyspace
    ) {
        this.redis = redis;
        this.keyspace = keyspace;
    }

    public void save(String sku, String name) {
        redis.opsForValue().set(
                keyspace.key("products", sku),
                name
        );
    }

    public String get(String sku) {
        return redis.opsForValue().get(
                keyspace.key("products", sku)
        );
    }
}
```

In development/production config, wire a `RedisKeyspace` bean with an app-managed prefix. In integration tests, pass a `RedisKeyspace("it:UUID:")` to the exact adapter under test.

The key benefit is that **the same production code** executes the key-naming rule, rather than tests forging keys separately.

### 8.2. Control Special Characters in IDs

If tests use framework-generated IDs, normalize or encode them before concatenating keys. For instance, an ID containing `:` does not break Redis itself, yet can confuse parsing/logging tools.

When cleaning up via prefix patterns, ensure **test prefixes never contain glob characters** like `*`, `?`, or `[`, which carry special meaning in Redis patterns. UUIDs, hex strings, or alphanumeric-plus-hyphen strings are safe choices.

## 9. Isolation at Method, Class, and Test-Run Scopes

No single prefix scope fits all suites. Consider:

### 9.1. Unique Prefix per Test Method

```text
it:<run-id>:<class-id>:<method-id>:*
```

Pros: allows parallel method execution with zero key collisions. Cons: if the prefix bean is created once per Spring context, you need a safe way to pass per-method namespaces into services.

**Never mutate a static/global prefix variable during parallel tests** if methods share a singleton bean; one method will hijack another's namespace.

### 9.2. One Prefix per Test Class

```text
it:<class-id>:*
```

Fits sequential test classes that clean state between methods. Under parallelism or with Spring Cache/Redis Repositories, also keep per-test key IDs unique.

### 9.3. One Prefix per CI Job or Test Run

```text
it:build-481:*
```

Makes it easy to audit leftover keys if a job crashes before cleanup. Still, separate keys internally when multiple methods share a run prefix.

### 9.4. Scope Selection Table

| Scope | Structure | When to Use |
|---|---|---|
| Per method | Unique UUID per test | Parallel tests, independent state |
| Per class | Unique UUID per class | Shared Redis container, clean method teardown |
| Per suite | Run ID + component | Multiple classes needing suite-wide cleanup |
| Per CI job | Build ID + namespace | Tracking orphaned resources after aborted jobs |
| Per container | Dedicated Redis instance | Frameworks generating auxiliary keys, server config tests |

**Never derive test IDs solely from static class/method names across runs.** If a prior run aborted violently, stale keys break the next run. Add a random run ID or fresh container.

---

## 10. Prefer Exact Deletion of Keys Created by the Test

The safest cleanup when keys are known up front is **deleting from a tracked list**.

Example lightweight helper:

**`RedisTestKeys.java`**

```java
package com.example.redis;

import java.util.LinkedHashSet;
import java.util.Set;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;

public final class RedisTestKeys {

    private final String prefix =
            "it:" + UUID.randomUUID() + ":";

    private final Set<String> created = new LinkedHashSet<>();

    public String newKey(String logicalName) {
        String key = prefix + logicalName;
        created.add(key);
        return key;
    }

    public String prefix() {
        return prefix;
    }

    public void cleanup(StringRedisTemplate redis) {
        if (!created.isEmpty()) {
            redis.delete(created);
            created.clear();
        }
    }
}
```

JUnit usage:

```java
class ProductRedisIT {

    @Autowired
    StringRedisTemplate redis;

    RedisTestKeys keys;

    @BeforeEach
    void setup() {
        keys = new RedisTestKeys();
    }

    @AfterEach
    void teardown() {
        keys.cleanup(redis);
    }

    @Test
    void storesValue() {
        String key = keys.newKey("product:SKU-1001");
        redis.opsForValue().set(key, "Pen");

        assertThat(redis.opsForValue().get(key))
                .isEqualTo("Pen");
    }
}
```

This snippet illustrates lifecycle and cleanup; JUnit, AssertJ, and Spring imports depend on your test setup.

### Why Register Keys Before Writing?

`newKey(...)` records the key in the registry **before** the Redis `SET` command runs. If Redis persists the key yet the app hits a timeout receiving the reply, `@AfterEach` still knows to delete that key.

If you register keys only **after** `set(...)` returns successfully, keys written before a timeout/exception slip past cleanup.

### Deleting Multiple Keys

`redis.delete(created)` deletes a known collection of keys. In Redis Cluster, multi-key commands obey slot rules; driver/Spring Data Redis support varies by version. When keys span multiple slots, delete keys one by one in tests or use a topology-aware method.

`DEL`/`UNLINK` are idempotent regarding absent keys: deleting a non-existent key never creates anything. That makes cleanup resilient when tests abort mid-way.

**Limitation:** the registry tracks only explicitly registered keys. If a Redis Repository, Lua script, cache writer, or listener spawns auxiliary keys, the registry alone misses them.

## 11. `@AfterEach` and `try/finally` Ensure Cleanup After Failed Assertions

JUnit Jupiter runs `@AfterEach` after ordinary test methods even when assertions fail or exceptions are thrown. Placing cleanup in `@AfterEach` is therefore much safer than putting it at the end of the test body:

```java
@Test
void unsafeCleanupPlacement() {
    redis.opsForValue().set(key, "test");

    assertThat(redis.opsForValue().get(key))
            .isEqualTo("different-value");

    // The assertion above fails, so this line never runs.
    redis.delete(key);
}
```

Proper placement:

```java
@AfterEach
void cleanup() {
    if (key != null) {
        redis.delete(key);
    }
}
```

For temporary keys allocated inside helper methods, use `try/finally`:

```java
String key = allocateTestKey();

try {
    redis.opsForValue().set(key, "value");
    assertThat(redis.opsForValue().get(key))
            .isEqualTo("value");
} finally {
    redis.delete(key);
}
```

### When Cleanup Still Cannot Run

No `@AfterEach` hook can guarantee execution if:

- The JVM is killed abruptly (`SIGKILL`).
- The CI host loses power or the runner is terminated.
- The process crashes fatally.
- Connectivity to Redis drops.
- Redis itself crashed before cleanup.

Therefore, add a **second line of defense**: apply reasonable TTLs to test keys, give Redis containers bounded lifecycles, or run controlled stale-namespace reaper jobs. Never rely solely on teardown code to keep a long-lived shared Redis clean forever.

---

## 12. TTL as a Safety Net, Not a Replacement for Active Cleanup

You can write test keys with a TTL:

```java
redis.opsForValue().set(
        key,
        "sample",
        java.time.Duration.ofMinutes(10)
);
```

If the JVM dies before `@AfterEach`, the key expires automatically after 10 minutes.

However:

- TTL **does not** remove keys right when the test ends.
- Too short a TTL can make keys vanish mid-test on slow runners, causing false failures.
- Too long a TTL leaves garbage piling up across many test runs.
- Certain update/overwrite commands clear or alter TTL; know Redis semantics.
- Auxiliary keys from Redis Repositories, cache indexes, or Streams may not receive identical TTLs.
- Test data expiring mid-test can mask real bugs.
- Subscribed listeners hold separate resources unaffected by key TTLs.

Thus, TTL is strictly a **safety net**, not a substitute for deleting created keys or isolating containers.

### Never Use TTL to “Prove Cleanup”

An `@AfterEach` test verifying cleanup should check explicit `delete` behavior or let the harness inspect state immediately. A key expiring on its own proves nothing about cleanup execution.

---

## 13. When Do You Need `SCAN` for Prefix Cleanup?

Some tests cannot predict every physical key generated—for example:

- Spring Cache generating keys via `CacheManager`.
- Redis Repositories creating entity keys and secondary indexes.
- Lua scripts creating multiple keys (within declared scopes).
- Stream flows or auxiliary components creating metadata.
- Multiple service operations sharing a test namespace.

Without a fixed key list, consider **scanning by prefix with `SCAN`**.

Redis CLI:

```redis
SCAN 0 MATCH it:2ec5f83b:* COUNT 200
```

Redis returns a cursor and a batch of keys per iteration. Continue until the cursor returns to `0`.

### Why Avoid `KEYS`?

```redis
KEYS it:2ec5f83b:*
```

`KEYS` is O(N) over the entire keyspace and blocks Redis in a single command. On a tiny dedicated integration container the cost may look negligible, yet cleanup utilities should stay safe if ever reused against larger datasets.

**Prefer deleting known keys; when prefix cleanup is necessary, use bounded `SCAN` with strict scope guards.**

### `SCAN` Does Not Inspect Only Prefixed Keys

`SCAN MATCH prefix*` still walks the Redis keyspace via cursor buckets to find matches. `COUNT` is a **work-per-iteration hint**, not a cap on total deleted keys.

Keep in mind:

- An iteration can return an empty list while the cursor is still non-zero.
- A key may appear more than once across iterations; deletion must be idempotent.
- If concurrent writers modify keys mid-scan, there is no atomic snapshot.
- One `SCAN` pass can miss newly created keys if writers are still active.
- On Redis Cluster, scanning may require iterating per node depending on driver/topology.

Therefore, to guarantee a namespace is completely wiped, **stop active writers/listeners in that namespace first**, then clean and verify inside an isolated environment.

---

## 14. Example Prefix Cleanup with Spring Data Redis

This example uses `StringRedisTemplate` for UTF-8 string keys:

**`RedisPrefixCleaner.java`**

```java
package com.example.redis;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class RedisPrefixCleaner {

    private final StringRedisTemplate redis;

    public RedisPrefixCleaner(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long deleteOwnedPrefix(String ownedPrefix) {
        if (ownedPrefix == null
                || !ownedPrefix.matches(
                        "it:[0-9a-fA-F-]{36}:[A-Za-z0-9:_-]+:"
                )) {
            throw new IllegalArgumentException(
                    "Refusing to scan an unowned or broad prefix"
            );
        }

        ScanOptions options = ScanOptions.scanOptions()
                .match(ownedPrefix + "*")
                .count(200)
                .build();

        long deleted = 0;

        try (Cursor<String> cursor = redis.scan(options)) {
            List<String> batch = new ArrayList<>();

            while (cursor.hasNext()) {
                String key = cursor.next();

                // Extra safeguard: accept only keys matching the owned prefix.
                if (!key.startsWith(ownedPrefix)) {
                    throw new IllegalStateException(
                            "Unexpected key outside owned prefix"
                    );
                }

                batch.add(key);

                if (batch.size() >= 100) {
                    deleted += deleteBatch(batch);
                    batch.clear();
                }
            }

            if (!batch.isEmpty()) {
                deleted += deleteBatch(batch);
            }
        }

        return deleted;
    }

    private long deleteBatch(List<String> keys) {
        // Delete one key at a time: avoids cross-slot multi-key constraints in Redis Cluster.
        long deleted = 0;

        for (String key : keys) {
            Boolean existed = redis.delete(key);
            if (Boolean.TRUE.equals(existed)) {
                deleted++;
            }
        }

        return deleted;
    }
}
```

This snippet assumes a Spring Data Redis version supporting `StringRedisTemplate.scan(ScanOptions)` and `Cursor<String>`. On older APIs or different drivers/topologies, adapt cursor iteration accordingly.

**Safety limits of this example:**

- `ownedPrefix` strictly requires a standard UUID after `it:` plus a specific namespace segment ending with `:`.
- Refuses empty prefixes, `*`, or overly broad `it:`.
- Deletes keys individually to avoid cross-slot multi-key errors.
- Never executes `FLUSHDB` or `FLUSHALL`.
- Intended as a helper for **explicitly allocated test namespaces**, not a production Redis admin tool.
- `SCAN` on Redis Cluster has client/topology caveats; use supported per-node scanning when cluster tests truly require keyspace-wide cleanup.

### Serializer Compatibility

`StringRedisTemplate` scans and deletes string keys using its String serializer. If the app writes keys using a `RedisTemplate` with a binary serializer (e.g., JDK serialization), inspecting via CLI or scanning with a String template may fail to match.

When mixing templates, verify the actual physical key bytes. An identical Java prefix **does not mean identical raw Redis key bytes** when serializers differ.

### Prefix Cleanup Should Be a Last Resort

If a test knows the 5 keys it wrote, 5 direct deletes are clearer and safer than scanning the entire keyspace. Reserve `SCAN` for cases where frameworks or flows create dynamic keys.

---

## 15. Preventing Accidental Deletion with an “Ownership Guard”

Before running any prefix cleanup, verify these checks:

1. **Endpoint:** is the Redis server genuinely a test environment?
2. **Scope:** does the prefix belong to this run/test?
3. **Structure:** is the prefix narrow, with a UUID and trailing delimiter?
4. **Commands:** does it use only `DEL`/`UNLINK` on exact matching keys?
5. **Concurrency:** are any writers still writing into this namespace?
6. **Serializer:** does the cleaner encode keys identically to the producer?
7. **Topology:** is this running standalone or Cluster?
8. **Observability:** is the expected key count known so anomalies stand out?

Example guard:

```java
if (!key.startsWith("it:" + runId + ":")) {
    throw new IllegalStateException(
            "Cleanup would touch a key outside this test run"
    );
}
```

Never write:

```java
if (key.contains("test")) {
    redis.delete(key);
}
```

The substring `test` can easily appear in ordinary application keys.

### Dry-Run Mode for Broad Cleanup Tools

If building a cleanup helper for shared environments, support a **dry-run listing expected keys** without deleting. Allow deletion only after confirming the prefix belongs to the job.

For automated tests, strict UUID prefixes and dedicated containers provide far stronger safety than manual dry-run confirmation.

---

## 16. `FLUSHDB` and `FLUSHALL`: Use Only When Redis Is Truly Dedicated

Redis provides:

```redis
FLUSHDB
FLUSHALL
```

Meaning:

- `FLUSHDB`: deletes **every key in the currently selected logical DB**.
- `FLUSHALL`: deletes **every key across every logical DB** in the Redis instance.

Many tests put `FLUSHDB` in `@BeforeEach` for “clean state” because it is effortless. That becomes dangerous the moment an endpoint is misconfigured or shared.

### When Is It Acceptable?

Only when **all** of these hold:

- The Redis server/container is **strictly dedicated to the test**, holding no user or sibling-test data.
- The endpoint has been verified to be a test endpoint.
- Safeguards ensure only the test controls that server.
- Wiping is an intentional part of the test lifecycle.
- No parallel test shares that container while relying on its own state.

Even on dedicated containers, namespaced keys and targeted cleanup produce clearer failure diagnostics. `FLUSHDB` can reset a completely disposable container **between non-parallel phases**, yet should never become the default for every integration test.

### Never Claim “It’s DB 1, So `FLUSHDB` Is Safe”

A shared local Redis can hold another developer's or process's data in DB 1. A DB number confers zero exclusive ownership. And on Redis Cluster, logical DBs collapse to DB 0 anyway.

---

## 17. `DEL` vs. `UNLINK` During Cleanup

Both `DEL` and `UNLINK` remove keys by name:

```redis
DEL it:abc:product:SKU-1
UNLINK it:abc:product:SKU-1
```

Primary difference:

- `DEL` removes keys and reclaims memory synchronously inside the command.
- `UNLINK` detaches the key from the keyspace immediately and reclaims value memory asynchronously in the background.

For a handful of small keys in integration tests, `DEL` is simple and sufficient. For thousands of keys or huge values, `UNLINK` avoids blocking Redis while freeing structures.

Spring Data Redis exposes corresponding `unlink(...)` APIs, though support and multi-key behavior depend on template/driver versions. Match commands to your actual Redis version.

**Do not confuse “`UNLINK` returned” with “all memory reclamation completed.”** The key is gone from the keyspace immediately, while memory reclamation continues in the background.

In ordinary test cleanup, assert **the key is no longer accessible**, not that `RSS`/`used_memory` drops instantaneously.

---

## 18. Spring Cache: `RedisCacheManager` Prefixes Can Differ from Service Key Names

With Spring Cache:

```java
@Cacheable(cacheNames = "products", key = "#p0")
public ProductView getProduct(String sku) {
    return gateway.load(sku);
}
```

The Redis key is not necessarily `products:SKU-1`. `RedisCacheManager` formats keys using `RedisCacheConfiguration`, prefixes, and serializers—for instance:

```text
products::SKU-1
```

If a test tries deleting only:

```java
redis.delete("SKU-1");
```

the real cache entry stays untouched.

### 18.1. Configuring a Suite-Specific Prefix

Example:

```java
@Configuration
@EnableCaching
public class TestRedisCacheConfiguration {

    @Bean
    RedisCacheManager cacheManager(
            RedisConnectionFactory factory
    ) {
        String prefix = "it:01234567-89ab-4cde-8fab-0123456789ab:";

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .computePrefixWith(
                                name -> prefix + "cache:" + name + "::"
                        )
                        .entryTtl(Duration.ofMinutes(5));

        return RedisCacheManager.builder(factory)
                .cacheDefaults(defaults)
                .build();
    }
}
```

The prefix above is illustrative. In real tests, allocate a fresh UUID per **context/container/suite** from a controlled source rather than hardcoding the same UUID across every CI run.

`computePrefixWith(...)` determines the prefix used by the cache writer for puts and evictions. Thus, calling `@CacheEvict(allEntries = true)` in tests clears only entries under that configured prefix.

### 18.2. Evict Single Entries or Clear the Whole Cache?

- When the logical key is known, invoke `@CacheEvict(key = ...)` through the Spring proxy or `Cache.evict(key)`.
- When clearing the entire cache, ensure the **cache prefix belongs strictly to the test**; `Cache.clear()` can scan/delete many Redis keys via `KEYS` or `SCAN` batch strategies.
- If multiple tests share a cache name/prefix, one test's `clear()` wipes entries needed by parallel tests.

**Warning:** changing only the logical test key without isolating the cache manager prefix does not isolate `allEntries = true`. Any `clear()` wipes every entry under that shared cache name regardless of key ID.

### 18.3. Per-Method Dynamic Prefixes and Spring Singletons

`RedisCacheManager` is normally a singleton bean configured at context startup. Never have two parallel test methods mutate a shared global prefix variable while calling the cache manager.

Solutions:

- Separate contexts/containers for tests that must clear entire cache regions.
- Distinct cache names per test when configuration permits and each test stays within its own name.
- Unique key IDs while avoiding `allEntries = true` whenever tests share a cache name.
- Run tests sequentially if they genuinely must share one cache manager/namespace.

---

## 19. Redis Repositories: Deleting the Entity Does Not Mean `DEL` Cleans Auxiliary Keys

A Redis Repository can create several kinds of keys:

- The entity's Hash.
- Secondary indexes for `@Indexed` fields.
- Other mapping/metadata depending on repository configuration.
- Auxiliary keys supporting TTL and expiration events in certain setups.

Example:

```java
@RedisHash("orders")
public class Order {

    @Id
    private String id;

    @Indexed
    private String status;

    // ...
}
```

An entity with ID `test-123` is stored as a Hash and referenced inside the secondary index for `status`.

If a test runs a raw delete:

```java
redis.delete("orders:test-123");
```

auxiliary indexes are not guaranteed to update as they do on repository deletion.

### Preferred Cleanup Path

When repositories are managed by Spring Data Redis:

```java
@AfterEach
void cleanupRepositories() {
    for (String id : createdOrderIds) {
        orderRepository.deleteById(id);
    }
}
```

Cleaning through the repository lets Spring Data Redis update secondary indexes according to repository logic.

Beyond that, when tests must guarantee zero leftover auxiliary metadata, use a **dedicated Redis container** or reconciliation tailored to your exact repository/version.

### Unique IDs and Namespaces Are Still Needed

If an entity's keyspace is hardcoded via `@RedisHash("orders")`, adding a prefix to `StringRedisTemplate` will not automatically prefix Redis Repository keys.

You can generate unique IDs:

```java
String id = "it-" + UUID.randomUUID();
```

yet secondary indexes can still share keys per keyspace and field value—for example, multiple tests indexing `status=ACTIVE`. Thus, **unique entity IDs do not guarantee every auxiliary key created by the repository is isolated**.

For tests verifying indexes, expiration, and cleanup, dedicated Redis containers or test-configured repository keyspaces give stronger isolation.

---

## 20. Redis Repositories with TTL and Shadow Copies

When entities use `@RedisHash(timeToLive = ...)` or `@TimeToLive`, Spring Data Redis may register expiration listeners and, in certain configurations, store a **shadow copy/phantom key** so expiration events still carry the entity payload.

Consequences:

- The primary entity Hash may expire while auxiliary keys linger briefly.
- Keyspace events may not be processed immediately if Redis or the app disconnects.
- Secondary indexes may require post-expiration cleanup.
- Checking only that the primary hash vanished does not prove all auxiliary keys are gone.
- Relying on a 1-second TTL to “wipe all repository state” is an unsafe assumption.

When testing TTL Repositories:

1. Provision a dedicated Redis container/namespace.
2. Use unique entity IDs.
3. Choose a TTL large enough for reliable execution.
4. Assert the business outcome of expiration.
5. Never use raw `DEL` on a guessed key to replace repository cleanup.
6. Let container teardown discard any remaining auxiliary keys unless needed.
7. If listeners or schedulers are active, stop or close their lifecycles before assuming the namespace is quiet.

**Never alter `notify-keyspace-events` on a shared Redis just to test a TTL annotation.** When tests need expiration events, use a dedicated Redis instance configured explicitly.

---

## 21. Redis Streams: Isolating Keys and Consumer Groups

A Redis Stream stores records alongside consumer group metadata. Stream tests commonly use named resources:

```text
Stream key:    it:run-42:orders:events
Group:         integration-test-workers
Consumer:      worker-1
```

Sharing a Stream key across tests causes collisions:

- Test A reads records produced by Test B.
- Test A trims the Stream, dropping B's backlog.
- Test A creates the same group name, causing Test B to hit `BUSYGROUP`.
- A consumer processes/ACKs records outside its own scenario.
- `$` or `0-0` offsets pick up history from another test.

### How to Isolate

Create a unique Stream key per test:

```java
String streamKey =
        "it:" + UUID.randomUUID() + ":orders:events";
```

You can vary group names too, yet **changing only the group name does not isolate** tests sharing the same Stream key, because both share the same record log and retention.

### Stream Cleanup

When both the Stream key and groups belong solely to the test, deleting the **Stream key** removes all entries and attached group metadata per Redis semantics. However:

- Never delete the Stream while listeners/containers are still reading or writing.
- Stop/cancel consumers and close subscriptions/containers first.
- If a background job recreates the Stream key, deleting early risks “resurrection” by the still-running writer.
- When tests inspect pending/ACK state, run assertions before deleting state.

Safe cleanup order:

```text
1. Stop test producers.
2. Stop test consumers/listeners.
3. Wait for in-flight callbacks to finish.
4. Delete Stream keys owned by the test namespace.
5. Close connections/containers.
```

If a test attaches a consumer group to a shared Stream owned by another system, never delete that Stream key; destroy only the test's own group when ownership is clear and commands are supported.

---

## 22. Redis Pub/Sub: Channels Are Not Keys You Can Delete

Redis Pub/Sub uses channels:

```text
it:run-42:order-events
```

Channel names route messages, yet a Pub/Sub channel **is not a stored key** you can remove with `DEL`. Proper cleanup here means:

- Unsubscribing.
- Stopping the test's `RedisMessageListenerContainer` or subscriptions.
- Closing/releasing connections.
- Ensuring no asynchronous callbacks deliver late messages after the test finishes.
- Using isolated channels so test listeners never pick up traffic from other apps.

### Use Dedicated Channels and Patterns

Example:

```java
String channel =
        "it:" + UUID.randomUUID() + ":notifications";
```

When using `PatternTopic`, avoid overly broad patterns like `*` or `__keyevent@0__:*` unless specifically needed. Broad patterns capture events from unrelated tests or services.

### Pub/Sub Has No Replay

Publishing before a subscriber finishes registering loses messages. Synchronize listener readiness with bounded signals/latches instead of `Thread.sleep(100)`.

These are **lifecycle isolation** concerns—they cannot be solved by Redis key prefixes alone.

---

## 23. Lua Scripts, Redis Functions, and Auxiliary Keys

A Redis script is typically invoked via:

```java
redis.execute(
        script,
        List.of(testKey),
        arguments...
);
```

If the script only mutates the registered `testKey`, cleanup is simple. Scripts touching multiple keys—such as:

```text
it:run-42:quota:user-1
it:run-42:quota:index
it:run-42:quota:metadata
```

require an explicit contract covering **every key the script can modify**.

### Things to Control

- All keys stay inside the test's namespace.
- Every accessed key is declared properly in `KEYS` per Redis scripting rules.
- In Redis Cluster, all keys for one script invocation satisfy hash-slot rules.
- Avoid scripts constructing global unnamespaced keys dynamically.
- If a script writes auxiliary metadata, register those keys for cleanup or use a dedicated container.
- Remember `SCRIPT LOAD`/script caches and Redis Functions are server-level resources outside the keyspace; deleting keys does not clean them up.

For Redis Functions, loading/deleting function libraries affects the whole server. Tests mutating function libraries must run against a dedicated Redis instance, never shared workloads.

### Dangerous Actions When Testing Scripts

Never run a long-looping Lua script or scan huge keysets on a shared server just to simulate faults. Long-running Redis scripts block all other clients on that node.

---

## 24. Other Resources That Need Proper Type-Specific Cleanup

Redis tests create more than plain String keys:

| Resource | Isolation Approach | Safe Cleanup Approach |
|---|---|---|
| String/hash/set/zset | Key prefix + UUID | `DEL`/`UNLINK` owned keys |
| Spring Cache | Test cache prefix or cache name | `evict` exact entry or `clear` inside isolated namespace |
| Redis Repository | Unique IDs/keyspace, dedicated container if needed | `repository.deleteById`, container teardown for auxiliary keys |
| Redis Stream | Dedicated Stream key | Stop consumers, then delete Stream key |
| Consumer group | Dedicated Stream + group | Delete owned Stream or destroy owned group |
| Pub/Sub | Dedicated channel | Unsubscribe/stop listeners |
| Keyspace notifications | Dedicated Redis instance if changing config | Restore config only if exclusively owned |
| Lua script state | Explicitly declared keys | Delete every key mutated by the script |
| Redis Function library | Dedicated instance | Teardown instance or delete library if exclusively owned |
| Lock key | Prefix + UUID | Release via matching ownership/token |
| Rate-limit counter | Unique subject/policy namespace | Delete key afterward; TTL backup |
| Transaction/pipeline state | Isolated connection lifecycle | Finish/discard transaction, close/release connection |
| Connection pool/listener threads | Scoped bean/context lifecycle | Close/stop during teardown |

**Never delete a lock owned by another component just because its name contains “test.”** Release locks only when owner tokens match, especially under concurrent workers.

---

## 25. Parallel Test Execution: Subtle Collisions to Watch For

JUnit can execute test methods or classes concurrently depending on configuration. Even with distinct keys per method, collisions still occur over shared resources.

Example:

```text
Test A:
  Cache name = products
  Redis prefix = products::
  @CacheEvict(allEntries = true)

Test B:
  Cache name = products
  Redis prefix = products::
  Testing cache hit on a different SKU
```

Test A clears the entire cache and triggers an unexpected cache miss in Test B, even though their SKUs differ.

### Parallel Testing Rules

1. Allocate unique namespaces per test or non-overlapping group.
2. Avoid sharing cache names/prefixes whenever any test calls `clear()`.
3. Never have two methods mutate a shared static prefix variable.
4. Never modify shared Redis server configs in non-deterministic order.
5. Never call `FLUSHDB` to reset state inside a parallel suite.
6. Stop background workers/listeners before cleanup.
7. When sharing state intentionally to test concurrency, document boundaries and expected invariants explicitly.
8. If isolation is impossible, run that group sequentially or give it a dedicated container.

### Spring Context Caching Is Also Shared State

Singleton beans like `RedisCacheManager`, `RedisKeyspace`, or listeners persist across test classes when Spring reuses contexts. If a bean holds mutable prefixes or cached state, context reuse introduces cross-test interference.

Keep configurations immutable per context lifecycle, or isolate contexts for tests needing modified settings.

---

## 26. When a Test Suite Is Killed Mid-Run: Handling Orphaned Data

`@AfterEach` is never guaranteed to run on hard aborts. On a shared test Redis, aborted CI jobs leave keys behind:

```text
it:old-run-1:...
it:old-run-2:...
it:current-run:...
```

Mitigations:

### 26.1. Prefer Disposable Containers

If each job owns its Redis container with proper lifecycle management, CI/runner teardown removes all data along with the container. Still account for orphaned containers when runners crash hard.

### 26.2. Attach Backup TTLs to Test Keys

Where features allow, give test keys a TTL long enough to outlast normal test execution yet shorter than acceptable garbage retention.

### 26.3. Controlled Stale-Namespace Reaper Jobs

If a long-lived shared test Redis is unavoidable, build a reaper scanning `it:<run-id>:*` only for runs verified as finished.

Requirements:

- Authoritative, reliable tracking of run IDs.
- Only clean up runs confirmed finished/expired.
- Never guess “stale” keys purely from UUID text without trusted metadata.
- Clean with strict prefixes, dry-run support, and rate limits.
- Never touch prefixes of active runs.
- Log deleted key counts and alert on unusual spikes.

This is an operational tool for **test infrastructure**, not an excuse for tests to leak permanent keys recklessly.

---

## 27. Isolation When Testing `@CacheEvict` and Repository Deletion

Two deletion operations often cause confusion:

### 27.1. Single-Entry Cache Eviction

```java
@CacheEvict(cacheNames = "products", key = "#p0")
public void evictProduct(String sku) {
}
```

When the cache manager uses a unique prefix, single-key eviction is relatively straightforward to isolate.

### 27.2. Region-Wide Cache Eviction

```java
@CacheEvict(cacheNames = "products", allEntries = true)
public void evictAll() {
}
```

This directs the cache writer to delete **every entry matching that cache region's prefix**, not just keys created by this method. If the cache name is shared, sibling tests break.

### 27.3. Repository Deletion

`repository.deleteById(id)` updates secondary indexes, whereas raw `redis.delete("key")` leaves stale index entries behind.

Therefore:

| Behavior Under Test | Preferred Teardown |
|---|---|
| Caching a single SKU | Evict the exact key or delete test-owned key |
| Clearing an entire cache | Dedicated cache prefix, context, or container |
| Saving/updating Redis Repository | Repository delete for all created IDs |
| Complex secondary indexes + TTL | Dedicated container rather than raw entity-hash `DEL` |
| Stream consumer group | Stop consumers, then delete owned stream |
| Pub/Sub listener | Stop/unsubscribe, never `DEL` the channel |

---

## 28. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Hardcoding `product:1` across all tests | Order-dependent tests and parallel failures | Unique prefix + UUID per test |
| Running `FLUSHALL` in `@BeforeEach` | Wipes entire Redis instance, risking non-test data | Use disposable test-owned containers; prefer key-level cleanup |
| Running `FLUSHDB` assuming DB index isolation | Wipes sibling data in same DB; breaks on Cluster | Dedicated namespaces and containers |
| Cleaning up with `KEYS test*` | Heavy full scan and overly broad pattern | Bounded `SCAN` with strict UUID prefix or key registry |
| Using `StringRedisTemplate` to scan binary keys written by another template | Fails to find/delete keys | Align key serializers or clean via the creating API |
| Calling raw `DEL` on a Redis Repository hash | Leaves stale secondary indexes | Use repository delete or dedicated container |
| Relying on TTL to clean all state | Auxiliary keys/listeners linger | Active cleanup plus container teardown |
| UUID entity IDs sharing one cache prefix | `allEntries=true` wipes sibling test data | Dedicated cache prefixes, avoid shared clears |
| Mutable static namespace across parallel tests | Methods overwrite each other's prefixes | Immutable per-context namespaces or per-test dependencies |
| Forgetting to stop Stream listeners | Deleted keys get recreated immediately | Stop/cancel producers and consumers before cleanup |
| Trying to `DEL` a Pub/Sub channel | Channels are not stored keys | Unsubscribe/close listeners |
| Testing against local dev Redis instead of container | Collides with running apps or wipes wrong data | Testcontainers with dynamic ports |
| Cached Spring context points to stopped container | Later test classes fail to connect | Align context and container lifecycles |
| Assuming `@AfterEach` runs only if test passes | Misunderstands teardown semantics | Put cleanup in hooks/`finally`; add TTL/container safety nets |
| Failing to register keys before `SET` | Timeout after server write leaks the key | Register key prior to sending command |
| Running `SCAN` while writers keep adding keys | Namespace remains non-empty after scan | Stop writers, control lifecycle, and verify |
| Multi-key cleanup across Cluster slots | `CROSSSLOT` or routing failures | Delete individually or use cluster-aware APIs |
| Calling `CONFIG SET` on a shared server | Disrupts other apps | Dedicated Redis instance for config tests |
| Embedding API keys or emails in key prefixes | Leaks sensitive data in logs and Redis | Use opaque IDs or controlled hashes |

---

## 29. Workflow for Designing Safe Redis Integration Tests

Follow these steps in order:

1. **Define the test boundary.** Are you testing Redis Strings, Spring Cache, Redis Repositories, or Streams?
2. **Identify created resources.** A single key, or auxiliary indexes, metadata, and listeners?
3. **Choose the isolation level.** Per-method prefix or dedicated container.
4. **Ensure the endpoint is test Redis.** Use Testcontainers property injection and dynamic ports.
5. **Allocate a UUID namespace.** Never depend on wall-clock timestamps or fixed names.
6. **Inject the namespace into production code.** Never invent a prefix used only by test assertions while services write unprefixed keys.
7. **Register keys before writing.** Keep an explicit cleanup list.
8. **Run assertions.** Avoid assuming the entire Redis keyspace is empty.
9. **Stop writers and listeners.** Especially Stream consumers and Pub/Sub listeners.
10. **Clean up by ownership.** Delete exact keys, call repository deletes, or run scoped `SCAN` only when truly required.
11. **Avoid global wipes.** Unless certain the container is 100% disposable with zero concurrent users.
12. **Plan for hard aborts.** Add TTLs, container teardown, and controlled stale-run cleanup.
13. **Check parallel execution.** Avoid mutable singleton prefixes or shared `allEntries=true` regions.
14. **Verify stability in CI.** Ensure tests pass regardless of runner or execution order.

### Example Test Data Contract

```text
Owner       : RedisNamespaceIsolationIT
Run ID      : UUID generated by test runner
Redis       : Testcontainers dedicated Redis
Namespace   : it:<runId>:product:
Created keys: Registered before each SET operation
Cleanup     : @AfterEach deletes tracked key list
Fallback    : Container teardown
Parallel    : Unique UUID per method; no FLUSHDB
Expected    : Zero keys created/deleted outside test namespace
```

Documenting this contract keeps tests maintainable without future authors accidentally widening deletion scopes.

---

## 30. Practice Scenarios

### Scenario 1 — Two Tests Reading the Same Product

Tests A and B share Redis and both execute `GET products::SKU-1`. B expects a cache miss right after A warmed the cache.

**Explanation:** the tests did not isolate cache keys. Give each test its own key or cache namespace/context. With `@Cacheable`, changing only the object's ID without isolating the cache key generator may still be insufficient.

### Scenario 2 — Parallel CI Jobs Running `FLUSHDB`

Two CI jobs share Redis DB 1. Job A runs `FLUSHDB` before its suite, wiping Job B's keys.

**Explanation:** DB indexes do not grant exclusive ownership. Give each job its own Redis container or isolated namespace, and remove `FLUSHDB`.

### Scenario 3 — `repository.deleteById` Leaves Broken Indexes

An integration test with an `@Indexed` entity still sees stale index references after cleanup because TTL listeners did not run as expected.

**Explanation:** inspect repository/index mechanics, auxiliary keys, and expiration listeners. A dedicated container provides strong isolation here; manual raw cleanup often worsens inconsistency.

### Scenario 4 — Test Killed Before `@AfterEach`

A job creates `it:run-123:*` and the runner dies. Subsequent runs collide with leftover state.

**Explanation:** generate a fresh run ID on every execution, backed by TTLs, container teardown, or controlled stale-namespace cleanup.

### Scenario 5 — `SCAN` Returns an Empty Batch

Cleanup runs `SCAN`, sees an empty key list on the first iteration while the cursor is not yet `0`, and stops early.

**Explanation:** stopped too soon. `SCAN` must iterate until the cursor returns to `0`. One empty batch does not mean no matching keys remain.

### Scenario 6 — Redis Cluster Holds Prefixed Keys Across Nodes

A test issues a multi-key command to delete all prefixed keys and Redis throws `CROSSSLOT`.

**Explanation:** matching prefixes do not guarantee matching hash slots. Delete keys individually or use topology-aware cleanup. Cluster `SCAN` must also scan every relevant node rather than assuming one cursor spans the cluster.

### Scenario 7 — Deleted Stream Key Reappears

`@AfterEach` deletes a Stream key, and a background producer immediately calls `XADD`.

**Explanation:** the producer is still running and recreating the key. Stop all test producers and consumers before cleaning up.

### Scenario 8 — Pub/Sub Listener Receives Messages from Another Test

Two tests both subscribe to `events:*` and capture each other's events.

**Explanation:** the pattern is too broad and channels are unisolated. Use unique channels and stop subscriptions at lifecycle end.

### Scenario 9 — `RedisTemplate` Uses a Different Serializer

A test creates keys via `RedisTemplate<Object,Object>` with a binary key serializer, then tries deleting them via `StringRedisTemplate` with the same Java string.

**Explanation:** raw key bytes differ. Cleanup must use the same API or compatible serializer as the producer.

### Scenario 10 — Do Unit Tests Need Namespaces?

A service unit test mocks `RedisTemplate` with Mockito and never talks to a Redis server.

**Explanation:** unit tests create no real Redis keys and need no Redis cleanup. Just reset mocks/stubs per test lifecycle and ensure tests never hit a real Redis accidentally.

---

## 31. Key Takeaways

**Isolating test data in Spring Data Redis** means more than putting the word `test` in a key name. Clarify **who owns each resource**, how keys are generated, and what must be cleaned up afterward.

- **For known keys:** use UUID namespaces, register keys before creating them, and delete exact keys.
- **For caches or repositories generating auxiliary keys:** configure unique prefixes or use dedicated Redis containers; prefer framework-level cleanup APIs.
- **For Streams:** use unique Stream keys and stop consumers/producers before deleting.
- **For Pub/Sub:** use unique channels and unsubscribe/stop listeners—never `DEL` channels.
- **For tests altering Redis config or injecting server faults:** use completely dedicated instances.
- **For prefix-based cleanup:** use `SCAN` with strict ownership guards; avoid broad patterns or default `FLUSHDB`/`FLUSHALL`.
- **For parallel tests:** never share mutable prefixes or cache managers executing region-wide clears.
- **For aborted CI runs:** combine container teardown, backup TTLs, and controlled stale-run reaping.

The safest, easiest-to-operate choice for integration tests is **isolated Redis Testcontainers**, paired with **per-test namespaces/UUIDs** and **cleanup scoped strictly to created resources**. That keeps tests independent of execution order and protects unrelated application data.

### References

- [Spring Data Redis — Reference Documentation](https://docs.spring.io/spring-data/redis/reference/)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Testcontainers for Java](https://java.testcontainers.org/)
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/)
- [Redis — UNLINK](https://redis.io/docs/latest/commands/unlink/)
- [Redis — FLUSHDB](https://redis.io/docs/latest/commands/flushdb/)
- [Redis — FLUSHALL](https://redis.io/docs/latest/commands/flushall/)
