# Phân biệt client, template, repository, connection factory và connection pool

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot kết nối HTTP client, cơ sở dữ liệu, cache, message broker và các adapter Spring Integration thành các luồng nghiệp vụ có cấu hình, hợp đồng dữ liệu, giao dịch, xử lý lỗi, chống trùng lặp, kiểm thử và quan sát được. Những hệ thống này đều “kết nối đến bên ngoài”, nhưng code thường có tên rất khác: `RestClient`, `JdbcTemplate`, `JpaRepository`, `LettuceConnectionFactory`, `KafkaTemplate`, `RabbitTemplate` hay `HikariDataSource`.

Một câu hỏi kiến trúc thường gặp: **đối tượng nào thật sự giữ kết nối, đối tượng nào mượn kết nối, đối tượng nào chỉ mô tả cách truy vấn dữ liệu và đối tượng nào nên được dùng lại giữa các requests?**

Bài thuộc chương **Cấu hình kết nối**, với chủ đề **Phân biệt client, template, repository, connection factory và connection pool**. Đây không phải năm tên gọi thay thế cho nhau. Chúng biểu diễn **những tầng trách nhiệm khác nhau**; một integration adapter có thể sử dụng đồng thời nhiều tầng.

Sau bài này, bạn có thể:

1. Nhận diện chính xác **client, template, repository, connection factory và connection pool** trong Spring Boot.
2. Vẽ đường đi từ service → repository/template/client → factory → connection/pool → hệ thống ngoài.
3. Phân biệt lifecycle và thread safety của abstraction với connection/session/channel thật.
4. Cấu hình ví dụ đúng cho JDBC/JPA, HTTP, Redis, Kafka, RabbitMQ và JMS.
5. Giải thích vì sao pool không tự cải thiện throughput vô hạn, và vì sao Kafka không dùng pool giống JDBC.
6. Tránh tạo connection/client tùy tiện cho mỗi HTTP request hoặc broker message.
7. Thiết kế transaction, retry, credential/TLS rotation, idempotency và backpressure đúng ranh giới.
8. Kiểm thử wiring/cấu hình, đo tài nguyên và xử lý sự cố pool exhaustion.

> **Nguyên tắc:** **Repository/Template/Client là API dùng từ ứng dụng; ConnectionFactory/DataSource là cách có được tài nguyên kết nối; Connection Pool là chiến lược quản lý số tài nguyên có thể sử dụng lại.** Không phải công nghệ nào cũng có đủ năm lớp hoặc gọi chúng bằng cùng một tên.

## 1. Tổng quan: năm vai trò khác nhau

~~~mermaid
flowchart TD
    A["OrderService / IntegrationFlow"] --> B["Repository hoặc Template hoặc Client"]
    B --> C["ConnectionFactory / DataSource / Client factory"]
    C --> D["Connection Pool / shared transport resources"]
    D --> E["Connection / Channel / Session / Producer"]
    E --> F["PostgreSQL / HTTP API / Redis / Broker"]
    A -.-> G["Transaction, retry, idempotency"]
    D -.-> H["Timeout, saturation, metrics"]
~~~

Sơ đồ mang tính **khái niệm**, không nói rằng mọi thư viện đều có đúng thứ tự đối tượng như vậy. Ví dụ Kafka `ProducerFactory` tạo producer được cache; Kafka không có một JDBC-style connection pool riêng để ứng dụng mượn `Connection`.

| Khái niệm | Câu hỏi nó trả lời | Ví dụ Spring | Không tự đảm bảo |
| --- | --- | --- | --- |
| **Client** | “Gửi protocol request đến dịch vụ nào và nhận response thế nào?” | `RestClient`, `WebClient`, Kafka client, Redis client | Business authorization, transaction nhiều hệ |
| **Template** | “Dùng một API thống nhất thay cho boilerplate resource/protocol như thế nào?” | `JdbcTemplate`, `RedisTemplate`, `KafkaTemplate`, `RabbitTemplate`, `JmsTemplate` | Cứ gọi là template thì sẽ có pool riêng |
| **Repository** | “Truy cập/ghi dữ liệu theo domain model thế nào?” | `JpaRepository`, `CrudRepository`, Spring Data Redis repositories | Trừu tượng hóa tất cả lỗi mạng/transaction |
| **Connection factory** | “Lấy/tạo connection, session hoặc producer theo cấu hình nào?” | `RedisConnectionFactory`, AMQP `ConnectionFactory`, `ProducerFactory` | Mọi factory đều có pool; mọi connection đều thread-safe |
| **Connection pool** | “Bao nhiêu physical resources có thể tồn tại, được mượn/trả và tái sử dụng?” | HikariCP, Apache HttpClient pool, pool của JMS provider | Exactly-once, request ordering, business success |

**Client** có thể là một đối tượng API cấp cao (Spring `RestClient`) hoặc một client kết nối mạng cấp thấp (Apache `CloseableHttpClient`). **Factory** có thể tạo đối tượng transport thay vì connection trực tiếp. Khi đọc code, cần xác định *loại resource được tạo* chứ không suy luận chỉ từ hậu tố `Factory`.

### 1.1. Không phải quan hệ “chọn một trong năm”

Ví dụ cùng một request:

~~~text
OrderService
  -> OrderRepository
       -> JPA EntityManager proxy
            -> EntityManagerFactory
                 -> DataSource/HikariCP
                      -> JDBC Connection -> PostgreSQL
~~~

Ở một HTTP call khác:

~~~text
OrderService
  -> InventoryGateway
       -> RestClient
            -> ClientHttpRequestFactory
                 -> Apache HttpClient
                      -> PoolingHttpClientConnectionManager
                           -> TCP/TLS connection -> Inventory API
~~~

Ở Redis:

~~~text
ProductCache
  -> StringRedisTemplate
       -> RedisConnectionFactory
            -> Lettuce native client/shared connection
                 -> TCP/TLS -> Redis
~~~

Một Repository có thể được triển khai dựa trên Template hoặc một layer khác; không phải “repository và template luôn xếp nối tiếp nhau”.

## 2. Những đối tượng nào nằm ở tầng nào?

### 2.1. Client: API gọi một giao thức

Một client biết **cách** nói chuyện với một dịch vụ: host/base URL, serializer, protocol, headers, authentication, HTTP method, timeout và response mapping. Ví dụ:

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

`InventoryResponse` là DTO contract minh họa. `RestClient` là entrypoint API; chính `ClientHttpRequestFactory` và HTTP transport phía dưới quyết định connection reuse.

Một object client có thể **không giữ một socket chuyên dụng** ngay lúc tạo. Nhiều clients tạo kết nối lười khi request đầu tiên xảy ra; nhiều requests có thể dùng lại kết nối trong pool.

### 2.2. Template: gom boilerplate thành operations an toàn hơn

`JdbcTemplate` giúp:

- Lấy connection từ `DataSource` phù hợp transaction.
- Tạo `PreparedStatement` và binding parameters.
- Chạy query/update và map `ResultSet`.
- Đóng/trả tài nguyên đúng, chuyển SQL exceptions sang Spring data-access exceptions.

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

Một `JdbcTemplate` thường được cấu hình một lần và dùng lại. Nó **không phải một JDBC Connection**. Cùng logic, `RedisTemplate` đóng gói thao tác key/value, `KafkaTemplate` đóng gói producer send, `RabbitTemplate` đóng gói AMQP send/receive.

### 2.3. Repository: giao diện dữ liệu theo domain

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface OrderRepository
        extends JpaRepository<OrderEntity, Long> {

    Optional<OrderEntity> findByExternalId(
            String externalId);
}
~~~

Spring Data tạo implementation/proxy cho interface repository, dựa trên underlying persistence API và transaction infrastructure. Repository thể hiện **hành vi truy xuất dữ liệu**, không phải một network connection hoặc pool.

Không đồng nhất `JpaRepository` với `JdbcTemplate`. `JpaRepository` sử dụng JPA/ORM với persistence context, dirty checking, lazy loading và entity lifecycle; `JdbcTemplate` làm việc trực tiếp với SQL/rows. Một ứng dụng có thể dùng cả hai vì nhu cầu truy vấn và consistency khác nhau.

### 2.4. Connection factory: cấp/tạo đối tượng kết nối

Trong Redis:

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

`RedisConnectionFactory` là hạ tầng để templates/repositories lấy Redis connections. Service nghiệp vụ thường **không gọi trực tiếp `getConnection()`**; dùng `StringRedisTemplate` hoặc abstraction phù hợp để tránh tự xử lý lifecycle.

Trong RabbitMQ, `CachingConnectionFactory` tạo và cache AMQP connections/channels. Trong JMS, `ConnectionFactory` tạo `Connection`/`JMSContext` theo provider. Trong Kafka, `ProducerFactory`/`ConsumerFactory` cung cấp clients, không phải `java.sql.Connection`.

### 2.5. Connection pool: giới hạn và tái sử dụng tài nguyên

Một pool như HikariCP quản lý các JDBC Connections; Apache HttpClient pool quản lý HTTP connections. Các yếu tố:

- Max connections tổng và theo destination.
- Thời gian chờ **mượn connection**.
- Idle timeout, maximum lifetime và eviction.
- Health/validation, stale connections.
- Metrics leased/active, idle, pending.
- Shutdown/reconfiguration và certificate/credential rotation.

Pool không chuyển một thao tác blocking thành non-blocking, không làm downstream tăng capacity và không tự rollback business transaction.

## 3. Mô hình lựa chọn nhanh theo hệ thống

| Công nghệ | Entry API ứng dụng | Factory/resource provider | Pool/caching điển hình |
| --- | --- | --- | --- |
| JDBC | `JdbcTemplate`, Spring Data JDBC repo | `DataSource` | HikariCP |
| JPA/Hibernate | `JpaRepository`, `EntityManager` proxy | `EntityManagerFactory` + `DataSource` | JDBC pool ở DataSource |
| HTTP đồng bộ | `RestClient`, HTTP interface proxy | `ClientHttpRequestFactory` | Apache HttpClient/other transport pool |
| HTTP reactive | `WebClient` | `ClientHttpConnector` | Reactor Netty connection provider |
| Redis | `StringRedisTemplate`, `RedisTemplate`, Redis repository | `RedisConnectionFactory` | Lettuce shared connection/pool khi cấu hình |
| Kafka producer | `KafkaTemplate` | `ProducerFactory` | Cache/reuse KafkaProducer, **không** JDBC pool |
| Kafka consumer | `@KafkaListener`/container | `ConsumerFactory` | Consumer instances theo concurrency |
| RabbitMQ | `RabbitTemplate`, `@RabbitListener` | AMQP `ConnectionFactory` | Connection/channel cache |
| JMS | `JmsTemplate`, `@JmsListener` | JMS `ConnectionFactory` | Provider pool / `CachingConnectionFactory` |
| Spring Integration | `IntegrationFlow`, adapters | Underlying client/template/factory | Theo transport bên dưới |

Đừng áp đặt một pattern duy nhất: “mọi kết nối đều có `ConnectionFactory` và `ConnectionPool`”. Tên `DataSource` trong JDBC chính là abstraction cấp connection; `EntityManagerFactory` tạo EntityManager, chứ không cấp TCP socket trực tiếp.

## 4. JDBC: DataSource, HikariCP và JdbcTemplate

### 4.1. Đường đi một câu lệnh SQL

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

`Connection.close()` trên pooled connection thường **trả connection về pool**, không đóng socket vật lý ngay. Nếu connection đang tham gia Spring-managed transaction, việc release thực tế xảy ra theo transaction lifecycle.

### 4.2. Spring Boot cấu hình DataSource

Với starter JDBC/JPA và HikariCP khả dụng, Spring Boot thường auto-configure `DataSource` theo `spring.datasource.*`. Ví dụ:

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

Với Hikari numeric timeouts như trên, đơn vị thông thường là **mili giây**, cần đối chiếu Spring Boot binding và Hikari configuration theo version. Password không được hardcode. JDBC URL phải cấu hình TLS/server identity theo driver và môi trường, không mặc định toàn bộ connection được bảo mật chỉ vì server nằm trong mạng nội bộ.

### 4.3. JdbcTemplate là bean dùng lại

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

`OrderJdbcRepository` là một **repository theo thiết kế ứng dụng**, nhưng sử dụng template và SQL thủ công. Nó không tự động là Spring Data `JpaRepository`. Repository này nên tách business query ra khỏi orchestration của controller/service.

**Thread safety:** `JdbcTemplate` được thiết kế thread-safe khi đã cấu hình xong. `java.sql.Connection` và `PreparedStatement` không nên bị giữ trong một singleton service để các threads dùng chung; hãy cho Spring/transaction infrastructure quản lý.

### 4.4. DataSource là factory và pooling boundary

`javax.sql.DataSource` có method `getConnection()`; đối tượng được inject có thể chính là Hikari `DataSource`. Không nhất thiết cần thêm một bean “ConnectionFactory” cho JDBC.

Một lỗi thường gặp:

~~~java
// Anti-pattern: không mở và giữ một Connection chung trong singleton.
class UnsafeDao {
    private java.sql.Connection sharedConnection;
}
~~~

Hậu quả gồm transaction chồng nhau, connection stale, session settings bị rò và đa luồng race. Thay bằng `JdbcTemplate` hoặc dùng `DataSourceUtils`/transaction API đúng khi cần low-level JDBC.

### 4.5. Connection pool sizing không theo số HTTP requests đơn thuần

Nếu ứng dụng có 10 replicas và mỗi replica đặt `maximum-pool-size=20`, tổng số connections hướng tới database có thể xấp xỉ 200 **chưa tính các ứng dụng khác**. Khi PostgreSQL chỉ cho phép số connections thấp, tăng pool sẽ gây connection exhaustion.

