# Thứ tự tạo HTML và thêm resource

## 1. Inline resource trong email HTML là gì?

Trong **Spring Framework Mail**, ứng dụng có thể gửi email HTML có logo, biểu tượng, ảnh chữ ký hoặc hình minh họa hiển thị ngay trong nội dung. Những tài nguyên này thường được gọi là **inline resource**: ảnh được đóng gói thành một MIME body part riêng, còn HTML tham chiếu đến part đó bằng một địa chỉ **Content-ID (CID)**.

Ví dụ HTML:

~~~html
<img src="cid:company-logo" alt="Company logo">
~~~

Khi tạo MIME message, ứng dụng cần thêm một image part có Content-ID tương ứng với `company-logo`. Email client kết hợp phần HTML với image part để hiển thị ảnh ngay trong nội dung thư.

~~~text
Email HTML
   |
   | <img src="cid:company-logo">
   |
   v
MIME message
   |
   +-- text/html body part
   |      |
   |      +-- tham chiếu cid:company-logo
   |
   +-- image/png body part
          |
          +-- Content-ID: <company-logo>
          +-- Content-Disposition: inline
          +-- dữ liệu ảnh
~~~

Điểm quan trọng của bài này là **thứ tự thao tác khi dùng MimeMessageHelper**:

1. Tạo HTML string có chứa các tham chiếu `cid:...`.
2. Gọi `MimeMessageHelper.setText(...)` để thiết lập body HTML (và text/plain nếu có).
3. Gọi `MimeMessageHelper.addInline(...)` để thêm các resource được HTML tham chiếu.
4. Nếu có file đính kèm tải xuống, thêm chúng bằng `addAttachment(...)`.
5. Gửi message bằng `JavaMailSender`.

Tài liệu API của Spring nhấn mạnh **phải gọi addInline sau setText**. Nếu thêm inline resource trước khi đặt body, một số mail reader có thể không phân giải được tham chiếu CID đúng cách do cấu trúc multipart chưa được thiết lập theo thứ tự mong đợi.

## 2. Phân biệt inline resource và attachment

Inline resource và attachment đều là MIME body part, nhưng mục đích hiển thị khác nhau:

| Đặc điểm | Inline resource | Attachment |
|---|---|---|
| Mục đích | Hiển thị trực tiếp trong body HTML | Cho người nhận tải hoặc mở riêng |
| HTML tham chiếu | Thường dùng `src="cid:..."` | Không cần HTML tham chiếu |
| Content-ID | Có để HTML liên kết tới part | Thường không cần |
| Content-Disposition | Thường là `inline` | Thường là `attachment` |
| Spring API | `addInline(...)` | `addAttachment(...)` |
| Ví dụ | Logo, ảnh chữ ký, sơ đồ nhúng | PDF hóa đơn, file Excel, tài liệu |

Một ảnh được thêm bằng `addAttachment("logo.png", resource)` không tự trở thành ảnh hiển thị trong HTML. Ngược lại, ảnh thêm bằng `addInline("company-logo", resource)` không nhất thiết xuất hiện như một tệp đính kèm thông thường trong mọi email client.

Nếu email có cả logo hiển thị trong body và PDF cho người nhận tải xuống, cần tạo **hai part riêng**: một inline image với CID và một attachment có filename.

## 3. Vì sao phải gọi setText trước addInline?

`MimeMessageHelper` không chỉ thêm chuỗi HTML vào một field. Khi làm việc ở chế độ multipart, helper tạo và quản lý cây MIME, gồm các phần nội dung và các tài nguyên liên quan.

Nếu gọi `setText(html, true)` trước, helper đã biết body HTML và có thể thiết lập phần MIME liên quan. Sau đó `addInline(...)` mới gắn image part vào vùng multipart phù hợp để client giải quyết `cid:` reference.

Thứ tự nên dùng:

~~~text
Tạo MimeMessage
      |
      v
Tạo MimeMessageHelper (multipart = true)
      |
      v
Tạo HTML String chứa cid:logo
      |
      v
helper.setText(html, true)
      |
      v
helper.addInline("logo", logoResource)
      |
      v
mailSender.send(message)
~~~

Ví dụ thứ tự không nên dùng:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.addInline("logo", logoResource); // Gọi quá sớm
helper.setText(html, true);
~~~

Không nên dựa vào việc một email client cụ thể vẫn hiển thị được khi đảo thứ tự. Hãy theo trình tự được Spring khuyến nghị để cấu trúc MIME nhất quán.

**Lưu ý:** HTML string cần được tạo trước `setText` vì nó chứa CID mà body sẽ tham chiếu. Nhưng việc **đính kèm resource vào MimeMessage** bằng `addInline` phải thực hiện sau khi đã gọi `setText`.

## 4. Ví dụ hoàn chỉnh: HTML tham chiếu logo bằng CID

Giả sử logo được đóng gói trong classpath:

~~~text
src/main/resources/
└── mail/
    └── images/
        └── company-logo.png
~~~

