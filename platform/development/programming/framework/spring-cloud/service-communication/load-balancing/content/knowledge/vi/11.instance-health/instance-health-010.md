# Mô phỏng bản sao lỗi rồi phục hồi để kiểm chứng

Một lần gọi `http://catalog-service/api/items` có thể thành công lúc đầu, thất bại khi một instance gặp sự cố, rồi thành công trở lại khi instance phục hồi. **Spring Cloud LoadBalancer không mặc nhiên biết ngay thời điểm instance hỏng hoặc khỏe lại**: nó chọn từ danh sách `ServiceInstance` do supplier cung cấp, còn discovery, health check, cache và chu kỳ cập nhật quyết định tập ứng viên đó thay đổi khi nào.

Bài thực hành thuộc chương **Sức khỏe bản sao** của module **SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING**. Chúng ta sẽ dựng **hai instance cùng service ID**, tạo lỗi health có kiểm soát trên một instance, quan sát việc chuyển request sang instance còn khỏe, bật lại instance lỗi rồi xác nhận nó quay về tập ứng viên. Trong quá trình thực hành, bài học kết nối cơ chế chọn instance với **service discovery, health check, chính sách định tuyến**, cũng như hành vi của **RestClient, WebClient, OpenFeign, timeout, retry và observability**.

Kết quả cần phân biệt được ba trường hợp:

1. **Probe thất bại nhưng tiến trình còn chạy:** health supplier có thể đánh dấu instance không phù hợp, dù endpoint nghiệp vụ vẫn có thể phản hồi.
2. **Tiến trình hoặc mạng bị lỗi:** HTTP request gửi tới instance đã chọn có thể bị từ chối kết nối hoặc timeout trước khi health supplier kịp cập nhật.
3. **Instance phục hồi:** chỉ sau khi health/discovery cập nhật và instance được đưa lại vào danh sách, bộ chọn mới có thể tiếp tục sử dụng nó.

> Tất cả endpoint thay đổi trạng thái trong bài chỉ dành cho môi trường thử nghiệm cục bộ. Không triển khai endpoint điều khiển lỗi này công khai trên môi trường production.

## 1. Kiến trúc thí nghiệm và giả thuyết

Hệ thống có một caller và hai instance của cùng một dịch vụ logic:

| Thành phần | Cổng cục bộ | Vai trò |
|---|---:|---|
| `caller-service` | `18090` | Gọi URL bằng service ID thông qua RestClient có LoadBalancer |
| `catalog-a` | `18081` | Instance A của `catalog-service` |
| `catalog-b` | `18082` | Instance B của `catalog-service` |

Cả A và B đăng ký logic dưới cùng service ID `catalog-service` trong cấu hình discovery tĩnh. Mỗi instance có:

- `GET /internal/lb-health`: trả `200 OK` khi khỏe và `503 Service Unavailable` khi bị đánh dấu không khỏe.
- `GET /api/whoami`: trả mã instance thực sự nhận request.
- `POST /__test/ready?healthy=false|true`: chuyển trạng thái probe nhằm mô phỏng lỗi và phục hồi.

Chúng ta dùng `HealthCheckServiceInstanceListSupplier` để khám phá sự thay đổi từ health endpoint. Các ví dụ chạy trong môi trường thử nghiệm, không cần Eureka hay Kubernetes.

~~~mermaid
flowchart LR
    U["curl / client thử nghiệm"] --> CALLER["caller-service :18090"]
    CALLER --> LB["Spring Cloud LoadBalancer"]
    DISC["SimpleDiscoveryClient: A, B"] --> HEALTH["HealthCheckServiceInstanceListSupplier"]
    HEALTH --> LB
    HEALTH -. "GET /internal/lb-health" .-> A["catalog-a :18081"]
    HEALTH -. "GET /internal/lb-health" .-> B["catalog-b :18082"]
    LB --> A
    LB --> B
~~~

**Giả thuyết:** ở trạng thái ổn định, sau khi thông tin health đã được cập nhật, A và B đều có thể nhận request; khi B trả health `503`, request mới ưu tiên đi đến A; khi B trở lại `200`, B có cơ hội được chọn trở lại. Kết quả thực tế phải được xác minh bằng log và danh sách supplier chứ không chỉ dựa vào một request đơn lẻ.

