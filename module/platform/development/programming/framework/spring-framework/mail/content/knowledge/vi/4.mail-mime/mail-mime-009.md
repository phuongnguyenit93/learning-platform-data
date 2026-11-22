# MIME: Content-Disposition `inline` và `attachment` trong Spring Framework Mail

Một email có thể chứa nội dung văn bản, HTML, hình ảnh xuất hiện ngay trong thân thư và các tệp để người nhận tải xuống. Để mô tả từng phần như vậy, hệ thống email sử dụng **MIME (Multipurpose Internet Mail Extensions)**. Một header đặc biệt quan trọng là **`Content-Disposition`**: nó cung cấp gợi ý cho ứng dụng đọc thư về cách trình bày một MIME part, thường là **`inline`** (hiển thị cùng nội dung) hoặc **`attachment`** (xử lý như tệp đính kèm).

Trong **Spring Framework Mail**, bạn thường không cần tự ghép các MIME header. `JavaMailSender`, `MimeMessage` và `MimeMessageHelper` cho phép tạo thư nhiều phần, đính kèm tài liệu bằng `addAttachment(...)` và thêm tài nguyên nội tuyến bằng `addInline(...)`. Muốn dùng đúng, cần hiểu `Content-Disposition` tương tác thế nào với `Content-Type`, `Content-ID` và cấu trúc `multipart/*`.

## 1. MIME part là gì và Content-Disposition dùng để làm gì?

Email thông thường có phần header và body. Khi email sử dụng MIME, body có thể được chia thành nhiều **part**; mỗi part có header riêng mô tả loại nội dung, cách mã hóa và cách hiển thị.

Ví dụ một part là tệp PDF:

```text
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQK... (nội dung base64 đã rút gọn)
```

Ba header có vai trò khác nhau:

| Header | Câu hỏi được trả lời | Ví dụ |
|---|---|---|
| `Content-Type` | Dữ liệu trong part thuộc loại gì? | `application/pdf`, `image/png`, `text/html; charset=UTF-8` |
| `Content-Disposition` | Ứng dụng đọc thư nên trình bày part thế nào? | `inline` hoặc `attachment`; có thể kèm `filename` |
| `Content-Transfer-Encoding` | Nội dung được biểu diễn như thế nào để truyền qua email? | `base64`, `quoted-printable` |
| `Content-ID` | Part này có định danh để phần khác của thư tham chiếu không? | `<brand-logo>`, được tham chiếu bởi `cid:brand-logo` |

`Content-Disposition` **không phải định dạng tệp** và không quyết định nội dung thật của dữ liệu. Nó còn không phải mệnh lệnh bắt buộc với mọi mail client: ứng dụng đọc thư có thể áp dụng quy tắc riêng vì lý do bảo mật, loại tệp hoặc trải nghiệm người dùng.

Header có cú pháp điển hình:

```text
Content-Disposition: inline
Content-Disposition: attachment; filename="report.pdf"
Content-Disposition: inline; filename="chart.png"
```

Hai giá trị `inline` và `attachment` là **disposition type**. `filename` là tham số tùy chọn hỗ trợ đặt tên khi lưu phần dữ liệu ra tệp. Một phần nội tuyến không nhất thiết cần tên tệp; một phần đính kèm có thể được hiển thị trước trong giao diện mà không cần tải xuống.

## 2. `inline`: nội dung được đề nghị hiển thị cùng thư

`Content-Disposition: inline` cho biết part được dự định hiển thị trực tiếp trong bối cảnh xem thông điệp, khi loại nội dung và chính sách mail client cho phép.

Các trường hợp dễ gặp:

- Một hình logo trong email HTML, hiển thị qua `<img src="cid:brand-logo">`.
- Một hình biểu đồ được nhúng trong email báo cáo, tránh phụ thuộc vào URL ảnh từ Internet.
- Một part văn bản được ứng dụng đọc thư chọn hiển thị ngay khi mở thư.

Ví dụ MIME part của một hình PNG:

```text
Content-Type: image/png
Content-Disposition: inline
Content-ID: <brand-logo>
Content-Transfer-Encoding: base64

iVBORw0KGgoAAA... (dữ liệu ảnh rút gọn)
```

Để hình xuất hiện tại vị trí mong muốn trong HTML, phần HTML của email có thể chứa:

```html
<p>Chào mừng bạn!</p>
<img src="cid:brand-logo" alt="Logo công ty" width="120">
```

