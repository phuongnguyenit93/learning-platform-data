# Kết hợp bộ lọc, bộ nhớ đệm và kiểm tra sức khỏe

Trong Spring Cloud LoadBalancer, bộ chọn như `RoundRobinLoadBalancer` không tự khám phá, lưu cache hay kiểm tra sức khỏe từng máy chủ. Nó lấy **danh sách `ServiceInstance` ứng viên** từ `ServiceInstanceListSupplier`, rồi chọn một instance theo chính sách. Khi kết hợp nhiều supplier, chúng tạo thành một chuỗi: lấy dữ liệu từ discovery, tái sử dụng dữ liệu hợp lý, sàng lọc instance và trả danh sách cuối cùng cho bộ chọn.

Bài học thuộc chương **Chuỗi cung cấp bản sao** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Mục tiêu là hiểu cách kết hợp **lọc instance**, **bộ nhớ đệm (cache)** và **kiểm tra sức khỏe (health check)** để giao tiếp bằng service ID ổn định hơn, đồng thời nhận biết khi nào dữ liệu cũ hoặc bộ lọc quá chặt làm mất toàn bộ ứng viên. Kiến thức này áp dụng cho lời gọi qua RestClient, WebClient và OpenFeign có tích hợp Spring Cloud LoadBalancer.

## 1. Vì sao phải kết hợp nhiều nguồn cung cấp instance?

Giả sử ứng dụng `order-service` gọi `catalog-service`. Registry thông báo bốn instance:

| Instance | Zone | Trạng thái tại thời điểm kiểm tra | Ghi chú |
|---|---|---|---|
| `catalog-a` | `zone-a` | Healthy | Cùng zone với caller |
| `catalog-b` | `zone-a` | Unhealthy | Không nên nhận traffic mới |
| `catalog-c` | `zone-b` | Healthy | Có thể dùng khi cần |
| `catalog-d` | `zone-b` | Healthy | Có thể dùng khi cần |

Nếu chỉ lấy danh sách từ registry rồi Round Robin, `catalog-b` vẫn có thể được chọn khi registry chưa kịp cập nhật tình trạng lỗi. Nếu luôn truy vấn registry cho từng request, tải và độ trễ discovery tăng. Nếu lọc chỉ còn `zone-a` mà không cân nhắc sức khỏe, có thể không còn ứng viên trong một số thời điểm.

Một chuỗi supplier giúp thực hiện từng trách nhiệm:

1. **Nguồn gốc danh sách**: `DiscoveryClientServiceInstanceListSupplier` hoặc nguồn tĩnh lấy các instance của service ID.
2. **Cache**: `CachingServiceInstanceListSupplier` giảm tần suất truy vấn nguồn phía sau khi phù hợp.
3. **Health check**: `HealthCheckServiceInstanceListSupplier` theo dõi khả năng phản hồi của các instance được cung cấp.
4. **Lọc hoặc ưu tiên**: các supplier theo zone, hint, metadata hay yêu cầu cụ thể xử lý danh sách trước bước chọn.
5. **Bộ chọn**: `RoundRobinLoadBalancer`, `RandomLoadBalancer` hoặc thuật toán khác chọn một instance từ danh sách kết quả.

Không phải hệ thống nào cũng cần đủ tất cả các lớp. Nếu discovery đã phản ánh sức khỏe chính xác và có cache phù hợp, thêm một bộ health check riêng có thể làm tăng số request và trạng thái cần quản lý.

## 2. Supplier là chuỗi decorator, không phải một danh sách luật độc lập

`ServiceInstanceListSupplier` có thể được bao quanh bởi một supplier khác. Supplier ngoài gọi supplier bên trong, nhận danh sách rồi biến đổi hoặc lưu dữ liệu đó. Vì vậy **thứ tự bao bọc ảnh hưởng đến dữ liệu được cache, được kiểm tra sức khỏe và được lọc**.

Sơ đồ tư duy của một pipeline:

~~~mermaid
flowchart LR
    R["Discovery / danh sách tĩnh"] --> C["Cache danh sách gốc, nếu cần"]
    C --> H["Health check, nếu cần"]
    H --> F["Lọc / ưu tiên theo zone, hint, request"]
    F --> L["LoadBalancer chọn một ServiceInstance"]
    L --> A["RestClient / WebClient / OpenFeign gửi HTTP"]
~~~

