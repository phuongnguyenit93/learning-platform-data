# Phụ thuộc OpenFeign, LoadBalancer và điều kiện tích hợp

**Spring Cloud OpenFeign** giúp ứng dụng Java gọi HTTP API bằng một interface khai báo với `@FeignClient`, thay vì tự xây dựng từng request trong mã nghiệp vụ. Tuy nhiên, **có Feign chưa chắc đã có client-side load balancing**. Để Feign dùng **Spring Cloud LoadBalancer** chọn bản sao (`ServiceInstance`) theo service ID, ứng dụng cần đúng dependency, đúng bean auto-configuration, nguồn danh sách instance và cách khai báo client không cố định URL.

Ví dụ, `order-service` cần gọi `catalog-service` có hai bản sao. Cách khai báo sau thể hiện ý định gọi theo tên dịch vụ:

~~~java
@FeignClient(name = "catalog-service")
interface CatalogFeignClient {
    @GetMapping("/products/{id}")
    ProductDto findById(@PathVariable("id") Long id);
}
~~~

Nếu tích hợp LoadBalancer hoạt động, `catalog-service` là **service ID**, còn đích vật lý được chọn ở mỗi lời gọi có thể là `10.0.1.11:8081` hoặc `10.0.1.12:8081`. Nếu khai báo thêm `url`, Feign sẽ gọi URL được cung cấp **không qua cơ chế cân bằng tải theo service ID**.

Bài học thuộc chương **OpenFeign** làm rõ bốn câu hỏi: cần những phụ thuộc nào, điều kiện nào kích hoạt tích hợp, phân biệt Feign HTTP transport với bộ chọn instance ra sao, và kiểm tra thế nào để biết ứng dụng có thực sự gọi qua LoadBalancer.

## 1. Ba lớp phụ thuộc không được nhầm lẫn

Một lời gọi HTTP qua Feign có thể đi qua ba lớp khác nhau:

| Lớp | Thành phần tiêu biểu | Trách nhiệm |
|---|---|---|
| **Khai báo HTTP client** | `spring-cloud-starter-openfeign`, `@FeignClient`, Feign encoder/decoder/contract | Sinh proxy từ interface, chuyển method invocation thành HTTP request và decode response |
| **Chọn bản sao** | `spring-cloud-starter-loadbalancer`, `FeignBlockingLoadBalancerClient`, `ServiceInstanceListSupplier` | Tra service ID, lấy danh sách instance và chọn endpoint cụ thể |
| **Cung cấp danh sách bản sao** | Eureka/Consul/Zookeeper discovery client, `SimpleDiscoveryClient` hoặc supplier tùy biến | Cho biết service ID đang có những `ServiceInstance` nào |

Ba lớp có thể phối hợp, nhưng **không thay thế nhau**.

- Feign biết cách tạo một HTTP request theo interface, nhưng không tự tạo ra registry.
- LoadBalancer chọn endpoint từ một danh sách, nhưng không tự đăng ký hoặc chạy các server.
- Discovery cung cấp danh sách, nhưng không tự bảo đảm Feign sẽ sử dụng danh sách đó nếu Feign chưa tích hợp LoadBalancer.
- HTTP transport bên dưới Feign vẫn phụ trách kết nối TCP/TLS, connection pool, timeout và truyền dữ liệu.

~~~mermaid
flowchart TD
    A["Mã nghiệp vụ gọi CatalogFeignClient"]
    B["Feign proxy / SpringMvcContract"]
    C["FeignBlockingLoadBalancerClient"]
    D["ServiceInstanceListSupplier"]
    E["Discovery client hoặc nguồn tĩnh"]
    F["LoadBalancer chọn ServiceInstance"]
    G["Feign Client thực thi HTTP"]
    H["catalog instance tại host:port"]
    A --> B --> C
    C --> D --> E
    E --> D --> F
    F --> C --> G --> H
~~~

