# Metrics của connection pool, cache và cơ sở dữ liệu

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot giúp liên kết HTTP client, cơ sở dữ liệu, cache, message broker và các adapter Spring Integration thành những luồng tích hợp thực tế. Một request có thể gọi Catalog API, đọc Redis, lấy JDBC connection từ HikariCP, truy vấn PostgreSQL rồi phát outbox event sang broker.

Khi hệ thống chậm, câu hỏi “database có hoạt động không?” là chưa đủ. Cần phân biệt:

- **Pool chờ connection** vì toàn bộ connection đang bận.
- **SQL chậm** vì index thiếu, lock contention hoặc transaction kéo dài.
- **Cache miss tăng** làm số truy vấn database tăng đột biến.
- **Cache stale** trả dữ liệu cũ dù cache hit ratio cao.
- **Consumer backlog** tăng dù từng query vẫn nhanh, vì throughput nghiệp vụ không theo kịp tải.

Spring Boot Actuator kết hợp **Micrometer** để thu thập metrics ở nhiều lớp. Bài thuộc chương **Quan sát tích hợp**, tập trung vào **metrics của connection pool, cache và cơ sở dữ liệu**, cùng cách đọc các tín hiệu đó để xử lý hiệu năng và độ tin cậy.

Sau bài học, bạn có thể:

1. Thiết lập Actuator, MeterRegistry và một registry xuất metrics.
2. Phân biệt gauge, counter, timer, histogram và observation.
3. Đọc các metrics `jdbc.connections.*` và `hikaricp.*`, nhận diện pool saturation.
4. Thu cache metrics cho Caffeine/Redis, biết khi nào thống kê cache không khả dụng hoặc chưa được bật.
5. Phân biệt metrics cho JDBC pool, Spring Data repository, Hibernate và thời gian **một SQL operation**.
6. Tạo observation/metric riêng cho adapter tích hợp mà không tạo high-cardinality labels.
7. Thiết kế dashboard, cảnh báo, kiểm thử và quy trình chẩn đoán theo dữ liệu thực.

> **Phân biệt trọng tâm:** Pool metrics cho biết **tình trạng cấp phát kết nối**; repository/Hibernate metrics phản ánh một phần công việc truy cập dữ liệu; muốn biết **truy vấn nào chậm và tại sao**, có thể cần instrumentation bổ sung, SQL logs được kiểm soát, query plan, database monitoring và tracing.

## 1. Vị trí của metrics trong luồng tích hợp

Ví dụ một luồng nhận đơn hàng:

~~~mermaid
flowchart LR
    A["HTTP / broker receive"] --> B["Order service"]
    B --> C["Cache lookup"]
    C -->|"Miss"| D["JDBC / JPA"]
    D --> E["Hikari connection pool"]
    E --> F["Database"]
    B --> G["Outbox writer"]
    G --> D
    G --> H["Outbox relay → broker"]
    C -. "cache metrics" .-> I["MeterRegistry"]
    E -. "pool metrics" .-> I
    D -. "repository / operation metrics" .-> I
    H -. "business metrics" .-> I
    I --> J["Prometheus / OTLP / monitoring"]
~~~

Trong cùng một request, Hikari có thể cho thấy pool **không bị cạn**, nhưng query vẫn chậm do database đang chờ lock. Một cache hit ratio 95% có thể tốt cho đọc sản phẩm nhưng không giúp ích cho job đồng bộ nếu job luôn phải ghi database. Cần kết hợp nhiều chỉ số, không đưa ra kết luận từ một metric đơn lẻ.

Ba lớp thường cần quan sát:

| Lớp | Câu hỏi | Tín hiệu |
| --- | --- | --- |
| **Connection pool** | Có connection để xử lý hay caller phải chờ? | Active, idle, pending, max, acquire time, timeout |
| **Cache** | Cache có giảm tải, chứa dữ liệu phù hợp hay đang gây lỗi? | Hits/misses, evictions, size, load time, backend errors |
| **Database operations** | Repository/SQL/transaction chạy nhanh và thành công không? | Operation timer, repository invocations, Hibernate statistics, query/lock indicators |

Metrics tổng hợp giúp phát hiện xu hướng và cảnh báo. **Traces** giúp đi theo từng lời gọi, còn **logs/audit** giúp điều tra lỗi và business event cụ thể. Không biến metric label thành nơi lưu `orderId`, `eventId` hoặc raw SQL.

## 2. Micrometer và các loại phép đo

Micrometer là facade cho metrics, hỗ trợ các loại meter chính:

| Meter | Phù hợp để đo | Cách diễn giải |
| --- | --- | --- |
| **Gauge** | Số connection đang active, cache size, queue depth | Giá trị tại **thời điểm lấy mẫu** |
| **Counter** | Số lần timeout, cache miss, retry, duplicate | Tăng dần; dashboard dùng rate/increase |
| **Timer** | Thời gian acquire connection, query, business operation | Count, tổng thời gian, max và histogram tùy cấu hình |
| **DistributionSummary** | Kích thước batch, payload, số item một lần chạy | Distribution của giá trị, không nhất thiết là thời gian |
| **LongTaskTimer** | Số tác vụ lâu đang chạy và thời lượng hiện tại | Hữu ích với reconciliation/backfill dài |
| **Observation** | Một hoạt động có lifecycle và context | Có thể phát timer/span qua handlers tương ứng |

Hai bẫy thường gặp:

1. Gauge `active=4` không nói rằng **đã có 10.000 request chờ** trong phút trước; scrape có thể bỏ lỡ spike ngắn. Kết hợp gauge với timeout counter và acquire timer.
2. Counter tích lũy từ lúc process start không nên vẽ như “lỗi trong một phút” mà không dùng `rate(...)` hoặc `increase(...)`.

`Micrometer Observation` và `MeterRegistry` có vai trò khác nhau. Observation mô tả hoạt động start/stop/error và có thể sinh metrics khi một meter handler được cấu hình. MeterRegistry lưu/trình bày các meter, sau đó một registry/exporter chuyển dữ liệu sang Prometheus, OTLP hoặc hệ thống khác.

## 3. Thiết lập Actuator và xuất metrics

### 3.1. Dependency

Ví dụ Gradle Groovy DSL cho Spring Boot tích hợp JDBC, JPA hoặc cache:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    // Dùng khi ứng dụng cần JDBC:
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    // Chỉ cần khi chọn Caffeine cache:
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'

    // Chỉ cần khi xuất metrics sang Prometheus:
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
~~~