Sơ đồ này mô tả các **giai đoạn dữ liệu** theo chiều đọc trái sang phải. Cách hiện thực Java dùng nhiều lớp decorator có thể có thứ tự gọi hàm ngược lại: supplier ngoài cùng được gọi trước và lấy dữ liệu từ delegate bên trong.

Đầu ra của `ServiceInstanceListSupplier` là luồng chứa **danh sách** ứng viên, chẳng hạn `Flux<List<ServiceInstance>>`. Nó chưa phải response chọn server. Sau khi nhận danh sách, bộ chọn mới có thể trả `Response<ServiceInstance>` chứa instance hoặc `EmptyResponse` nếu không có ứng viên.

Một ví dụ trừu tượng:

~~~text
Discovery: [A, B, C, D]
      |
      v
Cache:     [A, B, C, D]  (bản chụp danh sách)
      |
      v
Health:    [A, C, D]     (B thất bại health check)
      |
      v
Zone:      [A]           (ưu tiên zone-a)
      |
      v
Selector:  A
~~~

Trong thực tế, một số supplier ưu tiên vùng hoặc hint **có cơ chế trả lại danh sách ban đầu nếu không có ứng viên khớp**. Do đó không thể suy từ tên “filter” rằng chắc chắn sẽ trả danh sách rỗng khi không có khớp. Cần kiểm tra chính sách fallback của supplier thực tế và phiên bản Spring Cloud đang chạy.

## 3. Nguồn danh sách: discovery và instance tĩnh

Nguồn cơ sở thường là một trong hai kiểu:

- `DiscoveryClientServiceInstanceListSupplier` lấy danh sách từ hệ thống discovery tương thích với Spring Cloud.
- `SimpleDiscoveryClient` có thể cung cấp danh sách instance khai báo bằng cấu hình tĩnh cho `DiscoveryClientServiceInstanceListSupplier` trong môi trường không dùng service registry đầy đủ; ngoài ra ứng dụng có thể tự xây nguồn supplier phù hợp.

Mỗi `ServiceInstance` chứa thông tin như `serviceId`, `host`, `port`, `secure` và `metadata`. Ví dụ một instance logic:

~~~text
serviceId = catalog-service
host      = 192.0.2.21
port      = 8080
secure    = false
metadata  = { zone: "zone-a", version: "v2" }
~~~

`192.0.2.21` là địa chỉ minh họa, không phải máy chủ thật. Khi HTTP client gọi `http://catalog-service/api/items/42`, Spring Cloud LoadBalancer sử dụng `catalog-service` để lấy danh sách instance; sau đó client gọi host/port đã chọn.

Nguồn discovery không phải lúc nào cũng có trạng thái tức thời. Instance mới khởi động có thể chưa xuất hiện; instance vừa dừng có thể vẫn còn trong registry. Cache và health check giải quyết những vấn đề khác nhau phát sinh từ độ trễ này.

## 4. Bộ nhớ đệm: tối ưu chi phí đọc, chấp nhận độ trễ cập nhật

`CachingServiceInstanceListSupplier` lưu danh sách instance nhận được từ nguồn bên trong, giúp các request gần nhau tái sử dụng kết quả. Lợi ích thường gặp là giảm số lần đọc discovery, giảm độ trễ chọn instance và tránh tăng tải registry khi lưu lượng HTTP cao.

Ví dụ, trong khoảng cache còn hiệu lực:

~~~mermaid
sequenceDiagram
    participant R as Request
    participant C as Caching supplier
    participant D as Discovery

    R->>C: Lần gọi 1: catalog-service
    C->>D: Cache miss: lấy danh sách
    D-->>C: [A, B, C]
    C-->>R: [A, B, C]
    R->>C: Lần gọi 2: catalog-service
    C-->>R: Cache hit: [A, B, C]
    Note over C: Cache hết hạn hoặc bị làm mới
    R->>C: Lần gọi 3: catalog-service
    C->>D: Lấy danh sách mới
    D-->>C: [A, C, D]
    C-->>R: [A, C, D]
~~~

### Thời gian sống và giới hạn dung lượng

Cache có **TTL (time to live)** và giới hạn dung lượng phù hợp. TTL ngắn giúp cập nhật danh sách nhanh hơn nhưng tăng số lần truy vấn discovery. TTL dài giảm tải registry nhưng giữ địa chỉ instance vừa hỏng hoặc đã bị gỡ lâu hơn.

