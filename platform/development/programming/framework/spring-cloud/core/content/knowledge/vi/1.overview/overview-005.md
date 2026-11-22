# Vai trò Spring Cloud Commons đối với các thành phần dùng chung

## 1. Vì sao hệ thống phân tán cần một lớp trừu tượng chung?

Trong ứng dụng Spring Boot đơn lẻ, một thành phần có thể gọi thành phần khác bằng đối tượng Java hoặc URL đã biết. Khi hệ thống được tách thành nhiều dịch vụ, địa chỉ của từng instance thay đổi do triển khai, tự mở rộng, khởi động lại hoặc lỗi hạ tầng. Các dịch vụ còn có thể sử dụng những giải pháp đăng ký và khám phá khác nhau.

Nếu mã nghiệp vụ gọi trực tiếp API của Eureka, Consul hoặc một bộ cân bằng tải cụ thể, việc đổi hạ tầng sẽ kéo theo thay đổi ở nhiều lớp ứng dụng. **Spring Cloud Commons** cung cấp các *hợp đồng lập trình dùng chung* để phần lớn mã ứng dụng làm việc với khái niệm `service ID`, `ServiceInstance`, khám phá dịch vụ, đăng ký dịch vụ và cân bằng tải thay vì phụ thuộc ngay vào một nhà cung cấp.

Trong module **SPRING_CLOUD_CORE**, Commons là nền móng cho các chức năng phối hợp dịch vụ. Nó làm việc cùng Spring Cloud Context, cơ chế cấu hình bên ngoài của Spring Boot và hệ sinh thái Spring Cloud; mỗi phần có trách nhiệm riêng.

> Ý tưởng cốt lõi: **Commons chuẩn hóa cách các thành phần phối hợp; các thư viện và hạ tầng cụ thể đảm nhiệm cách triển khai.** Một interface chung không tự tạo ra registry, kết nối mạng hay khả năng chịu lỗi.

## 2. Commons nằm ở đâu trong kiến trúc Spring Cloud?

| Thành phần | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| **Spring Boot** | Khởi tạo ứng dụng, cấu hình tự động, externalized configuration, Actuator | `application.yml`, `@ConfigurationProperties`, health endpoint |
| **Spring Cloud Commons** | Hợp đồng chung cho discovery, service instance, service registration, load balancing và các điểm tích hợp | `DiscoveryClient`, `ServiceInstance`, `ServiceRegistry`, `@LoadBalanced` |
| **Spring Cloud Context** | Tích hợp vòng đời `ApplicationContext`, nguồn cấu hình và cơ chế làm mới bean theo phạm vi | `@RefreshScope`, xử lý refresh |
| **Triển khai cụ thể** | Kết nối tới registry, lựa chọn instance, trao đổi HTTP, quản lý cấu hình tập trung | Eureka/Consul/Kubernetes integration, Spring Cloud LoadBalancer, Spring Cloud Config, `WebClient` |

Có thể hình dung quan hệ phụ thuộc:

~~~mermaid
flowchart TB
    A["Mã nghiệp vụ: order-service"] --> B["API chung của Spring Cloud Commons"]
    B --> C["DiscoveryClient / ServiceInstance"]
    B --> D["LoadBalancerClient / @LoadBalanced"]
    B --> E["ServiceRegistry / Registration"]
    C --> F["Adapter: Eureka, Consul, Kubernetes hoặc danh sách tĩnh"]
    D --> G["Spring Cloud LoadBalancer"]
    E --> F
    H["Spring Cloud Context: refresh và vòng đời cấu hình"] -. "Bổ trợ" .-> A
    I["Spring Boot: cấu hình ngoài và auto-configuration"] -. "Nền tảng" .-> A
~~~

Sơ đồ nhấn mạnh ranh giới trách nhiệm. Một ứng dụng có thể dùng interface `DiscoveryClient` của Commons, nhưng hành vi truy vấn registry và cập nhật danh sách instance phụ thuộc adapter đã cài. Tương tự, API chung liên quan cân bằng tải chỉ hoạt động khi có implementation phù hợp trên classpath.

## 3. Các hợp đồng dùng chung quan trọng

### 3.1. `ServiceInstance`: cách biểu diễn một instance

