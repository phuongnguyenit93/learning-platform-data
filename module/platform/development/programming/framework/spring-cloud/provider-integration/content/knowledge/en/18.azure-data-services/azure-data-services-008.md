# Integrating Redis via Spring Data and Inspecting Service Lifecycle

Redis is commonly used as a distributed cache, session store, counter store, rate limiter, and lightweight queue. In Spring Boot, **Spring Data Redis** provides `RedisTemplate`, repositories, and Spring Cache integration; **Lettuce** is the popular default Redis client thanks to its synchronous, asynchronous, reactive, and Redis Cluster support. On Azure, applications may encounter two service lines: **Azure Cache for Redis** (the legacy service on a retirement path) and **Azure Managed Redis** (the new strategic service built on Redis Enterprise).

Integration must account for two lifecycles: the **application/client lifecycle** (initializing the connection factory, authenticating, refreshing tokens, reconnecting, and shutting down) and the **Redis service lifecycle** (provisioning, TTL/eviction, scaling, failover, backup, migration, and retirement). An application that starts after configuring host/password is still unsafe for production if tokens expire, the service fails over, or entries are evicted.

This lesson belongs to the **Azure Data Services** chapter of the **SPRING_CLOUD_PROVIDER_INTEGRATION** module. The module covers practical integration of Spring Boot with managed services across AWS, Azure, and Google Cloud via their respective Spring Cloud libraries, including identity/permission configuration, storage, messaging, data, secrets, integration testing, and evaluating differences between cloud providers. This lesson focuses on Spring Data Redis, Lettuce, and the operational lifecycle of Azure Redis.

## 1. Learning Outcomes

After this lesson, you will be able to:

- Distinguish Azure Cache for Redis and Azure Managed Redis, and understand the retirement/migration roadmap.
- Explain the roles of Spring Data Redis, `RedisConnectionFactory`, Lettuce, `RedisTemplate`, repositories, and `RedisCacheManager`.
- Configure the Spring Cloud Azure Redis starter for Azure Cache for Redis per documented support.
- Connect to Azure Managed Redis using Lettuce and Microsoft Entra ID via `redis-authx-entraid`.
- Integrate a refreshing credential provider into Spring Data Redis via Lettuce connection configuration.
- Choose a Redis Cluster or single-endpoint client based on Azure Managed Redis clustering policy.
- Use `@Cacheable`, `@CachePut`, `@CacheEvict`, TTL, and cache-aside properly.
- Manage serializers, key prefixes, eviction, cache invalidation, and cache stampedes.
- Understand the lifecycle of `LettuceConnectionFactory`, token providers, connections, failover, and shutdown.
- Design readiness/health checks, retries, timeouts, backups, geo-replication, and migrations.

## 2. Azure Redis: Choosing the Right Service

### 2.1. Azure Cache for Redis vs. Azure Managed Redis

| Criterion | Azure Cache for Redis | Azure Managed Redis |
| --- | --- | --- |
| Architecture | Based on Redis community edition in Basic/Standard/Premium tiers; Enterprise has its own architecture | Built on Redis Enterprise, running multiple shards across nodes |
| Current role | Legacy service on a retirement path | Recommended strategic service for new workloads |
| Spring integration | Microsoft provides Spring Cloud Azure starter `spring-cloud-azure-starter-data-redis-lettuce` | Spring Data Redis/Lettuce connects over Redis protocol; Entra uses `redis-authx-entraid` |
| Entra authentication | Supported depending on SKU/configuration; starter has passwordless property | Enabled by default for new caches; access key authentication disabled by default |
| Endpoint/port | Depends on SKU; commonly 6380 or 10000 | FQDN of the form `<dns>.<region>.redis.azure.net`, port 10000 |
| Clustering | Depends on SKU/tier | Choose OSS, Enterprise, or Non-clustered policy at provisioning |
| Lifecycle | Basic/Standard/Premium and Enterprise have different retirement dates | Newer service; some tiers/features may still be in preview |

Never use the generic name "Azure Redis" as if both services shared identical hostnames, ports, clustering, authentication, and starters. Check the exact SKU, endpoint, and guidance for the right service before configuring Spring.

### 2.2. Azure Cache for Redis Retirement Roadmap

Microsoft has announced retirement for all Azure Cache for Redis SKUs. According to the July 2026 schedule for **Azure public cloud**:

| SKU | Key Milestones |
| --- | --- |
| Enterprise and Enterprise Flash | New cache creation blocked starting 2026-04-01; service retires on 2027-03-31, with migration of remaining instances to Azure Managed Redis beginning 2027-04-01 |
| Basic, Standard, Premium | New creation blocked for new tenants/customers starting 2026-04-01; eligible existing tenants can keep creating until retirement; full cache retirement on 2028-09-30 |

A tenant counts as existing if at least one subscription in the tenant had an Azure Cache for Redis before 2026-04-01. Schedules for Azure Government and Azure operated by 21Vianet differ; check FAQs/What's New if deploying to sovereign clouds.

For new applications, prioritize evaluating Azure Managed Redis. For existing systems running Azure Cache for Redis, plan migration, compatibility testing, benchmarking, and cutover well ahead of retirement dates. Do not wait until the service shuts down to begin.

## 3. Spring Data Redis Architecture

Spring Data Redis decouples business logic from the underlying Redis client and wire protocol:

~~~mermaid
flowchart LR
    A[Application service] --> B[Spring Cache / RedisTemplate / Repository]
    B --> C[RedisConnectionFactory]
    C --> D[Lettuce client]
    D --> E[TLS + Redis protocol]
    E --> F[Azure Cache for Redis / Azure Managed Redis]
    G[Microsoft Entra token provider] -. credentials / refresh .-> D
    H[Spring ApplicationContext] -. bean lifecycle .-> C
~~~

- **Spring Cache abstraction:** provides `@Cacheable`, `@CachePut`, and `@CacheEvict`; business code avoids writing boilerplate GET/SET logic for every method.
- **`RedisTemplate`/`StringRedisTemplate`:** executes Redis commands directly across values, hashes, lists, sets, sorted sets, streams, and pub/sub.
- **Spring Data Redis repositories:** map objects to Redis hashes/keyspaces with `@RedisHash` and `CrudRepository`.
- **`RedisConnectionFactory`:** supplies connections to Spring Data. With Lettuce, the implementation is `LettuceConnectionFactory`.
- **Lettuce:** manages Redis clients, connections, cluster topology, reconnection, command timeouts, and credential providers.
- **Azure Redis:** manages nodes/shards, replication, failover, maintenance, and service limits.

An application can use Spring Cache and `RedisTemplate` side by side, provided it standardizes key namespaces, serializers, TTLs, and invalidation rules so access paths do not overwrite or misread each other's data.

## 4. Adding Dependencies and Managing BOMs

With Spring Cloud Azure, Microsoft provides the starter:

`com.azure.spring:spring-cloud-azure-starter-data-redis-lettuce`

Maven example for Spring Data Redis with Azure Cache for Redis:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-data-redis-lettuce</artifactId>
    </dependency>
</dependencies>
~~~

The Azure Redis starter is documented in Microsoft's Spring guide for **Azure Cache for Redis**. Do not assume this starter automatically supplies every Azure Managed Redis/Redis Enterprise clustering option and Entra token refresh configuration. For Azure Managed Redis, this lesson uses Spring Data Redis/Lettuce with Redis's credential provider.

Pick the Spring Cloud Azure BOM matching your Spring Boot line. Current documentation spans 4.x/5.x/6.x/7.x branches; do not mix individual versions of Spring Data Redis, Lettuce, and the Azure starter. Check the [Spring Cloud Azure version mapping](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview) before pinning dependencies.

For Azure Managed Redis via Entra, add the library:

~~~xml
<dependency>
    <groupId>redis.clients.authentication</groupId>
    <artifactId>redis-authx-entraid</artifactId>
    <version>${redis-authx-entraid.version}</version>
</dependency>
~~~

Lettuce requires a version supporting Entra/streaming credentials (Lettuce 6.6+); the new `CredentialsProvider` API and Spring Data compatibility adapter were introduced in the Lettuce 7.9 line. Verify compatibility across Spring Boot, Spring Data Redis, Lettuce, and `redis-authx-entraid` in your actual dependency tree.

## 5. Configuring Azure Cache for Redis with Spring Cloud Azure

### 5.1. Entra Passwordless

For Azure Cache for Redis SKUs/endpoints supporting Entra, the Spring Cloud Azure starter provides passwordless properties. Example:

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT}
      username: ${REDIS_ENTRA_USERNAME}
      ssl:
        enabled: true
      azure:
        passwordless-enabled: true
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        # Declare only when using a user-assigned identity:
        client-id: ${AZURE_CLIENT_ID}
~~~

`REDIS_HOST`, `REDIS_PORT`, and `REDIS_ENTRA_USERNAME` come from your cache resource/Redis user setup. For Azure Cache for Redis, the port may be 6380 or 10000 depending on SKU/deployment. Never copy a port from another environment without checking the portal.

Managed Identity enables the app to acquire tokens; the principal must still be added to the Redis authentication/authorization configuration. Entra authentication works only over SSL/TLS. Never disable TLS to fix authentication failures.

### 5.2. Access Key/Password Authentication

If legacy systems have not yet migrated to Entra, access keys can be used per SKU configuration:

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST}
      port: ${REDIS_PORT}
      password: ${REDIS_ACCESS_KEY}
      ssl:
        enabled: true
~~~

Access keys are secrets; store them in Key Vault/secret manager and never commit them to `application.yml`, images, or logs. Plan key rotation and migrate to Entra where supported by the service/app. Toggling authentication or rotating keys can drop existing connections; test reconnection before rolling out.

## 6. Azure Managed Redis with Microsoft Entra and Lettuce

### 6.1. Provisioning and Endpoint

When provisioning Azure Managed Redis, choose:

- Region and tier matching latency, capacity, CPU, and workload requirements.
- High availability/zone redundancy as required.
- **Clustering policy**: OSS, Enterprise, or Non-clustered.
- Required Redis modules (such as RediSearch) at provisioning time; modules cannot be added after cache creation.
- Active geo-replication at creation time if the architecture needs replication groups; caches created without active geo-replication cannot normally join a group later.
- Private access/networking and authentication.

New caches enable Microsoft Entra ID by default and disable access key authentication by default. Hostnames take the form:

`<dns-name>.<azure-region>.redis.azure.net`

The client port is **10000**. Use the Azure-configured FQDN, TLS, and network path; never hard-code IPs or shard ports.

### 6.2. Clustering Policy Dictates the Client

Azure Managed Redis runs a sharded Redis Enterprise architecture; the clustering policy controls how clients see topology:

| Policy | Client Model | When to Choose |
| --- | --- | --- |
| **Enterprise** | Single endpoint/proxy; client uses standalone Redis API | Want a simpler client interface; proxy handles internal routing |
| **OSS** | Redis Cluster API; client discovers shards and follows redirects | Want clients connecting directly to shards via cluster-aware Lettuce |
| **Non-clustered** | Single endpoint, no sharding; limited to smaller caches per service caps | Small workloads needing single-process semantics |

Choose OSS vs. Enterprise at provisioning time because switching policies later generally requires deleting and recreating the cache; Non-clustered supports scaling to clustered under certain conditions. With OSS, the client must support the Redis Cluster API. With Enterprise/Non-clustered, use a standalone client. Never use `RedisClusterConfiguration` against an Enterprise endpoint merely because the product is built on Redis Enterprise.

When using OSS cluster mode, multi-key commands must respect hash slots; keys operated on together atomically should share consistent hash tags, such as `order:{tenant-42}:header` and `order:{tenant-42}:lines`. Never hard-code discovered shard ports; the service can change topology.

### 6.3. Creating an Entra Credential Provider

Azure Managed Redis uses token audience `https://redis.azure.com/.default`. The `redis-authx-entraid` library acquires and refreshes tokens for Lettuce. Example for system-assigned Managed Identity:

~~~java
import java.util.Set;
import redis.clients.authentication.core.TokenBasedRedisCredentialsProvider;
import redis.clients.authentication.entraid.EntraIDTokenAuthConfigBuilder;

public TokenBasedRedisCredentialsProvider createRedisCredentials() {
    try (EntraIDTokenAuthConfigBuilder builder =
            EntraIDTokenAuthConfigBuilder.builder()) {
        builder.systemAssignedManagedIdentity();
        builder.scopes(Set.of("https://redis.azure.com/.default"));
        return TokenBasedRedisCredentialsProvider.create(builder.build());
    }
}
~~~

For user-assigned Managed Identity, configure `userAssignedManagedIdentity` with the appropriate identifier type (client ID, object ID, or resource ID) per your library version. Service principals are also supported; if using a client secret, fetch it from Key Vault/secret provider instead of source code.

In the Azure portal, add the corresponding user/service principal to the Redis users list. By default, principals may receive broad command/key permissions; use custom data access permissions where supported by features and policy to restrict commands/keys. Azure Managed Redis does not currently support Entra groups per current docs, so do not assume group assignment substitutes for adding the principal directly.

When changing Access Keys Authentication settings (e.g., disabling keys after migrating to Entra), Azure Managed Redis may **close all existing connections**, including connections already using Entra. Afterward, clients must reconnect and re-authenticate; perform rolling changes with monitoring rather than flipping all caches/apps simultaneously.

### 6.4. Integrating the Credential Provider into Spring Data Redis

Spring Cloud Azure currently documents a dedicated Redis starter for Azure Cache for Redis; for Azure Managed Redis, the Java path documented by Microsoft/Redis uses `redis-authx-entraid` with Lettuce. Spring Data Redis lets you configure `RedisCredentialsProviderFactory` on `LettuceClientConfiguration`. With Lettuce 7.9+, you can adapt the new `CredentialsProvider` to the SPI expected by Spring Data Redis via `RedisCredentialsProvider.adapt(...)`.

The example below demonstrates Azure Managed Redis with the **OSS clustering policy**:

~~~java
import java.util.List;
import java.util.Set;
import io.lettuce.core.ClientOptions;
import io.lettuce.core.RedisCredentialsProvider;
import io.lettuce.core.cluster.ClusterClientOptions;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisClusterConfiguration;
import org.springframework.data.redis.connection.RedisConfiguration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.connection.lettuce.RedisCredentialsProviderFactory;
import redis.clients.authentication.core.TokenBasedRedisCredentialsProvider;
import redis.clients.authentication.entraid.EntraIDTokenAuthConfigBuilder;

@Configuration(proxyBeanMethods = false)
public class ManagedRedisConfiguration {

    @Bean(destroyMethod = "close")
    TokenBasedRedisCredentialsProvider redisCredentialsProvider() {
        try (EntraIDTokenAuthConfigBuilder builder =
                EntraIDTokenAuthConfigBuilder.builder()) {
            builder.systemAssignedManagedIdentity();
            builder.scopes(Set.of("https://redis.azure.com/.default"));
            return TokenBasedRedisCredentialsProvider.create(builder.build());
        }
    }

    @Bean
    RedisConnectionFactory redisConnectionFactory(
            TokenBasedRedisCredentialsProvider credentialsProvider) {

        RedisClusterConfiguration cluster =
            new RedisClusterConfiguration(
                List.of(System.getenv("REDIS_HOST") + ":10000"));

        ClusterClientOptions clientOptions = ClusterClientOptions.builder()
            .reauthenticateBehavior(
                ClientOptions.ReauthenticateBehavior.ON_NEW_CREDENTIALS)
            .build();

        LettuceClientConfiguration clientConfiguration =
            LettuceClientConfiguration.builder()
                .useSsl()
                .clientOptions(clientOptions)
                .redisCredentialsProviderFactory(
                    new RedisCredentialsProviderFactory() {
                        @Override
                        public RedisCredentialsProvider createCredentialsProvider(
                                RedisConfiguration configuration) {
                            return RedisCredentialsProvider.adapt(
                                credentialsProvider);
                        }
                    })
                .build();

        return new LettuceConnectionFactory(cluster, clientConfiguration);
    }
}
~~~

