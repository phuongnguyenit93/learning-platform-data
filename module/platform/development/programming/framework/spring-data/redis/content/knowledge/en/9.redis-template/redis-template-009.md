# Sharing Templates Across Threads and Keeping Configuration Stable

In a Spring Boot application, many HTTP requests, scheduled jobs, and message consumers can interact with Redis concurrently through a single `RedisTemplate` or `StringRedisTemplate` bean. A common question is: **should you create a new `RedisTemplate` per request to avoid contention across threads?**

In Spring Data Redis, **`RedisTemplate` is designed to be shared across multiple threads once configured and initialized**. The standard pattern is defining the template once as a Spring singleton bean, injecting it into multiple services, and calling Redis operations from many concurrent threads.

However, that conclusion comes with clear boundaries:

- **The template is shareable; its configuration must remain stable** while the application is using it.
- **Not every related object is thread-safe**: `RedisConnection`, callbacks, serialized Java objects, and custom mutable state can still cause race conditions.
- **Template thread-safety does not make multi-command business sequences atomic**. Two threads calling `GET` then `SET` can still suffer lost updates.
- **Connections and pooling belong to `RedisConnectionFactory`/the driver**. You do not need per-request templates just because requests run concurrently.

This lesson explains the template lifecycle, what can safely be shared, how to keep serializers and connection factories consistent, and sound design patterns in Spring Data Redis.

## 1. Placing `RedisTemplate` Correctly in the Architecture

Execution path of an operation like `redis.opsForValue().get(key)`:

~~~text
Request A ----> ProductService ----\
                                    \
Request B ----> OrderService --------> RedisTemplate singleton
                                    /          |
Scheduled job ---------------------/           v
                                      RedisConnectionFactory
                                               |
                                        Lettuce or Jedis
                                               |
                                         Redis server
~~~

Different components carry different responsibilities:

| Component | Responsibility | Multi-threaded usage |
|---|---|---|
| `RedisTemplate<K,V>` | Holds connection factory, serializers, and Redis operations groups | **Shareable after configuration completes** |
| `StringRedisTemplate` | Specialized template for string keys and values | **Shareable after configuration completes** |
| `ValueOperations`, `HashOperations`, ... | Command APIs invoked via the template | Use per key/value context; avoid shared mutable business state |
| `RedisConnectionFactory` | Supplies connections for individual operations | Normally a singleton; coordinates with the driver |
| `RedisConnection` | Executes commands over an acquired connection; may hold transaction/pipeline state | **Do not retain for concurrent multi-thread calls** |
| Native Lettuce/Jedis client | Manages protocol, sockets, reconnects, and topology | Sharing rules depend on driver/connection type |
| Serializer | Converts keys/values between Java objects and `byte[]` | Must be thread-safe and consistently configured |
| Domain object `V` | Specific data being serialized/deserialized | Does not become thread-safe automatically because of the template |

**Distinguish sharing a template from sharing a raw connection.** The template is a high-level API whose lifecycle is managed by Spring. It borrows and releases connections per Spring Data Redis and factory mechanisms; holding a specific connection in a service and calling it from multiple threads is an entirely different matter.

## 2. Why Can `RedisTemplate` Be a Singleton?

`RedisTemplate` primarily holds configuration references such as:

- `RedisConnectionFactory` for accessing Redis;
- key/value serializers and hash key/value serializers;
- default serializer, transaction support, and execution options;
- implementations of operations groups like `opsForValue()`, `opsForHash()`, and `opsForSet()`.

When executing `get`, `set`, `increment`, or `hGet`, the template **does not mutate these configuration references**. It encodes data into bytes, executes the command over a factory-supplied connection, reads the reply, and decodes it back into a Java type.

This allows multiple callers to use the same template concurrently:

~~~text
                  +--> Thread 1: GET product:101
                  |
RedisTemplate ----+--> Thread 2: SET product:102
                  |
                  +--> Thread 3: INCR counter:requests
                  |
                  +--> Thread 4: HGET user:7 name
~~~

Commands can be issued concurrently. The Redis server processes commands per Redis's execution model, while the driver handles multiplexing or pooling physical connections as designed.

In a typical Spring Boot application, `@Bean` creates a **singleton**-scoped bean by default. When two services inject that bean, both receive the exact same template instance. That is the intended usage.

### 2.1. Thread-Safe After Configuration Does Not Mean "Call Any Setter Anytime"

The template supports concurrent use **after initialization**. Do not generalize that calling `setValueSerializer`, `setConnectionFactory`, or changing transaction settings while serving Redis commands is safe.

Configuration setters belong during bean creation, before any request can use the template. Afterwards, invoke only data-operation APIs:

~~~text
Initialization phase:
    new RedisTemplate<>()
    -> setConnectionFactory(...)
    -> setKeySerializer(...)
    -> setValueSerializer(...)
    -> Spring completes bean lifecycle

Runtime phase:
    Services A/B/C concurrently call opsForValue/opsForHash/...
    -> DO NOT mutate template configuration
~~~

This is the **"configure once, use many times"** principle.

### 2.2. What Spring Does During Initialization

`RedisTemplate` implements Spring's initialization lifecycle to set up internal components once bean properties are configured. When declared via `@Bean`, Spring invokes the appropriate lifecycle callbacks before exposing the bean for normal use.

