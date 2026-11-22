# Không dùng đường dẫn file cục bộ trong HTML gửi đi với Spring Framework Mail

Khi tạo email HTML trong Spring Framework Mail, một lỗi thường gặp là đặt đường dẫn file trên máy chủ vào thuộc tính `src` của thẻ `<img>`:

```html
<!-- Những cách này không phù hợp cho email gửi đến người khác -->
<img src="C:\app\images\logo.png" alt="Logo">
<img src="file:///var/app/images/logo.png" alt="Logo">
<img src="/opt/application/assets/logo.png" alt="Logo">
<img src="../images/logo.png" alt="Logo">
```

Các đường dẫn trên chỉ có ý nghĩa trong một filesystem hoặc ngữ cảnh cụ thể. Email được gửi đến hộp thư của người nhận; mail client trên máy người nhận không có quyền truy cập vào ổ đĩa, thư mục hoặc container của máy chủ Spring. Vì vậy ảnh thường bị hỏng, dù file có tồn tại trên máy chạy ứng dụng.

**Không đưa đường dẫn filesystem vào HTML email.** Nếu ảnh phải được gửi kèm thông điệp, hãy nhúng nó thành MIME inline resource và tham chiếu bằng `cid:...`. Nếu ảnh có thể được tải từ web, dùng URL HTTPS tuyệt đối do ứng dụng kiểm soát. Nếu tài liệu cần được tải riêng, đính kèm nó bằng API attachment.

Bài học này giải thích ranh giới giữa đường dẫn local của máy chủ và nội dung email, cách dùng `MimeMessageHelper.addInline(...)` với tài nguyên classpath, file system hoặc byte array, cách dùng ảnh remote, và cách quản lý vòng đời cũng như bảo mật của tài nguyên.

## 1. Vì sao đường dẫn file cục bộ không hoạt động trong email?

Khi ứng dụng Spring render HTML, chuỗi HTML được đưa vào phần thân MIME của email. Ví dụ:

```html
<img src="C:\app\images\logo.png" alt="Logo">
```

Email chỉ chứa **chuỗi ký tự** `C:\app\images\logo.png`. Nó không tự động gửi file ở vị trí đó. Khi người nhận mở email, ứng dụng đọc thư cố gắng diễn giải giá trị `src` trong môi trường của chính nó. Đường dẫn Windows trên máy chủ gửi không phải đường dẫn trên máy Windows của người nhận, và đường dẫn Linux trong container không phải đường dẫn trên thiết bị di động.

Ví dụ:

```text
Máy chủ Spring
  C:\app\images\logo.png
          |
          | HTML chỉ chứa chuỗi đường dẫn
          v
      SMTP message
          |
          v
Mail client của người nhận
  Không có quyền truy cập filesystem của máy chủ Spring
```

Một file có thể tồn tại và đọc được bởi tài khoản chạy ứng dụng, nhưng điều đó không tạo ra một liên kết mà người nhận có thể truy cập. Email không chia sẻ filesystem của hai máy.

### Các kiểu đường dẫn cần phân biệt

| Kiểu giá trị trong `src` | Ví dụ | Kết quả trong email |
|---|---|---|
| Đường dẫn Windows | `C:\app\images\logo.png` | Không có ý nghĩa trên máy người nhận |
| URI file | `file:///var/app/logo.png` | Trỏ đến filesystem phía client hoặc bị client chặn; không trỏ về máy chủ gửi |
| Đường dẫn tuyệt đối Linux | `/opt/app/logo.png` | Không phải URL web; không có tài nguyên tương ứng ở client |
| Đường dẫn tương đối | `../images/logo.png` | Không có base path filesystem/web đáng tin cậy trong email |
| URL HTTPS tuyệt đối | `https://static.example.org/logo.png` | Client có thể tải từ web nếu chính sách cho phép |
| CID | `cid:brand-logo` | Tham chiếu MIME part được nhúng trong chính email |
| Data URI | `data:image/png;base64,...` | Một số client chặn hoặc không hỗ trợ; không nên dùng làm phương án mặc định |

### Đường dẫn local có thể làm lộ thông tin nội bộ

Ngoài việc không hiển thị, đường dẫn như `/srv/apps/customer-prod/tenant-a/reports/secret.pdf` có thể tiết lộ tên thư mục, cấu trúc triển khai hoặc thông tin nội bộ của hệ thống. Không đưa đường dẫn vật lý, tên ổ đĩa, username máy chủ hoặc mount point vào HTML, subject hay header email.

Ngay cả khi một số mail client cho phép người dùng bấm một liên kết `file://` trong môi trường đặc biệt, không nên dựa vào hành vi đó. Email gửi qua Internet cần nội dung có thể xử lý độc lập với filesystem riêng của máy gửi.

## 2. Chọn cách đưa hình ảnh vào email

Với hình ảnh trong HTML email, có hai cách thông dụng:

1. **Remote image:** HTML trỏ đến URL HTTPS công khai hoặc URL được cấp quyền phù hợp.
2. **Inline resource:** byte ảnh được đóng gói trong MIME message và HTML tham chiếu nó qua Content-ID bằng `cid:`.

Ví dụ:

```html
<!-- Remote image: mail client tải ảnh từ web -->
<img src="https://static.example.org/mail/logo.png"
     alt="Logo Example" width="140">

<!-- Inline resource: ảnh nằm trong cùng MIME message -->
<img src="cid:brand-logo"
     alt="Logo Example" width="140">
```

Hai giá trị `src` này không thể hoán đổi tùy tiện. `https://...` yêu cầu client truy cập máy chủ web; `cid:brand-logo` yêu cầu email có một MIME part mang Content-ID tương ứng.

| Tiêu chí | Remote image | Inline resource (CID) |
|---|---|---|
| Dữ liệu ảnh | Trên máy chủ web/CDN | Nằm trong MIME message |
| HTML `src` | URL HTTPS tuyệt đối | `cid:content-id` |
| Cần `addInline` | Không | Có |
| Cần mạng khi mở ảnh | Thường có, trừ khi đã cache/proxy | Không cần tải ảnh đó từ web |
| Dung lượng email | Nhỏ hơn | Tăng theo kích thước ảnh và MIME encoding |
| Phụ thuộc URL còn sống | Có | Không |
| Chính sách chặn ảnh | Có thể bị chặn | Cũng có thể bị client hạn chế |
| Phù hợp | Banner, ảnh sản phẩm, tài nguyên dùng chung | Logo nhỏ, biểu đồ riêng, ảnh cần đi cùng message |

Không có cách nào bảo đảm ảnh luôn hiển thị trên mọi mail client. Hãy thêm `alt`, giữ thông tin quan trọng ở dạng văn bản và thử nghiệm với các ứng dụng đọc thư mà sản phẩm cần hỗ trợ.

## 3. Cách đúng cho ảnh nằm trên máy chủ: nhúng bằng CID

Nếu file ảnh hiện có trên máy chạy ứng dụng và bạn muốn gửi nó cùng email, hãy đọc file thành một **MIME resource**. Không ghi đường dẫn local vào HTML. Thay vào đó:

1. Đặt một Content-ID, ví dụ `brand-logo`.
2. Trong HTML, dùng `src="cid:brand-logo"`.
3. Gọi `MimeMessageHelper.addInline("brand-logo", resource, "image/png")`.
4. Gửi message sau khi đã thiết lập body và inline resource.

Ví dụ:

```html
<img src="cid:brand-logo" alt="Logo cửa hàng" width="140">
```

Phần HTML chỉ biết Content-ID. Việc đọc file từ classpath hoặc filesystem do code Java thực hiện.

### Cấu trúc MIME logic

Một message có HTML và ảnh inline có thể có cấu trúc:

```text
MimeMessage
└── multipart/related
    ├── text/html; charset=UTF-8
    │   <img src="cid:brand-logo">
    └── image/png
        Content-ID: <brand-logo>
        Content-Disposition: inline
```

Nếu email còn có plain text, phần body có thể chứa `multipart/alternative` bên trong `multipart/related`. Nếu có attachment độc lập, `multipart/mixed` có thể bao ngoài. `MimeMessageHelper` quản lý việc tạo các MIME part và boundary; ứng dụng không cần tự ghép raw MIME source.

### Content-ID phải khớp với CID trong HTML

Với:

```java
helper.addInline("brand-logo", resource, "image/png");
```

HTML phải dùng:

```html
<img src="cid:brand-logo" alt="Logo">
```

Trong MIME source, header có thể được biểu diễn là `Content-ID: <brand-logo>`. Khi gọi `addInline`, truyền ID dạng chuỗi `brand-logo`; không tự thêm dấu ngoặc nhọn. Mỗi ảnh cần một Content-ID riêng, ổn định trong message đó.

**CID không phải đường dẫn file.** Nó là định danh của một MIME part bên trong email. Mail client tìm ảnh trong message hiện tại thay vì truy cập filesystem của máy chủ.

## 4. Dùng ClassPathResource cho ảnh đóng gói cùng ứng dụng

Với logo dùng chung, icon hoặc hình ảnh tĩnh, có thể đặt file trong resources:

```text
src/main/resources/
└── mail/
    └── images/
        └── logo.png
```

Khi ứng dụng được đóng gói thành JAR, tài nguyên có thể nằm bên trong JAR chứ không phải một file vật lý độc lập ở đường dẫn cố định. Vì vậy, nên đọc qua abstraction `Resource` của Spring thay vì tự ghép một đường dẫn kiểu `src/main/resources/mail/images/logo.png`.

Ví dụ:

```java
import org.springframework.core.io.ClassPathResource;

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
```

`ClassPathResource` đọc tài nguyên từ classpath dù ứng dụng chạy trong IDE hay từ JAR đóng gói. Nội dung ảnh được đưa vào MIME part khi email được gửi.

### Service Spring hoàn chỉnh với logo classpath

