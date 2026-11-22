# Thứ tự multipart ảnh hưởng khả năng hiển thị

## 1. Vì sao cấu trúc multipart quyết định cách email được hiển thị?

Trong **Spring Framework Mail**, một email có thể chứa nhiều dạng nội dung cùng lúc: văn bản thuần, HTML, ảnh nhúng trong HTML và file đính kèm. Những phần này được đóng gói theo cấu trúc **MIME multipart**. Cách tổ chức các phần không chỉ ảnh hưởng đến kích thước message mà còn quyết định email client hiểu đâu là nội dung chính, đâu là ảnh liên quan đến HTML và đâu là file người nhận cần tải xuống.

Một email có thể gửi thành công qua SMTP nhưng vẫn hiển thị sai:

- Ảnh logo xuất hiện thành file đính kèm thay vì nằm trong phần HTML.
- HTML được hiển thị nhưng ảnh có CID không xuất hiện.
- Người dùng thấy cả bản text và bản HTML như hai nội dung độc lập.
- File PDF bị coi như một phần của nội dung liên quan thay vì attachment.
- Email hiển thị đúng trong một client nhưng sai trong client khác.

Những tình huống này thường liên quan đến **Content-Type**, **multipart nesting**, **Content-ID**, **Content-Disposition** và thứ tự tạo các part.

Một email nhiều định dạng thường có các thành phần:

| Thành phần | MIME type / thuộc tính | Vai trò |
|---|---|---|
| Plain text | `text/plain` | Phiên bản văn bản cho client không render HTML |
| HTML | `text/html` | Phiên bản có định dạng, bố cục và liên kết ảnh CID |
| Inline image | `image/png`, `image/jpeg`... và `Content-ID` | Tài nguyên mà HTML tham chiếu |
| Attachment | `application/pdf`, `application/octet-stream`... | Tệp người nhận tải xuống |

**Multipart không đơn giản là một danh sách các file.** Các kiểu multipart biểu đạt quan hệ giữa những part:

- `multipart/alternative`: nhiều cách biểu diễn thay thế của cùng một nội dung.
- `multipart/related`: một tài nguyên gốc (thường là HTML) cùng các tài nguyên mà nó tham chiếu.
- `multipart/mixed`: một tập các phần độc lập được gửi cùng nhau, thường gồm nội dung thư và attachment.

Chọn cấu trúc phù hợp giúp email client diễn giải đúng mục đích của từng phần.

## 2. MIME multipart/alternative: text và HTML là hai phiên bản thay thế

Khi một email có cả text/plain và text/html, hai phần này thường thuộc **multipart/alternative**. Chúng diễn tả cùng một thông điệp ở hai dạng khác nhau, không phải hai thông báo độc lập.

~~~text
multipart/alternative
  |
  +-- text/plain; charset=UTF-8
  |
  +-- text/html; charset=UTF-8
~~~

Ví dụ:

~~~java
String plainText = """
        Xin chào!
        Đơn hàng ORD-001 đã được xác nhận.
        Cảm ơn bạn đã sử dụng dịch vụ.
        """;

String htmlText = """
        <html lang="vi">
          <body>
            <h1>Xin chào!</h1>
            <p>Đơn hàng <strong>ORD-001</strong>
               đã được xác nhận.</p>
            <p>Cảm ơn bạn đã sử dụng dịch vụ.</p>
          </body>
        </html>
        """;

helper.setText(plainText, htmlText);
~~~

Với overload hai tham số, `MimeMessageHelper.setText(plainText, htmlText)` tạo hai nội dung thay thế. Email client thường chọn dạng phong phú nhất mà nó hỗ trợ, thường là HTML; client text-only có thể chọn plain text.

**Thứ tự các part trong multipart/alternative có ý nghĩa.** Theo quy ước MIME, các alternative được sắp xếp từ dạng ít phong phú hơn đến dạng phong phú hơn. Client có thể chọn part cuối cùng mà nó hiểu. Vì vậy, khi tạo thủ công multipart/alternative bằng Jakarta Mail, thường đặt text/plain trước text/html.

Với `MimeMessageHelper`, hãy dùng overload `setText(plainText, htmlText)` thay vì tự tạo các body part nếu không có nhu cầu đặc biệt. Helper quản lý thứ tự và charset của các alternative.

### Khi nào không cần multipart/alternative?

Nếu email chỉ có nội dung văn bản đơn giản, `SimpleMailMessage` hoặc một `MimeMessage` với `text/plain` là đủ. Nếu email chỉ có HTML và không cần phiên bản text, có thể gọi `setText(html, true)`. Không cần tạo multipart/alternative chỉ vì muốn dùng HTML.

Tuy nhiên, email có HTML quan trọng thường nên có bản text tương ứng để tăng khả năng đọc trên các client và hệ thống chỉ xử lý plain text.

## 3. MIME multipart/related: HTML và tài nguyên mà nó tham chiếu

Một HTML body có thể tham chiếu ảnh bằng CID:

~~~html
<img src="cid:brand-logo" alt="Company logo">
~~~

Ảnh được thêm vào message như một MIME part có `Content-ID` tương ứng. **multipart/related** biểu diễn rằng các part này có quan hệ với nhau: một part là nội dung gốc, các part khác là tài nguyên cần thiết để hiển thị nội dung đó.

~~~text
multipart/related
  |
  +-- text/html
  |     |
  |     +-- <img src="cid:brand-logo">
  |
  +-- image/png
        Content-ID: <brand-logo>
        Content-Disposition: inline
~~~

Trong cấu trúc này, HTML là nội dung chính; ảnh PNG là tài nguyên liên quan. Email client có thể giải quyết `cid:brand-logo` bằng cách tìm body part có Content-ID tương ứng.

Trong Spring:

~~~java
helper.setText(html, true);
helper.addInline(
        "brand-logo",
        new ClassPathResource("mail/images/brand-logo.png"),
        "image/png");
~~~

`addInline` phải được gọi **sau `setText`**. Khi body đã được thiết lập, helper mới gắn resource vào cấu trúc multipart phù hợp. Gọi theo thứ tự ngược có thể khiến một số mail reader không giải quyết được CID đúng cách.

### CID và Content-ID phải khớp

Trong HTML:

~~~html
<img src="cid:brand-logo" alt="Company">
~~~

Trong Java:

~~~java
helper.addInline("brand-logo", logoResource, "image/png");
~~~

Không thêm tiền tố `cid:` vào đối số `contentId` của `addInline`. Helper sẽ tạo header Content-ID cho MIME part. Nếu HTML dùng `cid:brand-logo` nhưng code thêm ID `logo`, email có thể vẫn được SMTP chấp nhận nhưng ảnh sẽ không xuất hiện.

## 4. MIME multipart/mixed: nội dung thư và các phần độc lập

**multipart/mixed** thường được dùng để gửi một nội dung thư cùng các attachment. Các part là những thành phần độc lập được đóng gói trong cùng message.

~~~text
multipart/mixed
  |
  +-- text/plain hoặc text/html
  |
  +-- application/pdf
        Content-Disposition: attachment
        filename="invoice.pdf"
~~~

Ví dụ thêm file đính kèm:

~~~java
helper.setText("Hóa đơn của bạn được đính kèm.", false);
helper.addAttachment(
        "invoice.pdf",
        new ClassPathResource("mail/files/invoice.pdf"));
~~~

Attachment không phải một alternative của body và cũng không phải tài nguyên mà HTML cần để render. Nó là một part độc lập mà email client có thể trình bày trong vùng tệp đính kèm.

Nếu một email có cả HTML, inline image và PDF, chỉ dùng một multipart/mixed phẳng có thể làm các part bị diễn giải không như mong muốn ở một số client. Khi đó cần một cấu trúc lồng nhau để thể hiện đúng quan hệ giữa HTML và ảnh, đồng thời giữ PDF là attachment độc lập.

## 5. Vì sao cần multipart lồng nhau khi có HTML, ảnh inline và attachment?

Một email thường có cả ba yêu cầu:

1. Có plain text cho client không render HTML.
2. Có HTML và ảnh CID để tạo nội dung phong phú.
3. Có PDF attachment để người nhận tải xuống.

Một cấu trúc MIME khái quát phù hợp có thể là:

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
  |           Content-ID: <brand-logo>
  |
  +-- application/pdf
        Content-Disposition: attachment
        filename="invoice.pdf"
~~~

Quan hệ trong cấu trúc này:

- **Alternative** đặt plain và HTML như hai phiên bản của cùng nội dung.
- **Related** gắn ảnh với HTML đang tham chiếu CID.
- **Mixed** đặt nội dung thư và PDF attachment cạnh nhau như các phần độc lập.

Đây là mô hình MIME thường dùng cho email HTML có ảnh inline và attachment. Cấu trúc lồng thực tế có thể thay đổi theo multipart mode và cách thư viện tạo message, nhưng ý nghĩa của các quan hệ cần được giữ.

Nếu đặt image part như một attachment ngang hàng không liên quan với HTML, client có thể hiển thị nó thành tệp rời hoặc không tìm thấy CID. Nếu đặt PDF vào multipart/related cùng HTML, client có thể coi nó là tài nguyên của nội dung thay vì một attachment thông thường.

## 6. Multipart mode của MimeMessageHelper

Spring cung cấp các multipart mode trong `MimeMessageHelper`. Khi tạo helper, mode được chọn ảnh hưởng cách helper tổ chức các MIME part:

| Mode | Cấu trúc khái quát | Cách dùng |
|---|---|---|
| `MULTIPART_MODE_NO` | Không tạo multipart | Email một phần đơn giản, không inline/attachment |
| `MULTIPART_MODE_MIXED` | Một multipart/mixed ở root | Nội dung và các part được thêm ở cùng cấp |
| `MULTIPART_MODE_RELATED` | Một multipart/related ở root | HTML và inline resources, thường không có attachment độc lập |
| `MULTIPART_MODE_MIXED_RELATED` | multipart/mixed root, lồng multipart/related | HTML, inline resources và attachment cùng message |

Khi cần email HTML có cả inline image và attachment, `MULTIPART_MODE_MIXED_RELATED` thường là lựa chọn phù hợp. Đây cũng là **mode mặc định của constructor multipart boolean** trong các phiên bản Spring Framework phổ biến:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");
~~~

Có thể chỉ định rõ mode để người đọc code thấy ý định:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name());
~~~

### MULTIPART_MODE_RELATED

Mode này tạo multipart/related ở root. Nó phù hợp với email HTML có inline image và không cần nhóm attachment độc lập. Nếu thêm attachment vào cùng cấu trúc related, một số client có thể xử lý khác với mong muốn vì attachment và inline resource cùng ở một cấp.

### MULTIPART_MODE_MIXED

Mode này tạo multipart/mixed ở root và các phần được thêm ở cùng cấp. Cấu trúc phẳng có thể hoạt động trong một số client, nhưng quan hệ giữa HTML và inline resource không được thể hiện bằng nested related rõ ràng. Do đó khả năng tương thích có thể kém hơn với email HTML phức tạp.

### MULTIPART_MODE_MIXED_RELATED

Mode này tạo multipart/mixed ở root với một multipart/related lồng bên trong. Các phần liên quan đến HTML, bao gồm inline resources, nằm trong vùng related; attachment độc lập nằm ở cấp mixed. Đây là lựa chọn thường phù hợp khi email có **HTML + CID images + attachment**.

