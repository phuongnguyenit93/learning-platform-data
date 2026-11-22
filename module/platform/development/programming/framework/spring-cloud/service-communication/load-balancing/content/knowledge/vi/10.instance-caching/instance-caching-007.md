# Bản sao đã ngừng hoạt động nhưng còn trong cache

Khi gọi một dịch vụ qua **Spring Cloud LoadBalancer**, client không nhất thiết truy vấn lại service registry ở mọi request. Danh sách `ServiceInstance` có thể được lưu trong cache để giảm độ trễ và số lần truy vấn discovery. Đổi lại, trong một khoảng thời gian, cache có thể tiếp tục chứa **bản sao đã dừng, mất kết nối hoặc không còn sẵn sàng nhận request**.

Đây là một tình huống quan trọng của chương **Bộ nhớ đệm bản sao**: registry có thể đã cập nhật rằng instance không còn hoạt động, nhưng LoadBalancer của client vẫn chọn endpoint cũ. Kết quả thường là `Connection refused`, connect timeout hoặc lỗi HTTP tùy vị trí sự cố. Cách xử lý đúng là xác định **danh sách cũ nằm ở đâu**, cơ chế nào làm mới danh sách và biện pháp nào bảo vệ request trong khoảng thời gian dữ liệu chưa đồng bộ.

## 1. Hiện tượng: instance đã chết nhưng vẫn được lựa chọn

Giả sử `order-service` gọi `catalog-service` qua URL logic:

~~~http
GET http://catalog-service/products/42
~~~

Hai bản sao của `catalog-service` được đăng ký:

| Instance | URI | Trạng thái lúc đầu |
|---|---|---|
| `catalog-1` | `http://10.0.1.11:8080` | Đang phục vụ |
| `catalog-2` | `http://10.0.1.12:8080` | Đang phục vụ |

Client đang cache danh sách `[catalog-1, catalog-2]`. Sau đó, tiến trình `catalog-2` dừng đột ngột. Registry loại `catalog-2` nhưng cache ở client chưa hết hạn:

~~~text
Service registry hiện tại:
  catalog-service -> [catalog-1]

Cache của LoadBalancer client:
  catalog-service -> [catalog-1, catalog-2]   (đã cũ)

Đích được LoadBalancer chọn:
  catalog-2 -> 10.0.1.12:8080                (không còn phục vụ)
~~~

LoadBalancer có thể hoàn tất việc **chọn instance** dù việc **thực thi HTTP** tới endpoint đó thất bại. Cơ chế chọn round-robin chỉ làm việc với danh sách được cung cấp; nó không tự kiểm chứng từng kết nối mạng trước mỗi lần chọn.

~~~mermaid
flowchart TD
    A["HTTP client gọi catalog-service"] --> B["Spring Cloud LoadBalancer"]
    B --> C["CachingServiceInstanceListSupplier"]
    C --> D["Cache còn catalog-1 và catalog-2"]
    D --> E["RoundRobin chọn catalog-2"]
    E --> F["HTTP transport kết nối 10.0.1.12:8080"]
    F --> G["Connection refused / timeout"]
    H["Registry hiện tại chỉ còn catalog-1"] -.->|"chưa được làm mới vào cache"| C
~~~

Điều này không đồng nghĩa service registry hoạt động sai: một instance có thể đã biến mất khỏi registry nhưng còn tồn tại trong một tầng dữ liệu cũ khác.

## 2. Các lớp dữ liệu và nơi có thể xuất hiện thông tin cũ

Một hệ thống dùng service discovery thường có nhiều tầng liên quan đến danh sách instance:

| Tầng | Dữ liệu/hoạt động | Vì sao có thể chậm cập nhật? |
|---|---|---|
| Tiến trình server | Thực sự lắng nghe và xử lý request | Có thể dừng hoặc mất mạng tức thì |
| Service registry | Thông tin đăng ký và tình trạng instance | Heartbeat, timeout phát hiện mất kết nối, đồng bộ cụm |
| Discovery client | Trả `getInstances(serviceId)` | Một số implementation có cache cục bộ hoặc chu kỳ refresh riêng |
| `CachingServiceInstanceListSupplier` | Lưu danh sách `ServiceInstance` cho LoadBalancer | TTL chưa hết, chưa có lần truy vấn làm mới |
| Supplier lọc/ưu tiên | Health check, zone, hint hoặc chính sách khác | Có thể dựa trên dữ liệu nguồn cũ hoặc kết quả probe cũ |
| Thuật toán LoadBalancer | Chọn một instance trong danh sách | Chọn từ ứng viên được cung cấp, không thực thi HTTP |
| HTTP client/transport | Kết nối tới URI của instance | Báo lỗi khi endpoint ngừng phục vụ |

`DiscoveryClient.getInstances("catalog-service")` và danh sách cuối cùng do `ServiceInstanceListSupplier` cung cấp **không nhất thiết bằng nhau**. Nếu discovery đã cập nhật nhưng cache LoadBalancer chưa hết hạn, hai kết quả có thể khác nhau. Nếu chính discovery client đang cache dữ liệu cũ, rút ngắn TTL LoadBalancer cũng chưa đủ để có danh sách chính xác.

### Đừng nhầm với connection pool hoặc DNS cache

Một request có thể thất bại vì **danh sách instance stale**, **địa chỉ DNS stale**, hoặc **kết nối HTTP đang tái sử dụng đã bị đóng**. Đây là các cơ chế khác nhau:

- Instance stale: client vẫn nhìn thấy và chọn một endpoint không còn hợp lệ.
- DNS stale: hostname của endpoint được chọn vẫn phân giải ra địa chỉ cũ.
- Connection stale: transport tái sử dụng kết nối đã bị server hoặc thiết bị trung gian đóng.

Thay đổi `spring.cloud.loadbalancer.cache.ttl` chỉ trực tiếp tác động tới **cache danh sách instance của LoadBalancer**; nó không tự thay đổi TTL DNS, connection pool hay chính sách phát hiện lỗi của registry.

## 3. Timeline: vì sao request vẫn chạm instance đã chết?

Xét một kịch bản minh họa. Cache có một mục ghi tại `t = 0s` với TTL 35 giây; registry loại instance sau khi phát hiện nó đã ngừng:

| Thời điểm | Sự kiện | Danh sách mà client có thể thấy |
|---|---|---|
| `t = 0s` | Cache ghi `[catalog-1, catalog-2]` | Hai instance |
| `t = 5s` | `catalog-2` dừng đột ngột | Cache vẫn có hai instance |
| `t = 10s` | Registry đã nhận biết và loại `catalog-2` | Registry chỉ có `catalog-1`, cache vẫn có hai |
| `t = 15s` | Client gửi request và chọn `catalog-2` | Request có thể lỗi kết nối |
| Sau khi mục cache hết TTL | Một lần lấy dữ liệu mới được thực hiện | Có thể chỉ còn `catalog-1`, nếu discovery đã cập nhật |

~~~mermaid
sequenceDiagram
    participant S as catalog-2
    participant R as Service Registry
    participant C as LB Cache
    participant L as LoadBalancer
    participant H as HTTP client
    C->>R: Lấy instance lúc đầu
    R-->>C: [catalog-1, catalog-2]
    Note over S: Tiến trình ngừng
    R->>R: Phát hiện / loại catalog-2
    H->>L: Gọi catalog-service
    L->>C: Xin danh sách ứng viên
    C-->>L: [catalog-1, catalog-2] (còn TTL)
    L-->>H: Chọn catalog-2
    H--xS: Kết nối thất bại
    Note over C,R: Sau khi cache hết hạn và lấy lại danh sách
    C->>R: Truy vấn lại
    R-->>C: [catalog-1]
~~~

