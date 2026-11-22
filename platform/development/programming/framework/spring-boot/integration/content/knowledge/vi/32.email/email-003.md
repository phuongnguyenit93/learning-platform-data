# SimpleMailMessage và MimeMessageHelper trong Spring Boot

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, ứng dụng Spring Boot kết nối hệ thống qua HTTP client, cơ sở dữ liệu, cache, message broker và các adapter của Spring Integration. Một nhu cầu tích hợp phổ biến là **gửi email thông báo**: xác nhận đơn hàng, thông báo đối soát, gửi báo cáo hoặc cảnh báo vận hành. Ở đây, email là một tác động ra ngoài hệ thống tương tự lời gọi HTTP hoặc phát thông điệp; vì thế cần kiểm soát cấu hình, hợp đồng dữ liệu, transaction, lỗi, xử lý trùng lặp, kiểm thử và quan sát.

Spring hỗ trợ gửi email qua **`JavaMailSender`**, sử dụng Jakarta Mail để tạo thông điệp và kết nối SMTP. Hai công cụ quan trọng:

- **`SimpleMailMessage`**: biểu diễn email **văn bản thuần**, có người gửi, người nhận, chủ đề và nội dung đơn giản.
- **`MimeMessageHelper`**: hỗ trợ xây dựng `MimeMessage` với **HTML, phần văn bản thay thế, CC/BCC, tệp đính kèm, nội dung đa phần và ảnh nhúng (inline)**.

Bài học thuộc chương **Email**, tập trung trực tiếp vào **`SimpleMailMessage` và `MimeMessageHelper`**. Sau bài này, bạn có thể:

1. Cấu hình `spring.mail.*` và inject `JavaMailSender` do Spring Boot quản lý.
2. Gửi email plain text bằng `SimpleMailMessage`.
3. Tạo email HTML, plain-text alternative, attachment và inline resource bằng `MimeMessageHelper`.
4. Phân biệt quá trình **tạo MIME** với **SMTP gửi**, hiểu ý nghĩa của kết quả gửi.
5. Xây dựng adapter email an toàn: timeout, TLS, validation, template, retry và idempotency.
6. Tích hợp email với SQL/outbox/message broker mà không giả định transaction phân tán.
7. Viết unit/integration test không gửi email thật và theo dõi chất lượng vận hành.

> **Giới hạn quan trọng:** `JavaMailSender.send(...)` hoàn thành mà không có exception thường chỉ có nghĩa SMTP server đã **chấp nhận xử lý thông điệp trong phiên gửi**. Nó **không** bảo đảm email đã được giao tới hộp thư cuối, đã vượt bộ lọc spam hay đã được người nhận đọc.

## 1. Mô hình gửi email trong luồng tích hợp

Một luồng thông báo đơn hàng có thể gồm các bước:

~~~mermaid
flowchart LR
    A["Đơn hàng thay đổi trạng thái"] --> B["Application service"]
    B --> C["SQL transaction"]
    C --> D["Order + notification outbox"]
    D --> E["Outbox relay / broker"]
    E --> F["Email worker"]
    F --> G{"Thông điệp"}
    G -->|"Text đơn giản"| H["SimpleMailMessage"]
    G -->|"HTML/attachment"| I["MimeMessageHelper"]
    H --> J["JavaMailSender"]
    I --> J
    J --> K["SMTP relay"]
    K --> L["Mail provider / người nhận"]
    F -.-> M["Logs + metrics + retry/DLQ"]
~~~

Các thành phần có trách nhiệm tách biệt:

| Thành phần | Vai trò | Không tự cung cấp |
| --- | --- | --- |
| `JavaMailSender` | Gửi thư thông qua cấu hình SMTP | Giao hàng cuối cùng, exactly-once |
| `SimpleMailMessage` | Nội dung email text/plain | HTML, attachment, MIME multipart |
| `MimeMessage` | Thông điệp theo chuẩn MIME | Chính sách nghiệp vụ và retry |
| `MimeMessageHelper` | Tạo MIME thuận tiện, xử lý encoding và multipart | Template sanitization, anti-virus |
| SMTP relay/provider | Chấp nhận và chuyển tiếp email | Xác nhận người dùng đã đọc |
| Email application adapter | Ánh xạ dữ liệu nghiệp vụ sang email | Độ bền nếu không có outbox |
| Outbox/broker | Lưu ý định gửi và cho phép xử lý lại | Chống gửi email trùng nếu thiếu khóa nghiệp vụ |

**Vì sao email nên là adapter?** Domain service nên mô tả ý định như `sendOrderConfirmation(orderId)`, không trực tiếp ghép HTML, SMTP header và MIME attachment. Khi thay SMTP provider hoặc đổi thiết kế email, nghiệp vụ vẫn giữ hợp đồng của nó.

## 2. Cài đặt dependency và auto-configuration

Spring Boot hỗ trợ **MailSender auto-configuration** khi có các thư viện mail phù hợp, cùng cấu hình như `spring.mail.host`. Với ứng dụng Gradle Groovy DSL thông thường:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Starter mang vào Spring Mail và Jakarta Mail cần để gửi SMTP. Khi điều kiện phù hợp và chưa có bean `JavaMailSender` riêng do ứng dụng tạo, Boot có thể cấu hình `JavaMailSenderImpl` từ `spring.mail.*`.

**Không cần tự tạo `JavaMailSenderImpl` chỉ để gửi SMTP thông thường.** Tự tạo bean có thể làm một phần cấu hình mặc định nhường chỗ; khi đó bạn chịu trách nhiệm host, port, credentials, session, timeouts và lifecycle.

Các lớp chính:

~~~java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import jakarta.mail.internet.MimeMessage;
~~~

Từ Spring Framework 6 / Spring Boot 3 trở lên, API mail dựa trên **`jakarta.mail.*`**, không còn dùng `javax.mail.*` như nhiều ví dụ cũ. Không trộn hai namespace trong cùng project.

### 2.1. Bean nào được inject?

~~~java
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Component;

@Component
public class MailTransportProbe {

    private final JavaMailSender mailSender;

    public MailTransportProbe(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }
}
~~~

Nếu có lỗi `No qualifying bean of type JavaMailSender`, trước hết kiểm tra starter, cấu hình `spring.mail.host` (hoặc cấu hình JNDI mail session được hỗ trợ), auto-configuration conditions và việc ứng dụng có tự tạo bean mail khác hay không.

