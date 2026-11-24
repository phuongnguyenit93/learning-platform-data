# Thiết lập Eureka độc lập với profile riêng

Eureka Server là registry trung tâm để các service đăng ký instance và tra cứu lẫn nhau. Khi phát triển local hoặc chạy một môi trường demo, có thể khởi động một Eureka Server độc lập trên cổng `8761`. Spring Cloud Netflix mặc định cấu hình chính Eureka Server như một Eureka Client; nếu không điều chỉnh, server sẽ thử đăng ký với peer và tải registry từ peer dù chỉ có một node.

Cách thiết lập phù hợp cho môi trường độc lập là tạo một Spring profile riêng, ví dụ `eureka-server`, rồi đặt các thuộc tính standalone trong `application-eureka-server.yml`. Khi profile này được kích hoạt, server không tự đăng ký vào chính registry và cũng không fetch registry từ node khác. Cấu hình này phù hợp cho local/development; triển khai production cần nhiều peer để có tính sẵn sàng cao.

## 1. Cấu trúc ứng dụng

Một ứng dụng Eureka Server tối thiểu có thể được tổ chức như sau:

```text
eureka-server/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/eurekaserver/
        │       └── EurekaServerApplication.java
        └── resources/
            ├── application.yml
            └── application-eureka-server.yml
```

`application.yml` chứa cấu hình chung của ứng dụng. `application-eureka-server.yml` chứa cấu hình chỉ có hiệu lực khi profile `eureka-server` được kích hoạt. Cách tách này giúp dễ nhận biết cấu hình server độc lập và không trộn nó với cấu hình của các môi trường hoặc vai trò khác.

## 2. Khai báo dependency Eureka Server

Thêm starter `spring-cloud-starter-netflix-eureka-server` vào dự án. Không khai báo version riêng cho starter khi Spring Cloud BOM đã được import.

Ví dụ phần dependency trong `pom.xml`:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
    </dependency>
