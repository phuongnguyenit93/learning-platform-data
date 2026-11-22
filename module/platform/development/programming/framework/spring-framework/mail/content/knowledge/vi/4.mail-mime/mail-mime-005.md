# multipart/related cho HTML và tài nguyên inline

Trong ứng dụng **Spring Framework Mail**, một email HTML có thể hiển thị chữ, bảng, nút bấm và hình ảnh. Tuy nhiên, nếu mã HTML chứa `<img src="logo.png">`, chương trình email của người nhận không thể tự đọc tệp `logo.png` trên máy chủ ứng dụng. Muốn gửi hình ảnh đi **cùng thông điệp** và tham chiếu chúng ngay trong HTML, ta cần cấu trúc MIME phù hợp: **`multipart/related`** và **Content-ID (CID)**.

Bài học giải thích cách MIME tổ chức nội dung HTML và tài nguyên inline, cách `JavaMailSender` cùng `MimeMessageHelper` tạo thông điệp tương ứng, cách kết hợp với văn bản thuần hoặc tệp đính kèm, và vì sao cùng một email có thể hiển thị khác nhau trên các ứng dụng đọc thư.

## 1. MIME là gì và vì sao HTML cần multipart/related?

**MIME (Multipurpose Internet Mail Extensions)** mở rộng định dạng email để mang nhiều kiểu dữ liệu: văn bản thuần, HTML, hình ảnh, PDF và nhiều phần nội dung trong một thông điệp. Những phần đó được mô tả bằng các header như `Content-Type`, `Content-ID`, `Content-Disposition` và `Content-Transfer-Encoding`.

Một email đơn giản chỉ có text thường dùng:

```text
MIME-Version: 1.0
Content-Type: text/plain; charset=UTF-8

Xin chào, đây là nội dung thư.
```

Email HTML đơn giản có thể dùng `text/html`. Nhưng khi HTML tham chiếu **ảnh được đính kèm bên trong chính thông điệp** thay vì tải từ website, ta cần cho chương trình đọc thư biết: “Phần HTML này và các ảnh này có quan hệ với nhau; ảnh nào ứng với tham chiếu nào”.

`multipart/related` làm đúng việc đó:

- Nó là một **container MIME** chứa nhiều body part có quan hệ với nhau.
- Một part đóng vai trò **nội dung gốc** (thường là HTML hoặc một `multipart/alternative` chứa HTML).
- Các part khác chứa **tài nguyên liên quan**, chẳng hạn logo PNG, ảnh JPEG hoặc hình minh họa được HTML tham chiếu bằng `cid:...`.
- Ứng dụng email có thể kết hợp các part để render cùng một nội dung.

**Không đồng nhất “inline” với “gửi kèm attachment”.** Tài nguyên inline là một phần phục vụ hiển thị trong body; attachment thông thường được người dùng mở hoặc tải riêng. Cả hai đều là MIME parts nhưng thường cần các container khác nhau.

## 2. Phân biệt related, alternative và mixed

Ba subtype `multipart` rất hay xuất hiện cùng nhau:

| MIME subtype | Ý nghĩa | Trường hợp điển hình |
|---|---|---|
| `multipart/alternative` | Nhiều phiên bản của **cùng nội dung**, theo thứ tự từ đơn giản đến giàu định dạng hơn | Cùng thông điệp có `text/plain` và `text/html`. |
| `multipart/related` | Một nội dung chính cùng **tài nguyên phụ thuộc** để hiển thị nội dung đó | HTML tham chiếu logo qua `cid:brand-logo`. |
| `multipart/mixed` | Nhiều thành phần độc lập được gộp vào một thư | Nội dung email và tệp hóa đơn PDF đính kèm. |

Ví dụ cấu trúc chỉ có HTML và logo inline:

```text
multipart/related
├── text/html                     (nội dung gốc)
│   └── <img src="cid:brand-logo">
└── image/png                     (tài nguyên inline)
    └── Content-ID: <brand-logo>
```

Nếu muốn có cả **bản text thuần** để dự phòng và **bản HTML** để hiển thị đẹp:

```text
multipart/related
├── multipart/alternative          (nội dung gốc)
│   ├── text/plain
│   └── text/html                  (tham chiếu cid:brand-logo)
└── image/png                      (Content-ID: <brand-logo>)
```

Nếu thư có thêm PDF cần tải về:

```text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html              (tham chiếu cid:brand-logo)
│   └── image/png                  (logo inline)
└── application/pdf                (tệp đính kèm hóa đơn)
```

Cách lồng này giúp ứng dụng email phân biệt **logo thuộc nội dung HTML** với **PDF là attachment**.

> `multipart/related` giải quyết quan hệ giữa HTML và tài nguyên; `multipart/alternative` giải quyết nhiều cách trình bày cùng nội dung; `multipart/mixed` giải quyết việc đóng gói các phần độc lập. Chúng không thay thế nhau và có thể lồng nhau.

## 3. Content-ID và cú pháp cid: liên kết HTML với ảnh

Cốt lõi của email HTML có ảnh inline là cặp **`Content-ID` trong MIME part** và **`cid:...` trong HTML**.

Trong HTML:

```html
<img src="cid:brand-logo" alt="Logo thương hiệu" width="160">
```

Trong MIME part chứa ảnh:

```text
Content-Type: image/png
Content-ID: <brand-logo>
Content-Disposition: inline; filename="logo.png"
Content-Transfer-Encoding: base64

[du lieu PNG duoc ma hoa base64]
```

Chương trình đọc email thấy `src="cid:brand-logo"`, tìm part có `Content-ID: <brand-logo>` và dùng dữ liệu ảnh của part đó để hiển thị.

Các điểm cần nhớ:

1. **Khớp định danh:** `cid:brand-logo` phải tham chiếu đúng `Content-ID: <brand-logo>`. Phần nằm trong ngoặc nhọn của header tương ứng với giá trị sau `cid:`.
2. **Không đặt ngoặc nhọn trong HTML:** viết `src="cid:brand-logo"`, không viết `src="cid:<brand-logo>"`.
3. **Content-ID khác Message-ID:** `Message-ID` định danh toàn bộ email; `Content-ID` định danh một MIME part.
4. **Content-ID khác filename:** tên `logo.png` chỉ mang ý nghĩa mô tả tệp, không thay thế được CID khi HTML cần tìm đúng ảnh.
5. **Mỗi tài nguyên dùng một CID riêng:** tránh dùng trùng CID cho các ảnh khác nhau trong cùng thư. Với mã tự tạo MIME, nên dùng định danh duy nhất và hợp lệ theo cấu trúc message-id; `MimeMessageHelper` hỗ trợ tự đặt CID qua `addInline(...)`.
6. **CID được dùng trong nhiều thuộc tính có URL** của HTML nếu mail client hỗ trợ, nhưng `<img src="cid:...">` là trường hợp thông dụng nhất. Hỗ trợ cho CSS background, SVG và các kỹ thuật nâng cao khác không đồng đều.

Header `Content-Disposition: inline` gợi ý cho mail client rằng nội dung nên hiển thị cùng body. **Nó không tự tạo liên kết từ HTML đến ảnh** nếu thiếu CID phù hợp. Ngược lại, một số ứng dụng email vẫn hiển thị tài nguyên inline trong danh sách tệp đính kèm; đây là khác biệt về cách hiển thị của client, không nhất thiết là lỗi MIME.

### Inline khác ảnh tải từ URL

Hai ví dụ nhìn giống nhau trên giao diện nhưng có cơ chế khác nhau:

```html
<!-- Ảnh nằm bên trong thông điệp, tham chiếu bằng Content-ID -->
<img src="cid:brand-logo" alt="Logo">

<!-- Ảnh được tải từ một địa chỉ HTTP/HTTPS bên ngoài -->
<img src="https://cdn.example.com/mail/logo.png" alt="Logo">
```

| Tiêu chí | CID inline | URL ngoài |
|---|---|---|
| Dữ liệu ảnh | Được gói trong email dưới dạng MIME part. | Mail client có thể phải tải từ máy chủ ngoài. |
| Phụ thuộc mạng khi người nhận mở thư | Có thể hiển thị từ dữ liệu thư đã nhận; còn tùy chính sách client. | Cần truy cập URL và phụ thuộc khả năng/chính sách tải ảnh từ xa. |
| Kích thước email | Tăng vì ảnh được gửi cùng thông điệp và thường mã hóa cho truyền tải. | Nội dung email có thể nhỏ hơn, nhưng cần host ảnh ổn định. |
| Khả năng hiển thị | Phụ thuộc cách mail client xử lý `multipart/related` và CID. | Phụ thuộc chính sách tải ảnh ngoài, proxy, chặn tracking và kết nối mạng. |
| URL trong HTML | `cid:brand-logo` | `https://...` |

