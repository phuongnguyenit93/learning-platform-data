# Thêm starter Eureka Client và cấu hình tên dịch vụ

## Mục tiêu

Sau bài học này, bạn có thể:

- Thêm Spring Cloud Netflix Eureka Client vào một ứng dụng Spring Boot bằng Maven hoặc Gradle.
- Khai báo tên dịch vụ bằng `spring.application.name` và địa chỉ Eureka Server.
- Giải thích cách một instance đăng ký, gửi heartbeat và nhận danh sách dịch vụ từ registry.
- Kiểm tra việc đăng ký và nhận biết các lỗi cấu hình thường gặp.

## Eureka Client làm gì?

Trong kiến trúc microservice, một dịch vụ thường chạy thành nhiều instance. Địa chỉ IP hoặc cổng của từng instance có thể thay đổi khi ứng dụng được triển khai lại, mở rộng hoặc chuyển sang máy khác. Nếu một service gọi service khác bằng địa chỉ cố định, cấu hình của bên gọi sẽ nhanh chóng lỗi thời.

Trong Spring Cloud Service Discovery, `DiscoveryClient` là abstraction để ứng dụng truy vấn các instance theo service ID, còn `ServiceRegistry` chuẩn hóa các thao tác đăng ký và hủy đăng ký. Eureka và Consul cung cấp các triển khai registry khác nhau cho những abstraction này. Bài học tập trung cấu hình Eureka Client để ứng dụng tham gia registry Eureka.

Eureka Server giữ registry chứa thông tin các instance đang được đăng ký. Eureka Client là thành phần chạy bên trong ứng dụng Spring Boot để ứng dụng tham gia registry đó. Client có thể đăng ký instance của chính nó, gửi heartbeat để thông báo instance vẫn hoạt động và tải danh sách instance của các dịch vụ khác.

Starter `spring-cloud-starter-netflix-eureka-client` đưa Eureka Client và phần tích hợp Spring Cloud vào classpath. Khi ứng dụng khởi động với cấu hình phù hợp, Spring Cloud tự cấu hình `DiscoveryClient` và Eureka client để thực hiện việc đăng ký, cập nhật registry và khám phá dịch vụ.

Eureka Client không tự biến ứng dụng thành Eureka Server. Ứng dụng client cần kết nối đến một Eureka Server đã chạy. Phần server sử dụng starter riêng `spring-cloud-starter-netflix-eureka-server`.

## 1. Thêm dependency Eureka Client

Spring Cloud quản lý các thư viện theo release train. Phiên bản release train phải tương thích với phiên bản Spring Boot của dự án. Hãy dùng Spring Cloud BOM để quản lý phiên bản các dependency Spring Cloud đồng bộ; không chọn một phiên bản riêng cho Eureka Client theo cảm tính.

### Maven

Khai báo Spring Cloud BOM trong `dependencyManagement`, sau đó thêm starter mà không ghi phiên bản trực tiếp:

~~~~xml
<properties>
    <spring-cloud.version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
~~~~

Thay `REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN` bằng release train phù hợp với Spring Boot đang dùng. Nếu dự án đã import Spring Cloud BOM ở cấp parent hoặc trong cấu hình quản lý dependency chung, không cần import BOM lần thứ hai.

### Gradle Kotlin DSL

Với Gradle, có thể import BOM bằng `platform`:

~~~~kotlin
val springCloudVersion = "REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN"

dependencies {
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion"))
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-client")
}
~~~~

Sau khi thêm dependency, đồng bộ lại project và kiểm tra dependency tree nếu Gradle hoặc Maven báo xung đột phiên bản. Không trộn các release train Spring Cloud khác nhau trong cùng một ứng dụng.

## 2. Đặt tên dịch vụ và cấu hình Eureka Server

Tên dịch vụ được khai báo bằng `spring.application.name`. Đây là định danh logic mà các service khác dùng khi tìm instance trong registry. Tên này không phải hostname, IP hay cổng mạng của một instance.

Ví dụ, ứng dụng quản lý kho có thể dùng tên `inventory-service`:

~~~~yaml
spring:
  application:
    name: inventory-service

server:
  port: 8081

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
    register-with-eureka: true
    fetch-registry: true
~~~~

Các thuộc tính quan trọng:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `spring.application.name` | Tên logic của dịch vụ. Các instance thuộc cùng một dịch vụ thường dùng chung tên này. |
| `server.port` | Cổng HTTP mà instance đang lắng nghe. Mỗi instance có thể dùng cổng khác nhau. |
| `eureka.client.service-url.defaultZone` | URL của Eureka Server mà client sẽ kết nối, thường kết thúc bằng `/eureka/`. |
| `eureka.client.register-with-eureka` | Cho phép instance đăng ký chính nó với registry. |
| `eureka.client.fetch-registry` | Cho phép client tải registry để khám phá các dịch vụ khác. |

