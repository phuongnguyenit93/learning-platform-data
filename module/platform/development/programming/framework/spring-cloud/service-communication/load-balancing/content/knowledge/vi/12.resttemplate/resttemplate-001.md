# Vai trò của RestTemplate trong hệ thống đang sử dụng

Trong nhiều hệ thống Spring Boot đã vận hành từ trước, **RestTemplate** vẫn là thành phần thực hiện HTTP request **đồng bộ** giữa các dịch vụ: lấy thông tin tồn kho, gọi hệ thống thanh toán, đồng bộ dữ liệu hoặc trao đổi với API của bên thứ ba. Trong hệ thống dùng Spring Cloud LoadBalancer, RestTemplate còn có thể gửi request đến **service ID** thay vì địa chỉ IP/port cố định. Nhờ đó, code nghiệp vụ không cần biết bản sao nào đang chạy và LoadBalancer có thể chọn **ServiceInstance** thích hợp.

Để bảo trì hoặc nâng cấp một hệ thống như vậy, cần hiểu **RestTemplate đang đảm nhiệm trách nhiệm gì**, khi nào nó thực sự đi qua LoadBalancer, đâu là điểm giới hạn của mô hình blocking và khi nào nên chuyển sang **RestClient**, **WebClient** hoặc **OpenFeign**.

**Bối cảnh phiên bản:** Spring Framework 6.x vẫn cung cấp RestTemplate và các API quen thuộc. Tài liệu Spring Framework 7.x đã đánh dấu RestTemplate là API deprecated để ưu tiên **RestClient** cho HTTP đồng bộ; hướng đi được Spring công bố là loại bỏ trong một phiên bản lớn tương lai. Vì thế, bài này giải thích cách **hiểu, vận hành và di trú code đang có**, không coi RestTemplate là lựa chọn mặc định cho dự án mới.

## 1. RestTemplate là gì và không phải là gì?

RestTemplate nằm trong package **org.springframework.web.client** của Spring Framework. Đây là HTTP client với cách dùng theo mẫu phương thức (**template method API**). Ứng dụng gọi các phương thức như **getForObject**, **getForEntity**, **postForEntity**, **exchange** hoặc **execute**; RestTemplate xây dựng HTTP request, gửi qua một **ClientHttpRequestFactory**, chuyển đổi body bằng **HttpMessageConverter** và trả kết quả hoặc exception.

Ví dụ:

~~~java
@Service
class InventoryReader {

    private final RestTemplate restTemplate;

    InventoryReader(RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    StockResponse getStock(String sku) {
        return restTemplate.getForObject(
                "https://api.example.net/stock/{sku}",
                StockResponse.class,
                sku);
    }
}
~~~

Ở ví dụ này, RestTemplate chỉ là HTTP client đồng bộ gọi một URL cụ thể. **Không có cơ chế tự tìm service instance hoặc cân bằng tải** nếu chưa có tích hợp Spring Cloud LoadBalancer.

### Những việc RestTemplate làm

- Xây dựng HTTP request theo URL/URI, method, header và body.
- Gọi HTTP/HTTPS qua request factory đã cấu hình.
- Chuyển đổi Java object thành JSON/XML hoặc ngược lại bằng message converters.
- Trả **ResponseEntity** khi cần xem status, headers và body.
- Cho phép cấu hình interceptors, request factory, error handler và timeout.
- Có thể tích hợp với Spring Cloud LoadBalancer để biến service ID thành địa chỉ instance thật.

### Những việc RestTemplate không tự làm

- Không tự đăng ký service vào Eureka/Consul/Kubernetes.
- Không tự tải danh sách ServiceInstance từ registry khi thiếu LoadBalancer integration.
- Không mặc định retry an toàn cho mọi request hay tự bảo đảm idempotency.
- Không cung cấp I/O non-blocking; thread gọi phải đợi kết quả.
- Không thay thế circuit breaker, tracing, logging bảo mật hoặc chính sách giới hạn tải.
- Không biến mọi URL thành service ID: URL vật lý vẫn là lời gọi HTTP trực tiếp trong RestTemplate thông thường.

## 2. Tại sao RestTemplate vẫn xuất hiện trong hệ thống đang chạy?

RestTemplate được dùng phổ biến trước khi Spring giới thiệu RestClient và trước khi các microservice chuyển mạnh sang reactive stack. Một codebase đang vận hành có thể có hàng chục client phụ thuộc vào nó:

| Dạng sử dụng | Ví dụ | Vai trò của RestTemplate |
| --- | --- | --- |
| Service-to-service trong nội bộ | Order gọi Inventory | Gửi HTTP đồng bộ giữa microservice |
| API của đối tác | Billing gọi cổng hóa đơn | Trao đổi JSON với endpoint cố định |
| Đồng bộ tác vụ nền | Job cập nhật tỷ giá | Gọi HTTP trong scheduler |
| Hệ thống cũ | Ứng dụng Spring MVC | Giữ code đã ổn định, tránh nâng cấp ồ ạt |
| Cần metadata HTTP | Gọi API yêu cầu status/header | Sử dụng ResponseEntity/exchange |
| Test và mock | Unit test client adapter | Sử dụng MockRestServiceServer |

Các giá trị thực tế của RestTemplate trong hệ thống cũ:

1. **Ổn định và quen thuộc:** API đã được dùng lâu, có nhiều test và mẫu xử lý lỗi.
2. **Tích hợp sâu:** request interceptors, tracing, authentication và logging đã hình thành quy trình vận hành.
3. **Tương thích với code blocking:** Spring MVC hoặc background job không nhất thiết cần reactive end-to-end.
4. **Có thể nâng cấp dần:** code có thể tiếp tục hoạt động trong lúc từng adapter chuyển sang RestClient.

Tuy nhiên, việc giữ lại RestTemplate nên là **quyết định có quản lý**, không phải lý do bỏ qua timeout, retry hoặc nguy cơ hết thread. Những chức năng mới trong Spring HTTP clients tập trung nhiều vào RestClient/WebClient; khi vòng đời công nghệ thay đổi, cần có kế hoạch bảo trì hoặc di trú.

## 3. RestTemplate nằm ở đâu trong kiến trúc Spring Cloud LoadBalancer?

Trong kiến trúc load balancing phía client, RestTemplate là **đầu vào HTTP đồng bộ** của quy trình. Sau khi áp dụng **@LoadBalanced**, interceptor phối hợp với **BlockingLoadBalancerClient** để chọn một ServiceInstance và chuyển URI logic sang URI vật lý.

~~~mermaid
flowchart TD
    A["OrderService.getStock()"] --> B["RestTemplate gọi URI logic"]
    B --> C["LoadBalancerInterceptor"]
    C --> D["BlockingLoadBalancerClient"]
    D --> E["LoadBalancerClientFactory"]
    E --> F["ServiceInstanceListSupplier"]
    F --> G["Discovery/cache/health/filter"]
    G --> H["Danh sách ServiceInstance"]
    H --> I["RoundRobin / Random chọn instance"]
    I --> J["reconstructURI"]
    J --> K["ClientHttpRequestFactory gửi HTTP"]
    K --> L["Inventory Service instance"]
~~~

Ví dụ request logic:

~~~text
GET http://inventory-service/api/stock/BOOK-01
~~~

Registry biết:

| Service ID | Instance ID | URI vật lý |
| --- | --- | --- |
| inventory-service | inv-a | http://10.10.1.21:8080 |
| inventory-service | inv-b | http://10.10.1.22:8080 |

Nếu LoadBalancer chọn **inv-b**, HTTP connector thực sự gọi:

~~~text
GET http://10.10.1.22:8080/api/stock/BOOK-01
~~~

Từng lớp có trách nhiệm:

- **RestTemplate:** method, URL, headers, body, chuyển đổi response.
- **LoadBalancerInterceptor:** chặn request có service ID để áp dụng chọn instance.
- **BlockingLoadBalancerClient:** thực thi cơ chế chọn đích qua LoadBalancer.
- **ServiceInstanceListSupplier:** cung cấp danh sách sau discovery, cache và các bộ lọc.
- **ClientHttpRequestFactory:** mở kết nối và thực hiện I/O HTTP tới URI đã tái dựng.

RestTemplate **không trực tiếp** chọn Round Robin hay tạo danh sách từ registry. Hai nhiệm vụ này thuộc các thành phần LoadBalancer khác.

## 4. Cấu hình một RestTemplate có LoadBalancer

Spring Boot **không tự tạo RestTemplate bean chỉ vì có spring-web trên classpath**. Ứng dụng cần tự khai báo bean và gắn **@LoadBalanced** nếu muốn gọi theo service ID.

### 4.1. Dependencies

Ứng dụng cần các dependency thích hợp với phiên bản Spring Boot/Spring Cloud đang dùng:

- **spring-web** hoặc web starter phù hợp, cung cấp RestTemplate.
- **spring-cloud-starter-loadbalancer**, cung cấp Spring Cloud LoadBalancer.
- Một implementation discovery như Eureka/Consul nếu muốn registry động, hoặc cấu hình SimpleDiscoveryClient cho local.

Ví dụ Gradle cho môi trường đang dùng Spring Boot BOM và Spring Cloud BOM tương thích:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
    // Khi dùng registry thực, thêm starter của provider discovery tương ứng.
}
~~~

