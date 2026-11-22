# SimpleMailMessage cho thư chỉ có văn bản

Trong **Spring Framework Mail**, `SimpleMailMessage` là lớp giúp ứng dụng mô tả một email **văn bản thuần (plain text)** bằng các thuộc tính quen thuộc như người gửi, người nhận, tiêu đề và nội dung. Khi chỉ cần gửi thông báo đơn giản như “Tài khoản đã được tạo”, “Đơn hàng đang được xử lý” hoặc “Báo cáo hoàn tất”, đây thường là cách dễ tiếp cận nhất với API gửi mail của Spring.

Ví dụ ngắn:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setFrom("no-reply@example.com");
message.setTo("customer@example.net");
message.setSubject("Đăng ký thành công");
message.setText("Xin chào! Tài khoản của bạn đã được tạo.");

mailSender.send(message);
~~~

Đoạn mã có hai thành phần với vai trò khác nhau:

- **`SimpleMailMessage`:** đối tượng chứa **thông tin một bức thư**; bản thân nó không kết nối mạng và không tự gửi.
- **`MailSender` hoặc `JavaMailSender`:** thành phần thực hiện thao tác gửi bằng cấu hình mail transport của ứng dụng.

Bài học này đi từ cấu trúc đối tượng `SimpleMailMessage` tới ví dụ Spring Boot có thể áp dụng, cách dùng các trường địa chỉ, hạn chế của plain text và cách xử lý những tình huống thường gặp.

## 1. SimpleMailMessage nằm ở đâu trong Spring Mail?

`SimpleMailMessage` thuộc package:

~~~java
import org.springframework.mail.SimpleMailMessage;
~~~

Hai interface quan trọng:

~~~java
import org.springframework.mail.MailSender;
import org.springframework.mail.javamail.JavaMailSender;
~~~

Quan hệ sử dụng thường được mô tả như sau:

~~~text
Ứng dụng / NotificationService
    |
    | tạo dữ liệu thư
    v
SimpleMailMessage
    |
    | đưa vào phương thức send(...)
    v
MailSender (interface)
    ^
    |
JavaMailSender (interface, mở rộng MailSender)
    ^
    |
JavaMailSenderImpl (implementation SMTP thông dụng)
    |
    v
SMTP server / email provider
~~~

**`MailSender`** cung cấp phương thức gửi `SimpleMailMessage`. **`JavaMailSender`** mở rộng interface đó và hỗ trợ thêm `MimeMessage` cho nội dung phức tạp. Vì vậy, nếu service chỉ gửi plain text, phụ thuộc vào `MailSender` là đủ về mặt API; nếu cùng service cần tạo email MIME, sử dụng `JavaMailSender`.

Trong ứng dụng Spring Boot dùng starter mail và cấu hình phù hợp, bean sender thường được tự động cấu hình để có thể inject vào service. Với Spring Framework thuần hoặc cấu hình tùy biến, bạn phải cung cấp implementation tương ứng.

### 1.1. Dữ liệu thư và hành động gửi là hai trách nhiệm

Xét hai dòng:

~~~java
SimpleMailMessage message = new SimpleMailMessage();
mailSender.send(message);
~~~

Dòng đầu **chỉ khởi tạo một đối tượng trong bộ nhớ**. Ở thời điểm đó chưa có kết nối SMTP. Dòng sau mới yêu cầu sender thực hiện quá trình gửi. Tách hai trách nhiệm giúp việc tạo nội dung dễ kiểm thử và cho phép thay đổi cách cấu hình transport mà không phải viết lại mã ghép tiêu đề, người nhận và thân thư.

`SimpleMailMessage` là đối tượng **có thể thay đổi (mutable)**; các setter thay đổi trạng thái của chính đối tượng đó. Vì vậy, thông thường nên tạo **một instance mới cho mỗi email cần gửi** thay vì tái sử dụng cùng một đối tượng giữa nhiều request hoặc nhiều thread.

## 2. Những thuộc tính mà SimpleMailMessage hỗ trợ

Một bức thư text có thể có các trường sau:

| Thuộc tính | API tiêu biểu | Ý nghĩa |
| --- | --- | --- |
| Người đứng tên gửi | `setFrom(String from)` | Địa chỉ hiển thị trong trường `From` |
| Đích khi người dùng trả lời | `setReplyTo(String replyTo)` | Địa chỉ được đề xuất khi người nhận nhấn Reply |
| Người nhận chính | `setTo(String... to)` | Một hoặc nhiều địa chỉ `To` |
| Người nhận bản sao | `setCc(String... cc)` | Các địa chỉ `Cc` |
| Người nhận bản sao kín | `setBcc(String... bcc)` | Các địa chỉ `Bcc` |
| Ngày gửi | `setSentDate(Date date)` | Thời điểm khai báo trong thông điệp |
| Tiêu đề | `setSubject(String subject)` | Dòng tiêu đề email |
| Nội dung | `setText(String text)` | Phần thân plain text |

