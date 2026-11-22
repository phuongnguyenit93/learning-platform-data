# Xử lý thứ tự add inline và set text

Trong **Spring Framework Mail**, `MimeMessageHelper` giúp tạo email HTML, chèn ảnh hiển thị ngay trong nội dung và gửi tệp đính kèm mà không cần tự lắp từng phần MIME. Tuy nhiên, một lỗi phổ biến là **gọi `addInline(...)` trước `setText(...)`**. Email có thể vẫn được gửi thành công, nhưng hình ảnh tham chiếu bằng `cid:...` lại không hiển thị ở một số ứng dụng đọc thư, hoặc hiển thị như tệp đính kèm.

Quy tắc thực hành quan trọng nhất là:

> **Tạo nội dung thư bằng `helper.setText(...)` trước; sau đó mới thêm mọi tài nguyên inline bằng `helper.addInline(...)`.**

Đây cũng là thứ tự được tài liệu API của Spring lưu ý vì việc tạo lại cấu trúc body có thể ảnh hưởng tới cách một số mail client phân giải tài nguyên liên quan. Bài học giải thích nguyên nhân, cách dùng đúng với email HTML hoặc HTML có bản text thuần, cách thêm nhiều ảnh và attachment, cùng phương pháp chẩn đoán khi đã tuân thủ thứ tự nhưng hình ảnh vẫn không hiển thị.

## 1. Bài toán: một email HTML có logo trong body

Giả sử hệ thống gửi email chào mừng:

```html
<!DOCTYPE html>
<html lang="vi">
  <body>
    <img
      src="cid:company-logo"
      alt="Logo công ty"
      width="160"
    >
    <h1>Chào mừng bạn!</h1>
    <p>Tài khoản của bạn đã được tạo thành công.</p>
  </body>
</html>
```

Đoạn HTML này không chứa trực tiếp dữ liệu hình ảnh. Giá trị `cid:company-logo` có nghĩa: **hãy tìm một phần MIME của email có `Content-ID` tương ứng với `company-logo`** và hiển thị dữ liệu ảnh của phần đó.

Một MIME part chứa logo có thể mang các header tương tự:

```text
Content-Type: image/png
Content-ID: <company-logo>
Content-Disposition: inline; filename="logo.png"
Content-Transfer-Encoding: base64

[noi dung anh PNG da duoc ma hoa de truyen]
```

Hai thành phần phải khớp:

| Vị trí | Giá trị |
|---|---|
| HTML | `src="cid:company-logo"` |
| MIME header | `Content-ID: <company-logo>` |
| Java API | `helper.addInline("company-logo", resource, "image/png")` |

Chuỗi `company-logo` trong `addInline(...)` là **Content-ID**, không phải tên tệp, đường dẫn, tên biến Java hay `Message-ID` của toàn bộ thư.

Tham chiếu `cid:...` khác `src="https://cdn.example.com/logo.png"`. Với URL ngoài, mail client có thể cần tải ảnh từ máy chủ web. Với CID, ảnh được gói **bên trong email** và có thể được mail client dùng để hiển thị HTML, tùy khả năng hỗ trợ và chính sách hiển thị của nó.

## 2. setText(...) và addInline(...) làm hai việc khác nhau

### 2.1. setText(...) tạo nội dung gốc

`MimeMessageHelper` cung cấp một số cách đặt nội dung:

```java
// Văn bản thuần:
helper.setText("Xin chào!");

// Chỉ HTML:
helper.setText("<p>Xin chào!</p>", true);

// Cùng nội dung ở hai phiên bản:
helper.setText(
    "Xin chào! Hãy xác nhận tài khoản của bạn.",
    "<p>Xin chào! <strong>Hãy xác nhận tài khoản của bạn.</strong></p>"
);
```

Ý nghĩa:

- `setText(String)` đặt nội dung văn bản thuần.
- `setText(String, boolean)` cho phép xác định nội dung là HTML khi tham số thứ hai là `true`.
- `setText(String plainText, String htmlText)` tạo **hai bản thay thế** của cùng nội dung, thường trong `multipart/alternative`.

Các thao tác này có thể thiết lập hoặc cập nhật phần nội dung gốc và cấu trúc các body part MIME. Khi kết hợp với inline resource, thứ tự xây dựng các part vì vậy có ý nghĩa thực tế.

### 2.2. addInline(...) thêm tài nguyên liên quan

Ví dụ:

```java
helper.addInline(
    "company-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
```

Lệnh này thêm một part chứa ảnh và gắn `Content-ID` để HTML tham chiếu. `MimeMessageHelper` và Jakarta Mail đảm nhiệm việc biểu diễn dữ liệu nhị phân thành nội dung MIME phù hợp.

Một số overload của `addInline(...)` cho phép truyền:

- `File` khi ảnh nằm trên hệ thống tệp;
- `Resource` hoặc `InputStreamSource` khi ảnh được đọc từ classpath, byte array hay nguồn dữ liệu khác;
- `contentType` khi cần chỉ định kiểu MIME rõ ràng.

Để nhúng ảnh nội dung vào HTML, **cả nội dung HTML lẫn part inline đều cần tồn tại và được liên kết bằng CID**. Chỉ gọi `addInline(...)` không khiến hình ảnh tự xuất hiện trên màn hình.

