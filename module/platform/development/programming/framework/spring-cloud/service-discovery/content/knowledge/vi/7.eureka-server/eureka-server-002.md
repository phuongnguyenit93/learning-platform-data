# Khởi tạo máy chủ bằng starter và `@EnableEurekaServer`

## Mục tiêu

Sau bài học này, bạn có thể:

- Tạo một ứng dụng Spring Boot đóng vai trò Eureka Server.
- Thêm đúng starter và kích hoạt server bằng `@EnableEurekaServer`.
- Cấu hình một registry độc lập để các Eureka Client đăng ký và tra cứu dịch vụ.
- Phân biệt cấu hình server độc lập với cấu hình cụm Eureka nhiều node.
- Khởi động, xác minh và bảo vệ Eureka Server trong môi trường triển khai.

## Eureka Server giữ vai trò gì?

Trong Spring Cloud Service Discovery, ứng dụng cần một nơi lưu thông tin các instance đang cung cấp dịch vụ. Eureka Server cung cấp registry đó. Eureka Client trong từng ứng dụng sẽ đăng ký instance, gửi heartbeat và lấy danh sách instance từ server.

Spring Cloud Commons định nghĩa các abstraction như `DiscoveryClient` để tra cứu instance và `ServiceRegistry` để đăng ký hoặc hủy đăng ký. Eureka là một implementation cụ thể của cơ chế này. Eureka Server là tiến trình lưu và phục vụ registry; Eureka Client là thành phần được thêm vào các ứng dụng cần tham gia registry. Hai vai trò thường chạy trong các ứng dụng riêng biệt.

Starter `spring-cloud-starter-netflix-eureka-server` cung cấp phần tích hợp server. Annotation `@EnableEurekaServer` bật cấu hình Eureka Server trong ứng dụng Spring Boot. Chỉ thêm dependency chưa đủ để biến ứng dụng thành server.

## 1. Chuẩn bị dependency

Spring Boot và Spring Cloud phải dùng các phiên bản tương thích. Hãy chọn Spring Cloud release train phù hợp với phiên bản Spring Boot của dự án và dùng Spring Cloud BOM để quản lý phiên bản đồng bộ. Starter Eureka Server bên dưới không khai báo phiên bản riêng vì BOM quản lý phiên bản đó.

### Maven

Thêm BOM vào `dependencyManagement` và starter vào `dependencies`:

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
        <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
    </dependency>
</dependencies>
~~~~

Thay `REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN` bằng release train tương thích với Spring Boot đang sử dụng. Nếu dự án đã import Spring Cloud BOM ở parent hoặc trong cấu hình dependency chung, giữ lại BOM hiện có và chỉ thêm starter.

### Gradle Kotlin DSL

Với Gradle Kotlin DSL, có thể import BOM bằng `platform`:

~~~~kotlin
val springCloudVersion = "REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN"

dependencies {
    implementation(platform("org.springframework.cloud:spring-cloud-dependencies:$springCloudVersion"))
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-server")
}
~~~~

Sau khi đồng bộ dependency, kiểm tra dependency tree nếu build báo xung đột. Không trộn các release train Spring Cloud khác nhau trong cùng ứng dụng.

## 2. Tạo lớp khởi động Eureka Server

Tạo một ứng dụng Spring Boot thông thường và đặt `@EnableEurekaServer` trên lớp cấu hình chính. Ví dụ:

~~~~java
package com.example.discoveryserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class DiscoveryServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(DiscoveryServerApplication.class, args);
    }
}
~~~~

`@SpringBootApplication` bật cơ chế cấu hình và component scan của Spring Boot. `@EnableEurekaServer` kích hoạt các thành phần cần thiết để ứng dụng cung cấp Eureka registry và dashboard. Đặt lớp này trong package gốc để các component khác của ứng dụng được scan theo cấu trúc thông thường.

Không đặt `@EnableEurekaServer` trong mọi microservice. Các ứng dụng nghiệp vụ chỉ cần đăng ký và tìm dịch vụ thường thêm Eureka Client starter. Chỉ ứng dụng đóng vai trò registry mới dùng Eureka Server starter và annotation này.

## 3. Cấu hình server độc lập

Với môi trường học tập hoặc phát triển cục bộ, bắt đầu bằng một Eureka Server duy nhất. Tạo `src/main/resources/application.yml`:

~~~~yaml
spring:
  application:
    name: discovery-server

server:
  port: 8761

eureka:
  client:
    register-with-eureka: false
    fetch-registry: false
~~~~