Service tạo email:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class BrandedMailService {
    private final JavaMailSender mailSender;

    public BrandedMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendWelcome(String recipient)
            throws MessagingException {
        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                true,
                StandardCharsets.UTF_8.name());

        String html = """
                <!doctype html>
                <html lang="vi">
                  <head><meta charset="UTF-8"></head>
                  <body>
                    <div>
                      <img src="cid:company-logo"
                           alt="Company logo"
                           width="160">
                    </div>
                    <h1>Chào mừng bạn!</h1>
                    <p>Tài khoản của bạn đã sẵn sàng.</p>
                  </body>
                </html>
                """;

        helper.setFrom("welcome@example.com");
        helper.setTo(recipient);
        helper.setSubject("Chào mừng bạn đến với dịch vụ");

        // 1. Đặt nội dung HTML trước.
        helper.setText(html, true);

        // 2. Sau đó thêm resource mà HTML tham chiếu.
        helper.addInline(
                "company-logo",
                new ClassPathResource("mail/images/company-logo.png"));

        mailSender.send(message);
    }
}
~~~

Trong ví dụ:

- `true` trong `MimeMessageHelper` bật chế độ multipart.
- HTML dùng `src="cid:company-logo"`.
- `addInline("company-logo", ...)` dùng cùng ID, không có tiền tố `cid:`.
- `ClassPathResource` đọc ảnh đã đóng gói trong ứng dụng.
- `setText(...)` được gọi trước `addInline(...)`.

**Content-ID phải khớp chính xác** giữa HTML và tham số `contentId` truyền vào helper. Nếu HTML tham chiếu `cid:company-logo` nhưng code thêm `addInline("logo", ...)`, email client không tìm thấy part tương ứng và ảnh có thể bị mất.

## 5. Thứ tự khi email có cả text/plain, HTML và inline image

Email HTML thường nên có thêm phiên bản **text/plain** để hỗ trợ email client không render HTML. Khi dùng `MimeMessageHelper.setText(plainText, htmlText)`, helper tạo các part thay thế cho cùng một nội dung.

Ví dụ:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

String plainText = """
        Xin chào!
        Đây là thông báo tài khoản của bạn.
        """;

String htmlText = """
        <html lang="vi">
          <body>
            <img src="cid:brand-mark" alt="Brand">
            <h1>Xin chào!</h1>
            <p>Đây là thông báo tài khoản của bạn.</p>
          </body>
        </html>
        """;

helper.setText(plainText, htmlText);
helper.addInline(
        "brand-mark",
        new ClassPathResource("mail/images/brand-mark.png"));
~~~

Thứ tự vẫn là:

1. Chuẩn bị cả hai chuỗi plain text và HTML.
2. Gọi `setText(plainText, htmlText)`.
3. Gọi `addInline(...)` cho từng resource được HTML tham chiếu.
4. Gửi message.

Inline image chỉ được tham chiếu từ HTML body. Phiên bản text/plain không cần và không nên chứa `cid:` URI như thể đó là đường dẫn văn bản thông thường.

### Cấu trúc MIME khái quát

Với multipart alternative và inline resource, cây MIME có thể lồng nhiều lớp:

~~~text
multipart/mixed
  |
  +-- multipart/related
  |     |
  |     +-- multipart/alternative
  |     |     |
  |     |     +-- text/plain
  |     |     +-- text/html
  |     |
  |     +-- image/png
  |           Content-ID: <brand-mark>
  |
  +-- application/pdf
        Content-Disposition: attachment
~~~

Đây là sơ đồ khái niệm về các quan hệ MIME. Cấu trúc lồng cụ thể phụ thuộc multipart mode và cách helper dựng message; không nên viết test giả định mọi part luôn nằm ở cùng một chỉ số trong multipart ngoài cùng.
## 6. Thêm nhiều inline resource

Một email có thể chứa nhiều hình: logo đầu thư, ảnh sản phẩm, biểu tượng mạng xã hội và chữ ký. Mỗi resource có một Content-ID riêng, và HTML phải tham chiếu đúng ID tương ứng.

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

String html = """
        <html lang="vi">
          <body>
            <img src="cid:brand-logo" alt="Brand" width="140">
            <h1>Đơn hàng của bạn</h1>
            <img src="cid:product-photo"
                 alt="Ảnh sản phẩm"
                 width="240">
            <p>
              <img src="cid:support-icon"
                   alt=""
                   width="20">
              Liên hệ bộ phận hỗ trợ nếu cần giúp đỡ.
            </p>
          </body>
        </html>
        """;

helper.setText(html, true);

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/brand-logo.png"));
helper.addInline(
        "product-photo",
        new ClassPathResource("mail/images/product-photo.jpg"));
helper.addInline(
        "support-icon",
        new ClassPathResource("mail/images/support-icon.png"));

mailSender.send(message);
~~~

Thứ tự vẫn giữ nguyên: **setText trước, tất cả addInline sau**. Không cần gọi setText lại sau mỗi ảnh. Khi thêm một resource mới, cần đồng thời thêm thẻ HTML tham chiếu CID tương ứng.

Quy tắc quản lý ID:

- Mỗi nội dung ảnh khác nhau nên có Content-ID riêng trong message.
- Nếu cùng một ảnh được dùng nhiều lần trong HTML, có thể dùng lại cùng CID để các vị trí tham chiếu cùng một part.
- Không dùng một CID cho hai ảnh khác nhau trong cùng message.
- ID nên đơn giản, ổn định trong message, tránh dấu cách và ký tự đặc biệt.
- Không đưa tên file hoặc đường dẫn filesystem vào CID; CID là định danh MIME, không phải đường dẫn đọc file.

