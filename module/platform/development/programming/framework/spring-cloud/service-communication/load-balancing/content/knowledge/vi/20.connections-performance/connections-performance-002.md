# Giới hạn pool tổng thể và theo địa chỉ đích

Khi **Spring Cloud LoadBalancer** chọn một `ServiceInstance` cho request, HTTP client vẫn phải mượn hoặc tạo một kết nối mạng để gọi bản sao đó. Nếu nhiều request đến đồng thời, **connection pool** giúp tái sử dụng socket và kiểm soát số kết nối được mở. Tuy nhiên, không phải mọi giới hạn pool đều có cùng phạm vi: một số giới hạn dành cho **toàn bộ connection manager**, còn một số chỉ giới hạn các kết nối tới **một HTTP route hoặc một địa chỉ đích**.

Đây là điểm quan trọng của chương **Kết nối và hiệu năng**. Ví dụ, đặt `maxConnTotal = 30` và `maxConnPerRoute = 5` không có nghĩa mỗi dịch vụ được dùng tối đa 30 kết nối. Nếu LoadBalancer chọn một instance vật lý, request tới instance đó vẫn bị ràng buộc bởi mức 5/route, dù toàn pool còn rất nhiều chỗ trống.

Bài học tập trung vào ba vấn đề: **hiểu đúng phạm vi giới hạn**, **cấu hình cho RestClient, WebClient và OpenFeign**, và **đo để phân biệt nghẽn pool với lỗi LoadBalancer hoặc backend chậm**.

## 1. Service ID không phải một HTTP route

Giả sử `order-service` gọi:

~~~http
GET http://catalog-service/products/42
~~~

Discovery cung cấp ba `ServiceInstance` cho service ID `catalog-service`:

| Instance ID | URI vật lý | HTTP route thông thường |
|---|---|---|
| `catalog-1` | `http://10.0.1.11:8081` | HTTP tới `10.0.1.11:8081` |
| `catalog-2` | `http://10.0.1.12:8081` | HTTP tới `10.0.1.12:8081` |
| `catalog-3` | `http://10.0.1.13:8081` | HTTP tới `10.0.1.13:8081` |

Spring Cloud LoadBalancer nhận URL logic, lấy danh sách instance rồi chọn **một** instance. HTTP transport sẽ làm việc với endpoint đã chọn; connection pool không tự truy vấn registry hoặc áp dụng round-robin.

~~~mermaid
flowchart TD
    A["order-service gọi<br/>http://catalog-service"]
    B["Spring Cloud LoadBalancer<br/>chọn ServiceInstance"]
    C["catalog-1<br/>10.0.1.11:8081"]
    D["catalog-2<br/>10.0.1.12:8081"]
    E["catalog-3<br/>10.0.1.13:8081"]
    P["HTTP connection manager<br/>giới hạn tổng T"]
    R1["Route 1<br/>giới hạn P"]
    R2["Route 2<br/>giới hạn P"]
    R3["Route 3<br/>giới hạn P"]
    A --> B
    B --> C
    B --> D
    B --> E
    C --> P
    D --> P
    E --> P
    P --> R1
    P --> R2
    P --> R3
~~~

Sơ đồ mô tả sự phân tách trách nhiệm, không ngụ ý mỗi request đi qua cả ba route. Request chỉ dùng route tương ứng với instance đã được chọn.

Với **Apache HttpClient 5**, một `HttpRoute` thường bao gồm scheme, target host/port và thông tin proxy/tunnel nếu có. Do đó, “route” không đơn giản là tên service ID và cũng không luôn đồng nghĩa một instance: proxy, cùng endpoint, scheme hoặc cấu hình mạng có thể làm cách nhóm route khác đi.

## 2. Hai giới hạn chính trong Apache HttpClient 5

Apache HttpClient 5 cung cấp `PoolingHttpClientConnectionManager` với hai thông số nổi bật:

- **`maxConnTotal`:** số connection tối đa mà **một connection manager** được phép quản lý trên tất cả các route của manager đó.
- **`maxConnPerRoute`:** số connection tối đa dành cho **mỗi HTTP route** của manager đó, trừ khi một route được cấu hình giới hạn riêng.

Các API cấu hình bằng builder:

~~~java
PoolingHttpClientConnectionManager manager =
        PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(30)
                .setMaxConnPerRoute(5)
                .build();
~~~

Khi dùng HTTP/1.1 với một request đang chiếm một connection, số request đang sử dụng connection tại cùng thời điểm thường bị chặn bởi cả hai điều kiện:

~~~text
Tổng kết nối của tất cả route <= maxConnTotal
Kết nối của từng route      <= maxConnPerRoute
~~~

Đây là mô hình đơn giản hóa để tính capacity. HTTP/2 có multiplexing, nên **số request đồng thời không nhất thiết bằng số TCP connection**. Chính sách pooling, proxy và implementation cụ thể cũng có thể ảnh hưởng cách cấp phát.

### Ví dụ số học với pool tổng 6, mỗi route 4