Sơ đồ mô tả trường hợp **có đủ điều kiện tích hợp LoadBalancer**. Nếu Feign được cấu hình gọi URL vật lý trực tiếp, bước chọn `ServiceInstance` theo service ID sẽ không tham gia.

## 2. Dependency bắt buộc và dependency tùy chọn

### 2.1. Starter OpenFeign

Để Spring Boot tạo Feign clients, trước hết cần dependency:

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-openfeign")
}
~~~

Starter này cung cấp cấu hình cho `@FeignClient`, Feign proxy, Spring MVC contract, encoder/decoder và các tích hợp thích hợp với Spring Cloud.

### 2.2. Starter LoadBalancer — phải thêm rõ khi cần chọn instance

**`spring-cloud-starter-loadbalancer` là dependency tùy chọn của Spring Cloud OpenFeign**, không được xem là luôn có sẵn chỉ vì đã thêm starter OpenFeign.

Khi cần client-side load balancing theo service ID, hãy khai báo rõ cả hai:

~~~kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-starter-openfeign")
    implementation("org.springframework.cloud:spring-cloud-starter-loadbalancer")
}
~~~

Nếu xây dựng HTTP controller hoặc REST endpoint trong cùng ứng dụng, có thể cần thêm `spring-boot-starter-web`, nhưng đây không phải điều kiện thay thế cho LoadBalancer.

**Không tự gắn version khác nhau cho từng starter Spring Cloud.** Cần sử dụng Spring Cloud BOM (`spring-cloud-dependencies`) cùng release train tương thích với Spring Boot của dự án. Các ví dụ trong bài chỉ hiển thị dependency cần thiết; việc nhập BOM/plugin quản lý phiên bản được thực hiện ở build configuration của dự án.

Với Maven, hai dependency tương ứng là:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-openfeign</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-loadbalancer</artifactId>
    </dependency>
</dependencies>
~~~

Đoạn XML giả định parent/BOM đã quản lý phiên bản; đây không phải `pom.xml` đầy đủ.

### 2.3. Nguồn discovery: không nhất thiết phải có registry ngoài

LoadBalancer cần danh sách instance cho service ID. Tùy môi trường, có thể dùng:

| Nguồn | Dependency / cấu hình | Phù hợp |
|---|---|---|
| Eureka | Starter Eureka discovery client tương thích | Hệ thống microservices đăng ký và hủy đăng ký động |
| Consul | Starter Spring Cloud Consul Discovery tương thích | Hệ thống dùng Consul service discovery |
| `SimpleDiscoveryClient` | Khai báo danh sách instance trong `application.yml` | Demo, local test và môi trường có endpoint tĩnh |
| Supplier tùy biến | Bean `ServiceInstanceListSupplier` theo cấu hình LoadBalancer | Cần chính sách hoặc nguồn dữ liệu riêng |

**Không phải cứ thêm Feign + LoadBalancer là phải thêm Eureka.** Thực hành có thể dùng `SimpleDiscoveryClient`. Ngược lại, nếu không cấu hình bất kỳ nguồn instance phù hợp nào thì LoadBalancer có thể không tìm thấy bản sao để gọi.

## 3. Điều kiện để Feign thực sự gọi qua LoadBalancer

Trong cấu hình Spring Cloud OpenFeign thông thường, cần đồng thời đáp ứng:

1. Ứng dụng có `spring-cloud-starter-openfeign` và các Feign client được Spring đăng ký.
2. Có Spring Cloud LoadBalancer trên classpath và auto-configuration tương ứng được áp dụng.
3. Feign client dùng **`name`/service ID**, **không khai báo URL cố định** trong annotation hoặc thuộc tính cấu hình client.
4. Có supplier/discovery trả về ít nhất một `ServiceInstance` của service ID đó.
5. Các cấu hình tùy biến không thay `Client` load-balanced bằng một Feign `Client` trực tiếp ngoài ý muốn.

