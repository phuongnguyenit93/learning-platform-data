# Tái sử dụng HTTP client và tránh tạo kết nối cho từng yêu cầu

Trong hệ thống microservices, `order-service` có thể gọi `catalog-service` hàng trăm hoặc hàng nghìn lần mỗi giây. Nếu mỗi lần gọi đều xây mới một HTTP client cùng các tài nguyên transport riêng, hoặc đóng kết nối ngay sau mỗi request, ứng dụng dễ phải trả chi phí **TCP/TLS handshake, cấp phát socket, quản lý thread/bộ nhớ và chờ connection pool** nhiều hơn cần thiết. Tải tăng còn có thể khiến cạn file descriptor, phát sinh nhiều socket ở trạng thái `TIME_WAIT` hoặc tăng độ trễ phần đuôi.

Bài thuộc chương **Kết nối và hiệu năng** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Trọng tâm là **tái sử dụng HTTP client và connection pool** khi gọi theo service ID qua **Spring Cloud LoadBalancer**, đồng thời hiểu vai trò của discovery, health check, chính sách định tuyến, timeout/retry và quan sát lỗi. Các ví dụ bao gồm `RestClient` đồng bộ, `WebClient` reactive và `OpenFeign` declarative.

> **Nguyên tắc:** tạo và cấu hình client ở cấp ứng dụng hoặc một phạm vi sống đủ dài; dùng lại client cho nhiều request. Tuy nhiên, *reuse đối tượng client* và *reuse kết nối TCP* không phải cùng một khái niệm: kết nối chỉ có thể tái sử dụng nếu HTTP transport, server, proxy và chính sách pool cho phép.

## 1. Bốn thành phần khác nhau: service ID, client, pool và socket

Khi gọi `http://catalog-service/api/items/42`, có ít nhất bốn mức cần phân biệt:

1. **Service ID:** `catalog-service` là tên logic mà Spring Cloud LoadBalancer dùng để tìm danh sách `ServiceInstance`.
2. **HTTP client:** đối tượng `RestClient`, `WebClient` hoặc proxy Feign giữ cấu hình request và sử dụng HTTP transport.
3. **Connection manager/pool:** nơi quản lý các kết nối vật lý hoặc logical HTTP streams có thể tái sử dụng, tùy client và giao thức.
4. **TCP/TLS connection:** đường truyền thực sự tới một endpoint cụ thể, có thể được giữ lại cho request kế tiếp hoặc bị đóng.

~~~mermaid
flowchart TD
    A["order-service"] --> R["RestClient / WebClient / Feign proxy (reuse)"]
    R --> LB["Spring Cloud LoadBalancer"]
    DISC["Discovery + supplier + health/filter"] --> LB
    LB --> X{"Chọn ServiceInstance"}
    X --> B["catalog-a :18081"]
    X --> C["catalog-b :18082"]
    R --> P["HTTP transport + connection pool"]
    P -. "Kết nối đang có tới A" .-> B
    P -. "Kết nối đang có tới B" .-> C
~~~

**LoadBalancer lựa chọn đích cho HTTP request; connection pool quản lý kết nối tới đích đã chọn.** Một pool không thay thế discovery, và một danh sách instance được cache không đồng nghĩa socket tới từng instance đã được mở sẵn.

### Ví dụ vòng đời

~~~text
Request #1: service ID -> chọn A -> chưa có socket -> TCP/TLS connect -> HTTP GET
Request #2: service ID -> chọn B -> chưa có socket B -> TCP/TLS connect -> HTTP GET
Request #3: service ID -> chọn A -> có socket A còn dùng được -> tái sử dụng
Request #4: service ID -> chọn B -> socket B bị server đóng -> mở socket mới
~~~

Ví dụ mô tả một tình huống có thể xảy ra; không cam kết Round Robin luôn tạo đúng thứ tự trên. Việc tái sử dụng socket phụ thuộc transport thực tế và trạng thái kết nối tại thời điểm request.

## 2. Vì sao tạo client và connection mới cho từng request gây tốn kém?

Một kết nối HTTP mới có thể phải thực hiện:

- Phân giải địa chỉ đích ở tầng transport theo cấu hình, định tuyến mạng và chọn địa chỉ phù hợp.
- TCP three-way handshake; nếu dùng HTTPS, thực hiện TLS handshake phù hợp.
- Khởi tạo hoặc cấp phát socket, buffer và các cấu trúc quản lý kết nối.
- Thiết lập trạng thái kết nối, kiểm tra chứng chỉ, trao đổi HTTP headers.
- Đóng socket và chịu chi phí dọn dẹp; ở một số trường hợp xuất hiện nhiều kết nối `TIME_WAIT`.

Các khoản này làm tăng **latency per request**, CPU mạng/crypto, số kết nối đồng thời và áp lực tài nguyên. Tạo một HTTP client mới cũng có thể tạo request factory, connection manager hoặc event-loop resources mới tùy cách cấu hình.

Tuy nhiên, cần tránh khẳng định “mỗi lần `new RestClient` chắc chắn tạo một TCP connection”. **Tạo client object và mở socket là hai thao tác khác nhau**; một số triển khai có thể chia sẻ transport mặc định hoặc mở kết nối lazy. Vấn đề là tạo client/transport/pool không cần thiết làm mất cơ hội reuse có kiểm soát và khiến vòng đời tài nguyên khó quản lý.

### Nhận biết anti-pattern

~~~java
// Không nên tạo client mới mỗi khi một nghiệp vụ cần gọi HTTP.
ItemDto findItem(String id) {
    RestClient client = RestClient.create();

    return client.get()
        .uri("http://catalog-service/api/items/{id}", id)
        .retrieve()
        .body(ItemDto.class);
}
~~~