Một sizing đầu tiên phải xét:

- Tổng connection budget của DB.
- Số replicas/pods.
- Thời gian giữ JDBC connection trong một transaction.
- SQL latency, lock contention và workload.
- Burst concurrency và pool wait p95/p99.
- Số nguồn dữ liệu (read/write, multi-tenant).
- Batch jobs và scheduled integration workers.

Tăng pool không làm truy vấn SQL chậm trở nên nhanh; thường cần index/query plan, transaction ngắn và concurrency cap.

## 5. JPA: Repository, EntityManagerFactory và pool JDBC

JPA bổ sung một tầng khác:

~~~text
OrderService
  -> JpaRepository<OrderEntity, Long>
  -> Spring Data JPA repository proxy
  -> EntityManager (persistence context cho transaction)
  -> EntityManagerFactory
  -> DataSource/HikariCP
  -> JDBC Connection -> PostgreSQL
~~~

### 5.1. EntityManagerFactory khác DataSource

| Đối tượng | Chức năng |
| --- | --- |
| `EntityManagerFactory` | Factory thread-safe để tạo EntityManagers/persistence contexts |
| `EntityManager` | Persistence context, quản lý entities và dirty checking |
| Spring Data `JpaRepository` | API CRUD/query trên entities |
| `DataSource` | Cấp JDBC Connection cho Hibernate/JPA |
| HikariCP | Quản lý JDBC connections vật lý |

**`EntityManager` không thread-safe.** Nhưng `@PersistenceContext` được inject trong Spring thường là một **proxy** chuyển thao tác tới EntityManager gắn với transaction/thread phù hợp. Không tạo một `EntityManager` rồi lưu vào singleton và chia sẻ giữa requests.

### 5.2. Transaction boundary

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

Ví dụ này giả định `OrderEntity.confirm()` thay đổi state được JPA dirty checking lưu khi transaction commit. `@Transactional` thường dùng transaction manager phù hợp (ví dụ `JpaTransactionManager`). **Không giữ transaction mở khi gọi HTTP/broker chậm** nếu có thể tránh.

**Không nhầm:** JPA repository proxy có thể được dùng lại giữa threads, nhưng EntityManager/persistence context làm việc theo transaction. JDBC Connection vẫn được quản lý bởi DataSource/pool.

## 6. HTTP đồng bộ: RestClient, request factory và connection manager

~~~mermaid
flowchart TD
    A["InventoryGateway"] --> B["RestClient"]
    B --> C["ClientHttpRequestFactory"]
    C --> D["Apache HttpClient hoặc JDK transport"]
    D --> E["Pooling connection manager"]
    E --> F["TCP/TLS socket tới Inventory API"]
~~~

`RestClient` là API cấp cao để tạo HTTP requests. `ClientHttpRequestFactory` quyết định implementation transport; một số factories dùng Apache HttpClient 5, một số dùng JDK HttpClient hoặc SimpleClientHttpRequestFactory. **Không phải mọi request factory đều có cùng pooling semantics**.

### 6.1. Tạo RestClient theo downstream

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

`base-url` nên là cấu hình theo môi trường, không được cho client request tự đổi sang một URL nội bộ tùy ý. Nếu cần TLS/mTLS, HTTP Basic, API key hoặc OAuth2, gắn vào **đúng client/transport** của downstream đó, không tạo global Authorization header.

### 6.2. Pool HTTP với Apache HttpClient 5

Ở Spring Framework 6.x có `HttpComponentsClientHttpRequestFactory` sử dụng Apache HttpClient 5, khi module `httpclient5` tương thích được thêm vào build.

~~~groovy
dependencies {
    implementation 'org.apache.httpcomponents.client5:httpclient5'
}
~~~

Ví dụ cấu hình (minh họa cho các phiên bản Apache HttpClient 5/Spring 6 tương thích):

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

Hai `@Bean` methods nằm trong một class `@Configuration`. Các timeouts (pool acquisition, connect, response) **phải cấu hình bổ sung** ở request factory hoặc Apache HttpClient connection/request configs theo đúng phiên bản. Code trên chỉ làm rõ **sở hữu pool/transport**. Các versions mới có thể thay đổi chữ ký `ConnectionConfig`, `RequestConfig` và TLS strategy; không copy cấu hình HttpClient 4 vào HttpClient 5.

### 6.3. Phân biệt bốn loại timeout

| Timeout | Chờ gì? | Thường ở tầng |
| --- | --- | --- |
| Pool acquisition | Mượn một connection rảnh | HTTP connection manager/request config |
| TCP connect | Thiết lập socket đến endpoint/proxy | HTTP transport/connection config |
| TLS handshake | Xác minh certificate và thiết lập TLS | HTTP transport/TLS strategy |
| Read/response | Chờ response bytes | HTTP request/connection/socket config |
| Total operation deadline | Bao gồm các bước trên và retries | Application/adapter policy |

Nếu `maxPerRoute=20` và 200 threads cùng gọi Inventory API, các threads có thể chờ pool. Chỉ tăng `readTimeout` không giải quyết **connection request timeout**. Nếu phía Inventory API chậm, pool quá lớn có thể khuếch đại tải và làm downstream sập.

### 6.4. Thread safety và lifecycle HTTP

`RestClient` sau khi build có thể tái sử dụng an toàn giữa các callers theo contract của framework; tạo một bean riêng cho mỗi downstream phù hợp hơn việc dựng mới mỗi request. Underlying `CloseableHttpClient` thường thread-safe và nên đóng khi application shutdown.

**Một RestClient không nhất thiết sở hữu một HTTP pool riêng**: điều đó phụ thuộc request factory và transport được inject. Khi dùng nhiều clients có credentials khác nhau, cân nhắc tách request factories/connection pools theo trust boundary.

## 7. HTTP reactive: WebClient và Reactor Netty ConnectionProvider

`WebClient` là HTTP API dạng reactive. Khi sử dụng Reactor Netty, tầng quản lý tài nguyên gồm:

~~~text
WebClient
  -> ReactorClientHttpConnector
       -> Reactor Netty HttpClient
            -> ConnectionProvider / shared event-loop resources
                 -> TCP/TLS channels
~~~

`WebClient` không phải tự động “một socket cho mỗi Mono”. Request được thực hiện khi publisher được subscribe; connections có thể được tái sử dụng trong pool do HTTP connector quản lý.

### 7.1. Ví dụ Reactor Netty pool có giới hạn

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

Đây là cấu hình một **ConnectionProvider riêng**; API cụ thể phải đối chiếu Reactor Netty version đang chạy. Provider riêng cần được dispose khi shutdown. Trong Boot, nếu dùng resource factory được auto-configure, cần tránh tạo nhiều event loops/pools không chủ đích.

