# Xây MailService gửi plain text bằng SimpleMailMessage

Bài thực hành này hướng dẫn xây dựng một **MailService** trong ứng dụng **Spring Boot** để gửi email **văn bản thuần (plain text)** bằng `org.springframework.mail.SimpleMailMessage`. Người học sẽ tạo một hợp đồng service rõ ràng, cấu hình `JavaMailSender` qua Spring Boot, thử gửi với một SMTP sandbox cục bộ, kiểm tra nội dung bằng Mockito và hiểu các giới hạn của cách gửi đồng bộ khi triển khai thật.

Kết quả mong muốn:

~~~java
mailService.sendPlainText(
    new PlainTextMailCommand(
        "learner@example.net",
        "Xác nhận đăng ký",
        "Xin chào!\nTài khoản của bạn đã được tạo."));
~~~

Lớp service sẽ chuyển command thành:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom(fromAddress);
message.setTo(command.to());
message.setSubject(command.subject());
message.setText(command.body());
javaMailSender.send(message);
~~~

Đoạn code có vẻ đơn giản, nhưng một thiết kế dùng được cần trả lời các câu hỏi: **From lấy từ đâu? Ai được phép gọi service? Địa chỉ nhận có hợp lệ không? Gửi bị lỗi thì caller biết bằng cách nào? Unit test có gửi email thật không? SMTP accepted có phải delivered không?**

**Giới hạn của bài:** xây service gửi text ngay bằng SMTP, chưa triển khai HTML/attachment, queue hoặc transactional outbox. Các phần mở rộng production được giải thích riêng để không nhầm ví dụ thực hành với bảo đảm exactly-once.

## 1. Tình huống nghiệp vụ và mục tiêu học tập

Giả sử một ứng dụng đặt hàng nhỏ cần gửi email khi khách hàng đăng ký:

~~~text
From: no-reply@example.test
To: learner@example.net
Subject: Xác nhận tài khoản

Xin chào,

Tài khoản của bạn đã được tạo thành công.
Hãy đăng nhập và bắt đầu sử dụng dịch vụ.

Trân trọng,
Đội ngũ hỗ trợ
~~~

Thay vì mỗi `AccountService`, `OrderService` hay `NotificationController` tự dựng email, ta tạo một mail module:

~~~text
Local test API / Business Service
                 |
                 v
        MailService interface
                 |
                 v
    SmtpPlainTextMailService
                 |
        new SimpleMailMessage
                 |
                 v
          JavaMailSender
                 |
                 v
       SMTP sandbox / provider
~~~

Sau bài này cần làm được:

1. Nắm vai trò của `SimpleMailMessage` và khi nào nên chuyển sang `MimeMessageHelper`.
2. Thêm dependency, cấu hình sender, host, port, TLS, credentials và timeout.
3. Viết một `MailService` dễ tái sử dụng, dễ mock và không hard-code secret.
4. Gửi một mail với From, To, Subject, Text.
5. Sử dụng một local SMTP server để quan sát email mà không gửi ra Internet.
6. Viết unit test xác minh chính xác message object.
7. Phân biệt submission success với delivery, phân loại lỗi và nhận biết yêu cầu bảo mật production.

## 2. SimpleMailMessage hoạt động ra sao?

`SimpleMailMessage` là lớp thuộc Spring Mail dùng biểu diễn email text đơn giản. Nó giữ những trường thông dụng mà không yêu cầu caller trực tiếp xử lý MIME multipart.

| Phương thức | Tác dụng | Ví dụ |
| --- | --- | --- |
| `setFrom(String)` | Địa chỉ người gửi | `no-reply@example.test` |
| `setTo(String...)` | Một hoặc nhiều recipients chính | `learner@example.net` |
| `setCc(String...)` | Carbon copy | `manager@example.net` |
| `setBcc(String...)` | Blind carbon copy | `audit@example.net` |
| `setReplyTo(String)` | Địa chỉ nhận phản hồi | `support@example.test` |
| `setSubject(String)` | Subject | `Xác nhận đăng ký` |
| `setText(String)` | Plain-text body | `Xin chào!` |
| `setSentDate(Date)` | Ngày gửi nếu cần đặt rõ | Thường để mail sender quản lý |

Ở bài này, chỉ cần `From`, `To`, `Subject`, `Text`. Những trường khác được giới thiệu ở phần mở rộng.

### 2.1. SimpleMailMessage khác MimeMessage

| Khả năng | SimpleMailMessage | MimeMessage + MimeMessageHelper |
| --- | --- | --- |
| Gửi plain text | Có | Có |
| Gửi HTML thực sự | Không | Có |
| Đính kèm PDF/ảnh | Không | Có |
| Inline image theo Content-ID | Không | Có |
| Điều khiển MIME multipart | Không trực tiếp | Có |
| Dễ học/dễ test | Cao | Cần hiểu MIME |

Lưu ý: 

~~~java
message.setText("<h1>Xin chào</h1>");
~~~

vẫn là **plain text**, không tự biến thành nội dung HTML. Mail client có thể hiển thị nguyên chuỗi `<h1>Xin chào</h1>`. Với HTML, dùng `MimeMessageHelper.setText(plainText, htmlText)` và MIME multipart phù hợp.

### 2.2. MailSender và JavaMailSender

Spring có `MailSender` cho `SimpleMailMessage`. `JavaMailSender` là interface mở rộng hỗ trợ gửi cả `SimpleMailMessage` và `jakarta.mail.internet.MimeMessage`.

Spring Boot starter-mail thường cấu hình một `JavaMailSenderImpl` phù hợp khi `spring.mail.host` được cung cấp, sau đó service inject qua constructor:

~~~java
private final JavaMailSender javaMailSender;
~~~

Không cần tạo SMTP connection hay Jakarta Mail `Session` trực tiếp ở mỗi method nghiệp vụ.

### 2.3. Không dùng chung SimpleMailMessage giữa threads

`SimpleMailMessage` là một object **mutable**. Không khai báo:

~~~java
@Service
public class BadMailService {
    private final SimpleMailMessage shared =
            new SimpleMailMessage();
}
~~~

rồi sửa `To`, `Subject` và `Text` trên cùng object cho nhiều request. Hai threads có thể làm lẫn dữ liệu recipient/body.

**Đúng:** tạo `new SimpleMailMessage()` cho mỗi lần gửi. Service là Spring singleton vẫn an toàn hơn khi chỉ giữ sender/config bất biến.

## 3. Cấu trúc dự án mẫu

Ví dụ dùng Java 17+, Spring Boot 3.x, Spring Framework 6.x và namespace `jakarta.*` cho Jakarta Validation.

~~~text
mail-demo/
  build.gradle
  src/
    main/
      java/com/example/maildemo/
        MailDemoApplication.java
        mail/
          MailService.java
          PlainTextMailCommand.java
          SmtpPlainTextMailService.java
        web/
          SendPlainTextMailRequest.java
          SendPlainTextMailResponse.java
          LocalMailController.java
      resources/
        application.yml
        application-local.yml
        application-prod.yml
    test/
      java/com/example/maildemo/mail/
        SmtpPlainTextMailServiceTest.java
~~~

### 3.1. Dependency Gradle

Trong `build.gradle` của dự án Spring Boot có dependency management thích hợp:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Đây là phần `dependencies`, không phải toàn bộ `build.gradle`. Cấu hình Spring Boot plugin/Java toolchain theo version dự án. Nếu chỉ gọi MailService từ business service không cần REST, `spring-boot-starter-web` có thể bỏ.

