# JavaMailSender làm bean dùng chung trong Spring Framework Mail

Trong một ứng dụng Spring, nhiều chức năng có thể cần gửi email: đăng ký tài khoản, xác thực địa chỉ, thông báo đơn hàng, nhắc lịch hoặc gửi báo cáo. Nếu mỗi chức năng tự tạo `JavaMailSenderImpl` và tự cấu hình SMTP, dự án sẽ sớm có nhiều nơi chứa host, port, thông tin xác thực và quy tắc timeout khác nhau. Khi đổi nhà cung cấp email hoặc thay chính sách bảo mật, việc duy trì các cấu hình rải rác trở nên khó khăn.

Cách tổ chức tự nhiên trong Spring là **đăng ký một `JavaMailSender` làm bean dùng chung**, sau đó dùng dependency injection để các service cần gửi email sử dụng cùng thành phần đó. Một bean sender dùng chung giúp tập trung cấu hình giao thức, giảm mã khởi tạo lặp lại và thuận tiện thay thế bằng mock khi kiểm thử.

Điểm cần phân biệt ngay từ đầu: **dùng chung bean `JavaMailSender` không có nghĩa dùng chung một email, một `MimeMessage` hoặc một kết nối SMTP mở vĩnh viễn**. Bean là thành phần gửi và cấu hình; mỗi lần gửi vẫn cần tạo thông điệp riêng, còn transport và kết nối SMTP được thư viện quản lý theo từng thao tác.

## 1. `JavaMailSender` là gì?

Spring Framework Mail có một số kiểu quan trọng:

| Kiểu | Vai trò | Trường hợp sử dụng |
| --- | --- | --- |
| `MailSender` | Giao diện gửi `SimpleMailMessage` | Email plain text đơn giản |
| `JavaMailSender` | Mở rộng khả năng gửi với `MimeMessage` và `MimeMessagePreparator` | Email HTML, MIME, attachment, nội dung phong phú |
| `JavaMailSenderImpl` | Triển khai SMTP phổ biến do Spring cung cấp | Bean kết nối đến SMTP relay hoặc Email Service Provider (ESP) |
| `SimpleMailMessage` | Dữ liệu một thư plain text | Thông báo ngắn, email văn bản |
| `MimeMessage` | Thông điệp email theo Jakarta Mail/MIME | HTML, multipart, file và inline content |
| `MimeMessageHelper` | Tiện ích của Spring giúp cấu hình `MimeMessage` | Đặt From/To/Subject, HTML, attachment, ảnh nội tuyến |
| `MimeMessagePreparator` | Callback chuẩn bị một `MimeMessage` trước khi gửi | Gom phần tạo nội dung email vào một callback |

`JavaMailSender` là **giao diện**. Code nghiệp vụ nên khai báo phụ thuộc vào giao diện này; Spring cung cấp một implementation ở runtime. Việc này giảm phụ thuộc trực tiếp vào `JavaMailSenderImpl` và cho phép thay thế bằng bean khác trong môi trường kiểm thử hoặc khi chuyển cách gửi.

Một kiến trúc đơn giản:

```text
                Spring ApplicationContext
                         |
                         v
              JavaMailSender bean
              (JavaMailSenderImpl)
                 |      |      |
                 |      |      |
        +--------+      |      +---------+
        |               |                |
        v               v                v
  RegistrationMail  OrderMail        ReportMail
      Service        Service          Service
        |               |                |
        +---------------+----------------+
                        |
                 send(message)
                        |
                        v
                  SMTP relay / ESP
```

Các service có thể tạo ra các email khác nhau nhưng dùng chung cấu hình SMTP và cơ chế gửi do bean trung tâm cung cấp.

## 2. Bean dùng chung nghĩa là gì trong Spring?

Trong Spring, một bean được khai báo bằng `@Bean` hoặc được tạo bởi auto-configuration thường có **scope singleton theo mặc định**. Trong một `ApplicationContext`, Spring thường tạo một instance của bean và cung cấp tham chiếu đến instance đó cho các thành phần có dependency phù hợp.

Ví dụ:

```java
@Service
public class RegistrationMailService {
    private final JavaMailSender mailSender;

    public RegistrationMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
}
```

Và:

```java
@Service
public class BillingMailService {
    private final JavaMailSender mailSender;

    public BillingMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
}
```

Nếu chỉ có một bean `JavaMailSender` trong context, hai service được Spring tiêm vào **cùng instance** đó.

### Singleton của Spring không phải singleton toàn hệ thống

- Một bean singleton tồn tại theo phạm vi **ApplicationContext**, không tự động chia sẻ giữa các tiến trình Java.
- Hai container/pod chạy cùng ứng dụng có các sender instance riêng, dù cùng dùng một SMTP host và bộ thông tin xác thực.
- Hai ApplicationContext khác nhau có thể có bean riêng.
- Dùng chung instance Java không tạo ra giới hạn tốc độ toàn hệ thống và không ngăn hai instance gửi cùng một email.
- Trong unit test, nếu khởi tạo service thủ công bằng `new`, cần truyền dependency vào constructor; Spring container không tự tiêm cho object do ta tự tạo.

### Bean sender khác với thông điệp và kết nối SMTP

`JavaMailSenderImpl` giữ các thông tin như host, port, username, password, JavaMail properties và đối tượng `Session` của Jakarta Mail. Nó là một thành phần gửi, không phải “lá thư đang được xây”.