Phần `cid:brand-logo` trong HTML trỏ đến part có header `Content-ID: <brand-logo>`. Đây là **content identifier**, không phải URL HTTP và cũng không phải đường dẫn đến file trên máy của người gửi. Tên `brand-logo` chỉ cần nhất quán giữa phần HTML và part MIME tương ứng.

**Lưu ý:** đặt `Content-Disposition: inline` một mình **không làm ảnh tự xuất hiện ở vị trí bất kỳ trong HTML**. Để chèn nội dung ở vị trí cụ thể, HTML phải tham chiếu đến part qua `cid:...` và thông điệp phải tổ chức các part theo cấu trúc MIME phù hợp. Một số mail client vẫn có thể liệt kê ảnh inline trong danh sách “tệp đính kèm” hoặc chặn hiển thị một số loại nội dung.

### Tại sao đôi khi hình inline vẫn hiện thành tệp?

Hệ thống đọc email rất đa dạng: trình duyệt webmail, ứng dụng desktop, ứng dụng di động và các bộ lọc bảo mật. Phần mềm có thể:

1. Không hỗ trợ tốt tài nguyên `cid:` cho một kiểu hiển thị nhất định.
2. Không tìm được `Content-ID` khớp với HTML.
3. Chặn một số loại MIME như SVG hoặc nội dung có thể thực thi.
4. Hiển thị mọi part mang tên tệp trong một khu vực phụ, kể cả khi disposition là `inline`.
5. Áp dụng các quy tắc riêng cho cấu trúc `multipart/related`.

Vì vậy, **`inline` thể hiện ý định hiển thị**, không bảo đảm mọi mail client sẽ render giống nhau. Với thư cần hiển thị ổn định, nên dùng ảnh PNG/JPEG phổ biến, HTML đơn giản và thêm văn bản thay thế qua `alt`.

## 3. `attachment`: nội dung được đề nghị xử lý như tệp đính kèm

`Content-Disposition: attachment` cho biết part thường nên được liệt kê và xử lý dưới dạng tệp riêng. Mail client có thể cho phép xem trước, mở bằng ứng dụng phù hợp hoặc tải về.

Ví dụ:

```text
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice-2026.pdf"
Content-Transfer-Encoding: base64

JVBERi0xLjQK... (dữ liệu PDF rút gọn)
```

Trong ví dụ này:

- `application/pdf` mô tả loại nội dung.
- `attachment` thể hiện ý định đính kèm.
- `filename="invoice-2026.pdf"` cung cấp tên hiển thị hoặc tên mặc định khi lưu.
- `base64` là cách biểu diễn dữ liệu nhị phân trong email; nó **không phải mã hóa bí mật**.

Tệp PDF vẫn có thể được mail client hiển thị xem trước ngay trong cửa sổ email. Đây là tính năng của client, không mâu thuẫn với disposition `attachment`. Ngược lại, một phần được đánh dấu `inline` có thể không được render trực tiếp nếu client không hỗ trợ.

### `filename` và `name` khác nhau thế nào?

Đôi khi một MIME part có cả:

```text
Content-Type: application/pdf; name="invoice.pdf"
Content-Disposition: attachment; filename="invoice.pdf"
```

`name` là tham số của `Content-Type` thường thấy ở các thông điệp cũ; `filename` là tham số của `Content-Disposition` dành cho tên tệp. Trong phần mềm hiện đại, nên cung cấp tên thông qua API attachment và để thư viện MIME mã hóa các header phù hợp. Không nên tự ghép các header này từ dữ liệu người dùng.

Tên tệp có dấu, khoảng trắng hoặc ký tự đặc biệt cần được biểu diễn theo chuẩn mã hóa MIME tương ứng; cách giải mã còn tùy client. Hãy thử nghiệm với tên tệp có Unicode trên các client mục tiêu. Tránh dùng đường dẫn hệ thống như `C:\Users\...\invoice.pdf` trong filename: người nhận thường chỉ cần tên tệp, và việc lộ cấu trúc thư mục của server là không cần thiết.

## 4. So sánh trực tiếp `inline` và `attachment`

