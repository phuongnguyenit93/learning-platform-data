# Starting real services with containers and dynamic connection configuration

## 1. Overview

In Spring Boot Testing, mocking a MongoDB repository, Redis client, or message producer keeps unit tests fast, yet **does not prove** the real application connects to the right host/port, serializes data accurately, executes MongoDB queries, handles Redis TTLs, or stays compatible with the server version. Relying on a manually installed Mongo/Redis at `localhost` is also hard to reproduce in CI and risks accidentally touching out-of-scope data.

**Testcontainers** starts real services inside test-scoped Docker containers. Those services are isolated from the external environment, follow a test-managed lifecycle, and typically expose **dynamic host ports**. Spring Boot **3.3.5** supports two key integration mechanisms:

- **`@ServiceConnection`** from `spring-boot-testcontainers`: creates `ConnectionDetails` for a container so Spring Boot auto-configuration picks up the service endpoint.
- **`@DynamicPropertySource`** from Spring TestContext: registers host, mapped port, URI, or credentials as dynamic properties, ideal when custom keys are needed or a backend lacks a service-connection factory.

Because this topic belongs to **Non-SQL Data**, the hands-on example uses **MongoDB 7.0 and Redis 7.2** instead of H2. We build a Spring Boot Java 17+ project, wire MongoDB via `MongoDBContainer + @ServiceConnection`, wire Redis via `GenericContainer + @DynamicPropertySource`, and test Spring Data MongoDB, `StringRedisTemplate`, and a cache-aside service using both real backends.

### Learning outcomes

1. Know the difference between mocked unit tests and integration tests with real containers.
2. Configure Testcontainers, Spring Boot Testcontainers, JUnit 5, and Spring Data starters.
3. Understand `@Testcontainers`, `@Container`, `MongoDBContainer`, `GenericContainer`, and static vs. instance lifecycles.
4. Retrieve `getHost()` and `getMappedPort(6379)` after startup rather than hardcoding host ports.
5. Configure MongoDB via `@ServiceConnection` to produce `MongoConnectionDetails`.
6. Register Redis `spring.data.redis.host` / `spring.data.redis.port` using `DynamicPropertyRegistry`.
7. Test real operations on a MongoDB repository, Redis data/TTLs, and a coordinating service.
8. Clean up fixtures properly, distinguishing SQL rollback from persisted NoSQL data.
9. Handle Spring context caching, Docker networking, CI, and startup errors.
10. Understand alternatives like Redis `@ServiceConnection(name="redis")`, container beans, and limits when testing clusters/production.

**Versions:** Spring Boot 3.3.5, Java 17+, Testcontainers versions managed by the Spring Boot BOM. Spring Boot 3.3/JUnit/Testcontainers documentation forms the API baseline; do not assume Boot 4 imports are identical.

## 2. Why test against real services?

```text
JUnit Jupiter + @SpringBootTest
  |
  +-- InventoryRepository
  |       |
  |       +-- MongoDB driver
  |               |
  |               +-- MongoDB 7.0 container (dynamic URI)
  |
  +-- InventoryLookupService
          |
          +-- StringRedisTemplate
                  |
                  +-- Lettuce Redis client
                          |
                          +-- Redis 7.2 container (dynamic host + port)
```

A mock can return `Optional.of(item)` even when the production MongoDB query uses the wrong field name or hits the wrong database. A fake Redis can ignore TTLs or return values immediately even when the application configures incompatible serializers. Real containers force test code through client driver → network → server → response.

| Test approach | Real backend? | What does it catch? | Limitations |
| --- | --- | --- | --- |
| Mockito/mocks | No | Branches, retries, mapping logic around dependencies | Does not verify driver, protocol, or DB constraints |
| Fake/in-memory replacement | Partial | Logic under simplified contracts | Semantics may diverge from real servers |
| Testcontainers | Yes | Connections, codecs, commands, persistence, TTLs, queries | Requires Docker and system resources |
| Shared staging service | Yes | Shared system with multiple collaborators | Data races, cleanup hazards, permissions, low repeatability |
| Production | Yes | Observing the live running system | Never a place for arbitrary test writes/deletes |

**Real containers do not equal a full production environment.** A single-node MongoDB does not simulate a sharded cluster; a standalone Redis cannot replace Redis Sentinel/Cluster, TLS/ACL, or failover infrastructure. Most CRUD/TTL tests remain highly valuable, while resilience/availability requires dedicated test environments.

## 3. Testcontainers lifecycle and networking

Example declaring a Redis container:

```java
@Testcontainers
class ExampleTest {
    @Container
    static GenericContainer<?> redis =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.2-alpine"))
                    .withExposedPorts(6379);
}
```

This snippet requires imports for `Testcontainers`, `Container`, `GenericContainer`, and `DockerImageName`. With the `@Testcontainers` JUnit extension:

- A `static @Container` field normally starts once before the class's test methods and stops after the class.
- An instance `@Container` field normally follows each individual test method's lifecycle.
- `withExposedPorts(6379)` instructs Docker to publish container port **6379** onto a **dynamically assigned host port**.
- `redis.getHost()` returns the host the test JVM should use to reach the container.
- `redis.getMappedPort(6379)` returns the host port mapped to container port 6379.
- `redis.isRunning()` signals the Docker container is running; **it is not sufficient** to prove the app client can connect.

**Do not call `getMappedPort` too early:** before the container starts, Docker has not allocated a mapped port and the accessor throws an error. Therefore, Spring configuration registers a `Supplier` resolved lazily when Spring reads properties, such as `() -> redis.getMappedPort(6379)`.

```text
Redis internal: redis-container:6379
Developer host: localhost:49153         (example only)
CI host:        192.168.65.2:32778      (example only)

App client on host must use getHost + getMappedPort,
never assume localhost:6379.
```