Thông thường, implementation SMTP sẽ mở và sử dụng transport theo lần gửi hoặc theo một batch trong một lần gọi `send`, rồi đóng transport sau đó. **Chỉ khai báo bean singleton không đồng nghĩa có SMTP connection pool hoặc một kết nối TCP luôn mở**.

Không nên tự giả định rằng chi phí handshake/xác thực biến mất vì sender là singleton. Nếu cần throughput cao, phải xem khả năng batch, giới hạn kết nối, pooling ở thư viện/ESP và chính sách gửi thực tế.

## 3. Cách ưu tiên: Spring Boot tự tạo `JavaMailSender`

Với Spring Boot, cách đơn giản nhất là thêm mail starter và khai báo cấu hình. Khi các điều kiện auto-configuration phù hợp và chưa có sender bean tùy chỉnh cần ưu tiên, Boot có thể tạo `JavaMailSenderImpl` cho ứng dụng.

### Thêm dependency

Với Maven và dự án sử dụng Spring Boot dependency management:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Với Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-mail'
```

Các ví dụ bên dưới dùng Spring Framework 6+/Spring Boot 3+ và package `jakarta.mail.*`. Ở các thế hệ Spring cũ hơn có thể gặp `javax.mail.*`; không nên trộn hai hệ package trong cùng ứng dụng.

### Cấu hình SMTP trong `application.properties`

```properties
spring.mail.host=smtp.example.com
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8

spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true

spring.mail.properties.mail.smtp.connectiontimeout=5000
spring.mail.properties.mail.smtp.timeout=10000
spring.mail.properties.mail.smtp.writetimeout=10000
```

Host, port và chế độ TLS phải đúng với nhà cung cấp SMTP thực tế. Port 587/STARTTLS là ví dụ phổ biến, không phải lựa chọn duy nhất. Biến môi trường `SMTP_USERNAME` và `SMTP_PASSWORD` nên được cấp từ môi trường triển khai hoặc hệ thống quản lý secrets, thay vì ghi giá trị nhạy cảm vào source code.

Ba timeout có đơn vị mili giây:

| Thuộc tính | Giá trị ví dụ | Ý nghĩa |
| --- | ---: | --- |
| `mail.smtp.connectiontimeout` | 5000 | Giới hạn thời gian mở kết nối socket |
| `mail.smtp.timeout` | 10000 | Giới hạn thao tác đọc dữ liệu từ socket |
| `mail.smtp.writetimeout` | 10000 | Giới hạn thao tác ghi dữ liệu lên socket |

Nếu bỏ các giá trị timeout, một số thao tác socket có thể chờ rất lâu. Các thuộc tính này không tạo deadline tổng cho toàn bộ `send()`; một lần gửi có thể gồm nhiều thao tác đọc/ghi tuần tự.

Đặt cấu hình cũng có thể dùng `application.yml`:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
      "[mail.smtp.connectiontimeout]": 5000
      "[mail.smtp.timeout]": 10000
      "[mail.smtp.writetimeout]": 10000
```

Các khóa có dấu chấm dưới `spring.mail.properties` là thuộc tính Jakarta Mail; cách ghi bracket trong YAML giúp giữ chúng như những key map nguyên vẹn.

### Sử dụng bean đã được Boot tạo

Khi Boot đã có sender bean, service chỉ cần tiêm dependency:

```java
package example.mail;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {
    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    // Các phương thức gửi email dùng mailSender ở đây.
}
```

Không cần viết `new JavaMailSenderImpl()` trong mỗi service. Cũng không cần thêm `@Scope("singleton")`: singleton đã là scope mặc định của bean Spring.

## 4. Hai service dùng chung sender nhưng tạo email độc lập

Hãy xây hai nghiệp vụ: gửi thư xác nhận đăng ký bằng plain text và gửi hóa đơn bằng HTML.

### Dịch vụ gửi plain text

```java
package example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class AccountMailService {
    private final JavaMailSender mailSender;

    public AccountMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient, String displayName) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("no-reply@example.com");
        mail.setTo(recipient);
        mail.setSubject("Chào mừng bạn");
        mail.setText("Xin chào " + displayName + "!\n"
                + "Tài khoản của bạn đã được tạo thành công.");

        mailSender.send(mail);
    }
}
```

Ở đây, mỗi lần gọi `sendWelcome` tạo một `SimpleMailMessage` **mới**. Sender là bean dùng chung, nhưng đối tượng chứa người nhận và nội dung thuộc riêng lần gửi.