## 2. Các lớp tham gia và giới hạn mỗi lớp

| Lớp | Biết gì? | Không bảo đảm điều gì? |
|---|---|---|
| `SimpleDiscoveryClient` | A và B được cấu hình là instance của cùng service ID | Không tự xóa B khi chúng ta đổi health trong ứng dụng |
| `HealthCheckServiceInstanceListSupplier` | Kết quả probe được cập nhật theo cơ chế và chu kỳ đã cấu hình | Không biết chắc mọi HTTP request nghiệp vụ sẽ thành công |
| `RoundRobinLoadBalancer` | Danh sách ứng viên hiện được cung cấp | Không tự thực hiện probe hoặc kiểm tra CPU |
| `RestClient` | HTTP request đã gửi và response/exception trả về | Không tự biết service ID hợp lệ nếu chưa tích hợp LoadBalancer |
| Caller | Kết quả nghiệp vụ và thông tin lỗi của lần gọi | Không nhìn thấy ngay mọi thay đổi trạng thái trên server |

Thứ tự logic là **discovery → health supplier → thuật toán chọn đích → HTTP client**. Khi B hỏng, có thể tồn tại một khoảng thời gian ngắn trước lần kiểm tra tiếp theo, trong đó LoadBalancer vẫn thấy B. Đây là đặc tính của hệ thống cập nhật trạng thái bất đồng bộ, không phải bằng chứng Round Robin hoạt động sai.

## 3. Chuẩn bị môi trường

Dùng các phiên bản **Spring Boot và Spring Cloud tương thích** đang được project quản lý bằng BOM. Không tự trộn các release train không tương thích.

Với dự án instance, cần ít nhất:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Với dự án caller:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.cloud:spring-cloud-starter-loadbalancer'
}
~~~

Trong Gradle hoặc Maven thực tế, cần áp dụng plugin và dependency management/BOM của dự án. Các đoạn `dependencies` trên chỉ thể hiện những dependency phục vụ lab, không phải toàn bộ file build.

Có thể kiểm tra thí nghiệm bằng trình duyệt, Postman hoặc `curl`; các lệnh bên dưới minh họa dùng `curl`. Chuẩn bị ba terminal để chạy hai instance và caller độc lập.

## 4. Viết ứng dụng instance có thể chuyển trạng thái health

Để quan sát rõ ràng, hai instance sử dụng **cùng source code** nhưng chạy trên hai cổng và có `instance.id` khác nhau:

~~~java
package demo.catalog;

import java.util.Map;
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class CatalogInstanceApplication {

    private final AtomicBoolean healthy = new AtomicBoolean(true);

    @Value("${instance.id:catalog-unknown}")
    private String instanceId;

    public static void main(String[] args) {
        SpringApplication.run(CatalogInstanceApplication.class, args);
    }

    @GetMapping("/internal/lb-health")
    public ResponseEntity<Map<String, Object>> health() {
        if (!healthy.get()) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(Map.of("status", "DOWN", "instance", instanceId));
        }
        return ResponseEntity.ok(
            Map.of("status", "UP", "instance", instanceId));
    }

    @GetMapping("/api/whoami")
    public Map<String, String> whoAmI() {
        return Map.of("instance", instanceId, "message", "request received");
    }

    // Chỉ bật trong lab cục bộ; không triển khai endpoint này ở production.
    @PostMapping("/__test/ready")
    public Map<String, Object> changeHealth(
            @RequestParam boolean healthy) {
        this.healthy.set(healthy);
        return Map.of("instance", instanceId, "healthy", healthy);
    }
}
~~~

**Vì sao endpoint nghiệp vụ vẫn trả thành công khi health bị tắt?** Đây là thiết kế cố ý: để chứng minh health supplier sàng lọc ở **phía caller**. Việc đổi `healthy=false` chỉ làm endpoint probe trả `503`; `GET /api/whoami` vẫn chạy nếu gửi trực tiếp đến instance. Điều này phân biệt **mô phỏng unhealthy** với **tiến trình bị kill**.

