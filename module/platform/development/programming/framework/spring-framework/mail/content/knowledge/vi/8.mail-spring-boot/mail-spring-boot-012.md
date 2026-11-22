# Cấu hình sender trong nhiều profile Spring

## 1. Vì sao cần cấu hình mail sender theo môi trường?

Trong một ứng dụng sử dụng **Spring Boot** và **Spring Framework Mail**, cùng một chức năng gửi email có thể chạy ở nhiều môi trường: máy lập trình viên, môi trường kiểm thử, staging và production. Code nghiệp vụ vẫn có thể gọi cùng một interface `JavaMailSender`, nhưng máy chủ SMTP, tài khoản, TLS, người nhận được phép và mức độ gửi email ra ngoài cần được quản lý theo môi trường.

Ví dụ:

- Ở **local**, email nên được đưa tới một SMTP sink như Mailpit/MailHog để lập trình viên quan sát nội dung mà không gửi cho khách hàng thật.
- Ở **test**, bài kiểm thử logic nên dùng fake/mock sender; bài kiểm thử tích hợp có thể dùng một SMTP server thử nghiệm được kiểm soát.
- Ở **staging**, ứng dụng có thể gửi qua tài khoản thử nghiệm của nhà cung cấp, kèm giới hạn địa chỉ nhận và cấu hình an toàn.
- Ở **production**, ứng dụng gửi qua dịch vụ chính thức, dùng credentials được quản lý như bí mật, TLS và chính sách vận hành phù hợp.

Nếu tất cả môi trường dùng chung một SMTP endpoint và password trong `application.yml`, ứng dụng chạy local có thể vô tình gửi email thật hoặc staging bị mất quyền truy cập do dùng nhầm tài khoản. **Spring profiles** giúp phân tách cấu hình theo môi trường, trong khi code gửi thư phụ thuộc vào cùng abstraction.

> Mục tiêu của profile là **chọn cấu hình cần dùng khi chạy ứng dụng**. Profile không tự tạo một hệ thống chống gửi nhầm; ứng dụng vẫn cần kiểm soát quyền, địa chỉ nhận và chính sách bảo mật phù hợp.

## 2. Profile ảnh hưởng đến JavaMailSender như thế nào?

**Spring profile** là một tên định danh như `local`, `test`, `staging` hoặc `prod`. Khi một profile được kích hoạt, Spring Boot có thể nạp cấu hình riêng trong `application-{profile}.yml`, đồng thời Spring Framework có thể bật/tắt bean được gắn `@Profile`.

Với cấu hình mail thông thường, Spring Boot cung cấp **MailSender auto-configuration**: khi classpath và các điều kiện cấu hình đáp ứng, Boot tạo một bean `JavaMailSender` (thường triển khai bằng `JavaMailSenderImpl`), gán các thuộc tính `spring.mail.*` và để các service inject interface `JavaMailSender`.

~~~mermaid
flowchart TD
    A["Khởi động Spring Boot"] --> B["Đọc application.yml"]
    B --> C["Xác định active profile"]
    C --> D["Nạp cấu hình theo profile"]
    D --> E["Kết hợp property sources và giá trị override"]
    E --> F["Tạo/cấu hình JavaMailSender nếu đủ điều kiện"]
    F --> G["Inject JavaMailSender vào service"]
    G --> H["Khi có yêu cầu: tạo MIME và gửi qua SMTP"]
~~~

Đọc cấu hình và tạo bean là các bước ở **thời điểm khởi động**; còn kết nối SMTP thường chỉ diễn ra khi code gửi email hoặc khi ứng dụng chủ động kiểm tra kết nối. Vì vậy cấu hình được nạp thành công không đồng nghĩa SMTP credentials hay đường truyền chắc chắn đúng.

### 2.1. Hai phạm vi khác nhau của profile

| Cơ chế | Ví dụ | Ảnh hưởng |
| --- | --- | --- |
| **Cấu hình theo profile** | `application-local.yml`, `application-prod.yml` | Các thuộc tính `spring.mail.host`, `port`, TLS, timeout... được chọn theo môi trường |
| **Bean theo profile** | `@Profile("test")` trên một `@Configuration`/`@Bean` | Một implementation sender riêng chỉ xuất hiện ở profile đó |
| **Profile khi kiểm thử** | `@ActiveProfiles("test")` | Spring Test khởi tạo context với profile cần kiểm thử |
| **Kích hoạt từ môi trường** | `SPRING_PROFILES_ACTIVE=prod` | Chọn profile khi khởi động mà không cần sửa source |

**Với một SMTP sender duy nhất mỗi môi trường, thường chỉ cần cấu hình `spring.mail.*` theo profile.** Không cần viết các class `@Configuration` giống nhau chỉ để thay đổi host hoặc port.

Nếu cần thay *implementation* (ví dụ test dùng fake sender, production dùng SMTP thật) hoặc có nhiều tài khoản gửi đồng thời, khi đó cấu hình bean có điều kiện hoặc named sender mới trở nên cần thiết.

## 3. Cấu trúc tệp cấu hình dễ quản lý

Một dự án Spring Boot có thể tổ chức:

~~~text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-staging.yml
└── application-prod.yml

src/test/resources/
└── application-test.yml
~~~

Ý nghĩa:

- `application.yml` chứa **các cấu hình chung** không phụ thuộc môi trường, ví dụ timeout.
- `application-local.yml` ghi endpoint SMTP sandbox trên máy lập trình viên.
- `application-staging.yml` chỉ định tài khoản và chính sách kết nối của staging.
- `application-prod.yml` chỉ định chính sách của production; lấy credentials từ nguồn bí mật.
- `application-test.yml` chứa cấu hình riêng cho test; test logic có thể thay sender bằng fake/mock, còn integration test có thể dùng một sink chuyên biệt.