The `redisCredentialsProvider()` bean creates the provider and lets Spring close it when the `ApplicationContext` shuts down. For Enterprise or Non-clustered policies, replace `RedisClusterConfiguration` with `RedisStandaloneConfiguration(host, 10000)` and use appropriate `ClientOptions`. This example requires Spring Data Redis/Lettuce versions exposing `redisCredentialsProviderFactory`, `CredentialsProvider`, and `RedisCredentialsProvider.adapt`; if your current BOM lacks them, upgrade cohesively or use the verified client integration for that version.

Avoid simultaneously letting Spring Boot auto-configuration create another `RedisConnectionFactory` configured with access keys. When defining custom beans, verify that `RedisTemplate`, `RedisCacheManager`, and repositories all use the single intended connection factory.

## 7. Using `RedisTemplate` and Spring Data Repositories

### 7.1. `StringRedisTemplate`

`StringRedisTemplate` fits when keys/values are strings or pre-serialized JSON:

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class SessionStore {
    private final StringRedisTemplate redis;

    public SessionStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String sessionId, String json) {
        redis.opsForValue().set(
            "session:" + sessionId,
            json,
            Duration.ofMinutes(30));
    }

    public String find(String sessionId) {
        return redis.opsForValue().get("session:" + sessionId);
    }

    public Boolean delete(String sessionId) {
        return redis.delete("session:" + sessionId);
    }
}
~~~

The 30-minute TTL is applied atomically in `SET`; keys expire automatically unless renewed. Never store sensitive session data in plain text if encryption/minimization is required. Never log JSON payloads or session tokens.

### 7.2. `RedisTemplate` for Objects

When storing objects, configure serializers explicitly:

- Stable key serializer, typically `StringRedisSerializer`.
- Value serializer using a versioned JSON schema or format compatible across service releases.
- Never rely on default Java native serialization for data shared across services/versions.
- Avoid enabling unrestricted polymorphic default typing; allow-list deserializable types only.

Changing a Java class does not automatically migrate existing data in Redis. During schema changes, use version fields/namespaces or temporary dual-read transitions.

### 7.3. Spring Data Redis Repositories

Spring Data Redis can map entities into Redis hashes:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "customer-session", timeToLive = 1800)
public class CustomerSession {
    @Id
    private String id;
    private String customerId;
    private String state;

    public CustomerSession() {}
}
~~~

Repository:

~~~java
import org.springframework.data.repository.CrudRepository;

public interface CustomerSessionRepository
        extends CrudRepository<CustomerSession, String> {
}
~~~

`timeToLive = 1800` sets the lifetime in seconds. Repositories support CRUD and derived queries over indexed/supported properties; do not treat Redis repositories like a relational database with arbitrary joins and transactions. Design keyspaces and indexes around access patterns, and avoid scanning entire keyspaces on the request path.

## 8. Spring Cache Abstraction with Redis

### 8.1. Annotation-Based Cache-Aside

Spring Cache checks the cache before executing a method. A cache hit returns the cached value; a cache miss invokes the method and stores the result:

~~~java
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {
    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "productById", key = "#id")
    public ProductView findById(String id) {
        return repository.findViewById(id);
    }

    @CachePut(cacheNames = "productById", key = "#result.id")
    public ProductView update(ProductCommand command) {
        return repository.update(command);
    }

    @CacheEvict(cacheNames = "productById", key = "#id")
    public void delete(String id) {
        repository.deleteById(id);
    }
}
~~~

This example assumes `ProductRepository`, `ProductView`, and `ProductCommand` are application types. `@Cacheable` does not make the cache the system of record. If Redis becomes temporarily unavailable, the service must provide fallback or degraded behavior per requirements; cache-aside normally reads from the source database on cache misses.

### 8.2. Configuring `RedisCacheManager` and TTL

~~~java
import java.time.Duration;
import java.util.Map;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class RedisCachingConfiguration {

    @Bean
    CacheManager cacheManager(RedisConnectionFactory connectionFactory) {
        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(5))
                .disableCachingNullValues()
                .computePrefixWith(
                    cacheName -> "provider-integration:" + cacheName + "::");

        return RedisCacheManager.builder(connectionFactory)
            .cacheDefaults(defaults)
            .withInitialCacheConfigurations(Map.of(
                "productById", defaults.entryTtl(Duration.ofMinutes(10)),
                "productSearch", defaults.entryTtl(Duration.ofMinutes(2))))
            .build();
    }
}
~~~

This sets a default 5-minute TTL, 10 minutes for product details, and 2 minutes for search results. Choose TTLs based on stale-data tolerance and source mutation rates; never apply one TTL across all caches when lifecycles differ.

Without a TTL, cache entries can persist indefinitely until deleted or evicted. Set explicit TTLs on reconstructible data alongside invalidation policies; retain non-expiring keys only with an operational justification and proper memory limits. `RedisCacheManager` uses a non-locking writer by default; `putIfAbsent` and `clean` may execute multiple commands and are not atomic by default. A locking writer reduces overlapping cache writes at the cost of extra requests and contention.

Spring Data Redis prefixes cache keys with the cache name by default, yet configuring a custom prefix prevents key collisions across apps/environments. The default value serializer may use Java serialization; configure a schema-appropriate serializer instead of treating the default as a long-term data contract.

### 8.3. TTL and TTI Are Not the Same

- **TTL (time-to-live):** counts down from the last creation/write. Reading the key does not reset TTL.
- **TTI (time-to-idle):** counts down from the last access. Redis has no native TTI, though Spring Data Redis can emulate it using `GETEX` on reads.

