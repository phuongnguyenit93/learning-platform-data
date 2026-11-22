# Điều kiện phiên bản và phạm vi tự cấu hình được hỗ trợ

**Spring HTTP Interface** cho phép khai báo HTTP API bằng Java interface với `@HttpExchange`, `@GetExchange`, `@PostExchange`…, rồi gọi API qua một proxy sử dụng `RestClient` hoặc `WebClient`. Tuy nhiên, **việc tạo được proxy HTTP không đồng nghĩa proxy tự động dùng Spring Cloud LoadBalancer**. Khả năng đăng ký proxy, cấu hình HTTP client và tự gắn cơ chế chọn `ServiceInstance` phụ thuộc rõ ràng vào **thế hệ Spring Framework, Spring Boot và Spring Cloud**.

Trong module Spring Cloud LoadBalancer, hiểu đúng ranh giới phiên bản giúp tránh ba lỗi phổ biến:

1. Áp dụng `@ImportHttpServices` hoặc `spring.http.serviceclient.*` cho dự án Spring Boot 3 / Spring Framework 6 rồi kỳ vọng tự cấu hình giống Boot 4.
2. Tạo HTTP Interface proxy bằng tay nhưng quên gắn LoadBalancer vào `RestClient`/`WebClient` phía dưới.
3. Tưởng rằng chỉ cần đặt `base-url: http://catalog-service` là HTTP Service group ở Spring Cloud 5 tự cân bằng tải — trong khi cách cấu hình này **không kích hoạt integration LoadBalancer của group**.

Bài học thuộc chương **HTTP Interface**, tập trung vào điều kiện phiên bản, điều kiện classpath/bean và **phạm vi tự cấu hình thực sự được hỗ trợ**. Các ví dụ dùng dịch vụ logic `catalog-service` có nhiều bản sao do discovery cung cấp.

## 1. Phân biệt bốn tầng trách nhiệm

Bốn thành phần thường được nhắc đến chung nhưng không phải cùng một tính năng:

| Tầng | Công nghệ | Trách nhiệm |
|---|---|---|
| **Khai báo HTTP contract** | Spring Framework `@HttpExchange` / `@GetExchange` | Mô tả HTTP method, path, headers, tham số, body và kiểu trả về |
| **Tạo proxy HTTP** | `HttpServiceProxyFactory`; từ Framework 7 có `@ImportHttpServices` và registry theo nhóm | Sinh đối tượng implement interface để mã nghiệp vụ inject và gọi |
| **Cấu hình HTTP transport** | `RestClient` / `WebClient`; từ Boot 4 có auto-configuration HTTP Service group | Đặt URL, timeout, SSL, default headers, codecs và thực thi HTTP |
| **Cân bằng tải phía client** | Spring Cloud LoadBalancer, `ServiceInstanceListSupplier`, interceptor/filter | Dựa vào service ID để lấy và chọn một `ServiceInstance` trước khi gửi request |

~~~mermaid
flowchart TD
    A["Mã nghiệp vụ gọi CatalogHttpApi"]
    B["HTTP Interface proxy"]
    C["RestClient hoặc WebClient của nhóm"]
    D{"Group/client có<br/>tích hợp LoadBalancer?"}
    E["LoadBalancer chọn ServiceInstance"]
    F["Dùng URL trực tiếp"]
    G["HTTP transport gửi request"]
    H["Backend trả response"]
    A --> B --> C --> D
    D -->|"Có"| E --> G
    D -->|"Không"| F --> G
    G --> H
~~~

`@GetExchange` không trực tiếp truy vấn Eureka; `@ImportHttpServices` cũng không tự cung cấp registry bản sao. Muốn gọi bằng service ID phải có đủ nguồn `ServiceInstance` và integration LoadBalancer ở HTTP client đang thực thi.

## 2. Bảng tương thích theo thế hệ Spring

Điều kiện hỗ trợ nên xét theo **khả năng cụ thể**, thay vì chỉ nhìn thấy một annotation trên classpath.

