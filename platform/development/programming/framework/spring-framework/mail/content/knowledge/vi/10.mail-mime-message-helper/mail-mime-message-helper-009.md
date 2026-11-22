# Thêm inline resource với Content-ID

Khi gửi một email HTML bằng Spring Framework Mail, bạn có thể muốn người nhận thấy **logo, biểu đồ hoặc hình minh họa ngay trong nội dung thư**. Một cách phổ biến là đóng gói hình ảnh vào chính thông điệp email dưới dạng một MIME part, gán cho part đó một **Content-ID**, rồi tham chiếu tới nó từ HTML bằng địa chỉ bắt đầu với **cid:**.

Trong Spring, **MimeMessageHelper.addInline(...)** là API giúp thực hiện thao tác này. Thay vì tự viết MIME header, Content-ID, boundary và mã hóa ảnh, ứng dụng cung cấp mã định danh cùng nguồn dữ liệu; Spring Mail và Jakarta Mail tạo cấu trúc thông điệp để SMTP vận chuyển.

Ví dụ cốt lõi:

~~~html
<img src="cid:companyLogo" alt="Logo công ty">
~~~

~~~java
helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

Chuỗi **companyLogo** phải khớp giữa HTML và lời gọi addInline. Nếu khớp, email client có thể tìm MIME part chứa ảnh và hiển thị tại vị trí của thẻ img. Đây là **mối quan hệ giữa nội dung HTML và một tài nguyên nằm trong cùng email**, không phải địa chỉ ảnh công khai trên Internet.

Bài này giải thích Content-ID, cấu trúc **multipart/related**, các chế độ multipart của MimeMessageHelper, ví dụ Java đầy đủ, việc kết hợp ảnh inline với attachment, xử lý nhiều hình ảnh và các giới hạn tương thích khi gửi mail thực tế.

## 1. Inline resource khác gì với attachment?

Một email chứa lời nhắn và file đính kèm thường được hình dung như sau:

~~~text
Email
├── Nội dung: "Xin xem báo cáo"
└── report.pdf (tệp đính kèm)
~~~

File **report.pdf** là tài liệu độc lập. Người nhận có thể mở hoặc tải về từ danh sách attachment.

Với ảnh inline, ý định lại khác:

~~~text
Email
└── Nội dung HTML
    ├── "Chào mừng bạn!"
    ├── [Logo hiển thị ở đây]
    └── "Cảm ơn bạn đã đăng ký."
~~~

Hình ảnh là **tài nguyên phục vụ việc hiển thị nội dung HTML**, không đơn thuần là tài liệu được gửi kèm. Ở tầng MIME, hình ảnh vẫn là dữ liệu trong một part riêng, nhưng HTML biết cách tìm part ấy qua Content-ID.

| Tiêu chí | Inline resource | Attachment |
| --- | --- | --- |
| Mục tiêu | Hiển thị trong HTML ở vị trí xác định | Cho người dùng xem hoặc tải tệp riêng |
| Spring Mail API | **addInline(...)** | **addAttachment(...)** |
| Liên kết quan trọng | **Content-ID** và **cid:** | Tên tệp, MIME type, disposition |
| Disposition thường gặp | **inline** | **attachment** |
| MIME container thường gặp | **multipart/related** | **multipart/mixed** |
| Ví dụ | Logo, ảnh QR, biểu đồ trong thư | PDF, CSV, ZIP |

Một email client có thể vẫn liệt kê ảnh inline trong khu vực tệp đính kèm. Đó có thể là lựa chọn hiển thị riêng của client. Cách phân biệt ở đây là **mục đích và cấu trúc MIME** mà ứng dụng tạo.

## 2. Content-ID và cid: hoạt động như thế nào?

**Content-ID** là một trường header của MIME part. Nó cung cấp định danh để phần nội dung khác tham chiếu tới part ấy.

Ví dụ MIME part của ảnh:

~~~text
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-Disposition: inline
Content-ID: <companyLogo>

[du-lieu-PNG-duoc-ma-hoa-base64]
~~~

HTML có:

~~~html
<img src="cid:companyLogo" alt="Logo công ty">
~~~

Khi client xử lý HTML, nó nhận ra URL **cid:companyLogo** và tìm part có **Content-ID: <companyLogo>** trong thông điệp.

### 2.1. Vì sao Content-ID có dấu ngoặc còn cid: không có?

Trong header MIME, Content-ID thường được biểu diễn bằng một giá trị nằm giữa dấu **<** và **>**:

~~~text
Content-ID: <companyLogo>
~~~

Nhưng khi gọi helper, bạn chỉ đưa **định danh logic**:

~~~java
helper.addInline("companyLogo", resource, "image/png");
~~~

Và trong HTML:

~~~html
<img src="cid:companyLogo">
~~~

Spring Mail xử lý định dạng header cần thiết. **Không nên truyền sẵn dấu ngoặc nhọn** vào tham số contentId của addInline rồi để thư viện tiếp tục bọc thêm một lớp.