### Dịch vụ gửi HTML

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {
    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoiceNotice(String recipient, String invoiceId)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());
        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn của bạn");

        String plain = "Hóa đơn " + invoiceId
                + " đã sẵn sàng.\nXem tại https://example.com/invoices";

        String html = """
                <!doctype html>
                <html lang="vi">
                  <body>
                    <h1>Hóa đơn đã sẵn sàng</h1>
                    <p>Đăng nhập để xem hóa đơn trong tài khoản của bạn.</p>
                    <a href="https://example.com/invoices">Xem hóa đơn</a>
                  </body>
                </html>
                """;

        helper.setText(plain, html);
        mailSender.send(message);
    }
}
```

Constructor `MimeMessageHelper(message, true, "UTF-8")` bật chế độ multipart để có thể cung cấp cả bản plain text lẫn HTML. Nếu HTML dùng dữ liệu động như tên, số tiền hoặc mã hóa đơn, nên dùng template engine với escaping đúng ngữ cảnh, không chèn dữ liệu không tin cậy thành HTML thô.

### Ranh giới chia sẻ

Hai service phía trên chia sẻ:

- Cùng `JavaMailSender` và thông số kết nối của nó.
- Cùng quy tắc TLS, xác thực và timeout SMTP.
- Cùng quá trình đưa thư tới SMTP relay đã cấu hình.

Chúng **không chia sẻ**:

- `SimpleMailMessage` hay `MimeMessage`.
- Người nhận, tiêu đề, body, attachment của từng email.
- Trạng thái retry hoặc thông tin nghiệp vụ của từng lần gửi.

Nếu muốn mỗi loại thông báo có địa chỉ `From` khác nhau, có thể đặt chúng trong message riêng **miễn nhà cung cấp SMTP cho phép các địa chỉ đó**. Việc dùng cùng một bean sender không tự trao quyền gửi thay mặt mọi domain.

## 5. Khai báo `@Bean` thủ công khi không dùng auto-configuration

Với Spring Framework thuần hoặc khi cần một cấu hình SMTP đặc biệt, có thể tạo bean trong lớp `@Configuration`:

```java
package example.mail;

import java.util.Properties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MailConfiguration {

    @Bean
    public JavaMailSender javaMailSender() {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost("smtp.example.com");
        sender.setPort(587);
        sender.setUsername(System.getenv("SMTP_USERNAME"));
        sender.setPassword(System.getenv("SMTP_PASSWORD"));
        sender.setDefaultEncoding("UTF-8");

        Properties properties = new Properties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "10000");
        properties.put("mail.smtp.writetimeout", "10000");

        sender.setJavaMailProperties(properties);
        return sender;
    }
}
```

Spring gọi factory method `javaMailSender()` để tạo bean, sau đó quản lý instance trong `ApplicationContext`. Các service chỉ cần constructor injection giống phần trước.

Không nên vừa để Boot tự cấu hình, vừa thêm bean thủ công mà không có chủ đích: khi đã có bean phù hợp, mail auto-configuration của Boot thường nhường chỗ cho cấu hình do ứng dụng cung cấp. Kết quả là các giá trị từ `spring.mail.*` có thể không được áp dụng nếu bean thủ công không đọc chúng.

### Tại sao không gọi trực tiếp phương thức `@Bean` trong service?

Không nên biến một service thành nơi khởi tạo sender:

```java
// Không nên:
public void sendSomething() {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("smtp.example.com");
    // ...
    sender.send(message);
}
```

Cách này tạo cấu hình lặp, khiến test khó thay thế dependency và dễ gây sai lệch giữa các chức năng. Dùng constructor injection để Spring quyết định instance và vòng đời.

## 6. Vòng đời và tính ổn định của bean dùng chung

Khi ứng dụng khởi động, Spring tạo bean theo nhu cầu cấu hình và các dependency. `JavaMailSenderImpl` nắm các thiết lập phục vụ gửi: SMTP host, port, username/password, các thuộc tính Jakarta Mail và một `Session` được tạo hoặc cung cấp theo cấu hình.

Đây là bean dùng lâu dài, nhưng **không phải trạng thái của một lần gửi**.

### Cần cố định cấu hình sau khi ứng dụng khởi động

Một thực hành quan trọng là xem các thuộc tính của `JavaMailSenderImpl` như **cấu hình bất biến sau khi bean đã được khởi tạo**.

Ví dụ không nên làm khi nhiều thread đang gửi:

```java
// Tránh đổi cấu hình sender dùng chung theo từng request:
JavaMailSenderImpl sender = (JavaMailSenderImpl) mailSender;
sender.setHost(request.getSmtpHost());
sender.setUsername(request.getUsername());
sender.setPassword(request.getPassword());
sender.send(message);
```

Nếu request A đổi host rồi request B đổi username trước khi A gọi `send`, một email có thể đi qua tài khoản hoặc máy chủ ngoài ý muốn. Vấn đề này vừa là race condition vừa là rủi ro lộ dữ liệu giữa các tenant.

Giải pháp là:

- Chốt cấu hình mỗi sender bean khi xây dựng `ApplicationContext`.
- Tạo đối tượng email mới cho từng lần gửi.
- Nếu ứng dụng cần nhiều cấu hình SMTP đồng thời, tạo **nhiều sender bean được phân biệt rõ** hoặc một cơ chế factory/pool theo tenant có quản lý vòng đời.
- Nếu cần xoay vòng credential, dùng quy trình tái tạo/reconfigure sender có kiểm soát, tránh tự đổi các setter trên instance đang có request gửi song song.

### `Session` có phải là “email đang gửi” không?

Không. `jakarta.mail.Session` chứa cấu hình và cơ chế phục vụ Jakarta Mail; mỗi `MimeMessage` là đối tượng riêng. Trong `JavaMailSenderImpl`, session có thể được tạo hoặc cung cấp và tái sử dụng. Tuy nhiên, một `Session` dùng chung **không có nghĩa các message hoặc network connection dùng chung**.

Một message nên có vòng đời:

```text
Service method được gọi
      |
      v
createMimeMessage()
      |
      v
MimeMessageHelper thiết lập nội dung/header
      |
      v
