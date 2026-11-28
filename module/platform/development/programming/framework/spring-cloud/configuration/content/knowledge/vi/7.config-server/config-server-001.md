# Khởi tạo máy chủ với @EnableConfigServer

Spring Cloud Config Server là dịch vụ trung tâm cung cấp cấu hình cho các ứng dụng Spring Boot thông qua HTTP. Thay vì để mỗi ứng dụng tự quản lý một bản cấu hình riêng, nhóm có thể lưu cấu hình trong Git, triển khai một Config Server và để các Config Client truy vấn theo tên ứng dụng, profile và label. Bước khởi tạo server gồm thêm đúng dependency, bật `@EnableConfigServer`, cấu hình backend và kiểm tra endpoint trước khi kết nối các client.

## 1. Tạo ứng dụng Spring Boot cho Config Server

Config Server là một ứng dụng Spring Boot độc lập. Nó cần dependency `spring-cloud-config-server` và một Spring Cloud release train tương thích với phiên bản Spring Boot của dự án. Nên quản lý phiên bản Spring Cloud bằng BOM `spring-cloud-dependencies`, không khai báo một phiên bản tùy ý cho riêng module Config Server.

Ví dụ dependency trong Maven khi BOM đã được import trong `dependencyManagement`:

```xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-config-server</artifactId>
</dependency>
```

Với Gradle, dependency tương ứng là:

```kotlin
dependencies {
    implementation("org.springframework.cloud:spring-cloud-config-server")
}
```

Tên ứng dụng server nên rõ vai trò, ví dụ `configuration-server`. Đây là tên ứng dụng Spring Boot của chính server; nó không phải tên application mà client truyền vào endpoint để lấy cấu hình.

## 2. Bật chức năng bằng @EnableConfigServer

Đặt `@EnableConfigServer` trên lớp cấu hình hoặc lớp khởi động của ứng dụng Spring Boot:

```java
package com.example.configserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

@SpringBootApplication
@EnableConfigServer
public class ConfigurationServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigurationServerApplication.class, args);
    }
}
```

`@SpringBootApplication` thiết lập ứng dụng Spring Boot và component scan. `@EnableConfigServer` nhập cấu hình cần thiết của Spring Cloud Config Server, đăng ký các thành phần phục vụ endpoint cấu hình và kết nối chúng với repository backend đã khai báo. Sau khi ứng dụng khởi động thành công, server có thể nhận yêu cầu HTTP để trả về `Environment` cho một application, profile và label.

Chỉ thêm dependency chưa đủ để biến ứng dụng thành Config Server; cần bật annotation này. Ngược lại, annotation cũng không tự tạo ra một kho cấu hình. Server cần được chỉ định backend và quyền truy cập tương ứng.

## 3. Cấu hình Git backend

Trong môi trường thực tế, Git là backend phổ biến vì lưu được lịch sử thay đổi, hỗ trợ review và cho phép chọn revision bằng branch, tag hoặc commit. Khai báo địa chỉ repository trong `application.yml` của Config Server:

```yaml
server:
  port: 8888

spring:
  application:
    name: configuration-server
  cloud:
    config:
      server:
        git:
          uri: https://github.com/example-org/config-repository.git
          default-label: main
          clone-on-start: true
```

Trong đó:

- `server.port` đặt cổng HTTP của Config Server.
- `spring.application.name` định danh chính ứng dụng server.
- `spring.cloud.config.server.git.uri` trỏ tới Git repository chứa các tệp cấu hình.
- `default-label` chọn label mặc định khi client không gửi label.
- `clone-on-start: true` yêu cầu server clone repository khi khởi động để phát hiện sớm lỗi truy cập hoặc cấu hình Git.

Repository có thể tổ chức theo application và profile:

```text
config-repository/
├── application.yml
├── application-prod.yml
├── billing-api.yml
├── billing-api-prod.yml
├── inventory-api.yml
└── inventory-api-prod.yml
```

`application.yml` chứa giá trị dùng chung; `billing-api.yml` chứa cấu hình riêng của dịch vụ thanh toán; `billing-api-prod.yml` bổ sung cấu hình dành cho profile `prod`. Config Server kết hợp các tệp phù hợp với bộ ba application, profile và label mà client yêu cầu.