**35 giây ở đây là TTL mặc định của LoadBalancer cache theo tài liệu Spring Cloud Commons hiện hành, không phải thời gian bảo đảm tối đa để loại một instance chết.** TTL được tính từ thời điểm mục được ghi vào cache. Thời điểm refresh còn phụ thuộc cách cache được truy cập; nếu discovery client hoặc registry vẫn có dữ liệu cũ lúc cache nạp lại, instance chết có thể tiếp tục xuất hiện.

Thực tế, khoảng thời gian nhìn thấy instance stale chịu ảnh hưởng tổng hợp của phát hiện lỗi, đồng bộ registry, cache discovery, cache LoadBalancer và lịch health check. Các giai đoạn có thể chồng lấn; không nên coi phép cộng các TTL là một cam kết thời gian chính xác.

## 4. Spring Cloud LoadBalancer cache những gì?

`CachingServiceInstanceListSupplier` là supplier được dùng để **cache danh sách instance** mà supplier phía dưới trả về. Nó phục vụ LoadBalancer bằng dữ liệu đã lưu khi phù hợp, giảm việc truy vấn discovery liên tục.

Trong Spring Cloud Commons, có hai lựa chọn triển khai cache thường gặp:

- **Caffeine-backed cache:** được sử dụng khi dependency `com.github.ben-manes.caffeine:caffeine` có trên classpath.
- **`DefaultLoadBalancerCache`:** được cung cấp khi không có Caffeine, cùng với hỗ trợ từ `spring-cloud-starter-loadbalancer`.

Các thuộc tính cấu hình chung:

| Thuộc tính | Mặc định được tài liệu hiện hành mô tả | Tác dụng |
|---|---|---|
| `spring.cloud.loadbalancer.cache.enabled` | `true` | Bật/tắt cơ chế LoadBalancer cache |
| `spring.cloud.loadbalancer.cache.ttl` | `35s` | Thời gian tồn tại của mục cache tính từ lúc ghi |
| `spring.cloud.loadbalancer.cache.capacity` | `256` | Dung lượng khởi tạo của cache, không phải số instance tối đa trong một service |
| `spring.cloud.loadbalancer.cache.caffeine.spec` | Không đặt sẵn | Cấu hình Caffeine tùy chọn khi Caffeine có mặt |

Các giá trị mặc định phụ thuộc phiên bản thư viện. Khi dùng Spring Cloud release train cụ thể, cần đối chiếu configuration metadata và tài liệu của phiên bản đó.

Một cấu hình minh họa để giảm thời gian lưu dữ liệu:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: true
        ttl: 10s
        capacity: 256
~~~

`ttl: 10s` nghĩa là các mục cache của LoadBalancer hết hạn sớm hơn so với mặc định. Nó không tự buộc registry loại instance ngay lập tức và cũng không làm cho HTTP client gửi lại request đã thất bại.

### Caffeine spec có thể ghi đè các thuộc tính chung

Nếu sử dụng Caffeine và cấu hình trực tiếp `spring.cloud.loadbalancer.cache.caffeine.spec`, spec này có quyền ưu tiên so với các thuộc tính LoadBalancer cache chung như `ttl` và `capacity`. Vì vậy, không nên đồng thời viết một spec với `expireAfterWrite=30s` rồi kỳ vọng `cache.ttl: 10s` sẽ thắng.

Ví dụ cấu hình **thay thế**, không phải bổ sung cho cấu hình TTL ở trên:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        caffeine:
          spec: expireAfterWrite=10s,initialCapacity=256,maximumSize=1024
~~~

Cấu hình này chỉ có ý nghĩa khi Caffeine đang được sử dụng. Kiểm tra các phần tử hợp lệ của `CaffeineSpec` theo phiên bản Caffeine trong dự án.

## 5. Supplier chain và vị trí cache

`ServiceInstanceListSupplier` có thể được ghép thành chuỗi: nguồn discovery, cache, health check, ưu tiên zone, hint hoặc chính sách tùy biến. Với một chuỗi có cache bình thường, Spring Cloud khuyến nghị đặt `CachingServiceInstanceListSupplier` **ngay sau supplier lấy instance từ mạng, trước các supplier lọc khác**.

