# spring-boot-starter-mail và các dependency liên quan

Trong ứng dụng **Spring Boot**, chức năng gửi email thường bắt đầu bằng một dòng dependency:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Dòng khai báo nhỏ này có ý nghĩa lớn: nó đưa những thành phần cần thiết để **tạo và gửi email bằng Spring Mail** vào classpath, đồng thời cho phép **Spring Boot auto-configuration** tạo một mail sender từ cấu hình của ứng dụng. Ta có thể inject `JavaMailSender` rồi gửi plain text hoặc dựng thông điệp MIME gồm HTML, file đính kèm và hình ảnh.

Tuy nhiên, thêm starter **không đồng nghĩa email tự được gửi**. Ứng dụng còn phải có SMTP server hoặc dịch vụ gửi mail phù hợp, cấu hình kết nối và quyền xác thực; tầng nghiệp vụ vẫn phải quyết định ai nhận thư, nội dung là gì và khi nào thực hiện gửi.

Bài học giải thích starter cung cấp gì, các dependency nào là trực tiếp hoặc bắc cầu, cách quản lý phiên bản, khi nào cần bổ sung thư viện và cách tránh lỗi cấu hình classpath thường gặp.

## 1. Starter trong Spring Boot là gì?

**Starter** là một artifact đóng vai trò tập hợp các dependency liên quan đến một nhóm chức năng theo quy ước của Spring Boot. Thay vì phải tra cứu và khai báo riêng từng thư viện nền tảng, ứng dụng khai báo starter tương ứng để Boot quản lý bộ thành phần thích hợp.

Với gửi mail, dependency chính là:

~~~text
Group   : org.springframework.boot
Artifact: spring-boot-starter-mail
~~~

Mô hình tổng quát:

~~~mermaid
flowchart TD
    A["Ứng dụng Spring Boot"] --> B["spring-boot-starter-mail"]
    B --> C["Spring Mail support"]
    B --> D["Jakarta Mail API / provider"]
    B --> E["Các dependency Boot và Spring cần thiết"]
    F["spring.mail.*"] --> G["Mail sender auto-configuration"]
    C --> G
    D --> G
    G --> H["JavaMailSender"]
    H --> I["SMTP server"]
~~~

Trong các dự án Spring Boot 3.x điển hình, starter liên quan đến **`spring-context-support`** của Spring Framework và một **Jakarta Mail implementation** (thường thuộc họ Angus Mail), cùng các dependency nền tảng cần thiết. Các artifact bắc cầu và phiên bản cụ thể phụ thuộc **phiên bản Spring Boot** đang dùng; hãy xem cây dependency thực tế của dự án để biết chính xác.

Starter giải quyết hai nhu cầu:

1. **Đưa API và implementation cần dùng vào classpath**, chẳng hạn `JavaMailSender` và các lớp Jakarta Mail.
2. **Kết hợp với auto-configuration của Spring Boot** để có thể tạo bean sender từ thuộc tính `spring.mail.*`.

Starter **không** tự tạo template nội dung, REST controller, hàng đợi gửi thư, dịch vụ nhận email, bảng lưu lịch sử hay cơ chế theo dõi thư đã đến hộp nhận.

## 2. Khai báo dependency bằng Gradle và Maven

### 2.1. Gradle Groovy DSL

Trong một **module Spring Boot đã được thiết lập quản lý phiên bản dependency**, thêm:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

`implementation` đưa dependency vào compile classpath và runtime classpath của module dùng nó; nó phù hợp với ứng dụng chỉ cần dùng mail nội bộ. Nếu đây là một thư viện dùng chung và public API của thư viện trực tiếp phơi bày kiểu của Spring Mail cho module khác, cần xem lại ranh giới API và scope dependency tương ứng; không tự đổi mọi khai báo thành `api`.

Khi dùng Spring Boot Gradle plugin **cùng cơ chế dependency management phù hợp**, bạn thường không cần tự khai báo version riêng cho starter vì phiên bản được quản lý đồng bộ với Spring Boot. Với Gradle dự án không sử dụng cách quản lý phiên bản này, phải thiết lập BOM/platform hoặc cơ chế tương đương.

### 2.2. Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-mail")
}
~~~

Cách khai báo tương đương về ý nghĩa; khác biệt chính nằm ở cú pháp build script. Nếu project đa module dùng version catalog, có thể tạo alias và dùng alias đó, miễn toàn bộ dependency vẫn được quản lý tương thích với Spring Boot của dự án.

### 2.3. Maven

Trong dự án Maven đã sử dụng `spring-boot-starter-parent` hoặc import Spring Boot dependency BOM:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-mail</artifactId>
    </dependency>
</dependencies>
~~~

Khi parent/BOM quản lý phiên bản, bạn không cần thêm `<version>` vào dependency này. Nếu Maven project không có parent hoặc BOM phù hợp thì phải cấu hình version management riêng trước; việc bỏ version mà không có quản lý dependency sẽ không hoạt động.

### 2.4. Quản lý phiên bản bằng Spring Boot BOM