Do not confuse host-to-container networking with container-to-container networking. When container A talks to container B on the same Docker network, they use network aliases and internal ports; mapped ports are for the test JVM/host reaching the container. In remote Docker or Docker-in-Docker CI, `getHost()` may not be `localhost`.

## 4. ServiceConnection and ConnectionDetails

In Boot 3.3, you can declare:

```java
@Container
@ServiceConnection
static final MongoDBContainer MONGO =
        new MongoDBContainer(
                DockerImageName.parse("mongo:7.0"));
```

Spring Boot detects the `MongoDBContainer` type and creates `MongoConnectionDetails` to auto-configure the MongoDB client. `ConnectionDetails` takes precedence over regular connection properties for that service.

```text
MongoDBContainer
      |
      | @ServiceConnection
      v
MongoConnectionDetails
      |
      v
MongoAutoConfiguration / MongoClient
      |
      v
MongoRepository / MongoTemplate
```

Important requirements:

- Add `testImplementation 'org.springframework.boot:spring-boot-testcontainers'`.
- Include `org.testcontainers:mongodb` to compile `MongoDBContainer`.
- Include the Spring Data Mongo starter so Boot creates the Mongo client/repository.
- `@ServiceConnection` **does not replace** Docker lifecycle management; the demo field uses `@Container`, or you can use Spring Boot-managed container beans.
- Do not also declare `spring.data.mongodb.uri` alongside this container "just in case"; Boot already selects connection details and precedence can cause your property to be ignored.

The catalog of service-connection factories changes across Boot versions. Spring Boot 3.3 recognizes containers such as MongoDB, Redis by image name, Neo4j, Cassandra, Elasticsearch, RabbitMQ, Kafka, and others per its compatibility table. If a custom Docker image is unrecognized, use `name` on `@ServiceConnection` or `@DynamicPropertySource` as actually supported.

## 5. @DynamicPropertySource in Spring Test

To supply Redis host and port, write a static method:

```java
@DynamicPropertySource
static void redisProps(DynamicPropertyRegistry registry) {
    registry.add("spring.data.redis.host", REDIS::getHost);
    registry.add("spring.data.redis.port",
            () -> REDIS.getMappedPort(6379));
}
```

Spring TestContext only needs `DynamicPropertyRegistry` and `Supplier<?>` callbacks. It **does not start Redis**; lifecycle must be managed separately by `@Container` or a container bean.

Rules:

1. A `@DynamicPropertySource` method must be **static** and accept a single `DynamicPropertyRegistry` parameter.
2. `registry.add` accepts a supplier, resolving the dynamic value lazily when the property is read.
3. Dynamic properties have higher precedence than test properties, system properties, and many standard property sources.
4. Use Boot 3.3 keys: `spring.data.redis.host` and `spring.data.redis.port`.
5. `getMappedPort(6379)` is valid only after the container has started.
6. Registering host/port alone does not prove the client used them correctly; tests must send real Redis commands.

**Distinction:** `@ServiceConnection` feeds details into auto-configuration, while `@DynamicPropertySource` injects key/value pairs into the Spring `Environment`. In the example, the two mechanisms serve **two separate backends**, so there is no conflict between Mongo and Redis.

### Alternative MongoDB URI approach

If not using `@ServiceConnection` for Mongo, you can register:

```java
@DynamicPropertySource
static void mongoProps(DynamicPropertyRegistry registry) {
    registry.add("spring.data.mongodb.uri",
            MONGO::getReplicaSetUrl);
}
```

`MongoDBContainer.getReplicaSetUrl()` builds a URI matching the replica-set container. This is an **alternative**, not used simultaneously with Mongo `@ServiceConnection` in the main project. Never guess a MongoDB connection string from `localhost` and an assumed port when the container exposes a dedicated accessor.

## 6. Sample project: Java 17+ Spring Boot 3.3.5

The project has two external services and a simple application:

```text
nosql-containers-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/nosql/
│   ├── NosqlContainersApplication.java
│   ├── InventoryItem.java
│   ├── InventoryRepository.java
│   └── InventoryLookupService.java
└── src/test/java/com/example/nosql/
    └── RealBackendsIntegrationTest.java
```

Never use corporate or production Mongo/Redis credentials or networked databases. Tests spin up their own MongoDB and Redis containers, independent of any server someone happened to start on default ports.

### 6.1. settings.gradle

```groovy
rootProject.name = 'nosql-containers-demo'
```

### 6.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-mongodb'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:mongodb'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

**Dependency notes:**

- `spring-boot-starter-data-mongodb`: Mongo driver, Spring Data MongoDB, and repositories.
- `spring-boot-starter-data-redis`: Spring Data Redis, Lettuce client, and `StringRedisTemplate`.
- `spring-boot-starter-test`: JUnit Jupiter, Spring TestContext, and test assertions.
- `spring-boot-testcontainers`: `@ServiceConnection` + connection details factories.
- `testcontainers:junit-jupiter`: Testcontainers JUnit integration.
- `testcontainers:mongodb`: specialized `MongoDBContainer`, which also brings in core `GenericContainer`.
- `junit-platform-launcher`: supports JUnit Platform runtime in Gradle.

No Redis-specific Testcontainers module is required for `GenericContainer<?>`. Spring Boot manages dependency versions via the BOM; do not force incompatible Testcontainers/Jackson/Mongo client versions just to run a demo.

**External requirements outside Java:** active Docker daemon, test runner access to Docker, sufficient host RAM/CPU, and ability to pull images. Docker privileges must be governed properly in CI; never mount secrets or the host Docker socket into untrusted images casually.

## 7. Spring Boot application root

`src/main/java/com/example/nosql/NosqlContainersApplication.java`:

```java
package com.example.nosql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NosqlContainersApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                NosqlContainersApplication.class, args);
    }
}
```

