# Thêm attachment mà không phá alternative

## 1. Vấn đề: email cần cả plain text, HTML và tệp đính kèm

Một email nghiệp vụ thường cần hai cách trình bày cùng một nội dung:

- **Plain text** để đọc được trong client không hiển thị HTML, chế độ chỉ văn bản hoặc công cụ hỗ trợ tiếp cận.
- **HTML** để có định dạng, bảng, liên kết và bố cục dễ đọc hơn.

Trong một số trường hợp, email còn cần thêm tệp như PDF hóa đơn, bảng tính hoặc báo cáo. Khi đó, mục tiêu là gửi **cả hai phiên bản nội dung và attachment trong cùng một MIME message**:

~~~text
Email
├── Nội dung plain text
├── Nội dung HTML
└── Tệp PDF đính kèm
~~~

Nhưng ở tầng MIME, plain text và HTML không phải hai phần độc lập để người nhận luôn hiển thị đồng thời. Chúng là **hai phiên bản thay thế** của cùng nội dung, thường được đặt trong `multipart/alternative`. Tệp PDF là một phần độc lập của email, nên phải được đặt ở lớp container phù hợp, thường là `multipart/mixed` bên ngoài.

Nếu ghép các part sai cấu trúc, email client có thể:

- Chỉ hiển thị plain text hoặc chỉ hiển thị HTML theo cách không mong muốn.
- Xem attachment như một phiên bản nội dung thay thế thay vì tệp đính kèm.
- Bỏ qua một body part khi chọn alternative.
- Hiển thị nội dung nhưng mất tệp, hoặc hiển thị tệp mà không có body như mong đợi.

Spring Framework Mail cung cấp **`MimeMessageHelper`** để quản lý cấu trúc này. Ta có thể gọi `setText(plainText, htmlText)` để tạo alternative, sau đó gọi `addAttachment(...)` để thêm file độc lập mà không phải tự xây dựng MIME boundary.

> **Nguyên tắc:** Plain text và HTML thuộc `multipart/alternative` vì chúng là các bản thay thế. Attachment thuộc `multipart/mixed` vì nó là phần bổ sung độc lập của email.

## 2. Hiểu hai loại multipart trước khi thêm attachment

### 2.1. multipart/alternative: các phiên bản thay thế của cùng nội dung

`multipart/alternative` chứa nhiều cách biểu diễn cùng một thông tin. Ví dụ:

~~~text
multipart/alternative
├── text/plain; charset=UTF-8
└── text/html; charset=UTF-8
~~~

Mail client chọn phiên bản phù hợp với khả năng và chính sách hiển thị của nó. Theo quy ước MIME, các alternative được sắp theo thứ tự từ dạng ít phong phú hơn tới dạng phong phú hơn; do đó plain text thường đứng trước HTML.

Ví dụ nội dung:

**Plain text**

~~~text
Hóa đơn tháng 11 đã sẵn sàng.
Mã đơn hàng: INV-2026-1101
Vui lòng xem chi tiết trong tài liệu đính kèm.
~~~

**HTML**

~~~html
<p>Hóa đơn tháng 11 đã <strong>sẵn sàng</strong>.</p>
<p>Mã đơn hàng: <strong>INV-2026-1101</strong></p>
<p>Vui lòng xem chi tiết trong tài liệu đính kèm.</p>
~~~

Hai nội dung có thể khác cách trình bày nhưng phải truyền tải cùng thông tin quan trọng. HTML không nên chứa một thông báo khác hoàn toàn với bản plain text.

### 2.2. multipart/mixed: các phần độc lập trong một email

`multipart/mixed` nhóm các phần độc lập của email. Một phần có thể là body chính, phần khác là attachment:

~~~text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── text/html
└── application/pdf
    Content-Disposition: attachment
    filename="invoice.pdf"
~~~

Trong cấu trúc này:

- Part đầu là nội dung chính, được tổ chức thành các alternative.
- Part thứ hai là PDF độc lập, có thể tải hoặc mở riêng.
- Client hiểu rằng PDF là tài liệu đính kèm chứ không phải một phiên bản khác của body.

Đây là cấu trúc quan trọng khi gửi HTML và plain text cùng attachment.

### 2.3. Vì sao không đặt PDF vào multipart/alternative?

`multipart/alternative` có ngữ nghĩa: mỗi part là một cách thể hiện thay thế của cùng nội dung. PDF hóa đơn là **tệp đi kèm**, không phải một cách hiển thị thay thế cho body HTML hoặc plain text.

