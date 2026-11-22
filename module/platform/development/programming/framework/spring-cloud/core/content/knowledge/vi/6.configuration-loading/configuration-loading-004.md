# Profile, tệp theo profile và nhóm profile

> **Chương:** Nạp cấu hình  
> **Module:** SPRING_CLOUD_CORE

Một ứng dụng Spring Boot thường được triển khai ở nhiều môi trường như local, test, staging và production. Các môi trường có thể dùng cùng một artifact nhưng cần endpoint, cổng, giới hạn kết nối, mức log và một số bean khác nhau. **Spring Profile** cung cấp cách đặt tên cho những ngữ cảnh cấu hình đó, để ứng dụng chọn đúng thuộc tính và thành phần khi khởi động.

Trong module **SPRING_CLOUD_CORE**, profile là một phần của quá trình nạp cấu hình bên ngoài. Profile phối hợp với `application.yml`, các tệp `application-{profile}.yml`, `@Profile`, Spring Cloud Config và các nguồn property khác. Cần hiểu profile được kích hoạt lúc nào, tệp nào được nạp, cấu hình nào ghi đè cấu hình nào và cách nhóm nhiều profile thành một lựa chọn triển khai có ý nghĩa.

## 1. Profile là gì?

**Profile** là một nhãn được Spring dùng để xác định nhóm cấu hình và bean phù hợp với một ngữ cảnh chạy. Ví dụ:

- `local`: chạy trên máy lập trình, có thể gọi dịch vụ phụ thuộc ở localhost.
- `test`: cấu hình cho kiểm thử tích hợp.
- `staging`: môi trường kiểm thử gần production.
- `production`: môi trường phục vụ người dùng thật.

Profile có hai vai trò liên quan nhưng khác nhau:

1. **Chọn cấu hình:** Spring Boot nạp các tệp hoặc document dành cho profile đang active.
2. **Chọn bean:** Spring Framework chỉ đăng ký bean được đánh dấu với `@Profile` khi điều kiện profile thỏa mãn.

Profile không tự tạo môi trường, không thay thế cơ chế phân quyền và không đảm bảo các dịch vụ bên ngoài đã sẵn sàng. Nó chỉ là điều kiện lựa chọn cấu hình và bean trong ApplicationContext.

### 1.1. Profile không phải tên instance

`production` có thể là profile của ứng dụng; `order-service` là tên logic của ứng dụng; một instance cụ thể có thể là `order-7f8c9d`. Ba giá trị trả lời ba câu hỏi khác nhau:

| Giá trị | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Profile | Ứng dụng đang dùng bộ cấu hình/bean nào? | `production` |
| Application/service name | Ứng dụng hoặc dịch vụ được nhận diện bằng tên gì? | `order-service` |
| Instance ID | Bản chạy cụ thể nào đang hoạt động? | `order-7f8c9d` |

Trong Spring Cloud, `spring.application.name` thường được dùng làm tên ứng dụng khi tích hợp discovery hoặc Config Client. Profile có thể được gửi cùng tên ứng dụng tới Config Server để lấy bộ cấu hình tương ứng. Profile không phải cơ chế thay thế service discovery, service registry hay load balancing.

## 2. Tổ chức cấu hình chung và cấu hình theo profile

Cách phổ biến là giữ thuộc tính dùng chung trong `application.yml`, rồi chỉ ghi những khác biệt trong từng tệp profile.

Ví dụ cấu trúc:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-staging.yml
  application-production.yml
~~~

Tệp `application.yml` chứa mặc định dùng chung:

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080
  shutdown: graceful

catalog:
  client:
    connect-timeout: 2s
    read-timeout: 5s
    max-attempts: 2

logging:
  level:
    root: INFO
~~~

Tệp `application-local.yml` chỉ khai báo khác biệt ở local:

~~~yaml
server:
  port: 8081

catalog:
  client:
    base-url: "http://localhost:8090"

logging:
  level:
    com.example.order: DEBUG
~~~

Tệp `application-production.yml` khai báo giá trị dành cho production:

~~~yaml
server:
  port: 8080

catalog:
  client:
    base-url: "https://catalog.internal"
    connect-timeout: 800ms
    read-timeout: 2s
    max-attempts: 2

logging:
  level:
    root: WARN
~~~

Khi profile `production` active, Spring Boot nạp cấu hình chung và cấu hình profile tương ứng. Các key được khai báo trong `application-production.yml` có thể ghi đè giá trị cùng key từ `application.yml`; các key không bị ghi đè vẫn giữ giá trị chung.

Cách tổ chức này giúp tránh lặp toàn bộ cấu hình ở mọi môi trường. Ví dụ `catalog.client.max-attempts` không cần xuất hiện trong file production nếu giá trị hai lần thử vẫn đúng với môi trường đó.

**Lưu ý:** `catalog.client.*` là namespace do ứng dụng tự định nghĩa. Các giá trị này chỉ có tác dụng khi được bind bằng `@ConfigurationProperties`, đọc bằng `@Value` hoặc được thành phần tương ứng sử dụng. Tên file profile không tự làm cho mọi key trong YAML có ý nghĩa.

## 3. Kích hoạt profile

Profile có thể được kích hoạt qua biến môi trường, tham số dòng lệnh hoặc system property. Đây là cách phù hợp để cùng một artifact chạy ở nhiều môi trường mà không phải sửa file đóng gói.

### 3.1. Kích hoạt bằng biến môi trường

Trên Linux/macOS:

~~~bash
SPRING_PROFILES_ACTIVE=production java -jar order-service.jar
~~~

Trên PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "production"
java -jar order-service.jar
~~~

Có thể kích hoạt nhiều profile cùng lúc, phân tách bằng dấu phẩy:

~~~bash
SPRING_PROFILES_ACTIVE=production,observability java -jar order-service.jar
~~~

Các profile active cùng tham gia lựa chọn cấu hình và bean. Nếu cùng một thuộc tính được khai báo ở nhiều profile, thứ tự profile có ý nghĩa; trong các nguồn profile-specific cùng mức, profile được xét sau có thể ghi đè giá trị trước đó.

### 3.2. Kích hoạt bằng tham số dòng lệnh

~~~bash
java -jar order-service.jar --spring.profiles.active=staging
~~~

Hoặc truyền system property cho JVM:

~~~bash
java -Dspring.profiles.active=staging -jar order-service.jar
~~~

Tham số dòng lệnh và system property là những nguồn cấu hình có ưu tiên cao trong cấu hình khởi chạy thông thường. Do đó chúng có thể ghi đè giá trị được khai báo trong file cấu hình. Khi có nhiều nguồn cùng đặt `spring.profiles.active`, hãy kiểm tra nguồn có độ ưu tiên cao nhất để biết profile thực sự được chọn.

### 3.3. Profile mặc định

Nếu không có profile nào được kích hoạt tường minh, Spring Boot sử dụng profile mặc định có tên `default`. Vì vậy, cấu hình chung trong `application.yml` vẫn được áp dụng khi không chọn profile cụ thể.

Có thể đổi tên profile mặc định bằng thuộc tính `spring.profiles.default`, nhưng nên cân nhắc kỹ. Nếu đặt mặc định thành `local`, một ứng dụng production khởi động thiếu biến `SPRING_PROFILES_ACTIVE` có thể vô tình nhận cấu hình local. Với dịch vụ triển khai thật, thường nên để cấu hình chung an toàn và yêu cầu pipeline hoặc nền tảng triển khai chỉ định profile rõ ràng.

Không nên dựa vào profile mặc định để quyết định quyền truy cập hoặc bảo vệ secret.

## 4. Cách Spring Boot nạp tệp theo profile

Spring Boot hỗ trợ tên tệp theo quy ước:

- `application.yml`: cấu hình chung.
- `application-{profile}.yml`: cấu hình riêng của một profile.

Ví dụ `application-test.yml` được xem xét khi profile `test` active; `application-production.yml` được xem xét khi profile `production` active.

