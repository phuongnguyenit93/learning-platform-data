# Tên dịch vụ bị phân giải như DNS: tìm lỗi tích hợp client

Một lỗi thường gặp khi tích hợp **Spring Cloud LoadBalancer** là lập trình viên viết:

~~~java
restClient.get()
        .uri("http://catalog-service/products/42")
        .retrieve()
        .body(ProductDto.class);
~~~

nhưng ứng dụng lại báo lỗi tương tự **`UnknownHostException: catalog-service`**. Người viết mong `catalog-service` được coi là **service ID** và Spring Cloud chọn một `ServiceInstance`; HTTP transport thì đang coi nó là **hostname DNS thông thường**.

Tình huống này không đồng nghĩa discovery bị hỏng. Nguyên nhân có thể là **RestClient/WebClient/Feign chưa được gắn thành phần LoadBalancer**, một bean khác được inject nhầm, client được tạo thủ công thay vì dùng builder do Spring quản lý, hoặc một URL cấu hình cố định làm bỏ qua cơ chế chọn instance.

Tuy nhiên, cũng có trường hợp LoadBalancer **đã chọn thành công instance**, rồi DNS của **địa chỉ vật lý được discovery trả về** không phân giải được. Vì vậy, **chỉ nhìn tên exception chưa đủ để kết luận lỗi nằm ở đâu**.

Bài thuộc chương **Chẩn đoán sự cố** của module Spring Cloud LoadBalancer, tập trung vào cách phát hiện ranh giới sai giữa **service ID → ServiceInstance → địa chỉ HTTP vật lý → DNS/TCP**, cách sửa tích hợp `RestClient`, `WebClient`, OpenFeign và HTTP Interface, cùng bộ thử nghiệm để chứng minh việc sửa thực sự có hiệu lực.

## 1. Phân biệt service ID logic và hostname vật lý

Giả sử `order-service` cần gọi `catalog-service`:

~~~http
GET http://catalog-service/api/products/42
Accept: application/json
~~~

Có hai đường đi hoàn toàn khác nhau.

### Đường đúng khi sử dụng Spring Cloud LoadBalancer

~~~mermaid
flowchart TD
    A["order-service<br/>RestClient có LoadBalancer interceptor"]
    B["serviceId = catalog-service"]
    C["Spring Cloud LoadBalancer"]
    D["ServiceInstanceListSupplier<br/>discovery / cache / filter"]
    E["ServiceInstance<br/>host=10.0.1.12 port=8081"]
    F["HTTP transport"]
    G["DNS nếu host vật lý là hostname<br/>TCP / TLS"]
    H["catalog instance trả response"]
    A --> B --> C
    C <--> D
    C --> E --> F --> G --> H
~~~

Ở đường này:

1. HTTP client được **Spring Cloud LoadBalancer tích hợp**.
2. Nó nhận URL có hostname logic `catalog-service`.
3. LoadBalancer dùng tên đó để lấy danh sách instance, rồi chọn một instance.
4. URI được chuyển sang địa chỉ instance đã chọn, ví dụ `http://10.0.1.12:8081/api/products/42`.
5. HTTP transport thực hiện kết nối; nếu host vật lý là tên DNS, lúc này mới cần phân giải DNS.

### Đường lỗi khi client không được gắn LoadBalancer

~~~mermaid
flowchart TD
    A["order-service<br/>RestClient thường"]
    B["URI = http://catalog-service/api/products/42"]
    C["HTTP transport"]
    D["DNS lookup hostname catalog-service"]
    E{"Có bản ghi DNS?"}
    F["UnknownHostException / DNS failure"]
    G["Kết nối theo DNS<br/>không qua Spring Cloud LB"]
    A --> B --> C --> D --> E
    E -->|"Không"| F
    E -->|"Có"| G
~~~

Ở đường này, không có bước hỏi `ServiceInstanceListSupplier`. HTTP transport chỉ thấy một hostname cần kết nối.

**Kết luận nền tảng:** một chuỗi URL có tên dịch vụ **không tự bật** client-side load balancing. Tích hợp phải nằm ở **bean HTTP client thực sự được dùng**.

## 2. UnknownHostException không phải bằng chứng tuyệt đối rằng thiếu LoadBalancer

Hai lỗi có thể trông giống nhau:

| Tình huống | Bước đã hoàn thành | Host gây lỗi DNS | Nhận định |
|---|---|---|---|
| Client thường gọi `http://catalog-service` | Chưa có bước lựa chọn instance | `catalog-service` | Nghi lỗi tích hợp HTTP client hoặc chủ ý dùng DNS |
| Client LB chọn `catalog-1` có URI `http://catalog-a:8081`, nhưng container không resolve `catalog-a` | LoadBalancer **đã chọn** instance | `catalog-a` | Nghi networking/DNS của đích vật lý |
| Client LB có danh sách rỗng | Không chọn được instance | Có thể **không thực hiện DNS** | Nghi discovery/filter/health/cấu hình service ID |
| Client LB chọn IP `10.0.1.12:8081` nhưng kết nối bị từ chối | Đã chọn instance | Không cần DNS nếu dùng IP | Nghi port/backend/firewall |
| Client thường dùng URL DNS hợp lệ trong Kubernetes | Không có LB tại caller | DNS hợp lệ | Request có thể **thành công**, nhưng không chứng minh Spring Cloud LB hoạt động |

**Không lấy `UnknownHostException` làm điều kiện duy nhất để tự sửa annotation.** Trước hết xác định **hostname nào đã được gửi đến resolver** và **LoadBalancer có thực sự chọn một instance không**.

## 3. Sơ đồ quyết định nhanh khi gặp lỗi

~~~mermaid
flowchart TD
    A["Lỗi khi gọi http://catalog-service"]
    B{"Client có được gắn<br/>Spring Cloud LoadBalancer?"}
    C["Kiểm tra starter, builder bean,<br/>filter/interceptor, URL cố định"]
    D{"Có danh sách instance<br/>cho catalog-service?"}
    E["Kiểm tra service ID, registry,<br/>supplier, cache, health/filter"]
    F{"LoadBalancer đã chọn<br/>instance nào?"}
    G["Thu thập selected URI / host:port"]
    H{"HTTP transport lỗi DNS?"}
    I{"Host gây DNS lỗi là<br/>logic hay physical?"}
    J["Sửa tích hợp client"]
    K["Sửa địa chỉ instance,<br/>Compose network / registry"]
    L["Tiếp tục kiểm tra TCP,<br/>TLS, timeout và response"]
    A --> B
    B -->|"Không / chưa chắc"| C --> J
    B -->|"Có"| D
    D -->|"Không"| E
    D -->|"Có"| F
    F -->|"Có"| G --> H
    F -->|"Không"| E
    H -->|"Có"| I
    I -->|"Logic catalog-service"| J
    I -->|"Đích catalog-a / IP"| K
    H -->|"Không"| L
