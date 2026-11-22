# Khai báo RestClient.Builder có @LoadBalanced

Trong kiến trúc microservice, `order-service` thường không nên hard-code địa chỉ `localhost:8081` của `inventory-service`. Một service có thể có nhiều `ServiceInstance` chạy ở các host/port khác nhau, và danh sách instance thay đổi khi triển khai hoặc scale. Với **Spring Cloud LoadBalancer**, bạn có thể gọi dịch vụ bằng **service ID** thông qua `RestClient` bằng cách khai báo một `RestClient.Builder` có `@LoadBalanced`.

Bài học thuộc chương **RestClient** của module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING`. Module hướng tới việc hiểu cân bằng tải phía client: chọn `ServiceInstance` theo service ID, discovery, health check, chính sách định tuyến và giao tiếp ổn định bằng `RestClient`, `WebClient`, OpenFeign, retry/timeout cùng quan sát lỗi. Nội dung bài tập trung vào cách khai báo đúng **builder có khả năng load balancing**, sử dụng nó trong ứng dụng và kiểm chứng rằng request được gửi tới bản sao thích hợp.

Sau bài học, bạn có thể:

- Phân biệt `RestClient`, `RestClient.Builder` và ý nghĩa của annotation `@LoadBalanced`.
- Cài dependency cần thiết và đăng ký bean builder có `@LoadBalanced`.
- Tạo client gọi `http://inventory-service` thay vì host/port cố định.
- Dùng builder có cân bằng tải bên cạnh builder/client HTTP trực tiếp mà không nhầm bean.
- Hiểu nơi LoadBalancer chọn instance và giới hạn của `@LoadBalanced` đối với retry, timeout, health check.
- Kiểm tra lỗi thường gặp khi service ID không được phân giải hoặc request không tới được replica.

## 1. Vì sao RestClient cần @LoadBalanced?

Một lời gọi tới địa chỉ vật lý dùng URI như sau:

~~~http
GET http://localhost:8081/internal/instance
~~~

Ở đây, `localhost:8081` là một **địa chỉ đích cụ thể**. Nếu instance chuyển sang `8082`, client phải biết địa chỉ mới. Nếu có ba replica, `RestClient` thông thường không tự biết nên chọn replica nào theo danh sách discovery.

Khi dùng Spring Cloud LoadBalancer, caller có thể gửi:

~~~http
GET http://inventory-service/internal/instance
~~~

`inventory-service` ở đây là **service ID**. Nếu builder được tích hợp với Spring Cloud LoadBalancer, phần hostname logic của URI được dùng để xác định dịch vụ cần tìm. LoadBalancer lấy danh sách `ServiceInstance`, chọn một instance rồi gửi HTTP tới địa chỉ vật lý của instance đó.

~~~mermaid
flowchart LR
    A["RestClient gọi http://inventory-service"] --> B["LoadBalancer interceptor"]
    B --> C["Service ID: inventory-service"]
    C --> D["ServiceInstanceListSupplier"]
    D --> E["Discovery: inv-a, inv-b, inv-c"]
    E --> F["Chọn một ServiceInstance"]
    F --> G["Thay URI bằng host:port thực"]
    G --> H["HTTP request tới replica"]
~~~

Điểm quan trọng: `@LoadBalanced` **không phải là một thuật toán round robin**. Annotation đánh dấu builder để cơ chế tự động cấu hình của Spring Cloud bổ sung khả năng dùng LoadBalancer. Việc lấy danh sách và chọn instance thuộc về các thành phần Spring Cloud LoadBalancer.

## 2. Phân biệt ba đối tượng

| Thành phần | Vai trò | Có tự cân bằng tải không? |
|---|---|---|
| `RestClient` | HTTP client đồng bộ dùng API fluent để gửi request, nhận response | Không, nếu được tạo từ builder thông thường |
| `RestClient.Builder` | Cấu hình và xây dựng một `RestClient` | Không, nếu không được tích hợp LoadBalancer |
| `@LoadBalanced RestClient.Builder` | Bean builder được Spring Cloud nhận diện để gắn khả năng chọn service instance | Có, khi dependency và auto-configuration tương ứng hoạt động |

