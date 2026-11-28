# Thêm đúng starter cho Config Server, Config Client và Actuator

Một hệ thống Spring Cloud Config thường có ít nhất hai loại ứng dụng: ứng dụng cung cấp cấu hình tập trung và các ứng dụng lấy cấu hình đó để chạy. Spring Cloud cung cấp dependency riêng cho từng vai trò. Spring Boot Actuator bổ sung các endpoint phục vụ kiểm tra sức khỏe và vận hành. Chọn đúng dependency giúp mỗi ứng dụng có đúng chức năng cần thiết, giảm phụ thuộc thừa và tránh nhầm lẫn giữa các starter.

Trong bài này, ta thiết lập ba dependency chính:

- `spring-cloud-config-server` cho ứng dụng Config Server.
- `spring-cloud-starter-config` cho ứng dụng Config Client.
- `spring-boot-starter-actuator` cho ứng dụng cần endpoint quản trị và giám sát.

Actuator là dependency độc lập, có thể được thêm vào server, client hoặc cả hai tùy nhu cầu vận hành. Nó không thay thế Config Server hay Config Client.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt dependency của Config Server, Config Client và Actuator.
- Quản lý phiên bản Spring Cloud bằng BOM tương thích với Spring Boot.
- Khai báo dependency trong Maven hoặc Gradle.
- Tạo cấu hình tối thiểu để Config Server đọc kho Git và Config Client kết nối server.
- Bật có chọn lọc các endpoint Actuator và hiểu rủi ro khi công khai endpoint quản trị.
- Kiểm tra dependency tree để phát hiện thiếu hoặc trùng phiên bản thư viện.

## Chọn đúng dependency theo vai trò

| Ứng dụng | Dependency | Chức năng |
|---|---|---|
| Config Server | `org.springframework.cloud:spring-cloud-config-server` | Bật API phân phối cấu hình và các backend như Git |
| Config Client | `org.springframework.cloud:spring-cloud-starter-config` | Tích hợp client để lấy cấu hình từ Config Server |
| Server hoặc Client cần giám sát/quản trị | `org.springframework.boot:spring-boot-starter-actuator` | Cung cấp các endpoint như health, info và những endpoint quản trị được bật |

Hai dependency Config có vai trò khác nhau. Server dùng artifact `spring-cloud-config-server`; client dùng starter `spring-cloud-starter-config`. Không thêm cả hai vào mọi ứng dụng theo thói quen. Chỉ ứng dụng có trách nhiệm phục vụ cấu hình mới cần dependency server; mỗi ứng dụng muốn lấy cấu hình từ xa mới cần dependency client.

`spring-boot-starter-actuator` thuộc Spring Boot, không phải starter Config của Spring Cloud. Có thể thêm nó vào Config Server để kiểm tra sức khỏe dịch vụ trung tâm, và vào Config Client để quan sát hoặc kích hoạt những thao tác vận hành được hỗ trợ. Nếu ứng dụng không cần endpoint Actuator thì không bắt buộc phải thêm dependency này.

## Quản lý phiên bản bằng Spring Cloud BOM

Các thư viện Spring Cloud được phát hành theo release train. Phiên bản release train phải tương thích với phiên bản Spring Boot đang dùng. Hãy tra bảng tương thích chính thức của Spring Cloud trước khi chọn giá trị cho `spring-cloud.version`; không tự chọn một phiên bản mới nhất riêng lẻ cho Config Server hoặc Config Client.

Với Maven, có thể import BOM ở `dependencyManagement` của project cha hoặc từng project độc lập:

```xml
<properties>
    <spring-cloud.version>YOUR_COMPATIBLE_SPRING_CLOUD_TRAIN</spring-cloud.version>
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
```

`YOUR_COMPATIBLE_SPRING_CLOUD_TRAIN` là chỗ giữ chỗ: thay bằng phiên bản release train đã xác nhận tương thích với Spring Boot của dự án. Nếu project cha đã import BOM thì các module con dùng chung dependency management và không cần import lặp lại.

### Dependency cho Config Server

Trong module triển khai Config Server, khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-config-server</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

Nếu server chỉ cần cung cấp cấu hình và chưa dùng endpoint Actuator, có thể bỏ dependency Actuator. Khi vận hành thực tế, health check của server thường hữu ích cho load balancer và hệ thống giám sát.

### Dependency cho Config Client

