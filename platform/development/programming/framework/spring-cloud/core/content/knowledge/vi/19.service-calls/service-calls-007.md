# Tạo WebClient.Builder với bộ lọc load balancer

Bài học thuộc chương **Gọi dịch vụ** của module **SPRING_CLOUD_CORE**. Trong ứng dụng Spring WebFlux, `WebClient` là HTTP client reactive để gọi API của dịch vụ khác. Khi kết hợp với Spring Cloud LoadBalancer, một `WebClient.Builder` được đánh dấu `@LoadBalanced` sẽ được gắn bộ lọc chọn instance. Ứng dụng có thể gọi dịch vụ bằng service ID, còn LoadBalancer tìm một instance phù hợp và thay URI logic bằng địa chỉ thực tế trước khi gửi request.

Cấu hình đúng builder rất quan trọng. Một builder load-balanced phải có Spring Cloud LoadBalancer trên classpath, dùng URI chứa service ID, được inject đúng qualifier và giữ các customizer mà Spring Boot cung cấp. Nếu ứng dụng còn gọi endpoint bên ngoài bằng hostname thông thường, nên phân biệt builder load-balanced với builder HTTP thông thường để tránh gửi nhầm request qua cơ chế service discovery.

## 1. Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích vai trò của `WebClient`, `WebClient.Builder` và `ExchangeFilterFunction`.
2. Cấu hình bean `WebClient.Builder` với qualifier `@LoadBalanced`.
3. Bổ sung dependency Spring Cloud LoadBalancer và Spring WebFlux phù hợp.
4. Inject đúng builder load-balanced vào service client.
5. Gọi service bằng URI có service ID thay vì địa chỉ IP/hostname của một instance.
6. Mô tả cách filter chuyển URI logic thành địa chỉ instance được chọn.
7. Giữ các `WebClientCustomizer` của Spring Boot khi tự tạo builder.
8. Phân biệt builder load-balanced với builder HTTP thông thường.
9. Sử dụng `ReactorLoadBalancerExchangeFilterFunction` khi muốn gắn filter tường minh.
10. Tùy biến cấu hình LoadBalancer theo service ID và kiểm tra cách discovery cung cấp instance.
11. Kiểm thử lựa chọn instance, xử lý lỗi, timeout và retry của lời gọi reactive.
12. Chẩn đoán lỗi do thiếu starter, sai service ID, thiếu instance hoặc inject nhầm builder.

## 2. WebClient và bộ lọc load balancer

### 2.1. WebClient.Builder tạo HTTP client

`WebClient` là HTTP client hỗ trợ reactive API. Thông thường ứng dụng tạo client bằng builder:

~~~java
WebClient client = WebClient.builder()
        .baseUrl("https://api.example.com")
        .build();
~~~

`WebClient.Builder` cho phép thiết lập base URL, default header, codec, connector và filter. Sau khi gọi `build()`, ứng dụng nhận một `WebClient` có cấu hình cố định để tái sử dụng.

Trong ứng dụng Spring Boot, builder thường được cấu hình bởi các customizer tự động. Chúng có thể bổ sung observability, codec, connector hoặc các cấu hình chung của ứng dụng. Khi tự khai báo builder bean, cần quyết định có áp dụng các customizer này hay không.

### 2.2. ExchangeFilterFunction can thiệp vào request

`ExchangeFilterFunction` là một thành phần nằm trong chuỗi xử lý request của WebClient. Filter có thể đọc request, thay đổi header, ghi log, đo thời gian, xử lý authentication hoặc chuyển request tới một cơ chế khác trước khi gọi HTTP connector.

Spring Cloud LoadBalancer tích hợp với WebClient bằng một filter reactive. Filter nhận URI chứa service ID, yêu cầu LoadBalancer chọn một `ServiceInstance` và tạo request tới địa chỉ vật lý của instance đó.

Ví dụ request logic:

~~~text
http://inventory-service/api/items/42
~~~

Nếu registry có hai instance:

~~~text
inventory-service
  ├── http://10.20.0.11:8080
  └── http://10.20.0.12:8080
~~~

LoadBalancer chọn một instance, ví dụ instance thứ hai, rồi gửi request tới:

~~~text
http://10.20.0.12:8080/api/items/42
~~~

Code gọi dịch vụ chỉ cần biết service ID. Nó không phải tự truy vấn registry hoặc lưu địa chỉ từng instance.

