# Giữ cấu hình và quan sát của builder do Spring Boot cung cấp

Khi gọi service qua Spring Cloud LoadBalancer, ứng dụng thường tự khai báo một builder có qualifier **@LoadBalanced** để chuyển tên service logic thành địa chỉ instance thực tế. Nếu tạo builder hoàn toàn mới mà không áp dụng cấu hình của Spring Boot, client có thể vẫn gọi được service nhưng mất các cấu hình nền tảng như message converter/codec, HTTP request factory/connector, SSL bundle, timeout, customizer và đặc biệt là quan sát HTTP client.

Spring Boot cung cấp các builder đã được cấu hình sẵn cho **RestTemplate**, **RestClient** và **WebClient**. Spring Cloud cung cấp cơ chế đánh dấu builder load-balanced. Khi hai cơ chế cùng được sử dụng, cần giữ cấu hình của Boot trong lúc tạo builder có LoadBalancer.

Bài học này thuộc chương **Gọi dịch vụ** của module **SPRING_CLOUD_CORE**. Mục tiêu là hiểu vì sao cần giữ các customizer của Boot, cách kết hợp chúng với @LoadBalanced, cách phân biệt builder thường và builder load-balanced, cùng cách xác minh metrics/traces của request đi qua client.

## 1. Hai lớp cấu hình cùng tham gia tạo HTTP client

Một HTTP client trong ứng dụng Spring Cloud thường nhận cấu hình từ hai phía:

- **Spring Boot:** cấu hình HTTP client nền tảng, message conversion, codec, request factory/connector, SSL, ObservationRegistry và các customizer của ứng dụng.
- **Spring Cloud LoadBalancer:** bổ sung cơ chế phân giải service name và chọn ServiceInstance trước khi gửi request.

Hai lớp này giải quyết hai nhiệm vụ khác nhau. Boot chuẩn bị HTTP client có thể vận hành và quan sát được; LoadBalancer thay thế service name logic bằng địa chỉ instance được chọn.

~~~mermaid
flowchart TD
    A["Spring Boot auto-configuration"] --> B["Builder có cấu hình nền"]
    A --> C["Builder customizers"]
    C --> B
    D["@LoadBalanced"] --> E["Spring Cloud LoadBalancer customization"]
    B --> F["Load-balanced builder"]
    E --> F
    F --> G["RestTemplate / RestClient / WebClient"]
    G --> H["HTTP request"]
    H --> I["Discovery + chọn ServiceInstance"]
    I --> J["Địa chỉ instance thực tế"]
    H --> K["Micrometer Observation"]
    K --> L["Metrics / Traces"]
~~~

Nếu chỉ tạo builder bằng API gốc rồi gắn LoadBalancer, request có thể được định tuyến đúng nhưng thiếu các cấu hình mà Boot vốn đã chuẩn bị. Ngược lại, nếu chỉ dùng builder Boot mà không đánh dấu @LoadBalanced, URL chứa service name như http://catalog-service có thể bị xử lý như hostname DNS thông thường.

## 2. Builder do Spring Boot cung cấp có những gì?

Boot auto-configure builder để ứng dụng không phải tự lắp từng thành phần HTTP client. Chi tiết tùy loại client và phiên bản, nhưng thường bao gồm:

| Builder | Cấu hình Boot có thể cung cấp |
| --- | --- |
| RestTemplateBuilder | HttpMessageConverter, ClientHttpRequestFactory, timeout, SSL, RestTemplateCustomizer và request customizer |
| RestClient.Builder | HttpMessageConverter, ClientHttpRequestFactory, timeout, SSL, RestClientCustomizer |
| WebClient.Builder | ClientHttpConnector, codec, HTTP resources, WebClientCustomizer, SSL và cấu hình quan sát |

Những cấu hình này có thể đến từ property, classpath, bean customizer hoặc auto-configuration khác. Ví dụ, việc thêm một HTTP client implementation vào classpath có thể ảnh hưởng request factory/connector được chọn; cấu hình Jackson có thể ảnh hưởng converter/codec; SSL bundle có thể cung cấp trust/key material; Actuator có thể cung cấp observation customizer.

Vì vậy, builder Boot là điểm tích hợp của nhiều phần trong ứng dụng. Tự tạo một builder mới có thể bỏ qua các phần đó.

### 2.1. Builder và client là hai thời điểm khác nhau

Builder là đối tượng cấu hình. Gọi build() tạo HTTP client cụ thể:

~~~java
RestClient client = builder
        .baseUrl("https://catalog.internal")
        .build();
~~~