Giả sử artifact của ứng dụng instance tên là `catalog-instance.jar`, chạy riêng hai tiến trình:

~~~bash
java -jar catalog-instance.jar --server.port=18081 --instance.id=catalog-a
~~~

~~~bash
java -jar catalog-instance.jar --server.port=18082 --instance.id=catalog-b
~~~

Kiểm tra hai probe hoạt động:

~~~bash
curl -i http://localhost:18081/internal/lb-health
curl -i http://localhost:18082/internal/lb-health
~~~

Ban đầu, cả hai dự kiến trả HTTP `200` và body báo `UP`. Nếu không, cần kiểm tra cổng, log startup, xung đột port và khả năng kết nối trước khi tiếp tục.

## 5. Cấu hình caller với discovery tĩnh và health check

Trong `application.yml` của caller:

~~~yaml
server:
  port: 18090

spring:
  application:
    name: caller-service
  cloud:
    discovery:
      client:
        simple:
          instances:
            catalog-service:
              - uri: http://localhost:18081
              - uri: http://localhost:18082
    loadbalancer:
      cache:
        enabled: false
      health-check:
        path:
          catalog-service: /internal/lb-health
        interval: 5s
~~~

Giải thích:

- `spring.cloud.discovery.client.simple.instances.catalog-service` khai báo hai địa chỉ đại diện cho cùng một service ID.
- `health-check.path.catalog-service` chỉ rõ endpoint kiểm tra của từng instance.
- `health-check.interval: 5s` là chu kỳ tham khảo giúp quan sát thay đổi trong môi trường lab; không phải giá trị khuyến nghị production.
- `cache.enabled: false` giúp thí nghiệm dễ lý giải hơn vì không thêm cache LoadBalancer như một nguồn dữ liệu cũ. Health supplier vẫn có cơ chế phát và duy trì kết quả riêng.

Các thuộc tính liên quan như initial delay, refetch instances, update results và timeout có thể khác theo phiên bản Spring Cloud. Với dự án đang dùng, hãy kiểm tra configuration properties thực tế. Không suy rằng các instance được kiểm tra đồng thời ngay khi ứng dụng khởi động.

### Đăng ký supplier health check cho đúng service ID

Trên ứng dụng caller, gắn cấu hình dành riêng cho `catalog-service`:

~~~java
package demo.caller;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.loadbalancer.annotation.LoadBalancerClient;
import demo.lbconfig.CatalogLbConfiguration;

@SpringBootApplication
@LoadBalancerClient(
    name = "catalog-service",
    configuration = CatalogLbConfiguration.class
)
public class CallerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CallerApplication.class, args);
    }
}
~~~

Tạo lớp cấu hình supplier:

~~~java
package demo.lbconfig;

import org.springframework.cloud.loadbalancer.core.ServiceInstanceListSupplier;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CatalogLbConfiguration {

    @Bean
    ServiceInstanceListSupplier catalogInstanceListSupplier(
            ConfigurableApplicationContext context) {
        return ServiceInstanceListSupplier.builder()
            .withDiscoveryClient()
            .withHealthChecks()
            .build(context);
    }
}
~~~

Thêm import `demo.lbconfig.CatalogLbConfiguration` vào `CallerApplication`. **Đặt lớp `CatalogLbConfiguration` ngoài cây package được Spring Boot component-scan từ `demo.caller`**, để không vô tình áp dụng bean supplier chuyên biệt cho mọi service ID. `@LoadBalancerClient` sẽ nạp cấu hình này trong context LoadBalancer dành cho `catalog-service`.

Dùng `withDiscoveryClient().withHealthChecks()` thay vì vừa thêm `withCaching()` vào cùng chuỗi: health supplier có vòng đời cập nhật riêng, và ghép chồng cache có thể làm khó kiểm chứng dữ liệu mới. Đây là lựa chọn tối giản cho lab, không phải một quy tắc thay thế mọi kiến trúc production.

## 6. Tạo RestClient có LoadBalancer và endpoint quan sát