Nếu app dùng Spring Data JPA, starter JPA thường đã mang hạ tầng JDBC cần thiết. Với PostgreSQL/MySQL vẫn phải thêm **JDBC driver** đúng vendor ở runtime, ví dụ `org.postgresql:postgresql`. Ví dụ trên minh họa các lựa chọn, không yêu cầu một ứng dụng luôn thêm đồng thời tất cả dependency.

Spring Boot thường cung cấp `MeterRegistry` và các meter binders nếu Actuator, Micrometer và implementation tương ứng có trên classpath. **Thấy Actuator endpoint không chứng minh mọi loại metrics sẽ tồn tại**: bean/pool/cache và hỗ trợ instrumentation phải thực sự hiện diện.

### 3.2. Cấu hình cơ bản

~~~yaml
spring:
  application:
    name: order-integration
  datasource:
    url: ${DB_URL:jdbc:postgresql://localhost:5432/orders_db}
    username: ${DB_USERNAME:orders_app}
    password: ${DB_PASSWORD}
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 12
      connection-timeout: 3s

management:
  endpoints:
    web:
      exposure:
        include: health,info,metrics,prometheus
  metrics:
    tags:
      application: order-integration
~~~

Các URL và username chỉ để minh họa; không đưa secret thật vào source. `/actuator/prometheus` chỉ khả dụng khi có Prometheus registry và endpoint được expose. Tại production cần **bảo vệ các management endpoints** qua network policy, authentication/authorization, ingress hoặc management port phù hợp.

Cách kiểm tra:

~~~text
GET /actuator/metrics
GET /actuator/metrics/jdbc.connections.active
GET /actuator/metrics/hikaricp.connections.active
GET /actuator/metrics/cache.gets
GET /actuator/prometheus
~~~

Các đường dẫn `/actuator/metrics/{name}` dùng **tên meter trong Micrometer**, không phải tên sau khi backend chuẩn hóa. Ví dụ Micrometer `hikaricp.connections.active` có thể được Prometheus xuất thành `hikaricp_connections_active`.

Nếu endpoint trả 404/không có tên meter:

- Kiểm tra endpoint được expose và quyền truy cập.
- Kiểm tra dependency, bean `DataSource`/`CacheManager`/repository phù hợp.
- Kiểm tra metrics bị filter bởi `management.metrics.enable.*` hoặc registry configuration.
- Kiểm tra cache có được tạo lúc startup và thống kê provider có bật không.
- Kiểm tra có hoạt động thật để phát sinh timer/counter (một số meter chỉ xuất hiện sau lần đo đầu).

### 3.3. Micrometer naming và tags

Tên và nhãn nên ổn định theo loại hoạt động:

| Tag nên dùng | Ví dụ | Vì sao |
| --- | --- | --- |
| `application` | `order-integration` | Nhận diện service ổn định |
| `pool` | `orders-pool` | Tập pool hữu hạn |
| `cache` | `productById` | Tập cache hữu hạn |
| `cacheManager` | `cacheManager` | Phân biệt manager |
| `operation` | `outbox.fetch`, `order.save` | Phân loại công việc |
| `outcome` | `success`, `error` | So sánh tỷ lệ lỗi |
| `db.system` | `postgresql` | Nhóm database, khi instrumentation hỗ trợ |

Không đặt `customerId`, `userEmail`, `orderId`, `eventId`, full SQL có literal dữ liệu hoặc URL có query parameter vào metric tag. Một tag có hàng triệu giá trị làm số chuỗi thời gian phình ra và tạo chi phí cao.

## 4. Metrics DataSource: jdbc.connections.*

Spring Boot Actuator có thể tự instrument các bean `DataSource` có pool metadata được hỗ trợ. Các meter thường mang tiền tố `jdbc.connections` và được tag theo tên bean datasource.

| Meter thường gặp | Kiểu | Diễn giải |
| --- | --- | --- |
| `jdbc.connections.active` | Gauge | Connection đang được mượn/sử dụng |
| `jdbc.connections.idle` | Gauge | Connection nhàn rỗi trong pool |
| `jdbc.connections.max` | Gauge | Số connection tối đa của pool |
| `jdbc.connections.min` | Gauge | Giới hạn/minimum idle theo metadata pool |
| `jdbc.connections.*` khác | Tùy provider/version | Kiểm tra danh sách thực của app |

**Cần nhớ:** `active` không phải số SQL statement đang chạy. Một transaction có thể mượn connection rồi không làm SQL trong một khoảng thời gian. Và một connection có thể được dùng để thực hiện nhiều statement liên tiếp.

Các con số hữu ích:

~~~text
Pool limit: 12
Active:      11
Idle:         1
Pending:      0  (thường lấy từ Hikari-specific metrics)
~~~

Nhìn vào `active/max = 11/12` có thể nghi ngờ pool gần đầy, nhưng nếu acquire time vẫn thấp và pending bằng 0 trong traffic bình thường thì chưa chắc có sự cố. Cần nhìn xu hướng, tải và độ trễ.

### 4.1. Nhiều DataSource

Khi ứng dụng có `ordersDataSource` và `reportingDataSource`, Boot có thể bind hai nhóm metrics với tag nhận diện riêng. Đừng lấy tổng active của cả hai rồi so sánh với max của một pool.

Cần đo từng nguồn:

- `ordersDataSource`: phục vụ HTTP command, JPA transaction và outbox.
- `reportingDataSource`: phục vụ export/reporting jobs.
- `quartzDataSource` (nếu có): dành cho Quartz JDBC JobStore.

Nếu tự định nghĩa DataSource bằng implementation không được hỗ trợ metadata, một số `jdbc.connections.*` có thể vắng mặt. Có thể cần `DataSourcePoolMetadataProvider` phù hợp hoặc instrumentation riêng, không mặc định mọi `DataSource` đều đo giống Hikari.

## 5. HikariCP: hikaricp.* chi tiết hơn jdbc.connections.*

Spring Boot thường sử dụng HikariCP khi starter JDBC/JPA đưa Hikari vào classpath. Hikari cung cấp các metrics chi tiết về **acquire, connection usage, creation, timeout và pending threads**.

| Metric thường gặp | Loại | Câu hỏi vận hành |
| --- | --- | --- |
| `hikaricp.connections.active` | Gauge | Đang có bao nhiêu connection được mượn? |
| `hikaricp.connections.idle` | Gauge | Còn connection rảnh không? |
| `hikaricp.connections.pending` | Gauge | Có bao nhiêu thread đang chờ lấy connection? |
| `hikaricp.connections.max` | Gauge | Pool được phép mở tối đa bao nhiêu connection? |
| `hikaricp.connections.min` | Gauge | Minimum idle của pool là bao nhiêu? |
| `hikaricp.connections.timeout` | Counter | Có bao nhiêu lần chờ connection quá hạn? |
| `hikaricp.connections.acquire` | Timer | Mất bao lâu để lấy được connection? |
| `hikaricp.connections.usage` | Timer | Connection được mượn trong bao lâu? |
| `hikaricp.connections.creation` | Timer | Tạo connection mới mất bao lâu? |

Tên cụ thể có thể được registry chuẩn hóa khác nhau và một số meter phụ thuộc version; dùng `/actuator/metrics` để xác nhận. Hikari-specific metrics thường tag theo **tên pool**, ví dụ `orders-pool`. Có thể đặt tên ổn định bằng `spring.datasource.hikari.pool-name` thay vì để tên tự sinh thay đổi giữa deploy.

### 5.1. Đọc đúng các metric

~~~mermaid
flowchart TD
    A["Order service cần connection"] --> B{"Pool có connection rảnh?"}
    B -->|"Có"| C["Lấy connection nhanh"]
    B -->|"Không"| D["Chờ trong pending queue"]
    D --> E{"Có connection được trả trước timeout?"}
    E -->|"Có"| C
    E -->|"Không"| F["Connection acquisition timeout"]
    C --> G["SQL / transaction"]
    G --> H["Trả connection về pool"]
~~~

Ba metric thường được dùng cùng nhau:

- `pending`: **hiện tại** có ai chờ connection không?
- `acquire`: trong một khoảng thời gian, độ trễ lấy connection có tăng không?
- `timeout`: đã có lần không thể lấy connection trong thời gian cho phép chưa?

Nếu `active` gần `max` nhưng acquire time thấp, pool có thể đang vận hành bình thường ở tải cao. Nếu `pending` tăng kéo dài, acquire p95 tăng và timeout xuất hiện, đó là dấu hiệu pool saturation đáng điều tra.

### 5.2. Vì sao connection pool bị cạn?

Những nguyên nhân phổ biến:

1. SQL chậm hoặc chờ database lock làm mỗi request giữ connection lâu.
2. Transaction mở quá rộng, bao phủ cả lời gọi HTTP downstream hoặc các tác vụ không cần SQL.
3. Code JDBC thủ công không đóng connection, dẫn tới connection leak.
4. Số lượng HTTP requests/broker consumers vượt năng lực database.
5. `maximum-pool-size` quá nhỏ so với concurrency cần thiết, nhưng DB vẫn còn capacity.
6. Database/server có sự cố tạo connection, khiến pool không bổ sung được connection.
7. Nhiều replica cùng mở connection tối đa vượt giới hạn server.

**Không tăng pool ngay như phản ứng đầu tiên.** Tăng `maximum-pool-size` trên 10 replicas từ 10 lên 30 có thể làm nhu cầu kết nối tối đa từ 100 lên 300; database có thể trở nên chậm hơn do quá nhiều transaction cạnh tranh.

### 5.3. Timeout khác nhau ở các lớp

| Timeout | Đo điều gì | Không nên nhầm |
| --- | --- | --- |
| Hikari `connection-timeout` | Thời gian chờ **mượn** connection từ pool | SQL query timeout |
| JDBC driver connect/socket timeout | Thời gian kết nối/đọc phản hồi mạng | Thời gian chờ pool |
| Query timeout | Thời gian SQL statement được phép chạy | Thời gian transaction toàn bộ |
| Spring transaction timeout | Giới hạn transaction theo manager/cơ chế thực thi | Timeout của HTTP/broker ngoài DB |
| HTTP client timeout | Lời gọi Catalog/Payment bên ngoài | JDBC connection timeout |

Ví dụ cấu hình:

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-pool
      maximum-pool-size: 12
      connection-timeout: 3s
      max-lifetime: 30m
~~~

Các giá trị là minh họa. `max-lifetime` cần xét timeout của database, proxy/load balancer và khả năng tạo lại connection; không có bộ giá trị chuẩn cho mọi hệ thống.

## 6. Cache metrics: hit, miss, eviction và size

Cache thường là tầng đầu tiên được nghi ngờ khi database load thay đổi. Spring Boot Actuator có thể bind các cache được hỗ trợ (Caffeine, Redis, Hazelcast, JCache và những provider khác theo version) với các meter tên bắt đầu bằng `cache`.

Những tín hiệu hay gặp:

| Metric hoặc khái niệm | Diễn giải | Bẫy diễn giải |
| --- | --- | --- |
| `cache.gets` với result hit/miss khi hỗ trợ | Số lần lookup trúng/trượt | Cần provider bật statistics |
| `cache.puts` | Số lần ghi cache | Không bằng số business writes |
| `cache.evictions` | Số lần entry bị eviction | Eviction do size không luôn giống TTL expiration |
| `cache.size` | Số entry hiện có hoặc ước tính | Phụ thuộc provider; không phải byte size |
| Cache load duration/failures | Chi phí tải dữ liệu khi miss | Có thể không có ở mọi implementation |
| Redis roundtrip errors/latency | Sức khỏe Redis transport | Khác với hit/miss của Spring Cache |

**Không mặc định mọi loại cache đều có đầy đủ từng metric.** Boot có thể instrument `Cache` của Spring, nhưng số liệu cụ thể phụ thuộc API thống kê mà cache provider hỗ trợ và cách cache được cấu hình.

### 6.1. Bật Caffeine statistics đúng cách

Caffeine có cơ chế `recordStats`. Cấu hình cache được tạo lúc startup:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

~~~yaml
spring:
  cache:
    type: caffeine
    cache-names:
      - productById
      - integrationSettings
    caffeine:
      spec: maximumSize=10000,expireAfterWrite=10m,recordStats
~~~

Tên cache `productById` và `integrationSettings` là **tên vùng cache**, có số lượng ổn định. Không tạo một cache name riêng cho từng customer/order.

Muốn sử dụng caching với Spring Cache annotations, bật caching trong configuration:

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CacheConfiguration {
}
~~~

Một service minh họa:

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductLookupService {

    private final ProductCatalogPort catalog;

    public ProductLookupService(ProductCatalogPort catalog) {
        this.catalog = catalog;
    }

    @Cacheable(cacheNames = "productById", key = "#productId")
    public ProductDto findById(String productId) {
        return catalog.fetchFromDatabase(productId);
    }
}
~~~

`ProductCatalogPort` và `ProductDto` ở đây là các hợp đồng giả định của ứng dụng. Một call qua Spring proxy tới `findById("P-100")` có thể gây miss rồi đi DB, lần tiếp theo hit cache nếu key/TTL vẫn phù hợp.

**Quan trọng:** `@Cacheable` tự nó không bảo đảm metrics hit/miss hiện diện. Cần cache provider hỗ trợ và bật statistics, đồng thời cache được bind tới `MeterRegistry`. Với `recordStats` của Caffeine, các chỉ số này có dữ liệu để quan sát.

### 6.2. Cache được tạo sau startup

Theo tài liệu Boot, **cache có sẵn lúc startup** được bind tự động khi hỗ trợ. Một cache được tạo động bằng code sau startup có thể không tự được đăng ký metrics.

Ví dụ anti-pattern:

~~~java
// Không nên tạo tên cache theo từng request/customer:
cacheManager.getCache("customer-" + customerId);
~~~

Dù cache manager có thể trả về/khởi tạo cache động, việc này tạo số lượng cache và metric series rất lớn, đồng thời có thể không được auto-bind. Nên định nghĩa tập cache names hữu hạn, lưu customer ID dưới **cache key** thay vì **cache name**.

Nếu thật sự cần tạo cache lúc runtime, Spring Boot cung cấp `CacheMetricsRegistrar` trong các phiên bản hỗ trợ để bind tường minh; xác minh API của dòng Boot đang dùng và kiểm tra tránh bind hai lần. `CacheMetricsRegistrar` không biến một cache không hỗ trợ statistics thành cache có đầy đủ hit/miss.

### 6.3. Redis Cache khác Caffeine thế nào?

| Khía cạnh | Caffeine local cache | Redis-backed Spring Cache |
| --- | --- | --- |
| Dữ liệu | Thường trong JVM của từng instance | Trên Redis server/cluster |
| Hit/miss | Caffeine `recordStats` tại instance | `RedisCacheManager` có stats tùy cấu hình |
| Cache size | Provider có thể cung cấp số entry cục bộ | Việc đếm global keys có giới hạn/chi phí |
| Vấn đề vận hành | JVM memory/eviction, stale local state | Network RTT, timeout, Redis memory và availability |
| Scale nhiều replica | Mỗi node có cache riêng | Các node dùng chung Redis nhưng client stats có thể chỉ cục bộ |

Theo Spring Data Redis, thống kê của `RedisCache` **mặc định bị tắt**. Có thể bật khi xây dựng `RedisCacheManager` qua builder `enableStatistics()`. Thống kê `RedisCache#getStatistics()` mô tả hoạt động **cục bộ ở cache instance/client**, không đồng nghĩa toàn bộ cluster Redis có tổng hit/miss như vậy.

Ví dụ cấu hình manager thủ công chỉ để minh họa cơ chế:

~~~java
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

public RedisCacheManager buildRedisCacheManager(
        RedisConnectionFactory connectionFactory) {

    return RedisCacheManager.builder(connectionFactory)
            .enableStatistics()
            .build();
}
~~~

Đây là một phương thức factory minh họa, **không phải `@Bean` bắt buộc**. Nếu tự đăng ký bean `RedisCacheManager`, Boot auto-configuration có thể nhường chỗ; cần giữ cấu hình serialization, TTL, cache names, key prefix, null handling và transaction awareness phù hợp. Không thay manager production chỉ để bật metrics nếu builder customizer hoặc cách cấu hình ít xâm lấn hơn được phiên bản Boot của bạn hỗ trợ.

**Phân biệt các bộ số liệu:**

- Redis `INFO stats` và Redis server monitoring: số liệu cấp server.
- Spring Data RedisCache statistics: số liệu ứng dụng/cache instance khi bật.
- Micrometer Redis/client instrumentation: network command latency/pool metrics tùy driver và cấu hình.
- `cache.gets`: chỉ số cache abstraction khi provider binding hỗ trợ.

Không so sánh trực tiếp cache hit ratio của một node với Redis server keyspace hit rate của toàn cluster rồi kết luận có lỗi.

## 7. Đọc cache hit ratio đúng ngữ cảnh

Một tỷ lệ thường dùng:

~~~text
hit ratio = hits / (hits + misses)
~~~

Ví dụ một khoảng 5 phút có 9.000 hits, 1.000 misses: hit ratio = 90%. Tuy nhiên:

1. Nếu lần miss dẫn tới query rất nặng, 10% misses vẫn có thể làm database quá tải.
2. Nếu cache trả dữ liệu cũ, hit ratio cao **không chứng minh dữ liệu đúng**.
3. Cache có nhiều tenant/loại dữ liệu khác nhau thì ratio tổng có thể che một nhóm đang miss liên tục.
4. Khi service vừa restart, cache warm-up gây miss spike; so sánh theo trạng thái warm-up và baseline.
5. Nếu cache có bypass, local computation hoặc fallback, metric `cache.gets` có thể không bao phủ mọi request nghiệp vụ.

Các metric bổ sung nên có:

- Business lookup duration trong trường hợp hit/miss.
- Database query rate và response time.
- Số lần cache fallback xuống DB.
- Cache invalidation/eviction counts.
- Redis timeout và error rate.
- End-to-end latency hoặc lag của dữ liệu khi qua event-driven cache update.

Nếu dùng Redis làm cache trong luồng tích hợp, đảm bảo sự kiện update/evict không bị bỏ sót; metrics hiệu năng **không thay thế chiến lược consistency** giữa SQL và cache.

## 8. Database metrics: có nhiều cấp quan sát khác nhau

Không dùng một khái niệm chung “DB metrics” cho tất cả.

| Cấp đo | Nguồn | Có thể biết | Không thể kết luận |
| --- | --- | --- | --- |
| **DataSource/pool** | `jdbc.connections.*` / `hikaricp.*` | Connection usage, pending, acquire time | SQL statement nào chậm |
| **Spring Data repository** | `spring.data.repository.invocations` | Số lần gọi, duration, trạng thái của repository method | Thời gian một câu SQL riêng biệt trong method |
| **Hibernate ORM** | `hibernate.*` khi statistics được bật | Session/entity/query/cache statistics được hỗ trợ | Query plan và mọi wait của database |
| **Custom DB operation** | Observation/Timer quanh code | Latency một thao tác nghiệp vụ được chọn | Mọi SQL call nếu chưa instrument đầy đủ |
| **SQL/JDBC/R2DBC instrumentation** | Agent/proxy/instrumentation riêng | SQL spans và timing, nếu được cấu hình | Business commit chính xác nếu span scope ngắn |
| **Database server** | PostgreSQL/MySQL/DB-native monitoring | Slow queries, locks, CPU, I/O, connections | Ý nghĩa nghiệp vụ nếu thiếu correlation |

**Ví dụ:** `JdbcTemplate.query(...)` có thể lấy connection từ Hikari, chạy SQL và map kết quả. Một timer bao quanh lời gọi sẽ bao gồm **thời gian chờ connection + SQL execution + result mapping** (và một số overhead). Nó không cung cấp tự động breakdown giữa ba phần. Muốn tách riêng cần query tracing, pool acquire timer và server-side metrics.

### 8.1. Spring Data Repository metrics

Spring Boot có thể instrument các invocation của Spring Data `Repository` theo meter mặc định:

~~~text
spring.data.repository.invocations
~~~

Các tags phổ biến bao gồm `repository`, `method`, `state`, `exception`. Điều kiện: có Spring Data repositories, Actuator/Micrometer và instrumentation được bật theo phiên bản, cùng ít nhất một invocation.

Ví dụ:

~~~java
public interface OrderRepository
        extends org.springframework.data.jpa.repository.JpaRepository<
                OrderEntity, String> {

    java.util.List<OrderEntity> findByStatus(String status);
}
~~~

Với auto instrumentation phù hợp, invocation `findByStatus(...)` được đo ở mức repository method. Đây **không phải** timer riêng của từng SQL statement do Hibernate phát sinh. Một repository method có thể làm nhiều query, nhất là khi có lazy loading hoặc N+1.

Có thể cấu hình:

~~~yaml
management:
  metrics:
    data:
      repository:
        autotime:
          enabled: true
~~~

Khi muốn chỉ đo các method đã chọn, có thể tắt autotime và dùng `@Timed` theo hỗ trợ của phiên bản Spring Data/Boot. Tránh thay tên meter tùy tiện giữa các release, vì dashboard và cảnh báo đang dựa trên tên ổn định.

### 8.2. Hibernate metrics và generate_statistics

Với JPA/Hibernate, việc có `spring-boot-starter-data-jpa` **không có nghĩa đã bật đầy đủ Hibernate statistics**. Theo hướng dẫn Boot, cần `hibernate-micrometer` trên classpath và bật `hibernate.generate_statistics` cho các `EntityManagerFactory` liên quan.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.hibernate.orm:hibernate-micrometer'
}
~~~

