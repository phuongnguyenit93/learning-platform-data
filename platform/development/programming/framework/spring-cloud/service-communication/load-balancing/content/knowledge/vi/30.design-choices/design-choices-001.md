# Chọn RestTemplate, RestClient, WebClient, Feign hay HTTP Interface

Spring Cloud LoadBalancer tích hợp được với nhiều HTTP client, nhưng **không có một lựa chọn tốt nhất cho mọi ứng dụng**. Việc chọn client nên dựa trên mô hình xử lý của service, yêu cầu streaming/concurrency, cách nhóm muốn khai báo HTTP contract, mức độ tương thích với code hiện có và khả năng vận hành.

Năm lựa chọn thường gặp:

- **RestTemplate**: client đồng bộ quen thuộc, phù hợp hệ thống đang sử dụng ổn định và cần thay đổi ít.
- **RestClient**: API đồng bộ hiện đại của Spring Framework, phù hợp phần lớn code Spring MVC mới.
- **WebClient**: API reactive/non-blocking, phù hợp khi luồng xử lý cần giữ tính reactive hoặc streaming.
- **OpenFeign**: client khai báo bằng interface và annotation, phù hợp khi muốn mô tả HTTP API theo kiểu declarative.
- **HTTP Interface**: interface HTTP do Spring Framework cung cấp; có thể chạy trên RestClient hoặc WebClient, nên đặc tính blocking/reactive và LoadBalancer phụ thuộc adapter bên dưới.

Bài thuộc chương **Lựa chọn thiết kế** của module Spring Cloud LoadBalancer. Trọng tâm là quyết định client nào phù hợp với ứng dụng, cách tích hợp đúng với **service ID**, và các hệ quả về timeout, connection pool, retry, testing và khả năng bảo trì.

## 1. Bắt đầu từ mô hình xử lý của ứng dụng

Trước khi so sánh API, xác định caller đang chạy theo mô hình nào:

~~~mermaid
flowchart TD
    A["Service cần gọi HTTP downstream"]
    B{"Luồng xử lý hiện tại?"}
    C["Imperative / blocking"]
    D["Reactive / non-blocking"]
    E{"Đang có code RestTemplate<br/>ổn định?"}
    F["Giữ RestTemplate<br/>và tích hợp LoadBalancer"]
    G["Dùng RestClient<br/>cho code đồng bộ mới"]
    H["Dùng WebClient<br/>giữ reactive chain"]
    I{"Cần khai báo API<br/>bằng interface?"}
    J["OpenFeign<br/>nếu phù hợp hệ sinh thái"]
    K["HTTP Interface<br/>chọn RestClient/WebClient adapter"]
    A --> B
    B -->|"Blocking"| C --> E
    E -->|"Có"| F
    E -->|"Không / code mới"| G
    B -->|"Reactive"| D --> H
    C -->|"Cần declarative interface"| I
    D -->|"Cần interface proxy"| I
    I --> J
    I --> K
~~~

Đây là **đường ra quyết định gợi ý**, không phải luật bắt buộc. Một ứng dụng có thể dùng nhiều client vì có nhiều loại downstream; điều cần tránh là để mỗi module tự chọn client, retry và timeout theo cách không nhất quán.

Ba câu hỏi cần trả lời trước:

1. **Caller có chấp nhận blocking không?** Nếu đang ở Spring MVC/imperative service, RestClient, RestTemplate hoặc Feign thường phù hợp. Nếu đang ở WebFlux reactive chain, ưu tiên WebClient hoặc HTTP Interface chạy trên WebClient.
2. **Muốn viết lời gọi theo cách nào?** Fluent API, declarative interface hay một abstraction nghiệp vụ riêng?
3. **Ai quản lý kết nối và resilience?** Cần chỉ rõ HTTP transport, pool, timeout, retry, metrics và LoadBalancer nằm ở lớp nào.

## 2. Bảng so sánh nhanh năm lựa chọn

