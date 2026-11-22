# Khi dùng helper và khi tạo Multipart trực tiếp

Trong **Spring Framework Mail**, có hai cách chính để tạo nội dung email MIME nhiều phần: dùng tiện ích `MimeMessageHelper` của Spring hoặc tự dựng các nhóm `MimeMultipart` và `MimeBodyPart` bằng Jakarta Mail. Cả hai cách đều tạo ra một `MimeMessage` có thể gửi qua `JavaMailSender`, nhưng mức độ kiểm soát và trách nhiệm của lập trình viên khác nhau.

`MimeMessageHelper` phù hợp với các email thường gặp: một body text/HTML, hai phiên bản plain text và HTML, ảnh inline, tệp đính kèm hoặc kết hợp những thành phần đó. Khi yêu cầu cần kiểm soát chính xác cây MIME, subtype, thứ tự, tham số, header của từng part hoặc kiểu đóng gói đặc biệt, có thể tạo multipart trực tiếp bằng Jakarta Mail.

Điểm quan trọng là chọn API dựa trên **cấu trúc MIME mà email thực sự cần**. Dùng API cấp thấp cho một email đơn giản làm code dài và tăng trách nhiệm xử lý. Ngược lại, cố ép một cấu trúc đặc biệt vào helper có thể khiến cây MIME không khớp hợp đồng của bên nhận.

Bài học này giải thích hai cách tiếp cận, cách chọn theo nhu cầu, ví dụ Java hoàn chỉnh, cách kết hợp với Spring sender, kiểm tra MIME source và những lỗi cần tránh.

## 1. MIME message gồm những thành phần nào?

Một email MIME không nhất thiết chỉ có một body. Nó có thể chứa nhiều part và các nhóm multipart lồng nhau.

Email văn bản đơn giản:

```text
MimeMessage
└── text/plain; charset=UTF-8
```

Email có hai dạng nội dung thay thế:

```text
MimeMessage
└── multipart/alternative
    ├── text/plain; charset=UTF-8
    └── text/html; charset=UTF-8
```

Email HTML có ảnh inline và file đính kèm:

```text
MimeMessage
└── multipart/mixed
    ├── multipart/related
    │   ├── text/html
    │   └── image/png; Content-ID: <brand-logo>
    └── application/pdf; attachment
```

Các loại multipart biểu đạt quan hệ khác nhau:

| Content-Type | Ý nghĩa | Ví dụ |
|---|---|---|
| `multipart/alternative` | Các phiên bản thay thế của cùng nội dung; client chọn dạng phù hợp. | Plain text và HTML. |
| `multipart/related` | Nội dung gốc và các tài nguyên cần để hiển thị nội dung đó. | HTML và ảnh CID. |
| `multipart/mixed` | Các phần cùng tồn tại độc lập. | Body email và PDF attachment. |
| `multipart/report` | Báo cáo có cấu trúc theo quy ước MIME. | Delivery Status Notification. |
| `multipart/signed` | Nội dung đi kèm chữ ký theo chuẩn MIME ký số. | S/MIME signed message. |

Các nhóm có thể được lồng nhau. Ví dụ, một email có plain text, HTML, ảnh inline và PDF có thể dùng mixed bên ngoài, related để nhóm HTML/ảnh và alternative để nhóm các phiên bản nội dung. Cây cụ thể cần phản ánh đúng ý nghĩa của từng part.

## 2. MimeMessageHelper là gì?

`MimeMessageHelper` là lớp tiện ích của Spring trong package:

```java
org.springframework.mail.javamail.MimeMessageHelper
```

Nó bọc một `jakarta.mail.internet.MimeMessage` và cung cấp API mức cao để thiết lập các trường email và các thành phần MIME phổ biến.

Các thao tác thường dùng:

| API | Mục đích |
|---|---|
| `setFrom(...)` | Địa chỉ và tên hiển thị người gửi. |
| `setTo(...)`, `setCc(...)`, `setBcc(...)` | Người nhận chính và người nhận bản sao. |
| `setReplyTo(...)` | Địa chỉ nhận thư trả lời. |
| `setSubject(...)` | Tiêu đề email. |
| `setText(text)` | Body văn bản thuần. |
| `setText(html, true)` | Một body HTML. |
| `setText(plain, html)` | Hai phiên bản plain text và HTML. |
| `addInline(...)` | Thêm tài nguyên inline, thường là ảnh được tham chiếu bằng CID. |
| `addAttachment(...)` | Thêm tệp đính kèm. |

Ví dụ email HTML đơn giản:

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setFrom("notice@example.org");
helper.setTo("user@example.net");
helper.setSubject("Thông báo");
helper.setText("<p>Xin chào!</p>", true);

mailSender.send(message);
```

Helper xử lý nhiều chi tiết MIME thường gặp như charset, tạo part, content type và attachment metadata. Nhờ vậy, service gửi email có thể tập trung vào nội dung nghiệp vụ.

### Multipart mode của helper

Khi cần nhiều part, constructor cho phép chọn multipart mode:

```java
new MimeMessageHelper(message, multipart, encoding);
new MimeMessageHelper(message, multipartMode, encoding);
```

Các mode chính:

| Constant | Cấu trúc được helper thiết lập | Trường hợp thường dùng |
|---|---|---|
| `MULTIPART_MODE_NO` | Không tạo multipart | Một body text hoặc HTML. |
| `MULTIPART_MODE_MIXED` | `multipart/mixed` | Body và attachment. |
| `MULTIPART_MODE_RELATED` | `multipart/related` | Body và inline resource. |
| `MULTIPART_MODE_MIXED_RELATED` | `multipart/mixed` ngoài, `multipart/related` bên trong | Inline resource cùng attachment độc lập. |

Ví dụ chỉ có ảnh inline:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_RELATED,
        "UTF-8"
);
```

