# Khi SimpleMailMessage phù hợp trong Spring Framework Mail

Trong Spring Framework Mail, không phải email nào cũng cần HTML, hình ảnh, tệp đính kèm hay cấu trúc MIME nhiều phần. Một email thông báo ngắn chỉ có tiêu đề, người gửi, người nhận và vài dòng văn bản có thể được xây dựng bằng lớp `SimpleMailMessage`. Lớp này là lựa chọn phù hợp khi yêu cầu nội dung thật sự đơn giản, còn việc kết nối SMTP và gửi email được giao cho `MailSender` hoặc `JavaMailSender`.

Ví dụ, ứng dụng có thể cần gửi:

- Mã xác minh tài khoản cùng hướng dẫn ngắn.
- Thông báo đã tiếp nhận yêu cầu hỗ trợ.
- Cảnh báo tác vụ nền bị lỗi cho nhóm vận hành.
- Nhắc lịch hoặc thông báo trạng thái đơn hàng với vài dòng văn bản.
- Một đường dẫn xác nhận và lời giải thích rõ ràng bằng văn bản thuần.

Tuy nhiên, nếu email cần định dạng HTML, logo xuất hiện bên trong nội dung, file PDF đính kèm hoặc cả phiên bản plain text và HTML, nên sử dụng `MimeMessage` với `MimeMessageHelper`. Hiểu đúng ranh giới này giúp lựa chọn API có độ phức tạp vừa đủ và tránh các lỗi như gửi nguyên thẻ HTML tới người đọc.

## 1. SimpleMailMessage đại diện cho điều gì?

`SimpleMailMessage` là lớp thuộc package `org.springframework.mail`. Nó mô tả các thuộc tính cơ bản của một email **văn bản thuần**:

| Thành phần | API tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Người gửi | `setFrom(String)` | Địa chỉ trong trường `From` của thư |
| Người nhận chính | `setTo(String...)` | Danh sách người nhận `To` |
| Người nhận bản sao | `setCc(String...)` | Danh sách `Cc` |
| Người nhận bản sao kín | `setBcc(String...)` | Danh sách `Bcc` |
| Địa chỉ nhận trả lời | `setReplyTo(String)` | Trường `Reply-To` |
| Tiêu đề | `setSubject(String)` | Chủ đề thư |
| Nội dung | `setText(String)` | Phần thân văn bản thuần |
| Ngày gửi | `setSentDate(Date)` | Thời gian được khai báo trên thư khi có nhu cầu |

Đây là một đối tượng dữ liệu có thể thay đổi được (mutable). Nó **không tự kết nối** đến SMTP server, không tự gửi và không mở hộp thư của người nhận. Để gửi, ứng dụng chuyển object cho một thành phần sender.

```text
Service nghiệp vụ
       |
       | tạo SimpleMailMessage mới
       | setFrom, setTo, setSubject, setText
       v
SimpleMailMessage
       |
       | JavaMailSender.send(message)
       v
JavaMailSender / JavaMailSenderImpl
       |
       | Chuyển thông điệp sang dạng có thể truyền bằng SMTP
       | Sử dụng Jakarta Mail để làm việc với SMTP transport
       v
SMTP relay / Email Service Provider
       |
       v
Hệ thống thư phía nhận
```

`SimpleMailMessage` không phải một lớp “email HTML phiên bản nhẹ”. Nó được thiết kế cho trường hợp nội dung chỉ là text. Việc implementation ở tầng dưới có thể tạo một `MimeMessage` để truyền qua Jakarta Mail **không làm `SimpleMailMessage` trở thành API soạn thư MIME đầy đủ**.

### Mối quan hệ với MailSender và JavaMailSender

- `MailSender` là giao diện Spring hỗ trợ gửi `SimpleMailMessage`.
- `JavaMailSender` là giao diện mở rộng khả năng gửi email MIME, đồng thời vẫn hỗ trợ gửi `SimpleMailMessage`.
- `JavaMailSenderImpl` là một implementation SMTP phổ biến của `JavaMailSender`.
- `MimeMessageHelper` hỗ trợ xây dựng `MimeMessage` với HTML, multipart, attachment và nhiều header/kiểu nội dung hơn.

Trong ứng dụng Spring Boot, thường chỉ cần inject `JavaMailSender` vào service để có cả lựa chọn đơn giản lẫn MIME. Một dự án chỉ sử dụng plain text về mặt API có thể phụ thuộc vào `MailSender` nếu không cần những khả năng mở rộng của `JavaMailSender`.

## 2. Trường hợp nên chọn SimpleMailMessage

Một tiêu chí dễ áp dụng là: **người nhận có thể hiểu và thực hiện mọi hành động cần thiết chỉ bằng vài đoạn văn bản, không cần bố cục phong phú hoặc tệp đi kèm**.

| Tình huống | SimpleMailMessage có phù hợp? | Lý do |
| --- | --- | --- |
| OTP hoặc mã xác minh ngắn | Có | Nội dung một vài dòng, ít yêu cầu trình bày |
| Xác nhận đã tiếp nhận đơn hàng | Có, nếu chỉ chứa thông tin ngắn | Mã đơn, trạng thái và đường dẫn xem chi tiết đủ bằng text |
| Cảnh báo job lỗi đến nhóm kỹ thuật | Có | Log tóm tắt, mã lỗi, liên kết dashboard rõ ràng |
| Nhắc lịch đơn giản | Có | Thời gian, địa điểm và hướng dẫn có thể đọc bằng text |
| Email giới thiệu nhiều cột và banner | Không phù hợp | Cần HTML/CSS và có thể có ảnh nội tuyến |
| Hóa đơn dưới dạng PDF | Không phù hợp | Cần attachment qua MIME |
| Email có bản HTML và bản plain text dự phòng | Không phù hợp với riêng SimpleMailMessage | Cần `multipart/alternative` |
| Thư có logo hiển thị trong body | Không phù hợp | Cần tài nguyên inline với Content-ID |
| Calendar invite dạng tệp `.ics` | Không phù hợp nếu gửi dưới dạng attachment/calendar MIME | Cần nội dung MIME thích hợp |
| Email có custom MIME headers, priority hoặc DSN chuyên biệt | Thường không phù hợp | Cần kiểm soát `MimeMessage` hoặc cơ chế provider |
| Email cần theo dõi mở/click qua ESP | Có thể dùng nếu chỉ cần body text; tracking phụ thuộc ESP | Bản thân SimpleMailMessage không theo dõi các sự kiện đó |