| Tiêu chí | RestTemplate | RestClient | WebClient | OpenFeign | HTTP Interface |
|---|---|---|---|---|---|
| Kiểu API | Imperative | Imperative, fluent | Reactive, fluent | Declarative interface | Declarative interface |
| Blocking mặc định | Có | Có | Không khi dùng reactive; có thể bị block bởi caller | Có | Theo adapter |
| Streaming/backpressure reactive | Hạn chế | Không phải mục tiêu chính | Có | Không phải mô hình reactive | Có nếu dùng WebClient adapter |
| Tích hợp LoadBalancer | `@LoadBalanced RestTemplate` | `@LoadBalanced RestClient.Builder` | `@LoadBalanced WebClient.Builder` | Feign LB client khi có integration | Kế thừa từ RestClient/WebClient |
| Cách khai báo endpoint | URL và method trong code | URL và method trong code | URL và reactive operators | `@FeignClient` và mapping annotations | `@HttpExchange`, `@GetExchange`... |
| Kiểm soát HTTP transport | RequestFactory | RequestFactory | Connector/ConnectionProvider | Feign Client/delegate | Adapter được chọn |
| Phù hợp nhất | Code đồng bộ hiện có | Code đồng bộ mới | Reactive/streaming | Declarative blocking client | Contract interface theo chuẩn Spring |
| Rủi ro thường gặp | Dùng nhầm bean không LB | Tạo client từ builder thường | Dùng WebClient thường hoặc block event-loop | URL cố định bỏ qua LB | Proxy dùng nhầm adapter/client |

**Không suy ra LoadBalancer chỉ từ tên client.** Mỗi lựa chọn cần đúng bean, filter, interceptor hoặc delegate tích hợp Spring Cloud LoadBalancer. Một `RestClient.create("http://catalog-service")` thông thường không trở thành load-balanced chỉ vì trong project có starter.

## 3. RestTemplate: phù hợp khi code hiện có đang ổn định

`RestTemplate` là HTTP client đồng bộ lâu đời của Spring. Nếu ứng dụng đã có nhiều lời gọi, interceptors, request factory, message converters và test ổn định, việc tiếp tục sử dụng có thể hợp lý.

### Tích hợp với service ID

~~~java
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
class CatalogRestTemplateConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate catalogRestTemplate(RestTemplateBuilder builder) {
        return builder.build();
    }
}
~~~

Sử dụng bean:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestTemplate;

@Component
class CatalogRestTemplateClient {

    private final RestTemplate restTemplate;

