# Manual Configuration of ConnectionFactory and Template in Spring Data Redis

In a Spring Boot application, adding `spring-boot-starter-data-redis` and configuring `spring.data.redis.*` is often enough for Spring Boot to auto-create connections and beans for working with Redis. However, when you need fine-grained connection control, custom serializers, multiple Redis servers, or a precise understanding of the underlying mechanics, you can **manually declare `RedisConnectionFactory` and `RedisTemplate` using Java Configuration**.

This lesson focuses on **manually initializing and wiring components** in Spring Data Redis: building a factory, configuring the Lettuce client, creating templates for strings and objects, injecting beans into services, inspecting Redis data, and handling common configuration errors. The main examples use Java 17+, Spring Boot 3.x, and Spring Data Redis 3.x; when using other versions, verify the corresponding APIs and configuration properties.

## 1. Learning Objectives

After completing this lesson, you will be able to:

1. Explain the roles of `RedisConnectionFactory`, `LettuceConnectionFactory`, `RedisConnection`, `RedisTemplate`, and `StringRedisTemplate`.
2. Manually initialize a `LettuceConnectionFactory` for standalone Redis with host, port, database, credentials, command timeout, and TLS.
3. Create a `RedisTemplate<String, ProductSnapshot>` with explicitly configured key and value serializers.
4. Create a `StringRedisTemplate` for string operations, counters, and TTLs.
5. Inject the right template into services via constructor injection and `@Qualifier` when multiple matching beans exist.
6. Distinguish Spring Boot auto-configured beans from manually declared beans and understand the consequences of overriding.
7. Verify connections and Redis data, and recognize common issues caused by wrong addresses, authentication, database index, or serialization.

**Prerequisites:** familiarity with core Java, `@Configuration`, `@Bean`, Dependency Injection, and running a Spring Boot application; basic understanding of Redis key-value storage and data types such as String/Hash/List/Set.

## 2. Connection Architecture: What Each Component Does

Typical operation flow:

~~~text
ProductService
    |
    | inject @Qualifier("productRedisTemplate")
    v
RedisTemplate<String, ProductSnapshot>
    |        |
    |        +-- Key serializer: StringRedisSerializer
    |        +-- Value serializer: Jackson2JsonRedisSerializer<ProductSnapshot>
    |
    v
RedisConnectionFactory (application-declared bean)
    |
    v
LettuceConnectionFactory
    |
    v
Lettuce client  --->  Redis Server
~~~

| Component | Responsibility | Notes |
| --- | --- | --- |
| `RedisConnectionFactory` | Abstraction creating/supplying `RedisConnection` to execute Redis commands | Interface; used by templates and other Spring Data Redis components |
| `LettuceConnectionFactory` | Implementation backed by the Lettuce client | Supports standalone, Sentinel, Cluster, and client options |
| `RedisConnection` | Low-level connection abstraction exposing Redis operations | Usually not managed manually inside business services |
| `RedisTemplate<K, V>` | High-level synchronous API for Redis operations and data serialization | Must configure serializers for key, value, hash key, and hash value |
| `StringRedisTemplate` | Specialized RedisTemplate for String keys and values | Ideal for `GET`, `SET`, `INCR`, and CLI-readable string data |
| `RedisSerializer<T>` | Converts between Java objects and Redis bytes | Applications sharing keys must agree on the format |

**Redis Server** is the process that stores and processes data; **Lettuce** is the network client library; **Spring Data Redis** is the integration and abstraction layer for Spring applications. Creating a `RedisConnectionFactory` does not start Redis Server: the server must run independently at a hostname/port reachable by the application.

Normally, services use templates rather than calling `factory.getConnection()` and holding a `RedisConnection` across requests. Templates manage acquiring and releasing connections via the factory; properly configured template objects can be shared safely across beans.

## 3. When Should You Configure Manually?

For most Spring Boot projects, auto-configuration is sufficient:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
~~~

Spring Boot detects the starter and creates `RedisConnectionFactory` along with default templates if no conflicting beans exist. Manual declaration is useful when:

- You need direct control over Lettuce initialization or a topology configuration outside default settings.
- You want to isolate a module's Redis settings under a custom prefix such as `app.redis.*`.
- You must use explicit serializers per data type instead of default serialization.
- You connect to multiple distinct Redis instances: cache, sessions, short-lived metrics, or legacy systems.
- You need deliberate configuration of TLS, ACLs, command timeouts, or client options.
- You want strict control over bean names and factory-to-template relationships in a large application.

You do not need manual configuration just to perform `GET`/`SET`. If a project only needs one Redis connection with standard settings, auto-configuration is usually shorter and easier to maintain.