Các customizer và cấu hình được áp dụng lên builder trước khi build. Sau khi client được tạo, thay đổi builder không nhất thiết thay đổi client đã tạo trước đó.

Đây là lý do cần hoàn tất cấu hình builder trước khi tạo client, và cần quản lý phạm vi builder nếu tạo nhiều client khác nhau.

## 3. Observability phụ thuộc vào cấu hình builder

Spring Framework sử dụng Micrometer Observation để ghi nhận hoạt động của HTTP client. Một observation có thể tạo:
- Metric timer/counter phục vụ thống kê thời gian và tỷ lệ lỗi.
- Span trong distributed trace nếu hệ thống tracing được cấu hình.
- Metadata như HTTP method, URI template, client name, status và exception.

Spring Boot tích hợp observation vào các builder tự cấu hình. Nếu client không có ObservationRegistry hoặc observation customizer tương ứng, observation có thể trở thành no-op và không tạo dữ liệu.

Tên metric mặc định thường dùng cho HTTP client là:

~~~text
http.client.requests
~~~

Các chỉ số có thể giúp trả lời:
- Service nào đang được gọi nhiều?
- Request có thời gian phản hồi tăng không?
- Tỷ lệ lỗi theo status/outcome thay đổi thế nào?
- Request nào nằm trong trace gây chậm?
- Lỗi xuất hiện ở client, network hay dịch vụ đích?

Không nên chỉ dựa vào log thủ công để đo latency hoặc trace xuyên nhiều service nếu Boot/Micrometer đã cung cấp instrumentation.

### 3.1. Metric và trace khác nhau

| Dữ liệu | Mục đích | Ví dụ |
| --- | --- | --- |
| Metric | Tổng hợp theo thời gian, dùng cho dashboard/alert | số request, latency, error rate |
| Trace | Theo dõi một request xuyên qua nhiều thành phần | order-service gọi catalog-service rồi inventory-service |
| Log | Ghi sự kiện chi tiết tại một thời điểm | timeout khi gọi catalog |

Observation là lớp tích hợp giúp tạo metric và/hoặc trace từ cùng một hoạt động. Có metric không đồng nghĩa đã cấu hình trace exporter; trace cũng cần bridge/exporter phù hợp.

### 3.2. Quan sát HTTP client cần builder được instrument

Spring Boot Actuator hỗ trợ instrumentation cho:
- RestTemplate được tạo từ RestTemplateBuilder đã cấu hình.
- RestClient được tạo từ RestClient.Builder đã cấu hình.
- WebClient được tạo từ WebClient.Builder đã cấu hình.

Nếu tự tạo client trực tiếp bằng constructor/API gốc và bỏ qua customizer, ứng dụng có thể mất observation. Có thể tự cấu hình ObservationRegistry thủ công, nhưng phải chịu trách nhiệm tích hợp đúng cho từng loại client.

## 4. Tạo load-balanced RestTemplateBuilder và giữ cấu hình Boot

Spring Cloud Commons hướng dẫn tạo một bean RestTemplateBuilder được đánh dấu @LoadBalanced. Để giữ các cấu hình và customizer mà Boot cung cấp, hãy dùng **RestTemplateBuilderConfigurer**.

Ví dụ cho Spring Boot 3.x:

~~~java
import org.springframework.boot.autoconfigure.web.client.RestTemplateBuilderConfigurer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class LoadBalancedRestTemplateConfiguration {

    @Bean
    @LoadBalanced
    RestTemplateBuilder loadBalancedRestTemplateBuilder(
            RestTemplateBuilderConfigurer configurer) {

        return configurer.configure(new RestTemplateBuilder());
    }
}
~~~

Điểm quan trọng:
1. Tạo builder mới làm nền.
2. Gọi configurer.configure(...) để áp dụng cấu hình Boot.
3. Đánh dấu bean bằng @LoadBalanced để Spring Cloud bổ sung cơ chế load balancing.
4. Inject đúng builder có qualifier khi tạo RestTemplate.

Consumer:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.web.client.RestTemplate;

@Service
public class CatalogGateway {

    private final RestTemplate restTemplate;

    public CatalogGateway(
            @LoadBalanced RestTemplateBuilder builder) {
        this.restTemplate = builder.build();
    }

    public String getCatalog() {
        return restTemplate.getForObject(
                "http://catalog-service/api/catalog",
                String.class
        );
    }
}
~~~

Ví dụ trên dùng service name logic catalog-service. Spring Cloud LoadBalancer chọn một instance phù hợp và chuyển request tới địa chỉ vật lý của instance đó.

### 4.1. RestTemplateBuilderConfigurer giữ lại điều gì?