    CatalogRestTemplateClient(
            @Qualifier("catalogRestTemplate")
            RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    ProductDto find(long id) {
        return restTemplate.getForObject(
                "http://catalog-service/api/products/{id}",
                ProductDto.class,
                id);
    }
}
~~~

`catalog-service` ở đây là **service ID** do Spring Cloud LoadBalancer resolve qua danh sách instance. `@LoadBalanced` phải nằm trên bean RestTemplate được sử dụng; tạo `new RestTemplate()` ở một class khác sẽ không tự có interceptor.

### Khi nên chọn

- Codebase đang sử dụng RestTemplate rộng rãi.
- Luồng xử lý là blocking/imperative.
- Muốn giảm rủi ro migration trong một release.
- RequestFactory, interceptors và cách kiểm thử hiện tại đã được chuẩn hóa.

### Khi nên cân nhắc lựa chọn khác

- Đang viết code đồng bộ mới và muốn API fluent hơn: xem RestClient.
- Cần reactive composition, streaming hoặc backpressure: xem WebClient.
- Muốn interface declarative: xem OpenFeign hoặc HTTP Interface.

Không cần chuyển tất cả RestTemplate chỉ để “được dùng LoadBalancer”; RestTemplate vẫn có thể tích hợp client-side load balancing khi cấu hình đúng.

## 4. RestClient: lựa chọn mặc định đáng cân nhắc cho code đồng bộ mới

`RestClient` được Spring Framework giới thiệu từ **Spring Framework 6.1**. API fluent giúp code dễ đọc, nhưng mô hình thực thi vẫn là **blocking**.

### Tích hợp LoadBalancer

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogRestClientConfiguration {

    @Bean("catalogLoadBalancedBuilder")
    @LoadBalanced
    RestClient.Builder catalogLoadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean("catalogRestClient")
    RestClient catalogRestClient(
            @Qualifier("catalogLoadBalancedBuilder")
            RestClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

Gọi API:

~~~java
ProductDto product = catalogRestClient.get()
        .uri("/api/products/{id}", 42)
        .retrieve()
        .body(ProductDto.class);
~~~

### Điểm mạnh

- API fluent, dễ đọc và dễ tổ chức theo gateway/service adapter.
- Tích hợp với Spring message converters và hệ sinh thái Spring.
- Có thể dùng RequestFactory phù hợp, ví dụ JDK HttpClient hoặc Apache HttpClient 5, để kiểm soát pool và timeout.
- Blocking model đơn giản cho service Spring MVC và code nghiệp vụ imperative.

### Điểm cần chú ý

- `RestClient` **không phải reactive**; request thread chờ kết quả.
- Phải dùng đúng `@LoadBalanced RestClient.Builder`, sau đó inject đúng `RestClient` được tạo từ builder đó.
- Nếu tạo `RestClient.create(...)` hoặc `RestClient.builder()` ở nơi khác, client mới không tự kế thừa LoadBalancer interceptor.
- Nếu project dùng builder/customizer do Spring Boot quản lý cho observability, SSL hoặc converters, cần kiểm tra cách cấu hình builder tùy version để không vô tình bỏ các customizations đó.

**Khuyến nghị thực tế:** với một service Spring MVC mới, nếu không cần declarative interface và không có lý do đặc biệt cho Feign, RestClient là lựa chọn đồng bộ tốt để bắt đầu.

## 5. WebClient: chọn khi cần reactive hoặc streaming

`WebClient` là client non-blocking của Spring WebFlux. Nó phù hợp khi caller cần ghép nhiều lời gọi bất đồng bộ, xử lý stream, backpressure hoặc đang dùng WebFlux end-to-end.

### Tích hợp LoadBalancer

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class CatalogWebClientConfiguration {

    @Bean("catalogLoadBalancedWebClientBuilder")
    @LoadBalanced
    WebClient.Builder catalogLoadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean("catalogWebClient")
    WebClient catalogWebClient(
            @Qualifier("catalogLoadBalancedWebClientBuilder")
            WebClient.Builder builder) {
        return builder
                .baseUrl("http://catalog-service")
                .build();
    }
}
~~~

Lời gọi reactive:

~~~java
Mono<ProductDto> product = catalogWebClient.get()
        .uri("/api/products/{id}", 42)
        .retrieve()
        .bodyToMono(ProductDto.class);
~~~

### Điểm mạnh

- Non-blocking I/O khi sử dụng reactive đúng cách.
- Hỗ trợ streaming và composition qua `Mono`/`Flux`.
- Hợp với WebFlux, reactive database driver và các dependency non-blocking.
- Có thể kiểm soát connector và Reactor Netty connection provider.

### Điểm cần chú ý

- Chỉ dùng WebClient **không làm toàn bộ ứng dụng thành non-blocking**. Nếu gọi JDBC/JPA blocking trong reactive callback, event-loop có thể bị chặn.
- Gọi `.block()` trên event-loop là anti-pattern; trong Spring MVC, `.block()` có thể chặn servlet worker dù không phải event-loop.
- Pool của Reactor Netty có đặc tính và giới hạn riêng; cần quan sát theo remote host, pending acquire và response latency.
- `@LoadBalanced` phải được gắn vào builder thực sự dùng để tạo client. `WebClient.create("http://catalog-service")` không tự có LoadBalancer filter.

### Khi nào không nên chọn WebClient?

Nếu toàn bộ service là Spring MVC blocking, downstream không cần streaming/reactive và đội ngũ không có nhu cầu reactive composition, dùng WebClient rồi `.block()` khắp nơi thường tăng độ phức tạp mà không mang lại lợi ích rõ ràng.

## 6. OpenFeign: declarative client cho HTTP API

OpenFeign cho phép mô tả remote API bằng Java interface và annotation. Nó phù hợp khi muốn giảm boilerplate của request/response và chuẩn hóa client theo service.

### Khai báo Feign client theo service ID

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping("/api/products/{id}")
    ProductDto findById(@PathVariable("id") long id);
}
~~~

Bật scanning:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.openfeign.EnableFeignClients;

@SpringBootApplication
@EnableFeignClients(basePackages = "com.example.orders.client")
class OrderApplication {
}
~~~

Dependencies thường cần:

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-openfeign")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

Khi không khai báo URL cố định và có Spring Cloud LoadBalancer integration tương thích, Feign client có thể sử dụng `FeignBlockingLoadBalancerClient` để chọn instance theo service ID.

### Điểm mạnh

- Interface thể hiện rõ service và operation.
- Giảm code lặp về HTTP method, path và binding.
- Hợp với ứng dụng imperative/blocking.
- Có cơ chế cấu hình decoder, encoder, interceptors và client theo context.

### Điểm cần chú ý

- OpenFeign theo mô hình blocking; không chọn nó nếu yêu cầu cốt lõi là reactive end-to-end.
- `@FeignClient(url=...)` hoặc property URL tường minh sẽ gọi endpoint cố định và bỏ qua việc chọn instance theo name cho client đó.
- Cần kiểm tra HTTP delegate thực tế nếu tự cấu hình `feign.Client`.
- Spring Cloud OpenFeign mặc định cấu hình `Retryer.NEVER_RETRY`; không suy ra retry sẽ tự hoạt động chỉ vì có LoadBalancer. Hãy cấu hình rõ và xét idempotency.
- Annotation interface có thể tạo cảm giác “chỉ là method Java”, nhưng đây vẫn là lời gọi mạng có timeout, lỗi transport, status và contract.

### Khi nên chọn

- Codebase đã chuẩn hóa OpenFeign.
- Team thích khai báo API bằng interface.
- Các downstream call chủ yếu blocking và có contract rõ.
- Cần cấu hình per-client trong hệ sinh thái Spring Cloud OpenFeign.

## 7. HTTP Interface: declarative interface của Spring, adapter quyết định cách chạy

HTTP Interface dùng `@HttpExchange`, `@GetExchange`, `@PostExchange` để khai báo HTTP contract trong Java interface. Khác OpenFeign, nó là cơ chế của Spring Framework và **không tự định nghĩa transport hay LoadBalancer**.

Interface ví dụ:

~~~java
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.bind.annotation.PathVariable;

@HttpExchange("/api/products")
interface CatalogHttpApi {

    @GetExchange("/{id}")
    ProductDto findById(@PathVariable("id") long id);
}
~~~

### Dùng RestClient adapter

Nếu muốn blocking và đã có `RestClient` load-balanced:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Bean
CatalogHttpApi catalogHttpApi(
        @Qualifier("catalogRestClient") RestClient client) {

    HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(
                    RestClientAdapter.create(client))
                    .build();

    return factory.createClient(CatalogHttpApi.class);
}
~~~

Proxy gọi qua chính RestClient adapter, do đó **kế thừa LoadBalancer** từ RestClient được truyền vào.

### Dùng WebClient adapter

Nếu muốn reactive, khai báo interface trả về `Mono`/`Flux` và tạo proxy từ WebClient load-balanced:

~~~java
import reactor.core.publisher.Mono;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange("/api/products")
interface ReactiveCatalogHttpApi {

    @GetExchange("/{id}")
    Mono<ProductDto> findById(long id);
}
~~~

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.support.WebClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

@Bean
ReactiveCatalogHttpApi reactiveCatalogHttpApi(
        @Qualifier("catalogWebClient") WebClient client) {

    HttpServiceProxyFactory factory =
            HttpServiceProxyFactory.builderFor(
                    WebClientAdapter.create(client))
                    .build();

    return factory.createClient(ReactiveCatalogHttpApi.class);
}
~~~

Các package/API cụ thể phải tương thích Spring Framework version của ứng dụng.

### Điểm mạnh và giới hạn

- Interface là contract gọn, dễ mock và dùng lại.
- Có thể chọn RestClient adapter cho blocking hoặc WebClient adapter cho reactive.
- Không cần một transport riêng chỉ để dùng HTTP Interface.
- Đặc tính timeout, pool, LoadBalancer và retry **đến từ client/adapter bên dưới**.
- Không được nhầm `@HttpExchange` với `@LoadBalanced`; annotation interface không tự bật discovery hay chọn instance.

**HTTP Interface đặc biệt phù hợp** khi team muốn declarative interface nhưng vẫn muốn giữ quyền chọn RestClient/WebClient và cấu hình transport của Spring.

## 8. Chọn theo tình huống thực tế

| Tình huống | Lựa chọn nên cân nhắc | Lý do |
|---|---|---|
| Ứng dụng cũ dùng RestTemplate, test ổn định | Giữ RestTemplate | Ít thay đổi, vẫn có thể tích hợp LB |
| Service Spring MVC mới, gọi HTTP đồng bộ | RestClient | Fluent API, blocking model rõ |
| WebFlux gọi nhiều downstream reactive | WebClient | Giữ non-blocking chain và composition |
| Team đã chuẩn hóa declarative blocking clients | OpenFeign | Interface và cấu hình per-client |
| Muốn interface declarative theo Spring Framework | HTTP Interface | Chọn adapter RestClient hoặc WebClient |
| Cần streaming response/reactive backpressure | WebClient hoặc HTTP Interface + WebClient | Reactive pipeline |
| Cần gọi external API bằng URL cố định | Client direct riêng | Không ép external host vào discovery |
| Một module cần cả service ID và external URL | Hai bean client tách biệt | Không trộn direct URL và service ID trong cùng policy |

### Quy tắc ra quyết định

- **Giữ code hiện có** nếu nó ổn định và không có yêu cầu migration.
- **RestClient** là điểm bắt đầu hợp lý cho synchronous Spring MVC mới.
- **WebClient** khi reactive là yêu cầu thực sự của toàn pipeline.
- **OpenFeign** khi declarative client đã là quy ước của team và mô hình blocking phù hợp.
- **HTTP Interface** khi muốn interface Spring-native và chủ động chọn adapter.
- **RestTemplate** cho code đồng bộ hiện có hoặc hệ thống cần tương thích với cấu hình cũ.

Đừng chọn WebClient chỉ vì từ “reactive” nghe có vẻ nhanh hơn; đừng chọn Feign chỉ vì ít dòng code hơn; và đừng chuyển RestTemplate chỉ vì muốn dùng Spring Cloud LoadBalancer.

## 9. Tách business logic khỏi lựa chọn HTTP client

Một thiết kế dễ thay đổi là để business service phụ thuộc vào **interface nghiệp vụ**, còn mỗi HTTP client nằm ở adapter:

~~~mermaid
flowchart LR
    A["OrderApplicationService"]
    B["CatalogGateway<br/>business port"]
    C["RestClient adapter"]
    D["WebClient adapter"]
    E["Feign adapter"]
    F["HTTP Interface adapter"]
    G["Spring Cloud LoadBalancer"]
    H["catalog-service instances"]
    A --> B
    B --> C
    B --> D
    B --> E
    B --> F
    C --> G
    D --> G
    E --> G
    F --> G
    G --> H
~~~

Ví dụ interface nghiệp vụ:

~~~java
public interface CatalogGateway {
    ProductDto findProduct(long id);
}
~~~

Business service chỉ phụ thuộc `CatalogGateway`, không biết RestClient hay Feign:

~~~java
import org.springframework.stereotype.Service;

@Service
class OrderApplicationService {

    private final CatalogGateway catalogGateway;

    OrderApplicationService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    OrderView createOrder(long productId) {
        ProductDto product = catalogGateway.findProduct(productId);
        // Thực hiện quy tắc nghiệp vụ với product đã lấy được.
        return new OrderView(product.id(), product.name());
    }
}
~~~

Adapter triển khai port bằng RestClient:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class RestClientCatalogGateway implements CatalogGateway {

    private final RestClient client;

    RestClientCatalogGateway(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    @Override
    public ProductDto findProduct(long id) {
        return client.get()
                .uri("/api/products/{id}", id)
                .retrieve()
                .body(ProductDto.class);
    }
}
~~~

Lợi ích:

- Business logic không bị gắn với API của một HTTP library.
- Có thể thay adapter bằng Feign/HTTP Interface mà ít ảnh hưởng service nghiệp vụ.
- Unit test business chỉ cần mock `CatalogGateway`.
- Integration test riêng adapter để chứng minh LoadBalancer và transport hoạt động.
- Có thể áp dụng cùng contract lỗi, logging, tracing và timeout policy ở ranh giới gateway.

Không nên tạo abstraction chung quá phức tạp chỉ để bọc mọi method của RestClient. Port nên diễn đạt **nghiệp vụ cần dùng**, không sao chép toàn bộ HTTP API vào một lớp generic.

## 10. So sánh timeout, pool và retry theo client

| Client | Connection/pool nằm ở đâu? | Timeout cấu hình ở đâu? | Retry cần kiểm tra |
|---|---|---|---|
| RestTemplate | RequestFactory và HTTP client bên dưới | RequestFactory/transport | LB retry hoặc resilience layer tùy cấu hình |
| RestClient | RequestFactory và HTTP client bên dưới | RequestFactory/transport | LB retry hoặc resilience layer tùy cấu hình |
| WebClient | ClientConnector, thường Reactor Netty ConnectionProvider | Connect/response/pending acquire và deadline tổng | Reactor retry và/hoặc LB retry, tránh nhiều tầng |
| OpenFeign | Feign Client delegate, có thể HC5/OkHttp/JDK | Feign connect/read timeout và transport | Spring Cloud OpenFeign mặc định `Retryer.NEVER_RETRY`; cấu hình rõ |
| HTTP Interface | Adapter RestClient hoặc WebClient | Theo adapter | Theo adapter; interface không tự thêm retry |

### Timeout không phải một con số duy nhất

Cần phân biệt:

- **Pool acquisition timeout**: chờ một connection rảnh.
- **Connect timeout**: thiết lập TCP tới instance đã chọn.
- **TLS handshake timeout**: hoàn tất TLS nếu dùng HTTPS.
- **Response/read timeout**: chờ response/data theo semantics transport.
- **Deadline tổng**: toàn bộ operation, gồm selection, acquire, connect, response, decode và retry.

Ví dụ client chờ pool 300ms, connect 500ms và response 2s có thể tốn hơn 2s end-to-end. Không giả định `responseTimeout=2s` tự giới hạn toàn bộ operation.

### Retry phải gắn với tính chất nghiệp vụ

- Không retry vô hạn hoặc không backoff khi downstream quá tải.
- Chỉ retry các lỗi có thể phục hồi và được policy cho phép.
- Xác định request đã được gửi chưa; timeout sau khi server xử lý có thể gây kết quả không rõ.
- Với POST tạo đơn/thanh toán, cần idempotency key hoặc cơ chế chống ghi trùng.
- Đặt giới hạn attempts và deadline tổng xuyên các tầng.
- Theo dõi **logical operations** và **HTTP attempts** riêng biệt.

Không phải client nào cũng có cùng retry default. Đặc biệt, đừng giả định Feign có retry giống một WebClient `retryWhen`, hoặc HTTP Interface tự thêm retry chỉ vì dùng annotation.

## 11. Observability và xử lý lỗi

Mỗi lựa chọn client có thể có exception wrapper khác nhau, nhưng cần một **contract vận hành chung**:

| Error category | Ví dụ nguyên nhân | Thông tin nên ghi nhận |
|---|---|---|
| `NO_INSTANCE` | Discovery/filter trả danh sách rỗng | Service ID, candidate count, policy |
| `DNS_RESOLUTION` | Hostname service logic bị DNS resolve do client thiếu LB, hoặc physical host lỗi | Host category logic/physical, selected instance nếu có |
| `POOL_ACQUIRE_TIMEOUT` | Không lấy được connection | Pool pending/leased/max, remote route |
| `CONNECT_TIMEOUT` | TCP tới endpoint vật lý không thành công kịp | Selected endpoint category, connect duration |
| `RESPONSE_TIMEOUT` | Backend/network không trả response kịp | Service ID, instance, response duration |
| `HTTP_4XX/5XX` | Backend trả HTTP status | Status, operation, trace ID |
| `DECODE_ERROR` | Response body không đúng contract | Content type/schema category, không log body nhạy cảm |

Với RestClient/RestTemplate/Feign blocking, trace span thường theo HTTP client instrumentation của transport. Với WebClient reactive, context propagation/tracing cần đúng integration. HTTP Interface kế thừa khả năng quan sát của adapter, không tự tạo một telemetry stack riêng.

**Không log toàn bộ headers/body để tìm lỗi.** Không ghi Authorization, cookie, raw URL có query token hoặc dữ liệu cá nhân. Dùng allowlist gồm service ID, operation/route template, error category, instance label được phép, duration và trace ID.

## 12. Kiểm thử: tách unit, integration và contract

| Tầng | Test điều gì? | Client nào cần kiểm tra? |
|---|---|---|
| Unit business | Quy tắc nghiệp vụ với `CatalogGateway` mock | Không phụ thuộc HTTP client cụ thể |
| Unit adapter | Mapping DTO, status/error mapping, request parameters | Mỗi adapter có thể có test riêng |
| Integration LoadBalancer | Client thật được gắn LB, service ID resolve ra instance URI | RestTemplate, RestClient, WebClient, Feign |
| HTTP Interface integration | Proxy được tạo từ đúng adapter và adapter đã LB | RestClient/WebClient adapter |
| Contract test | Path, headers, status, JSON schema tương thích | Tất cả client cùng contract |
| Failure test | Empty discovery, DNS physical host, timeout, backend 5xx | Client/transport đang dùng |
| Load test | Pool, concurrency, p95/p99, retry amplification | Đường gọi end-to-end qua caller |

### Nguyên tắc integration test

- Dùng Spring context thật cho phần wiring cần xác minh.
- Dùng fake HTTP servers trên port động và đăng ký URI qua `SimpleDiscoveryClient`/`@DynamicPropertySource`.
- Gọi URL logic `http://catalog-service` từ bean client đã cấu hình.
- Cho backend trả `instanceId` khác nhau để chứng minh selection.
- Tắt hoặc kiểm soát retry/cache khi test một attempt.
- Không assert lần đầu luôn chọn A hoặc round-robin chia chính xác trong cửa sổ ngắn.
- Tạo test negative cho client thường nếu môi trường test có thể kiểm soát DNS; không phụ thuộc hostname ngẫu nhiên của CI.

Mock một RestClient hoặc Feign interface không chứng minh LoadBalancer interceptor đã được cài. Cần ít nhất một integration test chạy qua **HTTP transport thật**.

## 13. Những lỗi thiết kế thường gặp

**1. Dùng client thường với service ID rồi trông chờ DNS tự hiểu discovery.** Tên `catalog-service` không tự trở thành service ID của Spring Cloud.

**2. Gắn `@LoadBalanced` lên builder nhưng code lại tạo client từ builder khác.** Annotation chỉ có ý nghĩa ở bean được Spring xử lý và được inject vào đúng nơi.

**3. Dùng URL cố định trong Feign nhưng kỳ vọng LoadBalancer chọn instance.** Kiểm tra cả `@FeignClient(url=...)` và property URL.

**4. Dùng WebClient rồi gọi `.block()` khắp reactive pipeline.** Có thể gây blocking thread và làm mất lợi ích non-blocking.

**5. Đưa JDBC/JPA trực tiếp vào event-loop.** Chuyển blocking call sang scheduler phù hợp hoặc dùng driver non-blocking.

**6. Dùng một connection pool cho mọi mục đích mà không phân biệt route.** Tổng pool và per-route/remote-host limits có semantics khác nhau.

**7. Retry cùng lúc ở Feign, LoadBalancer, Reactor và gateway.** Có thể khuếch đại số attempts và tạo retry storm.

**8. Tạo client mới mỗi request.** Làm mất lợi ích connection pooling, customizers và observability thống nhất.

**9. Để business service phụ thuộc trực tiếp vào HTTP library.** Unit test và migration trở nên khó hơn.

**10. Chọn client theo xu hướng thay vì theo mô hình xử lý.** Reactive, declarative hoặc fluent không tự động làm hệ thống nhanh, bền hay dễ bảo trì hơn.

## 14. Kế hoạch chuyển đổi giữa các client

Không cần đổi toàn hệ thống cùng lúc. Chuyển từng adapter, giữ nguyên service ID và contract.

### RestTemplate → RestClient

1. Xác định request factory, timeout, pool và interceptors hiện tại.
2. Tạo `@LoadBalanced RestClient.Builder` riêng.
3. Chuyển một gateway nhỏ, giữ nguyên path/DTO/error mapping.
4. So sánh metrics, retry và connection pool.
5. Mở rộng sau khi integration tests pass.

### RestClient → HTTP Interface

1. Định nghĩa interface theo endpoint/contract thực tế.
2. Tạo proxy từ RestClient đã load-balanced.
3. Chuyển adapter ở gateway, giữ business port.
4. Kiểm tra path variables, headers, codecs và exception behavior.
5. Không thêm một HTTP client/pool mới nếu adapter hiện tại đã đủ.

### Feign → HTTP Interface

1. Kiểm kê Feign configuration: URL, encoder/decoder, interceptors, error decoder, timeout, retry.
2. Xác định client hiện tại dùng service ID hay URL cố định.
3. Chọn RestClient adapter cho blocking hoặc WebClient adapter cho reactive.
4. Viết integration/contract tests trước khi thay.
5. Chuyển từng client, quan sát error rate và latency trước khi loại cấu hình Feign cũ.

### RestClient → WebClient

Chỉ chuyển khi có lý do reactive/streaming hoặc cần composition non-blocking. Kiểm tra lại mọi dependency downstream: một JDBC call blocking trong pipeline có thể làm mất lợi ích. Đánh giá event-loop, connection provider, context propagation và cancellation.

## 15. Checklist quyết định cuối cùng

Trước khi chọn client cho một service ID, hãy trả lời:

1. Luồng xử lý caller là Spring MVC/imperative hay WebFlux/reactive?
2. Có cần streaming/backpressure hoặc ghép nhiều request bất đồng bộ không?
3. Có code hiện tại ổn định nên giữ lại không?
4. Team muốn fluent API hay declarative interface?
5. Nếu chọn HTTP Interface, adapter bên dưới là RestClient hay WebClient?
6. Bean client thực tế đã được gắn `@LoadBalanced` đúng cách chưa?
7. Có dependency `spring-cloud-starter-loadbalancer` và release train tương thích không?
8. Feign có URL tường minh trong annotation/properties không?
9. Pool, connect/read/response timeout và deadline tổng được quản lý ở đâu?
10. Retry được bật ở tầng nào, attempts tổng bao nhiêu và operation có idempotent không?
11. Có metrics/tracing cho service ID, instance, pool và HTTP errors không?
12. Có integration test chứng minh client chọn được hai instance qua HTTP thật không?
13. Có một gateway/business port để tách business logic khỏi HTTP library không?
14. Có kế hoạch rollout/rollback nếu đổi transport hoặc client không?

**Kết luận:** Không chọn client chỉ theo số dòng code hoặc tên gọi. Với code blocking mới, **RestClient** là lựa chọn đáng cân nhắc; giữ **RestTemplate** nếu code hiện có ổn định; chọn **WebClient** khi cần reactive/streaming thực sự; dùng **OpenFeign** khi muốn declarative blocking client theo quy ước team; và dùng **HTTP Interface** khi muốn interface Spring-native với quyền chọn adapter. Dù chọn cách nào, **LoadBalancer chỉ hoạt động khi client thực tế được tích hợp đúng**, còn pool, timeout, retry, observability và testing vẫn phải được thiết kế ở đúng tầng.

**Tài liệu tham khảo chính thức:**

- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons – RestTemplate, RestClient và WebClient LoadBalancer integrations](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Framework – REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Framework – HTTP Interface Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-http-interface)
- [Spring Cloud OpenFeign – Declarative REST Client](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)