Spring `MailSender` là interface gửi email đơn giản, còn `JavaMailSender` mở rộng để xử lý MIME/Jakarta Mail. Khi cần attachment hoặc HTML, inject `JavaMailSender`.

## 3. Cấu hình spring.mail.*: host, cổng, TLS và timeout

Ví dụ một hệ thống có SMTP relay hỗ trợ **STARTTLS trên cổng 587**:

~~~yaml
# application.yml
spring:
  mail:
    host: ${SMTP_HOST:smtp.example.org}
    port: ${SMTP_PORT:587}
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
      "[mail.debug]": false

notifications:
  mail:
    from: ${NOTIFICATION_FROM:no-reply@example.org}
~~~

`smtp.example.org` và `no-reply@example.org` chỉ là **địa chỉ minh họa**. Ở production, URL, username, password và địa chỉ gửi phải do hệ thống vận hành/provisioning cung cấp. Không đưa mật khẩu thật vào mã nguồn hoặc logs.

| Property | Vai trò | Ghi chú |
| --- | --- | --- |
| `spring.mail.host` | Máy chủ SMTP | Tên DNS/host relay |
| `spring.mail.port` | Cổng SMTP | Phụ thuộc STARTTLS hay implicit TLS |
| `spring.mail.username/password` | SMTP authentication | Lấy từ secret manager/env |
| `spring.mail.default-encoding` | Charset mặc định | UTF-8 với nội dung tiếng Việt |
| `mail.smtp.auth` | Yêu cầu xác thực SMTP | Phụ thuộc relay |
| `mail.smtp.starttls.enable` | Bắt đầu SMTP rồi nâng cấp kết nối bằng STARTTLS | Không đồng nghĩa implicit TLS |
| `mail.smtp.starttls.required` | Từ chối gửi nếu STARTTLS không khả dụng | Hữu ích khi TLS là bắt buộc |
| `mail.smtp.connectiontimeout` | Timeout mở kết nối, đơn vị **mili giây** | Thuộc Jakarta Mail provider |
| `mail.smtp.timeout` | Timeout đọc phản hồi SMTP, mili giây | Không phải deadline end-to-end |
| `mail.smtp.writetimeout` | Timeout ghi dữ liệu, mili giây | Không phải timeout tổng của job |
| `mail.debug` | Logging chi tiết giao thức | **Tắt production** nếu có nguy cơ lộ thông tin |

Định dạng `"[mail.smtp.auth]"` trong YAML thể hiện **một key nguyên vẹn của map** `spring.mail.properties`. Các thuộc tính `mail.smtp.*` thuộc Jakarta Mail provider; tên/đơn vị phải được kiểm chứng với provider tương ứng.

### 3.1. Cổng 587 STARTTLS và 465 implicit TLS

Hai cấu hình không hoán đổi tùy tiện:

- **587/STARTTLS**: khởi tạo phiên SMTP rồi nâng cấp TLS. Cấu hình `mail.smtp.starttls.enable=true` và `required=true` khi relay yêu cầu.
- **465/implicit TLS (SMTPS)**: TLS bắt đầu ngay khi kết nối. Cần cấu hình SSL phù hợp, thường `mail.smtp.ssl.enable=true`, đồng thời dùng cổng tương ứng.

Không chỉ đổi `port: 587` thành `465` rồi giữ mọi thuộc tính STARTTLS như cũ. Thực hiện theo tài liệu SMTP provider và kiểm chứng chứng chỉ, hostname; không tắt certificate validation để vượt lỗi TLS.

### 3.2. Vì sao cần timeout?

Một tác vụ gửi email có thể chạy trong HTTP request, scheduled job hoặc broker consumer. Nếu transport không có timeout hữu hạn, thread worker có thể bị giữ quá lâu khi SMTP relay mất kết nối.

Phân biệt:

1. **Connection timeout**: chờ thiết lập kết nối.
2. **Read timeout**: chờ phản hồi SMTP.
3. **Write timeout**: chờ ghi request/email.
4. **Application deadline**: tổng thời gian cho một nghiệp vụ, gồm queue, render template, retry và gửi.
5. **Delivery latency**: thời gian từ lúc SMTP chấp nhận đến lúc hộp thư nhận (không nằm trong phạm vi một lời gọi `send`).

Không đặt timeout cực lớn để che một relay thường xuyên không đáp ứng. Khi gửi batch, cần giới hạn concurrency và số lần retry để tránh làm cạn thread pool.

### 3.3. Kiểm tra kết nối khi startup

Một số phiên bản Spring Boot hỗ trợ `spring.mail.test-connection=true` để thử kết nối mail server lúc khởi động. Tính năng này có thể giúp fail-fast khi SMTP không khả dụng, nhưng cũng có thể khiến **toàn bộ ứng dụng không khởi động** chỉ vì dịch vụ thông báo tạm thời lỗi.

Với ứng dụng quan trọng vẫn cần phục vụ các API khác khi SMTP mất, nên cân nhắc kiểm tra SMTP qua health indicator/monitoring và outbox retry thay vì ép kết nối mail là điều kiện startup bắt buộc.

## 4. SimpleMailMessage: email văn bản thuần

`SimpleMailMessage` được thiết kế cho email **plain text**; nó giữ các trường như from, to, cc, bcc, replyTo, sentDate, subject và text. Nó không có cấu trúc MIME multipart để chứa file/HTML.

Ví dụ service:

~~~java
// PlainTextNotificationService.java
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class PlainTextNotificationService {

    private final JavaMailSender mailSender;

    public PlainTextNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderReceived(
            String recipient,
            String orderId) {

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.org");
        message.setTo(recipient);
        message.setSubject("Xác nhận tiếp nhận đơn hàng");
        message.setText(
                "Chúng tôi đã tiếp nhận đơn hàng " + orderId
                + ".\nBạn sẽ nhận thông tin tiếp theo khi xử lý xong.");

        mailSender.send(message);
    }
}
~~~

Ở đây địa chỉ người gửi được viết cứng **chỉ để minh họa**. Trong production nên bind giá trị `notifications.mail.from` qua `@ConfigurationProperties` và kiểm tra địa chỉ đã được SMTP provider cho phép sử dụng. `orderId` phải đến từ nghiệp vụ đáng tin cậy, tránh đưa trực tiếp dữ liệu người dùng không kiểm soát vào tiêu đề hoặc body.