Caller cần một builder được đánh dấu `@LoadBalanced` để URL `http://catalog-service/...` được diễn giải bằng service ID thay vì DNS của máy cục bộ.

~~~java
package demo.caller;

import org.springframework.cloud.client.loadbalancer.LoadBalanced;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
class RestClientConfiguration {

    @Bean
    @LoadBalanced
    RestClient.Builder restClientBuilder() {
        return RestClient.builder();
    }
}
~~~

Endpoint gọi dịch vụ:

~~~java
package demo.caller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
class CatalogCallController {

    private final RestClient catalogRestClient;

    CatalogCallController(RestClient.Builder restClientBuilder) {
        this.catalogRestClient = restClientBuilder.build();
    }

    @GetMapping("/demo/whoami")
    ResponseEntity<String> callCatalog() {
        String body = catalogRestClient.get()
            .uri("http://catalog-service/api/whoami")
            .retrieve()
            .body(String.class);
        return ResponseEntity.ok(body);
    }
}
~~~

Ví dụ để response hoặc exception đi qua controller một cách đơn giản, phù hợp quan sát trong lab. Ở production cần thêm HTTP error mapping rõ nghĩa, timeout, retry giới hạn và xử lý trường hợp discovery không chọn được instance.

Sau khi khởi động caller, thử:

~~~bash
curl -i http://localhost:18090/demo/whoami
~~~

Response thành công sẽ chứa `catalog-a` hoặc `catalog-b` trong body. Đây là kết quả được trả từ **instance thực sự nhận request**, không phải từ cache của LoadBalancer.

## 7. Kịch bản A — cả hai instance khỏe mạnh

Thực hiện các bước:

1. Xác nhận cả `localhost:18081/internal/lb-health` và `localhost:18082/internal/lb-health` trả `200`.
2. Khởi động caller, chờ chu kỳ health đầu tiên cập nhật danh sách.
3. Gửi một loạt request đến `http://localhost:18090/demo/whoami`.
4. Ghi lại số lần thấy `catalog-a` và `catalog-b`.

Ví dụ lệnh trong shell tương thích Bash:

~~~bash
for i in $(seq 1 12); do
  curl -s http://localhost:18090/demo/whoami
  echo
done
~~~

Nếu dùng PowerShell thay vì Bash, có thể dùng:

~~~powershell
1..12 | ForEach-Object {
  Invoke-RestMethod -Uri "http://localhost:18090/demo/whoami"
}
~~~

Trong điều kiện hai instance luôn thuộc danh sách healthy và Round Robin mặc định đang được chọn, một chuỗi request tuần tự thường phân phối tương đối cân bằng. Không dựa vào một hoặc hai request để kết luận; thứ tự hoặc tỷ lệ có thể thay đổi khi nhiều caller, retry và các yêu cầu khác cùng chạy.

Ghi nhận baseline:

| Quan sát | Kết quả cần xác minh |
|---|---|
| Discovery | Có đủ A và B |
| Health | A và B đều trả HTTP 200 |
| Danh sách sau health supplier | Có A và B sau khi kết quả kiểm tra hội tụ |
| Request qua caller | Có thể nhận response từ cả hai |
| Lỗi HTTP/timeout | Không có lỗi trong điều kiện lab bình thường |

## 8. Kịch bản B — đánh dấu B không khỏe

Không dừng tiến trình B. Chỉ đổi trạng thái health của B:

~~~bash
curl -i -X POST "http://localhost:18082/__test/ready?healthy=false"
curl -i http://localhost:18082/internal/lb-health
curl -i http://localhost:18081/internal/lb-health
~~~

Kết quả cần thấy:

- B trả `503` **cho endpoint health**.
- A vẫn trả `200` cho endpoint health.
- Gọi trực tiếp `http://localhost:18082/api/whoami` vẫn có thể trả `200` vì tiến trình B chưa dừng.

Tiếp tục gửi request qua caller. Sau khi health supplier thực sự nhận được kết quả mới (có thể cần hơn một chu kỳ cấu hình), kiểm tra xem response chỉ còn đến từ A:

~~~bash
for i in $(seq 1 12); do
  curl -s http://localhost:18090/demo/whoami
  echo
done
~~~

### Điều gì phải xảy ra bên trong?

~~~mermaid
sequenceDiagram
    autonumber
    participant T as Người thử nghiệm
    participant B as catalog-b
    participant H as HealthCheck supplier
    participant LB as LoadBalancer
    participant A as catalog-a

    T->>B: POST /__test/ready?healthy=false
    B-->>T: healthy=false
    H->>A: GET /internal/lb-health
    A-->>H: HTTP 200
    H->>B: GET /internal/lb-health
    B-->>H: HTTP 503
    Note over H: Cập nhật danh sách healthy theo cơ chế phiên bản
    LB->>H: Xin danh sách ServiceInstance
    H-->>LB: [A] (khi chính sách lọc áp dụng)
    LB->>A: Chọn A cho request mới
~~~

**Điểm cần xác minh:** quan sát được B biến mất khỏi tập ứng viên **sau khi health supplier cập nhật**, không chỉ quan sát probe trả `503`. Khi status vừa bị chuyển, một vài request mới vẫn có thể đi đến B trước khi kết quả kiểm tra được công bố.

Trong bước này, HTTP `503` của `GET /internal/lb-health` là **response từ endpoint probe**, không phải HTTP `503` mà caller nhất thiết nhận khi gọi `GET /demo/whoami`. Nếu request qua caller đến A thành công, caller có thể vẫn trả `200` bình thường.

## 9. Kịch bản C — phục hồi B và kiểm tra khả năng quay lại

Bật lại trạng thái health của B:

~~~bash
curl -i -X POST "http://localhost:18082/__test/ready?healthy=true"
curl -i http://localhost:18082/internal/lb-health
~~~

Khi probe B trả `200` trở lại, tiếp tục gọi qua caller qua nhiều chu kỳ health. Sau khi danh sách healthy cập nhật, kỳ vọng B có thể được lựa chọn trở lại:

~~~mermaid
sequenceDiagram
    autonumber
    participant T as Người thử nghiệm
    participant B as catalog-b
    participant H as HealthCheck supplier
    participant LB as LoadBalancer

    T->>B: POST /__test/ready?healthy=true
    B-->>T: healthy=true
    H->>B: GET /internal/lb-health
    B-->>H: HTTP 200
    Note over H: B trở lại danh sách healthy
    LB->>H: Xin danh sách mới
    H-->>LB: [A, B]
    LB->>B: Có thể chọn B
~~~

Để kết luận **phục hồi hoàn tất**, cần có đủ bằng chứng:

1. Probe B đã trả `200`.
2. Health supplier đã công bố danh sách có B.
3. Một hoặc nhiều request qua caller thực sự đến B.
4. Không xuất hiện lỗi bất thường sau khi nhận lại traffic.

**Probe UP không tự chứng minh caller đã dùng B**; nếu caller không thấy B trở lại, kiểm tra lại chu kỳ health, danh sách supplier, config path, service ID, startup và khả năng kết nối.

## 10. Trình tự thời gian: lỗi không được phát hiện ngay lập tức

Giả sử chu kỳ health là 5 giây, tại T0 danh sách healthy có A và B. B chuyển health sang `503` ngay sau lần probe gần nhất:

| Mốc minh họa | Sự kiện | LoadBalancer có thể thấy |
|---|---|---|
| T0 | A và B healthy | [A, B] |
| T1 | B chuyển probe từ 200 sang 503 | Có thể vẫn [A, B] |
| T2 | Chu kỳ kiểm tra B tiếp theo chạy | Kết quả đang cập nhật |
| T3 | Health supplier phát danh sách mới | Có thể [A] |
| T4 | B được bật lại về 200 | Có thể vẫn [A] |
| T5 | Chu kỳ kiểm tra tiếp theo thành công | Có thể [A, B] |

Các mốc không phải SLA cố định: thời gian hội tụ chịu ảnh hưởng của scheduling, timeout probe, cơ chế cập nhật kết quả, phiên bản Spring Cloud, trạng thái discovery và các tầng cache. Một giá trị `interval: 5s` **không cam kết** trạng thái được phát hiện đúng sau 5 giây.