Ví dụ có ảnh inline và PDF:

```java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
```

Tên mode diễn tả hình dạng multipart ở cấp helper. Khi một hệ thống yêu cầu cây MIME cụ thể hơn, hãy serialize message và xác nhận cấu trúc thực tế thay vì suy luận chỉ từ tên constant.

## 3. Khi nào nên dùng MimeMessageHelper?

Chọn helper khi email nằm trong những tình huống Spring đã hỗ trợ trực tiếp.

### 3.1. Email chỉ có text hoặc HTML

Nếu chỉ có một body, helper làm cho code ngắn và rõ:

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setFrom("support@example.org");
helper.setTo(recipient);
helper.setSubject("Yêu cầu đã được tiếp nhận");
helper.setText(
        "<html><body><h1>Chúng tôi đã nhận yêu cầu.</h1></body></html>",
        true
);

mailSender.send(message);
```

Không cần tự tạo `MimeMultipart` vì message chỉ có một phần nội dung.

### 3.2. Plain text và HTML là hai phiên bản thay thế

Nếu muốn mail client chọn một trong hai dạng, dùng overload hai chuỗi:

```java
helper.setText(
        "Đơn hàng ORD-001 đã được xác nhận.",
        "<p>Đơn hàng <strong>ORD-001</strong> đã được xác nhận.</p>"
);
```

Helper xây dựng nội dung alternative phù hợp. Bản plain text vẫn cần truyền đạt đầy đủ thông tin và thao tác quan trọng nếu người nhận không hiển thị HTML.

### 3.3. HTML có ảnh inline

Dùng `addInline(...)` với Content-ID khớp CID URL trong HTML:

```java
String logoCid = "brand-logo";

helper.setText(
        "<html><body>"
                + "<h1>Xin chào!</h1>"
                + "<img src=\"cid:" + logoCid + "\" alt=\"Logo\">"
                + "</body></html>",
        true
);

helper.addInline(
        logoCid,
        new ClassPathResource("mail/brand-logo.png"),
        "image/png"
);
```

Nên gọi `setText(...)` trước `addInline(...)`. Tài liệu Spring lưu ý thứ tự này để tăng khả năng một số mail client nhận dạng đúng inline resource.

### 3.4. Có attachment thông thường

`addAttachment(...)` đủ dùng khi chỉ cần thêm file:

```java
helper.setText("Báo cáo được gửi kèm trong email này.");

