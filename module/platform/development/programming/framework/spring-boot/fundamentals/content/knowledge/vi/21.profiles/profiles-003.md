# spring.profiles.active và profile mặc định

Spring Boot thường cần chạy cùng một mã nguồn trong nhiều bối cảnh: máy lập trình viên, môi trường kiểm thử, staging và production. Những bối cảnh này có thể dùng database, endpoint, logging và implementation khác nhau. Nếu phải sửa source code mỗi lần triển khai, ứng dụng sẽ khó kiểm soát và dễ phát sinh lỗi.

**Spring Profiles** là cơ chế cho phép gắn một nhóm cấu hình hoặc bean với một tên profile. Hai khái niệm quan trọng nhất là:

- **Active profiles:** các profile đang được kích hoạt; trong Spring Boot có thể cấu hình bằng `spring.profiles.active`.
- **Default profiles:** profile dùng khi *không có active profile nào*; tên mặc định của Spring là `default`, và có thể thay đổi qua `spring.profiles.default`.

Đây không phải hai cách đặt tên cho cùng một thứ. Khi active profile `prod` tồn tại, cấu hình dành riêng cho default profile không tự được kích hoạt thêm. Ngược lại, nếu danh sách active profile rỗng, Spring dùng default profile để quyết định những cấu hình có `@Profile` nào phù hợp.

Bài học này giải thích cách thiết lập, kết hợp và chẩn đoán active/default profiles trong Spring Boot, bao gồm cấu hình qua YAML, properties, command line, biến môi trường, Java API, Config Data và kiểm thử.

## 1. Profile giải quyết bài toán gì?

Giả sử ứng dụng gửi thông báo đơn hàng. Ở môi trường lập trình, ta muốn dùng implementation mô phỏng để không gửi email thật. Ở production, ứng dụng cần một implementation gửi qua dịch vụ thật.

Không dùng profile, code có thể có điều kiện môi trường rải rác:

~~~java
if ("prod".equals(environmentName)) {
    return new SmtpNotificationSender(...);
}

return new LoggingNotificationSender();
~~~

Cách này buộc nhiều service phải biết tên môi trường và làm logic nghiệp vụ phụ thuộc cấu hình triển khai.

Với profile, Spring có thể chọn bean phù hợp lúc dựng `ApplicationContext`:

~~~java
@Configuration(proxyBeanMethods = false)
public class NotificationConfiguration {

    @Bean
    @Profile("dev")
    NotificationSender developmentNotificationSender() {
        return new LoggingNotificationSender();
    }

    @Bean
    @Profile("prod")
    NotificationSender productionNotificationSender() {
        return new SmtpNotificationSender();
    }
}
~~~

Các class `NotificationSender`, `LoggingNotificationSender` và `SmtpNotificationSender` là thành phần minh họa của ứng dụng.

Service sử dụng chỉ cần dependency:

~~~java
@Service
public class OrderService {

    private final NotificationSender notificationSender;

    public OrderService(NotificationSender notificationSender) {
        this.notificationSender = notificationSender;
    }

    public void confirmOrder(String customerId) {
        notificationSender.send(
                customerId,
                "Your order has been confirmed"
        );
    }
}
~~~

`OrderService` không cần tự kiểm tra profile. Spring quyết định bean definition nào được đăng ký khi context được xây dựng.

**Lưu ý:** nếu không bật `dev` hoặc `prod`, hai bean trên đều không được tạo từ cấu hình này. Nếu `OrderService` bắt buộc cần một `NotificationSender` và không có bean khác, ứng dụng sẽ lỗi khi khởi động. Đây là hành vi cần được thiết kế có chủ đích, không phải Spring tự chọn một implementation bất kỳ.

## 2. Active profile là gì?

Active profile là profile đã được kích hoạt trong `Environment` của Spring. Ví dụ:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Với cấu hình này, profile `dev` được xem là active. Các bean hoặc configuration class có điều kiện `@Profile("dev")` có thể được áp dụng, miễn là những điều kiện đăng ký khác cũng thỏa.

Có thể bật nhiều profile:

~~~yaml
spring:
  profiles:
    active: dev,observability
~~~

Hoặc dùng dạng danh sách trong YAML:

~~~yaml
spring:
  profiles:
    active:
      - dev
      - observability
~~~

Khi đó, ứng dụng đồng thời có nhóm cấu hình `dev` và `observability`.

### Profile không nhất thiết là tên môi trường triển khai

Nhiều dự án đặt tên profile là `dev`, `test`, `staging`, `prod`. Nhưng Spring không giới hạn chỉ có bốn tên đó. Một profile có thể đại diện cho một nhóm khả năng:

- `observability`: bổ sung cấu hình quan sát.
- `cloud`: bật một nhóm thành phần tích hợp cloud.
- `mock-payment`: dùng payment adapter mô phỏng.
- `local-db`: cấu hình database cục bộ.

Tuy nhiên, cần tránh lạm dụng profile cho mọi feature flag nhỏ. Với tính năng cần bật/tắt độc lập bằng cấu hình, `@ConditionalOnProperty` và `@ConfigurationProperties` có thể dễ bảo trì hơn.

### Cùng một ứng dụng có nhiều active profiles

Ví dụ:

~~~bash
java -jar store.jar --spring.profiles.active=prod,observability
~~~

Spring sẽ xem xét các cấu hình dành cho cả `prod` và `observability`. Nếu hai profile đăng ký hai bean cùng kiểu và injection không xác định lựa chọn, có thể xuất hiện `NoUniqueBeanDefinitionException`. Vì thế, nhiều profile không có nghĩa các cấu hình của chúng luôn kết hợp được mà không xung đột.

## 3. Profile mặc định là gì?

Khi không khai báo bất kỳ active profile nào, Spring vẫn cần một ngữ cảnh để đánh giá cấu hình có điều kiện profile. Nó dùng **default profile**.

Trong cấu hình mặc định của Spring, tên default profile là:

~~~text
default
~~~

Nếu không bật profile nào:

~~~java
@Profile("default")
@Configuration
public class DefaultOnlyConfiguration {
    // ...
}
~~~

cấu hình này có thể được áp dụng.

Ngược lại:

~~~java
@Profile("prod")
@Configuration
public class ProductionConfiguration {
    // ...
}
~~~

không được áp dụng vì `prod` không active.

### Default không đồng nghĩa với dev

Spring mặc định dùng tên `default`, **không phải `dev`**. Một số ứng dụng tự cấu hình default profile thành `local` hoặc `dev`, nhưng đó là quyết định của dự án.

Cũng không nên giả định môi trường không có active profile thì toàn bộ ứng dụng mặc nhiên chạy theo cấu hình dev. Chỉ các bean không có điều kiện profile và những bean có condition khớp default profile mới được đăng ký.

### Khi bật active profile thì điều gì xảy ra?

Giả sử ứng dụng có:

~~~java
@Bean
@Profile("default")
DataSource embeddedDataSource() {
    return createEmbeddedDataSource();
}

@Bean
@Profile("prod")
DataSource productionDataSource() {
    return createProductionDataSource();
}
~~~