## 4. Preparing the Project and Local Redis

### 4.1. Maven Dependencies

In a Spring Boot application with an appropriate BOM/dependency management setup, add:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

This is the dependency snippet, not a complete `pom.xml`. `spring-boot-starter-data-redis` normally brings Lettuce as the default Redis client. `spring-boot-starter-web` provides REST/JSON support for examples along with common Jackson dependencies. You can use the Gradle equivalent:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

If you want to use a Jackson JSON serializer without the web starter, ensure compatible Jackson libraries are on the classpath.

### 4.2. Running Redis with Docker

Example for a personal development machine:

~~~bash
docker run --name manual-redis -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it manual-redis redis-cli PING
~~~

If Redis is running, `PING` returns `PONG`. If another Redis instance already occupies port 6379, change the host port, e.g., `-p 127.0.0.1:6380:6379`, and set `app.redis.port: 6380`.

The command above starts a passwordless local Redis bound only to the host loopback interface. When connecting to Redis in non-local environments, apply proper network controls, authentication, and encryption. In Docker Compose, a Spring Boot container normally connects using **the Redis container's service name**; `localhost` inside an app container does not point to another Redis container.

## 5. Complete Example: Manually Declaring ConnectionFactory and Two Templates

We will connect to standalone Redis at `localhost:6379`. The configuration uses the `app.redis` namespace to clearly show the application handles these properties itself rather than relying on Spring Boot auto-configuration.

### 5.1. Declaring `application.yml`

~~~yaml
app:
  redis:
    host: ${APP_REDIS_HOST:localhost}
    port: ${APP_REDIS_PORT:6379}
    database: ${APP_REDIS_DATABASE:0}
    username: ${APP_REDIS_USERNAME:}
    password: ${APP_REDIS_PASSWORD:}
    command-timeout-ms: ${APP_REDIS_TIMEOUT_MS:2000}
    ssl: ${APP_REDIS_SSL:false}
~~~

- Local Redis in this example has authentication disabled, so `username`/`password` are empty.
- When using ACLs or a password, inject values via environment variables; never commit production passwords into source code or checked-in files.
- `database: 0` is the standard logical database in standalone Redis. Redis Cluster manages keys differently and does not support selecting multiple logical databases like standalone.
- `command-timeout-ms` is the client-side wait limit per command; choose it based on SLAs, network latency, and application error policies.
- `ssl: true` works only if the Redis endpoint actually serves TLS and the client trusts its certificate. Enabling TLS on the client against a plaintext server causes connection errors.

### 5.2. Declaring the Model Stored in Redis

Create `ProductSnapshot.java`:

~~~java
package com.example.redis;

import java.math.BigDecimal;

public record ProductSnapshot(
        String productId,
        String name,
        BigDecimal price
) {
}
~~~

This is a sample object for caching/temporarily storing product data. This lesson uses a Java record for illustration. When persisting real objects, consider data types, schema versioning, constructors/setters, and backward compatibility across application upgrades.

### 5.3. Manually Creating the `RedisConnectionFactory` Bean

Create `ManualRedisConfig.java`:

~~~java
package com.example.redis;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.Jackson2JsonRedisSerializer;
import org.springframework.data.redis.serializer.StringRedisSerializer;

@Configuration(proxyBeanMethods = false)
public class ManualRedisConfig {

    @Bean
    public RedisConnectionFactory redisConnectionFactory(
            @Value("${app.redis.host:localhost}") String host,
            @Value("${app.redis.port:6379}") int port,
            @Value("${app.redis.database:0}") int database,
            @Value("${app.redis.username:}") String username,
            @Value("${app.redis.password:}") String password,
            @Value("${app.redis.command-timeout-ms:2000}") long timeoutMs,
            @Value("${app.redis.ssl:false}") boolean ssl) {

        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration(host, port);
        server.setDatabase(database);

        if (!username.isBlank()) {
            server.setUsername(username);
        }
        if (!password.isBlank()) {
            server.setPassword(RedisPassword.of(password));
        }

        var clientBuilder = LettuceClientConfiguration.builder();
        clientBuilder.commandTimeout(Duration.ofMillis(timeoutMs));
        if (ssl) {
            clientBuilder.useSsl();
        }

        return new LettuceConnectionFactory(server, clientBuilder.build());
    }

