# Connection pooling và tái sử dụng kết nối tới hệ thống đích

## 1. Bài toán: REST API chậm vì thiết lập kết nối, không chỉ vì xử lý nghiệp vụ

Một endpoint `GET /api/orders/{id}` của Shop API đọc PostgreSQL, gọi Inventory API để tra tồn kho và gọi Pricing API để tra giá. Nếu mỗi request đều tạo HTTP client mới, mở TCP connection mới và bắt tay TLS rồi đóng sau khi lấy JSON, độ trễ tăng ngay cả khi xử lý phía Inventory rất nhanh. Tải tăng sẽ kéo theo thêm socket, file descriptor, CPU cho TLS và nhiều kết nối phía target.

Ở database, nếu code mở JDBC connection mới mỗi request thay vì mượn từ HikariCP, quá trình kết nối/xác thực DB trở thành chi phí lặp lại. Nhưng **pool quá lớn cũng nguy hiểm**: 20 pod có tối đa 40 connection/pod sẽ mở tới 800 connection đồng thời, có thể vượt ngân sách PostgreSQL.

**Connection pooling** quản lý một tập kết nối có thể tái sử dụng, đồng thời kiểm soát **giới hạn tài nguyên, hàng đợi và thời gian chờ**. Pool không phải một nút “bật để mọi request nhanh hơn”: nó cần khớp với protocol, tải thực, khả năng của hệ thống đích, timeout, cấu hình mạng và số instance.

Đây là bài trong chương **Hiệu năng** thuộc module **INTEGRATION_API_REST**. Kiến thức áp dụng khi thiết kế REST resource/URI, gọi downstream, phân trang, cache, idempotency, authentication/authorization, HTTP status, Java/Spring và kiểm thử hiệu năng.

### Mục tiêu

1. Giải thích HTTP/1.1 persistent connection, HTTP/2 multiplexing và JDBC pool khác nhau ra sao.
2. Sử dụng HTTP client sống theo vòng đời ứng dụng; quản lý max total/per-route, pending/acquire timeout và response body.
3. Cấu hình HikariCP, ước lượng tổng kết nối qua nhiều pod và tránh giữ connection DB khi đang chờ HTTP.
4. Nhận diện stale connection, connection leak, DNS/TLS rotation, retry storm và pool starvation.
5. Phân biệt lỗi pool exhaustion, timeout, quota với HTTP 429/503/504; xử lý retry/idempotency an toàn.
6. Đo hiệu quả bằng metric/trace/load test và xây kiểm thử Java/Spring.

## 2. Các thành phần của một lời gọi HTTP ra ngoài

~~~text
Controller -> Business service -> HTTP client/connection manager
                                      |
                         acquire slot/connection
                                      |
                          reuse sẵn có? ----- Không
                              |                  |
                             Có            DNS + TCP + TLS
                              |                  |
                              +--------+---------+
                                       |
                              gửi HTTP request
                                       |
                              nhận và đọc response
                                       |
                             release/close resource
~~~

Chi phí tạo connection mới có thể gồm DNS resolution, TCP handshake, TLS handshake và thiết lập protocol. Connection đã mở có thể được dùng lại để giảm những chi phí đó; nhưng chính socket đang idle vẫn chiếm tài nguyên. Một connection manager thường theo dõi:

| Khái niệm | Ý nghĩa |
|---|---|
| HTTP client | Đối tượng Java giữ configuration, executor, connection manager, TLS settings |
| Connection | Kênh transport TCP/TLS tới route/origin; không đồng nghĩa một HTTP request |
| Leased/active | Connection hoặc slot đang được sử dụng |
| Idle/available | Connection còn mở và có thể dùng lại |
| Pending/waiting | Request chờ connection/slot vì pool đã đạt giới hạn |
| Eviction/expiry | Thu hồi connection quá idle, hết lifetime hoặc không còn hợp lệ |
| Request/stream | Một request HTTP; nhiều stream HTTP/2 có thể cùng một connection |

**Quy tắc quan trọng:** Phải **đọc đủ hoặc đóng response body** đúng cách để thư viện giải phóng tài nguyên. Một `InputStream` bị bỏ quên có thể giữ connection leased, khiến pool cạn mà không cần tăng request rate.

### 2.1. Một connection không đồng nghĩa một danh tính

Pool tái sử dụng **kết nối mạng**, không tự phân quyền user/tenant. Nếu shared client giữ mặc định header `Authorization` của User A rồi được dùng để gọi thay User B, đó là lỗi bảo mật. Credentials và tenant context phải đến từ request đã xác minh và được áp dụng theo chính sách của từng lời gọi. Với mTLS, một client/pool có identity khác nhau có thể cần được tách theo chứng chỉ.

## 3. HTTP/1.1 keep-alive và HTTP/2 multiplexing

### 3.1. HTTP/1.1 persistent connections

HTTP/1.1 cho phép giữ TCP connection sau khi trả response. Trong một mô hình thường gặp, một connection dùng cho các request **tuần tự**, còn nhiều request đồng thời tới một origin có thể cần nhiều connection:

~~~text
Inventory route, HTTP/1.1:
  socket 1: GET /stock/A -> response -> GET /stock/D
  socket 2: GET /stock/B -> response -> GET /stock/E
  socket 3: GET /stock/C -> response -> idle
~~~

Nếu pool giới hạn 3 connections mà cùng lúc có 20 lời gọi, số còn lại phải đợi hoặc bị từ chối theo giới hạn pending/acquisition timeout. HTTP/1.1 pipelining tồn tại về mặt giao thức nhưng không nên giả định được client/proxy thực tế sử dụng.

Thông thường **không cần tự đặt `Connection: keep-alive`** trong mỗi request: HTTP/1.1 đã có semantics persistence và client quản lý. Server/load balancer vẫn có quyền đóng connection; phía client phải xử lý lỗi reuse socket đã cũ.

### 3.2. HTTP/2 stream multiplexing

HTTP/2 cho phép nhiều request/response **stream** chạy trên cùng một connection. Vì vậy:

- 1 TCP/TLS connection không nhất thiết chỉ phục vụ 1 request đang chạy.
- Max concurrent streams, flow control và khả năng xử lý của server vẫn giới hạn tải.
- Một HTTP/2 connection không tự biến downstream thành dịch vụ có concurrency vô hạn.
- HTTP/2 qua TLS thường được thương lượng với ALPN; cấu hình client “prefer HTTP/2” có thể fallback HTTP/1.1.
- Header connection-specific như `Connection: keep-alive` không dùng trong HTTP/2.

HTTP/3 dùng QUIC thay TCP; không suy trực tiếp số socket TCP hoặc quy tắc HTTP/1.1 sang HTTP/3. Trong phần tính tải, với HTTP/2 nên theo dõi **số stream/request in-flight** bên cạnh physical connection count.

### 3.3. So sánh

| Đặc điểm | HTTP/1.1 thường gặp | HTTP/2 |
|---|---|---|
| Request đồng thời trên một connection | Thực tế thường một request tại một thời điểm | Nhiều stream multiplexed |
| Vấn đề pool chủ yếu | Số connection, queue acquire, idle close | Connection lifetime **và** giới hạn stream/concurrency |
| TLS handshake | Tránh lặp bằng reuse | Tránh lặp bằng reuse, đồng thời ghép kênh |
| Nút thắt còn lại | Socket count, upstream concurrency | Max streams, bandwidth, flow control, upstream concurrency |
| Điều cần kiểm | Leased/idle/pending/timeout | Physical connections, streams, pending/timeout |