Trong YAML, giữ nguyên cách viết `defaultZone` ở khóa cuối. Đây là khóa của map URL theo cấu hình Eureka; không đổi thành `default-zone`. Có thể khai báo URL bằng biến môi trường khi triển khai để mỗi môi trường dùng đúng registry của nó, thay vì đóng cứng `localhost` trong cấu hình production.

Hai thuộc tính `register-with-eureka` và `fetch-registry` thường có giá trị mặc định là `true`; khai báo tường minh trong ví dụ giúp người đọc hiểu rõ vai trò của client. Một ứng dụng chỉ cần đọc registry có thể tắt đăng ký bằng `register-with-eureka: false`. Hãy giữ `fetch-registry: true` nếu ứng dụng cần tìm các dịch vụ khác.

Tên dịch vụ nên ổn định, dễ đọc và thống nhất giữa các môi trường, ví dụ `inventory-service`, `order-service` hoặc `payment-service`. Không đưa port hay mã instance vào `spring.application.name`, vì nhiều instance của cùng một dịch vụ phải được gom dưới cùng một service ID. Eureka có thể hiển thị tên ứng dụng viết hoa trên dashboard; điều đó không có nghĩa giá trị cấu hình `spring.application.name` đã bị thay đổi.

## 3. Quá trình đăng ký và khám phá

Khi ứng dụng khởi động, Spring Cloud tạo Eureka client dựa trên dependency và cấu hình. Client đọc tên ứng dụng, địa chỉ server và thông tin instance, sau đó liên hệ Eureka Server để đăng ký. Trong thời gian chạy, client định kỳ gửi heartbeat và cập nhật registry theo cấu hình. Client cũng tải registry để biết những instance nào đang được công bố.

Luồng tổng quát:

~~~~mermaid
flowchart LR
    A[Ứng dụng inventory-service] -->|Đăng ký và heartbeat| E[Eureka Server]
    E -->|Registry các instance| B[Ứng dụng order-service]
    B -->|Tìm theo service ID| D[DiscoveryClient]
    D -->|Danh sách instance| B
    B -->|Gửi request đến instance đã chọn| A
~~~~

`spring.application.name` xác định service ID; mỗi tiến trình đang chạy là một instance của service đó. Vì vậy, khi chạy ba bản sao `inventory-service`, registry có thể lưu ba instance dưới cùng một tên dịch vụ nhưng với các địa chỉ hoặc instance ID khác nhau.

Eureka Client thường tự đăng ký khi ứng dụng khởi động; ứng dụng không cần tự gọi REST endpoint đăng ký. Với các phiên bản Spring Cloud hiện đại, việc có Eureka Client trên classpath đã kích hoạt cấu hình khám phá tương ứng. Không cần thêm `@EnableEurekaClient` hoặc `@EnableDiscoveryClient` chỉ để bật hành vi mặc định này.

## 4. Kiểm tra ứng dụng đã đăng ký

Giả sử Eureka Server đang chạy tại `http://localhost:8761` và ứng dụng `inventory-service` chạy tại cổng `8081`:

1. Khởi động Eureka Server và xác nhận dashboard truy cập được.
2. Khởi động ứng dụng có Eureka Client.
3. Xem log khởi động để kiểm tra client có kết nối được đến URL đã cấu hình hay không.
4. Mở dashboard Eureka và tìm ứng dụng `INVENTORY-SERVICE` trong danh sách instance.
5. Kiểm tra địa chỉ và cổng được công bố có thể truy cập từ các service cần gọi nó.

Việc ứng dụng khởi động thành công chưa chứng minh đăng ký thành công. Nếu dashboard chưa có instance, hãy kiểm tra URL registry, kết nối mạng và log của Eureka client. Trong môi trường phát triển, Eureka Server thường dùng cổng `8761`; khi triển khai thực tế, URL phải trỏ đến địa chỉ server mà container hoặc máy chạy ứng dụng có thể truy cập.

Có thể kiểm tra registry từ code thông qua `DiscoveryClient` của Spring Cloud Commons:

~~~~java
import java.net.URI;
import java.util.List;
import java.util.stream.Collectors;

import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Service;

@Service
public class ServiceLookup {

    private final DiscoveryClient discoveryClient;

    public ServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<URI> findInstances(String serviceId) {
        return discoveryClient.getInstances(serviceId)
                .stream()
                .map(ServiceInstance::getUri)
                .collect(Collectors.toList());
    }
}
~~~~

Ví dụ gọi `findInstances("inventory-service")` sẽ trả về URI của các instance mà client hiện biết trong registry. Kết quả có thể rỗng nếu service chưa đăng ký, registry chưa được tải hoặc service ID không khớp.

`DiscoveryClient` chỉ cung cấp thông tin instance. Nếu muốn gọi dịch vụ bằng tên logic và tự chọn một instance cho mỗi request, ứng dụng thường kết hợp Spring Cloud LoadBalancer với HTTP client được cấu hình hỗ trợ load balancing. Chỉ thêm Eureka Client không tự động làm mọi lệnh gọi HTTP dùng tên service trở thành request có cân bằng tải.

## 5. Phân biệt tên dịch vụ và định danh instance

