# `spring.mail.default-encoding`

Khi ứng dụng Spring Boot gửi email tiếng Việt, một lỗi rất dễ gặp là máy chủ SMTP chấp nhận thư nhưng người nhận thấy `ChÃ o`, `Th?ng b?o` hoặc những ký tự không đúng với nội dung mà ứng dụng đã tạo. Để một mail client khôi phục được văn bản, phần nội dung MIME phải được chuyển thành byte theo **bộ mã ký tự (charset)** phù hợp và được mô tả bằng header chính xác.

Spring Boot cung cấp thuộc tính **`spring.mail.default-encoding`** để cấu hình **charset mặc định khi tạo MIME message qua mail sender được Spring Boot cấu hình tự động**. Giá trị thường dùng là **`UTF-8`**. Đây là một thiết lập nhỏ, nhưng cần hiểu phạm vi tác động của nó: nó không tự chọn HTML hay text, không thay thế `Content-Type`, không kiểm soát SMTP relay và cũng không sửa được dữ liệu đã bị đọc sai charset ở bước trước.

Bài này giải thích vai trò, cách áp dụng, thứ tự ưu tiên khi override, mối liên hệ với `JavaMailSender` và `MimeMessageHelper`, cùng cách phân tích sự cố ký tự trong email.

## 1. Encoding của email nằm ở đâu?

Email không vận chuyển trực tiếp một đối tượng Java `String`. Khi tạo nội dung, ứng dụng cần biến chuỗi Unicode thành các byte. MIME cho phép khai báo loại dữ liệu, charset và cách biểu diễn byte trên đường gửi thư.

```text
Nguồn dữ liệu / template
       |
       | Đọc đúng charset của nguồn
       v
Java String: "Chào bạn"
       |
       | Charset: UTF-8
       v
Byte: 43 68 C3 A0 6F 20 62 E1 BA A1 6E
       |
       | Content-Transfer-Encoding (nếu cần)
       v
MIME body, ví dụ: Ch=C3=A0o b=E1=BA=A1n
       |
       | SMTP / mail server / mailbox
       v
Mail client giải mã transfer encoding
       |
       | Dùng charset được khai báo
       v
Văn bản: "Chào bạn"
```

Với một phần MIME chứa văn bản, các header có thể trông như sau:

```eml
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Ch=C3=A0o b=E1=BA=A1n
```

Ở đây:

- `Content-Type: text/plain` cho biết dữ liệu là **văn bản thuần**.
- `charset=UTF-8` cho biết byte của **phần văn bản này** được diễn giải thành ký tự bằng UTF-8.
- `Content-Transfer-Encoding: quoted-printable` chỉ cách biểu diễn byte trong body; các chuỗi `=C3=A0` là dạng mã hóa đường truyền, không phải văn bản gốc.
- Mail client phải khôi phục byte từ quoted-printable **trước**, rồi dùng UTF-8 để hiển thị `Chào bạn`.

Thuộc tính `spring.mail.default-encoding` chủ yếu liên quan đến lựa chọn **charset mặc định ở bước tạo văn bản MIME**.

## 2. `spring.mail.default-encoding` nghĩa là gì?

Đây là một property của **Spring Boot Mail**:

```properties
spring.mail.default-encoding=UTF-8
```

Hoặc viết trong `application.yml`:

```yaml
spring:
  mail:
    default-encoding: UTF-8
```

Spring Boot dùng giá trị này để cấu hình encoding mặc định cho `JavaMailSenderImpl` khi auto-configuration tạo sender. Giá trị là một **tên charset được Java nhận diện**, chẳng hạn `UTF-8`. Spring Boot 3.x mặc định sử dụng **UTF-8** cho mail encoding trong cấu hình chuẩn của mình; khai báo tường minh vẫn hữu ích khi muốn làm rõ quy ước của ứng dụng.

### Ý nghĩa của từ “default”

`Default` nghĩa là **giá trị được sử dụng khi nơi tạo MIME part không yêu cầu charset khác**. Nó không phải quy tắc cứng buộc mọi nội dung, mọi attachment và mọi mail client phải sử dụng cùng một charset.

Ví dụ:

```text
Spring Boot configuration
  spring.mail.default-encoding = UTF-8
                |
                v
JavaMailSenderImpl (defaultEncoding = "UTF-8")
                |
                | mailSender.createMimeMessage()
                v
Spring-managed MimeMessage
                |
                | new MimeMessageHelper(message, ...)
                | nếu không ghi đè encoding
                v
Text part / HTML part được tạo với UTF-8
                |
                v
Jakarta Mail đóng gói MIME và gửi SMTP
```

Điểm cần phân biệt: **Spring Boot** bind property và cấu hình sender; **Spring Framework Mail** cung cấp `JavaMailSenderImpl` và `MimeMessageHelper`; **Jakarta Mail** thực hiện các chi tiết xây dựng và gửi MIME message.

### Default encoding không phải là cấu hình SMTP