TTI-like behavior requires Redis 6.2+ and configuring `enableTimeToIdle()` alongside a TTL. Every read/write path must use expiration-aware commands; if `@Cacheable` reads via the cache abstraction while other code reads the same key via `RedisTemplate`/repository using plain `GET`, those reads do not reset TTL. Never mix both access patterns while expecting consistent TTI.

## 9. Key Design, Serialization, and Invalidation

A cache key should include namespace, data type, and parameters affecting the result:

`<application>:<environment>:<cache-name>:<entity-id-or-query-hash>`

Examples:

- `catalog:prod:productById:SKU-1001`
- `catalog:prod:search:sha256(filter+sort+page)`
- `orders:prod:session:session-abc`

Never put access tokens, emails/PII, or secrets into keys. With Redis Cluster, multiple keys used together in a multi-key command must share the same hash slot; hash tags such as `{tenant-42}` group related keys together.

### 9.1. Cache Invalidation

When source data changes, pick a consistent rule:

- `@CachePut` refreshes the cache with the new result.
- `@CacheEvict` deletes the key so the next read fetches from source.
- Events/outbox emit invalidations when updates originate in another service.
- TTL bounds the staleness window if invalidation events arrive late or drop.

If the database commits while the Redis update fails, cached data can become stale. Prefer deleting keys post-commit, emitting invalidations via outbox, or embedding versions in keys to avoid serving stale entries. Never treat a Redis command and a database transaction as atomic.

### 9.2. Cache Stampedes and Thundering Herds

When a hot key's TTL expires, many concurrent requests can hit the database at once. Mitigations:

- Jittered TTLs so keys do not expire simultaneously.
- Single-flight/request coalescing per key.
- Bounded warm-up for popular entries.
- Stale-while-revalidate when business rules permit stale responses.
- Rate limits or bulkheads to protect the source database.

Avoid distributed locks on every cache miss unless truly necessary; locks introduce contention and require handling owner crashes and lease expiration. When using locks, enforce ownership tokens and safe release.

## 10. Redis Commands and Service Limits

Redis protocol compatibility does not mean every command is permitted by Azure Managed Redis. Certain administrative/cluster-topology commands are blocked because Azure manages infrastructure. Check the supported commands list for your exact service and clustering policy.

- Avoid `KEYS *` on large keyspaces; use `SCAN` with appropriate cursors and batch sizes.
- For large caches, configure the Spring Data Redis writer with a `SCAN` strategy where supported by driver/mode. Spring Data Redis may default to `KEYS` + `DEL` when clearing caches.
- With OSS clustering, clients must follow redirects/discovery; never issue commands altering cluster topology.
- Multi-key commands in cluster mode may require keys in the same hash slot.
- Pub/Sub is not a durable queue; if consumers are offline, messages are not retained for replay like a broker.
- Redis transactions/Lua scripts have server and cluster-slot constraints; never assume multi-key transactions across shards are atomic.

## 11. Application and Redis Client Lifecycle

### 11.1. `LettuceConnectionFactory` Lifecycle

Spring Data Redis's `LettuceConnectionFactory` implements `InitializingBean`, `SmartLifecycle`, and `DisposableBean`. Spring initializes and starts the factory within the `ApplicationContext`; on context shutdown, the factory closes clients/connections per lifecycle hooks. It typically shares a native thread-safe connection for normal operations; Spring's `LettuceConnection` wrapper itself should not be shared across threads.

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Initialized: afterPropertiesSet
    Initialized --> Started: ApplicationContext lifecycle
    Started --> Reconnecting: socket failure / failover
    Reconnecting --> Started: reconnect succeeds
    Reconnecting --> Degraded: retry budget exhausted
    Degraded --> Reconnecting: recovery / backoff
    Started --> Stopping: context shutdown
    Degraded --> Stopping: context shutdown
    Stopping --> Destroyed: close client/resources
    Destroyed --> [*]
~~~

Never instantiate a Lettuce client or connection factory per request. Use Spring-managed singleton beans; avoid sharing `LettuceConnection` objects across threads. For blocking/transactional/pub-sub operations, check dedicated connection rules in Spring Data Redis/Lettuce.

### 11.2. Token Provider Lifecycle

Entra tokens expire. Azure Managed Redis requires clients to refresh tokens periodically and send `AUTH` with the new token before the old one expires; Microsoft recommends sending refreshed tokens at least 3 minutes before expiry with jitter so clients do not refresh simultaneously.

Lettuce + `redis-authx-entraid` provides a streaming token provider and automatic re-authentication when new credentials arrive if `ReauthenticateBehavior.ON_NEW_CREDENTIALS` is enabled. Lettuce does not manage the lifecycle of `TokenBasedRedisCredentialsProvider` itself; the application must close the provider on shutdown. In the Spring example, declaring the bean with `destroyMethod = "close"` lets Spring close it when the context stops.

Never fetch a token once at startup and reuse it as a static long-lived password. Never log tokens or place tokens in `application.yml`.

### 11.3. Startup, Readiness, and Shutdown

- Startup can verify DNS, TLS, authentication, and a lightweight `PING`.
- Readiness should reflect whether the app can serve Redis-dependent traffic; avoid tying liveness to Redis so an orchestrator does not crash-loop pods during transient cache outages.
- Shutdown should stop accepting traffic, drain in-flight requests within deadlines, and close subscriptions/connection factories and token providers.
- Never call `FLUSHALL` or wipe the entire cache on application restart.
- If caching is optional for request handling, design a degraded mode rather than failing startup solely because Redis is temporarily unavailable.

