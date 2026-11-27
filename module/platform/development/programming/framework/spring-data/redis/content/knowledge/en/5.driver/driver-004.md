# Configuring `JedisConnectionFactory` in Spring Data Redis

`JedisConnectionFactory` is the Spring Data Redis implementation of the **`RedisConnectionFactory`** interface backed by the **Jedis** driver. It is responsible for creating and supplying Redis connections to Spring components such as `RedisTemplate`, `StringRedisTemplate`, Redis Cache, and other synchronous APIs that use Spring Data Redis. When using Jedis, configuring the connection factory is the central place to specify the Redis server, authentication mechanism, timeouts, TLS, connection pool, and topology such as standalone, Sentinel, or Cluster.

In a Spring Boot application, there are two common approaches:

1. **Let Spring Boot auto-configure**: include Jedis on the classpath, set `client-type: jedis`, and configure `spring.data.redis.*`. This suits most applications.
2. **Declare a `JedisConnectionFactory` bean manually**: construct `RedisStandaloneConfiguration`, `RedisSentinelConfiguration`, or `RedisClusterConfiguration` combined with `JedisClientConfiguration` when connection control beyond what Boot provides is needed.

This lesson focuses on proper configuration in Spring Data Redis, the role of each class, what changes when switching topologies, and practical pitfalls when integrating Jedis with Spring Boot.

## 1. Where does `JedisConnectionFactory` fit in the architecture?

This class resides in package:

```java
org.springframework.data.redis.connection.jedis.JedisConnectionFactory
```

It serves as an adapter between Spring Data Redis and the `redis.clients:jedis` client library:

```text
                 Spring Boot Application
                         |
             Service / Repository / Cache
                         |
          RedisTemplate / StringRedisTemplate
                         |
                RedisConnectionFactory
                         |
                JedisConnectionFactory
                  /               \
     RedisStandaloneConfiguration  JedisClientConfiguration
       or Sentinel / Cluster         timeout / TLS / pool
                  \               /
                    Jedis client
                         |
               Redis standalone / Sentinel / Cluster
```

`RedisConnectionFactory` is a **Spring Data Redis abstraction**; `JedisConnectionFactory` is **one implementation**. `LettuceConnectionFactory` is another popular implementation using the Lettuce driver. Business code should interact via `RedisTemplate` or Spring Data Redis abstractions, allowing you to switch drivers without rewriting all data manipulation commands.

Distinguishing class responsibilities:

| Component | Role |
|---|---|
| `JedisConnectionFactory` | Creates/acquires Redis connections through Jedis; integrates with Spring bean lifecycle |
| `RedisStandaloneConfiguration` | Configures host, port, database, and credentials for a standalone server |
| `RedisSentinelConfiguration` | Configures Sentinel master name, sentinel addresses, and related auth |
| `RedisClusterConfiguration` | Configures seed nodes, redirects, and credentials for Redis Cluster |
| `JedisClientConfiguration` | Configures Jedis-side behavior such as connection pooling, timeouts, SSL/TLS |
| `RedisTemplate<K,V>` | Executes Redis commands and applies key/value serializers |
| `StringRedisTemplate` | Convenient template for string keys and values |

A connection factory **does not determine serializers for individual business domains**. It supplies connections; the template or cache configuration decides how Java data turns into bytes stored by Redis.

## 2. Jedis vs. Lettuce: choosing the right driver

Spring Data Redis supports common drivers, though Jedis and Lettuce differ in key ways:

| Criterion | Jedis | Lettuce |
|---|---|---|
| Spring Data Redis class | `JedisConnectionFactory` | `LettuceConnectionFactory` |
| Synchronous Spring Data APIs | Supported | Supported |
| `ReactiveRedisTemplate` via Spring Data Redis | Not the Spring Data Redis reactive driver | Supported via `ReactiveRedisConnectionFactory` |
| Typical connection model | Pool of synchronous connections under concurrent requests | Can share a native connection across many operations via Lettuce's I/O model; configured per situation |
| Standalone / Sentinel / Cluster | Supported per respective Jedis and Spring Data Redis versions | Supported |
| Spring Boot starter integration | Must add Jedis dependency if default starter brings Lettuce | Usually included with the default starter |

