# Kết hợp alternative, related và mixed

Một email có thể cần nhiều cách hiển thị và nhiều loại nội dung cùng lúc: người nhận có thể đọc bản **plain text** hoặc **HTML**, phần HTML có thể tham chiếu logo/ảnh nội tuyến, và email còn có thể mang một hay nhiều tệp đính kèm. Trong Spring Framework Mail, các nhu cầu này được đóng gói bằng MIME multipart.

Ba loại multipart quan trọng nhất là **multipart/alternative**, **multipart/related** và **multipart/mixed**. Mỗi loại biểu diễn một quan hệ khác nhau giữa các phần của email:

- **alternative**: các phiên bản nội dung thay thế nhau, ví dụ plain text và HTML.
- **related**: một nội dung chính cùng những tài nguyên mà nội dung đó tham chiếu, ví dụ HTML và ảnh qua CID.
- **mixed**: một nội dung chính cùng các phần độc lập như file PDF hoặc bảng tính đính kèm.

Khi email cần cả ba khả năng, điều quan trọng là **lồng các multipart theo đúng ý nghĩa**. Chỉ có đủ part text/plain, text/html, image/png và application/pdf vẫn chưa chứng minh message đúng; mỗi part phải nằm trong nhóm thích hợp để email client hiểu mối quan hệ của chúng.

Bài học này giải thích cách phối hợp ba loại multipart, cách tạo email bằng **MimeMessageHelper**, cách kiểm tra MIME tree sau khi tạo và các vấn đề thường gặp khi email client hiển thị ảnh hoặc attachment.

## 1. Ba loại multipart biểu diễn ba quan hệ khác nhau

### multipart/alternative: cùng nội dung, nhiều cách trình bày

Một email có thể cung cấp hai phiên bản của cùng thông điệp:

~~~text
multipart/alternative
    +-- text/plain
    |     "Đơn hàng ORD-1528 đã được xác nhận."
    |
    '-- text/html
          <p>Đơn hàng <strong>ORD-1528</strong>
          đã được xác nhận.</p>
~~~

Plain text cung cấp nội dung dễ đọc ở mọi trình đọc thư; HTML cho phép dùng heading, liên kết có nhãn, bảng và kiểu trình bày phong phú hơn. Đây là **hai lựa chọn cho cùng một nội dung**, không phải hai đoạn cần nối tiếp khi hiển thị.

Các part trong multipart/alternative thường được sắp xếp từ phiên bản ít phong phú đến phiên bản phong phú hơn. Vì vậy, **text/plain thường đứng trước text/html**. Email client chọn phiên bản phù hợp với khả năng hoặc cài đặt của nó.

Nếu plain text nói “thanh toán thành công” nhưng HTML nói “thanh toán đang chờ”, hai part không còn là hai cách trình bày tương đương. Đây là lỗi dữ liệu/template, dù MIME hierarchy có hợp lệ.

### multipart/related: nội dung chính cùng tài nguyên phụ thuộc

HTML có thể tham chiếu ảnh nội tuyến:

~~~html
<img src="cid:brand-logo" alt="Logo">
~~~

Ảnh có thể được đóng gói cùng nội dung HTML trong multipart/related:

~~~text
multipart/related
    +-- text/html
    |     <img src="cid:brand-logo">
    |
    '-- image/png
          Content-ID: <brand-logo>
          Content-Disposition: inline
~~~

Part đầu tiên của multipart/related là **nội dung gốc (root part)**; những part còn lại là tài nguyên liên quan mà nội dung gốc tham chiếu. Với ví dụ trên, HTML là root và ảnh là resource được tìm bằng Content-ID.

**CID trong HTML và Content-ID của ảnh phải khớp nhau.** Nếu HTML dùng cid:brand-logo nhưng part ảnh có Content-ID khác, ảnh có thể không được tìm thấy dù MIME message vẫn chứa đủ một HTML part và một image part.

### multipart/mixed: các phần độc lập trong cùng email

Một email có thể chứa nội dung chính và file đính kèm:

~~~text
multipart/mixed
    +-- text/plain
    |     "Báo cáo được đính kèm."
    |
    '-- application/pdf
          Content-Disposition: attachment
          filename="report.pdf"
~~~

Các part con của mixed là những thành phần riêng biệt trong một thông điệp. Attachment không phải là một phiên bản thay thế của body và cũng không phải tài nguyên HTML tham chiếu bằng CID.

Vì vậy, nếu email có một PDF để người nhận tải về, PDF thường nằm trong nhóm **mixed**. Nếu HTML có logo, logo thuộc nhóm **related** với HTML. Nếu cần cả plain và HTML, hai phiên bản thuộc nhóm **alternative**.

## 2. Vì sao phải kết hợp và lồng ba loại multipart?

Giả sử một email xác nhận đơn hàng có yêu cầu:

1. Có plain text fallback.
2. Có HTML với logo và ảnh sản phẩm nội tuyến.
3. Có hóa đơn PDF đính kèm.

Một cấu trúc MIME thường dùng cho trường hợp này:

~~~text
MimeMessage
|
'-- multipart/mixed
     |
     +-- multipart/related
     |    |
     |    +-- multipart/alternative
     |    |    |
     |    |    +-- text/plain
     |    |    |
     |    |    '-- text/html
     |    |
     |    +-- image/png
     |    |     Content-ID: <brand-logo>
     |    |
     |    '-- image/jpeg
     |          Content-ID: <product-photo>
     |
     '-- application/pdf
           Content-Disposition: attachment
           filename="invoice.pdf"
~~~

Đọc cây theo quan hệ:

- **mixed** ở ngoài cùng gom nhóm nội dung email và attachment PDF.
- **related** gom phần nội dung có thể hiển thị cùng tài nguyên ảnh nội tuyến.
- **alternative** cung cấp hai phiên bản plain và HTML của nội dung.
- Các image part được tham chiếu từ HTML qua CID.
- PDF nằm ở cấp mixed, tách khỏi tài nguyên inline.

Đây là một cách lồng hợp lệ và dễ hiểu cho email có cả body alternatives, inline resources và attachments. Cấu trúc thực tế do cách tạo message, multipart mode và thư viện quyết định; cần đọc MIME tree sau khi tạo thay vì suy đoán chỉ từ số lần gọi helper.

### Một cách lồng khác cũng có thể hợp lệ

Về mặt MIME, một lựa chọn khác là đặt **multipart/alternative** ở ngoài, trong đó nhánh HTML là một multipart/related:

~~~text
multipart/mixed
    |
    +-- multipart/alternative
    |    |
    |    +-- text/plain
    |    |
    |    '-- multipart/related
    |         +-- text/html
    |         +-- image/png
    |         '-- image/jpeg
    |
    '-- application/pdf
~~~

Trong cấu trúc này, plain text là một lựa chọn; lựa chọn HTML gồm HTML root và các ảnh liên quan. Đây cũng là một cách biểu diễn có ý nghĩa: ảnh chỉ cần thiết cho nhánh HTML.

Hai sơ đồ thể hiện những cách nhóm nội dung khác nhau. Điều cần giữ là **alternative phải chứa các lựa chọn tương đương**, **related phải gom nội dung gốc với tài nguyên được tham chiếu**, và **mixed phải gom các phần độc lập như attachment**. Khi dùng Spring helper, hãy kiểm tra cấu trúc mà phiên bản và multipart mode đang tạo ra.

## 3. Vai trò của thứ tự part trong từng loại multipart

Thứ tự các part không phải chi tiết trang trí.

| Multipart | Part đầu tiên | Các part tiếp theo |
| --- | --- | --- |
| **alternative** | Phiên bản ít phong phú hơn, thường là text/plain | Các phiên bản phong phú hơn, thường HTML ở cuối |
| **related** | Root part, tức nội dung chính | Tài nguyên được root tham chiếu, như ảnh CID |
| **mixed** | Nội dung chính hoặc nhóm nội dung của email | Các phần độc lập, thường là attachment |

### Với alternative

Đặt plain text trước HTML giúp client chọn phiên bản phù hợp. Không nên đặt hai bản giống hệt nhau chỉ để tăng số part; mỗi bản cần có nội dung thực sự tương ứng.

### Với related

Root part phải là nội dung mà các resource liên quan phục vụ. Nếu HTML tham chiếu logo, HTML cần được xác định là root của nhóm related (hoặc nằm trong root alternative mà nhóm related sử dụng theo cấu trúc đã chọn). Ảnh CID không tự trở thành body chính.

### Với mixed

Nội dung email nên được đặt trước attachment. Điều này giúp các client xử lý phần body và phần tải xuống theo quan hệ thông thường. Attachment vẫn là part độc lập, dù nó có cùng chủ đề với nội dung body.

## 4. Chọn multipart mode trong MimeMessageHelper

Spring cung cấp các chế độ multipart phổ biến:

| Hằng số | Cấu trúc gốc | Mục đích thường gặp |
| --- | --- | --- |
| **MULTIPART_MODE_NO** | Không tạo multipart | Một body đơn giản |
| **MULTIPART_MODE_MIXED** | multipart/mixed | Body cùng các attachment |
| **MULTIPART_MODE_RELATED** | multipart/related | Body cùng inline resources |
| **MULTIPART_MODE_MIXED_RELATED** | mixed root với related multipart lồng bên trong | HTML có inline resources và có thêm attachment |

Với email cần cả **alternative + related + mixed**, chế độ **MULTIPART_MODE_MIXED_RELATED** thường là điểm khởi đầu phù hợp: mixed ở root để chứa attachment, related lồng bên trong để chứa nội dung và tài nguyên inline. Khi dùng **setText(plainText, htmlText)**, helper tạo nội dung thay thế theo API của nó; khi dùng **addInline(...)**, resource được thêm vào nhóm related; khi dùng **addAttachment(...)**, attachment được thêm vào nhóm mixed bên ngoài.

Sơ đồ khái niệm:

~~~text
MimeMessageHelper
    |
    +-- setText(plain, html)
    |       -> alternative body
    |
    +-- addInline(cid, resource)
    |       -> related resource
    |
    '-- addAttachment(name, resource)
            -> mixed attachment
~~~

**Multipart mode quyết định cấu trúc container**, còn các phương thức helper bổ sung nội dung vào cấu trúc đó. Chỉ gọi cả ba phương thức không tự chứng minh các part đã được đặt đúng quan hệ; hãy kiểm tra message sau khi tạo.

### Khởi tạo helper

~~~java
MimeMessage message = mailSender.createMimeMessage();

MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8"
);
~~~

Tham số thứ hai là multipart mode; tham số thứ ba là charset cho phần văn bản. Charset UTF-8 giúp nội dung tiếng Việt được biểu diễn đúng khi thư viện tạo text parts. Nó không có nghĩa các file nhị phân như PNG hoặc PDF được chuyển thành UTF-8.

### Đừng nhầm multipart với HTML

Multipart chỉ có nghĩa thông điệp chứa nhiều MIME parts. Nó không tự tạo HTML, cũng không tự tạo plain fallback.

- **setText(html, true)** đánh dấu chuỗi body là HTML.
- **setText(plainText, htmlText)** cung cấp hai phiên bản nội dung thay thế.
- **addInline(...)** thêm resource nội tuyến.
- **addAttachment(...)** thêm file đính kèm.

Một email multipart/mixed có thể chỉ có text/plain và PDF. Một email text/html đơn giản có thể không cần multipart. Hãy chọn cấu trúc theo quan hệ nội dung, không chọn theo suy nghĩ “email càng nhiều multipart càng tốt”.

## 5. Tạo email có plain text, HTML, ảnh inline và PDF

Ví dụ dưới đây tạo email xác nhận đơn hàng với:

- **Plain text** chứa thông tin đơn hàng và đường dẫn xem đơn.
- **HTML** có logo và ảnh sản phẩm nội tuyến.
- **PDF** là hóa đơn đính kèm.

Giả sử hai template đã được cấu hình trong các TemplateEngine tương ứng. HTML template tham chiếu ảnh bằng CID:

~~~html
<html>
  <body>
    <img src="cid:brand-logo" alt="Logo cửa hàng">
    <h1>Đơn hàng đã được xác nhận</h1>
    <p>Xin chào <span th:text="${mail.recipientName}">bạn</span>.</p>
    <p>
      Đơn hàng:
      <strong th:text="${mail.orderNumber}">ORD-000</strong>
    </p>
    <p>
      Sản phẩm:
      <span th:text="${mail.productName}">Sản phẩm</span>
    </p>
    <img src="cid:product-photo" alt="Ảnh sản phẩm">
    <p>
      <a th:href="${mail.orderUrl}">Xem đơn hàng</a>
    </p>
  </body>
</html>
~~~

Plain text template có thể là:

~~~text
ĐƠN HÀNG ĐÃ ĐƯỢC XÁC NHẬN

Xin chào, [[${mail.recipientName}]].
Mã đơn hàng: [[${mail.orderNumber}]]
Sản phẩm: [[${mail.productName}]]

Xem đơn hàng:
[[${mail.orderUrl}]]

