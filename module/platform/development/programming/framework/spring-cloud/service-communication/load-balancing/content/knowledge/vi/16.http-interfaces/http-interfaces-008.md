# So sánh HTTP Interface với OpenFeign theo nhu cầu dự án

Khi hai microservice cần giao tiếp HTTP, đội phát triển thường muốn code gọi từ `order-service` đến `catalog-service` trông như một lời gọi phương thức Java: `catalogClient.findById("42")`. **Spring HTTP Service Interface** và **Spring Cloud OpenFeign** đều hỗ trợ phong cách *declarative HTTP client* đó, nhưng chúng khác nhau về cách tạo proxy, annotation, HTTP stack nền, cấu hình và hệ sinh thái tích hợp.

Bài học thuộc chương **HTTP Interface** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Trọng tâm là lựa chọn theo **nhu cầu thực tế của dự án**, đặc biệt khi phải gọi theo **service ID**, chọn `ServiceInstance` qua Spring Cloud LoadBalancer, kết nối discovery/health check và kiểm soát timeout, retry, lỗi HTTP. Mục tiêu không phải tuyên bố một giải pháp luôn tốt hơn giải pháp kia, mà là nắm rõ **điểm đánh đổi** để chọn hoặc di chuyển có chủ đích.

> **Phạm vi:** Spring Framework 6.1+ cho HTTP Service Interface với `RestClientAdapter`; Spring Cloud OpenFeign tương thích với Spring Boot/Spring Cloud của dự án. API và thuộc tính cấu hình có thể khác theo release train, vì vậy cần đối chiếu version thực tế. Các ví dụ chủ yếu là ứng dụng đồng bộ; phần WebClient minh họa lựa chọn reactive.

## 1. Hai cách khai báo cùng một HTTP API

Giả sử có service ID `catalog-service` với các endpoint:

| HTTP endpoint | Công dụng | Hợp đồng phản hồi giả định |
|---|---|---|
| `GET /api/items/{id}` | Tìm một mặt hàng | `200` + JSON `ItemDto` hoặc `404` |
| `GET /api/items?category=paper` | Tìm theo nhóm | `200` + JSON array |
| `POST /api/items` | Tạo mặt hàng | `201` + JSON `ItemDto` |
| `GET /api/items/events` | Luồng cập nhật tồn kho | `200 text/event-stream` nếu server hỗ trợ |

DTO dùng trong ví dụ:

~~~java
record ItemDto(String id, String name, int stock) {}

record CreateItemRequest(String name, int stock) {}
~~~

Đây là các kiểu dữ liệu minh họa. Để biên dịch trong một dự án thật, cần đặt chúng ở package và phạm vi truy cập phù hợp; client và server không bắt buộc chia sẻ một thư viện DTO Java.

### Spring HTTP Service Interface

~~~java
import java.util.List;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.service.annotation.PostExchange;

@HttpExchange(
    url = "/api/items",
    accept = MediaType.APPLICATION_JSON_VALUE
)
interface CatalogHttpApi {

    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);

    @GetExchange
    List<ItemDto> search(@RequestParam("category") String category);

    @PostExchange(contentType = MediaType.APPLICATION_JSON_VALUE)
    ItemDto create(
        @RequestBody CreateItemRequest body,
        @RequestHeader("X-Idempotency-Key") String idempotencyKey
    );
}
~~~

### Spring Cloud OpenFeign

~~~java
import java.util.List;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;

@FeignClient(
    name = "catalog-service",
    path = "/api/items"
)
interface CatalogFeignApi {

    @GetMapping("/{id}")
    ItemDto findById(@PathVariable("id") String id);

    @GetMapping
    List<ItemDto> search(@RequestParam("category") String category);

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ItemDto create(
        @RequestBody CreateItemRequest body,
        @RequestHeader("X-Idempotency-Key") String idempotencyKey
    );
}
~~~

Hai interface mô tả **cùng hành vi HTTP**. Tuy nhiên, `@GetExchange` là annotation của **Spring HTTP Interface**, còn `@GetMapping` trong ví dụ Feign được Spring Cloud OpenFeign diễn giải bằng contract riêng. Đổi một annotation mà không đổi cơ chế đăng ký/tạo proxy có thể khiến request không được xây đúng.

## 2. Khác biệt quan trọng nhất: ai tạo proxy và ai thực hiện request?

~~~mermaid
flowchart TB
    App["order-service gọi findById(id)"] --> X{"Client declarative được dùng"}
    X -->|HTTP Interface| HP["HttpServiceProxyFactory"]
    HP --> AD["RestClientAdapter hoặc WebClientAdapter"]
    AD --> LB["Spring Cloud LoadBalancer nếu client nền có @LoadBalanced"]
    X -->|OpenFeign| FP["Spring Cloud OpenFeign tạo Feign proxy"]
    FP --> FC["Feign Client / transport"]
    FC --> LB2["Spring Cloud LoadBalancer nếu tích hợp và không cố định URL"]
    SUP["Discovery + ServiceInstanceListSupplier"] --> LB
    SUP --> LB2
    LB --> A["catalog-service instance"]
    LB2 --> A
~~~