### 4.1. Cấu hình profile-specific ghi đè cấu hình chung

Giả sử cấu hình chung có:

~~~yaml
catalog:
  client:
    connect-timeout: 2s
    read-timeout: 5s
    max-attempts: 3
~~~

Còn `application-production.yml` có:

~~~yaml
catalog:
  client:
    connect-timeout: 500ms
    read-timeout: 2s
~~~

Khi profile `production` active, kết quả có dạng:

| Property | Giá trị hiệu lực | Nguồn |
| --- | --- | --- |
| `catalog.client.connect-timeout` | `500ms` | `application-production.yml` |
| `catalog.client.read-timeout` | `2s` | `application-production.yml` |
| `catalog.client.max-attempts` | `3` | `application.yml` |

Spring Boot hợp nhất các thuộc tính theo property source; key profile-specific ghi đè key chung tương ứng. Các thuộc tính không xuất hiện trong file profile vẫn có thể lấy từ cấu hình chung.

Đối với collection, cần chú ý quy tắc hợp nhất. Ví dụ list ở cấu hình có độ ưu tiên cao hơn thường thay thế toàn bộ list ở cấu hình thấp hơn thay vì nối thêm từng phần tử. Không nên giả định hai danh sách sẽ tự động được nối với nhau. Hãy kiểm thử kết quả binding nếu cấu hình có list hoặc map phức tạp.

### 4.2. Nhiều profile active và thứ tự ưu tiên

Giả sử khởi chạy:

~~~bash
SPRING_PROFILES_ACTIVE=staging,observability java -jar order-service.jar
~~~

Ứng dụng nạp các nguồn cấu hình phù hợp với các profile được kích hoạt. Khi cùng một key được khai báo trong nhiều profile-specific sources, thứ tự profile có thể quyết định giá trị cuối cùng. Vì vậy, tránh để các profile độc lập cùng định nghĩa những thuộc tính quan trọng với giá trị mâu thuẫn.

Một cách tốt là phân chia trách nhiệm:

- `staging` và `production` quyết định endpoint, giới hạn tài nguyên và thuộc tính môi trường.
- `observability` quyết định cấu hình log, metrics hoặc tracing.
- Các giá trị nền tảng ổn định nằm trong `application.yml`.

Nếu phải kết hợp nhiều profile, hãy ghi rõ thứ tự trong cấu hình triển khai và có kiểm thử xác nhận giá trị hiệu lực.

## 5. Nhiều document trong cùng một application.yml

Thay vì tạo nhiều file, có thể đặt nhiều YAML document trong một file, phân tách bằng `---`. Dùng `spring.config.activate.on-profile` để xác định document nào được áp dụng.

~~~yaml
spring:
  application:
    name: order-service

server:
  port: 8080

catalog:
  client:
    connect-timeout: 2s

---
spring:
  config:
    activate:
      on-profile: local

server:
  port: 8081

catalog:
  client:
    base-url: "http://localhost:8090"

---
spring:
  config:
    activate:
      on-profile: production

catalog:
  client:
    base-url: "https://catalog.internal"
    connect-timeout: 800ms
~~~

Document đầu tiên không có điều kiện profile nên là cấu hình chung. Document thứ hai chỉ áp dụng khi `local` active; document thứ ba chỉ áp dụng khi `production` active.

### 5.1. Biểu thức profile

`spring.config.activate.on-profile` hỗ trợ biểu thức profile. Một số ví dụ:

| Biểu thức | Điều kiện |
| --- | --- |
| `local` | Profile `local` active |
| `!test` | Profile `test` không active |
| `"production & cloud"` | Cả `production` và `cloud` đều active |
| `"staging | production"` | Có ít nhất một trong hai profile active |

Với YAML, nên đặt biểu thức có ký tự đặc biệt như `!` hoặc `&` trong dấu nháy để tránh parser diễn giải chúng như cú pháp YAML.

Có thể dùng biểu thức tương tự trong `@Profile`. Khi kết hợp `&` và `|`, hãy dùng ngoặc để thể hiện rõ thứ tự logic; tránh biểu thức khó đọc và khó kiểm thử.