The root class sits in `com.example.nosql`, parent package of the repository, service, and test. `@SpringBootTest` finds the primary `@SpringBootConfiguration` via package hierarchy and loads the real application context.

Running `bootRun` outside tests without external backend config falls back to default connection properties; this project focuses on **testing** rather than production deployment. Inside the test class, the two containers provide the endpoints.

## 8. MongoDB document mapping

`src/main/java/com/example/nosql/InventoryItem.java`:

```java
package com.example.nosql;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(collection = "inventory_items")
public class InventoryItem {

    @Id
    private String id;

    private String sku;
    private String title;
    private long available;

    public InventoryItem() {
        // Constructor for Spring Data MongoDB.
    }

    public InventoryItem(
            String sku, String title, long available) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku is required");
        }
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        if (available < 0) {
            throw new IllegalArgumentException(
                    "available cannot be negative");
        }
        this.sku = sku;
        this.title = title;
        this.available = available;
    }

    public String getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public String getTitle() {
        return title;
    }

    public long getAvailable() {
        return available;
    }

    public void setTitle(String title) {
        if (title == null || title.isBlank()) {
            throw new IllegalArgumentException("title is required");
        }
        this.title = title;
    }
}
```

`@Document` defines the MongoDB collection, and `@Id` marks the identifier that the driver/Spring Data can assign on save. This is **not** a JPA `@Entity`; MongoDB has no Hibernate-style persistence-context dirty checking. To update `title`, call `repository.save(...)` or the `MongoTemplate` update API.

MongoDB's flexible schema does not automatically ensure data quality. In production, define explicit validation and index policies. A `findBySku` method does not automatically create a unique index on SKU.

## 9. MongoRepository with derived queries

`src/main/java/com/example/nosql/InventoryRepository.java`:

```java
package com.example.nosql;

import java.util.Optional;
import org.springframework.data.mongodb.repository.MongoRepository;

public interface InventoryRepository
        extends MongoRepository<InventoryItem, String> {

    Optional<InventoryItem> findBySku(String sku);

    long countByAvailableGreaterThan(long quantity);
}
```

`findBySku` runs a Mongo query on the `sku` field. `countByAvailableGreaterThan` checks records with stock above a threshold; both go through the Mongo driver to the real container.

Never mock the repository and conclude the MongoDB query is right: a mocked response only proves **what Mockito was told to return**, without executing any Mongo query. The container test inserts fixtures, invokes repository methods, and asserts real results.

## 10. Redis cache-aside service

`src/main/java/com/example/nosql/InventoryLookupService.java`:

```java
package com.example.nosql;

import java.time.Duration;
import java.util.NoSuchElementException;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class InventoryLookupService {

    private final InventoryRepository repository;
    private final StringRedisTemplate redis;

    public InventoryLookupService(
            InventoryRepository repository,
            StringRedisTemplate redis) {
        this.repository = repository;
        this.redis = redis;
    }

    public String titleBySku(String sku) {
        String key = "inventory:title:" + sku;

        String fromCache = redis.opsForValue().get(key);
        if (fromCache != null) {
            return fromCache;
        }

        String title = repository.findBySku(sku)
                .map(InventoryItem::getTitle)
                .orElseThrow(() ->
                        new NoSuchElementException(
                                "Unknown SKU: " + sku));

        redis.opsForValue().set(
                key, title, Duration.ofMinutes(2));
        return title;
    }
}
```

The code illustrates a **cache-aside** read path: Redis lookup → on miss, query Mongo → write cache with a two-minute TTL. In tests, the service uses both real connections simultaneously.

**Production warning:** cache-aside does not automatically solve stale cache after Mongo updates, cache stampedes, Redis outages, distributed transactions, or authorization. Implement invalidation, retries/fallbacks, and consistency policies per business requirements. Never store sensitive data in Redis key strings just for debugging convenience.

## 11. Complete integration test suite

`src/test/java/com/example/nosql/RealBackendsIntegrationTest.java`:

```java
package com.example.nosql;

import java.time.Duration;
import java.util.NoSuchElementException;
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.testcontainers.service.connection.ServiceConnection;
import org.springframework.core.env.Environment;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.containers.MongoDBContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
@SpringBootTest
class RealBackendsIntegrationTest {

    private static final int REDIS_PORT = 6379;

    private static final String VALUE_KEY = "it:redis:value";
    private static final String COUNTER_KEY = "it:redis:count";
    private static final String TTL_KEY = "it:redis:ttl";
    private static final String CACHE_KEY =
            "inventory:title:SKU-CACHE";
    private static final String UNKNOWN_CACHE_KEY =
            "inventory:title:SKU-UNKNOWN";

    @Container
    @ServiceConnection
    static final MongoDBContainer MONGO =
            new MongoDBContainer(
                    DockerImageName.parse("mongo:7.0"));

    @Container
    static final GenericContainer<?> REDIS =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.2-alpine"))
                    .withExposedPorts(REDIS_PORT);

    @DynamicPropertySource
    static void redisProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
                "spring.data.redis.host", REDIS::getHost);
        registry.add(
                "spring.data.redis.port",
                () -> REDIS.getMappedPort(REDIS_PORT));
    }

    @Autowired
    InventoryRepository repository;

    @Autowired
    InventoryLookupService service;

    @Autowired
    StringRedisTemplate redis;

    @Autowired
    Environment environment;

    @BeforeEach
    void prepareData() {
        repository.deleteAll();
        redis.delete(VALUE_KEY);
        redis.delete(COUNTER_KEY);
        redis.delete(TTL_KEY);
        redis.delete(CACHE_KEY);
        redis.delete(UNKNOWN_CACHE_KEY);
    }

    @AfterEach
    void cleanData() {
        repository.deleteAll();
        redis.delete(VALUE_KEY);
        redis.delete(COUNTER_KEY);
        redis.delete(TTL_KEY);
        redis.delete(CACHE_KEY);
        redis.delete(UNKNOWN_CACHE_KEY);
    }

    @Test
    void containersAreRunning() {
        assertTrue(MONGO.isRunning());
        assertTrue(REDIS.isRunning());
        assertTrue(REDIS.getMappedPort(REDIS_PORT) > 0);
    }

    @Test
    void environmentReceivesDynamicRedisProperties() {
        assertEquals(
                REDIS.getHost(),
                environment.getProperty("spring.data.redis.host"));
        assertEquals(
                Integer.toString(REDIS.getMappedPort(REDIS_PORT)),
                environment.getProperty("spring.data.redis.port"));
    }

    @Test
    void mongoSavesAndFindsDocumentBySku() {
        InventoryItem saved = repository.save(
                new InventoryItem("SKU-101", "Mongo data", 9));

        assertNotNull(saved.getId());

        InventoryItem loaded = repository
                .findBySku("SKU-101").orElseThrow();

        assertEquals(saved.getId(), loaded.getId());
        assertEquals("Mongo data", loaded.getTitle());
        assertEquals(9, loaded.getAvailable());
    }

    @Test
    void mongoCanUpdateDocument() {
        InventoryItem saved = repository.save(
                new InventoryItem("SKU-102", "Before", 3));

        saved.setTitle("After");
        repository.save(saved);

        InventoryItem updated = repository
                .findById(saved.getId()).orElseThrow();

        assertEquals("After", updated.getTitle());
    }

    @Test
    void mongoCanDeleteDocument() {
        InventoryItem saved = repository.save(
                new InventoryItem("SKU-103", "Delete", 1));

        repository.deleteById(saved.getId());

        assertTrue(repository
                .findById(saved.getId()).isEmpty());
    }

    @Test
    void mongoDerivedQueryCountsMatchingDocuments() {
        repository.save(new InventoryItem(
                "SKU-104", "Small", 2));
        repository.save(new InventoryItem(
                "SKU-105", "Large", 8));
        repository.save(new InventoryItem(
                "SKU-106", "Empty", 0));

        assertEquals(
                1L,
                repository.countByAvailableGreaterThan(4));
    }

    @Test
    void mongoFindReturnsEmptyForUnknownSku() {
        assertTrue(repository
                .findBySku("SKU-DOES-NOT-EXIST").isEmpty());
    }

    @Test
    void redisCanStoreAndReadString() {
        redis.opsForValue().set(VALUE_KEY, "live-redis");

        assertEquals(
                "live-redis",
                redis.opsForValue().get(VALUE_KEY));
    }

    @Test
    void redisIncrementIsAtomicAtServer() {
        assertEquals(
                1L,
                redis.opsForValue().increment(COUNTER_KEY));

        assertEquals(
                2L,
                redis.opsForValue().increment(COUNTER_KEY));
    }

    @Test
    void redisCanAssignKeyTtl() {
        redis.opsForValue().set(
                TTL_KEY, "short-lived", Duration.ofMinutes(5));

        Long seconds = redis.getExpire(
                TTL_KEY, TimeUnit.SECONDS);

        assertNotNull(seconds);
        assertTrue(seconds > 0);
        assertTrue(seconds <= 300);
    }

    @Test
    void redisCanDeleteKey() {
        redis.opsForValue().set(VALUE_KEY, "remove-me");

        assertEquals(Boolean.TRUE, redis.delete(VALUE_KEY));
        assertFalse(Boolean.TRUE.equals(
                redis.hasKey(VALUE_KEY)));
    }

    @Test
    void serviceReadsMongoAndThenCachesInRedis() {
        InventoryItem saved = repository.save(
                new InventoryItem(
                        "SKU-CACHE", "Cached title", 5));

        assertEquals(
                "Cached title",
                service.titleBySku("SKU-CACHE"));

        assertEquals(
                "Cached title",
                redis.opsForValue().get(CACHE_KEY));

        repository.deleteById(saved.getId());

        assertEquals(
                "Cached title",
                service.titleBySku("SKU-CACHE"));
    }

    @Test
    void serviceDoesNotCacheUnknownSku() {
        assertThrows(
                NoSuchElementException.class,
                () -> service.titleBySku("SKU-UNKNOWN"));

        assertFalse(Boolean.TRUE.equals(
                redis.hasKey(UNKNOWN_CACHE_KEY)));
    }
}
```

There are **13 `@Test` methods** in the source; `@BeforeEach`/`@AfterEach` are not counted as tests. This is an example suite expected to run with Docker available and matching dependencies, **not** a Gradle/CI execution report from this session.

### 11.1. Two independent configuration flows

**Mongo:** `@Container MONGO` → `@ServiceConnection` → `MongoConnectionDetails` → Spring Boot Mongo client → repository. No manual URI needed.

**Redis:** `@Container REDIS` → Docker mapped port → `@DynamicPropertySource` supplies host/port → `RedisConnectionFactory`/Lettuce → `StringRedisTemplate`. `@ServiceConnection` is intentionally omitted for Redis in this class to demonstrate manual dynamic configuration.

### 11.2. Why is reading Environment alone not enough?

`environmentReceivesDynamicRedisProperties` asserts the property keys are set, yet an application could construct a custom `RedisConnectionFactory` and ignore those properties. `redisCanStoreAndReadString` is the actual proof that GET/SET commands travel through the client bean to the server.

Similarly, `containersAreRunning` only proves Docker reports the containers as running. `mongoSavesAndFindsDocumentBySku` proves the Spring Data driver, mapping, and server really work.

### 11.3. Real MongoDB operations