Spring Boot phát hành bộ phiên bản dependency đã được kiểm tra tính tương thích. Một ứng dụng Gradle sử dụng native BOM support có thể khai báo theo mô hình:

~~~groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:<boot-version>')
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

`<boot-version>` trong đoạn minh họa là **placeholder**, không phải phiên bản chạy được. Hãy dùng đúng phiên bản đã được dự án lựa chọn và bảo đảm tương thích với Boot plugin, Java và Spring Framework. Nếu build đã import Spring Boot BOM theo cơ chế khác thì không thêm một nguồn version management thứ hai không cần thiết.

Không nên tùy tiện gán phiên bản riêng cho `spring-context-support` hoặc Jakarta Mail provider chỉ để “lấy bản mới nhất”. Việc ghi đè các phiên bản bắc cầu có thể làm phát sinh lỗi ở runtime. Khi cần nâng cấp để sửa lỗi bảo mật hoặc tương thích, nên chọn phiên bản Spring Boot phù hợp trước, sau đó kiểm tra đầy đủ dependency tree và thử nghiệm tích hợp.

## 3. Những lớp dependency chính và trách nhiệm của chúng

Có ba lớp cần phân biệt: **Spring Mail API**, **Jakarta Mail API và implementation**, và **Spring Boot auto-configuration**.

| Thành phần | Thư viện hoặc package tiêu biểu | Vai trò |
| --- | --- | --- |
| Spring Boot starter | `org.springframework.boot:spring-boot-starter-mail` | Gom các dependency mail phù hợp với Spring Boot |
| Spring Framework Mail | `org.springframework:spring-context-support`, package `org.springframework.mail.*` | Interface gửi thư, thông điệp đơn giản, helper và implementation SMTP |
| Jakarta Mail API | Package `jakarta.mail.*` và `jakarta.mail.internet.*` | Biểu diễn message, session, MIME, địa chỉ, ngoại lệ mail |
| Jakarta Mail implementation/provider | Ví dụ Angus Mail trong hệ sinh thái Jakarta | Thực thi transport/store protocol như SMTP; được đưa vào classpath theo dependency được chọn |
| Jakarta Activation | `jakarta.activation.*` | Hỗ trợ kiểu dữ liệu và nguồn nội dung cho multipart, attachment |
| Spring Boot autoconfigure | Các lớp cấu hình mail trong Spring Boot | Tạo và cấu hình sender dựa trên điều kiện classpath, bean và properties |

Bảng này mô tả **vai trò logic**, không phải khẳng định mọi artifact đều xuất hiện như dependency trực tiếp trong mọi phiên bản. Một phần có thể được kéo vào thông qua các dependency bắc cầu.

### 3.1. Spring Framework Mail: API ở tầng ứng dụng

Những lớp thường thấy:

~~~java
import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;
import org.springframework.mail.javamail.MimeMessageHelper;
~~~

- **`MailSender`:** abstraction gửi `SimpleMailMessage`.
- **`JavaMailSender`:** mở rộng `MailSender` để tạo/gửi `MimeMessage`.
- **`JavaMailSenderImpl`:** implementation phổ biến dùng Jakarta Mail để tương tác với SMTP server.
- **`SimpleMailMessage`:** mô tả email chỉ có văn bản với From, To, Reply-To, Cc, Bcc, Subject, Text.
- **`MimeMessageHelper`:** hỗ trợ cấu hình MIME như HTML, nhiều phần, hình ảnh inline và file đính kèm.
- **`MailException`:** nhóm ngoại lệ của Spring khi thao tác mail thất bại.

Đây là những lớp **thuộc Spring Framework**, không thuộc package `jakarta.mail`. Khi đọc ví dụ, đừng nhầm `JavaMailSender` với `Session` hoặc `Transport` của Jakarta Mail: chúng hoạt động ở những mức abstraction khác nhau.

### 3.2. Jakarta Mail: mô hình thông điệp và giao thức

Những kiểu thường gặp:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.InternetAddress;
~~~

Jakarta Mail định nghĩa các API cho email theo chuẩn Internet, trong đó có message, địa chỉ, MIME, session và transport. Khi thư viện/provider tương ứng có trên runtime classpath, nó xử lý những công việc như tạo nội dung MIME hoặc giao tiếp qua SMTP.

**Spring Mail không thay thế Jakarta Mail**: Spring cung cấp lớp tích hợp và abstraction thân thiện với ứng dụng, còn Jakarta Mail đảm nhiệm phần biểu diễn thông điệp và giao thức ở mức thấp hơn.

### 3.3. Jakarta Activation và tài nguyên đính kèm

Khi tạo email HTML có ảnh inline hoặc file đính kèm, các API Activation/`DataSource` giúp mô tả nguồn bytes và media type. Spring Mail cũng chấp nhận những resource của Spring Core như `ClassPathResource` và `ByteArrayResource`.

Ví dụ:

~~~java
helper.addAttachment(
    "receipt.pdf",
    new ByteArrayResource(pdfBytes),
    "application/pdf"
);
~~~