| Yêu cầu đồng thời | Tổng giới hạn = 6 | Giới hạn mỗi route = 4 | Kết quả có thể đạt |
|---|---|---|---|
| A cần 6, B cần 0 | Chưa đầy tổng khi mới có 4 | A tối đa 4 | 4 request ở A; 2 request phải chờ dù tổng còn 2 slot |
| A cần 4, B cần 4 | Chỉ 6 tổng | A và B mỗi bên ≤4 | Tối đa 6 đang sử dụng; ít nhất 2 chờ |
| A cần 2, B cần 2 | Đủ tổng | Không route nào chạm ngưỡng | 4 đang sử dụng |
| A cần 0, B cần 7 | Tổng còn dư | B tối đa 4 | 4 đang sử dụng; 3 chờ |
| A cần 4, B cần 0, C cần 2 | Đủ tổng | A tối đa 4; C tối đa 4 | 6 đang sử dụng |

Bảng giả định request không hoàn tất trong thời gian khảo sát, pool đã có hoặc có thể tạo kết nối, và mọi request thuộc hai/ba route vật lý riêng biệt. Nếu kết nối đang bận được trả về, số request mới có thể tiếp tục thực thi; bảng **không** giới hạn tổng request hoàn thành trong một giây.

Một hệ quả dễ bỏ sót: **tăng `maxConnTotal` không giải quyết nghẽn một route đã chạm `maxConnPerRoute`**. Ngược lại, chỉ tăng `maxConnPerRoute` không giải quyết nghẽn khi toàn bộ manager đã đạt `maxConnTotal`.

## 3. Giới hạn pool không phải giới hạn tải toàn hệ thống

Các giới hạn trên chỉ có hiệu lực trong phạm vi **một `PoolingHttpClientConnectionManager` đang thực sự được chia sẻ**.

Ví dụ, ứng dụng có ba client khác nhau, mỗi client tạo một connection manager riêng với `maxConnTotal=30`. Khi đó, không thể suy ra toàn tiến trình bị giới hạn ở 30 connection; tổng số connection có thể tăng cao hơn vì có **ba pool độc lập**.

Cũng cần phân biệt:

| Khái niệm | Phạm vi | Không thể suy ra |
|---|---|---|
| `maxConnTotal` của Apache | Tất cả route trong **một manager** | Giới hạn toàn JVM hoặc toàn cụm |
| `maxConnPerRoute` của Apache | **Một route** trong manager | Giới hạn theo service ID |
| Thread pool của ứng dụng | Số công việc blocking có thể chạy | Số connection vật lý |
| Rate limiter | Tần suất request được phép bắt đầu | Số connection đang sống |
| Bulkhead/semaphore | Số lời gọi đồng thời qua một phạm vi nghiệp vụ | Số socket HTTP |
| Max concurrent streams của HTTP/2 | Stream đồng thời trên một HTTP/2 connection | Số TCP connection |
| LoadBalancer cache | Danh sách `ServiceInstance` | HTTP connection reuse |

Nếu yêu cầu là “không quá 100 lời gọi đồng thời tới payment-service trên toàn ứng dụng”, chỉ đặt `maxConnTotal=100` thường **không đủ**. Cần chính sách concurrency/bulkhead ở tầng ứng dụng hoặc HTTP client, và nếu muốn giới hạn toàn cụm có thể cần cơ chế phân tán.

## 4. Quan hệ giữa LoadBalancer và số route

Một service ID có thể dẫn tới nhiều route vật lý. Khi autoscaling làm tăng số instance, số route được sử dụng cũng có thể tăng, ngay cả khi request rate tổng không đổi.

Giả sử:

~~~text
maxConnTotal    = 24
maxConnPerRoute = 8

catalog-service:
  catalog-1 -> 10.0.1.11:8081
  catalog-2 -> 10.0.1.12:8081
  catalog-3 -> 10.0.1.13:8081
~~~

Khi cả ba instance được chọn nhiều lần, tổng giới hạn cho cả ba route vẫn là **24**, không phải `3 × 24`. Mỗi route không được vượt 8 connection theo ví dụ. Nếu ứng dụng còn dùng chính manager đó để gọi `payment-service`, các route của payment cùng tranh tài nguyên **tổng 24**.

### Đặt per-route quá thấp

Nếu một nhóm request bị chính sách zone/hint chỉ cho phép gọi `catalog-1`, toàn bộ tải có thể dồn về một route. Cho dù manager có `maxConnTotal=100`, với `maxConnPerRoute=4`, phần lớn request có thể chờ mượn connection.

### Đặt total quá thấp

Giả sử ba instance catalog và hai instance payment đều đang phục vụ. Mỗi route còn dung lượng riêng, nhưng nhiều request ở các route khác có thể giữ hết `maxConnTotal`. Request tới một route mới có thể phải chờ vì **giới hạn tổng**, dù route đó chưa bao giờ đạt `maxConnPerRoute`.

### Một route không còn nhận traffic