Các tên `local`, `staging`, `prod` không phải tên profile cố định của Spring. Chúng do nhóm phát triển lựa chọn và cần thống nhất với quy trình triển khai.

### 3.1. application.yml: chỉ đặt những giá trị dùng chung

Ví dụ:

~~~yaml
# src/main/resources/application.yml
spring:
  mail:
    default-encoding: UTF-8
    properties:
      mail.smtp.connectiontimeout: 5000
      mail.smtp.timeout: 5000
      mail.smtp.writetimeout: 5000
~~~

Giải thích:

- `spring.mail.default-encoding` đặt encoding mặc định khi tạo message theo cấu hình của Boot.
- `mail.smtp.connectiontimeout` giới hạn thời gian chờ kết nối TCP.
- `mail.smtp.timeout` giới hạn thời gian chờ đọc dữ liệu qua SMTP socket.
- `mail.smtp.writetimeout` giới hạn thời gian chờ ghi.
- Các giá trị timeout ở đây là **mili-giây**; chỉ là ví dụ và cần điều chỉnh theo điều kiện mạng/thời gian đáp ứng của provider.

Để tránh gửi nhầm, ví dụ cố ý **không đặt** `spring.mail.host`, tài khoản hay mật khẩu production trong file chung. Môi trường nào cần SMTP thật sẽ tự cung cấp endpoint phù hợp. Nếu ứng dụng phải có `JavaMailSender` ở mọi môi trường, cần bảo đảm profile tương ứng tạo được bean hoặc cung cấp fake/mocked bean cho test.

### 3.2. application-local.yml: SMTP sandbox

~~~yaml
# src/main/resources/application-local.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      mail.smtp.auth: false
      mail.smtp.starttls.enable: false
      mail.smtp.starttls.required: false
~~~

Giả định máy lập trình viên chạy một **SMTP sink** (chẳng hạn Mailpit) ở `127.0.0.1:1025`. Đây là một ví dụ endpoint cục bộ; không có SMTP sink chạy thì thao tác gửi sẽ thất bại vì kết nối không đến được server.

SMTP sink nhận thông điệp và lưu ở giao diện kiểm thử, thay vì định tuyến ra Internet. Tùy cấu hình công cụ, có thể xem email từ một web UI riêng.

**Không sao chép cấu hình `auth: false`/`starttls: false` sang production.** Việc không xác thực và không dùng TLS ở ví dụ này chỉ dành cho SMTP sink cô lập trên local. Nếu chạy ứng dụng trong container, `127.0.0.1` trỏ tới **chính container ứng dụng**, không nhất thiết trỏ tới máy host hoặc container SMTP. Trong môi trường Docker Compose, hãy dùng tên service/địa chỉ mạng được khai báo cho SMTP sink.

### 3.3. application-staging.yml: SMTP submission có STARTTLS

~~~yaml
# src/main/resources/application-staging.yml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
~~~

Spring Boot giải quyết các placeholder từ environment hoặc property sources khác:

- `${SMTP_HOST}`: hostname SMTP bắt buộc.
- `${SMTP_PORT:587}`: lấy cổng từ `SMTP_PORT`; nếu chưa cấu hình, dùng `587`.
- `${SMTP_USERNAME}` và `${SMTP_PASSWORD}`: lấy thông tin xác thực từ nguồn cấu hình bên ngoài.

Với submission qua cổng `587`, `STARTTLS` nâng cấp kết nối TCP đã mở lên TLS. `mail.smtp.starttls.required=true` buộc transport không tiếp tục gửi trên kết nối không đáp ứng yêu cầu này. Thuộc tính `mail.smtp.ssl.checkserveridentity=true` yêu cầu kiểm tra tên server theo chứng chỉ trong Jakarta Mail SMTP provider có hỗ trợ thuộc tính tương ứng.

Staging thường cần thêm chính sách ở tầng nghiệp vụ: giới hạn người nhận, sử dụng miền/tài khoản thử nghiệm, đánh dấu tiêu đề và lưu vết gửi. Những biện pháp đó **không tự xuất hiện** chỉ vì profile có tên `staging`.

### 3.4. application-prod.yml: chính sách production

Một ví dụ production cũng dùng SMTP submission qua STARTTLS:

~~~yaml
# src/main/resources/application-prod.yml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.starttls.enable: true
      mail.smtp.starttls.required: true
      mail.smtp.ssl.checkserveridentity: true
~~~

Hai file staging/prod có thể giống nhau ở phương thức bảo mật mà vẫn dùng **giá trị biến môi trường khác nhau**. Lợi ích của việc giữ chúng tách biệt là có thể chủ động thay chính sách riêng theo môi trường mà không đổi code gửi email.

Nếu provider production sử dụng **TLS ngay khi mở kết nối** trên cổng `465` (*implicit TLS*), cấu hình phải chuyển sang mode phù hợp, ví dụ:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 465
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail.smtp.auth: true
      mail.smtp.ssl.enable: true
      mail.smtp.ssl.checkserveridentity: true
~~~

Đây là một **phương án thay thế** cho cấu hình STARTTLS phía trên, không nên gộp hai ví dụ một cách tùy tiện. Chọn cổng và cơ chế TLS theo tài liệu SMTP provider; không mặc định `465`/`587` luôn được mở trong mọi hạ tầng.