### 5.2. Không dùng cú pháp kích hoạt document cũ cho cấu hình mới

Từ Spring Boot 2.4, cơ chế Config Data thay đổi cách kích hoạt document theo profile. Cách hiện đại là:

~~~yaml
spring:
  config:
    activate:
      on-profile: production
~~~

Các dự án cũ có thể gặp cú pháp lịch sử dùng `spring.profiles` để đánh dấu document. Không sao chép cú pháp cũ sang dự án Spring Boot mới mà không kiểm tra tài liệu của đúng phiên bản. Cũng không đặt `spring.profiles.active`, `spring.profiles.default` hoặc `spring.profiles.include` bên trong một document đã được giới hạn bởi điều kiện profile; các thuộc tính này phải nằm ở document không gắn điều kiện profile.

## 6. Nhóm profile bằng spring.profiles.group

Khi một môi trường cần kích hoạt nhiều profile thành phần, việc phải truyền một danh sách dài ở mọi nơi dễ gây sai sót. **Profile group** cho phép đặt một tên nhóm đại diện cho tập profile.

Ví dụ môi trường production cần:

- `production`: cấu hình môi trường production.
- `prod-database`: cấu hình database production.
- `prod-observability`: cấu hình metrics, tracing và logging production.

Có thể khai báo nhóm trong `application.yml`:

~~~yaml
spring:
  application:
    name: order-service
  profiles:
    group:
      production:
        - prod-database
        - prod-observability
~~~

Khi kích hoạt:

~~~bash
SPRING_PROFILES_ACTIVE=production java -jar order-service.jar
~~~

Spring Boot kích hoạt profile `production` cùng các profile thành phần trong nhóm. Nhờ đó, pipeline chỉ cần biết tên nhóm `production`, còn cấu trúc thành phần được quản lý trong cấu hình ứng dụng.

Các file thành phần có thể được tổ chức riêng:

~~~text
application.yml
application-production.yml
application-prod-database.yml
application-prod-observability.yml
~~~

Ví dụ `application-prod-database.yml`:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 20
      connection-timeout: 1500
~~~

Ví dụ `application-prod-observability.yml`:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - health
          - info
          - prometheus

logging:
  level:
    root: WARN
~~~

Khi `production` active, các cấu hình thành phần được nạp cùng. Profile group giúp đặt tên cho một bộ cấu hình có ý nghĩa, đồng thời cho phép tái sử dụng profile thành phần ở các nhóm khác nếu thiết kế phù hợp.

### 6.1. Khai báo nhiều nhóm

Một ứng dụng có thể định nghĩa nhiều nhóm:

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod-database
        - prod-observability
      staging:
        - staging-database
        - staging-observability
~~~

Kích hoạt `staging` sẽ kích hoạt `staging` cùng các profile thành phần của nó. Kích hoạt `production` sẽ kích hoạt nhóm tương ứng.

Profile group phải được khai báo trong tài liệu cấu hình không gắn điều kiện profile. Không đặt khai báo group trong `application-production.yml` hoặc trong một YAML document chỉ được kích hoạt bởi `production`, vì ứng dụng cần biết cách mở rộng nhóm trước khi xử lý đầy đủ các cấu hình theo profile.

### 6.2. Profile group khác spring.profiles.include như thế nào?

Cả hai đều có thể bổ sung profile, nhưng mục đích sử dụng khác nhau:

| Cơ chế | Ý nghĩa | Khi nên dùng |
| --- | --- | --- |
| `spring.profiles.active` | Chỉ định profile được kích hoạt trực tiếp | Môi trường triển khai chọn `local`, `staging` hoặc `production` |
| `spring.profiles.include` | Bổ sung các profile luôn cần khi một cấu hình gốc được dùng | Một profile cần kéo theo cấu hình dùng chung như `common` |
| `spring.profiles.group` | Định nghĩa tên nhóm đại diện cho một tập profile | Một lựa chọn `production` cần kích hoạt nhiều profile thành phần |

