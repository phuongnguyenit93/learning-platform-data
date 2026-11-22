# Phân biệt attachment với inline resource

Khi gửi email bằng Spring Framework Mail, một thông điệp có thể chứa nhiều loại nội dung: văn bản, HTML, ảnh, PDF, bảng tính hoặc tài liệu khác. Một số tệp được gửi để người nhận tải xuống như tài liệu độc lập; một số tài nguyên được nhúng để hiển thị ngay bên trong phần HTML. Hai mục đích này thường được gọi là **attachment** và **inline resource**.

Spring cung cấp hai API tương ứng trong **MimeMessageHelper**:

~~~java
helper.addAttachment(
        "invoice.pdf",
        pdfResource,
        "application/pdf"
);

helper.addInline(
        "companyLogo",
        logoResource,
        "image/png"
);
~~~

**addAttachment(...)** thêm một tệp đính kèm độc lập, thường có tên file và Content-Disposition là **attachment**. **addInline(...)** thêm một tài nguyên được nội dung email tham chiếu, thường qua **Content-ID** và URL **cid:** trong HTML.

Điểm khác biệt nằm ở **ý định sử dụng và cách MIME mô tả mối quan hệ giữa các part**. Cả hai đều là dữ liệu được đóng gói trong một email; cả hai có thể được biểu diễn bằng MIME part và được gửi trong cùng một lần gọi SMTP. Tuy nhiên, cách người nhận tìm và sử dụng chúng khác nhau.

## 1. Hai mục đích hiển thị khác nhau

Hãy hình dung email báo cáo có logo và một file PDF:

~~~text
Email
├── Nội dung HTML
│   ├── Tiêu đề báo cáo
│   ├── Logo hiển thị trong nội dung
│   └── Lời nhắn
└── Attachment
    └── report.pdf
~~~

Logo được đặt ngay trong nội dung HTML. Người nhận nhìn thấy logo khi đọc email, nếu client hỗ trợ hiển thị inline resource. PDF là tài liệu riêng; người nhận có thể mở hoặc lưu file từ danh sách tệp đính kèm.

| Câu hỏi | Attachment | Inline resource |
| --- | --- | --- |
| Mục đích chính | Gửi một tệp độc lập để người nhận mở hoặc tải | Cung cấp tài nguyên cho nội dung email, thường là HTML |
| API Spring | **addAttachment(...)** | **addInline(...)** |
| Metadata thường gặp | **Content-Disposition: attachment** | **Content-Disposition: inline** |
| Định danh liên kết | Filename | **Content-ID** |
| HTML tham chiếu | Thường không cần | **cid:contentId** |
| MIME container thường dùng | **multipart/mixed** | **multipart/related** |
| Ví dụ | PDF hóa đơn, CSV, ZIP | Logo, ảnh minh họa, biểu đồ trong HTML |

Một email client có thể hiển thị ảnh inline trong khu vực attachment hoặc cho phép lưu ảnh đó. Đây là cách trình bày của client. Nó không làm thay đổi mục đích khi ứng dụng tạo message: ảnh được thêm để HTML tham chiếu, còn PDF được thêm như một tài liệu độc lập.

## 2. Attachment là gì?

**Attachment** là một MIME part được gửi kèm email để người nhận có thể mở hoặc lưu như một tệp riêng. Thông thường part có:

- **Content-Type** mô tả loại dữ liệu.
- **Content-Disposition: attachment** gợi ý cách trình bày là tệp đính kèm.
- **filename** cung cấp tên file được đề xuất cho người nhận.
- **Content-Transfer-Encoding** mô tả cách dữ liệu được biểu diễn trong message, thường là Base64 với dữ liệu nhị phân.

Ví dụ một part PDF:

~~~text
Content-Type: application/pdf
Content-Disposition: attachment; filename="invoice.pdf"
Content-Transfer-Encoding: base64

[du-lieu-PDF-duoc-ma-hoa]
~~~

Phần dữ liệu trong dấu ngoặc vuông là ký hiệu minh họa, không phải nội dung PDF thật.

Người nhận không cần một thẻ HTML để tìm file này. Email client nhận diện part qua MIME header và hiển thị nó như một attachment.

### 2.1. Dùng addAttachment trong Spring Mail

Để gửi attachment, cần tạo **MimeMessage** và **MimeMessageHelper** ở chế độ multipart:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);

helper.setFrom("billing@example.org");
helper.setTo("customer@example.net");
helper.setSubject("Hóa đơn của bạn");
helper.setText(
        "Xin chào,\nVui lòng xem hóa đơn đính kèm.",
        false
);

helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail/invoice.pdf"),
        "application/pdf"
);

mailSender.send(message);
~~~

Trong ví dụ:

- **createMimeMessage()** tạo thông điệp MIME.
- **MULTIPART_MODE_MIXED** cho phép kết hợp body và các phần độc lập như attachment.
- **setText(...)** đặt nội dung email.
- **addAttachment(...)** thêm PDF với filename và MIME type.
- **send(...)** gửi toàn bộ message, bao gồm body và attachment.

**SimpleMailMessage** không hỗ trợ attachment. Khi cần gửi file, HTML phức tạp hoặc inline resource, hãy sử dụng MimeMessage.

### 2.2. Filename không phải đường dẫn file

Tham số đầu của addAttachment là tên hiển thị cho người nhận:

~~~java
helper.addAttachment(
        "invoice-2026-001.pdf",
        pdfResource,
        "application/pdf"
);
~~~

Nó không phải đường dẫn lưu trên máy gửi và không yêu cầu ứng dụng phải tạo file vật lý có đúng tên đó. Nếu dữ liệu đến từ byte array, tên file vẫn được truyền riêng.

Không nên dùng đường dẫn nội bộ như **C:\app\private\invoice.pdf** làm filename vì có thể làm lộ cấu trúc filesystem và tạo tên không phù hợp cho người nhận.

## 3. Inline resource là gì?

**Inline resource** là một MIME part được thêm vào message để phần nội dung khác tham chiếu tới nó. Trường hợp phổ biến nhất là HTML sử dụng URL **cid:** để hiển thị ảnh.

Ví dụ HTML:

~~~html
<html>
  <body>
    <h1>Chào mừng!</h1>
    <img src="cid:companyLogo" alt="Logo công ty">
    <p>Cảm ơn bạn đã đăng ký.</p>
  </body>
</html>
~~~

Đoạn HTML này tham chiếu tới một MIME part có Content-ID tương ứng. Nếu message không chứa part đó, client không có dữ liệu inline để giải quyết tham chiếu.

### 3.1. Content-ID nối HTML với MIME part

Một part ảnh có thể có header:

~~~text
Content-Type: image/png
Content-Disposition: inline
Content-ID: <companyLogo>
Content-Transfer-Encoding: base64

[du-lieu-anh-PNG]
~~~

Trong HTML:

~~~html
<img src="cid:companyLogo" alt="Logo công ty">
~~~

Giá trị logic **companyLogo** phải khớp. Dấu ngoặc nhọn trong header là cách biểu diễn Content-ID; trong lời gọi helper và URL cid: thông thường chỉ dùng giá trị định danh.

Java:

~~~java
helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

Không cần truyền **<companyLogo>** vào tham số contentId. Hãy để Spring Mail tạo header theo cú pháp MIME.

### 3.2. Dùng addInline trong Spring Mail

Một message có HTML và ảnh inline:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);

helper.setFrom("notifications@example.org");
helper.setTo("user@example.net");
helper.setSubject("Thông báo");

String html = """
        <html>
          <body>
            <p>Xin chào!</p>
            <img src="cid:companyLogo"
                 alt="Logo công ty"
                 width="160">
          </body>
        </html>
        """;

helper.setText(html, true);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

mailSender.send(message);
~~~

Ở đây:

- **setText(html, true)** khai báo phần thân là HTML.
- **addInline(...)** thêm ảnh vào message và gắn Content-ID.
- **src="cid:companyLogo"** chỉ đến ảnh đã nhúng.
- **MULTIPART_MODE_RELATED** thể hiện mối quan hệ giữa HTML và tài nguyên liên quan.

### 3.3. Gọi setText trước addInline

Với MimeMessageHelper, nên thiết lập body bằng **setText(...)** trước khi thêm inline resource:

~~~java
helper.setText(html, true);
helper.addInline("companyLogo", logoResource, "image/png");
~~~

Thứ tự này được Spring Mail khuyến nghị vì một số email client nhạy cảm với cách các MIME part được bố trí. Nó giúp helper thiết lập nội dung trước rồi mới thêm các resource được nội dung tham chiếu.

Tránh đảo thứ tự nếu không có lý do rõ ràng:

~~~java
helper.addInline("companyLogo", logoResource, "image/png");
helper.setText(html, true);
~~~

### 3.4. Inline không có nghĩa ảnh chắc chắn xuất hiện

Email client có thể ẩn ảnh, chọn bản plain text, không hỗ trợ định dạng ảnh hoặc trình bày part inline trong khu vực attachment. MIME structure đúng giúp client hiểu ý định, nhưng không thể điều khiển hoàn toàn giao diện và chính sách hiển thị của ứng dụng nhận thư.

Vì vậy, hãy dùng **alt text**, giữ thông tin quan trọng ở dạng chữ và kiểm tra trên các client mục tiêu.

## 4. Phân biệt Content-Disposition: attachment và inline

**Content-Disposition** là một MIME header gợi ý cách trình bày một part.

Ví dụ attachment:

~~~text
Content-Disposition: attachment; filename="report.pdf"
~~~

Ví dụ inline:

~~~text
Content-Disposition: inline
Content-ID: <reportLogo>
~~~

Ý nghĩa:

- **attachment**: part được cung cấp như một tệp độc lập để người nhận mở hoặc tải.
- **inline**: part có thể được hiển thị cùng nội dung, nếu cấu trúc message và client hỗ trợ.

Tuy nhiên, chỉ nhìn vào Content-Disposition là chưa đủ để kết luận một part sẽ hiển thị chính xác ra sao. Với inline image, mối quan hệ **multipart/related** và **Content-ID** rất quan trọng. Với attachment, filename và MIME type giúp client nhận diện tài liệu.

Một part có disposition inline vẫn có thể được client liệt kê như attachment. Một part có disposition attachment cũng có thể được người dùng tải xuống và mở bên ngoài email. Header thể hiện ý định của người gửi; client quyết định cách trình bày cuối cùng.

## 5. multipart/mixed và multipart/related

Hai subtype MIME thường gặp khi gửi attachment và inline resource là **multipart/mixed** và **multipart/related**.

### 5.1. multipart/mixed cho các phần độc lập

Khi email có phần thân và một PDF đính kèm, cấu trúc thường là:

~~~text
multipart/mixed
├── text/plain
└── application/pdf
    └── Content-Disposition: attachment
~~~

Các part là những thành phần độc lập của cùng message. PDF không cần được HTML tham chiếu.

### 5.2. multipart/related cho nội dung và tài nguyên liên quan

Khi email có HTML và logo inline:

~~~text
multipart/related
├── text/html
│   └── <img src="cid:companyLogo">
└── image/png
    └── Content-ID: <companyLogo>
~~~

HTML và ảnh phối hợp để tạo một nội dung hoàn chỉnh. Part ảnh không chỉ là tài liệu độc lập; nó được HTML tham chiếu.

### 5.3. Kết hợp cả attachment và inline resource

Một email báo cáo có HTML, logo và PDF có thể được tổ chức như sau:

~~~text
multipart/mixed
├── multipart/related
│   ├── text/html
│   │   └── <img src="cid:companyLogo">
│   └── image/png
│       └── Content-ID: <companyLogo>
└── application/pdf
    └── Content-Disposition: attachment
~~~

Nhánh **multipart/related** chứa HTML cùng ảnh. PDF là part độc lập nằm trong root **multipart/mixed**.

Đây là lý do Spring cung cấp **MULTIPART_MODE_MIXED_RELATED**: tạo cấu trúc mixed ở ngoài và related ở nhánh nội dung có tài nguyên inline.

### 5.4. Khi có plain text và HTML

Email có thể cung cấp cả hai biểu diễn:

~~~text
multipart/mixed
├── multipart/related
│   ├── multipart/alternative
│   │   ├── text/plain
│   │   └── text/html
│   │       └── <img src="cid:companyLogo">
│   └── image/png
│       └── Content-ID: <companyLogo>
└── application/pdf
    └── Content-Disposition: attachment
~~~

Bản plain text và HTML là các lựa chọn thay thế của cùng nội dung; ảnh inline phục vụ bản HTML. PDF vẫn là attachment độc lập.

Sơ đồ trên mô tả quan hệ MIME thường dùng. Cây chính xác và boundary do thư viện mail tạo, có thể thay đổi theo cách cấu hình message và phiên bản provider.

## 6. Chọn multipart mode trong MimeMessageHelper

Spring Framework cung cấp các mode thường gặp:

| Mode | Ý nghĩa | Tình huống phù hợp |
| --- | --- | --- |
| **MULTIPART_MODE_NO** | Không tạo multipart | Email không có attachment hoặc inline part |
| **MULTIPART_MODE_MIXED** | Root multipart/mixed | Body và attachment độc lập |
| **MULTIPART_MODE_RELATED** | Root multipart/related | HTML cùng inline resource |
| **MULTIPART_MODE_MIXED_RELATED** | Root mixed với nhánh related lồng nhau | HTML, inline resource và attachment |

Ví dụ chỉ có PDF attachment:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);
~~~

Ví dụ chỉ có HTML và logo:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);
~~~

Ví dụ có HTML, logo và PDF:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

Constructor boolean tiện dụng:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
~~~

Trong Spring Framework, **true** bật multipart theo mode mặc định **MULTIPART_MODE_MIXED_RELATED**. Nếu cần thể hiện chính xác ý định cấu trúc, dùng hằng số mode tường minh sẽ dễ đọc hơn.

## 7. Ví dụ hoàn chỉnh: email có logo inline và PDF attachment

Giả sử ứng dụng gửi báo cáo cho quản lý. Nội dung HTML có logo và lời giới thiệu; PDF là tài liệu riêng để tải xuống.

### 7.1. Cấu trúc tài nguyên

~~~text
src/main/resources/
└── mail/
    └── logo.png
~~~