## 4. Thiết kế pool: giới hạn, timeout, vòng đời

| Cấu hình | Quy tắc | Rủi ro nếu bỏ qua |
|---|---|---|
| Max total connections | Giới hạn tài nguyên toàn client | File descriptor và memory tăng |
| Max per-route | Một host/route không chiếm toàn bộ pool | Noisy neighbor giữa các target |
| Pending acquisition limit | Giới hạn số request chờ slot | Hàng đợi không giới hạn, OOM, latency cao |
| Acquisition timeout | Thời gian tối đa đợi pool | Request chờ lâu dù deadline đã hết |
| Connect timeout | Giới hạn mở connection mới | Không bảo vệ chờ body trên connection đã mở |
| Response/read timeout | Giới hạn chờ dữ liệu target, tùy thư viện | Không đồng nghĩa deadline toàn workflow |
| End-to-end deadline | Ngân sách tổng cho nghiệp vụ | Nhiều lượt retry làm request vượt SLO |
| Max idle time | Thu hồi connection idle quá lâu | LB/NAT/firewall đã đóng kết nối |
| Max connection lifetime | Chủ động thay kết nối cũ | Giữ IP/cert cũ, reset khi server drain |
| Eviction/validation | Phát hiện/thu hồi connection không còn tốt | Kết nối hỏng được tái dùng |
| Connection release | Đọc/đóng body, hoàn trả lease | Pool leak hoặc starvation |

Một pool **đầy** không tự động là sự cố nếu throughput tốt và không có pending. Tuy nhiên, `leased == max`, pending tăng liên tục, acquisition timeout và p99 latency tăng là tín hiệu cần điều tra. Đừng lập tức nâng max: có thể là leak, downstream chậm, transaction dài hoặc service đang vượt khả năng xử lý.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant O as Orders API
    participant P as HTTP Pool
    participant I as Inventory API
    C->>O: GET /orders/101
    O->>P: Acquire slot/connection
    alt Có connection/stream
        P-->>O: Lease
        O->>I: GET /stocks/101
        I-->>O: 200 JSON
        O->>P: Consume body + release
        O-->>C: 200
    else Hết capacity
        P-->>O: Wait in bounded queue
        alt Hết acquisition timeout
            O-->>C: Controlled error/degrade
        else Có slot trước deadline
            P-->>O: Lease
        end
    end
~~~

## 5. Java 17+ `java.net.http.HttpClient`: dùng chung instance

JDK `HttpClient` tự quản lý connection resources trong instance. Không gọi `HttpClient.newHttpClient()` trong mỗi controller request. Tạo `@Bean` dùng chung:

~~~java
import java.net.http.HttpClient;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class HttpClientConfig {
    @Bean
    HttpClient inventoryHttpClient() {
        return HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_2) // Prefer, có thể fallback.
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();
    }
}
~~~

`connectTimeout` dành cho việc mở connection mới. `HttpRequest.timeout` bên dưới là timeout của request; business service vẫn phải có deadline xuyên suốt nếu request còn gọi nhiều hop/retry.

~~~java
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import org.springframework.stereotype.Service;

@Service
class InventoryAdapter {
    private final HttpClient client;

    InventoryAdapter(HttpClient inventoryHttpClient) {
        this.client = inventoryHttpClient;
    }

    HttpResponse<String> stock(String sku)
            throws IOException, InterruptedException {
        String encoded = URLEncoder.encode(
            sku, StandardCharsets.UTF_8);
        // Host cố định, không lấy URL tùy ý từ người gọi.
        URI uri = URI.create(
            "https://inventory.example.test/api/stocks?sku=" + encoded);

        HttpRequest request = HttpRequest.newBuilder(uri)
            .header("Accept", "application/json")
            .timeout(Duration.ofSeconds(4))
            .GET()
            .build();

        return client.send(request,
            HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
    }
}
~~~

Với `BodyHandlers.ofString`, client đã đọc body trước khi trả về. Service gọi adapter cần map HTTP status theo hợp đồng của Inventory, không coi mọi response 200/404/429/503 là thành công. Nếu bắt `InterruptedException`, phục hồi cờ ngắt bằng `Thread.currentThread().interrupt()`. `URLEncoder` ở ví dụ dùng **cho query parameter**, không dùng thẳng cho path segment.

**Nếu dùng streaming body, bắt buộc đóng stream:**

~~~java
HttpResponse<java.io.InputStream> response =
    client.send(request, HttpResponse.BodyHandlers.ofInputStream());

try (java.io.InputStream stream = response.body()) {
    // Stream dữ liệu theo buffer, kiểm size limit trước khi parse.
    // Không bỏ stream mở trong scope dài hoặc quên close().
}
~~~

Đóng stream khi chưa đọc đủ có thể khiến connection không còn tái sử dụng được, nhưng vẫn cần giải phóng tài nguyên đúng cách. Với response rất lớn, không dùng `readAllBytes()` thiếu giới hạn. Đừng lưu Authorization header mặc định cho mọi tenant trên một client dùng chung.

JDK HttpClient có connection management nội bộ nhưng không cung cấp public API cấu hình `maxPerRoute` và pending queue rõ như Apache HttpClient 5. Khi cần kiểm capacity theo target, dùng một connection manager có tính năng đó hoặc thêm bulkhead/concurrency limiter.

## 6. Spring `RestClient` + Apache HttpClient 5: pool có giới hạn rõ ràng

Trong Spring Framework 6.1+ (thường đi với Spring Boot 3.2+), `RestClient` là API đồng bộ gọi HTTP. Nếu dùng Apache HttpClient 5 qua `HttpComponentsClientHttpRequestFactory`, có thể cấu hình max total/per route và acquisition timeout.

Dependency theo version/BOM tương thích của dự án:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.apache.httpcomponents.client5:httpclient5'
}
~~~

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration
class DownstreamClientConfig {
    @Bean(destroyMethod = "close")
    CloseableHttpClient inventoryApacheClient() {
        var manager = new PoolingHttpClientConnectionManager();
        manager.setMaxTotal(80);
        manager.setDefaultMaxPerRoute(30);

        manager.setDefaultConnectionConfig(ConnectionConfig.custom()
            .setConnectTimeout(Timeout.ofSeconds(2))
            .setTimeToLive(TimeValue.ofMinutes(5))
            .build());

        var requestConfig = RequestConfig.custom()
            .setConnectionRequestTimeout(Timeout.ofMilliseconds(700))
            .setResponseTimeout(Timeout.ofSeconds(3))
            .build();

        return HttpClients.custom()
            .setConnectionManager(manager)
            .setDefaultRequestConfig(requestConfig)
            .evictExpiredConnections()
            .evictIdleConnections(TimeValue.ofSeconds(30))
            .build();
    }