Ví dụ include:

~~~yaml
spring:
  profiles:
    include:
      - common
      - metrics
~~~

`include` có thể được dùng để bổ sung profile theo cấu hình. Trong khi đó, group làm rõ quan hệ giữa một tên profile đại diện và các profile thành phần. Khi có cả active, include và group, thứ tự mở rộng và ưu tiên cấu hình cần được kiểm thử trên phiên bản Spring Boot đang dùng.

Giống `spring.profiles.active`, thuộc tính `spring.profiles.include` phải được khai báo trong document không gắn điều kiện profile. Tránh khai báo cùng một profile theo nhiều cách nếu không có lý do rõ ràng; điều đó làm cho tập profile thực tế khó dự đoán hơn.

## 7. Dùng @Profile để chọn bean

Profile không chỉ ảnh hưởng tới YAML. Spring Framework cho phép điều kiện hóa bean bằng annotation `@Profile`.

Giả sử ứng dụng cần một implementation giả lập khi chạy local và một implementation gọi hệ thống thật ở production.

Khai báo interface:

~~~java
public interface PaymentGateway {
    PaymentResult charge(String orderId, long amount);
}
~~~

Implementation cho local:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("local")
public class LocalPaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(String orderId, long amount) {
        return new PaymentResult("LOCAL-" + orderId, true);
    }
}
~~~

Implementation cho production:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("production")
public class RemotePaymentGateway implements PaymentGateway {

    @Override
    public PaymentResult charge(String orderId, long amount) {
        // Gọi payment provider qua HTTP client đã cấu hình.
        return new PaymentResult("REMOTE-" + orderId, true);
    }
}
~~~

Khi `local` active, Spring đăng ký `LocalPaymentGateway`. Khi `production` active, Spring đăng ký `RemotePaymentGateway`. Cần bảo đảm có đúng một implementation phù hợp trong mỗi ngữ cảnh; nếu không có bean nào hoặc có nhiều bean cùng thỏa mãn một dependency đơn, ứng dụng có thể không khởi động được hoặc cần qualifier/primary phù hợp.

Có thể đặt `@Profile` trên `@Configuration` hoặc phương thức `@Bean`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
public class PaymentConfiguration {

    @Bean
    @Profile("test")
    PaymentGateway testPaymentGateway() {
        return (orderId, amount) ->
                new PaymentResult("TEST-" + orderId, true);
    }
}
~~~

### 7.1. Biểu thức trong @Profile

Một số cách dùng:

~~~java
@Profile("production")
class ProductionOnlyConfiguration {
}

@Profile("local | test")
class DevelopmentConfiguration {
}

@Profile("production & cloud")
class CloudProductionConfiguration {
}

@Profile("!production")
class NonProductionConfiguration {
}
~~~

`@Profile("local | test")` có nghĩa bean được đăng ký nếu một trong hai profile active. `@Profile("production & cloud")` yêu cầu cả hai. `@Profile("!production")` áp dụng khi `production` không active.

Có thể dùng mảng tên profile như `@Profile({"local", "test"})` để diễn đạt điều kiện OR. Hãy ưu tiên biểu thức đơn giản, dễ hiểu và có kiểm thử.

Không nên dùng `@Profile` làm công cụ bật/tắt tính năng cho từng người dùng hoặc từng request. Profile được quyết định trong quá trình tạo ApplicationContext; feature flag động và quyền truy cập là những bài toán khác.

## 8. Profile trong ứng dụng Spring Cloud

Profile đặc biệt hữu ích khi cùng một dịch vụ chạy ở nhiều môi trường nhưng vẫn dùng chung mã nguồn và artifact.

### 8.1. Kết hợp profile với Spring Cloud Config

Khi ứng dụng sử dụng Spring Cloud Config Client, tên ứng dụng và profile đang active là một phần của thông tin yêu cầu cấu hình từ Config Server. Ví dụ:

~~~yaml
spring:
  application:
    name: order-service
  config:
    import: "optional:configserver:http://config-server:8888"