**Độ dài không phải tiêu chí duy nhất.** Một email rất ngắn nhưng bắt buộc có ảnh hoặc file vẫn cần MIME. Ngược lại, một email văn bản tương đối dài, chỉ gồm đoạn văn và liên kết, vẫn có thể dùng `SimpleMailMessage` nếu trải nghiệm đọc phù hợp.

### Ví dụ 1: Thông báo tác vụ nền

```text
Subject: [Scheduler] Sao lưu hoàn thành

Tác vụ: backup-daily
Môi trường: production
Kết quả: thành công
Thời điểm: 2026-11-12 02:00 UTC

Chi tiết: https://ops.example.com/jobs/backup-daily
```

Thư này không cần HTML. Các thông tin quan trọng được trình bày thành các dòng dễ đọc và có liên kết đầy đủ.

### Ví dụ 2: Xác nhận yêu cầu hỗ trợ

```text
Subject: Đã tiếp nhận yêu cầu #SUP-1042

Xin chào,

Chúng tôi đã nhận được yêu cầu hỗ trợ của bạn.

Mã yêu cầu: SUP-1042
Theo dõi: https://example.com/support/requests

Trân trọng,
Bộ phận hỗ trợ
```

Nội dung này có thể đọc được trên nhiều email client và các công cụ hỗ trợ tiếp cận mà không cần CSS hay hình ảnh.

## 3. Cấu hình Spring Boot trước khi gửi

Trong ứng dụng Spring Boot sử dụng Maven và dependency management của Boot, thêm starter:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Nếu dùng Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-mail'
```

Khai báo SMTP trong `src/main/resources/application.properties`:

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

Các giá trị host và port chỉ minh họa; phải thay bằng SMTP endpoint mà tổ chức hoặc nhà cung cấp cung cấp. Port 587 thường dùng STARTTLS, nhưng một số hệ thống dùng port 465 với implicit TLS hoặc relay nội bộ có chính sách khác.

Trong ví dụ:

- `spring.mail.username` và `spring.mail.password` được lấy từ môi trường, không ghi mật khẩu thật trong repository.
- `spring.mail.default-encoding=UTF-8` hỗ trợ biểu diễn nội dung có dấu tiếng Việt đúng cách.
- `auth` và `starttls.*` phải tương thích với chính sách xác thực/mã hóa của SMTP server.
- Ba timeout có đơn vị mili giây, giới hạn kết nối/đọc/ghi riêng biệt để giảm nguy cơ tác vụ bị treo lâu.
- `JavaMailSenderImpl` sẽ được Spring Boot tự cấu hình khi dependency và các điều kiện cấu hình được đáp ứng; thông thường không cần tự tạo sender mới trong từng service.

Đặt timeout giúp xử lý chậm mạng, nhưng tổng `send()` vẫn có thể lâu hơn từng giá trị timeout vì SMTP gồm nhiều thao tác tuần tự. Việc gửi thư cũng phụ thuộc đường mạng, DNS, TLS, xác thực, quota của nhà cung cấp và trạng thái server.

### Cấu hình không gửi thư thử khi mới chạy ứng dụng

Với Spring Boot, `spring.mail.test-connection` là thuộc tính độc lập:

```properties
spring.mail.test-connection=false
```

Giá trị `false` nghĩa là không bắt buộc thử kết nối SMTP trong startup theo tính năng này. Nếu bật `true`, khi auto-configuration phù hợp, Boot có thể kiểm tra transport lúc khởi động và thất bại nếu SMTP không kết nối được. **Nó không gửi `SimpleMailMessage` thử nghiệm** và không chứng minh email đã tới inbox.

## 4. Ví dụ gửi email đơn giản bằng JavaMailSender

Dịch vụ dưới đây gửi một thông báo tiếp nhận yêu cầu:

```java
package example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class SupportNotificationService {

    private final JavaMailSender mailSender;

    public SupportNotificationService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendRequestReceived(
            String recipient,
            String requestCode) {

        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("support@example.com");
        message.setTo(recipient);
        message.setReplyTo("helpdesk@example.com");
        message.setSubject("Đã tiếp nhận yêu cầu " + requestCode);

        String body = """
                Xin chào,

                Chúng tôi đã tiếp nhận yêu cầu hỗ trợ của bạn.

                Mã yêu cầu: %s
                Theo dõi: https://example.com/support/requests

                Trân trọng,
                Bộ phận hỗ trợ
                """.formatted(requestCode);

        message.setText(body);
        mailSender.send(message);
    }
}
```

Ở đây:

1. Spring inject một sender dùng chung vào service thông qua constructor.
2. Mỗi lần gọi `sendRequestReceived(...)` tạo **một `SimpleMailMessage` mới**.
3. `setFrom(...)` xác định địa chỉ gửi hiển thị; `setReplyTo(...)` xác định nơi nhận phản hồi.
4. `setTo(...)` xác định người nhận.
5. `setSubject(...)` và `setText(...)` xây dựng tiêu đề và phần thân.
6. `mailSender.send(message)` giao quá trình gửi cho SMTP transport đã được cấu hình.

Việc `send` trả về thành công không có nghĩa thư đã được giao đến inbox hoặc người dùng đã đọc. Nó chỉ phản ánh kết quả submission tới SMTP relay ở phạm vi mà ứng dụng tương tác.

### Dùng MailSender khi chỉ cần simple mail

Nếu mọi phương thức của service chỉ gửi `SimpleMailMessage`, có thể phụ thuộc vào interface gọn hơn:

```java
package example.mail;