Khi Spring Cloud LoadBalancer có mặt, cấu hình mặc định Spring Cloud OpenFeign chọn `FeignBlockingLoadBalancerClient` để bọc HTTP transport bên dưới. Nếu không có LoadBalancer trên classpath, Feign sử dụng HTTP client mặc định hoặc client được cấu hình và không có bước chọn instance của Spring Cloud LoadBalancer.

Điều kiện này **khác** với việc đã cài đặt một HTTP library như Apache HttpClient 5 hay OkHttp: các library đó thực hiện kết nối, không thay thế thuật toán chọn bản sao.

### Bảng quyết định

| OpenFeign starter | LoadBalancer starter | Feign có `url` cố định? | Nguồn instance | Kết quả thường gặp |
|---|---|---|---|---|
| Có | Có | Không | Có instance | Feign chọn qua LoadBalancer, sau đó gửi HTTP |
| Có | Có | Không | Danh sách rỗng | Không có instance để chọn; lỗi tại client/integration |
| Có | Không | Không | Có registry | Feign không dùng Spring Cloud LoadBalancer; tên đích có thể được xử lý như hostname bình thường |
| Có | Có | Có | Có hoặc không | Gọi URL đã cấu hình, **bỏ qua bước load balancing theo name** |
| Có | Có | Không | Không có nguồn nào phù hợp | Lookup theo service ID không cung cấp endpoint để gọi |
| Không | Có | Không áp dụng | Có | Không có cấu hình OpenFeign tương ứng để tạo proxy `@FeignClient` |

Đây là hành vi trong trường hợp cấu hình mặc định. Các `Client` bean, Feign factory, targeter, transport hoặc auto-configuration được tùy biến có thể thay đổi đường đi; cần kiểm tra bean thực tế khi ứng dụng có nhiều integration.

## 4. Bật quét Feign client đúng cách

Trong Spring Boot application, dùng `@EnableFeignClients` để đăng ký các interface Feign. Với dự án nhiều module, chỉ định client cụ thể thường rõ ràng hơn dựa vào package scan mặc định:

~~~java
package com.example.orders;

import com.example.orders.client.CatalogFeignClient;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.openfeign.EnableFeignClients;

@SpringBootApplication
@EnableFeignClients(clients = CatalogFeignClient.class)
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Interface tại package `com.example.orders.client`:

~~~java
package com.example.orders.client;

import org.springframework.cloud.openfeign.FeignClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@FeignClient(name = "catalog-service")
public interface CatalogFeignClient {

    @GetMapping("/products/{id}")
    ProductDto findById(@PathVariable("id") Long id);
}
~~~

DTO:

~~~java
package com.example.orders.client;

public record ProductDto(Long id, String name) {}
~~~

Sử dụng trong service:

~~~java
package com.example.orders;

import com.example.orders.client.CatalogFeignClient;
import com.example.orders.client.ProductDto;
import org.springframework.stereotype.Service;

@Service
class ProductLookupService {

    private final CatalogFeignClient catalog;

    ProductLookupService(CatalogFeignClient catalog) {
        this.catalog = catalog;
    }

    ProductDto load(long id) {
        return catalog.findById(id);
    }
}
~~~

Trong ví dụ này, code nghiệp vụ không chứa host, port hoặc một `RestClient` tự tạo. Proxy Feign lo HTTP contract; nếu đủ điều kiện, LoadBalancer chọn đích cho `catalog-service`.

Có thể dùng `@EnableFeignClients(basePackages = "com.example.orders.client")` thay cho `clients`. Với multi-module project, khai báo explicit package/interface giúp tránh tình huống component scan không thấy Feign client và phát sinh lỗi thiếu bean.

## 5. Cung cấp instance cho service ID

Để chạy thử mà không cần Eureka, khai báo danh sách tĩnh bằng `SimpleDiscoveryClient`:

~~~yaml
spring:
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://127.0.0.1:8081
                metadata:
                  zone: zone-a
              - uri: http://127.0.0.1:8082
                metadata:
                  zone: zone-b