helper.addAttachment(
        "report.pdf",
        new ClassPathResource("mail/report.pdf"),
        "application/pdf"
);
```

Nếu email còn có ảnh inline, có thể chọn `MULTIPART_MODE_MIXED_RELATED` để helper tổ chức related và mixed theo cấu trúc mà mode hỗ trợ.

### 3.5. Các header và charset thông thường

Helper cũng phù hợp khi chỉ cần thiết lập From, Reply-To, To/Cc/Bcc, subject, tên hiển thị và charset. Những thao tác này không cần quản lý trực tiếp từng `MimeBodyPart`.

**Quy tắc thực tế:** nếu các API helper mô tả được email bạn muốn gửi, hãy dùng helper. Nó giảm số lượng chi tiết MIME phải tự quản lý và giúp code nghiệp vụ dễ đọc.

## 4. Ví dụ đầy đủ với MimeMessageHelper

Giả sử email xác nhận đơn hàng cần:

- Plain text làm nội dung dự phòng.
- HTML để trình bày đẹp hơn.
- Logo inline được tham chiếu qua CID.
- PDF đính kèm để người nhận tải về.

Một service:

```java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import org.springframework.core.io.ClassPathResource;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;

    public OrderMailService(JavaMailSender mailSender) {
        this.mailSender = mailSender;
    }

    public void sendConfirmation(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        String logoCid = "order-brand-logo";

        helper.setFrom("orders@example.org", "Example Store");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng ORD-001");

        String plainText = """
                Đơn hàng ORD-001 đã được xác nhận.
                Xem báo cáo trong file report.pdf đính kèm.
                """;

        String htmlText = """
                <html>
                  <body>
                    <img src="cid:order-brand-logo"
                         alt="Example Store"
                         width="140">
                    <h1>Đơn hàng đã được xác nhận</h1>
                    <p>Mã đơn hàng: <strong>ORD-001</strong></p>
                    <p>Vui lòng xem báo cáo đính kèm.</p>
                  </body>
                </html>
                """;

        helper.setText(plainText, htmlText);

        helper.addInline(
                logoCid,
                new ClassPathResource("mail/brand-logo.png"),
                "image/png"
        );

        helper.addAttachment(
                "report.pdf",
                new ClassPathResource("mail/report.pdf"),
                "application/pdf"
        );

        mailSender.send(message);
    }
}
```

Đoạn code minh họa những thao tác phổ biến mà helper hỗ trợ trực tiếp. Tên file trong classpath phải tồn tại trong artifact chạy ứng dụng. Trong hệ thống thực tế, CID có thể được sinh duy nhất cho từng message, còn mã đơn hàng và nội dung được truyền từ nghiệp vụ thay vì hard-code.

### Vì sao ví dụ này phù hợp với helper?

Không có yêu cầu đặc biệt về thứ tự part, subtype riêng, tham số MIME tùy biến hoặc một cây lồng nhau bắt buộc. Email chỉ cần plain/HTML, ảnh CID và PDF. Helper đã cung cấp API trực tiếp cho các thành phần đó.

Khi cần hợp đồng MIME nghiêm ngặt với một hệ thống khác, cần xác nhận cây do helper tạo bằng raw source hoặc parser. Nếu cấu trúc thực tế không đúng hợp đồng, có thể chuyển sang tạo multipart trực tiếp.

## 5. Khi nào nên tạo Multipart trực tiếp?

Dùng Jakarta Mail trực tiếp khi bạn cần kiểm soát chi tiết mà helper không biểu diễn thuận tiện.

Các tình huống thường gặp:

### 5.1. Cần cây MIME lồng nhau chính xác

Ví dụ bên nhận yêu cầu:

```text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── multipart/related
│       ├── text/html
│       └── image/png; Content-ID: <logo>
└── application/pdf; attachment
```

Trong cây này, nhánh HTML và ảnh related là một phiên bản alternative của plain text. Nhánh related nằm bên trong alternative. Nếu helper tạo ra hình dạng lồng nhau khác với hợp đồng, Jakarta Mail cho phép bạn tự tạo đúng parent-child relationship.

### 5.2. Cần subtype multipart đặc biệt

Ví dụ:

- `multipart/report` cho delivery status notification.
- `multipart/signed` cho một cấu trúc MIME có chữ ký.
- `multipart/alternative` ở root theo yêu cầu tích hợp.
- Một subtype multipart đặc thù của hệ thống nhận.

Helper có các mode được định nghĩa trước, không phải API tổng quát để truyền mọi subtype hoặc mọi tham số multipart.

### 5.3. Cần điều khiển header của từng part

Bạn có thể cần tự đặt:

- `Content-Type` với tham số như `method=REQUEST` cho calendar part.
- `Content-ID` hoặc `Content-Location`.
- `Content-Disposition` là inline hoặc attachment.
- Filename, charset và transfer encoding.
- Tham số `start` hoặc `type` của `multipart/related`.
- Các header tùy chỉnh được quy định trong hợp đồng tích hợp.

Jakarta Mail cho phép thao tác trực tiếp trên từng `MimeBodyPart` và `MimeMultipart`. Tuy nhiên, header phải phù hợp với chuẩn MIME và ý nghĩa thực tế của part.

### 5.4. Cần part không được helper hỗ trợ trực tiếp

Một email có thể chứa `text/calendar`, `message/rfc822` hoặc nội dung được ký/mã hóa. Đây không chỉ là attachment bình thường. Cần đặt đúng content type, disposition và vị trí trong cây MIME.

### 5.5. Cần xử lý message MIME đã có

Nếu ứng dụng nhận một email MIME rồi cần bao bọc, chuyển tiếp hoặc tạo message mới dựa trên một phần của nó, API Jakarta Mail cung cấp khả năng duyệt và lắp các part chi tiết hơn. Cần đặc biệt cẩn thận khi giữ nguyên nội dung đã ký hoặc các header phục vụ threading.

## 6. Các lớp Jakarta Mail cần biết

Khi tạo multipart trực tiếp, những lớp chính là:

| Lớp | Trách nhiệm |
|---|---|
| `MimeMessage` | Email hoàn chỉnh: header và content root. |
| `MimeMultipart` | Một nhóm nhiều part với subtype như mixed, related, alternative. |
| `MimeBodyPart` | Một part có header và nội dung riêng; có thể chứa text, binary hoặc multipart con. |
| `DataHandler` | Cung cấp dữ liệu cho body part thông qua DataSource. |
| `DataSource` | Nguồn byte và content type của part. |
| `ByteArrayDataSource` | DataSource tiện dụng cho dữ liệu byte đã có trong bộ nhớ. |
| `Part` | API/constant về disposition, ví dụ INLINE và ATTACHMENT. |
| `InternetAddress` | Biểu diễn địa chỉ email Internet. |

Với Spring Boot sử dụng Spring Framework 6, các package mail là namespace `jakarta.mail`. Dự án Spring cũ có thể sử dụng `javax.mail`; không trộn hai namespace trong cùng ứng dụng. Dependency và phiên bản Jakarta Mail/Activation phải tương thích với Spring version đang dùng.

## 7. Cách tạo Multipart trực tiếp

Quy trình tổng quát:

1. Tạo `MimeMessage` qua `JavaMailSender.createMimeMessage()` để dùng session mail đã cấu hình.
2. Đặt From, To, Subject và các header cần thiết.
3. Tạo từng `MimeBodyPart` lá.
4. Đặt content type, charset, Content-ID và disposition cho từng part.
5. Tạo các nhóm `MimeMultipart` theo subtype.
6. Lồng các nhóm bằng cách đặt multipart vào một body part.
7. Gắn multipart root vào message bằng `message.setContent(...)`.
8. Gửi message bằng `JavaMailSender.send(...)`.

Điều quan trọng là xây cây từ những part lá lên root. Mỗi nhóm multipart cần có lý do ngữ nghĩa rõ ràng.

### 7.1. Tạo email chỉ có plain text và HTML

Nếu muốn root là `multipart/alternative`:

```java
MimeMessage message = mailSender.createMimeMessage();

