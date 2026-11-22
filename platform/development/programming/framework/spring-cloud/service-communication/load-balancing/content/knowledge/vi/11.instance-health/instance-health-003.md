# Đường dẫn kiểm tra, chu kỳ và thời điểm bắt đầu

Trong hệ thống dùng **Spring Cloud LoadBalancer**, danh sách `ServiceInstance` mà discovery cung cấp có thể chứa các bản sao đã dừng, đang khởi động hoặc chưa sẵn sàng xử lý request. Để giảm khả năng gửi lời gọi tới bản sao không khỏe, caller có thể dùng `HealthCheckServiceInstanceListSupplier` để thăm dò endpoint sức khỏe của các instance và chỉ đưa các instance được đánh giá khỏe vào tập chọn.

Ba thiết lập quyết định phần lớn hành vi thăm dò là:

- **Đường dẫn kiểm tra**: HTTP endpoint nào của dịch vụ đích được gọi?
- **Thời điểm bắt đầu** (`initial-delay`): scheduler đợi bao lâu trước khi bắt đầu vòng kiểm tra đầu tiên?
- **Chu kỳ kiểm tra** (`interval`): sau bao lâu scheduler chạy lại việc kiểm tra?

Chúng được cấu hình dưới tiền tố `spring.cloud.loadbalancer.health-check`, không phải dưới cấu hình HTTP timeout của RestClient/WebClient/OpenFeign. Bài này giải thích cách các thuộc tính phối hợp với discovery, bộ lọc instance, cơ chế retry và quan sát lỗi, rồi xây dựng một ví dụ có thể thử với nhiều bản sao.

## 1. Health check nằm ở đâu trong quá trình chọn instance?

Trong mô hình client-side load balancing, caller gửi request đến một **service ID** như `inventory-service`. Một nguồn discovery cung cấp các instance có host, port và metadata. Chuỗi `ServiceInstanceListSupplier` có thể lọc danh sách rồi thuật toán như Round Robin hoặc Random mới chọn một instance.

~~~mermaid
flowchart LR
    A["RestClient / WebClient / OpenFeign"] --> B["Service ID: inventory-service"]
    D["SimpleDiscoveryClient / Registry"] --> S["ServiceInstanceListSupplier"]
    S --> H["HealthCheckServiceInstanceListSupplier"]
    H -->|"Danh sách có thể chọn"| L["RoundRobin / Random"]
    B --> L
    L --> I["ServiceInstance"]
    I --> T["HTTP request tới bản sao"]
~~~

`HealthCheckServiceInstanceListSupplier` chủ động gửi các request kiểm tra sức khỏe đến instance được delegate cung cấp. Khi danh sách được cập nhật, thuật toán chỉ nhìn thấy danh sách mà supplier trả về, không tự thực hiện phép thử HTTP cho mỗi request nghiệp vụ.

Điểm cần nhớ:

1. **Discovery** cho biết những instance nào được đăng ký hoặc đã biết.
2. **Health check ở caller** ước lượng những instance nào đang phản hồi endpoint kiểm tra.
3. **LoadBalancer** chọn một instance từ danh sách sau xử lý.
4. **HTTP client** thực sự kết nối và gửi request nghiệp vụ.

Một instance vừa trả health check thành công vẫn có thể lỗi ngay sau đó. Ngược lại, một request health check lỗi không tự chứng minh mọi API của instance đã hỏng. Health check làm giảm rủi ro chứ không thay thế timeout, retry có kiểm soát hay quan sát lỗi.

## 2. Ba thuộc tính cơ bản và giá trị mặc định

Theo tài liệu thuộc tính Spring Cloud Commons, các giá trị mặc định phổ biến là:

| Thuộc tính | Mặc định | Ý nghĩa |
|---|---|---|
| `spring.cloud.loadbalancer.health-check.path` | `/actuator/health` nếu không cấu hình | Đường dẫn HTTP được kiểm tra trên instance |
| `spring.cloud.loadbalancer.health-check.initial-delay` | `0` | Khoảng trì hoãn trước vòng kiểm tra được lập lịch đầu tiên |
| `spring.cloud.loadbalancer.health-check.interval` | `25s` | Khoảng thời gian giữa các vòng scheduler |
| `spring.cloud.loadbalancer.health-check.port` | Cổng của `ServiceInstance` | Ghi đè cổng dành cho request kiểm tra nếu cần |