### 3.2. Dependency Maven

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Sử dụng Spring Boot parent/BOM đúng version để quản lý phiên bản Spring Mail, Jakarta Mail và các thư viện test. Không trộn `javax.mail` từ dự án cũ với `jakarta.mail` của Spring Boot 3.

### 3.3. Main class

`MailDemoApplication.java`:

~~~java
package com.example.maildemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MailDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MailDemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` quét các component trong `com.example.maildemo` và subpackages. Sau khi cấu hình host SMTP trong profile, Spring Boot thường auto-configure `JavaMailSender`; không phải khởi tạo thủ công ở controller.

## 4. Tách cấu hình local và production

Với dự án này, ta cố ý không đặt SMTP account mặc định ở cấu hình chung. Chạy profile `local` để gửi đến sandbox hoặc `prod` khi đã có hạ tầng thật. Đừng vô ý gửi mail production khi đang thử nghiệm.

### 4.1. application.yml

~~~yaml
spring:
  application:
    name: mail-demo

# Chạy bằng --spring.profiles.active=local hoặc prod.
~~~

### 4.2. application-local.yml

`src/main/resources/application-local.yml`:

~~~yaml
server:
  address: 127.0.0.1

spring:
  mail:
    host: 127.0.0.1
    port: 1025
    protocol: smtp
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "false"
      "[mail.smtp.starttls.enable]": "false"
      "[mail.smtp.starttls.required]": "false"
      "[mail.smtp.connectiontimeout]": "3000"
      "[mail.smtp.timeout]": "5000"
      "[mail.smtp.writetimeout]": "5000"

app:
  mail:
    from: no-reply@example.test
~~~

Mục đích: kết nối SMTP server local như Mailpit trên cổng 1025, không dùng credential và không phát thư thật ra Internet. Plaintext trong sandbox trên máy local là lựa chọn **chỉ dành cho môi trường thử nghiệm cô lập**, không phải cấu hình mẫu cho production.

`server.address=127.0.0.1` giới hạn web endpoint demo trong loopback của máy chạy app. Nếu chạy bằng Docker hoặc remote development, cần xem kỹ network mapping để không vô tình công khai endpoint.

### 4.3. application-prod.yml

`src/main/resources/application-prod.yml`:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    protocol: smtp
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": "true"
      "[mail.smtp.starttls.enable]": "true"
      "[mail.smtp.starttls.required]": "true"
      "[mail.smtp.ssl.checkserveridentity]": "true"
      "[mail.smtp.connectiontimeout]": "5000"
      "[mail.smtp.timeout]": "10000"
      "[mail.smtp.writetimeout]": "10000"

app:
  mail:
    from: ${MAIL_FROM}
~~~

Đây là ví dụ dành cho SMTP submission hỗ trợ **STARTTLS trên port 587**. Với SMTP provider sử dụng **implicit TLS trên port 465**, cần đổi chế độ cho phù hợp như `mail.smtp.ssl.enable=true` và dùng đúng port/hostname theo tài liệu provider.

Các lưu ý:

- `SMTP_HOST` phải là hostname hợp lệ trong chứng chỉ TLS.
- `SMTP_USERNAME` và `SMTP_PASSWORD` lấy từ secret management/environment, không commit vào Git.
- `MAIL_FROM` phải là địa chỉ mà SMTP account được phép sử dụng.
- `mail.smtp.starttls.required=true` ngăn tiếp tục gửi plaintext nếu STARTTLS không dùng được theo policy.
- `mail.smtp.ssl.checkserveridentity=true` yêu cầu kiểm tra hostname.
- Không thêm `mail.smtp.ssl.trust=*` hoặc trust-all manager để né lỗi chứng chỉ.
- Timeouts giúp kiểm soát network stalls; chúng không chứng minh mail chưa được relay nhận khi xảy ra timeout cuối giao dịch.

### 4.4. Bảng cấu hình nhanh

| Property | Mục đích |
| --- | --- |
| `spring.mail.host` | SMTP relay endpoint |
| `spring.mail.port` | Port phù hợp TLS mode |
| `spring.mail.username/password` | Thông tin SMTP authentication |
| `spring.mail.default-encoding` | Charset để xử lý Unicode |
| `mail.smtp.auth` | Yêu cầu SMTP AUTH |
| `mail.smtp.starttls.enable` | Bật STARTTLS |
| `mail.smtp.starttls.required` | Bắt buộc STARTTLS khi cấu hình |
| `mail.smtp.ssl.checkserveridentity` | Xác minh hostname server |
| `mail.smtp.connectiontimeout` | Timeout kết nối |
| `mail.smtp.timeout` | Timeout đọc |
| `mail.smtp.writetimeout` | Timeout ghi |
| `app.mail.from` | From được ứng dụng kiểm soát |

Các thuộc tính JavaMail dùng bracket notation trong YAML để giữ dấu chấm của keys khi Spring Boot bind Map properties.

## 5. Thiết kế PlainTextMailCommand

Business service nên truyền một request **mang ý nghĩa rõ ràng**, không trực tiếp thao tác với mutable message object.

`mail/PlainTextMailCommand.java`:

~~~java
package com.example.maildemo.mail;

import java.util.Objects;

public record PlainTextMailCommand(
        String to,
        String subject,
        String body) {

    public PlainTextMailCommand {
        Objects.requireNonNull(to, "to");
        Objects.requireNonNull(subject, "subject");
        Objects.requireNonNull(body, "body");

        if (to.isBlank()) {
            throw new IllegalArgumentException(
                    "Recipient must not be blank");
        }
        if (subject.isBlank() || subject.length() > 200) {
            throw new IllegalArgumentException(
                    "Invalid subject length");
        }
        if (subject.contains("\r") || subject.contains("\n")) {
            throw new IllegalArgumentException(
                    "Subject must not contain newlines");
        }
        if (body.isBlank() || body.length() > 10000) {
            throw new IllegalArgumentException(
                    "Invalid body length");
        }
    }
}
~~~

Ý nghĩa:

- `record` giúp dữ liệu command bất biến theo các trường String.
- `Objects.requireNonNull` phát hiện lỗi input sớm.
- Subject không chứa CR/LF nhằm tránh đưa newline tùy ý vào vùng header.
- Body được phép chứa newline bình thường.
- `200` ký tự subject và `10000` ký tự body là giới hạn **minh họa của ứng dụng**, không phải giới hạn SMTP chung.

Đây chưa phải validation đầy đủ cho email address. Lớp web sẽ dùng `@Email`, còn caller từ message consumer/business service cần đi qua validation và authorization tương đương.

## 6. Định nghĩa MailService

`mail/MailService.java`:

~~~java
package com.example.maildemo.mail;

public interface MailService {
    void sendPlainText(PlainTextMailCommand command);
}
~~~

Hợp đồng của phương thức:

- Nhận một command hợp lệ từ caller đã được cấp quyền.
- Thực hiện một **lời gọi gửi** qua transport SMTP đã cấu hình.
- Nếu JavaMailSender hoàn tất bình thường, method return.
- Nếu xảy ra `MailException` hoặc lỗi liên quan, caller được nhận lỗi để xử lý rõ ràng.

`void` là lựa chọn hợp lý ở mức ví dụ vì `JavaMailSender.send(SimpleMailMessage)` không trả delivery receipt hay provider message ID. Không nên đổi tên method thành `deliverEmail`, vì **SMTP submitted không đồng nghĩa delivered**.

Nếu sau này triển khai outbox, một interface khác có thể là:

~~~java
EnqueueResult enqueue(MailCommand command);
~~~

và trả job ID với status `PENDING`. Lúc đó enqueue thành công nghĩa là lưu bền vững yêu cầu, chưa phải đã gọi SMTP.

## 7. Triển khai SmtpPlainTextMailService

`mail/SmtpPlainTextMailService.java`:

~~~java
package com.example.maildemo.mail;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class SmtpPlainTextMailService implements MailService {

    private final JavaMailSender javaMailSender;
    private final String fromAddress;

    public SmtpPlainTextMailService(
            JavaMailSender javaMailSender,
            @Value("${app.mail.from}") String fromAddress) {

        this.javaMailSender = Objects.requireNonNull(
                javaMailSender, "javaMailSender");

        if (fromAddress == null || fromAddress.isBlank()) {
            throw new IllegalArgumentException(
                    "app.mail.from must be configured");
        }
        this.fromAddress = fromAddress;
    }

    @Override
    public void sendPlainText(PlainTextMailCommand command) {
        Objects.requireNonNull(command, "command");

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(fromAddress);
        message.setTo(command.to());
        message.setSubject(command.subject());
        message.setText(command.body());

        javaMailSender.send(message);
    }
}
~~~

Đây là phần cốt lõi của bài thực hành. Ta không tự tạo Jakarta Mail `Session`, không chứa SMTP credential trong service và không dùng một `SimpleMailMessage` mutable làm field singleton.

### 7.1. Giải thích từng bước

1. `@Service` đăng ký bean Spring.
2. Inject `JavaMailSender` qua constructor, giúp thay bằng mock trong unit test.
3. Inject `app.mail.from` từ cấu hình đã tách theo profile.
4. Kiểm tra From không rỗng từ lúc tạo bean.
5. Mỗi lần gọi tạo một `SimpleMailMessage` mới.
6. `setFrom` dùng sender identity do server quản lý.
7. `setTo` dùng recipient của command đã validate.
8. `setSubject` và `setText` đặt tiêu đề/nội dung text.
9. `javaMailSender.send(message)` yêu cầu transport thực hiện SMTP submission.

### 7.2. Vì sao không cho caller tự đặt From?

Trong ứng dụng thật, một REST caller không nên được tự chọn:

~~~json
{
  "from": "ceo@unrelated-domain.example",
  "to": "someone@example.org",
  "subject": "Important",
  "body": "..."
}
~~~

Điều này có thể gây spoofing hoặc bị SMTP provider từ chối vì sender chưa được xác minh. Nếu ứng dụng có nhiều địa chỉ gửi hợp lệ, hãy dùng một **sender profile** hoặc cấu hình allowlist được phân quyền, không tin mọi địa chỉ From từ request body.

### 7.3. Vì sao không catch rồi nuốt exception?

Một cách làm sai:

~~~java
try {
    javaMailSender.send(message);
} catch (Exception ex) {
    logger.warn("Email failed");
}
// Caller vẫn tưởng thao tác thành công.
~~~

Khi service nuốt exception và return bình thường, caller không biết SMTP submission bị lỗi. Trong bài, ta để `MailException` được truyền lên. Ở production, tầng điều phối xử lý retry, alert và trạng thái job có chủ đích.

### 7.4. Không log cả email

Không log nguyên object `SimpleMailMessage` nếu nó chứa địa chỉ người nhận, OTP, token reset hoặc dữ liệu hóa đơn. Ưu tiên metadata tối thiểu như mail type, sender profile, correlation ID và error class. Password/API token tuyệt đối không ghi log.

## 8. Thêm REST endpoint thực hành chỉ ở local

Để thao tác dễ quan sát, tạo một controller **chỉ hoạt động khi profile `local` được bật**. Endpoint này là công cụ học tập, **không phải public mail API an toàn**. Một endpoint cho phép người ngoài gửi tới recipient tùy ý mà không có authentication và rate limit có thể biến thành công cụ spam/open relay.

### 8.1. Request DTO

`web/SendPlainTextMailRequest.java`:

~~~java
package com.example.maildemo.web;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record SendPlainTextMailRequest(
        @NotBlank @Email
        String to,

        @NotBlank @Size(max = 200)
        String subject,

        @NotBlank @Size(max = 10000)
        String body) {
}
~~~

`@NotBlank` đảm bảo trường có nội dung; `@Email` kiểm tra dạng địa chỉ; `@Size` giới hạn dữ liệu đầu vào. Validator không chứng minh mailbox có tồn tại và không thay thế authorization/anti-abuse.

### 8.2. Response DTO

`web/SendPlainTextMailResponse.java`:

~~~java
package com.example.maildemo.web;

public record SendPlainTextMailResponse(
        String status) {
}
~~~

### 8.3. Controller

`web/LocalMailController.java`:

~~~java
package com.example.maildemo.web;

import com.example.maildemo.mail.MailService;
import com.example.maildemo.mail.PlainTextMailCommand;
import jakarta.validation.Valid;

import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@Profile("local")
@RequestMapping("/api/local/mail")
public class LocalMailController {

    private final MailService mailService;

    public LocalMailController(MailService mailService) {
        this.mailService = mailService;
    }

    @PostMapping("/plain")
    public ResponseEntity<SendPlainTextMailResponse> send(
            @Valid @RequestBody SendPlainTextMailRequest request) {

        PlainTextMailCommand command =
                new PlainTextMailCommand(
                        request.to(),
                        request.subject(),
                        request.body());

        mailService.sendPlainText(command);

        return ResponseEntity.ok(
                new SendPlainTextMailResponse(
                        "SUBMITTED_TO_SMTP"));
    }
}
~~~

Nếu `JavaMailSender.send(...)` ném lỗi, method không trả response thành công. HTTP response khác cần được định nghĩa bởi exception mapper/server policy.

Tên `SUBMITTED_TO_SMTP` trong demo thể hiện rằng lời gọi transport **trả về bình thường**; nó không chứng minh email đã được giao vào Inbox hoặc đã đọc. Với bất kỳ API production nào, cần định nghĩa rõ trạng thái submission/queued/delivered.

### 8.4. Vì sao chỉ bật ở local?

`@Profile("local")` làm controller không được đăng ký nếu chỉ chạy profile `prod`. Trong `application-local.yml`, `server.address=127.0.0.1` giới hạn listener trên loopback host. Tuy nhiên, đó **không phải** cơ chế authorization đầy đủ. Không chạy đồng thời profile `local` và `prod` rồi công khai endpoint.

Trong ứng dụng lớn, business service có thể gọi `MailService` trực tiếp sau khi đã xác thực tác vụ. Nếu cần một endpoint gửi mail ở production, phải thêm authentication, authorization, tenant isolation, allowlist/destination policy, rate limiting, audit và idempotency.

## 9. Gửi thử qua Mailpit ở máy local

Để tránh dùng tài khoản email thật, chạy một **SMTP sandbox**. Mailpit là một lựa chọn phổ biến; ví dụ nó có SMTP listener port 1025 và giao diện web port 8025.

Nếu máy có Docker:

~~~bash
docker run --rm --name mailpit-demo \
  -p 127.0.0.1:1025:1025 \
  -p 127.0.0.1:8025:8025 \
  axllent/mailpit:latest
~~~

Đây chỉ là **lệnh hướng dẫn người học**, không phải lệnh được thực thi khi soạn bài. Đối chiếu image/port với tài liệu Mailpit hiện hành. Các port được map lên loopback để giảm nguy cơ lộ SMTP sandbox ra mạng ngoài.

Giao diện sandbox (theo ví dụ cấu hình):

~~~text
http://127.0.0.1:8025
~~~

### 9.1. Chạy ứng dụng với profile local

Với Gradle:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=local'
~~~

Với Maven:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=local
~~~

Nếu app dùng port HTTP 8080 mặc định, endpoint sẽ ở `http://127.0.0.1:8080/api/local/mail/plain`.