~~~yaml
spring:
  jpa:
    properties:
      "[hibernate.generate_statistics]": true
~~~

Khi điều kiện phù hợp, các metrics Hibernate thường có tiền tố `hibernate` và tag theo tên `EntityManagerFactory`. Chúng có thể cho biết hoạt động entity/session, second-level cache hoặc các thống kê ORM khác tùy version.

**Chi phí:** thống kê có overhead và tăng lượng telemetry. Cần đo overhead/giá trị trên staging trước khi bật đại trà trong production. Nó không tự thay thế database monitoring, query explain plan hoặc phân tích lock.

### 8.3. Cẩn thận với N+1 query

Một repository method có latency cao có thể vì fetch 100 entities rồi truy cập lazy association, tạo 101 SQL queries. `spring.data.repository.invocations` chỉ phản ánh một lời gọi repository đã đo; nếu lazy access xảy ra **sau khi method trả về** tại tầng khác, timer repository còn có thể không đo phần SQL phát sinh muộn.

Khi nghi ngờ N+1:

- So sánh repository/business latency với số lượng statement từ Hibernate statistics/SQL tracing.
- Dùng log SQL có giới hạn ở môi trường test, không in dữ liệu nhạy cảm.
- Kiểm tra fetch joins/entity graphs/batch fetching và phân trang.
- Dùng query plan/database monitoring để xác minh nguyên nhân chậm thực.