**Điểm đáng nhớ:**

- `setText(...)` tạo nội dung text/plain, **không render HTML**.
- `setTo(...)` cho phép danh sách địa chỉ; không copy danh sách người nhận giữa các tenant.
- `setCc(...)` / `setBcc(...)` phục vụ các kiểu người nhận khác nhau.
- `setReplyTo(...)` đặt địa chỉ nhận phản hồi, không đồng nghĩa người gửi SMTP.
- `mailSender.send(message)` có thể ném `MailException` khi chuẩn bị/gửi bị lỗi.

### 4.1. Tránh dùng lại message mutable cho nhiều lần gửi

`SimpleMailMessage` là một bean dữ liệu **có thể thay đổi**. Đừng tạo một singleton `SimpleMailMessage` rồi các thread cùng sửa `to`/`subject` và gửi đồng thời. Có nguy cơ người nhận A nhận nội dung dự kiến cho B.

Thay vào đó, tạo **một object message mới cho mỗi ý định gửi**. Nếu muốn sao chép các giá trị tĩnh từ một template, Spring có cơ chế copy constructor, nhưng vẫn cần đảm bảo địa chỉ và nội dung từng request được đặt lại đầy đủ.

### 4.2. Khi nào chọn SimpleMailMessage?

Phù hợp cho:

- Cảnh báo nội bộ ngắn, không cần định dạng.
- Email thông báo có ít trường và không có attachment.
- Bản plain text của một workflow đơn giản.
- Thư cần dễ đọc trên hầu hết mail clients, bao gồm thiết bị hỗ trợ hạn chế.

Không phù hợp khi cần HTML, ảnh inline, nhiều phần content hoặc tệp đính kèm. Đừng đặt chuỗi `<b>Đơn hàng</b>` vào `SimpleMailMessage.setText(...)` rồi mong mail client hiển thị chữ đậm.

## 5. MimeMessage và MimeMessageHelper: email phong phú

`MimeMessage` là đối tượng email theo cấu trúc MIME do Jakarta Mail cung cấp. Nó có thể chứa nhiều body parts và metadata. `MimeMessageHelper` đơn giản hóa việc tạo và định dạng MimeMessage.

Các bước điển hình:

1. Gọi `JavaMailSender.createMimeMessage()`.
2. Tạo `MimeMessageHelper` với chế độ multipart/charset phù hợp.
3. Đặt From/To/Subject, content plain text và HTML.
4. Thêm tệp đính kèm hoặc inline resources khi cần.
5. Gọi `JavaMailSender.send(mimeMessage)`.

Ví dụ HTML đơn giản, có plain-text alternative:

~~~java
// RichNotificationService.java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class RichNotificationService {

    private final JavaMailSender mailSender;

    public RichNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderConfirmed(
            String recipient,
            String orderId) throws MessagingException {

        MimeMessage mimeMessage = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                mimeMessage,
                true,
                StandardCharsets.UTF_8.name());

        helper.setFrom("no-reply@example.org");
        helper.setTo(recipient);
        helper.setSubject("Đơn hàng đã được xác nhận");

        String plainText =
                "Đơn hàng " + orderId + " đã được xác nhận.";

        // HTML tĩnh cho minh họa; dữ liệu động phải được escape
        // qua template engine có bảo vệ chống HTML injection.
        String htmlText =
                "<html><body><h2>Đơn hàng đã xác nhận</h2>"
                + "<p>Vui lòng xem chi tiết trong tài khoản.</p>"
                + "</body></html>";

        helper.setText(plainText, htmlText);
        mailSender.send(mimeMessage);
    }
}
~~~

Ở mức ví dụ, `plainText` chứa ID, còn `htmlText` là nội dung tĩnh để không đưa giá trị chưa escape vào HTML. Một template sản xuất có thể hiển thị ID trong HTML, nhưng cần cơ chế HTML escaping chuẩn.

**Lưu ý:** `MimeMessageHelper.setText(plainText, htmlText)` tạo **multipart/alternative** để mail client chọn bản hiển thị phù hợp; đây không phải hai email riêng. Hàm `setText(htmlText, true)` tạo nội dung HTML nhưng không cung cấp bản text thuần thay thế.

### 5.1. Khi nào cần bật multipart?

Các constructor thường gặp:

~~~java
// Email chỉ cần body text hoặc HTML, không cần attachment:
new MimeMessageHelper(mimeMessage, "UTF-8");

// Email multipart, cần attachment / inline:
new MimeMessageHelper(mimeMessage, true, "UTF-8");

// Chọn chế độ multipart tường minh:
new MimeMessageHelper(
        mimeMessage,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
~~~

`true` là constructor thuận tiện để bật multipart theo chế độ do helper lựa chọn. Với email vừa có HTML, hình inline và attachments, có thể chọn `MULTIPART_MODE_MIXED_RELATED` để tạo cấu trúc phối hợp; các mail client có thể diễn giải hơi khác nhau, nên cần kiểm thử với những client chính.

| Nhu cầu | SimpleMailMessage | MimeMessageHelper |
| --- | --- | --- |
| Plain text | Có | Có |
| Tiêu đề UTF-8, tiếng Việt | Có qua cấu hình sender | Có qua charset rõ ràng |
| HTML | Không | Có |
| Plain text + HTML alternative | Không | Có |
| Attachment | Không | Có |
| Embedded image / cid inline | Không | Có |
| Custom MIME headers | Không phải mục tiêu | Có qua MimeMessage/Jakarta Mail |
| Gửi SMTP | `JavaMailSender.send(...)` | `JavaMailSender.send(...)` |

### 5.2. Charset và tiêu đề tiếng Việt

Dùng `UTF-8` cho HTML/plain text để tránh lỗi chữ có dấu như “Xác nhận đơn hàng”. Nếu ứng dụng nhận nội dung từ nhiều hệ thống, cần thống nhất Unicode normalization và encoding của template. Với `MimeMessageHelper`, đặt charset rõ ràng hoặc bảo đảm `spring.mail.default-encoding` đã được cấu hình.

Đừng tự encode MIME subject hoặc Base64 nội dung bằng cách ghép chuỗi không chuẩn; `MimeMessageHelper` và Jakarta Mail xử lý encoding phù hợp.

## 6. Gửi email có tệp đính kèm

Ví dụ gửi hóa đơn PDF đã được tạo ở tầng nghiệp vụ. Ở đây `pdfBytes` chứa **byte PDF thật** từ một service khác; ví dụ không tự sinh PDF.

~~~java
// InvoiceEmailService.java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceEmailService {

    private final JavaMailSender mailSender;

    public InvoiceEmailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient,
            String invoiceNumber,
            byte[] pdfBytes) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom("invoices@example.org");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn " + invoiceNumber);
        helper.setText(
                "Hóa đơn đã được phát hành.",
                "<p>Hóa đơn của bạn đã được phát hành.</p>");

        helper.addAttachment(
                "invoice.pdf",
                new ByteArrayResource(pdfBytes),
                "application/pdf");

        mailSender.send(message);
    }
}
~~~