| Hệ sinh thái | HTTP Interface client | Đăng ký tự động theo group | Tự tích hợp LoadBalancer cho HTTP Service group |
|---|---|---|---|
| **Spring Framework 6.0**, thường cùng Boot 3.0/3.1 | Có `@HttpExchange`, `HttpServiceProxyFactory` và hỗ trợ tạo proxy qua adapter thích hợp như `WebClientAdapter` | **Chưa có `@ImportHttpServices` của Framework 7** | Không có cơ chế group auto-config của Spring Cloud LoadBalancer 5; cấu hình client và proxy bằng tay |
| **Spring Framework 6.1–6.x**, thường cùng Boot 3.2–3.x | Có thêm `RestClient` / `RestClientAdapter`, có thể tự cấu hình proxy dùng `RestClient` hoặc `WebClient` | Không có mô hình group registry của Framework 7 | Dùng `@LoadBalanced RestClient.Builder` hoặc `@LoadBalanced WebClient.Builder` và `HttpServiceProxyFactory` bằng tay |
| **Spring Framework 7 + Spring Boot 4** | Có HTTP Interface, `@ImportHttpServices`, `HttpServiceProxyRegistry` và HTTP Service group | **Có** đăng ký proxy theo group và cấu hình group qua `spring.http.serviceclient.<group>.*` | Chưa mặc nhiên có cân bằng tải nếu không có tích hợp Spring Cloud phù hợp |
| **Spring Framework 7 + Boot 4 + Spring Cloud LoadBalancer 5.0+** | Các khả năng ở trên | **Có** | **Có** auto-configuration integration cho HTTP Service group theo các điều kiện URL và bean/classpath được mô tả ở phần sau |

Mốc quan trọng từ tài liệu chính thức:

- Spring Framework **6.0** giới thiệu HTTP Service Interface.
- Spring Framework **6.1** giới thiệu `RestClient` và adapter tương ứng cho HTTP Interface.
- Spring Framework **7.0** giới thiệu cơ chế `@ImportHttpServices` và registry/group hỗ trợ đăng ký proxy như Spring beans.
- Spring Boot **4.0** cung cấp auto-configuration HTTP Service Clients theo group.
- Spring Cloud LoadBalancer **5.0.0** bắt đầu hỗ trợ **tự tích hợp LoadBalancer cho các HTTP Service groups** thông qua group configurer.

Đây là **mốc của từng tính năng**, không phải khuyến nghị tùy ý ghép các version. Khi triển khai, chọn Spring Boot/Spring Cloud release train tương thích theo BOM, không tự ép Framework 7 vào dự án Boot 3 hoặc Spring Cloud 5 vào một tổ hợp chưa được hỗ trợ.

## 3. Phạm vi của HTTP Interface trong Spring Framework 6

Ở Spring Framework 6, bạn có thể định nghĩa HTTP contract:

~~~java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange
public interface CatalogHttpApi {

    @GetExchange("/products/{id}")
    ProductDto findProduct(@PathVariable("id") Long id);
}

record ProductDto(Long id, String name) {}
~~~

Proxy sẽ sử dụng HTTP client mà bạn cung cấp cho `HttpServiceProxyFactory`. Trong dự án Spring Framework 6.x, người phát triển thường **tự tạo factory và tự đăng ký proxy như bean**, thay vì chỉ dùng `@ImportHttpServices`.

### Ví dụ Spring Framework 6.1+ và RestClient

Để dùng `RestClient` (có từ Framework 6.1) kết hợp Spring Cloud LoadBalancer bản tương thích:

~~~java
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
    RestClient.Builder catalogLoadBalancedBuilder() {
        return RestClient.builder();
    }

    @Bean
    CatalogHttpApi catalogHttpApi(
            @LoadBalanced RestClient.Builder catalogLoadBalancedBuilder) {

        RestClient restClient = catalogLoadBalancedBuilder
                .baseUrl("http://catalog-service")
                .build();

        HttpServiceProxyFactory factory = HttpServiceProxyFactory
                .builderFor(RestClientAdapter.create(restClient))
                .build();

        return factory.createClient(CatalogHttpApi.class);
    }
}
~~~

Luồng này được chia thành hai bước rõ ràng:

1. `@LoadBalanced RestClient.Builder` đưa khả năng chọn instance vào HTTP client; `http://catalog-service` là URL **logic**.
2. `HttpServiceProxyFactory` tạo `CatalogHttpApi` proxy; proxy sử dụng `RestClient` **đã được tích hợp LoadBalancer** để gọi HTTP.