## 12. Azure Managed Redis Service Lifecycle

### 12.1. Provisioning and Immutable Settings

Several decisions lock in at cache creation time:

- OSS vs. Enterprise clustering policy; changing policies typically requires recreating the cache.
- Redis modules; modules cannot be added after creation.
- Active geo-replication; must be enabled during provisioning to participate in a replication group.
- Region/tier/capacity, HA/zone redundancy, and network exposure.

Choosing the wrong clustering policy can cause a standalone Spring Data client to fail against an OSS cluster cache or vice versa. Choosing the wrong modules can force provisioning a new instance and migrating data.

### 12.2. Scaling, Maintenance, and Failover

Azure Managed Redis distributes primary/replica shards across nodes. With HA enabled, the service manages replicas, health monitoring, and failover within the cache/availability zone scope. Planned failovers during maintenance/scaling typically finish quickly; unplanned failovers can take longer and drop active connections.

Per service guidance, planned failovers typically take under 1 second; unplanned failovers typically take 10–15 seconds due to failure detection and verification. These are reference figures, not per-request SLAs.

Applications may observe:

- Connection resets, socket errors, or timeouts.
- Commands sent without receiving a response before failover hit.
- Old connections rejected until reconnection succeeds.
- Elevated latency during replica promotion and data sync.

Lettuce has built-in reconnection behavior, but never assume every command executes exactly once. If a write times out, the outcome is ambiguous; retrying `INCR`, `LPUSH`, or similar side effects can create duplicates. Use operation IDs/idempotency or inspect state before retrying.

### 12.3. Region Failover and Active Geo-Replication

HA/zone redundancy handles node/zone failures within one region. **Region-wide failover** is an application architecture responsibility:

- Without active geo-replication, there is no automatic regional failover to a cache in another region.
- With active geo-replication, the app must monitor health/replication metrics, decide when to shift traffic, and route to the healthy regional cache.
- When the impaired region recovers, the service resynchronizes data; applications must verify health before shifting traffic back.
- Test firewalls, DNS, routing, failover, and recovery procedures.

Active geo-replication replicates Redis cache state; it does not replace backups/restores and does not guarantee multi-region business consistency across workflows.

### 12.4. Persistence, Backups, and Eviction

Redis is typically used as a reconstructible cache, though Azure Managed Redis offers persistence/import-export features depending on tier/support. Distinguish:

- **Replication/HA:** protects against certain node/zone failures.
- **Persistence:** writes snapshots/data to storage per config to recover a cache instance in supported scenarios.
- **Export/import backups:** creates backup artifacts to restore the same or another instance per service capabilities.
- **Eviction policy:** determines which keys are evicted when hitting memory limits.

Persistence does not protect against logic bugs, accidental deletes, or corruption; backups/exports require separate schedules and restore drills. If data is a system of record, store it in an appropriate database and treat Redis as a reconstructible copy.

## 13. Resilient Connections: Retries, Timeouts, and Keepalives

Azure Managed Redis recommends retrying commands with exponential backoff, bounding retry budgets, and setting sensible connect/command timeouts. Principles:

1. Initial connect timeout of a few seconds (Microsoft cites 5 seconds as a reference); tune to environment and real p95.
2. Command timeout aligned with target latency; too low causes false timeouts, too high stalls requests.
3. Retry with exponential backoff + jitter; never retry authentication/authorization errors as transient failures.
4. Bound retry attempts and total deadlines so requests do not hang indefinitely.
5. Stagger reconnections after failover to avoid connection storms across instances.
6. Close old connections/clients when replacing them to avoid exceeding connection quotas.

Azure Managed Redis enforces a 10-minute idle connection timeout. If connections can sit idle for long periods, enable keepalives/heartbeats under 10 minutes or send `PING` appropriately. On Linux workloads, verify host/container TCP keepalive/retry settings; Microsoft notes some Linux defaults can delay dead-connection detection by several minutes.

### 13.1. Retries by Command Type

| Command / Workflow | Retry After Timeout? | Notes |
| --- | --- | --- |
| `GET` | Usually safe to retry | Idempotent read, though the value may have changed |
| `SET key value` with same value | Safe if semantics permit | If carrying a TTL, retrying may reset the TTL |
| `INCR` | Do not retry blindly | May increment twice if the first attempt succeeded |
| `LPUSH`/append | Do not retry blindly | May create duplicate entries |
| `DEL` | Generally idempotent by final state | Consider application side effects/events |
| Lua script/transaction | Depends on logic | Use operation IDs/deduplication when side effects exist |

Do not turn every cache exception into an unbounded database fallback call. Use circuit breakers or concurrency limits so a Redis outage does not overload the backing database.

## 14. Monitoring and Diagnostics

Monitor both application and cache layers:

| Layer | Metrics |
| --- | --- |
| Spring Cache | Hits/misses, evictions, cache operation latency |
| Lettuce | Active connections, reconnect counts, command latency, timeouts, connection errors |
| Entra | Token acquisition failures, refresh failures, `AUTH`/re-authentication errors |
| Azure Managed Redis | CPU, memory, connected clients, throughput, latency, shard health, failover/maintenance events |
| Active geo-replication | Replication health/lag and group status |
| Application | p50/p95/p99, fallback rate, backing database load during Redis outages |