Data URI như `src="data:image/png;base64,..."` là cơ chế khác nữa; nhiều email client có giới hạn hoặc không hỗ trợ tốt. Đối với ảnh cần gửi kèm thông điệp, CID trong `multipart/related` thường là hướng rõ ràng hơn.

## 4. MIME thô của một email HTML có logo inline

Hãy nhìn vào cấu trúc minh họa sau. Chuỗi boundary và nội dung Base64 được rút gọn để dễ đọc, **không phải** thông điệp được thiết kế để gửi trực tiếp:

```text
From: no-reply@example.com
To: user@example.net
Subject: Chao mung ban
MIME-Version: 1.0
Content-Type: multipart/related;
 boundary="rel-001";
 type="multipart/alternative"

--rel-001
Content-Type: multipart/alternative; boundary="alt-001"

--alt-001
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Chao mung ban den voi ung dung.

--alt-001
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<html>
  <body>
    <h1>Chao mung ban!</h1>
    <img src="cid:brand-logo" alt="Logo">
  </body>
</html>

--alt-001--

--rel-001
Content-Type: image/png; name="logo.png"
Content-ID: <brand-logo>
Content-Disposition: inline; filename="logo.png"
Content-Transfer-Encoding: base64

[du lieu PNG da ma hoa, duoc rut gon]

--rel-001--
```

Đọc từ ngoài vào trong:

- Header `Content-Type: multipart/related` khai báo thông điệp gồm các phần có quan hệ.
- Boundary `rel-001` phân tách **nội dung gốc** và **ảnh inline**.
- Nội dung gốc là `multipart/alternative`, chứa text/plain trước và text/html sau. Client có thể chọn phiên bản mình hỗ trợ.
- HTML chứa `cid:brand-logo`; ảnh PNG ở part khác có header `Content-ID: <brand-logo>`.
- `Content-Transfer-Encoding: base64` mô tả cách biểu diễn byte của ảnh trong thông điệp; mã hóa kiểu này **không phải mã hóa bảo mật**.

Thông điệp MIME thực tế có cú pháp newline, boundary, encoding và header theo quy định. Trong ứng dụng Spring, nên để Jakarta Mail tạo những chi tiết đó thay vì tự nối chuỗi MIME theo mẫu minh họa.

## 5. Tạo multipart/related bằng Spring Framework Mail

Trong Spring, công cụ chính là:

- `JavaMailSender` tạo và gửi `MimeMessage`;
- `MimeMessageHelper` giúp đặt thông tin người gửi/nhận, nội dung HTML, text thay thế, tài nguyên inline và attachment;
- `ClassPathResource`, `FileSystemResource` hoặc `ByteArrayResource` cung cấp dữ liệu tệp/ảnh cho helper.

Với Spring Boot, thêm starter mail (ví dụ Gradle Groovy DSL):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

Một cấu hình SMTP minh họa cho máy chủ submission dùng STARTTLS:

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

Cấp `SMTP_USERNAME` và `SMTP_PASSWORD` qua môi trường hoặc secret store; không commit credential thật vào repository. Nếu dùng Spring Framework không có Boot, tự cấu hình `JavaMailSenderImpl`, SMTP properties và dependency Jakarta Mail phù hợp.

### 5.1. Chuẩn bị hình ảnh trong resources

Đặt logo trong classpath của ứng dụng:

```text
src/
  main/
    java/
      com/example/mail/WelcomeMailService.java
    resources/
      mail/
        logo.png
      application.yml
```

Khi đóng gói JAR, file `src/main/resources/mail/logo.png` thường có thể đọc bằng:

```java
new ClassPathResource("mail/logo.png")
```

Không dùng đường dẫn tương đối trên máy phát triển như `C:\project\src\main\resources\...`. Đường dẫn classpath hoạt động ổn định hơn khi chạy trong JAR, container hay môi trường triển khai khác.

### 5.2. Gửi HTML + plain text + logo inline