`mongoSavesAndFindsDocumentBySku` checks generated ID, title, available count, and SKU query. `mongoCanUpdateDocument` executes `repository.save` after modifying `title`. `mongoCanDeleteDocument` verifies deletion and absent result. `mongoDerivedQueryCountsMatchingDocuments` inserts three documents with different `available` values and asserts one matches `available > 4`.

`MongoRepository.findBySku` returns `Optional.empty()` when no document matches; network errors or authentication failures throw exceptions and **must not** be swallowed into "not found" without an explicit policy.

### 11.4. Redis commands and TTL

`StringRedisTemplate` uses string serialization, so Redis SET/GET verifies both protocol and compatible serializer. Redis `increment` runs an atomic server-side increment on a key; the test checks returned values 1 and 2.

`redisCanAssignKeyTtl` writes a key with a five-minute TTL and checks `getExpire` is positive within `(0,300]` seconds. We do not wait five minutes in the test. A TTL return of `-1` means the key exists without expiry; `-2` means the key does not exist. When testing actual expiry, use bounded polling with a short TTL and allow timing variability rather than arbitrary `Thread.sleep`.

### 11.5. Cache-aside case proves coordination

On the first read, the service fetches `title` from Mongo and stores it in Redis. The test confirms the cache key holds the value. Deleting the Mongo document and reading again still returns the cached title. That proves a cache hit **while** serving as a reminder that caches go stale when the source of truth changes.

`serviceDoesNotCacheUnknownSku` verifies that missing Mongo records cause the service to throw `NoSuchElementException` without writing a bad cache entry. That is this example's contract; a product choosing negative caching needs explicit TTL and invalidation rules.

## 12. Cleanup and isolation for NoSQL

`@SpringBootTest` **does not auto-rollback** MongoDB/Redis operations the way `@DataJpaTest` rolls back JPA test transactions. Every test in the example:

- Deletes all documents in the Mongo collection of the **dedicated test container**.
- Deletes only its own Redis keys before and after each method.
- Arranges its own fixtures per method without relying on other tests.
- Never needs a shared company or production Mongo/Redis server.
- Never relies on test method ordering to create implicit dependencies.

**Caution:** `repository.deleteAll()` is safe only because the repository talks to a fresh test container. Never copy this cleanup onto shared/production databases. With larger test datasets or multiple concurrent suites, create separate databases/collections/key prefixes and clean up by namespace; avoid Redis `FLUSHALL` or `FLUSHDB` outside completely test-owned instances.

If JUnit parallel execution is enabled on tests sharing a collection and Redis keys, Test A's `@BeforeEach` can wipe Test B's data. When running in parallel, use per-test unique fixtures/namespaces or run shared-state tests sequentially.

### No distributed transaction by default

MongoDB supports transactions on replica sets with the right manager; Redis has its own transactions/atomic commands. They do not join a single global transaction merely because an application uses `@Transactional`. Cache-aside has failure windows requiring idempotency, retries, and stale-state policies in production. Never infer from a passing integration test that updating Mongo and Redis is atomic.

## 13. Replacing Redis DynamicPropertySource with @ServiceConnection

Spring Boot 3.3 recognizes the Redis image name `redis`. With a static `GenericContainer<?>`, you can replace the Redis setup in the test with:

```java
@Container
@ServiceConnection(name = "redis")
static final GenericContainer<?> REDIS =
        new GenericContainer<>(
                DockerImageName.parse("redis:7.2-alpine"))
                .withExposedPorts(6379);
```

When using this approach, **remove the `redisProperties(DynamicPropertyRegistry)` method**. Spring Boot creates `RedisConnectionDetails` from the Redis container, passes it to Redis auto-configuration, and saves you from wiring host/port properties manually.

This is an **alternative**, not a third container inside the runnable project. When switching approaches, remove or adjust `environmentReceivesDynamicRedisProperties` because those Environment keys may no longer be registered; instead test actual connectivity and service connection behavior.

### With @Bean GenericContainer, name is needed

Inside a `@TestConfiguration`:

```java
@TestConfiguration(proxyBeanMethods = false)
class RedisTestConfiguration {

    @Bean
    @ServiceConnection(name = "redis")
    GenericContainer<?> redisContainer() {
        return new GenericContainer<>(
                DockerImageName.parse("redis:7.2-alpine"))
                .withExposedPorts(6379);
    }
}
```

This configuration snippet needs imports for `TestConfiguration`/`Bean`/`ServiceConnection`/`GenericContainer`/`DockerImageName`. Boot does not invoke the `@Bean` method early to inspect `GenericContainer<?>`'s image name when registering connection details; **`name="redis"`** lets the factory select Redis. With static fields, Boot can read the image name from the container instance; still, specifying `name` makes intent explicit.

A container managed as a Spring bean normally starts and stops with the `ApplicationContext` lifecycle. That helps when multiple test classes share one cached context. Never create both a JUnit `@Container` field and a `@Bean` for the same service without knowing which container the app actually uses.

## 14. When to choose which approach?

| Criterion | `@ServiceConnection` | `@DynamicPropertySource` |
| --- | --- | --- |
| Service supported by Boot factory | Very concise | Still works |
| Custom property keys needed | Not its primary purpose | Ideal fit |
| Endpoint mechanism | `ConnectionDetails` | `DynamicPropertyRegistry` |
| Boot property renames | Less boilerplate | Must update exact property keys |
| Starts container on its own? | No without JUnit/bean lifecycle | No |
| Precedence | `ConnectionDetails` beats ordinary properties | Dynamic property source has high precedence |
| Unrecognized `GenericContainer` image | Needs `name`/custom factory | Only needs endpoint accessors |
| Custom backend API | Likely unsupported | Declare `partner.api.base-url` directly |
| Verification required | Assert real client operations | Assert real client operations |