```java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public WelcomeMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendWelcome(String recipient)
            throws MessagingException {

        String plainText = """
                Chào mừng bạn đến với Example!

                Bạn có thể truy cập https://example.org để bắt đầu.
                Nếu cần hỗ trợ, hãy liên hệ support@example.org.
                """;

        String htmlText = """
                <!doctype html>
                <html lang="vi">
                  <body>
                    <p>
                      <img src="cid:brand-logo"
                           alt="Logo Example"
                           width="140">
                    </p>
                    <h2>Chào mừng bạn đến với Example!</h2>
                    <p>
                      Truy cập
                      <a href="https://example.org">Example</a>
                      để bắt đầu.
                    </p>
                    <p>Cần hỗ trợ? support@example.org</p>
                  </body>
                </html>
                """;

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message, true, StandardCharsets.UTF_8.name());

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn đến với Example");
        helper.setText(plainText, htmlText);

        // HTML đã được đặt trước, sau đó thêm MIME part mà CID tham chiếu.
        helper.addInline(
                "brand-logo",
                new ClassPathResource("mail/images/logo.png"),
                "image/png");

        mailSender.send(message);
    }
}
```

Các điểm chính:

- `MimeMessageHelper(message, true, "UTF-8")` bật multipart để message chứa nhiều MIME part.
- `setText(plainText, htmlText)` tạo hai phiên bản body thay thế.
- `src="cid:brand-logo"` tham chiếu ảnh đã được thêm bằng `addInline`.
- `ClassPathResource` lấy file từ resources, không để lộ đường dẫn local trong HTML.
- `mailSender.send(message)` gửi một message chứa nội dung và ảnh.

Với Spring Boot, `JavaMailSender` thường được cấu hình qua `spring.mail.*`. Địa chỉ `From` nên lấy từ cấu hình gửi đã xác minh; không lấy trực tiếp từ dữ liệu người dùng.

### Thứ tự gọi API

Nên làm theo thứ tự:

1. Tạo `MimeMessage`.
2. Tạo `MimeMessageHelper` ở multipart mode.
3. Đặt From, To, Subject và body bằng `setText(...)`.
4. Gọi `addInline(...)` cho từng ảnh được HTML tham chiếu.
5. Thêm attachment khác nếu có.
6. Gọi `JavaMailSender.send(...)`.

Spring khuyến nghị gọi `setText(...)` trước `addInline(...)` để tránh vấn đề tương thích với một số mail client và giữ cấu trúc MIME theo cách helper dự kiến.

## 5. Dùng FileSystemResource cho ảnh được lưu trên đĩa

Nếu ảnh được tạo hoặc lưu bên ngoài classpath, ví dụ logo tenant, biểu đồ được xuất ra file hoặc tài liệu được tạo trong thư mục tạm, có thể dùng `FileSystemResource`:

```java
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;

Path logoPath = Path.of("/var/app/private-mail/tenant-a/logo.png");

helper.addInline(
        "tenant-logo",
        new FileSystemResource(logoPath),
        "image/png");
```

HTML vẫn chỉ chứa:

```html
<img src="cid:tenant-logo" alt="Logo doanh nghiệp">
```

`FileSystemResource` là nguồn byte cho ứng dụng dựng MIME part. Chuỗi `/var/app/private-mail/tenant-a/logo.png` **không được đưa vào HTML**. Khi email được gửi, ảnh được đọc từ filesystem phía server và đóng gói vào message.

### Đường dẫn filesystem phải do ứng dụng kiểm soát

Không nên nhận một đường dẫn tuyệt đối tùy ý từ request rồi đưa thẳng vào `FileSystemResource`. Ví dụ không an toàn:

```java
// Không dùng đường dẫn do người dùng tùy ý gửi lên.
Path path = Path.of(request.getParameter("imagePath"));
helper.addInline("image", new FileSystemResource(path), "image/png");
```

Người dùng có thể đưa đường dẫn trỏ đến file ngoài thư mục ảnh được phép, tùy quyền của tiến trình ứng dụng. Thay vào đó, hãy nhận một ID tài nguyên đã được xác thực, rồi tìm file từ một thư mục được cấu hình:

```java
Path allowedRoot = Path.of("/var/app/mail-assets").toRealPath();
Path candidate = allowedRoot.resolve(assetRecord.storageName()).normalize();

if (!candidate.startsWith(allowedRoot)) {
    throw new SecurityException("Asset path is outside allowed directory");
}

Path realFile = candidate.toRealPath();
if (!realFile.startsWith(allowedRoot)) {
    throw new SecurityException("Resolved asset escapes allowed directory");
}

helper.addInline(
        "tenant-logo",
        new FileSystemResource(realFile),
        "image/png");
```

Ví dụ này giả định `assetRecord.storageName()` là tên file do hệ thống quản lý. Việc kiểm tra đường dẫn đã chuẩn hóa và đường dẫn thực giúp chống một số dạng path traversal và symlink escape; cần kết hợp quyền filesystem, thư mục upload riêng và kiểm tra loại nội dung. Không để người dùng quyết định ID Content-ID tùy ý hoặc truy cập asset của tenant khác.

### Khi file là file tạm

Nếu ảnh được tạo vào thư mục tạm, cần bảo đảm file tồn tại cho đến khi thư viện gửi hoàn tất:

```java
Path imagePath = Files.createTempFile("mail-chart-", ".png");
try {
    chartGenerator.writePng(chartData, imagePath);

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper =
            new MimeMessageHelper(message, true, "UTF-8");
    helper.setFrom(fromAddress);
    helper.setTo(recipient);
    helper.setSubject("Biểu đồ báo cáo");
    helper.setText(
            "Biểu đồ được đính kèm trong nội dung HTML.",
            "<p>Biểu đồ:</p><img src=\"cid:chart-image\" alt=\"Biểu đồ\">");
    helper.addInline(
            "chart-image",
            new FileSystemResource(imagePath),
            "image/png");

    mailSender.send(message);
} finally {
    Files.deleteIfExists(imagePath);
}
```

Đây là mẫu đồng bộ: file được xóa sau khi `send` kết thúc hoặc ném lỗi. Nếu việc gửi được đưa vào queue và worker chạy sau, **không xóa file ngay khi enqueue**. Worker cần đọc được tài nguyên tại thời điểm gửi; hãy lưu artifact bền vững hoặc quản lý file tạm theo trạng thái job và thời hạn dọn dẹp.

## 6. Dùng ByteArrayResource cho ảnh được tạo trong bộ nhớ

Nếu ảnh đã có dưới dạng `byte[]` (ví dụ biểu đồ được render từ dữ liệu, QR code hoặc ảnh thu nhỏ), dùng `ByteArrayResource`:

```java
import org.springframework.core.io.ByteArrayResource;

byte[] chartPng = chartGenerator.renderPng(chartData);

helper.setText(
        "Báo cáo đã sẵn sàng.",
        """
        <h2>Báo cáo</h2>
        <p>Biểu đồ doanh thu:</p>
        <img src="cid:sales-chart" alt="Biểu đồ doanh thu">
        """);

helper.addInline(
        "sales-chart",
        new ByteArrayResource(chartPng),
        "image/png");
```

`ByteArrayResource` cung cấp một `InputStream` mới từ cùng byte array khi được yêu cầu. Điều này hữu ích vì thư viện mail có thể đọc resource trong quá trình tạo/gửi MIME message. Không cần ghi byte array ra một đường dẫn local chỉ để sau đó đưa đường dẫn đó vào HTML.

Với file lớn, byte array giữ toàn bộ nội dung trong heap. Hãy cân nhắc giới hạn kích thước và số tác vụ đồng thời; có thể dùng `FileSystemResource` hoặc object storage cho tài nguyên lớn.

### So sánh các Resource thường dùng

| Resource | Nguồn dữ liệu | Khi phù hợp |
|---|---|---|
| `ClassPathResource` | Tài nguyên đóng gói trong classpath/JAR | Logo và ảnh tĩnh của ứng dụng |
| `FileSystemResource` | File trên filesystem phía server | Ảnh tenant, file động hoặc file tạm |
| `ByteArrayResource` | Byte array trong bộ nhớ | Ảnh sinh động hoặc đã được đọc sẵn |
| `InputStreamResource` | Một InputStream | Nguồn stream đặc thù; cần chú ý khả năng đọc lại |

`InputStreamSource` truyền vào helper nên cung cấp một stream mới mỗi lần thư viện yêu cầu. Một `InputStreamResource` bọc stream đã mở và đã đọc hết có thể không dùng lại được; ưu tiên resource có vòng đời rõ ràng.

## 7. Ảnh remote: dùng URL HTTPS tuyệt đối

Nếu ảnh nằm trên website/CDN và được phép truy cập từ Internet, hãy đặt URL HTTPS tuyệt đối trong HTML:

```html
<img src="https://static.example.org/mail/brand-logo.png"
     alt="Logo Example"
     width="140"
     style="display:block;max-width:100%;height:auto">
```

Không dùng:

```html
<!-- Không phải URL web hợp lệ cho người nhận -->
<img src="/assets/logo.png">
<img src="../assets/logo.png">
<img src="file:///var/app/assets/logo.png">
```

URL tương đối không có base URL ổn định trong email. Nếu muốn dùng remote image:

- Dùng hostname HTTPS tuyệt đối.
- Đảm bảo endpoint có thể truy cập từ phía người nhận hoặc proxy của mail client.
- Không yêu cầu cookie đăng nhập nội bộ nếu người nhận bên ngoài cần xem ảnh.
- Giữ URL hoạt động trong khoảng thời gian email cần được xem.
- Không chứa token bí mật hoặc thông tin cá nhân nhạy cảm trong query string.
- Thêm `alt` và giữ nội dung quan trọng trong văn bản.

Một số mail client chặn hoặc proxy ảnh ngoài để bảo vệ quyền riêng tư. Vì vậy remote image có thể không xuất hiện dù URL hoạt động khi mở bằng trình duyệt. Nếu logo cần đi cùng message và không phụ thuộc URL web, cân nhắc CID inline.

## 8. Không dùng data URI như giải pháp thay thế mặc định

Một cách khác là nhúng base64 trực tiếp trong HTML:

```html
<img src="data:image/png;base64,iVBORw0KGgoAAA..." alt="Logo">
```

Đây là **data URI**, không phải đường dẫn local. Tuy nhiên, hỗ trợ data URI trong email client không đồng nhất; một số client loại bỏ hoặc không hiển thị chúng. Nó cũng làm HTML body lớn hơn và khó quản lý template.

Nếu muốn gửi byte ảnh bên trong email, dùng MIME inline resource:

```html
<img src="cid:brand-logo" alt="Logo">
```