Khi một instance bị hủy đăng ký, LoadBalancer có thể ngừng chọn nó khi dữ liệu discovery/cache cập nhật, nhưng connection pool có thể vẫn giữ một số **kết nối idle** tới endpoint cũ cho đến khi hết TTL/idle time hoặc được dọn. Đây là hai vòng đời khác nhau: **danh sách instance** và **connection vật lý**.

## 5. Cấu hình RestClient với pool tổng và theo route

Ví dụ sau áp dụng với Spring Framework có `RestClient` (từ 6.1), Spring Cloud LoadBalancer và Apache HttpClient 5 tương thích.

Dependency minh họa với Gradle Kotlin DSL, giả định đã có BOM/release train tương thích Spring Boot:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    implementation("org.apache.httpcomponents.client5:httpclient5")
}
~~~

### Tạo một connection manager dùng chung

Để đo được `PoolStats`, manager được khai báo thành một bean riêng. Spring chịu trách nhiệm đóng manager khi application context dừng; `CloseableHttpClient` được cấu hình **shared connection manager** để không đóng manager trước các bean khác.

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.Timeout;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class PooledRestClientConfiguration {

    @Bean(value = "sharedConnectionManager", destroyMethod = "close")
    PoolingHttpClientConnectionManager sharedConnectionManager() {
        ConnectionConfig connection = ConnectionConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(2))
                .setSocketTimeout(Timeout.ofSeconds(8))
                .build();

        return PoolingHttpClientConnectionManagerBuilder.create()
                .setMaxConnTotal(6)
                .setMaxConnPerRoute(4)
                .setDefaultConnectionConfig(connection)
                .build();
    }

    @Bean(destroyMethod = "close")
    CloseableHttpClient pooledHttpClient(
            @Qualifier("sharedConnectionManager")
            PoolingHttpClientConnectionManager manager) {

        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(
                        Timeout.ofMilliseconds(500))
                .setResponseTimeout(Timeout.ofSeconds(6))
                .build();

        return HttpClients.custom()
                .setConnectionManager(manager)
                .setConnectionManagerShared(true)
                .setDefaultRequestConfig(requestConfig)
                .disableAutomaticRetries() // Chỉ để phép đo lab rõ ràng.
                .build();
    }

    @Bean("catalogRestClientBuilder")
    @LoadBalanced
    RestClient.Builder catalogRestClientBuilder(
            CloseableHttpClient pooledHttpClient) {
        return RestClient.builder()
                .requestFactory(
                        new HttpComponentsClientHttpRequestFactory(
                                pooledHttpClient));
    }

    @Bean
    RestClient catalogRestClient(
            @Qualifier("catalogRestClientBuilder")
            RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }

    // Bean gọi URL vật lý: cũng chia sẻ đúng HTTP pool ở trên.
    @Bean("directLabRestClient")
    RestClient directLabRestClient(
            CloseableHttpClient pooledHttpClient) {
        return RestClient.builder()
                .requestFactory(
                        new HttpComponentsClientHttpRequestFactory(
                                pooledHttpClient))
                .build();
    }
}
~~~

Các thông số trong ví dụ là **giá trị lab**, không phải khuyến nghị production:

| Tham số | Giá trị | Ý nghĩa |
|---|---|---|
| `maxConnTotal` | 6 | Tất cả route trong manager chia sẻ tối đa 6 connection |
| `maxConnPerRoute` | 4 | Một route vật lý tối đa 4 connection |
| `connectionRequestTimeout` | 500 ms | Chờ mượn connection từ pool tối đa 500 ms |
| `connectTimeout` | 2 s | Thời gian thiết lập connection mới |
| `responseTimeout` | 6 s | Chờ response theo semantics Apache HttpClient 5 |
| `socketTimeout` | 8 s | Timeout I/O mặc định ở socket |
| `disableAutomaticRetries` | Bật | Tránh HTTP transport tự retry trong thí nghiệm |

`connectionRequestTimeout` là tham số đặc biệt quan trọng khi khảo sát **cạn pool**. Khi route hoặc manager đã chạm ngưỡng, một request có thể chờ mượn connection rồi timeout **trước khi server nhận request đó**.

Với `setConnectionManagerShared(true)`, cần quản lý rõ vòng đời manager; không giả định background eviction do `CloseableHttpClient` quản lý sẽ chạy như khi client sở hữu manager. Khi cần dọn connection idle, cấu hình TTL/idle eviction/scheduler phù hợp với cách sở hữu pool và phiên bản đang sử dụng.

### Hai bean RestClient nhưng một pool

Cả `catalogRestClient` và `directLabRestClient` đều dùng **cùng `pooledHttpClient`/connection manager**. Vì vậy, request từ hai bean cạnh tranh `maxConnTotal=6` nếu các route được giữ trong manager đó.

Tuy nhiên, chỉ `catalogRestClient` được tạo từ `@LoadBalanced RestClient.Builder`: nó giải quyết service ID theo Spring Cloud LoadBalancer. `directLabRestClient` được dùng cho các URI vật lý, giúp thử riêng giới hạn route mà không phụ thuộc thuật toán chọn instance.