Cấu hình ví dụ trong **ứng dụng caller**:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 2s
        interval: 10s
        path:
          default: /actuator/health
          inventory-service: /internal/ready
~~~

Ý nghĩa:

- Nếu có health-check supplier cho `inventory-service`, nó sẽ kiểm tra `/internal/ready` trên các instance inventory.
- Nếu có health-check supplier cho một service khác mà không được khai báo riêng, đường dẫn mặc định là `/actuator/health`.
- Scheduler của health-check supplier dùng `initial-delay` và `interval` phù hợp với cấu hình có hiệu lực.
- Các thuộc tính này **không tự tạo health-check supplier**. Nếu chỉ thêm YAML mà không tạo supplier hoặc chọn preset tương ứng, các instance vẫn có thể được chọn mà không qua bước thăm dò.

Các giá trị và tên thuộc tính cần đối chiếu với phiên bản Spring Cloud Commons đang dùng. Khi dùng Boot/Cloud BOM, giữ phiên bản tương thích trước khi chạy lab.

## 3. Cấu hình đường dẫn kiểm tra theo service ID

Thuộc tính `health-check.path` có cấu trúc dạng map, trong đó khóa `default` là đường dẫn dự phòng và khóa khác là service ID cụ thể:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        path:
          default: /actuator/health
          inventory-service: /internal/ready
          payment-service: /actuator/health/readiness
          catalog-service: /internal/health
~~~

Khi service ID đang được kiểm tra là `payment-service`, request kiểm tra dùng `/actuator/health/readiness`. Service ID không có entry riêng sẽ dùng `default`.

**Không nhầm service ID của đích với `spring.application.name` của caller.** Ví dụ caller có `spring.application.name: order-service` nhưng gọi `http://inventory-service` qua RestClient được đánh dấu `@LoadBalanced`. Khi đó khóa cần khai báo trong map là `inventory-service`.

Đường dẫn thực tế phải tồn tại tại dịch vụ đích. Nếu endpoint bị bảo vệ và trả `401` hoặc `403` cho bộ kiểm tra, instance có thể bị đánh giá không khỏe dù API nghiệp vụ vẫn chạy tốt. Nếu dùng Spring Boot Actuator và chọn `/actuator/health`, hãy thêm `spring-boot-starter-actuator` vào **ứng dụng đích**, hoặc tự triển khai endpoint tương đương.

Ví dụ dependency cho inventory-service:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
~~~

Đường dẫn `/actuator/health/readiness` chỉ hoạt động khi ứng dụng Spring Boot cấu hình và công bố các health probe tương ứng. Không giả định mọi phiên bản hoặc mọi môi trường đều có sẵn endpoint này.

### Khi dùng cổng management riêng

Giả sử inventory API chạy tại `8081`, nhưng endpoint sức khỏe chỉ được mở ở cổng management `9091`. Request `http://localhost:8081/actuator/health` có thể trả `404` dù `http://localhost:9091/actuator/health` hoạt động.

Spring Cloud LoadBalancer hỗ trợ thuộc tính `spring.cloud.loadbalancer.health-check.port` để đặt cổng probe khác với cổng nghiệp vụ. Nếu nhiều replica có cổng management khác nhau, cấu hình một cổng chung có thể không phù hợp; nên thiết kế endpoint readiness có thể kiểm tra qua địa chỉ instance được discovery cung cấp hoặc cấu hình một health-check mechanism tùy chỉnh theo metadata/port của từng instance.

Cần phân biệt:

- `server.port` là cổng ứng dụng đích nhận traffic nghiệp vụ.
- `management.server.port` (nếu có) là cổng Actuator của ứng dụng đích.
- `spring.cloud.loadbalancer.health-check.port` đặt ở caller để điều chỉnh cổng **request kiểm tra của LoadBalancer**.

Đổi cổng trong caller không tự thay đổi cổng management của dịch vụ đích.

### Khi cố ý không kiểm tra một service