PDF được tạo bởi service báo cáo và trả về byte[]:

~~~java
byte[] reportPdf = reportGenerator.generate(month);
~~~

### 7.2. Code gửi email

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class ReportMailService {

    private final JavaMailSender mailSender;

    public ReportMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendReport(
            String recipient,
            byte[] reportPdf
    ) throws MessagingException {

        if (reportPdf == null || reportPdf.length == 0) {
            throw new IllegalArgumentException(
                    "Nội dung báo cáo PDF không được để trống"
            );
        }

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("reports@example.org");
        helper.setTo(recipient);
        helper.setSubject("Báo cáo tháng");

        String plainText =
                "Báo cáo tháng đã sẵn sàng. "
                + "Vui lòng xem file PDF đính kèm.";

        String htmlText = """
                <html>
                  <body>
                    <img src="cid:companyLogo"
                         alt="Logo công ty"
                         width="150">
                    <h1>Báo cáo tháng</h1>
                    <p>Báo cáo của bạn đã được tạo.</p>
                    <p>Vui lòng xem file PDF đính kèm.</p>
                  </body>
                </html>
                """;

        // Thiết lập body trước.
        helper.setText(plainText, htmlText);

        // Logo được HTML tham chiếu bằng cid:companyLogo.
        helper.addInline(
                "companyLogo",
                new ClassPathResource("mail/logo.png"),
                "image/png"
        );

        // PDF là tài liệu độc lập để tải về.
        helper.addAttachment(
                "monthly-report.pdf",
                new ByteArrayResource(reportPdf),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

Ví dụ giả định **reportPdf** là byte PDF hợp lệ, logo tồn tại trên classpath và recipient đã được kiểm tra theo nghiệp vụ. **ByteArrayResource** dùng cho PDF trong bộ nhớ; **ClassPathResource** dùng cho logo tĩnh.

### 7.3. Phân tích kết quả

| Thành phần | Cách tạo | Mục đích |
| --- | --- | --- |
| Plain text | **setText(plainText, htmlText)** | Nội dung dự phòng cho client không dùng HTML |
| HTML | Tham số thứ hai của setText | Bố cục email |
| Logo | **addInline("companyLogo", ...)** | Hiển thị trong HTML qua cid: |
| PDF | **addAttachment("monthly-report.pdf", ...)** | Tệp độc lập để tải |
| To/Subject/From | Các setter tương ứng | Metadata message |

Người nhận có thể thấy logo trong phần HTML và PDF trong danh sách attachment. Nếu client chỉ hiển thị plain text, người nhận vẫn đọc được thông tin chính nhưng không thấy logo.

### 7.4. Tại sao không dùng addAttachment cho logo?

Nếu dùng:

~~~java
helper.addAttachment(
        "logo.png",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);
~~~

thì Spring tạo part attachment theo ý định tải file. HTML chứa **src="cid:companyLogo"** không tự động tìm được part này vì không có Content-ID tương ứng được thiết lập theo cách addInline.

Nếu mục đích là hiển thị ảnh trong HTML, dùng **addInline** với cùng Content-ID. Nếu mục đích là cung cấp ảnh để người nhận tải xuống, dùng **addAttachment**.

## 8. Ví dụ chỉ gửi attachment, không có inline resource

Một email thông báo có thể chỉ chứa plain text và PDF:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED,
        "UTF-8"
);

helper.setTo("customer@example.net");
helper.setSubject("Biên nhận thanh toán");
helper.setText(
        "Biên nhận của bạn được đính kèm trong email này.",
        false
);

helper.addAttachment(
        "receipt.pdf",
        new ByteArrayResource(receiptBytes),
        "application/pdf"
);

mailSender.send(message);
~~~

Ở đây không có HTML tham chiếu CID. PDF chỉ là một file đính kèm. Không cần **MULTIPART_MODE_RELATED** vì không có các part cần liên kết để hiển thị nội dung.

## 9. Ví dụ chỉ có inline resource, không có attachment độc lập

Một email chào mừng có thể chỉ dùng HTML và logo:

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);

helper.setTo("user@example.net");
helper.setSubject("Chào mừng");

String html = """
        <html>
          <body>
            <h1>Chào mừng bạn!</h1>
            <img src="cid:welcomeLogo"
                 alt="Logo"
                 width="160">
            <p>Cảm ơn bạn đã đăng ký.</p>
          </body>
        </html>
        """;

helper.setText(html, true);

helper.addInline(
        "welcomeLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

mailSender.send(message);
~~~

Không cần addAttachment nếu không có tài liệu độc lập để người nhận tải. Logo đã là một MIME part, nhưng được dùng như resource của HTML.

## 10. Nhiều attachment và nhiều inline resource trong cùng email

Một email có thể chứa nhiều loại part. Ví dụ báo cáo có logo, biểu đồ inline, PDF và CSV:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);

helper.setText(html, true);

helper.addInline(
        "companyLogo",
        new ClassPathResource("mail/logo.png"),
        "image/png"
);

helper.addInline(
        "salesChart",
        new ByteArrayResource(chartPngBytes),
        "image/png"
);

helper.addAttachment(
        "report.pdf",
        new ByteArrayResource(pdfBytes),
        "application/pdf"
);

helper.addAttachment(
        "details.csv",
        new ByteArrayResource(csvBytes),
        "text/csv; charset=UTF-8"
);
~~~

HTML:

~~~html
<html>
  <body>
    <img src="cid:companyLogo" alt="Logo">
    <h2>Doanh thu</h2>
    <img src="cid:salesChart" alt="Biểu đồ doanh thu">
    <p>File PDF và CSV được đính kèm.</p>
  </body>
</html>
~~~

Cấu trúc khái niệm:

~~~text
multipart/mixed
└── multipart/related
    ├── text/html
    │   ├── cid:companyLogo
    │   └── cid:salesChart
    ├── image/png
    │   └── Content-ID: <companyLogo>
    └── image/png
        └── Content-ID: <salesChart>
    ├── application/pdf
    │   └── Content-Disposition: attachment
    └── text/csv
        └── Content-Disposition: attachment
~~~

Sơ đồ trên chỉ minh họa quan hệ logic. Các MIME part cụ thể được helper tổ chức theo cấu trúc multipart của nó. Mỗi inline resource cần Content-ID riêng và HTML phải tham chiếu đúng ID. Các attachment độc lập không cần CID.

## 11. Có thể dùng cùng một Resource cho cả hai mục đích không?

Về mặt dữ liệu, cùng một nguồn byte có thể được dùng để tạo part inline hoặc attachment. Nhưng **mỗi lần thêm part cần API phản ánh đúng mục đích**.

Ví dụ, nếu ứng dụng muốn vừa hiển thị logo trong HTML vừa cung cấp file logo tải riêng, có thể thêm hai part:

~~~java
ClassPathResource logo =
        new ClassPathResource("mail/logo.png");

helper.setText(html, true);

helper.addInline(
        "companyLogo",
        logo,
        "image/png"
);

helper.addAttachment(
        "company-logo.png",
        logo,
        "image/png"
);
~~~

Điều này tạo hai MIME part từ cùng nguồn dữ liệu: một part liên quan HTML và một part độc lập. Email sẽ lớn hơn vì dữ liệu ảnh có thể được đóng gói hai lần. Chỉ làm khi nghiệp vụ thực sự cần cả hai cách sử dụng.

Một số client có thể hiển thị part inline trong attachment list ngay cả khi chỉ có addInline; vì thế, nếu mục tiêu chỉ là hiển thị ảnh, không cần tự thêm attachment thứ hai để “đảm bảo người nhận thấy ảnh”.

## 12. So sánh với ảnh bên ngoài qua HTTPS

Một lựa chọn khác là đặt URL ảnh bên ngoài trong HTML:

~~~html
<img
  src="https://assets.example.org/images/company-logo.png"
  alt="Logo công ty">
~~~

Khi đó ứng dụng không cần nhúng byte ảnh vào MIME message. Email client có thể tải ảnh khi người nhận mở thư, nếu chính sách của client cho phép.

| Tiêu chí | Inline CID | HTTPS image |
| --- | --- | --- |
| Dữ liệu ảnh | Nằm trong message | Nằm trên máy chủ bên ngoài |
| Cần truy cập Internet lúc mở mail | Không cần tải ảnh từ server ngoài | Thường cần |
| Kích thước email | Tăng theo kích thước ảnh và MIME encoding | Thường nhỏ hơn |
| Cập nhật ảnh | Mỗi email mang bản ảnh tại thời điểm gửi | Có thể cập nhật ở URL server |
| Quyền riêng tư | Không cần request tải ảnh từ server ngoài | Request có thể tạo tín hiệu truy cập |
| Khả năng bị chặn | Client vẫn có thể ẩn part inline | Client có thể chặn tải ảnh từ xa |
| Vị trí hiển thị | HTML dùng cid: | HTML dùng URL |

Inline CID phù hợp khi muốn mang theo hình ảnh cùng message, chẳng hạn logo hoặc biểu đồ của một báo cáo. URL HTTPS phù hợp khi ảnh lớn, thay đổi độc lập hoặc muốn giảm kích thước email. Cần cân nhắc quyền riêng tư và chính sách tải nội dung từ xa của email client.

## 13. MIME type và filename: mỗi mục đích vẫn cần metadata đúng

Dù là attachment hay inline resource, MIME part cần loại nội dung phù hợp.

| Dữ liệu | MIME type thường dùng |
| --- | --- |
| PDF | **application/pdf** |
| CSV | **text/csv; charset=UTF-8** |
| PNG | **image/png** |
| JPEG | **image/jpeg** |
| GIF | **image/gif** |
| Plain text | **text/plain; charset=UTF-8** |
| HTML | **text/html; charset=UTF-8** |

Với attachment, filename giúp người nhận nhận diện tệp:

~~~java
helper.addAttachment(
        "invoice.pdf",
        pdfResource,
        "application/pdf"
);
~~~

Với inline resource, Content-ID là liên kết quan trọng:

~~~java
helper.addInline(
        "invoiceLogo",
        logoResource,
        "image/png"
);
~~~

Một inline image có thể có filename hoặc metadata tên trong MIME, tùy cách thư viện tạo part, nhưng **HTML tìm part bằng Content-ID**, không phải bằng filename.

MIME type không chuyển đổi dữ liệu. Nếu byte thực là JPEG nhưng khai báo image/png, client có thể không hiển thị đúng. Hãy khai báo theo định dạng thực tế.

## 14. Kích thước và hiệu năng

Attachment và inline resource đều làm tăng kích thước email vì dữ liệu của chúng được đóng gói trong MIME message.

Với dữ liệu nhị phân được mã hóa Base64, kích thước biểu diễn thường xấp xỉ **4/3 dữ liệu gốc**, chưa tính xuống dòng, header và boundary. Vì thế, một file 6 MB có thể tạo ra phần dữ liệu vận chuyển lớn hơn 6 MB.

Các điểm cần cân nhắc:

- Giới hạn kích thước mỗi attachment.
- Giới hạn tổng kích thước email.
- Giới hạn số attachment và inline image.
- Tối ưu ảnh logo và biểu đồ trước khi nhúng.
- Không gửi ảnh độ phân giải lớn nếu chỉ hiển thị ở kích thước nhỏ.
- Cân nhắc heap khi dùng ByteArrayResource.
- Xem giới hạn message size của SMTP provider và hệ thống nhận.

Nếu file lớn, có thể dùng FileSystemResource thay vì giữ toàn bộ byte[] trong heap, hoặc cung cấp link tải có thời hạn. Tuy nhiên, FileSystemResource không bảo đảm toàn bộ quá trình gửi hoàn toàn không dùng buffer bộ nhớ; cần xét implementation và provider thực tế.

## 15. Bảo mật khi gửi attachment và inline resource

Hai loại part đều có thể chứa dữ liệu nhạy cảm. Việc đặt dữ liệu thành inline hay attachment không làm nó tự an toàn hơn.

### 15.1. Kiểm tra quyền người nhận

Trước khi gửi, xác định người nhận có quyền xem tài liệu hoặc hình ảnh không. Không lấy ID tài liệu từ request rồi gửi nội dung mà chưa kiểm tra quan hệ giữa tài liệu, người dùng và nghiệp vụ.

### 15.2. Kiểm tra nguồn file và MIME type

Nếu file đến từ upload hoặc storage bên ngoài:

- Kiểm tra định dạng thực tế, không chỉ phần mở rộng.
- Giới hạn kích thước trước khi đọc toàn bộ vào bộ nhớ.
- Chỉ cho phép các loại file theo chính sách.
- Quét mã độc nếu yêu cầu.
- Kiểm tra quyền đọc và quyền gửi tài liệu.

### 15.3. Filename và Content-ID không phải nơi chứa bí mật

Filename có thể được hiển thị cho người nhận. Content-ID xuất hiện trong MIME header và HTML. Không đưa đường dẫn nội bộ, access token, mật khẩu hoặc metadata nhạy cảm vào hai trường này.

### 15.4. Không tự ghép MIME header

Không tạo raw header bằng cách nối chuỗi dữ liệu không tin cậy:

~~~java
message.setHeader(
        "Content-Disposition",
        "attachment; filename=\"" + userFilename + "\""
);
~~~

Hãy dùng **addAttachment** hoặc **addInline** để thư viện xử lý metadata MIME. Filename vẫn cần validation theo chính sách ứng dụng.

### 15.5. HTML động cần escape

Nếu email HTML chứa tên hoặc nội dung do người dùng cung cấp, hãy escape theo ngữ cảnh HTML hoặc dùng template engine có cơ chế escaping phù hợp. Content-ID không bảo vệ phần HTML khỏi HTML injection.

### 15.6. Base64 không phải mã hóa bảo mật

Base64 là cách biểu diễn dữ liệu nhị phân để truyền trong MIME. Người có email có thể giải mã file hoặc ảnh. Nếu nội dung cần bảo vệ, hãy dùng cơ chế mã hóa tài liệu hoặc kênh tải có xác thực theo yêu cầu, không dựa vào việc file là attachment hay inline.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| PDF không xuất hiện trong danh sách file | Không gọi addAttachment hoặc message không multipart | Dùng MimeMessageHelper ở multipart mode |
| Ảnh không hiển thị trong HTML | Không có part CID hoặc ID không khớp | Dùng addInline và đồng bộ cid: |
| Dùng addAttachment cho logo nhưng HTML không tìm thấy | Attachment không được thêm với Content-ID mong đợi | Dùng addInline cho ảnh HTML tham chiếu |
| Dùng addInline cho PDF nhưng người nhận muốn tải file | API thể hiện mục đích inline | Dùng addAttachment |
| HTML hiện nguyên thẻ img | setText(..., false) hoặc body không phải HTML | Dùng setText(html, true) |
| Ảnh inline bị liệt kê như attachment | Cách trình bày của email client | Kiểm tra MIME; chấp nhận khác biệt UI nếu cấu trúc đúng |
| Message quá lớn | Nhiều file/ảnh hoặc ảnh độ phân giải cao | Tối ưu và giới hạn tổng kích thước |
| File đính kèm bị hỏng | MIME type sai hoặc dữ liệu đã encode Base64 trước | Truyền byte gốc và khai báo type đúng |
| Tên file bị lỗi | Filename có ký tự đặc biệt hoặc quá dài | Kiểm tra tên và để thư viện mã hóa header |
| Inline image không đọc được | Resource sai đường dẫn hoặc stream không đọc lại được | Dùng resource hợp lệ có thể mở lại |
| Email không tới inbox | Lỗi chuyển phát, bounce hoặc spam | Phân biệt SMTP accept với delivery |

### 16.1. HTML có cid nhưng không gọi addInline

Ví dụ thiếu part:

~~~html
<img src="cid:logo" alt="Logo">
~~~

Nếu code không gọi:

~~~java
helper.addInline("logo", logoResource, "image/png");
~~~

thì email không có dữ liệu được định danh **logo** để client tìm. Thẻ img chỉ là một tham chiếu.

### 16.2. Gọi addInline nhưng Content-ID khác

Sai:

~~~java
helper.addInline("brandLogo", logoResource, "image/png");
~~~

HTML:

~~~html
<img src="cid:companyLogo">
~~~

Phải thống nhất:

~~~java
helper.addInline("companyLogo", logoResource, "image/png");
~~~

### 16.3. Không bật multipart

Nếu helper được tạo với multipart=false hoặc mode NO, không có cấu trúc phù hợp cho các part riêng. Hãy chọn mode dựa trên loại nội dung.

### 16.4. Gọi setText sau addInline

Nên gọi setText trước addInline theo khuyến nghị của Spring Mail để giảm khác biệt giữa email client.

### 16.5. Cho rằng SMTP send thành công đồng nghĩa ảnh đã hiển thị

SMTP chấp nhận message chỉ là một mốc. Client nhận còn parse MIME, chọn body và quyết định hiển thị hình ảnh. Có thể cần kiểm tra raw MIME trong SMTP capture server và thử trên client mục tiêu.

## 17. Kiểm thử attachment và inline resource

Có thể kiểm tra các phần của message trong môi trường phát triển mà không gửi tới hộp thư thật.

### 17.1. Kiểm tra attachment

Xác nhận:

- Message có multipart.
- Có part attachment.
- Filename đúng.
- Content-Type đúng.
- Byte sau khi giải mã part khớp với dữ liệu nguồn.

### 17.2. Kiểm tra inline resource

Xác nhận:

- HTML có **src="cid:..."**.
- Có MIME part với Content-ID tương ứng.
- Part có loại nội dung đúng.
- Message dùng multipart/related hoặc cấu trúc mixed/related thích hợp.
- Body được thiết lập trước khi gọi addInline.

### 17.3. Dùng SMTP capture server

SMTP capture server giúp nhận email trong môi trường test và quan sát:

- Header message.
- Cây MIME.
- Attachment filename.
- Content-ID.
- Nội dung HTML và plain text.
- Kích thước message.

Đây là cách phù hợp để xác định lỗi do ứng dụng tạo MIME hay do client cuối cùng hiển thị. Không dùng mailbox người dùng thật cho test tự động.

### 17.4. Không kiểm tra bằng boundary cố định

MIME boundary thường được sinh tự động. Test nên kiểm tra nội dung và cấu trúc thông qua parser/API thay vì giả định boundary có một chuỗi cố định hoặc Base64 xuống dòng theo một dạng duy nhất.

## 18. Chọn API theo yêu cầu

| Yêu cầu | API nên dùng | Multipart mode thường phù hợp |
| --- | --- | --- |
| Gửi PDF để tải | **addAttachment** | **MIXED** |
| Gửi CSV để tải | **addAttachment** | **MIXED** |
| Hiển thị logo trong HTML | **addInline** | **RELATED** |
| Hiển thị biểu đồ trong HTML | **addInline** | **RELATED** |
| HTML có logo và PDF attachment | **addInline + addAttachment** | **MIXED_RELATED** |
| Plain text và HTML cùng một message | **setText(plain, html)** | Theo cấu trúc multipart cần thiết |
| Nhiều file đính kèm độc lập | Nhiều lần **addAttachment** | **MIXED** |
| Nhiều ảnh HTML tham chiếu CID | Nhiều lần **addInline** với ID riêng | **RELATED** hoặc **MIXED_RELATED** |

Đây là hướng lựa chọn thông dụng. Mode chính xác còn phụ thuộc việc message có alternative body, inline resource và các part khác hay không.

## 19. Câu hỏi thường gặp

**1. Attachment và inline resource có phải hai loại file hoàn toàn khác nhau không?**

Không. Cả hai đều có thể là dữ liệu ảnh, PDF hoặc loại nội dung khác được đóng gói thành MIME part. Khác biệt chủ yếu là mục đích sử dụng và cách part được liên kết/trình bày trong message.

**2. Có thể dùng addAttachment để hiển thị ảnh trong HTML không?**

Không nên dựa vào addAttachment cho mục đích đó. Nếu HTML tham chiếu bằng cid:, hãy dùng addInline để tạo part có Content-ID tương ứng.

**3. addInline có làm ảnh xuất hiện trong mọi email client không?**

Không. Client có thể ẩn ảnh, chọn plain text hoặc xử lý MIME khác nhau. Hãy kiểm tra trên các client mục tiêu và giữ nội dung quan trọng ở dạng chữ.

**4. Content-ID có phải tên file ảnh không?**

Không. Content-ID là định danh để HTML tìm part. Filename và Content-ID có thể khác nhau.

**5. Tại sao cần multipart/related?**

Vì HTML và ảnh inline là các part liên quan để tạo một nội dung hoàn chỉnh. Multipart/related mô tả mối quan hệ đó cho MIME client.

**6. Khi nào cần multipart/mixed?**

Khi message chứa các phần độc lập, thường là body cùng attachment. Nếu có cả related resources, mixed có thể bao nhánh related.

**7. Có thể dùng cả addInline và addAttachment trong một email không?**

Có. Chọn **MULTIPART_MODE_MIXED_RELATED**, đặt body, thêm inline resource rồi thêm attachment.

**8. Có cần gọi send cho từng file không?**

Không. Thêm tất cả part vào một MimeMessage rồi gọi send một lần.

**9. Inline image có thể xuất hiện trong attachment list không?**

Có thể, tùy email client. Content-Disposition inline là gợi ý trình bày, không ép buộc UI của mọi client.

**10. Ảnh CID có làm tăng kích thước email không?**

Có. Dữ liệu ảnh được đóng gói trong message và thường được mã hóa Base64, làm tăng kích thước vận chuyển.

**11. Có nên nhúng mọi ảnh bằng CID không?**

Không nhất thiết. Với logo hoặc ảnh cần có ngay trong message, CID có thể phù hợp. Với ảnh lớn hoặc nội dung cần cập nhật độc lập, URL HTTPS có thể thích hợp hơn nếu chấp nhận chính sách tải ảnh từ xa.

**12. Có thể đính kèm PDF bằng ByteArrayResource không?**

Có. Bọc byte[] trong ByteArrayResource rồi truyền vào addAttachment cùng filename và MIME type.

**13. SimpleMailMessage có hỗ trợ attachment hoặc inline không?**

Không. Cần MimeMessage và MimeMessageHelper.

**14. Gửi thành công có bảo đảm người nhận đã tải file hoặc thấy ảnh không?**

Không. SMTP accept, delivery, hiển thị và hành động của người nhận là các mốc khác nhau.

## 20. Ghi nhớ khi phân biệt attachment với inline resource

**Attachment** là tệp độc lập được thêm bằng **MimeMessageHelper.addAttachment(...)**, thường có filename và **Content-Disposition: attachment**. **Inline resource** là tài nguyên được phần nội dung tham chiếu, thường thêm bằng **addInline(...)**, có **Content-ID** và được HTML tìm qua URL **cid:**.

Về cấu trúc MIME, **multipart/mixed** thường chứa các phần độc lập như body và PDF; **multipart/related** nhóm HTML với ảnh mà HTML tham chiếu. Khi một email vừa có ảnh inline vừa có tài liệu tải riêng, **MULTIPART_MODE_MIXED_RELATED** giúp tổ chức hai mục đích trong cùng message.

Hãy chọn API theo cách người nhận cần sử dụng dữ liệu: dùng addAttachment cho file để tải, addInline cho tài nguyên được HTML tham chiếu; đặt body trước khi thêm inline resource, dùng MIME type đúng và kiểm soát filename, kích thước, nguồn file cùng quyền nhận. Email client vẫn có thể trình bày khác nhau, vì vậy thông tin quan trọng cần tồn tại ở dạng văn bản và cấu trúc message nên được kiểm tra trong môi trường thử nghiệm.
