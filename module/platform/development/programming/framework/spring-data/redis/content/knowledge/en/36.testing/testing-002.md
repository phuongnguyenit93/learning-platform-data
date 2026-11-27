# Mocking at the Service Boundary Instead of Simulating All of Redis in Spring Data Redis

## 1. The Problem: The Deeper You Simulate Redis, the More False Confidence Tests Create

A Spring Boot application uses Spring Data Redis to cache data, store OTPs, rate-limit login attempts, or hold temporary state. When writing unit tests, a developer might try mocking every underlying layer:

~~~text
BusinessService
     |
     v
RedisTemplate
     |
     v
ValueOperations / HashOperations / RedisConnection
     |
     v
Lettuce / Jedis / Serializer
     |
     v
Redis server
~~~

Example:

~~~java
@Mock
RedisTemplate<String, String> redisTemplate;

@Mock
ValueOperations<String, String> operations;

@BeforeEach
void setUp() {
    when(redisTemplate.opsForValue())
        .thenReturn(operations);
}

@Test
void readsFromRedis() {
    when(operations.get("products:v1:p-42"))
        .thenReturn("{\"id\":\"p-42\"}");
    // ...
}
~~~

Such a test can be useful for a narrow adapter layer. However, if the *business service* has to know Redis keys, serializers, command names, TTL, and connection mechanics, the test is coupled to the implementation rather than the business objective.

More dangerously, Mockito can return `true` twice for `setIfAbsent` on the same key even though real Redis `SET NX` enforces existence atomically. Mocks also lack TTL, replication lag, Redis Cluster slots, network failures, and Lua behavior.

**Principle:** Unit test business policies by mocking at the **service boundary**; verify Redis guarantees using **real Redis** in integration tests.

## 2. What Is a Service Boundary?

A service boundary is a contract that the business layer relies on to achieve its goal, for example:

~~~java
public interface ProductCache {
    Optional<ProductView> find(String id);
    void put(String id, ProductView snapshot, Duration ttl);
    void evict(String id);
}
~~~

The service only understands the semantics of `find`, `put`, and `evict`. It does not need to know:

- How the Redis key prefix is constructed.
- Whether `StringRedisTemplate`, `RedisTemplate`, or Lua is used.
- Whether Lettuce or Jedis is used.
- Which JSON serializer or key serializer is configured.
- Whether Redis runs standalone, Sentinel, or Cluster.
- How connections reconnect, pool, and send low-level commands.

Architecture:

~~~text
                    ProductQueryService
                           |
                    ProductCache port
                           |
                +----------+-----------+
                |                      |
                v                      v
         Mockito mock            RedisProductCache
         (unit test)              (production)
                                         |
                                         v
                                 StringRedisTemplate
                                         |
                                         v
                                       Redis
~~~

The same `ProductCache` contract has two testing paths: a mock to test business decisions, and a real adapter with real Redis to verify persistence.

This is an application of ports-and-adapters, not a rigid rule forcing extra interface layers into every program.

## 3. Dividing Testing Responsibilities

| Test Level | What to Verify | Tools |
| --- | --- | --- |
| Business service unit test | Cache hit/miss, errors, fallback, business decisions | JUnit 5 + Mockito |
| Pure logic unit test | DTO mapping, key policy, validation, deadlines | JUnit 5, no mocks required |
| Redis adapter integration | Keys, TTL, serializers, Redis commands, atomicity | Real Redis / Testcontainers |
| Spring integration | `@Cacheable`, `@CacheEvict`, AOP proxy, transactions, event lifecycle | Spring Test + Redis/database |
| Concurrency test | Can two clients execute the operation simultaneously? | Real Redis, multiple connections/threads |
| Fault/system test | Reconnect, failover, Cluster redirects, replication | Multi-node Redis topology |

Do not use a Mockito test to claim all of Redis has been tested. Conversely, do not force every unit test to launch Docker just to test a single logic branch.

## 4. Running Example: ProductQueryService with Cache-Aside

Suppose PostgreSQL is the authoritative data source and Redis is only a cache copy.

DTO:

~~~java
package com.example.products;

import java.math.BigDecimal;

public record ProductView(
    String id,
    String name,
    BigDecimal price
) { }
~~~

Repository port:

~~~java
package com.example.products;

import java.util.Optional;

public interface ProductReadRepository {
    Optional<ProductView> findById(String id);
}
~~~

Cache port:

~~~java
package com.example.products;

import java.time.Duration;
import java.util.Optional;

public interface ProductCache {
    Optional<ProductView> find(String id);
    void put(String id, ProductView snapshot, Duration ttl);
    void evict(String id);
}
~~~

Business exception:

~~~java
package com.example.products;

public class ProductNotFoundException extends RuntimeException {
    public ProductNotFoundException(String id) {
        super("Product not found: " + id);
    }
}
~~~

This contract contains no Redis APIs; it allows testing business logic with mocks and testing the Redis adapter against a real server.

## 5. Business Service Only Decides How to Use the Cache

~~~java
package com.example.products;