Nếu repository có thư mục con riêng, có thể khai báo `search-paths`:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://github.com/example-org/config-repository.git
          default-label: main
          search-paths:
            - config
            - services
```

Server sẽ tìm cấu hình trong các đường dẫn đã khai báo bên trong repository. Cần bảo đảm cấu trúc thư mục thực tế khớp với `search-paths`; nếu không, repository clone thành công nhưng phản hồi có thể thiếu property source mong muốn.

## 4. Truy cập repository riêng tư

Với Git repository riêng tư, Config Server cần thông tin xác thực phù hợp. Với HTTPS, có thể cấu hình username và password hoặc token do nhà cung cấp Git cấp. Hãy truyền chúng qua biến môi trường hoặc secret manager:

```yaml
spring:
  cloud:
    config:
      server:
        git:
          uri: https://github.com/example-org/private-config.git
          username: ${CONFIG_GIT_USERNAME}
          password: ${CONFIG_GIT_TOKEN}
          default-label: main
```

Các biến môi trường phải được cấp cho tiến trình Config Server khi triển khai. Không commit token, mật khẩu hoặc private key vào repository cấu hình hay mã nguồn server. Cấp quyền đọc tối thiểu cho credential và có quy trình xoay vòng khi credential bị thay thế.

Nếu dùng SSH, cần thiết lập private key và xác minh host key theo chính sách của môi trường triển khai. Tránh tắt xác minh máy chủ SSH chỉ để làm cho kết nối hoạt động. Với HTTPS, dùng TLS và chứng thư được tin cậy. Ngoài quyền đọc Git, cũng cần bảo vệ chính HTTP endpoint của Config Server bằng xác thực, phân quyền và giới hạn truy cập mạng.

## 5. Khởi động và kiểm tra server

Chạy Config Server bằng Maven hoặc Gradle wrapper của dự án:

```bash
./mvnw spring-boot:run
```

Hoặc:

```bash
./gradlew bootRun
```

Trên Windows có thể dùng `mvnw.cmd` hoặc `gradlew.bat`. Khi `clone-on-start` được bật, xem log để xác nhận server đã truy cập và clone repository. Nếu ứng dụng không khởi động, kiểm tra URI, DNS, mạng, credential, quyền đọc và label mặc định.

Sau khi server chạy tại `http://localhost:8888`, có thể truy vấn cấu hình của một ứng dụng:

```bash
curl -i http://localhost:8888/billing-api/default/main
```

Hoặc truy vấn cấu hình production:

```bash
curl -i http://localhost:8888/billing-api/prod/main
```

Endpoint có dạng `/{application}/{profile}/{label}`. Phản hồi thành công thường là JSON `Environment` chứa tên ứng dụng, danh sách profile, label, Git revision và các `propertySources`. Mỗi property source cho biết một nguồn cấu hình được lấy từ repository. Ví dụ cấu trúc rút gọn:

```json
{
  "name": "billing-api",
  "profiles": ["prod"],
  "label": "main",
  "version": "a1b2c3d4",
  "propertySources": [
    {
      "name": ".../billing-api-prod.yml",
      "source": {
        "acme.billing.connect-timeout": "4s"
      }
    }
  ]
}
```

Đây là ví dụ minh họa; tên nguồn, revision và nội dung thực tế phụ thuộc repository. Kiểm tra `name`, `profiles`, `label` và `version` để xác nhận đúng truy vấn. Nếu nhận HTTP 404 hoặc danh sách `propertySources` rỗng, kiểm tra tên application, profile, label và `search-paths`.

## 6. Những endpoint cơ bản và cách đọc kết quả

Ngoài truy vấn một application cụ thể, Config Server có các endpoint dạng:

| Endpoint | Mục đích |
| --- | --- |
| `/{application}/{profile}/{label}` | Lấy `Environment` của application, profile và label |
| `/{application}/{profile}` | Lấy cấu hình với label mặc định của server |
| `/{application}-{profile}.yml` | Trả về cấu hình ở định dạng YAML |
| `/{application}-{profile}.properties` | Trả về cấu hình ở định dạng properties |

Các endpoint định dạng YAML hoặc properties hữu ích khi kiểm tra thủ công, còn Config Client thường dùng endpoint `Environment` để nhận danh sách property source và metadata. Cách diễn giải kết quả phụ thuộc định dạng và phiên bản Config Server.