Theo tài liệu Spring Cloud Commons, nếu mục đường dẫn riêng của một service được đặt rỗng hoặc `null`, việc kiểm tra cho service đó có thể được bỏ qua. Không dùng cách này nếu bạn chỉ muốn kế thừa mặc định: hãy **không khai báo** khóa service tương ứng. Một mục YAML rỗng và một mục không tồn tại có thể mang ý nghĩa khác nhau, nên cần xác minh trên phiên bản thực tế.

## 4. initial-delay: thời điểm khởi động scheduler

`spring.cloud.loadbalancer.health-check.initial-delay` là khoảng trì hoãn dành cho scheduler thực hiện health check, ví dụ:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 3s
        interval: 15s
~~~

Về mặt ý niệm, timeline có thể được hình dung như sau:

~~~text
Khởi tạo health-check supplier
t = 0s
  |
  | initial-delay = 3s
  v
t ~ 3s       Vòng probe được lập lịch đầu tiên
  |
  | interval = 15s
  v
t ~ 18s      Vòng probe tiếp theo
  |
  | interval = 15s
  v
t ~ 33s      Vòng probe tiếp theo
~~~

Đây chỉ là dòng thời gian **theo cấu hình scheduler**. Thời gian quan sát thực tế có thể khác do thời điểm context con được tạo, thread scheduling, thời gian probe và cơ chế làm mới danh sách instance.

Mặc định `initial-delay: 0` không bảo đảm request nghiệp vụ đầu tiên sẽ đợi cho đến khi **mọi instance đã được kiểm tra**. Spring Cloud LoadBalancer thường tạo context riêng cho một service ID khi service đó được sử dụng lần đầu, trừ khi được cấu hình eager load. Do đó, một client mới khởi động có thể trải qua một giai đoạn ngắn trước khi có kết quả probe ổn định.

Không nên dùng `initial-delay` để giải quyết bài toán đồng bộ hóa khởi động của toàn hệ thống. Nếu service cần chỉ nhận traffic khi đủ điều kiện, hãy kết hợp readiness của bản sao, discovery và chính sách retry/timeout ở caller.

## 5. interval: chu kỳ kiểm tra, không phải thời gian timeout

`spring.cloud.loadbalancer.health-check.interval` kiểm soát thời gian lặp lại việc thăm dò:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 1s
        interval: 20s
~~~

`interval: 20s` không có nghĩa một request health check được phép chạy tối đa 20 giây. **Interval không phải HTTP connect timeout hoặc response timeout**. Nếu request probe mất quá lâu, lịch cập nhật và thời điểm phản ánh trạng thái instance có thể bị ảnh hưởng. Timeout của transport cần được đặt trên `WebClient`, `RestClient` hoặc `RestTemplate` thực hiện probe, tùy cấu hình supplier.

Cũng cần phân biệt với TTL của LoadBalancer cache:

| Khái niệm | Câu hỏi nó trả lời |
|---|---|
| Health-check `interval` | Khi nào chạy lại probe? |
| Health-check `initial-delay` | Khi nào lên lịch vòng đầu tiên? |
| Health-check `refetch-instances-interval` | Khi nào lấy lại **danh sách instance** từ nguồn delegate nếu bật refetch? |
| LoadBalancer `cache.ttl` | Danh sách instance được cache bao lâu ở tầng cache riêng? |
| HTTP response timeout | Chờ phản hồi một request lâu tối đa bao nhiêu? |

Không dùng `cache.ttl` để thay cho lịch health check, và cũng không dùng `interval` để giới hạn thời gian chờ HTTP.

### Chọn chu kỳ dài hay ngắn?

Giảm interval giúp phát hiện trạng thái không khỏe nhanh hơn, nhưng làm tăng số request probe. Với `M` caller, mỗi caller kiểm tra `N` instance cùng chu kỳ `T` giây, tải thăm dò xấp xỉ:

\[
\text{probe requests/second} \approx \frac{M \times N}{T}
\]

Ví dụ, có 40 caller, mỗi caller nhìn thấy 12 instance và interval bằng 10 giây thì toàn hệ thống tạo trung bình khoảng `48` probe/s, chưa tính việc tái lấy danh sách, retry hoặc những khác biệt trong việc lập lịch.

Do đó, đừng áp dụng `interval: 1s` cho hàng trăm caller chỉ để có cảm giác “phát hiện lỗi tức thì”. Hãy đo tải health endpoint, độ trễ phát hiện lỗi và yêu cầu về thời gian failover trước khi chọn chu kỳ.