Không tự cho rằng tăng Hikari pool size sẽ sửa N+1.

## 9. Tạo metric riêng cho một operation JDBC có ý nghĩa nghiệp vụ

Giả sử outbox relay cứ vài giây đọc batch sự kiện chưa publish. Cần đo **độ trễ của lần lấy batch**, độc lập với metrics của pool.

Đầu tiên định nghĩa DTO:

~~~java
import java.util.UUID;

public record OutboxRow(UUID id, String eventType) {
}
~~~

Một adapter Spring JDBC:

~~~java
// OutboxBatchReader.java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import java.util.List;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class OutboxBatchReader {

    private final JdbcTemplate jdbcTemplate;
    private final ObservationRegistry registry;

    public OutboxBatchReader(
            JdbcTemplate jdbcTemplate,
            ObservationRegistry registry) {
        this.jdbcTemplate = jdbcTemplate;
        this.registry = registry;
    }

    public List<OutboxRow> findPending(int limit) {
        int safeLimit = Math.max(1, Math.min(limit, 500));

        return Observation.createNotStarted(
                        "integration.outbox.load", registry)
                .lowCardinalityKeyValue(
                        "operation", "pending_batch")
                .observe(() ->
                        jdbcTemplate.query(
                                """
                                SELECT id, event_type
                                FROM outbox_events
                                WHERE published_at IS NULL
                                ORDER BY created_at, id
                                LIMIT ?
                                """,
                                (rs, rowNum) -> new OutboxRow(
                                        rs.getObject("id",
                                                java.util.UUID.class),
                                        rs.getString("event_type")),
                                safeLimit));
    }
}
~~~

