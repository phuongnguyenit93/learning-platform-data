# Cold start, khởi tạo client và làm nóng kết nối

Khi một dịch vụ Spring Boot mới được khởi động, request đầu tiên đến một downstream đôi khi chậm hơn các request kế tiếp. Ví dụ Order Service gọi **http://inventory-service/api/stock/BOOK-01** lần đầu mất 800 ms, nhưng các lần tiếp theo chỉ khoảng 30–50 ms. Nếu chỉ nhìn thuật toán Round Robin, rất dễ kết luận sai rằng **Spring Cloud LoadBalancer chọn chậm**. Trên thực tế, request đầu có thể đang gánh nhiều công việc chưa từng xảy ra: khởi tạo bean và child context, tải danh sách ServiceInstance, tạo tài nguyên HTTP client, DNS lookup, mở TCP connection, TLS handshake và nạp class/JIT.

Trong bài này, **cold start** là chi phí phát sinh khi một tiến trình, một service ID, một HTTP client hoặc một kết nối được dùng lần đầu sau giai đoạn chưa hoạt động. **Warm-up** là chủ động thực hiện một số phần của quá trình khởi tạo *trước khi có traffic quan trọng*, còn **connection reuse** là sử dụng lại kết nối đã tồn tại. Ba khái niệm này có liên quan nhưng không đồng nghĩa.

Mục tiêu là hiểu đúng điểm khởi đầu của độ trễ, cấu hình làm nóng có chủ đích cho **RestClient, RestTemplate, WebClient và OpenFeign**, kết hợp với **ServiceInstanceListSupplier**, discovery, health check, timeout và retry, rồi kiểm chứng bằng số liệu thực tế. Bài không giả định một lệnh warm-up có thể bảo đảm mọi request kế tiếp đều nhanh.

## 1. Có nhiều loại “cold” cùng xuất hiện trong một request

| Tầng | Điều gì có thể xảy ra lần đầu? | Có còn cold ở request sau không? |
| --- | --- | --- |
| **JVM / Spring Boot** | Nạp class, tạo bean, chạy auto-configuration, tạo mapper/converter, JIT | Có thể tiếp tục nóng dần sau nhiều request |
| **Spring Cloud LoadBalancer** | Tạo child ApplicationContext cho service ID; tạo supplier và thuật toán chọn | Context thường được tái sử dụng trong tiến trình |
| **Discovery / supplier** | Gọi registry, nhận snapshot đầu, dựng cache/health publisher | Có thể tái diễn khi TTL hết hoặc registry thay đổi |
| **HTTP client resources** | Tạo event loop, resolver, thread, native transport/SSL libraries | Thường tái sử dụng nếu giữ cùng client/resources |
| **DNS** | Phân giải hostname của ServiceInstance đã chọn | Có thể tái diễn do DNS TTL, instance mới hoặc resolver mới |
| **TCP / TLS** | Mở connection mới, handshake TLS, thiết lập HTTP/2 | Tái diễn khi pool rỗng, connection hết hạn hoặc origin mới |
| **Application protocol** | Khởi tạo serializer/deserializer, xác thực, tải schema, cache ứng dụng | Phụ thuộc client, endpoint và thư viện |
| **Runtime pressure** | GC, CPU contention, pool acquisition, autoscaling, backend cold | Có thể gây chậm ngay cả ở tiến trình đã “warm” |

Một phương án warm-up chỉ nhắm tới **một hoặc vài tầng** trong bảng. Ví dụ, khởi tạo sớm LoadBalancer context không tự tạo TCP connection; làm nóng Reactor Netty không tự gọi API Inventory; gọi một endpoint Inventory cũng không bảo đảm đã khởi tạo trước tất cả bản sao trong registry.

### 1.1. Dòng thời gian minh họa

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Order Service
    participant LB as Spring Cloud LoadBalancer
    participant D as Discovery/Supplier
    participant H as HTTP Client
    participant I as Inventory Instance B
    O->>LB: GET http://inventory-service/...
    Note over LB: Child context có thể được tạo lần đầu
    LB->>D: Lấy danh sách ServiceInstance
    D-->>LB: [A, B]
    LB-->>O: Chọn B
    O->>H: Request đến host:port của B
    Note over H: Pool/Resolver/Native resources
    H->>H: DNS + TCP + TLS nếu cần
    H->>I: HTTP request
    I-->>H: HTTP response
    H-->>O: DTO / response
~~~

Các bước chỉ là **mô hình logic**: LoadBalancer thường nằm trong interceptor/filter của HTTP client chứ không trả kết quả về business layer ở một lần gọi tách biệt. Với connection đã có sẵn, bước DNS/TCP/TLS có thể được bỏ qua. Với cache, discovery không nhất thiết bị gọi qua mạng.

## 2. Phân biệt startup latency, first-call latency và steady-state latency

Ba số đo khác nhau cần được ghi riêng:

1. **Process startup:** từ lúc JVM bắt đầu đến khi ứng dụng được coi là ready nhận request.
2. **First-call latency:** từ khi bắt đầu request đầu tiên đến khi nhận đủ kết quả, gồm công việc lazy chưa thực hiện.
3. **Steady-state latency:** độ trễ của các request sau khi cấu hình/tài nguyên chủ yếu đã được sử dụng, dưới tải xác định.

Ví dụ minh họa:

| Sự kiện | Thời gian |
| --- | ---: |
| Spring Boot bắt đầu chạy | T=0 ms |
| ApplicationReadyEvent | T=2.500 ms |
| Request đầu đến inventory-service | T=2.600 ms |
| Lần gọi Inventory đầu hoàn tất | T=3.350 ms |
| Lần gọi Inventory sau hoàn tất | 45 ms sau khi bắt đầu |

Chênh lệch **750 ms so với 45 ms** không tự chứng minh có 705 ms do LoadBalancer. Phải tách thời gian của context initialization, discovery, pool, DNS, TCP/TLS và backend. Cũng không được lấy kết quả request ấm trên localhost rồi suy diễn latency production trên các zone.

### 2.1. Warm-up chuyển chi phí, không làm chi phí biến mất

Nếu dời 500 ms khởi tạo khỏi request đầu sang startup, người dùng đầu tiên có thể thấy nhanh hơn. Nhưng:

- Startup/readiness có thể lâu hơn.
- Một số downstream có thể chưa sẵn sàng khi caller bắt đầu warm-up.
- Khi rollout nhiều pod, các probe warm-up có thể tạo spike lưu lượng.
- Tiền khởi tạo tài nguyên có thể tăng memory/threads và kết nối nhàn rỗi.

Vì vậy, phải đánh giá **thời gian sẵn sàng**, **first-call P95/P99**, **tỷ lệ lỗi startup** và **tải downstream**, không chỉ một con số latency sau warm-up.

## 3. Spring Cloud LoadBalancer tạo child context theo service ID

Tài liệu Spring Cloud LoadBalancer mô tả mỗi **service ID** có một **Spring child ApplicationContext** riêng. Theo mặc định, context này được tạo **lazily** khi request đầu cho service ID đó đi qua LoadBalancer.

Ví dụ ứng dụng Order gọi ba service:

~~~text
inventory-service  -> context LB của Inventory
payment-service    -> context LB của Payment
catalog-service    -> context LB của Catalog
~~~

Nếu request đầu chỉ gọi inventory-service, context của payment-service và catalog-service có thể chưa khởi tạo. **Tạo bean RestClient/WebClient ở startup không đồng nghĩa đã khởi tạo child context của tất cả service ID**.

### 3.1. Eager-load chính xác các service ID quan trọng

Spring Cloud hỗ trợ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      eager-load:
        clients:
          - inventory-service
          - payment-service
~~~

Ý nghĩa: khởi tạo sớm **LoadBalancer client contexts** dành cho hai service ID nêu trên, thay vì chờ request đầu.

Không cần chọn toàn bộ service nếu chỉ một số downstream có latency đầu tiên quan trọng. **Tên phải đúng service ID được dùng khi gọi**, không phải tên class, URL vật lý, pod name hoặc bean RestClient.

### 3.2. Eager context không phải preconnect

| Tác động của eager-load | Có thể thực hiện? |
| --- | --- |
| Tạo sớm child ApplicationContext cho service ID | **Có** |
| Tạo supplier/LoadBalancer beans trong child context | **Có**, theo cấu hình |
| Bảo đảm registry đã trả danh sách mới nhất | **Không** |
| Bảo đảm cache chứa đủ mọi instance | **Không** |
| Mở TCP/TLS tới tất cả instance | **Không** |
| Bảo đảm backend đã sẵn sàng nhận request | **Không** |
| Bảo đảm mọi HTTP client đã được khởi tạo tài nguyên | **Không** |