Tên web starter và dependency quản lý có thể khác theo các thế hệ Spring Boot. Hãy đối chiếu BOM/release train của dự án, không trộn tùy ý Spring Framework 6/7 với Spring Cloud release khác.

### 4.2. Khai báo bean

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
class LoadBalancedHttpConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate loadBalancedRestTemplate() {
        return new RestTemplate();
    }
}
~~~

Ứng dụng tiêu thụ bean:

~~~java
@Service
class InventoryClient {

    private final RestTemplate restTemplate;

    InventoryClient(@LoadBalanced RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    StockResponse getStock(String sku) {
        return restTemplate.getForObject(
                "http://inventory-service/api/stock/{sku}",
                StockResponse.class,
                sku);
    }
}
~~~

**@LoadBalanced** là điểm mấu chốt: nó đánh dấu bean cho Spring Cloud gắn interceptor LoadBalancer. URL có host **inventory-service** là URI logic. Nếu dùng một RestTemplate không có interceptor và không có DNS cho tên này, kết nối có thể báo **UnknownHostException**.

### 4.3. Khi cần cả client trực tiếp và client qua LoadBalancer

Một ứng dụng thường gọi cả service nội bộ theo service ID lẫn API đối tác theo URL cố định. Nên tách bean để tránh vô tình đưa traffic bên ngoài qua LoadBalancer:

~~~java
@Configuration(proxyBeanMethods = false)
class HttpClientsConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate loadBalancedRestTemplate() {
        return new RestTemplate();
    }

    @Bean
    @Primary
    RestTemplate directRestTemplate() {
        return new RestTemplate();
    }
}
~~~

Ví dụ constructor injection:

~~~java
@Service
class ExternalAndInternalClient {

    private final RestTemplate internalClient;
    private final RestTemplate externalClient;

    ExternalAndInternalClient(
            @LoadBalanced RestTemplate internalClient,
            @Qualifier("directRestTemplate") RestTemplate externalClient) {
        this.internalClient = internalClient;
        this.externalClient = externalClient;
    }
}
~~~

Khi có nhiều bean cùng kiểu, gắn **@Qualifier** hoặc **@LoadBalanced** ở điểm injection để rõ ý định. Đánh dấu **@Primary** cho client trực tiếp giúp injection không có qualifier chọn bean thường. Đây là ví dụ tách vai trò; có thể bổ sung tên bean và cấu hình riêng để tránh nhập nhằng.

### 4.4. Cấu hình qua RestTemplateBuilder

Ứng dụng đang dùng **RestTemplateBuilder** cũng có thể khai báo builder với **@LoadBalanced**:

~~~java
@Bean
@LoadBalanced
RestTemplateBuilder loadBalancedRestTemplateBuilder() {
    return new RestTemplateBuilder();
}
~~~