| Tiêu chí | `inline` | `attachment` |
|---|---|---|
| Mục đích | Đề nghị hiển thị trong ngữ cảnh xem thư | Đề nghị trình bày như tệp riêng |
| Trường hợp điển hình | Logo, biểu đồ, tài nguyên của HTML email | PDF hóa đơn, CSV báo cáo, tài liệu hợp đồng |
| `Content-Disposition` | `inline` | `attachment` |
| Có cần `filename`? | Không bắt buộc | Nên có khi dữ liệu là tệp tải về |
| Có cần `Content-ID`? | Khi part cần được tham chiếu qua `cid:` | Thường không cần |
| Cách HTML chỉ đến tài nguyên | `src="cid:..."` khi có Content-ID | Thường không cần tham chiếu trong HTML |
| Spring Mail API | `MimeMessageHelper.addInline(...)` | `MimeMessageHelper.addAttachment(...)` |
| Hiển thị thực tế | Phụ thuộc mail client và cấu trúc MIME | Có thể được xem trước ngay trong mail client |
| Đảm bảo bảo mật? | Không; chỉ là metadata về trình bày | Không; tệp vẫn cần kiểm soát loại và nội dung |

Quy tắc lựa chọn dễ áp dụng: nếu tài nguyên là **một phần của cách trình bày email HTML**, dùng inline và Content-ID; nếu tài nguyên là **một tệp người nhận cần xem, lưu hoặc xử lý riêng**, dùng attachment.

## 5. Content-Disposition phối hợp với `multipart/*` ra sao?

Một thư HTML có ảnh nội tuyến và một tệp PDF đính kèm không chỉ là ba part đặt cạnh nhau. Cấu trúc `multipart/*` cho client biết những part nào là phương án hiển thị của cùng một nội dung, những part nào liên quan với HTML, và những part nào là tệp bổ sung.

Ba kiểu multipart quan trọng:

| Loại | Ý nghĩa |
|---|---|
| `multipart/alternative` | Nhiều phiên bản thay thế cho **cùng nội dung** (ví dụ text/plain và text/html); client chọn phiên bản phù hợp |
| `multipart/related` | Một nội dung chính cùng các tài nguyên cần để hiển thị nó (ví dụ HTML và ảnh CID) |
| `multipart/mixed` | Thư chứa những phần độc lập được gom chung, thường gồm nội dung thư và các tệp đính kèm |

Một cây MIME **minh họa** cho email có văn bản, HTML, logo và PDF:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain; charset=UTF-8
    │   │   └── text/html; charset=UTF-8
    │   │       (có <img src="cid:brand-logo">)
    │   └── image/png
    │       Content-ID: <brand-logo>
    │       Content-Disposition: inline
    └── application/pdf
        Content-Disposition: attachment; filename="invoice.pdf"
```

Cách đọc cấu trúc:

- `alternative` cho phép ứng dụng đọc thư chọn phiên bản HTML hoặc plain text theo khả năng và thiết lập người dùng.
- `related` liên kết nội dung HTML với ảnh nội tuyến; ảnh có `Content-ID` khớp với tham chiếu `cid:`.
- `mixed` thêm tệp PDF độc lập vào cùng email.

Đây là cấu trúc logic điển hình, **không phải thứ tự header bắt buộc cho mọi thư do mọi phiên bản thư viện sinh ra**. Trình tự và cách lồng cụ thể có thể khác tùy multipart mode và cách tạo thông điệp. Điều quan trọng là các part có mối liên hệ đúng và phần mềm nhận có thể chọn phiên bản hiển thị hợp lý.

### Tại sao không chỉ dùng `multipart/mixed` cho mọi thứ?

Nếu đặt tất cả part cùng một mức trong `multipart/mixed`, client có thể hiểu ảnh logo là tệp bổ sung thay vì tài nguyên của HTML. `multipart/related` diễn đạt rõ mối quan hệ nội dung chính và tài nguyên hỗ trợ, làm tăng khả năng hiển thị đúng trên các client.

Trong Spring, `MimeMessageHelper` hỗ trợ nhiều multipart mode. `MULTIPART_MODE_MIXED_RELATED` phù hợp khi email có **cả inline resources và attachments**: nó tổ chức các part theo mô hình hỗn hợp và liên quan. `MULTIPART_MODE_RELATED` phù hợp với email cần HTML và inline resources; `MULTIPART_MODE_MIXED` có thể hữu ích trong những trường hợp đính kèm đơn giản hoặc khả năng tương thích riêng. Lựa chọn cuối cùng cần xét mail client mà hệ thống phục vụ.

## 6. Tạo email có cả ảnh inline và PDF attachment bằng Spring Mail

Spring Framework cung cấp `JavaMailSender`; với ứng dụng Spring Boot, thường bổ sung dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-mail'
}
```

Ứng dụng cũng cần một máy chủ SMTP submission được cấu hình qua `spring.mail.host`, `spring.mail.port`, thông tin xác thực và thuộc tính TLS phù hợp. Việc sử dụng inline/attachment là vấn đề định dạng MIME; nó **không thay thế** cấu hình kết nối SMTP.