## 7. Dùng Content-ID động khi tạo HTML từ template

Với template engine, CID có thể được sinh trong code rồi truyền vào model. Điều quan trọng là **cùng một giá trị** phải được dùng ở hai nơi:

1. HTML sinh ra `src="cid:<id>"`.
2. `addInline("<id>", resource)` dùng đúng `<id>` đó.

Ví dụ với một CID cố định:

~~~java
String logoCid = "brand-logo";
String html = """
        <html><body>
          <img src="cid:%s" alt="Brand">
        </body></html>
        """.formatted(logoCid);

helper.setText(html, true);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/images/brand-logo.png"));
~~~

Nếu nhiều email được tạo độc lập, có thể dùng ID riêng cho từng message:

~~~java
import java.util.UUID;

String logoCid = "logo-" + UUID.randomUUID();
String html = """
        <html><body>
          <img src="cid:%s" alt="Brand">
        </body></html>
        """.formatted(logoCid);

helper.setText(html, true);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/images/brand-logo.png"));
~~~

CID động không bắt buộc nếu message được tách riêng và ID cố định không gây xung đột. Ưu điểm của ID động là giảm nguy cơ hai part vô tình dùng chung Content-ID khi một message được ghép từ nhiều module hoặc nhiều đoạn template.

### Ví dụ với Thymeleaf

Template có thể nhận biến CID:

~~~html
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<body>
  <img th:src="'cid:' + ${logoCid}"
       alt="Brand"
       width="140">
  <h1 th:text="${title}">Thông báo</h1>
</body>
</html>
~~~

Renderer đặt biến và tạo HTML trước:

~~~java
String logoCid = "brand-logo";

Context context = new Context(Locale.forLanguageTag("vi-VN"));
context.setVariable("logoCid", logoCid);
context.setVariable("title", "Chào mừng bạn!");

String html = templateEngine.process("mail/welcome", context);

helper.setText(html, true);
helper.addInline(
        logoCid,
        new ClassPathResource("mail/images/brand-logo.png"));
~~~

**Không thêm inline resource trước khi render hoặc trước setText.** Có thể chuẩn bị object Resource từ sớm, nhưng thao tác gắn nó vào MimeMessage bằng addInline chỉ thực hiện sau setText. Điều này giúp code thể hiện đúng thứ tự và dễ đọc khi template có nhiều CID.

## 8. Chọn Resource phù hợp

Spring cung cấp nhiều kiểu Resource để đọc nội dung ảnh. Chọn theo nơi lưu trữ và vòng đời dữ liệu:

| Resource | Nguồn dữ liệu | Trường hợp phù hợp |
|---|---|---|
| `ClassPathResource` | File đóng gói trong classpath/JAR | Logo, icon hoặc ảnh thương hiệu cố định |
| `FileSystemResource` | File trên filesystem | Ảnh được lưu trong thư mục do ứng dụng quản lý |
| `ByteArrayResource` | Mảng byte trong bộ nhớ | Ảnh đã được tải/biến đổi và có kích thước phù hợp |
| `InputStreamSource` | Cung cấp stream theo yêu cầu | Tích hợp nguồn dữ liệu có thể mở lại stream |

### ClassPathResource

~~~java
Resource logo = new ClassPathResource("mail/images/logo.png");
helper.addInline("logo", logo);
~~~

Đường dẫn classpath thường không có dấu slash ở đầu. Resource được đọc từ classpath và vẫn có thể hoạt động khi ứng dụng được đóng gói thành JAR, không cần giả định có file vật lý tại thư mục làm việc.

### FileSystemResource

~~~java
Resource chart = new FileSystemResource(
        "/var/app/mail-assets/monthly-chart.png");
helper.addInline("monthly-chart", chart);
~~~

Đường dẫn filesystem phải tồn tại và runtime phải có quyền đọc. Trong container, đường dẫn này phải được mount hoặc tạo trong filesystem của container. Không lấy một đường dẫn do người dùng gửi trực tiếp rồi mở tùy ý; hãy giới hạn vào thư mục đã được ứng dụng quản lý.

### ByteArrayResource

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] imageBytes = imageService.createSmallPreview();
helper.addInline(
        "preview-image",
        new ByteArrayResource(imageBytes),
        "image/png");
~~~

ByteArrayResource phù hợp khi ảnh đã có sẵn dưới dạng byte array và kích thước được kiểm soát. Với ảnh lớn, việc giữ toàn bộ byte trong heap có thể tăng áp lực bộ nhớ; nên cân nhắc Resource dạng file hoặc một nguồn stream có thể mở lại.

### InputStreamSource phải có khả năng mở stream phù hợp

Overload nhận InputStreamSource yêu cầu nguồn dữ liệu cung cấp stream để thư viện đọc. Một số quy trình serialize có thể cần mở stream nhiều lần. Vì vậy, nguồn nên tạo **InputStream mới cho mỗi lần getInputStream()**; không dùng một stream đã đọc hết hoặc đã đóng.

~~~java
import java.io.ByteArrayInputStream;
import org.springframework.core.io.InputStreamSource;

byte[] imageBytes = imageService.createSmallPreview();
InputStreamSource source =
        () -> new ByteArrayInputStream(imageBytes);

helper.addInline("preview-image", source, "image/png");
~~~