</dependencies>
```

Phần quản lý phiên bản phải dùng Spring Cloud Release Train tương thích với Spring Boot của dự án. Ví dụ môi trường Boot `4.2.0` có thể dùng Spring Cloud BOM `2026.0.0` theo bảng tương thích của Spring Cloud:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.2.0</version>
    <relativePath/>
</parent>

<properties>
    <java.version>21</java.version>
    <spring-cloud.version>2026.0.0</spring-cloud.version>
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

Đây là ví dụ phiên bản minh họa; khi tạo dự án khác, tra bảng tương thích trước và dùng service release mới nhất trong train đã chọn. Nếu dùng Gradle, cấu hình Spring Boot Gradle plugin và import cùng Spring Cloud BOM bằng dependency management để các module Spring Cloud được căn chỉnh đồng bộ.

## 3. Bật Eureka Server trong ứng dụng

Với một ứng dụng chỉ có nhiệm vụ chạy registry, đặt `@EnableEurekaServer` trên lớp main:

```java
package com.example.eurekaserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class EurekaServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(EurekaServerApplication.class, args);
    }
}
```

`@EnableEurekaServer` kích hoạt cấu hình server của Spring Cloud Netflix. Sau khi ứng dụng khởi động thành công, Eureka cung cấp dashboard và các HTTP API dưới đường dẫn `/eureka/*`.

Nếu cùng một JAR còn đảm nhiệm vai trò khác và chỉ muốn bật Eureka Server khi profile `eureka-server` được chọn, không đặt `@EnableEurekaServer` trực tiếp trên lớp main dùng chung. Thay vào đó, đặt annotation trên một cấu hình có `@Profile`:

```java
package com.example.application;

import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("eureka-server")
@EnableEurekaServer
class EurekaServerRoleConfiguration {
}
```

Lớp cấu hình này phải nằm trong phạm vi component scan của ứng dụng. Khi profile không hoạt động, cấu hình có annotation `@EnableEurekaServer` sẽ không được nạp. Với một Eureka Server chuyên biệt, cách đơn giản hơn vẫn là bật annotation trên lớp main và dùng profile riêng cho cấu hình standalone.

## 4. Cấu hình chung trong application.yml

Đặt tên ứng dụng trong `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: eureka-server
```

Không đặt `spring.profiles.active` trong file này nếu muốn profile được quyết định từ lệnh chạy hoặc biến môi trường. Việc kích hoạt từ bên ngoài giúp cùng một artifact có thể chạy với cấu hình khác nhau mà không cần đóng gói lại.

## 5. Tạo profile standalone

Tạo `src/main/resources/application-eureka-server.yml` với nội dung:

```yaml
server:
  port: 8761

eureka:
  instance:
    hostname: localhost
  client:
    register-with-eureka: false
    fetch-registry: false
    service-url:
      defaultZone: http://${eureka.instance.hostname}:${server.port}/eureka/
```

Ý nghĩa từng thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `server.port: 8761` | Mở HTTP server trên cổng mặc định thường dùng cho Eureka |
| `eureka.instance.hostname` | Tên host mà Eureka Server tự nhận diện và quảng bá |
| `eureka.client.register-with-eureka: false` | Không đăng ký chính server như một service instance vào registry |
| `eureka.client.fetch-registry: false` | Không tải danh sách service từ registry của peer |
| `eureka.client.service-url.defaultZone` | Địa chỉ Eureka service URL mặc định; cấu hình standalone trỏ về chính node |

Hai thuộc tính `register-with-eureka` và `fetch-registry` là điểm quan trọng của standalone mode. Eureka Server cũng có thành phần client; tắt hai hành vi này ngăn nó liên tục tìm peer khi chỉ chạy một node.

Chú ý: `defaultZone` là key của một `Map<String, String>` nên **phân biệt chữ hoa/chữ thường**. Giữ nguyên `defaultZone`; không viết thành `default-zone`. Spring Cloud Netflix nêu rõ ngoại lệ này trong tài liệu cấu hình.

Trong ví dụ local, `localhost` là phù hợp khi server và client chạy trên cùng máy. Nếu Eureka chạy trong Docker, Kubernetes hoặc một máy khác, `localhost` sẽ trỏ về chính container/máy của client chứ không phải Eureka Server. Hãy thay `hostname` bằng DNS name hoặc địa chỉ mà các client thực sự truy cập được, ví dụ `eureka-server` trong cùng Docker network.

## 6. Kích hoạt profile eureka-server

Spring Boot nạp file `application-{profile}.yml` khi profile tương ứng đang active. Có thể kích hoạt profile bằng tham số dòng lệnh:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=eureka-server
```

Hoặc khi chạy JAR đã build:

```bash
java -jar target/eureka-server-0.0.1-SNAPSHOT.jar --spring.profiles.active=eureka-server
```

Trên Linux/macOS có thể dùng biến môi trường:

```bash
SPRING_PROFILES_ACTIVE=eureka-server ./mvnw spring-boot:run
```

Trên PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "eureka-server"
.\mvnw.cmd spring-boot:run
```

Khi khởi động, log Spring Boot cần thể hiện profile `eureka-server` đang active. Nếu không có profile active, Spring Boot dùng profile `default`; file `application-eureka-server.yml` sẽ không được áp dụng.

Không đặt `spring.profiles.active` bên trong `application-eureka-server.yml`. Spring Boot chỉ cho phép khai báo `spring.profiles.active` và `spring.profiles.default` trong tài liệu cấu hình không gắn profile. Profile-specific file chỉ cung cấp các thuộc tính dành cho profile đã được kích hoạt.

## 7. Kiểm tra Eureka Server sau khi khởi động

Mở dashboard trong trình duyệt:

```text
http://localhost:8761/
```

Kiểm tra registry API:

```bash
curl -H "Accept: application/json" http://localhost:8761/eureka/apps
```

Trong môi trường standalone mới khởi động, danh sách instance có thể đang rỗng. Đây là trạng thái bình thường nếu chưa có Eureka Client nào đăng ký. Bản thân Eureka Server không xuất hiện như một service instance do `register-with-eureka` đã tắt.

Có thể kiểm tra thêm bằng cách xem log:

- Ứng dụng khởi động thành công và đang lắng nghe cổng `8761`.
- Active profile là `eureka-server`.
- Không có vòng lặp log liên tục về việc không thể đăng ký hoặc fetch registry từ peer.
- Dashboard có thể truy cập từ máy phát triển.

## 8. Kết nối một Eureka Client thử nghiệm

Một ứng dụng client cần starter `spring-cloud-starter-netflix-eureka-client`, tên service và địa chỉ Eureka Server:

```yaml
spring:
  application:
    name: inventory-service

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
```

Client không dùng profile `eureka-server`; profile của client có thể là `local` hoặc `dev` tùy cách tổ chức môi trường. Khi client khởi động, nó gửi thông tin instance và heartbeat tới Eureka. Sau khi đăng ký thành công, dashboard của server sẽ hiển thị `INVENTORY-SERVICE` cùng các instance tương ứng.

Đối với client chạy trong container hoặc máy khác, URL phải dùng DNS/IP có thể định tuyến tới Eureka Server, ví dụ `http://eureka-server:8761/eureka/`. Không sao chép URL `localhost` từ ví dụ local sang cấu hình triển khai phân tán.

## 9. Tách cấu hình standalone và peer-aware

Standalone mode phù hợp để học, demo hoặc phát triển trên một máy. Một Eureka Server đơn lẻ không cung cấp tính sẵn sàng cao: registry lưu dữ liệu trong bộ nhớ, và một lần server dừng có thể làm mất trạng thái đăng ký hiện tại cho đến khi các client kết nối lại và đăng ký lại.

Trong production, Spring Cloud Netflix khuyến nghị chạy nhiều Eureka Server theo mô hình peer-aware. Các node đăng ký và đồng bộ registry với peer; chúng cần địa chỉ peer có thể phân giải và truy cập được. Cấu hình peer-aware không dùng hai thuộc tính standalone `register-with-eureka: false` và `fetch-registry: false`.

Ví dụ cấu hình profile cho hai peer có thể được tổ chức thành các file riêng:

`application-eureka-peer-a.yml`:

```yaml
server:
  port: 8761
eureka:
  instance:
    hostname: eureka-a.internal
  client:
    service-url:
      defaultZone: http://eureka-b.internal:8761/eureka/
```

`application-eureka-peer-b.yml`:

```yaml
server:
  port: 8761
eureka:
  instance:
    hostname: eureka-b.internal
  client:
    service-url:
      defaultZone: http://eureka-a.internal:8761/eureka/
```

Ví dụ này chỉ minh họa hướng peer awareness. Khi triển khai thật, mỗi peer cần hostname, port, TLS, firewall và service URL phù hợp với hạ tầng. Không dùng `localhost` cho peer ở máy khác; cũng không dùng hai peer trên cùng một host/cổng như một cấu hình HA thực tế.

## 10. Một số lưu ý bảo mật và vận hành

- Chỉ mở cổng Eureka tới các service hoặc mạng quản trị cần truy cập registry. Dashboard và API `/eureka/**` không nên được phơi bày công khai.
- Nếu thêm Spring Security, cấu hình xác thực cho dashboard và client. Eureka client thường gửi các request đăng ký/heartbeat bằng HTTP; khi bật CSRF mặc định, cần cấu hình miễn CSRF phù hợp cho `/eureka/**` để các thao tác registry không bị chặn. Không tắt toàn bộ bảo mật chỉ để client đăng ký được.
- Không ghi username/password trực tiếp vào file cấu hình được commit. Dùng biến môi trường hoặc secret store của nền tảng.
- Theo dõi số lượng instance, trạng thái heartbeat, thời gian phản hồi registry, log eviction và trạng thái self-preservation.
- Cân nhắc graceful shutdown để client ngừng nhận traffic và deregister đúng trình tự trước khi process dừng.
- Bảo đảm đồng hồ hệ thống được đồng bộ và cấu hình hostname/IP mà client đăng ký có thể truy cập từ consumer.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể gặp | Cách xử lý |
|---|---|---|
| Dashboard không truy cập được | Ứng dụng chưa chạy, sai cổng hoặc profile không active | Xem log startup, kiểm tra `server.port` và profile `eureka-server` |
| Log báo không kết nối được peer | Standalone chưa tắt client-side registration/fetch hoặc service URL sai | Kiểm tra `register-with-eureka: false`, `fetch-registry: false` và profile đang nạp |
| Client không đăng ký được | Client dùng sai URL, DNS, port, firewall hoặc Eureka Server chưa sẵn sàng | Kiểm tra `defaultZone`, kết nối từ chính môi trường chạy client và log của cả hai phía |
| Client đăng ký với localhost nhưng consumer khác không gọi được | Instance quảng bá hostname/IP không thể truy cập từ consumer | Cấu hình `eureka.instance.hostname` hoặc `prefer-ip-address` và kiểm tra đường mạng |
| `defaultZone` không được nhận | Viết sai chữ hoa/chữ thường của key map | Dùng đúng `defaultZone` camel case |
| Cấu hình standalone không có hiệu lực | Chưa kích hoạt profile hoặc đặt sai tên file | Tên file phải là `application-eureka-server.yml`; active profile phải đúng `eureka-server` |
| Eureka Server vẫn bật ở profile khác | `@EnableEurekaServer` đặt trên lớp main dùng chung | Nếu server chỉ hoạt động theo profile, chuyển annotation vào `@Configuration` có `@Profile("eureka-server")` |

## 12. Checklist hoàn tất

- [ ] Đã thêm `spring-cloud-starter-netflix-eureka-server` và dùng Spring Cloud BOM tương thích.
- [ ] Đã bật `@EnableEurekaServer` đúng phạm vi ứng dụng.
- [ ] Đã tạo `application-eureka-server.yml` đúng tên profile.
- [ ] Đã đặt cổng server, hostname và service URL phù hợp môi trường.
- [ ] Đã tắt `register-with-eureka` và `fetch-registry` trong standalone mode.
- [ ] Đã giữ key `defaultZone` đúng camel case.
- [ ] Đã kích hoạt profile từ command line hoặc environment variable.
- [ ] Log startup xác nhận profile đúng và không có vòng lặp kết nối peer.
- [ ] Dashboard và `/eureka/apps` truy cập được từ mạng được phép.
- [ ] Một Eureka Client thử nghiệm đăng ký và xuất hiện trên dashboard.
- [ ] Đã phân biệt standalone local với peer-aware production và có phương án bảo vệ registry.

## Tài liệu tham khảo

- [Spring Cloud Netflix — Eureka Server, Standalone Mode và Peer Awareness](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Boot 4.2 — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot 4.2 — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud Project — Release Train và tương thích phiên bản](https://spring.io/projects/spring-cloud/)