Ví dụ sử dụng Spring Boot 3.x / Spring Framework 6.x với các import `jakarta.mail.*`:

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private static final String LOGO_CID = "brand-logo";

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient) throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();

        // Chọn rõ cấu trúc related: phần HTML và ảnh inline có liên hệ.
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            "UTF-8"
        );

        helper.setFrom("no-reply@example.com");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn");

        String plainText =
            "Chào mừng bạn đến với ứng dụng!\n"
            + "Chúng tôi rất vui vì có bạn tham gia.";

        String htmlText = """
            <!DOCTYPE html>
            <html lang="vi">
              <body>
                <img src="cid:brand-logo"
                     alt="Logo thương hiệu"
                     width="160"
                     style="display:block;border:0">
                <h1>Chào mừng bạn!</h1>
                <p>Chúng tôi rất vui vì có bạn tham gia.</p>
              </body>
            </html>
            """;

        // Đặt nội dung TRƯỚC khi thêm các tài nguyên inline.
        helper.setText(plainText, htmlText);

        // Content-ID của part ảnh sẽ tương ứng với cid:brand-logo.
        helper.addInline(
            LOGO_CID,
            new ClassPathResource("mail/logo.png"),
            "image/png"
        );

        mailSender.send(message);
    }
}
```

Phân tích các dòng quan trọng:

1. `createMimeMessage()` tạo đối tượng email có thể chứa MIME multipart, khác với `SimpleMailMessage` chỉ phục vụ thư văn bản đơn giản.
2. `MULTIPART_MODE_RELATED` yêu cầu helper tạo container MIME dạng `multipart/related`.
3. `helper.setText(plainText, htmlText)` tạo các phiên bản nội dung plain text và HTML để client lựa chọn. Phiên bản HTML chứa `cid:brand-logo`.
4. `helper.addInline("brand-logo", ..., "image/png")` thêm một MIME part có Content-ID tương ứng. Spring/Jakarta Mail phụ trách đọc resource và biểu diễn nội dung ảnh.
5. `mailSender.send(message)` gửi thông điệp qua SMTP được cấu hình; việc gọi thành công không đồng nghĩa thư đã được giao tới Inbox.

**Thứ tự rất quan trọng:** theo cách dùng `MimeMessageHelper`, gọi `setText(...)` **trước** `addInline(...)`. Điều này giúp tạo đúng cấu trúc các MIME part và tránh trường hợp một số mail client không phân giải được ảnh inline.

### 5.3. Vì sao dùng text/plain và text/html cùng lúc?

Không phải mail client nào cũng hiển thị HTML giống nhau. Một số trường hợp email được đọc trong chế độ văn bản thuần, chuyển tiếp qua hệ thống chỉ hỗ trợ text hoặc phục vụ công nghệ hỗ trợ người dùng. Với:

```java
helper.setText(
    "Xin chào, cảm ơn bạn đã đăng ký.",
    "<p>Xin chào, <strong>cảm ơn bạn đã đăng ký.</strong></p>"
);
```

Spring tạo hai phiên bản thuộc `multipart/alternative`. Đây là **cùng nội dung được biểu diễn theo hai cách**, không phải hai email. Phiên bản plain text nên giữ đủ thông tin nghiệp vụ; đừng chỉ ghi “Vui lòng xem bản HTML”.

Nếu chỉ cần HTML, có thể gọi `helper.setText(htmlText, true)`; khi dùng inline CID, vẫn cần container `multipart/related` và gọi `addInline(...)` sau khi đặt text.

## 6. Khi nào dùng MULTIPART_MODE_RELATED và MIXED_RELATED?

`MimeMessageHelper` cung cấp nhiều chế độ multipart. Trong tình huống có HTML và inline assets, hai chế độ cần hiểu rõ nhất:

| Chế độ helper | Cấu trúc chính | Nên dùng khi |
|---|---|---|
| `MULTIPART_MODE_RELATED` | `multipart/related` ở phần nội dung chính | Email chỉ có HTML/plain text và tài nguyên inline liên quan. |
| `MULTIPART_MODE_MIXED_RELATED` | `multipart/mixed` ngoài cùng, `multipart/related` bên trong | Email có HTML + inline assets **và** tệp đính kèm độc lập, như PDF. |

Trong Spring, constructor dùng `multipart=true` thường chọn kiểu kết hợp `MULTIPART_MODE_MIXED_RELATED`. Chọn hằng số chế độ cụ thể trong ví dụ giúp người đọc hiểu ý định tạo cấu trúc MIME.

### 6.1. Ví dụ logo inline và hóa đơn PDF đính kèm

Giả sử ứng dụng đã tạo ra một mảng byte `pdfBytes` từ nghiệp vụ xuất hóa đơn:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;

public class InvoiceMailSender {
    private final JavaMailSender mailSender;

    public InvoiceMailSender(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendInvoice(String recipient, byte[] pdfBytes)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
            "UTF-8"
        );

        helper.setFrom("billing@example.com");
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn của bạn");
        helper.setText(
            "Hóa đơn của bạn được đính kèm dưới dạng PDF.",
            """
            <html><body>
              <img src="cid:invoice-logo" alt="Logo" width="120">
              <p>Hóa đơn của bạn được đính kèm dưới dạng PDF.</p>
            </body></html>
            """
        );

        helper.addInline(
            "invoice-logo",
            new ClassPathResource("mail/logo.png"),
            "image/png"
        );

        helper.addAttachment(
            "hoa-don.pdf",
            new ByteArrayResource(pdfBytes),
            "application/pdf"
        );

        mailSender.send(message);
    }
}
```

