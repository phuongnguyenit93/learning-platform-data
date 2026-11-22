# Plain text, HTML và thư nhiều phần trong Spring Framework Mail

Gửi email từ ứng dụng Java không chỉ là đưa một chuỗi ký tự vào máy chủ SMTP. Ứng dụng cần quyết định **người nhận sẽ thấy nội dung ở định dạng nào**, có bản dự phòng cho chương trình đọc thư không hỗ trợ HTML hay không, và hình ảnh hoặc tệp đính kèm được đóng gói như thế nào. Spring Framework Mail cung cấp các API cho cả email văn bản đơn giản lẫn email MIME có cấu trúc phức tạp.

Trong bài này, ta lần lượt tạo thư plain text, thư HTML, thư có hai phiên bản nội dung và thư nhiều phần chứa hình ảnh nội tuyến cùng tệp đính kèm. Các ví dụ dùng Spring Boot để cấu hình thuận tiện, nhưng hai API cốt lõi là `JavaMailSender` và `MimeMessageHelper` thuộc Spring Framework Mail.

## 1. Phân biệt các kiểu nội dung thư

Một email được mô tả bằng các header (như `From`, `To`, `Subject`, `Content-Type`) và phần thân. Header `Content-Type` cho chương trình đọc thư biết cách diễn giải phần thân. Các kiểu thường gặp:

| Kiểu nội dung | `Content-Type` tiêu biểu | Đặc điểm | Khi nên dùng |
| --- | --- | --- | --- |
| Plain text | `text/plain; charset=UTF-8` | Chỉ có văn bản; xuống dòng và URL được hiển thị tùy ứng dụng đọc thư | OTP, cảnh báo ngắn, thông báo hệ thống, bản dự phòng dễ đọc |
| HTML | `text/html; charset=UTF-8` | Có thẻ HTML, liên kết, màu sắc và bố cục; khả năng hiển thị khác nhau giữa các email client | Thư chào mừng, hóa đơn, thông báo có cấu trúc |
| Alternative | `multipart/alternative` | Chứa **nhiều phiên bản của cùng một nội dung**, thường là plain text và HTML | Email HTML cần bản dự phòng cho các client khác nhau |
| Related | `multipart/related` | Gom nội dung với tài nguyên liên quan, ví dụ ảnh dùng qua `cid:...` | Logo hoặc ảnh hiển thị ngay trong nội dung HTML |
| Mixed | `multipart/mixed` | Gom các phần độc lập, điển hình là nội dung thư và tệp đính kèm | Gửi PDF, bảng dữ liệu, tài liệu cùng nội dung |

**Phân biệt quan trọng:** “multipart” nói đến *cấu trúc MIME có nhiều phần*, không đồng nghĩa với việc gửi thư cho nhiều người. Trường `To`/`Cc`/`Bcc` kiểm soát người nhận; `multipart/*` mô tả cách đóng gói nội dung.

Ví dụ, một thư thông báo có PDF và logo có thể có cấu trúc khái niệm:

```text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain; charset=UTF-8
│   │   └── text/html; charset=UTF-8
│   └── image/png; Content-ID: <brandLogo>  (inline)
└── application/pdf                      (attachment)
```

Cây MIME thực tế có thể khác tùy thư viện, nhưng ba quan hệ cần nhớ là: **alternative = các cách biểu diễn**, **related = tài nguyên cùng nội dung**, **mixed = các phần/tệp đi kèm**.

## 2. Chuẩn bị Spring Mail

Với Spring Boot và Maven, thêm dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Spring Boot quản lý phiên bản dependency tương ứng thông qua BOM/parent của dự án. Với ứng dụng dùng Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-mail'
```

Khai báo SMTP trong `src/main/resources/application.properties` (thông số chỉ là ví dụ; thay bằng máy chủ SMTP thực tế):

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
spring.mail.properties.mail.smtp.timeout=5000
spring.mail.properties.mail.smtp.writetimeout=5000
```