Không phải vì cần gửi PDF mà ứng dụng bắt buộc phải tự thêm một dependency Activation riêng: trong cấu hình starter Mail thông dụng, những thư viện cần thiết cho Jakarta Mail và MIME thường đã có qua dependency bắc cầu. Chỉ bổ sung artifact riêng khi cây dependency thực tế chứng minh chúng đang thiếu hoặc bạn có yêu cầu sử dụng một implementation cụ thể.

## 4. Spring Boot tự cấu hình mail sender như thế nào?

Auto-configuration là phần **Spring Boot**, kết hợp với starter và `spring.mail.*` để tạo bean phù hợp.

Diễn giải ở mức ứng dụng:

~~~text
spring-boot-starter-mail có trong dependencies
        |
        v
Có những lớp MailSender/Jakarta Mail phù hợp trên classpath?
        |
        v
Có cấu hình mail thích hợp (ví dụ spring.mail.host hoặc JNDI session)?
        |
        v
Chưa có MailSender bean do ứng dụng tự định nghĩa?
        |
        v
Spring Boot tạo/cấu hình JavaMailSender
        |
        v
@Service inject JavaMailSender và gọi send(...)
~~~

Các điều kiện và lớp cấu hình chi tiết có thể khác giữa các phiên bản Boot; mô hình trên mô tả **hành vi thường gặp trong Spring Boot 3.x**. Với SMTP thông thường, ứng dụng nên khai báo `spring.mail.host` và các thuộc tính liên quan. Nếu chưa cung cấp host/JNDI session hoặc ứng dụng đã tự định nghĩa bean sender, không nên mặc định rằng Boot chắc chắn sẽ tạo một `JavaMailSender`.

### 4.1. Cấu hình `application.yml` cho SMTP

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
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 5000
      "[mail.smtp.writetimeout]": 5000

app:
  mail:
    from: ${MAIL_FROM:no-reply@example.com}
~~~

Lưu ý:

- `spring.mail.*` là nhóm thuộc tính chuẩn cho cấu hình mail của Spring Boot.
- Các khóa `mail.smtp.*` là thuộc tính transport được Jakarta Mail provider diễn giải; trong YAML dùng cách viết `"[mail.smtp.auth]"` để giữ nguyên khóa map có dấu chấm.
- `spring.mail.default-encoding` cấu hình encoding mặc định; hữu ích với tiếng Việt và nội dung Unicode.
- `app.mail.from` là **cấu hình ứng dụng tự định nghĩa**; application service phải đọc nó và đặt header `From`.
- Các biến `SMTP_USERNAME` và `SMTP_PASSWORD` phải được cung cấp bởi môi trường nếu provider yêu cầu xác thực; không lưu mật khẩu thật trong Git.
- Ví dụ dùng `587` và STARTTLS; provider dùng implicit TLS như cổng `465` cần cấu hình `mail.smtp.ssl.enable` theo hướng dẫn tương ứng.

Tùy phiên bản Boot và mô hình cấu hình, cũng có thể cấp trực tiếp biến môi trường `SPRING_MAIL_HOST`, `SPRING_MAIL_PORT`, `SPRING_MAIL_USERNAME` và `SPRING_MAIL_PASSWORD`. Spring Boot sẽ dùng cơ chế property binding/relaxed binding để đọc những giá trị tương ứng.

### 4.2. Dependency và cấu hình là hai điều kiện khác nhau

| Trạng thái | Điều có thể xảy ra |
| --- | --- |
| Có starter, có `spring.mail.host` và cấu hình hợp lệ | Boot thường có thể tạo `JavaMailSender` |
| Có starter nhưng không cung cấp host/JNDI session | Không có sender bean tự động trong cấu hình thường gặp |
| Có classpath mail nhưng đã tự khai báo `MailSender` bean | Auto-configuration có thể nhường cho bean ứng dụng |
| Có sender bean nhưng sai host/port/credentials | Bean vẫn có thể được tạo; thao tác gửi sau đó thất bại |
| Có starter và SMTP test server local | Có thể gửi thử mà không cần nhà cung cấp email bên ngoài, nếu cấu hình phù hợp |

Tạo bean và **kết nối thực sự tới SMTP** thường là hai giai đoạn tách nhau. Mặc định, việc ứng dụng khởi động được không chứng minh SMTP host có thể truy cập, thông tin xác thực đúng hay người nhận chấp nhận thư.

Spring Boot có tùy chọn `spring.mail.test-connection=true` để thử kết nối lúc khởi động khi phù hợp. Đây là lựa chọn vận hành; nếu nhà cung cấp tạm ngừng, nó có thể làm startup thất bại. Cũng không thể suy ra một lần test-connection thành công sẽ bảo đảm mọi email được giao tới Inbox.

## 5. Ví dụ sử dụng starter: gửi email plain text

Khi starter và SMTP đã được cấu hình, application service inject `JavaMailSender`:

~~~java
package com.example.mail.application;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class NotificationMailService {
    private final JavaMailSender mailSender;
    private final String fromAddress;

    public NotificationMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendText(String recipient, String subject, String body) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(fromAddress);
        message.setTo(recipient);
        message.setSubject(subject);
        message.setText(body);

        mailSender.send(message);
    }
}
~~~

