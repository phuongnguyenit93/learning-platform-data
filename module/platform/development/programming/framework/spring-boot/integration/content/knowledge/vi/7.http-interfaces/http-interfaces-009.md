# Phân biệt HTTP interface của Spring với OpenFeign và thư viện bên ngoài

## 1. Bối cảnh: một hợp đồng HTTP nhưng có nhiều cách viết client

Trong một ứng dụng **Spring Boot Integration**, service đặt hàng thường phải gọi API tồn kho, bảng giá hoặc vận chuyển qua HTTP, đồng thời ghi cơ sở dữ liệu, cập nhật cache Redis và phát sự kiện cho Kafka/RabbitMQ. Khi tự viết `RestClient` hoặc `WebClient`, mỗi lời gọi có thể lặp lại cách ghép URL, header, parse JSON và chuyển đổi lỗi. **Declarative HTTP client** cho phép mô tả HTTP request ngay trên các phương thức Java interface và để một thư viện tạo mã gọi HTTP thực tế.

Hệ sinh thái Spring có một số lựa chọn dễ bị đánh đồng:

- **Spring Framework HTTP interface**: cơ chế lõi từ Spring Framework 6, dùng `@HttpExchange`, `@GetExchange`, `@PostExchange`... và `HttpServiceProxyFactory`, ủy quyền thao tác mạng cho HTTP client được cấu hình.
- **Spring Cloud OpenFeign**: tích hợp Spring Cloud với thư viện OpenFeign/Feign, thường dùng `@FeignClient`, `@GetMapping`, `@PostMapping`, có hệ thống cấu hình và extension riêng.
- **Thư viện ngoài**: Feign core, Retrofit, MicroProfile Rest Client hoặc client sinh từ OpenAPI; mỗi giải pháp có annotation, cơ chế transport, serializer và lifecycle riêng.

Đây là **các cách triển khai client gửi HTTP**. Không có lựa chọn nào tự bảo đảm một API đối tác luôn khỏe, transaction phân tán an toàn hoặc xử lý trùng lặp đúng. Những điều đó vẫn cần timeout, retry có giới hạn, circuit breaker, bulkhead, idempotency, kiểm thử và observability.

Sau bài học, bạn có thể giải thích khi nào nên chọn HTTP interface gốc của Spring, khi nào một hệ thống đã dùng OpenFeign nên tiếp tục dùng nó, cách đặt timeout/đăng ký bean, và cách chuyển đổi mà không làm thay đổi hợp đồng HTTP.

## 2. Làm rõ các thuật ngữ

### 2.1. HTTP interface của Spring là gì?

**HTTP interface** là một Java interface có các annotation mô tả HTTP exchange. Chẳng hạn:

```java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange(url = "/api/inventory", accept = "application/json")
public interface InventoryHttpApi {

    @GetExchange("/{sku}")
    InventoryResponse getAvailability(@PathVariable("sku") String sku);
}

record InventoryResponse(String sku, boolean available, long version) {}
```

Annotation khai báo **contract client**: đường dẫn, method, content type, tham số và kiểu dữ liệu trả về. Nó **không biến interface thành controller** hay mở một HTTP endpoint trên server. Muốn gọi mạng, ứng dụng cần tạo proxy cho interface bằng `HttpServiceProxyFactory` và kết nối proxy với client có cấu hình thực sự.

Spring Framework hỗ trợ các annotation phổ biến:

| Annotation | Ý nghĩa chính | Ví dụ |
| --- | --- | --- |
| `@HttpExchange` | Thông tin chung cho interface/phương thức, như URL, accept, content type | Tiền tố `/api/inventory` |
| `@GetExchange` | HTTP GET | Đọc tồn kho |
| `@PostExchange` | HTTP POST | Tạo reservation |
| `@PutExchange` | HTTP PUT | Cập nhật tài nguyên |
| `@PatchExchange` | HTTP PATCH | Cập nhật một phần |
| `@DeleteExchange` | HTTP DELETE | Xóa/hủy theo hợp đồng |
| `@PathVariable`, `@RequestParam`, `@RequestHeader`, `@RequestBody` | Bind path, query, headers và body | SKU, filter, token và JSON |