Nếu đặt PDF thành một sibling trực tiếp trong alternative:

~~~text
multipart/alternative
├── text/plain
├── text/html
└── application/pdf
~~~

client có thể xem PDF như một alternative khác để lựa chọn. Điều này không diễn đạt đúng ý nghĩa email có một body và một file đính kèm. Cách rõ ràng hơn là đặt alternative trong multipart/mixed bên ngoài.

## 3. MimeMessageHelper tạo alternative như thế nào?

Spring cung cấp overload:

~~~java
helper.setText(plainText, htmlText);
~~~

Khi helper được khởi tạo ở chế độ multipart, lời gọi này tạo một `multipart/alternative` với hai body part:

1. `text/plain` cho bản văn bản.
2. `text/html` cho bản HTML.

Ví dụ:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText(
        "Báo cáo đã sẵn sàng.",
        "<p>Báo cáo đã <strong>sẵn sàng</strong>.</p>");
~~~

Tham số `true` ở constructor có nghĩa là **bật multipart**, không có nghĩa nội dung là HTML. Hai đối số của `setText(plain, html)` mới xác định hai phiên bản nội dung.

Nếu chỉ gọi:

~~~java
helper.setText(htmlText, true);
~~~

thì helper đặt một body HTML. Nó không tự tạo bản plain text tương đương. Muốn có alternative, dùng overload hai chuỗi.

### 3.1. Constructor multipart mode rõ ràng

Với email chỉ có alternative và attachment, có thể chọn:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8");
~~~

`MULTIPART_MODE_MIXED` tạo một root `multipart/mixed`. Nội dung chính có thể được đặt trong đó và attachment là part độc lập bổ sung. Khi `setText(plainText, htmlText)` được gọi, phần nội dung chính được tổ chức dưới dạng alternative.

Constructor boolean:

~~~java
new MimeMessageHelper(message, true, "UTF-8");
~~~

là cách ngắn hơn khi không cần chọn mode cụ thể; Spring sử dụng multipart mode mặc định dành cho helper. Khi đọc hoặc bảo trì code, dùng hằng số mode tường minh giúp người đọc hiểu rõ ý định của cấu trúc MIME.

### 3.2. Khi nào cần MULTIPART_MODE_MIXED_RELATED?

Nếu email chỉ có plain text, HTML và PDF attachment, `MULTIPART_MODE_MIXED` thường diễn đạt đúng nhu cầu.

Nếu email có thêm **ảnh inline được tham chiếu bằng CID** trong HTML, cần nhóm body với các inline resource bằng `multipart/related`, đồng thời giữ attachment độc lập bên ngoài. Khi đó dùng:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
~~~

Cấu trúc khái quát:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html
│   │       <img src="cid:brand-logo">
│   └── image/png
│       Content-ID: <brand-logo>
└── application/pdf
    Content-Disposition: attachment
    filename="invoice.pdf"
~~~

Mode này phù hợp khi cùng email có cả **inline image** và **attachment**. Không cần chọn nó chỉ vì có một file PDF; hãy chọn cấu trúc theo những MIME part thật sự có trong email.

## 4. Thêm attachment mà không làm mất alternative

Với `MimeMessageHelper`, trình tự thông dụng là:

1. Tạo `MimeMessage`.
2. Tạo helper ở multipart mode.
3. Đặt địa chỉ, subject và nội dung plain/HTML.
4. Thêm attachment bằng `addAttachment(...)`.
5. Gọi `JavaMailSender.send(message)`.

Ví dụ:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Hóa đơn tháng 11");

String plainText = """
        Hóa đơn tháng 11 đã sẵn sàng.
        Mã hóa đơn: INV-2026-1101
        Vui lòng xem file PDF đính kèm.
        """;

String htmlText = """
        <html lang="vi">
          <body>
            <p>Hóa đơn tháng 11 đã <strong>sẵn sàng</strong>.</p>
            <p>Mã hóa đơn: <strong>INV-2026-1101</strong></p>
            <p>Vui lòng xem file PDF đính kèm.</p>
          </body>
        </html>
        """;

helper.setText(plainText, htmlText);
helper.addAttachment("invoice-2026-1101.pdf", invoiceResource,
        "application/pdf");

mailSender.send(message);
~~~

Trong ví dụ:

- `MULTIPART_MODE_MIXED` tạo container để chứa body và attachment.
- `setText(plainText, htmlText)` tạo cặp alternative.
- `addAttachment(...)` thêm PDF như một phần độc lập.
- `send(message)` gửi đúng message đã được helper chỉnh sửa.

`invoiceResource` là một `InputStreamSource`/`Resource` hợp lệ, cung cấp bytes PDF. Ví dụ này giả định resource đã được tạo và kiểm soát trước đó. Nội dung text và HTML có cùng mã hóa UTF-8.

### 4.1. Vì sao nên gọi setText trước addAttachment?

Đặt body trước rồi thêm attachment giúp trình tự code thể hiện rõ:

~~~java
helper.setText(plainText, htmlText);
helper.addAttachment("invoice.pdf", invoiceResource, "application/pdf");
~~~

Helper quản lý root multipart và các part con. Việc gọi API theo trình tự trên làm rõ đâu là body chính và đâu là tệp độc lập.

Tránh thao tác trực tiếp lên `MimeMessage` để thay toàn bộ content sau khi helper đã dựng multipart. Ví dụ:

~~~java
helper.setText(plainText, htmlText);
helper.addAttachment("invoice.pdf", invoiceResource);

// Không làm việc này sau khi helper đã tạo cấu trúc multipart:
message.setText("Một body mới");
~~~

Lệnh cuối có thể thay nội dung message và làm mất cấu trúc multipart/attachment mà helper đã tạo. Sau khi bắt đầu dùng helper, tiếp tục chỉnh sửa nội dung qua helper; không ghi đè toàn bộ content của message bằng một API khác.

## 5. Các overload addAttachment và nguồn dữ liệu

`MimeMessageHelper` hỗ trợ thêm attachment từ nhiều loại nguồn. Những dạng thường dùng:

~~~java
helper.addAttachment(attachmentFilename, dataSource);
helper.addAttachment(attachmentFilename, inputStreamSource);
helper.addAttachment(attachmentFilename, inputStreamSource, contentType);
~~~

| Đối số | Ý nghĩa |
| --- | --- |
| `attachmentFilename` | Tên file người nhận nhìn thấy trong email |
| `dataSource` | Nguồn dữ liệu cung cấp bytes và content type |
| `inputStreamSource` | Nguồn có thể mở `InputStream` để đọc dữ liệu |
| `contentType` | MIME type như `application/pdf` hoặc `text/csv` |

### 5.1. Dùng Resource của Spring

`Resource` trong Spring cũng triển khai `InputStreamSource`, nên có thể truyền trực tiếp:

~~~java
import org.springframework.core.io.ClassPathResource;
import org.springframework.core.io.Resource;

Resource invoice = new ClassPathResource(
        "mail/invoices/invoice-2026-1101.pdf");

helper.addAttachment(
        "invoice-2026-1101.pdf",
        invoice,
        "application/pdf");
~~~

Nếu file được đặt trong `src/main/resources`:

~~~text
src/main/resources/
└── mail/
    └── invoices/
        └── invoice-2026-1101.pdf
~~~

`ClassPathResource` có thể đọc tài nguyên từ classpath kể cả khi ứng dụng được đóng gói thành JAR. Với file bên ngoài do ứng dụng quản lý, có thể dùng `FileSystemResource`. Không nên lấy đường dẫn file tùy ý từ request rồi đính kèm; hãy kiểm tra quyền truy cập và giới hạn vùng lưu trữ.

### 5.2. Dùng ByteArrayResource khi dữ liệu ở trong bộ nhớ

Nếu PDF đã được tạo thành mảng byte:

~~~java
import org.springframework.core.io.ByteArrayResource;

byte[] pdfBytes = pdfGenerator.createInvoicePdf(invoice);
ByteArrayResource pdf = new ByteArrayResource(pdfBytes);

helper.addAttachment(
        "invoice.pdf",
        pdf,
        "application/pdf");
~~~

`ByteArrayResource` cung cấp stream mới từ dữ liệu trong bộ nhớ. Cách này thuận tiện cho file vừa phải và đã có giới hạn kích thước. Với tài liệu lớn, không nên nạp toàn bộ bytes vào heap nếu ứng dụng có thể dùng một resource/file/stream có khả năng đọc lại phù hợp.

### 5.3. Nguồn InputStreamSource cần mở lại được