~~~text
Nguồn discovery
   ↓
CachingServiceInstanceListSupplier
   ↓
Zone / hint / bộ lọc khác (nếu được cấu hình)
   ↓
LoadBalancer chọn một ServiceInstance
   ↓
HTTP client gọi host:port
~~~

Vị trí đó giúp cache danh sách chung của service ID. Nếu cache đặt sau một bước lọc theo dữ liệu request (như hint), kết quả được lưu có thể mang điều kiện của một request cụ thể, gây sai lệch cho các request tiếp theo khi cache key không phân biệt những điều kiện ấy.

### Ví dụ cấu hình chuỗi supplier

Với ứng dụng có `DiscoveryClient` phù hợp và phiên bản Spring Cloud cung cấp builder tương ứng:

~~~java
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@LoadBalancerClient(
        name = "catalog-service",
        configuration = CatalogLoadBalancerConfiguration.class
)
class CatalogLoadBalancerRegistration {}

// Để lớp cấu hình chuyên biệt này ngoài phạm vi component scan chính,
// hoặc không chú thích @Configuration để chỉ nạp trong child context.
class CatalogLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier serviceInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withCaching()
                .build(context);
    }
}
~~~

Ví dụ này cho thấy nơi cache được nối vào supplier. Nó **không** cung cấp một registry hoàn chỉnh; ứng dụng phải có dependency LoadBalancer và một nguồn `ServiceInstance` phù hợp. Để tránh tạo nhiều lớp cache không cần thiết, không nên tự thêm `.withCaching()` nếu đã dùng cấu hình tương ứng hoặc integration khác đã quản lý cache theo yêu cầu.

## 6. Caching kép: registry đúng nhưng client vẫn thấy bản sao cũ

Một số discovery client, ví dụ `EurekaDiscoveryClient`, tự có cache hoặc cơ chế đồng bộ dữ liệu từ registry. Nếu LoadBalancer tiếp tục bật cache trên kết quả đó, hệ thống có thể có **hai tầng giữ dữ liệu**:

~~~mermaid
flowchart TD
    A["Service registry<br/>catalog-1"]
    B["Discovery client cache<br/>catalog-1, catalog-2 (cũ)"]
    C["LoadBalancer cache<br/>catalog-1, catalog-2 (cũ)"]
    D["LoadBalancer chọn catalog-2"]
    E["HTTP kết nối lỗi"]
    A -->|"làm mới có độ trễ"| B
    B -->|"làm mới có TTL riêng"| C
    C --> D --> E
~~~

Ngay cả khi giảm TTL LoadBalancer xuống 5 giây, cache mới có thể đọc lại `[catalog-1, catalog-2]` từ discovery client vì tầng đó chưa cập nhật. Ngược lại, chỉnh tham số refresh của registry nhưng giữ một TTL LoadBalancer quá dài cũng trì hoãn việc thấy danh sách mới.

Tài liệu Spring Cloud khuyến nghị **tắt LoadBalancer cache khi discovery client đã thực hiện caching** để tránh double caching trong trường hợp không cần thiết:

~~~yaml
spring:
  cloud:
    loadbalancer:
      cache:
        enabled: false
~~~

Cấu hình trên chỉ tắt cache LoadBalancer. Nó **không vô hiệu hóa cache nội bộ của Eureka hoặc các discovery client khác**. Trong production, cần đo số lượng truy vấn và độ trễ thực tế trước khi quyết định bỏ một lớp cache, tránh gây tải không cần thiết lên registry.

## 7. Health check có loại được instance stale ngay không?

`HealthCheckServiceInstanceListSupplier` có thể kiểm tra định kỳ endpoint của các `ServiceInstance` do supplier phía dưới cung cấp. Nếu một endpoint không trả về trạng thái khỏe theo tiêu chí kiểm tra, supplier có thể loại nó khỏi tập ứng viên trước khi LoadBalancer chọn.