~~~

Cấu hình trên đặt **hai instance** dưới khóa service ID `catalog-service`. Tên này phải khớp với `@FeignClient(name = "catalog-service")`. Mỗi instance cung cấp URI vật lý cho LoadBalancer.

Lưu ý:

- `127.0.0.1` chỉ phù hợp khi client và server dùng cùng network namespace hoặc cùng localhost; trong Docker/Kubernetes cần địa chỉ truy cập được giữa các workload.
- `SimpleDiscoveryClient` là nguồn **tĩnh**. Dừng server ở cổng `8081` không tự xóa URI đó khỏi cấu hình. Muốn quan sát danh sách thay đổi tự động, dùng discovery động hoặc supplier cập nhật danh sách.
- Metadata zone không tự động kích hoạt zone preference. Cần cấu hình supplier/chính sách tương ứng nếu muốn ưu tiên vùng.
- Không thêm thuộc tính `spring.cloud.openfeign.client.config.catalog-service.url` trong cùng ví dụ nếu mục đích là kiểm thử LoadBalancer.

Nếu hai backend cung cấp `GET /products/{id}` và trả JSON tương thích `ProductDto`, lời gọi `catalog.findById(42L)` có thể được phân phối tới một trong hai instance khi LoadBalancer sử dụng round-robin và danh sách ứng viên hợp lệ.

## 6. FeignBlockingLoadBalancerClient tham gia luồng gọi như thế nào?

Spring Cloud OpenFeign phối hợp các thành phần theo thứ tự khái niệm:

~~~mermaid
sequenceDiagram
    participant App as ProductLookupService
    participant Proxy as CatalogFeignClient proxy
    participant FeignLB as FeignBlockingLoadBalancerClient
    participant LB as BlockingLoadBalancerClient
    participant Supplier as ServiceInstanceListSupplier
    participant HTTP as Feign HTTP Client
    participant Target as catalog-service instance
    App->>Proxy: findById(42)
    Proxy->>FeignLB: Feign Request tới service ID
    FeignLB->>LB: choose("catalog-service")
    LB->>Supplier: lấy danh sách ứng viên
    Supplier-->>LB: catalog-1, catalog-2
    LB-->>FeignLB: catalog-2: 127.0.0.1:8082
    FeignLB->>HTTP: Request tới URI vật lý
    HTTP->>Target: GET /products/42
    Target-->>HTTP: HTTP response
    HTTP-->>App: ProductDto hoặc lỗi
~~~

Phân biệt ba đầu ra:

- **Kết quả discovery:** danh sách `ServiceInstance` cho service ID.
- **Kết quả selection:** một `ServiceInstance` đã được chọn.
- **Kết quả HTTP:** status, headers, body hoặc exception từ transport.

Ngay cả khi lựa chọn instance thành công, kết nối HTTP vẫn có thể thất bại nếu server dừng hoặc host/port không truy cập được. Feign proxy không biến một endpoint đã chết thành endpoint khỏe.

Với load-balanced Feign, `FeignBlockingLoadBalancerClient` làm việc cùng một delegate `feign.Client` để gửi request sau bước lựa chọn. Delegate có thể là transport mặc định, Apache HttpClient 5 hoặc một lựa chọn được cấu hình. Vì vậy, **không nhầm `FeignBlockingLoadBalancerClient` với connection pool**: lớp đầu tiên chọn instance/điều phối, lớp thứ hai vận chuyển request.

## 7. Chỉ cần thêm url là có thể bỏ qua LoadBalancer

Đây là nguồn gây nhầm lẫn thường gặp khi cấu hình Feign.

### 7.1. URL nằm ngay trong @FeignClient

~~~java
@FeignClient(
        name = "catalog-service",
        url = "http://127.0.0.1:8081"
)
interface DirectCatalogClient {

    @GetMapping("/products/{id}")
    ProductDto findById(@PathVariable("id") Long id);
}
~~~