If the application is built on Spring MVC with synchronous services and you want to use Jedis, `JedisConnectionFactory` is a suitable choice. If the application uses **`ReactiveRedisTemplate`** or end-to-end Reactor flows, choose Lettuce and `LettuceConnectionFactory`, because `JedisConnectionFactory` does not implement `ReactiveRedisConnectionFactory` for Spring Data Redis.

Remember: **adding the Jedis library as a dependency does not automatically guarantee the application is using Jedis**, especially when both Lettuce and Jedis exist on the classpath. Verify which driver is selected by auto-configuration or inspect the active connection factory bean at runtime.

## 3. Adding the Jedis dependency in Spring Boot

Gradle Groovy DSL example with Spring Boot 3.x:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'redis.clients:jedis'

    // Needed when using a connection pool and not already present in the environment.
    implementation 'org.apache.commons:commons-pool2'
}
```

If the project uses Spring Boot dependency management or a Boot-managed Gradle platform, **let the BOM determine compatible versions** of Spring Data Redis and Jedis; avoid arbitrarily pairing a newer Jedis release with an older Spring Data Redis. Commons Pool 2 supports Jedis pooling. When a project does not use dependency management, you must specify and align compatible versions explicitly.

With Maven:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>redis.clients</groupId>
        <artifactId>jedis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.apache.commons</groupId>
        <artifactId>commons-pool2</artifactId>
    </dependency>
</dependencies>
```

In this lesson, examples use **Spring Boot 3.x** configuration under the `spring.data.redis.*` namespace. If maintaining a Spring Boot 2.x application, Redis properties typically live under `spring.redis.*`, and APIs/library combinations may differ. Always consult documentation for the exact deployed version.

## 4. Recommended approach: Spring Boot auto-configures `JedisConnectionFactory`

When the goal is simply connecting to standalone Redis with Jedis, you can use `application.yml`:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
      jedis:
        pool:
          enabled: true
          max-active: 16
          max-idle: 8
          min-idle: 2
          max-wait: 2s
```

Meaning:

- `client-type: jedis`: instructs Spring Boot auto-configuration to choose Jedis when the driver is available and no custom connection factory bean is supplied by the application.
- `host`, `port`: standalone Redis address.
- `database: 0`: logical database; non-`0` values may be used with standalone Redis supporting multiple DBs, but **Redis Cluster uses only DB 0**.
- `connect-timeout`: maximum wait to establish a network connection.
- `timeout`: read/write operation timeout as applied by Spring Boot and the driver for the corresponding version.
- `jedis.pool.*`: bounds and maintains reusable connections.

With matching configuration and dependencies, Boot creates a `RedisConnectionFactory` backed by Jedis. Auto-configured beans such as `StringRedisTemplate` consume that connection factory. The application **does not need to call `new JedisConnectionFactory(...)`** in each service.

### Environment configuration and passwords

In authenticated environments, you can add:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      username: ${REDIS_USERNAME:default}
      password: ${REDIS_PASSWORD}
```

This example requires `REDIS_HOST` and `REDIS_PASSWORD` to be set in the deployment environment. `default` is the default ACL username in Redis 6+; if the system only uses `requirepass` without separate ACL users, authentication must match the server and driver. Never commit real passwords to repositories, logs, or publicly shared examples.

If the application runs in Docker Compose, `localhost` inside a container usually points to **the application container itself**. When Redis runs in a separate container on the same Compose network, use the service DNS name, such as `redis`, instead of `localhost`.

## 5. Declaring a `JedisConnectionFactory` bean manually

When specialized connection policies are required, or when separating multiple connection factories, you can create the bean with Java config.

Example standalone connection with pooling and timeouts:

```java
package com.example.redis;

import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.jedis.JedisClientConfiguration;
import org.springframework.data.redis.connection.jedis.JedisConnectionFactory;

@Configuration(proxyBeanMethods = false)
public class JedisRedisConfiguration {

    @Bean
    public RedisConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration server =
                new RedisStandaloneConfiguration("localhost", 6379);
        server.setDatabase(0);

        JedisClientConfiguration client = JedisClientConfiguration.builder()
                .connectTimeout(Duration.ofSeconds(2))
                .readTimeout(Duration.ofSeconds(3))
                .usePooling()
                .build();

        return new JedisConnectionFactory(server, client);
    }
}
```

Each step serves a distinct purpose:

1. `RedisStandaloneConfiguration` describes **the target server** and logical database.
2. `JedisClientConfiguration` describes **client behavior** such as timeouts, pooling, and optionally TLS.
3. The `new JedisConnectionFactory(server, client)` constructor combines both groups to create the connection factory.
4. `@Bean` hands factory lifecycle management to Spring: Spring initializes the bean and releases resources when the context closes.

With the manual approach, **Spring Boot does not automatically apply all `spring.data.redis.*` properties to your custom bean**. For instance, changing `spring.data.redis.host` in YAML will not change `"localhost"` hardcoded in the bean above. To read environment settings, bind properties via `@ConfigurationProperties`, `RedisProperties`, or inject the appropriate values. Avoid arbitrarily mixing an auto-configured factory with a manual factory without deciding which bean is primary.

### Constructors and bean lifecycle

`JedisConnectionFactory` implements the required Spring lifecycle contracts. In an application using `@Bean`, the framework invokes the corresponding initialization/destruction callbacks. Do not create a factory per request or manually call `afterPropertiesSet()` when the factory already belongs to the Spring `ApplicationContext`.

If instantiating the factory outside Spring for isolated use, understand and manage the factory lifecycle according to your version's API. In typical Spring Boot apps, let the container manage it to prevent connection/pool leaks.

## 6. `RedisStandaloneConfiguration`: address, DB, and authentication

Standalone is a standard Redis server, possibly with a replica and external failover, where the client connects to a specific endpoint. Typical settings:

```java
import org.springframework.data.redis.connection.RedisPassword;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;

RedisStandaloneConfiguration standalone =
        new RedisStandaloneConfiguration("redis.internal", 6379);

standalone.setDatabase(1);
standalone.setUsername("app_user");
standalone.setPassword(RedisPassword.of("example-secret"));
```

`example-secret` is only a placeholder. In production code, retrieve passwords from a secret manager or environment configuration rather than hardcoding literals in source. Redis versions without ACL usernames require configuring authentication according to how Redis is set up.

Common points of confusion:

- `database` is a logical database index, not an SQL-style schema or database name.
- `database: 1` only suits standalone when the server has enough logical databases enabled.
- Any database other than `0` **cannot be used when the factory connects to Redis Cluster**.
- Specifying a static primary IP does not automatically provide discovery of a new primary on failover. For Sentinel discovery, you need Sentinel topology configuration.

## 7. `JedisClientConfiguration`: timeouts, TLS, connection pool

Server details and client policies are separated for clarity. `JedisClientConfiguration` does not specify key or value serializers; it controls how Jedis connects.

### 7.1. Connect timeout and read timeout

Sample configuration:

```java
JedisClientConfiguration client = JedisClientConfiguration.builder()
        .connectTimeout(Duration.ofSeconds(2))
        .readTimeout(Duration.ofSeconds(3))
        .usePooling()
        .build();
```

**Connect timeout** limits establishing the TCP/TLS connection to Redis. **Read timeout** governs waiting for a command reply from the server. Distinguish both from the time spent waiting for an idle connection from the pool (`max-wait`). Slow server connectivity, a slow command, and pool exhaustion are three distinct causes of timeouts.

There is no single optimal timeout across all applications. For example, simple cache lookups usually require fast responses, whereas tasks executing expensive commands have different policies. Timeouts must also match real latency, load levels, retries, and request SLAs.

### 7.2. Enabling TLS

If the Redis server is configured with TLS, the client must also enable TLS. At the Jedis configuration level:

```java
JedisClientConfiguration tlsClient = JedisClientConfiguration.builder()
        .useSsl()
        .build();
```

With Spring Boot auto-configuration, you can use:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      host: redis-secure.example.net
      port: 6380
      ssl:
        enabled: true