    @Bean("productRedisTemplate")
    public RedisTemplate<String, ProductSnapshot> productRedisTemplate(
            RedisConnectionFactory redisConnectionFactory) {

        RedisTemplate<String, ProductSnapshot> template =
                new RedisTemplate<>();

        template.setConnectionFactory(redisConnectionFactory);

        StringRedisSerializer stringSerializer =
                new StringRedisSerializer();
        Jackson2JsonRedisSerializer<ProductSnapshot> jsonSerializer =
                new Jackson2JsonRedisSerializer<>(ProductSnapshot.class);

        template.setKeySerializer(stringSerializer);
        template.setHashKeySerializer(stringSerializer);
        template.setValueSerializer(jsonSerializer);
        template.setHashValueSerializer(jsonSerializer);

        return template;
    }

    @Bean
    public StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory redisConnectionFactory) {
        return new StringRedisTemplate(redisConnectionFactory);
    }
}
~~~

**Explanation in bean creation order:**

1. Spring reads `app.redis.*` values and invokes `redisConnectionFactory(...)` to build `RedisStandaloneConfiguration`.
2. `RedisStandaloneConfiguration` holds the Redis server address and credentials; `LettuceClientConfiguration` holds client-side settings, here the command timeout and optional TLS.
3. `new LettuceConnectionFactory(server, clientBuilder.build())` creates the Lettuce-backed implementation of `RedisConnectionFactory`.
4. Spring injects this factory into `productRedisTemplate(...)`. The template is configured with serializers and managed as a Spring bean.
5. The same factory is injected into `stringRedisTemplate(...)`; both templates share connection settings while performing different serialization.

This is a **complete manual configuration for standalone Redis**. The factory should not be instantiated per incoming request. Spring manages the factory and templates as singletons by default and releases resources when the application context shuts down.

In this example, `@Bean("productRedisTemplate")` avoids ambiguity when the application has multiple `RedisTemplate` beans. `StringRedisTemplate` is specialized for string data, making `INCR` calls and reading values via Redis CLI straightforward.

### 5.4. Using the Templates in Services

Create `ProductSnapshotService.java`:

~~~java
package com.example.redis;

import java.time.Duration;
import java.util.Optional;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductSnapshotService {
    private final RedisTemplate<String, ProductSnapshot> redis;

    public ProductSnapshotService(
            @Qualifier("productRedisTemplate")
            RedisTemplate<String, ProductSnapshot> redis) {
        this.redis = redis;
    }

    public void save(ProductSnapshot product, Duration ttl) {
        if (product == null || product.productId() == null
                || product.productId().isBlank()) {
            throw new IllegalArgumentException("Invalid product");
        }
        if (ttl == null || ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        redis.opsForValue().set(key(product.productId()), product, ttl);
    }

    public Optional<ProductSnapshot> find(String productId) {
        return Optional.ofNullable(redis.opsForValue().get(key(productId)));
    }

    public boolean remove(String productId) {
        return Boolean.TRUE.equals(redis.delete(key(productId)));
    }

    private String key(String productId) {
        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException("Invalid product ID");
        }
        return "demo:product:snapshot:" + productId;
    }
}
~~~

When calling:

~~~java
ProductSnapshot example =
        new ProductSnapshot("42", "Keyboard", new BigDecimal("590000"));

productSnapshotService.save(example, Duration.ofMinutes(10));
Optional<ProductSnapshot> stored =
        productSnapshotService.find("42");
boolean deleted = productSnapshotService.remove("42");
~~~

the corresponding key is `demo:product:snapshot:42`. The value is converted by the serializer from `ProductSnapshot` into JSON bytes. A `SET` with TTL expires the key automatically after the given duration; `GET` on a missing key returns `null` at the template level, converted here to `Optional.empty()`. `delete()` returns a nullable `Boolean`, so the example checks `Boolean.TRUE.equals(...)`.

The service invocation snippet above illustrates usage inside an existing method; to run it, place it inside a controller, runner, or test with the `ProductSnapshotService` bean injected.

### 5.5. Using `StringRedisTemplate` for Counters

Create `ViewCounterService.java`:

~~~java
package com.example.redis;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ViewCounterService {
    private final StringRedisTemplate redis;

    public ViewCounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long increase(String productId) {
        if (productId == null || productId.isBlank()) {
            throw new IllegalArgumentException("Invalid product ID");
        }

        String key = "demo:product:views:" + productId;
        Long count = redis.opsForValue().increment(key);
        if (count == null) {
            throw new IllegalStateException("Missing Redis increment result");
        }
        return count;
    }
}
~~~

`increment(...)` maps to an atomic increment via Redis `INCR`. Redis Server executes the increment itself; the service does not need to `GET`, add 1 in Java, and `SET` back. Counts requiring durability still need persistence/backup strategies or periodic flushing to a primary store. A template does not guarantee data survives forever if Redis fails.

If you want to set a TTL on the counter, you can call `redis.expire(key, Duration.ofHours(1))`, though two separate `increment` and `expire` calls are not atomic together. For strict expiration windows or race-condition safety, design an appropriate command, transaction, or script.