### 3.5. application-test.yml: phân biệt unit test với SMTP integration test

Với test logic của service, lựa chọn phù hợp thường là thay `JavaMailSender` bằng mock/fake, để test kiểm tra nội dung được tạo và hành vi của service mà **không tạo kết nối ra ngoài**. Khi dùng Spring Test, kích hoạt profile:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class NotificationServiceTest {
    // Cấu hình hoặc thay JavaMailSender bằng mock/fake
    // theo cơ chế Spring Test mà dự án đang sử dụng.
}
~~~

Trong Spring Boot 3.3, có thể sử dụng `@MockBean` của Boot Test để thay sender trong test context. Nếu code được phép gọi `createMimeMessage()`, mock cần trả về `MimeMessage` hợp lệ (hoặc dùng một fake sender biết lưu những message đã gửi); một mock trả `null` cho mọi phương thức sẽ không phản ánh đúng đường tạo thư.

Đối với **integration test SMTP**, có thể cung cấp một `application-test.yml` trỏ tới SMTP sink/container kiểm thử:

~~~yaml
# src/test/resources/application-test.yml
spring:
  mail:
    host: 127.0.0.1
    port: 1025
    properties:
      mail.smtp.auth: false
      mail.smtp.starttls.enable: false
~~~

Giá trị chỉ phù hợp khi có SMTP sink thực sự được kiểm thử quản lý tại địa chỉ đó. Khi chạy trong CI/container, hostname và port phải được cấp cho test theo môi trường, tránh phụ thuộc vào dịch vụ ngẫu nhiên trên máy lập trình viên. Test tích hợp nên đọc message trong SMTP sink để xác nhận envelope/body/MIME theo mục tiêu test, thay vì gửi đến địa chỉ email công cộng.

## 4. Kích hoạt profile khi chạy ứng dụng

Cấu hình riêng chỉ được nạp khi profile tương ứng hoạt động. Ví dụ một vài cách:

~~~bash
# Trên môi trường Unix-like, kích hoạt profile trước khi chạy:
SPRING_PROFILES_ACTIVE=staging java -jar mail-service.jar

# Dùng JVM system property (phù hợp trong nhiều môi trường):
java -Dspring.profiles.active=prod -jar mail-service.jar

# Dùng command-line argument của Spring Boot:
java -jar mail-service.jar --spring.profiles.active=local
~~~

Trên Windows PowerShell, có thể thiết lập biến môi trường ở shell hiện tại:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
java -jar mail-service.jar
~~~

Ví dụ với test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class MailProfileContextTest {
    @Test
    void contextLoads() {
        // Kiểm tra context profile test được khởi tạo.
    }
}
~~~

`spring.profiles.active` có thể được cung cấp từ property source ngoài ứng dụng (ví dụ biến môi trường `SPRING_PROFILES_ACTIVE` hoặc command-line argument). Với hệ thống có nhiều profile, giá trị thường là danh sách ngăn bằng dấu phẩy:

~~~text
SPRING_PROFILES_ACTIVE=staging,observability
~~~

Cần hiểu **thứ tự và quyền ưu tiên property sources**: cấu hình có độ ưu tiên cao hơn có thể ghi đè giá trị từ file profile. Khi nhiều profile active có những thuộc tính trùng nhau, profile được xử lý sau có thể ghi đè giá trị của profile trước trong cùng nhóm cấu hình tương ứng. Không nên dùng nhiều profile mâu thuẫn cùng cung cấp SMTP host/credentials, ví dụ `local,prod`, nếu không có quy ước hợp nhất và kiểm soát rõ.

### 4.1. Không hard-code active profile vào mã Java

Ví dụ không nên làm:

~~~java
if (environment.getActiveProfiles()[0].equals("prod")) {
    // Tự tạo transport production ở nhiều nơi trong code.
}
~~~

Cách này phụ thuộc thứ tự profile, có thể lỗi khi không có active profile, và tạo cấu hình trùng lặp với Spring Boot. Với một mail sender thông thường, hãy để hệ thống cấu hình môi trường chọn `spring.mail.*`, còn service chỉ inject `JavaMailSender`.

### 4.2. Profile active phải nằm ở nơi khai báo hợp lệ

Spring Boot hỗ trợ file theo tên `application-prod.yml` và YAML multi-document dùng `spring.config.activate.on-profile`, ví dụ:

~~~yaml
spring:
  mail:
    default-encoding: UTF-8

---
spring:
  config:
    activate:
      on-profile: local
  mail:
    host: 127.0.0.1
    port: 1025

---
spring:
  config:
    activate:
      on-profile: prod
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
~~~

Đây là phương án **multi-document YAML** thay cho các file `application-*.yml` riêng. Chỉ cần chọn một cách tổ chức nhất quán để dễ đọc và review.

Không khai báo `spring.profiles.active` hoặc `spring.profiles.include` trong tài liệu vốn đã chỉ được bật bởi `spring.config.activate.on-profile` hoặc trong file profile-specific. Spring Boot giới hạn những thuộc tính điều khiển việc kích hoạt profile ở các vị trí profile-specific để tránh tự kích hoạt vòng lặp khó dự đoán. Hãy kích hoạt profile từ nguồn chung hoặc môi trường chạy.

## 5. Cấu hình nào có hiệu lực khi nhiều nguồn cùng cung cấp một property?

Hệ thống cấu hình của Spring Boot hợp nhất nhiều **property sources**: file cấu hình, biến môi trường, system property, đối số dòng lệnh và các nguồn được bổ sung bởi ứng dụng. Khi cùng một property được khai báo ở nhiều nơi, **giá trị có độ ưu tiên cao hơn** quyết định giá trị hiệu lực.