message.setFrom(new InternetAddress("notice@example.org"));
message.setRecipients(
        Message.RecipientType.TO,
        InternetAddress.parse(recipient, true)
);
message.setSubject("Thông báo", "UTF-8");

MimeBodyPart plainPart = new MimeBodyPart();
plainPart.setText(
        "Yêu cầu của bạn đã được tiếp nhận.",
        "UTF-8"
);

MimeBodyPart htmlPart = new MimeBodyPart();
htmlPart.setContent(
        "<html><body><h1>Yêu cầu đã được tiếp nhận.</h1></body></html>",
        "text/html; charset=UTF-8"
);

MimeMultipart alternative = new MimeMultipart("alternative");
alternative.addBodyPart(plainPart);
alternative.addBodyPart(htmlPart);

message.setContent(alternative);

mailSender.send(message);
```

Trong `multipart/alternative`, thứ tự thường đặt dạng đơn giản hơn trước rồi đến dạng phong phú hơn. Ở ví dụ này, plain text đứng trước HTML.

### 7.2. Tạo cây mixed → alternative → related

Giả sử email cần:

- Plain text.
- HTML với logo inline.
- PDF attachment.

Cây mục tiêu:

```text
multipart/mixed
├── multipart/alternative
│   ├── text/plain
│   └── multipart/related
│       ├── text/html
│       └── image/png; Content-ID: <brand-logo>
└── application/pdf; attachment
```

Code minh họa:

```java
import jakarta.activation.DataHandler;
import jakarta.mail.Message;
import jakarta.mail.MessagingException;
import jakarta.mail.Part;
import jakarta.mail.internet.InternetAddress;
import jakarta.mail.internet.MimeBodyPart;
import jakarta.mail.internet.MimeMessage;
import jakarta.mail.internet.MimeMultipart;
import jakarta.mail.util.ByteArrayDataSource;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

public void sendCustomReport(String recipient)
        throws MessagingException, IOException {

    MimeMessage message = mailSender.createMimeMessage();

    message.setFrom(new InternetAddress("reports@example.org"));
    message.setRecipients(
            Message.RecipientType.TO,
            InternetAddress.parse(recipient, true)
    );
    message.setSubject("Báo cáo tháng", StandardCharsets.UTF_8.name());

    // 1. Plain text là lựa chọn nội dung đơn giản.
    MimeBodyPart plainPart = new MimeBodyPart();
    plainPart.setText(
            "Báo cáo tháng đã sẵn sàng. Xem PDF đính kèm.",
            StandardCharsets.UTF_8.name()
    );

    // 2. HTML là root của nhánh related.
    String cid = "brand-logo";

    MimeBodyPart htmlPart = new MimeBodyPart();
    htmlPart.setContent(
            "<html><body>"
                    + "<h1>Báo cáo tháng</h1>"
                    + "<img src=\"cid:" + cid + "\" alt=\"Logo\">"
                    + "<p>Xem file PDF đính kèm.</p>"
                    + "</body></html>",
            "text/html; charset=UTF-8"
    );

    // 3. Ảnh được tham chiếu bằng CID từ HTML.
    byte[] logoBytes = loadLogoBytes();

    MimeBodyPart logoPart = new MimeBodyPart();
    logoPart.setDataHandler(new DataHandler(
            new ByteArrayDataSource(logoBytes, "image/png")
    ));
    logoPart.setHeader("Content-ID", "<" + cid + ">");
    logoPart.setDisposition(Part.INLINE);

    MimeMultipart related = new MimeMultipart("related");
    related.addBodyPart(htmlPart);
    related.addBodyPart(logoPart);

    // 4. Đưa toàn bộ HTML + ảnh thành một alternative body part.
    MimeBodyPart htmlAlternativePart = new MimeBodyPart();
    htmlAlternativePart.setContent(related);

    MimeMultipart alternative = new MimeMultipart("alternative");
    alternative.addBodyPart(plainPart);
    alternative.addBodyPart(htmlAlternativePart);

    MimeBodyPart mainBodyPart = new MimeBodyPart();
    mainBodyPart.setContent(alternative);

    // 5. PDF là attachment độc lập.
    byte[] pdfBytes = loadReportBytes();

    MimeBodyPart pdfPart = new MimeBodyPart();
    pdfPart.setDataHandler(new DataHandler(
            new ByteArrayDataSource(pdfBytes, "application/pdf")
    ));
    pdfPart.setFileName("monthly-report.pdf");
    pdfPart.setDisposition(Part.ATTACHMENT);

    // 6. Root mixed nhóm body và attachment.
    MimeMultipart mixed = new MimeMultipart("mixed");
    mixed.addBodyPart(mainBodyPart);
    mixed.addBodyPart(pdfPart);

    message.setContent(mixed);

    mailSender.send(message);
}
```

`loadLogoBytes()` và `loadReportBytes()` là các hàm minh họa đọc dữ liệu ảnh/PDF từ nguồn được ứng dụng quản lý. Chúng phải trả về byte hợp lệ và có thể được đọc hoàn chỉnh trước khi gửi.

Cây MIME được kiểm soát rõ ràng:

- `mixed` ở root chứa body chính và PDF.
- `alternative` cho phép client chọn plain hoặc phiên bản HTML.
- `related` nhóm HTML và ảnh mà HTML tham chiếu.
- `Content-ID` của ảnh khớp với CID URL trong HTML.

Đây là một ví dụ cho thấy lý do chọn API trực tiếp: ứng dụng muốn quy định chính xác nhánh related là một phần tử của alternative.

## 8. Tạo attachment và inline part trực tiếp

Với API cấp thấp, bạn chịu trách nhiệm thiết lập header của từng part.

### Attachment từ byte array

```java
MimeBodyPart attachment = new MimeBodyPart();