## 6. Serializers: The Most Important Part of Manual `RedisTemplate` Setup

Redis stores keys and values as bytes. Declaring `RedisTemplate<String, ProductSnapshot>` only informs the compiler about Java types; **it does not determine a Redis format suited to your data**. The actual serializers govern the bytes written and read.

### 6.1. Four Serializers Typically Configured

| Property on RedisTemplate | Data Covered | Choice in Example |
| --- | --- | --- |
| `keySerializer` | Keys for `GET`, `SET`, `DEL`, etc. | `StringRedisSerializer` |
| `valueSerializer` | Values in key-value operations | `Jackson2JsonRedisSerializer<ProductSnapshot>` |
| `hashKeySerializer` | Fields of a Redis Hash | `StringRedisSerializer` |
| `hashValueSerializer` | Values of a Redis Hash field | JSON serializer for `ProductSnapshot` |

In practice, the data type of **values inside a Hash** may differ from values in `opsForValue()`. If a Redis Hash stores scalars like `name = "ABC"`, `price = "100"`, you may want `StringRedisSerializer` for `hashValueSerializer` or a separate template. Do not reuse a single template for every schema and expect serializers to guess formats.

### 6.2. Common Choices

**StringRedisSerializer**

- Converts Java strings to byte arrays using a consistent character encoding.
- Suitable for keys, Redis Strings, and text Hash fields.
- Makes values easy for operators to inspect with `redis-cli GET` or `HGETALL`.

**Jackson2JsonRedisSerializer<T>**

- JSON serializer bound to a specific target type, such as `ProductSnapshot.class`.
- Easy to inspect via CLI; allows intentional evolution of JSON schemas.
- Requires that stored data in the key actually matches type `T` when read back.
- When upgrading models, plan compatibility for added/removed fields, nulls, and versioning.

**GenericJackson2JsonRedisSerializer**

- Useful when one template must store multiple object types, typically embedding type metadata to reconstruct objects.
- Requires strict control over data sources, typing configuration, and allowed deserializable types; never treat JSON with type metadata as safe to deserialize from untrusted sources.
- Creates coupling to Java class names, making migrations harder than single-type templates.

**JdkSerializationRedisSerializer**

- A binary Java serialization option used by `RedisTemplate` in some default setups.
- Hard to read in CLI, sensitive to Java/class compatibility, and poses deserialization risks on untrusted data.
- Avoid using it casually for data shared across languages or expected to remain stable across deployments.

If you do not explicitly set serializers on a new `RedisTemplate`, do not assume keys will look like the strings you passed in. Default `RedisTemplate` configuration can produce binary keys/values via JDK serialization, causing `redis-cli GET demo:...` to miss keys because the key bytes differ.

### 6.3. Why Never Share the Same Key Across Two Templates with Different Serializers?

Suppose:

~~~text
StringRedisTemplate:
  key = "demo:product:snapshot:42"
  value = "hello"

RedisTemplate<String, ProductSnapshot>:
  key = "demo:product:snapshot:42"
  value = JSON of ProductSnapshot
~~~

Both operations will **overwrite the same Redis key** if both use string key serializers. After writing `hello` via `StringRedisTemplate`, reading it back with a template expecting `ProductSnapshot` can fail deserialization. Therefore:

1. Define a **namespace/prefix** per data category.
2. Let only one flow/format own a key, or document a clear data contract across applications.
3. When changing serializers, plan key prefix updates, controlled cache eviction, or data migration.
4. If multiple applications read Redis, agree on charset, JSON schema, value type, and lifetime upfront.

Modules like Spring Cache or Spring Session maintain their own key namespaces and serializers; manually configuring a template does not automatically switch those modules to your template's JSON format.

## 7. Verifying `RedisConnectionFactory` and Templates After Configuration

### 7.1. Confirming Redis Server

~~~bash
docker exec -it manual-redis redis-cli PING
~~~

Expect `PONG`. If not, inspect the container, port mapping, Docker network, and Redis logs before investigating Java.

### 7.2. Inspecting Created Keys

After the service calls `save(...)` or `increase(...)`:

~~~bash
docker exec -it manual-redis redis-cli
~~~

Run these commands:

~~~redis
GET demo:product:snapshot:42
TTL demo:product:snapshot:42
TYPE demo:product:snapshot:42
GET demo:product:views:42
SCAN 0 MATCH demo:* COUNT 100
~~~

You should see the snapshot key holding JSON for `ProductSnapshot` with `TYPE` equal to `string`, and a decreasing TTL. The counter key holds numeric digits that increment on each call. `SCAN` returns a cursor; to traverse the full keyspace, pass the returned cursor repeatedly until it returns `0`.