Một ví dụ cấu hình tham khảo:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 30s
        capacity: 256
~~~

Tên thuộc tính và giá trị mặc định có thể thay đổi theo phiên bản. Nếu hệ thống discovery đã cache, cần kiểm tra việc dùng thêm LoadBalancer cache có lợi hay đang tạo **hai tầng dữ liệu cũ**. Không tự động chọn TTL thật dài chỉ để tăng tỷ lệ cache hit.

### Cache giữ thông tin đăng ký, không chứng minh instance khỏe

Một entry cache chứa `catalog-b` chỉ cho biết instance từng nằm trong danh sách discovery. Nó không chứng minh `catalog-b` hiện phản hồi tốt. Health check hoặc kết quả thực tế từ HTTP client vẫn cần được xem xét để quyết định có nên gửi traffic.

Ngược lại, health check thành công tại thời điểm T không bảo đảm instance tiếp tục khỏe tại T+1: lỗi mạng, quá tải hoặc restart có thể xuất hiện ngay sau lần kiểm tra. Timeout và xử lý lỗi HTTP vẫn là bắt buộc.

## 5. Health check: loại bỏ ứng viên không đủ khả năng nhận request

`HealthCheckServiceInstanceListSupplier` kiểm tra các instance từ nguồn phía dưới và công bố danh sách phù hợp theo kết quả kiểm tra. Mục tiêu là hạn chế gửi request mới đến instance đang lỗi, ngay cả khi registry chưa gỡ đăng ký.

Quy trình khái quát:

1. Lấy danh sách instance từ delegate.
2. Định kỳ gọi HTTP health endpoint của từng instance theo cấu hình.
3. Theo dõi kết quả và phát danh sách instance được xem là khỏe mạnh.
4. Cập nhật kết quả khi vòng health check tiếp theo hoàn thành hoặc khi nguồn instance thay đổi theo cấu hình.

~~~mermaid
sequenceDiagram
    participant D as Discovery
    participant H as HealthCheck supplier
    participant A as Instance A
    participant B as Instance B
    participant LB as LoadBalancer

    D-->>H: [A, B]
    H->>A: GET /actuator/health
    A-->>H: 200 OK
    H->>B: GET /actuator/health
    B-->>H: Timeout / lỗi
    H-->>LB: Danh sách khỏe: [A]
    LB-->>LB: Chọn A
~~~

Đường dẫn `/actuator/health` chỉ là ví dụ thường dùng. Endpoint thực tế có thể khác, chẳng hạn readiness probe riêng, và phải truy cập được từ ứng dụng caller. Health check không nên phụ thuộc vào endpoint yêu cầu đăng nhập mà client không có quyền sử dụng.

### Liveness, readiness và tính phù hợp với traffic

- **Liveness** trả lời ứng dụng còn chạy hay không.
- **Readiness** trả lời ứng dụng đã sẵn sàng nhận traffic hay chưa.
- **Health của dependency** có thể cần cân nhắc: không phải mọi lỗi dependency đều khiến instance không thể phục vụ tất cả API.

Nếu dùng endpoint quá đơn giản, health check có thể đánh giá khỏe khi instance chưa sẵn sàng. Nếu endpoint quá khắt khe, một dependency phụ bị lỗi có thể làm mọi instance bị loại, gây mất toàn bộ dịch vụ. Hãy xác định tiêu chí phù hợp với loại request đang được định tuyến.

### Health check cũng có chi phí

Giả sử có 100 client ứng dụng, mỗi client kiểm tra 20 instance sau mỗi 10 giây. Hệ thống có thể phát sinh lượng health-check request đáng kể. Cần cân đối chu kỳ, timeout, số instance và khả năng phục vụ của health endpoint. Health check dày đặc không tự động làm hệ thống ổn định hơn.

Đặc biệt, `HealthCheckServiceInstanceListSupplier` đã có cơ chế giữ hoặc phát lại kết quả kiểm tra theo vòng đời của nó. Vì vậy **không mặc định xếp thêm `CachingServiceInstanceListSupplier` vào cùng một chuỗi**. Kiểm tra tài liệu của phiên bản sử dụng và chỉ giữ cả hai nếu biết rõ cache lớp nào, dữ liệu nào và vì sao cần.

## 6. Bộ lọc: chọn danh sách thích hợp cho request hiện tại

Các supplier lọc hoặc ưu tiên instance có thể sử dụng metadata, zone hoặc thông tin của request. Ví dụ:

| Cơ chế | Thông tin dùng để quyết định | Lưu ý |
|---|---|---|
| Ưu tiên zone | Zone của caller và metadata instance | Có thể fallback sang zone khác tùy supplier |
| Hint-based | Hint trong request và metadata | Cần quy định hành vi khi không có hint phù hợp |
| Metadata tự định nghĩa | Version, nhóm khách hàng, năng lực phần cứng | Tránh gửi request tới version thiếu API cần thiết |
| Sticky/session preference | Instance đã phục vụ request trước | Không nên cố giữ instance đã hỏng |
| Health filtering | Kết quả kiểm tra của instance | Có độ trễ giữa các lần kiểm tra |

Không phải mọi bộ lọc đều có cùng hợp đồng. Một bộ lọc **ưu tiên** có thể trả về toàn bộ danh sách khi không có ứng viên phù hợp; một bộ lọc **bắt buộc** tự viết có thể trả danh sách rỗng. Hai hành vi tạo hệ quả nghiệp vụ khác nhau, đặc biệt với yêu cầu cách ly tenant hoặc canary deployment.

### Quy tắc sắp xếp quan trọng: lọc theo request sau cache dùng chung

Giả sử request A cần `version=v1` và request B cần `version=v2`. Nếu lưu cache danh sách đã lọc theo request A bằng một khóa chỉ gồm service ID, request B có thể nhận sai danh sách và không tìm thấy `v2`.

Một thiết kế an toàn hơn:

~~~text
Discovery: [A(v1), B(v2), C(v2)]
             |
             v
Cache theo service ID: [A, B, C]
             |
             +---- Request A (version=v1) ---> [A]
             |
             +---- Request B (version=v2) ---> [B, C]
~~~

Vì vậy, nên để tầng cache dùng chung **nhìn thấy dữ liệu không phụ thuộc vào từng request**, rồi áp dụng các bộ lọc request-specific sau khi lấy snapshot từ cache. Nếu cần cache cả kết quả lọc, khóa cache phải bao gồm đầy đủ các điều kiện tác động đến kết quả và cần cân nhắc nguy cơ bùng nổ số khóa.

## 7. Thiết kế chuỗi supplier theo nhu cầu

Có thể xem ba mẫu sau như các lựa chọn kiến trúc. Chúng minh họa luồng dữ liệu, không bắt buộc áp dụng đồng loạt.

### Mẫu A: Discovery → Cache → Zone preference

Phù hợp khi discovery có trạng thái sức khỏe đáng tin cậy, registry chịu tải nhiều và cần giảm số lần đọc. Tầng cache lưu danh sách đăng ký; tầng zone preference chọn ứng viên gần caller hơn nếu chính sách cho phép.

~~~text
Discovery -> CachingServiceInstanceListSupplier
          -> ZonePreferenceServiceInstanceListSupplier
          -> LoadBalancer
~~~

Mẫu này không chủ động gọi health endpoint ở phía client. Nếu một instance vừa hỏng nhưng vẫn có trong discovery và cache, request có thể lỗi cho đến khi cập nhật hoặc retry thành công.

### Mẫu B: Discovery → Health check → Zone preference

Phù hợp khi registry chưa phản ánh sức khỏe đủ nhanh, và client cần xác minh khả năng phản hồi của từng instance.

~~~text
Discovery -> HealthCheckServiceInstanceListSupplier
          -> ZonePreferenceServiceInstanceListSupplier
          -> LoadBalancer
~~~

Health supplier quản lý vòng kiểm tra và danh sách khỏe mạnh. Không cần thêm cache chỉ vì mặc định “cache luôn tốt”; trước hết phải hiểu kết quả health được giữ thế nào và discovery đã cache chưa.

### Mẫu C: Discovery → Cache → Health check → Lọc theo request

Có thể cân nhắc khi discovery tốn chi phí truy vấn, health check riêng là cần thiết và lọc theo request có điều kiện rõ ràng:

~~~text
Discovery -> Cache dữ liệu discovery
          -> Health check có lịch cập nhật riêng
          -> Lọc theo request (zone / hint / policy)
          -> LoadBalancer
~~~