`RestClient` là HTTP client **đồng bộ** của Spring Framework. Nếu ứng dụng cần gọi bất đồng bộ/non-blocking, `WebClient` có mô hình khác. Cả hai đều có thể tích hợp Spring Cloud LoadBalancer, nhưng bài này chỉ giải thích `RestClient.Builder`.

`RestClient.Builder` mang các cấu hình như base URL, headers, request factory, message converters và interceptors. Sau khi gọi `build()`, bạn nhận `RestClient` để tái sử dụng. Không nên sửa một shared builder liên tục từ nhiều luồng request để thay đổi service ID động: hãy xây client thích hợp trong giai đoạn khởi tạo ứng dụng.

## 3. Điều kiện để ví dụ hoạt động

Ví dụ giả định dự án dùng phiên bản Spring Boot/Spring Cloud **tương thích**, có `RestClient` (Spring Framework 6.1 trở lên) và tích hợp Spring Cloud LoadBalancer với `RestClient.Builder`.

Các dependency Gradle thường cần trong ứng dụng caller:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Trong dự án thực tế, hãy sử dụng **Spring Cloud BOM tương thích với phiên bản Spring Boot** để quản lý phiên bản các thư viện Spring Cloud; không đặt ngẫu nhiên những phiên bản độc lập cạnh nhau. Nếu ứng dụng dùng Eureka/Consul/Kubernetes discovery, cần bổ sung starter/adapter discovery tương ứng theo nền tảng của dự án.

Bạn có thể bắt đầu bằng `SimpleDiscoveryClient` để thử nghiệm mà không cần registry động. Với cấu hình tĩnh, không cần có một Eureka server đang chạy; nhưng các địa chỉ instance phải thực sự phục vụ HTTP nếu muốn kiểm chứng end-to-end.

### Ghi nhớ sự khác nhau giữa dependency và annotation

- **Dependency LoadBalancer** cung cấp cơ chế lựa chọn instance và tích hợp với HTTP client.
- **Discovery** cung cấp thông tin instance. Nó có thể là registry động hoặc danh sách tĩnh.
- **Annotation `@LoadBalanced` trên builder** giúp Spring Cloud nhận ra bean phải được trang bị khả năng lựa chọn instance theo service ID.
- **HTTP transport** thực hiện request cuối tới địa chỉ đã chọn.

Chỉ thêm dependency mà không chọn đúng builder có thể khiến request vẫn dùng hostname như một địa chỉ DNS bình thường. Chỉ gắn `@LoadBalanced` mà không có auto-configuration hoặc nguồn instance phù hợp cũng không đủ để request thành công.

## 4. Khai báo bean RestClient.Builder có @LoadBalanced

Cấu hình tối thiểu:

~~~java
package com.example.order.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class RestClientConfig {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Phân tích từng phần:

1. `@Configuration` cho biết đây là lớp khai báo bean Spring.
2. `@Bean` đưa đối tượng `RestClient.Builder` vào application context.
3. `@LoadBalanced` là marker/qualifier để các thành phần Spring Cloud nhận biết builder cần được cấu hình cho load balancing.
4. `RestClient.builder()` tạo builder. Spring Cloud tích hợp phần load-balancing thông qua cơ chế xử lý bean và interceptor phù hợp khi có dependency.
5. Tên `loadBalancedRestClientBuilder` giúp dễ phân biệt với builder thông thường nếu ứng dụng có nhiều client.

**Đặt annotation ở phương thức khai báo bean builder**, không phải chỉ ở một controller gọi HTTP. Đối tượng được inject về sau phải chính là builder đã được xử lý cho load balancing.

Lưu ý rằng cách cấu hình cụ thể phụ thuộc vào phiên bản Spring Cloud: nếu annotation không được xử lý hoặc bean không xuất hiện trong context, bạn phải sửa dependency/auto-configuration trước, thay vì giả định service ID sẽ được tự động phân giải.

## 5. Inject builder và tạo RestClient cho một service cụ thể

Với `InventoryClient`, tạo client từ builder có `@LoadBalanced`:

~~~java
package com.example.order.client;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class InventoryClient {

    private final RestClient inventoryRestClient;

    public InventoryClient(
            @LoadBalanced RestClient.Builder builder) {
        this.inventoryRestClient = builder
                .clone()
                .baseUrl("http://inventory-service")
                .build();
    }

    public String readInstanceIdentity() {
        return inventoryRestClient.get()
                .uri("/internal/instance")
                .retrieve()
                .body(String.class);
    }
}
~~~

Ở đây:

- `@LoadBalanced` trên tham số constructor giúp yêu cầu đúng bean builder có marker phù hợp, đặc biệt khi có nhiều builder.
- `baseUrl("http://inventory-service")` dùng service ID, **không phải tên host vật lý của một instance**.
- `clone()` tạo builder riêng trước khi đổi base URL, hạn chế ảnh hưởng đến builder được chia sẻ nếu nhiều client cùng dùng nó.
- `build()` tạo client có thể tái sử dụng cho các request sau.
- `uri("/internal/instance")` thêm path vào base URL; Spring Cloud LoadBalancer xử lý service ID của request.

Nếu chỉ có một builder trong context, việc inject theo kiểu cũng có thể hoạt động. Tuy vậy, đặt qualifier `@LoadBalanced` làm ý định rõ ràng hơn và giảm rủi ro khi sau này thêm client HTTP khác.

### Dùng DTO thay cho String

Trong ứng dụng thật, response nên có hợp đồng dữ liệu rõ ràng. Ví dụ service đích trả:

~~~json
{
  "serviceId": "inventory-service",
  "instanceId": "inv-a",
  "zone": "zone-a"
}
~~~

Có thể định nghĩa DTO:

~~~java
public record InstanceIdentity(
        String serviceId,
        String instanceId,
        String zone
) {}
~~~

Và đọc response:

~~~java
public InstanceIdentity fetchInstanceIdentity() {
    return inventoryRestClient.get()
            .uri("/internal/instance")
            .retrieve()
            .body(InstanceIdentity.class);
}
~~~

DTO này giúp quan sát instance được chọn, nhưng `instanceId` trong response là **thông tin do ứng dụng đích cung cấp**. Nó không nhất thiết trùng hoàn toàn với instance ID trong registry. Cần phân biệt hai định danh nếu dùng chúng để đối chiếu log và metric.

## 6. Chuẩn bị hai replica với SimpleDiscoveryClient

Để kiểm thử local, caller có thể biết trước hai địa chỉ của cùng một service ID. Trong `application.yml` của **ứng dụng caller**:

~~~yaml
spring:
  application:
    name: order-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            inventory-service:
              - uri: http://localhost:8081
                metadata:
                  zone: zone-a
              - uri: http://localhost:8082
                metadata:
                  zone: zone-b
~~~

Dữ liệu này cho biết `inventory-service` có hai instance. Để thử đúng:

1. Khởi chạy bản sao thứ nhất trên cổng `8081`, trả `instanceId=inv-a`.
2. Khởi chạy bản sao thứ hai trên cổng `8082`, trả `instanceId=inv-b`.
3. Bảo đảm cả hai cung cấp endpoint `GET /internal/instance`.
4. Chạy `order-service` có dependency và bean `@LoadBalanced RestClient.Builder`.
5. Gọi `InventoryClient.readInstanceIdentity()` nhiều lần từ controller thử nghiệm.

Ví dụ một endpoint ở caller:

~~~java
package com.example.order.web;

import com.example.order.client.InventoryClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProbeController {

    private final InventoryClient inventoryClient;

    public ProbeController(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }

    @GetMapping("/demo/selected-instance")
    public String selectedInstance() {
        return inventoryClient.readInstanceIdentity();
    }
}
~~~

Có thể gọi:

~~~bash
curl http://localhost:8080/demo/selected-instance
curl http://localhost:8080/demo/selected-instance
curl http://localhost:8080/demo/selected-instance
~~~

Các response có thể lần lượt cho thấy `inv-a` và `inv-b`. Đây là minh họa để quan sát phân phối; **không nên coi thứ tự luân phiên chính xác trong mọi tình huống là cam kết tuyệt đối**. Thuật toán LoadBalancer, trạng thái instance, concurrency và các supplier filter có thể ảnh hưởng kết quả.

Danh sách SimpleDiscoveryClient là **tĩnh**. Nếu bạn dừng `8082` mà không cập nhật cấu hình và không dùng health check, supplier vẫn có thể cung cấp địa chỉ đã chết. `@LoadBalanced` không tự loại replica hỏng hay retry request.

## 7. Bên trong một request: điều gì xảy ra?

Giả sử client gọi `GET /internal/instance` bằng base URL `http://inventory-service`.

~~~mermaid
sequenceDiagram
    participant App as Order application
    participant RC as RestClient
    participant LB as LoadBalancer integration
    participant S as Instance supplier
    participant Inv as Inventory replica
    App->>RC: GET http://inventory-service/internal/instance
    RC->>LB: HTTP request với service ID
    LB->>S: Lấy danh sách ServiceInstance
    S-->>LB: inv-a, inv-b
    LB->>LB: Chọn một ServiceInstance
    LB->>Inv: GET http://host:port/internal/instance
    Inv-->>LB: Response / instance identity
    LB-->>RC: Response
    RC-->>App: Body DTO hoặc String
~~~

Chi tiết đường đi qua interceptor có thể khác theo version và HTTP client được cấu hình, nhưng phân định trách nhiệm vẫn như sau:

- `RestClient` thực hiện API gửi request đồng bộ.
- Tích hợp LoadBalancer lấy **hostname logic trong URI** làm service ID.
- `ServiceInstanceListSupplier` lấy danh sách từ discovery, có thể qua cache hoặc bộ lọc.
- Thuật toán chọn instance xác định đích vật lý.
- HTTP request được gửi tới host/port của instance được chọn.

Nếu URI đã dùng `http://localhost:8081`, đó là một địa chỉ cụ thể; không nên dùng nó trong client có ý định chọn theo service ID. Ngược lại, nếu gọi `http://inventory-service` bằng RestClient thông thường không được tích hợp, hostname có thể được xử lý như một tên DNS bình thường và dẫn tới lỗi phân giải tên.

## 8. Một ứng dụng có cả RestClient trực tiếp và RestClient có LoadBalancer

Trong một hệ thống, bạn có thể cần cả hai kiểu:

- Client **có LoadBalancer**: gọi `inventory-service`, `payment-service` theo service ID.
- Client **trực tiếp**: gọi một endpoint có URL cố định, chẳng hạn API của bên thứ ba hoặc một dịch vụ không dùng service discovery.

Khai báo hai builder có chủ đích:

~~~java
package com.example.order.config;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class HttpClientBuilders {

    @Bean
    @Primary
    RestClient.Builder directRestClientBuilder() {
        return RestClient.builder();
    }

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {
        return RestClient.builder();
    }
}
~~~

`@Primary` đánh dấu builder thông thường là lựa chọn mặc định khi inject chỉ theo kiểu. `@LoadBalanced` giúp lựa chọn builder được tích hợp Spring Cloud LoadBalancer.

Ví dụ inject theo ý định:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.web.client.RestClient;

public SomeClient(
        @LoadBalanced RestClient.Builder internalBuilder,
        @Qualifier("directRestClientBuilder") RestClient.Builder directBuilder) {
    this.inventory = internalBuilder.clone()
            .baseUrl("http://inventory-service")
            .build();

    this.external = directBuilder.clone()
            .baseUrl("https://api.example.com")
            .build();
}
~~~

Đây là **minh họa constructor**, cần đặt trong một class có các field `inventory` và `external` tương ứng. Cách inject này ngăn một URL bên ngoài bị đưa nhầm vào builder đang mong đợi service ID trong môi trường discovery.

Nếu bạn dùng Spring Boot auto-configured `RestClient.Builder` làm builder trực tiếp, không nhất thiết phải tự khai báo `directRestClientBuilder()`. Điều quan trọng là **định nghĩa rõ bean nào trực tiếp, bean nào load balanced**, đặc biệt khi application context có nhiều builder cùng kiểu.

## 9. Timeout và retry không tự xuất hiện vì @LoadBalanced

`@LoadBalanced` giải quyết **việc chọn instance**. Nó không tự cấp một bộ timeout/retry phù hợp với mọi API nghiệp vụ. Một request được cân bằng tải vẫn có thể bị chậm, không kết nối được hoặc nhận mã `5xx`.

Ví dụ cấu hình timeout cho builder thông qua request factory trong ứng dụng dùng client đồng bộ:

~~~java
import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class HttpTimeoutConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder loadBalancedRestClientBuilder() {

        SimpleClientHttpRequestFactory factory =
                new SimpleClientHttpRequestFactory();
        factory.setConnectTimeout(2000);
        factory.setReadTimeout(3000);

        return RestClient.builder().requestFactory(factory);
    }
}
~~~