Ví dụ này giữ byte array trong bộ nhớ nhưng tạo stream mới mỗi lần được yêu cầu. Với nguồn file, ClassPathResource hoặc FileSystemResource thường rõ ràng và thuận tiện hơn.

**Tránh InputStreamResource dựa trên một InputStream đơn lẻ đã mở** nếu thư viện có thể đọc resource nhiều lần. Một nguồn one-shot có thể đã cạn hoặc đóng ở lần đọc tiếp theo, dẫn đến lỗi khi serialize message.

## 9. Chỉ định Content-Type đúng cho resource

Inline image cần có media type phù hợp, ví dụ:

| Định dạng | Content-Type |
|---|---|
| PNG | `image/png` |
| JPEG/JPG | `image/jpeg` |
| GIF | `image/gif` |
| SVG | `image/svg+xml` |
| WebP | `image/webp` |

Với overload nhận Resource, helper thường suy luận content type dựa trên tên file hoặc FileTypeMap. Với định dạng không phổ biến hoặc nguồn không có filename đáng tin cậy, nên cung cấp content type tường minh:

~~~java
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/brand-logo.png"),
        "image/png");
~~~

Không khai báo ảnh JPEG là image/png chỉ vì file có đuôi png; content type phải phản ánh **định dạng byte thực tế**. Nếu header nói image/png nhưng dữ liệu là JPEG, một số client có thể không hiển thị ảnh.

### SVG và khả năng tương thích

SVG là ảnh vector nhưng hỗ trợ SVG trong email client không đồng đều. Một số client chặn hoặc không render SVG inline vì lý do bảo mật/tương thích. Với email cần hiển thị rộng rãi, PNG hoặc JPEG thường là lựa chọn an toàn hơn. Nếu dùng SVG, cần kiểm tra trên các client mục tiêu và tránh nhúng script hoặc nội dung không tin cậy.

### Resource không phải HTML fragment

`addInline` dành cho nội dung resource như ảnh, không phải cách để chèn một đoạn HTML vào body. Nếu cần thêm nội dung HTML, hãy render nó vào chuỗi HTML trước setText; chỉ các binary/resource được tham chiếu bằng CID mới được thêm qua addInline.
## 10. Kết hợp inline image và attachment trong cùng email

Một email xác nhận có thể dùng logo hiển thị trong HTML và đính kèm hóa đơn PDF. Khi đó cần phân biệt rõ:

- Logo: được HTML tham chiếu bằng CID, thêm qua `addInline`.
- Hóa đơn PDF: người nhận tải xuống, thêm qua `addAttachment`.

Ví dụ:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

String html = """
        <html lang="vi">
          <body>
            <img src="cid:invoice-brand" alt="Company" width="140">
            <h1>Hóa đơn của bạn</h1>
            <p>Hóa đơn PDF được đính kèm trong email này.</p>
          </body>
        </html>
        """;

helper.setFrom("billing@example.com");
helper.setTo("customer@example.net");
helper.setSubject("Hóa đơn điện tử");

// Thiết lập body trước.
helper.setText(html, true);

// Thêm resource inline được HTML tham chiếu.
helper.addInline(
        "invoice-brand",
        new ClassPathResource("mail/images/invoice-brand.png"));

// Thêm file người nhận tải xuống.
helper.addAttachment(
        "hoa-don.pdf",
        new FileSystemResource("/var/app/invoices/invoice-2026-001.pdf"));

mailSender.send(message);
~~~

`addAttachment` có thể được gọi sau khi đã thiết lập nội dung và inline resource. Tên file attachment là metadata hiển thị cho người nhận; nó không phải Content-ID và không được dùng trong `src="cid:..."`.

Với message có nhiều loại part, helper tạo cấu trúc multipart để phân biệt nội dung liên quan và file đính kèm. Hãy để helper quản lý cấu trúc đó, trừ khi ứng dụng có yêu cầu MIME đặc biệt cần sử dụng trực tiếp Jakarta Mail.

## 11. Tạo HTML từ template rồi mới gắn resource

Trong ứng dụng thực tế, HTML thường đến từ Thymeleaf, FreeMarker hoặc một template engine khác. Thứ tự xử lý nên tách thành hai giai đoạn:

1. **Render nội dung**: tạo chuỗi HTML hoàn chỉnh, trong đó các thẻ ảnh đã có CID.
2. **Compose MIME**: gọi setText với HTML đã render, sau đó addInline từng resource theo CID.

Ví dụ với một renderer:

~~~java
public record InlineImage(
        String contentId,
        org.springframework.core.io.Resource resource,
        String contentType) {
}

public record RenderedMail(
        String subject,
        String html,
        java.util.List<InlineImage> inlineImages) {
}
~~~

Renderer có thể trả về cả HTML và danh sách resource cần gắn:

~~~java
public RenderedMail renderWelcome(String customerName) {
    String logoCid = "welcome-logo";

    Context context = new Context(Locale.forLanguageTag("vi-VN"));
    context.setVariable("customerName", customerName);
    context.setVariable("logoCid", logoCid);

    String html = templateEngine.process("mail/welcome", context);

    InlineImage logo = new InlineImage(
            logoCid,
            new ClassPathResource("mail/images/logo.png"),
            "image/png");

    return new RenderedMail(
            "Chào mừng bạn",
            html,
            java.util.List.of(logo));
}
~~~