| Property | Công dụng | Ví dụ |
| --- | --- | --- |
| `spring.mail.host` | Host của SMTP server | `smtp.example.org` |
| `spring.mail.port` | Cổng kết nối SMTP | `587` |
| `spring.mail.username` | Danh tính xác thực nếu cần | Tài khoản ứng dụng |
| `spring.mail.password` | Secret dùng xác thực nếu cần | Lấy từ môi trường |
| `spring.mail.properties.*` | Thuộc tính bổ sung của Jakarta Mail/SMTP | `mail.smtp.starttls.enable` |
| **`spring.mail.default-encoding`** | **Charset mặc định cho MIME message** | **`UTF-8`** |

Thay `UTF-8` bằng một giá trị khác **không** thay đổi host, cổng, TLS, SMTP AUTH, giới hạn gửi, sender address hay quyền relay.

## 3. Vì sao nên dùng UTF-8 cho email tiếng Việt?

UTF-8 là một cách mã hóa Unicode thành byte, có khả năng biểu diễn tiếng Việt, nhiều ngôn ngữ khác và các ký tự thông dụng. Nó giữ nguyên cách biểu diễn byte của ASCII ở vùng ký tự cơ bản nên rất phù hợp cho ứng dụng hiện đại.

Xét chuỗi:

```text
Chào bạn
```

Byte UTF-8 tương ứng:

```text
43 68 C3 A0 6F 20 62 E1 BA A1 6E
```

Ví dụ, ký tự `à` được biểu diễn bằng hai byte `C3 A0`; ký tự `ạ` được biểu diễn bằng ba byte `E1 BA A1`. **Số ký tự Java, số byte UTF-8 và số ký tự trong quoted-printable/base64 là những đại lượng khác nhau**.

Giả sử ứng dụng dùng một charset chỉ hỗ trợ các ký tự ASCII hoặc không thể biểu diễn ký tự tiếng Việt cần gửi. Khi chuyển `String` thành byte, một số ký tự có thể bị thay thế bằng `?` hoặc kết quả khác theo chính sách encoder. Nếu byte đã bị mất thông tin, việc đổi header thành `charset=UTF-8` ở giai đoạn sau không thể khôi phục dấu đã mất.

### Charset đúng phải khớp byte thực tế

MIME header:

```text
Content-Type: text/plain; charset=UTF-8
```

là một **lời khai về byte của body sau khi decode transfer encoding**. Nếu ứng dụng tạo byte theo một charset khác nhưng khai báo UTF-8, mail client có thể hiển thị sai. Ngược lại, nếu thư chứa đúng byte UTF-8 nhưng header khai báo một charset không tương ứng, người đọc cũng gặp lỗi.

Sử dụng UTF-8 nhất quán là nguyên tắc tốt, nhưng **tính nhất quán từ nguồn dữ liệu tới MIME part** mới là điều quyết định.

## 4. Cấu hình thực tế trong Spring Boot

### 4.1. Dependency

Với Maven, thường khai báo:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-mail</artifactId>
</dependency>
```

Spring Boot cung cấp auto-configuration cho `JavaMailSender` khi các điều kiện về thư viện và cấu hình được thỏa mãn. Starter mail mang các thành phần cần thiết để tích hợp Spring Mail/Jakarta Mail trong ứng dụng Boot.

### 4.2. `application.yml`

Ví dụ SMTP submission dùng STARTTLS trên cổng 587:

```yaml
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
    from: ${MAIL_FROM_ADDRESS}
```

Giải thích:

- `default-encoding: UTF-8` quy định charset mặc định cho MIME message.
- `host` và `port` là địa chỉ máy chủ nhận submission.
- `username`/`password` phục vụ xác thực nếu SMTP server yêu cầu.
- `mail.smtp.starttls.enable` và `required` minh họa việc yêu cầu nâng cấp bảo vệ kết nối qua STARTTLS.
- Các timeout tính bằng mili giây nhằm tránh kết nối hoặc lời gọi gửi chờ vô hạn khi server không phản hồi.
- `app.mail.from` là property riêng của ứng dụng, **không phải** một property mặc định của Spring Mail.

Cấu hình ví dụ phù hợp với endpoint hỗ trợ STARTTLS trên 587. Nếu nhà cung cấp dùng implicit TLS trên 465 hoặc OAuth, phải dùng cấu hình phù hợp với dịch vụ đó. Cũng cần chọn địa chỉ `From` nằm trong phạm vi gửi được nhà cung cấp cấp quyền.

**Không đưa mật khẩu SMTP thật vào repository.** Có thể cấp credential qua biến môi trường hoặc secret manager của nền tảng triển khai.

### 4.3. Dùng `application.properties`

Hai cách YAML và properties thể hiện cùng một cấu hình:

```properties
spring.mail.host=${SMTP_HOST}
spring.mail.port=587
spring.mail.username=${SMTP_USERNAME}
spring.mail.password=${SMTP_PASSWORD}
spring.mail.default-encoding=UTF-8
spring.mail.properties.mail.smtp.auth=true
spring.mail.properties.mail.smtp.starttls.enable=true
spring.mail.properties.mail.smtp.starttls.required=true
```

Các placeholder `${SMTP_HOST}`, `${SMTP_USERNAME}` và `${SMTP_PASSWORD}` nhận giá trị từ môi trường hoặc nguồn cấu hình tương ứng khi ứng dụng chạy; dấu `:587` trong `${SMTP_PORT:587}` chỉ giá trị mặc định nếu không có cấu hình khác.

## 5. `JavaMailSenderImpl` nhận default encoding như thế nào?

`JavaMailSenderImpl` thuộc package:

```java
import org.springframework.mail.javamail.JavaMailSenderImpl;
```

Class này có API:

```java
sender.setDefaultEncoding("UTF-8");
```

Khi sender tạo thông điệp qua `createMimeMessage()`, các thiết lập mặc định của sender được lưu trên kiểu MIME message mà Spring sử dụng để `MimeMessageHelper` có thể nhận biết. Trong đường đi điển hình:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, true);
```