    @Bean
    RestClient inventoryRestClient(
            CloseableHttpClient inventoryApacheClient) {
        return RestClient.builder()
            .baseUrl("https://inventory.example.test")
            .requestFactory(new HttpComponentsClientHttpRequestFactory(
                inventoryApacheClient))
            .build();
    }
}
~~~

Ý nghĩa: tối đa 80 connections do manager quản lý; 30 cho mỗi route theo mặc định; chờ acquire tối đa khoảng 700 ms, connect mới tối đa 2 s, response timeout 3 s theo semantics Apache; connection TTL 5 phút, idle eviction sau 30 s. **Các số chỉ là minh họa**, phải đo để đặt đúng. Response timeout của Apache không thay thế deadline bao gồm acquisition + nhiều retries + parse + nghiệp vụ. API và tên cấu hình chi tiết có thể khác giữa minor version; kiểm version trong build trước khi sao chép.

Dùng bean:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

record StockView(String sku, long available) {}

@Service
class StockService {
    private final RestClient inventoryRestClient;

    StockService(RestClient inventoryRestClient) {
        this.inventoryRestClient = inventoryRestClient;
    }

    StockView getStock(String sku) {
        return inventoryRestClient.get()
            .uri(b -> b.path("/api/stocks")
                .queryParam("sku", sku)
                .build())
            .retrieve()
            .body(StockView.class);
    }
}
~~~

Với `retrieve().body(StockView.class)`, framework đọc và đóng response theo contract của client. Streaming/download qua API thấp hơn cần quản lý response body rõ ràng. `@Bean(destroyMethod="close")` đảm bảo đóng HTTP client/eviction resources khi Spring context shutdown. Không tạo `RestClient`/connection manager mới cho mỗi request.

**Vì sao acquisition timeout quan trọng?** Khi per-route chỉ có 30 connections và hàng trăm request đến, pending không được chờ vượt deadline của REST caller. Một request timeout ở **bước acquire** có thể chưa từng chạm downstream; response timeout sau khi đã gửi thì side effect có thể đã xảy ra. Hai trường hợp cần logging và retry policy khác nhau.


## 7. `WebClient` / Reactor Netty cho các lời gọi bất đồng bộ

Ứng dụng Spring WebFlux thường dùng `WebClient` với Reactor Netty. `ConnectionProvider` cho phép cấu hình số connection, pending acquisition, idle time và lifetime. Không được nhầm **nonblocking** với **không cần giới hạn concurrency**.

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
~~~

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration
class ReactiveDownstreamConfig {
    @Bean(destroyMethod = "dispose")
    ConnectionProvider inventoryConnectionProvider() {
        return ConnectionProvider.builder("inventory-http")
            .maxConnections(40)
            .pendingAcquireMaxCount(80)
            .pendingAcquireTimeout(Duration.ofMillis(500))
            .maxIdleTime(Duration.ofSeconds(30))
            .maxLifeTime(Duration.ofMinutes(5))
            .build();
    }

    @Bean
    WebClient inventoryWebClient(
            ConnectionProvider inventoryConnectionProvider) {
        HttpClient http = HttpClient.create(inventoryConnectionProvider)
            .responseTimeout(Duration.ofSeconds(3));
        return WebClient.builder()
            .baseUrl("https://inventory.example.test")
            .clientConnector(new ReactorClientHttpConnector(http))
            .build();
    }
}
~~~

Đây là cấu hình mẫu; API chi tiết/metric của Reactor Netty phụ thuộc version. Spring Boot còn có cơ chế quản lý Reactor Netty resources toàn cục, cần tránh tạo nhiều provider/event loop không chủ đích. Provider được dọn khi context đóng.

`maxConnections=40` **không tự đảm bảo** tối đa chỉ 40 request đồng thời trong mọi protocol, nhất là HTTP/2 streams. Khi downstream chỉ chịu được 20 công việc nặng đồng thời, thêm bulkhead giới hạn cả request concurrency. Không gọi `.block()` trên event-loop WebFlux: blocking có thể khiến response đến chậm dù pool socket chưa đầy. `timeout`, cancellation và backpressure cũng cần xử lý ở reactive chain, không đợi hàng đợi phát triển vô hạn.

## 8. JDBC connection pooling với HikariCP

Spring Boot thường dùng HikariCP cho `DataSource` khi có JDBC/JPA starter. Hikari quản lý một tập **JDBC connection vật lý tới DB**, không phải socket HTTP. Các connection được mượn khi cần SQL, dùng trong transaction và **trả về pool** khi kết thúc.

Ví dụ cấu hình `application.yml` (URL, user, password được cấp từ cấu hình bảo mật của môi trường, không hardcode secret):

~~~yaml
spring:
  datasource:
    hikari:
      pool-name: orders-db
      maximum-pool-size: 12
      minimum-idle: 4
      connection-timeout: 1000
      validation-timeout: 500
      idle-timeout: 600000
      max-lifetime: 1500000
      keepalive-time: 300000
~~~

Giá trị thời gian Hikari trong cấu hình này dùng **mili giây**:

| Thuộc tính | Ví dụ | Công dụng |
|---|---:|---|
| `maximum-pool-size` | 12 | Giới hạn kết nối đang tồn tại/được dùng của pool |
| `minimum-idle` | 4 | Mức idle connection pool cố duy trì |
| `connection-timeout` | 1000 ms | Thời gian chờ mượn connection trước khi timeout |
| `validation-timeout` | 500 ms | Timeout kiểm connection hợp lệ |
| `idle-timeout` | 600000 ms | Thu hồi idle connection khi phù hợp và vượt minimum idle |
| `max-lifetime` | 1500000 ms | Chủ động thay connection khi đạt lifetime tối đa; không giết connection đang dùng |
| `keepalive-time` | 300000 ms | Kiểm idle connection định kỳ để giảm khả năng bị hạ tầng đóng |

Những con số trên không phải cấu hình tối ưu chung. Nên đặt `max-lifetime` ngắn hơn giới hạn lifetime connection của database/proxy/HA infrastructure. `keepalive-time` không được quá sát đến mức tạo lượng query vô ích. Khi `minimumIdle` bằng `maximumPoolSize`, pool mang tính fixed size và ý nghĩa của `idleTimeout` bị hạn chế.

### 8.1. `close()` trên pooled JDBC Connection nghĩa là trả về pool

~~~java
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.UUID;
import javax.sql.DataSource;

class OrderJdbcReader {
    private final DataSource dataSource;

    OrderJdbcReader(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    long countOrders(UUID tenantId) throws SQLException {
        String sql = "SELECT count(*) FROM orders WHERE tenant_id = ?";
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setObject(1, tenantId);
            try (ResultSet rs = ps.executeQuery()) {
                rs.next();
                return rs.getLong(1);
            }
        }
    }
}
~~~

Trong pooled DataSource, `conn.close()` thường trả **logical connection** về Hikari, không phá connection vật lý ngay. Dùng `try-with-resources` cho Connection/Statement/ResultSet, và tham số hóa SQL để tránh injection. Kiểm `tenantId` phải xuất phát từ principal/membership đã xác minh; pooling không giải quyết BOLA.

### 8.2. Tránh giữ DB connection khi chờ HTTP downstream

Mẫu dễ gây starvation:

~~~java
@Transactional
public OrderView updateThenAskInventory(...) {
    Order order = repository.findById(...).orElseThrow();
    order.setStatus("PROCESSING");

    // HTTP mất 3 giây: DB connection/locks có thể bị giữ.
    StockView stock = inventoryClient.getStock(...);
    return mapper.toView(order, stock);
}
~~~

Sau khi query DB trong transaction, ORM/driver có thể giữ JDBC connection tới khi transaction kết thúc. Nếu Inventory chậm, request **giữ DB connection trong lúc không chạy SQL**. 12 concurrent requests kiểu đó có thể giữ cả 12 Hikari connections, khiến một endpoint chỉ đọc DB cũng timeout acquire.

Phương án thường hợp lý hơn:

~~~text
1. Transaction ngắn: kiểm quyền và ghi order/intent/outbox.
2. Commit, giải phóng DB connection.
3. Gọi HTTP downstream với timeout/concurrency budget riêng.
4. Transaction ngắn khác: kiểm version/state rồi ghi kết quả.
~~~

Chia transaction yêu cầu **optimistic locking, state machine, outbox/idempotency hoặc compensation** để giữ bất biến nghiệp vụ. Không đơn giản tách `@Transactional` rồi bỏ qua race. Với Payment POST, nếu response mất, trạng thái có thể UNKNOWN: phải đối soát và retry bằng same-key theo contract, không gửi giao dịch mới.

## 9. Ước lượng pool size và tổng ngân sách kết nối

### 9.1. Bắt đầu từ Little's Law

Ở trạng thái tương đối ổn định:

\[
L \approx \lambda W
\]

- \(\lambda\): throughput trung bình (request/giây).
- \(W\): **thời gian trung bình** một request giữ tài nguyên/giai đoạn đang xét (giây).
- \(L\): số request đang xử lý đồng thời trung bình.

Nếu một hệ thống gọi Inventory **240 lần/giây** và giữ một HTTP/1.1 connection trung bình **125 ms**, thì:

\[
L \approx 240 \times 0.125 = 30
\]

Khoảng 30 calls in-flight trung bình ở giai đoạn đó; **không** có nghĩa một pool 30 luôn đủ cho burst. Khi peak tăng gấp đôi hoặc latency tăng do downstream nghẽn, concurrency cần thiết cũng tăng. Phải đo burst, queueing, p95/p99, tỷ lệ lỗi và năng lực Inventory; không thay thời gian trung bình trong công thức bằng p95 rồi vẫn gọi đó là Little's Law.

Với **HTTP/2**, \(L\) là concurrency request/stream, không nhất thiết bằng physical connection count. Với **JDBC**, \(W\) là thời gian thật sự giữ DB connection, không phải toàn bộ HTTP latency nếu connection được lấy muộn/trả sớm.

### 9.2. Nhân theo instance tối đa

Ví dụ 12 pod, mỗi Hikari pool tối đa 12 connection:

\[
C_{\text{DB,potential}} = 12 \times 12 = 144
\]

Phải cộng thêm connection từ migration, scheduler, job, replica và các ứng dụng khác, đồng thời dành capacity cho quản trị/HA. Nếu rolling deployment có **surge pods**, số pod nhất thời có thể cao hơn số pod bình thường.

Với HTTP client tới Inventory, 12 pod × 30 max per route = **360 potential HTTP/1.1 connections**. Nếu Inventory chỉ xử lý tốt khoảng 180 concurrent requests, caller có thể đổ quá tải dù pool “không full”. Khi tăng `maxConnections`, cần xem upstream CPU, queue, thread limits và database của chính upstream.

### 9.3. Pool nhỏ/quá lớn

| Hiện tượng | Pool quá nhỏ | Pool quá lớn |
|---|---|---|
| Queue acquire | Tăng, timeout ngay cả khi upstream còn dư | Có thể thấp tại caller |
| Socket/FD/heap | Ít tiêu thụ | Có thể vượt giới hạn |
| Tốc độ upstream | Có thể chưa tận dụng đủ | Có thể quá tải, throughput hữu ích giảm |
| Latency | Cao do chờ slot | Cao do lock/CPU/queue ở upstream |
| Cách sửa | Đo wait + capacity rồi tăng có kiểm soát | Giảm concurrency, bulkhead, backpressure |

Pool size không phải chỉ tiêu thành công. **Throughput thành công, latency p99, error rate và tài nguyên cấp cụm** mới là căn cứ quyết định. Khi nhiều route cùng dùng một HTTP manager, cần giới hạn **per route** để một target nóng không chiếm mọi slot.

## 10. Stale connections, DNS và TLS rotation

### 10.1. Idle connection bị LB/firewall đóng

Load balancer, NAT hoặc server có thể đóng TCP connection không dùng sau một khoảng. Pool còn giữ reference và thử dùng lại, dẫn đến EOF, connection reset, `NoHttpResponseException` hoặc lỗi transport.

Các biện pháp:

- `maxIdleTime` ngắn hơn idle timeout hạ tầng khi hợp lý.
- Connection TTL/max lifetime để làm mới socket cũ.
- Stale validation/keepalive nếu thư viện hỗ trợ và chi phí phù hợp.
- Retry **có giới hạn** với GET/idempotent request; không retry POST có side effect khi outcome chưa rõ.
- Giám sát reset theo thời gian idle, kiểm LB logs và connection churn trước khi chỉnh timeout.

Một reset ở request đầu sau 10 phút không dùng có thể do stale connection, không nhất thiết Inventory down. Nhưng nếu lỗi lặp liên tục và p99 tăng, vẫn phải điều tra vì trải nghiệm người dùng bị ảnh hưởng.

### 10.2. DNS thay IP, rolling deployment

Connection đã mở tới IP cũ có thể tiếp tục được reuse dù DNS đã trả IP mới. TTL của DNS không tự chuyển một TCP connection đang sống sang máy khác. Cần graceful shutdown/connection draining phía target và max connection lifetime phù hợp phía caller. Đo connect errors, endpoint distribution và thời gian thay connection trong rolling deploy.

Không giả định mọi HTTP client re-resolve DNS ở cùng thời điểm, hoặc max lifetime sẽ đảm bảo đổi IP ngay: cache DNS, connection manager và hạ tầng cân bằng tải đều ảnh hưởng.

### 10.3. TLS, mTLS và security

Tái sử dụng TLS session/connection giảm handshake; nhưng TLS/mTLS identity, certificate rotation và CA trust cần vòng đời kết nối phù hợp. Không dùng `trust-all`/tắt hostname verification để khắc phục handshake fail. Với nhiều mTLS identities, cần pool phù hợp identity hoặc thiết kế session/context đúng: một kết nối đã xác thực bằng chứng chỉ A không tự trở thành kết nối của identity B.

Các guardrail bảo mật khác:

- **SSRF:** không cho client tự truyền URL/host đến request proxy; dùng allowlist target, validate URL và chống redirect tới vùng mạng không được phép.
- **Credential scope:** không giữ API key/token của tenant A trong shared client dùng cho B. Nếu có redirect, không forward Authorization ra host khác ngoài policy.
- **Không log secret:** header Authorization, cookie, token provider và body nhạy cảm không đi vào metric/log/trace.
- **Tenant isolation:** cache response và dữ liệu theo user/tenant tách biệt; reuse socket không phải cơ chế cache business hoặc authorization.
- **TLS inspection:** outbound proxy có thể là nơi kết thúc TLS; kiểm trust boundary thay vì coi “có HTTPS” là đủ.

