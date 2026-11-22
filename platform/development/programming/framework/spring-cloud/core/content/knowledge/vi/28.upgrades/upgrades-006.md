# Loại bỏ giả định cũ về annotation bắt buộc và client tự tạo

## 1. Vì sao cần xem lại cách bật discovery và tạo client?

Trong các ứng dụng Spring Cloud đời cũ, nhiều dự án đặt `@EnableDiscoveryClient` trên lớp cấu hình chính rồi tự tạo HTTP client trong từng service. Cách làm đó dễ khiến code phụ thuộc vào annotation, implementation cụ thể hoặc cách khởi tạo thủ công.

Spring Cloud Commons hiện đại dựa nhiều hơn vào auto-configuration và dependency injection:

- Đưa discovery implementation phù hợp vào classpath thường đã đủ để Spring Boot cấu hình `DiscoveryClient`; `@EnableDiscoveryClient` không còn là điều kiện bắt buộc.
- Ứng dụng vẫn phải khai báo HTTP client dưới dạng Spring bean khi cần dùng client đó. `RestTemplate` không tự xuất hiện thành bean chỉ vì thêm Spring Web.
- Khi gọi bằng service ID, client phải được cấu hình với Spring Cloud LoadBalancer, thường thông qua bean có `@LoadBalanced`.
- Service nên nhận các abstraction hoặc client bean qua constructor injection thay vì tự `new` implementation ở từng nơi.

Mục tiêu của bài học là giúp người nâng cấp bỏ các bước bật tính năng đã trở nên dư thừa, đồng thời giữ lại những khai báo bean thực sự cần thiết. Không phải mọi annotation `@Enable...` đều đã lỗi thời, và không phải mọi HTTP client đều tự động được load balance.

Sau bài học, người đọc có thể:

- Giải thích vì sao `@EnableDiscoveryClient` không còn bắt buộc trong trường hợp thông thường.
- Xác định dependency nào cung cấp discovery implementation và dependency nào cung cấp LoadBalancer.
- Inject `DiscoveryClient`, `ServiceRegistry` và HTTP client qua Spring container.
- Phân biệt HTTP client thông thường với client có khả năng phân giải service ID.
- Chọn `RestClient`, `RestTemplate` hoặc `WebClient` phù hợp với stack đồng bộ/Reactive.
- Nâng cấp code cũ mà vẫn giữ được các thiết lập auto-registration và security cần thiết.

## 2. Discovery được tự cấu hình từ dependency

Spring Cloud Commons cung cấp abstraction `DiscoveryClient` và `ReactiveDiscoveryClient`. Các integration như Eureka, Consul hoặc Zookeeper cung cấp implementation tương ứng. Khi dependency implementation nằm trên classpath, Spring Boot có thể tự cấu hình discovery client.

Ví dụ dependency Maven cho một ứng dụng dùng Eureka:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
</dependency>
```

Hoặc nếu dùng Consul:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
```

Chọn integration tương ứng với service registry mà hệ thống sử dụng. Thông thường không thêm đồng thời nhiều registry client chỉ để “bật discovery”; nếu có nhiều implementation, cần hiểu thứ tự và vai trò của từng client.

### 2.1. @EnableDiscoveryClient không còn bắt buộc

Code cũ thường có:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

@SpringBootApplication
@EnableDiscoveryClient
public class InventoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
```

Với Spring Cloud Commons hiện đại, có thể bỏ `@EnableDiscoveryClient`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class InventoryApplication {

    public static void main(String[] args) {
        SpringApplication.run(InventoryApplication.class, args);
    }
}
```

Nếu dependency Eureka hoặc Consul Discovery đã có trên classpath và không bị tắt bằng property, auto-configuration sẽ cung cấp các bean discovery tương ứng.

`@EnableDiscoveryClient` vẫn tồn tại trong Spring Cloud Commons. Điểm thay đổi là ứng dụng không cần annotation này chỉ để yêu cầu Spring tìm implementation. Không nên gọi đây là annotation đã bị xóa hoặc đã khiến mọi ứng dụng cũ phải thay đổi.

### 2.2. Dependency và property mới là các điều kiện cần kiểm tra

Nếu discovery không xuất hiện, hãy kiểm tra:

1. Starter của registry implementation có trong runtime classpath không?
2. Có property nào đặt `spring.cloud.discovery.enabled=false` không?
3. Có tắt riêng blocking hoặc reactive discovery không?
4. Auto-configuration có bị exclude hoặc điều kiện bean có bị vô hiệu hóa không?
5. Registry endpoint, credential và network có sẵn sàng không?

Các property điều khiển phổ biến:

```yaml
spring:
  cloud:
    discovery:
      enabled: true
      blocking:
        enabled: true
      reactive:
        enabled: true
```

`spring.cloud.discovery.enabled=false` tắt service discovery nói chung. Hai property `blocking.enabled` và `reactive.enabled` cho phép tắt riêng từng kiểu client. Không dùng `@EnableDiscoveryClient` để cố ghi đè một cấu hình đã chủ động tắt discovery.

Tên đầy đủ của hai property riêng là `spring.cloud.discovery.blocking.enabled` và `spring.cloud.discovery.reactive.enabled`.

### 2.3. SimpleDiscoveryClient khi không có registry implementation

Nếu không có discovery client dựa trên service registry trong classpath, Spring Cloud Commons có thể dùng `SimpleDiscoveryClient`. Nó lấy danh sách instance từ cấu hình thay vì truy vấn Eureka, Consul hoặc Zookeeper.

Prefix cấu hình của nó là `spring.cloud.discovery.client.simple.instances`; phần tử tiếp theo là service ID và chỉ số instance.

Ví dụ:

```yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
            pricing-service:
              - uri: http://localhost:8082
```

Cách này hữu ích cho môi trường local, test hoặc một hệ thống có danh sách endpoint tĩnh. Nó không tự đăng ký instance lên registry bên ngoài.

## 3. Annotation còn lại dùng cho mục đích riêng

Không nên xóa hàng loạt annotation có tiền tố `@Enable` chỉ vì `@EnableDiscoveryClient` không còn bắt buộc.

| Annotation | Vai trò | Có thể bỏ chỉ vì discovery auto-config không? |
| --- | --- | --- |
| `@EnableDiscoveryClient` | Cơ chế enable discovery kiểu cũ; không còn bắt buộc khi implementation có trên classpath | Có thể bỏ nếu chỉ dùng để bật discovery |
| `@EnableFeignClients` | Quét và đăng ký interface `@FeignClient` | Không |
| `@EnableScheduling` | Bật scheduled task | Không |
| `@EnableAsync` | Bật xử lý bất đồng bộ qua Spring | Không |
| `@EnableMethodSecurity` | Bật method-level authorization | Không |
| `@EnableConfigurationProperties` | Đăng ký các class cấu hình được chỉ định | Không, trừ khi cách đăng ký khác đã thay thế |

Mỗi annotation có điều kiện và mục đích riêng. Khi nâng cấp, hãy xóa `@EnableDiscoveryClient` nếu nó chỉ được dùng để bật discovery; giữ các annotation đang bật một năng lực độc lập.

## 4. Điều khiển auto-registration mà không cần annotation

Discovery và auto-registration là hai việc liên quan nhưng khác nhau:

- Discovery cho phép ứng dụng tìm các service instance.
- Auto-registration đăng ký instance hiện tại của ứng dụng vào service registry.

Mặc định, nhiều discovery implementation tự đăng ký local service. Nếu muốn tắt hành vi đó, cấu hình bằng property:

```yaml
spring:
  cloud:
    service-registry:
      auto-registration:
        enabled: false
```

Code cũ đôi khi dùng:

```java
@EnableDiscoveryClient(autoRegister = false)
```

Khi bỏ annotation, không được vô tình bỏ luôn chủ đích tắt auto-registration. Hãy chuyển ý định đó sang `spring.cloud.service-registry.auto-registration.enabled=false`.

Nếu cần thao tác registration có kiểm soát, inject abstraction `ServiceRegistry` và `Registration` phù hợp với implementation. `ServiceRegistry` là generic theo kiểu registration cụ thể; ví dụ Eureka và Consul có các kiểu registration riêng. Vì vậy, khai báo field/constructor bằng đúng kiểu mà integration đang cung cấp, rồi để Spring inject bean đó. Không tự dựng implementation registry bằng `new`.

Nếu chỉ muốn tắt auto-registration, property là đủ; không cần inject `ServiceRegistry` rồi tự thay thế toàn bộ lifecycle của registry.