Đoạn SQL này minh họa cho **PostgreSQL**. Bảng `outbox_events` và index phù hợp phải được migration tạo sẵn. Nếu hệ thống có nhiều relay workers, truy vấn đọc đơn thuần **không claim** bản ghi và có thể trả cùng record cho nhiều worker; cần thiết kế claim nguyên tử, transaction và idempotency riêng. Bài này dùng query chỉ để minh họa thời gian đo.

Khi `ObservationRegistry` có meter observation handler (như Boot Actuator cấu hình phù hợp), observation hoàn thành có thể tạo timer tên `integration.outbox.load`.

Điểm quan trọng:

- Timer đo **lời gọi đồng bộ `jdbcTemplate.query`** bao gồm lấy connection và mapping kết quả.
- Exception được ném ra ngoài `observe(...)` được ghi nhận theo lifecycle observation.
- Tag `operation=pending_batch` hữu hạn, không chứa `outboxId`.
- Nếu database transaction commit **sau khi method trả về**, timer này không đo thời gian commit; cần đặt scope ngoài ranh giới transaction nếu mục tiêu là commit latency.
- Dù Observation có thể tạo span, chưa có tracer/exporter phù hợp thì không có distributed trace.

### 9.1. Khi nào dùng Timer thủ công?

Nếu không cần trace/Observation, Micrometer `Timer` đo trực tiếp cũng phù hợp:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public void recordBatch(
        MeterRegistry registry, Runnable action) {

    Timer timer = Timer.builder("integration.batch.apply")
            .description("Thời gian áp dụng một batch")
            .tag("operation", "apply")
            .register(registry);

    timer.record(action);
}
~~~