Spring Data Redis cache statistics can be enabled via `RedisCacheManagerBuilder.enableStatistics()`; numbers are local per-process snapshots, not cluster-wide aggregates. Ship metrics to centralized monitoring and avoid logging cached values, tokens, or PII.

When connection errors occur:

1. Check FQDN/port and DNS resolution from the exact pod/VM.
2. Check private networking, firewalls, routing, TLS, and certificate validation.
3. Verify the Entra principal is added as a Redis user and the token scope is `https://redis.azure.com/.default`.
4. Confirm tokens refresh before expiry and re-authentication is enabled.
5. Verify clustering policy matches standalone vs. cluster client configuration.
6. Inspect connected clients, quotas, CPU, memory, failovers, and maintenance events.
7. Run Azure CLI `az redisenterprise test-connection` for end-to-end verification if permitted.

## 15. Testing

### 15.1. Unit Tests

Mock repositories/cache abstractions to test business rules, invalidation, and fallbacks on cache misses/errors. Unit tests do not validate TLS, tokens, Redis command support, or cluster redirection.

### 15.2. Local Integration Tests

Use a Redis container (Testcontainers or Docker Compose) to verify:

- `RedisTemplate` serializers/deserializers.
- Repository CRUD and keyspace mapping.
- `@Cacheable`, `@CachePut`, `@CacheEvict`.
- TTL expiration and prefix isolation.
- Serialization compatibility across application versions.
- Lua scripts, transactions, or Pub/Sub if used by the app.

Local Redis does not fully emulate Azure Entra, Redis Enterprise clustering policies, private networking, token refresh, geo-replication, quotas, or failovers.

### 15.3. Azure Integration Tests

On an Azure test cache, verify:

- Managed Identity or service principal acquires tokens with the right scope.
- The principal is registered on the cache with appropriate command/key permissions.
- TLS and private endpoints work properly.
- OSS cluster client or Enterprise standalone client matches the policy.
- Tokens refresh and re-authenticate on long-lived connections.
- Failover/maintenance triggers reconnection and requests recover within SLA.
- TTL/eviction, persistence, export/import, and restore behave as configured.
- Active geo-replication and application routing if multi-region is required.

### 15.4. Application Lifecycle Tests

| Event | What to Verify |
| --- | --- |
| Application startup | Connection factory initializes cleanly; readiness does not trigger request storms |
| Token near expiry | Provider supplies a fresh token; Lettuce sends `AUTH` again |
| Application rolling restart | Old clients close cleanly; new clients connect without exhausting quotas |
| Redis maintenance/failover | Request timeouts/reconnects, safe retries, and cache fallback work |
| Redis unavailable | Backing database is protected from thundering herds |
| Application shutdown | Subscriptions, connection factory, and token provider close cleanly |
| Cache migration | Key formats, TTLs, serialization, and data loss are reconciled |

## 16. Migrating from Azure Cache for Redis to Azure Managed Redis

A migration plan should follow these steps:

1. **Inventory:** SKU, capacity, endpoint, port, TLS, Entra/access keys, clustering, modules, commands, Pub/Sub, Lua, key counts, and traffic.
2. **Compatibility:** verify Redis version, command support, cluster behavior, key hash slots, and serializers.
3. **Provision target:** pick region/tier, clustering policy, modules, HA, networking, Entra, and active geo-replication up front.
4. **Identity:** add Managed Identity/service principal as a target Redis user, grant least privilege, and test token refresh.
5. **Client:** update host/port, Lettuce topology, and credential provider; do not blindly copy legacy ACR settings.
6. **Data strategy:** decide whether the cache can be re-warmed or needs export/import/dual-write; reconstructible caches may not require copying every key.
7. **Canary:** shift one instance or small traffic slice; monitor hit ratio, latency, errors, CPU, memory, and reconnects.
8. **Cutover:** switch traffic per plan with a rollback window and avoid uncontrolled dual writes.
9. **Reconcile:** compare key counts, critical data, TTLs, stale data, and business behavior.
10. **Retire source:** delete the old cache only after confirming zero active workload connections and closing the retention/rollback window.

If Redis serves as a session store or holds non-reconstructible data, migration requires dedicated consistency/dual-write/maintenance-window planning. Never treat flipping DNS/endpoints as a complete data migration.

## 17. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Using the Azure Cache for Redis starter assuming all settings apply to Azure Managed Redis | Wrong endpoint, auth, or topology | Distinguish ACR and AMR; configure AMR with Lettuce/Redis auth extension |
| Selecting OSS cluster while using a standalone client | Redirect/cluster routing errors | Use `RedisClusterConfiguration`/`RedisClusterClient` |
| Selecting Enterprise policy while assuming cluster discovery | Discovery commands blocked | Use single-endpoint client and drop cluster-management commands |
| Using long-lived access keys | Secret rotation burden and key exposure | Entra Managed Identity and token refresh |
| Fetching a token once and storing it as a password | Connections break when the token expires | `TokenBasedRedisCredentialsProvider` + re-authentication |
| Failing to close token providers/clients | Thread, connection, and background task leaks | Spring lifecycle beans + destroy methods |
| Omitting TTLs | Keys live indefinitely, memory grows | Set domain-appropriate TTLs and eviction policies |
| Assuming reads reset TTL | Keys expire despite frequent reads | Distinguish TTL vs. TTI; use `GETEX`/TTI consistently |
| Using default JDK serialization across services | Compatibility breaks and deserialization risks | Versioned JSON/schemas and explicit serializers |
| Clearing caches with `KEYS` on large keyspaces | Server blocking/latency spikes | `SCAN` batch strategy with Lettuce |
| Blindly retrying `INCR`/`LPUSH` after timeouts | Duplicate side effects | Idempotency keys or state verification |
| Treating Redis as the primary database | Data loss on eviction/outage | Store truth in a database; cache-aside fallback |
| Failing to plan for Azure Cache for Redis retirement | Forced scramble at service end-of-life | Schedule migration before retirement dates |

