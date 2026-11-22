# Chuẩn bị endpoint trả về định danh bản sao để quan sát

Khi một service chạy nhiều bản sao, client gọi bằng service ID và Spring Cloud LoadBalancer chọn một instance để xử lý mỗi request. Nhìn từ phía client, các request đều gửi tới cùng một địa chỉ logic, chẳng hạn `reservation-service`. Nếu response không cho biết instance nào đã xử lý request, ta khó quan sát kết quả phân phối tải và khó điều tra trường hợp chỉ một bản sao gặp lỗi.

Bài học này thuộc chương **Thiết lập dự án** của module `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING`. Module tập trung vào cân bằng tải phía client của Spring Cloud LoadBalancer: chọn `ServiceInstance` theo service ID, discovery, health check và chính sách định tuyến; thực hành tích hợp `RestClient`, `WebClient`, OpenFeign, retry/timeout và quan sát lỗi. Endpoint định danh là một điểm quan sát nhỏ được chuẩn bị trước: mỗi bản sao trả về một mã riêng để ta nhận biết request đã tới đâu.

Sau bài học, bạn có thể:

- Phân biệt service ID với định danh riêng của từng instance.
- Cấu hình một định danh ổn định cho mỗi bản sao của service.
- Tạo endpoint HTTP trả về thông tin nhận diện tối thiểu dưới dạng JSON.
- Chạy nhiều bản sao và xác minh từng bản sao trả về định danh khác nhau.
- Dùng endpoint qua một client có LoadBalancer để quan sát instance được chọn.
- Nhận biết giới hạn của endpoint chẩn đoán và cách bảo vệ thông tin vận hành.

## 1. Vì sao cần endpoint định danh instance?

Giả sử service `reservation-service` đang chạy ba bản sao:

- Bản sao thứ nhất chạy tại `10.0.1.11:8080`.
- Bản sao thứ hai chạy tại `10.0.1.12:8080`.
- Bản sao thứ ba chạy tại `10.0.1.13:8080`.

Client chỉ biết service ID là `reservation-service`. Service discovery cung cấp danh sách instance, còn Spring Cloud LoadBalancer chọn một instance trong danh sách đó. Sau khi request tới server, ứng dụng cần một cách đơn giản để trả lời câu hỏi: “Bản sao nào vừa xử lý request này?”

Ta có thể thêm endpoint:

```http
GET /internal/instance
```

Endpoint trả về JSON ví dụ:

~~~json
{
  "serviceId": "reservation-service",
  "instanceId": "reservation-2",
  "zone": "zone-a",
  "version": "1.4.0"
}
~~~

Mỗi bản sao có cùng service ID nhưng có instance ID khác nhau. Khi gọi endpoint qua LoadBalancer, client có thể quan sát instance ID trong response để thấy request đã được chuyển tới bản sao nào.

Luồng quan sát:

~~~mermaid
flowchart LR
    A["Client gọi reservation-service"] --> B["Spring Cloud LoadBalancer"]
    B --> C["Chọn ServiceInstance"]
    C --> D["Replica 1"]
    C --> E["Replica 2"]
    C --> F["Replica 3"]
    D --> G["GET /internal/instance"]
    E --> G
    F --> G
    G --> H["JSON chứa instanceId của bản sao"]
~~~

Endpoint chỉ cung cấp thông tin nhận diện. Nó không tự đăng ký instance vào service discovery, không chọn instance và không thực hiện cân bằng tải. Các chức năng đó vẫn thuộc service registry và Spring Cloud LoadBalancer.

## 2. Phân biệt service ID và instance ID

Hai khái niệm này có vai trò khác nhau:

| Khái niệm | Ví dụ | Ý nghĩa |
|---|---|---|
| Service ID | `reservation-service` | Tên logic mà client dùng để gọi một dịch vụ. |
| Instance ID | `reservation-2` | Định danh một bản sao cụ thể của dịch vụ đó. |
| Địa chỉ instance | `10.0.1.12:8080` | Host và port mà client kết nối sau khi instance được chọn. |
| Version | `1.4.0` | Phiên bản ứng dụng đang chạy trên bản sao. |

Thông thường, service ID được cấu hình bằng `spring.application.name`. Các bản sao của cùng một service dùng chung tên này để được đăng ký dưới cùng một dịch vụ logic.

Instance ID phải phân biệt được các bản sao cùng service ID. Nếu tất cả bản sao đều trả về `reservation-service` làm instance ID thì endpoint không giúp xác định request đã tới bản sao nào.

Trong bài này, ta dùng thuộc tính riêng `app.instance.id` để phục vụ endpoint chẩn đoán. Thuộc tính này không tự động trở thành `ServiceInstance.getInstanceId()` trong mọi hệ thống discovery. Nếu muốn định danh trả về từ endpoint trùng với định danh trong registry, cần cấu hình thuộc tính instance ID tương ứng của registry đang dùng.

## 3. Cấu hình định danh riêng cho từng bản sao

Trước tiên, khai báo tên service và các thuộc tính nhận diện trong `application.yml`:

~~~yaml
spring:
  application:
    name: reservation-service

server:
  port: ${SERVER_PORT:8080}

app:
  instance:
    id: ${APP_INSTANCE_ID:${HOSTNAME:${COMPUTERNAME:local}}}
    zone: ${APP_INSTANCE_ZONE:local}
    version: ${APP_VERSION:dev}
~~~

Giải thích:

- `spring.application.name` là service ID dùng trong giao tiếp giữa các service.
- `server.port` xác định cổng HTTP của tiến trình.
- `app.instance.id` là mã riêng của bản sao. Ứng dụng ưu tiên biến môi trường `APP_INSTANCE_ID`; nếu không có, cấu hình thử dùng hostname của môi trường chạy và cuối cùng là `local`.
- `app.instance.zone` là thông tin vùng triển khai nếu hệ thống có khái niệm zone; khi chạy local có thể để `local`.
- `app.instance.version` cho biết phiên bản build hoặc release đang chạy.

Giá trị dự phòng `local` chỉ thuận tiện khi chạy một tiến trình để phát triển. Khi chạy nhiều bản sao, hãy cấp một ID riêng cho từng bản sao. Không để nhiều replica cùng dùng một giá trị mặc định, vì response sẽ không thể phân biệt chúng.

Có thể truyền giá trị bằng tham số dòng lệnh khi chạy hai tiến trình local:

~~~bash
java -jar reservation-service.jar --server.port=8081 --app.instance.id=reservation-1
java -jar reservation-service.jar --server.port=8082 --app.instance.id=reservation-2
~~~

Hai tiến trình có cùng `spring.application.name`, nhưng có port và instance ID khác nhau. Mỗi lệnh nên được chạy trong một terminal riêng.

Trong Kubernetes, có thể lấy tên Pod làm instance ID bằng Downward API:

~~~yaml
env:
  - name: APP_INSTANCE_ID
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
~~~

Tên Pod thường phân biệt được các replica trong cùng một workload. Nếu nền tảng triển khai dùng cơ chế đặt hostname hoặc định danh khác, hãy chọn một giá trị duy nhất, ổn định trong vòng đời của replica và truyền vào `APP_INSTANCE_ID`.

Không nên tạo một UUID mới mỗi lần gọi endpoint. Instance ID cần giữ nguyên giữa các request của cùng một tiến trình; nếu thay đổi theo từng request, ta sẽ nhầm định danh request với định danh bản sao.

## 4. Ánh xạ cấu hình vào kiểu Java

Dùng `@ConfigurationProperties` để gom các thuộc tính liên quan vào một kiểu dữ liệu:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.instance")
public record InstanceIdentityProperties(
    String id,
    String zone,
    String version
) {}
~~~