Nếu không bật active profile, bean từ `@Profile("default")` có thể được đăng ký. Nếu chạy với:

~~~bash
java -jar store.jar --spring.profiles.active=prod
~~~

bean mặc định sẽ không được đăng ký từ cấu hình đó, còn bean production có thể được đăng ký.

Default profile chỉ là **fallback khi active profile rỗng**, không tự động được cộng vào active profiles.

## 4. spring.profiles.default: thay tên profile mặc định

Spring Boot cho phép đổi default profile:

~~~yaml
spring:
  profiles:
    default: local
~~~

Với cấu hình này, nếu không có active profile nào, Spring coi `local` là default profile. Điều kiện:

~~~java
@Profile("local")
@Configuration
public class LocalConfiguration {
}
~~~

có thể match dù `environment.getActiveProfiles()` vẫn trả mảng rỗng.

### Ví dụ cấu hình local fallback

`application.yml`:

~~~yaml
spring:
  profiles:
    default: local
~~~

`application-local.yml`:

~~~yaml
app:
  payment:
    mode: simulation
    endpoint: http://localhost:9095
~~~

`application-prod.yml`:

~~~yaml
app:
  payment:
    mode: live
    endpoint: https://payments.example.internal
~~~

Khi khởi động mà không cung cấp active profile:

1. Spring đọc cấu hình chung.
2. Danh sách active profiles không có phần tử.
3. Default profile `local` được sử dụng cho profile matching và nạp Config Data phù hợp.
4. `application-local.yml` có thể được nạp.

Khi khởi động với `prod`:

~~~bash
java -jar store.jar --spring.profiles.active=prod
~~~

Spring dùng `prod` thay vì fallback `local`; `application-prod.yml` được áp dụng theo quy tắc Config Data.

### Có thể bỏ default profile không?

Trong cơ chế Config Data của Spring Boot, có thể cấu hình:

~~~yaml
spring:
  profiles:
    default: none
~~~

`none` là giá trị được Spring Boot tài liệu hóa để **không bật default profile được dùng như một cấu hình môi trường thông thường**. Khi chọn cách này, nên thiết kế ứng dụng yêu cầu active profile rõ ràng hoặc đảm bảo những bean không có profile đã đủ để khởi động.

Không nên dùng `none` như tên của một môi trường nghiệp vụ và mong nó tương đương với `dev` hay `prod`.

## 5. Active và default profiles khác nhau như thế nào?

Một bảng tóm tắt:

| Tiêu chí | Active profiles | Default profiles |
|---|---|---|
| Cấu hình Boot | `spring.profiles.active` | `spring.profiles.default` |
| Mục đích | Chọn profile muốn chạy | Fallback khi chưa chọn active profile |
| API đọc | `Environment.getActiveProfiles()` | `Environment.getDefaultProfiles()` |
| Khi có active profile | Được dùng để match | Không tự được áp dụng thêm |
| Khi active rỗng | Không có profile active | Được sử dụng để match |
| Giá trị Spring thường dùng | Không có sẵn profile cụ thể | `default` |
| Có thể thay qua command line? | Có | Có |
| Có thể liên quan file profile-specific? | Có | Có, khi được dùng làm fallback |

### Ví dụ 1: không cấu hình profile

~~~text
spring.profiles.active:  [không được đặt]
spring.profiles.default: [không được đặt]
~~~

Khi đó:

~~~text
getActiveProfiles()  -> []
getDefaultProfiles() -> ["default"]
Profile đang dùng để match -> default
~~~

### Ví dụ 2: đổi default sang local

~~~yaml
spring:
  profiles:
    default: local
~~~

Khi không có active profile:

~~~text
getActiveProfiles()  -> []
getDefaultProfiles() -> ["local"]
Profile đang dùng để match -> local
~~~

### Ví dụ 3: cùng đặt active và default

~~~yaml
spring:
  profiles:
    active: prod
    default: local
~~~

Khi đó:

~~~text
getActiveProfiles()  -> ["prod"]
getDefaultProfiles() -> ["local"]
Profile đang dùng để match -> prod
~~~

`local` vẫn là giá trị default được cấu hình, nhưng nó chỉ có tác dụng fallback nếu active profiles không còn.

## 6. Khai báo trong application.properties

YAML không phải cách duy nhất. Trong `application.properties`:

~~~properties
spring.profiles.active=dev
~~~

Hoặc nhiều profile:

~~~properties
spring.profiles.active=dev,observability
~~~

Default profile:

~~~properties
spring.profiles.default=local
~~~

Để vô hiệu hóa default profile theo cơ chế Boot:

~~~properties
spring.profiles.default=none
~~~

Spring Boot nạp `application.properties` và `application.yml` qua Config Data. Nếu cùng một key có mặt ở nhiều property source, giá trị cuối phụ thuộc vào **thứ tự ưu tiên** của những nguồn đó.

### Không cần cả properties và YAML cùng đặt giá trị

Một dự án nên tránh phân tán cùng một cấu hình cốt lõi sang nhiều file trừ khi việc override có chủ đích. Khi cần biết profile nào đang chạy, hãy tìm **giá trị hiệu lực trong Environment**, không kết luận chỉ từ file đang mở.

## 7. Kích hoạt profile từ command line

Một cách thông dụng khi triển khai ứng dụng là truyền option lúc chạy:

~~~bash
java -jar store-service.jar --spring.profiles.active=prod
~~~

Nhiều profile:

~~~bash
java -jar store-service.jar --spring.profiles.active=prod,observability
~~~

Đổi default profile nhưng không kích hoạt profile cụ thể:

~~~bash
java -jar store-service.jar --spring.profiles.default=local
~~~

### Command-line property có thể ghi đè YAML

Giả sử file `application.yml` khai báo:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Nhưng lệnh chạy là:

~~~bash
java -jar store-service.jar --spring.profiles.active=prod
~~~

Trong cấu hình Spring Boot thông thường, command-line properties có độ ưu tiên cao hơn Config Data từ file application. Kết quả hiệu lực là `prod`, không phải `dev`.

Đây là điểm hữu ích để xây dựng một artifact duy nhất rồi triển khai vào nhiều môi trường mà không cần sửa JAR.

### Cẩn thận với thứ tự tham số Java

System property của JVM cần đặt trước `-jar`:

~~~bash
java -Dspring.profiles.active=prod -jar store-service.jar
~~~

Còn Spring Boot command-line argument thường đặt sau tên JAR:

~~~bash
java -jar store-service.jar --spring.profiles.active=prod
~~~

Hai cú pháp thuộc hai cơ chế khác nhau nhưng đều có thể đưa property vào quá trình khởi động.

## 8. Kích hoạt profile bằng biến môi trường

Trong Linux/macOS shell:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
java -jar store-service.jar
~~~

Hoặc một lệnh:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar store-service.jar
~~~

Trong PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "prod"
java -jar store-service.jar
~~~

Biến môi trường `SPRING_PROFILES_ACTIVE` được Spring Boot nhận diện tương ứng với property `spring.profiles.active` qua cơ chế cấu hình Environment.