## 11. Pool timeout, retry và HTTP status phải đúng nguyên nhân

| Lỗi | Lý do | Điều cần phân biệt |
|---|---|---|
| Acquire timeout | Pool/route hết slot, caller chưa lấy được connection | Request có thể **chưa hề gửi** tới target |
| Connect timeout | Không tạo được connection mới đúng hạn | Có thể do mạng/DNS/target |
| TLS handshake failure | Certificate/trust/protocol mismatch | Không giải quyết bằng retry vô hạn |
| Response/read timeout | Đã có connection, target không trả đủ đúng hạn | Target **có thể đã thực hiện side effect** |
| Request deadline exceeded | Vượt tổng thời gian cho nghiệp vụ | Có thể do queue + connect + response + retry |
| Gateway timeout | Gateway chờ upstream quá hạn | HTTP 504 có thể xuất phát từ gateway |

**Không tự động trả 429 khi HTTP pool đầy.** `429 Too Many Requests` phù hợp khi **caller vượt quota**. Một pool kết nối tới Inventory bị cạn thường cho thấy service tạm thiếu năng lực hoặc cấu hình sai; trong những kiến trúc thích hợp, API có thể trả **503 Service Unavailable**. Nếu thực sự đóng vai trò gateway và timeout chờ upstream, **504 Gateway Timeout** có thể phản ánh đúng hơn. HTTP status cần dựa trên contract/tầng phát lỗi; không ánh xạ mọi `IOException` thành 503 rồi che mất bug hoặc vấn đề security.

~~~http
HTTP/1.1 503 Service Unavailable
Content-Type: application/problem+json
Cache-Control: no-store

{
  "type": "https://api.example.test/problems/inventory-unavailable",
  "title": "Service Unavailable",
  "status": 503,
  "code": "INVENTORY_UNAVAILABLE",
  "requestId": "req-72b3"
}
~~~

`Retry-After` là tùy chọn cho 503 nếu có ước lượng phục hồi tin cậy; không tự hẹn 5 giây chỉ vì server đang overload mà chưa biết khi nào hồi phục.

### 11.1. Retry amplification

Giả sử browser retry tổng cộng 3 attempts và Orders cũng retry 3 attempts mỗi lần gọi Inventory. Với một thao tác ban đầu, Inventory có thể thấy tới **9 attempts** nếu mọi tầng đều retry. Pool lớn càng làm retry storm dễ dồn tải, kéo dài sự cố.

Giải pháp:

1. Chọn một tầng chịu trách nhiệm retry khi có thể, giới hạn số lần và tổng deadline.
2. Exponential backoff + jitter, tôn trọng `Retry-After` hợp lệ.
3. Phân biệt lỗi **trước khi gửi** với timeout **sau khi target có thể đã ghi**.
4. POST/PATCH thanh toán/tạo đơn chỉ retry nếu provider có idempotency key hoặc điều kiện chống trùng rõ ràng.
5. Bulkhead, bounded queue, circuit breaker và load shedding theo capacity.
6. Đo retry attempts tới target, không chỉ số request từ browser.

`Connection pool` quản lý transport resources, **circuit breaker** hạn chế gọi target đang lỗi, **bulkhead** giới hạn công việc đồng thời, **rate limiter** áp quota theo consumer, **cache** giảm số lượt gọi. Chúng bổ trợ nhưng không thay thế nhau.

### 11.2. Deadline propagation

Nếu client đặt deadline 2 giây còn Orders dùng 700 ms để chờ HTTP pool, 2 giây chờ response và 2 lần retry, request sẽ tiếp tục chạy lâu sau khi client bỏ cuộc. Hãy tính **thời gian còn lại** trước mỗi attempt, giảm timeout xuống theo ngân sách, và ngừng khi deadline đã hết. Trong Java blocking, cần có cơ chế cancellation/interrupt an toàn; trong reactive, propagation của cancellation và response body lifecycle phải được kiểm thử.

## 12. Quan sát HTTP pool và HikariCP để tìm bottleneck

### 12.1. Metric bắt buộc

| Nguồn | Metric/chiều cần xem | Câu hỏi |
|---|---|---|
| HTTP outgoing | RPS, response code, p50/p95/p99 latency, target/route | Downstream có chậm không? |
| HTTP pool | Leased/active, idle/available, pending, max total/per-route | Pool đang đầy hay chỉ target chậm? |
| Acquire | Wait duration, timeout count | Tốn thời gian lấy slot bao nhiêu? |
| Connection lifecycle | Open/close, resets, TLS failures, TTL/idle eviction | Có stale/churn hoặc rotation issue? |
| HTTP/2 | Active streams, concurrency/flow control nếu client hỗ trợ | 1 connection xử lý bao nhiêu request? |
| HikariCP | Active, idle, pending, total, acquire timeout | DB pool có starvation? |
| PostgreSQL | Connection count, CPU/IO, lock wait, slow queries | DB thật có quá tải không? |
| Reliability | Retries, circuit state, bulkhead rejects, deadline exceeded | Có retry storm hay overload? |
| Runtime | Thread pools, event-loop lag, file descriptors, heap, GC | Pool rò tài nguyên không? |
| Business | Tỷ lệ hoàn thành order, 202 pending, duplicate effect | “Nhanh” có còn đúng nghiệp vụ không? |

Spring Boot Actuator/Micrometer thường có Hikari pool metrics khi được cấu hình. Tên series Prometheus và labels tùy phiên bản; kiểm `/actuator/metrics` hoặc exporter thật. Apache HttpClient 5 `PoolingHttpClientConnectionManager.getTotalStats()` và per-route stats có thể được dùng khi muốn instrument manager; JDK HttpClient không phơi cùng API pool statistics. Reactor Netty metrics cần bật theo version/cấu hình phù hợp.

### 12.2. Trace tách thời gian chờ pool và chờ target

~~~text
Trace A: GET /orders/101, tổng ~1,000 ms
  acquire Inventory connection:  760 ms
  outbound Inventory HTTP:       200 ms
  JSON mapping:                   10 ms

Trace B: GET /orders/102, tổng ~1,000 ms
  acquire Inventory connection:    1 ms
  outbound Inventory HTTP:       950 ms
  JSON mapping:                   10 ms
~~~

Trace A nghi ngờ sizing/queue/leak; Trace B nghi ngờ downstream latency hoặc mạng. Cần dùng pool metrics/histogram acquire nếu client không tự phát span acquire riêng; không giả định outbound span đã phân tách tất cả pha.

### 12.3. Nhận diện connection leak

~~~text
Trước deploy:
  hikari.active=2  idle=10  pending=0
Sau deploy:
  hikari.active=12 idle=0   pending=35
  DB CPU vẫn thấp, request rate không tăng
  acquisition timeout tăng đều
~~~