### Ví dụ một dịch vụ gửi hóa đơn

Ví dụ dưới đây nhận sẵn dữ liệu PNG và PDF dưới dạng `byte[]`, tạo body plain text và HTML, chèn logo qua `cid:` rồi thêm hóa đơn dạng attachment.

```java
package com.example.notification;

import java.nio.charset.StandardCharsets;
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class InvoiceMailService {

    private final JavaMailSender mailSender;
    private final String fromAddress;

    public InvoiceMailService(
            JavaMailSender mailSender,
            @Value("${app.mail.from}") String fromAddress) {
        this.mailSender = mailSender;
        this.fromAddress = fromAddress;
    }

    public void sendInvoice(
            String recipient,
            byte[] logoPng,
            byte[] invoicePdf) throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom(fromAddress);
        helper.setTo(recipient);
        helper.setSubject("Hóa đơn của bạn");

        String plainText = "Cảm ơn bạn đã mua hàng. "
                + "Vui lòng xem hóa đơn PDF đính kèm.";

        String htmlText = """
                <!doctype html>
                <html>
                  <body>
                    <p><img src="cid:brand-logo"
                            alt="Logo cửa hàng" width="120"></p>
                    <h2>Cảm ơn bạn đã mua hàng!</h2>
                    <p>Hóa đơn PDF được đính kèm trong email này.</p>
                  </body>
                </html>
                """;

        // Thiết lập nội dung trước khi thêm các tài nguyên inline.
        helper.setText(plainText, htmlText);

        helper.addInline(
                "brand-logo",
                new ByteArrayResource(logoPng),
                "image/png");

        helper.addAttachment(
                "invoice.pdf",
                new ByteArrayResource(invoicePdf),
                "application/pdf");

        mailSender.send(message);
    }
}
```

Điều cần hiểu trong ví dụ:

1. `MimeMessage` cho phép email gồm nhiều MIME part. `SimpleMailMessage` không cung cấp cách tạo cấu trúc MIME với HTML và tệp đính kèm như trên.
2. `MULTIPART_MODE_MIXED_RELATED` được chỉ định tường minh cho tình huống vừa có logo inline vừa có PDF attachment.
3. `setText(plainText, htmlText)` tạo hai phiên bản của nội dung. Người nhận dùng client hỗ trợ HTML có thể thấy HTML; client chỉ dùng plain text vẫn có thông tin chính.
4. `addInline("brand-logo", ...)` thêm ảnh có content ID tương ứng với `cid:brand-logo`. **Không truyền dấu `< >` vào tham số `contentId`**; helper xử lý cách thể hiện header.
5. `addAttachment("invoice.pdf", ...)` cung cấp tên tệp và dữ liệu PDF để thư viện tạo part đính kèm.
6. `ByteArrayResource` cho phép đọc lại byte dữ liệu khi Jakarta Mail cần chuẩn bị hoặc truyền MIME content. Với tệp lớn, có thể chọn tài nguyên dạng file/stream lặp lại được, tránh nạp toàn bộ vào RAM.
7. `mailSender.send(message)` nộp thư đến máy chủ SMTP đã cấu hình. Thành công tại bước này chưa bảo đảm thư đã đến hộp thư cuối cùng.

Mã sử dụng Java text block (`"""`), yêu cầu phiên bản Java hỗ trợ text block. API `jakarta.mail` tương ứng Spring Framework hiện đại (Spring 6+, Spring Boot 3+); dự án cũ có thể dùng namespace `javax.mail` và cần import theo phiên bản thực tế.

### Vì sao phải gọi `setText(...)` trước `addInline(...)`?

Với `MimeMessageHelper`, thứ tự được khuyến nghị là **thiết lập nội dung văn bản/HTML trước, sau đó thêm inline resources**. Một số mail client nhạy với thứ tự MIME part, và cách tổ chức của helper có thể thay đổi khi đặt text. Giữ thứ tự trên giúp ảnh inline được liên kết với HTML ổn định hơn.

Có thể thêm attachment sau khi tạo nội dung và inline resources. Nếu email có nhiều ảnh, dùng các content ID duy nhất trong thông điệp (`brand-logo`, `summary-chart`, ...) rồi tham chiếu chúng tương ứng trong HTML.

## 7. Các API Spring Mail liên quan

`MimeMessageHelper` cung cấp nhiều overload để sử dụng tài nguyên từ byte, file, classpath hoặc `DataSource`.