Điểm quan trọng:

- `ByteArrayResource` cho phép Jakarta Mail đọc lại dữ liệu đính kèm từ bộ nhớ khi xây dựng MIME. Nó phù hợp với tệp vừa phải, **không phù hợp với file rất lớn**.
- `addAttachment(filename, InputStreamSource, contentType)` nhận tên file hiển thị và dữ liệu nguồn. Chọn content type đúng để mail client nhận diện.
- Giữ tên file an toàn, không tin tuyệt đối tên do người dùng gửi, không đưa path hệ thống thật vào tên file.
- Giới hạn kích thước **trước khi** chuyển đổi sang MIME: Base64/MIME encoding còn làm email lớn hơn byte gốc.
- Không đính kèm báo cáo/bản sao ID cá nhân/dữ liệu tài chính nếu không có mục đích, phân quyền và chính sách bảo mật.
- Cân nhắc quét mã độc với tệp người dùng upload trước khi gửi và kiểm soát danh sách loại file được phép.

Nếu attachment được đọc từ file hoặc stream, giữ nguồn tài nguyên còn truy cập được **cho đến khi thông điệp được gửi**. Một số `InputStreamSource` chỉ đọc stream được một lần sẽ gây lỗi nếu JavaMail yêu cầu đọc lại. `ByteArrayResource` và các resource Spring phù hợp giúp xử lý trường hợp đó.

### 6.1. Không tải tệp cực lớn vào byte[]

Đối với báo cáo dung lượng lớn, có thể:

- Tạo một đường link tải có thời hạn, được phân quyền và audit thay vì attachment.
- Lưu tệp ở object storage an toàn, gửi link được ký có hạn thay vì tệp.
- Dùng cơ chế lưu trữ file có kiểm soát và `FileSystemResource` nếu kích thước phù hợp.
- Thiết kế quota, size limit và cleanup sau khi gửi.

Không dùng email như phương thức truyền dữ liệu nhạy cảm dung lượng lớn nếu có kênh trao đổi được kiểm soát tốt hơn.

## 7. Ảnh inline với Content-ID (cid)

Email HTML có thể tham chiếu ảnh nội tuyến qua `cid:...`:

~~~html
<html>
  <body>
    <h2>Thông báo từ hệ thống</h2>
    <img src="cid:brand-logo" alt="Biểu trưng" width="120">
  </body>
</html>
~~~

Trong Java:

~~~java
import org.springframework.core.io.ClassPathResource;

helper.setText(
        "Thông báo từ hệ thống",
        "<h2>Thông báo từ hệ thống</h2>"
            + "<img src=\"cid:brand-logo\" alt=\"Biểu trưng\">");

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png");
~~~

Snippet này giả định tài nguyên `mail/brand-logo.png` có thật trong classpath và `helper` là `MimeMessageHelper` đã bật multipart. Nếu file không có, cần xử lý lỗi tài nguyên ở application adapter.

**Thứ tự nên dùng:** gọi `setText(...)` trước `addInline(...)`, vì thứ tự nội dung MIME ảnh hưởng khả năng mail client nhận diện resource. `addInline` gắn Content-ID; trong HTML tham chiếu `cid:brand-logo` mà không dùng URL web tùy tiện.

Ảnh inline có thể không được mọi mail client hiển thị giống nhau. Nhiều client chặn hình ảnh theo chính sách bảo mật, vì vậy luôn cung cấp văn bản/alt text để email vẫn hiểu được khi không có ảnh.

## 8. Thiết kế email template và hợp đồng dữ liệu

Một đơn hàng có thể gửi qua email theo nhiều ngôn ngữ. Không nên để Controller, Kafka consumer hoặc Quartz Job tự ghép HTML bằng phép cộng chuỗi.

Một hợp đồng đầu vào tối thiểu:

~~~java
// OrderConfirmationNotice.java
public record OrderConfirmationNotice(
        String notificationId,
        String orderId,
        String recipientEmail,
        String localeTag) {
}
~~~

Các trường phải có quy tắc rõ:

| Trường | Trách nhiệm | Chú ý |
| --- | --- | --- |
| `notificationId` | Khóa idempotency/đối soát thông báo | Ổn định xuyên retry/redelivery |
| `orderId` | Tham chiếu nghiệp vụ | Chỉ đưa vào body sau khi kiểm tra quyền |
| `recipientEmail` | Địa chỉ nhận được phép | Validation, không tiết lộ tenant khác |
| `localeTag` | Chọn ngôn ngữ/template | Chỉ whitelist locale được hỗ trợ |
| Template version | Phiên bản nội dung đã phê duyệt | Giữ dấu vết cho replay khi cần |
| Attachment reference | Tài nguyên đính kèm (nếu có) | Quota, kiểm tra quyền và thời hạn |

Đặt việc render template trong một service độc lập, ví dụ `MailTemplateRenderer` trả về `RenderedMail(plainText, htmlText, subject)`. Adapter SMTP chỉ quan tâm dữ liệu đã render và destination.

### 8.1. Tránh HTML injection và template injection

Không đưa text do người dùng cung cấp vào HTML bằng cách nối chuỗi không escape. Ví dụ tên sản phẩm chứa `<script>` hoặc thẻ HTML có thể làm cấu trúc email sai, lộ nội dung hoặc dẫn tới rủi ro tương tác trong những mail clients/renderers yếu.