Nếu message được tạo từ `JavaMailSenderImpl` có default encoding, helper có thể lấy lại cấu hình đó mà không cần truyền tên charset lần nữa.

Ví dụ khi ứng dụng **tự quản lý** sender:

```java
JavaMailSenderImpl sender = new JavaMailSenderImpl();
sender.setHost("smtp.example.org");
sender.setPort(587);
sender.setDefaultEncoding("UTF-8");
```

Đây là ví dụ minh họa API; một sender SMTP thật còn phải cấu hình credential, TLS và các thuộc tính transport phù hợp.

### Phân biệt Spring Boot auto-configuration và bean tự khai báo

Khi Spring Boot tự tạo sender, `spring.mail.default-encoding` được áp dụng trong cấu hình đó. Nhưng nếu ứng dụng tự định nghĩa bean `JavaMailSender`/`JavaMailSenderImpl` riêng, Boot có thể **không tạo sender mặc định** nữa. Bean tự quản lý sẽ cần được cấu hình encoding tương ứng.

Ví dụ:

```java
@Bean
JavaMailSender customSender() {
    JavaMailSenderImpl sender = new JavaMailSenderImpl();
    sender.setHost("smtp.example.org");
    sender.setPort(587);
    sender.setDefaultEncoding("UTF-8");
    // Cấu hình auth/TLS và các thiết lập khác tùy SMTP server.
    return sender;
}
```

Không nên giả định rằng mọi property `spring.mail.*` vẫn tự động được sao chép vào bean do ứng dụng tự tạo. Với sender tự cấu hình, hãy xác định rõ ai sở hữu mọi thông số SMTP, encoding, timeout và credentials.

### Kiểu dữ liệu của property

Ở mức cấu hình Boot, encoding là một giá trị **charset**, được chuyển thành tên phù hợp khi gắn vào JavaMail sender. `UTF-8` là charset tiêu chuẩn được Java hỗ trợ. Tránh nhập tên charset không được hỗ trợ hoặc giá trị trông giống tên media type:

```properties
# Đúng: tên charset
spring.mail.default-encoding=UTF-8

# Không đúng ý nghĩa: đây là media type, không phải tên charset
# spring.mail.default-encoding=text/html

# Không đúng ý nghĩa: đây là transfer encoding
# spring.mail.default-encoding=base64
```

## 6. Sử dụng default encoding với `MimeMessageHelper`

`MimeMessageHelper` là API tiện ích để tạo thư text, HTML và multipart trong Spring Framework Mail. Dưới đây là ví dụ dùng encoding mặc định do sender cung cấp.

### 6.1. Gửi văn bản thuần

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class AccountMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public AccountMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress
    ) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendWelcome(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(message);

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject("Chào mừng đến với hệ thống");
        helper.setText(
                "Xin chào! Tài khoản của bạn đã được tạo thành công.",
                false
        );

        mailSender.send(message);
    }
}
```

Đoạn này sử dụng `new MimeMessageHelper(message)` mà **không truyền encoding tường minh**. Với message được tạo qua sender đã có default encoding `UTF-8`, helper sử dụng default phù hợp để tạo phần văn bản. `setText(..., false)` chỉ rõ body là text thuần.

Các địa chỉ `fromAddress` và `recipient` phải hợp lệ theo yêu cầu ứng dụng và chính sách SMTP server. Exception của Jakarta Mail/Spring phản ánh lỗi chuẩn bị hoặc gửi, không mặc nhiên chứng minh người dùng đã nhận thư.

### 6.2. Gửi HTML có tiếng Việt

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Thông báo xác nhận");
helper.setText(
        "<h1>Xin chào!</h1>"
            + "<p>Đơn hàng của bạn đã được xác nhận.</p>",
        true
);

mailSender.send(message);
```

`setText(html, true)` biểu thị nội dung HTML và giúp MIME part mang `Content-Type: text/html`. Charset mặc định như `UTF-8` giúp mã hóa các ký tự tiếng Việt trong HTML.

**Dùng UTF-8 không tự biến text thành HTML.** Nếu gọi `setText(html, false)`, helper sẽ tạo text thuần và người nhận có thể thấy nguyên các tag `<h1>` và `<p>`. Hai khái niệm khác nhau:

- `isHtml`/`Content-Type`: xác định dữ liệu là HTML hay text.
- `charset`: xác định cách mã hóa ký tự văn bản.