Eager-loading làm giảm một phần **lazy initialization cost**, không thay thế health check, discovery synchronization hoặc connection warm-up.

### 3.3. Không eager-load mọi service chỉ để “cho chắc”

Tạo hàng trăm context từ startup có thể:

- Tăng thời gian khởi động và số bean/đối tượng.
- Tăng memory footprint và công việc cấu hình.
- Khởi tạo những service không bao giờ được gọi trong tiến trình này.
- Che mất mục tiêu tối ưu: chi phí thực có thể nằm ở TLS hoặc DNS thay vì context.

Trước khi thêm nhiều service ID, hãy đo xem **lazy child-context creation** thực sự đóng góp bao nhiêu vào first-call latency.

## 4. Discovery, cache và health-check cũng có trạng thái ban đầu

**ServiceInstanceListSupplier** cung cấp danh sách bản sao cho thuật toán chọn. Tùy cấu hình, nó lấy danh sách từ DiscoveryClient/ReactiveDiscoveryClient, CachingServiceInstanceListSupplier hoặc HealthCheckServiceInstanceListSupplier.

~~~text
Discovery source -> Cache hoặc HealthCheck -> Zone/Hint filters -> LB
~~~

### 4.1. First discovery query

Nếu discovery client chưa có snapshot, lần lấy instance đầu có thể làm:

- Gọi registry hoặc đọc cache registry.
- Deserialize metadata và dựng ServiceInstance.
- Đợi registry đồng bộ sau khi provider vừa đăng ký.

Eager-load context không bảo đảm network discovery query đã hoàn tất. Một lời gọi warm-up qua service ID có thể ép hệ thống thực hiện **lookup + choose** thực tế, nhưng không nên kích hoạt lookup không kiểm soát ở bean constructor.

### 4.2. Cache ấm chưa chắc chứa instance còn khỏe

Spring Cloud LoadBalancer có cache theo service ID; tài liệu hiện hành ghi nhận cache mặc định được bật và TTL mặc định **35 giây** trong cấu hình thông dụng. Khi TTL hết, lần đọc sau có thể cần cập nhật từ discovery.

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 35s
~~~

Đây là ví dụ cho thấy cache có thể giúp giảm chi phí lấy danh sách instance, **không phải cơ chế giữ connection mở**. Nếu discovery implementation (ví dụ Eureka) đã có cache, việc cache hai tầng có thể tăng độ trễ nhìn thấy instance mới/mất.

Một cache đã được làm ấm có thể nhanh hơn nhưng **stale**. Đừng đánh đổi tính đúng đắn của lựa chọn instance chỉ vì first request nhanh hơn vài mili giây.

### 4.3. Health-check warm-up có độ trễ riêng

HealthCheckServiceInstanceListSupplier kiểm tra instance theo lịch và phát danh sách gần nhất. Sau startup, có thể cần thời gian để lần probe đầu hoàn tất, rồi mới có đủ dữ liệu health. Nếu health publisher đã cấu hình replay/snapshot, kết quả đầu cũng phụ thuộc chính sách khi không tìm thấy instance khỏe.

Không nên lấy một lần HTTP warm-up thành công rồi kết luận tất cả instance đang healthy; LoadBalancer có thể đã chọn một instance duy nhất. Khi health check có lịch riêng, cần theo dõi **thời điểm snapshot được cập nhật**, không chỉ HTTP status của warm-up request.

## 5. Khởi tạo RestTemplate và RestClient đúng vòng đời

**RestTemplate** và **RestClient** là các HTTP clients đồng bộ. Thông thường nên tạo cấu hình và client **một lần**, dùng lại giữa nhiều request, thay vì tự lắp lại mỗi lần gọi nghiệp vụ.

Ví dụ cấu hình cho RestClient:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryRestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    RestClient inventoryRestClient(
            @LoadBalanced RestClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Ví dụ cho RestTemplate trong hệ thống cũ:

~~~java
@Bean
@LoadBalanced
RestTemplate inventoryRestTemplate() {
    return new RestTemplate();
}
~~~

Những đoạn này chỉ minh họa lifecycle và LoadBalancer integration, **chưa cấu hình timeout, HTTP engine, pool và observability**. Production nên có transport timeout rõ ràng và dùng các customizer/bean do Spring Boot quản lý khi thích hợp.

### 5.1. Tạo client object không đồng nghĩa mở connection

Nhiều HTTP client dùng kiểu **lazy I/O**:

~~~text
Tạo bean RestClient
       |
       | chưa gọi Inventory
       v
Tạo request đầu
       |
       | LoadBalancer chọn instance
       | HTTP transport tìm/tạo connection
       v
Nhận response
~~~

Không nên kết luận “đã warm” chỉ vì Spring Context đã có RestClient bean. Ngay cả khi một factory/underlying HTTP client được tạo sớm, **DNS/TCP/TLS vẫn có thể chỉ chạy ở request đầu**.

### 5.2. Không tạo một pool mới cho mỗi request

Một anti-pattern:

~~~java
StockResponse loadStock(String sku) {
    // Không nên dựng lại HTTP client và transport bên dưới liên tục.
    RestClient client = RestClient.builder()
            .baseUrl("https://inventory.internal")
            .build();

    return client.get()
            .uri("/api/stock/{sku}", sku)
            .retrieve()
            .body(StockResponse.class);
}
~~~

Đoạn này có thể làm mất các timeout, auth, tracing và request factory đã cấu hình tại bean chính. Nếu code còn tạo **Apache HttpClient/connection manager mới** cho mỗi lần gọi, pool không được dùng lại hiệu quả và có nguy cơ rò rỉ tài nguyên.

**Không khẳng định mọi lần gọi RestClient.builder() đều tạo pool/socket mới**: điều đó phụ thuộc HTTP engine và cơ chế chia sẻ tài nguyên. Nhưng việc dựng client/factory liên tục làm lifecycle khó kiểm soát và không phải chiến lược warm-up đúng.

### 5.3. Dùng client đã cấu hình như một đối tượng lâu sống

RestClient/RestTemplate thường được dùng như singleton hoặc thành phần tái sử dụng, với cấu hình hoàn tất trước khi xử lý traffic. Không mutate interceptors, message converters hoặc request factory đồng thời với các request. Đặt timeout, pool size, auth, TLS và observability ở lúc xây dựng client.

Trong hệ thống RestTemplate đã có ổn định, chưa nhất thiết phải chuyển ngay sang WebClient để giải quyết first-call latency; trước tiên hãy xác minh **bean reuse, connection pool và thời điểm lookup**.

## 6. OpenFeign: tạo Feign proxy khác với thiết lập connection

**Spring Cloud OpenFeign** tạo proxy Java từ interface:

~~~java
@FeignClient(name = "inventory-service")
interface InventoryFeignClient {
    @GetMapping("/api/stock/{sku}")
    StockResponse stock(@PathVariable("sku") String sku);
}
~~~

OpenFeign còn có context/cấu hình per named client, với encoder, decoder, contract, interceptors và HTTP Client implementation. Từ Spring Cloud OpenFeign 4.x, **@FeignClient attributes được resolve eagerly theo mặc định** để hỗ trợ AOT. Thuộc tính:

~~~yaml
spring:
  cloud:
    openfeign:
      lazy-attributes-resolution: false
~~~

liên quan tới **thời điểm resolve annotation attributes**. Nó **không phải nút bật TCP preconnect, không tương đương spring.cloud.loadbalancer.eager-load.clients**, và không bảo đảm Feign đã gửi HTTP request nào.

### 6.1. Không gọi Feign trong constructor/Bean initialization

Tài liệu Spring Cloud OpenFeign cảnh báo việc gọi Feign client trong giai đoạn sớm của application lifecycle, khi các bean/context còn được khởi tạo, **không được hỗ trợ** và có thể dẫn tới initialization errors.

Tránh:

~~~java
@Component
class BadStartup {

    BadStartup(InventoryFeignClient feign) {
        feign.stock("BOOK-01");  // Sai vị trí: I/O trong constructor.
    }
}
~~~

Nếu cần gọi thử thực sự, thực hiện ở một hook startup **sau khi context và các proxies sẵn sàng**, có timeout, có giới hạn và quyết định rõ downstream lỗi có chặn readiness hay không.

### 6.2. Cấu hình Feign transport theo implementation thực tế

Feign có thể dùng Apache HttpClient 5, OkHttp hoặc một HTTP client khác. Thời gian TCP/TLS đầu tiên, pool acquisition và khả năng reuse connection phụ thuộc **transport phía dưới**, không chỉ interface @FeignClient. Tham số Feign connectTimeout/readTimeout không đảm bảo mọi phase hoặc tổng deadline.

Việc “tạo proxy Feign sớm” chỉ loại bớt chi phí khởi tạo proxy/configuration; muốn warm connection phải thực sự thực hiện một request an toàn hoặc dùng API preconnect riêng nếu transport hỗ trợ và có lý do chính đáng.

## 7. Reactor Netty có API warmup() cho tài nguyên client

**WebClient** thường dùng **Reactor Netty** làm HTTP connector trong Spring WebFlux. Theo tài liệu Reactor Netty, các tài nguyên sau mặc định có thể được khởi tạo theo nhu cầu ở **request đầu**:

- Event loop group.
- Hostname resolver.
- Native transport libraries (nếu platform sử dụng).
- Native security libraries, ví dụ OpenSSL (nếu được cấu hình).

Reactor Netty cung cấp:

~~~java
HttpClient httpClient = HttpClient.create();

// Chủ động khởi tạo tài nguyên Netty.
httpClient.warmup().block(Duration.ofSeconds(3));
~~~

**HttpClient.warmup() trả Mono<Void>**. Nếu chỉ gọi warmup() mà không subscribe, công việc reactive **chưa được thực hiện**. Trong ví dụ trên, block(Duration) được gọi trên **startup thread hoặc một worker có thể blocking**, không dùng trong Netty event loop và không đưa vào đường xử lý WebFlux request.

### 7.1. warmup() làm được và không làm được gì?

| Công việc | HttpClient.warmup() |
| --- | --- |
| Khởi tạo event loop/resources đã cấu hình | Có |
| Khởi tạo hostname resolver | Có |
| Nạp native transport/security libraries cần thiết | Có |
| Phân giải trước DNS của inventory-a.internal | **Không bảo đảm** |
| Thực hiện TCP connect đến inventory-service | **Không** |
| Thực hiện TLS handshake với mọi instance | **Không** |
| Đi qua Spring Cloud LoadBalancer để chọn ServiceInstance | **Không** |
| Làm nóng decoder/mapper theo endpoint thực tế | **Không bảo đảm** |

Trong tài liệu Reactor Netty, lời gọi HTTP **đầu tiên** vẫn là lần phân giải hostname và mở connection; những request sau có thể sử dụng kết nối trong pool. Vì vậy, dùng warmup() chỉ loại bỏ **một phần chi phí ban đầu ở client**, không phải giải pháp preconnect toàn diện.

### 7.2. Đảm bảo warm đúng HttpClient được WebClient sử dụng

Ví dụ bean cấu hình thống nhất:

~~~java
import java.time.Duration;
import io.netty.channel.ChannelOption;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.boot.ApplicationRunner;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.netty.http.client.HttpClient;

@Configuration(proxyBeanMethods = false)
class InventoryWebClientConfiguration {

    @Bean
    HttpClient inventoryNettyHttpClient() {
        return HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, 500)
                .responseTimeout(Duration.ofSeconds(2));
    }

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder(
            HttpClient inventoryNettyHttpClient) {
        return WebClient.builder().clientConnector(
                new ReactorClientHttpConnector(inventoryNettyHttpClient));
    }

    @Bean
    ApplicationRunner warmupHttpResources(
            HttpClient inventoryNettyHttpClient) {
        return args -> inventoryNettyHttpClient.warmup()
                .block(Duration.ofSeconds(3));
    }
}
~~~