`org.springframework.cloud.client.ServiceInstance` là mô hình chung mô tả một instance dịch vụ. Nó cung cấp những thông tin thường gặp như:

- `getServiceId()`: tên logic của dịch vụ, chẳng hạn `catalog-service`.
- `getHost()`, `getPort()`, `isSecure()`, `getUri()`: thông tin kết nối.
- `getMetadata()`: thuộc tính bổ sung do implementation hoặc registry cung cấp.

Ví dụ, cùng một `serviceId` có thể trỏ đến hai instance:

| Service ID | Instance | URI |
| --- | --- | --- |
| `catalog-service` | `catalog-1` | `http://localhost:8081` |
| `catalog-service` | `catalog-2` | `http://localhost:8082` |

Mã ứng dụng có thể duyệt các `ServiceInstance` mà không cần biết địa chỉ được lấy từ registry nào. Metadata có thể chứa zone, phiên bản hoặc nhãn triển khai, nhưng ý nghĩa, độ tin cậy và khả năng cập nhật của metadata tùy thuộc giải pháp cụ thể.

### 3.2. `DiscoveryClient`: tìm instance theo tên logic

`org.springframework.cloud.client.discovery.DiscoveryClient` cung cấp phương thức đồng bộ như `getInstances(String serviceId)` và `getServices()`. Biến thể `ReactiveDiscoveryClient` cung cấp cách truy xuất phù hợp ứng dụng reactive.

Ví dụ một lớp chỉ đọc các endpoint đang được discovery công bố:

~~~java
import java.net.URI;
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class CatalogLocator {
    private final DiscoveryClient discoveryClient;

    public CatalogLocator(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<URI> endpoints() {
        return discoveryClient.getInstances("catalog-service")
                .stream()
                .map(ServiceInstance::getUri)
                .toList();
    }
}
~~~

Trong thực tế, `DiscoveryClient` có thể được cung cấp bởi thư viện tương thích Eureka, Consul, Kubernetes hoặc `SimpleDiscoveryClient` đọc danh sách instance cấu hình sẵn. `CompositeDiscoveryClient` có thể kết hợp nhiều nguồn khi ứng dụng có nhiều discovery client.

Đoạn mã trên dùng để quan sát danh sách instance; **nó chưa thực hiện cân bằng tải**. Nếu danh sách rỗng, phía gọi phải có phương án xử lý như phản hồi phù hợp, retry có giới hạn hoặc fallback theo yêu cầu nghiệp vụ.

### 3.3. `ServiceRegistry` và `Registration`: phía đăng ký dịch vụ

Khám phá và đăng ký là hai việc khác nhau:

- `DiscoveryClient` trả lời: “Hiện có thể tìm những instance nào của dịch vụ này?”
- `ServiceRegistry<R extends Registration>` biểu diễn thao tác đăng ký, hủy đăng ký và truy vấn/thay đổi trạng thái đăng ký theo khả năng implementation.
- `Registration` là thông tin một instance dùng khi đăng ký, đồng thời kế thừa `ServiceInstance`.

Một adapter registry có thể cung cấp cơ chế tự đăng ký khi ứng dụng khởi động và hủy đăng ký khi dừng. Chi tiết về heartbeat, lease, readiness và thời điểm instance bị loại khỏi registry **không đồng nhất** giữa các nhà cung cấp. Commons đưa ra ngôn ngữ chung để tích hợp, chứ không thay registry server.

### 3.4. Tích hợp cân bằng tải: chọn instance để gọi

`LoadBalancerClient` là abstraction đồng bộ thuộc Commons cho thao tác chọn instance và thực thi theo một instance đã chọn. Trong các ứng dụng Spring Cloud hiện đại, **Spring Cloud LoadBalancer** cung cấp implementation và tích hợp với các HTTP client thích hợp. Với luồng reactive, các thành phần như `ReactorServiceInstanceLoadBalancer` và `ServiceInstanceListSupplier` có thể tham gia quá trình chọn và cung cấp danh sách instance.

Luồng thông thường:

1. Mã nghiệp vụ yêu cầu `http://catalog-service/...`; `catalog-service` là **tên logic**, không phải hostname bắt buộc phải tra DNS.
2. Bộ tích hợp load balancer yêu cầu danh sách `ServiceInstance` từ nguồn thích hợp, thường dựa vào discovery.
3. Thuật toán chọn một instance có thể dùng, rồi gửi HTTP tới host/port thực tế của nó.
4. Timeout, retry, circuit breaker, idempotency và xử lý HTTP lỗi vẫn cần được cấu hình ở các lớp tương ứng.

Không nên coi discovery và load balancing là một: discovery **biết những instance nào tồn tại**, còn load balancing **quyết định sử dụng instance nào**.

## 4. Ví dụ: `order-service` gọi `catalog-service`

Giả sử có một `order-service` và hai instance `catalog-service` ở cổng `8081`, `8082`. Ví dụ minh họa dùng cấu hình tĩnh để tập trung vào Commons, không cần dựng registry thật.

### Bước 1. Chọn dependency

Với Maven, ứng dụng gọi dịch vụ cần WebClient và bộ cân bằng tải:

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

Trong dự án thật, hãy quản lý dependency Spring Cloud bằng **Spring Cloud BOM/release train tương thích với phiên bản Spring Boot** đang dùng. Không tự chọn mỗi thư viện Spring Cloud một phiên bản rời rạc. Khi thay `SimpleDiscoveryClient` bằng registry thật, bổ sung starter/adapter discovery tương ứng.

### Bước 2. Khai báo instance tĩnh để phát triển hoặc kiểm thử

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:8081
              - uri: http://localhost:8082
~~~

`SimpleDiscoveryClient` dùng các địa chỉ trong cấu hình. Điều này hữu ích ở môi trường local/test; **không tự cập nhật khi instance tăng giảm** như một registry động. Cả hai địa chỉ phải có ứng dụng đích thực sự chạy thì ví dụ gửi HTTP mới thành công.

### Bước 3. Tạo `WebClient.Builder` có load balancing

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class ClientConfiguration {
    @Bean
    @LoadBalanced
    WebClient.Builder loadBalancedWebClientBuilder() {
        return WebClient.builder();
    }
}
~~~

Annotation `@LoadBalanced` đánh dấu builder để Spring Cloud gắn cơ chế phân giải service ID và chọn instance. `WebClient` thực hiện HTTP; Commons cùng Spring Cloud LoadBalancer cung cấp các điểm tích hợp cho việc tìm và chọn địa chỉ. Không nên gán nhãn `@LoadBalanced` lên mọi HTTP client nếu có những cuộc gọi phải đi đến URL cố định bên ngoài.

### Bước 4. Gọi theo service ID, không gắn địa chỉ instance vào nghiệp vụ

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class CatalogGateway {
    private final WebClient client;

    public CatalogGateway(@LoadBalanced WebClient.Builder builder) {
        this.client = builder.build();
    }

    public Mono<String> getProduct(String productId) {
        return client.get()
                .uri("http://catalog-service/api/products/{id}", productId)
                .retrieve()
                .bodyToMono(String.class);
    }
}
~~~

Giả sử cả hai instance đều cung cấp `GET /api/products/{id}`, Spring Cloud LoadBalancer có thể phân phối các lần gọi giữa chúng theo chiến lược đang được cấu hình. **Không khẳng định mỗi lần gọi sẽ luân phiên chính xác**: kết quả còn tùy thuật toán, bộ lọc instance, cache, retry và trạng thái hệ thống.

Một cách nhìn theo trình tự:

~~~mermaid
sequenceDiagram
    participant O as order-service
    participant L as LoadBalancer
    participant D as DiscoveryClient
    participant R as Nguồn instance
    participant C as catalog-service
    O->>L: GET http://catalog-service/api/products/42
    L->>D: Tìm instance của catalog-service
    D->>R: Đọc danh sách hiện tại
    R-->>D: catalog-1, catalog-2
    D-->>L: List<ServiceInstance>
    L->>C: GET /api/products/42 tới instance đã chọn
    C-->>O: HTTP response (qua client)
~~~

Trong ví dụ cấu hình tĩnh, “Nguồn instance” là cấu hình `spring.cloud.discovery.client.simple.instances`. Khi chuyển sang registry thật, luồng nghiệp vụ và service ID có thể giữ nguyên; cấu hình adapter và đặc tính vận hành phải được xem lại.

## 5. Quan hệ với Context, cấu hình bên ngoài và tương thích phiên bản

Commons thường được dùng cùng Spring Cloud Context, nhưng hai thư viện không có vai trò giống nhau:

| Nhu cầu | Cơ chế phù hợp | Giới hạn cần hiểu |
| --- | --- | --- |
| Thay URL, credential hoặc tham số theo môi trường | Externalized configuration của Spring Boot; có thể kết hợp nguồn cấu hình tập trung | Đổi giá trị ở nguồn không đảm bảo mọi bean đang chạy đã nhận giá trị mới |
| Làm mới bean có phạm vi refresh | Spring Cloud Context và `@RefreshScope` | Bean được tạo lại khi cơ chế refresh thực sự được kích hoạt; không tự làm mới mọi trạng thái ứng dụng |
| Tìm instance khi dịch vụ thay đổi | Commons `DiscoveryClient` cộng implementation thích hợp | Độ mới của dữ liệu phụ thuộc registry, cache, polling và mạng |
| Chọn instance cho lời gọi | Spring Cloud LoadBalancer và integration | Không tự thay thế timeout, retry, circuit breaker hoặc xác thực |
| Ghép thư viện Cloud với Boot | Spring Cloud release train/BOM và công cụ kiểm tra tương thích nếu có | Cần đối chiếu bảng tương thích chính thức cho từng cặp phiên bản |

Ví dụ: thay đổi địa chỉ tĩnh của `catalog-service` trong cấu hình là bài toán **cập nhật nguồn cấu hình**; để ứng dụng đang chạy nhìn thấy danh sách mới còn phụ thuộc cơ chế reload/refresh của nguồn đó. Khi một instance đăng ký mới vào Eureka/Consul/Kubernetes, đó là bài toán **cập nhật discovery**, không nhất thiết cần refresh `@RefreshScope` của mọi bean.

Với Spring Cloud hiện đại, nhiều discovery implementation được cấu hình tự động thông qua starter; `@EnableDiscoveryClient` thường không bắt buộc. Luôn kiểm tra yêu cầu của integration và phiên bản thực tế. Tránh mang cấu hình cũ của Ribbon hoặc các thành phần đã ngừng được hỗ trợ sang dự án mới mà không xem lại tài liệu phiên bản.

## 6. Phần dùng chung đem lại lợi ích gì?

**Giảm phụ thuộc nhà cung cấp:** lớp nghiệp vụ có thể yêu cầu `DiscoveryClient` hoặc gọi HTTP theo service ID. Thay Eureka bằng một discovery implementation tương thích thường giảm lượng mã ứng dụng phải sửa, dù vẫn có thể cần đổi dependency, cấu hình, health check và quy tắc vận hành.

**Thống nhất mô hình và tích hợp:** `ServiceInstance` cung cấp mô hình chung cho danh sách instance. Các thành phần như load balancer và health integration có thể sử dụng cùng ý niệm service ID/instance, giúp hệ sinh thái Spring phối hợp nhất quán hơn.

**Dễ kiểm thử:** một interface như `DiscoveryClient` có thể được giả lập để kiểm tra logic ở cấp đơn vị. Cấu hình discovery tĩnh giúp chạy bài thử tích hợp mà không cần đầy đủ hạ tầng registry.

**Tăng khả năng thay đổi khi vận hành:** hệ thống có thể triển khai nhiều instance sau một tên dịch vụ. Tuy vậy, kết quả phụ thuộc adapter, cơ chế loại bỏ instance lỗi, giới hạn gọi mạng và cấu hình của client.

## 7. Kiểm thử các abstraction của Commons

Có thể kiểm thử độc lập lớp `CatalogLocator` ở trên bằng `Mockito` và `JUnit 5`, không cần kết nối registry:

~~~java
import java.net.URI;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.DefaultServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class CatalogLocatorTest {
    @Test
    void readsEndpointsFromDiscoveryClient() {
        DiscoveryClient discovery = mock(DiscoveryClient.class);
        when(discovery.getInstances("catalog-service")).thenReturn(List.of(
            new DefaultServiceInstance(
                "catalog-1", "catalog-service", "localhost", 8081, false
            )
        ));

        CatalogLocator locator = new CatalogLocator(discovery);

        assertThat(locator.endpoints())
                .containsExactly(URI.create("http://localhost:8081"));
    }
}
~~~

Ví dụ giả định dự án có dependency kiểm thử Spring Boot hoặc tương đương cung cấp JUnit, Mockito và AssertJ.

Ở mức tích hợp, nên có các kịch bản sau:

| Tình huống | Điều cần xác nhận |
| --- | --- |
| Có hai instance khỏe mạnh | Lời gọi qua service ID có thể đến instance đã chọn và nhận phản hồi |
| Discovery trả danh sách rỗng | Client trả lỗi có kiểm soát, không treo vô hạn |
| Một instance ngừng phục vụ | Chính sách timeout, retry và loại bỏ instance hoạt động theo cấu hình |
| Registry tạm thời không truy cập được | Hành vi cache, fallback và phục hồi được hiểu rõ; không giả định dữ liệu luôn tức thời |
| Cấu hình thay đổi lúc chạy | Xác định chính xác thành phần nào được refresh/rebind và có cần khởi động lại không |
| Nâng Spring Boot/Spring Cloud | Khởi động ứng dụng và kiểm tra dependency, auto-configuration, discovery, load balancing |

Trong production, theo dõi log, chỉ số lỗi/độ trễ của lời gọi dịch vụ, trạng thái registry và health. Cần xác định thời gian timeout, ngân sách retry và chính sách circuit breaker ở lớp phù hợp; Commons không tự quyết định các tham số này cho mọi ứng dụng.

## 8. Những nhầm lẫn thường gặp

1. **“Thêm Spring Cloud Commons là có service discovery ngay.”** Commons cung cấp API; cần có implementation thích hợp, hoặc danh sách tĩnh được cấu hình.
2. **“`DiscoveryClient` sẽ tự chia đều request.”** Discovery chỉ trả danh sách. Load balancing là bước riêng, cần tích hợp và thuật toán chọn instance.
3. **“`ServiceRegistry` chính là registry server.”** Đây là hợp đồng phía ứng dụng; server, giao thức và quy tắc lease phụ thuộc nhà cung cấp.
4. **“`@RefreshScope` tự làm mọi cấu hình thay đổi tức thì.”** Refresh cần tín hiệu/cơ chế kích hoạt và không bao phủ tùy ý mọi đối tượng hoặc kết nối đã tạo.
5. **“Cùng service ID thì các instance chắc chắn tương đương.”** Hợp đồng API, phiên bản, dữ liệu và khả năng tương thích khi rolling deployment phải được quản lý độc lập.
6. **“Dùng interface chung thì không cần quan tâm phiên bản.”** Boot và Cloud phải có bộ phiên bản tương thích; API, starter và auto-configuration có thể thay đổi giữa các release train.

## 9. Khi nào dùng abstraction nào?

| Bạn đang cần... | Điểm bắt đầu |
| --- | --- |
| Hiển thị hoặc kiểm tra các instance của một dịch vụ | `DiscoveryClient` hoặc `ReactiveDiscoveryClient` |
| Biểu diễn thông tin một instance độc lập vendor | `ServiceInstance` |
| Tích hợp đăng ký/hủy đăng ký theo provider | `ServiceRegistry` và `Registration` |
| Gọi API bằng `http://service-id/...` | HTTP client được tích hợp `@LoadBalanced`, cộng Spring Cloud LoadBalancer |
| Cấu hình cho từng môi trường | Externalized configuration của Spring Boot |
| Làm mới bean theo tín hiệu refresh | Spring Cloud Context, `@RefreshScope` khi phù hợp |

**Điểm ghi nhớ:** Spring Cloud Commons là lớp quy ước chung giữa mã nghiệp vụ và các thành phần hạ tầng của Spring Cloud. Nó làm cho discovery, registration và load balancing có thể tích hợp theo các hợp đồng ổn định hơn; khả năng hoạt động thực tế vẫn đến từ implementation, cấu hình và cách vận hành của từng hệ thống phân tán.