Với Spring Boot, builder được cấu hình sẵn hoặc các RestTemplateCustomizer có thể mang theo timeout, message converters và observability. Cần hiểu **builder nào đang được inject** và việc tạo builder mới có giữ các tùy chỉnh của Boot hay không. Không mặc định rằng **new RestTemplateBuilder()** có mọi customizer mà Boot đã tự cấu hình.

## 5. Những phương thức RestTemplate thường thấy

| Phương thức | Tình huống điển hình | Kết quả |
| --- | --- | --- |
| getForObject | GET, chỉ cần body | Đối tượng T |
| getForEntity | GET, cần status/headers/body | ResponseEntity<T> |
| postForObject | POST, chỉ cần body trả về | Đối tượng T |
| postForEntity | POST, cần metadata response | ResponseEntity<T> |
| put | PUT cập nhật resource | void |
| delete | DELETE resource | void |
| exchange | Tùy chỉnh method, headers, body, response type | ResponseEntity<T> |
| execute | Mức thấp, xử lý request/response callbacks | Tùy callback |

Các phương thức này dùng chung hạ tầng gửi request. Từ góc nhìn LoadBalancer, **GET hay POST vẫn cần tìm instance trước khi thực thi** nếu URI dùng service ID.

### 5.1. GET với ResponseEntity

~~~java
ResponseEntity<StockResponse> response =
        restTemplate.getForEntity(
                "http://inventory-service/api/stock/{sku}",
                StockResponse.class,
                sku);

if (response.getStatusCode().is2xxSuccessful()) {
    StockResponse stock = response.getBody();
}
~~~

Khi dùng error handler mặc định, response 4xx/5xx thường sinh exception thay vì đi tiếp tới điều kiện kiểm tra status; không viết code giả định tất cả status đều trả ResponseEntity bình thường.

### 5.2. POST với body và header

~~~java
HttpHeaders headers = new HttpHeaders();
headers.setContentType(MediaType.APPLICATION_JSON);
headers.set("Idempotency-Key", operationId);

ReserveRequest payload = new ReserveRequest(sku, quantity);
HttpEntity<ReserveRequest> entity = new HttpEntity<>(payload, headers);

ResponseEntity<ReserveResponse> result = restTemplate.exchange(
        "http://inventory-service/api/reservations",
        HttpMethod.POST,
        entity,
        ReserveResponse.class);
~~~

RestTemplate có thể gửi header tùy chỉnh và JSON body như một HTTP client thông thường. **Idempotency-Key** ở đây là hợp đồng do hệ thống tự triển khai, không phải chức năng tự có của RestTemplate hay Spring Cloud LoadBalancer. Server phải lưu và xử lý key để tránh tác dụng phụ khi retry.

### 5.3. Generic response type

Khi API trả danh sách DTO hoặc kiểu generic, sử dụng **ParameterizedTypeReference**:

~~~java
ResponseEntity<List<StockResponse>> response = restTemplate.exchange(
        "http://inventory-service/api/stock",
        HttpMethod.GET,
        HttpEntity.EMPTY,
        new ParameterizedTypeReference<List<StockResponse>>() {});

List<StockResponse> items = response.getBody();
~~~

Cách này giúp message converter giữ thông tin kiểu generic cần thiết, thay vì deserialize một cách mơ hồ sang List<Map>.

## 6. Điều gì xảy ra khi RestTemplate nhận HTTP 4xx/5xx?

RestTemplate dùng **ResponseErrorHandler** để quyết định response nào bị coi là lỗi. Với error handler mặc định:

- HTTP **4xx** thường ném **HttpClientErrorException**.
- HTTP **5xx** thường ném **HttpServerErrorException**.
- Một số lỗi giao thức hoặc kiểu status khác được báo qua nhánh exception tương ứng.
- Lỗi mạng, DNS, TLS hoặc timeout có thể được bọc trong **ResourceAccessException**.

Ví dụ phân loại lỗi ở client:

~~~java
try {
    return restTemplate.getForObject(
            "http://inventory-service/api/stock/{sku}",
            StockResponse.class,
            sku);
} catch (HttpClientErrorException.NotFound e) {
    throw new StockNotFoundException(sku, e);
} catch (HttpServerErrorException e) {
    throw new InventoryUnavailableException("Inventory returned 5xx", e);
} catch (ResourceAccessException e) {
    throw new InventoryUnavailableException("Inventory transport failure", e);
}
~~~

Điều cần phân biệt trong thiết kế:

| Loại lỗi | Ví dụ | Nguyên nhân có thể |
| --- | --- | --- |
| 404 | SKU không tồn tại | Lỗi nghiệp vụ hoặc path sai |
| 400/422 | Dữ liệu không hợp lệ | Contract/schema request |
| 401/403 | Không có quyền | Token, scope, policy |
| 429 | Rate limit | Downstream quá tải/chính sách |
| 502/503/504 | Gateway/downstream unavailable | Hạ tầng, timeout, không có instance |
| ResourceAccessException | Connection refused, timeout | Transport, TLS, DNS hoặc mạng |

Không tự động retry tất cả 4xx. **404/400/401/403** thường không phải lỗi tạm thời có thể sửa bằng retry. Một số 429 và 5xx có thể retry nhưng phải xét **Retry-After**, deadline, idempotency và chính sách tổng thể.

### 6.1. Error handler tùy biến

RestTemplate cho phép thay error handler nếu hệ thống cần chuyển đổi response lỗi thành exception domain riêng. Tuy nhiên, việc thay handler để **nuốt mọi 4xx/5xx** dễ làm mất tín hiệu lỗi và gây khó chẩn đoán. Hãy giữ thông tin status, mã lỗi downstream và trace ID, đồng thời tránh đưa body chứa dữ liệu nhạy cảm vào log.

Một chiến lược dễ bảo trì là để adapter HTTP **chuyển exception thành exception domain** theo từng endpoint; phần nghiệp vụ không phải biết chi tiết HttpServerErrorException hoặc ResourceAccessException.

## 7. Timeout và blocking I/O phải được xác định rõ

RestTemplate là client đồng bộ. Nếu downstream mất nhiều giây mới trả lời, **thread gọi RestTemplate phải chờ** tương ứng. Trong Spring MVC, điều này thường giữ một request-processing thread; trong batch/job, nó giữ worker thread. Số lượng request đồng thời lớn cộng với timeout dài có thể làm pool thread cạn kiệt.