~~~

Nếu khởi chạy với:

~~~bash
SPRING_PROFILES_ACTIVE=production java -jar order-service.jar
~~~

Config Client có thể yêu cầu bộ cấu hình cho `order-service` và profile `production`. Config Server có thể trả cấu hình chung của ứng dụng và phần dành cho profile đó, tùy repository, label và cách cấu hình server.

Cần phân biệt:
- `application.yml` trong ứng dụng là nguồn cấu hình cục bộ.
- Config Server cung cấp nguồn cấu hình từ xa.
- Profile xác định biến thể cấu hình cần lấy.
- Property source precedence quyết định giá trị cuối cùng khi nhiều nguồn cùng khai báo một key.

Không giả định cấu hình remote luôn ghi đè mọi giá trị local theo cùng một cách ở mọi phiên bản. Quy tắc import và override phụ thuộc Config Data, vị trí import và cấu hình của Config Server. Khi có giá trị quan trọng như URL, timeout hoặc secret, hãy kiểm tra kết quả thực tế và kiểm thử quá trình khởi động.

### 8.2. Profile không thay thế discovery và service registry

Ví dụ `application-production.yml` có thể đặt endpoint gateway hoặc thuộc tính kết nối tới discovery provider. Nhưng profile chỉ chọn giá trị cấu hình. Nó không đăng ký instance, kiểm tra sức khỏe, cập nhật danh sách service hay chọn instance cho request.

Trong một ứng dụng production, có thể đồng thời cần:
- Profile `production` để nạp cấu hình môi trường.
- Discovery integration để tìm instance dịch vụ.
- Spring Cloud LoadBalancer để chọn instance phù hợp.
- Spring Cloud Context nếu cần cơ chế refresh một số bean.
- Cấu hình bên ngoài để thay đổi endpoint, credential và timeout theo môi trường.

Mỗi thành phần giải quyết một trách nhiệm khác nhau; không nên gộp tất cả vào khái niệm profile.

## 9. Kiểm thử profile và cấu hình theo profile

Profile ảnh hưởng tới bean được tạo và property được nạp, vì vậy cần kiểm thử cả hai mặt.

### 9.1. Chọn profile cho Spring Boot Test

Dùng `@ActiveProfiles` để chỉ định profile cho test context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class OrderApplicationProfileTest {

    @Autowired
    CatalogClientProperties properties;

    @Test
    void loadsTestCatalogEndpoint() {
        assertThat(properties.baseUrl().toString())
                .isEqualTo("http://localhost:9090");
    }
}
~~~

Tệp `application-test.yml` có thể khai báo:

~~~yaml
catalog:
  client:
    base-url: "http://localhost:9090"
    connect-timeout: 300ms
    read-timeout: 1s
    max-attempts: 1
~~~

`@ActiveProfiles("test")` giúp test context chọn profile một cách tường minh và ổn định. Không nên phụ thuộc profile đang được đặt tình cờ trong terminal hoặc IDE của người chạy test.

### 9.2. Kiểm thử bean theo profile

Có thể kiểm tra implementation phù hợp được tạo. Ví dụ, nếu local phải dùng gateway giả, test cần xác nhận Spring context có `LocalPaymentGateway` và không đăng ký implementation production.

~~~java
@SpringBootTest
@ActiveProfiles("local")
class LocalPaymentGatewayProfileTest {

    @Autowired
    ApplicationContext context;

    @Test
    void registersLocalGateway() {
        assertThat(context.getBean(PaymentGateway.class))
                .isInstanceOf(LocalPaymentGateway.class);
    }
}
~~~

Ví dụ trên cần import `ApplicationContext`, AssertJ và các lớp trong dự án. Điều quan trọng là test xác nhận **hành vi lựa chọn bean**, không chỉ xác nhận profile string tồn tại.

### 9.3. Kiểm thử nhóm profile

Với group `production` gồm `prod-database` và `prod-observability`, nên kiểm tra các property thuộc cả ba nguồn khi profile group được kích hoạt. Có thể dùng test context với `@ActiveProfiles("production")` và xác nhận các bean/property mong đợi.