Trong quá trình serialize và gửi MIME message, thư viện mail có thể cần đọc dữ liệu attachment. Do đó, `InputStreamSource.getInputStream()` nên cung cấp **một stream mới ở đầu dữ liệu cho mỗi lần được gọi**.

Nguồn thường phù hợp:

| Nguồn | Đặc điểm |
| --- | --- |
| `ClassPathResource` | Mở lại resource từ classpath |
| `FileSystemResource` | Mở lại file được phép truy cập |
| `ByteArrayResource` | Mở stream mới từ byte array |
| `InputStreamSource` tùy chỉnh | Phải tạo stream mới mỗi lần |
| `InputStreamResource` bọc một stream đã mở | Thường chỉ đọc một lần; có thể không phù hợp nếu transport cần đọc lại |

Không nên đọc hết một stream rồi trả lại cùng stream đã tiêu thụ cho lần gọi tiếp theo. Nếu dữ liệu chỉ đến từ nguồn một lần, có thể đọc vào buffer có giới hạn thành `ByteArrayResource` hoặc lưu vào vùng tạm được kiểm soát rồi cung cấp resource mở lại được.

Ví dụ nguồn tùy chỉnh:

~~~java
byte[] bytes = loadPdfBytesWithSizeLimit();
InputStreamSource source = () -> new ByteArrayInputStream(bytes);

helper.addAttachment("report.pdf", source, "application/pdf");
~~~

Mỗi lần helper/transport yêu cầu stream, lambda tạo một `ByteArrayInputStream` mới từ đầu mảng. Hãy kiểm soát dung lượng `bytes` trước khi giữ trong bộ nhớ.

### 5.4. Chọn Content-Type đúng với bytes