**HTTP Service Interface** thuộc Spring Framework: interface chỉ cung cấp metadata. Để dùng, ứng dụng tạo một `HttpServiceProxyFactory` với adapter thực thi như `RestClientAdapter` hoặc `WebClientAdapter`, sau đó gọi `createClient(...)`. Spring Cloud LoadBalancer được đưa vào **HTTP client nền**, không phải vào annotation `@HttpExchange`.

**OpenFeign** là tích hợp Spring Cloud của dự án Feign: khi có `@EnableFeignClients` và cấu hình phù hợp, Spring tạo Feign proxy từ `@FeignClient`. Với `name = "catalog-service"`, Feign có thể định tuyến theo service ID nhờ tích hợp Spring Cloud LoadBalancer nếu dependency và cấu hình hiện hữu.

Cả hai đều tách interface khỏi logic nghiệp vụ. Điểm cần cân nhắc là **cơ chế tạo proxy và HTTP stack mà đội đã có**.

## 3. Dependency và yêu cầu phiên bản

Đối với HTTP Interface dùng RestClient trong dự án Spring Boot/Spring Cloud:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Đối với OpenFeign:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-openfeign'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Các đoạn trên chỉ minh họa dependency liên quan; dự án cần plugin, BOM và các dependency thực tế khác. `spring-cloud-starter-openfeign` không tự là một API của Spring Framework; nó kích hoạt hệ sinh thái cấu hình Feign của Spring Cloud. `spring-cloud-starter-loadbalancer` nên có mặt khi mục tiêu là phân giải **service ID** bằng Spring Cloud LoadBalancer.

Nếu muốn HTTP Interface chạy qua WebClient, cần HTTP client reactive:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

**Không ghép tùy tiện release train:** ví dụ `RestClient` yêu cầu Spring Framework 6.1+; các API của `HttpServiceProxyFactory`, Spring Cloud OpenFeign và thuộc tính timeout phụ thuộc những version có trong dependency management thực tế. Kiểm tra compatibility matrix của Spring Boot và Spring Cloud trước khi copy mã.

## 4. Tạo HTTP Service Interface proxy với RestClient và LoadBalancer

Bản HTTP Interface ở phần 1 chưa có proxy. Ví dụ một cấu hình bean cho caller:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Configuration(proxyBeanMethods = false)
class CatalogHttpInterfaceConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder lbRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    CatalogHttpApi catalogHttpApi(
            @Qualifier("lbRestClientBuilder") RestClient.Builder builder) {

        RestClient restClient = builder
            .baseUrl("http://catalog-service")
            .build();

        RestClientAdapter adapter = RestClientAdapter.create(restClient);

        HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(adapter).build();

        return factory.createClient(CatalogHttpApi.class);
    }
}
~~~

Ở đây:

1. `@LoadBalanced` đánh dấu builder để Spring Cloud cấu hình xử lý URL theo service ID.
2. `baseUrl("http://catalog-service")` là URL logic, không phải hostname của instance.
3. `RestClientAdapter.create(restClient)` nối proxy với RestClient đồng bộ.
4. `HttpServiceProxyFactory.createClient(CatalogHttpApi.class)` tạo object thực hiện interface.
5. `@HttpExchange("/api/items")` + `@GetExchange("/{id}")` tạo đường dẫn `/api/items/{id}`.

Với `catalogHttpApi.findById("42")`, HTTP client thực hiện **lời gọi đồng bộ**. Phần xử lý HTTP status, connection timeout và đọc response phụ thuộc RestClient và request factory.

Không dùng `RestClient.create("http://catalog-service")` độc lập rồi giả định nó tự có LoadBalancer; URL khi đó có thể đi qua DNS thông thường. Ngược lại, khi gọi Internet API trực tiếp, không nên vô tình dùng một builder load-balanced nếu host không phải service ID trong discovery.

## 5. Đăng ký OpenFeign proxy qua @FeignClient

Với Feign, không cần tự gọi `HttpServiceProxyFactory`. Đăng ký interface được tạo bởi Spring Cloud OpenFeign:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.openfeign.EnableFeignClients;

@SpringBootApplication
@EnableFeignClients(clients = CatalogFeignApi.class)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Interface `CatalogFeignApi` đã dùng `@FeignClient(name = "catalog-service", path = "/api/items")`; Spring Cloud OpenFeign tạo bean tương ứng và inject vào service nghiệp vụ.

Sử dụng:

~~~java
import org.springframework.stereotype.Service;

@Service
class ItemService {

    private final CatalogFeignApi catalog;

    ItemService(CatalogFeignApi catalog) {
        this.catalog = catalog;
    }

    ItemDto getItem(String id) {
        return catalog.findById(id);
    }
}
~~~

Trong dự án thật, `@EnableFeignClients` có thể dùng package scanning hoặc liệt kê clients rõ ràng. Liệt kê class được yêu cầu giúp tránh không scan thấy interface khi nó nằm ngoài package mặc định.

**Không đồng thời đăng ký cả `CatalogHttpApi` và `CatalogFeignApi` chỉ vì ví dụ có hai lựa chọn** nếu ứng dụng chỉ cần một cách gọi. Hai interface là **hai phương án thay thế** cho cùng downstream; có thể cùng tồn tại khi đang migration nhưng cần tên bean và đường sử dụng rõ ràng.

## 6. Service ID và lựa chọn ServiceInstance

Đây là điểm chung quan trọng với module Spring Cloud LoadBalancer.

