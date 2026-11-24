# spring.data.redis.* and Connection and Timeout Configuration

## 1. Redis Is an Integration Dependency, Not Just a Host Address

In the **SPRING_BOOT_INTEGRATION** module, a Spring Boot application may access databases, call HTTP APIs, use caches, communicate with brokers, and process messages via Spring Integration. **Redis** commonly appears in multiple roles: read caching, temporary locks, session state, rate limiting, deduplication, or as a dedicated key-value data store.

Regardless of purpose, the client still connects over the network. If the address, TLS, credentials, or timeouts are misconfigured, Redis failures can affect the entire flow:

- A cache miss unable to reach Redis slows down or fails an HTTP request.
- Unbounded Redis retries saturate service threads and put pressure on the database.
- A flow writing idempotency state to Redis that times out risks running duplicate side effects if timeout is treated as "not written".
- A message consumer running in Spring Integration may fail and trigger redelivery; poor timeout configuration creates unexpected retry loops.

Therefore, this lesson aims to explain the **`spring.data.redis.*`** property group in Spring Boot: how auto-configuration creates the Redis client, connection properties, timeouts, Lettuce/Jedis, Redis standalone/Sentinel/Cluster, TLS and credentials, error behavior, testing, and observability.

```mermaid
flowchart LR
    A["HTTP / Service / Integration Flow"] --> B["RedisTemplate / StringRedisTemplate"]
    A --> C["Spring Cache (if used)"]
    B --> D["RedisConnectionFactory"]
    C --> D
    D --> E["Lettuce / Jedis"]
    E --> F[("Redis server / Sentinel / Cluster")]
    G["spring.data.redis.*"] -. "Connection / timeout / TLS" .-> D
```

**Version scope:** examples are based on Spring Boot **3.x**, where the primary property group is `spring.data.redis.*` and the default client is typically Lettuce. In Spring Boot 2.x, Redis properties may use a different prefix such as `spring.redis.*`; when upgrading, never copy old configuration files verbatim without checking the metadata of the running version.

## 2. Layers of Responsibility: Boot, Spring Data Redis, Client, and Server

| Component | Role | What It Does Not Do Automatically |
| --- | --- | --- |
| Spring Boot auto-configuration | Reads properties and prepares Redis beans when conditions match | Does not start a Redis server |
| Spring Data Redis | Provides `RedisTemplate`, `StringRedisTemplate`, repositories, and related abstractions | Does not replace Redis security/HA rules |
| `RedisConnectionFactory` | Common entry point supplying Redis connections to abstractions | Does not guarantee every Redis command succeeds |
| Lettuce or Jedis | Client libraries speaking the Redis protocol over the network | Does not know your business contract |
| Redis server / Cluster / Sentinel | Stores data and serves Redis commands | Does not provide distributed transactions with databases or HTTP |
| Spring Cache | `@Cacheable`, `@CacheEvict` annotations with `CacheManager` | Not automatically suitable for business idempotency/locks |

Common beans in a Spring Boot app with `spring-boot-starter-data-redis`:

- `RedisConnectionFactory`: typically `LettuceConnectionFactory` when using Lettuce.
- `RedisTemplate<Object, Object>`: Redis operations helper whose serializers are determined by bean/configuration.
- `StringRedisTemplate`: string key/value operations using string serializers.
- Reactive components such as `ReactiveRedisTemplate` may be present when dependencies/clients support them, with corresponding configuration.

**Having a `RedisConnectionFactory` bean does not mean Redis is running.** Some clients establish connections lazily when executing commands. DNS, authentication, or timeout errors may surface only on the first request.

Conversely, if the application declares a custom `RedisConnectionFactory`, Spring Boot may **back off** creating the default factory. Changing `spring.data.redis.host` may then not change the custom bean's address. To see who owns configuration, inspect the actual beans and auto-configuration conditions.

## 3. Minimal Dependencies and Enabling Spring Data Redis

With Maven using Spring Boot parent or BOM version management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

Gradle:

```groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
}
```

This common starter includes Spring Data Redis along with Lettuce and required dependencies. It **does not start a Redis server**. You need a local Redis instance, container, managed service, or provisioned infrastructure.