| API | Mục đích | Đặc điểm |
|---|---|---|
| `setText(String text, boolean html)` | Đặt body dạng plain text hoặc HTML | `true` là HTML, `false` là plain text |
| `setText(String plainText, String htmlText)` | Cung cấp cả text/plain và text/html | Hỗ trợ client chọn phiên bản phù hợp |
| `addInline(String contentId, InputStreamSource source, String contentType)` | Tạo inline resource | Content ID có thể được HTML tham chiếu qua `cid:` |
| `addInline(String contentId, Resource resource)` | Inline resource từ Spring `Resource` | Cần có thể xác định loại nội dung phù hợp; với trường hợp khó đoán, dùng overload có content type |
| `addAttachment(String attachmentFilename, InputStreamSource source, String contentType)` | Thêm tệp đính kèm với tên và MIME type | Hữu ích khi dữ liệu đến từ bộ nhớ hoặc storage |
| `addAttachment(String attachmentFilename, File file)` | Đính kèm file từ filesystem | File phải tồn tại và còn truy cập được khi gửi |
| `addAttachment(String attachmentFilename, DataSource dataSource)` | Đính kèm dữ liệu Jakarta Activation | Dùng khi tích hợp với nguồn MIME/Jakarta Mail khác |

Ví dụ lấy logo từ classpath và PDF có sẵn trên filesystem:

```java
import java.io.File;
import org.springframework.core.io.ClassPathResource;

helper.setText(
        "<p>Báo cáo tháng này: <img src='cid:company-logo'></p>",
        true);

helper.addInline(
        "company-logo",
        new ClassPathResource("mail/logo.png"),
        "image/png");

helper.addAttachment(
        "monthly-report.pdf",
        new File("/srv/reports/monthly-report.pdf"));
```

Đường dẫn `mail/logo.png` trong ví dụ là tài nguyên đóng gói trong ứng dụng. `/srv/reports/monthly-report.pdf` chỉ là ví dụ về đường dẫn file trên server. Đừng ghép thẳng đường dẫn từ input người dùng vào `new File(...)`; cần kiểm soát file được phép đính kèm và xử lý lỗi khi file không tồn tại.

### Lưu ý về `InputStreamSource` và dữ liệu chỉ đọc được một lần

Tài nguyên được truyền cho helper phải có khả năng cung cấp một `InputStream` mới mỗi khi cần. Jakarta Mail có thể yêu cầu lấy dữ liệu nhiều lần trong quá trình tạo, tính kích thước, hoặc gửi thông điệp. Truyền một luồng duy nhất đã mở có thể dẫn tới dữ liệu rỗng hoặc lỗi khi sử dụng lại.

Ví dụ an toàn với dữ liệu đã nằm trong bộ nhớ:

```java
byte[] pdfBytes = /* lấy từ dịch vụ tạo PDF */;
helper.addAttachment(
        "document.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf");
```

Với dữ liệu lớn, `FileSystemResource`, file trên disk hoặc `InputStreamSource` tự tạo luồng mới từ storage có thể phù hợp hơn. Cần tính đến thời điểm phát thư: file/stream phải còn truy cập được khi transport đọc dữ liệu, đặc biệt nếu gửi bất đồng bộ.

## 8. Đọc header MIME: các ví dụ phân biệt

### Ví dụ A: tệp đính kèm PDF thông thường

```text
Content-Type: application/pdf
Content-Disposition: attachment; filename="contract.pdf"
Content-Transfer-Encoding: base64

JVBERi0... 
```

Thư có một tệp `contract.pdf`, client thường hiển thị tên tệp cùng hành động xem/tải.

### Ví dụ B: ảnh nội tuyến được HTML tham chiếu

```text
Content-Type: image/png
Content-ID: <chart-01>
Content-Disposition: inline
Content-Transfer-Encoding: base64

iVBORw0...
```

HTML chứa `<img src="cid:chart-01">`. Client hỗ trợ MIME related có thể đặt ảnh tại vị trí được tham chiếu trong thân thư.

### Ví dụ C: ảnh được đánh dấu inline nhưng không có CID

```text
Content-Type: image/jpeg
Content-Disposition: inline; filename="photo.jpg"
Content-Transfer-Encoding: base64

/9j/4AAQ...
```

Header thể hiện mong muốn hiển thị trực tiếp ảnh. Nhưng nếu HTML không có tham chiếu và thư không có cấu trúc thích hợp, client có thể hiển thị ảnh như một part riêng, liệt kê như tệp hoặc không hiển thị. `inline` không thay thế `Content-ID` khi cần nhúng ảnh theo vị trí HTML.

### Ví dụ D: dữ liệu có `Content-ID` nhưng lại là attachment