### 2.2. Content-ID không phải tên file

Giả sử file nằm trong:

~~~text
src/main/resources/mail/brand-logo-2026.png
~~~

Nhưng bạn gọi:

~~~java
helper.addInline(
        "headerLogo",
        new ClassPathResource("mail/brand-logo-2026.png"),
        "image/png"
);
~~~

HTML phải dùng:

~~~html
<img src="cid:headerLogo" alt="Logo">
~~~

Không phải **cid:brand-logo-2026.png** trừ khi bạn thực sự dùng chuỗi ấy làm Content-ID. Tên file mô tả dữ liệu nguồn; Content-ID là khóa liên kết giữa MIME part và phần HTML.

### 2.3. Content-ID có cần duy nhất không?

Mỗi ảnh khác nhau được tham chiếu trong cùng một message nên có **Content-ID riêng**. Nếu hai part khác nhau cùng dùng một định danh, client có thể không biết nên hiển thị phần nào.

Các ví dụ ngắn như **logo** hoặc **chart** thường dùng trong hướng dẫn Spring. Với những hệ thống cần định danh có phạm vi duy nhất rộng hơn, có thể dùng một giá trị Content-ID theo dạng message-id hợp lệ, ví dụ **logo.20261112@example.org**. Khi đó, tham chiếu trong HTML phải dùng đúng định danh và mã hóa URL nếu có ký tự đòi percent-encoding.

Content-ID là metadata có thể đọc được trong email, **không phải token bí mật**, cơ chế xác thực hay ràng buộc quyền truy cập.

### 2.4. cid: khác ảnh URL HTTPS

So sánh:

~~~html
<!-- Ảnh nằm trong cùng MIME message -->
<img src="cid:companyLogo" alt="Logo">

<!-- Ảnh lưu trên máy chủ bên ngoài -->
<img src="https://assets.example.org/images/logo.png" alt="Logo">
~~~

Ảnh **cid:** được vận chuyển cùng email; ảnh **https:** cần client tải từ một server khác khi nó quyết định hiển thị. Nhiều email client hạn chế tải nội dung từ xa vì quyền riêng tư. Tuy nhiên, điều đó không có nghĩa ảnh CID luôn được hiển thị: client vẫn có thể chặn hình ảnh hoặc xử lý MIME khác nhau.

## 3. Vì sao inline image cần MIME multipart?

Một message chỉ có **text/html** không tự chứa dữ liệu ảnh chỉ vì xuất hiện thẻ:

~~~html
<img src="cid:companyLogo">
~~~

Nếu không tồn tại MIME part có Content-ID tương ứng, thẻ img không có tài nguyên để tải.

MIME cho phép một thông điệp chứa nhiều part:

~~~text
MimeMessage
└── multipart/related
    ├── text/html
    │   └── <img src="cid:companyLogo">
    └── image/png
        ├── Content-ID: <companyLogo>
        ├── Content-Disposition: inline
        └── Dữ liệu PNG
~~~

Ở đây:

- **text/html** là nội dung chính.
- **image/png** là tài nguyên liên quan.
- **multipart/related** thể hiện mối quan hệ giữa hai part.
- **Content-ID** nối ảnh với tham chiếu cid: trong HTML.

### 3.1. multipart/related khác multipart/mixed

**multipart/mixed** thường dùng để ghép các thành phần độc lập như lời nhắn và tệp đính kèm. **multipart/related** cho biết các part cùng tạo một nội dung tổng thể, ví dụ HTML và ảnh.

Nếu có cả ảnh inline lẫn PDF tải về:

~~~text
multipart/mixed
├── multipart/related
│   ├── text/html
│   │   └── cid:companyLogo
│   └── image/png
│       └── Content-ID: <companyLogo>
└── application/pdf
    └── Content-Disposition: attachment
~~~

Như vậy, logo là tài nguyên của HTML, trong khi PDF là attachment độc lập.

### 3.2. Một message có nhiều MIME part vẫn là một email

Gọi **addInline** không yêu cầu tạo thêm một giao dịch SMTP riêng cho mỗi ảnh. Ứng dụng tạo **một MimeMessage** chứa body và các part, rồi **JavaMailSender.send(...)** giao toàn bộ message cho SMTP transport.

Số lượng MIME part khác với số email hoặc số người nhận. Một message có thể chứa ba ảnh inline nhưng chỉ gửi cho một người; hoặc chứa một ảnh nhưng được gửi đến nhiều người nhận theo phong bì SMTP.

### 3.3. Base64 giúp truyền dữ liệu nhị phân

PNG, JPEG hay GIF là dữ liệu nhị phân. Khi đóng gói thành MIME part, chúng thường được biểu diễn bằng **Content-Transfer-Encoding: base64**.

**Base64 là cách mã hóa biểu diễn dữ liệu cho vận chuyển**, không phải mã hóa bảo mật. Người có quyền xem nội dung email có thể giải mã và lấy byte ảnh.

Việc mã hóa làm tăng kích thước message; vì thế ảnh inline lớn có thể khiến email vượt giới hạn SMTP hoặc bộ lọc bên nhận.