If the application only wants to use Redis as a Spring Cache provider:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
```

`spring-boot-starter-cache` provides Spring Cache annotations; `spring-boot-starter-data-redis` provides the Redis client. You can use `RedisTemplate` without enabling `@EnableCaching`. Conversely, for cache annotations to actually be intercepted, caching advice must be enabled (usually via `@EnableCaching`) along with an appropriate `CacheManager`.

## 4. Configuring Standalone Redis: Host, Port, Database, Username, and Password

A basic local configuration:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      database: 0
      connect-timeout: 2s
      timeout: 3s
      client-type: lettuce
```

Explanation:

| Property | Meaning | Common Pitfall |
| --- | --- | --- |
| `spring.data.redis.host` | Redis host (standalone) | Using a container name when the app runs on the host rather than inside the Docker network |
| `spring.data.redis.port` | Redis port (standalone), commonly defaulting to 6379 | Hard-coding the host port despite dynamic Docker port mapping |
| `spring.data.redis.database` | Logical database index, typically defaulting to 0 | Setting a non-zero database in Redis Cluster |
| `spring.data.redis.username` | ACL username when Redis requires it | Confusing the app's Redis username with a Linux/Docker user |
| `spring.data.redis.password` | Redis password (or matching ACL password) | Committing plaintext passwords to Git |
| `spring.data.redis.connect-timeout` | Time limit for establishing a network connection | Treating it as the total SLA of an HTTP request |
| `spring.data.redis.timeout` | Timeout for executing/reading Redis commands per client | Treating it as a retry policy or TCP connect timeout |
| `spring.data.redis.client-type` | Selects Lettuce or Jedis when present on classpath | Switching to Jedis without adding the dependency |

Durations use Spring Boot's `Duration` format: `2s`, `500ms`, `1m`. Always write **explicit units** to avoid misreading raw integers as seconds versus milliseconds.

### 4.1. Production Configuration Using Environment Variables

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6379}
      database: 0
      username: ${REDIS_USERNAME:}
      password: ${REDIS_PASSWORD}
      connect-timeout: ${REDIS_CONNECT_TIMEOUT:2s}
      timeout: ${REDIS_COMMAND_TIMEOUT:3s}
      client-type: lettuce
```

Spring resolves `${...}` placeholders from the environment. Never place production passwords directly in committed YAML; use a secret manager, Kubernetes Secret, or your organization's credential system.

**Note on empty values:** `username: ${REDIS_USERNAME:}` is only appropriate if the client/server accepts an empty username (e.g., Redis authenticating only the default user). In systems using Redis ACLs, supply explicit username/password pairs and test them. Avoid exposing secrets in startup logs, Actuator `/env`, or exception details.

### 4.2. Spring Boot Running on Host vs. in a Container?

The two setups do not use the same hostname:

- App running on the **development machine**, Redis in Compose with `ports: ["6379:6379"]`: the app typically connects to `localhost:6379`.
- App running in the **same Compose network**, Redis with service name `redis`: the app typically connects to `redis:6379` and does not need to expose ports for container-to-container communication.
- App running in Kubernetes/cloud: host/port are provided via Service DNS, Redis endpoint, or connection details.

Do not take Docker Compose's `redis` hostname for an IDE running on the host if the machine cannot resolve that name. Similarly, do not use `localhost` inside an app container when Redis runs in another container: `localhost` then refers to the app container itself.

## 5. Redis URL and Precedence Over Individual Properties

Spring Boot supports configuring a Redis connection URL where appropriate:

```yaml
spring:
  data:
    redis:
      url: ${REDIS_URL}
      connect-timeout: 2s
      timeout: 3s
```

Example URLs (containing no real secrets):

```text
redis://localhost:6379/0
rediss://user:password@redis.example.org:6380/0
```

- `redis://` is a non-TLS Redis connection.
- `rediss://` typically denotes a TLS-enabled Redis connection, if the client/provider is configured appropriately.
- The URL may include host, port, database, and credentials according to the Redis URI syntax supported by the client.

In Spring Boot 3.x, **`spring.data.redis.url` can take precedence over `host`, `port`, `username`, and `password`** in auto-configured connection settings. If you set both URL and individual properties and observe the app connecting to the "wrong" target, inspect the actual `RedisConnectionFactory` bean and resolved URL value.