**Không chọn mode chỉ dựa trên việc email có bao nhiêu file.** Hãy chọn theo quan hệ giữa các part và yêu cầu hiển thị của email client mục tiêu.
## 7. Thứ tự gọi các phương thức của MimeMessageHelper

Khi một message có nhiều định dạng, hãy thiết lập nội dung chính trước rồi mới thêm resource mà nội dung tham chiếu. Một thứ tự thực hành dễ hiểu:

1. Tạo `MimeMessage`.
2. Tạo `MimeMessageHelper` với multipart mode phù hợp.
3. Thiết lập From, To, Cc/Bcc, Subject và các header cần thiết.
4. Gọi `setText(...)` để tạo body plain text, HTML hoặc cả hai.
5. Gọi `addInline(...)` cho các ảnh được HTML tham chiếu bằng CID.
6. Gọi `addAttachment(...)` cho các file độc lập người nhận tải xuống.
7. Gửi message bằng `JavaMailSender.send(...)`.

Sơ đồ:

~~~text
createMimeMessage()
        |
        v
new MimeMessageHelper(..., multipartMode, "UTF-8")
        |
        v
setFrom / setTo / setSubject
        |
        v
setText(plainText, htmlText)
        |
        v
addInline(cid, resource)
        |
        v
addAttachment(filename, resource)
        |
        v
JavaMailSender.send(message)
~~~

Điều kiện thứ tự quan trọng nhất đối với ảnh inline là **setText phải đứng trước addInline**. Attachment nên được thêm sau khi nội dung chính và inline resource đã được thiết lập để luồng code phản ánh rõ cấu trúc message. Không cần gọi lại setText sau khi đã thêm ảnh.

### Vì sao không gọi setText lần nữa ở cuối?

setText thiết lập body part của message. Nếu gọi lại sau khi đã thêm inline resource, có thể thay thế hoặc làm thay đổi phần body/multipart mà resource đang liên quan tới. Hãy chuẩn bị nội dung hoàn chỉnh trước, gọi setText một lần, rồi gắn các resource tương ứng.

Nếu phải thay đổi nội dung sau khi đã tạo helper, cách an toàn và dễ hiểu hơn thường là dựng lại message/helper từ đầu theo đúng trình tự, thay vì sửa cây MIME từng phần trong trạng thái đã hoàn tất.

## 8. Ví dụ đầy đủ: text, HTML, inline image và PDF attachment

Ví dụ dưới đây dùng `MULTIPART_MODE_MIXED_RELATED` để thể hiện rõ mục đích của từng phần:

~~~java
import jakarta.mail.MessagingException;
import jakarta.mail.internet.MimeMessage;
import java.nio.charset.StandardCharsets;
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

    public void sendOrderConfirmation(String recipient)
            throws MessagingException {

        MimeMessage message = mailSender.createMimeMessage();
        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        String plainText = """
                Xin chào!
                Đơn hàng ORD-2026-001 đã được xác nhận.
                Hóa đơn PDF được đính kèm trong email.
                """;

        String htmlText = """
                <!doctype html>
                <html lang="vi">
                  <head><meta charset="UTF-8"></head>
                  <body>
                    <img src="cid:company-logo"
                         alt="Company"
                         width="140">
                    <h1>Đơn hàng đã được xác nhận</h1>
                    <p>Mã đơn hàng: <strong>ORD-2026-001</strong></p>
                    <p>Hóa đơn PDF được đính kèm trong email.</p>
                  </body>
                </html>
                """;

        helper.setFrom("orders@example.com");
        helper.setTo(recipient);
        helper.setSubject("Xác nhận đơn hàng ORD-2026-001");

        // Thiết lập hai alternative: text/plain và text/html.
        helper.setText(plainText, htmlText);

        // Ảnh logo thuộc nội dung HTML: thêm sau setText.
        helper.addInline(
                "company-logo",
                new ClassPathResource("mail/images/company-logo.png"),
                "image/png");

        // PDF là file độc lập để người nhận tải xuống.
        helper.addAttachment(
                "hoa-don-ORD-2026-001.pdf",
                new ClassPathResource("mail/files/invoice-ORD-2026-001.pdf"),
                "application/pdf");

        mailSender.send(message);
    }
}
~~~

Giả sử các resource nằm trong:

~~~text
src/main/resources/
└── mail/
    ├── images/
    │   └── company-logo.png
    └── files/
        └── invoice-ORD-2026-001.pdf
~~~

Trong ví dụ này:

- setText(plainText, htmlText) tạo phần alternative.
- addInline("company-logo", ...) thêm ảnh mà HTML tham chiếu.
- addAttachment(...) thêm PDF độc lập.
- Mode mixed-related giúp nhóm HTML và ảnh trong related, còn PDF ở vùng mixed bên ngoài.
- Charset UTF-8 giữ đúng nội dung tiếng Việt.

Không nên chỉ đổi multipart mode mà giữ nguyên mọi thứ khác rồi kết luận email tương thích hơn. Hãy kiểm tra message được serialize và thử với các email client mà ứng dụng hỗ trợ.

## 9. Chọn multipart mode theo loại email

Một hướng chọn mode thực tế:

| Nội dung email | Mode thường phù hợp | Ghi chú |
|---|---|---|
| Plain text đơn giản | `MULTIPART_MODE_NO` | Không có ảnh inline hoặc attachment |
| HTML đơn giản, không ảnh/attachment | Không cần multipart hoặc `NO` | Chỉ một text/html part |
| HTML + inline images, không attachment | `MULTIPART_MODE_RELATED` hoặc default mixed-related | Related thể hiện ảnh gắn với HTML |
| Plain + HTML, không ảnh/attachment | Multipart alternative được helper quản lý | Dùng `setText(plain, html)` |
| HTML + inline images + PDF attachment | `MULTIPART_MODE_MIXED_RELATED` | Related bên trong mixed |
| Plain + HTML + inline images + attachment | `MULTIPART_MODE_MIXED_RELATED` | Cấu trúc đầy đủ thường dùng |
| Nhiều loại part với quy tắc MIME riêng | Cấu trúc Jakarta Mail tùy chỉnh | Chỉ dùng khi helper không đáp ứng yêu cầu |