### 9.2. Gửi HTTP request

~~~bash
curl -i -X POST http://127.0.0.1:8080/api/local/mail/plain \
  -H "Content-Type: application/json" \
  -d '{
    "to": "learner@example.net",
    "subject": "Thử nghiệm SimpleMailMessage",
    "body": "Xin chào,\nĐây là email plain text từ Spring Boot."
  }'
~~~

Nếu sandbox nhận email và sender không gặp lỗi, response demo có thể là:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"SUBMITTED_TO_SMTP"}
~~~

Mở `http://127.0.0.1:8025` để xem một mail mới đến. Với Mailpit, recipient trong test không cần tồn tại ngoài Internet; mailbox sandbox chỉ giữ dữ liệu thử nghiệm để kiểm tra.

### 9.3. Những gì cần quan sát

1. `From` có đúng `no-reply@example.test` không?
2. `To` có đúng `learner@example.net` không?
3. Subject có đúng tiếng Việt và dấu không?
4. Body có giữ dấu và xuống dòng không?
5. Mail có phải plain text, không phải HTML part không?
6. Có một email cho một POST, không xuất hiện nhiều message bất thường không?

Chỉ quan sát ở local sandbox, không gửi nội dung thử nghiệm tới mailbox người dùng thật nếu chưa được phép.