Không mặc định rằng framework đã thiết lập connect timeout, read timeout và deadline phù hợp với SLO của dịch vụ. Cần xác định rõ:

- **Connect timeout:** thời gian chờ thiết lập kết nối.
- **Read/response timeout:** thời gian chờ dữ liệu trả về sau khi kết nối, tùy request factory/HTTP library.
- **Connection-pool acquisition timeout:** thời gian chờ lấy kết nối từ pool khi pool cạn.
- **End-to-end deadline:** tổng ngân sách thời gian, gồm discovery, chọn instance, kết nối, response và retry.

Ví dụ đơn giản cấu hình RestTemplate với request factory:

~~~java
@Bean
@LoadBalanced
RestTemplate loadBalancedRestTemplate() {
    SimpleClientHttpRequestFactory factory =
            new SimpleClientHttpRequestFactory();
    factory.setConnectTimeout(Duration.ofSeconds(2));
    factory.setReadTimeout(Duration.ofSeconds(5));
    return new RestTemplate(factory);
}
~~~

Đoạn này minh họa API trong các phiên bản Spring Framework gần đây, với import **java.time.Duration** và **SimpleClientHttpRequestFactory**. Hành vi timeout thực tế phụ thuộc HTTP engine; production có thể dùng Apache HttpComponents hoặc request factory khác với connection pooling.

**Read timeout không phải luôn là deadline toàn bộ request.** Nếu server gửi từng chunk mà không hoàn tất, thời gian tổng có thể dài hơn read timeout. Khi bật retry, phải tính tổng số lần thử cùng backoff. Có thể xảy ra trạng thái downstream đã hoàn thành nghiệp vụ nhưng client timeout khi nhận response.

## 8. Retry, timeout và service instance lựa chọn lại

Spring Cloud LoadBalancer có cơ chế retry riêng cho một số tích hợp HTTP client. Khi được bật với các dependency và policy phù hợp, retry có thể **chọn lại ServiceInstance**. Bản thân RestTemplate không bảo đảm một retry policy đúng cho mọi request.

Ví dụ:

~~~text
Lần gọi 1:
  serviceId = inventory-service
  instance = inventory-a:8080
  HTTP POST /reservations
  client timeout trước khi nhận response

Lần gọi 2:
  LoadBalancer có thể chọn inventory-b:8080
  HTTP POST /reservations
~~~

Không thể kết luận lần 1 chưa thành công chỉ vì client timeout. Với POST tạo reservation, nếu backend không khử trùng theo idempotency key, hai lần gọi có thể tạo hai reservation.

Khi đánh giá retry trong hệ thống cũ:

1. **Kiểm tra nơi bật retry:** RestTemplate interceptor, Spring Retry, Spring Cloud LoadBalancer, circuit-breaker wrapper hoặc service mesh.
2. **Tránh retry lồng nhau không kiểm soát:** hai tầng retry có thể nhân số lần gọi thực tế.
3. **Chỉ retry điều kiện phù hợp:** timeout/503 có thể tạm thời; lỗi validate thường không.
4. **Giới hạn attempts và tổng deadline:** để caller không giữ thread quá lâu.
5. **Dùng backoff/jitter có giới hạn:** giảm retry storm khi downstream đang lỗi.
6. **Đảm bảo idempotency:** nhất là POST hoặc thao tác ghi tài chính.
7. **Quan sát instance trước và sau retry:** retry có thể chuyển đích, không mặc định luôn cùng instance.

**Không thử lại một thao tác chỉ vì HTTP method là PUT/DELETE** nếu ứng dụng thực hiện side effect ngoài contract hoặc trạng thái hệ thống không bảo đảm an toàn. Ngữ nghĩa HTTP và tính lũy đẳng nghiệp vụ phải được thiết kế đồng bộ.

## 9. ClientHttpRequestFactory quyết định cách giao tiếp trên mạng

RestTemplate là lớp API ở trên; HTTP engine thực sự được cung cấp bởi **ClientHttpRequestFactory**. Khi đọc hệ thống đang sử dụng RestTemplate, cần tìm cả cấu hình request factory vì nó ảnh hưởng trực tiếp tới:

- Kết nối TCP/TLS và DNS lookup.
- Connect timeout, read timeout và lựa chọn HTTP version.
- Quản lý connection pool, keep-alive và reuse connection.
- Proxy, xác thực proxy, truststore và mTLS.
- Kiểm soát redirect và một số đặc tính của HTTP client implementation.

| Thành phần | Vai trò |
| --- | --- |
| RestTemplate | API đồng bộ và quy trình gửi/nhận HTTP |
| ClientHttpRequestFactory | Khởi tạo kết nối và request thật |
| ClientHttpRequestInterceptor | Bổ sung/chặn request, ví dụ tracing hoặc header |
| HttpMessageConverter | Chuyển Java object ↔ body HTTP |
| ResponseErrorHandler | Phân loại response HTTP lỗi |
| Spring Cloud LoadBalancer interceptor | Chọn instance và thay URI logic |

Ví dụ, **SimpleClientHttpRequestFactory** là lựa chọn đơn giản dựa trên hạ tầng JDK. Với lượng request lớn hoặc cần cấu hình pool cụ thể, có thể dùng factory phù hợp với Apache HttpComponents hoặc JDK HttpClient, tùy phiên bản Spring Framework.

Không nên mặc định rằng thay request factory chỉ làm thay đổi hiệu năng. Một số hành vi về timeout, redirect, cookie, TLS, header và cách truyền request body có thể khác nhau. Khi thay factory trong quá trình di trú, phải chạy regression test ở tầng HTTP thật.

### 9.1. Dùng chung RestTemplate như bean đã cấu hình

RestTemplate thường được khai báo là một bean dùng lại thay vì tạo mới ở mỗi request. Điều này giúp tái sử dụng interceptors, converters, observability và HTTP connection infrastructure.