Điểm mấu chốt là **cùng HttpClient bean** được:

1. Truyền vào ReactorClientHttpConnector của WebClient.
2. Gọi warmup() trong ApplicationRunner.

Nếu khởi tạo một HttpClient A để warm nhưng WebClient thực tế lại dùng HttpClient B với resources riêng, kết quả warm-up có thể không tương ứng với traffic thực. Trong thực tế, các HttpClient có thể dùng tài nguyên toàn cục chung, nhưng **không nên dựa vào việc chia sẻ ngầm** để chứng minh một warm-up đã áp dụng đúng connector.

**Lưu ý về Spring Boot:** tạo WebClient.Builder bằng WebClient.builder() thủ công có thể bỏ qua một số **WebClientCustomizer, observation, codec, auth hoặc connector customization** do Boot cung cấp. Khi đưa vào production, cần giữ những customizations hiện có hoặc dùng cấu hình builder do Boot quản lý một cách phù hợp. Ví dụ trên chỉ tập trung vào cơ chế warm-up Netty.

### 7.3. Không gọi block() trên WebFlux event loop

Đặt warm-up có block() trong một handler:

~~~java
@GetMapping("/stock")
Mono<StockResponse> readStock() {
    // Sai: dùng blocking warmup trên request path reactive.
    httpClient.warmup().block();
    return inventoryClient.getStock("BOOK-01");
}
~~~

Đây là anti-pattern: request đang chạy trên event loop có thể bị chặn, làm giảm concurrency và gây lỗi non-blocking-thread. Nếu startup cần chờ tài nguyên Netty, thực hiện ở ApplicationRunner (startup thread) với **thời hạn hữu hạn**, hoặc triển khai warm-up bất đồng bộ và readiness gate rõ ràng.

## 8. Connection pool, TCP keep-alive và TLS reuse

Sau khi chọn một ServiceInstance, HTTP client kết nối đến **origin thực tế** (scheme, host, port). Connection pool có thể giữ connection để các request sau không phải thiết lập TCP/TLS lại từ đầu.

~~~text
Request 1 -> inventory-a:8443
  pool chưa có connection phù hợp
  DNS / TCP / TLS -> HTTP request -> giữ connection idle

Request 2 -> inventory-a:8443
  pool có connection còn hợp lệ
  reuse -> HTTP request

Request 3 -> inventory-b:8443
  origin khác
  có thể phải DNS / TCP / TLS mới
~~~

### 8.1. Load balancing và reuse connection không mâu thuẫn

Round Robin có thể chọn xen kẽ A/B, nhưng transport vẫn có thể giữ **connection riêng đến từng origin**, nếu pool và server cho phép. Không cần cố ghim tất cả traffic vào một instance chỉ để có connection reuse.

Tuy nhiên, khi số instance tăng đột ngột, mỗi origin có thể cần connection mới. Đó là lý do latency sau scale-out đôi khi tăng tạm thời, dù cả caller và Spring Cloud LoadBalancer contexts đã tồn tại.

### 8.2. HTTP/2 thay đổi cách hiểu “một request = một connection”

Khi HTTP/2 được thương lượng, một connection có thể mang nhiều streams đồng thời. Vì thế:

- **Số HTTP requests** không bằng **số TCP connects**.
- Giới hạn connection pool không tương đương tuyệt đối với giới hạn request concurrency.
- Một connection vẫn có thể bị server/proxy đóng do idle timeout, max age hoặc GOAWAY.

Không dùng thống kê **response count** để khẳng định client đã reuse connection. Cần connection-level metrics/traces từ HTTP transport và kiểm tra HTTP version thực tế.

### 8.3. Những nguyên nhân khiến connection không được tái sử dụng

- Server, ingress, load balancer hạ tầng hoặc proxy gửi Connection: close / đóng idle connection.
- Client pool có maxIdleTime hoặc maxLifeTime quá ngắn.
- Connection bị reset, timeout hoặc bị coi không lành mạnh.
- Request tới instance khác (origin khác).
- HTTP engine được tạo lại liên tục với pool không được chia sẻ.
- TLS/proxy configuration thay đổi.
- Pool đạt giới hạn, connection bị eviction hoặc đóng để giảm tài nguyên.

Đừng đặt idle timeout rất dài chỉ để giữ connection vĩnh viễn: socket có thể đã chết ở trung gian nhưng client chưa biết, và tài nguyên nhàn rỗi cũng có chi phí.

### 8.4. DNS cache ấm không có nghĩa IP ổn định

DNS TTL có thể khiến một hostname được resolve lại. Với registry chứa hostname, thay đổi IP sau deployment là chuyện bình thường. Hardcode hoặc ép cache DNS quá lâu để tối ưu cold lookup có thể khiến traffic gửi tới địa chỉ đã mất.

**Không vô hiệu xác minh TLS, hostname verification hoặc kiểm soát certificate chỉ để giảm handshake time.** TLS session resumption có thể giúp giảm chi phí tùy transport và server, nhưng không đảm bảo mọi connection mới đều được resume thành công.

## 9. Khởi động ứng dụng và readiness: warm-up đặt ở đâu?

Theo tài liệu Spring Boot, thứ tự lifecycle ở giai đoạn cuối có thể hiểu như sau:

~~~text
ApplicationContext refreshed
    |
ApplicationStartedEvent
    |
