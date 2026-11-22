# Tạo email HTML và plain text bằng MimeMessageHelper

Một email giao dịch gửi từ Spring Framework Mail không nên chỉ có một đoạn HTML. Nhiều ứng dụng email ưu tiên hiển thị HTML, nhưng một số môi trường doanh nghiệp, phần mềm đọc thư, trình đọc hỗ trợ tiếp cận, công cụ kiểm thử hoặc bộ xử lý tự động lại cần phiên bản **plain text**. Một email có cả hai phiên bản thường được đóng gói thành **MIME multipart/alternative**: cùng một thông điệp có hai cách biểu diễn nội dung, không phải hai email khác nhau.

Trong dự án thực hành này, chúng ta tạo ứng dụng Spring Boot gửi **email xác nhận đơn hàng** với:

- Một phiên bản `text/plain` dễ đọc và đầy đủ thông tin.
- Một phiên bản `text/html` trình bày đẹp, có đường dẫn tới đơn hàng.
- `MimeMessageHelper#setText(plainText, htmlText)` để tạo MIME alternative đúng.
- UTF-8 để giữ nguyên tiếng Việt trong subject/body và display name.
- Thymeleaf để render HTML từ dữ liệu động có escaping.
- Mailpit làm SMTP server local để xem nội dung mà **không gửi email thật**.
- API chỉ bật trong profile `local`, tránh vô tình tạo một open relay khi deploy.
- Kiểm thử đọc MIME thực tế, phân biệt SMTP submission với delivery.

Đây là một **dự án thực hành hoàn chỉnh về nội dung mail**. Những phần production như transactional outbox, xác thực API, hạn mức gửi và provider events sẽ được đặt vào ranh giới kiến trúc phù hợp, không bị giả vờ là đã có sẵn chỉ nhờ gọi `JavaMailSender`.

## 1. Mục tiêu sau khi thực hành

Sau khi hoàn thành, bạn có thể:

1. Hiểu vì sao HTML và plain text nên nằm trong cùng một email.
2. Phân biệt Spring `SimpleMailMessage`, Jakarta `MimeMessage`, `JavaMailSender` và `MimeMessageHelper`.
3. Tạo cấu trúc Maven Spring Boot có Mail, Web, Validation và Thymeleaf.
4. Khởi động một SMTP catcher để nhận email ở môi trường local.
5. Viết hai phiên bản nội dung từ cùng dữ liệu đơn hàng.
6. Tạo `MimeMessage` với From, To, Reply-To, Subject và charset.
7. Gọi chính xác overload `setText(plainText, htmlText)`.
8. Xác nhận MIME có cả `text/plain` và `text/html`.
9. Hiểu lý do top-level Content-Type có thể là `multipart/mixed`.
10. Kiểm thử tiếng Việt, HTML escaping, URL, lỗi kết nối SMTP.
11. Biết cách tách phần demo đồng bộ khỏi kiến trúc production bền vững.

## 2. Kết quả mong muốn

Gửi một request dữ liệu minh họa:

```json
{
  "to": "buyer@example.test",
  "customerName": "Nguyễn An",
  "orderCode": "ORD-2026-001"
}
```

Bản plain text tương ứng:

```text
Xin chào Nguyễn An,

Đơn hàng ORD-2026-001 của bạn đã được ghi nhận.

Xem đơn hàng: http://localhost:8080/orders/ORD-2026-001

Đây là email tự động. Nếu cần hỗ trợ, hãy phản hồi email này.

Trân trọng,
Demo Workspace
```

Bản HTML tương ứng về ý nghĩa:

```html
<h1>Xác nhận đơn hàng</h1>
<p>Xin chào <strong>Nguyễn An</strong>,</p>
<p>Đơn hàng <strong>ORD-2026-001</strong> đã được ghi nhận.</p>
<a href="http://localhost:8080/orders/ORD-2026-001">
  Xem đơn hàng
</a>
```

Hai phần phải mang cùng thông tin quan trọng: người nhận không nên mất mã đơn hàng hoặc link chỉ vì client đang hiển thị plain text.

Khi mở email trong Mailpit, giao diện thường cho phép xem phần HTML, plain text và nguồn MIME. Đây là **một email chứa hai phiên bản**, không phải ứng dụng gửi hai lần.

## 3. Sơ đồ luồng thực hành

```text
POST /api/dev/order-confirmations
              |
              v
      @Valid OrderMailRequest
              |
              v
      OrderMailRenderer
        |           |
        |           +--> Thymeleaf HTML template
        |
        +--> Plain text renderer
              |
              v
      RenderedMail
        - subject
        - plainText
        - htmlText
              |
              v
      OrderMailService
        - JavaMailSender.createMimeMessage()
        - MimeMessageHelper(..., UTF-8)
        - setFrom / setTo / setReplyTo
        - setSubject
        - setText(plainText, htmlText)
              |
              v
      JavaMailSender.send(...)
              |
              v
      Mailpit SMTP :1025
              |
              v
      Mailpit UI :8025
```

`OrderMailRequest`, `RenderedMail`, `OrderMailRenderer` và `OrderMailService` là những lớp chúng ta tự xây. `JavaMailSender`/`MimeMessageHelper` là API của Spring Framework Mail.

## 4. Cần chuẩn bị gì?

- JDK 17 trở lên với một phiên bản Spring Boot tương thích.
- Maven và một IDE hỗ trợ Java/Spring.
- Docker/Compose nếu muốn chạy Mailpit bằng container.
- Không cần Gmail hay tài khoản SMTP production.
- Một trình duyệt để xem Mailpit ở `http://localhost:8025`.
- Một HTTP client như `curl`, Postman hoặc PowerShell.

Ví dụ dưới đây chọn **Spring Boot 3.5.0** làm phiên bản Maven minh họa, tương ứng hệ sinh thái Jakarta `jakarta.mail.*`. Dự án có thể dùng một bản Spring Boot được tổ chức đang hỗ trợ; không nên coi phiên bản trong tài liệu là lời khẳng định “mới nhất”.

Nếu dự án dùng Spring Boot 2/Spring Framework 5, namespace mail thường là `javax.mail.*`; không trộn hai namespace trong cùng source code.

## 5. Cấu trúc thư mục

```text
mail-html-plain-demo/
├── pom.xml
├── compose.yml
└── src/
    ├── main/
    │   ├── java/com/example/maildemo/
    │   │   ├── MailDemoApplication.java
    │   │   ├── config/
    │   │   │   └── DemoMailProperties.java
    │   │   └── mail/
    │   │       ├── OrderMailRequest.java
    │   │       ├── RenderedMail.java
    │   │       ├── OrderMailRenderer.java
    │   │       ├── OrderMailService.java
    │   │       ├── SubmissionReceipt.java
    │   │       ├── MailPreparationFailure.java
    │   │       ├── MailSubmissionFailure.java
    │   │       ├── MailDemoController.java
    │   │       └── MailDemoErrorHandler.java
    │   └── resources/
    │       ├── application-local.yml
    │       └── templates/mail/
    │           └── order-confirmation.html
    └── test/
        └── java/com/example/maildemo/mail/
            └── OrderMailServiceTest.java
```

Chúng ta sẽ xây theo thứ tự từ môi trường local tới renderer, service gửi và kiểm thử. Mỗi file minh họa dưới đây là nội dung của dự án **được hướng dẫn tạo**, không phải yêu cầu sửa các file khác của module đang đọc.

## 6. Khởi tạo Maven pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>mail-html-plain-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>mail-html-plain-demo</name>

    <properties>
        <java.version>17</java.version>
    </properties>

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
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Vai trò dependencies:**

| Dependency | Mục đích |
| --- | --- |
| `spring-boot-starter-mail` | Cấu hình `JavaMailSender` và Jakarta Mail transport |
| `spring-boot-starter-web` | API dev để kích hoạt gửi thử |
| `spring-boot-starter-validation` | Bean Validation cho request/properties |
| `spring-boot-starter-thymeleaf` | Render HTML template bằng `th:text`, `th:href` |
| `spring-boot-starter-test` | JUnit, Mockito, Spring Test theo dependency management |

Không cần thêm `javax.mail` hoặc `jakarta.mail-api` version thủ công vào starter này. Dùng dependency management của Spring Boot để tránh sai khác JavaMail provider/API versions.

## 7. Chạy SMTP catcher bằng Mailpit

Tạo `compose.yml`:

```yaml
services:
  mailpit:
    image: axllent/mailpit:latest
    ports:
      - "127.0.0.1:1025:1025"
      - "127.0.0.1:8025:8025"
```

Khởi động trong thư mục project:

```bash
docker compose up -d
```

Truy cập:

```text
SMTP server : localhost:1025
Mailpit UI  : http://localhost:8025
```

Mailpit nhận các email gửi từ ứng dụng và hiển thị chúng để kiểm thử; nó **không chuyển email tới mailbox thật** trong cấu hình local này.

Lưu ý:

- `127.0.0.1` ở port bindings giúp chỉ expose cho máy local.
- Không deploy cấu hình Mailpit catcher không xác thực ra Internet.
- Image tag `latest` tiện cho bài học; CI/team production-like tests nên pin version/digest.
- Nếu ứng dụng chạy trong container cùng Compose network, SMTP host thường là service name `mailpit`, không phải `localhost` của container app.
- Nếu Docker không sẵn, có thể dùng một SMTP capture tool khác với cùng mục đích.

## 8. Cấu hình application-local.yml

Tạo `src/main/resources/application-local.yml`:

```yaml
server:
  port: 8080

spring:
  mail:
    host: localhost
    port: 1025
    properties:
      "[mail.smtp.auth]": false
      "[mail.smtp.starttls.enable]": false
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
      "[mail.debug]": false

  thymeleaf:
    cache: false
    encoding: UTF-8

demo:
  mail:
    from: "no-reply@example.test"
    from-name: "Demo Workspace"
    reply-to: "support@example.test"
    public-base-url: "http://localhost:8080"
```

Trong môi trường local, Mailpit trên cổng 1025 không đòi hỏi SMTP AUTH/TLS theo cấu hình demo. **Không mang `auth=false` hoặc `starttls=false` sang provider production** nếu nhà cung cấp yêu cầu xác thực và mã hóa.

Với SMTP production qua cổng 587, thường cần cấu hình authentication, STARTTLS, certificate/hostname verification và secrets lấy từ environment/secret manager. Không hardcode SMTP password trong repository.

Tham số `demo.mail.*` là **configuration của ứng dụng**; Spring Boot không tự hiểu ý nghĩa sender/from-name của chúng nếu ta không tạo class binding.

## 9. Main application và configuration properties

`MailDemoApplication.java`:

```java
package com.example.maildemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class MailDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MailDemoApplication.class, args);
    }
}
```

`config/DemoMailProperties.java`:

```java
package com.example.maildemo.config;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo.mail")
public record DemoMailProperties(
    @NotBlank @Email String from,
    @NotBlank String fromName,
    @NotBlank @Email String replyTo,
    @NotBlank String publicBaseUrl
) {}
```

Spring Boot bind `from-name` sang `fromName`, `public-base-url` sang `publicBaseUrl` theo relaxed binding.

Trong production, nên kiểm tra `publicBaseUrl` là HTTPS URL của domain allowlisted; không cho HTTP request truyền URL bất kỳ để chèn vào email vì có nguy cơ phishing. Ví dụ local dùng HTTP và `localhost` chỉ để thực hành.

`@ConfigurationPropertiesScan` và `@Validated` giúp cấu hình sai bị phát hiện sớm. Với cấu hình production phức tạp hơn, có thể thêm validator cho URL/sender domain.

## 10. DTO nhận dữ liệu của email

Tạo `mail/OrderMailRequest.java`:

```java
package com.example.maildemo.mail;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record OrderMailRequest(
    @NotBlank @Email String to,

    @NotBlank @Size(max = 80) String customerName,

    @NotBlank
    @Pattern(regexp = "[A-Z0-9-]{3,40}")
    String orderCode
) {}
```

Điểm quan trọng:

- `@Email` kiểm tra định dạng ở mức validation, không chứng minh địa chỉ thuộc đúng người nhận.
- `@NotBlank` ngăn địa chỉ/text rỗng.
- `@Size` tránh một trường rất dài vượt nhu cầu thông báo.
- `@Pattern` giới hạn order code thành path segment tương đối an toàn trong ví dụ.
- Không nhận `from`, `replyTo` hay SMTP credentials từ request body.
- Không cho client gửi raw HTML/template để API bị lợi dụng như open relay.

**Trong production, controller không nên cho người dùng bất kỳ truyền `to` và kích hoạt gửi mail tự do.** Recipient nên được resolve từ đơn hàng/tài khoản mà caller được phép truy cập. Endpoint ở đây chỉ bật trong local profile.

## 11. Model hai phiên bản nội dung

Tạo `mail/RenderedMail.java`:

```java
package com.example.maildemo.mail;

public record RenderedMail(
    String subject,
    String plainText,
    String htmlText
) {}
```

Model này biểu diễn **nội dung đã render**, chưa có transport settings và chưa phải Jakarta `MimeMessage`.

Nó tách nhiệm vụ:

```text
OrderMailRequest
     |
     v
Content renderer
     |
     +--> subject
     +--> plainText
     +--> htmlText
     |
     v
MimeMessage construction
     |
     v
SMTP transport
```

Lợi ích:

- Có thể unit test plain/HTML mà không cần SMTP.
- Cùng một tập dữ liệu tạo hai phiên bản đồng nhất.
- Template có thể được version hóa.
- Lỗi render được phân biệt với lỗi SMTP.
- Không cần đặt business formatting logic vào SMTP handler.

Không log nguyên `RenderedMail` bởi `record.toString()` có thể chứa toàn bộ nội dung, tên khách, order code và link.

## 12. Viết template HTML bằng Thymeleaf

Tạo `src/main/resources/templates/mail/order-confirmation.html`:

```html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Xác nhận đơn hàng</title>
</head>
<body style="margin:0;padding:0;background:#f4f6fa;font-family:Arial,sans-serif;">
<table role="presentation" cellpadding="0" cellspacing="0"
       style="width:100%;background:#f4f6fa;padding:24px;">
    <tr>
        <td align="center">
            <table role="presentation" cellpadding="0" cellspacing="0"
                   style="width:100%;max-width:600px;background:#ffffff;
                          border:1px solid #e4e7ec;border-radius:8px;">
                <tr>
                    <td style="padding:28px;">
                        <h1 style="margin:0 0 16px;color:#17202a;
                                   font-size:24px;">
                            Xác nhận đơn hàng
                        </h1>

                        <p style="font-size:16px;line-height:1.6;color:#263445;">
                            Xin chào
                            <strong th:text="${customerName}">Khách hàng</strong>,
                        </p>

                        <p style="font-size:16px;line-height:1.6;color:#263445;">
                            Đơn hàng
                            <strong th:text="${orderCode}">ORD-DEMO</strong>
                            của bạn đã được ghi nhận.
                        </p>

                        <p style="padding:16px 0;">
                            <a th:href="${orderUrl}"
                               href="http://localhost:8080/orders/ORD-DEMO"
                               style="background:#2255cc;color:#ffffff;
                                      text-decoration:none;padding:12px 18px;
                                      border-radius:6px;display:inline-block;">
                                Xem đơn hàng
                            </a>
                        </p>

                        <p style="font-size:13px;line-height:1.6;color:#667085;">
                            Đây là email tự động. Nếu cần hỗ trợ,
                            hãy phản hồi email này.
                        </p>

                        <p style="font-size:14px;color:#667085;">
                            Trân trọng,
                            <strong>Demo Workspace</strong>
                        </p>
                    </td>
                </tr>
            </table>
        </td>
    </tr>
</table>
</body>
</html>
```

Các biểu thức `th:text="${customerName}"` và `th:text="${orderCode}"` cho Thymeleaf escape dữ liệu ở ngữ cảnh HTML text. Tránh thay bằng chuỗi nối HTML thủ công rồi dùng `th:utext` cho dữ liệu nhập vào từ client.

`th:href="${orderUrl}"` đưa URL vào attribute HTML có escaping. **Escaping không tự đảm bảo URL an toàn**: nguồn tạo `orderUrl` vẫn phải thuộc domain được phép, tránh `javascript:`, user-controlled redirect hoặc link phishing. Trong demo, base URL là configuration server-side và `orderCode` có regex hạn chế.

Email clients hỗ trợ CSS/HTML không đồng đều. Ví dụ dùng bảng, inline styles và markup tương đối đơn giản, tránh phụ thuộc JavaScript, CSS layout phức tạp hoặc remote fonts.

## 13. Vì sao không dùng HTML giống trang web?

Email HTML khác HTML trình duyệt:

- Nhiều email clients lọc JavaScript hoàn toàn.
- CSS có thể bị hạn chế; inline CSS thường ổn định hơn nhiều style rules nâng cao.
- Remote images có thể bị chặn mặc định.
- Layout tables thường tương thích tốt hơn một số kỹ thuật layout mới.
- Media queries và dark mode có mức hỗ trợ khác nhau.
- Form, iframe và script thường không đáng tin trong email.
- Link có thể qua security scanner hoặc provider rewrite.
- Một số clients hiển thị plaintext thay vì HTML.

Vì vậy, dự án này tạo **HTML đủ đơn giản** nhưng vẫn có plain text đầy đủ. Không nên coi plain version là phần phụ không cần kiểm tra.

## 14. Render HTML và plain text từ cùng dữ liệu

Tạo `mail/OrderMailRenderer.java`:

```java
package com.example.maildemo.mail;

import java.util.Locale;

import com.example.maildemo.config.DemoMailProperties;
import org.springframework.stereotype.Component;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Component
public class OrderMailRenderer {

    private final TemplateEngine templateEngine;
    private final DemoMailProperties mailProperties;

    public OrderMailRenderer(
            TemplateEngine templateEngine,
            DemoMailProperties mailProperties) {
        this.templateEngine = templateEngine;
        this.mailProperties = mailProperties;
    }

    public RenderedMail render(OrderMailRequest request) {
        String orderUrl =
            mailProperties.publicBaseUrl().replaceAll("/+$", "")
                + "/orders/" + request.orderCode();

        Context context = new Context(Locale.forLanguageTag("vi-VN"));
        context.setVariable("customerName", request.customerName());
        context.setVariable("orderCode", request.orderCode());
        context.setVariable("orderUrl", orderUrl);

        String html = templateEngine.process(
            "mail/order-confirmation", context
        );

        String safeName = request.customerName()
            .replace('\r', ' ')
            .replace('\n', ' ')
            .trim();

        String plain = """
            Xin chào %s,

            Đơn hàng %s của bạn đã được ghi nhận.

            Xem đơn hàng: %s

            Đây là email tự động. Nếu cần hỗ trợ,
            hãy phản hồi email này.

            Trân trọng,
            Demo Workspace
            """.formatted(safeName, request.orderCode(), orderUrl);

        String subject =
            "Xác nhận đơn hàng " + request.orderCode();

        return new RenderedMail(subject, plain, html);
    }
}
```