Đây là một **kiến trúc có điều kiện**, không phải mặc định khuyến nghị cho mọi phiên bản. Cần bảo đảm cache đầu vào không giữ danh sách lỗi quá lâu, health supplier nhận được thay đổi discovery, và kết quả theo request không bị lưu lại trong cache dùng chung. Nếu health supplier đã đủ cơ chế lưu trạng thái, bỏ lớp cache thừa sẽ đơn giản hơn.

## 8. Ví dụ cấu hình bằng `ServiceInstanceListSupplier.builder()`

Spring Cloud LoadBalancer cung cấp builder để kết hợp các supplier phổ biến trong một cấu hình dành riêng cho service ID. Ví dụ dưới đây chọn **Mẫu B**, tránh chồng thêm cache khi health check đã quản lý danh sách kết quả.

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
    name = "catalog-service",
    configuration = CatalogSupplierConfiguration.class
)
class CatalogLoadBalancerRegistration {
}

// Đặt ngoài phạm vi component scan mặc định nếu được đăng ký
// riêng qua @LoadBalancerClient.
@Configuration(proxyBeanMethods = false)
class CatalogSupplierConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogInstanceListSupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withHealthChecks()
            .withZonePreference()
            .build(context);
    }
}
~~~

Ý nghĩa:

- `withDiscoveryClient()` lấy instance từ discovery được cấu hình trong ứng dụng.
- `withHealthChecks()` thêm cơ chế kiểm tra sức khỏe trước khi đưa ứng viên tới selector.
- `withZonePreference()` thêm ưu tiên zone theo chính sách của supplier.
- `build(context)` dựng chuỗi supplier trong context dành cho LoadBalancer.

Các phương thức builder và tùy chọn của chúng cần đối chiếu với phiên bản Spring Cloud đang sử dụng. Cấu hình riêng của `@LoadBalancerClient` không nên vô tình bị component scan đưa thành cấu hình global cho mọi service ID. Có thể đặt lớp này ở package nằm ngoài phạm vi quét component mặc định.

Ví dụ một lựa chọn **Mẫu A** thay health check bằng cache:

~~~java
@Bean
ServiceInstanceListSupplier catalogInstanceListSupplier(
        ConfigurableApplicationContext context) {

    return ServiceInstanceListSupplier.builder()
        .withDiscoveryClient()
        .withCaching()
        .withZonePreference()
        .build(context);
}
~~~

Đây là **phương án thay thế** cho bean ở trên, không phải khai báo bean trùng tên trong cùng context. Khi xây chuỗi, tránh đăng ký hai bean `ServiceInstanceListSupplier` cho cùng một LoadBalancer mà không có chủ đích rõ ràng.

### Cấu hình health endpoint

Nếu ứng dụng đích cung cấp readiness endpoint riêng, có thể cấu hình đường dẫn theo service ID khi phiên bản Spring Cloud hỗ trợ các thuộc tính health check tương ứng:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          catalog-service: /actuator/health/readiness
        interval: 15s
~~~

Đường dẫn và chu kỳ trên là ví dụ cần điều chỉnh theo topology, tốc độ khởi động và tải thực tế. Cần bảo đảm instance đích có endpoint này, quyền truy cập phù hợp và phản hồi đúng trạng thái sẵn sàng phục vụ. Một số hệ thống dùng discovery đã loại unhealthy instance thì không cần cấu hình polling ở phía client.

### Quan hệ với các HTTP client

Khi đã cấu hình chuỗi supplier cho `catalog-service`, request từ một RestClient/WebClient có builder `@LoadBalanced` hoặc OpenFeign tích hợp LoadBalancer sẽ dựa vào danh sách instance mà chuỗi đó cung cấp. Ví dụ:

~~~java
// RestClient với @LoadBalanced RestClient.Builder
catalogRestClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .body(ItemDto.class);

// WebClient với @LoadBalanced WebClient.Builder
catalogWebClient.get()
    .uri("http://catalog-service/api/items/{id}", itemId)
    .retrieve()
    .bodyToMono(ItemDto.class);

// Feign client: @FeignClient(name = "catalog-service")
catalogFeignClient.getItem(itemId);
~~~

Các client khác nhau về mô hình thread và xử lý HTTP response; **chuỗi supplier quyết định tập ứng viên**, còn chính sách của LoadBalancer quyết định instance được chọn. Cấu hình retry và timeout vẫn phải xét riêng cho loại HTTP client thực tế.

## 9. Tình huống bộ lọc và health check tương tác ngoài ý muốn

### Lọc zone trước khi kiểm tra sức khỏe