### Khi chỉ có HTML và inline image

`MULTIPART_MODE_RELATED` có thể phù hợp vì toàn bộ nội dung của message là một nhóm liên quan: HTML và các ảnh CID. `MULTIPART_MODE_MIXED_RELATED` cũng có thể dùng được, nhưng tạo thêm lớp mixed ở root dù không có attachment độc lập.

### Khi có attachment độc lập

Nếu PDF hoặc tài liệu cần được hiển thị trong vùng attachment, `MULTIPART_MODE_MIXED_RELATED` thể hiện quan hệ rõ hơn: phần nội dung thư (related group) là một phần của mixed root; file đính kèm là part độc lập khác.

### Khi chỉ dùng MULTIPART_MODE_MIXED

Mode mixed đặt các part ở cùng cấp root. Cấu trúc phẳng có thể được nhiều client xử lý, nhưng không diễn tả rõ ràng rằng ảnh thuộc về HTML. Đặc biệt khi message có inline images và attachment, mixed-related thường là lựa chọn dễ tương thích hơn.

## 10. Điều gì xảy ra nếu multipart mode không phù hợp?

Một số dấu hiệu có thể xuất hiện:

| Dấu hiệu | Khả năng liên quan đến cấu trúc |
|---|---|
| Ảnh CID thành attachment rời | Image part không được đặt trong related group phù hợp, CID không khớp hoặc client xử lý khác |
| PDF hiển thị như nội dung inline | Content-Disposition hoặc vị trí part không thể hiện attachment đúng |
| Chỉ thấy plain text dù có HTML | Client chọn part plain text, cấu trúc alternative hoặc Content-Type không đúng |
| Thấy cả plain và HTML như hai đoạn nối tiếp | Hai part không được tổ chức thành multipart/alternative |
| Ảnh không hiển thị dù CID đúng | Part không ở related group phù hợp, Content-ID header sai hoặc client chặn/không hỗ trợ |
| Attachment biến mất khi thêm inline image | Cấu trúc multipart bị dựng sai hoặc helper bị dùng không đúng thứ tự |
| Một client hiển thị khác client khác | Client có thể áp dụng heuristic hoặc mức hỗ trợ MIME khác nhau |

**Không phải mọi lỗi hiển thị đều do multipart mode.** Cần kiểm tra CID, Content-Type, Content-Disposition, dữ liệu ảnh, kích thước, charset và chính sách chặn ảnh của client. Một email client có thể chủ động ẩn ảnh hoặc yêu cầu người nhận cho phép hiển thị.

## 11. Content-Disposition và Content-ID phối hợp với multipart

Hai header thường liên quan tới cách client xử lý ảnh và attachment:

**Content-ID** xác định một MIME part để nội dung khác tham chiếu. HTML dùng URI `cid:...` và part có header Content-ID tương ứng.

**Content-Disposition** gợi ý cách trình bày part:

- `inline`: nội dung có thể được hiển thị cùng message.
- `attachment`: nội dung là tệp độc lập người nhận tải xuống.

Ví dụ khái quát:

~~~mime
Content-Type: image/png
Content-Transfer-Encoding: base64
Content-ID: <company-logo>
Content-Disposition: inline
~~~

~~~mime
Content-Type: application/pdf
Content-Transfer-Encoding: base64
Content-Disposition: attachment; filename="invoice.pdf"
~~~

**Content-Disposition: inline một mình không bảo đảm ảnh xuất hiện đúng vị trí.** HTML còn phải tham chiếu đúng CID, và MIME hierarchy cần thể hiện quan hệ related. Tương tự, chỉ có Content-ID nhưng không có thẻ HTML tham chiếu thì ảnh có thể không được dùng trong body.

Một số email client có thể tự hiển thị hoặc gom nhóm attachment theo heuristic riêng. Hãy coi MIME headers và multipart hierarchy là hợp đồng gửi đi, còn giao diện cuối cùng vẫn cần được kiểm tra trên client mục tiêu.
## 12. Kiểm tra cấu trúc MIME thay vì chỉ nhìn giao diện

Khi email hiển thị sai, nên kiểm tra **message đã serialize** để biết helper thực sự tạo cấu trúc gì. Chỉ nhìn lời gọi `addInline` hoặc `addAttachment` chưa chứng minh MIME cuối cùng đúng.

Quy trình:

1. Tạo message trong bộ nhớ bằng `MimeMessage` và `MimeMessageHelper`.
2. Gọi các phương thức theo đúng thứ tự.
3. Gọi `saveChanges()` để hoàn tất header và metadata.
4. Serialize bằng `writeTo(...)`.
5. Parse lại byte thành một `MimeMessage` mới.
6. Duyệt cây multipart để tìm các part theo MIME type, Content-ID và Content-Disposition.

Ví dụ kiểm tra cấu trúc sau serialize/parse:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import jakarta.mail.BodyPart;
import jakarta.mail.Multipart;
import jakarta.mail.Part;
import jakarta.mail.Session;
import jakarta.mail.internet.MimeMessage;
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.mail.javamail.MimeMessageHelper;