attachment.setDataHandler(new DataHandler(
        new ByteArrayDataSource(pdfBytes, "application/pdf")
));

attachment.setFileName("invoice.pdf");
attachment.setDisposition(Part.ATTACHMENT);
```

### Inline image từ byte array

```java
MimeBodyPart image = new MimeBodyPart();

image.setDataHandler(new DataHandler(
        new ByteArrayDataSource(imageBytes, "image/png")
));

image.setHeader("Content-ID", "<invoice-logo>");
image.setDisposition(Part.INLINE);
```

### Text part có charset rõ ràng

```java
MimeBodyPart plain = new MimeBodyPart();
plain.setText(plainText, "UTF-8");

MimeBodyPart html = new MimeBodyPart();
html.setContent(htmlText, "text/html; charset=UTF-8");
```

Dữ liệu binary như PDF hoặc PNG không được chuyển thành chuỗi UTF-8. Hãy giữ nguyên byte và để DataHandler/DataSource cung cấp đúng content type cho MIME part.

### Chọn DataSource theo nguồn dữ liệu

- `ByteArrayDataSource`: dữ liệu đã có trong byte array.
- `FileDataSource`: dữ liệu lấy từ file.
- DataSource tùy chỉnh: dữ liệu từ storage hoặc hệ thống khác.

Với nguồn stream, bảo đảm có thể mở lại stream nếu thư viện cần đọc nội dung nhiều lần. Không đóng stream trước khi quá trình serialize message hoàn tất.

## 9. So sánh helper và multipart trực tiếp

| Tiêu chí | MimeMessageHelper | Jakarta Mail trực tiếp |
|---|---|---|
| Mức trừu tượng | Cao hơn, API theo nhu cầu email phổ biến. | Thấp hơn, thao tác trực tiếp trên part và multipart. |
| Code tạo message | Ngắn và dễ đọc. | Dài hơn, cần tạo từng part. |
| Plain + HTML | Có `setText(plain, html)`. | Tự tạo `multipart/alternative`. |
| Inline resource | Có `addInline(...)`. | Tự tạo body part, DataHandler, Content-ID và related. |
| Attachment | Có `addAttachment(...)`. | Tự tạo part, DataSource, filename và disposition. |
| Multipart mode | Các mode có sẵn. | Tự chọn subtype và cây lồng nhau. |
| Header từng part | Phần lớn được helper quản lý. | Kiểm soát trực tiếp. |
| Cấu trúc MIME đặc biệt | Có giới hạn theo thiết kế helper. | Linh hoạt hơn. |
| Khối lượng code | Ít. | Nhiều. |
| Rủi ro cấu hình sai | Thấp hơn cho trường hợp phổ biến. | Cao hơn vì phải tự quản lý metadata và quan hệ. |
| Khả năng đáp ứng hợp đồng MIME tùy biến | Phụ thuộc mode/API helper. | Phù hợp khi cần cấu trúc chính xác. |
| Bảo trì | Dễ hơn nếu nhu cầu chuẩn. | Cần kiến thức MIME và kiểm thử kỹ hơn. |

### Ma trận lựa chọn

| Nhu cầu | Cách nên bắt đầu |
|---|---|
| Chỉ text hoặc HTML | Helper |
| Plain text + HTML | Helper |
| HTML + một vài ảnh CID | Helper |
| Body + PDF/CSV attachment | Helper |
| HTML + CID + attachment thông thường | Helper với mode phù hợp |
| Root phải là subtype multipart cụ thể | Multipart trực tiếp |
| Cây related/alternative lồng theo hợp đồng riêng | Multipart trực tiếp |
| Calendar part có tham số MIME đặc biệt | Multipart trực tiếp hoặc thư viện chuyên dụng |
| `message/rfc822` hoặc MIME part đặc biệt | Multipart trực tiếp |
| `multipart/signed` hoặc S/MIME | Thư viện S/MIME chuyên dụng và Jakarta Mail |
| Cần giữ nguyên MIME message đã nhận | Jakarta Mail, với quy trình bảo toàn nội dung rõ ràng |

## 10. Có thể kết hợp MimeMessageHelper với Multipart trực tiếp không?

Về kỹ thuật, `MimeMessageHelper` thao tác trên `MimeMessage` của Jakarta Mail. Bạn có thể dùng helper để đặt một số header quen thuộc rồi gắn một cây MIME được tạo thủ công.

Ví dụ:

```java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");

helper.setFrom("reports@example.org");
helper.setTo(recipient);
helper.setSubject("Báo cáo");

MimeMultipart customRoot = buildCustomMultipart();
message.setContent(customRoot);

mailSender.send(message);
```

Cách này có thể hữu ích nếu muốn dùng helper cho From/To/Subject nhưng vẫn tự tạo body. Tuy nhiên, cần hiểu một giới hạn quan trọng: helper có thể giữ tham chiếu tới multipart mà nó khởi tạo. Nếu sau đó thay root content bằng một cây khác, những lời gọi body API tiếp theo trên helper có thể thao tác vào cây cũ.

Tránh mẫu sau:

```java
MimeMessageHelper helper = new MimeMessageHelper(message, true);

helper.setText("Body ban đầu");

// Thay root bằng cây MIME riêng.
message.setContent(customRoot);