Ở đây:

1. `JavaMailSender` là **bean Spring quản lý**, ứng dụng không cần tạo `JavaMailSenderImpl` trong method gửi.
2. Địa chỉ `From` được lấy từ cấu hình, còn người nhận/tiêu đề/nội dung đến từ nghiệp vụ.
3. `SimpleMailMessage` đại diện cho một thông điệp văn bản thuần.
4. `send(message)` dùng mail transport đã được cấu hình để nộp thư cho SMTP server.

Ứng dụng thực tế phải kiểm tra nguồn gọi và dữ liệu người nhận theo nghiệp vụ. Không nên tự động mở một REST endpoint công khai cho phép người khác tùy ý đặt `To`, `Subject`, `Body` rồi gửi mail.

### 5.1. Có cần khai báo `spring-context-support` riêng?

Với **Spring Boot starter mail thông thường**, không. Starter đã giải quyết việc kéo thư viện Spring Mail cần thiết vào dependency graph. Thêm bản khai báo thứ hai chỉ để dùng `JavaMailSender` hoặc `SimpleMailMessage` thường là dư thừa.

Chỉ cân nhắc khai báo `spring-context-support` trực tiếp khi:

- module **không dùng starter mail** nhưng cần API Spring Mail;
- dự án cố ý tự quản lý phụ thuộc để tạo một thư viện tích hợp riêng;
- có yêu cầu kiến trúc rõ ràng về public API hoặc runtime scope.

Trong những trường hợp đó, bạn cũng phải bảo đảm một Jakarta Mail provider tương thích có mặt khi cần SMTP thực sự, và phải tự quyết định cách cấu hình sender.

## 6. Ví dụ sử dụng starter: HTML và file đính kèm

Starter mail cũng cung cấp khả năng dùng `MimeMessage` thông qua `JavaMailSender`. Không cần thay starter khác chỉ vì email có HTML hoặc PDF.

~~~java
package com.example.mail.application;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {
    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(String recipient, byte[] pdfBytes)
            throws MessagingException {
        MimeMessage mime = mailSender.createMimeMessage();
        MimeMessageHelper helper =
                new MimeMessageHelper(mime, true, "UTF-8");

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn của bạn");
        helper.setText(
                "Hóa đơn của bạn đã sẵn sàng.",
                "<html><body><h1>Hóa đơn đã sẵn sàng</h1>" +
                "<p>Xin cảm ơn bạn.</p></body></html>"
        );
        helper.addAttachment(
                "invoice.pdf",
                new ByteArrayResource(pdfBytes),
                "application/pdf"
        );

        mailSender.send(mime);
    }
}
~~~

Các thành phần xuất hiện trong đoạn code:

| Kiểu | Nguồn | Vai trò |
| --- | --- | --- |
| `JavaMailSender` | Spring Framework Mail | Tạo và gửi `MimeMessage` |
| `MimeMessage` | Jakarta Mail | Đối tượng thông điệp theo cấu trúc MIME |
| `MimeMessageHelper` | Spring Framework Mail | Tạo nội dung text/HTML và attachment |
| `ByteArrayResource` | Spring Core | Cung cấp bytes cho file đính kèm |
| `MessagingException` | Jakarta Mail | Báo lỗi liên quan tới việc dựng/xử lý thông điệp |

Đoạn mã giả định `pdfBytes` là nội dung PDF được chuẩn bị từ trước. Với file lớn, nên đánh giá giới hạn kích thước SMTP, bộ nhớ và khả năng dùng resource/stream phù hợp thay vì luôn giữ toàn bộ bytes trong heap.

Kết quả `send` trả về bình thường thường có nghĩa transport đã hoàn tất lần nộp thư theo giao thức hiện tại. Nó **không bảo đảm** email đã đến hộp thư đến, chưa bị bounce hoặc đã được người nhận mở.

## 7. Những dependency tùy chọn thường đi cùng mail starter

`spring-boot-starter-mail` phục vụ chức năng mail nền tảng. Một số ứng dụng bổ sung dependency cho **đầu vào HTTP, template, validation, test hoặc job processing**. Các thư viện bổ sung này không phải điều kiện bắt buộc để gửi thư text.

| Nhu cầu | Dependency thường gặp | Vì sao thêm? |
| --- | --- | --- |
| Gửi plain text qua SMTP | `spring-boot-starter-mail` | Đủ thành phần cốt lõi để tạo/sử dụng sender khi đã cấu hình đúng |
| Tạo HTML từ template | `spring-boot-starter-thymeleaf` | Render mẫu HTML với dữ liệu nghiệp vụ |
| API REST kích hoạt gửi | `spring-boot-starter-web` | Cung cấp controller HTTP trong ứng dụng Servlet/MVC |
| Kiểm tra DTO/request | `spring-boot-starter-validation` | Hỗ trợ Bean Validation như `@NotBlank`, `@Email` |
| Unit/integration test | `spring-boot-starter-test` | Cung cấp cơ sở kiểm thử Spring Boot và các thư viện test thường dùng |
| Gửi bất đồng bộ đơn giản | Khả năng async của Spring khi đã có framework phù hợp | Chạy thao tác gửi trên executor khác, nhưng không tự tạo queue bền vững |
| Job/queue bền vững | Tùy kiến trúc: database, broker, Spring Batch, v.v. | Lưu yêu cầu gửi, retry, chống xử lý trùng và giám sát |