### 9.4. Chạy trong Docker khác chạy trên host

Nếu Spring app cũng ở container:

~~~text
127.0.0.1 trong Spring container = chính container Spring
127.0.0.1 trên host             = host machine
~~~

Vì vậy `spring.mail.host=127.0.0.1` trong container Spring không tự trỏ đến container Mailpit. Cần cấu hình cùng Docker network và hostname service phù hợp, ví dụ `mailpit` trong Compose network (nếu service thực sự có tên đó). Không mở port SMTP sandbox ra Internet để giải quyết nhầm network.

### 9.5. Kịch bản lỗi nhanh

Tắt Mailpit và gọi lại endpoint. `JavaMailSender.send(...)` thường phát lỗi kết nối thay vì hoàn tất. Đừng sửa bằng cách bỏ qua exception rồi vẫn trả `SUBMITTED_TO_SMTP`.

**Sau đây là phần kiểm thử tự động, xử lý lỗi và mở rộng production cho service đã tạo.**

## 10. Unit test MailService bằng JUnit và Mockito

Vì `SmtpPlainTextMailService` nhận `JavaMailSender` qua constructor, có thể thay sender thật bằng Mockito mock. Đây là lợi ích thiết kế quan trọng: **kiểm tra logic tạo email mà không kết nối mạng và không gửi thư thật**.

`src/test/java/com/example/maildemo/mail/SmtpPlainTextMailServiceTest.java`:

~~~java
package com.example.maildemo.mail;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.doThrow;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.ArgumentCaptor;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.mail.MailException;
import org.springframework.mail.MailSendException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

@ExtendWith(MockitoExtension.class)
class SmtpPlainTextMailServiceTest {

    @Mock
    private JavaMailSender javaMailSender;

    @Test
    void sendsPlainTextWithExpectedFields() {
        MailService service =
                new SmtpPlainTextMailService(
                        javaMailSender,
                        "no-reply@example.test");

        service.sendPlainText(
                new PlainTextMailCommand(
                        "learner@example.net",
                        "Thông báo",
                        "Xin chào!\nĐây là nội dung text."));

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(
                        SimpleMailMessage.class);

        verify(javaMailSender).send(captor.capture());

        SimpleMailMessage actual = captor.getValue();

        assertEquals(
                "no-reply@example.test",
                actual.getFrom());
        assertArrayEquals(
                new String[]{"learner@example.net"},
                actual.getTo());
        assertEquals(
                "Thông báo",
                actual.getSubject());
        assertEquals(
                "Xin chào!\nĐây là nội dung text.",
                actual.getText());
    }

    @Test
    void propagatesMailException() {
        MailService service =
                new SmtpPlainTextMailService(
                        javaMailSender,
                        "no-reply@example.test");

        doThrow(new MailSendException(
                "SMTP sandbox unavailable"))
                .when(javaMailSender)
                .send(any(SimpleMailMessage.class));

        assertThrows(
                MailException.class,
                () -> service.sendPlainText(
                        new PlainTextMailCommand(
                                "learner@example.net",
                                "Thông báo lỗi",
                                "Nội dung thử nghiệm")));
    }
}
~~~

### 10.1. Vì sao dùng ArgumentCaptor?

`verify(javaMailSender).send(captor.capture())` lấy ra chính đối tượng `SimpleMailMessage` được truyền vào mock. Sau đó test xác minh:

- `From` khớp cấu hình;
- `To` khớp command;
- `Subject` đúng;
- `Text` được giữ nguyên, bao gồm Unicode và dấu xuống dòng;
- `send(...)` được gọi;
- không có SMTP connection thật.

Điều này chính xác hơn một test chỉ gọi service rồi assert “không ném exception”: mock mặc định không ném lỗi và vẫn có thể che việc tạo sai recipient.

### 10.2. Kiểm thử subject có newline

Bổ sung vào test cho command:

~~~java
@Test
void rejectsSubjectWithLineBreaks() {
    assertThrows(
            IllegalArgumentException.class,
            () -> new PlainTextMailCommand(
                    "learner@example.net",
                    "Hello\r\nBcc: hidden@example.org",
                    "Nội dung"));
}
~~~

Kỳ vọng constructor từ chối trước khi SMTP sender được gọi. Body vẫn được phép chứa newline thông thường.

### 10.3. Kiểm thử hai lần gửi độc lập

Đối với service singleton, cần xác minh hai commands liên tiếp không trộn dữ liệu:

~~~java
MailService service =
        new SmtpPlainTextMailService(
                javaMailSender, "no-reply@example.test");

service.sendPlainText(
        new PlainTextMailCommand(
                "first@example.net", "First", "Body A"));
service.sendPlainText(
        new PlainTextMailCommand(
                "second@example.net", "Second", "Body B"));
~~~

Trong test, capture cả hai invocations, kiểm tra mỗi message chứa đúng dữ liệu và hai objects không cùng reference. Đây là phép kiểm tra hữu ích để phát hiện anti-pattern dùng một `SimpleMailMessage` field chung.

### 10.4. Những điều unit test không chứng minh

Unit test không xác nhận:

- SMTP host/port đang hoạt động;
- STARTTLS, certificate chain và SMTP AUTH đúng;
- text được encode đúng khi chuyển lên wire format;
- provider đã chấp nhận email;
- message tới mailbox người nhận.

Cần integration test để bao phủ các tầng còn lại.

## 11. Kiểm thử tích hợp với SMTP server giả lập

Một integration test có thể chạy Mailpit/GreenMail hoặc SMTP sandbox container trong môi trường kiểm thử. Luồng:

~~~text
Start isolated SMTP test server
          |
          v
Configure JavaMailSender host/port
          |
          v
Call MailService.sendPlainText(...)
          |
          v
Test server receives message
          |
          v
Assert From/To/Subject/Text/charset
          |
          v
Cleanup server/mailbox/fixtures
~~~