Tuy nhiên, cần hiểu ba giới hạn:

1. **Health check chạy theo chu kỳ.** Instance vừa chết vẫn có thể được chọn trước khi lần kiểm tra tiếp theo phát hiện lỗi.
2. **Health check cần có nguồn instance đủ mới.** Nếu supplier phía dưới không phát danh sách cập nhật, cần cấu hình cơ chế refetch trong trường hợp đó.
3. **Hành vi mặc định khi không còn instance khỏe là fallback về toàn bộ danh sách vừa truy xuất.** Theo tài liệu Spring Cloud, `HealthCheckServiceInstanceListSupplier` trả các instance khỏe, **nhưng nếu không có instance khỏe nào thì trả lại toàn bộ danh sách được cung cấp**. Vì vậy, nó không mặc định là một bộ lọc fail-closed khi mọi endpoint đều thất bại.

Điểm thứ ba dễ bị hiểu sai: khi cả `catalog-1` lẫn `catalog-2` đều fail health check, hệ thống có thể vẫn chọn một instance từ danh sách nguồn. Nếu nghiệp vụ yêu cầu tuyệt đối không định tuyến đến endpoint không khỏe, cần chính sách tùy biến và cách xử lý không có ứng viên phù hợp.

### Cấu hình health check minh họa

Với ứng dụng được cấu hình sử dụng `HealthCheckServiceInstanceListSupplier`, các thuộc tính sau điều chỉnh việc kiểm tra và làm mới:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        interval: 10s
        path:
          default: /actuator/health
        refetch-instances: true
        refetch-instances-interval: 15s
~~~

`refetch-instances: true` hữu ích khi delegate không chủ động phát danh sách mới trong khi nguồn instance có thể thay đổi. Thuộc tính này không thay thế việc cấu hình supplier health check; một số tích hợp cần khai báo chain riêng bằng `.withHealthChecks()` (reactive) hoặc `.withBlockingHealthChecks()` (blocking).

Ví dụ builder cho trường hợp dùng discovery client:

~~~java
@Bean
ServiceInstanceListSupplier healthCheckedSupplier(
        ConfigurableApplicationContext context) {
    return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withHealthChecks()
            .build(context);
}
~~~

Đoạn code là phương án **thay thế** cho chain cache ở mục trước, không phải bean thứ hai cần khai báo song song. `HealthCheckServiceInstanceListSupplier` có cơ chế giữ dữ liệu dựa trên Reactor `Flux.replay()`, vì vậy nên cân nhắc **không bọc thêm `CachingServiceInstanceListSupplier`** khi dùng cơ chế này. Nếu health endpoint là `/actuator/health`, server cần cung cấp endpoint đó, ví dụ qua Spring Boot Actuator.

## 8. Vì sao retry và timeout không tự làm sạch cache?

Khi LoadBalancer chọn `catalog-2`, HTTP client mới thực hiện kết nối. Nếu kết nối thất bại, dữ liệu cache không tự động được cập nhật chỉ vì đã xuất hiện một exception.

Phân biệt rõ trách nhiệm:

| Cơ chế | Vấn đề nó xử lý | Điều nó không tự bảo đảm |
|---|---|---|
| Cache TTL | Giới hạn thời gian giữ một danh sách instance | Instance cũ biến mất ngay khi dừng |
| Service discovery | Cung cấp danh sách từ registry | Mọi request có dữ liệu tức thời |
| Health check | Đánh giá endpoint theo chu kỳ | Không bao giờ chọn endpoint đã chết |
| Retry | Thử lại một lời gọi khi lỗi phù hợp chính sách | Tự loại instance khỏi mọi cache/discovery |
| Connect/response timeout | Giới hạn thời gian chờ HTTP | Tự chọn một instance khỏe hơn |
| Circuit breaker | Hạn chế tiếp tục thực thi lời gọi đang có nhiều lỗi | Cập nhật trực tiếp danh sách instance trong registry |