Choose **one source of truth**: either URL or host/port/auth fields, unless there is a clear reason. Never print URLs containing passwords into logs, metric tags, or exception messages. For Sentinel and Cluster, use the corresponding topology properties rather than assuming a standalone URL expresses all nodes/failover strategies.

## 6. Distinguishing connect-timeout, command timeout, and Business Deadline

A common question: "I set `timeout=2s`, so why did the HTTP request still take more than 2 seconds?"

Because a business flow has multiple phases:

```mermaid
flowchart LR
    A["HTTP request"] --> B["Acquire connection / connect Redis"]
    B --> C["Execute Redis command"]
    C --> D["Read DB or call downstream HTTP"]
    D --> E["Write state / return response"]
    F["connect-timeout"] -.-> B
    G["timeout (Redis command)"] -.-> C
    H["HTTP/business flow deadline"] -.-> E
```

### 6.1. Connect Timeout

`spring.data.redis.connect-timeout` bounds a single attempt to **connect** to Redis. It does not guarantee the entire request finishes within that value. DNS resolution, TLS handshake, connection pool waits, and retry/failover steps can affect total latency depending on client and transport.

For instance, `connect-timeout: 2s` does not mean the service waits at most 2 seconds for **all operations** when Redis is down: retries or multiple call steps in the flow can still extend total duration.

### 6.2. Redis Command Timeout

`spring.data.redis.timeout` controls command execution/response read waiting time for the Redis client according to Spring Data Redis and the selected client's mechanics. With Lettuce, command timeout is separate from connect timeout; an established TCP connection can still stall while Redis processes commands, undergoes failover, or experiences network issues.

A command timeout does **not prove Redis failed to execute the command**. For example, the client sends `INCR orders:counter`, Redis increments the counter, and the response is lost. Retrying the same `INCR` immediately will increment it a second time. This is the core distinction between transport errors and business outcomes.

### 6.3. End-to-End Flow Deadline

An HTTP endpoint calling Redis twice, a database once, and a downstream HTTP API once has a total latency larger than any individual component timeout. Allocate a clear time budget:

| Item | Illustrative Value | Notes |
| --- | --- | --- |
| Redis connect timeout | 1 second | Limits connection establishment |
| Redis command timeout | 2 seconds | Limits Redis operation |
| Downstream HTTP timeout | 3 seconds | Depends on upstream |
| Total HTTP deadline | 5 seconds | May be tighter than worst-case sum under retries/parallelism |
| Retry budget | 0–2 attempts depending on operation | Never retry infinitely |

These values are **not fixed production recommendations**. Measure p95/p99 latency, network hops, cluster failover behavior, and SLAs before locking values down.

### 6.4. Reactive Redis and Timeouts

When using `ReactiveRedisTemplate` with Lettuce, operations return `Mono`/`Flux`; you can place `timeout(Duration)` on the publisher at the business layer to bound waiting for a signal. However, a reactive timeout may **cancel the client subscription without canceling a Redis command already executed on the server**. Design idempotency and reconciliation just as in blocking code.

Never set infinite or excessively long timeouts that leave HTTP threads, executors, or message listeners stuck during a Redis outage.

## 7. Lettuce and Jedis: Choosing the Client by Execution Model

Spring Data Redis can use **Lettuce** or **Jedis**. In standard Spring Boot 3.x projects, Lettuce is the default when using the Redis starter.

| Characteristic | Lettuce | Jedis |
| --- | --- | --- |
| Client model | Netty-based; supports synchronous/asynchronous and reactive APIs | Traditional synchronous client; pooling depending on usage |
| Common `RedisConnectionFactory` | `LettuceConnectionFactory` | `JedisConnectionFactory` |
| Reactive Redis integration | Suitable for Spring Data Redis reactive | Does not replace the reactive Lettuce path |
| Connection sharing | Supports connection sharing per configuration; pooling not always needed | Pooling is typically important for concurrent connections |
| Cluster/Sentinel support | Supported per client/configuration | Supported per client/configuration and version |
| When to consider | Most Boot apps, reactive or mixed workloads | Specific library/configuration constraints requiring Jedis |

Explicitly selecting Lettuce:

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      connect-timeout: 2s
      timeout: 3s
```

To use Jedis, a compatible Jedis dependency must be present along with configuration:

```yaml
spring:
  data:
    redis:
      client-type: jedis
      connect-timeout: 2s
      timeout: 3s