### 7.1. HTML template và Thymeleaf

Nếu HTML có tên người nhận, mã đơn hàng hoặc bảng dữ liệu, việc ghép chuỗi trực tiếp dễ làm nội dung khó bảo trì. Có thể dùng Thymeleaf với một dependency riêng:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
}
~~~

Ví dụ tài nguyên:

~~~text
src/main/resources/
  templates/
    mail/
      welcome.html
      invoice.html
~~~

Luồng:

~~~mermaid
flowchart LR
    A["Dữ liệu nghiệp vụ"] --> B["Thymeleaf / template renderer"]
    B --> C["Chuỗi HTML"]
    C --> D["MimeMessageHelper"]
    D --> E["JavaMailSender"]
    E --> F["SMTP server"]
~~~

**Thymeleaf không gửi email.** Nó chỉ render nội dung HTML; Spring Mail/Jakarta Mail vẫn đảm nhiệm tạo và gửi thông điệp. Có thể dùng template engine khác hoặc tự tạo chuỗi text, tùy quy mô dự án. Khi đưa dữ liệu người dùng vào HTML, cần dùng cú pháp escape phù hợp; không chèn thẳng HTML không tin cậy.

### 7.2. REST API không phải yêu cầu của module mail

Nếu một nghiệp vụ cần endpoint nội bộ như “gửi lại email xác nhận”, có thể dùng `spring-boot-starter-web` cho controller. Tuy nhiên, rất nhiều module mail được kích hoạt từ:

- sự kiện người dùng đăng ký hoặc thanh toán;
- consumer nhận event từ message broker;
- scheduler gửi báo cáo theo lịch;
- worker xử lý job từ database/queue;
- service nội bộ được gọi trực tiếp trong cùng ứng dụng.

Những mô hình này **không bắt buộc có REST controller**. Đừng thêm web starter chỉ vì bài toán có gửi email; chọn dependency theo kiến trúc runtime thực tế.

### 7.3. Validation cho dữ liệu yêu cầu gửi

Nếu ứng dụng nhận một request:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

public record SendNotificationRequest(
        @NotBlank @Email String recipient,
        @NotBlank String message
) {}
~~~

Các annotation trên thường được cung cấp thông qua Bean Validation dependency và implementation khi ứng dụng dùng starter validation. `@Email` chỉ kiểm tra theo quy tắc validator, **không xác nhận mailbox tồn tại** hoặc người nhập có quyền sử dụng địa chỉ đó. Vẫn cần xác thực nguồn gọi, kiểm soát recipient và áp dụng rate limiting theo nghiệp vụ.

### 7.4. Test dependencies và SMTP giả lập

Unit test có thể mock `JavaMailSender` để kiểm tra nội dung được truyền vào `send(...)` mà **không cần SMTP server thật**. Với integration test, các công cụ như Mailpit hoặc GreenMail cho phép nhận và kiểm tra email ở môi trường local/test.

Nếu chọn thư viện SMTP test nhúng trong JVM, hãy thêm dependency của thư viện đó vào **test scope** (ví dụ `testImplementation`), không đưa vào runtime production trừ khi có lý do rõ ràng.

Ví dụ Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Khi muốn tích hợp Mailpit chạy bên ngoài JVM, ứng dụng thường chỉ cần cấu hình `spring.mail.host=localhost` và port của SMTP server test; không nhất thiết phải thêm một thư viện Mailpit vào Java dependencies.

## 8. Boot 3.x, Jakarta Mail và khác biệt với ví dụ cũ

Khi đọc bài hướng dẫn Java Mail trên Internet, bạn có thể gặp hai nhóm package:

~~~java
// Code cũ theo JavaMail trước khi chuyển sang Jakarta namespace:
import javax.mail.internet.MimeMessage;

// Code trong Spring Boot 3.x / Spring Framework 6:
import jakarta.mail.internet.MimeMessage;
~~~

Spring Framework 6 và Spring Boot 3.x sử dụng hệ sinh thái **Jakarta EE**, trong đó Jakarta Mail dùng package `jakarta.mail.*`. Các hướng dẫn cũ dựa trên Spring Boot 2.x có thể dùng `javax.mail.*`.

Phân biệt quan trọng:

| Đối tượng | Trong Boot 3.x |
| --- | --- |
| `JavaMailSender` | Vẫn là `org.springframework.mail.javamail.JavaMailSender` |
| `SimpleMailMessage` | Vẫn là `org.springframework.mail.SimpleMailMessage` |
| `MimeMessage` | `jakarta.mail.internet.MimeMessage` |
| `MessagingException` | `jakarta.mail.MessagingException` |
| Jakarta Activation | Package `jakarta.activation.*` |