import java.time.Duration;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private static final Duration CACHE_TTL =
        Duration.ofMinutes(5);

    private final ProductReadRepository products;
    private final ProductCache cache;

    public ProductQueryService(
            ProductReadRepository products,
            ProductCache cache) {
        this.products = products;
        this.cache = cache;
    }

    public ProductView findById(String id) {
        return cache.find(id).orElseGet(() -> {
            ProductView product = products.findById(id)
                .orElseThrow(() ->
                    new ProductNotFoundException(id)
                );
            cache.put(id, product, CACHE_TTL);
            return product;
        });
    }
}
~~~

Flow:

~~~text
getById(id)
    |
    v
cache.find(id)
    |
    +-- HIT -> return ProductView
    |
    +-- MISS -> products.findById(id)
                    |
                    +-- NOT FOUND -> business error
                    |
                    +-- FOUND -> cache.put(id, view, 5 minutes)
                                       |
                                       v
                                   return view
~~~

This is the **cache-aside policy**. Whether the port implementation uses `GET`, `SET`, a Redis Hash, or Lua does not affect the policy definition.

## 6. Mockito Unit Test: Cache Hit Skips the Database

~~~java
package com.example.products;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.*;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.Optional;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

@ExtendWith(MockitoExtension.class)
class ProductQueryServiceTest {

    @Mock ProductReadRepository products;
    @Mock ProductCache cache;

    ProductQueryService service;

    @BeforeEach
    void init() {
        service = new ProductQueryService(products, cache);
    }

    @Test
    void returnsCacheHitWithoutReadingDatabase() {
        ProductView value = new ProductView(
            "p-42",
            "Spring Book",
            new BigDecimal("120000")
        );

        when(cache.find("p-42"))
            .thenReturn(Optional.of(value));

        ProductView actual = service.findById("p-42");

        assertThat(actual).isEqualTo(value);
        verify(cache).find("p-42");
        verifyNoInteractions(products);
        verify(cache, never()).put(
            anyString(),
            any(ProductView.class),
            any(Duration.class)
        );
    }
}
~~~

What the test **proves**: the service uses the cached snapshot when available, does not read the repository, and does not write the snapshot back unnecessarily.

What the test **does not prove**: that Redis contains the key, TTL is active, the serializer can parse the JSON, the Redis connection works, or replicas have no lag.

## 7. Mockito Unit Test: Cache Miss Must Load Data

In the same test class:

~~~java
@Test
void loadsDatabaseAndCachesSnapshotOnMiss() {
    ProductView fromDb = new ProductView(
        "p-42", "Spring Book", new BigDecimal("120000")
    );

    when(cache.find("p-42"))
        .thenReturn(Optional.empty());

    when(products.findById("p-42"))
        .thenReturn(Optional.of(fromDb));

    ProductView result = service.findById("p-42");

    assertThat(result).isEqualTo(fromDb);

    verify(products).findById("p-42");
    verify(cache).put(
        "p-42",
        fromDb,
        Duration.ofMinutes(5)
    );
}
~~~

This test only speaks to the contract:

~~~text
Cache miss -> read DB -> write cache with TTL -> return snapshot
~~~

It continues to pass if the implementation switches from a JSON string to a Redis Hash or Lua, as long as the business boundary stays unchanged.

If call ordering is an invariant to verify, use `InOrder`:

~~~java
InOrder inOrder = inOrder(cache, products);

inOrder.verify(cache).find("p-42");
inOrder.verify(products).findById("p-42");
inOrder.verify(cache).put(
    "p-42", fromDb, Duration.ofMinutes(5)
);
~~~

Do not verify the order of every method if ordering does not affect the contract.

## 8. Mockito Unit Test: Product Not Found

~~~java
@Test
void doesNotCacheMissingProduct() {
    when(cache.find("missing"))
        .thenReturn(Optional.empty());

    when(products.findById("missing"))
        .thenReturn(Optional.empty());

    assertThatThrownBy(
        () -> service.findById("missing")
    )
        .isInstanceOf(ProductNotFoundException.class)
        .hasMessageContaining("missing");

    verify(products).findById("missing");
    verify(cache, never()).put(
        anyString(),
        any(ProductView.class),
        any(Duration.class)
    );
}
~~~

Required import:

~~~java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
~~~

The current contract **does not negative-cache** missing products. If you want to cache negative results briefly, you must design a dedicated representation, TTL, and invalidation strategy rather than treating `null` as a dummy product.

## 9. RedisProductCache: The Right Place to Call Redis APIs

Adapter using `StringRedisTemplate` and Jackson:

~~~java
package com.example.products.redis;

import java.time.Duration;
import java.util.Optional;