Bật quét configuration properties ở lớp ứng dụng chính:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ReservationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReservationApplication.class, args);
    }
}
~~~

Spring Boot sẽ bind các giá trị trong `app.instance` vào `InstanceIdentityProperties`. Các thành phần khác có thể inject kiểu này để sử dụng định danh của tiến trình.

Nếu dự án đã dùng `@EnableConfigurationProperties(InstanceIdentityProperties.class)` thì có thể giữ cách đăng ký đó thay cho `@ConfigurationPropertiesScan`. Chỉ cần bảo đảm lớp properties được đăng ký trong Spring context.

## 5. Tạo response DTO và endpoint

Không trả toàn bộ đối tượng cấu hình hoặc thông tin môi trường ra HTTP. Hãy định nghĩa response DTO chỉ chứa những trường cần thiết cho việc quan sát:

~~~java
public record InstanceIdentityResponse(
    String serviceId,
    String instanceId,
    String zone,
    String version
) {}
~~~

Tiếp theo, tạo controller:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal")
public class InstanceIdentityController {

    private final InstanceIdentityProperties identity;
    private final Environment environment;

    public InstanceIdentityController(
            InstanceIdentityProperties identity,
            Environment environment) {
        this.identity = identity;
        this.environment = environment;
    }

    @GetMapping(
        value = "/instance",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public InstanceIdentityResponse getInstanceIdentity() {
        String serviceId = environment.getProperty(
            "spring.application.name",
            "unknown"
        );

        return new InstanceIdentityResponse(
            serviceId,
            identity.id(),
            identity.zone(),
            identity.version()
        );
    }
}
~~~

Controller đọc service ID từ cấu hình Spring và lấy instance ID, zone, version từ properties đã bind. Spring MVC dùng message converter với Jackson để chuyển record thành JSON response.

Khi gọi endpoint, response có dạng:

~~~json
{
  "serviceId": "reservation-service",
  "instanceId": "reservation-1",
  "zone": "local",
  "version": "dev"
}
~~~

Nếu gọi tới bản sao thứ hai, trường `instanceId` sẽ là `reservation-2`. Các trường còn lại có thể giống nhau nếu hai bản sao chạy cùng cấu hình zone và version.

## 6. Kiểm tra từng bản sao trực tiếp

Trước khi kiểm tra LoadBalancer, hãy gọi trực tiếp từng tiến trình để xác nhận cấu hình và endpoint hoạt động.

Với hai tiến trình đang chạy ở port 8081 và 8082:

~~~bash
curl http://localhost:8081/internal/instance
curl http://localhost:8082/internal/instance
~~~

Kết quả kỳ vọng:

~~~json
{
  "serviceId": "reservation-service",
  "instanceId": "reservation-1",
  "zone": "local",
  "version": "dev"
}
~~~

~~~json
{
  "serviceId": "reservation-service",
  "instanceId": "reservation-2",
  "zone": "local",
  "version": "dev"
}
~~~

Nếu đang dùng PowerShell:

~~~powershell
Invoke-RestMethod http://localhost:8081/internal/instance
Invoke-RestMethod http://localhost:8082/internal/instance
~~~

Ở bước này, ta gọi trực tiếp host và port nên chưa kiểm tra cơ chế cân bằng tải. Mục đích là xác nhận mỗi tiến trình trả về đúng định danh mà nó được cấu hình.

Nếu cả hai response cùng có một instance ID, hãy kiểm tra tham số khởi chạy, biến môi trường và thứ tự ưu tiên cấu hình. Spring Boot cho phép tham số dòng lệnh ghi đè giá trị trong `application.yml`, vì vậy cần xác minh giá trị cuối cùng mà ứng dụng nhận được.

## 7. Quan sát instance được chọn qua LoadBalancer

Sau khi hai bản sao được đăng ký trong cơ chế discovery mà ứng dụng sử dụng, client gọi bằng service ID thay vì địa chỉ cố định. Ví dụ, với một `RestClient` đã được cấu hình `@LoadBalanced`:

~~~java
InstanceIdentityResponse response = restClient.get()
    .uri("http://reservation-service/internal/instance")
    .retrieve()
    .body(InstanceIdentityResponse.class);
~~~

Client gửi request tới địa chỉ logic `reservation-service`. Spring Cloud LoadBalancer lấy danh sách instance khả dụng, chọn một instance, rồi chuyển request tới host và port tương ứng. Endpoint trên instance được chọn trả về instance ID của chính nó.

Gọi nhiều lần và ghi lại trường `instanceId` sẽ giúp quan sát các bản sao được chọn. Ví dụ, kết quả có thể lần lượt là:

~~~text
reservation-1
reservation-2
reservation-1
reservation-2
reservation-1
~~~

Đây chỉ là một kết quả minh họa. Không nên yêu cầu số lần xuất hiện của từng ID phải bằng nhau tuyệt đối. Kết quả thực tế phụ thuộc danh sách instance mà discovery cung cấp, chiến lược chọn instance, trạng thái khả dụng, cấu hình theo service và thời điểm request được gửi.

Endpoint định danh giúp trả lời “request đã tới replica nào?”. Để giải thích vì sao replica đó được chọn, cần quan sát thêm danh sách instance, cấu hình LoadBalancer, health check và thuật toán định tuyến.

Nếu client luôn nhận cùng một instance ID, hãy kiểm tra lần lượt:

1. Các replica có thực sự khởi động và đăng ký cùng service ID không?
2. Service discovery có trả về đủ các instance không?
3. Client có dùng HTTP client được đánh dấu `@LoadBalanced` và gọi bằng service ID không?
4. Các instance có đang được xem là khả dụng không?
5. Cấu hình theo service hoặc chiến lược chọn instance có giới hạn danh sách ứng viên không?
6. Response có đang được cache ở một lớp khác không?

Đừng kết luận LoadBalancer bị lỗi chỉ vì một chuỗi request ngắn chưa đi qua tất cả replica. Hãy quan sát đủ số request, xác minh registry và đối chiếu cấu hình đang chạy.

## 8. Liên hệ instance ID với service discovery

Trong bài này, `app.instance.id` là dữ liệu ứng dụng dùng để trả lời endpoint. Service registry có thể có trường định danh instance riêng. Hai giá trị chỉ trùng nhau khi ta chủ động cấu hình.

Ví dụ, nếu dự án dùng Eureka, có thể kết hợp service ID và instance ID của ứng dụng trong cấu hình Eureka:

~~~yaml
eureka:
  instance:
    instance-id: ${spring.application.name}:${app.instance.id}
~~~

Khi đó, registry có thể phân biệt các bản đăng ký của cùng service bằng instance ID được cấu hình. Cách khai báo cụ thể phụ thuộc discovery client và phiên bản thư viện mà dự án sử dụng. Với Consul hoặc registry khác, hãy dùng thuộc tính định danh instance tương ứng của nền tảng đó.

Cần phân biệt ba giá trị khi điều tra:

- **Service ID**: tên logic mà client yêu cầu.
- **Registry instance ID**: định danh mà discovery client đăng ký và trả về trong thông tin instance, nếu nền tảng hỗ trợ.
- **Application instance ID**: giá trị ứng dụng trả về từ endpoint chẩn đoán.

Nếu ba giá trị được đồng bộ, việc đối chiếu log, registry và HTTP response thuận tiện hơn. Nếu chúng khác nhau, hãy ghi rõ quy ước ánh xạ để người vận hành không hiểu nhầm.

## 9. Bảo vệ endpoint và giới hạn thông tin trả về

Endpoint định danh hữu ích trong môi trường phát triển, kiểm thử và quan sát nội bộ. Tuy nhiên, mọi endpoint chẩn đoán đều cần được xem xét trước khi đưa ra môi trường công khai.

Một số nguyên tắc:

- Chỉ trả về các trường cần thiết như service ID, instance ID, zone và version.
- Không trả về biến môi trường, system properties, đường dẫn file, thông tin xác thực, token, cấu hình kết nối hoặc nội dung bí mật.
- Nếu endpoint chỉ dành cho nội bộ, áp dụng chính sách mạng hoặc xác thực/ủy quyền phù hợp để giới hạn người gọi.
- Không đưa dữ liệu cá nhân hoặc thông tin nhạy cảm vào instance ID.
- Không dùng endpoint này thay cho readiness hoặc liveness probe.

Một response thành công từ `/internal/instance` chỉ cho biết request đã tới ứng dụng và controller có thể trả lời. Nó không chứng minh cơ sở dữ liệu, message broker hoặc các dịch vụ phụ thuộc đều khỏe mạnh. Hãy dùng Spring Boot Actuator health endpoint và readiness/liveness probe cho mục đích kiểm tra sức khỏe.

Trong môi trường có Spring Security, đường dẫn `/internal/instance` có thể bị bảo vệ theo cấu hình hiện tại. Chỉ cho phép các caller nội bộ cần thiết truy cập; tránh mở toàn bộ nhóm endpoint nội bộ ra Internet để tiện kiểm thử.

## 10. Checklist xác minh

Trước khi dùng endpoint trong bài thực hành LoadBalancer, kiểm tra các điều kiện sau:

| Kiểm tra | Kết quả mong đợi |
|---|---|
| Cùng một service có nhiều bản sao | Các bản sao dùng chung service ID. |
| Định danh từng bản sao | Mỗi bản sao có instance ID riêng. |
| Tính ổn định | Một bản sao trả cùng instance ID qua nhiều request. |
| Endpoint | `GET /internal/instance` trả HTTP 200 và JSON hợp lệ. |
| Trường nhận diện | Response có service ID, instance ID và thông tin cần thiết. |
| Gọi trực tiếp | Mỗi host/port trả đúng ID đã cấu hình. |
| Gọi qua LoadBalancer | Client dùng service ID và quan sát được ID của instance được chọn. |
| Discovery | Registry cung cấp danh sách các instance đang hoạt động. |
| Bảo mật | Response không chứa secrets hoặc thông tin môi trường không cần thiết. |

Khi một request qua LoadBalancer trả về instance ID, ta đã có bằng chứng ở tầng ứng dụng về bản sao xử lý request đó. Kết hợp dữ liệu này với log, correlation ID, registry và trạng thái health check sẽ giúp phân tích hành vi định tuyến rõ ràng hơn.

## 11. Những điểm cần nhớ

- Service ID xác định dịch vụ logic; instance ID xác định một bản sao cụ thể.
- Các replica của cùng service dùng chung `spring.application.name`, nhưng phải có định danh riêng nếu cần quan sát từng replica.
- Định danh phải ổn định trong vòng đời của replica và được cấp từ cấu hình hoặc nền tảng triển khai.
- Endpoint `GET /internal/instance` chỉ trả thông tin nhận diện; nó không thực hiện discovery hoặc load balancing.
- Gọi trực tiếp từng port giúp xác minh cấu hình của từng tiến trình; gọi qua client có LoadBalancer giúp quan sát instance được chọn.
- Application instance ID không tự động đồng nhất với registry instance ID; cần cấu hình ánh xạ nếu muốn dùng chung.
- Giữ response tối thiểu và bảo vệ endpoint theo phạm vi truy cập nội bộ.

Sau khi chuẩn bị endpoint này, các bài thực hành tiếp theo có thể gọi cùng một service ID nhiều lần và đọc instance ID trong response để quan sát kết quả chọn `ServiceInstance` của Spring Cloud LoadBalancer.