**Reactive không đồng nghĩa không giới hạn:** vẫn có TCP sockets, pool acquisition, CPU, memory và remote concurrency. Nếu pipeline phát hàng nghìn requests, phải giới hạn `flatMap` concurrency/buffer theo khả năng downstream, không chỉ tăng pool.

### 7.2. WebClient là client; pool không ở WebClient

Một code như:

~~~java
WebClient client = WebClient.builder()
        .baseUrl("https://inventory.example.org")
        .build();
~~~

không cho biết rõ các giới hạn max connections, pending acquire hay TLS lifecycle. Muốn chẩn đoán pool exhaustion, phải kiểm tra **connector/provider/transport** thật sự đang dùng, không chỉ nhìn bean `WebClient`.

## 8. Redis: RedisConnectionFactory, RedisTemplate và shared connections

Trong Spring Data Redis, hai đối tượng thường bị nhầm:

- `RedisConnectionFactory`: factory để cấp kết nối Redis.
- `RedisTemplate` / `StringRedisTemplate`: API thực hiện các Redis operations.

Ví dụ:

~~~mermaid
flowchart LR
    S["ProductCacheService"] --> T["StringRedisTemplate"]
    T --> F["RedisConnectionFactory"]
    F --> L["Lettuce native client/connection"]
    L --> R["Redis server/cluster"]
~~~

### 8.1. Cấu hình Spring Boot Redis

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

Trong production, phải cấu hình TLS/ACL và topology (standalone, Sentinel hoặc Cluster) theo hệ thống thực. `spring.data.redis.*` là namespace thông dụng ở Boot 3, nhưng các dòng Boot/driver khác có thể có cấu hình khác. Password có thể bị bỏ nếu môi trường dùng identity/authentication khác; không hardcode secret.

### 8.2. StringRedisTemplate dùng trong business adapter

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

`StringRedisTemplate` dùng serializers cho string keys/values. Với domain objects, cần khai báo JSON serialization/versioning một cách có kiểm soát, không mặc định Java native serialization an toàn hoặc tương thích.

### 8.3. LettuceConnectionFactory có luôn dùng pool không?

**Không.** Với Spring Data Redis/Lettuce, `LettuceConnectionFactory` có thể sử dụng một shared native connection cho nhiều thao tác non-blocking và cơ chế khác cho blocking/transactional operations. Việc có `LettuceConnectionFactory` **không chứng minh** mỗi request mượn một socket từ một pool kiểu HikariCP.

Chỉ khi workload/topology yêu cầu pooling và client hỗ trợ, mới cấu hình pool tương ứng, thường cần `commons-pool2`. Ví dụ Boot Lettuce pool options:

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

Các options này chỉ có ý nghĩa nếu pool thực sự được tạo và sử dụng theo config/driver/version. Không “bật pool để tăng hiệu năng” theo thói quen: quá nhiều connections có thể tăng overhead trên Redis server.

### 8.4. Thread safety

`RedisTemplate` được thiết kế để dùng lại sau khi cấu hình. **RedisConnection cấp thấp không nên bị chia sẻ tùy tiện giữa threads**, đặc biệt với transaction/pipeline/blocking operations. Lettuce native connections có những khả năng thread-safety riêng, nhưng adapter và transaction wrapper ở Spring Data vẫn có lifecycle/contract cần tuân thủ.

Transaction SQL không tự bao gồm Redis write. Nếu SQL update commit nhưng Redis invalidation thất bại, cần cache-aside TTL, event-driven invalidation/outbox hoặc reconciliation; pool không giải quyết consistency.

## 9. RabbitMQ: CachingConnectionFactory, RabbitTemplate và Channel

RabbitMQ/AMQP tạo thêm một tầng: **TCP connection** mang nhiều **AMQP channels**. Spring AMQP thường dùng `CachingConnectionFactory` để tái sử dụng chúng.

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

### 9.1. Cấu hình Spring Boot

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

`cache.channel.size` là mục tiêu cache channels theo cấu hình; **không mặc định là giới hạn tuyệt đối số channels đồng thời**. Giới hạn có thể cần `channelCheckoutTimeout` và các settings tương ứng. Các thuộc tính khác như connection cache mode/connection limit cần được xem trong bối cảnh Spring AMQP version và broker limits.

### 9.2. RabbitTemplate dùng lại

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

`RabbitTemplate` là abstraction cấp cao, thường có thể tái sử dụng trong singleton bean. Nó **không phải một AMQP Channel** cố định; connection/channel management thuộc `ConnectionFactory`/template và messaging infrastructure. Nếu cần publisher confirms, returns, message persistence và retries, phải cấu hình thêm broker/template tương ứng.

### 9.3. Publish và consume là hai lifecycle khác nhau

- Producer `RabbitTemplate` gửi message; publisher confirm nếu bật chỉ chứng minh theo broker confirm semantics.
- Listener container (`@RabbitListener`) có channels, concurrency, prefetch và ACK policy riêng.
- Consumer `basicAck`/`basicNack` quyết định settlement của message.
- Broker exchange/queue binding và durability ảnh hưởng khả năng delivery.

Không suy luận rằng một `RabbitTemplate.convertAndSend(...)` return không lỗi chứng minh consumer đã commit SQL. Đây là bài toán **producer ack vs consumer completion**, không phải connection pool.

### 9.4. Pool/channel caches không cứu poison message

Nếu handler liên tục NACK requeue một event không hợp lệ, tăng channel cache chỉ làm tăng lượng retry hoặc memory; cần DLQ, backoff, dedupe và schema validation. Với CPU/DB overload, điều chỉnh listener concurrency/prefetch và downstream capacity trước khi tăng connections.

## 10. Kafka: ProducerFactory/ConsumerFactory không phải JDBC Connection Pool

Kafka là nơi tên **factory/template** rất giống Spring Data nhưng mô hình tài nguyên khác:

~~~text
KafkaTemplate<K,V>
  -> ProducerFactory<K,V>
       -> KafkaProducer<K,V>
            -> Network connections, buffers, sender thread
                 -> Kafka broker/topic partitions

@KafkaListener container
  -> ConsumerFactory<K,V>
       -> KafkaConsumer<K,V> for each consumer instance
            -> poll / group assignment / offset commit
~~~

### 10.1. Spring Boot Kafka config

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

Broker TLS/SASL/mTLS properties và ACLs phải được cấu hình theo môi trường. `acks=all` là producer broker acknowledgement policy, không phải bằng chứng consumer đã xử lý.

### 10.2. KafkaTemplate và ProducerFactory

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
                        // Fail/unknown outcome; điều phối retry có kiểm soát.
                        return;
                    }
                    // Broker accepted theo acks config.
                    // KHÔNG đánh dấu consumer processed ở đây.
                });
    }
}
~~~

Ví dụ Spring Kafka 3.x+ với `CompletableFuture`. `KafkaTemplate` được dùng lại an toàn, còn `ProducerFactory` quản lý producer instances/caching theo config. **Không tạo mới một KafkaProducer cho mỗi event**, vì producer có network connections, buffers, threads và batching.