class MultipartStructureTest {
    @Test
    void buildsAlternativeRelatedAndMixedParts() throws Exception {
        Session session = Session.getInstance(new Properties());
        MimeMessage message = new MimeMessage(session);

        MimeMessageHelper helper = new MimeMessageHelper(
                message,
                MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
                StandardCharsets.UTF_8.name());

        helper.setFrom("orders@example.test");
        helper.setTo("customer@example.test");
        helper.setSubject("Order confirmation");

        helper.setText(
                "Order ORD-001 is confirmed.",
                "<html><body><img src=\"cid:brand-logo\" "
                        + "alt=\"Brand\">Order ORD-001</body></html>");

        helper.addInline(
                "brand-logo",
                new ByteArrayResource(new byte[] {1, 2, 3, 4}),
                "image/png");
        helper.addAttachment(
                "invoice.pdf",
                new ByteArrayResource(new byte[] {5, 6, 7, 8}),
                "application/pdf");

        message.saveChanges();
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        message.writeTo(output);

        MimeMessage parsed = new MimeMessage(
                session,
                new ByteArrayInputStream(output.toByteArray()));

        assertThat(parsed.isMimeType("multipart/mixed")).isTrue();

        List<Part> parts = new ArrayList<>();
        collectParts(parsed, parts);

        assertThat(parts).anySatisfy(part ->
                assertThat(part.isMimeType("multipart/related")).isTrue());
        assertThat(parts).anySatisfy(part ->
                assertThat(part.isMimeType("multipart/alternative")).isTrue());
        assertThat(parts).anySatisfy(part -> {
            assertThat(part.isMimeType("image/png")).isTrue();
            assertThat(part.getDisposition()).isEqualTo(Part.INLINE);
            assertThat(contentId(part)).isEqualTo("brand-logo");
        });
        assertThat(parts).anySatisfy(part -> {
            assertThat(part.isMimeType("application/pdf")).isTrue();
            assertThat(part.getDisposition()).isEqualTo(Part.ATTACHMENT);
        });
    }

    private static void collectParts(
            Part part, List<Part> result) throws Exception {
        result.add(part);
        Object content = part.getContent();
        if (content instanceof Multipart multipart) {
            for (int i = 0; i < multipart.getCount(); i++) {
                BodyPart child = multipart.getBodyPart(i);
                collectParts(child, result);
            }
        }
    }

    private static String contentId(Part part) throws Exception {
        String[] values = part.getHeader("Content-ID");
        if (values == null || values.length == 0) {
            return null;
        }
        return values[0].replace("<", "").replace(">", "").trim();
    }
}
~~~

Ví dụ dùng byte array ngắn để minh họa việc kiểm tra **cấu trúc MIME**, không phải ảnh PNG/PDF thực. Khi kiểm tra khả năng render thật, hãy dùng file fixture hợp lệ trên classpath và kiểm tra nội dung của file. Test này giả định phiên bản Spring/Jakarta Mail của dự án hỗ trợ multipart mode đã chọn.

### Vì sao phải parse lại message?

Đọc cùng object ngay sau khi gọi helper có thể chỉ cho thấy các trạng thái đang nằm trong bộ nhớ. Serialize rồi parse lại giúp kiểm tra **header và multipart đã được ghi ra byte** theo cách email client sẽ nhận. Điều này phát hiện được lỗi xảy ra trong quá trình tạo boundary, Content-ID, Content-Disposition hoặc cấu trúc lồng.

### Không kiểm tra part bằng index cố định

Không nên viết:

~~~java
Multipart root = (Multipart) parsed.getContent();
BodyPart image = root.getBodyPart(1); // Giả định mong manh
~~~

Với mixed-related, part ảnh có thể nằm trong multipart/related lồng bên trong root; part PDF có thể nằm ở cấp mixed. Khi thêm text alternative hoặc resource khác, index có thể đổi. Duyệt đệ quy và tìm theo `isMimeType`, Content-ID, Content-Disposition sẽ bền hơn.

## 13. Kiểm tra raw MIME bằng SMTP sink

Unit test với Jakarta Mail giúp xác minh message được tạo ra. Khi cần quan sát cách message đi qua SMTP transport, dùng một **SMTP sink/test server** trong local hoặc CI:

~~~text
Application
   |
   | JavaMailSender.send(...)
   v
SMTP sink
   |
   +-- Raw message source
   +-- multipart/mixed root
   +-- multipart/related group
   +-- multipart/alternative group
   +-- Content-ID của ảnh
   +-- Content-Disposition của attachment
~~~

SMTP sink nhận thư nhưng không chuyển đến người nhận thật. Giao diện của sink thường cho xem raw source và các part đã giải mã, giúp so sánh:

- Subject và header.
- `Content-Type` của root và các multipart con.
- HTML có `cid:...` hay không.
- Inline image có Content-ID và disposition tương ứng.
- PDF có filename và disposition attachment.
- Nội dung text/plain và text/html có cùng ý nghĩa hay không.

Không dùng mailbox khách hàng hoặc dữ liệu nhạy cảm trong sink chưa được bảo vệ. Công cụ capture có thể lưu toàn bộ MIME message và file đính kèm; cần giới hạn quyền truy cập và thời gian lưu.

### Khi nào cần gửi thử qua email client thật?

MIME round-trip chứng minh cấu trúc và dữ liệu được serialize đúng theo thư viện. Nó không bảo đảm mọi email client render giống nhau. Nếu ứng dụng hỗ trợ Outlook desktop, Outlook web, Gmail hoặc ứng dụng mobile cụ thể, hãy gửi một bộ message thử nghiệm tới tài khoản được kiểm soát và quan sát từng client.

SMTP sink và MIME parser là bước chẩn đoán; client test là bước xác nhận trải nghiệm hiển thị.
## 14. Email client có thể diễn giải cùng MIME khác nhau

MIME quy định cách biểu diễn message, nhưng email client còn có logic riêng để hiển thị nội dung. Một số client xử lý inline resource, attachment, CSS và HTML khác nhau. Do đó, một MIME tree hợp lệ là điều kiện quan trọng nhưng chưa đủ để bảo đảm giao diện giống nhau ở mọi nơi.