A solid strategy is `@ServiceConnection` for standard Boot-recognized backends and `@DynamicPropertySource` for backends lacking factories or needing custom configuration. Never register two competing configuration sources for the same backend "just to be sure" tests run.

## 15. Static containers, instance containers, and Spring context cache

### JUnit-managed static @Container

A static `@Container` lives for the test class lifecycle. If Spring TestContext caches the same `ApplicationContext` for reuse across multiple classes after the previous class's static container has stopped, client beans in the cached context still point to an endpoint that is **no longer running**.

Ways to handle this:

- Group integration tests sharing the same container/config into one test class or a unified fixture lifecycle.
- Use Spring Boot-managed container beans inside `@TestConfiguration` when lifecycle should track the cached Spring context.
- Use `@DirtiesContext` intentionally when dynamic properties change between classes; never scatter it on every test because it is very slow.
- Do not declare a fresh static container in each class expecting an older cached context to reconnect automatically to new mapped ports.
- If enabling reusable containers, handle leftover data across JVM runs rather than assuming every run starts with an empty DB.

### Instance @Container

Instance container fields restart per test method, offering isolation at a steep runtime cost for Mongo. If the app context is built once while container ports change every method, `MongoClient`/`RedisConnectionFactory` keep stale endpoints. Therefore, **never** simply change `static` to an instance field in a Spring Boot integration test expecting connections to auto-refresh; context and container lifecycles must match.

### Container reuse

Testcontainers supports reusable containers depending on configuration and environment. Reuse speeds up local runs, yet can leave data/indexes across runs and break isolation assumptions. In multi-user/PR CI environments, establish clear policies on reuse and cleanup rather than turning reuse on globally just to skip setup code.

## 16. Docker networking and dynamic ports

`getHost()` and `getMappedPort(containerPort)` are the **test JVM → container path**. When two containers on the same Docker network communicate with each other, use Docker network aliases and internal ports.

```text
JVM on host:
  getHost():getMappedPort(6379)
Docker container on same network:
  redis-alias:6379
```

Do not use hostname `redis-alias` from the host JVM if it only resolves inside Docker DNS. Do not use mapped ports for container-to-container calls when a shared network provides internal addressing. In remote Docker/CI-in-Docker, the host may not be `127.0.0.1`.

When an application connects multiple containers together, consider `Network.newNetwork()`, `withNetwork(network)`, and `withNetworkAliases(...)` for real container-to-container traffic. The demo does not need that because the test JVM talks to each service via host mapped ports.

## 17. Started does not mean ready to accept requests

A Docker container can report running while MongoDB has not finished initializing its replica set or Redis is not yet ready for commands. Specialized Testcontainers classes include suitable wait strategies; `GenericContainer` has a default wait strategy or can be configured explicitly.

Snippet:

```java
GenericContainer<?> redis =
        new GenericContainer<>(
                DockerImageName.parse("redis:7.2-alpine"))
                .withExposedPorts(6379)
                .waitingFor(Wait.forListeningPort());
```

Requires `import org.testcontainers.containers.wait.strategy.Wait`. This snippet does not replace the main project's `REDIS` field unless integrated completely into the test class.

For HTTP services, wait strategies can poll an HTTP health endpoint. For databases, readiness must reflect the driver's ability to connect/read/write, not merely that a process forked. Avoid fixed `Thread.sleep(10000)` because CI load varies; prefer readiness checks with bounded timeouts.

## 18. What does CI need to run these tests?

Operational checklist:

1. Java 17+ and a matching Gradle/Gradle Wrapper version.
2. Active Docker daemon with runner permission to call the Docker API.
3. Ability to pull `mongo:7.0` and `redis:7.2-alpine` from a trusted registry.
4. Enough RAM/CPU to start both services in the same job.
5. Working Docker port forwarding for host/remote runners.
6. Container cleanup properly configured; verify Testcontainers resource reaper/Ryuk and security policies.
7. Never inject production Mongo URIs or Redis passwords into tests.
8. Mechanisms to collect Gradle/JUnit test reports and container logs without secrets.
9. Never use fixed host ports so jobs do not race each other.
10. When running in parallel, isolate data/key namespaces and suite lifecycles.

Example logical CI pipeline steps:

```text
Checkout
  -> Setup JDK / Gradle
  -> Provide Docker access
  -> Testcontainers pulls Mongo + Redis images
  -> Starts two containers, maps host ports
  -> Spring Boot creates clients
  -> JUnit tests run
  -> Gradle writes XML/HTML reports
  -> Containers stop/cleanup
```

**Never assume Docker socket mounting is always allowed.** In containerized CI, sharing the Docker socket exposes host-level privilege risks. Use runner/container services approved by your ops team; when Docker is unavailable, report integration tests as not run rather than claiming PASS from unit mocks.

## 19. Running and evaluating results

In a project with Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.nosql.RealBackendsIntegrationTest'
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

If Gradle Wrapper is absent yet compatible Gradle is installed:

```bash
gradle test
```

Docker must be running beforehand. The first run pays image pull time; later runs reuse cached image layers. Tests print no fixed business stdout. Check real results in:

```text
build/reports/tests/test/index.html
build/test-results/test/
```

**There are 13 `@Test` methods in the source**, yet no execution report was generated while authoring this lesson, so do not claim 13 PASSED. If a method fails, separate Docker startup, `ApplicationContext`, mapped port, Mongo mapping, Redis serialization, and assertion failures; never alter expected data just to hide an error.