Configurer giúp builder tùy chỉnh dựa trên cấu hình mà Boot auto-configuration cung cấp. Các cấu hình có thể bao gồm:
- Message converter mặc định.
- Request factory phù hợp với HTTP client có trên classpath.
- Timeout và SSL bundle.
- Các RestTemplateCustomizer.
- Observation customizer của Boot.
- Các request customizer được đăng ký trong context.

Không nên tự tạo RestTemplateBuilder rồi coi nó tương đương builder Boot. Cần configurer để tái sử dụng cấu hình nền tảng.

## 5. Tạo load-balanced RestClient.Builder và giữ cấu hình Boot

RestClient là HTTP client imperative với API fluent. Nó phù hợp khi ứng dụng không cần mô hình reactive của WebClient. Spring Boot cung cấp prototype RestClient.Builder và cấu hình nó với message converter, request factory cùng customizer.

Spring Cloud Commons hướng dẫn dùng **RestClientBuilderConfigurer** khi tự tạo builder có @LoadBalanced.

Ví dụ cho Spring Boot 3.2 trở lên:

~~~java
import org.springframework.boot.autoconfigure.web.client.RestClientBuilderConfigurer;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class LoadBalancedRestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder(
            RestClientBuilderConfigurer configurer) {

        return configurer.configure(RestClient.builder());
    }
}
~~~

Consumer:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class InventoryGateway {

    private final RestClient restClient;

    public InventoryGateway(
            @LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    public String getInventory() {
        return restClient.get()
                .uri("http://inventory-service/api/inventory")
                .retrieve()
                .body(String.class);
    }
}
~~~

Configurer áp dụng các cấu hình Boot lên builder trước khi client được tạo. Sau đó Spring Cloud LoadBalancer customization được áp dụng nhờ qualifier @LoadBalanced.

### 5.1. Vì sao không dùng RestClient.create()?

RestClient.create() là API tạo client trực tiếp. Client được tạo theo cấu hình mặc định của API và không tự nhận toàn bộ auto-configuration/customizer của Boot.

Nếu cần:
- HttpMessageConverters do Boot quản lý.
- ClientHttpRequestFactory do Boot chọn.
- Observation instrumentation.
- SSL bundle.
- Các RestClientCustomizer trong ApplicationContext.

hãy inject builder Boot hoặc dùng RestClientBuilderConfigurer khi tự tạo builder load-balanced.

## 6. Tạo load-balanced WebClient.Builder và áp dụng WebClientCustomizer

WebClient là HTTP client reactive, phù hợp với ứng dụng Spring WebFlux hoặc luồng xử lý cần non-blocking I/O. Spring Boot cung cấp WebClient.Builder được cấu hình với connector, codec và tài nguyên HTTP thích hợp.

Khi tạo builder riêng có @LoadBalanced, Spring Cloud Commons hướng dẫn áp dụng các bean **WebClientCustomizer** mà Boot cung cấp. Dùng ObjectProvider để lấy customizer theo thứ tự:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class LoadBalancedWebClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder(
            ObjectProvider<WebClientCustomizer> customizerProvider) {

        WebClient.Builder builder = WebClient.builder();

        customizerProvider.orderedStream()
                .forEach(customizer -> customizer.customize(builder));

        return builder;
    }
}
~~~

Đoạn code:
- Tạo builder.
- Lấy tất cả WebClientCustomizer.
- Áp dụng theo thứ tự được Spring quản lý.
- Trả builder đã có cấu hình Boot và qualifier LoadBalancer.

