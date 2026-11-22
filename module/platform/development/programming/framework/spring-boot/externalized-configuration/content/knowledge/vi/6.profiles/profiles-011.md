# Thiết kế profile theo nhu cầu triển khai và tránh tổ hợp khó kiểm soát

Trong Spring Boot, **profile** là cơ chế chọn cấu hình và thành phần phù hợp với một ngữ cảnh chạy. Một ứng dụng có thể cần kết nối đến database local khi phát triển, dùng hạ tầng kiểm thử ở staging và tích hợp với dịch vụ thật ở production. Profile giúp mô tả những khác biệt đó mà không phải sửa mã nguồn cho từng lần triển khai.

Tuy nhiên, profile rất dễ bị lạm dụng. Khi dự án có nhiều chiều độc lập — môi trường, vùng địa lý, nhà cung cấp cloud, tính năng, loại database, mức logging, nhóm khách hàng — nếu tạo một profile cho mỗi tổ hợp, số trường hợp cần hiểu và kiểm thử tăng nhanh. Ngược lại, nếu bật quá nhiều profile đồng thời, cấu hình cuối cùng có thể phụ thuộc vào thứ tự ưu tiên mà nhóm phát triển không còn kiểm soát rõ.

Mục tiêu của bài là thiết kế profile theo **nhu cầu triển khai thực tế**, dùng số lượng nhỏ, có quy ước rõ ràng, và tách những tham số thông thường khỏi quyết định về cấu trúc ứng dụng.

## 1. Profile thực sự quyết định điều gì?

Spring profile có hai tác dụng thường gặp:

1. **Chọn cấu hình** từ file hoặc tài liệu có điều kiện, chẳng hạn `application-dev.yml`, `application-prod.yml` hay tài liệu YAML với `spring.config.activate.on-profile`.
2. **Chọn bean** do Spring container quản lý thông qua `@Profile`, chẳng hạn tạo bộ gửi email giả ở local nhưng sử dụng adapter thật ở môi trường triển khai.

Ví dụ:

~~~yaml
# application.yml — cấu hình chung
app:
  name: "order-service"
  reporting:
    enabled: false
    timeout: 3s

server:
  port: 8080
~~~

~~~yaml
# application-dev.yml — chỉ khác biệt cần thiết cho dev
logging:
  level:
    com.example.orders: DEBUG

app:
  reporting:
    timeout: 1s
~~~

~~~yaml
# application-prod.yml — chỉ khác biệt cho production
app:
  reporting:
    enabled: true
    timeout: 5s
~~~

Khi `dev` được kích hoạt, Spring Boot nạp cấu hình tương ứng với profile đó. Khi `prod` được kích hoạt, cấu hình production được xét theo các quy tắc của Config Data và thứ tự ưu tiên nguồn property.

**Profile không tự tạo ra một bản ứng dụng khác.** Ứng dụng vẫn dùng cùng artifact; điều khác là các nguồn cấu hình và bean có điều kiện. Mục tiêu tốt là duy trì một bản build có thể triển khai nhiều nơi với cấu hình minh bạch.

Profile cũng **không phải nơi lưu trạng thái nghiệp vụ**. Trạng thái đơn hàng, cờ bật tính năng cho từng khách hàng hoặc hạn mức thay đổi theo giao dịch nên có cơ chế nghiệp vụ tương ứng.

## 2. Những câu hỏi cần trả lời trước khi tạo profile

Không nên bắt đầu bằng danh sách tên `dev`, `test`, `stage`, `prod` rồi mặc định mọi hệ thống cần đủ bốn profile. Hãy hỏi trước:

- Ứng dụng được triển khai ở **những ngữ cảnh nào**? Local workstation, CI, môi trường tích hợp, staging, production, hay những ngữ cảnh khác?
- Ở mỗi ngữ cảnh, **điều gì cần thay đổi**? Endpoint, kết nối database, quan sát hệ thống, mức logging, một implementation cụ thể hay chỉ một vài giá trị?
- Khác biệt đó có phải **một thuộc tính của bản triển khai** hay là trạng thái runtime thay đổi theo request hoặc người dùng?
- Sự thay đổi có đòi hỏi **chọn bean khác** hay chỉ cần cùng một bean với giá trị property khác?
- Cấu hình nào **bắt buộc phải có** để môi trường đó hoạt động an toàn?
- Ai sở hữu việc thay đổi: lập trình viên, pipeline triển khai, bộ phận vận hành, hay người sử dụng?

Nếu chỉ cần thay một URL hoặc timeout, thường không cần thêm profile mới. Một nguồn externalized configuration, biến môi trường hoặc giá trị override trong hệ thống triển khai có thể giải quyết tốt hơn.

Nếu cùng một ứng dụng cần hai topology rõ rệt, ví dụ local dùng fake email sender còn production dùng SMTP gateway thật, một profile có thể giúp diễn đạt khác biệt về thành phần.

## 3. Phân biệt ba loại quyết định