Client này gọi URL cố định, **không dùng LoadBalancer chọn `catalog-service` từ discovery** dù `spring-cloud-starter-loadbalancer` vẫn tồn tại trên classpath.

### 7.2. URL nằm trong cấu hình client

Nếu interface không khai báo `url`:

~~~java
@FeignClient(name = "catalog-service")
interface CatalogFeignClient {
    @GetMapping("/products/{id}")
    ProductDto findById(@PathVariable("id") Long id);
}
~~~

Nhưng `application.yml` chứa:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            url: http://127.0.0.1:8081
~~~

Thì `catalog-service` cũng được gắn với **đích cố định**, không chạy load balancing theo service ID.

### 7.3. Cả annotation và properties cùng có URL

Theo tài liệu Spring Cloud OpenFeign, nếu `url` đã được cung cấp trong `@FeignClient`, URL ở annotation có ưu tiên cho việc tạo client; URL tương ứng trong properties không dùng để ghi đè trường hợp này.

| URL trong annotation | URL trong properties | Cách chọn đích |
|---|---|---|
| Không | Không | Tên `@FeignClient` được dùng như service ID cho LoadBalancer (nếu tích hợp có sẵn) |
| Có | Không | Gọi URL từ annotation |
| Không | Có | Gọi URL từ properties |
| Có | Có | Gọi URL từ annotation; property URL không quyết định đích |

**Tên `name` vẫn cần khai báo**, ngay cả khi có `url`. Đừng coi `@FeignClient(name = "catalog-service", url = "...")` là cách “ưu tiên instance này rồi failover bằng LoadBalancer”; thông thường nó chỉ gọi đích đã xác định.

## 8. Tùy chọn thêm vào không phải điều kiện bắt buộc của LoadBalancer

Nhiều công cụ thường đi cùng Feign nhưng phục vụ nhiệm vụ khác:

| Thành phần | Cần để Feign chọn `ServiceInstance`? | Vai trò |
|---|---|---|
| `spring-cloud-starter-openfeign` | Cần cho Feign proxy | Khai báo và tạo HTTP client |
| `spring-cloud-starter-loadbalancer` | Cần cho tích hợp Spring Cloud LB theo service ID | Chọn instance |
| Eureka/Consul hoặc `SimpleDiscoveryClient` | Cần một nguồn instance tương đương | Cung cấp các endpoint |
| Apache HttpClient 5 | Không | Connection pooling và thực thi HTTP |
| `feign-micrometer` + `ObservationRegistry` | Không | Metrics/tracing HTTP client khi tích hợp được bật |
| Spring Cloud CircuitBreaker starter | Không | Circuit breaker/fallback riêng |
| Retryer tùy biến | Không | Điều chỉnh thử lại theo chính sách |
| OAuth2 client | Không | Cấp access token cho lời gọi được cấu hình |

### 8.1. Transport Apache HttpClient 5

Khi Apache HttpClient 5 có trên classpath và Spring Cloud OpenFeign cấu hình dùng nó, Feign có thể tái sử dụng kết nối qua connection pool. Để vô hiệu hóa cơ chế HTTP client này theo cấu hình OpenFeign, có thể đặt:

~~~yaml
spring:
  cloud:
    openfeign:
      httpclient:
        hc5:
          enabled: false
~~~

Đây là cấu hình **HTTP transport**, không có nghĩa LoadBalancer bị tắt. Tương tự, giới hạn pool, socket timeout và kết nối theo route không phải cấu hình của thuật toán round-robin.

Từ Spring Cloud OpenFeign 4, Apache HttpClient 4 không còn là lựa chọn được hỗ trợ trong integration này; cần dùng transport tương thích như HttpClient 5.

### 8.2. Circuit breaker là cơ chế riêng

Để bật Spring Cloud CircuitBreaker wrapping cho Feign, cần dependency circuit breaker phù hợp và thuộc tính:

~~~yaml
spring:
  cloud:
    openfeign:
      circuitbreaker:
        enabled: true