`SimpleMailMessage` cũng có getter tương ứng như `getFrom()`, `getTo()`, `getSubject()` và `getText()` để đọc giá trị đã thiết lập.

Các thuộc tính địa chỉ trên khác với việc thao tác trực tiếp với giao thức SMTP. Ví dụ `setFrom(...)` khai báo người gửi của **thông điệp**, nhưng địa chỉ dùng trong **SMTP envelope** có thể chịu ảnh hưởng của sender implementation hoặc cấu hình provider. Không nên suy luận chỉ từ `setFrom` rằng bạn đã tự chọn được toàn bộ đường đi hoặc địa chỉ nhận bounce.

### 2.1. `setFrom(...)`: địa chỉ người đứng tên gửi

~~~java
message.setFrom("no-reply@example.com");
~~~

Địa chỉ này thường xuất hiện trong header `From` của email. Ứng dụng phải sử dụng domain và tài khoản có quyền gửi theo chính sách nhà cung cấp. Một số SMTP provider chỉ cho phép địa chỉ hoặc domain đã được xác minh; nhập địa chỉ bất kỳ không bảo đảm server chấp nhận.

Nên tách địa chỉ mặc định của ứng dụng ra cấu hình thay vì lặp lại ở từng phương thức gửi:

~~~yaml
app:
  mail:
    from: ${MAIL_FROM:no-reply@example.com}
~~~

Đây là thuộc tính **tự định nghĩa** của ứng dụng, cần được đọc và truyền vào `setFrom`. Nó không tự động được Spring Boot áp dụng lên mọi email.

### 2.2. `setTo(...)`, `setCc(...)` và `setBcc(...)`: các nhóm người nhận

~~~java
message.setTo("alice@example.net");
message.setCc("manager@example.net");
message.setBcc("audit@example.net");
~~~

Ý nghĩa thông thường:

- **To:** người nhận chính.
- **Cc:** người được gửi bản sao; địa chỉ thường được các người nhận khác nhìn thấy.
- **Bcc:** người được gửi bản sao kín; không nên bị lộ trong bản thư được phát cho người nhận khác.

Có thể khai báo nhiều địa chỉ:

~~~java
message.setTo(
    "alice@example.net",
    "bob@example.net"
);

message.setCc(new String[] {
    "teamlead@example.net",
    "observer@example.net"
});
~~~

**Lưu ý về riêng tư:** dùng `To` hoặc `Cc` cho danh sách khách hàng có thể làm lộ địa chỉ của họ cho nhau. Dùng `Bcc` có thể phù hợp với một số nhu cầu, nhưng các thông báo giao dịch cá nhân thường nên tạo email riêng cho từng người nhận để tránh nhầm nội dung cá nhân, trạng thái gửi và cơ chế retry.

### 2.3. `setReplyTo(...)`: địa chỉ nhận phản hồi

~~~java
message.setFrom("notification@example.com");
message.setReplyTo("support@example.com");
~~~

Khi người đọc nhấn **Reply**, ứng dụng mail của họ thường sử dụng `Reply-To` nếu có; nếu thiếu, thường sử dụng `From`. `Reply-To` không thay đổi địa chỉ SMTP dùng nhận thông báo lỗi phát thư (bounce), không tự mở hộp thư nhận và không bảo đảm người dùng sẽ trả lời.

Trong ví dụ này, thư được gửi dưới tên địa chỉ `notification@example.com` nhưng lời đáp được hướng về `support@example.com`. Địa chỉ support phải tồn tại và được cấu hình nhận mail thì phản hồi mới có thể đi đến nơi.

### 2.4. `setSubject(...)`: tiêu đề

~~~java
message.setSubject("Đơn hàng #A123 đã được xác nhận");
~~~

Tiêu đề nên ngắn, rõ nghiệp vụ và không chứa dữ liệu bí mật như mã OTP, token đặt lại mật khẩu hoặc thông tin nhạy cảm. Mặc dù email client có thể hỗ trợ tiêu đề Unicode, việc biểu diễn ký tự trên đường truyền vẫn do thư viện mail và charset/encoding phụ trách.

### 2.5. `setText(...)`: văn bản thuần

~~~java
message.setText("""
    Xin chào,

    Đơn hàng A123 của bạn đã được ghi nhận.
    Bộ phận xử lý sẽ cập nhật trạng thái tiếp theo.

    Trân trọng,
    Đội ngũ hỗ trợ
    """);
~~~

Nội dung là chuỗi `String` thông thường. Ký tự xuống dòng và khoảng trắng được đưa vào thân thư theo cách phù hợp khi Spring/Jakarta Mail xây dựng thông điệp. Các đoạn rõ ràng, câu ngắn, đường dẫn đầy đủ và phân cách dòng hợp lý thường giúp thư text dễ đọc trên điện thoại.

Nếu gọi:

~~~java
message.setText("<h1>Chào mừng!</h1>");
~~~