Consumer:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class PricingGateway {

    private final WebClient webClient;

    public PricingGateway(
            @LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<String> getPrice() {
        return webClient.get()
                .uri("http://pricing-service/api/price")
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

Nếu dùng Boot 4.x, package của WebClientCustomizer chuyển sang org.springframework.boot.webclient.WebClientCustomizer. Cần dùng import đúng theo Boot version của dự án.

### 6.1. Vì sao dùng orderedStream()?

Các customizer có thể có thứ tự để bảo đảm cấu hình được áp dụng đúng. Dùng orderedStream() giữ thứ tự do Spring quản lý thay vì tự lấy danh sách và áp dụng tùy ý.

Một customizer có thể cấu hình:
- Codec và message reader/writer.
- ObservationRegistry.
- Connector hoặc HTTP resources.
- Các thiết lập chung của WebClient.
- Hành vi do starter hoặc ứng dụng bổ sung.

Không nên bỏ qua danh sách customizer khi tạo builder riêng nếu muốn giữ hành vi Boot.

## 7. Khi ứng dụng có cả builder thường và builder load-balanced

Một ứng dụng thường cần hai kiểu gọi:

- Gọi service nội bộ bằng tên logic, ví dụ http://catalog-service.
- Gọi endpoint cố định bên ngoài, ví dụ https://payment-provider.example.

Không nên dùng một builder load-balanced cho mọi URL. Builder thường và builder load-balanced nên được đăng ký riêng để thể hiện rõ ý định.

### 7.1. Hai RestClient.Builder

Ví dụ:

~~~java
import org.springframework.boot.autoconfigure.web.client.RestClientBuilderConfigurer;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class RestClientBuildersConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder(
            RestClientBuilderConfigurer configurer) {

        return configurer.configure(RestClient.builder());
    }

    @Bean
    @Primary
    RestClient.Builder restClientBuilder(
            RestClientBuilderConfigurer configurer) {

        return configurer.configure(RestClient.builder());
    }
}
~~~

Consumer dùng qualifier:

~~~java
@Service
public class CatalogGateway {

    private final RestClient client;

    public CatalogGateway(
            @LoadBalanced RestClient.Builder builder) {
        this.client = builder.build();
    }
}
~~~

Consumer gọi endpoint ngoài có thể inject builder không qualifier:

~~~java
@Service
public class PaymentProviderGateway {

    private final RestClient client;

    public PaymentProviderGateway(RestClient.Builder builder) {
        this.client = builder
                .baseUrl("https://payment-provider.example")
                .build();
    }
}
~~~

@Primary đặt trên builder thường giúp Spring chọn bean đó khi injection không có qualifier. @LoadBalanced giúp chọn builder dành cho service discovery.

### 7.2. Hai WebClient.Builder

Nếu khai báo nhiều WebClient.Builder bean, cấu hình của Boot cần được áp dụng cho từng builder. Ví dụ:

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.web.reactive.function.client.WebClientCustomizer;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class WebClientBuildersConfiguration {

    private WebClient.Builder createConfiguredBuilder(
            ObjectProvider<WebClientCustomizer> customizerProvider) {

        WebClient.Builder builder = WebClient.builder();

        customizerProvider.orderedStream()
                .forEach(customizer -> customizer.customize(builder));

        return builder;
    }

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder(
            ObjectProvider<WebClientCustomizer> customizerProvider) {

        return createConfiguredBuilder(customizerProvider);
    }

    @Bean
    @Primary
    WebClient.Builder webClientBuilder(
            ObjectProvider<WebClientCustomizer> customizerProvider) {

        return createConfiguredBuilder(customizerProvider);
    }
}
~~~

Cả hai builder đều nhận customizer Boot; chỉ builder có @LoadBalanced nhận thêm hành vi chọn service instance.

### 7.3. Hai RestTemplateBuilder

Cách tổ chức tương tự:

~~~java
import org.springframework.boot.autoconfigure.web.client.RestTemplateBuilderConfigurer;
import org.springframework.boot.web.client.RestTemplateBuilder;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration(proxyBeanMethods = false)
public class RestTemplateBuildersConfiguration {

    @Bean
    @LoadBalanced
    RestTemplateBuilder loadBalancedRestTemplateBuilder(
            RestTemplateBuilderConfigurer configurer) {

        return configurer.configure(new RestTemplateBuilder());
    }

    @Bean
    @Primary
    RestTemplateBuilder restTemplateBuilder(
            RestTemplateBuilderConfigurer configurer) {

        return configurer.configure(new RestTemplateBuilder());
    }
}
~~~

Nếu không có nhu cầu hai loại client, không cần tạo thêm bean builder. Hãy giữ cấu hình đơn giản và chỉ tạo builder thứ hai khi ứng dụng thực sự cần phân biệt đường gọi.

## 8. Ý nghĩa của @LoadBalanced và service name URI

@LoadBalanced là qualifier để Spring Cloud nhận diện bean builder/client cần tích hợp với LoadBalancer. Nó không tự tìm service registry nếu dependency discovery/load balancer chưa có.

Để sử dụng, ứng dụng cần Spring Cloud LoadBalancer implementation, thường được thêm qua starter:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
~~~

Khi gọi qua builder load-balanced, URI dùng service name logic:

~~~text
http://catalog-service/api/catalog
~~~

LoadBalancer lấy danh sách ServiceInstance của catalog-service, chọn một instance và thay host/port logic bằng endpoint thực tế.

Nếu dùng URI cố định:

~~~text
https://catalog.internal/api/catalog
~~~

thì không cần service name resolution của Spring Cloud LoadBalancer. Có thể dùng builder thường để gọi endpoint cố định.

Không nên gắn @LoadBalanced cho builder chỉ để có metrics. Observability đến từ cấu hình Boot; LoadBalancer là một cơ chế định tuyến riêng.

## 9. Giữ customizer của Boot khi thêm cấu hình riêng

Ứng dụng thường cần thêm header, timeout, base URL hoặc filter. Hãy bổ sung cấu hình trên builder đã được configure thay vì thay toàn bộ cấu hình nền.

Ví dụ RestClient:

~~~java
@Bean
@LoadBalanced
RestClient.Builder catalogRestClientBuilder(
        RestClientBuilderConfigurer configurer) {

    return configurer.configure(RestClient.builder())
            .defaultHeader("X-Client-Application", "order-service");
}
~~~

Ví dụ RestTemplate:

~~~java
@Bean
@LoadBalanced
RestTemplateBuilder catalogRestTemplateBuilder(
        RestTemplateBuilderConfigurer configurer) {

    return configurer.configure(new RestTemplateBuilder())
            .connectTimeout(java.time.Duration.ofSeconds(2))
            .readTimeout(java.time.Duration.ofSeconds(5));
}
~~~

Các phương thức connectTimeout và readTimeout trong ví dụ có từ Spring Boot 3.4. Với Boot 3.2 hoặc 3.3, dùng setConnectTimeout và setReadTimeout theo API của phiên bản đó; khi nâng Boot, kiểm tra các phương thức đã deprecated và chuyển sang API mới.

Ví dụ WebClient:

~~~java
@Bean
@LoadBalanced
WebClient.Builder catalogWebClientBuilder(
        ObjectProvider<WebClientCustomizer> customizerProvider) {

    WebClient.Builder builder = WebClient.builder();

    customizerProvider.orderedStream()
            .forEach(customizer -> customizer.customize(builder));

    return builder.defaultHeader(
            "X-Client-Application",
            "order-service"
    );
}
~~~

Đặt cấu hình riêng sau khi customizer Boot đã được áp dụng để thể hiện rõ phần nào là default, phần nào là override của ứng dụng.

### 9.1. Tránh thao tác thay thế toàn bộ cấu hình

Một số API có semantics thay thế thay vì bổ sung:
- RestTemplateBuilder.interceptors(...) thay thế danh sách interceptor đã có; additionalInterceptors(...) bổ sung interceptor.
- WebClient.Builder.filters(...) cho phép thao tác trực tiếp danh sách filter; thao tác clear() có thể xóa filter đã được customizer đăng ký.
- RestClient.Builder có các API để thêm hoặc thay interceptor/request initializer tùy phiên bản.

Nếu muốn giữ instrumentation, không xóa observation interceptor/filter do Boot cung cấp. Khi cần thêm xử lý, ưu tiên API additive và kiểm tra danh sách customizer trước/sau.

## 10. Builder có trạng thái và cách tránh cấu hình chéo

Không phải builder nào cũng có cùng semantics:

| Builder | Tính chất | Cách dùng an toàn |
| --- | --- | --- |
| RestTemplateBuilder | Immutable; phương thức cấu hình trả builder mới | Lưu builder kết quả từ mỗi lời gọi |
| RestClient.Builder | Stateful; thay đổi builder ảnh hưởng client tạo sau đó | Clone khi cần nhánh cấu hình độc lập |
| WebClient.Builder | Stateful; thay đổi builder ảnh hưởng client tạo sau đó | Clone khi cần nhánh cấu hình độc lập |

Ví dụ với WebClient:

~~~java
WebClient.Builder base = configuredBuilder.clone();

WebClient catalogClient = base.clone()
        .baseUrl("http://catalog-service")
        .build();

WebClient inventoryClient = base.clone()
        .baseUrl("http://inventory-service")
        .build();
~~~

Ví dụ với RestClient:

~~~java
RestClient catalogClient = configuredBuilder.clone()
        .baseUrl("http://catalog-service")
        .build();

RestClient inventoryClient = configuredBuilder.clone()
        .baseUrl("http://inventory-service")
        .build();
~~~

Việc clone giúp hai client không vô tình dùng chung base URL, default header, filter hoặc interceptor được thêm ở bước sau.

Với RestTemplateBuilder, các phương thức thường trả về instance builder mới nên có thể giữ mỗi nhánh riêng:

~~~java
RestTemplateBuilder base = configuredBuilder;

RestTemplate catalogClient = base
        .rootUri("http://catalog-service")
        .build();

RestTemplate inventoryClient = base
        .rootUri("http://inventory-service")
        .build();
~~~

Không dùng một mutable WebClient.Builder hoặc RestClient.Builder như một đối tượng toàn cục rồi thay baseUrl liên tục giữa các service.

## 11. Cấu hình observability và nơi xem kết quả

Để xem metrics HTTP client, ứng dụng thường cần Spring Boot Actuator và registry/exporter phù hợp. Ví dụ:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>

<dependency>
    <groupId>io.micrometer</groupId>
    <artifactId>micrometer-registry-prometheus</artifactId>
    <scope>runtime</scope>
</dependency>
~~~

Cấu hình expose các endpoint cần thiết:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - metrics
          - prometheus
  observations:
    http:
      client:
        requests:
          name: http.client.requests
~~~

Tên metric mặc định là http.client.requests. Có thể truy vấn qua:

~~~text
GET /actuator/metrics/http.client.requests
~~~

Nếu Prometheus registry được cấu hình, endpoint scrape thường là:

~~~text
GET /actuator/prometheus
~~~

Endpoint thực tế phụ thuộc management base path, port và exposure configuration. Không expose management endpoint ra public network nếu không có chính sách bảo vệ phù hợp.

### 11.1. Metric có thể cho biết điều gì?

HTTP client observation thường ghi nhận các thuộc tính như:
- HTTP method.
- URI template.
- Tên client/host theo cách instrumentation xác định.
- Status code.
- Outcome.
- Exception/error.
- Thời gian trao đổi request/response.

Low-cardinality key values phù hợp cho metric vì số giá trị hữu hạn. URI đầy đủ hoặc dữ liệu có cardinality cao thường phù hợp với trace hơn. Tránh đưa user ID, order ID, token hoặc query string có dữ liệu nhạy cảm vào metric tag.

### 11.2. Trace xuyên service

Nếu hệ thống đã cấu hình Micrometer Tracing và exporter, Observation có thể tạo span cho HTTP client exchange. Khi trace propagation hoạt động, trace ID và span context được truyền tới service đích theo instrumentation/protocol tương ứng.

Khi builder mất ObservationRegistry hoặc customizer, có thể xuất hiện khoảng trống:
- Server span vẫn tồn tại.
- Client request không tạo span.
- Trace bị đứt tại ranh giới gọi service.
- Metric client request không xuất hiện.

Do đó, khi kiểm tra trace bị đứt, hãy kiểm tra builder đã dùng để tạo client trước khi điều tra collector hoặc backend tracing.

## 12. SSL bundle và cấu hình HTTP nền tảng

Boot có thể cung cấp SSL bundle và cấu hình request factory/connector cho builder. Khi tự tạo builder, nếu không áp dụng configurer/customizer, client có thể không dùng truststore, keystore hoặc TLS setting mà ứng dụng đã cấu hình.

Với RestClient trong Spring Boot 3.x, có thể dùng RestClientSsl và apply bundle:

~~~java
RestClient client = builder
        .baseUrl("https://catalog.internal")
        .apply(ssl.fromBundle("internal-services"))
        .build();
~~~

Với WebClient, sử dụng WebClientSsl tương ứng với Boot version và connector:

~~~java
WebClient client = builder
        .baseUrl("https://catalog.internal")
        .apply(ssl.fromBundle("internal-services"))
        .build();
~~~

Nếu builder đã được customizer cấu hình SSL toàn cục, không cần tạo một connector/request factory mới một cách tùy tiện. Khi override connector, cần hiểu rằng có thể đang thay thế HTTP resource hoặc TLS configuration mà Boot đã chọn.

## 13. Phân biệt observability với LoadBalancer instrumentation

Hai cơ chế thường cùng xuất hiện trong một request nhưng có mục tiêu khác nhau:

| Cơ chế | Trách nhiệm |
| --- | --- |
| Boot HTTP client observation | Đo thời gian, status, exception và tạo span cho HTTP exchange |
| Spring Cloud LoadBalancer | Chọn ServiceInstance và phân giải service name |
| DiscoveryClient | Lấy danh sách instance từ registry hoặc discovery implementation |
| HTTP connector/request factory | Mở kết nối, xử lý TLS, timeout và I/O |
| Micrometer registry/exporter | Lưu và xuất metric/trace tới backend quan sát |

LoadBalancer có thể chọn instance đúng nhưng không có nghĩa request đã được instrument. Ngược lại, metric có thể ghi nhận request nhưng request không nhất thiết dùng discovery nếu builder không có @LoadBalanced.

Một request hoàn chỉnh thường đi qua:

~~~mermaid
sequenceDiagram
    participant App as Service gọi
    participant Builder as Load-balanced builder
    participant LB as Spring Cloud LoadBalancer
    participant Discovery as DiscoveryClient
    participant HTTP as HTTP client
    participant Target as Service đích
    participant Obs as ObservationRegistry

    App->>Builder: Tạo client và gửi request
    Builder->>LB: Resolve service name
    LB->>Discovery: Lấy ServiceInstance
    Discovery-->>LB: Danh sách instance
    LB-->>HTTP: Địa chỉ instance được chọn
    HTTP->>Obs: Bắt đầu/ghi nhận observation
    HTTP->>Target: HTTP request
    Target-->>HTTP: HTTP response
    HTTP->>Obs: Kết thúc observation
    HTTP-->>App: Kết quả
~~~

Sơ đồ diễn tả trách nhiệm khái quát; thứ tự nội bộ của interceptor/filter và observation phụ thuộc loại client cùng phiên bản integration.

## 14. Package và API thay đổi giữa Spring Boot 3.x và 4.x

Khi nâng Boot, một số package builder/configurer đã được tổ chức lại. Không copy import từ ví dụ Boot 3 sang Boot 4 mà không kiểm tra compile.

| Thành phần | Spring Boot 3.x | Spring Boot 4.x |
| --- | --- | --- |
| RestTemplateBuilder | org.springframework.boot.web.client.RestTemplateBuilder | org.springframework.boot.restclient.RestTemplateBuilder |
| RestTemplateBuilderConfigurer | org.springframework.boot.autoconfigure.web.client.RestTemplateBuilderConfigurer | org.springframework.boot.restclient.autoconfigure.RestTemplateBuilderConfigurer |
| RestClientBuilderConfigurer | org.springframework.boot.autoconfigure.web.client.RestClientBuilderConfigurer | org.springframework.boot.restclient.autoconfigure.RestClientBuilderConfigurer |
| WebClientCustomizer | org.springframework.boot.web.reactive.function.client.WebClientCustomizer | org.springframework.boot.webclient.WebClientCustomizer |

Một số điểm version cần nhớ:
- RestClient có từ Spring Boot 3.2.
- Spring Boot 3.2/3.3/3.4/3.5 dùng package của thế hệ Boot 3.
- Spring Boot 4.0 chuyển một số client API và customizer sang package mới.
- Spring Framework 7 đánh dấu RestTemplate deprecated để hướng tới RestClient; ứng dụng cũ vẫn cần migration theo lộ trình phù hợp.
- Spring Cloud release train phải tương thích với Spring Boot generation. Dùng Spring Cloud BOM để quản lý version, không pin riêng từng module tùy tiện.

Nếu dự án dùng Boot 3.1 hoặc cũ hơn, không có RestClient; chọn RestTemplateBuilder hoặc WebClient.Builder. Luôn kiểm tra API thực tế của Spring Boot/Spring Cloud BOM đang dùng.

## 15. Những cách làm dễ làm mất cấu hình Boot

| Cách làm | Rủi ro | Cách xử lý |
| --- | --- | --- |
| Tạo RestTemplate trực tiếp bằng new RestTemplate() | Không đi qua RestTemplateBuilder/customizer của Boot | Inject RestTemplateBuilder và build |
| Dùng RestClient.create() | Không nhận RestClientBuilderConfigurer/customizer | Inject RestClient.Builder hoặc configure builder |
| Dùng WebClient.create() | Bỏ qua WebClientCustomizer và Boot codec/observation config | Inject WebClient.Builder |
| Tạo RestClient.Builder mới nhưng không configurer | Mất cấu hình builder Boot như converter, request factory, observation | Dùng RestClientBuilderConfigurer |
| Tạo RestTemplateBuilder mới nhưng không configurer | Mất customizer/settings Boot | Dùng RestTemplateBuilderConfigurer |
| Tạo WebClient.Builder mới nhưng không áp dụng customizer | Có thể mất codec, observation, connector customization | Áp dụng ordered WebClientCustomizer |
| Xóa toàn bộ interceptor/filter | Có thể xóa instrumentation hoặc LoadBalancer integration | Dùng API bổ sung và kiểm tra thứ tự |
| Dùng builder load-balanced cho endpoint cố định | Thêm xử lý discovery không cần thiết | Dùng builder thường |
| Inject nhiều builder mà không qualifier | Có thể lấy nhầm builder hoặc gặp lỗi ambiguous | Dùng @LoadBalanced và @Primary |
| Dùng một mutable builder cho nhiều client | Cấu hình client sau có thể ảnh hưởng client tạo tiếp theo | Clone builder hoặc tạo builder riêng |

## 16. Kiểm thử để chứng minh cấu hình và observability vẫn hoạt động

Một test chỉ xác nhận request trả HTTP 200 chưa chứng minh builder giữ đủ cấu hình. Nên kiểm tra riêng:
1. Bean builder được tạo đúng qualifier.
2. Request đi qua LoadBalancer khi URI dùng service name.
3. Converter/codec vẫn serialize và deserialize đúng.
4. Timeout/SSL/header customizer vẫn được áp dụng.
5. Observation được ghi nhận.
6. Client thường không đi qua LoadBalancer ngoài ý muốn.

### 16.1. Kiểm tra metrics

Trong integration test, có thể dùng SimpleMeterRegistry hoặc MeterRegistry test để kiểm tra sau một request:
- Có meter http.client.requests.
- Count tăng sau request.
- Tags cơ bản phản ánh method/status/outcome phù hợp.
- Exception request cũng được ghi nhận theo instrumentation.

Nếu test chỉ dùng mock builder tự tạo, test có thể không chứa Boot observation customizer. Hãy chạy ít nhất một test với ApplicationContext/auto-configuration thật.

### 16.2. Kiểm tra trace

Nếu tracing được bật:
- Gửi một request từ service gọi tới service đích.
- Kiểm tra client span được tạo.
- Kiểm tra trace ID được propagate tới service đích.
- Kiểm tra span có kết thúc cả khi response 4xx/5xx hoặc lỗi kết nối.
- Xác nhận không có khoảng trống do client được tạo từ builder bỏ qua ObservationRegistry.

### 16.3. Kiểm tra load balancing

Có thể dùng hai instance test cùng service ID và ghi lại instance nhận request. Kiểm tra:
- URI logic dùng service name.
- LoadBalancer chọn instance theo policy đã cấu hình.
- Request không gọi thẳng hostname logic qua DNS.
- Builder thường gọi endpoint cố định không bị thay đổi sang service instance.

Test cần dùng Spring Cloud LoadBalancer integration thật nếu mục tiêu là xác minh @LoadBalanced customization.

## 17. Checklist khi tạo builder load-balanced

Trước khi đưa builder vào production, xác nhận:

- [ ] Đã thêm Spring Cloud LoadBalancer starter phù hợp.
- [ ] Builder được đánh dấu @LoadBalanced.
- [ ] Builder được tạo từ cấu hình Boot hoặc đã chạy configurer/customizer.
- [ ] RestTemplateBuilder dùng RestTemplateBuilderConfigurer.
- [ ] RestClient.Builder dùng RestClientBuilderConfigurer.
- [ ] WebClient.Builder áp dụng WebClientCustomizer theo thứ tự.
- [ ] Có @Primary cho builder thường nếu cùng tồn tại hai loại.
- [ ] Consumer inject đúng builder bằng @LoadBalanced.
- [ ] URI dùng service name khi cần discovery/load balancing.
- [ ] Không xóa interceptor/filter quan sát của Boot.
- [ ] ObservationRegistry và exporter đã được cấu hình.
- [ ] Metrics http.client.requests xuất hiện sau request.
- [ ] Trace có client span và context propagation nếu tracing được bật.
- [ ] SSL, timeout và codec/converter đã được kiểm thử.
- [ ] Import phù hợp với Spring Boot version và release train.

## Ghi nhớ

Spring Boot builder chứa nhiều cấu hình nền tảng của HTTP client, trong đó có message converter/codec, request factory/connector, SSL và observability. Khi cần builder load-balanced, hãy kết hợp @LoadBalanced với cấu hình Boot: RestTemplateBuilderConfigurer cho RestTemplateBuilder, RestClientBuilderConfigurer cho RestClient.Builder, và ordered WebClientCustomizer cho WebClient.Builder. Khi có cả builder thường và builder load-balanced, dùng qualifier rõ ràng và @Primary cho builder thường. Sau cùng, xác minh request qua LoadBalancer, metric http.client.requests và trace thực tế; đừng kết luận chỉ từ việc request trả về thành công.

## Tài liệu tham khảo

- Spring Cloud Commons – Common Abstractions: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html
- Spring Cloud LoadBalancer: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html
- Spring Boot 3.4 – Calling REST Services: https://docs.spring.io/spring-boot/3.4/reference/io/rest-client.html
- Spring Boot – Calling REST Services: https://docs.spring.io/spring-boot/reference/io/rest-client.html
- Spring Boot – Metrics and HTTP Client Metrics: https://docs.spring.io/spring-boot/reference/actuator/metrics.html
- Spring Framework – Observability Support: https://docs.spring.io/spring-framework/reference/integration/observability.html