`spring.mail.*` tạo/cấu hình bean `JavaMailSender` khi có starter và cấu hình phù hợp. Tài khoản và mật khẩu SMTP nên đến từ biến môi trường hoặc bộ quản lý bí mật; không commit thông tin đăng nhập vào mã nguồn. Port `587` với STARTTLS chỉ là một cấu hình phổ biến: một số nhà cung cấp dùng port, TLS và cơ chế xác thực khác.

Các lớp quan trọng:

- `JavaMailSender`: tạo và gửi `MimeMessage`; đồng thời hỗ trợ `SimpleMailMessage`.
- `SimpleMailMessage`: mô hình đơn giản cho email **chỉ văn bản**.
- `jakarta.mail.internet.MimeMessage`: đối tượng thư MIME, hỗ trợ HTML, nhiều phần và tài nguyên đính kèm.
- `MimeMessageHelper`: API của Spring giúp thao tác `MimeMessage`, như `setText`, `addAttachment`, `addInline`, với ít mã Jakarta Mail hơn.

Ví dụ bên dưới sử dụng các import thuộc `jakarta.mail.*` (Spring Framework 6+/Spring Boot 3+) và Java 17+.

## 3. Gửi thư plain text bằng `SimpleMailMessage`

Khi chỉ cần thông báo văn bản, `SimpleMailMessage` là cách dễ hiểu nhất:

```java
package example.mail;

import org.springframework.mail.SimpleMailMessage;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.stereotype.Service;

@Service
public class PlainTextMailService {
    private final JavaMailSender mailSender;

    public PlainTextMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOtp(String recipient, String otp) {
        SimpleMailMessage message = new SimpleMailMessage();
        message.setFrom("no-reply@example.com");
        message.setTo(recipient);
        message.setSubject("Mã xác thực tài khoản");
        message.setText(
            "Xin chào,\n\n"
            + "Mã xác thực của bạn là: " + otp + "\n"
            + "Mã chỉ có hiệu lực trong thời gian quy định.\n\n"
            + "Nếu không yêu cầu, bạn có thể bỏ qua email này."
        );

        mailSender.send(message);
    }
}
```

`setText(...)` ở đây nhận **chuỗi văn bản thuần**, vì vậy các ký tự như `<strong>` hay `<a>` sẽ không biến thành HTML. Dùng `\n` để xuống dòng; không cần tự tạo thẻ HTML. Trong một ứng dụng thực tế, mã OTP phải được sinh, giới hạn thời gian và xác minh an toàn ở lớp nghiệp vụ; phần gửi mail chỉ đảm nhận việc truyền nội dung.

Ưu điểm của plain text là đơn giản, dễ đọc với công nghệ hỗ trợ tiếp cận và ít bị tác động bởi giới hạn hiển thị HTML. Hạn chế là không định dạng phong phú, không nhúng hình ảnh nội tuyến và không thêm tệp đính kèm bằng `SimpleMailMessage`.

Nếu vẫn muốn thư **chỉ plain text** nhưng cần các header MIME đặc biệt hoặc attachment, hãy chuyển sang `MimeMessage` thay vì cố gắng mở rộng `SimpleMailMessage`.

## 4. Gửi thư HTML bằng `MimeMessageHelper`