Nếu cần phản hồi nhanh hơn, giảm interval có thể tăng tần suất probe nhưng cũng tăng số request health từ các caller. Với N caller, M instance và mỗi caller thăm dò định kỳ, tổng tải health có thể trở nên đáng kể.

## 11. Kịch bản D — dừng hẳn tiến trình B

Thử nghiệm thứ hai là dừng tiến trình `catalog-b` trên cổng 18082, trong khi giữ cấu hình discovery tĩnh vẫn chứa hai địa chỉ.

Điều này khác với việc đặt `healthy=false`:

- Không còn HTTP server ở cổng 18082, nên lời gọi trực tiếp tới B có thể bị **connection refused** hoặc timeout, không có HTTP response thành công.
- Health supplier có thể phát hiện lỗi probe ở chu kỳ tiếp theo.
- Vì `SimpleDiscoveryClient` vẫn liệt kê địa chỉ B, **discovery không tự gỡ B** chỉ vì tiến trình bị dừng.
- Một request mới trước khi health được cập nhật có thể vẫn chọn B và gặp lỗi kết nối.

Khi chạy lại `catalog-b` với cùng `instance.id` và cổng, sau khi HTTP server sẵn sàng và health check thành công, B có thể quay lại tập ứng viên.

Lưu ý thao tác dừng tiến trình trong lab chỉ thực hiện trên tiến trình thử nghiệm của chính bạn, không tắt dịch vụ đang phục vụ người dùng thật.

### So sánh ba loại lỗi

| Tình huống | Health probe | Request trực tiếp tới B | Đường điều tra |
|---|---|---|---|
| `healthy=false` | HTTP 503 | `/api/whoami` vẫn có thể 200 | Kiểm tra health supplier và vòng cập nhật |
| Tiến trình B dừng | Không kết nối được | Không kết nối được hoặc timeout | Tiến trình, mạng, port và discovery |
| Endpoint nghiệp vụ B bị lỗi | Health có thể vẫn 200 | HTTP 5xx hoặc latency cao | Endpoint, dependency và log server |

Nếu chỉ dựa vào health check nhẹ, LoadBalancer có thể tiếp tục chọn một instance có endpoint nghiệp vụ đang lỗi. Đây là giới hạn của tín hiệu health, không phải lỗi của thuật toán chọn đích.

## 12. Trường hợp cả A và B đều unhealthy

Thử đánh dấu cả hai instance unhealthy bằng endpoint `/__test/ready`. Khi đó, **không tự giả định** bộ chọn chắc chắn trả danh sách rỗng hoặc HTTP `503`.

Hành vi khi **không còn instance healthy** phụ thuộc vào phiên bản và cách cấu hình `HealthCheckServiceInstanceListSupplier`, bao gồm chính sách khi health check không tìm được instance khỏe. Một số triển khai có cơ chế trả lại tập instance gốc trong tình huống tất cả health check thất bại, để tránh loại sạch ứng viên; các cấu hình khác hoặc supplier tự tạo có thể phát danh sách rỗng.

Bởi vậy hãy kiểm tra thực tế:

1. Supplier cuối cùng công bố danh sách gì: rỗng, danh sách ban đầu hay danh sách khác?
2. `Response<ServiceInstance>.hasServer()` có `true` không?
3. HTTP client có thực sự gửi request đến một instance hay thất bại trước khi gửi?
4. Nếu caller trả `503`, đó là status ứng dụng caller tạo ra hay response từ service đích?

Thí nghiệm này giúp tránh quy kết sai: một probe trả `503` không đồng nghĩa API caller chắc chắn nhận `503`, và một instance không healthy theo probe có thể vẫn đáp ứng endpoint thử nghiệm.

## 13. Thêm quan sát để chứng minh việc chuyển đích

Chỉ nhìn response body là cách nhanh nhất cho lab, nhưng production cần thêm log và metric.

### Nên ghi gì?