Sử dụng template engine có HTML escaping mặc định hoặc xử lý escaping tường minh theo ngữ cảnh. Phân biệt HTML text node, HTML attribute và URL — mỗi ngữ cảnh có quy tắc escape/allowlist khác nhau. Không cho phép người dùng sửa nguyên template source hay thực thi template expression tùy ý.

**Email HTML không phải trang web tin cậy.** Tránh script, embedded forms hoặc liên kết đáng ngờ; các mail client cũng có thể loại bỏ CSS/HTML không an toàn.

### 8.2. Template nên có bản plain text

Ngay cả khi thiết kế HTML đẹp, nhiều ứng dụng mail vẫn ưu tiên text/plain trong các trường hợp accessibility hoặc bảo mật. `helper.setText(plainText, htmlText)` cho phép cả hai bản, cải thiện khả năng đọc và khả năng tương thích.

Một email hữu ích nên có subject rõ, người gửi đáng tin cậy, nội dung không yêu cầu mở tệp lạ, thông tin hỗ trợ/phản hồi và cơ chế unsubscribe khi thuộc nhóm email marketing chịu yêu cầu pháp lý tương ứng.

## 9. Exception và ý nghĩa thực sự của kết quả gửi

Spring Mail đưa các lỗi gửi/parse/authentication thành các lớp trong hệ `MailException`, ví dụ:

- `MailAuthenticationException`: không xác thực được với SMTP provider.
- `MailSendException`: có lỗi trong quá trình gửi một hoặc nhiều message.
- `MailParseException` / `MailPreparationException`: không tạo được message hợp lệ.
- `MailException`: loại cha để boundary có thể bắt khi cần.

Ngoài ra, khi **xây dựng MimeMessage** qua `MimeMessageHelper`, có thể xuất hiện checked `MessagingException`; lỗi này xảy ra **trước** hoặc trong quá trình chuẩn bị nội dung, không nên đánh đồng với SMTP outage.

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.MailException;
import org.springframework.mail.MailPreparationException;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public void sendHtml(JavaMailSender sender, String recipient) {

    MimeMessage message = sender.createMimeMessage();

    try {
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setFrom("no-reply@example.org");
        helper.setTo(recipient);
        helper.setSubject("Thông báo");
        helper.setText("Nội dung thuần", "<p>Nội dung HTML</p>");
    } catch (MessagingException exception) {
        throw new MailPreparationException(
                "Không thể tạo email hợp lệ", exception);
    }

    // MailException có thể xuất hiện khi gửi.
    sender.send(message);
}
~~~

Cách tách chuẩn bị/gửi làm rõ các nhóm lỗi:

| Nhóm lỗi | Ví dụ | Hành động |
| --- | --- | --- |
| Cấu hình/vận hành | Sai SMTP host, TLS, password | Cảnh báo, sửa cấu hình; không retry nhanh vô hạn |
| Hợp đồng địa chỉ/nội dung | Địa chỉ email sai, template không render, attachment thiếu | Sửa dữ liệu/template, có thể chuyển xử lý thủ công |
| Tạm thời | SMTP 4xx, network timeout, relay quá tải | Retry giới hạn, exponential backoff/jitter |
| Lỗi chính sách người nhận | Địa chỉ bị từ chối, domain không hợp lệ | Phân loại permanent vs temporary theo provider |
| Kết quả gửi không chắc chắn | Mất kết nối sau khi relay có thể đã nhận | Retry có rủi ro gửi trùng, cần đối soát/khóa nghiệp vụ |
| Lỗi giao nhận sau SMTP accept | Bounce hoặc bị spam filter | Quan sát qua webhook/DSN/provider API nếu có |

### 9.1. SMTP send thành công không đồng nghĩa email đã đến

Một timeline thực tế:

~~~mermaid
sequenceDiagram
    participant W as Email worker
    participant S as SMTP relay
    participant P as Provider/MTA
    participant R as Hộp thư người nhận
    W->>S: Gửi MIME message
    S-->>W: 250 accepted/queued
    Note over W: JavaMailSender.send có thể trả về thành công
    S->>P: Chuyển tiếp sau đó
    alt Được nhận
        P->>R: Deliver
    else Bounce / reject
        P-->>S: Delivery failure
    end
~~~

Do đó cần tách các trạng thái nghiệp vụ như **PENDING → SMTP_ACCEPTED → DELIVERED/BOUNCED** nếu provider cung cấp event tương ứng. Không thể khẳng định `DELIVERED` chỉ vì lời gọi `JavaMailSender.send(...)` không ném exception.

Một số SMTP relay không cung cấp tracking delivery cuối. Nếu bài toán yêu cầu xác nhận pháp lý/kinh doanh rằng đã đến người nhận, cần chọn provider có event callback và lưu lịch sử trạng thái phù hợp.

## 10. Transaction SQL, outbox và vấn đề gửi trùng

Gọi email trực tiếp trong transaction của đơn hàng gây rủi ro:

~~~java
@Transactional
public void confirmOrder(String orderId) {
    orderRepository.markConfirmed(orderId);
    mailSender.send(buildMessage(orderId));
}
~~~

Kịch bản khó:

1. SMTP relay đã chấp nhận email.
2. Transaction SQL sau đó rollback vì lỗi hoặc deadlock.
3. Người nhận nhận email xác nhận dù đơn hàng không được commit.

Ngược lại, nếu SQL commit trước rồi gọi mail bên ngoài transaction, SMTP failure có thể khiến đơn hàng đã xác nhận nhưng không có email. Không có transaction ACID chung giữa JDBC và SMTP một cách mặc định.

### 10.1. Transactional outbox

Kiến trúc đáng tin cậy hơn:

~~~mermaid
flowchart LR
    A["Order confirmed"] --> B["SQL transaction"]
    B --> C["Update orders"]
    B --> D["Insert notification_outbox"]
    D --> E["Worker / broker consumer"]
    E --> F["JavaMailSender"]
    F --> G["SMTP provider"]
    E -.-> H["Retry/Backoff/DLQ"]
    E -.-> I["Status + attempt_count"]
~~~

Bảng outbox minh họa:

~~~sql
CREATE TABLE notification_outbox (
    id UUID PRIMARY KEY,
    notification_type VARCHAR(100) NOT NULL,
    aggregate_id VARCHAR(100) NOT NULL,
    recipient_hash VARCHAR(128) NOT NULL,
    status VARCHAR(32) NOT NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    UNIQUE (notification_type, aggregate_id, recipient_hash)
);
~~~