## 6. Bật HealthCheckServiceInstanceListSupplier: YAML chưa đủ

Scheduler chỉ hoạt động khi health-check supplier được tạo trong chuỗi supplier. Trong một ứng dụng Spring MVC dùng RestClient blocking, có thể tạo cấu hình riêng theo service ID.

**Ứng dụng caller:**

~~~java
package com.example.caller;

import com.example.lb.InventoryHealthLoadBalancerConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;

@SpringBootApplication
@LoadBalancerClient(
        name = "inventory-service",
        configuration = InventoryHealthLoadBalancerConfiguration.class
)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

**Cấu hình supplier cho inventory-service:**

~~~java
package com.example.lb;

import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.ConfigurableApplicationContext;

public class InventoryHealthLoadBalancerConfiguration {

    @Bean
    ServiceInstanceListSupplier inventorySupplier(
            ConfigurableApplicationContext context) {

        return ServiceInstanceListSupplier.builder()
                .withDiscoveryClient()
                .withBlockingHealthChecks()
                .build(context);
    }
}
~~~

Lớp `InventoryHealthLoadBalancerConfiguration` nằm ngoài package scan của `com.example.caller`; đừng để nó vô tình trở thành cấu hình global. Với hệ reactive, có thể dùng `.withHealthChecks()` thay cho `.withBlockingHealthChecks()`, với các thành phần reactive HTTP phù hợp.

Có thể dùng configuration preset `spring.cloud.loadbalancer.configurations: health-check` nếu release train đang dùng hỗ trợ preset đó, nhưng cần hiểu nó áp dụng ở phạm vi cấu hình đã chọn và tránh trộn với bean supplier tùy chỉnh gây trùng lặp.

**Thứ tự supplier rất quan trọng.** Health-check supplier nên đặt ngay sau nguồn lấy instance qua network, trước các supplier lọc theo request như zone/hint. `HealthCheckServiceInstanceListSupplier` đã sử dụng cơ chế replay/caching của riêng nó; thường không nên bọc tiếp bằng `CachingServiceInstanceListSupplier` mà không có lý do đo đạc rõ ràng.

Trong hệ thống dựa vào Eureka/Consul hoặc registry đã lọc instance khỏe, việc bổ sung health check ở caller có thể gây probe dư thừa. Cơ chế này đặc biệt hữu ích với `SimpleDiscoveryClient` khai báo instance tĩnh, vì danh sách tĩnh không tự phát hiện tiến trình đã tắt.

## 7. Ví dụ cấu hình hoàn chỉnh ở caller

Giả sử caller cần gọi inventory và catalog. Inventory có endpoint readiness riêng; catalog dùng endpoint Actuator mặc định:

~~~yaml
server:
  port: 8080

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
              - uri: http://localhost:8082
            catalog-service:
              - uri: http://localhost:8091

    loadbalancer:
      health-check:
        initial-delay: 2s
        interval: 10s
        path:
          default: /actuator/health
          inventory-service: /internal/ready

      clients:
        inventory-service:
          health-check:
            interval: 5s
~~~

Khi các service đều được cấu hình dùng health-check supplier, giá trị hiệu lực là:

| Service ID | Path | Initial delay | Interval |
|---|---|---:|---:|
| `inventory-service` | `/internal/ready` | 2s | 5s |
| `catalog-service` | `/actuator/health` | 2s | 10s |

Nhánh `clients.inventory-service` ghi đè interval của inventory trong các phiên bản hỗ trợ cấu hình per-client, nhưng không cần sao chép initial-delay. Nếu không khai báo supplier cho catalog, thông số interval của catalog **không khiến catalog tự chạy probe**.

Đừng đặt danh sách instance dưới `spring.cloud.loadbalancer.clients.inventory-service`: danh sách instance thuộc discovery (`spring.cloud.discovery.client.simple.instances`) hoặc nguồn `ServiceInstanceListSupplier`. Namespace LoadBalancer chứa chính sách lựa chọn, không phải nơi định nghĩa các URI đích cố định.

## 8. Thực hành endpoint health riêng trên mỗi bản sao