Mail composer sử dụng kết quả:

~~~java
public void sendRendered(
        String recipient,
        RenderedMail rendered) throws MessagingException {

    MimeMessage message = mailSender.createMimeMessage();
    MimeMessageHelper helper = new MimeMessageHelper(
            message, true, StandardCharsets.UTF_8.name());

    helper.setFrom("welcome@example.com");
    helper.setTo(recipient);
    helper.setSubject(rendered.subject());

    // Giai đoạn 1: tạo body MIME từ HTML đã render.
    helper.setText(rendered.html(), true);

    // Giai đoạn 2: gắn tất cả inline resource sau setText.
    for (InlineImage inlineImage : rendered.inlineImages()) {
        helper.addInline(
                inlineImage.contentId(),
                inlineImage.resource(),
                inlineImage.contentType());
    }

    mailSender.send(message);
}
~~~

Hai record là DTO do ứng dụng tự định nghĩa, không phải kiểu có sẵn của Spring. Thiết kế này giúp template renderer không phải biết MimeMessageHelper, còn mail composer không phải tự tìm và phân tích thẻ HTML để đoán ảnh nào cần đính kèm.

### Kiểm tra hợp đồng giữa template và danh sách resource

Nếu template tham chiếu `cid:welcome-logo` nhưng renderer không đưa resource có Content-ID `welcome-logo` vào danh sách, email có thể gửi thành công nhưng ảnh không hiển thị. Ngược lại, danh sách có resource không được HTML tham chiếu sẽ làm message lớn hơn mà không mang lại lợi ích.

Có thể kiểm tra trong test:

- Mỗi CID trong template có một resource tương ứng.
- Không có hai resource khác nhau dùng chung CID.
- Không có resource không cần thiết nếu chính sách yêu cầu tối ưu dung lượng.
- MIME part có Content-Type đúng với byte ảnh.

Đây là hợp đồng giữa **template** và **mail composer**; SMTP server thường không kiểm tra rằng mọi CID trong HTML đều có image part tương ứng.

## 12. Những lỗi thường gặp khi thứ tự hoặc CID không đúng

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Email gửi thành công nhưng ảnh không hiện | CID trong HTML không khớp contentId | Dùng cùng ID ở src và addInline |
| Ảnh hiện thành attachment rời | Dùng addAttachment thay vì addInline | Chuyển sang addInline cho ảnh hiển thị trong HTML |
| Ảnh mất khi đảo thứ tự lệnh | addInline được gọi trước setText | Gọi setText trước rồi addInline |
| IllegalStateException khi addInline | Helper được tạo ở chế độ không multipart | Tạo MimeMessageHelper với multipart=true hoặc mode phù hợp |
| ResourceNotFoundException/IOException | Đường dẫn classpath/filesystem sai hoặc không có quyền đọc | Kiểm tra resource path và quyền runtime |
| Ảnh có tên đúng nhưng không hiển thị | Content-Type không khớp định dạng byte | Chỉ định image/png, image/jpeg... đúng |
| Ảnh chỉ hiện trong môi trường IDE | File nằm ngoài classpath khi đóng gói JAR | Đặt ảnh trong resources và dùng ClassPathResource |
| Email có dung lượng lớn bất thường | Ảnh quá lớn hoặc cùng ảnh bị nhúng nhiều lần | Resize/nén và tái sử dụng CID phù hợp |
| Template có CID nhưng part không tồn tại | Renderer quên thêm resource vào danh sách | Kiểm tra mapping template-resource |
| Ảnh bị lẫn giữa các message | Tái sử dụng MimeMessage mutable hoặc mapping resource không đúng | Tạo message và mapping riêng cho mỗi email |

### Lỗi thứ tự thường gặp

Không nên:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.addInline("logo", logoResource);
helper.setText(html, true);
~~~

Nên:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText(html, true);
helper.addInline("logo", logoResource);
~~~

Điểm khác biệt là thời điểm helper tạo body multipart. Theo hướng dẫn của Spring, inline resource cần được thêm **sau khi nội dung text đã được thiết lập** để các mail reader có thể liên kết CID đúng cách.

## 13. Kiểm tra MIME message mà không gửi SMTP

Khi ảnh không hiển thị, có thể kiểm tra message đã tạo trước khi gọi JavaMailSender.send. Dùng Jakarta Mail để xem MIME part và Content-ID:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Properties;
import jakarta.mail.Session;

MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

String html = """
        <html><body>
          <img src="cid:test-logo" alt="Logo">
        </body></html>
        """;

helper.setText(html, true);
helper.addInline(
        "test-logo",
        new ClassPathResource("mail/images/logo.png"),
        "image/png");

message.saveChanges();

ByteArrayOutputStream output = new ByteArrayOutputStream();
message.writeTo(output);

Session session = Session.getInstance(new Properties());
MimeMessage parsed = new MimeMessage(
        session,
        new ByteArrayInputStream(output.toByteArray()));

Object content = parsed.getContent();
if (content instanceof Multipart multipart) {
    // Duyệt các body part và tìm part có Content-ID.
}
~~~

Ví dụ serialize rồi parse lại message để kiểm tra **MIME thực tế**, không chỉ các lời gọi helper. Đối với message lồng multipart, cần duyệt đệ quy:

~~~java
static void inspectPart(Part part) throws Exception {
    String[] contentIds = part.getHeader("Content-ID");
    if (contentIds != null) {
        System.out.println("Content-ID: " + contentIds[0]);
    }

    Object content = part.getContent();
    if (content instanceof Multipart multipart) {
        for (int i = 0; i < multipart.getCount(); i++) {
            inspectPart(multipart.getBodyPart(i));
        }
    }
}
~~~

Gọi:

~~~java
inspectPart(parsed);
~~~

Đoạn inspect chỉ minh họa cách duyệt part và in Content-ID trong môi trường test. Không in toàn bộ nội dung email hoặc dữ liệu nhạy cảm trong production log. Khi cần xác nhận part ảnh, có thể kiểm tra thêm isMimeType("image/png"), Content-Disposition và Content-ID sau khi parse.

**Không giả định image part nằm ở index cố định.** Khi message có text/plain, text/html, ảnh inline và attachment, MIME có thể lồng nhiều multipart. Duyệt đệ quy hoặc tìm theo media type/Content-ID đáng tin cậy hơn.
## 14. CID inline image hay ảnh từ URL bên ngoài?

Có hai cách phổ biến để HTML email hiển thị ảnh:

1. **CID inline image**: ứng dụng đóng gói ảnh thành MIME part và HTML tham chiếu bằng `cid:...`.
2. **Remote image**: HTML tham chiếu URL HTTPS của ảnh trên máy chủ bên ngoài.

| Tiêu chí | CID inline | Remote image URL |
|---|---|---|
| Dữ liệu ảnh | Nằm trong email MIME | Được tải từ máy chủ khi client hiển thị |
| Cần addInline | Có | Không |
| Dung lượng email | Tăng theo kích thước ảnh và transfer encoding | Nhỏ hơn vì chỉ chứa URL |
| Cần mạng khi mở thư | Không cần tải ảnh từ website ngoài | Cần client truy cập URL |
| Quyền riêng tư | Không tạo request tải ảnh đến máy chủ ảnh khi mở thư | Có thể làm lộ thời điểm mở thư, IP hoặc thông tin request |
| Khả năng hiển thị | Phụ thuộc hỗ trợ CID của email client | Có thể bị chặn ảnh từ xa theo chính sách client |

Remote image:

~~~html
<img src="https://cdn.example.com/mail/logo.png"
     alt="Company"
     width="140">
~~~

CID image:

~~~html
<img src="cid:company-logo"
     alt="Company"
     width="140">
~~~

Remote image giúp email nhẹ hơn nhưng người nhận có thể phải cho phép tải ảnh bên ngoài. Các request tải ảnh còn có thể được dùng để theo dõi việc mở thư; cần xem xét quyền riêng tư và chính sách tổ chức. CID image tăng dung lượng MIME nhưng không phụ thuộc máy chủ ảnh khi mở email.

**Không có cách nào bảo đảm mọi email client đều hiển thị ảnh.** Client có thể ẩn ảnh inline, giới hạn loại ảnh, hoặc áp dụng chính sách bảo mật riêng. Với logo hoặc ảnh quan trọng, hãy cung cấp alt text và bảo đảm thông tin thiết yếu vẫn đọc được khi ảnh không hiển thị.

### Không nên dùng data URI làm phương án thay thế phổ quát

Một số trang web có thể nhúng ảnh trực tiếp bằng URL dạng data URI:

~~~html
<img src="data:image/png;base64,..." alt="Logo">
~~~

Hỗ trợ data URI trong email client không đồng đều; nhiều client loại bỏ hoặc không hiển thị. Với Spring Mail, khi cần ảnh nhúng có khả năng tương thích tốt hơn, dùng CID và addInline theo cấu trúc MIME.

### Ưu tiên thẻ img cho ảnh inline

Ảnh trong CSS background, pseudo-element hoặc cấu trúc CSS phức tạp có thể không được email client hỗ trợ nhất quán. Với logo, icon hoặc ảnh sản phẩm, thẻ `img` có `src="cid:..."`, `alt` và kích thước rõ ràng thường dễ tương thích hơn.

## 15. Tối ưu kích thước và cách hiển thị ảnh

Inline resource được đóng gói vào MIME message nên byte ảnh làm tăng kích thước email. Dữ liệu nhị phân thường được transfer-encode, chẳng hạn Base64, nên phần truyền đi có thể lớn hơn file ảnh gốc.

Những thực hành nên áp dụng:

- Resize ảnh theo kích thước hiển thị thực tế; không nhúng ảnh 4000 pixel nếu email chỉ hiển thị rộng 140 pixel.
- Nén PNG/JPEG phù hợp nội dung; logo phẳng có thể dùng PNG tối ưu, ảnh chụp thường phù hợp JPEG.
- Tránh nhúng nhiều bản sao của cùng một ảnh với CID khác nhau nếu có thể tham chiếu cùng một part.
- Chỉ thêm resource thực sự được HTML sử dụng.
- Dùng alt text mô tả ảnh có ý nghĩa; ảnh trang trí có thể dùng alt rỗng.
- Khai báo width/height hợp lý để layout ít thay đổi khi ảnh tải hoặc bị ẩn.
- Kiểm tra tổng kích thước MIME của cả message, bao gồm body, inline resource và attachment.

Ví dụ ảnh trang trí:

~~~html
<img src="cid:divider-image" alt="" width="600">
~~~

Ví dụ ảnh mang thông tin:

~~~html
<img src="cid:product-photo"
     alt="Bàn phím cơ màu trắng"
     width="240">
~~~

Nếu ảnh bị ẩn, alt text giúp người nhận hiểu ý nghĩa của nội dung. Đối với ảnh trang trí, alt rỗng tránh screen reader đọc một tên file hoặc mô tả không cần thiết.

### Dung lượng ảnh và giới hạn email

Giả sử email có logo 80 KB, ảnh sản phẩm 450 KB và PDF attachment 2 MB. Tổng byte file nguồn chưa phải kích thước cuối của email: ảnh và PDF có thể được mã hóa Base64, MIME còn thêm header, boundary, body text và các part khác. Do đó cần có headroom so với giới hạn provider.

Không nên chỉ kiểm tra kích thước của từng file inline. Một template có nhiều ảnh nhỏ hoặc một vòng lặp tạo ảnh cho từng sản phẩm vẫn có thể làm tổng message vượt hạn mức.

## 16. Bảo vệ đường dẫn và nguồn resource

Resource inline thường được lấy từ classpath, filesystem hoặc kho lưu trữ. Cần bảo đảm ứng dụng chỉ đính kèm tài nguyên mà nó được phép đọc và gửi:

- **Không dùng path do người dùng cung cấp trực tiếp** để tạo FileSystemResource; có thể dẫn đến đọc file ngoài thư mục cho phép.
- Nếu người dùng chọn ảnh, lưu ảnh vào vùng lưu trữ được quản lý và ánh xạ bằng ID đã xác thực, thay vì tin vào đường dẫn gửi từ client.
- Với ảnh tải từ URL, kiểm tra scheme, hostname, địa chỉ IP và redirect theo chính sách; không fetch URL tùy ý từ request vì có nguy cơ SSRF.
- Giới hạn kích thước file, loại MIME thực tế và số lượng resource.
- Không cho phép nội dung SVG/HTML tùy ý chạy trong ngữ cảnh email mà không qua kiểm soát phù hợp.
- Không log byte ảnh, token truy cập kho file hoặc URL có chữ ký chứa secret.

Ví dụ không an toàn:

~~~java
// Không lấy đường dẫn filesystem tùy ý từ request.
Resource image = new FileSystemResource(request.imagePath());
helper.addInline("user-image", image);
~~~

Một cách tổ chức an toàn hơn là nhận **asset ID**, kiểm tra quyền truy cập rồi lấy Resource từ một service quản lý:

~~~java
Resource image = assetService.getReadableInlineImage(
        authenticatedUser,
        request.assetId());

helper.setText(html, true);
helper.addInline("user-image", image, "image/png");
~~~

Tên method và service trong ví dụ là abstraction do ứng dụng xây dựng. Điều quan trọng là việc xác thực quyền và giới hạn nguồn dữ liệu diễn ra **trước khi resource được gắn vào email**.

## 17. Kiểm thử thứ tự và Content-ID

Test inline resource nên xác nhận ít nhất ba điều:

1. Body HTML được thiết lập và chứa CID cần tham chiếu.
2. MIME message có part resource với Content-ID khớp.
3. Part có Content-Type phù hợp với nội dung ảnh.

Một cách test là tạo MimeMessage trong bộ nhớ, serialize và parse lại. Không cần gửi đến SMTP server:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.MimeMessageHelper;

class InlineResourceMimeTest {
    @Test
    void containsHtmlReferenceAndMatchingInlinePart() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);
        MimeMessageHelper helper =
                new MimeMessageHelper(message, true, "UTF-8");

        helper.setText(
                "<html><body><img src=\"cid:test-logo\" "
                        + "alt=\"Logo\"></body></html>",
                true);
        helper.addInline(
                "test-logo",
                new ClassPathResource("mail/images/logo.png"),
                "image/png");

        message.saveChanges();
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        message.writeTo(output);

        MimeMessage parsed = new MimeMessage(
                session,
                new ByteArrayInputStream(output.toByteArray()));

        assertThat(parsed.getContent()).isInstanceOf(Multipart.class);
        assertThat(findPart(parsed, "test-logo", "image/png"))
                .isTrue();
    }

    private static boolean findPart(
            Part part,
            String expectedContentId,
            String expectedMimeType) throws Exception {
        String[] ids = part.getHeader("Content-ID");
        if (ids != null && ids.length > 0
                && ids[0].contains(expectedContentId)
                && part.isMimeType(expectedMimeType)) {
            return true;
        }

        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                if (findPart(child, expectedContentId, expectedMimeType)) {
                    return true;
                }
            }
        }
        return false;
    }
}
~~~

Test này giả định file ảnh test tồn tại trên classpath ở `mail/images/logo.png`. Nó kiểm tra message sau serialize/parse, nên có thể phát hiện trường hợp helper không tạo ra inline part như mong đợi. Phương thức tìm part duyệt multipart lồng nhau thay vì dựa vào vị trí cố định.

Nếu chỉ mock JavaMailSender rồi verify `send(message)`, test đó chưa chứng minh Content-ID và MIME part đúng. Hãy kiểm tra MimeMessage đã dựng hoặc dùng SMTP test server khi cần xác minh cả giao thức.

### Kiểm tra số lần resource được thêm