### 2.3. Vì sao setText phải được gọi trước?

Hãy hình dung `MimeMessageHelper` đang xây dựng một cây MIME. Khi gọi `setText(...)`, helper thiết lập phần nội dung gốc, có thể tạo `text/html`, `text/plain` hoặc nhóm `multipart/alternative`. Khi gọi `addInline(...)`, helper bổ sung part ảnh liên quan vào nhóm MIME thích hợp.

Nếu thêm ảnh trước rồi **sau đó mới dựng lại body bằng `setText(...)`**, một số ứng dụng đọc thư có thể gặp khó khăn khi xác định đâu là nội dung gốc, đâu là resource liên quan hoặc cách phân giải các phần trong cấu trúc đã tạo.

Vì vậy, **Spring khuyến nghị `addInline(...)` được gọi sau `setText(...)`**. Không cần giả định thứ tự sai luôn gây exception hoặc luôn làm mất part ảnh; sự cố thường biểu hiện ở **cách mail client hiển thị** sau khi email đã được gửi.

## 3. So sánh mã sai và mã đúng

### 3.1. Thứ tự không nên dùng

```java
MimeMessage mimeMessage = mailSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(mimeMessage, true, "UTF-8");

helper.setTo("alice@example.net");
helper.setSubject("Chào mừng bạn");

// Không nên thêm inline trước khi tạo HTML body:
helper.addInline(
    "company-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

String html = """
    <html><body>
      <img src="cid:company-logo" alt="Logo">
      <p>Xin chào!</p>
    </body></html>
    """;

helper.setText(html, true);
mailSender.send(mimeMessage);
```

Vấn đề **không nằm ở câu lệnh SMTP** hay việc ID của ảnh sai (ở ví dụ trên hai ID khớp nhau). Vấn đề là thứ tự thao tác trên MIME body: resource được thêm trước khi body chính được hoàn thiện.

Mã như vậy có thể hoạt động trên một số client nhưng hiển thị lỗi trên client khác. Không nên dùng việc “chạy được trên máy tôi” làm bằng chứng thứ tự tạo MIME đã an toàn với mọi trình đọc thư.

### 3.2. Thứ tự khuyến nghị

```java
MimeMessage mimeMessage = mailSender.createMimeMessage();
MimeMessageHelper helper =
    new MimeMessageHelper(mimeMessage, true, "UTF-8");

helper.setFrom("no-reply@example.com");
helper.setTo("alice@example.net");
helper.setSubject("Chào mừng bạn");

String html = """
    <html><body>
      <img src="cid:company-logo" alt="Logo">
      <p>Xin chào!</p>
    </body></html>
    """;

// 1. Thiết lập nội dung gốc.
helper.setText(html, true);

// 2. Thêm tài nguyên mà nội dung HTML tham chiếu.
helper.addInline(
    "company-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

// 3. Gửi sau khi hoàn thiện các part.
mailSender.send(mimeMessage);
```

Thứ tự nên tuân theo luồng sau:

```text
createMimeMessage()
       |
       v
new MimeMessageHelper(... multipart ...)
       |
       v
setFrom / setTo / setSubject / setReplyTo
       |
       v
Tạo hoặc render nội dung HTML
       |
       v
setText(plainText, htmlText)
hoặc setText(htmlText, true)
       |
       v
addInline(cid1, resource1, type1)
       |
       v
addInline(cid2, resource2, type2)
       |
       v
addAttachment(...) nếu có
       |
       v
JavaMailSender.send(mimeMessage)
```

Các header cơ bản như `From`, `To`, `Subject` không nhất thiết phải được đặt đúng theo một thứ tự cố định với nhau. **Quan hệ thứ tự cần ghi nhớ là: `setText` trước `addInline`; hoàn thiện MIME trước khi gửi.**

## 4. Ví dụ Spring Boot hoàn chỉnh: HTML + plain text + ảnh inline

Ví dụ dưới đây sử dụng **Spring Boot 3.x, Spring Framework 6.x và Java 17+**. Với Spring Framework 6, các đối tượng email dùng namespace `jakarta.mail`.

### 4.1. Dependency

Nếu dùng Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

Starter cung cấp khả năng tự cấu hình `JavaMailSender` cho trường hợp dùng SMTP thông thường, khi cấu hình `spring.mail.*` phù hợp.

### 4.2. Cấu hình SMTP

`application.yml` minh họa cổng 587 và STARTTLS:

```yaml
spring:
  mail:
    host: smtp.example.com
    port: 587
    username: ${SMTP_USERNAME}
    password: ${SMTP_PASSWORD}
    properties:
      mail:
        smtp:
          auth: true
          starttls:
            enable: true
            required: true
          connectiontimeout: 5000
          timeout: 5000
          writetimeout: 5000
```

Hai biến `SMTP_USERNAME` và `SMTP_PASSWORD` được cấp từ môi trường/secret store, không commit credential thật vào repository. Cổng và cơ chế TLS phải tuân theo tài liệu của SMTP provider.

### 4.3. Đặt logo trong resources

Cấu trúc dự án:

```text
src/main/
├── java/com/example/mail/WelcomeMailService.java
└── resources/
    ├── application.yml
    └── mail/
        └── logo.png
```

