# Distinguishing Client, Template, Repository, Connection Factory, and Connection Pool

## Objectives and Context

In the **SPRING_BOOT_INTEGRATION** module, Spring Boot connects HTTP clients, databases, caches, message brokers, and Spring Integration adapters into business flows that are configurable, contract-driven, transactional, error-resilient, deduplicated, testable, and observable. All of these systems "connect outward," yet their code names look very different: `RestClient`, `JdbcTemplate`, `JpaRepository`, `LettuceConnectionFactory`, `KafkaTemplate`, `RabbitTemplate`, or `HikariDataSource`.

A recurring architectural question is: **which object actually holds a connection, which borrows a connection, which merely describes data access, and which should be reused across requests?**

This lesson belongs to the **Connection Configuration** chapter and covers **distinguishing client, template, repository, connection factory, and connection pool**. These are not five interchangeable labels. They represent **distinct layers of responsibility**; a single integration adapter may use several of them together.

After this lesson, you will be able to:

1. Accurately identify **client, template, repository, connection factory, and connection pool** in Spring Boot.
2. Trace the path from service → repository/template/client → factory → connection/pool → external system.
3. Distinguish the lifecycle and thread safety of abstractions from physical connections, sessions, or channels.
4. Write proper configuration examples for JDBC/JPA, HTTP, Redis, Kafka, RabbitMQ, and JMS.
5. Explain why pools do not scale throughput infinitely and why Kafka does not use a JDBC-style connection pool.
6. Avoid creating connections or clients per HTTP request or broker message.
7. Design transactions, retries, credential/TLS rotation, idempotency, and backpressure along proper boundaries.
8. Test wiring/configuration, measure resources, and troubleshoot pool exhaustion.

> **Principle:** **Repositories, Templates, and Clients are application-facing APIs; ConnectionFactory/DataSource provides connection resources; a Connection Pool is a strategy for bounding and reusing those resources.** Not every technology has all five layers or calls them by the same name.

## 1. Overview: five distinct roles

~~~mermaid
flowchart TD
    A["OrderService / IntegrationFlow"] --> B["Repository or Template or Client"]
    B --> C["ConnectionFactory / DataSource / Client factory"]
    C --> D["Connection Pool / shared transport resources"]
    D --> E["Connection / Channel / Session / Producer"]
    E --> F["PostgreSQL / HTTP API / Redis / Broker"]
    A -.-> G["Transactions, retries, idempotency"]
    D -.-> H["Timeouts, saturation, metrics"]
~~~

This diagram is **conceptual**; it does not mean every library follows this exact object sequence. For instance, Kafka's `ProducerFactory` caches producers; Kafka does not have a separate JDBC-style pool where applications borrow a `Connection`.

| Concept | Question it answers | Spring examples | Does not automatically guarantee |
| --- | --- | --- | --- |
| **Client** | "Which service receives protocol requests and how are responses parsed?" | `RestClient`, `WebClient`, Kafka client, Redis client | Business authorization, cross-system transactions |
| **Template** | "How to replace resource/protocol boilerplate with a consistent API?" | `JdbcTemplate`, `RedisTemplate`, `KafkaTemplate`, `RabbitTemplate`, `JmsTemplate` | Having its own pool just because it is named Template |
| **Repository** | "How to read/write data around a domain model?" | `JpaRepository`, `CrudRepository`, Spring Data Redis repositories | Abstracting away all network/transaction errors |
| **Connection factory** | "How are connections, sessions, or producers obtained/created from config?" | `RedisConnectionFactory`, AMQP `ConnectionFactory`, `ProducerFactory` | That every factory pools or every connection is thread-safe |
| **Connection pool** | "How many physical resources can exist, be borrowed/returned, and reused?" | HikariCP, Apache HttpClient pool, JMS provider pool | Exactly-once, request ordering, business success |

A **Client** can be a high-level API (Spring `RestClient`) or a low-level network client (Apache `CloseableHttpClient`). A **Factory** can produce transport objects rather than raw connections directly. When reading code, identify *what resource is created* rather than guessing from a `Factory` suffix.

### 1.1. Not a "pick one out of five" choice

Within a single request:

~~~text
OrderService
  -> OrderRepository
       -> JPA EntityManager proxy
            -> EntityManagerFactory
                 -> DataSource/HikariCP
                      -> JDBC Connection -> PostgreSQL
~~~

On another HTTP call:

~~~text
OrderService
  -> InventoryGateway
       -> RestClient
            -> ClientHttpRequestFactory
                 -> Apache HttpClient
                      -> PoolingHttpClientConnectionManager
                           -> TCP/TLS connection -> Inventory API
~~~

With Redis:

~~~text
ProductCache
  -> StringRedisTemplate
       -> RedisConnectionFactory
            -> Lettuce native client/shared connection
                 -> TCP/TLS -> Redis
~~~

A Repository may be implemented on top of a Template or another layer; "repository and template" are not always stacked one after another.

## 2. Which object belongs at which layer?

### 2.1. Client: API for speaking a protocol

A client knows **how** to communicate with a service: host/base URL, serializers, protocol, headers, authentication, HTTP methods, timeouts, and response mapping. Example:

~~~java
import org.springframework.web.client.RestClient;

RestClient inventoryClient = RestClient.builder()
        .baseUrl("https://inventory.example.org")
        .build();

InventoryResponse response = inventoryClient.get()
        .uri("/v1/products/{sku}", "P-100")
        .retrieve()
        .body(InventoryResponse.class);
~~~

`InventoryResponse` is an illustrative contract DTO. `RestClient` is the API entrypoint; the underlying `ClientHttpRequestFactory` and HTTP transport decide connection reuse.

A client object may **not hold a dedicated socket** upon construction. Many clients open connections lazily on the first request, and multiple requests can reuse pooled connections.

### 2.2. Template: turning boilerplate into safer operations

`JdbcTemplate` handles:

- Acquiring a connection from `DataSource` aligned with the active transaction.
- Creating a `PreparedStatement` and binding parameters.
- Executing queries/updates and mapping `ResultSet` rows.
- Closing/returning resources properly and translating SQL exceptions into Spring data-access exceptions.

~~~java
import org.springframework.jdbc.core.JdbcTemplate;

public int markProcessed(
        JdbcTemplate jdbcTemplate,
        String eventId) {

    return jdbcTemplate.update(
            "UPDATE integration_inbox SET processed = true WHERE event_id = ?",
            eventId);
}
~~~

A `JdbcTemplate` is typically configured once and reused. It is **not a JDBC Connection**. Similarly, `RedisTemplate` wraps key/value operations, `KafkaTemplate` wraps producer sends, and `RabbitTemplate` wraps AMQP send/receive calls.

### 2.3. Repository: domain-oriented data interface

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    Optional<OrderEntity> findByExternalId(
            String externalId);
}
~~~

Spring Data generates an implementation/proxy for the repository interface atop the underlying persistence API and transaction infrastructure. A repository expresses **data access behavior**, not a network connection or pool.

Do not equate `JpaRepository` with `JdbcTemplate`. `JpaRepository` uses JPA/ORM with a persistence context, dirty checking, lazy loading, and entity lifecycles; `JdbcTemplate` works directly with SQL and rows. An application may use both depending on query and consistency needs.