Unique constraint ở ví dụ chỉ là một **gợi ý nghiệp vụ**: nếu người dùng có thể nhận nhiều thông báo cùng loại cho cùng một đơn, cần có version/sequence hoặc event ID trong khóa. Không tự dùng khóa này khi hợp đồng yêu cầu gửi lặp hợp lệ.

Quy trình:

1. Trong transaction SQL, cập nhật trạng thái đơn và ghi outbox record.
2. Worker claim các bản ghi PENDING theo cơ chế atomic/locking phù hợp.
3. Render email, gọi SMTP với timeout hữu hạn.
4. Khi SMTP chấp nhận, lưu `SMTP_ACCEPTED` cùng timestamp/attempt metadata.
5. Khi lỗi tạm thời, tăng attempt count và đặt `next_attempt_at`.
6. Khi lỗi vĩnh viễn/hết retry, chuyển trạng thái xử lý thủ công hoặc dead-letter.
7. Nếu có delivery webhook, cập nhật `DELIVERED`/`BOUNCED` bằng event có xác thực và idempotency.

### 10.2. Exactly-once email có thực tế không?

Với SMTP, khi mất kết nối sau khi gửi nhưng trước khi ứng dụng ghi nhận thành công, worker **không chắc relay đã nhận hay chưa**. Nếu retry, có thể tạo email thứ hai. Do đó khó bảo đảm exactly-once end-to-end chỉ bằng `JavaMailSender` và unique constraint trong DB.

Cần phân biệt:

- **At-least-once attempt:** có thể thử gửi lại để giảm mất thông báo, chấp nhận nguy cơ duplicate.
- **At-most-once attempt:** tránh lặp nhưng có thể mất thông báo khi lỗi không xác định.
- **Exactly-once business intent:** ghi một ý định thông báo duy nhất trong outbox, nhưng gửi SMTP vẫn có thể trùng.
- **Provider idempotency:** nếu sử dụng API có hỗ trợ idempotency key, có thể tăng mức bảo đảm; SMTP thông thường không có một idempotency contract tương đương.

Không dùng `Message-ID` hay traceId thay thế một hệ thống dedupe có tính nguyên tử. Chọn chiến lược theo tầm quan trọng của email; ví dụ email xác nhận đơn có thể chịu được một mức duplicate, nhưng email chứa mã kích hoạt/đường link hành động cần kiểm soát nghiêm ngặt hiệu lực token.

## 11. Gửi bất đồng bộ và giới hạn tải

Không nên để HTTP controller chờ SMTP nếu lời gọi mail không nằm trong hợp đồng response và có thể mất nhiều giây. Các lựa chọn:

| Cách gửi | Ưu điểm | Rủi ro |
| --- | --- | --- |
| Đồng bộ ngay trong HTTP request | Đơn giản, biết lỗi SMTP ngay | Latency cao, timeout, coupling |
| `@Async`/executor | Trả lời HTTP nhanh hơn | Nếu chỉ giữ trong RAM, có thể mất việc khi crash |
| Spring Integration mail adapter hoặc flow | Tách nguồn, channel và bước xử lý | Channel nội bộ không tự có durability |
| Broker + email consumer | Buffer và retry/redelivery | Consumer cần idempotency, DLQ, visibility |
| SQL transactional outbox + worker | Ý định gửi được commit cùng nghiệp vụ | Cần claim, retry, monitoring |

Dù chọn cách nào, giới hạn:

- Thread pool/concurrency gửi SMTP.
- Số lượng mail mỗi phút theo quota provider.
- Kích thước body/attachment và số người nhận.
- Retry attempts và tổng thời gian retry.
- Tốc độ xử lý lại sau outage để tránh “thác lũ” email.
- Per-tenant quota và quyền gửi thay mặt người dùng.

Một hàng đợi RAM không tự đảm bảo message còn sau restart; nếu nghiệp vụ cần giao nhận đáng tin cậy, chọn broker bền vững hoặc SQL outbox.

### 11.1. Không tạo nhiều JavaMailSender chỉ để gửi song song

Một `JavaMailSender` được cấu hình ở Spring context có thể được nhiều request dùng; dữ liệu **MimeMessage/SimpleMailMessage phải được tạo riêng cho từng lần gửi**. Không chia sẻ một MimeMessage mutable cho nhiều thread.

SMTP provider có quota và connection policies riêng. Tăng thread pool không giúp nếu provider hạn chế throughput; thậm chí có thể kích hoạt lỗi 429/rate-limit tương đương hoặc khóa tài khoản.

## 12. Bảo mật email và dữ liệu cá nhân

Email chứa dữ liệu nhạy cảm và được chuyển qua nhiều server. Vì vậy:

- **Credential:** lưu `SMTP_PASSWORD` và API key trong secret manager, không ghi logs, stacktrace đầy đủ hoặc repository.
- **TLS:** bắt buộc phiên mã hóa phù hợp và xác thực certificate/hostname.
- **From identity:** dùng địa chỉ đã được provider xác thực; cấu hình SPF, DKIM, DMARC theo domain và hệ thống mail vận hành.
- **Recipients:** kiểm tra định dạng và quyền nhận thông tin; tránh lộ người nhận qua CC khi đáng ra phải BCC hoặc gửi riêng.
- **Attachment:** kiểm soát file type/size, quét mã độc và quyền truy cập; tránh đường dẫn hệ thống hoặc thông tin bí mật trong tên tệp.
- **HTML:** escape dữ liệu động, giới hạn template syntax, chống lừa đảo qua link.
- **Logs/traces:** không ghi raw email address nếu không cần; dùng hash/redaction hoặc audit store có kiểm soát.
- **Quyền truy cập:** không cung cấp API gửi email tùy ý đến địa chỉ người dùng nhập nếu thiếu kiểm soát abuse, quota và authorization.
- **Unsubscribe/consent:** email marketing có các nghĩa vụ quản lý opt-in/opt-out theo pháp luật và chính sách provider; không đánh đồng với email giao dịch.

SMTP không phải cơ chế bí mật đầu-cuối mặc định. STARTTLS bảo vệ các hop có hỗ trợ nhưng không đảm bảo chỉ người nhận giải mã được nội dung email. Nếu gửi dữ liệu có yêu cầu bảo mật cao, cân nhắc gửi **thông báo không chứa dữ liệu nhạy cảm** kèm đường dẫn vào portal được bảo vệ.