Giả sử discovery biết hai instance:

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

Tương ứng với service ID `catalog-service`, cả HTTP Interface và OpenFeign có thể lựa chọn A/B theo bộ chọn đang cấu hình.

~~~mermaid
sequenceDiagram
    participant B as Business code
    participant C as Declarative HTTP client
    participant LB as LoadBalancer
    participant S as ServiceInstanceListSupplier
    participant I as catalog-a hoặc catalog-b

    B->>C: findById("42")
    C->>LB: Cần instance của catalog-service
    LB->>S: Lấy ứng viên (discovery, health, filter)
    S-->>LB: [A, B]
    LB-->>C: Chọn B
    C->>I: GET /api/items/42
    I-->>C: HTTP 200 + JSON
    C-->>B: ItemDto
~~~

**HTTP Interface:** service ID thường nằm trong `baseUrl("http://catalog-service")` của RestClient/WebClient được đánh dấu `@LoadBalanced`; `@HttpExchange` xác định path của API.

**OpenFeign:** `@FeignClient(name = "catalog-service")` xác định tên client/service dùng cho LoadBalancer khi không cung cấp URL cố định, và `path` là prefix chung của các endpoint.

Nếu trong Feign cấu hình `url` trỏ tới một địa chỉ cụ thể, ví dụ `@FeignClient(name = "catalog-service", url = "http://localhost:18081")`, client sẽ **gọi URL được chỉ định** thay vì phân phối giữa những instance của `catalog-service` qua cơ chế chọn đích thông thường. Đây là thay đổi semantics cần nêu rõ khi chuyển cấu hình dev sang staging/production.

Tương tự, với HTTP Interface, sử dụng builder không load-balanced và baseUrl là host trực tiếp sẽ bypass Spring Cloud LoadBalancer. **Tên interface hoặc tên bean không tự động kích hoạt service discovery.**

## 7. So sánh annotation và cách biểu diễn request

| Nhu cầu | HTTP Service Interface | OpenFeign |
|---|---|---|
| Đánh dấu interface | `@HttpExchange` | `@FeignClient` |
| Prefix URL | `@HttpExchange(url = "/api/items")` | `@FeignClient(path = "/api/items")` |
| GET | `@GetExchange("/{id}")` | `@GetMapping("/{id}")` |
| POST | `@PostExchange` | `@PostMapping` |
| PUT/PATCH/DELETE | `@PutExchange`, `@PatchExchange`, `@DeleteExchange` | `@PutMapping`, `@PatchMapping`, `@DeleteMapping` |
| Path variable | `@PathVariable("id")` | `@PathVariable("id")` |
| Query | `@RequestParam("category")` | `@RequestParam("category")` |
| Request body | `@RequestBody` | `@RequestBody` |
| Request header | `@RequestHeader` | `@RequestHeader` |
| Content negotiation | `accept`, `contentType` trên Exchange annotation | `produces`, `consumes` trên mapping theo contract |
| Tham số request nâng cao | Theo HTTP Interface argument resolvers/adapter | Theo Feign contract, encoders, capabilities |

**Lưu ý:** các annotation trùng tên như `@PathVariable` và `@RequestBody` đến từ Spring MVC package nhưng được cả hai cơ chế khai thác trong ngữ cảnh client. Ngược lại, `@GetExchange` và `@GetMapping` **không thể thay thế tùy ý**; mỗi framework có metadata reader/contract riêng.

### Lỗi ghép URL rất dễ gặp

HTTP Interface:

~~~java
@HttpExchange("/api/items")
interface CatalogHttpApi {