Trong ứng dụng inventory-service thử nghiệm, tạo một endpoint có thể điều khiển trạng thái để kiểm tra lịch thăm dò. Mã sau chỉ phục vụ lab; không mở endpoint thay đổi health công khai trong production.

~~~java
package com.example.inventory;

import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal")
public class DemoHealthController {

    private final AtomicBoolean ready = new AtomicBoolean(true);

    @GetMapping("/ready")
    public ResponseEntity<Map<String, String>> ready() {
        if (ready.get()) {
            return ResponseEntity.ok(Map.of("status", "UP"));
        }
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("status", "DOWN"));
    }

    // Chỉ dùng trong môi trường thử nghiệm cục bộ.
    @PostMapping("/demo/unready")
    public void markUnready() {
        ready.set(false);
    }

    @PostMapping("/demo/ready")
    public void markReady() {
        ready.set(true);
    }
}
~~~

Chạy cùng một artifact inventory trên cổng 8081 và 8082. Mỗi tiến trình có trạng thái `ready` độc lập. Caller cấu hình cả hai URI dưới service ID `inventory-service` và `health-check.path.inventory-service: /internal/ready`.

Kiểm tra trực tiếp bằng PowerShell:

~~~powershell
Invoke-WebRequest http://localhost:8081/internal/ready
Invoke-WebRequest http://localhost:8082/internal/ready
~~~

Ban đầu cả hai trả 200. Sau đó đánh dấu instance 8082 chưa sẵn sàng:

~~~powershell
Invoke-RestMethod -Method Post http://localhost:8082/internal/demo/unready
~~~

Khi request probe đã chạy, instance 8082 có thể bị loại khỏi danh sách đủ điều kiện được LoadBalancer chọn. Thời điểm xuất hiện kết quả phụ thuộc `initial-delay`, `interval`, trạng thái context, thời gian kiểm tra và cơ chế supplier. Đừng kỳ vọng thay đổi xảy ra ngay sau khi chạy lệnh POST.

Phục hồi instance:

~~~powershell
Invoke-RestMethod -Method Post http://localhost:8082/internal/demo/ready
~~~

Sau những vòng probe tiếp theo, bản sao 8082 có thể được đưa trở lại danh sách khỏe.

### Quan sát qua RestClient load-balanced

Ở caller, khai báo builder:

~~~java
@Bean
@LoadBalanced
RestClient.Builder loadBalancedRestClientBuilder() {
    return RestClient.builder();
}
~~~

Dịch vụ inventory có thể thêm endpoint chẩn đoán:

~~~java
@GetMapping("/internal/instance")
public Map<String, String> instance(Environment environment) {
    return Map.of("port", environment.getProperty("server.port", "8081"));
}
~~~

Caller tạo RestClient với `baseUrl("http://inventory-service")` và chuyển tiếp `GET /internal/instance`. Sau đó gửi nhiều request qua caller:

~~~powershell
1..30 | ForEach-Object {
    Invoke-RestMethod http://localhost:8080/proxy/instance
}
~~~

`/proxy/instance` là endpoint ví dụ cần được caller tự triển khai để chuyển tiếp request. Kết quả mong đợi khi cả hai khỏe là có thể nhìn thấy hai cổng được chọn. Khi 8082 chuyển sang trạng thái không sẵn sàng và **vẫn còn 8081 khỏe**, các lượt chọn mới sau khi supplier cập nhật thường chỉ đi đến 8081.

Hãy ghi timestamp của thao tác đánh dấu `unready`, lần probe tương ứng và lần đầu caller ngừng chọn instance đó. Đây là cách quan sát hiệu quả của interval hơn là chỉ nhìn YAML.

## 9. refetch-instances và repeat-health-check không cùng ý nghĩa

Hai quá trình độc lập cần được phân biệt:

1. **Lấy danh sách instance:** delegate `ServiceInstanceListSupplier` cung cấp hoặc cập nhật những bản sao đang được biết.
2. **Kiểm tra sức khỏe:** health-check supplier gọi endpoint của các bản sao đã được biết để quyết định tập đủ điều kiện lựa chọn.

Một delegate có thể cung cấp một danh sách cố định và không tự phát lại danh sách khi registry đổi. `HealthCheckServiceInstanceListSupplier` có các thuộc tính bổ sung để chủ động lấy lại danh sách:

| Thuộc tính | Mặc định | Tác dụng |
|---|---|---|
| `health-check.refetch-instances` | `false` | Có chủ động lấy lại danh sách instance hay không |
| `health-check.refetch-instances-interval` | `25s` | Chu kỳ lấy lại danh sách khi refetch bật |
| `health-check.repeat-health-check` | `true` | Có tiếp tục lặp probe độc lập hay không |
| `health-check.update-results-list` | `true` | Có phát cập nhật danh sách theo từng instance sống được phát hiện hay gom đủ trước khi phát |

Ví dụ muốn lấy lại danh sách sau mỗi 30 giây, đồng thời không tạo một lịch probe lặp riêng:

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        refetch-instances: true
        refetch-instances-interval: 30s
        repeat-health-check: false
~~~

Tài liệu Spring Cloud lưu ý mỗi lần refetch cũng có thể kích hoạt health check, vì vậy tắt việc lặp độc lập đôi khi phù hợp. Nhưng cấu hình này **không** làm chu kỳ 10s của `interval` chạy như trước: vòng probe phụ thuộc thời điểm refetch và cách delegate phát danh sách.

Nếu dùng `update-results-list: false`, supplier gom toàn bộ các instance khỏe được tìm thấy trước khi phát danh sách mới, thay vì phát cập nhật từng phần. Tùy nhu cầu quan sát, lựa chọn này giúp tránh nhìn thấy danh sách trung gian đang được xây dựng giữa các probe.

Đối với danh sách SimpleDiscoveryClient được khai báo tĩnh trong `application.yml`, bật refetch không tự phát hiện instance mới chưa được đưa vào cấu hình; nếu muốn động, cần registry hoặc nguồn cập nhật instance phù hợp.

## 10. Chú ý hành vi khi không có instance khỏe

Đây là điểm rất quan trọng đối với kỳ vọng failover: theo tài liệu chính thức, `HealthCheckServiceInstanceListSupplier` **thường chỉ trả instance khỏe, trừ khi không còn instance nào khỏe; lúc đó nó có thể trả lại toàn bộ danh sách đã truy xuất**.

Ví dụ:

~~~text
Discovery trả về: [A, B, C]

A khỏe, B lỗi, C khỏe
  -> Supplier có thể trả [A, C]
  -> Round Robin / Random chọn trong [A, C]

A lỗi, B lỗi, C lỗi
  -> Supplier có thể fallback về [A, B, C]
  -> Lời gọi nghiệp vụ vẫn có nguy cơ vào instance lỗi
~~~

Do đó, không được mô tả cơ chế này như một bộ lọc **fail-closed** tuyệt đối. Nó có hành vi fallback khi không phát hiện được instance khỏe nào để tránh trả kết quả rỗng trong một số tình huống. Nếu hệ thống yêu cầu “không gửi request đến bất kỳ instance đã bị đánh dấu unhealthy”, cần thiết kế một chính sách lọc hoặc fail-fast riêng và kiểm thử đúng điều kiện này.

Điều này cũng có nghĩa:

- Mất hết kết nối đến health endpoint có thể làm caller vẫn thử gửi request nghiệp vụ.
- Trả về mã 503 từ mọi instance không bảo đảm caller lập tức không gọi instance nào.
- HTTP timeout, retry, circuit breaker và trả lỗi phù hợp cho người dùng vẫn cần được thiết kế độc lập.

## 11. Tại sao danh sách đã khỏe vẫn có request thất bại?

Health-check là ảnh chụp trạng thái tại các thời điểm thăm dò; trạng thái có thể thay đổi **giữa hai probe**:

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant H as HealthCheck supplier
    participant I as Inventory instance

    H->>I: GET /internal/ready
    I-->>H: 200 OK
    Note over H: Ghi nhận instance khỏe
    Note over I: Tiến trình ngừng sau probe
    C->>H: Lấy danh sách eligible
    H-->>C: Vẫn có instance vừa ngừng
    C->>I: GET /api/items/SKU-001
    I--xC: Connection refused / timeout
    Note over H: Vòng probe sau mới phản ánh tình trạng
~~~