Có thể dùng dấu phẩy cho nhiều profile:

~~~bash
export SPRING_PROFILES_ACTIVE=prod,observability
~~~

Đổi default:

~~~bash
export SPRING_PROFILES_DEFAULT=local
~~~

### Biến môi trường phù hợp với container và CI/CD

Trong Docker, Kubernetes hoặc pipeline, profile thường được chọn tại thời điểm triển khai, không đóng cứng trong source code.

Ví dụ khái niệm cho một container:

~~~yaml
services:
  store:
    image: example/store-service:latest
    environment:
      SPRING_PROFILES_ACTIVE: prod
~~~

Đây là đoạn cấu hình theo phong cách Compose để minh họa việc truyền biến môi trường. Cấu hình thực tế phụ thuộc công cụ triển khai.

**Không đặt credential hoặc secret vào tên profile.** Profile là nhãn môi trường/khả năng; secret nên được cung cấp qua secret manager, config tree hoặc nguồn cấu hình bảo mật phù hợp.

## 9. Thứ tự ưu tiên khi nhiều nguồn đặt spring.profiles.active

Environment chứa nhiều `PropertySource`. Cùng một property có thể được khai báo ở nhiều nơi, ví dụ:

~~~text
Command line:      --spring.profiles.active=prod
System property:   -Dspring.profiles.active=staging
Environment:       SPRING_PROFILES_ACTIVE=qa
application.yml:   spring.profiles.active=dev
Default property:  spring.profiles.active=local
~~~

Trong cấu hình Boot thông thường, command-line argument có độ ưu tiên cao hơn system properties, environment variables và file Config Data; giá trị cao hơn sẽ được dùng.

Điểm quan trọng: **`spring.profiles.active` từ nhiều nguồn không tự cộng thành danh sách hợp nhất**. Nguồn có precedence cao hơn quyết định giá trị hiệu lực cho property đó.

Ví dụ:

`application.yml`:

~~~yaml
spring:
  profiles:
    active: dev
~~~

Command line:

~~~bash
java -jar store-service.jar --spring.profiles.active=prod
~~~

Kết quả không phải `dev,prod`. Kết quả thông thường là `prod`.

Nếu mục đích là **bổ sung profile** thay vì ghi đè danh sách active, hãy xem `spring.profiles.include`, profile groups hoặc `SpringApplication.setAdditionalProfiles`.

### Lưu ý về các nguồn khác

Trong môi trường test, `@TestPropertySource`, `@SpringBootTest(properties = ...)` hoặc `@ActiveProfiles` có thể thay đổi cách profile được chọn. Một số môi trường còn có config data import, cloud config và custom property sources. Khi có nghi vấn, quan sát Environment lúc chạy và các nguồn cấu hình được nạp.

## 10. Application profile-specific: application-{profile}.yml

Spring Boot nhận diện những file cấu hình theo profile, ví dụ:

~~~text
src/main/resources/
├── application.yml
├── application-dev.yml
├── application-test.yml
├── application-staging.yml
└── application-prod.yml
~~~

File chung:

~~~yaml
spring:
  application:
    name: store-service

app:
  payment:
    timeout: 3s
  catalog:
    cache-enabled: false
~~~

File development:

~~~yaml
app:
  payment:
    endpoint: http://localhost:9090
  catalog:
    cache-enabled: false
~~~

File production:

~~~yaml
app:
  payment:
    endpoint: https://payments.example.internal
    timeout: 8s
  catalog:
    cache-enabled: true
~~~

Khi profile `prod` active, Spring Boot có thể nạp `application-prod.yml` bên cạnh cấu hình chung. Giá trị profile-specific có thể ghi đè giá trị tương ứng ở file chung theo quy tắc Config Data.

Với ví dụ:

~~~text
app.payment.timeout -> 8s
app.catalog.cache-enabled -> true
app.payment.endpoint -> https://payments.example.internal
~~~

### File phải ở location được Spring Boot tìm

Nếu đặt `application-prod.yml` trong một thư mục tùy ý mà Boot không tìm, file sẽ không được nạp chỉ vì tên có hậu tố `prod`. Các vị trí mặc định và các property như `spring.config.location`, `spring.config.additional-location` hoặc `spring.config.import` quyết định nơi lấy Config Data.

### Không cần có file cho mọi profile

Một profile có thể chỉ dùng để chọn bean bằng `@Profile` mà không có file `application-{profile}.yml`. Ngược lại, một file profile-specific có thể thay property nhưng ứng dụng không có bean nào mang `@Profile`.

Profile là nhãn chung cho cả hai cơ chế, nhưng không bắt buộc phải tồn tại đồng thời.

## 11. Default profile và file application-default.yml

Vì Spring có default profile tên `default`, file:

~~~text
application-default.yml
~~~

có thể được nạp khi không có active profile nào và default profile vẫn là `default`.

Ví dụ:

~~~yaml
app:
  mail:
    sender: logging
  payment:
    mode: simulation
~~~

Nếu chạy không có active profile, các giá trị này có thể được sử dụng theo precedence.

Nếu đổi default profile:

~~~yaml
spring:
  profiles:
    default: local
~~~

thì file `application-local.yml` trở thành profile-specific file phù hợp cho fallback, không nên giả định `application-default.yml` vẫn được nạp như trước.

### Có nên dùng application-default.yml cho production?

Thông thường **không nên**. Nếu ứng dụng không được cấu hình rõ môi trường mà lại mặc định kết nối hệ thống production, một lần chạy thử có thể gây side effect thật.

Dự án nên chọn chính sách rõ:

- Không có active profile thì chỉ chạy local-safe defaults.
- Hoặc ứng dụng bắt buộc phải được cấp profile/cấu hình khi triển khai, thiếu cấu hình sẽ fail fast.
- Không dùng môi trường production như fallback không được kiểm soát.

## 12. Nhiều active profiles và thứ tự override

Có thể kích hoạt:

~~~properties
spring.profiles.active=dev,observability
~~~

Khi có nhiều file profile-specific cùng chứa một key, **thứ tự profile và quy tắc Config Data precedence** có thể làm thay đổi giá trị cuối.

Ví dụ:

`application-dev.yml`:

~~~yaml
app:
  diagnostics:
    level: basic
~~~

`application-observability.yml`:

~~~yaml
app:
  diagnostics:
    level: detailed
~~~

Với các location thông thường và cùng mức ưu tiên, trong các phiên bản Spring Boot hiện đại, cấu hình của profile được xử lý sau có thể ghi đè cấu hình trước; danh sách profile thường dùng quy tắc *last wins* cho profile-specific property values. Nhưng trong bài toán thực tế còn có location groups, import, property sources từ môi trường và quy tắc khác.

Vì vậy:

- Tránh để nhiều profile độc lập cùng quyết định một property quan trọng.
- Khi có xung đột, đọc giá trị hiệu lực từ Environment.
- Không sử dụng thứ tự profile làm một cơ chế routing nghiệp vụ khó quan sát.
- Nếu hai profile có ý nghĩa loại trừ, hãy tránh kích hoạt chúng cùng lúc hoặc kiểm tra điều kiện khởi động.