| Trường / metric | Mục đích |
|---|---|
| `serviceId=catalog-service` | Biết dịch vụ logic được gọi |
| Danh sách và số lượng instance từ discovery | Kiểm tra nguồn dữ liệu ban đầu |
| Số lượng instance sau health supplier | Phát hiện instance bị loại và được thêm lại |
| Instance được LoadBalancer chọn | Biết route thực tế |
| Kết quả probe từng instance | Phân biệt 200, HTTP 503 và lỗi kết nối |
| Timestamp probe và thời gian hội tụ | Đo độ trễ phát hiện lỗi/phục hồi |
| HTTP status từ endpoint nghiệp vụ | Không nhầm health probe với response nghiệp vụ |
| Connect/response timeout | Nhận diện lỗi sau khi đã chọn đích |
| Retry attempt và instance đã thử | Kiểm soát retries có gây tải khuếch đại không |
| `traceId` / `correlationId` | Liên kết caller với instance nhận request |

Có thể tận dụng `LoadBalancerLifecycle` để quan sát giai đoạn lựa chọn/kết thúc lời gọi, kết hợp Spring Boot Actuator và Micrometer cho metrics HTTP. Nếu cần quan sát sâu chuỗi supplier, bổ sung instrumentation cục bộ tại các lớp supplier phù hợp; không tạo thêm subscription ngoài ý muốn để tránh phát sinh probe thừa.

Các log nên giúp phân biệt:

~~~text
catalog-service -> catalog-b  [request được chọn]
catalog-b health -> DOWN      [probe báo unhealthy]
catalog-service -> catalog-a  [request được chọn sau cập nhật]
catalog-b health -> UP        [probe phục hồi]
catalog-service -> catalog-b  [đã nhận lại traffic]
~~~

Đây là **dòng log mục tiêu**, không phải format Spring Cloud mặc định. Đừng ghi token, cookie, request body nhạy cảm hoặc thông tin cá nhân vào log. Hạn chế cardinality nếu thêm instance ID vào metrics.

### Theo dõi độ trễ phục hồi

Đặt:

- `t_down`: thời điểm probe của B bắt đầu trả 503.
- `t_excluded`: thời điểm B biến mất khỏi danh sách ứng viên cuối.
- `t_up`: thời điểm probe B trả lại 200.
- `t_included`: thời điểm B trở lại danh sách ứng viên cuối.

Có thể đo xấp xỉ:

~~~text
Phát hiện lỗi:       t_excluded - t_down
Phát hiện phục hồi:  t_included - t_up
~~~

Giá trị thực tế chịu ảnh hưởng bởi chu kỳ probe và độ trễ cập nhật. Tách **thời điểm list cập nhật** khỏi **thời điểm có request đầu tiên đến B**, vì LoadBalancer có thể chưa chọn B ngay dù B đã được đưa lại vào danh sách.

## 14. Timeout và retry khi instance lỗi trong lúc được chọn

Health check không loại bỏ toàn bộ race condition. Một instance có thể chết ngay sau khi được LoadBalancer chọn, hoặc vừa bị quá tải nhưng chưa bị đánh dấu unhealthy.

Vì vậy RestClient/WebClient/OpenFeign vẫn cần:

- **Connect timeout:** không chờ kết nối vô hạn đến địa chỉ lỗi.
- **Read/response timeout:** giới hạn thời gian chờ phản hồi.
- **Retry có chọn lọc:** chỉ retry lỗi có khả năng phục hồi, số lần thử nhỏ, backoff có giới hạn.
- **Deadline tổng:** không để nhiều lần retry vượt thời gian caller cần trả lời.
- **Idempotency:** không tự retry thao tác có tác dụng phụ khi không đảm bảo chống thực thi lặp.
- **Quan sát lỗi trước và sau khi gửi HTTP:** `EmptyResponse` khác lỗi kết nối và khác HTTP 503 từ instance.

Một request có thể đã đến B, được server xử lý nhưng response bị mất. Retry sang A với lệnh ghi có thể tạo tác dụng phụ kép nếu không có idempotency key.

Không mặc định rằng bật retry sẽ tự chọn instance khác. Việc chọn lại cùng hay khác instance phụ thuộc tích hợp client, chính sách retry và supplier tương ứng.