`ClassPathResource("mail/logo.png")` phù hợp khi logo được đóng gói bên trong JAR. Không nên dùng đường dẫn tuyệt đối đến thư mục source trên máy developer.

### 4.4. Service gửi mail

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.springframework.web.util.HtmlUtils;

@Service
public class WelcomeMailService {

    private static final String LOGO_CID = "company-logo";

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient, String displayName)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        // Multipart cho phép dùng inline image và text/html.
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            "UTF-8"
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn");

        String safeName = HtmlUtils.htmlEscape(displayName);

        String plainText =
            "Xin chào " + displayName
            + ",\nChào mừng bạn đến với ứng dụng.";

        String htmlText = """
            <!DOCTYPE html>
            <html lang="vi">
              <body>
                <img src="cid:company-logo"
                     alt="Logo công ty"
                     width="160"
                     style="display:block;border:0">
                <h1>Xin chào, %s!</h1>
                <p>Chào mừng bạn đến với ứng dụng.</p>
              </body>
            </html>
            """.formatted(safeName);

        // BƯỚC 1: Tạo text/plain và text/html.
        helper.setText(plainText, htmlText);

        // BƯỚC 2: Chỉ thêm inline sau setText.
        Resource logo = new ClassPathResource("mail/logo.png");
        helper.addInline(LOGO_CID, logo, "image/png");

        // BƯỚC 3: Gửi thông điệp đã chuẩn bị xong.
        mailSender.send(message);
    }
}
```

Trong ví dụ:

1. `MimeMessage` chứa nội dung/header email và các cấu trúc MIME.
2. `MULTIPART_MODE_RELATED` yêu cầu helper dùng nhóm `multipart/related` cho HTML và resource phụ thuộc.
3. `setText(plainText, htmlText)` tạo hai phiên bản nội dung, trong đó HTML tham chiếu `cid:company-logo`.
4. `addInline(LOGO_CID, logo, "image/png")` tạo part ảnh với Content-ID tương ứng.
5. `ClassPathResource` cung cấp dữ liệu logo và có thể đọc khi ứng dụng đóng gói JAR.
6. `mailSender.send(message)` chuyển thư cho SMTP server; sự thành công của lời gọi chưa chứng minh thư đã vào Inbox.

**Dữ liệu người dùng xuất hiện trong HTML nên được escape.** `HtmlUtils.htmlEscape(displayName)` tránh chèn trực tiếp ký tự đặc biệt vào HTML. Với nhiều mẫu phức tạp, dùng template engine hỗ trợ escape phù hợp và render xong trước khi gọi `setText(...)`.

## 5. Tại sao phải chọn chế độ multipart?

Một constructor `MimeMessageHelper` không bật multipart có thể phù hợp để gửi văn bản thuần hoặc HTML đơn giản, nhưng **không phù hợp khi muốn thêm resource inline qua `addInline(...)`**.

Ví dụ chỉ có text:

```java
MimeMessageHelper helper =
    new MimeMessageHelper(message, "UTF-8");

helper.setText("Xin chào!");
```

Ví dụ cần inline:

```java
MimeMessageHelper helper =
    new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
    );
```

Hoặc có thể dùng constructor:

```java
MimeMessageHelper helper =
    new MimeMessageHelper(message, true, "UTF-8");
```

Trong Spring, constructor với `multipart=true` dùng chế độ multipart mặc định thích hợp với các trường hợp thường gặp, bao gồm hỗ trợ cả resource inline lẫn attachment. Nếu muốn xác định rõ cấu trúc MIME trong mã, có thể truyền hằng số mode.

Các mode cần phân biệt:

| Chế độ | Cấu trúc chính | Trường hợp |
|---|---|---|
| `MULTIPART_MODE_NO` | Không dùng multipart | Email text/plain hoặc HTML đơn giản không cần inline/attachment. |
| `MULTIPART_MODE_RELATED` | `multipart/related` | HTML có các tài nguyên inline như logo, banner. |
| `MULTIPART_MODE_MIXED` | `multipart/mixed` | Nhiều phần được gộp chung; tùy client, kém phù hợp hơn cho quan hệ HTML-inline phức tạp. |
| `MULTIPART_MODE_MIXED_RELATED` | `multipart/mixed` bao ngoài `multipart/related` | Email có HTML/inline và attachment độc lập. |

**Bật multipart là điều kiện cần, không thay thế việc gọi `setText` trước `addInline`.**

## 6. MIME tree giải thích vấn đề thứ tự

### 6.1. Chỉ HTML và logo

Cấu trúc mong muốn có thể hình dung:

```text
MimeMessage
└── multipart/related
    ├── text/html
    │   └── <img src="cid:company-logo">
    └── image/png
        ├── Content-ID: <company-logo>
        └── Content-Disposition: inline
```

Ở đây, HTML đóng vai trò **nội dung gốc**; ảnh PNG là tài nguyên có liên quan. `multipart/related` giúp mail client hiểu rằng ảnh phục vụ hiển thị nội dung HTML.

### 6.2. HTML, text thuần và logo

Nếu dùng `helper.setText(plainText, htmlText)`:

```text
MimeMessage
└── multipart/related
    ├── multipart/alternative
    │   ├── text/plain
    │   └── text/html
    │       └── <img src="cid:company-logo">
    └── image/png
        └── Content-ID: <company-logo>