Khi có nhiều tệp cùng khai báo một khóa, hãy xem danh sách `propertySources` để hiểu nguồn nào được kết hợp và thứ tự ưu tiên. Config Server chịu trách nhiệm tìm nguồn theo application, profile và label; Spring `Environment` ở client tiếp tục hợp nhất property source từ xa với các nguồn khác như biến môi trường hoặc tham số dòng lệnh. Do đó, giá trị cuối cùng trong ứng dụng có thể khác với giá trị nhìn thấy trong một tệp Git.

## 7. Kiểm tra lỗi thường gặp

| Hiện tượng | Nguyên nhân nên kiểm tra |
| --- | --- |
| Server không khởi động | Thiếu `@EnableConfigServer`, thiếu dependency, phiên bản Spring Boot/Spring Cloud không tương thích |
| Không clone được repository | Sai Git URI, DNS/mạng, credential hoặc quyền đọc |
| HTTP 404 hoặc không có property source | Sai application, profile, label hoặc `search-paths` |
| Server trả về cấu hình cũ | Label trỏ tới branch/tag/commit không như dự kiến hoặc bản sao repository chưa cập nhật theo cách cấu hình |
| Client không kết nối được | Sai host/port, firewall, TLS, xác thực hoặc server chưa sẵn sàng |
| Client nhận được cấu hình nhưng ứng dụng dùng giá trị khác | Property source khác có độ ưu tiên cao hơn trong Spring `Environment` |

Để khoanh vùng, trước hết kiểm tra log khởi động của server và trạng thái clone repository. Tiếp theo gọi trực tiếp endpoint với đúng application, profile và label. Chỉ khi phản hồi của server đúng mới chuyển sang kiểm tra Config Client, thứ tự nguồn cấu hình và quá trình bind vào bean.

## 8. Bảo vệ Config Server trong môi trường triển khai

Config Server có thể cung cấp URL nội bộ, thông tin kết nối và một số dữ liệu nhạy cảm cho nhiều dịch vụ. Vì vậy, cần bảo vệ cả hai đường truy cập: từ server tới Git và từ client tới server.

- Dùng TLS cho HTTP endpoint và xác thực client theo yêu cầu hệ thống.
- Giới hạn mạng có thể truy cập Config Server; không công khai endpoint cấu hình ra Internet nếu không có lớp bảo vệ phù hợp.
- Dùng credential Git chỉ có quyền đọc repository cần thiết và lưu credential trong secret manager.
- Không ghi token, mật khẩu hoặc nội dung bí mật vào log và ví dụ cấu hình.
- Review thay đổi trong repository, bảo vệ nhánh/tag phát hành và ghi nhận revision được triển khai.
- Chỉ bật endpoint chẩn đoán cần thiết; bảo vệ Actuator và các endpoint có thể tiết lộ cấu hình.

Khi cần cấu hình bí mật, hãy dùng cơ chế mã hóa của Spring Cloud Config hoặc tích hợp secret manager theo chính sách của tổ chức. Không coi Git repository riêng tư là nơi tự động an toàn để lưu mật khẩu ở dạng rõ.

## 9. Tóm tắt quy trình khởi tạo

1. Tạo ứng dụng Spring Boot và import BOM Spring Cloud tương thích.
2. Thêm dependency `spring-cloud-config-server`.
3. Bật `@EnableConfigServer` trên lớp ứng dụng.
4. Cấu hình `server.port`, Git URI, default label và search paths nếu cần.
5. Cấp credential qua secret manager hoặc biến môi trường, không ghi bí mật vào mã nguồn.
6. Khởi động server và kiểm tra log clone repository.
7. Gọi endpoint `/{application}/{profile}/{label}` để xác nhận `Environment` và `propertySources`.
8. Bảo vệ endpoint trước khi kết nối các Config Client trong môi trường dùng chung hoặc production.

Khi Config Server khởi động đúng và trả về được cấu hình từ Git, nền tảng phân phối cấu hình tập trung đã sẵn sàng cho bước tích hợp Config Client. Từ đây, từng ứng dụng có thể chọn cấu hình theo tên dịch vụ, profile và revision đã được nhóm quản trị.