`spring.application.name` đại diện cho cả dịch vụ. `eureka.instance.instance-id` đại diện cho một tiến trình cụ thể trong dịch vụ đó. Khi chạy nhiều bản sao, mỗi instance cần có định danh duy nhất trong registry. Trong cấu hình đơn giản, Spring Cloud có thể tạo instance ID mặc định. Nếu dashboard hiển thị các instance bị ghi đè hoặc khó phân biệt, hãy cấu hình `eureka.instance.instance-id` bằng một giá trị có tính duy nhất, chẳng hạn kết hợp tên host và cổng.

Địa chỉ instance được quảng bá cũng cần phù hợp với mạng triển khai. Thuộc tính `eureka.instance.prefer-ip-address: true` yêu cầu client ưu tiên công bố IP thay vì hostname. Chỉ bật tùy chọn này khi IP đó có thể được các client khác truy cập. Trong Kubernetes, Docker hoặc mạng nhiều subnet, một IP nội bộ có thể không dùng được từ nơi gọi; khi đó cần chọn hostname hoặc cấu hình địa chỉ quảng bá phù hợp với topology mạng.

## 6. Kết hợp health check

Heartbeat cho biết client vẫn liên lạc với Eureka Server; nó không nhất thiết chứng minh mọi chức năng nghiệp vụ của ứng dụng đều khỏe mạnh. Nếu muốn trạng thái sức khỏe của Spring Boot được phản ánh vào trạng thái instance, có thể thêm Spring Boot Actuator và bật health check integration của Eureka:

~~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~~

Khi bật tùy chọn này, hãy bảo đảm health indicator phản ánh đúng khả năng phục vụ request và cấu hình endpoint Actuator phù hợp. Không công khai các endpoint quản trị hoặc thông tin health chi tiết ra mạng công cộng nếu chưa có kiểm soát truy cập. Trạng thái trên registry cũng có thể trễ so với thay đổi thực tế vì client và server cần thời gian trao đổi heartbeat, cập nhật và loại bỏ instance hết hạn.

## 7. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Không thấy ứng dụng trên dashboard | Sai URL server, không truy cập được mạng, hoặc client không đăng ký | Kiểm tra `defaultZone`, DNS, firewall và log kết nối Eureka. |
| Log báo không liên hệ được Eureka Server | URL sai, server chưa chạy hoặc địa chỉ chỉ truy cập được từ máy khác | Thử truy cập URL từ chính môi trường chạy ứng dụng; kiểm tra cổng và đường dẫn `/eureka/`. |
| Tên ứng dụng không như mong đợi | Thiếu hoặc khai báo sai `spring.application.name` | Kiểm tra cấu hình theo profile và biến môi trường `SPRING_APPLICATION_NAME`. |
| Nhiều instance ghi đè hoặc khó phân biệt | Instance ID trùng nhau | Đặt `eureka.instance.instance-id` duy nhất cho từng tiến trình. |
| Tìm thấy instance nhưng gọi không được | Hostname/IP hoặc cổng được công bố không thể truy cập từ service gọi | Kiểm tra địa chỉ trong dashboard từ góc nhìn mạng của caller; điều chỉnh hostname/IP quảng bá và port. |
| Instance dừng nhưng vẫn còn trong registry một thời gian | Registry chưa nhận biết heartbeat đã ngừng hoặc cơ chế tự bảo vệ trì hoãn eviction | Kiểm tra heartbeat, lease và log của server; không giả định instance biến mất ngay lập tức sau khi tiến trình dừng. |
| Không tìm thấy service qua `DiscoveryClient` | Registry chưa đồng bộ hoặc service ID không khớp | Kiểm tra `fetch-registry`, tên service và danh sách instance mà client đang nhìn thấy. |

Khi triển khai production, hãy bảo vệ Eureka Server bằng mạng riêng, xác thực và TLS theo yêu cầu hạ tầng. Chỉ cho các service cần thiết truy cập registry; không xem dashboard hoặc endpoint đăng ký là tài nguyên công khai. Đồng thời quản lý URL registry và thông tin xác thực bằng cấu hình môi trường hoặc secret store, không commit bí mật vào repository.

## Ghi nhớ

- Thêm `spring-cloud-starter-netflix-eureka-client` để ứng dụng Spring Boot tham gia cơ chế discovery của Eureka.
- Dùng Spring Cloud BOM tương thích với Spring Boot để quản lý phiên bản dependency.
- Đặt `spring.application.name` thành service ID ổn định; port và instance ID mô tả từng instance riêng lẻ.
- Cấu hình `eureka.client.service-url.defaultZone` trỏ đến Eureka Server có thể truy cập từ môi trường chạy ứng dụng.
- Xác minh đăng ký trên dashboard và bằng `DiscoveryClient`; kiểm tra địa chỉ quảng bá trước khi kết luận service có thể gọi được.
- Eureka Client cung cấp discovery; cân bằng tải phía client cần thành phần phù hợp như Spring Cloud LoadBalancer.