```

`multipart/alternative` chứa hai **cách trình bày cùng một nội dung**. `multipart/related` liên kết nội dung có HTML với ảnh. Một mail client hỗ trợ HTML có thể chọn `text/html`, còn client thích văn bản thuần có thể dùng `text/plain`.

### 6.3. Có thêm tệp PDF đính kèm

Khi vừa có logo inline vừa có hóa đơn PDF:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html
    │   │       └── <img src="cid:company-logo">
    │   └── image/png
    │       └── Content-ID: <company-logo>
    └── application/pdf
        └── Content-Disposition: attachment
```

Với kiểu này, có thể dùng `MULTIPART_MODE_MIXED_RELATED` và tuân thủ thứ tự:

```text
setText(plainText, htmlText)
     ↓
addInline("company-logo", logo, "image/png")
     ↓
addAttachment("invoice.pdf", pdf, "application/pdf")
     ↓
send(...)
```

Thực chất `addAttachment(...)` và `addInline(...)` có mục đích khác nhau: attachment là thành phần độc lập để tải/mở, trong khi inline được HTML tham chiếu để hiển thị. **Không dùng `addAttachment(...)` để thay thế `addInline(...)` cho ảnh CID.**

## 7. Ví dụ HTML + logo inline + PDF attachment

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class InvoiceMailService {

    private final JavaMailSender mailSender;

    public InvoiceMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(
            String recipient, byte[] invoicePdf) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8"
        );

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn của bạn");

        String plain = "Hóa đơn PDF của bạn nằm trong tệp đính kèm.";
        String html = """
            <html>
              <body>
                <img src="cid:invoice-logo" alt="Logo" width="120">
                <p>Hóa đơn PDF của bạn nằm trong tệp đính kèm.</p>
              </body>
            </html>
            """;

        // 1. Tạo nội dung trước.
        helper.setText(plain, html);

        // 2. Tạo ảnh liên quan tới HTML.
        helper.addInline(
            "invoice-logo",
            new ClassPathResource("mail/logo.png"),
            "image/png"
        );

        // 3. Thêm attachment độc lập.
        helper.addAttachment(
            "hoa-don.pdf",
            new ByteArrayResource(invoicePdf),
            "application/pdf"
        );

        mailSender.send(message);
    }
}
```

`invoicePdf` là mảng byte của PDF được sinh từ nghiệp vụ khác. Không nên đưa file quá lớn vào bộ nhớ mà không xem giới hạn dung lượng thư, khả năng tải và điều kiện của SMTP provider. MIME thường mã hóa dữ liệu nhị phân để truyền, làm kích thước thư tăng so với tệp gốc.

## 8. Nhiều ảnh inline: đặt toàn bộ text trước mọi addInline

Một email marketing hoặc thông báo đẹp có thể có logo, biểu đồ và banner:

```html
<!DOCTYPE html>
<html lang="vi">
  <body>
    <img src="cid:brand-logo" alt="Logo" width="140">
    <h1>Báo cáo hoạt động</h1>
    <p>Đây là thông tin tổng hợp mới nhất.</p>
    <img src="cid:weekly-chart" alt="Biểu đồ hoạt động" width="480">
    <img src="cid:footer-banner" alt="Liên hệ hỗ trợ" width="480">
  </body>
</html>
```

Code tương ứng:

```java
helper.setText(plainText, htmlText);

helper.addInline(
    "brand-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

helper.addInline(
    "weekly-chart",
    new ByteArrayResource(chartPngBytes),
    "image/png"
);

helper.addInline(
    "footer-banner",
    new ClassPathResource("mail/footer.jpg"),
    "image/jpeg"
);

mailSender.send(message);
```

Không có quy tắc rằng phải gọi một `setText(...)` trước **mỗi** `addInline(...)`. Thông thường, **gọi setText một lần để hoàn thiện body**, rồi thêm lần lượt các inline part với CID riêng.

Điều cần giữ đúng:

- Mỗi `cid:...` trong HTML có một part tương ứng.
- Content-ID của các ảnh khác nhau không được va chạm trong thông điệp.
- `image/png`, `image/jpeg` phải phản ánh đúng dữ liệu.
- Không chỉnh sửa lại body HTML sau khi bắt đầu thêm inline nếu không có lý do và hiểu rõ cấu trúc MIME.
- Dữ liệu ảnh đến từ resource có thể đọc được khi Jakarta Mail cần sử dụng.

## 9. Render template trước khi gọi setText

Với ứng dụng có nhiều mẫu email, phần HTML nên được tạo trước bằng template engine như **Thymeleaf** hoặc **FreeMarker**. Ví dụ theo luồng:

```text
Dữ liệu nghiệp vụ
        |
        v
Template engine -> HTML hoàn chỉnh có cid:company-logo
        |
        v
helper.setText(plainText, htmlText)
        |
        v
helper.addInline("company-logo", imageResource, "image/png")
        |
        v
mailSender.send(message)
```

Pseudo-flow trong Java:

```java
// renderHtml(...) là hàm ứng dụng tự cài đặt bằng template engine.
String html = renderHtml(templateData);
String plain = renderPlainText(templateData);

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
    message,
    MimeMessageHelper.MULTIPART_MODE_RELATED,
    "UTF-8"
);

helper.setFrom("no-reply@example.com");
helper.setTo(recipient);
helper.setSubject("Thông báo");