Therefore, you do not need to call `afterPropertiesSet()` in every service or request. If you manually construct a template with `new RedisTemplate<>()` outside the Spring container, your code must explicitly ensure it is configured and initialized per the API/lifecycle contract.

An initialized template must also be **safely published** to other threads. Defining it as a Spring singleton bean injected by the container provides proper lifecycle and safe publication. Never store a half-configured template in a global variable for threads to start calling right away.

## 3. Declaring a Shared Template in Spring Boot

Example illustrating a JSON template for a fixed target type. The application defines a cache model:

~~~java
package com.example.redisexample;

public record ProductCache(
        String id,
        String title,
        long priceInCents) {
}
~~~

Configuring a bean shared across multiple services (Spring Data Redis 3.x, Jackson 2 API example):

~~~java
package com.example.redisexample;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration
public class RedisCacheConfiguration {

    @Bean("productCacheTemplate")
    public RedisTemplate<String, ProductCache> productCacheTemplate(
            RedisConnectionFactory connectionFactory,
            ObjectMapper objectMapper) {

        RedisTemplate<String, ProductCache> template =
                new RedisTemplate<>();

        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(
                        objectMapper, ProductCache.class));

        // Configured at bean creation time.
        // Spring completes initialization before services use it.
        return template;
    }
}
~~~

Two services can inject **the same bean**:

~~~java
package com.example.redisexample;

import java.time.Duration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheWriter {
    private final RedisTemplate<String, ProductCache> redis;

    public ProductCacheWriter(
            @Qualifier("productCacheTemplate")
            RedisTemplate<String, ProductCache> redis) {
        this.redis = redis;
    }

    public void put(ProductCache product) {
        redis.opsForValue().set(
                key(product.id()), product, Duration.ofMinutes(15));
    }

    private String key(String productId) {
        return "product:cache:" + productId;
    }
}

@Service
public class ProductCacheReader {
    private final RedisTemplate<String, ProductCache> redis;

    public ProductCacheReader(
            @Qualifier("productCacheTemplate")
            RedisTemplate<String, ProductCache> redis) {
        this.redis = redis;
    }

    public ProductCache get(String productId) {
        return redis.opsForValue()
                .get("product:cache:" + productId);
    }
}
~~~

Both services hold a `final` reference to the pre-configured bean. Even as many requests invoke `put` and `get` concurrently, **no request mutates serializer or factory configuration**.

`ProductCacheWriter` and `ProductCacheReader` are also standard singleton services. Being a singleton causes no issue as long as a service holds only properly shared dependencies and local per-call variables. Bugs appear when a service stores **mutable per-request state in fields** (such as `currentProductId`) that multiple threads overwrite concurrently.

### 3.1. If You Only Need Strings: Prefer `StringRedisTemplate`

When both keys and values are strings, Spring Boot normally auto-configures `StringRedisTemplate` from the Redis starter and `RedisConnectionFactory`.

~~~java
package com.example.redisexample;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ApiCounterService {
    private final StringRedisTemplate redis;

    public ApiCounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long increment(String apiName) {
        Long count = redis.opsForValue()
                .increment("metrics:api:" + apiName);

        if (count == null) {
            throw new IllegalStateException("Redis counter returned null");
        }

        return count;
    }
}
~~~

`StringRedisTemplate` is likewise shared once configured. There is no need to create new instances just because `increment` may be called by 100 concurrent requests. Redis `INCR` (or equivalent) executed by `increment()` is atomic at the command level.

## 4. Which Objects Must NOT Be Shared Arbitrarily?

Think of the system layout as:

~~~text
Shared singleton:
    RedisTemplate
        |
        +---- RedisConnectionFactory
                    |
                    +---- Connection A (request/transaction context)
                    +---- Connection B (request/transaction context)
                    +---- Shared native connection if driver permits
~~~

The thread-safety of the template **is not unconditionally inherited** by every object obtained from it.

### 4.1. Do Not Store `RedisConnection` in a Service Field

Design to avoid:

~~~java
// Avoid: retaining one RedisConnection for multiple requests to share.
@Service
public class UnsafeRedisService {
    private final RedisConnection connection;

    public UnsafeRedisService(RedisConnectionFactory factory) {
        this.connection = factory.getConnection();
    }

    // Multiple threads may call the same connection
    // without clear borrow/release lifecycle management.
}
~~~

This has several problems:

- `RedisConnection` is not an abstraction recommended for arbitrary sharing across threads.
- A connection can hold session, transaction, or pipeline state.
- There is no timely `close`/return mechanism.
- On server reconnects, a retained connection in a service may violate the lifecycle expected by the template/factory.

Better:

~~~java
@Service
public class SafeRedisService {
    private final StringRedisTemplate redis;

    public SafeRedisService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String load(String id) {
        return redis.opsForValue().get("item:" + id);
    }
}
~~~

When low-level commands are needed, use `RedisTemplate.execute(RedisCallback)` within the callback scope and never let the connection escape the callback:

~~~java
Long result = stringRedisTemplate.execute(connection ->
        connection.serverCommands().dbSize());
~~~

This callback only illustrates checking the database key count via the current `RedisConnection`; never save `connection` into a field, static variable, or queue for another thread to use later.