    // Đúng: chỉ thêm segment của endpoint
    @GetExchange("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

OpenFeign:

~~~java
@FeignClient(name = "catalog-service", path = "/api/items")
interface CatalogFeignApi {

    // Đúng: chỉ thêm segment của endpoint
    @GetMapping("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

Nếu thêm lại `/api/items` vào annotation method, có thể tạo path lặp hoặc path không đúng. Cần test request URL đã phát ra, không chỉ nhìn method name.

## 8. Đồng bộ, reactive và streaming

Một tiêu chí chọn công cụ quan trọng là **mô hình xử lý request của ứng dụng**.

### HTTP Interface qua RestClientAdapter

HTTP Service Interface có thể sử dụng `RestClientAdapter` với return type như:

~~~java
ItemDto findById(String id);
ResponseEntity<ItemDto> getEntity(String id);
void delete(String id);
~~~

RestClient là **blocking client**. Nếu một thread trong Spring MVC gọi ba dịch vụ tuần tự, thời gian chờ có thể cộng dồn. Tên “interface declarative” không làm lời gọi bớt blocking.

### HTTP Interface qua WebClientAdapter

Có thể tạo proxy bằng `WebClientAdapter` từ WebClient nền đã được đánh dấu `@LoadBalanced`. Khi đó interface có thể định nghĩa:

~~~java
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

record StockEvent(String sku, int quantity) {}

@HttpExchange("/api/items")
interface ReactiveCatalogHttpApi {

    @GetExchange("/{id}")
    Mono<ItemDto> findById(@PathVariable("id") String id);

    @GetExchange(
        url = "/events",
        accept = MediaType.TEXT_EVENT_STREAM_VALUE
    )
    Flux<ServerSentEvent<StockEvent>> streamEvents();
}
~~~

Tạo proxy:

~~~java
WebClient webClient = lbWebClientBuilder
    .baseUrl("http://catalog-service")
    .build();

HttpServiceProxyFactory factory =
    HttpServiceProxyFactory.builderFor(
        WebClientAdapter.create(webClient))
        .build();

ReactiveCatalogHttpApi api =
    factory.createClient(ReactiveCatalogHttpApi.class);
~~~

Trong đoạn rút gọn này, `lbWebClientBuilder` là một `WebClient.Builder` đã được Spring quản lý và đánh dấu `@LoadBalanced`. Khi dùng mã hoàn chỉnh, cần import `WebClient`, `WebClientAdapter` và `HttpServiceProxyFactory` như trong phần cấu hình tương ứng.

`Mono<T>` và `Flux<T>` phù hợp với pipeline không chặn và streaming SSE. Nhưng bản thân HTTP Interface không tạo ra reactive execution; **adapter mới quyết định HTTP stack**. Tránh gọi `block()` trong WebFlux event-loop.

### OpenFeign

Spring Cloud OpenFeign thường dùng mô hình gọi **đồng bộ**. Không suy rằng có thể chỉ đổi return type của `@FeignClient` thành `Mono<T>`/`Flux<T>` và được một reactive HTTP client tương đương WebClient. Nếu dự án cần non-blocking streaming, hãy chọn WebClientAdapter hoặc một công nghệ reactive được hỗ trợ rõ ràng.

| Nhu cầu | Cân nhắc |
|---|---|
| Spring MVC, request-response ngắn, team quen Feign | OpenFeign hoặc HTTP Interface + RestClient đều phù hợp |
| Ứng dụng mới muốn dùng HTTP stack Spring Framework trực tiếp | HTTP Interface + RestClient/WebClient |
| WebFlux cần `Mono`/`Flux` và SSE dài | HTTP Interface + WebClientAdapter thường phù hợp hơn |
| Dự án có nhiều Feign clients, error decoder và cấu hình lâu năm | Giữ OpenFeign đến khi có lý do migration |
| Cần đổi HTTP transport hoặc tăng connection pooling | Kiểm tra mức tùy biến transport thực tế của lựa chọn và dependency |

Không chọn chỉ theo số dòng khai báo: hãy tính khả năng bảo trì, mô hình thread, cách giám sát và mức tích hợp sẵn của dự án.

## 9. HTTP errors và exception khác nhau thế nào?

Giả sử backend trả `404` khi item không tồn tại và `503` khi đang quá tải.

**HTTP Interface qua RestClientAdapter** thường sử dụng status handling của RestClient. Các HTTP `4xx/5xx` không được xử lý riêng có thể tạo exception thuộc nhóm `RestClientResponseException`. Có thể cấu hình default status handler khi tạo RestClient hoặc xử lý exception ở tầng service.

**HTTP Interface qua WebClientAdapter** sử dụng WebClient; lỗi HTTP status thông thường xuất hiện dưới dạng error signal, ví dụ `WebClientResponseException`. Ứng dụng reactive nên xử lý bằng `onErrorResume`, `onErrorMap` hoặc lớp resilience phù hợp, không dùng try/catch quanh việc chỉ tạo `Mono`.

**OpenFeign** thường biểu diễn status lỗi bằng `FeignException` hoặc exception do một `ErrorDecoder` tùy chỉnh trả về.

Ví dụ phân loại trong Feign:

~~~java
import feign.FeignException;

try {
    ItemDto item = catalogFeignApi.findById("missing");
} catch (FeignException.NotFound ex) {
    // HTTP 404 từ backend: xử lý theo contract.
} catch (FeignException ex) {
    int httpStatus = ex.status();
    // Kiểm tra 429, 503, transport và chính sách nghiệp vụ.
}
~~~

Các class exception thực tế còn phụ thuộc transport và `ErrorDecoder` của Feign. Nếu dùng exception do decoder tự tạo, cách catch có thể khác.

Ví dụ với HTTP Interface + RestClient:

~~~java
import org.springframework.web.client.RestClientResponseException;

try {
    ItemDto item = catalogHttpApi.findById("missing");
} catch (RestClientResponseException ex) {
    int status = ex.getStatusCode().value();
    // Đã có HTTP response lỗi từ endpoint.
}
~~~

**Cả hai ví dụ không bao quát mọi lỗi kết nối.** Khi không chọn được `ServiceInstance`, connect timeout, TLS handshake failure hoặc server bị reset trước response, có thể không có HTTP status từ backend để decode.

| Trường hợp | HTTP Interface / RestClient | OpenFeign |
|---|---|---|
| HTTP 404 | Status handler hoặc `RestClientResponseException` | `FeignException.NotFound` hoặc ErrorDecoder |
| HTTP 503 | Status handler hoặc `RestClientResponseException` | `FeignException`/ErrorDecoder |
| Không có instance | Lỗi LoadBalancer trước HTTP | Lỗi LoadBalancer/Feign client trước HTTP |
| Connect timeout | Lỗi transport/client | Lỗi transport/client tùy Feign HTTP stack |
| JSON không tương thích DTO | Lỗi message conversion | Lỗi decoder |
| Fallback | Tự cấu hình wrapper/resilience | Cần cấu hình circuit breaker/fallback phù hợp |

**Không so sánh bằng tên exception đơn thuần.** Hãy thống nhất mapping sang lỗi nghiệp vụ như `ITEM_NOT_FOUND`, `DOWNSTREAM_UNAVAILABLE`, `TIMEOUT` ở boundary ứng dụng. Tách *không có instance* khỏi *backend đã trả HTTP 503* để chẩn đoán chính xác.

## 10. Timeout và retry: annotation không tự bảo đảm ổn định

Cả hai đều gọi HTTP qua mạng, nên cần giới hạn thời gian và số lần thử.

### HTTP Interface: cấu hình ở client nền

Ví dụ dùng request factory cho RestClient:

~~~java
import org.springframework.http.client.SimpleClientHttpRequestFactory;

SimpleClientHttpRequestFactory requestFactory =
    new SimpleClientHttpRequestFactory();

requestFactory.setConnectTimeout(2000);
requestFactory.setReadTimeout(3000);

RestClient restClient = lbRestClientBuilder
    .requestFactory(requestFactory)
    .baseUrl("http://catalog-service")
    .build();
~~~

Đây là **đoạn thay thế** phần tạo `RestClient` trong cấu hình bean ở trên, không phải bean thứ hai cần đăng ký. Hai giá trị là mili giây theo API request factory ví dụ; hệ thống thực tế có thể dùng Apache HttpComponents hoặc transport khác với connection pooling và cấu hình tương ứng.

### OpenFeign: cấu hình theo tên client

Trong `application.yml` có thể cấu hình:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            connectTimeout: 2000
            readTimeout: 3000
            loggerLevel: basic
~~~

Tên `catalog-service` phải khớp Feign client được cấu hình. Các timeout theo cấu hình trên được diễn giải bằng mili giây trong cấu hình Spring Cloud OpenFeign thông dụng; kiểm tra phiên bản thực tế và transport được sử dụng.

Một ưu điểm thực tế của OpenFeign trong hệ thống có nhiều client là **hệ thống cấu hình theo client name** đã được tích hợp sẵn. Với HTTP Interface, đội thường tạo bean/configuration cho từng nhóm proxy hoặc xây convention để áp dụng base URL, timeout và header chung.

### Retry khác nhau, nhưng đều có rủi ro

Không mặc định Spring Cloud OpenFeign hay HTTP Interface sẽ tự retry tất cả lỗi theo cùng một chính sách. Spring Cloud OpenFeign thường cấu hình `Retryer.NEVER_RETRY` làm mặc định theo tài liệu của nó, khác với một số hành vi mặc định của Feign core; cần kiểm tra khi nâng cấp hoặc tự khai báo `Retryer`.

HTTP Interface không có retry riêng chỉ vì method mang `@GetExchange`. Việc thử lại nằm ở client nền, LoadBalancer, Resilience4j/Spring Retry hoặc operator Reactor như `retryWhen` của ứng dụng.

Nguyên tắc chung:

- Phân loại lỗi có thể phục hồi trước khi retry: connect timeout, HTTP 429/503 theo contract, lỗi quá tải.
- Giới hạn **số lần thử tổng, backoff và deadline**; tránh retry cùng lúc ở client, gateway và mesh.
- Với POST/PATCH hoặc thao tác có tác dụng phụ, chỉ retry khi có idempotency/deduplication thực sự.
- Kiểm tra retry có chọn lại cùng instance hay khác instance; tên framework không bảo đảm chuyển đích.
- Cấu hình connection pooling và concurrency limit để retry không tạo bão request.

Một request đã tới server và được xử lý thành công nhưng response bị mất có thể bị thực hiện lại. **Đây là vấn đề ngữ nghĩa phân tán**, không phải vấn đề mà annotation client tự giải quyết.

## 11. Circuit breaker và fallback

Một số đội chọn Feign vì có cách khai báo fallback quen thuộc:

~~~java
@FeignClient(
    name = "catalog-service",
    path = "/api/items",
    fallback = CatalogFallback.class
)
interface CatalogFeignApi {
    @GetMapping("/{id}")
    ItemDto findById(@PathVariable("id") String id);
}
~~~

Đây là **minh họa một cấu hình Feign có fallback**, không tự chạy nếu chỉ copy đoạn interface. Để fallback hoạt động, cần Spring Cloud CircuitBreaker integration, dependency, property bật circuit breaker, implementation `CatalogFallback` là Spring bean phù hợp, và cấu hình phiên bản tương ứng. Không được hiểu `fallback=...` là một `try/catch` tự động trong mọi dự án có Feign.

Với HTTP Interface, thường đặt resilience ở một lớp bao quanh proxy, chẳng hạn `CatalogGateway` gọi `CatalogHttpApi` và áp dụng circuit breaker, fallback hoặc bulkhead qua thư viện được dự án lựa chọn. Cách này có nhiều mã cấu hình hơn nhưng rõ ranh giới giữa **transport API** và **chính sách phục hồi nghiệp vụ**.

Ví dụ fallback nghiệp vụ an toàn có thể trả cache read-only được đánh dấu stale khi catalog tạm thời lỗi. Nhưng với **tạo đơn hàng, ghi tồn kho hay thanh toán**, fallback giả vờ thành công khi downstream chưa xử lý có thể gây sai lệch dữ liệu nghiêm trọng.

Khi lựa chọn, hỏi đội vận hành: có thật sự cần fallback cho loại API đó không, cần circuit breaker theo service hay endpoint, và có phân biệt lỗi dữ liệu với lỗi hạ tầng không?

## 12. Logging, tracing, authentication và cấu hình chung

Công cụ client không thể thay thế observability và bảo mật. Cả hai cách tiếp cận cần:

- Correlation/trace ID xuyên qua caller và downstream.
- Metric HTTP request duration, status, timeout, retry attempts và instance được chọn.
- Log lỗi có phân loại, không ghi access token/cookie hoặc body nhạy cảm.
- Authentication và phân quyền service-to-service theo scope rõ ràng.
- Quy tắc cho token propagation khi cần truyền user context.

**HTTP Interface:** config tập trung ở builder và adapter. Với RestClient, dùng request interceptors, default headers hoặc observation theo Spring/Boot integration; với WebClient, dùng filters/connector configuration phù hợp.

**OpenFeign:** có extension points như `RequestInterceptor`, `ErrorDecoder`, `Logger.Level`, encoder/decoder và capability tùy cấu hình. Có thể tích hợp Micrometer/Observation khi dependency hỗ trợ hiện diện và tính năng được bật. Không cho rằng mọi metric đều tự có trong tất cả release train.

Ví dụ header request động có thể được khai báo ở cả hai kiểu interface:

~~~java
ItemDto findById(
    @PathVariable("id") String id,
    @RequestHeader("X-Correlation-Id") String correlationId
);
~~~

Nếu một interface đã khai báo method chỉ nhận `id`, ví dụ này là **chữ ký thay thế**, không phải overload cần đăng ký thêm. Với trace propagation tự động, nên ưu tiên instrumentation chuẩn thay vì tự quản lý header ở hàng chục method.

### Cấu hình theo từng downstream

Khi dự án gọi nhiều service:

| Mục tiêu | HTTP Interface | OpenFeign |
|---|---|---|
| URL theo service ID | Mỗi proxy dùng client nền có base URL logic | `@FeignClient(name=...)` khi dùng discovery |
| Timeout khác nhau theo downstream | Tạo client/builder/proxy theo nhóm | Cấu hình `openfeign.client.config.<name>` |
| Header chung | RestClient interceptors hoặc WebClient filters | RequestInterceptor hoặc config Feign |
| Error mapping riêng | Status handlers/mapper tại adapter hoặc gateway | ErrorDecoder theo client |
| Retry policy riêng | Resilience layer hoặc HTTP stack | Retryer/circuit-breaker integration |
| Logging | Spring HTTP client + observation | Feign logging/capability + observation |
| Authentication | HTTP client interceptors/filters | Interceptors và tích hợp OAuth2 nếu có |

Khi số downstream lớn, sự nhất quán cấu hình quan trọng hơn vẻ ngắn gọn của interface: nên thống nhất naming, timeout defaults, exception mapping và test contract.

## 13. Testing: kiểm tra contract, service ID và lỗi thực

Các thử nghiệm nên tách ba lớp:

1. **Unit test nghiệp vụ:** mock `CatalogHttpApi` hoặc `CatalogFeignApi` để kiểm tra xử lý DTO/exception, không gọi mạng.
2. **HTTP client contract test:** dùng một HTTP server giả như WireMock, MockWebServer hoặc server thử nghiệm để xác minh HTTP method, path, query, headers, body và status mapping.
3. **Integration test LoadBalancer:** hai instance thật hoặc stub được đăng ký qua discovery, kiểm tra service ID và thuật toán chọn instance trong điều kiện danh sách ổn định.

Nếu chỉ mock interface, bạn chưa chứng minh annotation đúng URL. Nếu chỉ dùng một backend thật, bạn chưa chứng minh sự phân phối qua LoadBalancer.

### Một bảng test chung cho cả hai client

| Tình huống | HTTP Interface | OpenFeign |
|---|---|---|
| GET theo ID | Proxy tạo đúng `GET /api/items/{id}` | Feign tạo đúng `GET /api/items/{id}` |
| Query và body | `@RequestParam`/`@RequestBody` được encode đúng | Spring MVC contract được encode đúng |
| Header idempotency | Giá trị được gửi theo request | Giá trị được gửi theo request |
| HTTP 404 | Mapping theo RestClient/WebClient | Mapping theo ErrorDecoder |
| HTTP 503 | Phân loại lỗi downstream | Phân loại lỗi downstream |
| Không có instance | Lỗi trước khi có response HTTP | Lỗi trước khi có response HTTP |
| Instance dừng sau khi chọn | Transport error/timeout | Transport error/timeout |
| Retry POST | Không được tạo resource trùng nếu contract chống lặp | Tương tự |
| Tracing | Có service ID, downstream, status | Có service ID, downstream, status |
| Thay đổi API schema | DTO/codec bắt đúng mismatch | DTO/decoder bắt đúng mismatch |

Để kiểm chứng hai instance, có thể cho backend trả header `X-Instance-Id` hoặc trường `instanceId` chỉ trong môi trường thử nghiệm rồi gọi nhiều lần. Không phản chiếu các địa chỉ hoặc thông tin vận hành nhạy cảm ra public API.

### Cấu hình discovery tĩnh cho lab

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

Khởi động hai bản backend cùng service ID và dùng policy Round Robin mặc định hoặc policy được cấu hình rõ. Một chuỗi gọi ngắn có thể không chia đều nếu có nhiều caller/health/cache; cần đo số lượt đủ lớn, theo dõi log và trạng thái supplier.

## 14. Ma trận chọn công cụ theo loại dự án

| Nhu cầu của dự án | Hướng thường phù hợp hơn | Lý do / điều kiện |
|---|---|---|
| Dự án mới đã dùng RestClient/WebClient và muốn giảm dependency client riêng | **HTTP Interface** | Dựa trên HTTP stack Spring Framework đang sử dụng |
| Dự án lâu năm dùng nhiều `@FeignClient` ổn định | **Giữ OpenFeign** nếu đáp ứng mục tiêu | Tránh migration không mang giá trị; team đã có tooling và contract |
| Spring MVC blocking API đơn giản | **Cả hai** | Chọn theo cấu hình, error handling và kinh nghiệm team |
| WebFlux non-blocking, SSE hoặc streaming dài | **HTTP Interface + WebClientAdapter** | Return `Mono`/`Flux` và quản lý subscription phù hợp |
| Muốn cấu hình per-client theo service name bằng properties sẵn có | **OpenFeign** có lợi thế | Ecosystem client config đã trưởng thành |
| Muốn kiểm soát trực tiếp HTTP stack, filter và request factory của Spring | **HTTP Interface** có lợi thế | Adapter dùng RestClient/WebClient có sẵn |
| Cần fallback Feign hiện đã được cấu hình với circuit breaker | **Giữ OpenFeign** đến khi có phương án tương đương | Fallback không tự xuất hiện ở HTTP Interface |
| Chỉ có vài downstream và muốn giữ cấu hình nhỏ | **HTTP Interface** thường đơn giản | Tạo một số proxy rõ ràng, ít cơ chế framework bổ sung |
| Yêu cầu đặc thù encoder, multipart, OAuth hoặc logging | **Đánh giá bằng spike** | Hai bên có extension points khác nhau, cần kiểm chứng tích hợp |
| Cần giao tiếp gRPC, Kafka hoặc event sourcing | **Không giải quyết bằng chọn một trong hai** | Cả hai là HTTP clients; xem lại protocol/kiến trúc |

Không nên xem ma trận như thứ hạng hiệu năng cố định. **Throughput và latency thực tế** phụ thuộc transport, connection pool, server, concurrency, serialization, circuit breaker và cấu hình, không chỉ annotation hoặc framework tạo proxy.

### Năm câu hỏi quyết định

1. **Mô hình xử lý:** ứng dụng dựa trên Spring MVC/blocking hay WebFlux/reactive?
2. **Tài sản hiện có:** bao nhiêu Feign clients, decoder/interceptor/fallback và integration tests đang ổn định?
3. **Nhu cầu vận hành:** cần bao nhiêu cấu hình riêng theo service, telemetry và policy retry?
4. **Mức độ tùy biến:** ứng dụng muốn chuẩn hóa trên RestClient/WebClient hay đã đầu tư hạ tầng Feign?
5. **Chi phí chuyển đổi:** có yêu cầu kỹ thuật thực sự chưa được công cụ hiện tại đáp ứng, hay chỉ muốn đổi phong cách annotation?

## 15. Quy trình migration từ Feign sang HTTP Interface

Nếu muốn chuyển một số Feign clients, đừng thực hiện kiểu tìm-thay `@GetMapping` thành `@GetExchange` trên toàn repository. Cách làm có kiểm soát:

1. **Lập inventory** từng Feign client: service name, path, header, timeout, retry, error decoder, interceptor, fallback, circuit breaker, auth, tests.
2. **Chọn một client đơn giản** (thường GET, không streaming hoặc multipart phức tạp) để làm proof-of-concept.
3. **Viết HTTP Interface tương đương** với `@HttpExchange` và các annotation phù hợp; giữ contract HTTP/DTO.
4. **Tạo proxy qua adapter** với `@LoadBalanced RestClient.Builder` hoặc `WebClient.Builder` và `baseUrl("http://service-id")`.
5. **Chuyển chính sách resilience**: status mapping, timeout, retry budgets, idempotency, circuit breaker và fallback.
6. **So sánh HTTP request thực tế** bằng một stub server; kiểm tra path, query, headers, body, media type và encoding.
7. **Chạy integration test discovery/LoadBalancer** với ít nhất hai instance và các trường hợp instance rỗng/hỏng.
8. **Bổ sung log/metric/tracing tương đương** trước khi chuyển traffic; kiểm tra security header.
9. **Phát hành từng bước**, theo dõi error rate và p95/p99; giữ rollback nếu contract/observability thay đổi.
10. **Loại bỏ dependency Feign** chỉ sau khi chắc chắn không còn client, config hoặc capability cần dùng.

Một số lỗi migration thường gặp:

- Đặt `baseUrl` thành host thật thay vì service ID, vô tình bỏ LoadBalancer.
- Bỏ quên `@EnableFeignClients` khi vẫn còn Feign clients sau migration một phần.
- Mất timeout riêng theo từng service vì dùng chung một RestClient.Builder chưa tách cấu hình.
- Đổi tên exception mà không sửa exception mapping ở service nghiệp vụ.
- Không chuyển error decoder/fallback hoặc quy tắc cho HTTP 404/503.
- Retry POST trước đây có kiểm soát giờ bị lặp ở cả gateway và client mới.
- Chuyển mã từ blocking sang reactive nhưng vẫn gọi `block()` trên event-loop.
- Copy annotation method có prefix URL trùng hoặc sai media type.

Migration thành công cần chứng minh **hành vi HTTP và SLO không thoái hóa**, chứ không chỉ chứng minh project build.

## 16. Bài thực hành so sánh có kiểm chứng

**Bối cảnh:** `order-service` gọi `catalog-service` với hai instance cục bộ `localhost:18081` và `localhost:18082`. Các instance có một API `GET /api/items/42` và trả header `X-Instance-Id` để xác định đích trong lab.

### Thí nghiệm A — HTTP Interface

- Định nghĩa `CatalogHttpApi` và bean `CatalogHttpInterfaceConfiguration` theo phần 1 và 4.
- Cấu hình discovery tĩnh cho `catalog-service`.
- Gọi `catalogHttpApi.findById("42")` nhiều lần; ghi request method/path thực tế ở backend và instance được chọn.
- Gọi ID không tồn tại, tạo HTTP 404 và quan sát exception mapping của RestClient.
- Dừng một instance nhưng chưa cập nhật discovery; quan sát lỗi trong khoảng supplier vẫn cung cấp instance đó.

### Thí nghiệm B — OpenFeign

- Thay proxy gọi bằng `CatalogFeignApi`, bật `@EnableFeignClients`.
- Dùng cùng service ID, discovery list và endpoints.
- Gọi lại các case ở thí nghiệm A; so sánh HTTP request và loại exception.
- Thiết lập timeout ngắn có chủ đích theo `openfeign.client.config.catalog-service`; so sánh với timeout tương ứng của HTTP Interface.
- Nếu muốn đo retry, bật chính sách riêng cho từng phương án nhưng đặt cùng tổng deadline và cùng điều kiện lỗi.

### Bảng ghi kết quả

| Tiêu chí | HTTP Interface | OpenFeign |
|---|---|---|
| Chữ ký interface | `@HttpExchange` / `@GetExchange` | `@FeignClient` / `@GetMapping` |
| Method/path/query thực tế | Ghi kết quả | Ghi kết quả |
| Service ID được chọn | Ghi từ log/trace | Ghi từ log/trace |
| Số instance được dùng | Ghi kết quả | Ghi kết quả |
| HTTP 404 -> loại lỗi ứng dụng | Ghi kết quả | Ghi kết quả |
| HTTP 503 -> loại lỗi ứng dụng | Ghi kết quả | Ghi kết quả |
| Connect/read timeout | Ghi kết quả | Ghi kết quả |
| Retry attempts | Ghi kết quả | Ghi kết quả |
| Header bảo mật/correlation | Kiểm tra | Kiểm tra |
| Độ trễ p95 và resource | Đo trong cùng điều kiện | Đo trong cùng điều kiện |

Đừng tự suy rằng phương án ít dòng code sẽ có latency thấp hơn. Khi đo, giữ nguyên backend, payload, pool, concurrency và số lần thử để tránh so sánh không công bằng.

## 17. Checklist kiến trúc và kết luận

Trước khi chọn HTTP Interface hoặc OpenFeign, hãy xác nhận:

- Đội hiểu rõ **service ID** và các instance được discovery/health supplier cung cấp.
- HTTP Interface dùng proxy qua RestClientAdapter/WebClientAdapter và **client nền load-balanced** khi cần.
- OpenFeign dùng đúng `@FeignClient(name=...)` và không vô tình cấu hình URL cố định nếu muốn phân phối instance.
- Cú pháp annotation và prefix path được kiểm tra qua HTTP test, không chỉ qua Java compile.
- Mô hình blocking/reactive phù hợp với web stack và SLO của ứng dụng.
- Status mapping, decoder, exception, timeout, retry, deadline và fallback có hợp đồng nhất quán.
- Các thao tác ghi có idempotency và hệ thống tránh retry storm.
- Connection pool, health check, cache, zone và chính sách chọn instance được cấu hình theo nhu cầu.
- Tracing, log và metric đủ phân biệt lỗi chọn instance, lỗi kết nối, HTTP 4xx/5xx và lỗi decode.
- Nếu đang migration, có test contract, đo hiệu năng và kế hoạch rollback.

**Kết luận:** **Spring HTTP Service Interface** phù hợp khi muốn dùng cách khai báo HTTP type-safe ngay trên HTTP stack của Spring Framework, đặc biệt khi dự án dùng `RestClient` hoặc `WebClient` và có nhu cầu reactive/streaming. **Spring Cloud OpenFeign** phù hợp khi dự án đã có hệ sinh thái Feign ổn định và tận dụng cấu hình theo client name, encoder/decoder, interceptor cùng các tích hợp resilience. Cả hai đều có thể gọi qua **Spring Cloud LoadBalancer**, nhưng cần cấu hình client đúng để hostname logic được phân giải thành `ServiceInstance`. Lựa chọn tốt nhất là lựa chọn đáp ứng **hợp đồng API, mô hình xử lý, nhu cầu vận hành và chi phí bảo trì** của dự án — không phải công cụ có annotation ngắn hơn.