import com.example.products.ProductCache;
import com.example.products.ProductView;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class RedisProductCache implements ProductCache {

    private static final String PREFIX = "products:v1:";

    private final StringRedisTemplate redis;
    private final ObjectMapper mapper;

    public RedisProductCache(
            StringRedisTemplate redis,
            ObjectMapper mapper) {
        this.redis = redis;
        this.mapper = mapper;
    }

    @Override
    public Optional<ProductView> find(String id) {
        String json = redis.opsForValue().get(key(id));

        if (json == null) {
            return Optional.empty();
        }

        try {
            return Optional.of(
                mapper.readValue(json, ProductView.class)
            );
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Invalid cache payload", ex
            );
        }
    }

    @Override
    public void put(
            String id,
            ProductView value,
            Duration ttl) {
        try {
            String json = mapper.writeValueAsString(value);
            redis.opsForValue().set(key(id), json, ttl);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                "Cannot serialize product", ex
            );
        }
    }

    @Override
    public void evict(String id) {
        redis.delete(key(id));
    }

    private String key(String id) {
        return PREFIX + id;
    }
}
~~~

The adapter is responsible for:

- The key prefix `products:v1:`.
- Serialization/deserialization of the DTO.
- Mapping a Redis cache miss to `Optional.empty()`.
- Redis TTL on `put`.
- Deletion on `evict`.
- Reporting invalid payloads.

The business service does not care about these details. These details must be verified in the **adapter's integration tests**, not in every service unit test.

## 10. Testing the Adapter: When Is Mocking `RedisTemplate` Useful?

A small unit test for the adapter can mock `StringRedisTemplate` and `ValueOperations` to verify the key is assembled properly:

~~~java
@Mock StringRedisTemplate redis;
@Mock ValueOperations<String, String> operations;

@BeforeEach
void init() {
    when(redis.opsForValue()).thenReturn(operations);
}
~~~

However, understand that it only tests **stubbed invocations**. It does not prove:

- JSON is stored and read properly.
- Redis creates a positive TTL.
- Real Redis returns `null` when the key is absent.
- The prefix serializes to the right Redis bytes.
- Which exception types occur on Redis timeout, connection refused, or permission errors.
- Redis Cluster multi-key constraints.

For a relatively simple adapter, one Redis integration test can be more valuable than a complex chain of mocks.

**There is no rule “forbidding mocking `RedisTemplate`”**; the point is keeping mocks in the right scope and not overstating what the test proves.

## 11. Separating Port Semantics from Redis Implementation

A well-designed port states its outcomes clearly:

~~~text
ProductCache.find(id)
  HIT                -> Optional.of(snapshot)
  MISS               -> Optional.empty()
  Redis unavailable  -> meaningful exception
  Payload invalid    -> exception or explicit policy
~~~

Do not write the adapter like this:

~~~java
public Optional<ProductView> find(String id) {
    try {
        return readFromRedis(id);
    } catch (Exception ex) {
        return Optional.empty();
    }
}
~~~

because it turns every Redis error into a cache miss, hiding outages and corrupt data. If fallback happens thousands of times per second, the authoritative database can be overwhelmed.

Define a dedicated exception type instead, for example:

~~~java
public class CacheUnavailableException
        extends RuntimeException {

    public CacheUnavailableException(Throwable cause) {
        super("Cache unavailable", cause);
    }
}
~~~

The adapter translates appropriate Redis connectivity errors to this type. Do not catch all exceptions indiscriminately without defining the policy for each error category.

## 12. Fail-Open and Fail-Closed Are Business Decisions

**Redis is just a product cache:** when unavailable, the service can read from the database if the system can handle the fallback load.

**Redis enforces rate limits, OTPs, or locks:** when unavailable, letting all requests through can be dangerous. Operations may need to be rejected or routed to another control mechanism.

Illustrative fail-open service:

~~~java
public ProductView findWithFallback(String id) {
    try {
        Optional<ProductView> cached = cache.find(id);

        if (cached.isPresent()) {
            return cached.get();
        }
    } catch (CacheUnavailableException ex) {
        // In production: record logs and metrics.
    }

    ProductView fromDb = products.findById(id)
        .orElseThrow(() ->
            new ProductNotFoundException(id)
        );

    try {
        cache.put(id, fromDb, Duration.ofMinutes(5));
    } catch (CacheUnavailableException ex) {
        // Cache is best effort; return data from the authoritative source.
    }

    return fromDb;
}
~~~

This method can live in the service and should include real logging/metrics rather than silently swallowing exceptions.

Mockito unit test:

~~~java
@Test
void readsDatabaseWhenCacheIsUnavailable() {
    ProductView fromDb = new ProductView(
        "p-42", "Redis Book", new BigDecimal("120000")
    );

    when(cache.find("p-42"))
        .thenThrow(
            new CacheUnavailableException(
                new RuntimeException("Connection refused")
            )
        );

    when(products.findById("p-42"))
        .thenReturn(Optional.of(fromDb));

    ProductView actual =
        service.findWithFallback("p-42");

    assertThat(actual).isEqualTo(fromDb);
    verify(products).findById("p-42");
}
~~~

This test confirms the **fallback policy**, not real Lettuce reconnection or Redis failover.

## 13. Avoid an Interface That Merely Renames Redis APIs

An overly generic abstraction:

~~~java
public interface KeyValueStore {
    Object get(String key);
    void set(String key, Object value);
    void delete(String key);
}
~~~

still makes the business service operate in terms of Redis commands, just under a renamed interface.