## 4. Các chế độ multipart của MimeMessageHelper

**MimeMessageHelper** hỗ trợ các mode khi khởi tạo:

| Chế độ | Ý nghĩa chính |
| --- | --- |
| **MULTIPART_MODE_NO** | Không bật multipart |
| **MULTIPART_MODE_MIXED** | Dùng root multipart/mixed |
| **MULTIPART_MODE_RELATED** | Dùng root multipart/related |
| **MULTIPART_MODE_MIXED_RELATED** | Root mixed với nhánh related lồng nhau |

Đối với email HTML chứa ảnh inline, **MULTIPART_MODE_RELATED** thể hiện quan hệ HTML–ảnh trực tiếp.

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        mimeMessage,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);
~~~

Khi email có cả HTML, ảnh inline và attachment, mode **MIXED_RELATED** thường thích hợp:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        mimeMessage,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

Constructor viết ngắn hơn:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(mimeMessage, true, "UTF-8");
~~~

Trong Spring Framework, tham số **true** kích hoạt multipart ở chế độ mặc định **MULTIPART_MODE_MIXED_RELATED**. Nó không chỉ có nghĩa “dùng multipart/mixed thuần” như đôi khi người học suy đoán.

**MULTIPART_MODE_NO** không thích hợp cho addInline, vì cần nơi chứa các MIME part riêng. Một thông điệp không multipart không thể biểu diễn HTML và ảnh như hai part liên quan.

## 5. Ví dụ hoàn chỉnh: email chào mừng với logo nhúng từ classpath

Giả sử dự án có cấu trúc:

~~~text
src/
└── main/
    ├── java/
    │   └── com/example/mail/
    │       └── WelcomeMailService.java
    └── resources/
        ├── application.yml
        └── mail/
            └── logo.png
~~~

Tệp **logo.png** được đặt trong tài nguyên của ứng dụng và sẽ có thể truy cập từ classpath sau khi build.

### 5.1. Dependency

Trong dự án Spring Boot dùng Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
~~~

Starter cung cấp các thành phần Spring Mail/Jakarta Mail để tạo và gửi thông điệp. Host, port, TLS, credential được cấu hình riêng trong application settings hoặc môi trường chạy.

### 5.2. Service Spring Mail

~~~java
package com.example.mail;

import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class WelcomeMailService {

    private final JavaMailSender mailSender;

    public WelcomeMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("noreply@example.org");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn");

        String plainText =
                "Chào mừng bạn đến với hệ thống!\n"
              + "Cảm ơn bạn đã đăng ký.";

        String htmlText = """
                <html>
                  <body>
                    <img src="cid:companyLogo"
                         alt="Logo công ty"
                         width="160">
                    <h1>Chào mừng!</h1>
                    <p>Cảm ơn bạn đã đăng ký.</p>
                  </body>
                </html>
                """;

        // Thiết lập nội dung trước khi thêm ảnh inline.
        helper.setText(plainText, htmlText);

        ClassPathResource logo =
                new ClassPathResource("mail/logo.png");

        helper.addInline("companyLogo", logo, "image/png");

        mailSender.send(message);
    }
}
~~~

Ví dụ giả định bean **JavaMailSender** đã được cấu hình và địa chỉ recipient được kiểm tra theo chính sách của ứng dụng. HTML cố định nhằm làm rõ cấu trúc; nếu đưa dữ liệu người dùng vào HTML thì phải escape theo ngữ cảnh.

### 5.3. Phân tích từng bước

**Bước 1 — Tạo MimeMessage.**

~~~java
MimeMessage message = mailSender.createMimeMessage();
~~~

Không dùng **SimpleMailMessage** vì kiểu đơn giản này không có API để dựng MIME tree với ảnh inline.

**Bước 2 — Chọn multipart mode.**

~~~java
new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

Chế độ này cho phép nội dung HTML, tài nguyên related và attachment độc lập nếu sau này cần mở rộng. Charset UTF-8 thuận tiện khi gửi văn bản tiếng Việt.

**Bước 3 — Đặt HTML có tham chiếu cid:.**

~~~html
<img src="cid:companyLogo" alt="Logo công ty">
~~~

HTML này chỉ định vị trí hiển thị ảnh trong phần thân.

**Bước 4 — Gọi setText trước addInline.**

~~~java
helper.setText(plainText, htmlText);
~~~

Spring Mail khuyến nghị thiết lập nội dung trước khi thêm inline resource. Thứ tự này tăng khả năng tương thích giữa các email client trong việc diễn giải quan hệ các MIME part.

**Bước 5 — Trỏ tới resource và thêm Content-ID.**

~~~java
ClassPathResource logo =
        new ClassPathResource("mail/logo.png");

helper.addInline("companyLogo", logo, "image/png");
~~~

Lời gọi thêm part ảnh với Content-ID tương ứng. Đối số cuối khai báo media type của tài nguyên.

**Bước 6 — Gửi toàn bộ thông điệp.**