Hóa đơn PDF được đính kèm trong email này.
~~~

Cú pháp nội suy của plain text phụ thuộc template mode và dialect được cấu hình; ví dụ trên minh họa ý tưởng nội dung, cần dùng cú pháp đúng với resolver text của ứng dụng.

Trong ví dụ service bên dưới, hai bean **htmlTemplateEngine** và **textTemplateEngine** phải được cấu hình với template mode/resolver tương ứng. Chú thích **@Qualifier** phân biệt hai bean cùng kiểu Java; nếu ứng dụng chỉ dùng một TemplateEngine, có thể cấu hình nhiều resolver hoặc một cách render riêng phù hợp với kiến trúc dự án.

### Mail model

~~~java
public record OrderMailModel(
        String recipientName,
        String orderNumber,
        String productName,
        String orderUrl
) {
    public OrderMailModel {
        if (orderNumber == null || orderNumber.isBlank()) {
            throw new IllegalArgumentException("Thiếu orderNumber");
        }
        if (orderUrl == null || orderUrl.isBlank()) {
            throw new IllegalArgumentException("Thiếu orderUrl");
        }

        recipientName =
                recipientName == null || recipientName.isBlank()
                        ? "bạn"
                        : recipientName.strip();
    }
}
~~~

Model kiểm tra các biến bắt buộc và chuẩn hóa tên người nhận. Trong ứng dụng thật, **orderUrl** cần được tạo từ domain tin cậy, còn **productName** phải được hiển thị qua cơ chế HTML escaping của template engine.

### Service tạo MIME message

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.util.Locale;
import org.springframework.core.io.Resource;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.mail.javamail.JavaMailSender;
import org.springframework.mail.javamail.MimeMessageHelper;
import org.springframework.stereotype.Service;
import org.thymeleaf.TemplateEngine;
import org.thymeleaf.context.Context;

@Service
public class OrderMailService {

    private final JavaMailSender mailSender;
    private final TemplateEngine htmlTemplateEngine;
    private final TemplateEngine textTemplateEngine;

    public OrderMailService(
            JavaMailSender mailSender,
            @Qualifier("htmlTemplateEngine") TemplateEngine htmlTemplateEngine,
            @Qualifier("textTemplateEngine") TemplateEngine textTemplateEngine
    ) {
        this.mailSender = mailSender;
        this.htmlTemplateEngine = htmlTemplateEngine;
        this.textTemplateEngine = textTemplateEngine;
    }

    public void sendOrderConfirmation(
            String recipient,
            OrderMailModel model,
            Resource brandLogo,
            Resource productPhoto,
            Resource invoicePdf,
            Locale locale
    ) throws MessagingException {

        Context context = new Context(locale);
        context.setVariable("mail", model);

        String html = htmlTemplateEngine.process(
                "mail/order-confirmation",
                context
        );
        String plain = textTemplateEngine.process(
                "mail/order-confirmation.txt",
                context
        );

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                "UTF-8"
        );

        helper.setFrom("orders@example.test");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng " + model.orderNumber());

        // Tạo hai phiên bản thay thế của phần nội dung trước.
        helper.setText(plain, html);

        // Các ảnh được HTML tham chiếu bằng CID.
        helper.addInline("brand-logo", brandLogo, "image/png");
        helper.addInline("product-photo", productPhoto, "image/jpeg");

        // Hóa đơn là attachment độc lập ở nhóm mixed.
        helper.addAttachment(
                "invoice-" + model.orderNumber() + ".pdf",
                invoicePdf,
                "application/pdf"
        );

        mailSender.send(message);
    }
}
~~~

Đoạn mã minh họa cách phối hợp các API:

1. Cùng một **OrderMailModel** được đưa vào context cho cả HTML và plain text.
2. **setText(plain, html)** tạo nội dung thay thế.
3. **addInline(...)** thêm các ảnh có Content-ID trùng với CID trong HTML.
4. **addAttachment(...)** thêm PDF với Content-Type tường minh.
5. **JavaMailSender.send(...)** nộp MIME message qua transport.

Ở đây dùng **MULTIPART_MODE_MIXED_RELATED** vì email có cả inline resources và attachment. Tên CID trong helper là **brand-logo** và **product-photo**, nên HTML phải tham chiếu chính xác **cid:brand-logo** và **cid:product-photo**.

### Vì sao gọi setText trước addInline?

Khi dùng **MimeMessageHelper**, nên thiết lập phần text/HTML trước khi thêm inline resource. Cách gọi này giúp helper tạo nội dung chính trước, rồi gắn các resource liên quan vào nhóm multipart phù hợp. Nếu thêm inline trước khi có nội dung HTML, tùy cách cấu trúc được tạo, có thể gặp lỗi hoặc quan hệ MIME không như mong đợi.

### Vì sao PDF dùng addAttachment thay vì addInline?

PDF hóa đơn cần được người nhận tải/mở như tài liệu đính kèm, không phải ảnh mà HTML tham chiếu bằng CID. **addAttachment(...)** tạo part có disposition attachment; **addInline(...)** tạo part liên quan đến body, thường được tham chiếu bằng CID.

Nếu muốn người nhận xem PDF qua một liên kết trong HTML, hãy tạo một URL an toàn tới tài liệu. Đính kèm PDF và cung cấp link tải là hai cách phân phối khác nhau.

### Resource phải còn đọc được

Các Resource truyền vào helper phải còn khả dụng khi message được serialize/gửi. Không xóa file tạm hoặc đóng nguồn stream quá sớm sau khi gọi **addAttachment(...)** hay **addInline(...)**. Với nguồn chỉ đọc một lần, cần bảo đảm implementation có thể mở stream theo yêu cầu của thư viện; nếu không, dùng một Resource phù hợp hơn.

## 6. Cấu trúc MIME raw minh họa

Một message được tạo theo ví dụ có thể được biểu diễn khái niệm như sau:

~~~text
MIME-Version: 1.0
Content-Type: multipart/mixed; boundary="mixed-01"

--mixed-01
Content-Type: multipart/related; boundary="related-01"

--related-01
Content-Type: multipart/alternative; boundary="alternative-01"

--alternative-01
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

Don hang ORD-1528 da duoc xac nhan.

--alternative-01
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable

<img src=3D"cid:brand-logo">
<h1>Don hang da duoc xac nhan</h1>

--alternative-01--
--related-01
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <brand-logo>
Content-Disposition: inline

[payload anh da duoc luoc bot]

--related-01--
--mixed-01
Content-Type: application/pdf; name="invoice-ORD-1528.pdf"
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice-ORD-1528.pdf"