If `GET` misses the key, verify hostname, port, logical database, prefix, and TTL; Redis CLI targets database `0` by default. In standalone mode, if the application uses a different database, run `SELECT <db>` in the CLI. Redis Cluster does not support this multi-database model.

### 7.3. Testing via Application-Level Java Code

You can create a `CommandLineRunner` for development:

~~~java
@Bean
CommandLineRunner redisDemo(
        ProductSnapshotService productService,
        ViewCounterService counterService) {

    return args -> {
        var product =
                new ProductSnapshot("42", "Keyboard", new BigDecimal("590000"));
        productService.save(product, Duration.ofMinutes(10));

        System.out.println(productService.find("42"));
        System.out.println(counterService.increase("42"));
    };
}
~~~

Place this inside the example `@Configuration` class and add imports for `CommandLineRunner`, `BigDecimal`, and `Duration`; use this runner only in learning environments. In production applications, never write demo data or log business objects on every startup.

### 7.4. Lifecycle and Connections

- `LettuceConnectionFactory` is a Spring bean initialized and shut down along with the application context.
- Templates borrow connections from the factory to run commands; applications normally do not open/close connections per method call.
- Redis connections may be opened lazily when commands run. **Successful application startup does not guarantee all subsequent Redis commands will succeed**; verify with a real operation or health check.
- In production deployments, configure timeouts, logging/metrics, error handling, and fallback behavior for Redis outages.

## 8. How Do Manually Declared Beans Interact with Spring Boot Auto-Configuration?

Spring Boot creates certain default Redis beans **only when no matching bean already exists**. Practical rules to note:

1. When you declare your own `RedisConnectionFactory`, standard connection auto-configuration uses your factory instead of creating a second default one.
2. Spring Boot may still create a default `redisTemplate` bean if no bean with that **name** exists. Our example bean `productRedisTemplate` uses a distinct name, so both templates can coexist.
3. Spring Boot normally creates `StringRedisTemplate` when no bean of that type exists. In our example, we define `stringRedisTemplate` manually, so that auto-configuration step backs off.
4. When injecting `RedisTemplate<String, ProductSnapshot>`, explicitly specify `@Qualifier("productRedisTemplate")`, especially when other `RedisTemplate` beans exist.
5. If multiple `RedisConnectionFactory` beans exist, resolve every injection point (templates, cache, session, etc.) clearly via `@Qualifier` or an intentional `@Primary` bean.

**Important note:** `@Primary` designates a preferred candidate when dependency injection encounters multiple beans of the same type; it does not replace clear bean naming, configure serializers, or ensure other modules target the right Redis instance.

If a project currently uses an auto-configured `redisTemplate` and you need to replace it with your own, name the bean `redisTemplate` so Spring Boot skips creating its default; then verify generic types and all callers relying on the default bean. Avoid altering shared beans in a large project without checking every consumer.

## 9. Manual Configuration by Redis Topology Type

The example in Section 5 uses `RedisStandaloneConfiguration`. In real infrastructure, a factory can also be built with Sentinel or Cluster configurations. This section shows that **the change occurs in the server configuration passed to the factory**; templates can remain unchanged if the data contract stays the same.

### 9.1. Standalone

~~~java
RedisStandaloneConfiguration standalone =
        new RedisStandaloneConfiguration("redis.example.internal", 6379);
standalone.setDatabase(0);

RedisConnectionFactory factory =
        new LettuceConnectionFactory(standalone);
~~~

There is only a single Redis endpoint. Account for connectivity, security, availability, and recovery when the server fails. For endpoints outside trusted networks, configure authentication and TLS rather than using the minimal snippet above.

### 9.2. Sentinel

Redis Sentinel monitors the master and handles master discovery/failover in a replication setup. Instead of pointing the app directly at a fixed master, the client knows the Sentinel list and managed master name.

~~~java
RedisSentinelConfiguration sentinel =
        new RedisSentinelConfiguration()
                .master("mymaster")
                .sentinel("sentinel-1.internal", 26379)
                .sentinel("sentinel-2.internal", 26379)
                .sentinel("sentinel-3.internal", 26379);

RedisConnectionFactory factory =
        new LettuceConnectionFactory(sentinel);
~~~

Import `RedisSentinelConfiguration` from `org.springframework.data.redis.connection`. Add credentials for Redis data nodes and Sentinel nodes if required by your infrastructure; do not assume credentials for both roles are identical. Sentinel failover does not eliminate the need for timeouts, error handling, or bounded retries in the application.

### 9.3. Cluster