Để tránh tạo quá nhiều profile, nên phân loại khác biệt theo ý nghĩa:

| Loại khác biệt | Ví dụ | Cách biểu diễn thường phù hợp |
| --- | --- | --- |
| **Ngữ cảnh triển khai** | local, CI test, staging, production | Một số profile ổn định, có tên rõ |
| **Tham số vận hành** | JDBC URL, timeout, connection pool, log level | Externalized configuration, nguồn bí mật/biến môi trường |
| **Quyết định tính năng/nghiệp vụ** | Bật chức năng theo khách hàng, A/B testing, hạn mức từng gói | Feature flag, policy hoặc dữ liệu nghiệp vụ; không dùng profile cho từng khách hàng |

Có thể có vùng giao nhau. Chẳng hạn `app.mail.enabled=false` là tham số cấu hình; bean gửi email có thể được chọn bằng `@ConditionalOnProperty`. Nếu muốn thay implementation toàn bộ cho local, `@Profile("local")` có thể hợp lý. Điều quan trọng là profile phải phản ánh **một ngữ cảnh chạy ổn định** chứ không phải một tổ hợp bất kỳ của mọi thuộc tính.

Ví dụ thiết kế thường khó quản lý:

~~~text
dev-mysql-debug
dev-postgres-debug
dev-postgres-no-mail
stage-postgres-real-mail
prod-postgres-real-mail
prod-postgres-no-mail
prod-postgres-real-mail-eu
prod-postgres-real-mail-us
...
~~~

Với 4 môi trường × 2 database × 2 trạng thái email × 3 vùng, đã có **48 tổ hợp lý thuyết**, chưa kể observability và retry. Không nên mã hóa tất cả tổ hợp đó thành tên profile.

Một thiết kế gọn hơn:

~~~text
Profile chính: local | test | staging | prod
Property riêng: datasource.url, mail.enabled, region, log level, retry
Bean có điều kiện: chọn adapter khi thực sự cần
Deployment config: cung cấp giá trị cụ thể của mỗi bản triển khai
~~~

## 4. Chọn số lượng profile nhỏ và có ý nghĩa

Một bộ profile ban đầu có thể gồm:

| Profile | Vai trò điển hình | Đặc điểm cần chú ý |
| --- | --- | --- |
| `local` | Chạy trên máy lập trình viên | Endpoint thử nghiệm, tiện ích phát triển, có thể dùng adapter giả |
| `test` | Bối cảnh chạy kiểm thử | Tài nguyên cô lập, dependency ổn định, tránh gọi dịch vụ thật |
| `staging` | Môi trường gần production | Kiểm tra tích hợp và cấu hình triển khai trước khi phát hành |
| `prod` | Production | Dùng dịch vụ thật, observability và chính sách vận hành phù hợp |

Đây là **ví dụ**, không phải bộ profile Spring Boot bắt buộc phải có. Có dự án chỉ cần `local` và `prod`; có dự án tách thêm `integration-test` vì CI thực sự chạy với topology riêng.

Quy ước nên có:

1. **Một profile chính biểu diễn ngữ cảnh triển khai** tại một thời điểm, nếu kiến trúc yêu cầu các môi trường là loại trừ nhau.
2. Tên profile mô tả ngữ cảnh bền vững, không phụ thuộc cá nhân hoặc một phiên bản build cụ thể.
3. Tránh dùng `prod2`, `prod-new`, `dev-john` mà không có nghĩa lâu dài và quy tắc vòng đời.
4. Khác biệt nhỏ chỉ về giá trị nên nằm ở cấu hình; khác biệt thực sự về bean mới cân nhắc `@Profile`.
5. Ghi rõ môi trường nào cần profile nào trong pipeline hoặc manifest triển khai.

Một profile chính như `prod` **không tự xác minh ứng dụng đã an toàn để chạy production**. Secret, validation, quyền truy cập, bảo vệ endpoint và kiểm tra kết nối vẫn cần được thiết kế độc lập.

## 5. Kích hoạt profile bằng cách nào?

Spring Boot hỗ trợ property `spring.profiles.active` để chọn profile hoạt động.

Ví dụ chạy ứng dụng:

~~~bash
java -jar order-service.jar --spring.profiles.active=local
~~~

Hoặc dùng biến môi trường:

~~~bash
SPRING_PROFILES_ACTIVE=prod java -jar order-service.jar
~~~

Ví dụ biến môi trường theo cú pháp shell POSIX; khi dùng Windows PowerShell, Docker, Kubernetes hoặc CI, cách thiết lập biến phụ thuộc vào môi trường.

Một số điểm quan trọng:

- Có thể kích hoạt nhiều profile bằng danh sách phân tách dấu phẩy, ví dụ `--spring.profiles.active=staging,metrics`. Nhưng chỉ nên làm vậy khi thứ tự và mục đích từng profile đã được quy định.
- Property `spring.profiles.active` cũng chịu **thứ tự ưu tiên nguồn cấu hình**. Ví dụ tham số command line có thể ghi đè giá trị tương ứng ở file cấu hình trong cấu hình mặc định của Spring Boot.
- Khi **không có active profile** được chỉ định, Spring dùng profile mặc định có tên `default`, trừ khi cấu hình mặc định đã được thay đổi.
- `spring.profiles.default` cho phép chỉ định tập profile mặc định; nếu cần vô hiệu default profile theo cách được Spring Boot hỗ trợ, có thể cấu hình giá trị `none`.
- Đừng mặc định profile `prod` trong `application.yml` chỉ để khỏi khai báo ở production. Môi trường chạy nên **chủ động khai báo** lựa chọn production; nếu sai deploy target, điều kiện này cần được phát hiện rõ.

Ví dụ policy deployment:

~~~text
Chạy local     -> SPRING_PROFILES_ACTIVE=local
CI integration -> SPRING_PROFILES_ACTIVE=test
Staging        -> SPRING_PROFILES_ACTIVE=staging
Production     -> SPRING_PROFILES_ACTIVE=prod
~~~

Đây là hợp đồng giữa ứng dụng và pipeline, giúp giảm trường hợp ứng dụng chạy trong môi trường không mong muốn.

## 6. Tổ chức file cấu hình theo nguyên tắc chung trước, khác biệt sau

Một cấu trúc dễ đọc:

~~~text
src/main/resources/
  application.yml
  application-local.yml
  application-test.yml
  application-staging.yml
  application-prod.yml
~~~

**`application.yml` nên chứa giá trị chung** không phụ thuộc môi trường, chẳng hạn tên dịch vụ, timeout mặc định hợp lý, quy tắc retry chung hoặc một số flag có mặc định an toàn.

**File theo profile nên chỉ chứa phần thực sự khác biệt.** Tránh copy toàn bộ `application.yml` sang bốn file rồi sửa vài dòng, vì sau một thời gian chúng sẽ trôi khỏi nhau và khó nhận ra giá trị nào thật sự có tác dụng.

Ví dụ file chung:

~~~yaml
# application.yml
app:
  checkout:
    retry-count: 2
    timeout: 3s
  mail:
    enabled: false

management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

File local:

~~~yaml
# application-local.yml
logging:
  level:
    com.example.checkout: DEBUG

app:
  checkout:
    timeout: 1s
~~~

File staging:

~~~yaml
# application-staging.yml
app:
  checkout:
    timeout: 4s
~~~

File production:

~~~yaml
# application-prod.yml
app:
  checkout:
    timeout: 5s
~~~

Trong dự án thực tế, database URL, credentials, API key và endpoint nhạy cảm nên đến từ nguồn cấu hình của deployment hoặc secrets manager. Các file được commit có thể chứa **key, mặc định an toàn và ví dụ**, nhưng không chứa secret thật.

### Tránh tạo file cho mỗi kết hợp nhỏ

Không cần có `application-prod-eu-postgres-mail.yml` nếu mục đích chỉ là đổi `region`, `datasource.url` và `mail.enabled`. Hãy cấp các giá trị đó từ deployment, còn profile `prod` thể hiện ngữ cảnh production chung.

## 7. Dùng tài liệu YAML có điều kiện với on-profile

Ngoài file `application-<profile>.yml`, Spring Boot có thể dùng nhiều tài liệu trong một file YAML, phân cách bằng `---` và điều kiện `spring.config.activate.on-profile`.

~~~yaml
app:
  pricing:
    timeout: 3s

---
spring:
  config:
    activate:
      on-profile: "local"

app:
  pricing:
    timeout: 1s

---
spring:
  config:
    activate:
      on-profile: "prod"

app:
  pricing:
    timeout: 5s
~~~

Tài liệu chung có hiệu lực theo quy tắc nạp cấu hình; tài liệu có `on-profile: "local"` chỉ được kích hoạt khi profile expression khớp với tập active profiles.

Có thể dùng biểu thức profile:

~~~yaml
spring:
  config:
    activate:
      on-profile: "staging | prod"
~~~

Biểu thức `staging | prod` thể hiện điều kiện OR. Spring hỗ trợ cú pháp biểu thức profile phù hợp, bao gồm `&`, `|` và `!` trong các ngữ cảnh có hỗ trợ. Đặt dấu nháy để YAML giữ nguyên giá trị biểu thức và để người đọc thấy đây là một chuỗi điều kiện.

Cân nhắc giữa hai cách tổ chức:

- **File riêng theo profile**: dễ xem khác biệt từng môi trường; phù hợp khi cấu hình theo môi trường dài.
- **Một YAML nhiều tài liệu**: tiện khi mỗi profile chỉ có vài dòng khác biệt và muốn nhìn gần nhau.

Không nên dùng cả hai kiểu một cách tùy hứng khiến một key được khai báo rải rác, khó truy vết nguồn cuối cùng.

## 8. @Profile chỉ nên chọn thành phần khi topology thật sự khác