## 5. Inject DiscoveryClient thay vì tự tạo implementation

`DiscoveryClient` là abstraction để truy vấn các service instance. Ứng dụng nên inject interface này:

```java
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

import java.util.List;

@Service
public class ServiceCatalog {

    private final DiscoveryClient discoveryClient;

    public ServiceCatalog(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances(String serviceId) {
        return discoveryClient.getInstances(serviceId);
    }

    public List<String> listServices() {
        return discoveryClient.getServices();
    }
}
```

Lợi ích của constructor injection:

- Spring cung cấp implementation đúng theo dependency và cấu hình hiện tại.
- Code nghiệp vụ không phụ thuộc trực tiếp vào Eureka, Consul hoặc Zookeeper.
- Test có thể thay bean `DiscoveryClient` bằng mock hoặc fake.
- Dependency bắt buộc được thể hiện rõ ở constructor.

Không nên viết:

```java
// Không tạo implementation cụ thể trong code nghiệp vụ.
DiscoveryClient client = new EurekaDiscoveryClient(...);
```

Implementation cụ thể có thể cần nhiều dependency, lifecycle và cấu hình nội bộ. Việc tự tạo object bỏ qua các bước auto-configuration và có thể tạo một client không dùng chung state với ApplicationContext.

### 5.1. Khi cần chọn instance cho một request

`DiscoveryClient.getInstances(serviceId)` trả danh sách instance. Nếu chỉ cần hiển thị hoặc kiểm tra metadata, cách này phù hợp. Nhưng nếu mục tiêu là gửi HTTP request tới một instance, không nên tự chọn phần tử đầu tiên rồi tự ghép URL.

Hãy dùng Spring Cloud LoadBalancer để chọn instance và xử lý URI service ID. Việc này giúp áp dụng chính sách chọn instance, supplier, cache và các customization của LoadBalancer.

## 6. Không tạo HTTP client mới trong từng service

Một lỗi thường gặp là tạo client trực tiếp ở nơi gọi:

```java
public class InventoryGateway {

    public Inventory get(String id) {
        RestTemplate restTemplate = new RestTemplate();
        return restTemplate.getForObject(
                "http://inventory-service/api/items/" + id,
                Inventory.class
        );
    }
}
```

Client này không phải bean của Spring. Nó không nhận các interceptor, customizer, observability configuration hoặc LoadBalancer integration mà ứng dụng đã cấu hình cho bean client. Nếu URI dùng service ID như `inventory-service`, một `RestTemplate` thông thường cũng không tự biết cách phân giải tên đó qua discovery.

Thay vào đó, hãy tạo client bean một lần và inject vào service cần dùng. Khi cần gọi service ID, đánh dấu client bằng `@LoadBalanced`.

## 7. RestTemplate: ứng dụng phải khai báo bean

Spring Cloud Commons ghi rõ `RestTemplate` bean không được tạo qua auto-configuration. Ứng dụng cần tự khai báo bean nếu muốn inject `RestTemplate`.

Ví dụ load-balanced:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestTemplate;

@Configuration(proxyBeanMethods = false)
public class HttpClientConfiguration {

    @Bean
    @LoadBalanced
    RestTemplate loadBalancedRestTemplate() {
        return new RestTemplate();
    }
}
```

Sau đó inject qua constructor:

```java
@Service
public class InventoryGateway {

    private final RestTemplate restTemplate;

    public InventoryGateway(@LoadBalanced RestTemplate restTemplate) {
        this.restTemplate = restTemplate;
    }

    public Inventory get(String id) {
        return restTemplate.getForObject(
                "http://inventory-service/api/items/{id}",
                Inventory.class,
                id
        );
    }
}
```

`@LoadBalanced` là qualifier đánh dấu bean cần được tích hợp với LoadBalancer. Nó không thay thế discovery implementation và không tự thêm một service registry vào classpath.

Để dùng `@LoadBalanced RestTemplate`, cần có Spring Cloud LoadBalancer implementation trên classpath, thường qua starter:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-loadbalancer</artifactId>
</dependency>
```

URI phải dùng service ID làm host, ví dụ `http://inventory-service/...`. LoadBalancer sẽ lấy instance vật lý từ discovery và tạo địa chỉ đích.

## 8. RestClient: lựa chọn đồng bộ cho code mới