helper.setText(plain, html); // Hoàn tất body.
helper.addInline("company-logo", logoResource, "image/png");

mailSender.send(message);
```

**Không nên** render một phần HTML, gọi `setText(...)`, thêm ảnh, rồi tiếp tục gọi `setText(...)` với HTML mới chứa những thay đổi. Lần gọi sau có thể cập nhật/tái tạo body và khiến cấu trúc MIME khó dự đoán đối với các mail client.

Nếu cần quyết định có bao nhiêu ảnh trước khi render, hãy xử lý ở tầng template data, dựng HTML và danh sách tài nguyên, sau đó **setText một lần rồi addInline toàn bộ danh sách**.

Ví dụ mô hình đối tượng:

```java
record InlineAsset(
    String cid,
    org.springframework.core.io.Resource resource,
    String contentType
) {}
```

Luồng xây dựng:

```java
String html = renderHtml(data);
helper.setText(plainText, html);

for (InlineAsset asset : inlineAssets) {
    helper.addInline(
        asset.cid(),
        asset.resource(),
        asset.contentType()
    );
}
```

Đảm bảo `inlineAssets` được lấy từ nguồn đáng tin cậy, CID hợp lệ và được HTML tham chiếu đúng; không cho phép dữ liệu đầu vào tùy ý chỉ định đường dẫn file nhạy cảm trên máy chủ.

## 10. Resource nào phù hợp để dùng với addInline?

`MimeMessageHelper.addInline(...)` nhận nguồn dữ liệu ảnh dưới nhiều dạng. Chọn nguồn phù hợp với nơi ảnh được tạo và khả năng đọc lại.

| Nguồn | Ví dụ | Khi sử dụng |
|---|---|---|
| `ClassPathResource` | `new ClassPathResource("mail/logo.png")` | Ảnh tĩnh trong JAR/resources. |
| `FileSystemResource` | `new FileSystemResource(file)` | File nằm trên hệ thống tệp và ứng dụng có quyền đọc. |
| `ByteArrayResource` | `new ByteArrayResource(imageBytes)` | Ảnh được tạo động hoặc tải về và lưu trong mảng byte. |
| `InputStreamSource` tùy biến | Nguồn mở stream mới khi đọc | Ảnh được cung cấp từ storage hoặc nguồn streaming có thể đọc nhiều lần. |

### 10.1. Resource phải có khả năng mở stream mới

Jakarta Mail có thể cần đọc lại dữ liệu khi tính toán hoặc truyền MIME. Vì vậy một `InputStreamSource` dùng với `addInline(...)` nên trả về **một `InputStream` mới mỗi lần `getInputStream()` được gọi**.

`ClassPathResource`, `FileSystemResource` và `ByteArrayResource` thường phù hợp với yêu cầu này.

Tránh bọc một input stream dùng một lần thành `InputStreamResource` rồi cho rằng thư viện có thể đọc lại vô hạn:

```java
// Cần thận trọng: stream này có thể chỉ đọc được một lần.
InputStream stream = storage.open("mail/logo.png");
InputStreamResource resource = new InputStreamResource(stream);
helper.addInline("company-logo", resource, "image/png");
```

Nếu ảnh nhỏ và không có nguồn mở stream lại, có thể tải dữ liệu vào byte array trước khi gửi:

```java
byte[] imageBytes = storage.loadBytes("mail/logo.png");
helper.setText(plainText, htmlText);
helper.addInline(
    "company-logo",
    new ByteArrayResource(imageBytes),
    "image/png"
);
```

`storage.loadBytes(...)` là một hàm minh họa do ứng dụng tự triển khai. Không nên đọc ảnh quá lớn vào RAM mà không giới hạn kích thước.

### 10.2. Content-Type phải đúng

Ví dụ:

```java
helper.addInline("logo", pngResource, "image/png");
helper.addInline("banner", jpegResource, "image/jpeg");
```

Không dùng `image/png` cho tệp JPEG chỉ vì code mẫu ban đầu dùng PNG. Mail client có thể dựa vào header MIME và nội dung để quyết định cách hiển thị; metadata sai làm tăng nguy cơ ảnh lỗi.

### 10.3. Tên resource không phải Content-ID

Giả sử file là `mail/logo-company-2026.png`. Bạn vẫn có thể dùng:

```java
helper.addInline(
    "header-logo",
    new ClassPathResource("mail/logo-company-2026.png"),
    "image/png"
);
```

Trong HTML cần `src="cid:header-logo"`, không phải `cid:logo-company-2026.png`, trừ khi bạn chủ động dùng đúng chuỗi đó làm CID. **Tên file và CID là hai định danh độc lập.**

## 11. Những lỗi thường thấy khi thứ tự bị sai hoặc MIME thiếu nhất quán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Email gửi thành công nhưng ảnh không hiển thị | `addInline` chạy trước `setText`; MIME tree không như dự định | Tạo body trước, rồi thêm inline; xem raw MIME thực nhận. |
| Hiện biểu tượng ảnh lỗi | `cid:...` không khớp `Content-ID` | Đối chiếu ID trong HTML với tham số đầu của `addInline`. |
| Ảnh chỉ hiện như attachment | Mode multipart chưa phù hợp hoặc mail client diễn giải khác | Dùng `MULTIPART_MODE_RELATED` hoặc `MIXED_RELATED`, đối chiếu Content-ID và MIME nesting. |
| Chỉ thấy chữ, không thấy HTML | `setText(html)` không bật cờ HTML hoặc dùng overload sai | Dùng `setText(html, true)` hoặc `setText(plain, html)`. |
| Lỗi khi addInline | Helper được tạo ở chế độ non-multipart | Tạo helper với multipart enabled. |
| Lỗi đọc ảnh khi gửi | Resource không tồn tại, stream đã bị đọc hết, không có quyền đọc | Dùng resource phù hợp, bảo đảm có thể mở stream mới. |
| Ảnh chỉ lỗi khi chạy bằng JAR | Dùng đường dẫn local/source thay vì classpath | Đưa ảnh vào resources và dùng `ClassPathResource`. |
| Ảnh bị lặp/nhầm ảnh | Trùng CID giữa các part hoặc sử dụng cùng tham chiếu | Đặt CID duy nhất cho từng tài nguyên, tham chiếu đúng. |
| Ảnh bị chặn ở một số mail client | Chính sách email client hoặc định dạng/CSS chưa được hỗ trợ | Dùng PNG/JPEG, HTML đơn giản, `alt` và bản text thuần. |
| MIME body có vẻ bị thay đổi | Gọi `setText(...)` thêm lần nữa sau `addInline(...)` | Hoàn thiện HTML trước, rồi setText một lần và thêm các inline. |
| Ảnh không xuất hiện trên thư đã forward | Client nhận/forward thay đổi MIME structure | Kiểm tra raw source của bản forward; không giả định cấu trúc sẽ được giữ nguyên. |

**Lỗi thứ tự không nhất thiết ném exception.** Đây là lý do cần hiểu MIME source của email đã nhận, chứ không chỉ kiểm tra lời gọi `send(...)` có báo lỗi hay không.

## 12. Cách đọc raw MIME để chẩn đoán

Khi cần xác định vì sao ảnh inline không render, hãy mở tính năng “Show original”, “View source”, “View raw message” hoặc chức năng tương ứng của mail client.

Một cấu trúc **minh họa** có thể trông như sau (đã rút gọn Base64):

```text
From: no-reply@example.com
To: alice@example.net
Subject: Chao mung
MIME-Version: 1.0
Content-Type: multipart/related; boundary="rel-001"

