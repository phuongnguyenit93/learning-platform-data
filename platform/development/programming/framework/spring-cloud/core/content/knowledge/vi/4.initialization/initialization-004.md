# Khai báo cấu hình cơ sở trong application.yml

> **Chương:** Khởi tạo  
> **Module:** SPRING_CLOUD_CORE

Một ứng dụng Spring Boot thường chạy ở nhiều môi trường: máy lập trình, kiểm thử, staging và production. Mã nguồn có thể giống nhau, nhưng cổng HTTP, tên ứng dụng, địa chỉ dịch vụ phụ thuộc, thời gian chờ và thông tin kết nối lại khác nhau. **Externalized configuration** cho phép đưa những giá trị đó ra khỏi mã Java để ứng dụng nhận chúng từ các nguồn cấu hình phù hợp.

Trong hệ sinh thái Spring Cloud, cấu hình còn giúp xác định tên ứng dụng, tham số discovery, địa chỉ dịch vụ và hành vi tích hợp. Bài này tập trung vào cách khai báo cấu hình cơ sở bằng **`application.yml`**, cách Spring Boot nạp và ghi đè giá trị, cách bind cấu hình có cấu trúc vào Java, cùng những điểm cần lưu ý khi ứng dụng dùng Spring Cloud Context hoặc Spring Cloud Config.

## 1. `application.yml` có vai trò gì?

`application.yml` là một tệp cấu hình dạng YAML được Spring Boot tự động tìm trong các vị trí cấu hình mặc định. Nó chứa các cặp thuộc tính theo cấu trúc phân cấp. Spring Boot đọc các thuộc tính này vào môi trường cấu hình của ứng dụng (`Environment`), sau đó các thành phần có thể truy cập chúng bằng cơ chế binding hoặc placeholder.

Ví dụ tối giản:

~~~yaml
server:
  port: 8080

spring:
  application:
    name: order-service
~~~

Cấu hình trên có hai thuộc tính chính:

- `server.port`: cổng HTTP mà embedded server sử dụng.
- `spring.application.name`: tên logic của ứng dụng Spring.

Trong dự án Spring Cloud, tên ứng dụng thường được discovery integration dùng làm service ID mặc định hoặc một phần của thông tin đăng ký. Hành vi cụ thể còn tùy provider và cấu hình của nó; chỉ đặt `spring.application.name` **không tự cài đặt registry hoặc tự tạo một hệ thống discovery hoàn chỉnh**.

### 1.1. Cấu trúc YAML và quy tắc viết

YAML biểu diễn cấu trúc bằng thụt lề. Spring Boot chuyển cấu trúc đó thành các property key phân cấp, ví dụ:

| YAML | Property key |
| --- | --- |
| `server.port: 8080` | `server.port` |
| `spring.application.name: order-service` | `spring.application.name` |
| `catalog.client.connect-timeout: 2s` | `catalog.client.connect-timeout` |

Một số quy tắc nên tuân thủ:

- Dùng dấu cách để thụt lề, thống nhất thường là hai dấu cách mỗi cấp; không dùng tab.
- Dùng `:` để phân tách tên thuộc tính và giá trị.
- Dùng `-` để khai báo phần tử danh sách.
- Có thể đặt chú thích sau ký tự `#`, nhưng cần đặt trong chuỗi nếu `#` là một phần giá trị.
- Nên dùng tên thuộc tính dạng kebab-case, ví dụ `connect-timeout`, để thống nhất với quy tắc relaxed binding của Spring Boot.
- Đặt chuỗi có ký tự đặc biệt, dấu `:`, `#`, hoặc định dạng dễ bị YAML diễn giải thành kiểu khác trong dấu nháy khi cần.
- Tránh khai báo lặp cùng một key ở cùng cấp; key trùng có thể khiến parser từ chối tệp hoặc làm cấu hình khó hiểu.

Ví dụ có object, list và kiểu dữ liệu:

~~~yaml
catalog:
  client:
    enabled: true
    base-url: "http://localhost:8090"
    connect-timeout: 2s
    max-attempts: 3
    supported-regions:
      - north
      - south
~~~

Các giá trị `true`, `3` và `2s` có thể được bind thành boolean, số nguyên và `Duration`. Không cần biến tất cả thành chuỗi trong Java; hãy để binder chuyển đổi sang kiểu đích được hỗ trợ.