~~~java
mailSender.send(message);
~~~

Lúc này transport xử lý message đã có body và ảnh. Lệnh gửi không đảm bảo người nhận sẽ thấy hình ảnh, vì email client có thể ẩn hoặc xử lý khác.

### 5.4. Cấu trúc kết quả về mặt logic

~~~text
MimeMessage
└── multipart/mixed
    └── multipart/related
        ├── multipart/alternative
        │   ├── text/plain
        │   └── text/html
        │       └── <img src="cid:companyLogo">
        └── image/png
            └── Content-ID: <companyLogo>
~~~

Đây là sơ đồ mô tả quan hệ nội dung thường gặp của cấu trúc mixed/related. Dạng chính xác của các boundary và MIME header do thư viện tạo và có thể phụ thuộc vào phiên bản và cách thiết lập body.

## 6. Tại sao nên có cả plain text và HTML?

Trong ví dụ:

~~~java
helper.setText(plainText, htmlText);
~~~

Spring Mail tạo hai cách biểu diễn của cùng lời nhắn. Thông thường chúng được nhóm theo ngữ nghĩa **multipart/alternative**.

- Bản **text/plain** không phụ thuộc thẻ HTML hay ảnh.
- Bản **text/html** có bố cục và liên kết **cid:** đến logo.
- Một email client có thể chọn phiên bản phù hợp với khả năng hiển thị và tùy chọn người dùng.

Nếu chỉ cần HTML, có thể dùng:

~~~java
helper.setText(htmlText, true);
~~~

Đối số **true** cho biết nội dung là HTML. Nếu đặt **false**, client có thể hiển thị chuỗi thẻ HTML như văn bản thông thường.

Nên giữ thông tin quan trọng ở dạng text. Một email xác nhận đơn hàng vẫn phải cung cấp mã đơn và thông tin cần thiết khi logo không hiển thị.

## 7. Thứ tự gọi setText và addInline

Một điểm kỹ thuật hay gây khó hiểu là thứ tự thêm MIME part.

Thứ tự được khuyến nghị:

~~~java
helper.setText(html, true);
helper.addInline("logo", logoResource, "image/png");
~~~

Tránh đảo ngược:

~~~java
helper.addInline("logo", logoResource, "image/png");
helper.setText(html, true);
~~~

Mặc dù thư viện có thể chấp nhận nhiều thao tác trên đối tượng message, Spring Mail khuyến nghị **setText trước addInline** vì một số client nhạy cảm với cách các part được bố trí. Quy tắc này đơn giản và giúp giữ cấu trúc rõ ràng.

Nếu còn attachment, có thể thêm nó sau phần body và inline resource:

~~~java
helper.setText(html, true);
helper.addInline("logo", logoResource, "image/png");
helper.addAttachment("report.pdf", reportResource);
~~~

Mọi lệnh thực hiện trước **mailSender.send(message)**; bạn không cần gọi send sau mỗi addInline/addAttachment.

## 8. Nguồn dữ liệu cho addInline

MimeMessageHelper có các overload cho nhiều nguồn dữ liệu. Ba lựa chọn thường gặp là **ClassPathResource**, **FileSystemResource** và **ByteArrayResource**.

### 8.1. ClassPathResource — ảnh đóng gói cùng ứng dụng

Khi logo là tài nguyên tĩnh:

~~~java
helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

Đường dẫn được tính theo **classpath**, không phải theo thư mục làm việc hiện tại. Nếu file nằm ở **src/main/resources/mail/logo.png**, đường dẫn runtime thông thường là **mail/logo.png**.

Không dùng nguyên đường dẫn source:

~~~java
new ClassPathResource("src/main/resources/mail/logo.png");
~~~

vì sau khi đóng gói JAR, thư mục **src/main/resources** có thể không tồn tại như đường dẫn vật lý.

### 8.2. FileSystemResource — ảnh đã có trên đĩa

Nếu chương trình sinh biểu đồ và lưu vào một đường dẫn **Path**:

~~~java
import org.springframework.core.io.FileSystemResource;

FileSystemResource chart =
        new FileSystemResource(chartPath);

helper.setText(
        "<p>Biểu đồ:</p>"
      + "<img src=\"cid:salesChart\" alt=\"Biểu đồ\">",
        true
);

helper.addInline("salesChart", chart, "image/png");
~~~

Đoạn mã giả định **chartPath** đã được ứng dụng xác định và file PNG đã được tạo. Nên kiểm soát nguồn đường dẫn, quyền truy cập và vòng đời tệp. Nếu file bị xóa hoặc thay đổi trước khi transport đọc dữ liệu, việc gửi có thể lỗi hoặc không còn nội dung như dự định.

### 8.3. ByteArrayResource — ảnh tạo trong bộ nhớ

Nếu ứng dụng đã có byte ảnh:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] pngBytes = createPngBytes();

helper.setText(
        "<img src=\"cid:generatedImage\" alt=\"Ảnh minh họa\">",
        true
);