### 11.1. Các trường hợp tích hợp quan trọng

| Kịch bản | Điều cần xác minh |
| --- | --- |
| Email đơn giản | SMTP server nhận đúng một message |
| Tiếng Việt | Subject/body được decode đúng UTF-8 |
| Body nhiều dòng | Newlines được bảo toàn theo MIME |
| SMTP server tắt | Service ném `MailException` hoặc lỗi phù hợp |
| Wrong SMTP password | Lỗi authentication được phân loại |
| Invalid From | Provider từ chối theo policy, không trả thành công |
| STARTTLS required nhưng server không hỗ trợ | Không fallback plaintext |
| Gửi nhiều messages | Không lẫn recipients/body giữa các lần gửi |
| Timeout/network reset | Không khẳng định chắc email chưa được nhận |

### 11.2. Chờ kết quả bằng điều kiện

Với test bất đồng bộ, tránh giả định email sẽ có ngay sau `Thread.sleep(1000)`. Nên chờ có giới hạn dựa trên điều kiện thực tế như “mailbox có message mang test correlation ID”, sử dụng Awaitility hoặc cơ chế polling test phù hợp.

Ngay cả khi bài này gửi đồng bộ, việc tách SMTP test server vào container có thể khiến việc đọc mailbox qua API xảy ra trễ; test nên xử lý điều đó có timeout hữu hạn.

### 11.3. Không dùng SMTP thật trong CI

CI không nên phụ thuộc tài khoản cá nhân hoặc gửi mail tới người dùng thật. Dùng sandbox có lifecycle rõ, fixture recipient riêng và cleanup. Nếu thực sự cần provider E2E test, dùng tài khoản sandbox/tenant được phép và tách khỏi pipeline unit test.

### 11.4. Mục tiêu của ba tầng kiểm thử

1. **Unit test:** mock `JavaMailSender`, xác minh việc tạo `SimpleMailMessage`.
2. **Integration test:** SMTP fake server, xác minh protocol và MIME/encoding.
3. **Provider test:** xác minh credentials, TLS, sender permissions, provider policy và delivery events theo tài liệu provider.

Một test không thay thế cả ba loại.

## 12. Ngoại lệ Spring Mail và cách xử lý

`JavaMailSender.send(...)` có thể ném các subclass của `org.springframework.mail.MailException`. Nguyên nhân từ Jakarta Mail/SMTP thường nằm sâu trong nested exception.

| Loại lỗi/dấu hiệu | Ý nghĩa thường gặp | Gợi ý xử lý |
| --- | --- | --- |
| `MailAuthenticationException` | SMTP AUTH thất bại | Credential/OAuth/account permissions |
| `MailSendException` | Lỗi phát sinh khi gửi | Kiểm tra nested cause và per-message failures |
| `MailParseException` | Không chuẩn bị/parse được message | Xem recipient, header, MIME/input |
| `MailPreparationException` | Lỗi trong quá trình chuẩn bị message theo API liên quan | Sửa dữ liệu/code chuẩn bị |
| `ConnectException` | TCP bị từ chối | Host/port/service chưa mở |
| `SocketTimeoutException` | Kết nối/đọc/ghi quá thời hạn | Network/provider, outcome có thể uncertain |
| `SSLHandshakeException` | Lỗi TLS chain/hostname/protocol | Sửa certificate/TLS mode/truststore |
| SMTP `535` | Xác thực không thành công | SMTP account/OAuth |
| SMTP `550`, `553` | Thường liên quan policy/recipient/sender | Phân loại theo phản hồi provider |

Không dùng tên exception lớp ngoài để suy luận chắc chắn email chưa gửi. Ví dụ một timeout xảy ra sau khi relay nhận DATA nhưng trước khi app đọc phản hồi cuối có thể cho trạng thái không chắc chắn.

### 12.1. Một handler không nên giấu lỗi

Nếu tầng web muốn chuẩn hóa phản hồi:

~~~java
package com.example.maildemo.web;

import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.mail.MailException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@Profile("local")
@RestControllerAdvice
public class LocalMailErrorHandler {

    @ExceptionHandler(MailException.class)
    public ResponseEntity<String> mailFailure(
            MailException exception) {
        // Không trả raw exception/SMTP credentials cho client.
        return ResponseEntity.status(
                HttpStatus.BAD_GATEWAY)
                .body("SMTP submission was not confirmed");
    }
}
~~~

Đây chỉ là một **error mapper minh họa**. `502 Bad Gateway` ở đây được dùng vì local API đóng vai trò phía trước SMTP service; một API production có thể chọn status khác theo contract. Chữ “not confirmed” cố ý **không khẳng định “definitely not sent”**.

Khi API production hỗ trợ retry và kết quả có thể uncertain, cần job ID, idempotency key, trạng thái lưu bền vững và cách truy vấn/reconciliation; không chỉ trả 502 rồi cho client retry vô điều kiện.

### 12.2. Không retry mọi lỗi theo cùng một cách

- Credential sai: sửa cấu hình, không retry hàng trăm lần mỗi giây.
- Certificate không tin: sửa CA/hostname/TLS, không bật trust-all.
- SMTP 4xx tạm thời: có thể retry với exponential backoff/jitter.
- Recipient bị từ chối vĩnh viễn: không retry vô hạn.
- Timeout sau submission: xử lý như kết quả có thể không chắc chắn.

Các quy tắc retry nên nằm ở tầng điều phối bền vững khi ứng dụng đã yêu cầu reliability, không lặp vô hạn trong một request HTTP.

### 12.3. Phân biệt SUBMITTED với DELIVERED

~~~text
JavaMailSender.send(message) returns normally
      |
      v
SMTP relay accepted the submission
      |
      v
Provider processing
      |
      +-- delivered to downstream mail server
      +-- deferred
      +-- bounced
      +-- filtered/rejected later
~~~

Vì vậy response demo `SUBMITTED_TO_SMTP` chỉ nói đến mốc transport call, **không bảo đảm thư tới Inbox**. Muốn quan sát delivery/bounce/complaint cần provider events hoặc hạ tầng mail theo contract phù hợp.

## 13. Gửi tiếng Việt và xử lý charset

Văn bản thuần có thể chứa Unicode:

~~~java
String subject = "Xác nhận đăng ký thành công";
String body =
        "Xin chào,\n"
        + "Tài khoản của bạn đã được kích hoạt.\n"
        + "Trân trọng.";

mailService.sendPlainText(
        new PlainTextMailCommand(
                "learner@example.net",
                subject,
                body));
~~~

`SimpleMailMessage` giữ Java `String`. `JavaMailSenderImpl` và Jakarta Mail sẽ chuẩn bị MIME headers/body; cấu hình `spring.mail.default-encoding=UTF-8` giúp định nghĩa charset mặc định theo ứng dụng.

### 13.1. Khi tiếng Việt bị lỗi

Kiểm tra từ đầu đến cuối:

1. File Java/YAML được lưu UTF-8.
2. HTTP request body gửi charset phù hợp.
3. Request DTO nhận đúng Java `String` (không có `?`/mojibake từ đầu).
4. `spring.mail.default-encoding` đúng.
5. SMTP test mailbox decode đúng MIME charset.
6. Mail client cuối có xử lý MIME chuẩn.

Không sửa bằng cách liên tục đổi String sang bytes rồi convert ngược với charset khác. Điều đó có thể làm hỏng dữ liệu trước khi sender xử lý.

### 13.2. Text block nhiều dòng

Với Java 17:

~~~java
String body = """
        Xin chào,

        Tài khoản của bạn đã được kích hoạt.
        Nếu cần trợ giúp, vui lòng liên hệ hỗ trợ.

        Trân trọng,
        Đội ngũ hỗ trợ
        """;
~~~

Text block giúp giữ body dễ đọc. Kiểm tra newline và indentation thực tế vì Java text blocks có quy tắc xử lý whitespace. Các email plain text có thể dùng dòng trống, dấu đầu dòng hoặc URL, nhưng không hỗ trợ nút bấm/định dạng HTML.

## 14. Mở rộng Cc, Bcc và Reply-To

Khi cần thêm recipients, `SimpleMailMessage` hỗ trợ:

~~~java
SimpleMailMessage message = new SimpleMailMessage();

message.setFrom("no-reply@example.test");
message.setTo("customer@example.net");
message.setCc("team@example.net");
message.setBcc("audit@example.net");
message.setReplyTo("support@example.test");
message.setSubject("Cập nhật đơn hàng");
message.setText(
        "Xin chào,\nĐơn hàng của bạn đã được xác nhận.");

javaMailSender.send(message);
~~~

Trong đó:

- `To` là recipients chính.
- `Cc` thường hiển thị cho những recipients khác.
- `Bcc` gửi tới recipients ẩn khỏi danh sách recipients thông thường; không dùng như cơ chế bulk-mail tùy tiện.
- `Reply-To` cho biết địa chỉ mail client sử dụng khi người dùng trả lời, có thể khác From.

### 14.1. Vẫn phải validate và authorize

Nếu controller nhận tùy ý `Cc`, `Bcc`, `Reply-To`, phải có quy tắc quyền gửi, allowlist, giới hạn số recipients và kiểm tra header. Không đưa địa chỉ của tenant khác vào cùng email, vì dễ lộ dữ liệu cá nhân.

### 14.2. Multi-recipient và partial success

Một message có nhiều To/Cc/Bcc có thể được SMTP server chấp nhận cho một số recipients nhưng từ chối người khác. Nếu retry toàn bộ message, những người đã được chấp nhận có nguy cơ nhận trùng.

Với yêu cầu theo dõi delivery/bounce riêng từng người, mô hình **một logical job trên mỗi recipient** hoặc bảng recipient-outcome thường dễ kiểm soát hơn.

### 14.3. Không đặt HTML trong setText

`message.setText("<strong>Xin chào</strong>")` vẫn là plain text. Khi cần HTML, attachment, inline logo hoặc multipart/alternative, chuyển sang `MimeMessageHelper`. Đừng cố thay custom MIME header để biến `SimpleMailMessage` thành HTML message.

## 15. Những giới hạn của gửi đồng bộ

Với implementation hiện tại:

~~~text
HTTP request
   -> LocalMailController
      -> MailService
         -> JavaMailSender.send(...)
   -> HTTP response sau khi transport return
~~~

Đặc tính này phù hợp khi học hoặc cho chức năng nội bộ nhỏ, nhưng ở production có các rủi ro:

- SMTP chậm làm HTTP latency tăng.
- Provider outage ảnh hưởng trực tiếp business request.
- Client timeout và retry có thể gửi trùng.
- Nhiều concurrent requests giữ thread và network resources.
- Process crash làm mất những yêu cầu chưa có persistent record.

### 15.1. Tránh gửi trực tiếp bên trong business transaction

Ví dụ:

~~~java
@Transactional
public void confirmOrder(UUID orderId) {
    orderRepository.confirm(orderId);
    mailService.sendPlainText(
            new PlainTextMailCommand(
                    "customer@example.net",
                    "Đơn hàng đã xác nhận",
                    "Cảm ơn bạn đã đặt hàng."));
}
~~~

SMTP không tham gia database transaction. Nếu SMTP accepted rồi DB rollback, email vẫn có thể được gửi; nếu DB commit mà process chết trước send, email có thể mất.

Khi cần đảm bảo không mất yêu cầu, dùng **transactional outbox**:

~~~mermaid
flowchart LR
    A["Business event"] --> B["DB transaction"]
    B --> C["Business data"]
    B --> D["Mail outbox PENDING"]
    D --> E["Background worker"]
    E --> F["MailService"]
    F --> G["SMTP relay"]
~~~

Trong cùng business DB transaction, lưu `mail_outbox` bên cạnh cập nhật nghiệp vụ. Worker sau commit lấy job và gọi service này, ghi retry/state. Nếu outbox và business data nằm ở hai databases khác nhau, cần một kiến trúc atomicity phù hợp; `@Transactional` đơn giản không tự đồng bộ hai nguồn.

### 15.2. Message key và idempotency

Nếu một event được giao lại:

~~~text
OrderConfirmed(eventId=evt-123)
   -> messageKey=order-confirmation:evt-123:recipient-9
~~~

cần giữ cùng message key ở mọi lần redelivery. Database có thể đặt `UNIQUE(tenant_id, message_key)` để tránh tạo trùng logical mail job.

Nhưng **một unique key không bảo đảm exactly-once SMTP**: worker có thể bị crash sau khi SMTP server accepted nhưng trước khi commit trạng thái `SUBMITTED`. Retry vẫn có thể khiến server nhận hai email. Cần attempt tracking, `UNKNOWN`/reconciliation và policy theo mail type.

### 15.3. Scheduler và retry

Một outbox worker có thể lưu:

~~~text
jobId
messageKey
mailType
recipient
payloadRef
state=PENDING|RETRY_WAIT|SUBMITTED|FAILED_FINAL|UNKNOWN
scheduledAt
nextAttemptAt
attemptCount
~~~

Worker claim job đến hạn bằng lock/lease có kiểm soát, gọi service rồi lưu kết quả. Lỗi 4xx tạm thời có thể retry với backoff; lỗi credential/TLS cấu hình thường cần alert và sửa root cause; job OTP đã hết hạn không nên gửi sau outage.

Đây là **mở rộng kiến trúc**, không phải tính năng mà `SimpleMailMessage` tự cung cấp.

## 16. Bảo mật khi đưa MailService vào ứng dụng thật

Một service gửi email là một khả năng có thể bị lạm dụng nếu không giới hạn quyền.

### 16.1. Tránh open relay

Một API public như:

~~~http
POST /api/mail
{"to":"anyone@example.net","subject":"...","body":"..."}
~~~

nếu không có authentication/rate limits có thể bị dùng để gửi spam, phishing hoặc lạm dụng quota. Trong bài này, controller chỉ dành cho profile local. Khi triển khai thật:

- xác thực người gọi;
- authorize loại email, tenant và sender profile;
- kiểm soát recipients và destination policy;
- rate-limit theo principal/tenant/use case;
- giới hạn kích thước request;
- ghi audit tối thiểu;
- sử dụng idempotency khi request có thể retry;
- không cho thay đổi From/Reply-To ngoài các địa chỉ được phép.

### 16.2. Bảo vệ SMTP credentials

Không viết:

~~~yaml
spring:
  mail:
    username: real-smtp-user
    password: real-smtp-password
~~~

trong repository. Lấy thông tin từ secret manager hoặc cơ chế inject an toàn, giới hạn quyền secret, có quy trình rotation. Không in password vào exception log hay debug transcript.

### 16.3. TLS verification phải được giữ

Với SMTP provider thật, dùng host/port/TLS mode chính xác và kiểm tra certificate chain/hostname. Không đặt `mail.smtp.ssl.trust=*` hoặc trust-all manager để né `PKIX path building failed`.