Các giá trị tính theo millisecond trong ví dụ này: connect timeout 2 giây, read timeout 3 giây. Đây là **cấu hình minh họa cho một ứng dụng**, không phải khuyến nghị mặc định cho mọi dịch vụ. Trong dự án thực, lựa chọn HTTP request factory phù hợp với connection pooling, TLS và nhu cầu throughput.

Đoạn code này là **một phương án thay thế** cho bean builder ở mục 4, không phải bean thứ hai cùng loại `@LoadBalanced` cần đặt cạnh nó.

Về retry:

- Retry có thể yêu cầu bật cơ chế retry tương ứng trong Spring Cloud hoặc một framework resilience; không nên giả định annotation tự retry mọi lỗi.
- Retry có thể chọn lại instance, tùy chính sách và cấu hình của LoadBalancer/retry client.
- Với HTTP `GET` idempotent, retry có kiểm soát thường an toàn hơn.
- Với `POST` tạo đơn hàng hoặc thanh toán, retry không có idempotency key có nguy cơ tạo tác dụng phụ lặp lại.
- Timeout, retry count, backoff và giới hạn thời gian tổng thể cần được thiết kế phối hợp.

Một endpoint không còn instance khả dụng cần được xử lý như lỗi không tìm được đích phục vụ. Loại exception hoặc cách chuyển thành HTTP status ở lớp trên phụ thuộc vào stack và phiên bản, nên không nên dựa vào một chuỗi thông báo lỗi cố định làm hợp đồng ứng dụng.