### 10.3. KafkaConsumer không thread-safe

Kafka consumer có lifecycle polling và group membership. Một `KafkaConsumer` không được cho nhiều threads gọi `poll()` hoặc mutate cùng lúc tùy tiện. Spring Kafka listener containers thường quản lý consumer instances theo concurrency/partitions.

Tăng `@KafkaListener` concurrency không đồng nghĩa tạo 100 JDBC Connections, nhưng có thể tạo nhiều consumer clients/network connections và tăng áp lực lên database downstream. **Số partition giới hạn song song hữu ích trong một consumer group**.

### 10.4. Kafka producer cache không phải generic connection pool

`DefaultKafkaProducerFactory` có thể reuse producer(s), đặc biệt cho transactional producer contexts, nhưng API này không giống HikariCP với `borrow Connection → execute SQL → return Connection`. Producer multiplexes records/batches qua broker connections và internal sender thread. Tối ưu cần xem:

- `batch.size`, `linger.ms`, `buffer.memory`.
- `acks`, retries/idempotence.
- Delivery timeout, inflight requests.
- Number of partitions/brokers.
- Producer/consumer concurrency.
- Serialization overhead và quota broker.

Cố tìm “Kafka connection pool maximum size” giống HikariCP thường dẫn đến cấu hình sai mục tiêu.

## 11. JMS: ConnectionFactory, JmsTemplate, Session và Pool

JMS gần với mẫu ConnectionFactory truyền thống hơn:

~~~text
JmsTemplate
  -> JMS ConnectionFactory
       -> Connection/JMSContext
            -> Session
                 -> Producer/Consumer
                      -> Queue/Topic
~~~

### 11.1. Cấu hình và lifecycle

`JmsTemplate` đóng gói việc lấy connection/session, gửi message, convert payload và giải phóng resources. Spring Boot có thể cấu hình JMS infrastructure khi provider/starter phù hợp.

### 11.2. Vì sao JMS Session không chia sẻ tùy tiện?

JMS `Session` thường có quy tắc single-threaded/lifecycle; không lưu một session làm biến global rồi dùng chung trong pool HTTP threads. `JmsTemplate` và listener container dùng factory/session handling đúng theo framework.

Có thể dùng provider pool hoặc `org.springframework.jms.connection.CachingConnectionFactory` để cache sessions/producers/consumers theo cấu hình, nhưng **không phải tất cả use cases đều nên cache consumers** (đặc biệt với durable subscriptions/dynamic destination). Cache sizing/lifecycle cần dựa trên provider, transaction và listener container.

### 11.3. Transaction boundary

`JmsTemplate` hoặc JMS session transaction không tự commit cùng một `@Transactional` JDBC nếu transaction manager chỉ quản lý database. Cần XA/JTA khi được thiết kế phù hợp hoặc transactional outbox/inbox để tránh mất/duplicate event.

## 12. Bean scopes, lifecycle và thread safety

Một lỗi phổ biến là nhìn thấy `@Bean` và tưởng đối tượng được tạo là một connection dành cho một request. Spring singleton bean là **một đối tượng service/adapter được chia sẻ**, không đồng nghĩa một socket duy nhất hoặc một transaction duy nhất.

| Đối tượng | Có nên inject singleton? | Có nên chia sẻ low-level resource giữa threads? |
| --- | --- | --- |
| `RestClient` | Có, với cấu hình bất biến sau build | Transport/pool làm việc theo contract |
| `WebClient` | Có | Không chia sẻ mutable request state |
| `JdbcTemplate` | Có | Không giữ một JDBC Connection global |
| `JpaRepository` proxy | Có | Không chia sẻ raw EntityManager |
| `EntityManagerFactory` | Có | Factory thread-safe; EntityManager không |
| `RedisTemplate` | Có, sau cấu hình | RedisConnection transaction/pipeline cần lifecycle riêng |
| `LettuceConnectionFactory` | Có | Tuân thủ driver connection semantics |
| `RabbitTemplate` | Có, cấu hình ổn định | Không tự giữ RabbitMQ Channel global |
| `CachingConnectionFactory` | Có | Factory quản lý channels/connections |
| `KafkaTemplate` | Có | KafkaProducer được factory quản lý; KafkaConsumer không thread-safe |
| `JmsTemplate` | Có | JMS Session không chia sẻ tùy tiện |
| `DataSource` (Hikari) | Có | Borrow JDBC Connection theo thao tác/transaction |

**Quy tắc mặc định:** Tạo factory, template, repository và configured client **một lần theo application scope**; lấy low-level connection/session theo từng operation/transaction do framework quản lý. Có ngoại lệ theo provider, nhưng phải chứng minh bằng tài liệu và kiểm thử thread safety.

### 12.1. Sở hữu tài nguyên và shutdown

Ai tạo resource thì phải có lifecycle đóng resource:

- HikariDataSource được Spring đóng khi context shutdown.
- Apache `CloseableHttpClient` custom bean có destroy method, pool manager được giải phóng.
- Reactor Netty `ConnectionProvider` riêng cần dispose.
- Rabbit `ConnectionFactory`/listener containers đóng channels/connections.
- Kafka producer/consumer factories, listener containers đóng clients/threads.
- Client cache hoặc credential rotation có thể cần rebuild connections/pools.

Không tạo một `CloseableHttpClient` mỗi lần gọi rồi quên `close()`; socket/thread leaks sẽ bộc lộ dưới tải thay vì trong unit tests.

## 13. Cấu hình connection và pool theo “ngân sách” tổng

Một ứng dụng đồng thời truy vấn SQL, Redis, Inventory HTTP và phát Kafka có **nhiều resources bị giới hạn độc lập**:

~~~text
HTTP inbound threads / concurrency
        |
        +-- JDBC pool: 16 active max
        +-- Inventory HTTP connections: 20 per route
        +-- Redis connections/shared native client
        +-- Kafka producer buffers/network threads
        +-- RabbitMQ channels/listener concurrency
~~~

Nếu 100 requests cùng lúc, database pool chỉ có 16, Inventory HTTP pool có 20, việc nâng JDBC pool lên 100 không giải quyết Inventory 503. Nếu giữ JDBC transaction trong lúc gọi HTTP chậm, JDBC connections có thể bị chiếm lâu, gây cascade failures.

### 13.1. Ví dụ concurrency budget

Giả sử 8 replicas:

| Resource | Per-instance limit | Tổng lý thuyết | Hậu quả nếu tăng vô hạn |
| --- | ---: | ---: | --- |
| JDBC connections | 12 | 96 | Vượt max_connections hoặc tăng lock contention |
| Inventory HTTP per-route | 16 | 128 | Làm Inventory API quá tải |
| Worker item threads | 8 | 64 | Backlog/CPU pressure |
| Rabbit listener concurrency | 4 | 32 consumers | Broker/DB nhận tải quá mức |