--rel-001
Content-Type: text/html; charset=UTF-8

<html>
  <body>
    <img src="cid:company-logo" alt="Logo">
    <p>Xin chao!</p>
  </body>
</html>

--rel-001
Content-Type: image/png
Content-ID: <company-logo>
Content-Disposition: inline
Content-Transfer-Encoding: base64

[BASE64_PNG_DATA]

--rel-001--
```

Cách đọc:

1. `Content-Type: multipart/related` nói rằng các phần có quan hệ.
2. `boundary="rel-001"` là chuỗi phân tách các part của thư; thư viện tự tạo boundary phù hợp.
3. Phần `text/html` có `src="cid:company-logo"`.
4. Phần ảnh có `Content-ID: <company-logo>` tương ứng.
5. `Content-Disposition: inline` gợi ý phần ảnh được dùng trong body.
6. Dữ liệu Base64 là nội dung được mã hóa để truyền, **không phải cơ chế bảo mật**.

Thông điệp MIME thực tế có các yêu cầu chặt chẽ về CRLF, header encoding, content-transfer-encoding và boundary. Hãy để Jakarta Mail tạo các phần đó; không nên nối chuỗi MIME thủ công theo ví dụ minh họa.

**Các bước khoanh vùng:**

- **Không thấy part ảnh:** kiểm tra `addInline` có thực sự được gọi, resource có tồn tại và code có gọi `setText` lại sau khi thêm ảnh không.
- **Có part ảnh nhưng CID khác:** sửa đúng tham số `addInline` hoặc giá trị `cid:` trong HTML.
- **CID đúng nhưng cấu trúc lồng không phù hợp:** dùng mode multipart phù hợp và thứ tự `setText` trước `addInline`.
- **MIME đúng nhưng chỉ một client lỗi:** cân nhắc giới hạn hiển thị, định dạng ảnh, HTML/CSS và chính sách của mail client.
- **Tất cả client đều lỗi:** xem cả MIME source lẫn exception ở bước chuẩn bị/gửi và dữ liệu ảnh thật.

## 13. Phân biệt lỗi xây MIME và lỗi SMTP

Có hai nhóm lỗi thường bị gộp chung:

**Lỗi xây MIME / hiển thị:**

- `setText(...)`, `addInline(...)` hoặc `addAttachment(...)` được dùng không đúng thứ tự/kiểu.
- Sai CID hoặc Content-Type.
- Resource không mở được.
- Cấu trúc `multipart/related`, `alternative`, `mixed` không như dự định.
- Mail client không render tài nguyên theo cách mong đợi.

**Lỗi transport hoặc giao hàng:**

- Không kết nối được SMTP host hoặc sai cổng/TLS.
- SMTP AUTH thất bại.
- Server từ chối sender/recipient.
- Server từ chối thông điệp vì kích thước hoặc chính sách nội dung.
- Thư bị bounce hoặc chặn ở chặng sau khi server đã tiếp nhận.

Không nên khắc phục ảnh không hiển thị bằng cách thay password SMTP nếu thư đã được nhận và có đầy đủ MIME parts. Ngược lại, thứ tự `setText`/`addInline` không giải quyết lỗi kết nối từ chối cổng SMTP.

Ứng dụng có thể gặp `MessagingException` trong quá trình chuẩn bị MIME hoặc `MailException` từ Spring Mail khi gửi. Ngay cả khi không có exception, mail client vẫn có thể hiển thị không như mong muốn.

## 14. Những ngộ nhận thường gặp

### “Có CID đúng thì thứ tự addInline và setText không quan trọng”

**Không đúng.** CID là liên kết giữa HTML và ảnh, còn `setText(...)` quyết định body và cấu trúc MIME tương ứng. Spring khuyến nghị thêm inline **sau** khi thiết lập text để tránh sự khác biệt khi client phân giải part liên quan.

### “addInline tự chèn thẻ img vào HTML”

**Không.** `addInline(...)` chỉ thêm resource. HTML phải tự có `src="cid:..."` tương ứng.

### “setText(html) là đủ để gửi HTML”

Khi dùng `setText(String)`, nội dung có thể được xem là **text/plain**. Hãy dùng `setText(html, true)` hoặc `setText(plain, html)` khi cần HTML.

### “Email có logo thì bắt buộc dùng addAttachment”

**Không.** Logo nằm trong body cần `addInline(...)`. PDF cho người dùng tải về thường dùng `addAttachment(...)`.

### “Phải gọi setText một lần cho mỗi ảnh inline”

**Không.** Thường chỉ cần tạo nội dung hoàn chỉnh một lần, sau đó gọi `addInline(...)` cho từng ảnh với CID riêng.

### “Có thể dùng đường dẫn file trong src của img”

`src="C:\projects\mail\logo.png"` hoặc `src="/static/logo.png"` không có nghĩa đối với hộp thư nhận. Để nhúng ảnh, dùng CID và MIME part, hoặc dùng một URL HTTPS ngoài nếu chọn cơ chế ảnh tải từ mạng.

### “Base64 data URI luôn là cách đơn giản hơn CID”

Không nên giả định. Nhiều email client hạn chế hoặc không hỗ trợ đầy đủ `data:` URI trong HTML. Với ảnh nằm trong thư, `multipart/related` và CID là cơ chế MIME rõ ràng hơn.

### “Mọi mail client đều ẩn ảnh inline khỏi danh sách attachment”

Không. Một số client có thể hiển thị logo như attachment dù ảnh cũng render trong body. Nếu CID và cấu trúc MIME đã đúng, đó có thể là khác biệt giao diện của mail client.

### “Gửi không ném exception nghĩa là logo chắc chắn hiện”

Không. `send(...)` là thao tác chuyển phát ở tầng ứng dụng/SMTP. Việc render HTML là trách nhiệm của mail client nhận thư.

## 15. Những tình huống cần xử lý cẩn thận

### 15.1. Thay đổi template hoặc ngôn ngữ sau khi thêm ảnh

Giả sử service gọi:

```java
helper.setText(htmlVi, true);
helper.addInline("company-logo", logo, "image/png");