Nếu thay `catalogLoadBalancedBuilder` bằng `RestClient.create("http://catalog-service")` thông thường, proxy vẫn được tạo nhưng hostname có thể được xử lý qua DNS thay vì Spring Cloud LoadBalancer.

Trong ứng dụng Boot 3, nếu cần các tùy chỉnh Boot như observability, message converter hoặc tracing trên builder, nên phối hợp `RestClientBuilderConfigurer` thay vì luôn tạo `RestClient.builder()` thô. Các API xây dựng proxy có thay đổi giữa các minor version Framework 6; hãy dùng tài liệu đúng phiên bản biên dịch của dự án.

### Còn WebClient thì sao?

Spring Framework 6.0 đã hỗ trợ HTTP Interface dựa trên `WebClientAdapter`. Với WebClient, mẫu kiến trúc tương tự: tạo `@LoadBalanced WebClient.Builder`, tạo WebClient có `baseUrl("http://catalog-service")`, gắn WebClient vào adapter và tạo proxy bằng API `HttpServiceProxyFactory` phù hợp phiên bản.

Không nên sao chép mã dùng `RestClientAdapter` của Framework 6.1 vào dự án Framework 6.0, vì `RestClient` chưa tồn tại ở phiên bản 6.0.

**Tóm lại:** Spring Framework 6 hỗ trợ HTTP Interface nhưng chưa có **cơ chế tự đăng ký HTTP Service groups của Framework 7 / Boot 4**. Người phát triển vẫn có thể tích hợp LoadBalancer thủ công với HTTP client bên dưới.

## 4. Framework 7 và Boot 4 tự cấu hình những gì?

Spring Framework 7 giới thiệu `@ImportHttpServices`. Annotation này xác định HTTP Interface cần đăng ký và đặt chúng vào các **group**. Mỗi group có thể chia sẻ cấu hình HTTP client và proxy factory.

Ví dụ:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.service.registry.ImportHttpServices;

@SpringBootApplication
@ImportHttpServices(
        group = "catalog-service",
        types = CatalogHttpApi.class
)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Với Boot 4 và các module cần thiết trên classpath, HTTP Service client auto-configuration có thể:

- Tạo các HTTP Interface proxy và đăng ký chúng như Spring beans để inject.
- Tổ chức proxy theo group thông qua `HttpServiceProxyRegistry`.
- Cấu hình `RestClient` hoặc `WebClient` cho group; mặc định dùng `RestClient` khi không chỉ định loại khác.
- Áp dụng thuộc tính cấu hình như `base-url`, `connect-timeout`, `read-timeout`, SSL bundles, headers hoặc các tùy chọn phù hợp version.
- Cho phép tinh chỉnh bằng `RestClientHttpServiceGroupConfigurer` hoặc `WebClientHttpServiceGroupConfigurer`.

**Boot 4 auto-config chủ yếu quản lý proxy và HTTP client**, không tự tạo server instance, không tự bật retries, không xác định thuật toán LoadBalancer, không tự cung cấp Eureka/Consul và không bảo đảm endpoint khỏe.

Nếu không khai báo `group`, proxy vào group mặc định tên **`default`**. Trong bài toán gọi nhiều service ID, khai báo group trùng service ID giúp tránh vô tình định tuyến tới service tên `default`.

### Ví dụ cấu hình thuộc tính theo group

~~~yaml
spring:
  http:
    clients:
      connect-timeout: 1s
    serviceclient:
      catalog-service:
        connect-timeout: 2s
        read-timeout: 3s
~~~

Các thuộc tính này thuộc hệ thống `spring.http.*` của **Spring Boot 4**, không phải cú pháp tự động có hiệu lực với HTTP Interfaces của Boot 3.

Tương tự, cấu hình HTTP Service group **không thay thế** `spring.cloud.loadbalancer.*`. Một bên điều chỉnh HTTP client và proxy; bên kia điều chỉnh lựa chọn instance, supplier, health check và cache.

## 5. Khi nào Spring Cloud tự gắn LoadBalancer cho HTTP Service group?

Kể từ **Spring Cloud LoadBalancer 5.0.0**, Spring Cloud có tích hợp riêng với HTTP Service Clients AutoConfiguration qua hai kiểu group configurer:

- `LoadBalancerRestClientHttpServiceGroupConfigurer` — cho nhóm dùng `RestClient` (blocking).
- `LoadBalancerWebClientHttpServiceGroupConfigurer` — cho nhóm dùng `WebClient` (reactive).

Những component này cấu hình thêm thành phần tích hợp LoadBalancer tương ứng, nếu bean cần thiết có trong application context:

- `DeferringLoadBalancerInterceptor` cho RestClient.
- `DeferringLoadBalancerExchangeFilterFunction` cho WebClient.

Điều quan trọng là **tự cấu hình theo group không áp dụng vô điều kiện cho mọi URL**. Quy tắc tài liệu Spring Cloud LoadBalancer mô tả như sau:

1. Nếu `spring.http.serviceclient.<group>.base-url` **không được khai báo** (`null`), Spring Cloud tạo URL logic theo tên group và gắn LoadBalancer.
2. Nếu `base-url` được khai báo với **scheme `lb://`**, Spring Cloud cũng gắn LoadBalancer.
3. Nếu `base-url` được khai báo với **scheme khác `lb`**, integration LoadBalancer theo group **không được gắn**, kể cả host của URL trông giống service ID.

~~~mermaid
flowchart TD
    A["@ImportHttpServices<br/>group=catalog-service"]
    B{"spring.http.serviceclient<br/>.catalog-service.base-url?"}
    C["Không khai báo"]
    D["lb://catalog-service"]
    E["http://catalog-service hoặc<br/>https://some-host"]
    F["Thêm LoadBalancer adapter<br/>và URL logic"]
    G["Không tự gắn LB<br/>gọi URL theo HTTP client"]
    H["ServiceInstanceListSupplier<br/>chọn instance phù hợp"]
    A --> B
    B --> C --> F --> H
    B --> D --> F
    B --> E --> G
~~~

### Bảng hành vi URL của HTTP Service group

Giả sử group tên `catalog-service` và tích hợp Cloud 5 hoạt động:

| Giá trị `base-url` của group | LoadBalancer auto-config theo group? | Cách xác định đích |
|---|---|---|
| **Không đặt property** | **Có** | Tạo URL logic `http://catalog-service`; chọn instance theo service ID tên group |
| `lb://catalog-service` | **Có** | Gắn LB, dùng service ID trong URL `lb://` |
| `lb://catalog-service/api` | **Có** | Gắn LB, giữ phần path phù hợp khi dựng request |
| `http://catalog-service` | **Không** | Dùng URL như một hostname bình thường; có thể phải phân giải DNS |
| `https://catalog.example.internal` | **Không** | HTTP client gọi hostname thật hoặc hạ tầng DNS/proxy |
| `http://127.0.0.1:8081` | **Không** | HTTP client gọi endpoint cụ thể |

**Tình huống dễ sai nhất:** `http://catalog-service` có thể là URL logic khi bạn tự tạo `@LoadBalanced RestClient.Builder` (cách thủ công), nhưng **khi đặt nó thành property `base-url` của HTTP Service group trong cơ chế tự cấu hình Cloud 5, nó lại không kích hoạt gắn LoadBalancer theo group**.

Hai cơ chế khác nhau có điểm kích hoạt khác nhau; đừng suy luận kết quả từ vẻ ngoài của URL.

### HTTPS và instance bảo mật

Khi `base-url` không được khai báo hoặc dùng `lb://`, scheme HTTP ban đầu được đặt phù hợp để LoadBalancer giải quyết đích. Nếu instance được chọn đánh dấu là secure theo dữ liệu `ServiceInstance`, scheme cuối có thể chuyển thành `https`. Điều này không thay thế việc cấu hình TLS trust store, certificate validation hoặc HTTP connector thực tế.

## 6. Ví dụ tự cấu hình hoàn chỉnh với Boot 4 và Spring Cloud 5

Đây là ví dụ cho **Spring Boot 4 + Spring Framework 7 + Spring Cloud LoadBalancer 5.x tương thích**.

### 6.1. Khai báo interface HTTP

~~~java
package com.example.orders.client;

import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange
public interface CatalogHttpApi {

    @GetExchange("/products/{id}")
    ProductDto getProduct(@PathVariable("id") Long id);
}
~~~

Giả sử `ProductDto` là DTO trong cùng package:

~~~java
package com.example.orders.client;

public record ProductDto(Long id, String name) {}
~~~

### 6.2. Import vào group có tên bằng service ID

~~~java
package com.example.orders;

import com.example.orders.client.CatalogHttpApi;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.service.registry.ImportHttpServices;

@SpringBootApplication
@ImportHttpServices(group = "catalog-service", types = CatalogHttpApi.class)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Từ đây `CatalogHttpApi` là Spring bean có thể được inject vào service. Ví dụ:

~~~java
package com.example.orders;

import com.example.orders.client.CatalogHttpApi;
import com.example.orders.client.ProductDto;
import org.springframework.stereotype.Service;

@Service
class CatalogGateway {

    private final CatalogHttpApi catalog;

    CatalogGateway(CatalogHttpApi catalog) {
        this.catalog = catalog;
    }

    ProductDto load(long id) {
        return catalog.getProduct(id);
    }
}
~~~

### 6.3. Thêm dependency phù hợp

Với **Spring Boot 4** và Gradle Kotlin DSL, phần dependency tối thiểu theo hướng blocking có thể là:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-restclient")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

Cần cấu hình Spring Boot plugin và Spring Cloud BOM/release train tương thích; snippet này không đại diện cho toàn bộ `build.gradle.kts`.

Nếu ứng dụng có REST controllers, cần thêm starter WebMVC phù hợp. Nếu dùng nguồn discovery động như Eureka hoặc Consul, thêm starter tương ứng. Để chạy bài demo, có thể dùng cấu hình instance tĩnh.

### 6.4. Cung cấp ServiceInstance qua SimpleDiscoveryClient

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
  http:
    serviceclient:
      catalog-service:
        connect-timeout: 2s
        read-timeout: 3s
~~~

**Cố ý không đặt `spring.http.serviceclient.catalog-service.base-url`.** Theo cơ chế Cloud 5, khi group thiếu base URL, URL logic được mặc định theo tên group, ví dụ `http://catalog-service`, và interceptor LoadBalancer được tự gắn nếu đủ điều kiện.

Khi muốn viết rõ rằng URL này cần load balancing, cấu hình có thể dùng một lựa chọn khác:

~~~yaml
spring:
  http:
    serviceclient:
      catalog-service:
        base-url: lb://catalog-service
        connect-timeout: 2s
        read-timeout: 3s
~~~

Hai block YAML trên là **hai phương án thay thế**, không phải ghép cả hai thành một cấu hình có ý nghĩa mới.

Địa chỉ `127.0.0.1` chỉ dùng được khi các server thử nghiệm và caller ở cùng máy hoặc network namespace. Trong container, cần hostname/URI mà caller thực sự truy cập được.

### Kết quả mong đợi

Nếu cả hai instance phục vụ `GET /products/42`, một lần gọi `catalog.getProduct(42L)` đi theo đường:

~~~text
HTTP Interface proxy
  -> RestClient của group catalog-service
  -> DeferringLoadBalancerInterceptor
  -> LoadBalancer chọn 127.0.0.1:8081 hoặc :8082
  -> HTTP transport gửi GET /products/42
  -> Decode response về ProductDto
~~~

Chọn instance thành công không đảm bảo HTTP request thành công: network timeout, endpoint sai hoặc server lỗi vẫn có thể gây exception.

## 7. Cấu hình nhóm reactive WebClient

Framework 7 cho phép định nghĩa group dùng `WebClient` thay cho `RestClient`. Trong `@ImportHttpServices`, dùng `clientType`:

~~~java
import org.springframework.web.service.registry.HttpServiceGroup;
import org.springframework.web.service.registry.ImportHttpServices;

@ImportHttpServices(
        group = "catalog-service",
        types = ReactiveCatalogHttpApi.class,
        clientType = HttpServiceGroup.ClientType.WEB_CLIENT
)
class ReactiveHttpClientsConfiguration {
}
~~~

Interface reactive có thể trả `Mono<ProductDto>`:

~~~java
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import reactor.core.publisher.Mono;

@HttpExchange
interface ReactiveCatalogHttpApi {

    @GetExchange("/products/{id}")
    Mono<ProductDto> getProduct(@PathVariable("id") Long id);
}
~~~