### 6.3. Gửi cả text và HTML

Thư giao dịch có thể cung cấp hai phiên bản cùng nội dung:

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, true);

helper.setFrom("notifications@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Xác nhận đơn hàng");

helper.setText(
        "Chào bạn. Đơn hàng đã được xác nhận.",
        "<p>Chào bạn. <strong>Đơn hàng</strong> đã được xác nhận.</p>"
);

mailSender.send(message);
```

Phương thức `setText(plainText, htmlText)` tạo các phần văn bản thay thế trong cấu trúc MIME. Mỗi text part cần một charset phù hợp; helper có thể dùng default encoding của sender khi chuẩn bị các part. Mail client lựa chọn bản text hoặc HTML theo khả năng và thiết lập.

Vì hai phần đại diện cùng một thông điệp, nội dung nghiệp vụ quan trọng cần xuất hiện trong **cả hai phiên bản**.

## 7. Thứ tự ưu tiên: property mặc định và encoding tường minh

Khi tạo helper, ứng dụng có thể chỉ định charset riêng:

```java
import java.nio.charset.StandardCharsets;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        true,
        StandardCharsets.UTF_8.name()
);
```

Constructor nhận encoding tường minh sẽ sử dụng encoding đó cho phần nội dung mà helper tạo, thay vì chỉ dựa vào default từ message. Điều này hữu ích khi một luồng gửi có yêu cầu riêng hoặc ứng dụng muốn nhìn thấy rõ charset ngay tại nơi xây dựng MIME.

| Nơi quyết định | Ví dụ | Kết quả về mặt nguyên tắc |
| --- | --- | --- |
| Spring Boot property | `spring.mail.default-encoding=UTF-8` | Default encoding của sender do Boot cấu hình |
| Sender tự cấu hình | `sender.setDefaultEncoding("UTF-8")` | Default áp dụng cho message do sender tạo |
| Helper không chỉ định encoding | `new MimeMessageHelper(message, true)` | Kế thừa default của message khi có |
| Helper chỉ định encoding | `new MimeMessageHelper(message, true, "UTF-8")` | Dùng encoding được truyền vào helper |
| MIME part được thao tác trực tiếp ở mức Jakarta Mail | `mimePart.setText(text, "UTF-8")` | Charset có thể được quyết định ở chính part đó |

Đây là **các tầng lựa chọn charset**, không phải một bảng bảo đảm rằng mọi phần của message luôn có đúng một charset. Khi can thiệp trực tiếp bằng Jakarta Mail, ứng dụng có thể tạo ra các part với những charset khác nhau.

### Ví dụ: ghi đè chỉ cho một message

Giả sử sender được cấu hình default là một encoding tương thích với hệ thống cũ, nhưng một email cụ thể cần UTF-8:

```java
MimeMessage mime = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        mime,
        false,
        "UTF-8"
);

helper.setSubject("Thông báo bằng tiếng Việt");
helper.setText("Dữ liệu dùng UTF-8.", false);
```

`false` ở đây là tham số **multipart**, không phải bật/tắt UTF-8. Helper đã nhận UTF-8 ở tham số thứ ba. Chọn multipart dựa trên cấu trúc email mong muốn; chọn encoding dựa trên văn bản cần biểu diễn.

Nếu code thực tế có nhiều nơi tạo `MimeMessageHelper`, cần biết nơi nào truyền encoding tường minh và nơi nào kế thừa default để tránh hiểu nhầm hiệu lực của property Boot.

## 8. `Content-Type`, `charset` và `Content-Transfer-Encoding` khác nhau

Ba khái niệm cùng xuất hiện trong header MIME nhưng giải quyết ba vấn đề riêng:

| Khái niệm | Trả lời câu hỏi | Ví dụ |
| --- | --- | --- |
| **Content-Type** | Đây là loại nội dung gì? | `text/plain`, `text/html`, `application/pdf` |
| **charset** | Byte của **text part** tương ứng với ký tự theo bộ mã nào? | `UTF-8` |
| **Content-Transfer-Encoding** | Byte được biểu diễn ra sao trong nội dung truyền email? | `quoted-printable`, `base64`, `7bit` |

Ví dụ 1, text thuần tiếng Việt:

```eml
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Ch=C3=A0o b=E1=BA=A1n.
```

Ví dụ 2, HTML tiếng Việt:

```eml
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<p>Xin ch=C3=A0o!</p>
```

Ví dụ 3, attachment PDF:

```eml
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQKLi4u
```

Chuỗi PDF base64 là đoạn minh họa, **không phải file PDF hoàn chỉnh**. Byte dữ liệu của PDF không cần `charset=UTF-8`: PDF là loại dữ liệu nhị phân, không phải một text part của email.

### Vì sao không đặt `spring.mail.default-encoding=base64`?

Base64 là một cơ chế biểu diễn byte, **không phải charset**. Nó thuộc trách nhiệm `Content-Transfer-Encoding`, và Jakarta Mail thường chọn cách vận chuyển phù hợp khi serialize MIME part.

Tương tự, `text/html` là media type, **không phải encoding**. Nếu muốn gửi HTML tiếng Việt, cần chọn `text/html` **và** charset phù hợp, ví dụ UTF-8.

### `8BITMIME` và `SMTPUTF8` có liên quan không?

Các SMTP extension như `8BITMIME` và `SMTPUTF8` có mục đích riêng. `8BITMIME` cho phép những trường hợp body chứa byte 8-bit khi hai bên hỗ trợ; `SMTPUTF8` liên quan tới email quốc tế hóa trong các thành phần mà SMTP truyền thống không hỗ trợ.

Việc cấu hình `default-encoding=UTF-8` **không tự bật** các extension SMTP này. Đối với body tiếng Việt được đóng gói bằng quoted-printable/base64, ứng dụng không cần tự bật SMTPUTF8 chỉ vì nội dung có dấu.

## 9. Subject và tên người gửi có dấu được xử lý thế nào?

Body không phải phần duy nhất chứa Unicode. Tiêu đề, tên hiển thị người gửi và tên hiển thị người nhận cũng có thể có dấu:

```text
Subject: Xác nhận đơn hàng
From: "Bộ phận chăm sóc khách hàng" <support@example.org>
```

Trong email truyền thống, một số giá trị header phải được mã hóa theo quy tắc riêng, chẳng hạn **MIME encoded-word** dạng:

```text
Subject: =?UTF-8?B?Q2jDoG8=?=
```

Chuỗi `=?UTF-8?B?Q2jDoG8=?=` biểu diễn từ `Chào` trong một ví dụ header. Đây là **cú pháp encoding của header**, khác với `Content-Transfer-Encoding` của body dù đều có thể sử dụng base64.

Khi xây dựng email bằng Spring:

```java
MimeMessageHelper helper = new MimeMessageHelper(message, "UTF-8");