helper.addInline(
        "generatedImage",
        new ByteArrayResource(pngBytes),
        "image/png"
);
~~~

**createPngBytes()** trong đoạn minh họa đại diện hàm do ứng dụng triển khai để tạo dữ liệu PNG hợp lệ.

ByteArrayResource phù hợp với ảnh nhỏ hoặc vừa. Với ảnh lớn, cần cân nhắc chi phí bộ nhớ và chiến lược lưu hoặc truyền dữ liệu.

### 8.4. Vì sao không tùy tiện dùng InputStreamResource?

Trong quá trình dựng và gửi MIME, Jakarta Mail có thể cần truy cập một part nhiều lần. Một nguồn dữ liệu chỉ có thể đọc một lần có thể gây lỗi hoặc trả luồng rỗng khi thư viện cần đọc lại.

**ClassPathResource**, **FileSystemResource** và **ByteArrayResource** là các lựa chọn dễ dùng vì thường có thể cung cấp lại dữ liệu. Nếu tự cung cấp **InputStreamSource**, phải bảo đảm nó có thể mở luồng mới theo yêu cầu của API, đồng thời quản lý tài nguyên đúng vòng đời.

## 9. Content-Type phải phù hợp với định dạng ảnh

Lời gọi:

~~~java
helper.addInline("logo", resource, "image/png");
~~~

không biến dữ liệu bên trong thành PNG. Nó khai báo với client rằng part chứa dữ liệu ảnh PNG.

| Định dạng | MIME type thông dụng | Nhận xét |
| --- | --- | --- |
| PNG | image/png | Phổ biến cho logo, biểu đồ, ảnh có nền trong suốt |
| JPEG | image/jpeg | Phổ biến cho ảnh chụp |
| GIF | image/gif | Có hỗ trợ tại nhiều client nhưng animation có thể khác |
| SVG | image/svg+xml | Tính tương thích và chính sách bảo mật khác nhau |
| WebP | image/webp | Không phải client email nào cũng hỗ trợ tốt |

Khi yêu cầu hiển thị ổn định trên nhiều email client, **PNG và JPEG** thường là các lựa chọn dễ kiểm soát. Không nên khai báo image/png cho file chứa dữ liệu JPEG chỉ vì phần mở rộng tên file là png.

Các overload không truyền Content-Type có thể dựa vào cơ chế nhận diện file type của thư viện. Khi biết rõ dữ liệu, truyền media type tường minh giúp người đọc code hiểu ý định.

## 10. Thêm nhiều ảnh inline trong một thông điệp

Một email báo cáo có thể vừa có logo vừa có biểu đồ:

~~~html
<html>
  <body>
    <img src="cid:brandLogo" alt="Logo công ty">
    <h2>Báo cáo doanh thu</h2>
    <img src="cid:revenueChart" alt="Biểu đồ doanh thu">
  </body>
</html>
~~~

Java:

~~~java
helper.setText(html, true);

helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

helper.addInline(
        "revenueChart",
        new FileSystemResource(chartPath),
        "image/png"
);
~~~

Cấu trúc:

~~~text
multipart/related
├── text/html
│   ├── cid:brandLogo
│   └── cid:revenueChart
├── image/png  Content-ID: <brandLogo>
└── image/png  Content-ID: <revenueChart>
~~~

Mỗi ảnh có định danh riêng. Nếu dùng cùng một Content-ID cho hai ảnh khác nhau, việc tham chiếu có thể mơ hồ.

Ngược lại, nếu **cùng một ảnh** xuất hiện ở hai vị trí trong HTML, bạn có thể dùng cùng **cid:brandLogo** ở cả hai thẻ img. Trong trường hợp đó, một MIME part của logo thường đủ; không cần thêm cùng dữ liệu hai lần.

## 11. Thêm inline image cùng PDF attachment

Khi muốn HTML có logo và PDF để tải xuống, chọn mode **MIXED_RELATED**:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setFrom("reports@example.org");
helper.setTo("manager@example.net");
helper.setSubject("Báo cáo tháng 11");

helper.setText(
        "<html><body>"
      + "<img src=\"cid:brandLogo\" alt=\"Logo\">"
      + "<p>Vui lòng xem tệp PDF đính kèm.</p>"
      + "</body></html>",
        true
);