Trong ứng dụng Spring Boot, nếu cần các auto-customizer, metrics và tracing mặc định, cân nhắc `RestClientBuilderConfigurer` và kiểm tra lại các customizer sau khi cấu hình builder thủ công.

## 6. Quan sát các trạng thái: leased, available và pending

Apache HttpClient 5 có `PoolStats`:

- `leased`: connection đang được mượn và phục vụ request.
- `available`: connection rảnh có thể được tái sử dụng, tùy trạng thái hợp lệ.
- `pending`: yêu cầu mượn connection đang chờ được cấp.
- `max`: giới hạn của phạm vi đang được quan sát.

Có thể chụp thống kê tổng pool:

~~~java
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.core5.pool.PoolStats;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;

@Component
class PoolInspector {

    private final PoolingHttpClientConnectionManager manager;

    PoolInspector(
            @Qualifier("sharedConnectionManager")
            PoolingHttpClientConnectionManager manager) {
        this.manager = manager;
    }

    void printTotal() {
        PoolStats stats = manager.getTotalStats();

        System.out.printf(
                "pool total: leased=%d available=%d pending=%d max=%d%n",
                stats.getLeased(),
                stats.getAvailable(),
                stats.getPending(),
                stats.getMax());
    }
}
~~~

Để phân biệt tình huống **tổng pool đầy** với **một route đầy**, cần xem thêm `manager.getStats(HttpRoute)` cho route được chọn. Việc dựng `HttpRoute` phải phản ánh target host, port, scheme, proxy/tunnel của request thực tế; không tự đổi khóa route thành service ID logic.

| Tổng pool | Route A | Diễn giải có thể |
|---|---|---|
| `leased=4, max=6` | `leased=4, max=4, pending>0` | Route A đã đầy nhưng pool còn chỗ tổng |
| `leased=6, max=6, pending>0` | `leased=2, max=4` | Tổng pool đang đầy; A còn room riêng nhưng không còn connection tổng |
| `leased=2, available=3, max=6` | `leased=2, max=4` | Có nhiều connection idle, không kết luận nghẽn chỉ từ available |
| `leased=6, pending lớn trong thời gian dài` | Nhiều route pending | Nguy cơ nghẽn pool hoặc backend giữ request quá lâu |

**`pending > 0` là triệu chứng**, chưa đủ để kết luận chỉ cần tăng pool. Cần kiểm tra service latency, thời gian giữ connection, response body chưa được giải phóng, số request đồng thời và số retries.

## 7. Thực hành A — Giới hạn theo một route

Tạo hai instance `catalog-service` trên cùng máy lab với endpoint chậm:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class SlowCatalogController {

    @GetMapping("/lab/slow")
    String slow(
            @RequestParam(defaultValue = "3000") long ms)
            throws InterruptedException {

        Thread.sleep(Math.max(0, Math.min(ms, 5000)));
        return "done";
    }
}
~~~

Server dùng `Thread.sleep` chỉ để mô phỏng việc giữ request trong môi trường test, không phải thiết kế production.

Ban đầu chỉ chạy một instance ở `8081` để mọi request đi cùng route. Client khai báo:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
~~~

### Các bước

1. Giữ `maxConnTotal=6` và `maxConnPerRoute=4`.
2. Gửi **5 request đồng thời** đến `/lab/slow?ms=3000`, cùng HTTP client/connection manager.
3. Khi 4 request đã mượn kết nối, request thứ 5 phải chờ pool vì **route đã đạt giới hạn 4**.
4. Với `connectionRequestTimeout=500ms` và backend giữ request khoảng 3 giây, request chờ có thể timeout trước khi được gửi tới server.
5. Quan sát `getTotalStats()` và thống kê route; tăng riêng `maxConnTotal` lên 10 sẽ không giúp route A vượt mức 4.
6. Chạy lại với `maxConnPerRoute=6` để so sánh; kiểm tra tác động tới response time/CPU của backend.

Các request nên được đồng bộ bằng latch hoặc một công cụ load test để bắt đầu gần nhau và bảo đảm đủ request đang hoạt động. Đừng khẳng định request “thứ 5” theo số thứ tự thread nào sẽ chờ; thread scheduling không quyết định theo trình tự bạn viết.

### Kết quả kỳ vọng

~~~text
Pool config: total=6, perRoute=4
Request group: 5 concurrent, one physical route

Expected while requests are still running:
  route leased <= 4
  total leased <= 6
  at least one acquisition waiting or timing out
  server sees at most 4 concurrent HTTP/1.1 requests from this pool
~~~

Nếu thí nghiệm chạy với HTTP/2 hoặc một proxy có multiplexing, không dùng con số “4 request” như một tính chất phổ quát của mọi protocol. Bài lab giả định Apache HttpClient 5 với kết nối HTTP/1.1 thông thường.

## 8. Thực hành B — Giới hạn tổng giữa hai route

Tiếp tục chạy hai backend:

~~~text
Route A: http://127.0.0.1:8081
Route B: http://127.0.0.1:8082
Pool: total=6, perRoute=4
~~~