~~~

Sơ đồ là **runbook**, không phải ánh xạ exception tuyệt đối. Một ứng dụng có thể đặt proxy, DNS cache hoặc nhiều lớp retry khiến exception cuối cùng không giữ đủ thông tin lần thử đầu.

## 4. Ma trận triệu chứng và bước xác minh đầu tiên

| Dấu hiệu | Nguyên nhân có khả năng | Cách xác minh |
|---|---|---|
| `UnknownHostException: catalog-service` với `RestClient.create(...)` | Client thường đưa service ID cho DNS | Kiểm tra cách tạo RestClient, bean đang inject |
| `UnknownHostException: catalog-service` với `WebClient.create(...)` | WebClient không có LoadBalancer filter | Kiểm tra `@LoadBalanced WebClient.Builder` |
| Feign gọi URL vật lý thay vì discovery | `url` được khai báo trong annotation/properties | Kiểm tra URL của named Feign client |
| Feign không khởi động và báo thiếu LoadBalancer client | Thiếu Spring Cloud LoadBalancer dependency trong cấu hình tương ứng | Kiểm tra classpath/starter, Feign configuration |
| “No instances available for catalog-service” | LB chạy nhưng supplier không có ứng viên | Kiểm tra `DiscoveryClient.getInstances("catalog-service")` và filter |
| LB chọn instance nhưng `UnknownHostException: catalog-a` | Địa chỉ vật lý không resolve | Kiểm tra host/port đã quảng bá và mạng container |
| `Connection refused: 10.0.1.12:8081` | Đã có địa chỉ, backend không lắng nghe cổng | Kiểm tra port và readiness, không sửa DNS |
| HTTPS handshake thất bại | Host/port, SNI, chứng chỉ hoặc TLS không phù hợp | Kiểm tra protocol và TLS transport |
| Cùng URI chạy trong container nhưng lỗi trên máy host | DNS name chỉ có trong Compose network | Xác định nơi client thực sự chạy |
| Gọi tên dịch vụ thành công dù không có `@LoadBalanced` | DNS/ClusterIP/mesh có thể xử lý hostname | Phân biệt LB ở caller và LB ở hạ tầng |

Các thông điệp lỗi và exception wrappers có thể thay đổi theo Spring Framework, Reactor Netty, Feign, JVM và HTTP transport.

## 5. Tạo một case tối thiểu: có discovery nhưng HTTP client gọi sai

Giả sử catalog có hai instance vật lý:

~~~text
catalog-service (service ID)
  -> http://127.0.0.1:8081
  -> http://127.0.0.1:8082
~~~

Caller khai báo danh sách instance tĩnh:

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
    loadbalancer:
      cache:
        enabled: false
      retry:
        enabled: false
~~~

**Đây chỉ là nguồn instance**. Nó không tự gắn LoadBalancer vào mọi `RestClient` được tạo trong JVM.

### Mã sai: RestClient thường

~~~java
import org.springframework.web.client.RestClient;

class BrokenCatalogGateway {

    private final RestClient client =
            RestClient.create("http://catalog-service");

    String whoami() {
        return client.get()
                .uri("/whoami")
                .retrieve()
                .body(String.class);
    }
}
~~~

Nếu `catalog-service` không có bản ghi DNS trong môi trường đang chạy, lời gọi có thể phát lỗi hostname không phân giải được **dù danh sách `SimpleDiscoveryClient` hoàn toàn đúng**.