Các khác biệt thường gặp:

- Client có thể chọn text/plain hoặc text/html dựa trên khả năng và cài đặt của người nhận.
- Client có thể hiển thị inline image ngay trong body, hoặc liệt kê ảnh trong vùng attachment.
- Client có thể ẩn ảnh từ xa, nhưng CID image thường được xử lý từ MIME message; vẫn có client áp dụng chính sách riêng.
- Client có thể loại bỏ một số HTML/CSS, không hỗ trợ SVG hoặc thay đổi bố cục.
- Một số hệ thống bảo mật có thể quét, viết lại hoặc loại bỏ MIME part trước khi message đến hộp thư.

Vì thế, khi điều tra lỗi, cần phân biệt ba lớp:

1. **MIME đã tạo đúng chưa?** Kiểm tra raw message và cây multipart.
2. **Transport/gateway có thay đổi message không?** So sánh bản capture trước và sau relay nếu hệ thống cho phép.
3. **Client nhận đã hiển thị thế nào?** Kiểm tra trên các client/phiên bản được hỗ trợ.

Không nên kết luận Spring Mail tạo MIME sai chỉ vì một client không hiện ảnh. Ngược lại, việc email hiển thị đúng trên Gmail cũng không chứng minh cấu trúc MIME phù hợp với mọi client.

### Ma trận kiểm tra client

Một bộ kiểm thử thủ công có thể bao gồm:

| Trường hợp | Cần quan sát |
|---|---|
| Client web hiện đại | HTML, ảnh CID, attachment và link |
| Client desktop | Inline image có nằm trong body, PDF có hiện trong attachment list |
| Ứng dụng mobile | Ảnh có tải/hiển thị, layout có đọc được trên màn hình nhỏ |
| Client text-only hoặc chế độ plain text | Bản text có đầy đủ thông tin quan trọng |
| Chế độ chặn ảnh | Alt text có ý nghĩa, nội dung không phụ thuộc hoàn toàn vào ảnh |
| Hệ thống mail có security gateway | MIME part có bị đổi tên, loại bỏ hoặc viết lại |

Hãy ghi rõ phiên bản client và cấu hình test. “Outlook” hoặc “Gmail” có thể chỉ nhiều ứng dụng, nền tảng và phiên bản khác nhau; một kết quả test không đại diện tuyệt đối cho tất cả.

## 15. Chẩn đoán các lỗi multipart theo triệu chứng

| Triệu chứng | Kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| HTML hiển thị nhưng logo không hiện | HTML CID, Content-ID, vị trí image part | Đồng bộ CID; dùng related group; gọi setText trước addInline |
| Logo hiện thành file đính kèm | Content-Disposition và multipart hierarchy | Kiểm tra addInline và multipart mode |
| PDF không xuất hiện trong attachment list | Content-Disposition, filename, root mixed | Dùng addAttachment và mixed-related khi có inline resources |
| Plain text và HTML cùng xuất hiện | Có thực sự dùng multipart/alternative không | Dùng setText(plain, html), không tạo hai part độc lập ở mixed root |
| Chỉ hiện plain text | Client đang chọn alternative nào, Content-Type của HTML | Kiểm tra MIME part, cấu trúc alternative và cài đặt client |
| Thêm attachment thì ảnh inline mất | Multipart mode và cây MIME sau khi thêm attachment | Dùng mixed-related, kiểm tra root/related nesting |
| Ảnh không có Content-ID | Resource được thêm bằng addAttachment hoặc CID sai | Dùng addInline với đúng contentId |
| MIME đúng nhưng client vẫn không hiện ảnh | Chính sách client, định dạng ảnh, relay/gateway | Thử PNG/JPEG, alt text, so sánh raw MIME tại các hop |
| File mở không được | Byte file, content type, transfer encoding | Kiểm tra resource gốc và MIME type khai báo |
| Email client báo message malformed | Boundary, nested multipart, header | Parse raw MIME bằng Jakarta Mail và xem gateway có viết lại không |

### Quy trình điều tra

~~~mermaid
flowchart TD
    A[Email hiển thị sai] --> B[Capture raw MIME]
    B --> C{Root multipart đúng mục đích?}
    C -- Không --> D[Chọn lại multipart mode / cấu trúc]
    C -- Có --> E{Alternative, related và mixed được lồng đúng?}
    E -- Không --> F[Kiểm tra setText và addInline/addAttachment]
    E -- Có --> G{CID và disposition đúng?}
    G -- Không --> H[Sửa Content-ID hoặc cách thêm part]
    G -- Có --> I{Relay có sửa message?}
    I -- Có --> J[Điều tra gateway/security policy]
    I -- Không --> K[Kiểm tra email client và khả năng render]
~~~

Đừng thay multipart mode ngẫu nhiên trước khi capture raw MIME. Một thay đổi có thể làm email hiển thị đúng trong client đang thử nhưng phá hành vi ở client khác.

## 16. Lỗi do thứ tự gọi API

### addInline trước setText

Đây là lỗi thứ tự phổ biến nhất với HTML và CID:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.addInline("brand-logo", logoResource);
helper.setText(html, true);
~~~

**Không nên dùng trình tự này.** Khi addInline được gọi trước, helper có thể chưa tạo phần body mà resource cần liên kết. Một số mail reader có thể không giải quyết được CID.

Trình tự đúng:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, true, "UTF-8");

helper.setText(html, true);
helper.addInline("brand-logo", logoResource);
~~~

### Gọi setText sau addInline

Nếu đã thêm ảnh rồi lại thay body bằng một lần setText khác, cấu trúc có thể không còn tương ứng với những CID đã thêm. Hãy hoàn tất chuỗi HTML/plain trước, gọi setText một lần, sau đó thêm tất cả inline resource.