Một RestTemplate đã khởi tạo có thể được gọi đồng thời từ nhiều thread **khi không thay đổi cấu hình trong lúc sử dụng** và khi request factory phía dưới phù hợp. Không nên mỗi request lại gọi setInterceptors(), setRequestFactory(), setErrorHandler() hoặc thêm converter vào một bean singleton đang được sử dụng; những thay đổi runtime này dễ gây race condition.

Khi cần các cấu hình khác nhau cho từng downstream, tạo các bean/client adapter riêng với timeout, headers, authorization và pool phù hợp.

## 10. Interceptor, truyền header và bảo mật

Trong microservice, RestTemplate hiếm khi chỉ mang path và body. Ứng dụng thường có request interceptor để thêm:

- Authorization hoặc token theo downstream.
- Trace context như W3C traceparent.
- Correlation ID.
- Header tenant hoặc API version theo contract.
- Header idempotency cho request ghi.
- Logging có che dữ liệu nhạy cảm.

Ví dụ một interceptor bổ sung header từ giá trị an toàn được truyền ở request context:

~~~java
class CorrelationIdInterceptor implements ClientHttpRequestInterceptor {

    @Override
    public ClientHttpResponse intercept(
            HttpRequest request,
            byte[] body,
            ClientHttpRequestExecution execution) throws IOException {

        String correlationId = CorrelationContext.currentId();
        if (correlationId != null && !correlationId.isBlank()) {
            request.getHeaders().set("X-Correlation-Id", correlationId);
        }

        return execution.execute(request, body);
    }
}
~~~

**CorrelationContext** là helper minh họa do ứng dụng cung cấp, không phải class có sẵn trong Spring. Trong production, nên dùng propagation của tracing/observability infrastructure khi có sẵn thay vì tự tạo header trùng lặp.

Đăng ký interceptor:

~~~java
@Bean
@LoadBalanced
RestTemplate loadBalancedRestTemplate() {
    RestTemplate restTemplate = new RestTemplate();
    restTemplate.getInterceptors().add(new CorrelationIdInterceptor());
    return restTemplate;
}
~~~

### 10.1. Thứ tự interceptor ảnh hưởng điều quan sát được

Spring Cloud có thể bổ sung **LoadBalancerInterceptor** vào danh sách interceptor của RestTemplate. Nếu interceptor tự viết ghi **request.getURI()**, nó có thể quan sát URI logic hoặc URI vật lý tùy cách các lớp được sắp xếp và thời điểm logging.

Vì vậy:

- Không suy luận rằng URL trong một log interceptor luôn là IP/port cuối cùng.
- Khi cần biết instance được chọn, dùng LoadBalancer lifecycle/các metric tương ứng hoặc ghi nhận ở phía server.
- Không tự thêm nhiều LoadBalancerInterceptor trùng nhau.
- Không thay đổi interceptors sau khi bean đã được ứng dụng dùng đồng thời.

### 10.2. Không sao chép header nhạy cảm một cách mù quáng

Nếu gọi một service khác, không nên tự động sao chép toàn bộ headers của request inbound sang request outbound. Cookie phiên người dùng, Authorization hoặc X-Forwarded-* có thể không thuộc hợp đồng của downstream. Chỉ truyền header đã được cho phép và hợp lệ về bảo mật.

Với URL bên ngoài, tránh dùng RestTemplate đã cấu hình token nội bộ mặc định. **Tách RestTemplate nội bộ và bên ngoài** giúp giảm nguy cơ gửi nhầm credential.

### 10.3. Logging có kiểm soát

Không log nguyên Authorization, Cookie, query chứa token, thông tin thẻ hoặc toàn bộ request/response body. Một log outbound hữu ích thường chứa:

~~~text
traceId | serviceId | instanceId | method | path template | status | durationMs
~~~

Tùy công cụ, instanceId có thể chưa sẵn trong interceptor RestTemplate cơ bản. Nếu cần dữ liệu LoadBalancer chính xác, sử dụng hook/observability phù hợp thay vì tự suy đoán từ tên host.

## 11. Observability: đo RestTemplate ở đúng lớp

Trong hệ thống nhiều service, cùng một HTTP lỗi có thể xuất phát ở các tầng khác nhau:

~~~text
Business Service
    ↓
RestTemplate
    ↓
LoadBalancerInterceptor
    ↓
Discovery + ServiceInstanceListSupplier
    ↓
Chọn ServiceInstance
    ↓
ClientHttpRequestFactory
    ↓
Network / TLS / Backend
~~~

Để chẩn đoán, nên tách các tín hiệu:

| Tín hiệu | Trả lời câu hỏi |
| --- | --- |
| Service ID | Downstream logic nào đang được gọi? |
| Instance ID/host:port | Bản sao nào đã được chọn? |
| HTTP method/path template | API nào gặp lỗi? |
| HTTP status | Backend trả lỗi 4xx/5xx hay không? |
| IOException/timeout/TLS error | Lỗi ở transport trước khi có HTTP response? |
| Request duration | Bao nhiêu thời gian bị tiêu hao? |
| Retry attempt | Đây là lần thử thứ mấy? |
| Trace ID | Request liên quan xuyên qua những service nào? |
| Cache/health state | Danh sách instance có mới và khỏe không? |

Spring Boot và Spring Framework có hỗ trợ observability thông qua Micrometer Observation, còn Spring Cloud LoadBalancer cung cấp lifecycle callbacks và tích hợp metric tùy cấu hình/phiên bản. Nếu ứng dụng tạo RestTemplate thủ công bằng **new RestTemplate()**, cần kiểm tra xem các customizer/observation registry của Boot đã thực sự được áp dụng chưa.

Một cách tiếp cận tốt là dùng builder do Boot quản lý hoặc cấu hình RestTemplate có chủ đích, sau đó xác minh trace và HTTP client metrics trong môi trường thử nghiệm.

**Không tự nhận mọi lỗi 503 là lỗi của LoadBalancer.** Một service instance có thể được chọn đúng nhưng downstream vẫn trả 503 vì quá tải. Ngược lại, khi không có instance, LoadBalancer có thể trả lỗi trước khi kết nối mạng thật.

## 12. Kiểm thử client RestTemplate mà không gọi dịch vụ thật