### 4.2. Do Not Share Mutable Per-Request State

A singleton service with a mutable field:

~~~java
@Service
public class UnsafeKeyService {
    private final StringRedisTemplate redis;
    private String currentKey;

    public UnsafeKeyService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String read(String id) {
        currentKey = "user:" + id;   // Another thread may overwrite this.
        return redis.opsForValue().get(currentKey);
    }
}
~~~

When thread A sets `currentKey=user:A`, thread B can change it to `user:B` before A calls `get`. Thread A may read the wrong user's data. This is a race condition in the **service**, not in the template.

Rewrite using a local variable:

~~~java
public String read(String id) {
    String key = "user:" + id;
    return redis.opsForValue().get(key);
}
~~~

No shared variable is mutated between requests.

### 4.3. Serialized Domain Objects `V` Must Also Be in a Valid State

Suppose two threads share a mutable `ArrayList`, and one thread modifies elements while the other thread serializes an object containing that list. The resulting JSON can capture an inconsistent state or throw an exception.

`RedisTemplate` does not lock Java objects for you. Use immutable DTOs where suitable (`record`s, value objects), take a snapshot before writing, or synchronize access to mutable objects as needed.

### 4.4. `Bound*Operations` Retain Their Bound Key

Spring Data Redis offers APIs like `boundValueOps(key)` and `boundHashOps(key)`. These objects are tied to **one specific key**.

~~~java
var cartOps = stringRedisTemplate.boundHashOps("cart:user-42");
cartOps.put("product-7", "2");
~~~

They are handy for performing multiple operations on one key. However, do not store `cartOps` inside a singleton expecting it to serve every request's cart: the key `cart:user-42` was bound upfront.

In a multi-user service, create bound operations locally with each method's key:

~~~java
public void addToCart(String userId, String productId, String quantity) {
    String key = "cart:" + userId;
    redis.boundHashOps(key).put(productId, quantity);
}
~~~

Whether you use bound operations or not, the rule remains: **per-request keys and business state must be resolved per request**.

## 5. What Does "Keeping Configuration Stable" Cover?

Once a template is in active use, do not arbitrarily re-invoke:

| Setting | Example setter / operation | Why it must stay fixed |
|---|---|---|
| Redis endpoint/factory | `setConnectionFactory(...)` | Switching targets between commands can send data to two different Redis servers |
| Key serializer | `setKeySerializer(...)` | The same logical key can turn into different byte sequences |
| Value serializer | `setValueSerializer(...)` | Newly written data may become unreadable by the old serializer |
| Hash key/value serializer | `setHashKeySerializer(...)`, `setHashValueSerializer(...)` | Hash structures can become incompatible between writers and readers |
| Default serializer | `setDefaultSerializer(...)` | Alters fallback serializer for unconfigured positions |
| Enable default serializer | `setEnableDefaultSerializer(...)` | Changes how null/unset serializers behave |
| Transaction support | `setEnableTransactionSupport(...)` | Alters how connections bind to transactions/threads |
| Other execution/behavior properties | Template/factory attributes | Can concurrently affect active threads |

Never call these setters inside controllers, `@Scheduled` tasks, callbacks, or request-handling methods.

### 5.1. Anti-Pattern: Swapping Serializers Per Request

Suppose an application wants to use two different JSON formats:

~~~java
// Avoid: mutating serializer on a shared singleton template.
public void saveAsDifferentFormat(String key, Object value) {
    sharedTemplate.setValueSerializer(alternateSerializer);
    sharedTemplate.opsForValue().set(key, value);
}
~~~

Thread A sets serializer X, thread B switches it to Y right before A calls `set`. Data is written in an unexpected format. On read, deserialization fails or maps the wrong object.

**Right approach:** declare two independent templates, each with a fixed serializer configuration; or standardize on one unified schema for a given key namespace.

~~~text
Bean A: orderCacheTemplate   -> OrderCache JSON, key order-cache:...
Bean B: metricsTemplate      -> String, key metrics:...
          |
          +-- Both can share the same RedisConnectionFactory
~~~

Having multiple **statically configured** templates is fundamentally different from mutating one shared template at runtime.

### 5.2. Example Declaring Multiple Qualified Templates

~~~java
@Configuration
public class CacheTemplatesConfig {

    @Bean("metricsTemplate")
    public StringRedisTemplate metricsTemplate(
            RedisConnectionFactory factory) {
        return new StringRedisTemplate(factory);
    }