// Sau đó phát hiện người nhận thích tiếng Anh:
helper.setText(htmlEn, true);
```

Đây là thiết kế dễ lỗi vì body bị cập nhật sau khi inline đã được thêm. Hãy quyết định ngôn ngữ/render template **trước**:

```java
String html = language.equals("en") ? htmlEn : htmlVi;
helper.setText(html, true);
helper.addInline("company-logo", logo, "image/png");
```

Nếu hệ thống có nhiều điều kiện tạo template, tổ chức thành các bước “chọn template → render → setText → addInline → send”.

### 15.2. Một phần ảnh có thể bị thiếu vì dữ liệu nghiệp vụ

Ví dụ email tùy chọn banner. Không nên viết HTML luôn có `cid:promo-banner` rồi bỏ qua `addInline` khi không có ảnh.

Giải pháp: dựng HTML theo danh sách tài nguyên thực sự sẵn có; chỉ thêm thẻ `img` với CID nếu thực sự có resource tương ứng. Sau khi render xong, gọi `setText` và thêm đúng các inline assets được sử dụng.

### 15.3. Cùng một mẫu gửi tới nhiều người

Có thể tái sử dụng **template** và **resource logo**, nhưng nên tạo `MimeMessage` riêng cho mỗi thư cá nhân hóa. Không để nhiều worker cùng sửa một đối tượng `MimeMessage` hoặc `MimeMessageHelper` trong khi gửi, vì có thể làm lẫn người nhận và các body part.

```text
for each recipient:
    createMimeMessage()
    new MimeMessageHelper(...)
    render user-specific HTML
    setText(...)
    addInline(...)
    send(...)