Giả sử `catalog-a` là instance duy nhất ở `zone-a`, nhưng đang unhealthy; `catalog-c` ở `zone-b` vẫn healthy. Nếu quy tắc zone **bắt buộc** loại hết instance ngoài zone-a và không có fallback, bước health chỉ còn danh sách rỗng.

Để xử lý, cần xác định yêu cầu nghiệp vụ: có được chuyển sang zone-b không? Nếu được, dùng ưu tiên zone có fallback thay vì một bộ lọc loại trừ tuyệt đối. Nếu không được do quy định dữ liệu hoặc độ trễ, việc trả “không có instance phù hợp” là kết quả đúng và cần được xử lý minh bạch.

### Cache một danh sách trước khi instance bị gỡ

Registry đã xóa `catalog-b` nhưng cache chưa hết hạn. Nếu không có health check hoặc kiểm soát lỗi kết nối phù hợp, client có thể tiếp tục chọn `catalog-b`. Giảm TTL chỉ làm nhỏ cửa sổ dữ liệu cũ; không loại bỏ tình huống instance chết ngay sau khi được chọn.

Nên phối hợp TTL với độ trễ cập nhật discovery, kết quả health, timeout và retry có giới hạn, thay vì trông chờ một cơ chế đơn lẻ.

### Tất cả instance bị health check đánh dấu unhealthy

Có thể do hệ thống thực sự lỗi diện rộng, nhưng cũng có thể do sai health path, chứng chỉ TLS, proxy, firewall hoặc timeout. Trước khi kết luận mọi instance chết, hãy thử health endpoint từ cùng môi trường mạng với caller và kiểm tra request/response health thực tế.

Cần biết supplier đang dùng có fallback khi không còn instance healthy hay không. Không tự suy rằng kết quả luôn là rỗng trong tất cả cấu hình và phiên bản.

### Cache sau bộ lọc theo request

Nếu cache không phân biệt hint, zone hoặc thông tin tenant, việc đặt bộ lọc trước cache có thể làm request sau dùng nhầm kết quả request trước. Tránh thiết kế này, đặc biệt khi metadata được dùng để giới hạn dữ liệu hoặc phân tách môi trường.

## 10. Khi danh sách ứng viên cuối cùng rỗng

Nếu chuỗi supplier cuối cùng trả về danh sách rỗng, bộ chọn phổ biến như `RoundRobinLoadBalancer` không thể tạo ra instance đích. Kết quả lựa chọn thường là một response không có server, chẳng hạn `EmptyResponse` với `hasServer() == false`.

~~~mermaid
flowchart TD
    S["Supplier chain trả danh sách"] --> Q{"Có ứng viên?"}
    Q -->|Có| C["Chọn ServiceInstance theo chính sách"]
    C --> H["HTTP client gửi request đến instance"]
    Q -->|Không| E["Response không có server"]
    E --> O["HTTP client báo lỗi chọn instance"]
    O --> R["Ứng dụng quyết định retry, fallback hoặc trả lỗi"]
~~~

Cần phân biệt tình huống này với instance đã chọn nhưng không thể kết nối, và với server đã nhận request nhưng trả HTTP `503`. Không có instance ở bước lựa chọn nghĩa là request chưa được gửi đến instance đích. Thông báo lỗi và metric nên giữ được thông tin đó.

Retry chỉ có tác dụng khi việc chờ thêm hoặc chọn lại có cơ hội tạo ra tập ứng viên khác. Nếu discovery mãi trả danh sách rỗng hoặc bộ lọc cố ý loại toàn bộ ứng viên, retry liên tiếp chỉ tốn tài nguyên. Giới hạn số lần thử, dùng backoff phù hợp, tránh retry lồng nhau giữa client, LoadBalancer và gateway; bảo đảm idempotency nếu request có tác dụng phụ.

## 11. Quan sát pipeline theo từng lớp

Để điều tra đúng nguyên nhân, đừng chỉ ghi “không gọi được service”. Hãy quan sát số instance và trạng thái tại từng giai đoạn.