## 2. Khai báo các thuộc tính nền tảng của Spring Boot và Spring Cloud

Một `application.yml` cơ sở có thể nhóm cấu hình theo trách nhiệm:

~~~yaml
server:
  port: 8080
  shutdown: graceful

spring:
  application:
    name: order-service
  lifecycle:
    timeout-per-shutdown-phase: 20s

catalog:
  client:
    base-url: "http://localhost:8090"
    connect-timeout: 2s
    read-timeout: 5s
    max-attempts: 2

management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
~~~

Trong ví dụ:

- `server.port` đặt cổng HTTP.
- `server.shutdown: graceful` bật cơ chế graceful shutdown của embedded server.
- `spring.application.name` đặt tên ứng dụng.
- `spring.lifecycle.timeout-per-shutdown-phase` đặt khoảng thời gian chờ cho một phase shutdown.
- `catalog.client.*` là namespace do ứng dụng tự định nghĩa để nhóm cấu hình client gọi catalog.
- `management.endpoints.web.exposure.include` chỉ định các endpoint Actuator được expose qua web; ví dụ này cần có Spring Boot Actuator.

Tên property thuộc namespace do ứng dụng tự thiết kế như `catalog.client.*` không tự có hiệu lực nếu không có code hoặc thư viện đọc chúng. Ngược lại, các thuộc tính chuẩn như `server.port` được Spring Boot và auto-configuration tương ứng sử dụng.

**Nguyên tắc tổ chức:** gom các thuộc tính liên quan vào cùng một namespace có ý nghĩa; tách cấu hình framework (`spring.*`, `server.*`, `management.*`) khỏi cấu hình nghiệp vụ hoặc client do ứng dụng sở hữu.

## 3. Đọc cấu hình trong Java

Có hai cách phổ biến để đọc giá trị cấu hình: `@Value` cho một giá trị riêng lẻ và `@ConfigurationProperties` cho một nhóm thuộc tính có cấu trúc.

### 3.1. `@Value` cho một thuộc tính đơn

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class ApplicationIdentity {

    private final String applicationName;

    public ApplicationIdentity(
            @Value("${spring.application.name:unknown-service}") String applicationName) {
        this.applicationName = applicationName;
    }

    public String applicationName() {
        return applicationName;
    }
}
~~~

Biểu thức `${spring.application.name:unknown-service}` đọc `spring.application.name`; nếu thuộc tính không tồn tại, giá trị mặc định là `unknown-service`.

`@Value` tiện lợi với một vài giá trị nhỏ. Khi có nhiều thuộc tính liên quan, dùng `@ConfigurationProperties` giúp gom chúng thành một kiểu rõ ràng, dễ kiểm thử và dễ xác thực hơn.

### 3.2. `@ConfigurationProperties` cho nhóm cấu hình

Với namespace `catalog.client`, có thể tạo một record:

~~~java
import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "catalog.client")
public record CatalogClientProperties(
        @NotNull URI baseUrl,
        @NotNull Duration connectTimeout,
        @NotNull Duration readTimeout,
        @Min(1) int maxAttempts
) {}
~~~

Spring Boot cần đăng ký kiểu cấu hình để binder tạo bean. Có thể bật scan ở lớp ứng dụng:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrderApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderApplication.class, args);
    }
}
~~~

Hoặc dùng `@EnableConfigurationProperties(CatalogClientProperties.class)` trên một lớp cấu hình nếu muốn đăng ký tường minh.

Các điểm cần hiểu:

- `prefix = "catalog.client"` xác định namespace cần bind.
- `URI` và `Duration` là kiểu dữ liệu phù hợp cho URL và thời lượng; Spring Boot có conversion hỗ trợ các kiểu phổ biến này.
- `@Validated` kết hợp Jakarta Bean Validation để kiểm tra ràng buộc khi bind, nếu ứng dụng có dependency validation phù hợp.
- `@NotNull` yêu cầu giá trị phải có; `@Min(1)` yêu cầu số lần thử tối thiểu là một.
- Với record có constructor duy nhất, Spring Boot hỗ trợ constructor binding mà không cần khai báo `@ConstructorBinding` trong trường hợp thông thường.