Business-aligned boundaries are usually better:

~~~java
public interface OneTimeTokenStore {
    Optional<TokenPayload> consume(String tokenId);
}
~~~

~~~java
public interface LoginAttemptLimiter {
    boolean tryAcquire(
        String accountId,
        int maxAttempts,
        Duration window
    );
}
~~~

~~~java
public interface InventoryReservationGateway {
    ReservationResult tryReserve(
        String orderId,
        String sku,
        int quantity
    );
}
~~~

These ports state clear capabilities: consuming a token, requesting permission past a rate limit, reserving stock. Business unit tests can mock `SUCCESS`/`DENIED` outcomes; the Redis adapter must implement true atomicity and undergo independent integration testing.

## 14. OTP: Why You Must Not Fake GET-Then-DEL as Atomic

A broken implementation:

~~~text
GET otp:123
If present:
    DEL otp:123
    return token
~~~

Two concurrent requests:

~~~text
Thread A                     Thread B
--------                     --------
GET -> token                 GET -> token
DEL                          DEL
return token                 return token
~~~

Both can use the same OTP, violating the one-time rule.

A good contract:

~~~java
public interface OneTimeTokenStore {
    Optional<TokenPayload> consume(String tokenId);
}
~~~

The Redis adapter can use `GETDEL` (when the Redis/client version supports it) or an appropriate Lua script to perform atomic consumption.

A business service unit test can mock:

~~~java
when(tokens.consume("otp-123"))
    .thenReturn(Optional.empty());

VerificationResult result =
    verificationService.verify("otp-123");

assertThat(result.accepted()).isFalse();
~~~

`TokenPayload`, `VerificationResult`, and `verificationService` are domain types from the OTP example that need to be implemented separately. The purpose is illustrating how to mock the port, not providing a self-contained test class with all dependencies.

**This unit test does not prove the Redis adapter is atomic.** A concurrency integration test is needed.

## 15. Concurrency Integration Test for One-Time Token Consumption

A proper test for `consume` should:

1. Create a real token on test Redis with a TTL.
2. Create multiple independent clients/connections.
3. Use a barrier so threads start simultaneously.
4. Have each thread call `OneTimeTokenStore.consume(id)`.
5. Wait for all futures to finish with a finite timeout.
6. Count the number of successful consumptions.
7. Assert **at most one** request succeeds.
8. Verify the token no longer exists in Redis.
9. Repeat with a fresh test token/namespace.

A `Map` fake does not accurately reproduce Redis `GETDEL`, Lua, replication, or networking. A Mockito stub pre-selecting which request wins also fails to prove real atomicity.

## 16. Lua Scripts and Final State

Example of a single-key inventory decrement script:

~~~lua
local stock = tonumber(
    redis.call('GET', KEYS[1]) or '0'
)
local qty = tonumber(ARGV[1])

if not qty or qty <= 0 then
    return -1
end

if stock < qty then
    return 0
end

redis.call('DECRBY', KEYS[1], qty)
return 1
~~~

This is an illustrative example of atomic check-and-decrement. Real inventory reservation also needs idempotency by order ID, reservation status, and a retry policy.

Service unit tests can mock `InventoryReservationGateway.tryReserve` returning various outcomes. However, Redis integration tests must verify:

- The script command actually runs on Redis.
- Invalid inputs do not cause writes.
- Two competing clients do not drive stock negative.
- Result codes are accurate.
- Serializers and keys/`ARGV` match.
- Script keys in Redis Cluster share a hash slot if multi-key operations are needed.

**Redis Lua atomicity does not mean rolling back all writes executed before the script hits a runtime error.** This is a real Redis detail that mocks cannot guarantee.

## 17. `@Cacheable` Does Not Run When Instantiating Objects with `new` in Unit Tests

Example:

~~~java
@Service
public class ProductQueryWithAnnotation {

    private final ProductReadRepository products;

    public ProductQueryWithAnnotation(
            ProductReadRepository products) {
        this.products = products;
    }

    @Cacheable(cacheNames = "productById", key = "#id")
    public ProductView findById(String id) {
        return products.findById(id)
            .orElseThrow(() ->
                new ProductNotFoundException(id)
            );
    }
}
~~~

If a unit test writes:

~~~java
var service = new ProductQueryWithAnnotation(
    mockRepository
);

service.findById("p-42");
~~~

this call **does not pass through a Spring proxy**. The `@Cacheable` annotation is not executed automatically by a freshly instantiated Java object.

Testing the method body like this is completely valid if you only want repository logic, but it **does not prove caching**.

Testing caching annotations requires:

- A Spring context with `@EnableCaching`.
- The right `CacheManager`.
- Calling through the Spring-managed bean/proxy.
- Checking that a subsequent read is cached.
- Checking keys, serializers, and TTL if Redis is the backing store.

## 18. Self-Invocation and Spring AOP

A service:

~~~java
public void refresh(String id) {
    this.findById(id);
}

@Cacheable(cacheNames = "productById")
public ProductView findById(String id) {
    // ...
}
~~~