Đây không nhất thiết là bug của Spring Cloud LoadBalancer. Đó là giới hạn của **kiểm tra định kỳ**.

Nếu request lỗi có thể lặp lại an toàn, bạn có thể cân nhắc retry sang instance khác với giới hạn tổng số lần thử. Với thao tác tạo thanh toán hoặc cập nhật dữ liệu, retry cần idempotency key hoặc bảo đảm không tạo tác dụng phụ trùng lặp.

Đặt timeout ở HTTP client riêng: timeout của RestClient khác với chu kỳ scheduler, timeout của WebClient khác với thời gian đợi lần probe tiếp theo, và OpenFeign có các khóa cấu hình connect/read timeout riêng. Không dùng `health-check.interval` để suy ra thời hạn chờ cho request nghiệp vụ.

## 12. Cấu hình path, interval và initial-delay theo từng service

Giả sử order-service gọi inventory và payment. Inventory dùng health check nhanh hơn vì các bản sao thường được triển khai lại; payment dùng health check thưa hơn để tránh probe vào hệ thống nhạy cảm.

~~~yaml
spring:
  cloud:
    loadbalancer:
      health-check:
        initial-delay: 1s
        interval: 25s
        path:
          default: /actuator/health
          inventory-service: /internal/ready
          payment-service: /actuator/health/readiness

      clients:
        inventory-service:
          health-check:
            initial-delay: 0s
            interval: 5s

        payment-service:
          health-check:
            initial-delay: 3s
            interval: 30s
~~~

Trong các phiên bản hỗ trợ thuộc tính theo client ID, các cấu hình riêng sẽ có ưu tiên cao hơn mặc định. Điều này áp dụng cho **service ID đích**, không phải tên application của caller.

Nếu cùng ứng dụng cấu hình health-check supplier cho inventory nhưng không cấu hình cho payment, các thuộc tính payment vẫn được bind nhưng sẽ không tự sinh ra một scheduler health check của payment.

Cần kiểm tra phiên bản Spring Cloud cụ thể khi kết hợp map `health-check.path` và nested `clients.<serviceId>.health-check`: các giá trị đơn như interval/initial-delay thường dễ ghép, còn map/list có thể có quy tắc merge riêng theo binder. Hãy xác minh đường dẫn thực tế bằng log network hoặc breakpoint khi vận hành.

## 13. Tránh gây thêm sự cố với endpoint health

Một endpoint kiểm tra sức khỏe cần **nhẹ, ổn định và phản ánh khả năng nhận traffic**. Nếu health endpoint mỗi lần được gọi đều chạy nhiều truy vấn database, gọi service khác và kiểm tra toàn bộ phụ thuộc, tải probe từ hàng trăm caller có thể gây thêm áp lực không cần thiết.

Một số nguyên tắc:

- Chọn readiness cho quyết định có được phục vụ traffic hay không; liveness thường dành cho quyết định khởi động lại tiến trình.
- Tránh tự động đánh dấu không khỏe hàng loạt khi một dependency không thiết yếu gặp lỗi; failure cascade có thể khiến nhiều replica cùng bị loại.
- Không đưa token hoặc thông tin nhạy cảm vào đường dẫn health check.
- Nếu endpoint không public, bảo đảm caller có thể truy cập bằng chính sách mạng/xác thực phù hợp; trả 401/403 thường làm probe thất bại.
- Kiểm tra security group, TLS, hostname và certificate; lỗi mạng/TLS cũng làm endpoint có vẻ không khỏe.
- Không mở các endpoint đổi trạng thái như `/internal/demo/unready` trong môi trường production.
- Theo dõi riêng lỗi thăm dò và lỗi API nghiệp vụ; chúng có nguyên nhân và độ ưu tiên khác nhau.

Nếu hệ thống có registry hoặc orchestration đã cung cấp trạng thái readiness của instance, đo xem có thật sự cần probe thêm ở mỗi caller hay không. Hãy tránh tạo hai cơ chế kiểm tra sức khỏe quá dày cùng lúc.