### 2.3. Luồng xử lý

~~~mermaid
sequenceDiagram
    participant App as Service caller
    participant WC as WebClient
    participant Filter as LoadBalancer filter
    participant LB as ReactiveLoadBalancer
    participant Supplier as ServiceInstanceListSupplier
    participant Registry as Discovery / registry
    participant Instance as Selected instance

    App->>WC: GET http://inventory-service/api/items/42
    WC->>Filter: Exchange request
    Filter->>LB: Chọn instance theo service ID
    LB->>Supplier: Lấy danh sách instance
    Supplier->>Registry: Truy vấn/cached discovery data
    Registry-->>Supplier: ServiceInstance list
    Supplier-->>LB: Danh sách instance
    LB-->>Filter: Instance được chọn
    Filter->>Instance: Gửi request tới host:port thực
    Instance-->>App: HTTP response
~~~

Trong cấu hình discovery-backed thông thường, `ServiceInstanceListSupplier` lấy instance từ DiscoveryClient rồi có thể áp dụng cache hoặc bộ lọc. LoadBalancer chọn một instance từ danh sách đã nhận.

## 3. Dependency cần thiết

Để dùng `@LoadBalanced WebClient.Builder`, ứng dụng cần cả WebFlux và một implementation Spring Cloud LoadBalancer.

Với Maven, dependency thường dùng:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
~~~

Spring Cloud starter cần được quản lý bởi Spring Cloud BOM tương thích với Spring Boot version của dự án. Không tự chọn một version starter độc lập nếu dự án đã import `spring-cloud-dependencies`.

Nếu instance được lấy từ Eureka, Consul hoặc Zookeeper, thêm discovery starter tương ứng. Nếu không có registry-backed DiscoveryClient, Spring Cloud Commons có thể dùng `SimpleDiscoveryClient` với danh sách URI cấu hình tĩnh, phù hợp cho local development hoặc test.

Ví dụ cấu hình Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Không cần tự thêm cả một discovery provider nếu bài toán chỉ cần kiểm thử với danh sách instance tĩnh. Ngược lại, có starter LoadBalancer không tự tạo ra các instance thật; ứng dụng vẫn cần một nguồn cung cấp `ServiceInstance`.

## 4. Tạo WebClient.Builder với @LoadBalanced

### 4.1. Cấu hình cơ bản

Cách đơn giản nhất là khai báo một bean `WebClient.Builder` và đánh dấu bằng `@LoadBalanced`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    public WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

`@LoadBalanced` là qualifier annotation để Spring Cloud nhận diện builder cần tích hợp LoadBalancer. Spring Cloud LoadBalancer cung cấp cơ chế xử lý builder này và gắn filter reactive tương ứng.

Annotation không tự cài đặt discovery provider. Cần có implementation LoadBalancer trên classpath và nguồn instance phù hợp.

### 4.2. Vì sao đánh dấu ở bean method?

Qualifier cần gắn với bean được Spring quản lý. Khi builder được tạo từ một method không có `@Bean`, Spring không quản lý object đó và không thể áp dụng các post-processor/customization cần thiết của integration.

Vì vậy, khai báo builder dưới dạng bean giúp:
- Spring quản lý vòng đời builder.
- Spring Cloud nhận diện bean cần load balancing.
- Service client inject được builder qua qualifier.
- Các cấu hình liên quan được áp dụng nhất quán trong ApplicationContext.

### 4.3. Giữ WebClientCustomizer của Spring Boot

Nếu tự gọi `WebClient.builder()` trong bean method, bạn có thể bỏ qua các `WebClientCustomizer` mà Spring Boot đã auto-configure. Để giữ các customizer có sẵn, có thể áp dụng chúng theo thứ tự:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    public WebClient.Builder loadBalancedWebClientBuilder(
            ObjectProvider<WebClientCustomizer> customizerProvider) {

        WebClient.Builder builder = WebClient.builder();

        customizerProvider.orderedStream()
                .forEach(customizer -> customizer.customize(builder));

        return builder;
    }
}
~~~

`ObjectProvider` cho phép lấy các customizer hiện có mà không cần tự quản lý danh sách. `orderedStream()` giữ thứ tự áp dụng do Spring sắp xếp.

Cách này hữu ích khi ứng dụng cần giữ observability, codec hoặc cấu hình WebClient chung của Spring Boot trong khi vẫn tạo builder có qualifier load-balanced.