ApplicationRunner / CommandLineRunner
    |
ApplicationReadyEvent
    |
AvailabilityChangeEvent: ReadinessState.ACCEPTING_TRAFFIC
~~~

Do đó, **ApplicationRunner** là một chỗ phù hợp để thực hiện warm-up có giới hạn **sau khi context đã sẵn**, trước tín hiệu readiness accepting traffic trong lifecycle chuẩn của Spring Boot.

### 9.1. Cách lựa chọn theo tính bắt buộc

| Mục tiêu | Cách thực hiện | Khi downstream lỗi lúc startup |
| --- | --- | --- |
| Loại chi phí tạo context LB | eager-load.clients | Thường không cần gửi network probe |
| Khởi tạo Reactor Netty resources | HttpClient.warmup() trong runner | Có thể log và tùy policy fail startup nếu tài nguyên nội bộ lỗi |
| Kiểm tra downstream quan trọng thật sự trả lời | GET warm-up có thời hạn | Chỉ chặn readiness nếu dependency **thật sự bắt buộc** cho toàn bộ traffic |
| Làm nóng cache không bắt buộc | Job startup bất đồng bộ/periodic | Cho phép tiếp tục phục vụ, báo degraded metric |
| Chỉ làm nóng khi traffic đã bắt đầu | Probe chạy có kiểm soát sau ready | Không giữ startup nhưng request đầu có thể vẫn cold |

Không đưa một yêu cầu **“mọi dependency phải UP”** vào readiness một cách máy móc. Nếu A chỉ cung cấp một chức năng phụ, A tạm thời lỗi có thể không nên khiến toàn bộ Order Service bị loại khỏi load balancer của Kubernetes. Ngược lại, với dependency bắt buộc để đáp ứng mọi request, chặn readiness có thể hợp lý nhưng cần tránh **circular startup dependency**.

### 9.2. Không warm bằng @PostConstruct khi cần Feign/LoadBalancer

Đoạn sau thường có rủi ro:

~~~java
@PostConstruct
void init() {
    inventoryFeignClient.stock("BOOK-01");
}
~~~

Bean có thể đang được khởi tạo và Feign/LoadBalancer subcontexts chưa đạt trạng thái thích hợp. Thực hiện I/O trong constructor hoặc @PostConstruct còn khiến startup failure khó phân loại. Theo hướng dẫn Spring Cloud OpenFeign, không nên sử dụng Feign client trong giai đoạn khởi tạo bean.

**Không có một hook lifecycle duy nhất an toàn cho tất cả chiến lược warm-up.** Với warm-up bất đồng bộ, chỉ dùng @EventListener(ApplicationReadyEvent.class) rồi subscribe fire-and-forget không bảo đảm nó hoàn tất trước readiness. Cần định nghĩa cơ chế theo dõi hoàn tất và gate readiness nếu có yêu cầu cứng.

## 10. Làm nóng kết nối bằng một HTTP request an toàn

Muốn DNS/TCP/TLS/pool và LoadBalancer **thực sự được sử dụng**, có thể thực hiện một request GET/HEAD an toàn tới downstream khi application context đã sẵn:

~~~text
ApplicationRunner
  -> WebClient qua @LoadBalanced
  -> LoadBalancer chọn một ServiceInstance
  -> HTTP connector kết nối host/port thật
  -> GET /internal/warmup
  -> đọc/đóng response, cho phép pool giữ connection nếu hợp lệ
~~~

Nhưng chỉ nên làm khi có **endpoint được thiết kế rõ là safe, idempotent, chi phí thấp**. Đừng gọi POST thanh toán, tạo đơn, đặt chỗ hoặc kích hoạt job như một “warm-up”.

### 10.1. Ví dụ WebClient warm-up có timeout

Giả sử Inventory cung cấp endpoint **GET /internal/warmup** đã xác thực, không có side effect:

~~~java
import java.time.Duration;
import org.springframework.boot.ApplicationRunner;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.http.ResponseEntity;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Bean
WebClient inventoryWebClient(
        @LoadBalanced WebClient.Builder builder) {
    return builder.baseUrl("http://inventory-service").build();
}

@Bean
ApplicationRunner inventoryWarmupProbe(
        WebClient inventoryWebClient) {
    return args -> {
        Mono<ResponseEntity<Void>> probe = inventoryWebClient.get()
                .uri("/internal/warmup")
                .retrieve()
                .toBodilessEntity()
                .timeout(Duration.ofSeconds(2));

        // Chỉ block trên startup thread; đây là policy hard-gate.
        probe.block(Duration.ofSeconds(3));
    };
}
~~~

Ví dụ này **chủ động chặn tiến trình startup nếu probe lỗi**, vì exception được để lan ra ngoài ApplicationRunner. Đó chỉ phù hợp khi Inventory là dependency bắt buộc và deployment/rollout đã tính đến khả năng nó tạm thời không khả dụng.

Nếu warm-up chỉ là tối ưu hiệu năng, có thể **catch lỗi có chọn lọc, ghi metric và tiếp tục startup**, thay vì làm toàn bộ replica không ready vì Inventory đang lỗi. Không viết một vòng retry vô hạn ở ApplicationRunner.

**Cần phân biệt hai timeout trong ví dụ:**

- **Mono.timeout(2s):** ngân sách cho publisher, có thể bao gồm chọn instance, pool, network và decode.
- **block(Duration.ofSeconds(3)):** giới hạn thời gian startup thread chờ kết quả, không phải setter connect/read timeout của transport.

Phải cấu hình transport timeout phù hợp riêng (connect, response, pool acquire). Không nên coi một câu lệnh block có timeout là thay thế đầy đủ cho chính sách cleanup/network.

Nếu có cả runner gọi **HttpClient.warmup()** lẫn runner gọi HTTP probe, thứ tự của hai runner không được mặc định bảo đảm. Khi cần Netty resources khởi tạo trước probe, hãy dùng **một ApplicationRunner** thực hiện tuần tự hoặc cấu hình thứ tự rõ ràng bằng @Order.

### 10.2. Một request không warm hết mọi bản sao

Nếu discovery trả [A, B, C], warm-up GET ở trên có thể chỉ được gửi đến **B**. Connection đến A/C vẫn cold. Ngay cả khi gọi ba lần, Round Robin hoặc policy zone/hint không bảo đảm từng instance nhận đúng một request.

Muốn thật sự warm mọi instance cần một cơ chế kiểm soát danh sách, khả năng truy cập và đích gọi, nhưng nó có chi phí/độ phức tạp cao hơn:

- Xác định inventory-service có bao nhiêu bản sao hiện tại.
- Phân biệt instance ID, scheme, host và port; danh sách có thể thay đổi ngay sau snapshot.
- Dùng request **safe**, timeout và giới hạn concurrency.
- Không bypass auth, mTLS hoặc chính sách tenant/zone.
- Không tạo traffic bão vào backend mới deploy.
- Không bảo đảm kết nối ấy sẽ còn mở sau idle timeout hoặc scaling.

Trong nhiều trường hợp, **không cần** warm tất cả instance. Làm nóng resources, eager-load service ID quan trọng và để traffic bình thường sử dụng connection pool là lựa chọn đơn giản hơn.

### 10.3. Endpoint health không tự động là endpoint warm-up

GET /actuator/health thường là tín hiệu kiểm tra trạng thái ứng dụng, không nhất thiết:

- Kích hoạt code path đắt của một API cụ thể.
- Đi qua đúng serializer/Jackson DTO mà caller cần.
- Có cùng authentication/headers với request nghiệp vụ.
- Phản ánh cùng khả năng xử lý một API kinh doanh.

Nếu xây dựng **/internal/warmup**, endpoint phải có contract rõ, giới hạn quyền truy cập, không kích hoạt tác vụ ghi hay khóa tài nguyên đắt, và có hành vi không nguy hiểm khi hàng trăm caller cùng gọi.

## 11. Warm-up của RestClient/RestTemplate và OpenFeign

Với client blocking, không có một API warmup() chuẩn trên RestClient hoặc RestTemplate tương đương HttpClient.warmup() của Reactor Netty. Có thể:

1. Xây dựng **HTTP client/connection manager dùng lại** khi tạo bean.
2. Khởi tạo sớm child context Spring Cloud LoadBalancer.
3. Gọi một **endpoint safe** bằng chính RestClient/RestTemplate/Feign được cấu hình để đi qua LoadBalancer.

Ví dụ với RestClient:

~~~java
@Bean
ApplicationRunner warmupInventoryBlocking(RestClient inventoryRestClient) {
    return args -> {
        inventoryRestClient.get()
                .uri("/internal/warmup")
                .retrieve()
                .toBodilessEntity();
    };
}
~~~