## 20. Common errors

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| `Could not find a valid Docker environment` | Docker daemon not running/insufficient permissions | Check `docker info` and runner Docker config |
| Image pull failed | Registry/network/tag/quota issue | Verify image version and registry access |
| Mongo server selection timeout | Container not ready, wrong URI or network | Inspect Mongo logs, service connection, wait strategy |
| Redis `Connection refused` | Hardcoded localhost:6379 or wrong dynamic port | Use `REDIS.getHost()`/`getMappedPort(6379)` |
| `@ServiceConnection` has no effect | Missing `spring-boot-testcontainers` or wrong container type/name | Check dependency, annotation, factory table |
| Missing `MongoRepository` bean | Wrong scan package or missing starter | Check `@SpringBootApplication` root and Mongo starter |
| Missing `StringRedisTemplate` bean | Redis starter/auto-config excluded | Check dependency and `RedisConnectionFactory` |
| Dynamic property is null | Non-static method, wrong supplier/field | Fix registry method signature and lifecycle |
| Passes locally, fails in CI | Different remote Docker host/port | Never hardcode hosts or ports |
| Mongo query unexpectedly empty | Wrong collection/database, unseeded fixture | Assert saved id and repository query |
| Test methods fail depending on order | Data wiped by another test | Add cleanup, isolated keys, avoid parallel runs |
| Context cache holds stale endpoint | Static container stopped after previous class | Use container bean lifecycle or `@DirtiesContext` |
| Redis TTL is -1 | `SET` called without expiration | Write key with `Duration` and assert TTL |
| Redis TTL is -2 | Key already gone | Check test setup and expiration |
| Tests run slowly | Mongo image pull/start, full context per method | Static container, proper context caching |
| Container "running" yet service unavailable | Service readiness not reached | Wait strategy and driver timeouts |
| Redis keys leak across suites | Reused container with missing cleanup | Per-test namespaces and cleanup |
| Wrong Mongo type mapping | BSON/schema differs from Java fields | Test real document serialization |
| Production infra differs from container | Cluster/TLS/ACL/sharding/replication | Add dedicated staging test environment |

### Debugging workflow

1. Check Docker daemon and image pulls.
2. Check container `isRunning()`, logs, and readiness.
3. Read host/mapped port or specialized URI after startup.
4. Verify `@ServiceConnection`/`@DynamicPropertySource` produced valid connection config.
5. Run the smallest real operation through actual Spring beans: Mongo save/find, Redis SET/GET.
6. Check data fixtures, database/collection, cache keys, and cleanup.
7. If failing only in CI, inspect remote Docker, resource limits, and Spring context reuse.
8. If failing only against production vendor/cluster, never treat single-node results as proof of equivalence.

## 21. Testcontainers and other non-SQL services

| Service | Suggested container | Items to verify |
| --- | --- | --- |
| MongoDB | `MongoDBContainer` | BSON mapping, indexes, queries, transactions per replica-set config |
| Redis | `GenericContainer<?>` with `redis` image | Strings, hashes, TTLs, cache semantics |
| Cassandra | `CassandraContainer` | CQL/keyspace, consistency, schema |
| Elasticsearch | `ElasticsearchContainer` | Mappings, analyzers, query DSL |
| Neo4j | `Neo4jContainer<?>` | Cypher, relationships, Bolt driver |
| Couchbase | `CouchbaseContainer` | Buckets, KV, indexes/queries |
| Kafka | `KafkaContainer` / compatible module | Producer/consumer, offsets, serialization |
| RabbitMQ | `RabbitMQContainer` | AMQP routing, acknowledgements |
| External custom HTTP | `GenericContainer<?>` | HTTP client, timeouts, JSON/error contracts |

These services do not share identical APIs or startup configurations. Check the Testcontainers module, supported Spring Boot `ConnectionDetails` factories, and Docker image versions for **your exact version**. Never assume Boot will recognize a custom image like an official canonical image without `@ServiceConnection(name=...)`.

### Schemas/indexes and seed data

A fresh MongoDB container does not automatically create **domain-specific indexes**, an Elasticsearch container does not create application mappings/indexes, and a Cassandra container does not create your project's keyspace. When testing migrations/bootstrapping, run the application's actual schema/index creation mechanism or build an intentional matching test fixture.

With message brokers, publishing a message does not mean a subscriber has consumed it: use Awaitility/bounded polling/test utilities rather than fixed `Thread.sleep` assuming synchronous delivery.

## 22. Comparison with Docker Compose

Docker Compose can launch supporting services for local development. Testcontainers ties container lifecycle directly into Java tests and dynamic endpoint wiring inside JUnit/Spring.

| Aspect | Testcontainers | Docker Compose |
| --- | --- | --- |
| Controlled from Java tests | Yes | Not directly like a JUnit extension |
| Dynamic test ports | `getMappedPort`/service connection | Driven by Compose config/ports |
| Per-suite isolation | Easy to design | Depends on shared stack/volumes |
| Manual developer stack startup | Possible | Often convenient |
| Automatic test cleanup | Follows test lifecycle/rules | Requires Compose teardown |
| Parallel CI branches | Usually straightforward without fixed ports | Requires isolated project names/networks |

Do not conflate the two tools: even if developers run a Compose stack, automated tests still need proof that the backend they connect to belongs strictly to the test scope. Testcontainers fits CI repeatability better, while Compose often suits long-lived development environments.

## 23. Safety and security

- Never run write/delete tests against production Mongo/Redis.
- Never use wildcard Mongo `deleteAll` or Redis `FLUSHALL` on shared services.
- Never store raw tokens, passwords, or PII in Redis cache/key names or test logs.
- Use Docker images from approved sources and pin versions/digests for reproducibility.
- Never expose mapped ports publicly to the Internet.
- Never grant untrusted CI jobs arbitrary access to the Docker socket.
- When TLS/ACL are needed, use test-only secrets and certificates.
- When using remote Docker, verify firewalls and network isolation.
- When disabling Testcontainers resource cleanup due to CI constraints, provide an alternative cleanup plan.
- When container reuse is enabled, never assume databases/keys are clean between runs.
- In production-like tests, use test-owned collections/DBs/namespaces and clean up strictly within scope.