    @Bean("orderCacheTemplate")
    public RedisTemplate<String, OrderCache> orderCacheTemplate(
            RedisConnectionFactory factory,
            ObjectMapper mapper) {

        RedisTemplate<String, OrderCache> template =
                new RedisTemplate<>();
        template.setConnectionFactory(factory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(
                new Jackson2JsonRedisSerializer<>(
                        mapper, OrderCache.class));
        return template;
    }
}
~~~

In this example, `OrderCache` is an application-defined DTO. `metricsTemplate` handles strings, while `orderCacheTemplate` handles `OrderCache` values. Both share the same connection factory while keeping independent serialization contracts.

If the project already has an auto-configured `StringRedisTemplate` from Spring Boot, **avoid inadvertently declaring a duplicate bean for the same role**. This example shows explicitly managing multiple templates; in a real project, check existing beans and use `@Qualifier` when multiple beans share a type.

### 5.3. Serializer Configuration Must Match Across Application Versions

Even if a template is never mutated at runtime, Service A and Service B might run with different configurations for the same key.

For example:

~~~text
Service version 1:
    key: user:42
    value: JDK serialized bytes

Service version 2:
    key: user:42
    value: JSON bytes
~~~

Both templates are "stable" within each JVM, yet the system lacks a unified data contract. During rolling deployments, old instances may fail to read values written by new instances.

Manage serializers, encodings, key names, field schemas, type metadata, TTLs, and migration paths as a **storage contract**. Separate namespaces like `user-cache:v1:42` and `user-cache:v2:42` during transitions or design backward-compatible readers if needed.

## 6. Are Serializers Truly Thread-Safe?

Since a template can be called concurrently, multiple threads can invoke `serialize`/`deserialize` on the same serializer instance simultaneously.

Standard Spring Data Redis serializers are designed for this concurrent usage pattern under their normal usage models. However, a **custom serializer** can break template shareability if it stores temporary state in unprotected instance fields.

Example to avoid:

~~~java
// Illustrates the bug: holding a shared mutable buffer.
class UnsafeExampleSerializer {
    private final StringBuilder scratch = new StringBuilder();