Ở đây, **logo** nằm trong nhóm `related` cùng HTML, còn **PDF** là attachment của `mixed`. `ByteArrayResource` tạo một input stream mới từ byte array mỗi lần cần đọc; điều này hữu ích vì thư viện mail có thể cần đọc dữ liệu resource nhiều lần trong quá trình chuẩn bị và gửi thư.

Không nên dùng một `InputStream` đơn lẻ đã bị đọc hết rồi bọc thành nguồn dữ liệu chỉ đọc được một lần. Nếu ảnh/tệp được lấy từ dịch vụ ngoài hoặc bộ nhớ, hãy cung cấp `InputStreamSource` có khả năng mở stream mới mỗi lần hoặc lưu nội dung vào `ByteArrayResource` khi kích thước phù hợp.

### 6.2. Có thể gửi nhiều ảnh inline

Chỉ cần mỗi ảnh có một CID khác nhau và HTML tham chiếu đúng:

```html
<img src="cid:header-logo" alt="Logo" width="120">
<p>Thông báo mới của bạn</p>
<img src="cid:notice-banner" alt="Ảnh minh họa thông báo" width="480">
```

```java
helper.setText(plainText, htmlText);
helper.addInline(
    "header-logo",
    new ClassPathResource("mail/logo.png"),
    "image/png"
);
helper.addInline(
    "notice-banner",
    new ClassPathResource("mail/banner.jpg"),
    "image/jpeg"
);
```

Đặt Content-Type đúng với dữ liệu ảnh thật; không gắn `image/png` cho file JPEG chỉ để giữ cùng một mẫu cấu hình.

## 7. Cách chọn nguồn tài nguyên inline

`MimeMessageHelper.addInline(...)` có nhiều overload. Việc chọn nguồn dữ liệu phù hợp giúp email chạy ổn định ở môi trường phát triển lẫn khi đóng gói.

| Nguồn | Ví dụ | Lưu ý |
|---|---|---|
| `ClassPathResource` | `new ClassPathResource("mail/logo.png")` | Phù hợp logo hoặc ảnh tĩnh đóng gói sẵn trong ứng dụng. |
| `FileSystemResource` | `new FileSystemResource(path)` | Phù hợp file ở ổ đĩa hoặc volume; cần kiểm soát đường dẫn/quyền đọc và tránh phụ thuộc đường dẫn cứng. |
| `ByteArrayResource` | `new ByteArrayResource(imageBytes)` | Phù hợp ảnh đã được tạo hoặc tải về và lưu trong byte array; tránh giữ ảnh quá lớn trong RAM. |
| `InputStreamSource` tùy biến | Nguồn có thể mở stream mới cho mỗi lần đọc | Cần đảm bảo mỗi lời gọi `getInputStream()` trả một stream độc lập, còn sử dụng được. |

Ví dụ tạo logo từ dữ liệu byte có sẵn:

```java
byte[] imageBytes = loadGeneratedPng(); // Hàm nghiệp vụ minh họa
helper.addInline(
    "generated-chart",
    new ByteArrayResource(imageBytes),
    "image/png"
);
```

Trong HTML tương ứng:

```html
<img src="cid:generated-chart" alt="Biểu đồ tổng hợp">
```

Hàm `loadGeneratedPng()` ở ví dụ này tượng trưng cho nơi tạo ảnh, không phải API sẵn có của Spring. Dù nguồn ở đâu, nội dung phải là dữ liệu ảnh hợp lệ và có kích thước phù hợp cho email.