`Runnable` chỉ bao phủ thao tác **đồng bộ**. Nếu `action` chỉ tạo `Mono` hoặc khởi tạo một asynchronous task rồi trả ngay, timer dừng trước khi I/O kết thúc. Với reactive code, đặt measurement theo subscription/terminal signal và context propagation phù hợp, hoặc tận dụng instrumentation sẵn của WebClient/R2DBC.

Tránh đo trùng cùng một operation bằng `@Observed`, manual Timer và instrumentation mặc định với các tên gần giống nhau mà không biết quan hệ giữa chúng.

## 10. Đo đúng ranh giới transaction và pipeline

Một luồng tích hợp nhận message rồi ghi SQL + outbox có nhiều ranh giới:

~~~mermaid
sequenceDiagram
    participant M as Broker Consumer
    participant S as Order Service
    participant P as Hikari Pool
    participant D as SQL Database
    participant O as Outbox Relay
    M->>S: OrderPaid event
    S->>P: Borrow connection
    P-->>S: Connection granted
    S->>D: Insert inbox + update order + outbox
    D-->>S: SQL results
    S->>D: COMMIT
    D-->>S: Commit outcome
    S-->>M: Processing success/ack
    O->>D: Fetch pending outbox
    D-->>O: Batch
~~~

Ở flow này:

- `hikaricp.connections.acquire` đo thời gian mượn connection từ pool.
- `hikaricp.connections.usage` phản ánh thời gian connection được mượn.
- `spring.data.repository.invocations` đo repository calls phù hợp.
- `integration.outbox.load` đo một query operation do ứng dụng định nghĩa.
- Một business timer riêng cần đo **từ lúc nhận event đến khi transaction commit**, nếu đó là SLA nghiệp vụ.
- Broker acknowledgment và outbox publish là ranh giới **khác**; metric DB không tự chứng minh event đã phát tới broker.

Nếu HTTP timeout sau DB commit và consumer bị redelivery, ứng dụng có thể xử lý trùng. Metrics cần phân biệt `duplicate_detected` với `business_apply_success`, không diễn giải mọi lần nhận message là một bản ghi mới.

**Quan sát không thay thế transaction:** `Observation` không cấp atomic commit cho database, Redis hay broker; nó giúp chỉ ra điểm nào chậm/lỗi để điều tra.

## 11. Tính toán SLO và nhận biết saturation

### 11.1. Những công thức hữu ích

**Pool utilization gần đúng:**

~~~text
utilization = active connections / maximum pool connections
~~~

Chỉ dùng công thức khi cả hai gauge thuộc **cùng pool**, và max khác 0. Đây là chỉ số tại một thời điểm, không phải bằng chứng pool khỏe/yếu độc lập.

**Cache hit ratio trong một khoảng thời gian:**

~~~text
hit ratio = hits_delta / (hits_delta + misses_delta)
~~~

Phải dùng số lần hit/miss **trong cùng cửa sổ thời gian**, không trộn counter tích lũy khác khoảng. Khi mẫu rất nhỏ, tỷ lệ phần trăm không ổn định.

**Connection acquisition error rate:**

~~~text
pool timeout rate = timeouts_delta / observation_window
~~~

Phải kết hợp với traffic/load: một timeout trong vài triệu request khác với 100 timeout trong một phút.

**Business-to-index lag:**

~~~text
lag = time_search_projection_visible - time_business_commit
~~~

Metric này không thể suy từ Hikari hoặc cache hit ratio. Muốn tính phải instrument và lưu timestamp/correlation metadata có kiểm soát giữa các giai đoạn.

### 11.2. Ví dụ truy vấn Prometheus

Đây là các **ví dụ** khi registry Prometheus thực sự xuất đúng tên/labels. Kiểm tra `/actuator/prometheus` trước khi sử dụng.

Pool usage:

~~~promql
hikaricp_connections_active{pool="orders-pool"}
/
clamp_min(hikaricp_connections_max{pool="orders-pool"}, 1)
~~~

Pending waiters:

~~~promql
hikaricp_connections_pending{pool="orders-pool"}
~~~

Timeout rate:

~~~promql
rate(hikaricp_connections_timeout_total{pool="orders-pool"}[5m])
~~~

Hit ratio nếu cache provider/binder phát `cache.gets` có tag `result=hit/miss`:

~~~promql
sum(rate(cache_gets_total{cache="productById",result="hit"}[5m]))
/
clamp_min(
  sum(rate(cache_gets_total{cache="productById"}[5m])),
  1
)
~~~

Phần chia cho `clamp_min(...,1)` tránh chia 0 trong khoảng rất ít request; khi không có dữ liệu thì kết quả có thể trống, **không nên tự diễn giải là 0% hit**. Cần kiểm tra cách provider phân loại result và trường hợp chỉ có một số result tags.

Timer p95 cho `integration.outbox.load` cần xuất **histogram buckets**:

~~~yaml
management:
  metrics:
    distribution:
      percentiles-histogram:
        integration.outbox.load: true
~~~

~~~promql
histogram_quantile(
  0.95,
  sum by (le) (
    rate(integration_outbox_load_seconds_bucket[5m])
  )
)
~~~

Tên Prometheus metric, hậu tố `_seconds_bucket` và sự tồn tại của histogram phụ thuộc registry/config. Không dùng histogram_quantile trên timer không bật buckets; hãy xác minh xuất dữ liệu và chi phí số buckets/tags.

## 12. Dashboard kết hợp pool, cache và database

Một dashboard dùng được trong vận hành thường cần chia thành các khu vực:

| Khu vực | Metrics nên đặt cùng nhau | Mục tiêu |
| --- | --- | --- |
| **Request/consumer load** | Throughput, error rate, p95, broker lag | Nhận diện tải đầu vào và SLO |
| **DB pool** | Active/max, idle, pending, acquire p95, timeouts | Nhận diện saturation cấp connection |
| **SQL/ORM** | Repository latency, custom DB operation p95, DB lock/slow query | Phân biệt SQL chậm và pool chờ |
| **Cache** | Hits/misses, ratio, evictions, size, Redis errors | Xác định hiệu quả và rủi ro cache |
| **Data consistency** | Cache invalidation lag, outbox oldest age, duplicate count | Xác định dữ liệu chậm/lặp |
| **Infrastructure** | DB CPU/I/O/connections, Redis memory, app JVM/GC | Kiểm tra nguyên nhân sâu |

**Khi request latency tăng**, cần nhìn xem cache miss tăng **trước** khi Hikari pending tăng hay ngược lại. Nếu theo trục thời gian có thứ tự:

~~~text
Cache miss ↑ → DB QPS ↑ → Pool active/max ↑ → Pending ↑ → API p95 ↑
~~~