Điểm cần hiểu:

1. **Cùng `OrderMailRequest`** được dùng để dựng subject, text và HTML.
2. `templateEngine.process(...)` đọc template theo Spring Boot Thymeleaf resolver.
3. Plain text có dòng trống, mã đơn hàng và URL rõ ràng.
4. `safeName` thay ký tự CR/LF bằng khoảng trắng để user input không tự tạo dòng mới trong bản text minh họa.
5. `orderCode` được validation theo regex nên không đưa slash/URL scheme vào path.
6. `publicBaseUrl` được cấu hình ở server; sản phẩm thật cần kiểm tra HTTPS/allowed domains.
7. Renderer không biết SMTP host, password hay provider.

Không dùng `HtmlUtils.htmlEscape` rồi lại đưa vào `th:text`: điều đó có thể khiến ký tự `&` hoặc `<` bị escape hai lần. Để template engine làm escaping ở đúng ngữ cảnh của nó.

### Bài tập nhỏ

Thử thay `customerName` bằng dữ liệu tổng hợp có dấu `&`, dấu nháy hoặc chuỗi `<b>An</b>` ở môi trường local. Phần HTML nên hiển thị **text người dùng**, không chạy markup người dùng cung cấp. Bản plain text có thể chứa nguyên ký tự `<` và `>` vì nó là văn bản, không phải HTML.

## 15. Tạo receipt cho lần submit

Tạo `mail/SubmissionReceipt.java`:

```java
package com.example.maildemo.mail;

import java.util.UUID;

public record SubmissionReceipt(
    UUID notificationId,
    String submissionStatus
) {}
```

Ở bản demo, `SUBMITTED` có nghĩa Spring Mail không báo lỗi trong lời gọi submit tới SMTP catcher. **Không gọi trạng thái này là `DELIVERED`**, vì đó là thông tin thuộc downstream delivery/provider event.

UUID trong demo giúp đối soát response/logs. Với production cần tạo ID bền vững trong database/outbox trước SMTP; UUID tạo trong memory đơn thuần không phải bằng chứng đã có notification bền vững.

## 16. Các exception dành cho ranh giới chuẩn bị và gửi

Tạo `mail/MailPreparationFailure.java`:

```java
package com.example.maildemo.mail;

public class MailPreparationFailure extends RuntimeException {

    public MailPreparationFailure(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Tạo `mail/MailSubmissionFailure.java`:

```java
package com.example.maildemo.mail;

public class MailSubmissionFailure extends RuntimeException {