Để gửi phần thân HTML, sử dụng `MimeMessage` và đặt tham số `html=true`:

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class HtmlMailService {
    private final JavaMailSender mailSender;

    public HtmlMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            StandardCharsets.UTF_8.name()
        );
        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn");

        String html = """
            <!doctype html>
            <html lang="vi">
              <body>
                <h1>Chào mừng!</h1>
                <p>Tài khoản của bạn đã được tạo thành công.</p>
                <p><a href="https://example.com/account">Mở tài khoản</a></p>
              </body>
            </html>
            """;

        helper.setText(html, true);
        mailSender.send(message);
    }
}
```

Ở dòng `helper.setText(html, true)`, tham số thứ hai cho biết đây là **HTML**, khiến nội dung được đóng gói với `Content-Type: text/html`. Ngược lại, `helper.setText(html, false)` sẽ gửi chuỗi đó như văn bản thuần và các thẻ HTML có thể hiện nguyên văn.

Constructor `new MimeMessageHelper(message, "UTF-8")` thiết lập encoding, đủ cho ví dụ một phần thân HTML đơn giản. `UTF-8` giúp hiển thị đúng các dấu tiếng Việt trong nội dung và tiêu đề. Một thư chỉ có `text/html` **không tự động có** bản `text/plain` dự phòng.

### Lưu ý khi viết HTML cho email

HTML của email không được xử lý giống trang web trong trình duyệt:

- Nhiều email client hạn chế CSS bên ngoài, JavaScript, form và các tính năng tương tác; ưu tiên cấu trúc HTML đơn giản, inline CSS và liên kết rõ ràng.
- Dùng văn bản có nghĩa ngay cả khi ảnh bị chặn; thêm thuộc tính `alt` cho ảnh.
- Dùng URL đầy đủ (ví dụ `https://example.com/account`), tránh đường dẫn tương đối như `/account`.
- Không ghép trực tiếp dữ liệu không tin cậy vào HTML. Chẳng hạn tên khách hàng chứa `<`, `>` hoặc dấu nháy cần được escape đúng ngữ cảnh; sử dụng template engine là cách thực tế hơn.
- Giữ nội dung có thể đọc trên màn hình nhỏ. Dùng tiêu đề rõ, đoạn ngắn và liên kết nhận biết được.

## 5. Gửi cả plain text lẫn HTML bằng `multipart/alternative`

Một email HTML nên có một phiên bản văn bản thể hiện **cùng thông điệp**. Chương trình đọc thư sẽ lựa chọn phần thích hợp dựa trên khả năng và tùy chọn người dùng. Với Spring, dùng overload `setText(plainText, htmlText)`:

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AlternativeMailService {
    private final JavaMailSender mailSender;

    public AlternativeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendOrderNotice(String recipient, String orderCode)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        // multipart=true là bắt buộc khi có nhiều phần thân thay thế nhau.
        MimeMessageHelper helper = new MimeMessageHelper(
            message, true, StandardCharsets.UTF_8.name()
        );
        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Cập nhật đơn hàng");

        String plainText = "Đơn hàng " + orderCode
            + " đã được tiếp nhận.\n"
            + "Xem chi tiết: https://example.com/orders";

        // Trong ứng dụng thực tế, escape biến khi đưa vào HTML.
        String htmlText = """
            <html><body>
              <h2>Đơn hàng đã được tiếp nhận</h2>
              <p>Xem thông tin đơn hàng trong tài khoản của bạn.</p>
              <p><a href="https://example.com/orders">Xem đơn hàng</a></p>
            </body></html>
            """;

        helper.setText(plainText, htmlText);
        mailSender.send(message);
    }
}
```

Hai tham số của `setText(plainText, htmlText)` **không** phải hai email riêng, cũng không phải phần HTML nối sau phần văn bản. Chúng là hai cách trình bày một nội dung trong MIME. Cần khởi tạo `MimeMessageHelper` ở chế độ multipart (`true` hoặc hằng `MULTIPART_MODE_*`); nếu helper không ở chế độ multipart, overload hai chuỗi này không hoạt động.

Trong ví dụ trên, mã đơn hàng được đưa vào bản plain text. Nếu cũng hiển thị mã đó trong HTML, hãy dùng template có escaping như ở phần 8 để tránh chèn nội dung không an toàn. Hai phiên bản không bắt buộc giống từng ký tự nhưng nên chứa thông tin và liên kết quan trọng tương đương, nhất là thời hạn, số tiền, cảnh báo và hành động cần thực hiện.

Có thể hiểu cấu trúc cốt lõi như sau:

```text
multipart/alternative
├── text/plain  → "Đơn hàng đã được tiếp nhận..."
└── text/html   → "<h2>Đơn hàng đã được tiếp nhận</h2>..."
```

Khi Spring dùng chế độ multipart kết hợp cho cả file đính kèm, `multipart/alternative` có thể được lồng bên trong phần `related`/`mixed`. Đó vẫn là các phiên bản thay thế của cùng một thân thư.

## 6. Thư nhiều phần với hình nội tuyến và tệp đính kèm

Một email quảng bá hoặc thông báo giao dịch có thể cần **logo hiển thị ngay trong HTML** và **PDF đính kèm để tải xuống**. Đây là hai trường hợp khác nhau:

- **Inline**: tài nguyên được tham chiếu trong HTML bằng `cid:<content-id>`; phía MIME có header `Content-ID` tương ứng.
- **Attachment**: tài nguyên xuất hiện như tệp đính kèm, thường có `Content-Disposition: attachment` và tên tệp.

Sử dụng `MULTIPART_MODE_MIXED_RELATED` để Spring dựng cấu trúc phù hợp cho nội dung, tài nguyên nội tuyến và attachment.

Giả sử hai tệp đã tồn tại trong ứng dụng:

```text
src/main/resources/
└── mail/
    ├── brand-logo.png
    └── huong-dan.pdf