helper.setFrom("notifications@example.org", "Bộ phận thông báo");
helper.setTo("customer@example.net");
helper.setSubject("Xác nhận đơn hàng");
helper.setText("Xin chào bạn.", false);
```

Những API này giúp thư viện tạo các giá trị header đúng định dạng. Tên hiển thị có dấu nên được truyền vào API hỗ trợ charset, thay vì tự nối chuỗi raw header với byte tùy ý.

**Charset của body part không đồng nghĩa toàn bộ header đều được diễn giải theo cùng một quy tắc.** Vì vậy, nếu chỉ `Subject` lỗi nhưng body hiển thị tốt, phải quan sát cách header được mã hóa, không chỉ kiểm tra `Content-Type` của body.

## 10. MIME multipart: mỗi part có charset riêng

Email HTML có attachment là một **MIME tree**, không phải một khối văn bản duy nhất:

```text
Top-level message:
  Content-Type: multipart/mixed
      |
      +-- Part 1: multipart/alternative
      |      |
      |      +-- text/plain; charset=UTF-8
      |      |
      |      +-- text/html; charset=UTF-8
      |
      +-- Part 2: application/pdf
               Content-Disposition: attachment
               Content-Transfer-Encoding: base64
```

Chỉ các part biểu diễn văn bản mới cần một charset theo nghĩa này. **Property `spring.mail.default-encoding` không biến byte ảnh/PDF/ZIP thành UTF-8.**

Ví dụ Spring tạo HTML và tệp PDF:

```java
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message, true);

helper.setFrom("billing@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Hóa đơn tháng này");
helper.setText(
        "Xin chào. Hóa đơn của bạn ở tệp đính kèm.",
        "<p>Xin chào. <strong>Hóa đơn</strong> ở tệp đính kèm.</p>"
);
helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(invoicePdfBytes),
        "application/pdf"
);

mailSender.send(message);
```

Ở đây, mặc định UTF-8 hỗ trợ phần text và HTML. Media type của PDF được truyền tường minh; byte PDF được đưa vào `ByteArrayResource` và không được chuyển qua một Java `String`.

### File name có dấu là một chuyện khác

Ví dụ `helper.addAttachment("hóa-đơn.pdf", resource, "application/pdf")`. Tên tệp nằm trong parameter của header MIME như `Content-Disposition`, có quy tắc encoding riêng và còn chịu ảnh hưởng từ mail client nhận thư. Thư viện MIME giúp xử lý tên file quốc tế hóa, nhưng không nên suy ra rằng chỉ đặt `spring.mail.default-encoding=UTF-8` sẽ khắc phục mọi trường hợp filename bị lỗi trên mọi client.

Nếu tên file có thông tin không đáng tin cậy từ người dùng, ứng dụng còn phải làm sạch path, ký tự điều khiển và giới hạn độ dài. Đây là trách nhiệm xử lý dữ liệu đầu vào, không phải trách nhiệm của property encoding.

## 11. `SimpleMailMessage` có cần property này không?

`SimpleMailMessage` là abstraction của Spring cho email văn bản thuần:

```java
import org.springframework.mail.SimpleMailMessage;