```text
Content-Type: image/png
Content-ID: <figure-02>
Content-Disposition: attachment; filename="figure.png"
```

`Content-ID` là định danh, còn `Content-Disposition` là gợi ý hiển thị. Chúng là **hai header độc lập**. Một số client có thể hiển thị nội dung theo cách khác nhau khi HTML tham chiếu `cid:figure-02` nhưng part được đánh dấu attachment. Nếu mục tiêu là hình nằm trong thân thư, sử dụng `addInline(...)` và cấu trúc `multipart/related` thay vì cố tạo trường hợp mâu thuẫn.

### Ví dụ E: một phần không khai báo Content-Disposition

```text
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Xin ch=C3=A0o!
```

Không phải part nào cũng có `Content-Disposition`. Phần text chính của email có thể được client hiển thị như nội dung thư dựa trên `Content-Type` và vị trí trong cây MIME, ngay cả khi thiếu header disposition.

## 9. Tên file, ký tự Unicode và Content-Type

Tên tệp trong header có thể chứa ký tự tiếng Việt hoặc khoảng trắng, chẳng hạn `"Báo cáo tháng 11.pdf"`. Trong thông điệp MIME thực tế, thư viện có thể mã hóa các tham số header để truyền an toàn và tương thích theo chuẩn. Bạn nên truyền **chuỗi Java tên tệp đã kiểm soát** vào `addAttachment(...)` và để thư viện xử lý biểu diễn MIME, thay vì tự nối chuỗi `Content-Disposition` theo ý mình.

Hai nguyên tắc khi thiết kế:

- **Tên tệp là metadata, không phải đường dẫn an toàn.** Dùng basename hợp lệ, loại bỏ ký tự điều khiển và dấu phân cách đường dẫn khi tên đến từ người dùng; không dùng tên tệp để quyết định quyền truy cập hệ thống lưu trữ.
- **MIME type phải phản ánh dữ liệu thực.** Khi có thông tin chính xác, truyền `application/pdf`, `image/png`, `text/csv` ... qua overload có `contentType`. Không suy luận rằng file chắc chắn an toàn chỉ vì phần mở rộng hoặc MIME type được khai báo.

Đối với ảnh inline, nếu file SVG chứa nội dung hoạt động, một số client có thể chặn hoặc xử lý khó dự đoán. PNG hoặc JPEG thường là lựa chọn tương thích hơn cho hình logo và ảnh minh họa. Với tài liệu và báo cáo, file PDF thường phù hợp hơn dưới dạng attachment.

### Base64 làm email lớn hơn

Các tệp nhị phân trong email thường được truyền bằng `Content-Transfer-Encoding: base64`. Base64 làm kích thước dữ liệu truyền tăng lên (xấp xỉ một phần ba, chưa kể xuống dòng và header), vì vậy hạn mức tệp đính kèm của dịch vụ gửi có thể thấp hơn tổng kích thước dữ liệu nhị phân mà bạn mong muốn gửi.

Khi cần truyền tệp rất lớn, cân nhắc gửi **liên kết tải có phân quyền và thời hạn** thay vì nhúng toàn bộ dữ liệu vào email. Cần xác định rõ quyền truy cập và thời hạn sống của liên kết.

## 10. Những lỗi phổ biến khi tích hợp Spring Mail

| Hiện tượng | Nguyên nhân có thể xảy ra | Hướng xử lý |
|---|---|---|
| HTML hiển thị nhưng logo bị biểu tượng lỗi | `cid:` không khớp `Content-ID`, thứ tự tạo MIME part sai hoặc client chặn | Dùng cùng content ID ở HTML và `addInline`; gọi `setText` trước `addInline` |
| Logo bị liệt kê ở danh sách tệp | Client hiển thị inline resources như tệp hoặc cấu trúc multipart chưa phù hợp | Dùng `MULTIPART_MODE_MIXED_RELATED`; kiểm tra trên client mục tiêu |
| PDF xuất hiện trong body thay vì tệp tải | Part có disposition hoặc cấu trúc không mong muốn | Dùng `addAttachment`; kiểm tra MIME source |
| Tệp đính kèm trống hoặc gửi báo lỗi luồng | `InputStreamSource` chỉ có thể đọc một lần, file bị đổi/xóa trước khi gửi | Dùng `ByteArrayResource` hoặc nguồn có thể mở stream mới; quản lý vòng đời file |
| Tên file có dấu bị lỗi | Khả năng hỗ trợ mã hóa header/Unicode khác nhau giữa client | Dùng API helper, cấu hình charset phù hợp, thử nghiệm với client cần hỗ trợ |
| Phần text/plain xuất hiện đồng thời với HTML | Client đang hiểu các part như những nội dung độc lập | Dùng `setText(plainText, htmlText)` để tạo cấu trúc alternative |
| Tệp bị chặn hoặc bị đổi tên khi nhận | Bộ lọc bảo mật, chính sách tổ chức, loại file bị hạn chế | Kiểm tra MIME type, chính sách gửi/nhận và loại file được phép |
| Message quá lớn bị từ chối | Base64 và multipart overhead, hạn mức SMTP/server | Tính kích thước thực sau đóng gói; giảm dung lượng hoặc gửi liên kết |
| Thư gửi thành công nhưng người nhận không thấy attachment | Client lọc/quarantine, lỗi cấu trúc MIME hoặc hệ thống trung gian | Kiểm tra nguồn MIME, log và sự kiện nhà cung cấp sau submission |