// Không nên tiếp tục coi helper đang quản lý customRoot.
helper.addAttachment("report.pdf", resource);
```

Sau khi đã thay root, không nên gọi lại `setText`, `addInline` hoặc `addAttachment` trên helper để tiếp tục xây body. Nếu cấu trúc đã được chuyển sang Jakarta Mail trực tiếp, hãy để code trực tiếp sở hữu toàn bộ body MIME của message đó.

**Khuyến nghị:** chọn một cơ chế chịu trách nhiệm xây body cho mỗi message. Có thể dùng helper để đặt header trước khi gắn custom root, nhưng không chia việc chỉnh sửa body giữa hai cơ chế.

## 11. Đặt header, charset và encoding khi tạo multipart trực tiếp

Khi dùng helper, nhiều chi tiết này được xử lý qua constructor và API. Khi tạo trực tiếp, hãy chú ý:

### Subject

Dùng overload có charset:

```java
message.setSubject(subject, "UTF-8");
```

Điều này giúp subject chứa ký tự Unicode được mã hóa đúng theo Jakarta Mail.

### Text body

Dùng charset rõ ràng:

```java
plainPart.setText(plainText, "UTF-8");
```

### HTML body

Đặt content type có charset:

```java
htmlPart.setContent(html, "text/html; charset=UTF-8");
```

### Binary part

Khai báo đúng MIME type:

```java
new ByteArrayDataSource(pdfBytes, "application/pdf")
new ByteArrayDataSource(pngBytes, "image/png")
```

Không dùng UTF-8 để chuyển đổi byte của PDF hoặc ảnh thành text. Thư viện mail sẽ serialize binary part theo transfer encoding thích hợp.

### Boundary

Không tự ghép boundary vào chuỗi MIME. `MimeMultipart` tự quản lý boundary khi serialize. Tự tạo raw MIME bằng string dễ dẫn đến lỗi xuống dòng, boundary kết thúc, nested multipart và encoding.

## 12. Kiểm tra cây MIME đã tạo

Khi dùng helper hay API trực tiếp, đừng chỉ nhìn code rồi đoán message sẽ có hình dạng nào. Hãy xem raw MIME hoặc parse cây part.

Có thể serialize message ra output stream trong môi trường test:

```java
ByteArrayOutputStream output = new ByteArrayOutputStream();

message.saveChanges();
message.writeTo(output);

String raw = output.toString(StandardCharsets.UTF_8);
```

`saveChanges()` giúp hoàn thiện header trước khi quan sát source. Trong luồng gửi Spring bình thường, sender/transport sẽ xử lý các bước hoàn thiện cần thiết; không phải mọi service đều cần gọi thủ công trước `send`.

Khi kiểm tra raw source, tìm:

- `MIME-Version`.
- `Content-Type` ở root và các nested multipart.
- `boundary` của từng nhóm.
- Thứ tự part trong alternative.
- HTML và ảnh có nằm trong related như mong đợi.
- `Content-ID` có khớp CID URL.
- Attachment có `Content-Disposition: attachment` và filename phù hợp.
- Charset và transfer encoding.

Không log toàn bộ raw email trong production vì có thể chứa địa chỉ, thông tin cá nhân, token và file đính kèm.

### Duyệt cây part bằng Jakarta Mail

Một tiện ích đơn giản:

```java
import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.MessagingException;
import java.io.IOException;

public final class MimeTreeInspector {

    private MimeTreeInspector() {}

    public static void print(Part part, String indent)
            throws MessagingException, IOException {

        System.out.println(
                indent + "Content-Type: " + part.getContentType()
        );
        System.out.println(
                indent + "Disposition: " + part.getDisposition()
        );
        System.out.println(
                indent + "Filename: " + part.getFileName()
        );

        String[] contentIds = part.getHeader("Content-ID");
        if (contentIds != null) {
            for (String contentId : contentIds) {
                System.out.println(indent + "Content-ID: " + contentId);
            }
        }

        Object content = part.getContent();

        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                print(child, indent + "  ");
            }
        }
    }
}
```

Gọi:

```java
MimeTreeInspector.print(message, "");
```

Với cây custom ở ví dụ trên, output khái niệm:

```text
multipart/mixed
  multipart/alternative
    text/plain; charset=UTF-8
    multipart/related
      text/html; charset=UTF-8
      image/png; Content-ID: <brand-logo>; inline
  application/pdf; attachment; filename=monthly-report.pdf
