# Cấu hình timeout và tái sử dụng kết nối

Khi một microservice gọi microservice khác bằng **Spring Framework `RestClient` kết hợp Spring Cloud LoadBalancer**, có hai vấn đề vận hành cần giải quyết song song: **chọn đúng bản sao `ServiceInstance`** và **thực thi HTTP với giới hạn thời gian, tài nguyên kết nối phù hợp**.

Spring Cloud LoadBalancer giúp chọn đích theo service ID như `catalog-service`. Nó không tự bảo đảm thời gian mở socket, chờ phản hồi hoặc kích thước connection pool. Các hành vi đó thuộc **HTTP request factory và transport** được `RestClient` sử dụng, ví dụ Apache HttpClient 5.

Bài thuộc chương **RestClient** này tập trung vào cách cấu hình timeout, dùng lại kết nối HTTP, tương tác với client-side load balancing và chẩn đoán sự cố khi giao tiếp giữa các dịch vụ.

## 1. Timeout và connection pool nằm ở tầng nào?

Ví dụ mã nghiệp vụ gọi:

~~~http
GET http://catalog-service/products/42
~~~

Giả sử `ServiceInstanceListSupplier` cho `catalog-service` trả hai bản sao:

| Instance | Host | Port |
|---|---|---|
| `catalog-1` | `10.0.1.11` | `8081` |
| `catalog-2` | `10.0.1.12` | `8081` |

Luồng xử lý về mặt khái niệm:

~~~mermaid
flowchart TD
    A["RestClient gọi URL logic<br/>catalog-service/products/42"]
    B["Spring Cloud LoadBalancer<br/>chọn ServiceInstance"]
    C["catalog-1: 10.0.1.11:8081"]
    D["Apache HttpClient 5<br/>connection pool"]
    E{"Có kết nối phù hợp<br/>còn dùng được?"}
    F["Tái sử dụng socket hiện có"]
    G["Mở kết nối mới<br/>DNS/TCP/TLS nếu cần"]
    H["Gửi HTTP request và nhận response"]
    A --> B --> C --> D --> E
    E -->|"Có"| F --> H
    E -->|"Không"| G --> H
~~~

Ranh giới trách nhiệm:

| Thành phần | Công việc chính |
|---|---|
| `ServiceInstanceListSupplier` | Cung cấp danh sách ứng viên từ discovery, cache, health check hoặc chính sách lọc |
| LoadBalancer | Chọn một `ServiceInstance` cho lần gọi |
| LoadBalancer interceptor/adapter | Chuyển URL chứa service ID thành đích vật lý được chọn |
| `RestClient` và `ClientHttpRequestFactory` | Tạo request, chuyển cho HTTP transport và nhận response |
| Apache HttpClient/connection manager | Quản lý socket, connection pool, timeout, keep-alive, TLS và tái sử dụng kết nối |

**Một lần chọn instance không tương đương một lần mở kết nối mới.** Khi LoadBalancer chọn lại đúng endpoint, transport có thể mượn một kết nối HTTP đang rảnh trong pool nếu kết nối đó còn hợp lệ và có thể tái sử dụng.

## 2. Phân biệt các loại timeout

Từ lúc mã gọi `RestClient` đến khi đọc xong phản hồi có nhiều thời gian chờ khác nhau. Không nên dùng từ “timeout” mà không nói rõ giai đoạn.

| Loại giới hạn | Chờ điều gì? | Dấu hiệu khi vượt giới hạn |
|---|---|---|
| **Connection request / pool lease timeout** | Chờ lấy một kết nối từ pool khi các kết nối của route đang bận | Request chưa được cấp kết nối để gửi |
| **Connect timeout** | Thiết lập kết nối TCP mới tới endpoint | Không kết nối được trước thời hạn |
| **Response timeout** | Chờ phản hồi từ server theo ngữ nghĩa transport | Backend/proxy không phản hồi kịp |
| **Socket timeout** | Thời gian chờ hoạt động I/O trên socket | Đọc dữ liệu bị gián đoạn quá lâu |
| **End-to-end deadline** | Tổng thời gian cho toàn bộ thao tác nghiệp vụ, có thể gồm retry | Cần cơ chế giới hạn tổng riêng; không được suy từ một timeout đơn lẻ |