Spring `@Profile` cho phép giới hạn đăng ký một bean hoặc configuration class khi profile được kích hoạt.

Ví dụ một giao diện gửi thông báo:

~~~java
public interface NotificationSender {
    void send(String address, String message);
}
~~~

Ở local, chỉ ghi log để tránh gửi email thật:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("local")
class LoggingNotificationSender implements NotificationSender {

    @Override
    public void send(String address, String message) {
        // Demo: ghi nhận yêu cầu gửi, không gửi ra hệ thống thật.
    }
}
~~~

Ở staging và production, ứng dụng dùng adapter SMTP:

~~~java
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("staging | prod")
class SmtpNotificationSender implements NotificationSender {

    private final MailGateway gateway;

    SmtpNotificationSender(MailGateway gateway) {
        this.gateway = gateway;
    }

    @Override
    public void send(String address, String message) {
        gateway.send(address, message);
    }
}
~~~

`MailGateway` ở đây là abstraction của tầng tích hợp; cần có implementation và cấu hình tương ứng. Ví dụ chỉ minh họa điều kiện chọn bean.

Nếu chỉ đơn giản là **cùng một SMTP client nhưng URL khác giữa staging và prod**, thường không cần hai lớp `@Profile`; dùng một bean và cấp URL từ externalized configuration.

Chú ý:

- Hai implementation cùng được đăng ký có thể gây ambiguity khi inject theo interface nếu không có qualifier, primary hoặc lựa chọn khác.
- Không có implementation nào được đăng ký có thể gây lỗi thiếu bean ở startup nếu service phụ thuộc bắt buộc.
- `@Profile("!prod")` không đồng nghĩa “chỉ local”, vì nó cũng khớp `test`, `staging` và bất kỳ ngữ cảnh nào không kích hoạt prod. Khi muốn phạm vi hẹp, dùng tên rõ như `@Profile("local")`.
- Nếu muốn bật/tắt một thành phần dựa trên property có ý nghĩa riêng, `@ConditionalOnProperty` thường diễn đạt đúng hơn một profile mới.

## 9. Profile group giúp gom cấu hình ổn định, nhưng không thay cho thiết kế

Spring Boot hỗ trợ **profile groups** để kích hoạt một tập profile liên quan bằng một tên nhóm.

Ví dụ khai báo trong tài liệu cấu hình chung không phụ thuộc profile:

~~~yaml
spring:
  profiles:
    group:
      local:
        - "local-db"
        - "local-diagnostics"
      prod:
        - "prod-db"
        - "prod-observability"
~~~

Khi kích hoạt `local`, nhóm làm các member tương ứng được kích hoạt cùng. Khi kích hoạt `prod`, các profile thành viên được kích hoạt theo quy tắc profile group.

Có thể tổ chức các file phụ trợ:

~~~text
application.yml
application-local.yml
application-local-db.yml
application-local-diagnostics.yml
application-prod.yml
application-prod-db.yml
application-prod-observability.yml
~~~

Profile group phù hợp khi các thành phần được gộp là **một gói cấu hình ổn định** luôn đi cùng nhau trong một kiểu triển khai. Ví dụ ở local, database in-memory hoặc local container luôn gắn với công cụ diagnostic của local.

Tuy nhiên, nhóm không phải cách biến mọi chiều lựa chọn độc lập thành profile:

~~~text
region-eu, region-us, use-postgres, use-mysql,
enable-reporting, disable-reporting, debug, verbose-http ...
~~~

Khi kết hợp tùy ý các profile kiểu này, vẫn nảy sinh rất nhiều tổ hợp khó kiểm soát. Hãy dùng **property** cho giá trị lựa chọn thông thường và group cho gói topology có ý nghĩa ổn định.

**Quy tắc khai báo:** `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include` và `spring.profiles.group` phải được khai báo ở tài liệu không đặc thù profile, không đặt trong `application-prod.yml` hoặc tài liệu có `spring.config.activate.on-profile`. Cấu hình các property điều khiển profile ở tài liệu bị ràng buộc bởi profile có thể bị Spring Boot từ chối.

## 10. Thận trọng với nhiều active profiles và thứ tự ghi đè

Spring Boot cho phép nhiều profile cùng hoạt động:

~~~bash
java -jar order-service.jar --spring.profiles.active=staging,observability
~~~

Điều này có thể hữu ích nếu hai profile được thiết kế để phối hợp. Nhưng nếu cùng một key được định nghĩa ở nhiều nguồn:

~~~yaml
# application-staging.yml
app:
  client:
    timeout: 2s
~~~

~~~yaml
# application-observability.yml
app:
  client:
    timeout: 10s
~~~

thì giá trị cuối cùng phụ thuộc thứ tự nạp và độ ưu tiên nguồn cấu hình. Với nhiều file theo profile cùng mức, Spring Boot áp dụng chiến lược **profile sau thắng** đối với các giá trị xung đột theo quy tắc Config Data. Tuy nhiên, nguồn có ưu tiên cao hơn như tham số dòng lệnh còn có thể ghi đè kết quả.