### Mã đúng: RestClient được Spring Cloud tích hợp

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class CatalogClientConfiguration {

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

Và dùng **chính bean RestClient đã cấu hình**:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
class CatalogGateway {

    private final RestClient client;

    CatalogGateway(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    String whoami() {
        return client.get()
                .uri("/whoami")
                .retrieve()
                .body(String.class);
    }
}
~~~

Ở ví dụ này, ứng dụng cần starter tương thích chứa Spring Cloud LoadBalancer và Spring Framework có `RestClient` (từ Framework 6.1).

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

Với Spring Boot 4, tên starter HTTP MVC/phiên bản dependency có thể khác. Luôn dùng **Spring Cloud release train/BOM tương thích** thay vì tự trộn versions.

**Lưu ý:** một bean `RestClient.Builder` có annotation `@LoadBalanced` chỉ có tác dụng khi nó được Spring quản lý và phần Spring Cloud auto-configuration liên quan có mặt. Việc tạo `RestClient.builder()` ở chỗ khác rồi sử dụng builder đó sẽ không tự kế thừa LoadBalancer interceptor.

## 6. Vì sao đặt đúng annotation mà vẫn lỗi?

### 6.1. Inject nhầm Builder

Ví dụ trong cùng ứng dụng có:

~~~java
@Bean("ordinaryBuilder")
RestClient.Builder ordinaryBuilder() {
    return RestClient.builder();
}

@Bean("catalogLoadBalancedBuilder")
@LoadBalanced
RestClient.Builder catalogLoadBalancedBuilder() {
    return RestClient.builder();
}
~~~

Nếu một class dùng `ordinaryBuilder` thay vì `catalogLoadBalancedBuilder`, URL `http://catalog-service` vẫn có thể bị đưa cho DNS.

Dùng `@Qualifier` theo bean name hoặc `@LoadBalanced` ở điểm inject để bảo đảm client dùng đúng builder. Khi có nhiều bean cùng kiểu, nên đặt tên/qualifier rõ và kiểm tra bean thực tế thay vì đoán dựa vào annotation của một method không được gọi.

### 6.2. Dùng builder đúng rồi lại tạo client khác

~~~java
// Đã có bean catalogRestClient trong Spring,
// nhưng đoạn này bỏ qua bean và tự tạo client mới.
RestClient client = RestClient.create("http://catalog-service");
~~~

Đây là một lỗi integration hay gặp trong lớp gateway, test fixture và factory tự viết. Hãy inject singleton RestClient đúng cấu hình hoặc xây client từ builder được inject.

### 6.3. Annotation đặt sai vị trí

Không được giả định:

~~~java
// Không thay thế cho @LoadBalanced RestClient.Builder:
@LoadBalanced
class CatalogGateway {
    // ...
}
~~~

sẽ khiến mọi HTTP call bên trong class tự được load-balanced. `@LoadBalanced` được Spring Cloud xử lý ở các **điểm mở rộng client được hỗ trợ**, chẳng hạn `RestClient.Builder`, `WebClient.Builder` và `RestTemplate` tương ứng.

### 6.4. Dùng client direct để thử URL logic

`RestClient.create("http://catalog-service")` không phải bài thử chứng minh discovery. Để thử Spring Cloud LoadBalancer, phải dùng client đã tích hợp. Để thử DNS hoặc proxy, dùng client direct. **Không tráo hai mục tiêu kiểm thử**.

### 6.5. Auto-configuration bị tắt hoặc thiếu dependency

Kiểm tra:

- Có `spring-cloud-starter-loadbalancer` trong **caller** hay không.
- Có classpath `RestClient`/Spring Web cần thiết hay không.
- Có bean `RestClient.Builder` do Spring quản lý hay không.
- Có override/customizer nào thay hoặc loại LoadBalancer interceptor/filter không.
- Có cấu hình auto-configuration bị exclude hoặc profile chỉ bật một môi trường không.
- Phiên bản Spring Boot/Framework và Spring Cloud có tương thích không.

**Đừng chữa lỗi bằng cách tự thêm DNS record giả cho service ID** trước khi xác định kiến trúc. DNS record có thể làm request tình cờ thành công nhưng che giấu client integration bị bỏ qua.

## 7. Phân biệt bean thường và bean load-balanced trong RestClient

Một ứng dụng có thể cần **cả hai**:

~~~java
@Configuration(proxyBeanMethods = false)
class SplitClientsConfiguration {

    @Bean("paymentDirectRestClient")
    RestClient paymentDirectRestClient() {
        return RestClient.create("https://payments.example.test");
    }

    @Bean("catalogLbBuilder")
    @LoadBalanced
    RestClient.Builder catalogLbBuilder() {
        return RestClient.builder();
    }

    @Bean("catalogLbRestClient")
    RestClient catalogLbRestClient(
            @Qualifier("catalogLbBuilder")
            RestClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

| Bean | Mục đích | Cách hiểu hostname |
|---|---|---|
| `paymentDirectRestClient` | Gọi external/gateway URL đã biết | DNS/proxy theo HTTP transport |
| `catalogLbRestClient` | Gọi nội bộ qua service ID | Spring Cloud LoadBalancer trước transport |
| Một RestClient khác tạo bằng `RestClient.create(...)` | Client direct mới | Không kế thừa interceptors của bean catalog |
| RestClient từ builder `@LoadBalanced` nhưng gọi IP trực tiếp | Có thể coi IP là service ID cần lookup | Không dùng làm direct client nếu muốn bỏ qua LB |

**Không sử dụng một builder load-balanced cho tất cả URL trên toàn ứng dụng.** Với URL vật lý, IP hoặc external host không có service ID trong discovery, điều đó có thể tạo lỗi “no available instance” khó hiểu.

## 8. Xác minh danh sách instance trước khi sửa HTTP client

Nếu đã chắc chắn client là load-balanced nhưng vẫn lỗi, bước tiếp theo là xem `DiscoveryClient` có dữ liệu phù hợp không.

Ví dụ diagnostic bean **chỉ dùng trong môi trường test/local**:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("diagnostic")
class CatalogDiscoveryProbe {

    private final DiscoveryClient discovery;

    CatalogDiscoveryProbe(DiscoveryClient discovery) {
        this.discovery = discovery;
    }

    List<String> candidateUris() {
        return discovery.getInstances("catalog-service").stream()
                .map(ServiceInstance::getUri)
                .map(Object::toString)
                .toList();
    }
}
~~~

Ví dụ kỳ vọng với `SimpleDiscoveryClient`:

~~~text
http://127.0.0.1:8081
http://127.0.0.1:8082
~~~

**Quan trọng:** `DiscoveryClient.getInstances(...)` cho biết danh sách **từ nguồn discovery**, không bảo đảm danh sách cuối sau toàn bộ `ServiceInstanceListSupplier` chain vẫn giống hệt. Zone, hint, health, caching hoặc strict filter có thể loại bớt ứng viên.

Một kết quả rỗng có thể do:

1. Sai service ID hoặc khác chữ hoa/chữ thường/format.
2. Chưa chạy registry/không fetch được registry.
3. Property `SimpleDiscoveryClient` sai đường dẫn hoặc profile không bật.
4. Discovery chưa cập nhật registration hoặc cache đang stale.
5. Supplier lọc hết ứng viên theo zone/hint/region/health.
6. Chính sách strict cố ý fail-closed.

**Không tự fallback bằng cách gọi DNS của một dịch vụ khác nếu policy không cho phép.** Đối với hard constraint, no-instance có thể là hành vi đúng.

## 9. WebClient: kiểm tra ExchangeFilterFunction chứ không chỉ baseUrl

Với `WebClient`, tích hợp Spring Cloud LoadBalancer thường được cấu hình qua **`@LoadBalanced WebClient.Builder`**. Client tạo bằng `WebClient.create(...)` thông thường không tự gắn exchange filter này.

### Cấu hình đúng

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
class CatalogReactiveConfiguration {

    @Bean("catalogLoadBalancedWebClientBuilder")
    @LoadBalanced
    WebClient.Builder catalogLoadBalancedWebClientBuilder() {
        return WebClient.builder();
    }

    @Bean("catalogWebClient")
    WebClient catalogWebClient(
            @Qualifier("catalogLoadBalancedWebClientBuilder")
            WebClient.Builder builder) {
        return builder.baseUrl("http://catalog-service").build();
    }
}
~~~

Ở caller có dependency WebFlux/WebClient và `spring-cloud-starter-loadbalancer` tương thích:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

Ví dụ lời gọi reactive:

~~~java
Mono<String> request = catalogWebClient.get()
        .uri("/whoami")
        .retrieve()
        .bodyToMono(String.class);
~~~

### Lỗi thường gặp ở WebClient

~~~java
// Dù ứng dụng đã có một WebClient.Builder @LoadBalanced,
// client tạo dưới đây hoàn toàn độc lập.
WebClient wrong = WebClient.create("http://catalog-service");
~~~

Nếu `catalog-service` không tồn tại trong DNS, Reactor Netty có thể báo lỗi hostname resolution. Đừng chữa bằng `retryWhen(...)` vô điều kiện, vì resubscribe nhiều lần **không tạo ra LoadBalancer filter bị thiếu**.

### Hai trường hợp cần tách

- **Không có filter LB:** transport xử lý `catalog-service` như hostname DNS.
- **Đã có filter LB:** filter chọn URI vật lý; Reactor Netty tiếp tục DNS/connection tới **host trong URI đó**.

Với một instance có URI `http://catalog-a:8081`, lỗi `UnknownHostException: catalog-a` xảy ra **sau selection**. Phải kiểm tra DNS/network của `catalog-a`, không đổi service ID `catalog-service` chỉ để thử.

## 10. OpenFeign: vì sao client vẫn dùng URL cố định?

OpenFeign theo service ID thường có dạng:

~~~java
import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;

@FeignClient(name = "catalog-service")
interface CatalogFeignClient {

    @GetMapping("/whoami")
    String whoami();
}
~~~

Ứng dụng cần bật client scanning đúng package và có dependencies phù hợp:

~~~java
@SpringBootApplication
@EnableFeignClients(basePackages = "com.example.orders.client")
class OrderApplication {
}
~~~

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-openfeign")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

Khi không cung cấp URL cố định và có integration tương ứng, Spring Cloud OpenFeign có thể dùng `FeignBlockingLoadBalancerClient` để chọn `ServiceInstance`.

### Lỗi 1 — Đặt URL trong annotation

~~~java
@FeignClient(
        name = "catalog-service",
        url = "http://catalog-service:8081")
interface CatalogDirectFeign {

    @GetMapping("/whoami")
    String whoami();
}
~~~

Đây là **URL được chỉ định**, nên nó không còn tương đương Feign chọn instance theo tên service ID. Nếu hostname chỉ tồn tại trong Docker DNS, Feign có thể kết nối thành công qua DNS nhưng **không dùng Spring Cloud LoadBalancer theo service ID** cho client đó.

### Lỗi 2 — URL được cấu hình qua property

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            url: http://catalog-service:8081
~~~

Một URL tường minh trong cấu hình named client có thể làm bỏ qua bước chọn instance theo service ID. Khi chuyển sang discovery-based load balancing, cần kiểm tra **cả annotation lẫn configuration properties**, không chỉ source code của interface.

### Lỗi 3 — Thiếu LoadBalancer starter hoặc override Feign Client

Nếu chỉ thêm OpenFeign mà không có dependency Spring Cloud LoadBalancer tương ứng, Feign có thể báo lỗi lúc khởi tạo rằng **không có load-balancing client**, thay vì âm thầm phân giải DNS. Hành vi và wording phụ thuộc version.

Nếu tự đăng ký bean `feign.Client` hoặc tạo manual `Feign.builder().target(...)`, phải kiểm tra delegate/wrapper có còn đi qua `FeignBlockingLoadBalancerClient` hay không. Một custom transport có thể bỏ qua LB nếu thay thế cấu hình không đúng.

### Bảng kiểm nhanh cho Feign

| Điều kiện | Muốn chọn theo service ID | Muốn gọi URL direct |
|---|---|---|
| `@FeignClient(name=...)` | Có | Có thể có |
| `@FeignClient(url=...)` | **Không đặt** | Có thể đặt |
| URL trong `spring.cloud.openfeign.client.config.*.url` | **Không đặt** | Có thể đặt |
| `spring-cloud-starter-loadbalancer` | Cần theo integration | Không cần cho URL direct |
| HTTP delegate | Có LB wrapper phù hợp | Client HTTP thường |
| `ServiceInstance` list | Phải có ứng viên | Không dùng để chọn đích |

## 11. HTTP Interface: proxy dùng RestClient nào mới là điều quyết định?

Spring HTTP Interface dùng `@HttpExchange`, `@GetExchange` giúp khai báo API dạng interface. Nhưng **bản thân interface không quyết định việc load balancing**. Nó chạy trên adapter của một RestClient/WebClient cụ thể.

Ví dụ:

~~~java
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;

@HttpExchange
interface CatalogHttpApi {

    @GetExchange("/whoami")
    String whoami();
}
~~~

Tạo proxy bằng **RestClient đã được load-balanced**:

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

Nếu thay `client` bằng `RestClient.create("http://catalog-service")`, proxy sẽ đi theo cách DNS của client đó. **Annotation `@HttpExchange` không tự gắn một LoadBalancer interceptor**.

Với adapter `WebClientAdapter` cũng vậy: phải tạo proxy từ WebClient được Spring Cloud tích hợp, không phải từ một WebClient thường.

## 12. DNS có thể hoạt động và che khuất lỗi integration

Trong **Docker Compose**, container cùng network có thể phân giải service name như `catalog-service`. Trong **Kubernetes**, DNS có thể phân giải `catalog-service` thành ClusterIP của một Service.

Vì vậy, mã sau có thể **chạy được** trong môi trường triển khai:

~~~java
RestClient directDns =
        RestClient.create("http://catalog-service:8081");
~~~

Nhưng việc request thành công chỉ chứng minh rằng **DNS/network có đường tới một endpoint**. Nó **không chứng minh** đã đi qua Spring Cloud LoadBalancer.

| Môi trường | `catalog-service` qua DNS | Ý nghĩa khi RestClient thường gọi thành công |
|---|---|---|
| Laptop không có DNS record | Thường không resolve | Có thể thấy `UnknownHostException` |
| Docker Compose cùng network | Có thể resolve service name | Docker DNS/network thực thi tên |
| Kubernetes có Service DNS | Có thể resolve | ClusterIP/CNI/kube-proxy/mesh có thể định tuyến |
| Máy host ngoài Compose network | Không nhất thiết resolve | Không dùng DNS service nội bộ nếu host không ở network |
| Service ID chỉ tồn tại trong Eureka | DNS có thể không biết tên | Cần Spring Cloud LB + Eureka discovery |

Với Compose static list, có thể cấu hình:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://catalog-a:8081
              - uri: http://catalog-b:8081
~~~

Ở đây:

- `catalog-service` là **key logic** cho LoadBalancer.
- `catalog-a` và `catalog-b` là **hostname thật** HTTP client cần resolve qua Compose DNS.
- Nếu `catalog-a` không nằm cùng network hoặc service bị đổi tên, DNS của instance vật lý có thể lỗi dù LoadBalancer đã chọn đúng.

**Không dùng `127.0.0.1` trong container để trỏ sang container khác.** `localhost` bên trong `order-service` là chính container `order-service`, không phải `catalog-service`.

## 13. LoadBalancer đã chọn rồi nhưng DNS/transport vẫn lỗi

Một ca thứ hai:

~~~text
serviceId = catalog-service
instanceId = catalog-a
ServiceInstance.uri = http://catalog-a:8081
selected = catalog-a
HTTP transport -> UnknownHostException(catalog-a)
~~~

Runbook lúc này khác hẳn ca thiếu LB:

1. Lấy đúng URI mà discovery/LoadBalancer chọn từ log/tracing có kiểm soát hoặc endpoint diagnostic chỉ dành cho test.
2. Kiểm tra hostname vật lý có tồn tại trong **network namespace của caller** không.
3. Với Compose, xác nhận các container ở cùng network, service name đúng và backend đang chạy.
4. Với Kubernetes, xác nhận DNS name/namespace, Service/EndpointSlice và quyền truy cập mạng phù hợp.
5. Với Eureka, kiểm tra instance quảng bá hostname/IP/port **thực sự truy cập được** từ caller; tránh `localhost` hoặc địa chỉ host-only.
6. Kiểm tra reverse proxy, DNS caching, TTL và HTTP connection reuse nếu địa chỉ thay đổi sau restart.
7. Nếu DNS thành công nhưng vẫn lỗi, chuyển sang kiểm tra TCP/TLS/port/timeout.

### Registry ghi sai endpoint

Ví dụ Eureka client trong container quảng bá:

~~~text
host = localhost
port = 8081
~~~

Caller ở container khác nhận instance này. LoadBalancer chọn nó hoàn toàn hợp lệ theo dữ liệu registry, nhưng khi HTTP client kết nối `localhost:8081`, nó gọi **chính caller**, không phải backend.

Không thể giải quyết bằng cách thêm `@LoadBalanced` ở một bean đã load-balanced; phải sửa **địa chỉ được registry quảng bá** hoặc topology network.

### Một instance được chọn không đồng nghĩa nó khỏe

Discovery cache có thể còn instance đã dừng. Lỗi sau khi chọn instance có thể là `Connection refused`, connection timeout hoặc response timeout. Đây là vấn đề membership/health/transport, không phải lỗi service name bị phân giải nhầm thành DNS.

## 14. Khác nhau giữa “không có instance” và “không resolve được hostname”

Hai loại lỗi thường bị gộp thành “service not found”:

**Trường hợp A — Discovery không có ứng viên**

~~~text
RestClient có LoadBalancer
  -> serviceId=catalog-service
  -> ServiceInstanceListSupplier trả []
  -> LoadBalancer không chọn được server
  -> lỗi no-instance / HTTP error mapping tương ứng
  -> thường chưa có request HTTP tới backend
~~~

**Trường hợp B — Client không có LoadBalancer**

~~~text
RestClient thường
  -> URI http://catalog-service/whoami
  -> HTTP transport phân giải hostname catalog-service
  -> UnknownHostException nếu không có bản ghi DNS
~~~

**Trường hợp C — Đích vật lý sai**

~~~text
RestClient có LoadBalancer
  -> catalog-service -> chọn catalog-a:8081
  -> HTTP transport phân giải catalog-a
  -> UnknownHostException nếu catalog-a không resolve
~~~

| Tình huống | Khâu cần sửa | Việc tăng read timeout có giúp? |
|---|---|---|
| A | Discovery/filter/service ID/health/cache | Không giải quyết thiếu ứng viên |
| B | Builder/filter/Feign URL/client integration | Không tạo ra interceptor bị thiếu |
| C | URI vật lý, registry, network/DNS | Không sửa host sai; có thể chỉ làm chờ lâu hơn |

**Cảnh báo:** các library có thể bọc nguyên nhân gốc trong `RestClientException`, `WebClientRequestException`, `FeignException` hoặc các exception khác. Hãy xem **cause chain** và ngữ cảnh selection; không dựa duy nhất tên exception bề mặt.

## 15. Kiểm tra request URL và cấu hình scheme/port

### 15.1. URL logic cần có scheme phù hợp

Ví dụ:

~~~java
RestClient client = lbBuilder
        .baseUrl("http://catalog-service")
        .build();
~~~

Phần host là service ID. Không sao chép URI scheme `lb://catalog-service` của một số hệ sinh thái gateway sang RestClient thông thường nếu integration đang dùng HTTP URI với `@LoadBalanced`.

### 15.2. Không dùng port của service ID làm cách chọn replica

~~~java
// Dễ gây hiểu nhầm khi cố dùng port 8081 để chọn replica:
RestClient client = lbBuilder
        .baseUrl("http://catalog-service:8081")
        .build();
~~~

LoadBalancer chọn instance từ danh sách theo service ID, và URI vật lý của instance có thể có port riêng. Nếu muốn gọi **một endpoint cố định** để debug, dùng RestClient direct. Nếu muốn chọn instance theo LoadBalancer, đừng dùng port logic làm tín hiệu định tuyến không được thiết kế.

### 15.3. HTTPS là quyết định riêng

Nếu selected URI dùng HTTPS, HTTP transport phải có TLS/cert trust/SNI thích hợp. Lỗi handshake hoặc certificate không hợp lệ không chứng minh rằng service ID đã bị DNS giải quyết sai.

Trong môi trường service mesh, một tên HTTP logic có thể đi qua sidecar; xác định kiến trúc để tránh hiểu nhầm tầng chọn đích và tầng mã hóa kết nối.

## 16. Chẩn đoán với log/tracing mà không lộ dữ liệu nhạy cảm

Để phân biệt hai lỗi, hữu ích nhất là một sự kiện quan sát có kiểm soát:

~~~text
operation=catalog.whoami
serviceId=catalog-service
loadBalancerApplied=true
candidateCount=2
selectedInstance=catalog-a
selectedEndpointCategory=compose-network
httpStatus=none
errorCategory=DNS_RESOLUTION
dnsHostCategory=PHYSICAL_INSTANCE
traceId=lab-123
~~~

Đây là **định dạng minh họa**, không phải tập metric/log được Spring Cloud tự phát sinh mặc định.

Chỉ đưa vào log các trường được **allowlist**:

- `serviceId` do code cấu hình.
- `operation` hoặc route template cố định.
- Số candidate trước/sau filter, nếu có thể instrument.
- Kết quả chọn instance/nhóm instance được phép ghi.
- Error category như `NO_INSTANCE`, `DNS_RESOLUTION`, `CONNECT_FAILURE`, `TIMEOUT`.
- Latency và trace ID an toàn.
- Có thể phân loại DNS host gây lỗi là `LOGICAL_SERVICE_NAME` hay `PHYSICAL_INSTANCE`.

**Không log nguyên URL chứa query token, `Authorization`, `Cookie`, response body hoặc toàn bộ exception message/stacktrace một cách vô điều kiện**. Exception message có thể mang URL và thông tin riêng tư; khi cần phân tích sâu, dùng kênh điều tra có quyền truy cập phù hợp.

### Không nhầm DEBUG HTTP với bằng chứng an toàn

Có thể dùng DEBUG của Spring Cloud LoadBalancer trong **lab với dữ liệu giả** để hiểu selection. Nhưng bật Feign `FULL`, Reactor Netty wiretap hoặc HTTP wire logs có thể ghi headers/body nhạy cảm. Trong production, ưu tiên metrics/tracing có kiểm soát hoặc event log riêng tại client boundary.

## 17. Bài lab: cố ý gọi sai rồi sửa RestClient

### Chuẩn bị

Chạy backend `catalog-service` đơn giản trả instance ID. Ví dụ:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CatalogWhoamiController {

    private final String instanceId;

    CatalogWhoamiController(
            @Value("${demo.instance-id:catalog-a}")
            String instanceId) {
        this.instanceId = instanceId;
    }

    @GetMapping("/whoami")
    String whoami() {
        return instanceId;
    }
}
~~~

Chạy hai instance của cùng ứng dụng, ví dụ port 8081/8082, với `demo.instance-id=catalog-a` và `catalog-b` tương ứng. Caller dùng `SimpleDiscoveryClient` như mục 5.

### Lần 1 — Dùng client thường

~~~java
RestClient wrong =
        RestClient.create("http://catalog-service");

String value = wrong.get()
        .uri("/whoami")
        .retrieve()
        .body(String.class);
~~~

Nếu hostname `catalog-service` không tồn tại trong DNS của caller, dự kiến sẽ xuất hiện lỗi resolver. Đây là **một kết quả có điều kiện theo môi trường**, không phải assertion luôn đúng: trong Compose/Kubernetes có thể đã có DNS record.

### Lần 2 — Dùng client load-balanced

Inject `catalogRestClient` từ mục 5. Gọi `/whoami` 10–12 lần và ghi tập instance IDs nhận được:

~~~java
Set<String> observed = new HashSet<>();

for (int i = 0; i < 12; i++) {
    String id = catalogRestClient.get()
            .uri("/whoami")
            .retrieve()
            .body(String.class);

    observed.add(id);
}

// Với hai instance khỏe và round-robin mặc định,
// kỳ vọng observed chứa cả catalog-a và catalog-b.
~~~

Nếu kết quả chứa cả hai, đó là bằng chứng thực tế của **đường đi service ID → danh sách instance → HTTP** trong lab, với điều kiện không có hạ tầng DNS/proxy nào làm giả lập kết quả.

### Lần 3 — Giữ LB nhưng phá hostname vật lý

Trong danh sách static, thay URI của một instance bằng `http://nonexistent-catalog-host.invalid:8081`. Đây là hostname giả trong vùng `.invalid` dành cho thử nghiệm, không phải endpoint thực.

Kiểm tra:

- LoadBalancer vẫn có thể thấy và chọn instance đó.
- HTTP transport không resolve được hostname vật lý.
- Đây là lỗi **sau selection**, không phải bằng chứng thiếu `@LoadBalanced`.
- Request tới instance còn tốt có thể thành công, tùy policy/retry.

Không cấu hình proxy/wildcard DNS trong lab nếu muốn quan sát trực tiếp lỗi resolver; nếu môi trường intercepts mọi request, kết quả có thể khác.

## 18. Integration test: chứng minh không còn phụ thuộc DNS của service ID

Một integration test đáng tin cậy hơn việc kiểm tra exception message phải:

1. Khởi chạy **HTTP server giả** trên cổng động.
2. Đăng ký server đó vào `SimpleDiscoveryClient` bằng `@DynamicPropertySource`.
3. Tạo **Spring context thật** với `@LoadBalanced RestClient.Builder`.
4. Gọi URL `http://catalog-service` qua bean đã inject.
5. Assert response có ID do backend giả trả về.
6. Không cần tạo bản ghi DNS cho `catalog-service`.

Ví dụ JUnit Jupiter + Spring Boot test:

~~~java
import java.io.IOException;
import java.io.OutputStream;
import java.io.UncheckedIOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.client.RestClient;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(
        classes = ServiceIdRestClientIT.TestApp.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
            "spring.cloud.loadbalancer.cache.enabled=false",
            "spring.cloud.loadbalancer.retry.enabled=false"
        })
class ServiceIdRestClientIT {

    private static final HttpServer CATALOG =
            startServer("catalog-a");

    @DynamicPropertySource
    static void register(DynamicPropertyRegistry properties) {
        properties.add(
                "spring.cloud.discovery.client.simple.instances.catalog-service[0].uri",
                () -> "http://127.0.0.1:"
                        + CATALOG.getAddress().getPort());
    }

    @Autowired
    @Qualifier("catalogRestClient")
    RestClient client;

    @Test
    void resolvesServiceIdViaLoadBalancer() {
        String response = client.get()
                .uri("/whoami")
                .retrieve()
                .body(String.class);

        assertEquals("catalog-a", response);
    }

    @AfterAll
    static void stopServer() {
        CATALOG.stop(0);
    }

    private static HttpServer startServer(String id) {
        try {
            HttpServer server = HttpServer.create(
                    new InetSocketAddress("127.0.0.1", 0), 0);

            server.createContext("/whoami", exchange -> {
                byte[] bytes = id.getBytes(StandardCharsets.UTF_8);

                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, bytes.length);

                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            });

            server.start();
            return server;
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {

        @Bean("catalogLbBuilder")
        @LoadBalanced
        RestClient.Builder catalogLbBuilder() {
            return RestClient.builder();
        }

        @Bean("catalogRestClient")
        RestClient catalogRestClient(
                @Qualifier("catalogLbBuilder")
                RestClient.Builder builder) {
            return builder
                    .baseUrl("http://catalog-service")
                    .build();
        }
    }
}
~~~

Test giả định có `spring-boot-starter-test`, Spring Cloud LoadBalancer và Spring Framework `RestClient` tương thích. JDK runtime phải có module `jdk.httpserver`; trong một số JPMS/runtime image tối giản cần bổ sung module hoặc thay bằng WireMock/MockWebServer.

**Kết quả có ý nghĩa:** caller được Spring cấu hình có thể gọi `catalog-service` thông qua instance URI đã đăng ký dù URL logic **không phải hostname mà test phải đưa vào DNS**. Đây là integration test của **client wiring**; không phải benchmark performance hay kiểm chứng mọi policy.

Một test bổ sung nên tạo **hai fake servers** và assert `Set.of("catalog-a","catalog-b")` sau nhiều lần gọi để kiểm tra multi-instance selection. Không assert request đầu tiên luôn chọn A hoặc round-robin chia đúng 6/6 khi chưa kiểm soát state.

### Test negative không nên phụ thuộc DNS của môi trường CI

Không nên viết assertion tuyệt đối rằng:

~~~java
RestClient.create("http://catalog-service")
        .get().uri("/whoami").retrieve().body(String.class);
// MUST throw UnknownHostException
~~~

Bởi ở CI Docker/Kubernetes, `catalog-service` có thể tình cờ được DNS giải quyết. Test positive đi qua LoadBalancer và tới **fake HTTP server xác định** ổn định hơn.

## 19. Checklist chẩn đoán theo thứ tự ưu tiên

Khi sự cố đang diễn ra, kiểm tra từ phần ít phá vỡ nhất:

| Bước | Câu hỏi | Bằng chứng cần lấy | Hành động |
|---|---|---|---|
| 1 | Client nào thực thi? | Bean name, loại client, constructor/config | Xác nhận RestClient/WebClient/Feign/HTTP Interface thực tế |
| 2 | URL logic có được cấu hình đúng? | `baseUrl`/Feign name, URL properties | Phân biệt service ID với URL vật lý |
| 3 | Client có tích hợp LB? | `@LoadBalanced` bean, filter/interceptor, Feign wrapper | Sửa wiring, starter, inject đúng bean |
| 4 | Có danh sách instance? | `DiscoveryClient`, supplier/filter output | Sửa service ID, registry, metadata/filter |
| 5 | LB chọn instance nào? | Selected instance/URI qua instrumentation | Tách logical DNS khỏi physical DNS |
| 6 | HTTP transport tới đúng host:port? | DNS/network trong caller, instance URI | Sửa address, network, port, registry |
| 7 | Request đã tới backend? | Trace/correlation và backend log an toàn | Tách connect lỗi với server/response lỗi |
| 8 | Retry/cache có làm sai chẩn đoán? | Attempt count, cache TTL, refresh | Test một attempt để tìm nguyên nhân gốc |
| 9 | Kết quả có bền qua scale/restart? | Integration test nhiều instance, outage test | Bổ sung regression tests và metrics |

**Không tắt toàn bộ cơ chế bảo mật, TLS hoặc bật DEBUG logging chứa token để chữa sự cố DNS.** Việc lấy bằng chứng phải được giới hạn ở môi trường, quyền truy cập và dữ liệu được phép.

## 20. Tình huống nâng cao dễ nhầm

### 20.1. Nhiều Spring contexts

`@LoadBalancerClient(name=..., configuration=...)` có thể tạo cấu hình riêng theo service ID trong **child context** của Spring Cloud LoadBalancer. Nếu configuration class bị component scan chính đưa nhầm vào parent context, các bean hoặc supplier không được áp dụng đúng phạm vi dự kiến.

Tuy nhiên, nếu client đang dùng DNS trực tiếp vì chưa có `@LoadBalanced`, **chỉnh thuật toán supplier không giải quyết nguyên nhân đầu tiên**.

### 20.2. Cache đã cũ

`CachingServiceInstanceListSupplier` có thể giữ danh sách cũ. Eureka/Consul cũng có cơ chế đồng bộ/caching riêng. Lỗi selected instance hostname không resolve sau khi scale-down có thể do registry/caches còn URI cũ. Tắt LB cache trong test **không làm mọi discovery cache khác biến mất**.

### 20.3. Proxy HTTP

Một HTTP proxy có thể nhận absolute URI và tự resolve host. Khi đó `UnknownHost` có thể xuất phát từ proxy hoặc môi trường transport, thay vì DNS resolver ngay trong caller. Cần xác nhận proxy settings và request route thực tế trước khi kết luận phần nào phân giải tên.

### 20.4. Circuit breaker và retry

Circuit breaker, timeout, retry và fallback có thể che lỗi ban đầu bằng một exception hoặc response khác. Trong lab chẩn đoán, tạm kiểm soát/tắt các tầng retry không cần thiết để có một attempt dễ đọc; production không nên thay chính sách resilience mà không đánh giá rủi ro.

### 20.5. Lỗi tồn tại riêng ở test

Mock `RestClient`/`WebClient` hoặc `MockRestServiceServer` có thể bypass HTTP transport thật, khiến test unit pass dù không có LoadBalancer interceptor. Phải có **integration test với Spring ApplicationContext + HTTP server thật** để chứng minh đường đi service ID.

### 20.6. Không nhầm discovery của Kubernetes với DNS Service

Nếu dùng Spring Cloud Kubernetes DiscoveryClient, cách ánh xạ service/endpoint phụ thuộc cấu hình và quyền truy cập Kubernetes API. Nếu dùng **RestClient thường tới Kubernetes Service DNS**, đó là lựa chọn tầng network, không phải Spring Cloud LoadBalancer chọn `ServiceInstance` ở caller. Cả hai kiến trúc đều có thể hợp lệ, nhưng phải chọn và đo đúng.

## 21. Ma trận kiểm thử hồi quy sau khi sửa

| Case | Cấu hình | Kết quả mong đợi |
|---|---|---|
| RestClient thường + service ID không có DNS | Không `@LoadBalanced` | Có thể lỗi DNS; kết quả tùy môi trường |
| RestClient đúng bean LB + static instances | `@LoadBalanced RestClient.Builder` | Gọi instance HTTP đã đăng ký |
| RestClient dùng nhầm bean direct | Inject ordinary builder | Không dùng Spring Cloud LB theo ý muốn |
| LB có danh sách rỗng | Supplier trả `[]` | Không có instance được chọn, xử lý lỗi no-server |
| LB chọn instance URI có host sai | URI `catalog-a` không resolve | DNS physical host lỗi sau selection |
| WebClient thường + service ID | `WebClient.create(...)` | Có thể DNS lookup hostname logic |
| WebClient LB + static instances | `@LoadBalanced WebClient.Builder` | Request tới URI vật lý được chọn |
| Feign name, không có URL | Có Feign + LB integration | Chọn theo service ID |
| Feign có URL | `@FeignClient(url=...)` hoặc property URL | Gọi direct URL, không chọn theo name |
| HTTP Interface với RestClient LB | Proxy tạo từ RestClient đúng | Gọi qua client-side LB |
| HTTP Interface với RestClient direct | Proxy tạo từ client thường | Theo DNS/direct của client |
| Docker Compose khác network | Instance URI `http://catalog-a:8081` | DNS/network physical host thất bại |
| Kubernetes Service DNS + RestClient thường | DNS/ClusterIP hợp lệ | Request có thể thành công **không qua Spring Cloud LB** |
| Scale-down và registry/cache stale | URI đã cũ | Có thể còn lỗi trước khi refresh |

Khi test, đừng chỉ assert HTTP 200: backend có thể trả 200 qua DNS/service mesh dù LoadBalancer chưa được gắn. Nếu muốn xác minh client-side selection, hãy quan sát **candidate list và selected instance** hoặc dùng fake servers có ID riêng và nguồn discovery được kiểm soát.

## 22. Anti-pattern và bài học vận hành

**1. Thêm dòng `127.0.0.1 catalog-service` vào hosts file để “sửa” lỗi.** Điều này có thể làm demo qua DNS chạy nhưng không gắn LoadBalancer và không hoạt động trong mạng container hay cụm.

**2. Bọc mọi exception bằng retry.** Một client thiếu LB sẽ không tự có interceptor sau 10 lần retry; retry còn tăng độ trễ và tải.

**3. Đổi tên service ID theo lỗi DNS mà không xem discovery.** Điều này có thể làm lệch contract giữa caller/registry và che cấu hình bean sai.

**4. Chỉ thử bằng curl tới `http://catalog-service`.** Curl kiểm tra DNS/network của môi trường chạy curl; không kiểm chứng Spring Cloud LoadBalancer của ứng dụng.

**5. Coi Feign có `@FeignClient(name=...)` là chắc chắn đã dùng LB.** URL trong annotation/properties hoặc HTTP client custom vẫn có thể bỏ qua bước lựa chọn theo service ID.

**6. Dùng `@LoadBalanced` builder cho mọi external URL/IP.** LoadBalancer có thể cố tìm instance cho hostname vật lý không phải service ID.

**7. Bật DEBUG wiretap/FULL logging ở production để in toàn bộ request.** Có nguy cơ lộ `Authorization`, `Cookie`, signed URLs, body và metadata nhạy cảm. Ưu tiên sự kiện quan sát an toàn.

**8. Dựa vào một test mock để chứng minh HTTP integration.** Mock có thể trả dữ liệu đúng dù client được tạo không đúng builder.

**9. Không phân biệt logical DNS và physical DNS.** Đây là nguyên nhân làm đội phát triển mất thời gian sửa discovery trong khi lỗi thật là Docker networking, hoặc ngược lại.

**10. Dùng kết quả một môi trường để kết luận cho mọi môi trường.** Laptop, Docker Compose, Kubernetes, service mesh, VPN và HTTP proxy có hành vi DNS/network khác nhau.

## 23. Checklist trước khi kết luận đã khắc phục

- Đã xác định **RestClient/WebClient/Feign/HTTP Interface bean nào** thực sự được dùng?
- Client có được tạo từ **`@LoadBalanced` builder/adapter** khi mục tiêu là chọn service ID?
- Có `spring-cloud-starter-loadbalancer`, phiên bản Spring phù hợp và auto-configuration không bị vô hiệu hóa?
- Với Feign, đã kiểm tra `url` trong annotation **và** properties?
- Đã phân biệt `UnknownHostException` của **hostname logic** với lỗi DNS của **instance host** sau khi chọn?
- Có thể xem `DiscoveryClient.getInstances(serviceId)` và kết quả supplier/filter mà không lộ metadata nhạy cảm?
- Service ID có đúng chính tả/case và source discovery có dữ liệu?
- URI vật lý được quảng bá có host/port/network mà caller truy cập được?
- Trong Docker/Kubernetes, đã kiểm tra network namespace và không dùng nhầm localhost?
- HTTP/HTTPS, proxy, TLS, connect/read timeout có được kiểm tra riêng sau selection?
- Retry/circuit breaker/cache đã được kiểm soát khi tái hiện lỗi?
- Có một **integration test Spring context thật** chứng minh request qua service ID tới fake HTTP server không phụ thuộc DNS logic?
- Sau sửa, có regression tests cho RestClient, WebClient, Feign hoặc HTTP Interface đúng với những client thực tế của hệ thống?
- Logging/tracing có cung cấp đủ sự kiện chọn instance mà **không ghi token/cookie/raw URL**?

**Kết luận:** Khi tên dịch vụ bị phân giải như DNS, đừng mặc định đổ lỗi cho registry. Trước hết kiểm tra **đường tích hợp HTTP client**: `RestClient` và `WebClient` phải được tạo từ builder có `@LoadBalanced`; OpenFeign không được bị URL cố định hoặc custom client làm bỏ qua LoadBalancer; HTTP Interface phải dùng adapter của client đã tích hợp. Sau đó mới kiểm tra **danh sách `ServiceInstance`** và **địa chỉ vật lý được chọn**. Khả năng phân biệt **DNS của tên dịch vụ logic** với **DNS của instance vật lý** là chìa khóa chẩn đoán đúng vấn đề và tránh sửa nhầm tầng.

**Tài liệu tham khảo chính thức:**

- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)
- [Spring Cloud Commons – RestClient và WebClient được load-balanced](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Framework – REST Clients và HTTP Interfaces](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html)
- [Spring Cloud OpenFeign – Declarative HTTP Client](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
- [Docker Docs – Compose Networking](https://docs.docker.com/compose/how-tos/networking/)