Để điều tra lỗi, nên phân biệt hai giai đoạn: **tạo MIME message** và **gửi qua SMTP**. Một exception trong `MimeMessageHelper` có thể xảy ra trước khi mở kết nối SMTP; ngược lại, lỗi SMTP AUTH hoặc timeout có thể xảy ra sau khi MIME message đã tạo hoàn chỉnh.

### Kiểm tra MIME source khi cần gỡ lỗi

Nhiều mail client cho phép “View original”, “Show source” hoặc “View message headers”. Khi có quyền truy cập phù hợp, bạn có thể kiểm tra:

1. Header `Content-Type` của thông điệp và từng part.
2. Cấu trúc và boundary của `multipart/mixed`, `related`, `alternative`.
3. `Content-Disposition` của attachment và inline resource.
4. `Content-ID` so với các URL `cid:` trong HTML.
5. `filename`, loại MIME và kích thước thực tế.

Trong môi trường phát triển, có thể dùng SMTP sink như Mailpit để xem thư thử nghiệm. Tránh xuất toàn bộ MIME source của thư chứa thông tin cá nhân, token, OTP hoặc attachment nhạy cảm ra log chung.

## 11. Bảo mật khi gửi inline resource và attachment

`Content-Disposition` chỉ là chỉ dẫn trình bày. Việc dùng `attachment` **không khiến file trở nên an toàn**, và việc dùng `inline` **không làm nội dung đáng tin cậy hơn**.

Những điểm cần quản lý trong ứng dụng:

1. **Nguồn dữ liệu đính kèm:** chỉ cho phép truy xuất file mà nghiệp vụ có quyền gửi. Tránh lỗi path traversal khi tên file hoặc đường dẫn chịu ảnh hưởng từ input người dùng.
2. **Kích thước và loại nội dung:** đặt giới hạn riêng cho từng file và tổng email; giới hạn các loại file nguy hiểm theo chính sách tổ chức.
3. **Kiểm soát dữ liệu nhạy cảm:** hóa đơn, báo cáo và ảnh nội bộ có thể chứa thông tin riêng tư; xác định đúng người nhận và quy trình cấp quyền trước khi gửi.
4. **HTML injection:** escape hoặc xử lý an toàn nội dung nhập từ người dùng trước khi đưa vào body HTML; không ghép dữ liệu chưa kiểm soát thành thẻ hoặc thuộc tính HTML.
5. **CID duy nhất và có kiểm soát:** không sử dụng cùng content ID cho các phần khác nhau trong một thông điệp; tránh tạo `cid:` trực tiếp từ input không được xác thực.
6. **Định dạng có nội dung hoạt động:** một số client chặn SVG, script hoặc các tệp có khả năng thực thi. Không dựa vào `inline` để vượt chính sách bảo mật của ứng dụng nhận.
7. **Vòng đời tài nguyên:** nếu worker gửi email bất đồng bộ, dữ liệu đính kèm cần còn tồn tại cho đến lúc message thực sự được gửi.

TLS trên kết nối SMTP bảo vệ **đường truyền từ ứng dụng đến máy chủ submission** theo cấu hình, không thay thế phân quyền truy cập nội dung và cũng không tự cung cấp mã hóa đầu cuối cho toàn bộ email.

## 12. Các tình huống lựa chọn