### 12.1. Unit test với MockRestServiceServer

Spring Test cung cấp **MockRestServiceServer** để kiểm thử REST client ở mức request/response mà không cần chạy một HTTP server. Ví dụ kiểm tra adapter dùng RestTemplate thông thường:

~~~java
@Test
void fetchesStockFromHttpEndpoint() {
    RestTemplate restTemplate = new RestTemplate();

    MockRestServiceServer server =
            MockRestServiceServer.bindTo(restTemplate).build();

    server.expect(requestTo(
                    "https://api.example.net/stock/BOOK-01"))
            .andExpect(method(HttpMethod.GET))
            .andRespond(withSuccess(
                    "{\"sku\":\"BOOK-01\",\"available\":7}",
                    MediaType.APPLICATION_JSON));

    InventoryReader client = new InventoryReader(restTemplate);

    StockResponse result = client.getStock("BOOK-01");

    assertEquals("BOOK-01", result.sku());
    assertEquals(7, result.available());
    server.verify();
}
~~~

Trong ví dụ này, **StockResponse** là DTO/record của ứng dụng:

~~~java
record StockResponse(String sku, int available) {}
~~~

Các import của JUnit, MockRestServiceServer và static helpers **requestTo**, **method**, **withSuccess** cần được bổ sung trong project test. Đoạn test minh họa đúng việc RestTemplate gửi GET và deserialize JSON; nó không kiểm chứng chọn instance qua LoadBalancer.

### 12.2. Kiểm thử riêng LoadBalancer integration

Muốn kiểm tra **service ID → ServiceInstance → URI vật lý**, cần một bài test tích hợp khác:

1. Khai báo danh sách tĩnh inventory-service bằng SimpleDiscoveryClient, hoặc dùng registry test.
2. Chạy hai stub HTTP server ở hai port khác nhau, mỗi server trả **instanceId** riêng.
3. Dùng RestTemplate có **@LoadBalanced** và gửi request tới **http://inventory-service/...**.
4. Xác minh request đến một trong hai địa chỉ vật lý và không phải cố DNS-resolve inventory-service.
5. Tắt một server hoặc thay supplier, quan sát hành vi lỗi/health/cache/retry.

Ví dụ application-test.yml dùng hai instance tĩnh:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

**SimpleDiscoveryClient** không phát hiện server tự động. Nếu dừng port 8081 mà vẫn giữ cấu hình, LoadBalancer có thể tiếp tục chọn nó cho đến khi nguồn instance/health được cập nhật. Đó không phải lỗi RestTemplate.

### 12.3. Kiểm tra lỗi mạng bằng mock HTTP server

Để kiểm chứng timeout, connection reset, TLS hoặc redirect, **WireMock** hoặc **MockWebServer** thường phù hợp hơn MockRestServiceServer, vì chúng dùng một HTTP server mô phỏng thật ở tầng mạng. Tài liệu Spring Framework cũng khuyến nghị cân nhắc mock HTTP server cho các bài kiểm tra transport đầy đủ.

Không nên chỉ dùng MockRestServiceServer rồi kết luận đã kiểm thử connect timeout hoặc connection pool thật.

## 13. Khi nào nên giữ RestTemplate, khi nào nên thay?

Spring Framework hiện cung cấp các lựa chọn HTTP client khác nhau:

| Công cụ | Kiểu API | Mô hình I/O | Phù hợp |
| --- | --- | --- | --- |
| RestTemplate | Template methods | Blocking | Code Spring cũ đang ổn định, cần bảo trì |
| RestClient | Fluent API | Blocking | HTTP client mới trong Spring MVC/job đồng bộ |
| WebClient | Fluent reactive | Non-blocking | WebFlux, streaming hoặc concurrency cao |
| OpenFeign | Interface có annotation | Thường blocking trong tích hợp Spring Cloud OpenFeign | Client declarative theo service ID |
| HTTP Service Client | Java interface với @HttpExchange | Theo adapter RestClient/WebClient | Contract type-safe và giảm boilerplate |

**RestClient không phải WebClient.** RestClient vẫn là synchronous HTTP client, nhưng có API hiện đại hơn RestTemplate và có thể dùng chung request factory, interceptors, message converters.

Một hệ thống không cần reactive hoàn toàn chỉ vì muốn bỏ RestTemplate. Với ứng dụng Spring MVC đồng bộ, **RestClient** là hướng chuyển đổi tự nhiên. Với WebFlux hoặc luồng stream/non-blocking thực sự, **WebClient** phù hợp hơn khi toàn bộ pipeline được thiết kế tránh blocking.

### 13.1. Khi còn có thể giữ RestTemplate

- Ứng dụng đang ở Spring Framework 6.x, có nhiều client cũ và test ổn định.
- Chưa có yêu cầu đổi API hoặc đang ưu tiên xử lý lỗi vận hành.
- Việc di trú ngay kéo theo thay đổi lớn về error handling, authentication hoặc transport.
- Có kế hoạch kỹ thuật rõ ràng và theo dõi vòng đời framework.

Giữ RestTemplate không đồng nghĩa giữ nguyên mọi cấu hình cũ. Timeout, retry, observability, credential handling và dependency support cần được rà soát trước.

### 13.2. Khi nên ưu tiên di trú

- Dự án đang chuyển sang Spring Framework 7.x hoặc chuẩn bị cho phiên bản sau.
- Đội ngũ phát triển client API mới hoặc có thể nâng cấp từng adapter.
- Muốn tiêu chuẩn hóa HTTP client và giảm code dùng API đã deprecated.
- Cần dùng tính năng mới được phát triển chủ yếu ở RestClient.
- Nhiều request bị nghẽn thread do blocking; lúc đó cần đánh giá kiến trúc WebClient, không chỉ thay tên class.

## 14. Lộ trình chuyển RestTemplate sang RestClient không gây gián đoạn

Spring Framework khuyến nghị chuyển dần theo component. **RestClient.create(restTemplate)** cho phép tạo RestClient với nhiều cấu hình được kế thừa từ RestTemplate sẵn có, hữu ích để đổi cú pháp gọi trước khi thay toàn bộ hạ tầng HTTP.