Đây là dấu hiệu thiết kế không tốt: một profile về observability lại thay timeout nghiệp vụ của client.

Quy ước nên áp dụng:

1. Mỗi profile phụ trợ có **phạm vi property rõ ràng**.
2. Tránh để hai profile đồng thời được kích hoạt cùng định nghĩa một key nếu không có lý do cụ thể.
3. Không xem thứ tự profile là một cơ chế điều phối nghiệp vụ.
4. Với các key quan trọng, xác nhận giá trị cuối cùng ở cấu hình triển khai thực tế.
5. Khi có xung đột, hãy làm rõ nguồn sở hữu key thay vì dựa vào “cứ đảo thứ tự là chạy”.

Đặc biệt tránh `dev,prod` hoặc `staging,prod` được kích hoạt đồng thời chỉ để lấy một vài property còn thiếu: điều đó làm mờ biên giới môi trường, có nguy cơ trộn endpoint, secret hoặc bean khác nhau.

## 11. spring.profiles.include và nhóm cấu hình

Ngoài danh sách active profiles, Spring Boot có `spring.profiles.include` để bổ sung profile khi cấu hình được xử lý.

Ví dụ:

~~~yaml
spring:
  profiles:
    include:
      - "common-observability"
~~~

Cần chú ý:

- `include` bổ sung profile, không được hiểu đơn giản như thay thế `spring.profiles.active`.
- Việc kích hoạt thêm profile có thể kéo theo file cấu hình và bean có điều kiện tương ứng.
- `include` không nên được đặt trong tài liệu cấu hình đặc thù profile hoặc tài liệu có `on-profile`.
- Nếu một nhóm profile chỉ cần luôn đi cùng **một tên môi trường cụ thể**, `spring.profiles.group.<name>` thường diễn đạt ý định tốt hơn `include` toàn cục.
- Dù dùng include hay group, hãy giữ tập profile nhỏ và tài liệu hóa chúng.

Có thể chọn một trong ba cách:

| Nhu cầu | Giải pháp |
| --- | --- |
| Chọn một ngữ cảnh triển khai | Active profile chính, ví dụ `prod` |
| Một tên triển khai luôn kéo theo vài profile phụ trợ | Profile group |
| Một thành phần luôn bổ sung vào active profile theo yêu cầu cấu hình chung | `spring.profiles.include`, dùng có cân nhắc |

Nhiều dự án không cần dùng cả group và include. Nếu các file profile phụ trợ không giúp đơn giản hóa, giữ cấu hình trong file chung và file theo môi trường sẽ dễ bảo trì hơn.

## 12. Tách cấu hình theo vùng địa lý, tenant và tính năng

Một ví dụ kinh điển tạo tổ hợp khó quản lý là **môi trường × vùng địa lý × khách hàng × feature flag**.

Giả sử hệ thống chạy:

- 4 môi trường: local, test, staging, prod.
- 3 vùng: APAC, EU, US.
- 2 nhà cung cấp database.
- 3 trạng thái của một tính năng.

Nếu mã hóa mọi tổ hợp thành tên profile, có tới **72 kết hợp lý thuyết**. Khi thêm một chiều lựa chọn nữa, con số tiếp tục nhân lên. Không nên tạo 72 file `application-...yml` để thể hiện chúng.

Thay vào đó:

~~~yaml
app:
  deployment:
    region: "apac"
  feature:
    invoice-export-enabled: false
~~~

Trong thực tế, pipeline có thể cấp `APP_DEPLOYMENT_REGION` và `APP_FEATURE_INVOICE_EXPORT_ENABLED` hoặc một nguồn cấu hình phù hợp theo môi trường. Database provider và URL có thể được cấu hình theo deployment, trong khi profile chính vẫn là `prod`.

**Region** có thể ảnh hưởng data residency hoặc endpoint, vì vậy nó cần được kiểm soát nghiêm túc, nhưng không nhất thiết phải trở thành tên profile. Một thuộc tính quan trọng không mặc nhiên phải là profile.

**Tenant/customer** thường là dữ liệu ứng dụng hoặc chính sách nghiệp vụ thay đổi theo request. Không tạo Spring profile `customer-acme` và `customer-beta` để xử lý từng giao dịch, vì active profile thuộc **ApplicationContext của bản chạy**, không phải trạng thái riêng cho mỗi request.

**Feature flag** cũng cần phân biệt:

- Flag dùng khi khởi động để có hoặc không tạo hẳn một tích hợp: có thể dùng `@ConditionalOnProperty`.
- Flag có thể đổi runtime theo khách hàng hoặc đợt thử nghiệm: dùng dịch vụ feature flag hoặc cơ chế nghiệp vụ phù hợp.
- Profile phù hợp khi bạn muốn nêu rõ môi trường chung cho tất cả request trong bản triển khai.

## 13. Không dùng profile để thay thế secrets management