~~~

Chỉ thêm `spring-cloud-starter-loadbalancer` không tự bật circuit breaker. Circuit breaker quyết định có tiếp tục thực thi lời gọi sau nhiều lỗi hay không; LoadBalancer quyết định instance nào được chọn khi lời gọi được thực hiện.

### 8.3. Retry và timeout cũng có cấu hình riêng

Spring Cloud OpenFeign mặc định cung cấp `Retryer.NEVER_RETRY` để tắt retry ở cấp Feign, khác với hành vi mặc định của Feign thuần. Retry của LoadBalancer hoặc lớp resilience khác, nếu được cấu hình và áp dụng, là vấn đề riêng: không nên giả định mọi request được thử lại chỉ vì có LoadBalancer.

Một cấu hình timeout minh họa cho Feign client:

~~~yaml
spring:
  cloud:
    openfeign:
      client:
        config:
          catalog-service:
            connectTimeout: 2000
            readTimeout: 5000
            loggerLevel: basic
~~~

`connectTimeout` và `readTimeout` ở đây dùng đơn vị milliseconds theo cấu hình OpenFeign. Chúng thuộc phần thực thi HTTP của Feign, không phải timeout của discovery client hay TTL cache instance. Giá trị ví dụ cần được kiểm thử trong hệ thống thật, đặc biệt khi có retry nhiều tầng.

## 9. Cấu hình named client và nguy cơ chồng lấn bean

Spring Cloud OpenFeign tạo **ngữ cảnh cấu hình theo named client** (thông qua `FeignClientsConfiguration`), gồm các thành phần như:

- `Decoder` và `Encoder` để chuyển đổi response/request body.
- `SpringMvcContract` để diễn giải annotation như `@GetMapping`, `@PostMapping`.
- `Feign.Builder` để tạo proxy.
- `feign.Client` để thực thi request; có thể được bọc bằng `FeignBlockingLoadBalancerClient` nếu đủ điều kiện.

Điều này cho phép mỗi service ID có timeout, encoder/decoder và các tùy chỉnh khác nhau. Nhưng nếu người phát triển tạo một bean `feign.Client` tùy biến không phù hợp hoặc cấu hình ngoài ý muốn, có thể làm thay đổi đường đi load-balanced mặc định.

### Dùng contextId khi có nhiều client cùng service

Khi có hai Feign interface cùng trỏ `catalog-service` nhưng khác policy, dùng `contextId` để tránh xung đột tên bean cấu hình:

~~~java
@FeignClient(
        contextId = "catalogReadClient",
        name = "catalog-service",
        configuration = CatalogReadFeignConfiguration.class
)
interface CatalogReadClient {
    @GetMapping("/products/{id}")
    ProductDto findById(@PathVariable("id") Long id);
}

@FeignClient(
        contextId = "catalogAdminClient",
        name = "catalog-service",
        configuration = CatalogAdminFeignConfiguration.class
)
interface CatalogAdminClient {
    @GetMapping("/admin/health")
    String health();
}
~~~

Hai interface vẫn dùng cùng **service ID `catalog-service`** cho discovery, nhưng có ngữ cảnh cấu hình Feign tách biệt. Hai class cấu hình ở ví dụ là các class ứng dụng cần tự định nghĩa nếu sử dụng đoạn mã này.

Nếu class cấu hình riêng được đặt trong phạm vi `@ComponentScan` của application context chính, các bean encoder/decoder/interceptor tùy biến có thể vô tình trở thành cấu hình chung cho nhiều Feign client. Nên đặt chúng ngoài vùng scan chính hoặc giới hạn rõ phạm vi.

### Scope của Feign HTTP Client

Tài liệu OpenFeign hiện hành nhấn mạnh bean `feign.Client` tùy biến nên có scope **singleton**. Nếu tạo HTTP `Client` mới mỗi lần khởi tạo Feign client, có thể tạo nhiều connection pool không cần thiết, gây cạn socket hoặc rò rỉ tài nguyên.