## 10. ServiceInstanceListSupplier, health và caching ảnh hưởng RestClient thế nào?

RestClient không tự quyết định danh sách instance. Nó dùng LoadBalancer context của service ID; context này có thể có supplier chain riêng:

~~~text
InventoryClient
    |
    v
@LoadBalanced RestClient
    |
    v
LoadBalancer for inventory-service
    |
    v
ServiceInstanceListSupplier
    |
    +--> Discovery client
    +--> Cache (nếu cấu hình)
    +--> Health checks (nếu cấu hình)
    +--> Zone/metadata policy (nếu cấu hình)
    |
    v
ServiceInstance được chọn
    |
    v
HTTP transport
~~~

Hậu quả thực tế:

- Nếu discovery trả danh sách rỗng, RestClient không có đích vật lý để gọi.
- Nếu cache còn chứa instance đã gỡ, request vẫn có thể được gửi tới instance không còn phục vụ.
- Nếu health-check supplier loại một replica, thuật toán chỉ còn chọn trong nhóm được xem là healthy.
- Nếu zone preference đang hoạt động, bạn có thể thấy RestClient chủ yếu chọn instance cùng zone thay vì luân phiên qua tất cả replica.
- Nếu retry chọn lại instance, số lần gọi HTTP thực tế có thể lớn hơn số lần gọi `InventoryClient.readInstanceIdentity()`.