## 8. Những lỗi thường gặp và cách nhận diện

### 8.1. Logo biến thành biểu tượng ảnh lỗi

Nguyên nhân phổ biến:

- HTML tham chiếu `cid:company-logo` nhưng gọi `addInline("brand-logo", ...)`.
- HTML dùng đường dẫn file local như `src="./logo.png"`, hoặc đường dẫn `/static/logo.png` vốn chỉ có nghĩa trong web server.
- Resource `mail/logo.png` không tồn tại trong classpath khi ứng dụng chạy.
- MIME part có dữ liệu sai định dạng, `Content-Type` sai hoặc client không hỗ trợ một định dạng ảnh.
- Thứ tự tạo MIME part không phù hợp: thêm inline trước khi đặt nội dung bằng `setText(...)`.
- Email client cụ thể không render cấu trúc đang dùng đúng như mong đợi.

Để phân biệt lỗi nội dung với lỗi cấu trúc, hãy kiểm tra **MIME source** của email đã nhận: có part ảnh thật không, `Content-ID` là gì, `src="cid:..."` có khớp không, và ảnh có nằm trong nhóm `multipart/related` cùng HTML không.

### 8.2. Hình ảnh bị hiển thị như tệp đính kèm

Một số mail client hiện cả biểu tượng attachment dù ảnh đã được hiển thị inline. Cần phân biệt:

- **Không hiển thị trong HTML và xuất hiện như attachment:** nên kiểm tra CID, container `related`, subtype ảnh và cấu trúc multipart.
- **Hiển thị đúng trong HTML nhưng vẫn có biểu tượng attachment:** có thể chỉ là cách phần mềm email trình bày các MIME part; không có cách nào đảm bảo mọi client ẩn hoàn toàn biểu tượng đó.

`Content-Disposition: inline` là một gợi ý xử lý, không phải yêu cầu bắt buộc mọi ứng dụng email phải render giống nhau.

### 8.3. Chỉ có text mà không thấy HTML hoặc thấy hai bản cùng lúc

Với `multipart/alternative`, chương trình đọc thư được kỳ vọng lựa chọn bản phù hợp. Nếu cấu trúc MIME bị lồng sai hoặc một client không hỗ trợ tốt, nó có thể hiển thị bản không mong muốn.

Hãy kiểm tra thứ tự các part `text/plain` trước `text/html` trong container `alternative`, rồi xác định container này có nằm trong `related` như dự định không. Tránh tự tạo các multipart lồng nhau bằng chuỗi, vì rất dễ sai boundary và header.

### 8.4. Ảnh có thể xem trên trang web nhưng không hiển thị trong email

Web browser và email client có bộ quy tắc khác nhau. Nhiều client loại bỏ JavaScript, hạn chế CSS, tự chặn tải tài nguyên ngoài hoặc áp dụng chính sách riêng với SVG, ảnh động, ảnh nền và định dạng không phổ biến. CID không bảo đảm tất cả client hỗ trợ đầy đủ mọi tính năng HTML/CSS.

Với email giao dịch quan trọng, hãy ưu tiên HTML đơn giản, ảnh PNG/JPEG phổ biến, khai báo kích thước hợp lý, `alt` có ý nghĩa và cung cấp bản text.

### 8.5. Lỗi khi truy cập tài nguyên hoặc gửi MIME

Một số vấn đề không liên quan đến SMTP:

- `MessagingException` có thể xuất hiện khi xây dựng/chỉnh sửa MIME.
- `MailException` của Spring có thể được ném khi gọi `mailSender.send(...)` gặp lỗi gửi.
- Nguồn dữ liệu ảnh không mở được hoặc đã bị tiêu thụ khiến quá trình tạo/gửi part không thành công.
- Ảnh hay attachment quá lớn khiến thông điệp vượt giới hạn nhà cung cấp hoặc gây tốn bộ nhớ.

Phân biệt **lỗi chuẩn bị MIME**, **lỗi kết nối/xác thực SMTP** và **lỗi giao hàng phía sau**; chúng xảy ra ở các tầng khác nhau và cần cách xử lý khác nhau.

## 9. Kích thước, bảo mật và khả năng truy cập

### 9.1. Không nhúng tài nguyên quá lớn

Ảnh trong email thường được biểu diễn bằng Base64, làm dữ liệu truyền lớn hơn dữ liệu nhị phân gốc (thường tăng khoảng một phần ba, chưa kể phần header và xuống dòng). Nếu chèn quá nhiều ảnh độ phân giải cao, thư có thể:

- bị máy chủ từ chối do vượt giới hạn kích thước;
- tải/chuyển tiếp chậm hoặc bị cắt nội dung ở một số ứng dụng đọc thư;
- tạo chi phí băng thông và lưu trữ lớn;
- khó đọc trên thiết bị di động.

Hãy tối ưu độ phân giải, nén ảnh phù hợp và chỉ nhúng những tài nguyên thật sự cần thiết. Với tệp lớn dùng để tải xuống, cân nhắc attachment hoặc liên kết an toàn theo yêu cầu nghiệp vụ.

### 9.2. CID không phải cơ chế bảo mật

`multipart/related` chỉ đóng gói nội dung. Nó **không mã hóa end-to-end** và không tự xác thực người gửi. TLS cho kết nối SMTP, quản lý quyền gửi, cùng cấu hình tên miền (SPF, DKIM, DMARC) là các mối quan tâm riêng.

Không nhúng thông tin bí mật vào ảnh hay HTML nếu không có căn cứ cho việc chia sẻ. Nếu tạo nội dung HTML từ dữ liệu người dùng, escape dữ liệu phù hợp hoặc dùng template engine có cơ chế xử lý an toàn. Tránh tải nội dung HTML tùy ý từ nguồn không tin cậy rồi gửi lại nguyên trạng.

### 9.3. Dùng alt text và bản plain text

Không nên để thông tin quan trọng chỉ xuất hiện trong hình ảnh. Ví dụ mã xác nhận, thời hạn hoặc thông tin thanh toán cần có dưới dạng text vì ảnh có thể bị ẩn hoặc không hiển thị.

Một ảnh trang trí:

```html
<img src="cid:decorative-line" alt="" width="480">
```

Một ảnh mang thông tin:

```html
<img src="cid:service-status"
     alt="Dịch vụ đang hoạt động bình thường"
     width="240">
```

Tốt hơn nữa, hãy đưa thông báo “Dịch vụ đang hoạt động bình thường” thành văn bản thực ngay cạnh ảnh, để mọi người đọc được dù ảnh không tải.

## 10. Quy trình tự kiểm tra khi gửi HTML có inline

Trong lúc phát triển, có thể gửi một thư thử đến các ứng dụng đọc email đại diện cho đối tượng người dùng rồi kiểm tra:

1. **Nội dung HTML:** có hiện tiêu đề, đoạn văn, liên kết và hình ảnh theo ý định không?
2. **CID:** giá trị sau `cid:` trong HTML có khớp `Content-ID` của ảnh không?
3. **Cấu trúc:** ảnh nằm trong `multipart/related` cùng nội dung gốc; nếu có PDF, nó ở nhóm `mixed` thích hợp hay chưa?
4. **Thứ tự tạo part:** `setText(...)` được gọi trước `addInline(...)` hay chưa?
5. **Bản thay thế:** khi xem plain text, thông tin chính có đầy đủ không?
6. **Khả năng truy cập:** ảnh quan trọng có `alt` phù hợp và nội dung vẫn hiểu được khi ảnh bị chặn không?
7. **Dung lượng:** kích thước thư sau MIME encoding có phù hợp giới hạn SMTP không?

Nếu một client cụ thể hiển thị ảnh lỗi, xem **source của email thực nhận** và đối chiếu với cấu trúc kỳ vọng thay vì chỉ nhìn mã HTML ban đầu. Sau khi xác nhận MIME hợp lệ, mới kiểm tra đến khác biệt hỗ trợ của từng client.

## 11. Bài tập thực hành

### Bài 1: Một HTML, hai ảnh inline

Yêu cầu: tạo email chào mừng có logo ở đầu và banner ở cuối. Hai ảnh được đóng gói trong thư.

Gợi ý:

```html
<h2>Chào mừng thành viên mới</h2>
<img src="cid:welcome-logo" alt="Logo" width="120">
<p>Cảm ơn bạn đã tham gia.</p>
<img src="cid:welcome-banner" alt="Banner chào mừng" width="480">
```

Gọi `helper.setText(plainText, htmlText)` rồi thêm hai part tương ứng bằng `addInline("welcome-logo", ...)` và `addInline("welcome-banner", ...)`. Mỗi part có Content-Type đúng với ảnh.