### Hai profile có thể đăng ký hai bean cùng kiểu

~~~java
@Bean
@Profile("dev")
PaymentGateway devGateway() {
    return new FakePaymentGateway();
}

@Bean
@Profile("staging")
PaymentGateway stagingGateway() {
    return new SandboxPaymentGateway();
}
~~~

Nếu cả `dev` và `staging` active, cả hai bean có thể được đăng ký. Consumer inject một `PaymentGateway` đơn lẻ có thể gặp ambiguity nếu không có `@Primary` hoặc `@Qualifier` phù hợp.

Không nên cho rằng profile phía sau tự “ghi đè” bean phía trước như property. **Override property và đăng ký bean là hai cơ chế khác nhau.**

## 13. @Profile trên @Configuration và @Bean

`@Profile` nằm trong Spring Framework:

~~~java
org.springframework.context.annotation.Profile
~~~

Đặt trên class:

~~~java
@Configuration(proxyBeanMethods = false)
@Profile("prod")
public class ProductionPaymentConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new RealPaymentGateway();
    }

    @Bean
    PaymentAuditPublisher paymentAuditPublisher() {
        return new PaymentAuditPublisher();
    }
}
~~~

Nếu `prod` không match, configuration class bị bỏ qua trong giai đoạn processing, những bean definitions do class này cung cấp cũng không được đăng ký.

Đặt trên method:

~~~java
@Configuration(proxyBeanMethods = false)
public class PaymentConfiguration {

    @Bean
    @Profile("dev")
    PaymentGateway fakePaymentGateway() {
        return new FakePaymentGateway();
    }

    @Bean
    @Profile("prod")
    PaymentGateway realPaymentGateway() {
        return new RealPaymentGateway();
    }
}
~~~

Từng bean method có điều kiện độc lập.

### Bean không có @Profile thì sao?

~~~java
@Bean
Clock clock() {
    return Clock.systemUTC();
}
~~~

Nếu không bị condition khác loại bỏ và configuration class được xử lý, bean không có `@Profile` có thể được đăng ký trong mọi môi trường. `@Profile` không bắt buộc cho tất cả bean.

### @Profile chỉ hiệu lực với bean do Spring quản lý

~~~java
RealPaymentGateway gateway = new RealPaymentGateway();
~~~

Một object được tạo trực tiếp bằng `new` không được Spring tự áp dụng `@Profile`. Annotation profile là điều kiện đăng ký bean/configuration trong container, không phải một công tắc cho mọi đối tượng Java.

## 14. @Profile("default") hoạt động thế nào?

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
public class StorageConfiguration {

    @Bean
    @Profile("default")
    StorageClient localStorageClient() {
        return new LocalStorageClient();
    }

    @Bean
    @Profile("prod")
    StorageClient productionStorageClient() {
        return new CloudStorageClient();
    }
}
~~~

Trường hợp A: không có active profile và default profile là `default`. Bean local có thể được đăng ký.

Trường hợp B: active profile là `prod`. Bean production có thể được đăng ký; bean default không tự đi kèm.

Trường hợp C: default profile đã đổi thành `local` và không có active profile. `@Profile("default")` không còn là fallback phù hợp; muốn nhận fallback local nên dùng `@Profile("local")`.

Trường hợp D: active profile là `test` nhưng không có bean `StorageClient` cho `test`. Bean default cũng không tự chạy chỉ vì test không có implementation.

Vì vậy, `@Profile("default")` là một **điều kiện profile cụ thể**, không phải “hãy chọn bean này nếu mọi bean khác đều vắng mặt”. Nếu cần một fallback bean dựa trên sự vắng mặt của bean khác, `@ConditionalOnMissingBean` trong auto-configuration phù hợp có semantics khác và phải cân nhắc thứ tự đăng ký bean.

## 15. Profile expression: kết hợp và phủ định

`@Profile` hỗ trợ biểu thức profile trong Spring Framework hiện đại. Ví dụ:

~~~java
@Configuration
@Profile("prod & !test")
public class ProductionOnlyConfiguration {
}
~~~

Ý nghĩa: profile `prod` được chọn và profile `test` không được chọn.

Một điều kiện khác:

~~~java
@Profile("dev | staging")
@Configuration
public class NonProductionConfiguration {
}
~~~

Ý nghĩa: `dev` hoặc `staging` phù hợp.

Phủ định:

~~~java
@Profile("!prod")
@Configuration
public class NotProductionConfiguration {
}
~~~

Cấu hình này có thể match khi `prod` không active, kể cả trong một môi trường mới chưa được nhóm phát triển dự kiến. Vì thế, `!prod` không đồng nghĩa “chỉ local”.

### Chọn biểu thức dễ hiểu

Nếu cần đúng dev và test, dùng:

~~~java
@Profile("dev | test")
~~~

thay vì:

~~~java
@Profile("!prod")
~~~

vì hệ thống có thể có các profile khác như `staging`, `benchmark` hoặc `disaster-recovery`.

### Nhiều giá trị trong annotation

~~~java
@Profile({"dev", "test"})
~~~

thể hiện điều kiện OR giữa những giá trị khai báo. Khi biểu thức phức tạp, nên dùng một biểu thức rõ ràng thay vì kết hợp nhiều chuỗi mà ý nghĩa logic khó đọc.

## 16. Cấu hình đa document trong application.yml

Ngoài file `application-{profile}.yml`, Spring Boot hỗ trợ nhiều document trong một file YAML, phân cách bằng `---`.

Ví dụ:

~~~yaml
app:
  payment:
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: dev

app:
  payment:
    endpoint: http://localhost:9090

---
spring:
  config:
    activate:
      on-profile: prod

app:
  payment:
    endpoint: https://payments.example.internal
    timeout: 8s
~~~

Document đầu chứa cấu hình chung. Document thứ hai chỉ được dùng khi biểu thức `on-profile: dev` phù hợp. Document thứ ba chỉ được dùng với `prod`.

### spring.config.activate.on-profile không kích hoạt profile

Cấu hình:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
~~~

**không yêu cầu Spring chuyển sang profile prod**. Nó có nghĩa: “chỉ sử dụng document này khi profile prod đã phù hợp theo Environment”.

Để chọn profile active, dùng `spring.profiles.active` ở vị trí hợp lệ hoặc nguồn cấu hình khởi động như command line.

### Multi-document .properties

Trong các phiên bản Boot hỗ trợ multi-document properties, có thể dùng marker phù hợp của định dạng đó, khác với `---` của YAML. Nếu dự án dùng properties thay vì YAML, hãy kiểm tra cú pháp của phiên bản Boot và tránh sao chép trực tiếp cú pháp YAML sang file .properties.

## 17. Không đặt spring.profiles.active trong profile-specific document

Đây là một giới hạn quan trọng của cơ chế **Config Data** từ Spring Boot 2.4 trở đi:

Những property chọn profile như `spring.profiles.active` và `spring.profiles.default` chỉ được khai báo ở **non-profile-specific documents**. Không được đặt chúng trong file dành riêng cho profile hoặc document đã được kích hoạt bởi `spring.config.activate.on-profile`.

Ví dụ **sai** trong `application-prod.yml`:

~~~yaml
spring:
  profiles:
    active: metrics
~~~

File `application-prod.yml` chỉ được nạp khi profile prod đã phù hợp. Nếu lại để nó quyết định active profile, quá trình chọn profile dễ trở thành vòng phụ thuộc, nên Boot không cho phép cách khai báo này.

Ví dụ **sai** trong multi-document YAML:

~~~yaml
spring:
  config:
    activate:
      on-profile: prod
  profiles:
    active: metrics
~~~

Document đã phụ thuộc profile `prod` nhưng lại cố đặt danh sách active profiles.

### Cách làm đúng

Đặt active profile trong document chung, trước phần kích hoạt theo profile:

~~~yaml
spring:
  profiles:
    active: prod

---
spring:
  config:
    activate:
      on-profile: prod

app:
  payment:
    endpoint: https://payments.example.internal
~~~

Trong môi trường triển khai thực tế, thường tốt hơn khi **không đóng cứng prod trong source** mà truyền `--spring.profiles.active=prod` hoặc `SPRING_PROFILES_ACTIVE=prod`.

### Giới hạn tương tự với profile include và group

Những property như `spring.profiles.include` và `spring.profiles.group` cũng phải nằm ở vị trí hợp lệ theo quy tắc Config Data; không đặt chúng trong profile-specific document hoặc document đã được kích hoạt theo profile.

Nếu ứng dụng xuất hiện lỗi về invalid profile property, hãy kiểm tra **property được khai báo ở document nào**, không chỉ kiểm tra tên và giá trị.

## 18. spring.profiles.include: bổ sung profile

`spring.profiles.include` dùng để **bổ sung** những profile vào tập profile cần kích hoạt. Ví dụ:

~~~yaml
spring:
  profiles:
    include:
      - common
      - observability
~~~

Ứng dụng có thể chạy với:

~~~bash
java -jar store.jar --spring.profiles.active=prod
~~~

và vẫn bổ sung các profile `common`, `observability` theo quy tắc xử lý profile của Spring Boot.

`include` khác `active` ở chỗ mục tiêu là thêm profile, không chỉ thay giá trị danh sách active từ một property source có độ ưu tiên cao hơn.

### Không đặt include trong application-prod.yml

Ví dụ không hợp lệ trong cơ chế Config Data hiện đại:

~~~yaml
# application-prod.yml
spring:
  profiles:
    include: observability
~~~

Nếu chỉ muốn profile `prod` kích hoạt thêm các nhóm phù hợp, hãy cân nhắc **profile group** được định nghĩa trong document không profile-specific.

### Include cũng cần có lý do

Nếu nhiều module/thư viện tự thêm profile mà không có thiết kế thống nhất, active profile cuối có thể khó dự đoán. Profile nên là hợp đồng cấu hình được tài liệu hóa, không phải một thay đổi ẩn trong module không liên quan.

## 19. spring.profiles.group: mở rộng một profile thành nhóm

Profile group cho phép một tên profile đại diện cho nhiều profile thành viên.

Ví dụ trong `application.yml` (document chung):

~~~yaml
spring:
  profiles:
    group:
      production:
        - prod-database
        - prod-security
        - observability
~~~

Khi kích hoạt:

~~~bash
java -jar store.jar --spring.profiles.active=production
~~~

Spring Boot có thể mở rộng nhóm để các profile `prod-database`, `prod-security` và `observability` cùng hoạt động.

### Vì sao group hữu ích?

Nếu một môi trường cần bật ba profile, người vận hành không phải nhớ lệnh dài:

~~~bash
java -jar store.jar --spring.profiles.active=prod-database,prod-security,observability
~~~

Chỉ cần:

~~~bash
java -jar store.jar --spring.profiles.active=production
~~~

Group giúp mô tả cấu hình triển khai có ý nghĩa hơn.

### Group không phải cơ chế phân quyền

Đặt tên `prod-security` không tự bật các biện pháp bảo mật nếu các bean và property tương ứng chưa được định nghĩa. Profile group là cơ chế kích hoạt nhóm profile, không phải công cụ quản lý policy hay secret.

### Đặt profile group ở document chung

Không đặt định nghĩa group trong file `application-production.yml` vì như vậy phụ thuộc vào một document chỉ được dùng khi profile đã được kích hoạt. Hãy định nghĩa group trong cấu hình không phụ thuộc profile.

## 20. SpringApplication.setAdditionalProfiles trong Java

Ngoài properties, có thể bổ sung profile bằng code trước khi gọi `run`:

~~~java
@SpringBootApplication
public class StoreApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(StoreApplication.class);

        app.setAdditionalProfiles("observability");
        app.run(args);
    }
}
~~~

`setAdditionalProfiles` bổ sung profile cho quá trình chạy ứng dụng. Nó hữu ích khi một thư viện hoặc launcher cần thêm một nhóm cấu hình.

Tuy nhiên, với ứng dụng triển khai thông thường, nên để môi trường chạy quyết định `dev` hay `prod`. Hard-code active profile trong source làm cùng một JAR khó được dùng nhất quán ở nhiều môi trường.

### SpringApplicationBuilder

~~~java
new SpringApplicationBuilder(StoreApplication.class)
        .profiles("dev")
        .run(args);
~~~

`SpringApplicationBuilder` cho phép cấu hình dạng fluent trước khi run. Đây là một lựa chọn khi ứng dụng cần kiểm soát launcher hoặc xây dựng context hierarchy.

### Không thay profile sau khi context refresh rồi mong bean tự đổi

Nếu context đã tạo bean theo `dev`, việc gọi thay đổi active profile trong `Environment` sau đó không tự:

- Xóa bean dev đã được tạo.
- Tạo bean prod còn thiếu.
- Nạp lại toàn bộ `application-prod.yml`.
- Re-evaluate toàn bộ `@Profile` và `@Conditional`.

Profile chủ yếu là **quyết định cấu hình trong giai đoạn bootstrap/bean registration**. Muốn thay đổi khi đang chạy cần kiến trúc riêng, không chỉ sửa mảng active profile.

## 21. Dùng Environment để quan sát profile hiệu lực

Có thể inject `Environment`:

~~~java
@Component
public class ProfileReporter implements ApplicationRunner {

    private final Environment environment;

    public ProfileReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Active: " +
                Arrays.toString(environment.getActiveProfiles())
        );

        System.out.println(
                "Default: " +
                Arrays.toString(environment.getDefaultProfiles())
        );
    }
}
~~~

Cần import các class Java và Spring tương ứng như `java.util.Arrays`, `Environment`, `ApplicationRunner` và `Component`.

Đầu ra điển hình khi không bật profile và default là local:

~~~text
Active: []
Default: [local]
~~~

Khi bật prod:

~~~text
Active: [prod]
Default: [local]
~~~