Do đó, khi phân phối không như kỳ vọng, đừng chỉ kiểm tra code RestClient. Hãy xem danh sách từ discovery, supplier chain và thuật toán chọn instance.

## 11. Các lỗi thường gặp và cách xác minh

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không resolve được `inventory-service` | Client dùng builder không load balanced, hoặc thiếu LoadBalancer dependency | Xác minh bean `@LoadBalanced` và injection đúng builder |
| Báo không có instance khả dụng | Service ID không khớp, discovery rỗng, supplier lọc hết | Kiểm tra service ID và danh sách `ServiceInstance` phía caller |
| Chỉ gọi một replica | Discovery chỉ có một entry, health/zone filter, hoặc thuật toán/chính sách | Quan sát candidate list và instance ID response |
| Request vẫn tới port đã tắt | Nguồn tĩnh, snapshot cũ hoặc cache chưa refresh | Kiểm tra registry, discovery, LoadBalancer cache |
| Bean injection bị ambiguous | Có nhiều `RestClient.Builder` không phân biệt | Dùng `@LoadBalanced`, `@Qualifier` hoặc `@Primary` đúng ý định |
| Cấu hình builder không có tác dụng | Class `@Configuration` ngoài component scan hoặc tạo RestClient bằng builder khác | Kiểm tra bean đang được inject vào client |
| Lỗi TLS hoặc connection timeout | Instance trả scheme/port không phù hợp, networking hoặc request factory | Kiểm tra URI của `ServiceInstance` và HTTP client config |
| Retry gây request lặp | Retry policy thiếu giới hạn/idempotency | Ghi attempt count, kiểm tra phương thức và idempotency key |

### Một số lỗi dễ bỏ sót

**Sai service ID:** `spring.application.name` của service đích và tên được caller sử dụng cần nhất quán theo discovery implementation. Ví dụ đăng ký là `stock-service` nhưng caller dùng `inventory-service` sẽ không tìm được instance phù hợp trừ khi có một ánh xạ riêng.

**Nhầm bean:** annotation `@LoadBalanced` trên một builder không làm mọi `RestClient.builder()` được gọi ở nơi khác tự động có LoadBalancer. Mỗi client phải được tạo từ builder đã tích hợp.

**Quên schema URI:** ví dụ `baseUrl("inventory-service")` không tương đương rõ ràng với `baseUrl("http://inventory-service")`. Dùng URI có scheme `http://` hoặc `https://` phù hợp.

**Quên phân biệt lỗi client và server:** `retrieve()` thường xử lý các status HTTP lỗi bằng exception theo chính sách mặc định/cấu hình. Lỗi kết nối không tới server và response `4xx/5xx` đã nhận được là hai nhóm lỗi khác nhau, nên quan sát riêng.

**Thiếu test trên nhiều instance:** một request thành công chỉ chứng minh đã gọi được một replica; nó không chứng minh danh sách nhiều instance hoặc thuật toán cân bằng tải hoạt động đúng.

## 12. Kiểm thử thực hành từ cấu hình tới request

Một bài kiểm tra end-to-end nên có các bước sau.

### Bước 1: Kiểm tra trực tiếp hai replica

~~~bash
curl http://localhost:8081/internal/instance
curl http://localhost:8082/internal/instance
~~~

Hai response cần cho thấy hai instance ID khác nhau.

### Bước 2: Kiểm tra cấu hình caller

Xác minh `application.yml` chứa cả hai URI dưới service ID `inventory-service`. Kiểm tra project có `spring-cloud-starter-loadbalancer`, bean `@LoadBalanced RestClient.Builder` tồn tại, và `InventoryClient` inject bean đó.

### Bước 3: Gọi qua service ID

~~~bash
curl http://localhost:8080/demo/selected-instance
curl http://localhost:8080/demo/selected-instance
curl http://localhost:8080/demo/selected-instance
curl http://localhost:8080/demo/selected-instance
~~~