Ở đây giả định bean inventoryRestClient đã được cấu hình **@LoadBalanced** đúng như mục 5, có baseUrl inventory-service và timeout thích hợp. **Không dùng một RestClient trực tiếp tới URL khác** để tuyên bố client logic qua LoadBalancer đã warm.

Ví dụ trên **không đặt một deadline tổng**; chỉ minh họa vị trí gọi. Trong production phải cấu hình timeout HTTP engine và tổng ngân sách startup/probe, đồng thời quyết định khi exception phát sinh thì fail hay degrade.

Với **Feign**, cũng có thể gọi một method GET không có side effect qua Feign proxy ở ApplicationRunner, nếu tương thích lifecycle và policy. Nhưng Feign không có hành vi đảm bảo preconnect mọi instance; việc này tạo **một HTTP request thực** và chịu những exception/retry của Feign/client bên dưới.

### 11.1. Đừng tạo riêng warm-up HTTP client với pool khác

Nếu warm-up gọi bằng một RestTemplate A nhưng request nghiệp vụ dùng RestClient B trên Apache HC5 connection pool khác, connection đã được mở bởi A **không nhất thiết** được B tái sử dụng. Hãy xác minh cùng underlying pool/HTTP engine và cùng TLS/proxy configuration nếu mục tiêu là giữ connection.

Không nên giữ credential riêng thiếu policy chỉ để probe /internal/warmup. Warm-up phải đi qua cấu hình authentication/tracing/authorization phù hợp với backend và môi trường.

## 12. Làm nóng connection pool bằng nhiều request: rủi ro và giới hạn

Một số hệ thống cố tình gửi nhiều HTTP requests song song ở startup để tăng số lượng connection đang mở:

~~~text
10 warm-up GET đồng thời -> mong đợi 10 sockets sẵn sàng
~~~

Giả định này không đáng tin nếu không biết rõ HTTP transport:

- Pool có thể dùng lại cùng connection cho các request tuần tự.
- HTTP/2 có thể multiplex nhiều streams vào một TCP connection.
- Connection pool giới hạn max connections, pending acquires hoặc tự co giãn.
- LoadBalancer có thể chọn instance theo zone/hint, không đảm bảo phân tán yêu cầu theo ý muốn.
- Backend hoặc proxy có thể đóng socket idle ngay sau warm-up.
- Truyền tải đồng thời có thể làm tăng CPU/TLS handshake, gây phản tác dụng trong rollout.

**Không khuyến nghị gửi hàng trăm requests giả để ép pool mở thật nhiều sockets.** Nếu cần preconnect có kiểm soát, trước tiên chọn transport/connection manager có API và metrics thích hợp, xác định origin nào cần và giới hạn traffic theo ngân sách rõ ràng.

### 12.1. Mức độ warm-up hợp lý theo chi phí

| Chiến lược | Chi phí startup | Lợi ích chính | Rủi ro |
| --- | --- | --- | --- |
| Không warm-up | Thấp | Startup nhanh | First call gánh lazy overhead |
| Eager-load LB contexts | Thấp đến vừa | Giảm context lazy per service ID | Không loại bỏ DNS/TCP |
| Reactor Netty warmup() | Thấp đến vừa | Chuẩn bị event loop/resolver/native resources | Không có network preconnect |
| Một GET probe an toàn | Có network I/O | Kích hoạt LB + DNS/TCP/TLS + endpoint | Fail startup/cold downstream/extra load |
| Probe nhiều service | Cao hơn | Có thể giảm cold trên các dependency cần thiết | Startup phụ thuộc nhiều backend |
| Probe từng instance | Cao | Có thể warm nhiều origins | Dễ bão kết nối, bypass chính sách routing |

Nên bắt đầu bằng phương án đơn giản nhất có số liệu chứng minh hiệu quả, thay vì tối ưu mọi tầng cùng lúc.

## 13. Warm-up không tự giải quyết retry, timeout và sự cố recovery

Ngay cả sau warm-up thành công:

~~~text
T0: caller warm-up kết nối A thành công
T1: A bị terminate, registry đang cập nhật
T2: request thật vẫn chọn A từ cache cũ
T3: connection refused / timeout
~~~

Warm-up **không thể bảo đảm instance tiếp tục sống**. Cần:

- Discovery và cache TTL phù hợp.
- Health check đáng tin cậy nếu cần.
- Connect/read/response timeout để giới hạn chờ.
- Retry chỉ với lỗi/method an toàn và attempt budget.
- Circuit breaker/bulkhead cho cô lập và giảm tải.
- Tracing/metrics để phân biệt lỗi cold connection với dependency failure.

Ngược lại, warm-up thất bại không nhất thiết phải làm ứng dụng fail startup. Nếu Order có thể phục vụ các endpoint không cần Inventory, nên **tách readiness của Order** với tình trạng Inventory theo contract thay vì tạo startup dependency vòng tròn.

### 13.1. Không gửi retry storm ngay khi nhiều pod khởi động

Khi deploy 100 pod cùng lúc, mỗi pod warm-up 3 service và retry 3 attempts, downstream có thể nhận tới 900 attempts trong thời gian ngắn. Nếu backend cũng cold, probe tạo thêm áp lực đúng lúc nó cần thời gian khởi động.

Cần đặt:

- Số probes ít và giới hạn concurrency.
- Deadline ngắn, retries ít hoặc không retry ở warm-up.
- Backoff và jitter theo yêu cầu.
- Startup/rollout concurrency phù hợp.
- Chính sách degraded startup rõ ràng.
- Metrics để phát hiện warm-up gây tải.

**Warm-up là công việc phụ trợ phục vụ performance, không phải lý do vô hạn retry khi dependency chưa sẵn sàng.**

## 14. Trạng thái hạ tầng có thể làm “ấm” biến thành “lạnh” trở lại

| Sự kiện | Điều gì có thể lạnh trở lại? | Điều cần kiểm tra |
| --- | --- | --- |
| Caller pod restart | JVM/beans/LB contexts/HTTP resources | Startup/readiness và first call |
| Inventory pod scale-out | Connections đến instance mới | First request tới origin mới |
| DNS record đổi | Resolver cache hết hạn, kết nối theo IP mới | DNS TTL và pool |
| Kết nối idle quá lâu | Pool đã đóng hoặc bị proxy close | Keep-alive/idle timeouts |
| Backend rollout/TLS rotation | TLS handshake hoặc session resumption | Certificate, SNI, truststore |
| Cache LB hết TTL | Discovery refresh | Registry latency/cache metrics |
| Traffic đổi zone/hint | Instance set mới sau filter | Supplier chain và metadata |
| JVM tải class chưa từng dùng | Classloading/JIT/serializer path | First-use code path |
| Autoscaling caller giảm xuống 0 | Toàn bộ process cold | Startup architecture |

Do đó, một phép đo ngay sau warm-up chỉ chứng minh **trạng thái tại thời điểm đo**. Hệ thống có thể gặp cold effects nhiều lần trong ngày do thay đổi topology, connection lifecycle và tải.

## 15. Đo độ trễ cold và warm như thế nào?

Trước khi bật warm-up, cần dựng một baseline. Tối thiểu nên có:

- **Startup duration** đến thời điểm readiness.
- **First HTTP call** tới từng service ID quan trọng sau startup.
- **Các lần gọi thứ 2–N**, cùng endpoint và payload, không thay đổi client bean.
- **First call tới một instance mới** vừa scale-out.
- **Request sau khi để idle lâu** hơn thời gian giữ connection.
- **P50/P95/P99** ở tải và topology đại diện cho production.

Đừng so sánh một lần cold request với đúng một warm request rồi kết luận chắc chắn mức cải thiện. DNS cache, JIT, CPU scheduling, GC, backend load và network jitter đều có thể tạo biến động lớn.

### 15.1. Dùng đồng hồ monotonic cho elapsed time

Ví dụ tối giản để đo một lần gọi RestClient:

~~~java
long begin = System.nanoTime();

try {
    StockResponse response = inventoryRestClient.get()
            .uri("/api/stock/{sku}", "BOOK-01")
            .retrieve()
            .body(StockResponse.class);
} finally {
    long elapsedNanos = System.nanoTime() - begin;
    System.out.println("Elapsed (ms) = " +
            Duration.ofNanos(elapsedNanos).toMillis());
}
~~~

**System.nanoTime()** thích hợp để tính elapsed time trên cùng tiến trình; không dùng timestamp wall clock rồi trừ nhau nếu clock có thể nhảy do đồng bộ thời gian. Với production, dùng **Micrometer Timer/Observation** và histogram thay vì System.out trong mỗi request.