| Loại tệp | MIME Content-Type |
| --- | --- |
| PDF | `application/pdf` |
| CSV | `text/csv; charset=UTF-8` |
| Excel Open XML | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` |
| Word Open XML | `application/vnd.openxmlformats-officedocument.wordprocessingml.document` |
| PNG | `image/png` |
| JPEG | `image/jpeg` |
| ZIP | `application/zip` |

Không chọn content type chỉ dựa vào phần mở rộng tên file nếu dữ liệu đến từ nguồn upload. Xác định định dạng thực của bytes, giới hạn loại file được phép và dùng content type phù hợp. MIME type sai có thể khiến người nhận mở nhầm ứng dụng hoặc client xử lý attachment không đúng.

## 6. Nhiều attachment trong cùng email

Một helper multipart có thể thêm nhiều file:

~~~java
helper.setText(plainText, htmlText);

helper.addAttachment("invoice.pdf", invoicePdf, "application/pdf");
helper.addAttachment("terms.pdf", termsPdf, "application/pdf");
helper.addAttachment("details.csv", detailsCsv, "text/csv; charset=UTF-8");

mailSender.send(message);
~~~

Các file là những part độc lập trong root `multipart/mixed`. Chúng không phải các alternative của body. Tên attachment nên có ý nghĩa, không chứa đường dẫn hệ thống và không được lấy nguyên vẹn từ input không đáng tin cậy.

Nếu gửi nhiều file:

- Giới hạn số lượng và tổng dung lượng.
- Kiểm tra mỗi nguồn có thể đọc được.
- Dùng tên file an toàn và content type tương ứng.
- Tránh đính kèm một bản dữ liệu không thuộc người nhận.
- Cân nhắc link tải an toàn thay vì gửi file lớn.

## 7. Khi email có cả alternative, inline image và attachment

Một email phức tạp có thể gồm:

- Bản text plain.
- Bản HTML.
- Logo hoặc biểu tượng được nhúng inline bằng CID.
- PDF độc lập để người nhận tải về.

Lúc này nên chọn `MULTIPART_MODE_MIXED_RELATED`:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("lan@example.net");
helper.setSubject("Hóa đơn điện tử");

String plainText = """
        Hóa đơn INV-2026-1101 đã sẵn sàng.
        Vui lòng xem file PDF đính kèm.
        """;

String htmlText = """
        <html lang="vi">
          <body>
            <p><img src="cid:brand-logo" alt="Logo" width="140"></p>
            <p>Hóa đơn <strong>INV-2026-1101</strong> đã sẵn sàng.</p>
            <p>Vui lòng xem file PDF đính kèm.</p>
          </body>
        </html>
        """;

helper.setText(plainText, htmlText);

helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/brand-logo.png"),
        "image/png",
        "brand-logo.png");

helper.addAttachment(
        "invoice-2026-1101.pdf",
        invoicePdf,
        "application/pdf");

mailSender.send(message);
~~~

Thứ tự:

1. Chọn mode mixed-related.
2. Đặt alternative bằng `setText(plainText, htmlText)`.
3. Thêm ảnh inline mà HTML đã tham chiếu bằng `cid:brand-logo`.
4. Thêm PDF như attachment độc lập.
5. Gửi message.

Cấu trúc MIME khái quát:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain; charset=UTF-8
│   │   └── text/html; charset=UTF-8
│   │       <img src="cid:brand-logo">
│   └── image/png
│       Content-ID: <brand-logo>
│       Content-Disposition: inline
└── application/pdf
    Content-Disposition: attachment
    filename="invoice-2026-1101.pdf"
~~~

Đây là mô hình để hiểu quan hệ các phần; chi tiết header và boundary do Jakarta Mail tạo. `multipart/related` nhóm HTML với ảnh mà HTML tham chiếu; `multipart/alternative` chứa các bản text/HTML; `multipart/mixed` ngoài cùng chứa các phần độc lập như PDF.

## 8. Vì sao nên để MimeMessageHelper quản lý MIME tree?

Có thể thao tác trực tiếp với Jakarta Mail `MimeMultipart` và `MimeBodyPart`, nhưng phải tự quản lý:

- Root multipart và subtype.
- Alternative multipart và thứ tự các body part.
- Quan hệ related giữa HTML và ảnh CID.
- Content-Disposition và filename của attachment.
- Content-Type, charset, transfer encoding và boundary.
- Việc gọi `saveChanges()`/serialize phù hợp.

Một lỗi khi đặt `message.setContent(...)` có thể ghi đè cấu trúc mà helper hoặc code trước đó đã dựng. Khi đã chọn `MimeMessageHelper`, hãy tiếp tục thêm nội dung bằng các API của helper:

~~~java
helper.setText(plainText, htmlText);
helper.addInline("brand-logo", logo, "image/png");
helper.addAttachment("invoice.pdf", invoice, "application/pdf");
~~~

Không cần tự tạo chuỗi boundary hoặc ghép MIME bằng string. Jakarta Mail chịu trách nhiệm serialize các part và boundary theo cấu trúc đối tượng.

### 8.1. Khi nào nên tự xây dựng MimeMultipart?

Chỉ cân nhắc tự xây dựng khi ứng dụng có yêu cầu MIME đặc biệt mà helper không đáp ứng, ví dụ cấu trúc lồng nhiều cấp tùy biến hoặc xử lý một định dạng message đã có. Khi đó cần hiểu rõ Jakarta Mail API, MIME subtype, thứ tự part và kiểm tra raw message. Không nên trộn hai cách quản lý trong cùng một message: một phần do helper quản lý, một phần bị code khác thay toàn bộ content.

## 9. Các lỗi thường gặp khi thêm attachment

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Attachment không xuất hiện | Helper được tạo ở chế độ non-multipart | Khởi tạo multipart mode trước khi thêm file |
| Chỉ thấy một body, mất alternative | Dùng `setText(html, true)` thay cho `setText(plain, html)` | Tạo cả hai phiên bản nội dung |
| Attachment thay thế HTML/plain | Đặt attachment vào sai vị trí trong MIME alternative | Dùng root mixed với alternative làm body |
| Body bị mất sau khi thêm file | Gọi `message.setText`/`setContent` sau khi helper đã dựng multipart | Không ghi đè toàn bộ content; dùng helper nhất quán |
| File có tên nhưng không mở được | Resource rỗng, bytes lỗi hoặc content type sai | Kiểm tra nguồn, bytes và MIME type |
| Gửi lỗi stream | Nguồn chỉ mở được một lần hoặc stream đã đóng | Dùng Resource/InputStreamSource mở lại được |
| Tên file không như mong đợi | Nhầm tên resource với tên attachment | Truyền tên file vào đối số `attachmentFilename` |
| PDF hiển thị như text | Content-Type không đúng | Dùng `application/pdf` cho bytes PDF hợp lệ |
| Chỉ thiếu một trong nhiều file | Nguồn tương ứng lỗi hoặc quá trình tạo part thất bại | Xác minh từng resource trước khi gửi |
| Email quá lớn hoặc bị provider từ chối | Tổng MIME vượt giới hạn server | Giảm dung lượng, nén hợp lý hoặc dùng link tải |

### 9.1. Quên bật multipart

Code sai:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setText(plainText, htmlText);
helper.addAttachment("invoice.pdf", invoiceResource, "application/pdf");
~~~

`false` có nghĩa không tạo multipart. Khi cần nhiều MIME part, phải khởi tạo helper ở chế độ multipart:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8");
~~~

### 9.2. Chỉ tạo HTML body mà không có plain alternative

Code:

~~~java
helper.setText(htmlText, true);
helper.addAttachment("invoice.pdf", invoiceResource);
~~~

Code này có thể gửi HTML cùng attachment nếu helper đang multipart, nhưng **không có bản plain text thay thế**. Nếu yêu cầu là cả hai định dạng, dùng:

~~~java
helper.setText(plainText, htmlText);
~~~

### 9.3. Gọi message.setText sau khi đã thêm attachment

Code không nên dùng:

~~~java
helper.setText(plainText, htmlText);
helper.addAttachment("invoice.pdf", invoiceResource);
message.setText("Nội dung mới");
~~~

`message.setText` có thể thay content đã được helper tổ chức thành multipart. Khi cần cập nhật body, hãy cập nhật qua helper trước khi gửi; tránh ghi đè root content sau khi đã thêm attachment.

### 9.4. Dùng addInline thay cho addAttachment

`addInline` dành cho resource được body HTML tham chiếu bằng `cid:...`. Một PDF cần tải về thường phải dùng `addAttachment`. Dùng sai API có thể khiến client hiển thị file không đúng mục đích.

### 9.5. Gửi một InputStream đã dùng hết

Nếu `InputStreamSource` trả lại cùng stream đã đọc hết, Jakarta Mail có thể gặp EOF khi serialize part. Dùng `ClassPathResource`, `FileSystemResource`, `ByteArrayResource` hoặc một nguồn tùy chỉnh tạo stream mới cho mỗi lần đọc.

## 10. Kiểm tra cấu trúc MIME trước khi gửi

Trong môi trường thử nghiệm, có thể serialize `MimeMessage` thành tệp `.eml` để xem root multipart, alternative và attachment:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8");

helper.setFrom("billing@example.com");
helper.setTo("test@example.net");
helper.setSubject("Kiểm tra alternative và attachment");
helper.setText(
        "Báo cáo đã sẵn sàng.",
        "<p>Báo cáo đã <strong>sẵn sàng</strong>.</p>");
helper.addAttachment(
        "report.pdf",
        new ClassPathResource("mail/report.pdf"),
        "application/pdf");

message.saveChanges();
try (OutputStream output =
             Files.newOutputStream(Path.of("mail-preview.eml"))) {
    message.writeTo(output);
}
~~~

Đoạn code giả định có import `java.io.OutputStream`, `java.nio.file.Files`, `java.nio.file.Path`, `ClassPathResource` và xử lý `IOException`/`MessagingException`. Nó chỉ ghi message ra file; **không gửi email** vì chưa gọi `mailSender.send(message)`.

Trong raw MIME, kiểm tra các dấu hiệu:

~~~text
Content-Type: multipart/mixed; boundary="..."

--...
Content-Type: multipart/alternative; boundary="..."

--...
Content-Type: text/plain; charset=UTF-8

Báo cáo đã sẵn sàng.
--...
Content-Type: text/html; charset=UTF-8

<p>Báo cáo đã <strong>sẵn sàng</strong>.</p>
--...
Content-Type: application/pdf
Content-Disposition: attachment; filename="report.pdf"
Content-Transfer-Encoding: base64
~~~

Đây là **đoạn minh họa đã lược bớt boundary và bytes**, không phải raw email hoàn chỉnh. Header và cách encode cụ thể có thể khác theo Jakarta Mail. Cần xác nhận:

- Root là `multipart/mixed`.
- Body chứa `multipart/alternative`.
- Có cả part `text/plain` và `text/html`.
- Attachment có `Content-Disposition: attachment` và filename hợp lý.
- Content-Type của attachment đúng với định dạng bytes.

Không cần kiểm tra boundary có giá trị cụ thể nào; boundary do Jakarta Mail tự sinh và quản lý.

## 11. Kiểm thử qua SMTP sink

Một tệp `.eml` chứng minh đối tượng message đã được serialize, nhưng chưa kiểm tra hết cách server và client xử lý. Có thể dùng SMTP sink cục bộ như Mailpit/MailHog để:

1. Chạy ứng dụng với profile local trỏ tới SMTP sink.
2. Gửi một message chứa plain text, HTML và một PDF giả lập.
3. Mở giao diện sink để xác nhận body và file đã nhận.
4. Xem raw MIME và kiểm tra root/alternative/attachment.
5. Tải PDF từ sink và xác nhận bytes giống tài liệu thử nghiệm.
6. Mở email trên các mail client mục tiêu để kiểm tra cách trình bày.

Không gửi email kiểm thử tới khách hàng hoặc địa chỉ công cộng nếu chưa có mục đích rõ ràng và môi trường được kiểm soát. SMTP sink xác nhận luồng ứng dụng gửi tới môi trường thử nghiệm; nó không chứng minh provider production sẽ chấp nhận mọi file hoặc mọi mail client sẽ hiển thị giống nhau.

### 11.1. Kiểm tra cả hai alternative

Không chỉ xem HTML trong giao diện sink. Hãy kiểm tra raw MIME có đủ:

~~~text
text/plain; charset=UTF-8
text/html; charset=UTF-8
~~~

Plain text cần có thông tin thiết yếu như mã hóa đơn, trạng thái và hướng dẫn xem tài liệu. HTML có thể trình bày đẹp hơn, nhưng không nên chứa thông tin duy nhất mà bản plain text bỏ mất.

### 11.2. Kiểm tra attachment

- Tên file hiển thị đúng với mục đích nghiệp vụ.
- Content-Type đúng với dữ liệu.
- Bytes mở được bằng ứng dụng phù hợp.
- Kích thước nằm trong giới hạn hệ thống và nhà cung cấp.
- File không bị nhầm giữa người nhận này và người nhận khác.
- Không đưa file chứa dữ liệu nhạy cảm vào email gửi nhầm địa chỉ.

## 12. Quản lý kích thước và bảo mật attachment

Attachment làm tăng tổng dung lượng email. Với MIME transfer encoding như Base64, kích thước truyền thường lớn hơn dữ liệu nhị phân gốc (xấp xỉ thêm một phần ba, chưa tính header và boundary). Vì thế file PDF 20 MB có thể làm email vượt giới hạn provider dù file gốc vẫn dưới giới hạn tải lên.

Trước khi thêm attachment:

- Đặt giới hạn số file và tổng dung lượng.
- Kiểm tra quyền người nhận đối với từng tài liệu.
- Xác định định dạng thực, không tin tên file hoặc MIME header do client cung cấp.
- Tạo tên attachment an toàn, không chứa đường dẫn hệ thống hoặc ký tự điều khiển.
- Không đính kèm file thực thi hoặc loại tệp bị chính sách hệ thống cấm.
- Với tài liệu lớn, cân nhắc link tải có thời hạn và quyền truy cập thay vì đính kèm.
- Không log nội dung bytes hoặc toàn bộ email có dữ liệu nhạy cảm.

Một ví dụ kiểm tra kích thước khi đã có bytes:

~~~java
private static final long MAX_ATTACHMENT_BYTES = 10L * 1024 * 1024;

static ByteArrayResource asPdf(byte[] bytes) {
    if (bytes == null || bytes.length == 0
            || bytes.length > MAX_ATTACHMENT_BYTES) {
        throw new IllegalArgumentException("Attachment size is not allowed");
    }
    // Trong thực tế cần xác minh bytes là PDF hợp lệ trước khi dùng.
    return new ByteArrayResource(bytes);
}
~~~

Giới hạn `10 MiB` chỉ là ví dụ chính sách ứng dụng; giới hạn phù hợp phụ thuộc SMTP provider, hệ thống nhận và dung lượng còn lại sau MIME encoding.

## 13. Tách template body khỏi bước đính kèm

Trong ứng dụng lớn, nên tách trách nhiệm:

~~~text
InvoiceService
   |
   v
InvoiceDocumentService
   | tạo PDF / kiểm tra quyền và kích thước
   v
InvoiceEmailContent
   | plainText + htmlText + attachment resource
   v
InvoiceMailer
   | MimeMessageHelper
   | setText(plain, html)
   | addAttachment(...)
   v
JavaMailSender.send(message)
~~~

Service tạo nội dung không cần tự biết SMTP host. Service gửi mail không nên tự quyết định người dùng có quyền xem PDF hay không; việc kiểm tra quyền phải diễn ra trước khi tạo và gắn file.

Một DTO nội bộ có thể mô tả attachment:

~~~java
public record MailAttachment(
        String filename,
        InputStreamSource content,
        String contentType) {
}
~~~

Mailer có thể nhận danh sách attachment đã được chuẩn bị:

~~~java
helper.setText(plainText, htmlText);

for (MailAttachment attachment : attachments) {
    helper.addAttachment(
            attachment.filename(),
            attachment.content(),
            attachment.contentType());
}
~~~

Đây là cấu trúc minh họa; cần validate danh sách, filename, content type và quyền truy cập ở tầng thích hợp trước khi gọi mailer. Mỗi `InputStreamSource` phải đáp ứng yêu cầu mở stream có thể lặp lại.

## 14. Câu hỏi thường gặp

**“`setText(plainText, htmlText)` có tự thêm attachment không?”**  
Không. Nó tạo các phiên bản nội dung thay thế. Dùng `addAttachment(...)` để thêm file độc lập.

**“Tại sao attachment nên nằm trong multipart/mixed?”**  
Vì attachment là phần bổ sung độc lập. `multipart/alternative` có ngữ nghĩa các phiên bản thay thế của cùng nội dung; đặt file ở đó không diễn đạt đúng ý định.

**“Có thể gửi HTML và PDF mà không có plain text không?”**  
Có. Dùng một body HTML và attachment trong multipart. Nhưng nếu yêu cầu có fallback plain text, hãy dùng `setText(plainText, htmlText)`.

**“Có thể dùng `new MimeMessageHelper(message, true, "UTF-8")` không?”**  
Có. Đây là cách bật multipart với mode mặc định của helper. Nếu muốn thể hiện rõ root mixed cho alternative + attachment, có thể dùng `MULTIPART_MODE_MIXED`.

**“Khi có ảnh inline và PDF, nên dùng mode nào?”**  
`MULTIPART_MODE_MIXED_RELATED` thường phù hợp: related nhóm body và ảnh CID, mixed bên ngoài chứa attachment độc lập.

**“Có cần tự tạo MimeMultipart và boundary không?”**  
Không khi dùng `MimeMessageHelper`. Helper và Jakarta Mail quản lý MIME tree/boundary. Tránh trộn việc quản lý content thủ công với helper.

**“Gọi addAttachment trước setText có được không?”**  
Hãy đặt body trước rồi thêm attachment để code rõ ràng và giữ cấu trúc helper nhất quán. Tránh ghi đè message content sau khi helper đã dựng các part.

**“Tại sao file không mở được dù email đã gửi?”**  
Kiểm tra resource bytes, content type, filename, transfer encoding và giới hạn của provider. SMTP chấp nhận message không chứng minh file bên trong hợp lệ.

**“Dùng InputStreamResource cho attachment được không?”**  
Chỉ khi nguồn đáp ứng việc mở stream mà Jakarta Mail cần. Stream đã mở/đã tiêu thụ một lần có thể không đọc lại được. Resource mở lại được hoặc ByteArrayResource thường dễ kiểm soát hơn.

**“Nếu chỉ có một PDF thì có cần multipart/alternative?”**  
Không. `multipart/mixed` có thể chứa một body đơn giản và attachment. Chỉ tạo alternative khi thực sự cung cấp nhiều phiên bản nội dung.

## 15. Ghi nhớ cấu trúc và trình tự

Đối với email có plain text, HTML và attachment:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/alternative
    │   ├── text/plain
    │   └── text/html
    └── application/pdf (attachment)
~~~

Đối với email có thêm ảnh inline:

~~~text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── multipart/alternative
    │   │   ├── text/plain
    │   │   └── text/html (cid reference)
    │   └── image/png (inline)
    └── application/pdf (attachment)
~~~

Trong Spring Framework Mail, cách triển khai thường dùng:

~~~java
MimeMessage message = mailSender.createMimeMessage();
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8");

helper.setText(plainText, htmlText);
helper.addAttachment("report.pdf", reportResource, "application/pdf");

mailSender.send(message);
~~~

Nếu có ảnh CID, chuyển sang `MULTIPART_MODE_MIXED_RELATED` và thêm `addInline(...)` sau khi đặt body. **Không thay root content sau khi helper đã dựng multipart**. Giữ đúng ngữ nghĩa alternative và mixed giúp mail client chọn phiên bản body phù hợp trong khi vẫn nhận được attachment độc lập, đúng tên và đúng loại nội dung.