### 2.4. Connection factory: provisioning/creating connection objects

In Redis:

~~~java
import org.springframework.data.redis.connection.RedisConnectionFactory;

public class CacheDiagnostics {

    private final RedisConnectionFactory connectionFactory;

    public CacheDiagnostics(
            RedisConnectionFactory connectionFactory) {
        this.connectionFactory = connectionFactory;
    }
}
~~~

`RedisConnectionFactory` is the infrastructure templates and repositories use to obtain Redis connections. Business services generally **do not call `getConnection()` directly**; use `StringRedisTemplate` or a higher-level abstraction to avoid managing lifecycle manually.

In RabbitMQ, `CachingConnectionFactory` creates and caches AMQP connections and channels. In JMS, `ConnectionFactory` creates `Connection`/`JMSContext` objects per provider. In Kafka, `ProducerFactory`/`ConsumerFactory` supply clients rather than `java.sql.Connection` handles.

### 2.5. Connection pool: bounding and reusing physical resources

A pool such as HikariCP manages JDBC Connections; an Apache HttpClient pool manages HTTP connections. Key concerns include:

- Total max connections and per-destination limits.
- Wait time to **borrow a connection**.
- Idle timeout, maximum lifetime, and eviction.
- Health/validation and stale connection checks.
- Metrics for leased/active, idle, and pending counts.
- Shutdown/reconfiguration and certificate/credential rotation.

A pool does not convert blocking operations into non-blocking ones, does not increase downstream server capacity, and does not automatically roll back business transactions.

## 3. Quick reference map across technologies

| Technology | Application entry API | Factory/resource provider | Typical pooling/caching |
| --- | --- | --- | --- |
| JDBC | `JdbcTemplate`, Spring Data JDBC repo | `DataSource` | HikariCP |
| JPA/Hibernate | `JpaRepository`, `EntityManager` proxy | `EntityManagerFactory` + `DataSource` | JDBC pool at `DataSource` |
| Synchronous HTTP | `RestClient`, HTTP interface proxy | `ClientHttpRequestFactory` | Apache HttpClient / transport pool |
| Reactive HTTP | `WebClient` | `ClientHttpConnector` | Reactor Netty connection provider |
| Redis | `StringRedisTemplate`, `RedisTemplate`, Redis repository | `RedisConnectionFactory` | Lettuce shared connection / pool if configured |
| Kafka producer | `KafkaTemplate` | `ProducerFactory` | Cached/reused `KafkaProducer`, **not** a JDBC pool |
| Kafka consumer | `@KafkaListener`/container | `ConsumerFactory` | Consumer instances scaled by concurrency |
| RabbitMQ | `RabbitTemplate`, `@RabbitListener` | AMQP `ConnectionFactory` | Connection/channel cache |
| JMS | `JmsTemplate`, `@JmsListener` | JMS `ConnectionFactory` | Provider pool / `CachingConnectionFactory` |
| Spring Integration | `IntegrationFlow`, adapters | Underlying client/template/factory | Depends on underlying transport |

Do not force a single rigid pattern: "every connection has a `ConnectionFactory` and `ConnectionPool`." In JDBC, `DataSource` itself is the connection-level abstraction; `EntityManagerFactory` creates `EntityManager` instances rather than issuing TCP sockets directly.

## 4. JDBC: DataSource, HikariCP, and JdbcTemplate

### 4.1. Lifecycle of a SQL statement

~~~mermaid
sequenceDiagram
    participant S as OrderService
    participant T as JdbcTemplate
    participant D as DataSource/HikariCP
    participant P as PostgreSQL
    S->>T: update(SQL, args)
    T->>D: Get JDBC Connection
    D-->>T: Connection borrowed
    T->>P: Execute prepared SQL
    P-->>T: Row count
    T->>D: Close wrapper / return to pool
    T-->>S: Update result
~~~

Calling `Connection.close()` on a pooled connection typically **returns the connection to the pool** rather than immediately closing the physical socket. When participating in a Spring-managed transaction, actual release follows the transaction lifecycle.

### 4.2. Spring Boot DataSource configuration

With the JDBC/JPA starter and HikariCP available, Spring Boot auto-configures `DataSource` from `spring.datasource.*`. Example:

~~~yaml
spring:
  datasource:
    url: ${DB_URL:jdbc:postgresql://db.internal:5432/orders}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: orders-jdbc
      maximum-pool-size: 16
      minimum-idle: 4
      connection-timeout: 2000
      idle-timeout: 600000
      max-lifetime: 1800000
~~~

For numeric Hikari timeouts above, the typical unit is **milliseconds**; verify against Spring Boot binding and Hikari settings for your version. Passwords must never be hard-coded. Configure TLS and server identity verification on the JDBC URL per driver and environment; never assume traffic is secure merely because the server sits on an internal network.

### 4.3. JdbcTemplate is a reusable bean

~~~java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OrderJdbcRepository {

    private final JdbcTemplate jdbcTemplate;

    public OrderJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public int markExported(long orderId) {
        return jdbcTemplate.update(
                "UPDATE orders SET exported = true WHERE id = ?",
                orderId);
    }
}
~~~

`OrderJdbcRepository` is an **application-level repository** built with a template and manual SQL. It is not automatically a Spring Data `JpaRepository`. Such repositories keep business queries separate from controller/service orchestration.

**Thread safety:** `JdbcTemplate` is thread-safe once configured. Never store `java.sql.Connection` or `PreparedStatement` in a singleton service shared across threads; let Spring's transaction infrastructure manage them.

### 4.4. DataSource is the factory and pooling boundary

`javax.sql.DataSource` defines `getConnection()`; the injected object may itself be a Hikari `DataSource`. You do not need an extra "ConnectionFactory" bean for JDBC.

A common mistake:

~~~java
// Anti-pattern: never open and retain a shared Connection in a singleton.
class UnsafeDao {
    private java.sql.Connection sharedConnection;
}
~~~

Consequences include overlapping transactions, stale connections, leaked session state, and multithreaded races. Use `JdbcTemplate`, or `DataSourceUtils`/transaction APIs when low-level JDBC is required.

### 4.5. Size connection pools by capacity, not raw HTTP request counts

If an application runs 10 replicas each with `maximum-pool-size=20`, total connections aimed at the database can reach roughly 200 **before counting other applications**. When PostgreSQL allows fewer connections, raising pool sizes triggers connection exhaustion.

Initial sizing must consider:

- Total DB connection budget.
- Number of replicas/pods.
- How long each transaction holds a JDBC connection.
- SQL latency, lock contention, and workload profile.
- Burst concurrency and pool wait p95/p99.
- Number of datasources (read/write, multi-tenant).
- Batch jobs and scheduled integration workers.

Enlarging the pool does not speed up slow SQL queries; you usually need indexes, better query plans, shorter transactions, and concurrency caps.

## 5. JPA: Repository, EntityManagerFactory, and JDBC pool

JPA adds another layer:

~~~text
OrderService
  -> JpaRepository<OrderEntity, Long>
  -> Spring Data JPA repository proxy
  -> EntityManager (transaction persistence context)
  -> EntityManagerFactory
  -> DataSource/HikariCP
  -> JDBC Connection -> PostgreSQL
~~~

### 5.1. EntityManagerFactory vs. DataSource

| Object | Responsibility |
| --- | --- |
| `EntityManagerFactory` | Thread-safe factory creating EntityManagers/persistence contexts |
| `EntityManager` | Persistence context managing entities and dirty checking |
| Spring Data `JpaRepository` | Entity CRUD/query API |
| `DataSource` | Supplies JDBC Connections to Hibernate/JPA |
| HikariCP | Manages physical JDBC connections |

**`EntityManager` is not thread-safe.** However, `@PersistenceContext` injected by Spring is typically a **proxy** delegating to an `EntityManager` bound to the current transaction/thread. Never create an `EntityManager` directly, store it in a singleton, and share it across requests.

### 5.2. Transaction boundaries

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderApplicationService {

    private final OrderRepository repository;

    public OrderApplicationService(
            OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void confirmOrder(long orderId) {
        OrderEntity order = repository.findById(orderId)
                .orElseThrow();
        order.confirm();
    }
}
~~~

This example assumes `OrderEntity.confirm()` mutates state flushed by JPA dirty checking on transaction commit. `@Transactional` uses the matching transaction manager (e.g. `JpaTransactionManager`). **Avoid holding transactions open across slow HTTP or broker calls** whenever possible.

**Do not confuse:** JPA repository proxies are safely shared across threads, whereas the `EntityManager`/persistence context operates per transaction. Physical JDBC Connections remain managed by the `DataSource`/pool.

## 6. Synchronous HTTP: RestClient, request factories, and connection managers

~~~mermaid
flowchart TD
    A["InventoryGateway"] --> B["RestClient"]
    B --> C["ClientHttpRequestFactory"]
    C --> D["Apache HttpClient or JDK transport"]
    D --> E["Pooling connection manager"]
    E --> F["TCP/TLS socket to Inventory API"]
~~~

`RestClient` is the high-level API for building HTTP requests. `ClientHttpRequestFactory` governs the transport implementation; some factories use Apache HttpClient 5, others use the JDK HttpClient or `SimpleClientHttpRequestFactory`. **Not all request factories share the same pooling semantics.**

### 6.1. Creating a RestClient per downstream service

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpConfiguration {

    @Bean
    RestClient inventoryRestClient(
            RestClient.Builder builder,
            @Value("${integrations.inventory.base-url}")
            String baseUrl) {

        return builder
                .baseUrl(baseUrl)
                .build();
    }
}
~~~

`base-url` should come from environment configuration, never allowing callers to arbitrarily steer requests to internal URLs. Configure TLS/mTLS, HTTP Basic, API keys, or OAuth2 on **that downstream's specific client/transport**, rather than setting a global `Authorization` header.

### 6.2. HTTP pooling with Apache HttpClient 5

Spring Framework 6.x provides `HttpComponentsClientHttpRequestFactory` backed by Apache HttpClient 5 when a compatible `httpclient5` module is present.

~~~groovy
dependencies {
    implementation 'org.apache.httpcomponents.client5:httpclient5'
}
~~~

Example configuration (illustrative for compatible Apache HttpClient 5 / Spring 6 versions):

~~~java
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Bean(destroyMethod = "close")
CloseableHttpClient inventoryApacheClient() {
    PoolingHttpClientConnectionManager manager =
            PoolingHttpClientConnectionManagerBuilder.create()
                    .setMaxConnTotal(80)
                    .setMaxConnPerRoute(20)
                    .build();

    return HttpClients.custom()
            .setConnectionManager(manager)
            .evictExpiredConnections()
            .build();
}

@Bean
RestClient inventoryPooledRestClient(
        RestClient.Builder builder,
        CloseableHttpClient inventoryApacheClient) {

    var requestFactory =
            new HttpComponentsClientHttpRequestFactory(
                    inventoryApacheClient);

    return builder
            .baseUrl("https://inventory.example.org")
            .requestFactory(requestFactory)
            .build();
}
~~~

Both `@Bean` methods belong inside a `@Configuration` class. Timeouts (pool acquisition, connect, response) **must be configured separately** on the request factory or Apache HttpClient connection/request configs according to version. This code focuses solely on **pool/transport ownership**. Newer releases may change `ConnectionConfig`, `RequestConfig`, or TLS strategy signatures; do not copy HttpClient 4 configuration into HttpClient 5.

### 6.3. Distinguishing four timeout types

| Timeout | What is it waiting for? | Typical layer |
| --- | --- | --- |
| Pool acquisition | Borrowing an idle connection | HTTP connection manager / request config |
| TCP connect | Establishing a socket to endpoint/proxy | HTTP transport / connection config |
| TLS handshake | Verifying certificates and negotiating TLS | HTTP transport / TLS strategy |
| Read/response | Waiting for response bytes | HTTP request / connection / socket config |
| Total operation deadline | Covers all steps above plus retries | Application / adapter policy |

If `maxPerRoute=20` and 200 threads call the Inventory API concurrently, threads queue waiting on the pool. Raising `readTimeout` alone will not fix **connection request timeouts**. When Inventory API slows down, an oversized pool can amplify load and topple the downstream service.

### 6.4. Thread safety and HTTP client lifecycle

Once built, `RestClient` can be reused safely across callers per framework contract; creating one bean per downstream is far better than constructing a new client on every request. The underlying `CloseableHttpClient` is generally thread-safe and should close on application shutdown.

**A `RestClient` does not automatically own a dedicated HTTP pool**: that depends on the injected request factory and transport. When clients carry different credentials, consider isolating request factories and connection pools by trust boundary.

## 7. Reactive HTTP: WebClient and Reactor Netty ConnectionProvider

`WebClient` is the reactive HTTP API. When backed by Reactor Netty, the resource layers look like:

~~~text
WebClient
  -> ReactorClientHttpConnector
       -> Reactor Netty HttpClient
            -> ConnectionProvider / shared event-loop resources
                 -> TCP/TLS channels
~~~

`WebClient` does not automatically mean "one socket per `Mono`." Requests execute when publishers are subscribed to, and connections can be reused from pools managed by the HTTP connector.

### 7.1. Bounded Reactor Netty pool example

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
public class ReactiveInventoryConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider inventoryConnectionProvider() {
        return ConnectionProvider.builder("inventory-http")
                .maxConnections(40)
                .pendingAcquireMaxCount(100)
                .pendingAcquireTimeout(Duration.ofSeconds(1))
                .build();
    }

    @Bean
    WebClient inventoryWebClient(
            WebClient.Builder builder,
            ConnectionProvider inventoryConnectionProvider) {

        HttpClient client = HttpClient
                .create(inventoryConnectionProvider)
                .responseTimeout(Duration.ofSeconds(8));

        return builder
                .baseUrl("https://inventory.example.org")
                .clientConnector(
                        new ReactorClientHttpConnector(client))
                .build();
    }
}
~~~

This configures a **dedicated `ConnectionProvider`**; verify exact API methods against your Reactor Netty version. Custom providers should be disposed on shutdown. In Boot, if using the auto-configured resource factory, avoid spawning unintended extra event loops or pools.

**Reactive does not mean unbounded:** TCP sockets, pool acquisition, CPU, memory, and downstream concurrency limits still apply. If a pipeline emits thousands of requests, cap `flatMap` concurrency/buffers to match downstream capacity rather than just growing the pool.

### 7.2. WebClient is the client; pooling does not live on WebClient

Code like:

~~~java
WebClient client = WebClient.builder()
        .baseUrl("https://inventory.example.org")
        .build();
~~~

does not show max connections, pending acquire limits, or TLS lifecycles. To diagnose pool exhaustion, inspect the **actual connector, provider, and transport**, not just the `WebClient` bean.

## 8. Redis: RedisConnectionFactory, RedisTemplate, and shared connections

In Spring Data Redis, two objects are frequently confused:

- `RedisConnectionFactory`: factory provisioning Redis connections.
- `RedisTemplate` / `StringRedisTemplate`: API executing Redis commands.

Diagram:

~~~mermaid
flowchart LR
    S["ProductCacheService"] --> T["StringRedisTemplate"]
    T --> F["RedisConnectionFactory"]
    F --> L["Lettuce native client/connection"]
    L --> R["Redis server/cluster"]
~~~

### 8.1. Spring Boot Redis configuration

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

~~~yaml
spring:
  data:
    redis:
      host: ${REDIS_HOST:redis.internal}
      port: ${REDIS_PORT:6379}
      password: ${REDIS_PASSWORD}
      timeout: 2s
~~~

In production, configure TLS/ACLs and topology (standalone, Sentinel, or Cluster) to match the live setup. `spring.data.redis.*` is the standard namespace in Boot 3, though other Boot/driver versions may vary. Omit passwords if another authentication mechanism is used; never hard-code secrets.

### 8.2. StringRedisTemplate in a business adapter

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class ProductCache {

    private final StringRedisTemplate redis;

    public ProductCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void cacheSku(String sku, String json) {
        redis.opsForValue()
                .set("product:" + sku, json, Duration.ofMinutes(5));
    }

    public String findSku(String sku) {
        return redis.opsForValue().get("product:" + sku);
    }
}
~~~

`StringRedisTemplate` uses string serializers for keys and values. For domain objects, configure versioned JSON serialization intentionally rather than assuming Java native serialization is safe or forward-compatible.

### 8.3. Does LettuceConnectionFactory always use a pool?

**No.** With Spring Data Redis/Lettuce, `LettuceConnectionFactory` can share a single native connection across non-blocking operations and handle blocking/transactional operations differently. Having `LettuceConnectionFactory` **does not prove** each request borrows a socket from a HikariCP-like pool.

Enable pooling only when workload or topology warrants it and the client supports it—typically requiring `commons-pool2`. Example Boot Lettuce pool options:

~~~yaml
spring:
  data:
    redis:
      lettuce:
        pool:
          max-active: 16
          max-idle: 8
          min-idle: 2
          max-wait: 2s
~~~

These options take effect only if a pool is actually instantiated and used per your config, driver, and version. Do not "turn on pooling for performance" out of habit: excessive connections add overhead to the Redis server.

### 8.4. Thread safety

`RedisTemplate` is designed for reuse once configured. **Low-level `RedisConnection` handles must not be shared arbitrarily across threads**, especially for transactions, pipelines, or blocking commands. Lettuce native connections provide specific thread-safety guarantees, yet Spring Data's adapters and transaction wrappers impose lifecycle contracts that must be respected.

A SQL transaction does not automatically include Redis writes. If a SQL update commits and Redis invalidation fails, rely on cache-aside TTLs, event-driven invalidation/outbox, or reconciliation; pooling does not solve consistency.

## 9. RabbitMQ: CachingConnectionFactory, RabbitTemplate, and Channels

RabbitMQ/AMQP adds another layer: a **TCP connection** multiplexes multiple **AMQP channels**. Spring AMQP commonly uses `CachingConnectionFactory` to reuse them.

~~~mermaid
flowchart LR
    S["OrderEventPublisher"] --> T["RabbitTemplate"]
    T --> F["CachingConnectionFactory"]
    F --> C["AMQP Connection"]
    C --> H1["AMQP Channel A"]
    C --> H2["AMQP Channel B"]
    H1 --> E["Exchange/Queue broker"]
    H2 --> E
~~~

### 9.1. Spring Boot configuration

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-amqp'
}
~~~