và:

```java
helper.addInline(
        "brand-logo",
        new ByteArrayResource(imageBytes),
        "image/png");
```

Cách CID biểu diễn ảnh theo cấu trúc MIME, phù hợp hơn với API Spring Mail dành cho inline resource. Không tự chuyển toàn bộ file thành base64 rồi ghép vào HTML trừ khi có yêu cầu tương thích đã được kiểm chứng cụ thể.

## 9. Phân biệt inline resource và attachment

Một hình ảnh có thể được gửi như tài nguyên inline hoặc như file đính kèm thông thường. Hai cách này có mục đích khác nhau:

| API | Mục đích | HTML tham chiếu |
|---|---|---|
| `helper.addInline(contentId, resource, contentType)` | Cung cấp tài nguyên mà HTML tham chiếu | `src="cid:..."` |
| `helper.addAttachment(filename, resource, contentType)` | Đưa file vào danh sách attachment | Không tự tạo `src` trong HTML |

Ví dụ một email có logo inline và PDF attachment:

```java
helper.setText(
        "Hóa đơn của bạn đã sẵn sàng.",
        """
        <p><img src="cid:invoice-logo" alt="Logo"></p>
        <p>Hóa đơn đã sẵn sàng. Vui lòng xem file PDF đính kèm.</p>
        """);

helper.addInline(
        "invoice-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");

helper.addAttachment(
        "invoice.pdf",
        new ByteArrayResource(invoicePdfBytes),
        "application/pdf");
```

Ảnh logo được HTML tham chiếu qua CID; PDF xuất hiện như một file có thể tải về. Chỉ gọi `addAttachment` không làm ảnh tự xuất hiện ở một vị trí trong HTML.

## 10. Nhiều ảnh inline trong một email

Mỗi tài nguyên cần một Content-ID riêng:

```java
helper.setText(
        "Báo cáo tháng đã sẵn sàng.",
        """
        <h2>Báo cáo tháng</h2>
        <p><img src="cid:brand-logo" alt="Logo Example"></p>
        <p>Doanh thu:</p>
        <img src="cid:revenue-chart" alt="Biểu đồ doanh thu">
        <p>Đơn hàng:</p>
        <img src="cid:orders-chart" alt="Biểu đồ đơn hàng">
        """);

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");
helper.addInline(
        "revenue-chart",
        new ByteArrayResource(revenueChartPng),
        "image/png");
helper.addInline(
        "orders-chart",
        new ByteArrayResource(ordersChartPng),
        "image/png");
```

Các ID phải khớp chính xác với HTML và không trùng nhau trong cùng message. Không tái sử dụng một Content-ID cho hai ảnh khác nhau vì client có thể hiển thị sai tài nguyên.

Với biểu đồ, đừng chỉ truyền số liệu qua ảnh. Cung cấp thêm bảng hoặc đoạn văn mô tả các giá trị chính trong HTML và bản plain text để người đọc vẫn hiểu khi ảnh không hiển thị hoặc dùng công cụ trợ năng.

## 11. Bảo mật khi đọc file local để nhúng vào email

Việc không đưa đường dẫn local vào HTML chưa đủ để đảm bảo an toàn. Ứng dụng vẫn phải kiểm soát file mà nó đọc và đưa vào message.

### Không nhận path tùy ý từ người dùng

Tránh API kiểu:

```java
public void sendImage(String recipient, String localPath) {
    // Không đọc một path tùy ý do client cung cấp.
}
```

Một path tùy ý có thể trỏ tới file cấu hình, file secret hoặc tài liệu thuộc tenant khác nếu process có quyền đọc. Hãy dùng asset ID đã được xác thực và tra cứu đường dẫn trong một vùng lưu trữ được phép.

### Kiểm tra tenant và quyền truy cập

Nếu logo hoặc ảnh được lưu theo tenant:

- Xác định tenant từ ngữ cảnh đã xác thực.
- Tra cứu asset trong phạm vi tenant đó.
- Kiểm tra asset đang hoạt động và được phép dùng trong email.
- Không cho người dùng gửi asset ID của tenant khác.
- Kiểm tra người nhận được phép nhận nội dung mà ảnh thể hiện.

### Kiểm tra loại file thực tế

Không tin hoàn toàn vào phần mở rộng file. Một file có tên `logo.png` có thể không phải PNG. Với ảnh động hoặc file upload, nên kiểm tra signature/định dạng thực tế, giới hạn kích thước và giải mã bằng thư viện phù hợp trước khi đưa vào email.

MIME type truyền cho `addInline` phải khớp nội dung, ví dụ `image/png` hoặc `image/jpeg`. Không khai báo ảnh JPEG thành `image/png` chỉ vì tên file có đuôi .png.

### Giới hạn kích thước

Đặt giới hạn số byte cho từng ảnh và tổng MIME message. Ảnh lớn có thể làm email vượt quota của provider hoặc tăng bộ nhớ khi gửi hàng loạt. Nếu ảnh quá lớn, resize/compress hoặc dùng URL HTTPS đến trang/tài nguyên được phép.

### Cẩn trọng khi backend tải URL để tạo CID

Có hai hành vi khác nhau:

- HTML chứa URL HTTPS: mail client có thể tải ảnh sau khi người nhận mở thư.
- Backend tự tải URL rồi nhúng ảnh CID: máy chủ Spring thực hiện HTTP request trước khi gửi.

Nếu backend nhận URL do người dùng cung cấp rồi tải nội dung, cần phòng ngừa SSRF: giới hạn scheme/host/port, kiểm tra DNS và địa chỉ IP, xử lý redirect an toàn, timeout, giới hạn byte và chặn mạng nội bộ/metadata endpoints theo chính sách. Không biến tính năng “nhúng ảnh từ URL” thành proxy truy cập tùy ý vào mạng của máy chủ.

### Không đưa đường dẫn hoặc dữ liệu nhạy cảm vào log

Log nên ghi asset ID, loại MIME, kích thước, mail job ID và kết quả đọc file. Tránh log nội dung file, token, đường dẫn chứa tên người dùng hoặc thư mục nội bộ nhạy cảm nếu không cần thiết.

## 12. Quản lý vòng đời tài nguyên

Một lỗi phổ biến trong gửi email bất đồng bộ là tạo file tạm, enqueue job rồi xóa file ngay. Khi worker nhận job, tài nguyên đã biến mất.

### Gửi đồng bộ

Với luồng đồng bộ:

```text
Tạo file tạm
   |
   v
Tạo MimeMessage
   |
   v
addInline(FileSystemResource)
   |
   v
send(message) hoàn tất
   |
   v
Xóa file tạm
```

File phải tồn tại đến khi mail library đọc xong resource. Có thể dùng `try/finally` để dọn dẹp sau khi `send` hoàn tất.

### Gửi bất đồng bộ

Với queue:

```text
Request thread
  -> tạo artifact
  -> lưu artifact bền vững
  -> enqueue artifact ID

Mail worker
  -> đọc artifact
  -> tạo MimeMessage
  -> addInline(...)
  -> send(...)
  -> cập nhật trạng thái
  -> cleanup theo retention
```

Không truyền một đường dẫn trỏ tới file tạm sẽ bị xóa khi request kết thúc. Có thể lưu file vào object storage hoặc thư mục được quản lý với TTL, rồi để worker đọc theo artifact ID đã được phân quyền.

### Resource cần có thể đọc lại

API nhận `InputStreamSource` có thể được mail library yêu cầu mở stream khi dựng hoặc gửi nội dung. Vì vậy, nguồn tài nguyên nên tạo được stream mới khi cần. `ClassPathResource`, `FileSystemResource` và `ByteArrayResource` thường thuận tiện hơn một `InputStreamResource` bọc một stream duy nhất đã mở.

## 13. Cấu hình Spring Boot và ví dụ sử dụng trong ứng dụng

Một ứng dụng Spring Boot có thể thêm mail starter:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

Cấu hình SMTP ví dụ với port 587 và STARTTLS:

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
      "[mail.smtp.ssl.checkserveridentity]": true

app:
  mail:
    from: ${MAIL_FROM}
```

Các biến môi trường là ví dụ; cung cấp chúng qua cấu hình triển khai hoặc secret manager. Nếu nhà cung cấp dùng port 465 với implicit TLS, cấu hình phải theo đúng yêu cầu provider, thường dùng `mail.smtp.ssl.enable` thay cho STARTTLS. Việc dùng CID không thay đổi cách kết nối SMTP.

### Tách asset resolver khỏi mail service

Khi ứng dụng có nhiều email, có thể đóng gói logic tìm ảnh vào một component:

```java
package com.example.mail;

import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Component;

@Component
public class MailImageCatalog {

    public Resource brandLogo() {
        return new ClassPathResource("mail/images/logo.png");
    }

    public String brandLogoContentId() {
        return "brand-logo";
    }

    public String brandLogoContentType() {
        return "image/png";
    }
}
```

Mail service dùng catalog:

```java
helper.setText(plainText, htmlText);
helper.addInline(
        imageCatalog.brandLogoContentId(),
        imageCatalog.brandLogo(),
        imageCatalog.brandLogoContentType());
```

Template HTML phải tham chiếu đúng `cid:brand-logo`. Catalog chỉ quản lý tài nguyên được ứng dụng tin cậy; nếu logo thay đổi theo tenant, component cần nhận tenant đã xác thực và tra cứu resource theo quyền, không lấy đường dẫn tùy ý từ template.

## 14. Kiểm thử email có inline resource

Không nên chỉ xác nhận rằng `addInline` không ném exception. Cần kiểm tra MIME message được dựng có part ảnh và Content-ID khớp HTML.

### Kiểm tra với SMTP sink

Trong môi trường phát triển, có thể trỏ Spring đến SMTP sink như Mailpit. Gửi một email thử nghiệm rồi mở raw source để kiểm tra:

```text
Content-Type: multipart/related

Content-Type: text/html; charset=UTF-8
...
<img src="cid:brand-logo">