### 15.2. Với WebClient, chỉ bắt đầu đo lúc subscribe

WebClient thường thực thi I/O khi có subscription. Đo thời gian chỉ để **tạo Mono** là không đúng:

~~~java
long start = System.nanoTime();
Mono<StockResponse> mono = inventoryWebClient.get()
        .uri("/api/stock/BOOK-01")
        .retrieve()
        .bodyToMono(StockResponse.class);
// Lúc này có thể chưa có HTTP request nào.
~~~

Một cách đo elapsed gần đúng cho từng subscription:

~~~java
Mono<StockResponse> timed = Mono.defer(() -> {
    long begin = System.nanoTime();
    return inventoryWebClient.get()
            .uri("/api/stock/BOOK-01")
            .retrieve()
            .bodyToMono(StockResponse.class)
            .doFinally(signal -> {
                long nanos = System.nanoTime() - begin;
                durationRecorder.record(
                        "inventory", signal.name(), nanos);
            });
});
~~~

Trong ví dụ, **durationRecorder** là helper đo metric do ứng dụng cung cấp, không phải API mặc định của Spring. Hook doFinally ghi cả complete/error/cancel; vì vậy cần phân biệt outcome thay vì coi mọi terminal signal đều là success.

Khi có retry, xác định timer đo **từng attempt** hay **lời gọi logic bao cả retries/backoff**. Hai loại đều hữu ích nhưng không thay thế nhau.

### 15.3. Một bảng đo minh họa

| Nhóm đo | Trước tối ưu | Sau eager + warmup | Cách diễn giải |
| --- | ---: | ---: | --- |
| Startup đến ready | 2.400 ms | 2.750 ms | Startup tăng 350 ms |
| First-call Inventory | 750 ms | 180 ms | Chi phí được dời khỏi request đầu |
| Steady-state Inventory P50 | 45 ms | 44 ms | Gần như không đổi |
| Steady-state Inventory P99 | 190 ms | 188 ms | Không cải thiện đáng kể |
| First-call instance mới | 600 ms | 590 ms | Vẫn cold vì instance mới chưa được kết nối |

**Các số hoàn toàn giả định** để minh họa cách đọc dữ liệu. Nếu chỉ báo first-call giảm 570 ms mà bỏ qua startup tăng 350 ms, dashboard sẽ kể một câu chuyện chưa đầy đủ.

## 16. Phân rã first-call latency theo tầng

Một phép đo tổng không chỉ ra nguyên nhân. Nên dùng:

| Tầng cần quan sát | Dấu hiệu/nguồn đo | Có thể tối ưu bằng |
| --- | --- | --- |
| Spring bean/classloading | Startup instrumentation, profile/JFR | Giảm bean/lazy path không cần thiết |
| Child LB context | Log khởi tạo LoadBalancerClientFactory/context | Eager-load service IDs cần thiết |
| Discovery query/cache | Registry metrics, supplier timing/cache hit | Dùng cache đúng chỗ, cải thiện discovery |
| HTTP event loop | Reactor Netty initialization/CPU | HttpClient.warmup() |
| Pool acquire | Active/idle/pending connections | Pool sizing/concurrency, không chỉ warmup |
| DNS | Resolver timing/cache hit | DNS configuration/TTL hợp lý |
| TCP connect | Connection establishment metrics | Reuse connection, topology mạng |
| TLS handshake | TLS handshake duration | Reuse/TLS configuration hợp lệ |
| Backend processing | Server tracing/endpoint latency | Backend warm-up, DB/query/cache |
| Decode/serialization | JFR, profiler, conversion timing | Jackson/codec configuration |

**Một slow first call có thể thực ra là backend cold.** Nếu backend vừa khởi động và lần đầu tải cache, khởi tạo database connection hoặc JIT code, việc warm **client** có thể không giải quyết phần lớn độ trễ. Cần trace hai phía và phân rã server processing time.

### 16.1. JFR, profiling và startup steps

Trong ứng dụng Java, **Java Flight Recorder (JFR)** và profiler có thể giúp quan sát CPU, classloading, lock contention, thread start, GC và network events. Spring Boot hỗ trợ ApplicationStartup instrumentation để xem các bước startup của application context. Kết hợp với HTTP client metrics và distributed tracing để tránh đổ toàn bộ độ trễ cho LoadBalancer.

Không bật profiling/wire logging nặng liên tục trên production mà không đánh giá overhead. Nếu cần capture trong thời gian ngắn, đặt phạm vi và che thông tin nhạy cảm.

### 16.2. Các metric cần tách

~~~text
app_startup_to_ready_seconds
outbound_first_call_seconds{service="inventory-service"}
outbound_http_duration_seconds{service="inventory-service"}
client_pool_pending_connections
client_pool_active_connections
client_connect_duration_seconds
client_tls_handshake_duration_seconds
loadbalancer_no_instance_total
outbound_retry_attempts_total
startup_warmup_failures_total
~~~

Đây là **bộ tên metric gợi ý**, không phải toàn bộ metric mặc định của Spring Boot, Spring Cloud hoặc Reactor Netty. Tên/sự sẵn có phụ thuộc instrumentation thực tế.

Tránh nhãn metric theo request ID, SKU, user ID, connection ID hoặc hostname ephemeral quá chi tiết gây high cardinality. Instance ID có thể hữu ích trong traces/logs, nhưng nếu đưa vào metric phải kiểm soát cardinality.

## 17. Kiểm thử warm-up bằng MockWebServer và Spring Cloud context

Một chiến lược kiểm thử tốt có **hai lớp**:

1. **Unit test:** xác nhận runner/subscription thật sự thực thi probe, timeout hoặc fallback policy.
2. **Integration test:** xác nhận request có **service ID** được LoadBalancer chuyển thành URI vật lý và đến đúng MockWebServer.

### 17.1. Unit test: warm-up WebClient phải subscribe

Ví dụ dùng fake ExchangeFunction để tránh network:

~~~java
AtomicInteger requestCount = new AtomicInteger();

ExchangeFunction fake = request -> {
    requestCount.incrementAndGet();
    return Mono.just(ClientResponse.create(HttpStatus.NO_CONTENT).build());
};

WebClient client = WebClient.builder()
        .baseUrl("http://inventory-service")
        .exchangeFunction(fake)
        .build();

Mono<ResponseEntity<Void>> probe = client.get()
        .uri("/internal/warmup")
        .retrieve()
        .toBodilessEntity();

assertEquals(0, requestCount.get()); // Chưa subscribe.
probe.block(Duration.ofSeconds(1));
assertEquals(1, requestCount.get()); // Probe thật sự được gọi.
~~~

Các class tương ứng: **AtomicInteger** trong java.util.concurrent.atomic; **ExchangeFunction/ClientResponse** trong Spring WebFlux; **HttpStatus** trong Spring HTTP; **Mono** trong Reactor.

**Giới hạn:** test này chỉ xác nhận subscription và request-building. Fake ExchangeFunction **không** có TCP/TLS, connection pool hoặc Spring Cloud LoadBalancer. Không dùng nó làm bằng chứng kết nối đã warm.

### 17.2. Integration test: phải quan sát server thật nhận request

Trong @SpringBootTest có hai MockWebServer ở port động, khai báo SimpleDiscoveryClient:

~~~java
@DynamicPropertySource
static void registerInstances(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.cloud.discovery.client.simple.instances.inventory-service[0].uri",
            () -> serverA.url("/").toString());
    registry.add(
            "spring.cloud.discovery.client.simple.instances.inventory-service[1].uri",
            () -> serverB.url("/").toString());
}
~~~

Cho cả hai server enqueue response 204 cho GET /internal/warmup. Sau đó gọi **chính @LoadBalanced WebClient/RestClient** được ứng dụng sử dụng. Kiểm tra:

- **RecordedRequest** cho thấy có request ở server A hoặc B.
- Method là GET; path là /internal/warmup.
- Không cố DNS lookup inventory-service như hostname vật lý.
- Không có request POST hoặc side effect.
- Có timeout hữu hạn khi một server chậm hoặc không phản hồi.
- Số probes/attempts đúng chính sách, không bị retry tự động nhân lên.

Nếu muốn chứng minh **mỗi instance nhận warm-up**, phải cấu hình selection deterministically hoặc gọi có chủ đích từng origin; chỉ dùng Round Robin mặc định không đủ bảo đảm. Đừng assert first request luôn tới server A vì vị trí counter có thể thay đổi.

### 17.3. Không kiểm tra reuse bằng response body

Hai HTTP requests đều trả 200 **không chứng minh** đã dùng chung TCP connection. Muốn kiểm chứng reuse, cần metrics/event hooks của underlying transport hoặc một server có khả năng ghi nhận connection identifier, TCP accepts và TLS handshakes.