Redis Cluster distributes keys across multiple nodes by hash slot. Example creating a factory from seed nodes:

~~~java
RedisClusterConfiguration cluster =
        new RedisClusterConfiguration(
                List.of("redis-1.internal:6379",
                        "redis-2.internal:6379",
                        "redis-3.internal:6379"));

RedisConnectionFactory factory =
        new LettuceConnectionFactory(cluster);
~~~

Import `RedisClusterConfiguration` from `org.springframework.data.redis.connection` and `List` from `java.util`. The node list acts as initial seed endpoints; the client discovers the cluster topology from them. Some multi-key commands are constrained by hash slots; Redis Cluster does not support `SELECT` across databases as standalone does. In production, also configure TLS/ACLs, advertised hostname resolution, sensible retries/timeouts, and failover testing.

**Never combine all three configurations for a single factory.** Match the topology to your Redis deployment. A standalone Redis running in Docker does not become Sentinel or Cluster simply by changing a Java constructor.

## 10. Multiple `RedisConnectionFactory` and Multiple Template Beans in One Application

A project might use separate Redis instances for distinct purposes, such as short-lived caching and event metrics. In that case, clearly bind each bean to its target endpoint.

~~~java
@Bean("cacheRedisConnectionFactory")
RedisConnectionFactory cacheRedisConnectionFactory() {
    return new LettuceConnectionFactory(
            new RedisStandaloneConfiguration("cache-redis.internal", 6379));
}

@Bean("metricsRedisConnectionFactory")
RedisConnectionFactory metricsRedisConnectionFactory() {
    return new LettuceConnectionFactory(
            new RedisStandaloneConfiguration("metrics-redis.internal", 6379));
}

@Bean("metricsRedisTemplate")
StringRedisTemplate metricsRedisTemplate(
        @Qualifier("metricsRedisConnectionFactory")
        RedisConnectionFactory factory) {
    return new StringRedisTemplate(factory);
}
~~~

This snippet focuses only on wiring; hostnames are illustrative and omit authentication/TLS. When placing two factories in the same context, **attach `@Qualifier` to every dependent bean** or deliberately designate a default factory with `@Primary`. Do not let Spring Boot accidentally wire cache Redis into Spring Session, Redis `CacheManager`, or other components.

If different Redis instances hold different value formats, name templates to reflect both purpose and data type; never reuse a single `RedisTemplate<Object, Object>` across unrelated Redis servers.

## 11. Distinguishing `RedisTemplate`, Spring Cache, and Redis Repository

When getting started with Spring Data Redis, three approaches are often confused:

| Tool | When to Use | Related Configuration |
| --- | --- | --- |
| `RedisTemplate` | Need explicit Redis commands: `SET`, `GET`, `HSET`, `INCR`, TTL, etc. | `RedisConnectionFactory` and four serializer settings |
| `StringRedisTemplate` | String keys/values, counters, CLI-friendly data | Factory and preconfigured string serializers |
| Spring Cache with Redis backend | Cache method results via `@Cacheable`, `@CacheEvict` | `CacheManager`, `RedisCacheConfiguration`, dedicated cache key/value serializers |
| Redis Repository | Persist entities via repositories, `@RedisHash`, `@Id` | Repository mapping configuration and underlying Redis operations |

**Declaring a `RedisTemplate<String, ProductSnapshot>` does not make Spring Cache automatically adopt that template's JSON serializer.** `RedisCacheManager` manages its own cache serializers and key prefixes; if the application uses cache annotations, configure the cache layer properly.

Example illustrating Spring Cache independently from `RedisTemplate`:

~~~java
@Configuration
@EnableCaching
public class CacheConfig {

    @Bean
    RedisCacheManager cacheManager(RedisConnectionFactory factory) {
        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(5))
                        .disableCachingNullValues();

        return RedisCacheManager.builder(factory)
                .cacheDefaults(defaults)
                .build();
    }
}
~~~

This snippet requires imports for `RedisCacheManager`, `RedisCacheConfiguration`, `Duration`, `@Bean`, `@Configuration`, and `@EnableCaching`, plus `spring-boot-starter-cache` if using Spring Cache. It only illustrates the relationship between the factory and the cache manager; evaluate `CacheManager`'s default serializers separately against your schema and usage patterns.

## 12. Timeouts, Transactions, Performance, and Connection Management

### 12.1. Timeouts Are Necessary but Do Not Replace Error Handling

`commandTimeout(Duration.ofMillis(...))` caps how long Lettuce waits for a Redis operation. On timeout, the application must still decide what to do:

- For **rebuildable caches**, consider reading from the primary source and repopulating later, while protecting the primary store from overload if Redis stays down.
- For **critical business counters or state**, never silently ignore errors when accuracy or durability matters.
- If a command was transmitted before the client timed out waiting for a reply, be cautious about retrying **non-idempotent** operations like `INCR`: retrying can double-increment.

A timeout is a wait boundary, not a guarantee about whether Redis executed the command or not.

### 12.2. Is a Connection Pool Needed?

Lettuce supports sharing a native connection across many regular operations. Not every project needs a dedicated pool. Pooling can fit specialized connection patterns or measured bottlenecks; oversized pools do not automatically increase throughput. When enabling pooling, monitor active connections, borrow wait times, timeouts, and Redis server resources.

### 12.3. Should You Call `setEnableTransactionSupport(true)`?

`RedisTemplate#setEnableTransactionSupport(true)` binds Redis operations to Spring-managed transactions in appropriate scenarios. **It does not turn Redis and a relational database into an atomic distributed transaction**; `MULTI/EXEC`, Spring transactions, and database transactions operate under different scopes.

Enable it only when you have designed transaction semantics carefully and tested effects on reads/writes, connections, and commit ordering. For standard `GET`/`SET`/`INCR` examples in this lesson, leave it disabled.

### 12.4. TTL and Key Naming

Templates allow:

~~~java
redis.opsForValue().set("demo:product:snapshot:42",
        product, Duration.ofMinutes(10));

Boolean updated =
        redis.expire("demo:product:snapshot:42", Duration.ofMinutes(30));

Boolean existed =
        redis.hasKey("demo:product:snapshot:42");
~~~

This snippet assumes a variable `redis` of type `RedisTemplate<String, ProductSnapshot>` and `product` of type `ProductSnapshot`. `expire` and `hasKey` can return nullable `Boolean` values in the API, so check them safely in conditionals.

Key conventions should include the application/feature name and a clear identifier, such as `shop:product:snapshot:42`. When multi-tenancy or access boundaries apply, include enough context in the key to prevent cross-leakage. Never embed tokens, passwords, or unnecessary PII into key names.

## 13. Common Errors in Manual Configuration

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| `RedisConnectionFailureException` or Connection refused | Wrong host/port, Redis stopped, firewall, Docker network | `redis-cli PING`, check port and hostname from the app's runtime environment |
| Authentication failed / NOAUTH | Wrong ACL username/password or Redis requires auth | Check permissions, environment variables, password policy |
| TLS handshake failed | TLS enabled on client but not server; untrusted cert; wrong endpoint | Check TLS endpoint, CA, and client/server settings |
| Command timeout | Slow/unresponsive Redis, network failure, too-short timeout | Inspect latency metrics, logs, Redis load, network, and deadlines |
| `NoSuchBeanDefinitionException` | Missing bean or configuration outside component scan | Check `@Configuration` package and injected types/qualifiers |
| `NoUniqueBeanDefinitionException` | Multiple matching factories or templates | Use `@Qualifier`, bean names, or intentional `@Primary` |
| Reading `null` even though data exists | Different DB, key prefix, key serializer, or expired TTL | Compare key bytes, `SELECT`, `TTL`, and factory settings |
| Unreadable binary values in CLI | Binary serializer, possibly JDK serializer | Check the template's actual `keySerializer`/`valueSerializer` |
| JSON deserialization error | Value written by another serializer or model schema changed | Verify format contract, key versioning, and migration plan |
| `WRONGTYPE Operation against a key...` | Existing key holds a different Redis data type | Run `TYPE <key>`, isolate namespaces, clean test data carefully |
| `MOVED` or hash slot errors | Using Cluster with mismatched client/topology/cross-slot keys | Check Cluster configuration, seed nodes, and multi-key commands |
| Cache annotations ignore custom template | `CacheManager` uses its own serializers and config | Check `CacheManager`/`RedisCacheConfiguration` beans |

**A subtle bug:** writing with a `StringRedisSerializer` key template and reading with another `RedisTemplate` using JDK serialization. In Java both look like the same String key, yet the bytes sent to Redis differ, producing a cache miss. Always verify serializers before concluding Redis dropped data.

### Troubleshooting Isolation Checklist

1. **Check server:** is Redis running, responding to `PING`, and at the expected address?
2. **Check credentials and TLS:** does the endpoint require AUTH, ACLs, certificates, or a separate TLS port?
3. **Check beans:** which exact factory and template beans is Spring injecting?
4. **Check keys:** are operations hitting the same logical database, namespace, and key serializer?
5. **Check values:** do write and read serializers match, and is the JSON schema compatible?
6. **Check lifecycle:** did the TTL expire, or did another service delete or overwrite the key?
7. **Check real load:** do timeouts correlate with CPU, memory, network, or client connection counts?