~~~yaml
spring:
  rabbitmq:
    host: ${RABBIT_HOST:rabbitmq.internal}
    port: ${RABBIT_PORT:5672}
    username: ${RABBIT_USERNAME}
    password: ${RABBIT_PASSWORD}
    cache:
      channel:
        size: 25
~~~

`cache.channel.size` sets the channel cache target; **it is not automatically a hard cap on concurrent channels**. Enforcing a cap may require `channelCheckoutTimeout` and related settings. Other options such as connection cache mode and connection limits depend on your Spring AMQP version and broker limits.

### 9.2. Reusing RabbitTemplate

~~~java
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderRabbitPublisher {

    private final RabbitTemplate rabbitTemplate;

    public OrderRabbitPublisher(RabbitTemplate rabbitTemplate) {
        this.rabbitTemplate = rabbitTemplate;
    }

    public void publish(String eventJson) {
        rabbitTemplate.convertAndSend(
                "orders.exchange",
                "order.confirmed",
                eventJson);
    }
}
~~~

`RabbitTemplate` is a high-level abstraction typically reusable as a singleton bean. It is **not a fixed AMQP Channel**; connection and channel management belong to `ConnectionFactory`, the template, and messaging infrastructure. Publisher confirms, returns, message persistence, and retries require explicit broker and template configuration.

### 9.3. Publishing and consuming are separate lifecycles

- Producer `RabbitTemplate` sends messages; publisher confirms (if enabled) only prove broker confirm semantics.
- Listener containers (`@RabbitListener`) maintain separate channels, concurrency, prefetch, and ACK policies.
- Consumer `basicAck`/`basicNack` governs message settlement.
- Broker exchange/queue bindings and durability govern deliverability.

Never conclude from `RabbitTemplate.convertAndSend(...)` returning without error that a consumer has committed SQL. That is a **producer ack vs. consumer completion** problem, not a connection pool concern.

### 9.4. Channel caches do not rescue poison messages

If a handler endlessly NACKs and requeues an invalid event, enlarging the channel cache only increases retry churn or memory pressure; apply DLQs, backoff, deduplication, and schema validation. For CPU/DB overload, tune listener concurrency, prefetch, and downstream capacity before adding connections.

## 10. Kafka: ProducerFactory/ConsumerFactory is not a JDBC Connection Pool

Kafka uses familiar **factory/template** names like Spring Data, yet its resource model is very different:

~~~text
KafkaTemplate<K,V>
  -> ProducerFactory<K,V>
       -> KafkaProducer<K,V>
            -> Network connections, buffers, sender thread
                 -> Kafka broker/topic partitions