## 13. Kiểm thử SimpleMailMessage không gửi email thật

Để kiểm tra logic tạo thư, có thể mock `JavaMailSender` và bắt đối tượng gửi:

~~~java
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

class PlainTextNotificationServiceTest {

    @Test
    void sendsPlainTextConfirmation() {
        JavaMailSender sender = mock(JavaMailSender.class);
        PlainTextNotificationService service =
                new PlainTextNotificationService(sender);

        service.sendOrderReceived(
                "customer@example.org", "ORD-42");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender).send(captor.capture());

        SimpleMailMessage sent = captor.getValue();
        assertEquals(
                "customer@example.org",
                sent.getTo()[0]);
        assertEquals(
                "Xác nhận tiếp nhận đơn hàng",
                sent.getSubject());
    }
}
~~~

Test này không mở kết nối mạng. Nó kiểm tra `to` và subject, có thể mở rộng để assert from/text/CC/BCC và việc **mỗi lần gọi tạo object riêng**. Mockito có trong Spring Boot test starter theo cấu hình thông thường; cần test dependencies phù hợp.

### 13.1. Test MimeMessageHelper mà không có SMTP thật

`JavaMailSender.createMimeMessage()` thường tạo `MimeMessage` dựa trên một Jakarta Mail `Session`. Trong unit test, có thể trả về message in-memory và bắt message được gửi:

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeMessage;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.mail.javamail.JavaMailSender;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.*;

class RichNotificationServiceTest {

    @Test
    void createsMimeMessageWithRecipientAndSubject()
            throws Exception {

        JavaMailSender sender = mock(JavaMailSender.class);
        MimeMessage mimeMessage =
                new MimeMessage(Session.getInstance(
                        new Properties()));

        when(sender.createMimeMessage()).thenReturn(mimeMessage);

        RichNotificationService service =
                new RichNotificationService(sender);

        service.sendOrderConfirmed(
                "customer@example.org", "ORD-42");

        verify(sender).send(mimeMessage);

        assertEquals(
                "customer@example.org",
                ((InternetAddress)
                        mimeMessage.getRecipients(
                                jakarta.mail.Message.RecipientType.TO)[0])
                        .getAddress());
        assertEquals(
                "Đơn hàng đã được xác nhận",
                mimeMessage.getSubject());
    }
}
~~~

Có thể mở rộng parse MIME structure để kiểm tra multipart/alternative, text/html và attachment content type/name/bytes. Test này vẫn **chưa kiểm tra SMTP authentication, TLS, encoding qua wire, quota và delivery event**.

### 13.2. Integration test với SMTP server giả

Dùng **GreenMail, Wiser/SubEthaSMTP hoặc SMTP capture server** có thể chạy trong test context, với cổng riêng và không chuyển tiếp thư ra ngoài Internet.

Quy trình:

1. Khởi động SMTP test server trên port động/riêng.
2. Cấp `spring.mail.host` và `spring.mail.port` tới server test.
3. Gọi service để gửi plain text và MIME.
4. Lấy thông điệp server đã nhận, parse subject, recipients, body parts và attachments.
5. Giả lập 4xx/5xx, timeout hoặc authentication failure để kiểm tra retry/error classification.
6. Dừng server sau test để tránh rò tài nguyên hoặc sử dụng nhầm SMTP production.

Nếu muốn thử hành vi một provider thật, cần môi trường sandbox/test account và explicit authorization; không gửi email tự động tới người dùng thật từ test suite.

### 13.3. Các contract tests cần có

| Tình huống | Điều cần xác minh |
| --- | --- |
| Plain text | Đúng from/to/subject/text, UTF-8 |
| HTML alternative | Có cả text/plain và text/html |
| Attachment | Đúng filename/content-type/bytes, không vượt quota |
| Inline image | Content-ID và `cid:` khớp, tài nguyên tồn tại |
| Email sai định dạng | Bị từ chối có nguyên nhân, không gửi |
| SMTP timeout | Retry có giới hạn hoặc chuyển outbox trạng thái phù hợp |
| SMTP auth failure | Không retry liên tục, có alert |
| Broker redelivery | Không tạo thêm ý định thông báo trùng |
| SQL rollback | Outbox/email intent không commit nếu đơn hàng rollback |
| SMTP accepted nhưng worker crash | Khi replay, xử lý nguy cơ gửi trùng theo chính sách |
| Hai tenant | Không gửi sai nội dung hoặc địa chỉ |
| Bounce/delivery webhook | Cập nhật trạng thái có xác thực và idempotency |

## 14. Quan sát luồng gửi mail

Một ứng dụng gửi email nên đo **tác động ở các ranh giới khác nhau**:

| Metric hoặc sự kiện | Ý nghĩa |
| --- | --- |
| Notification intent created | Nghiệp vụ đã quyết định cần gửi email |
| Outbox pending / oldest age | Đang tồn đọng bao nhiêu và bao lâu |
| SMTP send attempts | Mỗi lần thử gửi |
| SMTP accepted count | Số lượt relay xác nhận nhận trách nhiệm |
| SMTP errors by class | Auth/TLS/network/timeout/recipient |
| Retry and dead-letter count | Luồng phục hồi có hoạt động không |
| Delivery/bounce count (nếu có) | Kết quả sau khi SMTP chấp nhận |
| End-to-end notification latency | Từ ý định gửi đến SMTP accept/delivery theo hợp đồng |

Với Micrometer Observation, có thể instrument một lần gọi SMTP đồng bộ:

~~~java
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

public void sendObserved(
        JavaMailSender sender,
        ObservationRegistry registry,
        SimpleMailMessage message) {

    Observation.createNotStarted(
                    "integration.email.smtp.send", registry)
            .lowCardinalityKeyValue(
                    "template", "order-confirmation")
            .lowCardinalityKeyValue(
                    "transport", "smtp")
            .observe(() -> sender.send(message));
}
~~~

Quan sát này đo **thời gian lời gọi `send`**, không phải thời gian email đến hộp thư. Khi gửi lỗi, `observe(...)` giúp ghi exception theo lifecycle phù hợp nếu handler được cấu hình. Nếu có callback delivery, cần observation/metric riêng cho bước đó.