In standard Spring proxy mode, calling `this.findById` can bypass caching advice. Pure Java unit tests cannot catch this issue.

Therefore, separate two questions:

- Is the business logic of `findById` correct? → unit test.
- Does the call go through the Spring proxy, use `RedisCacheManager`, and cache properly? → integration test.

If using `@CacheEvict` and `@CachePut`, the same principle applies.

## 19. `@CacheEvict` Does Not Prove the Database Committed

Suppose:

~~~java
@Transactional
public void changePrice(String id, BigDecimal price) {
    repository.updatePrice(id, price);
    cache.evict(id);
}
~~~

Mockito can verify:

~~~java
verify(repository).updatePrice("p-42", newPrice);
verify(cache).evict("p-42");
~~~

However, it **does not prove** eviction happens only after the database commits. The method could return and then the transaction rolls back, or a concurrent reader could repopulate Redis with the old value after eviction.

Tests must be separated:

- Unit: the service issues the command/event with the right ID.
- DB+Redis integration: transaction commit/rollback and invalidation timing.
- After-commit: `@TransactionalEventListener(AFTER_COMMIT)` runs properly.
- Concurrency: cache-miss reader competing with writer.
- Recovery: application crashes after DB commit before Redis eviction—is TTL/outbox needed?

Mockito does not combine a database and Redis into a single atomic transaction.

## 20. Fake, Mock, Stub, and Spy Differ

| Test Double Type | Example | Role |
| --- | --- | --- |
| Stub | `when(cache.find(id)).thenReturn(...)` | Supplies canned responses |
| Mock | `verify(cache).evict(id)` | Verifies interactions |
| Fake | In-memory cache backed by `Map` | Runs multi-step flows with simple state |
| Spy | Wraps a real object | Observes specific behavior, used intentionally |
| Real dependency | Redis via Testcontainers | Verifies the real Redis contract |

In-memory fake:

~~~java
public class InMemoryProductCache implements ProductCache {

    private final Map<String, ProductView> values =
        new HashMap<>();

    @Override
    public Optional<ProductView> find(String id) {
        return Optional.ofNullable(values.get(id));
    }

    @Override
    public void put(
            String id,
            ProductView value,
            Duration ttl) {
        values.put(id, value);
    }

    @Override
    public void evict(String id) {
        values.remove(id);
    }
}
~~~

Requires imports for `Map`, `HashMap`, `Optional`, and `Duration`.

This fake **does not enforce TTL** and does not behave like Redis under concurrency. It only helps test stateful business flows, not verify a Redis server.

## 21. Clock Injection for Business Deadlines

To test expiration policies without sleeping:

~~~java
import java.time.Clock;
import java.time.Instant;

public class ExpiryPolicy {

    private final Clock clock;

    public ExpiryPolicy(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(Instant deadline) {
        return !Instant.now(clock).isBefore(deadline);
    }
}
~~~

Unit test:

~~~java
Clock fixed = Clock.fixed(
    Instant.parse("2026-11-13T10:00:00Z"),
    ZoneOffset.UTC
);

ExpiryPolicy policy = new ExpiryPolicy(fixed);

assertThat(
    policy.isExpired(
        Instant.parse("2026-11-13T09:59:59Z")
    )
).isTrue();
~~~

Requires importing `ZoneOffset` and AssertJ.

This test proves the **business deadline policy**, not Redis TTL. Advancing a Java clock does not move a real Redis server into the future.

## 22. Real Redis TTL Requires Integration Tests

When the adapter uses:

~~~java
redis.opsForValue().set(
    "products:v1:p-42",
    json,
    Duration.ofSeconds(120)
);
~~~

A test against real Redis can check:

~~~java
Long ttl = redis.getExpire(
    "products:v1:p-42",
    TimeUnit.SECONDS
);

assertThat(ttl).isNotNull();
assertThat(ttl).isGreaterThan(0L);
assertThat(ttl).isLessThanOrEqualTo(120L);
~~~

Requires `java.util.concurrent.TimeUnit`.

Do not assert exact `120L` in every environment: time elapses and Redis returns TTL in whole seconds.

When testing actual expiration, poll with a timeout rather than calling `Thread.sleep(120000)` and expecting a callback on the exact millisecond. Redis expired events can arrive later than the logical deadline.

## 23. Testcontainers: Real Redis in CI

Spring Boot integration test example:

~~~java
package com.example.products.redis;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Duration;

import com.example.products.ProductCache;
import com.example.products.ProductView;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RedisProductCacheIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.2-alpine")
        ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    ProductCache cache;

    @Test
    void storesReadsAndEvictsProduct() {
        ProductView product = new ProductView(
            "p-test-1",
            "Redis Book",
            new BigDecimal("150000")
        );

        cache.put(
            "p-test-1",
            product,
            Duration.ofMinutes(2)
        );

        assertThat(cache.find("p-test-1"))
            .contains(product);

        cache.evict("p-test-1");

        assertThat(cache.find("p-test-1"))
            .isEmpty();
    }
}
~~~