Một retry được cấu hình đúng có thể thử lại request sau `Connection refused` hoặc một số timeout, đôi khi chọn instance khác. Nhưng nếu cache còn hai instance và chính sách retry không tránh được `catalog-2`, lần thử sau vẫn có thể chọn cùng endpoint hỏng.

Với request có tác dụng phụ, ví dụ thanh toán hay tạo đơn hàng, retry chỉ nên thực hiện khi đã xem xét idempotency và điều kiện lỗi. Khi timeout, request đầu tiên có thể đã đến server và được xử lý dù client không nhận được response.

### Lỗi "không có instance" khác lỗi "instance đã chết"

- **Không có instance:** supplier trả danh sách rỗng; LoadBalancer không có endpoint để chọn. Adapter có thể tạo lỗi phía client trước khi thực thi HTTP.
- **Có instance stale:** supplier trả một endpoint không còn hoạt động; việc chọn có thể thành công nhưng kết nối HTTP thất bại.
- **Backend trả HTTP 5xx:** request đã đến server hoặc proxy và nhận response lỗi; cần đối chiếu log/trace để phân biệt lỗi backend và lỗi tầng trung gian.

Chỉ nhìn mã HTTP status không đủ để kết luận lỗi nằm ở cache. Ví dụ lỗi 503 có thể được tạo khi không có instance, nhưng cũng có thể do một proxy hoặc server thực sự trả về.

## 9. Điều chỉnh TTL: cân bằng giữa độ mới và tải truy vấn

TTL ngắn giúp danh sách instance được lấy lại thường xuyên hơn khi có request, nhưng có thể tăng số lần truy vấn discovery. TTL dài giảm tải registry nhưng kéo dài thời gian một danh sách cũ còn được sử dụng.

| Tiêu chí | TTL ngắn | TTL dài |
|---|---|---|
| Khả năng nhìn thấy thay đổi sau lần đọc cache mới | Thường sớm hơn | Thường chậm hơn |
| Số lần lấy lại danh sách | Có thể cao hơn | Có thể thấp hơn |
| Nguy cơ chọn instance đã dừng khi cache chưa cập nhật | Thường giảm | Có thể tăng |
| Chi phí truy vấn nguồn | Tăng nếu không có cache nguồn | Giảm |
| Tác động nếu discovery nguồn vẫn stale | Vẫn có thể lấy lại dữ liệu cũ | Vẫn có thể lấy lại dữ liệu cũ |

Không có một TTL tối ưu cho mọi hệ thống. Cần xét chu kỳ triển khai/scale, tốc độ phát hiện lỗi ở registry, số lượng client và request rate.

**Ví dụ:** nếu triển khai có nhiều instance bị thay thế liên tục, TTL 10 giây có thể là điểm thử nghiệm hợp lý. Đây chỉ là giá trị để đo kiểm, không phải khuyến nghị mặc định cho production. Nếu registry đã cache và refresh theo chu kỳ dài hơn, rút TTL LoadBalancer thấp hơn chu kỳ đó có thể đem lại rất ít lợi ích.

Không nên xem `capacity: 256` như giới hạn số instance của `catalog-service`; đây là tham số capacity của cache, không phải chính sách chọn tối đa 256 server.

## 10. Quan sát sự cố để tìm chính xác tầng dữ liệu stale

Một lộ trình chẩn đoán nên đi từ trạng thái thực đến danh sách client sử dụng:

1. Xác minh tiến trình `catalog-2` đã dừng hay chỉ tạm thời không đáp ứng health check.
2. Kiểm tra registry hiện còn thông tin `catalog-2` hay không; ghi lại thời điểm cập nhật.
3. Từ client, kiểm tra `DiscoveryClient.getInstances("catalog-service")` tại thời điểm sự cố.
4. Kiểm tra danh sách `ServiceInstance` mà supplier đưa tới LoadBalancer, đặc biệt lớp cache và health check.
5. Ghi lại instance ID, URI được chọn, exception HTTP và thời điểm request.
6. Kiểm tra TTL, cấu hình Caffeine (nếu có), nguồn discovery có cache riêng và các chu kỳ refresh.
7. Chỉ sau khi xác định tầng gây stale mới thay đổi TTL, bật health check hoặc điều chỉnh retry.