Các con số chỉ minh họa. Tổng thực tế còn phụ thuộc autoscaling, lưu lượng từ ứng dụng khác, số routes, socket reuse, DB reserve và broker quotas.

### 13.2. Pool size khác queue size

- Pool size giới hạn số physical resources được sử dụng.
- Queue size giới hạn số tasks/requests đang chờ.
- Timeout giới hạn một giai đoạn chờ.
- Bulkhead/concurrency cap giới hạn số operations đang chạy.
- Circuit breaker từ chối tạm thời khi downstream lỗi.
- Rate limiter kiểm soát QPS.

Một pool lớn cùng queue không giới hạn có thể tích lũy yêu cầu trong RAM, tăng p99 latency và gây OOM. Ưu tiên bounded resources và deadline rõ.

### 13.3. Các đơn vị timeout dễ bị nhầm

| Property | Đơn vị/ý nghĩa thường gặp |
| --- | --- |
| Hikari `connection-timeout` | Wait pool connection, thường millis với số nguyên |
| Hikari `max-lifetime` | Lifetime connection, không phải transaction timeout |
| HTTP connect timeout | Thời gian mở TCP connection, không phải total response |
| HTTP response timeout | Chờ response/dữ liệu, không phải toàn bộ retries |
| Reactor Netty `pendingAcquireTimeout` | Chờ slot connection pool |
| Redis `timeout` | Command/operation timeout theo driver config |
| Kafka `delivery.timeout.ms` | Producer delivery deadline, không phải consumer commit |
| Rabbit listener prefetch | Số unacked deliveries, không phải connection count |

Khi dùng YAML kiểu `2s` hoặc `2000`, phải biết binder property type của đúng Spring Boot/driver version; tránh nhầm mili giây và giây.

## 14. Connection pool không phải transaction manager

Một transaction bảo đảm điều gì phụ thuộc resource và manager:

~~~mermaid
flowchart LR
    A["OrderService"] --> T["SQL @Transactional"]
    T --> D["JdbcTemplate / JpaRepository"]
    D --> P["Hikari DataSource → PostgreSQL"]
    A --> H["RestClient → ERP"]
    A --> K["KafkaTemplate → Kafka"]
    A --> R["RedisTemplate → Redis"]
    T -. "Không tự rollback" .-> H
    T -. "Không tự rollback" .-> K
    T -. "Không tự rollback" .-> R
~~~

`@Transactional` với JDBC/JPA manager thường quản lý một database transaction; không kéo HTTP request, Redis update hoặc Kafka producer send vào cùng ACID transaction.

### 14.1. Một anti-pattern

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

Ví dụ chỉ minh họa bẫy thiết kế, các classes/fields là của application. Các lỗi có thể xảy ra:

- HTTP Inventory đã commit nhưng SQL transaction rollback.
- SQL transaction giữ JDBC Connection trong khi HTTP timeout.
- Kafka publish async có thể thành công dù SQL commit thất bại.
- Hikari pool hết connections do transactions quá dài.

Tăng connection pool không giải quyết vấn đề này; cần đổi architecture.

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

Trong SQL transaction, ghi business state và durable intent. Sau commit, outbox relay sử dụng client/template tương ứng để publish/gọi API. Nếu process crash, intent vẫn tồn tại để retry.

**Outbox thường là at-least-once.** Nếu broker nhận message nhưng relay crash trước khi ghi kết quả, relay có thể phát lại. Consumer/partner cần idempotency key ổn định, inbox/unique constraint hoặc status lookup. Connection factory và pool chỉ quản lý tài nguyên, không bảo đảm exactly-once.

### 14.3. Redis cache consistency

`RedisTemplate.opsForValue().set(...)` không atomic với PostgreSQL commit. Nếu SQL update thành công nhưng Redis write thất bại, cache có thể stale. Sử dụng TTL, cache-aside invalidation, transactional outbox/event hoặc versioning theo business requirements.

### 14.4. Kafka/Rabbit producer ACK và consumer completion

`KafkaTemplate.send(...)` future thành công hoặc Rabbit publisher confirm ACK chứng minh **broker accepted theo policy**; không chứng minh consumer đã commit SQL. Consumer ACK/offset commit cũng không tự bảo đảm business transaction đã hoàn tất nếu ứng dụng ACK quá sớm.

## 15. Lỗi, retry và pool exhaustion

### 15.1. Ba nhóm lỗi khác nhau

| Nhóm | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **Acquire resource** | Hikari connection wait timeout, HTTP pool pending timeout | Giới hạn concurrency, xem pool metrics, query/handler latency |
| **Establish connection** | DNS fail, TCP refused, TLS certificate mismatch | Kiểm tra endpoint, CA/SAN, network, proxy |
| **Operation/protocol** | SQL deadlock, HTTP 503, Redis command timeout, broker NACK | Phân loại transient/permanent, retry/idempotency |

**Không tăng pool để sửa lỗi TLS certificate hoặc HTTP 401**. Không tăng read timeout vô hạn để sửa connection leaks. Phân loại đúng tầng giúp tránh retry storm.

### 15.2. Pool starvation vì transaction quá dài

~~~text
HTTP thread A acquires JDBC Connection
   -> BEGIN TRANSACTION
   -> SELECT row
   -> calls slow HTTP partner for 15 seconds
   -> COMMIT + release JDBC Connection

Other requests wait on Hikari pool
   -> connectionTimeout exceeded
~~~

Giảm thời gian giữ database transaction. Nếu remote call có side effect, dùng outbox/saga hoặc flow trạng thái phù hợp. Giữ DB connection chờ HTTP thường tạo cascade failures.

### 15.3. Retry có giới hạn

Một HTTP timeout sau request ghi có thể là **outcome unknown**: remote service đã xử lý nhưng response bị mất. Khi retry, dùng cùng operationId/idempotency key nếu partner hỗ trợ; nếu không, gọi status API hoặc reconciliation.

Với message broker, broker redelivery và application retry có thể tạo duplicate. Dùng inbox/unique constraints cùng transaction side effect. Pool không chống duplicate.

### 15.4. Connection leaks

Dấu hiệu:

- Hikari active tăng và không giảm.
- HTTP leased connections cao, available thấp lâu dài.
- Rabbit channels tăng bất thường.
- Kafka producer threads và file descriptors tăng sau mỗi request.
- Redis connections vượt dự toán sau deploy.

Cần xem allocation stack/lifecycle và mã đang giữ connection/session không đóng. Tránh bật leak detection quá nhạy trên production gây noise; xem ngưỡng và chính sách runtime.

## 16. Cấu hình nhiều đích mà không trộn credential/pool

Một Order Service có thể dùng PostgreSQL cho business data, Redis cho cache, Inventory HTTP và Kafka cho events:

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

Thiết kế beans:

- Một `DataSource` theo database/trust boundary.
- Một `EntityManagerFactory`/transaction manager theo persistence unit.
- Một `RedisConnectionFactory` theo Redis endpoint/credentials.
- Một `RestClient`/HTTP transport riêng theo HTTP partner khi có auth riêng.
- Một `KafkaTemplate`/ProducerFactory theo serializer/cluster/security cần thiết.
- Một `RabbitTemplate`/AMQP ConnectionFactory theo virtual host/broker/trust boundary.

**Không dùng global HTTP Authorization header cho tất cả clients**, không forward bearer token của Inventory sang Payment và không chia sẻ JDBC Credentials cho broker. Khi certificate/client secret rotate, cần kiểm tra factory/client/pool đã nạp lại chưa và connections cũ còn sống bao lâu.

## 17. Observability: đo đúng tầng thay vì một “connection metric”

| Metric | Tầng | Ý nghĩa |
| --- | --- | --- |
| `hikaricp.connections.active` | JDBC pool | Số connections đang được sử dụng |
| `hikaricp.connections.idle` | JDBC pool | Số connections đang rảnh |
| `hikaricp.connections.pending` | JDBC pool | Số threads đợi connection |
| HTTP client pool leased/pending | HTTP transport | Saturation/reuse theo route |
| HTTP client response latency p95/p99 | HTTP operation | Remote/network time |
| Redis command latency/errors | Redis client | Command latency, timeout |
| Kafka producer request/batch/record metrics | Kafka producer | Batching, retries, broker acknowledgement |
| Kafka consumer lag/commit metrics | Kafka consumer | Tiến độ đọc và xử lý |
| Rabbit connections/channels/unacked | AMQP | Resource usage, consumer backlog |
| Business confirmation lag | Application | Từ intent đến remote confirmed |

Tên metric cụ thể thay đổi theo Micrometer/driver/Boot version và registry; ví dụ Hikari thường được Micrometer/Actuator instrument khi cấu hình phù hợp. Không mặc định có HTTP pool metrics nếu custom Apache connection manager chưa export metrics.

### 17.1. Phân biệt bốn loại latency

1. **Acquire latency:** thời gian chờ mượn connection từ pool.
2. **Connect/TLS latency:** thời gian tạo connection mới.
3. **Operation latency:** query, HTTP request/response, Redis command hoặc broker publish.
4. **Business end-to-end latency:** thời gian từ khi nhận command tới khi side effect cuối được xác nhận.

Nếu dashboard chỉ đo `repository.findById()` mà không quan sát pool pending/SQL query/lock, có thể kết luận nhầm là “repository chậm” trong khi nguyên nhân là pool exhausted.

### 17.2. Cardinality và secrets

Tags hợp lý: `component=jdbc`, `downstream=inventory`, `operation=reserve`, `outcome=timeout`. Không đặt orderId, eventId, full JDBC URL có password, token, client IP động hoặc raw SQL parameter thành metric labels.

Logs phải redact `Authorization`, database password, Redis ACL secret, Kafka SASL credentials và certificate private keys. Connection strings có thể chứa user/pass/token; không log nguyên object config.

## 18. Kiểm thử từng tầng kết nối

### 18.1. Unit test nghiệp vụ không cần live connection

Một service có thể được test với fake/mock repository/gateway:

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

Đây là **test skeleton**: `ConfirmOrderService`/`OutboxRepository` là interfaces/classes ứng dụng phải định nghĩa, không phải API có sẵn của Spring. Mock test xác minh orchestration, **không chứng minh transaction SQL hoặc broker durability**.

### 18.2. Slice/integration test JDBC và JPA

Dùng `@JdbcTest`, `@DataJpaTest` hoặc integration test với PostgreSQL Testcontainers theo nhu cầu. Kiểm tra:

- `DataSource`/Hikari wiring và SQL migrations.
- Repository query mapping, constraints và rollback.
- Transaction isolation/deadlocks, duplicate inserts.
- Timeouts và pool sizing theo load.
- Không có connection leaks khi exception.

H2 có khác biệt SQL/transaction so với PostgreSQL; khi cần kiểm tra `ON CONFLICT`, JSONB, locking hoặc `SKIP LOCKED`, dùng PostgreSQL trong test.

### 18.3. HTTP client test

`MockRestServiceServer` có thể kiểm tra URI, method, headers và body, **không tạo socket/TLS**, nên không chứng minh HTTP pool, connect/read timeout, CA trust hay mTLS.

Cần integration test với WireMock/MockWebServer/TLS-enabled test endpoint để kiểm tra:

- Pool reuse và saturation khi concurrency cao.
- Connect/read/pool acquisition timeout.
- HTTP Basic/API key/OAuth2 đúng downstream.
- TLS hostname/SAN/CA chain.
- Retry 429/503/timeout và operationId ổn định.
- Redirect không làm lộ Authorization header.

### 18.4. Redis Testcontainers

Kiểm tra `StringRedisTemplate` key/value, TTL, serializers, reconnect và optional TLS. Khi test transaction/cluster/Sentinel, môi trường test phải phản ánh topology thực, không dùng một standalone fake để kết luận Redis Cluster đúng.

### 18.5. Kafka/RabbitMQ Testcontainers

Kiểm tra:

- Producer serialization/config, confirms/acks.
- Consumer acknowledgment, retry/DLQ và idempotency.
- Broker disconnect/restart, redelivery behavior.
- Concurrency và ordering theo key/partition.
- Outbox replay không tạo business side effect trùng.

Test single-node broker không chứng minh HA durability hay quorum/ISR behavior trên cluster production.

### 18.6. Test cấu hình riêng cho từng đích

Một regression test quan trọng: xác minh Inventory client chỉ chứa Inventory credentials, Pricing client chỉ có API key riêng, database user không có quyền DDL nếu không cần và broker producer chỉ được publish tới topic được cấp phép.

**Các mocks có thể làm luồng đúng trên giấy; chỉ test với transport thật mới xác nhận kết nối, TLS, pool và protocol semantics.**

## 19. Các anti-pattern phổ biến

| Anti-pattern | Vì sao sai? | Phương án tốt hơn |
| --- | --- | --- |
| Tạo `RestClient` mới cho mỗi HTTP request | Khó kiểm soát config/resource reuse | Bean client theo partner |
| Tạo `KafkaProducer` mới cho từng event | Tăng sockets/threads, mất batching | `KafkaTemplate` + `ProducerFactory` |
| Giữ một JDBC `Connection` trong singleton | Thread safety/transaction leaks | `DataSource` + `JdbcTemplate` |
| Giữ raw `EntityManager` global | Persistence context không thread-safe | Spring JPA proxy/transaction |
| Giả định `RedisConnectionFactory` luôn có pool | Lettuce có shared native connection | Đo thực tế, chỉ bật pool nếu cần |
| Cho rằng `RabbitTemplate` = AMQP Channel | Sai resource lifecycle | Để ConnectionFactory quản lý |
| Coi Kafka producer cache là JDBC pool | Kafka client có mô hình network riêng | Cấu hình batching, buffer, producer factory |
| Tăng pool khi downstream 503 | Khuếch đại tải | Bulkhead, backoff, rate limit |
| Giữ transaction SQL trong khi gọi HTTP 15s | Chiếm JDBC Connection, dễ deadlock/cascade | Outbox/saga, giao dịch ngắn |
| Retry POST sau timeout không có idempotency | Có thể nhân đôi side effect | Stable operationId + status lookup |
| Dùng một HTTP client chứa mọi credentials | Token/key rò giữa các partners | Tách client theo trust boundary |
| Không đóng custom HttpClient/ConnectionProvider | Resource/thread/socket leak | Bean lifecycle/destroy methods |
| Dashboard chỉ nhìn pool idle | Bỏ sót pending, p99, business lag | Quan sát từng boundary |
| Coi ACK của broker là processed | Sai delivery semantics | Business completion metrics |