```

Ví dụ dịch vụ:

```java
package example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class MultipartMailService {
    private final JavaMailSender mailSender;

    public MultipartMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendGuide(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            StandardCharsets.UTF_8.name()
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Tài liệu hướng dẫn");

        String plainText = """
            Xin chào!

            Chúng tôi gửi bạn tài liệu hướng dẫn ở tệp đính kèm.
            Truy cập https://example.com/support nếu cần hỗ trợ.
            """;

        String htmlText = """
            <!doctype html>
            <html lang="vi">
              <body>
                <img src="cid:brandLogo" alt="Logo thương hiệu" width="120">
                <h2>Tài liệu hướng dẫn</h2>
                <p>Vui lòng xem PDF đính kèm để biết các bước thực hiện.</p>
                <p><a href="https://example.com/support">Trung tâm hỗ trợ</a></p>
              </body>
            </html>
            """;

        // Thiết lập phần thân trước khi thêm tài nguyên nội tuyến.
        helper.setText(plainText, htmlText);

        helper.addInline(
            "brandLogo",
            new ClassPathResource("mail/brand-logo.png"),
            "image/png"
        );

        helper.addAttachment(
            "huong-dan.pdf",
            new ClassPathResource("mail/huong-dan.pdf")
        );

        mailSender.send(message);
    }
}
```

Phân tích từng lệnh quan trọng:

1. `MULTIPART_MODE_MIXED_RELATED` tạo dạng MIME thích hợp cho thân thư, inline và attachment. Chế độ multipart chỉ nên bật khi nội dung cần nó.
2. `setText(plainText, htmlText)` bổ sung hai cách trình bày thân thư để người đọc có bản dự phòng.
3. `addInline("brandLogo", ...)` đặt ID nội dung của ảnh; thuộc tính `src="cid:brandLogo"` trong HTML phải khớp **chính xác** với ID này. Nên gọi `setText` **trước** `addInline` để tăng khả năng tương thích với các email client.
4. `addAttachment("huong-dan.pdf", ...)` thêm file để người nhận tải xuống. Tham số đầu là tên file hiển thị; `ClassPathResource` trỏ đến tài nguyên trong classpath.
5. `mailSender.send(message)` giao thư cho hệ thống gửi. Lệnh không bảo đảm email đã vào inbox: máy chủ nhận có thể tiếp tục lọc, trì hoãn hoặc từ chối.

Các overload khác của `addAttachment` và `addInline` chấp nhận `File`, `InputStreamSource` hoặc nguồn dữ liệu khác. Với stream, cần bảo đảm có thể đọc lại khi thư viện xây MIME; không đưa một `InputStream` đã tiêu thụ rồi cho quá trình gửi.

### Vì sao ảnh inline vẫn có thể không hiện?

Một số client chặn tải/hiển thị ảnh theo chính sách bảo mật, làm thay đổi cấu trúc MIME hoặc không hỗ trợ cách tổ chức `related` như mong đợi. Vì vậy, luôn có `alt` và giữ nội dung cốt lõi bằng văn bản; logo chỉ nên bổ trợ việc đọc.

Ảnh gắn qua `cid:...` không giống link ảnh từ Internet (`https://...`). Với `cid`, dữ liệu ảnh được đính kèm như phần MIME liên quan; với URL từ xa, ứng dụng đọc thư có thể phải tải thêm dữ liệu qua mạng.