[payload PDF da duoc luoc bot]

--mixed-01--
~~~

Đây là **raw MIME rút gọn để minh họa cấu trúc**, không phải một file email hoàn chỉnh có thể parse vì payload đã được lược bỏ. Boundary thực tế được thư viện sinh tự động. Các giá trị quoted-printable và Base64 chỉ minh họa cách byte được biểu diễn.

Điểm cần đọc:

- Boundary **mixed-01** tách phần body-related khỏi PDF.
- Boundary **related-01** tách phần nội dung chính khỏi ảnh inline.
- Boundary **alternative-01** tách plain text khỏi HTML.
- Header **Content-ID** kết nối ảnh với CID trong HTML.
- Header **Content-Disposition: attachment** cho biết PDF là file đính kèm.

Trong raw MIME thực tế, tên boundary sẽ khác, header có thể được gấp dòng, filename có thể được mã hóa, và thứ tự/header bổ sung có thể thay đổi. Hãy dùng parser MIME thay vì tự tách raw message bằng chuỗi boundary.

## 7. Kiểm tra MIME tree sau khi helper tạo message

Một message có thể chứa đủ các loại part nhưng vẫn được lồng sai. Ví dụ:

- Có text/plain và text/html nhưng chúng không nằm trong multipart/alternative.
- Có image/png và Content-ID nhưng ảnh không nằm trong nhóm related phù hợp.
- Có application/pdf nhưng PDF lại được thêm như inline resource thay vì attachment.
- Có mixed ở root nhưng các attachment không nằm ở cấp dự kiến.

Vì vậy, hãy kiểm tra **loại part, metadata và quan hệ cha/con**.

### Duyệt Part và Multipart đệ quy

Jakarta Mail cung cấp các API:

| API | Vai trò |
| --- | --- |
| **Part** | Giao diện chung cho message hoặc một body part |
| **Multipart** | Container chứa nhiều body part |
| **BodyPart** | Một phần con trong multipart |
| **MimeBodyPart** | Implementation MIME của body part |
| **MimeMessage** | Email message ở cấp root |

Một hàm duyệt cây cần:

1. In metadata của part hiện tại.
2. Nếu part là multipart, lấy Multipart và duyệt từng BodyPart.
3. Nếu part là message/rfc822, có thể duyệt tiếp message lồng bên trong.
4. Không đọc toàn bộ payload nhị phân chỉ để in cấu trúc.

Ví dụ:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.MessagingException;
import java.io.IOException;

public final class MimeTreePrinter {

    private MimeTreePrinter() {
    }

    public static void print(Part root)
            throws MessagingException, IOException {
        visit(root, "root", 0);
    }

    private static void visit(
            Part part,
            String path,
            int depth
    ) throws MessagingException, IOException {

        String indent = "  ".repeat(depth);
        String[] contentIds = part.getHeader("Content-ID");
        String contentId = contentIds == null
                ? ""
                : String.join(",", contentIds);

        System.out.printf(
                "%s%s type=%s disposition=%s filename=%s cid=%s%n",
                indent,
                path,
                part.getContentType(),
                part.getDisposition(),
                part.getFileName(),
                contentId
        );

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    BodyPart child = multipart.getBodyPart(i);
                    visit(child, path + "." + i, depth + 1);
                }
            }
        } else if (part.isMimeType("message/rfc822")) {
            Object content = part.getContent();
            if (content instanceof Message nestedMessage) {
                visit(nestedMessage, path + ".message", depth + 1);
            }
        }
    }
}
~~~

Ví dụ trên in **Content-Type**, **Content-Disposition**, filename và Content-ID. Nó không dump body text hay byte attachment. Trong production, các metadata như filename hoặc Content-ID cũng có thể chứa thông tin nội bộ; chỉ log khi cần và theo chính sách bảo vệ dữ liệu.

### Cây mong đợi ở mức khái niệm

Với email có mixed, related và alternative, kết quả có thể có dạng:

~~~text
root type=multipart/mixed
  root.0 type=multipart/related
    root.0.0 type=multipart/alternative
      root.0.0.0 type=text/plain
      root.0.0.1 type=text/html
    root.0.1 type=image/png disposition=inline cid=<brand-logo>
    root.0.2 type=image/jpeg disposition=inline cid=<product-photo>
  root.1 type=application/pdf disposition=attachment filename=invoice.pdf
~~~

Đây là cây minh họa cho cấu trúc được mô tả ở phần trước. Tên boundary, chỉ số con và cách lồng chính xác có thể khác tùy mode/phiên bản thư viện. Khi viết test, hãy xác định **hợp đồng cấu trúc mà ứng dụng yêu cầu**, rồi kiểm tra message thực tế theo hợp đồng đó.

### Vì sao chỉ xem root.getCount() là chưa đủ?

Nếu root mixed có hai con trực tiếp, một con related và một con PDF, **getCount()** ở root trả về hai. Các part text/plain, text/html và ảnh nằm sâu bên trong related. Đếm part ở một tầng không phải là đếm toàn bộ leaf của cây.

Hãy duyệt đệ quy và dùng đường dẫn như **root.0.0.1** để chỉ ra part cụ thể khi điều tra.

## 8. Kiểm tra đúng quan hệ alternative, related và mixed

Một bài kiểm tra cấu trúc cần xem từng nhóm:

### Kiểm tra alternative

Trong nhóm alternative, xác nhận có:

- Một part **text/plain**.
- Một part **text/html**.
- Hai part thể hiện cùng thông tin nghiệp vụ.
- Plain text được đặt trước HTML theo quy tắc sắp xếp thông thường.

Chỉ tìm thấy hai MIME type ở hai nhánh khác nhau của cây chưa đủ chứng minh chúng là hai lựa chọn thay thế nhau.

### Kiểm tra related

Xác nhận:

- Root của nhóm related là nội dung chính hoặc nhóm alternative chứa nội dung.
- HTML tham chiếu đúng CID.
- Mỗi CID được tham chiếu có một resource part tương ứng.
- Content-ID không bị trùng trong cùng phạm vi tham chiếu.
- Part ảnh có Content-Type phù hợp với bytes.
- Inline resource được thêm bằng **addInline(...)** và nằm trong nhóm related dự kiến.

Nếu HTML dùng **cid:brand-logo**, part ảnh thường có header **Content-ID: <brand-logo>**. Helper xử lý cú pháp header; người lập trình cần dùng cùng định danh khi gọi addInline và khi viết HTML.

### Kiểm tra mixed

Xác nhận:

- Root là **multipart/mixed** nếu đó là cấu trúc mong muốn.
- Nhóm nội dung chính nằm trước attachment.
- PDF có **Content-Disposition: attachment**.
- Filename là tên hiển thị mong muốn.
- PDF không bị đưa nhầm vào related như một resource inline.

### Kiểm tra nội dung và byte

Metadata đúng chưa chứng minh payload đúng. Với file quan trọng, có thể đọc stream của attachment sau khi parse message và so sánh hash với file nguồn. Đối với text parts, kiểm tra nội dung sau khi MIME parser giải mã transfer encoding.

Không nên so sánh toàn bộ raw MIME như một chuỗi cố định vì boundary, Message-ID, ngày giờ, header folding và transfer encoding có thể thay đổi hợp lệ.

## 9. Serialize và parse lại MIME message

Một MimeMessage có thể được chuẩn bị trong bộ nhớ nhưng một số header hoặc dữ liệu part chỉ được hoàn thiện khi message được serialize. Để kiểm tra dạng MIME thực tế, có thể gọi **saveChanges()**, ghi message ra file trong test, rồi parse lại.

~~~java
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Properties;

public final class MimeMessageRoundTrip {

    private MimeMessageRoundTrip() {
    }

    public static void write(MimeMessage message, Path destination)
            throws Exception {
        message.saveChanges();
        try (OutputStream output = Files.newOutputStream(destination)) {
            message.writeTo(output);
        }
    }

    public static MimeMessage read(Path source) throws Exception {
        Session session = Session.getInstance(new Properties());
        try (InputStream input = Files.newInputStream(source)) {
            return new MimeMessage(session, input);
        }
    }
}
~~~

Sau đó:

~~~java
Path eml = Path.of("build/test-mail/order-confirmation.eml");
MimeMessageRoundTrip.write(message, eml);

MimeMessage parsed = MimeMessageRoundTrip.read(eml);
MimeTreePrinter.print(parsed);
~~~

Đây là phép kiểm tra **round-trip MIME**: serialize message rồi parse lại để xem cấu trúc có thể đọc được theo định dạng MIME. Nó không gửi email và không kiểm tra SMTP provider hoặc cách mọi email client hiển thị.

Raw .eml có thể chứa địa chỉ, nội dung giao dịch, link có token và toàn bộ attachment được mã hóa. Chỉ tạo file dump bằng dữ liệu thử nghiệm, lưu ở vị trí được bảo vệ và xóa theo chính sách. **Base64 không phải mã hóa bảo mật**.

## 10. Kiểm thử message có cả ba loại multipart

Một test tốt không chỉ xác nhận message có multipart, mà cần kiểm tra những quan hệ quan trọng:

| Điều cần xác nhận | Bằng chứng trong MIME tree |
| --- | --- |
| Có body thay thế | Một nhóm multipart/alternative chứa text/plain và text/html |
| Có ảnh inline | Part image có Content-ID được HTML tham chiếu |
| Có attachment | Part có disposition attachment và filename mong muốn |
| Có container phù hợp | Root mixed và nhóm related nằm ở vị trí dự kiến |
| Nội dung nhất quán | Plain và HTML cùng order number, trạng thái, số tiền, URL |
| Payload được giữ nguyên | Bytes sau parse/giải mã khớp nguồn khi test yêu cầu |

### Tìm part theo loại thay vì cố định index

Với cây có nhiều cấp, test không nên giả định PDF luôn là **root.getBodyPart(1)** nếu template có thể thêm ảnh hoặc thay đổi cấu trúc. Có thể duyệt đệ quy để thu thập các part, rồi tìm theo **MIME type + disposition + filename**.

Ví dụ hàm tìm attachment:

~~~java
import jakarta.mail.BodyPart;
import jakarta.mail.Message;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.MessagingException;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public final class MimePartSearch {

    private MimePartSearch() {
    }

    public static List<Part> findAttachments(Part root)
            throws MessagingException, IOException {
        List<Part> matches = new ArrayList<>();
        walk(root, matches);
        return matches;
    }

    private static void walk(Part part, List<Part> matches)
            throws MessagingException, IOException {

        if (Part.ATTACHMENT.equalsIgnoreCase(part.getDisposition())) {
            matches.add(part);
        }

        if (part.isMimeType("multipart/*")) {
            Object content = part.getContent();
            if (content instanceof Multipart multipart) {
                for (int i = 0; i < multipart.getCount(); i++) {
                    BodyPart child = multipart.getBodyPart(i);
                    walk(child, matches);
                }
            }
        } else if (part.isMimeType("message/rfc822")) {
            Object content = part.getContent();
            if (content instanceof Message nested) {
                walk(nested, matches);
            }
        }
    }
}
~~~

Sau đó test có thể tìm part PDF:

~~~java
List<Part> attachments = MimePartSearch.findAttachments(parsed);

Part invoice = attachments.stream()
        .filter(part -> "invoice-ORD-1528.pdf".equals(part.getFileName()))
        .findFirst()
        .orElseThrow();

assertTrue(invoice.isMimeType("application/pdf"));
assertEquals(Part.ATTACHMENT, invoice.getDisposition());
~~~

Đoạn tìm kiếm trên minh họa cách tìm part theo disposition và filename. Với email có nhiều loại attachment, cần kiểm tra thêm MIME type, số lượng, nội dung hoặc hash theo hợp đồng của từng loại.

### Kiểm tra alternative nằm trong đúng related container

Tìm text/plain và text/html ở mọi nơi chưa đủ. Nếu cần kiểm tra hierarchy, hãy xác định:

1. Root có phải multipart/mixed không.
2. Một child của mixed có phải multipart/related không.
3. Root content của related có phải multipart/alternative không, theo cấu trúc mà ứng dụng chọn.
4. Các image parts là sibling trong related với Content-ID phù hợp.
5. Attachment nằm ngoài nhóm related ở cấp mixed.

Các test này cần dựa trên **multipart mode và cấu trúc dự kiến cụ thể**. Nếu ứng dụng chủ động dùng cách lồng hợp lệ khác, hãy kiểm tra theo cấu trúc đó thay vì ép mọi message phải có cùng đường dẫn node.

### Kiểm tra CID

Giả sử HTML có:

~~~html
<img src="cid:brand-logo">
~~~

Test nên tìm image part có:

~~~text
Content-ID: <brand-logo>
Content-Type: image/png
Content-Disposition: inline
~~~

Header Content-ID thường có cặp dấu ngoặc nhọn; chuỗi trong URI CID thường không có chúng. Khi so sánh, chuẩn hóa hai cách biểu diễn thay vì so sánh raw header với toàn bộ chuỗi cid:brand-logo.