Trong Apache HttpClient 5:

- `RequestConfig#setConnectionRequestTimeout(...)` đặt thời gian tối đa chờ **mượn kết nối từ connection manager**.
- `ConnectionConfig#setConnectTimeout(...)` đặt thời gian **thiết lập kết nối mới**; đây là cách nên dùng trên các phiên bản HttpClient 5 mới thay cho `RequestConfig#setConnectTimeout(...)` đã bị đánh dấu deprecated.
- `RequestConfig#setResponseTimeout(...)` giới hạn thời gian chờ **response**; theo tài liệu Apache, đây **không phải một deadline tuyệt đối** cho toàn bộ lời gọi.
- `ConnectionConfig#setSocketTimeout(...)` đặt timeout mặc định ở tầng socket; response timeout có thể ghi đè giới hạn này trong quá trình thực thi HTTP tùy transport.

Các giá trị không nên hiểu là có thể cộng đơn giản để thành “thời gian tối đa” của một lời gọi. Nếu có redirect, retry, proxy, TLS handshake, xử lý body hoặc nhiều attempt, thời gian thực có thể khác. Cơ chế timeout và khả năng áp dụng còn phụ thuộc HTTP client/version.

### Phân biệt timeout với lỗi không tìm thấy instance

Nếu supplier không cung cấp được bản sao cho `catalog-service`, LoadBalancer có thể trả lỗi “không có server khả dụng” **trước khi HTTP client mở kết nối**. Tăng `connectTimeout` hoặc `responseTimeout` không làm discovery tự tìm ra instance. Ngược lại, khi instance đã chọn có URI hợp lệ nhưng không thể kết nối, đó là sự cố ở bước HTTP transport.

## 3. Tại sao cần tái sử dụng kết nối?

Mở kết nối mới cho mọi request tốn thời gian và tài nguyên: cấp phát socket, bắt tay TCP, TLS nếu là HTTPS, và chi phí xử lý của client/server.

Với HTTP keep-alive, khi kết nối còn hợp lệ, HTTP client có thể tái sử dụng nó cho những request tiếp theo tới route tương ứng. Một pool dùng chung đem lại các lợi ích:

- Giảm số lần mở TCP/TLS mới khi cùng endpoint được gọi nhiều lần.
- Giới hạn số kết nối đồng thời để tránh tăng socket không kiểm soát.
- Giữ lại kết nối rảnh để phục vụ request tiếp theo.
- Cung cấp hàng đợi và timeout khi nhu cầu lớn hơn sức chứa của pool.

Tuy nhiên, tái sử dụng **không phải lúc nào cũng xảy ra**: server có thể gửi `Connection: close`, kết nối idle bị đóng, route thay đổi, kết nối đã hết hạn hoặc đang bận. Không nên xem keep-alive là cam kết rằng mọi lần gọi đều đi qua cùng một socket.

### Pool của HTTP client khác cache của LoadBalancer

| Bộ nhớ/tài nguyên | Lưu cái gì? | Giải quyết vấn đề gì? |
|---|---|---|
| `CachingServiceInstanceListSupplier` | Danh sách `ServiceInstance` theo service ID | Giảm chi phí hỏi discovery |
| Apache HTTP connection pool | Kết nối mạng còn sống và các slot đang được sử dụng | Giảm chi phí tạo socket, kiểm soát đồng thời |
| DNS cache | Kết quả phân giải hostname thành địa chỉ | Giảm chi phí DNS, tùy runtime/resolver |
| HTTP response cache (nếu có) | Nội dung phản hồi | Tránh gọi lại khi phù hợp chính sách cache |

Giảm TTL của LoadBalancer cache không tự làm sạch socket trong HTTP pool; đóng socket rảnh cũng không làm danh sách discovery cập nhật sớm hơn.

## 4. Chọn một HTTP transport có hỗ trợ connection pool