    byte[] serialize(String value) {
        scratch.setLength(0);
        scratch.append(value);
        return scratch.toString().getBytes(
                java.nio.charset.StandardCharsets.UTF_8);
    }
}
~~~

Two threads can interleave `setLength`/`append` calls on the same `scratch`, producing corrupted bytes.

A safer implementation keeps temporary state scoped inside the method:

~~~java
byte[] serialize(String value) {
    return value.getBytes(
            java.nio.charset.StandardCharsets.UTF_8);
}
~~~

In a real serializer, also handle `null`, encoding errors, and the full `RedisSerializer<T>` contract rather than merely converting strings to bytes.

### 6.1. With Jackson `ObjectMapper`

`ObjectMapper` is generally thread-safe for concurrent reads and writes **if all configuration is completed before first use**. Do not register modules, toggle features, register subtypes, or alter default typing on an `ObjectMapper` while concurrently serializing/deserializing with it.

If two JSON policies are needed, create two mappers or serializers and finish configuring both before sharing.

~~~text
Create mapper A -> configure A -> serializer A -> template A -> use
Create mapper B -> configure B -> serializer B -> template B -> use
~~~

Pay special attention to serializers using type metadata: if one service configures a subtype allowlist while another enables different default typing, the same JSON payload may deserialize to a different type or be rejected. That is a **configuration consistency** issue, not just thread safety.

### 6.2. Java DTOs Also Need a Stable Contract

For Redis caches outliving a single deployment, when refactoring DTOs consider:

- Added, removed, or renamed fields.
- Which properties `record`s/constructors require.
- Permitted polymorphic subtypes.
- Number, date/time, enum formats, and null policies.
- Cache lifetimes and ability to read older entries.

Template thread-safety cannot rescue data already stored under an incompatible schema.

## 7. A Singleton Template Does Not Make Multi-Command Sequences Atomic

Suppose two threads increment page views using this pattern:

~~~java
// Avoid: non-atomic read then write.
public void incrementUnsafe(String key) {
    String raw = redis.opsForValue().get(key);
    long current = raw == null ? 0 : Long.parseLong(raw);
    redis.opsForValue().set(key, Long.toString(current + 1));
}
~~~

Execution can interleave like this:

~~~text
Initial: counter = 5

Thread A                      Thread B
--------                      --------
GET -> 5                      GET -> 5
computes 6                    computes 6
SET 6                         SET 6

Final = 6, expected = 7
~~~

Both threads used the template correctly, yet the **business algorithm has a lost update**.

Use Redis's atomic command:

~~~java
public long incrementSafely(String key) {
    Long count = redis.opsForValue().increment(key);
    if (count == null) {
        throw new IllegalStateException("Counter unavailable");
    }
    return count;
}
~~~

Redis `INCR` is atomic at the command level. You do not need `synchronized(redis)` just to let multiple threads increment a counter.

### 7.1. `synchronized` on the Template Is Usually Not the Right Solution

~~~java
synchronized (redis) {
    String old = redis.opsForValue().get(key);
    redis.opsForValue().set(key, transform(old));
}
~~~

A `synchronized` block only serializes threads **within the same JVM** locking on that exact object. It provides zero protection against other application instances, other microservices, or external processes accessing Redis.

Furthermore, locking the whole template slows down unrelated keys. When multi-step atomicity is required, consider atomic commands, Redis transactions, Lua scripts, optimistic locking (`WATCH`), or coordination mechanisms suited to business needs.

### 7.2. Controlling One-Time Key Creation

To set an initial value and TTL only when the key does not exist, use a conditional command:

~~~java
import java.time.Duration;

Boolean created = redis.opsForValue()
        .setIfAbsent("job:lock:42", "owner-abc", Duration.ofSeconds(30));
~~~

`setIfAbsent` with TTL sets the value conditionally with expiration in a single operation when supported by the backend. Still, this is only the building block for a simple lock; safe lock release requires atomically verifying an owner token, handling timeouts/renewals, and guaranteeing business correctness. A thread-safe template does not turn a Redis key into a complete distributed lock on its own.

### 7.3. Write Timeouts and Retry Correctness

When two threads call `increment()`, Redis executes both commands cleanly. Yet if the network drops after Redis executed the command and before the client received the reply, retrying `INCR` can increment twice for **a single business event**.

Distinguish four concepts:

- **Atomicity:** a single Redis command cannot be interleaved mid-execution.
- **Thread safety:** multiple threads can share a template without corrupting the template's internal state.
- **Idempotency:** whether repeating a business request triggers additional side effects.
- **Consistency:** whether read/written data upholds business invariants across multiple keys or systems.

These four concepts are related, not interchangeable.

## 8. Transactions in Spring Data Redis and Thread Boundaries

Redis supports `MULTI`, `EXEC`, and `WATCH` for command grouping and optimistic locking. Spring Data Redis provides `SessionCallback` so related calls share a connection context.

Example grouping two commands in a Redis transaction:

~~~java
import java.util.List;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public List<Object> incrementTwoCounters(StringRedisTemplate redis) {
    return redis.execute(new SessionCallback<List<Object>>() {
        @Override
        @SuppressWarnings({ "rawtypes", "unchecked" })
        public List<Object> execute(RedisOperations operations) {
            operations.multi();
            operations.opsForValue().increment("counter:a");
            operations.opsForValue().increment("counter:b");
            return operations.exec();
        }
    });
}
~~~

In the example above, `SessionCallback` keeps operations in the same Spring Data Redis-managed session; `multi()` starts the Redis transaction and `exec()` runs queued commands. Command results arrive in the list returned after `EXEC`.

**Limits to keep in mind:**

- Redis transactions do not provide relational-database-style rollback; runtime command errors follow Redis rules and do not roll back previously succeeded commands.
- Do not pass `RedisOperations` or a `RedisConnection` in transaction/session state outside the callback for another thread to use.
- A transaction spread across independent connections does not have the semantics of `MULTI/EXEC` on one connection.
- For optimistic locking, `WATCH` must run in the same appropriate session; never assume `WATCH` happens automatically just because you called the template inside a synchronized block.

### 8.1. `setEnableTransactionSupport(true)` Must Be Configured Upfront

Spring Data Redis offers an option to bind Redis connections to Spring-managed transactions when enabled. One way to configure it (at bean creation time):

~~~java
@Bean("transactionalRedisTemplate")
public StringRedisTemplate transactionalRedisTemplate(
        RedisConnectionFactory factory) {

    StringRedisTemplate template = new StringRedisTemplate(factory);
    template.setEnableTransactionSupport(true);
    return template;
}
~~~

This option **must not be toggled per request on a singleton template**. When used with a compatible transaction, Spring binds a connection to the thread and releases it when the transaction ends.

Inside a `@Transactional` flow:

- Some Redis write operations may be queued until the transaction commit phase.
- Read operations may use another connection to read committed data per Redis/Spring Data semantics.
- Holding connections across long transactions can pressure the pool.
- Redis does not automatically become an XA resource that rolls back atomically with a relational database.

If work jumps to another thread (`@Async`, `CompletableFuture`, or an executor), do not assume the thread-bound transaction context transfers automatically to the new thread. Therefore, **a multi-thread-safe singleton template** does not mean **transaction state can be shared across threads**.

### 8.2. Pipelines Are Also Scoped to Callbacks

Pipelining reduces round-trips when sending multiple commands. Spring Data Redis exposes APIs like `executePipelined(...)` and `SessionCallback`.

Pipelining does not provide transaction semantics. Pipelined commands still require reasoning about atomicity, ordering, and parsing replies. Never store a connection in pipeline mode on a singleton and share it across requests.

When pipelining is needed, use the high-level APIs scoping the connection inside a **callback** rather than toggling pipeline mode manually on an uncontrolled shared connection.

## 9. How Do Lettuce and Jedis Affect Sharing a Template?

Spring Data Redis's two primary drivers have different connection characteristics.

| Aspect | Lettuce | Jedis |
|---|---|---|
| Configured `RedisTemplate` | Shareable | Shareable |
| Standard native connection | Can be shared across threads by Lettuce's design under suitable conditions | Must not arbitrarily share one `Jedis` connection across threads |
| Pooling | Depends on workload and dedicated connection needs | Typically required for concurrent requests |
| Transactions/Blocking/Stateful connections | Requires dedicated connections and careful scoping | Requires borrowing/returning connections and preventing session leaks |
| Reactive Spring Data Redis | Supported | Not used as a reactive factory in standard Spring Data Redis integration |

With `LettuceConnectionFactory`, normal operations can leverage a shared native connection, yet Spring Data Redis still wraps it in `RedisConnection` with its own lifecycle rules. Never grab a connection from the factory and hand it directly to multiple threads just because "Lettuce is thread-safe."

With `JedisConnectionFactory`, the template remains a singleton because the factory manages borrowing and returning pooled `Jedis` connections. Never create a new `RedisTemplate` per thread to substitute for pooling.

### 9.1. Distinguishing Template Count, Connection Count, and Request Count

~~~text
200 concurrent requests
        |
        v
1 StringRedisTemplate singleton
        |
        v
1 RedisConnectionFactory
        |
        v
Driver manages 1 or more native connections based on workload
        |
        v
Redis
~~~

There is no formula like "200 requests = 200 RedisTemplates = 200 connections." The right number of native connections depends on the driver, blocking/transactional commands, pool limits, latency, and real workload concurrency.

If Redis slows down or pools exhaust, creating extra singleton templates only increases JVM object counts without fixing the root cause. Measure pool wait times, timeouts, Redis latency, and concurrent command volumes.

### 9.2. When Connections Drop or Redis Restarts

A singleton template does not become permanently broken when a socket drops. Depending on configuration, the driver/factory can reconnect or open fresh connections. Services still must handle failing in-flight requests, timeouts, and retry safety.

Never build a pattern like "Redis timeout -> new RedisTemplate()" per request. That creates unmanaged lifecycles, risks bypassing standardized serializers and timeouts, and can add connection churn against the server.

## 10. ReactiveRedisTemplate and Reactive Flows

`ReactiveRedisTemplate<K,V>` is the abstraction for Reactor `Mono`/`Flux`. It should likewise be configured once and shared as a Spring bean, though it is a distinct API from imperative `RedisTemplate`.

~~~java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCounterService {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveCounterService(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<Long> increment(String apiName) {
        return redis.opsForValue()
                .increment("metrics:api:" + apiName);
    }
}
~~~

Multiple reactive requests can subscribe and execute commands through the same configured template concurrently. Keep clear:

- **Shared template:** safely shared as designed.
- **Publisher:** each subscription has its own execution context and result/error signals.
- **Mutable state in pipelines:** if a lambda mutates a shared collection or variable across subscribers, race conditions still occur.
- **Blocking:** calling synchronous `StringRedisTemplate` directly on a WebFlux event loop can block threads; use the reactive API for non-blocking pipelines.

Never store business state in `ThreadLocal` across reactive pipeline steps, since one logical request can hop across threads. Reactive transactions have their own context mechanisms when supported; do not extrapolate imperative rules directly to reactive code.

## 11. Common Design Mistakes in Multi-Threaded Applications

### 11.1. Creating a Template on Every Request

~~~java
public String readEveryRequest(String key,
                               RedisConnectionFactory factory) {
    RedisTemplate<String, String> template = new RedisTemplate<>();
    template.setConnectionFactory(factory);
    // Easy to miss serializer/lifecycle; repeats setup per request.
    return template.opsForValue().get(key);
}
~~~

This repeats configuration and easily omits initialization and serializers, causing data mismatches. Inject a fully initialized singleton template bean instead.

### 11.2. Changing the Serializer Right Before Writing

~~~java
sharedTemplate.setValueSerializer(serializerForCurrentUser);
sharedTemplate.opsForValue().set(key, value);
~~~

Another thread can swap the serializer mid-execution. User- or tenant-specific formats should never be handled by mutating a singleton template's serializer.

### 11.3. Storing the Current Key in a Singleton Field

~~~java
this.currentKey = "session:" + sessionId;
return redis.opsForValue().get(currentKey);
~~~

A mutable field can be overwritten by another thread. Use a local variable `String key = ...` inside the method.

### 11.4. Saving a Raw Connection in a Static Field

~~~java
static RedisConnection connection;
~~~

The connection may retain transaction/pipeline state, lacks borrow/release lifecycle management, and can break after a Redis restart. Use the template or short-lived callbacks.

### 11.5. Locking on the Template Object as a Transaction

~~~java
synchronized (redisTemplate) {
    // GET -> compute -> SET
}
~~~

This only synchronizes threads locking that object inside one JVM. In multi-instance deployments, cross-instance race conditions remain. Use Redis atomic primitives or suitable transactions/scripts.

### 11.6. Swapping `RedisConnectionFactory` While Running

~~~java
sharedTemplate.setConnectionFactory(newFactory);
~~~

Commands before and after the swap can hit different Redis instances, and in-flight callbacks or transactions may rely on prior assumptions. When changing endpoints/topologies, design an explicit bean/configuration replacement lifecycle, verify data compatibility, and allow the connection factory/driver to shut down cleanly.

### 11.7. Passing a Stateful Reusable `SessionCallback` Concurrently

A `SessionCallback` holding mutable fields across invocations can race if executed concurrently by multiple threads. Callbacks should be stateless or instantiated per call with local state only.

## 12. Proper Design for Multiple Redis Instances or Multiple Tenants

If an application talks to two different Redis servers, keep configurations separate:

~~~text
RedisConnectionFactory A ---- RedisTemplate A ---- product cache
RedisConnectionFactory B ---- RedisTemplate B ---- sessions
~~~

Never keep one template and swap `setConnectionFactory` per tenant or request. Each factory/template pair keeps its own endpoint, security settings, and serializers fixed.

Example method selecting among pre-configured templates:

~~~java
@Service
public class MultiCacheReader {
    private final RedisTemplate<String, String> primary;
    private final RedisTemplate<String, String> secondary;

    public MultiCacheReader(
            @Qualifier("primaryRedisTemplate")
            RedisTemplate<String, String> primary,
            @Qualifier("secondaryRedisTemplate")
            RedisTemplate<String, String> secondary) {
        this.primary = primary;
        this.secondary = secondary;
    }

    public String read(boolean useSecondary, String key) {
        RedisTemplate<String, String> selected =
                useSecondary ? secondary : primary;
        return selected.opsForValue().get(key);
    }
}
~~~

Both `primaryRedisTemplate` and `secondaryRedisTemplate` must be configured upfront with their respective factories. Picking a **stable template reference** per request is fundamentally different from mutating a shared template.

If multiple tenants share one Redis instance separated by key namespaces, building a per-call key prefix is usually sufficient:

~~~java
public String readForTenant(String tenantId, String itemId) {
    String key = "tenant:" + tenantId + ":item:" + itemId;
    return redis.opsForValue().get(key);
}
~~~

However, key prefixes **are not complete security isolation**; enforce tenant identity and access checks in the application layer. If tenants require separate Redis credentials or endpoints, dedicated factories/templates or an explicit per-tenant client manager is more appropriate.

## 13. Changing Configuration While the System Is Running

During operations, you may need to move Redis endpoints, change serializers, update cache formats, or adjust timeouts.

### 13.1. Configuration Changes Differ from Data Changes

Changes fall into distinct categories:

| Change type | Examples | How to handle |
|---|---|---|
| Connection parameters | Host, TLS, auth, timeout | Create new config/client/factory through a controlled lifecycle |
| Topology | Standalone -> Sentinel/Cluster | Use a factory/driver supporting the new topology and verify routing |
| Serializer/schema | JDK -> JSON, DTO changes | Plan migration, versioned keys, and compatible rollouts |
| Key conventions | `cache:user:...` -> `cache:v2:user:...` | Coordinate reads/writes between old and new versions |
| Business logic | Counter logic, TTL, transactions | Update service/command code and account for existing data |

Editing `application.yml` on disk **does not automatically reload** running singleton beans. With default Spring Boot behavior, properties bind at bean initialization. Dynamic reloading requires an explicit lifecycle/refresh mechanism that avoids exposing partially reconfigured templates to active requests.

### 13.2. Two-Version Rollout Pattern

Example upgrading a cache schema:

~~~text
Old version:
    product-cache:v1:<id> -> JSON schema 1

New version:
    product-cache:v2:<id> -> JSON schema 2
~~~

During rollout:

1. Declare the new version's serializer and namespace as a separate configuration.
2. New instances use the fully initialized new template/serializer.
3. Read from the source of truth to populate `v2` caches; let `v1` entries expire via TTL if appropriate.
4. Monitor deserialization errors and cache hit/miss rates.
5. Remove old code/schemas once no readers still depend on them.

This plan is far safer than changing serializers on a shared singleton template across requests. When Redis holds critical data rather than rebuildable caches, use a stronger migration and rollback strategy.

### 13.3. New DTOs/Serializers Must Be Verified Across Multiple Instances

During rolling deployments, multiple service versions coexist. If two versions write incompatible formats to the same key, keeping templates fixed per JVM **is still not enough**. Coordinate storage contract versions across services.

## 14. Observing and Diagnosing Concurrency Issues

When random errors appear under load, do not jump to "`RedisTemplate` is not thread-safe." Pinpoint the exact layer failing:

| Symptom | Common cause | Analysis path |
|---|---|---|
| One request reads another request's key | Singleton service holds mutable `currentKey`/request state | Inspect mutable fields and move state to local variables |
| Intermittent deserialization failures | Runtime serializer mutation, mutable mapper, writer/reader mismatch | Inspect bean initialization, serializer config, and schemas |
| Counter lower than expected | `GET` + `SET` causing lost updates | Use atomic Redis commands or proper concurrency control |
| Periodic latency spikes on Redis requests | Pool exhaustion, Redis latency, connection timeouts | Check active/idle/waiter metrics, timing, and server load |
| Errors during Redis restart | Dropped connections or timed-out commands | Handle reconnects, idempotent retries, and fallbacks |
| Transactions escaping scope | Connection/session/transaction state used on wrong thread | Use `SessionCallback` and matching transaction contexts |
| Cache suddenly changes format | Two service versions running different serializers | Align storage contracts and rollout steps |
| Cross-tenant data mix-ups | Runtime endpoint/factory swaps or wrong key prefixes | Separate beans per endpoint; compute keys locally per request |
| Growing connection counts | Re-creating factories/clients repeatedly instead of reusing managed beans | Check lifecycle and pooling |

### 14.1. What Should You Monitor?

- Redis command execution times and timeout rates.
- Connection counts and pool usage (active, idle, waiting threads) when pooling is enabled.
- Redis server `connected_clients`, CPU, memory, and blocked clients.
- Deserialization error counts and serializer/schema versions on cache reads.
- Long-running transactions/pipelines and connection hold times.
- Retry rates, post-reconnect errors, and overall service request latency.
- Whether cache format errors correlate with new version deployments.

Never log Redis passwords, tokens, personal data, or full payloads just to debug serializer issues.

## 15. Illustrative Concurrency Scenarios

### 15.1. Two Threads Writing Different Keys

~~~text
Thread A: redis.opsForValue().set("a", "1")
Thread B: redis.opsForValue().set("b", "2")
~~~

Sharing one `StringRedisTemplate` singleton is the intended pattern. Each request maintains its own `key` and `value`.

### 15.2. Two Threads Writing the Same Key

~~~text
Thread A: SET settings:feature "ON"
Thread B: SET settings:feature "OFF"
~~~

Sharing the template is still safe. However, **the final value** depends on which command Redis executes last. If overwrites must be prevented, use conditional writes, versioning, `WATCH`/transactions, or scripts depending on the use case.

### 15.3. Two Threads Changing the Serializer

~~~text
Thread A: template.setValueSerializer(JSON_A)
Thread B: template.setValueSerializer(JSON_B)
Thread A: template.opsForValue().set(...)
~~~

This violates the lifecycle contract. Never mutate configuration on a shared template. Split into two statically configured beans.

### 15.4. Two Requests Running Transactions

~~~text
Request A: SessionCallback -> MULTI -> commands -> EXEC
Request B: SessionCallback -> MULTI -> commands -> EXEC
~~~

Both can use the same singleton template. However, A's and B's transaction sessions/connections must be managed separately. Never pass A's connection or `RedisOperations` into B's callback.

### 15.5. Multiple Application Instances Writing to Redis

~~~text
Instance 1 (JVM A) --> template A --\
                                     > Redis
Instance 2 (JVM B) --> template B --/
~~~

Each instance has its own singleton template; **no Java object is shared over the network**. Command atomicity happens on the Redis server, and `synchronized` inside JVM A has no effect on JVM B. Distributed correctness must rely on Redis primitives and proper architecture.

## 16. Frequently Asked Questions

**Do I need `@Scope("prototype")` on `RedisTemplate` so each thread gets its own instance?**

Normally no. A fully configured singleton is the standard approach. Prototype creates extra template objects without solving connection pooling or lost updates.

**Should I call `new RedisTemplate` inside each service method?**

No. Re-creating it repeats configuration, risks skipping lifecycle/serializers, and complicates resource management. Inject a shared bean instead.

**If `RedisTemplate` is thread-safe, is `RedisConnection` also thread-safe?**

Do not assume so. Raw connections carry driver, session, transaction, and pipeline constraints. Use template APIs or properly scoped callbacks.

**Can I declare multiple `RedisTemplate` beans?**

Yes. When you need different serializers, value types, or connection factories, define distinctly named and configured beans. Each bean can be safely shared after initialization.

**Can `opsForValue()` and `opsForHash()` be used concurrently on the same template?**

Yes, provided each key uses its matching Redis data type and serializers. `WRONGTYPE` occurs from operating on a key with the wrong Redis type, not from sharing a template across threads.

**Can I call `setEnableTransactionSupport(true)` right before a method starts?**

No. That is a template-level setting and should be configured at bean creation time. Transaction context is managed per execution without mutating global config per request.

**Why does `INCR` work correctly across concurrent threads while `GET` then `SET` fails?**

`INCR` is a single atomic command executed by Redis. `GET` and `SET` are two separate commands; other threads or processes can interleave between them.

**If Lettuce supports sharing a native connection, do I still need `RedisConnectionFactory`?**

Yes. The factory is Spring Data Redis's integration point for creating/managing connections and handling topology/lifecycle. Direct raw connection management should only be used when you fully understand the requirements and constraints.

**When a service switches Redis endpoints, can I just call `setConnectionFactory` on the running singleton?**

No. Use a controlled bean/configuration replacement workflow, drain in-flight calls cleanly, and verify data on the new endpoint. For Sentinel/Cluster, rely on topology-aware drivers/factories.

## 17. Recommended Pattern in a Spring Data Redis Project

A clean, sustainable structure looks like:

~~~text
Spring ApplicationContext
    |
    +-- RedisConnectionFactory         (bean configured once)
    |
    +-- StringRedisTemplate            (singleton, fixed config)
    |
    +-- RedisTemplate<String, ProductCache>
    |                                  (singleton, fixed JSON serializer)
    |
    +-- ApiCounterService ---------------> StringRedisTemplate
    |
    +-- ProductCacheWriter -------------> ProductCacheTemplate
    |
    +-- ProductCacheReader -------------> ProductCacheTemplate
    |
    +-- Controllers A/B/C / jobs / consumers
                                       (multiple concurrent threads)
~~~

Follow these rules during design:

1. Declare templates as **Spring singleton beans**, configuring connection factories and serializers before use.
2. Inject templates into services via constructor injection; use local variables for keys, arguments, results, and per-request state.
3. Never mutate serializers, factories, transaction flags, or template settings inside runtime flows.
4. Use Redis atomic operations for counters and conditional writes; never confuse template thread-safety with multi-command atomicity.
5. Keep `RedisConnection`, transactions, and pipelines within proper lifecycle/callback scopes; never share connection state across threads.
6. For multiple data formats or multiple Redis instances, create **multiple independently configured templates** with explicit bean qualifiers.
7. Ensure serializers, `ObjectMapper`s, and DTOs are not mutated uncontrollably while concurrent requests read and write.
8. Manage schemas and serializers across application versions so Redis data remains readable during rollouts and after deployments.

**Key takeaway:** `RedisTemplate` and `StringRedisTemplate` are safely shareable across threads **once configuration completes**. That stability relies on keeping template configuration fixed, letting Spring manage connection lifecycles, and keeping request state local. Whenever an endpoint, serializer, or transaction policy needs to change, introduce a dedicated bean configuration with a clean lifecycle instead of mutating a shared singleton under live traffic.