`@ServiceConnection` and `@DynamicPropertySource` wire connections; **they do not guarantee** authorization, secret handling, or data safety.

## 24. Pre-merge checklist

1. Which real backend and image/version is the test meant to verify?
2. Is Docker running on developer machines and CI?
3. Is container lifecycle managed consistently via the JUnit extension or Spring container beans?
4. Does static vs. instance lifecycle align with Spring context caching?
5. Are `localhost` and host mapped ports free of hardcoding?
6. Is `getMappedPort` resolved only after the container starts?
7. Is `spring-boot-testcontainers` in test scope when using `@ServiceConnection`?
8. Is the container type or Docker image name supported by a Boot 3.3 factory?
9. Does `@DynamicPropertySource` use a static method and suppliers correctly?
10. Do host/port/URI property keys match the Boot version?
11. Did you avoid setting competing connection details and properties for the same backend?
12. Do tests send operations **through real Spring beans**, rather than merely asserting the container is running?
13. Do Mongo mappings/queries/CRUD cover both positive and not-found cases?
14. Do Redis SET/GET, INCR, TTL, and DELETE have explicit assertions?
15. Does an app service spanning multiple backends have a coordinated integration test?
16. Is fixture cleanup explicit rather than relying on SQL rollback?
17. Do parallel tests use separate namespaces or run sequentially?
18. Are Redis `FLUSHALL` and broad Mongo deletes avoided outside test-owned databases?
19. Are differences between a single container and production cluster/replication/TLS documented?
20. Does CI have Docker permissions, image pull access, and sufficient resources?
21. Were real test reports reviewed rather than claiming PASS from source alone?
22. When upgrading Boot/Testcontainers, were connection factories/types/key imports checked?

## 25. Practice exercises

1. Run `RealBackendsIntegrationTest` with Docker and verify the mapped ports differ from default 6379/27017.
2. Remove `@ServiceConnection` from Mongo while keeping Redis dynamic properties. Inspect where the Mongo client looks for its URL and explain the failure.
3. Replace Mongo `@ServiceConnection` with `@DynamicPropertySource` + `mongo::getReplicaSetUrl`.
4. Replace Redis dynamic properties with `@ServiceConnection(name="redis")`; update the test so it no longer asserts Environment host/port.
5. Try pinning `spring.data.redis.port=6379` in a sandbox and explain why it can connect to the wrong target.
6. Add a Mongo query `findByTitle` with fixtures distinguishing present and absent cases.
7. Add a unique index on `sku` via proper index configuration and verify `DuplicateKeyException`.
8. Test `redis.getExpire` when a key has no expiry and when a key does not exist; explain `-1` and `-2`.
9. Write a bounded polling test verifying a Redis key actually expires after a short TTL.
10. Update a Mongo document after Redis caching has occurred, observe the stale title, and then add invalidation.
11. Stop the Redis container in an **independent test class** to test fallback behavior without breaking shared resources for other tests.
12. Split tests across two Spring test classes with distinct static containers, observe context caching issues, and propose container beans to align lifecycles.
13. Use Testcontainers for Elasticsearch/Neo4j/Kafka if your app actually depends on them, ensuring proper schema/topic initialization.
14. Run the suite on Docker-in-Docker CI using real accessors instead of assuming `localhost`.
15. Inspect Gradle XML/HTML reports and verify exact PASS/FAIL/SKIPPED counts.
16. Add an integration test handling Redis connection timeouts/errors without using production credentials.
17. Distinguish container-to-container network aliases from host mapped ports on an experimental Docker network.

## 26. References

- [Spring Boot 3.3 — Testcontainers, service connections, and dynamic properties](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): lifecycle, `@ServiceConnection`, `MongoConnectionDetails`, Redis image names, `@DynamicPropertySource`.
- [Spring Boot 3.3 — Working with NoSQL Technologies](https://docs.spring.io/spring-boot/3.3/reference/data/nosql.html): MongoDB, Redis starters, and auto-configuration.
- [Spring Framework 6.1 — Dynamic Property Sources](https://docs.spring.io/spring-framework/docs/6.1.x/reference/html/testing.html#testcontext-ctx-management-dynamic-property-sources): `DynamicPropertyRegistry` and property precedence.
- [Testcontainers Java — JUnit 5](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers`, `@Container`, and lifecycle.
- [Testcontainers Java — MongoDB](https://java.testcontainers.org/modules/databases/mongodb/): `MongoDBContainer` and replica sets.
- [Testcontainers Java — Networking](https://java.testcontainers.org/features/networking/): `getHost`, `getMappedPort`, aliases.
- [Spring Data MongoDB Reference](https://docs.spring.io/spring-data/mongodb/reference/): Mongo documents, repositories, and mapping.
- [Spring Data Redis Reference](https://docs.spring.io/spring-data/redis/reference/): `StringRedisTemplate`, keys, and TTL.
- [Spring Framework TestContext — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): Spring cached contexts and lifecycle.

## 27. Conclusion

**Testcontainers** enables Spring Boot integration testing against **real backends** managed by Docker and the test lifecycle. **`@ServiceConnection`** connects specialized containers like `MongoDBContainer` to Spring Boot auto-configuration via `ConnectionDetails`. **`@DynamicPropertySource`** injects runtime values such as host, mapped port, and URI into the Spring `Environment`, fitting `GenericContainer` or custom backend setups.

The MongoDB + Redis example shows how to test all the way from Docker container readiness to Spring Data repositories/`RedisTemplate` and a cache-aside service. The highest value comes not from `container.isRunning()`, but from **real queries and commands** backed by clear assertions, proper fixture cleanup, and repeatability locally and in CI. Never confuse a single-node container with a production cluster, never rely on SQL rollback to clean NoSQL data, and never report test PASS counts without running Gradle with real Docker.