Với các dependency WebFlux và integration LoadBalancer phù hợp, auto-config HTTP Service group sử dụng `WebClient.Builder` cùng `DeferringLoadBalancerExchangeFilterFunction`.

Nếu project không có đủ các type của WebClient/reactive HTTP client trên classpath hoặc thiếu cấu hình hỗ trợ group tương ứng, không thể kỳ vọng auto-config reactive tự xuất hiện chỉ vì interface trả `Mono`.

**Nguyên tắc:** kiểu client được dùng phải phù hợp mô hình gọi. `RestClient` là blocking; `WebClient` là reactive. `@ImportHttpServices` không tự biến kết nối blocking thành non-blocking chỉ vì code nghiệp vụ muốn dùng reactive.

## 8. Những phạm vi không được bảo đảm bởi tự cấu hình

Các khả năng sau thường bị kỳ vọng quá mức:

| Kỳ vọng | Điều thực tế cần kiểm tra |
|---|---|
| Có `@HttpExchange` là proxy được tạo | Trong Framework 6 cần tự tạo proxy; Framework 7 có thể đăng ký qua `@ImportHttpServices` hoặc registrar phù hợp |
| Có Boot 4 là tự có LoadBalancer | Phải có Spring Cloud LoadBalancer tương thích và bean integration; Boot auto-config không tự cung cấp discovery policy |
| Có Spring Cloud 5 là mọi HTTP Interface đều tự cân bằng tải | Cơ chế hỗ trợ mặc định chỉ gắn vào **HTTP Service groups được auto-config**, theo quy tắc base URL |
| Mọi URL mang service ID đều auto load-balance | Group có `http://service-id` đặt tường minh không được Cloud 5 group configurer tự gắn LB |
| Nhóm `default` sẽ tự gọi đúng backend | Tên group không khai báo mặc định là `default`; cần đặt group có chủ đích |
| Có LoadBalancer là chắc chắn có instance | Cần `ServiceInstanceListSupplier` hoặc discovery có dữ liệu |
| Có LoadBalancer là health check/retry/timeout đều tự tối ưu | Các cơ chế này có dependency, cấu hình và ngữ nghĩa riêng |
| Cấu hình theo group áp dụng cho Feign | `@FeignClient` có cơ chế Spring Cloud OpenFeign và config riêng |
| Gắn group auto-config vào proxy tự tạo từ `HttpServiceProxyFactory` | Proxy tạo thủ công không mặc nhiên nhận group configurer của Boot 4; cần gắn đúng builder/adapter |
| Chạy trên native image giống JVM mà không cần kiểm tra | Cần xác minh AOT/native support, service IDs, reflection/configuration theo version và ứng dụng cụ thể |

Group configurers của Spring Cloud tác động đến các group phù hợp được đăng ký trong cơ chế HTTP Service Clients. Chúng không phải một interceptor toàn cục tự áp dụng cho mọi đối tượng `RestClient`, `WebClient` hoặc `RestTemplate` trong JVM.

### Circuit breaker không tự thay thế LoadBalancer

Một số phiên bản Spring Cloud hỗ trợ tích hợp circuit breaker cho HTTP Service groups khi có dependency và cấu hình phù hợp. Nhưng không nên xem circuit breaker, retry hay fallback là hệ quả đương nhiên của việc bật HTTP Service group. Chúng là những lớp resilience riêng, có thể ảnh hưởng đến tổng thời gian và số lần gọi.

## 9. Các điều kiện classpath và cấu hình cần kiểm tra

Khi HTTP Interface không hoạt động như mong đợi, hãy kiểm tra theo thứ tự:

**1. Phiên bản**

- `Spring Framework 6.x` hay `7.x`?
- `Spring Boot 3.x` hay `4.x`?
- `Spring Cloud Commons/LoadBalancer 4.x` hay `5.x`?
- Release train có thực sự tương thích với Spring Boot không?

**2. Đăng ký proxy**

- Framework 7/Boot 4: có `@ImportHttpServices` với `types` hoặc `basePackages` đúng không?
- Framework 6: có bean gọi `HttpServiceProxyFactory.createClient(...)` không?
- Interface có method được đánh dấu `@GetExchange`, `@HttpExchange` hoặc annotation tương ứng không?

**3. HTTP client**