Các HTTP exchange annotations thuộc `org.springframework.web.service.annotation`; một số annotation cho tham số dùng lại từ `org.springframework.web.bind.annotation`. Kiểu trả về có thể là DTO, `ResponseEntity<T>` hoặc kiểu phản ứng như `Mono<T>`/**`Flux<T>`** nếu adapter hỗ trợ. Chọn kiểu trả về phù hợp với HTTP client và luồng xử lý; một interface reactive không tự biến một transport blocking thành non-blocking.

### 2.2. Spring Cloud OpenFeign là gì?

**OpenFeign/Feign core** là thư viện tạo HTTP client theo interface. **Spring Cloud OpenFeign** bổ sung cách gắn Feign vào Spring: `@FeignClient`, Spring MVC contract, bean/configuration theo tên client và khả năng tích hợp Spring Cloud LoadBalancer, các cơ chế quan sát hoặc circuit breaker khi được cấu hình.

```java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "inventory", url = "${integration.inventory.base-url}")
public interface InventoryFeignApi {

    @GetMapping("/api/inventory/{sku}")
    InventoryResponse getAvailability(@PathVariable("sku") String sku);
}
```

Feign interface dùng `@FeignClient` để khai báo tên client và cách xác định đích. Trong Spring Cloud OpenFeign, `@GetMapping` là annotation theo Spring MVC contract; Feign core dùng contract/annotation riêng như `@RequestLine` khi không tích hợp Spring MVC. Bởi vậy, **Feign core không đồng nghĩa Spring Cloud OpenFeign**, và không nên sao chép một interface của chúng sang HTTP interface của Spring rồi giả định annotation nào cũng được hiểu.

### 2.3. Thư viện ngoài nghĩa là gì?

Ngoài hai lựa chọn trên, ứng dụng có thể dùng:

- **Retrofit**: thiết kế interface dựa trên annotation như `@GET`, `@POST`, converter và call adapter của Retrofit; phổ biến trong hệ sinh thái Java/Android, không phải Spring HTTP interface.
- **MicroProfile Rest Client**: `@RegisterRestClient` cùng JAX-RS annotations và cấu hình theo runtime MicroProfile; phù hợp dự án dựa trên MicroProfile/Jakarta stack tương thích.
- **OpenFeign core**: lập client Feign mà không cần starter Spring Cloud; doanh nghiệp tự quyết định contract, decoder, encoder, retry và dependency injection.
- **OpenAPI-generated client**: mã Java được sinh từ hợp đồng OpenAPI, có thể chọn các thư viện HTTP backend khác nhau tùy generator/options. Đây là **chiến lược sinh mã và quản lý hợp đồng**, không phải một transport nhất định.
- **OkHttp, Apache HttpClient, Java HttpClient**: HTTP transport/low-level clients; có thể nằm phía dưới một facade declarative, hoặc được dùng trực tiếp khi cần điều khiển giao thức ở mức thấp.

Nhiều đội chọn declarative interface để dễ đọc nhưng vẫn cần kiểm soát timeout, pool kết nối, xác thực, serializer, logging và việc đóng/mở tài nguyên.

## 3. Bảng so sánh để quyết định

| Câu hỏi | Spring HTTP interface | Spring Cloud OpenFeign | Retrofit / thư viện ngoài |
| --- | --- | --- | --- |
| Phạm vi | Spring Framework, tích hợp tự nhiên với Spring Web | Spring Cloud + Feign | Theo thư viện/runtime lựa chọn |
| Annotation chính | `@HttpExchange`, `@GetExchange`... | `@FeignClient`, Spring MVC mappings | Retrofit `@GET`; MicroProfile/JAX-RS hoặc contract khác |
| Tạo client | `HttpServiceProxyFactory` với adapter | Bean được đăng ký qua `@EnableFeignClients`/scan cấu hình | Builder/factory/injection của thư viện |
| HTTP transport | `RestClient`, `WebClient`, adapter tương thích phiên bản | Feign Client/transport được cấu hình; có thể dùng Apache HC5/OkHttp tùy dependency | Tùy thư viện, ví dụ OkHttp |
| Blocking / reactive | Có thể dùng blocking hoặc reactive theo adapter | Spring Cloud OpenFeign thông dụng là blocking; không hỗ trợ reactive client native tương đương WebClient | Phụ thuộc call adapter và framework |
| Cấu hình timeout, interceptor | Cấu hình ở `RestClient`/`WebClient` và request factory/connector | Feign properties, request interceptor, client config | Builder, call adapter và config riêng |
| Load balancing/service discovery | Qua client builder/adapter và tích hợp Spring Cloud phù hợp; cần kiểm tra cấu hình cụ thể | Tích hợp Spring Cloud LoadBalancer khi cấu hình tương thích | Tự tích hợp theo runtime |
| Mở rộng lỗi/codec | Cách xử lý status, Jackson/converters/filter của Spring client | `ErrorDecoder`, `Encoder`, `Decoder`, `RequestInterceptor` của Feign | Converter/error adapter riêng |
| Mức độ phụ thuộc | Thường ít dependency khi đã dùng Spring Web | Thêm Spring Cloud release train/starter | Thêm thư viện và cách quản lý phiên bản riêng |
| Migration | Đổi cách tạo proxy, annotations/return type | Đổi Feign client và Feign-specific config | Có thể đổi annotation, error model và transport |

**Đừng chọn chỉ từ cú pháp annotation.** Đường truyền HTTP mới là nơi quyết định timeout, TLS/mTLS, connection pooling, proxy, tracing, retry và những lỗi có thể xuất hiện. Hai interface nhìn rất giống nhau có thể khác đáng kể về retry mặc định, exception, URL encoding hoặc cách xử lý body rỗng.

### 3.1. Quy tắc chọn theo dự án

- Dự án Spring Boot mới, đã dùng Spring MVC/WebFlux và cần client khai báo ngắn gọn: **ưu tiên đánh giá HTTP interface của Spring** vì tái sử dụng HTTP client/converter và giảm số lớp tích hợp cần học.
- Dự án đã dùng Spring Cloud OpenFeign với nhiều client, config, interceptor, `ErrorDecoder`, load balancing và kiểm thử ổn định: **không cần đổi chỉ để thay annotation**; migration cần có mục tiêu kỹ thuật rõ.
- Dự án cần generator từ OpenAPI, SDK cho nhiều ngôn ngữ hoặc contract-first nghiêm ngặt: cân nhắc **generated client**; đánh giá generator target và quá trình cập nhật khi schema thay đổi.
- Dự án Java không dùng Spring, hoặc cần call adapter đặc thù của runtime: thư viện ngoài có thể phù hợp hơn.
- Luồng xử lý hoàn toàn reactive với WebFlux/Reactor: đánh giá Spring HTTP interface qua **WebClientAdapter** hoặc WebClient trực tiếp; tránh đặt lời gọi blocking vào event-loop.

Khi chọn thư viện, kiểm tra tương thích **Spring Boot – Spring Framework – Spring Cloud release train – Feign** của phiên bản dự án. Không lấy một ví dụ từ Boot 2 rồi áp nguyên sang Boot 3/4: package, cấu hình, default và cách tạo proxy có thể thay đổi.

## 4. Spring HTTP interface với RestClient: triển khai đầy đủ

Ví dụ hướng đến **Spring Boot 3.2+ / Spring Framework 6.1+**, nơi `RestClient` và `RestClientAdapter` có thể dùng cho HTTP interface. API minh họa: tra cứu một SKU và tạo giữ hàng (reservation) ở hệ thống tồn kho.

### 4.1. Cấu hình bằng properties theo môi trường

```yaml
# application.yml — giá trị minh họa, override ở mỗi environment
integration:
  inventory:
    base-url: "${INVENTORY_BASE_URL:http://localhost:18080}"
    connect-timeout: 500ms
    read-timeout: 2s
```

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "integration.inventory")
public record InventoryClientProperties(
        URI baseUrl,
        Duration connectTimeout,
        Duration readTimeout
) {}
```

Ví dụ record config cần được đăng ký với `@EnableConfigurationProperties(InventoryClientProperties.class)` hoặc quét bằng `@ConfigurationPropertiesScan`. Đối với production, thêm validation như `@Validated`, `@NotNull`, giới hạn timeout dương và kiểm tra scheme HTTPS/allowlist host theo chính sách ứng dụng. Không để URL hay secret phụ thuộc môi trường trong Java source.

### 4.2. Định nghĩa hợp đồng HTTP

```java
import java.math.BigDecimal;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

record AvailabilityResponse(String sku, boolean available, long version) {}
record ReserveRequest(String orderId, String sku, int quantity) {}
record ReserveResponse(String reservationId, String status) {}

@HttpExchange(url = "/api/inventory", accept = "application/json")
interface InventoryHttpClient {

    @GetExchange("/{sku}")
    AvailabilityResponse getAvailability(
            @PathVariable("sku") String sku,
            @RequestHeader("X-Correlation-Id") String correlationId);

    @PostExchange(url = "/reservations", contentType = "application/json")
    ReserveResponse reserve(
            @RequestHeader("Idempotency-Key") String idempotencyKey,
            @RequestHeader("X-Correlation-Id") String correlationId,
            @RequestBody ReserveRequest request);
}
```

`@HttpExchange` đặt tiền tố đường dẫn và Accept chung. `@GetExchange` / `@PostExchange` quyết định method, path và media type ở cấp phương thức. Các request/response DTO phải khớp contract của API thật; nếu upstream dùng trường khác, bắt buộc map rõ qua Jackson/config thay vì giả định Java record tự khớp.

`@RequestHeader("Idempotency-Key")` ở ví dụ là **hợp đồng nghiệp vụ do hai bên thống nhất**, không có nghĩa Spring tự cài idempotency. Server inventory phải lưu/kiểm tra key để bảo đảm lệnh reserve không bị thực hiện hai lần khi client retry.

### 4.3. Đăng ký proxy với RestClientAdapter

```java
import java.net.http.HttpClient;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration
@EnableConfigurationProperties(InventoryClientProperties.class)
class InventoryHttpClientConfig {

    @Bean
    InventoryHttpClient inventoryHttpClient(
            InventoryClientProperties properties,
            RestClient.Builder restClientBuilder) {

        HttpClient jdkClient = HttpClient.newBuilder()
                .connectTimeout(properties.connectTimeout())
                .build();

        JdkClientHttpRequestFactory factory =
                new JdkClientHttpRequestFactory(jdkClient);
        factory.setReadTimeout(properties.readTimeout());

        RestClient restClient = restClientBuilder
                .baseUrl(properties.baseUrl().toString())
                .requestFactory(factory)
                .build();

        RestClientAdapter adapter = RestClientAdapter.create(restClient);
        HttpServiceProxyFactory proxyFactory =
                HttpServiceProxyFactory.builderFor(adapter).build();

        return proxyFactory.createClient(InventoryHttpClient.class);
    }
}
```

Luồng chạy:

1. Spring Boot bind và validate thông số `InventoryClientProperties` theo cấu hình.
2. `RestClient` quản lý HTTP request factory, message converters, interceptor và xử lý phản hồi.
3. `RestClientAdapter` nối client thật vào `HttpServiceProxyFactory`.
4. Factory tạo proxy triển khai `InventoryHttpClient`; nghiệp vụ inject interface thay vì tự ghép HTTP request.
5. Khi gọi phương thức, proxy dựng HTTP exchange và giải mã response về DTO theo contract.

**Lưu ý phiên bản:** `HttpServiceProxyFactory.builderFor(...)` thuộc cách cấu hình Spring Framework 6.1+. Các bản Framework mới hơn có thể có thêm cơ chế đăng ký HTTP service client tự động; ví dụ này chủ động đăng ký bean để thể hiện rõ cách proxy được tạo. Không nên giả định chỉ viết `@HttpExchange` là mọi phiên bản Spring Boot tự quét và tạo bean.

### 4.4. Gọi từ service nghiệp vụ

```java
import org.springframework.stereotype.Service;

@Service
class OrderInventoryService {
    private final InventoryHttpClient inventory;

    OrderInventoryService(InventoryHttpClient inventory) {
        this.inventory = inventory;
    }

    boolean isAvailable(String sku, String correlationId) {
        AvailabilityResponse response =
                inventory.getAvailability(sku, correlationId);
        return response != null && response.available();
    }

    String reserveForOrder(
            String orderId, String sku, int quantity,
            String idempotencyKey, String correlationId) {
        ReserveResponse response = inventory.reserve(
                idempotencyKey,
                correlationId,
                new ReserveRequest(orderId, sku, quantity));
        if (response == null || response.reservationId() == null) {
            throw new IllegalStateException("Missing inventory reservation ID");
        }
        return response.reservationId();
    }
}
```

Không bọc một lời gọi HTTP chậm trong transaction DB dài nếu không bắt buộc: có thể giữ connection và lock trong lúc chờ mạng. Với nghiệp vụ phối hợp ghi DB và đặt giữ hàng, xem xét saga/compensation, transactional outbox hoặc trạng thái trung gian thay vì giả định HTTP call và DB commit là cùng một transaction.

## 5. Nếu dùng WebClient: HTTP interface vẫn giữ nguyên ý tưởng

Một ứng dụng WebFlux cần tránh chặn event-loop khi chờ HTTP. Với `WebClientAdapter`, Spring HTTP interface hỗ trợ return type phù hợp Reactor:

```java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import reactor.core.publisher.Mono;

@HttpExchange("/api/inventory")
interface ReactiveInventoryHttpClient {
    @GetExchange("/{sku}")
    Mono<AvailabilityResponse> getAvailability(
            @PathVariable("sku") String sku);
}
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration
class ReactiveInventoryConfig {
    @Bean
    ReactiveInventoryHttpClient reactiveInventoryHttpClient(
            WebClient.Builder webClientBuilder) {
        WebClient client = webClientBuilder
                .baseUrl("https://inventory.example.internal")
                .build();
        HttpServiceProxyFactory factory = HttpServiceProxyFactory
                .builderFor(WebClientAdapter.create(client))
                .build();
        return factory.createClient(ReactiveInventoryHttpClient.class);
    }
}
```

Đây là ví dụ nối proxy; **chưa đủ cấu hình production**. Cần thiết lập connect/response/read timeout ở connector tương ứng, retry policy, pool limits và TLS nếu cần. Khi dùng `Mono`/`Flux`, chỉ subscribe/compose trong pipeline được quản lý, tránh gọi `block()` trên event-loop. Cũng không mặc định reactive tốt hơn: blocking `RestClient` vẫn đơn giản và phù hợp trong ứng dụng MVC có đủ tài nguyên và giới hạn concurrency.

## 6. Spring Cloud OpenFeign: cùng yêu cầu, cách cấu hình khác

### 6.1. Dependency và đăng ký client

Với ứng dụng dùng Spring Cloud, thêm starter và chọn **Spring Cloud BOM tương thích Spring Boot**. Không cố định phiên bản Feign đơn lẻ bên ngoài dependency management nếu chưa đánh giá compatibility.

```kotlin
// build.gradle.kts — Spring Cloud BOM tương thích đã được cấu hình
implementation("org.springframework.cloud:spring-cloud-starter-openfeign")
```

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.openfeign.EnableFeignClients;

@SpringBootApplication
@EnableFeignClients(basePackageClasses = InventoryFeignApi.class)
public class OrderApplication {}
```

```java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestHeader;

@FeignClient(name = "inventory", url = "${integration.inventory.base-url}")
interface InventoryFeignApi {
    @GetMapping("/api/inventory/{sku}")
    AvailabilityResponse getAvailability(
            @PathVariable("sku") String sku,
            @RequestHeader("X-Correlation-Id") String correlationId);
}
```

Với URL trực tiếp, client gọi endpoint cấu hình. Khi dùng service discovery/load balancing, cách đặt name/URL và dependencies cần theo tài liệu Spring Cloud của phiên bản đang chạy. Một Feign client có thể có cấu hình riêng cho auth/interceptor, logging, encoder/decoder, timeout hoặc circuit breaker.

### 6.2. Cấu hình timeout theo tên client

```yaml
integration:
  inventory:
    base-url: "${INVENTORY_BASE_URL:https://inventory.example.internal}"

spring:
  cloud:
    openfeign:
      client:
        config:
          inventory:
            connectTimeout: 500
            readTimeout: 2000
            loggerLevel: basic
```

Trong ví dụ Spring Cloud OpenFeign 4.x, `connectTimeout` và `readTimeout` thể hiện bằng **mili-giây** theo cấu hình Feign. Điều này khác với giá trị `Duration` của cấu hình `integration.inventory.read-timeout: 2s` ở ví dụ Spring RestClient. Khi migration, rất dễ đưa nhầm `2000` thành giây hoặc ngược lại; cần kiểm tra property metadata của phiên bản dự án.

`loggerLevel` càng chi tiết càng có thể lộ headers/body; production không nên bật FULL tùy tiện vì payload có thể chứa token và dữ liệu cá nhân. Feign thường phát sinh exception như `FeignException` hoặc các lỗi transport riêng; cách phân loại và mapping khác với `RestClientResponseException` của Spring. Phải chuyển chúng về loại lỗi **nghiệp vụ ứng dụng** thống nhất tại boundary.

### 6.3. Điều gì dễ khác khi chuyển từ Feign?

| Khía cạnh | Feign đang vận hành | Spring HTTP interface thay thế |
| --- | --- | --- |
| Annotation | `@FeignClient` + `@GetMapping` | `@HttpExchange` + `@GetExchange` |
| Tạo bean | `@EnableFeignClients`/scan | Đăng ký proxy `HttpServiceProxyFactory` hoặc auto-registration phiên bản hỗ trợ |
| Request interception | `RequestInterceptor` | `RestClient` interceptor / `WebClient` filter |
| Error decode | `ErrorDecoder`, `FeignException` | `RestClient` status handlers/exception hoặc `WebClient` filter / response handlers |
| JSON/content negotiation | Feign encoder/decoder và Spring codecs cấu hình | `HttpMessageConverter`/codec của HTTP client Spring |
| Retry | Feign Retryer/config và chính sách ứng dụng | Retry/circuit breaker do application/client resilience layer thiết kế |
| Timeouts/pool/TLS | Feign client transport và properties | `ClientHttpRequestFactory` hoặc WebClient connector |
| Metrics/tracing | Tích hợp Feign/Micrometer, Spring Cloud instrumentation | Observation của RestClient/WebClient và instrumentation Spring |
| Load balancing | Spring Cloud client name/load balancer theo cấu hình | Cấu hình riêng builder/transport/integration Spring Cloud phù hợp |

**Đừng copy-paste property Feign sang Spring HTTP interface** rồi kỳ vọng có tác dụng. Ví dụ `spring.cloud.openfeign.client.config.inventory.readTimeout` không điều khiển `RestClient` ở phần 4. Cũng không giả định các interceptor, retryer, circuit breaker hoặc metric đã tự chuyển sang proxy mới.

## 7. Hành vi lỗi HTTP và hợp đồng ngoại lệ

Với các hệ thống tích hợp, lựa chọn thư viện là chuyện nội bộ; API nghiệp vụ phải có hành vi lỗi nhất quán. Phân loại lỗi theo *ý nghĩa* trước khi map thành response:

| Tình huống upstream | Cách diễn giải | Hướng xử lý |
| --- | --- | --- |
| 200 kèm dữ liệu hợp lệ | Thành công | Map DTO, kiểm tra điều kiện nghiệp vụ |
| 200 nhưng body rỗng/sai schema | Contract violation | Ghi lỗi hợp đồng, không tự coi null là thành công |
| 404 cho SKU không có | Có thể là "không tồn tại" theo hợp đồng | Map domain not-found nếu API quy định; không retry mù |
| 400/422 do request sai | Lỗi dữ liệu/hợp đồng | Chỉnh request hoặc trả lỗi nghiệp vụ |
| 401/403 | Lỗi xác thực/phân quyền | Kiểm tra credential và quyền; không retry vô hạn |
| 429 | Upstream áp quota/rate limit | Tôn trọng `Retry-After` khi có, giảm tốc độ gọi |
| 500/502/503 | Upstream lỗi hoặc không sẵn sàng | Circuit breaker, retry hữu hạn nếu an toàn |
| Connect/read timeout | Trạng thái kết quả có thể chưa biết | Chặn chờ quá lâu; với side effect cần idempotency/đối soát |
| Bulkhead full | Ứng dụng chặn quá tải trước khi gọi | Từ chối nhanh/fallback được phép, không retry tức thì |

Ở `RestClient`, các lỗi 4xx/5xx thường được chuyển thành exception khi dùng `retrieve()` theo handler mặc định; có thể tùy chỉnh xử lý status với `onStatus` hoặc default status handler. Với WebClient, `retrieve()` cũng có cơ chế xử lý lỗi HTTP status; Feign dùng `ErrorDecoder` hoặc default behavior của Feign. Hãy đặt **adapter mapping lỗi riêng** để phần nghiệp vụ không phụ thuộc trực tiếp vào exception kiểu transport.

### 7.1. Đừng retry mọi POST sau timeout

Giả sử `POST /reservations` đã ghi giữ hàng xong, nhưng response bị mất và client nhận timeout. Retry với một idempotency key **mới** có thể tạo hai reservation. Giữ nguyên key cho cùng thao tác và phải có hành vi idempotency phía server. Khi không biết trạng thái, API nên cho phép truy vấn theo business/command ID để đối soát.

Khi kết hợp retry với timeout và bulkhead:

- Có deadline end-to-end cho một request, không cộng vô hạn thời gian chờ ở mỗi lớp.
- Có backoff và jitter, giới hạn attempts, phân loại lỗi có thể thử lại.
- Không retry ngay các lỗi validation, auth, not-found hay bulkhead rejection.
- Circuit breaker dừng gọi sớm khi upstream hỏng liên tục; bulkhead giới hạn concurrency, không thay timeout.
- Khi API bắt buộc phụ thuộc đối tác, trả phản hồi lỗi rõ (ví dụ 503) thay vì tạo dữ liệu giả.
- Nếu cache Redis được dùng làm fallback, phải nêu dữ liệu có thể cũ và tránh cache stampede khi đối tác/Redis hồi phục.

## 8. Authentication, headers, TLS và truyền metadata

Mỗi client cần định nghĩa rõ:

1. **Base URL và endpoint** theo môi trường; không chấp nhận URL từ request client để tạo SSRF.
2. **Xác thực outbound**: token dịch vụ, OAuth2 client credentials, mTLS hoặc ký request theo hợp đồng.
3. **Header được phép truyền**: correlation ID/trace context chuẩn và metadata cần thiết; không forward mặc định `Authorization` của người dùng tới một đối tác khác.
4. **Timeout và connection pool** phù hợp RTO/SLO, traffic, quota của upstream.
5. **TLS/truststore/proxy** theo mạng thật; không tắt xác minh chứng chỉ để "sửa nhanh" môi trường.
6. **Giới hạn log**: không log token, cookie, body nhạy cảm hoặc URL query có thông tin cá nhân.

Trong HTTP interface, metadata có thể là tham số `@RequestHeader` rõ ràng (minh bạch, dễ test) hoặc được gắn bằng interceptor/filter theo chính sách thống nhất. Với Feign, thường dùng `RequestInterceptor`; cùng mục tiêu nhưng cơ chế cấu hình khác. Nếu dùng tracing qua Micrometer/Observation, kiểm tra builder được Spring quản lý và propagation thực tế; tránh tự dựng `traceparent` sai định dạng.

**Correlation ID khác idempotency key.** Correlation ID giúp tìm tất cả các lần thử trong cùng workflow; idempotency key nhận diện một thao tác logic cần chống trùng. Không dùng correlation ID làm khóa chống trùng toàn bộ luồng.

## 9. Kiểm thử contract để so sánh hai client

Khi đổi client library, cần chứng minh **HTTP wire contract không thay đổi**. Nên dùng mock HTTP server thực như WireMock hoặc MockWebServer, và integration test đi qua proxy/HTTP client đã cấu hình:

| Kịch bản | Kiểm tra | Tiêu chí chấp nhận |
| --- | --- | --- |
| GET SKU bình thường | Method, path encoding, Accept, body parse | DTO/đường dẫn đúng hợp đồng |
| Query/path có dấu cách, Unicode, ký tự đặc biệt | URI encoding của hai client | Không tạo sai URL hoặc double-encode |
| POST reservation | Content-Type, JSON body, Idempotency-Key | Một thao tác logic có key ổn định |
| HTTP 404/409/422 | Response status và error schema | Domain error mapping thống nhất |
| HTTP 429/503 + Retry-After | Thời gian chờ/attempts | Không retry storm, tôn trọng deadline |
| Kết nối không mở được | Connect timeout | Trả lỗi sớm, permit/tài nguyên được giải phóng |
| Upstream treo khi đọc body | Read/response timeout | Không giữ request thread/connection vô hạn |
| Body rỗng/malformed | Converter/decoder | Không coi như dữ liệu nghiệp vụ hợp lệ |
| Redirect, nén, charset | Behavior của transport đã chọn | Đúng theo policy bảo mật và hợp đồng |
| Trace/correlation | Header khi gọi outbound | Có propagation cần thiết, không lộ token |
| Gọi đồng thời nhiều request | Connection pool, bulkhead, timeout | Không vượt ngân sách concurrency |
| OpenFeign → HTTP interface | So sánh request/response từ cả hai client | Semantics giống nhau sau migration |

Nếu API trả 429, đừng viết test chỉ xác nhận "có throw exception": phải kiểm tra policy giảm tốc, số attempts và tổng thời gian. Với POST có side effect, test lần đầu đã commit nhưng mất response; xác minh idempotency ở phía server, vì client library không thể cung cấp bảo đảm này một mình.

### 9.1. Kiểm thử cấu hình proxy và client theo profile

Sử dụng test Spring Boot nạp cấu hình với mock server, xác nhận bean `InventoryHttpClient` có thể inject và dùng base URL/timeout tương ứng môi trường. Nên kiểm tra đường phát sinh lỗi thật qua client/adapter thay vì chỉ mock toàn bộ interface, vì mock interface sẽ không phát hiện sai URL encoding, media type, error handler hoặc network timeout.

Nếu có nhiều client cùng kiểu, đặt bean name/qualifier rõ ràng và đảm bảo không dùng chung cấu hình auth/headers giữa các đối tác không liên quan. Tránh HTTP connection pool cấu hình thiếu giới hạn gây ảnh hưởng sang các luồng JDBC, Redis hoặc consumer broker dưới tải lớn.

## 10. Lộ trình chuyển từ OpenFeign sang Spring HTTP interface

Việc chuyển đổi có thể chia thành các bước nhỏ, đo được:

1. **Kiểm kê Feign clients**: đường dẫn, method, query, headers, body, error decoder, encoder/decoder, interceptors, auth, timeout, retry, load balancing, logging, metric, tracing.
2. **Đóng băng contract** bằng test request/response HTTP thật, đặc biệt với enum, date, Pageable, multipart, PATCH, empty response và error body.
3. **Chọn transport Spring**: RestClient cho MVC/blocking; WebClient cho reactive; cấu hình pool, timeout, TLS và observability theo môi trường.
4. **Chuyển một client ít rủi ro**: thay `@FeignClient`/mappings bằng `@HttpExchange`/`@GetExchange` và đăng ký proxy bằng `HttpServiceProxyFactory`.
5. **Tái thiết kế các extension**: Feign interceptor → RestClient interceptor, Feign ErrorDecoder → status handling, retryer/circuit breaker → resilience policy chủ động. Chỉ tái sử dụng thứ có cùng semantics.
6. **So sánh hành vi**: cùng upstream giả lập, hai client cho HTTP method, URL, headers, body, timeout, errors và tracing như contract đã xác nhận.
7. **Triển khai dần**: dùng cấu hình chọn client theo service hoặc một adapter interface chung. Theo dõi latency p95/p99, lỗi, retry count, connection pool và các business outcome quan trọng.
8. **Dọn đường cũ** khi không còn phụ thuộc: gỡ starter/config/bean Feign không được sử dụng, cập nhật dashboards và tài liệu vận hành.

Không cần thực hiện migration đồng loạt cho mọi client chỉ vì muốn "thống nhất". Với một integration phức tạp, mỗi thay đổi transport có thể ảnh hưởng SSL, proxy, auth, retry, codecs và tài nguyên. Quyết định chuyển nên có mục tiêu và phép đo cụ thể.

### 10.1. Trường hợp không thể thay thẳng annotation

- Feign có `@SpringQueryMap` hoặc contract xử lý query objects đặc thù; cần định nghĩa lại tham số và encoding trong HTTP interface.
- Feign có `ErrorDecoder` biến status/body thành domain exception; cần port logic mapping một cách tường minh.
- Feign dùng client-specific TLS, auth signing, proxy hoặc load balancing; phải tái tạo cấu hình ở RestClient/WebClient.
- Feign sử dụng fallback/circuit breaker riêng; phải kiểm tra order retry → circuit breaker → bulkhead khi thay.
- Có multipart upload/download streaming, SSE, reactive streams hoặc body kích thước lớn; kiểu return và buffering khác nhau cần benchmark/test.
- Có interceptor thêm dynamic headers hoặc serialize body khác chuẩn Jackson; contract test phải kiểm tra byte wire khi chữ ký request phụ thuộc canonical encoding.

## 11. Kết hợp HTTP interface với các thành phần tích hợp

### JDBC và giao dịch

Một lệnh database và một lời gọi đối tác HTTP không chia sẻ atomic transaction. Spring `@Transactional` điều khiển transaction resource cục bộ tương ứng; không rollback được lệnh HTTP đã thực thi. Dùng outbox cho phát sự kiện sau commit, saga cho phối hợp nhiều bước có bù trừ, idempotency cho thao tác có thể phát lại.

### Redis cache và circuit breaker

Cache giảm số lời gọi đến đối tác nhưng cần TTL, invalidation và chống stampede. Nếu đối tác lỗi, có thể trả dữ liệu cache cũ **chỉ khi nghiệp vụ cho phép**. Dùng circuit breaker, bulkhead và timeout ở tầng HTTP client, không kỳ vọng annotation declarative tự tạo khả năng tự phục hồi.

### Kafka/RabbitMQ và Spring Integration

Một consumer xử lý message rồi gọi HTTP interface sẽ bị ảnh hưởng bởi latency/timeout giống như lời gọi từ controller. Nếu downstream hỏng, lựa chọn ack/retry/DLQ và idempotency quyết định có mất hoặc lặp tác dụng phụ hay không. Không ack thành công message chưa hoàn tất xử lý; đừng retry HTTP cùng message vô hạn tạo vòng lỗi nóng. Khi flow bất đồng bộ, propagation correlation ID/trace context phải được kiểm thử qua boundary.

### Observability

Dùng metric có tags hữu hạn như `dependency="inventory_api"`, `operation="reserve"`, `outcome="timeout"`. Không đưa raw URL chứa SKU, user ID, order ID, correlation ID hay trace ID vào metric labels. Các định danh chi tiết có thể nằm trong structured log/trace có phân quyền và giới hạn dữ liệu. Cả HTTP interface và Feign đều cần xác minh instrumentation **trên client thực tế**, không chỉ nhìn tên annotation.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| `@HttpExchange` tự tạo server endpoint | Đây là annotation client; server controller được đăng ký bằng cơ chế server riêng |
| Có annotation thì Spring Boot tự tạo proxy mọi phiên bản | Cần đăng ký client/proxy theo khả năng của phiên bản đang dùng |
| Spring HTTP interface là một HTTP engine mới | Nó là lớp declarative; request chạy qua RestClient/WebClient hoặc adapter tương ứng |
| OpenFeign và Feign core là một | Spring Cloud OpenFeign bổ sung Spring-specific integration/config |
| `@FeignClient` và `@HttpExchange` thay ngang 1:1 | Hệ thống tạo bean, interceptors, error model, retry, timeout có thể khác |
| Spring HTTP interface luôn reactive | Blocking/reactive phụ thuộc adapter và kiểu trả về |
| Feign mặc nhiên retry giống RestClient | Mặc định và cấu hình retry khác theo thư viện/phiên bản; phải xác minh |
| 2 giây timeout đọc là toàn bộ deadline | Connection, queue, retry, backoff và xử lý nội bộ cũng tiêu tốn thời gian |
| POST có idempotency header là đủ | Upstream phải hỗ trợ lưu/trả kết quả idempotent |
| Load balancing tự có vì interface dùng Spring | Cần cấu hình discovery/load balancer hoặc endpoint phù hợp |
| Mock interface đủ kiểm thử tích hợp | Phải kiểm tra HTTP request/response qua transport thực |

## 13. Checklist khi chọn và vận hành client

- [ ] Đã xác định ứng dụng dùng Spring Boot/Framework/Cloud phiên bản nào và client nào được hỗ trợ.
- [ ] Đã chọn RestClient, WebClient, Spring Cloud OpenFeign hoặc thư viện ngoài dựa trên nhu cầu blocking/reactive, discovery, tooling và contract.
- [ ] Interface mô tả đúng method, path/query encoding, headers, body, content type và return type.
- [ ] Proxy/Feign bean được đăng ký đúng và mỗi đối tác có base URL, credential, timeout, pool riêng theo nhu cầu.
- [ ] Connection/read/response timeout, tổng deadline, retry/backoff, circuit breaker và bulkhead có chính sách rõ.
- [ ] Lỗi HTTP, transport, deserialize và body rỗng được chuyển thành domain error có ý nghĩa.
- [ ] Các thao tác POST/PUT/PATCH có side effect có idempotency key hoặc đối soát khi retry sau timeout.
- [ ] Header auth và correlation/trace context được truyền qua boundary an toàn, không lộ token hay PII.
- [ ] Đã kiểm tra contract thật bằng mock HTTP server: success, 4xx, 5xx, timeout, encoding, lỗi body, concurrency.
- [ ] Khi migration từ Feign, đã port các interceptor, decoder, retry/timeout/metrics thay vì chỉ sửa annotation.
- [ ] Tích hợp với DB/Redis/broker xử lý đúng transaction, cache fallback, ack, retry và duplicate delivery.
- [ ] Metrics tags hữu hạn, logs/traces có dữ liệu phù hợp chính sách, dashboard cảnh báo đúng sau thay client.

**Kết quả mong muốn:** Nhóm phát triển hiểu Spring HTTP interface là cách khai báo và tạo proxy dựa trên các HTTP client Spring, OpenFeign là hệ sinh thái client riêng được Spring Cloud tích hợp, còn các thư viện ngoài có hợp đồng và extension riêng. Dù chọn công cụ nào, tính đúng đắn của tích hợp nằm ở hợp đồng HTTP, cấu hình transport, xử lý lỗi, idempotency, quan sát và kiểm thử end-to-end.