Ví dụ:

~~~yaml
# application.yml
spring:
  mail:
    port: 1025
~~~

~~~yaml
# application-prod.yml
spring:
  mail:
    port: 587
~~~

~~~text
SPRING_PROFILES_ACTIVE=prod
SPRING_MAIL_PORT=2525
~~~

Trong cấu hình thông dụng này, `SPRING_MAIL_PORT` là biến môi trường có thể ghi đè cấu hình trong file, do đó giá trị hiệu lực của `spring.mail.port` là `2525`. Nếu có command-line argument độ ưu tiên cao hơn:

~~~text
--spring.mail.port=465
~~~

thì `465` có thể trở thành giá trị hiệu lực. Các trường hợp config import, nguồn cấu hình tùy biến hay cơ chế triển khai đặc biệt có thể làm thứ tự tổng thể phức tạp hơn; vì vậy khi nghi ngờ, nên kiểm tra **property sources thực tế của application context** thay vì suy đoán từ tên file.

### 5.1. Phân biệt environment variable trực tiếp và placeholder

Hai cách cấu hình hợp lệ nhưng hoạt động khác nhau:

**Bind trực tiếp bằng tên property của Boot:**

~~~text
SPRING_MAIL_HOST=smtp.example.net
SPRING_MAIL_PORT=587
SPRING_MAIL_USERNAME=some-account
SPRING_MAIL_PASSWORD=provided-secret
~~~

**Hoặc để YAML đọc biến có tên tùy chọn:**

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
~~~

Ở cách thứ hai, `SMTP_HOST` không phải tên property `spring.mail.host` của Boot; nó chỉ được đưa vào vì có placeholder `${SMTP_HOST}`. Hai cách đều có thể dùng, nhưng đừng đặt tên biến tùy ý rồi kỳ vọng Spring tự hiểu mọi tên đó là `spring.mail.*`.

### 5.2. Không được đưa secret vào log khi kiểm tra precedence

Khi cần xác minh cấu hình đang dùng, có thể ghi nhận những thông tin **không nhạy cảm**, ví dụ active profiles, loại transport, host đã được phê duyệt để hiển thị và port. Không ghi password hoặc token.

Ví dụ:

~~~java
package com.example.mail;

import java.util.Arrays;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class MailEnvironmentDescription {

    private final Environment environment;

    public MailEnvironmentDescription(Environment environment) {
        this.environment = environment;
    }

    public String describe() {
        return "activeProfiles="
                + Arrays.toString(environment.getActiveProfiles())
                + ", smtpPort="
                + environment.getProperty("spring.mail.port", "unset");
    }
}
~~~

Đây chỉ là ví dụ lấy metadata; trong ứng dụng thật, những thông tin như host/domain nội bộ đôi khi cũng cần giới hạn hiển thị. Để xác định nguồn nào cung cấp một property, có thể dùng công cụ quan sát cấu hình của Spring Boot trong **môi trường được phân quyền**, bảo đảm các giá trị nhạy cảm luôn được che.

### 5.3. “Default profile” không đồng nghĩa profile prod

Nếu không cấu hình active profile, Spring dùng profile mặc định (thường tên `default`) cho các bean và tài liệu cấu hình tương ứng. File `application.yml` vẫn được đọc. Khi cần, `application-default.yml` có thể chứa cấu hình dùng khi chưa kích hoạt profile nào.

Không nên ngầm định “không có profile” có nghĩa đang chạy production. Một ứng dụng gửi mail nên có **quy ước khởi động rõ ràng**: production phải chỉ định profile và credentials phù hợp; môi trường không xác định thì không được tự động gửi thư đến người dùng thật.

## 6. Khi nào cần @Profile trên một sender bean?

Một service thông thường có thể chỉ inject:

~~~java
package com.example.notification;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailer {

    private final JavaMailSender mailSender;

    public NotificationMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient, String body)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(message, false, "UTF-8");

        helper.setFrom("notifications@example.com");
        helper.setTo(recipient);
        helper.setSubject("Thông báo hệ thống");
        helper.setText(body, false);

        mailSender.send(message);
    }
}
~~~

Class này không cần biết ứng dụng đang ở `local` hay `prod`. Spring sẽ inject bean `JavaMailSender` hiệu lực theo context, và bean đó sử dụng cấu hình môi trường tương ứng.

Chỉ nên dùng `@Profile` khi cần thay đổi **bean/implementation**, ví dụ một service chặn gửi thật trong test hay một adapter dành riêng cho hệ thống legacy:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.mail.javamail.JavaMailSender;

@Configuration(proxyBeanMethods = false)
@Profile("legacy-smtp")
class LegacyMailConfiguration {

    @Bean
    JavaMailSender legacyMailSender() {
        // Xây dựng JavaMailSenderImpl từ cấu hình an toàn
        // chỉ khi profile legacy-smtp được kích hoạt.
        throw new UnsupportedOperationException(
                "Ví dụ khung cấu hình, cần implementation cụ thể");
    }
}
~~~

Ví dụ trên **chỉ minh họa vị trí của annotation**, chưa phải bean dùng được. Khi triển khai thật, method phải trả `JavaMailSenderImpl` đã cấu hình đầy đủ. Nếu đã có `spring.mail.*` và Boot auto-config, tạo thêm bean tùy chỉnh không cần thiết có thể khiến auto-configuration **lùi lại** hoặc tạo xung đột theo loại bean. Cần chọn một cơ chế sở hữu cấu hình gửi mail rõ ràng.