| Yêu cầu nghiệp vụ | Cách triển khai MIME gợi ý |
|---|---|
| Email xác nhận đăng ký có logo | HTML + logo `addInline`, sử dụng `cid:`; kèm bản plain text |
| Gửi hóa đơn PDF và logo | `setText(plain, html)` + `addInline(logo)` + `addAttachment(invoice.pdf)` |
| Gửi báo cáo CSV cho bộ phận dữ liệu | Nội dung ngắn + `addAttachment(report.csv, ..., "text/csv")` |
| Gửi ảnh chụp để người nhận tải về, không cần hiển thị trong body | `addAttachment(photo.jpg, ..., "image/jpeg")` |
| Gửi ảnh sản phẩm để xuất hiện trong nội dung giới thiệu | `addInline` với `Content-ID` riêng từng ảnh và tham chiếu từ HTML |
| Gửi tệp dung lượng lớn hoặc tài liệu cần phân quyền truy cập động | Xem xét liên kết tải được cấp quyền, thay vì đính kèm toàn bộ |

Một email có thể chứa **cả inline và attachment**. Tính chất của mỗi part được quyết định riêng; không tồn tại quy tắc “đã có inline thì không được đính kèm tài liệu” hay ngược lại.

## 13. Câu hỏi thường gặp

**Dùng `addInline` có cần tự viết `Content-Disposition: inline` không?** Thông thường không. `MimeMessageHelper` tạo MIME part tương ứng và gắn metadata cần thiết, bao gồm Content-ID. Dùng API helper để hạn chế lỗi tạo header thủ công.

**Tại sao có `cid:logo` trong HTML mà hình không hiển thị?** Có thể Content-ID không khớp, part không được thêm, content type không phù hợp, cấu trúc MIME chưa đúng hoặc mail client hạn chế hiển thị. Đừng giả định chỉ cần thêm một URL `cid:` là dữ liệu ảnh tự được gửi theo.

**Tệp được đặt `inline` có thể tải xuống không?** Có. Nhiều mail client vẫn cho phép người nhận lưu hoặc tải nội dung hiển thị inline. Disposition là gợi ý trình bày, không phải quyền truy cập.

**Tệp được đặt `attachment` có thể được hiển thị ngay trong email không?** Có. Một số client xem trước PDF/ảnh trong giao diện dù part có disposition attachment.

**Có thể chỉ dựa vào phần mở rộng `.pdf` để đặt `Content-Type` không?** Không nên. Đuôi file do người gửi hoặc người dùng đặt có thể không phản ánh nội dung thực; nên xác định dữ liệu và loại MIME phù hợp, đặc biệt với file upload.

**Có thể đính kèm HTML như một file không?** Có thể, nếu đó là yêu cầu nghiệp vụ, nhưng cần cân nhắc rủi ro nội dung hoạt động và chính sách lọc file. Thông thường HTML muốn hiển thị như thân thư nên dùng `setText(html, true)`, thay vì đính kèm một file HTML.

**Có cần `Content-ID` cho PDF attachment không?** Phần lớn trường hợp không. `Content-ID` hữu ích chủ yếu khi part cần được tham chiếu từ phần khác của thư; attachment độc lập chỉ cần filename và MIME type phù hợp.

**Nội dung thư có `Content-Disposition` không?** Có thể có hoặc không. Nội dung chính `text/plain`/`text/html` thường được xác định bởi `Content-Type` và cấu trúc multipart; thiếu disposition không đồng nghĩa nội dung sẽ biến thành attachment.

## 14. Tài liệu chuẩn liên quan

- **RFC 2045–2049 (MIME):** các khái niệm MIME, content type, multipart, mã hóa nội dung và các header liên quan.
- **RFC 2183 (Content-Disposition):** định nghĩa disposition và các tham số như `filename`.
- **RFC 2392 (Content-ID và MID URL):** mô tả cách tham chiếu nội dung MIME qua lược đồ `cid:`.
- **RFC 2231:** cơ chế biểu diễn một số tham số MIME, gồm trường hợp ký tự và độ dài mở rộng.
- **Spring Framework Mail, `MimeMessageHelper`:** API xây dựng `MimeMessage` với text/HTML, inline resources, attachments và các multipart mode.

---

Khi soạn email bằng Spring Framework Mail, hãy nhớ ba điểm: **`Content-Disposition: inline` là ý định hiển thị part cùng thư, `Content-Disposition: attachment` là ý định xử lý part như tệp riêng, và `Content-ID` là cách HTML tham chiếu tài nguyên cụ thể qua `cid:`**. Kết quả hiển thị cuối cùng còn phụ thuộc `Content-Type`, cấu trúc `multipart/*` và mail client. Với ứng dụng Spring, dùng `MimeMessageHelper.addInline(...)` và `addAttachment(...)` cùng một multipart mode phù hợp sẽ giúp mô tả các quan hệ đó rõ ràng hơn.