Ví dụ đọc danh sách `DiscoveryClient` trong một ứng dụng Spring:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
class DiscoveryInspector {

    private final DiscoveryClient discoveryClient;

    DiscoveryInspector(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    void logCatalogInstances() {
        List<ServiceInstance> instances =
                discoveryClient.getInstances("catalog-service");

        System.out.println("Discovery count=" + instances.size());
        instances.forEach(instance ->
                System.out.println(instance.getInstanceId() +
                        " => " + instance.getUri()));
    }
}
~~~

Đoạn code đọc từ `DiscoveryClient`, **không phải đọc trực tiếp cache nội bộ của `CachingServiceInstanceListSupplier`**. Nếu cần chẩn đoán sâu hơn, có thể bổ sung logging/observation ở supplier chain hoặc test được kiểm soát để so sánh danh sách trước và sau cache.

### Những tín hiệu cần theo dõi

| Tín hiệu | Mục đích |
|---|---|
| Service ID và instance ID được chọn | Xác định endpoint thực sự bị gọi |
| Danh sách từ discovery so với danh sách supplier | Xác định tầng dữ liệu lệch |
| Thời điểm instance ngừng và registry cập nhật | Đo khoảng chậm phát hiện |
| Tuổi của mục cache hoặc thời điểm refresh | Đánh giá TTL có phù hợp |
| `Connection refused`, connect timeout, response timeout | Phân loại lỗi transport |
| Tỉ lệ retry, instance được chọn ở mỗi lần thử | Đánh giá retry có tránh endpoint lỗi |
| LoadBalancer/HTTP metrics theo service | Theo dõi xu hướng lỗi trước và sau thay đổi |

Khi cần metrics cho các lần gọi cân bằng tải, Spring Cloud có hỗ trợ tích hợp Micrometer qua cấu hình `spring.cloud.loadbalancer.stats.micrometer.enabled` nếu có `MeterRegistry`. Nội dung chi tiết và nhãn metric phụ thuộc phiên bản/framework integration. Log nên có trace/correlation ID nhưng tránh ghi token, cookie hoặc payload nhạy cảm.

## 11. Thực hành tái hiện và xác minh cách khắc phục

Thử nghiệm có thể làm bằng một registry động như Eureka/Consul hoặc một supplier giả lập cho phép thay đổi danh sách. Với danh sách cố định trong `SimpleDiscoveryClient`, dừng server không tự xóa instance khỏi cấu hình, nên trường hợp này chủ yếu minh họa một **instance không còn khỏe** chứ không tái hiện được việc registry loại rồi cache giữ stale.

### Kịch bản thực hành

1. Chạy `catalog-service` với hai instance `catalog-1` và `catalog-2`; mỗi instance phục vụ `GET /whoami` trả instance ID.
2. Khởi động `order-service` với HTTP client tích hợp LoadBalancer (`RestClient`, `WebClient` hoặc OpenFeign) gọi bằng service ID `catalog-service`.
3. Chờ registry và cache có đủ hai instance; gửi nhiều request và ghi lại instance nào được chọn.
4. Dừng đột ngột `catalog-2`, theo dõi thời điểm registry phát hiện và loại instance.
5. Tiếp tục gửi request trong lúc cache chưa cập nhật; ghi nhận các lần chọn endpoint cũ và exception.
6. Chờ refresh và xác nhận supplier cuối cùng chỉ còn `catalog-1` trong danh sách ứng viên.
7. Thử thay đổi `spring.cloud.loadbalancer.cache.ttl` ở một lần chạy độc lập; so sánh độ dài khoảng stale và tần suất truy vấn.
8. Nếu dùng Eureka hoặc discovery client đã cache, thử tắt riêng LoadBalancer cache và quan sát xem lỗi còn đến từ cache discovery hay không.
9. Bổ sung health check hoặc retry nếu cần, rồi đánh giá khả năng xử lý request lỗi trong lúc registry chưa đồng bộ.

Không nên cố định kỳ vọng rằng “sau đúng 10 giây sẽ hết lỗi”. Kết quả bị ảnh hưởng bởi heartbeat, lịch cập nhật cache, thời điểm ghi cache và điều kiện của HTTP transport.

### Bảng kiểm kết quả mong đợi

| Tình huống | Kết quả cần quan sát |
|---|---|
| Registry còn instance đã chết | Discovery và cache có thể vẫn cung cấp instance đó |
| Registry đã loại nhưng LoadBalancer cache còn TTL | Discovery mới và danh sách supplier có thể khác nhau |
| Cache hết hạn, discovery đã cập nhật | Supplier lấy lại danh sách không còn instance chết |
| TTL LoadBalancer giảm nhưng discovery cache chưa cập nhật | Client vẫn có thể thấy endpoint cũ |
| Health check phát hiện một instance chết, còn instance khỏe khác | Supplier health check có thể ưu tiên danh sách khỏe |
| Mọi instance đều thất bại health check | Theo fallback mặc định, supplier health check có thể trả toàn bộ danh sách nguồn |
| Supplier trả danh sách rỗng | LoadBalancer không có instance hợp lệ để chọn |

## 12. Biện pháp vận hành cho hệ thống thực tế

Để giảm tỉ lệ request tới instance đã ngừng hoạt động, nên xử lý theo nhiều tầng:

- **Dừng dịch vụ có kiểm soát:** chuyển trạng thái không sẵn sàng hoặc hủy đăng ký trước khi tắt tiến trình; chừa thời gian cho đường truyền và discovery cập nhật, đồng thời hoàn tất request đang xử lý.
- **Theo dõi registry và discovery:** xác minh heartbeat, thời gian phát hiện lỗi, refresh và độ mới của danh sách thực tế.
- **Tối ưu cache:** chọn TTL theo số liệu, tránh hai lớp cache không cần thiết và đặt caching supplier đúng vị trí trong chain.
- **Health check có chủ đích:** dùng khi cần phát hiện endpoint chưa bị registry loại; hiểu rõ nhược điểm của chu kỳ kiểm tra và fallback khi không còn instance khỏe.
- **Timeout/retry phù hợp:** giới hạn thời gian request bị kẹt và thử lại có điều kiện, đồng thời bảo vệ các thao tác không idempotent.
- **Quan sát đủ hai giai đoạn:** ghi nhận cả `ServiceInstance` đã chọn lẫn kết quả HTTP để phân biệt lỗi dữ liệu danh sách với lỗi kết nối.

Nếu chỉ tăng số lần retry mà không cải thiện độ mới của danh sách, client có thể tiếp tục chọn instance đã chết. Nếu chỉ giảm TTL mà registry vẫn báo instance cũ, kết quả cũng có thể không thay đổi đáng kể. Cần tìm đúng nguồn dữ liệu stale trước khi điều chỉnh.

**Điều cần nhớ:** cache của Spring Cloud LoadBalancer là cơ chế tối ưu việc cung cấp danh sách `ServiceInstance`, không phải bản ghi sức khỏe thời gian thực. Một instance ngừng hoạt động có thể tiếp tục được chọn trong khoảng dữ liệu chưa cập nhật. Sự ổn định đến từ phối hợp discovery, cache, health filtering, timeout/retry và quan sát trạng thái của từng tầng.

**Tài liệu tham khảo chính thức:**

- [Spring Cloud Commons – Spring Cloud LoadBalancer Caching](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#spring-cloud-loadbalancer-caching)
- [Spring Cloud Commons – Instance Health-Check for LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html#instance-health-check-for-loadbalancer)
- [Spring Cloud Commons – Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html)