Người nhận sẽ thấy chuỗi ký tự giống như `<h1>Chào mừng!</h1>`, **không phải tiêu đề HTML được render**, vì `SimpleMailMessage` dành cho plain text.

### 2.6. `setSentDate(...)`: thời điểm trên thông điệp

~~~java
import java.util.Date;

message.setSentDate(new Date());
~~~

Trường này biểu diễn ngày giờ gửi ở mức header của email. Nó không phải cơ chế hẹn lịch gửi; đặt một ngày trong tương lai **không** khiến Spring Mail tự đợi đến thời điểm đó mới nộp thư cho SMTP.

Nếu cần gửi theo lịch, hãy sử dụng scheduler, queue/job hoặc quy trình vận hành có nhiệm vụ kích hoạt việc gửi vào đúng thời điểm.

## 3. Ví dụ đầy đủ trong Spring Boot

Giả sử ứng dụng Spring Boot có một service gửi thông báo plain text khi tài khoản được tạo.

### 3.1. Khai báo dependency

Với Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Starter cung cấp những thành phần cần thiết để ứng dụng Spring Boot sử dụng Spring Mail cùng thư viện Jakarta Mail tương ứng. Trong dự án Spring Framework thuần, bạn có thể cấu hình dependency và bean sender thủ công mà không cần starter.

### 3.2. Cấu hình máy chủ SMTP

Ví dụ `application.yml` cho SMTP server dùng STARTTLS:

~~~yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: ${SMTP_PORT:587}
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
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
    reply-to: ${MAIL_REPLY_TO:support@example.com}
~~~

Giải thích:

| Cấu hình | Vai trò |
| --- | --- |
| `spring.mail.host` / `port` | Địa chỉ và cổng SMTP của nhà cung cấp |
| `spring.mail.username` / `password` | Thông tin xác thực nếu SMTP provider yêu cầu |
| `spring.mail.default-encoding` | Encoding mặc định cho nội dung/thông điệp khi sender tạo MIME |
| `mail.smtp.starttls.enable` | Bật khả năng nâng cấp kết nối SMTP bằng STARTTLS |
| `mail.smtp.starttls.required` | Yêu cầu nâng cấp TLS thành công |
| Các timeout | Giới hạn thời gian kết nối, nhận và ghi dữ liệu |
| `app.mail.from` / `reply-to` | Giá trị riêng của ứng dụng dùng khi gọi setter |

Cổng `587` là một lựa chọn phổ biến với STARTTLS, nhưng phải kiểm tra cấu hình thật của nhà cung cấp. Nếu provider dùng SMTP qua TLS ngay từ đầu trên cổng `465`, cấu hình kết nối sẽ khác (ví dụ thuộc tính SSL thích hợp). Không nên tắt xác thực TLS hoặc chép nguyên ví dụ sang mọi provider.

**Không commit mật khẩu SMTP vào repository.** Môi trường production nên cấp credentials qua biến môi trường hoặc secret manager. Ngay cả khi dùng email văn bản đơn giản, việc gửi thư vẫn phụ thuộc vào cấu hình transport và quyền sử dụng domain của SMTP provider.

### 3.3. Tạo service gửi thông báo

~~~java
package com.example.mail.application;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class AccountMailService {
    private final JavaMailSender mailSender;
    private final String from;
    private final String replyTo;

    public AccountMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String from,
            @Value("${app.mail.reply-to}") String replyTo) {
        this.mailSender = mailSender;
        this.from = from;
        this.replyTo = replyTo;
    }

    public void sendWelcome(String recipient, String displayName) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom(from);
        message.setReplyTo(replyTo);
        message.setTo(recipient);
        message.setSubject("Chào mừng bạn đến với ứng dụng");
        message.setText("""
            Xin chào %s,

            Tài khoản của bạn đã được tạo thành công.
            Nếu cần hỗ trợ, bạn có thể trả lời email này.

            Trân trọng,
            Đội ngũ ứng dụng
            """.formatted(displayName));

        mailSender.send(message);
    }
}
~~~

Trong ví dụ này:

1. Spring inject `JavaMailSender` vào constructor.
2. Các giá trị `From` và `Reply-To` được lấy từ cấu hình.
3. Mỗi lần gọi `sendWelcome(...)` tạo **một `SimpleMailMessage` mới**.
4. Service gán người nhận, tiêu đề và nội dung plain text.
5. `mailSender.send(message)` thực hiện thao tác nộp thư qua cơ chế gửi đã cấu hình.

Đây là ví dụ tập trung vào cách dùng API. Trong dịch vụ thực tế, tầng gọi cần xác định đúng người được phép nhận email, kiểm tra dữ liệu đầu vào, giới hạn thao tác gửi và xử lý kết quả hoặc lỗi theo yêu cầu nghiệp vụ.

### 3.4. Cách sử dụng trong nghiệp vụ

Một service xử lý đăng ký có thể gọi:

~~~java
accountMailService.sendWelcome(
    "new-user@example.net",
    "Nguyễn An"
);
~~~

Cách này phù hợp với chương trình nhỏ hoặc thao tác không yêu cầu tách xử lý gửi thư. Tuy nhiên, **việc tạo tài khoản** và **việc chuyển email qua SMTP** là hai nghiệp vụ có khả năng thất bại độc lập. Với hệ thống cần độ tin cậy cao, có thể phát sinh sự kiện hoặc lưu yêu cầu gửi vào queue/outbox để worker xử lý sau.

## 4. Giới hạn của SimpleMailMessage: chỉ text, không MIME phức tạp

`SimpleMailMessage` rất tiện cho email đơn giản, nhưng không có API để dựng nội dung HTML, tệp đính kèm, ảnh inline hoặc nhiều phần alternative.

| Yêu cầu | `SimpleMailMessage` có phù hợp? | Công cụ thường dùng |
| --- | --- | --- |
| Gửi một đoạn plain text | **Có** | `SimpleMailMessage` + `MailSender` |
| Gửi nhiều dòng và đường dẫn URL | **Có** | `setText(...)` |
| Đặt From, To, Cc, Bcc, Reply-To | **Có** | Các setter tương ứng |
| Gửi tiêu đề và nội dung có tiếng Việt | **Có**, qua encoding của mail sender | Sender được cấu hình UTF-8 |
| Nội dung được render như HTML | **Không** | `MimeMessage` + `MimeMessageHelper` |
| Gửi cả plain text và HTML thay thế | **Không** | `MimeMessageHelper.setText(plainText, htmlText)` |
| Đính kèm PDF hoặc ZIP | **Không** | `MimeMessageHelper.addAttachment(...)` |
| Chèn ảnh bằng `cid:...` | **Không** | `MimeMessageHelper.addInline(...)` |
| Tự đặt header tùy chỉnh | **Không qua API đơn giản của lớp này** | `MimeMessage` |
| Đọc mail từ inbox | **Không** | Cơ chế nhận thư riêng |

Chú ý: email plain text vẫn được vận chuyển dưới dạng một thông điệp email theo các chuẩn Internet; nói “không MIME” ở đây chỉ có nghĩa `SimpleMailMessage` **không cung cấp mô hình dựng email nhiều phần hoặc nội dung MIME phức tạp**. Spring/Jakarta Mail vẫn có thể tạo các header MIME thích hợp như `Content-Type: text/plain; charset=UTF-8` khi gửi.

### 4.1. Khi nào nên chuyển sang `MimeMessageHelper`?

Nếu email có yêu cầu như “gửi hóa đơn PDF cùng phần mô tả”, “hiển thị nút xác nhận bằng HTML” hoặc “cung cấp cả bản text và HTML”, bạn nên chuyển sang `MimeMessage`:

~~~java
import jakarta.mail.internet.MimeMessage;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(mime, true, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Thông tin đơn hàng");
helper.setText(
    "Đơn hàng của bạn đã được xác nhận.",
    "<html><body><h1>Xác nhận đơn hàng</h1></body></html>"
);

mailSender.send(mime);
~~~

Tham số `true` khi khởi tạo helper bật hỗ trợ multipart; phương thức `setText(plainText, htmlText)` thiết lập hai phiên bản nội dung. Khi cần tài nguyên inline hoặc attachment, có thể thêm bằng các phương thức riêng của helper.

Không nên cố tạo email HTML bằng cách đặt chuỗi thẻ HTML vào `SimpleMailMessage.setText(...)`: email client sẽ nhận nội dung text và không có chỉ dẫn để render như HTML.

## 5. Gửi một email và nhiều email

`MailSender` hỗ trợ gửi một hoặc nhiều `SimpleMailMessage`. Với `JavaMailSender`, cũng có thể gọi cùng các overload dành cho loại thông điệp này.

### 5.1. Gửi một email

~~~java
SimpleMailMessage message = new SimpleMailMessage();
message.setTo("alice@example.net");
message.setFrom("no-reply@example.com");
message.setSubject("Báo cáo");
message.setText("Báo cáo đã được tạo.");

mailSender.send(message);
~~~

### 5.2. Gửi nhiều thông điệp riêng biệt

~~~java
SimpleMailMessage first = new SimpleMailMessage();
first.setFrom("no-reply@example.com");
first.setTo("alice@example.net");
first.setSubject("Thông báo cho Alice");
first.setText("Xin chào Alice.");

SimpleMailMessage second = new SimpleMailMessage();
second.setFrom("no-reply@example.com");
second.setTo("bob@example.net");
second.setSubject("Thông báo cho Bob");
second.setText("Xin chào Bob.");

mailSender.send(first, second);
~~~

Ở đây, mỗi người nhận có một thông điệp riêng, giúp cá nhân hóa nội dung và giảm nguy cơ lộ địa chỉ người khác. Tuy nhiên, overload gửi nhiều message **không tạo ra bảo đảm transaction all-or-nothing**: lỗi trong một phần quá trình có thể xảy ra sau khi một số thông điệp đã được gửi. Vì vậy, hệ thống cần ghi nhận trạng thái riêng cho mỗi yêu cầu, đặc biệt khi có retry.

### 5.3. Dùng template đối tượng và copy constructor

Nếu nhiều email có phần cấu hình giống nhau, `SimpleMailMessage` hỗ trợ tạo một bản sao từ một instance khác:

~~~java
SimpleMailMessage template = new SimpleMailMessage();
template.setFrom("no-reply@example.com");
template.setReplyTo("support@example.com");
template.setSubject("Thông báo từ hệ thống");

SimpleMailMessage message = new SimpleMailMessage(template);
message.setTo("alice@example.net");
message.setText("Xin chào Alice.");

mailSender.send(message);
~~~

Ý tưởng là giữ một mẫu thông tin chung, sau đó tạo bản sao và bổ sung dữ liệu cá nhân cho từng thư. Tránh dùng lại trực tiếp một `SimpleMailMessage` mutable rồi liên tục thay đổi `To` và `Text` trong các tác vụ song song. Nếu template chung được chia sẻ, hãy đảm bảo nó được khởi tạo hoàn chỉnh và không bị sửa trong lúc các luồng khác sao chép.

## 6. Viết email plain text dễ đọc

Plain text không có CSS, bảng HTML hay nút bấm đồ họa; chất lượng phụ thuộc vào cách viết nội dung.

### 6.1. Ví dụ email xác nhận đơn hàng

~~~text
Chào Nguyễn An,

Đơn hàng #A123 của bạn đã được ghi nhận.

Tóm tắt:
- Mã đơn hàng: A123
- Trạng thái: Đang xử lý
- Ngày đặt: 12/11/2026

Bạn có thể xem tiến độ tại:
https://example.com/orders/A123

Nếu cần hỗ trợ, hãy trả lời email này.

Trân trọng,
Đội ngũ chăm sóc khách hàng
~~~

Các điểm cần nhớ:

- Đặt thông tin quan trọng ở phần đầu; một số email client chỉ hiện vài dòng preview.
- Dùng đoạn ngắn, dấu gạch đầu dòng và dòng trống khi có nhiều thông tin.
- Đặt URL đầy đủ thay vì giả định có thể dùng text liên kết như HTML.
- Viết rõ địa chỉ hoặc kênh hỗ trợ để người đọc biết phải làm gì tiếp theo.
- Tránh nhúng dữ liệu cá nhân quá mức, mã xác thực hoặc token nhạy cảm trong nội dung, subject và log.

### 6.2. Khi dữ liệu có ký tự Unicode

Ví dụ:

~~~java
message.setSubject("Xác nhận yêu cầu hỗ trợ");
message.setText("Xin chào Nguyễn An,\nYêu cầu của bạn đã được ghi nhận.");
~~~

`String` của Java hỗ trợ Unicode; mail sender và thư viện bên dưới sẽ chịu trách nhiệm biểu diễn văn bản và header để truyền qua email. Với email có tiếng Việt, nên cấu hình encoding rõ ràng, ví dụ `spring.mail.default-encoding: UTF-8` trong Spring Boot.

Nếu người nhận thấy ký tự lỗi như `Ã` hoặc chuỗi quoted-printable chưa được giải mã, hãy kiểm tra charset và header khi email được gửi. Không nên tự Base64-encode toàn bộ `message.setText(...)`, vì setter yêu cầu **nội dung văn bản**, không phải chuỗi đã được mã hóa thủ công.

## 7. Xử lý lỗi khi gửi với SimpleMailMessage

Thao tác gửi có thể thất bại vì kết nối mạng, máy chủ SMTP không khả dụng, xác thực sai, người nhận bị từ chối hoặc vấn đề cấu hình.

Spring sử dụng hệ thống ngoại lệ `MailException` (unchecked) và một số lớp con:

| Ngoại lệ | Ý nghĩa khái quát |
| --- | --- |
| `MailAuthenticationException` | Có vấn đề ở bước xác thực mail |
| `MailSendException` | Có lỗi trong quá trình gửi |
| `MailPreparationException` | Có lỗi khi chuẩn bị thông điệp mail |
| `MailException` | Lớp cha chung cho lỗi Spring Mail |

Ví dụ service ghi nhận lỗi ở ranh giới gửi:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.mail.MailException;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class ReportMailService {
    private static final Logger log =
            LoggerFactory.getLogger(ReportMailService.class);

    private final JavaMailSender sender;

    public ReportMailService(JavaMailSender sender) {
        this.sender = sender;
    }

    public void sendReport(String recipient, String reportId) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("reports@example.com");
        message.setTo(recipient);
        message.setSubject("Báo cáo đã sẵn sàng");
        message.setText(
                "Báo cáo " + reportId + " đã được tạo thành công.");

        try {
            sender.send(message);
            log.info("SMTP submission completed for reportId={}", reportId);
        } catch (MailException ex) {
            log.error("SMTP submission failed for reportId={}", reportId, ex);
            throw ex;
        }
    }
}
~~~