### 14.1. Bước 1: vẽ bản đồ client hiện có

Với từng bean RestTemplate, ghi lại:

| Nội dung kiểm kê | Ví dụ |
| --- | --- |
| Bean name / qualifier | loadBalancedRestTemplate |
| Các service đang sử dụng | InventoryClient, PaymentClient |
| Đích gọi | service ID hoặc URL đối tác |
| Request factory | JDK/Apache HttpComponents |
| Interceptors | auth, tracing, correlation |
| Message converters | JSON, form, XML |
| Error handler | mặc định hoặc tùy chỉnh |
| Timeout | connect/read/pool acquisition |
| Retry/circuit breaker | tầng nào và điều kiện nào |
| Observability | client metrics, trace propagation |
| Regression tests | HTTP contract, LB, timeout, auth |

Việc kiểm kê tránh trường hợp chuyển syntax sang RestClient nhưng làm mất một interceptor quan trọng hoặc vô tình chuyển từ HTTP engine có connection pool sang engine khác.

### 14.2. Bước 2: đổi cú pháp trong từng adapter

RestTemplate hiện có:

~~~java
StockResponse stock = restTemplate.getForObject(
        "http://inventory-service/api/stock/{sku}",
        StockResponse.class,
        sku);
~~~

Có thể tạo RestClient từ bean RestTemplate đã được cấu hình:

~~~java
RestClient restClient = RestClient.create(restTemplate);

StockResponse stock = restClient.get()
        .uri("http://inventory-service/api/stock/{sku}", sku)
        .retrieve()
        .body(StockResponse.class);
~~~

Hoặc với RestClient.Builder được tích hợp LoadBalancer:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder();
}
~~~

Sau đó sử dụng builder trong client adapter:

~~~java
@Service
class InventoryRestClient {

    private final RestClient restClient;

    InventoryRestClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    StockResponse getStock(String sku) {
        return restClient.get()
                .uri("http://inventory-service/api/stock/{sku}", sku)
                .retrieve()
                .body(StockResponse.class);
    }
}
~~~

**Lưu ý:** RestClient.create(restTemplate) giúp tái sử dụng cấu hình hiện có theo khả năng của framework, nhưng không thay thế regression test. Cần xác minh interceptor LoadBalancer, timeout, error handling, message converters và observability tiếp tục vận hành tương đương.

### 14.3. Bước 3: kiểm tra khác biệt hành vi

Trong giai đoạn chạy song song:

1. So sánh method, URI, headers, body của request.
2. So sánh cách URI logic được biến thành URI vật lý.
3. Kiểm tra mapping lỗi 4xx/5xx, timeout, exception và retry.
4. Kiểm tra JSON serialization/deserialization, generic types và status handling.
5. So sánh proxy, redirect, TLS và connection pooling.
6. Kiểm tra trace propagation và client metrics.
7. Chạy contract test với downstream và đánh giá latency/tỷ lệ lỗi.

Đặc biệt, **RestClient và RestTemplate có thể chọn request factory mặc định khác nhau** nếu không có thư viện HTTP nào bổ sung trên classpath. Không giả định hành vi mạng giống nhau chỉ vì cú pháp gọi mới ngắn hơn.

### 14.4. Bước 4: chuyển cấu hình sang RestClient.Builder

Sau khi các adapter đã dùng RestClient, mới nên chuẩn hóa cấu hình builder, HTTP factory, auth, observability và các policy dùng chung. Khi hoàn tất, xóa những bean RestTemplate không còn được sử dụng và cập nhật test/monitoring.

Không cần chuyển tất cả client trong một lần release. Có thể chia theo downstream ít rủi ro trước, rồi đến payment/order hoặc API có side effect sau khi đã kiểm chứng đầy đủ.

## 15. Các lỗi thường gặp trong hệ thống RestTemplate cũ

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm tra |
| --- | --- | --- |
| UnknownHostException: inventory-service | Đang inject RestTemplate không có @LoadBalanced | Kiểm tra đúng bean/qualifier và interceptor |
| Không có bean RestTemplate | Chưa khai báo @Bean hoặc config không được scan | Kiểm tra bean definitions, cấu hình ứng dụng |
| No instances available | Discovery/supplier không trả instance | Kiểm tra service ID, registry, cache, health |
| Lỗi SSLHandshakeException | TLS/certificate/SNI không phù hợp | Kiểm tra scheme của instance và truststore |
| Thời gian phản hồi cao | Downstream chậm hoặc timeout quá dài | Đo latency, phân loại connect/read/pool wait |
| Hết worker threads | Nhiều RestTemplate call chặn thread | Kiểm tra thread dump, pool, concurrency, timeout |
| 4xx/5xx không như mong đợi | DefaultResponseErrorHandler sinh exception | Kiểm tra exception mapping và error handler |
| Request thiếu trace/auth header | Bean được tạo ngoài builder/customizer hoặc interceptor bị thiếu | Kiểm tra danh sách interceptors thực tế |
| Một POST được xử lý hai lần | Retry sau timeout nhưng thiếu idempotency | Kiểm tra retry layers, server deduplication |
| URI logic không được tái dựng | Chưa có Spring Cloud LoadBalancer hoặc dùng client trực tiếp | Kiểm tra dependency và @LoadBalanced |
| Chuyển RestClient xong lỗi khác | Khác request factory, interceptors, status handling | So sánh HTTP wire data và regression tests |
| Log có token trong URL | Ghi nguyên query/header | Redact query, credentials và body nhạy cảm |

### Quy trình điều tra tối thiểu

~~~text
1. RestTemplate bean nào được inject?
2. Bean đó có @LoadBalanced và interceptor đúng không?
3. Request dùng service ID hay URL vật lý?
4. Supplier/discovery có instance nào?
5. LoadBalancer chọn instance nào?
6. URI vật lý là gì và HTTP request được gửi thế nào?
7. Lỗi xảy ra ở connect, read, TLS, status hay deserialize?
8. Có retry? Tổng số lần gọi thực tế là bao nhiêu?
~~~

Quy trình này tách lỗi ở lớp RestTemplate khỏi lỗi discovery, lỗi LoadBalancer và lỗi downstream.