Một server có thể có 2 HTTP requests trên 2 connections; hoặc HTTP/2 gửi nhiều requests trên một connection. Không suy luận từ thứ tự response hay số lượng RecordedRequest.

## 18. Thử nghiệm A/B: tránh benchmark bị sai

Để đánh giá lợi ích:

1. Chạy **cấu hình A không warm-up** và **cấu hình B có warm-up** ở môi trường tương đương.
2. Dùng cùng JDK, BOM, CPU/memory, HTTP engine, pool sizing và traffic pattern.
3. Đo nhiều lần khởi động **từ một process mới**, không chỉ đo trong một JVM đã chạy lâu.
4. Tách first call tới **service ID đã eager-load**, service ID chưa eager và instance mới.
5. Ghi cả startup time, first-call latency, steady-state P95/P99 và warm-up failures.
6. So sánh lượng connections và CPU/network phát sinh ở startup.
7. Test cả cold cache, hot cache và restart sau thời gian idle.
8. Giữ backend ở trạng thái tải xác định hoặc đo riêng backend latency.

### 18.1. “Cold start” không phải một phép thử JMH thông thường

JMH phù hợp cho **microbenchmark mã Java**, nhưng một request HTTP qua discovery, DNS, TCP/TLS và backend là phép đo nhiều hệ thống, không ổn định ở cấp nanosecond. Nên dùng integration/performance harness đo end-to-end và connection events.

Một phép đo duy nhất dễ bị nhiễu bởi:

- Warm state còn tồn tại từ test trước.
- Spring Test context cache tái sử dụng ApplicationContext.
- DNS cache hoặc pool toàn cục chưa được reset.
- Native transport/JIT đã được nạp trong JVM.
- Backend vừa scale hoặc cache DB vừa được khởi tạo.

Khi muốn đo **lần đầu thực sự**, cần process/context isolation rõ ràng, không chỉ tạo một instance WebClient mới trong cùng JVM.

### 18.2. Không assert thời gian tuyệt đối trong unit test

Test kiểu sau rất dễ flaky:

~~~java
assertTrue(firstCallMillis > secondCallMillis);
~~~

Không có gì bảo đảm request đầu luôn chậm hơn request sau trên một máy CI bị chia sẻ CPU. Thay vào đó:

- Unit test kiểm tra **hành vi warm-up được invoke** và giới hạn retries/deadline.
- Integration test xác minh **request đi qua LoadBalancer và HTTP server thật**.
- Performance test riêng so sánh **phân bố thống kê** qua nhiều process/requests.

## 19. Các tình huống first-call chậm nhưng warm-up không phải lời giải

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý phù hợp |
| --- | --- | --- |
| Request đầu cho mỗi service ID chậm | Lazy child context Spring Cloud LB | eager-load.clients cho service quan trọng |
| Request đầu mỗi JVM chậm trên WebClient | Reactor Netty event loop/resolver/native initialization | HttpClient.warmup() |
| Request đầu mỗi host:port mới chậm | DNS/TCP/TLS chưa thiết lập | Connection reuse; có thể probe giới hạn |
| Request sau idle dài lại chậm | Idle connection bị đóng | Điều chỉnh pool idle policy, hiểu lifecycle hạ tầng |
| Chỉ chậm khi traffic đột biến | Pool acquire queue/CPU/backpressure | Pool/concurrency sizing, timeout, profiling |
| Chậm khi có nhiều pods khởi động | Warm-up storm hoặc registry/backends chưa ready | Rollout pacing, jitter, giới hạn probes |
| HTTP 503 ngay, không có instance | Discovery/supplier rỗng | Kiểm tra registry/health, không tăng timeout |
| Response chậm dù client đã giữ connection | Backend query/DB/cache cold | Tối ưu backend, đo server spans |
| DNS lookup thường xuyên và lỗi | Resolver/TTL/network DNS | Điều tra DNS; không ép cache quá dài |
| RestClient nhanh nhưng Feign chậm lần đầu | Feign proxy/config/underlying HTTP engine khác | Phân biệt proxy init, request factory, LB context |
| Warm-up nhanh nhưng traffic thật vẫn chậm | Probe không đi qua code path/backend instance tương ứng | Tạo phép đo theo endpoint/instance thật |
| Sau deploy instance mới có P99 tăng | New origins cold, TLS/connection establishment | Quan sát per-origin connect và rollout |

Nếu số liệu cho thấy **độ trễ chủ yếu do backend**, cấu hình eager-load ở client có thể làm đẹp startup trace nhưng gần như không cải thiện request latency. Tối ưu phải dựa trên nguyên nhân được đo, không dựa trên tên cơ chế.

## 20. Thiết kế warm-up cho production: ưu tiên theo tác động

Một lộ trình an toàn:

1. **Xác minh cold effect:** chỉ ra chênh lệch latency đầu tiên với cùng client, instance và endpoint.
2. **Phân rã nguyên nhân:** child LB context, discovery, Netty resources, DNS/TCP/TLS, backend hay codec.
3. **Ưu tiên reuse:** client/HTTP engine/connection pool được tạo một lần và tái sử dụng.
4. **Eager-load có chọn lọc:** chỉ những service ID quan trọng với first-request SLO.
5. **Netty resource warm-up nếu phù hợp:** giữ cùng HttpClient/connector trong WebClient và startup runner.
6. **Probe HTTP nếu có lợi ích đo được:** GET endpoint safe, timeout, auth, giới hạn concurrency và số lần thử.
7. **Định nghĩa readiness policy:** fail startup chỉ khi dependency thật sự bắt buộc.
8. **Theo dõi cả trade-off:** startup time, CPU, memory, connections, first-call P99 và downstream load.
9. **Rollout có kiểm soát:** tránh hàng trăm pods warm đồng thời.
10. **Giữ khả năng phục hồi:** timeout, retry budget, health, cache và observability vẫn cần hoạt động.

### 20.1. Quyết định fail-fast hay best-effort

| Điều kiện | Chính sách khả dĩ |
| --- | --- |
| Inventory bắt buộc để xử lý **mọi** endpoint của Order | Có thể chặn readiness khi Inventory không hoạt động, nhưng cần chống vòng phụ thuộc startup |
| Inventory chỉ dùng ở một số endpoint | Warm-up best-effort; các endpoint khác vẫn được phục vụ |
| Registry mới khởi động và có eventual consistency | Retry ít có giới hạn hoặc chấp nhận degraded start, không retry vô hạn |
| Probe cần quyền truy cập đặc biệt | Không bỏ qua auth; cấp quyền riêng tối thiểu |
| Rollout lớn | Giới hạn rate, concurrency, jitter và số service được probe |
| Chi phí cold chỉ khoảng vài ms | Có thể không cần warm-up; tối ưu đơn giản hơn |

Ví dụ ứng dụng dùng best-effort policy có thể bắt lỗi từ probe startup:

~~~java
@Bean
ApplicationRunner optionalInventoryWarmup(WebClient inventoryWebClient) {
    return args -> {
        try {
            inventoryWebClient.get()
                    .uri("/internal/warmup")
                    .retrieve()
                    .toBodilessEntity()
                    .timeout(Duration.ofSeconds(1))
                    .block(Duration.ofSeconds(2));
        } catch (RuntimeException ex) {
            // Ghi metric và structured log theo policy ứng dụng.
            // Không coi probe thất bại là chứng cứ toàn bộ ứng dụng hỏng.
            warmupMetrics.recordFailure("inventory-service", ex);
        }
    };
}
~~~

Trong ví dụ, **warmupMetrics** là helper do ứng dụng cung cấp và cần được inject; đây là mẫu mô tả policy, không phải một class mặc định của Spring. Nếu yêu cầu hard-gate, không nuốt exception; để runner thất bại (hoặc quản lý readiness state có chủ đích) và quan sát tác động tới deployment.

### 20.2. AOT/native-image có thêm yêu cầu xác định service ID

Theo tài liệu Spring Cloud LoadBalancer, khi dùng **Spring AOT/native image**, service IDs cần được khai báo rõ qua @LoadBalancerClient hoặc thuộc tính **spring.cloud.loadbalancer.eager-load.clients** để hỗ trợ phân tích cấu hình. Điều này là một nhu cầu **khả năng tạo AOT metadata**, không đồng nghĩa tất cả client sẽ tự có connection ấm.

Không thay đổi global lazy initialization, AOT config hoặc toàn bộ danh sách service IDs chỉ vì muốn cải thiện vài request đầu; hãy xác minh ứng dụng thuộc mô hình JVM/JIT hay native image và yêu cầu tương thích cụ thể.