Có thể là connection leak, transaction dài hoặc DB locks; đừng kết luận chỉ từ một metric. Đọc thread dump, transaction duration, slow query/lock wait, trace và code `try-with-resources`. Hikari `leakDetectionThreshold` có thể hỗ trợ điều tra connection giữ quá lâu nhưng **không chứng minh** tất cả cảnh báo đều là leak.

Với HTTP streaming, quên đóng response body tạo hiện tượng leased/pending tương tự. Đừng dùng raw user ID, order ID, token hay tenant UUID làm metric label; route template/target/error enum có cardinality kiểm soát mới phù hợp.


## 13. Kiểm thử: chứng minh reuse, giới hạn pool và không rò connection

### 13.1. Chia test theo mục đích

| Tầng test | Phụ thuộc | Bất biến cần kiểm |
|---|---|---|
| Unit | Fake clock, fake adapter | Timeout budget, retry policy, status mapping, chọn target |
| HTTP integration | Local fake HTTP server hoặc WireMock | Response body, HTTP status, timeout, cancellation, redirect, TLS theo khả năng |
| HTTP pool integration | Fake target có delay/connection control | Max per-route, acquire timeout, leased/available/pending, release |
| JDBC integration | PostgreSQL Testcontainers + Hikari | Concurrency, transaction, SQL locks, DB pool starvation |
| Component test | App + DB + downstream fake | REST → DB → HTTP → error mapping, idempotency/rollback |
| Load/staging | Nhiều instance và target có kiểm soát | Peak throughput, p99, resource budget, recovery và autoscaling |

**Không đồng nhất “dùng chung `HttpClient`” với “đã chứng minh một TCP connection được tái sử dụng”.** Test chức năng với cùng instance chứng minh code tái sử dụng đối tượng client; muốn chứng minh reuse socket cần thêm connection statistics ở cả hai đầu, server-side peer connection IDs hoặc packet capture phù hợp. Việc assert remote port giống nhau trong mọi môi trường thường gây flaky tests vì LB/server có thể chủ động đóng connection.

### 13.2. Java JUnit 5 với HTTP target thật trên localhost

Dùng `com.sun.net.httpserver.HttpServer` của JDK để có một server HTTP đơn giản mà test tự quản lý lifecycle:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class HttpClientReuseIT {
    @Test
    void sharedClientCanServeManyRequests() throws Exception {
        AtomicInteger handled = new AtomicInteger();
        HttpServer target = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);

        target.createContext("/ping", exchange -> {
            handled.incrementAndGet();
            byte[] body = "ok".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                "Content-Type", "text/plain");
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        target.start();
        try {
            String url = "http://127.0.0.1:"
                + target.getAddress().getPort() + "/ping";

            HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(2))
                .build();

            for (int i = 0; i < 20; i++) {
                var request = HttpRequest.newBuilder(URI.create(url))
                    .timeout(Duration.ofSeconds(3))
                    .GET()
                    .build();
                var response = client.send(
                    request, HttpResponse.BodyHandlers.ofString());
                assertEquals(200, response.statusCode());
                assertEquals("ok", response.body());
            }

            assertEquals(20, handled.get());
        } finally {
            target.stop(0);
        }
    }
}
~~~

**Giới hạn của test:** 20 HTTP calls thành công bằng **một `HttpClient` instance**, nhưng có thể chúng dùng nhiều socket do server/runtime. Muốn xem pooled reuse, dùng server đo số TCP connections hoặc Apache connection manager `getTotalStats()`. Với JDK HTTP/2, cần target hỗ trợ HTTP/2 thực sự nếu muốn xác nhận version/stream behavior; HTTP server JDK trong ví dụ là fake HTTP đơn giản.

### 13.3. Test acquisition timeout với Apache max per route = 2

Tạo fake Inventory giữ **hai HTTP/1.1 requests** chưa trả response bằng `CountDownLatch`. Cấu hình per-route pool max 2, `connectionRequestTimeout=300ms`.

~~~text
Given:
  target accepts GET /slow but blocks response until release latch
  client pool maxTotal=2, maxPerRoute=2
  acquisition timeout=300ms

When:
  request A và request B chạy song song, chiếm 2 connections
  request C gọi cùng route khi A/B vẫn đang chờ

Then:
  C fail do acquisition timeout nếu không có slot kịp thời
  target chưa nhận request C
  release latch để A/B hoàn tất và đọc/đóng body
  tiếp theo request D thành công
  cuối test pool leased == 0, không rò resource
~~~

Dùng barrier/latch và deadline thay vì `Thread.sleep` mù. Kiểm cả số request **thật sự đến target**, không chỉ status của caller. Đối với error mapping, service có thể trả 503 theo hợp đồng khi pool cạn; tuy nhiên nếu API có quota per-user và caller vượt quota thì policy riêng 429. Không cố định “mọi acquire timeout = HTTP 429”.

### 13.4. Test JDBC pool starvation bằng PostgreSQL thật

Dùng Testcontainers PostgreSQL (đúng migration/driver PostgreSQL đang triển khai) và Hikari max 2:

1. Tạo hai worker/transaction chủ động giữ JDBC connections bằng latch.
2. Để request thứ ba thử `dataSource.getConnection()`, kiểm timeout gần `connection-timeout`.
3. Release hai connection trong `finally`/try-with-resources.
4. Gọi query mới, xác minh pool phục hồi và DB không mất dữ liệu.
5. Chèn phiên bản service giữ connection trong khi gọi fake HTTP chậm, so với phiên bản tách transaction; đo thời gian `Hikari active` và `pending`.
6. Với `@SpringBootTest(webEnvironment=RANDOM_PORT)`, nhớ server xử lý trong thread/transaction khác: `@Transactional` trên test method không tự rollback commit của request HTTP.

Một test H2 không chứng minh được PostgreSQL lock/isolation và connection limits. Nếu app dùng RLS/tenant context, kiểm pooled JDBC connection **không giữ lại session tenant** khi được trả cho request khác; cấu hình `SET LOCAL` trong transaction và test nhiều tenant.

### 13.5. Fault injection và regression matrix

| Tình huống | Kỳ vọng / bằng chứng |
|---|---|
| Lượt cold và warm tới cùng host | Warm giảm chi phí setup khi reuse được; đo opened connections thay vì đoán |
| Pool per-route đạt max | Pending/acquire timeout có giới hạn, không OOM |
| Downstream chậm nhưng pool còn idle | Timeout đúng request/deadline, trace chỉ ra target |
| Target đóng idle socket | Client phát hiện/reset và retry an toàn nếu phương thức cho phép |
| Target thay IP sau rolling deploy | Connection lifetime/draining giúp dần dùng target mới |
| HTTP/2 nhiều streams | Không suy 1 request = 1 socket; kiểm max streams/latency |
| Streaming response bị bỏ dở | Close giải phóng resources, pool không kẹt leased mãi |
| JDBC transaction chờ HTTP 4 giây | Hikari pending tăng; tách transaction giảm thời gian giữ conn |
| Scale từ 4 lên 16 pod | Tổng DB/outbound connections vẫn nằm trong ngân sách |
| GET timeout rồi retry | Backoff+jitter, deadline không bị vượt |
| POST payment timeout sau gửi | Outcome có thể UNKNOWN; không tạo double-charge |
| Token Tenant A dùng chung HTTP client với Tenant B | Header/response không rò credentials hoặc dữ liệu |
| Pool shutdown | Không còn eviction threads, sockets/timers bị rò |