### Dùng helper không bật multipart

Nếu tạo:

~~~java
MimeMessageHelper helper =
        new MimeMessageHelper(message, false, "UTF-8");
~~~

thì helper ở chế độ không multipart. Không thể dùng cấu hình này để thêm inline resource hoặc attachment như một message multipart. Hãy chọn constructor multipart và mode tương ứng:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        "UTF-8");
~~~

### Gọi setText(plain, html) nhưng truyền nhầm thứ tự

Overload nhận hai chuỗi có thứ tự **plainText trước, htmlText sau**:

~~~java
helper.setText(plainText, htmlText);
~~~

Nếu truyền HTML vào tham số đầu và plain text vào tham số thứ hai, helper sẽ diễn giải sai vai trò của hai part. Client có thể chọn nội dung không mong muốn hoặc hiển thị tag HTML như văn bản.

## 17. Charset và transfer encoding trong từng part

Multipart mode xác định quan hệ giữa các part, nhưng **không thay thế cấu hình charset**. Mỗi text part vẫn cần Content-Type phù hợp, ví dụ:

~~~mime
Content-Type: text/plain; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

~~~mime
Content-Type: text/html; charset=UTF-8
Content-Transfer-Encoding: quoted-printable
~~~

Trong Spring:

~~~java
MimeMessageHelper helper = new MimeMessageHelper(
        message,
        MimeMessageHelper.MULTIPART_MODE_MIXED_RELATED,
        StandardCharsets.UTF_8.name());
~~~

Truyền UTF-8 giúp các part văn bản được tạo đúng charset. Ảnh và PDF là dữ liệu nhị phân nên có content type tương ứng và transfer encoding phù hợp, thường là Base64. Không áp dụng charset UTF-8 lên byte ảnh hoặc PDF như thể chúng là văn bản.

Nếu text/plain đúng nhưng HTML sai dấu, kiểm tra từng part riêng. Nếu cả hai sai, xem dữ liệu nguồn và cấu hình encoding chung. Nếu chữ đúng nhưng ảnh mất, vấn đề nhiều khả năng nằm ở CID/multipart/resource, không phải charset.
## 18. Kiểm thử theo các cấu hình multipart

Khi một ứng dụng có nhiều loại email, nên có test riêng cho từng cấu hình:

| Test case | Nội dung | Điều cần xác nhận |
|---|---|---|
| Plain only | Một body text/plain | Không tạo multipart không cần thiết |
| HTML only | Một body text/html | Content-Type và charset đúng |
| Plain + HTML | Hai alternative | Cùng thông tin, đúng thứ tự alternative |
| HTML + inline image | Related group | CID khớp image part |
| HTML + attachment | Nội dung và file độc lập | Attachment có filename/disposition phù hợp |
| Plain + HTML + inline image + attachment | Mixed/related/alternative lồng nhau | Root, nested groups và từng part đúng |

Không phải mọi tổ hợp đều cần một SMTP integration test. Có thể kiểm tra phần lớn cấu trúc bằng cách tạo MimeMessage trong bộ nhớ, serialize rồi parse lại. Chỉ dùng SMTP sink khi cần xác minh transport hoặc cách provider nhận message.

### Kiểm tra alternative

Với message chỉ có text/plain và text/html, parse lại rồi kiểm tra message có multipart/alternative hoặc một cấu trúc alternative tương đương do helper tạo. Duyệt các part và xác nhận:

- Có một part text/plain.
- Có một part text/html.
- Nội dung hai part cùng mô tả một thông điệp.
- Charset của từng part được khai báo phù hợp.

Không assert toàn bộ HTML bằng một snapshot dài nếu mục tiêu chỉ là kiểm tra nội dung. Hãy kiểm tra các thông tin quan trọng và các phần được render.

### Kiểm tra inline image

Với từng ảnh, kiểm tra:

- Có đúng một MIME part mang Content-ID tương ứng.
- Content-Type phản ánh định dạng ảnh thật.
- Content-Disposition phù hợp với inline resource.
- HTML body có tham chiếu đúng CID.
- Resource có byte hợp lệ và không vượt giới hạn dung lượng.

### Kiểm tra attachment

Với mỗi attachment, kiểm tra:

- MIME type đúng.
- Content-Disposition là attachment theo ý định.
- Filename đúng và không chứa đường dẫn filesystem.
- Byte sau khi decode giống nội dung file gốc.
- File không vượt giới hạn mà ứng dụng/provider cho phép.

## 19. Quy trình kiểm thử hiển thị trên email client

Một test MIME trong bộ nhớ không thể thay thế hoàn toàn việc xem email trên client. Khi thay đổi multipart mode hoặc template, có thể dùng quy trình:

1. Dựng một message thử nghiệm có text/plain, HTML, một inline image và một PDF attachment.
2. Gửi tới SMTP sink hoặc tài khoản test do tổ chức quản lý.
3. Lưu raw MIME để có bằng chứng về cấu trúc message.
4. Mở email trên các client/phiên bản mà sản phẩm hỗ trợ.
5. Kiểm tra ảnh inline, bản text, attachment, link, bố cục và chế độ chặn ảnh.
6. Nếu client khác nhau, so sánh MIME tại nơi gửi và nơi nhận nếu hạ tầng cho phép.

Một mẫu test data:

~~~text
Subject: Xác nhận đơn hàng ORD-TEST-001
Plain text: Có mã đơn, tổng tiền và thông tin hỗ trợ
HTML: Có logo CID và cùng thông tin nghiệp vụ
Inline image: brand-logo.png
Attachment: invoice-ORD-TEST-001.pdf
Recipient: mailbox thử nghiệm
~~~