```

Đây là cách xác nhận cấu trúc thực tế thay vì dựa vào suy đoán từ code. `getContent()` có thể đọc dữ liệu part và phát sinh lỗi I/O; chỉ dùng tiện ích này trong kiểm tra có kiểm soát.

## 13. Kiểm thử khi dùng helper và khi dùng multipart trực tiếp

Hai cách tiếp cận cần được kiểm thử theo mục tiêu giống nhau: message có nội dung đúng và cây MIME đúng.

### Unit test cho helper

Có thể tạo message mà không kết nối SMTP:

1. Tạo `MimeMessage` qua sender.
2. Dùng `MimeMessageHelper` xây body.
3. Serialize hoặc duyệt cây MIME.
4. Kiểm tra text, HTML, CID, attachment và header.

Ví dụ kiểm tra các dấu hiệu cơ bản:

```java
@Test
void helperBuildsHtmlMailWithInlineLogo() throws Exception {
    MimeMessage message = mailSender.createMimeMessage();

    MimeMessageHelper helper = new MimeMessageHelper(
            message,
            MimeMessageHelper.MULTIPART_MODE_RELATED,
            "UTF-8"
    );

    helper.setTo("user@example.net");
    helper.setSubject("CID test");
    helper.setText(
            "<html><body><img src=\"cid:logo-test\"></body></html>",
            true
    );
    helper.addInline(
            "logo-test",
            new ClassPathResource("mail/logo.png"),
            "image/png"
    );

    message.saveChanges();

    ByteArrayOutputStream output = new ByteArrayOutputStream();
    message.writeTo(output);
    String raw = output.toString(StandardCharsets.UTF_8);

    assertThat(raw).contains("multipart/related");
    assertThat(raw).contains("cid:logo-test");
    assertThat(raw).contains("Content-ID: <logo-test>");
}
```

Trong test thực tế, nên parse MIME để kiểm tra header và cây part thay vì chỉ tìm substring, vì header có thể được gấp dòng và cách serialize có thể thay đổi.

### Unit test cho multipart trực tiếp

Với custom builder, kiểm tra:

- Root có đúng subtype.
- Số lượng child part đúng.
- Thứ tự alternative đúng.
- HTML part và image part ở cùng related subtree.
- CID và Content-ID khớp.
- PDF nằm ở nhánh mixed ngoài cùng.
- Charset và disposition đúng.

Việc kiểm tra cấu trúc quan trọng hơn chỉ xác nhận `message.setContent(...)` đã được gọi.

### Integration test với SMTP server giả lập

Có thể dùng Mailpit hoặc GreenMail để xác nhận sender đã chuyển message đến SMTP test server. Sau khi nhận message, parse lại rồi kiểm tra MIME tree. Đây là cách kiểm tra thêm đường đi qua transport.

SMTP test server không đảm bảo mọi Gmail, Outlook hoặc Apple Mail sẽ render giống nhau. Với email quan trọng, cần kiểm tra trên mail client mục tiêu.

## 14. Những lỗi thường gặp khi tự tạo Multipart

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Quên gắn multipart root vào message | Message không chứa body mong muốn | Gọi `message.setContent(rootMultipart)`. |
| Đặt sai subtype | Client hiểu sai quan hệ giữa các part | Chọn mixed, related, alternative theo ý nghĩa nội dung. |
| Đảo thứ tự alternative | Client có thể chọn nội dung không mong muốn | Đặt plain text trước, HTML sau. |
| Ảnh CID không nằm trong related với HTML | Client không phân giải inline resource như dự kiến | Lồng HTML và ảnh trong cùng related subtree. |
| CID và Content-ID khác nhau | Ảnh không hiện | Sinh ID một lần và dùng ở cả hai vị trí. |
| Quên disposition/filename của attachment | Client phân loại file không đúng | Đặt `Part.ATTACHMENT` và filename. |
| Dùng charset cho dữ liệu binary | File bị hỏng | Giữ byte và dùng DataSource với MIME type đúng. |
| Tự tạo boundary bằng chuỗi | MIME malformed | Để `MimeMultipart` sinh và quản lý boundary. |
| Nguồn stream chỉ đọc được một lần | Lỗi khi serialize/gửi | Dùng nguồn có thể mở stream mới hoặc byte array. |
| Thay root rồi tiếp tục gọi helper body API | Thao tác có thể đi vào multipart cũ | Chọn một cơ chế sở hữu body. |
| Không kiểm tra MIME source | Khó xác định lỗi nằm ở đâu | Serialize/parse và kiểm tra cây part. |
| Coi SMTP accepted là client render đúng | Lỗi hiển thị bị bỏ sót | Kiểm tra raw MIME và client thực tế. |

## 15. Những loại email nên dùng thư viện chuyên biệt

Một số MIME subtype liên quan tới giao thức hoặc bảo mật. Tự tạo một `MimeMultipart` có subtype phù hợp chưa chắc đã tạo được thông điệp hợp lệ.

### Calendar invitation

`text/calendar` có thể chứa dữ liệu iCalendar với `METHOD` như REQUEST hoặc CANCEL. Để lời mời họp hoạt động, cần tạo dữ liệu VCALENDAR/VEVENT đúng schema và các thuộc tính như UID, DTSTART, DTEND, ORGANIZER, ATTENDEE. Có thể dùng Jakarta Mail để đặt part, nhưng nên dùng thư viện iCalendar chuyên dụng để tạo nội dung lịch.

### S/MIME signed/encrypted

`multipart/signed` và các dạng S/MIME khác cần chữ ký/mã hóa đúng chuẩn. Không thể chỉ thêm file chữ ký vào mixed rồi coi email là signed. Dùng thư viện S/MIME chuyên dụng và tuân thủ quy trình ký/kiểm tra chữ ký.

### Delivery Status Notification

`multipart/report` có các part và tham số dành riêng cho báo cáo trạng thái phân phát. Đây không phải một cách đặt tên khác cho email có nhiều attachment. Nếu cần phát sinh DSN, hãy tuân theo chuẩn và khả năng của mail transport.

Trong những trường hợp này, helper có thể vẫn hữu ích cho nội dung trước khi đưa vào quy trình chuyên biệt, nhưng không thay thế phần triển khai giao thức hoặc mật mã.

## 16. Hiệu năng và quản lý tài nguyên

Helper và Jakarta Mail trực tiếp cuối cùng đều tạo MIME message và serialize nội dung khi gửi. API cấp thấp không tự làm email nhỏ hơn hoặc gửi nhanh hơn.

Một số yếu tố cần xem xét:

- Ảnh/PDF lớn có thể làm tăng heap khi đọc toàn bộ vào byte array.
- MIME transfer encoding như base64 làm dữ liệu truyền tải lớn hơn dữ liệu nhị phân gốc.
- Template HTML quá lớn hoặc quá nhiều inline resource làm tăng thời gian render và serialize.
- DataSource tùy chỉnh cần cung cấp dữ liệu ổn định trong thời gian gửi.
- Mỗi lần gửi nên tạo `MimeMessage` mới, tránh chia sẻ message mutable giữa nhiều request.
- Giới hạn tổng dung lượng và số lượng attachment theo chính sách SMTP provider.

Dùng helper giúp giảm code quản lý MIME; dùng trực tiếp cho phép kiểm soát chi tiết hơn nhưng không thay thế việc quản lý dung lượng và nguồn dữ liệu.

## 17. Tách message builder khỏi nghiệp vụ

Khi ứng dụng có nhiều loại email, không nên để mỗi service tự lắp cây MIME theo một cách khác nhau.

Có thể tổ chức:

```text
Business service
    |
    v