@KafkaListener container
  -> ConsumerFactory<K,V>
       -> KafkaConsumer<K,V> per consumer instance
            -> poll / group assignment / offset commit
~~~

### 10.1. Spring Boot Kafka configuration

~~~groovy
dependencies {
    implementation 'org.springframework.kafka:spring-kafka'
}
~~~

~~~yaml
spring:
  kafka:
    bootstrap-servers: ${KAFKA_BOOTSTRAP_SERVERS:kafka.internal:9092}
    producer:
      acks: all
      key-serializer: org.apache.kafka.common.serialization.StringSerializer
      value-serializer: org.apache.kafka.common.serialization.StringSerializer
    consumer:
      group-id: order-projection
      key-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      value-deserializer: org.apache.kafka.common.serialization.StringDeserializer
      enable-auto-commit: false
~~~

Broker TLS/SASL/mTLS properties and ACLs must be configured per environment. `acks=all` is a producer broker acknowledgment policy, not proof that consumers have processed the record.

### 10.2. KafkaTemplate and ProducerFactory

~~~java
import org.springframework.kafka.core.KafkaTemplate;
import org.springframework.stereotype.Component;

@Component
public class OrderKafkaPublisher {

    private final KafkaTemplate<String, String> kafkaTemplate;

    public OrderKafkaPublisher(
            KafkaTemplate<String, String> kafkaTemplate) {
        this.kafkaTemplate = kafkaTemplate;
    }

    public void send(String orderId, String eventJson) {
        kafkaTemplate.send("orders.events", orderId, eventJson)
                .whenComplete((result, error) -> {
                    if (error != null) {
                        // Failed/unknown outcome; orchestrate bounded retry.
                        return;
                    }
                    // Accepted by broker per acks config.
                    // Do NOT mark consumer processed here.
                });
    }
}
~~~

Spring Kafka 3.x+ example using `CompletableFuture`. `KafkaTemplate` is safely reused, while `ProducerFactory` manages producer instances/caching per configuration. **Never instantiate a new `KafkaProducer` per event**, because each producer carries network connections, buffers, threads, and batching state.

### 10.3. KafkaConsumer is not thread-safe

A Kafka consumer maintains polling state and consumer group membership. One `KafkaConsumer` must never be polled or mutated concurrently across threads. Spring Kafka listener containers manage consumer instances according to concurrency and partition counts.

Raising `@KafkaListener` concurrency does not create 100 JDBC Connections directly, yet it spins up more consumer clients/network connections and adds load to downstream databases. **Partition count caps useful parallelism within a single consumer group.**

### 10.4. Kafka producer caching is not a generic connection pool

`DefaultKafkaProducerFactory` can reuse producers, especially for transactional producer contexts, yet it does not follow HikariCP's `borrow Connection → execute SQL → return Connection` cycle. A producer multiplexes records and batches over broker connections via an internal sender thread. Tuning focuses on:

- `batch.size`, `linger.ms`, `buffer.memory`.
- `acks`, retries/idempotence.
- Delivery timeouts, in-flight requests.
- Partition/broker counts.
- Producer/consumer concurrency.
- Serialization overhead and broker quotas.

Searching for a HikariCP-style "Kafka connection pool maximum size" usually points to misaimed tuning.

## 11. JMS: ConnectionFactory, JmsTemplate, Session, and Pool

JMS follows the classic ConnectionFactory pattern more closely:

~~~text
JmsTemplate
  -> JMS ConnectionFactory
       -> Connection/JMSContext
            -> Session
                 -> Producer/Consumer
                      -> Queue/Topic
~~~

### 11.1. Configuration and lifecycle

`JmsTemplate` encapsulates acquiring connections/sessions, sending messages, converting payloads, and releasing resources. Spring Boot configures JMS infrastructure when a suitable provider and starter are present.

### 11.2. Why shouldn't JMS Sessions be shared arbitrarily?

JMS `Session` instances follow single-threaded/lifecycle rules; never store a session in a global field shared across HTTP worker threads. `JmsTemplate` and listener containers manage factories and sessions properly through the framework.

You can use a provider pool or `org.springframework.jms.connection.CachingConnectionFactory` to cache sessions, producers, and consumers per config, though **not every use case should cache consumers** (especially durable subscriptions or dynamic destinations). Cache sizing and lifecycle must match the provider, transaction mode, and listener container.

### 11.3. Transaction boundaries

`JmsTemplate` or JMS session transactions do not automatically commit atomically with a JDBC `@Transactional` if the transaction manager only manages the database. Use XA/JTA where appropriately designed, or a transactional outbox/inbox to prevent lost or duplicate events.

## 12. Bean scopes, lifecycles, and thread safety

A frequent mistake is seeing `@Bean` and assuming the object represents a single connection dedicated to one request. A Spring singleton bean is **a shared service/adapter object**, not a single socket or a single transaction.

| Object | Should it be injected as a singleton? | Should low-level resources be shared across threads? |
| --- | --- | --- |
| `RestClient` | Yes, with immutable post-build config | Transport/pool operates per contract |
| `WebClient` | Yes | Never share mutable request state |
| `JdbcTemplate` | Yes | Never hold a global JDBC `Connection` |
| `JpaRepository` proxy | Yes | Never share a raw `EntityManager` |
| `EntityManagerFactory` | Yes | Factory is thread-safe; `EntityManager` is not |
| `RedisTemplate` | Yes, once configured | `RedisConnection` transactions/pipelines need dedicated lifecycles |
| `LettuceConnectionFactory` | Yes | Follow driver connection semantics |
| `RabbitTemplate` | Yes, stable config | Never hold a global RabbitMQ `Channel` |
| `CachingConnectionFactory` | Yes | Factory manages channels/connections |
| `KafkaTemplate` | Yes | `KafkaProducer` is factory-managed; `KafkaConsumer` is not thread-safe |
| `JmsTemplate` | Yes | Never share a JMS `Session` arbitrarily |
| `DataSource` (Hikari) | Yes | Borrow JDBC `Connection` per operation/transaction |

**Default rule:** Create factories, templates, repositories, and configured clients **once at application scope**; acquire low-level connections and sessions per operation/transaction managed by the framework. Provider-specific exceptions exist, but must be backed by documentation and thread-safety tests.

### 12.1. Resource ownership and shutdown

Whoever creates a resource owns closing it:

- `HikariDataSource` is closed by Spring on context shutdown.
- A custom Apache `CloseableHttpClient` bean declares a destroy method to release its pool manager.
- A custom Reactor Netty `ConnectionProvider` must be disposed.
- Rabbit `ConnectionFactory` and listener containers close channels and connections.
- Kafka producer/consumer factories and listener containers close clients and threads.
- Client caches or credential rotation may require rebuilding connections or pools.

Never allocate a new `CloseableHttpClient` per call and omit `close()`; socket and thread leaks emerge under production load rather than unit tests.

## 13. Sizing connections and pools within an overall "budget"

An application concurrently querying SQL, Redis, Inventory HTTP, and publishing to Kafka has **multiple independently bounded resources**:

~~~text
HTTP inbound threads / concurrency
        |
        +-- JDBC pool: 16 active max
        +-- Inventory HTTP connections: 20 per route
        +-- Redis connections / shared native client
        +-- Kafka producer buffers / network threads
        +-- RabbitMQ channels / listener concurrency
~~~

If 100 concurrent requests arrive while the DB pool holds 16 and Inventory HTTP allows 20, raising the JDBC pool to 100 will not cure Inventory 503s. Worse, holding a JDBC transaction open during slow HTTP calls ties up JDBC connections and triggers cascading failures.

### 13.1. Concurrency budget example

Assuming 8 replicas:

| Resource | Per-instance limit | Theoretical total | Consequence if grown unbounded |
| --- | ---: | ---: | --- |
| JDBC connections | 12 | 96 | Exceeds `max_connections` or increases lock contention |
| Inventory HTTP per-route | 16 | 128 | Overloads Inventory API |
| Worker item threads | 8 | 64 | Backlog / CPU pressure |
| Rabbit listener concurrency | 4 | 32 consumers | Excessive broker/DB load |

Figures are illustrative. Actual totals also depend on autoscaling, traffic from other services, number of routes, socket reuse, DB reserves, and broker quotas.

### 13.2. Pool size vs. queue size

- Pool size limits active physical resources.
- Queue size limits waiting tasks/requests.
- Timeouts limit a single wait stage.
- Bulkheads/concurrency caps limit in-flight operations.
- Circuit breakers fail fast temporarily when downstream breaks.
- Rate limiters cap QPS.

An oversized pool paired with an unbounded queue accumulates work in RAM, spikes p99 latency, and causes OOM crashes. Prefer bounded resources and explicit deadlines.

### 13.3. Commonly confused timeout units

| Property | Typical unit / meaning |
| --- | --- |
| Hikari `connection-timeout` | Pool wait time, usually integer milliseconds |
| Hikari `max-lifetime` | Connection lifetime, not transaction timeout |
| HTTP connect timeout | Time to open TCP connection, not total response |
| HTTP response timeout | Waiting for response/data, excluding retries |
| Reactor Netty `pendingAcquireTimeout` | Waiting for a connection pool slot |
| Redis `timeout` | Command/operation timeout per driver config |
| Kafka `delivery.timeout.ms` | Producer delivery deadline, not consumer commit |
| Rabbit listener prefetch | Count of unacked deliveries, not connection count |

When writing YAML such as `2s` or `2000`, verify the bound property type in your Spring Boot and driver versions to avoid confusing milliseconds with seconds.

## 14. A connection pool is not a transaction manager

What a transaction guarantees depends on the resource and manager:

~~~mermaid
flowchart LR
    A["OrderService"] --> T["SQL @Transactional"]
    T --> D["JdbcTemplate / JpaRepository"]
    D --> P["Hikari DataSource → PostgreSQL"]
    A --> H["RestClient → ERP"]
    A --> K["KafkaTemplate → Kafka"]
    A --> R["RedisTemplate → Redis"]
    T -. "Does not auto-rollback" .-> H
    T -. "Does not auto-rollback" .-> K
    T -. "Does not auto-rollback" .-> R
~~~

`@Transactional` with a JDBC/JPA manager typically governs a single database transaction; it does not enroll HTTP calls, Redis writes, or Kafka sends into the same ACID transaction.

### 14.1. An anti-pattern

~~~java
@Transactional
public void confirmOrder(long id) {
    orderRepository.markConfirmed(id);
    inventoryRestClient.post()
            .uri("/v1/reservations")
            .body(new ReservationRequest(id))
            .retrieve()
            .toBodilessEntity();
    kafkaTemplate.send("orders.events", Long.toString(id), "confirmed");
}
~~~

This illustrates a design trap; classes and fields belong to the application. Possible failures include:

- HTTP Inventory commits, then the SQL transaction rolls back.
- The SQL transaction holds a JDBC Connection while HTTP times out.
- An async Kafka publish succeeds even though SQL commit fails.
- Hikari pool runs out of connections due to overly long transactions.

Increasing the connection pool cannot solve this; the architecture must change.

### 14.2. Transactional outbox

~~~mermaid
flowchart LR
    A["Confirm order"] --> B["SQL tx: update order + insert outbox"]
    B --> C["Commit"]
    C --> D["Outbox worker"]
    D --> E["HTTP/Kafka/Rabbit adapter"]
    E --> F["Partner/broker"]
    F -.-> G["Result + retry/reconciliation"]
~~~

Inside the SQL transaction, persist business state and durable intent together. After commit, an outbox relay uses the corresponding client or template to publish or call the API. If the process crashes, the intent remains safely persisted for retry.

**Outboxes are typically at-least-once.** If the broker receives a message and the relay crashes before recording success, the relay sends it again. Consumers and partners need stable idempotency keys, inbox/unique constraints, or status lookups. Connection factories and pools manage resources; they do not provide exactly-once guarantees.

### 14.3. Redis cache consistency

`RedisTemplate.opsForValue().set(...)` is not atomic with a PostgreSQL commit. If SQL succeeds and the Redis write fails, the cache becomes stale. Use TTLs, cache-aside invalidation, transactional outbox/events, or versioning per business requirements.

### 14.4. Kafka/Rabbit producer ACKs vs. consumer completion

A completed `KafkaTemplate.send(...)` future or Rabbit publisher confirm ACK proves **broker acceptance per policy**; it does not prove a consumer committed SQL. Consumer ACKs or offset commits also do not guarantee business completion if the app ACKs too early.

## 15. Errors, retries, and pool exhaustion

### 15.1. Three distinct failure categories

| Category | Examples | Direction to address |
| --- | --- | --- |
| **Acquire resource** | Hikari connection wait timeout, HTTP pool pending timeout | Cap concurrency, inspect pool metrics and query/handler latency |
| **Establish connection** | DNS failure, TCP refused, TLS certificate mismatch | Verify endpoints, CA/SANs, networking, proxies |
| **Operation/protocol** | SQL deadlock, HTTP 503, Redis command timeout, broker NACK | Classify transient vs. permanent, retry/idempotency |

**Do not enlarge a pool to fix a TLS certificate error or HTTP 401.** Do not raise read timeouts indefinitely to mask connection leaks. Layer-accurate classification prevents retry storms.

### 15.2. Pool starvation from long-running transactions

~~~text
HTTP thread A acquires JDBC Connection
   -> BEGIN TRANSACTION
   -> SELECT row
   -> calls slow HTTP partner for 15 seconds
   -> COMMIT + release JDBC Connection

Other requests wait on Hikari pool
   -> connectionTimeout exceeded
~~~

Minimize database transaction duration. When remote calls cause side effects, use an outbox, saga, or state-machine flow. Holding DB connections across HTTP waits invites cascading failures.

### 15.3. Bounded retries

An HTTP timeout on a write request can leave an **unknown outcome**: the remote service may have processed the work before the response was lost. When retrying, reuse the same `operationId`/idempotency key if supported by the partner; otherwise query a status API or reconcile.

With message brokers, broker redeliveries and application retries can produce duplicates. Pair an inbox/unique constraint with business side effects in the same transaction. Pools do not prevent duplicates.