## 7. Chọn API và cấu trúc thích hợp

| Nhu cầu | API và cách đặt nội dung | Kết quả |
| --- | --- | --- |
| OTP chỉ văn bản | `SimpleMailMessage#setText(text)` | Thư plain text đơn giản |
| Thư chỉ HTML | `MimeMessageHelper#setText(html, true)` | Thân thư HTML, không tự sinh plain text |
| Thư HTML có bản dự phòng | Helper multipart + `setText(plain, html)` | Hai phiên bản nội dung |
| HTML có ảnh trong nội dung | Helper multipart + `addInline(id, resource, type)` | Body và tài nguyên liên quan |
| Thư có PDF | Helper multipart + `addAttachment(name, resource)` | Body và tệp đính kèm |
| Có cả ảnh nội tuyến, PDF và bản dự phòng | `MULTIPART_MODE_MIXED_RELATED` + cả ba thao tác | MIME lồng nhau tương ứng |

Một điểm dễ nhầm: `helper.setText(html, true)` và `helper.setText(plain, html)` là **hai overload khác nhau**. Ở overload một chuỗi cộng boolean, `true` có nghĩa “đầu vào là HTML”. Ở overload hai chuỗi, chuỗi thứ nhất là plain text và chuỗi thứ hai là HTML, cần helper ở chế độ multipart.

### Các chế độ multipart của `MimeMessageHelper`

| Chế độ | Ý nghĩa |
| --- | --- |
| `MULTIPART_MODE_NO` | Không tạo multipart |
| `MULTIPART_MODE_MIXED` | Dùng `multipart/mixed` làm vùng chứa chung |
| `MULTIPART_MODE_RELATED` | Dùng `multipart/related` cho các phần có quan hệ với nhau |
| `MULTIPART_MODE_MIXED_RELATED` | Kết hợp vùng chứa `mixed` với vùng `related` lồng bên trong; hữu ích khi vừa có nội dung/ảnh vừa có tệp đính kèm |

Chế độ mặc định khi dùng constructor có `multipart=true` là `MULTIPART_MODE_MIXED_RELATED` ở các phiên bản Spring Framework phổ biến. Khi yêu cầu cấu trúc rõ ràng, việc truyền hằng chế độ như ví dụ trên giúp người đọc mã hiểu ý định.

## 8. Tạo HTML động bằng template

Đặt HTML dài trực tiếp trong Java chỉ phù hợp ví dụ nhỏ. Với ứng dụng thực tế, template giúp tách giao diện email khỏi xử lý nghiệp vụ và escape dữ liệu người dùng. Một lựa chọn là **Thymeleaf**.

Nếu chưa có, thêm dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-thymeleaf</artifactId>
</dependency>
```

Đặt template ở `src/main/resources/templates/mail/welcome.html`:

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
  <body>
    <h1>Chào mừng!</h1>
    <p>Xin chào <strong th:text="${customerName}">Khách hàng</strong>,</p>
    <p>Tài khoản của bạn đã sẵn sàng.</p>
    <p><a th:href="${accountUrl}">Truy cập tài khoản</a></p>
  </body>
</html>
```

Dấu `${...}` trên thuộc tính trong template thật là biểu thức Spring/Thymeleaf, được xử lý khi tạo nội dung. Phần Java:

```java
import java.util.Locale;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

// templateEngine được Spring cung cấp bằng dependency/configuration thích hợp.
Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("customerName", customerName);
context.setVariable("accountUrl", "https://example.com/account");
String html = templateEngine.process("mail/welcome", context);

// Sau đó gọi helper.setText(plainText, html) trong MimeMessageHelper multipart.
```

`th:text` giúp escape ký tự có ý nghĩa trong HTML khi chèn tên hoặc nội dung động. Với thuộc tính liên kết, nên kiểm soát/giới hạn URL đích phía ứng dụng; escape HTML không thay thế việc xác thực URL. Tránh `th:utext` cho dữ liệu chưa được làm sạch vì nó chèn HTML thô.

Nếu nội dung được gửi đa ngôn ngữ, có thể xây template riêng, dùng `MessageSource` và tạo plain text tương ứng. Không giả định rằng việc chuyển HTML sang plain text bằng cách xóa thẻ sẽ tạo ra bản dự phòng dễ đọc: link, bảng, nút bấm và thông tin nhấn mạnh có thể bị mất ý nghĩa.

## 9. Địa chỉ nhận, encoding và ranh giới trách nhiệm

Các thuộc tính `setTo`, `setCc`, `setBcc` trên `MimeMessageHelper` điều khiển người nhận:

```java
helper.setTo("customer@example.com");
helper.setCc("support@example.com");
helper.setBcc("audit@example.com");
```

`Cc` là người được nhận bản sao và hiển thị với người nhận; `Bcc` thường không xuất hiện trong danh sách người nhận được công bố. Việc thêm nhiều người nhận không tạo “multipart”. Khi gửi thư tới nhiều người cần riêng tư, cân nhắc gửi theo từng người thay vì đặt tất cả vào `To`.

Encoding UTF-8 nên được áp dụng nhất quán ở cấu hình mail và khi tạo helper để tránh lỗi ký tự tiếng Việt. Spring/Jakarta Mail xử lý việc mã hóa header và thân thư theo chuẩn MIME; không nên tự chèn `Content-Type` hoặc header mã hóa thủ công khi dùng helper.

Trong dịch vụ gửi mail, phân biệt ba giai đoạn:

1. **Tạo nội dung**: dựng plain text/HTML, chọn đúng phiên bản, làm sạch dữ liệu.
2. **Đóng gói MIME**: chọn chế độ multipart, gắn tài nguyên nội tuyến, attachment và header.
3. **Gửi qua SMTP**: chuyển MIME đến máy chủ gửi đã cấu hình.

`MessagingException` thường liên quan đến việc thao tác/đóng gói `MimeMessage`. Các lỗi từ tầng Spring Mail khi gửi có thể biểu hiện dưới các loại `MailException`, như xác thực hoặc thất bại khi gửi. Không nuốt lỗi rồi báo gửi thành công.

## 10. Những lỗi thường gặp và cách nhận diện

| Biểu hiện | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Người nhận thấy nguyên thẻ `<h1>` | Gửi HTML như plain text | Dùng `helper.setText(html, true)` hoặc `setText(plain, html)` |
| Thư HTML không có bản văn bản | Chỉ gọi `setText(html, true)` | Cung cấp plain text riêng và dùng overload hai chuỗi |
| Lỗi khi dùng `setText(plain, html)` | Helper chưa bật multipart | Khởi tạo với `true` hoặc chế độ multipart phù hợp |
| Ảnh logo không hiện | ID trong `cid:` không khớp, MIME sai thứ tự, client chặn ảnh | Kiểm tra ID; đặt `setText` trước `addInline`; có `alt` |
| Tệp đính kèm không được tìm thấy | Sai đường dẫn classpath hoặc tệp không được đóng gói vào ứng dụng | Kiểm tra vị trí dưới `src/main/resources` và tên resource |
| Tiếng Việt lỗi dấu | Encoding không thống nhất | Dùng UTF-8 khi tạo helper, cấu hình và template |
| Lỗi xác thực SMTP | Sai user/password, cơ chế xác thực hoặc yêu cầu của nhà cung cấp | Kiểm tra cấu hình SMTP/TLS và thông tin đăng nhập |
| Thư gửi không đến inbox | Lọc spam, chính sách máy chủ nhận, cấu hình tên miền hoặc trạng thái giao thư | Xem log máy chủ SMTP, bounce và thiết lập SPF/DKIM/DMARC |