Đoạn code dùng `reportId` làm thông tin theo dõi, tránh ghi tràn lan địa chỉ người nhận và toàn bộ nội dung thư vào log. Việc ném lại ngoại lệ giúp tầng gọi nhận biết đã có lỗi; trong sản phẩm thật, có thể ghi nhận trạng thái công việc và đưa vào hàng đợi xử lý tùy yêu cầu.

### 7.1. Lời gọi gửi thành công có nghĩa gì?

Nếu `sender.send(message)` trả về bình thường, ta biết lời gọi gửi thông qua sender đã hoàn tất mà không phát sinh ngoại lệ đồng bộ. Với SMTP, kết quả đó thường biểu thị nhà cung cấp đã chấp nhận **thao tác nộp thư**, **không chứng minh** email đã tới Inbox, đã được đọc hoặc không bị hệ thống phía sau trả lại.

Muốn theo dõi trạng thái thực sự của email sau khi nộp, cần cơ chế bên ngoài API đơn giản như:

- webhook sự kiện delivered/bounced của email provider;
- Delivery Status Notification (DSN), bounce mailbox hoặc dịch vụ xử lý thư trả về;
- trạng thái job được ghi vào database khi hệ thống dùng queue.

`SimpleMailMessage` không có trường để tự quản lý các trạng thái nghiệp vụ này.

### 7.2. Không phải lỗi nào cũng nên retry

SMTP có phản hồi `4xx` cho nhiều tình huống tạm thời và `5xx` cho nhiều trường hợp cần khắc phục trước khi gửi lại. Nhưng JavaMailSender có thể báo một ngoại lệ tổng quát, còn mã phản hồi SMTP chỉ nằm ở nguyên nhân sâu bên dưới, nếu có.

Không nên phân loại “cứ `MailSendException` là retry” hoặc “mọi `MailAuthenticationException` đều là sai mật khẩu vĩnh viễn”. Cần xét nguyên nhân thật, mã SMTP nếu có, nhà cung cấp và pha giao thức. Timeout sau khi dữ liệu thư đã được gửi còn có thể tạo trạng thái **không chắc máy chủ đã chấp nhận hay chưa**; retry có nguy cơ gây gửi trùng.

Đối với yêu cầu quan trọng, nên gắn **ID nghiệp vụ**, lưu số lần gửi và kết quả theo từng người nhận, sử dụng backoff có giới hạn và cơ chế chống xử lý trùng ở tầng ứng dụng.

## 8. Gửi đồng bộ và gửi bất đồng bộ

Mặc định, một lời gọi `mailSender.send(message)` thông thường chạy trên luồng gọi và đợi hoạt động gửi tương ứng kết thúc hoặc phát sinh lỗi.

~~~mermaid
flowchart LR
    A["Đăng ký tài khoản"] --> B["Account service"]
    B --> C["Tạo SimpleMailMessage"]
    C --> D["JavaMailSender.send"]
    D --> E["SMTP provider"]
    E -. "Kết quả gửi đồng bộ" .-> B
~~~

Điều này đơn giản nhưng có thể làm HTTP request chậm nếu SMTP phản hồi chậm. Với hệ thống nhiều thư hoặc đòi hỏi độ tin cậy:

~~~mermaid
flowchart LR
    A["Đăng ký tài khoản"] --> B["Lưu nghiệp vụ"]
    B --> C["Lưu mail job / outbox"]
    C --> D["Queue hoặc worker"]
    D --> E["Tạo SimpleMailMessage"]
    E --> F["JavaMailSender.send"]
    F --> G["SMTP provider"]
    D --> H["Trạng thái / retry"]
~~~

`SimpleMailMessage` **không phụ thuộc vào việc gọi đồng bộ hay bất đồng bộ**: nó vẫn chỉ là dữ liệu thư. Worker có thể dùng cùng API `send(...)` để nộp message. Dùng `@Async` cũng không tự cung cấp hàng đợi bền vững qua restart, lịch retry hay cơ chế chống gửi trùng; các tính năng đó cần được thiết kế riêng.

## 9. Kiểm thử service gửi SimpleMailMessage

Vì nội dung được gói trong một đối tượng dữ liệu đơn giản, ta có thể kiểm thử logic dựng thư mà không kết nối SMTP thật.

### 9.1. Kiểm thử đơn vị bằng mock sender

Giả sử service nhận `JavaMailSender` từ constructor, có thể dùng Mockito bắt lại đối tượng được truyền cho `send(...)`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;

import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;

class AccountMailServiceTest {