## 5. Inject builder và tạo service client

### 5.1. Inject bằng qualifier

Khi ứng dụng chỉ có một builder load-balanced, có thể inject builder được đánh dấu `@LoadBalanced`:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public class InventoryClient {

    private final WebClient webClient;

    public InventoryClient(
            @LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<Item> getItem(String itemId) {
        return webClient.get()
                .uri("http://inventory-service/api/items/{id}", itemId)
                .retrieve()
                .bodyToMono(Item.class);
    }
}
~~~

Ví dụ này minh họa client gọi dịch vụ inventory theo service ID. `InventoryClient` tạo `WebClient` một lần trong constructor và tái sử dụng cho các request tiếp theo.

`WebClient` là immutable sau khi build nên phù hợp để dùng như dependency lâu dài của service client. Không cần gọi `builder.build()` cho mỗi request nếu cấu hình client không thay đổi.

### 5.2. Dùng URI có service ID

URI cần có dạng:

~~~text
http://<service-id>/<path>
~~~

Ví dụ:

~~~java
webClient.get()
        .uri("http://pricing-service/api/prices/{sku}", sku)
        .retrieve()
        .bodyToMono(PriceResponse.class);
~~~

`pricing-service` là service ID mà DiscoveryClient/ServiceInstanceListSupplier nhận diện. Nó không phải tên class Java và cũng không nhất thiết là DNS hostname có thể phân giải trực tiếp.

Không thay URI bằng IP/port của một instance nếu muốn LoadBalancer chọn instance. Khi dùng địa chỉ vật lý cố định, filter không còn service ID để thực hiện lựa chọn.

### 5.3. Dùng URI builder khi có query parameter

~~~java
public Mono<List<Item>> search(String category, int page) {
    return webClient.get()
            .uri(uriBuilder -> uriBuilder
                    .scheme("http")
                    .host("inventory-service")
                    .path("/api/items")
                    .queryParam("category", category)
                    .queryParam("page", page)
                    .build())
            .retrieve()
            .bodyToFlux(Item.class)
            .collectList();
}
~~~

Điểm quan trọng là authority vẫn phải chứa service ID. Filter LoadBalancer cần nhận diện đúng host logic trước khi chuyển request đến instance vật lý.

## 6. Tách builder load-balanced và builder thông thường

Một ứng dụng có thể vừa gọi dịch vụ nội bộ theo service ID, vừa gọi API bên ngoài như payment gateway hoặc public API. Hai loại request có mục đích khác nhau:

- Request nội bộ dùng service ID và cần LoadBalancer.
- Request bên ngoài dùng hostname/URI thực và không cần discovery nội bộ.

Nên khai báo hai builder riêng để code thể hiện rõ ý định.

~~~java
@Configuration
public class WebClientConfiguration {

    @Bean
    @LoadBalanced
    public WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean
    @Primary
    public WebClient.Builder webClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Service cần LoadBalancer inject qualifier:

~~~java
public InventoryClient(
        @LoadBalanced WebClient.Builder builder) {
    this.webClient = builder.build();
}
~~~

Client gọi external API inject builder thường:

~~~java
public PaymentGatewayClient(WebClient.Builder builder) {
    this.webClient = builder
            .baseUrl("https://payments.example.com")
            .build();
}
~~~

`@Primary` trên builder thông thường giúp giải quyết injection không có qualifier khi có nhiều bean cùng kiểu. Với code gọi service nội bộ, luôn dùng `@LoadBalanced` để tránh inject nhầm builder.

Trong cấu hình production, nếu cả hai builder cần observability/customization, hãy áp dụng `WebClientCustomizer` theo cùng nguyên tắc ở phần trước.

## 7. Gắn filter thủ công với ReactorLoadBalancerExchangeFilterFunction

Ngoài việc đánh dấu builder bean bằng `@LoadBalanced`, Spring Cloud LoadBalancer còn cung cấp filter reactive có thể inject trực tiếp:

`ReactorLoadBalancerExchangeFilterFunction`

Khi `spring-cloud-starter-loadbalancer` và `spring-webflux` có trên classpath, Spring Cloud có thể auto-configure filter này.

Ví dụ:

~~~java
import org.springframework.cloud.client.loadbalancer.reactive.ReactorLoadBalancerExchangeFilterFunction;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public class ManualLoadBalancedClient {

    private final WebClient webClient;

    public ManualLoadBalancedClient(
            ReactorLoadBalancerExchangeFilterFunction loadBalancerFilter) {

        this.webClient = WebClient.builder()
                .filter(loadBalancerFilter)
                .build();
    }

    public Mono<String> getInventory() {
        return webClient.get()
                .uri("http://inventory-service/api/inventory")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

Cách này cho thấy rõ filter nào được gắn vào builder. Nó hữu ích khi chỉ một client cụ thể cần load balancing hoặc khi đang xây dựng WebClient theo cách lập trình.

Tuy nhiên, nếu nhiều service client đều cần cùng integration, bean builder được đánh dấu `@LoadBalanced` thường dễ quản lý và inject hơn. Không nên tự gắn cùng filter nhiều lần lên một builder vì có thể làm request đi qua các bước xử lý lặp ngoài ý muốn.

### 7.1. Không nhầm filter reactive với filter cũ

Spring Cloud có các API filter cũ dùng non-reactive LoadBalancer client bên dưới. Với ứng dụng WebFlux, ưu tiên `ReactorLoadBalancerExchangeFilterFunction` để sử dụng `ReactiveLoadBalancer`.

`LoadBalancerExchangeFilterFunction` non-reactive đã được đánh dấu deprecated trong tài liệu hiện hành. Không chọn API cũ cho ứng dụng mới nếu không có lý do tương thích cụ thể.

## 8. LoadBalancer tìm instance từ đâu?

### 8.1. Discovery-backed service instances

Trong cấu hình phổ biến, LoadBalancer dùng `ServiceInstanceListSupplier` để lấy instance. Supplier có thể sử dụng DiscoveryClient provider như Eureka, Consul hoặc Zookeeper.

Luồng khái quát:

1. WebClient gửi request có service ID.
2. LoadBalancer xác định client theo service ID.
3. ServiceInstanceListSupplier lấy danh sách instance.
4. ReactiveLoadBalancer chọn một instance theo chiến lược.
5. Filter thay URI logic bằng URI của instance.
6. WebClient gửi HTTP request.

Spring Cloud cung cấp các chiến lược như round-robin và random. Cấu hình cụ thể phụ thuộc release train và LoadBalancer client của service.

### 8.2. SimpleDiscoveryClient cho local/test

Nếu không muốn chạy registry trong môi trường local, có thể khai báo instance tĩnh:

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

Khi gọi `http://inventory-service/...`, LoadBalancer có thể chọn một trong các URI được cấu hình. Cách này hữu ích cho integration test hoặc môi trường phát triển đơn giản.

Nếu có registry-backed DiscoveryClient trên classpath, provider đó thường được ưu tiên theo auto-configuration. Hãy xác minh nguồn instance thực tế, tránh cho rằng cấu hình SimpleDiscoveryClient luôn thắng registry.

### 8.3. Service ID phải khớp

Nếu request dùng:

~~~text
http://inventory-service/api/items
~~~

thì nguồn instance phải đăng ký service ID tương ứng. Những lỗi thường gặp:
- Service đăng ký tên `inventory` nhưng client gọi `inventory-service`.
- Sai namespace hoặc profile.
- Registry chưa có instance healthy.
- Discovery provider không được auto-configure.
- Supplier cache chưa cập nhật sau khi topology thay đổi.

Service ID phải được thống nhất giữa bên đăng ký và bên gọi.

## 9. Tùy biến LoadBalancer theo service ID

Spring Cloud cho phép khai báo cấu hình LoadBalancer riêng cho một service bằng `@LoadBalancerClient`:

~~~java
@Configuration
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryLoadBalancerConfiguration.class
)
public class InventoryClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

`name` là service ID mà cấu hình riêng sẽ áp dụng. `InventoryLoadBalancerConfiguration` có thể khai báo `ReactorLoadBalancer` hoặc `ServiceInstanceListSupplier` phù hợp với yêu cầu.

Ví dụ cấu hình riêng cần được tổ chức cẩn thận:

~~~java
public class InventoryLoadBalancerConfiguration {

    @Bean
    ReactorLoadBalancer<ServiceInstance> inventoryLoadBalancer(
            Environment environment,
            LoadBalancerClientFactory clientFactory) {

        String serviceId = environment.getProperty(
                LoadBalancerClientFactory.PROPERTY_NAME);

        return new RandomLoadBalancer(
                clientFactory.getLazyProvider(
                        serviceId,
                        ServiceInstanceListSupplier.class),
                serviceId);
    }
}
~~~

Class được truyền vào `@LoadBalancerClient` không nên nằm trong component-scan như một cấu hình toàn cục ngoài ý muốn. Tài liệu Spring Cloud khuyến nghị class cấu hình này không gắn `@Configuration` hoặc đặt ngoài component scan scope để tránh bean bị áp dụng cho toàn bộ context chính.

Chỉ tùy biến thuật toán khi có yêu cầu rõ ràng. Round-robin mặc định thường đủ cho các tình huống cơ bản.

## 10. Xử lý lỗi HTTP và timeout

Load balancing chỉ chọn instance. Nó không thay thế xử lý lỗi của HTTP client.

### 10.1. Xử lý status lỗi

`retrieve()` chuyển HTTP status 4xx/5xx thành lỗi reactive nếu không có handler phù hợp. Có thể ánh xạ lỗi:

~~~java
public Mono<Item> getItem(String itemId) {
    return webClient.get()
            .uri("http://inventory-service/api/items/{id}", itemId)
            .retrieve()
            .onStatus(
                    status -> status.is4xxClientError(),
                    response -> response.createException())
            .onStatus(
                    status -> status.is5xxServerError(),
                    response -> response.createException())
            .bodyToMono(Item.class);
}
~~~

Ứng dụng có thể chuyển các lỗi này thành domain exception, log correlation ID hoặc trả response phù hợp cho caller. Không log toàn bộ body nếu response có thể chứa dữ liệu nhạy cảm.

### 10.2. Timeout

Có thể giới hạn thời gian cho một lời gọi:

~~~java
public Mono<Item> getItem(String itemId) {
    return webClient.get()
            .uri("http://inventory-service/api/items/{id}", itemId)
            .retrieve()
            .bodyToMono(Item.class)
            .timeout(Duration.ofSeconds(2));
}
~~~

Timeout của Reactor pipeline không đồng nghĩa mọi socket-level timeout đã được cấu hình. Với yêu cầu production, hãy cấu hình timeout phù hợp ở HTTP connector và kiểm tra thời gian chờ của LoadBalancer/discovery provider.

### 10.3. Retry cần dựa trên semantics

Spring Cloud LoadBalancer hỗ trợ retry cho WebClient reactive qua cấu hình như:

~~~yaml
spring:
  cloud:
    loadbalancer:
      retry:
        enabled: true
        max-retries-on-same-service-instance: 0
        max-retries-on-next-service-instance: 1
~~~

Retry có thể hữu ích khi một instance tạm thời không phản hồi, nhưng không phải request nào cũng an toàn để gửi lại. Chỉ retry thao tác idempotent hoặc request có idempotency key phù hợp. Cần giới hạn số lần thử, tổng deadline và backoff để tránh khuếch đại tải khi dịch vụ đang lỗi.

Không nhầm retry của Spring Cloud LoadBalancer với Reactor `retryWhen` tự thêm ở tầng business. Nếu bật cả hai, tổng số lần request có thể tăng nhiều hơn dự kiến.

## 11. Bộ lọc WebClient khác và thứ tự áp dụng

Một WebClient có thể có nhiều filter:

- LoadBalancer filter để chuyển service ID thành instance.
- Authentication filter để thêm token.
- Correlation filter để truyền trace/correlation ID.
- Logging/metrics filter để quan sát request.
- Error mapping filter để chuẩn hóa lỗi.

Ví dụ filter thêm correlation ID:

~~~java
ExchangeFilterFunction correlationFilter =
        (request, next) -> {
            ClientRequest updated = ClientRequest.from(request)
                    .header("X-Correlation-Id", UUID.randomUUID().toString())
                    .build();

            return next.exchange(updated);
        };
~~~

Có thể gắn filter vào builder:

~~~java
WebClient client = WebClient.builder()
        .filter(correlationFilter)
        .filter(loadBalancerFilter)
        .build();
~~~

Thứ tự filter ảnh hưởng request/response đi qua chuỗi. Với custom filter, tránh sửa host/service ID theo cách khiến LoadBalancer không nhận diện được request. Không tự resolve service ID thành IP trước khi filter LoadBalancer chạy.

Nếu cần thêm header dựa trên instance đã chọn, Spring Cloud LoadBalancer cung cấp `LoadBalancerClientRequestTransformer` cho WebClient. Transformer nhận request và ServiceInstance được chọn, phù hợp hơn với logic cần biết instance cuối cùng.

## 12. Kiểm thử WebClient.Builder load-balanced

### 12.1. Kiểm tra bean qualifier

Một integration test có thể xác minh builder load-balanced được đăng ký:

~~~java
@Autowired
@LoadBalanced
WebClient.Builder loadBalancedBuilder;

@Test
void loadBalancedBuilderIsAvailable() {
    assertThat(loadBalancedBuilder).isNotNull();
}
~~~

Test này chỉ xác nhận bean được inject. Nó chưa chứng minh filter có thể tìm instance hoặc request đã được chuyển đến đúng host.

### 12.2. Kiểm thử với SimpleDiscoveryClient

Cấu hình test có hai instance:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
~~~

Khởi chạy hai HTTP stub server trên hai port đó. Mỗi server trả một nội dung nhận diện riêng, ví dụ `instance-1` và `instance-2`.

Gọi nhiều lần:

~~~java
Flux<String> responses = Flux.range(0, 10)
        .flatMap(index -> inventoryClient.getInstanceMarker());
~~~

Xác minh:
- Request dùng service ID `inventory-service`.
- Filter đã thay URI thành một trong hai host/port test.
- Response đến từ các instance hợp lệ.
- Không có request nào đi tới hostname logic như thể nó là DNS host thật.
- Khi danh sách instance rỗng, lỗi được truyền về caller theo hành vi mong muốn.

Nếu thuật toán mặc định là round-robin, test có thể quan sát sự phân phối qua nhiều request nhưng không nên khẳng định thứ tự tuyệt đối nếu có cache, concurrency hoặc thay đổi cấu hình.

### 12.3. Kiểm thử builder thường

Tạo thêm một server HTTP test có hostname/URI thông thường. Gọi nó bằng builder không có `@LoadBalanced` và xác minh request đi thẳng tới endpoint đó.

Test này giúp phát hiện việc inject nhầm builder khiến external URL bị đưa vào service discovery.

### 12.4. Kiểm thử lỗi và timeout

Bao gồm các trường hợp:

1. Service ID không tồn tại.
2. Registry trả danh sách rỗng.
3. Một instance không phản hồi.
4. Instance trả HTTP 4xx/5xx.
5. Request vượt quá timeout.
6. Retry được bật và chỉ chạy với thao tác an toàn.
7. Discovery provider tạm thời không truy cập được.

Test nên kiểm tra cả kết quả reactive signal và log/metrics có liên quan, tránh chỉ kiểm tra rằng method trả về một `Mono`.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Không inject được `@LoadBalanced WebClient.Builder` | Thiếu Spring Cloud LoadBalancer starter hoặc WebFlux integration không được auto-configure. | Kiểm tra `spring-cloud-starter-loadbalancer`, `spring-webflux` và dependency tree. |
| Bean builder có nhưng request báo UnknownHost | URI dùng service ID nhưng LoadBalancer filter không được gắn. | Kiểm tra qualifier và bean builder thực tế được inject. |
| Request gọi sai host | Code inject builder thường thay vì builder load-balanced. | Dùng `@LoadBalanced` qualifier tại injection point. |
| Không tìm thấy instance | Service ID không khớp, registry chưa có instance hoặc provider chưa hoạt động. | Kiểm tra service ID, DiscoveryClient và instance list. |
| Request gọi thẳng hostname service ID | Filter không được cài đặt hoặc request không qua builder load-balanced. | Kiểm tra filter chain và cách tạo WebClient. |
| Observability/customizer bị mất | Builder tự tạo không áp dụng `WebClientCustomizer`. | Áp dụng customizer qua `ObjectProvider` theo thứ tự. |
| External API bị xử lý như service discovery | Dùng nhầm builder load-balanced cho hostname bên ngoài. | Tạo builder thường riêng và inject rõ qualifier. |
| Không thấy phân phối đều request | LoadBalancer cache, concurrency, instance list hoặc thuật toán được tùy biến. | Kiểm tra supplier, cache và cấu hình client. |
| Lỗi 503 hoặc không có server instance | Supplier không lấy được instance phù hợp. | Kiểm tra registry, service health và service ID. |
| WebClient vẫn bị block | Một dependency/provider bên dưới thực hiện I/O blocking. | Kiểm tra implementation và tránh blocking trên Reactor event loop. |
| Retry làm tăng tải | Retry chồng với retryWhen hoặc áp dụng cho request không idempotent. | Giới hạn retry, tổng deadline và chọn thao tác an toàn. |
| Cấu hình @LoadBalancerClient không có hiệu lực | Configuration class bị component scan vào context chính hoặc service ID không khớp. | Đặt class ngoài component scan và kiểm tra tên service. |

## 14. Nguyên tắc triển khai

1. **Dùng starter phù hợp.** WebClient cần Spring WebFlux; load balancing cần Spring Cloud LoadBalancer implementation.
2. **Khai báo builder thành bean.** Đánh dấu bean bằng `@LoadBalanced` để Spring Cloud tích hợp filter.
3. **Inject đúng qualifier.** Không dùng builder thường cho request service ID.
4. **Gọi bằng service ID.** URI logic phải khớp ID trong discovery source.
5. **Tách internal và external clients.** Dùng builder riêng khi cần cả hai kiểu HTTP call.
6. **Giữ Boot customizers.** Áp dụng `WebClientCustomizer` theo thứ tự nếu tự tạo builder.
7. **Ưu tiên reactive filter.** Dùng `ReactorLoadBalancerExchangeFilterFunction` cho WebFlux.
8. **Không tự resolve địa chỉ.** Để LoadBalancer xử lý chọn instance và thay URI.
9. **Thiết kế timeout/retry có giới hạn.** Không retry vô điều kiện các thao tác ghi.
10. **Kiểm thử bằng instance giả.** Dùng SimpleDiscoveryClient hoặc test provider để xác minh URI được chuyển đúng.
11. **Quan sát request.** Ghi correlation ID, service ID, kết quả và latency; tránh log token/body nhạy cảm.
12. **Đối chiếu release train.** Kiểm tra Spring Boot, Spring Cloud Commons và LoadBalancer BOM tương thích trước khi nâng cấp.

## 15. Checklist hoàn thành

- [ ] Giải thích được WebClient, WebClient.Builder và ExchangeFilterFunction.
- [ ] Thêm spring-boot-starter-webflux và spring-cloud-starter-loadbalancer.
- [ ] Import Spring Cloud BOM tương thích.
- [ ] Tạo bean WebClient.Builder có @LoadBalanced.
- [ ] Inject builder qua qualifier @LoadBalanced.
- [ ] Dùng URI có service ID thay cho địa chỉ instance.
- [ ] Hiểu filter dùng ReactiveLoadBalancer để chọn ServiceInstance.
- [ ] Áp dụng WebClientCustomizer nếu tự tạo builder.
- [ ] Phân biệt builder load-balanced và builder thường.
- [ ] Biết cách gắn ReactorLoadBalancerExchangeFilterFunction thủ công.
- [ ] Không dùng filter non-reactive deprecated cho ứng dụng mới nếu không có lý do tương thích.
- [ ] Kiểm tra service ID và nguồn instance từ DiscoveryClient/SimpleDiscoveryClient.
- [ ] Biết cách tùy biến LoadBalancer theo service ID.
- [ ] Có timeout, xử lý lỗi và retry có giới hạn.
- [ ] Có test xác minh URI được chuyển tới instance thật và external client không bị load balance.
- [ ] Kiểm tra observability, security và compatibility theo release train.

**Tài liệu chính thức cần đối chiếu theo phiên bản dự án:**

- [Spring Cloud Commons – Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): tích hợp WebClient với qualifier @LoadBalanced và yêu cầu LoadBalancer implementation.
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): ReactiveLoadBalancer, filter WebClient, supplier, cache và cấu hình theo service ID.
- [Spring – Client-Side Load-Balancing with Spring Cloud LoadBalancer](https://spring.io/guides/gs/spring-cloud-loadbalancer/): ví dụ WebClient.Builder, filter và gọi service bằng service ID.
- [Spring Framework – WebClient Filters](https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-filter.html): cách tạo và gắn ExchangeFilterFunction.

Tên class, auto-configuration và behavior có thể thay đổi theo Spring Cloud release train. Hãy kiểm tra dependency BOM, xác minh builder được gắn đúng filter và chạy integration test với ít nhất hai service instance trước khi triển khai.