**Phân biệt lỗi “send” và “delivery”:** `JavaMailSender#send(...)` có thể hoàn thành sau khi máy chủ SMTP chấp nhận thư, nhưng thư vẫn có thể bị từ chối hoặc phân loại sau đó. Hệ thống quan trọng cần theo dõi trạng thái giao thư/bounce theo khả năng của nhà cung cấp SMTP, thay vì xem việc gọi API thành công là bằng chứng người dùng đã đọc thư.

### Một số nguyên tắc vận hành

- Giới hạn kích thước tệp đính kèm theo chính sách SMTP và ứng dụng; một số máy chủ từ chối thư lớn.
- Không gửi mật khẩu hay dữ liệu nhạy cảm không cần thiết trong nội dung email. Đối với link xác nhận, đặt thời hạn và quy tắc sử dụng ở phía máy chủ.
- Tránh ghi nguyên nội dung email, OTP, địa chỉ nhận hàng loạt hoặc thông tin SMTP bí mật vào log.
- Khi gửi số lượng lớn, cân nhắc hàng đợi và cơ chế retry có kiểm soát. Retry mù quáng có thể gây gửi trùng khi máy chủ đã nhận thư nhưng kết nối phản hồi bị gián đoạn.
- Với email từ tên miền của tổ chức, cấu hình SPF, DKIM và DMARC phù hợp để cải thiện khả năng xác thực và uy tín gửi thư.
- Kiểm tra hiển thị trên các email client mục tiêu; cùng một HTML có thể trông khác nhau trên Gmail, Outlook và thiết bị di động.

## 11. Áp dụng cho một tình huống hoàn chỉnh

Giả sử cần gửi email “Hướng dẫn bắt đầu” cho người dùng mới với yêu cầu: đọc được dù tắt HTML, có logo, có PDF hướng dẫn và liên kết hỗ trợ. Một cách triển khai hợp lý là:

1. Viết **bản plain text** chứa lời chào, mục đích và URL hỗ trợ.
2. Tạo **bản HTML** với nội dung tương đương, bố cục thân thiện với email client và `alt` cho ảnh.
3. Dùng `MimeMessageHelper` ở chế độ `MULTIPART_MODE_MIXED_RELATED`.
4. Gọi `setText(plainText, htmlText)` để đưa vào các phiên bản thay thế.
5. Gọi `addInline("brandLogo", ...)` và tham chiếu `cid:brandLogo` trong HTML.
6. Gọi `addAttachment("huong-dan.pdf", ...)`.
7. Gửi bằng `JavaMailSender#send`, ghi nhận kết quả xử lý SMTP phù hợp với yêu cầu ứng dụng.

Ví dụ `MultipartMailService` ở phần 6 minh họa toàn bộ quá trình này. Chỉ cần bỏ `addInline` nếu không có hình nội tuyến; bỏ `addAttachment` nếu không cần PDF; còn nếu chỉ gửi vài dòng văn bản, `SimpleMailMessage` ở phần 3 vẫn là lựa chọn gọn nhất.

Khi làm việc với Spring Framework Mail, hãy chọn API theo **hình thức nội dung mà người nhận cần**: `SimpleMailMessage` cho plain text đơn giản; `MimeMessageHelper` cho HTML, phiên bản thay thế, ảnh nội tuyến và tệp đính kèm. Việc hiểu quan hệ `alternative`, `related` và `mixed` giúp thiết kế thư dễ đọc, tương thích hơn và dễ mở rộng khi tính năng gửi mail phát triển.