## 14. Bảng chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Đổi `interval` nhưng không có request probe | Chưa tạo health-check supplier | Xác minh `ServiceInstanceListSupplier` thực tế và cấu hình `@LoadBalancerClient` |
| Probe trả 404 | Path sai hoặc Actuator chưa tồn tại | Gọi trực tiếp path trên instance, kiểm tra `spring-boot-starter-actuator` |
| Probe trả 401/403 | Security chặn endpoint | Kiểm tra authorization của URL và request probe |
| Probe đi sai cổng | Port management khác port nghiệp vụ | Kiểm tra `ServiceInstance.getPort()`, `management.server.port` và `health-check.port` |
| Tắt 8082 nhưng vẫn có request vào 8082 | Chưa đến kỳ probe tiếp theo, danh sách chưa cập nhật hoặc fallback khi tất cả unhealthy | Đối chiếu timestamp, danh sách ứng viên và kết quả probe |
| Thêm bản sao mà caller không nhìn thấy | Delegate không phát danh sách mới | Kiểm tra registry/discovery, cân nhắc `refetch-instances` |
| Cấu hình path cho inventory không tác dụng | Sai service ID | Đối chiếu URL logic/`@FeignClient(name)` và khóa map |
| Số request probe nhiều | Interval quá ngắn, quá nhiều caller hoặc hai tầng health check | Tính tải probe, kiểm tra registry/Actuator |
| Mọi instance trả 503 nhưng caller vẫn gửi request | Supplier fallback khi không còn instance khỏe | Đánh giá yêu cầu fail-closed và chính sách resilience |
| Lỗi xảy ra trong lúc khởi động | Context khởi tạo chưa có kết quả probe ổn định | Kiểm tra `initial-delay`, eager load, readiness và timeout/retry |

## 15. Checklist triển khai

- [ ] Xác định service ID và nguồn danh sách `ServiceInstance`.
- [ ] Bảo đảm `HealthCheckServiceInstanceListSupplier` thực sự được cấu hình; chỉ khai báo YAML là chưa đủ.
- [ ] Chọn đúng path theo service ID và xác nhận endpoint trả HTTP thành công khi bản sao sẵn sàng.
- [ ] Nếu dùng `/actuator/health`, ứng dụng đích phải có Actuator hoặc endpoint tương ứng.
- [ ] Đặt `initial-delay` và `interval` dựa trên thời gian mong muốn phát hiện lỗi cùng chi phí probe.
- [ ] Phân biệt scheduler interval, refetch interval, cache TTL và HTTP timeout.
- [ ] Nếu có management port riêng, kiểm tra cấu hình port probe.
- [ ] Không dùng cả caching supplier và health-check supplier một cách trùng lặp khi không có nhu cầu.
- [ ] Nắm hành vi fallback khi **không còn instance khỏe**.
- [ ] Quan sát request thực tế, trace/metric và log health check trong các tình huống một instance lỗi hoặc tất cả lỗi.
- [ ] Kiểm thử trường hợp thêm, xóa, khởi động lại instance; không chỉ thử một lần sau deploy.
- [ ] Khi dùng discovery registry, xác định liệu kiểm tra lại ở caller có thực sự cần thiết.
- [ ] Cấu hình timeout, retry, circuit breaker và chính sách idempotency riêng ở tầng phù hợp.

## Tài liệu tham khảo

- [Spring Cloud Commons — Instance Health-Check for LoadBalancer](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/loadbalancer.html): cách cấu hình supplier, đường dẫn theo service ID, refetch và hành vi khi không có instance khỏe.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html): tra cứu giá trị mặc định của `initial-delay`, `interval`, `path`, `port` và các thuộc tính bổ sung.
- [Spring Boot Actuator — Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): tìm hiểu cách công bố health endpoint và health probe cho dịch vụ đích.

**Kết luận:** đường dẫn `path` quyết định *kiểm tra ở đâu*, `initial-delay` quyết định *bắt đầu lịch kiểm tra khi nào*, còn `interval` quyết định *lặp lại với tần suất nào*. Chúng chỉ có tác dụng khi health-check supplier tham gia pipeline lựa chọn `ServiceInstance`. Thiết kế đúng ba giá trị, kết hợp discovery, readiness, quan sát và cơ chế chịu lỗi sẽ giúp RestClient, WebClient và OpenFeign giảm nguy cơ gửi request đến bản sao không sẵn sàng mà vẫn hiểu rõ giới hạn của phép kiểm tra định kỳ.