### 13.6. Load testing không làm đẹp p99 giả tạo

Một phép thử hiệu năng có kiểm soát nên ghi:

- RPS **offered** và RPS **thành công**, status 2xx/4xx/5xx, timeout count.
- p50/p95/p99 **theo cả thời gian chờ acquire và response**, không chỉ service time.
- Active/idle/pending HTTP connections, HTTP/2 streams, Hikari pool và upstream capacity.
- CPU, memory, sockets/FD, GC, thread/event-loop lag và TCP resets nếu có.
- Số retries **thật sự tới target**, timeout budget, số pod và fan-out.
- Phiên bản protocol, kết thúc TLS, idle timeout của LB, DNS/lifetime và image/runtime version.

Tăng tải từng bậc, đo steady-state sau warm-up, có ngưỡng dừng và tài nguyên staging riêng. Nếu load generator chỉ gửi request tiếp theo khi request trước đã hoàn tất, nó có thể bỏ sót tail latency trong thời gian nghẽn (**coordinated omission**). Dùng chiến lược đo phù hợp và công bố cả lỗi/từ chối, không loại request timeout khỏi percentile để kết quả trông tốt hơn.

## 14. Đừng bỏ quên cache, phân trang và hiệu ứng fan-out

Connection pooling chỉ giảm chi phí mạng, không biến API gọi quá nhiều downstream thành tối ưu:

- **N+1 HTTP calls:** mỗi order gọi Inventory một lần; một trang 100 order có thể phát 100 requests. Nếu target hỗ trợ batch API, có thể giảm từ 100 calls xuống một số ít calls.
- **N+1 DB queries:** JPA lazy loading tạo nhiều SQL round-trips. Tối ưu query/fetch plan và giới hạn page size trước khi tăng Hikari pool.
- **Cache đọc công khai:** cache hợp lệ có thể tránh gọi downstream; phải phân quyền dữ liệu tenant/user, `Cache-Control`, freshness và invalidation đúng.
- **ETag/conditional requests:** giảm payload nếu representation không đổi, nhưng cần kiểm response status, proxy và semantics của API.
- **Fan-out:** `GET /orders` gọi Inventory + Pricing + Shipping làm concurrency downstream tăng nhiều hơn số request đầu vào; nếu gửi parallel, p99 có thể phụ thuộc hop chậm nhất.
- **Idempotency:** retry có thể phát thêm HTTP calls ngay cả khi business operation là một; key và dedupe phải đặt tại đúng ranh giới.

**Tối ưu đường gọi trước rồi tối ưu số connection.** Nếu mỗi request gây 100 downstream calls không cần thiết, mở thêm 200 connections có thể chỉ chuyển điểm nghẽn sang Inventory. Cân bằng concurrency, batch/cache và mức nhất quán nghiệp vụ.

## 15. Anti-pattern và cách khắc phục

| Sai lầm | Hệ quả | Cách sửa |
|---|---|---|
| Tạo `HttpClient` hoặc manager mới mỗi request | Tăng TCP/TLS handshake, socket churn | Singleton bean/client theo target và identity |
| Quên đóng streaming body hoặc JDBC Connection | Leased tăng mãi, pending timeout | Try-with-resources/lifecycle rõ |
| Bật pool nhưng không đặt acquisition timeout | Queue chờ vô hạn | Bounded pending + acquire timeout |
| Tăng `maxConnections` khi thấy chậm | Downstream/DB quá tải | Đo pending/CPU/locks/upstream capacity |
| Dùng một pool không có giới hạn per-route | Một target nóng ảnh hưởng target khác | Per-route budgets hoặc separate pools |
| Giữ JDBC transaction khi gọi HTTP | Chiếm Hikari/locks trong lúc đợi mạng | Transaction ngắn, outbox/version |
| Chỉ đặt connect timeout | Request reused connection vẫn có thể treo | Response timeout và operation deadline |
| Retry mọi IOException | Retry storm, duplicate side effects | Retry budget, jitter, idempotency |
| Gắn token user vào shared client default | Cross-tenant credential leak | Auth per request, credential isolation |
| Không quan tâm LB idle timeout | Reset ở request sau thời gian idle | Idle eviction/lifetime/validation |
| Nhầm HTTP/2 max streams với socket count | Sizing sai | Theo dõi streams, backpressure |
| Mỗi pod tự mở hàng trăm DB connections | Vượt ngân sách cấp cụm | Sizing theo autoscaling max và DB limit |
| Lấy URL downstream trực tiếp từ request | SSRF, credential exfiltration | Destination allowlist, không redirect tùy ý |
| Chỉ nhìn HTTP status, bỏ pool metrics | Không xác định được acquire wait/leak | Traces, pool stats, upstream health |
| Mở nhiều client theo tenant không giới hạn | Quá nhiều pool nhỏ, socket/memory phình | Tách theo identity khi cần và quản lý lifecycle/upper bound |

## 16. Bài tập thực hành

### Bài tập 1 — Tính concurrency và ngân sách pool

Orders API gọi Inventory 240 lần/giây. Thời gian giữ connection HTTP/1.1 **trung bình** 125 ms. Có 8 pod, max 20 connections/pod tới Inventory. Inventory chỉ chịu tốt khoảng 100 concurrent requests.

Hãy tính concurrency trung bình toàn cụm, potential connections toàn cụm; đánh giá khi peak gấp đôi và latency tăng. Giải thích tại sao phép tính số **physical connections** không áp dụng nguyên xi cho HTTP/2.

**Đối chiếu:** \(240 \times 0.125 = 30\) requests in-flight trung bình, 8 × 20 = 160 potential connections; đừng coi 160 là cần thiết hoặc là capacity an toàn. Nên thử tải, đo queue và giới hạn concurrency phù hợp upstream.

### Bài tập 2 — Refactor code tạo HTTP client mỗi request

Mã cũ:

~~~java
@GetMapping("/api/stock")
String stock(@RequestParam String sku) throws Exception {
    var client = HttpClient.newHttpClient();
    var request = HttpRequest.newBuilder(
        URI.create("https://inventory.example.test/stock?sku=" + sku))
        .GET().build();
    return client.send(
        request, HttpResponse.BodyHandlers.ofString()).body();
}
~~~

Hãy sửa thành `@Bean HttpClient` được inject vào adapter, encode query param, thêm connect/request timeout, kiểm HTTP status, tránh trả JSON body lỗi như một 200 của Shop API. Viết test với fake target.

**Tiêu chí:** Không tạo client mỗi call; không cho user chỉ định target URL; body và errors được xử lý đúng contract.

### Bài tập 3 — Apache pool saturation

Cấu hình Apache HttpClient 5 `maxTotal=4`, `maxPerRoute=2`, acquisition timeout 300 ms. Fake target trì hoãn hai request đầu bằng latch. Gửi ba lời gọi đồng thời đến cùng target.

Hãy mô tả kết quả thứ ba, release hai connection, kiểm request mới thành công và đo `leased/available/pending`. Phân biệt acquisition timeout với response timeout.