`RestClient` là API HTTP đồng bộ của Spring Framework. Nó sử dụng `ClientHttpRequestFactory` để làm việc với transport thực tế. Các request factory khác nhau hỗ trợ timeout và pooling với mức độ khác nhau.

Đối với hệ thống cần **điều chỉnh rõ số kết nối, thời gian chờ mượn pool, keep-alive và loại bỏ kết nối rảnh**, Apache HttpClient 5 cùng `HttpComponentsClientHttpRequestFactory` là một lựa chọn phổ biến.

Ví dụ dependency Gradle Kotlin DSL, trong dự án đã có Spring Boot/Spring Cloud BOM tương thích:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    implementation("org.apache.httpcomponents.client5:httpclient5")
}
~~~

Cần một nguồn cung cấp `ServiceInstance` như Eureka, Consul hoặc `SimpleDiscoveryClient` để gọi theo service ID. Các ví dụ tiếp theo giả định Spring Framework có `RestClient` (Spring 6.1 trở lên) và Apache HttpClient 5 phiên bản hỗ trợ các API `ConnectionConfig` được sử dụng.

Nếu ứng dụng dùng HTTP transport khác, **không sao chép nguyên cấu hình Apache** sang transport đó: mỗi request factory có API và ngữ nghĩa timeout riêng.

## 5. Cấu hình một Apache HttpClient 5 dùng chung

Mục tiêu của cấu hình minh họa:

- Chờ mượn kết nối từ pool tối đa **1 giây**.
- Thời gian thiết lập TCP connection mới tối đa **2 giây**.
- Response timeout **4 giây**, socket timeout mặc định **5 giây**.
- Giới hạn tối đa **100 kết nối tổng**, trong đó tối đa **20 kết nối mỗi HTTP route**.
- Kiểm tra lại các kết nối đã idle đủ lâu trước khi cấp phát lại.
- Dọn dẹp kết nối hết hạn và kết nối rảnh quá **30 giây**.
- Sử dụng **một `CloseableHttpClient` dùng chung** trong vòng đời application context.

Ví dụ cấu hình:

~~~java
import org.apache.hc.client5.http.config.ConnectionConfig;
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManager;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogRestClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient pooledCatalogHttpClient() {
        ConnectionConfig connectionConfig = ConnectionConfig.custom()
                .setConnectTimeout(Timeout.ofSeconds(2))
                .setSocketTimeout(Timeout.ofSeconds(5))
                .setValidateAfterInactivity(TimeValue.ofSeconds(3))
                .build();

        PoolingHttpClientConnectionManager manager =
                PoolingHttpClientConnectionManagerBuilder.create()
                        .setMaxConnTotal(100)
                        .setMaxConnPerRoute(20)
                        .setDefaultConnectionConfig(connectionConfig)
                        .build();

        RequestConfig requestConfig = RequestConfig.custom()
                .setConnectionRequestTimeout(Timeout.ofSeconds(1))
                .setResponseTimeout(Timeout.ofSeconds(4))
                .build();

        return HttpClients.custom()
                .setConnectionManager(manager)
                .setDefaultRequestConfig(requestConfig)
                .evictExpiredConnections()
                .evictIdleConnections(TimeValue.ofSeconds(30))
                .build();
    }

    @Bean("catalogRestClientBuilder")
    @LoadBalanced
    RestClient.Builder catalogRestClientBuilder(
            CloseableHttpClient pooledCatalogHttpClient) {
        return RestClient.builder()
                .requestFactory(new HttpComponentsClientHttpRequestFactory(
                        pooledCatalogHttpClient));
    }

    @Bean("catalogRestClient")
    RestClient catalogRestClient(
            @Qualifier("catalogRestClientBuilder") RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Đây là **các giá trị minh họa để học cơ chế**, không phải bộ thông số production cho mọi hệ thống. Cần điều chỉnh theo SLO, tải đồng thời, thời gian xử lý backend, số instance và giới hạn tài nguyên mạng.

### Những điểm quan trọng trong cấu hình

**`@LoadBalanced` nằm trên `RestClient.Builder`, không phải trên `CloseableHttpClient`.** Spring Cloud tích hợp lựa chọn instance vào builder; Apache HttpClient nhận đích vật lý và thực thi HTTP. Cơ chế pooling vẫn hoạt động cho các request đã được LoadBalancer chọn.

**Không tạo `CloseableHttpClient` mới mỗi lần gọi.** Bean singleton cho phép các request sử dụng cùng connection manager. Khi application context đóng, Spring gọi `close()` trên bean để giải phóng pool và các thành phần dọn kết nối.

**`setMaxConnPerRoute(20)` thường áp dụng theo HTTP route vật lý**, không phải đúng 20 kết nối cho toàn bộ service ID `catalog-service`. Route còn có thể phụ thuộc proxy và scheme; nhiều instance khác host/port thường có các route khác nhau.

**Không mặc định rằng timeout trên request factory và timeout trên Apache HttpClient cộng dồn.** Cấu hình ở transport cần được xác minh bằng test thời gian chờ thực tế, nhất là khi ứng dụng có retry hoặc network proxy.

### Tích hợp với Spring Boot auto-configuration

Ví dụ tự tạo `RestClient.builder()` ở trên ưu tiên minh họa Apache request factory. Nếu dự án phụ thuộc những customizer tự động của Spring Boot (như observability, codec/message converter hoặc các interceptor khác), cần đảm bảo chúng vẫn được áp dụng cho builder load-balanced. Tài liệu Spring Cloud đề xuất dùng `RestClientBuilderConfigurer` khi tạo `@LoadBalanced RestClient.Builder` để tận dụng các cấu hình có sẵn của Spring Boot.

Không nên thay thế builder đã được Boot customizer xử lý mà không kiểm tra tác động đến metrics, tracing, authentication hoặc serialization.

## 6. Gọi bằng service ID nhưng kết nối được tái sử dụng theo endpoint

Sử dụng bean `catalogRestClient`:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class CatalogGateway {

    private final RestClient client;

    CatalogGateway(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    Product getProduct(long id) {
        return client.get()
                .uri("/products/{id}", id)
                .retrieve()
                .body(Product.class);
    }
}

record Product(long id, String name) {}
~~~

Ở mỗi lần gọi:

1. `RestClient` nhận URL logic theo `baseUrl("http://catalog-service")`.
2. Spring Cloud LoadBalancer chọn một instance hiện có của `catalog-service`.
3. HTTP request được gửi đến đích vật lý bằng Apache HttpClient.
4. Connection manager tìm kết nối rảnh hợp lệ cho route đó; nếu không có, nó có thể tạo kết nối mới nếu chưa chạm giới hạn.
5. Sau khi xử lý response đúng cách, kết nối có thể quay lại pool để tái sử dụng.

Ví dụ với round-robin, kết nối có thể được giữ riêng cho các route:

~~~text
Service ID: catalog-service

LoadBalancer chọn catalog-1 (10.0.1.11:8081)
  -> Pool route 10.0.1.11:8081
     available: 2, leased: 1

LoadBalancer chọn catalog-2 (10.0.1.12:8081)
  -> Pool route 10.0.1.12:8081
     available: 1, leased: 1
~~~

Các con số là minh họa, không phải kết quả do framework tự tạo. Điều đáng chú ý là **LoadBalancer quyết định instance**, còn **pool quyết định dùng socket nào** đối với route đã được chọn.

### Vì sao pool không “cân bằng tải” thay LoadBalancer?

Apache connection manager không biết toàn bộ danh sách `ServiceInstance` của `catalog-service` để áp dụng round-robin, zone preference hoặc hint. Nó quản lý kết nối theo route HTTP đã xác định. Nếu LoadBalancer liên tục chọn một instance, pool có thể tái sử dụng socket đến instance đó, nhưng không tự đổi đích sang instance khác chỉ vì route hiện tại đang chậm.

## 7. Pool sizing: tổng kết nối và kết nối mỗi route

Giả sử `catalog-service` có bốn instance và tải tăng đến 100 request HTTP đồng thời.

- `maxConnTotal=100`: giới hạn tổng số kết nối được pool quản lý.
- `maxConnPerRoute=20`: giới hạn số kết nối cho mỗi route; dù pool còn dung lượng tổng, một route riêng có thể đã chạm 20.
- `connectionRequestTimeout=1s`: một request chờ mượn connection có thể thất bại nếu không có slot sẵn sàng trước thời hạn.

Vì một service ID có thể ánh xạ tới nhiều route vật lý, giới hạn 20/route **không đồng nghĩa** 20 request đồng thời cho cả service. Ngược lại, nếu nhiều request được LoadBalancer chọn vào một instance, route đó có thể bị nghẽn dù các route khác còn chỗ.

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Chờ mượn kết nối, timeout dù server khỏe | Pool bị chiếm hết hoặc per-route limit quá nhỏ | Đo leased/pending/available và mức đồng thời trên route |
| Tăng pool lớn nhưng backend chậm hơn | Backend không xử lý thêm được hoặc đang quá tải | Kiểm tra CPU, DB pool, concurrency và SLO backend |
| Nhiều kết nối idle sau scale-out | Traffic phân tán qua nhiều route | Giới hạn idle/TTL, cân nhắc cấu hình pool phù hợp |
| Thường xuyên mở kết nối mới | Server đóng keep-alive, idle eviction quá ngắn hoặc client/pool bị tạo lại | Kiểm tra server headers, lifecycle và connection reuse |
| Chỉ một số instance chạm giới hạn | Thuật toán/supplier tạo phân phối không đều | Kiểm tra zone, weight, hint và per-route metrics |

Không nên tăng pool vô hạn. Mỗi kết nối tiêu thụ file descriptor, bộ nhớ, cổng mạng và tài nguyên backend; đồng thời không phải mọi request blocking đều có thể xử lý nhanh nếu thread pool của ứng dụng đã bão hòa.

## 8. Keep-alive, idle eviction và kết nối stale

Kết nối vừa phục vụ request có thể được tái sử dụng nếu HTTP protocol, server và client cho phép. Tuy nhiên, trong môi trường microservices, instance có thể bị thay thế, load balancer hạ tầng có thể đóng kết nối rảnh, hoặc mạng có thể làm đứt một kết nối đã tồn tại.

Ba cơ chế hay dùng:

| Cơ chế | Mục đích |
|---|---|
| **Keep-alive** | Cho phép dùng lại kết nối phù hợp sau request |
| **Evict expired/idle connections** | Đóng kết nối hết hạn hoặc đã rảnh quá lâu |
| **Validate after inactivity** | Kiểm tra khả năng tái sử dụng của kết nối đã không hoạt động một khoảng thời gian |

Trong đoạn cấu hình mục 5, `evictIdleConnections(TimeValue.ofSeconds(30))` giúp dọn các kết nối rảnh trên 30 giây, còn `setValidateAfterInactivity(3s)` hỗ trợ đánh giá lại những kết nối đã không hoạt động đủ lâu trước khi cho mượn. Đây là những biện pháp hạn chế lỗi socket stale, **không thể bảo đảm loại bỏ toàn bộ race condition**: một kết nối có thể bị đóng ngay sau khi được kiểm tra.

### Khác biệt giữa instance stale và socket stale

- **Instance stale:** supplier của LoadBalancer vẫn trả một `ServiceInstance` đã ngừng hoạt động. Cần xem discovery, cache hoặc health check.
- **Socket stale:** instance được chọn có thể vẫn hợp lệ, nhưng một kết nối rảnh trong pool tới nó đã bị server/proxy đóng. Cần xem connection manager, idle validation và networking.
- **Kết hợp cả hai:** instance đã ngừng hoạt động và pool vẫn có socket cũ. Retry/timeout và làm mới discovery có thể cùng cần thiết, nhưng xử lý tại các tầng khác nhau.

Một request tới socket stale có thể gặp lỗi sớm rồi cần kết nối mới; có nên thử lại không phụ thuộc chính sách retry của transport và integration. Với thao tác ghi dữ liệu, tránh retry thiếu kiểm soát vì request có thể đã đến server trước khi kết nối hỏng.

### Phải xử lý response và body đúng cách

Kết nối chỉ có cơ hội được trả về pool khi response được xử lý và tài nguyên cần thiết được giải phóng. Các lời gọi như `retrieve().body(Product.class)` thường tiêu thụ body và đóng tài nguyên theo cơ chế của Spring.

Với streaming hoặc callback xử lý trực tiếp response, phải tuân thủ vòng đời response của API để tránh giữ connection đang leased vô thời hạn. Không giữ tham chiếu tới body stream đã đóng hoặc bỏ qua các cơ chế đóng được framework cung cấp.

## 9. Không nhầm timeout với một deadline tổng

Giả sử cấu hình:

~~~text
pool lease timeout : 1s
connect timeout    : 2s
response timeout   : 4s
socket timeout     : 5s
~~~

Đây là **các giới hạn cho từng giai đoạn**, không phải lời hứa “mỗi request hoàn tất trong 4 giây” hoặc “tối đa đúng 1 + 2 + 4 giây”.

Một số lý do thời gian toàn bộ request có thể vượt kỳ vọng:

1. Request phải chờ connection trong pool rồi mới bước sang connect hoặc gửi request.
2. TLS, DNS, proxy, redirect và đọc response body có ngữ nghĩa timeout phụ thuộc transport.
3. Một số HTTP client tự retry trong các điều kiện được cấu hình.
4. Spring Cloud LoadBalancer hoặc tầng application có thể retry thêm với một lựa chọn instance mới.
5. Backend trả response header kịp thời nhưng body được truyền chậm.

**Response timeout của Apache HttpClient không phải deadline tổng của tất cả attempts.** Nếu yêu cầu nghiệp vụ có ngân sách thời gian tuyệt đối (ví dụ 2 giây cho việc lấy giá), cần thiết kế time budget/deadline ở tầng cao hơn, cân nhắc cả retry và thời gian chờ queue, đồng thời chọn cách hủy/giới hạn tương thích với client đồng bộ.

### Retry nhân số lần chờ

Ví dụ một request ban đầu gặp response timeout 4 giây, sau đó retry thêm hai lần. Tổng thời gian của thao tác có thể cao hơn nhiều so với 4 giây, chưa kể backoff, kết nối hoặc thời gian chờ mượn pool.

Điều này đặc biệt nguy hiểm nếu client có **nhiều tầng retry**: HTTP transport tự retry, LoadBalancer retry, và ứng dụng lại dùng Resilience4j hoặc một vòng lặp retry khác. Cần rà soát và giới hạn tổng số attempts, phân loại exception được phép retry và khả năng idempotent của endpoint.

Một POST tạo đơn hàng có thể đã được server xử lý trước khi client bị timeout; gửi lại không có idempotency key hoặc xử lý chống trùng có thể tạo hai đơn.

## 10. Chẩn đoán lỗi theo giai đoạn

Khi thấy `RestClient` timeout, thứ tự kiểm tra hiệu quả là xác định **đã chọn được instance hay chưa**, sau đó xác định đang chờ **pool, connect hay response**.

| Tín hiệu quan sát | Giai đoạn nghi vấn | Hành động nên làm |
|---|---|---|
| Không có instance cho service ID | Discovery/LoadBalancer | Kiểm tra service ID, registry, supplier, health filtering |
| Pool pending cao và leased sát giới hạn | Mượn connection | Kiểm tra `maxConnPerRoute`, `maxConnTotal`, request concurrency, response chưa đóng |
| Connect timeout tới một instance cụ thể | Tạo kết nối | Kiểm tra host/port, firewall, server listener, network reachability |
| `Connection refused` | Kết nối bị từ chối | Kiểm tra instance đã dừng, cổng chưa mở hoặc discovery stale |
| Response timeout dù connect nhanh | Backend/proxy phản hồi chậm | Kiểm tra server latency, thread/DB pool, downstream dependency |
| Lỗi sau thời gian idle dài | Kết nối trong pool đã stale | Kiểm tra keep-alive, idle eviction, validate-after-inactivity |
| Timeout tăng sau khi bật retry | Nhiều attempts và backoff | Đo số lần retry và ngân sách thời gian thực |
| Instance được chọn thay đổi nhưng pool chậm | Nhiều physical routes hoặc route nóng | Đo pool theo route, phân phối load balancing |

Lỗi transport thường được Spring bọc thành exception như `ResourceAccessException`, nhưng loại exception lồng bên trong khác nhau theo request factory. Không nên dựa vào một tên exception duy nhất để kết luận đó là connect, lease hay response timeout.

Một HTTP 503 cũng không luôn là lỗi timeout: nó có thể do LoadBalancer không tìm thấy instance hoặc do backend/proxy thực sự trả về `503 Service Unavailable`.

## 11. Quan sát hai hệ thống: LoadBalancer và HTTP pool

Một request lỗi có thể có quyết định chọn instance đúng nhưng bị nghẽn kết nối. Vì vậy, log/traces nên phân biệt:

**Phía chọn đích:** service ID, instance ID, host/port, số ứng viên và chính sách routing nếu có thể quan sát.

**Phía HTTP:** route vật lý, thời gian chờ mượn connection, thời gian mở kết nối, thời gian nhận response, HTTP status/exception, số attempts và số connection `leased/pending/available` nếu HTTP client expose được metrics.

Ví dụ định dạng log tùy biến:

~~~text
traceId=abc123 serviceId=catalog-service selected=catalog-2
route=10.0.1.12:8081 poolPending=0 poolLeased=8
attempt=1 httpStatus=200 durationMs=53
~~~

Đây là **định dạng gợi ý**, không phải các field tự động tồn tại trong Spring Cloud LoadBalancer/Apache HttpClient. Nếu dùng Spring Boot observability, cần bảo đảm `RestClient.Builder` được áp dụng các customizer phù hợp; nếu muốn pool metrics chi tiết, có thể cần tự instrument connection manager hoặc tích hợp thư viện metrics tương ứng.

Không ghi token, cookie, thông tin xác thực hoặc toàn bộ request body có dữ liệu nhạy cảm chỉ để đo timeout.

## 12. Thử nghiệm tái hiện lỗi timeout và kiểm tra tái sử dụng

Có thể thực hành mà không cần service registry riêng. Chạy hai instance `catalog-service` trên máy thử nghiệm và khai báo trong `SimpleDiscoveryClient`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
              - uri: http://127.0.0.1:8082
~~~

Giả sử mỗi instance có các endpoint:

- `GET /whoami` trả về instance ID.
- `GET /slow?ms=5000` mô phỏng chậm trả phản hồi trong 5 giây.
- `GET /ping` trả nhanh một body nhỏ để đo kết nối.

Đây là **endpoint giả định cần tự triển khai trong ứng dụng thử nghiệm**, không phải endpoint có sẵn của Spring Cloud.

### Bài thực hành A — Kiểm tra lựa chọn instance và pooling

1. Khởi tạo một `RestClient` bean từ builder ở mục 5 và **tái sử dụng cùng bean** cho nhiều request.
2. Gọi `/whoami` nhiều lần để xác nhận LoadBalancer chọn các instance mà discovery cung cấp.
3. Dùng logging hoặc metrics ở Apache HttpClient để quan sát request tới từng route, số connection được mở, leased và available.
4. So sánh số kết nối mới được tạo với tổng số request. Khi keep-alive và pool hoạt động, số lần mở kết nối có thể thấp hơn số request.
5. Tắt tính năng keep-alive ở server thử nghiệm hoặc giảm thời gian idle, rồi so sánh.

**Không kết luận connection reuse chỉ từ việc cùng instance trả response.** Muốn chứng minh, phải quan sát connection manager, network trace hoặc thông tin socket/connection ID phù hợp.

### Bài thực hành B — Response timeout

1. Giữ response timeout 4 giây trong Apache HttpClient.
2. Gọi `/slow?ms=5000`, xác nhận client báo timeout theo transport và cấu hình thực tế.
3. Đổi backend để phản hồi nhanh hơn và chạy lại.
4. Nếu bật retry, ghi số attempts và tổng thời gian thay vì chỉ đọc response timeout.

Kết quả còn phụ thuộc endpoint chậm ở giai đoạn gửi headers, body hay ở middleware/proxy.

### Bài thực hành C — Pool lease timeout

1. Trong một lần chạy riêng, đặt `maxConnPerRoute=2` và `connectionRequestTimeout=1s`.
2. Gửi nhiều lời gọi blocking đồng thời đến cùng một route, ví dụ tạm dùng một instance để tránh LoadBalancer phân tán tải.
3. Cho backend giữ request khoảng vài giây để các connection đang leased không được trả về ngay.
4. Quan sát các request vượt quá hai connection phải chờ pool và một số có thể hết hạn chờ mượn.
5. Tăng per-route limit trong một lần đo khác để so sánh, đồng thời quan sát tác động tới backend.

Không dùng thử nghiệm ép tải này trên môi trường production.

### Bài thực hành D — Kết nối idle và instance bị thay thế

1. Gửi request để pool có kết nối rảnh.
2. Đợi server đóng idle connection hoặc dừng một instance.
3. Gửi request tiếp theo, quan sát lỗi/việc mở lại kết nối.
4. Phân biệt trường hợp **instance đã dừng nhưng vẫn được discovery chọn** với trường hợp **instance còn sống nhưng kết nối idle trong pool đã bị đóng**.
5. Điều chỉnh idle eviction/validate-after-inactivity rồi so sánh, không mặc định nó giải quyết stale discovery.

## 13. Checklist cấu hình trước khi đưa vào vận hành

- `@LoadBalanced RestClient.Builder` đã được cấu hình đúng và URL logic dùng service ID hợp lệ chưa?
- Có đang dùng một `CloseableHttpClient`/connection manager dùng chung thay vì tạo mới mỗi request không?
- `connectionRequestTimeout`, `connectTimeout` và `responseTimeout` đã được kiểm thử độc lập chưa?
- `maxConnTotal` và `maxConnPerRoute` có phù hợp số instance, phân phối tải và khả năng backend không?
- Response body hoặc stream có được giải phóng để trả connection về pool không?
- Idle eviction và validate-after-inactivity đã phù hợp thời gian server/proxy giữ kết nối chưa?
- Khi instance scale down, có phân biệt cache `ServiceInstance` stale và socket pool stale không?
- Retry có thể nhân số lần chờ hay gây gọi trùng thao tác ghi dữ liệu không?
- Tracing/metrics của Spring Boot và HTTP pool có còn hoạt động sau khi tự tạo `RestClient.Builder` không?
- Có kiểm thử timeout với proxy, TLS, backend chậm và nhiều request đồng thời trên phiên bản thư viện thực tế không?

**Kết luận:** Spring Cloud LoadBalancer xác định **bản sao nào sẽ được gọi**; `RestClient` cùng request factory/HTTP transport quyết định **kết nối được mở, tái sử dụng và chờ trong bao lâu**. Cấu hình timeout theo từng giai đoạn, quản lý pool dùng chung và quan sát cả hai tầng giúp giảm độ trễ, kiểm soát tài nguyên và phân biệt đúng lỗi discovery với lỗi mạng.

**Tài liệu tham khảo:**

- [Spring Cloud Commons – RestClient as a LoadBalancer Client](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html#spring-restclient-as-a-loadbalancer-client)
- [Spring Framework – HttpComponentsClientHttpRequestFactory](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/client/HttpComponentsClientHttpRequestFactory.html)
- [Apache HttpClient 5 – RequestConfig.Builder](https://hc.apache.org/httpcomponents-client-5.6.x/current/httpclient5/apidocs/org/apache/hc/client5/http/config/RequestConfig.Builder.html)