## 21. Bài tập: phân biệt đúng loại warm-up

### 21.1. Tình huống A: first call tới inventory-service chậm

~~~text
Ứng dụng Order đã ready
Call #1 inventory-service: 640 ms
Call #2 inventory-service: 42 ms
Call #1 payment-service:   610 ms
Call #2 payment-service:    51 ms
~~~

**Câu hỏi:** Thuộc tính nào có thể giúp giảm lazy-load context theo từng service ID?

**Đáp án:** Khai báo inventory-service và payment-service trong **spring.cloud.loadbalancer.eager-load.clients**. Tuy nhiên, chưa đủ dữ liệu để khẳng định **toàn bộ** khoảng chênh lệch sẽ biến mất, bởi TCP/TLS và backend có thể chiếm phần lớn latency.

### 21.2. Tình huống B: WebClient đã gọi HttpClient.warmup()

~~~text
Event loop/hostname resolver đã khởi tạo
Chưa có một HTTP request nào tới inventory-a:8443
~~~

**Câu hỏi:** Kết nối TCP và TLS đến Inventory đã ấm chưa?

**Đáp án:** **Chưa thể kết luận đã ấm**. API warmup() của Reactor Netty khởi tạo resources, không tự gửi request tới inventory-a. Một lần gọi HTTP thật có thể vẫn phải DNS resolve, TCP connect và TLS handshake.

### 21.3. Tình huống C: có ba instance nhưng chỉ một probe

~~~text
Discovery: [A, B, C]
LoadBalancer chọn B cho GET /internal/warmup
~~~

**Câu hỏi:** Các kết nối đến A/C có được warm không?

**Đáp án:** **Không có bảo đảm**. Probe chỉ chứng minh request đã đến B và có thể giữ connection tới B trong pool. Khi request thật chọn A hoặc C, transport có thể cần kết nối mới.

### 21.4. Tình huống D: gọi warm-up trong constructor Feign client

**Câu hỏi:** Rủi ro là gì?

**Đáp án:** Feign proxies, contexts hoặc dependencies có thể chưa khởi tạo xong, dẫn đến lỗi lifecycle; Spring Cloud OpenFeign khuyến cáo không gọi client lúc bean initialization. Hãy chuyển sang một hook sau context refresh như ApplicationRunner, có timeout và policy phù hợp.

### 21.5. Tình huống E: warm-up làm startup tăng

Giả sử trước tối ưu, startup là **2.000 ms**, first call là **700 ms**. Sau tối ưu, startup **2.400 ms**, first call **180 ms**.

**Câu hỏi:** Có nên triển khai?

**Gợi ý:** First call giảm 520 ms, nhưng startup tăng 400 ms; kết quả có thể đáng giá nếu first-request SLO quan trọng và rollout đáp ứng readiness budget. Cần đo nhiều lần, cân nhắc concurrency và xem tổng trải nghiệm/chi phí của hệ thống. Không có kết luận “luôn tốt hơn” chỉ từ hai con số.

## 22. Checklist kiểm tra cold start và warm-up

- [ ] Đã xác định rõ đang đo startup, first logical call hay first connection to origin.
- [ ] Có số liệu baseline trước warm-up, gồm P50/P95/P99 và process restart nhiều lần.
- [ ] Phân biệt Spring Cloud LoadBalancer child context với HTTP client resources.
- [ ] Khai báo đúng service IDs trong eager-load.clients nếu cần khởi tạo sớm.
- [ ] Không coi eager-load contexts là preconnect TCP/TLS.
- [ ] ServiceInstanceListSupplier có cache/health đúng chỗ, không làm dữ liệu stale quá mức.
- [ ] RestClient/RestTemplate/Feign HTTP engine và connection pool được tái sử dụng có chủ đích.
- [ ] Không tạo HttpClient/connection manager mới cho mỗi HTTP request.
- [ ] Với Reactor Netty, warmup() được subscribe, gọi trên startup thread và đúng HttpClient mà WebClient sử dụng.
- [ ] Không gọi block() trên WebFlux event loop.
- [ ] Nếu dùng HTTP probe, endpoint safe/idempotent, authenticated và có timeout rõ.
- [ ] Warm-up không dùng POST tạo đơn, thanh toán, ghi dữ liệu hay hành vi có side effect.
- [ ] Không giả định một GET probe đã kết nối mọi ServiceInstance.
- [ ] Readiness policy được chọn có chủ đích, tránh dependency startup vòng tròn.
- [ ] Không gọi Feign client trong constructor hoặc @PostConstruct khi context chưa sẵn.
- [ ] Warm-up có giới hạn concurrency/retry và kiểm soát bão traffic trong rollout.
- [ ] Có phép đo connection reuse/handshake thực, không chỉ HTTP request count.
- [ ] Test tách fake ExchangeFunction với Spring Cloud LoadBalancer integration thật.
- [ ] Xem xét cold trở lại khi instance scale-out, DNS TTL hoặc pool idle eviction.
- [ ] Không vô hiệu TLS/hostname verification chỉ để giảm latency.
- [ ] Có timeout, retry budget, health check và circuit breaker sau warm-up.
- [ ] Có metric warm-up failure, first-call latency, pool pending, no-instance và downstream latency.
- [ ] Không log token, cookie hoặc payload nhạy cảm trong probe/tracing.
- [ ] Đánh giá tác động lên startup duration, CPU, memory và chi phí kết nối sau triển khai.

## 23. Kết luận

**Cold start không phải một điểm duy nhất trên đường đi của request.** Một lời gọi Spring Cloud LoadBalancer có thể chịu chi phí của nhiều tầng: JVM/Spring context, child context per service ID, discovery/cache/health, HTTP client resources, DNS, TCP/TLS và backend. Các tầng này được khởi tạo và tái sử dụng theo vòng đời **khác nhau**.

Hai cơ chế cần nhớ:

1. **spring.cloud.loadbalancer.eager-load.clients** giúp tạo sớm child context cho những service ID quan trọng; **không tự kết nối** tới các bản sao.
2. **Reactor Netty HttpClient.warmup()** giúp chuẩn bị event loop, resolver và native resources; **không tự DNS/TCP/TLS preconnect** tới từng origin.

Nếu cần làm nóng kết nối thực, phải có một HTTP request **safe** qua đúng client, LoadBalancer và transport được dùng trong production, rồi quan sát network/connection metrics. Đây là một lựa chọn tối ưu có đánh đổi: startup dài hơn, thêm traffic vào backend và không có bảo đảm kết nối còn sống mãi.

Thiết kế tốt nhất là **đo đúng nguyên nhân, làm nóng tối thiểu cần thiết, quản lý client/pool lâu sống, giữ readiness policy hợp lý và kiểm thử cả request đầu lẫn steady-state**. Warm-up cải thiện khả năng phục vụ traffic đầu tiên nhưng không thay thế discovery đúng, timeout, retry an toàn hoặc resilience của hệ thống.

## 24. Tài liệu tham khảo

- [Spring Cloud LoadBalancer – Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): child ApplicationContext theo service ID, eager loading, ServiceInstanceListSupplier và caching.
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): spring.cloud.loadbalancer.eager-load.clients và cache TTL.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): @LoadBalanced RestTemplate, RestClient và WebClient builders.
- [Reactor Netty – HTTP Client Reference](https://projectreactor.io/docs/netty/release/reference/http-client.html): HttpClient eager initialization/warmup, DNS, pool, TCP, TLS và timeout.
- [Reactor Netty – HttpClient Javadoc](https://projectreactor.io/docs/netty/release/api/reactor/netty/http/client/HttpClient.html): HttpClient.warmup() và chính xác các resources được nạp.
- [Spring Boot – SpringApplication Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html): ApplicationRunner, ApplicationReadyEvent và ReadinessState.ACCEPTING_TRAFFIC.
- [Spring Boot – Application Availability](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-availability): readiness/liveness state và lifecycle.
- [Spring Boot – Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): HTTP client builders và cấu hình RestClient/RestTemplate/WebClient.
- [Spring Framework – WebClient Configuration](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-builder.html): ReactorClientHttpConnector và client configuration.
- [Spring Framework – WebClient Testing](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-testing.html): mock HTTP servers để kiểm thử outbound WebClient.
- [Spring Cloud OpenFeign – Reference](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html): named client contexts, eager attribute resolution và cảnh báo gọi Feign trong giai đoạn bean initialization.
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestClient, RestTemplate và ClientHttpRequestFactory.
- [Reactor – Testing](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier và subscription trong unit/integration test.
- [Micrometer – Concepts](https://docs.micrometer.io/micrometer/reference/concepts.html): timer, counters và đo latency có kiểm soát.