mailSender.send(message)
      |
      v
Thông điệp không còn bị service sửa
```

Không lưu một `MimeMessage` trong field của singleton service để sửa và tái sử dụng cho nhiều người nhận.

## 7. Có thể gọi một singleton sender từ nhiều thread không?

Trong kiến trúc Spring phổ biến, `JavaMailSenderImpl` được dùng như **bean singleton với cấu hình cố định**, và nhiều service/request có thể gọi `send`. Điều quan trọng là phân biệt tính ổn định của sender với tính an toàn của những đối tượng khác:

| Thành phần | Cách sử dụng được khuyến nghị |
| --- | --- |
| `JavaMailSender` được cấu hình một lần | Tiêm dùng chung giữa nhiều service |
| `JavaMailSenderImpl` và `Properties` | Không thay đổi host, credentials, session hoặc properties trong khi đang gửi |
| `SimpleMailMessage` | Tạo mới cho mỗi email hoặc dùng bản copy riêng |
| `MimeMessage` | Tạo mới cho mỗi lần gửi; không chỉnh sửa đồng thời |
| `MimeMessageHelper` | Tạo mới theo từng `MimeMessage` |
| Mutable template data/model | Dùng object riêng theo request, không sửa dữ liệu dùng chung |
| Retry state/recipient list | Lưu theo delivery/attempt, không đặt trong field mutable của singleton |

### Singleton không giới hạn số phiên SMTP đồng thời

Nếu 100 request cùng gọi `mailSender.send(...)`, việc có **một sender bean** không đồng nghĩa ứng dụng chỉ mở **một kết nối** hoặc tự có queue 100 phần tử. Thư viện và lời gọi gửi có thể tạo nhiều kết nối/transport đồng thời.

Hậu quả cần tính đến:

- SMTP provider có giới hạn kết nối, số thư/phút hoặc số recipient.
- Mỗi connect và TLS handshake có chi phí CPU, mạng và độ trễ.
- Đọc/ghi socket bị chặn có thể chiếm thread trong thời gian dài.
- Bật `mail.smtp.writetimeout` ở một số triển khai Jakarta Mail có thêm chi phí tài nguyên lập lịch theo kết nối.
- Khi có lỗi mạng đồng loạt, retry không kiểm soát có thể gây quá tải.

Để kiểm soát, đặt hàng đợi/worker pool với độ đồng thời giới hạn và chính sách retry/backoff. Giới hạn này **thuộc kiến trúc gửi mail**, không xuất hiện tự động chỉ nhờ bean singleton.

## 8. Tiêm dependency qua constructor: lý do và quy tắc

Constructor injection là cách dễ kiểm soát nhất khi các service có dependency bắt buộc:

```java
@Service
public class PasswordResetMailService {
    private final JavaMailSender mailSender;
    private final MailTemplateRenderer renderer;

    public PasswordResetMailService(
            JavaMailSender mailSender,
            MailTemplateRenderer renderer) {
        this.mailSender = mailSender;
        this.renderer = renderer;
    }
}
```

Lợi ích:

1. Dependency được khai báo rõ; không thể tạo service hoàn chỉnh mà thiếu sender/renderer.
2. Dễ thay `JavaMailSender` bằng mock hoặc fake trong unit test.
3. Có thể khai báo field `final`, hạn chế thay đổi dependency ở runtime.
4. Service tập trung xây dựng nội dung và quy tắc nghiệp vụ, không tự nắm cấu hình SMTP.
5. Khi chỉ có một constructor, Spring có thể dùng constructor đó để inject mà không cần `@Autowired` trong các phiên bản Spring hiện đại.

Với nhiều service, nếu tất cả cùng chứa logic chung như định dạng sender name, đo thời gian gửi hoặc mapping lỗi, có thể tạo một lớp hạ tầng/adapter email chung. Tuy nhiên, lớp này vẫn nên **nhận `JavaMailSender` qua constructor**, thay vì tự tạo sender mới.

### Có nên inject `JavaMailSenderImpl` trực tiếp?

Ví dụ:

```java
private final JavaMailSenderImpl sender;
```

Cách này làm service phụ thuộc vào implementation và tạo cám dỗ sửa host/password từ code nghiệp vụ. Nếu service chỉ cần gửi mail, hãy dùng `JavaMailSender`. Chỉ phần cấu hình/hạ tầng thật sự cần API cụ thể của `JavaMailSenderImpl` mới nên làm việc với implementation.

## 9. `MimeMessagePreparator` và dùng chung sender theo từng lần gửi

Khi dùng HTML, template hoặc MIME phức tạp, `MimeMessagePreparator` cho phép chuẩn bị message bằng callback. Đây là một cách tốt để giữ message mới theo từng lần gọi:

```java
package example.mail;