Để thí nghiệm **phân biệt rõ nguyên nhân**, dùng bean `directLabRestClient` và URL vật lý thay vì dựa vào round-robin không kiểm soát. Cả hai URL vẫn chia sẻ **một connection manager**.

Ví dụ request:

~~~java
String a = directLabRestClient.get()
        .uri("http://127.0.0.1:8081/lab/slow?ms=3000")
        .retrieve()
        .body(String.class);

String b = directLabRestClient.get()
        .uri("http://127.0.0.1:8082/lab/slow?ms=3000")
        .retrieve()
        .body(String.class);
~~~

Đoạn mã minh họa hai URI riêng, **không phải gọi tuần tự A rồi B** nếu muốn kiểm thử contention; dùng executor/load generator gửi request đồng thời.

### Các bước

1. Cho 4 request đồng thời tới route A.
2. Cho 4 request khác đồng thời tới route B khi nhóm A chưa hoàn tất.
3. Cả hai route đều chưa được vượt `perRoute=4`, nhưng **tổng là 8 yêu cầu**, nhiều hơn `maxConnTotal=6`.
4. Khi 6 connection đang phục vụ, các request còn lại có thể phải chờ mượn pool.
5. Xác minh `getTotalStats().getLeased() <= 6`, cùng `pending` tăng trong thời gian backend còn giữ request.
6. Chạy lại sau khi tăng riêng `maxConnTotal` lên 8. Nếu hai backend đủ năng lực, cả 8 request có thể tiến hành đồng thời.

**Kết quả quan trọng:** route A và route B đều có thể “chưa đầy” theo giới hạn riêng ở một thời điểm, nhưng vẫn có request chờ vì **tổng pool đã đầy**.

Khi chuyển từ test URL vật lý sang `@LoadBalanced RestClient`, cách chọn instance có thể thay đổi phân phối theo round-robin, zone, hint, weight, cache hoặc health filter. Không được suy ra 50/50 nếu không quan sát request thực tế.

## 9. Chọn giới hạn theo tải: cần nhiều hơn một phép nhân

Một ước lượng ban đầu cho HTTP/1.1 là định luật Little:

~~~text
Số request đang đồng thời ≈ request rate × thời gian giữ request
~~~

Ví dụ lưu lượng ổn định 100 request/giây, thời gian giữ connection trung bình 200 ms:

~~~text
100 request/s × 0,2 s ≈ 20 request đồng thời
~~~

Kết quả 20 là **ước lượng trung bình**, không phải khuyến nghị đặt `maxConnTotal=20`. Cần xét:

- Peak RPS và burst traffic, không chỉ trung bình.
- p95/p99 latency, backend có lúc chậm hơn trung bình nhiều lần.
- Số route thực sự hoạt động và phân phối qua mỗi route.
- Retry, hedge requests hoặc proxy có thể tăng số attempt.
- Pool có dùng chung giữa nhiều service ID không.
- Kết nối idle được giữ lại theo timeout/TTL bao lâu.
- CPU, heap, file descriptors, ephemeral ports và connection limits của backend.

Nếu route A thường có 60 request/s và mỗi request chiếm connection khoảng 150 ms, trung bình khoảng 9 request ở A; nhưng một đợt p99 backend tăng lên vài giây có thể khiến hàng chờ tăng rất nhanh. Vì vậy nên chọn giới hạn qua **load test có cấu hình quan sát**, sau đó kiểm tra tác động tới SLO và tải backend.

### Ngưỡng quá lớn cũng gây sự cố

Tăng `maxConnTotal` lên hàng nghìn có thể giảm một số lỗi chờ pool, nhưng đẩy nhiều request tới backend đang quá tải, tăng connection setup, CPU, số file descriptor và chi phí TLS. Pool là một **biện pháp kiểm soát đồng thời**, không chỉ là bộ nhớ để “càng lớn càng tốt”.

Tốt hơn là cân đối pool với timeout, backpressure, rate limiting/bulkhead và capacity của backend.

## 10. WebClient/Reactor Netty: giới hạn thường theo remote host

Với `WebClient` dùng Reactor Netty, đối tượng tương ứng là `ConnectionProvider`. Tuy nhiên, **không được ánh xạ trực tiếp**:

~~~text
Apache maxConnTotal    == Reactor Netty maxConnections
Apache maxConnPerRoute == một API duy nhất cùng ý nghĩa
~~~

Ở Reactor Netty, pool kết nối được tổ chức theo remote host/địa chỉ đích (và thông tin pool/protocol phù hợp). `ConnectionProvider.Builder.maxConnections(n)` là số connection tối đa **cho mỗi connection pool**, thường tương ứng một remote address. Đây **không** phải một global cap đơn giản cho tất cả remote hosts đang dùng provider.