Nếu cấu hình thiếu hoặc sai kiểu/ràng buộc, ứng dụng có thể thất bại ngay lúc khởi động. Đây thường là hành vi tốt hơn việc để lỗi xuất hiện muộn trong một request production.

### 3.3. Sử dụng bean cấu hình

Một service có thể nhận bean cấu hình qua constructor:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CatalogClientSettings {

    private final CatalogClientProperties properties;

    public CatalogClientSettings(CatalogClientProperties properties) {
        this.properties = properties;
    }

    public String baseUrl() {
        return properties.baseUrl().toString();
    }
}
~~~

Cách tiêm dependency này làm rõ thành phần nào cần cấu hình catalog. Khi kiểm thử, có thể cung cấp bộ property khác mà không sửa mã nghiệp vụ.

## 4. Placeholder, giá trị mặc định và biến môi trường

Không nên lưu giá trị riêng cho từng máy hoặc từng môi trường trực tiếp trong mã Java. `application.yml` hỗ trợ placeholder để lấy giá trị từ property source khác và cung cấp mặc định:

~~~yaml
server:
  port: ${SERVER_PORT:8080}

spring:
  application:
    name: ${APP_NAME:order-service}

catalog:
  client:
    base-url: ${CATALOG_BASE_URL:http://localhost:8090}
    connect-timeout: ${CATALOG_CONNECT_TIMEOUT:2s}
~~~

Cú pháp:

- `${NAME}`: đọc thuộc tính `NAME`; nếu không có, việc resolve có thể thất bại tùy nơi sử dụng.
- `${NAME:default}`: dùng `default` nếu thuộc tính không được cung cấp.

Có thể đặt biến môi trường khi chạy ứng dụng:

~~~powershell
$env:SERVER_PORT = "8180"
$env:APP_NAME = "order-service"
$env:CATALOG_BASE_URL = "https://catalog.internal"
java -jar order-service.jar
~~~

Hoặc trên Linux/macOS:

~~~bash
SERVER_PORT=8180 APP_NAME=order-service \
CATALOG_BASE_URL=https://catalog.internal \
java -jar order-service.jar
~~~

Spring Boot áp dụng relaxed binding cho tên biến môi trường. Quy tắc phổ biến là viết hoa, thay dấu chấm bằng dấu gạch dưới và loại bỏ dấu gạch ngang. Ví dụ `spring.application.name` có thể được đặt bằng `SPRING_APPLICATION_NAME`; `catalog.client.connect-timeout` có thể được đặt bằng `CATALOG_CLIENT_CONNECTTIMEOUT`.

Giá trị trong biến môi trường thường được đọc như chuỗi và được chuyển đổi sang kiểu đích khi binding. Hãy kiểm tra tên biến theo đúng quy tắc chuyển đổi, đặc biệt với list và map có chỉ số.

### 4.1. Không commit secret vào tệp cấu hình

Không đưa mật khẩu database, token, private key hoặc credential production vào `application.yml` được commit lên Git.

Có thể dùng biến môi trường, secret manager của nền tảng triển khai hoặc tệp secret được mount vào container. Ví dụ cấu hình chỉ tham chiếu tới một biến:

~~~yaml
spring:
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
~~~

Không đặt giá trị mặc định yếu cho secret production. Nếu secret bắt buộc mà không được cung cấp, để ứng dụng báo lỗi cấu hình khi khởi động sẽ dễ phát hiện hơn việc âm thầm chạy bằng credential không an toàn.

Spring Boot cũng hỗ trợ import dạng `configtree:` cho các nguồn cấu hình được mount dưới dạng thư mục, trong đó tên file biểu diễn property key và nội dung file là giá trị. Cơ chế này hữu ích với secret được nền tảng container mount thành file; cần xác nhận đường dẫn và quyền đọc của tiến trình ứng dụng.

## 5. Cấu hình theo môi trường bằng profile

Một ứng dụng thường cần các giá trị khác nhau ở local, test và production. **Spring Profile** cho phép kích hoạt một nhóm cấu hình theo tên môi trường.

### 5.1. Tách `application.yml` và `application-{profile}.yml`

Cấu trúc tệp thường gặp:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-prod.yml
~~~

Tệp chung:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

catalog:
  client:
    connect-timeout: 2s
    read-timeout: 5s
~~~

Tệp `application-local.yml`:

~~~yaml
server:
  port: 8081

catalog:
  client:
    base-url: "http://localhost:8090"
~~~

Tệp `application-prod.yml`:

~~~yaml
server:
  port: 8080

catalog:
  client:
    base-url: "https://catalog.internal"
    connect-timeout: 800ms
    read-timeout: 2s
~~~

Khi profile `prod` được kích hoạt, Spring Boot nạp cấu hình chung và cấu hình profile tương ứng. Thuộc tính ở profile-specific config có thể ghi đè giá trị cùng key trong cấu hình chung.

Kích hoạt profile qua biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar order-service.jar
~~~

Hoặc qua tham số dòng lệnh:

~~~bash
java -jar order-service.jar --spring.profiles.active=prod
~~~

Không nên mặc định profile production trong tệp cấu hình được đóng gói nếu cùng artifact phải được triển khai ở nhiều môi trường. Môi trường triển khai nên quyết định profile phù hợp.

### 5.2. Dùng nhiều document trong một YAML

Có thể đặt nhiều document trong cùng một `application.yml`, phân tách bằng `---`:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

---
spring:
  config:
    activate:
      on-profile: local

catalog:
  client:
    base-url: "http://localhost:8090"

---
spring:
  config:
    activate:
      on-profile: prod

catalog:
  client:
    base-url: "https://catalog.internal"
~~~

Document có `spring.config.activate.on-profile` chỉ được áp dụng khi profile tương ứng hoạt động. Cách này hữu ích với cấu hình ngắn; khi mỗi môi trường có nhiều thuộc tính, tách file thường dễ đọc và quản lý hơn.

`spring.profiles.active` và `spring.profiles.include` phải được khai báo ở document không gắn điều kiện profile; không đặt chúng trong document chỉ áp dụng cho một profile. Có thể kích hoạt nhiều profile cùng lúc, ví dụ `local,debug`, nhưng cần kiểm tra xung đột khi nhiều nguồn cùng khai báo một thuộc tính.

### 5.3. Profile không phải cơ chế bảo mật

Profile là cơ chế chọn cấu hình và bean theo môi trường. Nó không tự mã hóa secret, cô lập mạng, cấp quyền truy cập hoặc bảo đảm rằng production không thể vô tình dùng cấu hình local. Những yêu cầu đó cần được thực thi bởi pipeline, nền tảng triển khai, secret manager và chính sách bảo mật.

## 6. Nguồn cấu hình và thứ tự ưu tiên

`application.yml` chỉ là **một trong nhiều property source** mà Spring Boot có thể sử dụng. Giá trị cuối cùng được chọn theo thứ tự ưu tiên của các nguồn cấu hình. Nguồn có độ ưu tiên cao hơn có thể ghi đè nguồn thấp hơn khi cùng một key được khai báo.

Trong ứng dụng thông thường, các nguồn hay gặp gồm:

- Tệp cấu hình đóng gói trong ứng dụng (`application.yml`).
- Tệp cấu hình bên ngoài JAR/container image.
- Tệp cấu hình theo profile.
- Biến môi trường của tiến trình.
- Java system properties, ví dụ `-Dserver.port=8180`.
- Tham số dòng lệnh, ví dụ `--server.port=8181`.
- Nguồn cấu hình phục vụ kiểm thử.

Thứ tự chính xác còn phụ thuộc loại nguồn và ngữ cảnh khởi chạy; không nên suy luận chỉ từ tên tệp. Đặc biệt, test property sources có thể có độ ưu tiên cao trong test context. Khi có xung đột, hãy kiểm tra property source thực tế của ứng dụng và tài liệu Spring Boot đúng phiên bản đang dùng.

Ví dụ cùng khai báo `server.port`:

| Nguồn | Giá trị |
| --- | ---: |
| `application.yml` | 8080 |
| `application-prod.yml` | 8081 |
| Biến môi trường `SERVER_PORT` | 8082 |
| Tham số `--server.port=8180` | 8180 |

Nếu chạy với profile `prod`, biến môi trường và tham số dòng lệnh ở ví dụ trên, giá trị cuối cùng thường là `8180` do tham số dòng lệnh có ưu tiên cao hơn các nguồn cấu hình thông thường trước đó.

### 6.1. Vị trí cấu hình bên ngoài

Spring Boot tìm cấu hình ở các vị trí mặc định, bao gồm classpath và các vị trí bên ngoài ứng dụng. Có thể thêm nguồn cấu hình bằng `spring.config.additional-location` hoặc chỉ định vị trí bằng `spring.config.location`.

Khác biệt quan trọng:

- `spring.config.additional-location`: thêm vị trí vào tập vị trí tìm kiếm mặc định.
- `spring.config.location`: chỉ định vị trí cấu hình cần tìm, thay thế các vị trí mặc định.

Các thuộc tính này phải được cung cấp đủ sớm để quá trình nạp Config Data sử dụng được, thường qua biến môi trường, system property hoặc command line. Nếu muốn mở rộng cấu hình của image đã đóng gói mà vẫn giữ các mặc định bên trong, `additional-location` thường là lựa chọn phù hợp hơn.

Ví dụ:

~~~bash
java -jar order-service.jar \
  --spring.config.additional-location=optional:file:./config/
~~~

Tiền tố `optional:` cho phép ứng dụng tiếp tục nếu vị trí được chỉ định không tồn tại. Nếu cấu hình là bắt buộc, không nên dùng `optional:` vì lỗi thiếu file có thể bị che khuất.

## 7. Nạp cấu hình bổ sung với `spring.config.import`

Spring Boot Config Data hỗ trợ import nguồn cấu hình bổ sung ngay trong `application.yml`.

Ví dụ import tệp bên ngoài:

~~~yaml
spring:
  config:
    import: "optional:file:./config/extra.yml"
~~~

Tệp được import sẽ tham gia vào môi trường cấu hình theo quy tắc thứ tự của Config Data. Có thể dùng `optional:` khi nguồn không bắt buộc; bỏ `optional:` nếu ứng dụng phải dừng khi nguồn không truy cập được.

### 7.1. Kết nối Spring Cloud Config Server

Với ứng dụng dùng Spring Cloud Config, có thể import cấu hình từ Config Server:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://localhost:8888"
~~~

Ứng dụng cần dependency Config Client tương thích với Spring Boot và Spring Cloud release train đang sử dụng. Tên ứng dụng, profile và label có thể được dùng để Config Server trả về bộ cấu hình tương ứng.

Nếu Config Server là nguồn bắt buộc để ứng dụng hoạt động đúng, bỏ `optional:` để ứng dụng fail-fast khi không thể nạp cấu hình. Nếu cho phép chạy bằng cấu hình cục bộ khi server chưa sẵn sàng, có thể dùng `optional:` nhưng phải đánh giá rõ hành vi fallback và tránh khởi động với cấu hình thiếu an toàn.

Không nhầm **Config Server** với **service registry**: Config Server phân phối thuộc tính cấu hình; registry/discovery quản lý thông tin instance dịch vụ. Chúng giải quyết hai vấn đề khác nhau, dù một hệ thống có thể dùng cả hai.

## 8. Cấu hình có cấu trúc cho giao tiếp dịch vụ

Trong Spring Cloud, nhiều thuộc tính liên quan đến giao tiếp giữa dịch vụ với nhau. Có thể tổ chức theo namespace riêng:

~~~yaml
catalog:
  client:
    base-url: "https://catalog.internal"
    connect-timeout: 1s
    read-timeout: 3s
    max-attempts: 2

inventory:
  discovery:
    service-id: inventory-service
  client:
    connect-timeout: 500ms
    read-timeout: 2s
~~~

Lợi ích:

- Mỗi nhóm cấu hình có một chủ sở hữu rõ ràng.
- Dễ bind vào các lớp `@ConfigurationProperties` độc lập.
- Có thể ghi đè từng key theo profile hoặc môi trường.
- Có thể kiểm tra ràng buộc ngay khi khởi động.
- Giảm việc rải `@Value` và tên property khắp các lớp nghiệp vụ.

Không tự giả định property tự đặt như `inventory.discovery.service-id` sẽ được Spring Cloud Commons đọc. Nếu ứng dụng muốn dùng nó, code phải bind và truyền giá trị đó tới thành phần thích hợp; hoặc dùng đúng property chuẩn mà integration cụ thể hỗ trợ.

### 8.1. Cấu hình không thay thế discovery

`base-url` cố định là phù hợp khi ứng dụng gọi một endpoint ổn định hoặc một gateway. Nếu muốn gọi theo service ID và để Spring Cloud LoadBalancer chọn instance, HTTP client phải được tích hợp load balancing và nguồn discovery phải cung cấp instance tương ứng.

Ví dụ gọi bằng service ID:

~~~java
WebClient client = loadBalancedBuilder.build();

client.get()
      .uri("http://inventory-service/stock/{sku}", sku);
~~~

Trong ví dụ này, `inventory-service` là tên logic. Cơ chế phân giải service ID cần integration `@LoadBalanced` và Spring Cloud LoadBalancer; nó không tự hoạt động chỉ vì YAML có key `inventory.discovery.service-id`.

## 9. Thay đổi cấu hình khi ứng dụng đang chạy

Mặc định, `application.yml` được đọc trong quá trình khởi tạo ứng dụng. Sửa file trên đĩa **không có nghĩa mọi bean đang chạy sẽ tự nhận giá trị mới ngay lập tức**.

Cần phân biệt ba việc:

1. **Thay đổi nguồn cấu hình:** cập nhật biến môi trường, file hoặc Config Server.
2. **Nạp/refresh môi trường ứng dụng:** kích hoạt cơ chế để ứng dụng nhìn thấy property mới, tùy loại nguồn và tích hợp.
3. **Áp dụng giá trị mới vào bean:** bean phải đọc lại giá trị hoặc được tạo lại theo cơ chế hỗ trợ.

Spring Cloud Context cung cấp các cơ chế như `@RefreshScope` và refresh event cho những trường hợp cần làm mới bean có hỗ trợ. Ví dụ:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class CatalogEndpoint {

    private final String baseUrl;

    public CatalogEndpoint(
            @Value("${catalog.client.base-url}") String baseUrl) {
        this.baseUrl = baseUrl;
    }

    public String baseUrl() {
        return baseUrl;
    }
}
~~~

Khi cơ chế refresh phù hợp được kích hoạt, bean trong refresh scope có thể được tạo lại để đọc giá trị mới. Tuy nhiên:

- `@RefreshScope` không tự theo dõi mọi thay đổi trên file.
- Không phải mọi bean hoặc mọi trạng thái đều có thể refresh an toàn.
- Kết nối, thread pool hoặc client đã tạo có thể cần cách cập nhật riêng.
- Việc kích hoạt refresh phụ thuộc endpoint/event và cấu hình bảo mật của ứng dụng.
- Thay đổi cấu hình không tương đương thay mã nguồn hoặc triển khai phiên bản ứng dụng mới.

Không expose endpoint refresh ra môi trường không được kiểm soát. Nếu dùng Spring Cloud Config Monitor/Bus hoặc cơ chế refresh khác, cần cấu hình xác thực, phân quyền và luồng phát sự kiện tương ứng.

## 10. Kiểm thử cấu hình

Cấu hình là một phần của hành vi ứng dụng, do đó nên kiểm tra cả khả năng bind và các giá trị ghi đè.

### 10.1. Ghi đè property trong test

Với Spring Boot Test, có thể truyền property trực tiếp:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(properties = {
    "catalog.client.base-url=http://localhost:9999",
    "catalog.client.connect-timeout=250ms",
    "catalog.client.read-timeout=1s",
    "catalog.client.max-attempts=1"
})
class CatalogClientPropertiesTest {

    @Autowired
    CatalogClientProperties properties;

    @Test
    void bindsConfiguredValues() {
        assertThat(properties.baseUrl().toString())
                .isEqualTo("http://localhost:9999");
        assertThat(properties.connectTimeout().toMillis())
                .isEqualTo(250);
        assertThat(properties.maxAttempts()).isEqualTo(1);
    }
}
~~~

Test này xác nhận binder chuyển đổi các giá trị sang kiểu Java đúng như mong đợi. Cần bảo đảm test context bật `@ConfigurationPropertiesScan` hoặc đăng ký lớp cấu hình tương ứng.

### 10.2. Danh sách kiểm tra khi cấu hình lỗi

| Tình huống | Điều nên kiểm tra |
| --- | --- |
| Ứng dụng dùng sai cổng | `server.port`, biến môi trường, command line và profile đang active |
| Bean cấu hình không được tạo | `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` |
| Thuộc tính không bind | Prefix, tên key, kiểu dữ liệu, tên biến môi trường và cấu trúc YAML |
| Profile không áp dụng | `spring.profiles.active`, tên file và `spring.config.activate.on-profile` |
| Giá trị bị ghi đè bất ngờ | Property source có ưu tiên cao hơn và nguồn cấu hình bên ngoài |
| Không lấy được cấu hình từ Config Server | Config Client dependency, URL, `spring.config.import`, network và profile/label |
| Giá trị mới chưa tác dụng | Bean đã bind lúc nào, có refresh event không và bean có hỗ trợ refresh không |
| Ứng dụng chạy với secret rỗng | Placeholder, nguồn secret, quyền đọc file và quy tắc bắt buộc khi khởi động |

Khi chẩn đoán, hãy kiểm tra môi trường và property source của đúng tiến trình. Tránh log toàn bộ cấu hình hoặc secret. Nếu dùng Actuator để xem thông tin `env`/`configprops`, chỉ expose trong phạm vi cần thiết, bật sanitization và bảo vệ bằng xác thực/phân quyền.

## 11. Lỗi thường gặp và cách tránh

1. **Đặt sai cấp thụt lề:** YAML vẫn có thể hợp lệ nhưng property nằm dưới namespace khác. Kiểm tra cấu trúc key sau khi parse và binding.
2. **Dùng tab:** YAML thường không chấp nhận tab để thụt lề. Dùng spaces.
3. **Cho rằng sửa file sẽ tự refresh bean:** cấu hình thường được nạp khi khởi động; cần cơ chế refresh hoặc restart phù hợp.
4. **Nhầm tên ứng dụng với registry:** `spring.application.name` cung cấp tên ứng dụng; cần discovery integration và registry hoặc nguồn instance phù hợp.
5. **Đặt secret trong Git:** đưa secret ra nguồn được quản lý an toàn và cấp quyền đọc cho ứng dụng.
6. **Dùng profile để thay thế bảo mật:** profile chỉ chọn cấu hình/bean, không bảo đảm cách ly hoặc phân quyền.
7. **Dùng `optional:` cho nguồn bắt buộc:** ứng dụng có thể khởi động thiếu cấu hình quan trọng; chỉ dùng khi có fallback được thiết kế.
8. **Khai báo property tự đặt nhưng không bind:** Spring Boot không tự suy ra mọi key trong YAML là cấu hình có tác dụng; cần thư viện hoặc code đọc key đó.
9. **Không quản lý phiên bản Boot/Cloud:** Config Client, Context và các starter phải nằm trong tổ hợp release train tương thích với Spring Boot.

## 12. Quy trình khởi tạo cấu hình đề xuất

Khi bắt đầu một dịch vụ Spring Boot dùng Spring Cloud, có thể đi theo thứ tự:

1. Đặt `spring.application.name` và các thuộc tính nền tảng thực sự cần thiết.
2. Xác định các nhóm cấu hình riêng của ứng dụng, ví dụ `catalog.client.*`.
3. Bind nhóm thuộc tính vào `@ConfigurationProperties`; thêm validation cho giá trị bắt buộc và giới hạn hợp lệ.
4. Đặt mặc định an toàn, không nhúng secret hoặc địa chỉ môi trường production vào artifact.
5. Tạo profile hoặc nguồn cấu hình bên ngoài cho local, test và production.
6. Chọn cách nạp cấu hình từ file, environment, Config Server hoặc config tree theo hạ tầng.
7. Kiểm thử binding, override, profile và trường hợp thiếu cấu hình.
8. Chỉ thêm refresh scope khi có yêu cầu thay đổi lúc chạy và đã xác định bean nào có thể refresh an toàn.
9. Kiểm tra lại dependency Spring Cloud theo release train tương thích với Spring Boot.

**Điểm ghi nhớ:** `application.yml` là điểm khởi đầu thuận tiện để khai báo cấu hình có cấu trúc. Spring Boot đưa các giá trị đó vào `Environment`, bind chúng vào bean hoặc resolve qua placeholder, rồi kết hợp với profile và các nguồn cấu hình bên ngoài theo thứ tự ưu tiên. Trong Spring Cloud, cần phân biệt cấu hình ứng dụng, cấu hình tập trung, discovery và refresh; mỗi cơ chế có vòng đời và trách nhiệm riêng.