```

Merely changing the property to `jedis` without Jedis on the classpath **does not pull in the dependency**. Some projects must remove Lettuce-specific configuration and verify which factory bean is active. Before switching clients in production, re-measure latency, socket usage, pool saturation, connection leaks, and failover behavior.

**Do not equate "Jedis is blocking" with "Lettuce is always non-blocking."** Using `RedisTemplate` in Spring MVC is still a synchronous call from the caller's perspective even with Lettuce underneath. For end-to-end reactive behavior, use reactive APIs and avoid other blocking steps in the chain.

## 8. Lettuce Pool: Needed or Not, and How to Configure It?

A common misconception is "if we have many HTTP requests, we must enable a large Redis pool." Lettuce can share suitable connections across commands; opening many connections does not automatically increase throughput.

Pooling can help execution paths needing dedicated connections, transactions/blocking operations, or workload isolation policies. Evaluate empirically before enabling.

To configure pooling in Boot 3.x when compatible pool dependencies are present, for example:

```xml
<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-pool2</artifactId>
</dependency>
```

```yaml
spring:
  data:
    redis:
      client-type: lettuce
      lettuce:
        pool:
          enabled: true
          max-active: 16
          max-idle: 8
          min-idle: 0
          max-wait: 500ms
```

Meaning:

- `max-active`: maximum number of connections the pool can allocate simultaneously per pool config.
- `max-idle` and `min-idle`: bounds on idle connections.
- `max-wait`: time to wait for a connection from the pool, **distinct from** Redis command timeout.
- `enabled`: enables pooling on Boot versions supporting this property.

In multi-instance deployments, 16 connections per instance × 20 instances can already open **320 connections**; the Redis server, NAT/proxy, and network policies must tolerate that total load. Avoid raising `max-active` merely to mask timeouts caused by slow Redis processing or heavy commands.

If using Jedis, pool settings live under `spring.data.redis.jedis.pool.*` with their corresponding supported properties; do not copy `lettuce.pool` verbatim to `jedis.pool` without verifying version/properties.

## 9. Configuring TLS, Redis ACL Authentication, and Secrets

Managed Redis environments often require TLS, for example on port 6380. Spring Boot 3.x supports Redis SSL configuration:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6380}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      connect-timeout: 2s
      timeout: 3s
```

Some Spring Boot 3.x releases also support **SSL bundles** for centrally managed trust/key material, for example:

```yaml
spring:
  ssl:
    bundle:
      jks:
        redis-client:
          truststore:
            location: classpath:certs/redis-truststore.p12
            password: ${REDIS_TRUSTSTORE_PASSWORD}
            type: PKCS12
  data:
    redis:
      ssl:
        enabled: true
        bundle: redis-client
```

This is a structural configuration example, **not bundled with a real certificate**; `certs/redis-truststore.p12` must be provisioned separately and distributed securely. When using a different Spring Boot version or providers requiring mTLS, check exact SSL bundle support, keystores/truststores, and expected credential formats.

**Never disable hostname/certificate verification** just to "make the connection work." If the TLS handshake fails, verify the CA/truststore, hostname, system clock, SNI, and server certificate chain. Never print private keys, tokens, or Redis passwords in logs.

### 9.1. Redis ACL Differs from Network Access

A TCP connection reaching Redis does not mean `GET`/`SET` is permitted. Redis ACLs can restrict commands and key prefixes:

- A read-only cache user needs read permissions on the appropriate keyspace, not all administrative commands.
- A worker managing idempotency state needs write access to the relevant keys and required atomic operations.
- Health checks may require `PING`, while restricted production accounts may need a dedicated health policy.

If you receive `NOAUTH`/`WRONGPASS`/`NOPERM`, do not treat it as a cache miss. Verify username/password, ACLs, TLS endpoint, and key namespace. In production, Redis typically resides in a private network protected by authentication/ACL, TLS when required by infrastructure, and per-service least-privilege permissions.

## 10. Redis Sentinel: Discovering the Primary During Failover

With **Redis Sentinel**, the application does not talk only to a single fixed server host/port. The client connects to Sentinel nodes, queries the primary for a service name, and locates the Redis instance currently acting as primary.

Common configuration structure example:

```yaml
spring:
  data:
    redis:
      sentinel:
        master: mymaster
        nodes:
          - sentinel-1.example.org:26379
          - sentinel-2.example.org:26379
          - sentinel-3.example.org:26379
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      connect-timeout: 2s
      timeout: 3s
```

`mymaster` is the **master name managed by Sentinel**, not a hostname. The illustrative Sentinel hosts must be replaced with real infrastructure.

Key points:

1. `spring.data.redis.sentinel.nodes` lists **Sentinel endpoints**, not Redis data nodes.
2. Sentinel credentials **may differ** from Redis data node credentials; on supported Boot/client versions, check `sentinel.username`/`sentinel.password` properties if Sentinel requires separate authentication.
3. During failover, the client must discover the new primary and reconnect; in-flight commands may still time out or fail.
4. Sentinel does not provide "transactions across failover": a response lost after a write is accepted by the old primary can leave state ambiguous, requiring idempotency or reconciliation.
5. Tests must simulate Sentinel failover and measure recovery time, not just test against standalone Redis on localhost.

Do not configure both `sentinel` and `cluster` expecting the client to combine them. They are two distinct Redis topologies and must be chosen to match actual deployment.

## 11. Redis Cluster: Node List, Redirection, and Database Index

In **Redis Cluster**, data is partitioned across hash slots among primary nodes. Clients need cluster-aware routing and may receive redirections such as `MOVED`/`ASK` when topology changes.

Example:

```yaml
spring:
  data:
    redis:
      cluster:
        nodes:
          - redis-1.example.org:6379
          - redis-2.example.org:6379
          - redis-3.example.org:6379
        max-redirects: 5
      connect-timeout: 2s
      timeout: 3s
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
```

The nodes declared above are typically **seed nodes** for cluster discovery; they are not an immutable list of every node forever. Topology auto-refresh behavior, refresh intervals/adaptive refresh, and failover depend on Lettuce/Jedis and specific configuration.

**Redis Cluster only supports database index 0 in standard Redis Cluster mode.** Do not set `spring.data.redis.database: 1` expecting `SELECT 1` to behave like standalone. Isolate data across apps/tenants via key prefixes and permissions, not logical DB indexes.

Other important constraints:

- Multi-key operations may require keys to belong to the **same hash slot**.
- Redis key hash tags `{...}` map related keys to the same slot when multi-key operations are genuinely needed.
- Lua scripts/transactions spanning multiple keys in different slots can fail.
- Cluster does not guarantee atomic transactions across a PostgreSQL database or message broker.
- Timeout settings must account for redirections, reconnects, and failovers; do not equate "one 2-second command" with the entire business request.

Example keys with a hash tag:

```text
order:{ord-1024}:status
order:{ord-1024}:attempts
```

These two keys typically hash to the same slot because of the portion inside curly braces. Do not overuse hash tags in ways that concentrate hot keys onto a single slot; understand the load distribution model.

## 12. Service Connections and Configuration Precedence

Locally, `spring-boot-docker-compose` or Spring Boot Testcontainers can create **`RedisConnectionDetails`** from a detected Redis container. When a connection details bean is present, auto-configuration may take endpoints/credentials from it **instead of certain `spring.data.redis.*` properties**.

Compose example:

```yaml
services:
  redis:
    image: redis:7
    ports:
      - "6379"
```

Docker may map container port 6379 to a random host port, such as 49170. Spring Boot detects the mapped port and provides connection details so the Redis client connects to the right host port.

**Confusing scenario:** you configured `spring.data.redis.host=localhost` and `port=6379`, yet the app connects to mapped port 49170. This can be **correct behavior** when Compose service connections take precedence.

Checklist when verifying:

1. Are Docker Compose/Testcontainers modules on the runtime classpath?
2. Is a `RedisConnectionDetails` bean present in the context?
3. Is a custom `RedisConnectionFactory` bean overriding auto-configuration?
4. Is the app running on the host or inside a container, and what is the mapped port?
5. Do tests and production use the same source of connection details?

Do not disable connection details just to force `localhost:6379` when Compose uses dynamic port mapping. Pick one clear mechanism per environment: local Compose, test containers, or production endpoints via secrets/config.

## 13. Spring Cache and RedisTemplate: Two Separate Configuration Layers

A common mistake is mixing namespaces:

- **`spring.data.redis.*`**: configures **Redis client connectivity**—host, port, username, password, TLS, connect timeout, command timeout, topology, pooling.
- **`spring.cache.redis.*`**: configures **cache behavior** of `RedisCacheManager` when Spring Cache uses Redis—TTL, null caching, key prefix, cache names, etc.

Example:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
  cache:
    type: redis
    redis:
      time-to-live: 5m
      cache-null-values: false
      use-key-prefix: true
```

`spring.data.redis.timeout: 3s` is **not** a three-second cache TTL. `spring.cache.redis.time-to-live: 5m` is **not** a Redis connection timeout.

Similarly, when calling `StringRedisTemplate.opsForValue().set(key, value, Duration.ofMinutes(5))`, the TTL comes from **your command**; it is not automatically inherited from `spring.cache.redis.time-to-live`. If using `RedisTemplate` with custom serializers, version keys/values and avoid deserializing untrusted data with dangerous serializers.

### 13.1. StringRedisTemplate Example with Explicit TTL

```java
import java.time.Duration;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class InventorySnapshotStore {

    private final StringRedisTemplate redis;

    public InventorySnapshotStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String sku, String json) {
        redis.opsForValue().set(
            "inventory:snapshot:v1:" + sku,
            json,
            Duration.ofMinutes(5)
        );
    }

    public String find(String sku) {
        return redis.opsForValue().get(
            "inventory:snapshot:v1:" + sku
        );
    }
}
```

In this example, `json` is a JSON payload serialized under the application's contract; validate and enforce size limits on write/read. A versioned key prefix avoids collisions when DTO structures change.

**On correctness:** a cached inventory snapshot can be stale. To reserve or place a real order, the owner service must verify inventory atomically inside an appropriate transaction/synchronization mechanism rather than trusting the cache alone.

## 14. Classifying Connection Errors and Recovery Policies

In an integration system, Redis errors must be distinguished by origin:

| Symptom | Common Cause | Appropriate Action |
| --- | --- | --- |
| Connection refused | Wrong host/port, server down, firewall | Verify endpoint, port mapping, network policy |
| Connect timeout | Network failed to establish connection in time | Check DNS, route, TLS, connection count, outage |
| Command/read timeout | Slow Redis, congested network, failover, heavy command | Check slowlog/latency, inspect pool and request deadline |
| NOAUTH / WRONGPASS | Missing/incorrect credentials | Check secrets/ACL; do not hot-loop retry infinitely |
| NOPERM | ACL forbids command/key | Fix permission policy; do not mask errors with fallback |
| TLS handshake error | CA/truststore/SNI/cert mismatch | Fix trust chain and endpoint; do not disable verification |
| Unexpected MOVED / ASK | Wrong cluster client/topology | Verify cluster-aware client and node reachability |
| READONLY | Writing to replica, failover, or stale topology | Check primary routing; bounded retry |
| Serialization failure | Incompatible DTO/serializer/schema | Lock schema/version, migrate or invalidate cache |
| Redis reachable but wrong business behavior | Key prefix, TTL, type, or command semantics | Verify contract and test against key patterns |

In Spring, exceptions may be translated into `DataAccessException` subtypes such as `RedisConnectionFailureException`, `QueryTimeoutException`, or client/library exceptions depending on the operation. Never write recovery logic by matching exception message strings alone.

### 14.1. A Redis Timeout Does Not Mean "The Command Did Not Run"

Consider:

```text
Client -> Redis: INCR notification:sent-counter
Redis executes increment
Network drops response
Client times out
```

Retrying the same command increments it again. For creating idempotency state, storing checkpoints, or emitting events, use a **stable business ID** and atomic conditional operations where appropriate. If state must be guaranteed across database and Redis, local DB transactions **do not automatically cover Redis**.

### 14.2. Cache Fallback and Fail-Open/Fail-Closed

If Redis is strictly a cache for non-sensitive read data, you may fall back to the DB/HTTP provider **with a concurrency limit** when Redis fails. However:

- Mass fallback can cause a cache stampede, taking down the authoritative data source.
- Redis used for idempotency, rate limiting, or distributed locks is no longer an optional cache; failing open can cause duplicate side effects or quota bypasses.
- Authorization data, critical pricing, or inventory require explicit stale-data policies.
- Retries need budgets, backoff, and circuit breakers; never retry errors caused by wrong ACLs or broken TLS.

## 15. Testing Connections, Timeouts, and Errors Against Real Redis

Unit testing a repository with a mocked `StringRedisTemplate` checks method invocations, but **does not test connections, serializers, TLS, Redis command semantics, or timeouts**. For configuration lessons, add integration tests against real Redis in a controlled environment.

### 15.1. Redis with Testcontainers and DynamicPropertySource

Example using JUnit 5, Spring Boot Test, and Testcontainers; the project needs `org.testcontainers:junit-jupiter` and compatible Spring Boot dependencies.

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@Testcontainers
@SpringBootTest
class RedisConnectionIntegrationTest {

    @Container
    static GenericContainer<?> redis =
        new GenericContainer<>(DockerImageName.parse("redis:7.2"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> redis.getMappedPort(6379)
        );
        registry.add("spring.data.redis.connect-timeout", () -> "1s");
        registry.add("spring.data.redis.timeout", () -> "2s");
    }

    @Autowired
    StringRedisTemplate template;

    @Test
    void writesAndReadsValueWithTtl() {
        String key = "test:redis:configuration:sku-123";

        template.opsForValue().set(key, "available", Duration.ofSeconds(30));

        assertThat(template.opsForValue().get(key))
            .isEqualTo("available");

        Long ttl = template.getExpire(key);
        assertThat(ttl).isNotNull();
        assertThat(ttl).isPositive();
    }
}
```