### Kiểm tra bản plain text không phụ thuộc ảnh

Plain text không thể hiển thị ảnh CID như HTML. Nội dung fallback cần truyền tải đủ thông tin ngay cả khi mọi ảnh bị bỏ qua:

- Tên/loại thông báo.
- Mã đơn, trạng thái, số tiền hoặc dữ liệu quan trọng.
- Đường dẫn đầy đủ nếu người nhận cần thực hiện hành động.
- Thông tin file đính kèm nếu email có tài liệu.

Không nên chỉ để dòng **“Xem nút bên dưới”** trong plain text, vì bản này không có nút HTML.

## 11. Các lỗi thường gặp khi kết hợp multipart

### Lỗi 1: Dùng multipart/mixed cho mọi thứ

Nếu đặt plain text, HTML, ảnh và PDF thành các part ngang hàng trong mixed, email client có thể coi mỗi phần là một thành phần độc lập. Nó không biết plain và HTML là hai phiên bản thay thế, cũng không biết ảnh là tài nguyên của HTML.

**Cách xử lý:** dùng alternative cho body variants, related cho CID resources và mixed cho attachment.

### Lỗi 2: Đưa PDF vào multipart/alternative

PDF không phải một cách trình bày thay thế của body. Nếu đặt PDF cùng cấp với plain/HTML trong alternative, client có thể coi PDF là một phiên bản thay thế của nội dung và không hiển thị như attachment thông thường.

**Cách xử lý:** đặt PDF trong nhóm mixed ở ngoài nhóm nội dung.

### Lỗi 3: Đưa ảnh inline vào mixed như attachment độc lập

Ảnh có thể xuất hiện trong danh sách file đính kèm nhưng HTML không tham chiếu được theo CID hoặc client không xử lý nó như tài nguyên liên quan.

**Cách xử lý:** thêm ảnh bằng **addInline(...)**, dùng Content-ID khớp HTML và kiểm tra nhóm related.

### Lỗi 4: Dùng addAttachment cho ảnh cần hiển thị trong HTML

**addAttachment(...)** biểu diễn file như attachment độc lập. Nó không tự tạo CID resource cho thẻ img.

**Cách xử lý:** dùng **addInline(...)** cho ảnh được HTML tham chiếu; có thể vẫn đính kèm riêng một bản ảnh nếu nghiệp vụ thật sự cần cả hai cách.

### Lỗi 5: CID không khớp

HTML tham chiếu **cid:logo** nhưng helper thêm inline với ID **brand-logo**. MIME tree có thể chứa ảnh, nhưng HTML không tìm thấy đúng resource.

**Cách xử lý:** dùng cùng một định danh trong HTML và lời gọi addInline; tránh tạo ID ngẫu nhiên ở hai nơi riêng biệt.

### Lỗi 6: Gọi addInline trước setText

Thứ tự thao tác có thể khiến helper chưa có main body thích hợp khi gắn inline resource.

**Cách xử lý:** thiết lập plain/HTML bằng setText trước, rồi mới addInline và addAttachment.

### Lỗi 7: Chỉ có HTML, không có plain fallback

Email vẫn có thể hợp lệ nhưng không đáp ứng yêu cầu hỗ trợ trình đọc plain text hoặc môi trường hạn chế HTML.

**Cách xử lý:** render bản plain có đầy đủ nội dung quan trọng và gọi overload **setText(plain, html)**.

### Lỗi 8: Plain và HTML khác dữ liệu

Hai template dùng model riêng hoặc tính default khác nhau, khiến người nhận đọc một trạng thái trong plain và trạng thái khác trong HTML.

**Cách xử lý:** dùng cùng một mail model đã validate/normalize cho cả hai template.

### Lỗi 9: Attachment nằm trong related

Nếu attachment bị thêm vào container related, một số client có thể coi nó là tài nguyên liên quan thay vì file đính kèm độc lập.

**Cách xử lý:** khi có cả inline resource và attachment, dùng chế độ mixed-related phù hợp và xác nhận attachment nằm ở nhóm mixed.

### Lỗi 10: MIME type của ảnh hoặc PDF không chính xác

Một image part có CID nhưng Content-Type không phù hợp có thể không hiển thị; một PDF có filename đúng nhưng Content-Type tổng quát có thể bị nhận diện khác mong đợi.

**Cách xử lý:** cung cấp MIME type tường minh khi cần, kiểm tra byte nguồn và kiểm tra part sau khi tạo.

### Lỗi 11: Cho rằng helper mode luôn tạo đúng một cây giống nhau

Các chi tiết lồng nhau có thể thay đổi theo mode, overload, phiên bản Spring/Jakarta Mail và cách thêm part.

**Cách xử lý:** xem mode là lựa chọn cấu trúc ban đầu; xác nhận cây thực tế bằng API Jakarta Mail hoặc raw MIME đã parse.

### Lỗi 12: MIME tree đúng nghĩa là email đã được giao

Kiểm tra cấu trúc chỉ xác nhận message được dựng như mong muốn. SMTP vẫn có thể từ chối, provider có thể xử lý tiếp, và email client có thể chặn ảnh hoặc thay đổi cách render.

**Cách xử lý:** tách kiểm tra MIME, kiểm tra SMTP submission, delivery/bounce events và kiểm tra hiển thị ở email client.

## 12. Những điểm cần kiểm tra trên email client

MIME tree đúng là điều kiện quan trọng, nhưng email client vẫn có quyền chọn cách trình bày nội dung theo khả năng và cài đặt của nó.

| Thành phần | Điều cần thử |
| --- | --- |
| **Plain text** | Mở thư ở chế độ plain text hoặc một trình đọc không hiển thị HTML; xác nhận đủ nội dung và URL |
| **HTML** | Kiểm tra heading, link, bảng, màu sắc và khả năng đọc trên màn hình nhỏ |
| **Inline image** | Bật/tắt tải ảnh từ xa; xác nhận ảnh CID vẫn hiển thị khi resource được đóng gói trong thư |
| **Attachment** | Xác nhận PDF xuất hiện như file đính kèm, tên file dễ hiểu và file mở được |
| **Dark mode** | Kiểm tra độ tương phản, nền và chữ khi client đổi màu |
| **Accessibility** | Kiểm tra alt text, thứ tự đọc và nội dung không phụ thuộc riêng vào màu hoặc ảnh |

### Inline image và remote image khác nhau

Ảnh CID được đóng gói trong MIME message và được HTML tham chiếu bằng Content-ID. Ảnh từ xa thường dùng URL HTTPS:

~~~html
<img src="https://cdn.example.test/banner.png" alt="Banner">
~~~

Hai cách có hành vi khác nhau:

- **CID image** tăng kích thước email do ảnh nằm trong message; không cần client tải ảnh từ URL ngoài để có byte ảnh.
- **Remote image** giữ message nhỏ hơn nhưng client có thể chặn tải ảnh, URL có thể hết hạn hoặc máy chủ ảnh không sẵn sàng.
- Cả hai đều không nên chứa thông tin thiết yếu chỉ có thể hiểu qua hình ảnh; hãy có văn bản tương đương.

Với logo nhỏ cần hiển thị ổn định trong email, CID có thể phù hợp. Với banner lớn hoặc ảnh thay đổi thường xuyên, remote URL có thể phù hợp hơn nếu chính sách quyền riêng tư và tải ảnh cho phép.

### Không để ảnh quyết định ý nghĩa của thông điệp

Nếu HTML có biểu tượng màu xanh thể hiện “đã thanh toán”, plain text cần có câu **“Trạng thái: Đã thanh toán”**. Nếu ảnh sản phẩm không tải được, tên sản phẩm và mã đơn vẫn phải có trong nội dung. Alt text giúp người dùng công cụ trợ năng hiểu ảnh, nhưng không thay thế mọi thông tin nghiệp vụ.

### Attachment vẫn cần được kiểm tra riêng

PDF có thể xuất hiện đúng tên trong danh sách file nhưng payload bị hỏng. Hãy thử mở file trong môi trường kiểm thử, so sánh hash sau khi giải mã MIME nếu cần và kiểm tra giới hạn dung lượng của provider.

Không nên chỉ dựa vào icon PDF hoặc filename để kết luận file đã được đóng gói nguyên vẹn.

## 13. Charset, transfer encoding và header trong multipart

Khi kết hợp nhiều part, mỗi part có thể có Content-Type và Content-Transfer-Encoding riêng.

Ví dụ:

~~~text
multipart/alternative
    +-- text/plain; charset=UTF-8
    |      Content-Transfer-Encoding: quoted-printable
    |
    '-- text/html; charset=UTF-8
           Content-Transfer-Encoding: quoted-printable

multipart/related
    '-- image/png
           Content-Transfer-Encoding: base64

multipart/mixed
    '-- application/pdf
           Content-Transfer-Encoding: base64
~~~

Một số điểm cần nhớ:

- **UTF-8** mô tả cách biểu diễn ký tự trong text parts.
- **quoted-printable** hoặc **base64** mô tả cách byte được biểu diễn để truyền tải.
- File nhị phân như PNG/PDF thường dùng Base64 trong MIME.
- Boundary phân tách part; boundary được thư viện sinh và quản lý.
- Header Content-ID gắn định danh cho inline resource.
- Content-Disposition phân biệt part inline với attachment theo ý định của người gửi.

Không nên tự mã hóa nội dung thành Base64 rồi đưa vào **setText(...)**. Hãy đưa chuỗi text/HTML và Resource bytes vào helper; Jakarta Mail sẽ xử lý transfer encoding khi serialize message.

### Filename có thể cần encoding

Tên attachment chứa tiếng Việt hoặc ký tự ngoài ASCII có thể được biểu diễn bằng cơ chế mã hóa header/parameter phù hợp. Không nên tự nối tên file vào raw MIME header. Dùng **addAttachment(...)** với filename mong muốn và để thư viện xử lý việc mã hóa/quoting.

Nếu tên file hiển thị sai trên một client, hãy kiểm tra raw MIME header và thử client khác. Có thể chọn filename ASCII an toàn, dễ đọc nếu tương thích với hệ thống nhận quan trọng hơn việc giữ nguyên mọi dấu tiếng Việt.

## 14. Quản lý Content-ID và resource inline

Mỗi ảnh inline cần một định danh CID duy nhất trong phạm vi message. Ví dụ:

~~~java
helper.addInline("brand-logo", logoResource, "image/png");
helper.addInline("product-photo-1528", photoResource, "image/jpeg");
~~~

HTML:

~~~html
<img src="cid:brand-logo" alt="Logo">
<img src="cid:product-photo-1528" alt="Ảnh sản phẩm">
~~~

Không nên dùng cùng một CID cho hai ảnh khác nhau. Nếu hai phần tử HTML cùng tham chiếu một CID, client có thể hiển thị cùng một resource ở cả hai vị trí; nếu hai part cùng CID, kết quả lựa chọn resource có thể không nhất quán.

### Content-ID không phải đường dẫn file

CID là định danh nội dung trong message, không phải đường dẫn trên ổ đĩa hay URL tải file. Khi HTML dùng:

~~~html
<img src="cid:brand-logo">
~~~

email client tra cứu part trong message có Content-ID tương ứng. Nó không truy cập file local của server và không biết đường dẫn Resource mà Java đã sử dụng.

### Kiểm tra số lượng resource

Nếu template tham chiếu ba CID, message cần có đủ ba part resource tương ứng. Ngược lại, nếu message chứa nhiều ảnh inline nhưng HTML không dùng tới, các ảnh đó làm email lớn hơn mà không đem lại giá trị cho người nhận.

Nên quản lý danh sách CID trong một nơi có thể dùng chung cho template và Java, ví dụ constants hoặc một lớp định nghĩa tài nguyên email, để tránh sai khác khi đổi tên.

~~~java
public final class OrderMailContentIds {

    public static final String BRAND_LOGO = "brand-logo";
    public static final String PRODUCT_PHOTO = "product-photo";

    private OrderMailContentIds() {
    }
}
~~~

Khi tạo message:

~~~java
helper.addInline(
        OrderMailContentIds.BRAND_LOGO,
        brandLogo,
        "image/png"
);
~~~

Trong template, CID vẫn phải được viết đúng theo giá trị constant. Nếu cần tránh lặp string ở nhiều template, có thể truyền CID vào model hoặc dùng một cơ chế template fragment được quản lý chung.

## 15. Phân biệt cấu trúc MIME với trạng thái gửi

Việc kết hợp alternative, related và mixed diễn ra ở tầng **tạo message**. Sau đó, JavaMailSender nộp message qua transport. Các trạng thái này không nên bị gộp:

~~~text
Render templates
      |
      v
Build MIME tree
      |
      v
Serialize message
      |
      v
SMTP submission
      |
      v
Provider accepts / rejects
      |
      v
Delivery, bounce or downstream processing
      |
      v
Email client renders chosen content
~~~