Local sandbox plaintext trên loopback là một trường hợp học tập đã cô lập, **không phải** tiền lệ để production dùng plaintext.

### 16.4. Không log body và token

Email có thể chứa:

- OTP;
- reset-password token;
- invoice/order data;
- recipient address;
- thông tin tài khoản.

Log chỉ nên chứa metadata cần thiết như mail type, sender profile, correlation ID, error class và status đã được kiểm soát quyền. Không dùng recipient address, subject, body hoặc token làm metric labels.

## 17. Quan sát và metrics

Khi tích hợp vào môi trường có nhiều requests, nên instrument các chỉ số:

| Metric đề xuất | Ý nghĩa |
| --- | --- |
| `mail_submission_attempts_total` | Số lời gọi SMTP/API |
| `mail_submission_duration_seconds` | Thời gian một attempt |
| `mail_submission_errors_total` | Lỗi transport theo nhóm |
| `mail_jobs_created_total` | Logical jobs nếu có outbox |
| `mail_outbox_pending` | Số jobs đang chờ |
| `mail_outbox_oldest_pending_age_seconds` | Tuổi backlog |
| `mail_retry_scheduled_total` | Lần retry được lên lịch |

Đây là tên metrics gợi ý do ứng dụng tự instrument; `spring-boot-starter-mail` không tự xuất tất cả chúng.

### 17.1. Đếm đúng đơn vị

~~~text
1 logical mail job
3 SMTP attempts
1 accepted submission
~~~

Số jobs là 1, attempts là 3, submission accepted là 1. Đừng gắn nhãn `delivered` cho một lời gọi `JavaMailSender.send(...)` return bình thường.

### 17.2. Nhãn phải có cardinality giới hạn

Có thể dùng:

~~~text
sender_profile=tx_primary|tx_backup
mail_type=order_confirmation|otp|invoice|newsletter
result=submitted|exception
error_class=auth|tls|network|recipient|unknown
~~~

Không dùng `recipient`, `messageKey`, `subject` hoặc raw exception text làm metrics labels.

### 17.3. Alert thiết yếu

- Authentication failures tăng liên tục.
- TLS handshake lỗi sau certificate rotation.
- SMTP timeouts làm backlog tăng.
- Provider throttling khiến retry nhiều.
- Một loại mail quan trọng như OTP vượt thời hạn chờ.
- Lưu lượng đột ngột tăng có thể là abuse.

Alert cần dùng số liệu và ngưỡng theo hoàn cảnh; không page chỉ vì một request thử nghiệm bị từ chối.

## 18. Bảng xử lý lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Không inject được `JavaMailSender` | Thiếu starter, host chưa cấu hình/profile sai | Kiểm tra dependency và profile |
| `Connection refused` | SMTP sandbox chưa chạy, sai port hoặc network | Xác minh host/port từ nơi app chạy |
| `Connect timed out` | Firewall/route/host sai | Kiểm tra TCP connectivity |
| `MailAuthenticationException` | Credential/OAuth hoặc SMTP AUTH policy | Kiểm tra account và auth mechanism |
| `535 Authentication failed` | Provider không chấp nhận thông tin đăng nhập | Sửa credential/policy, không tắt TLS |
| `PKIX path building failed` | JVM không tin CA chain | Kiểm tra truststore/chain/hostname |
| Hostname mismatch | Certificate SAN không khớp SMTP host | Dùng endpoint/cert hợp lệ |
| STARTTLS required nhưng server không hỗ trợ | Sai host/port/proxy | Chọn đúng SMTP endpoint |
| `Unsupported or unrecognized SSL message` | Sai implicit TLS/STARTTLS mode | Phân biệt port 465 và 587 |
| SMTP `550/553` | From hoặc recipient bị reject theo provider policy | Xác minh sender identity/recipient |
| Body tiếng Việt lỗi | Encoding không nhất quán | Kiểm tra UTF-8 và MIME charset |
| Hiển thị HTML tags nguyên văn | Dùng `SimpleMailMessage` cho HTML | Chuyển `MimeMessageHelper` |
| API 404 trong prod | `LocalMailController` chỉ bật ở local | Đúng thiết kế; không bật local trên prod |
| API 400 | DTO/command validation failed | Sửa request |
| Email gửi nhưng không đến Inbox | Provider filtering/delivery/bounce | Theo dõi delivery events, không suy từ submission |

### 18.1. Một nguyên nhân phổ biến: localhost trong container

Nếu Mailpit là container A, Spring Boot là container B, `127.0.0.1` trong B không trỏ sang A. Dùng Docker network/service hostname phù hợp. Tránh lạm dụng host networking hoặc mở SMTP port công khai chỉ để hết lỗi kết nối.

### 18.2. Không bỏ qua nguyên nhân sâu

`MailSendException` có thể bọc `MessagingException`, `SocketException` hoặc `SSLHandshakeException`. Xem nested cause để phân biệt lỗi auth/TLS/network/message; không retry mù mọi lỗi bằng cùng một chính sách.

## 19. Bài tập thực hành mở rộng

### Bài 1: Gửi nội dung tiếng Việt nhiều dòng

Viết một email có subject và body:

~~~text
Subject: Thông báo kích hoạt tài khoản

Xin chào,

Tài khoản của bạn đã được kích hoạt thành công.
Bạn có thể đăng nhập và bắt đầu sử dụng dịch vụ.

Trân trọng,
Đội ngũ hỗ trợ
~~~

Quan sát trong Mailpit xem dấu tiếng Việt, dấu xuống dòng và subject có đúng.

### Bài 2: Thêm Reply-To qua cấu hình

Bổ sung `app.mail.reply-to`, inject vào service và gọi `message.setReplyTo(...)` khi được phép. Kiểm tra bằng Mockito `getReplyTo()`. Không cho client tự đặt giá trị tùy ý.

### Bài 3: Gửi Cc và Bcc

Mở rộng command để nhận các recipients phụ được validate/authorize. Dùng `setCc(...)` và `setBcc(...)`, capture message trong unit test. Cân nhắc privacy và partial SMTP acceptance trước khi dùng nhiều recipients ở production.

### Bài 4: Từ chối subject có CR/LF

Thử gửi subject:

~~~text
Hello\r\nBcc: hidden@example.org
~~~

Kỳ vọng constructor từ chối, không gọi SMTP. Body vẫn được chứa newline.

### Bài 5: Mô phỏng SMTP outage

Dừng Mailpit, gọi service và quan sát `MailException`. Không để API trả `SUBMITTED_TO_SMTP` khi lời gọi transport thất bại. Xác minh log không chứa credential hoặc nội dung nhạy cảm.

### Bài 6: Hai lần gửi liên tiếp

Gửi cho hai recipients khác nhau trong cùng test. Capture messages và xác minh không lẫn To/Subject/Text; cả hai là object riêng.

### Bài 7: Thiết kế outbox thay cho synchronous sending

Tạo bảng `mail_outbox` với `id`, `message_key`, `recipient`, `payload_ref`, `status`, `attempt_count` và `next_attempt_at`. Ghi outbox cùng business transaction, worker claim/schedule attempts rồi gọi `MailService`. Thêm unique constraint để broker redelivery không tạo duplicate logical job.

### Bài 8: Chuyển HTML bằng MimeMessageHelper

Thử `setText("<h1>Xin chào</h1>")` và xem nguyên markup ở plain text. Sau đó xây một service khác dùng `MimeMessageHelper` với text/plain và text/html đúng MIME, không biến service hiện tại thành một lớp chứa mọi loại định dạng.