**Test prerequisites:** Docker daemon is running, the test Redis image can be pulled, the Redis starter is on the classpath, and no custom connection factory/`RedisConnectionDetails` overrides these properties. If the app uses a service connection from Compose or another Testcontainers bean, ensure there are no conflicting endpoint sources.

Use a dedicated namespace and short TTLs to avoid interfering with other tests. This test verifies real I/O and TTL; it **does not automatically test timeouts** during Redis network loss.

### 15.2. Designing Timeout and Failover Tests

Key test groups:

1. **Wrong host/port**: finite connect timeout, classified exception, no indefinite hang.
2. **Slow command/stalled Redis**: command timeout takes effect, retry count obeys policy.
3. **Redis restart**: client reconnects, in-flight requests report clear errors, controlled recovery.
4. **Wrong credentials/ACL**: no infinite fallback or retries masking security failures.
5. **TLS trust failure**: application fails clearly without disabling certificate verification.
6. **Redis Cluster failover/MOVED**: client discovers new topology; key routing stays correct.
7. **Sentinel switch-over**: discovers new primary and preserves business semantics.
8. **Multiple instances**: connection limits, pool saturation, and shared cache invalidation.
9. **Timeout after successful write**: operations with side effects are not unintentionally duplicated.

Tools like Toxiproxy or other network fault-injection utilities can introduce controlled timeouts in integration tests. Do not use arbitrary `Thread.sleep` calls to measure timeouts or deliberately take down production Redis in automated tests.

### 15.3. Verifying Version-Appropriate Properties

When upgrading from Boot 2.x to 3.x, write an application context test asserting that `RedisConnectionFactory` has the expected type, endpoint, and timeouts. Do not rely on `application.yml` "looking valid": properties with outdated prefixes can be silently ignored, causing the client to fall back to default `localhost:6379`.

## 16. Observability, Security, and Real-World Operations

To verify configuration in action, inspect:

- **Startup/conditions**: whether the app uses `LettuceConnectionFactory` or `JedisConnectionFactory`; whether custom beans or `RedisConnectionDetails` exist.
- **Redis client**: command/connection latency, timeouts, error rates, pool wait and active connections if instrumented.
- **Redis server**: memory usage, evictions, connected clients, command latency, slowlog, failover, and replication health.
- **Spring Cache**: hit/miss ratio, TTL, cache key cardinality, stale entries; inspect metrics specific to the provider.
- **Business flows**: request p95/p99, consumer lag, retry count, duplicate event count, fallback count, and stuck jobs.

When using Spring Boot Actuator, a Redis health indicator and metrics can be available with proper dependencies and configuration. A Redis health check reporting "UP" only proves the configured probe/connection succeeded; it does not guarantee all key schemas, ACLs, or business commands are correct.

### 16.1. Checklist When the App Cannot Connect to Redis