import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class NewsMailService {
    private final JavaMailSender mailSender;

    public NewsMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendNews(String recipient) {
        mailSender.send(mimeMessage -> {
            MimeMessageHelper helper = new MimeMessageHelper(
                    mimeMessage, "UTF-8");
            helper.setFrom("news@example.com");
            helper.setTo(recipient);
            helper.setSubject("Thông báo mới");
            helper.setText(
                    "<h2>Tin mới</h2><p>Xem cập nhật trong tài khoản của bạn.</p>",
                    true
            );
        });
    }
}
```

Overload `send(MimeMessagePreparator)` yêu cầu thư viện cung cấp một `MimeMessage` cho callback. Spring xử lý việc tạo và gửi message; nếu chuẩn bị thất bại, ngoại lệ được ánh xạ theo cơ chế của Spring Mail. Không nên giữ tham chiếu đến `mimeMessage` sau khi callback kết thúc rồi tiếp tục sửa trong thread khác.

Nếu cần hai phiên bản plain text và HTML, tạo helper ở chế độ multipart rồi gọi `helper.setText(plain, html)`. Nếu có attachment, cũng cần multipart thích hợp. Sender bean vẫn không đổi dù các message có cấu trúc khác nhau.

## 10. Nhiều tài khoản SMTP: khi nào cần nhiều bean?

“Một bean dùng chung” là lựa chọn mặc định tốt **khi toàn ứng dụng dùng cùng cấu hình SMTP**. Một số hệ thống có nhu cầu thực sự khác:

- Email giao dịch qua nhà cung cấp A, newsletter qua B.
- Ứng dụng gửi từ hai tenant với credential/domain tách biệt.
- Một relay nội bộ cho cảnh báo kỹ thuật, ESP công cộng cho người dùng.
- Chính sách giới hạn/tải và uy tín gửi cần cách ly giữa các nhóm email.

Lúc đó, tạo nhiều bean `JavaMailSender` với tên/`@Qualifier` rõ ràng. Ví dụ:

```java
package example.mail;

import java.util.Properties;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.JavaMailSenderImpl;

@Configuration
public class MultiSmtpConfiguration {

    @Bean("transactionalMailSender")
    public JavaMailSender transactionalMailSender() {
        return createSender(
                "smtp-transactional.example.com",
                587,
                System.getenv("SMTP_TRANSACTIONAL_USER"),
                System.getenv("SMTP_TRANSACTIONAL_PASSWORD"));
    }

    @Bean("campaignMailSender")
    public JavaMailSender campaignMailSender() {
        return createSender(
                "smtp-campaign.example.com",
                587,
                System.getenv("SMTP_CAMPAIGN_USER"),
                System.getenv("SMTP_CAMPAIGN_PASSWORD"));
    }