Không dùng email khách hàng thật hoặc attachment chứa dữ liệu nhạy cảm trong quá trình kiểm tra. Dữ liệu thử nên được tạo riêng và có thể xóa sau khi hoàn thành.

### Những gì cần xác nhận bằng mắt

- Logo nằm trong nội dung ở đúng vị trí, không chỉ xuất hiện trong attachment list.
- Nội dung chính vẫn đọc được khi ảnh bị chặn.
- PDF có thể tải xuống và mở được.
- Client text-only có bản text dễ hiểu.
- Không có phần HTML và text bị nối thành hai bản nội dung.
- Ảnh không bị phóng quá lớn hoặc làm vỡ bố cục.
- Link, màu chữ và khoảng cách không phụ thuộc vào ảnh để truyền đạt thông tin quan trọng.

## 20. Bảo mật và giới hạn của multipart resources

Multipart mode là cách tổ chức message, không phải cơ chế bảo mật. Các resource được nhúng hoặc đính kèm vẫn phải được kiểm soát:

- Chỉ lấy ảnh/file từ nguồn mà ứng dụng có quyền đọc và gửi.
- Không dùng đường dẫn filesystem do người dùng cung cấp trực tiếp.
- Kiểm tra kích thước, định dạng byte thực tế và Content-Type.
- Hạn chế số lượng inline resource và attachment để tránh email quá lớn.
- Không nhúng dữ liệu cá nhân hoặc token vào ảnh nếu không cần thiết.
- Không ghi raw MIME, attachment bytes, credential hoặc token vào log production.
- Kiểm tra quyền truy cập và thời gian lưu của SMTP sink/test mailbox.
- Cân nhắc việc tải ảnh từ URL bên ngoài; cần chống SSRF, redirect ngoài dự kiến và tải file quá lớn.

**Không tin phần mở rộng file là bằng chứng của định dạng.** Một file tên logo.png có thể chứa byte không phải PNG. Khi dữ liệu đến từ người dùng hoặc hệ thống bên ngoài, hãy kiểm tra nội dung file bằng cơ chế phù hợp trước khi đính kèm.

## 21. Câu hỏi thường gặp

**Có phải email có HTML luôn cần multipart/related?** Không. HTML không tham chiếu tài nguyên inline có thể là một text/html part đơn giản. Related hữu ích khi HTML có các resource như ảnh CID.

**Có phải mọi email có attachment đều cần mixed-related?** Không. Email chỉ có body và attachment có thể dùng mixed. Mixed-related đặc biệt hữu ích khi cùng message có HTML, inline resources và attachment độc lập.

**Tại sao constructor boolean true thường đủ?** Constructor multipart boolean của MimeMessageHelper thường chọn mode mixed-related mặc định, phù hợp với nhiều email HTML có inline elements và attachment. Nếu muốn code thể hiện ý định rõ ràng hoặc cần mode khác, dùng constructor nhận multipart mode.

**Có thể thêm attachment trước setText không?** Một số thứ tự có thể vẫn tạo được message, nhưng nên dùng trình tự rõ ràng: setText trước, addInline sau, rồi addAttachment. Điều kiện thứ tự được Spring nhấn mạnh trực tiếp là addInline phải đứng sau setText.

**Tại sao ảnh CID lại hiện thành file đính kèm?** Kiểm tra Content-ID, Content-Disposition, HTML reference và vị trí part trong related group. Cũng kiểm tra email client vì client có thể trình bày inline part theo cách riêng.

**Nếu CID đúng nhưng ảnh vẫn mất thì sao?** Xem raw MIME sau serialize, xác nhận image part tồn tại, content type đúng, byte ảnh hợp lệ và message có related structure phù hợp. Sau đó thử client khác hoặc kiểm tra gateway có sửa MIME hay không.

**Có nên tự tạo Multipart bằng Jakarta Mail thay vì dùng MimeMessageHelper?** Chỉ khi cấu trúc đặc biệt mà helper không đáp ứng. Với các trường hợp phổ biến, helper giúp quản lý alternative, related, mixed, charset và resource. Tự dựng cây MIME làm tăng trách nhiệm kiểm soát boundary, Content-ID, disposition và thứ tự.

**Multipart mode có sửa được CSS không tương thích không?** Không. Multipart chỉ tổ chức các phần MIME. CSS/HTML rendering là một vấn đề riêng và cần kiểm thử trên email client mục tiêu.

**SMTP server chấp nhận message có nghĩa client sẽ hiển thị đúng không?** Không. SMTP accepted chỉ cho biết server ở bước submission đã chấp nhận message; client có thể lọc, chặn ảnh hoặc diễn giải MIME theo khả năng riêng.

## 22. Nguyên tắc cần nhớ

Chọn multipart theo **quan hệ giữa các phần**, không chỉ theo số lượng part:

- **Alternative**: plain text và HTML là hai phiên bản của cùng nội dung.
- **Related**: HTML cùng ảnh/tài nguyên mà nó tham chiếu bằng CID.
- **Mixed**: nội dung thư cùng attachment độc lập.
- **Mixed-related**: mixed ở root, related group cho HTML và inline resource; phù hợp với email có HTML, ảnh CID và file đính kèm.

Trong Spring Framework Mail, hãy chọn multipart mode phù hợp, dùng setText(plain, html) khi cần hai phiên bản, gọi **setText trước addInline**, rồi thêm attachment độc lập. Kiểm tra MIME sau serialize/parse, không dựa vào index cố định của part, và thử trên email client mục tiêu khi khả năng hiển thị là yêu cầu sản phẩm.

**Một message gửi thành công chưa chắc hiển thị đúng.** Cấu trúc MIME phải diễn đạt đúng nội dung thay thế, tài nguyên liên quan và file độc lập; sau đó client mới có thể trình bày message theo cách phù hợp.