Content-Type: image/png
Content-ID: <brand-logo>
Content-Disposition: inline
...
```

Cây MIME thực tế có thể lồng `multipart/alternative` hoặc `multipart/mixed`. Hãy kiểm tra part ảnh bên trong cấu trúc, không chỉ nhìn header ở root.

### Các trường hợp nên thử

| Trường hợp | Điều cần xác nhận |
|---|---|
| Ảnh classpath | Resource có trong JAR và được nạp khi chạy từ artifact |
| Ảnh filesystem | Đường dẫn nằm trong vùng được phép, file còn tồn tại khi send |
| Ảnh byte array | Nội dung byte không rỗng, resource có thể đọc lại |
| CID | HTML và Content-ID khớp chính xác |
| Nhiều ảnh | Mỗi ảnh có Content-ID riêng |
| HTML + plain text | Cả hai body có nội dung nghiệp vụ cần thiết |
| Inline + attachment | Ảnh hiện trong body, file khác vẫn được đính kèm |
| Ảnh sai MIME type | Ứng dụng phát hiện hoặc từ chối tài nguyên không đúng định dạng |
| File quá lớn | Bị giới hạn trước khi tạo/gửi message |
| Queue | Worker đọc được artifact sau khi request ban đầu kết thúc |

Không cần gửi thư đến hộp thư khách hàng thật để kiểm tra MIME structure. Dùng mock sender hoặc SMTP sink trong test; môi trường test không nên dùng credential production.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ảnh hiện biểu tượng broken image | HTML chứa đường dẫn local | Dùng CID hoặc URL HTTPS tuyệt đối |
| Ảnh file:// không hiển thị | Mail client không truy cập filesystem máy gửi hoặc chặn file URI | Không dùng file URI trong HTML email |
| Ảnh tương đối không hiển thị | Email không có base path filesystem/web ổn định | Dùng HTTPS tuyệt đối hoặc CID |
| CID không tìm thấy ảnh | Chưa gọi `addInline` hoặc ID không khớp | So khớp `cid:...` với Content-ID |
| Ảnh xuất hiện như attachment | Mail client liệt kê MIME part inline | Kiểm tra MIME structure và client mục tiêu |
| File tồn tại trên IDE nhưng mất khi chạy JAR | Dùng filesystem path đến `src/main/resources` | Dùng `ClassPathResource` |
| File tạm không đọc được | Đã xóa trước khi mail library đọc resource | Giữ file đến khi send hoàn tất hoặc lưu artifact bền vững |
| Attachment/inline resource rỗng | Stream chỉ đọc được một lần hoặc đã tiêu thụ | Dùng resource có thể mở stream mới |
| Ảnh sai màu hoặc lỗi giải mã | MIME type không khớp dữ liệu hoặc file hỏng | Kiểm tra signature và content type |
| Email quá lớn | Nhiều ảnh inline hoặc ảnh độ phân giải cao | Resize, nén, giới hạn tổng byte hoặc dùng remote URL |
| HTML chứa đường dẫn nội bộ | Template lấy trực tiếp filesystem path | Chỉ truyền Content-ID hoặc URL HTTPS vào template |
| Người dùng có thể đọc file ngoài thư mục ảnh | Path được lấy trực tiếp từ request | Dùng asset ID, allowlist root và kiểm tra canonical path |
| Ảnh remote không tải | Client chặn ảnh, proxy/CDN lỗi hoặc URL không công khai | Kiểm tra URL và chính sách hiển thị; thêm alt/fallback |
| Ảnh khác tenant bị gửi nhầm | Asset lookup không giới hạn tenant | Kiểm tra tenant và quyền trước khi đọc resource |

### Phân biệt lỗi đọc resource và lỗi SMTP

- Nếu `ClassPathResource` hoặc `FileSystemResource` không mở được, lỗi xảy ra khi chuẩn bị MIME resource.
- Nếu MIME message được tạo nhưng SMTP không chấp nhận, kiểm tra network, TLS, AUTH, quota và provider.
- Nếu SMTP chấp nhận nhưng ảnh không hiển thị, kiểm tra MIME source, CID, content type và chính sách mail client.

`send(...)` thành công không bảo đảm mail client đã render ảnh. Cần xem đúng tầng xảy ra lỗi để tránh sửa SMTP khi nguyên nhân thực tế là HTML đang dùng đường dẫn local.

## 16. Các nguyên tắc nên áp dụng

1. **Không ghi đường dẫn local vào `src`.** HTML email không chia sẻ filesystem với máy chủ gửi.
2. **Dùng CID cho ảnh cần đi cùng message.** Tham chiếu `cid:...` và thêm resource bằng `addInline`.
3. **Dùng ClassPathResource cho asset tĩnh.** Tránh hard-code đường dẫn thư mục triển khai hoặc đường dẫn trong IDE.
4. **Dùng FileSystemResource cho file động được kiểm soát.** Kiểm tra path, quyền, tenant và vòng đời file.
5. **Dùng ByteArrayResource cho byte array.** Phù hợp với ảnh sinh trong bộ nhớ và có thể mở stream mới.
6. **Dùng URL HTTPS tuyệt đối cho ảnh remote.** Chấp nhận khả năng mail client chặn ảnh ngoài.
7. **Gọi setText trước addInline.** Giữ thứ tự tạo nội dung và tài nguyên theo khuyến nghị của Spring.
8. **Đặt alt và giữ thông tin quan trọng ở dạng text.** Email vẫn có ý nghĩa khi ảnh không hiển thị.
9. **Kiểm soát kích thước và loại file.** Tránh message quá lớn hoặc MIME type không đúng.
10. **Quản lý resource theo vòng đời job.** File phải còn tồn tại đến khi mail library đọc xong.

## 17. Câu hỏi thường gặp

**Tại sao đường dẫn `C:\images\logo.png` không hiển thị trong email?** Vì email chỉ chứa chuỗi đường dẫn đó. Mail client của người nhận không có quyền truy cập ổ đĩa C: của máy chủ gửi.

**Có thể dùng `file:///var/app/logo.png` không?** Không nên. URI file không trỏ đến filesystem của máy chủ Spring từ thiết bị người nhận và nhiều mail client còn chặn loại URI này.