| Chỉ số / dữ liệu | Câu hỏi cần trả lời |
|---|---|
| Service ID | Đang định tuyến tới dịch vụ nào? |
| Số instance từ discovery | Registry có biết instance nào không? |
| Cache hit/miss, tuổi entry | Có đang dùng danh sách cũ không? |
| Số instance healthy | Bộ health check đang giữ hay loại bao nhiêu instance? |
| Số instance sau mỗi filter | Bộ lọc nào làm số ứng viên thay đổi? |
| Instance được chọn | Request thực tế hướng tới đâu? |
| Thời gian chọn instance | Độ trễ đến từ discovery, cache hay health? |
| Lỗi kết nối, timeout, HTTP status | Lỗi xảy ra trước hay sau bước chọn? |
| Retry attempt, instance lần trước | Retry có chọn lại cùng instance không? |

Nên kết hợp correlation ID/trace ID và log chọn instance với metric request. Không đưa access token, cookie, dữ liệu cá nhân hay thông tin nhạy cảm từ HTTP body vào log. Với service ID hoặc hint có số lượng giá trị biến động lớn, cần giới hạn chiều dữ liệu metric để tránh bùng nổ cardinality.

Có thể dùng hook vòng đời như `LoadBalancerLifecycle` cho các sự kiện chọn instance, đồng thời thêm instrumentation tại nguồn discovery và các wrapper nếu cần quan sát số lượng trước/sau filter. Cách instrument phải tránh tạo thêm một subscription ngoài ý muốn dẫn đến health check hoặc discovery chạy lặp lại.

## 12. Kiểm thử các trạng thái của chuỗi supplier

Không nên chỉ kiểm tra khi mọi instance đều healthy. Bộ kiểm thử nên bao gồm cả chuyển trạng thái và phối hợp giữa các lớp:

| Kịch bản | Kết quả cần xác minh |
|---|---|
| Discovery trả A, B, C | Supplier cuối có tập ứng viên đúng theo policy |
| A và C healthy, B unhealthy | B được loại khi kết quả health đã cập nhật |
| Cache hit | Không truy vấn discovery không cần thiết trong thời gian cache còn hiệu lực |
| B bị gỡ khỏi registry | Sau refresh, B không còn là ứng viên |
| B phục hồi health | B trở lại tập ứng viên sau khi health được cập nhật |
| Không còn instance healthy | Lỗi/fallback tuân thủ hợp đồng, không gửi request tới host ngẫu nhiên |
| Caller ở zone khác | Chính sách ưu tiên hoặc fallback zone hoạt động như thiết kế |
| Request A và B có hint khác nhau | Cache dùng chung không gây rò kết quả lọc giữa hai request |
| Instance chết sau khi được chọn | Timeout/retry có giới hạn, log tách được lỗi kết nối |
| Sai health endpoint | Hệ thống có metric/log giúp phát hiện lỗi cấu hình |

Khi kiểm thử thời gian, tránh dựa vào giả định health check và cache cập nhật tức thì. Hãy xác định chu kỳ refresh, TTL và thời điểm phát danh sách. Với điều kiện bất đồng bộ, cần chờ sự kiện cập nhật có giới hạn thay vì dùng một thời gian ngủ cố định dễ gây test không ổn định.

## 13. Nguyên tắc lựa chọn cấu hình thực tế

- Nếu discovery đã quản lý sức khỏe và cache tốt, bắt đầu với pipeline đơn giản; thêm supplier chỉ khi có vấn đề cụ thể.
- Nếu cần hạn chế truy vấn discovery, sử dụng cache với TTL tương thích tốc độ thay đổi của các instance.
- Nếu registry chậm cập nhật trạng thái unhealthy, cân nhắc health-check supplier với endpoint readiness có ý nghĩa.
- Nếu cần routing theo zone, hint hoặc metadata, xác định rõ **ưu tiên có fallback** hay **lọc bắt buộc**.
- Đặt bước lọc phụ thuộc request sau lớp lưu cache danh sách dùng chung để tránh trộn kết quả giữa request.
- Quan sát danh sách ở từng lớp, lỗi lựa chọn instance và lỗi HTTP, đồng thời cấu hình timeout/retry giới hạn.

Chuỗi `ServiceInstanceListSupplier` là nơi quyết định **instance nào đủ điều kiện được chọn**. Cache, health check và filtering hỗ trợ ba mục tiêu khác nhau: hiệu quả truy xuất, sức khỏe đích và chính sách định tuyến. Hiểu được quan hệ và thứ tự giữa chúng giúp Spring Cloud LoadBalancer lựa chọn instance phù hợp, đồng thời giúp RestClient, WebClient và OpenFeign xử lý tình huống danh sách rỗng một cách có thể giải thích và vận hành được.