### 15.4. Connection leaks

Symptoms:

- Hikari active count climbs and never drops.
- HTTP leased connections stay high while available stays low persistently.
- Rabbit channels grow abnormally.
- Kafka producer threads and file descriptors climb per request.
- Redis connections exceed estimates after deployment.

Inspect allocation stacks, lifecycles, and code paths holding unclosed connections/sessions. Avoid setting overly aggressive leak detection thresholds in production where legitimate slow transactions cause false alarms; tune thresholds to runtime policies.

## 16. Configuring multiple targets without mixing credentials or pools

An Order Service might use PostgreSQL for business data, Redis for cache, Inventory HTTP, and Kafka for events:

~~~text
OrderService
  ├── OrderRepository (JPA)
  │     └─ EntityManagerFactory → HikariCP → PostgreSQL
  ├── ProductCache (StringRedisTemplate)
  │     └─ LettuceConnectionFactory → Redis
  ├── InventoryGateway (RestClient)
  │     └─ HTTP RequestFactory → HTTP Pool → Inventory
  └── OrderEventPublisher (KafkaTemplate)
        └─ ProducerFactory → KafkaProducer → Kafka
~~~

Bean design:

- One `DataSource` per database/trust boundary.
- One `EntityManagerFactory`/transaction manager per persistence unit.
- One `RedisConnectionFactory` per Redis endpoint/credentials.
- One dedicated `RestClient`/HTTP transport per HTTP partner when authentication differs.
- One `KafkaTemplate`/`ProducerFactory` per serializer/cluster/security profile.
- One `RabbitTemplate`/AMQP `ConnectionFactory` per virtual host/broker/trust boundary.

**Never apply a global HTTP `Authorization` header across all clients**, never forward Inventory's bearer token to Payment, and never share JDBC credentials with brokers. When certificates or client secrets rotate, verify that factories, clients, and pools reload properly and check how long older connections live.

## 17. Observability: measuring the right layer instead of one "connection metric"

| Metric | Layer | Meaning |
| --- | --- | --- |
| `hikaricp.connections.active` | JDBC pool | Connections currently in use |
| `hikaricp.connections.idle` | JDBC pool | Idle connections available |
| `hikaricp.connections.pending` | JDBC pool | Threads waiting for a connection |
| HTTP client pool leased/pending | HTTP transport | Saturation/reuse per route |
| HTTP client response latency p95/p99 | HTTP operation | Remote/network duration |
| Redis command latency/errors | Redis client | Command latency, timeouts |
| Kafka producer request/batch/record metrics | Kafka producer | Batching, retries, broker acknowledgments |
| Kafka consumer lag/commit metrics | Kafka consumer | Read and processing progress |
| Rabbit connections/channels/unacked | AMQP | Resource usage, consumer backlog |
| Business confirmation lag | Application | Time from intent to remote confirmation |

Exact metric names depend on Micrometer, driver, Boot version, and registry; for example, Hikari is instrumented by Micrometer/Actuator when configured properly. Do not assume HTTP pool metrics exist automatically if a custom Apache connection manager has not been instrumented.

### 17.1. Distinguishing four types of latency

1. **Acquire latency:** time waiting to borrow a connection from a pool.
2. **Connect/TLS latency:** time to establish a new connection.
3. **Operation latency:** SQL query, HTTP exchange, Redis command, or broker publish.
4. **Business end-to-end latency:** time from receiving a command until the final side effect is confirmed.

If a dashboard only measures `repository.findById()` without watching pending pool waits or SQL locks, you may wrongly blame a "slow repository" when the real culprit is pool exhaustion.

### 17.2. Cardinality and secrets

Good tags: `component=jdbc`, `downstream=inventory`, `operation=reserve`, `outcome=timeout`. Never attach `orderId`, `eventId`, full JDBC URLs with passwords, tokens, dynamic client IPs, or raw SQL parameters as metric labels.

Logs must redact `Authorization` headers, database passwords, Redis ACL secrets, Kafka SASL credentials, and certificate private keys. Connection strings can contain embedded usernames/passwords/tokens; never log full configuration objects.

## 18. Testing every connection layer

### 18.1. Business unit tests without live connections

A service can be tested with fake/mock repositories and gateways:

~~~java
import static org.mockito.Mockito.*;
import org.junit.jupiter.api.Test;

class ConfirmOrderServiceTest {

    @Test
    void savesIntentForLaterPublishing() {
        OrderRepository repository = mock(OrderRepository.class);
        OutboxRepository outbox = mock(OutboxRepository.class);

        ConfirmOrderService service =
                new ConfirmOrderService(repository, outbox);

        service.confirm("ORD-100");

        verify(repository).confirm("ORD-100");
        verify(outbox).saveIntent("ORD-100");
    }
}
~~~

This is a **test skeleton**: `ConfirmOrderService` and `OutboxRepository` are application-defined types, not Spring APIs. Mock tests verify orchestration; they **do not verify SQL transactions or broker durability**.

### 18.2. JDBC and JPA slice/integration tests

Use `@JdbcTest`, `@DataJpaTest`, or integration tests with PostgreSQL Testcontainers as appropriate. Verify:

- `DataSource`/Hikari wiring and SQL migrations.
- Repository query mapping, constraints, and rollbacks.
- Transaction isolation/deadlocks and duplicate inserts.
- Timeouts and pool sizing under load.
- Zero connection leaks when exceptions occur.

H2 differs from PostgreSQL in SQL and transaction semantics; when testing `ON CONFLICT`, JSONB, row locking, or `SKIP LOCKED`, test against real PostgreSQL.

### 18.3. HTTP client tests

`MockRestServiceServer` verifies URIs, methods, headers, and bodies, **without opening sockets or TLS**, so it cannot test HTTP pooling, connect/read timeouts, CA trust, or mTLS.

Write integration tests using WireMock/MockWebServer/TLS-enabled test endpoints to verify:

- Pool reuse and saturation under high concurrency.
- Connect/read/pool acquisition timeouts.
- HTTP Basic/API key/OAuth2 per downstream.
- TLS hostname/SAN/CA chain verification.
- 429/503/timeout retries with stable `operationId` values.
- Redirects not leaking `Authorization` headers.

### 18.4. Redis Testcontainers

Verify `StringRedisTemplate` keys/values, TTLs, serializers, reconnects, and optional TLS. When testing transactions, Cluster, or Sentinel, the test environment must mirror real topology rather than relying on a standalone fake to validate Redis Cluster behavior.

### 18.5. Kafka/RabbitMQ Testcontainers

Verify:

- Producer serialization/config and confirms/acks.
- Consumer acknowledgment, retry/DLQ, and idempotency.
- Broker disconnect/restart and redelivery behavior.
- Concurrency and ordering by key/partition.
- Outbox replay causing no duplicate business side effects.

Single-node broker tests do not prove HA durability or quorum/ISR behavior on production clusters.

### 18.6. Testing isolated per-destination configuration

An important regression test: verify the Inventory client carries only Inventory credentials, the Pricing client has its own API key, database users lack DDL privileges unless required, and broker producers can only publish to authorized topics.