Với Spring Framework có `RestClient`, Spring Cloud LoadBalancer hỗ trợ `RestClient.Builder` được đánh dấu `@LoadBalanced`.

Khai báo builder bean:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class RestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
```

Inject builder vào client wrapper:

```java
@Component
public class PricingClient {

    private final RestClient restClient;

    public PricingClient(@LoadBalanced RestClient.Builder builder) {
        this.restClient = builder.build();
    }

    public Price getPrice(String sku) {
        return restClient.get()
                .uri("http://pricing-service/api/prices/{sku}", sku)
                .retrieve()
                .body(Price.class);
    }
}
```

Nếu muốn giữ các customization mà Spring Boot áp dụng cho `RestClient.Builder` như observability, hãy cấu hình builder bằng `RestClientBuilderConfigurer` theo phiên bản Boot đang dùng. Đừng thay builder Boot-managed bằng một instance tự tạo nếu ứng dụng phụ thuộc vào các customizer đó.

`RestClient` cần phiên bản Spring Framework hỗ trợ API này. Với baseline cũ hơn, tiếp tục dùng `RestTemplate` hoặc `WebClient` theo stack hiện có.

## 9. WebClient: client Reactive có LoadBalancer

Ứng dụng Reactive có thể dùng `WebClient.Builder` với `@LoadBalanced`:

```java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class ReactiveClientConfiguration {

    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
```

Inject builder và tạo client:

```java
@Component
public class ReactiveInventoryClient {

    private final WebClient webClient;

    public ReactiveInventoryClient(
            @LoadBalanced WebClient.Builder builder) {
        this.webClient = builder.build();
    }

    public Mono<Inventory> get(String id) {
        return webClient.get()
                .uri("http://inventory-service/api/items/{id}", id)
                .retrieve()
                .bodyToMono(Inventory.class);
    }
}
```

`@LoadBalanced WebClient.Builder` cần Spring Cloud LoadBalancer trên classpath. Với WebFlux, LoadBalancer sử dụng reactive integration; không tạo `WebClient` mới trong từng method nếu cần giữ filter, connector và customizer chung của ứng dụng.

## 10. Phân biệt client thường và client load-balanced

Một ứng dụng thường cần cả hai loại client:

- Client thường gọi URL vật lý hoặc endpoint bên ngoài như `https://api.partner.example`.
- Client load-balanced gọi service ID nội bộ như `http://inventory-service`.

Có thể khai báo hai builder:

```java
@Configuration(proxyBeanMethods = false)
public class ClientBuildersConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean
    @Primary
    RestClient.Builder directBuilder() {
        return RestClient.builder();
    }
}
```

Khi inject, chỉ rõ qualifier:

```java
@Component
public class PartnerApiClient {

    private final RestClient restClient;

    public PartnerApiClient(RestClient.Builder directBuilder) {
        this.restClient = directBuilder.build();
    }
}

@Component
public class InternalInventoryClient {

    private final RestClient restClient;

    public InternalInventoryClient(
            @LoadBalanced RestClient.Builder loadBalancedBuilder) {
        this.restClient = loadBalancedBuilder.build();
    }
}
```

`@Primary` giúp Spring chọn builder thường khi injection không có qualifier. Điểm quan trọng là client nội bộ dùng service ID phải nhận builder load-balanced một cách tường minh; client gọi internet không cần qua discovery.

## 11. Dependency injection không đồng nghĩa với tạo mọi thứ tự động

Khi nâng cấp, cần phân biệt ba việc:

| Thành phần | Ai cung cấp? | Ứng dụng cần làm gì? |
| --- | --- | --- |
| `DiscoveryClient` | Discovery starter và auto-configuration | Thêm đúng registry implementation, inject interface |
| `ServiceRegistry` | Discovery integration | Inject nếu cần thao tác registration |
| `RestTemplate` | Ứng dụng khai báo bean | Tạo `@Bean`; thêm `@LoadBalanced` nếu cần service ID |
| `RestClient.Builder` load-balanced | Ứng dụng khai báo builder với `@LoadBalanced` | Inject builder và build client dùng chung |
| `WebClient.Builder` load-balanced | Ứng dụng khai báo builder với `@LoadBalanced` | Inject builder trong Reactive client |
| `LoadBalancerClient` | Spring Cloud LoadBalancer | Inject khi cần API chọn instance trực tiếp |

Việc discovery tự cấu hình không có nghĩa mọi HTTP client đều được tự tạo. Ngược lại, việc ứng dụng phải khai báo HTTP client bean không có nghĩa phải tự tạo discovery implementation.

## 12. Lộ trình nâng cấp từ code cũ

Khi chuyển một ứng dụng hiện hữu, có thể thực hiện theo các bước:

1. Kiểm tra dependency registry hiện tại và xác nhận nó còn tương thích với Spring Boot/Spring Cloud release train đang dùng.
2. Xóa `@EnableDiscoveryClient` nếu annotation chỉ được dùng để bật discovery.
3. Nếu annotation đang đặt `autoRegister=false`, chuyển ý định đó sang `spring.cloud.service-registry.auto-registration.enabled=false`.
4. Tìm các lệnh `new EurekaDiscoveryClient`, `new ConsulClient`, `new RestTemplate()` hoặc `new WebClient...` trong code nghiệp vụ.
5. Chuyển dependency sang constructor injection và tạo bean tập trung trong cấu hình.
6. Thêm Spring Cloud LoadBalancer starter nếu HTTP client cần gọi bằng service ID.
7. Gắn `@LoadBalanced` cho đúng builder/client bean và qualifier tại điểm inject.
8. Giữ client thường cho URL vật lý hoặc external API.
9. Kiểm tra `@EnableFeignClients` và các annotation enable khác; không xóa chúng theo suy luận chung.
10. Viết integration test chứng minh discovery bean và client bean được tạo từ ApplicationContext.
11. Kiểm tra request thực tế được route tới instance do discovery cung cấp.

Không nên nâng cấp tất cả service cùng lúc mà chưa xác minh behavior. Hãy bắt đầu từ một service có ít downstream dependency, xác nhận đăng ký, discovery và load balancing, rồi áp dụng cùng mẫu cho các service khác.

## 13. Kiểm thử sau nâng cấp

### 13.1. Kiểm tra DiscoveryClient được cung cấp mà không cần annotation

Test này không khai báo `@EnableDiscoveryClient`. Nó giả định test runtime có starter discovery implementation:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class DiscoveryAutoConfigurationTests {

    @Autowired
    ApplicationContext applicationContext;

    @Test
    void discoveryClientIsProvidedByClasspathIntegration() {
        assertThat(applicationContext.getBeansOfType(DiscoveryClient.class))
                .isNotEmpty();
    }
}
```

Test kiểm tra bean được tạo trong ApplicationContext. Nếu ứng dụng có nhiều discovery implementation, có thể có composite hoặc nhiều bean tùy cấu hình; không nên assert tên implementation cụ thể trừ khi test đang kiểm tra một integration cụ thể.
Test này được đặt trong project đã có `@SpringBootConfiguration` của ứng dụng và dependency discovery ở test runtime. Nếu chạy như một test độc lập, hãy chỉ định `classes` trỏ tới test application configuration.

### 13.2. Kiểm tra client load-balanced được inject

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class LoadBalancedClientConfigurationTests {

    @Autowired
    @LoadBalanced
    RestClient.Builder loadBalancedBuilder;

    @Test
    void loadBalancedBuilderIsAvailable() {
        assertThat(loadBalancedBuilder).isNotNull();
    }
}
```

Test này giả định `RestClient` có trong Spring Framework baseline và ứng dụng đã khai báo builder bean như phần trước. Với ứng dụng dùng `RestTemplate` hoặc `WebClient`, kiểm tra bean có qualifier tương ứng.

### 13.3. Kiểm tra không dùng service ID bằng client thường

Một test integration nên khởi động hai instance giả của service `inventory-service`, đăng ký chúng với test discovery source, gửi nhiều request qua client load-balanced và xác nhận URI được phân giải sang các instance hợp lệ.

Không chỉ kiểm tra client bean tồn tại. Một bean có qualifier `@LoadBalanced` nhưng thiếu Spring Cloud LoadBalancer starter sẽ không có đầy đủ integration để phân giải service ID.

### 13.4. Kiểm tra auto-registration

Nếu môi trường yêu cầu không tự đăng ký:

1. Đặt `spring.cloud.service-registry.auto-registration.enabled=false`.
2. Khởi động context với registry integration.
3. Xác nhận `ServiceRegistry` không tự nhận registration của ứng dụng theo lifecycle mặc định.
4. Nếu ứng dụng có luồng register thủ công, xác nhận chỉ luồng đó thực hiện đăng ký.

Kiểm thử với registry test container hoặc mock server phù hợp; không dùng registry production để kiểm tra hành vi này.

## 14. Lỗi thường gặp khi nâng cấp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Xóa `@EnableDiscoveryClient` rồi không thấy registry | Discovery starter thiếu hoặc bị disable | Kiểm tra runtime classpath và `spring.cloud.discovery.enabled` |
| `DiscoveryClient` có nhưng không tìm thấy instance | Registry chưa có registration hoặc service ID sai | Kiểm tra registration, namespace và service ID |
| Gọi `http://inventory-service` bị DNS error | Dùng client thường thay vì load-balanced client | Khai báo bean `@LoadBalanced` và thêm LoadBalancer starter |
| Inject `RestTemplate` báo thiếu bean | Ứng dụng chưa khai báo `RestTemplate` bean | Tạo `@Bean` trong configuration |
| Inject builder báo nhiều bean cùng kiểu | Có client thường và load-balanced nhưng thiếu qualifier/primary | Dùng `@LoadBalanced` hoặc `@Primary` |
| Client không nhận interceptor/observability | Tạo client bằng `new` ngoài ApplicationContext | Dùng builder bean và Boot customizer/configurer |
| Auto-registration vẫn xảy ra sau khi bỏ annotation | Trước đó annotation đã đặt `autoRegister=false` nhưng chưa chuyển sang property | Đặt `spring.cloud.service-registry.auto-registration.enabled=false` |
| `@EnableFeignClients` bị xóa cùng discovery annotation | Nhầm hai annotation có chức năng khác nhau | Khôi phục annotation scan Feign client nếu ứng dụng dùng OpenFeign |
| LoadBalancer không có instance | Chỉ có LoadBalancer starter nhưng không có nguồn instance | Thêm discovery implementation hoặc cấu hình SimpleDiscoveryClient |
| Gọi URL vật lý qua load-balanced client | Client bị gắn `@LoadBalanced` dù URL không phải service ID | Dùng client thường cho endpoint vật lý |

## 15. Checklist hoàn tất nâng cấp

1. Đã xác định registry implementation và dependency tương thích.
2. Đã bỏ `@EnableDiscoveryClient` khi chỉ dùng nó để bật discovery.
3. Đã giữ nguyên các annotation enable độc lập như `@EnableFeignClients`.
4. Đã chuyển `autoRegister=false` sang property nếu cần.
5. Đã inject `DiscoveryClient` hoặc `ServiceRegistry` qua Spring.
6. Không còn tự tạo discovery implementation trong code nghiệp vụ.
7. Đã khai báo bean cho HTTP client cần dùng.
8. Đã phân biệt client thường với client load-balanced.
9. Đã thêm LoadBalancer starter nếu gọi bằng service ID.
10. Đã dùng `@LoadBalanced` và qualifier đúng chỗ.
11. Đã kiểm thử auto-configuration không cần `@EnableDiscoveryClient`.
12. Đã kiểm thử routing tới service instance và auto-registration theo yêu cầu.

## 16. Tài liệu tham khảo

- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html): `@EnableDiscoveryClient`, auto-registration, `DiscoveryClient`, `ServiceRegistry`, `RestTemplate`, `RestClient` và `WebClient`.
- [Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): tích hợp LoadBalancer với discovery client, `RestTemplate`, `RestClient` và `WebClient`.
- [Spring Cloud Netflix](https://docs.spring.io/spring-cloud-netflix/reference/): cấu hình Eureka Discovery Client.
- [Spring Cloud Consul](https://docs.spring.io/spring-cloud-consul/reference/): cấu hình Consul Discovery.

Khi nâng cấp, hãy bỏ giả định rằng discovery cần một annotation enable riêng, nhưng đừng bỏ các bean HTTP client mà ứng dụng thực sự cần. Dependency cung cấp discovery implementation; Spring container quản lý các client; `@LoadBalanced` nối HTTP client với service discovery và LoadBalancer. Khi ba trách nhiệm này được tách rõ, code nghiệp vụ ít phụ thuộc implementation cụ thể và dễ kiểm thử hơn.