SimpleMailMessage mail = new SimpleMailMessage();
mail.setFrom("notifications@example.org");
mail.setTo("customer@example.net");
mail.setSubject("Chào mừng");
mail.setText("Xin chào! Tài khoản của bạn đã được kích hoạt.");
mailSender.send(mail);
```

Đối với `JavaMailSenderImpl`, gửi `SimpleMailMessage` cuối cùng vẫn cần biến nội dung thành một thông điệp email phù hợp để vận chuyển. Charset mặc định của sender có liên quan đến đường tạo và gửi MIME ở phía dưới. Tuy nhiên, `SimpleMailMessage` **không cho ứng dụng mô tả rõ cấu trúc multipart hoặc HTML** như `MimeMessageHelper`.

Vì vậy:

- Với email text thuần đơn giản, `SimpleMailMessage` có thể đáp ứng nhu cầu.
- Khi cần kiểm soát encoding tại từng thông điệp, HTML, attachment, display name hay các phần MIME phức tạp, dùng `JavaMailSender` và `MimeMessageHelper`.
- Không nhầm `default-encoding` với khả năng thêm HTML: `SimpleMailMessage` vẫn là API văn bản đơn giản.

## 12. Vì sao cấu hình đúng UTF-8 mà mail vẫn bị lỗi dấu?

Một nguyên nhân quan trọng là **ký tự đã bị hỏng trước khi đưa vào mail sender**.

Giả sử hệ thống đọc một template có byte UTF-8 nhưng sử dụng charset sai:

```text
File template (byte UTF-8 đúng)
     |
     | Đọc bằng charset khác
     v
Java String đã thành "ChÃ o"
     |
     | MIME encode theo UTF-8 (đúng quy trình)
     v
Người nhận thấy "ChÃ o"
```

Ở đây Spring Mail **đã mã hóa đúng chuỗi mà ứng dụng đưa vào**, nhưng chuỗi đó không phải nội dung mong muốn. Đổi property mail sang charset khác thường chỉ che triệu chứng hoặc làm hỏng thêm dữ liệu.

Một ví dụ đọc template đúng charset:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

String template = Files.readString(
        Path.of("templates/welcome.txt"),
        StandardCharsets.UTF_8
);
```

Nếu template nằm trong classpath của ứng dụng đóng gói JAR, nên dùng cơ chế đọc `Resource`/`InputStream` của Spring và giải mã UTF-8 phù hợp, thay vì giả định đường dẫn file hệ điều hành luôn tồn tại.

### Lỗi ở database, API hoặc template

Nguồn dữ liệu có thể đã sai trong:

- Database lưu hoặc trả chuỗi theo bộ mã không phù hợp.
- HTTP API bên ngoài khai báo sai charset hoặc gửi byte không khớp.
- File template được lưu một charset nhưng đọc như charset khác.
- Thành phần sinh HTML chuyển text sang byte rồi lại tạo `String` bằng charset khác.
- Thông điệp được encode trước thành chuỗi base64/quoted-printable và sau đó bị MIME helper mã hóa một lần nữa.

Để tìm nguyên nhân, hãy xác định **lần đầu tiên nội dung bị thay đổi**: nguồn dữ liệu, Java `String`, MIME part, SMTP transport, hay client nhận.

## 13. Các lỗi thường gặp và cách đọc dấu hiệu

| Triệu chứng | Điều có thể đã xảy ra | Hướng kiểm tra |
| --- | --- | --- |
| `ChÃ o` thay vì `Chào` | Byte UTF-8 bị giải mã như bộ mã khác ở một giai đoạn | Nguồn string, charset đọc/ghi và header MIME |
| `Th?ng b?o` hoặc ký tự `�` | Dữ liệu bị thay thế do codec không hỗ trợ hoặc byte sai | Xem nội dung `String` trước khi gửi và encoding ở nguồn |
| `Ch=C3=A0o` xuất hiện trực tiếp | Quoted-printable chưa được giải mã như mong đợi | `Content-Transfer-Encoding` trên đúng MIME text part |
| `SGVsbG8=` xuất hiện như chữ | Base64 bị xem như text hoặc có bước encode thủ công sai | Tránh double encoding; xem raw MIME |
| Chữ trong body đúng, `Subject` bị lỗi | Header encoding khác với body encoding | Cách gọi `setSubject`, raw header và encoded-word |
| Thư HTML hiện nguyên tag | Part là `text/plain` hoặc gọi `setText(html, false)` | Media type/`isHtml` thay vì chỉ charset |
| File PDF đính kèm không mở được | Byte nhị phân bị thay đổi hoặc attachment được tạo sai | Dùng `addAttachment` với byte nguyên vẹn |
| Đã khai báo property nhưng không có tác dụng | Ứng dụng dùng sender tự tạo hoặc helper override encoding | Xem nơi tạo `JavaMailSender` và constructor helper |
| Mail client khác hiển thị khác nhau | MIME thiếu header, charset không khớp hoặc client xử lý khác | Raw MIME của đúng phần và behavior của client |
| Body tiếng Việt OK, tên file có dấu bị sai | Quy tắc mã hóa parameter filename hoặc tương thích client | `Content-Disposition` và thư viện tạo attachment |

### 13.1. Đọc raw MIME đúng vị trí

Một email có attachment thường có header ngoài cùng `Content-Type: multipart/mixed`. Charset **không nhất thiết xuất hiện ở header ngoài cùng**; nó có thể nằm ở `text/plain`/`text/html` part bên trong.