Ví dụ sai:

~~~yaml
# application-prod.yml
payment:
  api-key: "production-secret-value"
~~~

File ở repository không nên chứa khóa thật, kể cả khi chỉ dùng trong profile production.

Thay vào đó, để cấu hình được cấp từ secret manager, environment hoặc config tree của hạ tầng triển khai. Ví dụ file có thể chỉ định key hoặc placeholder được giải quyết lúc chạy theo cơ chế Spring Boot, còn giá trị thực nằm ngoài source control.

Điều cần thiết kế:

- Ai được quyền đọc/sửa secret.
- Môi trường nào được cấp secret nào.
- Secret nào bắt buộc ở startup.
- Cơ chế rotation và tránh in secret vào log.
- Cách phát hiện cấu hình sai trước khi nhận traffic.

`prod` chỉ là tên profile. Một profile không tự tạo ranh giới bảo mật; bảo mật phải đến từ hạ tầng, permission và cấu hình ứng dụng.

## 14. Đừng biến profile thành cách điều khiển nghiệp vụ

Các yêu cầu sau thường **không** nên dùng profile:

- “Khách hàng VIP có mức chiết khấu khác”.
- “Đơn hàng sau 18 giờ đi quy trình phê duyệt”.
- “Nhóm người dùng thử chức năng mới”.
- “Một tenant có giới hạn 200 request/phút, tenant khác có 100”.
- “Giá thay đổi theo khu vực và ngày hiệu lực”.

Những quyết định này liên quan đến dữ liệu, policy và logic nghiệp vụ. Chúng cần mô hình lưu trữ, quyền cập nhật, audit hoặc feature flag theo phạm vi phù hợp.

Một bean singleton chạy trong ứng dụng có thể phục vụ nhiều tenant. Active profile không đổi theo từng request. Nếu cố dùng profile để biểu diễn mỗi tenant, bạn đang ép cấu hình **khởi động ứng dụng** giải một vấn đề **runtime**.

Có thể dùng một property cấu hình như `billing.policy-source=database` để chọn adapter đọc chính sách; nội dung chính sách của từng khách hàng vẫn thuộc nguồn dữ liệu nghiệp vụ.

## 15. Thiết kế profile cho kiểm thử

Một profile `test` hữu ích nếu test suite cần topology ổn định, chẳng hạn database nhúng hoặc stub external API.

Ví dụ trong Spring Boot test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class CheckoutApplicationTests {

    @Test
    void contextLoads() {
        // Kiểm tra ApplicationContext khởi động trong bối cảnh test.
    }
}
~~~

`@ActiveProfiles("test")` đến từ Spring Test, giúp chọn profile cho context của bài test. Tuy nhiên:

- Một bài unit test thuần không khởi động Spring container thường **không cần profile**.
- Integration test có thể dùng `@DynamicPropertySource`, Testcontainers hoặc test-specific properties để cấp endpoint và credential của tài nguyên thực tế được tạo cho test.
- Không nên thêm `test-postgres-debug-local-external-api` chỉ để phục vụ một test class.
- Nếu cần kiểm thử điều kiện tạo bean, có thể kiểm tra trường hợp active profile khác nhau một cách có chủ đích.
- Đảm bảo test không vô tình gọi production endpoint hoặc dùng secret thật.

Một cấu hình test có thể tối giản:

~~~yaml
# application-test.yml
app:
  notification:
    enabled: false
  checkout:
    retry-count: 0
~~~

Với bài test tích hợp cần database, endpoint thực tế nên đến từ test harness. Điều quan trọng là cô lập được tác dụng phụ và giữ test lặp lại ổn định, không phải tạo nhiều tổ hợp profile.

## 16. Ma trận triển khai gọn và có thể xác minh

Thay vì mỗi nhóm phát triển tự đoán profile cần bật, hãy ghi rõ hợp đồng cấu hình. Ví dụ:

| Bối cảnh | Active profile chính | Nguồn cấu hình bổ sung | Khác biệt về bean |
| --- | --- | --- | --- |
| Local workstation | `local` | File override cá nhân, biến môi trường | Có thể dùng fake sender |
| CI integration | `test` | Testcontainers, biến của CI | Stub/tài nguyên test |
| Staging | `staging` | Deployment config, secrets staging | Adapter thật với endpoint staging |
| Production | `prod` | Deployment config, secrets production | Adapter thật với endpoint production |

Mỗi hàng cần có người chịu trách nhiệm và cách kiểm chứng. Đây là **ma trận triển khai**, không phải ma trận của mọi kết hợp region, feature, database và tenant.

Các yêu cầu thực tế cần ghi rõ:

1. **Một nơi xác định active profile**: ví dụ manifest deployment hoặc biến môi trường của CI/CD.
2. **File chung chỉ lưu giá trị chung**: tránh lặp.
3. **Property quan trọng có nguồn sở hữu rõ**: ví dụ URL từ config deployment, secret từ secret manager.
4. **Giới hạn tổ hợp profile cho phép**: chẳng hạn không cho cùng lúc `local` và `prod`.
5. **Kiểm tra startup bằng cấu hình thực tế**: phát hiện thiếu property, sai profile, lỗi binding/validation sớm.
6. **Đảm bảo tính tái lập**: cùng version artifact và cùng cấu hình đầu vào phải có hành vi khởi động tương ứng.

Với deployment có nhiều thành phần, có thể tự động kiểm tra rằng active profile chỉ thuộc tập đã quy định và thuộc đúng environment. Không cần biến quy tắc này thành hàng chục profile mới.

## 17. Kiểm tra cấu hình cuối cùng và xử lý xung đột

Khi một ứng dụng có nhiều nguồn property (file chung, file profile, config import, biến môi trường, command line), cấu hình cuối cùng không đơn giản là “lấy file ứng với profile”.

Một số cách kiểm tra hữu ích:

- Quan sát log khởi động để xác định profile đang active.
- Đọc manifest/pipeline thực tế để xác định biến `SPRING_PROFILES_ACTIVE` và các nguồn config được cấp.
- Dùng test context hoặc môi trường staging để xác thực bean được đăng ký đúng.
- Có thể dùng Spring Boot Actuator `/actuator/env` hoặc `/actuator/configprops` khi được cấu hình và **bảo vệ quyền truy cập** phù hợp; những endpoint này có thể liên quan cấu hình nhạy cảm, không được công khai tùy tiện.
- Kiểm tra lỗi binding/validation của `@ConfigurationProperties` để fail-fast khi thiếu cấu hình quan trọng.

Ví dụ một hệ thống có:

~~~yaml
# application.yml
app:
  integration:
    timeout: 3s
~~~

~~~yaml
# application-prod.yml
app:
  integration:
    timeout: 5s
~~~

Nhưng deployment lại cấp giá trị tương ứng qua environment hoặc command line với thứ tự ưu tiên cao hơn. Khi đó timeout hiệu lực có thể khác 5s. Cần kiểm tra **nguồn thắng cuối cùng**, không dựa hoàn toàn vào tên file.

Nếu hai profile được kích hoạt đồng thời và cùng khai báo một key, hãy cải thiện thiết kế để mỗi key có trách nhiệm rõ ràng. Đảo thứ tự profile cho đến khi ứng dụng chạy chỉ là xử lý triệu chứng.

## 18. Những sai lầm thiết kế thường gặp

### 18.1. Tạo profile riêng cho mỗi developer

~~~text
dev-phuong
dev-linh
dev-minh
~~~

Khó đồng bộ, dễ commit cấu hình máy cá nhân, và tạo hàng loạt trường hợp không cần thiết. Nên dùng một profile `local` chung cùng nguồn override cá nhân không chứa bí mật trong repository.

### 18.2. Dùng profile để bật một flag nhỏ

~~~text
prod-with-report
prod-without-report
~~~

Nếu chỉ là một cờ cấu hình, ưu tiên `app.reporting.enabled`. Cân nhắc `@ConditionalOnProperty` nếu cờ quyết định có tạo bean hay không. Chỉ tạo profile mới khi đó là một topology ổn định có ý nghĩa triển khai.

### 18.3. Copy nguyên file cấu hình cho mỗi môi trường

Bốn file dài hàng trăm dòng gần giống nhau làm thay đổi mặc định bị bỏ sót. Hãy chuyển cấu hình dùng chung vào `application.yml` và để mỗi file profile chỉ chứa khác biệt.

### 18.4. Dùng cả dev và prod cùng lúc

~~~bash
java -jar app.jar --spring.profiles.active=dev,prod
~~~

Các property và bean có thể bị trộn theo thứ tự nạp. Nếu thiếu một property ở production, cần bổ sung property đúng nguồn, không kích hoạt thêm dev để “mượn” giá trị.

### 18.5. Xem profile như cơ chế quản lý quyền

`@Profile("prod")` không phải lớp kiểm tra authorization hay secret access. Một runtime có cấu hình sai vẫn có thể chạy với profile không mong muốn. Quyền truy cập endpoint, credentials và dữ liệu phải được bảo vệ độc lập.

### 18.6. Đặt active/group/include sai vị trí

Ví dụ không nên:

~~~yaml
spring:
  config:
    activate:
      on-profile: "prod"
  profiles:
    active: "extra"
~~~

Các property dùng để quyết định active profile như `spring.profiles.active` không được khai báo bên trong tài liệu chỉ active theo profile. Hãy khai báo ở cấu hình không đặc thù profile hoặc điều khiển từ deployment.

### 18.7. Dùng phủ định quá rộng

`@Profile("!prod")` khớp mọi trường hợp không có prod, kể cả nhiều môi trường không dự kiến. Nếu ý định là local, khai báo `@Profile("local")` để giảm bất ngờ.

### 18.8. Dùng profile làm feature flag theo request