Ngoài chi phí tạo client, ví dụ này còn có một lỗi riêng: `RestClient.create()` không tự nhận cấu hình `@LoadBalanced` của Spring, nên host `catalog-service` có thể bị đưa qua DNS thông thường thay vì discovery của Spring Cloud LoadBalancer.

Với WebClient, việc gọi `WebClient.create(...)` trong mỗi handler cũng khiến chính sách client và connector khó nhất quán. Với Feign, tự xây một Feign proxy mỗi request thay vì inject bean do Spring quản lý là một anti-pattern tương tự.

## 3. HTTP/1.1 keep-alive và HTTP/2 multiplexing

**HTTP/1.1:** trong điều kiện hỗ trợ persistent connection, nhiều request nối tiếp có thể đi qua cùng TCP connection. Một connection HTTP/1.1 thường không thực thi đồng thời nhiều response theo cách multiplex như HTTP/2; để xử lý nhiều request đồng thời, transport có thể cần nhiều connections trong pool.

**HTTP/2:** nhiều HTTP streams có thể cùng tồn tại trên một TCP/TLS connection khi client, server và hạ tầng trung gian đã thương lượng HTTP/2. Điều này giảm nhu cầu mở TCP connection mới trong nhiều trường hợp, nhưng vẫn có các giới hạn concurrent streams, flow control và tài nguyên server.

| Khía cạnh | HTTP/1.1 persistent | HTTP/2 |
|---|---|---|
| Tái sử dụng TCP | Có, khi giữ kết nối mở | Có |
| Request đồng thời trên cùng connection | Thường không multiplex theo cách HTTP/2 | Nhiều logical streams có thể multiplex |
| Cách giới hạn concurrency | Số connection và hàng đợi pool | Số connection, streams và flow control |
| Có phải luôn được dùng? | Phụ thuộc transport/server | Phải được hỗ trợ và thương lượng thực tế |
| Có loại bỏ nhu cầu quản lý pool? | Không | Không |

Dù client là singleton, server/proxy có thể đóng idle connection sau timeout hoặc gửi `Connection: close` trong HTTP/1.1. Client có thể phải mở kết nối khác ở request sau. **Không đặt mục tiêu “không bao giờ mở connection mới”; mục tiêu là tái sử dụng hợp lý và dọn connection đúng vòng đời.**

## 4. LoadBalancer vẫn chọn instance trên mỗi HTTP request

Spring Cloud LoadBalancer có thể chọn `catalog-a` cho request thứ nhất và `catalog-b` cho request thứ hai. Khi transport có socket đang mở tới A, nó chỉ có thể dùng lại socket đó cho request phù hợp với **đích vật lý, scheme, bảo mật và các quy tắc phân vùng connection của transport**.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Caller
    participant LB as Spring Cloud LoadBalancer
    participant Pool as HTTP connection pool
    participant A as catalog-a
    participant B as catalog-b

    C->>LB: Request 1 tới catalog-service
    LB-->>C: Chọn A
    C->>Pool: Xin kết nối tới A
    Pool->>A: Mở TCP/TLS nếu chưa có
    A-->>C: Response 200
    Note over Pool: Giữ connection A nếu có thể tái sử dụng

    C->>LB: Request 2 tới catalog-service
    LB-->>C: Chọn B
    C->>Pool: Xin kết nối tới B
    Pool->>B: Mở TCP/TLS nếu chưa có
    B-->>C: Response 200

    C->>LB: Request 3 tới catalog-service
    LB-->>C: Chọn A
    C->>Pool: Xin kết nối tới A
    Pool-->>C: Reuse connection A nếu còn hợp lệ
    C->>A: GET qua kết nối A
    A-->>C: Response 200
~~~

**Một client dùng chung không buộc mọi request đi vào cùng một instance.** Ngược lại, connection pool không phải sticky-session policy: nó chỉ tái sử dụng kết nối nếu instance vừa được chọn có endpoint phù hợp với connection sẵn có.

Đây cũng là lý do việc đổi thuật toán chọn instance, lọc theo zone hoặc cập nhật health check vẫn có tác dụng khi client được tái sử dụng. Những thay đổi đó thường ảnh hưởng **request mới**, không bắt buộc chuyển hướng một request hoặc stream đang chạy.

## 5. Thiết kế vòng đời HTTP client ở Spring

Trong Spring, cách phổ biến là **khai báo client hoặc proxy thành bean** và inject vào service nghiệp vụ:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder catalogLoadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient catalogRestClient(
            @Qualifier("catalogLoadBalancedBuilder")
            RestClient.Builder builder) {

        return builder
            .baseUrl("http://catalog-service")
            .build();
    }
}
~~~

Sau đó sử dụng lại:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

record ItemDto(String id, String name, int stock) {}

@Service
class CatalogGateway {

    private final RestClient catalogRestClient;

    CatalogGateway(RestClient catalogRestClient) {
        this.catalogRestClient = catalogRestClient;
    }

    ItemDto getItem(String id) {
        return catalogRestClient.get()
            .uri("/api/items/{id}", id)
            .retrieve()
            .body(ItemDto.class);
    }
}
~~~

Với Spring singleton bean như trên, nhiều lần gọi `getItem` dùng **cùng đối tượng RestClient đã được cấu hình**. Các request spec tạo ra từ client là đối tượng riêng của từng lời gọi; không lưu một request spec mutable để dùng chung giữa các thread.

### Phân biệt client và builder

- **RestClient/WebClient đã build** thường được dùng an toàn từ nhiều luồng khi cấu hình không bị sửa, và được thiết kế để tái sử dụng.
- **Builder** là đối tượng cấu hình có thể thay đổi. Không để nhiều thread cùng sửa một builder rồi build client mỗi request.
- Nếu cần nhiều client cho nhiều downstream, có thể tạo các client bean riêng từ builder được clone hoặc các builder có cấu hình tách biệt.
- Không giữ request/response body stream sau khi kết thúc lifecycle của request; phải đóng/consume theo contract của HTTP stack.