```text
MIME message: multipart/mixed
  |
  +-- text/html; charset=UTF-8
  |     Content-Transfer-Encoding: quoted-printable
  |
  +-- application/pdf
        Content-Transfer-Encoding: base64
```

Khi gặp lỗi dấu:

1. Xác định đúng part chứa văn bản bị lỗi.
2. Kiểm tra `Content-Type` và `charset` trên part ấy.
3. Kiểm tra `Content-Transfer-Encoding` trên **cùng part**.
4. Giải mã transfer encoding để xác định byte văn bản.
5. So sánh byte/chuỗi với nội dung ngay trước khi ứng dụng đưa vào helper.

Đây là **cách hiểu cấu trúc email để chẩn đoán**, không cần tự chỉnh raw MIME trong ứng dụng.

### 13.2. Không sửa MIME bằng cách thay chuỗi

Tránh thao tác kiểu:

```java
// Không phải giải pháp đúng:
// rawMail = rawMail.replace(
//     "charset=ISO-8859-1", "charset=UTF-8");
```

Thay header mà không chuyển byte thật sẽ khiến khai báo và nội dung có thể không còn tương ứng. Tốt hơn là sửa **nguồn sinh byte/chuỗi** hoặc **API được dùng để tạo part**.

### 13.3. Encoding không phải là cơ chế bảo mật

UTF-8 chỉ là bộ mã ký tự. Quoted-printable và base64 là transfer encoding, **không phải mã hóa dữ liệu để giữ bí mật**. Việc dùng `spring.mail.default-encoding=UTF-8` không bảo vệ nội dung khỏi bị đọc trên đường gửi; bảo mật kết nối SMTP phụ thuộc TLS và thiết lập hạ tầng, còn bảo mật đầu cuối là một bài toán khác.

## 14. Những ranh giới quan trọng trong cấu hình Spring Boot

### 14.1. Encoding mặc định không áp dụng cho dữ liệu không phải text

Các dữ liệu như PDF, ảnh PNG, ZIP hay byte nhị phân khác cần được giữ nguyên và mô tả bằng media type phù hợp:

```java
helper.addAttachment(
        "document.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);
```

`spring.mail.default-encoding` không dùng để xác định `application/pdf` và không thay thế `FileTypeMap`, tức cơ chế ánh xạ filename sang MIME media type khi chưa khai báo tường minh.

### 14.2. Encoding mặc định không đặt địa chỉ người nhận

`To`, `Cc` và `Bcc` liên quan đến địa chỉ email và SMTP envelope. Charset của body không quyết định ai nhận được thư. Tên hiển thị chứa Unicode có yêu cầu encoding header riêng, nhưng việc định tuyến vẫn phụ thuộc địa chỉ hợp lệ và chính sách máy chủ.

### 14.3. Encoding mặc định không bảo đảm gửi thành công

SMTP server có thể từ chối đăng nhập, không cấp quyền relay, giới hạn số người nhận, hạn chế kích thước thư hoặc chặn nội dung. Một thông điệp được tạo đúng UTF-8 vẫn có thể bị từ chối hoặc chưa giao đến mailbox.

Kết quả `mailSender.send(...)` hoàn thành không có ngoại lệ chỉ mô tả trạng thái tương tác của ứng dụng với cơ chế gửi ở chặng đó; nó không chứng minh người nhận đã đọc thư.

### 14.4. Encoding mặc định không quyết định charset của mọi dữ liệu đầu vào

Một kết nối database, HTTP client hoặc template engine có thể có cấu hình charset riêng. Property `spring.mail.default-encoding` không tự thay đổi `Files.readString(...)`, JSON parser hay cách một hệ thống khác gửi byte.

## 15. Ví dụ thực hành: email đa ngôn ngữ

Một ứng dụng cần gửi email cho người dùng Việt Nam và một số thị trường quốc tế. Mục tiêu là giữ Unicode end-to-end mà không phải chọn charset riêng cho từng ngôn ngữ.

```yaml
spring:
  mail:
    host: ${SMTP_HOST}
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    default-encoding: UTF-8
    properties:
      "[mail.smtp.auth]": true
      "[mail.smtp.starttls.enable]": true
      "[mail.smtp.starttls.required]": true
```

```java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(message);

helper.setFrom("notifications@example.org", "Bộ phận thông báo");
helper.setTo("customer@example.net");
helper.setSubject("Đơn hàng đã xác nhận");
helper.setText(
        "Xin chào! Đơn hàng của bạn đã được xác nhận.",
        false
);

mailSender.send(message);
```

Ở đây, **UTF-8 làm mặc định cho sender** giúp tránh việc mỗi service cần viết lại tên charset. Ứng dụng cần bảo đảm chuỗi truyền tới helper đã đúng Unicode, còn Jakarta Mail thực hiện mã hóa header/body phù hợp.

Khi gửi phiên bản tiếng Anh:

```java
helper.setSubject("Order confirmed");
helper.setText("Hello! Your order has been confirmed.", false);
```