    @Test
    void sendsWelcomeAsPlainText() {
        JavaMailSender sender = mock(JavaMailSender.class);
        AccountMailService service =
                new AccountMailService(
                        sender,
                        "no-reply@example.com",
                        "support@example.com");

        service.sendWelcome("customer@example.net", "Nguyễn An");

        ArgumentCaptor<SimpleMailMessage> captor =
                ArgumentCaptor.forClass(SimpleMailMessage.class);
        verify(sender).send(captor.capture());

        SimpleMailMessage message = captor.getValue();
        assertEquals("no-reply@example.com", message.getFrom());
        assertEquals("support@example.com", message.getReplyTo());
        assertEquals("customer@example.net", message.getTo()[0]);
        assertEquals(
                "Chào mừng bạn đến với ứng dụng",
                message.getSubject());
        assertEquals(true, message.getText().contains("Nguyễn An"));
    }
}
~~~

Kiểu kiểm thử này xác nhận service **dựng đúng dữ liệu và gọi sender**, nhưng không kiểm tra máy chủ SMTP thật, encoding sau chuyển đổi sang MIME hay trạng thái giao thư. Tên service trong ví dụ tương ứng với lớp đã định nghĩa ở phần trên; dự án cần có JUnit Jupiter và Mockito trong test dependencies.

### 9.2. Kiểm thử tích hợp với SMTP giả lập

Các công cụ như **Mailpit** hoặc **GreenMail** cho phép ứng dụng gửi email tới máy chủ thử nghiệm rồi xem nội dung đã được nhận:

1. Cấu hình host/port trỏ tới SMTP server thử nghiệm.
2. Gọi service tạo `SimpleMailMessage`.
3. Quan sát email được ghi nhận trong công cụ thử nghiệm.
4. Kiểm tra header `From`, `To`, `Reply-To`, `Subject` và `Content-Type` của thông điệp nhận được.
5. Kiểm tra nội dung text và khả năng hiển thị ký tự Unicode.

Việc dùng SMTP giả lập giúp tránh gửi email thử cho khách hàng thật. Chỉ nên kết luận kiểm thử tích hợp đã mô phỏng thành công **luồng nộp thư**, chưa phải kiểm chứng inbox delivery với nhà cung cấp production.

## 10. Các sai lầm dễ gặp

### 10.1. Dùng cùng một SimpleMailMessage cho nhiều request

~~~java
// Không phù hợp nếu nhiều request dùng chung instance mutable.
private final SimpleMailMessage sharedMessage = new SimpleMailMessage();

public void send(String to, String text) {
    sharedMessage.setTo(to);
    sharedMessage.setText(text);
    sender.send(sharedMessage);
}
~~~

Hai request song song có thể ghi đè địa chỉ/nội dung của nhau. Hãy tạo đối tượng mới cho từng yêu cầu hoặc sao chép một template bất biến về mặt sử dụng:

~~~java
public void send(String to, String text) {
    SimpleMailMessage message = new SimpleMailMessage();
    message.setFrom("no-reply@example.com");
    message.setTo(to);
    message.setText(text);
    sender.send(message);
}
~~~

### 10.2. Đưa HTML vào `setText(...)` và mong được render

~~~java
message.setText("<strong>Important</strong>");
~~~

Nội dung trên vẫn là plain text. Nếu cần HTML, chuyển sang `MimeMessageHelper` và dùng phương thức `setText(html, true)` hoặc `setText(plainText, htmlText)`.

### 10.3. Cho người dùng nhập người nhận tùy ý mà không kiểm soát

Một endpoint công khai cho phép người ngoài gọi:

~~~text
POST /send-mail
to = bất kỳ địa chỉ nào
subject = bất kỳ chuỗi nào
body = bất kỳ nội dung nào
~~~

Rất dễ trở thành công cụ gửi spam. Hãy gắn hành động gửi với nghiệp vụ cụ thể, xác thực/ủy quyền nguồn gọi, kiểm tra dữ liệu, giới hạn tốc độ và tránh để người dùng tùy ý lựa chọn `From`. Khi thao tác với địa chỉ, hãy sử dụng API JavaMail phù hợp để kiểm tra cú pháp và để thư viện xử lý header thay vì tự nối các dòng SMTP/header từ chuỗi input.

### 10.4. Quên cấu hình timeout

Không có timeout phù hợp, một lần gửi tới SMTP provider có vấn đề có thể kéo dài hơn dự kiến, làm chậm request hoặc chiếm thread worker. Nên cấu hình timeout kết nối/đọc/ghi phù hợp với yêu cầu hệ thống và phương án retry.

### 10.5. Đánh đồng gửi thành công với đã giao thư

Lời gọi `send(...)` thành công thường thể hiện SMTP server đã nhận trách nhiệm xử lý thư ở mức giao thức; nó không xác nhận người nhận đã xem. Các hệ thống giao dịch quan trọng nên ghi “đã nộp thư cho dịch vụ gửi” ở trạng thái nội bộ khi thích hợp, thay vì hiển thị sai rằng người nhận chắc chắn đã nhận.