Không “sửa” lỗi import bằng cách thêm ngẫu nhiên dependency `javax.mail` cũ vào ứng dụng Boot 3.x. Hai namespace `javax.mail` và `jakarta.mail` là các kiểu Java khác nhau; trộn chúng dễ dẫn đến lỗi biên dịch hoặc không tương thích runtime.

Nếu đang duy trì dự án Spring Boot 2.x, cần dùng API và dependency tương ứng của dòng đó. Khi nâng cấp sang Boot 3.x, hãy cập nhật import và cả những thư viện mở rộng mail tương thích, đồng thời kiểm tra cấu hình runtime.

### 8.1. Không pin một provider không tương thích

Trong classpath có thể xuất hiện API Jakarta Mail và implementation SMTP provider. Nếu dự án cố tình exclude hoặc ghi đè các thư viện này, biểu hiện có thể là:

- biên dịch thấy được `MimeMessage` nhưng chạy không có provider gửi SMTP;
- lỗi `ClassNotFoundException` hoặc `NoClassDefFoundError`;
- lỗi liên quan `javax.mail` và `jakarta.mail` khi module hoặc thư viện khác dùng API không tương thích;
- bean `JavaMailSender` không được auto-configure do điều kiện classpath bị phá vỡ.

Trước khi thêm dependency theo một lời gợi ý ngẫu nhiên, cần kiểm tra **resolved dependency graph** và lý do artifact xuất hiện/bị exclude.

## 9. Khi nào nên dùng Spring Mail mà không dùng starter?

Có trường hợp ứng dụng hoặc thư viện chỉ cần API Spring Mail, không muốn phụ thuộc vào Spring Boot starter:

1. **Ứng dụng Spring Framework thuần:** muốn tự khai báo `JavaMailSenderImpl` và các thư viện Jakarta Mail tương ứng.
2. **Thư viện dùng chung:** chỉ cần biên dịch với `MailSender` hoặc một abstraction riêng, còn ứng dụng tiêu thụ chịu trách nhiệm cấu hình implementation.
3. **Tích hợp nhà cung cấp qua HTTP API thay vì SMTP:** có thể không cần `JavaMailSender`, mà dùng SDK/HTTP client của nhà cung cấp và một gateway ở tầng ứng dụng.

Với Spring Framework thuần, ví dụ bean cấu hình (giả định property đã được nạp vào Spring `Environment`):

~~~java
import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfig {

    @Bean
    JavaMailSender javaMailSender(Environment env) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(env.getRequiredProperty("mail.host"));
        sender.setPort(env.getRequiredProperty("mail.port", Integer.class));
        sender.setUsername(env.getRequiredProperty("mail.username"));
        sender.setPassword(env.getRequiredProperty("mail.password"));
        sender.setDefaultEncoding("UTF-8");

        Properties properties = sender.getJavaMailProperties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        return sender;
    }
}
~~~

Ở kiến trúc này, ứng dụng tự quản lý dependency Spring Mail, Jakarta Mail/provider, cấu hình và vòng đời sender. Nếu đã dùng Spring Boot mail starter thông thường, **không cần tạo lại bean giống ví dụ** trừ khi có yêu cầu tùy chỉnh cụ thể.

Một module gửi email chỉ qua **HTTP API** của một nhà cung cấp có thể chọn hoàn toàn khác: client/SDK gửi yêu cầu HTTPS và xử lý provider response. `spring-boot-starter-mail` chủ yếu phù hợp khi dùng API Spring Mail và/hoặc SMTP; không phải dependency bắt buộc cho mọi loại dịch vụ gửi email.

## 10. Cách xem dependency thực sự đã được đưa vào dự án

Trong một build Gradle đa module, những dependency được khai báo chưa chắc giống hệt các artifact được resolve cho runtime. Để hiểu starter kéo theo gì, có thể dùng các lệnh **tham khảo** dưới đây tại module thích hợp:

~~~bash
# Xem toàn bộ runtime dependencies của module.
./gradlew dependencies --configuration runtimeClasspath

# Tìm vì sao spring-context-support hiện diện.
./gradlew dependencyInsight --dependency spring-context-support --configuration runtimeClasspath

# Kiểm tra implementation/provider mail được resolve.
./gradlew dependencyInsight --dependency jakarta.mail --configuration runtimeClasspath
~~~

Nếu chạy từ root của multi-project, cần chỉ rõ project path trong command, ví dụ `:my-mail-app:dependencies`, theo tên thực tế của module. Với Maven:

~~~bash
mvn dependency:tree
~~~

Các lệnh này giúp bạn kiểm tra:

- starter nào đã kéo Spring Mail vào;
- phiên bản `spring-context-support` và Jakarta Mail/provider cuối cùng;
- có dependency bị exclude hoặc override không;
- một thư viện khác có mang theo legacy `javax.mail` hay không;
- scope/runtime classpath có chứa các lớp cần thiết không.

Không nên suy đoán dependency graph chỉ từ tên starter khi dự án có nhiều plugin, BOM hoặc luật resolution.