```

Port `6380` is just an example; the actual port depends on your Redis service. TLS also requires proper certificate/truststore configuration and hostname verification. Do not disable certificate verification merely to bypass handshake errors in environments requiring security.

When using a **manual factory bean**, `spring.data.redis.ssl.enabled` will not automatically turn on TLS on a hardcoded `JedisClientConfiguration`. Pass SSL settings directly into the corresponding builder.

### 7.3. What is pooling?

Jedis typically works with synchronous connections acquired per execution flow. A connection pool holds ready connections for the application to borrow, use, and return, avoiding the cost of opening a new connection for every command:

```text
Thread A ---> borrow ---> [Redis connection #1] ---\
Thread B ---> borrow ---> [Redis connection #2] ----> Redis
Thread C ---> borrow ---> [Redis connection #3] ---/
                  |
               return
                  v
             Jedis pool
```

A `JedisConnection` or native Jedis connection used for an individual operation **must not be used concurrently by multiple threads**. Rather than holding a `Jedis` object in a singleton service and sharing it, use `RedisTemplate` and a Spring-managed factory so borrowing/returning connections follows framework mechanics.

## 8. Detailed Jedis connection pool configuration

When using Spring Boot auto-configuration, common pool properties are:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      jedis:
        pool:
          enabled: true
          max-active: 24
          max-idle: 12
          min-idle: 3
          max-wait: 1500ms
          time-between-eviction-runs: 30s
```

| Property | Meaning | If misconfigured |
|---|---|---|
| `max-active` | Connections the pool can allocate concurrently | Too small causes contention; too large can pressure Redis |
| `max-idle` | Maximum idle connections retained by the pool | Too large keeps unnecessary idle connections |
| `min-idle` | Target minimum idle connections | Too large keeps many connections open under low load |
| `max-wait` | Maximum wait when borrowing while pool is exhausted | Too short fails during traffic spikes; too long slows requests |
| `time-between-eviction-runs` | Interval between idle connection eviction checks per pool support | Must align with idle validation policy and resource usage |

The numbers above are for explanation only; they are not standard production settings. A service with 10 instances, each with `max-active: 24`, can open up to roughly **240 active connections** if all pools hit max capacity. Compare this against Redis's `maxclients`, CPU/network load, admin/monitoring connections, and other applications sharing Redis.

### What happens when the pool runs out of connections?

Suppose a service has `max-active: 2` while 20 concurrent requests must execute a slow Redis operation:

```text
Request 1 ---- uses connection A ------------------>
Request 2 ---- uses connection B ------------------>
Request 3 ---- waits on pool (-- max-wait --) -> timeout
Request 4 ---- waits on pool (-- max-wait --) -> timeout
...
```

Here the error may be **failing to borrow a connection from the pool**, not necessarily Redis refusing connections. Check Redis command execution times, request concurrency, pool sizing, proper connection return, and possible Redis overload. Raising `max-active` indefinitely simply shifts the bottleneck onto the server.

### Connection pooling in Java config

Jedis supports Commons Pool 2, and Spring Data Redis provides a builder to enable pooling. Minimal configuration:

```java
JedisClientConfiguration jedisClient =
        JedisClientConfiguration.builder().usePooling().build();

JedisConnectionFactory factory =
        new JedisConnectionFactory(
                new RedisStandaloneConfiguration("localhost", 6379),
                jedisClient);
```

To customize pool limits deeply in code, the Jedis pooling builder can accept a corresponding Commons Pool config; exact config types and generics depend on the Jedis/Spring Data Redis version. In Spring Boot applications, it is usually easier to operate with pool parameters in `application.yml` instead of burying capacity limits in Java source code.

## 9. Configuring Redis Sentinel connections with Jedis

**Redis Sentinel** monitors Redis primary/replicas and supports discovery/failover. Applications should not hardcode a single primary address that can change on failover. Instead, Sentinel configuration provides the master name and a list of Sentinel endpoints.

Spring Boot example:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1.example.net:26379
          - sentinel-2.example.net:26379
          - sentinel-3.example.net:26379
      username: ${REDIS_USERNAME:default}
      password: ${REDIS_PASSWORD}
      connect-timeout: 2s
      timeout: 3s
```

`mymaster` is the master group name known to Sentinel, not a specific Redis master hostname. The `sentinel-*` addresses must point to the **Sentinel service**, typically listening on port `26379`; they differ from Redis data node endpoints, which typically listen on port `6379` unless customized.

When Sentinel itself requires authentication, configure **Sentinel credentials** in addition to Redis data node credentials using the properties/settings supported by your Spring Boot and Spring Data Redis versions. Do not assume the Redis server password automatically works for Sentinel login.

### Configuring Sentinel in Java

```java
import org.springframework.data.redis.connection.RedisSentinelConfiguration;
import org.springframework.data.redis.connection.jedis.JedisClientConfiguration;
import org.springframework.data.redis.connection.jedis.JedisConnectionFactory;

RedisSentinelConfiguration sentinel = new RedisSentinelConfiguration()
        .master("mymaster")
        .sentinel("sentinel-1.example.net", 26379)
        .sentinel("sentinel-2.example.net", 26379)
        .sentinel("sentinel-3.example.net", 26379);

JedisClientConfiguration client =
        JedisClientConfiguration.builder().usePooling().build();

JedisConnectionFactory factory =
        new JedisConnectionFactory(sentinel, client);
```

This snippet illustrates topology without declaring authentication or TLS. In production, add credentials for both Redis and Sentinel as needed. For a Spring-managed bean, return the factory from a `@Bean` so Spring manages its lifecycle and exposes it to templates.

**Sentinel is not Redis Cluster.** Sentinel manages failover for a primary/replica group; it does not distribute keys across 16,384 slots like Cluster. Logical database selection and data modeling under Sentinel still differ from Cluster.

## 10. Configuring Redis Cluster connections with Jedis

Redis Cluster distributes data across hash slots. When using Jedis with Spring Data Redis, configure seed nodes so the client discovers topology and routes commands to the appropriate node.

Spring Boot example:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      cluster:
        nodes:
          - redis-1.example.net:6379
          - redis-2.example.net:6379
          - redis-3.example.net:6379
        max-redirects: 5
      connect-timeout: 2s
      timeout: 3s
```

If Cluster uses username/password, TLS, or separate pool settings, add the corresponding properties. The node list above represents initial connection endpoints (**seed nodes**), not that data lives only on those three nodes. Addresses advertised by the Cluster must be reachable from the application. If Cluster runs inside a container network, NAT, or Kubernetes, check advertised addresses and network routes.

Java config example:

```java
import java.util.List;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.jedis.JedisClientConfiguration;
import org.springframework.data.redis.connection.jedis.JedisConnectionFactory;

RedisClusterConfiguration cluster = new RedisClusterConfiguration(
        List.of(
                "redis-1.example.net:6379",
                "redis-2.example.net:6379",
                "redis-3.example.net:6379"));
cluster.setMaxRedirects(5);

JedisClientConfiguration client =
        JedisClientConfiguration.builder().usePooling().build();

JedisConnectionFactory factory =
        new JedisConnectionFactory(cluster, client);
```

With Cluster, remember:

- **Redis Cluster supports only logical database `0`**. Do not use `database: 1` or try to run `SELECT`.
- Cluster-capable clients must route by hash slot and may receive redirects like `MOVED` or `ASK` when slot ownership changes.
- Multi-key operations must be checked for same-slot constraints. Matching key prefixes do not guarantee the same slot; `{...}` hash tags can place related keys in the same slot when genuinely required.
- `FLUSHDB`, `DBSIZE`, and `SCAN` against one node do not automatically operate on or observe the entire Cluster; administrative tooling must understand topology and per-node scope.

`JedisConnectionFactory` handles Cluster connectivity; it does not automatically migrate key/transaction strategies from standalone to Cluster. During migration, audit Lua scripts, multi-key commands, and code relying on database indices.

## 11. Using the connection factory from `RedisTemplate`

Once the factory is created, ordinary service calls do not depend directly on Jedis:

```java
package com.example.redis;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class VisitCounter {

    private final StringRedisTemplate redis;

    public VisitCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long increment(String articleId) {
        return redis.opsForValue().increment("article:visits:" + articleId);
    }

    public void saveLastVisited(String articleId, String userId) {
        redis.opsForValue().set(
                "article:last-viewed:" + articleId,
                userId,
                Duration.ofMinutes(30));
    }
}
```

`StringRedisTemplate` uses the Spring-supplied factory and string serialization. `increment(...)` executes a Redis command on a string-encoded integer; it returns `Long` which can be `null` in certain pipeline/transaction contexts, so check the API contract at call sites.

If you want to declare the template manually:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class TemplateConfig {

    @Bean
    StringRedisTemplate stringRedisTemplate(RedisConnectionFactory factory) {
        return new StringRedisTemplate(factory);
    }
}
```

In Spring Boot, the `StringRedisTemplate` bean is normally auto-configured if no matching bean exists; declare another only for a specific reason. When multiple `RedisConnectionFactory` beans coexist, select the factory with `@Qualifier` or mark a `@Primary` bean to prevent injection ambiguity.

### Direct connections: only when truly needed

Spring Data Redis provides the `RedisConnection` API for low-level commands:

```java
import org.springframework.data.redis.connection.RedisConnection;
import org.springframework.data.redis.connection.RedisConnectionFactory;

public String ping(RedisConnectionFactory factory) {
    try (RedisConnection connection = factory.getConnection()) {
        return connection.ping();
    }
}
```

When acquiring a connection directly, the caller must close it properly to return it to the pool or release resources. In regular business code, use `RedisTemplate` so the framework manages connection lifecycle, exception translation, and data operations consistently.

## 12. Distinguishing pool connections, Redis databases, and serializers

Three concepts are frequently confused:

**Connection pool** holds reusable TCP connections. Multiple connections in the pool can all operate on DB 0, and a larger pool does not mean extra Redis databases.

**Logical database** is a keyspace selected on standalone Redis. The database index is part of server configuration. In Redis Cluster, this selection is restricted to DB 0.

**Serializer** converts Java values into Redis bytes. Replacing `JedisConnectionFactory` with `LettuceConnectionFactory` does not convert existing stored data from JDK serialization to JSON or alter key names. `RedisTemplate`/`RedisCacheManager` serializer configuration is an independent contract.

For example, the same factory can serve two templates with different serializers:

```text
JedisConnectionFactory
      |
      +--> StringRedisTemplate
      |      key: UTF-8 string
      |      value: UTF-8 string
      |
      +--> RedisTemplate<String, Product>
             key: UTF-8 string
             value: JSON Product
```

If two templates read the same key without agreeing on serializers, deserialization errors can occur even while the Jedis connection is completely healthy. When multiple data groups or services share Redis, use clear key prefixes and payload formats.

## 13. How Spring Boot picks a factory and common conflict scenarios

Consider these scenarios:

| Situation | Expected behavior |
|---|---|
| Default `spring-boot-starter-data-redis` without Jedis configured | Typically uses Lettuce if starter dependencies remain intact |
| Both Lettuce and Jedis present, `client-type: jedis` declared | Spring Boot selects Jedis for auto-config when classpath and bean conditions match |
| Custom `@Bean RedisConnectionFactory` declared | Auto-configured factory typically backs off for the custom bean; Boot properties do not auto-apply to all manual builders |
| Two `RedisConnectionFactory` beans present | Type-based injection may be ambiguous; requires `@Primary` or `@Qualifier` |
| `ReactiveRedisTemplate` present but only Jedis factory exists | No `ReactiveRedisConnectionFactory` suitable for reactive Redis via Jedis |
| Custom `RedisTemplate` with custom serializer | Connection factory supplies connections; template serializer must still be configured separately |

To verify the factory type at runtime, inspect the bean class rather than guessing from dependencies:

```java
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration(proxyBeanMethods = false)
public class RedisFactoryInspector {

    @Bean
    ApplicationRunner inspectRedisFactory(RedisConnectionFactory factory) {
        return args -> System.out.println(
                "Redis connection factory: " + factory.getClass().getName());
    }
}
```

This snippet is for learning-environment inspection; production applications should use a logging framework instead of `System.out.println`. Output containing `JedisConnectionFactory` shows Spring is injecting the Jedis driver. If the bean is wrapped or proxied, inspect the actual `ApplicationContext` configuration further.

## 14. A complete development environment configuration

Example `application-dev.yml` for standalone Redis without authentication in an isolated dev environment:

```yaml
spring:
  config:
    activate:
      on-profile: dev
  data:
    redis:
      client-type: jedis
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
      jedis:
        pool:
          enabled: true
          max-active: 8
          max-idle: 4
          min-idle: 1
          max-wait: 1s
```

When using another profile for production, settings need not mirror dev values. Production typically needs internal endpoints, authentication, TLS, load-appropriate connection limits, error observability, and proper retry policies. Note that properties under `spring.data.redis.*` only apply to factories created/bound by Spring Boot or custom code that explicitly reads those properties.

Simple snippet to manipulate a key:

```java
import java.time.Duration;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class RedisExampleRunner {

    @Bean
    ApplicationRunner demoRedis(StringRedisTemplate redis) {
        return args -> {
            String key = "demo:jedis:status";
            redis.opsForValue().set(key, "connected", Duration.ofSeconds(60));
            String value = redis.opsForValue().get(key);
            System.out.println("Read from Redis: " + value);
        };
    }
}
```

In a dev environment with Redis running, typical read output is:

```text
Read from Redis: connected
```

The demo above writes to Redis on every startup; enable such runners only in practice environments and never let demo code write to production Redis. Applying `@Profile("dev")` on the class or bean is one way to limit its scope.

## 15. Common errors when configuring `JedisConnectionFactory`

| Symptom | Common cause | Approach |
|---|---|---|
| `JedisConnectionFactory` or `Jedis` class not found | Missing Spring Data Redis/Jedis dependency, incompatible versions | Check dependency graph and version-matched BOM |
| App still uses `LettuceConnectionFactory` | Added Jedis without selecting driver, or another factory bean exists | Check `client-type`, declared beans, and auto-configuration |
| `Connection refused` | Redis not running, wrong host/port, `localhost` confusion in Docker | Verify DNS, network, container, Redis endpoint |
| `NOAUTH` or `WRONGPASS` | Wrong password, ACL username, secret, or Sentinel credentials | Separate Redis server and Sentinel credentials; verify ACL permissions |
| `SSLHandshakeException` | TLS wrong port or invalid certificate/trust | Check TLS on client and server; certificate chain, hostname |
| Timeout borrowing connection | Pool too small or connections held too long | Check pool wait, concurrency, command duration, and connection return |
| `RedisCommandTimeoutException` or similar timeout | Slow Redis or network, timeout too short | Distinguish connect/read/pool wait; observe latency before raising timeout |
| `ERR SELECT is not allowed in cluster mode` | Using non-zero logical DB or trying `SELECT` in Cluster | Use DB 0; remove database selection logic |
| `MOVED`, `CROSSSLOT` on Cluster access | Client not cluster-aware, multi-key across slots | Use Cluster-aware factory; review multi-key/hash tags |
| `SerializationException` | Reader serializer incompatible with stored data | Check key/value serializers; usually not a Jedis connection error |
| Cannot inject `RedisConnectionFactory` | Multiple beans of same type without qualifier/primary | Explicitly specify which bean template/service must use |
| YAML settings have no effect | Manually created factory with hardcoded values | Bind properties in Java or rely on Spring Boot auto-config |

### Isolating a timeout error to the right layer

When a service reports a Redis-related error, pinpoint which stage failed:

```text
HTTP request
    |
    v
Borrow connection from pool  -- waits past max-wait --> Pool timeout
    |
    v
Connect to Redis             -- exceeds connect-timeout --> Connect timeout
    |
    v
Send command / wait reply    -- exceeds read timeout --> Read/command timeout
    |
    v
Deserialize response         -- format mismatch --> SerializationException
```

These four errors have different root causes and fixes. Simply increasing `max-active` will not fix a slow Redis server; simply increasing `readTimeout` will not fix an exhausted connection pool. Before retrying, check command idempotency: `GET` and `SET` with a deterministic value differ from `INCR`/`LPUSH` in consequences if re-sent after a lost reply.

### Example when Redis changes endpoint

If Redis uses Sentinel and the primary fails over to a replica, connecting directly to `old-primary:6379` can fail or write to a node that is no longer primary. A Sentinel-configured factory lets the application locate the primary through Sentinel via the driver. With Cluster, the client must refresh topology and handle redirects. That is why you must choose the **right server configuration type** rather than merely changing a hostname list.

## 16. Operating and monitoring the pool in production

Metrics to watch when tuning `JedisConnectionFactory`:

1. **Redis latency**: round-trip time and execution time for common commands, especially commands that can block or consume heavy resources.
2. **Connection counts**: active/idle connections in the pool, `connected_clients`, and server `maxclients` limit.
3. **Timeouts**: classify pool exhaustion, network connect timeouts, and read/command timeouts; correlate with concurrent requests.
4. **Topology and failover**: active endpoint, Sentinel master changes, or Cluster redirects/unavailable nodes.
5. **Auth/TLS failures**: distinguish expired credentials, ACL changes, expired certificates, or hostname verification errors.
6. **Data and format**: serializer errors, incorrect TTLs, keyspace growth, large keys, or bloated hashes/lists.

Increasing the connection pool generally increases concurrency of Redis commands, yet Redis still has limits on CPU, memory, network, and client count. When multiple application instances share Redis, capacity must be calculated **across the entire system**, not per JVM.

Retry mechanisms must also be bounded and measured. If Redis is degraded, every request retrying immediately in unison can worsen the outage. For non-idempotent commands or commands with side effects, a lost reply does not mean the server never executed the command; retry policy must follow business contracts.

## 17. Frequently asked questions

**Is it mandatory to define `@Bean JedisConnectionFactory` to use Jedis?**

No. With Spring Boot and appropriate dependencies, `spring.data.redis.client-type: jedis` plus Redis configuration properties allow Boot to create the factory. Manual bean configuration makes sense when the application has specialized connection requirements.

**Why does Spring Boot still use Lettuce even after adding `redis.clients:jedis`?**

Because the starter usually brings Lettuce, and having two clients on the classpath does not indicate an explicit choice. Check `spring.data.redis.client-type`, custom declared beans, and auto-configuration conditions. No business code changes are needed just to switch drivers.

**Does `JedisConnectionFactory` support Spring WebFlux?**

A WebFlux application can still call Redis synchronously, but that is a blocking operation requiring appropriate execution offloading to avoid blocking the event loop. For true reactive Redis via `ReactiveRedisTemplate`, use Lettuce with `ReactiveRedisConnectionFactory`.

**Is a pool needed for a low-traffic service?**

There is no mandatory pool size for every app. Pooling helps when multiple concurrent operations occur and connections are reused. Sizing decisions should be based on load, connection lifecycle, latency, and server limits; with Jedis, pooling is the standard approach rather than unsafely sharing a native connection across threads.

**Can `database: 3` be used with Sentinel?**

Sentinel manages standard Redis primary/replicas, unlike Redis Cluster. Logical databases can still be used if the Redis data nodes support and are configured for them. Conversely, Redis Cluster supports only DB 0.

**Does switching from Jedis to Lettuce lose Redis data?**

Changing drivers does not delete Redis keys. However, you must keep the same endpoint, database, key names, serializers, and command semantics. If you change serializers or namespaces simultaneously, the application may fail to read old data even though the data still exists.

**Is `@Primary` needed when there is only one `RedisConnectionFactory`?**

No. `@Primary` is mainly needed when multiple beans of the same type exist and injection points do not specify which bean to use. With a single Boot-created factory, the framework wires it to matching templates automatically.

**If Redis Cluster has no DB 1, can data be isolated using two connection factories on the same Cluster?**

Two factories pointing to the same Cluster still see the same DB 0. Use key prefix/namespace conventions and Redis ACLs if key-level access restrictions are needed; if strong resource or operational isolation is required, consider separate Redis deployments.

## 18. Summary of configuration choices

| Context | `JedisConnectionFactory` configuration approach |
|---|---|
| Spring Boot + standard standalone Redis | Add Jedis, set `client-type: jedis`, declare host/port/password/timeout in YAML |
| Need programmatic control of timeout, pooling, TLS | Create `RedisStandaloneConfiguration` and `JedisClientConfiguration`, pass to factory constructor |
| Redis Sentinel | Use `RedisSentinelConfiguration` or `spring.data.redis.sentinel.*`; declare master name and sentinel nodes |
| Redis Cluster | Use `RedisClusterConfiguration` or `spring.data.redis.cluster.*`; DB 0 only and mind hash slots |
| Using `ReactiveRedisTemplate` | Choose Lettuce and `ReactiveRedisConnectionFactory` for the reactive path |
| Multiple Redis connection factories | Disambiguate beans via `@Qualifier`/`@Primary`; configure templates/caches with the right factory |

`JedisConnectionFactory` is the integration point for the Jedis driver in Spring Data Redis architecture. When configuring it, clearly separate **server topology** (`RedisStandaloneConfiguration`, Sentinel, or Cluster), **client behavior** (`JedisClientConfiguration`: timeout, pool, TLS), and **data representation** (template/cache serializers). With Spring Boot, auto-configuration is usually simpler and easier to manage; manual Java configuration should be reserved for specific needs. Recognizing those three boundaries keeps connectivity reliable, error handling grounded, and Redis scaling clean without tangling business logic.