### Ví dụ reactive

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
class PooledWebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider webClientConnectionProvider() {
        return ConnectionProvider.builder("catalog-http")
                .maxConnections(4)
                .pendingAcquireMaxCount(32)
                .pendingAcquireTimeout(Duration.ofMillis(500))
                .maxIdleTime(Duration.ofSeconds(30))
                .metrics(true)
                .build();
    }

    @Bean
    @LoadBalanced
    WebClient.Builder catalogWebClientBuilder(
            ConnectionProvider webClientConnectionProvider) {

        HttpClient httpClient =
                HttpClient.create(webClientConnectionProvider)
                        .option(
                                ChannelOption.CONNECT_TIMEOUT_MILLIS,
                                2000)
                        .responseTimeout(Duration.ofSeconds(6));

        return WebClient.builder()
                .clientConnector(
                        new ReactorClientHttpConnector(httpClient));
    }
}
~~~

Giả sử hai instance có hai remote addresses khác nhau, mỗi pool có giới hạn 4, nên **một `ConnectionProvider` có thể quản lý nhiều hơn 4 connection trên toàn bộ các đích**. Nếu yêu cầu là “toàn ứng dụng tối đa 6 request đang xử lý”, cần giới hạn concurrency ở tầng application/resilience hoặc cơ chế giới hạn riêng, không chỉ dựa vào `maxConnections(4)`.

Bảng đối chiếu:

| Apache HttpClient 5 | Reactor Netty |
|---|---|
| `setMaxConnTotal(6)` — toàn manager | Không có một tùy chọn `maxConnections` tương đương global cap cho mọi host |
| `setMaxConnPerRoute(4)` — mỗi `HttpRoute` | `ConnectionProvider.maxConnections(4)` — giới hạn của từng pool theo remote address |
| `setConnectionRequestTimeout(500ms)` | `pendingAcquireTimeout(500ms)` |
| `PoolStats.getPending()` | Metrics pending/acquired/active của ConnectionProvider |
| Route có thể gồm proxy/tunnel | Pool keyed theo remote address/protocol với ngữ nghĩa Reactor Netty |

Không dùng số liệu hoặc giới hạn trên như thể mọi HTTP/2 stream cần một connection riêng. Các protocol có cơ chế multiplexing làm thay đổi quan hệ request/connection.

### Metrics của Reactor Netty

Khi bật Micrometer cho ConnectionProvider, các metric thường liên quan:

- `reactor.netty.connection.provider.active.connections`
- `reactor.netty.connection.provider.idle.connections`
- `reactor.netty.connection.provider.pending.connections`
- `reactor.netty.connection.provider.max.connections`
- `reactor.netty.connection.provider.pending.connections.time`

Tên/nhãn metric thực tế phụ thuộc phiên bản Reactor Netty và backend metrics. Nên nhóm theo pool ID và remote address khi được hỗ trợ, không chỉ xem tổng số kết nối trong một dashboard.

## 11. OpenFeign: có pool hay không phụ thuộc HTTP transport

Spring Cloud OpenFeign tạo proxy từ interface `@FeignClient`. Khi tích hợp Spring Cloud LoadBalancer, `FeignBlockingLoadBalancerClient` chọn `ServiceInstance`, còn HTTP client delegate thực thi kết nối.

Vì vậy:

- Nếu delegate dùng **Apache HttpClient 5**, connection manager của Apache mới quyết định giới hạn tổng và theo route.
- Nếu delegate dùng transport khác, phải dùng các thuộc tính và semantics của transport đó.
- `@FeignClient(name = "catalog-service")` không tự có nghĩa một pool dành riêng cho service ID đó.
- Các Feign clients có thể chia sẻ hoặc có pool riêng tùy auto-configuration và bean scope.

Thêm dependency `spring-cloud-starter-loadbalancer` giúp Feign chọn instance khi đủ điều kiện, nhưng **không phải cấu hình thay thế cho HTTP connection pool**.

Trong Spring Cloud OpenFeign có những thuộc tính HC5 để điều chỉnh pool ở mức cấu hình auto-managed transport. Ví dụ các tên thuộc tính mà tài liệu hiện hành mô tả:

~~~yaml
spring:
  cloud:
    openfeign:
      httpclient:
        max-connections: 200
        max-connections-per-route: 50
~~~

Các giá trị trên chỉ là minh họa và cần được kiểm tra với **Spring Cloud OpenFeign version và HC5 transport thực tế**. Không tự áp dụng chúng cho `RestClient` hoặc Reactor Netty.

Nếu tự tạo bean `feign.Client`, phải kiểm tra đường đi qua `FeignBlockingLoadBalancerClient` có còn được giữ hay không; thay đổi HTTP transport không nên vô tình bỏ cơ chế chọn instance.

## 12. Phân biệt nghẽn pool, backend chậm và lỗi discovery