Ghi `instanceId` của các response. Nếu chỉ thấy một ID, kiểm tra candidate list trước khi kết luận thuật toán không hoạt động.

### Bước 4: Dừng một replica để quan sát lỗi

Dừng cổng `8082` rồi gọi lại. Với nguồn tĩnh và không có health check, một số request có thể lỗi vì địa chỉ vẫn được khai báo. Thử nghiệm này cho thấy **`@LoadBalanced` chọn instance, chứ không tự bảo đảm mọi instance được chọn đang khỏe**.

### Bước 5: Đánh giá timeout và retry

Cấu hình timeout hợp lý, thử trường hợp replica phản hồi chậm, ghi thời gian lỗi và số lần gửi request. Không dùng retry không kiểm soát để che giấu một danh sách instance stale.

### Bước 6: Ghi kết quả

| Kiểm tra | Kỳ vọng |
|---|---|
| Request trực tiếp 8081 và 8082 | Cả hai endpoint trả định danh riêng |
| Request qua `http://inventory-service` | Caller được xử lý qua LoadBalancer |
| Lặp lại nhiều request | Có thể quan sát tập các instance được chọn |
| Dừng một replica với discovery tĩnh | Có thể phát sinh lỗi nếu không có health/discovery refresh |
| Bật đúng timeout | Request bị treo quá lâu được kết thúc theo chính sách |
| Đối chiếu log | Biết service ID, instance thực tế và lý do lỗi |

## 13. Checklist cho production

Trước khi áp dụng `RestClient.Builder` có `@LoadBalanced` vào môi trường thật, kiểm tra:

- **Phiên bản:** Spring Boot/Spring Cloud hỗ trợ `RestClient` và tích hợp LoadBalancer tương thích.
- **Bean:** builder có `@Bean` + `@LoadBalanced`, được component scan nhận diện, inject đúng nơi.
- **Service ID:** hostname logic trong URI đúng với service đã đăng ký.
- **Discovery:** có nguồn `ServiceInstance` và độ mới phù hợp.
- **HTTP:** request factory, connection pooling, TLS, headers, serialization và timeout được xác định.
- **Retry:** giới hạn attempt/backoff, tránh tác dụng phụ lặp lại với phương thức không idempotent.
- **Health:** có cơ chế phát hiện hoặc loại instance không khả dụng.
- **Observability:** có thể đối chiếu service ID, địa chỉ instance được chọn, số attempt, duration và lỗi.
- **Fallback:** hành vi khi không có instance được xử lý rõ ràng ở tầng ứng dụng.
- **Bảo mật:** không log thông tin nhạy cảm; endpoint chẩn đoán nội bộ không được phơi bày không cần thiết.

## 14. Tổng kết

- `RestClient.Builder` mặc định tạo client HTTP đồng bộ nhưng không tự có service discovery/load balancing.
- Bean được đánh dấu `@LoadBalanced` cho phép Spring Cloud tích hợp khả năng chọn `ServiceInstance` khi client gọi URL chứa **service ID**.
- Với `@LoadBalanced RestClient.Builder`, hãy tạo `RestClient` dùng `baseUrl("http://inventory-service")` và tái sử dụng client đã build.
- Khi có cả HTTP client trực tiếp và load balanced, phân biệt bean bằng `@LoadBalanced`, `@Qualifier` hoặc `@Primary`.
- `@LoadBalanced` **không tự cấu hình timeout, retry, health check hay chính sách nghiệp vụ**; những cơ chế đó cần được thiết kế riêng.
- Kiểm chứng end-to-end bằng nhiều replica có endpoint trả instance ID, rồi quan sát cả candidate list và kết quả HTTP.

Một cấu hình `RestClient.Builder` đúng là điểm bắt đầu để caller gọi service theo tên logic. Khả năng giao tiếp ổn định chỉ đạt được khi kết hợp builder đó với discovery chính xác, supplier chain phù hợp, lựa chọn instance, timeout/retry hợp lý và quan sát lỗi đầy đủ.