Với ứng dụng Spring MVC hoặc tác vụ nền, inject `CatalogGateway` hoặc `RestClient` làm dependency dài hạn. Với WebFlux, inject một `WebClient` cấu hình sẵn thay vì tạo client bên trong mỗi chuỗi `flatMap`.

## 6. Reuse RestClient chưa đủ nếu transport không có pool phù hợp

`RestClient` là facade cho thao tác HTTP đồng bộ; khả năng pooling phụ thuộc vào `ClientHttpRequestFactory` và HTTP transport. Nếu muốn kiểm soát pool rõ ràng trong ứng dụng dùng Apache HttpComponents 5, có thể cung cấp `HttpComponentsClientHttpRequestFactory`.

**Dependencies (Gradle, với Spring Boot/Spring Cloud BOM tương thích):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
    implementation 'org.apache.httpcomponents.client5:httpclient5'
}
~~~

**Ví dụ cấu hình pool Apache HttpClient 5:**

~~~java
import org.apache.hc.client5.http.config.RequestConfig;
import org.apache.hc.client5.http.impl.classic.CloseableHttpClient;
import org.apache.hc.client5.http.impl.classic.HttpClients;
import org.apache.hc.client5.http.impl.io.PoolingHttpClientConnectionManagerBuilder;
import org.apache.hc.core5.util.TimeValue;
import org.apache.hc.core5.util.Timeout;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.HttpComponentsClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class PooledCatalogRestClientConfiguration {

    @Bean(destroyMethod = "close")
    CloseableHttpClient pooledApacheHttpClient() {

        var manager = PoolingHttpClientConnectionManagerBuilder.create()
            .setMaxConnTotal(200)
            .setMaxConnPerRoute(50)
            .build();

        RequestConfig requestConfig = RequestConfig.custom()
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
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder(
            CloseableHttpClient pooledApacheHttpClient) {

        var factory = new HttpComponentsClientHttpRequestFactory(
            pooledApacheHttpClient);

        factory.setConnectTimeout(2000);
        factory.setConnectionRequestTimeout(1000);

        return RestClient.builder().requestFactory(factory);
    }

    @Bean
    RestClient catalogRestClient(
        @Qualifier("loadBalancedRestClientBuilder") RestClient.Builder builder
    ) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Các đoạn bean ở phần 5 và 6 là **hai cách cấu hình thay thế**; không đăng ký cả hai cùng tên nếu Spring context chỉ cần một `catalogRestClient`.

Ý nghĩa cấu hình:

| Thành phần | Giá trị ví dụ | Mục đích |
|---|---:|---|
| `maxConnTotal` | 200 | Giới hạn tổng connection do Apache connection manager quản lý |
| `maxConnPerRoute` | 50 | Giới hạn connection theo route vật lý tương ứng |
| `connectionRequestTimeout` | 1 giây | Giới hạn chờ lấy connection từ pool |
| `connectTimeout` | 2 giây | Giới hạn thiết lập kết nối theo transport/factory |
| `responseTimeout` | 3 giây | Giới hạn chờ response theo Apache transport |
| `evictIdleConnections` | 30 giây | Dọn kết nối idle theo chính sách |
| `destroyMethod="close"` | Khi Spring context đóng | Giải phóng transport và kết nối |

**Các con số là cấu hình thí nghiệm, không phải khuyến nghị mặc định production.** API timeout hoặc chính sách Apache HC5 có thể khác theo minor version của Spring Framework/HttpComponents; kiểm tra dependency đang dùng trước khi áp dụng nguyên mã.

### Vì sao phải giới hạn cả total và per-route?

Spring Cloud LoadBalancer có thể chọn nhiều instance, mỗi instance là một đích vật lý. Với Apache HttpClient, `maxConnTotal` giới hạn tổng connection do manager quản lý; `maxConnPerRoute` giới hạn theo route. Nếu có 10 instance và mỗi instance đang nhận 50 connections, bạn không thể suy rằng tổng hệ thống được phép 500 connections khi `maxConnTotal` chỉ bằng 200.

Ngược lại, một instance đang quá tải có thể làm cạn giới hạn per-route của nó, trong khi tổng pool vẫn chưa đầy. Hai metric cần được đọc khác nhau.

## 7. Reuse WebClient và Reactor Netty connection pool

`WebClient` cung cấp API reactive, có thể sử dụng Reactor Netty làm HTTP connector. Trong ứng dụng Spring WebFlux, `WebClient` đã cấu hình là đối tượng nên được **dùng lại**, không tạo một WebClient/HttpClient/ConnectionProvider mới cho từng event.

**Dependencies (Gradle):**

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Ví dụ **tùy chỉnh ConnectionProvider** để quản lý pooled connections:

~~~java
import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;
import reactor.netty.resources.ConnectionProvider;

@Configuration(proxyBeanMethods = false)
class PooledCatalogWebClientConfiguration {

    @Bean(destroyMethod = "dispose")
    ConnectionProvider catalogConnectionProvider() {
        return ConnectionProvider.builder("catalog-pool")
            .maxConnections(100)
            .pendingAcquireMaxCount(200)
            .pendingAcquireTimeout(Duration.ofSeconds(1))
            .maxIdleTime(Duration.ofSeconds(30))
            .maxLifeTime(Duration.ofMinutes(5))
            .evictInBackground(Duration.ofSeconds(30))
            .build();
    }

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder(
            ConnectionProvider catalogConnectionProvider) {

        HttpClient client = HttpClient.create(catalogConnectionProvider)
            .responseTimeout(Duration.ofSeconds(3));

        return WebClient.builder()
            .clientConnector(new ReactorClientHttpConnector(client));
    }

    @Bean
    WebClient catalogWebClient(
        @Qualifier("loadBalancedWebClientBuilder") WebClient.Builder builder
    ) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Các giá trị trên nhằm cho thấy cách cấu hình, không phải thông số bắt buộc. Reactor Netty quản lý pool theo các remote endpoints/connection keys; `maxConnections` thường áp dụng cho một pool được phân vùng, **không tự tương đương giới hạn tổng TCP connections của toàn ứng dụng**. Phải theo dõi số pool/địa chỉ đích thực tế khi có nhiều `ServiceInstance`.

`pendingAcquireMaxCount` giới hạn hàng đợi chờ lấy connection; `pendingAcquireTimeout` giới hạn thời gian chờ. `maxIdleTime` và `maxLifeTime` giúp tránh giữ socket quá lâu. Không dùng các giới hạn này thay thế timeout nghiệp vụ hoặc backpressure/concurrency control.

**Quan trọng về vòng đời:** vì ConnectionProvider được tạo riêng cho cấu hình này, Spring cần giải phóng nó khi context đóng. Trong ứng dụng sử dụng Reactor Netty resources toàn cục hoặc Spring Boot auto-configuration khác, việc dùng chung và quản lý lifecycle có thể khác; không đóng một provider chung đang phục vụ các client khác vào giữa thời gian hoạt động.

### Ví dụ dùng WebClient trong service reactive

~~~java
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
class ReactiveCatalogGateway {

    private final WebClient catalogWebClient;

    ReactiveCatalogGateway(WebClient catalogWebClient) {
        this.catalogWebClient = catalogWebClient;
    }

    Mono<ItemDto> getItem(String id) {
        return catalogWebClient.get()
            .uri("/api/items/{id}", id)
            .retrieve()
            .bodyToMono(ItemDto.class);
    }
}
~~~

Mỗi subscription vào `getItem` có thể tạo một HTTP request mới, nhưng cùng dùng **WebClient, connector và pool đã cấu hình**. Tránh gọi `block()` trong WebFlux event-loop; nếu nhiều request cần xử lý song song, giới hạn concurrency để không dồn toàn bộ vào pool.

## 8. OpenFeign: tái sử dụng proxy và HTTP transport

Với Spring Cloud OpenFeign, cách phổ biến là inject bean `@FeignClient` được Spring tạo ra, không tạo proxy Feign mới trong mỗi method:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping("/api/items/{id}")
    ItemDto getItem(@PathVariable("id") String id);
}
~~~

Sau khi đã bật `@EnableFeignClients` và cấu hình dependency tương thích:

~~~java
import org.springframework.stereotype.Service;

@Service
class CatalogUseCase {

    private final CatalogFeignClient catalog;

    CatalogUseCase(CatalogFeignClient catalog) {
        this.catalog = catalog;
    }

    ItemDto getItem(String id) {
        return catalog.getItem(id);
    }
}
~~~

Feign proxy được quản lý bởi Spring, còn **khả năng tái sử dụng connection** phụ thuộc HTTP client implementation nằm dưới Feign. Với Apache HttpClient 5 hoặc OkHttp được cấu hình đúng, connection pooling thường được hỗ trợ; nhưng không được suy rằng chỉ thêm `@FeignClient` là chắc chắn đang dùng một transport cụ thể.

Ví dụ cấu hình một số thuộc tính OpenFeign phổ biến, cần đối chiếu với release train:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            connectTimeout: 2000
            readTimeout: 3000
      httpclient:
        max-connections: 200
        max-connections-per-route: 50
~~~

Đây là cấu hình theo **tên client** và các thuộc tính của HTTP client integration; nó chỉ điều chỉnh kết nối theo đúng nghĩa khi implementation tương ứng được nạp và sử dụng. Muốn dùng HC5, phải đảm bảo dependency Apache HC5 và cấu hình bật transport phù hợp phiên bản, đồng thời xác minh bean/metrics thực tế. Nếu chọn OkHttp, thuộc tính và cách cấu hình pool cũng khác.

**Feign thường hoạt động theo mô hình blocking** trong Spring Cloud OpenFeign. Nó không tự trở thành reactive client chỉ vì backend hỗ trợ HTTP/2 hoặc connection pooling.

## 9. Không nhầm ba loại cache/pool

Các thành phần sau thường cùng xuất hiện, nhưng phục vụ mục tiêu khác nhau:

| Thành phần | Lưu gì? | Có làm gì? |
|---|---|---|
| `CachingServiceInstanceListSupplier` | Danh sách instance theo service ID | Giảm truy vấn discovery, có nguy cơ stale list |
| HTTP connection pool | Kết nối đến host/port/route đã chọn | Giảm số TCP/TLS handshake không cần thiết |
| Application response cache | DTO/HTTP response/dữ liệu nghiệp vụ | Giảm số HTTP request thực sự phải gửi |

Caching instance list **không giữ socket**; connection pool **không cache JSON response**; response cache **không quyết định LoadBalancer chọn instance nào**. Tuning TTL của một loại không tự giải quyết sự cố của loại còn lại.

### Ví dụ số liệu

Giả sử 10.000 request gọi `catalog-service` trong một khoảng đo:

- Instance list cache có thể giảm số lần hỏi discovery xuống một lượng rất nhỏ.
- HTTP connection pool có thể tái sử dụng một nhóm connections tới A/B thay vì bắt tay TCP/TLS cho mỗi request.
- Response cache (nếu có theo contract) có thể làm giảm số request thực sự cần gọi đến catalog.

Ba thay đổi khác nhau. Khi đo performance, phải xác định mục tiêu: **độ trễ tìm instance, số connection mới hay số request tới backend**.

## 10. Sizing pool từ concurrency và latency

Một cách ước lượng ban đầu là quan hệ Little trong trạng thái ổn định:

~~~text
Số request đang xử lý trung bình ≈ thông lượng (request/giây)
                                  × thời gian xử lý trung bình (giây)
~~~

Ví dụ caller gửi **200 request/giây** đến một downstream, thời gian phục vụ trung bình **100 ms**:

~~~text
200 req/s × 0,1 s = 20 request đang chạy trung bình
~~~

Nếu một request HTTP/1.1 giữ một connection active, mức trung bình khoảng 20 connections đang hoạt động là điểm tham chiếu, **không phải cấu hình max=20 tối ưu**. Burst traffic, p95/p99, chờ DB, retry và số request song song có thể đòi khoảng trống đáng kể.

Nếu độ trễ tăng lên 500 ms nhưng thông lượng vẫn 200 request/giây:

~~~text
200 req/s × 0,5 s = 100 request đang chạy trung bình
~~~

Connection pool có thể bắt đầu bị chặn hoặc pending tăng lên. Trong trường hợp này, chỉ tăng `maxConnections` có thể khiến downstream chịu nhiều concurrent requests hơn và **làm tình trạng quá tải nặng hơn**.

### Một service có nhiều instance

Nếu `catalog-service` có A nhanh 50 ms và B chậm 500 ms, cùng nhận 100 request/giây:

| Instance | Request/giây được giao | Mean latency | In-flight trung bình xấp xỉ |
|---|---:|---:|---:|
| A | 50 | 50 ms | 2,5 |
| B | 50 | 500 ms | 25 |

Dù LoadBalancer phân phối đều số request, B chiếm nhiều tài nguyên connection hơn. Nếu pool có giới hạn per-route riêng, B có thể có pending acquire lớn hơn A.

**Đừng biến connection pool thành giải pháp che giấu sự chậm trễ của server.** Cần tìm nguyên nhân latency, saturation và kiến trúc retry trước khi tăng bừa giới hạn.

## 11. Pool exhaustion: khi tài nguyên bị giữ quá lâu

Một request có thể phải chờ lấy connection nếu toàn bộ pool cho route đã đầy hoặc các connections đang bận phục vụ request khác.

~~~mermaid
flowchart TD
    A["Request cần gửi tới catalog-b"] --> B{"Có connection hợp lệ và rảnh?"}
    B -->|Có| C["Lease/reuse connection"]
    B -->|Không| D{"Có thể tạo connection mới theo giới hạn?"}
    D -->|Có| E["Mở TCP/TLS connection"]
    D -->|Không| F["Chờ trong pending-acquire queue"]
    F --> G{"Có slot trước timeout?"}
    G -->|Có| C
    G -->|Không| H["Pool acquire timeout / từ chối chờ"]
    C --> I["Thực hiện HTTP request"]
    E --> I
    I --> J["Consume/close response -> trả tài nguyên về pool"]
~~~

Khi số connection bận hoặc hàng đợi chờ tăng, cần xem:

- **Ứng dụng tạo nhiều requests đồng thời** hơn dự kiến không?
- **Downstream xử lý chậm**, khiến connection bị giữ lâu?
- **Response body được tiêu thụ và đóng đúng** hay còn stream bị treo?
- **Timeout đọc response** có quá dài, giữ socket sau khi người dùng đã bỏ cuộc?
- Có **retry storm** làm tăng số attempts?
- Có nhiều **service instances/physical routes** làm phân mảnh pool?
- Có **long-lived streaming** dùng chung pool với request ngắn?

Pool exhaustion và “server không có instance” là hai lỗi khác nhau. Với pool exhaustion, LoadBalancer có thể đã chọn được một instance; HTTP transport chỉ không lấy được connection kịp thời.

## 12. Quản lý response body để trả kết nối về pool

Để một HTTP connection có cơ hội được tái sử dụng, HTTP transport cần biết response đã được đọc đến mức thích hợp hoặc đã được đóng/hủy đúng cách.

**Với RestClient:**

~~~java
ItemDto item = catalogRestClient.get()
    .uri("/api/items/{id}", id)
    .retrieve()
    .body(ItemDto.class);
~~~

Đây là đường đi phổ biến: converter tiêu thụ body và RestClient/transport quản lý response lifecycle. Nếu dùng `exchange(...)` để truy cập response thấp hơn, không giữ `ClientHttpResponse`/input stream bên ngoài callback một cách tùy tiện. Đọc body lớn vào RAM bằng `readAllBytes()` cũng có chi phí riêng.

**Với WebClient:**

~~~java
Mono<ItemDto> item = catalogWebClient.get()
    .uri("/api/items/{id}", id)
    .retrieve()
    .bodyToMono(ItemDto.class);
~~~

Publisher sẽ thực hiện I/O theo subscription, và lifecycle phải được quản lý để body được đọc hoặc subscription bị cancel khi không còn cần thiết. Không tạo `Mono` rồi tự gọi `subscribe()` trong service nếu bạn không quản lý `Disposable` và việc hủy.

**Với SSE/streaming dài:** response có thể tiếp tục mãi, nên một HTTP connection hoặc logical HTTP stream có thể được giữ trong thời gian dài. Không thể giả định “đọc event đầu tiên” là đủ để trả connection về pool. Phải có timeout/heartbeat, cancellation và quota dành riêng cho streaming.

### Lỗi phổ biến

~~~java
// Không nên trong một pipeline WebFlux:
catalogWebClient.get()
    .uri("/api/events")
    .retrieve()
    .bodyToFlux(String.class)
    .collectList()
    .block();
~~~

Nếu `/api/events` là stream không kết thúc, `collectList()` sẽ chờ mãi và có thể tích lũy dữ liệu vô hạn; `block()` còn chiếm thread. Đây không phải lỗi “pool quá nhỏ”, mà là vấn đề vòng đời và cách consume response.

## 13. Chọn timeout theo lớp, không nhầm với pool size

Mỗi giới hạn xử lý một giai đoạn khác nhau:

| Giới hạn | Áp dụng cho | Khi vượt |
|---|---|---|
| Pool acquire timeout | Chờ lấy connection từ pool | Chưa gửi HTTP request tới backend |
| Connect timeout | Thiết lập kết nối | Không có TCP connection kịp hạn |
| TLS handshake timeout | Đàm phán bảo mật | Không hoàn tất TLS |
| Response/read timeout | Chờ/đọc response theo transport | Có thể request đã được xử lý bên đích |
| End-to-end deadline | Tổng thao tác nghiệp vụ | Caller không muốn chờ thêm |
| Idle connection lifetime | Kết nối rảnh trong pool | Kết nối có thể bị dọn |
| Maximum connection lifetime | Tổng tuổi kết nối | Transport có thể thay bằng connection mới |

**Tăng pool size không sửa read timeout. Giảm connect timeout không giải quyết pending acquire.** Cần đo được thời gian chờ ở từng giai đoạn.

Với lời gọi có tác dụng phụ như POST tạo đơn, response timeout không có nghĩa server chắc chắn chưa commit. Nếu retry, sử dụng idempotency key bền vững qua nhiều attempts và tra cứu trạng thái khi kết quả không xác định.

## 14. Instance chết, stale idle connection và thay đổi topology

Trong môi trường autoscaling hoặc rolling deployment, một instance đang có connection trong pool có thể ngừng phục vụ:

~~~mermaid
sequenceDiagram
    participant D as Discovery
    participant LB as LoadBalancer
    participant P as Connection pool
    participant A as catalog-a
    participant B as catalog-b

    D-->>LB: [A, B]
    LB->>P: Request tới B
    P->>B: Mở connection tới B
    B-->>P: Response
    Note over P: Connection B idle trong pool
    Note over B: B dừng hoặc proxy đóng idle socket
    D-->>LB: [A]
    LB->>P: Request mới tới A
    P->>A: Dùng/mở connection A
    Note over P: B có thể còn entry idle tới khi eviction/validation
~~~

Khi discovery/supplier cập nhật để không chọn B nữa, **các request mới** có thể tránh B. Connection cũ tới B có thể bị dọn theo chính sách pool, nhưng LoadBalancer không tự “xóa socket” chỉ vì service list đổi.

Ngược lại, nếu cache discovery/health vẫn coi B là ứng viên, LoadBalancer có thể chọn B và pool thử dùng socket đã bị server đóng; request có thể gặp reset/refused/timeout. Cần kết hợp **discovery cập nhật, health check, TTL/eviction của pool, timeout và retry an toàn**.

### Không phải mọi lỗi reuse đều là lỗi LoadBalancer

- `Connection reset by peer` có thể đến từ backend/proxy đóng socket đã idle.
- `Pool acquire timeout` có thể do caller bão hòa concurrency.
- `No servers available`/không chọn được instance thường liên quan tập ứng viên của discovery/supplier.
- `Read timeout` có thể do request đã tới server nhưng xử lý chậm.
- HTTP `503` từ backend/gateway có response, khác lỗi kết nối trước khi có HTTP response.

Phân loại đúng lỗi giúp chọn giải pháp đúng: chỉnh pool, chỉnh timeout, sửa discovery hoặc giảm tải downstream thay vì chỉ tăng retries.

## 15. HTTP client reuse và long-lived connections

Khi gọi SSE, gRPC streaming hoặc HTTP response lớn, thời gian giữ connection khác hẳn một GET JSON ngắn. Với HTTP/1.1, một SSE response có thể giữ một TCP connection bận trong suốt luồng. Với HTTP/2, một TCP connection có thể chứa nhiều logical streams, nhưng concurrency và flow control vẫn có giới hạn.

Một ứng dụng có 500 subscriber SSE không thể được đánh giá bằng cùng chỉ số “requests/giây” như 500 GET ngắn. Nên cân nhắc:

- Pool/connector và quota dành riêng cho streaming nếu tải lớn.
- Giới hạn số active subscribers và thời gian không có heartbeat.
- Cancellation khi client ngắt kết nối để giải phóng upstream.
- Không dùng response timeout dành cho REST JSON ngắn cho một luồng cố ý im lặng lâu.
- Giám sát active connections, active streams và memory buffers.

**Reuse không phải giữ mọi connection sống vô hạn.** Với long-lived stream, giữ connection là một phần hợp đồng truyền dữ liệu; với request ngắn, tái sử dụng idle connection có thể giúp giảm latency.

## 16. OpenFeign, RestClient và WebClient: chọn theo mô hình ứng dụng

| Tiêu chí | RestClient | WebClient | OpenFeign |
|---|---|---|---|
| API | Fluent, đồng bộ | Fluent, reactive | Interface declarative |
| Đối tượng nên reuse | `RestClient` và transport | `WebClient`, connector/provider | Feign proxy và HTTP transport |
| Pooling phụ thuộc | `ClientHttpRequestFactory` | Client connector (ví dụ Reactor Netty) | Feign HTTP client (HC5/OkHttp...) |
| LoadBalancer theo service ID | Builder `@LoadBalanced` | Builder `@LoadBalanced` | Feign integration với LoadBalancer |
| Quản lý request | Thread blocking | Subscription, demand, cancellation | Thường blocking |
| Lỗi nếu tạo per-request | Mất cấu hình, khó reuse pool | Tạo connector/pool thừa, khó dọn | Tạo proxy/transport thừa |
| Cần theo dõi | leased/pending per-route, timeout | active/pending connections, event-loop | HTTP transport metrics, Feign status |
| Phù hợp | Spring MVC, request-response | WebFlux, streaming | Dự án dùng nhiều declarative clients |

Không có kết luận rằng WebClient luôn nhanh hơn RestClient hoặc OpenFeign trong mọi tình huống. Hiệu năng thực tế còn phụ thuộc transport, contention, serialization, server, CPU, connection pool, mức concurrency và cách viết business code. Đội nên đo theo SLO và workload thực.

## 17. Quan sát: xác minh client đang tái sử dụng kết nối

Tạo bean singleton mới là **điều kiện thiết kế**, nhưng chưa chứng minh transport thực sự reuse socket. Muốn biết, cần metric/log ở tầng HTTP transport và hệ điều hành.

| Tín hiệu | Giúp trả lời |
|---|---|
| Connections created/opened/closed | Mỗi request có phải mở socket mới không? |
| Active / idle / leased connections | Pool có tái sử dụng hợp lý hay bị giữ quá lâu? |
| Pending acquire count/time | Caller đang chờ vì pool hết chỗ? |
| Connection lifetime / idle age | Có socket idle quá lâu, stale hoặc churn? |
| Connect/TLS handshake latency | Bao nhiêu chi phí mở kết nối mới? |
| HTTP request rate và p50/p95/p99 | Latency có cải thiện sau pooling? |
| Error by cause | Refused, reset, timeout, HTTP 5xx khác nhau thế nào? |
| Service ID và selected instance | Lưu lượng phân phối thực tế ra sao? |
| Retry attempts | Có tăng tải vì retry storm không? |
| Backend active connections | Pool của client có vượt khả năng server không? |

Với Reactor Netty, có thể bật metrics phù hợp cho `ConnectionProvider` và HTTP client theo cấu hình. Với Apache HC5, dùng pool stats/JMX hoặc instrumentation tương thích. Không giả định Spring Cloud LoadBalancer tự phát ra đầy đủ mọi metric connection; nó chủ yếu ở phía **chọn instance**, không kiểm soát mọi socket của transport.

### Đừng dựa duy nhất vào TIME_WAIT

Nhiều socket `TIME_WAIT` có thể chỉ ra churn connections, nhưng cũng có thể xuất hiện bình thường trong lưu lượng mạng và chính sách đóng socket của hệ thống. Cần đối chiếu số new connections/giây, mức tải thực, port exhaustion, errors và TLS handshakes. Không khắc phục bằng thay đổi sysctl hoặc giảm TIME_WAIT một cách tùy tiện.

Nếu cần log connection reuse trong môi trường kiểm thử, sử dụng logging/debug của HTTP client đã chọn với mức phù hợp. **Không bật wire logging chứa Authorization, Cookie hoặc payload nhạy cảm trên production**.

## 18. Bài thực hành: cùng client, hai ServiceInstance, nhiều request

Mục tiêu lab là chứng minh:

1. Reuse cùng HTTP client/proxy không làm mất cơ chế chọn instance theo service ID.
2. Transport có thể reuse connections tới từng instance khi response được đọc và socket còn hợp lệ.
3. Khi pool chật hoặc backend chậm, pending acquire và p99 latency tăng; tăng pool mù quáng không phải giải pháp chắc chắn.

### A. Chuẩn bị hai backend cục bộ

Cùng một Spring MVC application chạy với các cổng và instance ID khác nhau:

~~~java
import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogController {

    private final String instanceId;

    CatalogController(Environment environment) {
        this.instanceId = environment.getProperty(
            "instance.id", "catalog-unknown");
    }

    @GetMapping("/api/items/{id}")
    Map<String, Object> item(@PathVariable String id) {
        return Map.of(
            "id", id,
            "name", "Notebook",
            "instanceId", instanceId
        );
    }
}
~~~

Để tự chạy, ứng dụng backend phải có `@SpringBootApplication` và dependency Spring Web; giả sử được build thành `catalog-service.jar`:

~~~bash
java -jar catalog-service.jar --server.port=18081 --instance.id=catalog-a
java -jar catalog-service.jar --server.port=18082 --instance.id=catalog-b
~~~

### B. Cấu hình discovery tĩnh ở caller

Để không cần một registry riêng trong lab, `SimpleDiscoveryClient` lấy danh sách instance từ cấu hình tĩnh dưới đây:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

Tạo caller từ **một trong các cấu hình bean RestClient ở trên**, rồi gọi từ một service nghiệp vụ. Với body demo trả `Map`, ví dụ gọi:

~~~java
import java.util.Map;

import org.springframework.web.client.RestClient;

class CatalogLoadTestGateway {

    private final RestClient client;

    CatalogLoadTestGateway(RestClient catalogRestClient) {
        this.client = catalogRestClient;
    }

    Map<?, ?> fetch(String id) {
        return client.get()
            .uri("/api/items/{id}", id)
            .retrieve()
            .body(Map.class);
    }
}
~~~

Chạy nhiều lời gọi **trong cùng một tiến trình caller**. Nếu tạo một chương trình test tuần tự:

~~~java
for (int i = 0; i < 100; i++) {
    Map<?, ?> item = gateway.fetch(Integer.toString(i));
    System.out.println(item.get("instanceId"));
}
~~~

Kỳ vọng quan sát cả `catalog-a` và `catalog-b` nếu Round Robin và danh sách instance ổn định; pool có cơ hội reuse connections tới hai đích khi transport hỗ trợ.

### C. So sánh có kiểm soát

Chạy ít nhất hai cấu hình trên cùng workload:

| Kịch bản | Phân phối request | New connections/s | Pool pending | p95/p99 | Điều cần kết luận |
|---|---|---|---|---|---|
| RestClient singleton + pool | Ghi A/B | Đo | Đo | Đo | Reuse tốt tới đâu? |
| Pool nhỏ, concurrency cao | Ghi A/B | Đo | Có tăng? | Có tăng? | Điểm bão hòa ở đâu? |
| Backend B chậm | Ghi A/B | Đo | B có cao? | B có cao? | Pool chật do latency hay max size? |
| Server đóng idle sockets nhanh | Ghi A/B | Có tăng? | Đo | Đo | Có stale connection/reconnect? |
| Dừng instance B | Chọn theo supplier | Reset/refused? | Đo | Đo | Discovery/health và pool tương tác ra sao? |

Dùng warm-up, giữ payload và mức concurrency tương đồng. Không đo performance chỉ bằng một vài request đầu vì chi phí khởi tạo JVM, JIT, TLS, DNS và pool warm-up có thể gây sai lệch.

**Không nên viết một benchmark “tạo pool mới mỗi request” trên production**: nó có thể gây leak hoặc quá tải hạ tầng. Nếu cần kiểm chứng anti-pattern trong lab, phải tạo và đóng transport đúng vòng đời, giới hạn lưu lượng và dùng môi trường thử tách biệt.

### D. Tăng concurrency một cách có kiểm soát

Nếu dùng WebClient trong WebFlux, có thể giới hạn số request đồng thời bằng `flatMap(..., concurrency)`:

~~~java
import java.util.Map;
import reactor.core.publisher.Flux;

Flux<Map> results = Flux.range(0, 100)
    .flatMap(
        i -> catalogWebClient.get()
            .uri("/api/items/{id}", i)
            .retrieve()
            .bodyToMono(Map.class),
        16
    );
~~~

Đây là pipeline minh họa có concurrency tối đa 16 ở operator `flatMap`; nó không trực tiếp quy định pool size. `results` phải được subscribe bởi test/framework để thực sự gửi HTTP requests. Tránh `blockLast()` trên reactive event-loop, và đừng bật concurrency hàng nghìn nếu backend/pool chưa được chuẩn bị.

## 19. Những lỗi cấu hình thường gặp

1. **Tạo RestClient/WebClient trong từng handler:** bỏ lỡ khả năng reuse cấu hình và có nguy cơ tạo transport resources thừa.
2. **Dùng client không `@LoadBalanced`:** gọi service ID như DNS bình thường, dù discovery đã có instance.
3. **Chỉ tạo singleton client nhưng không xem HTTP transport:** cho rằng pooling chắc chắn có cấu hình đúng mà không kiểm tra.
4. **Tăng `maxConnections` bất chấp p99 backend đang cao:** có thể đẩy thêm concurrency vào server quá tải.
5. **Nhầm per-route với total:** cấu hình giới hạn 50/route không có nghĩa toàn hệ thống tối đa 50.
6. **Không giới hạn pending queue:** request có thể xếp hàng quá lâu, vượt deadline nghiệp vụ.
7. **Không consume/close response đúng:** connection không quay về pool khi cần.
8. **Chia sẻ mutable request builder giữa các thread:** gây race ở header, URI và body.
9. **Giữ streaming response vô hạn mà không cancel:** chiếm connection/stream và memory.
10. **Dùng pool lifetime quá dài khi server/proxy đóng idle socket sớm:** làm tăng xác suất dùng connection stale, dù transport có thể kiểm tra trước khi dùng.
11. **Dùng timeout ngắn mà retry không giới hạn:** gây connection churn và retry storm.
12. **Đồng nhất instance list cache với connection pool:** sửa TTL discovery để xử lý pool acquire timeout.
13. **Quên dọn custom pool khi shutdown:** background resource có thể tồn tại quá vòng đời mong muốn.
14. **Cấu hình Feign transport không khớp classpath:** thuộc tính pool được khai báo nhưng implementation không sử dụng.
15. **Đo bằng request count duy nhất:** bỏ qua connect/handshake, active connections, pool pending và latency đuôi.
16. **Mặc định HTTP/2 luôn được bật:** phụ thuộc connector, TLS/ALPN, server và proxy.

## 20. Checklist vận hành và kết luận

Trước khi triển khai, xác minh:

- HTTP client/proxy được **inject và reuse** đúng vòng đời ứng dụng, không xây lại trong mỗi request.
- `@LoadBalanced` và service ID được cấu hình đúng cho RestClient/WebClient; Feign có integration tương ứng.
- Đã xác định chính xác **HTTP transport** nằm dưới client, không dựa vào giả định.
- Pool có giới hạn tổng/per-route hoặc remote endpoint thích hợp và có chính sách dọn idle/lifetime.
- Connect, pool acquire, response/read timeout và deadline nghiệp vụ được phân biệt rõ.
- Response body được consume/cancel đúng; streaming có giới hạn riêng.
- Có metric active/idle/pending connections, tạo mới/đóng connection, latency và error cause.
- LoadBalancer/discovery/health có thể đổi instance mà không nhầm với quản lý socket.
- Retry có giới hạn và không gây side effect trùng khi response timeout.
- Đã kiểm thử thay đổi topology, một instance chậm, server đóng idle socket và concurrency tăng.
- Cấu hình được đo theo SLO thực tế, không sao chép nguyên số max connections hoặc timeout từ ví dụ.

**Kết luận:** **tái sử dụng HTTP client** là một nguyên tắc kiến trúc giúp quản lý cấu hình và lifecycle nhất quán; **connection pooling/keep-alive** mới là cơ chế cho phép nhiều HTTP requests tận dụng lại kết nối vật lý khi có thể. Trong Spring Cloud LoadBalancer, bộ chọn vẫn có thể chọn `ServiceInstance` theo từng request qua discovery và health supplier; pool sẽ tìm/mở kết nối tới endpoint đã chọn. Muốn giao tiếp RestClient, WebClient và OpenFeign ổn định, hãy kết hợp **client reuse, pool sizing, lifecycle cleanup, timeout/retry có ngân sách và quan sát kết nối thực tế**, thay vì chỉ tạo thêm nhiều client hoặc tăng giới hạn pool khi phát hiện latency cao.