Email content model
    |
    v
Message builder
    ├── CommonMailBuilder (MimeMessageHelper)
    └── SpecialMimeBuilder (Jakarta Mail)
    |
    v
JavaMailSender
    |
    v
SMTP
```

`CommonMailBuilder` tạo các email phổ biến bằng helper. `SpecialMimeBuilder` xử lý những cấu trúc cần kiểm soát trực tiếp. Cả hai trả về `MimeMessage` để lớp gửi dùng chung.

Ví dụ interface:

```java
public interface MailMessageBuilder<T> {

    MimeMessage build(T model) throws MessagingException;
}
```

Một builder cụ thể có thể nhận JavaMailSender và các dependency render/template. Việc tách builder giúp:

- Business service không cần hiểu MIME.
- Quy tắc header và charset nhất quán.
- Cấu trúc đặc biệt được cô lập và kiểm thử.
- Có thể thay đổi cách dựng message mà không thay đổi quy trình nghiệp vụ.
- Dễ truy xuất message type và version của nội dung khi điều tra.

Không cần tạo một framework builder phức tạp cho ứng dụng chỉ có một loại email. Tách lớp khi có nhiều loại message hoặc khi cấu trúc MIME thực sự khác nhau.

## 18. Quyết định theo yêu cầu, không theo thói quen

Trước khi viết code, hãy xác định:

1. Email có bao nhiêu body và chúng thay thế hay cùng tồn tại?
2. Có ảnh/tài nguyên inline được HTML tham chiếu không?
3. Có attachment độc lập không?
4. Bên nhận có yêu cầu root MIME hoặc nested multipart cụ thể không?
5. Có subtype hoặc header đặc biệt không?
6. Có chữ ký, mã hóa, calendar hoặc report format chuyên biệt không?
7. Có cần kiểm soát thứ tự part và root related không?
8. Có thể xác nhận cấu trúc bằng raw MIME test không?

Nếu câu trả lời chỉ xoay quanh text, HTML, inline image và attachment thông thường, helper thường đáp ứng tốt. Nếu có yêu cầu cụ thể về cấu trúc hoặc giao thức, tạo multipart trực tiếp và kiểm thử đúng hợp đồng.

## 19. Ghi nhớ

- **`MimeMessageHelper`** là lựa chọn phù hợp cho email phổ biến: text, HTML, alternative, inline resource và attachment.
- Multipart mode của helper gồm `NO`, `MIXED`, `RELATED` và `MIXED_RELATED`; chúng đáp ứng các cấu trúc thông dụng.
- **Jakarta Mail `MimeMultipart` và `MimeBodyPart`** cho phép tự định nghĩa subtype, thứ tự và quan hệ cha-con của từng part.
- Dùng multipart trực tiếp khi hợp đồng yêu cầu cây MIME chính xác, header/parameter đặc biệt hoặc subtype mà helper không hỗ trợ thuận tiện.
- Khi tạo trực tiếp, bạn phải tự quản lý Content-Type, charset, Content-ID, disposition, filename, DataSource và việc lồng multipart.
- Với ảnh CID, HTML và ảnh cần nằm trong cùng nhánh related; ID trong HTML phải khớp Content-ID.
- Với plain/HTML, dùng alternative và đặt dạng đơn giản trước dạng phong phú hơn.
- Không trộn việc sửa body của helper với việc thay root multipart thủ công; xác định một cơ chế sở hữu body cho mỗi message.
- Dùng `JavaMailSender` để gửi message dù body được tạo bằng helper hay Jakarta Mail trực tiếp.
- Kiểm tra raw MIME và parse cây part; integration test SMTP không thay thế kiểm tra hiển thị trên mail client.
- Calendar, DSN và S/MIME cần tuân thủ giao thức/chữ ký riêng; chỉ đặt subtype MIME không đủ bảo đảm hợp lệ.

Hãy bắt đầu bằng `MimeMessageHelper` cho những email mà API của nó diễn đạt đầy đủ yêu cầu. Khi hệ thống cần một **cây MIME hoặc part đặc biệt có hợp đồng rõ ràng**, dùng `MimeMultipart` và `MimeBodyPart` trực tiếp để kiểm soát cấu trúc, sau đó gửi bằng `JavaMailSender` như bình thường. Sự phân chia này giữ code email thông dụng gọn và giúp các trường hợp đặc biệt được quản lý ở đúng tầng.