Ý nghĩa các thuộc tính:

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `spring.application.name` | Tên ứng dụng Spring Boot; giúp nhận diện tiến trình server trong log và cấu hình. |
| `server.port` | Cổng HTTP mà Eureka Server lắng nghe. `8761` là cổng thường dùng trong ví dụ Eureka. |
| `eureka.client.register-with-eureka` | Tắt việc server tự đăng ký như một client với registry. |
| `eureka.client.fetch-registry` | Tắt việc server tải registry từ peer khác khi đang chạy độc lập. |

Hai tùy chọn cuối làm rõ chế độ standalone: server không cần đăng ký chính nó hoặc tải registry từ một Eureka Server khác. Các Eureka Client vẫn có thể đăng ký vào server này và tải registry từ nó.

Không nhầm `spring.application.name` với service ID mà server quản lý. Ví dụ, `discovery-server` là tên ứng dụng registry; `inventory-service` và `order-service` là các tên dịch vụ do những client đăng ký.

## 4. Khởi động và xác minh

Sau khi cấu hình dependency, lớp khởi động và YAML, chạy ứng dụng bằng Maven hoặc Gradle:

~~~~bash
./mvnw spring-boot:run
~~~~

Hoặc:

~~~~bash
./gradlew bootRun
~~~~

Trên Windows có thể dùng `mvnw.cmd` hoặc `gradlew.bat` tương ứng. Khi ứng dụng khởi động thành công:

1. Kiểm tra log cho biết Spring Boot đã khởi động trên cổng `8761`.
2. Mở `http://localhost:8761` để xem dashboard Eureka.
3. Kiểm tra dashboard hiển thị server và danh sách instance đã đăng ký.
4. Khởi động một ứng dụng có Eureka Client trỏ đến `http://localhost:8761/eureka/`.
5. Xác nhận service ID của client xuất hiện trên dashboard sau khi client đăng ký.

Dashboard có thể hiển thị registry trống khi chưa có client nào đăng ký. Điều đó không có nghĩa server chưa hoạt động. Ngược lại, việc mở được trang dashboard chỉ xác nhận giao diện HTTP truy cập được; cần kiểm tra client đăng ký thành công để xác nhận luồng discovery hoạt động từ đầu đến cuối.

## 5. Cấu hình cụm Eureka nhiều node

Một Eureka Server đơn lẻ phù hợp cho môi trường phát triển hoặc thử nghiệm. Trong triển khai cần khả năng chịu lỗi, có thể chạy nhiều Eureka Server và cấu hình chúng làm peer. Mỗi node trao đổi registry với các peer được khai báo để thông tin đăng ký được sao chép giữa các node.

Ví dụ node `eureka-a` chạy ở `8761` và node `eureka-b` chạy ở `8762`. Cấu hình của node A trỏ đến B:

~~~~yaml
spring:
  application:
    name: discovery-server

server:
  port: 8761

eureka:
  instance:
    hostname: eureka-a
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: http://eureka-b:8762/eureka/
~~~~

Node B cấu hình hostname và port của chính nó, đồng thời trỏ `defaultZone` về node A:

~~~~yaml
spring:
  application:
    name: discovery-server

server:
  port: 8762

eureka:
  instance:
    hostname: eureka-b
  client:
    register-with-eureka: true
    fetch-registry: true
    service-url:
      defaultZone: http://eureka-a:8761/eureka/
~~~~

Các hostname trong ví dụ phải phân giải được và các node phải kết nối được với nhau qua mạng. Trong triển khai thật, thay chúng bằng DNS hoặc địa chỉ nội bộ ổn định của hạ tầng. Với nhiều hơn hai node, mỗi node khai báo các peer còn lại theo cùng nguyên tắc. Cần tránh để node chỉ trỏ về chính nó trong cấu hình peer vì như vậy không tạo ra trao đổi registry giữa các node.

Các client nghiệp vụ nên được cấu hình để truy cập các endpoint Eureka phù hợp với topology, chẳng hạn qua danh sách peer hoặc địa chỉ cân bằng tải nội bộ đã được thiết kế cho Eureka. Khi triển khai cluster, hãy kiểm tra cả khả năng kết nối hai chiều giữa peer và khả năng client truy cập các endpoint được công bố.

## 6. Hiểu registry, heartbeat và self-preservation

Eureka Server lưu trạng thái các instance mà client đăng ký. Client định kỳ gửi heartbeat để gia hạn lease. Nếu server không nhận heartbeat trong khoảng thời gian quy định, instance có thể bị xem là hết hạn và được loại khỏi registry. Client cũng định kỳ tải registry và có thể giữ bản cache cục bộ để tra cứu giữa các lần đồng bộ.