Dữ liệu này làm rõ vì sao `getDefaultProfiles()` vẫn có giá trị nhưng default không được dùng để match khi active profiles đang tồn tại.

### Kiểm tra một profile có match không

Spring có API `Profiles`:

~~~java
boolean production =
        environment.acceptsProfiles(
                Profiles.of("prod")
        );
~~~

Hoặc một biểu thức:

~~~java
boolean nonProduction =
        environment.acceptsProfiles(
                Profiles.of("!prod")
        );
~~~

`acceptsProfiles(Profiles.of(...))` là API phù hợp với Spring Framework hiện đại. Nó kiểm tra profile expression theo Environment hiện tại, bao gồm semantics default profile nếu không có active profile.

Tuy nhiên, không nên rải `environment.acceptsProfiles(...)` vào mọi method nghiệp vụ. Nếu đang quyết định nên đăng ký bean nào, hãy ưu tiên `@Profile` ở tầng configuration.

## 22. Profile và @ConditionalOnProperty khác nhau thế nào?

Đôi khi một lựa chọn phụ thuộc môi trường triển khai; đôi khi nó chỉ là một tính năng có thể bật/tắt.

Ví dụ lựa chọn database adapter theo môi trường:

~~~java
@Bean
@Profile("dev")
PaymentGateway fakePaymentGateway() {
    return new FakePaymentGateway();
}

@Bean
@Profile("prod")
PaymentGateway livePaymentGateway() {
    return new LivePaymentGateway();
}
~~~

Ví dụ bật một tính năng độc lập:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
)
AuditPublisher auditPublisher() {
    return new AuditPublisher();
}
~~~

| Tiêu chí | `@Profile` | `@ConditionalOnProperty` |
|---|---|---|
| Câu hỏi | Môi trường/nhóm profile nào đang phù hợp? | Property cụ thể có giá trị phù hợp không? |
| Dữ liệu đầu vào | Active/default profiles | Environment property |
| Ví dụ | `prod`, `dev`, `observability` | `app.audit.enabled=true` |
| Phù hợp với | Cụm cấu hình theo bối cảnh | Feature option độc lập |
| Rủi ro khi lạm dụng | Quá nhiều profile kết hợp khó dự đoán | Quá nhiều flag phụ thuộc nhau |

Một quy tắc thực dụng: dùng profile cho **bối cảnh hoặc tổ hợp cấu hình**, dùng typed properties/condition cho **tùy chọn độc lập**.

## 23. Profile không thay thế cơ chế bảo vệ production

Một sai lầm nguy hiểm là coi profile như boundary bảo mật:

~~~java
@Profile("prod")
public class RealPaymentGateway {
}
~~~

Việc chỉ dùng `@Profile("prod")` không bảo đảm mọi đường truy cập production đều được chặn trong môi trường khác. Nếu config source bị chọn nhầm hoặc có bean thay thế, ứng dụng vẫn có thể kết nối endpoint thật.

Những biện pháp cần thiết gồm:

- Credential production chỉ được cấp trong môi trường thích hợp.
- Network policy giới hạn truy cập dịch vụ production.
- Validation cấu hình lúc startup.
- Không đặt secret trong source/YAML được commit.
- Tách endpoint giả và thật rõ ràng.
- Kiểm thử tình huống thiếu profile hoặc active profile sai.

Profile là **cơ chế cấu hình**, không phải một lớp bảo mật độc lập.

## 24. Kích hoạt profile trong test bằng @ActiveProfiles

Spring Test hỗ trợ `@ActiveProfiles` để chọn profile cho test context.

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentServiceIntegrationTest {

    @Autowired
    PaymentGateway paymentGateway;

    @Test
    void usesTestGateway() {
        assertThat(paymentGateway)
                .isInstanceOf(FakePaymentGateway.class);
    }
}
~~~

Ví dụ giả định có bean `FakePaymentGateway` phù hợp khi profile `test` active và dependency assertion đã được thêm vào dự án.

### @ActiveProfiles khác cấu hình runtime

`@ActiveProfiles` là annotation của Spring Test để chuẩn bị test ApplicationContext. Nó không phải cơ chế nên dùng để quyết định active profile cho ứng dụng production.

Nếu test không khai báo profile, kết quả còn phụ thuộc cấu hình, test environment và default profile; không nên mặc định mọi test đều dùng `test`.

### Dùng profile-specific properties cho test

`application-test.yml`:

~~~yaml
app:
  payment:
    endpoint: http://localhost:9999
  audit:
    enabled: false
~~~

Test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentIntegrationTest {
}
~~~

Spring Boot có thể nạp `application-test.yml` tương ứng với active profile test.

### Test với nhiều profile

~~~java
@SpringBootTest
@ActiveProfiles({"test", "observability"})
class ObservabilityIntegrationTest {
}
~~~

Nếu hai profile cùng đăng ký bean trùng kiểu, test có thể lỗi tương tự production. Nên kiểm soát xung đột thay vì cho rằng test annotation xử lý mọi ambiguity.

## 25. Kiểm thử default profile

Để kiểm tra fallback, cần một context mà danh sách active profiles không được bật. Ví dụ đơn giản về cấu hình bean:

~~~java
@Configuration
public class FallbackConfiguration {

    @Bean
    @Profile("default")
    String fallbackMessage() {
        return "default-message";
    }

    @Bean
    @Profile("prod")
    String productionMessage() {
        return "production-message";
    }
}
~~~

Trong một test dùng `AnnotationConfigApplicationContext`:

~~~java
@Test
void usesDefaultProfileWhenNoActiveProfileExists() {
    try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(
                         FallbackConfiguration.class
                 )) {

        assertEquals(
                "default-message",
                context.getBean(String.class)
        );
    }
}
~~~

Vì context không kích hoạt profile nào và Spring default là `default`, bean fallback có thể được chọn.

Test với active prod:

~~~java
@Test
void usesProductionProfile() {
    try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

        context.getEnvironment().setActiveProfiles("prod");
        context.register(FallbackConfiguration.class);
        context.refresh();

        assertEquals(
                "production-message",
                context.getBean(String.class)
        );
    }
}
~~~

Ở đây, `setActiveProfiles` được gọi **trước `refresh()`**. Nếu gọi sau khi bean definitions đã được xử lý, không nên mong bean được chọn lại.

### Test khi default profile đổi tên

~~~java
@Test
void usesLocalAsConfiguredDefault() {
    try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext()) {

        context.getEnvironment().setDefaultProfiles("local");
        context.register(LocalOnlyConfiguration.class);
        context.refresh();

        assertNotNull(context.getBean(LocalService.class));
    }
}
~~~

Test giả định `LocalOnlyConfiguration` đăng ký `LocalService` bằng `@Profile("local")`. Đây là kiểm thử Spring Framework thuần cho semantics của default profile.

## 26. Lỗi thường gặp: đặt active trong application-prod.yml

Một lỗi dễ mắc là nghĩ “nếu đang vào file prod thì tôi sẽ bật thêm profile metrics tại đó”:

~~~yaml
# application-prod.yml
spring:
  profiles:
    active: metrics