import org.springframework.mail.MailSender;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.stereotype.Service;

@Service
public class AlertMailService {

    private final MailSender mailSender;

    public AlertMailService(MailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendAlert(String recipient, String description) {
        SimpleMailMessage mail = new SimpleMailMessage();
        mail.setFrom("alerts@example.com");
        mail.setTo(recipient);
        mail.setSubject("Cảnh báo hệ thống");
        mail.setText(description);

        mailSender.send(mail);
    }
}
```

`JavaMailSender` mở rộng `MailSender`, vì vậy bean `JavaMailSenderImpl` thông thường cũng có thể thỏa mãn dependency kiểu `MailSender`. Tuy nhiên, nếu ứng dụng có nhiều bean cùng đáp ứng kiểu đó, cần xác định rõ bean bằng `@Qualifier` hoặc cấu hình phù hợp.

## 5. Cách soạn plain text để người nhận dễ đọc

Vì `SimpleMailMessage` không cung cấp bố cục HTML, chất lượng của nội dung phụ thuộc cách trình bày bằng văn bản. Một email text tốt nên có:

- **Mục đích rõ ngay từ tiêu đề**: “Đã tiếp nhận yêu cầu #SUP-1042” dễ hiểu hơn “Thông báo”.
- **Lời mở đầu ngắn**: người nhận biết email liên quan đến hành động nào.
- **Thông tin chính trong một vài dòng**: mã đơn, thời gian, trạng thái, mức độ ưu tiên.
- **Khoảng trắng và xuống dòng hợp lý**: ngắt đoạn bằng dòng trống, tránh một khối dài.
- **Liên kết đầy đủ**: ghi cả `https://` và hostname; đừng dùng đường dẫn tương đối.
- **Hành động rõ ràng**: “Mở trang để xác nhận”, “Liên hệ hỗ trợ nếu không thực hiện yêu cầu”.
- **Chữ ký/nguồn gửi**: để người nhận biết đây là thông báo từ hệ thống nào.

Ví dụ tương phản:

**Khó đọc:**

```text
Da co don hang moi. Ma: ORD-1023 trang thai: confirmed.
Xem ngay va kiem tra lai neu can.
```

**Dễ đọc hơn:**

```text
Tiêu đề: Xác nhận đơn hàng ORD-1023

Xin chào,

Đơn hàng của bạn đã được tiếp nhận.

Mã đơn hàng: ORD-1023
Trạng thái: Đã xác nhận

Xem chi tiết:
https://example.com/orders

Nếu không thực hiện giao dịch này, vui lòng liên hệ hỗ trợ.

Cảm ơn bạn.
```

Lưu ý: `setSubject(...)` là tiêu đề riêng, không cần đưa dòng “Tiêu đề:” vào `setText(...)`. Ví dụ chỉ minh họa cấu trúc khi đọc.

### Newline và ký tự xuống dòng

Trong Java, có thể dùng `\n` hoặc text block để tạo đoạn văn:

```java
String text =
        "Xin chào,\n\n"
        + "Yêu cầu của bạn đã được tiếp nhận.\n"
        + "Mã: SUP-1042\n\n"
        + "Trân trọng,\n"
        + "Bộ phận hỗ trợ";

message.setText(text);
```

`MimeMessage` được sender dựng ở tầng dưới sẽ xử lý cách truyền nội dung lên SMTP. Khi xây body, không cần tự thêm các dấu phân cách MIME hoặc header `Content-Type` vào chuỗi văn bản.

Các email client có thể tự nhận diện URL để biến thành link có thể bấm, nhưng **không có bảo đảm mọi client đều làm giống nhau**. Với tác vụ thiết yếu, nên đặt URL đầy đủ và một lời hướng dẫn dễ hiểu; người dùng vẫn có thể sao chép liên kết nếu client không tự biến thành link.

### Tiếng Việt và encoding

`SimpleMailMessage` có thể chứa chuỗi Java Unicode:

```java
message.setSubject("Mã xác nhận tài khoản");
message.setText("Xin chào,\n\nMã của bạn là: 284193.");
```

Việc mã hóa để truyền qua SMTP được implementation Jakarta Mail xử lý. Trong dự án Spring Boot, cấu hình `spring.mail.default-encoding=UTF-8` giúp dùng một encoding nhất quán cho nội dung và header mà sender tạo. Không nên tự thay dấu tiếng Việt bằng escape HTML như `&aacute;` trong phần thân plain text: các entity HTML có thể được hiển thị nguyên văn.

## 6. Gửi cho nhiều người nhận, Cc và Bcc

`SimpleMailMessage` hỗ trợ nhiều địa chỉ nhận:

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("alerts@example.com");
mail.setTo("oncall@example.com", "operations@example.com");
mail.setCc("teamlead@example.com");
mail.setBcc("audit@example.com");
mail.setSubject("Cảnh báo sự cố");
mail.setText("Tác vụ đồng bộ dữ liệu đã thất bại.");

mailSender.send(mail);
```

Về mặt chức năng:

| Trường | Người nhận thường thấy gì? |
| --- | --- |
| `To` | Danh sách người nhận chính |
| `Cc` | Danh sách người nhận bản sao |
| `Bcc` | Người nhận ẩn thường không được công khai trong bản giao cho các người nhận khác |
| `Reply-To` | Địa chỉ mà email client sử dụng khi người dùng chọn Reply |

Không nên đặt hàng trăm địa chỉ người dùng độc lập trong một `To` hoặc `Cc`: các địa chỉ có thể bị lộ cho nhau. Với email cần cá nhân hóa, bảo vệ quyền riêng tư, tracking theo người nhận hoặc xử lý bounce riêng, nên tạo **một delivery record và một thông điệp cho từng người nhận**, hoặc sử dụng tính năng gửi hàng loạt an toàn của nhà cung cấp.

`SimpleMailMessage` hỗ trợ nhiều người nhận nhưng **không tự cung cấp hệ thống bulk mailing, quản lý quota, suppression list hoặc theo dõi trạng thái từng recipient**. Những yêu cầu này thuộc tầng ứng dụng và/hoặc Email Service Provider.

## 7. Vì sao không gửi HTML bằng SimpleMailMessage?

Giả sử service thực hiện:

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setTo("user@example.net");
mail.setSubject("Chào mừng");
mail.setText("<h1>Chào mừng!</h1><p>Tài khoản đã sẵn sàng.</p>");
mailSender.send(mail);
```

Người nhận có thể nhìn thấy chính các ký tự:

```text
<h1>Chào mừng!</h1><p>Tài khoản đã sẵn sàng.</p>
```

Nguyên nhân là `setText(...)` trong `SimpleMailMessage` định nghĩa **nội dung text**. Nó không có tham số `html=true` và không cho lập trình viên cấu hình `text/html` hoặc cấu trúc multipart một cách trực tiếp.

Khi thật sự cần HTML, hãy sử dụng:

```java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage mimeMessage = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("user@example.net");
helper.setSubject("Chào mừng");
helper.setText("<h1>Chào mừng!</h1><p>Tài khoản đã sẵn sàng.</p>", true);

mailSender.send(mimeMessage);
```

Trong overload `helper.setText(String, boolean)`, `true` có nghĩa là nội dung đầu vào là HTML. Nếu muốn cả plain text và HTML cùng một email, cần bật multipart:

```java
MimeMessage mimeMessage = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, true, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("user@example.net");
helper.setSubject("Chào mừng");
helper.setText(
    "Xin chào! Tài khoản của bạn đã sẵn sàng.",
    "<h1>Xin chào!</h1><p>Tài khoản của bạn đã sẵn sàng.</p>"
);

mailSender.send(mimeMessage);
```

Overload `setText(plain, html)` thêm hai phiên bản của cùng một nội dung theo cơ chế MIME phù hợp. `SimpleMailMessage` không cung cấp thao tác tương đương.

## 8. Không dùng SimpleMailMessage cho attachment hoặc hình nội tuyến

Một email có PDF hướng dẫn không chỉ là “text cộng thêm tên file”. Attachment cần cấu trúc MIME với `Content-Disposition`, `Content-Type` và dữ liệu nhị phân được mã hóa phù hợp. `SimpleMailMessage` không có phương thức `addAttachment(...)`.

Ví dụ dùng `MimeMessageHelper` để đính kèm PDF:

```java
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage mimeMessage = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, true, "UTF-8");

helper.setFrom("support@example.com");
helper.setTo("user@example.net");
helper.setSubject("Hướng dẫn sử dụng");
helper.setText("Bạn vui lòng xem file PDF đính kèm.", false);

helper.addAttachment(
    "huong-dan.pdf",
    new ClassPathResource("mail/huong-dan.pdf")
);

mailSender.send(mimeMessage);
```

Tệp `mail/huong-dan.pdf` trong ví dụ phải thực sự nằm trên classpath, chẳng hạn `src/main/resources/mail/huong-dan.pdf`. Muốn hiện ảnh trong HTML bằng `cid:logo`, cũng phải dùng `MimeMessageHelper#addInline(...)` với chế độ multipart phù hợp.

Do đó, khi yêu cầu thay đổi từ “gửi lời nhắc ngắn” sang “gửi lời nhắc có PDF”, có thể giữ nguyên bean `JavaMailSender` và nâng phần tạo **message** từ `SimpleMailMessage` sang `MimeMessage`. Không cần viết lại toàn bộ cấu hình kết nối SMTP.

## 9. SimpleMailMessage là mutable: tạo mới cho mỗi email

Một lỗi quan trọng trong ứng dụng có nhiều request là lưu `SimpleMailMessage` trong field của singleton service rồi thay các thuộc tính theo người nhận.

**Không nên:**

```java
@Service
public class UnsafeMailer {
    private final JavaMailSender mailSender;

    // Một đối tượng bị chia sẻ giữa nhiều request:
    private final SimpleMailMessage shared = new SimpleMailMessage();

    public UnsafeMailer(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void send(String recipient, String text) {
        shared.setTo(recipient);
        shared.setText(text);
        mailSender.send(shared);
    }
}
```

Nếu hai thread gọi `send(...)` đồng thời, giá trị `To` hoặc `Text` của thread này có thể bị thread kia thay đổi trước khi nội dung được gửi. Kết quả là email có nguy cơ được gửi sai người hoặc mang nhầm nội dung. Vấn đề tương tự xảy ra khi giữ `MimeMessage` dùng chung và thay nó trong các request.

**Nên tạo object mới cho mỗi lần gửi:**

```java
public void send(String recipient, String text) {
    SimpleMailMessage mail = new SimpleMailMessage();
    mail.setFrom("no-reply@example.com");
    mail.setTo(recipient);
    mail.setSubject("Thông báo");
    mail.setText(text);
    mailSender.send(mail);
}
```

Một bean `JavaMailSender` có thể được inject dùng chung giữa các service khi cấu hình sender được thiết lập và không bị thay đổi trong lúc gửi. Điều đó **không có nghĩa message nên được tái sử dụng giữa nhiều request**.

### Dùng message template bằng copy constructor

Nếu nhiều email có chung From/Reply-To hoặc tiêu đề mặc định, `SimpleMailMessage` có copy constructor để tạo bản sao:

```java
SimpleMailMessage template = new SimpleMailMessage();
template.setFrom("no-reply@example.com");
template.setReplyTo("support@example.com");
template.setSubject("Thông báo");

// Mỗi lần gửi tạo bản sao độc lập:
SimpleMailMessage message = new SimpleMailMessage(template);
message.setTo(recipient);
message.setText(body);

mailSender.send(message);
```

Điều kiện quan trọng: template gốc phải được tạo và cấu hình trước khi nhiều thread sử dụng, rồi được xem là **không thay đổi**. Chỉ sửa bản sao của từng lần gửi. Không nên đặt người nhận hoặc body của một request vào template dùng chung.

Với phần lớn service nhỏ, việc tạo mới `SimpleMailMessage` và đặt các trường cần thiết thường đủ gọn; template copy chỉ hữu ích khi thực sự có nhiều thuộc tính chung.

## 10. Địa chỉ From, Reply-To và SMTP account không phải một

`SimpleMailMessage` có `setFrom(...)` và `setReplyTo(...)`, nhưng hai trường này không chọn trực tiếp username/password để đăng nhập SMTP.

Ví dụ:

```java
message.setFrom("orders@shop.example.com");
message.setReplyTo("help@shop.example.com");
```

Trong khi cấu hình gửi có thể là:

```properties
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
```

- `From` là danh tính người gửi hiển thị trên thư.
- `Reply-To` là nơi email client gửi phản hồi.
- Username/password xác thực với SMTP provider.
- SMTP envelope sender (`MAIL FROM`) có thể được provider điều khiển riêng, phục vụ xử lý bounce và chính sách giao thư.

Một ESP có thể yêu cầu địa chỉ hoặc domain `From` đã xác minh, dù ứng dụng tạo message thành công. Nếu sender không được phép, provider có thể từ chối hoặc viết lại thông tin gửi. `SimpleMailMessage` không tự vượt qua các quy tắc này.

Ngoài ra, một email có thể được SMTP relay chấp nhận nhưng sau đó bị lọc spam hoặc bounce. Việc lựa chọn `SimpleMailMessage` thay cho `MimeMessage` không bảo đảm khả năng giao thư.

## 11. Mã hóa, đầu vào người dùng và an toàn nội dung

Dùng văn bản thuần giúp giảm độ phức tạp của HTML, nhưng vẫn cần xử lý đầu vào cẩn thận.

### Không tự dựng raw header

Các trường tiêu đề và địa chỉ nên được đặt qua setter:

```java
mail.setTo(recipient);
mail.setSubject("Xác nhận yêu cầu");
mail.setText(body);
```

Đừng tự ghép một raw email bằng chuỗi kiểu `"To: " + recipient + "\r\nSubject: ..."` rồi cố gửi trực tiếp. Đầu vào chứa CR/LF hoặc ký tự điều khiển có thể dẫn tới header injection nếu ứng dụng tự xây cú pháp header không an toàn.

Đối với dữ liệu do người dùng cung cấp:

- Kiểm tra địa chỉ người nhận theo quy tắc nghiệp vụ, giới hạn số người nhận và độ dài.
- Giới hạn độ dài `Subject` và tránh cho phép ký tự điều khiển không cần thiết.
- Tránh đưa toàn bộ thông tin cá nhân, nội dung hỗ trợ nhạy cảm hoặc secret vào tiêu đề/header vì chúng dễ xuất hiện trong log và công cụ vận chuyển.
- Không coi việc gửi plain text là một cách mã hóa end-to-end; SMTP/TLS bảo vệ một số chặng vận chuyển, không đồng nghĩa nội dung luôn được mã hóa tới thiết bị người nhận.
- Không đưa mật khẩu hay token dài hạn vào email. Với mã xác minh, phải có thời hạn, giới hạn số lần thử và logic xác nhận an toàn phía backend.

### Với mã xác thực, logic bảo mật nằm ngoài SimpleMailMessage

Ví dụ:

```java
public void sendOtp(String recipient, String otp) {
    SimpleMailMessage mail = new SimpleMailMessage();
    mail.setFrom("security@example.com");
    mail.setTo(recipient);
    mail.setSubject("Mã xác thực");
    mail.setText(
        "Mã của bạn là: " + otp
        + "\nMã chỉ có hiệu lực trong thời gian quy định."
    );
    mailSender.send(mail);
}
```

`SimpleMailMessage` chỉ đưa mã vào thông điệp. Nó không tự:

- Tạo OTP ngẫu nhiên đủ an toàn.
- Lưu hash/trạng thái mã.
- Kiểm tra hạn sử dụng.
- Giới hạn số lần xác minh.
- Khóa mã sau khi sử dụng.
- Bảo đảm người nhận đã nhận hoặc đọc email.

Những chức năng đó phải nằm trong lớp bảo mật và nghiệp vụ riêng. Không log OTP thô chỉ vì cần chẩn đoán quá trình gửi email.

## 12. Tách văn bản khỏi nghiệp vụ và hỗ trợ đa ngôn ngữ

Một service gửi mail đơn giản có thể bắt đầu bằng cách ghép chuỗi Java. Khi email có nhiều biến thể hoặc ngôn ngữ, nên tách nội dung ra thành template/resource.

Ví dụ một template plain text:

```text
Xin chào {name},

Chúng tôi đã nhận được yêu cầu {requestCode}.

Theo dõi tiến độ:
{requestUrl}

Trân trọng,
Nhóm hỗ trợ
```

Lớp renderer có thể nhận dữ liệu nghiệp vụ, đảm bảo nội dung được định dạng và trả về `String`. `SimpleMailMessage` chỉ nhận chuỗi kết quả bằng `setText(...)`. Không cần chuyển sang HTML chỉ vì ứng dụng sử dụng template.

Với Spring, `MessageSource` có thể cung cấp chuỗi theo locale, ví dụ:

```properties
# messages_vi.properties
mail.support.subject=Đã tiếp nhận yêu cầu {0}
mail.support.body=Xin chào {0},\n\nYêu cầu {1} đã được tiếp nhận.\n\nTrân trọng.
```

Ví dụ code lấy message theo ngôn ngữ:

```java
import java.util.Locale;
import org.springframework.context.MessageSource;

String subject = messageSource.getMessage(
    "mail.support.subject",
    new Object[] {requestCode},
    Locale.forLanguageTag("vi-VN")
);

String body = messageSource.getMessage(
    "mail.support.body",
    new Object[] {displayName, requestCode},
    Locale.forLanguageTag("vi-VN")
);

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("support@example.com");
mail.setTo(recipient);
mail.setSubject(subject);
mail.setText(body);
mailSender.send(mail);
```

Đây là ví dụ khi ứng dụng đã có `MessageSource` và các resource bundle tương ứng. Nội dung `.properties` cần đúng quy tắc escaping của resource bundle/message format; với template phức tạp hơn, có thể xây renderer riêng để tránh các vấn đề về placeholder hoặc ngôn ngữ.

### Khi nào nên đổi sang HTML vì yêu cầu trải nghiệm?

Plain text có thể hỗ trợ nhiều ngôn ngữ và template. Nhưng nếu email cần:

- Bảng hóa đơn nhiều cột có bố cục rõ.
- Nút CTA với định dạng nổi bật.
- Logo, hình ảnh nội tuyến hoặc hệ thống nhận diện thương hiệu.
- Hai phiên bản `text/plain` và `text/html` cho cùng nội dung.
- Tệp đính kèm hoặc nội dung lịch chuẩn MIME.

Lúc đó, lựa chọn `MimeMessage` là do **yêu cầu cấu trúc thư**, không phải vì số lượng biến trong template tăng lên.

## 13. Gửi nhiều SimpleMailMessage và lưu ý kết quả

`MailSender` và `JavaMailSender` hỗ trợ gửi một hoặc nhiều `SimpleMailMessage`:

```java
SimpleMailMessage first = new SimpleMailMessage();
first.setFrom("alerts@example.com");
first.setTo("alice@example.net");
first.setSubject("Thông báo A");
first.setText("Nội dung A");

SimpleMailMessage second = new SimpleMailMessage();
second.setFrom("alerts@example.com");
second.setTo("bob@example.net");
second.setSubject("Thông báo B");
second.setText("Nội dung B");

mailSender.send(first, second);
```

Gọi varargs như trên giúp chuyển nhiều message cho sender trong một lần gọi API; **không có nghĩa tất cả trở thành một email duy nhất** hoặc đảm bảo mọi người nhận sẽ thành công đồng thời. Nếu xảy ra lỗi, một số thông điệp có thể đã được SMTP server tiếp nhận trước khi lỗi xuất hiện.

Với hệ thống cần biết kết quả **theo từng delivery**, nên tạo delivery ID và ghi nhận attempt riêng cho mỗi người nhận hoặc mỗi message. Nếu dùng ESP có webhook, đối soát message ID/event riêng để biết deferred, bounced hoặc delivered.

Một lần `send` thành công thường chỉ chứng minh relay đã tiếp nhận lần submission tương ứng. `SimpleMailMessage` không có cơ chế built-in để biết email đã **opened** hoặc **clicked**. Các chỉ số này nếu có cần hạ tầng tracking/ESP, và bản thân tín hiệu open/click có giới hạn về độ tin cậy.

## 14. Xử lý lỗi và retry

Gửi SMTP là hoạt động I/O, có thể gặp lỗi mạng hoặc chính sách provider. Spring Mail cung cấp nhóm `MailException` để phản ánh các lỗi gửi email. Những kiểu hay gặp gồm:

| Loại vấn đề | Ví dụ | Hành động gợi ý |
| --- | --- | --- |
| Lỗi kết nối | Connection refused, connect timeout | Kiểm tra host/port/firewall, retry có giới hạn nếu là lỗi tạm thời |
| Lỗi đọc hoặc ghi | Read timeout khi chờ SMTP, write timeout khi truyền | Xác định giai đoạn gửi và khả năng provider đã nhận thư |
| Lỗi xác thực | Tài khoản hoặc ứng dụng không được phép đăng nhập | Sửa credentials/cơ chế xác thực; không retry vô hạn |
| Header/địa chỉ không hợp lệ | Giá trị `To` hoặc `From` bị từ chối | Kiểm tra dữ liệu đầu vào và sender domain |
| Policy nhà cung cấp | Rate limit, sender chưa xác minh, kích thước thư | Theo thông báo SMTP/ESP để chọn xử lý |
| Bounce sau submission | Máy chủ đích không giao được mail | Theo dõi event của ESP; đây không nhất thiết là lỗi trong `send` |

Ví dụ xử lý lỗi ở ranh giới service:

```java
import org.springframework.mail.MailException;

public void sendStatusUpdate(String recipient, String statusText) {
    SimpleMailMessage message = new SimpleMailMessage();
    message.setFrom("no-reply@example.com");
    message.setTo(recipient);
    message.setSubject("Cập nhật trạng thái");
    message.setText(statusText);

    try {
        mailSender.send(message);
        // Ghi nhận kết quả submission ở tầng ứng dụng.
    } catch (MailException exception) {
        // Ghi loại lỗi và correlation ID ở hạ tầng logging.
        // Chuyển lỗi cho quy trình xử lý/retry phù hợp.
        throw exception;
    }
}
```

Code này chưa triển khai retry. Retry cần một chính sách tách riêng, tránh lặp vô hạn trong thread HTTP. Đặc biệt, nếu timeout xảy ra **sau khi client đã gửi xong `DATA` nhưng chưa nhận phản hồi `250`**, ứng dụng không thể chắc chắn relay đã nhận email hay chưa. Gửi lại vô điều kiện có thể tạo email trùng.

Một quy trình retry hợp lý có thể:

1. Lưu `notification_id` hoặc `delivery_id` ổn định cho yêu cầu gửi.
2. Lưu từng `attempt_id`, thời gian gửi, provider và kết quả.
3. Phân loại lỗi tạm thời, lỗi cấu hình, lỗi vĩnh viễn và kết quả không chắc chắn.
4. Retry có **exponential backoff với jitter**, giới hạn số lần và thời hạn phù hợp.
5. Theo dõi webhook hoặc khả năng đối soát của provider khi có.
6. Không đánh dấu `delivered` chỉ vì `send` đã trả về thành công.

Đối với email OTP, chính sách thời hạn gửi cần gắn với thời gian hiệu lực của mã. Đối với cảnh báo vận hành, cần hạn chế storm khi cùng một lỗi được phát hiện liên tục.

## 15. Không để việc gửi simple mail làm treo luồng HTTP

`SimpleMailMessage` làm bước **tạo nội dung** đơn giản hơn; nó không làm hoạt động SMTP trở thành non-blocking. `JavaMailSender.send(...)` trong cách dùng phổ biến vẫn chờ các thao tác giao tiếp với SMTP transport.

Nếu gửi trực tiếp trong request:

```text
POST /orders
   |
   v
Lưu đơn hàng
   |
   v
Tạo SimpleMailMessage
   |
   v
JavaMailSender.send()
   |
   +--> TCP, TLS, AUTH, DATA, chờ xác nhận
   |
   v
Trả HTTP response
```

Khi SMTP chậm hoặc outage, request sẽ chờ. Với các hệ thống quan trọng, cách tổ chức tốt hơn có thể là outbox/queue và worker riêng:

```text
HTTP request
     |
     v
Business service
     | Ghi nghiệp vụ và outbox record
     v
HTTP response
     |
     v
Outbox / queue
     |
     v
Email worker
     | Tạo SimpleMailMessage
     | Gọi JavaMailSender
     | Retry/backoff và theo dõi attempt
     v
SMTP / ESP
```

Outbox giúp gắn yêu cầu gửi với transaction nghiệp vụ khi triển khai đúng. Worker xử lý lỗi SMTP độc lập, giảm nguy cơ một nhà cung cấp mail làm nghẽn toàn bộ API.

Tuy nhiên, lựa chọn giữa gửi đồng bộ và bất đồng bộ còn phụ thuộc nhu cầu: nếu một công cụ nội bộ chỉ gửi vài thông báo không khẩn cấp theo thao tác của quản trị viên, một lời gọi đồng bộ với timeout hợp lý có thể đủ. Không cần xây queue phức tạp chỉ vì đang dùng `SimpleMailMessage`.

## 16. Kiểm thử SimpleMailMessage

Một ưu điểm của loại message đơn giản là có thể kiểm tra các trường mà không cần mail server thật. Vì service phụ thuộc `JavaMailSender` qua constructor, unit test có thể dùng Mockito.

Giả sử kiểm thử `SupportNotificationService` ở phần 4:

```java
package example.mail;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class SupportNotificationServiceTest {

    @Test
    void sendsReadableRequestAcknowledgement() {
        JavaMailSender sender = mock(JavaMailSender.class);
        SupportNotificationService service =
                new SupportNotificationService(sender);

        service.sendRequestReceived("customer@example.net", "SUP-1042");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);

        verify(sender).send(captor.capture());

        SimpleMailMessage sent = captor.getValue();
        assertEquals("support@example.com", sent.getFrom());
        assertEquals("customer@example.net", sent.getTo()[0]);
        assertEquals("helpdesk@example.com", sent.getReplyTo());
        assertEquals("Đã tiếp nhận yêu cầu SUP-1042", sent.getSubject());
        assertEquals(true, sent.getText().contains("SUP-1042"));
    }
}
```

Test này xác nhận service tạo đúng message và gọi sender với message đó. Nó **không kiểm tra** SMTP AUTH, TLS, thư đã được relay chấp nhận hay giao đến inbox.

Nếu muốn kiểm tra integration, có thể cấu hình Spring Boot dùng một SMTP test server nội bộ ở port dành riêng cho test, sau đó lấy thư đã nhận từ server để xem header và body. Không dùng SMTP production để chạy unit test tự động.

Một ví dụ test đơn giản còn có thể kiểm tra Unicode, newline, recipient list và việc không để lộ địa chỉ trong Cc/To. Khi dùng các template động, test cần xác minh nội dung quan trọng có mặt và các biến được đặt đúng.

## 17. Một số sai lầm khi dùng SimpleMailMessage

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Người nhận thấy nguyên thẻ `<p>` hoặc `<strong>` | Đặt HTML vào `setText(...)` | Chuyển sang `MimeMessageHelper#setText(html, true)` |
| Muốn gắn PDF nhưng không thấy `addAttachment` | `SimpleMailMessage` chỉ hỗ trợ simple text | Dùng `MimeMessage` + `MimeMessageHelper` multipart |
| Email tiếng Việt lỗi dấu | Encoding sender hoặc môi trường không đồng nhất | Cấu hình UTF-8 và kiểm tra hệ thống gửi/nhận |
| Nội dung email bị lẫn giữa hai request | Dùng chung một `SimpleMailMessage` mutable | Tạo message mới cho mỗi lần gửi |
| Thông báo từ email khác bị SMTP từ chối | `From` không thuộc sender domain đã xác minh | Xem chính sách SMTP/ESP và cấu hình sender |
| Không nhận được bounce ở `Reply-To` | Nhầm Reply-To với SMTP envelope sender | Cấu hình bounce address qua provider phù hợp |
| Dùng `Bcc` nhưng vô tình lộ người nhận | Tự tạo danh sách `To` hoặc gửi chung sai quy tắc | Dùng recipient isolation và API đúng |
| Không biết người nhận đã đọc chưa | `send` chỉ thực hiện submission | Tích hợp telemetry từ ESP nếu có nhu cầu |
| Request HTTP bị chậm khi gửi mail | SMTP blocking, network hoặc timeout cao | Dùng timeout, queue/outbox hoặc worker |
| Retry gây hai email giống nhau | Server có thể đã nhận thư trước khi timeout | Lưu attempt và đối soát kết quả |
| Test bị kết nối SMTP thật | Không dùng fake/mock sender trong unit test | Inject mock, dùng SMTP test server cho integration |
| Thay template gốc gây rò nội dung | Sửa object dùng chung giữa các thread | Copy template trước khi thay To/Text |

## 18. Quy tắc ra quyết định trong dự án

Khi phát triển một tính năng email mới, có thể lựa chọn theo luồng:

```text
Có cần gửi email từ ứng dụng Spring?
             |
             v
Body có thể diễn đạt hoàn chỉnh bằng văn bản thuần?
             |
       +-----+-----+
       |           |
      Có          Không
       |           |
       v           v
Cần attachment,  Sử dụng MimeMessage
inline image,    + MimeMessageHelper
HTML alternative
hoặc MIME custom?
       |
   +---+---+
   |       |
  Không   Có
   |       |
   v       v
SimpleMailMessage   MimeMessage
+ JavaMailSender    + MimeMessageHelper
```

Bốn câu hỏi thực hành:

1. **Người nhận chỉ cần đọc thông tin hoặc sao chép một URL?** `SimpleMailMessage` thường đủ.
2. **Cần định dạng, nút bấm, banner, hình ảnh hoặc tệp?** Dùng `MimeMessage`.
3. **Cần cả phiên bản plain text và HTML trong một email?** Dùng `MimeMessageHelper` multipart, không gửi hai `SimpleMailMessage` độc lập để thay thế.
4. **Cần gửi số lượng lớn, retry, tracking hoặc sự kiện giao nhận?** Đây là yêu cầu kiến trúc gửi mail/ESP; có thể vẫn dùng `SimpleMailMessage` cho phần thân, nhưng phải bổ sung worker, lưu event và chính sách provider.

### Ví dụ từ đơn giản đến phức tạp

**Mức 1 — Email trạng thái**

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("no-reply@example.com");
mail.setTo("customer@example.net");
mail.setSubject("Yêu cầu đã được tiếp nhận");
mail.setText("Chúng tôi đã nhận yêu cầu của bạn.");
mailSender.send(mail);
```

**Mức 2 — Email trạng thái có link**

```java
SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("no-reply@example.com");
mail.setTo("customer@example.net");
mail.setSubject("Theo dõi yêu cầu");
mail.setText(
    "Yêu cầu của bạn đã được tiếp nhận.\n\n"
    + "Xem tiến độ: https://example.com/support/requests"
);
mailSender.send(mail);
```

Thêm URL không bắt buộc phải chuyển sang HTML.

**Mức 3 — Email trạng thái kèm PDF**

```text
Yêu cầu: gửi trạng thái + file xác nhận.pdf
→ Chuyển sang MimeMessage và addAttachment(...).
```

**Mức 4 — Email có nút CTA, logo và bản plain text dự phòng**

```text
Yêu cầu: HTML + hình inline + plain text alternative
→ Dùng MimeMessageHelper multipart, setText(plain, html), addInline(...).
```

Mỗi lần nâng cấp chỉ thay đổi cách xây message theo nhu cầu; cấu hình `JavaMailSender` và hạ tầng SMTP vẫn có thể được tái sử dụng.

## 19. Ghi nhớ cho người phát triển Spring Mail

`SimpleMailMessage` phù hợp khi email **chỉ cần văn bản thuần, các trường header cơ bản và nội dung dễ đọc bằng text**. API nhỏ giúp service dễ hiểu, dễ unit test và ít nguy cơ lỗi cấu trúc HTML/MIME.

Các nguyên tắc sử dụng cần giữ nhất quán:

- Dùng `JavaMailSender` hoặc `MailSender` được Spring quản lý; đừng tạo SMTP sender mới cho mỗi email.
- Tạo `SimpleMailMessage` **mới cho mỗi lần gửi**, hoặc sao chép template bất biến trước khi sửa.
- Đặt `From`, `To`, `Reply-To`, `Subject` và `Text` qua các setter thích hợp.
- Viết plain text có đoạn, xuống dòng và URL đầy đủ; giữ Unicode/UTF-8.
- Khi cần HTML, alternate, attachment, ảnh inline hoặc header nâng cao, chuyển sang `MimeMessage` và `MimeMessageHelper`.
- Xem `send()` thành công là kết quả SMTP submission, không phải bằng chứng delivered/opened/clicked.
- Bảo vệ đầu vào, secrets và dữ liệu người nhận; áp dụng timeout, retry và queue nếu yêu cầu vận hành cần.

Lựa chọn đúng không nằm ở việc API nào “mạnh” hơn mà ở **hình thức email cần tạo**. Với email văn bản thuần, `SimpleMailMessage` thường là công cụ rõ ràng và đủ dùng; với thư phức tạp, `MimeMessage` là lựa chọn được thiết kế cho cấu trúc đó.