- Group dùng `RestClient` hay `WebClient`?
- Dependencies hỗ trợ client đã có trên classpath?
- Có auto-config Boot 4 hay builder/adapter tự tạo theo Framework 6?

**4. LoadBalancer**

- Có `spring-cloud-starter-loadbalancer`?
- `spring.cloud.loadbalancer.enabled` có bị đặt thành `false` không?
- Có integration interceptor/filter được gắn cho đúng group hoặc builder không?
- Có nguồn discovery/`ServiceInstanceListSupplier` và service ID thực sự có bản sao?

**5. URL**

- Group `base-url` bỏ trống, dùng `lb://` hay đã cấu hình `http://`?
- Tên `group` có khớp service ID, hoặc host của `lb://` có đúng?
- URI của instance có scheme/host/port có thể truy cập từ client?

## 10. Chẩn đoán các lỗi thường gặp

| Hiện tượng | Nguyên nhân hay gặp | Cách kiểm tra |
|---|---|---|
| IDE không nhận `@ImportHttpServices` | Framework 6 thay vì 7 hoặc thiếu module `spring-web` phù hợp | Kiểm tra dependency tree, không nâng riêng một jar Spring |
| Không có bean `CatalogHttpApi` | Chưa import group/không scan đúng interface hoặc chưa tạo proxy thủ công | Kiểm tra cấu hình import/bean và application context |
| Property `spring.http.serviceclient.*` dường như không có tác dụng | Đang dùng Boot 3 hoặc proxy được tạo thủ công không thuộc auto-config group | Kiểm tra Boot version và cách đăng ký client |
| Group không tìm được instance | Sai group/service ID, discovery trống hoặc supplier lọc hết | Kiểm tra `DiscoveryClient.getInstances(serviceId)` |
| `UnknownHostException: catalog-service` | Group được đặt tường minh `base-url: http://catalog-service` khiến không có auto LB; hoặc thiếu interceptor | Kiểm tra property và cấu hình bean |
| HTTP Interface luôn gọi một endpoint | Dùng URL vật lý hoặc group không gắn LB | Kiểm tra `base-url`, HTTP client config và service list |
| Reactive client không khởi tạo | Chọn `WEB_CLIENT` nhưng thiếu WebClient/dependency phù hợp | Kiểm tra WebFlux, connector và auto-config |
| Lỗi HTTP 503 | Có thể không có instance, cũng có thể backend/proxy trả 503 | Xem có bước chọn instance và request có đến server không |
| Timeout khi gọi bản sao đã chọn | Lỗi transport/server hoặc endpoint stale | Kiểm tra network, backend latency và timeout của client |
| Mã ứng dụng cũ dùng Framework 6 compile lỗi sau migration | API proxy/adapter/group thay đổi giữa version | Chọn đúng API cho release và rà soát hướng dẫn migration |

Không nên chẩn đoán bằng mã HTTP status đơn lẻ. Cần phân biệt **không có proxy**, **proxy có nhưng thiếu integration**, **LoadBalancer không có instance**, và **HTTP transport thất bại sau khi đã chọn instance**.

### Quan sát bằng log/metrics

Các thông tin hữu ích:

~~~text
group=catalog-service
baseUrl=lb://catalog-service
loadBalancerIntegration=true
selectedServiceId=catalog-service
selectedInstance=127.0.0.1:8082
httpStatus=200 durationMs=45
~~~

Đây chỉ là ví dụ định dạng log mong muốn, **không phải tên trường log mặc định do Spring tự sinh**. Nên kết hợp logging/observability của HTTP client, Spring Cloud LoadBalancer và distributed tracing khi đã được cấu hình. Tránh ghi headers hoặc token nhạy cảm.

## 11. Bài thực hành kiểm tra đúng phạm vi hỗ trợ

### Kịch bản A: Boot 4 + Cloud 5 auto-config group