### 6.1. @Profile và @ConditionalOnProperty khác nhau

| Nhu cầu | Cơ chế phù hợp |
| --- | --- |
| Bật cấu hình riêng cho `prod` | File `application-prod.yml` hoặc `@Profile("prod")` khi thay bean |
| Chỉ tạo fake mailer trong `test` | `@Profile("test")` trên bean cấu hình test |
| Bật chức năng gửi thông báo theo cờ nghiệp vụ | `@ConditionalOnProperty` với một property như `app.notifications.email.enabled` |
| Đặt host và port theo môi trường | `spring.mail.*` trong file profile-specific |
| Dùng hai SMTP accounts đồng thời trong một profile | Hai named beans và `@Qualifier` hoặc abstraction riêng |

Profile mô tả **môi trường hoặc tập cấu hình đang hoạt động**; một feature flag mô tả **trạng thái của một tính năng**. Không cần tạo profile mới cho mọi lựa chọn nghiệp vụ. Đồng thời, khi bật/tắt gửi email qua feature flag, hãy kiểm tra đường thực thi để chắc chắn tác vụ không dùng một sender khác đi vòng qua cơ chế đó.

### 6.2. Ví dụ chọn cấu hình khác bằng @Profile

Nếu một ứng dụng cần tự tạo `JavaMailSenderImpl` cho một profile riêng, có thể cấu hình:

~~~java
package com.example.mail.config;

import java.util.Properties;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration(proxyBeanMethods = false)
@Profile("custom-smtp")
public class CustomSmtpConfiguration {

    @Bean
    JavaMailSender mailSender(
            org.springframework.core.env.Environment environment) {

        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(environment.getRequiredProperty("app.smtp.host"));
        sender.setPort(Integer.parseInt(
                environment.getProperty("app.smtp.port", "587")));
        sender.setUsername(
                environment.getRequiredProperty("app.smtp.username"));
        sender.setPassword(
                environment.getRequiredProperty("app.smtp.password"));
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.ssl.checkserveridentity", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "5000");
        properties.put("mail.smtp.writetimeout", "5000");

        return sender;
    }
}
~~~

Với profile `custom-smtp`, properties `app.smtp.*` phải được cung cấp bởi cấu hình phù hợp hoặc môi trường chạy. Ví dụ này cho thấy cách bean chỉ được tạo trong một profile; nó không yêu cầu chỉnh sửa code service `NotificationMailer` phía trên.

Đây là phương án **tùy chỉnh**, dành cho khi cần điều khiển rõ hơn việc tạo sender. Với những ứng dụng thông thường, `spring.mail.*` cùng auto-configuration của Spring Boot vẫn là cấu hình đơn giản hơn.

## 7. Nhiều profile và nhiều sender đồng thời là hai bài toán khác nhau

Một hiểu nhầm phổ biến:

> “Tôi có `application-staging.yml` và `application-prod.yml`, vậy Spring tạo cả hai `JavaMailSender`?”

Không. Trong một Spring context, các property theo profile đang active được hợp nhất để tạo **cấu hình hiệu lực**. Mô hình mặc định thường là **một `JavaMailSender` dùng cấu hình hiện tại**, không tự sinh một sender cho mỗi file.

Nếu ứng dụng cần đồng thời gửi email giao dịch qua nhà cung cấp A và email hỗ trợ qua nhà cung cấp B, nên tạo **hai bean có tên riêng**. Ví dụ:

~~~yaml
app:
  mail:
    transactional:
      host: ${TRANSACTIONAL_SMTP_HOST}
      port: ${TRANSACTIONAL_SMTP_PORT:587}
      username: ${TRANSACTIONAL_SMTP_USERNAME}
      password: ${TRANSACTIONAL_SMTP_PASSWORD}
    support:
      host: ${SUPPORT_SMTP_HOST}
      port: ${SUPPORT_SMTP_PORT:587}
      username: ${SUPPORT_SMTP_USERNAME}
      password: ${SUPPORT_SMTP_PASSWORD}
~~~

Bean configuration:

~~~java
package com.example.mail.config;

import java.util.Properties;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration(proxyBeanMethods = false)
public class MultipleSendersConfiguration {

    @Bean("transactionalMailSender")
    JavaMailSender transactionalSender(
            @Value("${app.mail.transactional.host}") String host,
            @Value("${app.mail.transactional.port:587}") int port,
            @Value("${app.mail.transactional.username}") String user,
            @Value("${app.mail.transactional.password}") String password) {
        return createSender(host, port, user, password);
    }

    @Bean("supportMailSender")
    JavaMailSender supportSender(
            @Value("${app.mail.support.host}") String host,
            @Value("${app.mail.support.port:587}") int port,
            @Value("${app.mail.support.username}") String user,
            @Value("${app.mail.support.password}") String password) {
        return createSender(host, port, user, password);
    }

    private JavaMailSender createSender(
            String host, int port, String user, String password) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(user);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties props = sender.getJavaMailProperties();
        props.put("mail.smtp.auth", "true");
        props.put("mail.smtp.starttls.enable", "true");
        props.put("mail.smtp.starttls.required", "true");
        props.put("mail.smtp.ssl.checkserveridentity", "true");
        props.put("mail.smtp.connectiontimeout", "5000");
        props.put("mail.smtp.timeout", "5000");
        props.put("mail.smtp.writetimeout", "5000");
        return sender;
    }
}
~~~

Lúc này service phải chọn đúng bean:

~~~java
package com.example.mail;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class TransactionalEmailService {

    private final JavaMailSender mailSender;

    public TransactionalEmailService(
            @Qualifier("transactionalMailSender")
            JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    // Tạo MimeMessage và gửi qua đúng sender được chỉ định.
}
~~~

Nếu inject `JavaMailSender` mà không phân biệt tên, trong context có nhiều bean cùng kiểu, Spring có thể báo lỗi **không xác định được bean duy nhất** (`NoUniqueBeanDefinitionException`) nếu không có cách lựa chọn khác. `@Qualifier` giúp code thể hiện rõ mục đích. `@Primary` có thể chỉ định một bean ưu tiên, nhưng nên tránh dùng nó để giấu sự khác nhau quan trọng giữa hai đường gửi thư.

**Các điểm cần phân biệt:**

- `spring.mail.*` là namespace auto-configuration cho sender mặc định; hai nhóm `app.mail.transactional.*` và `app.mail.support.*` là **properties do ứng dụng tự định nghĩa** và được code trên đọc trực tiếp.
- Khi ứng dụng tự định nghĩa `MailSender`/`JavaMailSender` bean, Spring Boot mail auto-configuration có thể back off theo điều kiện của nó; không mặc định rằng Boot tiếp tục tạo một sender thứ ba.
- `@Qualifier` chọn sender theo mục đích nghiệp vụ; profile vẫn có thể thay **host, port, credentials** của cả hai sender ở từng môi trường.
- Một provider hỏng không khiến Spring tự động chuyển sang sender khác. Failover, retry và idempotency phải được thiết kế nếu nghiệp vụ cần chúng.

Mẫu trên là cách minh họa tạo hai sender cố định. Dự án có nhiều tài khoản thường nên gom cấu hình theo `@ConfigurationProperties` và validate đầu vào lúc khởi động, thay vì nhân đôi từng tham số và setter trên nhiều bean.

## 8. Credentials, TLS và chính sách riêng từng profile

### 8.1. Profile không thay thế kho lưu trữ bí mật

`application-prod.yml` có thể tham chiếu biến môi trường, nhưng không nên chứa SMTP password thật trong Git. Một cách triển khai thông dụng là cung cấp `SMTP_USERNAME`/`SMTP_PASSWORD` tại runtime từ secret manager, orchestration platform hoặc cơ chế quản lý bí mật của tổ chức.

Đối với staging và production:

- Dùng tài khoản được cấp quyền cho miền gửi; không để form công khai tùy ý đặt `From`.
- Tách credentials giữa môi trường để giảm phạm vi ảnh hưởng khi có sự cố.
- Dùng TLS theo yêu cầu nhà cung cấp và xác thực server thích hợp.
- Quy định recipient cho phép ở môi trường thử nghiệm; tránh gửi thư kiểm thử tới khách hàng thật.
- Giới hạn tần suất gửi và retry; theo dõi lỗi xác thực và lỗi chuyển phát.
- Luân chuyển credential mà không phải sửa source code hay commit giá trị mới.

Chỉ thấy `prod` trong `SPRING_PROFILES_ACTIVE` không phải bằng chứng một request có quyền gửi email thật. Quyền gửi phải được hệ thống cấp và kiểm soát ở tầng ứng dụng/provider.

### 8.2. Tránh “sửa” TLS bằng cách bỏ kiểm tra chứng chỉ

Ví dụ cùng là SMTP nhưng hai cơ chế thường gặp:

| Cổng thường dùng | Cơ chế | Thuộc tính liên quan |
| --- | --- | --- |
| `587` | Submission, kết nối rồi nâng cấp bằng STARTTLS | `mail.smtp.starttls.enable=true`, có thể `required=true` |
| `465` | TLS ngay từ đầu kết nối (*implicit TLS*) | `mail.smtp.ssl.enable=true` |
| `1025` ở local sink | SMTP thử nghiệm cô lập, có thể không auth/TLS | Tùy SMTP sink; tuyệt đối không coi là mặc định Internet |

Khi gặp `SSLHandshakeException`, cần xem cấu hình cổng, mode TLS, trust store và hostname verification. Không tự động chuyển sang plaintext hoặc bật “trust all certificates” chỉ để gửi thành công.

### 8.3. JNDI Session và spring.mail.*

Ngoài host/port/user/password, Spring Boot còn có thể cấu hình Jakarta Mail `Session` qua `spring.mail.jndi-name` trong môi trường hỗ trợ JNDI. Nếu cấu hình JNDI session, những property trực tiếp của mail sender có thể được xử lý khác hoặc bị JNDI session ưu tiên tùy cơ chế auto-configuration.

Vì vậy, khi host/port dường như không đổi dù đã sửa `application-prod.yml`, hãy kiểm tra liệu sender đang lấy `Session` từ JNDI hay không. Không cấu hình đồng thời nhiều nguồn session với ý định mơ hồ.

## 9. Kiểm tra cấu hình trước khi gửi thư thật

Có ba cấp độ cần phân biệt:

| Cấp độ | Phương pháp | Điều được chứng minh |
| --- | --- | --- |
| **Cấu hình Spring context** | Kiểm tra active profiles, bean `JavaMailSender`, property values đã được che secrets | Context có bean và thông số hiệu lực theo dự kiến |
| **Kết nối SMTP** | Kiểm tra kết nối trong môi trường cho phép, hoặc dùng `spring.mail.test-connection` có kiểm soát | Endpoint và phiên kết nối/xác thực đáp ứng ở thời điểm kiểm tra |
| **Gửi email end-to-end** | Gửi tới SMTP sink hoặc tài khoản thử nghiệm, kiểm tra message nhận thực tế | Quá trình tạo, vận chuyển và tiếp nhận thử nghiệm hoạt động theo điều kiện đó |

Spring Boot có thuộc tính `spring.mail.test-connection`. Khi bật trong cấu hình phù hợp, Boot có thể thử kết nối với mail server khi khởi tạo và làm quá trình khởi động thất bại nếu việc kiểm tra kết nối không thành công.

Ví dụ trong staging:

~~~yaml
# application-staging.yml
spring:
  mail:
    test-connection: true
~~~

Đây là **phần bổ sung** cho cấu hình staging trước đó. Cần cân nhắc chính sách vận hành: một hệ thống email bên ngoài tạm thời không sẵn sàng có thể khiến ứng dụng không khởi động được. Thuộc tính này **không gửi một email tới người nhận để chứng minh delivery**, và kết nối thành công cũng không bảo đảm mọi lần gửi tiếp theo đều thành công.

Với test logic, cách phù hợp thường là không mở kết nối mạng. Kiểm tra việc tạo `MimeMessage` và gọi `JavaMailSender` trên fake/mock. Với integration test, dùng SMTP sink để đọc thông điệp thực tế, kiểm tra địa chỉ nhận, text/HTML, inline image và attachment.

### 9.1. Kiểm tra active profile bằng code

Khi cần điều tra context, có thể dùng `Environment`:

~~~java
import java.util.Arrays;
import org.springframework.core.env.Environment;

String active = Arrays.toString(environment.getActiveProfiles());
boolean production = environment.acceptsProfiles(
        org.springframework.core.env.Profiles.of("prod"));
~~~

`acceptsProfiles(...)` diễn đạt điều kiện profile rõ hơn so với chỉ lấy `getActiveProfiles()[0]`. Tuy nhiên, một ứng dụng không nên tự quyết định toàn bộ cấu hình SMTP dựa vào điều kiện `if (production)` rải rác trong business code. Dùng điều kiện profile khi thật sự cần chọn behavior; cấu hình host/TLS nên tập trung trong config.

## 10. Các tình huống cấu hình sai thường gặp

### 10.1. No qualifying bean of type JavaMailSender

Ví dụ:

~~~text
No qualifying bean of type 'JavaMailSender' available
~~~

Nguyên nhân có thể là thiếu dependency Jakarta Mail/Spring Mail, không đáp ứng điều kiện auto-configuration, không có `spring.mail.host` hoặc JNDI session, hay custom bean bị vô hiệu vì profile không khớp.

Hướng xử lý:

1. Xem classpath và starter mail.
2. Xác nhận profile đã active.
3. Xác nhận các properties/bean condition cần thiết.
4. Nếu test chủ động dùng fake, bảo đảm fake bean được import/đăng ký đúng context.

Chỉ đặt tên một file `application-prod.yml` không đảm bảo `JavaMailSender` xuất hiện trong mọi profile.

### 10.2. Có nhiều JavaMailSender và injection không rõ

Triệu chứng:

~~~text
NoUniqueBeanDefinitionException:
expected single matching bean but found 2
~~~

Nếu ứng dụng tự tạo sender cho marketing và transactional, cần inject với `@Qualifier` hoặc một cách lựa chọn rõ ràng. Dùng `@Primary` khi thật sự có default thích hợp, không để service tùy ý nhận tài khoản gửi khác mục đích.

### 10.3. Local gửi nhầm ra provider production

Khả năng thường gặp:

- Người chạy đặt `SPRING_PROFILES_ACTIVE=prod` mà không nhận ra.
- Biến môi trường `SPRING_MAIL_HOST` ghi đè giá trị trong `application-local.yml`.
- Nhiều profile active khiến một cấu hình không dự kiến được ưu tiên.
- Một bean tự tạo có credentials production, không dùng `spring.mail.*` mà team đang kiểm tra.

Cần quan sát **giá trị cấu hình hiệu lực và nguồn cấu hình**, không chỉ mở `application-local.yml` rồi kết luận đang dùng SMTP sink.

### 10.4. Staging bị lỗi AuthenticationFailedException

Nguyên nhân có thể gồm tài khoản chưa được cấp quyền SMTP, secret không được inject, username/password nhầm môi trường, phương thức AUTH không được provider chấp nhận hoặc chính sách TLS.

Kiểm tra `MailAuthenticationException` và cause bên trong. Không log password/token hoặc chuyển sang không xác thực chỉ để bỏ lỗi. Đồng thời không mặc định lỗi auth luôn do gõ sai mật khẩu.

### 10.5. Production bị TLS handshake error

Ví dụ SMTP server yêu cầu implicit TLS trên `465` nhưng ứng dụng lại dùng cấu hình STARTTLS trên kết nối plaintext. Hoặc trust store không nhận chứng chỉ server.

Cần phân biệt cổng/protocol và đọc cause như `SSLHandshakeException`. Không xử lý bằng cách bỏ `mail.smtp.starttls.required` hoặc disable hostname verification mà chưa xác định nguyên nhân.

### 10.6. Một profile hoạt động nhưng profile khác lỗi SMTP timeout

Kiểm tra trước hết:

- Endpoint/port tương ứng profile.
- Firewall, outbound network policy và DNS từ **môi trường ứng dụng thực sự chạy**.
- Nếu chạy trong container, hostname `localhost` có chỉ đúng SMTP service không?
- Các timeout mặc định hoặc giá trị `spring.mail.properties.mail.smtp.*timeout` có bị override không?

Một môi trường có thể truy cập SMTP trong khi môi trường khác bị network policy chặn; không nên thay đổi toàn bộ code `JavaMailSender` nếu vấn đề nằm ở đường mạng.

### 10.7. Profile-specific property không có tác dụng

Kiểm tra:

- Tên file có khớp profile active không, ví dụ `application-prod.yml` với `prod`?
- Có lỗi indentation YAML hoặc chính tả tên property không?
- Đối số command line hoặc biến môi trường có ghi đè không?
- Có nhiều file config/import với precedence khác nhau không?
- Sender thật được tạo từ `spring.mail.*` hay từ namespace tùy chỉnh `app.mail.*`?
- Bean có bị tạo trước/được cấp `Session` qua nguồn khác không?

Khi sửa một property, không nên kết luận hiệu lực của nó bằng cách chỉ grep source. Hãy kiểm tra cấu hình mà **Spring context đã resolve** và hành vi thật của bean.

## 11. Thiết kế gửi mail theo môi trường mà service không phải đổi code

Xét hệ thống gửi email xác thực tài khoản:

~~~text
RegistrationService
    |
    v
VerificationMailer (inject JavaMailSender)
    |
    +-- profile=local   -> SMTP sink 127.0.0.1:1025
    |
    +-- profile=test    -> mock/fake hoặc SMTP sink test
    |
    +-- profile=staging -> SMTP account thử nghiệm (STARTTLS)
    |
    +-- profile=prod    -> SMTP account chính thức (STARTTLS hoặc implicit TLS)
~~~

Service có thể giữ logic:

~~~java
public void sendVerification(String recipient, String verificationUrl)
        throws jakarta.mail.MessagingException {

    var message = mailSender.createMimeMessage();
    var helper = new org.springframework.mail.javamail.MimeMessageHelper(
            message, false, "UTF-8");

    helper.setFrom("no-reply@example.com");
    helper.setTo(recipient);
    helper.setSubject("Xác minh tài khoản");
    helper.setText("Vui lòng mở liên kết: " + verificationUrl, false);

    mailSender.send(message);
}
~~~

Trong ví dụ, `no-reply@example.com` và `verificationUrl` là giá trị minh họa. Địa chỉ sender thật phải thuộc miền được phép và nên được cấu hình tập trung theo môi trường; liên kết xác thực cần được tạo an toàn trong tầng nghiệp vụ. Bản thân `VerificationMailer` không cần một khối `if/else` cho từng profile vì cơ chế cấu hình Spring đã chọn sender.

Nếu một môi trường yêu cầu địa chỉ `From` khác, cũng nên inject một property của ứng dụng như `app.mail.from-address` từ cấu hình profile tương ứng. Đổi cả địa chỉ người gửi bằng cấu hình giúp tránh hard-code thông tin giả lập vào production.

Ví dụ:

~~~yaml
# application-local.yml
app:
  mail:
    from-address: dev-notifications@example.test

# application-prod.yml (trong file riêng thực tế)
app:
  mail:
    from-address: ${MAIL_FROM_ADDRESS}
~~~

Trong code:

~~~java
public VerificationMailer(
        JavaMailSender mailSender,
        @org.springframework.beans.factory.annotation.Value(
                "${app.mail.from-address}")
        String fromAddress) {
    this.mailSender = mailSender;
    this.fromAddress = fromAddress;
}
~~~

Ví dụ chỉ minh họa injection của cấu hình; class cần có trường `mailSender` và `fromAddress` tương ứng. Nếu có nhiều địa chỉ gửi, tên hiển thị hoặc chính sách theo loại email, nên tạo một cấu trúc cấu hình mail rõ ràng thay vì nhân bản literal trong nhiều service.

## 12. Nguyên tắc áp dụng trong hệ thống thực tế

| Quyết định thiết kế | Lý do |
| --- | --- |
| Đặt timeout, encoding dùng chung trong `application.yml` | Giảm lặp lại và bảo đảm hành vi nhất quán |
| Đặt endpoint SMTP theo `application-{profile}.yml` hoặc property source ngoài | Mỗi môi trường sử dụng đường gửi phù hợp |
| Không commit credentials thật | Giảm rủi ro lộ tài khoản gửi mail |
| Local/test dùng sink hoặc fake | Kiểm thử được nội dung mà không gửi nhầm khách hàng |
| Staging/prod yêu cầu TLS đúng với provider | Bảo vệ kết nối gửi và xác thực server |
| Service inject `JavaMailSender` | Giữ logic nghiệp vụ độc lập với SMTP host/profile |
| Dùng `@Qualifier` khi có nhiều sender cùng lúc | Chọn đúng tài khoản/provider theo nghiệp vụ |
| Phân biệt submission và delivery | `send(...)` hoàn tất không bảo đảm email đã vào Inbox hoặc được đọc |
| Retry theo trạng thái thật và giới hạn | Tránh gửi trùng hoặc lặp vô hạn khi gặp timeout |
| Kiểm tra effective configuration khi chẩn đoán | Phát hiện override bởi environment/CLI/import |

Spring profiles giải quyết tốt bài toán **cùng một ứng dụng chạy trên nhiều môi trường**. `JavaMailSender` giữ vai trò abstraction chung, còn `spring.mail.*`, placeholder và các profile-specific configuration files quyết định SMTP endpoint, xác thực và TLS phù hợp. Khi cần nhiều sender đồng thời, hãy tạo và inject các bean có tên rõ ràng; khi cần kiểm thử, dùng fake hoặc SMTP sink có kiểm soát. Sự tách biệt này cho phép thay cấu hình của local, test, staging và production mà không phải sửa quy trình tạo `MimeMessage` trong business service.