### Bài 2: Thêm hóa đơn vào thư có logo

Một email có nội dung HTML tham chiếu logo và có file `invoice.pdf` cho người nhận tải về. Hãy chọn giữa `MULTIPART_MODE_RELATED` và `MULTIPART_MODE_MIXED_RELATED` rồi vẽ cây MIME.

**Đáp án gợi ý:** chọn `MULTIPART_MODE_MIXED_RELATED`; phần ngoài là `multipart/mixed`, phần trong là `multipart/related` (HTML và logo) và một part `application/pdf` độc lập.

### Bài 3: Tìm lỗi Content-ID

HTML:

```html
<img src="cid:brand-banner" alt="Banner">
```

Java:

```java
helper.setText(plainText, htmlText);
helper.addInline(
    "brand-logo",
    new ClassPathResource("mail/banner.png"),
    "image/png"
);
```

**Vấn đề:** CID trong HTML là `brand-banner`, còn CID được tạo qua `addInline(...)` là `brand-logo`. Sửa một bên để hai định danh khớp nhau. Tên file `banner.png` không quyết định liên kết CID.

### Bài 4: Khi người nhận không xem được ảnh

Email đã gửi, phần text hiển thị nhưng logo không hiện. Hãy phân tích lần lượt: file nguồn có tồn tại, helper có dùng multipart, `setText` có đặt trước `addInline`, MIME part có Content-ID đúng, client có chính sách hiển thị ảnh riêng hay không.

Đây là bài tập phân tích cấu trúc MIME và cách client sử dụng tài nguyên; kết quả gửi SMTP thành công chỉ xác nhận việc server đã tiếp nhận thư ở một bước nhất định.

## 12. Câu hỏi ôn tập

**1. `multipart/related` khác `multipart/alternative` như thế nào?** Related liên kết một phần nội dung chính với tài nguyên phụ thuộc; alternative cung cấp nhiều phiên bản thay thế của cùng nội dung, ví dụ plain text và HTML.

**2. Vì sao không dùng `src="/images/logo.png"` để hiển thị logo inline?** Đường dẫn đó thường chỉ có nghĩa trong môi trường web hoặc máy chủ của ứng dụng; email client không có thông tin để mở tệp đó trong thư. Cần gửi tài nguyên và tham chiếu bằng CID, hoặc dùng một URL ngoài hợp lệ nếu chọn cơ chế tải ảnh từ mạng.

**3. Header nào liên kết ảnh với `cid:logo`?** `Content-ID: <logo>` trên MIME part chứa ảnh.

**4. Dùng `addAttachment(...)` có thay thế `addInline(...)` không?** Không. Attachment là một phần được gửi kèm độc lập; `addInline` đặt Content-ID và cấu trúc phù hợp để HTML tham chiếu nội dung đó.

**5. Khi nào dùng `MULTIPART_MODE_MIXED_RELATED`?** Khi email có cả tài nguyên inline phục vụ HTML và attachment độc lập như PDF.

**6. Vì sao gọi `setText(...)` trước `addInline(...)`?** Để `MimeMessageHelper` tạo cấu trúc nội dung chính trước, rồi bổ sung các MIME part liên quan theo cách mail client có thể phân giải CID đáng tin cậy hơn.

**7. Tại sao nên có phiên bản `text/plain`?** Nó cho phép người nhận tiếp cận nội dung khi HTML không được hiển thị hoặc người nhận chọn chế độ văn bản thuần.

## 13. Tổng kết

Khi email HTML cần sử dụng ảnh nằm ngay trong thông điệp, hãy dùng **`multipart/related`** để nhóm HTML với tài nguyên inline, và dùng **`Content-ID` + `cid:...`** để liên kết chính xác từng ảnh. Trong Spring Framework Mail, `MimeMessageHelper` giúp tạo cấu trúc này qua `MULTIPART_MODE_RELATED`, `setText(...)` và `addInline(...)`.

Nếu thư còn có bản plain text, sử dụng thêm cấu trúc `multipart/alternative`. Nếu có tệp đính kèm độc lập, chọn `MULTIPART_MODE_MIXED_RELATED` để phân tách nội dung liên quan và attachment. Dù cấu trúc MIME đã đúng, cách hiển thị vẫn phụ thuộc mail client; vì vậy nội dung quan trọng nên tồn tại dưới dạng text và ảnh nên có mô tả thay thế phù hợp.