Never use `KEYS *` to scan all keys on a busy Redis server; use cursor-based `SCAN` or proper metrics. Never run `FLUSHDB`/`FLUSHALL` on an environment holding real data to "fix" configuration mistakes.

## 14. Better Configuration Design for Larger Projects

Section 5 uses `@Value` directly to keep focus on factory construction. As parameter counts grow, group them into a `@ConfigurationProperties(prefix = "app.redis")` class with validation, documentation, and per-environment profiles.

Suggested structure:

~~~text
com.example.redis
  ├── RedisClientProperties.java   # host, port, username, TLS, timeout...
  ├── ManualRedisConfig.java       # factory, named templates
  ├── ProductSnapshot.java         # model stored in Redis
  ├── ProductSnapshotService.java  # business operations
  └── ViewCounterService.java      # StringRedisTemplate
~~~

Keep connection setup separate from business logic so changing hosts or passwords does not require editing services. When adding a new value type with an independent schema, create another named template sharing the same factory.

Practical guidelines:

- **Configure by environment:** local may use passwordless standalone bound to loopback; staging/production use proper endpoints, ACLs/TLS, and secrets.
- **Name beans clearly:** `productRedisTemplate`, `sessionRedisTemplate`, `metricsRedisTemplate` when separating data types is genuinely needed.
- **Specify serializers explicitly:** keys and hash keys are typically String; values need a consistent, versioned schema when necessary.
- **Use a factory matched to the topology:** do not assume standalone code works unchanged for Cluster or Sentinel.
- **Manage timeouts/retries:** account for command idempotency and behavior during Redis outages.
- **Manage keys and TTLs:** temporary data needs TTLs; critical data needs explicit persistence guarantees.
- **Monitor connections and memory:** validate initial settings against real metrics and load.

## 15. Comprehensive Hands-On Exercise

**Goal:** Manually configure a Spring Boot application connected to local Redis, store a product snapshot as JSON, increment a view counter via `StringRedisTemplate`, and verify that both datasets can be read independently.

Steps:

1. Start local Redis via Docker and confirm `PING` returns `PONG`.
2. Add the Spring Data Redis dependency and configure `app.redis.*`.
3. Write `ManualRedisConfig` with `redisConnectionFactory`, `productRedisTemplate`, and `stringRedisTemplate`.
4. Create `ProductSnapshot` and inject `productRedisTemplate` into a service using `@Qualifier`.
5. Save product ID 42 with a 10-minute TTL, read it back, and test deleting it.
6. Increment views for product ID 42 three times, confirming `demo:product:views:42` holds increasing numeric values.
7. Use the CLI to check `GET`, `TTL`, and `TYPE` for each key; confirm the snapshot is JSON and the counter is a numeric string.
8. Try changing the key prefix or database index in a test environment and explain why old keys are no longer visible.
9. Try pointing to an invalid port to observe the exception type, then restore valid settings and rerun.
10. Summarize in your own words the roles of the factory, template, serializer, service, and Redis Server.

### Expected Results

- The Spring context creates the manual beans and the service injects the right template.
- Object read/write operations use an explicit JSON serializer; keys appear with readable names.
- Counter increments work via `StringRedisTemplate` without adding in Java code.
- Host/port/credentials/timeout can be changed per environment without touching business services.
- Connectivity failures can be distinguished from serializer/key/database mismatches through real checks.

## 16. Self-Review Questions

1. Why should `RedisConnectionFactory` be a shared Spring bean rather than instantiated per request?
2. How do `LettuceConnectionFactory` and `RedisTemplate` differ in responsibility?
3. Why does `RedisTemplate<String, ProductSnapshot>` still need `setKeySerializer(...)` and `setValueSerializer(...)`?
4. When would you choose `StringRedisTemplate` over a template storing JSON objects?
5. If both templates use the same Redis server, what happens when they write to the same key using different serializers?
6. Why does declaring `productRedisTemplate` not guarantee Spring Cache uses that serializer?
7. What problem does `@Qualifier` solve when multiple factories or templates exist?
8. What determines whether to choose `RedisStandaloneConfiguration`, `RedisSentinelConfiguration`, or `RedisClusterConfiguration`?
9. Could a Redis command that timed out on the client have executed on the server? Why does that affect retrying `INCR`?
10. If Redis uses ACLs/TLS, which settings must come from secure configuration instead of being hardcoded?

**Key takeaway:** `RedisConnectionFactory` handles connections; `RedisTemplate` handles the operation API and data conversion; services handle business rules. Manual configuration is reliable only when **the factory targets the right Redis, beans are injected unambiguously, serializers are consistent per key, and failure behavior is explicitly designed**.