This sample assumes the application has `RedisProductCache`, `ObjectMapper`, and Redis connection auto-configuration beans. If the app also requires a database or other external services to start up, the test must provide test dependencies or configure a suitably narrowed Spring context.

With older Spring Boot versions, the prefix may be `spring.redis.*` instead of `spring.data.redis.*`. Match the project's version.

A standalone Redis container **is not a Redis Cluster**. Cluster/Sentinel testing requires an appropriate multi-process/multi-node topology.

## 24. Redis Adapter Cases Worth Testing

| Scenario | Expected Outcome |
| --- | --- |
| Reading a missing key | `Optional.empty()` |
| Put + get | DTO round-trips properly |
| Put TTL | TTL is positive and matches policy |
| Evict | Key disappears |
| Overwriting put | New snapshot is read back |
| Unicode | No character corruption |
| BigDecimal | No distortion of monetary precision |
| Unreadable JSON | Explicit exception/policy |
| Redis unavailable | Error mapped appropriately |
| Cache schema version change | Backward compatibility or versioned namespace |
| Multiple instances sharing cache | No cross-tenant data leakage |
| Retry after timeout | No dangerous duplicate side effects |

This table tests the **Redis contract**, which cannot be replaced by Mockito stubs.

## 25. Serializers Are Details That Must Be Tested for Real

Spring Data Redis offers several serialization approaches:

- `StringRedisSerializer`.
- Versioned Jackson JSON serializers.
- Custom binary serializers.
- Redis Hash mapping.

Questions to test:

- Is type metadata compatible across releases?
- Are Java records, enums, `Instant`, and `BigDecimal` restored properly?
- Are keys serialized into the strings operators expect?
- Can old values still be read after a schema change?
- Could untrusted data undergo unsafe polymorphic deserialization?

A stub like:

~~~java
when(serializer.deserialize(any()))
    .thenReturn(product);
~~~

does not prove real bytes are valid. You can test the serializer directly with real DTOs/bytes, and then test the adapter against a Redis server to verify the full pipeline.

## 26. Redis Cluster Cannot Be Replaced by a HashMap

Redis Cluster partitions keys across **16,384 hash slots**. Multi-key commands, Lua scripts, and transactions have same-slot constraints.

Example sharing a slot via a hash tag:

~~~text
cart:{user-42}:items
cart:{user-42}:total
~~~

These two keys have no same-slot guarantee:

~~~text
cart:user-42:items
stock:sku-99
~~~

A fake `Map` has no hash slots, `CROSSSLOT`, `MOVED`, `ASK`, failover, or topology refresh. If the production adapter uses Cluster, integration tests must run against a real Redis Cluster when verifying these behaviors.

## 27. Pub/Sub and Streams Cannot Be Proved by Mocking Handlers Either

A receiver:

~~~java
public class OrderEventReceiver {
    private final OrderProcessor processor;

    public OrderEventReceiver(OrderProcessor processor) {
        this.processor = processor;
    }

    public void receiveMessage(String json) {
        processor.process(json);
    }
}
~~~

Unit test:

~~~java
receiver.receiveMessage("{\"orderId\":\"o-42\"}");

verify(processor).process(
    "{\"orderId\":\"o-42\"}"
);
~~~

This only proves the receiver forwards the payload properly. It does not prove:

- `RedisMessageListenerContainer` subscribed.
- The adapter has a matching serializer.
- Redis Pub/Sub replays messages.
- An offline subscriber misses events or not.
- Multiple pods duplicate processing.

Redis Pub/Sub is at-most-once and does not replay for offline subscribers. For mandatory work, use a durable queue/Stream/outbox and proper idempotency.

## 28. Redis Failover and Replication Require Dedicated Fault Tests

Scenarios such as:

~~~text
Primary returns OK
Replica has not received the write yet
Primary dies
Replica is promoted
The write may not exist on the new primary
~~~

cannot be simulated accurately by mocking a Redis connection exception.

Similarly, `READONLY`, `MOVED`, `ASK`, Sentinel failover, and Lettuce reconnection require a multi-node Redis environment if they are critical operational requirements.

Mockito is great for testing how a service **handles a simulated exception**, but it does not prove when real Redis throws that exception, how the client retries, or which data survives failover.

## 29. Testing Redis Failures: Distinguish Mapping from Policy

Suppose a service catches `CacheUnavailableException` and falls back to the database.

- **Unit test:** mocks the port to throw `CacheUnavailableException`, verifying the service falls back.
- **Adapter integration test:** makes Redis unreachable or uses fault injection, verifying real exceptions are mapped to the right type.
- **Load test:** verifies fallback volume does not overload the database.
- **System test:** checks whether reconnect and failover restore the service to normal operation.

If you only have service unit tests, you cannot know whether the adapter actually throws the exception type the service catches.

## 30. Do Not Over-Verify Implementation Details

A brittle test might do:

~~~java
verify(cache, times(1)).find(id);
verify(products, times(1)).findById(id);
verify(cache, times(1)).put(id, snapshot, ttl);
verifyNoMoreInteractions(cache, products);
~~~

This is occasionally appropriate, but should not be applied mechanically.

Prefer:

1. Asserting the outcomes the caller cares about.
2. Verifying important side effects.
3. Verifying “no DB call on cache hit” because that is a performance invariant.
4. Verifying call order/counts only when necessary.
5. Not verifying every getter, logger, or internal serializer inside the service.
6. Using `ArgumentCaptor` when the service transforms a payload that must be inspected.

Example captor:

~~~java
ArgumentCaptor<ProductView> captor =
    ArgumentCaptor.forClass(ProductView.class);

verify(cache).put(
    eq("p-42"),
    captor.capture(),
    eq(Duration.ofMinutes(5))
);

assertThat(captor.getValue().price())
    .isEqualByComparingTo("120000");
~~~

If the service passes the snapshot unmodified from the repository, you can verify the expected object directly instead of using a captor.

## 31. Isolating Redis Integration Tests

To keep tests from interfering with each other:

- Use unique key prefixes and random IDs per test.
- Delete created keys when finished.
- Do not run `FLUSHALL` on a shared Redis outside a dedicated test environment.
- Avoid parallel tests touching the same keys.
- Pin the Redis image version in CI for reproducibility.
- Do not point tests to production Redis by default.
- With cached Spring contexts, remember the Redis container may still hold data from earlier tests.
- With Cluster, cleanup must account for per-shard scope.

An integration test with unique keys is less flaky than one relying on execution order.

## 32. Comprehensive Test Matrix

| Requirement | Mocked Port Unit | Real Redis | Spring Context | Multi-Node / Fault |
| --- | --- | --- | --- | --- |
| Cache hit skips DB | Yes | Optional | If using annotations | No |
| Cache miss writes snapshot | Yes | Yes to test value/TTL | Possible | No |
| Positive TTL | Verify `Duration` only | Yes | Possible | No |
| DTO serialization | No | Yes | Possible | No |
| Atomic Redis `SET NX` | Insufficient | Yes, concurrency | Optional | Possible |
| Lua stock reservation | Result mapping only | Yes, concurrency | Possible | Possible |
| `@Cacheable`/proxy | No | Possible | Yes | No |
| Evict after DB commit | Intent/event only | Possible | Yes with DB | Possible |
| Pub/Sub message delivery | Receiver logic only | Yes | Yes | Yes with reconnect |
| Redis Cluster slot constraints | No | Real Cluster | Possible | Yes |
| Sentinel failover | No | Not via standalone | Insufficient | Yes |
| Fallback during Redis outage | Yes | Test exception mapping | Possible | Load/fault test |

## 33. Organizing Source Code and Tests

~~~text
src/main/java/com/example/products/
├── domain/
│   ├── ProductView.java
│   ├── ProductReadRepository.java
│   └── ProductCache.java
├── application/
│   └── ProductQueryService.java
├── infrastructure/
│   ├── redis/
│   │   └── RedisProductCache.java
│   └── jpa/
│       └── JpaProductRepositoryAdapter.java
└── web/
    └── ProductController.java

src/test/java/com/example/products/
├── application/
│   └── ProductQueryServiceTest.java
└── infrastructure/redis/
    └── RedisProductCacheIntegrationTest.java
~~~

You do not need to follow this directory tree dogmatically. What matters is that the business layer depends on **meaningful contracts**, while Redis APIs live in the adapter so each layer can be tested properly.

## 34. Common Misconceptions

**“Mocking more of `RedisTemplate` makes unit tests more accurate.”** No. You just have more stubs; if you model Redis semantics wrongly, tests pass while the app breaks.

**“A fake `HashMap` is just like Redis for every test.”** No. It lacks TTL, serialization, concurrency semantics, networking, Cluster, replication, and failover.

**“Mockito verifying `cache.put` proves TTL.”** No. It only proves the service passed a `Duration`, not that Redis set an expiration on the key.

**“A unit test creating a `@Cacheable` service with `new` will use caching.”** No. Spring AOP proxies do not appear on manually instantiated objects.

**“Mocking `GET` then `DEL` proves one-time OTP.”** No. Two separate commands have a race; you need an atomic command and a Redis concurrency test.

**“Mocking a Redis connection exception is enough to test failover.”** No. The test only verifies the error branch, not election, promotion, routing, or real reconnection.

**“Every Redis outage can be treated as a cache miss.”** No. Redis may be the authoritative store for locks, tokens, or rate limiters; failing open wrongly can cause business errors.

**“Because we have Redis integration tests, we don't need unit tests.”** No. Unit tests are fast and clarify policies; integration tests focus on Redis contracts and Spring wiring.

**“A single Redis container is a Redis Cluster.”** No. Cluster has hash slots and a multi-node topology.

**“Verifying more internal method calls is safer.”** No. Over-verifying makes tests brittle and hard to refactor.

## 35. Exercise A: Refactoring a Service Using `RedisTemplate`

A service currently calls:

~~~java
String json =
    redis.opsForValue().get("products:v1:" + id);

redis.opsForValue().set(
    "products:v1:" + id,
    json,
    Duration.ofMinutes(5)
);
~~~

Tasks:

1. Create `ProductCache` with `find/put/evict`.
2. Move key formatting and JSON handling into `RedisProductCache`.
3. Make the service depend only on the port.
4. Write unit tests for cache hit, miss, and not-found.
5. Write integration tests for keys, serializers, TTL, and deletion.
6. Explain why changing the serializer does not break the business unit tests.

## 36. Exercise B: One-Time Token and Concurrency

Design `OneTimeTokenStore.consume`:

1. Unit test the service when the port returns a token or empty.
2. Have the Redis adapter use an appropriate atomic operation.
3. Fire multiple concurrent requests for the same token.
4. Assert at most one request succeeds.
5. Verify the token has been consumed.
6. Simulate a Redis timeout and explain why the outcome can be ambiguous.
7. Define idempotency if the response is lost after the token was consumed.

## 37. Exercise C: Spring Cache Annotations

For a `@Cacheable` method:

1. Unit test the method's logic on a plain Java object.
2. Spring integration test via the bean/proxy.
3. Call twice with the same key and verify cache hit.
4. Evict the exact key and read again.
5. Test whether self-invocation bypasses advice.
6. If invalidation after commit is needed, use a transaction integration test instead of mocking transactions.

## 38. Exercise D: Cache Failure and Rate-Limit Failure

Create two ports:

- `ProductCache`: cache hit/miss, can fall back to the database.
- `LoginAttemptLimiter`: decides whether to allow login, does not fail open by default on Redis error.

Tasks:

1. Define the exception contract.
2. Unit test error branches via mocked ports.
3. Integration test Redis outage mapping.
4. Define metrics, fallbacks, and circuit breakers.
5. Evaluate the impact of a Redis outage on the database and security.

## 39. Frequently Asked Questions

**Should mocking `RedisTemplate` be banned completely?**

No. Mocking Redis APIs can make sense in a small adapter test. What to avoid is making the business service depend on every Redis detail and treating the mocking framework as a Redis server.

**When should a dedicated interface be created?**

When a capability has business semantics, error/atomicity boundaries worth defining, or helps isolate infrastructure. Do not mechanically create unnecessary interfaces for every single method.

**Can unit tests verify TTL?**

Only which TTL the service requested. Whether real Redis creates and enforces TTL belongs in integration tests.

**Does mocking a `consume` port prove a token is only used once?**

No. It allows testing the service policy. The Redis adapter needs a concurrency test on a real server.

**Why does testing `@Cacheable` require a Spring context?**

Because caching annotations normally work via Spring AOP proxies. Calling objects created with `new` bypasses the proxy.

**Can Redis failover be tested with Mockito?**

You can test how business code reacts to a simulated exception, but it does not prove real failover/reconnect. An appropriate Redis topology and fault test are required.

**Does using Redis Testcontainers slow down tests?**

It is slower than pure unit tests, so group them separately and run them in CI as appropriate. In return, it catches bugs mocks miss.

**Should one fake `Map` be used for the entire suite?**

Only for flows that do not depend on TTL, atomicity, or Redis behavior. The fake must clearly state its limits.

**What if both cache miss and Redis error return empty?**

The service cannot distinguish normal misses from outages, easily triggering uncontrolled fallback traffic. Have an explicit error contract.

**Can Redis integration tests be skipped if only non-critical data is cached?**

Base the decision on risk, but even simple caches suffer from key/serializer/TTL bugs worth verifying. There is no need to simulate Redis just to avoid those tests.

## 40. Key Takeaways

- **Business service unit tests mock ports** such as `ProductCache`, `OneTimeTokenStore`, `InventoryReservationGateway`, or repositories.
- **Do not simulate all of Redis** with Mockito and treat it as a guarantee of TTL, Lua, atomicity, replication, or failover.
- **The Redis adapter** owns key prefixes, serializers, Redis commands, TTL, and error mapping.
- **Integration tests on real Redis** verify the semantics provided by Redis.
- **Spring integration tests** verify annotations, AOP proxies, transactions, and caching lifecycles.
- **Concurrency/fault tests** verify races, Cluster/Sentinel, and retries per system requirements.
- **Mocking at the boundary makes tests less brittle**, because changing the Redis implementation does not change policy service tests.
- **Error contracts must be explicit**: cache miss differs from Redis unavailable; fail-open/fail-closed depends on the authoritative source's role.

The goal is not maximizing mocks or eliminating all integration tests. The goal is **verifying each guarantee at the layer that actually provides it**: business logic with unit tests, Redis semantics with real Redis, and distributed behavior with appropriate topology/fault tests.

## References

- [Spring Data Redis – RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis – Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis – Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html)
- [Spring Data Redis – Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis – Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Framework – Testing](https://docs.spring.io/spring-framework/reference/testing.html)
- [Mockito – Official Documentation](https://site.mockito.org/)
- [JUnit 5 – User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Testcontainers for Java – Documentation](https://java.testcontainers.org/)
- [Redis – EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis – GETDEL](https://redis.io/docs/latest/commands/getdel/)
- [Redis – EVAL](https://redis.io/docs/latest/commands/eval/)
- [Redis – Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