**Nếu file nằm trong `src/main/resources`, có nên dùng đường dẫn `src/main/resources/...` không?** Không. Khi đóng gói ứng dụng, tài nguyên có thể nằm bên trong JAR. Dùng `ClassPathResource` để đọc nó.

**Nếu ảnh nằm trong thư mục upload trên server thì sao?** Dùng `FileSystemResource` làm nguồn MIME cho `addInline`, sau khi xác thực asset và đường dẫn. HTML chỉ chứa `cid:...`.

**`addInline(...)` có tự thay đường dẫn local trong HTML thành CID không?** Không. Bạn phải đặt `src="cid:content-id"` trong HTML và gọi `addInline` với cùng Content-ID.

**Có thể dùng `ByteArrayResource` không?** Có. Đây là lựa chọn thuận tiện khi ảnh đã có trong `byte[]`, ví dụ ảnh QR hoặc biểu đồ vừa tạo.

**Tại sao nên gọi `setText(...)` trước `addInline(...)`?** Đây là thứ tự Spring khuyến nghị để tạo phần nội dung trước rồi thêm các tài nguyên mà HTML tham chiếu, giúp tương thích tốt hơn với mail client.

**CID có phải URL công khai không?** Không. CID tham chiếu một MIME part bên trong cùng thông điệp email; nó không phải endpoint HTTP và không cần DNS.

**Ảnh CID có cần máy chủ web hoạt động khi người nhận mở thư không?** Không cần tải chính ảnh CID từ web vì dữ liệu ảnh nằm trong message đã nhận. Tuy nhiên, các ảnh remote khác trong email vẫn phụ thuộc mạng và chính sách client.

**Có nên dùng data URI base64 trong HTML không?** Không nên làm mặc định vì hỗ trợ giữa mail client không đồng nhất và HTML trở nên lớn. Dùng CID inline nếu muốn đóng gói ảnh trong email.

**Có thể đính kèm một file và đồng thời hiển thị file đó trong HTML không?** Có thể tạo một MIME part inline và tham chiếu bằng CID; attachment thông thường được thêm bằng `addAttachment`. Hai cách có mục đích hiển thị khác nhau.

**Có thể nhận đường dẫn ảnh từ người dùng rồi nhúng không?** Không nên nhận filesystem path tùy ý. Hãy nhận asset ID, kiểm tra quyền và chỉ đọc file trong vùng lưu trữ được phép.

**Gửi bất đồng bộ có ảnh hưởng đến resource không?** Có. Resource phải còn tồn tại đến khi worker gửi. Không xóa file tạm ngay sau khi enqueue job; dùng artifact lưu bền vững hoặc tạo lại trong worker.

**Nếu SMTP gửi thành công nhưng ảnh không hiện thì sao?** SMTP chỉ xác nhận submission. Kiểm tra MIME part, Content-ID, MIME type và hành vi của mail client; không kết luận ảnh đã được hiển thị từ kết quả `send()`.

## 18. Tài liệu kỹ thuật liên quan

- **Spring Framework Mail — `MimeMessageHelper`:** `addInline(...)`, `addAttachment(...)`, `setText(...)` và multipart mode.
- **Spring Core Resources:** `ClassPathResource`, `FileSystemResource`, `ByteArrayResource` và `InputStreamSource`.
- **Jakarta Mail:** `MimeMessage`, `MimeMultipart`, `Content-ID` và `Content-Disposition`.
- **RFC 2045–2049 — MIME:** cách biểu diễn nội dung và multipart trong email.
- **RFC 2387 — Multipart/Related:** quan hệ giữa HTML body và tài nguyên liên quan.
- **RFC 2392 — Content-ID and Message-ID URLs:** tham chiếu tài nguyên bằng `cid:`.
- **Spring Boot Mail:** cấu hình `JavaMailSender` qua `spring.mail.*`.

---

**Ghi nhớ:** filesystem của máy chủ gửi không được chia sẻ với mail client. Không đặt `C:\...`, `/var/...`, đường dẫn tương đối hoặc `file://...` vào HTML email. Với ảnh cần gửi cùng thư, dùng `src="cid:..."` và `MimeMessageHelper.addInline(...)` với `ClassPathResource`, `FileSystemResource` hoặc `ByteArrayResource`. Với ảnh trên web, dùng URL HTTPS tuyệt đối. Luôn xác thực tài nguyên, giữ file tồn tại đến khi gửi xong, kiểm soát kích thước và cung cấp nội dung văn bản thay thế.