## 20. Những sai lầm cần tránh

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Tạo `JavaMailSenderImpl` trong mọi business method | Lặp config, khó test | Inject bean |
| Dùng chung `SimpleMailMessage` mutable | Lẫn dữ liệu recipients | Tạo mới mỗi lần |
| Hard-code SMTP password | Lộ secret | Env/secret manager |
| Cho request đặt From tùy ý | Spoofing/provider reject | Server-controlled sender |
| Dùng `setText` để gửi HTML | Markup hiển thị nguyên | MimeMessageHelper |
| Không validate recipient/subject/body | Input sai, lỗi muộn | Command + Bean Validation |
| Chỉ có `@Email` mà không có authorization | API bị lợi dụng | Auth, quota, rate limit |
| Công khai controller local | Open relay | Profile + network isolation |
| Không có network timeouts | Thread treo lâu | Timeout properties |
| Port 587 nhưng cấu hình implicit TLS | Handshake lỗi | STARTTLS đúng |
| Tắt TLS verification vì PKIX | Mất xác thực server | Sửa CA/chain/host |
| Bắt exception rồi return bình thường | Caller tưởng đã gửi | Error contract rõ |
| Coi `send` hoàn tất nghĩa là delivered | Báo cáo sai | Tách submitted/delivered |
| Retry mọi timeout ngay lập tức | Có thể gửi trùng | UNKNOWN/reconciliation |
| Gửi trong DB transaction nghiệp vụ | Không atomic với SMTP | Transactional outbox |
| Log full message/body/OTP | Lộ dữ liệu | Metadata tối thiểu |
| Unit test dùng SMTP thật | Dễ flaky và gửi thư ngoài ý muốn | Mockito mock |

## 21. Tình huống tổng hợp: thông báo tài khoản đã kích hoạt

Giả sử một luồng nghiệp vụ đã xác nhận tài khoản:

~~~text
Business event: ACCOUNT_ACTIVATED
Account ID: user-123
Recipient: learner@example.net
~~~

Ứng dụng tạo command:

~~~java
PlainTextMailCommand command =
        new PlainTextMailCommand(
                "learner@example.net",
                "Tài khoản đã được kích hoạt",
                """
                Xin chào,

                Tài khoản của bạn đã được kích hoạt.
                Bạn có thể đăng nhập và sử dụng dịch vụ.

                Trân trọng,
                Đội ngũ hỗ trợ
                """);

mailService.sendPlainText(command);
~~~

Trong môi trường local:

~~~text
ACCOUNT_ACTIVATED
    -> PlainTextMailCommand
    -> SmtpPlainTextMailService
    -> new SimpleMailMessage()
    -> setFrom / setTo / setSubject / setText
    -> JavaMailSender.send()
    -> Mailpit
    -> người học kiểm tra inbox sandbox
~~~

Trong production nếu phải bảo đảm không mất yêu cầu:

~~~text
ACCOUNT_ACTIVATED persisted
    -> durable mail outbox with message key
    -> worker
    -> SmtpPlainTextMailService
    -> SMTP relay
    -> provider delivery/bounce events
~~~

Message key có thể dựa vào `accountActivatedEventId`, mail type và recipient ID, với unique constraint trong DB. Worker retry không tạo logical job mới, nhưng vẫn cần xử lý bất định nếu SMTP accepted rồi process crash.

## 22. Checklist hoàn thành bài

### Cấu hình

- [ ] Có `spring-boot-starter-mail` và dependency test.
- [ ] Có profile local dùng SMTP sandbox.
- [ ] Có profile production với SMTP TLS/auth đúng.
- [ ] Cấu hình `app.mail.from` rõ ràng và được provider cho phép.
- [ ] Không hard-code secret hoặc disable TLS verification.
- [ ] Có connection/read/write timeout.

### Triển khai MailService

- [ ] Có interface `MailService`.
- [ ] Có immutable `PlainTextMailCommand`.
- [ ] Có `SmtpPlainTextMailService` inject `JavaMailSender`.
- [ ] Tạo `SimpleMailMessage` mới cho mỗi lần gửi.
- [ ] Đặt From, To, Subject và Text chính xác.
- [ ] Không dùng SimpleMailMessage như HTML/attachment API.
- [ ] Không nuốt `MailException`.

### Kiểm thử

- [ ] Có unit test Mockito xác minh From/To/Subject/Text.
- [ ] Có test exception propagation.
- [ ] Có test command từ chối subject CR/LF.
- [ ] Đã gửi mail thử qua local sandbox, không gửi ra Internet.
- [ ] Kiểm tra Unicode/newlines trong test mailbox.
- [ ] Controller demo chỉ chạy local, không công khai trên production.

### Sẵn sàng mở rộng

- [ ] Hiểu SMTP submitted khác provider delivered.
- [ ] Có cơ chế authorization/rate limiting nếu mở API thật.
- [ ] Biết khi nào cần MimeMessageHelper.
- [ ] Biết lý do cần outbox/idempotency khi mail không được phép mất.
- [ ] Có monitoring và retry policy cho lỗi SMTP.

## 23. Tổng kết

Phần quan trọng nhất của bài là biến việc gửi email text từ một đoạn code lặp lại thành một service tái sử dụng:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom(fromAddress);
message.setTo(command.to());
message.setSubject(command.subject());
message.setText(command.body());
javaMailSender.send(message);
~~~

**`SimpleMailMessage` là lựa chọn phù hợp cho email plain text đơn giản**. `JavaMailSender` cung cấp tầng SMTP transport; Spring Boot giúp cấu hình bằng `spring.mail.*`; một command và interface rõ ràng giúp giữ business code sạch; Mockito và SMTP sandbox giúp kiểm chứng mà không cần tài khoản email thật.

Điều quan trọng là không dừng ở việc “gọi `send(...)` không lỗi”. Trong hệ thống thực tế phải kiểm soát From, recipients, credentials, TLS, quota, timeout và semantics trạng thái. **SMTP submission không đồng nghĩa delivered**, còn gửi đồng bộ trong business transaction không tự chống mất hoặc gửi trùng. Khi nhu cầu tăng, có thể giữ service đã viết làm transport adapter và bổ sung outbox, message key, retry và tracking ở các lớp phù hợp.

### Tài liệu tham khảo

- **Spring Framework Reference — Email:** `MailSender`, `JavaMailSender` và `SimpleMailMessage`.
- **Spring Framework API — SimpleMailMessage:** `setFrom`, `setTo`, `setCc`, `setBcc`, `setReplyTo`, `setSubject`, `setText`.
- **Spring Framework API — JavaMailSender:** `send(SimpleMailMessage)`, `send(MimeMessage)`.
- **Spring Boot Reference — Sending Email:** `spring-boot-starter-mail`, `spring.mail.*` và mail auto-configuration.
- **Spring Boot Reference — Profiles:** `application-local.yml`, `application-prod.yml` và profile activation.
- **Jakarta Mail API:** SMTP transport, MIME encoding và exceptions.
- **Jakarta Bean Validation:** `@Valid`, `@Email`, `@NotBlank`, `@Size`.
- **JUnit 5 / Mockito Documentation:** `@ExtendWith`, `@Mock`, `ArgumentCaptor` và `verify`.
- **Mailpit Documentation:** SMTP sandbox, web UI và Docker configuration.
- **RFC 5321 — Simple Mail Transfer Protocol:** SMTP transactions và submission responses.
- **RFC 5322 — Internet Message Format:** From, To, Subject và email headers.