thì cache effectiveness là một giả thuyết đáng kiểm tra. Nhưng tương quan thời gian chưa chứng minh nguyên nhân: có thể cùng một deployment thay đổi cả query pattern và cache key, hoặc DB vừa có lock contention.

### 12.1. Alert theo hành động, không theo số tuyệt đối tùy tiện

Ví dụ các dấu hiệu vận hành:

- `hikaricp.connections.pending` tăng kéo dài **đồng thời** acquire latency tăng.
- `hikaricp.connections.timeout` xuất hiện thường xuyên trong khi error rate ở HTTP/consumer cũng tăng.
- Cache misses tăng bất thường so với baseline, đi kèm DB QPS tăng và response latency xấu.
- Repository p95 tăng trong khi pool không bão hòa: xem query plan, lock và DB I/O.
- Hibernate second-level cache miss tăng sau deploy: kiểm tra cache invalidation và vùng cache.
- Outbox oldest age/consumer lag vi phạm SLO dù từng query nhanh: throughput xử lý chưa đủ.

Không đặt ngưỡng chung kiểu “active > 80% luôn là lỗi” cho mọi pool. Một pool có sử dụng cao nhưng acquire latency thấp và không timeout có thể đang vận hành bình thường. Ngưỡng cần lấy từ baseline, traffic pattern, số instance và error budget.

## 13. Kiểm thử metrics với Micrometer

### 13.1. Unit test một operation tự instrument

`SimpleMeterRegistry` giúp kiểm tra không cần Prometheus/collector. Ví dụ test Observation:

~~~java
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import io.micrometer.core.instrument.observation.DefaultMeterObservationHandler;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class OutboxObservationTest {

    @Test
    void recordsOneCompletedOperation() {
        var meterRegistry = new SimpleMeterRegistry();
        var observationRegistry = ObservationRegistry.create();

        observationRegistry.observationConfig()
                .observationHandler(
                        new DefaultMeterObservationHandler(meterRegistry));

        Observation.createNotStarted(
                        "integration.outbox.load",
                        observationRegistry)
                .lowCardinalityKeyValue(
                        "operation", "pending_batch")
                .observe(() -> {
                    // Một tác vụ đồng bộ mô phỏng đọc batch.
                });

        assertEquals(
                1L,
                meterRegistry.get("integration.outbox.load")
                        .tag("operation", "pending_batch")
                        .timer()
                        .count());
    }
}
~~~

Test này chứng minh **Observation + meter handler** tạo một completed timer. Nó chưa kiểm tra cấu hình Actuator thật, Hikari pool hay Prometheus export.

### 13.2. Spring Boot integration test cho pool metrics

Trong `@SpringBootTest` có Hikari DataSource thật, inject `MeterRegistry` và thực hiện query qua repository/JdbcTemplate. Sau đó kiểm tra một meter có tồn tại:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class DataSourceMetricsTest {

    @Autowired
    MeterRegistry meterRegistry;

    @Test
    void bindsDataSourcePoolMetrics() {
        assertNotNull(
                meterRegistry.find("jdbc.connections.active").gauge());
    }
}
~~~

Điều kiện test: có `DataSource` được Actuator hỗ trợ, meter binder hoạt động và pool được tạo. Nếu dùng nhiều datasource, thêm filter theo tag datasource thực tế. Nếu test dùng một `DataSource` không pooling, assertion này có thể không phù hợp; đừng đổi kiểm thử chỉ để “ép metrics tồn tại”.

### 13.3. Test cache metrics

Một integration test cache nên:

1. Bật `@EnableCaching` và provider có statistics, ví dụ Caffeine `recordStats`.
2. Tạo cache `productById` lúc startup.
3. Gọi một method qua **Spring proxy** hai lần với cùng key.
4. Xác minh business port chỉ được gọi một lần.
5. Kiểm tra cache meter đã bind và có hit/miss theo provider.
6. Đổi key hoặc evict cache, xác minh counters/size thay đổi theo kỳ vọng.

Nếu gọi nội bộ từ một method khác của cùng object (`self-invocation`), `@Cacheable` dựa trên proxy có thể không kích hoạt; test sẽ thất bại về caching dù business method vẫn trả đúng.

Với Redis, test cần kiểm tra rằng metrics thu từ local `RedisCache` statistics nếu bật, **không** suy ra số liệu toàn cluster khi chạy nhiều replica.

### 13.4. Test tải và failure modes

Unit test không tái hiện pool saturation. Cần thử trong môi trường cô lập:

- Tạo nhiều request đồng thời vượt pool max, đo pending/acquire/timeout.
- Inject SQL query chậm hoặc lock contention, theo dõi pool usage.
- Tắt cache tạm thời, quan sát tải DB và fallback.
- Restart service, ghi nhận warm-up miss spike.
- Giả lập Redis timeout, xác minh policy fallback không gây overload database.
- Dừng database/network, đo timeout, error rate và recovery.
- Khi job bị retry hoặc broker redelivery, kiểm tra business idempotency và metric duplicate count.

Không dùng database production cho stress tests hoặc cố tình giữ connection làm cạn pool nếu chưa có quyền và kế hoạch bảo vệ.

## 14. Chẩn đoán lỗi theo số liệu

| Hiện tượng | Các tín hiệu đi kèm | Hướng điều tra |
| --- | --- | --- |
| Pool active gần max, pending tăng | Acquire p95/timeout tăng | Long transaction, leak, DB lock, concurrency |
| Pool active thấp nhưng API chậm | HTTP client p95 hoặc cache/backend latency tăng | Downstream khác DB |
| Repository latency cao, pool acquisition thấp | DB CPU/I/O, slow query, lock wait tăng | Query plan/index/N+1 |
| Cache hit ratio giảm sau deploy | Cache name/key/TTL thay đổi, DB QPS tăng | Key generation, invalidation, warm-up |
| Cache hit ratio cao nhưng dữ liệu cũ | Business version/invalidations lag | Consistency, outbox replay, TTL |
| Caffeine eviction cao | Cache size gần max, churn | Keyspace/TTL/max size, memory pressure |
| Redis cache metric thiếu | Stats tắt hoặc cache không bind lúc startup | RedisCacheManager settings/registrar |
| Hibernate metrics thiếu | Thiếu hibernate-micrometer hoặc statistics chưa bật | Dependency + generate_statistics |
| Repository metrics thiếu | Chưa có repository invocation/auto instrumentation bị tắt | Actuator, Spring Data, autotime |
| jdbc.connections.* có nhưng SQL timer thiếu | Pool được bind, query instrumentation chưa có | Thêm operation timing/SQL instrumentation |
| Prometheus không hiển thị meter | Chưa có Prometheus registry/exposure/scrape, name đổi | Kiểm tra /actuator/metrics và /actuator/prometheus |
| Metric series tăng đột ngột | Tags chứa ID/user/dynamic cache name | Chặn high-cardinality source |