Với template có nhiều ảnh, có thể dùng một test model liệt kê các resource mong đợi và kiểm tra mỗi CID xuất hiện trong HTML có đúng một MIME part. Nếu cùng CID được tham chiếu nhiều lần trong HTML, chỉ cần một part tương ứng; nếu hai resource khác nhau dùng cùng CID, test nên thất bại.

## 18. Checklist thao tác khi dựng email có inline resource

Trình tự dưới đây là cách triển khai dễ đọc và hạn chế lỗi:

1. Chuẩn bị dữ liệu nghiệp vụ và kiểm tra quyền sử dụng từng ảnh.
2. Chọn resource từ classpath hoặc kho lưu trữ được quản lý.
3. Sinh Content-ID duy nhất cho từng ảnh khác nhau trong message.
4. Render HTML với các thẻ ảnh dùng `src="cid:<content-id>"`.
5. Tạo MimeMessage.
6. Tạo MimeMessageHelper ở chế độ multipart.
7. Đặt From, To, Subject và các header cần thiết.
8. Gọi `setText(html, true)` hoặc `setText(plain, html)`.
9. Gọi `addInline(contentId, resource, contentType)` cho từng ảnh.
10. Gọi `addAttachment(...)` cho tài liệu người nhận cần tải xuống.
11. Gửi message bằng JavaMailSender.
12. Khi có lỗi hiển thị, serialize/parse MIME và kiểm tra CID cùng Content-Type.

~~~text
Validate recipient và asset
          |
          v
Chọn resource + sinh CID
          |
          v
Render HTML có cid reference
          |
          v
Create MimeMessage + helper multipart
          |
          v
setText(plain/html)
          |
          v
addInline(resource theo CID)
          |
          v
addAttachment(file tải xuống)
          |
          v
JavaMailSender.send()
~~~

## 19. Những câu hỏi thường gặp

**Có thể gọi addInline trước setText nếu email vẫn hiển thị đúng trong Gmail không?** Không nên dựa vào hành vi của một client cụ thể. Spring khuyến nghị gọi addInline sau setText để các mail reader có thể giải quyết CID đúng cách.

**Có bắt buộc dùng multipart=true không?** Có. Inline resource cần message multipart. Hãy tạo MimeMessageHelper với multipart mode phù hợp; constructor boolean true là lựa chọn thường dùng.

**CID trong HTML có cần dấu ngoặc nhọn không?** Trong HTML, dùng `cid:company-logo`. Truyền `company-logo` vào addInline. Helper xử lý cách biểu diễn Content-ID trong MIME header; không tự thêm dấu ngoặc nhọn vào HTML.

**Tên resource và Content-ID có phải giống nhau không?** Không. Tên file mô tả resource; Content-ID là định danh mà HTML tham chiếu. Chúng chỉ cần được ánh xạ đúng trong code.

**Một ảnh có thể xuất hiện nhiều lần trong HTML không?** Có. Các vị trí có thể tham chiếu cùng một CID và dùng chung một MIME part.

**Có thể thêm nhiều inline resource không?** Có. Gọi addInline một lần cho mỗi Content-ID/resource, tất cả sau setText.

**Có thể dùng addInline cho PDF không?** Về kỹ thuật có thể gắn resource vào MIME với CID, nhưng PDF thường phù hợp hơn với attachment. Chỉ dùng inline nếu email client và nghiệp vụ có cách hiển thị PDF nhúng rõ ràng; không nên coi nó tương đương ảnh inline.

**Ảnh có hiện nếu người nhận dùng text-only mail client không?** Không. Text/plain không render ảnh CID; hãy bảo đảm nội dung quan trọng vẫn có trong phiên bản text.

**Có thể lấy ảnh từ URL rồi addInline trực tiếp không?** addInline nhận Resource/DataSource/InputStreamSource, không phải URL tùy ý theo nghĩa tự động tải an toàn. Nếu cần tải ảnh từ nguồn ngoài, phải kiểm soát SSRF, redirect, host, kích thước, MIME type và quyền truy cập trước khi tạo Resource.

**Nếu setText được gọi lần thứ hai sau addInline thì sao?** Không nên thiết kế luồng đó. Hãy hoàn thiện body một lần trước khi thêm inline resources; nếu cần thay nội dung, tạo lại message/helper theo trình tự rõ ràng.

## 20. Nguyên tắc cần nhớ

Inline resource là một MIME part có **Content-ID** để HTML tham chiếu bằng URI `cid:...`. Trong Spring Framework Mail, hãy tạo HTML chứa CID, gọi **MimeMessageHelper.setText(...) trước**, rồi mới gọi **addInline(...)** cho từng resource. Khi có file tải xuống, sử dụng addAttachment riêng.

Hãy giữ Content-ID khớp chính xác giữa template và helper, dùng Resource có thể đọc ổn định, chỉ định Content-Type đúng, kiểm soát nguồn ảnh và tối ưu dung lượng. Khi cần chẩn đoán, kiểm tra MIME sau serialize/parse và tìm part theo Content-ID thay vì giả định thứ tự part cố định.

**Thứ tự cốt lõi: render HTML → setText → addInline → addAttachment (nếu có) → send.** Đây là cách xây dựng email HTML có ảnh nhúng rõ ràng, dễ kiểm thử và tương thích tốt hơn với các email client.