## 20. Câu hỏi tư duy

**Câu 1: Vì sao Repository không thay được Connection Pool?**

Repository mô tả operations dữ liệu (ví dụ `findById`), trong khi pool quản lý số connections dùng để thực thi. Một repository có thể cùng lúc phục vụ nhiều requests nhưng phải mượn JDBC Connections thông qua infrastructure. Giới hạn pool và transaction latency vẫn tồn tại dù code repository trông đơn giản.

**Câu 2: JdbcTemplate có nên được tạo trong từng service method không?**

Thông thường không. `JdbcTemplate` thread-safe khi đã cấu hình và nên inject bean dùng lại. Tạo mới có thể không tự mở connection ngay, nhưng làm phân tán cấu hình và khó kiểm thử; vấn đề chính vẫn là DataSource/pool được dùng đúng.

**Câu 3: Tôi đã có RestClient, vậy có cần pool không?**

Phụ thuộc transport và tải. RestClient là API, không nói rằng pool nào được dùng. Với lượng request cao, xem `ClientHttpRequestFactory`, underlying HTTP client, connection manager, latency và resource metrics trước khi quyết định.

**Câu 4: Vì sao không nên cho một RedisConnection vào singleton?**

Kết nối thấp cấp có thể có transaction/pipeline state hoặc ràng buộc thread-safety. `RedisTemplate` và `RedisConnectionFactory` quản lý đúng lifecycle. Nếu dùng trực tiếp, phải đọc contract driver và release resources.

**Câu 5: Tăng pool từ 20 lên 100 có giải quyết HTTP timeout?**

Chỉ nếu nguyên nhân thật sự là chờ acquire và downstream có capacity. Nếu Inventory API chậm hoặc quá tải, tăng active connections có thể khiến tình hình xấu hơn; cần metrics phân biệt pool wait với response latency.

**Câu 6: Nếu RabbitTemplate gửi thành công thì tôi có thể đánh dấu Order completed?**

Không. Gửi và publisher confirm chỉ phản ánh broker acceptance/routing policy; consumer phải xử lý business effect và báo completion theo hợp đồng. Cần outbox/inbox/idempotency.

## 21. Checklist triển khai

- [ ] Phân biệt entry API (client/template/repository), resource factory và pool.
- [ ] Không suy ra một object có pool chỉ từ tên `ConnectionFactory`.
- [ ] Spring beans của client/template/repository/factory được dùng lại với scope phù hợp.
- [ ] Không chia sẻ raw JDBC Connection, JPA EntityManager, JMS Session hoặc KafkaConsumer đa luồng.
- [ ] JDBC dùng DataSource/HikariCP và transactions ngắn.
- [ ] HTTP client được gắn đúng request factory/connector/connection manager.
- [ ] RedisConnectionFactory/Lettuce shared connection/pool được cấu hình theo workload.
- [ ] RabbitMQ channels/prefetch/concurrency được quản lý bởi ConnectionFactory/listener.
- [ ] Kafka ProducerFactory/ConsumerFactory và batching/acks được hiểu đúng, không giả định JDBC pool.
- [ ] Pool/concurrency budget tính tổng replicas và năng lực downstream.
- [ ] Timeout phân biệt pool acquisition, connect, read, deadline tổng.
- [ ] Connection lifecycle/shutdown/secret rotation có người chịu trách nhiệm.
- [ ] Credentials/TLS được tách theo trust boundary, không dùng global token/header.
- [ ] SQL transaction không bị nhầm là transaction HTTP/Redis/Kafka/Rabbit.
- [ ] Có outbox, inbox/idempotency và reconciliation cho failure windows.
- [ ] Có unit và integration tests với transport/database/broker thật khi cần.
- [ ] Metrics đo active/idle/pending, operation latency, retry, backlog và business completion.
- [ ] Không log secrets, SQL parameters nhạy cảm hoặc metric labels có cardinality cao.

**Ghi nhớ:** Client gửi giao thức; Template giảm boilerplate thao tác; Repository tổ chức truy cập dữ liệu theo domain; ConnectionFactory/DataSource cấp tài nguyên; Connection Pool quản lý số resources được dùng lại. Trong Spring Boot, **những lớp này bổ sung cho nhau** và có lifecycle, thread-safety, timeout, transaction boundary khác nhau. Thiết kế tích hợp đúng bắt đầu từ việc xác định *ai sở hữu connection*, *khi nào mượn/trả*, *ai commit business state* và *lỗi ở tầng nào*, chứ không chỉ đặt tên bean thật đẹp.

## Tài liệu tham khảo

- [Spring Boot — Working with SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html): DataSource, JDBC, JPA và connection pools.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): JdbcTemplate và connection management.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction manager, thread-bound resources.
- [Spring Data JPA — Reference](https://docs.spring.io/spring-data/jpa/reference/): repositories, EntityManager và persistence context.
- [HikariCP — Configuration](https://github.com/brettwooldridge/HikariCP): maximumPoolSize, connectionTimeout, lifetime và metrics.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, WebClient, request factories và HTTP Interfaces.
- [Reactor Netty — Connection Pool](https://projectreactor.io/docs/netty/release/reference/http-client.html#_connection_pool): ConnectionProvider và reactive HTTP resource management.
- [Spring Data Redis — Reference](https://docs.spring.io/spring-data/redis/reference/): RedisConnectionFactory, RedisTemplate, Lettuce.
- [Spring AMQP — Connections](https://docs.spring.io/spring-amqp/reference/amqp/connections.html): CachingConnectionFactory, channels và RabbitTemplate.
- [Spring for Apache Kafka — Sending Messages](https://docs.spring.io/spring-kafka/reference/kafka/sending-messages.html): KafkaTemplate và ProducerFactory.
- [Spring for Apache Kafka — Message Listener Container](https://docs.spring.io/spring-kafka/reference/kafka/receiving-messages/message-listener-container.html): ConsumerFactory, listener concurrency và acknowledgement.
- [Spring Framework — JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html): JmsTemplate, JMS connections và transactions.
- [Spring Integration — Reference](https://docs.spring.io/spring-integration/reference/): channels, endpoints và underlying adapters.