Trong mỗi module ứng dụng cần lấy cấu hình từ xa, khai báo:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
</dependencies>
```

Nếu client không cần endpoint Actuator thì có thể bỏ dependency thứ hai. Client vẫn có thể lấy cấu hình khi khởi động bằng Config Data API mà không cần Actuator.

## Khai báo dependency bằng Gradle

Với Gradle, import Spring Cloud BOM dưới dạng platform để các dependency Spring Cloud nhận phiên bản đồng bộ. Ví dụ dưới đây dùng Groovy DSL cho module Config Server:

```groovy
ext {
    set('springCloudVersion', 'YOUR_COMPATIBLE_SPRING_CLOUD_TRAIN')
}

dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    implementation 'org.springframework.cloud:spring-cloud-config-server'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Trong module Config Client, giữ BOM và thay dependency Config Server bằng starter client:

```groovy
dependencies {
    implementation platform("org.springframework.cloud:spring-cloud-dependencies:${springCloudVersion}")
    implementation 'org.springframework.cloud:spring-cloud-starter-config'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Thay giá trị giữ chỗ bằng release train phù hợp. Nếu dự án đã quản lý BOM ở plugin hoặc cấu hình dependency management cấp cao hơn, hãy tuân theo cách quản lý phiên bản hiện có thay vì khai báo platform nhiều lần ở từng module.

## Thiết lập ứng dụng Config Server

Sau khi thêm dependency server, đánh dấu lớp ứng dụng bằng `@EnableConfigServer`:

```java
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
```

Ví dụ cấu hình server dùng Git làm backend:

```yaml
# config-server/src/main/resources/application.yml
server:
  port: 8888

spring:
  application:
    name: config-server
  cloud:
    config:
      server:
        git:
          uri: https://git.example.com/platform/config-repo.git
```

Config Server sẽ đọc repository được chỉ định và cung cấp cấu hình theo application, profile và label. Nếu repository riêng tư, cần cấu hình thông tin xác thực bằng secret hoặc cơ chế an toàn của môi trường triển khai. Không commit username, password, token hoặc private key vào file cấu hình công khai.

Dependency server chỉ cung cấp chức năng Config Server; annotation `@EnableConfigServer` bật server trong ứng dụng. Thiếu annotation thì việc thêm dependency không tự biến một ứng dụng Spring Boot thành Config Server.

## Thiết lập ứng dụng Config Client

Sau khi thêm `spring-cloud-starter-config`, khai báo tên ứng dụng và địa chỉ Config Server trong cấu hình client. Với Spring Boot sử dụng Config Data API, dùng `spring.config.import`:

```yaml
# order-service/src/main/resources/application.yml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://localhost:8888"
```

Tên `order-service` được dùng để Config Server chọn cấu hình tương ứng. Profile đang hoạt động và label có thể tiếp tục xác định biến thể môi trường và phiên bản cấu hình.

Tiền tố `optional:` cho phép client tiếp tục khởi động nếu Config Server không truy cập được trong lúc nạp cấu hình. Cách này phù hợp khi cấu hình từ xa là tùy chọn hoặc ứng dụng có giá trị mặc định an toàn. Nếu ứng dụng bắt buộc phải có cấu hình trung tâm để hoạt động đúng, bỏ `optional:` để lỗi kết nối được thể hiện ngay khi khởi động.

Trong các hệ thống cũ sử dụng bootstrap context, cách khai báo có thể khác và có thể cần `spring-cloud-starter-bootstrap`. Không thêm dependency bootstrap chỉ vì đang dùng Config Client theo Config Data API; hãy theo đúng cơ chế khởi tạo mà phiên bản Spring Boot/Spring Cloud của dự án hỗ trợ.

## Thêm Actuator và bật endpoint cần thiết

Actuator cung cấp endpoint vận hành. Ví dụ, `health` giúp hệ thống giám sát kiểm tra trạng thái ứng dụng; `info` có thể hiển thị thông tin build hoặc phiên bản nếu ứng dụng đã cấu hình dữ liệu tương ứng. Khi dùng Spring Cloud Config Client, endpoint `refresh` có thể được sử dụng để yêu cầu client làm mới cấu hình trong các mô hình hỗ trợ refresh.

Ví dụ cấu hình cơ bản:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: when_authorized
```