## 18. Practice Exercises

**Exercise 1 — Spring Cache.** Build a Spring Boot service reading Products from a database. Apply `@Cacheable`, `@CachePut`, and `@CacheEvict`; verify cache hits/misses and invalidation on updates/deletes.

**Exercise 2 — TTL.** Configure a 10-minute cache for product details and 2 minutes for search results. Prove TTL does not reset on `GET` alone; enable TTI-like behavior with `enableTimeToIdle()` on Redis 6.2+ and compare reading via Cache API vs. `RedisTemplate`.

**Exercise 3 — Azure Cache starter.** Connect to an existing cache using `spring-cloud-azure-starter-data-redis-lettuce`. Test both Entra passwordless and access keys in a test environment; verify TLS, port, and Redis username.

**Exercise 4 — Azure Managed Redis Entra.** Provision AMR with the OSS clustering policy, assign a system-assigned Managed Identity to the workload, register the principal as a Redis user, and configure `redis-authx-entraid` with Lettuce re-authentication. Verify token refresh without logging tokens.

**Exercise 5 — Clustering policies.** Compare OSS and Enterprise policies. Identify client classes, multi-key commands, hash slots, and the RediSearch module; explain which choices require recreating the cache to change.

**Exercise 6 — Failover.** Simulate a Redis connection interruption in a test environment. Measure reconnect time, p95, retry counts, and fallback rate. Show why retrying `GET` is safer than blindly retrying `INCR`.

**Exercise 7 — Cache stampede.** Send 100 concurrent requests for a key whose TTL just expired. Measure backing database queries and test jitter, single-flight, and stale-while-revalidate.

**Exercise 8 — Migration.** Plan migrating from Azure Cache for Redis to Azure Managed Redis ahead of the applicable retirement date. Cover inventory, endpoints, Entra, clustering, modules, data strategy, canary, cutover, rollback, and reconciliation.

## 19. Key Takeaways

- Spring Data Redis provides **`RedisTemplate`, repositories, and Spring Cache**; Lettuce is the client managing connections, protocol, and topology.
- The Spring Cloud Azure starter `spring-cloud-azure-starter-data-redis-lettuce` is documented by Spring Azure for **Azure Cache for Redis**; Azure Managed Redis requires evaluating Entra token providers and clustering policies separately.
- Azure Managed Redis enables Entra and disables access keys by default on new caches; use `redis-authx-entraid`, scope `https://redis.azure.com/.default`, and automatic re-authentication before token expiry.
- **OSS clustering policy** requires a cluster-aware client; **Enterprise policy** uses a single endpoint. Modules and several options lock in at provisioning time.
- Redis Cache TTL does not reset on reads; TTI-like behavior requires `GETEX`/Redis 6.2+ and consistent usage across every access path.
- `LettuceConnectionFactory` and token providers have their own lifecycles; close clients/providers on Spring context shutdown.
- Azure Managed Redis can fail over/patch and drop connections; use reconnect, exponential backoff, jitter, keepalives under the 10-minute idle timeout, and idempotent retries.
- Redis should remain a reconstructible cache unless explicitly designed for durability. Rely on a backing database, TTLs, eviction, backups/persistence, and geo-replication aligned with RPO/RTO.
- Azure Cache for Redis is retiring; plan migrations for Basic/Standard/Premium before 2028-09-30 and Enterprise/Enterprise Flash before 2027-03-31.

## 20. References

- [Spring Cloud Azure — Connect Spring Boot to Azure Cache for Redis](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-boot-initializer-java-app-with-redis-cache)
- [Spring Cloud Azure developer guide and starter version mapping](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview)
- [Azure Managed Redis — Java quickstart](https://learn.microsoft.com/en-us/azure/redis/java-get-started)
- [Azure Managed Redis — Microsoft Entra authentication](https://learn.microsoft.com/en-us/azure/redis/entra-for-authentication)
- [Redis Lettuce — Connect to Azure Managed Redis](https://redis.io/docs/latest/develop/clients/lettuce/amr/)
- [Lettuce — Connecting Redis and streaming credentials](https://redis.github.io/lettuce/user-guide/connecting-redis/)
- [Spring Data Redis — Redis Cache, TTL, and TTI](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis — LettuceConnectionFactory API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/connection/lettuce/LettuceConnectionFactory.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Azure Managed Redis — Clustering policy](https://learn.microsoft.com/en-us/azure/redis/choose-clustering-policy)
- [Azure Managed Redis — Failover and patching](https://learn.microsoft.com/en-us/azure/redis/failover)
- [Azure Managed Redis — Connection resilience](https://learn.microsoft.com/en-us/azure/redis/best-practices-connection)
- [Azure Managed Redis — Reliability, backup, and geo-replication](https://learn.microsoft.com/en-us/azure/reliability/reliability-managed-redis)
- [Azure Cache for Redis — What's New and retirement dates](https://learn.microsoft.com/en-us/azure/azure-cache-for-redis/cache-whats-new)