**Mocks can make a flow look valid on paper; only real transport tests verify connections, TLS, pooling, and protocol semantics.**

## 19. Common anti-patterns

| Anti-pattern | Why is it wrong? | Better alternative |
| --- | --- | --- |
| Creating a new `RestClient` per HTTP request | Hard to govern config/resource reuse | One client bean per partner |
| Creating a new `KafkaProducer` per event | Spawns extra sockets/threads, loses batching | `KafkaTemplate` + `ProducerFactory` |
| Holding a JDBC `Connection` in a singleton | Thread-safety issues and transaction leaks | `DataSource` + `JdbcTemplate` |
| Holding a raw `EntityManager` globally | Persistence context is not thread-safe | Spring JPA proxy/transactions |
| Assuming `RedisConnectionFactory` always pools | Lettuce uses a shared native connection by default | Measure first; enable pooling only if needed |
| Treating `RabbitTemplate` as an AMQP `Channel` | Misunderstands resource lifecycles | Let `ConnectionFactory` manage them |
| Treating Kafka producer cache as a JDBC pool | Kafka clients use a different network model | Tune batching, buffers, and producer factory |
| Enlarging the pool during downstream 503s | Amplifies load on failing target | Bulkheads, backoff, rate limiting |
| Holding a SQL transaction during a 15s HTTP call | Ties up JDBC Connections, invites deadlocks/cascades | Outbox/saga, short transactions |
| Retrying POST after timeout without idempotency | Can duplicate side effects | Stable `operationId` + status lookup |
| One HTTP client carrying all credentials | Tokens/keys leak across partners | Separate clients per trust boundary |
| Never closing custom `HttpClient`/`ConnectionProvider` | Leaks resources, threads, and sockets | Bean lifecycles / destroy methods |
| Watching only pool idle counts on dashboards | Misses pending waits, p99, and business lag | Monitor every boundary |
| Treating broker ACK as business completion | Confuses delivery semantics | Business completion metrics |

## 20. Thought questions

**Q1: Why cannot a Repository replace a Connection Pool?**

A repository defines data operations (like `findById`), whereas a pool manages the physical connections executing them. One repository can serve many concurrent requests only by borrowing JDBC Connections through the underlying infrastructure. Pool limits and transaction latency still apply regardless of how clean repository code looks.

**Q2: Should `JdbcTemplate` be instantiated inside each service method?**

Usually no. `JdbcTemplate` is thread-safe once configured and should be injected as a reusable bean. Instantiating it repeatedly may not open connections by itself, yet it fragments configuration and hurts testability; the underlying `DataSource`/pool remains the shared resource.

**Q3: I already have a `RestClient`, so do I need a pool?**

It depends on transport and load. `RestClient` is an API, not a specification of which pool is used. Under high request volumes, inspect the `ClientHttpRequestFactory`, underlying HTTP client, connection manager, latencies, and resource metrics before deciding.

**Q4: Why shouldn't a `RedisConnection` be stored in a singleton?**

Low-level connections can hold transaction/pipeline state or thread-safety constraints. `RedisTemplate` and `RedisConnectionFactory` manage lifecycle properly. If you use raw connections directly, follow the driver contract and release resources properly.

**Q5: Will increasing a pool from 20 to 100 fix HTTP timeouts?**

Only if the true bottleneck was pool acquisition wait and the downstream service has spare capacity. If the Inventory API is slow or overloaded, more active connections can worsen failures; use metrics to separate pool wait time from response latency.

**Q6: Once `RabbitTemplate` sends without error, can I mark the Order completed?**

No. Sending and publisher confirms reflect only broker acceptance and routing policies; the consumer must execute business effects and report completion per contract. You still need outbox, inbox, and idempotency.

## 21. Implementation checklist

- [ ] Distinguish entry APIs (client/template/repository), resource factories, and pools.
- [ ] Never infer that an object pools resources solely from the name `ConnectionFactory`.
- [ ] Reuse client/template/repository/factory Spring beans at appropriate scopes.
- [ ] Never share raw JDBC `Connection`, JPA `EntityManager`, JMS `Session`, or `KafkaConsumer` across threads.
- [ ] Configure JDBC with `DataSource`/HikariCP and short transactions.
- [ ] Wire HTTP clients with explicit request factories, connectors, and connection managers.
- [ ] Configure `RedisConnectionFactory`/Lettuce shared connections or pooling according to workload.
- [ ] Manage RabbitMQ channels, prefetch, and concurrency via `ConnectionFactory` and listener containers.
- [ ] Understand Kafka `ProducerFactory`/`ConsumerFactory`, batching, and acks without assuming JDBC pooling.
- [ ] Size pool and concurrency budgets against total replicas and downstream capacity.
- [ ] Separate pool acquisition, connect, read, and overall deadline timeouts.
- [ ] Assign clear ownership for connection lifecycles, shutdown, and secret rotation.
- [ ] Isolate credentials and TLS per trust boundary; avoid global tokens/headers.
- [ ] Never treat a SQL transaction as covering HTTP, Redis, Kafka, or RabbitMQ.
- [ ] Implement outbox, inbox/idempotency, and reconciliation for failure windows.
- [ ] Write unit and integration tests with real transports, databases, and brokers where needed.
- [ ] Monitor active/idle/pending counts, operation latency, retries, backlogs, and business completion.
- [ ] Never log secrets, sensitive SQL parameters, or high-cardinality metric labels.

**Takeaway:** Clients speak protocols; Templates remove operational boilerplate; Repositories organize domain data access; ConnectionFactory/DataSource provisions resources; Connection Pools bound and reuse physical resources. In Spring Boot, **these layers complement one another**, each with distinct lifecycles, thread-safety guarantees, timeouts, and transaction boundaries. Sound integration design starts by clarifying *who owns the connection*, *when it is borrowed and returned*, *what commits business state*, and *which layer failed*—not just giving beans tidy names.

## References

- [Spring Boot — Working with SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource, JDBC, JPA, and connection pools.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): JdbcTemplate and connection management.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction managers and thread-bound resources.
- [Spring Data JPA — Reference](https://docs.spring.io/spring-data/jpa/reference/): repositories, EntityManager, and persistence contexts.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP): maximumPoolSize, connectionTimeout, lifetimes, and metrics.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, WebClient, request factories, and HTTP Interfaces.
- [Reactor Netty — Connection Pool](https://projectreactor.io/docs/netty/release/reference/http-client.html#_connection_pool): ConnectionProvider and reactive HTTP resource management.
- [Spring Data Redis — Reference](https://docs.spring.io/spring-data/redis/reference/): RedisConnectionFactory, RedisTemplate, Lettuce.
- [Spring AMQP — Connections](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): CachingConnectionFactory, channels, and RabbitTemplate.
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): KafkaTemplate and ProducerFactory.
- [Spring for Apache Kafka — Message Listener Container](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): ConsumerFactory, listener concurrency, and acknowledgments.
- [Spring Framework — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): JmsTemplate, JMS connections, and transactions.
- [Spring Integration — Reference](https://docs.spring.io/spring-integration/reference/): channels, endpoints, and underlying adapters.