Spring Boot chỉ công khai một tập endpoint giới hạn qua HTTP theo mặc định; hãy chủ động liệt kê endpoint thực sự cần dùng. Nếu quy trình vận hành cần gọi refresh qua HTTP, có thể thêm `refresh` vào danh sách exposure:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
```

Endpoint refresh có thể làm thay đổi cấu hình đang được ứng dụng sử dụng. Bảo vệ endpoint bằng xác thực và phân quyền, giới hạn truy cập qua mạng nội bộ hoặc management port riêng, đồng thời chỉ cho phép người hoặc hệ thống vận hành được ủy quyền gọi. Không công khai rộng rãi các endpoint nhạy cảm như `env`, `configprops`, `heapdump`, `threaddump` hoặc `beans`; chúng có thể tiết lộ thông tin nội bộ hay dữ liệu cấu hình.

Nếu dùng Spring Cloud Bus để thông báo refresh cho nhiều instance, cần bổ sung dependency Bus tương ứng với broker (chẳng hạn AMQP hoặc Kafka) và cấu hình broker. Đó là phần mở rộng riêng; `spring-boot-starter-actuator` không tự cung cấp broker hay cơ chế broadcast.

## Xác minh dependency và cấu hình

Sau khi chỉnh sửa build file, kiểm tra dependency tree để chắc chắn module đã nhận đúng artifact và không có phiên bản xung đột.

Với Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.cloud,org.springframework.boot:spring-boot-starter-actuator
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Các điểm cần kiểm tra:

- Module Config Server có `spring-cloud-config-server` và lớp ứng dụng có `@EnableConfigServer`.
- Module Config Client có `spring-cloud-starter-config` và `spring.config.import` trỏ đến đúng địa chỉ server.
- Chỉ những module cần endpoint vận hành mới thêm `spring-boot-starter-actuator`.
- Spring Cloud BOM tương thích với Spring Boot; không khai báo version riêng lẻ gây lệch release train.
- Config Server đọc được repository cấu hình và Config Client nhận được cấu hình theo tên ứng dụng/profile dự kiến.
- Các endpoint Actuator cần thiết hoạt động và được bảo vệ theo chính sách truy cập.

Khi kiểm tra bằng HTTP, có thể gọi endpoint cấu hình của server, ví dụ `GET http://localhost:8888/order-service/default`. Nếu Actuator được cài và endpoint health được expose, kiểm tra `GET http://localhost:8888/actuator/health` trên server hoặc đường dẫn tương ứng trên client. Đường dẫn và quyền truy cập có thể thay đổi theo `management.server.port`, `management.endpoints.web.base-path` và cấu hình bảo mật của ứng dụng.

## Những lỗi cấu hình dependency thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách khắc phục |
|---|---|---|
| Không nhận diện `@EnableConfigServer` | Thiếu `spring-cloud-config-server` hoặc BOM không đúng | Thêm dependency server và kiểm tra dependency tree |
| Client không tải được cấu hình | Thiếu `spring-cloud-starter-config`, sai URL hoặc thiếu `spring.config.import` | Kiểm tra dependency, địa chỉ Config Server và tên ứng dụng |
| Ứng dụng báo lỗi không tìm thấy Config Server khi khởi động | Dùng import bắt buộc nhưng server chưa sẵn sàng hoặc địa chỉ sai | Kiểm tra mạng, readiness và chính sách `optional` |
| Không có `/actuator/health` qua HTTP | Thiếu Actuator hoặc endpoint chưa được expose/đổi base path | Thêm starter nếu cần và kiểm tra cấu hình management |
| Không gọi được `/actuator/refresh` | Thiếu hỗ trợ refresh, endpoint chưa expose hoặc bị bảo mật chặn | Kiểm tra dependency Spring Cloud, Actuator, exposure và quyền truy cập |
| Lỗi tương thích thư viện hoặc `NoSuchMethodError` | Spring Boot và Spring Cloud release train không tương thích hoặc dependency bị override | Dùng ma trận tương thích và bỏ override phiên bản không cần thiết |

Không nên giải quyết lỗi tương thích bằng cách nâng riêng một dependency Spring Cloud trong khi giữ các dependency còn lại ở release train cũ. Trước tiên hãy xác định phiên bản Spring Boot, chọn BOM tương ứng, rồi để BOM quản lý các module Spring Cloud liên quan.

## Kết luận

Thiết lập đúng Spring Cloud Config bắt đầu từ việc gắn đúng dependency với đúng vai trò: Config Server dùng `spring-cloud-config-server`, Config Client dùng `spring-cloud-starter-config`, còn endpoint quản trị và giám sát đến từ `spring-boot-starter-actuator`. Spring Cloud BOM giữ các dependency Cloud đồng bộ với phiên bản Spring Boot.

Sau khi khai báo dependency, cần bật `@EnableConfigServer` ở server, khai báo `spring.config.import` ở client và chỉ expose các endpoint Actuator thật sự cần thiết. Kiểm tra dependency tree, khả năng truy cập Config Server và chính sách bảo vệ management endpoint giúp môi trường chạy ổn định và dễ vận hành.