    public MailSubmissionFailure(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Ý nghĩa:

- `MailPreparationFailure`: không thể dựng `MimeMessage` hợp lệ, chẳng hạn thông tin địa chỉ/encoding/MIME.
- `MailSubmissionFailure`: Spring Mail báo lỗi khi submit SMTP; cần phân loại transport failure sâu hơn nếu đưa vào production retry pipeline.

Không coi mọi `MailSubmissionFailure` là chắc chắn **chưa gửi**. Timeout sau SMTP `DATA` có thể là kết quả không xác định (`AMBIGUOUS`) vì relay có thể đã nhận message nhưng response bị mất.

Ví dụ này giữ error handling gọn để tập trung vào HTML/plain; phần retry production sẽ xử lý bằng outbox và failure classifier.

## 17. Gửi cả HTML và plain text bằng MimeMessageHelper

Đây là **phần quan trọng nhất của bài thực hành**.

Tạo `mail/OrderMailService.java`:

```java
package com.example.maildemo.mail;

import java.io.UnsupportedEncodingException;
import java.util.UUID;

import com.example.maildemo.config.DemoMailProperties;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;

import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender sender;
    private final OrderMailRenderer renderer;
    private final DemoMailProperties properties;

    public OrderMailService(
            JavaMailSender sender,
            OrderMailRenderer renderer,
            DemoMailProperties properties) {
        this.sender = sender;
        this.renderer = renderer;
        this.properties = properties;
    }

    public SubmissionReceipt submitOrderConfirmation(
            OrderMailRequest request) {

        UUID notificationId = UUID.randomUUID();

        RenderedMail content = renderer.render(request);

        try {
            MimeMessage mime = sender.createMimeMessage();

            MimeMessageHelper helper = new MimeMessageHelper(
                mime,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
            );

            helper.setFrom(
                properties.from(),
                properties.fromName()
            );
            helper.setTo(request.to());
            helper.setReplyTo(properties.replyTo());
            helper.setSubject(content.subject());

            // Điểm mấu chốt:
            // Một email gồm hai phương án hiển thị.
            helper.setText(
                content.plainText(),
                content.htmlText()
            );

            sender.send(mime);

            return new SubmissionReceipt(
                notificationId, "SUBMITTED"
            );

        } catch (MessagingException
                 | UnsupportedEncodingException exception) {

            throw new MailPreparationFailure(
                "Cannot prepare order-confirmation email",
                exception
            );

        } catch (MailException exception) {

            throw new MailSubmissionFailure(
                "SMTP submission reported an error",
                exception
            );
        }
    }
}
```

**Dòng cần ghi nhớ:**

```java
helper.setText(content.plainText(), content.htmlText());
```

Đây là overload nhận **hai `String`**:

- Tham số thứ nhất: **plain-text alternative**.
- Tham số thứ hai: **HTML alternative**.

Nó khác:

```java
helper.setText(content.htmlText(), true);
```

Overload thứ hai chỉ biểu thị một HTML body, **không** tự tạo bản plain text đầy đủ. Muốn có cả hai, hãy dùng overload hai chuỗi.

### Vì sao chọn multipart mode tường minh?

```java
new MimeMessageHelper(
    mime,
    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
    "UTF-8"
)
```

`setText(plainText, htmlText)` yêu cầu helper được tạo ở **multipart mode**. Mode `MULTIPART_MODE_MIXED_RELATED` phù hợp khi dự án có thể mở rộng thêm attachment hoặc inline resources. Spring tạo cấu trúc MIME alternative bên trong. Với bài demo không có attachment, helper vẫn có thể tạo outer multipart wrappers; điều đó hợp lệ.

Nếu dùng:

```java
new MimeMessageHelper(mime, false, "UTF-8")
```

rồi gọi `setText(plain, html)`, helper không ở multipart mode và không đáp ứng trường hợp này. Cần tạo helper với `true` hoặc một multipart mode phù hợp.

## 18. Đọc kỹ từng lệnh trong service

| Lệnh | Tác dụng |
| --- | --- |
| `sender.createMimeMessage()` | Tạo Jakarta `MimeMessage` tương thích Mail Sender |
| `new MimeMessageHelper(..., MIXED_RELATED, "UTF-8")` | Khởi tạo MIME helper multipart và charset |
| `helper.setFrom(from, fromName)` | Tạo From với display name |
| `helper.setTo(to)` | Đặt recipient To |
| `helper.setReplyTo(replyTo)` | Đặt hộp thư nhận phản hồi |
| `helper.setSubject(subject)` | Đặt subject, có xử lý encoding |
| `helper.setText(plain, html)` | Tạo hai biểu diễn cùng nội dung |
| `sender.send(mime)` | Submit message qua cấu hình SMTP |
| `SubmissionReceipt(..., "SUBMITTED")` | Đánh dấu kết quả submission ở mức demo |

Ở ví dụ, địa chỉ From/Reply-To đến từ **cấu hình do ứng dụng kiểm soát**, không từ request body. Đây là một guard cần thiết để tránh biến endpoint thành công cụ giả mạo người gửi.

Ở production cần kiểm tra sender domain/alias có quyền gửi trên tài khoản provider. SMTP AUTH thành công không tự đồng nghĩa mọi From address đều được provider chấp thuận.

## 19. MimeMessageHelper không thay thế JavaMailSender

Phân biệt:

```text
RenderedMail (data)
      |
      v
MimeMessageHelper (builder/helper)
      |
      v
MimeMessage (email MIME representation)
      |
      v
JavaMailSender (transport abstraction)
      |
      v
SMTP server
```

`MimeMessageHelper` không tự mở connection hay gửi email. Nó thao tác trên `MimeMessage` được tạo.

`JavaMailSender` không tự render Thymeleaf hoặc hiểu business DTO. Nó nhận `MimeMessage` và thực hiện submit.

`MimeMessage` là **định dạng email**; `org.springframework.messaging.Message<?>` của Spring Integration lại là message nội bộ dùng trong integration flows. Không nhầm hai khái niệm.

## 20. Tạo API demo chỉ hoạt động trong profile local

Tạo `mail/MailDemoController.java`:

```java
package com.example.maildemo.mail;

import org.springframework.context.annotation.Profile;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import jakarta.validation.Valid;

@RestController
@Profile("local")
@RequestMapping("/api/dev/order-confirmations")
public class MailDemoController {

    private final OrderMailService service;

    public MailDemoController(OrderMailService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<SubmissionReceipt> send(
            @Valid @RequestBody OrderMailRequest request) {

        return ResponseEntity.ok(
            service.submitOrderConfirmation(request)
        );
    }
}
```

`@Profile("local")` làm endpoint này chỉ có bean khi profile `local` được kích hoạt. Nếu bật profile `local` trong production hoặc expose local port ra ngoài không kiểm soát, nó vẫn có thể bị lạm dụng. Vì vậy **profile là lớp giới hạn demo, không phải cơ chế authentication/authorization đầy đủ**.

Production nên dùng use case đã xác thực, từ order event hoặc outbox; recipient được resolve server-side và có rate/abuse controls.

### Lỗi validation

`@Valid @RequestBody` kết hợp Bean Validation kiểm tra `to`, `customerName`, `orderCode`. Nếu vi phạm, Spring MVC trả lỗi 4xx theo exception handling configuration.

Cần nhớ validation định dạng địa chỉ **không xác minh mailbox tồn tại** và không chứng minh người gọi có quyền gửi dữ liệu đơn hàng tới địa chỉ đó.

## 21. Xử lý lỗi demo không trả raw SMTP exception

Tạo `mail/MailDemoErrorHandler.java`:

```java
package com.example.maildemo.mail;

import java.util.Map;

import org.springframework.context.annotation.Profile;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
@Profile("local")
public class MailDemoErrorHandler {

    @ExceptionHandler(MailPreparationFailure.class)
    public ResponseEntity<Map<String, String>> preparationError() {
        return ResponseEntity
            .status(HttpStatus.INTERNAL_SERVER_ERROR)
            .body(Map.of(
                "error", "MAIL_PREPARATION_FAILED"
            ));
    }

    @ExceptionHandler(MailSubmissionFailure.class)
    public ResponseEntity<Map<String, String>> submissionError() {
        return ResponseEntity
            .status(HttpStatus.BAD_GATEWAY)
            .body(Map.of(
                "error", "SMTP_SUBMISSION_FAILED_OR_UNCERTAIN"
            ));
    }
}
```

Lỗi `SMTP_SUBMISSION_FAILED_OR_UNCERTAIN` cố ý không tuyên bố “chắc chắn chưa gửi”. Nếu client nhận HTTP 502, **không được tự động retry HTTP vô hạn** mà không có idempotency/notification lookup; một SMTP timeout sau DATA vẫn có thể có accepted message.

Đây là controller demonstration. Trong production nên dùng command/outbox ID, error classifier, retry policy và persisted status.

## 22. Chạy project lần đầu

Khởi động SMTP catcher:

```bash
docker compose up -d
```

Sau đó chạy Spring Boot ở profile local:

```bash
mvn spring-boot:run -Dspring-boot.run.profiles=local
```

Trong một số shell, cách truyền Maven system property cần quoting; nếu chạy trong Windows PowerShell, có thể đặt profile qua environment:

```powershell
$env:SPRING_PROFILES_ACTIVE = "local"
mvn spring-boot:run
```

Hoặc với bản build JAR:

```bash
java -jar target/mail-html-plain-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=local
```

Nếu JVM/app đang chạy trong Docker, `localhost:1025` sẽ trỏ về container của nó, không tự trỏ tới container Mailpit; cần dùng hostname `mailpit` trên Compose network chung hoặc mapping phù hợp.

### Xác nhận các services

- Spring Boot: `http://localhost:8080`.
- Mailpit web UI: `http://localhost:8025`.
- SMTP: `localhost:1025`.
- Chưa cần SMTP username/password trong môi trường local này.

Nếu cổng đã được dùng bởi ứng dụng khác, thay port binding và update `spring.mail.port` cho khớp.

## 23. Gửi request đầu tiên

Một lệnh `curl`:

```bash
curl -X POST "http://localhost:8080/api/dev/order-confirmations" \
  -H "Content-Type: application/json" \
  -d '{
    "to": "buyer@example.test",
    "customerName": "Nguyễn An",
    "orderCode": "ORD-2026-001"
  }'
```

Một lệnh PowerShell:

```powershell
$body = @{
    to = "buyer@example.test"
    customerName = "Nguyễn An"
    orderCode = "ORD-2026-001"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://localhost:8080/api/dev/order-confirmations" `
    -ContentType "application/json; charset=utf-8" `
    -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

Nếu SMTP catcher nhận thành công, response minh họa:

```json
{
  "notificationId": "c751fb74-127d-4c5a-9b8a-38b1c7af3e4d",
  "submissionStatus": "SUBMITTED"
}
```

UUID là giá trị tạo mới mỗi lượt gọi; mẫu trên chỉ minh họa. Nếu gửi cùng request hai lần, demo này tạo hai lần submission vì **chưa có idempotency/outbox**. Đó là hành vi cần nhận biết trước khi bổ sung vào production.

## 24. Mở Mailpit để xem kết quả

Truy cập `http://localhost:8025`, chọn email vừa nhận, rồi quan sát:

- From: `Demo Workspace <no-reply@example.test>`.
- To: `buyer@example.test`.
- Reply-To: `support@example.test`.
- Subject: `Xác nhận đơn hàng ORD-2026-001`.
- HTML body với tiêu đề, tên người nhận, button/link.
- Plain-text body có câu chào, mã đơn và URL.
- MIME source cho thấy các parts với Content-Type khác nhau.

Nếu UI mặc định hiển thị HTML, chuyển sang phần Text/Source để xác nhận plain text cũng được gửi. Không suy từ việc HTML hiện đẹp rằng MIME đã có `text/plain`; cần quan sát cả hai.

## 25. Cấu trúc MIME mà helper tạo ra

Về mặt ý nghĩa:

```text
MimeMessage
    |
    v
multipart/alternative
    |
    +--> text/plain; charset=UTF-8
    |
    +--> text/html; charset=UTF-8
```

Với `MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED`, cây MIME thực tế có thể được bọc như sau:

```text
MimeMessage
  Content-Type: multipart/mixed
      |
      +--> multipart/related
              |
              +--> multipart/alternative
                      |
                      +--> text/plain; charset=UTF-8
                      |
                      +--> text/html; charset=UTF-8
```

Khi thêm attachment/inline image, cấu trúc còn có các parts tương ứng. MIME headers và boundaries phụ thuộc Jakarta Mail implementation/multipart mode; **không hardcode kỳ vọng top-level Content-Type luôn là `multipart/alternative`**.

Ý tưởng chính: `multipart/alternative` biểu diễn **nhiều cách hiển thị cùng thông tin**. Client có thể ưu tiên bản HTML hoặc plain text.

## 26. Plain text không phải “HTML bỏ thẻ”

Một anti-pattern:

```java
String plain = html.replaceAll("<[^>]*>", "");
```

Regex này không phải HTML parser. Nó có thể:

- Làm dính các câu khi bỏ `<p>`, `<br>`, `<li>`.
- Để lại HTML entities như `&amp;`.
- Làm mất link thực tế trong `href`.
- Không xử lý hợp lý table và nội dung ẩn.
- Gây khó đọc ở text-only client.
- Có thể làm sai nghĩa của email.

Plain text nên được **soạn riêng nhưng cùng dữ liệu**, ví dụ câu chào, thông tin chính, link đầy đủ và hướng dẫn hỗ trợ.

Nếu ứng dụng có nhiều templates, có thể dùng một template `.txt` song song với `.html`, hoặc một renderer chuyên biệt cho plain text. Không phụ thuộc phép xóa tag đơn giản.

## 27. Hai phiên bản phải đồng nhất về ý nghĩa

So sánh nội dung:

| Thông tin | Plain text | HTML |
| --- | --- | --- |
| Lời chào | Có | Có |
| Mã đơn hàng | Có | Có |
| Trạng thái đơn | Có | Có |
| URL xem đơn | Viết đầy đủ | Gắn vào `<a>` |
| Thông tin hỗ trợ | Có | Có |
| Branding | Có, ở dạng văn bản | Có, kèm style |
| Dữ liệu nhạy cảm | Chỉ điều cần thiết | Cùng mức cần thiết |

Không để HTML có điều kiện hủy đơn/đường dẫn bắt buộc mà plain text không có. Một email có thể được hiển thị hoàn toàn bằng plain text ở client dùng chế độ bảo mật hoặc hỗ trợ accessibility.

### Trường hợp plain text dài

Nếu có bảng nhiều trường, có thể dùng:

```text
Thông tin đơn hàng
------------------
Mã đơn     : ORD-2026-001
Trạng thái : Đã ghi nhận
Xem chi tiết:
http://localhost:8080/orders/ORD-2026-001
```

Đừng cố tạo bảng monospace quá rộng khiến người đọc trên điện thoại phải cuộn ngang nhiều.

## 28. UTF-8 quan trọng ở những vị trí nào?

Email chứa:

```text
Tên: Nguyễn An
Subject: Xác nhận đơn hàng – Tháng 11
Body: Đơn hàng của bạn đã được ghi nhận.
```

Các vị trí cần xử lý:

1. **Java source/resource files** lưu UTF-8.
2. **Thymeleaf template** đọc với đúng encoding.
3. **MimeMessageHelper charset UTF-8**.
4. **Subject/From display name** được Jakarta Mail encode đúng ở MIME layer.
5. **HTTP request JSON** gửi đúng UTF-8 khi gọi API.
6. **SMTP test viewer** decode MIME parts theo charset.

Trong ví dụ:

```java
new MimeMessageHelper(
    mime,
    MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
    "UTF-8"
);
```

và:

```java
helper.setFrom(
    "no-reply@example.test",
    "Đội hỗ trợ"
);
```

MimeMessageHelper sẽ phối hợp Jakarta Mail để encode display name/headers phù hợp. Raw MIME header có thể xuất hiện dưới dạng encoded-word, không phải trực tiếp ký tự Unicode.

Trong test, dùng `mime.getSubject()` để xem giá trị đã giải mã. Không so sánh subject với bytes của raw MIME header.

## 29. Content-Type và HTML không phải một boolean ở tầng transport

Hai overload quan trọng:

```java
helper.setText("Xin chào");          // plain text
helper.setText("<b>Xin chào</b>", true); // HTML only
```

Và:

```java
helper.setText(
    "Xin chào, đơn hàng đã xác nhận.",
    "<html><body><b>Xin chào</b></body></html>"
); // plain + HTML alternatives
```

Boolean `true` ở overload hai tham số kiểu `(String, boolean)` cho biết **chuỗi đầu là HTML**, không bảo rằng plain alternative đã tự xuất hiện.

Overload `(String, String)` dành cho **plain + HTML**. Chú ý thứ tự: plain trước, HTML sau.

Một số lỗi thực tế đến từ việc gọi:

```java
helper.setText(html, plain);
```

Khi đảo thứ tự, các parts có thể bị gắn Content-Type ngược với nội dung, dẫn tới HTML bị hiển thị dạng text hoặc plain text hiển thị trong phần HTML.

## 30. Không gọi setText hai lần để tạo alternative

Không nên:

```java
helper.setText(plain);
helper.setText(html, true);
```

Đây không phải giao kèo tạo hai alternatives. Lần gọi sau có thể thay nội dung phần trước hoặc tạo kết quả không đúng ý đồ, tùy implementation và multipart mode.

Hãy gọi **một lần**:

```java
helper.setText(plain, html);
```

Nếu cần xây MIME structure rất đặc biệt, phải làm rõ multipart tree với Jakarta Mail API. Với trường hợp giao dịch thông thường, dùng overload này giúp code đơn giản và ít lỗi hơn.

## 31. From khác Reply-To

Trong ví dụ:

```java
helper.setFrom("no-reply@example.test", "Demo Workspace");
helper.setReplyTo("support@example.test");
```

Header minh họa:

```text
From: Demo Workspace <no-reply@example.test>
Reply-To: support@example.test
```

`From` biểu diễn sender người nhận thấy. `Reply-To` cho biết nếu khách bấm Reply, thư trả lời có thể gửi tới đâu.

Không nhầm với:

- SMTP AUTH username: tài khoản xác thực để submit.
- SMTP envelope `MAIL FROM`: địa chỉ bounce/return-path ở transport.
- Provider verified sender/domain: danh tính được phép gửi.
- `Sender` header: có semantics riêng trong MIME.

Một provider có thể yêu cầu From thuộc verified domain hoặc send-as permission. `setFrom` thành công khi dựng MIME không bảo đảm relay chấp nhận sender tùy ý.

## 32. To, Cc, Bcc và recipient privacy

Trong bài thực hành chỉ có một `To`. Với nhiều người nhận:

```java
helper.setTo(new String[] {
    "buyer1@example.test",
    "buyer2@example.test"
});
helper.setCc("audit@example.test");
helper.setBcc("internal@example.test");
```

Cần quan tâm:

- To/Cc thường hiển thị cho người nhận.
- Bcc không nên lộ trong delivered MIME headers; SMTP envelope có thể dùng địa chỉ này để giao.
- Một message có nhiều recipients không thuận tiện cho personalization hoặc per-recipient tracking.
- Marketing mail cần consent/unsubscribe/frequency caps theo từng người.
- Không log `getAllRecipients()`/Bcc arrays hoặc copy Bcc thành custom public header.

Trong production, người dùng không nên được tự cung cấp danh sách recipients không giới hạn qua public API.

## 33. MIME alternative là một nội dung, không phải hai email

Một khái niệm cần ghi nhớ:

```text
One logical email
    |
    +--> Alternative #1: text/plain
    |
    +--> Alternative #2: text/html
```

Đừng gọi:

```java
sender.send(plainMimeMessage);
sender.send(htmlMimeMessage);
```

chỉ để tạo fallback. Làm vậy sẽ gửi **hai thông điệp** chứ không tạo một MIME alternative.

Đúng là tạo **một MimeMessage** và thêm **hai body parts** bằng `MimeMessageHelper#setText(plain, html)`.

Nếu có tracking/dedup, một notification ID tương ứng một email logic; các phần plain/html không phải các notification ID riêng.

## 34. Kiểm thử đơn vị bằng Mockito mà không gửi SMTP

Mục tiêu test service:

1. Bản plain text được tạo.
2. Bản HTML có nội dung phù hợp.
3. `JavaMailSender.send(...)` nhận **một MimeMessage**.
4. MimeMessage có subject, To và From đúng.
5. MIME tree chứa cả `text/plain` và `text/html`.
6. Không cần kết nối thật tới Mailpit cho unit test.

Ở đây sử dụng Mockito và một Jakarta Mail `Session` in-memory. Spring Boot starter test cung cấp Mockito/JUnit theo version dependency management.

### Test setup

```java
package com.example.maildemo.mail;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import java.util.Properties;

import com.example.maildemo.config.DemoMailProperties;
import jakarta.mail.Address;
import jakarta.mail.Message;
import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.javamail.JavaMailSender;

import org.thymeleaf.TemplateEngine;
import org.thymeleaf.TemplateMode;
import org.thymeleaf.spring6.SpringTemplateEngine;
import org.thymeleaf.templateresolver.ClassLoaderTemplateResolver;

class OrderMailServiceTest {

    private JavaMailSender sender;
    private OrderMailService service;

    @BeforeEach
    void setUp() {
        sender = mock(JavaMailSender.class);

        when(sender.createMimeMessage()).thenAnswer(invocation ->
            new MimeMessage(Session.getInstance(new Properties()))
        );

        ClassLoaderTemplateResolver resolver =
            new ClassLoaderTemplateResolver();

        resolver.setPrefix("templates/");
        resolver.setSuffix(".html");
        resolver.setTemplateMode(TemplateMode.HTML);
        resolver.setCharacterEncoding("UTF-8");
        resolver.setCacheable(false);

        SpringTemplateEngine engine = new SpringTemplateEngine();
        engine.setTemplateResolver(resolver);

        DemoMailProperties properties = new DemoMailProperties(
            "no-reply@example.test",
            "Demo Workspace",
            "support@example.test",
            "http://localhost:8080"
        );

        OrderMailRenderer renderer =
            new OrderMailRenderer(engine, properties);

        service = new OrderMailService(
            sender, renderer, properties
        );
    }

    @Test
    void sendsPlainAndHtmlAlternatives() throws Exception {
        OrderMailRequest request = new OrderMailRequest(
            "buyer@example.test",
            "Nguyễn An",
            "ORD-2026-001"
        );

        SubmissionReceipt receipt =
            service.submitOrderConfirmation(request);

        assertEquals("SUBMITTED", receipt.submissionStatus());
        assertNotNull(receipt.notificationId());

        ArgumentCaptor<MimeMessage> captor =
            ArgumentCaptor.forClass(MimeMessage.class);

        verify(sender, times(1)).send(captor.capture());

        MimeMessage actual = captor.getValue();
        actual.saveChanges();

        assertEquals(
            "Xác nhận đơn hàng ORD-2026-001",
            actual.getSubject()
        );

        Address[] recipients =
            actual.getRecipients(Message.RecipientType.TO);

        assertEquals(1, recipients.length);
        assertEquals(
            "buyer@example.test",
            ((InternetAddress) recipients[0]).getAddress()
        );

        String plain = MimeParts.findText(
            actual, "text/plain"
        );
        String html = MimeParts.findText(
            actual, "text/html"
        );

        assertNotNull(plain);
        assertNotNull(html);
        assertTrue(plain.contains("ORD-2026-001"));
        assertTrue(plain.contains("Nguyễn An"));
        assertTrue(plain.contains(
            "http://localhost:8080/orders/ORD-2026-001"
        ));

        assertTrue(html.contains("Xác nhận đơn hàng"));
        assertTrue(html.contains("Nguyễn An"));
        assertTrue(html.contains("ORD-2026-001"));
    }
}
```

Dòng `org.thymeleaf.spring6.SpringTemplateEngine` phù hợp với Thymeleaf tích hợp Spring Framework 6 trong ví dụ Boot 3.x. Khi nâng sang framework generation khác, imports có thể thay đổi theo dependency version.

Trong unit test, `verify(sender).send(...)` chứng minh **service đã gọi JavaMailSender một lần**, không chứng minh một SMTP relay thật đã nhận email. Kiểm thử transport cần SMTP catcher hoặc test server riêng.

## 35. Helper duyệt MIME tree trong test

Với multipart mode nhiều lớp, không được ép thẳng:

```java
String body = (String) mime.getContent();
```

Top-level `getContent()` có thể là `Multipart`, không phải `String`.

Tạo test helper `MimeParts`:

```java
package com.example.maildemo.mail;

import jakarta.mail.Multipart;
import jakarta.mail.Part;

final class MimeParts {

    private MimeParts() {}

    static String findText(
            Part part, String wantedType) throws Exception {

        if (Part.ATTACHMENT.equalsIgnoreCase(
                part.getDisposition())) {
            return null;
        }

        if (part.isMimeType(wantedType)) {
            Object content = part.getContent();

            if (content instanceof String text) {
                return text;
            }
        }

        if (part.isMimeType("multipart/*")) {
            Multipart multipart =
                (Multipart) part.getContent();

            for (int i = 0; i < multipart.getCount(); i++) {
                String found = findText(
                    multipart.getBodyPart(i),
                    wantedType
                );

                if (found != null) {
                    return found;
                }
            }
        }

        return null;
    }
}
```

Lý do phải duyệt đệ quy: HTML/plain thường nằm trong `multipart/alternative` lồng dưới `multipart/related` hoặc `multipart/mixed`.

Đây là test helper cho email demo, không phải một MIME parser an toàn cho mọi email từ Internet. Parser production cần giới hạn nesting depth, số parts, tổng decoded bytes và xử lý nested `message/rfc822`/malformed MIME.

## 36. Test HTML escaping bằng dữ liệu tổng hợp

Một test bổ sung:

```java
@Test
void escapesUntrustedCustomerNameInHtml() {
    OrderMailRequest request = new OrderMailRequest(
        "buyer@example.test",
        "<img src=x onerror=alert(1)>",
        "ORD-2026-002"
    );

    RenderedMail rendered =
        renderer.render(request);

    assertFalse(rendered.htmlText().contains(
        "<img src=x onerror=alert(1)>"
    ));
    assertTrue(rendered.htmlText().contains(
        "&lt;img"
    ));
}
```

Đoạn test này cần field `renderer` ở test class được khởi tạo thay vì local variable trong `setUp`; ví dụ minh họa cách assert HTML escaping ở mức renderer. Có thể tách nó thành class `OrderMailRendererTest` với cùng setup Thymeleaf resolver để giữ test focused.

Thymeleaf `th:text` escape HTML meta characters trong text context. **Không dựa vào regex validator của `customerName` để chống HTML injection**; HTML escaping phải diễn ra ở output context.

Một chuỗi JavaScript dạng text trong HTML vẫn có thể xuất hiện dưới dạng chữ được escape; điều cần kiểm tra là nó không trở thành markup thực thi.

## 37. Test đối chiếu nội dung plain và HTML

Trong thực hành, hãy lập một bảng assertions cho cả hai body:

| Nội dung | Plain text | HTML |
| --- | --- | --- |
| Customer name | Có | Có, escaped |
| Order code | Có | Có |
| Absolute URL | Có | Có trong `href` |
| Support guidance | Có | Có |
| Subject | Không cần lặp trong body | Có thể có heading |
| HTML tags | Không có markup bắt buộc | Có markup |
| Text-only readability | Có | Không áp dụng |

Đừng kiểm tra HTML bằng một chuỗi nguyên vẹn khớp tất cả whitespace và thứ tự CSS. Template engines có thể thay đổi formatting. Test vào **semantic content**, escaped values và MIME parts.

Với URL, kiểm tra thuộc allowed domain và không có redirect/tracking token không cần thiết.

## 38. Kiểm thử end-to-end với SMTP catcher

Ngoài Mockito, chạy ứng dụng thực với Mailpit và gửi request:

```text
HTTP request
      |
      v
Spring Controller
      |
      v
Renderer + MimeMessageHelper
      |
      v
JavaMailSenderImpl
      |
      v
TCP localhost:1025
      |
      v
Mailpit SMTP
      |
      v
Captured MIME + UI
```

Các mục cần xác nhận bằng Mailpit:

1. Có đúng **một** message trong một lần gọi API.
2. Subject hiển thị tiếng Việt không lỗi encoding.
3. From display name có dấu nếu đổi từ config.
4. To và Reply-To đúng.
5. HTML hiển thị nút link và escape customer name.
6. Plain text có nội dung thực, không phải `<p>...</p>`.
7. MIME source chứa cả `text/plain` và `text/html`.
8. `Content-Type` của từng part có charset phù hợp.
9. Khi Mailpit ngừng chạy, API báo lỗi submission.
10. Không bị gọi SMTP lần thứ hai tự động nếu client chỉ gửi một request.

Mailpit capture là test **submission và MIME content**, không phải kiểm thử khả năng vào Inbox của Gmail/Outlook hoặc email reputation.

## 39. Tắt Mailpit để thử lỗi kết nối

Trong môi trường local:

```bash
docker compose stop mailpit
```

Gọi lại API. Nếu Spring Mail kết nối tới `localhost:1025` không được, có thể phát sinh `MailSendException` hoặc một subtype của `MailException`. Controller advice trả lỗi an toàn.

Sau đó bật lại:

```bash
docker compose start mailpit
```

Điều cần hiểu:

- Lỗi connect rõ ràng trước khi gửi message có thể retry theo chính sách.
- Demo hiện tại **không có queue và không tự retry**.
- HTTP caller tự retry có thể tạo email mới nếu response trước đó không rõ kết quả.
- Khi thêm production outbox phải giữ notification ID ổn định, idempotency và phân loại lỗi.

Không bắt đầu bằng `@Retryable(retryFor=MailException.class)` cho mọi exception rồi tuyên bố không bao giờ mất/trùng thư.

## 40. Tại sao dùng plain-text alternative vẫn quan trọng khi HTML đẹp?

Các lợi ích:

- Hỗ trợ email clients không render HTML.
- Hỗ trợ cách đọc văn bản đơn giản.
- Tăng khả năng truy cập nội dung chính trong nhiều môi trường.
- Phù hợp người dùng chọn chế độ chỉ nhận plain text.
- Giúp hệ thống xử lý mail tự động tìm thông tin dạng text.
- Có thể được provider/client xử lý khác nhau khi filtering.

Nhưng plain text **không tự bảo đảm deliverability**. Chất lượng giao thư còn phụ thuộc xác thực domain, sender reputation, consent, bounce rate, danh tiếng IP, nội dung, provider và recipient policies.

Đừng thêm plain text chỉ bằng một chuỗi rỗng. Cần để người nhận thực sự hiểu ý nghĩa thông điệp.

## 41. Tạo bản plain text dài bằng template riêng

Khi email dài, hardcode `String.formatted` có thể khó bảo trì. Bạn có thể đặt một file text template riêng:

```text
Xin chào [[${customerName}]],

Đơn hàng [[${orderCode}]] của bạn đã được ghi nhận.

Xem đơn hàng: [[${orderUrl}]]

Trân trọng,
Demo Workspace
```

Đây là syntax inline expression của Thymeleaf **trong ngữ cảnh TEXT template mode**, không phải file `.txt` bất kỳ tự được Spring Boot Thymeleaf HTML resolver xử lý đúng.

Nếu triển khai:

- Dùng resolver `TemplateMode.TEXT` có prefix/suffix riêng.
- Đảm bảo không xung đột với resolver HTML.
- Dùng cùng `Context`/render model cho cả hai.
- Kiểm soát xuống dòng và whitespace.
- Test không có HTML entities/escaping không mong muốn trong plain.

Với bài demo nhỏ, plain text trong Java giúp giảm cấu hình. Khi số template tăng, một hệ thống template riêng cho text và HTML có thể rõ ràng hơn.

## 42. Không dùng th:utext trên dữ liệu người dùng

Trong Thymeleaf:

```html
<span th:text="${customerName}">Tên</span>
```

là lựa chọn thông thường cho text từ dữ liệu.

Ngược lại:

```html
<span th:utext="${customerName}">Tên</span>
```

có thể đưa **HTML chưa escaped** vào email. Nếu customer name là markup, phần markup đó có thể trở thành HTML thực thay vì văn bản.

Email clients có thể sanitize một phần HTML, nhưng **không được dựa vào client để đảm bảo nội dung an toàn**. Với rich content được author kiểm soát, cần pipeline sanitize/trust boundary riêng.

Bài học này chỉ dùng `th:text` và các field được validation.

## 43. URL trong email cần được kiểm soát từ server

Ví dụ:

```java
String orderUrl =
    properties.publicBaseUrl()
        + "/orders/" + request.orderCode();
```

chỉ hợp lý khi:

- `publicBaseUrl` thuộc domain tin cậy trong config.
- `orderCode` được giới hạn ký tự phù hợp.
- Endpoint `/orders/{id}` yêu cầu authentication/authorization.
- URL không chứa bearer token hoặc secret bền vững.
- Không tự sử dụng Host header từ HTTP request để xây email link.

Trong ứng dụng thật, tốt hơn dùng một URL builder có encode path segments và có allowlist HTTPS. Khi order code có ký tự không phải `[A-Z0-9-]`, phải encode đúng, không nối tùy tiện.

Một email chứa link hợp lệ không có nghĩa tài liệu phía sau được công khai; hệ thống web vẫn cần resource authorization.

## 44. Có cần gửi ảnh logo không?

Không bắt buộc. Dự án đầu tiên nên tập trung đúng hai alternatives.

Nếu sau này cần inline logo:

```java
MimeMessageHelper helper =
    new MimeMessageHelper(mime, true, "UTF-8");

helper.setText(plainText, htmlText);

// HTML chứa: <img src="cid:companyLogo">
helper.addInline(
    "companyLogo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
```

Với inline CID, HTML và Content-ID phải khớp. Theo cách dùng thông thường của helper, nên đặt `setText(...)` trước khi thêm inline resources.

Trong JAR, `ClassPathResource` không nhất thiết có file path thật trên filesystem; tránh gọi `getFile()` rồi giả định luôn thành công. Dùng resource/input stream được API hỗ trợ.

Inline image là MIME part khác, **không thay text/plain**. Không nên log raw image bytes để debug email.

## 45. Nếu thêm PDF attachment thì sao?

Một extension:

```java
helper.setText(plainText, htmlText);

helper.addAttachment(
    "invoice.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);
```

Cần import:

```java
import org.springframework.core.io.ByteArrayResource;
```

Thứ tự minh họa: dựng plain/html alternatives, rồi thêm attachment vào MIME.

Các lưu ý production:

- Giới hạn kích thước PDF và tổng MIME.
- `ByteArrayResource` giữ toàn bộ bytes trong memory; chỉ phù hợp file nhỏ.
- Với file lớn, dùng resource/`InputStreamSource` có stream **repeatable**.
- Không để attachment filename chứa path nội bộ hoặc PII không cần thiết.
- Kiểm tra quyền truy cập tài liệu trước khi gửi.
- Dung lượng message sau MIME/base64 có thể lớn hơn file gốc.
- MIME vẫn phải có plain/html alternatives.

Không đặt attachment bytes vào JSON request hoặc logs của hệ thống.

## 46. MIME parts và thứ tự ưu tiên của client

Nhiều email clients có thể chọn cách hiển thị từ các parts alternative. Cấu trúc chuẩn mang tính ý tưởng:

```text
multipart/alternative
  1. text/plain
  2. text/html
```

Một số clients hiển thị HTML vì hỗ trợ rich content; những clients khác có thể hiển thị text. **Không có nghĩa email gửi thành hai bản**.

Test không nên phụ thuộc trực tiếp vào thứ tự MIME boundary raw string vì helper có thể bọc parts vào `mixed`/`related`. Tốt hơn parse MIME tree và tìm types, kiểm tra nội dung.

Khi muốn làm email có cả HTML/plain và attachment, dùng helper với multipart mode hỗ trợ layout phức tạp; đừng tự gắn Content-Type top-level `text/html` sau khi helper đã tạo multipart.

## 47. Có nên tự đặt Content-Type header không?

Không cần:

```java
mime.setHeader("Content-Type", "text/html; charset=UTF-8");
```

sau khi đã dùng `MimeMessageHelper#setText(plain, html)`. Việc ghi đè Content-Type top-level có thể phá cấu trúc multipart vì actual content là nhiều parts chứ không phải một HTML string.

Hãy để helper/Jakarta Mail tạo MIME headers, encoding và boundaries phù hợp. Nếu muốn tùy chỉnh charset, dùng constructor helper với encoding; nếu muốn HTML-only, dùng overload thích hợp nhưng phải hiểu đánh đổi.

Header `MIME-Version`, `Content-Transfer-Encoding` và multipart boundaries là phần kỹ thuật transport; không xây bằng string nối thủ công trong service.

## 48. Sự khác nhau giữa SimpleMailMessage và MimeMessage

| Khả năng | `SimpleMailMessage` | `MimeMessage` + helper |
| --- | --- | --- |
| Plain text đơn giản | Có | Có |
| HTML riêng | Không phải mục đích chính | Có |
| Plain + HTML alternative | Không | Có |
| Multipart attachment | Không | Có |
| Inline CID image | Không | Có |
| Unicode subject | Có qua mail sender | Có, cấu hình rõ MIME |
| Rich MIME headers | Hạn chế | Có |
| MIME tree kiểm thử được | Không theo dạng MIME object | Có |

`SimpleMailMessage` phù hợp notification plain text đơn giản. Nhưng nếu yêu cầu bài học là **cả HTML và plain text trong một email**, dùng `JavaMailSender` với `MimeMessageHelper`.

## 49. Bảng lỗi thường gặp và cách sửa

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| HTML hiện nguyên `<p>` | Đang gửi như text/plain | Dùng `setText(plain, html)` |
| Mail chỉ có HTML | Dùng `setText(html, true)` | Thêm bản plain trong overload hai String |
| Helper báo không ở multipart mode | Khởi tạo helper với `false` | Dùng multipart mode phù hợp |
| Subject tiếng Việt bị lỗi | Encoding source/helper/resource | Dùng UTF-8 end-to-end |
| Không tìm thấy template | Sai đường dẫn/suffix resolver | `templates/mail/order-confirmation.html` |
| Tên có `<script>` ảnh hưởng markup | Dùng unescaped HTML | Dùng `th:text`/escaping |
| Link trỏ domain lạ | Base URL từ request chưa kiểm tra | Server-side allowlisted base |
| SMTP connection refused | Mailpit chưa chạy hoặc sai host/port | Kiểm tra `localhost:1025` và container network |
| SMTP AUTH lỗi production | Credentials/mechanism sai | Dùng secret/config provider |
| STARTTLS/certificate lỗi | TLS/hostname/cert không đúng | Kiểm tra provider TLS requirements |
| Mailpit không thấy thư | Profile/config port sai | Kiểm tra app logs an toàn, SMTP host |
| Bị gửi hai email | API gọi hai lần hoặc code gửi hai messages | Kiểm tra requests/idempotency |
| MIME source có multipart/mixed | Helper mode có wrapper | Tìm nested alternative parts |
| Attachment rỗng | Stream không repeatable | Dùng repeatable InputStreamSource |
| Test cast Multipart sang String lỗi | Top-level multipart | Duyệt MIME recursively |
| HTTP 502 dù email có thể đã tới | Timeout sau DATA | Phân loại AMBIGUOUS; tránh retry mù |

Bảng giúp kiểm tra từ **content preparation** tới **SMTP submission**, không coi tất cả lỗi là cùng một loại.

## 50. SMTP accepted không đồng nghĩa delivered

Một phản hồi demo:

```json
{
  "notificationId": "opaque-uuid",
  "submissionStatus": "SUBMITTED"
}
```

có nghĩa ứng dụng đã gọi sender mà không gặp lỗi được ném. Nó không chứng minh:

- Mailbox đích tồn tại.
- Email vào Inbox thay vì Spam.
- Recipient đã đọc.
- Link đã được nhấp.
- Provider không gửi bounce sau đó.

Trong local Mailpit, ý nghĩa là SMTP catcher đã tiếp nhận để hiển thị. Trong production, ứng dụng cần provider delivery/bounce events nếu muốn theo dõi downstream status.

Một lần HTTP request bị timeout **không đủ** để kết luận relay chưa accepted. Đây là lý do cần idempotent command hoặc durable outbox khi thêm API thật.

## 51. Vì sao demo dùng đồng bộ nhưng production thường cần outbox?

Demo:

```text
HTTP request
    |
    v
Build MimeMessage
    |
    v
JavaMailSender.send()
    |
    v
HTTP response
```

Đơn giản và rất phù hợp để hiểu `MimeMessageHelper`. Nhưng với hệ thống giao dịch:

- SMTP chậm có thể khiến HTTP request timeout.
- Nếu business transaction commit xong rồi SMTP fail, email intent có thể mất.
- Client retry HTTP dễ tạo duplicate.
- Process restart có thể mất in-memory work.
- Không có durable attempt history.
- Không có rate limit/retry policy/bounce tracking.

Một kiến trúc production:

```text
Business transaction
  +--> Order state update
  +--> Mail outbox intent
  |
  v
COMMIT
  |
  v
Background worker
  |
  +--> Load content or immutable snapshot
  +--> Render HTML + plain
  +--> Build MimeMessageHelper
  +--> SMTP submit
  +--> Persist outcome
  |
  v
Provider delivery events / reconciliation
```

Phần **render HTML/plain và tạo MIME** vẫn dùng lại được. Chỉ cách kích hoạt và lưu trạng thái thay đổi.

Không giữ database transaction mở qua `JavaMailSender.send(...)`, vì SMTP side effect không thể rollback cùng DB transaction.

## 52. Chọn điểm render khi có retry

Có hai chiến lược:

**Render một lần, lưu snapshot/immutable content:**

- Các attempts của cùng notification giữ nguyên subject/body/version.
- Phù hợp hóa đơn hoặc email cần audit.
- Phải bảo vệ HTML/text và artifact references trong storage.
- Phải lưu có mã hóa, ACL và retention phù hợp.

**Render lại mỗi attempt:**

- Có thể lấy dữ liệu mới hơn.
- Dễ thay đổi nội dung giữa attempts của một notification.
- Template upgrade có thể làm HTML và plain không nhất quán nếu lấy version khác.
- Link/OTP có thể hết hạn.

Với email giao dịch, thiết kế cần quyết định rõ content version và source of truth. Không giả định application retry luôn được phép dùng lại token bảo mật cũ.

## 53. Tái sử dụng MailService mà không tạo duplicate

Một outbox worker có thể có method:

```java
public void process(MailJob job) {
    if (!eligibility.canSend(job)) {
        states.markSuppressed(job);
        return;
    }

    PreparedMail prepared = renderer.prepare(job);

    try {
        mailSubmissionPort.submit(prepared);
        states.markSubmitted(job);
    } catch (TransientMailFailure exception) {
        states.scheduleRetry(job);
    } catch (AmbiguousMailFailure exception) {
        states.markAmbiguous(job);
    }
}
```

Đây là pseudocode domain, không phải API mặc định của Spring Mail. Nó nhấn mạnh:

- Retry thuộc orchestration/outbox.
- MIME rendering thuộc renderer/builder.
- SMTP sending thuộc adapter.
- State updates cần owner/lease/version guards.
- Không retry mù khi SMTP outcome chưa rõ.

Bản demo trực tiếp chưa có các thành phần này và không nên được xem là hệ thống gửi production hoàn chỉnh.

## 54. Logging an toàn khi gửi HTML

Không làm:

```java
log.info("mail={}", mimeMessage);
log.debug("html={}", renderedMail.htmlText());
log.debug("plain={}", renderedMail.plainText());
```

Các body có thể chứa tên, số đơn, địa chỉ, URL token, dữ liệu thanh toán và attachments.

Một event gọn:

```java
log.info(
    "event=mail.smtp.submitted notificationId={} "
        + "category={} durationMs={}",
    notificationId,
    "ORDER_CONFIRMATION",
    elapsedMs
);
```

Nếu provider lỗi, ghi normalized failure class/SMTP code khi an toàn; không in raw exception chứa recipient/SMTP transcript vào logs phổ rộng.

Không bật `mail.debug=true` hoặc `Session.setDebug(true)` trên production để xem toàn bộ MIME, vì protocol debug có thể lộ thông tin giao thức, recipients và/hoặc payload.

## 55. Bảo vệ endpoint gửi mail

Dù API demo chỉ chạy trong profile `local`, khi triển khai thực cần:

1. Authentication cho caller.
2. Authorization trên order/resource.
3. Recipient được resolve từ order/customer đã xác thực.
4. Rate limit theo user/tenant/IP/campaign.
5. Idempotency key cho command gửi.
6. Suppression/consent policy theo loại email.
7. From/domain được provider xác thực.
8. Template key được allowlist; không cho arbitrary HTML từ client.
9. Giới hạn subject/HTML/attachment size.
10. CSRF/CORS settings phù hợp theo auth model.
11. Audit ai yêu cầu gửi và vì sao.
12. Business expiry/quiet hours khi áp dụng.
13. SMTP credentials trong secret manager.
14. TLS và hostname verification production.
15. Không public Mailpit/capture UI ra Internet.

Một endpoint “test send” không được triển khai thành open relay chỉ vì nó dùng `JavaMailSender` hợp lệ.

## 56. Nếu triển khai Spring Integration Mail

Trong Spring Integration, `Message<?>` có payload và headers; nó không giống Jakarta `MimeMessage`. Nếu cần gửi rich email:

```text
Business event
      |
      v
Spring Integration Message<MailIntent>
      |
      v
Transformer / service activator
      |
      v
RenderedMail + MimeMessageHelper
      |
      v
JavaMailSender.send(MimeMessage)
```

Hoặc dùng các outbound mapping do Spring Integration Mail hỗ trợ cho payload đơn giản. Nhưng email HTML/plain alternative trong bài này dễ kiểm soát bằng một service activator/custom adapter xây `MimeMessage` tường minh.

Không giả định set header `contentType=text/html` trên Spring Integration `MessageHeaders` tự tạo cả MIME alternative. Cần explicit mapping tại boundary.

## 57. Checklist bàn giao của dự án thực hành

- [ ] Maven có Mail, Web, Validation và Thymeleaf dependencies.
- [ ] JDK/Boot/Jakarta Mail packages tương thích.
- [ ] Mailpit local SMTP đang chạy.
- [ ] Spring Boot dùng profile `local`.
- [ ] SMTP host/port đúng, debug mặc định tắt.
- [ ] `DemoMailProperties` bind From, From name, Reply-To, URL.
- [ ] Request DTO validate email/name/orderCode.
- [ ] HTML template có `th:text` cho dynamic text.
- [ ] URL dùng base config tin cậy, không Host header user input.
- [ ] Plain-text bản riêng có đầy đủ thông tin.
- [ ] Renderer trả `RenderedMail(subject,plain,html)`.
- [ ] Service tạo `MimeMessage` bằng `JavaMailSender`.
- [ ] Helper ở multipart mode với `"UTF-8"`.
- [ ] `helper.setText(plainText, htmlText)` gọi đúng thứ tự.
- [ ] Service gọi `sender.send(mime)` **một lần**.
- [ ] Mailpit hiển thị đúng một email và cả hai alternatives.
- [ ] Subject/tên tiếng Việt hiển thị đúng.
- [ ] Test duyệt MIME tree, không cast top-level thành String.
- [ ] HTML escaping được thử bằng dữ liệu tổng hợp.
- [ ] Khi SMTP unavailable, API có error thay vì báo delivered.
- [ ] Không log raw MIME, recipient, OTP hoặc attachment.
- [ ] Phân biệt demo synchronous và production outbox/idempotency.

## 58. Bài tập mở rộng có hướng dẫn

**Bài tập 1 — Tùy chỉnh nội dung**

Thêm `shippingDate` vào request model cho demo; bổ sung câu tương ứng trong cả plain và HTML, dùng format theo locale Việt Nam. Assert cả hai alternatives có thông tin cùng ý nghĩa.

**Bài tập 2 — Đường dẫn an toàn**

Dùng URI/path builder để encode order path segment thay vì nối chuỗi khi order code cho phép ký tự đặc biệt. Đảm bảo base URL được allowlist và production dùng HTTPS.

**Bài tập 3 — Inline logo**

Đặt một logo test vào classpath, tham chiếu bằng `cid:companyLogo` trong HTML, gọi `addInline` sau `setText`, rồi xác nhận MIME có Content-ID tương ứng. Plain text vẫn giữ nội dung không phụ thuộc hình ảnh.

**Bài tập 4 — PDF attachment**

Thêm một PDF fixture nhỏ bằng `ByteArrayResource`, xác minh content type/filename/bytes. Đảm bảo không log attachment và kiểm soát dung lượng khi mở rộng.

**Bài tập 5 — Template version**

Đặt `templateVersion` vào render model và ghi version trong notification metadata. Khi retry cùng logical intent, quyết định xem cần dùng snapshot cũ hay render lại một cách có chủ đích.

**Bài tập 6 — Unit test chất lượng nội dung**

Tạo test bảo đảm plain có link thật, HTML escape dữ liệu và MIME có đúng hai alternative body types. Không kiểm thử bằng cách so sánh toàn bộ raw MIME bytes, vì boundaries/encoded headers có thể thay đổi.

**Bài tập 7 — Production outbox**

Thay API đồng bộ bằng lệnh ghi notification intent vào database, thêm worker `@Scheduled` claim và gửi sau commit, có idempotency/lease/retry. Không coi việc thêm `@Async` đơn thuần là durable queue.

## 59. Câu hỏi tự kiểm tra

1. Vì sao gửi hai emails riêng (một HTML, một text) không giống MIME alternative?
2. Overload `setText(String, boolean)` khác `setText(String, String)` thế nào?
3. Vì sao `setText(plain, html)` cần multipart mode?
4. Một email có `multipart/mixed` top-level có thể chứa `multipart/alternative` không?
5. Vì sao không nên sinh plain text bằng regex xóa HTML tags?
6. Vì sao HTML từ user input cần escape dù email clients có sanitization?
7. Khi From display name có tiếng Việt, cần quan tâm charset ở đâu?
8. `JavaMailSender.send()` thành công có chứng minh Inbox delivery không?
9. Nếu Mailpit không nhận thư, những điểm cấu hình nào cần xem trước?
10. Vì sao API demo dùng `@Profile("local")` mà production vẫn cần auth/authorization?
11. Nếu HTTP client retry vì timeout, điều gì có thể gây duplicate email?
12. Làm thế nào kiểm tra HTML và plain trong MIME tree mà không cast sai kiểu?
13. Khi thêm attachment, MIME structure thay đổi thế nào?
14. Trong production, renderer, outbox worker và SMTP adapter nên phân quyền trách nhiệm ra sao?
15. Email OTP có được resend nguyên raw HTML khi token đã hết hạn không?

Các câu hỏi này hướng vào hiểu bản chất MIME và ranh giới production, không chỉ nhớ vài dòng cấu hình.

## 60. Tóm tắt

- `JavaMailSender` là thành phần gửi mail qua SMTP; `MimeMessageHelper` là helper xây email MIME.
- Plain text và HTML **không phải hai emails**, mà là hai alternative parts trong một thông điệp.
- Dùng overload **`helper.setText(plainText, htmlText)`** để cung cấp cả hai phần.
- Khởi tạo helper với **multipart mode** và `"UTF-8"` để hỗ trợ alternative/tiếng Việt.
- Dùng `th:text` trong Thymeleaf cho dữ liệu động, tránh nối HTML không escaped.
- Plain text nên có nội dung được viết riêng, đầy đủ mã đơn và URL.
- Top-level MIME có thể là `multipart/mixed` hoặc `related`; hãy tìm nested `multipart/alternative`.
- Mailpit phù hợp kiểm thử local mà không gửi tới mailbox thật.
- Mockito test kiểm tra service và MIME; SMTP capture test kiểm tra transport boundary.
- From/Reply-To là mail headers, không phải SMTP credentials.
- Địa chỉ To từ request chỉ phù hợp demo giới hạn; production phải xác thực business resource/recipient.
- `send()` success có nghĩa submission ở hop hiện tại, không chứng minh delivered hay opened.
- Không retry mù sau timeout vì SMTP relay có thể đã accepted.
- Khi mở rộng production, giữ renderer/builder nhưng đưa orchestration vào durable outbox, có idempotency, quota và audit.

**Kết quả đạt được:** ứng dụng có thể tạo một `MimeMessage` với **bản HTML trình bày đẹp** và **bản plain text dễ đọc**, từ cùng dữ liệu đơn hàng, qua `MimeMessageHelper` và `JavaMailSender`. Cách triển khai này tạo nền tảng rõ ràng để bổ sung attachment, inline image, template version, retry/outbox và theo dõi provider trong các bước tiếp theo mà vẫn giữ đúng ranh giới giữa nội dung email và việc gửi thư.