1. Chạy hai backend `catalog-service` với `GET /whoami` trả về instance ID khác nhau.
2. Khai báo `CatalogHttpApi` có `@GetExchange("/whoami")` và dùng `@ImportHttpServices(group = "catalog-service", types = ...)`.
3. Thêm starter hỗ trợ HTTP client và LoadBalancer, cấu hình danh sách hai URI trong `SimpleDiscoveryClient`.
4. **Không đặt `spring.http.serviceclient.catalog-service.base-url`**; gọi nhiều lần qua proxy và quan sát instance được chọn.
5. Chạy lại với `base-url: lb://catalog-service`; xác minh LoadBalancer vẫn được tích hợp.
6. Chạy lại với `base-url: http://catalog-service` trong môi trường không có DNS tương ứng; xác minh đây không phải đường tích hợp group LB tự động.
7. Chạy lại với `base-url: http://127.0.0.1:8081`; kiểm tra mọi request gọi endpoint cố định.

### Kịch bản B: Boot 3 / Framework 6.1, tạo proxy thủ công

1. Khai báo interface HTTP tương tự.
2. Đăng ký `@LoadBalanced RestClient.Builder` và dùng `HttpServiceProxyFactory` để tạo proxy như mục 3.
3. Gọi `http://catalog-service` qua RestClient đã tích hợp LB; kiểm chứng chọn nhiều instance.
4. Đổi sang `RestClient.create("http://catalog-service")` và so sánh trong môi trường không có DNS/mesh cho hostname đó.
5. Không thêm `@ImportHttpServices` của Framework 7 vào code Boot 3; đây không phải API có sẵn của thế hệ này.

### Tiêu chí xác nhận

| Câu hỏi | Bằng chứng cần thu thập |
|---|---|
| Proxy được tạo chưa? | Có bean của interface và inject thành công |
| Group có đúng service ID chưa? | `group` hoặc hostname `lb://` khớp nguồn instance |
| LoadBalancer có chạy không? | Có log/observation chọn `ServiceInstance` hoặc kiểm thử nhiều instance |
| Request tới đích nào? | Instance ID từ server, host/port đích hoặc network trace |
| Timeout thuộc tầng nào? | Exception và thời gian ở bước selection/HTTP transport |
| Thay đổi property có tác dụng không? | So sánh `base-url` không đặt, `lb://` và URL trực tiếp |

## 12. Nguyên tắc lựa chọn cách tích hợp

- **Dự án dùng Boot 3 / Framework 6:** HTTP Interface vẫn phù hợp; tạo proxy thủ công và chủ động gắn LoadBalancer vào `RestClient` hoặc `WebClient`.
- **Dự án dùng Boot 4 / Framework 7:** tận dụng `@ImportHttpServices`, group registry và `spring.http.serviceclient.*` để giảm mã cấu hình lặp lại.
- **Dự án muốn HTTP Service group tự load-balance:** cần thêm Spring Cloud LoadBalancer 5.x tương thích, nguồn `ServiceInstance` và chọn **không khai báo `base-url` hoặc dùng `lb://`**.
- **Dự án gọi API bên ngoài qua hostname cố định:** có thể dùng `https://api.example.com` trực tiếp trong cấu hình group và không kỳ vọng LoadBalancer chọn instance.
- **Dự án có nhiều HTTP clients:** giữ ranh giới giữa group auto-config, proxy tạo thủ công và Spring Cloud OpenFeign; mỗi cơ chế có điều kiện và thuộc tính riêng.

**Kết luận:** Spring HTTP Interface là **contract gọi HTTP**; khả năng proxy được đăng ký tự động theo nhóm đến từ **Framework 7 / Boot 4**; khả năng tự gắn **Spring Cloud LoadBalancer** cho nhóm đến từ **LoadBalancer 5.0+** trong tổ hợp phiên bản hỗ trợ. Nắm chắc các mốc này, kiểm tra classpath và đọc kỹ quy tắc `base-url` sẽ giúp tích hợp `RestClient`, `WebClient`, discovery, timeout và định tuyến theo service ID mà không phụ thuộc các giả định sai về auto-configuration.

**Tài liệu tham khảo chính thức:**

- [Spring Framework – HTTP Interface](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html#rest-http-interface)
- [Spring Boot – Calling REST Services / HTTP Service Interface Clients](https://docs.spring.io/spring-boot/reference/io/rest-client.html#io.rest-client.http-service-clients)
- [Spring Cloud Commons – LoadBalancer Integration for Spring HTTP Service Clients AutoConfiguration](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring – HTTP Service Client Enhancements (23/09/2025)](https://spring.io/blog/2025/09/23/http-service-client-enhancements/)