Ngoài kiểm thử đơn vị, pipeline nên có smoke test khởi động ứng dụng với profile triển khai tương ứng. Điều này phát hiện trường hợp thiếu biến môi trường, thiếu file profile, cấu hình group sai hoặc bean không có implementation phù hợp.

## 10. Lỗi thường gặp và cách tránh

1. **Đặt `spring.profiles.active` trong `application-production.yml`:** thuộc tính kích hoạt profile phải được cung cấp từ cấu hình không gắn điều kiện profile hoặc từ nguồn bên ngoài; không dùng file profile để tự kích hoạt chính nó.
2. **Nhầm `spring.config.activate.on-profile` với `spring.profiles.active`:** một thuộc tính giới hạn document; thuộc tính còn lại chọn profile active.
3. **Dùng cú pháp cũ trên Spring Boot mới:** từ Boot 2.4, dùng Config Data và `spring.config.activate.on-profile` cho document có điều kiện.
4. **Kích hoạt profile sai chính tả:** `prod` và `production` là hai tên khác nhau. Chuẩn hóa tên ở pipeline và file.
5. **Đặt nhiều giá trị mâu thuẫn trong nhiều profile:** kiểm tra thứ tự active và giá trị hiệu lực; tránh dựa vào thứ tự ngẫu nhiên của môi trường chạy.
6. **Lặp toàn bộ cấu hình ở mọi file:** chỉ ghi khác biệt trong profile-specific file để giảm drift.
7. **Dùng profile như cơ chế bí mật hoặc phân quyền:** secret phải đến từ nguồn bảo mật; quyền truy cập phải được kiểm soát độc lập.
8. **Tạo quá nhiều profile kết hợp:** profile group có thể gom các phần cấu hình có ý nghĩa, nhưng không nên biến mỗi thuộc tính hoặc mỗi biến thể nhỏ thành một profile.
9. **Không kiểm thử profile production:** thêm smoke test với đúng profile và cấu hình triển khai.
10. **Cho rằng profile group tự tạo hạ tầng:** group chỉ kích hoạt thêm profile; nó không tạo database, registry, secret hoặc endpoint.

## 11. Quy trình lựa chọn profile cho một dịch vụ

Khi thiết kế profile cho một dịch vụ Spring Cloud, có thể thực hiện theo trình tự:

1. Xác định các môi trường thực tế mà artifact phải chạy: local, test, staging và production.
2. Đặt cấu hình chung, an toàn và có thể dùng lại trong `application.yml`.
3. Tạo `application-{profile}.yml` cho những khác biệt thực sự của từng môi trường.
4. Chọn cách kích hoạt profile qua biến môi trường hoặc tham số triển khai; tránh hard-code production trong artifact.
5. Nếu một môi trường cần nhiều nhóm cấu hình thành phần, định nghĩa `spring.profiles.group`.
6. Dùng `@Profile` cho bean thay thế theo môi trường, đồng thời bảo đảm mỗi ngữ cảnh có implementation phù hợp.
7. Nếu dùng Config Server, xác nhận tên ứng dụng, profile, label và nguồn cấu hình được nạp.
8. Viết test cho property binding, bean selection, profile group và các giá trị ghi đè.
9. Kiểm tra cú pháp và khả năng tương thích với phiên bản Spring Boot/Spring Cloud đang sử dụng.

**Điểm ghi nhớ:** Profile là nhãn để chọn cấu hình và bean trong lúc khởi tạo ứng dụng. `application-{profile}.yml` cung cấp phần cấu hình riêng, `spring.config.activate.on-profile` chọn document trong một file, còn `spring.profiles.group` gom nhiều profile thành một lựa chọn triển khai có ý nghĩa. Khi dùng Spring Cloud, profile phối hợp với Config Client và các nguồn cấu hình bên ngoài; nó vẫn có vòng đời riêng và không thay thế discovery, registry, load balancing hay cơ chế bảo mật.