Trong điều kiện mạng không ổn định, server có thể nhận ít heartbeat hơn dự kiến dù nhiều ứng dụng vẫn đang chạy. Cơ chế self-preservation giúp hạn chế việc loại bỏ hàng loạt instance khi server nghi ngờ có sự cố mạng diện rộng. Vì vậy, registry có thể tạm thời chứa thông tin cũ. Không nên xem một entry trong registry là phép đo sức khỏe tức thời hoặc bằng chứng chắc chắn rằng instance đang phục vụ request thành công.

Khi vận hành, cần quan sát log heartbeat, trạng thái peer, số lượng instance và các cảnh báo kết nối. Chỉ điều chỉnh lease hoặc self-preservation sau khi hiểu đặc điểm mạng, chu kỳ heartbeat và tác động đến thời gian phát hiện instance lỗi. Tắt self-preservation để làm dashboard sạch nhanh hơn có thể khiến registry loại bỏ nhầm các instance trong lúc mất kết nối.

## 7. Bảo mật Eureka Server

Registry chứa địa chỉ và thông tin định tuyến nội bộ của các dịch vụ, do đó cần được bảo vệ như một thành phần hạ tầng. Trong production:

- Đặt Eureka Server trong mạng nội bộ và giới hạn nguồn truy cập bằng network policy, firewall hoặc security group.
- Bật xác thực cho dashboard và API registry; cấp thông tin xác thực riêng cho client được phép đăng ký hoặc tra cứu.
- Dùng HTTPS/TLS khi lưu lượng đi qua mạng không tin cậy và quản lý chứng thư phù hợp.
- Không công khai dashboard, API đăng ký hoặc endpoint quản trị trực tiếp ra Internet.
- Lưu URL, username và password trong biến môi trường hoặc secret store; không commit bí mật vào repository.
- Nếu ứng dụng dùng Spring Security, cấu hình CSRF phù hợp cho API Eureka mà client cần gọi, đồng thời vẫn yêu cầu xác thực và phân quyền.
- Nếu bật Spring Boot Actuator, chỉ expose những endpoint thật sự cần thiết và áp dụng kiểm soát truy cập tương ứng.

Ví dụ cấu hình server ở trên chỉ dành cho môi trường local. Trước khi triển khai, hãy bổ sung xác thực, TLS và giới hạn truy cập theo chính sách hạ tầng.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Ứng dụng khởi động nhưng không có dashboard Eureka | Thiếu `@EnableEurekaServer` hoặc thiếu server starter | Kiểm tra dependency và annotation trên lớp cấu hình chính. |
| Không thể mở cổng `8761` | Port bị tiến trình khác chiếm hoặc cấu hình `server.port` khác | Kiểm tra log khởi động và cổng thực tế của ứng dụng. |
| Dashboard mở được nhưng registry trống | Chưa có client đăng ký hoặc client trỏ sai URL | Kiểm tra `defaultZone` phía client và log đăng ký. |
| Server peer không nhìn thấy nhau | DNS, firewall, port hoặc `defaultZone` sai | Kiểm tra phân giải hostname và kết nối giữa các node từ đúng môi trường chạy. |
| Instance đã dừng nhưng vẫn xuất hiện | Heartbeat hết hạn chưa được xử lý hoặc self-preservation đang giữ registry | Kiểm tra lease, log server và tình trạng kết nối mạng; chờ quá trình cập nhật registry. |
| Client nhận registry cũ | Đồng bộ registry hoặc kết nối peer gặp vấn đề | Kiểm tra trạng thái peer, log fetch registry và khả năng kết nối của client. |
| Client bị từ chối khi đăng ký | Sai thông tin xác thực, TLS hoặc CSRF/security filter chặn request | Kiểm tra cấu hình bảo mật trên server và cấu hình tương ứng ở client. |

## Ghi nhớ

- Dùng `spring-cloud-starter-netflix-eureka-server` để thêm thành phần server.
- Đặt `@EnableEurekaServer` trên lớp cấu hình Spring Boot để kích hoạt Eureka Server.
- Với server độc lập, đặt `register-with-eureka: false` và `fetch-registry: false`.
- Với cụm nhiều node, cấu hình peer qua `eureka.client.service-url.defaultZone` và bảo đảm hostname cùng port truy cập được.
- Dashboard trống vẫn có thể là server đang hoạt động bình thường nếu chưa có client đăng ký.
- Heartbeat, lease và self-preservation ảnh hưởng đến thời điểm registry phản ánh instance lỗi; cần quan sát trước khi điều chỉnh.
- Bảo vệ dashboard và API registry bằng mạng riêng, xác thực, TLS và quản lý secret phù hợp.