~~~

Cơ chế Config Data hiện đại không cho phép `spring.profiles.active` trong file profile-specific.

**Cách sửa:** chọn profile ở một non-profile-specific document hoặc nguồn bootstrap như command line. Nếu cần profile `prod` bật thêm một nhóm profile khác, khai báo profile group trong document chung:

~~~yaml
spring:
  profiles:
    group:
      prod:
        - observability
        - prod-security
~~~

Sau đó kích hoạt `prod` bằng command line hoặc environment variable.

## 27. Lỗi thường gặp: default profile bị hiểu là active profile

Giả sử:

~~~yaml
spring:
  profiles:
    default: local
~~~

Khi không có active profile, người viết code có thể kiểm tra:

~~~java
boolean hasLocal =
        Arrays.asList(environment.getActiveProfiles())
                .contains("local");
~~~

và nhận `false`.

Điều này không trái với việc `@Profile("local")` vẫn có thể match. Vì `getActiveProfiles()` vẫn trả danh sách active thật, không tự chèn default fallback.

Nếu muốn kiểm tra semantics match profile, dùng:

~~~java
boolean localMatches =
        environment.acceptsProfiles(
                Profiles.of("local")
        );
~~~

Nếu muốn hiển thị **active thực tế và default đã cấu hình**, đọc cả `getActiveProfiles()` và `getDefaultProfiles()`.

## 28. Lỗi thường gặp: profile-specific file không được nạp

Triệu chứng: đã chạy:

~~~bash
java -jar store.jar --spring.profiles.active=prod
~~~

nhưng một property trong `application-prod.yml` không có giá trị mong đợi.

Các nguyên nhân thường gặp:

1. File không nằm trong location mà Config Data loader tìm.
2. Tên file sai, ví dụ `applications-prod.yml`.
3. File dùng phần mở rộng hoặc định dạng không phù hợp.
4. Property bị nguồn có precedence cao hơn ghi đè.
5. Một document YAML khác có điều kiện `on-profile` không match.
6. `spring.config.location` đã thay thế các location mặc định.
7. Config import thay đổi nguồn và thứ tự ưu tiên.
8. Ứng dụng thực sự không có profile `prod` active.
9. Property name khác key mà code bind/đọc.

Hướng xử lý là đọc log startup, active/default profile thực tế và property sources đang được áp dụng.

### Đừng chỉ kiểm tra file trong source

Ứng dụng chạy từ JAR hoặc container image. File trong repository có thể khác file được đóng gói, còn cấu hình ngoài có thể ghi đè. Hãy kiểm tra artifact và môi trường chạy thực tế khi chẩn đoán.

## 29. Lỗi thường gặp: @Profile không có tác dụng

Ví dụ:

~~~java
@Service
@Profile("prod")
public class RealPaymentGateway implements PaymentGateway {
}
~~~

Nhưng ứng dụng không tạo bean này dù prod active.

Các nguyên nhân:

- Class nằm ngoài vùng component scanning.
- Configuration class không được import.
- Có condition khác không match.
- Bean được tạo thủ công bằng `new` nên Spring không quản lý.
- Dự án chạy một ApplicationContext khác với context đang kiểm tra.
- Active profile thực tế bị nguồn cấu hình khác ghi đè.

Không có nghĩa annotation `@Profile` bị “bỏ qua” chỉ vì Spring không thấy class. Cần kiểm tra toàn bộ quá trình bean registration.

### Hai bean cùng tên ở hai profile

Nếu profile khác nhau cùng đăng ký bean có cùng tên mà hai profile cùng được kích hoạt, có thể xảy ra xung đột bean definition theo chính sách override của ứng dụng. Nếu dùng tên khác nhưng cùng kiểu, có thể xảy ra ambiguity khi inject.

Nên chọn profile kết hợp hợp lệ, đặt tên bean ổn định và sử dụng `@Qualifier` hoặc các configuration class rõ ràng khi cần.

## 30. Lỗi thường gặp: đổi Environment sau khi startup

Ví dụ:

~~~java
environment.setActiveProfiles("prod");
~~~

Nếu lời gọi xảy ra sau khi ApplicationContext đã refresh, không nên kỳ vọng các bean dev tự biến mất và bean prod tự xuất hiện. Spring đã đánh giá `@Profile` và dựng object graph từ trước.

Nếu ứng dụng thật sự cần chuyển endpoint hoặc behavior lúc runtime, cân nhắc:

- Một strategy bean được cấu hình bằng properties có thể refresh theo cơ chế rõ ràng.
- Factory/resolver chọn implementation theo yêu cầu có chủ đích.
- Cấu hình được refresh theo framework hỗ trợ, với lifecycle đã được thiết kế.
- Triển khai lại/restart ứng dụng khi thay bối cảnh môi trường.

Không biến profile thành feature toggle động nếu kiến trúc không hỗ trợ refresh.

## 31. Chẩn đoán profile qua log và Actuator

Khi khởi động, Spring Boot thường ghi log về active profiles hoặc default fallback. Một thông báo điển hình khi không có active profile là Spring đang dùng một default profile, ví dụ `default`.

Có thể tự log an toàn:

~~~java
@Component
public class ProfileLogger implements ApplicationRunner {

    private static final Logger log =
            LoggerFactory.getLogger(ProfileLogger.class);

    private final Environment environment;

    public ProfileLogger(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        log.info(
                "Active profiles: {}",
                Arrays.toString(environment.getActiveProfiles())
        );

        log.info(
                "Default profiles: {}",
                Arrays.toString(environment.getDefaultProfiles())
        );
    }
}
~~~

Chỉ log tên profile là phù hợp cho nhiều trường hợp. Không nên log toàn bộ Environment vì property sources có thể chứa password, token hoặc secret.

Nếu ứng dụng có Spring Boot Actuator và endpoint quản trị được bảo vệ, endpoint `env` có thể giúp quan sát property sources; endpoint `conditions` giúp tìm hiểu vì sao một auto-configuration match hoặc không match. Việc expose endpoint cần kiểm soát bảo mật, tránh công khai cấu hình nội bộ.

### Property source nào quyết định active profile?

Câu hỏi cần trả lời là: **Nguồn cấu hình nào có precedence cao nhất đang cung cấp `spring.profiles.active` hoặc `spring.profiles.default`?**

Đừng chỉ nhìn:

~~~yaml
spring:
  profiles:
    active: dev
~~~

trong repository rồi khẳng định ứng dụng chạy dev. Một biến môi trường, command line hoặc config import có thể làm giá trị hiệu lực khác đi.

## 32. Ví dụ end-to-end: cùng JAR chạy local và production

Một ứng dụng thanh toán có các file:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
└── application-prod.yml
~~~

Cấu hình chung:

~~~yaml
spring:
  application:
    name: checkout-service
  profiles:
    default: local

app:
  payment:
    timeout: 3s
~~~

Cấu hình local:

~~~yaml
app:
  payment:
    mode: simulation
    endpoint: http://localhost:9090
~~~

Cấu hình production:

~~~yaml
app:
  payment:
    mode: live
    endpoint: https://payments.example.internal
    timeout: 8s
~~~

Typed configuration:

~~~java
@ConfigurationProperties(prefix = "app.payment")
public class PaymentProperties {

    private String mode;
    private URI endpoint;
    private Duration timeout = Duration.ofSeconds(3);

    public String getMode() {
        return mode;
    }

    public void setMode(String mode) {
        this.mode = mode;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
~~~

Đăng ký `PaymentProperties` qua `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties(PaymentProperties.class)` theo cấu trúc ứng dụng.

Service:

~~~java
@Service
public class PaymentService {

    private final PaymentProperties properties;

    public PaymentService(PaymentProperties properties) {
        this.properties = properties;
    }

    public URI targetEndpoint() {
        return properties.getEndpoint();
    }
}
~~~

### Chạy local không truyền active profile

~~~bash
java -jar checkout-service.jar
~~~

Vì không có active profile, default `local` có hiệu lực và `application-local.yml` được nạp theo quy tắc Config Data.

### Chạy production

~~~bash
java -jar checkout-service.jar --spring.profiles.active=prod
~~~

Vì `prod` đã active, fallback `local` không được dùng. `application-prod.yml` cung cấp endpoint và timeout phù hợp.

### Nếu quên active profile khi triển khai?

Ứng dụng có thể chạy local fallback, dẫn đến endpoint không mong muốn. Nếu đây là rủi ro lớn, production deployment cần kiểm tra biến môi trường bắt buộc, validation config và chính sách fail-fast thay vì chỉ tin vào default profile.

Một cách khác là không đặt default profile là local trong artifact production và yêu cầu cấu hình rõ ràng. Chọn chính sách tùy yêu cầu triển khai.

## 33. Trường hợp không nên dùng nhiều profile

Profile hữu ích nhưng không nên trở thành hệ thống tổ hợp tùy chọn không kiểm soát. Ví dụ:

~~~text
prod,cloud,redis,metrics,secure,fast-cache,async-mail,
feature-x,feature-y,feature-z,...
~~~

Khi quá nhiều profile điều khiển những lựa chọn nhỏ, số tổ hợp cần kiểm thử tăng nhanh, và các bean condition có thể chồng chéo khó hiểu.

Thay vào đó:

- Dùng profile để chọn **bối cảnh chạy chính** hoặc một nhóm cấu hình lớn.
- Dùng `@ConfigurationProperties` để ràng buộc giá trị và validation.
- Dùng `@ConditionalOnProperty` cho feature/capability độc lập.
- Dùng profile groups cho những tổ hợp thường dùng và được quản lý.
- Dùng runtime feature flag system nếu tính năng cần thay đổi không restart.

Cách phân chia này giúp code rõ ràng hơn và giảm lỗi “chỉ xảy ra với một tổ hợp profile đặc biệt”.

## 34. Bảng xử lý sự cố nhanh

| Triệu chứng | Kiểm tra trước |
|---|---|
| Không bật profile nhưng `@Profile("default")` chạy | Đó là fallback mặc định của Spring |
| Không bật profile nhưng `@Profile("local")` chạy | `spring.profiles.default` có thể là `local` |
| Có active prod nhưng bean default không chạy | Default không cộng thêm vào active profiles |
| Active profile khác YAML | Command line, environment, system property hoặc nguồn precedence cao hơn |
| `getActiveProfiles()` trả rỗng dù config local áp dụng | Local có thể là default profile, không phải active |
| `application-prod.yml` không nạp | Location, tên file, active profile hoặc Config Data precedence |
| `@Profile("prod")` không tạo bean | Package scan, import hoặc condition khác |
| Hai implementation cùng được đăng ký | Nhiều profile active hoặc bean không có condition |
| Boot báo profile property invalid | `spring.profiles.active/default/include/group` nằm sai document |
| Thay active profile runtime nhưng bean không đổi | Context đã parse configuration và tạo bean |
| Test dùng nhầm production config | Kiểm tra `@ActiveProfiles` và test property sources |
| Một profile có nhiều cấu hình khác nhau | Xác định property nguồn nào thắng và thứ tự document/import |

## 35. Checklist cấu hình profile cho dự án

1. **Xác định tên profile có ý nghĩa.** Ví dụ `local`, `test`, `staging`, `prod`.
2. **Quyết định chính sách khi không có active profile.** Dùng `default`, đổi thành `local`, dùng `none` hoặc fail fast.
3. **Đặt cấu hình chung ở `application.yml`.** Tránh sao chép các property không thay đổi giữa môi trường.
4. **Đặt khác biệt vào `application-{profile}.yml` hoặc on-profile documents.**
5. **Không đặt `spring.profiles.active/default` trong file profile-specific.**
6. **Không đặt `spring.profiles.include/group` trong document kích hoạt theo profile.**
7. **Ưu tiên chọn production profile từ deployment**, không hard-code trong source.
8. **Kiểm tra khả năng nhiều profile active đồng thời.** Tránh bean trùng kiểu/tên và property override khó hiểu.
9. **Dùng `@Profile` ở tầng configuration.** Không kiểm tra environment name rải rác trong business logic.
10. **Không coi profile là boundary bảo mật.** Credential, network policy và validation vẫn cần thiết.
11. **Viết test cho profile chính và fallback.** Đặc biệt test thiếu active profile.
12. **Quan sát active và default profiles trong startup log.** Không in secret.
13. **Xác nhận property source precedence.** Một file YAML không đại diện toàn bộ runtime configuration.
14. **Không đổi profile sau startup rồi mong object graph tự cập nhật.**
15. **Tài liệu hóa profile groups và quy tắc triển khai** để các thành viên dùng cùng cấu hình.

## Kết luận

`spring.profiles.active` chọn những profile được kích hoạt khi Spring Boot khởi động. Nếu danh sách active profile rỗng, Spring dùng **default profile**; tên mặc định thường là `default` và có thể đổi qua `spring.profiles.default`. Default profile không tự động cộng vào danh sách active profiles, và `getActiveProfiles()` vẫn có thể rỗng khi cấu hình fallback đang áp dụng.

Profile chi phối cả việc nạp Config Data như `application-prod.yml` lẫn việc đăng ký bean có `@Profile`. Active profile có thể được chọn qua file cấu hình chung, command line, JVM system property, biến môi trường hoặc API khởi động. Khi nhiều nguồn cùng khai báo, **property source precedence** quyết định giá trị hiệu lực; khi cần bổ sung profile, hãy dùng `spring.profiles.include`, `spring.profiles.group` hoặc `SpringApplication.setAdditionalProfiles` theo đúng mục đích.

Điểm thực hành quan trọng là đặt những property chọn profile ở **non-profile-specific document**, tránh coi `@Profile("default")` là một fallback bean bất kể môi trường nào, và kiểm tra active/default profiles thực tế thay vì đoán từ một file. Thiết kế rõ ràng những trường hợp không có active profile, production và test sẽ giúp cùng một ứng dụng Spring Boot chạy ổn định qua nhiều môi trường mà không phải thay đổi mã nguồn.