## 15. Mở rộng cùng thí nghiệm sang WebClient và OpenFeign

Chúng ta sử dụng RestClient để bài thực hành có ít biến số. Đối với WebClient hoặc OpenFeign, nguyên lý chọn instance theo service ID vẫn là một:

**WebClient:**

~~~java
// webClient tạo từ @LoadBalanced WebClient.Builder
Mono<String> result = webClient.get()
    .uri("http://catalog-service/api/whoami")
    .retrieve()
    .bodyToMono(String.class);
~~~

Lỗi ở WebClient xuất hiện qua tín hiệu `onError` của reactive publisher; không dùng `block()` trong pipeline đang chạy trên event-loop để xem kết quả. Có thể quan sát qua controller reactive hoặc test subscriber.

**OpenFeign:**

~~~java
@FeignClient(name = "catalog-service")
interface CatalogClient {

    @GetMapping("/api/whoami")
    String whoAmI();
}
~~~

Với dependency và cấu hình OpenFeign tương thích, mỗi lời gọi cũng sử dụng service ID khi tích hợp Spring Cloud LoadBalancer. Tuy nhiên exception, timeout, retry và cách xử lý HTTP status là riêng của từng client. Health supplier cho `catalog-service` vẫn phải cập nhật danh sách trước khi mong đợi hành vi chuyển đích đã ổn định.

## 16. Checklist kiểm chứng và cách kết luận

Ghi lại một bảng quan sát cho mỗi giai đoạn:

| Giai đoạn | Probe A | Probe B | Danh sách sau health (quan sát) | Instance qua caller |
|---|---|---|---|---|
| Baseline | 200 | 200 | Dự kiến [A, B] | A và B |
| B unhealthy, trước khi refresh | 200 | 503 | Có thể vẫn [A, B] | Có thể còn B |
| B unhealthy, sau khi hội tụ | 200 | 503 | Dự kiến [A] nếu policy lọc B | Chủ yếu/chỉ A |
| B phục hồi, trước khi refresh | 200 | 200 | Có thể vẫn [A] | Có thể chỉ A |
| B phục hồi, sau khi hội tụ | 200 | 200 | Dự kiến [A, B] | B có cơ hội trở lại |
| B dừng tiến trình | 200 | Không kết nối | Tùy thời điểm cập nhật | Có thể lỗi trước khi hội tụ |
| Cả hai unhealthy | 503 | 503 | Tùy chính sách fallback/version | Cần quan sát, không suy đoán |

Bài thực hành đạt mục tiêu khi bạn có thể chỉ ra bằng bằng chứng:

1. **Mất health** ở B không đồng nhất với việc B đã bị gỡ khỏi discovery.
2. **Kết quả health supplier** tác động tới danh sách ứng viên mà LoadBalancer nhìn thấy.
3. **Phục hồi** không xảy ra chỉ vì thay một cờ; cần probe thành công và kết quả mới được công bố.
4. **Request đang chạy** hoặc request gửi trước lần cập nhật có thể thất bại ngay cả khi chính sách health hoạt động đúng.
5. **HTTP 503** từ health endpoint, HTTP 503 từ business endpoint và HTTP 503 do caller chủ động trả là ba nguồn khác nhau.
6. **Timeout, retry và observability** giúp kiểm soát giai đoạn chuyển tiếp nhưng không thay thế health check.

**Kết luận:** Mô phỏng một instance unhealthy rồi phục hồi là cách kiểm chứng trực quan rằng Spring Cloud LoadBalancer định tuyến dựa trên **tập `ServiceInstance` hiện được cung cấp**, không dựa trên trạng thái tức thời tuyệt đối của hệ thống. Discovery, health-check interval, cache, thuật toán chọn đích và hành vi RestClient/WebClient/OpenFeign cùng quyết định lúc lỗi được phát hiện, lúc request được chuyển đi và lúc instance trở lại phục vụ. Hãy đo những mốc này và xác minh danh sách supplier ở từng giai đoạn, thay vì kết luận chỉ từ một lời gọi HTTP.