```

Thư gửi cho nhiều người trong cùng một MIME message là bài toán khác; nếu nội dung cá nhân hóa, cần thiết kế rõ quyền riêng tư và cách theo dõi người nhận.

### 15.4. CID và an toàn nội dung HTML

Không cho dữ liệu người dùng kiểm soát trực tiếp:

- `Content-ID` có ký tự bất thường hoặc newline;
- đường dẫn hệ thống tệp dùng làm inline resource;
- HTML chứa script hoặc tài nguyên không đáng tin cậy;
- header mail được ghép từ giá trị chưa kiểm tra.

Dùng template engine có escape mặc định hoặc escape dữ liệu khi chèn vào HTML, chọn CID từ các giá trị đã được ứng dụng định nghĩa, chỉ tải resource từ nguồn được phép. Thư HTML nên có `alt` cho ảnh và bản text thuần cho thông tin quan trọng.

## 16. Bài tập thực hành

### Bài 1: Sắp xếp lại các dòng

Cho đoạn mã:

```java
helper.addInline(
    "logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);

helper.setText(
    "<html><body><img src=\"cid:logo\"></body></html>",
    true
);
```

Hãy sửa thứ tự theo khuyến nghị của Spring.

**Gợi ý:** chuyển `setText(...)` lên trước, rồi mới `addInline(...)`. Đảm bảo helper đã được tạo ở multipart mode.

### Bài 2: Tìm lỗi CID

HTML:

```html
<img src="cid:header-logo" alt="Logo">
```

Java:

```java
helper.setText(htmlText, true);
helper.addInline(
    "footer-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
```

**Lỗi:** `cid:header-logo` không khớp tham số đầu của `addInline(...)` là `footer-logo`. Sửa một bên để hai giá trị thống nhất.

### Bài 3: Thêm ảnh inline và PDF

Email cần logo và hóa đơn PDF. Hãy chọn mode multipart, viết thứ tự gọi:

1. `setText(plainText, htmlText)`;
2. `addInline("logo", ...)`;
3. `addAttachment("invoice.pdf", ...)`;
4. `send(message)`.

**Đáp án gợi ý:** `MULTIPART_MODE_MIXED_RELATED` cho nhóm related chứa HTML/logo và part PDF độc lập.

### Bài 4: Resource từ một stream dùng một lần

Bạn nhận được `InputStream` của ảnh từ storage rồi bọc bằng `InputStreamResource`. Thư có thể đọc dữ liệu nhiều lần khi chuẩn bị và gửi. Hãy giải thích vì sao cách này dễ lỗi và đổi sang nguồn có thể mở stream mới hoặc `ByteArrayResource` cho ảnh kích thước vừa phải.

### Bài 5: Sự cố chỉ xảy ra trên một mail client

Email đã vào Inbox của hai ứng dụng, nhưng một ứng dụng hiển thị logo và ứng dụng kia chỉ hiện attachment. Hãy xem raw MIME, kiểm tra `multipart/related`, `Content-ID`, `cid:...` và `Content-Type`; sau đó đánh giá sự khác biệt hỗ trợ của hai mail client.

### Bài 6: Dựng email từ template

Ứng dụng dùng HTML template với logo và banner tùy chọn. Hãy thiết kế chuỗi xử lý gồm:

- lấy dữ liệu nghiệp vụ và quyết định asset nào xuất hiện;
- render HTML hoàn chỉnh, đồng thời tạo phiên bản plain text;
- gọi `setText(plain, html)`;
- thêm từng ảnh bằng `addInline(...)` với CID đã chọn;
- gọi `send(...)` sau khi hoàn tất MIME.

### Câu hỏi tự kiểm tra

1. Vì sao `setText(...)` cần đứng trước `addInline(...)`?
2. Tham số đầu của `addInline(...)` liên hệ thế nào với `src="cid:..."`?
3. `Content-ID` khác `Message-ID` ở đâu?
4. Khi có cả inline và attachment, mode nào diễn đạt cấu trúc tốt?
5. Vì sao `ByteArrayResource` thường phù hợp hơn một input stream chỉ đọc được một lần?
6. Nếu `send(...)` thành công nhưng ảnh không hiện, cần kiểm tra SMTP password hay cấu trúc MIME trước?
7. Có thể gọi `setText(...)` một lần và `addInline(...)` nhiều lần không?

**Gợi ý:** (1) để nội dung chính/cây MIME được thiết lập trước khi thêm tài nguyên liên quan; (2) phải khớp định danh; (3) Content-ID định danh MIME part, Message-ID định danh thông điệp; (4) MIXED_RELATED; (5) có thể đọc nhiều lần; (6) MIME và mail client; (7) có, với CID riêng cho mỗi ảnh.

## 17. Tổng kết

Để tạo email HTML chứa tài nguyên inline trong **Spring Framework Mail**, hãy bật chế độ multipart phù hợp, **hoàn thiện nội dung HTML hoặc HTML/plain text trước bằng `MimeMessageHelper.setText(...)`, rồi mới gọi `MimeMessageHelper.addInline(...)`** cho từng tài nguyên. HTML dùng `cid:...` phải trùng với Content-ID của part ảnh; nguồn resource phải đọc được và Content-Type phải phù hợp.

Khi email còn có attachment, `MULTIPART_MODE_MIXED_RELATED` giúp giữ phần HTML và các ảnh liên quan trong một nhóm, còn attachment ở phần riêng. Nếu ảnh vẫn không hiển thị, hãy kiểm tra MIME source thực nhận và khác biệt hỗ trợ của mail client. **Thứ tự `setText → addInline → send` là nguyên tắc nhỏ nhưng rất quan trọng để email HTML có ảnh inline hoạt động đáng tin cậy hơn trên nhiều ứng dụng đọc thư.**