helper.addInline(
        "brandLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

helper.addAttachment(
        "report.pdf",
        new FileSystemResource(reportPath),
        "application/pdf"
);

mailSender.send(message);
~~~

Ví dụ này giả định **reportPath** là một biến Path được cấp cho phương thức và tệp PDF tồn tại, ứng dụng có quyền đọc.

Mô hình khái niệm:

~~~text
multipart/mixed
├── multipart/related
│   ├── text/html
│   └── image/png
│       └── Content-ID: <brandLogo>
└── application/pdf
    └── Content-Disposition: attachment
~~~

**addInline** tạo part ảnh dùng để hiển thị trong HTML; **addAttachment** tạo part file độc lập. Nếu chỉ gọi **addAttachment("logo.png", resource)**, HTML chứa **cid:brandLogo** không tự động có một part với Content-ID tương ứng.

Một số client có thể hiển thị cả ảnh inline trong danh sách attachment. Đó là đặc điểm trình bày của client, không làm thay đổi khác biệt giữa hai API.

## 12. Ví dụ raw MIME để hiểu Content-ID

Một email HTML có hình nhúng có thể được biểu diễn ở mức giao thức như sau:

~~~text
From: noreply@example.org
To: user@example.net
Subject: Welcome
MIME-Version: 1.0
Content-Type: multipart/related; boundary="related-123"

--related-123
Content-Type: text/html; charset=UTF-8

<html>
  <body>
    <p>Welcome!</p>
    <img src="cid:welcomeLogo" alt="Logo">
  </body>
</html>

--related-123
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-Disposition: inline
Content-ID: <welcomeLogo>

[base64-du-lieu-anh]

--related-123--
~~~

Dòng **[base64-du-lieu-anh]** chỉ là ký hiệu minh họa, không phải một PNG hợp lệ. Thông điệp thực tế có thể dùng encoding khác cho HTML, và các dòng MIME trên wire có dấu kết thúc CRLF. Thư viện mail tự xử lý các chi tiết đó.

Cần chú ý:

1. Header gốc khai báo **multipart/related**.
2. HTML và ảnh nằm trong hai MIME part.
3. Header Content-ID của ảnh trùng với định danh trong URL cid: của HTML.
4. Ảnh được vận chuyển dưới dạng dữ liệu mã hóa, rồi được client giải mã.
5. Cả hai part vẫn thuộc cùng một MimeMessage.

**Content-ID không cần trùng tên tệp.** Ví dụ ảnh được lấy từ file brand-logo.png nhưng có Content-ID **welcomeLogo** vẫn hoạt động nếu HTML cũng sử dụng **cid:welcomeLogo**.

## 13. Những lỗi thường gặp và nguyên nhân

### 13.1. HTML dùng một ID, addInline dùng ID khác

Ví dụ:

~~~html
<img src="cid:logo" alt="Logo">
~~~

~~~java
helper.addInline("companyLogo", resource, "image/png");
~~~

Do **logo** và **companyLogo** khác nhau, client không thể giải quyết tham chiếu theo ý định. Hãy thống nhất một định danh.

### 13.2. Truyền sẵn dấu ngoặc vào contentId

Ví dụ nên tránh:

~~~java
helper.addInline("<logo>", resource, "image/png");
~~~

Tham số là giá trị ID, không phải toàn bộ cú pháp header. Hãy truyền **logo**, và để helper tạo Content-ID thích hợp.

### 13.3. Tạo helper ở chế độ không multipart

Ví dụ:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
~~~

Cấu hình này không tạo multipart thích hợp cho inline resource. Hãy chọn **MULTIPART_MODE_RELATED**, **MULTIPART_MODE_MIXED_RELATED** hoặc constructor **true** trong tình huống phù hợp.

### 13.4. Gọi addInline trước setText

Thứ tự khuyến nghị:

~~~java
helper.setText(html, true);
helper.addInline("logo", resource, "image/png");
~~~

Một số client có thể nhạy cảm với thứ tự và cách các part được thiết lập. Spring Mail khuyến nghị **setText trước addInline**.

### 13.5. Đặt HTML nhưng lại dùng isHtml=false

Nếu code có:

~~~java
helper.setText(
        "<img src=\"cid:logo\" alt=\"Logo\">",
        false
);
~~~

nội dung sẽ được biểu diễn như văn bản thuần. Client có thể hiển thị nguyên cú pháp thẻ img, không render ảnh.

Dùng **setText(html, true)** hoặc **setText(plainText, htmlText)**.

### 13.6. Resource không tồn tại

**new ClassPathResource("mail/logo.png")** chỉ hoạt động khi tài nguyên thực sự có trên classpath runtime. Sau khi đóng gói JAR, đường dẫn **src/main/resources** không còn là đường dẫn file cần dùng trong mã.

Với FileSystemResource, phải kiểm soát thư mục làm việc, đường dẫn tương đối, quyền đọc và thời điểm file bị xóa.

### 13.7. Resource chỉ đọc được một lần

Jakarta Mail có thể yêu cầu mở lại nguồn dữ liệu. Một stream đã được đọc hết không tự mở lại. Dùng resource có thể truy cập lại, hoặc một InputStreamSource có khả năng cung cấp luồng mới.

### 13.8. Content-Type sai hoặc định dạng ảnh không được hỗ trợ

Ảnh JPEG nhưng khai báo image/png có thể gây lỗi hiển thị. Tương tự, SVG/WebP có thể không được một số client hỗ trợ tốt dù MIME được dựng đúng.

### 13.9. Ảnh chỉ tồn tại ở URL ngoài nhưng HTML dùng cid:

Nếu HTML dùng **cid:logo**, phải có part MIME với Content-ID tương ứng. Một file ảnh nằm trên web server nhưng không được thêm vào message bằng addInline không tự xuất hiện như part inline.

### 13.10. Dữ liệu ảnh quá lớn

Ảnh inline làm message nặng hơn. Với file vài MB, phần base64 và MIME header khiến kích thước vận chuyển tăng. SMTP provider có thể giới hạn message size; client cũng có thể tải hoặc render chậm.

Hãy tối ưu ảnh trước khi nhúng và giữ nội dung thiết yếu ở dạng text.

## 14. Khả năng tương thích email client

Một số client tự động hiển thị ảnh inline, số khác áp dụng chính sách riêng.

| Tình huống | Hệ quả có thể xảy ra |
| --- | --- |
| Client chọn bản plain text | Không render ảnh trong HTML |
| Client chặn hình ảnh | Ảnh không xuất hiện dù MIME đúng |
| Client không hỗ trợ định dạng ảnh | Part tồn tại nhưng không render |
| Client trình bày mọi part như tệp | Ảnh inline có thể xuất hiện trong attachment list |
| CSS email không được hỗ trợ đầy đủ | Kích thước/vị trí ảnh hiển thị khác kỳ vọng |
| HTML tham chiếu sai CID | Client không tìm được part tương ứng |

Không nên dùng ảnh làm phương tiện duy nhất truyền tải mã xác minh, nội dung quan trọng hoặc hướng dẫn bắt buộc. Cung cấp **alt text**, phần plain text và nội dung chữ đầy đủ.

Một HTML đơn giản thường dễ tương thích hơn:

~~~html
<img
  src="cid:companyLogo"
  alt="Logo công ty"
  width="160"
  style="display:block;max-width:100%;height:auto;">
~~~

Tuy nhiên, mức hỗ trợ CSS của email client có thể khác trình duyệt web; ngay cả HTML đơn giản cũng cần xem xét trên các client mục tiêu.

## 15. Bảo mật khi đưa tài nguyên vào email

### 15.1. Không dùng đường dẫn file tùy ý từ người dùng

Không nên làm:

~~~java
String path = request.getParameter("path");
helper.addInline(
        "image",
        new FileSystemResource(path),
        "image/png"
);
~~~

Nếu đường dẫn do client trực tiếp điều khiển, ứng dụng có thể đọc nhầm file hoặc gửi thông tin không được phép.

Nên ánh xạ một ID nghiệp vụ đã kiểm tra sang tài nguyên nằm trong thư mục được quản lý, hoặc dùng tài nguyên tĩnh trên classpath.

### 15.2. Chỉ nhúng tài nguyên được phép gửi

Một ảnh biểu đồ có thể chứa dữ liệu khách hàng hoặc thông tin nội bộ. Vì ảnh inline nằm trong message, người nhận có thể trích xuất dữ liệu của part. Đừng xem ảnh nhúng là nội dung khó tải hoặc an toàn hơn attachment.

### 15.3. Kiểm tra loại và kích thước file

Không nên tin hoàn toàn vào đuôi file do người dùng cung cấp. Nếu ứng dụng cho phép upload ảnh, cần kiểm tra media type thực tế, giới hạn kích thước và xử lý dữ liệu theo chính sách.

### 15.4. Escape nội dung động trong HTML

Nếu template email có:

~~~html
<p>Xin chào, {{displayName}}</p>
<img src="cid:companyLogo" alt="Logo">
~~~

thì giá trị **displayName** phải được escape theo ngữ cảnh HTML. Content-ID không tự bảo vệ phần HTML khỏi việc người dùng chèn markup không mong muốn.

### 15.5. Content-ID không phải secret

Giá trị ID nằm trong header MIME và HTML. Không đặt password, token truy cập hoặc mã xác thực nhạy cảm trong Content-ID.

### 15.6. Base64 không phải mã hóa bảo mật

Ảnh được base64 để vận chuyển, nhưng có thể giải mã trực tiếp. Bảo mật nội dung phụ thuộc vào quyền gửi, nhận và lưu trữ, không phải dạng mã hóa MIME.

## 16. Khi ảnh không hiển thị, nên quan sát điều gì?

Khi cần chẩn đoán một email không render ảnh, hãy tách thành hai tầng: **cấu trúc message** và **hành vi của client nhận thư**.

Ở tầng MIME:

- Body được đặt thành **text/html** chưa?
- HTML có đúng chuỗi **cid:** không?
- Có MIME part với **Content-ID** tương ứng không?
- Helper có bật chế độ multipart phù hợp không?
- **setText** được gọi trước **addInline** chưa?
- Resource có thể đọc tại thời điểm gửi không?
- **Content-Type** có phù hợp byte dữ liệu không?
- Kích thước message có nằm trong hạn mức không?

Ở tầng client:

- Client có chọn hiển thị HTML hay chỉ plain text?
- Client có chặn hình ảnh hoặc loại bỏ một kiểu media không?
- Client có hiển thị ảnh như attachment?
- CSS hoặc bố cục HTML có bị thay đổi không?

**send() hoàn tất không đồng nghĩa người nhận đã thấy ảnh.** SMTP server có thể chấp nhận message nhưng client cuối cùng vẫn không render một part như mong đợi.

Một email có ảnh lỗi ở client A nhưng hiển thị được ở client B có thể phản ánh sự khác biệt tương thích MIME hoặc chính sách của client. Việc đổi password SMTP sẽ không giải quyết vấn đề Content-ID không khớp.

Khi cần xem raw MIME trong môi trường phát triển, dùng hộp thư thử nghiệm hoặc SMTP capture server được kiểm soát. Tránh ghi nguyên email thật, địa chỉ và dữ liệu attachment nhạy cảm vào log production.

## 17. Các tình huống áp dụng

**Logo trong email chào mừng.** Dùng ClassPathResource cho ảnh tĩnh, **helper.setText(plain, html)** và **helper.addInline("companyLogo", logo, "image/png")**. Đảm bảo HTML tham chiếu **cid:companyLogo**.

**Biểu đồ báo cáo hàng ngày.** Ứng dụng tạo một file hoặc byte PNG, dùng FileSystemResource hoặc ByteArrayResource, đặt Content-ID như **dailyChart** và tham chiếu từ HTML.

**Thông báo có hai ảnh.** Thêm hai MIME part với hai Content-ID khác nhau. HTML chứa hai thẻ img có đúng tham chiếu tương ứng.

**Email báo cáo có logo và PDF.** Dùng **MULTIPART_MODE_MIXED_RELATED**. Logo được thêm qua addInline; PDF dùng addAttachment.

**Cần hoạt động cả khi người nhận không xem HTML.** Dùng **setText(plainText, htmlText)** và bảo đảm phần plain text chứa đủ thông tin để hiểu message.

## 18. Câu hỏi thường gặp

**Có cần gọi send riêng cho từng ảnh không?**

Không. **addInline** thêm MIME part vào cùng một message; sau khi dựng xong, gọi send cho toàn bộ thông điệp.

**Content-ID có phải tên file?**

Không. Đó là định danh để HTML tìm MIME part. Resource có thể là **logo.png** nhưng Content-ID là **companyLogo**.

**HTML có cần dùng src="cid:<companyLogo>" không?**

Với cách dùng thông thường của **MimeMessageHelper**, không. HTML dùng **src="cid:companyLogo"**; helper tạo header dạng Content-ID có dấu ngoặc.

**Có nhất thiết dùng MIXED_RELATED không?**

Không. **RELATED** phù hợp với HTML và inline resource. **MIXED_RELATED** thuận tiện khi còn có attachment độc lập.

**new MimeMessageHelper(message, true) có dùng được không?**

Có. Constructor boolean true của Spring Framework kích hoạt chế độ multipart mặc định **MIXED_RELATED**.

**Tại sao nên gọi setText trước addInline?**

Vì các client có thể nhạy cảm với cách các part được bố trí. Spring Mail khuyến nghị thiết lập body trước khi thêm inline resource.

**Có thể thêm ảnh JPEG thay PNG không?**

Có. Chọn **image/jpeg** nếu byte dữ liệu thật là JPEG. Không khai báo sai MIME type.

**Ảnh CID có chắc chắn không bị chặn không?**

Không. Client có thể ẩn ảnh, chọn bản text hoặc không hỗ trợ định dạng. Nội dung chính vẫn nên có ở dạng văn bản.

**Một ảnh xuất hiện nhiều lần có cần nhiều addInline không?**

Thông thường không. Nhiều thẻ img có thể cùng dùng **cid:companyLogo** để tham chiếu một MIME part.

**Có thể đưa URL HTTPS vào addInline không?**

addInline cần nguồn dữ liệu resource/stream phù hợp. Nếu muốn nhúng ảnh lấy từ web, ứng dụng cần tải dữ liệu theo chính sách cho phép và cung cấp nguồn byte; hoặc để URL HTTPS trong HTML và chấp nhận việc client có thể chặn tải ảnh từ xa.

## 19. Ghi nhớ về Content-ID và MimeMessageHelper

**Content-ID** là định danh của một MIME part. HTML tham chiếu tới part qua URL **cid:**. Trong Spring Framework Mail, sự liên kết thường được tạo bằng **helper.addInline("companyLogo", resource, "image/png")** và **src="cid:companyLogo"**.

Để gửi HTML có ảnh inline, tạo **MimeMessage**, chọn chế độ multipart phù hợp, gọi **setText** trước **addInline** và sử dụng một resource có thể đọc lại. Khi có cả tệp độc lập để tải về, cấu trúc **mixed/related** giúp phân biệt nội dung có liên quan với attachment.

Một email có thể chứa nhiều ảnh inline mà vẫn chỉ là một message. Khả năng hiển thị cuối cùng phụ thuộc cấu trúc MIME, loại dữ liệu và email client; vì thế nên kèm văn bản rõ ràng, alt text, kích thước ảnh hợp lý và chính sách kiểm soát tài nguyên đầu vào.