## 16. Bài thực hành: nhận diện vai trò RestTemplate đang dùng

### Kịch bản

Một ứng dụng order-service dùng hai client:

- **InventoryClient** gọi nội bộ **inventory-service** qua service ID.
- **PartnerCatalogClient** gọi **https://api.partner.example/catalog** qua URL cố định.

Yêu cầu: cả hai đều dùng RestTemplate nhưng có cấu hình độc lập, và chỉ InventoryClient sử dụng LoadBalancer.

### Thiết lập

1. Thêm Spring Web và Spring Cloud LoadBalancer starter phù hợp với BOM.
2. Khai báo **@LoadBalanced RestTemplate** cho InventoryClient.
3. Khai báo một **RestTemplate trực tiếp** cho PartnerCatalogClient.
4. Cấu hình timeout riêng cho mỗi client.
5. Dùng SimpleDiscoveryClient local để khai báo hai bản sao Inventory.
6. Tạo endpoint GET /api/stock/{sku} trả về SKU và instanceId.
7. Gửi nhiều request, ghi lại instanceId và kiểm tra đường đi.

Ví dụ danh sách instance:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

Kết quả cần quan sát:

| Lời gọi | URI trong code | Đường thực thi |
| --- | --- | --- |
| InventoryClient.getStock() | http://inventory-service/api/stock/BOOK-01 | LoadBalancer chọn localhost:8081 hoặc :8082 |
| PartnerCatalogClient.getItem() | https://api.partner.example/catalog/BOOK-01 | Direct HTTP đến host đối tác |

Thử bỏ @LoadBalanced ở Inventory bean rồi chạy lại để thấy khác biệt giữa service ID logic và hostname mà hệ thống DNS biết. Sau đó khôi phục cấu hình đúng.

### Các tình huống kiểm chứng thêm

- Dừng một instance nhưng vẫn giữ nó trong SimpleDiscoveryClient để quan sát rủi ro danh sách tĩnh stale.
- Thay timeout ngắn để phân biệt ResourceAccessException với lỗi HTTP response.
- Thêm interceptor ghi correlation ID và kiểm tra header xuất hiện ở stub server.
- Gọi một endpoint trả 404 để xem default error handler xử lý.
- Dùng RestClient.create(restTemplate) và chạy lại cùng bộ contract tests.
- Tạo một POST có idempotency key, kiểm tra hành vi khi response bị trễ nhưng server đã hoàn thành nghiệp vụ.

## 17. Checklist cho đội bảo trì

- [ ] Biết RestTemplate đang phục vụ những downstream nào và bean nào đang được inject.
- [ ] Phân biệt RestTemplate trực tiếp và RestTemplate có @LoadBalanced.
- [ ] Có starter LoadBalancer và discovery source tương ứng nếu gọi bằng service ID.
- [ ] Đã cấu hình connect/read/pool timeout cùng deadline tổng thích hợp.
- [ ] Biết HTTP request factory thực sự đang được sử dụng.
- [ ] Hiểu cách default error handler ánh xạ 4xx/5xx thành exception.
- [ ] Tránh retry lồng nhau; thao tác có side effect có cơ chế idempotency.
- [ ] Không làm mất auth/trace/interceptors khi tạo bean hoặc migrate.
- [ ] Không log credential, cookie, token hoặc query chứa dữ liệu nhạy cảm.
- [ ] Có unit test cho client adapter và test tích hợp cho load balancing/transport.
- [ ] Có metric/trace để phân biệt lỗi discovery, HTTP và backend.
- [ ] Đã đánh giá vòng đời RestTemplate trong Spring Framework 7.x.
- [ ] Có lộ trình chuyển dần sang RestClient hoặc WebClient khi phù hợp.

## 18. Kết luận

**RestTemplate là HTTP client đồng bộ lâu đời, vẫn có vai trò quan trọng trong hệ thống Spring đang vận hành.** Nó tạo và thực hiện request, serialize/deserialize body, hỗ trợ interceptor và error handling. Khi được cấu hình **@LoadBalanced**, RestTemplate trở thành một đầu vào của **Spring Cloud LoadBalancer**: gọi bằng service ID, nhờ discovery và ServiceInstanceListSupplier tìm ứng viên, chọn một instance rồi tái dựng URI vật lý.

Hiểu được sự phân chia trách nhiệm này giúp đội bảo trì xử lý lỗi đúng tầng: RestTemplate phụ trách HTTP client; LoadBalancer phụ trách chọn instance; discovery phụ trách thông tin bản sao; request factory phụ trách transport. Với hệ thống mới hoặc đang nâng cấp Spring Framework, **RestClient** là lựa chọn ưu tiên cho HTTP blocking, trong khi **WebClient** phù hợp cho luồng non-blocking/reactive.

Thay vì thay toàn bộ RestTemplate một lần, nên **kiểm kê cấu hình, củng cố timeout/retry/observability, xây dựng contract tests rồi di trú từng client**, bảo đảm không mất chức năng load balancing hoặc hành vi bảo mật sẵn có.

## 19. Tài liệu tham khảo

- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): RestTemplate, RestClient, WebClient, error handling và hướng dẫn di trú sang RestClient.
- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): @LoadBalanced RestTemplate, BlockingLoadBalancerClient và cấu hình nhiều bean.
- [Spring Cloud LoadBalancer Reference](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ServiceInstanceListSupplier, retry, request transformer và các tùy chọn LoadBalancer.
- [Spring Boot – Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): RestTemplateBuilder, cấu hình HTTP clients và khả năng tái sử dụng infrastructure.
- [Spring Framework – Testing Client Applications](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-client.html): MockRestServiceServer và mock HTTP server.
- [The State of HTTP Clients in Spring](https://spring.io/blog/2025/09/30/the-state-of-http-clients-in-spring/): giải thích lý do ngừng phát triển RestTemplate và định hướng RestClient.
- [New in Spring 6.1: RestClient](https://spring.io/blog/2023/07/13/new-in-spring-6-1-restclient/): cách tạo RestClient từ RestTemplate và mẫu sử dụng fluent API.