## 11. Các lỗi phổ biến khi thêm starter mail

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| `NoSuchBeanDefinitionException: JavaMailSender` | Thiếu starter, thiếu cấu hình host/JNDI phù hợp, điều kiện auto-configuration không thỏa hoặc bean bị thay thế | Classpath, `spring.mail.host`, bean custom và auto-configuration report |
| `ClassNotFoundException` liên quan `jakarta.mail` | Provider/API bị exclude, scope sai hoặc phiên bản không tương thích | Resolved dependency graph và runtime classpath |
| `package javax.mail does not exist` | Code cũ chưa migrate sang Jakarta khi dùng Spring Boot 3.x | Import và dependency theo phiên bản Boot |
| `MailAuthenticationException` | Sai credentials hoặc provider từ chối cách xác thực | Biến môi trường, tài khoản, cơ chế SMTP AUTH |
| Connection refused / timeout | SMTP host/port sai, server không chạy, firewall/network policy, timeout | Kết nối môi trường và `spring.mail.*` |
| Server từ chối STARTTLS | Server không hỗ trợ hoặc cấu hình bảo mật không khớp | `mail.smtp.starttls.*`, chế độ TLS của provider |
| Lỗi certificate TLS | Sai hostname, chứng chỉ hết hạn hoặc truststore chưa phù hợp | Chứng chỉ, trust chain, DNS và bảo mật kết nối |
| Message text tiếng Việt bị lỗi | Charset/encoding bị cấu hình sai | `spring.mail.default-encoding`, header MIME và client nhận |
| `send(...)` trả về không lỗi nhưng người nhận chưa thấy thư | Mail đã được server chấp nhận nhưng còn chờ/đã bounce/vào spam | Provider dashboard, DSN, webhook, không chỉ Java exception |
| Tưởng starter sẽ tự gửi email theo sự kiện | Thiếu service/event handler/job kích hoạt gửi | Luồng nghiệp vụ và nơi gọi `JavaMailSender.send` |

### 11.1. Phân biệt lỗi lúc khởi động với lỗi lúc gửi

Nếu không có bean `JavaMailSender`, ứng dụng có thể lỗi khi tạo service phụ thuộc vào bean đó. Nếu bean đã được tạo nhưng SMTP host sai hoặc credentials hết hạn, lỗi có thể **chỉ xuất hiện khi gọi `send(...)`**.

Đối với thư giao dịch quan trọng, nên ghi nhận lỗi một cách có cấu trúc và thiết kế retry có giới hạn khi phù hợp. Không retry vô hạn mọi ngoại lệ: từ chối người nhận vĩnh viễn, authentication sai và lỗi mạng tạm thời cần cách xử lý khác nhau. Mất kết nối sau khi client đã gửi nội dung cũng có thể tạo tình huống không rõ server đã nhận thư hay chưa, nên retry có nguy cơ phát sinh thư trùng.

### 11.2. Cấu hình host không phải bằng chứng sẵn sàng gửi

Sự tồn tại của ba thứ khác nhau:

~~~text
Dependency có mặt -> Bean sender tồn tại -> SMTP gửi thành công
~~~

Không nên gộp thành một bước duy nhất. Dependency chỉ là **khả năng về mặt classpath**; bean là **cấu hình trong Spring container**; SMTP thực tế phụ thuộc **network, TLS, credentials, provider policy và trạng thái server**.

## 12. Ví dụ lựa chọn dependency theo tình huống

| Tình huống | Dependency khởi đầu phù hợp | Ghi chú |
| --- | --- | --- |
| Microservice Spring Boot gửi OTP hoặc thông báo text qua SMTP | `spring-boot-starter-mail` | Dùng `SimpleMailMessage`, kiểm soát dữ liệu nhạy cảm trong nội dung |
| Service gửi HTML hóa đơn có PDF | `spring-boot-starter-mail` | Dùng `MimeMessageHelper`; không cần starter attachment riêng |
| Service dùng mẫu HTML có biến động | Mail starter + Thymeleaf starter nếu chọn Thymeleaf | Renderer và sender là hai trách nhiệm riêng |
| Ứng dụng có REST endpoint để gửi lại thông báo | Mail starter + web/validation theo kiến trúc | Bảo vệ endpoint, tránh trở thành open mail relay |
| Worker gửi email từ queue | Mail starter + dependency queue theo broker | Queue không được cung cấp tự động bởi mail starter |
| Unit test mail service | Mail starter ở runtime/compile + test starter ở test scope | Mock sender để kiểm tra thông điệp |
| Integration test SMTP nội bộ | Mail starter + công cụ SMTP test bên ngoài hoặc test library | Không dùng credentials production |
| Library Spring Framework không chạy Spring Boot | Spring Mail API và Jakarta Mail/provider khi cần | Tự cấu hình sender, không dựa vào Boot auto-configuration |
| Gửi email qua REST API của provider | SDK hoặc HTTP client tương ứng | Có thể không dùng mail starter nếu không cần Spring SMTP API |

## 13. Thực hành nhỏ: từ dependency tới một email đầu tiên

Giả sử ứng dụng cần gửi thông báo văn bản từ tài khoản kỹ thuật:

1. **Khai báo** `spring-boot-starter-mail` trong module Spring Boot.
2. **Chọn SMTP server**: local test server hoặc provider có quyền gửi thực tế.
3. **Cấp cấu hình** `spring.mail.host`, port, AUTH/TLS, timeout và secret từ môi trường.
4. **Inject** `JavaMailSender` vào service; tránh tự tạo sender trong mỗi lần gửi.
5. **Tạo** `SimpleMailMessage`, đặt From, To, Subject và Text.
6. **Gọi** `send(message)`; theo dõi lỗi và kết quả nộp thư.
7. **Kiểm tra** email nhận được trong SMTP test server, bao gồm header, ký tự tiếng Việt và nội dung.
8. **Nâng cấp** sang `MimeMessageHelper` nếu cần HTML, attachment hoặc nhiều phần MIME.

Không cần tạo cả controller, scheduler, template engine hay queue cho bài thực hành gửi một thông báo text. Những dependency đó chỉ có ý nghĩa khi yêu cầu nghiệp vụ hoặc kiến trúc thực sự cần chúng.

Ví dụ lõi ngắn nhất:

~~~java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("no-reply@example.com");
mail.setTo("reader@example.net");
mail.setSubject("Xin chào");
mail.setText("Đây là thư thử nghiệm bằng Spring Boot Mail.");
javaMailSender.send(mail);
~~~

Đoạn code giả định `javaMailSender` đã được inject và SMTP sender được cấu hình đúng; nó không thể chạy độc lập ngoài ngữ cảnh ứng dụng đã có bean sender.

## 14. Những hiểu lầm cần tránh

| Hiểu lầm | Cách hiểu đúng |
| --- | --- |
| “Chỉ cần thêm `spring-boot-starter-mail` là email sẽ tự được gửi.” | Starter cung cấp dependency; ứng dụng vẫn phải cấu hình SMTP và gọi sender. |
| “Muốn HTML hoặc PDF phải tìm một starter mail khác.” | `JavaMailSender` và `MimeMessageHelper` trong hệ Spring Mail đã hỗ trợ MIME. |
| “Phải thêm `spring-context-support` và Jakarta Mail từng thư viện một.” | Trong trường hợp starter mail thông dụng, chúng thường là dependency bắc cầu; chỉ bổ sung khi thật sự cần. |
| “Starter là SMTP server.” | Starter là thư viện ứng dụng; server/provider SMTP là thành phần vận hành bên ngoài. |
| “Spring Mail cũng nhận và đọc inbox.” | API gửi mail không tự trở thành một hệ thống nhận email; inbound là bài toán riêng. |
| “Thêm web starter là điều kiện bắt buộc để gửi thư.” | Email có thể được kích hoạt bằng service, event, scheduler hoặc worker. |
| “`javax.mail` và `jakarta.mail` có thể tráo đổi tùy ý.” | Chúng thuộc các thế hệ API khác nhau; phải tương thích với Spring Boot/Spring Framework đang dùng. |
| “Email được nộp cho SMTP nghĩa là người dùng đã đọc.” | Delivery và read status cần theo dõi riêng nếu nghiệp vụ yêu cầu. |
| “Starter tự có queue và retry.” | Queue, outbox, backoff, idempotency và theo dõi trạng thái phải được thiết kế riêng. |

## 15. Kiến thức cần nắm sau bài học

Khi gặp `spring-boot-starter-mail` trong `build.gradle` hoặc `pom.xml`, bạn có thể hiểu:

- Dự án đang lựa chọn **Spring Mail integration** để xây chức năng gửi thư.
- API như `JavaMailSender`, `SimpleMailMessage` và `MimeMessageHelper` đến từ **Spring Framework Mail**.
- Các kiểu `MimeMessage` và `MessagingException` đến từ **Jakarta Mail** trong hệ Boot 3.x; implementation/provider giúp giao tiếp với SMTP.
- **Spring Boot auto-configuration** dùng classpath, những bean sẵn có và `spring.mail.*` để quyết định tạo sender.
- **Template engine, web API, validation, queue, test SMTP** là các thành phần bổ sung theo yêu cầu, không phải chức năng tự động của starter.

Hiểu đúng các ranh giới này giúp bạn chọn dependency vừa đủ, tránh version conflict, biết phải kiểm tra ở đâu khi `JavaMailSender` không tồn tại và phân biệt rõ một lỗi **classpath**, **cấu hình bean**, **kết nối SMTP** hay **giao thư**.

### Tài liệu tra cứu

- **Spring Boot Reference — Sending Email:** starter, `spring.mail.*` và mail auto-configuration.
- **Spring Boot Reference — Dependency Management:** BOM, phiên bản dependency do Spring Boot quản lý.
- **Spring Framework Reference — Email:** `MailSender`, `JavaMailSender` và `MimeMessageHelper`.
- **Spring Framework API — `org.springframework.mail.*`:** các interface, message và exception liên quan.
- **Jakarta Mail Specification / API:** `MimeMessage`, `Session`, SMTP provider và MIME.
- **Gradle User Manual / Maven Dependency Plugin:** xem resolved dependency graph và nguyên nhân dependency bắc cầu xuất hiện.