UTF-8 vẫn phù hợp vì ký tự ASCII cũng có biểu diễn hợp lệ trong UTF-8. Không cần đổi `default-encoding` chỉ vì nội dung không có dấu.

### Nếu tích hợp hệ thống cũ dùng bộ mã khác

Giả sử một nguồn dữ liệu cũ lưu nội dung bằng một charset khác UTF-8. Cách xử lý nên là:

1. Đọc byte nguồn bằng **charset thật của nguồn**.
2. Chuyển thành Java `String` mang đúng các ký tự Unicode.
3. Tạo MIME text part bằng UTF-8 theo default của sender.
4. Đảm bảo header MIME mô tả charset của byte thực tế.

Đừng đổi default encoding của toàn bộ hệ thống mail chỉ để bù cho lỗi giải mã một nguồn dữ liệu. Một giá trị mặc định thống nhất giúp code dễ bảo trì hơn khi ứng dụng phục vụ nhiều ngôn ngữ.

## 16. Câu hỏi kiểm tra hiểu biết

**Câu 1.** `spring.mail.default-encoding=UTF-8` có khiến nội dung `<b>Xin chào</b>` được hiển thị in đậm khi gọi `helper.setText(html, false)` không?

> Không. Charset UTF-8 chỉ mô tả cách mã hóa ký tự. `false` yêu cầu text thuần. Để gửi HTML, cần dùng `helper.setText(html, true)` hoặc phiên bản text/HTML phù hợp.

**Câu 2.** Một file PDF bị hỏng sau khi gửi. Đổi `default-encoding` từ UTF-8 sang charset khác có giải quyết được không?

> Thông thường không. PDF là dữ liệu nhị phân. Cần kiểm tra byte nguồn, MIME part, cách thêm attachment và quá trình transfer encoding; không biến byte PDF thành `String`.

**Câu 3.** Ứng dụng khai báo default UTF-8 trong YAML, nhưng code tự tạo `JavaMailSenderImpl` và không gọi `setDefaultEncoding`. Có thể kết luận sender sẽ dùng property Boot không?

> Không. Khi ứng dụng tự khai báo sender, cần biết chính xác đường cấu hình bean. Property Boot chỉ được áp dụng khi có thành phần tương ứng đọc và gắn nó vào sender.

**Câu 4.** Vì sao Subject có dấu có thể nhìn giống base64 trong raw email dù phần body dùng quoted-printable?

> Vì header chứa ký tự không phải ASCII dùng cú pháp mã hóa header riêng, chẳng hạn encoded-word, còn body dùng `Content-Transfer-Encoding` của MIME part. Hai cơ chế có thể chọn cách biểu diễn khác nhau.

**Câu 5.** Nếu Java `String` đã có nội dung `ChÃ o` trước khi gọi `send()`, chỉnh `spring.mail.default-encoding` có sửa lại `Chào` không?

> Không. Cần sửa bước đọc hoặc giải mã nguồn dữ liệu. Mail sender có thể mã hóa chính xác một chuỗi Unicode đã sai từ trước, nhưng không suy ra được nội dung người dùng ban đầu muốn gửi.

## 17. Quy tắc ghi nhớ

| Mục tiêu | Thiết lập hoặc API phù hợp | Điều cần nhớ |
| --- | --- | --- |
| Dùng UTF-8 mặc định trong Spring Boot Mail | `spring.mail.default-encoding=UTF-8` | Mặc định cho sender Boot cấu hình |
| Tự cấu hình `JavaMailSenderImpl` | `sender.setDefaultEncoding("UTF-8")` | Phải tự quản lý cấu hình sender |
| Tạo text/HTML kế thừa default | `new MimeMessageHelper(message)` hoặc constructor multipart không chỉ định charset | Message nên được tạo qua `mailSender.createMimeMessage()` |
| Cần charset tường minh cho một helper | `new MimeMessageHelper(message, true, "UTF-8")` | Override tại nơi tạo nội dung |
| Chọn text hay HTML | `helper.setText(text, false/true)` | `Content-Type` khác với charset |
| Gửi cả text và HTML | `helper.setText(plain, html)` trên helper multipart | Hai bản diễn đạt cùng thông điệp |
| Gửi PDF hoặc ảnh | `helper.addAttachment(...)` / `addInline(...)` | Kiểu nội dung và byte file khác charset của text |
| Lỗi dấu chỉ ở Subject | Xem header encoding, `setSubject(...)` | Body charset không mô tả toàn bộ header |
| Dữ liệu đã bị sai trước khi tạo message | Sửa bước đọc từ template/database/API | Email encoding không khôi phục dữ liệu đã mất |

**`spring.mail.default-encoding` quy định một charset mặc định cho đường tạo MIME message trong Spring Boot Mail.** Với ứng dụng tiếng Việt và đa ngôn ngữ, `UTF-8` là lựa chọn phù hợp. Để email hiển thị đúng, ứng dụng cần đồng thời giữ dữ liệu đầu vào đúng Unicode, đặt đúng `Content-Type` cho từng phần, không tự làm hỏng byte attachment và để thư viện tạo MIME headers/transfer encoding theo đúng cấu trúc.