### 14.1. Một quy trình điều tra thực tế

Giả sử consumer xử lý outbox chậm:

1. Xem **broker lag** và `outbox oldest age`: có đúng là pipeline chậm không?
2. Xem `hikaricp.connections.pending` và acquire timer: chậm vì chờ pool?
3. Xem repository/custom DB operation timer: thời gian query có tăng?
4. Xem database locks/slow query plan: lỗi ở SQL hay transaction?
5. Xem cache misses/Redis latency: thêm tải DB vì cache mất hiệu lực?
6. Xem active jobs/concurrency: Quartz hoặc Spring Integration pollers có chạy dồn?
7. Xem release timeline: có migration, index mới, cấu hình cache hoặc pool thay đổi?
8. Chọn biện pháp sửa dựa trên điểm nghẽn thực, sau đó theo dõi metrics xác nhận cải thiện.

Tránh phản ứng “tăng pool”, “bật cache TTL dài hơn” hoặc “retry thêm” trước khi hiểu bottleneck: những biện pháp này có thể làm tăng lock contention, stale data hoặc duplicate side effects.

## 15. Kiến trúc vận hành và bảo mật telemetry

Metrics cũng là một phần hệ thống sản xuất:

- **Collector/scraping:** Prometheus pull endpoint hoặc OTLP push phải có network route, retry/buffering và quyền truy cập phù hợp.
- **Retention:** lưu raw/high-resolution metrics theo ngân sách; tổng hợp/downsample khi cần.
- **High cardinality:** đặt allowlist tags hữu hạn, tránh tên cache/pool theo customer, event ID hoặc SQL động.
- **Secrets và PII:** không ghi JDBC URL chứa password, cache key nhạy cảm, payload hay SQL literal vào labels/logs.
- **Multi-instance:** dashboard cần filter theo instance và aggregation đúng, không lấy một instance làm đại diện cho toàn cluster.
- **Multiple pools:** cộng active/max theo các pool chỉ khi chúng phục vụ cùng một mục tiêu capacity; không gộp production và staging.
- **Sampling:** trace sampling khác metric aggregation; sample ít traces không có nghĩa các gauge/counters bị sample tương tự.
- **Overhead:** Hibernate statistics, SQL instrumentation chi tiết và histograms tạo chi phí; bật có chọn lọc, đo trên staging.
- **Health vs performance:** health `UP` không chứng minh DB query nhanh hoặc cache projection chính xác.
- **Incident review:** lưu dashboard, SLO và một tập query/trace/log đủ liên kết để phân tích nguyên nhân.

### 15.1. Cảnh báo liên quan tính nhất quán

Cache metrics và pool metrics **không đo correctness**. Với một luồng cập nhật Order rồi evict Redis cache:

~~~text
SQL COMMIT thành công
    |
    +-- Evict Redis thất bại
           |
           +-- Cache tiếp tục trả trạng thái cũ
~~~

Hikari và JDBC có thể đều “xanh”, cache hit ratio vẫn cao. Muốn phát hiện sai lệch cần thêm tín hiệu **cache invalidation failures**, **projection lag**, **reconciliation mismatches** và ranh giới commit của nghiệp vụ. Với cập nhật DB→broker, transactional outbox giúp giữ ý định phát sự kiện; consumer vẫn phải idempotent khi replay.

## 16. Checklist triển khai metrics

- [ ] Đã thêm Actuator, registry/exporter phù hợp và kiểm tra endpoint metrics được bảo vệ.
- [ ] Phân biệt gauge/counter/timer/Observation; không vẽ counter tích lũy như tốc độ tức thời.
- [ ] Kiểm tra `jdbc.connections.*` và `hikaricp.*` đúng datasource/pool.
- [ ] Có dashboard active/max, pending, acquire p95, timeouts và số replica.
- [ ] Đã bật statistics cho cache provider khi cần; Caffeine có `recordStats`.
- [ ] Cache names được khai báo/bind lúc startup; cache động có chính sách đăng ký riêng.
- [ ] Hiểu RedisCache statistics là local và có thể bị tắt mặc định.
- [ ] Phân biệt pool metrics với repository, Hibernate và SQL operation metrics.
- [ ] Nếu dùng Hibernate metrics, kiểm tra dependency `hibernate-micrometer` và `hibernate.generate_statistics`.
- [ ] Có operation timer/observation riêng cho các bước nghiệp vụ quan trọng (outbox, inbox, cache invalidation).
- [ ] Nhãn metrics có cardinality thấp, không chứa secret/PII/ID.
- [ ] Có cảnh báo theo baseline/SLO, kết hợp tải vào, latency, lỗi và backlog.
- [ ] Có unit/integration/load tests chứng minh instrumentation và behavior khi quá tải.
- [ ] Có dữ liệu observability cho retry, duplicate, transaction commit và projection lag — không chỉ pool/cache hit ratio.

**Ghi nhớ:** Spring Boot Actuator và Micrometer cung cấp metrics tự động cho nhiều pool, cache và Spring Data components. Nhưng **metrics đo một lớp không thay thế đo lớp khác**. Hikari cho biết kết nối được cấp phát thế nào; cache statistics cho biết hiệu quả lookup; repository/Hibernate/SQL instrumentation cho biết thời gian và hành vi truy cập dữ liệu ở mức khác nhau. Muốn vận hành luồng tích hợp đáng tin cậy, cần kết hợp chúng với **business outcome, transaction, retry, idempotency, kiểm thử và observability**.

## Tài liệu tham khảo

- [Spring Boot — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): DataSource, HikariCP, Cache, Hibernate, Spring Data repository và Micrometer.
- [Spring Boot 3.5 — Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): đối chiếu với hệ Boot 3.x.
- [Spring Boot — Observability](https://docs.spring.io/spring-boot/reference/actuator/observability.html): ObservationRegistry, handlers và context propagation.
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html): auto-configuration, cache providers và Caffeine.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): RedisCacheManager, statistics và các giới hạn.
- [Caffeine — Statistics](https://github.com/ben-manes/caffeine/wiki/Statistics): recordStats, hit rate, eviction và load penalties.
- [Micrometer — Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): meters, tags và registry.
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): timer buckets, percentiles và SLO.
- [Prometheus — Query Functions](https://prometheus.io/docs/prometheus/latest/querying/functions/): rate, increase, histogram_quantile.