### 10.6. Nhầm Reply-To với địa chỉ nhận bounce

`setReplyTo("support@example.com")` hướng hành động trả lời của người dùng. Nó không phải cấu hình reverse-path của SMTP envelope và không đảm bảo bounce sẽ chuyển về đó. Theo dõi bounce thường cần cấu hình nhà cung cấp, DSN hoặc webhook.

## 11. So sánh nhanh với MimeMessage

| Tiêu chí | `SimpleMailMessage` | `MimeMessage` / `MimeMessageHelper` |
| --- | --- | --- |
| Độ phức tạp | Ít API, dễ đọc | Nhiều tùy chọn cấu trúc hơn |
| Nội dung | Plain text | Text, HTML và multipart |
| Người gửi/nhận/Reply-To | Có | Có |
| Cc/Bcc | Có | Có |
| Tiêu đề Unicode | Được hỗ trợ qua sender/encoding | Được hỗ trợ qua thư viện MIME |
| File đính kèm | Không | Có |
| Ảnh nội tuyến | Không | Có |
| Header tùy chỉnh | Hạn chế | Có thể thao tác trên `MimeMessage` |
| Phù hợp | OTP thông báo đơn giản (tránh đưa bí mật nhạy cảm khi không cần), text notification, cảnh báo nội bộ | Email marketing HTML, hóa đơn PDF, email nhiều phần |

Không cần chuyển sang MIME chỉ vì email có nhiều dòng hoặc chứa tiếng Việt. `SimpleMailMessage` xử lý tốt trường hợp text cơ bản. Lý do chuyển sang MIME chủ yếu đến từ **yêu cầu về định dạng và phần đính kèm**.

## 12. Tình huống tổng hợp: hệ thống gửi thông báo hoàn tất tác vụ

Giả sử một ứng dụng có quy trình tạo báo cáo. Khi báo cáo hoàn thành, hệ thống muốn gửi email text cho người yêu cầu:

~~~text
From: reports@example.com
Reply-To: support@example.com
To: customer@example.net
Subject: Báo cáo tháng 11 đã sẵn sàng

Xin chào,

Báo cáo tháng 11 đã được tạo thành công.
Bạn có thể mở trang quản lý để tải báo cáo.

Nếu cần hỗ trợ, hãy trả lời email này.
~~~

Quy trình triển khai:

1. **Report service** xác định người cần nhận và ID báo cáo đã hoàn thành.
2. **Notification service** tạo một `SimpleMailMessage` mới, đặt địa chỉ, tiêu đề và nội dung text.
3. **Mail sender** được inject qua Spring gọi `send(message)` để nộp email cho SMTP provider.
4. **Tầng điều phối** ghi trạng thái nộp thư và phân loại lỗi nếu cần.
5. Nếu nghiệp vụ đòi hỏi gửi lại, **worker hoặc queue** quản lý retry theo ID công việc, không dùng cùng instance mutable.
6. Nếu sau này muốn đính kèm PDF, chuyển phần dựng nội dung sang **`MimeMessageHelper`**, còn ý định thông báo từ Report service vẫn có thể giữ nguyên.

Một số câu hỏi tự kiểm tra khi đọc code:

- `SimpleMailMessage` được tạo mới ở đâu và có bị chia sẻ giữa các thread không?
- `From`, `To`, `Reply-To` và tiêu đề lấy từ đâu, có phù hợp quyền gửi và nghiệp vụ không?
- `setText(...)` đang chứa nội dung plain text thực sự hay mã HTML bị gửi nhầm?
- Encoding/SMTP timeout/credentials được cấu hình ở đâu?
- Nếu sender báo lỗi, ứng dụng xử lý thế nào và có nguy cơ gửi trùng khi retry không?

Hiểu đúng `SimpleMailMessage` là hiểu **một mô hình dữ liệu email đơn giản**: tạo thông điệp plain text bằng các setter, chuyển cho `MailSender`/`JavaMailSender` gửi, và để cơ chế bên ngoài phụ trách cấu hình SMTP, theo dõi trạng thái, bảo mật và retry. Đây là nền tảng tốt trước khi học sâu về `MimeMessage` và các cấu trúc email nhiều phần.

### API và tài liệu tra cứu

- **Spring Framework — `org.springframework.mail.SimpleMailMessage`:** constructor, copy constructor, các phương thức `setFrom`, `setTo`, `setCc`, `setBcc`, `setReplyTo`, `setSubject`, `setText` và `setSentDate`.
- **Spring Framework — `MailSender`:** giao diện gửi `SimpleMailMessage`.
- **Spring Framework — `JavaMailSender` và `MimeMessageHelper`:** mở rộng sang nội dung MIME, HTML và attachment.
- **Spring Boot — Mail support / `spring.mail.*`:** tự cấu hình sender và các thuộc tính kết nối SMTP.