Các tag phù hợp gồm `template`, `transport`, `outcome` với tập giá trị hữu hạn. **Không đặt email người nhận, message-id, orderId hay notificationId vào metric label**; chúng có cardinality cao và/hoặc chứa dữ liệu cá nhân. Các định danh này có thể được lưu ở audit store có kiểm soát để đối soát từng sự kiện.

### 14.1. Giám sát khả năng gửi và bảo trì credential

Ngoài metrics của ứng dụng, cần theo dõi:

- Tỷ lệ bounce, complaint và reputation theo domain gửi khi provider hỗ trợ.
- Quota, rate limit và sự kiện khóa/tạm dừng SMTP account.
- Ngày hết hạn certificate, thay đổi endpoint và việc rotate credentials.
- SPF/DKIM/DMARC alignment theo cấu hình vận hành.
- Kích thước mail và số tệp đính kèm trung bình.
- Tỷ lệ outbox backlog tăng khi provider bị outage.

Một service có `health=UP` không đủ chứng minh email đã deliver. Nếu health indicator thử kết nối SMTP và provider bị outage, cần quyết định đó có ảnh hưởng **readiness của toàn ứng dụng** hay chỉ khả năng xử lý thông báo, để tránh cascade failure không cần thiết.

## 15. Các lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Không inject được `JavaMailSender` | Thiếu starter/cấu hình host hoặc autoconfig bị loại trừ | Kiểm tra dependency và `spring.mail.*` |
| SMTP auth failed | Username/password hoặc chính sách authentication sai | Kiểm tra secret, account, TLS, không log password |
| Timeout ở production | Thiếu connect/read/write timeout hoặc SMTP outage | Đặt timeout hữu hạn và kiểm tra mạng/provider |
| Port 465 không kết nối | Dùng STARTTLS trong khi provider yêu cầu implicit TLS | Cấu hình `mail.smtp.ssl.enable` theo cổng |
| Nội dung tiếng Việt lỗi dấu | Charset không phải UTF-8 | `spring.mail.default-encoding` và MimeMessageHelper charset |
| HTML hiển thị nguyên thẻ | Dùng `SimpleMailMessage` hoặc setText không bật HTML | Chọn MimeMessageHelper và HTML alternative |
| Email không thấy ảnh | CID sai, addInline trước setText hoặc mail client chặn | Kiểm tra MIME structure, resource và alt text |
| Attachment rỗng hoặc lỗi | Resource stream không đọc lại được hoặc bị xóa trước gửi | Dùng resource hợp lệ và kiểm tra lifecycle |
| Mail quá lớn | Attachment vượt giới hạn SMTP provider | Đặt quota hoặc gửi link an toàn |
| send() trả thành công nhưng không nhận mail | Relay chỉ accepted, thư bounce/spam/blocked sau đó | Theo dõi delivery events và provider logs |
| Duplicate email khi retry | Không có outbox/idempotency hoặc SMTP outcome không xác định | Định danh ý định gửi, giới hạn retry, đối soát |
| Gửi email dù SQL rollback | SMTP gọi trong transaction chưa commit | Transactional outbox/scheduling after commit |
| API HTTP chậm vì gửi mail | Gửi trực tiếp trên request thread | Outbox + async worker/broker |
| Không có metrics | Chưa instrument transport/worker hoặc thiếu registry | Observation/Actuator và dashboard |
| Rò danh sách người nhận | Dùng CC thay vì gửi riêng hoặc BCC | Kiểm tra privacy và recipient policy |

## 16. Checklist trước khi triển khai

- [ ] Đã cấu hình `spring.mail.host/port/username/password` qua nguồn an toàn.
- [ ] Chọn đúng STARTTLS hay implicit TLS, kiểm chứng certificate/hostname.
- [ ] Có connection/read/write timeout và giới hạn concurrency/quota.
- [ ] Chọn `SimpleMailMessage` cho plain text, `MimeMessageHelper` cho HTML/multipart/attachment.
- [ ] Dùng UTF-8 và cung cấp plain-text alternative cho email HTML.
- [ ] Template engine escape dữ liệu động; không chèn HTML không tin cậy.
- [ ] Attachment được kiểm soát kích thước, loại, quyền và vòng đời resource.
- [ ] Địa chỉ người gửi/nhận được xác thực, không lộ recipient giữa các tenant.
- [ ] Không gửi SMTP bên trong một transaction SQL rồi giả định có rollback chung.
- [ ] Nếu cần delivery bền vững, có notification outbox, worker, retry/DLQ và idempotency policy.
- [ ] Phân biệt SMTP accepted với delivered/bounced/read.
- [ ] Có unit test cho plain-text/MIME và integration test với SMTP capture server.
- [ ] Có metric attempt/accepted/delivery, backlog, failures; không gắn email/ID vào metric tags.
- [ ] Có quy trình rotate secret, theo dõi reputation/bounce và khôi phục khi provider outage.

**Ghi nhớ:** `SimpleMailMessage` phù hợp thông báo văn bản đơn giản; `MimeMessageHelper` giúp xây dựng email MIME với HTML, text alternative, attachment và inline resource. Cả hai được gửi qua `JavaMailSender`. Khả năng gửi email đáng tin cậy không chỉ dựa vào API tạo thư mà còn vào **cấu hình SMTP, bảo mật, ranh giới transaction, outbox/idempotency, retry, kiểm thử và khả năng quan sát delivery**.

## Tài liệu tham khảo

- [Spring Boot — Sending Email](https://docs.spring.io/spring-boot/reference/io/email.html): auto-configuration, `spring.mail.*`, JavaMailSender và timeout.
- [Spring Framework — Email](https://docs.spring.io/spring-framework/reference/integration/email.html): SimpleMailMessage, MimeMessageHelper, HTML/attachment.
- [Spring Framework API — SimpleMailMessage](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/mail/SimpleMailMessage.html): các trường và khả năng email text.
- [Spring Framework API — MimeMessageHelper](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/mail/javamail/MimeMessageHelper.html): constructor, multipart modes, `setText`, `addAttachment`, `addInline`.
- [Spring Framework API — JavaMailSender](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/mail/javamail/JavaMailSender.html): gửi SimpleMailMessage/MimeMessage.
- [Jakarta Mail — SMTP Transport](https://eclipse-ee4j.github.io/angus-mail/docs/SMTP-Transport.html): SMTP transport properties, TLS và timeouts.