Một request không thể “kích hoạt Spring profile mới” cho riêng nó theo cách thông thường. Điều kiện profile được Spring dùng trong cấu trúc context và lúc tạo bean; muốn thay đổi hành vi theo request phải dùng strategy, policy hoặc routing ở runtime.

## 19. Bài tập thiết kế: chọn profile hay property?

Giả sử dịch vụ đặt hàng phải chạy local, CI, staging và prod. Hãy phân loại các yêu cầu:

| Yêu cầu | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| Local ghi email ra log, staging/prod gửi email thật | Profile hoặc bean condition | Khác implementation khi khởi tạo |
| Thay endpoint giữa staging/prod | Property theo deployment | Cùng adapter, chỉ khác giá trị |
| Đổi thời gian timeout từ 3s lên 5s | Property | Tham số vận hành |
| Bật báo cáo cho từng tenant | Feature flag/chính sách nghiệp vụ | Thay đổi theo tenant |
| CI dùng database do Testcontainers tạo | Test property injection | Endpoint phát sinh khi test chạy |
| Production ở EU và US | Property region cùng deployment config | Không buộc nhân đôi mọi profile |
| Test không được gửi email thật | Profile test, stub và ràng buộc test | Cô lập side effect |
| Mỗi khách hàng có thuế suất riêng | Dữ liệu/chính sách nghiệp vụ | Không thuộc cấu hình khởi động |

Từ đó có thể chọn cấu trúc:

~~~text
application.yml              -> mặc định chung, an toàn
application-local.yml        -> khác biệt thực sự cho local
application-test.yml         -> khác biệt thực sự cho test
application-staging.yml      -> khác biệt thực sự cho staging
application-prod.yml         -> khác biệt thực sự cho prod

Deployment -> chọn một profile chính
           -> cấp URL, region, credentials, secret, flag kỹ thuật
Application -> bind property thành kiểu Java
            -> chọn bean nếu topology cần khác
Runtime -> thực thi nghiệp vụ theo dữ liệu request/tenant
~~~

### Một ví dụ @ConfigurationProperties cho cấu hình chung

~~~java
package example.orders;

import java.time.Duration;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.integration")
public record IntegrationProperties(
        URI endpoint,
        Duration timeout,
        boolean enabled
) {}
~~~

File profile có thể override timeout; deployment có thể cấp endpoint. Nếu không có yêu cầu chọn implementation khác nhau, một service duy nhất nhận `IntegrationProperties` sẽ đơn giản hơn nhiều service `@Profile` chỉ khác các hằng số.

## 20. Checklist khi thêm hoặc sửa một profile

Trước khi tạo thêm profile, dùng các câu hỏi sau:

1. **Có thêm một loại triển khai mới thật sự không?** Nếu không, thử dùng property.
2. **Khác biệt này có cần chọn bean khác không?** Nếu chỉ thay giá trị, tránh thêm profile.
3. **Có nguy cơ tổ hợp với các profile hiện tại không?** Tính xem số kết hợp sẽ tăng bao nhiêu.
4. **Tập profile có thuộc một nhóm ổn định không?** Nếu có, cân nhắc profile group; nếu không, đừng ép nhóm.
5. **File theo profile chỉ chứa khác biệt không?** Tránh lặp cấu hình chung.
6. **Các nguồn override đã được hiểu chưa?** Kiểm tra config import, environment, command line và thứ tự active profiles.
7. **Profile có bật nhầm bean hoặc endpoint không?** Thử khởi động trong từng bối cảnh cần hỗ trợ.
8. **Có đang nhét secret hoặc dữ liệu nghiệp vụ vào file cấu hình không?** Tách ra nguồn thích hợp.
9. **Có thể giải thích profile cho người vận hành bằng một câu không?** Nếu không, tên hoặc phạm vi có lẽ chưa rõ.
10. **Đội phát triển có thể thay đổi môi trường mà không build lại artifact không?** Đảm bảo externalized configuration được sử dụng đúng.

## 21. Ghi nhớ

Profile là công cụ diễn đạt **bối cảnh triển khai và lựa chọn thành phần khi khởi động**. Hãy chọn ít profile có tên ổn định, ưu tiên `application.yml` cho cấu hình chung, chỉ ghi phần khác biệt trong `application-<profile>.yml` và để deployment cấp giá trị vận hành/secret. Dùng `@Profile` khi topology của bean khác nhau; dùng `@ConfigurationProperties` hoặc `@ConditionalOnProperty` khi chỉ cần biến đổi tham số hay bật/tắt một thành phần.

Profile group có ích khi một ngữ cảnh luôn kéo theo một bộ profile phụ trợ, nhưng nó không giải quyết việc tạo tổ hợp tùy ý theo vùng, khách hàng, database và feature flag. Thiết kế tốt là thiết kế mà người phát triển và vận hành **có thể chỉ ra profile nào active, vì sao active và giá trị cuối cùng đến từ nguồn nào**, với một số ít trường hợp cần kiểm soát.