Điều này **không có nghĩa chỉ có một Feign interface trong cả ứng dụng**. Nhiều Feign proxies có thể chia sẻ hoặc dùng những transport/pool được quản lý vòng đời phù hợp.

## 10. Các lỗi tích hợp thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Không inject được `CatalogFeignClient` | Thiếu `@EnableFeignClients` hoặc quét sai package/interface | Kiểm tra annotation, `clients`/`basePackages` và module chứa interface |
| Feign gọi hostname `catalog-service` qua DNS thay vì discovery | Thiếu LoadBalancer trên classpath, hoặc dùng `Client` không tích hợp LB | Xem dependency tree và loại bean `feign.Client` đang sử dụng |
| Feign luôn gọi một IP dù có nhiều instance | `url` trong annotation/properties, hoặc supplier chỉ trả một instance | Kiểm tra URL precedence, danh sách discovery và policy |
| Client báo không có instance cho service ID | Service ID sai, registry rỗng hoặc supplier lọc hết | So sánh `@FeignClient(name)` và danh sách của `DiscoveryClient` |
| Có instance nhưng kết nối thất bại | Host/port của instance không truy cập được hoặc server chưa sẵn sàng | Kiểm tra network từ nơi client chạy, health và cache |
| Bật OkHttp/HC5 nhưng vẫn không chia tải | Đang thay HTTP transport, không cấu hình lại instance selection | Kiểm tra `FeignBlockingLoadBalancerClient` và supplier |
| Tạo hai client cùng `name` bị xung đột cấu hình | Trùng tên context/bean cấu hình | Dùng `contextId` duy nhất khi cần nhiều cấu hình |
| Circuit breaker/fallback không hoạt động | Chưa thêm dependency hoặc chưa bật thuộc tính tương ứng | Kiểm tra cấu hình Spring Cloud CircuitBreaker |
| Retry không diễn ra | `Retryer.NEVER_RETRY` mặc định hoặc policy không cho phép retry | Xem retry theo Feign, LoadBalancer và tầng ứng dụng |
| HTTP 503 | Có thể không có instance, hoặc backend/proxy trả 503 | Đọc exception, log lựa chọn instance và response nguồn |

**Không nên chẩn đoán chỉ từ HTTP status.** Nếu không có instance để chọn, lỗi phát sinh trước lần gửi HTTP tới backend. Nếu đã chọn instance nhưng backend trả HTTP 500, lỗi nằm sau bước chọn; LoadBalancer không tự sửa được lỗi nghiệp vụ.

## 11. Kiểm thử có thật sự load balance không?

Cấu hình đúng trên giấy chưa đủ. Một bài thực hành ngắn giúp phân biệt rõ Feign proxy, discovery và LoadBalancer.

### Thiết lập

1. Khởi động hai bản sao `catalog-service` ở cổng `8081` và `8082`; cả hai phục vụ `GET /whoami` với response là instance ID.
2. Khai báo hai URI trong `SimpleDiscoveryClient` như mục 5.
3. Thêm hai starter OpenFeign và LoadBalancer vào ứng dụng gọi.
4. Đăng ký một interface Feign **chỉ có `name = "catalog-service"`**, không có `url` trong annotation hay properties.
5. Gọi `/whoami` nhiều lần và ghi lại instance ID được trả về, cùng tên bean/transport nếu cần.

Một interface dùng cho bài test:

~~~java
@FeignClient(name = "catalog-service")
interface CatalogProbeClient {
    @GetMapping("/whoami")
    String whoAmI();
}
~~~

Với round-robin và hai ứng viên, kết quả thường thay đổi giữa hai instance. Không giả định thứ tự hai lần gọi đầu tiên luôn cố định vì còn phụ thuộc trạng thái chọn, mức đồng thời và các bộ lọc.

### Thí nghiệm phân biệt điều kiện