    private static JavaMailSender createSender(
            String host, int port, String user, String password) {
        JavaMailSenderImpl sender = new JavaMailSenderImpl();
        sender.setHost(host);
        sender.setPort(port);
        sender.setUsername(user);
        sender.setPassword(password);
        sender.setDefaultEncoding("UTF-8");

        Properties properties = new Properties();
        properties.put("mail.smtp.auth", "true");
        properties.put("mail.smtp.starttls.enable", "true");
        properties.put("mail.smtp.starttls.required", "true");
        properties.put("mail.smtp.connectiontimeout", "5000");
        properties.put("mail.smtp.timeout", "10000");
        properties.put("mail.smtp.writetimeout", "10000");
        sender.setJavaMailProperties(properties);

        return sender;
    }
}
```

Inject đúng bean theo nghiệp vụ:

```java
package example.mail;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class CampaignMailService {
    private final JavaMailSender mailSender;

    public CampaignMailService(
            @Qualifier("campaignMailSender") JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
}
```

Nếu Spring thấy **nhiều bean cùng kiểu `JavaMailSender`** mà nơi inject không chỉ rõ bean phù hợp, ứng dụng có thể gặp `NoUniqueBeanDefinitionException` hoặc lỗi autowire tương ứng. Cách khắc phục là dùng `@Qualifier`, đánh dấu một bean `@Primary` nếu có default rõ ràng, hoặc thiết kế factory/registry có chủ đích.

Cấu hình hai bean trực tiếp như trên chỉ minh họa cơ chế. Với ứng dụng lớn, nên đưa các giá trị host, port, username, password và timeout vào cấu hình riêng có validate, thay vì hard-code trong nhiều phương thức.

### Khi nào không nên tạo một bean riêng cho từng request?

Nếu mỗi HTTP request chứa một SMTP host hoặc credential mới, việc tạo vô số bean singleton theo request không phù hợp mô hình Spring. Có thể xây một dịch vụ quản lý client/transport theo tenant, nhưng cần xem xét:

- Quyền sử dụng sender credential của từng tenant.
- Chính sách lưu và làm mới secrets.
- Hạn mức kết nối và số tenant đang hoạt động.
- Vòng đời resource, bộ nhớ và cleanup.
- Không bao giờ sửa cấu hình của một sender dùng chung giữa hai tenant.
- Tránh để request tùy ý chọn SMTP host, vì có thể phát sinh SSRF hoặc truy cập mạng không mong muốn.

Mô hình multi-tenant phức tạp cần thiết kế riêng; đừng giải quyết bằng setter `setHost`/`setPassword` trên singleton đang được dùng đồng thời.

## 11. Dùng chung sender không đồng nghĩa dùng chung địa chỉ From

Một bean `JavaMailSender` không gắn vĩnh viễn một người gửi hiển thị duy nhất. Có hai nhóm cấu hình cần phân biệt:

- **SMTP account/transport**: host, port, username, password, TLS, timeout.
- **Nội dung email**: `From`, `To`, `Reply-To`, `Subject`, body, attachment.

Ví dụ hai service dùng cùng sender có thể đặt `From` khác nhau. Tuy nhiên, provider SMTP có thể yêu cầu địa chỉ hoặc domain `From` được xác minh hoặc cấp quyền. Nếu vi phạm, server có thể từ chối, chỉnh sender, hoặc chính sách nhận có thể đánh dấu email đáng ngờ.

`Reply-To` cũng không thay thế username SMTP hoặc địa chỉ bounce. Việc chọn domain gửi ảnh hưởng SPF, DKIM, DMARC và khả năng giao thư, nên được quản lý ở lớp cấu hình/triển khai chứ không chỉ là chuyện thay một chuỗi trong `SimpleMailMessage`.

Một cách tổ chức là cấu hình các địa chỉ gửi ứng với loại thông báo riêng, inject vào service:

```properties
app.mail.from.account=no-reply@example.com
app.mail.from.billing=billing@example.com
```

Đây là **application properties do dự án tự định nghĩa**, không phải các property chuẩn mặc định của Spring Boot. Ứng dụng có thể đọc bằng `@ConfigurationProperties` hoặc `@Value` và sử dụng khi tạo từng message.

## 12. Gửi mail từ luồng HTTP và xử lý bất đồng bộ

`JavaMailSender#send(...)` trong cách dùng SMTP thông thường là **lời gọi blocking**: thread gọi nó chờ tới khi quá trình submission hoàn tất hoặc phát sinh lỗi. Bean singleton không biến `send` thành tác vụ nền.

Ví dụ một request trực tiếp gọi:

```text
HTTP POST /orders
      |
      v
OrderService.createOrder()
      |
      +--> ghi đơn hàng
      |
      +--> mailSender.send()
               |
               +--> TCP connect / TLS / AUTH / DATA
      |
      v
HTTP response
```

Nếu SMTP chậm hoặc timeout, request HTTP cũng có thể bị kéo dài. Với thông báo phụ thuộc giao dịch, nên cân nhắc hàng đợi hoặc **transactional outbox**:

```text
HTTP request
     |
     v
Business Service
     |
     +--> Ghi dữ liệu nghiệp vụ + outbox record
     |    trong transaction phù hợp
     |
     v
HTTP response
     |
     v
Background Worker
     |
     +--> JavaMailSender singleton bean
     |    (trên instance ứng dụng/worker này)
     |
     v
SMTP relay / ESP
     |
     v
Webhook delivered/bounced nếu provider hỗ trợ
```

Trong kiến trúc này:

1. Business service lưu yêu cầu cần gửi.
2. Worker lấy từng delivery job, tạo message mới rồi dùng sender bean đã được inject.
3. Worker giới hạn độ đồng thời, retry có backoff và ghi attempt.
4. Hệ thống theo dõi trạng thái submission riêng với delivered/bounced.

Nếu gọi mail đồng bộ ngay trong transaction rồi sau đó transaction rollback, email có thể **đã ra khỏi hệ thống** trong khi dữ liệu nghiệp vụ chưa được commit. Outbox giúp tránh loại lệch trạng thái này khi được triển khai đúng.

### `@Async` có thay thế outbox không?

Có thể tạo một phương thức `@Async` trong một service được Spring quản lý để chuyển việc gửi qua executor, nhưng cần bật `@EnableAsync` và cấu hình executor phù hợp. Gọi nội bộ (self-invocation) qua `this.someAsyncMethod()` thường không đi qua Spring proxy nên có thể không chạy bất đồng bộ như dự kiến.

`@Async` không tự bảo đảm lưu bền vững email chưa gửi nếu tiến trình bị dừng; outbox hoặc queue bền vững thích hợp hơn cho thông báo không được phép thất lạc. Dù gửi đồng bộ hay async, vẫn cần timeout socket và kiểm soát retry.

## 13. Xử lý lỗi ở một nơi thống nhất

Dùng chung bean giúp thống nhất việc cấu hình SMTP, nhưng không tự thống nhất chính sách xử lý lỗi. Tùy kiến trúc, có thể tạo một adapter nhận `JavaMailSender` để các service nghiệp vụ gọi qua.

Ví dụ:

```java
package example.mail;

import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class EmailGateway {
    private final JavaMailSender sender;

    public EmailGateway(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendPlainText(
            String from, String to, String subject, String body) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setTo(to);
        message.setSubject(subject);
        message.setText(body);

        try {
            sender.send(message);
        } catch (MailException exception) {
            // Ở đây có thể ghi nhận attempt ID, loại lỗi và thời gian.
            // Tránh ghi password, OTP hoặc toàn bộ email vào log.
            throw exception;
        }
    }
}
```

Đây là ví dụ ranh giới hạ tầng. Adapter có thể bổ sung metrics, phân loại lỗi và correlation ID theo nhu cầu. Khi nhiều nhóm nghiệp vụ có cách định dạng nội dung khác nhau, đừng ép tất cả email vào một phương thức `sendPlainText` duy nhất; có thể mở rộng thêm phương thức MIME hoặc dùng nhiều collaborator cho phần render.

### Những loại lỗi cần nghĩ đến

| Nhóm vấn đề | Biểu hiện | Hướng xử lý |
| --- | --- | --- |
| Kết nối SMTP | Connect/read/write timeout, connection refused | Kiểm tra network, timeout và retry có giới hạn |
| Xác thực | Sai credentials hoặc SMTP policy từ chối | Sửa secret/quyền gửi, không retry mù quáng |
| Nội dung/header | Email, MIME hoặc địa chỉ không hợp lệ | Xác thực dữ liệu và sửa cách tạo message |
| Provider policy | Rate limit, sender chưa xác minh, giới hạn recipient | Theo chính sách ESP và điều chỉnh cấu hình |
| Kết quả gửi không chắc chắn | Timeout sau khi gửi DATA nhưng trước xác nhận | Đối soát trước khi retry để hạn chế trùng |
| Delivery sau submission | Bounce, deferred, spam filtering | Theo dõi event của ESP, không suy từ `send()` |

Một lần `sender.send(message)` thành công thường chỉ xác nhận quá trình gửi đến SMTP relay đã được chấp nhận theo phạm vi kết nối đó. **Không thể suy ra thư đã đến inbox hoặc đã được đọc**.

## 14. Kiểm thử service nhờ dependency injection

Một lợi ích thực tế của bean dùng chung qua giao diện là **unit test không cần SMTP server**. Có thể truyền mock `JavaMailSender` vào constructor rồi kiểm tra nội dung được tạo.

Ví dụ, dùng JUnit Jupiter và Mockito cho `AccountMailService` ở phần 4:

```java
package example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.mock;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class AccountMailServiceTest {

    @Test
    void sendsWelcomeMessage() {
        JavaMailSender sender = mock(JavaMailSender.class);
        AccountMailService service = new AccountMailService(sender);

        service.sendWelcome("user@example.net", "An");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(sender).send(captor.capture());

        SimpleMailMessage sent = captor.getValue();
        assertEquals("no-reply@example.com", sent.getFrom());
        assertEquals("Chào mừng bạn", sent.getSubject());
        assertEquals("user@example.net", sent.getTo()[0]);
        assertEquals(
            "Xin chào An!\nTài khoản của bạn đã được tạo thành công.",
            sent.getText()
        );
    }
}
```

Test trên chỉ kiểm tra cách service tạo và chuyển `SimpleMailMessage` cho sender. Nó **không kiểm tra SMTP kết nối thật**, TLS, credential hay giao thư tới mailbox.

Đối với thư MIME, có thể sử dụng fake/mock `JavaMailSender` hoặc công cụ kiểm tra MIME riêng để xem header, body và attachment. Một integration test có thể cấu hình `JavaMailSender` trỏ đến **SMTP test server cục bộ** để kiểm tra việc ứng dụng thực sự trao đổi SMTP mà không gửi email tới người dùng thật.

### Chia mức kiểm thử

| Mức | Mục tiêu | Gợi ý |
| --- | --- | --- |
| Unit test service | Kiểm tra To/From/Subject, lựa chọn template và nội dung | Mock interface `JavaMailSender` |
| Component test | Kiểm tra cấu hình bean và lựa chọn sender | Khởi tạo Spring test context |
| Integration test | Kiểm tra SMTP/MIME thực tế | SMTP test server nội bộ, cấu hình test |
| End-to-end/production monitoring | Kiểm tra giao thư, bounce và policy nhà cung cấp | ESP webhook, dashboard và email thử nghiệm có kiểm soát |

Không nên để unit test cần network hoặc credential production. Việc Spring có một bean singleton cũng không tự bảo đảm server SMTP khả dụng; đó là điều các mức test/giám sát khác phải đánh giá.

## 15. Các lỗi cấu hình bean thường gặp

| Triệu chứng | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` cho `JavaMailSender` | Thiếu dependency hoặc auto-configuration chưa có điều kiện phù hợp; cấu hình không được quét | Kiểm tra starter, `spring.mail.host`, context và khai báo `@Bean` |
| `NoUniqueBeanDefinitionException` | Có nhiều sender bean cùng kiểu | Dùng `@Qualifier` hoặc `@Primary` có chủ đích |
| Service gọi `mailSender` bị `null` | Tạo service bằng `new` nhưng không truyền dependency, hoặc không để Spring quản lý | Constructor injection và khởi tạo theo Spring |
| Cấu hình trong `application.properties` không có tác dụng | Bean `JavaMailSender` tự tạo thay auto-configuration hoặc profile sai | Rà soát nguồn tạo bean và config thực sự |
| Gửi được loại thư A nhưng loại B bị từ chối | `From` khác domain được phép, attachment quá lớn hoặc policy ESP | Kiểm tra message và nhà cung cấp |
| Gửi đồng thời bị giới hạn | Provider hạn chế connection/rate; quá nhiều worker | Thêm queue, limit concurrency, backoff |
| Nội dung thư của các request bị lẫn | Tái sử dụng `MimeMessage`/`SimpleMailMessage` mutable giữa thread | Tạo message mới cho mỗi delivery |
| Sau khi đổi password vẫn báo lỗi | Secret không được cập nhật trong instance/config đang chạy | Thiết kế secret rotation và tái khởi tạo sender có kiểm soát |
| Request HTTP chậm do SMTP | `send()` được gọi đồng bộ | Dùng worker/outbox/queue theo yêu cầu nghiệp vụ |
| Test vô tình gửi mail thật | Unit test dùng bean production hoặc cấu hình SMTP thật | Inject mock/fake, test SMTP riêng biệt |

### Vấn đề đặc biệt khi triển khai nhiều replica

Giả sử ứng dụng chạy ở ba pod. Trong mỗi pod, Spring có một `JavaMailSender` singleton. Như vậy thực tế có **ba sender instance**, và cả ba có thể gửi đồng thời vào cùng ESP.

Khi provider cho phép 20 kết nối/s hoặc một ngưỡng rate limit nhất định, giới hạn của một thread pool trong **một pod** chưa chắc đủ bảo đảm tổng tải. Cần cân nhắc quota chung, queue tập trung, worker scaling và khả năng retry khi bị throttling.

Đồng thời, nếu cả ba pod đều đọc cùng một outbox không có cơ chế claim/lock đúng, chúng có thể gửi trùng một notification. Vấn đề này thuộc quản lý delivery job, không thể giải quyết bằng singleton scope.

## 16. Thực hành cấu hình an toàn và dễ vận hành

Một sender bean dùng chung nên được xem là **cổng hạ tầng** của ứng dụng, cần chuẩn hóa một số yếu tố:

1. **Cấu hình tách khỏi mã nguồn**: dùng environment variables, secret manager hoặc cấu hình triển khai cho host, credentials và timeout.
2. **TLS đúng yêu cầu provider**: với STARTTLS, bật `mail.smtp.starttls.enable` và `required` nếu chính sách bắt buộc mã hóa; với implicit TLS dùng cấu hình phù hợp.
3. **Không log dữ liệu bí mật**: tránh in password, mã xác thực, nội dung email, access token và thông tin người nhận không cần thiết.
4. **Timeout rõ ràng**: cấu hình connect/read/write timeout bằng số liệu thực tế; không xem chúng là deadline tổng.
5. **Kiểm soát throughput**: queue, worker pool, hạn mức provider, backoff và giám sát backlog.
6. **Quan sát được từng lần gửi**: delivery ID, attempt ID, loại thư, sender profile, thời gian gửi, loại lỗi và thông điệp từ SMTP phù hợp.
7. **Tách submission khỏi delivery**: dùng webhook/event từ ESP nếu cần biết delivered, bounced hoặc các trạng thái sau khi relay nhận thư.
8. **Quy định quyền gửi theo domain**: một bean có thể đặt nhiều `From` trong message, nhưng sender account vẫn phải được provider cho phép.
9. **Tạo message theo lần gọi**: không giữ `MimeMessage`, attachment stream hoặc state người nhận trong field mutable của singleton service.
10. **Giữ interface làm dependency**: service phụ thuộc `JavaMailSender`, còn chi tiết `JavaMailSenderImpl` và SMTP properties nằm ở tầng cấu hình.

### Ví dụ tổ chức thư mục

Một cấu trúc đơn giản có thể là:

```text
src/main/java/example/
├── config/
│   └── MailConfiguration.java       (nếu cần cấu hình thủ công)
├── mail/
│   ├── EmailGateway.java            (adapter gửi chung, tùy kiến trúc)
│   ├── AccountMailService.java      (email đăng ký)
│   ├── InvoiceMailService.java      (email hóa đơn)
│   └── MailTemplateRenderer.java    (render template)
└── order/
    └── OrderService.java            (nghiệp vụ chính)

src/main/resources/
├── application.properties
└── templates/mail/
    ├── welcome.html
    └── invoice.html
```

Với Spring Boot auto-configuration, có thể **không cần `MailConfiguration.java`**. Đó là một ưu điểm: dependency và property đủ để có sender bean dùng chung. Các service tập trung vào nội dung/luồng nghiệp vụ thay vì tự dựng hạ tầng mạng.

## 17. Một luồng triển khai hoàn chỉnh

Giả sử yêu cầu là “ứng dụng Spring gửi email đăng ký và hóa đơn, cùng sử dụng một tài khoản SMTP”.

**Bước 1:** Thêm `spring-boot-starter-mail`, khai báo `spring.mail.*` và đưa credentials qua secret của môi trường.

**Bước 2:** Để Boot tạo `JavaMailSender` khi điều kiện auto-configuration được đáp ứng; tránh tự tạo sender ở từng service.

**Bước 3:** Viết `AccountMailService` và `InvoiceMailService`, tiêm `JavaMailSender` qua constructor. Mỗi lần gọi tạo message riêng.

**Bước 4:** Đặt `From`, `Reply-To`, charset, tiêu đề và nội dung theo từng loại thư; bảo đảm các sender address được ESP cho phép.

**Bước 5:** Với email ít quan trọng, quyết định có thể gửi đồng bộ hay không; với email liên quan giao dịch quan trọng, cân nhắc outbox + worker để tách SMTP khỏi HTTP transaction.

**Bước 6:** Tạo unit test cho logic email bằng mock interface và integration test bằng SMTP test server. Quan sát delivery/bounce từ ESP khi vận hành thực tế.

**Bước 7:** Nếu sau này cần thêm nhà cung cấp khác, thêm cấu hình/bean có qualifier rõ ràng hoặc thiết kế sender registry; không đổi host và credentials trên bean singleton đang phục vụ request.

Bản chất của **`JavaMailSender` làm bean dùng chung** là **dùng chung thành phần cấu hình và gửi email do Spring quản lý**. Các message vẫn được khởi tạo độc lập và xử lý theo từng delivery. Khi giữ ranh giới này rõ ràng, ứng dụng dễ kiểm thử, dễ thay đổi SMTP provider và có thể mở rộng gửi email đồng thời mà không trộn trạng thái giữa các người nhận.