| Triệu chứng | Nghi vấn chính | Dữ liệu để chứng minh |
|---|---|---|
| `pending` cao, `leased` bằng max của route | Route-specific saturation | `getStats(route)` + số request tới route |
| `pending` cao, `leased` bằng max tổng | Total pool saturation | `getTotalStats()` + thống kê nhiều route |
| `leased` cao lâu, response time tăng | Backend chậm hoặc connection bị giữ | Backend latency, trace request, body consumption |
| `available` cao nhưng request mới chậm | Route khác đang đầy, connection idle không phù hợp route hoặc transport khác | Thống kê đúng route, pool ID, DNS/TCP/TLS |
| HTTP client thường xuyên tạo socket mới | Không reuse được connection hoặc lifecycle client sai | New connection rate, keep-alive, idle eviction |
| LoadBalancer không tìm thấy instance | Discovery/supplier rỗng | Service ID, candidate list, config health/filter |
| Chọn instance nhưng `Connection refused` | Backend/port hỏng hoặc dữ liệu instance stale | Host/port đã chọn, listener, network |
| HTTP 503 khi pool vẫn rảnh | Backend/proxy hoặc một thành phần khác trả 503 | Trace đích và nội dung response |
| Tăng `maxConnTotal` nhưng lỗi vẫn ở một instance | `maxConnPerRoute` chạm giới hạn hoặc backend yếu | Route stats và server metrics |

**Lỗi chờ pool không phải connect timeout.** Ở bước chờ pool, request có thể chưa được cấp connection để thiết lập TCP. Vì vậy, tăng `connectTimeout` không giúp mượn được slot còn thiếu.

Cần xem cả **client-side metrics** và **backend throughput/latency**. Chỉ tăng giới hạn client mà không kiểm tra backend có thể làm tỉ lệ lỗi tăng lên.

## 13. Idle connections, stale connections và chuyển đổi instance

Kết nối đã sử dụng xong có thể trở lại pool ở trạng thái idle. Khi server/proxy đóng kết nối idle, kết nối ở pool có thể trở nên stale trước lần mượn sau.

Các yếu tố liên quan:

| Cơ chế | Vai trò |
|---|---|
| Keep-alive | Cho phép giữ kết nối và tái sử dụng |
| Max idle time | Đặt ngưỡng đóng kết nối quá lâu không sử dụng |
| Max life time / TTL | Giới hạn tuổi của một connection |
| Validate after inactivity | Giúp nhận diện kết nối rảnh đã không còn hợp lệ trước khi dùng |
| Evict expired/idle | Dọn kết nối hết hạn hoặc đã idle quá ngưỡng |
| Discovery/cache refresh | Loại instance khỏi danh sách lựa chọn; **không trực tiếp đóng socket idle** |

Nếu một instance `catalog-2` dừng:

1. Discovery và LoadBalancer cache có thể cần thời gian mới loại nó khỏi danh sách.
2. Những kết nối idle đến `catalog-2` có thể còn trong pool cho đến khi bị đóng/dọn.
3. Retry trong khoảng thời gian đó có thể tiếp tục chọn instance đã chết, hoặc chọn instance khác tùy chính sách.
4. Tăng `maxConnPerRoute` không khắc phục được endpoint đã dừng.

Một pool đúng cấu hình có thể vẫn gặp lỗi trong lúc scale down. Cần kết hợp graceful shutdown, discovery, health check, timeout, retry có điều kiện và quản lý kết nối idle.

## 14. Ảnh hưởng của HTTP/2, proxy và Kubernetes Service

Các giới hạn connection nên được hiểu theo **transport thực tế**, không chỉ theo kiến trúc dịch vụ logic.

### HTTP/2

Một kết nối HTTP/2 có thể mang nhiều stream đồng thời. Vì vậy, `maxConnections=4` không nhất thiết là tối đa 4 request đồng thời. Server có thể giới hạn số stream trên một connection; transport có cơ chế quản lý stream riêng. Khi đo, cần phân biệt **active TCP connections** và **active HTTP requests/streams**.

### Proxy

Nếu outbound requests đi qua HTTP proxy, `HttpRoute` và cách gom connection có thể chứa thông tin proxy/tunnel. Hai hostname backend khác nhau có thể đi qua cùng proxy nhưng vẫn được quản lý theo những route do transport xác định; không nên dùng chỉ `host:port` in trên log nghiệp vụ làm khóa route tuyệt đối.

### Kubernetes Service / service mesh

Nếu gọi thẳng một Kubernetes Service DNS hoặc sidecar proxy qua **RestClient không dùng Spring Cloud LoadBalancer**, connection pool có thể nhìn thấy route tới **ClusterIP/proxy**, không nhất thiết từng Pod IP. Khi dùng Spring Cloud LoadBalancer và discovery chọn từng Pod/instance vật lý, pool có thể có nhiều route hơn.

Vì vậy, mục tiêu “mỗi instance tối đa 10 connections” phải được kiểm tra theo địa chỉ đích mà HTTP client **thực sự kết nối**, không chỉ từ danh sách Pod hoặc service ID.

## 15. Bài thực hành đo và lựa chọn ngưỡng hợp lý

Thực hiện trong môi trường test, thay đổi **một thông số mỗi lần**:

1. Chạy `/lab/slow` trên một instance, đặt pool tổng 6/per-route 4 và gửi 5 request đồng thời.
2. Đo `leased`, `pending` theo route và response status; ghi số request thực sự tới server.
3. Chỉ tăng tổng từ 6 lên 10; kiểm tra tại sao route vẫn bị giới hạn 4.
4. Đưa per-route lên 6; chạy lại và đo thêm CPU, latency của backend.
5. Chạy hai instance, ép 4 request tới mỗi route dùng **direct client chung pool**; xem tổng 6 là nút nghẽn.
6. Tăng tổng lên 8 để quan sát thay đổi, không đổi per-route.
7. Chuyển sang `@LoadBalanced RestClient` và so sánh khi round-robin/zone/hint làm phân phối request khác đi.
8. Nếu đang dùng WebClient, chạy test riêng với `ConnectionProvider.maxConnections(4)` cho hai remote hosts và quan sát **hai pool**, không báo cáo nhầm là global 4.
9. Thử một backend có latency cao hơn và so sánh: pool có bị bão hòa chỉ vì request giữ connection lâu hơn không?
10. Tổng hợp p50/p95/p99 latency, số request thành công, exception và tài nguyên server trước khi kết luận cần tăng giới hạn nào.

### Mẫu bảng kết quả

| Lần thử | Transport | Route count | Total cap | Per-route cap | Leased tổng | Pending tổng | p95 latency | Kết luận |
|---|---|---:|---:|---:|---:|---|---|---|
| A | Apache HC5 | 1 | 6 | 4 | Tự đo | Tự đo | Tự đo | Per-route bottleneck? |
| B | Apache HC5 | 1 | 10 | 4 | Tự đo | Tự đo | Tự đo | Chỉ tăng total có giúp? |
| C | Apache HC5 | 1 | 6 | 6 | Tự đo | Tự đo | Tự đo | Backend có chịu tải? |
| D | Apache HC5 | 2 | 6 | 4 | Tự đo | Tự đo | Tự đo | Total bottleneck? |
| E | Apache HC5 | 2 | 8 | 4 | Tự đo | Tự đo | Tự đo | So sánh với D |
| F | Reactor Netty | 2 | Không tương đương | 4/pool | Tự đo | Tự đo | Tự đo | Có hai pool remote host? |

Không ghi lại các số liệu minh họa thành kết quả đo thật. Các chỉ số cần được lấy từ pool metrics và công cụ load test tương thích với ứng dụng.

## 16. Checklist trước khi đưa cấu hình vào production

- Một service ID hiện ánh xạ tới bao nhiêu physical routes?
- HTTP transport là Apache HttpClient 5, Reactor Netty hay implementation khác?
- Các client có dùng chung một manager/provider thật sự không, hay mỗi bean tạo pool mới?
- Giới hạn cấu hình là **tổng manager**, **per route**, hay **per remote host pool**?
- Pool có đủ chỗ cho peak load, nhưng không vượt capacity của backend/OS?
- Có `connectionRequestTimeout`/`pendingAcquireTimeout` để request không chờ vô hạn?
- Timeout ở tầng response/read và tổng deadline có phù hợp với tải backend?
- Response body/stream có được giải phóng đúng để trả connection về pool?
- Có metrics `leased/available/pending/max` theo pool/route, và có thể ghép với selected instance?
- Retry có đang tăng số attempt/concurrency và làm hàng chờ pool bùng lên?
- Idle eviction, max life time và graceful shutdown đã phù hợp với vòng đời instance?
- Nếu HTTP/2 hoặc proxy/mesh tham gia, có đang nhầm số request với số TCP connection?
- Đã thử tải với một route nóng và nhiều route để phát hiện cả hai loại nghẽn chưa?

**Kết luận:** `maxConnTotal` của Apache HttpClient 5 giới hạn **toàn bộ connection manager**, còn `maxConnPerRoute` giới hạn **từng HTTP route**; cả hai cùng tác động đến khả năng cấp phát. Với WebClient/Reactor Netty, `maxConnections` thường giới hạn **mỗi remote-host pool**, không phải một global cap tương đương Apache. Vì Spring Cloud LoadBalancer có thể chọn nhiều `ServiceInstance` vật lý từ cùng một service ID, hãy đo pool theo **địa chỉ đích thực**, lựa chọn giới hạn theo peak load/backend capacity và phân biệt rõ lỗi chờ pool với lỗi discovery, connect hoặc response.

**Tài liệu tham khảo chính thức:**

- [Apache HttpClient 5 – PoolingHttpClientConnectionManagerBuilder](https://hc.apache.org/httpcomponents-client-5.6.x/5.6/httpclient5/apidocs/org/apache/hc/client5/http/impl/io/PoolingHttpClientConnectionManagerBuilder.html)
- [Apache HttpClient 5 – PoolingHttpClientConnectionManager](https://hc.apache.org/httpcomponents-client-5.6.x/5.6/httpclient5/apidocs/org/apache/hc/client5/http/impl/io/PoolingHttpClientConnectionManager.html)
- [Reactor Netty – HTTP Client Connection Pool](https://projectreactor.io/docs/netty/release/reference/http-client.html#_connection_pool)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud OpenFeign – Spring Cloud OpenFeign](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)