| Thí nghiệm | Thay đổi | Điều cần quan sát |
|---|---|---|
| A — Có LoadBalancer | Giữ cả hai starter, không đặt URL | Client chọn qua các instance mà discovery cung cấp |
| B — URL cố định | Thêm `url = "http://127.0.0.1:8081"` vào Feign client | Chỉ gọi cổng 8081, không chọn 8082 theo LoadBalancer |
| C — Không có starter LB | Bỏ dependency LoadBalancer cho lần chạy riêng | Feign không chọn instance qua Spring Cloud LB; tên dịch vụ có thể bị xử lý như hostname DNS |
| D — Service ID sai | Đổi `name` thành `catalog-unknown` | Không lấy được đúng danh sách instance; quan sát lỗi chọn đích |
| E — Instance chết nhưng còn trong cấu hình tĩnh | Dừng server 8081 mà không sửa danh sách | LoadBalancer vẫn có thể chọn URI không còn phục vụ; lỗi kết nối |
| F — Quét Feign sai | Bỏ `@EnableFeignClients` hoặc bỏ interface khỏi phạm vi scan | Feign proxy không được đăng ký làm bean |

Không chạy thí nghiệm phá dependency hoặc dừng dịch vụ trên production. Trong `SimpleDiscoveryClient`, việc sửa YAML thường cần khởi động lại hoặc cơ chế refresh thích hợp; danh sách tĩnh không tự hủy đăng ký khi backend tắt.

## 12. Checklist trước khi kết luận Feign đã tích hợp LoadBalancer

1. **Build:** Có `spring-cloud-starter-openfeign` **và** `spring-cloud-starter-loadbalancer`, cùng BOM Spring Cloud tương thích Spring Boot?
2. **Registration:** Có `@EnableFeignClients` và scan đúng interface?
3. **Naming:** `@FeignClient(name = "...")` khớp service ID registry hoặc `SimpleDiscoveryClient`?
4. **URL:** Có vô tình đặt `url` trong annotation hoặc `spring.cloud.openfeign.client.config.<client>.url` làm Feign bỏ qua LoadBalancer?
5. **Instances:** Supplier có trả ít nhất một instance và host/port có truy cập được?
6. **Client bean:** `FeignBlockingLoadBalancerClient` có tham gia đường thực thi mặc định không, hay custom `feign.Client` đã thay thế?
7. **Transport:** Nếu dùng Apache HC5/OkHttp, timeout và pool được cấu hình đúng mà không nhầm với thuật toán chọn đích?
8. **Recovery:** Retry, circuit breaker và health check có được bật/cấu hình theo yêu cầu, thay vì chỉ giả định tồn tại?
9. **Observability:** Có thể liên hệ service ID, instance được chọn, HTTP status/exception và thời gian request?
10. **Validation:** Đã kiểm thử với ít nhất hai instance và phân biệt được lời gọi load-balanced với lời gọi URL cố định?

**Kết luận:** OpenFeign cung cấp mô hình HTTP client khai báo; Spring Cloud LoadBalancer cung cấp khả năng **chọn `ServiceInstance` theo service ID** khi có đúng dependency và tích hợp; discovery cung cấp **danh sách bản sao**. Với `@FeignClient(name = "catalog-service")` không có URL cố định và đủ các thành phần này, request đi qua `FeignBlockingLoadBalancerClient` trước khi HTTP transport kết nối tới instance được chọn. Nếu thiếu starter LoadBalancer, thiếu danh sách instance hoặc vô tình đặt URL cố định, hành vi sẽ khác hẳn dù interface Feign nhìn gần như giống nhau.

**Tài liệu tham khảo chính thức:**

- [Spring Cloud OpenFeign – Features, Dependencies và LoadBalancer](https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html)
- [Spring Cloud OpenFeign – Configuration Properties](https://docs.spring.io/spring-cloud-openfeign/reference/configprops.html)
- [Spring Cloud Commons – Spring Cloud LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html)