| Giai đoạn | Câu hỏi cần trả lời |
| --- | --- |
| Render | Các biến và template có tạo ra plain/HTML đúng không? |
| MIME construction | Alternative, related, mixed có đúng quan hệ không? |
| Serialization | MIME headers, boundaries và payload có ghi được không? |
| SMTP submission | Server có chấp nhận message không? |
| Delivery | Provider có phát thư hoặc tạo bounce event không? |
| Rendering | Client có chọn đúng alternative và hiển thị inline resource/attachment như mong đợi không? |

Một MIME tree đúng không chứng minh server đã nhận thư. Server trả phản hồi chấp nhận sau DATA cũng không chứng minh người nhận đã mở thư hoặc email client đã hiển thị đúng mọi part.

Nếu SMTP báo thành công nhưng ảnh không hiện, hãy kiểm tra MIME raw phía nhận và client. Nếu PDF không đến, kiểm tra provider logs, giới hạn kích thước và trạng thái delivery. Không cần bật debug toàn bộ giao thức chỉ để trả lời một câu hỏi về HTML/CID nếu MIME tree và bản thư phía nhận đã cung cấp bằng chứng.

## 16. Bài tập tình huống

### Tình huống 1 — Plain text và HTML nằm ngang hàng trong mixed

Message có root multipart/mixed với các con text/plain, text/html và application/pdf.

**Hỏi:** client có hiểu plain và HTML là hai phiên bản thay thế không?

**Đáp:** không có quan hệ alternative được biểu diễn. Nếu muốn hai cách trình bày thay thế nhau, đặt plain và HTML trong multipart/alternative; nhóm nội dung đó cùng attachment có thể nằm dưới mixed.

### Tình huống 2 — HTML tham chiếu ảnh bằng CID

HTML dùng **cid:logo-main**, nhưng image part có Content-ID **<logo-footer>**.

**Hỏi:** vì sao ảnh không hiện?

**Đáp:** CID không khớp. Dùng cùng định danh trong HTML và lời gọi addInline.

### Tình huống 3 — Email có plain, HTML, logo và PDF

**Hỏi:** loại multipart nào cần xuất hiện?

**Đáp:** alternative cho plain/HTML, related cho nội dung và logo, mixed để gom nhóm body cùng PDF attachment. Một cấu trúc thường gặp là mixed ở ngoài, related ở trong, alternative là body của related.

### Tình huống 4 — PDF được thêm bằng addInline

**Hỏi:** vì sao PDF có thể không xuất hiện như file đính kèm?

**Đáp:** addInline tạo resource liên quan đến nội dung, thường được tham chiếu bằng CID. PDF cần tải riêng nên dùng addAttachment.

### Tình huống 5 — Email chỉ có một HTML body

**Hỏi:** có bắt buộc tạo multipart/alternative không?

**Đáp:** không. Nếu chỉ cần một HTML body, setText(html, true) có thể đủ. Alternative cần khi muốn cung cấp một phiên bản plain text thay thế.

### Tình huống 6 — Có hai part image/png nhưng không có CID

**Hỏi:** HTML có thể tham chiếu ảnh bằng cid không?

**Đáp:** không nếu các part không có Content-ID tương ứng. Hãy thêm inline resource với ID và tham chiếu đúng CID trong HTML.

### Tình huống 7 — Root mixed có hai child

Một child là related chứa alternative và hai ảnh; child còn lại là PDF.

**Hỏi:** tại sao getCount() trả hai dù email có năm leaf parts?

**Đáp:** getCount() chỉ đếm các part con trực tiếp của container đang gọi. Cần duyệt đệ quy để thấy toàn bộ cây.

### Tình huống 8 — MIME tree đúng nhưng Outlook hiển thị ảnh như attachment

**Hỏi:** có thể kết luận helper tạo sai?

**Đáp:** chưa. Kiểm tra Content-ID, Content-Disposition, cấu trúc related và raw message phía nhận. Sau đó thử trên phiên bản client mục tiêu vì cách hiển thị có thể khác nhau.

### Tình huống 9 — Plain text không có URL

HTML có nút **Xem đơn hàng**, nhưng plain chỉ nói “bấm nút bên dưới”.

**Hỏi:** fallback đã đủ chưa?

**Đáp:** chưa. Plain text cần URL đầy đủ hoặc hướng dẫn thay thế thực hiện được hành động.

### Tình huống 10 — Attachment xuất hiện trong related

**Hỏi:** cấu trúc có thể khiến client coi file là resource inline không?

**Đáp:** có. Khi có cả ảnh inline và file đính kèm, dùng mixed-related để tách nhóm resource liên quan khỏi attachment độc lập, rồi xác nhận MIME tree thực tế.

## 17. Quy trình tạo và kiểm tra email nhiều định dạng

~~~text
1. Xác định nội dung
   -> plain fallback
   -> HTML body
   -> inline images
   -> file attachments

2. Chuẩn bị dữ liệu
   -> validate biến bắt buộc
   -> normalize giá trị tùy chọn
   -> tạo URL và filename an toàn

3. Render
   -> dùng cùng model cho plain và HTML
   -> kiểm tra HTML escaping

4. Tạo MIME message
   -> MIXED_RELATED
   -> setText(plain, html)
   -> addInline(CID, resource, type)
   -> addAttachment(filename, resource, type)

5. Kiểm tra cây
   -> mixed chứa body group và attachments
   -> related chứa body và inline resources
   -> alternative chứa plain và HTML
   -> CID, disposition, filename và content type đúng

6. Kiểm tra serialize và gửi
   -> saveChanges/writeTo trong test nếu cần
   -> parse lại MIME
   -> SMTP test capture

7. Kiểm tra phía nhận
   -> plain/HTML rendering
   -> CID images
   -> attachment và dung lượng
~~~

Một email nhiều định dạng nên được kiểm thử ở nhiều lớp. Test template xác nhận nội dung; test MIME xác nhận cây; SMTP capture xác nhận message được nộp trong môi trường thử; email client xác nhận cách hiển thị thực tế.

**Kết hợp alternative, related và mixed** là cách biểu diễn ba quan hệ khác nhau trong cùng một email: alternative cung cấp các phiên bản nội dung, related kết nối nội dung với tài nguyên inline, còn mixed gom nhóm nội dung cùng những attachment độc lập. Với Spring Framework Mail, **MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED**, **setText(plain, html)**, **addInline(...)** và **addAttachment(...)** tạo nền tảng thuận tiện để xây dựng message. Luôn kiểm tra MIME tree và bản serialize để xác nhận quan hệ part thực tế, rồi thử trên email client mục tiêu trước khi coi trải nghiệm nhận thư đã hoàn chỉnh.