1. **Verify where the app runs**: host, Docker Compose container, or Kubernetes.
2. **Check the resolved endpoint**: URL, host/port, Sentinel/Cluster, service connection precedence.
3. **Inspect the actual Redis instance**: listening port, DNS, firewall, TLS/ACL.
4. **Verify client implementation**: Lettuce/Jedis and compatible versions.
5. **Compare connect timeout, command timeout, and HTTP/message flow deadlines**.
6. **Inspect pooling and instance count**: total connections, queue wait, thread saturation.
7. **Classify the error**: transport, auth, ACL, TLS, serialization, topology, wrong database.
8. **Assess business impact**: idempotency, stale cache, retries, and DB/broker state.

Avoid logging passwords, full Redis URLs with credentials, access tokens, raw payloads containing PII, or cache keys containing sensitive info. For metric labels, never use arbitrary Redis keys as labels because cardinality explodes quickly.

### 16.2. Explicit Profiles per Environment

```yaml
# application-dev.yml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 1s
      timeout: 2s
```

```yaml
# application-prod.yml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6380}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      connect-timeout: 2s
      timeout: 3s
```

The snippets above **illustrate two separate configuration files**, not a recommendation to combine them in a single unprofiled YAML file. In managed Redis deployments, different URLs, Cluster/Sentinel settings, SSL bundles, and timeouts may be needed; check the provider's operational contract.

## 17. End-to-End Scenario: Redis in an Order → DB → Event Flow

Suppose Order Service receives an HTTP request, reads an inventory snapshot from Redis, writes the order in PostgreSQL, and emits `OrderCreated` via a broker:

```mermaid
flowchart TD
    A["POST /orders"] --> B["Read Redis snapshot"]
    B --> C["Business check in owner service"]
    C --> D["DB transaction: order + outbox"]
    D --> E["Outbox publisher"]
    E --> F[("Broker")]
    F --> G["Consumer inbox / idempotency"]
    G --> H["Redis cache invalidation (when appropriate)"]
```

An initial production configuration might look like:

```yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT:6380}
      username: ${REDIS_USERNAME}
      password: ${REDIS_PASSWORD}
      ssl:
        enabled: true
      client-type: lettuce
      connect-timeout: 2s
      timeout: 3s
  cache:
    type: redis
    redis:
      time-to-live: 2m
      cache-null-values: false
```

**Error paths to specify explicitly:**

- Redis timeout reading snapshot: may fall back to the source of truth if policy allows; never default to "inventory = 0" for every error.
- Redis timeout after writing idempotency state: verify whether the command executed and use idempotent keys/operations where possible.
- PostgreSQL commits but broker publish fails: outbox allows retries without publishing events from uncommitted transactions.
- Consumer receives duplicate event: inbox/deduplication prevents duplicate processing.
- Redis failover or key schema change during rolling deploy: test connections, serializers, and business-level consistency conditions.

### Pre-Deployment Checklist

- [ ] Using the right `spring-boot-starter-data-redis` version with a real Redis server?
- [ ] Selected standalone/URL, Sentinel, or Cluster properly without arbitrarily mixing topologies?
- [ ] Host/port match where the app runs, including Docker mapped ports/Service Connections?
- [ ] Credentials/ACL/TLS securely managed and authentication failures tested?
- [ ] `connect-timeout`, `timeout`, and end-to-end deadlines configured; fault injection tested?
- [ ] Determined Lettuce/Jedis, pooling needs, and total connection limits?
- [ ] Not confusing `spring.data.redis.timeout` with `spring.cache.redis.time-to-live`?
- [ ] Key namespace, TTL, serializer, schema version, and per-tenant permissions clearly defined?
- [ ] Retries do not turn non-idempotent commands into duplicate side effects?
- [ ] Tests cover real Redis, reconnect/failover, logging/metrics, and outage handling plans?

**Conclusion:** `spring.data.redis.*` is the primary configuration namespace for Spring Boot to construct Redis connections: endpoints, ACL credentials, TLS, client, topology, and timeouts. **`connect-timeout`** bounds connection establishment, while **`timeout`** governs command waiting per client; neither is an end-to-end SLA or a cache TTL. In a Spring Boot integration flow, combine this configuration with data contract management, cache invalidation, transactions, retry/idempotency, real-Redis testing, and error observability so Redis improves performance without compromising business correctness.