**Tiêu chí:** Test có barrier/latch và deadline, chứng minh không có request thứ ba đến target khi chưa acquire.

### Bài tập 4 — HikariCP starvation

Orders API có 20 requests đồng thời, Hikari max 10. Mỗi transaction đọc DB rồi chờ Payment API 4 giây. Dự đoán metric Hikari active/idle/pending và ảnh hưởng tới endpoint không liên quan Payment. Thiết kế lại bằng transaction ngắn, outbox và idempotency.

**Tiêu chí:** Giảm thời gian giữ DB connection mà không làm mất bất biến thanh toán khi timeout UNKNOWN.

### Bài tập 5 — HTTP/2 streams

Inventory hỗ trợ HTTP/2 với số stream đồng thời giới hạn. Có một kết nối TLS tới target, caller tạo hàng trăm requests song song. Tại sao vẫn có queue/latency? Thiết kế test đo negotiated protocol, active streams, timeout và concurrency bulkhead; so sánh với HTTP/1.1.

**Tiêu chí:** Phân biệt physical connection, stream và upstream capacity.

### Bài tập 6 — Stale socket sau deploy

Lượt request đầu sau 10 phút idle hay bị connection reset; các lần kế tiếp thành công. LB có idle timeout thấp hơn client retention. Đề xuất idle eviction, max lifetime, metrics và test giả lập target đóng socket. Vì sao không được retry mù `POST /payments/capture`?

**Tiêu chí:** Xử lý an toàn và có bằng chứng qua metrics; không gây double-charge.

### Bài tập 7 — Debug p99 tăng dù 5xx thấp

Sau deploy, p99 tăng từ 150 ms lên 2 giây. Hikari active=max, pending=35, DB CPU thấp, traffic gần như không đổi. Nêu ít nhất ba giả thuyết, số liệu cần kiểm, cách phân biệt leak/lock/transaction chờ HTTP, và kế hoạch benchmark sau sửa.

**Tiêu chí:** Không tăng max pool vô điều kiện; đo thời gian giữ connection, lock waits và acquire duration.

### Bài tập 8 — Tổng số kết nối qua autoscaling

Production có 16 pods, mỗi Hikari `maximumPoolSize=20`; PostgreSQL giới hạn 250 connections, cần giữ 50 cho quản trị/ứng dụng khác. Hãy tính connection potential của Orders API và đặt ngân sách max/pod khi 16 pods cùng hoạt động. Thảo luận surge pods, scheduler/migration và shared DB pooler.

**Đối chiếu:** 16 × 20 = 320 > 200 khả dụng. Với đúng 16 pod và không nguồn kết nối ứng dụng nào khác, 12/pod cho 192 connections; cần **dự phòng thêm** nếu có surge pods và background workers.

## 17. Câu hỏi tự kiểm tra, checklist và tài liệu

### Câu hỏi nhanh

1. **Một `HttpClient` có luôn tương đương một TCP connection không?** Không; một instance có thể quản lý nhiều connection và/hoặc stream.
2. **HTTP/1.1 có mặc định hỗ trợ persistent connection không?** Có, dù server/LB có thể đóng.
3. **HTTP/2 có đồng nghĩa vô hạn requests đồng thời không?** Không; còn max streams, flow control và khả năng upstream.
4. **Acquisition timeout khác connect timeout thế nào?** Một cái chờ slot trong pool, một cái chờ tạo connection mới.
5. **Response timeout có tự là toàn bộ business deadline không?** Không; còn chờ pool, parse, retry và nhiều hop.
6. **`close()` của JDBC Connection do Hikari cấp có nghĩa gì?** Thường trả logical connection về pool.
7. **Vì sao HTTP call trong `@Transactional` nguy hiểm?** Có thể giữ DB connection/locks trong khi chờ mạng.
8. **Dùng \(\lambda \times p95\) để tính Little's Law có đúng không?** Không; cần thời gian trung bình của giai đoạn được xét.
9. **Tăng max connections trên mỗi pod có luôn tăng throughput?** Không, có thể quá tải DB/downstream.
10. **Có được dùng pooled socket chung cho nhiều tenant không?** Có thể nếu protocol/identity cho phép, nhưng không được chia sẻ token/cookie/cache hay bỏ authorization.
11. **Pool có tự retry POST an toàn không?** Không; cần hợp đồng idempotency cho effect.
12. **Làm sao biết pool đang nghẽn?** Kết hợp leased/idle/pending, acquire wait, timeout và trace.
13. **Vì sao cần max idle/max lifetime?** Để giảm stale sockets, kết nối IP/cert cũ và giữ tài nguyên quá lâu.
14. **Pooling có thay batch/cache để chữa N+1 không?** Không; phải giảm lượt gọi không cần thiết.

### Checklist vận hành

- HTTP client có được tái sử dụng, có vòng đời shutdown và response luôn được đóng/tiêu thụ?
- Đã biết negotiated protocol HTTP/1.1 hay HTTP/2 và giới hạn stream/request?
- Max total/per-route, pending queue và acquire/connect/response/deadline có được đặt rõ?
- Idle TTL, max lifetime, DNS/LB/TLS rotation đã được kiểm theo hạ tầng?
- HikariCP được tính theo **số pod tối đa** cùng connection budget của DB?
- Transaction DB có được giữ ngắn, không chiếm connection khi chờ network không?
- Retries có budget, jitter, deadline, `Retry-After` và idempotency khi có tác dụng phụ?
- Pool metrics và trace phân biệt wait-acquire với wait-upstream, không chứa dữ liệu nhạy cảm?
- Có test saturation/leak/stale socket, cross-tenant credentials, resource exhaustion và load test có ngưỡng dừng?
- Đã cân nhắc batch, cache và giảm fan-out trước khi tăng connection count?

### Tài liệu tham khảo

- **RFC 9110 — HTTP Semantics:** https://www.rfc-editor.org/rfc/rfc9110
- **RFC 9113 — HTTP/2:** https://www.rfc-editor.org/rfc/rfc9113
- **JDK 17 `HttpClient`:** https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
- **Spring Framework — REST Clients:** https://docs.spring.io/spring-framework/reference/integration/rest-clients.html
- **Apache HttpComponents Client 5:** https://hc.apache.org/httpcomponents-client-5.4.x/
- **Reactor Netty HTTP Client:** https://projectreactor.io/docs/netty/release/reference/http-client.html
- **HikariCP configuration:** https://github.com/brettwooldridge/HikariCP#configuration-knobs-baby
- **Spring Boot DataSource:** https://docs.spring.io/spring-boot/reference/data/sql.html
- **Spring Boot Metrics:** https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- **OWASP SSRF Prevention Cheat Sheet:** https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html

**Ghi nhớ:** Connection pooling giảm chi phí tạo kết nối và cho phép tái sử dụng transport, nhưng hiệu quả thật phụ thuộc **giới hạn tài nguyên, vòng đời response/transaction, concurrency budget và năng lực hệ thống đích**. Hệ thống REST có hiệu năng tốt phải đồng thời kiểm soát HTTP keep-alive/HTTP2 streams, HikariCP, timeout/retry/idempotency, TLS, bảo mật, metric và kiểm thử tải — không phải chỉ tăng số socket.
